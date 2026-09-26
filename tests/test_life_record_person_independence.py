"""C-4F review addendum — a person is not defined by a role.

One scenario, end to end through the ONE writer, the assembled record, the
graph projection and the shipped Questionnaire V2 model:

  the narrator is one person throughout; earlier in life she was known by a
  former name, had two biological children with a woman (Anna), and later
  separated; she transitioned, now uses she/her, and is married to another
  woman (Maria). She calls her own mother "Mama".

What must hold — and what the tests pin:

  * ONE person id for the narrator, before and after; a former name is a
    name of that person, never a second person;
  * pronouns are an independent person fact (superseded, not overwritten);
  * `parent_of` records parenthood — never "father" or "mother"; `biological`
    is a relationship qualifier only; a narrator-chosen label ("Mama") is a
    label, not gender truth;
  * spouse / union participants are person ids with the role `partner`;
  * NOTHING about sex, gender identity or sexual orientation is stored,
    catalogued or derived — and the transition re-parents, duplicates or
    rewrites none of the existing relationships or occurrences.

No structured gender-identity, sexual-orientation or assigned-sex field
exists (Batch B/C design); this file also fails if one is ever catalogued.
"""
from __future__ import annotations

import json
import re
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
from api.services.life_record import writer as W  # noqa: E402
from api.services.life_record import graph_projection as G  # noqa: E402
from tests.test_life_record_writer import NORA, _Db, date  # noqa: E402

NODE = shutil.which("node")
GENDERED = re.compile(r"\b(father|mother|husband|wife|male|female|man|woman|gender|sex|orientation|"
                      r"straight|gay|lesbian|transgender|trans|maternal|paternal)\b", re.I)
IDENTITY_CONCEPT = re.compile(r"gender|sex\b|\.sex|orientation|assigned", re.I)


def rel(rid, subj, other, kind, **kw):
    v = dict({"subjectPersonId": subj, "otherPersonId": other, "kind": kind}, **kw)
    return {"op": "add", "path": f"relationships/{rid}", "value": v}


def ev(eid, kind, parts):
    return {"op": "add", "path": f"events/{eid}",
            "value": {"type": kind, "participants": [{"person": p, "role": r} for p, r in parts]}}


class OnePersonThroughATransition(_Db):

    def rows(self, sql, *args):
        con = sqlite3.connect(str(_db.DB_PATH))
        con.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in con.execute(sql, args)]
        finally:
            con.close()

    def setUp(self):
        super().setUp()
        a, pair_a = self.assertion, [(NORA, "partner"), ("p-anna", "partner")]
        # ── earlier life ────────────────────────────────────────────────
        self.ok([
            self.name(NORA, "n-old", "Robert Lund"),
            {"op": "set", "path": f"people/{NORA}/preferredNameRef", "value": "n-old", "expectedPrevious": None},
            a("pr-1", "person", NORA, "person.pronouns", "he/him"),
            {"op": "add", "path": "people/p-mama", "value": {}}, self.name("p-mama", "nm", "Ingrid Lund"),
            rel("r-mama", "p-mama", NORA, "parent_of", narratorLabel="Mama"),
            {"op": "add", "path": "people/p-anna", "value": {}}, self.name("p-anna", "na", "Anna Berg"),
            rel("r-anna", "p-anna", NORA, "spouse_of", qualifiers=["former"]),
            {"op": "add", "path": "people/c-1", "value": {}}, self.name("c-1", "nc1", "Erik Lund"),
            {"op": "add", "path": "people/c-2", "value": {}}, self.name("c-2", "nc2", "Sofie Lund"),
            rel("r-c1", NORA, "c-1", "parent_of", qualifiers=["biological"]),
            rel("r-c2", NORA, "c-2", "parent_of", qualifiers=["biological"]),
            rel("r-ac1", "p-anna", "c-1", "parent_of", qualifiers=["biological"]),
            rel("r-ac2", "p-anna", "c-2", "parent_of", qualifiers=["biological"]),
            ev("e-u1", "union", pair_a), a("d-u1", "event", "e-u1", "event.union.date", date("1970", "1970", "year")),
            ev("e-s1", "separation", pair_a),
            a("d-s1", "event", "e-s1", "event.separation.date", date("1988", "1988", "year")),
        ])
        self.before = {t: self.rows(f"SELECT * FROM {t} ORDER BY id")
                       for t in ("lr_relationships", "lr_events", "lr_event_participants")}
        old = next(n for n in self.rec()["people"] if n["id"] == NORA)["names"][0]
        old_value = {k: v for k, v in old.items() if k != "id"}
        # ── the transition: a current name, the old one kept as FORMER, she/her ──
        self.ok([
            self.name(NORA, "n-new", "Roberta Lund"),
            {"op": "set", "path": f"people/{NORA}/names/n-old", "value": dict(old_value, kind="former"),
             "expectedPrevious": old_value},
            {"op": "set", "path": f"people/{NORA}/preferredNameRef", "value": "n-new", "expectedPrevious": "n-old"},
            a("pr-2", "person", NORA, "person.pronouns", "she/her", supersedes="pr-1"),
            {"op": "set", "path": "assertions/pr-1/supersededBy", "value": "pr-2", "expectedPrevious": None},
            {"op": "set", "path": "assertions/pr-1/status", "value": "superseded", "expectedPrevious": "operator_entered"},
        ])
        # ── today: married to Maria ─────────────────────────────────────
        self.ok([
            {"op": "add", "path": "people/p-maria", "value": {}}, self.name("p-maria", "nmr", "Maria Costa"),
            rel("r-maria", "p-maria", NORA, "spouse_of"),
            ev("e-u2", "union", [(NORA, "partner"), ("p-maria", "partner")]),
            a("d-u2", "event", "e-u2", "event.union.date", date("2015", "2015", "year")),
        ])
        self.record = self.rec()

    def test_the_narrator_is_one_person_and_a_former_name_is_not_a_second(self):
        people = self.rows("SELECT id FROM lr_people ORDER BY id")
        self.assertEqual([p["id"] for p in people], sorted([NORA, "p-mama", "p-anna", "c-1", "c-2", "p-maria"]))
        me = next(p for p in self.record["people"] if p["id"] == NORA)
        self.assertEqual(sorted((n["fullText"], n["kind"]) for n in me["names"]),
                         [("Robert Lund", "former"), ("Roberta Lund", "current")])
        self.assertEqual(me["preferredNameRef"], "n-new")

    def test_pronouns_are_an_independent_person_fact_superseded_not_erased(self):
        live = self.rows("SELECT value_json FROM lr_assertions WHERE subject_id=? AND concept_id='person.pronouns' "
                         "AND status NOT IN ('superseded','rejected')", NORA)
        self.assertEqual([json.loads(r["value_json"]) for r in live], ["she/her"])
        self.assertEqual(self.rows("SELECT status FROM lr_assertions WHERE id='pr-1'")[0]["status"], "superseded")

    def test_the_transition_rewrote_no_relationship_and_no_occurrence(self):
        after = {t: [r for r in self.rows(f"SELECT * FROM {t} ORDER BY id") if r["id"] in {x["id"] for x in rows}]
                 for t, rows in self.before.items()}
        self.assertEqual(after, self.before, "children, the former spouse and both occurrences are untouched")
        kids = self.rows("SELECT subject_person_id, other_person_id, kind, qualifiers_json FROM lr_relationships "
                         "WHERE other_person_id IN ('c-1','c-2') ORDER BY id")
        self.assertEqual([(k["subject_person_id"], k["kind"], json.loads(k["qualifiers_json"])) for k in kids],
                         [("p-anna", "parent_of", ["biological"])] * 2 + [(NORA, "parent_of", ["biological"])] * 2)

    def test_union_participants_are_people_with_a_partner_role(self):
        roles = self.rows("SELECT event_id, person_id, role FROM lr_event_participants "
                          "WHERE event_id IN ('e-u1','e-s1','e-u2') ORDER BY event_id, person_id")
        self.assertEqual({r["role"] for r in roles}, {"partner"})
        self.assertEqual(len(roles), 6)

    def test_a_chosen_label_is_a_label_not_a_gender(self):
        r = self.rows("SELECT kind, narrator_label, qualifiers_json FROM lr_relationships WHERE id='r-mama'")[0]
        self.assertEqual((r["kind"], r["narrator_label"], r["qualifiers_json"]), ("parent_of", "Mama", None))

    def test_nothing_about_sex_gender_or_orientation_is_stored_or_catalogued(self):
        concepts = {r["concept_id"] for r in self.rows("SELECT DISTINCT concept_id FROM lr_assertions")}
        self.assertEqual({c for c in concepts if IDENTITY_CONCEPT.search(c)}, set())
        catalog = json.loads((REPO / "server/code/api/services/concept_catalog_v1.json").read_text("utf-8"))
        ids = {c["concept_id"] for c in catalog["concepts"]}
        self.assertEqual({c for c in ids if IDENTITY_CONCEPT.search(c)}, set(),
                         "no structured gender / sex / orientation concept exists — a deliberate design decision")
        # the assembled record carries nothing gendered beyond the chosen label
        blob = json.dumps(self.record).replace('"Mama"', '""')
        self.assertIsNone(GENDERED.search(blob), GENDERED.search(blob) and GENDERED.search(blob).group(0))

    def test_the_graph_projection_keeps_the_kinds_verbatim(self):
        proj = G.project(self.record)
        kinds = {r["relationship_type"] for r in proj["relationships"]}
        self.assertEqual(kinds, {"parent_of", "spouse_of"})
        self.assertIsNone(GENDERED.search(json.dumps(proj).replace('"Mama"', '""')))

    @unittest.skipUnless(NODE, "node is required")
    def test_the_v2_model_reads_children_as_children_and_spouses_as_spouses(self):
        script = ("const M=require(process.argv[1]);let d='';process.stdin.on('data',c=>d+=c);"
                  "process.stdin.on('end',()=>{const v=M.fromRecord(JSON.parse(d));"
                  "const roles={};Object.keys(v.relationships).forEach(k=>roles[k]=v.relationships[k].detailedRole);"
                  "process.stdout.write(JSON.stringify({roles,view:v}));});")
        out = subprocess.run([NODE, "-e", script, str(REPO / "ui/js/questionnaire-v2-model.js")],
                             input=json.dumps(self.record), capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr[-1500:])
        r = json.loads(out.stdout)
        self.assertEqual({k: r["roles"][k] for k in ("r-c1", "r-c2", "r-anna", "r-maria", "r-mama")},
                         {"r-c1": "child", "r-c2": "child", "r-anna": "spouse", "r-maria": "spouse",
                          "r-mama": "parent"})
        blob = json.dumps(r["view"]).replace('"Mama"', '""')
        self.assertIsNone(GENDERED.search(blob), GENDERED.search(blob) and GENDERED.search(blob).group(0))


if __name__ == "__main__":
    unittest.main()
