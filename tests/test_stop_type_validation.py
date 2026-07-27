"""WO-TRIP-LANE-AUDIT-FIXPACK-01 (H1) — stop_type validation.

An off-enum stop_type must be rejected with a clean 422 (API) or
ValueError (import), never bubble up as an unhandled 500 from the DB
CHECK constraint. Offline fastapi/pydantic stub pattern (same as
tests/test_trip_editable_fixes.py).
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
        # 2026-07-27 (WO-POST-LORI-CLEANUP-AND-UNBLOCK-01, incidental):
        # a bare `pass` here satisfies `class X(BaseModel)` but not
        # `X(id=..., label=...)`. Whichever sibling test loaded FIRST
        # won the sys.modules race, so a suite that passed alone failed
        # in a batch run -- a test env making tests lie. Matches the
        # stub tests/test_memoir_trip_story_lane.py already ships.
        def __init__(self, **kw):
            for _k, _v in kw.items():
                setattr(self, _k, _v)

    pstub.BaseModel = _BaseModel
    def _field(default=None, default_factory=None, **k):
        if default_factory is not None:
            return default_factory()
        return default

    pstub.Field = _field
    pstub.field_validator = lambda *a, **k: (lambda f: f)
    pstub.validator = lambda *a, **k: (lambda f: f)
    pstub.ConfigDict = dict
    sys.modules["pydantic"] = pstub

from fastapi import HTTPException  # noqa: E402  (stub)
from api import db as _db  # noqa: E402
from api.services import trip_repository  # noqa: E402
from api.services import trip_import  # noqa: E402
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


class StopTypeValidationTest(unittest.TestCase):
    def setUp(self):
        self._tmpdb = tempfile.NamedTemporaryFile(
            suffix=".sqlite3", delete=False)
        self._tmpdb.close()
        self.db_path = Path(self._tmpdb.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()
        self._orig_flag = os.environ.get("HORNELORE_TRIPS")
        os.environ["HORNELORE_TRIPS"] = "1"
        self._orig_sync = trips.trip_timeline_bridge.sync_trip_to_life_record
        trips.trip_timeline_bridge.sync_trip_to_life_record = \
            lambda *a, **k: None

        self.person_id = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO people (id, display_name, date_of_birth, "
            "created_at, updated_at) VALUES (?, 'T', '1962-12-24', "
            "'2026-07-10', '2026-07-10');", (self.person_id,))
        con.commit()
        con.close()

        self.trip_id = trip_repository.trip_create(self.person_id, "Trip")
        self.region_id = trip_repository.region_create(self.trip_id, "Germany")

    def tearDown(self):
        trips.trip_timeline_bridge.sync_trip_to_life_record = self._orig_sync
        if self._orig_flag is None:
            os.environ.pop("HORNELORE_TRIPS", None)
        else:
            os.environ["HORNELORE_TRIPS"] = self._orig_flag
        _db.DB_PATH = self._orig_db
        try:
            self.db_path.unlink()
        except OSError:
            pass

    # --- enum drift guard ----------------------------------------------
    def test_stop_types_match_db_check(self):
        # The DB CHECK enum lives in migration 0015; keep STOP_TYPES in
        # sync with the values the schema actually accepts.
        con = sqlite3.connect(str(self.db_path))
        try:
            for st in trip_repository.STOP_TYPES:
                sid = str(uuid.uuid4())
                con.execute(
                    "INSERT INTO trip_stops (id, trip_id, trip_region_id, "
                    "location_name, stop_type) VALUES (?, ?, ?, ?, ?)",
                    (sid, self.trip_id, self.region_id, "X", st))
            con.commit()
        finally:
            con.close()

    # --- create --------------------------------------------------------
    def test_valid_create_succeeds(self):
        out = trips.create_stop(
            self.trip_id, self.region_id,
            _stop_create_req(location_name="Munich", stop_type="lodging"))
        self.assertIn("stop_id", out)

    def test_invalid_create_returns_422_not_500(self):
        with self.assertRaises(HTTPException) as cm:
            trips.create_stop(
                self.trip_id, self.region_id,
                _stop_create_req(location_name="Munich",
                                 stop_type="travel_day"))
        self.assertEqual(cm.exception.status_code, 422)

    # --- patch ---------------------------------------------------------
    def test_valid_patch_succeeds(self):
        sid = trips.create_stop(
            self.trip_id, self.region_id,
            _stop_create_req(location_name="Munich"))["stop_id"]
        out = trips.patch_stop(sid, _stop_patch_req(stop_type="transit"))
        self.assertTrue(out.get("ok"))

    def test_invalid_patch_returns_422_not_500(self):
        sid = trips.create_stop(
            self.trip_id, self.region_id,
            _stop_create_req(location_name="Munich"))["stop_id"]
        with self.assertRaises(HTTPException) as cm:
            trips.patch_stop(sid, _stop_patch_req(stop_type="city"))
        self.assertEqual(cm.exception.status_code, 422)

    def test_none_patch_stop_type_still_allowed(self):
        sid = trips.create_stop(
            self.trip_id, self.region_id,
            _stop_create_req(location_name="Munich"))["stop_id"]
        out = trips.patch_stop(sid, _stop_patch_req(title="Renamed"))
        self.assertTrue(out.get("ok"))

    # --- import --------------------------------------------------------
    def test_import_itinerary_rejects_invalid_stop_type(self):
        itin = {
            "title": "Bad Import",
            "regions": [{
                "title": "Germany",
                "stops": [{"location_name": "Munich",
                           "stop_type": "hotel"}],
            }],
        }
        with self.assertRaises(ValueError):
            trip_import.import_itinerary(self.person_id, itin)

    def test_import_itinerary_accepts_valid_stop_type(self):
        itin = {
            "title": "Good Import",
            "regions": [{
                "title": "Germany",
                "stops": [{"location_name": "Munich",
                           "stop_type": "lodging"}],
            }],
        }
        tid = trip_import.import_itinerary(self.person_id, itin)
        self.assertTrue(tid)

    def test_import_csv_rejects_invalid_stop_type(self):
        csv_text = (
            "region,location,stop_type\n"
            "Germany,Munich,not_a_type\n")
        with self.assertRaises(ValueError) as cm:
            trip_import.import_csv(self.person_id, csv_text, "CSV Trip")
        self.assertIn("stop_type", str(cm.exception))

    def test_import_csv_accepts_valid_stop_type(self):
        csv_text = (
            "region,location,stop_type\n"
            "Germany,Munich,memory_anchor\n")
        tid = trip_import.import_csv(self.person_id, csv_text, "CSV Trip")
        self.assertTrue(tid)


if __name__ == "__main__":
    unittest.main()
