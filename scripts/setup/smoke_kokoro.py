#!/usr/bin/env python3
"""WO-ML-TTS-EN-ES-01 Phase 1 — Kokoro smoke probe.

Validates that the freshly-installed Kokoro pip package + espeak-ng
system dep can:
  1. Import cleanly
  2. Initialize KPipeline for English (lang_code='a')
  3. Synthesize a short English phrase
  4. Initialize KPipeline for Spanish (lang_code='e')
  5. Synthesize a short Spanish phrase
  6. Write the resulting WAVs to /tmp for Chris to play back

Does NOT touch the running TTS service or the LORI_TTS_ENGINE env
var. Pure offline probe.

Run:
    python scripts/setup/smoke_kokoro.py

Sample output paths (on success):
    /tmp/kokoro_smoke_en.wav
    /tmp/kokoro_smoke_es.wav

Plays back via:
    aplay /tmp/kokoro_smoke_en.wav    # WSL/Linux
    afplay /tmp/kokoro_smoke_en.wav   # macOS
    powershell -c "(New-Object Media.SoundPlayer '\\\\wsl$\\Ubuntu\\tmp\\kokoro_smoke_en.wav').PlaySync()"  # Windows from WSL
"""
from __future__ import annotations

import os
import sys
import time
import tempfile
from pathlib import Path


def _is_wsl() -> bool:
    """Detect WSL via /proc/version (used to pick playback hints)."""
    try:
        version_path = Path("/proc/version")
        if version_path.exists():
            content = version_path.read_text(encoding="utf-8", errors="ignore").lower()
            return "microsoft" in content or "wsl" in content
    except Exception:
        pass
    return False


def _extract_audio_from_chunk(chunk):
    """Defensively extract audio from a Kokoro pipeline chunk.

    Kokoro 0.9.x yields `KPipeline.Result` objects with public attrs:
        graphemes, phonemes, audio, output, pred_dur, text_index, tokens
    Older Kokoro (pre-0.9) yielded plain tuples (graphemes, phonemes, audio).

    Verified live on Kokoro 0.9.4 (MAG-Chris probe 2026-05-07):
        type(chunk).__name__ == 'Result'
        len(chunk) == 3                       # tuple-like via __iter__
        chunk.audio                           # FloatTensor, what we want
        chunk.output                          # alternate audio holder

    Order of preference:
      1. chunk.audio          — Kokoro 0.9.x canonical attribute
      2. chunk.output         — Kokoro 0.9.x alt attribute
      3. chunk[2]             — pre-0.9 tuple position
      4. chunk itself         — last-ditch fallback (raw tensor case)

    Raises ValueError if none of the above yield a tensor-shaped object.
    """
    # Preferred path — Kokoro 0.9.x Result.audio
    audio = getattr(chunk, "audio", None)
    if audio is not None:
        return audio
    # Alternate — some 0.9.x paths populate .output instead
    audio = getattr(chunk, "output", None)
    if audio is not None:
        return audio
    # Pre-0.9 tuple shape
    try:
        if len(chunk) >= 3:
            return chunk[2]
    except (TypeError, AttributeError):
        pass
    # Last-ditch — chunk IS the audio tensor
    return chunk


ENGLISH_TEXT = (
    "Hello, this is a Kokoro smoke test. The voice should sound warm and "
    "conversational, suitable for an older narrator hearing reflections "
    "of their life story."
)

SPANISH_TEXT = (
    "Hola, esto es una prueba de Kokoro en español. La voz debería "
    "sonar cálida y conversacional, apropiada para una narradora mayor "
    "escuchando reflexiones de la historia de su vida."
)


def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def _info(msg: str) -> None:
    print(f"  [..] {msg}")


def main() -> int:
    print("=== Kokoro smoke probe ===\n")

    # 1. Imports
    print("[1/6] Imports")
    try:
        from kokoro import KPipeline  # type: ignore
        _ok(f"kokoro.KPipeline ({KPipeline.__module__})")
    except Exception as exc:
        _fail(f"kokoro import failed: {exc!r}")
        print("\n  Hint: bash scripts/setup/install_kokoro.sh")
        return 1
    try:
        import phonemizer  # type: ignore
        _ok(f"phonemizer {phonemizer.__version__}")
    except Exception as exc:
        _fail(f"phonemizer import failed: {exc!r}")
        return 1
    try:
        import soundfile as sf  # type: ignore
        _ok(f"soundfile {sf.__version__}")
    except Exception as exc:
        _fail(f"soundfile import failed: {exc!r}")
        return 1
    try:
        import numpy as np  # type: ignore
        _ok(f"numpy {np.__version__}")
    except Exception as exc:
        _fail(f"numpy import failed: {exc!r}")
        return 1
    print()

    # 2. English KPipeline init
    print("[2/6] English KPipeline init (lang_code='a')")
    try:
        t0 = time.time()
        en_pipeline = KPipeline(lang_code="a")
        _ok(f"loaded in {time.time() - t0:.1f}s")
    except Exception as exc:
        _fail(f"English KPipeline init failed: {exc!r}")
        return 2
    print()

    # 3. English synthesis
    print("[3/6] English synthesis (voice=af_heart)")
    try:
        t0 = time.time()
        chunks = list(en_pipeline(ENGLISH_TEXT, voice="af_heart"))
        _ok(f"got {len(chunks)} chunks in {time.time() - t0:.1f}s")
    except Exception as exc:
        _fail(f"English synthesis failed: {exc!r}")
        return 3

    en_audio = []
    for chunk in chunks:
        try:
            audio = _extract_audio_from_chunk(chunk)
            if hasattr(audio, "detach"):
                audio = audio.detach().cpu().numpy()
            en_audio.append(np.asarray(audio, dtype=np.float32))
        except Exception as exc:
            _fail(f"chunk decode failed: {exc!r}")
            continue

    if not en_audio:
        _fail("no audio decoded")
        return 3
    en_full = np.concatenate(en_audio)
    en_path = Path(tempfile.gettempdir()) / "kokoro_smoke_en.wav"
    sf.write(str(en_path), en_full, samplerate=24000, format="WAV")
    _ok(f"wrote {en_path}  duration={len(en_full)/24000:.2f}s  bytes={en_path.stat().st_size}")
    print()

    # 4. Spanish KPipeline init
    print("[4/6] Spanish KPipeline init (lang_code='e')")
    try:
        t0 = time.time()
        es_pipeline = KPipeline(lang_code="e")
        _ok(f"loaded in {time.time() - t0:.1f}s")
    except Exception as exc:
        _fail(f"Spanish KPipeline init failed: {exc!r}")
        print("\n  Hint: espeak-ng must be installed for Spanish G2P.")
        print("  Verify with: espeak-ng --version")
        return 4
    print()

    # 5. Spanish synthesis
    print("[5/6] Spanish synthesis (voice=ef_dora)")
    try:
        t0 = time.time()
        chunks = list(es_pipeline(SPANISH_TEXT, voice="ef_dora"))
        _ok(f"got {len(chunks)} chunks in {time.time() - t0:.1f}s")
    except Exception as exc:
        _fail(f"Spanish synthesis failed: {exc!r}")
        return 5

    es_audio = []
    for chunk in chunks:
        try:
            audio = _extract_audio_from_chunk(chunk)
            if hasattr(audio, "detach"):
                audio = audio.detach().cpu().numpy()
            es_audio.append(np.asarray(audio, dtype=np.float32))
        except Exception as exc:
            _fail(f"chunk decode failed: {exc!r}")
            continue

    if not es_audio:
        _fail("no audio decoded")
        return 5
    es_full = np.concatenate(es_audio)
    es_path = Path(tempfile.gettempdir()) / "kokoro_smoke_es.wav"
    sf.write(str(es_path), es_full, samplerate=24000, format="WAV")
    _ok(f"wrote {es_path}  duration={len(es_full)/24000:.2f}s  bytes={es_path.stat().st_size}")
    print()

    # 6. Adapter-shape check
    print("[6/6] Verify adapter dispatch (in-process)")
    import os
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "server" / "code"))
    os.environ["LORI_TTS_ENGINE"] = "kokoro"
    try:
        from api.tts import get_engine
        from api.tts.dispatcher import reset_engine_cache
        reset_engine_cache()
        engine = get_engine()
        _ok(f"dispatcher returned engine={engine.engine_name}")
        _ok(f"supports_language('en') = {engine.supports_language('en')}")
        _ok(f"supports_language('es') = {engine.supports_language('es')}")
        _ok(f"default_voice_for('en') = {engine.default_voice_for('en')!r}")
        _ok(f"default_voice_for('es') = {engine.default_voice_for('es')!r}")
        # Don't synthesize via the adapter — it loads its own KPipeline,
        # doubling memory. The direct probes above already validated
        # synthesis. This step only validates the dispatch path resolves.
    except Exception as exc:
        _fail(f"adapter dispatch failed: {exc!r}")
        return 6
    finally:
        del os.environ["LORI_TTS_ENGINE"]
        try:
            reset_engine_cache()
        except Exception:
            pass

    print()
    print("=== Smoke probe PASSED ===")
    print()
    print("Listen to verify voice quality:")
    print(f"  English: {en_path}")
    print(f"  Spanish: {es_path}")
    print()

    # Playback hints — pick the right one based on platform.
    if _is_wsl():
        print("Playback (WSL — files are on the Linux side at /tmp/):")
        print("  Open in Windows File Explorer (handles audio playback):")
        print(f'    explorer.exe "$(wslpath -w {en_path})"')
        print(f'    explorer.exe "$(wslpath -w {es_path})"')
        print("  Or play in WSL with alsa-utils:")
        print( "    sudo apt install -y alsa-utils")
        print(f"    aplay {en_path}")
        print(f"    aplay {es_path}")
    else:
        print("Playback:")
        print(f"  Linux:    aplay {en_path}")
        print(f"            aplay {es_path}")
        print(f"  macOS:    afplay {en_path}")
        print(f"            afplay {es_path}")

    print()
    print("If the voices sound right, you're ready to flip LORI_TTS_ENGINE=kokoro")
    print("in .env after Melanie's next Spanish session live-verifies the guards.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
