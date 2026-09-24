"""Batch B-4 — the family graph: a server revision guard, and a projection of
the Life Record rather than a second store.

Real isolated SQLite migrated by the product's init_db (0063 + 0064), fictional
narrators. Rows are produced by the shipped writer and projection and read
back from the tables; nothing here constructs the property it asserts.
"""
from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))
sys.path.insert(0, str(REPO))

from api import db as _db  # noqa: E402
from api.services.life_record import graph_projection as G  # noqa: E402
from tests.test_life_record_writer import NORA, OWEN, _Db, date  # noqa: E402

try:
    from fastapi.testclient import TestClient  # noqa: F401
    from fastapi import FastAPI
    from api.routers import relationships as _rel_router
    _HAVE_FASTAPI = True
except Exception:  # pragma: no cover - interpreter without the web stack
    _HAVE_FASTAPI = False


class _Graph(_Db):
    def con(self):
        c = sqlite3.connect(str(_db.DB_PATH))
        c.row_factory = sqlite3.Row
        return c

    def graph(self, nid=NORA):
        return _db.graph_get_full(nid)

    def projected(self, nid=NORA):
        c = self.con()
        try:
            return G.read_projection(c, nid)
        finally:
            c.close()

    def family(self):
        """Nora, her mother Ada (approximate DOB in Spokane), her late father,
        and a former name that must not surface."""
        self.ok([
            self.name(NORA, "n-nora", "Nora Whitfield", givenParts=["Nora"], family="Whitfield"),
            self.name(NORA, "n-nora-old", "Nora Pell", kind="former"),
            {"op": "add", "path": "people/p-ada", "value": {}},
            self.name("p-ada", "n-ada", "Ada May Whitfield", givenParts=["Ada", "May"],
                      family="Whitfield", birthFamily="Lund"),
            {"op": "add", "path": "places/pl-spk", "value": {"label": "Spokane, Washington"}},
            {"op": "add", "path": "events/e-ada-b",
             "value": {"type": "birth", "place": "pl-spk",
                       "participants": [{"person": "p-ada", "role": "subject"}]}},
            self.assertion("a-ada-b", "event", "e-ada-b", "person.birth.date",
                           date("around 1915", "1915~", "approximate")),
            {"op": "set", "path": "people/p-ada/birthEventRef", "value": "e-ada-b",
             "expectedPrevious": None},
            {"op": "add", "path": "people/p-tom", "value": {}},
            self.name("p-tom", "n-tom", "Tom Whitfield", givenParts=["Tom"], family="Whitfield"),
            self.assertion("s-tom", "person", "p-tom", "person.life_status", "deceased"),
            {"op": "add", "path": "relationships/r-ada",
             "value": {"subjectPersonId": "p-ada", "otherPersonId": NORA, "kind": "parent_of",
                       "narratorLabel": "Mom"}},
            {"op": "add", "path": "relationships/r-tom",
             "value": {"subjectPersonId": "p-tom", "otherPersonId": NORA, "kind": "parent_of"}},
        ])


class ProjectionAgreesWithTheRecord(_Graph):
    def test_stored_projection_equals_the_projection_of_the_stored_record(self):
        self.family()
        want = G.project(self.rec())
        got = self.projected()
        key = lambda x: x["id"]  # noqa: E731
        self.assertEqual(sorted(got["persons"], key=key), sorted(want["persons"], key=key))
        self.assertEqual(sorted(got["relationships"], key=key), sorted(want["relationships"], key=key))

    def test_the_projected_values_are_the_records_values(self):
        self.family()
        p = {x["id"]: x for x in self.projected()["persons"]}
        ada, tom, nora = p["lr:p-ada"], p["lr:p-tom"], p["lr:" + NORA]
        self.assertEqual((ada["display_name"], ada["first_name"], ada["middle_name"],
                          ada["last_name"], ada["maiden_name"]),
                         ("Ada May Whitfield", "Ada", "May", "Whitfield", "Lund"))
        self.assertEqual((ada["birth_date"], ada["birth_place"]), ("around 1915", "Spokane, Washington"),
                         "the date as said, never a fabricated day")
        self.assertEqual((tom["deceased"], ada["deceased"]), (True, False))
        self.assertEqual((nora["is_narrator"], nora["display_name"]), (True, "Nora Whitfield"))
        r = {x["id"]: x for x in self.projected()["relationships"]}
        self.assertEqual((r["lr:r-ada"]["from_person_id"], r["lr:r-ada"]["to_person_id"],
                          r["lr:r-ada"]["relationship_type"], r["lr:r-ada"]["label"]),
                         ("lr:p-ada", "lr:" + NORA, "parent_of", "Mom"))

    def test_a_former_name_never_becomes_the_display_name(self):
        self.ok([self.name(NORA, "n-old", "Nora Pell", kind="former")])
        nora = self.projected()["persons"][0]
        self.assertEqual(nora["display_name"], "", "historical_only is not disclosed by the graph")

    def test_an_unresolved_date_projects_as_empty(self):
        self.family()
        self.ok([self.assertion("a-ada-b2", "event", "e-ada-b", "person.birth.date",
                                date("1916", "1916", "year"), status="conflicted",
                                conflictWith="a-ada-b"),
                 {"op": "set", "path": "assertions/a-ada-b/conflictWith", "value": "a-ada-b2",
                  "expectedPrevious": None}])
        ada = {x["id"]: x for x in self.projected()["persons"]}["lr:p-ada"]
        self.assertEqual(ada["birth_date"], "", "two live accounts and no decision: no guess")

    def test_a_correction_and_a_removal_reach_the_graph(self):
        self.family()
        self.ok([{"op": "set", "path": "people/p-ada/names/n-ada",
                  "value": {"fullText": "Adeline May Whitfield", "givenParts": ["Adeline", "May"],
                            "family": "Whitfield", "birthFamily": "Lund"},
                  "expectedPrevious": self.rec_name("p-ada", "n-ada")},
                 {"op": "remove", "path": "relationships/r-tom",
                  "expectedPrevious": self.rec_rel("r-tom")}])
        g = self.projected()
        self.assertEqual({x["id"]: x for x in g["persons"]}["lr:p-ada"]["display_name"],
                         "Adeline May Whitfield")
        self.assertNotIn("lr:r-tom", {x["id"] for x in g["relationships"]})

    def test_a_ui_edge_to_a_projected_person_survives_reprojection(self):
        self.family()
        rev = self.graph()["revision"]
        g = self.graph()
        _db.graph_replace_full(NORA, g["persons"] + [{"id": "ui-cousin", "display_name": "Cousin Bea"}],
                               g["relationships"] + [{"id": "ui-e1", "from_person_id": "ui-cousin",
                                                      "to_person_id": "lr:p-ada",
                                                      "relationship_type": "niece_of"}],
                               expected_revision=rev)
        self.ok([self.name("p-tom", "n-tom2", "Thomas Whitfield", kind="variant")])
        self.assertIn("ui-e1", {r["id"] for r in self.graph()["relationships"]})

    # helpers reading the CURRENT stored value, as a real client would
    def rec_name(self, pid, nid_):
        c = self.con()
        try:
            from api.services.life_record.writer import _Tx
            return _Tx(c, NORA, "t").view(f"people/{pid}/names/{nid_}")
        finally:
            c.close()

    def rec_rel(self, rid):
        c = self.con()
        try:
            from api.services.life_record.writer import _Tx
            return _Tx(c, NORA, "t").view(f"relationships/{rid}")
        finally:
            c.close()

    def test_a_refused_record_write_leaves_the_graph_untouched(self):
        self.family()
        before, rev = self.projected(), self.graph()["revision"]
        r = self.write([self.name("p-tom", "n-x", "X"),
                        self.assertion("bad", "person", "p-tom", "person.not_a_concept", 1)])
        self.assertFalse(r["ok"])
        self.assertEqual((self.projected(), self.graph()["revision"]), (before, rev))


class RevisionGuard(_Graph):
    def test_get_returns_a_revision_and_every_writer_bumps_it(self):
        revs = [self.graph()["revision"]]
        _db.graph_upsert_person(NORA, "ui-a", display_name="A"); revs.append(self.graph()["revision"])
        _db.graph_upsert_person(NORA, "ui-b", display_name="B"); revs.append(self.graph()["revision"])
        _db.graph_upsert_relationship(NORA, "ui-r", "ui-a", "ui-b", "sibling_of")
        revs.append(self.graph()["revision"])
        _db.graph_delete_relationship("ui-r"); revs.append(self.graph()["revision"])
        _db.graph_delete_person("ui-b"); revs.append(self.graph()["revision"])
        g = self.graph()
        _db.graph_replace_full(NORA, g["persons"], g["relationships"], expected_revision=g["revision"])
        revs.append(self.graph()["revision"])
        self.ok([self.name(NORA, "n1", "Nora Whitfield")]); revs.append(self.graph()["revision"])
        self.assertEqual(revs, list(range(8)), "all six graph writers move the revision")

    def test_a_stale_full_replacement_is_refused_and_writes_nothing(self):
        _db.graph_upsert_person(NORA, "ui-a", display_name="Ada")
        stale = self.graph()
        _db.graph_upsert_person(NORA, "ui-b", display_name="Bea")      # another tab's edit
        with self.assertRaises(_db.GraphRevisionConflict) as cm:
            _db.graph_replace_full(NORA, stale["persons"], stale["relationships"],
                                   expected_revision=stale["revision"])
        self.assertEqual(cm.exception.current, stale["revision"] + 1)
        self.assertIn("ui-b", {p["id"] for p in self.graph()["persons"]}, "the newer edit survives")

    def test_a_replacement_with_no_baseline_is_refused(self):
        with self.assertRaises(_db.GraphRevisionConflict):
            _db.graph_replace_full(NORA, [], [], expected_revision=None)

    def test_revisions_are_per_narrator(self):
        _db.graph_upsert_person(NORA, "ui-a", display_name="Ada")
        self.assertEqual((self.graph(NORA)["revision"], self.graph(OWEN)["revision"]), (1, 0))


class ProjectedRowsAreNotEditableHere(_Graph):
    def setUp(self):
        super().setUp()
        self.family()
        self.g = self.graph()

    def put(self, persons=None, rels=None):
        return _db.graph_replace_full(NORA, self.g["persons"] if persons is None else persons,
                                      self.g["relationships"] if rels is None else rels,
                                      expected_revision=self.g["revision"])

    def test_a_faithful_round_trip_is_accepted_and_keeps_the_projection(self):
        before = self.projected()
        self.put()
        self.assertEqual(self.projected(), before)

    def test_editing_a_projected_person_is_refused(self):
        persons = [dict(p, display_name="Someone Else") if p["id"] == "lr:p-ada" else p
                   for p in self.g["persons"]]
        with self.assertRaises(_db.GraphWriteRefused):
            self.put(persons=persons)
        ada = {x["id"]: x for x in self.projected()["persons"]}["lr:p-ada"]
        self.assertEqual(ada["display_name"], "Ada May Whitfield")

    def test_dropping_a_projected_row_is_refused(self):
        with self.assertRaises(_db.GraphWriteRefused):
            self.put(rels=[r for r in self.g["relationships"] if r["id"] != "lr:r-ada"])

    def test_forging_a_projected_row_is_refused(self):
        for forged in ({"id": "ui-x", "source": "life_record"}, {"id": "lr:p-fake"}):
            with self.assertRaises(_db.GraphWriteRefused):
                self.put(persons=self.g["persons"] + [forged])

    def test_incremental_routes_cannot_touch_projected_rows(self):
        with self.assertRaises(_db.GraphWriteRefused):
            _db.graph_upsert_person(NORA, "lr:p-ada", display_name="X")
        with self.assertRaises(_db.GraphWriteRefused):
            _db.graph_delete_person("lr:p-tom")
        with self.assertRaises(_db.GraphWriteRefused):
            _db.graph_delete_relationship("lr:r-ada")


class GraphNarratorIsolation(_Graph):
    def test_another_narrators_node_cannot_be_overwritten_or_linked(self):
        _db.graph_upsert_person(NORA, "ui-ada", display_name="Ada")
        with self.assertRaises(_db.GraphWriteRefused):
            _db.graph_upsert_person(OWEN, "ui-ada", display_name="Hijacked")
        _db.graph_upsert_person(OWEN, "ui-owen-dad", display_name="Carl")
        with self.assertRaises(_db.GraphWriteRefused):
            _db.graph_upsert_relationship(OWEN, "ui-r", "ui-owen-dad", "ui-ada", "spouse_of")
        with self.assertRaises(_db.GraphWriteRefused):
            _db.graph_replace_full(OWEN, [{"id": "ui-ada", "display_name": "Hijacked"}], [],
                                   expected_revision=self.graph(OWEN)["revision"])
        self.assertEqual(self.graph(NORA)["persons"][0]["display_name"], "Ada")


@unittest.skipUnless(_HAVE_FASTAPI, "fastapi is not importable under this interpreter")
class GraphRoutes(_Graph):
    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(_rel_router.router)
        self.client = TestClient(app)

    def test_put_statuses(self):
        url = f"/api/graph/{NORA}"
        g = self.client.get(url).json()
        self.assertEqual(g["revision"], 0)
        self.assertEqual(self.client.put(url, json={"persons": [], "relationships": []}).status_code, 428)
        ok = self.client.put(url, json={"persons": [{"id": "ui-a", "display_name": "A"}],
                                        "relationships": [], "revision": 0})
        self.assertEqual((ok.status_code, ok.json()["revision"]), (200, 1))
        stale = self.client.put(url, json={"persons": [], "relationships": [], "revision": 0})
        self.assertEqual((stale.status_code, stale.json()["detail"]["revision"]), (409, 1))
        forged = self.client.put(url, json={"persons": [{"id": "lr:x"}], "relationships": [],
                                            "revision": 1})
        self.assertEqual(forged.status_code, 422)


@unittest.skipUnless(_HAVE_FASTAPI, "fastapi is not importable under this interpreter")
class LifeRecordRoutes(_Graph):
    def setUp(self):
        super().setUp()
        from api.routers import life_record as _lr_router
        app = FastAPI()
        app.include_router(_lr_router.router)
        self.client = TestClient(app)
        self.url = f"/api/life-record/{NORA}"

    def patch(self, changes, base=None):
        return self.client.patch(self.url, json={"baseRevision": base, "actor": "operator:test",
                                                 "changes": changes})

    def test_get_patch_conflict_refusal_and_unknown_narrator(self):
        self.assertEqual(self.client.get(self.url).json()["revision"], 0)
        self.assertEqual(self.count("lr_record"), 0, "GET wrote nothing")
        ok = self.patch([self.name(NORA, "n1", "Nora Whitfield")])
        self.assertEqual((ok.status_code, ok.json()["revision"]), (200, 1))
        stale = self.patch([{"op": "set", "path": f"people/{NORA}/names/n1",
                             "value": {"fullText": "X"}, "expectedPrevious": {"fullText": "Old"}}], base=0)
        self.assertEqual((stale.status_code, stale.json()["detail"]["conflict"][0]["path"]),
                         (409, f"people/{NORA}/names/n1"))
        bad = self.patch([self.assertion("a", "person", NORA, "person.not_a_concept", 1)])
        self.assertEqual(bad.status_code, 422)
        self.assertEqual(self.client.get("/api/life-record/nobody").status_code, 404)


if __name__ == "__main__":
    unittest.main()
