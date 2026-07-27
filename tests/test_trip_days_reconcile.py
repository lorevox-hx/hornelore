"""WO-TRAVEL-DOC-UI-LAB-03 — trip-day date-range reconcile tests.

Covers: reconcile-preview detects missing in-range dates and
out-of-range day cards after the trip's start/end dates change;
preview is strictly read-only; add_missing creates ONLY the missing
in-range days and never overwrites operator-edited rows;
mark_out_of_range stamps reconcile_status (migration 0029) while every
out-of-range day card — and all its content — is preserved. NOTHING in
the reconcile lane deletes trip_days rows, and no test here permits it.

Offline fastapi/pydantic stub pattern (same as tests/test_trip_days.py).
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

from fastapi import HTTPException  # noqa: E402
from api import db as _db  # noqa: E402
from api.services import trip_repository  # noqa: E402
from api.routers import trips  # noqa: E402


class _ReconcileReq:
    """TripDaysReconcileReq stand-in."""

    def __init__(self, add_missing=False, mark_out_of_range=False):
        self.add_missing = add_missing
        self.mark_out_of_range = mark_out_of_range


class _ReconcileCase(unittest.TestCase):
    def setUp(self):
        self._tmpdb = tempfile.NamedTemporaryFile(suffix=".sqlite3",
                                                  delete=False)
        self._tmpdb.close()
        self.db_path = Path(self._tmpdb.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()
        self._orig_trips_flag = os.environ.get("HORNELORE_TRIPS")
        os.environ["HORNELORE_TRIPS"] = "1"
        self._orig_sync = trips.trip_timeline_bridge.sync_trip_to_life_record
        trips.trip_timeline_bridge.sync_trip_to_life_record = \
            lambda *a, **k: None

        self.person_id = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO people (id, display_name, date_of_birth, "
            "created_at, updated_at) VALUES (?, 'Reconcile Test', "
            "'1962-12-24', '2026-07-10', '2026-07-10');",
            (self.person_id,),
        )
        con.commit()
        con.close()
        self.trip_id = trip_repository.trip_create(
            person_id=self.person_id, title="Reconcile Trip",
            start_date="2026-05-01", end_date="2026-05-05",
            summary="reconcile fixture")
        trips.generate_trip_days(self.trip_id)
        self.days = trip_repository.trip_days_list(self.trip_id)

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

    # ── helpers ───────────────────────────────────────────────────────

    def _dump_days(self):
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in con.execute(
                "SELECT * FROM trip_days WHERE trip_id = ? ORDER BY id",
                (self.trip_id,)).fetchall()]
        finally:
            con.close()


class ReconcilePreviewTest(_ReconcileCase):
    def test_clean_trip_previews_empty_diff(self):
        pv = trips.reconcile_preview_trip_days(self.trip_id)
        self.assertEqual(pv["trip_id"], self.trip_id)
        self.assertEqual(pv["trip_start_date"], "2026-05-01")
        self.assertEqual(pv["trip_end_date"], "2026-05-05")
        self.assertEqual(pv["existing_days"], 5)
        self.assertEqual(pv["missing_dates"], [])
        self.assertEqual(pv["out_of_range_days"], [])
        self.assertEqual(pv["duplicate_or_invalid_days"], [])

    def test_detects_missing_dates_after_dates_widen(self):
        trip_repository.trip_update(self.trip_id, end_date="2026-05-07")
        pv = trips.reconcile_preview_trip_days(self.trip_id)
        self.assertEqual(pv["missing_dates"], ["2026-05-06", "2026-05-07"])
        self.assertEqual(pv["out_of_range_days"], [])

    def test_detects_out_of_range_after_dates_shrink(self):
        trip_repository.trip_update(self.trip_id,
                                    start_date="2026-05-02",
                                    end_date="2026-05-04")
        pv = trips.reconcile_preview_trip_days(self.trip_id)
        self.assertEqual(pv["missing_dates"], [])
        oor = sorted(d["date"] for d in pv["out_of_range_days"])
        self.assertEqual(oor, ["2026-05-01", "2026-05-05"])

    def test_preview_is_strictly_read_only(self):
        trip_repository.trip_update(self.trip_id,
                                    start_date="2026-05-02",
                                    end_date="2026-05-07")
        before = self._dump_days()
        trips.reconcile_preview_trip_days(self.trip_id)
        trip_repository.trip_days_reconcile_preview(self.trip_id)
        self.assertEqual(before, self._dump_days(),
                         "reconcile-preview must never write")

    def test_no_date_window_reports_nothing(self):
        bare = trip_repository.trip_create(
            person_id=self.person_id, title="No Dates")
        pv = trips.reconcile_preview_trip_days(bare)
        self.assertEqual(pv["missing_dates"], [])
        self.assertEqual(pv["out_of_range_days"], [])
        self.assertIsNone(pv["trip_start_date"])

    def test_detects_invalid_day_date(self):
        con = sqlite3.connect(str(self.db_path))
        try:
            con.execute("UPDATE trip_days SET date = 'not-a-date' "
                        "WHERE id = ?", (self.days[2]["id"],))
            con.commit()
        finally:
            con.close()
        pv = trips.reconcile_preview_trip_days(self.trip_id)
        bad = [d["id"] for d in pv["duplicate_or_invalid_days"]]
        self.assertEqual(bad, [self.days[2]["id"]])
        # The unreadable-date row is reported, not touched.
        self.assertEqual(len(self._dump_days()), 5)

    def test_unknown_trip_404(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.reconcile_preview_trip_days("no-such-trip")
        self.assertEqual(ctx.exception.status_code, 404)


class ReconcileApplyTest(_ReconcileCase):
    def test_add_missing_creates_only_missing(self):
        trip_repository.trip_update(self.trip_id, end_date="2026-05-07")
        out = trips.reconcile_trip_days(self.trip_id,
                                        _ReconcileReq(add_missing=True))
        self.assertEqual(out["added"], 2)
        self.assertEqual(out["preview"]["missing_dates"], [])
        dates = [d["date"] for d in out["days"]]
        self.assertIn("2026-05-06", dates)
        self.assertIn("2026-05-07", dates)
        self.assertEqual(len(dates), 7)

    def test_add_missing_never_overwrites_operator_edits(self):
        trip_repository.trip_day_update(self.days[0]["id"],
                                        title="Arrival — operator edit",
                                        morning_notes="museum first thing")
        trip_repository.trip_update(self.trip_id, end_date="2026-05-06")
        trips.reconcile_trip_days(self.trip_id,
                                  _ReconcileReq(add_missing=True))
        kept = trip_repository.trip_day_get(self.days[0]["id"])
        self.assertEqual(kept["title"], "Arrival — operator edit")
        self.assertEqual(kept["morning_notes"], "museum first thing")

    def test_mark_out_of_range_sets_status_preserves_content(self):
        # Give the soon-to-be-outside day real content.
        trip_repository.trip_day_update(self.days[0]["id"],
                                        title="Precious first day",
                                        evening_notes="beer hall dinner")
        trip_repository.location_note_create(
            trip_id=self.trip_id, note_text="day-one story",
            source_type="operator", trip_day_id=self.days[0]["id"])
        trip_repository.trip_update(self.trip_id, start_date="2026-05-02")
        out = trips.reconcile_trip_days(
            self.trip_id, _ReconcileReq(mark_out_of_range=True))
        self.assertEqual(out["marked_out_of_range"], 1)
        kept = trip_repository.trip_day_get(self.days[0]["id"])
        self.assertIsNotNone(kept, "out-of-range day card must be kept")
        self.assertEqual(kept["reconcile_status"],
                         "out_of_range_acknowledged")
        self.assertEqual(kept["title"], "Precious first day")
        self.assertEqual(kept["evening_notes"], "beer hall dinner")
        notes = [n for n in trip_repository.location_notes_list(self.trip_id)
                 if n.get("trip_day_id") == self.days[0]["id"]]
        self.assertEqual(len(notes), 1, "day content must survive marking")

    def test_reconcile_never_deletes_day_rows(self):
        ids_before = {d["id"] for d in self.days}
        trip_repository.trip_update(self.trip_id,
                                    start_date="2026-05-03",
                                    end_date="2026-05-09")
        trips.reconcile_trip_days(self.trip_id, _ReconcileReq(
            add_missing=True, mark_out_of_range=True))
        ids_after = {d["id"]
                     for d in trip_repository.trip_days_list(self.trip_id)}
        self.assertTrue(ids_before.issubset(ids_after),
                        "reconcile must NEVER delete trip_days rows")
        self.assertEqual(len(ids_after), 9)  # 5 original + 4 added

    def test_acknowledged_day_reactivates_when_back_in_range(self):
        trip_repository.trip_update(self.trip_id, start_date="2026-05-02")
        trips.reconcile_trip_days(self.trip_id,
                                  _ReconcileReq(mark_out_of_range=True))
        self.assertEqual(
            trip_repository.trip_day_get(self.days[0]["id"])
            ["reconcile_status"], "out_of_range_acknowledged")
        # Dates widen back out — the day is in range again.
        trip_repository.trip_update(self.trip_id, start_date="2026-05-01")
        out = trips.reconcile_trip_days(
            self.trip_id, _ReconcileReq(mark_out_of_range=True))
        self.assertEqual(out["reactivated"], 1)
        self.assertEqual(
            trip_repository.trip_day_get(self.days[0]["id"])
            ["reconcile_status"], "active")

    def test_reconcile_noop_flags_change_nothing(self):
        trip_repository.trip_update(self.trip_id, end_date="2026-05-07")
        before = self._dump_days()
        out = trips.reconcile_trip_days(self.trip_id, _ReconcileReq())
        self.assertEqual(out["added"], 0)
        self.assertEqual(out["marked_out_of_range"], 0)
        self.assertEqual(before, self._dump_days())

    def test_unknown_trip_404(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.reconcile_trip_days("no-such-trip",
                                      _ReconcileReq(add_missing=True))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_repository_reconcile_lane_has_no_delete(self):
        # Belt-and-braces lock: neither reconcile function may issue a
        # DELETE against trip_days (source inspection, comment-safe).
        import inspect
        for fn in (trip_repository.trip_days_reconcile_preview,
                   trip_repository.trip_days_reconcile):
            body = inspect.getsource(fn).upper()
            self.assertNotIn("DELETE", body.replace("DELETED", ""))


if __name__ == "__main__":
    unittest.main()
