"""TTS router — port-8001 service surface.

WO-ML-TTS-EN-ES-01 (2026-05-07): refactored to use the pluggable
engine dispatcher (api.tts package). Default behavior unchanged when
LORI_TTS_ENGINE is unset / "coqui" — same VCTK VITS, same speaker
p335, same 22050 Hz WAV output.

Set LORI_TTS_ENGINE=kokoro to switch to Kokoro multilingual (en + es
+ 6 others). Requires `pip install kokoro phonemizer` and `apt-get
install espeak-ng` (for non-English languages).

Request shape additions:
  - `language`: ISO 639-1 (default "en"); routed to engine.synthesize
  - `voice`: now engine-specific (Coqui: "lori"; Kokoro: "af_heart" / "ef_dora" / etc.)
"""
from __future__ import annotations
import base64
import json
import logging
import os
from typing import Any, Dict
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..tts import TTSError, get_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tts", tags=["tts"])


def warm():
    """Module-level warm hook called by tts_service.py startup. Picks
    up the engine via the dispatcher and warms it. Failure is logged
    but non-fatal — first /speak_stream call retries via lazy load."""
    try:
        engine = get_engine()
        engine.warm()
        logger.info("[tts] warmed engine=%s", engine.engine_name)
    except TTSError as exc:
        logger.warning("[tts] warm skipped/failed: %s", exc)
    except Exception as exc:
        logger.warning("[tts] warm unexpected error: %s", exc)


@router.get("/voices")
def voices():
    """List voices available from the currently-selected engine."""
    try:
        engine = get_engine()
        return {
            "ok": True,
            "engine": engine.engine_name,
            "voices": engine.available_voices(),
        }
    except Exception as exc:
        logger.warning("[tts] /voices failed: %s", exc)
        # Defensive — never break the route
        return {"ok": False, "error": str(exc), "voices": []}


@router.get("/engine")
def engine_info():
    """Operator diagnostic — report which engine is active + supported
    languages. Lets the Bug Panel surface 'Lori is using Kokoro for ES'
    without operators having to read .env."""
    try:
        engine = get_engine()
        return {
            "ok": True,
            "engine": engine.engine_name,
            "env_value": os.environ.get("LORI_TTS_ENGINE", "(unset)"),
            "supports_en": engine.supports_language("en"),
            "supports_es": engine.supports_language("es"),
            "voice_count": len(engine.available_voices()),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.post("/speak_stream")
def speak_stream(payload: Dict[str, Any]):
    """Synthesize a chunk of narrator-facing text into WAV.

    Backward-compatible request shape:
      {"text": "...", "voice": "lori"}        — works exactly as before
      {"text": "...", "voice": "...", "language": "es"}  — Kokoro path

    Response: NDJSON line with {"wav_b64": "<base64 WAV>", "engine": "...",
                                 "voice": "...", "language": "..."}
    """
    text = (payload.get("text") or "").strip()
    voice_key = (payload.get("voice") or "lori").strip()
    language = (payload.get("language") or "en").strip().lower()

    if not text:
        raise HTTPException(400, "text is required")

    try:
        engine = get_engine()
    except Exception as exc:
        raise HTTPException(501, f"Failed to load TTS engine: {exc}")

    # If the requested language isn't supported by the active engine,
    # fall back to engine's English (or whatever default) and log it.
    # Operators see the language-mismatch in api.log to debug Spanish-
    # voice-but-Coqui-engine misconfigurations.
    if not engine.supports_language(language):
        logger.warning(
            "[tts] engine=%s does not support language=%s — synthesizing anyway "
            "(output may be unintelligible). Switch to LORI_TTS_ENGINE=kokoro for ES.",
            engine.engine_name, language,
        )

    try:
        result = engine.synthesize(text, language=language, voice=voice_key)
    except TTSError as exc:
        raise HTTPException(500, f"TTS synthesis failed: {exc}")
    except Exception as exc:
        raise HTTPException(500, f"TTS unexpected error: {exc}")

    b64 = base64.b64encode(result.wav_bytes).decode("ascii")

    def gen():
        yield json.dumps({
            "wav_b64": b64,
            "engine": result.engine,
            "voice": result.voice,
            "language": result.language,
            "samplerate": result.samplerate,
            "duration_sec": result.duration_sec,
        }) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")
