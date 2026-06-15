"""WO-LORI-STORY-FIRST-PHASE-1-01 (2026-06-14) — question hierarchy tests.

Covers acceptance gate #4: 4-layer classifier accuracy, eligibility
model honors session state + momentum, no Layer 3 or 4 without prior
Layer 1/2 success, story mode suppresses Layer 3+4.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api.services.question_hierarchy import (  # noqa: E402
    QUESTION_LAYER_NARRATIVE,
    QUESTION_LAYER_OPEN_RECALL,
    QUESTION_LAYER_TIMELINE,
    QUESTION_LAYER_VERIFICATION,
    SessionHierarchyState,
    classify_question_layer,
    eligible_layers,
    enforce_question_hierarchy,
    extract_questions,
    reset_classification_cache,
)


class ClassifierLayer1Test(unittest.TestCase):
    def setUp(self):
        reset_classification_cache()

    def test_tell_me_about_is_open_recall(self):
        self.assertEqual(
            classify_question_layer("Tell me about your childhood."),
            QUESTION_LAYER_OPEN_RECALL,
        )

    def test_what_do_you_remember_is_open_recall(self):
        self.assertEqual(
            classify_question_layer("What do you remember from that time?"),
            QUESTION_LAYER_OPEN_RECALL,
        )

    def test_what_stands_out_is_open_recall(self):
        self.assertEqual(
            classify_question_layer("What stands out from those years?"),
            QUESTION_LAYER_OPEN_RECALL,
        )

    def test_what_were_those_like_is_open_recall(self):
        self.assertEqual(
            classify_question_layer("What were those days like?"),
            QUESTION_LAYER_OPEN_RECALL,
        )


class ClassifierLayer2Test(unittest.TestCase):
    def setUp(self):
        reset_classification_cache()

    def test_who_was_there_is_narrative(self):
        self.assertEqual(
            classify_question_layer("Who else was there with you?"),
            QUESTION_LAYER_NARRATIVE,
        )

    def test_what_was_the_place_like_is_narrative(self):
        self.assertEqual(
            classify_question_layer("What was the place like?"),
            QUESTION_LAYER_NARRATIVE,
        )

    def test_what_happened_next_is_narrative(self):
        self.assertEqual(
            classify_question_layer("What happened next?"),
            QUESTION_LAYER_NARRATIVE,
        )

    def test_where_were_you_is_narrative(self):
        self.assertEqual(
            classify_question_layer("Where were you when that happened?"),
            QUESTION_LAYER_NARRATIVE,
        )


class ClassifierLayer3Test(unittest.TestCase):
    def setUp(self):
        reset_classification_cache()

    def test_how_old_were_you_is_timeline(self):
        self.assertEqual(
            classify_question_layer("How old were you?"),
            QUESTION_LAYER_TIMELINE,
        )

    def test_what_year_was_that_is_timeline(self):
        # Critical fix from this WO — must NOT classify as Layer 4
        self.assertEqual(
            classify_question_layer("What year was that?"),
            QUESTION_LAYER_TIMELINE,
        )

    def test_before_or_after_is_timeline(self):
        self.assertEqual(
            classify_question_layer("Was this before or after the war?"),
            QUESTION_LAYER_TIMELINE,
        )

    def test_what_decade_is_timeline(self):
        self.assertEqual(
            classify_question_layer("What decade was that?"),
            QUESTION_LAYER_TIMELINE,
        )


class ClassifierLayer4Test(unittest.TestCase):
    def setUp(self):
        reset_classification_cache()

    def test_was_that_spokane_is_verification(self):
        self.assertEqual(
            classify_question_layer("Was that Spokane, Washington?"),
            QUESTION_LAYER_VERIFICATION,
        )

    def test_did_you_mean_is_verification(self):
        self.assertEqual(
            classify_question_layer("Did you mean your sister?"),
            QUESTION_LAYER_VERIFICATION,
        )

    def test_just_to_be_sure_is_verification(self):
        self.assertEqual(
            classify_question_layer("Just to be sure, was that 1962?"),
            QUESTION_LAYER_VERIFICATION,
        )


class ClassifierFallbackTest(unittest.TestCase):
    def setUp(self):
        reset_classification_cache()

    def test_unknown_pattern_defaults_to_layer_1(self):
        # No pattern matches; default is open-recall (safe default —
        # always eligible).
        self.assertEqual(
            classify_question_layer("Banana split, no?"),
            QUESTION_LAYER_OPEN_RECALL,
        )

    def test_empty_string_returns_layer_1(self):
        self.assertEqual(
            classify_question_layer(""), QUESTION_LAYER_OPEN_RECALL,
        )

    def test_classification_is_cached(self):
        # First call goes through patterns; second pulls from cache.
        # We don't assert the cache directly (it's internal), but the
        # result must be stable.
        q = "What stands out?"
        a = classify_question_layer(q)
        b = classify_question_layer(q)
        self.assertEqual(a, b)


# ─────────────────────────────────────────────────────────────────────
# Eligibility
# ─────────────────────────────────────────────────────────────────────


class EligibilityTest(unittest.TestCase):
    def test_layer_1_always_eligible(self):
        state = SessionHierarchyState()
        self.assertIn(QUESTION_LAYER_OPEN_RECALL, eligible_layers(state, "normal"))
        self.assertIn(QUESTION_LAYER_OPEN_RECALL, eligible_layers(state, "story"))

    def test_layer_2_needs_substantive_narrative(self):
        no = SessionHierarchyState(has_substantive_narrative_turn=False)
        yes = SessionHierarchyState(has_substantive_narrative_turn=True)
        self.assertNotIn(QUESTION_LAYER_NARRATIVE, eligible_layers(no, "normal"))
        self.assertIn(QUESTION_LAYER_NARRATIVE, eligible_layers(yes, "normal"))

    def test_layer_3_suppressed_in_story_mode(self):
        s = SessionHierarchyState(
            has_substantive_narrative_turn=True,
            has_layer_2_succeeded=True,
        )
        story_elig = eligible_layers(s, "story")
        normal_elig = eligible_layers(s, "normal")
        self.assertNotIn(QUESTION_LAYER_TIMELINE, story_elig)
        self.assertIn(QUESTION_LAYER_TIMELINE, normal_elig)

    def test_layer_3_requires_layer_2_succeeded(self):
        # Layer 2 eligible but never succeeded → Layer 3 NOT eligible
        s = SessionHierarchyState(
            has_substantive_narrative_turn=True,
            has_layer_2_succeeded=False,
        )
        self.assertNotIn(QUESTION_LAYER_TIMELINE, eligible_layers(s, "normal"))

    def test_layer_4_requires_specific_ambiguity(self):
        no_amb = SessionHierarchyState(
            has_substantive_narrative_turn=True,
            has_layer_2_succeeded=True,
            has_specific_ambiguity=False,
        )
        amb = SessionHierarchyState(
            has_substantive_narrative_turn=True,
            has_layer_2_succeeded=True,
            has_specific_ambiguity=True,
        )
        self.assertNotIn(QUESTION_LAYER_VERIFICATION, eligible_layers(no_amb, "normal"))
        self.assertIn(QUESTION_LAYER_VERIFICATION, eligible_layers(amb, "normal"))

    def test_default_state_only_allows_layer_1(self):
        # First turn of a session: no prior narrative, no successes
        elig = eligible_layers(None, "normal")
        self.assertEqual(elig, {QUESTION_LAYER_OPEN_RECALL})


# ─────────────────────────────────────────────────────────────────────
# Enforcement
# ─────────────────────────────────────────────────────────────────────


class EnforcementTest(unittest.TestCase):
    def setUp(self):
        reset_classification_cache()

    def test_layer_1_only_response_passes_with_default_state(self):
        r = enforce_question_hierarchy(
            "Tell me about your childhood. What stands out?",
            session_state=None,
            momentum_mode="normal",
        )
        self.assertTrue(r.passed)

    def test_layer_3_question_fails_default_state(self):
        # No prior Layer 1/2 success → Layer 3 not eligible
        r = enforce_question_hierarchy(
            "How old were you when that happened?",
            session_state=None,
            momentum_mode="normal",
        )
        self.assertFalse(r.passed)
        self.assertIn(QUESTION_LAYER_TIMELINE, r.violating_layers)
        self.assertIn("layer_3_not_eligible", r.failure_reason)

    def test_layer_3_passes_when_state_qualifies(self):
        state = SessionHierarchyState(
            has_substantive_narrative_turn=True,
            has_layer_2_succeeded=True,
        )
        r = enforce_question_hierarchy(
            "How old were you when that happened?",
            session_state=state, momentum_mode="normal",
        )
        self.assertTrue(r.passed)

    def test_layer_3_suppressed_in_story_mode_even_with_state(self):
        state = SessionHierarchyState(
            has_substantive_narrative_turn=True,
            has_layer_2_succeeded=True,
        )
        r = enforce_question_hierarchy(
            "About how old were you?",
            session_state=state, momentum_mode="story",
        )
        self.assertFalse(r.passed)
        self.assertIn(QUESTION_LAYER_TIMELINE, r.violating_layers)

    def test_response_with_no_question_passes_vacuously(self):
        r = enforce_question_hierarchy(
            "Spokane stays with me. The bread always smelled warm.",
            session_state=None, momentum_mode="normal",
        )
        self.assertTrue(r.passed)
        self.assertEqual(r.classified_layers, ())

    def test_multi_question_response_classified_individually(self):
        r = enforce_question_hierarchy(
            "What stands out? How old were you?",
            session_state=None, momentum_mode="normal",
        )
        # Layer 1 (eligible) + Layer 3 (not eligible) = fail
        self.assertFalse(r.passed)
        self.assertEqual(len(r.classified_layers), 2)
        self.assertIn(QUESTION_LAYER_TIMELINE, r.violating_layers)


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────


class ExtractQuestionsTest(unittest.TestCase):
    def test_single_question(self):
        self.assertEqual(
            extract_questions("What stands out?"),
            ["What stands out?"],
        )

    def test_statement_then_question(self):
        out = extract_questions(
            "Spokane stays with me. What stands out about that summer?"
        )
        self.assertEqual(out, ["What stands out about that summer?"])

    def test_two_questions(self):
        out = extract_questions(
            "What stands out? How old were you?"
        )
        self.assertEqual(len(out), 2)
        self.assertIn("?", out[0])
        self.assertIn("?", out[1])

    def test_no_questions(self):
        self.assertEqual(extract_questions("Spokane stays with me."), [])
        self.assertEqual(extract_questions(""), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
