# BUG-SESSION-STYLE-SWITCH-STALE-QF-STATE-01 — `lvSetSessionStyle` left QF/loop substate behind on lane transition

**Status:** **PARTIAL FIX LANDED 2026-05-06** (`ui/js/app.js` `lvSetSessionStyle` now clears QF + loop lane-ownership state on transition). Acceptance verification pending live re-test.
**Severity:** AMBER — narrator-visible behavioral inconsistency. Operator switching from `questionnaire_first` to `clear_direct` mid-session produced mixed Lori behavior: the deterministic era explainer fired for some turns, generic LLM improvisation for others.
**Surfaced by:** Chris's diagnosis 2026-05-06 12:30+ live session — operator started Mary in `questionnaire_first`, switched to `clear_direct`, observed inconsistent era handling and intermittent QF-shaped openers despite Phase 1 retirement landing earlier.
**Author:** Chris + Claude (2026-05-06)
**Lane:** Lane 2 / parent-session blockers — companion to WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01.

---

## Problem

`lvSetSessionStyle(value)` in `ui/js/app.js` updated `state.session.sessionStyle` and the localStorage mirror, but did NOT clear lane-specific substate from the previous style. Consequences when transitioning out of `questionnaire_first`:

- `state.session.questionnaireFirst.{active, segment, currentSection, currentField, askedKeys}` stayed populated.
- `state.session.loop.{activeIntent, currentSection, currentField, askedKeys, tellingStoryOnce, lastAction}` retained QF-walk values.

Anything reading these fields downstream (subsequent narrator turns, opener dispatch, runtime71 builders, the LLM's view of recent chat history that contained `[SYSTEM_QF: ...]` directives) saw stale ownership flags and could behave as if the prior lane were still active.

## Evidence

Live session 2026-05-06 12:30+ (Mary + Marvin, manual operator):

- **GOOD (clear_direct, deterministic path won):**
  Mary: *"What era are we in"*
  Lori: *"We're currently in the Building Years era, which refers to adulthood from your thirties through your fifties..."*
  → era infrastructure firing as designed.

- **BAD (questionnaire_first remnants, LLM improvisation):**
  Mary: *"what era are we talking about"*
  Lori: *"We're currently in the midst of figuring out which period of your life we'll be exploring together..."*
  → no deterministic era data; LLM invented context.

- **BAD (Marvin):**
  Marvin: *"yes i have choices earliest year etc.  Can you name them all"*
  Lori: *"Based on what you've shared, we've touched on your Early School Years, Adolescence, and Coming of Age..."*
  → didn't list all 7 eras; improvised based on chat history.

## Diagnosis

**Two opener/era paths fighting each other.** Deterministic infrastructure (era explainer block in `prompt_composer.py`, era_id_to_warm_label in `lv_eras.py`) ships system-prompt rules telling the LLM how to handle era questions. When LLM context is clean, the rules apply and the deterministic path wins. When LLM context contains stale QF directives + ownership signals, the LLM's improvisation drift wins.

**Operator session-style switch leaves stale state behind.** `lvSetSessionStyle` in `app.js:229-242` (pre-fix) did:

```js
function lvSetSessionStyle(value) {
  if (!LV_VALID_SESSION_STYLES.includes(value)) return;
  if (!state.session) state.session = {};
  state.session.sessionStyle = value;            // ← only this changed
  try { localStorage.setItem(LV_SESSION_STYLE_KEY, value); } catch (_) {}
  // radio sync …
}
```

No cleanup of `state.session.questionnaireFirst`, no reset of `state.session.loop` ownership flags. When the operator flipped Mary from QF to clear_direct, the dispatcher routed correctly through `case "clear_direct"` (Phase 1 retirement landed cleanly), but stale state lingered:

- `state.session.questionnaireFirst.active = true` (visible to ui-health-check)
- `state.session.loop.activeIntent` possibly still `"people_who_shaped_you"`
- `state.session.loop.currentField` possibly still pointing at a BB field
- Recent chat history full of `[SYSTEM_QF: ...]` directives the LLM continues to pattern-match

## Fix landed 2026-05-06

`ui/js/app.js` `lvSetSessionStyle` patched to clear stale lane state on transition:

```js
const _prevStyle = state.session.sessionStyle || null;
if (_prevStyle && _prevStyle !== value) {
  console.log("[session-style] transition", _prevStyle, "→", value, "— clearing stale lane state");
  if (state.session.questionnaireFirst) {
    delete state.session.questionnaireFirst;
  }
  if (state.session.loop) {
    state.session.loop.activeIntent = null;
    state.session.loop.currentSection = null;
    state.session.loop.currentField = null;
    state.session.loop.askedKeys = [];
    state.session.loop.tellingStoryOnce = false;
    state.session.loop.lastAction = "lane_transition_reset:" + _prevStyle + "_to_" + value;
  }
}
```

Behavior change: every operator-initiated session-style change clears QF substate completely and resets loop lane-ownership flags. Loop dispatcher re-initializes lazily on the next `lvSessionLoopOnTurn` call.

Console log marker `[session-style] transition X → Y — clearing stale lane state` is the verification signal.

## Acceptance gate

After fix:
- Operator switches `questionnaire_first` → `clear_direct` mid-session.
- DevTools console shows `[session-style] transition questionnaire_first → clear_direct — clearing stale lane state`.
- `state.session.questionnaireFirst` is `undefined` post-switch.
- `state.session.loop.activeIntent === null`.
- Subsequent narrator turns produce ONLY clear_direct-shaped behavior (no QF-shaped openers, no SYSTEM_QF preemption, no QF walk handoff).
- Era explainer ("what are the building years") fires consistently across 5+ subsequent narrator turns.
- "Can you name them all" produces a complete enumeration of the 7 eras, not a partial improvisation.
- Operator switches back QF mode (if needed for testing) — QF substate re-initializes from a clean slate.

## What this fix does NOT solve

**Stale chat-history contamination.** The LLM still sees prior `[SYSTEM_QF: ...]` directives in the chat-history context window. Even with state cleaned, the model may pattern-match to QF-shaped behavior because its recent context contains it. Two follow-up paths if behavior remains inconsistent:

1. **Filter SYSTEM_QF entries out of chat-history context** when current sessionStyle != questionnaire_first. Server-side prompt composition would strip them before sending to LLM.
2. **Hard-clear chat history on session-style change** — heavy-handed; loses narrative continuity. Not recommended.

If post-fix testing still shows improvisation drift, escalate to (1).

**Cross-session leakage.** `localStorage["lv_session_style"]` carries across page reloads. If the operator picks `questionnaire_first` in one session, refreshes, then unticks via `lvSetSessionStyle`, the cleanup runs. But if the operator picks QF then closes the browser, the substate is gone but localStorage retains the style. Subsequent narrator open will re-enter QF mode — that's expected, not a leak.

## Files modified

- `ui/js/app.js` — `lvSetSessionStyle` (10-line cleanup block added).

## Risks and rollback

**Risk 1: false-positive cleanup on programmatic re-set.** If some code calls `lvSetSessionStyle("questionnaire_first")` repeatedly with the same value, the `_prevStyle !== value` guard correctly skips cleanup. No regression.

**Risk 2: clearing loop substate mid-walk.** If operator changes session style WHILE Lori is mid-QF walk (asking birthOrder right now), the cleanup wipes `currentField`. The next `lvSessionLoopOnTurn` call re-initializes lazily AND consults `getSessionStyle()` which now returns the new style — so the dispatcher routes correctly. Not a regression.

**Rollback:** revert the cleanup block. Stale-state regressions return.

## Cross-references

- **WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01 Phase 1** — the dispatcher retirement that exposed this issue. Without QF firing on the live path, stale QF state had no obvious symptom. Once retirement landed, the LLM's chat-history view became the only path for QF behavior to leak through.
- **BUG-LORI-DUPLICATE-RESPONSE-01** — likely related. Stale conversational ownership in chat history may be one source of the duplicate-response pattern.
- **BUG-LORI-ERA-EXPLAINER-INCONSISTENT-01** — directly downstream. Era explainer was working SOMETIMES because deterministic infrastructure exists; failing OTHER times because stale state biased the LLM toward improvisation. This BUG fix should improve consistency without fully solving — the truly-deterministic `compose_era_explanation()` is still the proper Phase 2 fix for that BUG.
- **CLAUDE.md design principle 6** ("Lorevox is the memory system; Lori is the conversational interface to it") — stale state biasing LLM toward improvisation violates this. Lane-ownership flags are SYSTEM state; once cleared, the LLM should defer to the system's deterministic surfaces.

## Changelog

- 2026-05-06: Spec authored after Chris's diagnosis of mixed-behavior live session. Fix landed same day; pending live re-test verification.
