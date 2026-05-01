"""WO-LORI-QUESTION-ATOMICITY-01 — unit tests for the deterministic atomicity filter.

Three test classes:

  ClassifyAtomicityTests   — positive (must flag) + negative (must not flag)
  EnforceTruncationTests   — truncation grammar + Case A/B handling
  GolfballRegressionTests  — anchored to actual 2026-04-30 golfball-v2-clean
                             failures (Turns 03/04/07) so the suite acts as
                             a live regression gate
"""
from __future__ import annotations

import unittest

from server.code.api.services.question_atomicity import (
    classify_atomicity,
    enforce_question_atomicity,
)


class ClassifyAtomicityTests(unittest.TestCase):
    """Positive + negative classification per §4.1-4.6."""

    # -- 4.1 and_pivot ---------------------------------------------------

    def test_and_pivot_two_questions(self):
        text = "What was Spokane like, and how did your dad's work affect you?"
        self.assertIn("and_pivot", classify_atomicity(text))

    def test_and_pivot_question_plus_aux(self):
        text = "What was Spokane like, and did your family stay long?"
        self.assertIn("and_pivot", classify_atomicity(text))

    def test_and_pivot_statement_plus_question(self):
        text = "I can imagine that was thrilling, and what drew you to that role?"
        self.assertIn("and_pivot", classify_atomicity(text))

    # -- 4.2 or_speculation ---------------------------------------------

    def test_or_speculation_be_verb_post_pivot(self):
        # Real Turn 03 failure
        text = ("Did he often share stories about his experiences working at "
                "the plant with you, or were those nights a source of worry?")
        self.assertIn("or_speculation", classify_atomicity(text))

    def test_or_speculation_was_post_pivot(self):
        text = "Was it scary, or did it feel normal?"
        self.assertIn("or_speculation", classify_atomicity(text))

    def test_or_speculation_long_post_pivot(self):
        # Real Turn 07 failure
        text = ("Would you like to talk more about what is causing those "
                "feelings, or is there something else on your mind?")
        self.assertIn("or_speculation", classify_atomicity(text))

    # -- 4.3 request_plus_inquiry ---------------------------------------

    def test_request_plus_inquiry_tell_and_what(self):
        text = "Tell me more about Spokane and what happened next."
        self.assertIn("request_plus_inquiry", classify_atomicity(text))

    def test_request_plus_inquiry_describe_and_how(self):
        text = "Describe your morning routine and how it changed over time."
        self.assertIn("request_plus_inquiry", classify_atomicity(text))

    # -- 4.4 choice_framing ---------------------------------------------

    def test_choice_framing_three_options(self):
        text = "Did you feel proud, sad, or confused?"
        self.assertIn("choice_framing", classify_atomicity(text))

    def test_choice_framing_no_oxford_comma(self):
        text = "Was it cold, dark, lonely?"
        self.assertIn("choice_framing", classify_atomicity(text))

    # -- 4.5 hidden_second_target ---------------------------------------

    def test_hidden_target_two_places(self):
        text = "What do you remember about Spokane and Montreal?"
        self.assertIn("hidden_second_target", classify_atomicity(text))

    # 2026-05-01 NARROWING: hidden_second_target now requires
    # PROPER-NOUN pairs only. Generic relation pairs ("mom and dad",
    # "school and church") are conventionally single coordinated
    # retrieval targets and must NOT flag — see WO-LORI-COMMUNICATION-
    # CONTROL-01 §8 negative tests. Dual_retrieval_axis still catches
    # the real compound case (place + emotion / person + emotion).

    # -- 4.6 dual_retrieval_axis ----------------------------------------

    def test_dual_retrieval_place_plus_emotion(self):
        text = "What do you remember about Spokane and how you felt?"
        self.assertIn("dual_retrieval_axis", classify_atomicity(text))

    def test_dual_retrieval_event_plus_evaluation(self):
        text = "What happened that day and what did it mean for the family?"
        self.assertIn("dual_retrieval_axis", classify_atomicity(text))

    # -- Negatives (must NOT flag) --------------------------------------

    def test_negative_simple_question(self):
        self.assertEqual(classify_atomicity("What do you remember about Spokane?"), [])

    def test_negative_short_open_question(self):
        self.assertEqual(classify_atomicity("How did it feel at the time?"), [])

    def test_negative_imperative(self):
        self.assertEqual(classify_atomicity("Tell me more about Spokane."), [])

    def test_negative_internal_and_in_modifier(self):
        # "reading and writing" is a single coordinated noun phrase, not
        # a compound question subject. Must not trip and_pivot.
        self.assertEqual(
            classify_atomicity("What is your relationship with reading and writing?"),
            [],
        )

    def test_negative_internal_or_in_modifier(self):
        self.assertEqual(
            classify_atomicity("Was it weeks or months ago?"),
            [],
        )

    # 2026-05-01 negative tests from WO-LORI-COMMUNICATION-CONTROL-01 §8.
    # These are coordinated single-target patterns that must NOT trip:

    def test_negative_mother_and_father(self):
        # "your mother and father" = single coordinated retrieval target
        # ("memories of my parents" is one memory blob)
        self.assertEqual(
            classify_atomicity("What do you remember about your mother and father?"),
            [],
        )

    def test_negative_reading_and_writing(self):
        self.assertEqual(
            classify_atomicity("What do you remember about reading and writing?"),
            [],
        )

    def test_negative_you_and_brother(self):
        self.assertEqual(
            classify_atomicity("What did you and your brother do after school?"),
            [],
        )

    def test_negative_empty_string(self):
        self.assertEqual(classify_atomicity(""), [])

    def test_negative_whitespace_only(self):
        self.assertEqual(classify_atomicity("   \n  "), [])

    def test_negative_short_statement(self):
        self.assertEqual(classify_atomicity("That sounds important."), [])

    def test_negative_two_separate_sentences(self):
        # NOT a compound — each is its own complete thought separated by '.'
        # We don't flag this because Layer 1 prompt directive handles it.
        text = "Spokane sounds clear in your memory. What do you remember about it?"
        # Single question_clause, no compound pattern.
        flags = classify_atomicity(text)
        self.assertNotIn("and_pivot", flags)
        self.assertNotIn("or_speculation", flags)


class EnforceTruncationTests(unittest.TestCase):
    """§5.1 truncation grammar guard + Case A / Case B handling."""

    def test_case_a_question_lead_keeps_pre_pivot(self):
        text = "What was Spokane like, and how did your dad's work affect you?"
        out, failures = enforce_question_atomicity(text)
        self.assertIn("and_pivot", failures)
        self.assertEqual(out, "What was Spokane like?")

    def test_case_b_statement_lead_keeps_post_pivot(self):
        text = "I can imagine that was thrilling, and what drew you to that role?"
        out, failures = enforce_question_atomicity(text)
        self.assertIn("and_pivot", failures)
        self.assertEqual(out, "What drew you to that role?")

    def test_imperative_lead_keeps_pre_pivot(self):
        text = "Tell me more about Spokane and what happened next."
        out, failures = enforce_question_atomicity(text)
        self.assertIn("request_plus_inquiry", failures)
        self.assertEqual(out, "Tell me more about Spokane.")

    def test_or_speculation_truncation_clean(self):
        text = ("Did he often share stories with you, or were those nights "
                "a source of worry?")
        out, failures = enforce_question_atomicity(text)
        self.assertIn("or_speculation", failures)
        self.assertTrue(out.endswith("?"))
        self.assertNotIn(", or were", out)

    def test_dual_retrieval_truncation_keeps_first_target(self):
        text = "What do you remember about Spokane and how you felt?"
        out, failures = enforce_question_atomicity(text)
        self.assertIn("dual_retrieval_axis", failures)
        self.assertTrue(out.endswith("?"))
        self.assertIn("Spokane", out)
        self.assertNotIn("how you felt", out)

    def test_negative_pass_through_unchanged(self):
        text = "What do you remember about Spokane?"
        out, failures = enforce_question_atomicity(text)
        self.assertEqual(failures, [])
        self.assertEqual(out, text)

    def test_empty_string_pass_through(self):
        out, failures = enforce_question_atomicity("")
        self.assertEqual(failures, [])
        self.assertEqual(out, "")


class GolfballRegressionTests(unittest.TestCase):
    """Anchored to the 2026-04-30 golfball-v2-clean Turn 03/04/07
    failures so future regressions on this taxonomy break the suite."""

    def test_turn03_or_speculation_caught_and_truncated(self):
        text = ("Did he often share stories about his experiences working at "
                "the plant with you, or were those nights a source of worry "
                "for you?")
        out, failures = enforce_question_atomicity(text)
        self.assertIn("or_speculation", failures)
        self.assertTrue(out.endswith("?"))
        self.assertNotIn(", or were", out)

    def test_turn04_and_pivot_caught_and_truncated(self):
        text = ("I can imagine that must have been a thrilling experience "
                "for you, and what drew you to that role?")
        out, failures = enforce_question_atomicity(text)
        self.assertIn("and_pivot", failures)
        # Case B: pre-pivot is statement → keep post-pivot
        self.assertEqual(out, "What drew you to that role?")

    def test_turn07_or_speculation_caught_and_truncated(self):
        text = ("Would you like to talk more about what is causing those "
                "feelings, or is there something else on your mind?")
        out, failures = enforce_question_atomicity(text)
        self.assertIn("or_speculation", failures)
        self.assertTrue(out.endswith("?"))
        self.assertNotIn(", or", out)


if __name__ == "__main__":
    unittest.main()
