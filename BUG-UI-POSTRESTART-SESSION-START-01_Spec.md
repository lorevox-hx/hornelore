# BUG-UI-POSTRESTART-SESSION-START-01 — `session_start` post-restart UI flow blocks resume for both narrators

**Status:** OPEN — pre-parent-session blocker
**Severity:** RED (blocks every cold-restart resume; affects both Mary and Marvin)
**Surfaced by:** TEST-23 v6 (2026-05-05)
**Author:** Chris + Claude (2026-05-05)
**Lane:** Lane 2 / parent-session blockers (top of queue, sequenced before WO-PROVISIONAL-TRUTH-01 Phase D because Phase D's harness verification depends on resume working)

---

## Problem

After cold-restart browser context + `_select_narrator_by_pid()` + 2.5s wait + `_close_popovers()`, neither **"Start Narrator Session"** nor **"Enter Interview Mode"** buttons render in the narrator-room UI. The harness's `session_start()` helper raises `RuntimeError: session_start: neither Start Narrator Session nor Enter Interview Mode visible` for both Mary and Marvin in v6.

This blocks every post-restart resume phase. Without it, all the resume-phase scoring (post-restart recall, post-restart Today, etc.) is downstream-RED-by-default — the narrator can't enter a session to be tested.

## Evidence

v6 run (2026-05-05):

```
[mary/restart] cold restart — closing browser context
  [mary/restart] navigating to http://localhost:8082/ui/hornelore1.0.html
  [mary/restart] re-selecting narrator pid=d1ecf805-...
  [mary/restart] post-reload state: firstName=None DOB=None basics=True
  [mary/restart] session_start threw: session_start: neither Start Narrator Session nor Enter Interview Mode visible

[marvin/restart] cold restart — closing browser context
  [marvin/restart] navigating to http://localhost:8082/ui/hornelore1.0.html
  [marvin/restart] re-selecting narrator pid=aa4992e8-...
  [marvin/restart] post-reload state: firstName=None DOB=None basics=True
  [marvin/restart] session_start threw: session_start: neither Start Narrator Session nor Enter Interview Mode visible
```

Both narrators fail at the same point. Both have `basicsComplete=true` after re-selection, so the v9-gate "Complete profile basics" interstitial is NOT the cause.

## Why this wasn't surfaced earlier

The harness exception handler at `scripts/ui/run_test23_two_person_resume.py:1519-1522` only `print()`s the exception — it does NOT append to `nr.notes`. So v4/v5 JSON reports didn't carry the signal. v6 console output captured it directly. (Documented in `docs/reports/MARY_POST_RESTART_AUDIT_2026-05-05.md`.)

## Reproduction

```bash
cd /mnt/c/Users/chris/hornelore
python -m scripts.ui.run_test23_two_person_resume --tag debug_postrestart --only mary
```

Watch the Chromium window during the post-restart phase. The `[mary/restart] session_start threw` line appears immediately after the re-select.

Manual reproduction (no harness):
1. Create a new test narrator via Bug Panel
2. Run an interview session (any duration)
3. Wrap session
4. Close the browser tab
5. Open a new tab to `http://localhost:8082/ui/hornelore1.0.html`
6. Re-select the same narrator from the narrator switcher
7. Look for "Start Narrator Session" or "Enter Interview Mode" buttons
8. Either button missing = repro confirmed

## Diagnosis (read-only first)

Likely candidates, ranked by confidence:

**A. UI is in post-session state, not pre-session.** When the previous session ended via `wrap_session()`, the narrator-room UI may have transitioned to a "session wrapped" view that shows different controls (e.g., "Start a new session" instead of "Start Narrator Session"). On re-select, the UI restores that state from persisted session-state metadata rather than the fresh "ready to start" state. Expected fix: detect post-session state on re-select and reset to ready-to-start, OR add the alternative button labels to the harness's selector list.

**B. Popover-state race.** The narrator-switcher popover may not fully close before `session_start()` tries to query the DOM. The harness already calls `_close_popovers()` at line 1511 with a 150ms wait, but on slower runs the popover may still be in the DOM hiding the buttons. Expected fix: increase the wait or wait for an explicit "popover-closed" signal.

**C. State hydration race.** `state.session.identityPhase` may transition through intermediate values during re-select (e.g., briefly "loading" before settling to "complete"). The buttons may render conditionally on `identityPhase === "complete"` or `identityPhase === "ready"` — if neither is set at the moment session_start runs, no buttons render.

**D. Narrator profile not fully hydrated despite `basicsComplete=true`.** The `state.person_id` may set before `state.bioBuilder.personal` populates. Buttons may render conditionally on `state.bioBuilder.personal.firstName` being truthy. Per the v6 audit, BB state firstName=None for both narrators on resume, so this would block button render. (BB mirror gap is BUG-class — see WO-PROVISIONAL-TRUTH-01 Phase D.)

## Diagnostic plan (read-only, before any code change)

1. **Capture DOM tree at the failure point.** Modify the harness to dump `await page.content()` to a file when session_start raises, OR add a 5-second `await page.pause()` before the exception so the operator can manually inspect.
2. **Capture state snapshot at the failure point.** Read `window.state.session`, `window.state.bioBuilder`, `window.state.person_id`, identityPhase, basicsComplete via `page.evaluate()` and dump to the report.
3. **Run with `--no-headless` + `--start-maximized`** (already enabled per WO-HARNESS-V4-VISIBILITY-01) and watch the post-restart phase manually. Note which UI elements ARE visible when session_start fails.
4. **Compare to a successful pre-restart session_start** — what's structurally different in the DOM between "narrator just created, never started a session" and "narrator wrap_session'd, just re-loaded by pid"?

## Acceptance gate

Cold-restart resume reaches a usable interview surface for both narrators in TEST-23. Specifically:

- After `_select_narrator_by_pid()` + 2.5s wait + `_close_popovers()`, the narrator-room shows EITHER "Start Narrator Session" OR "Enter Interview Mode" OR a button labeled to mean "resume the wrapped session" (whatever the post-session-pre-resume state is named)
- `session_start()` helper succeeds for both Mary and Marvin in TEST-23 v7
- Post-restart recall + Today phases run their scoring (PASS/AMBER/RED depending on Lori's actual behavior, NOT downstream-RED-by-default-because-session-never-started)

If the fix introduces a new button name (e.g. "Resume Session"), update the harness selector list to include it.

## Files (planned, after diagnostic)

**Likely modified:**
- `ui/js/app.js` (narrator-switcher post-select hydration, possibly v9-gate handler)
- `scripts/ui/run_parent_session_readiness_harness.py` (selector list at L74-75 if the fix introduces a new button label)

**Possibly modified:**
- `ui/hornelore1.0.html` (button render conditional logic)
- `ui/js/state.js` (session-state transition handling on re-select)

**Zero touch (don't expand scope):**
- Backend / extractor / Lori behavior services / story preservation

## Risks & rollback

**Risk 1: fix breaks the pre-restart flow.** session_start is called BOTH pre-restart (after fresh narrator creation) and post-restart (after re-select). A fix targeting post-restart could regress the pre-restart path. Mitigation: TEST-23 v7 must verify pre-restart session_start still succeeds for both narrators (it currently does in v6 — pre-restart phases are PASS/AMBER, not RED).

**Risk 2: button name change breaks operator muscle memory.** If the fix renames "Start Narrator Session" to something else, real operators may pause. Mitigation: keep the canonical labels stable; the fix should make the existing labels render reliably in post-restart state, not invent new labels.

**Rollback:** revert the patch. Cold-restart resume goes back to broken-by-default. Pre-restart sessions remain unaffected.

## Sequencing

This is the FIRST item in Phase 0 / Track 1 because:
- Every other parent-session-blocker fix needs working cold-restart resume to verify (BUG-LORI-MIDSTREAM-CORRECTION-01 + BUG-LORI-LATE-AGE-RECALL-01 are tested mid-session, but resume verification matters for the broader regression net)
- WO-PROVISIONAL-TRUTH-01 Phase D's acceptance gate requires the harness to grade post-restart BB state — which can't happen if resume doesn't start

After this fix lands, re-run TEST-23 to get a clean v7 baseline before continuing.

## Changelog

- 2026-05-05: Spec authored after v6 evidence + Mary post-restart audit revision. Initial diagnostic plan ranked four hypotheses by confidence; resolution gated on read-only DOM/state capture before any code change.
