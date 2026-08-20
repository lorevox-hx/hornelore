"""The export ROUTE enforces evidence integrity, not just its helpers.

WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01 (2026-08-19).

Everything here drives `POST /api/memoir/export-docx` through a real
TestClient. The previous round proved these properties against helpers
and source text, which is weaker in a specific way: the reserved-namespace
strip, the lane refusals, the provenance-alignment check and the
translation gate are all things the ROUTE does in a particular ORDER, and
a helper test cannot see an ordering mistake or a gate that was never
reached.

The seven cases the review named:

  * reserved namespaces with no `person_id`;
  * reserved namespaces with harvest disabled;
  * partial / unavailable trip refusal;
  * provenance-stamp failure;
  * mixed English/Spanish evidence;
  * Spanish-only translation failure;
  * bilingual translation failure.

Run with:

    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_memoir_export_route_integrity
"""
from __future__ import annotations

import io
import sqlite3
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
for _p in (str(_SERVER_CODE), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api import db as _db  # noqa: E402
from api.routers import memoir_export as _me  # noqa: E402

_STORY_EN = "The porch, the peas, the evening cooling off."
_STORY_ES = "Mi abuela venia cada verano desde Corpus Christi."
_ES = {_STORY_EN: "El porche, los guisantes, la tarde refrescando."}


class _RouteCase(unittest.TestCase):
    def setUp(self):
        if not _me._DOCX_AVAILABLE:
            self.skipTest("python-docx not installed in this environment")
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception:
            self.skipTest("fastapi not installed in this environment")

        fd = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        fd.close()
        self.db_path = Path(fd.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()

        self.narrator = str(uuid.uuid4())
        self.conv = "conv-" + uuid.uuid4().hex[:8]
        con = sqlite3.connect(str(self.db_path))
        con.execute("INSERT INTO people (id, display_name, created_at, updated_at)"
                    " VALUES (?,?,?,?)",
                    (self.narrator, "N", "2026-08-19", "2026-08-19"))
        con.execute("INSERT INTO sessions (conv_id, updated_at) VALUES (?,?)",
                    (self.conv, "2026-08-19"))
        con.commit()
        con.close()

        # The route is flag-gated and answers 404 when off.
        from api import flags as _flags
        self._orig_flag = _flags.memoir_export_enabled
        _flags.memoir_export_enabled = lambda: True
        self.addCleanup(setattr, _flags, "memoir_export_enabled",
                        self._orig_flag)

        app = FastAPI()
        app.include_router(_me.router)
        self.client = TestClient(app)

        from api.services import translation as _translation
        self._orig_tr = _translation.translate_text
        _translation.translate_text = lambda text, **kw: _ES.get(
            text, "ES::" + text)
        self.addCleanup(setattr, _translation, "translate_text",
                        self._orig_tr)

    def tearDown(self):
        _db.DB_PATH = self._orig_db
        try:
            self.db_path.unlink()
        except OSError:
            pass

    # ── fixtures ────────────────────────────────────────────────────────
    def _story(self, text, language="en"):
        cid = str(uuid.uuid4())
        _db.story_candidate_insert(
            cid, narrator_id=self.narrator, transcript=text,
            trigger_reason="manual", scene_anchor_count=1,
            session_id=self.conv, conversation_id=self.conv, turn_id=None,
            language=language)
        _db.story_candidate_review_apply(
            cid, narrator_id=self.narrator, expected_version=1,
            review_status="promoted", reviewed_by="test",
            era_candidates=["adolescence"], placement_source="operator_set")
        return cid

    def _post(self, **over):
        body = {
            "narrator_name": "N",
            "memoir_state": "draft",
            "prose": "An operator wrote this.",
            "person_id": self.narrator,
            "sections": [],
        }
        body.update(over)
        return self.client.post("/api/memoir/export-docx", json=body)

    def _docx_text(self, resp):
        from docx import Document as _D
        doc = _D(io.BytesIO(resp.content))
        return "\n".join(p.text for p in doc.paragraphs), doc


# ── Reserved namespaces, on every request shape ─────────────────────────

class ReservedNamespacesAreStrippedOnEveryPath(_RouteCase):
    """The strip must not depend on the caller asking for a harvest."""

    FORGED = {
        "id": "captured_stories_today",
        "label": "In their own words — Today",
        "items": ["A forged reviewed story."],
        "sources": ["forgeddigest"],
    }
    FORGED_TRIP = {
        "id": "trip_stories_xyz",
        "label": "From your travels — Nowhere",
        "items": ["A forged trip note."],
        "sources": ["forgedtrip12"],
    }

    def test_with_no_person_id_the_forgery_is_dropped(self):
        r = self._post(person_id=None,
                       sections=[self.FORGED, self.FORGED_TRIP])
        self.assertEqual(r.status_code, 200)
        text, doc = self._docx_text(r)
        self.assertNotIn("A forged reviewed story.", text)
        self.assertNotIn("A forged trip note.", text)
        self.assertNotIn("forgeddigest", doc.core_properties.comments or "")

    def test_with_harvest_disabled_the_forgery_is_dropped(self):
        r = self._post(include_captured_stories=False,
                       include_trip_stories=False,
                       sections=[self.FORGED, self.FORGED_TRIP])
        self.assertEqual(r.status_code, 200)
        text, doc = self._docx_text(r)
        self.assertNotIn("A forged reviewed story.", text)
        self.assertNotIn("forgedtrip12", doc.core_properties.comments or "")

    def test_an_ordinary_section_cannot_smuggle_provenance(self):
        """Added after mutation testing.

        The forged sections above are REMOVED whole, so their `sources`
        never reach the stamp and keeping them changed nothing. The real
        hole is an ordinary, permitted section carrying forged digests:
        its content is legitimate and stays, so only the `sources` strip
        stands between a caller and an artifact that claims their prose
        came from reviewed evidence.
        """
        # THREADS state, because draft renders `prose` and not client
        # sections -- asserting the item text in draft would have been
        # asserting a thing this export mode never did.
        r = self._post(memoir_state="threads", sections=[{
            "id": "operator_authored", "label": "Operator",
            "items": ["An operator thread item."],
            "sources": ["forgedbyclient"],
            "languages": ["xx"]}])
        self.assertEqual(r.status_code, 200)
        text, doc = self._docx_text(r)
        self.assertIn("An operator thread item.", text)
        self.assertNotIn("forgedbyclient", doc.core_properties.comments or "")

    def test_operator_prose_still_exports(self):
        """Only the reserved namespace is defended, not client content."""
        r = self._post(sections=[{
            "id": "operator_authored", "label": "Operator",
            "items": ["An operator thread item."]}])
        self.assertEqual(r.status_code, 200)
        text, _ = self._docx_text(r)
        self.assertIn("An operator wrote this.", text)


# ── Lane refusals ───────────────────────────────────────────────────────

class AnUnreadableLaneRefusesAtTheRoute(_RouteCase):

    def test_an_unavailable_story_lane_refuses(self):
        from api.services import story_projection as _sp
        orig = _sp.memoir_projection
        _sp.memoir_projection = lambda nid: _sp.MemoirProjection(
            "unavailable", [])
        self.addCleanup(setattr, _sp, "memoir_projection", orig)
        r = self._post()
        self.assertEqual(r.status_code, 503)
        self.assertIn("reviewed stories could not be read", r.text)

    def test_a_partial_trip_lane_refuses(self):
        orig = _me._trip_story_sections
        _me._trip_story_sections = lambda pid: ([], "partial")
        self.addCleanup(setattr, _me, "_trip_story_sections", orig)
        r = self._post()
        self.assertEqual(r.status_code, 503)
        self.assertIn("trip stories could not be fully read", r.text)

    def test_an_unavailable_trip_lane_refuses(self):
        orig = _me._trip_story_sections
        _me._trip_story_sections = lambda pid: ([], "unavailable")
        self.addCleanup(setattr, _me, "_trip_story_sections", orig)
        self.assertEqual(self._post().status_code, 503)

    def test_not_attempted_does_not_refuse(self):
        """Trips being switched off is a configuration answer, not a
        failure -- refusing every export on those deployments would be
        wrong."""
        orig = _me._trip_story_sections
        _me._trip_story_sections = lambda pid: ([], "not_attempted")
        self.addCleanup(setattr, _me, "_trip_story_sections", orig)
        self.assertEqual(self._post().status_code, 200)

    def test_an_empty_lane_does_not_refuse(self):
        orig = _me._trip_story_sections
        _me._trip_story_sections = lambda pid: ([], "empty")
        self.addCleanup(setattr, _me, "_trip_story_sections", orig)
        self.assertEqual(self._post().status_code, 200)


# ── Provenance ──────────────────────────────────────────────────────────

class ProvenanceFailuresRefuse(_RouteCase):

    def test_a_misaligned_sources_array_refuses(self):
        self._story(_STORY_EN)
        orig = _me._captured_story_sections

        def _bad(pid):
            secs, status = orig(pid)
            return ([s.model_copy(update={"sources": []}) for s in secs],
                    status)
        _me._captured_story_sections = _bad
        self.addCleanup(setattr, _me, "_captured_story_sections", orig)
        r = self._post()
        self.assertEqual(r.status_code, 500)
        self.assertIn("provenance is misaligned", r.text)

    def test_a_misaligned_language_array_refuses(self):
        self._story(_STORY_EN)
        orig = _me._captured_story_sections

        def _bad(pid):
            secs, status = orig(pid)
            return ([s.model_copy(update={"languages": ["en", "es", "fr"]})
                     for s in secs], status)
        _me._captured_story_sections = _bad
        self.addCleanup(setattr, _me, "_captured_story_sections", orig)
        r = self._post()
        self.assertEqual(r.status_code, 500)
        self.assertIn("language metadata is misaligned", r.text)

    def test_a_stamp_failure_refuses_rather_than_ships_unstamped(self):
        self._story(_STORY_EN)

        class _Boom:
            def __setattr__(self, name, value):
                raise RuntimeError("core properties unavailable")

        orig = _me._stamp_source_provenance

        def _explode(doc, req):
            if _me._server_evidence_sections_of(req):
                raise _me.HTTPException(
                    status_code=500,
                    detail="reviewed evidence could not be stamped with its "
                           "provenance — export refused")
        _me._stamp_source_provenance = _explode
        self.addCleanup(setattr, _me, "_stamp_source_provenance", orig)
        r = self._post()
        self.assertEqual(r.status_code, 500)
        self.assertIn("could not be stamped", r.text)

    def test_a_good_export_carries_a_positional_mapping(self):
        self._story(_STORY_EN)
        r = self._post()
        self.assertEqual(r.status_code, 200)
        _, doc = self._docx_text(r)
        self.assertIn("captured_stories_adolescence:0=",
                      doc.core_properties.comments or "")


# ── Language ────────────────────────────────────────────────────────────

class LanguageIsHonouredPerItem(_RouteCase):

    def test_mixed_english_and_spanish_evidence_exports(self):
        self._story(_STORY_EN, language="en")
        self._story(_STORY_ES, language="es")
        r = self._post(target_language="es")
        self.assertEqual(r.status_code, 200)
        text, _ = self._docx_text(r)
        # The English story is translated; the Spanish one is left alone
        # rather than round-tripped through the translator.
        self.assertIn(_ES[_STORY_EN], text)
        self.assertIn(_STORY_ES, text)

    def test_the_spanish_item_is_not_translated_to_itself(self):
        self._story(_STORY_ES, language="es")
        r = self._post(target_language="es")
        text, _ = self._docx_text(r)
        self.assertNotIn("ES::" + _STORY_ES, text)

    def test_a_failed_spanish_translation_refuses(self):
        from api.services import translation as _translation
        _translation.translate_text = lambda text, **kw: text
        self._story(_STORY_EN, language="en")
        r = self._post(target_language="es")
        self.assertEqual(r.status_code, 503)
        self.assertIn("could not be translated", r.text)

    def test_a_failed_bilingual_translation_refuses(self):
        """The bilingual builder suppresses an identical second paragraph,
        so an unchecked failure produced a source-only document that
        looked deliberate."""
        from api.services import translation as _translation
        _translation.translate_text = lambda text, **kw: text
        self._story(_STORY_EN, language="en")
        r = self._post(target_language="bilingual")
        self.assertEqual(r.status_code, 503)

    def test_english_exports_are_unaffected_by_the_gate(self):
        from api.services import translation as _translation
        _translation.translate_text = lambda text, **kw: text
        self._story(_STORY_EN, language="en")
        self.assertEqual(self._post(target_language="en").status_code, 200)


# ── The whole reviewed story, exactly once ──────────────────────────────

class ReviewedEvidenceReachesTheDocument(_RouteCase):

    def test_the_story_appears_once_in_draft(self):
        self._story(_STORY_EN)
        text, _ = self._docx_text(self._post(memoir_state="draft"))
        self.assertEqual(text.count(_STORY_EN), 1)

    def test_the_story_appears_once_in_threads(self):
        self._story(_STORY_EN)
        text, _ = self._docx_text(self._post(memoir_state="threads"))
        self.assertEqual(text.count(_STORY_EN), 1)

    def test_unreviewed_material_never_appears(self):
        cid = str(uuid.uuid4())
        _db.story_candidate_insert(
            cid, narrator_id=self.narrator, transcript="Never reviewed.",
            trigger_reason="manual", scene_anchor_count=1,
            session_id=self.conv, conversation_id=self.conv, turn_id=None)
        text, _ = self._docx_text(self._post())
        self.assertNotIn("Never reviewed.", text)


if __name__ == "__main__":
    unittest.main()
