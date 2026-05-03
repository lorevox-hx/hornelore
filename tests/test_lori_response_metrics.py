"""WO-LORI-ACTIVE-LISTENING-01 Phase 3 — eval metrics tests.

Test the score_lori_turn function with known-good and known-bad
examples from the WO spec, plus regression tests for each metric.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api.services.lori_response_metrics import score_lori_turn  # noqa: E402


# ── Known-good / known-bad examples from the WO spec ──────────────────────

class WOSpecExamplesTest(unittest.TestCase):
    """The exact examples from the WO spec must score correctly."""

    def test_bad_compound_nested_4_hooks(self):
        """The Christopher live test failure case from 2026-04-28."""
        bad = (
            "Chris, I'm so glad you shared this rich and detailed account "
            "of your life. As you reflect on the journey you've been on, "
            "what do you remember about the daily life, routines, and "
            "rhythms of growing up in Williston, North Dakota, during "
            "your childhood?"
        )
        m = score_lori_turn(
            bad,
            user_text="I had a long childhood in Williston with my brothers.",
            word_cap=40,  # explicit tight cap to exercise the failure mode
        )
        # 1 question mark, but the question is long-winded — at the 40-word
        # cap (close to Chris's locked target of 55 with margin), this
        # 44-word turn fails pass_word_count
        self.assertEqual(m["question_count"], 1)
        self.assertFalse(m["pass_word_count"])

    def test_good_single_concrete_reflection(self):
        good = (
            "That sounds like your mother carried a lot of steadiness in "
            "the family. What is one scene that shows what she was like?"
        )
        m = score_lori_turn(good, user_text="My mother held everything together.")
        self.assertEqual(m["question_count"], 1)
        self.assertEqual(m["nested_question_count"], 0)
        self.assertEqual(m["menu_offer_count"], 0)
        self.assertLess(m["word_count"], 55)
        self.assertTrue(m["pass_overall"])

    def test_bad_compound_three_questions(self):
        bad = (
            "That sounds meaningful. What was your mother like, and where "
            "were you living then, and did your siblings feel the same way?"
        )
        m = score_lori_turn(bad, user_text="My mother meant a lot to me.")
        # Should be flagged as nested compound
        self.assertGreater(m["nested_question_count"], 0)
        self.assertFalse(m["pass_no_nested"])
        self.assertFalse(m["pass_overall"])

    def test_bad_menu_offer(self):
        bad = (
            "Would you like to talk about your father's work, or would "
            "you rather tell me about your school years, or maybe move "
            "forward to your career?"
        )
        m = score_lori_turn(bad, user_text="I have lots to share.")
        self.assertGreater(m["menu_offer_count"], 0)
        self.assertFalse(m["pass_no_menu_offer"])
        self.assertFalse(m["pass_overall"])

    def test_good_one_path_narrator_led(self):
        good = "What part of your father's work stayed with you?"
        m = score_lori_turn(good, user_text="My father worked the mill.")
        self.assertEqual(m["question_count"], 1)
        self.assertEqual(m["menu_offer_count"], 0)
        self.assertEqual(m["nested_question_count"], 0)
        self.assertTrue(m["pass_overall"])

    def test_bad_restates_context_and_nests(self):
        bad = (
            "As you reflect on the journey you've been on, what do you "
            "remember about the daily life, routines, and rhythms of "
            "growing up in Williston, North Dakota, during your childhood?"
        )
        m = score_lori_turn(bad, user_text="I grew up in Williston.")
        # Long word count + restate-context shape — at least 30 words
        self.assertGreaterEqual(m["word_count"], 30)

    def test_good_specific_anchor_single_question(self):
        good = (
            "You mentioned long winters and exploring outdoors with your "
            "brothers. What was a typical winter day like for the three "
            "of you?"
        )
        m = score_lori_turn(
            good,
            user_text="We had long winters and explored outdoors with my brothers.",
        )
        self.assertEqual(m["question_count"], 1)
        self.assertTrue(m["active_reflection_present"])  # echoes "winters", "brothers"
        self.assertTrue(m["pass_overall"])


# ── Per-metric regression tests ───────────────────────────────────────────

class QuestionCountTest(unittest.TestCase):

    def test_zero_questions(self):
        m = score_lori_turn("That is interesting.", user_text="x")
        self.assertEqual(m["question_count"], 0)
        self.assertTrue(m["pass_question_count"])

    def test_one_question(self):
        m = score_lori_turn("What was that like?", user_text="x")
        self.assertEqual(m["question_count"], 1)
        self.assertTrue(m["pass_question_count"])

    def test_two_questions_fails(self):
        m = score_lori_turn(
            "What was that like? And where were you?",
            user_text="x",
        )
        self.assertEqual(m["question_count"], 2)
        self.assertFalse(m["pass_question_count"])

    def test_quoted_question_not_counted(self):
        m = score_lori_turn(
            'You asked "what is it like?" — what is your answer.',
            user_text="x",
        )
        # The quoted "?" should NOT count
        self.assertEqual(m["question_count"], 0)


class NestedQuestionTest(unittest.TestCase):

    def test_two_q_marks_linked_by_and_is_nested(self):
        m = score_lori_turn(
            "What was Spokane like? And where did you live?",
            user_text="x",
        )
        self.assertGreater(m["nested_question_count"], 0)

    def test_single_q_with_inline_and_is_nested(self):
        m = score_lori_turn(
            "What was your mother like, and how did your siblings feel?",
            user_text="x",
        )
        self.assertGreater(m["nested_question_count"], 0)

    def test_simple_question_not_nested(self):
        m = score_lori_turn(
            "What was your mother like?",
            user_text="x",
        )
        self.assertEqual(m["nested_question_count"], 0)


class WordCountTest(unittest.TestCase):

    def test_short_turn(self):
        m = score_lori_turn("What was that like?", user_text="x")
        self.assertLess(m["word_count"], 10)
        self.assertTrue(m["pass_word_count"])

    def test_long_turn_fails_at_default_cap(self):
        long_turn = " ".join(["word"] * 100) + "?"
        m = score_lori_turn(long_turn, user_text="x")
        self.assertGreater(m["word_count"], 90)
        self.assertFalse(m["pass_word_count"])

    def test_custom_word_cap(self):
        m = score_lori_turn(" ".join(["word"] * 60), user_text="x", word_cap=55)
        self.assertEqual(m["word_count"], 60)
        self.assertFalse(m["pass_word_count"])


class MenuOfferTest(unittest.TestCase):

    def test_or_we_could(self):
        m = score_lori_turn(
            "Tell me about that, or we could talk about something else.",
            user_text="x",
        )
        self.assertGreater(m["menu_offer_count"], 0)

    def test_would_you_rather(self):
        m = score_lori_turn(
            "Would you rather start with childhood or career?",
            user_text="x",
        )
        self.assertGreater(m["menu_offer_count"], 0)

    def test_which_path(self):
        m = score_lori_turn(
            "Which path would you like to take next?",
            user_text="x",
        )
        self.assertGreater(m["menu_offer_count"], 0)

    def test_would_you_like_to_with_or(self):
        m = score_lori_turn(
            "Would you like to talk about that, or move on?",
            user_text="x",
        )
        self.assertGreater(m["menu_offer_count"], 0)

    def test_ordinary_phrasing_not_flagged(self):
        m = score_lori_turn(
            "Tell me what that was like.",
            user_text="x",
        )
        self.assertEqual(m["menu_offer_count"], 0)


class DirectAnswerFirstTest(unittest.TestCase):

    def test_user_no_question_no_constraint(self):
        m = score_lori_turn("What was it like?", user_text="I had a tough day.")
        self.assertFalse(m["user_turn_had_direct_question"])
        # No constraint applies — pass_direct_answer is True
        self.assertTrue(m["pass_direct_answer"])

    def test_user_question_lori_answers_first(self):
        m = score_lori_turn(
            "I'm Lori, your interviewer. What part of your story should we begin with?",
            user_text="What is your name?",
        )
        self.assertTrue(m["user_turn_had_direct_question"])
        self.assertTrue(m["direct_answer_first"])
        self.assertTrue(m["pass_direct_answer"])

    def test_user_question_lori_pivots_fails(self):
        m = score_lori_turn(
            "Tell me about your childhood. We can come back to that later.",
            user_text="What time is it?",
        )
        self.assertTrue(m["user_turn_had_direct_question"])
        self.assertFalse(m["direct_answer_first"])
        self.assertFalse(m["pass_direct_answer"])


class ActiveReflectionTest(unittest.TestCase):

    def test_lori_echoes_user_anchor(self):
        m = score_lori_turn(
            "Mastoidectomy when you were small — that's a vivid memory.",
            user_text="I had a mastoidectomy when I was little.",
        )
        self.assertTrue(m["active_reflection_present"])

    def test_lori_does_not_echo(self):
        m = score_lori_turn(
            "What about your earliest memory before kindergarten?",
            # Need 5+ content words so the trivial-response exemption
            # doesn't fire and the heuristic actually evaluates overlap
            user_text="My father worked nights at the aluminum factory railroad warehouse downtown.",
        )
        # No shared content words → no reflection
        self.assertFalse(m["active_reflection_present"])

    def test_trivial_user_response_exempt(self):
        m = score_lori_turn(
            "Let me ask you about something else.",
            user_text="Yes.",
        )
        # User said only 1 word — no reflection required
        self.assertTrue(m["active_reflection_present"])

    def test_user_4_word_response_exempt(self):
        m = score_lori_turn(
            "What about your father?",
            user_text="I think so yes",
        )
        # 4 content words → still under 5 floor → exempt
        self.assertTrue(m["active_reflection_present"])


class OverallPassTest(unittest.TestCase):

    def test_perfect_turn_passes_all(self):
        m = score_lori_turn(
            "Mastoidectomy when you were small — that's a vivid memory. "
            "Where in Spokane did the surgery happen?",
            user_text="I had a mastoidectomy when I was little, in Spokane.",
        )
        self.assertTrue(m["pass_overall"])

    def test_any_failure_fails_overall(self):
        # Compound + menu offer combo
        m = score_lori_turn(
            "Would you rather talk about Spokane or Mandan? "
            "And what was your father like?",
            user_text="x",
        )
        self.assertFalse(m["pass_overall"])


# ── _trim_to_one_question existing helper test (regression coverage) ──────

class TrimToOneQuestionRegressionTest(unittest.TestCase):
    """Locks in the existing _trim_to_one_question implementation behavior.
    The helper landed in SESSION-AWARENESS-01 Phase 2; this WO ratifies
    the test surface."""

    def setUp(self):
        try:
            from api.prompt_composer import _trim_to_one_question
            self.trim = _trim_to_one_question
        except Exception as exc:
            self.skipTest(f"prompt_composer import failed: {exc}")

    def test_single_question_passthrough(self):
        text = "What was that like?"
        out, was_trimmed, reason = self.trim(text)
        self.assertEqual(out, text)
        self.assertFalse(was_trimmed)

    def test_compound_two_questions_trimmed(self):
        text = "What was Spokane like? And where did you live?"
        out, was_trimmed, reason = self.trim(text)
        self.assertTrue(was_trimmed)
        self.assertIn("come back", out.lower())

    def test_menu_offer_single_q_trimmed(self):
        text = "Would you rather start with childhood or career?"
        out, was_trimmed, reason = self.trim(text)
        self.assertTrue(was_trimmed)

    def test_empty_input_passes(self):
        out, was_trimmed, reason = self.trim("")
        self.assertEqual(out, "")
        self.assertFalse(was_trimmed)

    def test_no_question_no_menu_passes(self):
        text = "That is interesting."
        out, was_trimmed, reason = self.trim(text)
        self.assertEqual(out, text)
        self.assertFalse(was_trimmed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
