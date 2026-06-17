"""
BUG-HARNESS-SCORER-TOO-LENIENT-CONTENT-QUALITY-01
==================================================

Tests for the 8 new content-quality scoring rows added to
scripts/harness_lib.py::score_chapter.

Each new row has a hard-FAIL example (taken directly from the 2026-06-17
full-family harness run that called these PASS under the old scorer) and
a corresponding PASS example (a real grounded Lori response).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from harness_lib import (  # noqa: E402
    ChapterConfig,
    _detect_anchor_cascade,
    _detect_false_name_confirm,
    _detect_fragment,
    _detect_got_it_stub,
    _detect_meta_leak,
    _detect_seeded_fact_intake,
    _detect_titlecase_phrase_as_name,
    score_chapter,
)


# ── Fixture chapter ──────────────────────────────────────────────────────────


def make_chapter(anchors=None, label="Earliest Years", era="earliest_years"):
    return ChapterConfig(
        label=label,
        runtime71_era=era,
        text="(narrator chapter text)",
        anchors=anchors or ["albany", "1942", "georgia"],
    )


# ── Row 9: no_false_name_confirmation ────────────────────────────────────────


class NoFalseNameConfirmTest(unittest.TestCase):
    """Catches 'Did I get that name right?' fired on descriptive phrases."""

    def test_got_it_did_i_get_that_name_right_fails(self):
        text = "Got it — It Was The Air. Did I get that name right? What happened next?"
        self.assertTrue(_detect_false_name_confirm(text))

    def test_normal_lori_response_passes(self):
        text = "Albany. What do you remember about your school there?"
        self.assertFalse(_detect_false_name_confirm(text))


# ── Row 10: no_got_it_stub ───────────────────────────────────────────────────


class NoGotItStubTest(unittest.TestCase):
    def test_jake_originally_schong_fails(self):
        text = "Got it — Originally Schong With A C. Did I get that name right? What happened next?"
        self.assertTrue(_detect_got_it_stub(text))

    def test_shatner_it_was_the_air_fails(self):
        text = "Got it — It Was The Air. Did I get that name right? What happened next?"
        self.assertTrue(_detect_got_it_stub(text))

    def test_real_response_starting_with_got_it_passes(self):
        # A real reflective response that happens to use "Got it" naturally
        # but is NOT followed by the "Did I get that name right" / "What
        # happened next" stub pattern.
        text = "I hear you — Albany during cotton-land time was hard. What stays with you most?"
        self.assertFalse(_detect_got_it_stub(text))


# ── Row 11: no_titlecase_phrase_as_name ──────────────────────────────────────


class NoTitlecasePhraseAsNameTest(unittest.TestCase):
    def test_originally_schong_with_a_c_fails(self):
        text = "Got it — Originally Schong With A C. Did I get that name right?"
        offender = _detect_titlecase_phrase_as_name(text)
        self.assertEqual(offender, "Originally Schong With A C")

    def test_you_learned_to_stand_up_sequence_fails(self):
        text = "Got it — You Learned To Stand Up And Sit Down And Kneel At The Right Times. Did I get that name right?"
        offender = _detect_titlecase_phrase_as_name(text)
        self.assertIsNotNone(offender)

    def test_real_short_name_passes(self):
        text = "Got it — Eliseo. Did I get that name right?"
        # 1 word ≤ 3 word threshold → not flagged
        self.assertIsNone(_detect_titlecase_phrase_as_name(text))


# ── Row 12: response_not_fragmented ──────────────────────────────────────────


class ResponseNotFragmentedTest(unittest.TestCase):
    def test_west_st_fragment_fails(self):
        self.assertTrue(_detect_fragment("West St."))

    def test_st_fragment_fails(self):
        self.assertTrue(_detect_fragment("St."))

    def test_began_single_word_fails(self):
        self.assertTrue(_detect_fragment("Began."))

    def test_short_real_response_passes(self):
        # 9 words — clearly a real response
        self.assertFalse(_detect_fragment(
            "What does West St. Paul mean to you now?"
        ))


# ── Row 14: no_meta_response_leak ────────────────────────────────────────────


class NoMetaResponseLeakTest(unittest.TestCase):
    def test_here_is_a_response_fails(self):
        text = (
            "Here is a response that follows the rules and guidelines:\n"
            "\"You mentioned Magee Hospital where you were born.\""
        )
        self.assertIsNotNone(_detect_meta_leak(text))

    def test_this_response_reflects_fails(self):
        text = "This response reflects the narrator's mentions of Magee Hospital and the Catholic Church."
        self.assertIsNotNone(_detect_meta_leak(text))

    def test_what_a_rich_evocative_narrative_fails(self):
        text = "What a rich and evocative narrative! Let me capture a few key points."
        self.assertIsNotNone(_detect_meta_leak(text))

    def test_normal_response_passes(self):
        text = "Magee Hospital and the Catholic Church grounded your earliest years. What stays?"
        self.assertIsNone(_detect_meta_leak(text))


# ── Row 15: no_titlecased_anchor_cascade ─────────────────────────────────────


class NoTitlecasedAnchorCascadeTest(unittest.TestCase):
    def test_walter_saint_augustine_cascade_fails(self):
        text = (
            "You went from Saint Augustine to Brendan, then Eileen, Patrick, "
            "Catholic, South Boston, Mass, and Walter. What happened next?"
        )
        self.assertTrue(_detect_anchor_cascade(text))

    def test_joe_cochiti_cascade_fails(self):
        text = (
            "You went from Cochiti Pueblo to August, then Frank, Elena, "
            "Andrew, Mary, Catholic, and Mass. What happened next?"
        )
        self.assertTrue(_detect_anchor_cascade(text))

    def test_you_said_x_you_kept_coming_back_to_x_fails(self):
        text = (
            "You said Boston Latin: I went to Boston Latin School. "
            "You kept coming back to Boston Latin — what was that actually like?"
        )
        self.assertTrue(_detect_anchor_cascade(text))

    def test_real_response_with_two_anchors_passes(self):
        text = "Princeton Avenue and Miss McCullough. What does that combination feel like now?"
        self.assertFalse(_detect_anchor_cascade(text))


# ── Row 16: no_seeded_fact_intake_question ───────────────────────────────────


class NoSeededFactIntakeQuestionTest(unittest.TestCase):
    def test_mable_were_you_born_in_albany_1942_fails(self):
        text = "You were born in Albany, Georgia, in 1942?"
        seeded = {"place_of_birth": "Albany, Georgia", "birth_year": "1942"}
        offender = _detect_seeded_fact_intake(text, seeded)
        self.assertIsNotNone(offender)

    def test_john_do_you_live_in_las_vegas_nm_fails(self):
        text = "Do you currently live in Las Vegas, New Mexico?"
        seeded = {"current_residence": "Las Vegas, New Mexico"}
        offender = _detect_seeded_fact_intake(text, seeded)
        self.assertIsNotNone(offender)

    def test_lived_experience_question_around_seeded_fact_passes(self):
        text = "What do you remember about Albany when you were little?"
        seeded = {"place_of_birth": "Albany, Georgia", "birth_year": "1942"}
        self.assertIsNone(_detect_seeded_fact_intake(text, seeded))

    def test_no_seeded_facts_returns_none(self):
        text = "You were born in Albany, Georgia, in 1942?"
        self.assertIsNone(_detect_seeded_fact_intake(text, None))


# ── End-to-end score_chapter integration ─────────────────────────────────────


class ScoreChapterIntegrationTest(unittest.TestCase):
    """Top-level scorer integration test for the 8 new rows."""

    def test_broken_jake_response_fails_multiple_new_rows(self):
        chapter = make_chapter(anchors=["stanley", "north dakota"])
        text = "Got it — Originally Schong With A C. Did I get that name right? What happened next?"
        score = score_chapter(chapter, text)
        rows = score["rows"]
        # Multiple new rows must FAIL on this broken response
        self.assertEqual(rows["no_false_name_confirmation"], "FAIL")
        self.assertEqual(rows["no_got_it_stub"], "FAIL")
        self.assertEqual(rows["no_titlecase_phrase_as_name"], "FAIL")
        self.assertEqual(rows["minimum_anchor_count"], "FAIL")

    def test_west_st_stub_fails_fragment_row(self):
        chapter = make_chapter(anchors=["west st. paul"])
        text = "West St."
        score = score_chapter(chapter, text)
        self.assertEqual(score["rows"]["response_not_fragmented"], "FAIL")

    def test_richard_meta_leak_fails_meta_row(self):
        chapter = make_chapter(anchors=["oakland", "magee hospital"])
        text = (
            "Here is a response that follows the rules and guidelines:\n"
            "\"You mentioned Magee Hospital where you were born.\""
        )
        score = score_chapter(chapter, text)
        self.assertEqual(score["rows"]["no_meta_response_leak"], "FAIL")

    def test_walter_cascade_fails_cascade_row(self):
        chapter = make_chapter(anchors=["saint augustine"])
        text = (
            "You went from Saint Augustine to Brendan, then Eileen, Patrick, "
            "Catholic, South Boston, Mass, and Walter. What happened next?"
        )
        score = score_chapter(chapter, text)
        self.assertEqual(score["rows"]["no_titlecased_anchor_cascade"], "FAIL")

    def test_mable_seeded_question_fails_seeded_row(self):
        chapter = make_chapter(anchors=["albany", "mount olive"])
        text = "You were born in Albany, Georgia, in 1942?"
        seeded = {"place_of_birth": "Albany, Georgia", "birth_year": "1942"}
        score = score_chapter(chapter, text, seeded_facts=seeded)
        self.assertEqual(score["rows"]["no_seeded_fact_intake_question"], "FAIL")

    def test_good_response_passes_all_new_rows(self):
        chapter = make_chapter(anchors=["albany", "mount olive ame", "1942"])
        text = (
            "Albany and Mount Olive AME — that combination stays with me. "
            "What was a typical Sunday morning like back then?"
        )
        seeded = {"place_of_birth": "Albany, Georgia", "birth_year": "1942"}
        score = score_chapter(chapter, text, seeded_facts=seeded)
        rows = score["rows"]
        for new_row in (
            "no_false_name_confirmation",
            "no_got_it_stub",
            "no_titlecase_phrase_as_name",
            "response_not_fragmented",
            "minimum_anchor_count",
            "no_meta_response_leak",
            "no_titlecased_anchor_cascade",
            "no_seeded_fact_intake_question",
        ):
            self.assertEqual(rows[new_row], "PASS", f"{new_row} should PASS on good response")


if __name__ == "__main__":
    unittest.main()
