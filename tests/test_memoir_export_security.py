"""WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 — Phase 5: memoir
export authority, containment, and feature gate.

The 2026-07-24 code review found POST /api/memoir/export-docx:
  - had NO feature-flag gate (trips/photos both 404 when off);
  - embedded AttachedPhoto.file_path — a client-supplied absolute
    path — directly via doc.add_picture() (arbitrary server file read);
  - dumped any narrator's captured-story transcripts for an arbitrary
    person_id;
  - built Content-Disposition from narrator_name with only space/slash
    replacement (CR/LF/quote header injection).

This module locks in the hardened contract: gate posture, server-side
media resolution contained within the media root, person existence,
operator-cleared story statuses, and a strict allowlist filename.

Runs against REAL fastapi/pydantic (installed in this env) with an
in-process TestClient, a tempfile sqlite DB, and a tempfile media root
injected via the MEDIA_DIR env var.
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
import tempfile
import unittest
import uuid
import zipfile
from io import BytesIO
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

# If a sibling test module (test_memoir_story_wire offline mode) already
# installed fastapi/pydantic STUBS in sys.modules, purge them so this
# module gets the real packages — these tests exercise the live HTTP
# surface and need a real TestClient.
_purged_stub = False
for _name in ("fastapi.responses", "fastapi", "pydantic"):
    _mod = sys.modules.get(_name)
    if _mod is not None and getattr(_mod, "__spec__", None) is None:
        del sys.modules[_name]
        _purged_stub = True

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from api import db as _db  # noqa: E402

if _purged_stub and "api.routers.memoir_export" in sys.modules:
    import importlib
    memoir_export = importlib.reload(sys.modules["api.routers.memoir_export"])
else:
    from api.routers import memoir_export  # noqa: E402


_GATE_ENV = "HORNELORE_MEMOIR_EXPORT_ENABLED"


def _write_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (4, 4), (170, 136, 68)).save(path, format="PNG")


class _SecurityCase(unittest.TestCase):
    """Shared fixture: temp DB, temp media root, gate ON by default."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        base = Path(self._tmpdir.name)
        self.media_root = base / "media_root"
        self.media_root.mkdir()
        self.outside_dir = base / "outside"
        self.outside_dir.mkdir()

        # Temp DB (same pattern as test_memoir_story_wire).
        self.db_path = base / "test.sqlite3"
        self._orig_db_path = _db.DB_PATH
        _db.DB_PATH = self.db_path
        self.addCleanup(lambda: setattr(_db, "DB_PATH", self._orig_db_path))
        _db.init_db()

        # Env: media root + gate. Restore exactly on teardown.
        self._env_backup = {
            k: os.environ.get(k) for k in ("MEDIA_DIR", "DATA_DIR", _GATE_ENV)
        }
        self.addCleanup(self._restore_env)
        os.environ["MEDIA_DIR"] = str(self.media_root)
        os.environ[_GATE_ENV] = "1"

        self.person_id = self._seed_person("Security Test")

        app = FastAPI()
        app.include_router(memoir_export.router)
        self.client = TestClient(app, raise_server_exceptions=True)

    def _restore_env(self):
        for k, v in self._env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # -- seed helpers -------------------------------------------------------

    def _seed_person(self, name: str) -> str:
        pid = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO people (id, display_name, created_at, updated_at) "
            "VALUES (?, ?, '2026-07-24', '2026-07-24');",
            (pid, name))
        con.commit()
        con.close()
        return pid

    def _seed_media(self, filename: str, *, person_id=None,
                    mime: str = "image/png") -> str:
        row = _db.add_media(
            person_id=person_id or self.person_id,
            filename=filename,
            mime=mime,
            bytes=1,
            sha256="x",
            kind="image",
        )
        return row["id"]

    def _seed_story(self, transcript: str, status: str, eras=None) -> str:
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

    # -- request helpers ----------------------------------------------------

    def _payload(self, **over):
        p = {
            "narrator_name": "Security Test",
            "memoir_state": "threads",
            "person_id": self.person_id,
            "include_captured_stories": False,
            "sections": [
                {"id": "sec1", "label": "Section One", "items": ["An item."]},
            ],
            "attached_photos": [],
        }
        p.update(over)
        return p

    def _post(self, **over):
        return self.client.post("/api/memoir/export-docx",
                                json=self._payload(**over))

    def _record_photo_renders(self):
        """Wrap _add_photo_to_doc to capture (media_id, resolved) for
        every render call — proves which path reached add_picture."""
        calls = []
        orig = memoir_export._add_photo_to_doc

        def _rec(doc, photo, resolved):
            calls.append((photo.media_id, resolved))
            return orig(doc, photo, resolved)

        memoir_export._add_photo_to_doc = _rec
        self.addCleanup(
            lambda: setattr(memoir_export, "_add_photo_to_doc", orig))
        return calls

    @staticmethod
    def _docx_xml(resp) -> str:
        with zipfile.ZipFile(BytesIO(resp.content)) as z:
            return z.read("word/document.xml").decode("utf-8")

    @staticmethod
    def _docx_media_names(resp):
        with zipfile.ZipFile(BytesIO(resp.content)) as z:
            return [n for n in z.namelist() if n.startswith("word/media/")]


# ---------------------------------------------------------------------------
# 5.1 — feature gate
# ---------------------------------------------------------------------------

class GateTest(_SecurityCase):
    def test_gate_off_returns_404(self):
        os.environ.pop(_GATE_ENV, None)
        resp = self._post()
        self.assertEqual(resp.status_code, 404)

    def test_gate_explicit_zero_returns_404(self):
        os.environ[_GATE_ENV] = "0"
        self.assertEqual(self._post().status_code, 404)

    def test_gate_on_returns_docx(self):
        resp = self._post()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.content.startswith(b"PK"))  # zip magic
        self.assertIn("wordprocessingml", resp.headers["content-type"])


# ---------------------------------------------------------------------------
# 5.2 / 5.3 — client path authority removed; server-side containment
# ---------------------------------------------------------------------------

class MediaAuthorityTest(_SecurityCase):
    def test_client_file_path_is_ignored(self):
        # Old-client wire shape still sends file_path — the server must
        # render only the media-table path, never /etc/passwd.
        img = self.media_root / self.person_id / "real.png"
        _write_png(img)
        mid = self._seed_media(str(img))
        calls = self._record_photo_renders()
        resp = self._post(attached_photos=[{
            "media_id": mid,
            "section_key": "sec1",
            "file_path": "/etc/passwd",
        }])
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(calls), 1)
        _, resolved = calls[0]
        self.assertEqual(resolved, img.resolve())
        self.assertNotEqual(resolved, Path("/etc/passwd"))
        # Something actually embedded, and it came from the media root.
        self.assertTrue(self._docx_media_names(resp))

    def test_valid_relative_filename_joins_media_root(self):
        rel = f"{self.person_id}/photo.png"
        _write_png(self.media_root / rel)
        mid = self._seed_media(rel)  # relative stored filename
        calls = self._record_photo_renders()
        resp = self._post(attached_photos=[
            {"media_id": mid, "section_key": "sec1"}])
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(calls[0][1], (self.media_root / rel).resolve())

    def test_valid_absolute_filename_inside_root_embeds(self):
        img = self.media_root / "abs.png"
        _write_png(img)
        mid = self._seed_media(str(img))
        resp = self._post(attached_photos=[
            {"media_id": mid, "section_key": "sec1"}])
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(self._docx_media_names(resp))

    def test_unknown_media_id_is_422(self):
        resp = self._post(attached_photos=[
            {"media_id": "no-such-media", "section_key": "sec1"}])
        self.assertEqual(resp.status_code, 422)
        self.assertIn("no-such-media", resp.json()["detail"])

    def test_stored_path_outside_root_is_422(self):
        img = self.outside_dir / "escape.png"
        _write_png(img)
        mid = self._seed_media(str(img))  # absolute, outside media root
        resp = self._post(attached_photos=[
            {"media_id": mid, "section_key": "sec1"}])
        self.assertEqual(resp.status_code, 422)
        self.assertIn("outside the media root", resp.json()["detail"])

    def test_symlink_escaping_root_is_422(self):
        target = self.outside_dir / "target.png"
        _write_png(target)
        link = self.media_root / "sneaky.png"
        link.symlink_to(target)
        mid = self._seed_media("sneaky.png")
        resp = self._post(attached_photos=[
            {"media_id": mid, "section_key": "sec1"}])
        self.assertEqual(resp.status_code, 422)
        self.assertIn("outside the media root", resp.json()["detail"])

    def test_wrong_person_media_is_422(self):
        img = self.media_root / "other.png"
        _write_png(img)
        other = self._seed_person("Someone Else")
        mid = self._seed_media(str(img), person_id=other)
        resp = self._post(attached_photos=[
            {"media_id": mid, "section_key": "sec1"}])
        self.assertEqual(resp.status_code, 422)
        self.assertIn("does not belong", resp.json()["detail"])

    def test_non_image_mime_is_422(self):
        doc = self.media_root / "notes.pdf"
        doc.parent.mkdir(parents=True, exist_ok=True)
        doc.write_bytes(b"%PDF-1.4 fake")
        mid = self._seed_media(str(doc), mime="application/pdf")
        resp = self._post(attached_photos=[
            {"media_id": mid, "section_key": "sec1"}])
        self.assertEqual(resp.status_code, 422)
        self.assertIn("non-image mime", resp.json()["detail"])

    def test_missing_file_on_disk_is_422(self):
        mid = self._seed_media(str(self.media_root / "ghost.png"))
        resp = self._post(attached_photos=[
            {"media_id": mid, "section_key": "sec1"}])
        self.assertEqual(resp.status_code, 422)
        self.assertIn("missing on disk", resp.json()["detail"])

    def test_corrupt_authorized_image_skips_gracefully(self):
        corrupt = self.media_root / "corrupt.png"
        corrupt.write_bytes(b"this is not a png at all")
        mid = self._seed_media(str(corrupt))
        calls = self._record_photo_renders()
        resp = self._post(attached_photos=[
            {"media_id": mid, "section_key": "sec1"}])
        # Authorized + contained but unreadable → graceful skip, and
        # ONLY the corrupt path was ever handed to the renderer.
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], corrupt.resolve())
        self.assertEqual(self._docx_media_names(resp), [])

    def test_media_root_falls_back_to_data_dir(self):
        # WO rule: MEDIA_DIR env when set, else DATA_DIR/media.
        os.environ.pop("MEDIA_DIR", None)
        os.environ["DATA_DIR"] = self._tmpdir.name
        self.assertEqual(
            memoir_export._media_root(),
            (Path(self._tmpdir.name) / "media").resolve())
        os.environ["MEDIA_DIR"] = str(self.media_root)
        self.assertEqual(memoir_export._media_root(),
                         self.media_root.resolve())


# ---------------------------------------------------------------------------
# 5.4 — narrator scope
# ---------------------------------------------------------------------------

class NarratorScopeTest(_SecurityCase):
    def test_unknown_person_id_refused(self):
        resp = self._post(person_id=str(uuid.uuid4()))
        self.assertEqual(resp.status_code, 422)
        self.assertIn("not found in people", resp.json()["detail"])

    def test_captured_stories_require_operator_cleared_status(self):
        # Extends the test_memoir_story_wire fixtures over the live
        # HTTP surface: promoted/memoir_only export; everything else
        # never leaves the review queue.
        self._seed_story("Promoted childhood story.", "promoted",
                         ["earliest_years"])
        self._seed_story("Memoir-only Munich story.", "memoir_only",
                         ["later_years"])
        self._seed_story("Unreviewed secret.", "unreviewed", ["today"])
        self._seed_story("Discarded secret.", "discarded", ["today"])
        self._seed_story("Mid-review secret.", "in_review", ["today"])
        resp = self._post(include_captured_stories=True)
        self.assertEqual(resp.status_code, 200)
        xml = self._docx_xml(resp)
        self.assertIn("Promoted childhood story.", xml)
        self.assertIn("Memoir-only Munich story.", xml)
        self.assertNotIn("Unreviewed secret.", xml)
        self.assertNotIn("Discarded secret.", xml)
        self.assertNotIn("Mid-review secret.", xml)

    def test_stories_load_server_side_not_from_client_sections(self):
        # A client cannot smuggle person-B transcripts by naming
        # person A — harvest is keyed strictly to the verified
        # person_id, server-side.
        other = self._seed_person("Narrator B")
        cid = str(uuid.uuid4())
        _db.story_candidate_insert(
            cid, other, "Narrator B private story.",
            trigger_reason="full_threshold", era_candidates=["today"])
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "UPDATE story_candidates SET review_status='promoted' "
            "WHERE id=?;", (cid,))
        con.commit()
        con.close()
        resp = self._post(include_captured_stories=True)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("Narrator B private story.", self._docx_xml(resp))


# ---------------------------------------------------------------------------
# 5.5 — safe Content-Disposition filename
# ---------------------------------------------------------------------------

class FilenameTest(_SecurityCase):
    _CD_RE = re.compile(r'^attachment; filename="[A-Za-z0-9_.-]+\.docx"$')

    def test_injection_characters_sanitized(self):
        # NB: \x07-style control chars are covered by the sanitizer
        # unit test below — lxml (pre-existing, out of WO scope)
        # rejects them in the docx BODY before the header is built.
        evil = 'Ev"il\r\nContent-Length: 0 \\../name'
        resp = self._post(narrator_name=evil)
        self.assertEqual(resp.status_code, 200)
        cd = resp.headers["content-disposition"]
        for bad in ("\r", "\n", "/", "\\"):
            self.assertNotIn(bad, cd)
        self.assertEqual(cd.count('"'), 2)  # only the wrapping quotes
        self.assertRegex(cd, self._CD_RE)

    def test_memoir_state_component_sanitized_too(self):
        resp = self._post(memoir_state='thr"eads\r\n/..')
        self.assertEqual(resp.status_code, 200)
        self.assertRegex(resp.headers["content-disposition"], self._CD_RE)

    def test_empty_name_falls_back_deterministically(self):
        resp = self._post(narrator_name='"""\r\n///')
        self.assertEqual(resp.status_code, 200)
        cd = resp.headers["content-disposition"]
        self.assertRegex(cd, self._CD_RE)
        self.assertIn("lorevox_memoir_memoir_", cd)  # fallback component

    def test_sanitizer_unit_contract(self):
        f = memoir_export._safe_filename_component
        self.assertEqual(f('a"b/c\\d\r\ne', fallback="memoir"), "a_b_c_d__e")
        self.assertEqual(f("x\x07y\x00z", fallback="memoir"), "x_y_z")
        self.assertEqual(f("", fallback="memoir"), "memoir")
        self.assertEqual(f(None, fallback="memoir"), "memoir")
        self.assertEqual(f('"""', fallback="memoir"), "memoir")
        self.assertLessEqual(
            len(f("x" * 500, fallback="memoir", max_len=80)), 80)


if __name__ == "__main__":
    unittest.main()
