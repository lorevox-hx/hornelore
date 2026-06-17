from __future__ import annotations

import unittest

from scripts.harness_lib import ChapterConfig, score_chapter
from tests.boris_quality._helpers import assert_row_fails, assert_row_passes
from tests.boris_quality.fixtures.boris_quality_cases import FAILURE_CASES


class HarnessScorerQualityRowsTests(unittest.TestCase):
    """Phase 2 — harden the long-narration harness scorer.

    These tests are full executable red tests. Before the scorer patch they
    should fail because scripts/harness_lib.py only has the original 8 rows.
    """

    REQUIRED_NEW_ROWS = [
        "no_false_name_confirmation",
        "no_got_it_stub",
        "no_titlecase_phrase_as_name",
        "response_not_fragmented",
        "minimum_anchor_count",
        "no_meta_response_leak",
        "no_titlecased_anchor_cascade",
        "no_seeded_fact_intake_question",
        "no_broken_code_mix",
        "direct_human_voice",
    ]

    def _score(self, case, response_text: str):
        chapter = ChapterConfig(
            label=case.label,
            runtime71_era="earliest_years",
            text=case.narrator_text,
            anchors=case.anchors,
            word_budget=110,
        )
        return score_chapter(chapter, response_text)

    def test_scorer_exposes_all_new_quality_rows(self):
        case = FAILURE_CASES[0]
        score = self._score(case, case.lori_good)
        rows = score["rows"]
        for row in self.REQUIRED_NEW_ROWS:
            self.assertIn(row, rows, f"Missing required Boris scorer row: {row}")

    def test_bad_outputs_fail_the_specific_rows_they_are_supposed_to_fail(self):
        for case in FAILURE_CASES:
            with self.subTest(case=case.label):
                score = self._score(case, case.lori_bad)
                for row in case.expected_failed_rows:
                    assert_row_fails(self, score, row)

    def test_good_outputs_pass_new_quality_rows(self):
        for case in FAILURE_CASES:
            with self.subTest(case=case.label):
                score = self._score(case, case.lori_good)
                for row in self.REQUIRED_NEW_ROWS:
                    if row == "no_seeded_fact_intake_question":
                        # Some generic good outputs have no seeded profile context;
                        # scorer can PASS by absence.
                        assert_row_passes(self, score, row)
                    else:
                        assert_row_passes(self, score, row)

    def test_word_budget_honored_fails_for_pat_110_word_response_over_budget(self):
        chapter = ChapterConfig(
            label="Pat Earliest",
            runtime71_era="earliest_years",
            text=(
                "I was born in Akron. My father Harold worked at Goodyear. I grew up "
                "around rules and routines and later became a teacher. Betty was part "
                "of the story from the beginning."
            ),
            anchors=["akron", "harold", "goodyear", "betty"],
            word_budget=90,
        )
        response = " ".join(["word"] * 125) + " What do you remember about Akron?"
        score = score_chapter(chapter, response)
        self.assertEqual(score["rows"]["word_budget_honored"], "FAIL")


if __name__ == "__main__":
    unittest.main()
