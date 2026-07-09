"""WO-TRIP-PHOTO-CONTEXT-ENRICHMENT-FOR-LORI-01 Phase 1 — reviewable
photo date/place metadata + Lori approval flags.

Locked rules under test: filename dates are LOW-CONFIDENCE guesses that
never auto-fill the canonical date; raw GPS never reaches Lori (or even
the operator photo-links projection — presence boolean only); approval
flags default 0; editing revokes approval; cross-trip/narrator metadata
never leaks; Ph1 adds NO dependencies (pure-stdlib parser).
"""
from __future__ import annotations

import ast
import sqlite3
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

import types  # noqa: E402

# Offline stubs (fastapi/pydantic may be absent). HTTPException is
# kwargs-capable — the stub is SHARED via sys.modules with other test
# files whose code raises HTTPException(status_code=..., detail=...).
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
    responses = types.ModuleType("fastapi.responses")
    responses.FileResponse = object
    responses.JSONResponse = object
    responses.StreamingResponse = object
    stub.responses = responses
    sys.modules["fastapi"] = stub
    sys.modules["fastapi.responses"] = responses

if "pydantic" not in sys.modules:
    pstub = types.ModuleType("pydantic")

    class _BaseModel:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)

    pstub.BaseModel = _BaseModel
    pstub.Field = lambda default=None, **k: default
    pstub.field_validator = lambda *a, **k: (lambda f: f)
    pstub.validator = lambda *a, **k: (lambda f: f)
    pstub.ConfigDict = dict
    sys.modules["pydantic"] = pstub

from api import db as _db  # noqa: E402
from api.services import trip_repository  # noqa: E402
from api.services import trip_interview_context as tic  # noqa: E402
from services.photo_intake.filename_date import (  # noqa: E402
    derive_date_fields, parse_filename_date)


class FilenameDateParserTest(unittest.TestCase):
    def test_pixel_and_common_shapes(self):
        for name, want in [
            ("PXL_20260514_123456789.jpg", "2026-05-14"),
            ("IMG_20260514_101112.jpg", "2026-05-14"),
            ("IMG-20260514-WA0001.jpg", "2026-05-14"),
            ("20260514_101112.jpg", "2026-05-14"),
            ("Screenshot_20260514-090000.png", "2026-05-14"),
            ("2026-05-14 dinner.jpg", "2026-05-14"),
        ]:
            self.assertEqual(parse_filename_date(name), want, name)

    def test_garbage_and_impossible_dates_rejected(self):
        for name in ("holiday.jpg", "IMG_20261399_1.jpg", "PXL_20260231_1.jpg",
                     "12345678.jpg", "", None):
            self.assertIsNone(parse_filename_date(name), repr(name))

    # 1. EXIF date stored (wins over filename guess).
    def test_exif_date_wins(self):
        d = derive_date_fields("2026-05-14T18:30:00", "PXL_20260101_1.jpg")
        self.assertEqual(d["date_value"], "2026-05-14T18:30:00")
        self.assertEqual(d["date_source"], "exif")
        self.assertEqual(d["taken_at_filename_guess"], "2026-01-01")

    # 2. Missing EXIF -> clean 'missing' state, nothing invented.
    def test_missing_everything_is_clean(self):
        d = derive_date_fields(None, "holiday.jpg")
        self.assertIsNone(d["date_value"])
        self.assertEqual(d["date_source"], "missing")
        self.assertIsNone(d["taken_at_filename_guess"])

    # 3. Filename date is LOW-CONFIDENCE only — never fills date_value.
    def test_filename_guess_never_canonical(self):
        d = derive_date_fields(None, "PXL_20260514_123.jpg")
        self.assertIsNone(d["date_value"])
        self.assertEqual(d["date_source"], "filename_guess")
        self.assertEqual(d["taken_at_filename_guess"], "2026-05-14")

    def test_suspect_scan_exif_demoted_to_guess_or_missing(self):
        d = derive_date_fields("2026-05-14T18:30:00", "scan001.jpg", suspect=True)
        self.assertIsNone(d["date_value"])
        self.assertEqual(d["date_source"], "missing")

    # 9. No dependency changes — the parser is pure stdlib.
    def test_parser_is_pure_stdlib(self):
        src = (_SERVER_CODE / "services" / "photo_intake" /
               "filename_date.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        allowed = {"datetime", "re", "typing", "__future__"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    self.assertIn(a.name.split(".")[0], allowed, a.name)
            elif isinstance(node, ast.ImportFrom):
                self.assertIn((node.module or "").split(".")[0], allowed)


class _MetaCase(unittest.TestCase):
    def setUp(self):
        self._tmpdb = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self._tmpdb.close()
        self.db_path = Path(self._tmpdb.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()
        self.person_id = str(uuid.uuid4())
        self.stranger = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        for pid in (self.person_id, self.stranger):
            con.execute(
                "INSERT INTO people (id, display_name, created_at, updated_at) "
                "VALUES (?, 'Meta Test', '2026-07-09', '2026-07-09');", (pid,))
        # Photo with GPS + EXIF date, narrator-ready, owned by person_id.
        con.execute(
            "INSERT INTO photos (id, narrator_id, image_path, file_hash, "
            "narrator_ready, date_value, date_source, latitude, longitude, "
            "location_label) VALUES ('p1', ?, '/tmp/p1.jpg', 'h1', 1, "
            "'2026-05-14', 'exif', 48.1374, 11.5755, 'Munich area');",
            (self.person_id,))
        # Stranger's photo — must never surface through person_id's trip.
        con.execute(
            "INSERT INTO photos (id, narrator_id, image_path, file_hash, "
            "narrator_ready, date_value, date_source) VALUES "
            "('p_foreign', ?, '/tmp/p2.jpg', 'h2', 1, '1999-01-01', 'exif');",
            (self.stranger,))
        con.commit()
        con.close()
        self.trip_id = trip_repository.trip_create(
            person_id=self.person_id, title="Meta Trip",
            start_date="2026-05-12", end_date="2026-06-13", summary=None)
        self.region_id = trip_repository.region_create(self.trip_id, "Bavaria")
        self.link_id = trip_repository.photo_link_upsert(
            self.trip_id, "p1", trip_region_id=self.region_id,
            assignment_method="operator")

    def tearDown(self):
        _db.DB_PATH = self._orig_db
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def _links(self):
        return trip_repository.photo_links_list(self.trip_id)

    # 5 + 6. Approval flags default OFF.
    def test_approvals_default_off(self):
        l = self._links()[0]
        self.assertFalse(l["photo_date_approved_for_lori"])
        self.assertFalse(l["photo_location_approved_for_lori"])

    # 4a. GPS presence is a boolean; raw coordinates are NOT projected
    # on the operator photo-links read.
    def test_gps_present_flag_without_raw_coords(self):
        l = self._links()[0]
        self.assertTrue(l["photo_gps_present"])
        for k in ("photo_latitude", "photo_longitude"):
            self.assertNotIn(k, l)

    # 4b. Raw GPS never appears in Lori's trip context.
    def test_raw_gps_never_in_lori_context(self):
        ctx = tic.build_trip_interview_context(self.person_id, self.trip_id)
        text = (ctx or {}).get("text", "")
        self.assertNotIn("48.13", text)
        self.assertNotIn("11.57", text)

    # Display fields present for the Travel Doc card.
    def test_review_fields_projected(self):
        l = self._links()[0]
        self.assertEqual(l["photo_date_value"], "2026-05-14")
        self.assertEqual(l["photo_date_source"], "exif")
        self.assertEqual(l["photo_location_label"], "Munich area")

    # 7. Editing date/place revokes approval — enforced at the
    # repository layer so every caller inherits the rule.
    def test_edit_revokes_approval(self):
        from services.photos import repository as photo_repo
        # approve both first
        photo_repo.patch_photo("p1", {
            "date_approved_for_lori": True,
            "location_approved_for_lori": True}, actor_id="t")
        l = self._links()[0]
        self.assertTrue(l["photo_date_approved_for_lori"])
        self.assertTrue(l["photo_location_approved_for_lori"])
        # edit date -> date approval drops, source stamps operator_confirmed
        photo_repo.patch_photo("p1", {"date_value": "2026-05-15"}, actor_id="t")
        l = self._links()[0]
        self.assertFalse(l["photo_date_approved_for_lori"])
        self.assertEqual(l["photo_date_source"], "operator_confirmed")
        self.assertTrue(l["photo_location_approved_for_lori"])  # untouched
        # edit place -> place approval drops
        photo_repo.patch_photo("p1", {"location_label": "Bavaria"}, actor_id="t")
        l = self._links()[0]
        self.assertFalse(l["photo_location_approved_for_lori"])

    # 8. Another narrator/trip cannot see this photo's metadata.
    def test_cross_trip_metadata_isolation(self):
        other_trip = trip_repository.trip_create(
            person_id=self.stranger, title="Foreign", start_date=None,
            end_date=None, summary=None)
        self.assertEqual(trip_repository.photo_links_list(other_trip), [])
        ids = [l["photo_id"] for l in self._links()]
        self.assertNotIn("p_foreign", ids)


if __name__ == "__main__":
    unittest.main()
