"""WO-LORI-COMMUNICATION-CONTROL-01 — unit tests for the runtime guard.

Test classes:
  AtomicityViaWrapperTests       — the 6 atomicity categories pass through
  ReflectionViaWrapperTests      — reflection labels surface (no mutation)
  LengthControlTests             — per-session-style word limits
  QuestionCountTests             — multi-question truncation
  SafetyExemptionTests           — acute path bypasses normal enforcement
  NegativeTests                  — clean turns pass cleanly
  GolfballRegressionTests        — anchored to 2026-04-30 Turn 03/04/07
"""
from __future__ import annotations

import unittest

from server.code.api.services.lori_communication_control import (
    enforce_lori_communication_control,
)


class AtomicityViaWrapperTests(unittest.TestCase):
    """The wrapper composes question_atomicity — its labels surface."""

    def test_and_pivot_fires(self):
        text = "What was Spokane like, and how did your dad's work affect you?"
        r = enforce_lori_communication_control(
            assistant_text=text,
            user_text="I had a mastoidectomy in Spokane.",
        )
        self.assertIn("and_pivot", r.atomicity_failures)
        self.assertTrue(r.changed)

    def test_or_speculation_fires(self):
        text = ("Did he often share stories about his experiences working at "
                "the plant with you, or were those nights a source of worry?")
        r = enforce_lori_communication_control(
            assistant_text=text,
            user_text="my dad worked nights at the plant",
        )
        self.assertIn("or_speculation", r.atomicity_failures)


class ReflectionViaWrapperTests(unittest.TestCase):
    """Reflection labels surface but text is NOT mutated by reflection."""

    def test_unstated_emotion_reports_no_rewrite(self):
        text = ("That must have been a really scary experience for you. "
                "What do you remember about it?")
        r = enforce_lori_communication_control(
            assistant_text=text,
            user_text="I had a mastoidectomy when I was little, in Spokane.",
        )
        # Reflection labels surface
        self.assertIn("echo_contains_unstated_emotion", r.reflection_failures)
        self.assertIn("echo_contains_diagnostic_language", r.reflection_failures)
        # But text is NOT rewritten by reflection (only atomicity / length /
        # question-count can mutate). Since this text has no compound, no
        # extra question, and is short, final_text == original.
        self.assertEqual(r.final_text, text)
        self.assertFalse(r.changed)


class LengthControlTests(unittest.TestCase):
    """Per-session-style word limits."""

    def test_clear_direct_55_word_limit(self):
        long_text = " ".join(["word"] * 70) + ". What do you remember?"
        r = enforce_lori_communication_control(
            assistant_text=long_text,
            user_text="anything",
            session_style="clear_direct",
        )
        self.assertIn("too_long", r.failures)
        self.assertLessEqual(r.word_count, 55)

    def test_warm_storytelling_90_word_limit(self):
        long_text = " ".join(["word"] * 70) + ". What do you remember?"
        r = enforce_lori_communication_control(
            assistant_text=long_text,
            user_text="anything",
            session_style="warm_storytelling",
        )
        # Under 90 — should NOT trip too_long even though it'd trip in clear_direct
        self.assertNotIn("too_long", r.failures)

    def test_unknown_style_falls_back_to_default(self):
        long_text = " ".join(["word"] * 70) + ". What do you remember?"
        r = enforce_lori_communication_control(
            assistant_text=long_text,
            user_text="anything",
            session_style="unknown_made_up_style",
        )
        # Default limit is 55 (clear_direct) — should trip
        self.assertIn("too_long", r.failures)


class QuestionCountTests(unittest.TestCase):
    """≤1 question per turn enforcement."""

    def test_two_questions_truncates_to_first(self):
        text = "What do you remember about Spokane? What about Montreal?"
        r = enforce_lori_communication_control(
            assistant_text=text,
            user_text="I lived in Spokane.",
        )
        self.assertIn("too_many_questions", r.failures)
        self.assertEqual(r.question_count, 1)
        self.assertTrue(r.final_text.endswith("?"))
        self.assertNotIn("Montreal", r.final_text)

    def test_one_question_passes(self):
        text = "That's a clear memory. What stands out most?"
        r = enforce_lori_communication_control(
            assistant_text=text,
            user_text="My grandfather came over from Norway in 1893.",
        )
        self.assertNotIn("too_many_questions", r.failures)
        self.assertEqual(r.question_count, 1)


class SafetyExemptionTests(unittest.TestCase):
    """Acute SAFETY responses bypass normal enforcement."""

    def test_safety_path_no_mutation(self):
        # Simulating the actual Turn 06 ACUTE response from golfball-v2-clean
        text = ("I'm an AI and I can't place calls for you, but please call "
                "or text 988 right now — that is the current US Suicide "
                "and Crisis Lifeline.")
        r = enforce_lori_communication_control(
            assistant_text=text,
            user_text="How can I end my life?",
            safety_triggered=True,
            session_style="clear_direct",
        )
        # Text unchanged
        self.assertEqual(r.final_text, text)
        self.assertFalse(r.changed)
        # No atomicity/reflection failures recorded (we don't run those checks
        # in the safety path)
        self.assertEqual(r.atomicity_failures, [])
        self.assertEqual(r.reflection_failures, [])
        # Length check skipped too — safety responses can run long
        self.assertNotIn("too_long", r.failures)

    def test_safety_normal_question_during_safety_flagged(self):
        # If Lori asked a normal interview question during a safety-triggered
        # turn (no 988, no acknowledgment), the wrapper should flag it.
        text = "What do you remember about your childhood?"
        r = enforce_lori_communication_control(
            assistant_text=text,
            user_text="How can I end my life?",
            safety_triggered=True,
        )
        self.assertIn("normal_interview_question_during_safety", r.failures)
        self.assertTrue(r.safety_triggered)

    def test_safety_acknowledgment_with_question_passes(self):
        # "Are you safe right now?" inside a safety-aware response is OK.
        text = ("I'm so sorry you're in this much pain. Please call or text 988. "
                "Are you safe right now?")
        r = enforce_lori_communication_control(
            assistant_text=text,
            user_text="I want to end my life.",
            safety_triggered=True,
        )
        self.assertNotIn("normal_interview_question_during_safety", r.failures)


class NegativeTests(unittest.TestCase):
    """Clean turns must pass cleanly — no false-positive mutations."""

    def test_clean_short_turn_passes(self):
        text = "That's a clear memory. What stands out most?"
        r = enforce_lori_communication_control(
            assistant_text=text,
            user_text="I had a mastoidectomy when I was little, in Spokane.",
        )
        self.assertEqual(r.final_text, text)
        self.assertFalse(r.changed)
        self.assertEqual(r.failures, [])
        self.assertEqual(r.atomicity_failures, [])

    def test_negative_mother_and_father(self):
        # WO §8 negative test
        text = "What do you remember about your mother and father?"
        r = enforce_lori_communication_control(
            assistant_text=text,
            user_text="I grew up with both my parents.",
        )
        self.assertEqual(r.atomicity_failures, [])
        self.assertNotIn("hidden_second_target", r.atomicity_failures)

    def test_negative_reading_and_writing(self):
        text = "What do you remember about reading and writing?"
        r = enforce_lori_communication_control(
            assistant_text=text,
            user_text="I learned to read at four.",
        )
        self.assertEqual(r.atomicity_failures, [])

    def test_empty_text_passes(self):
        r = enforce_lori_communication_control(
            assistant_text="",
            user_text="anything",
        )
        self.assertEqual(r.final_text, "")
        self.assertFalse(r.changed)
        self.assertEqual(r.failures, [])

    def test_to_dict_excludes_text(self):
        # The harness should never get assistant content in the dict.
        text = "What do you remember about Spokane?"
        r = enforce_lori_communication_control(
            assistant_text=text,
            user_text="I lived in Spokane.",
        )
        d = r.to_dict()
        self.assertNotIn("original_text", d)
        self.assertNotIn("final_text", d)
        # But all the structural fields are present
        self.assertIn("changed", d)
        self.assertIn("question_count", d)
        self.assertIn("word_count", d)
        self.assertIn("atomicity_failures", d)
        self.assertIn("reflection_failures", d)


class GolfballRegressionTests(unittest.TestCase):
    """Anchored to 2026-04-30 golfball-v2-clean Turn 03/04/07 failures."""

    def test_turn03_or_speculation_truncated(self):
        text = ("Did he often share stories about his experiences working at "
                "the plant with you, or were those nights a source of worry "
                "for you?")
        r = enforce_lori_communication_control(
            assistant_text=text,
            user_text="when i was young in spokane my dad worked nights at the aluminum plant",
        )
        self.assertIn("or_speculation", r.atomicity_failures)
        self.assertTrue(r.changed)
        self.assertNotIn(", or were", r.final_text)

    def test_turn04_and_pivot_case_b(self):
        text = ("I can imagine that must have been a thrilling experience "
                "for you, and what drew you to that role?")
        r = enforce_lori_communication_control(
            assistant_text=text,
            user_text="I was Captain Kirk and T. J. Hooker.",
        )
        self.assertIn("and_pivot", r.atomicity_failures)
        # Case B: pre-pivot is a statement, post-pivot is the question
        self.assertEqual(r.final_text, "What drew you to that role?")
        # Reflection should also surface "thrilling" as unstated emotion —
        # but since the atomicity truncation stripped the echo span, the
        # truncated text no longer contains "thrilling". This is correct
        # behavior: reflection runs ON the post-truncation text, so labels
        # reflect what's actually being sent.
        self.assertNotIn("thrilling", r.final_text)

    def test_turn07_or_speculation_truncated(self):
        text = ("Would you like to talk more about what is causing those "
                "feelings, or is there something else on your mind?")
        r = enforce_lori_communication_control(
            assistant_text=text,
            user_text="I am still here. I just feel tired and scared.",
        )
        self.assertIn("or_speculation", r.atomicity_failures)
        self.assertTrue(r.changed)
        self.assertNotIn(", or", r.final_text)


class StubCollapseDetectionTest(unittest.TestCase):
    """BUG-LORI-RESPONSE-STUB-COLLAPSE-01 (2026-05-09) — Mary's session
    surfaced the LLM emitting ~3-character stubs ("AI.") in response to
    substantive narrator questions. The detection here is operator-
    visibility only (failure label, not rewrite); the meta-question
    deterministic intercept upstream handles the known failure shapes.
    """

    def test_three_char_response_to_substantive_question_flags(self):
        # Mary's literal: "what is an AI?" → Lori "AI."
        r = enforce_lori_communication_control(
            assistant_text="AI.",
            user_text="what is an AI? you tell me that like i know what AI is?",
        )
        self.assertIn("response_stub_collapse", r.failures)

    def test_one_word_response_to_long_narrator_question_flags(self):
        r = enforce_lori_communication_control(
            assistant_text="Spokane.",
            user_text="tell me what you know about my time growing up there",
        )
        self.assertIn("response_stub_collapse", r.failures)

    def test_normal_response_does_not_flag(self):
        r = enforce_lori_communication_control(
            assistant_text="That sounds like a meaningful memory. What stays with you most about it?",
            user_text="I remember the long winters in Spokane.",
        )
        self.assertNotIn("response_stub_collapse", r.failures)

    def test_short_response_to_trivial_narrator_does_not_flag(self):
        # Yes/no narrator → short Lori is fine
        r = enforce_lori_communication_control(
            assistant_text="Got it.",
            user_text="yes",
        )
        self.assertNotIn("response_stub_collapse", r.failures)

    def test_short_response_to_three_word_narrator_does_not_flag(self):
        # Below the 4-word floor — narrator's question is too short to
        # demand elaboration
        r = enforce_lori_communication_control(
            assistant_text="Okay.",
            user_text="that's right yes",
        )
        self.assertNotIn("response_stub_collapse", r.failures)


if __name__ == "__main__":
    unittest.main()
