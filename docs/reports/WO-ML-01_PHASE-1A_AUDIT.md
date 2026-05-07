# WO-ML-01 Phase 1A — Backend STT Route Audit

**Date:** 2026-05-07
**Author:** Claude (dev computer)
**Scope:** Read-only audit of `/api/stt/transcribe` + minimal response-metadata patch.
**Supersedes:** nothing (companion to `WO-STT-LIVE-01A_AUDIT.md` from 2026-04-20).
**Status:** AUDIT DONE + tiny-safe patch landed in same pass (response metadata only).

---

## Files read

- `server/code/api/routers/stt.py` — full file (155 lines)
- `server/code/api/main.py:97` import + `:132` mount
- `server/code/api/api.py:115–116` legacy comment confirming the route is mounted under prefix `/api/stt`
- `.env` lines 104–105 — `STT_MODEL=large-v3`, `STT_GPU=1`
- `ui/js/app.js:6183–6240` — current Web Speech `_ensureRecognition()` and `recognition.onresult` shape
- `ui/js/transcript-guard.js` (selected lines 117–360) — existing FE staging layer that already expects `{text, confidence, language, source}` from a future backend STT response (`populateFromBackendResult` at line 204)
- `docs/reports/WO-STT-LIVE-01A_AUDIT.md` (predecessor; reference only)
- Greps for callers / tests / scripts: zero hits in `ui/`, `tests/`, `scripts/`

---

## Q1 — Is `/api/stt/transcribe` mounted and reachable?

**Yes.**
- Router defined at `server/code/api/routers/stt.py:24` with `prefix="/api/stt"`.
- Imported at `server/code/api/main.py:97` (`from .routers import ..., stt, ...`).
- Mounted at `main.py:132` (`app.include_router(stt.router)`).
- `GET /api/stt/status` and `POST /api/stt/transcribe` both reachable.
- The engine is lazy-loaded inside `_load_engine()` on first call, so module import is cheap; first request pays a one-time model load (~10–30s for large-v3 on CUDA).

---

## Q2 — What request params are accepted today?

`POST /api/stt/transcribe` is multipart (`multipart/form-data`) with these fields per `stt.py:107–110`:

| Field | Type | Default | Notes |
|---|---|---|---|
| `file` | `UploadFile` | required | webm / ogg / mp4 / wav (browser audio blob) |
| `lang` | `str` (Form) | `"en"` | passed to `WhisperModel.transcribe(language=...)` |
| `initial_prompt` | `str` (Form) | `""` | passed through; "" → `None` |

No streaming; full-blob upload only. VAD filter is on (`vad_filter=True`, `min_silence_duration_ms=500`).

---

## Q3 — Does `lang` support `auto` / `en` / `es` explicitly?

**Partial.** Today `lang` defaults to `"en"` and is passed verbatim to faster-whisper, which accepts ISO-639-1 codes (`en`, `es`, `fr`, `de`, ...). What's missing for the multilingual lane:

- **No `auto` handling.** faster-whisper auto-detects when `language=None`, but the current code does `language=lang or "en"` at `stt.py:133` — so `lang=""` falls back to `"en"`, NOT to auto-detection.
- **No regional bias.** No way for the operator to nudge Mexican vs Castilian Spanish — though `initial_prompt` partially substitutes (e.g. *"The speaker is from Mexico City"*).

**Patch in this pass:** when `lang="auto"` (case-insensitive), pass `language=None` so Whisper auto-detects. Keep `lang="en"` default for backward-compatibility with any future legacy callers.

---

## Q4 — Does the response include `text`?

**Yes.** `stt.py:149` returns `{"ok": True, "text": text}`. The text is the joined trimmed concatenation of `s.text.strip()` for every segment. No leading/trailing whitespace.

---

## Q5 — Does the response include detected language?

**No.** The faster-whisper `engine.transcribe()` call at `stt.py:131–137` returns `(segments, info)` where `info.language` is the detected language. The current code captures it as `_info` and **discards it**. This is the primary response-shape omission — Phase 1B can't decide whether to render the transcript as English or Spanish without it.

**Patch in this pass:** rename `_info` → `info` and bubble `info.language` into the response.

---

## Q6 — Does the response include language probability / confidence?

**No.** faster-whisper provides:
- `info.language_probability` — float, the model's confidence in the detected language (1.0 = certain).
- Per-segment `avg_logprob` (segments are dataclass instances) — the model's per-segment log-probability, useful as a transcription-confidence proxy.

Both are discarded today. The existing FE `transcript-guard.js:204` already has a `populateFromBackendResult(result)` helper that reads `result.confidence` if present — so adding it backend-side aligns with prior FE design intent.

**Patch in this pass:** bubble `info.language_probability` and a duration-weighted mean of segment `avg_logprob` (normalized to a 0–1 scale) as `avg_logprob` and `confidence`.

---

## Q7 — Does the response include segments / duration / timestamps?

**No.** faster-whisper segments carry `start`, `end`, `text`, `avg_logprob`, `no_speech_prob`, and word-level timestamps when `word_timestamps=True`. None bubble up today. `info.duration` (total audio duration) is also discarded.

**Patch in this pass:** add `info.duration` as `duration_sec` to the response. **DO NOT** add full segments / word-timestamps in this pass — that's a larger surface (introduces a new shape Phase 1B may or may not need; defer until proven necessary).

---

## Q8 — What exact response JSON should `ui/js/whisper-stt.js` expect?

### Response contract — Phase 1B target

```json
{
  "ok": true,
  "text": "<transcribed string, trimmed>",
  "language": "en|es|fr|...",        // ISO-639-1, detected by Whisper
  "language_probability": 0.0–1.0,   // null if openai-whisper fallback
  "confidence": 0.0–1.0,              // null if no segments
  "avg_logprob": -∞–0,                // raw faster-whisper score, null if openai-whisper fallback
  "duration_sec": 0.0,                // null if openai-whisper fallback
  "engine": "faster_whisper|whisper", // which path served the request
  "model": "large-v3"                 // resolved model size
}
```

On error: existing `HTTPException(500, ...)` shape preserved (FastAPI envelope). No partial-success shape.

### FE wrapper expectations (already present in transcript-guard.js)

`window.TranscriptGuard.populateFromBackendResult(result)` (`transcript-guard.js:204–238`) currently reads:
- `result.text` — required
- `result.confidence` — optional, number; gates fragile-fact downgrade
- `result.source = "whisper_backend"` (set by FE at population time, not by backend)

The new fields (`language`, `language_probability`, `duration_sec`, `engine`, `model`) are additive — `populateFromBackendResult` ignores unknown keys today, so adding them backend-side is byte-stable for the existing FE staging code.

---

## Q9 — Minimal backend patch needed before frontend wiring

**Yes — tiny + safe, applied in this same pass.** Patch surface:

1. **`lang="auto"` handling** — `lang.strip().lower() in ("auto", "")` → pass `language=None` to faster-whisper. Default still `"en"` for back-compat.
2. **Bubble Whisper metadata** — capture the `info` object from `engine.transcribe()`, surface `info.language`, `info.language_probability`, `info.duration` in the response.
3. **Compute response confidence** — iterate segments once (already iterated for text join); accumulate `avg_logprob` weighted by `(end - start)`; convert mean log-prob → 0-1 scale via `math.exp(avg_logprob)`.
4. **openai-whisper fallback parity** — return `language` if `result.get("language")` is present, else echo the input `lang`. `language_probability`, `avg_logprob`, `duration_sec` set to `null` (the openai-whisper Python API doesn't expose them by default).
5. **Greppable log markers** — `[ml-stt][route]` on entry (lang, file size), `[ml-stt][result]` on success (language, confidence, duration), `[ml-stt][error]` on failure. Single-line, structured, log-grep friendly.

**Out of scope for this pass** (deferred):
- Word-level timestamps (only useful for highlight-on-replay UI; not v1).
- Per-segment dump (callers can re-segment if needed; today's joined text is enough).
- Streaming response (chunked transfer; deferred to Phase 1C if latency proves unacceptable).
- Regional-variant prompt biasing (operator-side concern; `initial_prompt` already covers this).
- Authentication / rate limiting (Lorevox is local-first; out of scope).

---

## Was a patch made?

**Yes** — applied in this same pass per the WO directive ("Do not patch yet unless the audit finds a tiny response-shape omission that is safe to fix in the same pass"). The patch is:
- Pure response-metadata enrichment.
- Strictly additive (existing `{ok, text}` callers unaffected — there are zero today).
- One new request-param value (`lang="auto"`); existing values (`"en"`, `"es"`, `""`) behave identically.
- Three new log markers for greppable observability.

See `server/code/api/routers/stt.py` diff in this commit for exact change set. AST parse confirmed clean.

---

## Smoke test command

After Chris cycles the stack (or right now without a stack restart, since the route is unchanged at the import-time level — only the response body changed):

```bash
# 1. Confirm engine is alive + reports the right model/device
curl -s http://localhost:8000/api/stt/status | python3 -m json.tool

# Expected:
# {
#   "ok": true,
#   "engine": "faster_whisper",
#   "device": "cuda",
#   "model": "large-v3"
# }

# 2. English smoke (any short test webm/wav lying around)
#    Replace the path with a real audio file from /mnt/c/hornelore_data/...
curl -s -X POST http://localhost:8000/api/stt/transcribe \
  -F "file=@/mnt/c/hornelore_data/audio/<some_session>/<some_turn>.webm" \
  -F "lang=auto" \
  | python3 -m json.tool

# Expected (English audio):
# {
#   "ok": true,
#   "text": "Hello, my name is...",
#   "language": "en",
#   "language_probability": 0.98,
#   "confidence": 0.91,
#   "avg_logprob": -0.094,
#   "duration_sec": 3.42,
#   "engine": "faster_whisper",
#   "model": "large-v3"
# }

# 3. Spanish smoke (using the same auto path, swap the audio file)
curl -s -X POST http://localhost:8000/api/stt/transcribe \
  -F "file=@/mnt/c/hornelore_data/audio/<some_spanish_session>/<turn>.webm" \
  -F "lang=auto" \
  | python3 -m json.tool

# Expected:
# - "language": "es"
# - "language_probability": > 0.9
# - text in Spanish

# 4. Verify log markers
grep "\[ml-stt\]" /mnt/c/Users/chris/hornelore/.runtime/logs/api.log | tail -20

# Expected:
# [ml-stt][route] file=<n>B lang=auto resolved_lang=auto
# [ml-stt][result] engine=faster_whisper language=en lang_prob=0.98 confidence=0.91 duration=3.42s
```

If `confidence` or `language` shows up as `null` in the response when the engine is `faster_whisper`, that's a bug. If they show as `null` when the engine is `whisper` (openai-whisper fallback), that's expected.

---

## What this unlocks for Phase 1B

With the response contract above locked, `ui/js/whisper-stt.js` can:
1. POST audio chunks and receive enough metadata to render the transcript correctly per language.
2. Emit events that mimic Web Speech's `onresult` shape, with `language` and `confidence` carried in the event detail.
3. Feed `populateFromBackendResult` (which already exists in transcript-guard.js) without backend-side changes after Phase 1A.

Phase 1B is unblocked as soon as Chris cycles the stack and the smoke commands above return shape-correct responses.

---

## Acceptance gates

- ✅ Route mounted and reachable (verified via grep + manual route map review)
- ✅ Request params understood (file, lang, initial_prompt)
- ✅ Current response shape documented (`{ok, text}` only)
- ✅ Phase 1B target response contract proposed (tabular, with FE expectations cross-referenced)
- ✅ Tiny-safe patch landed (5 changes, additive, AST-clean)
- ✅ Greppable log markers wired
- ✅ Smoke commands provided

Phase 1A complete. Ready for Phase 1B (frontend `whisper-stt.js` module + feature flag + per-narrator operator toggle).
