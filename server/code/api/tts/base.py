"""TTS engine base ABC.

Every engine adapter must implement:
  - warm()                 — preload model weights / phonemizer / etc.
  - synthesize(...)        — produce WAV bytes
  - available_voices()     — return list of {key, language, gender, ...}
  - supports_language(lc)  — return True if engine can synthesize lc

All engines return WAV bytes (not raw float32) to keep the HTTP path
identical regardless of engine. Caller decodes via soundfile if it
needs the float audio.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional


class TTSError(Exception):
    """Raised by any engine when synthesis cannot proceed (model
    missing, language unsupported, voice unknown, etc.). Routers
    should map to HTTP 500 with the exception message."""


@dataclass
class SynthesisResult:
    """Synthesis output. wav_bytes is a complete WAV file (header +
    samples) that can be written directly to disk OR base64-encoded
    for the existing /api/tts/speak_stream route."""

    wav_bytes: bytes
    samplerate: int = 22050
    voice: str = ""
    language: str = "en"
    engine: str = ""
    duration_sec: float = 0.0
    extra: Dict[str, object] = field(default_factory=dict)


class TTSEngine(ABC):
    """Adapter contract every engine must satisfy."""

    # Human-readable engine name (used in [tts] log markers, errors).
    engine_name: str = "abstract"

    @abstractmethod
    def warm(self) -> None:
        """Preload the model weights / phonemizer / voice presets so
        the first synthesize() call is fast. Idempotent — calling
        twice is a no-op."""

    @abstractmethod
    def synthesize(
        self,
        text: str,
        *,
        language: str = "en",
        voice: Optional[str] = None,
    ) -> SynthesisResult:
        """Synthesize text into WAV bytes.

        Args:
            text:     narrator-facing text to speak (UTF-8)
            language: ISO 639-1 code ("en" / "es" / "fr" / etc.)
            voice:    engine-specific voice key; None → engine default
                      for the requested language

        Raises:
            TTSError: when the engine cannot synthesize (unsupported
                language, missing voice, model not loaded, etc.)
        """

    @abstractmethod
    def available_voices(self) -> List[Dict[str, str]]:
        """Return list of voice metadata dicts:
          [{"key": "af_heart", "language": "en", "gender": "female",
            "display_name": "Heart"}, ...]
        """

    @abstractmethod
    def supports_language(self, language: str) -> bool:
        """Return True if `language` (ISO 639-1) is supported by this
        engine's currently-loaded models."""

    def default_voice_for(self, language: str) -> Optional[str]:
        """Return the engine's default voice key for `language`, or
        None if the engine has no preference / language unsupported.
        Default impl returns None — engines override."""
        return None
