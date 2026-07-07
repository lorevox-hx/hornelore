"""WO-TRAVEL-DOC-EDITABLE-ITINERARY-TILES-01 — trip-level PATCH.

Adds the missing trip edit endpoint (region + stop PATCH already existed):

    PATCH /api/trips/{trip_id}   {title?, start_date?, end_date?, summary?}

Partial patch: only supplied fields are written; unknown trip -> 404;
empty body -> 400. Exercised through the fastapi/pydantic stubs (same
offline pattern as the other trip tests).
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

from fastapi import HTTPException  # noqa: E402
from api import db as _db  # noqa: E402
from api.services import trip_repository  # noqa: E402
from api.routers import trips  # noqa: E402


class _Req:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _TripPatchCase(unittest.TestCase):
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
            "updated_at) VALUES (?, 'Patch Test', '1962-12-24', "
            "'2026-07-07', '2026-07-07');",
            (self.person_id,),
        )
        con.commit()
        con.close()
        self.trip_id = trip_repository.trip_create(
            person_id=self.person_id, title="Old Title",
            start_date="2026-05-01", end_date="2026-05-10", summary="old")

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

    def test_patch_all_fields(self):
        out = trips.patch_trip(self.trip_id, _Req(
            title="New Title", start_date="2026-05-22",
            end_date="2026-06-13", summary="new"))
        self.assertTrue(out["ok"])
        trip = trip_repository.trip_get(self.trip_id)
        self.assertEqual(trip["title"], "New Title")
        self.assertEqual(trip["start_date"], "2026-05-22")
        self.assertEqual(trip["end_date"], "2026-06-13")
        self.assertEqual(trip["summary"], "new")

    def test_partial_patch_leaves_others(self):
        trips.patch_trip(self.trip_id, _Req(
            title="Only Title", start_date=None, end_date=None, summary=None))
        trip = trip_repository.trip_get(self.trip_id)
        self.assertEqual(trip["title"], "Only Title")
        self.assertEqual(trip["start_date"], "2026-05-01")  # unchanged
        self.assertEqual(trip["summary"], "old")            # unchanged

    def test_empty_patch_400(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.patch_trip(self.trip_id, _Req(
                title=None, start_date=None, end_date=None, summary=None))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_unknown_trip_404(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.patch_trip("no-such-trip", _Req(
                title="x", start_date=None, end_date=None, summary=None))
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
