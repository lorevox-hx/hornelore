# WO-AUDIO-NARRATOR-ONLY-01 — Narrator Audio Capture (per-turn segments)

```
Title:    Capture narrator audio per turn, upload to memory archive
Owner:    Claude (live build with Chris in browser, NOT overnight blind)
Mode:     Surgical implementation — frontend only, hooks existing endpoints
Priority: Ship-critical for parents-by-next-week (audio is the proofing input)
Scope:    MediaRecorder → per-turn webm segments → upload to
          /api/memory-archive/audio (already verified at 34/34 PASS)
```

## Why this is the load-bearing piece for parents next week

Per Chris's framing: the parents' actual sessions become the data acquisition pipeline. Each session produces:
1. Two-sided text transcript (already shipped via WO-ARCHIVE-INTEGRATION-01)
2. **Narrator audio per turn** (this WO)
3. Pulled via existing `GET /api/memory-archive/people/{pid}/export` zip
4. Operator listens + reads, marks corrections, those become the next eval round

Without (2), unclear transcripts can't be disambiguated. Mom mumbles "1947 maybe?" — the text might land as "1947" but you need to hear it to confirm. With (2) shipped, every uncertain transcript line has its 2-second clip available.

## Locked product rules

```
1. Narrator audio captured per turn (one webm segment per narrator
   message).  Uploaded after STT/text confirmation.

2. Lori audio is NEVER captured.  Defense in depth:
   (a) MediaRecorder STOPS when isLoriSpeaking flips true (TTS gate).
   (b) /api/memory-archive/audio rejects role=lori|assistant with 400.
   (c) Wait 500–900ms after isLoriSpeaking flips false before re-arm
       (covers TTS audible-but-flag-cleared edge).

3. Audio file = audio/<turn_id>.webm.  turn_id ties to the same
   identifier the archive-writer used for the corresponding narrator
   turn (so transcript row's audio_ref points to the file).

4. Operator setting: a "Save my voice" toggle in the narrator-room
   topbar (or Operator tab session-style block).  Default ON for
   parents-by-next-week shipping (the value of the data is the whole
   point).  When OFF, narrator records nothing — transcript only.

5. Best-effort upload: failures log + leave audio_ref=null on the
   transcript row.  "Audio lost" is fine.  Audio is supplementary;
   transcript is the core record.

6. Chrome-only Phase 1.  Safari/iOS narrators: transcript-only.
   Document loud and early.
```

## What's already shipped that this WO leans on

- **`/api/memory-archive/audio` endpoint** verified at 34/34 PASS in WO-ARCHIVE-AUDIO-01
- **Quota gating**: 413 over cap, transcript still flows
- **Role-validation**: server rejects lori/assistant audio with 400
- **`/api/memory-archive/people/{pid}/export`** zip endpoint live and tested
- **`isLoriSpeaking`** flag exists in app.js (already used by mic auto-pause)
- **`state.session.handsFree` / `micAutoRearm` / `loriSpeaking`** scaffold landed in WO-NARRATOR-ROOM-01
- **`archive-writer.js`** lazy-creates archive sessions per conv_id; we'll piggy-back on its `_ensureSessionStarted` via the diagnostic accessor or duplicate inline (4 lines)

## Files to add

- `ui/js/narrator-audio-recorder.js` — MediaRecorder controller, ~250 lines
- `docs/reports/WO-AUDIO-NARRATOR-ONLY-01.md` — landing report

## Files to modify

- `ui/hornelore1.0.html` — add `<script src="js/narrator-audio-recorder.js">`, add "Save my voice" toggle to narrator-room topbar (next to existing controls), add `<script src=...>` after archive-writer
- `ui/js/app.js` — fire `lvNarratorAudioStart()` when mic activates, `lvNarratorAudioStop(turn_id)` when narrator turn is committed (right next to the existing `lvArchiveOnNarratorTurn(text)` hook in sendUserMessage)
- `ui/js/archive-writer.js` — return turn_id from `lvArchiveOnNarratorTurn` so the audio recorder can match its segment to the transcript row
- `ui/js/state.js` — `state.session.recordVoice: true` default
- `ui/js/ui-health-check.js` — add Audio category to harness (recorder loaded, mic permission state, TTS gate observable, last segment turn_id)

Do NOT touch:
- Backend (audio endpoint already exists and is verified)
- emotion.js / camera-preview.js (camera is independent)
- Any extraction code

## Implementation plan

### Step 1 — `ui/js/narrator-audio-recorder.js` skeleton

```js
window.lvNarratorAudioRecorder = (function () {
  let _stream = null;          // MediaStream (mic)
  let _recorder = null;        // MediaRecorder instance
  let _chunks = [];            // current segment's blob chunks
  let _currentTurnId = null;   // pending turn this segment belongs to
  let _state = "idle";         // idle | armed | recording | uploading | error
  let _ttsGateBlocked = false;
  const _stats = { segments_started: 0, segments_uploaded: 0, segments_lost: 0 };

  async function _acquireStream() { /* getUserMedia + cache */ }
  function _newRecorder() { /* webm/opus MediaRecorder, ondataavailable, onstop */ }
  async function _uploadSegment(blob, turn_id) { /* POST /api/memory-archive/audio */ }

  // Public API
  async function lvNarratorAudioStart()       { /* arm + start segment if not Lori-blocked */ }
  async function lvNarratorAudioStop(turn_id) { /* stop + upload */ }
  function     lvNarratorAudioGate(loriSpeaking) { /* TTS gate hook */ }
  function     lvNarratorAudioEnabled()       { /* state.session.recordVoice */ }

  // ...
  return { start: lvNarratorAudioStart, stop: lvNarratorAudioStop, gate: lvNarratorAudioGate, stats: () => Object.assign({}, _stats) };
})();
```

### Step 2 — TTS gate

When `isLoriSpeaking` flips true (existing flag in app.js), call `lvNarratorAudioRecorder.gate(true)`. Recorder transitions to "blocked" state and stops any in-progress segment without uploading.

When `isLoriSpeaking` flips false, start a 700ms `setTimeout` before clearing the gate. Captures the audible-but-flag-cleared edge.

### Step 3 — Per-turn segment lifecycle

```
narrator clicks Mic (or hands-free re-arm):
  → lvNarratorAudioRecorder.start()
  → MediaRecorder.start() with timeslice undefined (single chunk)

narrator clicks Send (sendUserMessage):
  → const turn_id = await lvArchiveOnNarratorTurn(text)   // returns turn_id
  → lvNarratorAudioRecorder.stop(turn_id)
  → MediaRecorder.stop() → ondataavailable → blob ready → upload
```

### Step 4 — Upload contract

```
POST /api/memory-archive/audio (multipart)
  person_id   = state.person_id
  conv_id     = state.chat.conv_id
  turn_id     = <from archive-writer>
  role        = "narrator"
  file        = <webm/opus blob>
```

On success: backend writes `audio/<turn_id>.webm`, transcript row gets audio_ref patched.
On failure: log, increment `_stats.segments_lost`, leave audio_ref=null on transcript.

### Step 5 — UI toggle

Narrator-room topbar gets a small toggle:
```
🎤 Save my voice  [ON|OFF]
```

OFF state stops mic capture. Transcript still flows. Operator can flip during a session.

Default ON for parents-by-next-week. Operator can flip via Settings popover too.

### Step 6 — Harness Audio category

```
- narrator-audio-recorder loaded (function present)
- MediaRecorder API available in this browser
- mic permission state (granted | denied | prompt | unknown)
- recorder.stats() — segments_started/uploaded/lost
- TTS gate observable (window._lv80AudioGated or similar)
- state.session.recordVoice value
- last uploaded turn_id (informational)
```

## Acceptance tests

**A. Recorder loads + permission flow.**
PASS if: page load → `lvNarratorAudioRecorder` exposed, `MediaRecorder` available, navigator.permissions reports microphone state.

**B. Per-turn segment uploads.**
PASS if: narrator opens a session, types one turn → corresponding `audio/<turn_id>.webm` exists in DATA_DIR archive AND transcript row's `audio_ref` is patched.

**C. Lori audio rejected at API layer (already passing in 34/34 smoke).**
PASS if: POST /api/memory-archive/audio with role=lori → 400.

**D. TTS gate stops in-progress segment.**
PASS if: narrator starts speaking, MediaRecorder is running → Lori starts TTS playback (`isLoriSpeaking=true`) → recorder stops, segment NOT uploaded (gate-blocked).

**E. 700ms post-TTS buffer.**
PASS if: TTS finishes (`isLoriSpeaking=false`) → recorder does NOT immediately re-arm; ~700ms later it does.

**F. "Save my voice" OFF respected.**
PASS if: operator toggles `recordVoice=false` → no audio uploads, transcript still flows.

**G. Quota gating (413 path).**
PASS if: artificially hit per-person cap → upload returns 413, recorder logs the limit, narrator continues without audio (no chat break).

**H. Operator export pulls full archive zip.**
PASS if: `GET /api/memory-archive/people/{pid}/export` zip contains `transcript.jsonl`, `transcript.txt`, `meta.json`, AND one `audio/<turn_id>.webm` per confirmed narrator turn.

**I. Chrome-only declaration.**
PASS if: Safari/iOS user opens app → `MediaRecorder` API check shows unavailable → harness reports DISABLED with copy "narrator audio capture requires Chrome/Edge."

## Live-build sequencing (for tomorrow morning with Chris in front of browser)

```
1. Land Step 1 (recorder skeleton) — 30 min
   verify: lvNarratorAudioRecorder exposed, MediaRecorder API available

2. Land Steps 2 + 3 (TTS gate + per-turn lifecycle) — 45 min
   verify: real Mic click → 1 narrator turn → audio file appears on disk

3. Land Steps 4 + 5 (upload contract polish + UI toggle) — 30 min
   verify: toggle OFF → no upload, ON → upload

4. Land Step 6 (harness Audio category) — 20 min
   verify: harness reports new Audio checks

5. Acceptance tests A-I — 30 min total
   final verification: pull export zip, listen to one segment, confirm
   transcript audio_ref points at correct file

Estimated total: 2.5–3 hours of live work.
```

## Out of scope

- Hands-free auto-rearm STT loop (WO-STT-HANDSFREE-01A)
- Fragile-fact confirmation cards (WO-STT-HANDSFREE-01A)
- Safari/iOS audio support (Phase 2 — needs different MIME)
- Real-time waveform display
- Per-segment upload progress indicator
- Audio editing / trim controls
- Background-noise filtering

## Sequencing

Lands AFTER tonight's 4 WOs (already in main: 01B, 01C, HC-02, ARCHIVE-INTEGRATION-01).
Lands BEFORE WO-STT-HANDSFREE-01A (auto-rearm needs reliable per-turn segments first).
This is the priority WO for tomorrow morning's first live session.
