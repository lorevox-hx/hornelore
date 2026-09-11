"""WO-LOREVOX-PORTABLE-NARRATOR-01 Phase 3 — dry run + Restore v1, proven on synthetic Ada.

Reuses the Phase 2 fixture (`tests.test_narrator_package_export._Fixture`): Ada
with the complete travel domain and Bea beside her in a SOURCE root. Each test
exports Ada, then builds an EMPTY, DISPOSABLE destination root with the
product's own `init_db()` (§17 Phase 3 exit gate) and restores into it.

Restore has one meaning here (§10.1): this narrator as this narrator. Every
assertion below is against the destination database and filesystem after the
real `restore_narrator()`, never against the exporter's own bookkeeping:

  * dry run is READY on an empty root once its installation dependencies exist,
    REFUSED with named reasons for a collision, a missing dependency, a tampered
    package, an unsafe member — and writes nothing either way
  * restore inserts exactly the manifest's rows with ids verbatim, foreign keys
    intact, files at DATA_DIR-relative paths with the manifest's hashes, absolute
    path columns rewritten under the NEW root, the job row `complete`
  * a second restore of the same package is a collision, not an overwrite
  * a failure inside the transaction leaves NO rows, NO files, and a `failed` job
  * Bea is nowhere in the destination

Run:
    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_narrator_package_restore
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from typing import Dict

from tests.test_narrator_package_export import _Fixture, REPO_ROOT  # noqa: F401
from api.services import narrator_data_inventory as inv  # noqa: E402
from api.services import narrator_package as pkg  # noqa: E402


class _RoundTrip(_Fixture):
    """Source fixture from Phase 2 + an empty destination built by init_db()."""

    def setUp(self):
        super().setUp()
        # export Ada from the SOURCE while the api.db module still points there
        self.res = self.export()
        self.zip = self.res.package_path
        # now build the DESTINATION: a fresh root, the product's own schema
        self.dest_root = Path(self._tmp.name) / "dest"
        self.dest_root.mkdir()
        os.environ["DATA_DIR"] = str(self.dest_root)
        os.environ["DB_NAME"] = "dest.sqlite3"
        from api import db as _db
        importlib.reload(_db)
        _db.init_db()
        self.dest_db = Path(_db.DB_PATH)
        self.assertTrue(str(self.dest_db).startswith(str(self.dest_root)))
        # the ONE installation dependency Ada's rows carry (interview_plans) —
        # installation state is the destination's to provide, never the package's (§5-E)
        self.plan_id = next(iter(self.res.manifest["installation_dependencies"]["interview_plans"]))
        self.seed_plan(self.plan_id)

    def seed_plan(self, plan_id: str):
        con = sqlite3.connect(str(self.dest_db))
        try:
            con.execute("INSERT INTO interview_plans (id, title, created_at) VALUES (?, ?, ?)",
                        (plan_id, "plan", "2026-09-10T00:00:00Z"))
            con.commit()
        finally:
            con.close()

    def dest(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.dest_db))
        con.row_factory = sqlite3.Row
        self.addCleanup(con.close)
        return con

    def dry_run(self, path=None):
        return pkg.dry_run_restore(path or self.zip, data_dir=self.dest_root, db_path=self.dest_db)

    def restore(self, path=None):
        return pkg.restore_narrator(path or self.zip, data_dir=self.dest_root, db_path=self.dest_db, requested_by="test")

    def dest_files(self):
        return sorted(str(p.relative_to(self.dest_root)) for p in self.dest_root.rglob("*")
                      if p.is_file() and not p.name.endswith((".sqlite3", "-wal", "-shm", "-journal"))
                      and "/db/" not in ("/" + str(p.relative_to(self.dest_root)).replace("\\", "/")))

    def package_hashes(self) -> Dict[str, str]:
        with zipfile.ZipFile(self.zip) as zf:
            lines = zf.read("manifest-sha256.txt").decode().splitlines()
        return {l.split(maxsplit=1)[1]: l.split(maxsplit=1)[0] for l in lines if l.strip()}


# ══════════════════════════════════════════════════════════════════════

class DryRun(_RoundTrip):

    def test_ready_on_empty_root_and_writes_nothing(self):
        before_files = self.dest_files()
        before_db = self.dest_db.read_bytes()
        rep = self.dry_run()
        self.assertTrue(rep.ready, rep.reasons)
        self.assertEqual(rep.verdict, "RESTORE READY")
        self.assertEqual(rep.records_by_lane, self.res.manifest["record_counts_by_lane"])
        self.assertEqual(rep.files_by_lane, self.res.manifest["file_counts_by_lane"])
        self.assertEqual(rep.collisions, [])
        self.assertEqual(rep.missing_dependencies, [])
        self.assertEqual(self.dest_files(), before_files)
        self.assertEqual(self.dest_db.read_bytes(), before_db)
        # the §13 external person (Bea) is reported as absent here, not refused
        self.assertTrue(any(w["code"] == "external_person_absent_in_destination" for w in rep.warnings), rep.warnings)

    def test_missing_installation_dependency_is_named_and_refuses(self):
        con = sqlite3.connect(str(self.dest_db))
        con.execute("DELETE FROM interview_plans WHERE id=?", (self.plan_id,))
        con.commit()
        con.close()
        rep = self.dry_run()
        self.assertFalse(rep.ready)
        m = [r for r in rep.reasons if r["code"] == "missing_dependency"]
        self.assertEqual(m[0]["table"], "interview_plans")
        self.assertIn(self.plan_id, m[0]["ids"])

    def test_existing_narrator_is_a_collision(self):
        self.restore()
        rep = self.dry_run()
        self.assertFalse(rep.ready)
        kinds = {c["kind"] for c in rep.collisions}
        self.assertIn("narrator_exists", kinds)
        self.assertIn("row_id_exists", kinds)
        self.assertIn("file_exists", kinds)

    def test_existing_destination_file_alone_is_a_collision(self):
        rel = next(m for m in self.package_hashes() if m.startswith("data/files/"))[len("data/files/"):]
        target = self.dest_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"pre-existing")
        rep = self.dry_run()
        self.assertFalse(rep.ready)
        self.assertEqual([c for c in rep.collisions if c["kind"] == "file_exists"][0]["path"], rel)

    def test_tampered_package_refuses(self):
        tampered = self.out / "t.lorevox.zip"
        with zipfile.ZipFile(self.zip) as src, zipfile.ZipFile(tampered, "w") as dst:
            for info in src.infolist():
                data = src.read(info.filename)
                if info.filename.endswith("/trips.jsonl"):
                    data = data.replace(b"Trip 0", b"Trip X")
                dst.writestr(info, data)
        rep = self.dry_run(tampered)
        self.assertFalse(rep.ready)
        self.assertTrue(any(r["code"] == "package_invalid" for r in rep.reasons), rep.reasons)

    def test_traversal_member_refuses_before_any_byte_lands(self):
        evil = self.out / "evil.lorevox.zip"
        with zipfile.ZipFile(self.zip) as src, zipfile.ZipFile(evil, "w") as dst:
            for info in src.infolist():
                dst.writestr(info, src.read(info.filename))
            dst.writestr("data/files/../../escape.txt", b"nope")
        rep = self.dry_run(evil)
        self.assertFalse(rep.ready)
        self.assertTrue(any("unsafe member path" in r.get("detail", "") for r in rep.reasons), rep.reasons)
        self.assertFalse((self.dest_root.parent / "escape.txt").exists())


class Restore(_RoundTrip):

    def test_every_row_and_file_arrives_with_ids_verbatim(self):
        res = self.restore()
        m = self.res.manifest
        con = self.dest()
        expected = {t: n for t, n in m["record_counts_by_lane"].items() if n}
        self.assertEqual(res.records_inserted, expected)
        # every packaged row is in the destination by primary key
        with zipfile.ZipFile(self.zip) as zf:
            for table, n in expected.items():
                recs = [json.loads(l) for l in zf.read(f"data/records/{table}.jsonl").decode().splitlines() if l.strip()]
                pk = [r["name"] for r in con.execute(f'PRAGMA table_info("{table}")') if r["pk"]] or ["rowid"]
                for rec in recs:
                    where = " AND ".join(f'"{c}"=?' for c in pk)
                    row = con.execute(f'SELECT * FROM "{table}" WHERE {where}', tuple(rec[c] for c in pk)).fetchone()
                    self.assertIsNotNone(row, f"{table} row {[rec[c] for c in pk]} did not arrive")
                self.assertEqual(con.execute(f'SELECT COUNT(*) FROM "{table}" WHERE {inv.owner_predicate(table)}',
                                             {"pid": self.ada}).fetchone()[0], n, table)
        self.assertEqual(con.execute("SELECT display_name FROM people WHERE id=?", (self.ada,)).fetchone()[0], "Ada Pruitt")
        # foreign keys hold in the destination
        for table in expected:
            self.assertEqual(con.execute(f'PRAGMA foreign_key_check("{table}")').fetchall(), [], table)
        # files: every payload member at DATA_DIR/<rel>, byte-identical to the manifest hash
        for member, digest in self.package_hashes().items():
            if member.startswith("data/files/"):
                p = self.dest_root / member[len("data/files/"):]
                self.assertTrue(p.is_file(), member)
                self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), digest, member)
        self.assertEqual(len(res.files_created), sum(m["file_counts_by_lane"].values()))
        # job row
        job = con.execute("SELECT * FROM narrator_package_jobs WHERE id=?", (res.job_id,)).fetchone()
        self.assertEqual(job["state"], "complete")
        self.assertEqual(job["narrator_id"], self.ada)
        self.assertEqual(json.loads(job["counts_json"]), expected)

    def test_travel_domain_restored_completely(self):
        self.restore()
        con = self.dest()
        for table in [l.table for l in inv.DB_LANES if l.table.startswith("trip")]:
            got = con.execute(f'SELECT COUNT(*) FROM "{table}" WHERE {inv.owner_predicate(table)}', {"pid": self.ada}).fetchone()[0]
            self.assertEqual(got, len(self.ids.get(table, [])), table)
        # the two source documents are on the new disk where their rows say
        for r in con.execute("SELECT storage_path FROM trip_sources"):
            self.assertTrue((self.dest_root / r[0]).is_file(), r[0])
        # turn links resolve to turns that exist in the destination
        for r in con.execute("SELECT assistant_turn_row_id, conv_id FROM trip_turn_links"):
            self.assertIsNotNone(con.execute("SELECT 1 FROM turns WHERE id=?", (r[0],)).fetchone())
            self.assertIsNotNone(con.execute("SELECT 1 FROM sessions WHERE conv_id=?", (r[1],)).fetchone())

    def test_absolute_path_columns_are_rewritten_under_the_new_root(self):
        self.restore()
        con = self.dest()
        for r in con.execute("SELECT image_path, thumbnail_path FROM photos"):
            for v in r:
                self.assertTrue(Path(v).is_absolute(), v)
                self.assertTrue(str(v).startswith(str(self.dest_root)), v)
                self.assertTrue(Path(v).is_file(), v)
                self.assertNotIn(str(self.root), v)   # nothing points back at the source machine
        # relative columns stayed relative
        for r in con.execute("SELECT archive_dir FROM memory_archive_sessions"):
            self.assertFalse(Path(r[0]).is_absolute(), r[0])
            self.assertTrue((self.dest_root / r[0]).is_dir(), r[0])
        for r in con.execute("SELECT storage_path FROM media_archive_items"):
            self.assertFalse(Path(r[0]).is_absolute(), r[0])

    def test_nothing_of_the_other_narrator_arrives_and_the_tag_is_kept_as_recorded(self):
        self.restore()
        con = self.dest()
        self.assertIsNone(con.execute("SELECT 1 FROM people WHERE id=?", (self.bea,)).fetchone())
        self.assertIsNone(con.execute("SELECT 1 FROM sessions WHERE conv_id='conv-bea-1'").fetchone())
        self.assertIsNone(con.execute("SELECT 1 FROM sessions WHERE conv_id='conv-nobody'").fetchone())
        self.assertEqual(con.execute("SELECT COUNT(*) FROM trips").fetchone()[0], 2)
        # §13: the tag naming Bea is preserved verbatim, dangling by design, reported by dry run
        tag = con.execute("SELECT person_id FROM media_archive_people").fetchone()
        self.assertEqual(tag[0], self.bea)
        # ownership evidence only — never a name substring (a hex id can spell "bea")
        dest = self.dest_files()
        self.assertFalse(any(self.bea in f for f in dest), [f for f in dest if self.bea in f])
        for rel in self.bea_files:
            self.assertFalse((self.dest_root / rel).exists(), f"Bea's file arrived: {rel}")
        for table, col in (("photos", "narrator_id"), ("trips", "person_id"), ("trip_sources", "trip_id")):
            if col == "trip_id":
                n = con.execute("SELECT COUNT(*) FROM trip_sources s JOIN trips t ON t.id=s.trip_id WHERE t.person_id=?", (self.bea,)).fetchone()[0]
            else:
                n = con.execute(f'SELECT COUNT(*) FROM "{table}" WHERE "{col}"=?', (self.bea,)).fetchone()[0]
            self.assertEqual(n, 0, f"Bea has rows in {table}")

    def test_second_restore_is_refused_not_overwritten(self):
        self.restore()
        con = self.dest()
        before = con.execute("SELECT COUNT(*) FROM turns").fetchone()[0]
        with self.assertRaises(pkg.RestoreRefused) as cm:
            self.restore()
        self.assertTrue(any(r["code"] == "collision" for r in cm.exception.report.reasons))
        self.assertEqual(con.execute("SELECT COUNT(*) FROM turns").fetchone()[0], before)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM narrator_package_jobs WHERE state='complete'").fetchone()[0], 1)

    def test_failure_inside_the_transaction_leaves_no_rows_no_files_and_a_failed_job(self):
        # Break a row's foreign key inside the package: a trip whose region names a
        # region that is not in the package. Dry run cannot see this (it checks ids
        # against the DESTINATION); deferred FK enforcement catches it at COMMIT.
        broken = self.out / "broken.lorevox.zip"
        with zipfile.ZipFile(self.zip) as src:
            names = src.namelist()
            payload = {n: src.read(n) for n in names}
        stops = payload["data/records/trip_stops.jsonl"].decode().splitlines()
        rec = json.loads(stops[0])
        # same LENGTH as the real id so bag-info's Payload-Oxum still matches
        rid = rec["trip_region_id"]
        rec["trip_region_id"] = rid[:-1] + ("0" if rid[-1] != "0" else "1")
        stops[0] = json.dumps(rec, ensure_ascii=False, default=str)
        payload["data/records/trip_stops.jsonl"] = ("\n".join(stops) + "\n").encode()
        # keep BagIt valid: recompute that member's hash in manifest-sha256.txt and the tag manifest
        new_hash = hashlib.sha256(payload["data/records/trip_stops.jsonl"]).hexdigest()
        lines = payload["manifest-sha256.txt"].decode().splitlines()
        lines = [f"{new_hash}  data/records/trip_stops.jsonl" if l.endswith("data/records/trip_stops.jsonl") else l for l in lines]
        payload["manifest-sha256.txt"] = ("\n".join(lines) + "\n").encode()
        tm = payload["tagmanifest-sha256.txt"].decode().splitlines()
        mh = hashlib.sha256(payload["manifest-sha256.txt"]).hexdigest()
        tm = [f"{mh}  manifest-sha256.txt" if l.endswith("manifest-sha256.txt") and not l.endswith("tagmanifest-sha256.txt") else l for l in tm]
        payload["tagmanifest-sha256.txt"] = ("\n".join(tm) + "\n").encode()
        with zipfile.ZipFile(broken, "w") as dst:
            for n in names:
                dst.writestr(n, payload[n])
        self.assertTrue(pkg.validate_package(broken).ok, "fixture: the broken package must still be BagIt-valid")

        files_before = self.dest_files()
        with self.assertRaises(RuntimeError) as cm:
            self.restore(broken)
        self.assertIn("database", str(cm.exception))
        con = self.dest()
        self.assertIsNone(con.execute("SELECT 1 FROM people WHERE id=?", (self.ada,)).fetchone())
        self.assertEqual(con.execute("SELECT COUNT(*) FROM trips").fetchone()[0], 0)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM turns").fetchone()[0], 0)
        self.assertEqual(self.dest_files(), files_before, "files created by the failed job were not removed")
        job = con.execute("SELECT state, error FROM narrator_package_jobs").fetchone()
        self.assertEqual(job["state"], "failed")
        self.assertIn("foreign", job["error"].lower())


class _SimulatedCrash(BaseException):
    """NOT an Exception: nothing in the service catches it, exactly as nothing
    catches a process death. The ordinary cleanup handlers must not run."""


class CrashRecovery(_RoundTrip):
    """§12: the job row is crash-truthful, and recovery decides from it alone."""

    def job(self):
        return self.dest().execute("SELECT * FROM narrator_package_jobs ORDER BY created_at DESC").fetchone()

    def test_death_during_file_copy_leaves_a_job_that_names_its_files_and_recovery_removes_only_them(self):
        files_before = self.dest_files()

        def seam(point):
            if point == "after_first_file":
                raise _SimulatedCrash(point)

        with self.assertRaises(_SimulatedCrash):
            pkg.restore_narrator(self.zip, data_dir=self.dest_root, db_path=self.dest_db, _crash_seam=seam)
        # durable truth after the "crash": still `validated`; the job carries the package's
        # payload manifest (planned path -> sha256, 0055) and has journaled what it CREATED (0054)
        job = self.job()
        self.assertEqual(job["state"], "validated")
        planned = json.loads(job["file_manifest_json"])
        self.assertEqual(len(planned), sum(self.res.manifest["file_counts_by_lane"].values()))
        self.assertTrue(all(len(h) == 64 for h in planned.values()))
        created = json.loads(job["files_json"])
        on_disk = [rel for rel in planned if (self.dest_root / rel).is_file()]
        self.assertEqual(sorted(created), sorted(on_disk), "files_json must be exactly what landed, not the plan")
        self.assertGreaterEqual(len(on_disk), 1, "the crash was simulated after the first file landed")
        self.assertLess(len(on_disk), len(planned))
        con = self.dest()
        self.assertIsNone(con.execute("SELECT 1 FROM people WHERE id=?", (self.ada,)).fetchone())
        # recovery: removes exactly the job's files (by hash, not by name), no rows, job failed
        reports = pkg.recover_restore_jobs(data_dir=self.dest_root, db_path=self.dest_db)
        self.assertEqual([r["action"] for r in reports], ["cleaned"])
        self.assertEqual(sorted(reports[0]["removed"]), sorted(on_disk))
        self.assertEqual(reports[0]["left"], [])
        self.assertEqual(self.job()["state"], "failed")
        self.assertEqual(self.dest_files(), files_before)
        self.assertIsNone(con.execute("SELECT 1 FROM people WHERE id=?", (self.ada,)).fetchone())
        # idempotent after `failed`: nothing on disk or in the database moves
        db_before = self.dest_db.read_bytes()
        self.assertEqual([r["action"] for r in pkg.recover_restore_jobs(data_dir=self.dest_root, db_path=self.dest_db)], ["none"])
        self.assertEqual(self.dest_files(), files_before)
        self.assertEqual(self.dest_db.read_bytes(), db_before)
        # and a normal restore now succeeds on the cleaned destination
        self.assertEqual(self.restore().records_inserted, {t: n for t, n in self.res.manifest["record_counts_by_lane"].items() if n})

    def test_recovery_never_deletes_foreign_bytes_at_a_planned_path(self):
        """Mid-copy crash; then something else writes DIFFERENT bytes at a path the job
        planned but never created. Recovery must leave it, name it, and not call the
        cleanup clean."""
        def seam(point):
            if point == "after_first_file":
                raise _SimulatedCrash(point)

        with self.assertRaises(_SimulatedCrash):
            pkg.restore_narrator(self.zip, data_dir=self.dest_root, db_path=self.dest_db, _crash_seam=seam)
        job = self.job()
        planned = json.loads(job["file_manifest_json"])
        created = set(json.loads(job["files_json"]))
        foreign = next(rel for rel in sorted(planned) if rel not in created)
        fp = self.dest_root / foreign
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(b"SOMEBODY ELSE'S BYTES")
        reports = pkg.recover_restore_jobs(data_dir=self.dest_root, db_path=self.dest_db)
        self.assertEqual(reports[0]["action"], "cleaned")
        self.assertEqual(sorted(reports[0]["removed"]), sorted(created))
        self.assertEqual([l["path"] for l in reports[0]["left"]], [foreign])
        self.assertIn("do not match", reports[0]["left"][0]["why"])
        self.assertTrue(fp.is_file(), "the foreign file was deleted")
        self.assertEqual(fp.read_bytes(), b"SOMEBODY ELSE'S BYTES")
        job = self.job()
        self.assertEqual(job["state"], "cleanup_required")
        self.assertEqual(json.loads(job["files_json"]), [foreign])
        self.assertIn(foreign, job["error"])
        # the operator resolves it; a retry then closes the job
        fp.unlink()
        reports = pkg.recover_restore_jobs(data_dir=self.dest_root, db_path=self.dest_db)
        self.assertEqual((reports[0]["action"], reports[0]["state_after"]), ("cleaned", "failed"))

    def test_death_after_commit_leaves_db_committed_and_recovery_finishes_without_deleting(self):
        def seam(point):
            if point == "after_commit":
                raise _SimulatedCrash(point)

        with self.assertRaises(_SimulatedCrash):
            pkg.restore_narrator(self.zip, data_dir=self.dest_root, db_path=self.dest_db, _crash_seam=seam)
        job = self.job()
        self.assertEqual(job["state"], "db_committed", "db_committed must be published WITH the rows")
        expected = {t: n for t, n in self.res.manifest["record_counts_by_lane"].items() if n}
        self.assertEqual(json.loads(job["counts_json"]), expected)
        con = self.dest()
        self.assertIsNotNone(con.execute("SELECT 1 FROM people WHERE id=?", (self.ada,)).fetchone())
        files_after_crash = self.dest_files()
        for rel in json.loads(job["files_json"]):
            self.assertTrue((self.dest_root / rel).is_file(), rel)
        # the package is GONE before recovery runs — Phase 5's upload staging will not
        # outlive a restart. Recovery must verify from the durable job alone.
        self.zip.unlink()
        reports = pkg.recover_restore_jobs(data_dir=self.dest_root, db_path=self.dest_db)
        self.assertEqual([r["action"] for r in reports], ["completed"], reports)
        self.assertEqual(reports[0]["hashes_checked"], sum(self.res.manifest["file_counts_by_lane"].values()))
        self.assertEqual(self.job()["state"], "complete")
        self.assertEqual(self.dest_files(), files_after_crash)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM trips").fetchone()[0], 2)
        # idempotent
        self.assertEqual([r["action"] for r in pkg.recover_restore_jobs(data_dir=self.dest_root, db_path=self.dest_db)], ["none"])

    def test_recovery_refuses_to_delete_under_a_published_narrator(self):
        """The defensive check: a job below db_committed whose narrator IS present
        is a contradiction to report, never a licence to delete."""
        self.restore()
        con = sqlite3.connect(str(self.dest_db))
        con.execute("UPDATE narrator_package_jobs SET state='files_copied'")   # forge the contradiction
        con.commit()
        con.close()
        files_before = self.dest_files()
        reports = pkg.recover_restore_jobs(data_dir=self.dest_root, db_path=self.dest_db)
        self.assertEqual(reports[0]["action"], "refused")
        self.assertEqual(self.dest_files(), files_before)
        self.assertIn("recovery_required", self.job()["error"])

    def test_cleanup_required_under_a_published_narrator_is_refused_too(self):
        """The realistic path to this contradiction: a restore dies mid-copy, recovery leaves
        the job `cleanup_required` because foreign bytes sit at a planned path, the operator
        resolves that and runs a SECOND restore, which publishes the narrator with files
        whose bytes hash-match the OLD job's manifest. Recovering the old job must now
        refuse — deleting those matching files would gut the live narrator."""
        def seam(point):
            if point == "after_first_file":
                raise _SimulatedCrash(point)

        with self.assertRaises(_SimulatedCrash):
            pkg.restore_narrator(self.zip, data_dir=self.dest_root, db_path=self.dest_db, _crash_seam=seam)
        old = self.job()
        planned = json.loads(old["file_manifest_json"])
        created = set(json.loads(old["files_json"]))
        foreign = next(rel for rel in sorted(planned) if rel not in created)
        fp = self.dest_root / foreign
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(b"SOMEBODY ELSE'S BYTES")
        reports = pkg.recover_restore_jobs(data_dir=self.dest_root, db_path=self.dest_db)
        self.assertEqual((reports[0]["action"], reports[0]["state_after"]), ("cleaned", "cleanup_required"))
        # operator resolves the foreign file and restores successfully — Ada is now PUBLISHED
        fp.unlink()
        res = self.restore()
        con = self.dest()
        self.assertIsNotNone(con.execute("SELECT 1 FROM people WHERE id=?", (self.ada,)).fetchone())
        published_files = {rel: hashlib.sha256((self.dest_root / rel).read_bytes()).hexdigest() for rel in planned}
        self.assertEqual(published_files, planned, "the second restore's files hash-match the old job's manifest")
        rows_before = con.execute("SELECT COUNT(*) FROM turns").fetchone()[0]
        # recovering the OLD cleanup_required job must refuse, not delete
        reports = pkg.recover_restore_jobs(data_dir=self.dest_root, db_path=self.dest_db, job_id=old["id"])
        self.assertEqual(reports[0]["action"], "refused", reports)
        old_after = con.execute("SELECT * FROM narrator_package_jobs WHERE id=?", (old["id"],)).fetchone()
        self.assertEqual(old_after["state"], "cleanup_required")
        self.assertIn("recovery_required", old_after["error"])
        self.assertEqual({rel: hashlib.sha256((self.dest_root / rel).read_bytes()).hexdigest() for rel in planned},
                         planned, "a published narrator's files were touched")
        self.assertEqual(con.execute("SELECT COUNT(*) FROM turns").fetchone()[0], rows_before)
        self.assertEqual(con.execute("SELECT state FROM narrator_package_jobs WHERE id=?", (res.job_id,)).fetchone()[0], "complete")

    def test_db_committed_with_a_missing_file_is_recovery_required_not_complete(self):
        def seam(point):
            if point == "after_commit":
                raise _SimulatedCrash(point)

        with self.assertRaises(_SimulatedCrash):
            pkg.restore_narrator(self.zip, data_dir=self.dest_root, db_path=self.dest_db, _crash_seam=seam)
        rels = json.loads(self.job()["files_json"])
        (self.dest_root / rels[0]).unlink()
        (self.dest_root / rels[1]).write_bytes(b"ALTERED AFTER COMMIT")
        reports = pkg.recover_restore_jobs(data_dir=self.dest_root, db_path=self.dest_db)
        self.assertEqual(reports[0]["action"], "refused")
        problems = reports[0]["problems"]
        self.assertTrue(any(p.startswith("file missing") and rels[0] in p for p in problems), problems)
        self.assertTrue(any(p.startswith("file hash differs") and rels[1] in p for p in problems), problems)
        self.assertEqual(self.job()["state"], "db_committed")
        self.assertTrue((self.dest_root / rels[1]).is_file(), "recovery must delete nothing at db_committed")


class DeclarationCoversTheJobTable(_RoundTrip):

    def test_job_table_is_installation_owned_and_never_travels(self):
        lane = inv.lane("narrator_package_jobs")
        self.assertIsInstance(lane.owner, inv.Installation)
        self.assertEqual(lane.portable, "no")
        self.restore()
        # re-export from the destination: the job row is not in the package
        out2 = Path(self._tmp.name) / "packages2"
        out2.mkdir()
        res2 = pkg.export_narrator(self.ada, data_dir=self.dest_root, db_path=self.dest_db, out_dir=out2, repo_root=REPO_ROOT)
        with zipfile.ZipFile(res2.package_path) as zf:
            self.assertFalse(any("narrator_package_jobs" in n for n in zf.namelist()))
        self.assertEqual({t: n for t, n in res2.manifest["record_counts_by_lane"].items() if n},
                         {t: n for t, n in self.res.manifest["record_counts_by_lane"].items() if n},
                         "re-export from the destination does not carry the same record counts")
