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

    def test_a_second_successful_retry_is_an_idempotent_READ(self):
        """REPOINTED 2026-08-20. This asserted the second retry reported
        `files_removed == 0` -- i.e. that it RE-RAN the plan and found
        nothing. A completed job is now READ BACK instead, so the same
        result is returned rather than the filesystem walked again.
        Idempotence is proven where it matters: on disk.
        """
        f = self._seed(("stories-captured",))
        state = self._fail_once()
        client = self._client()
        client.delete("/api/people/%s?mode=hard" % self.pid)
        state["boom"] = False
        one = client.post("/api/people/%s/erase-retry" % self.pid).json()
        self.assertTrue(one["erasure_complete"])
        self.assertFalse(f.exists())

        r = client.post("/api/people/%s/erase-retry" % self.pid)
        two = r.json()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(two["erasure_complete"])
        self.assertTrue(two.get("already_completed"),
                        "a completed deletion was re-run instead of read back")
        self.assertEqual(two["database_rows_deleted"], {},
                         "a read-back must not claim to have deleted rows")
        self.assertFalse(f.exists())

    def test_retry_for_an_unknown_person_is_404(self):
        client = self._client()
        r = client.post("/api/people/%s/erase-retry" % uuid.uuid4())
        self.assertEqual(r.status_code, 404)

    def test_a_crash_between_the_phases_leaves_a_pending_job(self):
        """`pending` is written BEFORE the database phase, so a process
        that dies between the two is recoverable rather than silent."""
        self._seed(("memory", "archive", "people"))
        plan = _ne.build_plan(self.pid)
        # The ROOT is written with the plan (2026-08-20). Without it a
        # retry refuses, because the plan's relative paths exist under
        # every root this deployment has ever had.
        _db._erasure_job_upsert(self.pid, "Synthetic N", plan, "pending",
                                requested_by="test",
                                data_root=str(self.root))
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


# ── Fail closed BEFORE authority is lost ────────────────────────────────

class NothingIsDeletedWithoutARetryPlanTests(_Base):
    """Review, 2026-08-20: several failure paths could delete database
    authority and leave no reliable plan.

    Both steps -- building the plan and saving it -- used to log and
    continue. A plan-building failure substituted `plan=[]`; a
    job-write failure was swallowed. Either way the rows were destroyed
    and there was nothing left to retry with, so the files became
    permanently unreachable. Refusing costs a second attempt; that is
    the cheaper mistake by a wide margin.
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

    def test_a_failed_plan_SAVE_leaves_everything_untouched(self):
        f = self._seed(("memory", "archive", "people"))
        orig = _db._erasure_job_upsert

        def _boom(*a, **kw):
            if kw.get("required"):
                raise sqlite3.OperationalError("disk I/O error")
            return orig(*a, **kw)
        _db._erasure_job_upsert = _boom
        self.addCleanup(setattr, _db, "_erasure_job_upsert", orig)

        out = _db.hard_delete_person(self.pid, requested_by="test")
        self.assertEqual(out.get("error"), "plan_unavailable")
        self.assertIsNotNone(_db.get_person(self.pid), "the person was deleted")
        self.assertTrue(f.exists(), "files were removed without a saved plan")
        con = sqlite3.connect(str(self.db_path))
        self.assertEqual(
            con.execute("SELECT COUNT(*) FROM people WHERE id=?",
                        (self.pid,)).fetchone()[0], 1)
        con.close()

    def test_a_failed_plan_BUILD_on_an_installed_lane_refuses(self):
        """A MISSING table means the feature was never installed and is
        tolerated. A table that exists and will not answer is not."""
        f = self._seed(("stories-captured",))
        from api.services import narrator_erasure as _svc
        orig = _svc.build_plan
        _svc.build_plan = lambda pid, con=None: (_ for _ in ()).throw(
            _svc.PlanIncomplete("cannot plan the trip_sources lane"))
        self.addCleanup(setattr, _svc, "build_plan", orig)

        out = _db.hard_delete_person(self.pid, requested_by="test")
        self.assertEqual(out.get("error"), "plan_unavailable")
        self.assertIn("built", out["detail"])
        self.assertIsNotNone(_db.get_person(self.pid))
        self.assertTrue(f.exists())

    def test_a_missing_optional_table_is_tolerated(self):
        # REPOINTED 2026-08-20: BOTH tables of the joined lane. Dropping
        # only one is now a PARTIALLY installed lane and refuses -- the
        # surviving table can hold real rows whose directories the plan
        # would never name. "Never installed" means neither is there.
        con = sqlite3.connect(str(self.db_path))
        con.execute("DROP TABLE IF EXISTS trip_sources;")
        con.execute("DROP TABLE IF EXISTS trips;")
        con.commit()
        con.close()
        # The delete path also touches `trips` in its own cascade
        # bookkeeping, so this asserts the PLAN, which is where lane
        # installation is decided. A live delete on a schema without
        # trips is a different (and pre-existing) concern.
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        plan = _ne.build_plan(self.pid, con)
        con.close()
        self.assertTrue(plan, "a feature never installed blocked the plan")
        self.assertNotIn("trip_sources", [e["target"] for e in plan])

    def test_the_route_answers_503_and_deletes_nothing(self):
        f = self._seed(("memory", "archive", "people"))
        from api.services import narrator_erasure as _svc
        orig = _svc.build_plan
        _svc.build_plan = lambda pid, con=None: (_ for _ in ()).throw(
            _svc.PlanIncomplete("lane unreadable"))
        self.addCleanup(setattr, _svc, "build_plan", orig)
        r = self._client().delete("/api/people/%s?mode=hard" % self.pid)
        self.assertEqual(r.status_code, 503)
        self.assertIsNotNone(_db.get_person(self.pid))
        self.assertTrue(f.exists())


class AMediaFailureRollsBackTheWholeDeletionTests(_Base):
    """It used to catch `sqlite3.Error` and continue, which could leave
    ownerless media rows pointing at files the filesystem phase then
    removed -- a row asserting a photograph exists, and no photograph.
    """

    def test_the_person_and_every_row_survive(self):
        f = self._seed(("media",), name="upload.jpg")
        con = sqlite3.connect(str(self.db_path))
        con.execute("INSERT INTO media (id, person_id, kind, filename, mime,"
                    " bytes, sha256, created_at) VALUES (?,?,?,?,?,?,?,?)",
                    ("m1", self.pid, "image", "upload.jpg", "image/jpeg", 4,
                     "abc", "2026-08-20"))
        con.commit()
        con.close()

        orig = _db._hard_delete_media
        _db._hard_delete_media = lambda c, p: (_ for _ in ()).throw(
            sqlite3.OperationalError("database is locked"))
        self.addCleanup(setattr, _db, "_hard_delete_media", orig)

        out = _db.hard_delete_person(self.pid, requested_by="test")
        self.assertEqual(out.get("error"), "rollback")
        self.assertIsNotNone(_db.get_person(self.pid))
        con = sqlite3.connect(str(self.db_path))
        self.assertEqual(
            con.execute("SELECT COUNT(*) FROM media WHERE person_id=?",
                        (self.pid,)).fetchone()[0], 1,
            "the media row was left in an in-between state")
        con.close()
        self.assertTrue(f.exists(), "the file went while its row survived")


# ── Naming, counts and status semantics ─────────────────────────────────

class LegacyTranscriptsAreNamedLikeTheWriterNamesThemTests(_Base):
    """The writer slugs the conversation id and picks ONE subfolder.
    The plan used the unslugged id and scheduled all three, so a
    conversation whose id needed slugging kept its real file through a
    "complete" erasure -- and two of the three scheduled paths were
    never this narrator's at all."""

    def test_an_id_needing_a_slug_removes_its_ACTUAL_file(self):
        from api.services.chat_memory_paths import slug, subfolder_for
        conv = "switch:weird/id?v=2"
        con = sqlite3.connect(str(self.db_path))
        con.execute("INSERT INTO sessions (conv_id, person_id, updated_at)"
                    " VALUES (?,?,?)", (conv, self.pid, "2026-08-20"))
        con.commit()
        con.close()

        d = self.root / "memory" / "agents" / subfolder_for(conv)
        d.mkdir(parents=True)
        real = d / (slug(conv) + ".txt")
        real.write_text("narrator: I was born in Terre Haute", encoding="utf-8")
        # A same-named file in the OTHER subfolder, which is not this
        # narrator's and must survive.
        other = self.root / "memory" / "agents" / "interviews"
        other.mkdir(parents=True, exist_ok=True)
        bystander = other / (slug(conv) + ".txt")
        bystander.write_text("somebody else's export", encoding="utf-8")

        _db.hard_delete_person(self.pid, requested_by="test")
        self.assertFalse(real.exists(), "the real export survived")
        self.assertTrue(bystander.exists(),
                        "a file in a subfolder the writer never uses was "
                        "removed")

    def test_the_plan_never_schedules_the_unslugged_name(self):
        conv = "switch:weird/id?v=2"
        con = sqlite3.connect(str(self.db_path))
        con.execute("INSERT INTO sessions (conv_id, person_id, updated_at)"
                    " VALUES (?,?,?)", (conv, self.pid, "2026-08-20"))
        con.commit()
        con.close()
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        plan = _ne.build_plan(self.pid, con)
        con.close()
        names = [e["parts"][-1] for e in plan
                 if e["target"] == "agent_transcripts"]
        self.assertTrue(names)
        for n in names:
            self.assertNotIn("/", n)
            self.assertNotIn(":", n)
        subs = {e["parts"][-2] for e in plan
                if e["target"] == "agent_transcripts"}
        self.assertEqual(subs, {"bot_tests"},
                         "the plan scheduled a subfolder the writer never "
                         "uses for this conversation")


class TheDeletedCountsAreDatabaseTablesOnlyTests(_Base):

    def test_kawa_segments_is_not_reported_as_a_database_table(self):
        """It is a count of JSON FILES on disk. Reporting it under
        `database_rows_deleted` mixed a filesystem number into a
        database answer.

        Driven through the reporting function with a fabricated
        inventory rather than through a live delete: `db.DATA_DIR` is
        bound at import time, so `person_delete_inventory` reads the
        process's original root and would report 0 here whatever the
        test wrote. Fabricating the inventory tests the exclusion
        itself, which is the property.
        """
        out = _db._run_erasure_phase(
            self.pid, "Synthetic N", [],
            rows_deleted={"profiles": 1, "kawa_segments": 7,
                          "media_owned": 3, "story_candidates": 2},
            media_deleted={"media": 0, "media_attachments": 0})
        rows = out["database_rows_deleted"]
        self.assertNotIn("kawa_segments", rows,
                         "a count of files on disk was reported as deleted "
                         "database rows")
        self.assertNotIn("media_owned", rows)
        self.assertEqual(rows["profiles"], 1)
        self.assertEqual(rows["story_candidates"], 2)

    def test_the_kawa_files_still_go_and_are_reported_as_filesystem_work(self):
        seg = self.root / "kawa" / "people" / self.pid / "segments"
        seg.mkdir(parents=True)
        (seg / "a.json").write_text("{}", encoding="utf-8")
        out = _db.hard_delete_person(self.pid, requested_by="test")
        self.assertFalse(seg.exists())
        self.assertIn("kawa_segments",
                      [r["target"] for r in out["filesystem"]["removed_detail"]])
        self.assertNotIn("kawa_segments", out["database_rows_deleted"])


class ThreeOutcomesAndTheRightHttpCodeTests(_Base):

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

    def test_a_clean_delete_is_200_hard_deleted(self):
        self._seed(("stories-captured",))
        r = self._client().delete("/api/people/%s?mode=hard" % self.pid)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "hard_deleted")

    def test_a_backup_is_200_with_its_own_status(self):
        """Historical residue is NOT an actionable retry failure.
        Keying the code on `erasure_complete` made a backup produce a
        permanent 207 on a deletion where nothing had failed."""
        (self.root / "backups").mkdir()
        (self.root / "backups" / "snap.sqlite3").write_text("x", encoding="utf-8")
        self._seed(("stories-captured",))
        r = self._client().delete("/api/people/%s?mode=hard" % self.pid)
        body = r.json()
        self.assertEqual(r.status_code, 200,
                         "a shared backup produced an actionable error code")
        self.assertEqual(body["status"], "hard_deleted_historical_residue")
        self.assertTrue(body["active_data_erased"])
        self.assertTrue(body["historical_residue_present"])
        self.assertFalse(body["erasure_complete"])
        self.assertFalse(body["retry_available"])
        self.assertTrue((self.root / "backups" / "snap.sqlite3").exists())

    def test_an_active_failure_is_207_with_retry_available(self):
        import shutil as _shutil
        self._seed(("memory", "archive", "people"))
        real = _shutil.rmtree
        _ne.shutil.rmtree = lambda *a, **kw: (_ for _ in ()).throw(
            OSError("locked"))
        self.addCleanup(setattr, _ne.shutil, "rmtree", real)
        r = self._client().delete("/api/people/%s?mode=hard" % self.pid)
        self.assertEqual(r.status_code, 207)
        self.assertEqual(r.json()["status"], "hard_deleted_partial")
        self.assertTrue(r.json()["retry_available"])

    def test_repeating_a_completed_delete_reads_the_stored_job(self):
        (self.root / "backups").mkdir()
        (self.root / "backups" / "snap.sqlite3").write_text("x", encoding="utf-8")
        self._seed(("stories-captured",))
        client = self._client()
        client.delete("/api/people/%s?mode=hard" % self.pid)
        again = client.delete("/api/people/%s?mode=hard" % self.pid)
        self.assertEqual(again.status_code, 200,
                         "a finished deletion kept re-running because a "
                         "backup held erasure_complete false")
        self.assertTrue(again.json().get("already_completed"))


class TheRetrySucceedsInTheAuditTooTests(_Base):

    def _audit_trail(self):
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT action, result FROM narrator_delete_audit "
            "WHERE person_id=? ORDER BY ts", (self.pid,)).fetchall()
        con.close()
        return [(r["action"], r["result"]) for r in rows]

    def test_the_trail_reads_partial_then_completed(self):
        """The first attempt left `partial` and a successful retry used
        to leave it standing -- so the one place an operator checks
        said the deletion had failed after it had been finished."""
        import shutil as _shutil
        self._seed(("memory", "archive", "people"))
        real = _shutil.rmtree
        state = {"boom": True}
        _ne.shutil.rmtree = lambda *a, **kw: (
            (_ for _ in ()).throw(OSError("locked")) if state["boom"]
            else real(*a, **kw))
        self.addCleanup(setattr, _ne.shutil, "rmtree", real)

        _db.hard_delete_person(self.pid, requested_by="test")
        self.assertEqual(self._audit_trail(), [("hard_delete", "partial")])

        state["boom"] = False
        out = _db.retry_person_erasure(self.pid, requested_by="test")
        self.assertTrue(out["erasure_complete"])
        self.assertEqual(
            self._audit_trail(),
            [("hard_delete", "partial"), ("hard_delete_retry", "success")],
            "a successful retry left no record that the deletion finished")

    def test_a_failed_retry_records_partial_too(self):
        import shutil as _shutil
        self._seed(("memory", "archive", "people"))
        real = _shutil.rmtree
        _ne.shutil.rmtree = lambda *a, **kw: (_ for _ in ()).throw(
            OSError("locked"))
        self.addCleanup(setattr, _ne.shutil, "rmtree", real)
        _db.hard_delete_person(self.pid, requested_by="test")
        _db.retry_person_erasure(self.pid, requested_by="test")
        self.assertEqual(self._audit_trail(),
                         [("hard_delete", "partial"),
                          ("hard_delete_retry", "partial")])


class TheRequiredPlanWriteRaisesRatherThanLogsTests(_Base):
    """ADDED after mutation testing, 2026-08-20.

    Deleting `if required: raise` from `_erasure_job_upsert` left every
    test green: the fail-closed test replaces the whole function, so it
    proved the CALLER refuses on an exception and never proved the
    function raises one. Without that, a job-write failure is logged
    and the deletion proceeds with no retry plan -- the exact path this
    correction closes.
    """

    def test_a_required_write_propagates_its_failure(self):
        orig = _db.DB_PATH
        _db.DB_PATH = Path(self.tmp.name) / "no" / "such" / "dir" / "x.sqlite3"
        self.addCleanup(setattr, _db, "DB_PATH", orig)
        with self.assertRaises(Exception):
            _db._erasure_job_upsert(self.pid, "N", [{"target": "x",
                                                     "parts": ["a"]}],
                                    "pending", required=True)

    def test_a_best_effort_write_does_not(self):
        """Later writes are bookkeeping on work already done and must
        never break a deletion that succeeded."""
        orig = _db.DB_PATH
        _db.DB_PATH = Path(self.tmp.name) / "no" / "such" / "dir" / "x.sqlite3"
        self.addCleanup(setattr, _db, "DB_PATH", orig)
        _db._erasure_job_upsert(self.pid, "N", [], "complete")  # no raise


# ── A plan belongs to the root it was built for ─────────────────────────

class APlanCannotBeExecutedAgainstAnotherRootTests(_Base):
    """THE DESTRUCTIVE DEFECT REVIEW REPRODUCED, 2026-08-20.

    A saved plan holds RELATIVE paths. A retry used to execute them
    against whatever `DATA_DIR` the process had at that moment -- so a
    plan created for root A, retried under root B, left A intact and
    deleted B. The same narrator id exists under both roots in any
    deployment that has been migrated, restored from a snapshot, or
    pointed at a staging copy, and the retry is exactly the moment
    somebody is likely to be changing the environment.
    """

    def setUp(self):
        super().setUp()
        self.other = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(
            self.other, ignore_errors=True))
        # The SAME narrator id, under a second root.
        d = self.other / "memory" / "archive" / "people" / self.pid
        d.mkdir(parents=True)
        self.b_file = d / "transcript.txt"
        self.b_file.write_text("root B's copy of this narrator",
                               encoding="utf-8")

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

    def test_the_root_is_saved_with_the_plan(self):
        self._seed(("memory", "archive", "people"))
        self._fail_once()
        _db.hard_delete_person(self.pid, requested_by="test")
        job = _db.erasure_job_get(self.pid)
        self.assertEqual(job["data_root"], str(self.root))

    def test_a_retry_under_a_DIFFERENT_root_deletes_nothing(self):
        a_file = self._seed(("memory", "archive", "people"),
                            body="root A's copy")
        b_before = self.b_file.read_bytes()
        state = self._fail_once()
        _db.hard_delete_person(self.pid, requested_by="test")
        self.assertTrue(a_file.exists(), "precondition: A survived the failure")

        # The environment moves. This is the scenario.
        os.environ["DATA_DIR"] = str(self.other)
        state["boom"] = False
        out = _db.retry_person_erasure(self.pid, requested_by="test")

        self.assertTrue(self.b_file.exists(),
                        "the retry deleted the OTHER root's copy")
        self.assertEqual(self.b_file.read_bytes(), b_before)
        # …and A is still erased, because the plan is bound to A.
        self.assertFalse(a_file.exists(),
                         "the retry did not act on the root it planned for")
        self.assertTrue(out["erasure_complete"])

    def test_a_root_that_no_longer_validates_refuses_and_removes_nothing(self):
        a_file = self._seed(("memory", "archive", "people"))
        b_before = self.b_file.read_bytes()
        state = self._fail_once()
        _db.hard_delete_person(self.pid, requested_by="test")

        # The saved root is gone -- an unmounted volume, a moved data
        # directory. There is no second-best root to fall back to.
        import shutil as _shutil
        real = _shutil.rmtree
        state["boom"] = False
        _ne.shutil.rmtree = real
        saved = self.root
        moved = Path(tempfile.mkdtemp()) / "gone"
        _db._erasure_job_upsert(self.pid, "Synthetic N",
                                _db.erasure_job_get(self.pid)["plan"],
                                "partial", data_root=str(moved))

        os.environ["DATA_DIR"] = str(self.other)
        out = _db.retry_person_erasure(self.pid, requested_by="test")
        self.assertEqual(out["status"], "hard_deleted_partial")
        self.assertFalse(out["active_data_erased"])
        self.assertEqual(out["failed_targets"][0]["reason"],
                         "data_root_unconfirmed")
        self.assertTrue(out["retry_available"])
        self.assertTrue(self.b_file.exists(),
                        "a refusal still touched the other root")
        self.assertEqual(self.b_file.read_bytes(), b_before)
        self.assertTrue(a_file.exists(), "a refusal removed something")
        self.assertTrue(saved.exists())

    def test_a_job_with_no_saved_root_refuses_rather_than_guesses(self):
        """Rows written before the column existed. Their paths are true
        of every root this deployment has ever had, so there is nothing
        to infer from."""
        a_file = self._seed(("memory", "archive", "people"))
        state = self._fail_once()
        _db.hard_delete_person(self.pid, requested_by="test")
        con = sqlite3.connect(str(self.db_path))
        con.execute("UPDATE narrator_erasure_jobs SET data_root='' "
                    "WHERE person_id=?", (self.pid,))
        con.commit()
        con.close()

        state["boom"] = False
        out = _db.retry_person_erasure(self.pid, requested_by="test")
        self.assertFalse(out["active_data_erased"])
        self.assertIn("before its data root was recorded",
                      out["failed_targets"][0]["detail"])
        self.assertTrue(a_file.exists())
        self.assertTrue(self.b_file.exists())

    def test_the_route_reports_the_refusal_as_207_with_retry(self):
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
        self._fail_once()
        _db.hard_delete_person(self.pid, requested_by="test")
        con = sqlite3.connect(str(self.db_path))
        con.execute("UPDATE narrator_erasure_jobs SET data_root='' "
                    "WHERE person_id=?", (self.pid,))
        con.commit()
        con.close()

        r = client.post("/api/people/%s/erase-retry" % self.pid)
        self.assertEqual(r.status_code, 207)
        self.assertTrue(r.json()["retry_available"])

    def test_a_root_that_now_RESOLVES_ELSEWHERE_refuses(self):
        """ADDED after mutation testing, 2026-08-20.

        Deleting the `validated != saved_root` check left every test
        green, because the only existing case used a root that had
        VANISHED -- which `validate_root` catches first. The branch
        this check exists for is different and quieter: the path still
        exists and now points somewhere else. A moved mount, a
        re-pointed symlink. Same string, different directory, and the
        plan's relative paths would be executed there.
        """
        a_file = self._seed(("memory", "archive", "people"))
        b_before = self.b_file.read_bytes()
        state = self._fail_once()
        _db.hard_delete_person(self.pid, requested_by="test")

        link = Path(tempfile.mkdtemp()) / "data-root"
        try:
            link.symlink_to(self.other, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable in this environment")
        _db._erasure_job_upsert(self.pid, "Synthetic N",
                                _db.erasure_job_get(self.pid)["plan"],
                                "partial", data_root=str(link))
        import shutil as _shutil
        state["boom"] = False
        _ne.shutil.rmtree = _shutil.rmtree

        out = _db.retry_person_erasure(self.pid, requested_by="test")
        self.assertFalse(out["active_data_erased"])
        self.assertEqual(out["failed_targets"][0]["reason"],
                         "data_root_unconfirmed")
        self.assertIn("resolves to", out["failed_targets"][0]["detail"])
        self.assertTrue(self.b_file.exists(),
                        "the plan was executed against the resolved root")
        self.assertEqual(self.b_file.read_bytes(), b_before)
        self.assertTrue(a_file.exists())
