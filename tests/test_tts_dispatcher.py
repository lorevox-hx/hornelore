"""WO-ML-TTS-EN-ES-01 Phase 1 — TTS engine dispatcher tests.

Validates:
  - get_engine() reads LORI_TTS_ENGINE env var
  - "coqui" / "kokoro" / unset all resolve to a valid TTSEngine
  - Unknown engine names fall back to coqui with a warning
  - Engine cache works (same instance across calls)
  - reset_engine_cache() forces re-instantiation
  - CoquiEngine + KokoroEngine satisfy the TTSEngine ABC contract
  - supports_language() reflects engine capabilities

Run with:
    cd hornelore
    python -m unittest tests.test_tts_dispatcher -v

NOTE: Does NOT actually call .warm() or .synthesize() — those require
the Coqui-TTS / Kokoro pip packages installed on the test env. This
test pack only validates dispatcher logic + adapter shape.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "server", "code"))

from api.tts import (  # noqa: E402
    TTSEngine,
    TTSError,
    SynthesisResult,
    get_engine,
    list_available_engines,
)
from api.tts.dispatcher import (  # noqa: E402
    reset_engine_cache,
    current_engine_name,
    _instantiate,
)
from api.tts.coqui import CoquiEngine  # noqa: E402
from api.tts.kokoro import KokoroEngine  # noqa: E402


class _EnvManager:
    """Context-manager helper that sets LORI_TTS_ENGINE for a block
    and restores the prior value after."""

    def __init__(self, value):
        self.value = value
        self._prior = None
        self._was_set = False

    def __enter__(self):
        if "LORI_TTS_ENGINE" in os.environ:
            self._was_set = True
            self._prior = os.environ["LORI_TTS_ENGINE"]
        if self.value is None:
            os.environ.pop("LORI_TTS_ENGINE", None)
        else:
            os.environ["LORI_TTS_ENGINE"] = self.value
        reset_engine_cache()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._was_set:
            os.environ["LORI_TTS_ENGINE"] = self._prior
        else:
            os.environ.pop("LORI_TTS_ENGINE", None)
        reset_engine_cache()
        return False


class RegistryShape(unittest.TestCase):
    def test_known_engines(self):
        engines = list_available_engines()
        self.assertIn("coqui", engines)
        self.assertIn("kokoro", engines)


class DispatcherEngineSelection(unittest.TestCase):
    """LORI_TTS_ENGINE env var routing."""

    def test_unset_defaults_to_coqui(self):
        with _EnvManager(None):
            engine = get_engine()
            self.assertIsInstance(engine, CoquiEngine)
            self.assertEqual(engine.engine_name, "coqui")
            self.assertEqual(current_engine_name(), "coqui")

    def test_explicit_coqui(self):
        with _EnvManager("coqui"):
            engine = get_engine()
            self.assertIsInstance(engine, CoquiEngine)

    def test_explicit_kokoro(self):
        with _EnvManager("kokoro"):
            engine = get_engine()
            self.assertIsInstance(engine, KokoroEngine)
            self.assertEqual(engine.engine_name, "kokoro")
            self.assertEqual(current_engine_name(), "kokoro")

    def test_uppercase_env_value(self):
        # "KOKORO" should still resolve to kokoro (case-insensitive)
        with _EnvManager("KOKORO"):
            engine = get_engine()
            self.assertIsInstance(engine, KokoroEngine)

    def test_whitespace_env_value(self):
        with _EnvManager("  coqui  "):
            engine = get_engine()
            self.assertIsInstance(engine, CoquiEngine)

    def test_unknown_engine_falls_back_to_coqui(self):
        with _EnvManager("nonexistent_engine_xyz"):
            engine = get_engine()
            self.assertIsInstance(engine, CoquiEngine,
                                  "Unknown engine name should fall back to Coqui")

    def test_empty_env_value_falls_back_to_coqui(self):
        with _EnvManager(""):
            engine = get_engine()
            self.assertIsInstance(engine, CoquiEngine)


class EngineCache(unittest.TestCase):
    """Repeated get_engine() calls return the same instance."""

    def test_cache_returns_same_instance(self):
        with _EnvManager("coqui"):
            e1 = get_engine()
            e2 = get_engine()
            self.assertIs(e1, e2, "Dispatcher should cache the engine instance")

    def test_force_reload_creates_new_instance(self):
        with _EnvManager("coqui"):
            e1 = get_engine()
            e2 = get_engine(force_reload=True)
            self.assertIsNot(e1, e2)

    def test_reset_cache_creates_new_instance(self):
        with _EnvManager("coqui"):
            e1 = get_engine()
            reset_engine_cache()
            e2 = get_engine()
            self.assertIsNot(e1, e2)

    def test_cache_survives_env_change_without_reload(self):
        # Once cached, changing env doesn't auto-reload (operator must
        # restart or call reset_engine_cache).
        with _EnvManager("coqui"):
            e1 = get_engine()
            os.environ["LORI_TTS_ENGINE"] = "kokoro"
            e2 = get_engine()
            self.assertIs(e1, e2,
                          "Cached engine should persist across env changes")
            # Reset cleanly
            del os.environ["LORI_TTS_ENGINE"]


class CoquiContract(unittest.TestCase):
    """CoquiEngine satisfies the TTSEngine ABC."""

    def setUp(self):
        self.engine = CoquiEngine()

    def test_is_tts_engine(self):
        self.assertIsInstance(self.engine, TTSEngine)

    def test_engine_name(self):
        self.assertEqual(self.engine.engine_name, "coqui")

    def test_supports_english(self):
        self.assertTrue(self.engine.supports_language("en"))

    def test_does_not_support_spanish(self):
        # Coqui VCTK is English-only — supports_language must reflect this
        # so the dispatcher / router can warn on language mismatch.
        self.assertFalse(self.engine.supports_language("es"))

    def test_default_voice_for_english(self):
        self.assertEqual(self.engine.default_voice_for("en"), "lori")

    def test_default_voice_for_spanish_is_none(self):
        self.assertIsNone(self.engine.default_voice_for("es"))

    def test_available_voices_shape(self):
        voices = self.engine.available_voices()
        self.assertIsInstance(voices, list)
        self.assertGreater(len(voices), 0)
        for v in voices:
            self.assertIn("key", v)
            self.assertIn("language", v)
            self.assertIn("gender", v)
            self.assertIn("display_name", v)


class KokoroContract(unittest.TestCase):
    """KokoroEngine satisfies the TTSEngine ABC."""

    def setUp(self):
        self.engine = KokoroEngine()

    def test_is_tts_engine(self):
        self.assertIsInstance(self.engine, TTSEngine)

    def test_engine_name(self):
        self.assertEqual(self.engine.engine_name, "kokoro")

    def test_supports_english(self):
        self.assertTrue(self.engine.supports_language("en"))

    def test_supports_spanish(self):
        # The whole point of switching to Kokoro
        self.assertTrue(self.engine.supports_language("es"))

    def test_supports_french(self):
        self.assertTrue(self.engine.supports_language("fr"))

    def test_does_not_support_klingon(self):
        self.assertFalse(self.engine.supports_language("tlh"))

    def test_default_voice_for_english(self):
        # Default English voice ("af_heart" unless overridden via env)
        v = self.engine.default_voice_for("en")
        self.assertIsNotNone(v)
        self.assertTrue(v.startswith("af_") or v.startswith("am_"),
                        f"Expected af_* or am_* English voice; got {v!r}")

    def test_default_voice_for_spanish(self):
        # Default Spanish voice ("ef_dora" unless overridden via env)
        v = self.engine.default_voice_for("es")
        self.assertIsNotNone(v)
        self.assertTrue(v.startswith("ef_") or v.startswith("em_"),
                        f"Expected ef_* or em_* Spanish voice; got {v!r}")

    def test_unsupported_language_default_voice_is_none(self):
        # Klingon — return None for default voice
        self.assertIsNone(self.engine.default_voice_for("tlh"))

    def test_available_voices_includes_spanish(self):
        voices = self.engine.available_voices()
        en_voices = [v for v in voices if v["language"] == "en"]
        es_voices = [v for v in voices if v["language"] == "es"]
        self.assertGreater(len(en_voices), 0)
        self.assertGreater(len(es_voices), 0,
                           "Kokoro voice catalog must include Spanish")

    def test_synthesize_empty_text_raises(self):
        with self.assertRaises(TTSError):
            self.engine.synthesize("")
        with self.assertRaises(TTSError):
            self.engine.synthesize("   ")

    def test_synthesize_unknown_language_raises(self):
        # Klingon is not in our lang map
        with self.assertRaises(TTSError) as ctx:
            self.engine.synthesize("hello", language="tlh")
        self.assertIn("language", str(ctx.exception).lower())


class SynthesisResultShape(unittest.TestCase):
    """Defensive — the dataclass field set is locked."""

    def test_required_fields(self):
        r = SynthesisResult(wav_bytes=b"ABC")
        self.assertEqual(r.wav_bytes, b"ABC")
        self.assertEqual(r.samplerate, 22050)
        self.assertEqual(r.voice, "")
        self.assertEqual(r.language, "en")
        self.assertEqual(r.engine, "")
        self.assertEqual(r.duration_sec, 0.0)
        self.assertEqual(r.extra, {})


class InstantiateHelper(unittest.TestCase):
    """_instantiate is the core of the dispatcher."""

    def test_instantiate_coqui(self):
        e = _instantiate("coqui")
        self.assertIsInstance(e, CoquiEngine)

    def test_instantiate_kokoro(self):
        e = _instantiate("kokoro")
        self.assertIsInstance(e, KokoroEngine)

    def test_instantiate_unknown_raises(self):
        with self.assertRaises(TTSError):
            _instantiate("nonexistent_engine_xyz")

    def test_instantiate_empty_defaults_to_coqui(self):
        # _instantiate with empty string returns coqui (per dispatcher
        # contract — empty value is "default to coqui")
        e = _instantiate("")
        self.assertIsInstance(e, CoquiEngine)


if __name__ == "__main__":
    unittest.main(verbosity=2)
