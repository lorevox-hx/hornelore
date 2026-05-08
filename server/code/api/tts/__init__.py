"""WO-ML-TTS-EN-ES-01 — pluggable TTS engine adapter.

Engine selection via LORI_TTS_ENGINE env var:
  - "coqui"  (default) — existing English-only Coqui VCTK VITS
  - "kokoro"           — Apache 2.0 multilingual (en + es + 6 others)
  - "melotts", "piper", "parler" — reserved for future bakeoff

Public surface:
    from api.tts import get_engine, TTSEngine
    engine = get_engine()  # reads LORI_TTS_ENGINE
    wav_bytes = engine.synthesize(text, language="es", voice="ef_dora")

The dispatcher is lazy — engine modules are not imported until
selected. This keeps the Coqui-default path byte-stable for installs
that don't have Kokoro / espeak-ng / phonemizer dependencies on the
TTS service Python env.
"""
from __future__ import annotations

from .base import TTSEngine, TTSError, SynthesisResult
from .dispatcher import get_engine, list_available_engines

__all__ = [
    "TTSEngine",
    "TTSError",
    "SynthesisResult",
    "get_engine",
    "list_available_engines",
]
