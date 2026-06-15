# BUG-UI-POSTRESTART-SESSION-START-01 — `session_start` post-restart UI flow blocks resume for both narrators

**Status:** **REOPENED 2026-05-05 evening with refined hypothesis space.** Earlier same-day premature flip toward BUG-UI-API-BASE-RESET-01 was overfitting — API works correctly in production (manual switch transcripts confirm). The post-restart RED is Playwright-specific, not a production architecture failure. Real diagnostic question now: *after backend restart, does the real production UI restore narrator/interview state correctly, or only the Playwright harness fail?* Three new candidate hypotheses replace the original four (which all assumed production breakage).
**Severity:** AMBER for production — UNKNOWN until tested manually; RED for harness — blocks v7+ post-restart scoring
**Surfaced by:** TEST-23 v6 (2026-05-05); refined 2026-05-05 evening after manual transcript review
**Author:** Chris + Claude (2026-05-05)
**Lane:** Lane 2 / parent-session blockers — priority depends on whether production reproduces (high if yes, harness-cleanup if no)

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

---

## Refined hypothesis space (2026-05-05 evening, after manual transcript review)

The original four hypotheses (post-session UI state / popover-state race / state hydration race / BB hydration not complete) all assumed the failure was production-side. Manual switch transcripts on the same day showed the real UI working correctly (Lori reads identity, age math works, wife memory comes from session history). So the post-restart RED is likely harness-specific. Three replacement hypotheses:

**H1 — Playwright cold-restart timing differs from real-user reload.** The harness closes the browser context entirely and opens a fresh one with `_select_narrator_by_pid()` immediately. A real user reloading after a backend restart presses F5 on an existing tab; the page-load lifecycle is different. Things that survive an F5 (some in-memory state, cookies, http connection reuse) don't survive a Playwright context.close()/new_context(). Likely cause: harness's `_select_narrator_by_pid()` hits a state path the real UI never exercises.

**H2 — Backend WebSocket session not rebound after restart.** Backend restart breaks all open WebSocket connections. Real users' browser auto-reconnects on next page action (the existing chat_ws router handles reconnect). Playwright might not trigger that auto-reconnect until specific actions fire, and `_select_narrator_by_pid()` may run before the WS reconnects, returning stale state. The `[chat-ws] Phase G: WebSocket disconnected — cancelled in-flight, no stale replay` log entries in api.log between v7 phases support this.

**H3 — Narrator-room session resurrection logic doesn't fully fire under harness conditions.** The narrator-room has session resurrection logic (load latest session for this pid, restore turn count, restore era state, etc.) that may depend on certain DOM events or page lifecycle hooks. Playwright's `page.goto()` + `_select_narrator_by_pid()` + `_close_popovers()` may skip events the real UI relies on.

## Diagnostic plan (revised)

**Step 1 — manual cold-restart reproduction.** Run a real-browser test: start Marvin's session pre-restart in a regular browser, do some interview turns, wrap session, stop the backend stack, start it again, refresh the page. Does the narrator session restore correctly? If yes → bug is harness-specific (H1). If no → production has a real issue that needs investigation.

**Step 2 — if production reproduces:** capture DOM tree + state snapshot at the failure point in the real browser, compare to working pre-restart state. Same diagnostic as the original spec planned.

**Step 3 — if production does NOT reproduce:** narrow to harness fix. Likely candidates: increase post-context-restart wait time, add explicit WebSocket-reconnect probe before `session_start()`, add explicit page-event wait (e.g., wait for `state.session.identityPhase === "complete"` via `page.evaluate()` polling) instead of fixed timeouts.

## Acceptance gate (revised)

**If production reproduces (H2/H3):** real-user cold-restart resume succeeds for both narrators. Lori reads identity correctly post-restart. session_start UI buttons render reliably.

**If only harness reproduces (H1):** TEST-23 v8 post-restart phase reaches scoring (PASS/AMBER/RED on actual Lori behavior, not on missing buttons). The fix is in `scripts/ui/run_test23_two_person_resume.py:_restart_browser_and_resume()` — likely a wait-for-state-complete probe rather than fixed timeouts.

## Sequencing (revised)

The first action is the manual reproduction in step 1. Cheap (~5 min) and tells us whether this is parent-session-blocking (production bug) or harness-only (cleanup). Don't write any code until that's known.

If production reproduces → top of Track 1.
If harness-only → low priority, harness fix anytime.

## What changed from the original spec

The original spec's four hypotheses were all about the UI being in a wrong state (post-session view, popover-state race, etc.). Those are still possible but the manual transcripts make them less likely — real users go through the same UI states the harness goes through, and real users get working sessions. The remaining hypothesis space is about the *harness's specific path* through that UI, which differs from real-user navigation in ways that may matter (Playwright context close, WebSocket reconnect timing, page-event lifecycle).

The original spec is preserved above this section for reference.

## Cross-references

- **BUG-UI-API-BASE-RESET-01** — initially flipped to "actual root cause," reverted to "production hardening" after Chris pointed out the 404s only appeared in Playwright runs. Mistake captured in that spec's status block as a discipline note: don't promote a single log signal to "actual root cause" without checking whether the real production traffic shows the same symptom.
