"""WO-QUESTIONNAIRE-PERSISTENCE-INTEGRITY-01 — the integrity suite.

Filed from BUG-BIO-QUESTIONNAIRE-LOSSY-ROUNDTRIP-01.

WHY THIS SUITE EXISTS AND WHY IT USES A REAL DATABASE
─────────────────────────────────────────────────────
`tests/test_questionnaire_route_fanout.py` has seven tests and mocks
`upsert_questionnaire` in every one. It can prove "the route called the
legacy writer". It cannot prove "the writer preserved the narrator's
existing data", and that is the only property that mattered on 2026-09-15
when one ordinary save deleted ten populated values from a real narrator.

So every test here writes to a real temporary SQLite file and reads the
result back out of SQLite, never through the API. A test that checks the
API against the API cannot see this class of defect at all.

THE INVARIANT UNDER TEST
    An ordinary questionnaire update may ADD or MODIFY information.
    It may not silently REMOVE information.
    Removal requires an explicitly different operation.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))


SCHEMA = """
CREATE TABLE people (id TEXT PRIMARY KEY, display_name TEXT);
CREATE TABLE bio_builder_questionnaires (
    person_id TEXT PRIMARY KEY,
    questionnaire_json TEXT NOT NULL DEFAULT '{}',
    source TEXT NOT NULL DEFAULT 'unknown',
    version INTEGER NOT NULL DEFAULT 1,
    revision INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
);
CREATE TABLE bio_builder_questionnaire_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    questionnaire_json TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'unknown',
    schema_version INTEGER NOT NULL DEFAULT 1,
    content_updated_at TEXT,
    superseded_at TEXT NOT NULL,
    superseded_by_source TEXT NOT NULL DEFAULT 'unknown',
    write_kind TEXT NOT NULL DEFAULT 'merge',
    changed_paths TEXT,
    removed_paths TEXT,
    previous_values TEXT,
    FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
);
"""

NARRATOR = "93479171-0b97-4072-bcf0-d44c7f9078ba"

# A rich narrator, shaped like the real one this bug was found on: eleven
# fields per parent, sections the minimal intake form does not render at
# all, and prose that exists nowhere else.
RICH = {
    "personal": {"fullName": "Janice Josephine Horne", "preferredName": "Janice",
                 "dateOfBirth": "1939-09-30", "placeOfBirth": "Spokane, Washington",
                 "birthOrder": "Second child", "timeOfBirth": "10:20",
                 "zodiacSign": "Libra"},
    "parents": [
        {"relation": "Mother", "firstName": "Josephine", "middleName": "Eugenia, Susanna",
         "lastName": "Zarr", "maidenName": "Schaaf", "birthDate": "1914-10-22",
         "birthPlace": "Glen Ulin, ND", "occupation": "Housewife", "deceased": "Yes",
         "notableLifeEvents": "Josie was a gifted musician. She played the organ at "
                              "silent movie theaters to make money.",
         "notes": "Daughter of Anna Schaaf (nee Gustin) and Mathias Schaaf"},
        {"relation": "Father", "firstName": "Peter", "lastName": "Zarr",
         "birthDate": "1909-09-19", "birthPlace": "Dodge, ND",
         "occupation": "Steam Boiler operator license, carpenter", "deceased": "Yes",
         "notableLifeEvents": "Pete was born at home, delivered by Mrs. Steve Dodenheffer.",
         "notes": "Siblings in order: Tillie, Peter, Steven, Joe, August, Johnny"},
    ],
    "siblings": [{"relation": "Sister", "firstName": "Verene", "lastName": "Schnieder",
                  "memories": "She was mad because her confirmation name was Gertrude"}],
    "children": [{"firstName": "Christopher", "lastName": "Horne",
                  "narrative": "Third son, born on Christmas Eve."}],
    "spouse": [{"firstName": "Kent", "lastName": "Horne", "birthDate": "1939-12-24",
                "narrative": "Married Janice on October 10, 1959."}],
    "grandparents": [{"side": "Maternal", "firstName": "Anna", "lastName": "Schaaf",
                      "maidenName": "Gustin", "ancestry": "Germans from Russia",
                      "memorableStories": "Was 50 when she had Josie."}],
    "pets": [{"name": "Grey", "species": "Horse", "notes": "Childhood horse."}],
    "familyTraditions": [{"description": "Germans from Russia heritage"}],
    "earlyMemories": {"firstMemory": "Liked to be outside. Milked cows in Dodge."},
    "technology": {"culturalPractices": "Germans from Russia through both parents."},
}

# Exactly what the minimal-intake Bio Builder form renders for `parents`:
# six of the eleven fields. This is the shape that caused the loss.
MINIMAL_PARENTS_FORM = {
    "parents": [
        {"relation": "Mother", "firstName": "Josephine", "middleName": "Eugenia, Susanna",
         "lastName": "Zarr", "maidenName": "Schaaf", "occupation": "Housewife"},
        {"relation": "Father", "firstName": "Peter", "middleName": "",
         "lastName": "Zarr", "maidenName": "", "occupation": "Steam Boiler operator license, carpenter"},
    ]
}


def _leaves(doc, prefix=""):
    out = {}
    if isinstance(doc, dict):
        for k, v in doc.items():
            out.update(_leaves(v, f"{prefix}.{k}" if prefix else k))
    elif isinstance(doc, list):
        for i, v in enumerate(doc):
            out.update(_leaves(v, f"{prefix}[{i}]"))
    else:
        if doc not in (None, "", [], {}):
            out[prefix] = doc
    return out


class QuestionnairePersistenceIntegrity(unittest.TestCase):

    def setUp(self):
        import tempfile
        self.dir = tempfile.mkdtemp(prefix="qqint-")
        self.db_path = os.path.join(self.dir, "test.sqlite3")
        con = sqlite3.connect(self.db_path)
        con.executescript(SCHEMA)
        con.execute("INSERT INTO people (id, display_name) VALUES (?,?)",
                    (NARRATOR, "Janice"))
        con.commit()
        con.close()

        from api import db as _db
        self._real_connect = _db._connect

        def _connect():
            c = sqlite3.connect(self.db_path)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys=ON")
            return c

        _db._connect = _connect
        self._db = _db

        from api.services import questionnaire_persistence as qp
        self.qp = qp
        self.qp.replace_questionnaire(NARRATOR, RICH, source="test_seed")

    def tearDown(self):
        self._db._connect = self._real_connect
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)

    # ── reading straight out of SQLite, never through the API ─────────

    def _stored(self):
        con = sqlite3.connect(self.db_path)
        row = con.execute("SELECT questionnaire_json FROM bio_builder_questionnaires "
                          "WHERE person_id=?", (NARRATOR,)).fetchone()
        con.close()
        return json.loads(row[0])

    def _revision(self):
        con = sqlite3.connect(self.db_path)
        row = con.execute("SELECT revision FROM bio_builder_questionnaires "
                          "WHERE person_id=?", (NARRATOR,)).fetchone()
        con.close()
        return row[0]

    def _history(self):
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM bio_builder_questionnaire_revisions "
            "WHERE person_id=? ORDER BY revision", (NARRATOR,))]
        con.close()
        return rows

    # ── THE REGRESSION ────────────────────────────────────────────────

    def test_the_2026_09_15_loss_cannot_happen_again(self):
        """A save from a form that renders six of eleven parent fields must
        not delete the other five. This is the exact shape that destroyed
        ten values of real family history."""
        before = _leaves(self._stored())
        self.qp.merge_whole_document(NARRATOR, MINIMAL_PARENTS_FORM,
                                     source="bio_builder_minimal_intake")
        after = _leaves(self._stored())

        lost = {k: before[k] for k in before if k not in after}
        self.assertEqual({}, lost, f"an ordinary save deleted stored values: {sorted(lost)}")

        for i, field in [(0, "notableLifeEvents"), (0, "notes"), (0, "birthDate"),
                         (0, "birthPlace"), (0, "deceased"),
                         (1, "notableLifeEvents"), (1, "notes"), (1, "birthDate"),
                         (1, "birthPlace"), (1, "deceased")]:
            self.assertTrue(self._stored()["parents"][i].get(field),
                            f"parents[{i}].{field} was deleted by an ordinary save")

    def test_sections_the_form_does_not_render_survive(self):
        """Seven sections exist that neither the minimal form nor the
        bio_facts projection knows about. A save must not notice them."""
        self.qp.merge_whole_document(NARRATOR, MINIMAL_PARENTS_FORM, source="form")
        stored = self._stored()
        for section in ("grandparents", "pets", "familyTraditions",
                        "earlyMemories", "technology", "spouse", "children"):
            self.assertIn(section, stored, f"{section} vanished")
            self.assertTrue(stored[section], f"{section} was emptied")

    def test_an_ordinary_save_still_applies_real_edits(self):
        """Preservation must not mean inertness."""
        self.qp.merge_questionnaire(
            NARRATOR, {"parents[0].occupation": "Organist and housewife"},
            source="test")
        self.assertEqual("Organist and housewife",
                         self._stored()["parents"][0]["occupation"])
        self.assertTrue(self._stored()["parents"][0]["notableLifeEvents"])

    def test_empty_string_does_not_blank_a_stored_value(self):
        """A form renders a field it has no value for and submits "". That
        is not an instruction to delete."""
        self.qp.merge_whole_document(
            NARRATOR, {"parents": [{"notes": ""}, {}]}, source="form")
        self.assertIn("Anna Schaaf", self._stored()["parents"][0]["notes"])

    # ── deletion is a different operation ─────────────────────────────

    def test_removal_requires_removals(self):
        self.qp.merge_questionnaire(NARRATOR, removals=["parents[0].notes"],
                                    source="test")
        self.assertNotIn("notes", self._stored()["parents"][0])
        self.assertTrue(self._stored()["parents"][0]["notableLifeEvents"])

    def test_removing_an_array_entry_compacts_and_leaves_the_rest(self):
        self.qp.merge_questionnaire(NARRATOR, removals=["parents[0]"], source="test")
        parents = self._stored()["parents"]
        self.assertEqual(1, len(parents))
        self.assertEqual("Peter", parents[0]["firstName"])
        self.assertTrue(parents[0]["notableLifeEvents"])

    # ── history ───────────────────────────────────────────────────────

    def test_every_write_archives_the_prior_document(self):
        self.qp.merge_questionnaire(NARRATOR, {"personal.preferredName": "Jan"},
                                    source="test_a")
        self.qp.merge_questionnaire(NARRATOR, {"personal.preferredName": "Janice"},
                                    source="test_b")
        hist = self._history()
        self.assertGreaterEqual(len(hist), 2)
        prior = json.loads(hist[-1]["questionnaire_json"])
        self.assertEqual("Jan", prior["personal"]["preferredName"])
        self.assertEqual("test_b", hist[-1]["superseded_by_source"])

    def test_history_makes_a_destructive_write_recoverable(self):
        original = self._stored()
        self.qp.reset_questionnaire(NARRATOR, source="bb_deep_reset")
        self.assertEqual({}, self._stored())
        hist = self._history()
        self.assertEqual("reset", hist[-1]["write_kind"])
        recovered = json.loads(hist[-1]["questionnaire_json"])
        self.assertEqual(_leaves(original), _leaves(recovered))

    def test_reset_is_recorded_as_a_reset_not_an_ordinary_save(self):
        """If the two are indistinguishable afterwards, history cannot say
        whether an empty record was intended."""
        self.qp.merge_questionnaire(NARRATOR, {"personal.preferredName": "Jan"},
                                    source="ui")
        self.qp.reset_questionnaire(NARRATOR, source="bb_reset_utility")
        kinds = [h["write_kind"] for h in self._history()]
        self.assertIn("merge", kinds)
        self.assertEqual("reset", kinds[-1])

    # ── concurrency ───────────────────────────────────────────────────

    def test_a_stale_write_on_the_same_path_is_refused(self):
        base = self.qp.read_for_edit(NARRATOR)
        self.qp.merge_questionnaire(NARRATOR, {"parents[0].occupation": "Organist"},
                                    source="other_client")
        with self.assertRaises(self.qp.QuestionnaireConflict) as ctx:
            self.qp.merge_questionnaire(
                NARRATOR, {"parents[0].occupation": "Homemaker"},
                source="stale_client",
                base_revision=base["revision"], base_fields=base["base_fields"])
        self.assertIn("parents[0].occupation", ctx.exception.paths)
        self.assertEqual("Organist", self._stored()["parents"][0]["occupation"])

    def test_a_disjoint_edit_rebases_rather_than_conflicting(self):
        """A newer revision alone is not a conflict — that is the whole
        reason concurrency is per-path rather than a global counter."""
        base = self.qp.read_for_edit(NARRATOR)
        self.qp.merge_questionnaire(NARRATOR, {"parents[0].occupation": "Organist"},
                                    source="other_client")
        self.qp.merge_questionnaire(
            NARRATOR, {"personal.preferredName": "Jan"}, source="disjoint_client",
            base_revision=base["revision"], base_fields=base["base_fields"])
        stored = self._stored()
        self.assertEqual("Organist", stored["parents"][0]["occupation"])
        self.assertEqual("Jan", stored["personal"]["preferredName"])

    def test_a_caller_that_cannot_prove_its_base_contests_everything(self):
        """base_fields=None with a stale revision: unprovable is not safe."""
        base_rev = self.qp.read_for_edit(NARRATOR)["revision"]
        self.qp.merge_questionnaire(NARRATOR, {"personal.preferredName": "Jan"},
                                    source="other")
        with self.assertRaises(self.qp.QuestionnaireConflict):
            self.qp.merge_questionnaire(NARRATOR, {"parents[0].occupation": "X"},
                                        source="blind", base_revision=base_rev)

    def test_revision_advances_only_on_a_real_write(self):
        r0 = self._revision()
        self.qp.merge_questionnaire(NARRATOR, {"personal.preferredName": "Janice"},
                                    source="noop")
        self.assertEqual(r0, self._revision(), "a no-op write advanced the revision")
        self.qp.merge_questionnaire(NARRATOR, {"personal.preferredName": "Jan"},
                                    source="real")
        self.assertEqual(r0 + 1, self._revision())

    # ── the read path a caller must use ───────────────────────────────

    def test_read_for_edit_returns_the_stored_document_not_a_projection(self):
        """A caller hydrating from bio_questionnaire_view would receive nine
        sections and, writing back what it received, delete seven."""
        got = self.qp.read_for_edit(NARRATOR)["questionnaire"]
        self.assertEqual(set(RICH.keys()), set(got.keys()))


    def test_history_names_the_write_that_removed_a_path(self):
        """The forensic question this incident actually posed:
        'where did Josie\'s notableLifeEvents go?' must be a query."""
        self.qp.merge_questionnaire(
            NARRATOR, removals=["parents[0].notableLifeEvents"],
            source="whoever_did_it")
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT superseded_by_source, removed_paths, previous_values "
            "FROM bio_builder_questionnaire_revisions "
            "WHERE person_id=? AND removed_paths LIKE ? "
            "ORDER BY revision DESC LIMIT 1",
            (NARRATOR, "%parents[0].notableLifeEvents%")).fetchone()
        con.close()
        self.assertIsNotNone(row, "history cannot answer who removed the path")
        self.assertEqual("whoever_did_it", row["superseded_by_source"])
        self.assertIn("parents[0].notableLifeEvents", json.loads(row["removed_paths"]))
        self.assertIn("gifted musician",
                      json.loads(row["previous_values"])["parents[0].notableLifeEvents"])

    def test_an_intentional_blank_is_reported_even_though_it_is_not_applied(self):
        """Clearing a field must not silently do nothing. The write is
        unchanged; the caller is told, so it can ask and then send a real
        removal."""
        res = self.qp.merge_whole_document(
            NARRATOR, {"parents": [{"occupation": ""}, {}]}, source="form")
        self.assertIn("parents[0].occupation", res["ignored_blank_paths"])
        self.assertEqual("Housewife", self._stored()["parents"][0]["occupation"])

    def test_a_blank_over_nothing_stored_is_not_reported(self):
        """Every empty box on a form would otherwise be noise."""
        res = self.qp.merge_whole_document(
            NARRATOR, {"laterYears": {"retirement": ""}}, source="form")
        self.assertEqual([], res["ignored_blank_paths"])

    def test_the_two_sides_of_clearing_a_field(self):
        """The contract in one test, both halves side by side.

        A legacy whole-document client sending "" over a populated value
        must NOT delete it, and must be told so — otherwise it can
        truthfully report the operation as fully saved when it was not.
        An explicit removal must actually remove it AND leave the
        forensic record. Same field, same suite, opposite outcomes."""
        # ── side one: a blank from a whole-document client ────────────
        res = self.qp.merge_whole_document(
            NARRATOR, {"parents": [{"notableLifeEvents": ""}, {}]}, source="legacy_form")
        self.assertIn("parents[0].notableLifeEvents", res["ignored_blank_paths"])
        self.assertIn("gifted musician",
                      self._stored()["parents"][0]["notableLifeEvents"])

        # ── side two: an explicit removal of the very same path ───────
        res2 = self.qp.merge_questionnaire(
            NARRATOR, removals=["parents[0].notableLifeEvents"],
            source="operator_meant_it")
        self.assertEqual([], res2["ignored_blank_paths"])
        self.assertNotIn("notableLifeEvents", self._stored()["parents"][0])

        # ...and the removal is recoverable from history, by path.
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT superseded_by_source, removed_paths, previous_values "
            "FROM bio_builder_questionnaire_revisions "
            "WHERE person_id=? AND removed_paths LIKE ? ORDER BY revision DESC LIMIT 1",
            (NARRATOR, "%parents[0].notableLifeEvents%")).fetchone()
        con.close()
        self.assertEqual("operator_meant_it", row["superseded_by_source"])
        self.assertIn("gifted musician",
                      json.loads(row["previous_values"])["parents[0].notableLifeEvents"])

        # Everything else on that parent is untouched by either half.
        self.assertTrue(self._stored()["parents"][0]["notes"])
        self.assertEqual("1914-10-22", self._stored()["parents"][0]["birthDate"])

    def test_an_unsafe_whole_document_replace_is_refused_at_the_db_primitive(self):
        """The old primitive must not remain conveniently callable."""
        from api import db as _dbmod
        with self.assertRaises(RuntimeError) as ctx:
            _dbmod.upsert_questionnaire(NARRATOR, {"personal": {}}, source="new_feature")
        self.assertIn("refused by default", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
