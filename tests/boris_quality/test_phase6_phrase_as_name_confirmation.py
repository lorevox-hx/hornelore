from __future__ import annotations

import unittest

from scripts.harness_lib import ChapterConfig, score_chapter
from tests.boris_quality._helpers import assert_row_fails, require_callable


class PhraseAsNameConfirmationTests(unittest.TestCase):
    """Phase 6 — META_FEEDBACK false name-confirmation tests."""

    BAD_PHRASES = [
        "It Was The Air",
        "Originally Schong With A C",
        "Because The Adults Stopped Moving",
        "That I Still Picture Clearly",
        "You Learned To Stand Up And Sit Down And Kneel At The Right Times",
        "It Out Loud In The Empty Kitchen",
    ]

    def test_scorer_fails_phrase_as_name_confirmation_examples(self):
        chapter = ChapterConfig(
            label="Generic phrase-as-name",
            runtime71_era="earliest_years",
            text=(
                "I remember the air in Montreal and the way adults stopped moving "
                "when the subject of camp came up. These are phrases from a life "
                "story, not names."
            ),
            anchors=["montreal", "adults", "air"],
            word_budget=110,
        )
        for phrase in self.BAD_PHRASES:
            with self.subTest(phrase=phrase):
                response = f"Got it — {phrase}. Did I get that name right? What happened next?"
                score = score_chapter(chapter, response)
                assert_row_fails(self, score, "no_false_name_confirmation")
                assert_row_fails(self, score, "no_titlecase_phrase_as_name")

    def test_direct_name_confirmation_detector_rejects_titlecase_phrases(self):
        detector = require_callable([
            ("server.code.api.services.lori_meta_feedback", "is_valid_name_confirmation_candidate"),
            ("server.code.api.services.lori_meta_feedback", "should_ask_name_confirmation"),
            ("server.code.api.services.lori_response_guards", "is_valid_name_confirmation_candidate"),
        ])
        for phrase in self.BAD_PHRASES:
            with self.subTest(phrase=phrase):
                self.assertFalse(
                    bool(detector(phrase)),
                    f"Titlecase descriptive phrase must not be treated as a name: {phrase!r}",
                )

    def test_direct_name_confirmation_detector_allows_real_name_correction(self):
        detector = require_callable([
            ("server.code.api.services.lori_meta_feedback", "is_valid_name_confirmation_candidate"),
            ("server.code.api.services.lori_meta_feedback", "should_ask_name_confirmation"),
            ("server.code.api.services.lori_response_guards", "is_valid_name_confirmation_candidate"),
        ])
        self.assertTrue(bool(detector("Jon")))
        self.assertTrue(bool(detector("Eliseo")))


if __name__ == "__main__":
    unittest.main()
