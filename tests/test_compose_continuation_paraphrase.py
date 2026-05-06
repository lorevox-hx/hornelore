"""WO-BUG-LORI-SWITCH-FRESH-GREETING-01 Phase 2 Slice 2a — unit tests
for prompt_composer.compose_continuation_paraphrase().

Slice 2a covers Tier C (era-aware welcome-back) and Tier D (bare
welcome-back fallback). Slice 2b (after WO-LORI-MEMORY-ECHO-ERA-
STORIES-01 Phase 1c) will add Tier A (full paraphrase + unfinished
thread) and Tier B (paraphrase without thread) — those tests will
land alongside Slice 2b implementation.

Pure-deterministic: composer makes no LLM call, no DB write, only
reads via _build_profile_seed (stubbed in tests) and lv_eras lookup.

Run:
    python -m unittest tests.test_compose_continuation_paraphrase
    pytest tests/test_compose_continuation_paraphrase.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Make server/code importable so `import api.prompt_composer` works
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api import prompt_composer  # noqa: E402
from api.prompt_composer import compose_continuation_paraphrase  # noqa: E402


def _fake_seed_factory(seed_map):
    """Return a stub for _build_profile_seed that looks up person_id
    in the given dict; returns None for unknown ids."""
    def _stub(person_id):
        return seed_map.get(person_id)
    return _stub


class TierSelectionSliceTwoATests(unittest.TestCase):
    """Tier C and Tier D selection per Slice 2a."""

    def setUp(self):
        self._original_seed = prompt_composer._build_profile_seed
        prompt_composer._build_profile_seed = _fake_seed_factory({
            "mary":   {"preferred_name": "Mary", "full_name": "Mary Holts"},
            "marvin": {"preferred_name": "", "full_name": "Marvin Mann"},
            "noname": {},
        })

    def tearDown(self):
        prompt_composer._build_profile_seed = self._original_seed

    def test_tier_c_building_years(self):
        result = compose_continuation_paraphrase(
            person_id="mary", last_era_id="building_years"
        )
        self.assertEqual(
            result,
            "Welcome back, Mary. Last time we were in your building years. "
            "Would you like to continue there, or start somewhere else?",
        )

    def test_tier_c_earliest_years(self):
        result = compose_continuation_paraphrase(
            person_id="marvin", last_era_id="earliest_years"
        )
        self.assertEqual(
            result,
            "Welcome back, Marvin. Last time we were in the years before you "
            "started school. Would you like to continue there, or start "
            "somewhere else?",
        )

    def test_tier_c_today_special_case(self):
        # 'in today' reads awkward; composer renders 'talking about today'
        result = compose_continuation_paraphrase(
            person_id="mary", last_era_id="today"
        )
        self.assertIn("talking about today", result)
        self.assertNotIn("in today", result)

    def test_tier_c_legacy_era_key_canonicalizes(self):
        # midlife (legacy key) → building_years (canonical)
        result = compose_continuation_paraphrase(
            person_id="mary", last_era_id="midlife"
        )
        self.assertIn("your building years", result)

    def test_tier_d_no_era(self):
        result = compose_continuation_paraphrase(
            person_id="mary", last_era_id=None
        )
        self.assertEqual(
            result,
            "Welcome back, Mary. Where would you like to continue today?",
        )

    def test_tier_d_unknown_era_falls_through(self):
        result = compose_continuation_paraphrase(
            person_id="mary", last_era_id="unknown_era"
        )
        self.assertEqual(
            result,
            "Welcome back, Mary. Where would you like to continue today?",
        )


class NameResolutionTests(unittest.TestCase):
    """Name fallback cascade: name_hint > preferred_name > full_name first
    token > 'friend'."""

    def setUp(self):
        self._original_seed = prompt_composer._build_profile_seed
        prompt_composer._build_profile_seed = _fake_seed_factory({
            "mary":   {"preferred_name": "Mary", "full_name": "Mary Holts"},
            "marvin": {"preferred_name": "", "full_name": "Marvin Mann"},
            "noname": {},
        })

    def tearDown(self):
        prompt_composer._build_profile_seed = self._original_seed

    def test_name_hint_takes_precedence(self):
        result = compose_continuation_paraphrase(
            person_id="mary",
            last_era_id="building_years",
            name_hint="Janice",
        )
        self.assertIn("Welcome back, Janice.", result)
        self.assertNotIn("Mary", result)

    def test_preferred_name_used_when_no_hint(self):
        result = compose_continuation_paraphrase(
            person_id="mary", last_era_id="building_years"
        )
        self.assertIn("Welcome back, Mary.", result)

    def test_full_name_first_token_used_when_no_preferred(self):
        # marvin has no preferred_name; full_name is "Marvin Mann"
        result = compose_continuation_paraphrase(
            person_id="marvin", last_era_id="building_years"
        )
        self.assertIn("Welcome back, Marvin.", result)
        self.assertNotIn("Mann", result)

    def test_friend_fallback_when_no_name(self):
        result = compose_continuation_paraphrase(
            person_id="noname", last_era_id="building_years"
        )
        self.assertIn("Welcome back, friend.", result)

    def test_friend_fallback_when_empty_person_id(self):
        result = compose_continuation_paraphrase(
            person_id="", last_era_id="building_years"
        )
        self.assertIn("Welcome back, friend.", result)

    def test_friend_fallback_when_unknown_person_id(self):
        result = compose_continuation_paraphrase(
            person_id="ghost", last_era_id="building_years"
        )
        self.assertIn("Welcome back, friend.", result)


class DeterminismTests(unittest.TestCase):
    """Same inputs produce byte-identical output across calls."""

    def setUp(self):
        self._original_seed = prompt_composer._build_profile_seed
        prompt_composer._build_profile_seed = _fake_seed_factory({
            "mary": {"preferred_name": "Mary", "full_name": "Mary Holts"},
        })

    def tearDown(self):
        prompt_composer._build_profile_seed = self._original_seed

    def test_three_consecutive_calls_byte_identical(self):
        kwargs = dict(person_id="mary", last_era_id="building_years")
        a = compose_continuation_paraphrase(**kwargs)
        b = compose_continuation_paraphrase(**kwargs)
        c = compose_continuation_paraphrase(**kwargs)
        self.assertEqual(a, b)
        self.assertEqual(b, c)

    def test_tier_d_byte_stable_with_legacy_template(self):
        # Slice 2a Tier D fallback must match the legacy
        # interview.py:486-489 bare welcome-back template byte-for-byte
        # so default-off behavior is unchanged.
        result = compose_continuation_paraphrase(
            person_id="mary", last_era_id=None
        )
        legacy = "Welcome back, Mary. Where would you like to continue today?"
        self.assertEqual(result, legacy)


class GracefulDegradationTests(unittest.TestCase):
    """Composer never raises; degrades to Tier D on any internal failure."""

    def test_profile_seed_failure_degrades_to_tier_d_with_friend_name(self):
        original_seed = prompt_composer._build_profile_seed

        def _exploding_seed(_person_id):
            raise RuntimeError("simulated profile_seed failure")

        prompt_composer._build_profile_seed = _exploding_seed
        try:
            result = compose_continuation_paraphrase(
                person_id="mary", last_era_id="building_years"
            )
            # Era phrase still works; name falls back to "friend" because
            # the seed lookup raised.
            self.assertEqual(
                result,
                "Welcome back, friend. Last time we were in your building "
                "years. Would you like to continue there, or start "
                "somewhere else?",
            )
        finally:
            prompt_composer._build_profile_seed = original_seed

    def test_lv_eras_returning_none_falls_to_tier_d(self):
        original_seed = prompt_composer._build_profile_seed
        prompt_composer._build_profile_seed = _fake_seed_factory({
            "mary": {"preferred_name": "Mary"},
        })
        try:
            result = compose_continuation_paraphrase(
                person_id="mary", last_era_id="completely_made_up_era"
            )
            self.assertEqual(
                result,
                "Welcome back, Mary. Where would you like to continue today?",
            )
        finally:
            prompt_composer._build_profile_seed = original_seed


class VerbatimAnchorTests(unittest.TestCase):
    """Story anchors in Tier B / Tier A (Slice 2b) must come from
    narrator text only — no LLM, no invention. For Slice 2a, the only
    anchor-like element is `warm_era_phrase` which is a fixed lookup
    in lv_eras._LV_ERA_CONTINUATION_PHRASES — never invented."""

    def setUp(self):
        self._original_seed = prompt_composer._build_profile_seed
        prompt_composer._build_profile_seed = _fake_seed_factory({
            "mary": {"preferred_name": "Mary"},
        })

    def tearDown(self):
        prompt_composer._build_profile_seed = self._original_seed

    def test_tier_c_uses_only_lv_eras_lookup_phrase(self):
        # Confirm the rendered phrase IS one of the locked lv_eras values.
        from api.lv_eras import _LV_ERA_CONTINUATION_PHRASES
        result = compose_continuation_paraphrase(
            person_id="mary", last_era_id="adolescence"
        )
        # Phrase for adolescence is "your adolescence"
        self.assertIn(_LV_ERA_CONTINUATION_PHRASES["adolescence"], result)


if __name__ == "__main__":
    unittest.main()
