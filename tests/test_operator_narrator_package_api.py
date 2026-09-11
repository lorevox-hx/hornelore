"""WO-LOREVOX-PORTABLE-NARRATOR-01 Phase 5 — the operator HTTP layer over the package service.

The service is proven (Phases 2–4). This proves the ROUTER adds a safe workflow
and no logic of its own:

  * 404 when the flag is off — every verb
  * preflight: identity + per-lane counts from the declaration, nothing built; the
    plain-language summary is the server's, and it equals the fixture's own counts
  * export: 202 + job id, a daemon thread, durable 0056 row queued → running →
    complete; the download streams the very bytes on disk; the file is OUTSIDE DATA_DIR
  * import: an uploaded package is streamed to staging outside DATA_DIR and answered
    with TWO verdicts; a tampered package fails integrity and readiness is not even
    computed; a collision fails readiness while integrity passes; restore is refused
    with 409 unless readiness is READY, and there is no parameter that overrides it
  * restore through the router publishes the narrator; the 0054 job is `complete`;
    the staged file is gone afterwards; a second restore is a collision
  * one operation at a time: a second export while one runs is 409
  * a fixture-sized upload over the cap is 413 and nothing is left in staging
  * no verb on the router deletes narrator data (route table pinned)

Two installations in one test: Ada is exported from the SOURCE (Phase 2 fixture)
and imported into a DESTINATION built by init_db(), with the router re-pointed
between them by environment + reload, the way the product itself binds DATA_DIR.

Run:
    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_operator_narrator_package_api
"""
from __future__ import annotations

import importlib
import io
import json
import os
import sqlite3
import time
import zipfile
from pathlib import Path

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    _FASTAPI = True
except ImportError:  # the suite must REFUSE, not skip silently
    _FASTAPI = False

from tests.test_narrator_package_export import _Fixture, REPO_ROOT  # noqa: F401
from api.services import narrator_package as pkg  # noqa: E402


def _wait(pred, timeout=120.0, every=0.2):
    end = time.time() + timeout
    while time.time() < end:
        v = pred()
        if v:
            return v
        time.sleep(every)
    raise AssertionError("timed out waiting for the job")


class _Api(_Fixture):
    """Source fixture from Phase 2 + a TestClient over the router, pointed at the
    installation the environment names."""

    def setUp(self):
        if not _FASTAPI:
            self.fail("fastapi is not importable in this interpreter; run under .venv")
        super().setUp()
        self.side = Path(self._tmp.name) / "side"
        self.side.mkdir()
        self._prev_env = {k: os.environ.get(k) for k in (
            "HORNELORE_OPERATOR_PORTABLE_NARRATOR", "HORNELORE_PACKAGE_OUT_DIR",
            "HORNELORE_PACKAGE_STAGING_DIR", "HORNELORE_PACKAGE_MAX_MB")}
        os.environ["HORNELORE_OPERATOR_PORTABLE_NARRATOR"] = "1"
        os.environ["HORNELORE_PACKAGE_OUT_DIR"] = str(self.side / "packages")
        os.environ["HORNELORE_PACKAGE_STAGING_DIR"] = str(self.side / "staging")
        os.environ.pop("HORNELORE_PACKAGE_MAX_MB", None)
        self.addCleanup(self._restore_env)
        self.client = self._client()

    def _restore_env(self):
        for k, v in self._prev_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _client(self) -> "TestClient":
        from api.routers import operator_narrator_package as r
        importlib.reload(r)
        self.router_mod = r
        app = FastAPI()
        app.include_router(r.router)
        return TestClient(app)

    def point_at_destination(self):
        """Build an empty destination with init_db() and re-point db + router at it."""
        self.dest_root = Path(self._tmp.name) / "dest"
        self.dest_root.mkdir()
        os.environ["DATA_DIR"] = str(self.dest_root)
        os.environ["DB_NAME"] = "dest.sqlite3"
        from api import db as _db
        importlib.reload(_db)
        _db.init_db()
        self.dest_db = Path(_db.DB_PATH)
        self.assertTrue(str(self.dest_db).startswith(str(self.dest_root)))
        con = sqlite3.connect(str(self.dest_db))
        try:
            # the one installation dependency Ada carries (§5-E) is the destination's to
            # provide; init_db() already seeds a default plan under a fixed id on both
            # installations, and an installation row that already exists is exactly that
            for pid in self.plan_ids():
                con.execute("INSERT OR IGNORE INTO interview_plans (id, title, created_at) VALUES (?, ?, ?)", (pid, "plan", "t"))
            con.commit()
        finally:
            con.close()
        self.client = self._client()

    def plan_ids(self):
        return [r[0] for r in self.con.execute("SELECT id FROM interview_plans")]

    def export_via_router(self) -> dict:
        r = self.client.post(f"/api/operator/narrator-package/export/{self.ada}")
        self.assertEqual(r.status_code, 202, r.text)
        job_id = r.json()["job_id"]
        return _wait(lambda: (lambda j: j if j["state"] in ("complete", "failed", "refused") else None)(
            self.client.get(f"/api/operator/narrator-package/export/jobs/{job_id}").json()))


class GateAndPreflight(_Api):

    def test_404_on_every_verb_when_off(self):
        os.environ["HORNELORE_OPERATOR_PORTABLE_NARRATOR"] = "0"
        c = self._client()
        for method, path in (("get", f"/preflight/{self.ada}"), ("post", f"/export/{self.ada}"),
                             ("get", "/export/jobs"), ("get", "/restore/jobs"), ("post", "/recover"),
                             ("get", "/import/nope")):
            r = getattr(c, method)("/api/operator/narrator-package" + path)
            self.assertEqual(r.status_code, 404, (method, path, r.text))
        r = c.post("/api/operator/narrator-package/import/upload", files={"file": ("x.zip", b"zz", "application/zip")})
        self.assertEqual(r.status_code, 404)

    def test_preflight_reports_the_declarations_counts_without_building(self):
        r = self.client.get(f"/api/operator/narrator-package/preflight/{self.ada}")
        self.assertEqual(r.status_code, 200, r.text)
        p = r.json()
        self.assertEqual(p["narrator_id"], self.ada)
        self.assertEqual(p["narrator_display_name"], "Ada Pruitt")
        for table, seeded in self.ids.items():
            self.assertEqual(p["record_counts_by_lane"].get(table), len(seeded), table)
        s = p["summary"]
        self.assertEqual(s["trips"], 2)
        self.assertEqual(s["photos"], 3)
        self.assertEqual(s["conversations"], 2)
        self.assertGreater(s["files"], 0)
        self.assertRegex(s["size_human"], r"^\d+(\.\d)? (B|KB|MB)$")
        self.assertEqual(list((self.side / "packages").glob("*.lorevox.zip")), [], "preflight must build nothing")
        r = self.client.get("/api/operator/narrator-package/preflight/no-such-person")
        self.assertEqual(r.status_code, 404)

    def test_route_table_has_no_verb_that_deletes_narrator_data(self):
        routes = [(sorted(rt.methods), rt.path) for rt in self.router_mod.router.routes]
        self.assertFalse(any("DELETE" in m for m, _ in routes), routes)
        self.assertFalse(any("delete" in p or "erase" in p for _, p in routes), routes)


class ExportJobs(_Api):

    def test_export_runs_as_a_job_and_the_download_streams_the_file_on_disk(self):
        j = self.export_via_router()
        self.assertEqual(j["state"], "complete", j)
        self.assertTrue(j["download_available"])
        self.assertEqual(j["narrator_display_name"], "Ada Pruitt")
        self.assertEqual(j["summary"]["trips"], 2)
        self.assertEqual(j["summary"]["photos"], 3)
        self.assertIn("record_counts_by_lane", j["advanced"])
        # the package is on disk OUTSIDE DATA_DIR, and the download is those bytes
        files = list((self.side / "packages").glob("*.lorevox.zip"))
        self.assertEqual(len(files), 1)
        self.assertFalse(str(files[0]).startswith(str(self.root)))
        r = self.client.get(f"/api/operator/narrator-package/export/jobs/{j['job_id']}/download")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"].split(";")[0], "application/zip")
        self.assertIn(files[0].name, r.headers.get("content-disposition", ""))
        self.assertEqual(r.content, files[0].read_bytes())
        self.assertTrue(pkg.validate_package(files[0]).ok)
        # durable row
        con = sqlite3.connect(str(self.db_path))
        row = con.execute("SELECT state, package_path, package_bytes FROM narrator_package_export_jobs WHERE id=?", (j["job_id"],)).fetchone()
        con.close()
        self.assertEqual(row[0], "complete")
        self.assertEqual(Path(row[1]), files[0])
        self.assertEqual(row[2], files[0].stat().st_size)
        self.assertEqual(self.client.get("/api/operator/narrator-package/export/jobs").json()["jobs"][0]["job_id"], j["job_id"])

    def test_refusal_is_a_durable_refused_job_not_an_error(self):
        # break a verified source so the exporter refuses (§29.3)
        (self.root / "import_staging" / self.batch / self.pending / "original.jpg").write_bytes(b"WRONG")
        j = self.export_via_router()
        self.assertEqual(j["state"], "refused", j)
        self.assertTrue(any(r["code"] == "verified_source_hash_mismatch" for r in j["refusal"]), j["refusal"])
        self.assertFalse(j["download_available"])
        self.assertEqual(list((self.side / "packages").glob("*.lorevox.zip")), [])
        r = self.client.get(f"/api/operator/narrator-package/export/jobs/{j['job_id']}/download")
        self.assertEqual(r.status_code, 404)

    def test_progress_is_observational_stages_and_the_package_is_unchanged_by_it(self):
        j = self.export_via_router()
        self.assertEqual(j["state"], "complete", j)
        prog = j["progress"]
        self.assertEqual(prog["stage"], "complete")
        self.assertEqual([s["name"] for s in prog["stages"]], list(pkg.EXPORT_STAGES))
        self.assertTrue(all(s["state"] == "complete" for s in prog["stages"]))
        # observational only: the package the job built validates exactly as a service export does
        files = list((self.side / "packages").glob("*.lorevox.zip"))
        self.assertTrue(pkg.validate_package(files[0]).ok)
        direct = self.export()      # the same narrator, through the service, no progress hook
        rep = pkg.compare_packages_semantically(files[0], direct.package_path)
        self.assertTrue(rep.equivalent, rep.differences[:5])

    def test_remove_server_copy_removes_only_the_artifact_and_keeps_the_record(self):
        j = self.export_via_router()
        path = list((self.side / "packages").glob("*.lorevox.zip"))[0]
        rows_before = self.con.execute("SELECT COUNT(*) FROM turns").fetchone()[0]
        files_before = sorted(str(p) for p in self.root.rglob("*") if p.is_file() and not p.name.endswith(("-wal", "-shm")))
        r = self.client.post(f"/api/operator/narrator-package/export/jobs/{j['job_id']}/remove-server-copy")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["package_removed"])
        self.assertFalse(path.exists(), "the artifact should be gone")
        # narrator untouched: rows and every file under DATA_DIR
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM turns").fetchone()[0], rows_before)
        self.assertEqual(sorted(str(p) for p in self.root.rglob("*") if p.is_file() and not p.name.endswith(("-wal", "-shm"))), files_before)
        # the job record stays and says so
        v = self.client.get(f"/api/operator/narrator-package/export/jobs/{j['job_id']}").json()
        self.assertEqual(v["state"], "complete")
        self.assertFalse(v["download_available"])
        self.assertTrue(v["package_removed_at"])
        self.assertEqual(v["summary"]["trips"], 2, "what was created is still recorded")
        self.assertIn("never removes the narrator", v["retention"]["note"])
        self.assertEqual(self.client.get(f"/api/operator/narrator-package/export/jobs/{j['job_id']}/download").status_code, 410)
        # idempotent-ish: a second removal is a clean 200, nothing else to remove
        self.assertEqual(self.client.post(f"/api/operator/narrator-package/export/jobs/{j['job_id']}/remove-server-copy").status_code, 200)

    def test_one_package_operation_at_a_time(self):
        held = self.router_mod._OP_LOCK.acquire(blocking=False)
        self.assertTrue(held)
        try:
            r = self.client.post(f"/api/operator/narrator-package/export/{self.ada}")
            self.assertEqual(r.status_code, 409, r.text)
            self.assertEqual(r.json()["detail"]["code"], "package_operation_in_progress")
        finally:
            self.router_mod._OP_LOCK.release()


class FreshInstallationInitialisesItself(_Api):
    """Phase 6 first real run (2026-09-11): the operator's FIRST act on a brand-new
    root was to upload a package, and readiness refused `db_not_found` because the
    database file is created lazily by init_db() and nothing had called it yet. The
    5a walk had probed /api/people first, which hid it. The router must initialise
    the installation before it gives any verdict."""

    def setUp(self):
        super().setUp()
        self.package = self.export().package_path
        # a root that has NEVER been initialised: no db directory, no file, no seeds
        self.dest_root = Path(self._tmp.name) / "fresh"
        self.dest_root.mkdir()
        os.environ["DATA_DIR"] = str(self.dest_root)
        os.environ["DB_NAME"] = "fresh.sqlite3"
        from api import db as _db
        importlib.reload(_db)
        self.dest_db = Path(_db.DB_PATH)
        self.assertFalse(self.dest_db.exists(), "the fixture must start with no database file")
        self.client = self._client()

    def test_first_upload_on_a_never_initialised_root_gets_a_real_readiness_verdict(self):
        with self.package.open("rb") as fh:
            r = self.client.post("/api/operator/narrator-package/import/upload",
                                 files={"file": ("ada.lorevox.zip", fh, "application/zip")})
        self.assertEqual(r.status_code, 201, r.text)
        u = r.json()
        self.assertTrue(u["integrity"]["ok"], u["integrity"])
        codes = {x["code"] for x in u["readiness"]["reasons"]}
        self.assertNotIn("db_not_found", codes, u["readiness"])
        self.assertNotIn("unsupported_schema", codes, u["readiness"])
        self.assertTrue(self.dest_db.exists(), "the installation initialised itself before judging")
        # the installation-owned seeds are there too: the questionnaire schema and the
        # chat plan — the only dependency left unmet is the fixture's own minted plan id
        missing = {m["table"] for m in u["readiness"]["missing_dependencies"]}
        self.assertNotIn("bio_fields", missing, u["readiness"]["missing_dependencies"])
        con = sqlite3.connect(str(self.dest_db))
        try:
            self.assertIsNotNone(con.execute("SELECT 1 FROM interview_plans WHERE id='chat_ws'").fetchone())
        finally:
            con.close()


class ImportWorkflow(_Api):

    def setUp(self):
        super().setUp()
        self.package = self.export().package_path        # from the SOURCE, via the service
        self.point_at_destination()                        # router now serves the DESTINATION

    def upload(self, path: Path, name="ada.lorevox.zip"):
        with path.open("rb") as fh:
            return self.client.post("/api/operator/narrator-package/import/upload",
                                    files={"file": (name, fh, "application/zip")})

    def test_upload_gives_two_verdicts_and_stages_outside_data_dir(self):
        r = self.upload(self.package)
        self.assertEqual(r.status_code, 201, r.text)
        u = r.json()
        self.assertTrue(u["integrity"]["ok"], u["integrity"])
        self.assertTrue(u["integrity"]["bagit_valid"])
        self.assertTrue(u["readiness"]["ready"], u["readiness"])
        self.assertEqual(u["readiness"]["verdict"], "RESTORE READY")
        self.assertEqual(u["narrator_id"], self.ada)
        self.assertEqual(u["summary"]["trips"], 2)
        self.assertEqual(u["state"], "checked")
        # the stepper is the server's: Choose, Upload, Check package, Check readiness done → Review current
        st = u["stepper"]
        self.assertEqual([s["state"] for s in st["steps"]], ["complete"] * 4 + ["current", "pending", "pending"])
        self.assertEqual(st["current"], 5)
        staged = list((self.side / "staging").rglob("package.lorevox.zip"))
        self.assertEqual(len(staged), 1)
        self.assertFalse(str(staged[0]).startswith(str(self.dest_root)))
        # nothing restored yet
        con = sqlite3.connect(str(self.dest_db))
        self.assertIsNone(con.execute("SELECT 1 FROM people WHERE id=?", (self.ada,)).fetchone())
        con.close()

    def test_tampered_package_fails_integrity_and_readiness_is_not_computed(self):
        bad = self.side / "bad.lorevox.zip"
        with zipfile.ZipFile(self.package) as src, zipfile.ZipFile(bad, "w") as dst:
            for info in src.infolist():
                data = src.read(info.filename)
                if info.filename.endswith("/trips.jsonl"):
                    data = data.replace(b"Trip 0", b"Trip X")
                dst.writestr(info, data)
        u = self.upload(bad).json()
        self.assertFalse(u["integrity"]["ok"])
        self.assertFalse(u["integrity"]["bagit_valid"])
        self.assertIsNone(u["readiness"])
        self.assertEqual(u["state"], "integrity_failed")
        self.assertEqual(u["stepper"]["steps"][2], {"n": 3, "name": "Check package", "state": "failed"})
        r = self.client.post(f"/api/operator/narrator-package/import/{u['upload_id']}/restore")
        self.assertEqual(r.status_code, 409)

    def test_collision_fails_readiness_while_integrity_passes_and_restore_is_refused(self):
        first = self.upload(self.package).json()
        r = self.client.post(f"/api/operator/narrator-package/import/{first['upload_id']}/restore")
        self.assertEqual(r.status_code, 202, r.text)
        _wait(lambda: self.client.get(f"/api/operator/narrator-package/import/{first['upload_id']}").json()["state"] != "restoring")
        u = self.upload(self.package).json()
        self.assertTrue(u["integrity"]["ok"])
        self.assertFalse(u["readiness"]["ready"])
        self.assertTrue(any(c["kind"] == "narrator_exists" for c in u["readiness"]["collisions"]), u["readiness"])
        r = self.client.post(f"/api/operator/narrator-package/import/{u['upload_id']}/restore")
        self.assertEqual(r.status_code, 409, r.text)
        self.assertEqual(r.json()["detail"]["code"], "restore_refused")
        # and there is no field that changes that
        r = self.client.post(f"/api/operator/narrator-package/import/{u['upload_id']}/restore",
                             json={"force": True, "restore_anyway": True})
        self.assertEqual(r.status_code, 409)

    def test_restore_through_the_router_publishes_the_narrator(self):
        u = self.upload(self.package).json()
        r = self.client.post(f"/api/operator/narrator-package/import/{u['upload_id']}/restore")
        self.assertEqual(r.status_code, 202, r.text)
        final = _wait(lambda: (lambda v: v if v["state"] != "restoring" else None)(
            self.client.get(f"/api/operator/narrator-package/import/{u['upload_id']}").json()))
        self.assertEqual(final["state"], "restored", final)
        self.assertTrue(all(s["state"] == "complete" for s in final["stepper"]["steps"]), final["stepper"])
        self.assertEqual(final["restore_result"]["narrator_id"], self.ada)
        self.assertEqual(final["restore_job"]["state"], "complete")
        expected = {t: n for t, n in self.res_manifest()["record_counts_by_lane"].items() if n}
        self.assertEqual(final["restore_result"]["records_inserted"], expected)
        con = sqlite3.connect(str(self.dest_db))
        try:
            self.assertEqual(con.execute("SELECT display_name FROM people WHERE id=?", (self.ada,)).fetchone()[0], "Ada Pruitt")
            self.assertEqual(con.execute("SELECT COUNT(*) FROM trips").fetchone()[0], 2)
            self.assertEqual(con.execute("SELECT state FROM narrator_package_jobs").fetchone()[0], "complete")
        finally:
            con.close()
        # staging is not narrator state: gone after restore
        self.assertEqual(list((self.side / "staging").rglob("package.lorevox.zip")), [])
        jobs = self.client.get("/api/operator/narrator-package/restore/jobs").json()
        self.assertEqual(jobs["incomplete"], 0)
        self.assertEqual(jobs["jobs"][0]["state"], "complete")

    def res_manifest(self):
        rep = pkg.validate_package(self.package)
        return rep.manifest

    def test_discard_removes_only_the_staged_file(self):
        u = self.upload(self.package).json()
        staged = list((self.side / "staging").rglob("package.lorevox.zip"))
        self.assertEqual(len(staged), 1)
        r = self.client.post(f"/api/operator/narrator-package/import/{u['upload_id']}/discard")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(list((self.side / "staging").rglob("package.lorevox.zip")), [])
        self.assertEqual(self.client.get(f"/api/operator/narrator-package/import/{u['upload_id']}").status_code, 404)
        self.assertTrue(self.package.is_file(), "the operator's own file is untouched")

    def test_upload_over_the_cap_is_413_and_leaves_nothing(self):
        os.environ["HORNELORE_PACKAGE_MAX_MB"] = "0"     # cap 0 bytes: any upload is over
        r = self.upload(self.package)
        self.assertEqual(r.status_code, 413, r.text)
        self.assertEqual(r.json()["detail"]["code"], "package_too_large")
        self.assertEqual([p for p in (self.side / "staging").rglob("*") if p.is_file()], [],
                         "a refused upload must leave nothing in staging")


class CardSourcePins(_Api):
    """Source pins on the card, NOT acceptance evidence for its behaviour (CLAUDE.md:
    source-string assertions are never acceptance by themselves). They guard the two
    hard rules that must never regress by accident; the rendered behaviour is proven
    by the Phase 5 live acceptance, not here."""

    def _src(self):
        return (REPO_ROOT / "ui" / "js" / "operator-portable-narrator-card.js").read_text(encoding="utf-8")

    def test_card_offers_no_restore_anyway_no_narrator_data_deletion_and_no_export_plus_delete(self):
        """The invariant, precisely (review 2026-09-11): no "Restore anyway"; no control that
        deletes narrator rows or files; no combined Export+Delete. "Remove server copy" is
        ALLOWED and scoped: it removes only the finished .lorevox.zip artifact outside
        DATA_DIR, and the job record stays and says the copy was removed."""
        src = self._src()
        low = src.lower()
        self.assertNotIn("restore anyway", low.replace('no "restore anyway"', ""))
        for forbidden in ("/erase", "mode=hard", "hard_delete", "delete narrator", "delete this narrator",
                          "export and delete", "export & delete", "export+delete", "/people/"):
            self.assertNotIn(forbidden, low, forbidden)
        # the Restore control is created ONLY inside the readiness-ready branch, behind a confirmation
        self.assertIn("if (r && r.ready) row.appendChild", src)
        self.assertIn("confirmRestore(u).then", src)
        # the one artifact-removal control calls exactly the scoped verb, nothing else
        self.assertEqual(src.count("/remove-server-copy"), 1)
        self.assertIn("Removing the server copy never removes the narrator", (REPO_ROOT / "server/code/api/routers/operator_narrator_package.py").read_text(encoding="utf-8"))

    def test_card_renders_stages_and_steps_from_server_fields_only(self):
        src = self._src()
        for must in ("p.stages", "s.state", "sp.steps", "u.stepper", "j.progress", "'aria-busy'", "role: 'status'"):
            self.assertIn(must, src, must)
        # no percentage is ever computed in the browser
        self.assertNotIn("* 100", src)
        self.assertNotIn("/ p.total", src)

    def test_card_computes_no_verdict_of_its_own(self):
        src = self._src()
        # every verdict string it renders comes from a server field
        # integrity is rendered from the server's `integrity` object, readiness from the
        # server's `readiness` object; job and upload states from the server's fields
        for must in ("u.integrity", "integ.ok", "u.readiness", "r.ready", "j.state", "u.state", "u.stepper"):
            self.assertIn(must, src, must)
        # and neither verdict is derived in the browser from its ingredients
        for forbidden in ("collisions.length === 0", "collisions.length == 0", "reasons.length === 0",
                          "missing_dependencies.length", "problems.length === 0", "ready = ", "ready=!"):
            self.assertNotIn(forbidden, src, forbidden)
        # it never opens the package itself: no ZIP or bag parsing in the browser
        for forbidden in ("JSZip", "zip.js", "manifest-sha256", "bagit.txt", "sha256("):
            self.assertNotIn(forbidden.lower(), src.lower(), forbidden)

    def test_card_is_mounted_on_the_operator_tab_only(self):
        html = (REPO_ROOT / "ui" / "hornelore1.0.html").read_text(encoding="utf-8")
        self.assertEqual(html.count('id="lvOperatorPortableNarrator"'), 1)
        idx = html.index('id="lvOperatorPortableNarrator"')
        self.assertGreater(idx, html.index('id="lvOperatorTab"'))
        self.assertIn("operator-portable-narrator-card.js", html)


class RecoverViaRouter(_Api):

    def test_recover_reports_the_services_decisions(self):
        self.point_at_destination()
        r = self.client.post("/api/operator/narrator-package/recover")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["reports"], [])
        self.assertEqual(r.json()["refused"], 0)
