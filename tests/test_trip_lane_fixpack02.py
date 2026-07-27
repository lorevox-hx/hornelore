"""WO-TRIP-LANE-AUDIT-FIXPACK-02 — M1, M2, M3.

M1 — region_delete refuses when the region still has stops (preserving
     operator content); force=True is the explicit escape hatch; the
     route returns 409.
M2 — a turnless travel_doc_modal capture must NOT dedupe on the
     conv-level modal_turn:<conv>:- ref (would collapse later captures).
M3 — clustering time-score quarantine fails closed on missing/unknown/
     untrusted metadata_trust, usable only for full/time_only.
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
from api.services import trip_story_capture as tsc  # noqa: E402
from api.services.trip_photo_clustering import _photo_taken_dt  # noqa: E402
from api.routers import trips  # noqa: E402


# ─────────────────────────── M3 (pure) ────────────────────────────────
class M3ClusteringTrustTest(unittest.TestCase):
    def _dt(self, trust=None, key=True):
        p = {"taken_at": "2026-05-27 12:00:00"}
        if key:
            p["metadata_trust"] = trust
        return _photo_taken_dt(p)

    def test_full_and_time_only_are_usable(self):
        self.assertIsNotNone(self._dt("full"))
        self.assertIsNotNone(self._dt("time_only"))

    def test_untrusted_levels_blocked(self):
        for t in ("suspect_scan", "none", "gps_only", "unknown", ""):
            self.assertIsNone(self._dt(t), t)

    def test_missing_key_fails_closed(self):
        # narrow SELECT that omitted metadata_trust -> no date used
        self.assertIsNone(self._dt(key=False))

    def test_none_value_fails_closed(self):
        self.assertIsNone(self._dt(None))


# ───────────────────────── DB-backed cases ────────────────────────────
class _DbCase(unittest.TestCase):
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
        self._orig_story = os.environ.get("HORNELORE_STORY_CAPTURE")
        os.environ["HORNELORE_STORY_CAPTURE"] = "1"
        self._orig_sync = trips.trip_timeline_bridge.sync_trip_to_life_record
        trips.trip_timeline_bridge.sync_trip_to_life_record = \
            lambda *a, **k: None
        self.person_id = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO people (id, display_name, date_of_birth, "
            "created_at, updated_at) VALUES (?, 'P', '1962-12-24', "
            "'2026-07-10', '2026-07-10');", (self.person_id,))
        con.commit()
        con.close()
        self.trip_id = trip_repository.trip_create(
            self.person_id, "Spring 2026", start_date="2026-05-22",
            end_date="2026-06-13")
        self.region_id = trip_repository.region_create(self.trip_id, "Germany")

    def tearDown(self):
        trips.trip_timeline_bridge.sync_trip_to_life_record = self._orig_sync
        for k, v in (("HORNELORE_TRIPS", self._orig_flag),
                     ("HORNELORE_STORY_CAPTURE", self._orig_story)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        _db.DB_PATH = self._orig_db
        try:
            self.db_path.unlink()
        except OSError:
            pass


class M1RegionDeleteTest(_DbCase):
    def test_delete_refused_when_region_has_stops(self):
        trip_repository.stop_create(self.trip_id, self.region_id, "Munich")
        with self.assertRaises(trip_repository.RegionNotEmptyError):
            trip_repository.region_delete(self.region_id)
        # stop + region both survive the refusal
        tree = trip_repository.trip_tree(self.trip_id)
        self.assertEqual(len(tree["regions"]), 1)
        self.assertEqual(len(tree["regions"][0]["stops"]), 1)

    def test_force_deletes_region_with_stops(self):
        trip_repository.stop_create(self.trip_id, self.region_id, "Munich")
        self.assertTrue(
            trip_repository.region_delete(self.region_id, force=True))
        self.assertEqual(
            len(trip_repository.trip_tree(self.trip_id)["regions"]), 0)

    def test_empty_region_deletes_without_force(self):
        self.assertTrue(trip_repository.region_delete(self.region_id))

    def test_route_returns_409_when_region_has_stops(self):
        trip_repository.stop_create(self.trip_id, self.region_id, "Munich")
        with self.assertRaises(HTTPException) as cm:
            trips.delete_region(self.region_id)
        self.assertEqual(cm.exception.status_code, 409)

    def test_route_force_true_deletes(self):
        trip_repository.stop_create(self.trip_id, self.region_id, "Munich")
        out = trips.delete_region(self.region_id, force=True)
        self.assertTrue(out["ok"])


class M2ModalDedupeTest(_DbCase):
    def _capture(self, text, turn_id=None):
        return tsc.capture_trip_story_answer(
            person_id=self.person_id, active_trip_id=self.trip_id,
            narrator_text=text, source_surface="travel_doc_modal",
            assume_trip_scoped=True, conv_id="conv-1", turn_id=turn_id)

    def test_turnless_modal_captures_do_not_collapse(self):
        r1 = self._capture(
            "We wandered the old town for hours and it felt timeless.")
        r2 = self._capture(
            "The cathedral bells rang while we ate lunch by the river.")
        self.assertTrue(r1["captured"])
        self.assertTrue(r2["captured"])
        self.assertNotEqual(r2["reason"], "duplicate")
        notes = trip_repository.location_notes_list(self.trip_id)
        self.assertEqual(len(notes), 2)

    def test_real_turn_id_still_dedupes_on_repeat(self):
        text = "We wandered the old town for hours and it felt timeless."
        r1 = self._capture(text, turn_id="t-7")
        r2 = self._capture(text, turn_id="t-7")
        self.assertTrue(r1["captured"])
        self.assertEqual(r2["reason"], "duplicate")
        self.assertEqual(len(trip_repository.location_notes_list(self.trip_id)),
                         1)


if __name__ == "__main__":
    unittest.main()
