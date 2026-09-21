"""WO-LORI-QUESTION-ATOMICITY-01 — unit tests for the deterministic atomicity filter.

Three test classes:

  ClassifyAtomicityTests   — positive (must flag) + negative (must not flag)
  EnforceTruncationTests   — truncation grammar + Case A/B handling
  GolfballRegressionTests  — anchored to actual 2026-04-30 golfball-v2-clean
                             failures (Turns 03/04/07) so the suite acts as
                             a live regression gate
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

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


class AnswerPreservationTests(unittest.TestCase):
    """BUG-LORI-ATOMICITY-DISCARDS-THE-ANSWER-01.

    Case B used to delete the clause before the pivot unconditionally.
    When that clause was Lori's ANSWER, the narrator received the
    pleasantry and lost the facts — and nothing downstream could see it,
    because the survivor was a grammatical question of legal length.

    THE SHAPES ARE LIVE, THE CONTENT IS NOT. The turns were captured
    from the ZZ synthetic narrator on 2026-09-21 under the canonical
    production configuration, via the shipped response trace: a 45-word
    reply naming two facts about a father, delivered as four words.

    The fixtures below reproduce the SHAPE with invented people and
    places. The real generated text had picked up a living family
    member's details from a prompt example, and a test file is a tracked
    file — copying it here would be one more copy of the material this
    repository is in the middle of removing. What made those turns
    useful as fixtures was never whose life they described; it was that
    a factual statement sat in front of the pivot.

    The original real-record failure — an operator's own session, about
    his mother — cannot be reproduced at all: tracing was off that day
    and the generated text is not in the trace. Nothing here claims to
    be that turn.
    """

    ZZ_DAD = ("Your dad. We've touched on his years at the Marrow Bay "
              "boatyard and the winter you spent at your aunt's. I want "
              "to make sure I understand correctly. Can you tell me a bit "
              "more about your dad and what you remember about him?")

    ZZ_MOM_EVENTS = ("Your mom's notable life events... What stands out to "
                     "you about her life, or what would you like to share "
                     "about her experiences?")

    MOTHER_BIOGRAPHY = (
        "That came from your biography, not from anything you told me in "
        "our conversations. Your record lists your mother as Alda "
        "Quillfeather, born in Marrow Bay. Would you like to share "
        "something new about her, or shall we stay with what is there?")

    def test_the_live_dad_turn_keeps_its_facts(self):
        out, failures = enforce_question_atomicity(self.ZZ_DAD)
        self.assertIn("request_plus_inquiry", failures)
        self.assertIn("Marrow Bay boatyard", out)
        self.assertIn("your aunt's", out)
        self.assertNotEqual(out.strip(), "You remember about him?")

    def test_the_live_dad_turn_still_asks_only_one_question(self):
        """The rule's actual job is still done."""
        out, _ = enforce_question_atomicity(self.ZZ_DAD)
        self.assertEqual(out.count("?"), 1)

    def test_an_answer_plus_its_own_question_drops_only_the_second(self):
        out, failures = enforce_question_atomicity(self.ZZ_MOM_EVENTS)
        self.assertIn("or_speculation", failures)
        self.assertIn("notable life events", out)
        self.assertIn("What stands out to you", out)
        self.assertNotIn("or what would you like", out)
        self.assertEqual(out.count("?"), 1)

    def test_the_mother_biography_answer_survives(self):
        """Names, places and provenance all reach the narrator."""
        out, _ = enforce_question_atomicity(self.MOTHER_BIOGRAPHY)
        for fragment in ("Alda Quillfeather", "Marrow Bay", "your biography"):
            self.assertIn(fragment, out)
        self.assertEqual(out.count("?"), 1)

    def test_an_empathic_opener_is_still_discarded(self):
        """The clause Case B was BUILT for keeps its old treatment.

        This is the boundary of the repair. Widening it to 'never drop a
        pre-pivot clause' would have been easier and would have undone
        WO-LORI-QUESTION-ATOMICITY-01.
        """
        out, _ = enforce_question_atomicity(
            "I can imagine that must have been a thrilling experience for "
            "you, and what drew you to that role?")
        self.assertEqual(out, "What drew you to that role?")

    def test_an_ordinary_predicate_with_no_name_or_date_survives(self):
        """The hole the first repair left, found by review 2026-09-21.

        `_carries_information` asked "is this informative?" and answered
        with positive signals — a second sentence, a digit, a proper
        noun, its own question. So it protected NAMED facts and deleted
        ordinary ones. Every fixture above happens to carry a name or a
        date, which is exactly why the suite passed.

        These are the commonest shape a biography answer takes.
        """
        for text, must_survive in (
            ("Your mother was a teacher, or would you like to tell me "
             "more?", "teacher"),
            ("He was a foreman, or shall we stay with what is there?",
             "foreman"),
            ("She worked as a teacher, or would you like to tell me "
             "more?", "teacher"),
            ("They lived by the river, and what do you remember about "
             "it?", "river"),
        ):
            with self.subTest(text=text[:40]):
                out, _ = enforce_question_atomicity(text)
                self.assertIn(must_survive, out)

    def test_the_default_is_to_keep(self):
        """A clause the rule does not recognise is preserved.

        The asymmetry is the design: a false positive costs one surplus
        sentence; a false negative deletes an answer and leaves a
        grammatical question where nothing downstream can see the loss.
        """
        from server.code.api.services.question_atomicity import (
            _carries_information)
        for unrecognised in ("the mill shut that winter",
                             "we walked there every Sunday",
                             "bread and dripping"):
            with self.subTest(clause=unrecognised):
                self.assertTrue(_carries_information(unrecognised))

    def test_carries_information_separates_the_two(self):
        from server.code.api.services.question_atomicity import (
            _carries_information)
        self.assertFalse(_carries_information(
            "I can imagine that was thrilling"))
        self.assertFalse(_carries_information("that sounds lovely"))
        self.assertTrue(_carries_information(
            "Your record lists her as born in Spokane"))      # proper noun
        self.assertTrue(_carries_information(
            "she was born in 1939"))                          # digit
        self.assertTrue(_carries_information(
            "Your mom. What stands out to you"))              # own question
        self.assertTrue(_carries_information(
            "Your dad. He worked there."))                    # two sentences


class CollectionGuardTests(unittest.TestCase):
    """Nothing in this file may sit after `unittest.main()`.

    Twenty-three tests have been lost to that mistake in this repository
    across two separate files. The suite reported a number and meant it;
    the number was simply smaller than the file.
    """

    def test_every_test_class_is_collected(self):
        import inspect
        mod = sys.modules[__name__]
        defined = {n for n, o in inspect.getmembers(mod, inspect.isclass)
                   if issubclass(o, unittest.TestCase)
                   and o.__module__ == __name__}
        loaded = unittest.defaultTestLoader.loadTestsFromModule(mod)
        seen = set()

        def walk(suite):
            for t in suite:
                if isinstance(t, unittest.TestSuite):
                    walk(t)
                else:
                    seen.add(type(t).__name__)
        walk(loaded)
        self.assertEqual(defined - seen, set(),
                         "test classes defined but never collected")

    def test_nothing_follows_unittest_main(self):
        src = Path(__file__).read_text(encoding="utf-8")
        idx = src.rindex("unittest.main(")
        tail = src[idx:]
        self.assertNotIn("\nclass ", tail)
        self.assertNotIn("\n    def test_", tail)


if __name__ == "__main__":
    unittest.main()
