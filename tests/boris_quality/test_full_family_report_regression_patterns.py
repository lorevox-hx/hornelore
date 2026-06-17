from __future__ import annotations

import unittest

from scripts.harness_lib import ChapterConfig, score_chapter
from tests.boris_quality._helpers import assert_row_fails
from tests.boris_quality.fixtures.boris_quality_cases import FAILURE_CASES


class FullFamilyRegressionPatternTests(unittest.TestCase):
    """Regression locks for the actual patterns surfaced by the full-family run."""

    def test_every_known_full_family_bad_pattern_fails_at_least_one_new_quality_row(self):
        for case in FAILURE_CASES:
            with self.subTest(case=case.label):
                chapter = ChapterConfig(
                    label=case.label,
                    runtime71_era="earliest_years",
                    text=case.narrator_text,
                    anchors=case.anchors,
                    word_budget=110,
                )
                score = score_chapter(chapter, case.lori_bad)
                rows = score.get("rows", {})
                missing = [r for r in case.expected_failed_rows if r not in rows]
                self.assertFalse(missing, f"Missing rows for {case.label}: {missing}. Rows: {rows}")
                self.assertTrue(
                    any(rows[r] == "FAIL" for r in case.expected_failed_rows),
                    f"Expected at least one quality row to FAIL for {case.label}. Rows: {rows}",
                )

    def test_every_known_good_rewrite_has_human_voice_and_one_question(self):
        for case in FAILURE_CASES:
            with self.subTest(case=case.label):
                chapter = ChapterConfig(
                    label=case.label,
                    runtime71_era="earliest_years",
                    text=case.narrator_text,
                    anchors=case.anchors,
                    word_budget=110,
                )
                score = score_chapter(chapter, case.lori_good)
                self.assertLessEqual(score["question_count"], 1)
                self.assertEqual(score["rows"].get("direct_human_voice"), "PASS")


if __name__ == "__main__":
    unittest.main()
