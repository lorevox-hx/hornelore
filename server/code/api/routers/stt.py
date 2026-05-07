"""
STT router — local Whisper transcription.
POST /api/stt/transcribe   (multipart: file=<audio blob>, lang=en, initial_prompt="")
GET  /api/stt/status       (engine health)

Tries faster-whisper first, falls back to openai-whisper.
Model size and device controlled by env vars:

  STT_MODEL          default "medium"    (e.g. "large-v3" for best accuracy)
  STT_GPU            default "0"         set "1" to run on CUDA (matches .env pattern)
  STT_DEVICE         optional override   "cuda" or "cpu" (takes priority over STT_GPU)
  STT_COMPUTE        default auto        "float16" on CUDA, "int8" on CPU
"""
from __future__ import annotations

import math
import os
import pathlib
import shutil
import tempfile

import torch
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

router = APIRouter(prefix="/api/stt", tags=["stt"])

_engine = None
_engine_kind: str | None = None


def _resolve_device() -> str:
    """Resolve STT device from env vars.
    Priority: STT_DEVICE > STT_GPU > cpu fallback.
    """
    explicit = os.getenv("STT_DEVICE", "").strip().lower()
    if explicit in ("cuda", "cpu"):
        device = explicit
    else:
        gpu_flag = os.getenv("STT_GPU", "0").strip().lower() in ("1", "true", "yes", "y")
        device = "cuda" if gpu_flag else "cpu"

    # Safety: downgrade to CPU if CUDA requested but unavailable
    if device == "cuda" and not torch.cuda.is_available():
        print("[STT] CUDA requested but unavailable — falling back to CPU")
        device = "cpu"

    return device


def _load_engine():
    global _engine, _engine_kind
    if _engine is not None:
        return _engine_kind, _engine

    model_size = os.getenv("STT_MODEL", "medium").strip() or "medium"
    device = _resolve_device()
    compute = os.getenv("STT_COMPUTE", "float16" if device == "cuda" else "int8").strip()

    # Try faster-whisper first (CUDA fp16, ~5-10× faster than openai-whisper)
    try:
        from faster_whisper import WhisperModel  # type: ignore

        _engine = WhisperModel(model_size, device=device, compute_type=compute)
        _engine_kind = "faster_whisper"
        print(f"[STT] faster-whisper: {model_size} on {device} ({compute})")
        return _engine_kind, _engine
    except ImportError:
        pass
    except Exception as e:
        print(f"[STT] faster-whisper failed ({e}), trying openai-whisper …")

    # Fall back to openai-whisper (CPU-friendly)
    try:
        import whisper  # type: ignore

        _engine = whisper.load_model(model_size)
        _engine_kind = "whisper"
        print(f"[STT] openai-whisper: {model_size}")
        return _engine_kind, _engine
    except ImportError:
        pass
    except Exception as e:
        print(f"[STT] openai-whisper failed: {e}")

    raise RuntimeError(
        "No STT engine available. "
        "Install faster-whisper (pip install faster-whisper) "
        "or openai-whisper (pip install openai-whisper)."
    )


@router.get("/status")
def stt_status():
    """Health-check: returns engine name, device, and model."""
    try:
        kind, _ = _load_engine()
        return {
            "ok": True,
            "engine": kind,
            "device": _resolve_device(),
            "model": os.getenv("STT_MODEL", "medium"),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/transcribe")
async def stt_transcribe(
    file: UploadFile = File(...),
    lang: str = Form("en"),
    initial_prompt: str = Form(""),
):
    """
    Accept a browser audio blob (webm, ogg, mp4, wav) and return transcribed text.
    Optional form fields:
      lang            language code (default "en"). Accepts ISO-639-1 codes
                      ("en", "es", "fr", ...) OR "auto" / "" to let Whisper
                      auto-detect the language. Auto-detect is required for
                      multilingual narrators and code-switching capture per
                      WO-ML-01 (the multilingual project plan).
      initial_prompt  hint to help Whisper with proper nouns / names

    Response shape (WO-ML-01 Phase 1A response contract):
      {
        "ok": true,
        "text": "<transcribed string, trimmed>",
        "language": "en|es|fr|...",         # ISO-639-1, detected by Whisper
        "language_probability": 0.0-1.0,    # null if openai-whisper fallback
        "confidence": 0.0-1.0,              # exp(weighted-mean avg_logprob); null if no segments
        "avg_logprob": -inf-0,              # raw weighted-mean log-probability; null if openai-whisper
        "duration_sec": 0.0,                # null if openai-whisper fallback
        "engine": "faster_whisper|whisper",
        "model": "<resolved STT_MODEL>"
      }

    Response is strictly additive vs the pre-WO-ML-01 shape ({ok, text}). Existing
    callers that read only `text` continue to behave byte-identically.
    """
    try:
        kind, engine = _load_engine()
    except Exception as e:
        # [ml-stt][error] engine load failed
        print(f"[ml-stt][error] engine_load_failed err={e}")
        raise HTTPException(501, f"STT engine not available: {e}")

    # Resolve language: "auto" / "" / None → faster-whisper auto-detect.
    # Anything else passes through verbatim (Whisper validates ISO codes).
    lang_in = (lang or "").strip().lower()
    auto_detect = lang_in in ("", "auto")
    resolved_lang = None if auto_detect else lang_in

    tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="stt_"))
    try:
        suffix = pathlib.Path(file.filename or "audio.webm").suffix or ".webm"
        audio_path = tmpdir / f"upload{suffix}"
        content = await file.read()
        audio_path.write_bytes(content)

        # [ml-stt][route] entry — file size + lang resolution
        print(
            f"[ml-stt][route] file={len(content)}B lang_in={lang_in or '(empty)'} "
            f"resolved_lang={resolved_lang or 'auto'}"
        )

        model_name = os.getenv("STT_MODEL", "medium").strip() or "medium"
        detected_language: str | None = None
        language_probability: float | None = None
        avg_logprob: float | None = None
        confidence: float | None = None
        duration_sec: float | None = None

        if kind == "faster_whisper":
            segments, info = engine.transcribe(
                str(audio_path),
                language=resolved_lang,           # None → auto-detect
                initial_prompt=initial_prompt or None,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
            )
            # Iterate once: collect text + duration-weighted avg_logprob.
            text_parts: list[str] = []
            logprob_weighted_sum = 0.0
            duration_total = 0.0
            for s in segments:
                text_parts.append(s.text.strip())
                seg_dur = max(0.0, float(getattr(s, "end", 0.0)) - float(getattr(s, "start", 0.0)))
                seg_logprob = getattr(s, "avg_logprob", None)
                if seg_dur > 0.0 and isinstance(seg_logprob, (int, float)):
                    logprob_weighted_sum += float(seg_logprob) * seg_dur
                    duration_total += seg_dur
            text = " ".join(text_parts).strip()

            detected_language = getattr(info, "language", None)
            lp = getattr(info, "language_probability", None)
            language_probability = float(lp) if isinstance(lp, (int, float)) else None
            d = getattr(info, "duration", None)
            duration_sec = float(d) if isinstance(d, (int, float)) else None

            if duration_total > 0.0:
                avg_logprob = logprob_weighted_sum / duration_total
                # exp(avg_logprob) maps log-prob in (-inf, 0] to probability in (0, 1].
                # Clamp to [0, 1] for safety in case of pathological segment data.
                try:
                    confidence = max(0.0, min(1.0, math.exp(avg_logprob)))
                except (OverflowError, ValueError):
                    confidence = None
        else:
            # openai-whisper fallback (CPU-friendly; less metadata available)
            result = engine.transcribe(
                str(audio_path),
                language=resolved_lang,           # None → auto-detect
                initial_prompt=initial_prompt or None,
                fp16=False,
            )
            text = (result.get("text") or "").strip()
            # openai-whisper sets `language` on the result dict; other fields
            # are not exposed by default. Leave probability/confidence as None.
            detected_language = result.get("language") or resolved_lang or None

        # [ml-stt][result] success readout
        print(
            f"[ml-stt][result] engine={kind} language={detected_language or 'unknown'} "
            f"lang_prob={language_probability if language_probability is not None else 'na'} "
            f"confidence={confidence if confidence is not None else 'na'} "
            f"duration={duration_sec if duration_sec is not None else 'na'}s "
            f"text_len={len(text)}"
        )

        return {
            "ok": True,
            "text": text,
            "language": detected_language,
            "language_probability": language_probability,
            "confidence": confidence,
            "avg_logprob": avg_logprob,
            "duration_sec": duration_sec,
            "engine": kind,
            "model": model_name,
        }

    except HTTPException:
        raise
    except Exception as e:
        # [ml-stt][error] transcription failure (post-engine-load)
        print(f"[ml-stt][error] transcribe_failed err={e}")
        raise HTTPException(500, f"Transcription failed: {e}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
