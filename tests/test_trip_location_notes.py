"""WO-TRAVEL-DOC-STORY-LAYER-01 — trip_location_notes story backbone.

Covers the recreated table (migration 0019), repo accessors, and the four
endpoints. Promotion flags default OFF; nothing enters memoir/interview
context without an explicit flag flip.
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


def _note_create_req(**kw):
    base = dict(note_text="a memory", note_title=None, trip_region_id=None,
               trip_stop_id=None, trip_day_id=None, source_type="operator",
               source_ref=None,
               include_in_memoir=False, include_in_interview_context=False,
               target_language="en")
    base.update(kw)
    return _Req(**base)


def _note_patch_req(**kw):
    base = dict(note_title=None, note_text=None, source_type=None,
               source_ref=None, include_in_memoir=None,
               include_in_interview_context=None, ord=None, clear_title=False)
    base.update(kw)
    return _Req(**base)


class _LocationNotesCase(unittest.TestCase):
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
        con.execute(
            "INSERT INTO people (id, display_name, date_of_birth, created_at, "
            "updated_at) VALUES (?, 'Notes Test', '1962-12-24', "
            "'2026-07-08', '2026-07-08');",
            (self.person_id,),
        )
        con.commit()
        con.close()
        self.trip_id = trip_repository.trip_create(self.person_id, "Spring 2026")
        self.region_id = trip_repository.region_create(self.trip_id, "Germany")
        self.stop_id = trip_repository.stop_create(self.trip_id, self.region_id, "Munich")
        # A second trip to prove cross-trip validation.
        self.other_trip = trip_repository.trip_create(self.person_id, "Other")
        self.other_region = trip_repository.region_create(self.other_trip, "Elsewhere")
        self.other_stop = trip_repository.stop_create(self.other_trip, self.other_region, "X")

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

    # ── migration shape ──────────────────────────────────────────────────

    def test_table_has_story_columns(self):
        con = sqlite3.connect(str(self.db_path))
        cols = {r[1] for r in con.execute("PRAGMA table_info(trip_location_notes)")}
        con.close()
        for c in ("note_title", "note_text", "source_type", "source_ref",
                  "include_in_memoir", "include_in_interview_context", "ord"):
            self.assertIn(c, cols)

    def test_draft_source_type_allowed(self):
        nid = trip_repository.location_note_create(
            self.trip_id, "draft text", source_type="draft")
        self.assertEqual(trip_repository.location_note_get(nid)["source_type"], "draft")

    # ── create + scope ───────────────────────────────────────────────────

    def test_create_defaults_flags_off(self):
        out = trips.create_location_note(self.trip_id, _note_create_req(
            note_text="Germany was the first leg", trip_region_id=self.region_id))
        note = out["note"]
        self.assertEqual(note["include_in_memoir"], 0)
        self.assertEqual(note["include_in_interview_context"], 0)
        self.assertEqual(note["source_type"], "operator")

    def test_scope_filtering(self):
        trips.create_location_note(self.trip_id, _note_create_req(
            note_text="trip-level"))
        trips.create_location_note(self.trip_id, _note_create_req(
            note_text="region", trip_region_id=self.region_id))
        trips.create_location_note(self.trip_id, _note_create_req(
            note_text="stop", trip_region_id=self.region_id, trip_stop_id=self.stop_id))
        allnotes = trips.list_location_notes(self.trip_id)["notes"]
        self.assertEqual(len(allnotes), 3)
        region_only = trips.list_location_notes(self.trip_id, region_id=self.region_id)["notes"]
        self.assertEqual([n["note_text"] for n in region_only], ["region"])
        stop_only = trips.list_location_notes(self.trip_id, stop_id=self.stop_id)["notes"]
        self.assertEqual([n["note_text"] for n in stop_only], ["stop"])

    def test_create_rejects_stop_from_other_trip(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.create_location_note(self.trip_id, _note_create_req(
                note_text="x", trip_stop_id=self.other_stop))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_create_rejects_region_from_other_trip(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.create_location_note(self.trip_id, _note_create_req(
                note_text="x", trip_region_id=self.other_region))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_create_rejects_empty_text(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.create_location_note(self.trip_id, _note_create_req(note_text="  "))
        self.assertEqual(ctx.exception.status_code, 422)

    def test_create_rejects_bad_source_type(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.create_location_note(self.trip_id, _note_create_req(
                note_text="x", source_type="bogus"))
        self.assertEqual(ctx.exception.status_code, 422)

    # ── patch (promotion) + delete ───────────────────────────────────────

    def test_patch_promotes_to_memoir(self):
        out = trips.create_location_note(self.trip_id, _note_create_req(note_text="m"))
        nid = out["note_id"]
        res = trips.patch_location_note(nid, _note_patch_req(include_in_memoir=True))
        self.assertEqual(res["note"]["include_in_memoir"], 1)
        # interview context untouched (still off)
        self.assertEqual(res["note"]["include_in_interview_context"], 0)

    def test_patch_clear_title(self):
        out = trips.create_location_note(self.trip_id, _note_create_req(
            note_text="m", note_title="Arrival"))
        nid = out["note_id"]
        res = trips.patch_location_note(nid, _note_patch_req(clear_title=True))
        self.assertIsNone(res["note"]["note_title"])

    def test_patch_unknown_note_404(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.patch_location_note("nope", _note_patch_req(note_text="x"))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_delete_is_soft_hide(self):
        # WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01: DELETE now soft-hides —
        # the row is preserved and restorable; only an explicit purge
        # with the exact-id confirmation removes it physically.
        out = trips.create_location_note(self.trip_id, _note_create_req(note_text="m"))
        nid = out["note_id"]
        res = trips.delete_location_note(nid)
        self.assertTrue(res["hidden"])
        self.assertFalse(res["purged"])
        self.assertTrue(res["restorable"])
        row = trip_repository.location_note_get(nid)
        self.assertIsNotNone(row)          # row preserved
        self.assertEqual(row["hidden"], 1)
        # Purge with the exact id removes it for real.
        res2 = trips.delete_location_note(nid, purge=True, confirm_id=nid)
        self.assertTrue(res2["purged"])
        self.assertIsNone(trip_repository.location_note_get(nid))

    def test_delete_unknown_404(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.delete_location_note("nope")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_region_delete_nulls_note_scope(self):
        # FK ON DELETE SET NULL — deleting a region leaves its notes (scope
        # nulled) rather than cascading them away.
        out = trips.create_location_note(self.trip_id, _note_create_req(
            note_text="region note", trip_region_id=self.region_id))
        nid = out["note_id"]
        # M1: this region has a stop; deleting it is an explicit cascade.
        trip_repository.region_delete(self.region_id, force=True)
        note = trip_repository.location_note_get(nid)
        self.assertIsNotNone(note)
        self.assertIsNone(note["trip_region_id"])


    # ── memoir preview inclusion (Pass 3) ────────────────────────────────

    def test_memoir_preview_only_includes_promoted_notes(self):
        # One promoted stop note, one un-promoted — only the promoted one
        # reaches the memoir preview.
        trip_repository.location_note_create(
            self.trip_id, "Munich first impressions", note_title="Arrival",
            trip_region_id=self.region_id, trip_stop_id=self.stop_id,
            include_in_memoir=True)
        trip_repository.location_note_create(
            self.trip_id, "private operator note",
            trip_region_id=self.region_id, trip_stop_id=self.stop_id,
            include_in_memoir=False)
        preview = trip_repository.trip_memoir_preview(self.trip_id)
        region = preview["part_one_journey_in_order"][0]
        stop = region["stops"][0]
        texts = [n["note_text"] for n in stop["story_notes"]]
        self.assertIn("Munich first impressions", texts)
        self.assertNotIn("private operator note", texts)

    def test_memoir_preview_scopes_notes(self):
        trip_repository.location_note_create(
            self.trip_id, "whole trip", include_in_memoir=True)
        trip_repository.location_note_create(
            self.trip_id, "germany leg", trip_region_id=self.region_id,
            include_in_memoir=True)
        trip_repository.location_note_create(
            self.trip_id, "munich stop", trip_region_id=self.region_id,
            trip_stop_id=self.stop_id, include_in_memoir=True)
        preview = trip_repository.trip_memoir_preview(self.trip_id)
        self.assertEqual([n["note_text"] for n in preview["story_notes"]], ["whole trip"])
        region = preview["part_one_journey_in_order"][0]
        self.assertEqual([n["note_text"] for n in region["story_notes"]], ["germany leg"])
        self.assertEqual([n["note_text"] for n in region["stops"][0]["story_notes"]],
                         ["munich stop"])


    def test_create_rejects_mismatched_region_stop(self):
        # stop is in self.region_id; pass a DIFFERENT region for it.
        region2 = trip_repository.region_create(self.trip_id, "Austria")
        with self.assertRaises(HTTPException) as ctx:
            trips.create_location_note(self.trip_id, _note_create_req(
                note_text="x", trip_region_id=region2, trip_stop_id=self.stop_id))
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
