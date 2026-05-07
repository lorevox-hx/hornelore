# HuggingFace Models — Multilingual Project Shopping List

**Filed:** 2026-05-07
**Companion to:** `MULTILINGUAL-PROJECT-PLAN.md`
**Purpose:** concrete model list with download commands, sizes, licenses, and integration notes. So Chris can pre-download what's needed before each phase starts.

---

## What's already in the stack (don't re-download)

| Model | Path | Size | Used for |
|---|---|---|---|
| `meta-llama/Meta-Llama-3.1-8B-Instruct` | `/mnt/c/models/hornelore/Meta-Llama-3.1-8B-Instruct` | 30GB (fp16, ~4.5GB Q4) | Lori's brain. Already multilingual. |
| `large-v3` (Whisper) | (via faster-whisper auto-download) | ~3GB | STT — referenced in `.env` as `STT_MODEL=large-v3` |

Whisper-large-v3 may already be downloaded by faster-whisper's lazy-load. Check:
```bash
ls -lh ~/.cache/huggingface/hub/models--Systran--faster-whisper-large-v3/ 2>/dev/null
ls -lh /mnt/c/models/hornelore/hf_home/ 2>/dev/null
```

If absent, faster-whisper will download on first call to `/api/stt/transcribe`. Internet required only for that first run.

---

## Phase 1 — Whisper STT integration (already in stack)

No new downloads needed. Whisper-large-v3 is the model.

**Optional for live-latency:** `Systran/faster-whisper-medium` (~1.5GB) for live transcription where speed matters more than accuracy. Use large-v3 for batch / archival.

```bash
# Pre-download faster-whisper-medium for live latency mode
python3 -c "from faster_whisper import WhisperModel; WhisperModel('medium', device='cuda', compute_type='float16')"
```

---

## Phase 2 — Multilingual Lori directive

No new downloads. Llama-3.1-8B-Instruct already handles 8+ languages including Spanish, French, German, Italian, Portuguese, Hindi, Thai. Just a prompt change.

---

## Phase 3 — Storage + UI labels

No new downloads. Translation table is hand-crafted for era warm labels (small static dict).

---

## Phase 4 — Safety patterns + memoir export

### Memoir translation
For bilingual side-by-side memoir export, Llama-3.1-8B handles English↔Spanish translation acceptably. For higher quality (recommended for memoir-grade output) consider:

| Model | Size | License | Notes |
|---|---|---|---|
| `facebook/seamless-m4t-v2-large` | ~9GB | CC BY-NC 4.0 | NON-COMMERCIAL ONLY — fine for personal/family use, NOT for paid product |
| `facebook/nllb-200-3.3B` | ~6GB | CC BY-NC 4.0 | Same NC restriction. 200 languages. |
| `Helsinki-NLP/opus-mt-en-es` | ~300MB | Apache 2.0 | Commercial-ok. Single language pair. Good quality. |
| `Helsinki-NLP/opus-mt-es-en` | ~300MB | Apache 2.0 | Reverse direction. |

**Recommendation:** Llama-3.1-8B for in-product translation (already in stack, already commercial-friendly). Helsinki-NLP `opus-mt` pair as a fast/light fallback. Skip Seamless and NLLB unless Lorevox stays personal/family-only forever.

### Safety pattern detection
No model — Spanish patterns are hand-curated regex authored by the agent and reviewed by a Spanish-speaking mental-health clinician (contact lined up 2026-05-07) before production landing. The LLM second-layer classifier already in place (SAFETY-INTEGRATION-01 Phase 2) uses Llama for fuzzy fallback and fails-OPEN to safety mode under parse failure. No external model dependency for this lane.

---

## Phase 5 — Auto-punctuation + auto-cap

| Model | Size | License | Languages | Notes |
|---|---|---|---|---|
| `oliverguhr/fullstop-punctuation-multilang-large` | ~1.4GB | MIT | en, de, fr, it, es, nl, pt | **Recommended primary.** Single model handles 7 languages. Returns text with periods, commas, question marks, capitalization. |
| `kredor/punctuate-all` | ~1.1GB | MIT | en, de, fr, it, es, nl, ru, pt, bg, pl, cs, sk | Wider language coverage, slightly lower quality on Spanish than oliverguhr's. |
| `oliverguhr/fullstop-deep-punctuation-prediction` | ~500MB | MIT | en only | Backup for English-only fast path if multilingual is overkill. |

```bash
# Pre-download recommended punctuator
python3 -c "from transformers import pipeline; pipeline('token-classification', model='oliverguhr/fullstop-punctuation-multilang-large', aggregation_strategy='simple', device=0)"
```

**Integration:** Python service called between STT output and chat-WS payload. Adds ~50ms per turn on RTX 5080. Confidence threshold tunable; low-confidence punctuation falls back to bare STT output.

---

## Optional / future phases

### VAD (voice activity detection) for Phase C / always-listening mode

| Model | Size | License | Notes |
|---|---|---|---|
| `snakers4/silero-vad` | ~2MB | MIT | Tiny, fast, 95+ languages. Recommended. |
| WebRTC VAD (built into browsers) | 0 | n/a | Free, lower quality than Silero. Useful as fallback. |

```bash
pip install silero-vad
# Or via torch hub
python3 -c "import torch; torch.hub.load('snakers4/silero-vad', 'silero_vad')"
```

### Speaker diarization (multi-speaker session — future feature)

| Model | Size | License | Notes |
|---|---|---|---|
| `pyannote/speaker-diarization-3.1` | ~1.2GB | MIT | Requires HuggingFace token + accept user agreement. Useful when narrator brings a family member to session for paired interviews. |

Not needed for v1.

### Bilingual embeddings (for cross-language search in memoir/transcript)

| Model | Size | License | Notes |
|---|---|---|---|
| `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` | ~1GB | Apache 2.0 | 50+ languages. Good for "find Spanish stories about cooking" semantic search. |
| `sentence-transformers/distiluse-base-multilingual-cased-v2` | ~500MB | Apache 2.0 | Smaller, faster, slightly lower quality. |

Not needed for v1; useful for "search across narrators' stories" feature.

---

## Sizes summary (cumulative VRAM if all loaded)

For RTX 5080 16GB capacity planning:

| Phase load | Components | VRAM | Headroom |
|---|---|---|---|
| Today | Llama-Q4 + Coqui VITS (CPU) | ~5GB | 11GB |
| After Phase 1 | + Whisper-large-v3 | ~8GB | 8GB |
| After Phase 5 | + multilingual punctuator | ~9.5GB | 6.5GB |
| With Silero VAD | + Silero VAD | ~9.5GB (Silero is tiny) | 6.5GB |

All phases fit comfortably in 16GB. Concurrent inference (Whisper + Llama at the same turn) peaks around ~10-11GB; safe margin.

If capacity becomes tight: downgrade Whisper to `medium` (~1.5GB) for live; reserve `large-v3` for archival re-transcription. Acceptable quality tradeoff.

---

## Total disk footprint (cumulative)

| Phase | Disk | Cumulative |
|---|---|---|
| Today | (Llama 30GB + Whisper-large-v3 3GB) = 33GB | 33GB |
| Phase 5 punctuator | +1.4GB | 34.4GB |
| Optional Helsinki opus-mt pair | +0.6GB | 35GB |
| Optional Silero VAD | +0.002GB | 35GB |

`/mnt/c/models/hornelore/` should have ~50GB free for comfort. Confirm:
```bash
df -h /mnt/c/models/
```

---

## License audit summary

For Lorevox commercial path (if/when):

| Model | License | Commercial OK? |
|---|---|---|
| Llama-3.1-8B-Instruct | Llama 3.1 Community License | YES (with conditions; <700M MAU) |
| Whisper (any size) | MIT | YES |
| oliverguhr punctuator | MIT | YES |
| kredor punctuator | MIT | YES |
| Helsinki-NLP opus-mt | Apache 2.0 | YES |
| Silero VAD | MIT | YES |
| Coqui VITS | MPL 2.0 | YES (with attribution) |
| Seamless-M4T-v2 | CC BY-NC 4.0 | **NO** (non-commercial) |
| NLLB-200 | CC BY-NC 4.0 | **NO** (non-commercial) |
| pyannote diarization | MIT | YES |

**Skip Seamless and NLLB if Lorevox is ever commercial.** All other models in the recommended stack are commercial-friendly.

---

## Pre-download script (run once before Phase 1 build)

```bash
cd /mnt/c/Users/chris/hornelore
# Activate venv
source .venv-gpu/bin/activate

# Pre-warm Whisper-large-v3 (the only file that may not be cached)
python3 -c "
from faster_whisper import WhisperModel
print('Loading Whisper-large-v3...')
m = WhisperModel('large-v3', device='cuda', compute_type='float16')
print('Whisper-large-v3 ready')
"

# Pre-download multilingual punctuator (Phase 5 — early download is fine)
python3 -c "
from transformers import pipeline
print('Downloading punctuator...')
p = pipeline('token-classification', model='oliverguhr/fullstop-punctuation-multilang-large', aggregation_strategy='simple', device=0)
print('Punctuator ready')
"

# Verify VRAM headroom with Whisper + Llama both loaded
python3 -c "
import torch
print(f'GPU: {torch.cuda.get_device_name(0)}')
print(f'Total VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f}GB')
print(f'Currently allocated: {torch.cuda.memory_allocated(0) / 1024**3:.1f}GB')
"
```

Run once when Chris is ready to start Phase 1. After the first download, all subsequent loads are from local cache + offline-friendly (`HF_HUB_OFFLINE=1` already in `.env`).

---

## Notes on regional variants

Whisper auto-detects language but does not detect regional variant (Mexican vs Castilian Spanish). For higher accuracy on a specific narrator population:

- Pass `initial_prompt="<narrator background>"` to Whisper. Example: `initial_prompt="The speaker is from Mexico City. They use Mexican Spanish vocabulary."` Whisper biases its output toward that variety.
- Profile field `accent_family` on the narrator (one of: mexican / caribbean / castilian / argentinian / chilean / etc.) maps to `initial_prompt`.

Helsinki-NLP and most multilingual models are trained primarily on European Spanish (Castilian) — they handle other variants but with slightly higher error rates on idioms. For a Mexican narrator, Llama-3.1-8B is actually better at understanding regional vocabulary than dedicated translation models.

---

## What to download tonight (vs. later)

**Tonight:** nothing required if Whisper-large-v3 is already cached. Phase 1 build can start with what's there.

**Before Phase 5:** pre-download `oliverguhr/fullstop-punctuation-multilang-large` (1.4GB). One-time fetch.

**Before Phase 4 (memoir):** decide between Llama-only translation vs adding Helsinki-NLP `opus-mt-en-es` + `opus-mt-es-en` pair (600MB total). Llama-only is simpler; Helsinki adds quality + speed for high-volume export.

Everything else is optional / future.
