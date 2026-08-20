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
        # EXTENDED 2026-08-20. `database_rows_removed` did not
        # distinguish deleted from detached and counted rows that
        # survived with a null owner as removals; `residue` collapsed
        # two different questions. The report now names each action
        # separately.
        for key in ("database_rows_deleted", "database_rows_detached",
                    "files_removed", "paths_removed",
                    "intentionally_retained", "historical_residue",
                    "failed_targets", "retry_available",
                    "active_data_erased", "historical_residue_present",
                    "erasure_complete", "filesystem"):
            with self.subTest(key=key):
                self.assertIn(key, out)

    def test_rows_removed_are_reported_by_table(self):
        out = _db.hard_delete_person(self.pid, requested_by="test")
        rows = out["database_rows_deleted"]
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

    def test_media_files_rows_and_attachments_all_go(self):
        """REVERSED 2026-08-20 by Chris's ruling. This asserted media
        was RETAINED and that its presence made the erasure
        incomplete. `ON DELETE SET NULL` stays as a database fallback,
        but a confirmed hard erasure must not leave identifiable
        photographs as ownerless rows."""
        f = self._seed(("media",), name="upload.jpg")
        con = sqlite3.connect(str(self.db_path))
        con.execute("INSERT INTO media (id, person_id, kind, filename, mime,"
                    " bytes, sha256, created_at) VALUES (?,?,?,?,?,?,?,?)",
                    ("m1", self.pid, "image", "upload.jpg", "image/jpeg",
                     4, "abc", "2026-08-20"))
        con.execute("INSERT INTO media_attachments (id, media_id, entity_type,"
                    " entity_id, person_id, created_at) VALUES (?,?,?,?,?,?)",
                    ("a1", "m1", "memoir_section", "sec1", self.pid,
                     "2026-08-20"))
        con.commit()
        con.close()

        out = _db.hard_delete_person(self.pid, requested_by="test")
        self.assertFalse(f.exists(), "the photograph survived")
        self.assertEqual(out["database_rows_deleted"]["media"], 1)
        self.assertEqual(out["database_rows_deleted"]["media_attachments"], 1)
        con = sqlite3.connect(str(self.db_path))
        self.assertEqual(
            con.execute("SELECT COUNT(*) FROM media").fetchone()[0], 0,
            "an ownerless photograph row outlived the narrator")
        self.assertEqual(
            con.execute("SELECT COUNT(*) FROM media_attachments").fetchone()[0],
            0)
        con.close()
        self.assertEqual(out["database_rows_detached"], [],
                         "nothing should be merely detached on a hard delete")
        self.assertTrue(out["erasure_complete"])


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
        self.assertTrue(out["failed_targets"])
        self.assertTrue(out["retry_available"])

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


# ── Retry is a PRODUCT capability, not a service one ────────────────────

class APartialDeletionIsRetryableThroughTheApiTests(_Base):
    """The gap review found. The service was idempotent all along; the
    product could not reach it. After the first attempt the `people`
    row is gone, so repeating DELETE answered 404 while the narrator's
    transcripts sat on disk with no route back to them.
    """

    def _client(self):
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception:
            self.skipTest("fastapi not installed in this environment")
        from api.routers import people as _people
        app = FastAPI()
        app.include_router(_people.router)
        return TestClient(app)

    def _fail_once(self):
        import shutil as _shutil
        real = _shutil.rmtree
        state = {"boom": True}

        def _flaky(path, *a, **kw):
            if state["boom"]:
                raise OSError("locked")
            return real(path, *a, **kw)
        _ne.shutil.rmtree = _flaky
        self.addCleanup(setattr, _ne.shutil, "rmtree", real)
        return state

    def test_the_plan_is_saved_before_the_rows_are_deleted(self):
        self._seed(("memory", "archive", "people"))
        self._fail_once()
        _db.hard_delete_person(self.pid, requested_by="test")
        job = _db.erasure_job_get(self.pid)
        self.assertIsNotNone(job, "no saved plan; a retry has nothing to run")
        self.assertEqual(job["status"], "partial")
        self.assertTrue(job["plan"])

    def test_the_dedicated_retry_endpoint_finishes_the_job(self):
        f = self._seed(("memory", "archive", "people"))
        state = self._fail_once()
        client = self._client()
        first = client.delete("/api/people/%s?mode=hard" % self.pid)
        self.assertEqual(first.status_code, 207)
        self.assertTrue(f.exists(), "precondition: the file survived")

        state["boom"] = False
        r = client.post("/api/people/%s/erase-retry" % self.pid)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["erasure_complete"])
        self.assertFalse(f.exists(), "the retry did not remove the file")

    def test_repeating_the_delete_also_executes_the_saved_plan(self):
        """Not 404. The operator's instinct is to press delete again,
        and answering "not found" while the files are still there is
        how a partial deletion becomes permanent."""
        f = self._seed(("stories-captured",))
        state = self._fail_once()
        client = self._client()
        client.delete("/api/people/%s?mode=hard" % self.pid)
        state["boom"] = False
        again = client.delete("/api/people/%s?mode=hard" % self.pid)
        self.assertEqual(again.status_code, 200, again.text)
        self.assertTrue(again.json()["erasure_complete"])
        self.assertFalse(f.exists())

    def test_a_second_successful_retry_is_idempotent(self):
        self._seed(("stories-captured",))
        state = self._fail_once()
        client = self._client()
        client.delete("/api/people/%s?mode=hard" % self.pid)
        state["boom"] = False
        one = client.post("/api/people/%s/erase-retry" % self.pid).json()
        two = client.post("/api/people/%s/erase-retry" % self.pid).json()
        self.assertTrue(one["erasure_complete"])
        self.assertTrue(two["erasure_complete"], "a repeat retry reported failure")
        self.assertEqual(two["files_removed"], 0, "it removed something twice")

    def test_retry_for_an_unknown_person_is_404(self):
        client = self._client()
        r = client.post("/api/people/%s/erase-retry" % uuid.uuid4())
        self.assertEqual(r.status_code, 404)

    def test_a_crash_between_the_phases_leaves_a_pending_job(self):
        """`pending` is written BEFORE the database phase, so a process
        that dies between the two is recoverable rather than silent."""
        self._seed(("memory", "archive", "people"))
        plan = _ne.build_plan(self.pid)
        _db._erasure_job_upsert(self.pid, "Synthetic N", plan, "pending",
                                requested_by="test")
        job = _db.erasure_job_get(self.pid)
        self.assertEqual(job["status"], "pending")
        self.assertTrue(job["plan"])
        out = _db.retry_person_erasure(self.pid, requested_by="test")
        self.assertTrue(out["erasure_complete"])
        self.assertEqual(_db.erasure_job_get(self.pid)["status"], "complete")


class TheAuditRecordsTheRealOutcomeTests(_Base):
    """It used to be committed as `success` before a single file was
    touched, so a failed erasure still left a successful hard-delete
    record in the one place an operator would look."""

    def _audit(self):
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT result, error_detail FROM narrator_delete_audit "
            "WHERE person_id=? ORDER BY ts DESC LIMIT 1", (self.pid,)).fetchone()
        con.close()
        return dict(row) if row else None

    def test_a_clean_delete_records_success(self):
        self._seed(("stories-captured",))
        _db.hard_delete_person(self.pid, requested_by="test")
        self.assertEqual(self._audit()["result"], "success")

    def test_a_failed_erasure_records_partial(self):
        import shutil as _shutil
        self._seed(("memory", "archive", "people"))
        real = _shutil.rmtree
        _ne.shutil.rmtree = lambda *a, **kw: (_ for _ in ()).throw(
            OSError("locked"))
        self.addCleanup(setattr, _ne.shutil, "rmtree", real)
        _db.hard_delete_person(self.pid, requested_by="test")
        audit = self._audit()
        self.assertEqual(audit["result"], "partial",
                         "a partial erasure left a SUCCESSFUL delete record")
        self.assertIn("memory/archive/people", audit["error_detail"] or "")


# ── The DB-derived stores ───────────────────────────────────────────────

class StoresNamedByRowsThatCascadeAwayTests(_Base):
    """Trip sources, import staging and legacy transcript exports are
    named by rows that vanish with the person. If the plan were built
    after the delete, their names would be gone -- which is why the
    plan is built first and persisted."""

    def _trip_with_source(self):
        con = sqlite3.connect(str(self.db_path))
        con.execute("INSERT INTO trips (id, person_id, title, created_at,"
                    " updated_at) VALUES (?,?,?,?,?)",
                    ("trip1", self.pid, "Germany", "2026-08-20", "2026-08-20"))
        con.execute("INSERT INTO trip_sources (id, trip_id, source_type,"
                    " created_at, updated_at) VALUES (?,?,?,?,?)",
                    ("src1", "trip1", "ticket", "2026-08-20", "2026-08-20"))
        con.commit()
        con.close()
        d = self.root / "trip_sources" / "src1"
        d.mkdir(parents=True)
        f = d / "ticket.pdf"
        f.write_text("boarding pass", encoding="utf-8")
        return f

    def _import_batch(self):
        con = sqlite3.connect(str(self.db_path))
        con.execute("INSERT INTO import_batch (id, person_id, source,"
                    " created_at, updated_at) VALUES (?,?,?,?,?)",
                    ("batch1", self.pid, "local_upload", "2026-08-20",
                     "2026-08-20"))
        con.commit()
        con.close()
        a = self.root / "import_staging" / "batch1"
        a.mkdir(parents=True)
        (a / "original.jpg").write_text("bytes", encoding="utf-8")
        b = self.root / "import_staging" / ".incoming" / "batch1"
        b.mkdir(parents=True)
        (b / "partial.jpg").write_text("bytes", encoding="utf-8")
        return a / "original.jpg", b / "partial.jpg"

    def _legacy_transcript(self):
        conv = "switch_abc123"
        con = sqlite3.connect(str(self.db_path))
        con.execute("INSERT INTO sessions (conv_id, person_id, updated_at)"
                    " VALUES (?,?,?)", (conv, self.pid, "2026-08-20"))
        con.commit()
        con.close()
        d = self.root / "memory" / "agents" / "bot_tests"
        d.mkdir(parents=True)
        f = d / (conv + ".txt")
        f.write_text("narrator: I was born in Terre Haute", encoding="utf-8")
        return f

    def test_trip_source_documents_are_removed(self):
        f = self._trip_with_source()
        _db.hard_delete_person(self.pid, requested_by="test")
        self.assertFalse(f.exists(), "an uploaded ticket survived")

    def test_import_staging_and_incoming_are_removed(self):
        a, b = self._import_batch()
        _db.hard_delete_person(self.pid, requested_by="test")
        self.assertFalse(a.exists())
        self.assertFalse(b.exists(), "the .incoming scratch copy survived")

    def test_legacy_agent_transcripts_are_removed(self):
        f = self._legacy_transcript()
        _db.hard_delete_person(self.pid, requested_by="test")
        self.assertFalse(f.exists(), "a legacy transcript export survived")

    def test_another_trips_sources_are_untouched(self):
        keep_dir = self.root / "trip_sources" / "src-other"
        keep_dir.mkdir(parents=True)
        keep = keep_dir / "other.pdf"
        keep.write_text("someone else's", encoding="utf-8")
        self._trip_with_source()
        _db.hard_delete_person(self.pid, requested_by="test")
        self.assertTrue(keep.exists())

    def test_the_plan_survives_the_rows_it_was_derived_from(self):
        """The point of planning first, stated as a test."""
        f = self._trip_with_source()
        import shutil as _shutil
        real = _shutil.rmtree
        _ne.shutil.rmtree = lambda *a, **kw: (_ for _ in ()).throw(
            OSError("locked"))
        _db.hard_delete_person(self.pid, requested_by="test")
        # The trips row is gone now; only the saved plan knows `src1`.
        con = sqlite3.connect(str(self.db_path))
        self.assertEqual(
            con.execute("SELECT COUNT(*) FROM trips").fetchone()[0], 0)
        con.close()
        _ne.shutil.rmtree = real
        self.addCleanup(setattr, _ne.shutil, "rmtree", real)
        out = _db.retry_person_erasure(self.pid, requested_by="test")
        self.assertTrue(out["erasure_complete"])
        self.assertFalse(f.exists(),
                         "the retry could not find a target whose database "
                         "row had already cascaded away")


# ── The three properties a first mutation pass found UNPROVEN ───────────

class WrittenBeforeTheDatabasePhaseTests(_Base):
    """ADDED after mutation testing, 2026-08-20.

    Deleting the pre-commit `_erasure_job_upsert(... "pending")` left
    every test green, because `_run_erasure_phase` writes the job again
    afterwards -- so ordinary success and ordinary failure both look
    identical either way. What the early write actually buys is
    CRASH RECOVERY, and nothing was asserting it.
    """

    def test_the_plan_survives_a_rolled_back_delete(self):
        """The job is written on its OWN connection, so a delete that
        rolls back still leaves the plan. If it shared the
        transaction, a rollback would take the plan with it and the
        files would be unreachable."""
        self._seed(("memory", "archive", "people"))
        orig = _db._extended_person_scoped_delete
        _db._extended_person_scoped_delete = lambda *a, **kw: (
            _ for _ in ()).throw(RuntimeError("boom mid-transaction"))
        self.addCleanup(setattr, _db, "_extended_person_scoped_delete", orig)

        out = _db.hard_delete_person(self.pid, requested_by="test")
        self.assertEqual(out.get("error"), "rollback")
        # The person is still here -- and so is the plan.
        self.assertIsNotNone(_db.get_person(self.pid))
        job = _db.erasure_job_get(self.pid)
        self.assertIsNotNone(job, "the plan did not survive the rollback")
        self.assertEqual(job["status"], "pending")

    def test_a_crash_after_commit_leaves_pending_not_success(self):
        """The audit result must not read `success` before a file has
        been touched. A process that dies between the database commit
        and the filesystem phase leaves a `pending` record, which is a
        recoverable job; `success` would be a claim nobody checked."""
        self._seed(("memory", "archive", "people"))
        orig = _db._run_erasure_phase
        _db._run_erasure_phase = lambda *a, **kw: (_ for _ in ()).throw(
            RuntimeError("process died"))
        self.addCleanup(setattr, _db, "_run_erasure_phase", orig)
        with self.assertRaises(RuntimeError):
            _db.hard_delete_person(self.pid, requested_by="test")

        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT result FROM narrator_delete_audit "
                          "WHERE person_id=? ORDER BY ts DESC LIMIT 1",
                          (self.pid,)).fetchone()
        con.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["result"], "pending",
                         "the audit claimed success before erasure ran")
        self.assertEqual(_db.erasure_job_get(self.pid)["status"], "pending")


class DetachedRowsAreNotCountedAsDeletionsTests(_Base):
    """ADDED after mutation testing, 2026-08-20. Passing the raw
    pre-delete inventory straight through kept every test green,
    because no fixture had a row that would be DETACHED rather than
    deleted. `media_owned` is exactly that key -- the inventory's count
    of rows the FK cascade would null -- and reporting it as removed is
    how the response came to overstate the erasure by precisely the
    rows that survived it."""

    def test_the_inventory_key_for_detached_rows_never_appears(self):
        con = sqlite3.connect(str(self.db_path))
        con.execute("INSERT INTO media (id, person_id, kind, filename, mime,"
                    " bytes, sha256, created_at) VALUES (?,?,?,?,?,?,?,?)",
                    ("m9", self.pid, "image", "x.jpg", "image/jpeg", 1, "z",
                     "2026-08-20"))
        con.commit()
        con.close()
        inv = _db.person_delete_inventory(self.pid)
        self.assertEqual(inv["counts"].get("media_owned"), 1,
                         "precondition: the inventory counts it")

        out = _db.hard_delete_person(self.pid, requested_by="test")
        rows = out["database_rows_deleted"]
        self.assertNotIn("media_owned", rows,
                         "an inventory key for rows the cascade would DETACH "
                         "was reported as a deletion")
        # …and the real deletion count is the one the delete performed.
        self.assertEqual(rows["media"], 1)
