"""Unit tests for services/lori_meta_question.py.

Pure-function tests — no DB, no LLM, no filesystem. The detector
must catch the literal narrator turns from Mary's 2026-05-09 session
that broke Lori's identity / safety / capability behavior, AND must
NOT false-positive on storytelling turns that happen to contain
overlapping vocabulary ("my name was different back then" / "is it
safe to walk down there now").

Cases organized by category. Mary's literal turns appear as
NamedRealNarrator tests so any regression on her exact phrasing is
visible.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api.services import lori_meta_question as mq  # noqa: E402


# ── Section 1: identity_name ──────────────────────────────────────────────

class IdentityNameDetectionTest(unittest.TestCase):
    def test_what_is_your_name(self):
        match = mq.detect_meta_question("what is your name")
        self.assertTrue(match.is_meta)
        self.assertIn("identity_name", match.categories_matched)

    def test_whats_your_name(self):
        match = mq.detect_meta_question("what's your name?")
        self.assertTrue(match.is_meta)
        self.assertIn("identity_name", match.categories_matched)

    def test_who_are_you(self):
        match = mq.detect_meta_question("who are you?")
        self.assertTrue(match.is_meta)
        self.assertIn("identity_name", match.categories_matched)

    def test_tell_me_your_name(self):
        match = mq.detect_meta_question("tell me your name")
        self.assertTrue(match.is_meta)
        self.assertIn("identity_name", match.categories_matched)

    def test_spanish_como_te_llamas(self):
        match = mq.detect_meta_question("¿Cómo te llamas?")
        self.assertTrue(match.is_meta)
        self.assertIn("identity_name", match.categories_matched)

    def test_spanish_cual_es_tu_nombre(self):
        match = mq.detect_meta_question("cuál es tu nombre")
        self.assertTrue(match.is_meta)
        self.assertIn("identity_name", match.categories_matched)


# ── Section 2: identity_what (nature) ─────────────────────────────────────

class IdentityWhatDetectionTest(unittest.TestCase):
    def test_what_are_you(self):
        match = mq.detect_meta_question("what are you")
        self.assertTrue(match.is_meta)
        self.assertIn("identity_what", match.categories_matched)

    def test_are_you_a_robot(self):
        match = mq.detect_meta_question("are you a robot?")
        self.assertTrue(match.is_meta)
        self.assertIn("identity_what", match.categories_matched)

    def test_are_you_an_AI(self):
        match = mq.detect_meta_question("are you an AI?")
        self.assertTrue(match.is_meta)
        self.assertIn("identity_what", match.categories_matched)

    def test_are_you_a_person(self):
        match = mq.detect_meta_question("are you a person")
        self.assertTrue(match.is_meta)
        self.assertIn("identity_what", match.categories_matched)

    def test_are_you_real(self):
        match = mq.detect_meta_question("are you real")
        self.assertTrue(match.is_meta)
        self.assertIn("identity_what", match.categories_matched)

    def test_spanish_que_eres(self):
        match = mq.detect_meta_question("¿Qué eres?")
        self.assertTrue(match.is_meta)
        self.assertIn("identity_what", match.categories_matched)

    def test_spanish_eres_humana(self):
        match = mq.detect_meta_question("¿Eres humana?")
        self.assertTrue(match.is_meta)
        self.assertIn("identity_what", match.categories_matched)


# ── Section 3: purpose ────────────────────────────────────────────────────

class PurposeDetectionTest(unittest.TestCase):
    def test_what_is_your_purpose(self):
        match = mq.detect_meta_question("what is your purpose")
        self.assertTrue(match.is_meta)
        self.assertIn("purpose", match.categories_matched)

    def test_what_can_you_do(self):
        match = mq.detect_meta_question("what can you do for me")
        self.assertTrue(match.is_meta)
        self.assertIn("purpose", match.categories_matched)

    def test_why_are_you_here(self):
        match = mq.detect_meta_question("why are you here")
        self.assertTrue(match.is_meta)
        self.assertIn("purpose", match.categories_matched)

    def test_spanish_para_que_estas_aqui(self):
        match = mq.detect_meta_question("¿Para qué estás aquí?")
        self.assertTrue(match.is_meta)
        self.assertIn("purpose", match.categories_matched)


# ── Section 4: safety_concern (THE SHOW-STOPPER CATEGORY) ─────────────────

class SafetyConcernDetectionTest(unittest.TestCase):
    """These are the patterns that 988-mis-routed Mary on 2026-05-09.
    Every one of them MUST detect as safety_concern (not as
    distress/ideation handled by safety_classifier.py)."""

    def test_mary_literal_2026_05_09(self):
        # Verbatim from transcript_switch_moyc6 (2).txt:135
        text = "I am kind of scared, are you safe to talk to?"
        match = mq.detect_meta_question(text)
        self.assertTrue(match.is_meta, "Mary's literal turn must detect")
        self.assertEqual(
            match.primary_category, "safety_concern",
            "Mary's turn primary must be safety_concern (NOT routed to safety classifier)",
        )

    def test_is_it_safe(self):
        match = mq.detect_meta_question("is it safe?")
        self.assertTrue(match.is_meta)
        self.assertIn("safety_concern", match.categories_matched)

    def test_is_this_safe_to_talk_to(self):
        match = mq.detect_meta_question("is this safe to talk to")
        self.assertTrue(match.is_meta)
        self.assertIn("safety_concern", match.categories_matched)

    def test_am_i_safe(self):
        match = mq.detect_meta_question("am I safe?")
        self.assertTrue(match.is_meta)
        self.assertIn("safety_concern", match.categories_matched)

    def test_can_i_trust_you(self):
        match = mq.detect_meta_question("can I trust you")
        self.assertTrue(match.is_meta)
        self.assertIn("safety_concern", match.categories_matched)

    def test_are_you_safe(self):
        match = mq.detect_meta_question("are you safe")
        self.assertTrue(match.is_meta)
        self.assertIn("safety_concern", match.categories_matched)

    def test_spanish_es_seguro(self):
        match = mq.detect_meta_question("¿es seguro?")
        self.assertTrue(match.is_meta)
        self.assertIn("safety_concern", match.categories_matched)

    def test_spanish_estoy_a_salvo(self):
        match = mq.detect_meta_question("¿estoy a salvo aquí?")
        self.assertTrue(match.is_meta)
        self.assertIn("safety_concern", match.categories_matched)

    def test_spanish_puedo_confiar(self):
        match = mq.detect_meta_question("¿puedo confiar en ti?")
        self.assertTrue(match.is_meta)
        self.assertIn("safety_concern", match.categories_matched)


# ── Section 5: capability_explain ─────────────────────────────────────────

class CapabilityExplainDetectionTest(unittest.TestCase):
    def test_what_is_an_AI(self):
        match = mq.detect_meta_question("what is an AI?")
        self.assertTrue(match.is_meta)
        self.assertIn("capability_explain", match.categories_matched)

    def test_what_is_AI(self):
        match = mq.detect_meta_question("what is AI")
        self.assertTrue(match.is_meta)
        self.assertIn("capability_explain", match.categories_matched)

    def test_explain_AI(self):
        match = mq.detect_meta_question("explain AI to me")
        self.assertTrue(match.is_meta)
        self.assertIn("capability_explain", match.categories_matched)

    def test_what_is_artificial_intelligence(self):
        match = mq.detect_meta_question("what is artificial intelligence")
        self.assertTrue(match.is_meta)
        self.assertIn("capability_explain", match.categories_matched)

    def test_spanish_que_es_ia(self):
        match = mq.detect_meta_question("¿qué es IA?")
        self.assertTrue(match.is_meta)
        self.assertIn("capability_explain", match.categories_matched)

    def test_spanish_que_es_inteligencia_artificial(self):
        match = mq.detect_meta_question("qué es inteligencia artificial")
        self.assertTrue(match.is_meta)
        self.assertIn("capability_explain", match.categories_matched)


# ── Section 6: priority ordering ──────────────────────────────────────────

class PriorityOrderingTest(unittest.TestCase):
    """When multiple categories match in one turn, the dominant intent
    drives the response. Safety wins over everything else."""

    def test_safety_wins_over_name(self):
        # "what is your name and is it safe" — safety should win because
        # the narrator's primary anxiety is safety
        match = mq.detect_meta_question("what is your name and is it safe to talk to you")
        self.assertEqual(match.primary_category, "safety_concern")

    def test_safety_wins_over_capability(self):
        match = mq.detect_meta_question("what is an AI and is it safe")
        self.assertEqual(match.primary_category, "safety_concern")

    def test_capability_wins_over_what(self):
        match = mq.detect_meta_question("what are you, what is an AI")
        self.assertEqual(match.primary_category, "capability_explain")

    def test_name_and_purpose_combined(self):
        # Mary's third turn: "what is your name again and your purpose"
        match = mq.detect_meta_question("what is your name again and your purpose")
        self.assertEqual(match.primary_category, "name_and_purpose")


# ── Section 7: false-positive resistance ──────────────────────────────────

class FalsePositiveResistanceTest(unittest.TestCase):
    """Storytelling turns that happen to contain overlapping vocabulary
    must NOT detect as meta-questions. Every one of these is a real or
    plausible narrator memory."""

    def test_my_name_was_different_back_then(self):
        # Talking ABOUT names in past tense — narrative, not meta
        match = mq.detect_meta_question("my name was different back then")
        self.assertFalse(match.is_meta)

    def test_is_it_safe_to_walk(self):
        # Talking about a place's safety, not about Lori
        match = mq.detect_meta_question("is it safe to walk down by the river")
        self.assertTrue(match.is_meta, "this still matches 'is it safe' — acceptable false positive")
        # NOTE: This is a known limitation. "Is it safe" alone is
        # ambiguous — could be about Lori or about a place. We err
        # on the side of detecting (and giving the safety answer)
        # because the worst case is Lori reassures the narrator
        # that talking is safe; the worst case for the OTHER
        # direction is 988 dispatched on anxiety. The false
        # positive direction is fixable in conversation; the
        # false negative direction is the parent-session blocker.

    def test_my_purpose_in_life(self):
        # Narrator talking ABOUT their own purpose
        match = mq.detect_meta_question("I think my purpose in life was to raise my children")
        self.assertFalse(match.is_meta)

    def test_who_was_my_father(self):
        # Narrator asking ABOUT their father, not Lori
        match = mq.detect_meta_question("who was my father")
        self.assertFalse(match.is_meta)

    def test_what_was_school_like(self):
        match = mq.detect_meta_question("what was school like for you")
        # "what was" not "what are" — must not match what-are-you
        self.assertFalse(match.is_meta)

    def test_what_does_it_mean(self):
        match = mq.detect_meta_question("what does it mean to be a parent")
        self.assertFalse(match.is_meta)

    def test_simple_yes(self):
        match = mq.detect_meta_question("yes")
        self.assertFalse(match.is_meta)

    def test_empty_input(self):
        self.assertFalse(mq.detect_meta_question("").is_meta)
        self.assertFalse(mq.detect_meta_question(None).is_meta)
        self.assertFalse(mq.detect_meta_question("   \n  ").is_meta)


# ── Section 8: composer output ────────────────────────────────────────────

class ComposeMetaAnswerTest(unittest.TestCase):
    """The composed text must be warm, accurate, and include the
    Lorevox etymology on identity-touching answers."""

    def test_name_includes_etymology_en(self):
        match = mq.detect_meta_question("what is your name")
        text = mq.compose_meta_answer(match, target_language="en")
        self.assertIn("Lori", text)
        self.assertIn("Lorevox", text)
        self.assertIn("Lore", text)
        self.assertIn("Vox", text)
        self.assertIn("Latin", text)
        self.assertIn("voice", text)
        self.assertIn("stories", text)

    def test_name_includes_etymology_es(self):
        match = mq.detect_meta_question("¿cómo te llamas?")
        text = mq.compose_meta_answer(match, target_language="es")
        self.assertIn("Lori", text)
        self.assertIn("Lorevox", text)
        self.assertIn("Lore", text)
        self.assertIn("Vox", text)
        self.assertIn("latina", text.lower())
        self.assertIn("voz", text)
        self.assertIn("historias", text)

    def test_safety_response_does_not_mention_988(self):
        # CRITICAL — the fix would be a regression if this composer
        # somehow produced a 988 reference. The whole point of the
        # bypass is to NOT escalate.
        match = mq.detect_meta_question("are you safe to talk to")
        text = mq.compose_meta_answer(match, target_language="en")
        self.assertNotIn("988", text)
        self.assertNotIn("Suicide", text)
        self.assertNotIn("crisis", text.lower())
        # Must affirm safety
        self.assertIn("safe", text.lower())

    def test_safety_response_es_no_988(self):
        match = mq.detect_meta_question("¿es seguro?")
        text = mq.compose_meta_answer(match, target_language="es")
        self.assertNotIn("988", text)
        self.assertNotIn("Suicidio", text)
        self.assertNotIn("crisis", text.lower())
        self.assertIn("salvo", text.lower())

    def test_capability_explains_AI(self):
        match = mq.detect_meta_question("what is an AI?")
        text = mq.compose_meta_answer(match, target_language="en")
        self.assertIn("artificial intelligence", text.lower())
        self.assertIn("computer program", text.lower())
        # Mary's "AI." 3-char failure mode is impossible here:
        self.assertGreater(len(text), 50)

    def test_what_are_you_says_AI_assistant(self):
        match = mq.detect_meta_question("what are you")
        text = mq.compose_meta_answer(match, target_language="en")
        self.assertIn("AI", text)
        self.assertIn("Lori", text)

    def test_no_match_returns_empty(self):
        match = mq.detect_meta_question("yes that is correct")
        # Empty-meta match should compose to empty string
        text = mq.compose_meta_answer(match)
        self.assertEqual(text, "")


# ── Section 9: detect_and_compose convenience ─────────────────────────────

class DetectAndComposeTest(unittest.TestCase):
    def test_returns_none_for_non_meta(self):
        result = mq.detect_and_compose("My name was Mary back then.")
        self.assertIsNone(result)

    def test_returns_answer_for_meta(self):
        result = mq.detect_and_compose("what is your name", target_language="en")
        self.assertIsNotNone(result)
        self.assertEqual(result.language, "en")
        self.assertEqual(result.primary_category, "identity_name")
        self.assertIn("Lori", result.text)

    def test_es_locale_routing(self):
        result = mq.detect_and_compose("¿cómo te llamas?", target_language="es")
        self.assertIsNotNone(result)
        self.assertEqual(result.language, "es")
        self.assertIn("Lori", result.text)

    def test_unknown_language_falls_back_to_en(self):
        result = mq.detect_and_compose("what is your name", target_language="fr")
        self.assertIsNotNone(result)
        self.assertEqual(result.language, "en")

    def test_marys_988_turn_resolves_to_safety(self):
        # End-to-end: Mary's verbatim turn must produce a safety answer
        # in English with no 988 reference.
        result = mq.detect_and_compose(
            "I am kind of scared, are you safe to talk to?",
            target_language="en",
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.primary_category, "safety_concern")
        self.assertNotIn("988", result.text)
        self.assertIn("safe", result.text.lower())

    def test_marys_AI_question_resolves_to_capability(self):
        # Mary's "what is an AI?" turn must produce capability_explain,
        # NOT a 3-char "AI." stub.
        result = mq.detect_and_compose("what is an AI?")
        self.assertIsNotNone(result)
        self.assertEqual(result.primary_category, "capability_explain")
        self.assertGreater(len(result.text), 50)


# ── Section 10: determinism ───────────────────────────────────────────────

class DeterminismTest(unittest.TestCase):
    """Two calls on the same input must produce byte-identical output —
    this is a deterministic intercept, no randomness allowed."""

    def test_same_input_same_output(self):
        a = mq.detect_and_compose("what is your name")
        b = mq.detect_and_compose("what is your name")
        self.assertEqual(a.text, b.text)
        self.assertEqual(a.primary_category, b.primary_category)


if __name__ == "__main__":
    unittest.main(verbosity=2)
