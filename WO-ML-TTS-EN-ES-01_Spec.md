# WO-ML-TTS-EN-ES-01 — Bilingual TTS for Lori (Kokoro primary, pluggable engine)

**Status:** SPEC (design-only) — no runtime patches until reviewed.
**Filed:** 2026-05-07
**Author:** Claude (dev computer)
**Companion to:** `docs/specs/MULTILINGUAL/MULTILINGUAL-PROJECT-PLAN.md`,
`docs/specs/MULTILINGUAL/HUGGINGFACE-MODELS-MULTILINGUAL.md`
**Replaces (in part):** the `HF_MODELS` doc's TTS section, which
referenced XTTS-v2 as primary — that recommendation is **demoted to
optional/experimental** here on license grounds (CPML non-commercial).

---

## Problem statement

Lorevox's runtime TTS today is locked to English speakers via:

```
.env: TTS_MODEL=tts_models/en/vctk/vits
       TTS_SPEAKER_LORI=p335
```

This works for Lori speaking English. It does NOT work when Lori
speaks Spanish (Phase 2 LANGUAGE MIRRORING RULE landed; she now
*writes* Spanish but the audio output mangles the pronunciation —
English VITS phonemes butcher Spanish words). For a code-switching
narrator, it's worse: each Lori response may flip languages, and
swapping `.env` per session is operationally untenable.

The mission is intergenerational storytelling. A Spanish-speaking
grandparent narrating to an English-reading grandchild — and vice
versa — needs a Lori that speaks **both languages naturally** in the
same session, in the same voice if possible, with no operator
intervention to switch models.

---

## Decision

**Kokoro-82M is the primary multilingual TTS for Lori.**

**The TTS engine is pluggable** behind `LORI_TTS_ENGINE=coqui|kokoro|melotts|piper|parler`. We do not hardwire to a single model. Bakeoff
script ships alongside so future quality experiments can compare
engines side-by-side on identical English + Spanish Lori lines.

The current Coqui VITS English path stays in tree as the **fallback**
(`LORI_TTS_ENGINE=coqui` keeps current behavior byte-stable).

---

## Why Kokoro-82M primary

- **License: Apache 2.0.** Commercial-friendly, clean for the Lorevox
  product path. No CPML non-commercial trap (which would gate XTTS-v2).
- **Multilingual built-in.** `KPipeline(lang_code="a")` for American
  English; `KPipeline(lang_code="e")` for Spanish. Single dependency,
  single code path, single voice family.
- **Small + fast.** 82M parameters. ~200 MB GPU footprint (estimated).
  Combined with Llama-Q4 (~5 GB) + Whisper (~3 GB if active) leaves
  comfortable headroom on the RTX 5080 16 GB.
- **Already battle-tested.** HuggingFace `hexgrad/Kokoro-82M` has a
  large user base; the language-code interface is stable.
- **No voice cloning.** That's a feature for our use case — narrator
  privacy posture forbids voice cloning of real people, and the
  product doesn't need it.

### Why NOT XTTS-v2 (despite earlier consideration)

- **License: Coqui Public Model License — non-commercial only.**
  Lorevox's commercial path would require a license carve-out from
  Coqui that we don't have, OR a swap in the future under deadline
  pressure. Building the product on a non-commercial foundation is
  a footgun.
- Strong multilingual quality + voice cloning are real but we don't
  need either of those features for v1, and the licensing risk
  outweighs the quality lift.

XTTS-v2 stays available as a **private experimental** path behind
`LORI_TTS_ENGINE=xttsv2` for Hornelore-only family use (not commercial
Lorevox use). Spec'd separately from this WO.

### Why other engines stay in the bakeoff tier (not primary)

| Engine | License | Why not primary |
|---|---|---|
| **MeloTTS** | MIT | Older stack, smaller community momentum than Kokoro. Likely runner-up if Kokoro Spanish quality disappoints. |
| **Piper** | MIT | Per-voice language pack (English voice + Spanish voice are different speakers — feels like two different Loris when narrator code-switches). Good fallback for emergency-local TTS. |
| **Parler-TTS Mini Multilingual** | Apache 2.0 | ~0.9B params — much heavier than Kokoro-82M. Quality experiment if Kokoro voice fidelity is insufficient. |
| **Zonos** | Apache 2.0 | Heavy runtime, speaker-conditioning complexity we don't want. Future research, not v1. |
| **XTTS-v2** | CPML (non-commercial) | License risk for commercial path. Private-experimental only. |

---

## Architecture: pluggable engine

```
┌─────────────────────────────────┐
│ chat_ws.py / FE drainTts()      │
│   POST /api/tts/speak_stream    │
│   { text, language, voice }     │
└──────────────┬──────────────────┘
               │
        ┌──────▼──────┐
        │  tts.py     │   reads LORI_TTS_ENGINE
        │  router     │   dispatches by engine + language
        └──┬───────┬──┘
           │       │
   ┌───────▼─┐  ┌──▼──────┐  ┌──────────┐  ┌─────────┐  ┌──────────┐
   │ coqui   │  │ kokoro  │  │ melotts  │  │ piper   │  │ parler   │
   │ (legacy)│  │ adapter │  │ adapter  │  │ adapter │  │ adapter  │
   └─────────┘  └─────────┘  └──────────┘  └─────────┘  └──────────┘
```

**Adapter contract (Python):**

```python
class TTSAdapter:
    def supported_languages(self) -> list[str]: ...
    def synthesize(self, text: str, language: str, voice: str | None) -> bytes:
        """Returns WAV bytes (22050 Hz mono int16)."""
```

Each engine implements this surface. The router dispatches by reading
`LORI_TTS_ENGINE` env at request time (lazy, so the operator can flip
the engine without restart for adapter testing).

### Failure mode

When the chosen engine fails (model unavailable, dependency missing,
synthesis exception), the router falls back to `coqui` (the existing
English VITS path). This guarantees Lori always has audio — even if
Spanish synthesis breaks, English text plays cleanly through the
pre-WO-ML-TTS path. The narrator-visible result on a Spanish text
through Coqui fallback: audibly butchered Spanish (English phonemes
on Spanish words) but the chat bubble still shows the correct
Spanish text. Operator-greppable `[ml-tts][fallback]` log line records
the engine failure for post-mortem.

---

## Implementation plan (NOT STARTING UNTIL SPEC REVIEWED)

### Files that will change

| File | Change |
|---|---|
| `server/code/api/services/tts_kokoro.py` | NEW — `KokoroAdapter` class, lazy-loaded `KPipeline(lang_code=...)`, voice map `en→af_heart` / `es→<chosen>` |
| `server/code/api/services/tts_engine.py` | NEW — adapter base class + `get_engine(name) -> TTSAdapter` factory + `_detect_language(text)` helper |
| `server/code/api/routers/tts.py` | EXTEND — accept `language` field in payload, dispatch via `get_engine`, log markers `[ml-tts][detect|request|ok|fallback]`, fall back to coqui on adapter failure |
| `ui/js/app.js` | EXTEND — `drainTts()` detects Spanish before each chunk, includes `language` in speak_stream POST body |
| `.env.example` | EXTEND — add `LORI_TTS_ENGINE`, `LORI_TTS_DEFAULT_LANGUAGE`, `LORI_TTS_KOKORO_LANG_EN`, `LORI_TTS_KOKORO_LANG_ES`, `LORI_TTS_KOKORO_VOICE_EN`, `LORI_TTS_KOKORO_VOICE_ES` |
| `scripts/smoke_dual_language_tts.py` | NEW — POST one EN line + one ES line, verify both come back as valid WAV |
| `scripts/tts_bakeoff.py` | NEW — POST same text through coqui/kokoro/melotts/piper, save WAV files for human side-by-side listening |
| `requirements-gpu.txt` | ADD — `kokoro` (and possibly `kokoro-onnx` lighter variant) |

### NOT in this WO scope

- MeloTTS adapter implementation (placeholder in factory only)
- Piper adapter implementation (placeholder in factory only)
- Parler adapter implementation (placeholder in factory only)
- XTTS-v2 adapter (separate private-experimental WO)
- Voice cloning of any kind
- TTS streaming (current path is full-WAV synthesis; streaming is a future optimization)
- Per-narrator voice preference (operator config, future WO)

### `.env.example` block

```bash
# WO-ML-TTS-EN-ES-01 (2026-05-07) — bilingual Lori TTS engine selection.
# Default 'coqui' preserves the current English-only TTS path byte-stable.
# 'kokoro' is the multilingual primary (Apache 2.0, English + Spanish).
# 'melotts', 'piper', 'parler' are stubs at v1; see WO-ML-TTS-EN-ES-01_Spec.md.
LORI_TTS_ENGINE=coqui

# Default language when the FE doesn't supply one. Used by all engines.
LORI_TTS_DEFAULT_LANGUAGE=en

# ── Kokoro-82M voice + lang-code map ────────────────────────────────
# lang_code: 'a' = American English, 'b' = British English, 'e' = Spanish,
# 'f' = French, 'h' = Hindi, 'i' = Italian, 'j' = Japanese,
# 'p' = Brazilian Portuguese, 'z' = Mandarin Chinese.
LORI_TTS_KOKORO_LANG_EN=a
LORI_TTS_KOKORO_LANG_ES=e

# Voice IDs from the Kokoro voice list. 'af_heart' is a stable American
# English voice. Spanish voice ID is a placeholder; pick one of the
# 3 Spanish voices (1F + 2M) from the Kokoro voice list during smoke.
LORI_TTS_KOKORO_VOICE_EN=af_heart
LORI_TTS_KOKORO_VOICE_ES=ef_dora       # placeholder — verify on first install
```

### Voice + language code map (Kokoro)

| Lang | lang_code | Default voice | Notes |
|---|---|---|---|
| English (American) | `a` | `af_heart` | Larger voice pool available; warm female default |
| Spanish | `e` | `ef_dora` (placeholder) | 3 voices available (1F + 2M); pick during smoke after listening |
| English (British) | `b` | `bf_emma` (alt) | Reserved for future operator preference |
| French / Italian / Hindi / Japanese / Brazilian Portuguese / Mandarin | `f / i / h / j / p / z` | future | Out of scope for v1 |

The Kokoro voice list is small enough that we ship a fixed map in
`.env.example`. Operator can override per machine.

### Language detection

Lori's response language is detected client-side AND server-side
(defense in depth):

- **Client-side** (`ui/js/app.js`): `_lvDetectLang(text)` — same
  heuristic as `services/lori_spanish_guard.looks_spanish` — accent
  chars OR ≥2 distinct Spanish function words → "es", else "en".
  Result attached to speak_stream POST body as `language`.
- **Server-side** (`tts.py` / adapters): when payload omits `language`,
  fall back to server-side detection using the same heuristic via
  `services/lori_spanish_guard.looks_spanish`. Default: "en" when
  detection is ambiguous.
- **Explicit assistant_language wins**: future hook for operator
  override or runtime71 propagation. Out of scope for v1; mentioned
  in adapter contract for forward-compat.

### Bakeoff script (`scripts/tts_bakeoff.py`)

Operator runs this when comparing engines:

```bash
./scripts/tts_bakeoff.py --engines coqui kokoro [melotts piper] \
    --output .runtime/tts-bakeoff/
```

Produces:

```
.runtime/tts-bakeoff/
  coqui_en_welcome.wav
  coqui_es_bienvenida.wav     # English-phoneme Spanish; reference of the gap
  kokoro_en_welcome.wav
  kokoro_es_bienvenida.wav
  ... (other engines if installed)
  bakeoff_report.txt           # synthesis time per engine + per language
```

Same fixed reference lines for every engine:

- **EN short:** "Welcome back. Ready when you are."
- **EN medium:** "Tell me about a place from your earliest years."
- **EN long:** A 60-word memoir-style sentence.
- **ES short:** "Bienvenida de nuevo. Estoy lista cuando usted quiera."
- **ES medium:** "Cuéntame sobre un lugar de tus primeros años."
- **ES long:** "Nací en Las Vegas, Nuevo México. Mi abuela hacía
  tortillas los domingos y la casa olía a maíz caliente. ¿Qué
  recuerdas tú de los domingos cuando eras pequeña?"
- **Code-switch:** "Welcome back, María. Cuéntame, ¿cómo estás hoy?"

Operator listens to each WAV and grades fidelity. No automated quality
score — human ear is the judge for v1.

---

## Acceptance gates

Before flipping `LORI_TTS_ENGINE=kokoro` from the default `coqui`:

1. **Smoke pass:** `./scripts/smoke_dual_language_tts.py` returns
   200 on both English + Spanish requests, both responses are valid
   WAV (PCM 16-bit), both have non-zero duration.
2. **Log markers visible:** `grep "\[ml-tts\]" .runtime/logs/tts.log`
   shows `[ml-tts][detect]`, `[ml-tts][request]`, `[ml-tts][ok]` per
   request. No `[ml-tts][fallback]` on the smoke pack (would mean
   Kokoro silently failed and Coqui covered).
3. **Spanish accent rendering:** Spanish smoke line `"Nací en Las
   Vegas, Nuevo México. Mi abuela hacía tortillas los domingos."`
   is audibly Spanish, not English-phoneme-on-Spanish-words. Human
   ear test by Chris.
4. **VRAM headroom:** combined Llama + Whisper + Kokoro fits comfortably
   on RTX 5080 16 GB. Per VRAM-bench baseline (~9.5 GB current),
   Kokoro adds estimated ~200 MB. Hard requirement: leave ≥3 GB
   headroom under realistic workload.
5. **Mic / TTS state-machine integrity:** browser doesn't get stuck
   amber after Spanish playback. Tests: speak Spanish, wait 2s, click
   mic — should arm cleanly.
6. **English regression:** typing English to mary or marvin produces
   English audio identical (or quality-equivalent) to pre-WO-TTS-EN-ES
   path. No subtle quality drop on the existing English narrator
   experience.
7. **Bakeoff WAVs landed:** `.runtime/tts-bakeoff/` contains coqui +
   kokoro pairs across the reference set; operator files an opinion
   either approving Kokoro voice or rejecting it back to bakeoff
   tier.

When all 7 gates green, `.env` flip lands as a separate small commit:
`LORI_TTS_ENGINE=coqui` → `LORI_TTS_ENGINE=kokoro`. Default in
`.env.example` stays `coqui` until production-confidence is high
enough to flip the operator default.

---

## Risks + mitigations

1. **Kokoro Spanish quality may be thinner than English.** Per the
   Kokoro voice docs, non-English support has weaker grapheme-to-
   phoneme coverage and smaller training data per language.
   *Mitigation:* bakeoff script lets us compare against MeloTTS / Piper /
   Parler before committing. If Kokoro Spanish is bad, we drop to
   `LORI_TTS_ENGINE=melotts` without code rewrite — pluggable design
   wins.

2. **Short Spanish utterances may rush or distort.** Per Kokoro
   docs, voices may perform worse on utterances under ~10–20 tokens.
   *Mitigation:* server-side check before synthesis — if Lori response
   is `"Sí."` or `"Claro."` (≤2 tokens), pad to a slightly fuller
   sentence ("Sí, María. Estoy escuchando.") OR skip TTS for that
   chunk. Spec'd as a follow-up patch within this WO.

3. **`espeak-ng` is a system-level dependency.** Kokoro requires
   `apt install espeak-ng` (Linux/WSL) for phonemization. Operator
   must install before flipping the flag.
   *Mitigation:* document in `.env.example` block + smoke script
   exits cleanly with installation instructions if `espeak-ng` is
   missing.

4. **VRAM contention on RTX 5080.** Llama (5 GB) + Whisper (3 GB) +
   Kokoro (~0.5 GB est) = ~8.5 GB. With WO-10M VRAM-GUARD overhead
   (~1 GB) and operating-system overhead, we're at ~10 GB used /
   16 GB total. Comfortable but worth verifying.
   *Mitigation:* WO-10M's nvidia-smi poller logs VRAM during smoke;
   any `[VRAM-GUARD]` block events during Kokoro warmup → adapter
   fails closed and falls back to Coqui.

5. **Voice cloning misuse.** Kokoro doesn't support voice cloning,
   which is fine. But other engines in the bakeoff tier (XTTS-v2,
   Zonos) do. *Mitigation:* the adapter contract `synthesize(text,
   language, voice)` does NOT accept reference audio; voice is a
   string ID into a fixed voice map. Cloning is impossible by
   construction at this layer.

---

## Sequencing

```
✅ BUG-ML-LORI-SPANISH-PERSPECTIVE-01 perspective + fragment guard
   (in tree, awaiting commit + push + stack restart + live verify)

⏸ Live verify perspective fix — María's "Cuando mi abuela hablaba de
   Perú..." → Lori "Tu abuela / ese recuerdo de tu abuela..."

⏸ THIS SPEC: WO-ML-TTS-EN-ES-01_Spec.md — review by Chris

⏸ Phase A: Pluggable adapter scaffolding
   - tts_engine.py base class + factory + language detector
   - tts.py route accepts language field, dispatches via get_engine
   - Default LORI_TTS_ENGINE=coqui (preserves current behavior)
   - English regression smoke

⏸ Phase B: Kokoro adapter
   - kokoro pip install + espeak-ng documented
   - tts_kokoro.py implementation
   - .env.example block
   - smoke_dual_language_tts.py
   - bakeoff script with coqui + kokoro entries

⏸ Phase C: Live smoke + acceptance gates 1-7

⏸ Phase D: Operator approval → .env flip from coqui to kokoro

⏸ Future: MeloTTS / Piper / Parler stubs flesh out into adapters
   when bakeoff drives a quality decision.
```

---

## Estimated effort

| Phase | Work | ETA |
|---|---|---|
| Spec review (this doc) | Chris reads + approves / amends | 30 min |
| Phase A — adapter scaffolding | tts_engine.py + tts.py extension + FE language detect | ~2 hrs |
| Phase B — Kokoro adapter | kokoro_tts.py + smoke + bakeoff script | ~2 hrs |
| Phase C — live smoke | Install deps + 7 acceptance gates | ~1 hr |
| **Total runtime work** | After spec approval | **~5 hrs** |

---

## What I need from Chris before runtime patches start

1. **Approve this spec** (or amend). The pluggable architecture +
   Kokoro-primary + bakeoff-included design is the load-bearing
   call.
2. **Install deps when Phase B starts:** `pip install kokoro` +
   `sudo apt install espeak-ng` on the dev machine. I can drive the
   pip install via a copy-paste WSL block, but `sudo apt` needs
   you.
3. **Confirm the live perspective verification is green** before
   any TTS runtime work begins. The locked sequence stands.

When all three are confirmed, Phase A starts.
