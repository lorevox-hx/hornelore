"""Kokoro-82M engine — Apache 2.0 multilingual TTS.

Source: https://github.com/hexgrad/kokoro / pip install kokoro
Model: ~82M params; Apache 2.0; on-device CPU or GPU.

Lang codes accepted by KPipeline (per Kokoro docs):
  'a' — American English
  'b' — British English
  'e' — Spanish
  'f' — French
  'h' — Hindi
  'i' — Italian
  'j' — Japanese (requires misaki[ja])
  'p' — Brazilian Portuguese
  'z' — Mandarin Chinese (requires misaki[zh])

Voice keys (sample, not exhaustive — see Kokoro repo for full list):
  English (lang_code='a'):
    af_heart, af_bella, af_alloy, af_nova, af_sarah, af_sky, af_jessica
    am_adam, am_michael, am_eric, am_liam, am_onyx, am_puck
  Spanish (lang_code='e'):
    ef_dora, em_alex, em_santa

Default voices are configurable via env:
  LORI_TTS_KOKORO_VOICE_EN=af_heart   (warm female English)
  LORI_TTS_KOKORO_VOICE_ES=ef_dora    (warm female Spanish)

System-level prerequisite for non-English: `espeak-ng` installed
(used by phonemizer for grapheme-to-phoneme on Spanish/French/etc.).
English path uses misaki internally and does NOT require espeak-ng.

Defensive imports — if `kokoro` isn't installed, the engine raises
TTSError on warm() with a clear install hint instead of crashing
the whole TTS service. Coqui remains the default; users opting into
Kokoro via LORI_TTS_ENGINE=kokoro know they need to pip install.
"""
from __future__ import annotations

import logging
import os
from io import BytesIO
from typing import Dict, List, Optional

from .base import SynthesisResult, TTSEngine, TTSError

logger = logging.getLogger(__name__)


# Map ISO 639-1 language → Kokoro KPipeline lang_code.
_LANG_TO_KOKORO: Dict[str, str] = {
    "en": "a",   # American English (default; "b" for British via env override)
    "es": "e",   # Spanish
    "fr": "f",   # French
    "hi": "h",   # Hindi
    "it": "i",   # Italian
    "ja": "j",   # Japanese (extra deps)
    "pt": "p",   # Brazilian Portuguese
    "zh": "z",   # Mandarin (extra deps)
}

_DEFAULT_VOICE_EN = os.getenv("LORI_TTS_KOKORO_VOICE_EN", "af_heart")
_DEFAULT_VOICE_ES = os.getenv("LORI_TTS_KOKORO_VOICE_ES", "ef_dora")
_DEFAULT_VOICE_BY_LANG: Dict[str, str] = {
    "en": _DEFAULT_VOICE_EN,
    "es": _DEFAULT_VOICE_ES,
    "fr": "ff_siwis",      # placeholder until bakeoff
    "it": "if_sara",       # placeholder until bakeoff
    "pt": "pf_dora",       # placeholder until bakeoff
}

# Kokoro samplerate is 24000 Hz (per README).
_KOKORO_SAMPLERATE = 24000


class KokoroEngine(TTSEngine):
    """Kokoro KPipeline wrapper.

    One pipeline per language is cached lazily. Switching narrator
    languages mid-session re-uses cached pipelines instead of
    re-loading.
    """

    engine_name = "kokoro"

    def __init__(self) -> None:
        # Per-language pipeline cache: { "a": KPipeline, "e": KPipeline, ... }
        self._pipelines: Dict[str, object] = {}
        self._warm_done = False

    def _kpipeline_for(self, kokoro_lang_code: str):
        """Lazily load + cache KPipeline for the given Kokoro lang_code."""
        if kokoro_lang_code in self._pipelines:
            return self._pipelines[kokoro_lang_code]
        try:
            from kokoro import KPipeline  # type: ignore
        except Exception as exc:
            raise TTSError(
                f"Kokoro package not installed: {exc!r}. "
                "Install with: pip install kokoro phonemizer  +  apt-get install espeak-ng"
            )
        try:
            pipeline = KPipeline(lang_code=kokoro_lang_code)
        except Exception as exc:
            raise TTSError(
                f"Kokoro KPipeline init failed for lang_code={kokoro_lang_code}: {exc!r}"
            )
        self._pipelines[kokoro_lang_code] = pipeline
        logger.info("[tts][kokoro] loaded pipeline lang_code=%s", kokoro_lang_code)
        return pipeline

    def warm(self) -> None:
        """Preload the English pipeline only — Spanish loads on first
        Spanish synthesis. Avoids paying the espeak-ng startup cost
        on services that never see a Spanish narrator."""
        if self._warm_done:
            return
        try:
            self._kpipeline_for("a")
            self._warm_done = True
            logger.info("[tts][kokoro] warmed (English pipeline)")
        except TTSError:
            # Re-raise — caller decides whether to fall back to Coqui.
            raise

    def synthesize(
        self,
        text: str,
        *,
        language: str = "en",
        voice: Optional[str] = None,
    ) -> SynthesisResult:
        if not text or not text.strip():
            raise TTSError("text is required")

        lang = (language or "en").strip().lower()
        kokoro_lang = _LANG_TO_KOKORO.get(lang)
        if not kokoro_lang:
            raise TTSError(
                f"Kokoro doesn't support language={lang!r}. "
                f"Supported: {sorted(_LANG_TO_KOKORO.keys())}"
            )

        # Resolve voice: caller-provided > per-language default > engine default.
        # If voice is provided but isn't a known Kokoro voice key (e.g. "lori"
        # from Coqui-default callers, or any FE that hardcodes a voice name),
        # fall back to per-language default. This prevents
        #   LocalEntryNotFoundError('lori.pt')
        # when the live TTS service receives a Coqui-shaped request body.
        _known_keys = {v["key"] for v in self.available_voices()}
        if not voice or voice not in _known_keys:
            voice = _DEFAULT_VOICE_BY_LANG.get(lang) or _DEFAULT_VOICE_EN

        pipeline = self._kpipeline_for(kokoro_lang)

        # Kokoro yields (graphemes, phonemes, audio_chunk) tuples per
        # sentence-shaped chunk. Concatenate the audio across chunks.
        try:
            import numpy as np  # type: ignore
        except Exception as exc:
            raise TTSError(f"numpy not installed: {exc!r}")

        try:
            chunks = list(pipeline(text, voice=voice))
        except Exception as exc:
            raise TTSError(
                f"Kokoro synthesis failed (voice={voice} lang={lang}): {exc!r}"
            )

        if not chunks:
            raise TTSError(
                f"Kokoro returned no audio chunks for text={text[:60]!r}"
            )

        # Each chunk's audio is a numpy array OR torch tensor.
        # Kokoro 0.9.x yields KPipeline.Result objects with public attrs
        # (.audio, .graphemes, .phonemes, .output, .pred_dur, .text_index,
        # .tokens). Pre-0.9 yielded plain (graphemes, phonemes, audio)
        # tuples. Verified shape live on 0.9.4 MAG-Chris 2026-05-07.
        # Try .audio first, then .output, then the legacy tuple position.
        audio_arrays = []
        for chunk in chunks:
            try:
                audio = getattr(chunk, "audio", None)
                if audio is None:
                    audio = getattr(chunk, "output", None)
                if audio is None:
                    # Pre-0.9 tuple fallback
                    try:
                        audio = chunk[2] if len(chunk) >= 3 else chunk
                    except (TypeError, AttributeError):
                        audio = chunk
                # Coerce torch.Tensor → np.ndarray if needed
                if hasattr(audio, "detach"):
                    audio = audio.detach().cpu().numpy()
                audio_arrays.append(np.asarray(audio, dtype=np.float32))
            except Exception as exc:
                logger.warning(
                    "[tts][kokoro] chunk decode failed: %s", exc
                )
                continue

        if not audio_arrays:
            raise TTSError("Kokoro produced chunks but none decoded to audio")

        full_audio = np.concatenate(audio_arrays)

        try:
            import soundfile as sf  # type: ignore
        except Exception as exc:
            raise TTSError(f"soundfile not installed: {exc!r}")

        bio = BytesIO()
        try:
            sf.write(bio, full_audio, samplerate=_KOKORO_SAMPLERATE, format="WAV")
        except Exception as exc:
            raise TTSError(f"WAV encoding failed: {exc!r}")
        wav_bytes = bio.getvalue()

        try:
            duration = float(len(full_audio)) / _KOKORO_SAMPLERATE
        except Exception:
            duration = 0.0

        return SynthesisResult(
            wav_bytes=wav_bytes,
            samplerate=_KOKORO_SAMPLERATE,
            voice=voice,
            language=lang,
            engine="kokoro",
            duration_sec=duration,
            extra={"kokoro_lang_code": kokoro_lang},
        )

    def available_voices(self) -> List[Dict[str, str]]:
        # Curated subset — full list is in the Kokoro repo. Operators
        # can override per-language defaults via LORI_TTS_KOKORO_VOICE_*
        # env vars.
        return [
            # English (American)
            {"key": "af_heart", "language": "en", "gender": "female", "display_name": "Heart"},
            {"key": "af_bella", "language": "en", "gender": "female", "display_name": "Bella"},
            {"key": "af_nova", "language": "en", "gender": "female", "display_name": "Nova"},
            {"key": "af_sarah", "language": "en", "gender": "female", "display_name": "Sarah"},
            {"key": "am_michael", "language": "en", "gender": "male", "display_name": "Michael"},
            {"key": "am_eric", "language": "en", "gender": "male", "display_name": "Eric"},
            # Spanish
            {"key": "ef_dora", "language": "es", "gender": "female", "display_name": "Dora"},
            {"key": "em_alex", "language": "es", "gender": "male", "display_name": "Alex"},
            {"key": "em_santa", "language": "es", "gender": "male", "display_name": "Santa"},
        ]

    def supports_language(self, language: str) -> bool:
        lc = (language or "").strip().lower()
        return lc in _LANG_TO_KOKORO

    def default_voice_for(self, language: str) -> Optional[str]:
        lc = (language or "").strip().lower()
        return _DEFAULT_VOICE_BY_LANG.get(lc)
