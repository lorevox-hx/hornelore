"""Bucket C.2 — auto-days runs BEFORE best-effort timeline bridge sync.

Coverage for the ordering change in create_trip and patch_trip:

  * If ``trip_timeline_bridge.sync_trip_to_life_record`` raises,
    the day cards still generate cleanly and land in the response.
  * The sync_warning surfaces on the response body as before.
  * Ordering is verified by monkeypatching the two helpers with
    call-order tracking wrappers.

Fresh sqlite fixture per test.
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

# Same fastapi/pydantic stub pattern as sibling test files
if "fastapi" not in sys.modules:
    stub = types.ModuleType("fastapi")

    class _APIRouter:
        def __init__(self, *a, **k): pass

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

    class _BaseModel: pass
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
        base = dict(
            person_id=None, title=None,
            start_date=None, end_date=None, summary=None,
            clear_start_date=False, clear_end_date=False, clear_summary=False,
        )
        base.update(kw)
        self.__dict__.update(base)


class _FreshDBBase(unittest.TestCase):
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
        self.person_id = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO people (id, display_name, date_of_birth, "
            "created_at, updated_at) VALUES (?, 'Chris', '1962-12-24', "
            "'2026-07-23', '2026-07-23')", (self.person_id,))
        con.commit()
        con.close()

    def tearDown(self):
        if self._orig_flag is None:
            os.environ.pop("HORNELORE_TRIPS", None)
        else:
            os.environ["HORNELORE_TRIPS"] = self._orig_flag
        _db.DB_PATH = self._orig_db
        try:
            self.db_path.unlink()
        except OSError:
            pass


# ── Bridge failure does not block auto-days ────────────────────

class BridgeFailureDoesNotBlockAutoDaysTest(_FreshDBBase):
    def test_create_trip_generates_days_even_when_bridge_raises(self):
        """If trip_timeline_bridge.sync_trip_to_life_record raises,
        create_trip must still return 200 with day cards generated
        AND surface a sync_warning."""
        from api.routers import trips as _trips_mod
        orig_bridge = _trips_mod.trip_timeline_bridge.sync_trip_to_life_record

        def _boom(_tid):
            raise RuntimeError(
                "bridge sync failure — should NOT block auto-days")
        _trips_mod.trip_timeline_bridge.sync_trip_to_life_record = _boom
        try:
            out = trips.create_trip(_Req(
                person_id=self.person_id,
                title="Bridge failure canary",
                start_date="2026-08-03",
                end_date="2026-08-07"))
        finally:
            _trips_mod.trip_timeline_bridge.sync_trip_to_life_record = \
                orig_bridge

        # Trip created
        self.assertIn("trip_id", out)
        # Auto-days succeeded (no days_warning)
        self.assertNotIn(
            "days_warning", out,
            "day generation must succeed even when bridge fails")
        # Sync warning surfaced
        self.assertIn("sync_warning", out,
                      "bridge failure must produce a sync_warning")
        # And there are actually 5 day cards on the trip
        days = trip_repository.trip_days_list(out["trip_id"])
        self.assertEqual(len(days), 5,
                         "5 day cards expected for Aug 3–7 window")

    def test_patch_trip_reconciles_days_even_when_bridge_raises(self):
        """Same shape for PATCH: bridge failure surfaces as
        sync_warning but doesn't block the day reconcile."""
        out = trips.create_trip(_Req(
            person_id=self.person_id,
            title="Patch canary",
            start_date="2026-08-03",
            end_date="2026-08-07"))
        trip_id = out["trip_id"]

        from api.routers import trips as _trips_mod
        orig_bridge = _trips_mod.trip_timeline_bridge.sync_trip_to_life_record

        def _boom(_tid):
            raise RuntimeError("bridge sync failure on patch")
        _trips_mod.trip_timeline_bridge.sync_trip_to_life_record = _boom
        try:
            patch_out = trips.patch_trip(trip_id, _Req(
                start_date="2026-08-01"))
        finally:
            _trips_mod.trip_timeline_bridge.sync_trip_to_life_record = \
                orig_bridge

        self.assertNotIn(
            "days_warning", patch_out,
            "day reconcile must succeed even when bridge fails on patch")
        self.assertIn("sync_warning", patch_out,
                      "bridge failure on patch must produce a sync_warning")
        # Prepending Aug 1-2 → 7 total
        days = trip_repository.trip_days_list(trip_id)
        self.assertEqual(len(days), 7)


# ── Ordering: auto-days is called BEFORE bridge ────────────────

class OrderingTest(_FreshDBBase):
    """The whole point of C.2: primary workflow (day generation)
    must precede best-effort projection (bridge sync). Wrap both
    helpers with call-order tracking to verify the sequence."""

    def _wrap_ordering(self, calls_list):
        from api.routers import trips as _trips_mod
        orig_days = _trips_mod._auto_generate_days_for_new_trip
        orig_bridge = _trips_mod._safe_sync_life_record

        def _wrapped_days(trip_id, start_date, end_date):
            calls_list.append("auto_days")
            return orig_days(trip_id, start_date, end_date)

        def _wrapped_bridge(trip_id):
            calls_list.append("bridge_sync")
            return orig_bridge(trip_id)

        _trips_mod._auto_generate_days_for_new_trip = _wrapped_days
        _trips_mod._safe_sync_life_record = _wrapped_bridge
        return orig_days, orig_bridge

    def _unwrap_ordering(self, originals):
        from api.routers import trips as _trips_mod
        orig_days, orig_bridge = originals
        _trips_mod._auto_generate_days_for_new_trip = orig_days
        _trips_mod._safe_sync_life_record = orig_bridge

    def test_create_trip_calls_auto_days_before_bridge(self):
        calls = []
        originals = self._wrap_ordering(calls)
        try:
            trips.create_trip(_Req(
                person_id=self.person_id,
                title="Ordering canary",
                start_date="2026-08-03",
                end_date="2026-08-07"))
        finally:
            self._unwrap_ordering(originals)

        # Both must be called; auto_days MUST come first
        self.assertEqual(
            calls, ["auto_days", "bridge_sync"],
            "create_trip must call auto-days BEFORE bridge sync "
            "(primary workflow first, projection second)")

    def test_patch_trip_calls_reconcile_before_bridge(self):
        # Create a trip first (this run will use the current ordering
        # too, which is fine — we clear the calls list before PATCH)
        out = trips.create_trip(_Req(
            person_id=self.person_id,
            title="Patch ordering canary",
            start_date="2026-08-03",
            end_date="2026-08-07"))
        trip_id = out["trip_id"]

        # Now wrap for the PATCH call. PATCH uses
        # _auto_reconcile_days_on_patch instead of _auto_generate_...
        from api.routers import trips as _trips_mod
        orig_reconcile = _trips_mod._auto_reconcile_days_on_patch
        orig_bridge = _trips_mod._safe_sync_life_record
        calls = []

        def _wrapped_reconcile(tid, dt):
            calls.append("auto_reconcile")
            return orig_reconcile(tid, dt)

        def _wrapped_bridge(tid):
            calls.append("bridge_sync")
            return orig_bridge(tid)

        _trips_mod._auto_reconcile_days_on_patch = _wrapped_reconcile
        _trips_mod._safe_sync_life_record = _wrapped_bridge
        try:
            trips.patch_trip(trip_id, _Req(start_date="2026-08-01"))
        finally:
            _trips_mod._auto_reconcile_days_on_patch = orig_reconcile
            _trips_mod._safe_sync_life_record = orig_bridge

        self.assertEqual(
            calls, ["auto_reconcile", "bridge_sync"],
            "patch_trip must call reconcile BEFORE bridge sync")


if __name__ == "__main__":
    unittest.main()
