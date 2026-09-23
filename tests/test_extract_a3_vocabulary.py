"""WO-HORNELORE-INTEGRATED-LIFE-RECORD-01 Batch A3 — extractor vocabulary repairs.

Each test names the decision it enforces. They exercise the SHIPPED
functions (`_validate_item`, `_parse_llm_json`, `_apply_semantic_rerouter`,
`_apply_claims_value_shape`, the prompt builder) — no fixture supplies the
property being proven (docs/TESTING-DOCTRINE.md).

Run:
    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_extract_a3_vocabulary
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))
sys.path.insert(0, str(REPO / "tests"))

from fastapi_stub import install as _install_stub  # noqa: E402

# Stub ONLY when the real stack is not importable. fastapi_stub.install()
# checks sys.modules, not importability, so calling it unconditionally in
# .venv REPLACES the real fastapi/pydantic for every module loaded after this
# one in the same run. Loaded first in a multi-module run, that broke
# test_confirmation_reasons (stub BaseModel has no model_fields) and
# test_extract_api_subject_filters (stub fastapi has no FastAPI).
try:
    import fastapi  # noqa: F401
    import pydantic  # noqa: F401
except ImportError:
    _install_stub()

from api.routers import extract as X  # noqa: E402


def _item(fp, val, conf=0.9):
    return {"fieldPath": fp, "value": val, "confidence": conf}


def _parse(items):
    """Through the real parser, as the model's JSON array."""
    return X._parse_llm_json(json.dumps(items))


class D12MarriageRedirect(unittest.TestCase):
    """D12 — family.marriageDate/Place are the SAME fact as marriage.*."""

    def test_legacy_spelling_is_accepted_and_normalised(self):
        r = X._validate_item(_item("family.marriageDate", "1959-10-10"))
        self.assertEqual(r["fieldPath"], "marriage.marriageDate")
        self.assertEqual(r["value"], "1959-10-10")
        r = X._validate_item(_item("family.marriagePlace", "Fargo"))
        self.assertEqual(r["fieldPath"], "marriage.marriagePlace")

    def test_canonical_spelling_is_unchanged(self):
        r = X._validate_item(_item("marriage.marriageDate", "1959-10-10"))
        self.assertEqual(r["fieldPath"], "marriage.marriageDate")
        self.assertNotIn("_redirected_from", r)

    def test_both_spellings_in_one_response_are_one_fact(self):
        out = _parse([_item("marriage.marriageDate", "October 10, 1959"),
                      _item("family.marriageDate", "october 10, 1959.")])
        self.assertEqual([(i["fieldPath"], i["value"]) for i in out],
                         [("marriage.marriageDate", "October 10, 1959")])

    def test_redirected_first_then_canonical_is_still_one_fact(self):
        out = _parse([_item("family.marriageDate", "1959"),
                      _item("marriage.marriageDate", "1959")])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["fieldPath"], "marriage.marriageDate")

    def test_different_values_are_not_folded(self):
        # Two different dates are two claims; folding them would erase one.
        out = _parse([_item("family.marriageDate", "1956"),
                      _item("marriage.marriageDate", "1957")])
        self.assertEqual(sorted(i["value"] for i in out), ["1956", "1957"])

    def test_no_private_marker_leaks_out_of_the_parser(self):
        out = _parse([_item("family.marriageDate", "1958")])
        self.assertEqual(set(out[0]), {"fieldPath", "value", "confidence"})

    @unittest.expectedFailure
    def test_uncertainty_is_still_refused_after_the_redirect(self):
        """KNOWN PRE-EXISTING DEFECT, not caused by A3 — filed, not fixed here.

        WO-04 requirement 7 ("an unknown date is BLANK") is dead code:
        `_DATE_FIELD_SUFFIXES` is defined twice in extract.py, and the later
        camelCase frozenset (R4 Patch H) shadows the lowercase tuple that
        `_is_date_field` lower-cases against, so no date field ever matches.
        The canonical path is equally unguarded — see the companion test.
        Fixing it changes every date field in B2, so it is its own step.
        When it is fixed this test passes and the decorator must go."""
        self.assertIsNone(X._validate_item(
            _item("family.marriageDate", "exact dates unknown")))

    def test_the_redirect_is_no_weaker_than_the_canonical_path(self):
        # Whatever the date guard does, both spellings get the same answer.
        a = X._validate_item(_item("family.marriageDate", "exact dates unknown"))
        b = X._validate_item(_item("marriage.marriageDate", "exact dates unknown"))
        self.assertEqual(a is None, b is None)

    def test_the_prompt_no_longer_teaches_the_retired_spelling(self):
        system, _ = X._build_extraction_prompt_bounded(
            "We married in Fargo in 1958.", "marriage_story", "marriage.marriageDate")
        taught = X._NARRATIVE_FIELD_FEWSHOTS + system
        for gone in ('"family.marriageDate"', '"family.marriagePlace"',
                     "family.marriageDate='", "family.marriagePlace='"):
            self.assertNotIn(gone, taught, gone)
        self.assertIn('\\"marriage.marriageDate\\"'.replace("\\", ""), taught.replace("\\", ""))


class D13PetBirthDate(unittest.TestCase):
    """D13 — pets.dateOfBirth → pets.birthDate; approximate stays approximate."""

    def test_redirect_and_value_round_trips_unchanged(self):
        r = X._validate_item(_item("pets.dateOfBirth", "around 1964", 0.7))
        self.assertEqual(r["fieldPath"], "pets.birthDate")
        self.assertEqual(r["value"], "around 1964")

    def test_canonical_is_extractable(self):
        self.assertIn("pets.birthDate", X.EXTRACTABLE_FIELDS)
        self.assertEqual(X.EXTRACTABLE_FIELDS["pets.birthDate"]["repeatable"], "pets")


class A2DecidedAliasesReachTheForm(unittest.TestCase):
    """A2 — `split_destination` translates exactly the catalog's recorded
    pairs, so accept / decline / review key / suppression agree."""

    def setUp(self):
        from api.services import concept_catalog as cc
        from api.services.suggestion_review import split_destination
        self.split = split_destination
        self.pairs = {r["path"]: r["alias_of"]
                      for r in cc.load()._paths.values() if r.get("alias_of")}

    def test_every_recorded_pair_translates(self):
        self.assertEqual(len(self.pairs), 14, self.pairs)
        for ext, form in self.pairs.items():
            sec, fld = form.split(".", 1)
            got = self.split(ext)
            self.assertEqual(got[:2], (sec, fld), ext)
            # an ordinal is dropped with the translation, never honoured (C4)
            self.assertEqual(self.split(ext.replace(".", "[1].", 1))[:2], (sec, fld), ext)

    def test_an_unpaired_path_is_left_alone(self):
        # Same section family, no recorded pair: must NOT be guessed.
        self.assertEqual(self.split("family.spouse.education")[:2],
                         ("family", "spouse.education"))
        self.assertEqual(self.split("spouse.firstName")[:2], ("spouse", "firstName"))

    def test_spouse_group_marker_matches_the_repeatable_form_section(self):
        for fp, meta in X.EXTRACTABLE_FIELDS.items():
            if fp.startswith("family.spouse."):
                self.assertEqual(meta.get("repeatable"), "spouse", fp)


class D1fMiddleNames(unittest.TestCase):
    """D1f Q02 — relatives' middle / maiden names become extractable."""

    def test_new_destinations_exist_and_group_with_their_person(self):
        for fp, grp in (("family.children.middleName", "children"),
                        ("siblings.middleName", "siblings"),
                        ("siblings.maidenName", "siblings"),
                        ("grandparents.middleName", "grandparents")):
            self.assertIn(fp, X.EXTRACTABLE_FIELDS, fp)
            self.assertEqual(X.EXTRACTABLE_FIELDS[fp]["repeatable"], grp, fp)
            self.assertEqual(X._validate_item(_item(fp, "Edward"))["fieldPath"], fp)

    def test_child_middle_name_reaches_the_form_field(self):
        from api.services.suggestion_review import split_destination
        self.assertEqual(split_destination("family.children.middleName"),
                         ("children", "middleName", True))


class RetiredFromExtraction(unittest.TestCase):
    """D11 (five note buckets), D1d (the other *.notes), D1e, D3."""

    RETIRED = (
        # D11 — still questionnaire-editable; routed to story lanes, not extraction
        "faith.notes", "military.notes", "parents.notes", "pets.notes", "travel.notes",
        # D1d
        "education.notes", "hobbies.notes", "family.children.notes",
        "family.spouse.notes", "family.grandchildren.notes", "health.notes",
        "community.notes",
        # D1e
        "family.marriageNotes", "family.spouse.ageAtMarriage",
        "community.meetingDay", "community.meetingLocation",
        "community.memberCount", "community.successor",
        # D3
        "health.majorCondition", "health.currentMedications",
    )

    def test_not_offered_to_the_model(self):
        catalog = X._extraction_field_catalog()
        for p in self.RETIRED:
            self.assertNotIn(p, X.EXTRACTABLE_FIELDS, p)
            self.assertNotIn(f'"{p}"=', catalog, p)

    def test_an_item_at_a_retired_path_is_rejected(self):
        for p in self.RETIRED:
            self.assertIsNone(X._validate_item(_item(p, "some narrative colour here")), p)

    def test_no_alias_or_rerouter_writes_into_a_retired_path(self):
        # An alias to a retired target falls through to a reject by design
        # (`alias in EXTRACTABLE_FIELDS`); a REROUTER has no such check on
        # entry, so none may name one.
        items = [_item("hobbies.hobbies", "horse riding"),
                 _item("hobbies.personalChallenges", "losing my dog")]
        out = X._apply_semantic_rerouter(
            [dict(i) for i in items], "We had a dog and I loved riding my horse.",
            "childhood_pets")
        self.assertFalse([i for i in out if i["fieldPath"] in self.RETIRED], out)

    def test_catchment_whitelist_names_no_retired_path(self):
        self.assertFalse(set(self.RETIRED) & set(X._NARRATIVE_CATCHMENT_PATHS))

    def test_the_prompt_teaches_no_retired_path(self):
        system, _ = X._build_extraction_prompt_bounded(
            "I take pills for my heart and we had a dog.", "health_and_body", None)
        text = system + X._NARRATIVE_FIELD_FEWSHOTS
        for p in self.RETIRED:
            self.assertNotIn(f"{p}=", text, p)
            self.assertNotIn(f'\\"fieldPath\\":\\"{p}\\"'.replace("\\", ""),
                             text.replace("\\", ""), p)


class AncestorMilitaryNotCopiedToNarrator(unittest.TestCase):
    """_ANCESTOR_MIL_DUP_MAP removed: a great-grandparent's war stays his."""

    ANSWER = ("My great-grandfather John Michael Shong served in the Union Army, "
              "Company G of the 28th Infantry, in the Civil War. I never served myself.")

    def test_no_narrator_military_item_is_created(self):
        items = [_item("greatGrandparents.militaryBranch", "Union Army"),
                 _item("greatGrandparents.militaryUnit", "Company G of the 28th Infantry"),
                 _item("greatGrandparents.militaryEvent", "Civil War")]
        out = X._apply_semantic_rerouter([dict(i) for i in items], self.ANSWER,
                                         "family_stories_and_lore")
        self.assertEqual(sorted(i["fieldPath"] for i in out),
                         ["greatGrandparents.militaryBranch",
                          "greatGrandparents.militaryEvent",
                          "greatGrandparents.militaryUnit"])

    def test_the_prompt_sends_family_service_to_that_person(self):
        system, _ = X._build_extraction_prompt_bounded(self.ANSWER, "military_family", None)
        self.assertNotIn("military.* fields with a note that this is family history", system)
        self.assertIn("THAT person's fields", system)


class RelativeCatchAllsRemoved(unittest.TestCase):
    """An aunt or uncle is not a parent's life event."""

    def test_parent_sibling_paths_are_rejected_not_rewritten(self):
        for p in ("parents.sibling.firstName", "parents.sibling.relation",
                  "parents.siblings.firstName", "parents.siblings.birthOrder",
                  "family.relative", "family.member"):
            self.assertIsNone(X._validate_item(_item(p, "Verene")), p)

    def test_parent_schooling_goes_to_parent_education(self):
        r = X._validate_item(_item("parents.schooling", "Mount Marty in Yankton"))
        self.assertEqual(r["fieldPath"], "parents.education")


class AgeAtDeathIsBoundBeforeItExecutes(unittest.TestCase):
    """D1c: reverted in B2 (every admitted value was the narrator's age),
    reintroduced in B3(e) ONLY behind `_apply_age_at_death_guard`.

    The short-value stage admits "28" again; the binding guard at the
    finalization seam is what decides. See tests/test_extract_subject_binding.py.
    """

    def test_the_short_value_stage_admits_a_stated_age(self):
        out = X._apply_claims_value_shape([_item("parents.ageAtDeath", "28")])
        self.assertEqual([i["value"] for i in out], ["28"])

    def test_the_narrator_age_leak_28_is_still_rejected(self):
        import types
        it = types.SimpleNamespace(fieldPath="parents.ageAtDeath", value="28", confidence=0.9,
                                   repeatableGroup="parents_0", confirmation_reasons=[],
                                   normalized_from=None)
        out, entries, _ = X._apply_age_at_death_guard(
            [it], answer="Dad died December 23rd, 1967. I was twenty-eight.", clarifications=[])
        self.assertEqual((out, entries), ([], []), "a first-person age is rejected outright")

    def test_the_short_value_guard_still_applies_elsewhere(self):
        out = X._apply_claims_value_shape([_item("parents.notableLifeEvents", "ok")])
        self.assertEqual(out, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
