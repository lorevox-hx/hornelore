"""WO-TRAVEL-DOC-EDITABLE-ITINERARY-TILES-01 — review cleanup pass.

Locks the five bugs found in the 2026-07-07 review:
  1. clearing optional trip/region/stop fields (blank must actually erase)
  2. child stop ord computed from the parent's sibling group, not the
     region's top-level count
  3. moving a stop across regions updates its photo links' trip_region_id
  4. moving a stop renumbers BOTH the old and new sibling groups
  5. deleting a parent stop promotes children AND renumbers the region's
     top-level group so promoted children don't collide on ord

Exercised through the fastapi/pydantic stubs (offline pattern).
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import types
import unittest
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

if "fastapi" not in sys.modules:
    stub = types.ModuleType("fastapi")

    class _APIRouter:
        def __init__(self, *a, **k):
            pass

        def _deco(self, *a, **k):
            def wrap(f):
                return f
            return wrap
        get = post = patch = delete = put = _deco

    class _HTTPException(Exception):
        def __init__(self, status_code=0, detail=""):
            self.status_code, self.detail = status_code, detail
            super().__init__(detail)

    stub.APIRouter = _APIRouter
    stub.HTTPException = _HTTPException
    stub.Query = lambda default=None, **k: default
    stub.File = lambda default=None, **k: default
    stub.Form = lambda default=None, **k: default
    stub.UploadFile = object
    sys.modules["fastapi"] = stub

if "pydantic" not in sys.modules:
    pstub = types.ModuleType("pydantic")

    class _BaseModel:
        pass

    pstub.BaseModel = _BaseModel
    pstub.Field = lambda default=None, **k: default
    pstub.field_validator = lambda *a, **k: (lambda f: f)
    pstub.validator = lambda *a, **k: (lambda f: f)
    pstub.ConfigDict = dict
    sys.modules["pydantic"] = pstub

from api import db as _db  # noqa: E402
from api.services import trip_repository  # noqa: E402
from api.routers import trips  # noqa: E402


class _Req:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _stop_create_req(**kw):
    base = dict(location_name="Stop", stop_type="sight",
               parent_trip_stop_id=None, date_start=None, date_end=None,
               latitude=None, longitude=None, title=None, notes=None,
               thematic_tags=None, ord=None)
    base.update(kw)
    return _Req(**base)


def _stop_patch_req(**kw):
    base = dict(location_name=None, stop_type=None, date_start=None,
               date_end=None, latitude=None, longitude=None, title=None,
               notes=None, thematic_tags=None, clear_dates=False,
               clear_start_date=False, clear_end_date=False,
               clear_notes=False, ord=None, parent_trip_stop_id=None,
               clear_parent=False)
    base.update(kw)
    return _Req(**base)


def _region_patch_req(**kw):
    base = dict(title=None, country_or_area=None, start_date=None,
               end_date=None, summary=None, base_address=None, ord=None,
               clear_country_or_area=False, clear_start_date=False,
               clear_end_date=False, clear_summary=False,
               clear_base_address=False)
    base.update(kw)
    return _Req(**base)


def _trip_patch_req(**kw):
    base = dict(title=None, start_date=None, end_date=None, summary=None,
               clear_start_date=False, clear_end_date=False,
               clear_summary=False)
    base.update(kw)
    return _Req(**base)


class _EditableFixesCase(unittest.TestCase):
    def setUp(self):
        self._tmpdb = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self._tmpdb.close()
        self.db_path = Path(self._tmpdb.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()
        self._orig_trips_flag = os.environ.get("HORNELORE_TRIPS")
        os.environ["HORNELORE_TRIPS"] = "1"
        self._orig_sync = trips.trip_timeline_bridge.sync_trip_to_life_record
        trips.trip_timeline_bridge.sync_trip_to_life_record = lambda *a, **k: None

        self.person_id = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO people (id, display_name, date_of_birth, created_at, "
            "updated_at) VALUES (?, 'Fix Test', '1962-12-24', "
            "'2026-07-07', '2026-07-07');",
            (self.person_id,),
        )
        con.commit()
        con.close()

        self.trip_id = trip_repository.trip_create(
            person_id=self.person_id, title="Spring 2026",
            start_date="2026-05-01", end_date="2026-05-10", summary="s")
        self.czechia = trip_repository.region_create(
            self.trip_id, "Czechia", ord_=0,
            country_or_area="Czechia", base_address="Hotel Prague")
        self.austria = trip_repository.region_create(
            self.trip_id, "Austria", ord_=1)
        self.prague = trip_repository.stop_create(
            self.trip_id, self.czechia, "Prague", ord_=0, notes="old note",
            date_start="2026-05-02", date_end="2026-05-04")
        self.salzburg = trip_repository.stop_create(
            self.trip_id, self.czechia, "Salzburg", ord_=1)
        self.graz = trip_repository.stop_create(
            self.trip_id, self.czechia, "Graz", ord_=2)

    def tearDown(self):
        trips.trip_timeline_bridge.sync_trip_to_life_record = self._orig_sync
        _db.DB_PATH = self._orig_db
        if self._orig_trips_flag is None:
            os.environ.pop("HORNELORE_TRIPS", None)
        else:
            os.environ["HORNELORE_TRIPS"] = self._orig_trips_flag
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def _raw_ords(self, region_id, parent=None):
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        if parent is None:
            rows = con.execute(
                "SELECT ord FROM trip_stops WHERE trip_region_id=? "
                "AND parent_trip_stop_id IS NULL ORDER BY ord", (region_id,)).fetchall()
        else:
            rows = con.execute(
                "SELECT ord FROM trip_stops WHERE trip_region_id=? "
                "AND parent_trip_stop_id=? ORDER BY ord", (region_id, parent)).fetchall()
        con.close()
        return [r["ord"] for r in rows]

    # ── Bug 1: clearing fields ───────────────────────────────────────────

    def test_clear_trip_fields(self):
        trips.patch_trip(self.trip_id, _trip_patch_req(
            title="Spring 2026", clear_end_date=True, clear_summary=True))
        trip = trip_repository.trip_get(self.trip_id)
        self.assertEqual(trip["start_date"], "2026-05-01")  # untouched
        self.assertIsNone(trip["end_date"])
        self.assertIsNone(trip["summary"])

    def test_clear_region_fields(self):
        trips.patch_region(self.czechia, _region_patch_req(
            title="Czechia", clear_base_address=True,
            clear_country_or_area=True))
        region = trip_repository.trip_tree(self.trip_id)["regions"][0]
        self.assertIsNone(region["base_address"])
        self.assertIsNone(region["country_or_area"])

    def test_clear_stop_fields(self):
        trips.patch_stop(self.prague, _stop_patch_req(
            location_name="Prague", clear_dates=True, clear_notes=True))
        stop = trip_repository.stop_get(self.prague)
        self.assertIsNone(stop["date_start"])
        self.assertIsNone(stop["date_end"])
        self.assertIsNone(stop["notes"])

    def test_non_clear_leaves_field(self):
        # Blank field WITHOUT a clear flag must not erase (None-means-unchanged).
        trips.patch_stop(self.prague, _stop_patch_req(location_name="Prague"))
        stop = trip_repository.stop_get(self.prague)
        self.assertEqual(stop["notes"], "old note")
        self.assertEqual(stop["date_start"], "2026-05-02")

    # ── Bug 2: child stop ord ────────────────────────────────────────────

    def test_child_stop_ord_from_sibling_group(self):
        # Two day-trips under Prague. Region has 3 top-level stops, so the
        # OLD bug gave both children ord=3. Fix scopes to the parent group.
        trips.create_stop(self.trip_id, self.czechia, _stop_create_req(
            location_name="Kutna Hora", parent_trip_stop_id=self.prague,
            stop_type="day_trip"))
        trips.create_stop(self.trip_id, self.czechia, _stop_create_req(
            location_name="Karlstejn", parent_trip_stop_id=self.prague,
            stop_type="day_trip"))
        self.assertEqual(self._raw_ords(self.czechia, self.prague), [0, 1])

    # ── Bug 3: move updates photo-link region ────────────────────────────

    def test_move_updates_photo_link_region(self):
        lid = trip_repository.photo_link_upsert(
            self.trip_id, "photo-1", trip_region_id=self.czechia,
            trip_stop_id=self.prague, assignment_method="operator")
        trips.move_stop(self.trip_id, self.prague, _Req(
            region_id=self.austria, parent_trip_stop_id=None,
            before_stop_id=None, after_stop_id=None))
        link = trip_repository.photo_link_get(lid)
        self.assertEqual(link["trip_region_id"], self.austria)
        self.assertEqual(link["trip_stop_id"], self.prague)

    # ── Bug 4: move renumbers old + new group ────────────────────────────

    def test_move_renumbers_old_and_new_group(self):
        # Graz (czechia idx2) -> austria. Old group must close its gap; new
        # group must be clean too.
        trips.move_stop(self.trip_id, self.graz, _Req(
            region_id=self.austria, parent_trip_stop_id=None,
            before_stop_id=None, after_stop_id=None))
        old = self._raw_ords(self.czechia)
        new = self._raw_ords(self.austria)
        self.assertEqual(old, list(range(len(old))))  # 0..n, no gap
        self.assertEqual(new, list(range(len(new))))
        self.assertEqual(len(old), 2)  # Prague, Salzburg
        self.assertEqual(len(new), 1)  # Graz

    # ── Bug 5: delete parent promotes + renumbers ────────────────────────

    def test_delete_parent_promotes_and_renumbers(self):
        # Nest a day-trip (ord 0) under Prague (a top-level ord-0 stop),
        # then delete Prague. The child promotes to top level; without the
        # fix its ord=0 collides with Salzburg's promoted position.
        child = trip_repository.stop_create(
            self.trip_id, self.czechia, "Kutna Hora",
            parent_trip_stop_id=self.prague, ord_=0, stop_type="day_trip")
        trips.delete_stop(self.prague)
        ords = self._raw_ords(self.czechia)
        # Clean 0..n, no duplicates.
        self.assertEqual(ords, list(range(len(ords))))
        self.assertEqual(len(set(ords)), len(ords))
        # Salzburg, Graz, and promoted Kutna Hora remain (Prague gone).
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        names = [r["location_name"] for r in con.execute(
            "SELECT location_name FROM trip_stops WHERE trip_region_id=? "
            "AND parent_trip_stop_id IS NULL ORDER BY ord", (self.czechia,))]
        con.close()
        self.assertIn("Kutna Hora", names)
        self.assertNotIn("Prague", names)
        self.assertEqual(len(names), 3)


    # ── Subtree move: a parent moves as a unit (review 2026-07-07) ───────

    def test_move_parent_moves_children_region(self):
        # Nest Kutna Hora under Prague, link a photo to the CHILD, then move
        # Prague to Austria. The child's region + its photo link must follow.
        child = trip_repository.stop_create(
            self.trip_id, self.czechia, "Kutna Hora",
            parent_trip_stop_id=self.prague, ord_=0, stop_type="day_trip")
        child_link = trip_repository.photo_link_upsert(
            self.trip_id, "photo-child", trip_region_id=self.czechia,
            trip_stop_id=child, assignment_method="operator")
        trips.move_stop(self.trip_id, self.prague, _Req(
            region_id=self.austria, parent_trip_stop_id=None,
            before_stop_id=None, after_stop_id=None))
        moved_parent = trip_repository.stop_get(self.prague)
        moved_child = trip_repository.stop_get(child)
        self.assertEqual(moved_parent["trip_region_id"], self.austria)
        # Child follows the parent to the new region...
        self.assertEqual(moved_child["trip_region_id"], self.austria)
        # ...but stays parented under it (subtree shape preserved).
        self.assertEqual(moved_child["parent_trip_stop_id"], self.prague)
        # ...and the descendant's photo link follows too.
        link = trip_repository.photo_link_get(child_link)
        self.assertEqual(link["trip_region_id"], self.austria)

    def test_move_parent_moves_grandchildren_region(self):
        # Two levels deep: Prague > Kutna Hora > Sedlec. Move Prague; the
        # whole subtree lands in Austria.
        child = trip_repository.stop_create(
            self.trip_id, self.czechia, "Kutna Hora",
            parent_trip_stop_id=self.prague, ord_=0, stop_type="day_trip")
        grand = trip_repository.stop_create(
            self.trip_id, self.czechia, "Sedlec Ossuary",
            parent_trip_stop_id=child, ord_=0, stop_type="sight")
        trips.move_stop(self.trip_id, self.prague, _Req(
            region_id=self.austria, parent_trip_stop_id=None,
            before_stop_id=None, after_stop_id=None))
        self.assertEqual(
            trip_repository.stop_get(grand)["trip_region_id"], self.austria)

    def test_move_within_region_leaves_child_region(self):
        # No region change (re-order/reparent within Czechia) must NOT rewrite
        # child regions.
        child = trip_repository.stop_create(
            self.trip_id, self.czechia, "Kutna Hora",
            parent_trip_stop_id=self.prague, ord_=0, stop_type="day_trip")
        trips.move_stop(self.trip_id, self.prague, _Req(
            region_id=self.czechia, parent_trip_stop_id=None,
            before_stop_id=self.graz, after_stop_id=None))
        self.assertEqual(
            trip_repository.stop_get(child)["trip_region_id"], self.czechia)

    # ── Per-date stop clears ─────────────────────────────────────────────

    def test_clear_only_start_date(self):
        trips.patch_stop(self.prague, _stop_patch_req(
            location_name="Prague", clear_start_date=True))
        stop = trip_repository.stop_get(self.prague)
        self.assertIsNone(stop["date_start"])
        self.assertEqual(stop["date_end"], "2026-05-04")  # kept

    def test_clear_only_end_date(self):
        trips.patch_stop(self.prague, _stop_patch_req(
            location_name="Prague", clear_end_date=True))
        stop = trip_repository.stop_get(self.prague)
        self.assertEqual(stop["date_start"], "2026-05-02")  # kept
        self.assertIsNone(stop["date_end"])


    # ── Region patch triggers life-record sync (review 2026-07-07) ──────

    def test_patch_region_syncs_life_record(self):
        calls = []
        trips.trip_timeline_bridge.sync_trip_to_life_record = \
            lambda tid, *a, **k: calls.append(tid)
        trips.patch_region(self.czechia, _region_patch_req(title="Bohemia"))
        self.assertIn(self.trip_id, calls)


if __name__ == "__main__":
    unittest.main()
