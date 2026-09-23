"""B3 / A4 — subject binding.

Invariant (Chris, 2026-09-23): every extracted fact must identify the person or
entity it describes before it can become executable. A field path in the
right broad section is not enough.

The regression set is the B2/B2r cases. Values come from what the model
actually emitted; the BINDING is produced by shipped code and asserted at
`run_field_extraction` (docs/TESTING-DOCTRINE.md — a fixture may supply
values, never the property being proven).
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))
sys.path.insert(0, str(REPO / "tests"))

try:
    import fastapi  # noqa: F401
    import pydantic  # noqa: F401
except ImportError:
    from fastapi_stub import install as _install_stub
    _install_stub()
    import pydantic  # noqa: F401
_REAL_STACK = bool(getattr(pydantic, "__file__", None))

from api.routers import extract as X  # noqa: E402

_BANK = {c["id"]: c for c in json.loads(
    (REPO / "data" / "qa" / "question_bank_extraction_cases.json").read_text("utf-8"))["cases"]}
CASE_070 = _BANK["case_070"]["narratorReply"]


def _i(fp, v, c=0.9):
    return {"fieldPath": fp, "value": v, "confidence": c}


# case_070 as it reached grouping live: names first, dates after, the dates
# as the model wrote them ("4th" -- not the narrator's "4") and Amelia's
# year given by the narrator only as "'94".
CASE_070_ITEMS = [
    _i("family.children.firstName", "Vincent"), _i("family.children.firstName", "Gretchen"),
    _i("family.children.firstName", "Amelia"), _i("family.children.firstName", "Cole"),
    _i("family.children.dateOfBirth", "October 4th, 1991"),
    _i("family.children.dateOfBirth", "August 5th, 1994"),
    _i("family.children.dateOfBirth", "April 10th, 2002"),
]
EXPECTED_070 = {"Gretchen": "1991-10-04", "Amelia": "1994-08-05", "Cole": "2002-04-10"}


def _by_person(items):
    """{firstName: dateOfBirth} per repeatable group. Works on dicts or items."""
    g = lambda x, k: x[k] if isinstance(x, dict) else getattr(x, k)
    grp = lambda x: (x.get("_repeatableGroup") if isinstance(x, dict)
                     else getattr(x, "repeatableGroup", None))
    names = {grp(x): g(x, "value") for x in items if g(x, "fieldPath").endswith(".firstName")}
    return {names.get(grp(x)): g(x, "value") for x in items
            if g(x, "fieldPath").endswith(".dateOfBirth")}


class B3bEvidenceSpan(unittest.TestCase):
    """Part (b): a normalized date is located by what was said."""

    def test_r4h_keeps_what_was_said(self):
        out = X._apply_write_time_normalisation([_i("family.children.dateOfBirth", "October 4th, 1991")])
        self.assertEqual((out[0]["value"], out[0]["normalized_from"]),
                         ("1991-10-04", "October 4th, 1991"))

    def test_r4h_does_not_claim_a_change_that_did_not_happen(self):
        out = X._apply_write_time_normalisation([_i("family.children.dateOfBirth", "1991-10-04")])
        self.assertIsNone(out[0].get("normalized_from"))

    def test_case_070_each_date_on_its_own_child(self):
        items = X._apply_write_time_normalisation([dict(d) for d in CASE_070_ITEMS])
        self.assertEqual(_by_person(X._group_repeatable_items(items, CASE_070)), EXPECTED_070)

    def test_elided_year_is_found(self):
        items = X._apply_write_time_normalisation(
            [_i("family.children.firstName", "Vincent"), _i("family.children.firstName", "Amelia"),
             _i("family.children.dateOfBirth", "August 5th, 1994")])
        got = _by_person(X._group_repeatable_items(items, CASE_070))
        self.assertEqual(got, {"Amelia": "1994-08-05"})

    def test_a_locatable_value_is_located_as_before(self):
        # Nothing about names or already-findable values changes.
        items = [_i("family.children.firstName", "Vincent"), _i("family.children.firstName", "Cole"),
                 _i("family.children.placeOfBirth", "Germany")]
        grouped = X._group_repeatable_items(items, CASE_070)
        pob = [d for d in grouped if d["fieldPath"].endswith("placeOfBirth")][0]
        self.assertEqual(pob["_repeatableGroup"], "children_0")


CASE_068 = _BANK["case_068"]["narratorReply"]
CASE_073 = _BANK["case_073"]["narratorReply"]
CASE_112 = _BANK["case_112"]["narratorReply"]


def _obj(fp, v, grp=None):
    import types
    return types.SimpleNamespace(fieldPath=fp, value=v, confidence=0.9, repeatableGroup=grp,
                                 confirmation_reasons=[], normalized_from=None)


class B3cSpanSubject(unittest.TestCase):
    """Part (c): a birth/death date or place said about someone else is held."""

    def _guard(self, items, answer):
        return X._apply_subject_binding_guard(items, answer=answer, clarifications=[])

    def test_case_068_his_own_father_is_a_grandparent(self):
        # The model filed George under parents.firstName; the narrator said
        # "his own father George". The narrator's words win.
        items = [_obj("parents.firstName", "Ervin"), _obj("parents.firstName", "George"),
                 _obj("parents.deathDate", "1914"), _obj("parents.deathDate", "1967-12-23")]
        out, entries, _ = self._guard(items, CASE_068)
        self.assertEqual([(e["value"], e["resolved_subject_role"]) for e in entries],
                         [("1914", "grandparents")])
        self.assertIn("1967-12-23", [i.value for i in out], "Ervin's own death stays executable")
        self.assertEqual(entries[0]["reasons"], ["wrong_subject"])
        self.assertTrue(entries[0]["not_applied"])

    def test_case_073_my_moms_dad_is_a_grandparent(self):
        items = [_obj("grandparents.firstName", "Pete"), _obj("grandparents.birthPlace", "home")]
        out, entries, _ = self._guard(items, CASE_073)
        self.assertEqual(entries, [])
        self.assertEqual(len(out), 2)

    def test_case_112_said_once_is_said(self):
        # "Mom was born in spokane, and I was born in Spokane too."
        items = [_obj("parents.birthPlace", "spokane"), _obj("personal.placeOfBirth", "Spokane")]
        out, entries, _ = self._guard(items, CASE_112)
        self.assertEqual(entries, [], "both are true, each for its own person")

    def test_first_person_is_the_narrator(self):
        items = [_obj("parents.birthPlace", "Williston")]
        out, entries, _ = self._guard(items, "I was born in Williston.")
        self.assertEqual([e["resolved_subject_role"] for e in entries], ["narrator"])

    def test_unresolved_subject_leaves_the_item_alone(self):
        items = [_obj("parents.birthPlace", "Stanley")]
        out, entries, _ = self._guard(items, "It was a cold winter in Stanley.")
        self.assertEqual((len(out), entries), (1, []))

    def test_only_birth_and_death_dates_and_places_are_in_scope(self):
        items = [_obj("parents.occupation", "construction")]
        out, entries, _ = self._guard(items, "I worked construction all my life.")
        self.assertEqual((len(out), entries), (1, []))

    def test_never_re_homed(self):
        # decision 1: the resolved role is a PROPOSAL; no item is written to it.
        items = [_obj("parents.firstName", "Ervin"), _obj("parents.deathDate", "1914")]
        out, entries, _ = self._guard(items, CASE_068)
        self.assertFalse([i for i in out if i.fieldPath.startswith("grandparents.")])
        self.assertEqual(entries[0]["proposed_fieldPath"], "parents.deathDate")


CASE_054 = _BANK["case_054"]["narratorReply"]
CASE_090 = _BANK["case_090"]["narratorReply"]
CASE_102 = _BANK["case_102"]["narratorReply"]


class B3dPredicate(unittest.TestCase):
    """Part (d): a relative's birth/death fact needs birth/death wording."""

    def _guard(self, items, answer):
        return X._apply_predicate_binding_guard(items, answer=answer, clarifications=[])

    def test_case_102_homesteaded_is_not_born(self):
        out, entries, _ = self._guard([_obj("grandparents.birthPlace", "Ross")], CASE_102)
        self.assertEqual([(e["kind"], e["value"]) for e in entries],
                         [("predicate_unstated", "Ross")])
        self.assertEqual(entries[0]["reasons"], ["predicate_unstated"])
        self.assertTrue(entries[0]["not_applied"], "held, not dropped")

    def test_case_054_was_from_and_grew_up_are_not_born(self):
        out, entries, _ = self._guard([_obj("parents.birthPlace", "Stanley"),
                                       _obj("parents.birthPlace", "near Williston")], CASE_054)
        self.assertEqual(sorted(e["value"] for e in entries), ["Stanley", "near Williston"])

    def test_born_in_the_sentence_is_stated(self):
        out, entries, _ = self._guard([_obj("parents.birthPlace", "Stanley")],
                                      "My father was born in Stanley.")
        self.assertEqual((len(out), entries), (1, []))

    def test_a_sentence_that_points_back_borrows_the_previous_one(self):
        out, entries, _ = self._guard([_obj("parents.deathDate", "1967")],
                                      "My father died young. That was 1967.")
        self.assertEqual(entries, [])

    def test_a_sentence_that_does_not_point_back_does_not_borrow(self):
        out, entries, _ = self._guard([_obj("grandparents.birthPlace", "Ross")],
                                      "Stanley, where I was born. Ross, where my grandmother's people homesteaded.")
        self.assertEqual(len(entries), 1)

    def test_case_090_a_date_is_found_by_any_part_said(self):
        # "until 1985. Died December 1st that year." -- the death is in the
        # month-and-day sentence, the year in the one before.
        out, entries, _ = self._guard([_obj("parents.deathDate", "1985-12-01")], CASE_090)
        self.assertEqual(entries, [])

    def test_the_narrators_own_fields_are_out_of_scope(self):
        out, entries, _ = self._guard([_obj("personal.placeOfBirth", "Dodge")],
                                      "Then we moved back to Dodge.")
        self.assertEqual((len(out), entries), (1, []))


CASE_015 = _BANK["case_015"]["narratorReply"]


class B3eAgeAtDeath(unittest.TestCase):
    """Part (e): an age at death executes only when bound to the deceased."""

    def _guard(self, items, answer):
        return X._apply_age_at_death_guard(items, answer=answer, clarifications=[])

    def test_case_015_the_narrators_age_is_rejected(self):
        items = [_obj("parents.deathDate", "1967-12-23", "parents_0"),
                 _obj("parents.ageAtDeath", "28", "parents_0")]
        out, entries, _ = self._guard(items, CASE_015)
        self.assertEqual([i.fieldPath for i in out], ["parents.deathDate"])
        self.assertEqual(entries, [], "first person is REJECTED, not held")

    def test_case_068_the_narrators_age_is_rejected(self):
        items = [_obj("parents.firstName", "Ervin", "parents_0"),
                 _obj("parents.ageAtDeath", "28", "parents_0")]
        out, entries, _ = self._guard(items, CASE_068)
        self.assertNotIn("parents.ageAtDeath", [i.fieldPath for i in out])

    def test_a_bound_age_executes_said_in_words(self):
        items = [_obj("parents.relation", "father", "parents_0"),
                 _obj("parents.ageAtDeath", "72", "parents_0")]
        out, entries, _ = self._guard(items, "Dad died in 1980 at seventy-two.")
        self.assertIn(("parents.ageAtDeath", "72"), [(i.fieldPath, i.value) for i in out])

    def test_a_named_parent_binds_by_name(self):
        items = [_obj("parents.firstName", "Walter", "parents_0"),
                 _obj("parents.ageAtDeath", "64", "parents_0")]
        out, _, _ = self._guard(items, "My father Walter died at 64. Mom lived to 90.")
        self.assertIn("64", [i.value for i in out if i.fieldPath.endswith("ageAtDeath")])

    def test_the_other_parents_age_is_held(self):
        items = [_obj("parents.relation", "father", "parents_0"),
                 _obj("parents.ageAtDeath", "81", "parents_0")]
        out, entries, _ = self._guard(items, "Mom passed away at 81.")
        self.assertEqual([(e["kind"], e["value"]) for e in entries], [("age_unbound", "81")])
        self.assertTrue(entries[0]["not_applied"])

    def test_no_death_wording_is_held(self):
        items = [_obj("parents.relation", "father", "parents_0"),
                 _obj("parents.ageAtDeath", "40", "parents_0")]
        out, entries, _ = self._guard(items, "Dad was 40 when he bought the farm in Ross.")
        self.assertEqual([e["kind"] for e in entries], ["age_unbound"])


@unittest.skipUnless(_REAL_STACK, "production boundary needs real pydantic — run in .venv")
class ProductionBoundary(unittest.TestCase):
    """What run_field_extraction RETURNS. Only the network call is replaced."""

    def _run(self, answer, items, section, target):
        raw = json.dumps(items)
        req = X.ExtractFieldsRequest(answer=answer, person_id="test-narrator",
                                     current_section=section, current_target_path=target)
        with mock.patch.object(X, "_extract_via_llm",
                               side_effect=lambda *a, **k: (X._parse_llm_json(raw), raw)), \
             mock.patch.object(X, "_known_kinship_names", return_value={}):
            return X.run_field_extraction(req)

    def test_case_070_dates_bind_to_their_children_and_execute(self):
        resp = self._run(CASE_070, CASE_070_ITEMS, "family_life", "family.children.firstName")
        # Amelia's year was spoken only as "'94": value-grounding (pre-B3,
        # unchanged) holds a DERIVED year for review. The other two execute,
        # each on its own child.
        self.assertEqual(_by_person(resp.items),
                         {"Gretchen": "1991-10-04", "Cole": "2002-04-10"})
        held = [c for c in resp.clarification_required if c.get("kind") == "unsupported_value"]
        self.assertEqual([c["value"] for c in held], ["1994-08-05"])
        self.assertEqual(held[0]["repeatableGroup"],
                         [i.repeatableGroup for i in resp.items if i.value == "Amelia"][0],
                         "even the held date is bound to Amelia")
        self.assertFalse([c for c in resp.clarification_required
                          if c.get("kind") == "uncertain_date"],
                         "no conflict remains once each date is on its own child")


    def test_case_068_grandfathers_death_is_held_fathers_executes(self):
        resp = self._run(CASE_068, [
            _i("parents.firstName", "Ervin"), _i("parents.firstName", "George"),
            _i("parents.deathDate", "1914"), _i("parents.deathDate", "December 23, 1967")],
            "family_loss", "parents.deathDate")
        self.assertIn(("parents.deathDate", "1967-12-23"),
                      [(i.fieldPath, i.value) for i in resp.items])
        held = [c for c in resp.clarification_required if c.get("kind") == "wrong_subject"]
        self.assertEqual([(c["value"], c["resolved_subject_role"]) for c in held],
                         [("1914", "grandparents")])
        self.assertFalse([c for c in resp.clarification_required
                          if c.get("kind") == "uncertain_date"],
                         "bound first, so the two deaths no longer conflict")


    def test_case_102_ross_is_held_not_written(self):
        resp = self._run(CASE_102, [_i("grandparents.birthPlace", "Ross")],
                         "travel", "travel.significantTrip")
        self.assertNotIn("grandparents.birthPlace", [i.fieldPath for i in resp.items])
        self.assertEqual([c["value"] for c in resp.clarification_required
                          if c.get("kind") == "predicate_unstated"], ["Ross"])


    def test_case_015_no_narrator_age_reaches_the_parent(self):
        resp = self._run(CASE_015, [
            _i("parents.deathDate", "December 23, 1967"), _i("parents.ageAtDeath", "28")],
            "parental_care", "parents.deathDate")
        self.assertNotIn("parents.ageAtDeath", [i.fieldPath for i in resp.items])
        self.assertIn(("parents.deathDate", "1967-12-23"),
                      [(i.fieldPath, i.value) for i in resp.items])

    def test_a_bound_age_at_death_reaches_the_response(self):
        resp = self._run("My father Walter died at 64.", [
            _i("parents.firstName", "Walter"), _i("parents.ageAtDeath", "64")],
            "parental_care", "parents.deathDate")
        self.assertIn(("parents.ageAtDeath", "64"),
                      [(i.fieldPath, i.value) for i in resp.items])


if __name__ == "__main__":
    unittest.main()
