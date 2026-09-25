"""Batch C-1 — Life Record → Questionnaire V2 read model.

A difficult FICTIONAL narrator is written through the shipped Life Record
writer onto real SQLite migrated by init_db, assembled by the shipped store,
and handed — exactly as GET /api/life-record returns it — to the shipped
ui/js/questionnaire-v2-model.js under node. Nothing the assertions check is
constructed by the test: the record's shape comes from production code on
one side, the view from production code on the other.

Skips (and says so) when node is not installed.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))
sys.path.insert(0, str(REPO))

from api import db as _db  # noqa: E402
from tests.test_life_record_writer import NORA, _Db, date  # noqa: E402

NODE = shutil.which("node")
PROBE = REPO / "tests" / "qv2_adapter_probe.js"
N = NORA   # the narrator's person id IS people.id


def rel(rid, subj, other, kind, **kw):
    return {"op": "add", "path": f"relationships/{rid}",
            "value": dict({"subjectPersonId": subj, "otherPersonId": other, "kind": kind}, **kw)}


def person(pid):
    return {"op": "add", "path": f"people/{pid}", "value": {}}


def event(eid, etype, parts, place=None, **kw):
    v = dict({"type": etype, "participants": [{"person": p, "role": r} for p, r in parts]}, **kw)
    if place:
        v["place"] = place
    return {"op": "add", "path": f"events/{eid}", "value": v}


@unittest.skipUnless(NODE, "node is not installed — the adapter is shipped JS")
class QuestionnaireV2ReadModel(_Db):
    """One record, many views of it — built once per test (the template DB
    makes that cheap), because every test must start from shipped output."""

    def build(self):
        a = self.assertion
        self.ok([   # 1 — the narrator
            self.name(N, "n-now", "Ines Maribel Okafor-Lund", givenParts=["Ines", "Maribel"],
                      family="Okafor-Lund", pronunciation="EE-ness"),
            self.name(N, "n-before", "Ines Okafor", kind="former"),
            {"op": "set", "path": f"people/{N}/preferredNameRef", "value": "n-now",
             "expectedPrevious": None},
            a("pr1", "person", N, "person.pronouns", "ze/zir"),
            {"op": "add", "path": "places/pl-lagos", "value": {"label": "Lagos"}},
            event("e-nb", "birth", [(N, "subject")], place="pl-lagos"),
            a("d-nb", "event", "e-nb", "person.birth.date", date("around 1939", "1939~", "year")),
            {"op": "set", "path": f"people/{N}/birthEventRef", "value": "e-nb", "expectedPrevious": None},
            a("bo", "person", N, "person.birth.order", "second of four"),
            a("rc-sib", "person", N, "person.reported_count.siblings", 3),
            a("h1", "person", N, "person.heritage", "Igbo"),
            a("h2", "person", N, "person.heritage", "Swedish"),
            a("l1", "person", N, "person.languages", "Igbo"),
            a("l2", "person", N, "person.languages", "Swedish"),
            a("fr", "person", N, "person.faith.raised", "Anglican"),
            a("ms-n", "person", N, "person.military_service", "yes"),
            a("int", "person", N, "person.interest", "beekeeping"),
        ])
        self.ok([   # 2 — family and caregivers
            person("p-mother"), self.name("p-mother", "nm", "Adaeze Okafor"),
            a("ls-m", "person", "p-mother", "person.life_status", "deceased"),
            event("e-md", "death", [("p-mother", "subject")]),
            a("d-md", "event", "e-md", "person.death.date", date("1987", "1987", "year")),
            {"op": "set", "path": "people/p-mother/deathEventRef", "value": "e-md", "expectedPrevious": None},
            event("e-mb", "birth", [("p-mother", "subject")]),
            a("d-mb1", "event", "e-mb", "person.birth.date", date("1912", "1912", "year")),
            {"op": "set", "path": "people/p-mother/birthEventRef", "value": "e-mb", "expectedPrevious": None},
            a("ms-m", "person", "p-mother", "person.military_service", "unknown"),
            person("p-father"), self.name("p-father", "nf", "Gunnar Lund"),
            a("ls-f", "person", "p-father", "person.life_status", "unknown"),
            person("p-aunt"), self.name("p-aunt", "na", "Ngozi Okafor"),
            a("rc-aunt", "person", "p-aunt", "person.reported_count.children", 0),
            a("ms-a", "person", "p-aunt", "person.military_service", "no"),
            person("p-sib1"), self.name("p-sib1", "ns1", "Chidi Okafor-Lund"),
            person("p-sib2"), self.name("p-sib2", "ns2", "Astrid Okafor-Lund"),
            person("p-friend"), self.name("p-friend", "nfr", "Chidi Okafor-Lund"),
            rel("r-m", "p-mother", N, "parent_of", narratorLabel="Mama"),
            rel("r-f", "p-father", N, "parent_of"),
            rel("r-a", "p-aunt", N, "caregiver_of"),
            rel("r-s1", "p-sib1", N, "sibling_of"),
            rel("r-s2", N, "p-sib2", "sibling_of"),
            rel("r-fr", N, "p-friend", "friend_of"),
        ])
        self.ok([   # the mother's birth year is disputed; nobody has decided
            a("d-mb2", "event", "e-mb", "person.birth.date", date("1913", "1913", "year"),
              status="conflicted", conflictWith="d-mb1"),
            {"op": "set", "path": "assertions/d-mb1/conflictWith", "value": "d-mb2", "expectedPrevious": None},
        ])
        self.ok([   # 3 — partners, unions and children
            person("p-sp1"), self.name("p-sp1", "nsp1", "Tomas Berg"),
            person("p-pt2"), self.name("p-pt2", "npt2", "Lena Holm"),
            rel("r-sp1", N, "p-sp1", "spouse_of", period={"start": date("June 1961", "1961-06", "month"),
                                                        "end": date("1970", "1970", "year")},
                qualifiers={"status": "former"}),
            rel("r-pt2", "p-pt2", N, "partner_of", period={"start": date("1975", "1975", "year")}),
            event("e-u1", "union", [(N, "partner"), ("p-sp1", "partner")]),
            a("d-u1", "event", "e-u1", "event.union.date", date("June 1961", "1961-06", "month")),
            event("e-sep", "separation", [(N, "partner"), ("p-sp1", "partner")]),
            person("p-c1"), self.name("p-c1", "nc1", "Maja Berg"),
            person("p-c2"), self.name("p-c2", "nc2", "Oskar Holm-Okafor"),
            rel("r-c1", N, "p-c1", "parent_of"),
            rel("r-c1b", "p-sp1", "p-c1", "parent_of"),
            rel("r-c2", "p-c2", N, "child_of"),
            person("p-g1"), self.name("p-g1", "ng1", "Ada Berg"),
            rel("r-g1", N, "p-g1", "grandparent_of"),
            person("p-inlaw"), self.name("p-inlaw", "nil", "Karin Berg"),
            rel("r-inlaw", "p-c1", "p-inlaw", "spouse_of"),
        ])
        con = sqlite3.connect(str(_db.DB_PATH))
        con.execute("INSERT INTO story_candidates(id, narrator_id, transcript, trigger_reason) "
                    "VALUES ('c-ines', ?, 'The bees came back the spring Mama died.', 'manual')", (N,))
        con.commit()
        con.close()
        self.ok([   # 4–11 — places, periods, work, service, animals, stories
            {"op": "add", "path": "places/pl-upp", "value": {"label": "Uppsala"}},
            {"op": "add", "path": "places/pl-vax", "value": {"label": "Växjö"}},
            event("e-h1", "move", [(N, "resident")], place="pl-upp"),
            a("d-h1", "event", "e-h1", "event.residence.period",
              date("between 1958 and 1960", None, "unknown")),
            event("e-h2", "move", [(N, "resident"), ("p-pt2", "resident")], place="pl-vax",
                  attributes={"current": True}),
            event("e-ed", "education", [(N, "student")]),
            event("e-w1", "work", [(N, "worker")]),
            event("e-w2", "work", [(N, "worker")]),
            event("e-sv", "service", [(N, "member")]),
            a("d-sv", "event", "e-sv", "event.service.period", date("1956", "1956", "year")),
            {"op": "add", "path": "animals/a-dog", "value": {"name": "Biscuit", "species": "dog"}},
            a("br", "animal", "a-dog", "animal.breed", "beagle"),
            {"op": "add", "path": "stories/s-home", "value": {
                "origin": "authored", "kind": "memory", "body": "The yellow kitchen in Uppsala.",
                "placeRefs": ["pl-upp"]}},
            {"op": "add", "path": "stories/s-trad", "value": {
                "origin": "authored", "kind": "tradition", "body": "New Yam at my grandmother's."}},
            {"op": "add", "path": "stories/s-lesson", "value": {
                "origin": "authored", "kind": "lesson", "body": "Keep bees; keep patience."}},
            {"op": "add", "path": "stories/s-mama", "value": {
                "origin": "authored", "kind": "memory", "body": "Mama sang while she worked.",
                "peopleRefs": ["p-mother"]}},
            {"op": "add", "path": "stories/s-cap", "value": {
                "origin": "captured", "kind": "memory", "candidateRef": "c-ines"}},
        ])

    def view(self, trips=None, after_build=None):
        self.build()
        if after_build:
            after_build()
        record = json.loads(json.dumps(self.rec()))
        d = Path(self.tmp.name)
        (d / "record.json").write_text(json.dumps(record))
        args = [NODE, str(PROBE), str(d / "record.json")]
        if trips is not None:
            (d / "trips.json").write_text(json.dumps(trips))
            args.append(str(d / "trips.json"))
        db_before = hashlib.sha256(_db.DB_PATH.read_bytes()).hexdigest()
        out = subprocess.run(args, capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(hashlib.sha256(_db.DB_PATH.read_bytes()).hexdigest(), db_before)
        return record, json.loads(out.stdout)

    # ── the C-1 list ──────────────────────────────────────────────────
    def test_eleven_topics_in_order_and_zero_io(self):
        _, out = self.view()
        v = out["view"]
        self.assertEqual([t["title"] for t in out["topics"]], [
            "The narrator", "Family and caregivers", "Partners, unions and children",
            "Wider people and animals", "Homes and places", "Learning and work",
            "Service and community", "Heritage, languages and beliefs",
            "Experiences and interests", "Life today", "Memories, lessons and legacy"])
        self.assertEqual(v["topicOrder"], [t["id"] for t in out["topics"]])
        self.assertEqual(sorted(v["topics"]), sorted(v["topicOrder"]))
        self.assertEqual(out["touched"], [], "the adapter touched an IO global")
        self.assertTrue(out["deterministic"])

    def test_stable_ids_survive_and_nobody_is_merged(self):
        record, out = self.view()
        v = out["view"]
        self.assertEqual(sorted(v["people"]), sorted(p["id"] for p in record["people"]))
        self.assertEqual(sorted(v["relationships"]), sorted(r["id"] for r in record["relationships"]))
        chidis = [p for p in v["people"].values()
                  if any(n["fullText"] == "Chidi Okafor-Lund" for n in p["names"])]
        self.assertEqual(sorted(p["id"] for p in chidis), ["p-friend", "p-sib1"])
        self.assertEqual(sorted(v["topics"]["family"]["relationships"]),
                         ["r-a", "r-f", "r-m", "r-s1", "r-s2"])
        self.assertEqual({v["relationships"][r]["role"] for r in ("r-s1", "r-s2")}, {"sibling"})
        self.assertEqual(v["relationships"]["r-a"]["role"], "caregiver")

    def test_names_whole_former_on_the_same_person_pronouns_verbatim(self):
        _, out = self.view()
        ines = out["view"]["people"][N]
        self.assertEqual([(n["fullText"], n["kind"]) for n in ines["names"]],
                         [("Ines Maribel Okafor-Lund", "current"), ("Ines Okafor", "former")])
        self.assertEqual(ines["names"][0]["givenParts"], ["Ines", "Maribel"], "supplied, not split")
        self.assertNotIn("givenParts", out["view"]["people"]["p-mother"]["names"][0], "nothing parsed")
        self.assertEqual(ines["names"][1]["use"], "historical_only")
        self.assertEqual(ines["preferredNameId"], "n-now")
        self.assertEqual([p["value"] for p in ines["pronouns"]], ["ze/zir"])

    def test_life_status_and_answers_keep_blank_no_unknown_zero_apart(self):
        _, out = self.view()
        P = out["view"]["people"]
        self.assertEqual(P["p-mother"]["lifeStatus"]["value"], "deceased")
        self.assertEqual(P["p-father"]["lifeStatus"]["value"], "unknown")
        self.assertEqual(P["p-sib2"]["lifeStatus"]["state"], "blank")
        ms = {pid: P[pid]["militaryService"] for pid in (N, "p-aunt", "p-mother", "p-father")}
        self.assertEqual([(ms[p]["state"], ms[p].get("value")) for p in (N, "p-aunt", "p-mother", "p-father")],
                         [("value", "yes"), ("value", "no"), ("value", "unknown"), ("blank", None)])
        zero = P["p-aunt"]["reportedCounts"]["children"]
        self.assertEqual((zero["state"], zero["value"]), ("value", 0), "a stated zero is an answer")
        self.assertEqual(P["p-mother"]["reportedCounts"]["children"]["state"], "blank")
        self.assertEqual(P[N]["reportedCounts"]["siblings"]["value"], 3, "3 stated, 2 named: both kept")
        self.assertEqual(sorted(out["answer"].values()), ["declined", "no", "unknown", "yes"])

    def test_dates_keep_text_and_precision_and_disputes_stay_open(self):
        _, out = self.view()
        v = out["view"]
        self.assertEqual(v["people"][N]["birth"]["date"]["value"],
                         {"text": "around 1939", "value": "1939~", "precision": "year"})
        self.assertEqual(v["people"][N]["birth"]["placeLabel"], "Lagos")
        self.assertEqual(v["events"]["e-h1"]["date"]["value"]["text"], "between 1958 and 1960")
        self.assertEqual(v["events"]["e-u1"]["date"]["value"]["precision"], "month")
        mb = v["people"]["p-mother"]["birth"]["date"]
        self.assertEqual(mb["state"], "unresolved")
        self.assertEqual(sorted(x["value"]["text"] for x in mb["alternatives"]), ["1912", "1913"])
        self.assertIsNone(v["events"]["e-w1"]["date"], "work carries no date concept yet (C-4)")

    def test_a_legacy_date_is_read_as_stored_never_rewritten(self):
        """C-4 compatibility: dates stored before the contract (precision
        'approximate' / 'range') are READ exactly as stored. The legacy rows
        are put in by SQL, because the writer now refuses to create them."""
        legacy = {"d-nb": {"text": "around 1939", "value": "1939~", "precision": "approximate"},
                  "d-h1": {"text": "between 1958 and 1960", "value": "1958/1960", "precision": "range"}}

        def put_legacy():
            con = sqlite3.connect(str(_db.DB_PATH))
            for aid, val in legacy.items():
                con.execute("UPDATE lr_assertions SET value_json = ? WHERE id = ?",
                            (json.dumps(val, sort_keys=True), aid))
            con.commit()
            con.close()
        _, out = self.view(after_build=put_legacy)
        v = out["view"]
        self.assertEqual(v["people"][N]["birth"]["date"]["value"], legacy["d-nb"])
        self.assertEqual(v["events"]["e-h1"]["date"]["value"], legacy["d-h1"])

    def test_partners_children_grandchildren_and_the_unrelated_are_all_kept(self):
        _, out = self.view()
        t, R = out["view"]["topics"], out["view"]["relationships"]
        self.assertEqual(sorted(t["partners"]["relationships"]), ["r-pt2", "r-sp1"])
        self.assertEqual(R["r-sp1"]["qualifiers"], {"status": "former"})
        self.assertEqual(R["r-sp1"]["period"], {"start": date("June 1961", "1961-06", "month"),
                                                "end": date("1970", "1970", "year")})
        self.assertEqual(sorted(t["partners"]["unions"]), ["e-sep", "e-u1"])
        self.assertEqual(sorted(t["partners"]["children"]), ["r-c1", "r-c2"], "both stored directions")
        self.assertEqual(t["partners"]["grandchildren"], ["r-g1"], "no intermediate relative needed")
        self.assertEqual(t["wider"]["relationships"], ["r-fr"])
        self.assertEqual(t["wider"]["otherPeople"], ["p-inlaw"], "not related to the narrator, not lost")
        self.assertEqual(t["wider"]["animals"], ["a-dog"])

    def test_places_events_and_narrator_concepts_land_in_their_topics(self):
        _, out = self.view()
        t, v = out["view"]["topics"], out["view"]
        self.assertEqual(sorted(t["homes"]["events"]), ["e-h1", "e-h2"])
        self.assertEqual(t["narrator"]["currentHomes"], ["e-h2"])
        self.assertEqual(v["events"]["e-h2"]["participants"],
                         [{"personId": N, "role": "resident"}, {"personId": "p-pt2", "role": "resident"}])
        self.assertEqual(sorted(t["learning_work"]["events"]), ["e-ed", "e-w1", "e-w2"])
        self.assertEqual(t["service"]["events"], ["e-sv"])
        ines = v["people"][N]
        self.assertEqual([h["value"] for h in ines["heritage"]], ["Igbo", "Swedish"])
        self.assertEqual([x["value"] for x in ines["languages"]], ["Igbo", "Swedish"])
        self.assertEqual(ines["faithRaised"]["value"], "Anglican")
        self.assertEqual(ines["faithCurrent"]["state"], "blank")
        self.assertEqual(v["animals"]["a-dog"]["breed"]["value"], "beagle")

    def test_stories_are_references_or_authored_text_never_flattened(self):
        _, out = self.view()
        S, t = out["view"]["stories"], out["view"]["topics"]
        self.assertEqual(S["s-cap"]["candidateRef"], "c-ines")
        self.assertNotIn("body", S["s-cap"], "a captured story never carries a copy of the words")
        self.assertNotIn("bees came back", json.dumps(out["view"]))
        self.assertEqual(S["s-mama"]["body"], "Mama sang while she worked.")
        self.assertEqual(t["homes"]["stories"], ["s-home"])
        self.assertEqual(t["heritage"]["stories"], ["s-trad"])
        self.assertEqual(sorted(t["legacy"]["stories"]), ["s-cap", "s-lesson", "s-mama"])
        self.assertEqual(out["view"]["people"]["p-mother"]["stories"], ["s-mama"])

    def test_trips_are_references_not_copies(self):
        _, out = self.view(trips=[{"id": "trip-1", "label": "Norway, 1983",
                                   "stops": [{"place": "Bergen"}], "notes": "private"}])
        self.assertEqual(out["view"]["topics"]["experiences"]["trips"],
                         [{"tripId": "trip-1", "label": "Norway, 1983"}])
        self.assertNotIn("Bergen", json.dumps(out["view"]))


if __name__ == "__main__":
    unittest.main()
