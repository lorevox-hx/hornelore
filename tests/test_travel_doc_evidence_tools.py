"""WO-TRAVEL-DOC-EVIDENCE-TOOLS-01 Phase 1+2 — OCR/vision draft context,
public lookup, approval ladder, modal + narrator provenance wording.

Providers are monkeypatched (no real OCR engine / no network). Offline
fastapi/pydantic stub pattern (same as tests/test_stop_type_validation).
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

from fastapi import HTTPException  # noqa: E402  (stub)
from api import db as _db  # noqa: E402
from api.services import trip_repository  # noqa: E402
from api.services import travel_doc_photo_ocr as ocr  # noqa: E402
from api.services import travel_doc_public_lookup as lookup  # noqa: E402
from api.services import travel_doc_lori_modal as modal  # noqa: E402
from api.services import trip_interview_context as tic  # noqa: E402
from api.routers import trips  # noqa: E402


class _Req:
    def __init__(self, **kw):
        base = dict(query=None, url=None, source_type="place_context",
                    trip_region_id=None, trip_stop_id=None, trip_day_id=None,
                    photo_link_id=None, reason=None,
                    result_summary=None, raw_text=None,
                    approved_for_lori=None, include_in_memoir=None,
                    rejected=None)
        base.update(kw)
        self.__dict__.update(base)


# ── provider unit tests (no DB) ────────────────────────────────────────
class ProviderDefaultsOffTest(unittest.TestCase):
    def test_ocr_off_by_default(self):
        os.environ.pop("HORNELORE_PHOTO_OCR", None)
        self.assertFalse(ocr.ocr_enabled())
        r = ocr.run_ocr("/nonexistent.jpg")
        self.assertFalse(r["ok"])

    def test_lookup_off_by_default(self):
        os.environ.pop("HORNELORE_PUBLIC_LOOKUP", None)
        self.assertFalse(lookup.lookup_enabled())
        r = lookup.run_lookup(query="anything")
        self.assertFalse(r["ok"])

    def test_lookup_url_only_requires_url(self):
        os.environ["HORNELORE_PUBLIC_LOOKUP"] = "1"
        os.environ["HORNELORE_PUBLIC_LOOKUP_PROVIDER"] = "url_only"
        try:
            r = lookup.run_lookup(query="just a query", url=None)
            self.assertFalse(r["ok"])
        finally:
            os.environ.pop("HORNELORE_PUBLIC_LOOKUP", None)
            os.environ.pop("HORNELORE_PUBLIC_LOOKUP_PROVIDER", None)


class ProviderPlumbingTest(unittest.TestCase):
    def test_ocr_langs_default_and_override(self):
        os.environ.pop("HORNELORE_OCR_LANGS", None)
        self.assertEqual(ocr.ocr_langs(), "eng")
        os.environ["HORNELORE_OCR_LANGS"] = "eng+deu+ita"
        try:
            self.assertEqual(ocr.ocr_langs(), "eng+deu+ita")
        finally:
            os.environ.pop("HORNELORE_OCR_LANGS", None)

    def test_parse_html_fallback_extracts_title_and_text(self):
        # Works even without bs4/readability installed (regex fallback).
        html = ("<html><head><title>German Hunting and Fishing "
                "Museum</title></head><body><script>x=1</script>"
                "<p>A large catfish sculpture stands outside.</p>"
                "</body></html>")
        title, text = lookup._parse_html(html)
        self.assertIn("German Hunting and Fishing Museum", title)
        self.assertIn("catfish sculpture", text)
        self.assertNotIn("x=1", text)


class _DbCase(unittest.TestCase):
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
            "created_at, updated_at) VALUES (?, 'P', '1962-12-24', "
            "'2026-07-10', '2026-07-10');", (self.person_id,))
        con.execute(
            "INSERT INTO photos (id, narrator_id, image_path, file_hash, "
            "narrator_ready) VALUES ('ph1', ?, '/tmp/ph1.jpg', 'h1', 1)",
            (self.person_id,))
        con.commit()
        con.close()
        self.trip_id = trip_repository.trip_create(
            self.person_id, "Spring 2026", start_date="2026-05-22",
            end_date="2026-06-13")
        self.region_id = trip_repository.region_create(self.trip_id, "Germany")
        self.stop_id = trip_repository.stop_create(
            self.trip_id, self.region_id, "Munich")
        self.link_id = trip_repository.photo_link_upsert(
            self.trip_id, "ph1", trip_region_id=self.region_id,
            trip_stop_id=self.stop_id, assignment_method="operator")

    def tearDown(self):
        if self._orig_flag is None:
            os.environ.pop("HORNELORE_TRIPS", None)
        else:
            os.environ["HORNELORE_TRIPS"] = self._orig_flag
        _db.DB_PATH = self._orig_db
        for k in ("HORNELORE_PHOTO_OCR", "HORNELORE_OCR_PROVIDER",
                  "HORNELORE_PUBLIC_LOOKUP", "HORNELORE_PUBLIC_LOOKUP_PROVIDER"):
            os.environ.pop(k, None)
        try:
            self.db_path.unlink()
        except OSError:
            pass


class OcrEndpointTest(_DbCase):
    def test_ocr_disabled_returns_clear_status_no_row(self):
        os.environ.pop("HORNELORE_PHOTO_OCR", None)
        out = trips.run_photo_ocr(self.link_id)
        self.assertEqual(out["status"], "disabled")
        self.assertEqual(
            trip_repository.photo_context_list_for_link(self.link_id), [])

    def test_ocr_stores_draft_row_defaults_off(self):
        os.environ["HORNELORE_PHOTO_OCR"] = "1"
        orig = ocr.run_ocr
        ocr.run_ocr = lambda p: {
            "ok": True, "engine": "tesseract",
            "raw_text": "Deutsches Jagd- und Fischereimuseum",
            "summary": "Deutsches Jagd- und Fischereimuseum", "error": None}
        try:
            out = trips.run_photo_ocr(self.link_id)
        finally:
            ocr.run_ocr = orig
        self.assertEqual(out["status"], "stored")
        row = out["context"]
        self.assertEqual(row["context_type"], "ocr_text")
        self.assertEqual(row["approved_for_lori"], 0)
        self.assertEqual(row["include_in_memoir"], 0)
        self.assertEqual(row["rejected"], 0)
        self.assertEqual(row["confidence"], "draft")

    def test_ocr_provider_failure_writes_no_row(self):
        os.environ["HORNELORE_PHOTO_OCR"] = "1"
        orig = ocr.run_ocr
        ocr.run_ocr = lambda p: {"ok": False, "engine": "tesseract",
                                 "error": "no_text_found"}
        try:
            out = trips.run_photo_ocr(self.link_id)
        finally:
            ocr.run_ocr = orig
        self.assertEqual(out["status"], "unavailable")
        self.assertEqual(
            trip_repository.photo_context_list_for_link(self.link_id), [])


class ApprovalLadderTest(_DbCase):
    def _ocr_row(self, summary="museum sign", approved=False):
        cid = trip_repository.photo_context_create(
            trip_id=self.trip_id, photo_link_id=self.link_id,
            context_type="ocr_text", result_summary=summary, photo_id="ph1")
        if approved:
            trip_repository.photo_context_update(cid, approved_for_lori=True)
        return cid

    def test_approve_sets_flag(self):
        cid = self._ocr_row()
        trips.patch_photo_context(cid, _Req(approved_for_lori=True))
        self.assertEqual(
            trip_repository.photo_context_get(cid)["approved_for_lori"], 1)

    def test_edit_revokes_approval(self):
        cid = self._ocr_row(approved=True)
        trips.patch_photo_context(cid, _Req(result_summary="edited text"))
        self.assertEqual(
            trip_repository.photo_context_get(cid)["approved_for_lori"], 0)

    def test_include_in_memoir_requires_approved(self):
        cid = self._ocr_row(approved=False)
        with self.assertRaises(HTTPException) as cm:
            trips.patch_photo_context(cid, _Req(include_in_memoir=True))
        self.assertEqual(cm.exception.status_code, 400)

    def test_include_in_memoir_ok_when_approved_same_request(self):
        cid = self._ocr_row()
        out = trips.patch_photo_context(
            cid, _Req(approved_for_lori=True, include_in_memoir=True))
        self.assertTrue(out["ok"])
        row = trip_repository.photo_context_get(cid)
        self.assertEqual(row["include_in_memoir"], 1)

    def test_reject_hides_from_modal(self):
        cid = self._ocr_row(approved=True)
        trips.patch_photo_context(cid, _Req(rejected=True))
        pc = modal._photo_context_rows_for_scope(
            {"active_photo_link_id": self.link_id})
        self.assertEqual(pc["approved_ocr"], [])
        self.assertEqual(pc["draft_ocr"], [])


class ModalWordingTest(_DbCase):
    def _scope(self):
        return modal.build_modal_scope(
            self.person_id, self.trip_id, active_trip_region_id=self.region_id,
            active_trip_stop_id=self.stop_id,
            active_photo_link_id=self.link_id, selected_kind="photo")

    def test_draft_ocr_uses_appears_to_read(self):
        trip_repository.photo_context_create(
            trip_id=self.trip_id, photo_link_id=self.link_id,
            context_type="ocr_text",
            result_summary="Deutsches Jagd- und Fischereimuseum")
        ans = modal.answer_modal_direct_question(
            self.person_id, self._scope(), "tell me about this photo")
        self.assertIn("OCR draft appears to read", ans)
        self.assertNotIn("I can see", ans)
        self.assertNotIn("the image shows", ans)

    def test_approved_ocr_speaks_as_fact(self):
        cid = trip_repository.photo_context_create(
            trip_id=self.trip_id, photo_link_id=self.link_id,
            context_type="ocr_text",
            result_summary="Deutsches Jagd- und Fischereimuseum")
        trip_repository.photo_context_update(cid, approved_for_lori=True)
        ans = modal.answer_modal_direct_question(
            self.person_id, self._scope(), "tell me about this photo")
        self.assertIn("approved OCR text says", ans)
        self.assertNotIn("I can see", ans)

    def test_no_raw_gps_in_modal_answer(self):
        trip_repository.photo_context_create(
            trip_id=self.trip_id, photo_link_id=self.link_id,
            context_type="ocr_text", result_summary="sign text")
        ans = modal.answer_modal_direct_question(
            self.person_id, self._scope(), "tell me about this photo")
        for forbidden in ("48.1", "11.5", "latitude", "longitude"):
            self.assertNotIn(forbidden, ans)


class PublicLookupEndpointTest(_DbCase):
    def test_lookup_disabled_returns_status_no_row(self):
        os.environ.pop("HORNELORE_PUBLIC_LOOKUP", None)
        out = trips.public_context_lookup(
            self.trip_id, _Req(query="museum munich"))
        self.assertEqual(out["status"], "disabled")
        self.assertEqual(trip_repository.public_context_list(self.trip_id), [])

    def test_lookup_stores_draft_public_context_off(self):
        os.environ["HORNELORE_PUBLIC_LOOKUP"] = "1"
        orig = lookup.run_lookup
        lookup.run_lookup = lambda query=None, url=None: {
            "ok": True, "provider": "url_only",
            "summary": "German Hunting and Fishing Museum, Munich.",
            "title": "Museum", "source_url": "https://example.org", "error": None}
        try:
            out = trips.public_context_lookup(
                self.trip_id, _Req(url="https://example.org"))
        finally:
            lookup.run_lookup = orig
        self.assertEqual(out["status"], "stored")
        row = out["context"]
        self.assertEqual(row["approved_for_lori"], 0)
        self.assertEqual(row["include_in_memoir"], 0)
        self.assertEqual(row["confidence"], "draft")

    def test_lookup_rejects_cross_trip_photo_link(self):
        os.environ["HORNELORE_PUBLIC_LOOKUP"] = "1"
        # a photo link on a DIFFERENT trip
        other_trip = trip_repository.trip_create(self.person_id, "Italy")
        other_region = trip_repository.region_create(other_trip, "Tuscany")
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO photos (id, narrator_id, image_path, file_hash, "
            "narrator_ready) VALUES ('ph2', ?, '/tmp/ph2.jpg', 'h2', 1)",
            (self.person_id,))
        con.commit()
        con.close()
        other_link = trip_repository.photo_link_upsert(
            other_trip, "ph2", trip_region_id=other_region,
            assignment_method="operator")
        with self.assertRaises(HTTPException) as cm:
            trips.public_context_lookup(
                self.trip_id, _Req(query="x", photo_link_id=other_link))
        self.assertEqual(cm.exception.status_code, 400)


class LookupQueryPrivacyTest(_DbCase):
    def test_photo_query_uses_ocr_place_year_not_gps_or_person(self):
        # OCR row + a reviewable place/date on the link
        trip_repository.photo_context_create(
            trip_id=self.trip_id, photo_link_id=self.link_id,
            context_type="ocr_text", result_summary="Museum sign text")
        con = sqlite3.connect(str(self.db_path))
        con.execute("UPDATE photos SET date_value='2026-05-14', "
                    "location_label='Munich', latitude=48.137, "
                    "longitude=11.576 WHERE id='ph1'")
        con.commit()
        con.close()
        q = trips._build_photo_lookup_query(self.link_id, self.trip_id)
        self.assertIn("Museum sign text", q)
        self.assertIn("Munich", q)
        self.assertIn("2026", q)
        # never leak GPS or the person id
        self.assertNotIn("48.137", q)
        self.assertNotIn("11.576", q)
        self.assertNotIn(self.person_id, q)


class NarratorFacingGuardTest(_DbCase):
    def _ctx_text(self):
        ctx = tic.build_trip_interview_context(self.person_id, self.trip_id)
        return (ctx or {}).get("text", "")

    def test_unapproved_ocr_not_in_narrator_context(self):
        trip_repository.photo_context_create(
            trip_id=self.trip_id, photo_link_id=self.link_id,
            context_type="ocr_text", result_summary="DRAFT_ONLY_SIGN")
        self.assertNotIn("DRAFT_ONLY_SIGN", self._ctx_text())

    def test_approved_ocr_in_narrator_context_with_safe_wording(self):
        cid = trip_repository.photo_context_create(
            trip_id=self.trip_id, photo_link_id=self.link_id,
            context_type="ocr_text", result_summary="APPROVED_SIGN")
        trip_repository.photo_context_update(cid, approved_for_lori=True)
        text = self._ctx_text()
        self.assertIn("APPROVED_SIGN", text)
        self.assertIn("the text on one photo reads", text)
        self.assertNotIn("I can see", text)

    def test_rejected_ocr_not_in_narrator_context(self):
        cid = trip_repository.photo_context_create(
            trip_id=self.trip_id, photo_link_id=self.link_id,
            context_type="ocr_text", result_summary="REJECTED_SIGN")
        trip_repository.photo_context_update(
            cid, approved_for_lori=True, rejected=True)
        self.assertNotIn("REJECTED_SIGN", self._ctx_text())


if __name__ == "__main__":
    unittest.main()
