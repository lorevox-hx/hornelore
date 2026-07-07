"""WO-TRAVEL-DOC-EDITABLE-ITINERARY-TILES-01 — backend reorder/move.

Covers the three new trip endpoints that give the operator explicit route
authority via the existing ``ord`` column:

    POST /api/trips/{trip_id}/regions/reorder
    POST /api/trips/{trip_id}/stops/reorder
    POST /api/trips/{trip_id}/stops/{stop_id}/move

Behavior locked here:
  - reorder renumbers siblings cleanly 0,1,2… (no shared/gapped ord)
  - stop siblings = same trip + same region + same parent
  - reorder rejects incomplete / foreign / duplicate id sets
  - move across regions rewrites region + parent + sibling ord atomically
  - move validates ownership, parent placement, and cycle protection
  - tree read reflects the new order (memoir preview reads the same tree)

Endpoints are exercised through the fastapi/pydantic stubs (same offline
pattern as tests/test_trip_stop_upload.py) — the router functions are
plain callables, so we hand them duck-typed request objects.
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

# Minimal fastapi stub — decorators return the function unchanged so the
# router endpoints are directly callable.
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

from fastapi import HTTPException  # noqa: E402  (our stub)
from api import db as _db  # noqa: E402
from api.services import trip_repository  # noqa: E402
from api.routers import trips  # noqa: E402


class _Req:
    """Duck-typed request object (stand-in for the pydantic models)."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


class _ReorderMoveCase(unittest.TestCase):
    def setUp(self):
        self._tmpdb = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self._tmpdb.close()
        self.db_path = Path(self._tmpdb.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()
        self._orig_trips_flag = os.environ.get("HORNELORE_TRIPS")
        os.environ["HORNELORE_TRIPS"] = "1"

        # trip_timeline_bridge.sync_trip_to_life_record touches other tables;
        # neutralize it so these tests isolate the reorder/move behavior.
        self._orig_sync = trips.trip_timeline_bridge.sync_trip_to_life_record
        trips.trip_timeline_bridge.sync_trip_to_life_record = lambda *a, **k: None

        self.person_id = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO people (id, display_name, date_of_birth, created_at, "
            "updated_at) VALUES (?, 'Reorder Test', '1962-12-24', "
            "'2026-07-07', '2026-07-07');",
            (self.person_id,),
        )
        con.commit()
        con.close()

        self.trip_id = trip_repository.trip_create(
            person_id=self.person_id, title="Spring 2026 Europe",
        )
        # Two regions.
        self.czechia = trip_repository.region_create(
            self.trip_id, "Czechia", ord_=0)
        self.austria = trip_repository.region_create(
            self.trip_id, "Austria", ord_=1)
        # Top-level stops in Czechia: Prague(0), Salzburg(1), Graz(2).
        self.prague = trip_repository.stop_create(
            self.trip_id, self.czechia, "Prague", ord_=0)
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

    # ── helpers ────────────────────────────────────────────────────────────

    def _top_stops(self, region_id):
        """Top-level stop names for a region, in tree (ord) order."""
        tree = trip_repository.trip_tree(self.trip_id)
        region = next(r for r in tree["regions"] if r["id"] == region_id)
        return [s["location_name"] for s in region["stops"]]

    def _region_titles(self):
        tree = trip_repository.trip_tree(self.trip_id)
        return [r["title"] for r in tree["regions"]]

    def _raw_ords(self, region_id, parent=None):
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        if parent is None:
            rows = con.execute(
                "SELECT ord FROM trip_stops WHERE trip_region_id=? "
                "AND parent_trip_stop_id IS NULL ORDER BY ord",
                (region_id,)).fetchall()
        else:
            rows = con.execute(
                "SELECT ord FROM trip_stops WHERE trip_region_id=? "
                "AND parent_trip_stop_id=? ORDER BY ord",
                (region_id, parent)).fetchall()
        con.close()
        return [r["ord"] for r in rows]

    # ── region reorder ──────────────────────────────────────────────────────

    def test_region_reorder(self):
        self.assertEqual(self._region_titles(), ["Czechia", "Austria"])
        out = trips.reorder_regions(
            self.trip_id, _Req(ordered_ids=[self.austria, self.czechia]))
        self.assertTrue(out["ok"])
        self.assertEqual(self._region_titles(), ["Austria", "Czechia"])

    def test_region_reorder_rejects_incomplete_set(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.reorder_regions(self.trip_id, _Req(ordered_ids=[self.austria]))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_region_reorder_rejects_foreign_id(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.reorder_regions(
                self.trip_id,
                _Req(ordered_ids=[self.austria, self.czechia, "not-a-region"]))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_region_reorder_unknown_trip_404(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.reorder_regions("no-such-trip", _Req(ordered_ids=[]))
        self.assertEqual(ctx.exception.status_code, 404)

    # ── stop reorder ────────────────────────────────────────────────────────

    def test_stop_reorder_within_region(self):
        # Move Graz above Salzburg -> Prague, Graz, Salzburg.
        out = trips.reorder_stops(self.trip_id, _Req(
            region_id=self.czechia, parent_trip_stop_id=None,
            ordered_ids=[self.prague, self.graz, self.salzburg]))
        self.assertTrue(out["ok"])
        self.assertEqual(self._top_stops(self.czechia),
                         ["Prague", "Graz", "Salzburg"])
        # ord is a clean 0,1,2 with no gaps/dupes.
        self.assertEqual(self._raw_ords(self.czechia), [0, 1, 2])

    def test_stop_reorder_rejects_partial_group(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.reorder_stops(self.trip_id, _Req(
                region_id=self.czechia, parent_trip_stop_id=None,
                ordered_ids=[self.prague, self.graz]))  # missing salzburg
        self.assertEqual(ctx.exception.status_code, 400)

    def test_stop_reorder_rejects_duplicate(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.reorder_stops(self.trip_id, _Req(
                region_id=self.czechia, parent_trip_stop_id=None,
                ordered_ids=[self.prague, self.prague, self.salzburg]))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_stop_reorder_unknown_region_404(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.reorder_stops(self.trip_id, _Req(
                region_id="nope", parent_trip_stop_id=None, ordered_ids=[]))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_child_reorder_scoped_to_parent(self):
        # Nest two day-trips under Prague.
        d1 = trip_repository.stop_create(
            self.trip_id, self.czechia, "Kutna Hora",
            parent_trip_stop_id=self.prague, ord_=0, stop_type="day_trip")
        d2 = trip_repository.stop_create(
            self.trip_id, self.czechia, "Karlstejn",
            parent_trip_stop_id=self.prague, ord_=1, stop_type="day_trip")
        trips.reorder_stops(self.trip_id, _Req(
            region_id=self.czechia, parent_trip_stop_id=self.prague,
            ordered_ids=[d2, d1]))
        tree = trip_repository.trip_tree(self.trip_id)
        region = next(r for r in tree["regions"] if r["id"] == self.czechia)
        prague = next(s for s in region["stops"] if s["id"] == self.prague)
        self.assertEqual([c["location_name"] for c in prague["children"]],
                         ["Karlstejn", "Kutna Hora"])
        # Top-level ords untouched.
        self.assertEqual(self._raw_ords(self.czechia), [0, 1, 2])

    # ── move ────────────────────────────────────────────────────────────────

    def test_move_insert_before_sibling(self):
        # Add Munich at the end, then move it before Prague.
        munich = trip_repository.stop_create(
            self.trip_id, self.czechia, "Munich", ord_=3)
        trips.move_stop(self.trip_id, munich, _Req(
            region_id=self.czechia, parent_trip_stop_id=None,
            before_stop_id=self.prague, after_stop_id=None))
        self.assertEqual(self._top_stops(self.czechia),
                         ["Munich", "Prague", "Salzburg", "Graz"])
        self.assertEqual(self._raw_ords(self.czechia), [0, 1, 2, 3])

    def test_move_insert_after_sibling(self):
        munich = trip_repository.stop_create(
            self.trip_id, self.czechia, "Munich", ord_=3)
        trips.move_stop(self.trip_id, munich, _Req(
            region_id=self.czechia, parent_trip_stop_id=None,
            before_stop_id=None, after_stop_id=self.prague))
        self.assertEqual(self._top_stops(self.czechia),
                         ["Prague", "Munich", "Salzburg", "Graz"])

    def test_move_across_regions_clears_to_top_level(self):
        # Move Graz from Czechia to Austria (no parent).
        trips.move_stop(self.trip_id, self.graz, _Req(
            region_id=self.austria, parent_trip_stop_id=None,
            before_stop_id=None, after_stop_id=None))
        self.assertEqual(self._top_stops(self.czechia), ["Prague", "Salzburg"])
        self.assertEqual(self._top_stops(self.austria), ["Graz"])
        # Source group renumbered clean.
        self.assertEqual(self._raw_ords(self.czechia), [0, 1])
        self.assertEqual(self._raw_ords(self.austria), [0])

    def test_move_under_parent_makes_child(self):
        # Make Graz a day-trip under Prague.
        trips.move_stop(self.trip_id, self.graz, _Req(
            region_id=self.czechia, parent_trip_stop_id=self.prague,
            before_stop_id=None, after_stop_id=None))
        tree = trip_repository.trip_tree(self.trip_id)
        region = next(r for r in tree["regions"] if r["id"] == self.czechia)
        self.assertEqual([s["location_name"] for s in region["stops"]],
                         ["Prague", "Salzburg"])
        prague = next(s for s in region["stops"] if s["id"] == self.prague)
        self.assertEqual([c["location_name"] for c in prague["children"]],
                         ["Graz"])

    def test_move_rejects_cycle(self):
        # Nest Salzburg under Prague, then try to move Prague under Salzburg.
        trips.move_stop(self.trip_id, self.salzburg, _Req(
            region_id=self.czechia, parent_trip_stop_id=self.prague,
            before_stop_id=None, after_stop_id=None))
        with self.assertRaises(HTTPException) as ctx:
            trips.move_stop(self.trip_id, self.prague, _Req(
                region_id=self.czechia, parent_trip_stop_id=self.salzburg,
                before_stop_id=None, after_stop_id=None))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_move_rejects_self_parent(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.move_stop(self.trip_id, self.prague, _Req(
                region_id=self.czechia, parent_trip_stop_id=self.prague,
                before_stop_id=None, after_stop_id=None))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_move_rejects_parent_in_other_region(self):
        # A stop in Austria can't parent a stop being moved into Czechia.
        vienna = trip_repository.stop_create(
            self.trip_id, self.austria, "Vienna", ord_=0)
        with self.assertRaises(HTTPException) as ctx:
            trips.move_stop(self.trip_id, self.prague, _Req(
                region_id=self.czechia, parent_trip_stop_id=vienna,
                before_stop_id=None, after_stop_id=None))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_move_unknown_stop_404(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.move_stop(self.trip_id, "no-such-stop", _Req(
                region_id=self.czechia, parent_trip_stop_id=None,
                before_stop_id=None, after_stop_id=None))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_move_rejects_foreign_before_sibling(self):
        vienna = trip_repository.stop_create(
            self.trip_id, self.austria, "Vienna", ord_=0)
        with self.assertRaises(HTTPException) as ctx:
            trips.move_stop(self.trip_id, self.graz, _Req(
                region_id=self.czechia, parent_trip_stop_id=None,
                before_stop_id=vienna, after_stop_id=None))
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
