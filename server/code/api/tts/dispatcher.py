"""LORI_TTS_ENGINE dispatcher.

Reads the LORI_TTS_ENGINE env var on first call, instantiates the
matching adapter once, and caches it for the process lifetime.

Falls back to Coqui (default) when:
  - LORI_TTS_ENGINE is unset
  - LORI_TTS_ENGINE value is unrecognized (logs warning)

Caller pattern:
    from api.tts import get_engine
    engine = get_engine()
    result = engine.synthesize(text, language="es", voice=None)
    wav_bytes = result.wav_bytes
"""
from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional

from .base import TTSEngine, TTSError

logger = logging.getLogger(__name__)

_ENGINE_INSTANCE: Optional[TTSEngine] = None
_ENGINE_NAME_USED: Optional[str] = None

_ENGINE_REGISTRY = {
    "coqui": "coqui",
    "kokoro": "kokoro",
    # Reserved for future bakeoff:
    # "melotts": "melotts",
    # "piper":   "piper",
    # "parler":  "parler",
}


def list_available_engines() -> List[str]:
    """Return the engine names this build knows how to dispatch to.
    Does NOT verify that each engine's pip dependencies are installed
    — only that the adapter module is importable."""
    return sorted(_ENGINE_REGISTRY.keys())


def _instantiate(engine_name: str) -> TTSEngine:
    """Build a fresh adapter instance for `engine_name`. Lazy-imports
    the engine module so unselected engines don't pay their import
    cost (Kokoro pulls torch + phonemizer which is heavy)."""
    name = (engine_name or "").strip().lower()
    if name == "coqui" or name == "":
        from .coqui import CoquiEngine
        return CoquiEngine()
    if name == "kokoro":
        from .kokoro import KokoroEngine
        return KokoroEngine()
    # Future engines:
    # if name == "melotts":
    #     from .melotts import MeloTTSEngine
    #     return MeloTTSEngine()
    # if name == "piper":
    #     from .piper import PiperEngine
    #     return PiperEngine()
    raise TTSError(
        f"Unknown LORI_TTS_ENGINE={engine_name!r}. "
        f"Known engines: {list_available_engines()}"
    )


def get_engine(force_reload: bool = False) -> TTSEngine:
    """Return the configured TTS engine adapter (cached).

    Args:
        force_reload: when True, discard cached engine and re-instantiate.
                      Used by tests + potential operator hot-reload path.

    Reads LORI_TTS_ENGINE on cache miss. Falls back to "coqui" on
    unset/unknown values (with a warning log).
    """
    global _ENGINE_INSTANCE, _ENGINE_NAME_USED

    if _ENGINE_INSTANCE is not None and not force_reload:
        return _ENGINE_INSTANCE

    requested = (os.environ.get("LORI_TTS_ENGINE") or "coqui").strip().lower()

    try:
        engine = _instantiate(requested)
    except TTSError as exc:
        # Unknown engine name — fall back to coqui with a clear warning
        logger.warning(
            "[tts][dispatcher] %s — falling back to Coqui (default)",
            exc,
        )
        engine = _instantiate("coqui")
        requested = "coqui"

    _ENGINE_INSTANCE = engine
    _ENGINE_NAME_USED = requested
    logger.info(
        "[tts][dispatcher] engine=%s instantiated (LORI_TTS_ENGINE=%s)",
        engine.engine_name, os.environ.get("LORI_TTS_ENGINE", "(unset)"),
    )
    return engine


def reset_engine_cache() -> None:
    """Clear the cached engine. Used by tests + operator restart paths.
    Next get_engine() call re-reads LORI_TTS_ENGINE."""
    global _ENGINE_INSTANCE, _ENGINE_NAME_USED
    _ENGINE_INSTANCE = None
    _ENGINE_NAME_USED = None


def current_engine_name() -> Optional[str]:
    """Return the name of the currently-cached engine, or None if not
    yet instantiated. Diagnostic-only."""
    return _ENGINE_NAME_USED
