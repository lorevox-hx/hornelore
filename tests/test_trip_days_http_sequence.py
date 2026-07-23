"""Real FastAPI TestClient HTTP sequence for the trip lane.

Companion to ``test_trip_lock_leak_and_orphan_person.py``. Per
ChatGPT's post-1e388b5 review §5: that test file calls the router
functions directly, which cannot prove correct HTTP serialization,
Pydantic validation, DELETE routing, or middleware behavior. This
file mounts ``trips.router`` on a fresh minimal FastAPI app and
exercises the exact HTTP shape the browser sends.

Skips cleanly when FastAPI / TestClient are not installed (matches
the posture of test_extract_api_subject_filters).

Fresh sqlite fixture per test.
"""
from __future__ import annotations

import importlib
import os
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

_HAVE_FASTAPI = False
_STUBBED = False

# 2026-07-23 (Bucket A+B follow-up) — DO NOT drop fastapi stubs from
# sys.modules to hot-swap real fastapi mid-run. The earlier version
# did that, and after this test ran, downstream sibling test files
# (test_trip_days, test_trip_editable_fixes, etc.) that do a bare
# `from fastapi import HTTPException` picked up whichever class was
# left in sys.modules — DIFFERENT from what api.routers.trips had
# already bound. Every subsequent assertRaises(HTTPException) failed
# with a mismatched-class error.
#
# Correct posture: only run when real fastapi loads NATURALLY on
# import (i.e., a sibling file hasn't already stubbed). On Chris's
# laptop with real fastapi installed, no stub check ever fires and
# this test runs. In the sandbox with no fastapi installed AND a
# sibling stub registered, we skip cleanly. That trades running the
# HTTP test in the sandbox for the much bigger win of never
# poisoning downstream tests.
_fastapi_mod = sys.modules.get("fastapi")
if _fastapi_mod is not None and getattr(_fastapi_mod, "__file__", None) is None:
    _STUBBED = True
else:
    try:
        from fastapi import FastAPI  # noqa: E402
        from fastapi.testclient import TestClient  # noqa: E402
        _HAVE_FASTAPI = True
    except Exception:  # pragma: no cover — CI without fastapi installed
        _HAVE_FASTAPI = False


@unittest.skipUnless(
    _HAVE_FASTAPI,
    "fastapi + fastapi.testclient are required for the HTTP sequence test "
    "(skipped when sibling test file has already stubbed fastapi in "
    "sys.modules, or when fastapi isn't installed)",
)
class NorthDakotaHttpSequenceTest(unittest.TestCase):
    """Full ND flow driven through real HTTP against a minimal app
    that only mounts trips.router. Proves:
      * POST /api/trips serializes and validates through Pydantic
      * GET /api/trips/{id}/days returns partitioned response
      * PATCH /api/trips/{id} accepts JSON body and returns days_warning
      * DELETE /api/trips/{id} routes and returns 200
      * A bogus person_id is rejected as 422 through the real HTTP path
      * No HTTP 500 anywhere in the sequence
    """

    def setUp(self):
        # Fresh sqlite fixture per test.
        self._tmpdb = tempfile.NamedTemporaryFile(
            suffix=".sqlite3", delete=False)
        self._tmpdb.close()
        self.db_path = Path(self._tmpdb.name)

        # Rebind the DB path BEFORE any api.* module opens a connection.
        from api import db as _db
        # Reload db so its module-level state respects our DB_PATH.
        self._orig_db_path = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()

        # Enable the trips gate for this test.
        self._orig_flag = os.environ.get("HORNELORE_TRIPS")
        os.environ["HORNELORE_TRIPS"] = "1"

        # Insert a real narrator.
        self.person_id = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO people (id, display_name, date_of_birth, "
            "created_at, updated_at) VALUES (?, 'Chris', '1962-12-24', "
            "'2026-07-23', '2026-07-23')", (self.person_id,))
        con.commit()
        con.close()

        # Build the minimal app now that DB + gate are ready.
        # NOTE: trips.router self-declares prefix="/api/trips", so we
        # mount it WITHOUT a prefix here. Adding one would double-nest
        # the routes to /api/trips/api/trips/... and every real path
        # would 404. (Learned the hard way — Chris caught it live.)
        from api.routers import trips as _trips
        importlib.reload(_trips)  # pick up any repo mutations from other tests
        self.app = FastAPI()
        self.app.include_router(_trips.router)
        self.client = TestClient(self.app)

    def tearDown(self):
        if self._orig_flag is None:
            os.environ.pop("HORNELORE_TRIPS", None)
        else:
            os.environ["HORNELORE_TRIPS"] = self._orig_flag
        from api import db as _db
        _db.DB_PATH = self._orig_db_path
        try:
            self.db_path.unlink()
        except OSError:
            pass

    # ── The ND full sequence, but through real HTTP ──────────────

    def test_full_http_sequence(self):
        # 1. POST /api/trips — create Aug 3–7 trip
        r = self.client.post("/api/trips", json={
            "person_id": self.person_id,
            "title": "HTTP: ND Mineral Records",
            "start_date": "2026-08-03",
            "end_date": "2026-08-07",
            "summary": "Bismarck and Stanley."})
        self.assertEqual(r.status_code, 200,
                         f"create returned {r.status_code}: {r.text[:400]}")
        create_body = r.json()
        trip_id = create_body["trip_id"]
        self.assertNotIn("days_warning", create_body)

        # 2. GET /api/trips/{id}/days — partitioned response
        r = self.client.get(f"/api/trips/{trip_id}/days")
        self.assertEqual(r.status_code, 200,
                         f"days returned {r.status_code}: {r.text[:400]}")
        body = r.json()
        # Contract check on the new partitioned shape
        for key in ("days", "preserved", "count", "preserved_count",
                    "total", "trip_window"):
            self.assertIn(key, body, f"missing key {key}")
        self.assertEqual(body["count"], 5)
        self.assertEqual(body["preserved_count"], 0)
        self.assertEqual(body["total"], 5)
        self.assertEqual(len(body["days"]), 5)
        self.assertEqual([d["day_index"] for d in body["days"]],
                         [1, 2, 3, 4, 5])

        # 3. PATCH /api/trips/{id} — reversed dates → days_warning
        r = self.client.patch(f"/api/trips/{trip_id}", json={
            "start_date": "2026-08-10", "end_date": "2026-08-05"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("days_warning", body,
                      "reversed dates should surface a days_warning")
        self.assertIn("before", body["days_warning"].lower())

        # 4. PATCH /api/trips/{id} — restore valid dates AND extend
        r = self.client.patch(f"/api/trips/{trip_id}", json={
            "start_date": "2026-08-01", "end_date": "2026-08-09"})
        self.assertEqual(r.status_code, 200,
                         f"restore returned {r.status_code}: {r.text[:400]}")
        self.assertNotIn("days_warning", r.json())

        # 5. GET /days again — should show 9 in-window days
        r = self.client.get(f"/api/trips/{trip_id}/days")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["count"], 9)
        self.assertEqual(body["preserved_count"], 0)
        self.assertEqual([d["day_index"] for d in body["days"]],
                         [1, 2, 3, 4, 5, 6, 7, 8, 9])

        # 6. PATCH shrink to Aug 3–7 → partitioned preserved
        r = self.client.patch(f"/api/trips/{trip_id}", json={
            "start_date": "2026-08-03", "end_date": "2026-08-07"})
        self.assertEqual(r.status_code, 200)
        r = self.client.get(f"/api/trips/{trip_id}/days")
        body = r.json()
        self.assertEqual(body["count"], 5)
        self.assertEqual(body["preserved_count"], 4)
        # In-window indexes are sequential; preserved keeps its own indexes.
        self.assertEqual([d["day_index"] for d in body["days"]],
                         [1, 2, 3, 4, 5])

        # 7. DELETE /api/trips/{id} — no 500
        r = self.client.delete(f"/api/trips/{trip_id}")
        self.assertIn(r.status_code, (200, 204),
                      f"delete returned {r.status_code}: {r.text[:400]}")
        # And a GET now returns 404
        r = self.client.get(f"/api/trips/{trip_id}/days")
        self.assertEqual(r.status_code, 404)

    # ── Orphan validation through real HTTP ─────────────────────

    def test_bogus_person_id_returns_http_422(self):
        r = self.client.post("/api/trips", json={
            "person_id": "PASTE_UUID_HERE",
            "title": "Should not save"})
        self.assertEqual(r.status_code, 422,
                         f"bogus person_id returned {r.status_code}: "
                         f"{r.text[:400]}")

    def test_missing_person_id_returns_http_422(self):
        r = self.client.post("/api/trips", json={"title": "Missing person"})
        # Pydantic-level validation error → 422
        self.assertEqual(r.status_code, 422)

    def test_days_endpoint_404_on_unknown_trip(self):
        fake_id = str(uuid.uuid4())
        r = self.client.get(f"/api/trips/{fake_id}/days")
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
