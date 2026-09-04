"""Value grounding — a value nobody said must not execute.

WO-LORI-ARCHIVE-TO-MEMOIR-02 Phase 3 (2026-09-04).

THE CASE. Mable said: "Otis died in 2005. Heart attack at sixty-three." The
extractor proposed `parents.birthDate="1922"` at 0.7. 2005 − 63 is 1942; 1922
appears nowhere in her words and is not derivable from them. That is a
FABRICATED value — a different defect from a mis-bound one. The kinship guard
stops it reaching the profile today, but containment is not grounding: an
operator rebinding that group later would carry the invented year with it.

GROUNDING IS PER VALUE, NOT PER GROUP. In that same quarantine `Otis`, `2005`
and `died 2005` were all spoken; only `1922` was not. Marking the whole group
unsupported would erase exactly the distinction an operator needs.

Every test starts from NARRATOR TEXT and runs `run_field_extraction`, per
docs/TESTING-DOCTRINE.md — a test that declared a value grounded would be the
tenth instance of the failure that document exists to stop.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "server" / "code") not in sys.path:
    sys.path.insert(0, str(ROOT / "server" / "code"))

from api.routers import extract as EX  # noqa: E402

MABLE = "Otis died in 2005. Heart attack at sixty-three."
MABLE_PROFILE = {"profile_json": {"spouses": [{"firstName": "Otis"}],
                                  "parents": [{"firstName": "Clarence"}]}}


def item(fp, value, conf=0.9):
    return {"fieldPath": fp, "value": value, "confidence": conf}


def run(answer, items, profile=None, force_rules=False):
    req = EX.ExtractFieldsRequest(person_id="n", answer=answer,
                                  current_section="family_life")
    llm = ([], "[stub]") if force_rules else (list(items), "[stub]")
    with mock.patch("api.db.get_profile", return_value=profile), \
         mock.patch.object(EX, "_extract_via_llm", return_value=llm), \
         mock.patch.object(EX, "_extract_via_rules", return_value=list(items)):
        return EX.run_field_extraction(req)


def exec_paths(r):
    return [(i.fieldPath, i.value) for i in r.items]


def proposed(r):
    out = []
    for c in r.clarification_required:
        out.extend(c.get("proposed_items") or [])
    return out


def grounding_of(r, field_path):
    for p in proposed(r):
        if p.get("fieldPath") == field_path:
            return p.get("grounding")
    return None


class TheFabricatedYear(unittest.TestCase):
    """Requirements 1 and 2, driven by the real narration."""

    ITEMS = [item("parents.firstName", "Otis"),
             item("parents.birthDate", "1922", 0.7),
             item("parents.deathDate", "2005"),
             item("parents.notableLifeEvents", "died 2005", 0.8)]

    def test_1922_never_executes(self):
        r = run(MABLE, self.ITEMS, MABLE_PROFILE)
        self.assertNotIn("1922", [v for _, v in exec_paths(r)])

    def test_1922_is_preserved_as_review_evidence(self):
        r = run(MABLE, self.ITEMS, MABLE_PROFILE)
        self.assertIn("1922", [str(p.get("value")) for p in proposed(r)])

    def test_value_unsupported_attaches_to_1922_specifically(self):
        r = run(MABLE, self.ITEMS, MABLE_PROFILE)
        self.assertEqual("unsupported", grounding_of(r, "parents.birthDate"))

    def test_the_spoken_values_do_NOT_inherit_it(self):
        """Requirement 2. They share a quarantined kinship group; that says
        nothing about whether the narrator said them."""
        r = run(MABLE, self.ITEMS, MABLE_PROFILE)
        self.assertEqual("spoken", grounding_of(r, "parents.firstName"))
        self.assertEqual("spoken", grounding_of(r, "parents.deathDate"))
        self.assertEqual("not_checked",
                         grounding_of(r, "parents.notableLifeEvents"),
                         "a narrative field may summarise and must not be "
                         "held to literal wording")

    def test_the_detail_names_what_was_actually_spoken(self):
        r = run(MABLE, self.ITEMS, MABLE_PROFILE)
        for p in proposed(r):
            if p["fieldPath"] == "parents.birthDate":
                self.assertEqual([2005], p["grounding_detail"]["spoken_years"])


class SupportedRelationshipOneBadValue(unittest.TestCase):
    """Requirement 7: quarantine the VALUE, not the group."""

    ANSWER = "My father Otis died in 2005. Heart attack at sixty-three."

    def test_only_the_ungrounded_value_is_withheld(self):
        r = run(self.ANSWER,
                [item("parents.firstName", "Otis"),
                 item("parents.deathDate", "2005"),
                 item("parents.birthDate", "1922", 0.7)], None)
        paths = [fp for fp, _ in exec_paths(r)]
        self.assertIn("parents.firstName", paths)
        self.assertIn("parents.deathDate", paths)
        self.assertNotIn("parents.birthDate", paths)

    def test_it_produces_one_value_scoped_entry(self):
        r = run(self.ANSWER,
                [item("parents.firstName", "Otis"),
                 item("parents.birthDate", "1922", 0.7)], None)
        kinds = [c["kind"] for c in r.clarification_required]
        self.assertEqual(["unsupported_value"], kinds)
        self.assertIn("value_unsupported",
                      r.clarification_required[0]["reasons"])

    def test_a_quarantined_group_does_not_get_a_duplicate_prompt(self):
        """Requirement 6: merge into the existing entry rather than raising a
        second prompt for the same value."""
        r = run(MABLE, [item("parents.firstName", "Otis"),
                        item("parents.birthDate", "1922", 0.7)], MABLE_PROFILE)
        self.assertEqual(1, len(r.clarification_required))
        self.assertEqual("unbound_relationship",
                         r.clarification_required[0]["kind"])
        self.assertEqual("unsupported", grounding_of(r, "parents.birthDate"))


class SpokenAndNormalized(unittest.TestCase):
    """Requirements 3 and 4 — grounding must not block honest values."""

    def test_a_spoken_year_executes(self):
        r = run("My father Otis was born in 1922.",
                [item("parents.firstName", "Otis"),
                 item("parents.birthDate", "1922")], None)
        self.assertIn(("parents.birthDate", "1922"), exec_paths(r))

    def test_a_normalized_natural_language_date_executes(self):
        """'December 24, 1962' -> '1962-12-24' is normalisation, not
        fabrication. The shipped _normalize_date_value produces that form."""
        self.assertEqual("1962-12-24",
                         EX._normalize_date_value("December 24, 1962"))
        r = run("My father Kent was born on December 24, 1962.",
                [item("parents.firstName", "Kent"),
                 item("parents.birthDate", "1962-12-24")], None)
        self.assertIn(("parents.birthDate", "1962-12-24"), exec_paths(r))

    def test_a_spoken_name_executes(self):
        r = run("My father Otis worked at the plant.",
                [item("parents.firstName", "Otis")], None)
        self.assertEqual([("parents.firstName", "Otis")], exec_paths(r))

    def test_a_name_the_narrator_never_said_is_unsupported(self):
        r = run("My father worked at the plant for thirty years.",
                [item("parents.firstName", "Ida")], None)
        self.assertEqual([], exec_paths(r))


class DerivedIsNotSpoken(unittest.TestCase):
    """Requirement 5. 2005 − 63 = 1942 is reproducible from what she said;
    that is not the same as her having said it."""

    ANSWER = "My father Otis died in 2005. Heart attack at sixty-three."

    def test_a_derived_year_is_recorded_with_its_rule_and_operands(self):
        r = run(self.ANSWER, [item("parents.firstName", "Otis"),
                              item("parents.birthDate", "1942", 0.7)], None)
        self.assertNotIn("1942", [v for _, v in exec_paths(r)],
                         "an inferred date must not get the authority of "
                         "narrator wording")
        p = [q for q in proposed(r) if q["fieldPath"] == "parents.birthDate"][0]
        self.assertEqual("derived", p["grounding"])
        d = p["grounding_detail"]
        self.assertEqual("anchor_year_minus_age", d["rule"])
        self.assertEqual({"anchor_year": 2005, "age": 63}, d["operands"])

    def test_derived_and_unsupported_are_different_verdicts(self):
        """1942 is derivable; 1922 is not. If these collapsed, the operator
        could not tell a computation from an invention."""
        der = run(self.ANSWER, [item("parents.firstName", "Otis"),
                                item("parents.birthDate", "1942", 0.7)], None)
        unk = run(self.ANSWER, [item("parents.firstName", "Otis"),
                                item("parents.birthDate", "1922", 0.7)], None)
        self.assertEqual("derived", grounding_of(der, "parents.birthDate"))
        self.assertEqual("unsupported", grounding_of(unk, "parents.birthDate"))

    def test_a_spoken_age_in_words_is_read(self):
        self.assertIn(63, EX._numbers_spoken("Heart attack at sixty-three."))
        self.assertIn(2005, EX._numbers_spoken("He died in 2005."))


class BothPaths(unittest.TestCase):

    def test_the_rules_fallback_path_grounds_too(self):
        r = run("My father Otis died in 2005.",
                [item("parents.firstName", "Otis"),
                 item("parents.birthDate", "1922", 0.7)], None, force_rules=True)
        self.assertEqual("rules_fallback", r.method)
        self.assertNotIn("1922", [v for _, v in exec_paths(r)])
        self.assertEqual("unsupported", grounding_of(r, "parents.birthDate"))


class PreservedNotMissing(unittest.TestCase):
    """The evaluator must class the withheld value as preserved."""

    def test_preservation_accounting_sees_it(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "qb_eval", ROOT / "scripts" / "archive"
            / "run_question_bank_extraction_eval.py")
        QB = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(QB)

        r = run(MABLE, [item("parents.firstName", "Otis"),
                        item("parents.birthDate", "1922", 0.7)], MABLE_PROFILE)
        case = {"id": "synthetic_grounding", "truthZones": {
            "parents.birthDate": {"zone": "must_extract", "expected": "1922"}}}
        acc = QB.preservation_accounting(
            case, [i.model_dump() for i in r.items],
            list(r.clarification_required))
        self.assertEqual("preserved_for_review",
                         acc["fates"]["parents.birthDate=1922"],
                         "a withheld value must not be reported as missing")


if __name__ == "__main__":
    unittest.main()
