"""
BUG-LORI-PHRASE-AS-NAME-CONFIRMATION-01
========================================

Tests for the tightened META_FEEDBACK / correction-spelling trigger in
`services.lori_witness_mode`.

Before the patch, the trigger fired correction_spelling ("Did I get that
name right?") on any 2+ token titlecase phrase. This produced these false
positives across the 2026-06-17 full-family harness run:

  - "Got it — Originally Schong With A C. Did I get that name right?"  (Jake)
  - "Got it — You Learned To Stand Up And Sit Down And Kneel..."
  - "Got it — It Was The Air. Did I get that name right?"  (Shatner)
  - "Got it — Because The Adults Stopped Moving."  (Frank)
  - "Got it — That I Still Picture Clearly..."  (John seven-era)
  - "Got it — It Out Loud In The Empty Kitchen..."  (Richard)
  - "Got it — In March."  (Walter)

All of these are descriptive sentence fragments, not real names. The fix
adds `_looks_like_descriptive_phrase()` which suppresses
correction_spelling firing on these patterns while preserving the real
name-confirmation behavior for actual proper nouns ("Eliseo Sandoval",
"Las Vegas", "Magee Hospital", "Stanley").
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "server"))
sys.path.insert(0, str(REPO_ROOT / "server" / "code"))

from server.code.api.services.lori_witness_mode import (
    _looks_like_descriptive_phrase,
)


class LooksLikeDescriptivePhraseTest(unittest.TestCase):
    """The new guard helper that suppresses correction_spelling fires."""

    # ── True positives — these MUST be flagged as descriptive ──────────

    def test_originally_schong_with_a_c_flagged(self):
        self.assertTrue(_looks_like_descriptive_phrase(
            "Originally Schong With A C"
        ))

    def test_it_was_the_air_flagged(self):
        self.assertTrue(_looks_like_descriptive_phrase("It Was The Air"))

    def test_because_the_adults_stopped_moving_flagged(self):
        self.assertTrue(_looks_like_descriptive_phrase(
            "Because The Adults Stopped Moving"
        ))

    def test_that_i_still_picture_clearly_flagged(self):
        self.assertTrue(_looks_like_descriptive_phrase(
            "That I Still Picture Clearly"
        ))

    def test_it_out_loud_in_the_empty_kitchen_flagged(self):
        self.assertTrue(_looks_like_descriptive_phrase(
            "It Out Loud In The Empty Kitchen"
        ))

    def test_began_with_period_flagged(self):
        # Sentence-shaped — ends with period
        self.assertTrue(_looks_like_descriptive_phrase("Began."))

    def test_in_march_flagged(self):
        # "In" is a preposition; "March" is a month name
        self.assertTrue(_looks_like_descriptive_phrase("In March"))

    def test_you_learned_to_stand_up_flagged_by_length(self):
        # 9+ tokens — way too long to be a name
        self.assertTrue(_looks_like_descriptive_phrase(
            "You Learned To Stand Up And Sit Down And Kneel At The Right Times"
        ))

    # ── True negatives — these MUST NOT be flagged ──────────────────────

    def test_eliseo_sandoval_passes(self):
        self.assertFalse(_looks_like_descriptive_phrase("Eliseo Sandoval"))

    def test_las_vegas_passes(self):
        self.assertFalse(_looks_like_descriptive_phrase("Las Vegas"))

    def test_magee_hospital_passes(self):
        self.assertFalse(_looks_like_descriptive_phrase("Magee Hospital"))

    def test_stanley_passes(self):
        # Single-token — passes (but won't trigger correction_spelling
        # anyway because that requires 2+ tokens)
        self.assertFalse(_looks_like_descriptive_phrase("Stanley"))

    def test_boston_latin_school_passes(self):
        self.assertFalse(_looks_like_descriptive_phrase("Boston Latin School"))

    def test_mount_olive_ame_passes(self):
        self.assertFalse(_looks_like_descriptive_phrase("Mount Olive AME"))

    def test_new_mexico_highlands_university_flagged_by_length(self):
        # 4 tokens — borderline. Title contains no descriptive token so
        # it should pass.
        self.assertFalse(_looks_like_descriptive_phrase(
            "New Mexico Highlands University"
        ))


if __name__ == "__main__":
    unittest.main()
