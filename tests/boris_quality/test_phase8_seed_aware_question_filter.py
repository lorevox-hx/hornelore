from __future__ import annotations

import unittest

from scripts.harness_lib import ChapterConfig, score_chapter
from tests.boris_quality._helpers import assert_row_fails, require_callable
from tests.boris_quality.fixtures.boris_quality_cases import (
    CANONICAL_JOHN_TODAY_NARRATOR,
    MABLE_EARLIEST_NARRATOR,
    SEEDED_FACT_PROFILE_JOHN,
    SEEDED_FACT_PROFILE_MABLE,
)


class SeedAwareQuestionFilterTests(unittest.TestCase):
    """Phase 8 — Asks-what-seeded direct and scorer tests."""

    def test_scorer_fails_seeded_dob_pob_question(self):
        chapter = ChapterConfig(
            label="Mable Earliest",
            runtime71_era="earliest_years",
            text=MABLE_EARLIEST_NARRATOR,
            anchors=["albany", "1942", "mount olive"],
            word_budget=110,
        )
        bad = (
            "Mount Olive AME is important. You were born in Albany, Georgia, in 1942?"
        )
        score = score_chapter(chapter, bad)
        assert_row_fails(self, score, "no_seeded_fact_intake_question")

    def test_direct_filter_blocks_mable_seeded_birth_question(self):
        classify = require_callable([
            ("server.code.api.services.seed_aware_question_filter", "classify_seeded_fact_question"),
            ("server.code.api.services.seed_aware_question_filter", "should_block_seeded_fact_question"),
        ])
        question = "You were born in Albany, Georgia, in 1942?"
        result = classify(question, SEEDED_FACT_PROFILE_MABLE)
        if isinstance(result, tuple):
            result = result[0]
        self.assertTrue(bool(result), f"Expected seeded DOB/POB question to be blocked: {question!r}")

    def test_direct_filter_allows_lived_experience_around_seeded_birth(self):
        classify = require_callable([
            ("server.code.api.services.seed_aware_question_filter", "classify_seeded_fact_question"),
            ("server.code.api.services.seed_aware_question_filter", "should_block_seeded_fact_question"),
        ])
        question = "What do you remember about Albany when you were little?"
        result = classify(question, SEEDED_FACT_PROFILE_MABLE)
        if isinstance(result, tuple):
            result = result[0]
        self.assertFalse(bool(result), f"Expected lived-experience question to be allowed: {question!r}")

    def test_direct_filter_blocks_john_seeded_residence_and_work_questions(self):
        classify = require_callable([
            ("server.code.api.services.seed_aware_question_filter", "classify_seeded_fact_question"),
            ("server.code.api.services.seed_aware_question_filter", "should_block_seeded_fact_question"),
        ])
        blocked = [
            "Do you live in Las Vegas, New Mexico?",
            "Do you work at Pecos Schools?",
            "Is your mother alive?",
            "Does your mother live in St. Paul?",
            "Did you become a school psychologist in 2010?",
        ]
        for question in blocked:
            with self.subTest(question=question):
                result = classify(question, SEEDED_FACT_PROFILE_JOHN)
                if isinstance(result, tuple):
                    result = result[0]
                self.assertTrue(bool(result), f"Expected seeded fact question to be blocked: {question}")

    def test_direct_rewriter_turns_seeded_fact_question_into_lived_experience_question(self):
        rewrite = require_callable([
            ("server.code.api.services.seed_aware_question_filter", "rewrite_seeded_fact_question"),
            ("server.code.api.services.seed_aware_question_filter", "rewrite_or_block_seeded_fact_question"),
        ])
        rewritten = rewrite("Do you work at Pecos Schools?", SEEDED_FACT_PROFILE_JOHN)
        if isinstance(rewritten, tuple):
            rewritten = rewritten[-1]
        rewritten = str(rewritten)
        self.assertNotIn("Do you work at Pecos Schools", rewritten)
        self.assertIn("Pecos", rewritten)
        self.assertRegex(rewritten.lower(), r"(what|how|meaning|remember|feel|like)")


if __name__ == "__main__":
    unittest.main()
