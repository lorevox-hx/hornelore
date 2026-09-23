"""B2 repair — a date the narrator was not sure of is held for review.

Found by the B2 gate (2026-09-23), case_061:

    "We got married at St. Mary's church. I think it was 1956, maybe 1957.
     I'm not sure of the exact year anymore."

Before A3 both dates were rejected -- by accident, the model's
`family.marriageDate` spelling was invalid. D12 redirects that spelling, and
both became executable `marriage.marriageDate` facts. The scorer could not see
it: the case has no must_not_write on the date.

Invariant (approved, bounded):
  * a date whose source sentence the narrator hedged -> review,
    reason `narrator_uncertain` -- preserved, not discarded;
  * two different values for one date field of one entity in one turn ->
    neither is authoritative, both -> review, reason `conflicting_values`;
  * a value carrying its own approximation ("around 1964") stays as stated.

Two layers, per docs/TESTING-DOCTRINE.md: helper tests pin each rule, and the
production-boundary class asserts on what `run_field_extraction` RETURNS --
starting from the retired spelling the model actually emitted in B2, so the
D12 redirect is part of the path under test.
"""
from __future__ import annotations

import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))
sys.path.insert(0, str(REPO / "tests"))

# Stub ONLY when the real stack is absent (see test_extract_a3_vocabulary).
try:
    import fastapi  # noqa: F401
    import pydantic  # noqa: F401
except ImportError:
    from fastapi_stub import install as _install_stub
    _install_stub()
    import pydantic  # noqa: F401  (the stub)
# A stub is a bare ModuleType with no file. Checked AFTER import, because an
# earlier module in the same run may already have installed the stub.
_REAL_STACK = bool(getattr(pydantic, "__file__", None))

from api.routers import extract as X  # noqa: E402

CASE_061 = ("We got married at St. Mary's church. I think it was 1956, maybe 1957. "
            "I'm not sure of the exact year anymore.")


def _it(fp, value, group=None, conf=0.9, reasons=None):
    return types.SimpleNamespace(fieldPath=fp, value=value, confidence=conf,
                                 repeatableGroup=group,
                                 confirmation_reasons=list(reasons or []))


def _guard(items, answer, clarifications=None):
    return X._apply_date_uncertainty_guard(items, answer=answer,
                                           clarifications=clarifications or [])


class HeldForReview(unittest.TestCase):

    def test_case_061_neither_uncertain_date_is_executable(self):
        items = [_it("marriage.marriageDate", "1956", "marriage_0"),
                 _it("marriage.marriageDate", "1957", "marriage_0"),
                 _it("marriage.marriagePlace", "St. Mary's church", "marriage_0")]
        out, entries, _ = _guard(items, CASE_061)
        self.assertEqual([i.fieldPath for i in out], ["marriage.marriagePlace"],
                         "the place was said with certainty and stays executable")
        self.assertEqual(sorted(e["value"] for e in entries), ["1956", "1957"])
        for e in entries:
            self.assertIn("conflicting_values", e["reasons"])
            self.assertIn("narrator_uncertain", e["reasons"])
            self.assertTrue(e["not_applied"])
            # PRESERVED, not dropped: the operator sees the value to decide.
            self.assertEqual(e["proposed_items"][0]["value"], e["value"])
            self.assertEqual(e["proposed_fieldPath"], "marriage.marriageDate")

    def test_one_hedged_date_is_held_as_narrator_uncertain(self):
        out, entries, _ = _guard([_it("marriage.marriageDate", "1956", "marriage_0")],
                                 "I think we got married in 1956.")
        self.assertEqual(out, [])
        self.assertEqual(entries[0]["reasons"], ["narrator_uncertain"])

    def test_a_normalized_date_is_traced_to_its_sentence(self):
        # R4-H normalizes before this guard; the year still finds the sentence.
        out, entries, _ = _guard(
            [_it("marriage.marriageDate", "1959-10-10", "marriage_0")],
            "Maybe it was October 10, 1959. It was a long time ago.")
        self.assertEqual(out, [])
        self.assertEqual(len(entries), 1)

    def test_two_values_for_one_entity_conflict(self):
        # B2 case_070: two children's birth dates grouped onto one child.
        items = [_it("family.children.dateOfBirth", "1991-10-04", "children_3"),
                 _it("family.children.dateOfBirth", "2002-04-10", "children_3")]
        out, entries, _ = _guard(items, "Gretchen was born October 4, 1991. "
                                        "Cole was born April 10, 2002.")
        self.assertEqual(out, [])
        self.assertTrue(all(e["reasons"] == ["conflicting_values"] for e in entries))


class StaysExecutable(unittest.TestCase):

    def test_a_confident_date_is_untouched(self):
        items = [_it("marriage.marriageDate", "1959-10-10", "marriage_0")]
        out, entries, _ = _guard(items, "We got married October 10, 1959.")
        self.assertEqual(out, items)
        self.assertEqual(entries, [])

    def test_a_value_carrying_its_own_approximation_is_true_as_stated(self):
        items = [_it("pets.birthDate", "around 1964", "pets_0")]
        out, entries, _ = _guard(items, "Born around 1964 I think.")
        self.assertEqual(out, items, "'around 1964' is not converted or held")
        self.assertEqual(entries, [])

    def test_different_entities_are_not_a_conflict(self):
        items = [_it("family.children.dateOfBirth", "1991-10-04", "children_1"),
                 _it("family.children.dateOfBirth", "2002-04-10", "children_3")]
        out, entries, _ = _guard(items, "Gretchen was born October 4, 1991. "
                                        "Cole was born April 10, 2002.")
        self.assertEqual(out, items)
        self.assertEqual(entries, [])

    def test_the_same_value_twice_is_not_a_conflict(self):
        items = [_it("marriage.marriageDate", "1959-10-10", "marriage_0"),
                 _it("marriage.marriageDate", "1959-10-10 ", "marriage_0")]
        out, _, _ = _guard(items, "We got married October 10, 1959.")
        self.assertEqual(len(out), 2)

    def test_thinking_about_a_date_is_not_doubting_it(self):
        items = [_it("marriage.marriageDate", "1959-10-10", "marriage_0")]
        out, _, _ = _guard(items, "I think about October 10, 1959 every year.")
        self.assertEqual(out, items)

    def test_only_date_fields_are_in_scope(self):
        items = [_it("parents.firstName", "Pete", "parents_0")]
        out, entries, _ = _guard(items, "I think his name was Pete.")
        self.assertEqual(out, items, "names are not this repair's business")
        self.assertEqual(entries, [])


class EnvelopeHygiene(unittest.TestCase):

    def test_a_held_items_clarification_is_not_left_behind(self):
        clar = [{"fieldPath": "marriage.marriageDate", "value": "1956", "reason": "fragile_field"},
                {"fieldPath": "marriage.marriagePlace", "value": "St. Mary's", "reason": "fragile_field"}]
        items = [_it("marriage.marriageDate", "1956", "marriage_0", reasons=["fragile_field"])]
        _, entries, kept = _guard(items, "I think it was 1956.", clar)
        self.assertEqual([c["fieldPath"] for c in kept], ["marriage.marriagePlace"])
        self.assertIn("fragile_field", entries[0]["reasons"], "earlier doubt travels with it")


@unittest.skipUnless(_REAL_STACK, "production boundary needs real pydantic — run in .venv")
class ProductionBoundary(unittest.TestCase):
    """What run_field_extraction RETURNS, from the model's B2 output."""

    def _run(self, answer, items, section="marriage", target="marriage.marriageDate"):
        """Only the network call is replaced. The model's RAW text goes through
        the shipped `_parse_llm_json` -- validation, the D12 redirect and the
        same-fact fold -- exactly as production does."""
        raw = json.dumps(items)
        req = X.ExtractFieldsRequest(answer=answer, person_id="test-narrator",
                                     current_section=section, current_target_path=target)
        with mock.patch.object(X, "_extract_via_llm",
                               side_effect=lambda *a, **k: (X._parse_llm_json(raw), raw)), \
             mock.patch.object(X, "_known_kinship_names", return_value={}):
            return X.run_field_extraction(req)

    def test_case_061_as_the_model_emitted_it(self):
        # The retired spelling, exactly as B2's model wrote it: D12 redirects
        # it, and the guard must still hold both.
        resp = self._run(CASE_061, [
            {"fieldPath": "family.marriageDate", "value": "1956", "confidence": 0.7},
            {"fieldPath": "family.marriageDate", "value": "1957", "confidence": 0.7}])
        self.assertEqual([i for i in resp.items if i.fieldPath.endswith("marriageDate")], [],
                         "no uncertain marriage date may be executable")
        held = [c for c in resp.clarification_required if c.get("kind") == "uncertain_date"]
        self.assertEqual(sorted(c["value"] for c in held), ["1956", "1957"])
        self.assertTrue(all("narrator_uncertain" in c["reasons"] for c in held))

    def test_a_confident_date_still_executes(self):
        resp = self._run("We got married October 10, 1959.",
                         [{"fieldPath": "family.marriageDate", "value": "October 10, 1959",
                           "confidence": 0.9}])
        self.assertEqual([(i.fieldPath, i.value) for i in resp.items],
                         [("marriage.marriageDate", "1959-10-10")])
        self.assertFalse([c for c in resp.clarification_required
                          if c.get("kind") == "uncertain_date"])

    def test_around_1964_executes_as_stated(self):
        resp = self._run("We had a Golden Retriever named Ivan. Born around 1964 I think.",
                         [{"fieldPath": "pets.birthDate", "value": "around 1964", "confidence": 0.7}],
                         section="childhood_pets", target="pets.name")
        self.assertIn(("pets.birthDate", "around 1964"),
                      [(i.fieldPath, i.value) for i in resp.items])


if __name__ == "__main__":
    unittest.main()
