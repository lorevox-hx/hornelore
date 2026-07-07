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


class FrenchAccentFalsePositiveTest(unittest.TestCase):
    """BUG-LORI-SPANISH-DETECT-OVERFIRE-FRENCH-ACCENT-01 (2026-07-02).

    2019 France/Italy canary T3: Lori's all-English reply contained
    "Trocadéro" and the single-tier accent regex flagged it as Spanish,
    firing the G3 hard clamp. French/Italian/PT accents + English
    loanwords must NOT count as Spanish on their own.
    """

    def test_trocadero_english_reply_not_spanish(self):
        # Literal 2019 T3 failure class.
        self.assertFalse(g._looks_spanish(
            "You walked from the Eiffel Tower to the Trocadéro Gardens "
            "and Palais de Chaillot. What museum came next?"
        ))

    def test_dense_french_accents_not_spanish(self):
        self.assertFalse(g._looks_spanish(
            "You mentioned Musée d'Orsay, Sacré-Cœur, and the Champs "
            "Élysées. Which did you visit first?"
        ))

    def test_english_loanword_cafe_not_spanish(self):
        self.assertFalse(g._looks_spanish(
            "We had café au lait near the Louvre."
        ))

    def test_enye_alone_still_spanish(self):
        # Unique-tier characters keep firing without any word support.
        self.assertTrue(g._looks_spanish("El niño pequeño"))

    def test_inverted_punctuation_still_spanish(self):
        self.assertTrue(g._looks_spanish("¡Qué bonito!"))

    def test_accent_plus_one_spanish_word_still_spanish(self):
        # Kent K1/K2/K10 drift class: accented vowel + ≥1 Spanish-only
        # word must still detect.
        self.assertTrue(g._looks_spanish(
            "Ese recuerdo de la transición de Stanley, North Dakota, "
            "tiene una sensación de cambio."
        ))

    def test_no_accent_two_spanish_words_still_spanish(self):
        self.assertTrue(g._looks_spanish(
            "La casa de mi familia es muy grande"
        ))

    def test_t4_live_reply_tell_me_marche_is_english(self):
        # Live 2026-07-02 T4 evidence: accent (Marché) + "me" (English
        # word present in the Spanish word list) replaced an English
        # reply with the Spanish drift repair. Ambiguous tokens must
        # not carry the accent tier.
        self.assertFalse(g._looks_spanish(
            "Can you tell me about the sounds and smells of Marché "
            "d'Aligre brought back a lot of memories, didn't they?"
        ))

    def test_con_era_me_no_accent_is_english(self):
        self.assertFalse(g._looks_spanish(
            "The con man made me nervous during that era."
        ))

    def test_trocadero_reply_no_drift_flag(self):
        # End-to-end: English narrator + English reply carrying a French
        # place name must not be classified as language drift.
        self.assertFalse(g.detect_language_drift(
            "You walked from the Trocadéro to the Palais de Chaillot. "
            "What came next on the museum run?",
            "The Paris museum run included the Eiffel Tower and "
            "Trocadéro Gardens.",
            (),
        ))


class LanguageDriftRepairTest(unittest.TestCase):
    def test_default_english_repair(self):
        text = g.repair_language_drift("en")
        self.assertIn("English", text)
        self.assertNotIn("español", text.lower())

    def test_spanish_target_repair(self):
        # Stale-assertion fix 2026-07-02: the ES repair became the
        # neutral "Disculpa, continuemos" string when the chain-aware
        # English repair landed; it no longer mentions "inglés".
        text = g.repair_language_drift("es")
        self.assertIn("Disculpa", text)
        self.assertTrue(g._looks_spanish(text))
        self.assertNotIn("English", text)


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




class SensoryPivotOnChainTest(unittest.TestCase):
    """BUG-LORI-FACTUAL-OVER-SENSORY-PROBE-01 (2026-07-02).

    Live evidence: 2019 France/Italy T6 — with the strengthened
    directive ACTIVE, Lori still asked about "the city's atmosphere".
    Deterministic post-LLM repair is the enforcement layer.
    """

    T6_REPLY = (
        "Avignon Bridge. What was your impression of the city's "
        "atmosphere and historic buildings, like the Palais des Papes?"
    )
    T6_ANCHORS = ["Aix", "Avignon", "Palais des Papes", "Arles"]

    def test_t6_live_reply_detected_on_chain(self):
        self.assertTrue(
            g.detect_sensory_pivot_on_chain(self.T6_REPLY, True)
        )

    def test_not_detected_when_not_chain(self):
        self.assertFalse(
            g.detect_sensory_pivot_on_chain(self.T6_REPLY, False)
        )

    def test_factual_reply_passes_on_chain(self):
        self.assertFalse(g.detect_sensory_pivot_on_chain(
            "You went from Aix to Avignon and on to Arles. "
            "What came next after Arles?",
            True,
        ))

    def test_repair_echoes_anchors_one_question_no_sensory(self):
        repaired = g.repair_sensory_pivot(self.T6_ANCHORS)
        echoed = sum(1 for a in self.T6_ANCHORS if a in repaired)
        self.assertGreaterEqual(echoed, 2)
        self.assertEqual(repaired.count("?"), 1)
        self.assertFalse(g.detect_sensory_pivot_on_chain(repaired, True))

    def test_repair_no_anchors_neutral(self):
        repaired = g.repair_sensory_pivot([])
        self.assertEqual(repaired.count("?"), 1)
        self.assertFalse(g.detect_sensory_pivot_on_chain(repaired, True))

    def test_repair_spanish_target(self):
        repaired = g.repair_sensory_pivot(self.T6_ANCHORS, "es")
        self.assertIn("¿", repaired)

    def test_apply_response_guards_fires_and_repairs(self):
        final, fired = g.apply_response_guards(
            assistant_text=self.T6_REPLY,
            narrator_text=(
                "From Aix we did the Provence side trip to Avignon, "
                "saw the Palais des Papes and the Avignon Bridge, "
                "then went on to Arles."
            ),
            narrator_anchors=self.T6_ANCHORS,
            is_factual_chain=True,
        )
        self.assertIn("sensory_pivot_on_chain", fired)
        self.assertNotIn("atmosphere", final.lower())
        self.assertIn("Avignon", final)

    def test_apply_response_guards_default_off(self):
        # Without the chain flag, the T6 reply passes through (the
        # sensory ban only applies to chain turns).
        final, fired = g.apply_response_guards(
            assistant_text=self.T6_REPLY,
            narrator_text="What a lovely day it was.",
        )
        self.assertNotIn("sensory_pivot_on_chain", fired)
        self.assertEqual(final, self.T6_REPLY)


class MetaPreambleRequestedFormatTest(unittest.TestCase):
    """BUG-LORI-META-PREAMBLE-LEAK-01 (2026-07-07) — live trip-open leak.

    The narrator saw: 'Here is the response in the requested format:
    "Prague and Salzburg stand out..."'. The repair's quoted-draft
    recovery handled this shape but the DETECTOR did not, so the guard
    never fired and the meta-framing reached the bubble + archive.
    """

    LIVE = ('Here is the response in the requested format: "Prague and '
            'Salzburg stand out from that spring trip to Central Europe '
            'and Northern Italy. What comes to mind as you look back on '
            'those travels?"')

    def test_live_line_detected(self):
        self.assertTrue(g.detect_meta_response_leak(self.LIVE))

    def test_live_line_repairs_to_quoted_draft(self):
        repaired = g.repair_meta_response_leak(self.LIVE)
        self.assertTrue(repaired.startswith("Prague and Salzburg"))
        self.assertNotIn("requested format", repaired)

    def test_full_guard_pipeline_strips_it(self):
        final, fired = g.apply_response_guards(
            assistant_text=self.LIVE,
            narrator_text="Tell me about the trip.",
            recent_narrator_turns=["Tell me about the trip."],
            target_language="en",
        )
        self.assertTrue(final.startswith("Prague and Salzburg"))
        self.assertTrue(any("meta" in f for f in fired), fired)

    def test_benign_requested_format_mention_not_flagged(self):
        ok = ("You mentioned the paperwork had to be in the requested "
              "format for the visa office. What happened next?")
        self.assertFalse(g.detect_meta_response_leak(ok))

if __name__ == "__main__":
    unittest.main(verbosity=2)
