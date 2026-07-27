"""Track C fix (2026-07-15) — trip create + trip patch must generate /
reconcile day cards automatically. Prior behavior only wrote start_date
+ end_date; the Travel Doc Lab said "Start and end dates generate one
editable card per day" but nothing actually created them until the
operator found the separate "Generate / reconcile day cards" button.

The Bismarck trip was the live-test surfacer: Chris entered valid dates,
the trip saved, no day cards appeared, the UI rendered "No day cards
yet" — indistinguishable from the operator forgetting to click Generate.

These tests lock in the new automatic behavior:

  * Trip create with valid dates → day cards created automatically
  * Trip create with the exact Chris-named case (2026-07-14 → 2026-07-19)
    → 6 day cards (14, 15, 16, 17, 18, 19)
  * Trip create with no dates → no attempt, no warning, trip still saved
  * Trip create with bad dates → trip STILL saved + response carries
    ``days_warning`` string
  * Trip patch that sets dates → auto-reconcile adds missing day cards
  * Trip patch that changes end_date to extend the window → new days
    added, existing operator-edited day cards preserved
  * Trip patch that clears dates → no reconcile attempt (no window to
    generate against), no warning
  * Trip patch that touches only the title → no reconcile at all
  * Bad-date patch → trip title / other fields STILL saved, response
    carries ``days_warning``

Offline fastapi/pydantic stub pattern (matches test_trip_editable_fixes).
"""
from __future__ import annotations

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

import os  # noqa: E402
from api import db as _db  # noqa: E402
from api.services import trip_repository  # noqa: E402
from api.routers import trips  # noqa: E402


class _Req:
    """Simple attribute bag with defaults matching TripCreate / TripPatch."""

    def __init__(self, **kw):
        base = dict(
            person_id=None, title=None,
            start_date=None, end_date=None,
            summary=None,
            clear_start_date=False, clear_end_date=False,
            clear_summary=False,
        )
        base.update(kw)
        self.__dict__.update(base)


class _AutoDayGenerationTestBase(unittest.TestCase):
    """Fresh sqlite fixture per test with a narrator, so each auto-day
    call has a real trip row to attach to."""

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
            "'2026-07-15', '2026-07-15')", (self.person_id,))
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


class CreateTripAutoDaysTest(_AutoDayGenerationTestBase):
    def test_bismarck_july_14_to_19_creates_six_editable_day_cards(self):
        """The exact Chris-named case."""
        out = trips.create_trip(_Req(
            person_id=self.person_id,
            title="Bismarck",
            start_date="2026-07-14",
            end_date="2026-07-19"))
        self.assertIn("trip_id", out)
        self.assertNotIn("days_warning", out,
                         "clean valid dates → no warning")
        days = trip_repository.trip_days_list(out["trip_id"])
        self.assertEqual(len(days), 6, "July 14–19 inclusive is 6 days")
        actual_dates = [str(d["date"])[:10] for d in days]
        self.assertEqual(
            actual_dates,
            ["2026-07-14", "2026-07-15", "2026-07-16",
             "2026-07-17", "2026-07-18", "2026-07-19"])
        # And each is a real day card, editable, with an operator
        # workflow surface.
        for i, d in enumerate(days, start=1):
            self.assertEqual(d["day_index"], i)

    def test_create_without_dates_does_not_generate_days_or_warn(self):
        out = trips.create_trip(_Req(
            person_id=self.person_id,
            title="Trip without dates yet"))
        self.assertIn("trip_id", out)
        self.assertNotIn("days_warning", out)
        days = trip_repository.trip_days_list(out["trip_id"])
        self.assertEqual(days, [])

    def test_create_with_only_start_date_does_not_generate_or_warn(self):
        # Half-populated window is legitimate mid-typing; not an error.
        out = trips.create_trip(_Req(
            person_id=self.person_id,
            title="Half-populated",
            start_date="2026-07-14"))
        self.assertIn("trip_id", out)
        self.assertNotIn("days_warning", out)
        self.assertEqual(
            trip_repository.trip_days_list(out["trip_id"]), [])

    def test_create_with_reversed_dates_still_saves_and_warns(self):
        out = trips.create_trip(_Req(
            person_id=self.person_id,
            title="Reversed dates",
            start_date="2026-07-19",
            end_date="2026-07-14"))
        self.assertIn("trip_id", out)
        self.assertIn("days_warning", out)
        self.assertIn("before start", out["days_warning"].lower())
        # Trip itself is saved:
        self.assertIsNotNone(trip_repository.trip_get(out["trip_id"]))
        # No day cards attempted:
        self.assertEqual(
            trip_repository.trip_days_list(out["trip_id"]), [])

    def test_create_with_malformed_iso_date_still_saves_and_warns(self):
        out = trips.create_trip(_Req(
            person_id=self.person_id,
            title="Bad ISO",
            start_date="July 14, 2026",
            end_date="2026-07-19"))
        self.assertIn("trip_id", out)
        self.assertIn("days_warning", out)
        self.assertIsNotNone(trip_repository.trip_get(out["trip_id"]))
        self.assertEqual(
            trip_repository.trip_days_list(out["trip_id"]), [])

    def test_single_day_trip_generates_one_card(self):
        # Chris-visible: same start + end is a valid single-day trip.
        out = trips.create_trip(_Req(
            person_id=self.person_id,
            title="Day trip",
            start_date="2026-07-14",
            end_date="2026-07-14"))
        self.assertNotIn("days_warning", out)
        days = trip_repository.trip_days_list(out["trip_id"])
        self.assertEqual(len(days), 1)


class PatchTripAutoDaysTest(_AutoDayGenerationTestBase):
    def _create_undated(self):
        return trip_repository.trip_create(
            self.person_id, "Late-dated trip")

    def test_patch_adds_dates_triggers_generation(self):
        tid = self._create_undated()
        out = trips.patch_trip(tid, _Req(
            start_date="2026-07-14",
            end_date="2026-07-16"))
        self.assertTrue(out.get("ok"))
        self.assertNotIn("days_warning", out)
        days = trip_repository.trip_days_list(tid)
        self.assertEqual(len(days), 3)

    def test_patch_extends_end_date_adds_missing_days_only(self):
        # Start with 3 days, then extend end_date by 2 days. The two
        # new days appear; the original three keep their operator
        # edits.
        tid = self._create_undated()
        trips.patch_trip(tid, _Req(
            start_date="2026-07-14",
            end_date="2026-07-16"))
        original_days = trip_repository.trip_days_list(tid)
        self.assertEqual(len(original_days), 3)
        # Operator edits Day 2's title.
        trip_repository.trip_day_update(
            original_days[1]["id"], title="Kent's birthday dinner")
        # Now extend the window.
        out = trips.patch_trip(tid, _Req(end_date="2026-07-18"))
        self.assertTrue(out.get("ok"))
        self.assertNotIn("days_warning", out)
        days = trip_repository.trip_days_list(tid)
        self.assertEqual(len(days), 5, "3 original + 2 new")
        # The edited day still has its operator title.
        edited = trip_repository.trip_day_get(original_days[1]["id"])
        self.assertEqual(edited["title"], "Kent's birthday dinner")

    def test_patch_title_only_does_not_reconcile(self):
        tid = self._create_undated()
        # No day cards yet; patch title only should NOT create any.
        out = trips.patch_trip(tid, _Req(title="Just a rename"))
        self.assertTrue(out.get("ok"))
        self.assertNotIn("days_warning", out)
        self.assertEqual(trip_repository.trip_days_list(tid), [])

    def test_patch_clears_start_date_does_not_warn(self):
        # Clearing a date is a legitimate operator action (half-typed
        # correction, mode change) — reconcile skips silently, no
        # warning surfaced.
        tid = trip_repository.trip_create(
            self.person_id, "Trip with dates",
            start_date="2026-07-14", end_date="2026-07-16")
        trip_repository.trip_days_generate(tid)
        out = trips.patch_trip(tid, _Req(
            clear_start_date=True))
        self.assertTrue(out.get("ok"))
        # No warning: reconcile skipped because window is incomplete.
        self.assertNotIn("days_warning", out)
        # Existing day cards are preserved (no deletes ever).
        self.assertEqual(
            len(trip_repository.trip_days_list(tid)), 3)

    def test_patch_reversed_dates_still_saves_trip_and_warns(self):
        tid = self._create_undated()
        out = trips.patch_trip(tid, _Req(
            title="Bad dates",
            start_date="2026-07-19",
            end_date="2026-07-14"))
        self.assertTrue(out.get("ok"))
        self.assertIn("days_warning", out)
        # Trip title still saved:
        trip = trip_repository.trip_get(tid)
        self.assertEqual(trip["title"], "Bad dates")


class ExistingWorkflowsUnchangedTest(_AutoDayGenerationTestBase):
    """The manual Generate button + reconcile endpoints must keep
    working — auto-generation is additive, not a replacement."""

    def test_manual_generate_button_still_reachable(self):
        # Simulate the flow: create WITHOUT dates, then set dates via
        # PATCH, then hit the manual generate endpoint. All three paths
        # remain functional even though PATCH already ran auto-reconcile.
        tid = trip_repository.trip_create(
            self.person_id, "Manual-button user")
        trips.patch_trip(tid, _Req(
            start_date="2026-07-14", end_date="2026-07-16"))
        days_after_patch = trip_repository.trip_days_list(tid)
        self.assertEqual(len(days_after_patch), 3)
        # Second call is idempotent — no crash, no duplicates.
        result = trip_repository.trip_days_generate(tid)
        self.assertEqual(result.get("created"), 0)
        self.assertEqual(
            len(trip_repository.trip_days_list(tid)), 3)


if __name__ == "__main__":
    unittest.main()
