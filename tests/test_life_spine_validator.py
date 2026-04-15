"""WO-EX-VALIDATE-01 unit tests.

Pure-Python tests for life_spine/validator.py. No API server required,
no DB required. Run with:

    cd server/code
    python -m pytest ../../tests/test_life_spine_validator.py -v

Or with plain unittest:

    python -m unittest tests.test_life_spine_validator
"""
import os
import sys
import unittest
from datetime import date

# Add server/code to path so `from api.life_spine...` resolves
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "server", "code"))

from api.life_spine.validator import (  # noqa: E402
    ValidationResult,
    compute_age,
    validate_event,
    validate_fact,
)


class ComputeAgeTests(unittest.TestCase):
    def test_basic_age(self):
        # Chris: DOB 1962-12-24
        self.assertEqual(compute_age("1962-12-24", 1980), 17)  # event July 1980 (pre-birthday)
        self.assertEqual(compute_age("1962-12-24", 1981, 1, 1), 18)  # Jan 1981

    def test_event_before_birth_negative(self):
        # Event midpoint = July 1 1960. DOB = Dec 24 1962.
        # 1960 - 1962 = -2, and (Jul 1) < (Dec 24) so subtract 1 → -3.
        # The validator only cares that age is negative — value is -3.
        self.assertEqual(compute_age("1962-12-24", 1960), -3)
        self.assertEqual(compute_age("1962-12-24", 1961, 12, 25), -1)

    def test_birthday_boundary(self):
        # Event ON birthday = age that many years
        self.assertEqual(compute_age("1962-12-24", 1982, 12, 24), 20)
        # Event day before = one less
        self.assertEqual(compute_age("1962-12-24", 1982, 12, 23), 19)


class ValidateEventTests(unittest.TestCase):
    def test_event_before_birth_is_impossible(self):
        r = validate_event("first_job", 1950, "1962-12-24")
        self.assertEqual(r.flag, "impossible")
        self.assertIn("predates", r.reason)

    def test_civic_below_min_age_is_impossible(self):
        # voting at age 10 — 18 is a hard min
        r = validate_event("civic_voting_age", 1972, "1962-12-24")
        self.assertEqual(r.flag, "impossible")

    def test_voting_at_18_ok(self):
        # Chris first eligible to vote in 1980 (he was 17→18 Dec 1980)
        r = validate_event("civic_voting_age", 1980, "1962-12-24")
        # July 1980 Chris is 17, but 18 by Dec → our midpoint July returns 17
        # which is BELOW the 18 floor → impossible. Test the clean case:
        r2 = validate_event("civic_voting_age", 1981, "1962-12-24")
        self.assertEqual(r2.flag, "ok")

    def test_medicare_below_65_impossible(self):
        r = validate_event("civic_medicare_eligible", 2000, "1962-12-24")
        self.assertEqual(r.flag, "impossible")

    def test_medicare_at_65_ok(self):
        r = validate_event("civic_medicare_eligible", 2028, "1962-12-24")
        self.assertEqual(r.flag, "ok")

    def test_kindergarten_warn_at_age_3(self):
        # kindergarten at age 3 — envelope min is 4, severity=warn
        r = validate_event("school_kindergarten", 1965, "1962-12-24")
        self.assertEqual(r.flag, "warn")

    def test_unknown_event_kind_is_ok(self):
        r = validate_event("nonsense_event", 2000, "1962-12-24")
        self.assertEqual(r.flag, "ok")

    def test_missing_dob_is_ok(self):
        r = validate_event("first_job", 1980, "")
        self.assertEqual(r.flag, "ok")

    def test_age_over_110_warn(self):
        r = validate_event("retirement", 2080, "1962-12-24")
        self.assertEqual(r.flag, "warn")
        self.assertIn("110", r.reason)


class ValidateFactTests(unittest.TestCase):
    def test_dob_field_passes_through(self):
        r = validate_fact("personal.dateOfBirth", "1962-12-24", "1962-12-24")
        self.assertEqual(r.flag, "ok")

    def test_dob_out_of_range_warns(self):
        r = validate_fact("personal.dateOfBirth", "1700-01-01", "1962-12-24")
        self.assertEqual(r.flag, "warn")

    def test_retirement_field_with_year_in_string(self):
        # "retired in 1985" at age 22 → age below retirement envelope (50) → warn
        r = validate_fact("laterYears.retirement", "retired in 1985", "1962-12-24")
        self.assertEqual(r.flag, "warn")
        self.assertEqual(r.age_at_event, 22)

    def test_college_start_override(self):
        # Use event_kind_override for fields not in the default map
        r = validate_fact(
            "education.higherEducation",
            "started 1981",
            "1962-12-24",
            event_kind_override="education_college_start",
        )
        # Age 18 in 1981 — within envelope (16-35)
        self.assertEqual(r.flag, "ok")

    def test_no_dob_always_ok(self):
        r = validate_fact("education.earlyCareer", "1990", None)
        self.assertEqual(r.flag, "ok")


class JaneDoeFixtureTests(unittest.TestCase):
    """Cross-check against the research-doc sample dataset.

    Jane Doe DOB 1985-04-12, five events:
      - birth              1985-04-12  ok
      - kindergarten start 1990        ok    (age 5)
      - drivers license    2001        ok    (age 16)
      - college graduation 2007        ok    (age 22)
      - first child        1983        impossible (predates birth)
    """
    DOB = "1985-04-12"

    def test_birth_itself_ok(self):
        r = validate_fact("personal.dateOfBirth", self.DOB, self.DOB)
        self.assertEqual(r.flag, "ok")

    def test_kindergarten_age_5_ok(self):
        r = validate_event("school_kindergarten", 1990, self.DOB)
        self.assertEqual(r.flag, "ok")
        self.assertEqual(r.age_at_event, 5)

    def test_drivers_license_age_16_ok(self):
        r = validate_event("civic_drivers_license_age", 2001, self.DOB)
        self.assertEqual(r.flag, "ok")

    def test_college_graduation_age_22_ok(self):
        r = validate_event("education_college_grad", 2007, self.DOB)
        self.assertEqual(r.flag, "ok")
        self.assertEqual(r.age_at_event, 22)

    def test_first_child_before_birth_impossible(self):
        r = validate_event("child_birth", 1983, self.DOB)
        self.assertEqual(r.flag, "impossible")


if __name__ == "__main__":
    unittest.main()
