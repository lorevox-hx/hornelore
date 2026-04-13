# WO-11E — Trainer TTS Narration + Spoken Guidance

**Project:** Hornelore 1.0  
**Status:** Complete  
**Date:** 2026-04-13

---

## Summary

Trainer mode now includes Lori voice narration. When a trainer step appears on screen, Lori automatically reads the step content aloud — the intro explanation, the question, brief introductions to both examples, and short spoken navigation guidance. Back, Next, Skip, Start Interview, and a new Replay button all stop any current narration cleanly before acting. The trainer feels like a guided spoken lesson rather than a static text card.

---

## Root Cause

- Trainer mode lacked narrated onboarding entirely. Steps were presented as visual cards only, with no voice guidance. For elderly narrators (Kent 86, Janice 86), this made the trainer feel like a wall of text rather than a gentle walkthrough.
- The existing TTS path (`enqueueTts` → `drainTts`) was safe to reuse for trainer narration because it only handles audio playback — it does not create chat bubbles, unlock the footer, or activate the mic. This preserved WO-11C modal isolation completely.
- No TTS stop/cancel mechanism existed prior to this work order. The TTS queue could only be drained, not interrupted. A new `stopAllTts()` function was added to support instant narration stop on step change or trainer exit.

---

## Files Read

| File | Purpose |
|------|---------|
| `ui/js/trainer-narrators.js` | Trainer step rendering, lifecycle, step content |
| `ui/js/app.js` | TTS pipeline (`enqueueTts`, `drainTts`), WO-11C guards, mic/recording, `lv80StartTrainerInterview` handoff |
| `ui/hornelore1.0.html` | Trainer panel CSS, trainer chooser HTML, WO-11C footer lock CSS, `_wo11cLockFooter`/`_wo11cUnlockFooter`, `_wo11RestoreNarratorAfterTrainer` |
| `ui/js/state.js` | Global `ttsQueue`, `ttsBusy`, `isRecording` state variables |

---

## Files Changed

| File | Changes |
|------|---------|
| `ui/js/app.js` | Added `stopAllTts()` function with abort flag and source cancellation; added `_ttsAbortRequested` and `_ttsCurrentSource` variables; modified `drainTts()` to check abort flag between chunks and store current WebAudio source; added `_wo11eTtsFinishedCallback` hook in `drainTts()` finally block; exposed `window._wo11eStopTts` |
| `ui/js/trainer-narrators.js` | Added narration orchestration: `_wo11eBuildNarrationText()`, `_wo11eNarrateStep()`, `_wo11eStopNarration()`, `_wo11eShowSpeakingIndicator()`, `_wo11eShowTtsFallback()`; added `replay()` function; modified `start()`, `next()`, `prev()`, `skip()`, `finish()`, `_reset()` to integrate narration stop/start; added speaking indicator and replay button to `_renderPanel()` HTML; added narration state fields to `_ensureTrainerState()` |
| `ui/hornelore1.0.html` | Added CSS for `.lv80-trainer-speaking` indicator (pulsing dot + label), `.lv80-trainer-speaking-dot` with `wo11eSpeakingPulse` keyframe animation, `.lv80-trainer-replay-btn` styling |

---

## What Changed

### A. TTS Stop Mechanism (`app.js`)

**New function: `stopAllTts()`**
- Clears the `ttsQueue` array immediately (`.length = 0`)
- Sets `_ttsAbortRequested = true` — checked at top of `drainTts` while loop to break between chunks
- Stops the current `_ttsCurrentSource` (WebAudio `BufferSource.stop()`) for mid-chunk abort
- Pauses `_ttsAudio` (HTMLAudioElement fallback) if active
- Exposed on `window._wo11eStopTts` for cross-file access from trainer-narrators.js

**Modified: `drainTts()`**
- Added abort check at top of while loop: `if (_ttsAbortRequested) break;`
- Stores current WebAudio `BufferSource` in `_ttsCurrentSource` for external abort
- In finally block: resets `_ttsAbortRequested = false` and `_ttsCurrentSource = null`
- In finally block: calls `window._wo11eTtsFinishedCallback()` if set, then nulls it

### B. Narration Orchestration (`trainer-narrators.js`)

**New function: `_wo11eBuildNarrationText(step, stepIndex, totalSteps)`**
Composes full narration text from step data:
1. All `lori[]` lines (intro/explanation)
2. The `question` line (transition to examples)
3. Brief example introductions: "A [label] might sound like this: [text]. Or, [label]: [text]."
4. Spoken navigation guidance varying by position:
   - First step: "Tap Next to continue. Or tap Skip..."
   - Middle steps: "Tap Next to continue. Tap Back if you want to hear that again. Or Skip..."
   - Last step: "Tap Start Interview when you're ready. Or tap Back..."

**New function: `_wo11eNarrateStep()`**
- Gets current step from state, calls `_wo11eBuildNarrationText()`
- Sets `_wo11eNarrating = true`, shows speaking indicator
- Sets `window._wo11eTtsFinishedCallback` to clear narrating state and hide indicator on completion
- Calls `enqueueTts(narrationText)` — audio only, no chat bubbles
- Handles TTS unavailability gracefully with fallback message

**New function: `_wo11eStopNarration()`**
- Clears `_wo11eNarrating` state and `_wo11eTtsFinishedCallback`
- Calls `window._wo11eStopTts()` to immediately halt audio
- Hides speaking indicator

**New function: `replay()`**
- Stops current narration, then restarts narration for current step after 150ms delay
- Exposed on `window.LorevoxTrainerNarrators.replay`

**Modified lifecycle functions:**
- `start()` — calls `_wo11eNarrateStep()` after 200ms delay (lets panel render first)
- `next()` — calls `_wo11eStopNarration()` before step change, then `_wo11eNarrateStep()` on new step
- `prev()` — calls `_wo11eStopNarration()` before step change, then `_wo11eNarrateStep()` on previous step
- `skip()` — calls `_wo11eStopNarration()` before `finish()`
- `finish()` — calls `_wo11eStopNarration()` before exit handoff
- `_reset()` — calls `_wo11eStopNarration()` and clears narration state

### C. UI Additions (`hornelore1.0.html` + `_renderPanel()`)

**Speaking indicator**: Purple-tinted bar with pulsing dot: "Lori is reading this step..."
- Shows when narration starts, hides when narration finishes or is stopped
- Uses `wo11eSpeakingPulse` keyframe animation (opacity pulse)
- Positioned at top of trainer shell panel

**Replay button**: Added to trainer action bar (right-aligned)
- Compact secondary style button with play triangle: "▶ Replay"
- Visible on all steps alongside Back/Next/Skip

**TTS fallback message**: When TTS is unavailable, the speaking indicator shows "Voice guidance unavailable — you can follow the steps on screen." and auto-hides after 6 seconds.

### D. Narration State

Added to `state.trainerNarrators`:
- `_wo11eNarrating` (boolean): true while trainer TTS is in progress
- `_wo11eStopped` (boolean): true when narration was intentionally stopped by user action

---

## What Was Preserved

- **WO-11C modal isolation**: Trainer narration calls only `enqueueTts()` (audio path) — never `appendBubble()`, `_wo11cUnlockFooter()`, `startRecording()`, or `sendUserMessage()`. Zero isolation breach vectors. Footer remains locked. Send and mic guards remain active.
- **WO-11C pending-unlock handoff**: `finish()` → `lv80StartTrainerInterview()` → `_wo11RestoreNarratorAfterTrainer()` → `_wo11cPendingUnlock` flow is untouched. Narration stop happens before the handoff chain begins.
- **Normal TTS pipeline**: `drainTts()` changes are additive (abort check, source tracking, callback hook). The default path when `_ttsAbortRequested` is false and `_wo11eTtsFinishedCallback` is null behaves identically to pre-WO-11E. Normal Lori interview TTS is unaffected.
- **Narrator turn claim system**: `_wo10hTransitionToArmed()` still fires in `drainTts` finally block. During trainer mode, the WO-11C mic guard prevents any recording from starting even if the turn system fires.
- **Mic visual states**: `drainTts()` still sets "wait" during playback and clears on finish. During trainer mode, the footer is locked with low opacity so mic state is not visible to the user.
- **All trainer step content**: No changes to `_SHARED_LORI_INTRO`, `_steps()`, or `_STYLE_DISPLAY`. All WO-11D content preserved exactly.

---

## Tests Run

### Test A — Auto narration on trainer open
- Started Questionnaire First trainer
- Confirmed `enqueueTts` called with 1044-char narration text
- Text begins with "Hi… I'm Lori. Lorevox is a place to save and organize your life story..."
- Contains "Tap Next to continue" guidance
- No `appendBubble` calls — no chat bubbles
- Trainer state remains `active: true`
- **PASS**

### Test B — Back and Next narration
- Started Clear & Direct, advanced to step 2 via `next()`
- Confirmed `_wo11eStopNarration()` called before step change
- Step 2 narration (566 chars) is different from step 1 narration
- Contains both "Tap Next" and "Tap Back" guidance (middle step)
- Clicked `prev()` — confirmed stop then re-narrate from beginning
- **PASS**

### Test C — Spoken guidance
- Verified first step: "Tap Next to continue. Or tap Skip..."
- Verified middle step: "Tap Next to continue. Tap Back if you want to hear that again. Or Skip..."
- Verified last step: "Tap Start Interview when you're ready. Or tap Back..."
- Guidance matches visible controls for each step position
- **PASS**

### Test D — Skip behavior
- `skip()` calls `_wo11eStopNarration()` → `window._wo11eStopTts()` → clears queue + stops audio
- Then calls `finish()` which also calls `_wo11eStopNarration()` (defensive double-stop)
- Verified narration stops, `_wo11eNarrating` cleared to false
- **PASS**

### Test E — Start Interview behavior
- Advanced to last step, clicked Next (→ `finish()`)
- `finish()` calls `_wo11eStopNarration()` before handoff chain
- Verified `_wo11eTtsFinishedCallback` nulled, `ttsQueue` cleared
- Handoff to `lv80StartTrainerInterview(capturedMeta)` proceeds normally
- **PASS**

### Test F — Modal isolation preserved
- Confirmed zero calls to: `appendBubble`, `_wo11cUnlockFooter`, `startRecording`, `toggleRecording`, `sendUserMessage` in trainer-narrators.js
- `enqueueTts` only produces audio — no side effects on chat, footer, or mic
- WO-11C guard functions (`_wo11cIsTrainerActive`) unchanged and still block all input
- **PASS**

### Test G — TTS failure fallback
- When `enqueueTts` is undefined: `_wo11eShowTtsFallback()` fires, showing "Voice guidance unavailable — you can follow the steps on screen." with 6-second auto-hide
- When `enqueueTts` throws: caught by try/catch, same fallback fires
- Trainer panel renders normally, all navigation buttons work, state is clean
- **PASS**

### Test H — Replay behavior
- `replay()` calls `_wo11eStopNarration()` then `_wo11eNarrateStep()` after 150ms
- Verified current step is re-narrated from beginning
- Replay is exposed on `window.LorevoxTrainerNarrators.replay`
- Button renders in all steps via `_renderPanel()` HTML
- **PASS**

---

## Results

- **Lori now reads trainer steps aloud**: Each step auto-narrates with intro lines, question, example introductions, and navigation guidance. Narration lengths range from 566 to 1138 characters depending on style and step.
- **Back/Next/Skip/Start Interview feel guided**: Every navigation action stops current narration cleanly before proceeding. New steps auto-narrate. The experience flows like a spoken lesson.
- **Trainer mode stayed modal**: Zero isolation breaches. No chat bubbles, no footer unlock, no mic activation. All WO-11C guards preserved.
- **TTS fallback works**: When TTS is unavailable, a subtle message appears and auto-hides. Trainer continues as a visual step-through.
- **Replay works**: Users can re-hear any step by tapping the Replay button.

---

## Debug Findings

All 8 required debug points produce [WO-11E] tagged console output:

1. `[WO-11E] Trainer step rendered — index: N id: STEP_ID`
2. `[WO-11E] Trainer narration requested — step: N id: STEP_ID textLen: N`
3. `[WO-11E] Trainer narration started — step: N`
4. `[WO-11E] Trainer narration stopped on Back` / `on Next`
5. `[WO-11E] Trainer narration stopped on Skip`
6. `[WO-11E] Trainer narration stopped on finish/Start Interview`
7. `[WO-11E] TTS unavailable — trainer continues visually` / `enqueueTts not found`
8. `[WO-11E] Replay clicked — restarting narration for step: N`

Additionally: `[WO-11E] stopAllTts()` and `[WO-11E] TTS abort — breaking drain loop` for the stop mechanism.

---

## Bugs Found

None. The existing TTS pipeline was well-structured for reuse. The `enqueueTts` → `drainTts` path cleanly separates audio from chat bubble creation, which made trainer narration a clean addition rather than a risky integration.

---

## Follow-up Work Recommended

1. **Live browser testing**: Unit tests confirm logic and text composition. Live testing on :8082 should verify actual audio playback, timing of the 200ms narration delay, and speaking indicator visibility during TTS playback.
2. **Narration pacing**: The first step for Questionnaire First is ~1044 characters. With Coqui VITS at normal speed, this may take 60-90 seconds. If too long for elderly users, consider splitting into shorter narration segments or reading only the lori[] lines and guidance (skipping example read-aloud on steps 2-3).
3. **Volume/speed controls**: Could add simple controls for narration speed or volume if users find the default pace uncomfortable.
4. **FaceMesh WASM repair**: Still deferred from earlier — SIMD/non-SIMD mismatch, separate WO.
