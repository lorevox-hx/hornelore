"""WO-TRIP-PHOTO-STOP-UPLOAD-AND-ELICIT-01 Phase C2 — upload at a stop.

Covers the shared ingest pipeline (dedupe → store → EXIF → trust →
photos row) and the stop-scoped endpoint semantics: operator-truth
link, EXIF cross-check mismatch flag, duplicate re-link, re-cluster
never moves an operator link. Endpoint tested via the fastapi stub
(async def driven with asyncio.run + a fake UploadFile).
"""
from __future__ import annotations

import asyncio
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

# Minimal fastapi stub so routers import offline (same approach as
# tests/test_trip_timeline_bridge.py, extended with File/Form/UploadFile).
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

from api import db as _db  # noqa: E402
from api.services import trip_repository  # noqa: E402
from services.photo_intake.ingest import ingest_photo_file  # noqa: E402

# 1x1 JPEG, no EXIF — the "stripped share" class.
_TINY_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707"
    "07090908080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c23"
    "1c1c2837292c30313434341f27393d38323c2e333432ffc0000b0800010001010111"
    "00ffc40014000100000000000000000000000000000009ffc40014100100000000000"
    "00000000000000000000000ffda0008010100003f0054dfffd9"
)


class _FakeUpload:
    """Duck-typed UploadFile: async read + filename."""

    def __init__(self, data: bytes, filename: str):
        self._data = data
        self._pos = 0
        self.filename = filename

    async def read(self, n: int) -> bytes:
        chunk = self._data[self._pos:self._pos + n]
        self._pos += n
        return chunk


class _StopUploadCase(unittest.TestCase):
    def setUp(self):
        self._tmpdb = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self._tmpdb.close()
        self.db_path = Path(self._tmpdb.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()
        self._data_dir = tempfile.mkdtemp(prefix="trip_upload_data_")
        self._orig_data_dir = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = self._data_dir
        self._orig_trips_flag = os.environ.get("HORNELORE_TRIPS")
        os.environ["HORNELORE_TRIPS"] = "1"

        self.person_id = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO people (id, display_name, date_of_birth, created_at, "
            "updated_at) VALUES (?, 'Upload Test', '1962-12-24', "
            "'2026-07-05', '2026-07-05');",
            (self.person_id,),
        )
        con.commit()
        con.close()

        self.trip_id = trip_repository.trip_create(
            person_id=self.person_id, title="Spring 2026",
            start_date="2026-05-22", end_date="2026-06-13",
        )
        self.region_id = trip_repository.region_create(self.trip_id, "Czechia")
        self.stop_id = trip_repository.stop_create(
            self.trip_id, self.region_id, "Prague",
        )
        trip_repository.stop_update(
            self.stop_id, date_start="2026-05-27", date_end="2026-05-30",
            latitude=50.0875, longitude=14.4213,
        )

    def tearDown(self):
        _db.DB_PATH = self._orig_db
        if self._orig_data_dir is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self._orig_data_dir
        if self._orig_trips_flag is None:
            os.environ.pop("HORNELORE_TRIPS", None)
        else:
            os.environ["HORNELORE_TRIPS"] = self._orig_trips_flag
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def _tmp_image(self, data: bytes = _TINY_JPEG) -> str:
        fd, path = tempfile.mkstemp(suffix=".bin")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return path

    @staticmethod
    def _cleanup(*paths):
        # store_photo_file MOVES the temp file into the archive on
        # success — unlink only what's still there.
        for p in paths:
            try:
                os.unlink(p)
            except FileNotFoundError:
                pass

    def _upload(self, filename="prague.jpg", data=_TINY_JPEG, **form):
        from api.routers.trips import upload_photos_at_stop
        return asyncio.run(upload_photos_at_stop(
            self.stop_id,
            files=[_FakeUpload(data, filename)],
            uploaded_by_user_id=form.get("uploaded_by_user_id", "operator"),
            narrator_ready=form.get("narrator_ready", "true"),
            caption=form.get("caption", ""),
            sidecar_json=form.get("sidecar_json", ""),
        ))


class IngestPipelineTest(_StopUploadCase):
    def test_ingest_creates_row_with_trust(self):
        p = self._tmp_image()
        try:
            out = ingest_photo_file(
                narrator_id=self.person_id, tmp_path=p,
                original_filename="scan001.jpg",
                uploaded_by_user_id="operator", narrator_ready=True,
            )
        finally:
            self._cleanup(p)
        self.assertFalse(out["duplicate"])
        self.assertEqual(out["metadata_trust"], "none")  # no EXIF survives
        row = out["photo"]
        self.assertEqual(row["narrator_id"], self.person_id)
        # Trust persisted to the column (migration 0016 applied by init_db).
        con = sqlite3.connect(str(self.db_path))
        trust = con.execute(
            "SELECT metadata_trust FROM photos WHERE id=?", (row["id"],),
        ).fetchone()[0]
        con.close()
        self.assertEqual(trust, "none")

    def test_ingest_dedupes_by_hash(self):
        p1, p2 = self._tmp_image(), self._tmp_image()
        try:
            first = ingest_photo_file(
                narrator_id=self.person_id, tmp_path=p1,
                original_filename="a.jpg", uploaded_by_user_id="operator",
            )
            second = ingest_photo_file(
                narrator_id=self.person_id, tmp_path=p2,
                original_filename="b.jpg", uploaded_by_user_id="operator",
            )
        finally:
            self._cleanup(p1, p2)
        self.assertTrue(second["duplicate"])
        self.assertEqual(second["photo"]["id"], first["photo"]["id"])

    def test_sidecar_fills_missing_metadata(self):
        import json as _json
        p = self._tmp_image()
        sidecar = _json.dumps({
            "photoTakenTime": {"timestamp": "1748442600"},
            "geoData": {"latitude": 50.0875, "longitude": 14.4213},
        })
        try:
            out = ingest_photo_file(
                narrator_id=self.person_id, tmp_path=p,
                original_filename="takeout.jpg",
                uploaded_by_user_id="operator", sidecar_json=sidecar,
            )
        finally:
            self._cleanup(p)
        self.assertEqual(out["metadata_trust"], "full")
        self.assertAlmostEqual(out["exif_latitude"], 50.0875)
        self.assertIn("2025-05-28", out["photo"]["date_value"] or "")


class StopUploadEndpointTest(_StopUploadCase):
    def test_upload_links_as_operator_truth(self):
        resp = self._upload()
        self.assertEqual(resp["uploaded"], 1)
        self.assertEqual(resp["errors"], 0)
        r = resp["results"][0]
        self.assertIsNotNone(r["photo_id"])
        links = trip_repository.photo_links_list(self.trip_id)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["trip_stop_id"], self.stop_id)
        self.assertEqual(links[0]["assignment_method"], "operator")
        self.assertEqual(links[0]["cluster_confidence"], 1.0)
        # narrator_ready defaulted true (deliberate placement).
        con = sqlite3.connect(str(self.db_path))
        ready = con.execute(
            "SELECT narrator_ready FROM photos WHERE id=?",
            (r["photo_id"],),
        ).fetchone()[0]
        con.close()
        self.assertEqual(ready, 1)

    def test_no_exif_photo_flags_no_mismatch(self):
        # Stripped photo: no signals to contradict the operator.
        resp = self._upload()
        self.assertIsNone(resp["results"][0]["mismatch"])
        self.assertEqual(resp["results"][0]["metadata_trust"], "none")

    def test_duplicate_upload_still_links_existing_photo(self):
        first = self._upload()
        second = self._upload(filename="again.jpg")
        self.assertEqual(second["duplicates"], 1)
        self.assertEqual(
            second["results"][0]["photo_id"], first["results"][0]["photo_id"])
        links = trip_repository.photo_links_list(self.trip_id)
        self.assertEqual(len(links), 1)  # upsert, not a second link

    def test_recluster_never_moves_operator_link(self):
        resp = self._upload()
        photo_id = resp["results"][0]["photo_id"]
        # Simulate a re-cluster trying to move the photo elsewhere.
        link_id = trip_repository.photo_link_upsert(
            trip_id=self.trip_id, photo_id=photo_id,
            trip_stop_id=None, assignment_method="exif_time",
            cluster_confidence=0.3,
        )
        links = trip_repository.photo_links_list(self.trip_id)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["id"], link_id)
        self.assertEqual(links[0]["trip_stop_id"], self.stop_id)
        self.assertEqual(links[0]["assignment_method"], "operator")

    def test_unknown_stop_404s(self):
        from api.routers.trips import upload_photos_at_stop
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):
            asyncio.run(upload_photos_at_stop(
                "no-such-stop", files=[_FakeUpload(_TINY_JPEG, "x.jpg")],
                uploaded_by_user_id="operator", narrator_ready="true",
                caption="", sidecar_json="",
            ))

    def test_mismatched_sidecar_gps_lands_in_review(self):
        import json as _json
        # Sidecar GPS = Vienna (~250 km from the Prague stop) → mismatch
        # flag + confidence 0.45 (review queue) but placement kept.
        sidecar = _json.dumps({
            "photoTakenTime": {"timestamp": "1748442600"},
            "geoData": {"latitude": 48.2082, "longitude": 16.3738},
        })
        resp = self._upload(sidecar_json=sidecar)
        r = resp["results"][0]
        self.assertIsNotNone(r["mismatch"])
        self.assertIn("gps_km_from_stop", r["mismatch"])
        links = trip_repository.photo_links_list(self.trip_id)
        self.assertEqual(links[0]["trip_stop_id"], self.stop_id)  # kept
        self.assertEqual(links[0]["cluster_confidence"], 0.45)  # review
        self.assertEqual(links[0]["assignment_method"], "operator")


if __name__ == "__main__":
    unittest.main()
