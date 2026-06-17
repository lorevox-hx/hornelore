from __future__ import annotations

import unittest

from scripts.harness_lib import ChapterConfig, score_chapter
from tests.boris_quality._helpers import assert_row_fails, require_callable
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


if __name__ == "__main__":
    unittest.main()
