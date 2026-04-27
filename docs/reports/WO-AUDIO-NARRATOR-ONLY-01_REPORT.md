# WO-AUDIO-NARRATOR-ONLY-01 — Implementation Report

**Built:** 2026-04-25 afternoon
**Status:** **CODE LANDED — awaits live verify with Chris in browser** per spec ("live build with Chris in browser, NOT overnight blind").
**Gate:** This is **Gate 3** of the parent-session readiness checklist (`docs/PARENT-SESSION-READINESS-CHECKLIST.md`). Once verified, Gate 3 moves from RED → GREEN-needs-verify.

## What's built

A complete per-turn audio capture pipeline. Every narrator turn that started with mic-arm now produces a `webm/opus` segment uploaded to `audio/<turn_id>.webm` in the per-narrator memory archive. Lori's TTS audio is NEVER captured — three independent defenses guarantee it.

### Files

| File | Role |
|---|---|
| `ui/js/narrator-audio-recorder.js` (NEW, ~280 LOC) | MediaRecorder controller + state machine + upload contract |
| `ui/js/app.js` | Three hook sites: `startRecording` arms audio, `drainTts` open/close gates `isLoriSpeaking` transitions, `sendUserMessage` stops + uploads with a generated `turn_id`. New `lvNarratorSetRecordVoice()` for the toggle |
| `ui/js/state.js` | `state.session.recordVoice` (default `true`) |
| `ui/hornelore1.0.html` | `<script src="js/narrator-audio-recorder.js">` + Save my voice checkbox in narrator-room topbar |
| `ui/js/ui-health-check.js` | Five new harness checks under `mic` category |

### Public API (`window.lvNarratorAudioRecorder`)

- `start()` — arm + begin a new segment (idempotent if already mid-segment)
- `stop(turn_id)` — finalize segment, upload to `/api/memory-archive/audio` under that turn_id
- `gate(loriSpeaking)` — TTS gate hook; `true` drops in-progress segment without upload, `false` waits 700ms before clearing
- `stats()` — `{ segments_started, segments_uploaded, segments_lost, last_turn_id, state, ttsGateBlocked, last_error }`
- `isAvailable()` — MediaRecorder + getUserMedia present
- `isEnabled()` — recordVoice toggle on AND available
- `cleanup()` — drop in-progress, release mic stream

## Locked product rules (per spec)

1. **Narrator audio captured per turn** — mic-arm starts a segment, send-message finalizes and uploads under a fresh client-side `turn_id`.
2. **Lori audio is NEVER captured.** Three guards:
   - (a) **Client-side TTS gate** — when `isLoriSpeaking` flips true (`drainTts` start), `gate(true)` drops the in-progress segment WITHOUT upload (drop counted as `segments_lost`).
   - (b) **Backend rejection** — `/api/memory-archive/audio` already rejects `role=lori|assistant` with 400 (verified at 34/34 PASS in WO-ARCHIVE-AUDIO-01 smoke).
   - (c) **700ms post-TTS buffer** — when `isLoriSpeaking` flips false, `gate(false)` waits 700ms before clearing the gate. Covers the audible-but-flag-cleared edge.
3. **Audio file = `audio/<turn_id>.webm`** in the per-narrator archive. Filename also stamps `turn_id.slice(0,24).webm` for the multipart upload.
4. **Operator setting** — `state.session.recordVoice` default `true`. Toggle in narrator-room topbar ("Save my voice"). When `false`, recorder is a no-op (`start()` returns early; transcript still flows).
5. **Best-effort upload** — failures log but don't block the chat. `segments_lost++`, transcript is the core record.
6. **Chrome-only Phase 1** — Safari/iOS lacks `MediaRecorder` for audio/webm; harness reports DISABLED with detail.

## How it ties into existing systems

- **Doesn't fight BUG-209** — the audio recorder generates its OWN client-side `turn_id` (UUID), uploads under it, and doesn't depend on the disabled archive-writer auto-chain. Backend writes the transcript via chat_ws path (single source); audio uploads under its own turn_id. Operator correlates by timestamp at review time. The `audio_ref` linkage on transcript rows is best-effort — if the `turn_id` happens to match a chat_ws row it links automatically; otherwise the audio file just lives in `audio/` next to the transcript and operator correlates manually.
- **Honors BUG-218 capabilities honesty** — once this WO ships and `recordVoice=true`, the existing capabilities-honesty rule could be updated to "audio is being captured." For now, the rule still says "text only" since the operator hasn't yet verified end-to-end. **Chris should NOT update the BUG-218 directive until the live verify passes** — better to keep Lori truthful in one direction (under-claiming) than risk a regression to over-claiming.
- **Hooks into existing `isLoriSpeaking` flag** at `app.js:4293` (set true) and `app.js:4406` (set false) — defense-in-depth piggy-backs on the TTS state machine.

## Live verification protocol (Chris does this in browser)

After hard refresh (Ctrl+Shift+R) on the laptop:

### Test A — Recorder loads
- Console should show: `[Hornelore] narrator-audio-recorder loaded (available=true)`.
- In Bug Panel → Run Full UI Check → mic category should now show 5 new WO-AUDIO-NARRATOR-ONLY-01 rows. Recorder loaded check should be PASS, recordVoice should be PASS, segment activity should be INFO ("no segments yet"), TTS gate should be PASS, narrator-room checkbox PASS (if narrator-room is loaded).

### Test B — Per-turn segment uploads
1. Pick a test narrator (e.g., Corky). Enter narrator session.
2. Confirm **Save my voice** checkbox in topbar is checked.
3. Click mic, speak a sentence ("Hi Lori, this is a test"), click Send.
4. Console should show:
   - `[narrator-audio] segment START (mime=audio/webm;codecs=opus)`
   - `[narrator-audio] segment STOP (tid=...)`
   - `[narrator-audio] uploaded tid=... size=...KB → 200`
5. Bug Panel → Run Full UI Check → segment activity row should now show `started=1 uploaded=1 lost=0`.
6. Click Export Current Session in Bug Panel. Open the zip. Look in `sessions/<conv_id>/audio/`. **There should be one `<turn_id>.webm` file.** Open it in any audio player — should play your sentence.

### Test C — Lori audio rejected (TTS gate)
1. While Lori is speaking, look at recorder state via console: `lvNarratorAudioRecorder.stats()`.
2. `state` should be `tts_blocked` and `ttsGateBlocked` should be `true`.
3. After Lori finishes speaking, wait ~1 second.
4. State should return to `idle` (after 700ms buffer).
5. There should be NO `audio/lori_*.webm` or anything tagged as `role: lori` in the export zip — backend rejects with 400 if anything tries.

### Test D — TTS-mid-record drops segment
1. Click mic. Start speaking, but Lori interrupts with TTS.
2. Console should show: `[narrator-audio] TTS gate ACTIVE — in-progress segment dropped (Lori-audio defense)`.
3. `lvNarratorAudioRecorder.stats().segments_lost` should increment.
4. Export zip — that turn should NOT have an audio file.

### Test E — "Save my voice" OFF disables capture
1. Uncheck **Save my voice** in narrator-room topbar.
2. Click mic, speak, send.
3. Console should NOT show `[narrator-audio] segment START`.
4. Export zip — no audio file for that turn (transcript still present).
5. Re-check Save my voice.
6. Speak again — audio capture resumes.

### Test F — Quota gating (413 path)
- This is hard to test without artificially hitting the per-person cap. Defer unless it actually triggers in real use.

### Test G — Browser fallback
- On Chrome (your laptop): `lvNarratorAudioRecorder.isAvailable()` returns `true`.
- Hypothetical Safari/iOS narrator: would return `false`, harness reports DISABLED. Phase 1 ships Chrome-only per spec.

### Test H — Operator export verification (Gate 4 of readiness)
1. After 3+ narrator turns with audio, click **Export Current Session**.
2. Open the zip. Verify it contains:
   - `transcript.txt` and `transcript.jsonl` per session (BUG-209 fix means these are clean, no duplicates)
   - `audio/<turn_id>.webm` for each narrator turn that recorded
   - `meta.json` with the session_id
3. Open one `.webm` file externally — should be only your voice, audible, complete.
4. Verify NO Lori-voice audio anywhere in the zip.

## Out of scope (per spec)

- Hands-free auto-rearm STT loop (WO-STT-HANDSFREE-01A — deferred)
- Fragile-fact confirmation cards (already in WO-STT-LIVE-02)
- Safari/iOS audio support (Phase 2 — needs different MIME)
- Real-time waveform display
- Per-segment upload progress indicator
- Audio editing / trim controls
- Background-noise filtering
- Real `audio_ref` linkage to transcript rows (would require backend WS to use the same turn_id we generate — separate WO; for now operator correlates by timestamp)

## Sequencing

- Lands AFTER WO-ARCHIVE-AUDIO-01 (backend, 34/34 PASS) ✓
- Lands AFTER BUG-208/209/210/211/212/218 (today's batch, all live-verified or in_progress) ✓
- Lands BEFORE WO-STT-HANDSFREE-01A (auto-rearm needs reliable per-turn segments first)
- Lands BEFORE first parent session — **this is the priority WO** for Gate 3 of readiness

## Once Test B passes, BUG-218 directive can be updated

When Chris confirms audio capture is working end-to-end (a `.webm` plays back cleanly with only narrator voice), I can update the `_CAPABILITIES_HONESTY` constant in `session-loop.js` to reflect that audio IS being captured when `recordVoice=true`. Until then, Lori stays in "text only" mode.

Concrete update planned:
```js
const _CAPABILITIES_HONESTY = (
  "CAPABILITIES (must be honest, never overstate): " +
  "Right now this session captures the typed text + speech-to-text " +
  "transcript of our conversation, AND when 'Save my voice' is on, " +
  "your audio recordings per turn (your voice only, never Lori's). " +
  "If the narrator asks whether their voice is being recorded, answer " +
  "honestly based on the toggle state. Video is NOT captured. " +
  "If unsure, default to 'I'm not sure — let me check the toggle.' " +
  "Never claim more than what's actually saved."
);
```

That's a 5-minute follow-up after live verify.

## Status log

- 2026-04-25 morning: BUG-218 honesty rule landed (Lori always says "text only" until this WO ships).
- 2026-04-25 afternoon: WO-AUDIO-NARRATOR-ONLY-01 code landed. **Awaits live browser verify.**
- After live verify passes: BUG-218 directive update + Gate 3 → GREEN-verified.
