from __future__ import annotations

import unittest

from tests.boris_quality.fixtures.boris_quality_cases import (
    JOHN_ADOLESCENCE_ACCIDENT_FIRST_PERSON,
    JOHN_ADOLESCENCE_ACCIDENT_THIRD_PERSON,
    STEFI_INNOCENT_FAMILY_TEXT,
    TRUE_CHILD_ABUSE_DISCLOSURE,
)


class SafetyFalsePositiveLifeStoryTests(unittest.TestCase):
    """Phase 1 — safety false-positive regression tests.

    These are direct tests against server.code.api.safety.scan_answer().
    They are intentionally wordy because the bug appears in realistic
    oral-history sentences, not in tiny toy strings.
    """

    def setUp(self):
        from server.code.api.safety import scan_answer
        self.scan_answer = scan_answer

    def assert_no_safety_trigger(self, text: str) -> None:
        result = self.scan_answer(text)
        self.assertTrue(
            result is None or not result.triggered,
            f"Expected no safety trigger for ordinary biography. Got: {result!r}\nText:\n{text}",
        )

    def assert_child_abuse_trigger(self, text: str) -> None:
        result = self.scan_answer(text)
        self.assertIsNotNone(result, "Expected a safety result for true abuse disclosure.")
        self.assertTrue(result.triggered, f"Expected triggered=True. Got: {result!r}")
        self.assertEqual(result.category, "child_abuse", f"Expected child_abuse. Got: {result!r}")

    def test_john_father_car_death_first_person_is_not_child_abuse(self):
        self.assert_no_safety_trigger(JOHN_ADOLESCENCE_ACCIDENT_FIRST_PERSON)

    def test_john_father_car_death_third_person_is_not_child_abuse(self):
        self.assert_no_safety_trigger(JOHN_ADOLESCENCE_ACCIDENT_THIRD_PERSON)

    def test_stefi_sheep_rancher_family_background_is_not_child_abuse(self):
        self.assert_no_safety_trigger(STEFI_INNOCENT_FAMILY_TEXT)

    def test_true_child_abuse_disclosure_still_triggers(self):
        self.assert_child_abuse_trigger(TRUE_CHILD_ABUSE_DISCLOSURE)

    def test_father_hit_by_car_is_accident_not_perpetrator_hit(self):
        text = (
            "My father was hit by a car outside town. I was sixteen when it happened. "
            "He was changing a tire, and the driver did not see him. That accident changed "
            "the shape of our family, but it was not abuse and it was not anyone in the "
            "family hurting a child."
        )
        self.assert_no_safety_trigger(text)


if __name__ == "__main__":
    unittest.main()
