# BUG-LORI-MIC-MODAL-NO-LIVE-TRANSCRIPT-01 — Live Mic Transcript Modal

**Status:** SPEC — design + implementation parked, UI surface needs operator review before code lands
**Filed:** 2026-05-07 from Chris's parent-session-readiness flag during Melanie Carter Smoke 11
**Severity:** HIGH — parent-session blocker for any narrator who speaks more than one sentence

## Problem

When narrator clicks the mic to dictate, the existing flow:
- Mic activates
- Web Speech API streams interim transcripts into the hidden chatInput value
- Narrator speaks for some duration
- When narrator stops, final transcript fires `sendUserMessage()`
- Transcript appears in the chat as a bubble

The narrator never SEES what they're saying until after they're done. For a 90-second story, that's 90 seconds of speaking blind. Older narrators (Janice, Kent) and ELL speakers (Melanie Zollner) need to see accumulated text in real time so they can:
- Catch STT errors mid-utterance ("Hannah" should have been "hold my hand" — narrator could have corrected immediately if they'd seen it)
- Course-correct their own narrative ("I just said Tuesday but I meant Thursday")
- See visual confirmation that the system is hearing them
- Decide consciously when to stop (vs accidentally pausing too long and triggering an unintended send)

## Existing surface (focus-canvas.js)

A FocusCanvas modal already exists at `ui/js/focus-canvas.js` with:
- `_setMode("listening")` — full-screen modal with mic active
- `_handleRecognitionResult()` — receives Web Speech API results
- `_interimText` / `fcInterim` — element where in-progress STT shows
- `_doneCards` — list of confirmed segments

**It's mostly built.** What's missing is:
1. Triggering the modal automatically on mic activation (instead of requiring an explicit "focus mode" entry)
2. Visual polish: vertical expansion as content accumulates
3. Clear Send / Cancel actions
4. Per-segment confidence visualization (low-confidence words highlighted so narrator notices STT errors)

## Design

### Trigger
- Mic button click → modal opens AND starts STT
- Esc OR explicit "Cancel" button → modal closes, STT stops, no send
- Explicit "Send" button OR speech-end + N seconds silence → modal closes, transcript sends as user turn

### Layout
```
┌──────────────────────────────────────────────┐
│  Listening, Melanie…                         │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │ Lake Superior froze hard that winter.  │  │
│  │ My grandmother's kitchen smelled like  │  │
│  │ cinnamon rolls.                         │  │
│  │ ▏     <-- live cursor + interim text   │  │
│  └────────────────────────────────────────┘  │
│                                              │
│              [ Cancel ]  [ Send ]            │
└──────────────────────────────────────────────┘
```

The text area should:
- Start ~3 lines tall
- Expand vertically as content grows (max viewport-height-minus-buttons)
- Show finalized words in normal color, interim in muted gray
- Wrap naturally; no horizontal scroll
- Auto-scroll to bottom on each new word

### STT confidence overlay
Web Speech API provides per-segment confidence in `event.results[i][0].confidence`. Words below a threshold (e.g., 0.6) get a subtle yellow underline so the narrator can see "the system isn't sure about this one — should I repeat it?"

### Audio capture wiring
- The narrator-audio-recorder.js already captures webm per turn with a turn_id
- The modal should use the same turn_id and pass it on Send so the transcript turn's `audio_id` field gets populated (BUG-ARCHIVE-AUDIO-NOT-LINKED-TO-TRANSCRIPT-01 backend wiring landed 2026-05-07; this is the FE half)

### Send payload
On Send button OR speech-end-timeout:
- Final transcript text → `chatInput.value`
- `state.lastTranscript` populated with full transcript guard data (already exists via WO-STT-LIVE-02)
- WebSocket `start_turn` payload includes `audio_id: turn_id`
- chat_ws.py will read `audio_id` and pass to `archive.append_event` (already wired)

## Acceptance gates

1. Chris talks for 60 seconds; sees text accumulate in real time; can read the running transcript
2. STT mishearing ("Hannah" for "hold my hand") is visible BEFORE Send fires; narrator can:
   - Cancel and re-record, OR
   - Hit Send with the wrong text but see the error themselves and correct in next turn
3. Esc closes modal cleanly; mic stops; no send
4. Send button enabled only when transcript has ≥3 content words (avoids accidental empty sends)
5. Audio webm uploads tied to the same turn_id so `audio_id` field on the transcript turn matches the file
6. Modal accessible: keyboard-focusable Cancel/Send, ESC works, large-font friendly
7. Modal does NOT preempt safety paths — if STT detects safety keywords mid-stream, fragile-fact guard still fires per WO-STT-LIVE-02

## Implementation phases

**Phase A** — Wire mic button to open existing FocusCanvas in listening mode (currently requires manual entry). 2-3 hours.

**Phase B** — Layout polish: vertical expansion, interim/final styling, auto-scroll to bottom. 2-3 hours.

**Phase C** — Send/Cancel buttons + speech-end timeout (5s default, configurable). 1-2 hours.

**Phase D** — Confidence overlay highlighting low-confidence words. 2-3 hours; needs design eyeball.

**Phase E** — Audio_id pass-through: thread turn_id from narrator-audio-recorder.js through to ws start_turn payload. 1-2 hours.

Total: ~10-13 hours focused work. Spec authored from Chris's flag during Melanie Zollner live test 2026-05-07 — prioritize before any Janice/Kent session.

## Risks

- Speech-end timeout: too short and narrator gets cut off mid-thought; too long and narrator can't tell when to stop. Default 5s feels right; expose as `LV_SPEECH_END_TIMEOUT_MS` env for operator override.
- Modal interrupts visual focus: ensure FocusCanvas backdrop dims existing chat without blocking it entirely (narrator can still see what Lori last said as anchor context).
- Mobile / small-viewport: modal should be full-height on phones; not yet relevant for desktop-first deploys but worth keeping in CSS.
