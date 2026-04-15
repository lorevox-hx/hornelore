"""WO-EX-01C — narrator identity subject-filter regressions.

Tests the two live Chris-session bugs:
  Bug A: 'we lived in West Fargo...'      → personal.placeOfBirth=west Fargo
  Bug B: 'he [my son] was born 4/10/2002' → personal.dateOfBirth / placeOfBirth

Plus the month-name sanity layer.

Run with:
    cd hornelore
    python -m unittest tests.test_extract_subject_filters
"""
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "server", "code"))

# Stub FastAPI + pydantic for isolated unit testing of the pure helpers.
# In dev/prod the real packages are available and these stubs do nothing.
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
    _apply_birth_context_filter,
    _apply_month_name_sanity,
    _apply_narrator_identity_subject_filter,
    _is_birth_context,
    _subject_is_narrator_context,
)


class ExtractSubjectFilterTests(unittest.TestCase):
    def test_west_fargo_childhood_residence_not_birthplace(self):
        """Bug A — verbatim from Chris's session."""
        answer = (
            "When I was in kindergarten we lived in West Fargo in a trailer court. "
            "My parents were going to school at NDSU. We'd ride the bus home from school."
        )
        llm_items = [
            {"fieldPath": "personal.placeOfBirth", "value": "West Fargo",
             "confidence": 0.91},
            {"fieldPath": "education.schooling",
             "value": "kindergarten in West Fargo", "confidence": 0.72},
        ]
        filtered = _apply_birth_context_filter(
            llm_items,
            current_section="school_years",
            answer=answer,
            current_phase="elementary",
        )
        field_paths = [x["fieldPath"] for x in filtered]
        self.assertNotIn("personal.placeOfBirth", field_paths)
        self.assertIn("education.schooling", field_paths)

    def test_west_fargo_later_life_tab_still_not_birthplace(self):
        """Bug A — same answer but UI was in Later Life."""
        answer = (
            "When I was in kindergarten we lived in West Fargo in a trailer court. "
            "My parents were going to school at NDSU. We'd ride the bus home from school."
        )
        llm_items = [
            {"fieldPath": "personal.placeOfBirth", "value": "West Fargo",
             "confidence": 0.88},
        ]
        filtered = _apply_birth_context_filter(
            llm_items,
            current_section="later_life",
            answer=answer,
            current_phase="post_school",
        )
        self.assertEqual(filtered, [])

    def test_west_fargo_missing_section_still_safe(self):
        """Client forgets to send current_section. None must NOT be permissive."""
        answer = (
            "When I was in kindergarten we lived in West Fargo in a trailer court."
        )
        llm_items = [
            {"fieldPath": "personal.placeOfBirth", "value": "West Fargo",
             "confidence": 0.88},
        ]
        filtered = _apply_birth_context_filter(llm_items, None, answer, None)
        self.assertEqual(filtered, [])

    def test_child_birth_does_not_pollute_narrator_dob(self):
        """Bug B — verbatim from Chris's session."""
        answer = (
            "In 2022 my youngest son Cole Harber La Plante Horne graduated from "
            "West Las Vegas High School, and he was born April 10 2002."
        )
        llm_items = [
            {"fieldPath": "personal.dateOfBirth", "value": "2002-04-10",
             "confidence": 0.93},
            {"fieldPath": "personal.placeOfBirth", "value": "April",
             "confidence": 0.42},
            {"fieldPath": "education.schooling",
             "value": "youngest son graduated from West Las Vegas High School in 2022",
             "confidence": 0.67},
        ]
        filtered = _apply_narrator_identity_subject_filter(llm_items, answer)
        field_paths = [x["fieldPath"] for x in filtered]
        self.assertNotIn("personal.dateOfBirth", field_paths)
        self.assertNotIn("personal.placeOfBirth", field_paths)
        self.assertIn("education.schooling", field_paths)

    def test_explicit_narrator_birth_statement_still_allowed(self):
        """Protection against over-filtering — legit narrator birth passes."""
        answer = "I was born in Williston, North Dakota on December 24, 1962."
        llm_items = [
            {"fieldPath": "personal.placeOfBirth", "value": "Williston, North Dakota",
             "confidence": 0.96},
            {"fieldPath": "personal.dateOfBirth", "value": "1962-12-24",
             "confidence": 0.97},
        ]
        # Works in personal_information section
        filtered = _apply_birth_context_filter(
            llm_items, "personal_information", answer, "pre_school",
        )
        field_paths = [x["fieldPath"] for x in filtered]
        self.assertIn("personal.placeOfBirth", field_paths)
        self.assertIn("personal.dateOfBirth", field_paths)

    def test_explicit_narrator_birth_in_later_life_still_allowed(self):
        """Narrator volunteers birth statement in a non-birth section —
        the subject filter should let it through even though
        _is_birth_context is False, because _answer_has_explicit_birth_phrase
        fires and the subject filter finds 'I was born' signal."""
        answer = "I was born in Williston, North Dakota on December 24, 1962."
        llm_items = [
            {"fieldPath": "personal.placeOfBirth", "value": "Williston, North Dakota",
             "confidence": 0.96},
            {"fieldPath": "personal.dateOfBirth", "value": "1962-12-24",
             "confidence": 0.97},
        ]
        filtered = _apply_birth_context_filter(
            llm_items, "later_life", answer, "post_school",
        )
        field_paths = [x["fieldPath"] for x in filtered]
        self.assertIn("personal.placeOfBirth", field_paths)
        self.assertIn("personal.dateOfBirth", field_paths)

    def test_generic_born_without_narrator_signal_is_blocked(self):
        """Third-person 'born' must not pass through as narrator identity."""
        answer = "He was born April 10 2002."
        llm_items = [
            {"fieldPath": "personal.dateOfBirth", "value": "2002-04-10",
             "confidence": 0.9},
        ]
        filtered = _apply_birth_context_filter(
            llm_items, "early_childhood", answer, "elementary",
        )
        self.assertEqual(filtered, [])


class SubjectContextSemanticsTests(unittest.TestCase):
    """Direct tests of _subject_is_narrator_context semantics."""

    def test_i_was_born_narrator(self):
        self.assertTrue(_subject_is_narrator_context("I was born in Williston"))

    def test_my_birthday_is_narrator(self):
        self.assertTrue(_subject_is_narrator_context("my birthday is December 24"))

    def test_he_was_born_not_narrator(self):
        self.assertFalse(_subject_is_narrator_context("he was born in 2002"))

    def test_my_son_not_narrator(self):
        self.assertFalse(_subject_is_narrator_context("my son Cole graduated in 2022"))

    def test_my_grandson_not_narrator(self):
        self.assertFalse(_subject_is_narrator_context("my grandson was born last year"))

    def test_ambiguous_born_defaults_not_narrator(self):
        """Ambiguous 'born' with no clear subject → conservative False."""
        self.assertFalse(_subject_is_narrator_context("born in 1962"))

    def test_mixed_narrator_wins(self):
        """Positive-first: narrator signal found first wins."""
        self.assertTrue(_subject_is_narrator_context(
            "I was born in Williston. My son was born in Fargo."
        ))

    def test_empty_not_narrator(self):
        self.assertFalse(_subject_is_narrator_context(""))

    def test_no_birth_mention_defaults_narrator(self):
        """No birth claim in answer → default True (nothing to gate)."""
        self.assertTrue(_subject_is_narrator_context("I live in Las Vegas now"))


class MonthNameSanityTests(unittest.TestCase):
    """Month-name blacklist for placeOfBirth values — catches LLM mistakes
    like extracting 'april' from 'born in april 10 2002'."""

    def test_april_not_placeofbirth(self):
        items = [{"fieldPath": "personal.placeOfBirth", "value": "april",
                  "confidence": 0.6}]
        self.assertEqual(_apply_month_name_sanity(items), [])

    def test_capitalized_and_punctuated_months_caught(self):
        for v in ("January", "JANUARY", "jan", "Jan.", "February,", "Sept"):
            items = [{"fieldPath": "personal.placeOfBirth", "value": v,
                      "confidence": 0.6}]
            self.assertEqual(_apply_month_name_sanity(items), [],
                             f"failed for value={v!r}")

    def test_legit_cities_pass(self):
        items = [
            {"fieldPath": "personal.placeOfBirth", "value": "Williston",
             "confidence": 0.9},
            {"fieldPath": "personal.placeOfBirth", "value": "Fargo, ND",
             "confidence": 0.9},
        ]
        self.assertEqual(len(_apply_month_name_sanity(items)), 2)

    def test_other_fields_untouched(self):
        """Only placeOfBirth is sanity-checked — other fields with month-like
        values pass (e.g., hobby 'march protests')."""
        items = [{"fieldPath": "hobbies.hobbies", "value": "march",
                  "confidence": 0.5}]
        self.assertEqual(_apply_month_name_sanity(items), items)


class IsBirthContextTests(unittest.TestCase):
    """Stricter section-only gate — catches clients that forget current_section."""

    def test_none_section_is_strict(self):
        self.assertFalse(_is_birth_context(None))
        self.assertFalse(_is_birth_context(""))

    def test_named_birth_sections_ok(self):
        self.assertTrue(_is_birth_context("early_childhood"))
        self.assertTrue(_is_birth_context("earliest_memories"))
        self.assertTrue(_is_birth_context("personal"))
        self.assertTrue(_is_birth_context("personal_information"))
        self.assertTrue(_is_birth_context("Personal"))  # case-insensitive

    def test_other_sections_not_birth(self):
        for s in ("early_years", "school_years", "later_life",
                  "career_and_achievements", "adolescence"):
            self.assertFalse(_is_birth_context(s), f"failed for {s!r}")

    def test_phase_does_not_relax(self):
        """Pre-school phase used to flip to True; that was the root cause
        of the West Fargo bug. Phase must be inert now."""
        self.assertFalse(_is_birth_context("school_years", "pre_school"))
        self.assertFalse(_is_birth_context("early_years", "pre_school"))


if __name__ == "__main__":
    unittest.main()
