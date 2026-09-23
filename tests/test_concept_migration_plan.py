"""WO-HORNELORE-INTEGRATED-LIFE-RECORD-01 Batch A5 — the migration plan.

The plan must account for EVERY leaf of a legacy document exactly once, and
must never lose a value: a retired path keeps its value in the ledger, an
unknown key is kept for review, a derived field is recognised as derived.

BOUNDARIES (docs/TESTING-DOCTRINE.md). The plan runs against the REAL compiled
catalog, not a fixture catalog. The fixture document's SHAPE — which sections
are repeatable lists and which are single objects — is read from the shipped
`questionnaire_schema`, not assumed, so this cannot pass against a document
the product would never store. The values are fictional.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_concept_migration_plan
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "server", "code"))

from api.services import concept_migration_plan as mp  # noqa: E402
from api.services import questionnaire_schema as qs  # noqa: E402


def _section(sid, *entries):
    """Shape a section exactly as the product stores it: a list of entries for
    a repeatable section, a single object otherwise (read from the schema)."""
    if qs.is_repeatable(sid):
        return list(entries)
    assert len(entries) == 1, f"{sid} is not repeatable in the shipped schema"
    return entries[0]


# Fictional throughout.
QUESTIONNAIRE = {
    "personal": _section("personal", {
        "fullName": "Mireia Vasquez", "dateOfBirth": "around 1941",
        "placeOfBirth": "Girona", "zodiacSign": "Pisces",
        "favouriteColour": "green",                    # a key nothing binds
        "birthOrder": "",                              # empty
    }),
    "parents": _section("parents",
        {"_entryId": "p_mother", "relation": "Mother", "firstName": "Alba",
         "deceased": "Yes", "notes": "sang in the choir"},
        {"_entryId": "p_father", "relation": "Father", "firstName": "Tomas",
         "deceased": "", "occupation": "Boatwright"},
    ),
    "siblings": _section("siblings",
        {"_entryId": "s1", "firstName": "Pere", "notes": "a note an operator typed"},
    ),
    "_legacyRemovedSections": {"oldThing": "x"},
}

PROFILE = {
    "basics": {"dob": "1941-03-02", "dateOfBirth": "1941-03-02", "pob": "Girona",
               "fullname": "Mireia Vasquez", "location": "Barcelona"},
    "kinship": [{"name": "Tomas Vasquez", "relation": "Father", "deceased": True}],
    "pets": [{"name": "Nit", "species": "cat"}],
}


def _rows(result, path):
    return [r for r in result["rows"] if r["source_path"] == path]


class MigrationPlan(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.q = mp.plan(questionnaire=QUESTIONNAIRE)
        cls.p = mp.plan(profile=PROFILE)
        cls.both = mp.plan(questionnaire=QUESTIONNAIRE, profile=PROFILE)

    def test_every_leaf_is_accounted_for_exactly_once(self):
        for res in (self.q, self.p, self.both):
            self.assertTrue(res["reconciled"],
                            f"{res['leaves']} leaves but {len(res['rows'])} rows")
            self.assertEqual(sum(res["summary"].values()), len(res["rows"]))

    def test_no_nonempty_value_is_dropped(self):
        kept = {repr(r["value"]) for r in self.both["rows"]}
        for v in ("sang in the choir", "a note an operator typed", "green",
                  "Barcelona", "Pisces", "around 1941"):
            self.assertIn(repr(v), kept, f"{v!r} vanished from the plan")

    def test_a_retired_path_keeps_its_value(self):
        r = _rows(self.q, "siblings.notes")[0]
        self.assertEqual(r["disposition"], "retired_value_kept")
        self.assertEqual(r["value"], "a note an operator typed")
        self.assertEqual(r["decision_ids"], ["D1f"])

    def test_an_undecided_notes_bucket_is_mapped_not_retired(self):
        r = _rows(self.q, "parents.notes")[0]
        self.assertEqual(r["disposition"], "mapped")
        self.assertEqual(r["concept_id"], "note.about_subject")

    def test_derived_zodiac_is_not_migrated_as_truth(self):
        r = _rows(self.q, "personal.zodiacSign")[0]
        self.assertEqual(r["disposition"], "derived_not_migrated")

    def test_an_unknown_key_is_kept_for_review(self):
        r = _rows(self.q, "personal.favouriteColour")[0]
        self.assertEqual(r["disposition"], "unmapped_value_kept")
        self.assertEqual(r["value"], "green")

    def test_repeatable_rows_carry_entry_id_and_subject(self):
        alba = [r for r in _rows(self.q, "parents.firstName") if r["value"] == "Alba"][0]
        self.assertEqual((alba["entry_id"], alba["subject"], alba["concept_id"]),
                         ("p_mother", "parent", "person.name.given"))

    def test_life_status_is_flagged_for_three_state_normalisation(self):
        yes = [r for r in _rows(self.q, "parents.deceased") if r["value"] == "Yes"][0]
        self.assertEqual(yes["concept_id"], "person.life_status")
        self.assertIn("blank is NOT 'living'", yes["note"])
        blank = [r for r in _rows(self.q, "parents.deceased") if r["entry_id"] == "p_father"][0]
        self.assertEqual(blank["disposition"], "empty",
                         "an unanswered deceased field must not become 'explicitly living'")

    def test_bookkeeping_is_counted_not_migrated(self):
        self.assertEqual(_rows(self.q, "_legacyRemovedSections")[0]["disposition"], "bookkeeping")
        self.assertTrue(any(r["disposition"] == "bookkeeping" and r["source_path"].endswith("._entryId")
                            for r in self.q["rows"]))

    def test_profile_spellings_converge_on_one_concept(self):
        concepts = {r["concept_id"] for r in self.p["rows"]
                    if r["source_path"] in ("basics.dob", "basics.dateOfBirth")}
        self.assertEqual(concepts, {"person.birth.date"})

    def test_profile_ambiguous_key_is_not_guessed(self):
        r = _rows(self.p, "basics.location")[0]
        self.assertEqual(r["disposition"], "unmapped_value_kept")

    def test_kinship_subject_comes_from_the_entry(self):
        r = _rows(self.p, "kinship.deceased")[0]
        self.assertEqual((r["subject"], r["subject_detail"], r["concept_id"]),
                         ("by_relation", "Father", "person.life_status"))


if __name__ == "__main__":
    unittest.main()
