"""Batch C-4E — birth, death and places, through the shipped Questionnaire V2
editor and the one Life Record writer.

The DOM half (tests/qv2_vital_harness.js) drives the real controls against the
real writer; this file prepares the SQLite record, reads the harness's checks,
and then checks the DATABASE — what the Save actually wrote. A second class
exercises the writer directly for the atomicity and duplication rules.
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
from tests.test_life_record_writer import NORA, _Db, date  # noqa: E402

NODE = shutil.which("node")
HAVE_JSDOM = bool(NODE) and subprocess.run(
    [NODE, "-e", "require('jsdom')"], cwd=REPO, capture_output=True).returncode == 0


def run_harness(root=None):
    env = {"QV2_DB": str(_db.DB_PATH), "QV2_PY": sys.executable, "QV2_A": NORA,
           "PATH": os.environ.get("PATH", "")}
    if root:
        env["QV2_ROOT"] = str(root)
    out = subprocess.run([NODE, str(REPO / "tests" / "qv2_vital_harness.js")], cwd=REPO, env=env,
                         capture_output=True, text=True, timeout=180)
    if out.returncode != 0:
        raise AssertionError(out.stderr[-2000:])
    return json.loads(out.stdout)


def seed(db):
    a = db.assertion
    db.ok([
        db.name(NORA, "n1", "Ines Okafor-Lund"),
        {"op": "set", "path": f"people/{NORA}/preferredNameRef", "value": "n1", "expectedPrevious": None},
        {"op": "add", "path": "places/pl-a", "value": {"label": "Minot"}},
        {"op": "add", "path": "places/pl-b", "value": {"label": "Minot"}},        # same name, a different place
        {"op": "add", "path": "places/pl-c", "value": {"label": "Oslo"}},
        {"op": "add", "path": "people/p-m", "value": {}}, db.name("p-m", "nm", "Ada Okafor"),
        {"op": "add", "path": "relationships/r1",
         "value": {"subjectPersonId": "p-m", "otherPersonId": NORA, "kind": "parent_of"}},
        {"op": "add", "path": "events/e-ab",
         "value": {"type": "birth", "place": "pl-c", "participants": [{"person": "p-m", "role": "subject"}]}},
        a("d-ab", "event", "e-ab", "person.birth.date", date("1915", "1915", "year"), source="narrator_stated"),
        {"op": "set", "path": "people/p-m/birthEventRef", "value": "e-ab", "expectedPrevious": None},
        a("ls-m", "person", "p-m", "person.life_status", "explicitly_living"),
        {"op": "add", "path": "people/p-f", "value": {}}, db.name("p-f", "nf", "Olaf Lund"),
        {"op": "add", "path": "relationships/r2",
         "value": {"subjectPersonId": "p-f", "otherPersonId": NORA, "kind": "parent_of"}},
        # unrelated — must survive untouched
        {"op": "add", "path": "events/e-w", "value": {"type": "work", "attributes": {"employer": "the county"},
                                                       "participants": [{"person": NORA, "role": "worker"}]}},
        a("d-w", "event", "e-w", "event.work.period", date("1960 to 1975", "1960/1975", "year")),
    ])
    # C-4E review: Greta — an EXPLICITLY ACCEPTED birth date beside a retained
    # competing one, and an EXPLICITLY ACCEPTED "living".
    db.ok([
        {"op": "add", "path": "people/p-g", "value": {}}, db.name("p-g", "ng", "Greta Lund"),
        {"op": "add", "path": "relationships/r3",
         "value": {"subjectPersonId": "p-g", "otherPersonId": NORA, "kind": "grandparent_of"}},
        {"op": "add", "path": "events/e-gb",
         "value": {"type": "birth", "participants": [{"person": "p-g", "role": "subject"}]}},
        {"op": "set", "path": "people/p-g/birthEventRef", "value": "e-gb", "expectedPrevious": None},
        a("g-A", "event", "e-gb", "person.birth.date", date("1920", "1920", "year"), source="narrator_stated"),
        a("gls", "person", "p-g", "person.life_status", "explicitly_living"),
    ])
    db.ok([
        a("g-B", "event", "e-gb", "person.birth.date", date("1921", "1921", "year"), source="document",
          status="conflicted", conflictWith="g-A"),
        {"op": "set", "path": "assertions/g-A/conflictWith", "value": "g-B", "expectedPrevious": None},
        {"op": "set", "path": "assertions/g-A/status", "value": "conflicted", "expectedPrevious": "operator_entered"},
        {"op": "set", "path": "acceptances/event/e-gb/person.birth.date", "value": "g-A", "expectedPrevious": None},
        {"op": "set", "path": "acceptances/person/p-g/person.life_status", "value": "gls", "expectedPrevious": None},
    ])


@unittest.skipUnless(HAVE_JSDOM, "node + jsdom are required — npm install")
class BirthDeathPlacesThroughTheEditor(unittest.TestCase):
    """ONE harness run per class; every test reads its checks or the database."""

    @classmethod
    def setUpClass(cls):
        db = _Db("run")
        db.setUp()
        cls._db = db
        try:
            seed(db)
            cls.before_work = cls._rows("SELECT * FROM lr_events WHERE id='e-w'")
            cls.before_people = cls._rows("SELECT id, date_of_birth, place_of_birth FROM people ORDER BY id")
            cls.r = run_harness(os.environ.get("QV2_ROOT"))
        except Exception:
            db.tearDown()
            raise

    @classmethod
    def tearDownClass(cls):
        cls._db.tearDown()

    @staticmethod
    def _rows(sql, *args):
        con = sqlite3.connect(str(_db.DB_PATH))
        con.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in con.execute(sql, args)]
        finally:
            con.close()

    def one(self, sql, *args):
        rows = self._rows(sql, *args)
        self.assertEqual(len(rows), 1, rows)
        return rows[0]

    def value(self, aid):
        return json.loads(self.one("SELECT value_json FROM lr_assertions WHERE id=?", aid)["value_json"])

    def test_the_harness_ran_and_every_dom_check_holds(self):
        self.assertNotIn("error", self.r, self.r.get("error"))
        failed = [c for c in self.r["checks"] if not c["ok"]]
        self.assertEqual(failed, [], json.dumps(failed, indent=1))
        self.assertGreaterEqual(len(self.r["checks"]), 15)

    # 1, 3, 4, 5 — the narrator's birth
    def test_the_narrators_birth_is_one_event_with_its_date_and_the_chosen_place(self):
        births = self._rows("SELECT e.* FROM lr_events e JOIN lr_event_participants p ON p.event_id=e.id "
                            "WHERE e.type='birth' AND p.person_id=? AND p.role='subject'", NORA)
        self.assertEqual(len(births), 1, "one birth event, then EXTENDED — not a second")
        ev = births[0]
        self.assertEqual(self.one("SELECT birth_event_id FROM lr_people WHERE id=?", NORA)["birth_event_id"], ev["id"])
        self.assertEqual(ev["place_id"], "pl-a", "finally the FIRST Minot, chosen by id")
        first = [c for c in self.r["facts"]["firstPatch"] if c["path"] == f"events/{ev['id']}"][0]
        self.assertEqual(first["value"]["place"], "pl-b", "first the SECOND Minot, chosen by id")
        d = self.one("SELECT * FROM lr_assertions WHERE subject_type='event' AND subject_id=?", ev["id"])
        self.assertEqual(d["concept_id"], "person.birth.date")
        self.assertEqual(json.loads(d["value_json"]),
                         {"text": "30 August 1939", "value": "1939-08-30", "precision": "day"})

    # 2, 15 — Ada's birth EXTENDED: same event, corrected date supersedes, provenance kept
    def test_an_existing_birth_is_extended_and_the_old_date_superseded(self):
        births = self._rows("SELECT e.id FROM lr_events e JOIN lr_event_participants p ON p.event_id=e.id "
                            "WHERE e.type='birth' AND p.person_id='p-m'")
        self.assertEqual([b["id"] for b in births], ["e-ab"])
        self.assertEqual(self.one("SELECT place_id FROM lr_events WHERE id='e-ab'")["place_id"], "pl-c",
                         "the place was not touched")
        old = self.one("SELECT * FROM lr_assertions WHERE id='d-ab'")
        self.assertEqual(old["status"], "superseded")
        new = self.one("SELECT * FROM lr_assertions WHERE id=?", old["superseded_by_id"])
        self.assertEqual((new["concept_id"], new["supersedes_id"], new["source"], new["asserted_by"]),
                         ("person.birth.date", "d-ab", "operator", "operator"))
        self.assertEqual(json.loads(new["value_json"]), {"text": "about 1915", "value": "1915~", "precision": "year"})
        self.assertEqual(old["source"], "narrator_stated", "the earlier telling keeps its own provenance")

    # 6, 7, 8 — places: a new one is a distinct record, same names stay distinct
    def test_a_new_place_is_a_separate_record_even_with_a_recorded_name(self):
        places = self._rows("SELECT id, label FROM lr_places ORDER BY id")
        minots = [p["id"] for p in places if p["label"] == "Minot"]
        self.assertEqual(len(minots), 3, places)
        new_id = [i for i in minots if i not in ("pl-a", "pl-b")][0]
        death = self.one("SELECT e.* FROM lr_events e JOIN lr_event_participants p ON p.event_id=e.id "
                         "WHERE e.type='death' AND p.person_id='p-m'")
        self.assertEqual(death["place_id"], new_id, "the death points at the NEW place, not a same-named one")

    # 9, 12 — Ada's death and 'deceased' landed together; unknown date kept as said
    def test_death_and_deceased_landed_in_one_save(self):
        death = self.one("SELECT e.* FROM lr_events e JOIN lr_event_participants p ON p.event_id=e.id "
                         "WHERE e.type='death' AND p.person_id='p-m'")
        self.assertEqual(self.one("SELECT death_event_id FROM lr_people WHERE id='p-m'")["death_event_id"], death["id"])
        d = self.one("SELECT * FROM lr_assertions WHERE subject_type='event' AND subject_id=?", death["id"])
        self.assertEqual((d["concept_id"], json.loads(d["value_json"])),
                         ("person.death.date", {"text": "unknown", "value": None, "precision": "unknown"}))
        live = self._rows("SELECT * FROM lr_assertions WHERE subject_id='p-m' AND concept_id='person.life_status' "
                          "AND status NOT IN ('superseded','rejected')")
        self.assertEqual([json.loads(x["value_json"]) for x in live], ["deceased"])
        self.assertEqual(live[0]["supersedes_id"], "ls-m", "the earlier 'living' is superseded, not erased")
        self.assertEqual(self.one("SELECT status FROM lr_assertions WHERE id='ls-m'")["status"], "superseded")

    # 11 — deceased alone invents nothing
    def test_deceased_alone_creates_no_death(self):
        self.assertEqual(self._rows("SELECT e.id FROM lr_events e JOIN lr_event_participants p ON p.event_id=e.id "
                                    "WHERE e.type='death' AND p.person_id='p-f'"), [])
        self.assertIsNone(self.one("SELECT death_event_id FROM lr_people WHERE id='p-f'")["death_event_id"])
        live = self._rows("SELECT value_json FROM lr_assertions WHERE subject_id='p-f' AND "
                          "concept_id='person.life_status' AND status NOT IN ('superseded','rejected')")
        self.assertEqual([json.loads(x["value_json"]) for x in live], ["deceased"])

    # C-4E review — an ACCEPTED birth date corrected: the acceptance moves with it
    def test_correcting_an_accepted_dob_moves_the_acceptance_and_keeps_both_accounts(self):
        a = self.one("SELECT * FROM lr_assertions WHERE id='g-A'")
        self.assertEqual(a["status"], "superseded", "A is superseded, not deleted")
        c = self.one("SELECT * FROM lr_assertions WHERE id=?", a["superseded_by_id"])
        self.assertEqual((c["supersedes_id"], json.loads(c["value_json"])),
                         ("g-A", {"text": "1922", "value": "1922", "precision": "year"}))
        self.assertEqual(self.one("SELECT status FROM lr_assertions WHERE id='g-B'")["status"], "conflicted",
                         "the retained competing account survives, untouched")
        acc = self.one("SELECT accepted_assertion_id FROM lr_acceptances WHERE subject_type='event' "
                       "AND subject_id='e-gb' AND concept_id='person.birth.date'")
        self.assertEqual(acc["accepted_assertion_id"], c["id"], "the acceptance MOVED to the correction")
        from api.services.life_record import writer as W
        ev = next(e for e in W.read_record(NORA)["events"] if e["id"] == "e-gb")
        self.assertEqual(ev["date"]["value"], "1922", "the record's resolved birth date is the correction")

    # C-4E review — an ACCEPTED "living" and a death, in one Save
    def test_an_accepted_living_status_moves_to_deceased_with_the_death(self):
        ls = self.one("SELECT * FROM lr_assertions WHERE id='gls'")
        self.assertEqual(ls["status"], "superseded")
        dec = self.one("SELECT * FROM lr_assertions WHERE id=?", ls["superseded_by_id"])
        self.assertEqual((json.loads(dec["value_json"]), dec["supersedes_id"]), ("deceased", "gls"))
        acc = self.one("SELECT accepted_assertion_id FROM lr_acceptances WHERE subject_type='person' "
                       "AND subject_id='p-g' AND concept_id='person.life_status'")
        self.assertEqual(acc["accepted_assertion_id"], dec["id"])
        death = self.one("SELECT e.* FROM lr_events e JOIN lr_event_participants p ON p.event_id=e.id "
                         "WHERE e.type='death' AND p.person_id='p-g'")
        self.assertEqual(self.one("SELECT death_event_id FROM lr_people WHERE id='p-g'")["death_event_id"], death["id"])
        d = self.one("SELECT * FROM lr_assertions WHERE subject_type='event' AND subject_id=?", death["id"])
        self.assertEqual(json.loads(d["value_json"]), {"text": "2001", "value": "2001", "precision": "year"})

    # 14 — unrelated data survives
    def test_unrelated_events_and_assertions_are_untouched(self):
        self.assertEqual(self._rows("SELECT * FROM lr_events WHERE id='e-w'"), self.before_work)
        self.assertEqual(self.one("SELECT status FROM lr_assertions WHERE id='d-w'")["status"], "operator_entered")

    def test_no_legacy_mirror_is_written(self):
        # The Life Record is the authority; the old people row is not a second copy.
        self.assertEqual(self._rows("SELECT id, date_of_birth, place_of_birth FROM people ORDER BY id"),
                         self.before_people)


class TheWriterHoldsTheInvariants(_Db):
    """10 — atomicity and duplication, at the writer: a Save is all or nothing."""

    def ev(self, eid, kind, pid, place=None):
        v = {"type": kind, "participants": [{"person": pid, "role": "subject"}]}
        if place:
            v["place"] = place
        return {"op": "add", "path": f"events/{eid}", "value": v}

    def setUp(self):
        super().setUp()
        self.ok([self.name(NORA, "n1", "Nora Whitfield"), {"op": "add", "path": "people/p", "value": {}},
                 self.name("p", "np", "Tom Whitfield")])

    def test_a_death_without_deceased_is_refused_whole(self):
        r = self.write([self.ev("e-d", "death", "p"),
                        self.assertion("a-d", "event", "e-d", "person.death.date", date("1990", "1990", "year"))])
        self.assertFalse(r.get("ok"))
        self.assertIn("death event", json.dumps(r))
        self.assertEqual(self.count("lr_events"), 0)
        self.assertEqual(self.count("lr_assertions"), 0)

    def test_a_failing_deceased_half_leaves_no_death(self):
        r = self.write([self.ev("e-d", "death", "p"),
                        self.assertion("a-ls", "person", "p", "person.life_status", "dead")])   # not a valid status
        self.assertFalse(r.get("ok"))
        self.assertEqual(self.count("lr_events"), 0)

    def test_death_with_deceased_in_one_change_set_is_accepted(self):
        self.ok([self.ev("e-d", "death", "p"),
                 self.assertion("a-ls", "person", "p", "person.life_status", "deceased"),
                 {"op": "set", "path": "people/p/deathEventRef", "value": "e-d", "expectedPrevious": None}])

    def test_a_second_birth_event_for_the_same_person_is_refused(self):
        self.ok([self.ev("e-b1", "birth", "p")])
        r = self.write([self.ev("e-b2", "birth", "p")])
        self.assertFalse(r.get("ok"))
        self.assertIn("one birth and one death per person", json.dumps(r))
        self.assertEqual(self.count("lr_events"), 1)

    def test_a_second_death_event_is_refused_too(self):
        self.ok([self.ev("e-d1", "death", "p"),
                 self.assertion("a-ls", "person", "p", "person.life_status", "deceased")])
        r = self.write([self.ev("e-d2", "death", "p")])
        self.assertFalse(r.get("ok"))

    def test_the_wrong_date_concept_on_a_birth_is_refused(self):
        r = self.write([self.ev("e-b", "birth", "p"),
                        self.assertion("a-b", "event", "e-b", "person.death.date", date("1990", "1990", "year"))])
        self.assertFalse(r.get("ok"))
        self.assertEqual(self.count("lr_events"), 0)


if __name__ == "__main__":
    unittest.main()
