"""Unit tests for services/story_trigger.py.

Pure-function tests, no DB or filesystem. The trigger logic is the
gate between every chat_ws turn and the story preservation lane —
correctness here determines whether real stories get preserved or
quietly dropped.

Critical scenarios (from WO §3.3 and §12):
  - Janice canonical: ~25s/50w but 3+ anchors → borderline trigger
  - Long answer with anchor → full_threshold trigger
  - Short answer with no anchors → no trigger (correct null)
  - Empty / None / whitespace transcript → no trigger
  - Anchor false-positive resistance (bare keywords don't fire)
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

# Make `api.services.story_trigger` importable.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api.services import story_trigger  # noqa: E402


class CountSceneAnchorsTest(unittest.TestCase):
    """Each axis (place / time / person) contributes at most 1 to the
    anchor count. Total range is 0–3 per turn."""

    def test_empty_string(self):
        self.assertEqual(story_trigger.count_scene_anchors(""), 0)

    def test_none_safe(self):
        self.assertEqual(story_trigger.count_scene_anchors(None), 0)  # type: ignore[arg-type]

    def test_no_anchors(self):
        # Bare statement — no place, no relative time, no relation.
        self.assertEqual(
            story_trigger.count_scene_anchors("Yes that is correct."),
            0,
        )

    def test_place_only(self):
        # Multi-word capitalized run hits the proper-noun pattern
        self.assertEqual(
            story_trigger.count_scene_anchors("We lived in Grand Forks."),
            1,
        )

    def test_place_noun_only(self):
        self.assertEqual(
            story_trigger.count_scene_anchors("My uncle worked at the factory."),
            2,  # factory (place) + my uncle (person)
        )

    def test_time_only(self):
        self.assertEqual(
            story_trigger.count_scene_anchors("That happened back then."),
            1,
        )

    def test_person_only(self):
        self.assertEqual(
            story_trigger.count_scene_anchors("My dad helped a lot."),
            1,
        )

    def test_three_axes_canonical_janice(self):
        # The canonical reference — Janice's mastoidectomy story.
        # Place: Spokane (capitalized after "in")
        # Time: when I was
        # Person: my dad
        text = (
            "I had a mastoidectomy when I was little, in Spokane. "
            "My dad worked nights at the aluminum plant."
        )
        self.assertEqual(story_trigger.count_scene_anchors(text), 3)

    def test_axis_caps_at_one_per_dimension(self):
        # Five place mentions still only contribute 1 to the place
        # axis — anchor count is dimensional richness, not raw frequency.
        text = "Spokane Spokane Spokane in Spokane near Spokane"
        self.assertEqual(story_trigger.count_scene_anchors(text), 1)


class FalsePositiveResistanceTest(unittest.TestCase):
    """The keyword list ChatGPT originally proposed (`remember`,
    `home`, `school`, `when i was`, etc. as bare keywords) would
    overfire. Tighter detection keeps short conversational answers
    out of story-trigger territory."""

    def test_bare_remember_no_fire(self):
        # "I don't remember" should NOT fire the time anchor on its
        # own. Only specific time phrases qualify.
        self.assertEqual(story_trigger.count_scene_anchors("I don't remember."), 0)

    def test_bare_dad_no_fire_without_my(self):
        # "Dad was tall" should not fire — only "my dad" is the
        # anchor pattern.
        self.assertEqual(story_trigger.count_scene_anchors("Dad was tall."), 0)

    def test_yes_no_answer(self):
        for short_answer in ("yes", "no", "I think so", "maybe", "no idea"):
            self.assertEqual(
                story_trigger.count_scene_anchors(short_answer),
                0,
                f"unexpected anchor on bare answer: {short_answer!r}",
            )


class HasSceneAnchorTest(unittest.TestCase):
    def test_predicate_matches_count(self):
        self.assertTrue(story_trigger.has_scene_anchor("My dad worked nights."))
        self.assertFalse(story_trigger.has_scene_anchor("Yes."))


class ClassifyStoryCandidateTest(unittest.TestCase):
    """Two trigger paths plus the null case. WO §3.3 nailed-down."""

    def test_janice_borderline(self):
        # Canonical scenario from WO §12: ~25s/50w but 3+ anchors
        # → must fire as borderline_scene_anchor.
        text = (
            "I had a mastoidectomy when I was little, in Spokane. "
            "My dad worked nights at the aluminum plant because it "
            "paid more, and the nurses would let him bring me a "
            "hamburger."
        )
        # Word count is roughly 30; below the 60 floor for full_threshold
        result = story_trigger.classify_story_candidate(
            audio_duration_sec=25.0,
            transcript=text,
        )
        self.assertEqual(result, "borderline_scene_anchor")

    def test_full_threshold_long_with_anchors(self):
        # 70+ words, 60+ seconds, 1+ anchor → full_threshold.
        text = (
            "When I was a child growing up in Stanley, North Dakota, "
            "we had a small house on the edge of town. My dad was a "
            "farmer and my mom raised four of us. Every summer we'd "
            "drive into Minot to see my grandmother. The trip felt "
            "longer than it was. I remember the dust on the dashboard "
            "and the songs on the radio and the way the wheat looked."
        )
        self.assertGreaterEqual(len(text.split()), 60, "test setup needs ≥60 words")
        result = story_trigger.classify_story_candidate(
            audio_duration_sec=60.0,
            transcript=text,
        )
        self.assertEqual(result, "full_threshold")

    def test_long_no_anchors_no_trigger(self):
        # 70+ words but zero scene anchors — should NOT fire either
        # path. The presence of anchor signal is what distinguishes a
        # story from rambling.
        text = " ".join(["yes that is correct"] * 20)
        self.assertGreaterEqual(len(text.split()), 60)
        result = story_trigger.classify_story_candidate(
            audio_duration_sec=60.0,
            transcript=text,
        )
        self.assertIsNone(result)

    def test_short_no_anchors_no_trigger(self):
        result = story_trigger.classify_story_candidate(
            audio_duration_sec=2.0,
            transcript="Yes.",
        )
        self.assertIsNone(result)

    def test_short_with_one_anchor_no_trigger(self):
        # Only 1 anchor — below the 3-anchor borderline floor AND
        # below the duration/word floor. Correctly null.
        result = story_trigger.classify_story_candidate(
            audio_duration_sec=3.0,
            transcript="My dad was nice.",
        )
        self.assertIsNone(result)

    def test_short_with_two_anchors_no_trigger(self):
        # 2 anchors — still below the 3-anchor borderline floor.
        result = story_trigger.classify_story_candidate(
            audio_duration_sec=3.0,
            transcript="My dad worked at the factory.",
        )
        self.assertIsNone(result)

    def test_empty_transcript(self):
        result = story_trigger.classify_story_candidate(
            audio_duration_sec=30.0,
            transcript="",
        )
        self.assertIsNone(result)

    def test_whitespace_transcript(self):
        result = story_trigger.classify_story_candidate(
            audio_duration_sec=30.0,
            transcript="   \n  ",
        )
        self.assertIsNone(result)

    def test_none_duration_treated_as_zero(self):
        # Duration unknown → can't satisfy full_threshold's duration
        # check, but if anchor count is high enough for borderline
        # we still fire.
        result = story_trigger.classify_story_candidate(
            audio_duration_sec=None,
            transcript=(
                "I had a mastoidectomy when I was little, in Spokane. "
                "My dad worked nights."
            ),
        )
        self.assertEqual(result, "borderline_scene_anchor")


class EnvTunableThresholdsTest(unittest.TestCase):
    """Operator can re-tune thresholds without a code change.
    Tests verify env var changes flow through."""

    def setUp(self):
        # Snapshot the env so we can restore.
        self._snap = {
            k: os.environ.get(k)
            for k in (
                "STORY_TRIGGER_MIN_DURATION_SEC",
                "STORY_TRIGGER_MIN_WORDS",
                "STORY_TRIGGER_BORDERLINE_ANCHOR_COUNT",
            )
        }

    def tearDown(self):
        for k, v in self._snap.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_lowering_word_floor_admits_more_full_threshold(self):
        # 30 words at 30s with 1 anchor — below default 60-word floor.
        text = (
            "I grew up in Stanley with my dad and brothers. "
            "We had a farm and chickens and one old dog."
        )
        os.environ["STORY_TRIGGER_MIN_WORDS"] = "20"
        result = story_trigger.classify_story_candidate(
            audio_duration_sec=30.0, transcript=text,
        )
        self.assertEqual(result, "full_threshold")

    def test_raising_anchor_floor_blocks_borderline(self):
        # Janice canonical text — fires borderline by default. Raise
        # the threshold to 5 (impossible — only 3 axes exist) and
        # the trigger should disappear.
        text = (
            "I had a mastoidectomy when I was little, in Spokane. "
            "My dad worked nights."
        )
        os.environ["STORY_TRIGGER_BORDERLINE_ANCHOR_COUNT"] = "5"
        result = story_trigger.classify_story_candidate(
            audio_duration_sec=10.0, transcript=text,
        )
        self.assertIsNone(result)


class TriggerDiagnosticTest(unittest.TestCase):
    """The diagnostic returns the underlying numbers so chat_ws can
    emit a [story-trigger] log line per turn for operator review."""

    def test_diagnostic_shape(self):
        d = story_trigger.trigger_diagnostic(
            audio_duration_sec=25.0,
            transcript="I had a surgery in Spokane when I was little. My dad came.",
        )
        for key in (
            "trigger", "duration_sec", "word_count", "anchor_count",
            "place_anchor", "time_anchor", "person_anchor", "thresholds",
        ):
            self.assertIn(key, d, f"missing diagnostic key: {key}")
        self.assertEqual(d["place_anchor"], True)
        self.assertEqual(d["time_anchor"], True)
        self.assertEqual(d["person_anchor"], True)
        self.assertEqual(d["anchor_count"], 3)

    def test_diagnostic_thresholds_from_env(self):
        d = story_trigger.trigger_diagnostic(
            audio_duration_sec=0,
            transcript="anything",
        )
        self.assertIn("min_duration_sec", d["thresholds"])
        self.assertIn("min_words", d["thresholds"])
        self.assertIn("borderline_anchor_count", d["thresholds"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
