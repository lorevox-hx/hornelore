from __future__ import annotations

import unittest

from scripts.harness_lib import ChapterConfig, score_chapter
from tests.boris_quality._helpers import (
    assert_row_fails,
    get_source,
    require_callable,
)
from tests.boris_quality.fixtures.boris_quality_cases import RICHARD_EARLIEST_NARRATOR


class MetaResponseLeakGuardTests(unittest.TestCase):
    """Phase 5 — direct and scorer tests for meta-response leakage."""

    META_BAD = (
        "Here is a response that follows the rules and guidelines:\n\n"
        "\"You mentioned Magee Hospital where you were born, your parents, and "
        "the Catholic Church. What do you remember about daily life in Oakland?\"\n\n"
        "This response reflects the narrator's mentions of Magee Hospital, the "
        "Catholic Church, and Oakland."
    )

    def _score(self, text):
        chapter = ChapterConfig(
            label="Richard Earliest",
            runtime71_era="earliest_years",
            text=RICHARD_EARLIEST_NARRATOR,
            anchors=["magee", "oakland", "catholic"],
            word_budget=110,
        )
        return score_chapter(chapter, text)

    def test_scorer_fails_meta_response_leak(self):
        score = self._score(self.META_BAD)
        assert_row_fails(self, score, "no_meta_response_leak")

    def test_direct_meta_response_guard_strips_preamble_and_postamble(self):
        guard = require_callable([
            ("server.code.api.services.lori_response_guards", "strip_meta_response_leak"),
            ("server.code.api.services.lori_response_guards", "sanitize_lori_response"),
            ("server.code.api.routers.chat_ws", "strip_meta_response_leak"),
            ("server.code.api.routers.chat_ws", "_strip_meta_response_leak"),
        ])
        cleaned = guard(self.META_BAD)
        if isinstance(cleaned, tuple):
            cleaned = cleaned[0]
        cleaned_lower = str(cleaned).lower()
        self.assertNotIn("here is a response", cleaned_lower)
        self.assertNotIn("follows the rules", cleaned_lower)
        self.assertNotIn("this response reflects", cleaned_lower)
        self.assertIn("magee", cleaned_lower)
        self.assertIn("oakland", cleaned_lower)


class ReasoningLeakGuardTests(unittest.TestCase):
    """BUG-LORI-REASONING-LEAK-01 (2026-07-27).

    A live Lori turn was persisted as assistant content with the model's
    own planning sentence in front of the real reply:

      "The narrator is speaking in English, so I will respond in English
       too. \"Hi there, I'm Lori. ...\""

    The guard pipeline was alive and ran before persistence
    (chat_ws.py calls apply_response_guards ahead of the persist + WS
    done event). It was detect_meta_response_leak() that had no pattern
    for either shape: the 2026-07-07 preamble regex covers "I will
    respond BY/WITH/USING" but not "respond IN <language>", and nothing
    covered a third-person "The narrator is ..., so I ..." planning
    clause.

    Scope of the fix is the detector pattern only. These tests pin the
    verbatim leak, prove the existing repair path recovers the quoted
    greeting rather than falling through to the deterministic
    continuation, and pin the false-positive boundary.
    """

    # Verbatim, from turns.id at ts 2026-07-27T04:17:38.134681,
    # conv tdlab_9538cd88-5c8b-4da4-b2a9-2a03f8db32a3.
    LEAK_2026_07_27 = (
        "The narrator is speaking in English, so I will respond in "
        "English too. \"Hi there, I'm Lori. I'm here to listen to your "
        "story and learn more about your experiences. Would you like to "
        "share what you were working on in Bismarck?\""
    )

    # The reply that was always sitting inside the quotes.
    RECOVERED = (
        "Hi there, I'm Lori. I'm here to listen to your story and learn "
        "more about your experiences. Would you like to share what you "
        "were working on in Bismarck?"
    )

    def _detector(self):
        return require_callable([
            ("server.code.api.services.lori_response_guards",
             "detect_meta_response_leak"),
        ])

    def _repair(self):
        return require_callable([
            ("server.code.api.services.lori_response_guards",
             "strip_meta_response_leak"),
            ("server.code.api.services.lori_response_guards",
             "sanitize_lori_response"),
        ])

    @staticmethod
    def _text(value):
        return str(value[0] if isinstance(value, tuple) else value)

    # ── Acceptance 1 ──────────────────────────────────────────────────
    def test_the_verbatim_2026_07_27_leak_is_detected(self):
        self.assertTrue(self._detector()(self.LEAK_2026_07_27))

    # ── Acceptance 2 ──────────────────────────────────────────────────
    def test_repair_returns_the_quoted_greeting_not_the_meta_sentence(self):
        cleaned = self._text(self._repair()(self.LEAK_2026_07_27))
        self.assertEqual(cleaned, self.RECOVERED)
        lowered = cleaned.lower()
        self.assertNotIn("the narrator is speaking", lowered)
        self.assertNotIn("i will respond in english", lowered)
        # Not the deterministic last-resort continuation.
        self.assertNotEqual(cleaned, "Tell me more about that.")

    # ── The two shapes, isolated ──────────────────────────────────────
    def test_language_planning_clause_is_detected_on_its_own(self):
        detect = self._detector()
        for shape in (
            "I will respond in English too.",
            "I'll respond in Spanish since that is what they used.",
            "I'll reply in the same language.",
            "I will continue in Spanish.",
        ):
            with self.subTest(shape=shape):
                self.assertTrue(detect(shape))

    def test_third_person_narrator_planning_clause_is_detected_on_its_own(self):
        detect = self._detector()
        for shape in (
            "The narrator is speaking in English, so I will respond in kind.",
            "The narrator has said very little, so I should keep it short.",
            "The narrator was describing a photo, so I will ask about it.",
        ):
            with self.subTest(shape=shape):
                self.assertTrue(detect(shape))

    # ── Acceptance 4 — the false-positive boundary ────────────────────
    def test_legitimate_narrator_facing_text_survives_untouched(self):
        detect, repair = self._detector(), self._repair()
        for good in (
            "He never knew how to respond in a crisis. What did that "
            "feel like for you as a boy?",
            "You said you would respond in kind, and you did. Tell me "
            "more about what happened next.",
            "That was the year the narrator of the family stories, your "
            "grandmother, finally moved to Ohio.",
            "I will respond to that letter someday, you told her. Did "
            "you ever write it?",
        ):
            with self.subTest(good=good[:40]):
                self.assertFalse(detect(good))
                self.assertEqual(self._text(repair(good)), good)

    # ── Acceptance 3 — the pattern that already worked still works ────
    def test_the_2026_07_10_shape_is_still_detected(self):
        older = (
            "You're referring to a specific photo, but since I don't have "
            "any prior conversation or context about a photo, I'll assume "
            "you're asking about a photo you've shared recently. However, "
            "since there's no prior conversation, I'll respond with a "
            "neutral message."
        )
        self.assertTrue(self._detector()(older))

    # ── Acceptance 6 — detector-only change ───────────────────────────
    def test_the_repair_path_was_not_rewritten(self):
        """The fix is a pattern, not a new recovery branch.

        repair_meta_response_leak keeps its quoted-draft-first recovery
        order and its deterministic fallbacks; if someone replaces that
        with special-casing for this bug, this test says so.
        """
        src = get_source(
            "server.code.api.services.lori_response_guards")
        self.assertIn("_QUOTED_DRAFT_RX", src)
        self.assertIn("Tell me more about that.", src)
        self.assertIn("Cu\u00e9ntame m\u00e1s sobre eso.", src)
        # No bug-specific string matching smuggled into the repair.
        self.assertNotIn("Bismarck", src)


if __name__ == "__main__":
    unittest.main()
