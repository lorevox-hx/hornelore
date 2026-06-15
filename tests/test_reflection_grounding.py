"""WO-LORI-STORY-FIRST-PHASE-1-01 (2026-06-14) — reflection grounding tests.

Covers acceptance gate #1: reflection grounding — concrete narrator
content in every normal turn; forbidden generic empathy phrases never
appear; deterministic fallback template uses extract_concrete_anchor.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api.services.reflection_grounding import (  # noqa: E402
    check_reflection_grounding,
    is_forbidden_empathy_opener,
    build_fallback_reflection,
    extract_narrator_content_tokens,
)


class ReflectionGroundingTokenMatchTest(unittest.TestCase):
    NARRATOR_A = (
        "I had a mastoidectomy when I was little, in Spokane. "
        "My dad worked nights at the aluminum plant."
    )

    def test_grounded_response_passes(self):
        lori = "Spokane and the aluminum plant — that already paints a picture."
        r = check_reflection_grounding(lori, self.NARRATOR_A)
        self.assertTrue(r.passed)
        self.assertIn("spokane", r.anchor_overlap)

    def test_kinship_canonicalization_counts(self):
        # narrator says "dad", Lori says "father" — should match via kinship canon
        lori = "Your father working nights — what was that like?"
        r = check_reflection_grounding(lori, self.NARRATOR_A)
        self.assertTrue(r.passed)

    def test_stem_canonicalization_counts(self):
        # narrator says "worked", Lori says "working" — stem match
        lori = "Working nights in Spokane stays with me."
        r = check_reflection_grounding(lori, self.NARRATOR_A)
        self.assertTrue(r.passed)

    def test_no_anchor_fails(self):
        lori = "I appreciate you opening up. Let me know what comes to mind."
        r = check_reflection_grounding(lori, self.NARRATOR_A)
        self.assertFalse(r.passed)
        self.assertIn("no_anchor_overlap", r.failure_reason)

    def test_forbidden_empathy_opener_fails(self):
        lori = "That sounds difficult. Tell me more about it."
        r = check_reflection_grounding(lori, self.NARRATOR_A)
        self.assertFalse(r.passed)
        self.assertEqual(r.forbidden_phrase, "that sounds difficult")

    def test_forbidden_AND_no_anchor_reports_both(self):
        lori = "That sounds difficult. I can imagine."
        r = check_reflection_grounding(lori, self.NARRATOR_A)
        self.assertFalse(r.passed)
        self.assertIn("no_anchor_overlap", r.failure_reason)
        self.assertIn("forbidden_empathy_opener", r.failure_reason)

    def test_trivial_narrator_waives_anchor_requirement(self):
        # narrator turn < 4 content tokens → anchor check skipped
        r = check_reflection_grounding("That stays with me.", "yes")
        self.assertTrue(r.passed)

    def test_trivial_narrator_still_blocks_forbidden_phrase(self):
        r = check_reflection_grounding("That sounds difficult.", "yes")
        self.assertFalse(r.passed)
        self.assertEqual(r.forbidden_phrase, "that sounds difficult")


class ForbiddenEmpathyOpenerTest(unittest.TestCase):
    """All the forbidden phrases must be detected at sentence-start
    position (within ~120 chars of response opening)."""

    def test_each_forbidden_opener_detected(self):
        cases = (
            "That sounds difficult. Tell me more.",
            "That sounds hard.",
            "I can imagine.",
            "I cannot imagine.",
            "That must have been heavy.",
            "Thank you for sharing.",
            "I'm so sorry.",
            "That's so meaningful.",
            "How meaningful.",
        )
        for text in cases:
            with self.subTest(text=text):
                self.assertTrue(is_forbidden_empathy_opener(text))

    def test_substantive_response_not_falsely_blocked(self):
        # Even responses that talk ABOUT empathy aren't flagged when
        # they don't OPEN with one of the forbidden phrases.
        cases = (
            "Spokane stays with me.",
            "A long winter in the aluminum plant. What stands out?",
            "Your father worked nights — what was that like?",
        )
        for text in cases:
            with self.subTest(text=text):
                self.assertFalse(is_forbidden_empathy_opener(text))


class FallbackReflectionTest(unittest.TestCase):
    NARRATOR = (
        "I had a mastoidectomy when I was little, in Spokane. "
        "My dad worked nights at the aluminum plant."
    )

    def test_fallback_uses_concrete_anchor(self):
        fb = build_fallback_reflection(self.NARRATOR, 0)
        self.assertIn("Spokane", fb)

    def test_fallback_does_not_span_sentence_boundary(self):
        # Regression: the upstream extract_concrete_anchor used to
        # return "Spokane. My" across sentence boundaries. The fix
        # ensures the fallback opens with a clean anchor.
        fb = build_fallback_reflection(self.NARRATOR, 0)
        # The anchor sentence "Spokane." should be followed by a pause
        # token, NOT "My" or another sentence-start word.
        self.assertNotIn("Spokane. My", fb)

    def test_fallback_pause_token_rotates_deterministically(self):
        # Same narrator + different counter = different pause token
        fbs = [build_fallback_reflection(self.NARRATOR, i) for i in range(4)]
        # All 4 pause tokens are distinct
        pause_tokens = [
            fb.split(". ", 1)[1] for fb in fbs if ". " in fb
        ]
        self.assertEqual(len(set(pause_tokens)), len(pause_tokens))

    def test_fallback_clamps_negative_counter(self):
        fb_neg = build_fallback_reflection(self.NARRATOR, -10)
        fb_zero = build_fallback_reflection(self.NARRATOR, 0)
        self.assertEqual(fb_neg, fb_zero)

    def test_fallback_includes_continuation_when_provided(self):
        fb = build_fallback_reflection(
            self.NARRATOR, 0, continuation="What stands out most?",
        )
        self.assertTrue(fb.endswith("?"))

    def test_fallback_handles_trivial_narrator(self):
        fb = build_fallback_reflection("yes", 0)
        # No anchor → just the pause token, possibly with continuation
        self.assertTrue(fb)
        self.assertNotIn("Spokane", fb)


class ContentTokenExtractionTest(unittest.TestCase):
    def test_extracts_kinship_canonical_form(self):
        tokens = extract_narrator_content_tokens("My dad worked nights.")
        self.assertIn("father", tokens)
        self.assertIn("work", tokens)
        self.assertIn("night", tokens)

    def test_empty_input_returns_empty_set(self):
        self.assertEqual(extract_narrator_content_tokens(""), set())
        self.assertEqual(extract_narrator_content_tokens(None), set())

    def test_stopwords_filtered(self):
        tokens = extract_narrator_content_tokens("I had a small dog.")
        self.assertNotIn("i", tokens)
        self.assertNotIn("had", tokens)
        self.assertNotIn("a", tokens)
        self.assertIn("small", tokens)
        self.assertIn("dog", tokens)


if __name__ == "__main__":
    unittest.main(verbosity=2)
