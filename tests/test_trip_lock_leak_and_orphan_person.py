"""North Dakota live-test follow-up (2026-07-23).

Two coordinated failures surfaced by the North Dakota API run:

  (A) ``sqlite3.OperationalError: database is locked`` on the auto-day-
      generation write, appearing after a trip whose ``person_id`` was
      bogus went through ``trip_timeline_bridge.sync_trip_to_life_
      record`` and the bridge's ``add_timeline_event`` INSERT hit a
      FOREIGN KEY constraint failure. The old add_timeline_event body
      did not use try/finally, so the failed connection leaked its
      write lock. The next write (auto-days) tripped on that lock.

  (B) The bogus ``person_id="PASTE_UUID_HERE"`` was ACCEPTED by
      ``POST /api/trips`` and an orphan trip was created against a
      nonexistent narrator.

  (C) Day-index scramble when the operator moves the start_date
      earlier while day cards for later dates already exist and have
      operator content on them.

  (D) Full live-style sequence — create, edit a day, extend, reverse
      dates, restore, delete — must complete with zero
      OperationalError / HTTP 500 across all steps.

Test posture: fresh sqlite fixture per test, real trips + real
timeline_events tables via _db.init_db().
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

# 2026-07-23 — use whichever HTTPException class trips.py actually
# bound at import time. Guards against test-isolation drift when
# another file (test_trip_days_http_sequence) drops the fastapi
# stub to load real fastapi mid-run; without this, the two classes
# diverge and every assertRaises(HTTPException) here fails against
# an assertion-side stub mismatch.
HTTPException = trips.HTTPException


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


# ── (A) Lock leak: FK failure in add_timeline_event must not lock the DB
class TimelineFKLockLeakTest(_LiveStyleBase):
    def test_fk_fail_in_add_timeline_event_does_not_leak_lock(self):
        """The exact 2026-07-22 live reproducer: attempt a timeline
        event insert with a nonexistent person_id → FK failure →
        connection must be closed cleanly → the very next write must
        succeed without ``database is locked``."""
        bogus_person = str(uuid.uuid4())  # not in `people`
        # First write: triggers the FK failure inside add_timeline_event.
        # add_timeline_event now has try/except/finally, so this SHOULD
        # raise IntegrityError but the connection MUST be closed.
        with self.assertRaises(sqlite3.IntegrityError):
            _db.add_timeline_event(
                person_id=bogus_person,
                date="2026-08-03",
                title="orphan test event",
            )
        # Second write: MUST succeed. If the leaked-conn bug returns,
        # this raises sqlite3.OperationalError: database is locked.
        trip_id = trip_repository.trip_create(
            self.person_id, "Second write proves lock released",
            start_date="2026-08-03", end_date="2026-08-07")
        # And a third write for extra safety — auto-day-generation
        # against the fresh trip.
        result = trip_repository.trip_days_generate(trip_id)
        self.assertEqual(result["created"], 5)

    def test_delete_timeline_event_on_missing_id_does_not_leak(self):
        """delete_timeline_event with a missing id is a no-op (rowcount
        0) — but a bare except-less body would still hold a WRITE lock
        on the DELETE statement's implicit transaction until close.
        Verify the next write succeeds."""
        ok = _db.delete_timeline_event(str(uuid.uuid4()))  # not there
        self.assertFalse(ok)
        # Next write must succeed.
        trip_id = trip_repository.trip_create(
            self.person_id, "Post-delete write")
        self.assertTrue(bool(trip_id))

    def test_list_timeline_events_does_not_leak_on_missing_person(self):
        """Read-only accessor must still close cleanly on empty result."""
        out = _db.list_timeline_events(str(uuid.uuid4()))
        self.assertEqual(out, [])
        # Next write proves no lingering conn.
        _db.add_timeline_event(
            person_id=self.person_id,
            date="2026-08-03",
            title="OK after read",
        )


# ── (B) Orphan person_id rejected at create ─────────────────────────
class OrphanPersonIdValidationTest(_LiveStyleBase):
    def test_bogus_person_id_returns_422(self):
        with self.assertRaises(HTTPException) as cm:
            trips.create_trip(_Req(
                person_id="PASTE_UUID_HERE",
                title="Should not save",
                start_date="2026-08-03",
                end_date="2026-08-07"))
        self.assertEqual(cm.exception.status_code, 422)
        # 2026-07-23 (follow-up) — asserting trip_list(self.person_id)
        # only proves the VALID narrator got no trip; it does not prove
        # an orphan wasn't inserted under "PASTE_UUID_HERE". Fix per
        # ChatGPT review §6: assert the WHOLE trips table is empty AND
        # explicitly verify no row exists under the bogus owner.
        self.assertEqual(trip_repository.trip_list(), [],
                         "no trip should be persisted anywhere")
        self.assertEqual(
            trip_repository.trip_list("PASTE_UUID_HERE"), [],
            "no orphan should have landed under the bogus person_id")

    def test_empty_person_id_returns_422(self):
        with self.assertRaises(HTTPException) as cm:
            trips.create_trip(_Req(
                person_id="",
                title="Missing person",
                start_date="2026-08-03",
                end_date="2026-08-07"))
        self.assertEqual(cm.exception.status_code, 422)
        # And no rows anywhere (see test_bogus_person_id_returns_422).
        self.assertEqual(trip_repository.trip_list(), [])

    def test_uuid_shaped_but_nonexistent_person_id_returns_422(self):
        fake = str(uuid.uuid4())
        with self.assertRaises(HTTPException) as cm:
            trips.create_trip(_Req(
                person_id=fake,
                title="Fake UUID",
                start_date="2026-08-03",
                end_date="2026-08-07"))
        self.assertEqual(cm.exception.status_code, 422)
        self.assertIn(fake, cm.exception.detail)
        # No orphan under the shaped-but-nonexistent UUID either.
        self.assertEqual(trip_repository.trip_list(fake), [])
        self.assertEqual(trip_repository.trip_list(), [])

    def test_valid_person_id_still_creates_the_trip(self):
        out = trips.create_trip(_Req(
            person_id=self.person_id,
            title="Real narrator",
            start_date="2026-08-03",
            end_date="2026-08-07"))
        self.assertIn("trip_id", out)
        self.assertNotIn("days_warning", out)


# ── (C) Prepend renumber: earlier-start with existing edited card ──
class DayIndexRenumberOnPrependTest(_LiveStyleBase):
    def test_earlier_start_renumbers_and_preserves_operator_content(self):
        """Chris-named scenario: create Aug 3–7 → edit Aug 5 → move
        start to Aug 1. Assert:
          * Aug 1 = Day 1, Aug 2 = Day 2, Aug 3 = Day 3, ... Aug 7 = Day 7
          * Aug 5's operator content preserved
          * Aug 5's row ID unchanged (row was RENUMBERED, not replaced)"""
        # Step 1: create Aug 3–7 → 5 day cards, day_index 1..5
        out = trips.create_trip(_Req(
            person_id=self.person_id,
            title="North Dakota",
            start_date="2026-08-03",
            end_date="2026-08-07"))
        trip_id = out["trip_id"]
        days = trip_repository.trip_days_list(trip_id)
        self.assertEqual(len(days), 5)
        aug5 = next(d for d in days if str(d["date"])[:10] == "2026-08-05")
        aug5_original_id = aug5["id"]

        # Step 2: edit Aug 5 with operator content
        trip_repository.trip_day_update(
            aug5_original_id,
            title="Mountrail County Courthouse",
            main_location="Stanley, North Dakota",
            morning_notes="Reviewed mineral deeds and probate records.",
        )

        # Step 3: move start_date earlier → 2 new days prepended
        patch_out = trips.patch_trip(trip_id, _Req(
            start_date="2026-08-01"))
        self.assertNotIn("days_warning", patch_out)

        # Assert calendar shape: 7 days, chronological, sequential 1..7
        days_after = trip_repository.trip_days_list(trip_id)
        self.assertEqual(len(days_after), 7)
        dates_after = [str(d["date"])[:10] for d in days_after]
        self.assertEqual(dates_after, [
            "2026-08-01", "2026-08-02", "2026-08-03",
            "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07"])
        indexes_after = [d["day_index"] for d in days_after]
        self.assertEqual(indexes_after, [1, 2, 3, 4, 5, 6, 7],
                         "day_index must be sequential after renumber; "
                         "the pre-fix bug produced [1, 2, 1, 2, 3, 4, 5]")

        # Aug 5 is now Day 5 (was Day 3 before the prepend)
        aug5_after = next(d for d in days_after
                          if str(d["date"])[:10] == "2026-08-05")
        self.assertEqual(aug5_after["day_index"], 5)
        # Same row (not replaced).
        self.assertEqual(aug5_after["id"], aug5_original_id)
        # Operator content preserved.
        self.assertEqual(aug5_after["title"], "Mountrail County Courthouse")
        self.assertEqual(aug5_after["main_location"], "Stanley, North Dakota")
        self.assertIn("mineral deeds",
                      aug5_after.get("morning_notes") or "")

    def test_shrinking_dates_partitions_preserved_cards(self):
        """ChatGPT review §2: create Aug 1–9, edit content on Aug 2 and
        Aug 8, shrink to Aug 3–7. Verify:
          * list_trip_days returns days=[Aug 3..7] renumbered Day 1..5
          * preserved=[Aug 1, 2, 8, 9] kept, NOT renumbered
          * Aug 2 + Aug 8 operator content preserved in `preserved`
          * No duplicate day_index values in the current-window list
          * Correct total = 9 = len(days) + len(preserved)
        """
        # Step 1: create Aug 1–9 → 9 day cards
        out = trips.create_trip(_Req(
            person_id=self.person_id,
            title="Wide window then shrink",
            start_date="2026-08-01",
            end_date="2026-08-09"))
        trip_id = out["trip_id"]
        all_days = trip_repository.trip_days_list(trip_id)
        self.assertEqual(len(all_days), 9)

        # Step 2: edit Aug 2 and Aug 8 with operator content
        aug2_row = next(d for d in all_days
                        if str(d["date"])[:10] == "2026-08-02")
        aug8_row = next(d for d in all_days
                        if str(d["date"])[:10] == "2026-08-08")
        trip_repository.trip_day_update(
            aug2_row["id"], title="Notes I want kept",
            morning_notes="Aug 2 content")
        trip_repository.trip_day_update(
            aug8_row["id"], title="More notes I want kept",
            morning_notes="Aug 8 content")

        # Step 3: shrink to Aug 3–7. Both dates change → PATCH triggers
        # the auto-reconcile path but should NOT delete Aug 1/2/8/9.
        patch_out = trips.patch_trip(trip_id, _Req(
            start_date="2026-08-03", end_date="2026-08-07"))
        self.assertNotIn("days_warning", patch_out)

        # Step 4: verify partitioned response via the router endpoint
        # (list_trip_days is the caller the FE consumes).
        endpoint_out = trips.list_trip_days(trip_id)
        days = endpoint_out["days"]
        preserved = endpoint_out["preserved"]

        # Current window: exactly Aug 3..7, day_index 1..5
        self.assertEqual(len(days), 5)
        dates_in_window = [str(d["date"])[:10] for d in days]
        self.assertEqual(dates_in_window, [
            "2026-08-03", "2026-08-04", "2026-08-05",
            "2026-08-06", "2026-08-07"])
        indexes_in_window = [d["day_index"] for d in days]
        self.assertEqual(indexes_in_window, [1, 2, 3, 4, 5])
        # No duplicates (this is the whole point of the partition).
        self.assertEqual(len(set(indexes_in_window)), len(days))

        # Preserved: Aug 1, 2, 8, 9 kept (no deletion)
        preserved_dates = sorted(str(d["date"])[:10] for d in preserved)
        self.assertEqual(preserved_dates, [
            "2026-08-01", "2026-08-02", "2026-08-08", "2026-08-09"])

        # Operator content on Aug 2 and Aug 8 must be intact
        aug2_after = next(d for d in preserved
                          if str(d["date"])[:10] == "2026-08-02")
        aug8_after = next(d for d in preserved
                          if str(d["date"])[:10] == "2026-08-08")
        self.assertEqual(aug2_after["title"], "Notes I want kept")
        self.assertIn("Aug 2 content",
                      aug2_after.get("morning_notes") or "")
        self.assertEqual(aug8_after["title"], "More notes I want kept")
        self.assertIn("Aug 8 content",
                      aug8_after.get("morning_notes") or "")

        # Endpoint arithmetic sanity
        self.assertEqual(endpoint_out["count"], 5)
        self.assertEqual(endpoint_out["preserved_count"], 4)
        self.assertEqual(endpoint_out["total"], 9)
        self.assertEqual(endpoint_out["trip_window"], {
            "start_date": "2026-08-03",
            "end_date": "2026-08-07",
        })

    def test_renumber_preserves_updated_at_on_index_only_change(self):
        """ChatGPT review §8: structural calendar reshuffles must NOT
        mutate updated_at. Create Aug 3–7, snapshot Aug 5's updated_at,
        move start to Aug 1 (which renumbers Aug 5 from Day 3 to Day 5
        without touching any operator content). updated_at must be
        unchanged."""
        import time as _time
        out = trips.create_trip(_Req(
            person_id=self.person_id,
            title="Renumber updated_at",
            start_date="2026-08-03",
            end_date="2026-08-07"))
        trip_id = out["trip_id"]
        days = trip_repository.trip_days_list(trip_id)
        aug5 = next(d for d in days if str(d["date"])[:10] == "2026-08-05")
        original_updated_at = aug5["updated_at"]
        original_id = aug5["id"]
        # Sleep past 1s so _now() would produce a demonstrably different
        # timestamp if the bug regressed.
        _time.sleep(1.05)
        trips.patch_trip(trip_id, _Req(start_date="2026-08-01"))
        aug5_after = next(
            d for d in trip_repository.trip_days_list(trip_id)
            if d["id"] == original_id)
        # Same row, renumbered
        self.assertEqual(aug5_after["day_index"], 5)
        # updated_at UNCHANGED (structural renumber is not an edit)
        self.assertEqual(aug5_after["updated_at"], original_updated_at,
                         "renumber-only pass must not mutate updated_at")

    def test_earlier_start_then_extend_end_preserves_content(self):
        """After the prepend, extend the end date. All indexes stay
        correct; Aug 5's content still there."""
        out = trips.create_trip(_Req(
            person_id=self.person_id, title="Extend after prepend",
            start_date="2026-08-03", end_date="2026-08-07"))
        trip_id = out["trip_id"]
        aug5 = next(d for d in trip_repository.trip_days_list(trip_id)
                    if str(d["date"])[:10] == "2026-08-05")
        trip_repository.trip_day_update(
            aug5["id"], title="Mountrail County Courthouse")

        trips.patch_trip(trip_id, _Req(start_date="2026-08-01"))
        trips.patch_trip(trip_id, _Req(end_date="2026-08-09"))
        days = trip_repository.trip_days_list(trip_id)
        self.assertEqual(len(days), 9)
        self.assertEqual([d["day_index"] for d in days],
                         [1, 2, 3, 4, 5, 6, 7, 8, 9])
        aug5_final = next(d for d in days
                          if str(d["date"])[:10] == "2026-08-05")
        self.assertEqual(aug5_final["title"], "Mountrail County Courthouse")
        self.assertEqual(aug5_final["day_index"], 5)


# ── (D) Full live-style sequence ────────────────────────────────────
class NorthDakotaLiveSequenceTest(_LiveStyleBase):
    """Replicate the exact test_nd_trip_api.py flow in-process against
    real DB, no HTTP. If this passes green, the WSL/SQLite lock-leak
    class is closed for this sequence."""

    def test_full_sequence_completes_without_locks_or_500s(self):
        # 1. Create ND Aug 3–7 trip
        out = trips.create_trip(_Req(
            person_id=self.person_id,
            title="API Test — North Dakota Mineral Records",
            start_date="2026-08-03",
            end_date="2026-08-07",
            summary="Bismarck and Stanley."))
        trip_id = out["trip_id"]
        self.assertNotIn("days_warning", out)
        days = trip_repository.trip_days_list(trip_id)
        self.assertEqual(len(days), 5)

        # 2. Edit Aug 5
        aug5 = next(d for d in days if str(d["date"])[:10] == "2026-08-05")
        trip_repository.trip_day_update(
            aug5["id"], title="Mountrail County Courthouse",
            main_location="Stanley, North Dakota")

        # 3. Move start earlier
        out2 = trips.patch_trip(trip_id, _Req(start_date="2026-08-01"))
        self.assertNotIn("days_warning", out2)
        self.assertEqual(
            len(trip_repository.trip_days_list(trip_id)), 7)

        # 4. Extend end
        out3 = trips.patch_trip(trip_id, _Req(end_date="2026-08-09"))
        self.assertNotIn("days_warning", out3)
        days_after = trip_repository.trip_days_list(trip_id)
        self.assertEqual(len(days_after), 9)
        self.assertEqual([d["day_index"] for d in days_after],
                         [1, 2, 3, 4, 5, 6, 7, 8, 9])

        # 5. Reversed dates → warning, trip still saves
        out4 = trips.patch_trip(trip_id, _Req(
            title="Warning test",
            start_date="2026-08-10",
            end_date="2026-08-05"))
        self.assertIn("days_warning", out4)
        self.assertIn("before", out4["days_warning"].lower())

        # 6. Restore valid dates — MUST not 500
        out5 = trips.patch_trip(trip_id, _Req(
            start_date="2026-08-01", end_date="2026-08-09"))
        self.assertNotIn("days_warning", out5)
        days_restored = trip_repository.trip_days_list(trip_id)
        self.assertEqual(len(days_restored), 9)

        # 7. Delete — MUST not 500
        deleted = trip_repository.trip_delete(trip_id)
        self.assertTrue(deleted)
        self.assertIsNone(trip_repository.trip_get(trip_id))


if __name__ == "__main__":
    unittest.main()
