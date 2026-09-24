"""Batch B-5 — the Life Record's one writer, on real isolated SQLite.

Chris's acceptance list (2026-09-23), each on a fresh database migrated by the
product's own `init_db` (0063 included), with FICTIONAL narrators only:
create a person · relationships · an approximate DOB · two conflicting DOBs,
then accept one · a later correction that keeps history · living / deceased /
unknown · same-name distinct people · a stale same-path write rejected · a
non-overlapping concurrent edit allowed · an atomic multi-part write · no
cross-narrator contamination · (graph projection: test_life_record_graph).

The property under test is produced by the shipped writer and read back by the
shipped assembler; fixtures supply only values (docs/TESTING-DOCTRINE.md).
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))

from api import db as _db  # noqa: E402
from api.services.life_record import rules as R  # noqa: E402
from api.services.life_record import writer as W  # noqa: E402

NORA, OWEN = "narrator-nora-fictional", "narrator-owen-fictional"
T0 = "2026-09-23T00:00:00Z"


def date(text, value=None, precision="day"):
    return {"text": text, "value": value, "precision": precision}


_TEMPLATE = {}


def _migrated_template() -> Path:
    """One database per process, migrated by the product's own init_db, copied
    per test. Still the real schema — just not re-migrated 33 times."""
    if "path" not in _TEMPLATE:
        d = tempfile.mkdtemp(prefix="lr-template-")
        orig = _db.DB_PATH
        _db.DB_PATH = Path(d) / "template.sqlite3"
        try:
            _db.init_db()
            con = sqlite3.connect(str(_db.DB_PATH))
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            con.close()
        finally:
            _TEMPLATE["path"], _db.DB_PATH = _db.DB_PATH, orig
    return _TEMPLATE["path"]


class _Db(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = _db.DB_PATH
        _db.DB_PATH = Path(self.tmp.name) / "lr.sqlite3"
        shutil.copyfile(_migrated_template(), _db.DB_PATH)
        con = sqlite3.connect(str(_db.DB_PATH))
        for nid, name in ((NORA, "Nora Whitfield"), (OWEN, "Owen Marsh")):
            con.execute("INSERT INTO people(id, display_name, created_at, updated_at) VALUES (?,?,?,?)",
                        (nid, name, T0, T0))
        con.commit()
        con.close()

    def tearDown(self):
        _db.DB_PATH = self._orig
        self.tmp.cleanup()

    # helpers
    def write(self, changes, nid=NORA, base=None, actor="operator:test"):
        return W.apply_changes(nid, base, changes, actor)

    def ok(self, changes, nid=NORA, **kw):
        r = self.write(changes, nid, **kw)
        self.assertTrue(r.get("ok"), r)
        return r

    def rec(self, nid=NORA):
        return W.read_record(nid)

    def person(self, pid, nid=NORA):
        return next((p for p in self.rec(nid)["people"] if p["id"] == pid), None)

    def count(self, table):
        con = sqlite3.connect(str(_db.DB_PATH))
        try:
            return con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        finally:
            con.close()

    def name(self, pid, nid_, text, **kw):
        return {"op": "add", "path": f"people/{pid}/names/{nid_}",
                "value": dict({"fullText": text}, **kw)}

    def assertion(self, aid, stype, sid, concept, value, **kw):
        v = dict({"subjectType": stype, "subjectId": sid, "conceptId": concept, "value": value,
                  "source": "operator", "assertedBy": "narrator", "status": "operator_entered"}, **kw)
        return {"op": "add", "path": f"assertions/{aid}", "value": v}

    def birth(self, eid, pid, text, value, precision, aid):
        return [
            {"op": "add", "path": f"events/{eid}",
             "value": {"type": "birth", "participants": [{"person": pid, "role": "subject"}]}},
            self.assertion(aid, "event", eid, "person.birth.date", date(text, value, precision)),
            {"op": "set", "path": f"people/{pid}/birthEventRef", "value": eid, "expectedPrevious": None},
        ]


class ReadWritesNothing(_Db):
    def test_get_of_a_narrator_with_no_record_writes_nothing(self):
        r = self.rec()
        self.assertEqual((r["revision"], r["people"]), (0, []))
        self.assertEqual(self.count("lr_record"), 0, "a read never creates the record")


class CreatePerson(_Db):
    def test_first_write_creates_the_record_and_the_narrators_own_person(self):
        self.ok([self.name(NORA, "n-nora", "Nora Whitfield"),
                 {"op": "add", "path": "people/p-mother", "value": {}},
                 self.name("p-mother", "n-mother", "Ada Whitfield")])
        rec = self.rec()
        self.assertEqual(rec["narrator_person_id"], NORA, "the narrator IS people.id")
        self.assertEqual(sorted(p["id"] for p in rec["people"]), sorted([NORA, "p-mother"]))
        self.assertEqual(self.person("p-mother")["names"][0]["fullText"], "Ada Whitfield")
        self.assertEqual(rec["revision"], 1)

    def test_a_name_is_kept_whole_as_supplied(self):
        self.ok([self.name(NORA, "n1", "Ari Jo del Río Mercer",
                           givenParts=["Ari", "Jo"], family="del Río Mercer")])
        n = self.person(NORA)["names"][0]
        self.assertEqual((n["fullText"], n["family"]), ("Ari Jo del Río Mercer", "del Río Mercer"))

    def test_a_former_name_is_the_same_person_and_not_for_casual_use(self):
        self.ok([self.name(NORA, "n-now", "Nora Whitfield"),
                 self.name(NORA, "n-before", "Nathan Whitfield", kind="former")])
        rec = self.rec()
        self.assertEqual(len(rec["people"]), 1, "a former name never mints a person")
        former = [n for n in rec["people"][0]["names"] if n["kind"] == "former"][0]
        self.assertEqual(former["use"], "historical_only")

    def test_pronouns_persist_as_an_optional_person_fact(self):
        self.ok([self.assertion("a-pr", "person", NORA, "person.pronouns", "she/her")])
        self.assertEqual([a["value"] for a in self.person(NORA)["person.pronouns"]], ["she/her"])


class Relationships(_Db):
    def test_relationship_between_stable_people(self):
        self.ok([{"op": "add", "path": "people/p-mother", "value": {}},
                 self.name("p-mother", "n-m", "Ada Whitfield"),
                 {"op": "add", "path": "relationships/r1",
                  "value": {"subjectPersonId": "p-mother", "otherPersonId": NORA, "kind": "parent_of"}},
                 self.assertion("a-r1", "relationship", "r1", "relationship.kind", "parent_of")])
        r = self.rec()["relationships"][0]
        self.assertEqual((r["subjectPersonId"], r["otherPersonId"], r["kind"]), ("p-mother", NORA, "parent_of"))
        self.assertEqual(r["assertion"]["value"], "parent_of")

    def test_a_referenced_person_is_not_removed_implicitly(self):
        self.ok([{"op": "add", "path": "people/p-m", "value": {}},
                 {"op": "add", "path": "relationships/r1",
                  "value": {"subjectPersonId": "p-m", "otherPersonId": NORA, "kind": "parent_of"}}])
        r = self.write([{"op": "remove", "path": "people/p-m", "expectedPrevious": {}}])
        self.assertFalse(r["ok"])
        self.assertIsNotNone(self.person("p-m"))


class Dates(_Db):
    def test_approximate_dob_stays_approximate_and_anchors_the_span(self):
        self.ok(self.birth("e-b", NORA, "around 1945", "1945~", "approximate", "a-dob"))
        rec = self.rec()
        ev = rec["events"][0]
        self.assertEqual(ev["date"], date("around 1945", "1945~", "approximate"))
        span = R.resolve_life_span(rec)
        self.assertEqual((span["available"], span["precision"]), (True, "approximate"))

    def test_no_dob_no_fabricated_scaffold(self):
        self.ok([self.name(NORA, "n1", "Nora Whitfield")])
        self.assertFalse(R.resolve_life_span(self.rec())["available"])

    def test_a_birth_pointer_to_someone_elses_birth_is_refused(self):
        self.ok([{"op": "add", "path": "people/p-sis", "value": {}},
                 {"op": "add", "path": "events/e-sis",
                  "value": {"type": "birth", "participants": [{"person": "p-sis", "role": "subject"}]}}])
        r = self.write([{"op": "set", "path": f"people/{NORA}/birthEventRef", "value": "e-sis",
                         "expectedPrevious": None}])
        self.assertFalse(r["ok"])
        self.assertIn("subject_is_someone_else", json.dumps(r))

    def test_a_date_lives_only_on_its_event(self):
        r = self.write([self.assertion("a1", "person", NORA, "person.birth.date", date("1945", "1945", "year"))])
        self.assertFalse(r["ok"])


class ConflictAcceptCorrect(_Db):
    def _two_dobs(self):
        self.ok(self.birth("e-b", NORA, "August 30, 1939", "1939-08-30", "day", "a1"))
        self.ok([self.assertion("a2", "event", "e-b", "person.birth.date", date("1938", "1938", "year"),
                                source="extracted", status="conflicted", conflictWith="a1"),
                 {"op": "set", "path": "assertions/a1/conflictWith", "value": "a2", "expectedPrevious": None},
                 {"op": "set", "path": "assertions/a1/status", "value": "conflicted",
                  "expectedPrevious": "operator_entered"}])

    def test_two_conflicting_dobs_coexist_and_nothing_is_chosen(self):
        self._two_dobs()
        ev = self.rec()["events"][0]
        self.assertEqual(len(ev["dateAssertions"]), 2)
        self.assertNotIn("date", ev, "two live accounts and no decision is UNRESOLVED")
        self.assertFalse(R.resolve_life_span(self.rec())["available"])

    def test_unlinked_competing_accounts_are_refused(self):
        self.ok(self.birth("e-b", NORA, "August 30, 1939", "1939-08-30", "day", "a1"))
        r = self.write([self.assertion("a2", "event", "e-b", "person.birth.date",
                                       date("1938", "1938", "year"), source="extracted")])
        self.assertFalse(r["ok"], "competing accounts must be linked or adjudicated")

    def test_accept_one_explicitly(self):
        self._two_dobs()
        self.ok([{"op": "set", "path": "acceptances/event/e-b/person.birth.date", "value": "a1",
                  "expectedPrevious": None}])
        ev = self.rec()["events"][0]
        self.assertEqual(ev["date"]["value"], "1939-08-30")
        self.assertEqual(len(ev["dateAssertions"]), 2, "the alternative is retained")

    def test_a_later_correction_supersedes_and_keeps_history(self):
        self._two_dobs()
        self.ok([{"op": "set", "path": "acceptances/event/e-b/person.birth.date", "value": "a1",
                  "expectedPrevious": None}])
        self.ok([self.assertion("a3", "event", "e-b", "person.birth.date",
                                date("August 31, 1939", "1939-08-31"), source="narrator_stated",
                                status="narrator_corrected", supersedes="a1"),
                 {"op": "set", "path": "assertions/a1/supersededBy", "value": "a3", "expectedPrevious": None},
                 {"op": "set", "path": "assertions/a1/status", "value": "superseded",
                  "expectedPrevious": "conflicted"},
                 {"op": "set", "path": "acceptances/event/e-b/person.birth.date", "value": "a3",
                  "expectedPrevious": "a1"}])
        ev = self.rec()["events"][0]
        self.assertEqual(ev["date"]["value"], "1939-08-31")
        old = next(a for a in ev["dateAssertions"] if a["id"] == "a1")
        self.assertEqual((old["status"], old["supersededBy"], old["value"]),
                         ("superseded", "a3", "1939-08-30"), "the corrected account survives")

    def test_a_superseded_account_cannot_be_accepted(self):
        self.ok(self.birth("e-b", NORA, "August 30, 1939", "1939-08-30", "day", "a1"))
        self.ok([self.assertion("a2", "event", "e-b", "person.birth.date", date("August 31, 1939", "1939-08-31"),
                                status="narrator_corrected", supersedes="a1"),
                 {"op": "set", "path": "assertions/a1/supersededBy", "value": "a2", "expectedPrevious": None},
                 {"op": "set", "path": "assertions/a1/status", "value": "superseded",
                  "expectedPrevious": "operator_entered"}])
        r = self.write([{"op": "set", "path": "acceptances/event/e-b/person.birth.date", "value": "a1",
                         "expectedPrevious": None}])
        self.assertFalse(r["ok"])
        self.assertEqual(self.rec()["events"][0]["date"]["value"], "1939-08-31")

    def test_an_assertion_is_never_edited(self):
        self._two_dobs()
        r = self.write([{"op": "set", "path": "assertions/a1", "value": {}, "expectedPrevious": None}])
        self.assertFalse(r["ok"])

    def test_re_adding_an_assertion_id_does_not_overwrite_it(self):
        self.ok(self.birth("e-b", NORA, "August 30, 1939", "1939-08-30", "day", "a1"))
        r = self.write([self.assertion("a1", "event", "e-b", "person.birth.date",
                                       date("1941", "1941", "year"))])
        self.assertFalse(r["ok"])
        self.assertEqual(self.rec()["events"][0]["date"]["value"], "1939-08-30")


class ManyValuedConceptsHoldSeveralFacts(_Db):
    """Found by Batch C-1: two languages were refused as a 'dispute'. The
    catalog's cardinality decides: `many` holds several facts."""

    def test_two_languages_are_two_facts_not_competing_accounts(self):
        self.ok([self.assertion("l1", "person", NORA, "person.languages", "Igbo"),
                 self.assertion("l2", "person", NORA, "person.languages", "Swedish")])
        self.assertEqual([a["value"] for a in self.person(NORA)["person.languages"]], ["Igbo", "Swedish"])

    def test_a_one_valued_concept_still_needs_linking(self):
        self.ok([self.assertion("f1", "person", NORA, "person.faith.raised", "Anglican")])
        r = self.write([self.assertion("f2", "person", NORA, "person.faith.raised", "Methodist")])
        self.assertFalse(r["ok"], "two unlinked accounts of a `one` concept stay refused")


class LifeStatus(_Db):
    def _people(self):
        self.ok([{"op": "add", "path": f"people/{p}", "value": {}} for p in ("p-dead", "p-alive", "p-unknown")] +
                [self.assertion("s1", "person", "p-dead", "person.life_status", "deceased"),
                 self.assertion("s2", "person", "p-alive", "person.life_status", "explicitly_living")])

    def test_living_deceased_and_unknown(self):
        self._people()
        st = {p["id"]: (p.get("lifeStatus") or {}).get("value") for p in self.rec()["people"]}
        self.assertEqual((st["p-dead"], st["p-alive"], st["p-unknown"]),
                         ("deceased", "explicitly_living", None), "unknown stays unknown — never 'living'")

    def test_a_death_event_without_deceased_is_refused(self):
        self._people()
        r = self.write([{"op": "add", "path": "events/e-d",
                         "value": {"type": "death", "participants": [{"person": "p-unknown", "role": "subject"}]}}])
        self.assertFalse(r["ok"], "nothing infers deceased; the record refuses the contradiction")

    def test_atomic_multi_part_write_death_event_with_status(self):
        self._people()
        self.ok([{"op": "add", "path": "events/e-d",
                  "value": {"type": "death", "participants": [{"person": "p-unknown", "role": "subject"}]}},
                 self.assertion("s3", "person", "p-unknown", "person.life_status", "deceased")])
        self.assertEqual(self.person("p-unknown")["lifeStatus"]["value"], "deceased")


class SameNameDistinctPeople(_Db):
    def test_two_people_with_one_name_stay_two(self):
        self.ok([{"op": "add", "path": "people/p-a", "value": {}}, self.name("p-a", "na", "John Smith"),
                 {"op": "add", "path": "people/p-b", "value": {}}, self.name("p-b", "nb", "John Smith")])
        smiths = [p for p in self.rec()["people"] if p["names"] and p["names"][0]["fullText"] == "John Smith"]
        self.assertEqual(len(smiths), 2, "names are never identity keys; nothing merges")


class Concurrency(_Db):
    def setUp(self):
        super().setUp()
        self.ok([self.name(NORA, "n1", "Nora Whitfield"),
                 {"op": "add", "path": "people/p-m", "value": {}}, self.name("p-m", "n2", "Ada Whitfield")])
        self.base = self.rec()["revision"]

    def test_stale_same_path_write_is_rejected_and_writes_nothing(self):
        self.ok([{"op": "set", "path": "people/p-m/names/n2", "value": {"fullText": "Ada May Whitfield"},
                  "expectedPrevious": {"fullText": "Ada Whitfield", "kind": "current"}}], base=self.base)
        before = self.rec()
        r = self.write([{"op": "set", "path": "people/p-m/names/n2", "value": {"fullText": "Adeline Whitfield"},
                         "expectedPrevious": {"fullText": "Ada Whitfield", "kind": "current"}}], base=self.base)
        self.assertFalse(r["ok"])
        self.assertEqual(r["conflict"][0]["path"], "people/p-m/names/n2")
        self.assertEqual(r["conflict"][0]["current"]["fullText"], "Ada May Whitfield")
        self.assertEqual(self.rec(), before, "a conflict writes nothing")

    def test_non_overlapping_concurrent_edits_both_succeed(self):
        self.ok([{"op": "set", "path": f"people/{NORA}/names/n1", "value": {"fullText": "Nora J. Whitfield"},
                  "expectedPrevious": {"fullText": "Nora Whitfield", "kind": "current"}}], base=self.base)
        r = self.write([{"op": "set", "path": "people/p-m/names/n2", "value": {"fullText": "Ada May Whitfield"},
                         "expectedPrevious": {"fullText": "Ada Whitfield", "kind": "current"}}], base=self.base)
        self.assertTrue(r["ok"], "a stale baseRevision alone is not a conflict")

    def test_expected_previous_is_required(self):
        r = self.write([{"op": "set", "path": "people/p-m/names/n2", "value": {"fullText": "X"}}])
        self.assertFalse(r["ok"])


class Atomicity(_Db):
    def test_one_bad_change_writes_nothing_at_all(self):
        r = self.write([{"op": "add", "path": "people/p-x", "value": {}},
                        self.name("p-x", "nx", "Zed Doe"),
                        self.assertion("a-bad", "person", "p-x", "person.not_a_concept", "x")])
        self.assertFalse(r["ok"])
        self.assertEqual(self.count("lr_people"), 0)
        self.assertEqual(self.count("lr_names"), 0)
        self.assertEqual(self.count("lr_record"), 0)


class NarratorIsolation(_Db):
    def test_another_narrators_person_cannot_be_referenced_or_touched(self):
        self.ok([{"op": "add", "path": "people/p-nora-mom", "value": {}},
                 self.name("p-nora-mom", "nm", "Ada Whitfield")])
        before = self.rec(NORA)
        r = self.write([{"op": "add", "path": "relationships/r-x",
                         "value": {"subjectPersonId": "p-nora-mom", "otherPersonId": OWEN, "kind": "parent_of"}}],
                       nid=OWEN)
        self.assertFalse(r["ok"])
        r = self.write([{"op": "set", "path": "people/p-nora-mom/names/nm", "value": {"fullText": "X"},
                         "expectedPrevious": {"fullText": "Ada Whitfield", "kind": "current"}}], nid=OWEN)
        self.assertFalse(r["ok"])
        self.assertEqual(self.rec(NORA), before)
        self.assertEqual([p["id"] for p in self.rec(OWEN)["people"]], [], "Owen sees none of Nora's record")

    def test_an_assertion_about_another_narrators_person_is_refused(self):
        self.ok([{"op": "add", "path": "people/p-nora-mom", "value": {}}])
        r = self.write([self.assertion("a-x", "person", "p-nora-mom", "person.pronouns", "she/her")],
                       nid=OWEN)
        self.assertFalse(r["ok"])
        self.assertEqual(self.count("lr_assertions"), 0, "no dangling cross-narrator row")

    def test_narrator_erasure_removes_the_whole_record(self):
        self.ok([{"op": "add", "path": "people/p-m", "value": {}}, self.name("p-m", "n", "Ada Whitfield")])
        con = sqlite3.connect(str(_db.DB_PATH))
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("DELETE FROM people WHERE id = ?", (NORA,))
        con.commit()
        con.close()
        self.assertEqual((self.count("lr_record"), self.count("lr_people"), self.count("lr_names")), (0, 0, 0))


class StoriesKeepTheNarratorsWords(_Db):
    def setUp(self):
        super().setUp()
        con = sqlite3.connect(str(_db.DB_PATH))
        for cid, nid in (("c-nora", NORA), ("c-owen", OWEN)):
            con.execute("INSERT INTO story_candidates(id, narrator_id, transcript, trigger_reason) "
                        "VALUES (?,?,?,?)", (cid, nid, "We walked to the lake every Sunday.", "manual"))
        con.commit()
        con.close()

    def captured(self, cid, **kw):
        return {"op": "add", "path": "stories/s1",
                "value": dict({"origin": "captured", "candidateRef": cid, "kind": "memory"}, **kw)}

    def test_a_captured_story_references_the_narrators_own_candidate(self):
        self.ok([self.captured("c-nora")])
        s = self.rec()["stories"][0]
        self.assertEqual((s["candidateRef"], "body" in s), ("c-nora", False))

    def test_a_captured_story_is_a_reference_never_a_copy(self):
        r = self.write([self.captured("c-nora", body="copied words")])
        self.assertFalse(r["ok"])
        self.assertEqual(self.count("lr_stories"), 0)

    def test_another_narrators_candidate_is_refused(self):
        r = self.write([self.captured("c-owen")])
        self.assertFalse(r["ok"])

    def test_an_authored_story_holds_its_own_text(self):
        self.ok([{"op": "add", "path": "stories/s1",
                  "value": {"origin": "authored", "body": "A note for the grandchildren.", "kind": "message"}}])
        self.assertEqual(self.rec()["stories"][0]["body"], "A note for the grandchildren.")


class RevisionAudit(_Db):
    def test_every_write_is_audited_with_previous_values(self):
        self.ok([self.name(NORA, "n1", "Nora Whitfield")])
        self.ok([{"op": "set", "path": f"people/{NORA}/names/n1", "value": {"fullText": "Nora J. Whitfield"},
                  "expectedPrevious": {"fullText": "Nora Whitfield", "kind": "current"}}], base=1)
        con = sqlite3.connect(str(_db.DB_PATH))
        rows = con.execute("SELECT revision, base_revision, changes_json FROM lr_revisions "
                           "ORDER BY revision").fetchall()
        con.close()
        self.assertEqual([r[0] for r in rows], [1, 2])
        self.assertEqual(json.loads(rows[1][2])[0]["previous"]["fullText"], "Nora Whitfield")


if __name__ == "__main__":
    unittest.main()
