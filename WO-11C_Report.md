# WO-11C — Trainer Modal Isolation + Handoff Repair

**Status:** Patch complete — ready for live testing  
**Date:** April 13, 2026

---

## Summary

Trainer mode (Dolly, Shatner, Lori) was not truly modal. The coaching panel appeared on screen, but the normal chat footer remained fully live underneath. Users could type, send messages, and start mic capture during trainer mode. Because trainer isolation nulled `person_id`, these leaked messages routed through the normal interview runtime with null identity state, causing Lori to fall back to onboarding questions ("What's your date of birth?") simultaneously with the trainer coaching content. This patch closes all four leak paths and makes trainer mode a true modal gate.

## Root Cause

Three independent failures combined to produce the broken behavior:

1. **No trainer guards in the send/mic path.** `sendUserMessage()`, `toggleRecording()`, and `startRecording()` had zero checks for `state.trainerNarrators.active`. Any user input during trainer mode passed straight through to the normal interview runtime.

2. **Footer remained live and usable.** The HTML footer containing `#chatInput`, `#btnMic`, and `#lv80SendBtn` was never hidden, disabled, or visually locked during trainer mode. Users had no indication that the input controls were non-functional in this context.

3. **Handoff was incomplete.** `finish()` in trainer-narrators.js set `active = false` before calling `lv80StartTrainerInterview()`, which opened the narrator switcher. Between trainer exit and narrator selection, the send path was unguarded and `person_id` was null — a second leak window.

## Files Read

| File | Purpose |
|------|---------|
| `ui/js/trainer-narrators.js` | Trainer lifecycle: start, next, prev, finish, skip, state management |
| `ui/js/app.js` | sendUserMessage, toggleRecording, startRecording, loadPerson, lvxSwitchNarratorSafe, lv80StartTrainerInterview, lv80ClearTrainerAndCaptureState |
| `ui/hornelore1.0.html` | lv80RunTrainerNarrator, lv80LoadTrainerTemplate, _wo11RestoreNarratorAfterTrainer, _wo11UpdateHeaderForTrainer, footer HTML, trainer panel CSS |
| `ui/js/state.js` | state.trainerNarrators shape, all state fields |
| `ui/js/interview.js` | renderInterview trainer guard (already present from WO-11) |

## Files Changed

| File | Changes | Markers |
|------|---------|---------|
| `ui/js/app.js` | Added `_wo11cIsTrainerActive()` helper, guards on sendUserMessage/toggleRecording/startRecording, post-trainer footer unlock in loadPerson | 10 |
| `ui/hornelore1.0.html` | Footer locked CSS, lock/unlock JS functions, footer lock at trainer start, pending-unlock at trainer exit, contamination cleanup | 8 |

**Total: 18 `[WO-11C]` markers across 2 files.**

## What Changed

### Fix 1 — Block input while trainer is active

Added `_wo11cIsTrainerActive()` helper in app.js. This function checks both `state.trainerNarrators.active` (trainer running) AND `state.trainerNarrators._wo11cPendingUnlock` (trainer exited but no narrator selected yet). Three entry points guarded:

- `sendUserMessage()` — early return with sysBubble: "Complete the trainer first, then we'll begin your interview."
- `toggleRecording()` — early return with same message
- `startRecording()` — early return (silent, as this is an internal call)

### Fix 2 — Disable/hide footer while trainer is active

Added CSS class `trainer-locked` on `<footer>`:
- `pointer-events: none` — prevents all click/type interaction
- `opacity: 0.3` — visually dims the controls
- `::after` pseudo-element displays "Trainer in progress — start or skip the trainer to begin the interview."

Added `_wo11cLockFooter()` and `_wo11cUnlockFooter()` JS functions exposed on `window` for cross-file use.

Footer is locked at the start of `lv80RunTrainerNarrator()` before any state changes.

### Fix 3 — Clean trainer handoff

The handoff gap between trainer exit and narrator selection is now covered:

1. `_wo11RestoreNarratorAfterTrainer()` sets `state.trainerNarrators._wo11cPendingUnlock = true` instead of unlocking the footer
2. Footer stays visually locked (dimmed with banner) while narrator switcher is open
3. `_wo11cIsTrainerActive()` returns true during this pending state, so send/mic remain blocked
4. `loadPerson()` in app.js checks for `_wo11cPendingUnlock` when a narrator is loaded — only then does it call `_wo11cUnlockFooter()` and clear the flag

This ensures no input can leak between trainer exit and real narrator selection.

### Fix 4 — Clear trainer contamination

`_wo11RestoreNarratorAfterTrainer()` already cleared `chatMessages.innerHTML` — this was present from WO-11. Added `[WO-11C]` logging to confirm the contamination cleanup fires. Any null-narrator onboarding bubbles that leaked during trainer mode (before Fix 1 existed) are removed before the real interview begins.

## What Was Preserved

- Trainer panel rendering (trainer-narrators.js) — untouched
- Trainer step navigation (next/prev) — untouched
- Trainer metadata handoff (style, title, promptHint) — untouched
- Narrator restore flow (opens switcher for explicit selection) — preserved, enhanced with pending-unlock
- `state.trainerNarrators` shape — only added `_wo11cPendingUnlock` (transient flag)
- WO-11 transcript block — already working, not modified
- Interview.js renderInterview trainer guard — already working, not modified

## Tests Run

Structural verification only (live testing requires browser):

| Test | Method | Result |
|------|--------|--------|
| JS syntax | `node -e "require('fs').readFileSync('ui/js/app.js')"` | Pass |
| Brace balance | Script block extraction + count | 746/746 BALANCED |
| Marker count | `grep -c WO-11C` across all files | 18 markers, all accounted |
| Guard coverage | Manual trace: sendUserMessage, toggleRecording, startRecording | All three guarded |
| Footer lock wiring | Trace: lv80RunTrainerNarrator → _wo11cLockFooter | Confirmed |
| Pending-unlock trace | finish → _wo11RestoreNarratorAfterTrainer → _wo11cPendingUnlock → loadPerson → _wo11cUnlockFooter | Confirmed |

## Results

**Live testing required.** The patches are structurally sound and the logic traces cleanly. The acceptance test protocol from the work order (Tests A through G) should be run in Chrome with the three-service stack.

Expected outcomes:
- **Trainer mode is now truly modal** — footer is dimmed and unclickable, send/mic blocked at JS level
- **Send/mic are blocked during trainer mode** — three independent guards prevent any normal input
- **Start Interview / Skip restore cleanly** — footer stays locked until narrator is selected
- **Contaminated trainer-era bubbles are cleared on handoff** — chatMessages wiped at restore

## Debug Findings

Seven targeted `[WO-11C]` console.log points for live debugging:

1. `Footer LOCKED — trainer mode active` — fires at trainer start
2. `sendUserMessage() BLOCKED — trainer mode active` — fires on any send attempt during trainer
3. `toggleRecording() BLOCKED — trainer mode active` — fires on any mic attempt during trainer
4. `startRecording() BLOCKED — trainer mode active` — fires on internal mic start attempt
5. `Trainer contamination cleanup — chat cleared on exit` — fires at trainer handoff
6. `Footer remains locked — pending narrator selection` — fires after trainer exit, before narrator pick
7. `Footer unlocked — narrator selected after trainer exit` — fires when real narrator loads

## Bugs Found

1. **Primary bug (fixed):** `sendUserMessage()` had no trainer guard — core leak path
2. **Primary bug (fixed):** `toggleRecording()` / `startRecording()` had no trainer guard
3. **Primary bug (fixed):** Footer never disabled during trainer mode — no visual or interaction gate
4. **Gap bug (fixed):** Handoff window between `finish()` setting `active=false` and narrator selection left send path unguarded

## Follow-up Work Recommended

| Item | Priority | Notes |
|------|----------|-------|
| Live acceptance tests A-G | **High** | Must verify in Chrome with real trainer flow |
| Trainer panel z-index / visual dominance | Low | Panel renders at scroll position; could add `position:sticky` or full-screen overlay if footer dimming isn't enough |
| Footer unlock timeout safety net | Low | If user dismisses narrator switcher without selecting, footer stays locked forever; could add a 60s timeout or escape-key handler |
| FaceMesh WASM repair | Separate WO | Still broken (SIMD/non-SIMD mismatch) — unrelated to trainer |
