# WO-STT-HANDSFREE-01A — Hands-Free Speech Loop (minimum-viable)

```
Title:    Auto-rearm browser STT after Lori finishes speaking
Owner:    Claude (live build with Chris — NOT overnight blind)
Mode:     Surgical, additive on top of existing recognition + TTS infra
Priority: Polish — DEFERRED past parents-by-next-week first session
          (parents can type; STT is convenience, not data acquisition)
Scope:    Frontend only — chain into existing recognition + isLoriSpeaking +
          state.session.handsFree scaffold from WO-NARRATOR-ROOM-01
```

## Why this is deferred past the audio WO

Per Chris's reframing: parents using by next week → audio + transcript capture is the data pipeline. STT auto-rearm is convenience. If the narrator types or single-shot-clicks the mic, the data still flows. Auto-rearm reduces friction for the narrator but doesn't change what gets archived.

**Don't ship overnight, don't ship before the first parent session.** Ship after parents have used the app once or twice and Chris sees where the friction actually lives.

## Locked product rules

```
1. Mic NEVER listens while Lori is speaking (isLoriSpeaking=true).

2. After Lori finishes:
   - Wait 500–900ms (TTS-tail safety buffer)
   - Re-arm mic IF state.session.micAutoRearm === true
   - Else: stay armed-paused, narrator must click to speak

3. No auto-send.  Even when STT produces a final transcript, the
   narrator must click Send (or hit Enter) to commit.  Fragile-fact
   detection (already in WO-STT-LIVE-02) handles confirmation.

4. Browser STT first.  Local Whisper is WO-STT-LOCAL-01 (later).

5. Long pauses honor WO-10C ladder:
     0–120s   no interruption
     120s     gentle visual cue
     300s     soft re-entry prompt
     600s     pause hands-free + offer break

6. "Take a break" overlay (already shipped in WO-NARRATOR-ROOM-01)
   stops auto-rearm.  Resume restores it.
```

## What's already shipped that this WO leans on

- Browser SpeechRecognition wired in app.js
- `isLoriSpeaking` flag + TTS state machine
- `state.session.handsFree / micAutoRearm / loriSpeaking` scaffold (WO-NARRATOR-ROOM-01)
- WO-10C cognitive support timing constants
- Take-a-break overlay (WO-NARRATOR-ROOM-01)
- Transcript guard fragile-fact classifier (WO-STT-LIVE-02)
- Mic UI 4-state visual: LISTENING / OFF / WAIT amber / BLOCKED (WO-MIC-UI-02A)

## Files

Add:
- `ui/js/stt-handsfree.js` — auto-rearm controller (~150 lines)
- `docs/reports/WO-STT-HANDSFREE-01A.md` — landing report

Modify:
- `ui/js/app.js` — fire stt-handsfree hooks at TTS-start / TTS-end + at sendUserMessage
- `ui/hornelore1.0.html` — add hands-free toggle to narrator-room topbar (or settings)
- `ui/js/state.js` — `state.session.handsFree` default false (operator opts in per session)
- `ui/js/ui-health-check.js` — Mic/STT category extension (auto-rearm wired, TTS gate observable, idle pauses)

## Implementation plan (live-build outline)

### Step 1 — `stt-handsfree.js` skeleton

```
window.lvSttHandsfree = (function () {
  let _state = "idle";   // idle | armed | listening | tts_blocked | paused | break
  let _idleTimer = null; // long-pause ladder
  function lvSttArm()       { /* state.session.handsFree on + start recognition */ }
  function lvSttDisarm()    { /* state.session.handsFree off + stop recognition */ }
  function _onTtsStart()    { /* recognition.stop(); _state = "tts_blocked" */ }
  function _onTtsEnd()      { /* setTimeout(700, _maybeRearm) */ }
  function _maybeRearm()    { /* if !break && !disarmed, recognition.start() */ }
  function _idleTick()      { /* 120s/300s/600s soft cues */ }
  // ...
})();
```

### Step 2 — TTS hooks in app.js

Existing `enqueueTts(text)` in onAssistantReply. Find the corresponding "TTS playback ended" event (probably in the TTS module) and call `lvSttHandsfree.onTtsEnd()`. For TTS start, call `lvSttHandsfree.onTtsStart()` from the same enqueue site.

### Step 3 — Long-pause ladder

Use WO-10C constants. Visible cue at 120s ("Take your time. I'm listening."). Soft re-entry at 300s. At 600s, pause auto-rearm and surface the take-a-break overlay (existing WO-NARRATOR-ROOM-01 surface).

### Step 4 — Toggle UI

Single toggle: "Hands-free [ON|OFF]". Lives in the narrator-room topbar next to the mic button OR in the Settings popover. Default OFF — opt-in per session.

### Step 5 — Harness extension

Mic/STT category extends with:
- `lvSttHandsfree loaded`
- `state.session.handsFree` is bool
- TTS-end → re-arm hook installed (verified by checking `_onTtsEnd` is callable)
- Idle ladder timing constants present (120/300/600)

## Acceptance tests

**A. Auto-rearm after TTS.** Narrator armed hands-free → Lori speaks → TTS ends → 700ms later mic re-arms automatically. Narrator can speak without clicking.

**B. Mic blocked during TTS.** While `isLoriSpeaking=true`, recognition NOT running. Narrator can't accidentally talk over Lori into the transcript.

**C. No auto-send.** STT produces final text → text appears in input box → user must click Send. (Backstop against fragile-fact corruption.)

**D. Long-pause ladder.** No narrator activity for 120s → visual cue. 300s → re-entry prompt. 600s → break offer.

**E. Take-a-break overlay overrides auto-rearm.** Narrator clicks Take a Break → auto-rearm stops. Resume → auto-rearm restores.

**F. Toggle OFF disables.** `handsFree=false` → behavior identical to today (no auto-rearm).

**G. Browser STT fallback graceful.** SpeechRecognition unavailable → harness reports DISABLED, narrator falls back to typed input + per-turn manual mic press.

## Out of scope

- Local Whisper STT (WO-STT-LOCAL-01)
- "I heard you say…" review card (already exists in transcript-guard.js for fragile facts)
- Voice activity detection / silence cutoff
- Whisper streaming
- Custom wake-word

## Sequencing

Lands AFTER WO-AUDIO-NARRATOR-ONLY-01 (audio capture is the data; STT is the input modality).
Land AFTER first parent session (use the real-world data to know whether auto-rearm is even friction-worth-fixing).
Could be parked indefinitely if parents are happy typing or single-shot mic.
