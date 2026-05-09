"""Unit tests for services/lori_response_guards.py.

Two post-LLM guards: language drift (Mary's session never had this,
but Kent's line 23 did) + dangling determiner (Mary's line 47 had
this; Kent's line 47 had this; both transcripts).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api.services import lori_response_guards as g  # noqa: E402


# ── Section 1: language drift detection ───────────────────────────────────


class LanguageDriftDetectionTest(unittest.TestCase):
    def test_kent_line_23_drift_detected(self):
        # Kent literal: said "click that and start there repeat that
        # can you" — pure English. Lori responded in Spanish.
        narrator = "click that and start there repeat that can you"
        recent = (
            "hello",
            "[SYSTEM: Adolescence selected]",  # SYSTEM directive
            "[SYSTEM: Coming of Age selected]",
        )
        assistant = (
            "Ese recuerdo de la transición de Stanley, North Dakota, "
            "tiene una sensación de cambio."
        )
        self.assertTrue(g.detect_language_drift(assistant, narrator, recent))

    def test_legitimate_spanish_response_not_flagged(self):
        # Maria spoke Spanish, Lori responded Spanish — correct mirroring
        narrator = "Hola Lori, me llamo María. ¿Qué quieres saber?"
        recent = ("Hola", "Cuando mi abuela hablaba de Perú")
        assistant = "Hola María, cuéntame más sobre tu abuela."
        self.assertFalse(g.detect_language_drift(assistant, narrator, recent))

    def test_english_response_to_english_narrator(self):
        narrator = "I went to basic training in 1957."
        assistant = "Tell me more about basic training."
        self.assertFalse(g.detect_language_drift(assistant, narrator, ()))

    def test_recent_spanish_history_blocks_drift_detection(self):
        # Even if current narrator turn is English, if recent context
        # is Spanish, Lori's Spanish response is OK (legitimate code-
        # switch session).
        narrator = "yes that's right"
        recent = ("Hola Lori", "Mi abuela hablaba de Perú")
        assistant = "Cuéntame más sobre tu abuela."
        self.assertFalse(g.detect_language_drift(assistant, narrator, recent))

    def test_empty_assistant_no_drift(self):
        self.assertFalse(g.detect_language_drift("", "hello", ()))

    def test_empty_narrator_with_spanish_assistant_drifts(self):
        # No narrator context to mirror — Spanish response is still
        # drift if recent context is empty
        assistant = "Cuéntame más sobre tu vida."
        self.assertTrue(g.detect_language_drift(assistant, "", ()))


class LanguageDriftRepairTest(unittest.TestCase):
    def test_default_english_repair(self):
        text = g.repair_language_drift("en")
        self.assertIn("English", text)
        self.assertNotIn("español", text.lower())

    def test_spanish_target_repair(self):
        text = g.repair_language_drift("es")
        self.assertIn("inglés", text)


# ── Section 2: dangling determiner detection ─────────────────────────────


class DanglingDeterminerDetectionTest(unittest.TestCase):
    def test_marys_literal_line_47(self):
        # Mary's session: "Let's go back to what you were saying about the."
        text = "Let's go back to what you were saying about the."
        self.assertTrue(g.detect_dangling_determiner(text))

    def test_ends_with_for_period(self):
        self.assertTrue(g.detect_dangling_determiner("Tell me more about it for."))

    def test_ends_with_a_period(self):
        self.assertTrue(g.detect_dangling_determiner("Were you going to a."))

    def test_ends_with_to_period(self):
        self.assertTrue(g.detect_dangling_determiner("Where did you want to."))

    def test_complete_sentence_not_flagged(self):
        self.assertFalse(g.detect_dangling_determiner(
            "Tell me more about basic training."
        ))

    def test_question_mark_not_flagged(self):
        self.assertFalse(g.detect_dangling_determiner(
            "What happened after that?"
        ))

    def test_determiner_mid_sentence_not_flagged(self):
        # "the" mid-sentence is fine
        self.assertFalse(g.detect_dangling_determiner(
            "The table was set for dinner."
        ))

    def test_empty_input_not_flagged(self):
        self.assertFalse(g.detect_dangling_determiner(""))
        self.assertFalse(g.detect_dangling_determiner(None))


class DanglingDeterminerRepairTest(unittest.TestCase):
    def test_english_repair(self):
        text = g.repair_dangling_determiner("en")
        self.assertIn("?", text)  # Should end with a question

    def test_spanish_repair(self):
        text = g.repair_dangling_determiner("es")
        self.assertIn("¿", text)


# ── Section 3: combined application ───────────────────────────────────────


class ApplyResponseGuardsTest(unittest.TestCase):
    def test_language_drift_replaces_text(self):
        narrator = "click that and start there repeat that can you"
        assistant = (
            "Ese recuerdo de la transición de Stanley, North Dakota."
        )
        final, fired = g.apply_response_guards(
            assistant, narrator, (), target_language="en",
        )
        self.assertNotEqual(final, assistant)
        self.assertIn("language_drift", fired)
        # Repaired text is English
        self.assertNotIn("Ese recuerdo", final)

    def test_dangling_determiner_replaces_text(self):
        assistant = "Let's go back to what you were saying about the."
        final, fired = g.apply_response_guards(
            assistant, "yes", (), target_language="en",
        )
        self.assertNotEqual(final, assistant)
        self.assertIn("dangling_determiner", fired)

    def test_clean_response_passes_through(self):
        assistant = "Tell me more about basic training."
        final, fired = g.apply_response_guards(
            assistant, "I served in the Army.", (),
        )
        self.assertEqual(final, assistant)
        self.assertEqual(fired, [])

    def test_language_drift_takes_priority(self):
        # Spanish assistant ending with "the." — language drift fires
        # FIRST (drift is the larger failure)
        narrator = "yes go on"
        assistant = "Estaba pensando en la cosa about the."
        final, fired = g.apply_response_guards(
            assistant, narrator, (), target_language="en",
        )
        self.assertEqual(fired, ["language_drift"])

    def test_target_language_es_repair_to_spanish(self):
        # If operator routes to Spanish target, drift repair stays
        # Spanish-friendly. Use a clearly-Spanish narrator turn (≥2
        # distinct Spanish words) so the detector recognizes session
        # context as Spanish.
        narrator = "Hola Lori, ¿cómo estás?"
        assistant = "Hola, estoy bien gracias."
        recent = (
            "Hola Lori, me llamo María",
            "Cuando mi abuela hablaba de Perú",
        )
        final, fired = g.apply_response_guards(
            assistant, narrator, recent, target_language="es",
        )
        # Legitimate Spanish — no fire
        self.assertEqual(fired, [])
        self.assertEqual(final, assistant)


if __name__ == "__main__":
    unittest.main(verbosity=2)
