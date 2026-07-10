"""WO-TRAVEL-DOC-UI-LAB-01 — trip_days layer tests.

Covers: migration 0027 applies; generate-from-dates creates one row per
date (idempotent, day_index/date ordered, UNIQUE(trip_id,date)); region
auto-link only when exactly one region covers the date; partial update
with clear flags; cross-trip region/stop scope rejected on PATCH; honest
per-day counts (photos by taken date, scoped notes, zeros otherwise).

Offline fastapi/pydantic stub pattern (same as test_trip_patch.py).
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


class _DayReq:
    """TripDayPatch stand-in — clear flags default False, fields None."""

    def __init__(self, **kw):
        for f in ("title", "main_location", "lodging_base",
                  "trip_region_id", "trip_stop_id", "morning_notes",
                  "afternoon_notes", "evening_notes", "places_visited",
                  "meals"):
            setattr(self, f, None)
        for f in ("clear_title", "clear_main_location",
                  "clear_lodging_base", "clear_morning_notes",
                  "clear_afternoon_notes", "clear_evening_notes",
                  "clear_region", "clear_stop"):
            setattr(self, f, False)
        self.__dict__.update(kw)


class _TripDaysCase(unittest.TestCase):
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
            "created_at, updated_at) VALUES (?, 'Days Test', "
            "'1962-12-24', '2026-07-10', '2026-07-10');",
            (self.person_id,),
        )
        con.commit()
        con.close()
        self.trip_id = trip_repository.trip_create(
            person_id=self.person_id, title="Five Day Trip",
            start_date="2026-05-01", end_date="2026-05-05",
            summary="days fixture")

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

    def _region(self, title="Bavaria", start=None, end=None):
        return trip_repository.region_create(
            trip_id=self.trip_id, title=title, ord_=0,
            start_date=start, end_date=end)

    def _stop(self, region_id, name="Munich"):
        return trip_repository.stop_create(
            trip_id=self.trip_id, trip_region_id=region_id,
            location_name=name)


class MigrationTest(_TripDaysCase):
    def test_trip_days_table_exists(self):
        con = sqlite3.connect(str(self.db_path))
        try:
            row = con.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' "
                "AND name='trip_days'").fetchone()
            self.assertIsNotNone(row, "migration 0027 did not apply")
            self.assertIn("UNIQUE (trip_id, date)", row[0])
            idx = con.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND name='idx_trip_days_trip'").fetchone()
            self.assertIsNotNone(idx)
        finally:
            con.close()

    def test_unique_trip_date_constraint(self):
        trip_repository.trip_days_generate(self.trip_id)
        days = trip_repository.trip_days_list(self.trip_id)
        con = sqlite3.connect(str(self.db_path))
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute(
                    "INSERT INTO trip_days (id, trip_id, day_index, date) "
                    "VALUES (?, ?, 99, ?)",
                    (str(uuid.uuid4()), self.trip_id, days[0]["date"]))
        finally:
            con.close()


class GenerateTest(_TripDaysCase):
    def test_generate_five_day_trip(self):
        out = trips.generate_trip_days(self.trip_id)
        self.assertEqual(out["created"], 5)
        self.assertEqual(out["total"], 5)
        days = out["days"]
        self.assertEqual([d["day_index"] for d in days], [1, 2, 3, 4, 5])
        self.assertEqual(
            [d["date"] for d in days],
            ["2026-05-01", "2026-05-02", "2026-05-03",
             "2026-05-04", "2026-05-05"])

    def test_generate_idempotent(self):
        trips.generate_trip_days(self.trip_id)
        # Edit one day, then re-generate: nothing is created or clobbered.
        day1 = trip_repository.trip_days_list(self.trip_id)[0]
        trip_repository.trip_day_update(day1["id"], title="Arrival day")
        out = trips.generate_trip_days(self.trip_id)
        self.assertEqual(out["created"], 0)
        self.assertEqual(out["total"], 5)
        again = trip_repository.trip_day_get(day1["id"])
        self.assertEqual(again["title"], "Arrival day")

    def test_generate_fills_gap_only(self):
        trips.generate_trip_days(self.trip_id)
        days = trip_repository.trip_days_list(self.trip_id)
        con = sqlite3.connect(str(self.db_path))
        try:
            con.execute("DELETE FROM trip_days WHERE id = ?",
                        (days[2]["id"],))
            con.commit()
        finally:
            con.close()
        out = trips.generate_trip_days(self.trip_id)
        self.assertEqual(out["created"], 1)
        self.assertEqual(out["total"], 5)

    def test_generate_without_dates_422(self):
        bare = trip_repository.trip_create(
            person_id=self.person_id, title="No Dates")
        with self.assertRaises(HTTPException) as ctx:
            trips.generate_trip_days(bare)
        self.assertEqual(ctx.exception.status_code, 422)

    def test_generate_unknown_trip_404(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.generate_trip_days("no-such-trip")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_region_auto_link_when_exactly_one_covers(self):
        covering = self._region("Bavaria", "2026-05-02", "2026-05-03")
        self._region("Undated Region")  # no dates -> never auto-links
        trips.generate_trip_days(self.trip_id)
        days = trip_repository.trip_days_list(self.trip_id)
        by_date = {d["date"]: d for d in days}
        self.assertIsNone(by_date["2026-05-01"]["trip_region_id"])
        self.assertEqual(by_date["2026-05-02"]["trip_region_id"], covering)
        self.assertEqual(by_date["2026-05-03"]["trip_region_id"], covering)
        self.assertIsNone(by_date["2026-05-04"]["trip_region_id"])

    def test_region_auto_link_skipped_when_ambiguous(self):
        self._region("Bavaria", "2026-05-01", "2026-05-05")
        self._region("Austria", "2026-05-02", "2026-05-04")
        trips.generate_trip_days(self.trip_id)
        by_date = {d["date"]: d
                   for d in trip_repository.trip_days_list(self.trip_id)}
        # 05-03 is covered by BOTH regions -> honest NULL, not a guess.
        self.assertIsNone(by_date["2026-05-03"]["trip_region_id"])
        # 05-01 is covered by exactly one -> linked.
        self.assertIsNotNone(by_date["2026-05-01"]["trip_region_id"])


class UpdateTest(_TripDaysCase):
    def setUp(self):
        super().setUp()
        trips.generate_trip_days(self.trip_id)
        self.day = trip_repository.trip_days_list(self.trip_id)[0]

    def test_patch_fields_and_lists(self):
        out = trips.patch_trip_day(self.day["id"], _DayReq(
            title="Munich arrival", main_location="Munich, Germany",
            lodging_base="Hotel Königshof",
            morning_notes="Deutsches Museum",
            places_visited=["Deutsches Museum", "Marienplatz"],
            meals=["Beer hall dinner"]))
        self.assertTrue(out["ok"])
        day = out["day"]
        self.assertEqual(day["title"], "Munich arrival")
        self.assertEqual(day["lodging_base"], "Hotel Königshof")
        self.assertEqual(day["places_visited_json"],
                         ["Deutsches Museum", "Marienplatz"])
        self.assertEqual(day["meals_json"], ["Beer hall dinner"])
        # Untouched fields stay None.
        self.assertIsNone(day["evening_notes"])

    def test_clear_flags_null_fields(self):
        trips.patch_trip_day(self.day["id"], _DayReq(
            title="x", lodging_base="y", morning_notes="z"))
        out = trips.patch_trip_day(self.day["id"], _DayReq(
            clear_title=True, clear_lodging_base=True,
            clear_morning_notes=True))
        day = out["day"]
        self.assertIsNone(day["title"])
        self.assertIsNone(day["lodging_base"])
        self.assertIsNone(day["morning_notes"])

    def test_none_never_clears(self):
        trips.patch_trip_day(self.day["id"], _DayReq(title="keep me"))
        trips.patch_trip_day(self.day["id"], _DayReq(
            main_location="Munich"))
        day = trip_repository.trip_day_get(self.day["id"])
        self.assertEqual(day["title"], "keep me")

    def test_empty_patch_400(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.patch_trip_day(self.day["id"], _DayReq())
        self.assertEqual(ctx.exception.status_code, 400)

    def test_unknown_day_404(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.patch_trip_day("no-such-day", _DayReq(title="x"))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_stop_link_backfills_region(self):
        region = self._region("Bavaria")
        stop = self._stop(region)
        out = trips.patch_trip_day(self.day["id"],
                                   _DayReq(trip_stop_id=stop))
        self.assertEqual(out["day"]["trip_stop_id"], stop)
        self.assertEqual(out["day"]["trip_region_id"], region)

    def test_clear_region_and_stop(self):
        region = self._region("Bavaria")
        stop = self._stop(region)
        trips.patch_trip_day(self.day["id"], _DayReq(trip_stop_id=stop))
        out = trips.patch_trip_day(self.day["id"], _DayReq(
            clear_region=True, clear_stop=True))
        self.assertIsNone(out["day"]["trip_region_id"])
        self.assertIsNone(out["day"]["trip_stop_id"])

    def test_cross_trip_stop_rejected(self):
        other_trip = trip_repository.trip_create(
            person_id=self.person_id, title="Other Trip",
            start_date="2026-06-01", end_date="2026-06-02")
        other_region = trip_repository.region_create(
            trip_id=other_trip, title="Elsewhere", ord_=0)
        other_stop = trip_repository.stop_create(
            trip_id=other_trip, trip_region_id=other_region,
            location_name="Elsewhere City")
        with self.assertRaises(HTTPException) as ctx:
            trips.patch_trip_day(self.day["id"],
                                 _DayReq(trip_stop_id=other_stop))
        self.assertEqual(ctx.exception.status_code, 400)
        day = trip_repository.trip_day_get(self.day["id"])
        self.assertIsNone(day["trip_stop_id"])

    def test_cross_trip_region_rejected(self):
        other_trip = trip_repository.trip_create(
            person_id=self.person_id, title="Other Trip 2")
        other_region = trip_repository.region_create(
            trip_id=other_trip, title="Foreign Region", ord_=0)
        with self.assertRaises(HTTPException) as ctx:
            trips.patch_trip_day(self.day["id"],
                                 _DayReq(trip_region_id=other_region))
        self.assertEqual(ctx.exception.status_code, 400)


class CountsTest(_TripDaysCase):
    def setUp(self):
        super().setUp()
        trips.generate_trip_days(self.trip_id)
        self.days = trip_repository.trip_days_list(self.trip_id)

    def _photo_row(self, photo_id, date_value=None):
        con = sqlite3.connect(str(self.db_path))
        try:
            con.execute(
                "INSERT INTO photos (id, narrator_id, image_path, "
                "file_hash, date_value) VALUES (?, ?, '/tmp/p.jpg', "
                "?, ?)",
                (photo_id, self.person_id, "hash-" + photo_id,
                 date_value))
            con.commit()
        finally:
            con.close()

    def test_photo_counts_match_taken_date(self):
        pid = str(uuid.uuid4())
        self._photo_row(pid)
        trip_repository.photo_link_upsert(
            trip_id=self.trip_id, photo_id=pid,
            taken_at="2026-05-02T10:30:00Z",
            assignment_method="exif_time", cluster_confidence=0.9)
        out = trips.list_trip_days(self.trip_id)
        by_date = {d["date"]: d for d in out["days"]}
        self.assertEqual(by_date["2026-05-02"]["counts"]["photos"], 1)
        self.assertEqual(by_date["2026-05-01"]["counts"]["photos"], 0)

    def test_photo_counts_fall_back_to_photo_date_value(self):
        pid = str(uuid.uuid4())
        self._photo_row(pid, date_value="2026-05-04")
        trip_repository.photo_link_upsert(
            trip_id=self.trip_id, photo_id=pid,
            assignment_method="exif_time", cluster_confidence=0.6)
        out = trips.list_trip_days(self.trip_id)
        by_date = {d["date"]: d for d in out["days"]}
        self.assertEqual(by_date["2026-05-04"]["counts"]["photos"], 1)

    def test_scoped_counts_zero_without_day_link(self):
        # Notes/sources/public-context are NOT date-scoped in schema:
        # an unlinked day must report honest zeros, not trip totals.
        trip_repository.location_note_create(
            trip_id=self.trip_id, note_text="trip-level note",
            source_type="operator")
        out = trips.list_trip_days(self.trip_id)
        for d in out["days"]:
            self.assertEqual(d["counts"]["notes"], 0)
            self.assertEqual(d["counts"]["sources"], 0)
            self.assertEqual(d["counts"]["public_context"], 0)

    def test_scoped_counts_via_linked_stop(self):
        region = self._region("Bavaria")
        stop = self._stop(region)
        trips.patch_trip_day(self.days[0]["id"],
                             _DayReq(trip_stop_id=stop))
        trip_repository.location_note_create(
            trip_id=self.trip_id, note_text="Munich fish story",
            source_type="operator", trip_stop_id=stop,
            trip_region_id=region)
        trip_repository.source_create(
            trip_id=self.trip_id, source_type="ticket",
            title="Museum ticket", trip_stop_id=stop,
            trip_region_id=region)
        out = trips.list_trip_days(self.trip_id)
        day0 = out["days"][0]
        self.assertEqual(day0["counts"]["notes"], 1)
        self.assertEqual(day0["counts"]["sources"], 1)
        # Other days stay at zero.
        self.assertEqual(out["days"][1]["counts"]["notes"], 0)

    def test_scoped_counts_via_linked_region_exclude_stop_rows(self):
        region = self._region("Bavaria")
        stop = self._stop(region)
        trips.patch_trip_day(self.days[1]["id"],
                             _DayReq(trip_region_id=region))
        trip_repository.location_note_create(
            trip_id=self.trip_id, note_text="region-level note",
            source_type="operator", trip_region_id=region)
        trip_repository.location_note_create(
            trip_id=self.trip_id, note_text="stop-level note",
            source_type="operator", trip_region_id=region,
            trip_stop_id=stop)
        out = trips.list_trip_days(self.trip_id)
        day1 = out["days"][1]
        # Region-linked day counts region-scoped rows only (stop rows
        # belong to stop-linked days).
        self.assertEqual(day1["counts"]["notes"], 1)

    def test_list_unknown_trip_404(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.list_trip_days("no-such-trip")
        self.assertEqual(ctx.exception.status_code, 404)


class _PhotoLinksReq:
    """TripDayPhotoLinksReq stand-in."""

    def __init__(self, ids):
        self.photo_link_ids = list(ids)


class DayPhotoLinkTest(_TripDaysCase):
    """WO-TRAVEL-DOC-UI-LAB-02 — migration 0028 day photo attach/detach."""

    def setUp(self):
        super().setUp()
        trips.generate_trip_days(self.trip_id)
        self.days = trip_repository.trip_days_list(self.trip_id)

    def _photo_row(self, photo_id, date_value=None):
        con = sqlite3.connect(str(self.db_path))
        try:
            con.execute(
                "INSERT INTO photos (id, narrator_id, image_path, "
                "file_hash, date_value) VALUES (?, ?, '/tmp/p.jpg', "
                "?, ?)",
                (photo_id, self.person_id, "hash-" + photo_id,
                 date_value))
            con.commit()
        finally:
            con.close()

    def _link(self, taken_at=None):
        pid = str(uuid.uuid4())
        self._photo_row(pid)
        return trip_repository.photo_link_upsert(
            trip_id=self.trip_id, photo_id=pid, taken_at=taken_at,
            assignment_method="exif_time", cluster_confidence=0.9)

    def test_migration_0028_columns_exist(self):
        con = sqlite3.connect(str(self.db_path))
        try:
            link_cols = {r[1] for r in con.execute(
                "PRAGMA table_info(trip_photo_links)")}
            note_cols = {r[1] for r in con.execute(
                "PRAGMA table_info(trip_location_notes)")}
        finally:
            con.close()
        self.assertIn("trip_day_id", link_cols,
                      "migration 0028 did not apply to trip_photo_links")
        self.assertIn("trip_day_id", note_cols,
                      "migration 0028 did not apply to trip_location_notes")

    def test_link_and_unlink_photos_to_day(self):
        lid = self._link()
        day = self.days[0]
        out = trips.link_day_photos(self.trip_id, day["id"],
                                    _PhotoLinksReq([lid]))
        self.assertTrue(out["ok"])
        self.assertEqual(out["updated"], 1)
        row = trip_repository.photo_link_get(lid)
        self.assertEqual(row["trip_day_id"], day["id"])
        out = trips.unlink_day_photos(self.trip_id, day["id"],
                                      _PhotoLinksReq([lid]))
        self.assertTrue(out["ok"])
        row = trip_repository.photo_link_get(lid)
        self.assertIsNone(row["trip_day_id"])

    def test_link_rejects_cross_trip_photo_link(self):
        other_trip = trip_repository.trip_create(
            person_id=self.person_id, title="Other Trip",
            start_date="2026-06-01", end_date="2026-06-02")
        pid = str(uuid.uuid4())
        self._photo_row(pid)
        foreign_link = trip_repository.photo_link_upsert(
            trip_id=other_trip, photo_id=pid,
            assignment_method="exif_time")
        with self.assertRaises(HTTPException) as ctx:
            trips.link_day_photos(self.trip_id, self.days[0]["id"],
                                  _PhotoLinksReq([foreign_link]))
        self.assertEqual(ctx.exception.status_code, 400)
        row = trip_repository.photo_link_get(foreign_link)
        self.assertIsNone(row["trip_day_id"])

    def test_link_rejects_cross_trip_day(self):
        other_trip = trip_repository.trip_create(
            person_id=self.person_id, title="Other Trip 2",
            start_date="2026-06-01", end_date="2026-06-02")
        trip_repository.trip_days_generate(other_trip)
        other_day = trip_repository.trip_days_list(other_trip)[0]
        lid = self._link()
        with self.assertRaises(HTTPException) as ctx:
            trips.link_day_photos(self.trip_id, other_day["id"],
                                  _PhotoLinksReq([lid]))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_link_partial_failure_writes_nothing(self):
        # One good + one cross-trip id -> the whole batch is rejected,
        # the good link stays unattached (single transaction).
        good = self._link()
        other_trip = trip_repository.trip_create(
            person_id=self.person_id, title="Other Trip 3")
        pid = str(uuid.uuid4())
        self._photo_row(pid)
        bad = trip_repository.photo_link_upsert(
            trip_id=other_trip, photo_id=pid,
            assignment_method="exif_time")
        with self.assertRaises(HTTPException):
            trips.link_day_photos(self.trip_id, self.days[0]["id"],
                                  _PhotoLinksReq([good, bad]))
        self.assertIsNone(trip_repository.photo_link_get(good)["trip_day_id"])

    def test_link_empty_ids_422(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.link_day_photos(self.trip_id, self.days[0]["id"],
                                  _PhotoLinksReq([]))
        self.assertEqual(ctx.exception.status_code, 422)

    def test_counts_prefer_trip_day_id_over_date_match(self):
        # Photo TAKEN on day 2's date but attached to day 1: it counts
        # on day 1 (operator truth) and NOT on day 2 (no double count).
        lid = self._link(taken_at="2026-05-02T10:30:00Z")
        day1 = self.days[0]   # 2026-05-01
        trips.link_day_photos(self.trip_id, day1["id"],
                              _PhotoLinksReq([lid]))
        out = trips.list_trip_days(self.trip_id)
        by_date = {d["date"]: d for d in out["days"]}
        self.assertEqual(by_date["2026-05-01"]["counts"]["photos"], 1)
        self.assertEqual(by_date["2026-05-02"]["counts"]["photos"], 0)

    def test_counts_fall_back_to_date_match_for_unattached(self):
        self._link(taken_at="2026-05-03T09:00:00Z")   # unattached
        lid = self._link(taken_at="2026-05-03T12:00:00Z")
        day3 = self.days[2]   # 2026-05-03
        trips.link_day_photos(self.trip_id, day3["id"],
                              _PhotoLinksReq([lid]))
        out = trips.list_trip_days(self.trip_id)
        by_date = {d["date"]: d for d in out["days"]}
        # attached (1) + date-matched unattached (1) on the same day.
        self.assertEqual(by_date["2026-05-03"]["counts"]["photos"], 2)

    def test_day_scoped_note_counts_on_its_day(self):
        day2 = self.days[1]
        trip_repository.location_note_create(
            trip_id=self.trip_id, note_text="Day-scoped story",
            source_type="operator", trip_day_id=day2["id"])
        out = trips.list_trip_days(self.trip_id)
        self.assertEqual(out["days"][1]["counts"]["notes"], 1)
        self.assertEqual(out["days"][0]["counts"]["notes"], 0)

    def test_create_location_note_endpoint_validates_day(self):
        class _NoteReq:
            note_text = "in-lab day note"
            note_title = None
            trip_region_id = None
            trip_stop_id = None
            trip_day_id = None
            source_type = "operator"
            source_ref = None
            include_in_memoir = False
            include_in_interview_context = False
            target_language = "en"

        req = _NoteReq()
        req.trip_day_id = self.days[0]["id"]
        out = trips.create_location_note(self.trip_id, req)
        self.assertEqual(out["note"]["trip_day_id"], self.days[0]["id"])

        other_trip = trip_repository.trip_create(
            person_id=self.person_id, title="Other Trip 4",
            start_date="2026-06-01", end_date="2026-06-02")
        trip_repository.trip_days_generate(other_trip)
        req2 = _NoteReq()
        req2.trip_day_id = trip_repository.trip_days_list(other_trip)[0]["id"]
        with self.assertRaises(HTTPException) as ctx:
            trips.create_location_note(self.trip_id, req2)
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
