"""Bucket B coverage: SQLite failures across all trip-day routes.

Companion to test_trip_days_http_sequence.py. This file simulates
SQLite errors AT THE REPOSITORY BOUNDARY (via monkeypatch on the
trip_repository accessors) and asserts on the router response
shape:

  * SQLITE_BUSY, SQLITE_CONSTRAINT, SQLITE_CORRUPT, SQLITE_NOTADB
    each produce a classified 500 with a descriptive prefix
  * evidence-count failure returns HTTP 200 with day cards intact
    AND a top-level ``counts_warning`` string (the whole point of
    ChatGPT's review §4 — a locked counts query must not look
    like legitimate zero evidence)
  * legitimate zero evidence returns no counts_warning
  * every day-adjacent route (list, generate, reconcile,
    reconcile-preview, patch_trip_day, day-photo-link,
    day-photo-unlink) surfaces classified details rather than a
    generic 500

We do NOT depend on FastAPI TestClient here — we call the router
functions directly. That decouples this suite from the fastapi
installation state (matches the same pattern
test_trip_lock_leak_and_orphan_person uses) and lets us monkeypatch
the repository accessors cleanly.

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

# Same FastAPI/Pydantic stubbing pattern as the sibling test file so
# the router module imports without pulling the real framework in.
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

# 2026-07-23 (Bucket A+B follow-up) — Use whichever HTTPException
# class trips.py actually bound at import time, NOT a fresh
# `from fastapi import HTTPException`. When multiple test files
# with different fastapi stubbing strategies run in the same
# process (test_trip_days_http_sequence deletes stubs to load
# real fastapi; this file registers a stub if fastapi is missing),
# the two HTTPException classes can diverge — trips.py raises
# one, the test asserts against the other, and every assertion
# fails with the confusing "raised OtherHTTPException, expected
# HTTPException" shape. Import from trips itself to guarantee we
# always compare like-with-like.
HTTPException = trips.HTTPException


# ── SQLite-error factories (real error names/codes) ──────────────

def _make_sqlite_error(cls, name, code, message):
    """Build a real sqlite3.Error subclass instance with an errorname
    + errorcode. Python 3.11+ has these attributes natively on
    genuine sqlite3 raises; we set them via __setattr__ on our
    synthetic instances so the classifier finds them."""
    exc = cls(message)
    try:
        exc.sqlite_errorname = name
    except AttributeError:  # pragma: no cover — 3.10 fallback
        object.__setattr__(exc, "sqlite_errorname", name)
    try:
        exc.sqlite_errorcode = code
    except AttributeError:  # pragma: no cover
        object.__setattr__(exc, "sqlite_errorcode", code)
    return exc


def make_busy():
    return _make_sqlite_error(
        sqlite3.OperationalError, "SQLITE_BUSY", 5, "database is locked")


def make_constraint_fk():
    return _make_sqlite_error(
        sqlite3.IntegrityError, "SQLITE_CONSTRAINT_FOREIGNKEY", 787,
        "FOREIGN KEY constraint failed")


def make_corrupt():
    return _make_sqlite_error(
        sqlite3.DatabaseError, "SQLITE_CORRUPT", 11,
        "database disk image is malformed")


def make_notadb():
    return _make_sqlite_error(
        sqlite3.DatabaseError, "SQLITE_NOTADB", 26,
        "file is not a database")


def make_ioerr():
    return _make_sqlite_error(
        sqlite3.OperationalError, "SQLITE_IOERR_READ", 266,
        "disk I/O error")


class _Req:
    def __init__(self, **kw):
        base = dict(
            person_id=None, title=None,
            start_date=None, end_date=None, summary=None,
            clear_start_date=False, clear_end_date=False, clear_summary=False,
        )
        base.update(kw)
        self.__dict__.update(base)


class _LiveStyleBase(unittest.TestCase):
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

        # A real trip we can operate on
        out = trips.create_trip(_Req(
            person_id=self.person_id,
            title="Error classification pack",
            start_date="2026-08-03",
            end_date="2026-08-07"))
        self.trip_id = out["trip_id"]

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


# ── /days: classified errors on each stage ──────────────────────

class ListDaysClassifiedErrorTest(_LiveStyleBase):
    """/days must return a classified 500 whenever the underlying
    SQLite call raises — no matter which subclass and no matter
    which stage of the endpoint hit it."""

    def _assert_classified(self, exc_factory, expected_prefix_fragment):
        orig = trip_repository.trip_days_list

        def _boom(_tid):
            raise exc_factory()
        trip_repository.trip_days_list = _boom
        try:
            with self.assertRaises(HTTPException) as cm:
                trips.list_trip_days(self.trip_id)
        finally:
            trip_repository.trip_days_list = orig

        self.assertEqual(cm.exception.status_code, 500)
        self.assertIn(expected_prefix_fragment.lower(),
                      cm.exception.detail.lower(),
                      f"expected prefix {expected_prefix_fragment!r} in "
                      f"{cm.exception.detail!r}")

    def test_sqlite_busy_on_list_returns_500_locked(self):
        self._assert_classified(make_busy, "database temporarily locked")

    def test_sqlite_constraint_on_list_returns_500_constraint(self):
        self._assert_classified(make_constraint_fk, "foreign key")

    def test_sqlite_corrupt_on_list_returns_500_corrupt(self):
        # DatabaseError subclass, not OperationalError — this only
        # gets caught by the broader sqlite3.Error catch. If the
        # router regresses back to OperationalError-only, this test
        # will fail loud.
        self._assert_classified(make_corrupt, "corrupt")

    def test_sqlite_notadb_on_list_returns_500_corrupt(self):
        self._assert_classified(make_notadb, "corrupt")

    def test_sqlite_error_on_trip_get_wrapped_too(self):
        """The initial trip existence check must also be inside the
        classified try/except. ChatGPT §7: an unwrapped trip_get
        would let a DB failure escape as an unclassified 500 or as
        a misleading 404."""
        orig = trip_repository.trip_get

        def _boom(_tid):
            raise make_ioerr()
        trip_repository.trip_get = _boom
        try:
            with self.assertRaises(HTTPException) as cm:
                trips.list_trip_days(self.trip_id)
        finally:
            trip_repository.trip_get = orig
        self.assertEqual(cm.exception.status_code, 500)
        self.assertIn("i/o", cm.exception.detail.lower())


# ── /days: counts_warning path ──────────────────────────────────

class CountsWarningResponseTest(_LiveStyleBase):
    """When trip_day_counts raises, the endpoint must still return
    the day cards (so the operator can work) but attach a
    counts_warning explaining that evidence counts are unverified.
    Zero counts in the absence of a warning = legitimate absence.
    Zero counts + warning = the numbers don't reflect reality."""

    def test_counts_failure_yields_days_plus_counts_warning(self):
        orig = trip_repository.trip_day_counts

        def _boom(_tid):
            raise make_busy()
        trip_repository.trip_day_counts = _boom
        try:
            out = trips.list_trip_days(self.trip_id)
        finally:
            trip_repository.trip_day_counts = orig

        # Days still loaded, unaffected
        self.assertEqual(out["count"], 5,
                         "days must load even when counts fail")
        self.assertEqual(len(out["days"]), 5)
        # counts_warning surfaced and mentions the specific class
        self.assertIn("counts_warning", out)
        self.assertIn("locked", out["counts_warning"].lower())
        # Each card's counts zeroed defensively — but the warning
        # tells the operator not to trust those zeros
        for d in out["days"]:
            self.assertEqual(d["counts"]["photos"], 0)
            self.assertEqual(d["counts"]["notes"], 0)

    def test_corrupt_on_counts_yields_counts_warning(self):
        # DatabaseError subclass — only caught by the broader
        # sqlite3.Error catch. If the router regresses to
        # OperationalError-only, this test fails.
        orig = trip_repository.trip_day_counts

        def _boom(_tid):
            raise make_corrupt()
        trip_repository.trip_day_counts = _boom
        try:
            out = trips.list_trip_days(self.trip_id)
        finally:
            trip_repository.trip_day_counts = orig
        self.assertIn("counts_warning", out)
        self.assertIn("corrupt", out["counts_warning"].lower())

    def test_legitimate_zero_evidence_has_no_counts_warning(self):
        """Fresh trip has zero photos, zero notes, zero sources
        legitimately. That must NOT trigger counts_warning — a
        warning only means "counts could not be verified," not
        "counts happen to be zero." """
        out = trips.list_trip_days(self.trip_id)
        # All zero counts (fresh trip). `photo_suggestions` joined the
        # shape on 2026-08-13 (WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01 §7)
        # when the taken-date match was split out of `photos`; asserting
        # the WHOLE dict rather than the keys it cares about is what
        # makes this test notice, which is the behaviour to keep.
        for d in out["days"]:
            self.assertEqual(d["counts"], {
                "photos": 0, "photo_suggestions": 0, "notes": 0,
                "sources": 0, "public_context": 0,
            })
        # But no warning
        self.assertNotIn("counts_warning", out,
                         "legit zero evidence must not produce a warning")


# ── trip_day_counts internal swallow behavior ───────────────────

class TripDayCountsSwallowTest(_LiveStyleBase):
    """trip_day_counts internally used to swallow OperationalError
    twice (outer 0028 query + inner date-only fallback), converting
    real failures into silent zero counts. Now it swallows ONLY the
    exact ``no such column ... trip_day_id`` shape."""

    def test_non_legacy_operational_error_reraises(self):
        """A generic OperationalError from the photo-counts SQL
        (e.g. a lock) must propagate to the caller — not be
        silently swallowed."""
        # Monkeypatch _connect to return a connection whose execute
        # raises SQLITE_BUSY on the first call.
        orig_connect = trip_repository._connect

        class _BoomCon:
            def __init__(self, real): self._real = real
            def execute(self, *a, **k):
                raise make_busy()
            def close(self):
                self._real.close()

        def _boom_connect():
            return _BoomCon(orig_connect())
        trip_repository._connect = _boom_connect
        try:
            with self.assertRaises(sqlite3.OperationalError) as cm:
                trip_repository.trip_day_counts(self.trip_id)
            self.assertIn("locked", str(cm.exception).lower())
        finally:
            trip_repository._connect = orig_connect

    def test_legacy_missing_trip_day_id_column_swallowed(self):
        """The pre-0028 legacy shape — ``no such column: l.trip_day_id``
        — remains the ONLY silently-swallowed case. That's what
        ChatGPT explicitly said to preserve, so the fallback still
        exists but is narrowly scoped.

        We intercept only the SQL that references ``trip_day_id``,
        proxying every other execute through the real connection.
        That way trip_day_counts' initial call to trip_days_list
        (via the OUTER function) still gets its real rows back."""
        orig_connect = trip_repository._connect

        class _LegacyCon:
            def __init__(self, real):
                self._real = real
            def execute(self, sql, *args):
                # Only the outer 0028 query mentions trip_day_id in
                # its column list AND joins on trip_photo_links.
                # Everything else (trip_days_list SELECT * FROM
                # trip_days, the inner date-only query, etc.) goes
                # to the real connection.
                if ("trip_day_id" in sql
                        and "trip_photo_links" in sql):
                    raise _make_sqlite_error(
                        sqlite3.OperationalError,
                        "SQLITE_ERROR", 1,
                        "no such column: l.trip_day_id")
                return self._real.execute(sql, *args)
            def close(self):
                self._real.close()

        def _legacy_connect():
            return _LegacyCon(orig_connect())
        trip_repository._connect = _legacy_connect
        try:
            # Legacy path swallows the outer failure, retries with
            # the date-only inner query, returns real counts (zero
            # in this fresh fixture).
            counts = trip_repository.trip_day_counts(self.trip_id)
            self.assertIsInstance(counts, dict)
            for c in counts.values():
                self.assertEqual(c["photos"], 0)
        finally:
            trip_repository._connect = orig_connect


# ── Other day routes: classified errors ─────────────────────────

class OtherDayRoutesClassifiedErrorTest(_LiveStyleBase):
    """Every day-adjacent route must classify SQLite failures the
    same way. Regression check on ChatGPT §8: patch_trip_day,
    _require_day_in_trip, day-photo link/unlink, generate,
    reconcile, reconcile-preview all used to return generic 500s."""

    def _assert_wraps(self, callable_, accessor_attr, exc_factory,
                      expected_prefix_fragment):
        """Monkeypatch the given repo accessor to raise; invoke the
        callable; assert HTTPException(500) with classified detail."""
        orig = getattr(trip_repository, accessor_attr)

        def _boom(*a, **k):
            raise exc_factory()
        setattr(trip_repository, accessor_attr, _boom)
        try:
            with self.assertRaises(HTTPException) as cm:
                callable_()
        finally:
            setattr(trip_repository, accessor_attr, orig)
        self.assertEqual(
            cm.exception.status_code, 500,
            f"{accessor_attr} raised {exc_factory.__name__} — "
            f"expected classified 500, got {cm.exception.status_code} "
            f"detail={cm.exception.detail!r}")
        self.assertIn(
            expected_prefix_fragment.lower(),
            cm.exception.detail.lower(),
            f"{accessor_attr}: expected prefix "
            f"{expected_prefix_fragment!r} in {cm.exception.detail!r}")

    # generate ---------------------------------------------------

    def test_generate_wraps_sqlite_error(self):
        self._assert_wraps(
            lambda: trips.generate_trip_days(self.trip_id),
            "trip_days_generate", make_busy, "locked")

    def test_generate_exists_check_wraps_sqlite_error(self):
        self._assert_wraps(
            lambda: trips.generate_trip_days(self.trip_id),
            "trip_get", make_corrupt, "corrupt")

    # reconcile --------------------------------------------------

    def test_reconcile_wraps_sqlite_error(self):
        self._assert_wraps(
            lambda: trips.reconcile_trip_days(
                self.trip_id, _Req(add_missing=True)),
            "trip_days_reconcile", make_notadb, "corrupt")

    def test_reconcile_preview_wraps_sqlite_error(self):
        self._assert_wraps(
            lambda: trips.reconcile_preview_trip_days(self.trip_id),
            "trip_days_reconcile_preview", make_ioerr, "i/o")

    # patch_trip_day --------------------------------------------

    def test_patch_trip_day_wraps_sqlite_error(self):
        days = trip_repository.trip_days_list(self.trip_id)
        day_id = days[0]["id"]

        class _PatchReq:
            title = "test"
            main_location = None
            lodging_base = None
            trip_region_id = None
            trip_stop_id = None
            morning_notes = None
            afternoon_notes = None
            evening_notes = None
            places_visited = None
            meals = None
            clear_title = False
            clear_main_location = False
            clear_lodging_base = False
            clear_morning_notes = False
            clear_afternoon_notes = False
            clear_evening_notes = False
            clear_region = False
            clear_stop = False

        self._assert_wraps(
            lambda: trips.patch_trip_day(day_id, _PatchReq()),
            "trip_day_update", make_busy, "locked")

    def test_patch_trip_day_exists_check_wraps(self):
        days = trip_repository.trip_days_list(self.trip_id)
        day_id = days[0]["id"]

        class _PatchReq:
            title = None
            main_location = None
            lodging_base = None
            trip_region_id = None
            trip_stop_id = None
            morning_notes = None
            afternoon_notes = None
            evening_notes = None
            places_visited = None
            meals = None
            clear_title = False
            clear_main_location = False
            clear_lodging_base = False
            clear_morning_notes = False
            clear_afternoon_notes = False
            clear_evening_notes = False
            clear_region = False
            clear_stop = False

        self._assert_wraps(
            lambda: trips.patch_trip_day(day_id, _PatchReq()),
            "trip_day_get", make_corrupt, "corrupt")

    # day-photo-link / unlink -----------------------------------

    def test_day_photo_link_wraps_trip_check(self):
        days = trip_repository.trip_days_list(self.trip_id)
        day_id = days[0]["id"]

        class _R:
            photo_link_ids = ["fake-link"]
        self._assert_wraps(
            lambda: trips.link_day_photos(self.trip_id, day_id, _R()),
            "trip_get", make_busy, "locked")

    def test_day_photo_unlink_wraps_trip_check(self):
        days = trip_repository.trip_days_list(self.trip_id)
        day_id = days[0]["id"]

        class _R:
            photo_link_ids = ["fake-link"]
        self._assert_wraps(
            lambda: trips.unlink_day_photos(self.trip_id, day_id, _R()),
            "trip_get", make_notadb, "corrupt")


if __name__ == "__main__":
    unittest.main()
