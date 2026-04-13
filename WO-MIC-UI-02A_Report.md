# WO-MIC-UI-02A — Single Surface Voice Capture + Mic Truthfulness + Pause Tolerance

**Status:** Complete  
**Date:** April 13, 2026  
**Scope:** Narrowed from WO-MIC-UI-02 (full Focus Canvas retirement + transcript cleanup + camera-pause hooks)

---

## Problem Statement

Live testing revealed three overlapping voice capture issues that confused elderly narrators Kent (86) and Janice (86):

1. **Split capture surface:** Speech appeared in a lower overlay (Focus Canvas) or in a secondary transcript area (#wo8LiveTranscript) instead of the main chat input — narrators saw "nothing here when I speak but underneath it is there to send."
2. **Mic label lies:** The mic button only showed two states (LISTENING / MIC OFF) with no indication when Lori was speaking (mic silently stopped) or when permission was denied.
3. **Premature no-speech nudge:** Web Speech API fires no-speech events every ~5 seconds during silence. At threshold 10 (~50 seconds), the gentle nudge interrupted Kent's natural thinking pauses (30-90 seconds).

## Implemented Changes

### 1. Focus Canvas Bypass — Permanent for Hornelore

**File:** `ui/js/focus-canvas.js`  
**Lines:** 549-566 (replaced)

The Focus Canvas `_installHooks()` function previously hijacked `btnMic.onclick` and `chatInput.focus`, routing all input through a full-screen overlay. The prior WO-MIC-FIX added a conditional bypass with age-detection fallback logic. This patch simplifies to an unconditional bypass: Focus Canvas intercepts are permanently disabled unless explicitly re-enabled via `window._wo_focusCanvasBypass = false` before script load.

The `_initScrollManagement()` call is preserved (runs before the bypass return) so smooth-scroll behavior in the main chat is not affected.

### 2. Single Surface Authority — #wo8LiveTranscript and #wo8VoiceStatus Neutralized

**File:** `ui/js/app.js`  
**Functions:** `_wo8HandleRecognitionResult()`

WO-8's enhanced voice handler wrote final transcript text to both `#chatInput` (main surface) and `#wo8LiveTranscript` (competing visible surface), and wrote interim text to `#wo8VoiceStatus`. Both secondary elements are now hidden via `wo8-hidden` class (added as `display: none !important`). The data still writes for diagnostics/debug, but narrators see only `#chatInput`.

**File:** `ui/hornelore1.0.html`  
Both `#wo8VoiceStatus` and `#wo8LiveTranscript` now carry `wo8-hidden` class in their default markup, plus a new `.wo8-hidden` CSS rule ensures they stay invisible.

### 3. Expanded Mic Visual States

**File:** `ui/js/app.js`  
**Function:** `_setMicVisual()` (rewritten)

Previously two states: `true` (LISTENING, red pulse) and `false` (MIC OFF, grey). Now four:

| State | Label | Visual | Trigger |
|-------|-------|--------|---------|
| `true` / `"listening"` | LISTENING | Red pulse, glow | `startRecording()` |
| `false` / `"off"` | MIC OFF | Grey, no glow | `stopRecording()` |
| `"wait"` | WAIT — LORI IS SPEAKING | Amber pulse | `drainTts()` sets `isLoriSpeaking=true` |
| `"blocked"` | MIC BLOCKED | Dark red, no pulse, dimmed | `recognition.onerror` with `not-allowed` |

**Wiring:**
- `drainTts()` now calls `_setMicVisual("wait")` immediately after setting `isLoriSpeaking=true` and stopping recording. The narrator sees amber WAIT instead of confusing MIC OFF.
- The `finally{}` block of `drainTts()` calls `_setMicVisual(false)` to clear WAIT when Lori finishes. If WO-10H auto-starts recording, `startRecording()` immediately overrides to LISTENING.
- The `recognition.onerror` handler for `not-allowed` now calls `_setMicVisual("blocked")` for a persistent visual indicator.

**File:** `ui/hornelore1.0.html`  
New CSS rules for `.mic-wait`, `.mic-label-wait` (amber), `.mic-blocked`, `.mic-label-blocked` (dark red, dimmed).

### 4. No-Speech Pause Tolerance

**File:** `ui/js/app.js`  
**Variable:** `_NO_SPEECH_GENTLE_THRESHOLD`

Raised from 10 to 20. At ~5 seconds per event, the gentle nudge now fires at approximately 100 seconds of silence instead of 50. This accommodates Kent and Janice's natural thinking pauses without premature interruption.

The nudge message was softened from "Still listening — take your time, speak whenever you're ready" to "The microphone is still on — no rush, speak whenever you're ready."

### 5. Targeted Debug Logging

Six new `console.log` points tagged `[WO-MIC-UI-02A]`:

1. `toggleRecording()` — entry point with `isRecording`, `isLoriSpeaking`, FocusCanvas state
2. `recognition.onresult` — confirms final text reaches `#chatInput` (first 60 chars)
3. `sendUserMessage()` — confirms send source and content length
4. `_setMicVisual("wait")` — logs WAIT state transition
5. `_setMicVisual("blocked")` — logs BLOCKED state transition
6. Focus Canvas bypass — logs `[WO-MIC-UI-02A] Focus Canvas intercepts BYPASSED`

## Deferred Items (Out of Scope for 02A)

| Item | Reason Deferred | Recommended WO |
|------|----------------|----------------|
| Transcript cleanup (punctuation, capitalization) | Requires display/canonical text split — no such architecture exists yet | WO-MIC-UI-03 |
| Large listening-surface CSS redesign | Layout project, not a quick patch | WO-UI-LAYOUT |
| Camera-assisted pause hooks | FaceMesh vendor WASM is broken (SIMD/non-SIMD mismatch) — hooks would be dead code | WO-FACEMESH first |
| Focus Canvas full retirement (remove code) | Code is bypassed but preserved for potential non-Hornelore use | Low priority cleanup |

## Files Changed

| File | Changes |
|------|---------|
| `ui/js/focus-canvas.js` | Simplified bypass to unconditional (2 markers) |
| `ui/js/app.js` | Neutralized competing surfaces, expanded _setMicVisual(), raised no-speech threshold, added debug logging (16 markers) |
| `ui/hornelore1.0.html` | Added .wo8-hidden CSS, mic-wait/mic-blocked CSS, hidden default classes on WO-8 elements (4 markers) |

## Acceptance Test Protocol

| Test | What to Check | Expected |
|------|---------------|----------|
| A — Main surface authority | Click mic, speak, watch where text appears | Text appears in #chatInput only, no lower/overlay surface |
| B — No Focus Canvas popup | Click mic button | No overlay/scrim appears, mic starts directly |
| E — Pause behavior | Start mic, stay silent for 2 minutes | No nudge until ~100s, message is calm |
| F — Lori speaking lockout | Trigger Lori TTS while mic is on | Button shows WAIT — LORI IS SPEAKING (amber), recognition results discarded |
| G — Permission denied | Block mic in Chrome settings, click mic | Button shows MIC BLOCKED (dark red), sysBubble with instructions |
| H — Janice simplicity | Full cycle: mic on → speak → send | One surface, clear labels, no confusion |
