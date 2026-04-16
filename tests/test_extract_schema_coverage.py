"""WO-EX-SCHEMA-01 — Schema coverage tests.

Verifies:
  1. All 6 new field families exist in EXTRACTABLE_FIELDS
  2. New field paths survive _validate_item
  3. Aliases for new families resolve correctly
  4. Question bank extract_priority references all map to valid fields
  5. No regressions in existing guard stack

Run with:
    cd hornelore
    python -m unittest tests.test_extract_schema_coverage
"""
import json
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "server", "code"))

# Stub FastAPI + pydantic for isolated unit testing.
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
    class _Field:
        pass
    pd.BaseModel = _BaseModel
    pd.Field = lambda **kw: None
    sys.modules["pydantic"] = pd

from api.routers.extract import (  # noqa: E402
    EXTRACTABLE_FIELDS,
    _validate_item,
    _apply_birth_context_filter,
    _apply_field_value_sanity,
    _apply_month_name_sanity,
)


class TestSchemaFieldFamilies(unittest.TestCase):
    """Verify all 6 new field families are present in EXTRACTABLE_FIELDS."""

    def test_children_fields_exist(self):
        expected = [
            "family.children.relation",
            "family.children.firstName",
            "family.children.lastName",
            "family.children.dateOfBirth",
            "family.children.placeOfBirth",
            "family.children.preferredName",
        ]
        for fp in expected:
            self.assertIn(fp, EXTRACTABLE_FIELDS, f"Missing: {fp}")
            self.assertEqual(EXTRACTABLE_FIELDS[fp]["repeatable"], "children")

    def test_spouse_fields_exist(self):
        expected = [
            "family.spouse.firstName",
            "family.spouse.lastName",
            "family.spouse.maidenName",
            "family.spouse.dateOfBirth",
            "family.spouse.placeOfBirth",
        ]
        for fp in expected:
            self.assertIn(fp, EXTRACTABLE_FIELDS, f"Missing: {fp}")
            # Spouse fields are NOT repeatable
            self.assertNotIn("repeatable", EXTRACTABLE_FIELDS[fp])

    def test_marriage_fields_exist(self):
        expected = [
            "family.marriageDate",
            "family.marriagePlace",
            "family.marriageNotes",
        ]
        for fp in expected:
            self.assertIn(fp, EXTRACTABLE_FIELDS, f"Missing: {fp}")

    def test_prior_partners_fields_exist(self):
        expected = [
            "family.priorPartners.firstName",
            "family.priorPartners.lastName",
            "family.priorPartners.period",
        ]
        for fp in expected:
            self.assertIn(fp, EXTRACTABLE_FIELDS, f"Missing: {fp}")
            self.assertEqual(EXTRACTABLE_FIELDS[fp]["repeatable"], "priorPartners")

    def test_grandchildren_fields_exist(self):
        expected = [
            "family.grandchildren.firstName",
            "family.grandchildren.relation",
            "family.grandchildren.notes",
        ]
        for fp in expected:
            self.assertIn(fp, EXTRACTABLE_FIELDS, f"Missing: {fp}")
            self.assertEqual(EXTRACTABLE_FIELDS[fp]["repeatable"], "grandchildren")

    def test_residence_fields_exist(self):
        expected = [
            "residence.place",
            "residence.region",
            "residence.period",
            "residence.notes",
        ]
        for fp in expected:
            self.assertIn(fp, EXTRACTABLE_FIELDS, f"Missing: {fp}")
            self.assertEqual(EXTRACTABLE_FIELDS[fp]["repeatable"], "residences")

    def test_later_years_significant_event_exists(self):
        self.assertIn("laterYears.significantEvent", EXTRACTABLE_FIELDS)


class TestNewFieldValidation(unittest.TestCase):
    """Verify new field paths survive _validate_item."""

    def _make_item(self, fp, val, conf=0.9):
        return {"fieldPath": fp, "value": val, "confidence": conf}

    def test_child_firstname_validates(self):
        result = _validate_item(self._make_item("family.children.firstName", "Vince"))
        self.assertIsNotNone(result)
        self.assertEqual(result["fieldPath"], "family.children.firstName")
        self.assertEqual(result["value"], "Vince")

    def test_child_dob_validates(self):
        result = _validate_item(self._make_item("family.children.dateOfBirth", "1960"))
        self.assertIsNotNone(result)
        self.assertEqual(result["fieldPath"], "family.children.dateOfBirth")

    def test_child_pob_validates(self):
        result = _validate_item(self._make_item("family.children.placeOfBirth", "Germany"))
        self.assertIsNotNone(result)
        self.assertEqual(result["fieldPath"], "family.children.placeOfBirth")

    def test_spouse_firstname_validates(self):
        result = _validate_item(self._make_item("family.spouse.firstName", "Dorothy"))
        self.assertIsNotNone(result)
        self.assertEqual(result["fieldPath"], "family.spouse.firstName")

    def test_marriage_date_validates(self):
        result = _validate_item(self._make_item("family.marriageDate", "1958"))
        self.assertIsNotNone(result)
        self.assertEqual(result["fieldPath"], "family.marriageDate")

    def test_marriage_place_validates(self):
        result = _validate_item(self._make_item("family.marriagePlace", "Fargo"))
        self.assertIsNotNone(result)

    def test_residence_place_validates(self):
        result = _validate_item(self._make_item("residence.place", "West Fargo"))
        self.assertIsNotNone(result)
        self.assertEqual(result["fieldPath"], "residence.place")

    def test_residence_period_validates(self):
        result = _validate_item(self._make_item("residence.period", "1962-1964"))
        self.assertIsNotNone(result)

    def test_grandchild_validates(self):
        result = _validate_item(self._make_item("family.grandchildren.firstName", "Emma"))
        self.assertIsNotNone(result)

    def test_prior_partner_validates(self):
        result = _validate_item(self._make_item("family.priorPartners.firstName", "Helen"))
        self.assertIsNotNone(result)


class TestNewFieldAliases(unittest.TestCase):
    """Verify common LLM alias variants resolve to new field paths."""

    def _make_item(self, fp, val):
        return {"fieldPath": fp, "value": val, "confidence": 0.9}

    def test_son_alias(self):
        result = _validate_item(self._make_item("son", "son"))
        self.assertIsNotNone(result)
        self.assertEqual(result["fieldPath"], "family.children.relation")

    def test_daughter_alias(self):
        result = _validate_item(self._make_item("daughter", "daughter"))
        self.assertIsNotNone(result)
        self.assertEqual(result["fieldPath"], "family.children.relation")

    def test_child_name_alias(self):
        result = _validate_item(self._make_item("childName", "Cole"))
        self.assertIsNotNone(result)
        self.assertEqual(result["fieldPath"], "family.children.firstName")

    def test_spouse_name_alias(self):
        result = _validate_item(self._make_item("spouseName", "Dorothy"))
        self.assertIsNotNone(result)
        self.assertEqual(result["fieldPath"], "family.spouse.firstName")

    def test_wife_alias(self):
        result = _validate_item(self._make_item("wife", "Betty"))
        self.assertIsNotNone(result)
        self.assertEqual(result["fieldPath"], "family.spouse.firstName")

    def test_marriage_date_alias(self):
        result = _validate_item(self._make_item("marriage_date", "1958"))
        self.assertIsNotNone(result)
        self.assertEqual(result["fieldPath"], "family.marriageDate")

    def test_residence_bare_alias(self):
        result = _validate_item(self._make_item("residence", "Bismarck"))
        self.assertIsNotNone(result)
        self.assertEqual(result["fieldPath"], "residence.place")


class TestQuestionBankCoverage(unittest.TestCase):
    """Verify question_bank extract_priority entries all map to EXTRACTABLE_FIELDS."""

    def test_all_extract_priority_fields_exist_or_alias(self):
        bank_path = os.path.join(HERE, "..", "data", "prompts", "question_bank.json")
        if not os.path.exists(bank_path):
            self.skipTest("question_bank.json not found")

        with open(bank_path, "r") as f:
            bank = json.load(f)

        # Collect all extract_priority values
        all_priorities = set()
        for phase_id, phase in bank.items():
            if not isinstance(phase, dict):
                continue
            for sub in (phase.get("sub_topics") or []):
                for fp in (sub.get("extract_priority") or []):
                    all_priorities.add(fp)

        # Check each one exists in EXTRACTABLE_FIELDS or has a prefix match
        missing = []
        for fp in sorted(all_priorities):
            # Direct match
            if fp in EXTRACTABLE_FIELDS:
                continue
            # Prefix match (e.g., "family.spouse" matches "family.spouse.firstName")
            prefix_match = any(k.startswith(fp + ".") for k in EXTRACTABLE_FIELDS)
            if prefix_match:
                continue
            # Exact family match for aggregated names (e.g., "family.children")
            if any(k.startswith(fp) for k in EXTRACTABLE_FIELDS):
                continue
            missing.append(fp)

        self.assertEqual(missing, [], f"Question bank extract_priority fields not in EXTRACTABLE_FIELDS: {missing}")

    def test_no_underscore_marriage_date(self):
        """Verify marriage_date → marriageDate rename applied."""
        bank_path = os.path.join(HERE, "..", "data", "prompts", "question_bank.json")
        if not os.path.exists(bank_path):
            self.skipTest("question_bank.json not found")

        with open(bank_path, "r") as f:
            content = f.read()

        self.assertNotIn("family.marriage_date", content,
                         "question_bank.json still contains family.marriage_date (should be family.marriageDate)")


class TestGuardStackNoRegression(unittest.TestCase):
    """Verify WO-EX-01C/01D guards still work after schema extension."""

    def test_west_fargo_residence_not_birth_place(self):
        """West Fargo residence should NOT become personal.placeOfBirth."""
        items = [{"fieldPath": "personal.placeOfBirth", "value": "West Fargo",
                  "writeMode": "prefill_if_blank", "confidence": 0.9,
                  "source": "backend_extract", "extractionMethod": "llm"}]
        result = _apply_birth_context_filter(items, "school_years",
                                             "we lived in West Fargo in a trailer court", None)
        pob_items = [i for i in result if i["fieldPath"] == "personal.placeOfBirth"]
        self.assertEqual(len(pob_items), 0, "West Fargo should be stripped outside birth context")

    def test_residence_place_not_affected_by_birth_filter(self):
        """residence.place should pass through birth context filter untouched."""
        items = [{"fieldPath": "residence.place", "value": "West Fargo",
                  "writeMode": "candidate_only", "confidence": 0.9,
                  "source": "backend_extract", "extractionMethod": "llm"}]
        result = _apply_birth_context_filter(items, "school_years",
                                             "we lived in West Fargo in a trailer court", None)
        self.assertEqual(len(result), 1, "residence.place should survive birth context filter")
        self.assertEqual(result[0]["value"], "West Fargo")

    def test_child_dob_not_narrator_dob(self):
        """Child's DOB should NOT become personal.dateOfBirth."""
        items = [{"fieldPath": "personal.dateOfBirth", "value": "2002-04-10",
                  "writeMode": "prefill_if_blank", "confidence": 0.9,
                  "source": "backend_extract", "extractionMethod": "llm"}]
        result = _apply_birth_context_filter(items, "early_childhood",
                                             "my son Cole was born April 10 2002", None)
        pob_items = [i for i in result if i["fieldPath"] == "personal.dateOfBirth"]
        self.assertEqual(len(pob_items), 0, "Child DOB should not become narrator DOB")

    def test_state_abbreviation_sanity_still_works(self):
        """ND as lastName should still be dropped."""
        items = [{"fieldPath": "parents.lastName", "value": "ND",
                  "writeMode": "candidate_only", "confidence": 0.8,
                  "source": "backend_extract", "extractionMethod": "llm"}]
        result = _apply_field_value_sanity(items)
        self.assertEqual(len(result), 0, "State abbreviation lastName should be dropped")

    def test_month_name_sanity_still_works(self):
        """'april' as placeOfBirth should still be dropped."""
        items = [{"fieldPath": "personal.placeOfBirth", "value": "april",
                  "writeMode": "prefill_if_blank", "confidence": 0.8,
                  "source": "backend_extract", "extractionMethod": "llm"}]
        result = _apply_month_name_sanity(items)
        self.assertEqual(len(result), 0, "Month name placeOfBirth should be dropped")

    def test_child_place_of_birth_not_caught_by_month_sanity(self):
        """family.children.placeOfBirth should not be affected by month-name sanity
        (that filter only applies to personal.placeOfBirth)."""
        items = [{"fieldPath": "family.children.placeOfBirth", "value": "Germany",
                  "writeMode": "candidate_only", "confidence": 0.9,
                  "source": "backend_extract", "extractionMethod": "llm"}]
        result = _apply_month_name_sanity(items)
        self.assertEqual(len(result), 1, "Child placeOfBirth should survive month sanity")


if __name__ == "__main__":
    unittest.main()
