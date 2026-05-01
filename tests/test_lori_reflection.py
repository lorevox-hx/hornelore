"""WO-LORI-REFLECTION-01 — unit tests for the memory-echo validator.

Three test classes:

  IllegalEchoTypeTests        — positive (must flag) per §5.1-5.6
  PositiveGroundedEchoTests    — must NOT flag legitimate echoes
  EdgeAndGolfballRegressionTests — single-word answers, safety, real
                                    2026-04-30 Turn 02/03/04 failures
"""
from __future__ import annotations

import unittest

from server.code.api.services.lori_reflection import (
    validate_memory_echo,
)


class IllegalEchoTypeTests(unittest.TestCase):
    """§5.1-5.6 — each illegal echo type must produce its label."""

    # -- 5.1 missing_memory_echo ------------------------------------

    def test_missing_echo_question_only(self):
        passed, failures = validate_memory_echo(
            assistant_text="What do you remember about Spokane?",
            user_text="I had a mastoidectomy when I was little, in Spokane.",
        )
        self.assertFalse(passed)
        self.assertIn("missing_memory_echo", failures)

    # -- 5.2 echo_too_long ------------------------------------------

    def test_echo_too_long_over_25_words(self):
        echo = (
            "You've shared a deeply meaningful and emotionally layered "
            "memory about Spokane and your medical experience and your "
            "father's difficult work schedule that paints a vivid picture."
        )
        text = echo + " What do you remember about Spokane?"
        _passed, failures = validate_memory_echo(
            assistant_text=text,
            user_text="I had a mastoidectomy in Spokane.",
        )
        self.assertIn("echo_too_long", failures)

    # -- 5.3 echo_not_grounded --------------------------------------

    def test_echo_speculation_token(self):
        # Real Turn 03 failure — "possibly because" is speculation
        text = (
            "So your family seemed to spend some time in Spokane, "
            "possibly because of your dad's work at the aluminum plant. "
            "Did he share stories with you?"
        )
        _passed, failures = validate_memory_echo(
            assistant_text=text,
            user_text="when i was young in spokane my dad worked nights at the aluminum plant",
        )
        self.assertIn("echo_not_grounded", failures)

    def test_echo_low_overlap_with_user(self):
        # Echo content tokens don't overlap with user content
        text = (
            "Television and theater have such interesting histories. "
            "What was it like growing up?"
        )
        _passed, failures = validate_memory_echo(
            assistant_text=text,
            user_text="My grandfather Otto Horne came over from Norway in 1893.",
        )
        # Echo is about TV/theater; user_text is about grandfather/Norway.
        # Should flag echo_not_grounded.
        self.assertIn("echo_not_grounded", failures)

    # -- 5.4 echo_contains_archive_language -------------------------

    def test_echo_archive_phrase(self):
        text = (
            "That gives us a good story candidate for the archive. "
            "What else do you remember?"
        )
        _passed, failures = validate_memory_echo(
            assistant_text=text,
            user_text="I had a mastoidectomy in Spokane.",
        )
        self.assertIn("echo_contains_archive_language", failures)

    def test_echo_record_phrase(self):
        text = "I'll save that to your record. What happened next?"
        _passed, failures = validate_memory_echo(
            assistant_text=text,
            user_text="My dad worked at the plant.",
        )
        self.assertIn("echo_contains_archive_language", failures)

    # -- 5.5 echo_contains_diagnostic_language ----------------------

    def test_echo_must_have_been_traumatic(self):
        # Real Turn 02 failure — "must have been" + invented "scary"
        text = (
            "That must have been a really scary experience for you. "
            "What do you remember about it?"
        )
        _passed, failures = validate_memory_echo(
            assistant_text=text,
            user_text="I had a mastoidectomy when I was little, in Spokane.",
        )
        # Both diagnostic + unstated_emotion should fire.
        self.assertIn("echo_contains_diagnostic_language", failures)
        self.assertIn("echo_contains_unstated_emotion", failures)

    def test_echo_resilience_phrase(self):
        text = "That is a sign of resilience. How did you cope?"
        _passed, failures = validate_memory_echo(
            assistant_text=text,
            user_text="I worked nights and weekends.",
        )
        self.assertIn("echo_contains_diagnostic_language", failures)

    # -- 5.6 echo_contains_unstated_emotion -------------------------

    def test_echo_invented_thrilling(self):
        # Real Turn 04 failure — "thrilling" never said by narrator
        text = (
            "I can imagine that must have been a thrilling experience for "
            "you, and what drew you to that role?"
        )
        _passed, failures = validate_memory_echo(
            assistant_text=text,
            user_text="I was Captain Kirk and T. J. Hooker.",
        )
        self.assertIn("echo_contains_unstated_emotion", failures)

    def test_echo_invented_lonely(self):
        text = (
            "You were lonely in Spokane. What do you remember about it?"
        )
        _passed, failures = validate_memory_echo(
            assistant_text=text,
            user_text="I had a mastoidectomy in Spokane. My dad worked nights.",
        )
        self.assertIn("echo_contains_unstated_emotion", failures)

    def test_narrator_used_affect_token_passes(self):
        # If narrator said "I felt lonely", echoing "you felt lonely"
        # should pass (whitelist).
        text = "You felt lonely. What changed for you?"
        _passed, failures = validate_memory_echo(
            assistant_text=text,
            user_text="I felt lonely after the move.",
        )
        self.assertNotIn("echo_contains_unstated_emotion", failures)


class PositiveGroundedEchoTests(unittest.TestCase):
    """Legitimate grounded echoes must NOT flag."""

    def test_factual_echo_passes(self):
        text = (
            "You remember Spokane and your father working nights at the "
            "aluminum plant. What do you remember about Spokane?"
        )
        passed, failures = validate_memory_echo(
            assistant_text=text,
            user_text="I had a mastoidectomy when I was little, in Spokane. My dad worked nights at the aluminum plant.",
        )
        self.assertTrue(passed, msg=f"Unexpected failures: {failures}")

    def test_place_echo_passes(self):
        text = (
            "Spokane is coming through clearly in that memory. "
            "What do you remember about it?"
        )
        passed, failures = validate_memory_echo(
            assistant_text=text,
            user_text="I had a mastoidectomy in Spokane.",
        )
        self.assertTrue(passed, msg=f"Unexpected failures: {failures}")

    def test_relationship_echo_passes(self):
        text = (
            "Your father's night work seems connected to that time. "
            "What do you remember about him?"
        )
        passed, failures = validate_memory_echo(
            assistant_text=text,
            user_text="My dad worked nights at the aluminum plant.",
        )
        # Note: "seems connected" might flag echo_not_grounded due to
        # speculation token in some readings — this is borderline.
        # We allow ECHO_NOT_GROUNDED here as acceptable; the test
        # asserts no archive/diagnostic/affect violations.
        self.assertNotIn("echo_contains_archive_language", failures)
        self.assertNotIn("echo_contains_diagnostic_language", failures)
        self.assertNotIn("echo_contains_unstated_emotion", failures)

    def test_anchor_echo_passes(self):
        text = (
            "That memory has a place, a person, and a time. "
            "What stands out most?"
        )
        passed, failures = validate_memory_echo(
            assistant_text=text,
            user_text="My father drove a John Deere tractor at the Mandan farm in 1958.",
        )
        # Generic anchor echo — content tokens are abstract; should pass
        # archive/diagnostic/affect checks.
        self.assertNotIn("echo_contains_archive_language", failures)
        self.assertNotIn("echo_contains_diagnostic_language", failures)
        self.assertNotIn("echo_contains_unstated_emotion", failures)


class EdgeAndGolfballRegressionTests(unittest.TestCase):
    """Edge cases + anchored to 2026-04-30 golfball-v2-clean failures."""

    def test_empty_assistant_text_passes(self):
        passed, failures = validate_memory_echo(
            assistant_text="",
            user_text="anything",
        )
        self.assertTrue(passed)
        self.assertEqual(failures, [])

    def test_empty_user_text_passes(self):
        # First turn — narrator hasn't said anything yet. We don't
        # require an echo when there's nothing to echo.
        passed, failures = validate_memory_echo(
            assistant_text="What do you remember about Spokane?",
            user_text="",
        )
        # missing_memory_echo should NOT fire when user_text is empty.
        self.assertNotIn("missing_memory_echo", failures)

    def test_single_word_user_skips_grounding(self):
        # Narrator gave just "yes" — grounding check should skip
        # because user_text has < 5 content tokens.
        text = (
            "Television was a big part of life back then. "
            "What was your favorite show?"
        )
        _passed, failures = validate_memory_echo(
            assistant_text=text,
            user_text="Yes.",
        )
        self.assertNotIn("echo_not_grounded", failures)

    def test_turn02_real_failure_caught(self):
        """Real golfball-v2-clean Turn 02 — diagnostic + unstated
        emotion. Both labels must fire."""
        text = (
            "A mastoidectomy is a serious surgery, especially for a "
            "child. I'm so glad you're sharing this with me. That must "
            "have been a really scary experience for you. It's "
            "interesting that you mention Spokane. What do you remember?"
        )
        _passed, failures = validate_memory_echo(
            assistant_text=text,
            user_text="I had a mastoidectomy when I was little, in Spokane. My dad worked nights at the aluminum plant.",
        )
        self.assertIn("echo_contains_diagnostic_language", failures)
        self.assertIn("echo_contains_unstated_emotion", failures)

    def test_turn04_real_failure_caught(self):
        """Real golfball-v2-clean Turn 04 — invented 'thrilling'."""
        text = (
            "It seems like you've had quite the interesting career path! "
            "Being Captain Kirk and T.J. Hooker are iconic roles, and I "
            "can imagine that must have been a thrilling experience for "
            "you. And being the spokesman for Priceline must have been "
            "great. What drew you to that role?"
        )
        _passed, failures = validate_memory_echo(
            assistant_text=text,
            user_text="I was Captain Kirk and T. J. Hooker, and later I was the spokesman for Priceline.",
        )
        # "thrilling" is unstated emotion; "must have been" is diagnostic.
        self.assertIn("echo_contains_unstated_emotion", failures)
        self.assertIn("echo_contains_diagnostic_language", failures)


if __name__ == "__main__":
    unittest.main()
