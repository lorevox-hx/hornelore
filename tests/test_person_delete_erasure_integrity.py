"""`hard_delete_person` tells the truth about what it removed.

WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01 — deletion integrity
(2026-08-20).

`tests/test_narrator_erasure.py` proves the erasure service in
isolation. This proves the DELETE PATH: that the service is actually
called, that the response carries the structured account the operator
needs, and -- the load-bearing one -- that a filesystem failure cannot
be answered as a completed deletion.

Run with:

    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_person_delete_erasure_integrity
"""
from __future__ import annotations

import os
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
from api.services import narrator_erasure as _ne  # noqa: E402


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self._orig_env = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = str(self.root)
        self.addCleanup(self._restore_env)

        fd = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        fd.close()
        self.db_path = Path(fd.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()
        self.addCleanup(self._restore_db)

        self.pid = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        con.execute("INSERT INTO people (id, display_name, created_at, updated_at)"
                    " VALUES (?,?,?,?)",
                    (self.pid, "Synthetic N", "2026-08-20", "2026-08-20"))
        con.commit()
        con.close()

    def _restore_env(self):
        if self._orig_env is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self._orig_env

    def _restore_db(self):
        _db.DB_PATH = self._orig_db
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def _seed(self, parts, name="transcript.txt", body="narrator speech"):
        d = self.root.joinpath(*parts, self.pid)
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(body, encoding="utf-8")
        return d / name


class TheDeleteActuallyErasesTests(_Base):

    def test_the_transcript_and_the_captured_story_are_removed(self):
        t = self._seed(("memory", "archive", "people"),
                       body="the Wabash River in Terre Haute")
        s = self._seed(("stories-captured",))
        out = _db.hard_delete_person(self.pid, requested_by="test")
        self.assertEqual(out["status"], "hard_deleted")
        self.assertTrue(out["erasure_complete"])
        self.assertFalse(t.exists(), "the narrator's transcript survived")
        self.assertFalse(s.exists(), "the captured story survived")
        self.assertEqual(_ne.person_file_residue(self.pid, root=self.root), [])

    def test_the_person_row_is_still_gone(self):
        self._seed(("memory", "archive", "people"))
        _db.hard_delete_person(self.pid, requested_by="test")
        self.assertIsNone(_db.get_person(self.pid))

    def test_a_narrator_with_no_files_is_a_clean_complete_delete(self):
        out = _db.hard_delete_person(self.pid, requested_by="test")
        self.assertTrue(out["erasure_complete"])
        self.assertEqual(out["files_removed"], 0)


class TheResultIsStructuredTests(_Base):

    def test_every_required_field_is_present(self):
        self._seed(("memory", "archive", "people"))
        out = _db.hard_delete_person(self.pid, requested_by="test")
        for key in ("database_rows_removed", "files_removed",
                    "directories_removed", "intentionally_retained",
                    "residue", "erasure_complete", "filesystem"):
            with self.subTest(key=key):
                self.assertIn(key, out)

    def test_rows_removed_are_reported_by_table(self):
        out = _db.hard_delete_person(self.pid, requested_by="test")
        rows = out["database_rows_removed"]
        self.assertIsInstance(rows, dict)
        for t in ("profiles", "story_candidates", "turn_extraction_ledger"):
            self.assertIn(t, rows)

    def test_the_audit_record_is_named_as_intentionally_retained(self):
        """It really does survive, so it has to be stated.

        Leaving it unmentioned is how "complete" quietly stops meaning
        "nothing of this person remains".
        """
        out = _db.hard_delete_person(self.pid, requested_by="test")
        kept = {r["record"] for r in out["intentionally_retained"]}
        self.assertIn("narrator_delete_audit", kept)
        audit = [r for r in out["intentionally_retained"]
                 if r["record"] == "narrator_delete_audit"][0]
        self.assertIn("no narrator speech", audit["reason"])
        # …and it is genuinely there.
        con = sqlite3.connect(str(self.db_path))
        n = con.execute("SELECT COUNT(*) FROM narrator_delete_audit "
                        "WHERE person_id=?", (self.pid,)).fetchone()[0]
        con.close()
        self.assertGreaterEqual(n, 1)

    def test_media_is_named_when_it_exists(self):
        self._seed(("media",), name="upload.jpg")
        out = _db.hard_delete_person(self.pid, requested_by="test")
        kept = {r["record"] for r in out["intentionally_retained"]}
        self.assertIn("media_uploads", kept)
        self.assertFalse(out["erasure_complete"],
                         "narrator uploads on disk is not a complete erasure")


class APartialErasureIsNeverReportedAsCompleteTests(_Base):
    """The defect, stated as a test.

    The live acceptance received 200 `{"status": "hard_deleted"}` with
    eight files still on disk. Whatever else changes, that combination
    must never be producible again.
    """

    def _break_erasure(self):
        import shutil as _shutil
        real = _shutil.rmtree
        _ne.shutil.rmtree = lambda *a, **kw: (_ for _ in ()).throw(
            OSError("locked"))
        self.addCleanup(setattr, _ne.shutil, "rmtree", real)

    def test_a_failed_removal_downgrades_the_status(self):
        self._seed(("memory", "archive", "people"))
        self._break_erasure()
        out = _db.hard_delete_person(self.pid, requested_by="test")
        self.assertEqual(out["status"], "hard_deleted_partial")
        self.assertFalse(out["erasure_complete"])
        self.assertTrue(out["residue"] or out["filesystem"]["failed"])

    def test_the_rows_are_still_deleted(self):
        """A filesystem failure must not roll the database back.

        The rows really are gone by then; claiming otherwise would be a
        second untruth on top of the first.
        """
        self._seed(("memory", "archive", "people"))
        self._break_erasure()
        _db.hard_delete_person(self.pid, requested_by="test")
        self.assertIsNone(_db.get_person(self.pid))

    def test_the_route_answers_207_not_200(self):
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception:
            self.skipTest("fastapi not installed in this environment")
        from api.routers import people as _people
        app = FastAPI()
        app.include_router(_people.router)
        client = TestClient(app)

        self._seed(("memory", "archive", "people"))
        self._break_erasure()
        r = client.delete("/api/people/%s?mode=hard" % self.pid)
        self.assertEqual(r.status_code, 207,
                         "a partial deletion answered as though complete")
        body = r.json()
        self.assertFalse(body["erasure_complete"])
        self.assertEqual(body["status"], "hard_deleted_partial")

    def test_a_complete_delete_still_answers_200(self):
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception:
            self.skipTest("fastapi not installed in this environment")
        from api.routers import people as _people
        app = FastAPI()
        app.include_router(_people.router)
        client = TestClient(app)

        self._seed(("stories-captured",))
        r = client.delete("/api/people/%s?mode=hard" % self.pid)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["erasure_complete"])

    def test_the_retry_completes_and_reports_complete(self):
        import shutil as _shutil
        f = self._seed(("memory", "archive", "people"))
        real = _shutil.rmtree
        _ne.shutil.rmtree = lambda *a, **kw: (_ for _ in ()).throw(
            OSError("locked"))
        first = _db.hard_delete_person(self.pid, requested_by="test")
        self.assertFalse(first["erasure_complete"])
        _ne.shutil.rmtree = real
        # The person row is gone, so the retry is the erasure service
        # directly -- which is exactly why it is idempotent and
        # separately callable.
        again = _ne.erase_person_files(self.pid, root=self.root)
        self.assertTrue(again.ok)
        self.assertFalse(f.exists())
        self.assertEqual(_ne.person_file_residue(self.pid, root=self.root), [])
