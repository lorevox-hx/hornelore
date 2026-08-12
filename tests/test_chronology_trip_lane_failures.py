"""S8 — the chronology accordion must not render a trips failure as "no trips".

SECURITY/STABILITY-REVIEW-2026-08-12 finding S8. The trips lane in
``chronology_accordion.py`` was wrapped in a bare, unlogged
``except Exception: trip_items = []``. Any trips-schema problem, missing
migration, or malformed row therefore rendered as a narrator with no
trips — indistinguishable from the truth, with nothing in the log for an
operator to look at. The same shape sat around the per-trip photo strip.

Three behaviours are asserted here, all BEHAVIORAL (the real functions
run; only the repository boundary is doubled):

  1. a failure is LOGGED, not swallowed;
  2. a failure no longer DISCARDS the trips already collected, and one
     malformed row costs only itself;
  3. a genuinely absent schema (pre-0015 DB) stays quiet — the tolerance
     the original code was written for is preserved, so this does not
     trade silence for noise.

Run per-module:
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_chronology_trip_lane_failures
"""
from __future__ import annotations

import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(_REPO_ROOT / "server" / "code"),
           str(_REPO_ROOT / "server"),
           str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

if "code" in sys.modules and not hasattr(sys.modules["code"], "__path__"):
    del sys.modules["code"]

for _stub_name in ("fastapi", "pydantic"):
    _stub = sys.modules.get(_stub_name)
    if _stub is not None and not hasattr(_stub, "__path__"):
        for _k in [k for k in list(sys.modules)
                   if k == _stub_name or k.startswith(_stub_name + ".")]:
            del sys.modules[_k]

_TMP = tempfile.mkdtemp(prefix="hl-s8-")
os.environ["DATA_DIR"] = _TMP

for _m in [m for m in list(sys.modules)
           if m.endswith("api.db") or m == "api.db"]:
    del sys.modules[_m]

import code.api.db as db  # noqa: E402
from code.api.routers import chronology_accordion as chrono  # noqa: E402


_PERSON = "s8-narrator"


def _seed_person() -> None:
    """Seed a narrator WITH a birth year.

    Load-bearing, and it caught a silent-pass trap: the payload builder
    reads DOB from the PROFILE (`basics.dob`), not from the people row,
    and returns early with an empty payload when it cannot derive a
    birth year. Seeding only `people.date_of_birth` meant the trips
    block was never reached at all, so every failure assertion compared
    against an empty log and the suite looked like the fix was missing.
    """
    db.init_db()
    con = db._connect()
    try:
        now = db._now_iso()
        con.execute(
            "INSERT OR IGNORE INTO people"
            " (id, display_name, date_of_birth, created_at, updated_at)"
            " VALUES (?,?,?,?,?)",
            (_PERSON, "S8 Narrator", "1950-01-01", now, now))
        con.commit()
    finally:
        con.close()
    db.ensure_profile(_PERSON)
    db.update_profile_json(
        _PERSON,
        {"basics": {"dob": "1950-01-01", "fullname": "S8 Narrator"}},
        merge=True)


class _FakeRepo:
    """Stands in for services.trip_repository at the module boundary."""

    def __init__(self, trips, photo_error=None, list_error=None):
        self._trips = trips
        self._photo_error = photo_error
        self._list_error = list_error

    def trip_list(self, person_id):
        if self._list_error is not None:
            raise self._list_error
        return list(self._trips)

    def photo_links_with_photo_paths(self, trip_id, memoir_only=False):
        if self._photo_error is not None:
            raise self._photo_error
        return []


class _CaptureHandler(logging.Handler):
    """Collect records without assertLogs, which FAILS when a test
    legitimately logs nothing — and 'logs nothing' is exactly what the
    happy-path tests need to be able to assert."""

    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)

    def rendered(self) -> str:
        return "\n".join(
            f"{r.levelname}:{r.name}:{r.getMessage()}" for r in self.records)


class _TripLaneHarness(unittest.TestCase):
    """Drives the REAL accordion endpoint with the repository doubled.

    The trips lane imports its repository INSIDE the function as
    `from ..services import trip_repository`. That form resolves by
    getattr on the already-imported `code.api.services` package, so
    installing a double in sys.modules does nothing — the real module
    wins and the test silently exercises production code (which is how
    the first run of this suite produced 'no logs triggered'). The
    double therefore has to be set as an ATTRIBUTE on the package.
    """

    _PKG = "code.api.services"

    def setUp(self):
        _seed_person()
        import importlib
        self._pkg = importlib.import_module(self._PKG)
        self._had_attr = hasattr(self._pkg, "trip_repository")
        self._saved = getattr(self._pkg, "trip_repository", None)

    def tearDown(self):
        if self._had_attr:
            setattr(self._pkg, "trip_repository", self._saved)
        else:
            try:
                delattr(self._pkg, "trip_repository")
            except AttributeError:
                pass

    def _run_with(self, fake) -> tuple:
        setattr(self._pkg, "trip_repository", fake)
        logger = logging.getLogger("chronology_accordion")
        handler = _CaptureHandler()
        logger.addHandler(handler)
        prev_level, logger.level = logger.level, logging.DEBUG
        try:
            payload = chrono.api_chronology_accordion(person_id=_PERSON)
        finally:
            logger.removeHandler(handler)
            logger.level = prev_level
        # Payload shape: decades[] -> years[] -> items[]. (Reading
        # decades[].items[] silently yields [] and every trip assertion
        # fails against an empty list — verified against the real
        # payload rather than assumed.)
        trips = [
            item
            for dec in payload.get("decades", [])
            for yr in dec.get("years", [])
            for item in yr.get("items", [])
            if item.get("event_kind") == "trip"
        ]
        return payload, trips, handler.rendered()

    def test_the_double_is_actually_installed(self):
        """Non-vacuity: if the double were ignored (the sys.modules
        mistake above), every failure test would pass by never running
        the code it claims to test."""
        marker = RuntimeError("sentinel-double-reached")
        _, _, logs = self._run_with(_FakeRepo([], list_error=marker))
        self.assertIn("sentinel-double-reached", logs,
                      "the fake repository was never called")


class TripLaneFailureIsLoggedTest(_TripLaneHarness):

    def test_whole_lane_failure_is_logged_not_silent(self):
        fake = _FakeRepo([], list_error=RuntimeError("trips table is angry"))
        _, trips, logs = self._run_with(fake)
        self.assertEqual(trips, [])
        self.assertIn("trips lane FAILED", logs)
        self.assertIn(_PERSON, logs)
        self.assertIn("trips table is angry", logs)

    def test_photo_strip_failure_is_logged_and_the_trip_still_renders(self):
        fake = _FakeRepo(
            [{"id": "t1", "title": "Bismarck", "start_date": "2019-06-01"}],
            photo_error=RuntimeError("photo join exploded"),
        )
        _, trips, logs = self._run_with(fake)
        self.assertEqual(len(trips), 1, "trip vanished over a photo failure")
        self.assertEqual(trips[0]["photos"], [])
        self.assertIn("trip photo strip failed", logs)
        self.assertIn("t1", logs)


class PartialResultsSurviveTest(_TripLaneHarness):

    def test_one_malformed_row_does_not_discard_the_others(self):
        """The half that used to lose good trips.

        A row whose .get() raises stands in for any malformed record;
        previously it hit the outer handler, which reset trip_items to []
        and threw away every trip already collected.
        """
        class _Angry(dict):
            def get(self, *a, **kw):
                raise RuntimeError("malformed trip row")

        fake = _FakeRepo([
            {"id": "t1", "title": "Good One", "start_date": "2019-06-01"},
            _Angry(),
            {"id": "t3", "title": "Good Two", "start_date": "2021-06-01"},
        ])
        _, trips, logs = self._run_with(fake)
        labels = sorted(t["label"] for t in trips)
        self.assertEqual(labels, ["Trip — Good One", "Trip — Good Two"],
                         "a malformed row took good trips down with it")
        self.assertIn("skipping malformed trip row", logs)


class AbsentSchemaStaysQuietTest(_TripLaneHarness):
    """Do not trade silence for noise.

    The original tolerance existed for a legitimate case: a pre-0015
    database has no trip tables. That must stay quiet-and-INFO, never a
    warning, or operators learn to ignore the warnings that matter.
    """

    def test_missing_table_is_info_not_warning(self):
        import sqlite3
        fake = _FakeRepo([], list_error=sqlite3.OperationalError(
            "no such table: trips"))
        _, trips, logs = self._run_with(fake)
        self.assertEqual(trips, [])
        self.assertIn("schema not present", logs)
        self.assertNotIn("WARNING", logs)

    def test_unimportable_service_is_info_not_warning(self):
        fake = _FakeRepo([], list_error=ImportError("no trip_repository here"))
        _, trips, logs = self._run_with(fake)
        self.assertEqual(trips, [])
        self.assertIn("trips lane unavailable", logs)
        self.assertNotIn("WARNING", logs)


class HappyPathUnchangedTest(_TripLaneHarness):

    def test_dated_trips_still_render(self):
        fake = _FakeRepo([
            {"id": "t1", "title": "Bismarck", "start_date": "2019-06-01"},
            {"id": "t2", "title": "Prague", "end_date": "2021-09-02"},
        ])
        _, trips, _logs = self._run_with(fake)
        self.assertEqual(len(trips), 2)
        self.assertEqual(sorted(t["year"] for t in trips), [2019, 2021])

    def test_undated_trip_is_skipped_without_a_warning(self):
        """Pre-existing behaviour: no parseable year -> not on a timeline."""
        fake = _FakeRepo([
            {"id": "t1", "title": "Someday", "start_date": ""},
            {"id": "t2", "title": "Bismarck", "start_date": "2019-06-01"},
        ])
        _, trips, logs = self._run_with(fake)
        self.assertEqual(len(trips), 1)
        self.assertNotIn("malformed trip row", logs)


if __name__ == "__main__":
    unittest.main()
