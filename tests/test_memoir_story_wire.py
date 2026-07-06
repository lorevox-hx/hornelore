"""WO-MEMOIR-STORY-CANDIDATES-WIRE-01 — captured stories reach the
memoir export.

The story-preservation lane (WO-LORI-STORY-CAPTURE-01) has been
writing story_candidates since 2026-04-30; nothing consumed them at
export time. This wire harvests operator-cleared rows (review_status
'promoted' or 'memoir_only') into era-grouped sections in the
narrator's OWN words. Gates: unreviewed/discarded never export;
absent person_id is byte-stable with pre-wire callers.
"""
from __future__ import annotations

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

# Offline stubs (fastapi/pydantic may be absent in the test env).
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
        # Kwargs-capable — this stub is shared via sys.modules with
        # other test files whose code raises HTTPException(status_code=...).
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

    def _field(default=None, default_factory=None, **k):
        if default_factory is not None:
            return default_factory()
        return default

    pstub.BaseModel = _BaseModel
    pstub.Field = _field
    sys.modules["pydantic"] = pstub

from api import db as _db  # noqa: E402
from api.routers import memoir_export  # noqa: E402


class _WireCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self._tmp.close()
        self.db_path = Path(self._tmp.name)
        self._orig = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()
        self.person_id = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO people (id, display_name, created_at, updated_at) "
            "VALUES (?, 'Wire Test', '2026-07-06', '2026-07-06');",
            (self.person_id,))
        con.commit()
        con.close()

    def tearDown(self):
        _db.DB_PATH = self._orig
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def _seed_story(self, transcript, status, eras=None):
        cid = str(uuid.uuid4())
        _db.story_candidate_insert(
            cid, self.person_id, transcript,
            trigger_reason="full_threshold",
            era_candidates=eras or [],
        )
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "UPDATE story_candidates SET review_status=? WHERE id=?;",
            (status, cid))
        con.commit()
        con.close()
        return cid


class HarvestTest(_WireCase):
    def test_promoted_and_memoir_only_export(self):
        self._seed_story("The mastoidectomy story, in her own words.",
                         "promoted", ["early_school_years"])
        self._seed_story("The Munich arrival story.",
                         "memoir_only", ["later_years"])
        sections = memoir_export._captured_story_sections(self.person_id)
        all_items = [i for s in sections for i in s.items]
        self.assertIn("The mastoidectomy story, in her own words.", all_items)
        self.assertIn("The Munich arrival story.", all_items)

    def test_unreviewed_and_discarded_never_export(self):
        # The export gate: a family-facing artifact only carries what
        # the operator cleared.
        self._seed_story("Not yet reviewed.", "unreviewed", ["today"])
        self._seed_story("Rejected story.", "discarded", ["today"])
        self._seed_story("Mid review.", "in_review", ["today"])
        sections = memoir_export._captured_story_sections(self.person_id)
        self.assertEqual(sections, [])

    def test_era_grouping_in_spine_order(self):
        self._seed_story("Later story.", "promoted", ["later_years"])
        self._seed_story("Childhood story.", "promoted", ["earliest_years"])
        sections = memoir_export._captured_story_sections(self.person_id)
        self.assertEqual(len(sections), 2)
        # Spine order, not insertion order.
        self.assertIn("earliest", sections[0].id)
        self.assertIn("later", sections[1].id)

    def test_unplaced_story_lands_in_trailing_group(self):
        self._seed_story("No era on this one.", "promoted", [])
        sections = memoir_export._captured_story_sections(self.person_id)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].id, "captured_stories_more")

    def test_transcripts_are_verbatim(self):
        raw = "We drove an' drove — Dad said \"almost there\" for two hours."
        self._seed_story(raw, "promoted", ["adolescence"])
        sections = memoir_export._captured_story_sections(self.person_id)
        self.assertEqual(sections[0].items, [raw])  # no rewriting, ever

    def test_no_person_no_sections(self):
        sections = memoir_export._captured_story_sections(str(uuid.uuid4()))
        self.assertEqual(sections, [])

    def test_harvest_never_raises(self):
        # Point at a broken DB path — must return [] not raise.
        _db.DB_PATH = Path("/nonexistent/nope.sqlite3")
        try:
            self.assertEqual(
                memoir_export._captured_story_sections(self.person_id), [])
        finally:
            _db.DB_PATH = self.db_path

    def test_request_model_defaults_are_byte_stable(self):
        # Absent person_id -> no harvest is even attempted; the field
        # defaults keep pre-wire request payloads valid.
        src = (_SERVER_CODE / "api" / "routers" / "memoir_export.py"
               ).read_text(encoding="utf-8")
        self.assertIn("person_id: Optional[str] = Field(default=None)", src)
        self.assertIn("include_captured_stories: bool = Field(default=True)", src)
        self.assertIn("req.person_id and req.include_captured_stories", src)

    def test_fe_passes_person_id(self):
        html = (_REPO_ROOT / "ui" / "hornelore1.0.html").read_text(
            encoding="utf-8")
        self.assertIn("person_id: (typeof state !== \"undefined\"", html)


if __name__ == "__main__":
    unittest.main()
