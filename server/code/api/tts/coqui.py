"""Coqui VCTK VITS engine — wraps the existing port-8001 TTS path.

This is the DEFAULT engine when LORI_TTS_ENGINE is unset / "coqui".
Behavior is byte-stable with the pre-WO-ML-TTS-EN-ES-01 router code:
same model (`tts_models/en/vctk/vits`), same speaker selection (p335
for "lori"), same WAV samplerate (22050).

English-only. supports_language("es") returns False. Spanish narrators
still get speech via this engine when the dispatcher falls back, but
the output is English-phonetics speaking Spanish words — generally
unintelligible. The proper fix is to switch the engine to "kokoro"
for Spanish narrators (see kokoro.py).
"""
from __future__ import annotations

import logging
import os
from io import BytesIO
from typing import Dict, List, Optional

from .base import SynthesisResult, TTSEngine, TTSError

logger = logging.getLogger(__name__)


class CoquiEngine(TTSEngine):
    """Coqui-TTS VCTK VITS — current production English voice."""

    engine_name = "coqui"

    def __init__(self) -> None:
        self._tts = None
        self._model_name = os.getenv("TTS_MODEL", "tts_models/en/vctk/vits")
        self._gpu = os.getenv("TTS_GPU", "0").strip().lower() in ("1", "true", "yes", "y")

    def _speaker_for(self, key: Optional[str]) -> str:
        k = (key or "lori").strip().lower()
        if k == "lori":
            return os.getenv("TTS_SPEAKER_LORI", "p335")
        return os.getenv("TTS_SPEAKER_LORI", "p335")

    def warm(self) -> None:
        if self._tts is not None:
            return
        try:
            from TTS.api import TTS  # type: ignore
        except Exception as exc:
            raise TTSError(f"Coqui TTS package not installed: {exc!r}")
        try:
            self._tts = TTS(model_name=self._model_name, progress_bar=False, gpu=self._gpu)
        except Exception as exc:
            raise TTSError(f"Coqui model load failed: {exc!r}")
        logger.info("[tts][coqui] warmed model=%s gpu=%s", self._model_name, self._gpu)

    def synthesize(
        self,
        text: str,
        *,
        language: str = "en",
        voice: Optional[str] = None,
    ) -> SynthesisResult:
        if not text or not text.strip():
            raise TTSError("text is required")
        # Coqui VCTK VITS is English-only. Synthesizing Spanish text
        # produces English-phonetics output (unintelligible). Log the
        # mismatch but proceed — the dispatcher should have caught
        # this; this is defensive.
        if language and language != "en":
            logger.warning(
                "[tts][coqui] language=%s requested but Coqui is English-only "
                "— output will be English phonetics speaking %s text",
                language, language,
            )

        if self._tts is None:
            self.warm()

        try:
            import numpy as np  # type: ignore
            import soundfile as sf  # type: ignore
        except Exception as exc:
            raise TTSError(f"numpy/soundfile not installed: {exc!r}")

        speaker = self._speaker_for(voice)
        try:
            wav = self._tts.tts(text=text, speaker=speaker)
        except Exception as exc:
            raise TTSError(f"Coqui synthesis failed: {exc!r}")

        bio = BytesIO()
        try:
            sf.write(bio, np.array(wav), samplerate=22050, format="WAV")
        except Exception as exc:
            raise TTSError(f"WAV encoding failed: {exc!r}")
        wav_bytes = bio.getvalue()

        # Compute duration from sample count for telemetry.
        try:
            duration = float(len(wav)) / 22050.0
        except Exception:
            duration = 0.0

        return SynthesisResult(
            wav_bytes=wav_bytes,
            samplerate=22050,
            voice=speaker,
            language="en",
            engine="coqui",
            duration_sec=duration,
        )

    def available_voices(self) -> List[Dict[str, str]]:
        # Coqui VCTK has 100+ speakers; we expose only "lori" → p335
        # to keep the narrator-facing voice catalog small.
        return [
            {
                "key": "lori",
                "language": "en",
                "gender": "female",
                "display_name": self._speaker_for("lori"),
            }
        ]

    def supports_language(self, language: str) -> bool:
        return (language or "").strip().lower() == "en"

    def default_voice_for(self, language: str) -> Optional[str]:
        if (language or "").strip().lower() == "en":
            return "lori"
        return None
