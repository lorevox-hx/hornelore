# WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01 — Phase 1 implementation plan

**Status:** READY TO LAND. Tree-clean precondition satisfied 2026-05-05 evening.
**Scope:** Phase 1 only (audit + suppress on live narrator path). Phases 2–4 parked.
**Authored:** 2026-05-05 night-shift code review.
**Reviewer:** Chris.

---

## What Phase 1 is

Retire the questionnaire-first lane's SYSTEM_QF auto-prompt emission and its welcome-back suppression on the **live narrator path**. Keep all data, all schema, all operator UI, all identity onboarding. Keep the QF code in-tree and reactivable for Phase 4's optional structured-intake-mode via a single feature flag.

Phase 1 acceptance gate from the WO spec:

- No SYSTEM_QF auto-prompt fires during a live narrator session across 30 minutes of provoked-question testing.
- Existing welcome-back composer (`interview.py:486-489`) fires correctly on switch-back.
- Cold-start `first_time` greeting still fires for fresh narrators.
- Identity onboarding state machine (askName/askDob/askPob) still works for incomplete narrators.

## Site map (ranked by criticality)

### Critical (load-bearing for Phase 1)

| Site | File | Line | Role |
|---|---|---|---|
| **Dispatcher case for QF** | `ui/js/session-loop.js` | 117–118 | Routes `questionnaire_first` → `_routeQuestionnaireFirst()` which is the sole SYSTEM_QF emitter. **THE choke point.** |
| **Dispatcher case for clear_direct** | `ui/js/session-loop.js` | 119, 495–497 | `clear_direct` calls `_routeQuestionnaireFirst(event)` — inherits the same SYSTEM_QF walk. Phase 1 retires this too per principle 8 ("Live Lori sessions must not auto-advance questionnaire fields" — applies to ALL styles). |
| **`_ssIsQF` welcome-back gate** | `ui/hornelore1.0.html` | 5179–5183 | The smoking gun. Suppresses welcome-back/opener when sessionStyle is QF so the QF lane can own first-prompt dispatch. Phase 1 inverts this. |

### Transitively retired (no edit needed; sit inside `_routeQuestionnaireFirst`)

| Site | File | Line | Role |
|---|---|---|---|
| BUG-227 IDENTITY RESCUE directive | `ui/js/session-loop.js` | 328–340 | Fires inside `_routeQuestionnaireFirst()` only. Dead code path once dispatcher case is no-op. |
| Personal-walk handoff prompt | `ui/js/session-loop.js` | 422–434 | Fires inside `_routeQuestionnaireFirst()` only. Dead code path. |
| Next-field SYSTEM_QF prompt | `ui/js/session-loop.js` | 480–487 (call) + 1047–1068 (`_buildFieldPrompt`) | Fires inside `_routeQuestionnaireFirst()` only. Dead code path. |

### Preserved (do NOT touch)

| Site | File | Line | Why kept |
|---|---|---|---|
| Identity onboarding 3-step machine | `ui/js/app.js` | `startIdentityOnboarding`, `handleIdentityPhaseAnswer` | The askName/askDob/askPob conversation is NOT SYSTEM_QF. It's the existing identity intake that Corky-bypasses for incomplete narrators. **Preserved**. |
| QF entry for incomplete narrators | `ui/js/session-style-router.js` | 92–143 (`_enterQuestionnaireFirst`) | Routes incomplete narrators to identity onboarding. Stays alive. The post-identity hand-off to `lvSessionLoopOnTurn` becomes a no-op via the dispatcher edit. |
| Backend SYSTEM_QF receive comment | `server/code/api/routers/chat_ws.py` | 223 | Comment only, documents UI emission. No edit. |
| Comm-control wrapper QF priority | `server/code/api/services/lori_communication_control.py` | 75 | `questionnaire_first: 70` priority is for routing config, not emission. SYSTEM_QF user-role messages stop arriving from the live path. No edit. |
| Picker UI radio button | `ui/hornelore1.0.html` | 3014 | Operator can still pick "Questionnaire First" — stays as a session-style label. No emission consequence after Phase 1. |
| `prompt_composer.py:1828` comment | `server/code/api/prompt_composer.py` | 1828 | Reference only. No edit. |

### Harness sites (need test-side updates AFTER Phase 1 lands)

| Site | File | Line | Action |
|---|---|---|---|
| `test-bb-walk.js` forces QF style | `ui/js/test-bb-walk.js` | 417–419 | Test relies on QF lane firing. **Set `localStorage["lv_qf_live_ownership"] = "1"` before forcing the style** so the legacy walk reactivates for the test. |
| `ui-health-check.js` QF expectations | `ui/js/ui-health-check.js` | 1098–1112, 1238 | Two existing checks (`questionnaire_first incomplete-gate bypass wired`, `WO-13 welcome-back suppressed for questionnaire_first`) need new states reflecting Phase 1. Add status branch for "QF-RETIRE Phase 1 active — welcome-back fires regardless of style." |
| `parent_session_rehearsal_harness.py` | `scripts/ui/run_parent_session_rehearsal_harness.py` | (TBD — grep) | Verify no harness fixtures depend on SYSTEM_QF firing in the live path. |
| `parent_session_readiness_harness.py` | `scripts/ui/run_parent_session_readiness_harness.py` | (TBD — grep) | Same verification. |

## Feature flag convention

`localStorage["lv_qf_live_ownership"] === "1"` — operator-toggleable, persists across page reload, reads `null` for default-OFF behavior. Follows the same pattern as `lvClockVariant` (UI feature flag) and `lv_session_style` (operator-set persistence). NOT a server env var; this is purely a UI lane flag.

Read in JS as:

```js
const _qfLegacyLiveOwnership = (function () {
  try {
    return (typeof localStorage !== "undefined") &&
           localStorage.getItem("lv_qf_live_ownership") === "1";
  } catch (_) { return false; }
})();
```

Default: `false`. Setting to `"1"` reactivates the legacy QF lane for Phase 4's structured-intake-mode (manual operator gesture, parked).

## Edit 1 — `ui/js/session-loop.js`

Replace the dispatcher switch at lines 117–129 with a flag-gated retirement:

```js
// BEFORE (current code, L117-129):
switch (style) {
  case "questionnaire_first": return _routeQuestionnaireFirst(event);
  case "clear_direct":        return _routeClearDirect(event);
  case "companion":           return _routeCompanion(event);
  case "warm_storytelling":
  default:                    return _routeWarmStorytelling(event);
}

// AFTER (Phase 1):
// WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01 Phase 1 (2026-05-XX):
// QF and clear_direct walks are retired from the live narrator path
// per CLAUDE.md design principle 8 ("Live Lori sessions must not
// auto-advance questionnaire fields"). The walks remain in-tree and
// reactivate via localStorage["lv_qf_live_ownership"]="1" for the
// optional structured-intake-mode scoped in Phase 4 of this WO.
const _qfLegacyLiveOwnership = (function () {
  try {
    return (typeof localStorage !== "undefined") &&
           localStorage.getItem("lv_qf_live_ownership") === "1";
  } catch (_) { return false; }
})();

switch (style) {
  case "questionnaire_first":
    if (_qfLegacyLiveOwnership) return _routeQuestionnaireFirst(event);
    state.session.loop.lastAction = "qf_retired:routed_to_warm_storytelling";
    console.log("[QF-RETIRE] questionnaire_first → warm_storytelling (live path); " +
      "set localStorage.lv_qf_live_ownership=1 for legacy walk");
    return _routeWarmStorytelling(event);
  case "clear_direct":
    if (_qfLegacyLiveOwnership) return _routeClearDirect(event);
    state.session.loop.lastAction = "qf_retired:clear_direct_directive_only";
    console.log("[QF-RETIRE] clear_direct → directive-only (live path); " +
      "tier-2 directive still applies via runtime71");
    return _routeWarmStorytelling(event);
  case "companion":           return _routeCompanion(event);
  case "warm_storytelling":
  default:                    return _routeWarmStorytelling(event);
}
```

Net change: ~20 lines added (mostly comments + flag read). Zero deletions. Behavior change: questionnaire_first + clear_direct stop calling `_routeQuestionnaireFirst()` on the live path, which kills SYSTEM_QF emission, BUG-227 IDENTITY RESCUE directive, handoff prompt, and next-field prompt — all transitively.

## Edit 2 — `ui/hornelore1.0.html` lines 5179–5183

Invert the `_ssIsQF` welcome-back gate so it only suppresses when the legacy flag is on:

```html
<!-- BEFORE (current code, L5178-5184): -->
const _wo13PriorUserTurns = Number((state.session && state.session.priorUserTurns) || 0);
const _ssIsQF = (state.session && state.session.sessionStyle) === "questionnaire_first";
if (_ssIsQF) {
  console.log("[WO-13] questionnaire_first override — skipping welcome-back/opener so session-loop owns first prompt");
  try { window._lv80WelcomeBackSuppressedForQF = true; } catch (_) {}
} else if (_wo13PriorUserTurns > 0) {

<!-- AFTER (Phase 1): -->
const _wo13PriorUserTurns = Number((state.session && state.session.priorUserTurns) || 0);
const _ssIsQF = (state.session && state.session.sessionStyle) === "questionnaire_first";
// WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01 Phase 1: welcome-back/opener is
// the live narrator path's first prompt. Legacy QF override only fires
// when localStorage.lv_qf_live_ownership=1 (Phase 4 structured-intake-mode).
let _qfLegacyLiveOwnership = false;
try {
  _qfLegacyLiveOwnership = (typeof localStorage !== "undefined") &&
                           localStorage.getItem("lv_qf_live_ownership") === "1";
} catch (_) {}
if (_ssIsQF && _qfLegacyLiveOwnership) {
  console.log("[QF-RETIRE] LV_QF_LIVE_OWNERSHIP=1 — legacy QF override active, skipping welcome-back/opener");
  try { window._lv80WelcomeBackSuppressedForQF = true; } catch (_) {}
} else if (_wo13PriorUserTurns > 0) {
```

Net change: ~10 lines added. Zero deletions. Behavior change: welcome-back / opener now fires regardless of session style on the live narrator path.

## Edit 3 (optional, recommended) — `.env.example` documentation block

Add a short comment block documenting the new flag so operators discover it:

```
# WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01 — UI-only flag (NOT server env)
# Read by ui/js/session-loop.js + ui/hornelore1.0.html via:
#   localStorage["lv_qf_live_ownership"] === "1"
# Default OFF: questionnaire-first / clear_direct do not drive live Lori
# interview (no SYSTEM_QF auto-prompts; welcome-back/opener owns first
# prompt regardless of session style).
# Set to "1" in browser DevTools to reactivate the legacy QF walk for
# the optional structured-intake-mode (Phase 4 of the WO; manually-
# started, deliberately-entered).
# Operator setting:
#   localStorage.setItem("lv_qf_live_ownership", "1")  // reactivate
#   localStorage.removeItem("lv_qf_live_ownership")    // retire (default)
```

This block is documentation-only; it lives in `.env.example` next to the existing `LV_*` UI flag comments.

## Smoke test plan

After landing the two edits, restart the stack and run these checks in a real browser. Each takes <2 minutes.

**Test A — Returning narrator switch-back produces welcome-back, NOT cold-start.**

1. Open Mary's narrator card (she has prior turns).
2. Confirm operator session style is "Questionnaire First" (the style that previously caused cold-start).
3. Switch to Marvin.
4. Switch BACK to Mary.
5. **Expect:** Mary's first Lori bubble is `"Welcome back, Mary. Where would you like to continue today?"` (the existing `interview.py:486-489` template).
6. **Failure mode (regression):** Mary gets `"Hi mary, I'm Lori. I'm here to help you capture your life story..."` cold-start text. → revert.

**Test B — User question wins over previously-racing SYSTEM_QF.**

1. With Mary loaded (identity complete, prior turns), in operator session style "Questionnaire First."
2. Type `what do you know about me`.
3. **Expect:** Lori's response is the memory_echo readback (identity + sources + "(not on record yet)" gracefully).
4. **Expect (negative):** No SYSTEM_QF birth-order question arrives. No "Were you the oldest, the youngest..." text.
5. **Failure mode:** Lori responds with the birth-order question instead of the memory_echo. → check that the dispatcher edit landed; check console for `[QF-RETIRE] questionnaire_first → warm_storytelling` log marker.

**Test C — Era-explainer ("what are the building years") works.**

1. Same Mary session, after Test B.
2. Type `what are the building years`.
3. **Expect:** Lori explains the era warmly (per the ERA EXPLAINER block in `prompt_composer.py`).
4. **Failure mode:** Lori asks a structured-field question. → same diagnosis as Test B.

**Test D — Cold-start narrator still gets the cold-start template.**

1. Create a fresh test narrator (no identity, no turns).
2. **Expect:** Lori opens with `"Hi <name>, I'm Lori. I'm here to help you capture your life story..."` (the existing `first_time` template).
3. **Failure mode:** No greeting fires, or welcome-back fires for a fresh narrator. → check `_wo13PriorUserTurns === 0` branch reaches the opener fetch.

**Test E — Incomplete narrator + Questionnaire First still routes to identity intake.**

1. Create a test narrator with NO date-of-birth captured.
2. Confirm session style is "Questionnaire First."
3. Open the narrator.
4. **Expect:** Lori starts the askName / askDob / askPob 3-step identity intake (this is `startIdentityOnboarding`, NOT SYSTEM_QF).
5. After identity completes, **expect:** Lori transitions to a normal warm-storytelling first turn — NOT into the QF section walk asking birth order / time of birth / preferred name.
6. **Failure mode A:** identity intake doesn't start. → `_enterQuestionnaireFirst` Corky bypass broke; revert and investigate.
7. **Failure mode B:** after identity completes, Lori asks "Were you the oldest, the youngest..." → the dispatcher edit didn't land or the flag is set; check `localStorage.getItem("lv_qf_live_ownership")` returns null in console.

**Test F — Legacy structured-intake-mode reactivates with the flag.**

1. In any narrator session, run in DevTools console: `localStorage.setItem("lv_qf_live_ownership", "1")`.
2. Refresh the page; reopen the narrator.
3. With operator style "Questionnaire First": **expect** the SYSTEM_QF walk reactivates (legacy behavior — birth order, time of birth, preferred name asked one at a time).
4. Run: `localStorage.removeItem("lv_qf_live_ownership")`. Refresh. **Expect** Phase 1 retired-behavior returns.
5. **Failure mode:** flag has no effect. → check `_qfLegacyLiveOwnership` reads correctly in both edited files.

If A through F all pass: Phase 1 lands. Commit, push, then re-run TEST-23 v8 against the same narrators with this stack.

## Auto-resolution check (after Phase 1 lands)

These BUGs / WOs are predicted to auto-resolve via Phase 1. After landing, verify each against the same Mary + Marvin transcripts:

- **BUG-LORI-SYSTEM-QF-PREEMPTION-01** — preemption race is structurally impossible. Close.
- **BUG-LORI-SWITCH-FRESH-GREETING-01 Phase 1** — basic continuation greeting now fires via `interview.py:486-489`. Close Phase 1; Phase 2 (active-listening continuation paraphrase) remains independent.
- **BUG-LORI-MIDSTREAM-CORRECTION-01** — likely partial improvement. Re-test corrections in a fresh Mary session; if still failing, the remaining work is the original three-hypothesis diagnostic.
- **BUG-LORI-ERA-EXPLAINER-INCONSISTENT-01** (pending filing) — likely partial improvement. Verify Mary's "what are the building years" returns era-explainer consistently.

## Risks and rollback

**Risk 1: clear_direct narrators expected the structured walk.** clear_direct currently calls `_routeQuestionnaireFirst` (session-loop.js:496). Phase 1 retires it. If any operator was relying on clear_direct's walk-plus-tighter-prompts behavior, they'll see only the tier-2 directive in runtime71 (no walk). Mitigation: tier-2 directive is the substantive part of clear_direct's tone preset; the walk was bonus structure that violates principle 8. If we want the walk, it's reactivated with the flag.

**Risk 2: harness regressions.** test-bb-walk.js + ui-health-check.js have QF-firing assertions. They need the flag set, OR the assertions need to flip. Plan: harness updates land in the same PR as Phase 1 to keep the gate green.

**Risk 3: feature flag rot.** A `localStorage` flag that's never set never gets exercised. Phase 4 (structured-intake-mode) is the long-term path; until then, the flag-on path will only be exercised by Test F. Acceptable for a defense-in-depth reactivation knob.

**Rollback:** revert both edits. `_ssIsQF` gate restored, dispatcher routes back to QF walk. SYSTEM_QF emission resumes, welcome-back stays suppressed. No data harm.

## Files modified

- `ui/js/session-loop.js` — dispatcher switch updated (~20 lines net)
- `ui/hornelore1.0.html` — `_ssIsQF` gate inverted (~10 lines net)
- `.env.example` — documentation-only flag block (~12 lines)
- (later, not Phase 1) `ui/js/test-bb-walk.js` + `ui/js/ui-health-check.js` — harness updates

## Out-of-scope for Phase 1

- Phase 2 of the WO: operator-data-entry verification (manual smoke test only — verify operator-entered BB fields appear in next memory_echo readback).
- Phase 3 of the WO: natural-speech quiet capture verification (manual smoke test only — narrator volunteers a fact, verify provisional truth captures it without SYSTEM_QF follow-up).
- Phase 4 of the WO: optional structured-intake-mode design (parked).
- BUG-LORI-SWITCH-FRESH-GREETING-01 Phase 2 (active-listening continuation paraphrase composer) — independent scope, dependent on Phase 1c data feed.
- Backend code changes — none required for Phase 1.

## Total effort estimate

- Code edits: 30 lines net across 2 files.
- Smoke tests: 6 tests, ~10 minutes wall clock total.
- Harness updates (test-bb-walk + ui-health-check): ~30 minutes.
- Verify auto-resolutions (4 BUGs): ~20 minutes.

**One focused 90-minute session lands Phase 1 cleanly.**
