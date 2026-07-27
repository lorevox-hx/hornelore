"""WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01 Phase 1 — hide-not-delete.

Operator "delete" on trip evidence must be reversible. These tests pin
the full lifecycle on a real temp DB (migration 0036 applied via
init_db):

  * a HIDDEN note/source/photo-link appears in NONE of: the Draft
    Assistant context preview / evidence text, the travelogue builder
    outline (blocks + per-stop entries + intake_review + overview
    counts), the narrator interview context, the memoir preview + DOCX
    assembly, or the default list endpoints;
  * it DOES appear with include_hidden=1, remains in the DB, and PATCH
    hidden:false fully restores it to every consumer;
  * DELETE-as-hide preserves the row; purge with the exact confirm_id
    removes it; purge with a wrong confirm_id is a 422 and the row is
    intact;
  * context-row DELETE sets rejected=1 (never physical); an approved
    context row is a 409 and untouched;
  * hiding preserves the promotion/approval flags across a
    hide/restore round-trip.

Offline fastapi/pydantic stub pattern (same as
tests/test_travel_doc_evidence_tools).
"""
from __future__ import annotations

import io
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
from api.services import travelogue_builder  # noqa: E402
from api.services import trip_draft  # noqa: E402
from api.services import trip_interview_context as tic  # noqa: E402
from api.routers import trips  # noqa: E402

_SECRET_NOTE = "SECRET-NOTE-the bells rang over the empty square"
_SECRET_SOURCE = "SECRET-SOURCE-hotel bill from the Pension"
_SECRET_CAPTION = "SECRET-CAPTION-us on the bridge at dawn"


class _NotePatchReq:
    def __init__(self, **kw):
        base = dict(note_title=None, note_text=None, source_type=None,
                    source_ref=None, include_in_memoir=None,
                    include_in_interview_context=None, ord=None,
                    clear_title=False, hidden=None)
        base.update(kw)
        self.__dict__.update(base)


class _SourcePatchReq:
    def __init__(self, **kw):
        base = dict(source_type=None, title=None, pasted_text=None,
                    link_url=None, source_date=None, summary=None,
                    include_in_memoir=None, ord=None, trip_day_id=None,
                    clear_day=False, hidden=None)
        base.update(kw)
        self.__dict__.update(base)


class _LinkPatchReq:
    def __init__(self, **kw):
        base = dict(trip_stop_id=None, include_in_memoir=None, caption=None,
                    narrator_caption=None, confirm=False,
                    caption_approved_for_lori=None,
                    operator_context_note=None,
                    clear_operator_context_note=False,
                    operator_context_approved_for_lori=None, hidden=None)
        base.update(kw)
        self.__dict__.update(base)


class _CtxPatchReq:
    def __init__(self, **kw):
        base = dict(result_summary=None, notes=None, source_url=None,
                    query=None, raw_text=None, approved_for_lori=None,
                    include_in_memoir=None, rejected=None)
        base.update(kw)
        self.__dict__.update(base)


class _EvidenceDbCase(unittest.TestCase):
    """Temp-DB fixture: init_db applies every migration (0036 included),
    then one narrator + one narrator-ready photo + one trip with a
    region, a discovery stop, and a photo link."""

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
            "'2026-07-24', '2026-07-24');", (self.person_id,))
        con.execute(
            "INSERT INTO photos (id, narrator_id, image_path, file_hash, "
            "narrator_ready) VALUES ('ph1', ?, '/tmp/ph1.jpg', 'h1', 1)",
            (self.person_id,))
        con.commit()
        con.close()
        self.trip_id = trip_repository.trip_create(
            self.person_id, "Spring 2026", start_date="2026-05-22",
            end_date="2026-05-24")
        self.region_id = trip_repository.region_create(
            self.trip_id, "Bavaria")
        self.stop_id = trip_repository.stop_create(
            self.trip_id, self.region_id, "Munich", stop_type="sight")
        self.link_id = trip_repository.photo_link_upsert(
            self.trip_id, "ph1", trip_region_id=self.region_id,
            trip_stop_id=self.stop_id, assignment_method="operator")

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

    # ── helpers ────────────────────────────────────────────────────────
    def _make_note(self, **kw):
        base = dict(trip_id=self.trip_id, note_text=_SECRET_NOTE,
                    trip_region_id=self.region_id,
                    trip_stop_id=self.stop_id,
                    include_in_memoir=True,
                    include_in_interview_context=True)
        base.update(kw)
        return trip_repository.location_note_create(**base)

    def _make_source(self, **kw):
        base = dict(trip_id=self.trip_id, source_type="hotel",
                    title="Pension bill", summary=_SECRET_SOURCE,
                    trip_region_id=self.region_id,
                    trip_stop_id=self.stop_id, include_in_memoir=True)
        base.update(kw)
        return trip_repository.source_create(**base)

    def _outline_json(self):
        return json.dumps(
            travelogue_builder.build_travelogue_outline(self.trip_id))

    def _narrator_text(self):
        ctx = tic.build_trip_interview_context(self.person_id, self.trip_id)
        return (ctx or {}).get("text") or ""

    def _draft_ctx(self, **kw):
        return trip_draft.assemble_context(self.trip_id, **kw)


# ── Notes ───────────────────────────────────────────────────────────────


class NoteHideLifecycleTest(_EvidenceDbCase):

    def test_visible_note_reaches_all_consumers(self):
        # Baseline sanity — before hiding, the note is everywhere it
        # should be, so the exclusion assertions below mean something.
        self._make_note()
        self.assertIn(_SECRET_NOTE, self._outline_json())
        self.assertIn(_SECRET_NOTE, self._narrator_text())
        preview = trip_repository.trip_memoir_preview(self.trip_id)
        self.assertIn(_SECRET_NOTE, json.dumps(preview))
        ctx = self._draft_ctx(stop_id=self.stop_id)
        self.assertIn(_SECRET_NOTE,
                      json.dumps([n["text"] for n in ctx["notes"]]))
        listed = trips.list_location_notes(self.trip_id)
        self.assertIn(_SECRET_NOTE,
                      json.dumps([n["note_text"] for n in listed["notes"]]))

    def test_hidden_note_excluded_everywhere(self):
        nid = self._make_note()
        res = trips.patch_location_note(nid, _NotePatchReq(hidden=True))
        self.assertEqual(res["note"]["hidden"], 1)
        self.assertTrue(res["note"]["hidden_at"])

        # Travelogue builder: blocks + per-stop + intake + counts.
        outline = travelogue_builder.build_travelogue_outline(self.trip_id)
        blob = json.dumps(outline)
        self.assertNotIn(_SECRET_NOTE, blob)
        self.assertNotIn(nid, blob)
        self.assertEqual(outline["intake_review"]["count"], 0)

        # Draft Assistant preview + evidence text.
        ctx = self._draft_ctx(stop_id=self.stop_id)
        self.assertNotIn(_SECRET_NOTE, json.dumps(ctx))
        self.assertNotIn(_SECRET_NOTE, trip_draft._evidence_text(ctx))

        # Narrator interview context — hidden wins over
        # include_in_interview_context=1.
        self.assertNotIn(_SECRET_NOTE, self._narrator_text())

        # Memoir preview — hidden wins over include_in_memoir=1.
        preview = trip_repository.trip_memoir_preview(self.trip_id)
        self.assertNotIn(_SECRET_NOTE, json.dumps(preview))

        # Default list endpoint excludes; include_hidden surfaces it.
        listed = trips.list_location_notes(self.trip_id)
        self.assertEqual(listed["notes"], [])
        listed_all = trips.list_location_notes(self.trip_id,
                                               include_hidden=True)
        self.assertEqual([n["id"] for n in listed_all["notes"]], [nid])
        self.assertEqual(listed_all["notes"][0]["hidden"], 1)

        # Row is preserved in the DB with its flags intact.
        row = trip_repository.location_note_get(nid)
        self.assertIsNotNone(row)
        self.assertEqual(row["include_in_memoir"], 1)
        self.assertEqual(row["include_in_interview_context"], 1)

    def test_restore_returns_note_to_every_consumer(self):
        nid = self._make_note()
        trips.patch_location_note(nid, _NotePatchReq(hidden=True))
        res = trips.patch_location_note(nid, _NotePatchReq(hidden=False))
        self.assertEqual(res["note"]["hidden"], 0)
        self.assertIsNone(res["note"]["hidden_at"])
        self.assertIn(_SECRET_NOTE, self._outline_json())
        self.assertIn(_SECRET_NOTE, self._narrator_text())
        self.assertIn(_SECRET_NOTE,
                      json.dumps(trip_repository.trip_memoir_preview(
                          self.trip_id)))
        listed = trips.list_location_notes(self.trip_id)
        self.assertEqual([n["id"] for n in listed["notes"]], [nid])

    def test_hide_restore_roundtrip_preserves_flags(self):
        nid = self._make_note()
        trips.patch_location_note(nid, _NotePatchReq(hidden=True))
        trips.patch_location_note(nid, _NotePatchReq(hidden=False))
        row = trip_repository.location_note_get(nid)
        self.assertEqual(row["include_in_memoir"], 1)
        self.assertEqual(row["include_in_interview_context"], 1)
        self.assertEqual(row["source_type"], "operator")

    def test_delete_default_hides_row_preserved(self):
        nid = self._make_note()
        res = trips.delete_location_note(nid)
        self.assertEqual(
            {k: res[k] for k in ("ok", "hidden", "purged", "restorable")},
            {"ok": True, "hidden": True, "purged": False,
             "restorable": True})
        row = trip_repository.location_note_get(nid)
        self.assertIsNotNone(row)
        self.assertEqual(row["hidden"], 1)

    def test_purge_wrong_confirm_id_422_row_intact(self):
        nid = self._make_note()
        with self.assertRaises(HTTPException) as ctx:
            trips.delete_location_note(nid, purge=True,
                                       confirm_id="not-the-id")
        self.assertEqual(ctx.exception.status_code, 422)
        with self.assertRaises(HTTPException) as ctx2:
            trips.delete_location_note(nid, purge=True, confirm_id=None)
        self.assertEqual(ctx2.exception.status_code, 422)
        row = trip_repository.location_note_get(nid)
        self.assertIsNotNone(row)
        self.assertEqual(row["hidden"], 0)     # not even hidden

    def test_purge_exact_confirm_id_removes_row(self):
        nid = self._make_note()
        res = trips.delete_location_note(nid, purge=True, confirm_id=nid)
        self.assertTrue(res["purged"])
        self.assertIsNone(trip_repository.location_note_get(nid))

    def test_hidden_draft_note_out_of_intake_review(self):
        # Draft Assistant kept notes (source_type='draft') and Lori
        # captures (source_type='lori') ride the same lifecycle.
        did = self._make_note(source_type="draft", include_in_memoir=False,
                              include_in_interview_context=False,
                              note_text="draft: " + _SECRET_NOTE)
        lid = self._make_note(source_type="lori", include_in_memoir=False,
                              include_in_interview_context=False,
                              note_text="lori: " + _SECRET_NOTE)
        outline = travelogue_builder.build_travelogue_outline(self.trip_id)
        self.assertEqual(outline["intake_review"]["count"], 2)
        trips.patch_location_note(did, _NotePatchReq(hidden=True))
        trips.patch_location_note(lid, _NotePatchReq(hidden=True))
        outline = travelogue_builder.build_travelogue_outline(self.trip_id)
        self.assertEqual(outline["intake_review"]["count"], 0)
        # Both rows survive for restore.
        self.assertIsNotNone(trip_repository.location_note_get(did))
        self.assertIsNotNone(trip_repository.location_note_get(lid))


# ── Sources ─────────────────────────────────────────────────────────────


class SourceHideLifecycleTest(_EvidenceDbCase):

    def test_hidden_source_excluded_everywhere(self):
        sid = self._make_source()
        res = trips.patch_source(sid, _SourcePatchReq(hidden=True))
        self.assertEqual(res["source"]["hidden"], 1)
        # Draft assistant
        ctx = self._draft_ctx(stop_id=self.stop_id)
        self.assertNotIn(_SECRET_SOURCE, json.dumps(ctx))
        # Memoir preview
        self.assertNotIn(_SECRET_SOURCE,
                         json.dumps(trip_repository.trip_memoir_preview(
                             self.trip_id)))
        # Default list vs include_hidden
        self.assertEqual(trips.list_sources(self.trip_id)["sources"], [])
        allrows = trips.list_sources(self.trip_id,
                                     include_hidden=True)["sources"]
        self.assertEqual([s["id"] for s in allrows], [sid])
        # Row preserved with promotion flag intact.
        row = trip_repository.source_get(sid)
        self.assertEqual(row["include_in_memoir"], 1)

    def test_restore_source(self):
        sid = self._make_source()
        trips.patch_source(sid, _SourcePatchReq(hidden=True))
        trips.patch_source(sid, _SourcePatchReq(hidden=False))
        row = trip_repository.source_get(sid)
        self.assertEqual(row["hidden"], 0)
        self.assertIsNone(row["hidden_at"])
        self.assertIn(_SECRET_SOURCE,
                      json.dumps(trip_repository.trip_memoir_preview(
                          self.trip_id)))
        ctx = self._draft_ctx(stop_id=self.stop_id)
        self.assertIn(_SECRET_SOURCE, json.dumps(ctx))

    def test_delete_default_hides_purge_needs_exact_id(self):
        sid = self._make_source()
        res = trips.delete_source(sid)
        self.assertTrue(res["hidden"])
        self.assertIsNotNone(trip_repository.source_get(sid))
        with self.assertRaises(HTTPException) as ctx:
            trips.delete_source(sid, purge=True, confirm_id="wrong")
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIsNotNone(trip_repository.source_get(sid))
        res2 = trips.delete_source(sid, purge=True, confirm_id=sid)
        self.assertTrue(res2["purged"])
        self.assertIsNone(trip_repository.source_get(sid))

    def test_explicit_selection_of_hidden_source_reports_skipped(self):
        sid = self._make_source(include_in_memoir=False)
        trips.patch_source(sid, _SourcePatchReq(hidden=True))
        ctx = self._draft_ctx(stop_id=self.stop_id,
                              include_source_ids=[sid])
        # Never enters evidence, and the skip is visible.
        self.assertNotIn(_SECRET_SOURCE, json.dumps(ctx["sources"]))
        self.assertIn(sid, ctx["skipped_hidden_ids"])

    def test_explicit_selection_of_hidden_note_reports_skipped(self):
        nid = self._make_note(include_in_memoir=False,
                              include_in_interview_context=False)
        trips.patch_location_note(nid, _NotePatchReq(hidden=True))
        ctx = self._draft_ctx(stop_id=self.stop_id,
                              include_note_ids=[nid])
        self.assertNotIn(_SECRET_NOTE, json.dumps(ctx["notes"]))
        self.assertIn(nid, ctx["skipped_hidden_ids"])


# ── Photo links ─────────────────────────────────────────────────────────


class PhotoLinkHideLifecycleTest(_EvidenceDbCase):

    def setUp(self):
        super().setUp()
        trip_repository.photo_link_update(
            self.link_id, narrator_caption=_SECRET_CAPTION,
            include_in_memoir=True)

    def test_hidden_link_excluded_everywhere(self):
        res = trips.patch_photo_link(self.link_id,
                                     _LinkPatchReq(hidden=True))
        self.assertTrue(res["ok"])
        # Builder outline (photo packets + link ids + overview count).
        outline = travelogue_builder.build_travelogue_outline(self.trip_id)
        blob = json.dumps(outline)
        self.assertNotIn(self.link_id, blob)
        self.assertNotIn(_SECRET_CAPTION, blob)
        self.assertEqual(outline["overview"]["photo_count"], 0)
        # Narrator context (captions ride narrator_photo_links).
        self.assertNotIn(_SECRET_CAPTION, self._narrator_text())
        self.assertEqual(
            trip_repository.narrator_photo_links(self.trip_id), [])
        # Memoir/DOCX assembly path.
        self.assertEqual(
            trip_repository.photo_links_with_photo_paths(
                self.trip_id, memoir_only=False), [])
        # Default list endpoint vs include_hidden.
        self.assertEqual(trips.list_photo_links(self.trip_id)["count"], 0)
        allrows = trips.list_photo_links(
            self.trip_id, include_hidden=True)["photo_links"]
        self.assertEqual([l["id"] for l in allrows], [self.link_id])
        self.assertEqual(allrows[0]["hidden"], 1)
        self.assertTrue(allrows[0]["hidden_at"])
        # Tree photo counts exclude the hidden link.
        tree = trip_repository.trip_tree(self.trip_id)
        self.assertEqual(
            tree["regions"][0]["stops"][0]["photo_count"], 0)
        # Row preserved.
        row = trip_repository.photo_link_get(self.link_id)
        self.assertIsNotNone(row)
        self.assertEqual(row["hidden"], 1)

    def test_restore_link_and_flags_survive(self):
        trips.patch_photo_link(self.link_id, _LinkPatchReq(hidden=True))
        trips.patch_photo_link(self.link_id, _LinkPatchReq(hidden=False))
        row = trip_repository.photo_link_get(self.link_id)
        self.assertEqual(row["hidden"], 0)
        self.assertIsNone(row["hidden_at"])
        self.assertEqual(row["include_in_memoir"], 1)
        self.assertEqual(row["narrator_caption"], _SECRET_CAPTION)
        self.assertIn(_SECRET_CAPTION, self._narrator_text())
        self.assertEqual(trips.list_photo_links(self.trip_id)["count"], 1)


# ── Context rows: DELETE means REJECT ───────────────────────────────────


class ContextRejectDeleteTest(_EvidenceDbCase):

    def _public(self, **kw):
        base = dict(trip_id=self.trip_id, result_summary="museum context",
                    source_type="place_context")
        base.update(kw)
        return trip_repository.public_context_create(**base)

    def _photo_ctx(self, **kw):
        base = dict(trip_id=self.trip_id, photo_link_id=self.link_id,
                    context_type="ocr_text",
                    result_summary="sign reads Marienplatz")
        base.update(kw)
        return trip_repository.photo_context_create(**base)

    def test_public_context_delete_rejects_never_deletes(self):
        cid = self._public()
        res = trips.delete_public_context(cid)
        self.assertEqual(
            {k: res[k] for k in ("ok", "rejected", "purged")},
            {"ok": True, "rejected": True, "purged": False})
        row = trip_repository.public_context_get(cid)
        self.assertIsNotNone(row)
        self.assertEqual(row["rejected"], 1)

    def test_public_context_delete_approved_409_untouched(self):
        cid = self._public()
        trip_repository.public_context_update(cid, approved_for_lori=True)
        with self.assertRaises(HTTPException) as ctx:
            trips.delete_public_context(cid)
        self.assertEqual(ctx.exception.status_code, 409)
        row = trip_repository.public_context_get(cid)
        self.assertEqual(row["rejected"], 0)
        self.assertTrue(row["approved_for_lori"])

    def test_photo_context_delete_rejects_never_deletes(self):
        cid = self._photo_ctx()
        res = trips.delete_photo_context(cid)
        self.assertEqual(
            {k: res[k] for k in ("ok", "rejected", "purged")},
            {"ok": True, "rejected": True, "purged": False})
        row = trip_repository.photo_context_get(cid)
        self.assertIsNotNone(row)
        self.assertEqual(row["rejected"], 1)

    def test_photo_context_delete_approved_409_untouched(self):
        cid = self._photo_ctx()
        trip_repository.photo_context_update(cid, approved_for_lori=True,
                                             include_in_memoir=True)
        with self.assertRaises(HTTPException) as ctx:
            trips.delete_photo_context(cid)
        self.assertEqual(ctx.exception.status_code, 409)
        row = trip_repository.photo_context_get(cid)
        self.assertEqual(row["rejected"], 0)
        self.assertTrue(row["approved_for_lori"])
        self.assertTrue(row["include_in_memoir"])


# ── Memoir DOCX assembly ────────────────────────────────────────────────


class MemoirDocxHiddenExclusionTest(_EvidenceDbCase):

    def _docx_text(self):
        from docx import Document
        preview = trip_repository.trip_memoir_preview(self.trip_id)
        photo_rows = trip_repository.photo_links_with_photo_paths(
            self.trip_id, memoir_only=True)
        from api.services.trip_memoir_docx import build_trip_docx
        blob = build_trip_docx(preview, photo_rows)
        doc = Document(io.BytesIO(blob))
        return "\n".join(p.text for p in doc.paragraphs)

    def test_hidden_note_and_source_absent_from_docx(self):
        try:
            import docx  # noqa: F401
        except Exception:
            self.skipTest("python-docx not installed")
        nid = self._make_note()
        sid = self._make_source()
        text = self._docx_text()
        self.assertIn(_SECRET_NOTE, text)      # baseline: promoted rows in
        self.assertIn(_SECRET_SOURCE, text)
        trips.patch_location_note(nid, _NotePatchReq(hidden=True))
        trips.patch_source(sid, _SourcePatchReq(hidden=True))
        text = self._docx_text()
        self.assertNotIn(_SECRET_NOTE, text)   # hidden wins over
        self.assertNotIn(_SECRET_SOURCE, text)  # include_in_memoir=1


if __name__ == "__main__":
    unittest.main(verbosity=2)
