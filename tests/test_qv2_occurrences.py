"""Batch C-4F — homes/moves and unions/separations, through the shipped
Questionnaire V2 editor and the one Life Record writer.

The DOM half (tests/qv2_occurrence_harness.js) drives the real controls against
the real writer; this file prepares the SQLite record, reads the harness's
checks, and then checks the DATABASE — what the Save actually wrote. A second
class exercises the writer directly for atomicity, concepts and duplication.

A home is its own `move` event; a union and a separation are separate events.
The same pair of people NEVER means the same occurrence, a separation never
rewrites the union it ends, and a missing end is never "current".
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
    out = subprocess.run([NODE, str(REPO / "tests" / "qv2_occurrence_harness.js")], cwd=REPO, env=env,
                         capture_output=True, text=True, timeout=180)
    if out.returncode != 0:
        raise AssertionError(out.stderr[-2000:])
    return json.loads(out.stdout)


LEGACY_PERIOD = '{"text": "about 1989 to 1995", "value": null, "precision": null}'


def seed(db):
    a = db.assertion
    db.ok([
        db.name(NORA, "n1", "Ines Okafor-Lund"),
        {"op": "set", "path": f"people/{NORA}/preferredNameRef", "value": "n1", "expectedPrevious": None},
        {"op": "add", "path": "places/pl-a", "value": {"label": "Minot"}},
        {"op": "add", "path": "places/pl-b", "value": {"label": "Minot"}},        # same name, a different place
        {"op": "add", "path": "places/pl-c", "value": {"label": "Oslo"}},
        {"op": "add", "path": "people/p-s", "value": {}}, db.name("p-s", "ns", "Sam Berg"),
        {"op": "add", "path": "relationships/r-s",
         "value": {"subjectPersonId": "p-s", "otherPersonId": NORA, "kind": "spouse_of",
                   "period": {"start": date("1961", "1961", "year")}}},
        # home 1 — a period, EXPLICITLY ACCEPTED
        {"op": "add", "path": "events/e-h1",
         "value": {"type": "move", "place": "pl-c", "participants": [{"person": NORA, "role": "resident"}]}},
        a("d-h1", "event", "e-h1", "event.residence.period", date("1962 to 1975", "1962/1975", "year"),
          source="narrator_stated"),
        {"op": "set", "path": "acceptances/event/e-h1/event.residence.period", "value": "d-h1",
         "expectedPrevious": None},
        # home 2 — its period is a LEGACY row, inserted below by SQL
        {"op": "add", "path": "events/e-h2",
         "value": {"type": "move", "place": "pl-a", "participants": [{"person": NORA, "role": "resident"}]}},
        # home 3 — EXPLICITLY current, no period; they have since moved on
        {"op": "add", "path": "events/e-h3",
         "value": {"type": "move", "place": "pl-c", "participants": [{"person": NORA, "role": "resident"}],
                   "attributes": {"current": True}}},
        # home 4 — current, "to present": unticking it alone is a contradiction
        {"op": "add", "path": "events/e-h4",
         "value": {"type": "move", "place": "pl-c", "participants": [{"person": NORA, "role": "resident"}],
                   "attributes": {"current": True}}},
        a("d-h4", "event", "e-h4", "event.residence.period", date("1985 to present", "1985/..", "unknown")),
        # home 5 — a CO-RESIDENT, and a LEGACY contradiction (current, yet the period ended)
        {"op": "add", "path": "people/p-co", "value": {}}, db.name("p-co", "nco", "Rosa Lund"),
        {"op": "add", "path": "events/e-h5",
         "value": {"type": "move", "place": "pl-a", "attributes": {"current": True},
                   "participants": [{"person": NORA, "role": "resident"}, {"person": "p-co", "role": "resident"}]}},
        a("d-h5", "event", "e-h5", "event.residence.period", date("1950 to 1955", "1950/1955", "year")),
        # home 6 — a LEGACY contradiction the other way ("to present", not current)
        {"op": "add", "path": "events/e-h6",
         "value": {"type": "move", "place": "pl-b", "participants": [{"person": NORA, "role": "resident"}]}},
        a("d-h6", "event", "e-h6", "event.residence.period", date("1970 to present", "1970/..", "unknown")),
        # the stored union
        {"op": "add", "path": "events/e-u1",
         "value": {"type": "union", "place": "pl-c", "participants": [{"person": NORA, "role": "partner"},
                                                                      {"person": "p-s", "role": "partner"}]}},
        a("d-u1", "event", "e-u1", "event.union.date", date("June 1961", "1961-06", "month")),
        # a union filed with the WRONG person (Alex, should be Taylor), with a relationship
        # DERIVED from it, a separately STATED one, and a story pointing at it
        {"op": "add", "path": "people/p-alex", "value": {}}, db.name("p-alex", "nal", "Alex Moreau"),
        {"op": "add", "path": "people/p-t", "value": {}}, db.name("p-t", "nt", "Taylor Reed"),
        {"op": "add", "path": "events/e-u2", "value": {"type": "union", "participants": [
            {"person": NORA, "role": "partner"}, {"person": "p-alex", "role": "partner"}]}},
        a("d-u2", "event", "e-u2", "event.union.date", date("1990", "1990", "year")),
        {"op": "add", "path": "relationships/r-d", "value": {
            "subjectPersonId": "p-alex", "otherPersonId": NORA, "kind": "spouse_of",
            "basis": "derived_from_event", "derivedFromEventId": "e-u2"}},
        {"op": "add", "path": "relationships/r-alex", "value": {
            "subjectPersonId": "p-alex", "otherPersonId": NORA, "kind": "friend_of"}},
        # a THREE-person union
        {"op": "add", "path": "people/p-a2", "value": {}}, db.name("p-a2", "na2", "Ana Cruz"),
        {"op": "add", "path": "people/p-b2", "value": {}}, db.name("p-b2", "nb2", "Ben Cruz"),
        {"op": "add", "path": "people/p-c2", "value": {}}, db.name("p-c2", "nc2", "Cole Park"),
        {"op": "add", "path": "events/e-u3", "value": {"type": "union", "participants": [
            {"person": NORA, "role": "partner"}, {"person": "p-a2", "role": "partner"},
            {"person": "p-b2", "role": "witness"}]}},
        a("d-u3", "event", "e-u3", "event.union.date", date("2000", "2000", "year")),
        # unrelated — must survive untouched
        {"op": "add", "path": "events/e-w", "value": {"type": "work", "attributes": {"employer": "the county"},
                                                       "participants": [{"person": NORA, "role": "worker"}]}},
        a("d-w", "event", "e-w", "event.work.period", date("1960 to 1975", "1960/1975", "year")),
        # STORIES that point at these occurrences (C-5 owns telling them; C-4F must not strand them)
        {"op": "add", "path": "stories/s-home", "value": {
            "origin": "authored", "kind": "memory", "body": "The furnace quit the first week; we slept by the stove.",
            "eventRefs": ["e-h1"], "placeRefs": ["pl-c"]}},
        {"op": "add", "path": "stories/s-legacy", "value": {
            "origin": "authored", "kind": "memory", "body": "The house on the hill.", "eventRefs": ["e-h2"]}},
        {"op": "add", "path": "stories/s-u2", "value": {
            "origin": "authored", "kind": "memory", "body": "We married on the beach.", "eventRefs": ["e-u2"]}},
        {"op": "add", "path": "stories/s-wed", "value": {
            "origin": "authored", "kind": "anecdote", "body": "It rained all through the wedding.",
            "eventRefs": ["e-u1"], "peopleRefs": ["p-s"]}},
    ])
    # A legacy period the C-4 parser would now read differently. Written by SQL
    # because the writer (rightly) refuses to add a date without its contract.
    con = sqlite3.connect(str(_db.DB_PATH))
    try:
        con.execute("INSERT INTO lr_assertions (id, narrator_id, subject_type, subject_id, concept_id, value_json, "
                    "source, recorded_by, asserted_by, recorded_at, status) VALUES "
                    "('d-h2', ?, 'event', 'e-h2', 'event.residence.period', ?, 'migrated', 'migration', "
                    "'narrator', '2026-01-01T00:00:00Z', 'operator_entered')", (NORA, LEGACY_PERIOD))
        con.commit()
    finally:
        con.close()


def pair_events(rows, kind=None):
    return [r for r in rows if kind is None or r["type"] == kind]


@unittest.skipUnless(HAVE_JSDOM, "node + jsdom are required — npm install")
class HomesUnionsSeparationsThroughTheEditor(unittest.TestCase):
    """ONE harness run per class; every test reads its checks or the database."""

    @classmethod
    def setUpClass(cls):
        db = _Db("run")
        db.setUp()
        cls._db = db
        try:
            seed(db)
            cls.before = {
                "work": cls._rows("SELECT * FROM lr_events WHERE id='e-w'"),
                "union": cls._rows("SELECT * FROM lr_events WHERE id='e-u1'"),
                "union_date": cls._rows("SELECT * FROM lr_assertions WHERE subject_id='e-u1'"),
                "legacy": cls._rows("SELECT * FROM lr_assertions WHERE id='d-h2'"),
                "rel": cls._rows("SELECT * FROM lr_relationships WHERE id='r-s'"),
                "rel_alex": cls._rows("SELECT * FROM lr_relationships WHERE id='r-alex'"),
                "rel_d": cls._rows("SELECT * FROM lr_relationships WHERE id='r-d'"),
                "people": cls._rows("SELECT * FROM people ORDER BY id"),
                "story_refs": cls._rows("SELECT * FROM lr_story_refs ORDER BY id"),
                "stories": cls._rows("SELECT * FROM lr_stories ORDER BY id"),
            }
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

    def narrator_events(self, kind):
        return self._rows("SELECT e.* FROM lr_events e JOIN lr_event_participants p ON p.event_id=e.id "
                          "WHERE e.type=? AND p.person_id=? ORDER BY e.id", kind, NORA)

    def live_date(self, eid):
        return self._rows("SELECT * FROM lr_assertions WHERE subject_type='event' AND subject_id=? "
                          "AND concept_id <> 'event.residence.type' "
                          "AND status NOT IN ('superseded','rejected')", eid)

    def new_home(self, value):
        for ev in self.narrator_events("move"):
            d = self.live_date(ev["id"])
            if d and json.loads(d[0]["value_json"]).get("value") == value:
                return ev, d[0]
        self.fail(f"no home with period {value!r}")

    def test_the_harness_ran_and_every_dom_check_holds(self):
        self.assertNotIn("error", self.r, self.r.get("error"))
        failed = [c for c in self.r["checks"] if not c["ok"]]
        self.assertEqual(failed, [], json.dumps(failed, indent=1))
        self.assertEqual(len(self.r["checks"]), 46, "every DOM check ran — none skipped by an early exit")

    # homes — each its own event
    def test_eight_homes_are_eight_separate_move_events(self):
        homes = self.narrator_events("move")
        self.assertEqual(len(homes), 8, homes)
        roles = self._rows("SELECT role FROM lr_event_participants WHERE event_id IN "
                           "(SELECT e.id FROM lr_events e WHERE e.type='move')")
        self.assertEqual({r["role"] for r in roles}, {"resident"})

    def test_ongoing_is_stated_and_an_unknown_end_stays_unknown(self):
        ev, d = self.new_home("1990/..")
        self.assertEqual(json.loads(d["value_json"]),
                         {"text": "1990 to present", "value": "1990/..", "precision": "unknown"})
        ev2, d2 = self.new_home("1980/")
        self.assertEqual(json.loads(d2["value_json"])["text"], "1980 to ?")
        self.assertEqual(ev2["place_id"], "pl-a", "an existing place, chosen by id")
        self.assertIsNone(json.loads(ev2["attributes_json"] or "{}").get("current"),
                          "an unknown end is NOT current")
        self.assertEqual(json.loads(ev["attributes_json"]), {"current": True}, "current because the operator said so")

    def test_current_is_one_explicit_truth(self):
        currents = [e["id"] for e in self.narrator_events("move")
                    if json.loads(e["attributes_json"] or "{}").get("current") is True]
        ev, _ = self.new_home("1990/..")
        self.assertEqual(sorted(currents), sorted([ev["id"], "e-h4", "e-h5"]),
                         "exactly the homes said to be current — several are allowed, none is inferred")
        h3 = self.one("SELECT * FROM lr_events WHERE id='e-h3'")
        self.assertIsNone(h3["attributes_json"], "unticked: the flag is gone, nothing else invented")
        self.assertEqual(h3["place_id"], "pl-c")
        self.assertEqual(self._rows("SELECT id FROM lr_assertions WHERE subject_id='e-h3'"), [],
                         "no period was invented for the home they left")

    def test_the_kind_of_home_is_an_assertion_on_that_home(self):
        rows = self._rows("SELECT * FROM lr_assertions WHERE concept_id='event.residence.type' AND subject_id='e-h1'")
        self.assertEqual([(r["subject_type"], r["subject_id"], json.loads(r["value_json"])) for r in rows],
                         [("event", "e-h1", "farmhouse")])
        self.assertIsNone(self.one("SELECT attributes_json FROM lr_events WHERE id='e-h1'")["attributes_json"],
                          "not smuggled into event attributes")

    def test_the_stated_marriage_count_is_kept_beside_the_identified_unions(self):
        rc = self.one("SELECT * FROM lr_assertions WHERE concept_id='person.reported_count.marriages'")
        self.assertEqual((rc["subject_id"], json.loads(rc["value_json"])), (NORA, 3))
        from api.services.life_record import writer as W
        rec = W.read_record(NORA)
        self.assertEqual(rec["reportedCounts"]["marriages"]["value"], 3)
        unions = [e for e in rec["events"] if e["type"] == "union" and any(
            p["person"] == "p-s" for p in e["participants"])]
        self.assertEqual(len(unions), 2, "two with Sam identified — the stated three is NOT overwritten by a count")

    def test_a_new_home_gets_its_kind_in_the_same_save(self):
        ev, _ = self.new_home("1990/..")
        rows = self._rows("SELECT * FROM lr_assertions WHERE concept_id='event.residence.type' AND subject_id=?", ev["id"])
        self.assertEqual([json.loads(r["value_json"]) for r in rows], ["apartment"])
        self.assertIsNone(json.loads(ev["attributes_json"]).get("type"), "a kind is an assertion, not an attribute")

    def participants(self, eid):
        return [(p["person_id"], p["role"]) for p in self._rows(
            "SELECT person_id, role FROM lr_event_participants WHERE event_id=? ORDER BY person_id", eid)]

    # C-4F review — correcting who took part
    def test_a_corrected_participant_keeps_the_event_its_derived_relationship_and_its_stories(self):
        self.assertEqual(self.participants("e-u2"), sorted([(NORA, "partner"), ("p-t", "partner")]))
        rd = self.one("SELECT * FROM lr_relationships WHERE id='r-d'")
        before = self.before["rel_d"][0]
        self.assertEqual((rd["subject_person_id"], rd["other_person_id"]), ("p-t", NORA), "the same relationship id followed")
        for col in ("kind", "basis", "derived_from_event_id", "period_json", "qualifiers_json", "narrator_label",
                    "described_as", "narrator_id", "created_at"):
            self.assertEqual(rd[col], before[col], col)
        self.assertEqual(self._rows("SELECT * FROM lr_relationships WHERE id='r-alex'"), self.before["rel_alex"],
                         "a STATED relationship is its own fact — not rewritten by an event correction")
        self.assertEqual(self._rows("SELECT target_type, target_id FROM lr_story_refs WHERE story_id='s-u2'"),
                         [{"target_type": "event", "target_id": "e-u2"}], "the story still points at the SAME event")

    def test_a_three_person_union_keeps_everyone_through_an_unrelated_edit_and_a_correction(self):
        self.assertEqual(self.participants("e-u3"),
                         sorted([(NORA, "partner"), ("p-c2", "partner"), ("p-b2", "witness")]),
                         "only Ana was corrected (to Cole); Ben and his role are untouched")
        d = self.live_date("e-u3")
        self.assertEqual([json.loads(x["value_json"])["value"] for x in d], ["2001"], "the unrelated date edit landed")

    def test_a_co_resident_survives_an_unrelated_home_edit(self):
        h5 = self.one("SELECT * FROM lr_events WHERE id='e-h5'")
        self.assertEqual((h5["place_id"], json.loads(h5["attributes_json"])), ("pl-c", {"current": True}))
        self.assertEqual(self.participants("e-h5"), sorted([(NORA, "resident"), ("p-co", "resident")]))
        self.assertEqual(self.one("SELECT place_id FROM lr_events WHERE id='e-h6'")["place_id"], "pl-c",
                         "a stored contradiction the edit did not touch never blocks it")

    def test_stories_still_point_at_the_same_occurrences(self):
        self.assertEqual(self._rows("SELECT * FROM lr_story_refs ORDER BY id"), self.before["story_refs"])
        self.assertEqual(self._rows("SELECT * FROM lr_stories ORDER BY id"), self.before["stories"])
        from api.services.life_record import writer as W
        rec = W.read_record(NORA)
        ids = {e["id"] for e in rec["events"]}
        for s in rec["stories"]:
            for eid in s.get("eventRefs", []):
                self.assertIn(eid, ids, f"story {s['id']} is stranded")
        self.assertEqual({e["id"] for e in rec["events"]} >= {"e-h1", "e-h2", "e-u1", "e-u2", "e-u3"}, True,
                         "edited occurrences kept their ids")

    def test_a_new_place_is_a_separate_record_even_with_a_recorded_name(self):
        minots = [p["id"] for p in self._rows("SELECT id, label FROM lr_places") if p["label"] == "Minot"]
        self.assertEqual(len(minots), 3)
        ev, _ = self.new_home("1990/..")
        self.assertNotIn(ev["place_id"], ("pl-a", "pl-b"))
        self.assertIn(ev["place_id"], minots)

    def test_a_corrected_accepted_period_supersedes_and_carries_the_acceptance(self):
        old = self.one("SELECT * FROM lr_assertions WHERE id='d-h1'")
        self.assertEqual(old["status"], "superseded")
        new = self.one("SELECT * FROM lr_assertions WHERE id=?", old["superseded_by_id"])
        self.assertEqual((new["concept_id"], new["supersedes_id"], json.loads(new["value_json"])),
                         ("event.residence.period", "d-h1",
                          {"text": "1962 to 1976", "value": "1962/1976", "precision": "year"}))
        self.assertEqual(old["source"], "narrator_stated", "the earlier telling keeps its own provenance")
        acc = self.one("SELECT accepted_assertion_id FROM lr_acceptances WHERE subject_type='event' "
                       "AND subject_id='e-h1' AND concept_id='event.residence.period'")
        self.assertEqual(acc["accepted_assertion_id"], new["id"])
        self.assertEqual(self.one("SELECT place_id FROM lr_events WHERE id='e-h1'")["place_id"], "pl-c",
                         "the period edit did not touch this home's place")

    def test_a_place_only_edit_leaves_the_legacy_period_byte_for_byte(self):
        self.assertEqual(self.one("SELECT place_id FROM lr_events WHERE id='e-h2'")["place_id"], "pl-b",
                         "the SECOND Minot, chosen by id")
        self.assertEqual(self._rows("SELECT * FROM lr_assertions WHERE id='d-h2'"), self.before["legacy"])
        self.assertEqual(len(self._rows("SELECT id FROM lr_assertions WHERE subject_id='e-h2'")), 1,
                         "no new period assertion was written")

    # unions and separations
    def test_union_separation_union_for_one_pair_are_three_distinct_events(self):
        rows = self._rows("SELECT e.id, e.type, e.place_id FROM lr_events e WHERE e.type IN ('union','separation') "
                          "AND EXISTS (SELECT 1 FROM lr_event_participants p WHERE p.event_id=e.id AND p.person_id=?) "
                          "AND EXISTS (SELECT 1 FROM lr_event_participants p WHERE p.event_id=e.id AND p.person_id='p-s') "
                          "ORDER BY e.id", NORA)
        self.assertEqual(sorted(r["type"] for r in rows), ["separation", "union", "union"], rows)
        self.assertEqual(len({r["id"] for r in rows}), 3)
        new_union = [r for r in rows if r["type"] == "union" and r["id"] != "e-u1"][0]
        self.assertEqual(new_union["place_id"], "pl-a")
        d = self.live_date(new_union["id"])
        self.assertEqual([(x["concept_id"], json.loads(x["value_json"])) for x in d],
                         [("event.union.date", {"text": "1980", "value": "1980", "precision": "year"})])
        sep = [r for r in rows if r["type"] == "separation"][0]
        self.assertIsNone(sep["place_id"])
        d = self.live_date(sep["id"])
        self.assertEqual([(x["concept_id"], json.loads(x["value_json"])["value"]) for x in d],
                         [("event.separation.date", "1975")])
        parts = self._rows("SELECT person_id, role FROM lr_event_participants WHERE event_id=? ORDER BY person_id",
                           sep["id"])
        self.assertEqual([(p["person_id"], p["role"]) for p in parts],
                         sorted([(NORA, "partner"), ("p-s", "partner")]))

    def test_the_separation_did_not_rewrite_the_union(self):
        self.assertEqual(self._rows("SELECT * FROM lr_events WHERE id='e-u1'"), self.before["union"])
        self.assertEqual(self._rows("SELECT * FROM lr_assertions WHERE subject_id='e-u1'"), self.before["union_date"])

    def test_the_relationship_period_is_not_derived_from_the_events(self):
        self.assertEqual(self._rows("SELECT * FROM lr_relationships WHERE id='r-s'"), self.before["rel"])

    def test_unrelated_data_and_the_legacy_people_row_are_untouched(self):
        self.assertEqual(self._rows("SELECT * FROM lr_events WHERE id='e-w'"), self.before["work"])
        self.assertEqual(self.one("SELECT status FROM lr_assertions WHERE id='d-w'")["status"], "operator_entered")
        self.assertEqual(self._rows("SELECT * FROM people ORDER BY id"), self.before["people"])


class TheWriterHoldsTheOccurrenceInvariants(_Db):
    """Atomicity, concept and duplication rules, at the writer."""

    def ev(self, eid, kind, parts, place=None):
        v = {"type": kind, "participants": [{"person": p, "role": r} for p, r in parts]}
        if place:
            v["place"] = place
        return {"op": "add", "path": f"events/{eid}", "value": v}

    def setUp(self):
        super().setUp()
        self.ok([self.name(NORA, "n1", "Nora Whitfield"), {"op": "add", "path": "people/p", "value": {}},
                 self.name("p", "np", "Tom Whitfield"), {"op": "add", "path": "places/pl", "value": {"label": "Fargo"}}])
        self.pair = [(NORA, "partner"), ("p", "partner")]

    def test_a_union_date_on_a_home_is_refused_whole(self):
        r = self.write([self.ev("e-h", "move", [(NORA, "resident")], "pl"),
                        self.assertion("a", "event", "e-h", "event.union.date", date("1970", "1970", "year"))])
        self.assertFalse(r.get("ok"))
        self.assertEqual((self.count("lr_events"), self.count("lr_assertions")), (0, 0))

    def test_an_impossible_period_is_refused_at_the_writer(self):
        r = self.write([self.ev("e-h", "move", [(NORA, "resident")]),
                        self.assertion("a", "event", "e-h", "event.residence.period",
                                       date("1990-02-30 to 1995", "1990-02-30/1995", "day"))])
        self.assertFalse(r.get("ok"))
        self.assertEqual(self.count("lr_events"), 0)

    def test_a_range_is_refused_as_a_union_date_at_the_writer(self):
        r = self.write([self.ev("e-u", "union", self.pair),
                        self.assertion("a", "event", "e-u", "event.union.date", date("1961 to 1962", "1961/1962", "year"))])
        self.assertFalse(r.get("ok"))
        self.assertEqual(self.count("lr_events"), 0)

    def test_a_change_set_breaking_a_rule_commits_nothing(self):
        # a valid union and separation beside a second birth for one person: all refused
        self.ok([self.ev("e-b1", "birth", [("p", "subject")])])
        r = self.write([self.ev("e-u", "union", self.pair), self.ev("e-s", "separation", self.pair),
                        self.ev("e-b2", "birth", [("p", "subject")])])
        self.assertFalse(r.get("ok"))
        self.assertEqual(self.count("lr_events"), 1, "no partial commit")

    # C-4F review — a relationship DERIVED from an event must be between its participants
    def derived(self, rid, subj, other, eid):
        return {"op": "add", "path": f"relationships/{rid}", "value": {
            "subjectPersonId": subj, "otherPersonId": other, "kind": "spouse_of",
            "basis": "derived_from_event", "derivedFromEventId": eid}}

    def add_people(self, *pids):
        out = []
        for pid in pids:
            out += [{"op": "add", "path": f"people/{pid}", "value": {}}, self.name(pid, f"n-{pid}", pid.title())]
        return out

    def test_a_stale_derived_relationship_is_refused_whole(self):
        r = self.write(self.add_people("p-alex", "p-sam") + [
            self.ev("e-u", "union", [(NORA, "partner"), ("p-alex", "partner")]),
            self.derived("r-d", "p-sam", NORA, "e-u")])
        self.assertFalse(r.get("ok"))
        self.assertIn("not a participant", json.dumps(r))
        self.assertEqual((self.count("lr_events"), self.count("lr_relationships")), (0, 0))

    def test_correcting_a_participant_without_its_derived_relationship_is_refused_whole(self):
        self.ok(self.add_people("p-alex", "p-sam") + [
            self.ev("e-u", "union", [(NORA, "partner"), ("p-alex", "partner")]),
            self.derived("r-d", "p-alex", NORA, "e-u")])
        # the writer's view lists participants in (person, role) order
        before = {"type": "union", "participants": [{"person": NORA, "role": "partner"},
                                                    {"person": "p-alex", "role": "partner"}]}
        after = {"type": "union", "participants": [{"person": NORA, "role": "partner"},
                                                   {"person": "p-sam", "role": "partner"}]}
        r = self.write([{"op": "set", "path": "events/e-u", "value": after, "expectedPrevious": before}])
        self.assertFalse(r.get("ok"), r)
        self.assertEqual(sorted(p["person"] for p in next(e for e in self.rec()["events"] if e["id"] == "e-u")
                                ["participants"]), sorted([NORA, "p-alex"]), "nothing committed")
        rel_before = {"subjectPersonId": "p-alex", "otherPersonId": NORA, "kind": "spouse_of",
                      "basis": "derived_from_event", "derivedFromEventId": "e-u"}
        self.ok([{"op": "set", "path": "events/e-u", "value": after, "expectedPrevious": before},
                 {"op": "set", "path": "relationships/r-d", "value": dict(rel_before, subjectPersonId="p-sam"),
                  "expectedPrevious": rel_before}])

    def test_the_same_pair_may_marry_separate_and_marry_again(self):
        self.ok([self.ev("e-u1", "union", self.pair),
                 self.assertion("a1", "event", "e-u1", "event.union.date", date("1961", "1961", "year"))])
        self.ok([self.ev("e-s", "separation", self.pair),
                 self.assertion("a2", "event", "e-s", "event.separation.date", date("1975", "1975", "year"))])
        self.ok([self.ev("e-u2", "union", self.pair),
                 self.assertion("a3", "event", "e-u2", "event.union.date", date("1980", "1980", "year"))])
        self.assertEqual(self.count("lr_events"), 3)


if __name__ == "__main__":
    unittest.main()
