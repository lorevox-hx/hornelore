"""WO-EX-CLAIMS-02 — quick-win post-extraction validator tests.

Tests the three validators added by CLAIMS-02:
  1. Value-shape rejection (garbage words, sub-3-char narrative values)
  2. Relation allowlist (only known relation terms pass)
  3. Confidence floor (below 0.5 rejected)

Run with:
    cd hornelore
    python -m unittest tests.test_extract_claims_validators -v
"""
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "server", "code"))

# ── Stub FastAPI + pydantic (same pattern as test_extract_subject_filters) ──
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
    _apply_claims_value_shape,
    _apply_claims_relation_allowlist,
    _apply_claims_confidence_floor,
    _apply_claims_validators,
)


def _item(fieldPath, value, confidence=0.85):
    return {"fieldPath": fieldPath, "value": value, "confidence": confidence}


# ── Validator 1: Value-shape rejection ─────────────────────────────────────

class TestValueShapeValidator(unittest.TestCase):
    """WO-EX-CLAIMS-02 validator 1: garbage words and short fragments."""

    def test_rejects_connector_word_then(self):
        items = [_item("family.children.relation", "then")]
        self.assertEqual(_apply_claims_value_shape(items), [])

    def test_rejects_connector_word_and(self):
        items = [_item("family.children.firstName", "and")]
        self.assertEqual(_apply_claims_value_shape(items), [])

    def test_rejects_connector_word_kids(self):
        items = [_item("family.children.relation", "kids")]
        self.assertEqual(_apply_claims_value_shape(items), [])

    def test_rejects_bare_was(self):
        items = [_item("education.higherEducation", "was")]
        self.assertEqual(_apply_claims_value_shape(items), [])

    def test_keeps_real_name_value(self):
        items = [_item("family.children.firstName", "Gretchen")]
        self.assertEqual(len(_apply_claims_value_shape(items)), 1)

    def test_keeps_real_narrative_value(self):
        items = [_item("education.higherEducation", "Graduated from NDSU with a business degree")]
        self.assertEqual(len(_apply_claims_value_shape(items)), 1)

    def test_rejects_short_narrative_value(self):
        """Sub-3-char values for narrative fields are rejected."""
        items = [_item("education.careerProgression", "ok")]
        self.assertEqual(_apply_claims_value_shape(items), [])

    def test_keeps_short_exempt_field(self):
        """Short values in name/date/code fields are NOT rejected."""
        items = [_item("personal.gender", "M")]
        self.assertEqual(len(_apply_claims_value_shape(items)), 1)

    def test_keeps_state_abbreviation_in_state_field(self):
        """Two-char state abbreviations should survive in .state fields."""
        items = [_item("residence.state", "ND")]
        self.assertEqual(len(_apply_claims_value_shape(items)), 1)

    def test_keeps_birth_order_numeric(self):
        """Numeric birthOrder like '3' (one char) should survive."""
        items = [_item("personal.birthOrder", "3")]
        self.assertEqual(len(_apply_claims_value_shape(items)), 1)

    def test_rejects_with_trailing_punctuation(self):
        """Garbage words with trailing punctuation should still be caught."""
        items = [_item("family.children.relation", "then,")]
        self.assertEqual(_apply_claims_value_shape(items), [])

    def test_keeps_valid_location(self):
        """Real location values pass through."""
        items = [_item("residence.city", "Fargo")]
        self.assertEqual(len(_apply_claims_value_shape(items)), 1)


# ── Validator 2: Relation allowlist ────────────────────────────────────────

class TestRelationAllowlist(unittest.TestCase):
    """WO-EX-CLAIMS-02 validator 2: only known relations survive."""

    def test_rejects_relation_then(self):
        items = [_item("family.children.relation", "then")]
        self.assertEqual(_apply_claims_relation_allowlist(items), [])

    def test_rejects_relation_and(self):
        items = [_item("family.children.relation", "and")]
        self.assertEqual(_apply_claims_relation_allowlist(items), [])

    def test_rejects_relation_kids(self):
        items = [_item("family.children.relation", "kids")]
        self.assertEqual(_apply_claims_relation_allowlist(items), [])

    def test_accepts_relation_daughter(self):
        items = [_item("family.children.relation", "daughter")]
        self.assertEqual(len(_apply_claims_relation_allowlist(items)), 1)

    def test_accepts_relation_son(self):
        items = [_item("family.children.relation", "son")]
        self.assertEqual(len(_apply_claims_relation_allowlist(items)), 1)

    def test_accepts_relation_brother(self):
        items = [_item("family.siblings.relation", "brother")]
        self.assertEqual(len(_apply_claims_relation_allowlist(items)), 1)

    def test_accepts_hyphenated_relation(self):
        """Half-brother, mother-in-law, etc. should be accepted."""
        items = [_item("family.siblings.relation", "half-brother")]
        self.assertEqual(len(_apply_claims_relation_allowlist(items)), 1)

    def test_accepts_spaced_hyphenated_relation(self):
        """'mother in law' (with spaces) should match 'mother-in-law'."""
        items = [_item("parents.relation", "mother in law")]
        self.assertEqual(len(_apply_claims_relation_allowlist(items)), 1)

    def test_does_not_filter_non_relation_fields(self):
        """Non-.relation fields should pass through unfiltered."""
        items = [_item("family.children.firstName", "then")]
        self.assertEqual(len(_apply_claims_relation_allowlist(items)), 1)

    def test_accepts_with_trailing_whitespace(self):
        items = [_item("family.children.relation", " daughter ")]
        self.assertEqual(len(_apply_claims_relation_allowlist(items)), 1)

    def test_accepts_case_insensitive(self):
        items = [_item("family.children.relation", "Daughter")]
        self.assertEqual(len(_apply_claims_relation_allowlist(items)), 1)


# ── Validator 3: Confidence floor ──────────────────────────────────────────

class TestConfidenceFloor(unittest.TestCase):
    """WO-EX-CLAIMS-02 validator 3: items below 0.5 are dropped."""

    def test_rejects_low_confidence(self):
        items = [_item("family.children.firstName", "Ghost", confidence=0.3)]
        self.assertEqual(_apply_claims_confidence_floor(items), [])

    def test_rejects_at_threshold_boundary(self):
        """Exactly 0.49 should be rejected."""
        items = [_item("family.children.firstName", "Ghost", confidence=0.49)]
        self.assertEqual(_apply_claims_confidence_floor(items), [])

    def test_keeps_at_threshold(self):
        """Exactly 0.5 should pass (not strictly less than)."""
        items = [_item("family.children.firstName", "Gretchen", confidence=0.5)]
        self.assertEqual(len(_apply_claims_confidence_floor(items)), 1)

    def test_keeps_high_confidence(self):
        items = [_item("family.children.firstName", "Gretchen", confidence=0.95)]
        self.assertEqual(len(_apply_claims_confidence_floor(items)), 1)

    def test_keeps_missing_confidence(self):
        """Items without a confidence key should pass through."""
        items = [{"fieldPath": "personal.firstName", "value": "Chris"}]
        self.assertEqual(len(_apply_claims_confidence_floor(items)), 1)

    def test_keeps_none_confidence(self):
        """Items with confidence=None should pass through."""
        items = [_item("personal.firstName", "Chris", confidence=None)]
        # confidence=None doesn't satisfy isinstance check, so it passes
        items[0]["confidence"] = None
        self.assertEqual(len(_apply_claims_confidence_floor(items)), 1)


# ── Combined validator ─────────────────────────────────────────────────────

class TestCombinedValidators(unittest.TestCase):
    """Test the combined _apply_claims_validators pipeline."""

    def test_combined_filters_stack(self):
        """A mix of good and bad items: only good ones survive."""
        items = [
            _item("family.children.firstName", "Gretchen", confidence=0.9),     # keep
            _item("family.children.relation", "then", confidence=0.7),          # killed by value-shape + relation
            _item("family.children.relation", "daughter", confidence=0.9),      # keep
            _item("family.children.relation", "and", confidence=0.7),           # killed by value-shape + relation
            _item("family.children.firstName", "Ghost", confidence=0.3),        # killed by confidence
            _item("education.higherEducation", "ok", confidence=0.8),           # killed by value-shape (short)
        ]
        # Force the flag on for this test
        os.environ["HORNELORE_CLAIMS_VALIDATORS"] = "1"
        result = _apply_claims_validators(items)
        os.environ.pop("HORNELORE_CLAIMS_VALIDATORS", None)

        values = [(r["fieldPath"], r["value"]) for r in result]
        self.assertEqual(values, [
            ("family.children.firstName", "Gretchen"),
            ("family.children.relation", "daughter"),
        ])

    def test_flag_off_skips_all(self):
        """When flag is OFF, nothing is filtered."""
        items = [
            _item("family.children.relation", "then", confidence=0.3),  # would be killed
        ]
        os.environ["HORNELORE_CLAIMS_VALIDATORS"] = "0"
        result = _apply_claims_validators(items)
        os.environ.pop("HORNELORE_CLAIMS_VALIDATORS", None)
        self.assertEqual(len(result), 1)

    def test_real_case_005_hallucinations(self):
        """Regression: the exact hallucinations from case_005 eval report."""
        items = [
            _item("family.children.relation", "then", confidence=0.7),
            _item("family.children.relation", "and", confidence=0.7),
            _item("family.children.relation", "kids", confidence=0.9),
        ]
        os.environ["HORNELORE_CLAIMS_VALIDATORS"] = "1"
        result = _apply_claims_validators(items)
        os.environ.pop("HORNELORE_CLAIMS_VALIDATORS", None)
        self.assertEqual(result, [], "All three case_005 hallucinations should be rejected")


if __name__ == "__main__":
    unittest.main()
