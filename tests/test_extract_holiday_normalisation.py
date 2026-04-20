"""WO-EX-PATCH-H-DATEFIELD-01 — holiday-phrase date normaliser tests.

Regression coverage for task #67 (case_011 Patch H un-normalisation):

  1. `_DATE_FIELD_SUFFIXES` now covers the schema-actual date fields
     (`dateOfBirth`, `dateOfDeath`, `dateOfMarriage`) in addition to the
     legacy short forms (`birthDate`, `deathDate`, `marriageDate`).

  2. `_normalize_date_value` now handles colloquial fixed-date holiday
     phrases ("Christmas Eve, 1939", "4th of July 1976", "St. Patrick's
     Day, 1988") in addition to ISO / Month-Day-Year / year-only forms.

  3. The holiday branch does NOT over-match on prose or on unmapped
     variable-feast holidays (Easter, Thanksgiving, etc.).

Run with:
    cd hornelore
    python -m unittest tests.test_extract_holiday_normalisation -v
"""
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "server", "code"))

# ── Stub FastAPI + pydantic (same pattern as test_extract_claims_validators) ──
if "fastapi" not in sys.modules:
    fa = types.ModuleType("fastapi")
    class _APIRouter:
        def __init__(self, *a, **kw): pass
        def post(self, *a, **kw):
            def deco(fn): return fn
            return deco
        def get(self, *a, **kw):
            def deco(fn): return fn
            return deco
    class _HTTPException(Exception): pass
    fa.APIRouter = _APIRouter
    fa.HTTPException = _HTTPException
    sys.modules["fastapi"] = fa

if "pydantic" not in sys.modules:
    pd = types.ModuleType("pydantic")
    class _BaseModel:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)
        def model_dump(self):
            return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}
    pd.BaseModel = _BaseModel
    sys.modules["pydantic"] = pd

from api.routers.extract import (  # noqa: E402
    _normalize_date_value,
    _apply_write_time_normalisation,
    _DATE_FIELD_SUFFIXES,
    _HOLIDAY_DATE_MAP,
)


def _item(fieldPath, value, confidence=0.85):
    return {"fieldPath": fieldPath, "value": value, "confidence": confidence}


# ── Holiday phrase → ISO date ──────────────────────────────────────────────

class TestHolidayNormaliser(unittest.TestCase):
    """#67 Patch H follow-up: colloquial holiday phrases normalise to ISO."""

    # The case_011 regression itself
    def test_case_011_christmas_eve_1939(self):
        self.assertEqual(_normalize_date_value("Christmas Eve, 1939"), "1939-12-24")

    def test_christmas_day(self):
        self.assertEqual(_normalize_date_value("Christmas Day 1950"), "1950-12-25")

    def test_christmas_bare(self):
        self.assertEqual(_normalize_date_value("Christmas 1952"), "1952-12-25")

    def test_xmas_eve(self):
        self.assertEqual(_normalize_date_value("Xmas Eve 1949"), "1949-12-24")

    def test_new_years_eve_curly_apostrophe(self):
        # U+2019 right single quote (common in LLM output)
        self.assertEqual(_normalize_date_value("New Year\u2019s Eve, 1999"), "1999-12-31")

    def test_new_years_day_no_apostrophe(self):
        self.assertEqual(_normalize_date_value("New Years Day 2001"), "2001-01-01")

    def test_valentines_day_with_apostrophe(self):
        self.assertEqual(_normalize_date_value("Valentine's Day 1975"), "1975-02-14")

    def test_st_patricks_day_period_in_abbrev(self):
        # Exercises the `.` in the regex char class (r4i Edit 3 fix)
        self.assertEqual(_normalize_date_value("St. Patrick's Day, 1988"), "1988-03-17")

    def test_halloween(self):
        self.assertEqual(_normalize_date_value("Halloween 1965"), "1965-10-31")

    def test_veterans_day(self):
        self.assertEqual(_normalize_date_value("Veterans Day 1968"), "1968-11-11")

    def test_fourth_of_july_word_form(self):
        self.assertEqual(_normalize_date_value("Fourth of July 1952"), "1952-07-04")

    def test_4th_of_july_digit_prefix(self):
        # Exercises the `0-9` in the regex char class (r4i Edit 3 fix)
        self.assertEqual(_normalize_date_value("4th of July, 1976"), "1976-07-04")

    def test_july_4th_digit_suffix(self):
        self.assertEqual(_normalize_date_value("July 4th, 1980"), "1980-07-04")

    def test_independence_day(self):
        self.assertEqual(_normalize_date_value("Independence Day 1945"), "1945-07-04")

    def test_boxing_day(self):
        self.assertEqual(_normalize_date_value("Boxing Day 1955"), "1955-12-26")

    def test_all_hallows_eve(self):
        self.assertEqual(_normalize_date_value("All Hallows Eve, 1955"), "1955-10-31")

    # Longest-prefix match — "christmas eve" must win over "christmas"
    def test_longest_prefix_match_christmas_eve_vs_christmas(self):
        self.assertEqual(_normalize_date_value("Christmas Eve 1939"), "1939-12-24")


# ── Non-holiday passthroughs (regression guards) ──────────────────────────

class TestHolidayNonInterference(unittest.TestCase):
    """Verify the holiday branch does NOT over-match on ISO, MDY, or prose."""

    def test_iso_passthrough(self):
        self.assertEqual(_normalize_date_value("1939-12-24"), "1939-12-24")

    def test_mdy_full_month(self):
        self.assertEqual(_normalize_date_value("December 24, 1939"), "1939-12-24")

    def test_mdy_abbreviated(self):
        self.assertEqual(_normalize_date_value("Dec 24 1939"), "1939-12-24")

    def test_year_only(self):
        self.assertEqual(_normalize_date_value("1942"), "1942")

    def test_empty_string(self):
        self.assertEqual(_normalize_date_value(""), "")

    def test_prose_with_year_long(self):
        # Year-only fallback has a len(s) <= 10 cap, so longer prose stays raw.
        self.assertEqual(
            _normalize_date_value("some random Tuesday 1980"),
            "some random Tuesday 1980",
        )

    def test_prose_with_year_long_period(self):
        self.assertEqual(
            _normalize_date_value("I graduated in 1968."),
            "I graduated in 1968.",
        )

    # Variable feasts (Easter, Thanksgiving, etc.) are intentionally
    # excluded from _HOLIDAY_DATE_MAP and should pass through unchanged.
    def test_easter_sunday_not_normalised(self):
        self.assertEqual(
            _normalize_date_value("Easter Sunday 1947"),
            "Easter Sunday 1947",
        )

    def test_thanksgiving_not_normalised(self):
        self.assertEqual(
            _normalize_date_value("Thanksgiving, 1963"),
            "Thanksgiving, 1963",
        )


# ── Field-suffix coverage (the real case_011 root cause) ──────────────────

class TestDateFieldSuffixCoverage(unittest.TestCase):
    """#67 root cause: `personal.dateOfBirth` did not match the old suffix
    set {birthDate, deathDate, marriageDate}, so the normaliser never ran
    on it. Verify the schema-actual long forms are now recognised."""

    def test_dateOfBirth_included(self):
        self.assertIn("dateOfBirth", _DATE_FIELD_SUFFIXES)

    def test_dateOfDeath_included(self):
        self.assertIn("dateOfDeath", _DATE_FIELD_SUFFIXES)

    def test_dateOfMarriage_included(self):
        self.assertIn("dateOfMarriage", _DATE_FIELD_SUFFIXES)

    def test_legacy_birthDate_still_included(self):
        self.assertIn("birthDate", _DATE_FIELD_SUFFIXES)

    def test_legacy_deathDate_still_included(self):
        self.assertIn("deathDate", _DATE_FIELD_SUFFIXES)

    def test_legacy_marriageDate_still_included(self):
        self.assertIn("marriageDate", _DATE_FIELD_SUFFIXES)


# ── End-to-end via _apply_write_time_normalisation ────────────────────────

class TestWriteTimeNormalisationEndToEnd(unittest.TestCase):
    """Confirm the normaliser fires through the full apply() path for the
    schema-actual field names — this is what the live pipeline calls."""

    def test_personal_dateOfBirth_christmas_eve(self):
        items = [_item("personal.dateOfBirth", "Christmas Eve, 1939")]
        out = _apply_write_time_normalisation(items)
        self.assertEqual(out[0]["value"], "1939-12-24")

    def test_personal_dateOfDeath_iso_passthrough(self):
        items = [_item("personal.dateOfDeath", "2015-06-12")]
        out = _apply_write_time_normalisation(items)
        self.assertEqual(out[0]["value"], "2015-06-12")

    def test_family_dateOfMarriage_holiday(self):
        items = [_item("family.dateOfMarriage", "Valentine's Day 1975")]
        out = _apply_write_time_normalisation(items)
        self.assertEqual(out[0]["value"], "1975-02-14")

    def test_non_date_field_not_normalised(self):
        # A firstName field should not be touched by the date branch even
        # if its value accidentally looks like a holiday phrase.
        items = [_item("parents.firstName", "Christmas Eve, 1939")]
        out = _apply_write_time_normalisation(items)
        # firstName branch will Title-case it but won't ISO-normalise
        self.assertNotEqual(out[0]["value"], "1939-12-24")

    def test_non_string_value_skipped(self):
        items = [_item("personal.dateOfBirth", 1939)]
        out = _apply_write_time_normalisation(items)
        self.assertEqual(out[0]["value"], 1939)


# ── Holiday map completeness sanity ────────────────────────────────────────

class TestHolidayMapSanity(unittest.TestCase):
    """Confirm the holiday map keys are lower-case, apostrophe-stripped,
    and free of duplicate (month, day) bugs that would cause lookups to
    silently return the wrong date."""

    def test_keys_are_lowercase(self):
        for k in _HOLIDAY_DATE_MAP.keys():
            self.assertEqual(k, k.lower(), f"key {k!r} is not lowercase")

    def test_keys_have_no_apostrophes(self):
        for k in _HOLIDAY_DATE_MAP.keys():
            self.assertNotIn("'", k, f"key {k!r} contains a straight apostrophe")
            self.assertNotIn("\u2019", k, f"key {k!r} contains a curly apostrophe")

    def test_month_day_values_in_valid_range(self):
        for k, (m, d) in _HOLIDAY_DATE_MAP.items():
            mi, di = int(m), int(d)
            self.assertTrue(1 <= mi <= 12, f"{k!r}: month {m} out of range")
            self.assertTrue(1 <= di <= 31, f"{k!r}: day {d} out of range")


if __name__ == "__main__":
    unittest.main()
