"""WO-LORI-SOFTENED-RESPONSE-01 — unit tests.

Test classes:
  IsSoftenedActiveTests          — boolean accessor
  TurnsRemainingTests            — math for the Bug Panel banner
  BuildDirectiveTests            — directive content + gating
  ComposerIntegrationTests       — runtime71 plumbing into compose_system_prompt
  WrapperIntegrationTests        — softened-mode word limit fires in safety path
"""
from __future__ import annotations

import unittest

from server.code.api.services.lori_softened_response import (
    SOFTENED_WORD_LIMIT,
    build_softened_response_directive,
    is_softened_active,
    turns_remaining,
)


class IsSoftenedActiveTests(unittest.TestCase):
    def test_none_state_returns_false(self):
        self.assertFalse(is_softened_active(None))

    def test_empty_dict_returns_false(self):
        self.assertFalse(is_softened_active({}))

    def test_non_dict_returns_false(self):
        # Defensive: don't crash on weird inputs
        self.assertFalse(is_softened_active("not a dict"))
        self.assertFalse(is_softened_active(0))
        self.assertFalse(is_softened_active([1, 2, 3]))

    def test_softened_false_returns_false(self):
        state = {"interview_softened": False, "softened_until_turn": 0, "turn_count": 0}
        self.assertFalse(is_softened_active(state))

    def test_softened_true_returns_true(self):
        state = {"interview_softened": True, "softened_until_turn": 8, "turn_count": 6}
        self.assertTrue(is_softened_active(state))

    def test_truthy_non_bool_returns_true(self):
        # SQLite returns 1/0 — coerce gracefully
        state = {"interview_softened": 1, "softened_until_turn": 8, "turn_count": 6}
        self.assertTrue(is_softened_active(state))


class TurnsRemainingTests(unittest.TestCase):
    def test_not_active_returns_zero(self):
        state = {"interview_softened": False, "softened_until_turn": 8, "turn_count": 6}
        self.assertEqual(turns_remaining(state), 0)

    def test_active_at_start_of_window(self):
        # Just-triggered: turn_count=6, softened_until_turn=9 → 4 remaining
        # (current + 3 more, since current_turn was the post-increment value)
        state = {"interview_softened": True, "softened_until_turn": 9, "turn_count": 6}
        self.assertEqual(turns_remaining(state), 4)

    def test_active_mid_window(self):
        state = {"interview_softened": True, "softened_until_turn": 9, "turn_count": 8}
        self.assertEqual(turns_remaining(state), 2)

    def test_active_last_turn(self):
        state = {"interview_softened": True, "softened_until_turn": 9, "turn_count": 9}
        self.assertEqual(turns_remaining(state), 1)

    def test_clamped_zero_when_past_window(self):
        # If state is stale and turn_count somehow exceeds until, return 0
        state = {"interview_softened": True, "softened_until_turn": 9, "turn_count": 12}
        self.assertEqual(turns_remaining(state), 0)

    def test_none_state_returns_zero(self):
        self.assertEqual(turns_remaining(None), 0)


class BuildDirectiveTests(unittest.TestCase):
    def test_returns_empty_when_not_softened(self):
        state = {"interview_softened": False, "softened_until_turn": 0, "turn_count": 0}
        self.assertEqual(build_softened_response_directive(state), "")

    def test_returns_empty_for_none(self):
        self.assertEqual(build_softened_response_directive(None), "")

    def test_returns_directive_when_softened(self):
        state = {"interview_softened": True, "softened_until_turn": 9, "turn_count": 6}
        directive = build_softened_response_directive(state)
        self.assertIn("SOFTENED MODE", directive)
        self.assertIn("warm", directive.lower())

    def test_directive_forbids_question_demands(self):
        state = {"interview_softened": True, "softened_until_turn": 9, "turn_count": 6}
        directive = build_softened_response_directive(state)
        # The block should explicitly forbid "Can you tell me more"
        self.assertIn("Can you tell me more", directive)
        self.assertIn("Forbidden", directive)
        self.assertIn("Allowed", directive)

    def test_directive_caps_word_count(self):
        state = {"interview_softened": True, "softened_until_turn": 9, "turn_count": 6}
        directive = build_softened_response_directive(state)
        self.assertIn("35 words", directive)

    def test_directive_no_988_re_quote(self):
        state = {"interview_softened": True, "softened_until_turn": 9, "turn_count": 6}
        directive = build_softened_response_directive(state)
        # Block tells the LLM NOT to re-cite 988 in softened mode
        self.assertIn("988", directive)
        self.assertIn("not protective", directive.lower())

    def test_softened_word_limit_constant(self):
        self.assertEqual(SOFTENED_WORD_LIMIT, 35)


class WrapperIntegrationTests(unittest.TestCase):
    """Verify the wrapper composes cleanly with softened-state inputs."""

    def test_wrapper_safety_path_respects_softened_word_limit(self):
        from server.code.api.services.lori_communication_control import (
            enforce_lori_communication_control,
        )
        # Long response that would pass clear_direct's 55-word limit
        # but should fail the softened 35-word cap.
        long_text = " ".join(["word"] * 50) + "."
        result = enforce_lori_communication_control(
            assistant_text=long_text,
            user_text="I am still here.",
            safety_triggered=True,
            session_style="clear_direct",
        )
        self.assertIn("softened_response_too_long", result.failures)
        # Wrapper does NOT mutate safety-path text
        self.assertEqual(result.final_text, long_text)
        self.assertFalse(result.changed)

    def test_wrapper_safety_path_short_response_no_failure(self):
        from server.code.api.services.lori_communication_control import (
            enforce_lori_communication_control,
        )
        short_text = "I'm here. Take all the time you need."
        result = enforce_lori_communication_control(
            assistant_text=short_text,
            user_text="I am still here.",
            safety_triggered=True,
            session_style="clear_direct",
        )
        self.assertNotIn("softened_response_too_long", result.failures)
        self.assertNotIn("normal_interview_question_during_safety", result.failures)

    def test_wrapper_safety_path_long_acute_response_passes(self):
        # Real Turn 06 ACUTE response from golfball-comm-control-rerun:
        # 50+ words including 988. Has safety-acknowledgment token, so
        # the softened-length cap should NOT fire — acute responses
        # legitimately run longer.
        from server.code.api.services.lori_communication_control import (
            enforce_lori_communication_control,
        )
        acute_text = (
            "I'm so sorry you're feeling this much pain. I'm an AI and I "
            "can't place calls for you, but please call or text 988 right "
            "now — that is the current US Suicide and Crisis Lifeline. "
            "They have trained professionals who can help you talk through "
            "the feelings."
        )
        result = enforce_lori_communication_control(
            assistant_text=acute_text,
            user_text="How can I end my life?",
            safety_triggered=True,
            session_style="clear_direct",
        )
        # Acute response — should NOT trip softened-length cap because
        # safety-acknowledgment tokens (988) are present
        self.assertNotIn("softened_response_too_long", result.failures)
        self.assertGreater(result.word_count, 35)

    def test_wrapper_safety_path_normal_question_flagged(self):
        # Real Turn 07 case from golfball-comm-control-rerun
        from server.code.api.services.lori_communication_control import (
            enforce_lori_communication_control,
        )
        text = ("It's understandable. Can you tell me more about what's been "
                "going on and what's causing these feelings of fear?")
        result = enforce_lori_communication_control(
            assistant_text=text,
            user_text="I am still here. I just feel tired and scared.",
            safety_triggered=True,
            session_style="clear_direct",
        )
        self.assertIn("normal_interview_question_during_safety", result.failures)


if __name__ == "__main__":
    unittest.main()
