"""Batch C-3 — Questionnaire V2 edits people and relationships through the
one writer.

Drives tests/qv2_people_harness.js (jsdom + the shipped UI files), whose fake
fetch hands every Life Record request to tests/qv2_bridge.py — the shipped
writer, rules and assembler on this test's real SQLite. The UI checks are
reported by the harness; the DATABASE is checked here, because "the form
said it saved" is not "the record holds it".

What is pinned, in the database:
  * one person per person — Greta is grandparent AND caregiver with ONE id;
  * relationships stored in the right direction, with the qualifiers, label,
    period (text as said) and lineage side the operator chose — nothing else;
  * provenance as selected: the first Save was "the narrator told me", the
    second "entered by the operator"; recorded_by is always the operator;
  * a life-status change supersedes, never overwrites;
  * a former name is stored whole, and not for everyday use;
  * a stated count is a number;
  * the family graph is re-projected from the record in the same write;
  * two relatives with one name are two people;
  * exactly two writes landed; the stale tab's did not.

Skips (and says so) without node or jsdom.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))
sys.path.insert(0, str(REPO))

from api import db as _db  # noqa: E402
from tests.test_life_record_writer import NORA, OWEN, _Db  # noqa: E402

NODE = shutil.which("node")
HAVE_JSDOM = bool(NODE) and subprocess.run(
    [NODE, "-e", "require('jsdom')"], cwd=REPO, capture_output=True).returncode == 0


def run_harness(root=None):
    env = {"QV2_DB": str(_db.DB_PATH), "QV2_PY": sys.executable, "QV2_A": NORA, "QV2_B": OWEN,
           "PATH": os.environ.get("PATH", "")}
    if root:
        env["QV2_ROOT"] = str(root)
    out = subprocess.run([NODE, str(REPO / "tests" / "qv2_people_harness.js")], cwd=REPO, env=env,
                         capture_output=True, text=True, timeout=180)
    if out.returncode != 0:
        raise AssertionError(out.stderr[-2000:])
    return json.loads(out.stdout)


@unittest.skipUnless(HAVE_JSDOM, "node + jsdom are required — npm install")
class QuestionnairePeople(_Db):
    def setUp(self):
        super().setUp()
        self.ok([self.name(OWEN, "o1", "Owen Marsh")], nid=OWEN)
        self.ok([self.name(NORA, "n1", "Ines Maribel Okafor-Lund"),
                 {"op": "set", "path": f"people/{NORA}/preferredNameRef", "value": "n1", "expectedPrevious": None}])
        self.result = run_harness(os.environ.get("QV2_ROOT"))
        self.assertNotIn("error", self.result, self.result.get("error"))

    def rows(self, sql, *args):
        con = sqlite3.connect(str(_db.DB_PATH))
        try:
            return con.execute(sql, args).fetchall()
        finally:
            con.close()

    def person_named(self, text):
        r = self.rows("SELECT person_id FROM lr_names WHERE narrator_id=? AND full_text=?", NORA, text)
        self.assertEqual(len(r), 1, f"{text!r}: {r}")
        return r[0][0]

    def test_people_and_relationships_in_the_dom_and_in_the_database(self):
        failed = [c for c in self.result["checks"] if not c["ok"]]
        self.assertEqual(failed, [], "\n".join(f"{c['name']}: {c['why']}" for c in failed))
        self.assertGreaterEqual(len(self.result["checks"]), 23)

        # exactly: the setUp write, the first Save, the second Save. The
        # stale tab wrote nothing.
        self.assertEqual(self.rows("SELECT revision, actor FROM lr_revisions WHERE narrator_id=? ORDER BY revision",
                                   NORA), [(1, "operator:test"), (2, "operator"), (3, "operator")])

        people = self.rows("SELECT id FROM lr_people WHERE narrator_id=?", NORA)
        # the narrator + Astrid, Greta, Chidi, two Eriks, Tomas, Nils, Liv, Mrs. Pike — NOT the undone one
        self.assertEqual(len(people), 10, people)
        eriks = self.rows("SELECT person_id FROM lr_names WHERE narrator_id=? AND full_text='Erik Lund'", NORA)
        self.assertEqual(sorted(x[0] for x in eriks), sorted(self.result["facts"]["eriks"]),
                         "two people named Erik Lund: two rows, the ids minted in the browser")
        self.assertEqual(len({x[0] for x in eriks}), 2)
        self.assertEqual(self.rows("SELECT count(*) FROM lr_names WHERE full_text='Someone Mistaken'"), [(0,)])

        greta = self.person_named("Greta Lund")
        self.assertEqual(greta, self.result["facts"]["greta"], "the id minted in the browser is the stored id")
        rels = {r[0]: r[1:] for r in self.rows(
            "SELECT id, subject_person_id, other_person_id, kind, qualifiers_json, narrator_label, period_json "
            "FROM lr_relationships WHERE narrator_id=?", NORA)}
        by = lambda pid: sorted((v[2], v[0] == pid) for v in rels.values() if pid in v[:2])  # noqa: E731
        self.assertEqual(by(greta), [("caregiver_of", True), ("grandparent_of", True)],
                         "one Greta, two relationships, both 'Greta is … of the narrator'")

        astrid = self.person_named("Astrid M. Lund")          # renamed by the second Save
        (ra,) = [k for k, v in rels.items() if v[0] == astrid]
        self.assertEqual(rels[ra][:5], (astrid, NORA, "parent_of", '["biological"]', "Mamma"))
        self.assertEqual(json.loads(rels[ra][5]), {"start": {"text": "1950", "value": "1950", "precision": "year"}})

        nils = self.person_named("Nils Berg")
        self.assertEqual([v[:3] for v in rels.values() if nils in v[:2]], [(NORA, nils, "parent_of")],
                         "a child: the narrator is parent_of them")
        liv = self.person_named("Liv Berg")
        self.assertEqual([v[:3] for v in rels.values() if liv in v[:2]], [(NORA, liv, "grandparent_of")],
                         "a grandchild with no parent in between: one relationship, nothing inferred")
        self.assertEqual(self.rows("SELECT count(*) FROM lr_people WHERE narrator_id=?", OWEN), [(1,)],
                         "narrator B received nothing from A's draft")
        # C-3 follow-up: the old V1 draft's answer landed under the id assigned at hydration
        self.assertEqual(self.rows("SELECT id, value_json FROM lr_assertions WHERE narrator_id=? "
                                   "AND concept_id='person.birth.order'", OWEN),
                         [(self.result["facts"]["oldDraftId"], '"the eldest"')])
        tomas = self.person_named("Tomas Berg")
        (rt,) = [v for v in rels.values() if tomas in v[:2]]
        self.assertEqual(rt[2:4], ("spouse_of", '["former"]'))
        self.assertEqual(json.loads(rt[5]), {"start": {"text": "1971", "value": "1971", "precision": "year"},
                                             "end": {"text": "about 1989", "value": None, "precision": "unknown"}},
                         "a date as said: text kept, no value invented for 'about 1989'")
        pike = self.person_named("Mrs. Pike")
        self.assertEqual(self.rows("SELECT kind, described_as FROM lr_relationships WHERE subject_person_id=?", pike),
                         [("other", "the neighbour who taught her to read")])
        chidi = self.person_named("Chidi Okafor")
        self.assertEqual(self.rows("SELECT qualifiers_json FROM lr_relationships WHERE subject_person_id=?", chidi),
                         [('["half", "older"]',)])

        # provenance: first Save "the narrator told me", second "entered by the operator"
        a = self.rows("SELECT subject_type, subject_id, concept_id, value_json, source, asserted_by, recorded_by, "
                      "status, supersedes_id FROM lr_assertions WHERE narrator_id=? ORDER BY recorded_at, id", NORA)
        kinds = [x for x in a if x[2] == "relationship.kind"]
        self.assertEqual(len(kinds), len(rels), "every relationship carries who said so")
        self.assertTrue(all(x[4:7] == ("narrator_stated", "narrator", "operator") for x in kinds), kinds)
        lineage = sorted((x[1], x[3]) for x in a if x[2] == "relationship.qualifier.lineage_side")
        erik_rel = {v[0]: k for k, v in rels.items() if v[0] in self.result["facts"]["eriks"]}
        self.assertEqual(lineage, sorted([(ra, '"maternal"'),
                                          ([k for k, v in rels.items() if v[0] == greta and v[2] == "grandparent_of"][0],
                                           '"maternal"'),
                                          (erik_rel[self.result["facts"]["eriks"][0]], '"paternal"'),
                                          (erik_rel[self.result["facts"]["eriks"][1]], '"maternal"')]))
        life = [x for x in a if x[2] == "person.life_status" and x[1] == astrid]
        self.assertEqual([(x[3], x[4], x[7]) for x in life],
                         [('"deceased"', "narrator_stated", "superseded"),
                          ('"unknown"', "operator", "operator_entered")],
                         "a correction supersedes; the first account is kept")
        self.assertEqual(life[1][8], self.rows("SELECT id FROM lr_assertions WHERE subject_id=? AND "
                                                "concept_id='person.life_status' AND status='superseded'", astrid)[0][0])
        self.assertEqual([x[3] for x in a if x[2] == "person.reported_count.siblings"], ["6"], "a count is a number")
        self.assertEqual([x[3] for x in a if x[2] == "person.pronouns"], ['"she/her"'])

        # names: stored whole; a former name is not for everyday use
        self.assertEqual(self.rows("SELECT kind, use FROM lr_names WHERE person_id=? AND full_text='Ines Okafor'", NORA),
                         [("former", "historical_only")])
        self.assertEqual(self.rows("SELECT kind FROM lr_names WHERE person_id=? AND full_text='Inès Okafor-Lund'", NORA),
                         [("variant",)])
        self.assertEqual(self.rows("SELECT given_parts_json, family FROM lr_names WHERE full_text='Astrid M. Lund'"),
                         [(None, None)], "never split")

        # the family graph is the record's projection, re-made in the same writes
        gp = self.rows("SELECT id, display_name, deceased FROM graph_persons WHERE narrator_id=? AND source='life_record'", NORA)
        self.assertEqual(len(gp), 10)
        self.assertIn(("lr:" + astrid, "Astrid M. Lund", 0), gp, "life status 'unknown' is not 'deceased'")
        self.assertEqual(self.rows("SELECT count(*) FROM graph_relationships WHERE narrator_id=? AND source='life_record'",
                                   NORA), [(len(rels),)])


if __name__ == "__main__":
    unittest.main()
