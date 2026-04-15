"""WO-LIFE-SPINE-05 unit tests.

Pure-Python tests for phase_aware_composer. Uses the real question_bank.json
(no fixtures). Run with:

    python -m unittest tests.test_phase_aware_composer
"""
import os
import sys
import unittest
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "server", "code"))

from api.phase_aware_composer import (  # noqa: E402
    ask_key,
    current_age,
    list_phase_ids,
    phase_for_age,
    pick_next_question,
    reload_bank,
)


class BankLoadTests(unittest.TestCase):
    def test_bank_found_and_parsed(self):
        phases = list_phase_ids()
        self.assertEqual(len(phases), 5)
        self.assertIn("developmental_foundations", phases)
        self.assertIn("legacy_reflection", phases)


class AgeAndPhaseTests(unittest.TestCase):
    def test_current_age_basic(self):
        # Fixed today so test doesn't drift year-over-year
        self.assertEqual(current_age("1962-12-24", today=date(2026, 4, 14)), 63)
        self.assertEqual(current_age("1962-12-24", today=date(1963, 1, 1)), 0)

    def test_phase_for_age_chris_63(self):
        bank = reload_bank()
        self.assertEqual(phase_for_age(bank, 63), "legacy_reflection")

    def test_phase_for_age_child_8(self):
        bank = reload_bank()
        self.assertEqual(phase_for_age(bank, 8), "developmental_foundations")

    def test_phase_for_age_teen_15(self):
        bank = reload_bank()
        self.assertEqual(phase_for_age(bank, 15), "transitional_adolescence")


class PickNextQuestionTests(unittest.TestCase):
    def test_returns_none_without_dob(self):
        self.assertIsNone(pick_next_question(dob=None))

    def test_returns_phase_appropriate_for_teen(self):
        # Narrator age 15 → transitional_adolescence
        q = pick_next_question(dob="2011-01-01", today=date(2026, 4, 14))
        self.assertIsNotNone(q)
        self.assertEqual(q["section_id"], "transitional_adolescence")
        self.assertIn("prompt", q)
        self.assertIn("_meta", q)

    def test_skips_asked_questions(self):
        # First call gives us Q0 of the first sub-topic
        first = pick_next_question(dob="1962-12-24", today=date(2026, 4, 14))
        self.assertIsNotNone(first)
        asked = {first["_meta"]["ask_key"]}
        second = pick_next_question(
            dob="1962-12-24",
            asked_keys=asked,
            today=date(2026, 4, 14),
        )
        self.assertIsNotNone(second)
        self.assertNotEqual(second["_meta"]["ask_key"], first["_meta"]["ask_key"])

    def test_respects_phase_override(self):
        # Chris is 63 (legacy phase) but force developmental_foundations
        q = pick_next_question(
            dob="1962-12-24",
            phase_override="developmental_foundations",
            today=date(2026, 4, 14),
        )
        self.assertIsNotNone(q)
        self.assertEqual(q["section_id"], "developmental_foundations")

    def test_response_shape_mirrors_db_row(self):
        q = pick_next_question(dob="1962-12-24", today=date(2026, 4, 14))
        # Keys that _qout() depends on
        self.assertIn("id", q)
        self.assertIn("section_id", q)
        self.assertIn("ord", q)
        self.assertIn("prompt", q)
        self.assertTrue(q["id"].startswith("qb:"))

    def test_ask_key_format(self):
        self.assertEqual(ask_key("legacy_reflection", "reflection", 0),
                         "legacy_reflection:reflection:0")


class SpineAnchorReachabilityTests(unittest.TestCase):
    def test_anchor_gated_questions_skipped_when_too_young(self):
        # A 5-year-old shouldn't see autonomy_milestones (gated by drivers license).
        # But phase_for_age for age 5 is developmental_foundations, so that
        # sub-topic wouldn't appear in their phase anyway. Instead force
        # the adolescence phase with a too-young narrator and verify
        # drivers-license anchored questions are skipped.
        q = pick_next_question(
            dob="2020-01-01",          # age 6
            phase_override="transitional_adolescence",
            today=date(2026, 4, 14),
        )
        # Could be None (all anchors unreachable) or non-anchor sub-topic.
        # If we got a question, it must not be anchored to an envelope the
        # 6yo can't reach.
        if q is not None:
            anchor = q["_meta"].get("spine_anchor")
            # If anchor exists, min_age for drivers_license is 14 > 6 → should be filtered
            self.assertNotEqual(anchor, "civic_drivers_license_age")


if __name__ == "__main__":
    unittest.main()
