"""WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01 Phase 2 — destructive-trip
controls on DELETE /api/trips/{trip_id}.

Pins the full force gate on a real temp DB:

  * empty disposable trip deletes normally (pre-existing contract);
  * evidence-bearing trip without force → 409 with correct per-table
    counts, NOTHING modified;
  * force with a wrong/missing confirm_trip_id → 422, nothing modified;
  * force + exact id deletes the intended trip only — cascade removes
    ALL dependent rows (verified per-table), another narrator's trip is
    untouched, and PRAGMA foreign_key_check returns no rows;
  * partial failure (precommit hook raises) rolls back the WHOLE
    transaction — trip intact, audit row absent;
  * the audit row records action/person/title/counts/reason/timestamp.

Offline fastapi/pydantic stub pattern (same as
tests/test_travel_doc_evidence_tools).
"""
from __future__ import annotations

import json
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
            super().__init__(str(detail))

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

from fastapi import HTTPException  # noqa: E402  (stub)
from api import db as _db  # noqa: E402
from api.services import trip_repository  # noqa: E402
from api.routers import trips  # noqa: E402

# Every dependent table the cascade must clear, in the count-key order
# the endpoint reports.
_CHILD_TABLES = {
    "regions": "trip_regions",
    "stops": "trip_stops",
    "days": "trip_days",
    "photo_links": "trip_photo_links",
    "notes": "trip_location_notes",
    "sources": "trip_sources",
    "story_links": "trip_story_links",
    "public_context": "trip_public_context",
    "photo_context": "trip_photo_context",
    "bio_suggestions": "trip_bio_suggestions",
}


class _Body:
    def __init__(self, force=False, confirm_trip_id=None, reason=None):
        self.force = force
        self.confirm_trip_id = confirm_trip_id
        self.reason = reason


class _ForceDeleteCase(unittest.TestCase):
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
        self.person_a = str(uuid.uuid4())
        self.person_b = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        for pid, name in ((self.person_a, "A"), (self.person_b, "B")):
            con.execute(
                "INSERT INTO people (id, display_name, date_of_birth, "
                "created_at, updated_at) VALUES (?, ?, '1962-12-24', "
                "'2026-07-24', '2026-07-24');", (pid, name))
        con.execute(
            "INSERT INTO photos (id, narrator_id, image_path, file_hash, "
            "narrator_ready) VALUES ('phA', ?, '/tmp/phA.jpg', 'hA', 1)",
            (self.person_a,))
        con.execute(
            "INSERT INTO photos (id, narrator_id, image_path, file_hash, "
            "narrator_ready) VALUES ('phB', ?, '/tmp/phB.jpg', 'hB', 1)",
            (self.person_b,))
        con.commit()
        con.close()
        # Trip A — one row in EVERY dependent table.
        self.trip_a = self._build_full_trip(self.person_a, "Bavaria 2026",
                                            "phA")
        # Trip B — a second narrator's evidence-bearing trip that must
        # survive Trip A's force delete untouched.
        self.trip_b = self._build_full_trip(self.person_b, "Prague 1998",
                                            "phB")

    def tearDown(self):
        trip_repository._TRIP_FORCE_DELETE_PRECOMMIT_HOOK = None
        if self._orig_flag is None:
            os.environ.pop("HORNELORE_TRIPS", None)
        else:
            os.environ["HORNELORE_TRIPS"] = self._orig_flag
        _db.DB_PATH = self._orig_db
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def _build_full_trip(self, person_id: str, title: str,
                         photo_id: str) -> str:
        trip_id = trip_repository.trip_create(
            person_id, title, start_date="2026-05-22",
            end_date="2026-05-23")
        region_id = trip_repository.region_create(trip_id, "Region")
        stop_id = trip_repository.stop_create(trip_id, region_id, "Stop")
        trip_repository.trip_days_generate(trip_id)   # 2 day cards
        link_id = trip_repository.photo_link_upsert(
            trip_id, photo_id, trip_region_id=region_id,
            trip_stop_id=stop_id, assignment_method="operator")
        trip_repository.location_note_create(
            trip_id=trip_id, note_text="note for " + title,
            trip_stop_id=stop_id, include_in_memoir=True)
        trip_repository.source_create(
            trip_id=trip_id, source_type="hotel", title="bill",
            summary="source for " + title)
        trip_repository.public_context_create(
            trip_id=trip_id, result_summary="public ctx",
            source_type="place_context")
        trip_repository.photo_context_create(
            trip_id=trip_id, photo_link_id=link_id,
            context_type="ocr_text", result_summary="ocr ctx")
        trip_repository.bio_suggestion_replace_for_trip(
            trip_id, person_id, "travel_history", title)
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO trip_story_links (id, trip_id, trip_stop_id, "
            "story_candidate_id, status, created_at) "
            "VALUES (?, ?, ?, ?, 'suggested', '2026-07-24')",
            (str(uuid.uuid4()), trip_id, stop_id, str(uuid.uuid4())))
        con.commit()
        con.close()
        return trip_id

    # ── helpers ────────────────────────────────────────────────────────
    def _counts(self, trip_id: str):
        con = sqlite3.connect(str(self.db_path))
        try:
            out = {}
            for key, table in _CHILD_TABLES.items():
                out[key] = con.execute(
                    "SELECT COUNT(*) FROM %s WHERE trip_id = ?" % table,
                    (trip_id,)).fetchone()[0]
            return out
        finally:
            con.close()

    _EXPECTED_A = {"regions": 1, "stops": 1, "days": 2, "photo_links": 1,
                   "notes": 1, "sources": 1, "story_links": 1,
                   "public_context": 1, "photo_context": 1,
                   "bio_suggestions": 1}

    def _audit_rows(self):
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in con.execute(
                "SELECT * FROM narrator_delete_audit "
                "WHERE action = 'trip_force_delete' ORDER BY ts"
            ).fetchall()]
        finally:
            con.close()

    # ── tests ──────────────────────────────────────────────────────────
    def test_empty_trip_deletes_normally(self):
        tid = trip_repository.trip_create(self.person_a, "Disposable")
        res = trips.delete_trip(tid)     # no body — legacy call shape
        self.assertTrue(res["ok"])
        self.assertTrue(res["deleted"])
        self.assertEqual(sum(res["counts"].values()), 0)
        self.assertIsNone(trip_repository.trip_get(tid))
        self.assertEqual(self._audit_rows(), [])   # no force, no audit

    def test_evidence_trip_without_force_409_nothing_modified(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.delete_trip(self.trip_a)
        self.assertEqual(ctx.exception.status_code, 409)
        detail = ctx.exception.detail
        self.assertEqual(detail["detail"], "Trip contains evidence")
        self.assertEqual(detail["trip_id"], self.trip_a)
        self.assertTrue(detail["requires_force"])
        self.assertEqual(detail["counts"], self._EXPECTED_A)
        # Nothing was modified.
        self.assertIsNotNone(trip_repository.trip_get(self.trip_a))
        self.assertEqual(self._counts(self.trip_a), self._EXPECTED_A)
        self.assertEqual(self._audit_rows(), [])

    def test_force_wrong_confirm_id_422_nothing_modified(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.delete_trip(self.trip_a, _Body(
                force=True, confirm_trip_id=self.trip_b))
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIsNotNone(trip_repository.trip_get(self.trip_a))
        self.assertEqual(self._counts(self.trip_a), self._EXPECTED_A)
        self.assertEqual(self._audit_rows(), [])

    def test_force_missing_confirm_id_422_nothing_modified(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.delete_trip(self.trip_a, _Body(force=True))
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIsNotNone(trip_repository.trip_get(self.trip_a))
        self.assertEqual(self._counts(self.trip_a), self._EXPECTED_A)

    def test_force_exact_id_cascades_and_spares_other_narrator(self):
        res = trips.delete_trip(self.trip_a, _Body(
            force=True, confirm_trip_id=self.trip_a,
            reason="stale duplicate import"))
        self.assertTrue(res["ok"])
        self.assertTrue(res["deleted"])
        self.assertEqual(res["counts"], self._EXPECTED_A)
        # Trip A and EVERY dependent row are gone (per-table zeros).
        self.assertIsNone(trip_repository.trip_get(self.trip_a))
        zeros = self._counts(self.trip_a)
        for key, n in zeros.items():
            self.assertEqual(n, 0, "table %s not cascaded" % key)
        # The other narrator's trip is byte-for-byte intact.
        self.assertIsNotNone(trip_repository.trip_get(self.trip_b))
        self.assertEqual(self._counts(self.trip_b), self._EXPECTED_A)
        # Referential integrity holds after the cascade.
        con = sqlite3.connect(str(self.db_path))
        try:
            violations = con.execute("PRAGMA foreign_key_check").fetchall()
        finally:
            con.close()
        self.assertEqual(violations, [])

    def test_audit_row_records_everything(self):
        trips.delete_trip(self.trip_a, _Body(
            force=True, confirm_trip_id=self.trip_a,
            reason="stale duplicate import"))
        rows = self._audit_rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["action"], "trip_force_delete")
        self.assertEqual(row["person_id"], self.person_a)
        self.assertEqual(row["display_name"], "Bavaria 2026")
        self.assertEqual(row["requested_by"], "operator")
        self.assertEqual(row["result"], "success")
        self.assertTrue(row["ts"])
        counts = json.loads(row["dependency_counts_json"])
        self.assertEqual(counts["reason"], "stale duplicate import")
        self.assertEqual(counts["requested_by"], "operator")
        for key, n in self._EXPECTED_A.items():
            self.assertEqual(counts[key], n)

    def test_partial_failure_rolls_back_trip_and_audit(self):
        # Monkeypatch the precommit test seam to blow up AFTER the audit
        # append + cascade delete but BEFORE commit — the whole
        # transaction (audit row included) must roll back.
        def _boom(con, trip_id):
            raise RuntimeError("simulated late failure")
        trip_repository._TRIP_FORCE_DELETE_PRECOMMIT_HOOK = _boom
        try:
            with self.assertRaises(RuntimeError):
                trips.delete_trip(self.trip_a, _Body(
                    force=True, confirm_trip_id=self.trip_a,
                    reason="doomed"))
        finally:
            trip_repository._TRIP_FORCE_DELETE_PRECOMMIT_HOOK = None
        # Trip + every child row intact; audit row absent.
        self.assertIsNotNone(trip_repository.trip_get(self.trip_a))
        self.assertEqual(self._counts(self.trip_a), self._EXPECTED_A)
        self.assertEqual(self._audit_rows(), [])
        # And the gate still works after the failed attempt.
        res = trips.delete_trip(self.trip_a, _Body(
            force=True, confirm_trip_id=self.trip_a, reason="retry"))
        self.assertTrue(res["deleted"])

    def test_unknown_trip_404(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.delete_trip("nope", _Body(force=True,
                                            confirm_trip_id="nope"))
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
