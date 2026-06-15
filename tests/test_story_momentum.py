"""WO-LORI-STORY-FIRST-PHASE-1-01 (2026-06-14) — story momentum tests.

Covers acceptance gate #2: composite score in [0.0, 1.0], mode
boundaries snap correctly, env-tunable thresholds honored, per-signal
extraction behaves sensibly on edge cases.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api.services.story_momentum import (  # noqa: E402
    MODE_EMERGING,
    MODE_NORMAL,
    MODE_STORY,
    mode_for_score,
    score_story_momentum,
)


# A representative "chapter" turn carrying named entities, temporal,
# sensory, sequence, and dialogue signals.
CHAPTER_TEXT = (
    "When I was nine, we lived in Spokane on Knox Avenue. "
    "First I would walk the dog past the aluminum plant, then I'd cut "
    "through the alley behind the bakery where the bread always smelled "
    "warm and sweet. The wind off the river was cold in the morning. "
    "I remember Mrs. Henderson would call out, \"Be careful crossing!\" "
    "She watched us the whole way down to the corner."
)


class MomentumCompositeBoundsTest(unittest.TestCase):
    def test_composite_clamped_to_unit_interval(self):
        score = score_story_momentum(CHAPTER_TEXT, uninterrupted_run=4)
        self.assertGreaterEqual(score.composite, 0.0)
        self.assertLessEqual(score.composite, 1.0)

    def test_empty_text_zero_composite(self):
        s = score_story_momentum("")
        self.assertEqual(s.composite, 0.0)
        self.assertEqual(s.word_count, 0)
        self.assertEqual(s.mode, MODE_NORMAL)

    def test_none_text_safe(self):
        s = score_story_momentum(None)
        self.assertEqual(s.composite, 0.0)
        self.assertEqual(s.mode, MODE_NORMAL)


class MomentumSignalCountsTest(unittest.TestCase):
    def test_chapter_text_named_entities(self):
        s = score_story_momentum(CHAPTER_TEXT)
        # Spokane / Knox Avenue / Mrs. Henderson — at least 2 entities
        self.assertGreaterEqual(s.named_entity_count, 2)

    def test_chapter_text_temporal_markers(self):
        s = score_story_momentum(CHAPTER_TEXT)
        # "when", "then", year-style not present but plenty of when/then/morning
        self.assertGreaterEqual(s.temporal_marker_count, 2)

    def test_chapter_text_sensory_tokens(self):
        s = score_story_momentum(CHAPTER_TEXT)
        # smelled, warm, sweet, cold, watched, walk
        self.assertGreaterEqual(s.sensory_token_count, 3)

    def test_chapter_text_sequence_markers(self):
        s = score_story_momentum(CHAPTER_TEXT)
        # "First", "then"
        self.assertGreaterEqual(s.sequence_marker_count, 2)

    def test_chapter_text_dialogue_present(self):
        s = score_story_momentum(CHAPTER_TEXT)
        # quoted speech + "watched" + "call out"
        self.assertTrue(s.dialogue_present)

    def test_year_pattern_counts_as_temporal(self):
        s = score_story_momentum("It was 1962, the summer my father came home.")
        self.assertGreaterEqual(s.temporal_marker_count, 1)

    def test_age_pattern_counts_as_temporal(self):
        s = score_story_momentum("When I was 9, we moved to a new house.")
        self.assertGreaterEqual(s.temporal_marker_count, 1)


class MomentumModeSelectionTest(unittest.TestCase):
    def test_chapter_text_with_uninterrupted_run_is_story(self):
        s = score_story_momentum(CHAPTER_TEXT, uninterrupted_run=4)
        self.assertEqual(s.mode, MODE_STORY)

    def test_short_yes_no_answer_is_normal(self):
        s = score_story_momentum("Yes, I think so.")
        self.assertEqual(s.mode, MODE_NORMAL)

    def test_mode_for_score_thresholds(self):
        self.assertEqual(mode_for_score(0.65), MODE_STORY)
        self.assertEqual(mode_for_score(0.45), MODE_EMERGING)
        self.assertEqual(mode_for_score(0.20), MODE_NORMAL)

    def test_mode_for_score_exact_boundaries(self):
        # >= STORY threshold (default 0.60) → story
        self.assertEqual(mode_for_score(0.60), MODE_STORY)
        # >= EMERGING threshold (default 0.40) → emerging
        self.assertEqual(mode_for_score(0.40), MODE_EMERGING)


class MomentumEnvTunableThresholdsTest(unittest.TestCase):
    """The two env vars are read at call time; setting them changes
    which mode_for_score returns for the same composite. Use os.environ
    + a try/finally to keep test isolation."""

    def _with_env(self, **vars):
        saved = {k: os.environ.get(k) for k in vars}
        for k, v in vars.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return saved

    def _restore_env(self, saved):
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_lowered_story_threshold_promotes_mode(self):
        saved = self._with_env(HORNELORE_MOMENTUM_STORY="0.30")
        try:
            # Composite 0.35 is "emerging" at default 0.60, but "story"
            # when the story threshold drops to 0.30.
            self.assertEqual(mode_for_score(0.35), MODE_STORY)
        finally:
            self._restore_env(saved)

    def test_raised_emerging_threshold_demotes_mode(self):
        saved = self._with_env(HORNELORE_MOMENTUM_EMERGING="0.50")
        try:
            # Composite 0.45 was "emerging" at default 0.40, becomes
            # "normal" when emerging climbs to 0.50.
            self.assertEqual(mode_for_score(0.45), MODE_NORMAL)
        finally:
            self._restore_env(saved)

    def test_invalid_env_value_falls_back_to_default(self):
        saved = self._with_env(HORNELORE_MOMENTUM_STORY="not_a_number")
        try:
            # Bad env value → default 0.60 still in effect
            self.assertEqual(mode_for_score(0.65), MODE_STORY)
            self.assertEqual(mode_for_score(0.55), MODE_EMERGING)
        finally:
            self._restore_env(saved)

    def test_threshold_clamped_to_unit_interval(self):
        # Bad >1.0 input should clamp; mode_for_score(1.0) still story
        saved = self._with_env(HORNELORE_MOMENTUM_STORY="5.0")
        try:
            self.assertEqual(mode_for_score(1.0), MODE_STORY)
        finally:
            self._restore_env(saved)


class MomentumUninterruptedRunTest(unittest.TestCase):
    def test_run_increases_composite(self):
        no_run = score_story_momentum(CHAPTER_TEXT, uninterrupted_run=0)
        with_run = score_story_momentum(CHAPTER_TEXT, uninterrupted_run=4)
        self.assertGreater(with_run.composite, no_run.composite)

    def test_negative_run_clamped_to_zero(self):
        a = score_story_momentum(CHAPTER_TEXT, uninterrupted_run=-5)
        b = score_story_momentum(CHAPTER_TEXT, uninterrupted_run=0)
        self.assertAlmostEqual(a.composite, b.composite, places=6)

    def test_run_above_cap_does_not_overflow(self):
        s = score_story_momentum(CHAPTER_TEXT, uninterrupted_run=999)
        self.assertLessEqual(s.composite, 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
