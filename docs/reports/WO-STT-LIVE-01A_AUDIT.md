# WO-STT-LIVE-01A — Live STT Reality Audit (No Behavior Change)

**Author:** Claude
**Date:** 2026-04-20
**Status:** DONE (audit only; no runtime behavior changed)
**Supersedes premise of:** WO-STT-LIVE-01 (old split-authority framing was wrong)
**Next:** Step 2 (STT-agnostic fragile-fact guard) → Step 3 (backend migration behind flag)

---

## 1. Current-state verdict

**Current live STT authority = browser (Chrome Web Speech API, sending audio to Google servers).**

There is no split authority, no mixed authority, and no hidden parallel system. There is one live mic path, and it is browser-only. The backend STT route exists and is configured but has **zero frontend callers today**.

---

## 2. Evidence map

Every claim here is cited to a file + line region in the tree at HEAD on 2026-04-20.

### 2.1. Browser STT source

- `ui/js/app.js:3788–3895` — `_ensureRecognition()` / `startRecording()` / `stopRecording()`.
- `ui/js/app.js:3790` — engine: `const SR = window.SpeechRecognition || window.webkitSpeechRecognition;`
- `ui/js/app.js:3792` — `recognition = new SR(); recognition.continuous = true; recognition.interimResults = true;`
- `ui/js/app.js:3856` — error handler for `e.error === "network"` says verbatim: *"🎤 Speech recognition requires an internet connection (Chrome sends audio to Google's servers). Please check your connection."* This is the code admitting the privacy/data-egress model.

### 2.2. Focus-canvas relationship

- `ui/js/focus-canvas.js:293–309` — `_hookRecognition()` polls for `window.recognition` and wraps its `onresult` + `onend`. It does **not** create a separate `SpeechRecognition` instance.
- `ui/js/focus-canvas.js:269–291` — `_startListening()` / `_stopListening()` call `toggleRecording()` / `stopRecording()` from app.js.

**Conclusion:** focus-canvas is an `onresult` interceptor on top of the single app.js recognition instance. Not a second STT authority.

### 2.3. Backend endpoint existence

- `server/code/api/routers/stt.py:106–154` — `@router.post("/transcribe")` endpoint. Accepts multipart `file`, form `lang`, form `initial_prompt`. Batch path (multipart file upload, VAD-filtered segments). No streaming.
- `server/code/api/routers/stt.py:91–103` — `@router.get("/status")` endpoint.
- `server/code/api/routers/stt.py:49–88` — `_load_engine()` tries `faster_whisper.WhisperModel` first, falls back to `openai-whisper`.

### 2.4. Frontend caller presence/absence

- `grep -r "stt/transcribe" ui/` → **0 hits.**
- `grep -E "STT|stt|transcribe" ui/js/api.js` → **0 hits.** The endpoint is not even declared in the frontend's URL constants table (unlike `EXTRACT_FIELDS`, `THREAD_ANCHOR_GET`, etc.).
- `grep -c "/api/stt/transcribe\|stt_transcribe\|POST.*stt" .runtime/logs/api.log` → **0.** Zero transcribe requests in the current API log.
- `.runtime/logs/api.log` contains 94 matches for `stt|transcribe|whisper`, and all 94 are launcher banner prints `[launcher] STT_MODEL=large-v3 STT_GPU=1`. No runtime invocations.

**Conclusion:** `/api/stt/transcribe` is dead code from the browser's perspective.

### 2.5. Model default / env override truth

- `server/code/api/routers/stt.py:54` — code default: `model_size = os.getenv("STT_MODEL", "medium").strip() or "medium"`.
- `.env:STT_MODEL=large-v3` and `.env:STT_GPU=1` (both also in `.env.example`).

**Conclusion:** the code default is `medium` but the live `.env` sets it to `large-v3`. The WO-01 claim "backend is configured for local Whisper `large-v3`" is **true at config level**. However, since no transcribe request has ever been made in the current log window, the large-v3 model has never actually been loaded or run against any audio. "Configured for" ≠ "proven in use."

### 2.6. Backend response payload shape

- `server/code/api/routers/stt.py:149` — `return {"ok": True, "text": text}`.
- No `confidence`. No `segments`. No `avg_logprob`. No per-word timing.
- `faster_whisper` transcribe call at `stt.py:131–137` receives segments with `avg_logprob` on each, but the code discards them via `" ".join(s.text.strip() for s in segments)`.

**Conclusion:** today's backend payload is strictly `{ok, text}`. The WO's Phase 2C "normalized transcript object" that includes `confidence` would require stt.py to be extended before it can be populated from the primary source. Ironic note: browser Web Speech's `SpeechRecognitionResult[0].confidence` *does* exist per-result — today's fallback would have a field the primary cannot provide.

### 2.7. Extraction payload vs STT metadata

- `server/code/api/routers/extract.py:36–65` — `ExtractFieldsRequest` has `person_id`, `session_id`, `answer`, `current_section`, `current_target_path`, `current_target_paths`, `profile_context`, `current_phase`, `current_era`, `current_pass`, `current_mode`. It does **not** carry `transcript_source`, `transcript_confidence`, or `fragile_fact_flag`.
- `server/code/api/routers/extract.py:57–76` — `ExtractedItem` has a `source` field but that tags the **extractor pipeline** (`"backend_extract"`), not the **input audio source**.

**Conclusion:** the extractor is currently blind to whether the `answer` text came from Web Speech, backend Whisper, or typing. Phase 2A/4D of the migration WO would require this field to be added.

### 2.8. State model for mic permission

- `ui/js/state.js:234–240` — `inputState: { micActive, micPaused, cameraActive, cameraConsent }` (booleans only).
- `ui/js/state.js:364–367` — `permMicOn = true` (module-level boolean default).

**Conclusion:** no real permission-state machine. No `unknown / requesting / granted / denied / blocked / device_missing` states. The app treats permissions as binary. The WO's Phase 3A model doesn't exist today.

### 2.9. UI mic button wiring

- `ui/hornelore1.0.html:2988` — `<button id="btnMic" title="Click to toggle microphone" onclick="toggleMic()">`.
- `ui/js/app.js:3754–3755` — `toggleMic() { toggleRecording(); }`.
- `ui/js/app.js:3733–3752` — `toggleRecording()` → `startRecording()` or `stopRecording()`.
- `ui/js/app.js:3903–3920` — `_setMicVisual()` handles four visual states: `true/"listening"`, `false/"off"`, `"wait"`, `"blocked"`.

### 2.10. Self-hearing guard (Lori-hearing-herself)

- `ui/js/app.js:3461` — `let isLoriSpeaking = false;`
- `ui/js/app.js:3579, 3687` — set on TTS start, cleared on TTS end.
- `ui/js/app.js:3794–3800` — inside `recognition.onresult`: if `isLoriSpeaking`, discard the result with `console.warn("[STT guard] Recognition fired while isLoriSpeaking=true — result discarded.")`.
- `ui/js/app.js:3818` — `onend` auto-restart is gated on `isRecording && !isLoriSpeaking`.

**Conclusion:** the guard is tightly coupled to `recognition.onresult` — a callback that exists only in the Web Speech path. A MediaRecorder → backend migration has to re-implement the guard as a *pre-capture* gate (don't start recording while TTS is speaking), not a *post-result* filter.

### 2.11. Other frontend STT surfaces

- `ui/js/camera-preview.js:42` — calls `navigator.mediaDevices.getUserMedia({ video: true, audio: false })`. Video-only; not an STT path.
- `ui/js/emotion.js:403` — references `getUserMedia` in the emotion engine. Video path; not STT.
- No other `MediaRecorder`, `getUserMedia({audio:true})`, `SpeechRecognition`, or fetch-to-`/api/stt` callers exist in `ui/`.

---

## 3. Call chain (mic click → transcript enters app)

```
user clicks #btnMic
  hornelore1.0.html:2988  onclick="toggleMic()"
  app.js:3754             toggleMic() → toggleRecording()
  app.js:3733             toggleRecording() → startRecording()
  app.js:3868             startRecording() → _ensureRecognition()
  app.js:3788             _ensureRecognition()
                             - creates new webkitSpeechRecognition
                             - recognition.continuous = true
                             - recognition.interimResults = true
                             - installs onresult / onend / onerror handlers
  app.js:3876             recognition.start()  ← Chrome opens mic + streams audio to Google

audio → Google → transcript event
  app.js:3793             recognition.onresult(e)
    if isLoriSpeaking: discard (line 3796)
    build final-only string from e.results where isFinal (line 3801)
    check for voice-send commands (line 3806, off by default)
    _normalisePunctuation(fin) (line 3811)
    setv("chatInput", ...) (line 3812)   ← text lands in the input box

user sends message (typed or via send button)
  …submit path → interview.js / app.js → /api/extract-fields with req.answer = display text

focus-canvas surface
  focus-canvas.js:269   _startListening() → window.toggleRecording()
  focus-canvas.js:305   wraps window.recognition.onresult
  → same engine, same Google dependency, same guard
```

No path in this chain touches `server/code/api/routers/stt.py`.

---

## 4. Backend STT gap analysis

Status: **unused and blocked by multiple issues.**

| Gap | Evidence | Severity |
|---|---|---|
| Frontend capture gap | no `MediaRecorder` + no `navigator.mediaDevices.getUserMedia({audio:true})` anywhere in `ui/` | **blocker** — must be built from scratch |
| Frontend wiring gap | `ui/js/api.js` has no STT endpoint constant; grep `stt/transcribe` in `ui/` → 0 hits | **blocker** |
| Backend streaming gap | `stt.py:106–154` is multipart batch only; no chunked / WebSocket path | **UX concern** — end-of-utterance batch adds 1–4s perceived latency vs. Web Speech interim results |
| Backend response gap | `stt.py:149` returns `{ok, text}`; discards faster-whisper segment-level `avg_logprob` | **blocker for WO's confidence requirement** |
| Model-proven gap | `.env:STT_MODEL=large-v3`, but 0 transcribe requests in `api.log` | **"configured ≠ proven"** — first real transcribe will also be the first real model load on the 50-series GPU |
| Permission-model gap | `state.js:234–240` has booleans only; no 6-state machine | **UX concern** — elderly narrators are the exact users who hit denial/reload edge cases |
| Extraction-payload gap | `extract.py:ExtractFieldsRequest` has no transcript-source / transcript-confidence fields | **blocker for WO Phase 4D fragile-fact guard** |
| Self-hearing-guard gap | guard lives in `recognition.onresult` (app.js:3794); MediaRecorder has no onresult | **semantic rewrite needed** — must move to pre-capture gating |
| Focus-canvas gap | `focus-canvas.js:299` polls for `window.recognition`; would go stale if recognition is gone | **needs parallel update** — not a separate surface, but directly coupled to the Web Speech object |
| Live-testing gap | requires human running Chrome on the WSL-hosting box with real mic | **agent-can't-close** — all acceptance gates B–E need Chris to drive |

**Net read:** backend STT is an **empty shell** with respect to the live path. Config is present, the model is probably downloaded, but no audio has ever reached it. Migration is a greenfield build on the frontend + an extension on the backend, not a rewiring of existing traffic.

---

## 5. Chrome permission analysis

### 5.1. Current handling (facts)

- **Permission request:** implicit, via the first `recognition.start()` call inside `startRecording()`. The browser's prompt is triggered automatically; there is no pre-flight `navigator.permissions.query({name:'microphone'})` call anywhere in `ui/`.
- **Permission denied:** `app.js:3837–3842` — `onerror(e.error === "not-allowed")` calls `stopRecording()`, sets mic visual to `"blocked"`, and shows a `sysBubble` with instructions.
- **No-speech cascade:** `app.js:3822–3852` — Web Speech fires `no-speech` every ~5s during silence. The code throttles logging to every 5th event and shows a gentle nudge after 20 events (~100s). Authored for Kent/Janice natural long pauses.
- **Network-dependent:** `app.js:3853–3856` — `onerror(e.error === "network")` shows *"🎤 Speech recognition requires an internet connection (Chrome sends audio to Google's servers)."* This is the code itself acknowledging the Google-server dependency.
- **Service unavailable:** `app.js:3857–3859` — `onerror(e.error === "service-not-allowed")` handles non-HTTPS / blocked-by-config cases.
- **Auto-restart:** `app.js:3818` — `onend` auto-restarts if `isRecording && !isLoriSpeaking`. This means a single user "mic on" claim keeps restarting recognition sessions until stopped explicitly.

### 5.2. Assumptions the current code makes (likely failure states)

1. **Permission survives reload.** Chrome will usually remember a granted permission for an HTTPS/localhost origin across reloads, but there are edge cases (incognito mode, clear-site-data, system-level privacy changes) where it resets to unknown. Current code has no "re-prompt" path — if permission is silently lost mid-session, the next `recognition.start()` fails with `not-allowed` and the app goes to `blocked` state.
2. **Mic is available.** No `device_missing` state. If the user unplugs a USB mic mid-session, `start()` throws and the `"already started"` branch in `app.js:3882–3887` will not catch it — falls into the generic `sysBubble` path.
3. **Single-tab exclusivity.** If another tab opens a recognition instance, Chrome will revoke the audio device from this tab silently. No detection.
4. **Online-only.** The `network` error branch exists but offline-use simply stops working; no queued offline capture.
5. **HTTPS or localhost.** Web Speech will refuse to start on `http://` origins other than localhost.

### 5.3. UI permission surfacing today

- Visual states `listening / off / wait / blocked` are handled (`_setMicVisual`, app.js:3903–3920).
- No state for `unknown / requesting / denied-recoverable / device_missing`.
- No visible "STT source" label — narrator cannot tell whether audio is going to Google or to a local backend.

### 5.4. Relevant fact for migration

A MediaRecorder + backend path would **change the permission story in user-visible ways**:

- The first request would be a `navigator.mediaDevices.getUserMedia({audio:true})` call; this gives a different Chrome prompt (different wording, same underlying permission).
- Offline capability changes: browser can buffer audio → backend transcription is still online-dependent but on **your** server, not Google's.
- No per-result confidence from `faster-whisper` unless `stt.py` is extended to surface it.

---

## 6. Risk framing correction

The prior WO framed this as "split-authority cleanup / remove hidden parallel system."

**That framing is wrong.** The correct framing:

> There is one live STT authority in Hornelore today: Chrome's Web Speech API, sending audio to Google's servers. A backend Whisper route exists as dead code. Any "migration" is therefore a **greenfield build on the frontend capture path + an extension on the backend response** — not a consolidation.

This changes the risk profile:

- **Old framing implied:** regression risk is low because we're removing a hidden path that wasn't really doing anything.
- **Actual reality:** regression risk is **non-trivial** because we're replacing a working path (Web Speech with tuned guards, auto-restart, no-speech cascade, voice-send, TTS self-hearing guard) with an unproven path (MediaRecorder → batch upload → Whisper) and all of those tuned behaviors have to be re-implemented under a different event model.

The strongest argument for migration is **not** accuracy (Web Speech on Chrome is decent for American English) — it is **privacy**: every narrator utterance for an elderly memoir product currently goes to Google. That is the headline. Accuracy / no-internet-dependence / confidence-data are secondary wins.

---

## 7. Recommended next cut

**Step 2 first. Step 3 after Step 2 ships.**

Rationale:

- **Step 2 (STT-agnostic fragile-fact guard)** ships value under *either* STT authority. It tightens extraction write discipline on the fact classes that matter (names, DOBs, birthplaces, spouse/child/sibling anchors) regardless of whether the audio came from Google or Whisper. Today Web Speech mis-hears "Dorothy" as "Darlene" and the extractor writes it. Step 2 fixes that specific write leak before we touch the capture path.
- **Step 2 is local to `extract.py` + one new request field + a small amount of interview-flow code**. It does not require a live Chrome test matrix to sign off. Agent can close Gates on Step 2 without you.
- **Step 3 is a greenfield frontend build.** Larger. Must be behind a flag (`HORNELORE_STT_BACKEND=1` or similar). Must be paired with a `stt.py` extension to return `confidence` + segments. Must be live-tested in Chrome by you. Not something to start mid-R5.5.
- Shipping Step 2 first means Step 3's test matrix is simpler: when we flip the flag, we already know the extraction-safety layer is holding, so we're isolating the *capture* change and only the *capture* change.

### Step 2 shape (preview, not committed by this WO)

- Add `transcript_source` (`"browser_web_speech" | "backend_whisper" | "typed" | "unknown"`) and `transcript_confidence` (`Optional[float]`) to `ExtractFieldsRequest`.
- Extract side: classify any fact touching `personal.fullName`, `personal.dateOfBirth`, `personal.placeOfBirth`, `parents.*`, `spouse.*`, `siblings.*`, `family.children.*` as **fragile**. On fragile + low-confidence-source, downgrade `writeMode` to `suggest_only` with a `confirmation_required=true` flag. Lori asks "Did you say Dorothy or Darlene?" before the projection lands.
- Frontend side: tag every `/api/extract-fields` call with the source (`"browser_web_speech"` until Step 3 lands) and typed-input turns as `"typed"`.
- Keep it behind a soft flag for one eval turn so we can measure: does a fragile-fact guard change the topline of the master eval? It shouldn't (the eval feeds typed strings, source will be `"typed"` and confidence will pass), but we want to prove it's a no-op on the 104-case suite before calling it safe.

### Step 3 shape (preview, not committed)

- Extend `stt.py` to return `{ok, text, segments: [{text, avg_logprob, start, end}], confidence}` where `confidence` is derived from `mean(segments[].avg_logprob)`.
- Frontend: new capture module — `getUserMedia({audio:true})`, `MediaRecorder`, VAD-ish silence detection, batch upload on utterance end.
- Re-implement `isLoriSpeaking` guard as **pre-capture** (don't start recorder while TTS is active), not post-result.
- Behind `HORNELORE_STT_BACKEND` flag. Visible UI state labeling "Source: Whisper (local)" vs "Source: Chrome (Google)".
- Fallback path: if backend `/api/stt/status` returns not-ok or `/transcribe` fails, show `sysBubble` + use browser Web Speech as explicit labeled fallback. No silent downgrade.

---

## 8. Stop/go gate

| Question | Answer |
|---|---|
| GO to Step 2 (fragile-fact guard, STT-agnostic)? | **Yes, recommended.** Agent-closable. Ships value independent of STT migration. Small surface. |
| GO to Step 3 (backend migration behind flag)? | **Not yet.** Gated on Step 2 landing + a Phase 3 causal-matrix decision on SECTION-EFFECT-01 (#95) so R5.5 critical path isn't abandoned mid-flight. |
| Prerequisites before Step 3 | (a) Step 2 shipped and eval-clean. (b) `stt.py` extended to return confidence + segments. (c) Chris has an uninterrupted block to drive the live Chrome test matrix. (d) `HORNELORE_STT_BACKEND` flag scaffolded so Step 3 defaults off. |
| When to revisit the privacy framing | As the headline argument for Step 3 when that WO is written. Hornelore is an elderly-memoir product; per-utterance data egress to Google is the actual motivator. |

---

## 9. Files inspected (complete list, for audit trail)

Frontend:
- `ui/hornelore1.0.html` (mic button at 2988)
- `ui/js/app.js` (recognition engine + guards at 3461–3960, toggleRecording at 3733)
- `ui/js/interview.js` (no mic / STT refs; verified by grep)
- `ui/js/api.js` (full file read; no STT endpoint declared)
- `ui/js/state.js` (234–245, 364–367 — input state + permission booleans)
- `ui/js/focus-canvas.js` (269–330 — hook around app.js recognition)
- `ui/js/camera-preview.js:42` (getUserMedia video-only; not STT)
- `ui/js/emotion.js:403` (getUserMedia video; not STT)

Backend:
- `server/code/api/routers/stt.py` (all 154 lines)
- `server/code/api/routers/chat_ws.py` (grepped for stt/transcribe/recognition — 0 hits)
- `server/code/api/routers/extract.py:36–76` (ExtractFieldsRequest + ExtractedItem fields)
- `server/code/api/prompt_composer.py` (grepped for stt/transcribe — 0 hits; "confidence" refs all belong to resume-confidence, not STT confidence)
- `server/code/api/api.py:103` (comment acknowledging stt.py owns `/api/stt/transcribe`)

Runtime/config:
- `.env` (`STT_MODEL=large-v3`, `STT_GPU=1`)
- `.env.example` (same)
- `.runtime/logs/api.log` (94 launcher banner hits for STT; 0 transcribe invocations)
- `scripts/start_all.sh`, `scripts/restart_api.sh` (no STT-specific wiring beyond the env load)

No files were modified during this audit.

---

## 10. Revision history

- 2026-04-20: Initial draft. Corrects WO-STT-LIVE-01's split-authority premise. Recommends Step 2 (fragile-fact guard) before Step 3 (backend migration behind flag).
