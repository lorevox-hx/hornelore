"""WO-TRAVEL-DOC-SOURCES-01 — trip_sources documents lane (JSON path)."""
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


def _src_create_req(**kw):
    base = dict(source_type="hotel", title=None, trip_region_id=None,
               trip_stop_id=None, pasted_text=None, link_url=None,
               source_date=None, summary=None, include_in_memoir=False)
    base.update(kw)
    return _Req(**base)


def _src_patch_req(**kw):
    base = dict(source_type=None, title=None, pasted_text=None, link_url=None,
               source_date=None, summary=None, include_in_memoir=None, ord=None)
    base.update(kw)
    return _Req(**base)


class _SourcesCase(unittest.TestCase):
    def setUp(self):
        self._tmpdb = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self._tmpdb.close()
        self.db_path = Path(self._tmpdb.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()
        self._orig_flag = os.environ.get("HORNELORE_TRIPS")
        os.environ["HORNELORE_TRIPS"] = "1"
        self.person_id = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        con.execute("INSERT INTO people (id, display_name, date_of_birth, "
                    "created_at, updated_at) VALUES (?, 'S', '1962-12-24', "
                    "'2026-07-08', '2026-07-08');", (self.person_id,))
        con.commit(); con.close()
        self.trip_id = trip_repository.trip_create(self.person_id, "Trip")
        self.region_id = trip_repository.region_create(self.trip_id, "Germany")
        self.stop_id = trip_repository.stop_create(self.trip_id, self.region_id, "Munich")
        self.other_trip = trip_repository.trip_create(self.person_id, "Other")
        self.other_stop = trip_repository.stop_create(
            self.other_trip, trip_repository.region_create(self.other_trip, "R"), "X")

    def tearDown(self):
        _db.DB_PATH = self._orig_db
        if self._orig_flag is None:
            os.environ.pop("HORNELORE_TRIPS", None)
        else:
            os.environ["HORNELORE_TRIPS"] = self._orig_flag
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def test_table_exists(self):
        con = sqlite3.connect(str(self.db_path))
        cols = {r[1] for r in con.execute("PRAGMA table_info(trip_sources)")}
        con.close()
        for c in ("source_type", "pasted_text", "link_url", "storage_path",
                  "include_in_memoir"):
            self.assertIn(c, cols)

    def test_create_and_scope_filter(self):
        trips.create_source(self.trip_id, _src_create_req(
            source_type="note", pasted_text="trip level note"))
        trips.create_source(self.trip_id, _src_create_req(
            source_type="hotel", title="Munich hotel", trip_region_id=self.region_id,
            trip_stop_id=self.stop_id, link_url="http://hotel"))
        allrows = trips.list_sources(self.trip_id)["sources"]
        self.assertEqual(len(allrows), 2)
        stop_rows = trips.list_sources(self.trip_id, stop_id=self.stop_id)["sources"]
        self.assertEqual([s["title"] for s in stop_rows], ["Munich hotel"])

    def test_create_requires_content(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.create_source(self.trip_id, _src_create_req())
        self.assertEqual(ctx.exception.status_code, 422)

    def test_create_bad_source_type(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.create_source(self.trip_id, _src_create_req(
                source_type="bogus", pasted_text="x"))
        self.assertEqual(ctx.exception.status_code, 422)

    def test_create_rejects_foreign_stop(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.create_source(self.trip_id, _src_create_req(
                pasted_text="x", trip_stop_id=self.other_stop))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_default_flag_off(self):
        out = trips.create_source(self.trip_id, _src_create_req(pasted_text="x"))
        self.assertEqual(out["source"]["include_in_memoir"], 0)

    def test_patch_promote_and_delete(self):
        out = trips.create_source(self.trip_id, _src_create_req(pasted_text="x"))
        sid = out["source_id"]
        res = trips.patch_source(sid, _src_patch_req(include_in_memoir=True,
                                                     summary="a receipt"))
        self.assertEqual(res["source"]["include_in_memoir"], 1)
        self.assertEqual(res["source"]["summary"], "a receipt")
        # WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01: DELETE now soft-hides —
        # row preserved (promotion flag intact), restorable; a physical
        # purge needs the exact-id confirmation.
        hide = trips.delete_source(sid)
        self.assertTrue(hide["hidden"])
        self.assertFalse(hide["purged"])
        row = trip_repository.source_get(sid)
        self.assertIsNotNone(row)
        self.assertEqual(row["hidden"], 1)
        self.assertEqual(row["include_in_memoir"], 1)   # hide != un-promote
        purge = trips.delete_source(sid, purge=True, confirm_id=sid)
        self.assertTrue(purge["purged"])
        self.assertIsNone(trip_repository.source_get(sid))

    def test_delete_unknown_404(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.delete_source("nope")
        self.assertEqual(ctx.exception.status_code, 404)


    def test_promoted_source_in_memoir_preview(self):
        trips.create_source(self.trip_id, _src_create_req(
            source_type="hotel", title="Munich hotel", summary="2 nights",
            trip_region_id=self.region_id, trip_stop_id=self.stop_id,
            include_in_memoir=True))
        trips.create_source(self.trip_id, _src_create_req(
            source_type="receipt", pasted_text="private receipt",
            trip_region_id=self.region_id, trip_stop_id=self.stop_id,
            include_in_memoir=False))
        preview = trip_repository.trip_memoir_preview(self.trip_id)
        stop = preview["part_one_journey_in_order"][0]["stops"][0]
        titles = [x.get("title") for x in stop["sources"]]
        self.assertIn("Munich hotel", titles)
        # un-promoted source absent
        texts = [x.get("pasted_text") for x in stop["sources"]]
        self.assertNotIn("private receipt", texts)


if __name__ == "__main__":
    unittest.main()
