"""Unit tests for services/age_arithmetic.py.

Pure-function tests, no DB or filesystem. The arithmetic is small and
high-leverage: every story_candidate row's era_candidates and
estimated_year_* fields trace through this module, so its correctness
is load-bearing for the operator review queue.
"""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

# Add server/code to sys.path so `api.services.age_arithmetic` imports.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api.services import age_arithmetic  # noqa: E402


class NormalizeBucketTest(unittest.TestCase):
    def test_lowercase_and_strip(self):
        self.assertEqual(age_arithmetic.normalize_bucket("  In_School  "), "in_school")

    def test_none(self):
        self.assertIsNone(age_arithmetic.normalize_bucket(None))

    def test_empty_string(self):
        self.assertIsNone(age_arithmetic.normalize_bucket(""))

    def test_whitespace_only(self):
        self.assertIsNone(age_arithmetic.normalize_bucket("   "))


class IsKnownBucketTest(unittest.TestCase):
    def test_known(self):
        for b in ("very_little", "in_school", "older", "young_adult"):
            self.assertTrue(age_arithmetic.is_known_bucket(b), f"expected known: {b}")

    def test_known_case_insensitive(self):
        self.assertTrue(age_arithmetic.is_known_bucket("IN_SCHOOL"))

    def test_unknown(self):
        self.assertFalse(age_arithmetic.is_known_bucket("middle_aged"))

    def test_none(self):
        self.assertFalse(age_arithmetic.is_known_bucket(None))


class BucketToEraCandidatesTest(unittest.TestCase):
    def test_single_era(self):
        self.assertEqual(
            age_arithmetic.bucket_to_era_candidates("very_little"),
            ["earliest_years"],
        )

    def test_multi_era_preserves_ambiguity(self):
        # "before_school" spans the boundary between earliest_years
        # and early_school_years — both candidates must be returned.
        result = age_arithmetic.bucket_to_era_candidates("before_school")
        self.assertEqual(result, ["earliest_years", "early_school_years"])

    def test_unknown_returns_empty(self):
        self.assertEqual(age_arithmetic.bucket_to_era_candidates("middle_aged"), [])

    def test_none_returns_empty(self):
        self.assertEqual(age_arithmetic.bucket_to_era_candidates(None), [])

    def test_returns_a_copy(self):
        # Caller shouldn't be able to mutate the module's internal table.
        result = age_arithmetic.bucket_to_era_candidates("very_little")
        result.append("evil_era")
        # Re-fetch and confirm internal state is unchanged
        result2 = age_arithmetic.bucket_to_era_candidates("very_little")
        self.assertEqual(result2, ["earliest_years"])


class EstimateYearFromAgeBucketTest(unittest.TestCase):
    def test_janice_in_school(self):
        # The canonical reference scenario: Janice DOB 1939-08-30,
        # bucket "in_school" → ages 5-11 → years 1944-1950.
        dob = date(1939, 8, 30)
        low, high = age_arithmetic.estimate_year_from_age_bucket(dob, "in_school")
        self.assertEqual((low, high), (1944, 1950))

    def test_janice_very_little(self):
        # "very_little" → ages 0-4 → years 1939-1943.
        dob = date(1939, 8, 30)
        low, high = age_arithmetic.estimate_year_from_age_bucket(dob, "very_little")
        self.assertEqual((low, high), (1939, 1943))

    def test_janice_before_school_multi_year(self):
        # "before_school" → ages 3-5 → years 1942-1944.
        dob = date(1939, 8, 30)
        low, high = age_arithmetic.estimate_year_from_age_bucket(dob, "before_school")
        self.assertEqual((low, high), (1942, 1944))

    def test_dob_none_returns_none_pair(self):
        low, high = age_arithmetic.estimate_year_from_age_bucket(None, "in_school")
        self.assertEqual((low, high), (None, None))

    def test_bucket_none_returns_none_pair(self):
        dob = date(1939, 8, 30)
        low, high = age_arithmetic.estimate_year_from_age_bucket(dob, None)
        self.assertEqual((low, high), (None, None))

    def test_unknown_bucket_returns_none_pair(self):
        # Important: an unknown bucket must NOT crash. Stale clients
        # could send unknown labels; we should fail gracefully.
        dob = date(1939, 8, 30)
        low, high = age_arithmetic.estimate_year_from_age_bucket(dob, "wandering_years")
        self.assertEqual((low, high), (None, None))

    def test_dob_not_a_date_returns_none_pair(self):
        # Defensive: caller passing a string accidentally must not crash.
        low, high = age_arithmetic.estimate_year_from_age_bucket(
            "1939-08-30",  # type: ignore[arg-type]
            "in_school",
        )
        self.assertEqual((low, high), (None, None))

    def test_jan_born_narrator(self):
        # Edge case: born January 1. We don't account for school-year
        # cutoff; arithmetic is birth_year + age, so a Jan-born narrator
        # gets the same range as an Aug-born one for the same bucket.
        dob = date(1939, 1, 1)
        low, high = age_arithmetic.estimate_year_from_age_bucket(dob, "in_school")
        self.assertEqual((low, high), (1944, 1950))

    def test_dec_born_narrator(self):
        dob = date(1939, 12, 31)
        low, high = age_arithmetic.estimate_year_from_age_bucket(dob, "in_school")
        self.assertEqual((low, high), (1944, 1950))

    def test_leap_year_dob(self):
        dob = date(1940, 2, 29)
        low, high = age_arithmetic.estimate_year_from_age_bucket(dob, "in_school")
        self.assertEqual((low, high), (1945, 1951))


class ParseDobTest(unittest.TestCase):
    def test_iso_date(self):
        self.assertEqual(age_arithmetic.parse_dob("1939-08-30"), date(1939, 8, 30))

    def test_iso_datetime(self):
        self.assertEqual(
            age_arithmetic.parse_dob("1939-08-30T00:00:00"),
            date(1939, 8, 30),
        )

    def test_slash_format(self):
        self.assertEqual(age_arithmetic.parse_dob("1939/08/30"), date(1939, 8, 30))

    def test_us_format(self):
        self.assertEqual(age_arithmetic.parse_dob("08/30/1939"), date(1939, 8, 30))

    def test_year_only(self):
        # "born around 1939" — land on Jan 1 of that year.
        self.assertEqual(age_arithmetic.parse_dob("1939"), date(1939, 1, 1))

    def test_garbage(self):
        self.assertIsNone(age_arithmetic.parse_dob("not a date"))

    def test_year_out_of_range(self):
        # 1700 is before our 1850 floor; refuse rather than guess.
        self.assertIsNone(age_arithmetic.parse_dob("1700"))

    def test_none(self):
        self.assertIsNone(age_arithmetic.parse_dob(None))

    def test_empty(self):
        self.assertIsNone(age_arithmetic.parse_dob(""))

    def test_non_string(self):
        self.assertIsNone(age_arithmetic.parse_dob(12345))  # type: ignore[arg-type]


class AllKnownBucketsTest(unittest.TestCase):
    def test_returns_sorted_list(self):
        buckets = age_arithmetic.all_known_buckets()
        self.assertEqual(buckets, sorted(buckets))
        self.assertGreater(len(buckets), 0)

    def test_includes_canonical_set(self):
        buckets = age_arithmetic.all_known_buckets()
        for required in ("very_little", "in_school", "older", "young_adult"):
            self.assertIn(required, buckets)


if __name__ == "__main__":
    unittest.main(verbosity=2)
