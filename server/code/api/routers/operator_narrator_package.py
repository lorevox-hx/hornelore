"""Operator surface for the Lorevox Narrator Package — WO-LOREVOX-PORTABLE-NARRATOR-01 Phase 5 (§16, §16.1, §35).

An HTTP layer over ONE service. Nothing here exports, validates, dry-runs,
restores or recovers on its own: every verb below calls
`services.narrator_package` and reports what it said (§28.5). What this router
adds is the operator workflow the WO asks for and nothing more:

  Export    preflight (from the declaration, nothing built) → start job → poll
            → package on disk OUTSIDE DATA_DIR → download streamed from disk.
  Import    upload streamed to a controlled staging area OUTSIDE DATA_DIR →
            TWO verdicts, integrity and readiness, as separate objects → restore
            only when readiness is READY (re-checked at restore time; there is
            no "restore anyway") → poll → narrator available.
  Recover   finish or undo interrupted restore jobs through the service's rules.

Jobs are asynchronous — one daemon thread per operation, state durable in the
job tables (0054/0055 restore, 0056 export), polled by GET. ONE PACKAGE
OPERATION AT A TIME in this process: a module lock makes Phase 3's
"stack down / exclusive" assumption an application rule rather than an
operator's memory.

GATE, LIKE EVERY OTHER OPERATOR ROUTE. `HORNELORE_OPERATOR_PORTABLE_NARRATOR=1`,
404 when off — not 403 — so an outside probe cannot distinguish "off" from
"absent". Same posture as `operator_guard_lab`.

Paths are explicit and validated, never inferred from a request: DATA_DIR and
the database come from the running installation's own configuration, the
package output and staging directories from `HORNELORE_PACKAGE_OUT_DIR` /
`HORNELORE_PACKAGE_STAGING_DIR` (defaults beside DATA_DIR, never inside it).
NOTHING ON THIS ROUTER DELETES NARRATOR DATA, and nothing will (§16). Two verbs
remove files, both outside DATA_DIR and neither narrator state: "discard" removes
a staged upload; "remove-server-copy" removes a finished package artifact, checked
to resolve under the configured output directory first, and keeps the job record.
Exclusivity (`_OP_LOCK`) is per process; a multi-worker deployment would need a
cross-process lock (WO §35.3, deployment hardening — not a Phase 5a concern).
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from .. import db as _db
from ..services import narrator_package as pkg
from ..services import narrator_package_summary as summary
from ..services.narrator_erasure import validate_root

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/operator/narrator-package", tags=["operator", "narrator-package"])

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

# ── gate ─────────────────────────────────────────────────────────────────

def _enabled() -> bool:
    return os.getenv("HORNELORE_OPERATOR_PORTABLE_NARRATOR", "0").strip().lower() in ("1", "true", "yes", "on")


def _require_enabled() -> None:
    if not _enabled():
        raise HTTPException(status_code=404, detail="Not found")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── paths: explicit, validated, never inside DATA_DIR ────────────────────

def _data_dir() -> Path:
    return validate_root(os.getenv("DATA_DIR", ""))


def _db_path() -> Path:
    return Path(_db.DB_PATH)


def _side_dir(env: str, default_name: str) -> Path:
    """An absolute directory OUTSIDE DATA_DIR; default is a sibling of DATA_DIR."""
    root = _data_dir()
    raw = os.getenv(env, "").strip()
    p = Path(raw).expanduser() if raw else root.parent / default_name
    if not p.is_absolute():
        raise HTTPException(status_code=503, detail={"code": f"{env}_not_absolute", "path": str(p)})
    try:
        p.resolve().relative_to(root.resolve())
        raise HTTPException(status_code=503, detail={"code": f"{env}_inside_data_dir", "path": str(p),
                                                    "message": "package directories must live outside DATA_DIR"})
    except ValueError:
        pass
    p.mkdir(parents=True, exist_ok=True)
    return p


def _out_dir() -> Path:
    return _side_dir("HORNELORE_PACKAGE_OUT_DIR", "lorevox_packages")


def _staging_dir() -> Path:
    return _side_dir("HORNELORE_PACKAGE_STAGING_DIR", "lorevox_package_staging")


def _max_upload_bytes() -> int:
    try:
        return int(os.getenv("HORNELORE_PACKAGE_MAX_MB", "20480")) * 1024 * 1024
    except ValueError:
        return 20480 * 1024 * 1024


# ── one operation at a time ──────────────────────────────────────────────

_OP_LOCK = threading.Lock()


def _acquire_or_409(what: str) -> None:
    if not _OP_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail={"code": "package_operation_in_progress",
                                                    "message": f"another package operation is running; {what} refused"})


# ── export jobs (0056) ───────────────────────────────────────────────────

def _con() -> sqlite3.Connection:
    con = sqlite3.connect(str(_db_path()))
    con.row_factory = sqlite3.Row
    return con


def _export_job_create(job: Dict[str, Any]) -> None:
    """The row is INSERTED once, complete; every later change is an UPDATE. (A single
    upsert used for both hit NOT NULL on a partial update before ON CONFLICT could
    apply, and froze the job at `queued`.)"""
    con = _con()
    try:
        job = dict(job, updated_at=_now())
        cols = ", ".join(f'"{k}"' for k in job)
        con.execute(f'INSERT INTO narrator_package_export_jobs ({cols}) VALUES ({", ".join("?" for _ in job)})',
                    tuple(job.values()))
        con.commit()
    finally:
        con.close()


def _export_job_update(job_id: str, **fields: Any) -> None:
    con = _con()
    try:
        fields["updated_at"] = _now()
        con.execute("UPDATE narrator_package_export_jobs SET " + ", ".join(f'"{k}"=?' for k in fields) + " WHERE id=?",
                    (*fields.values(), job_id))
        con.commit()
    finally:
        con.close()


def _export_job_read(job_id: str) -> Optional[Dict[str, Any]]:
    con = _con()
    try:
        row = con.execute("SELECT * FROM narrator_package_export_jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None
    finally:
        con.close()


def _export_job_view(row: Dict[str, Any]) -> Dict[str, Any]:
    manifest = json.loads(row.get("manifest_json") or "{}")
    view = {
        "job_id": row["id"], "state": row["state"], "narrator_id": row["narrator_id"],
        "narrator_display_name": row.get("display_name") or "",
        "created_at": row["created_at"], "started_at": row.get("started_at"), "finished_at": row.get("finished_at"),
        "package_id": row.get("package_id"), "package_bytes": row.get("package_bytes"),
        "package_filename": Path(row["package_path"]).name if row.get("package_path") else None,
        "download_available": bool(row.get("package_path") and not row.get("package_removed_at")
                                   and Path(row["package_path"]).is_file()),
        "package_removed_at": row.get("package_removed_at"),
        "progress": json.loads(row.get("progress_json") or "{}"),
        "refusal": json.loads(row.get("refusal_json") or "[]"),
        "error": row.get("error"),
        # retention (§16.1): stated, never silent. No automatic removal is configured yet —
        # the period is a deliberate decision, not a default this router invents.
        "retention": {"policy": "no automatic removal (policy not yet set)",
                      "note": "Removing the server copy never removes the narrator."},
    }
    if manifest:
        view["summary"] = summary.summarize_manifest(manifest)
        view["summary"]["size_human"] = summary.human_bytes(row.get("package_bytes") or 0)
        view["advanced"] = {k: manifest.get(k) for k in (
            "package_format", "package_format_version", "package_kind", "source_commit",
            "source_schema_fingerprint", "path_column_basis", "record_counts_by_lane", "file_counts_by_lane",
            "bytes_by_lane", "installation_dependencies", "external_person_dependencies",
            "residue_not_packaged", "warnings", "payload_integrity", "verified_source_digests_checked")}
    return view


def _run_export(job_id: str, person_id: str, data_dir: Path, db_path: Path, out_dir: Path) -> None:
    import time as _time
    last = {"t": 0.0, "done": -1}

    def progress(stage: str, done=None, total=None) -> None:
        """Stages, never a percentage. Persist on every stage change, and during 'files'
        at most twice a second so a narrator with thousands of files does not turn the
        export into a thousand tiny commits."""
        now = _time.monotonic()
        stage_change = last.get("stage") != stage
        if not stage_change and stage == "files" and (now - last["t"] < 0.5) and done != total:
            return
        last.update(t=now, stage=stage, done=done)
        idx = pkg.EXPORT_STAGES.index(stage) if stage in pkg.EXPORT_STAGES else -1
        _export_job_update(job_id, progress_json=json.dumps({
            "stage": stage, "done": done, "total": total,
            "stages": [{"name": s, "state": "complete" if i < idx else ("current" if i == idx else "pending")}
                       for i, s in enumerate(pkg.EXPORT_STAGES)]}))

    try:
        _export_job_update(job_id, state="running", started_at=_now())
        res = pkg.export_narrator(person_id, data_dir=data_dir, db_path=db_path, out_dir=out_dir,
                                  repo_root=_REPO_ROOT, progress=progress)
        _export_job_update(job_id, progress_json=json.dumps({
            "stage": "complete", "done": None, "total": None,
            "stages": [{"name": s, "state": "complete"} for s in pkg.EXPORT_STAGES]}))
        _export_job_update(job_id, state="complete", finished_at=_now(),
                           package_id=res.package_id, package_path=str(res.package_path),
                           package_bytes=res.package_path.stat().st_size,
                           manifest_json=json.dumps(res.manifest, default=str))
    except pkg.ExportRefused as exc:
        _export_job_update(job_id, state="refused", finished_at=_now(),
                           refusal_json=json.dumps(exc.reasons, default=str))
    except Exception as exc:  # noqa: BLE001 — a job must always end in a durable state
        logger.exception("export job %s failed", job_id)
        try:
            _export_job_update(job_id, state="failed", finished_at=_now(),
                               error=f"{exc.__class__.__name__}: {exc}"[:2000])
        except Exception:  # noqa: BLE001
            logger.exception("export job %s could not record its failure", job_id)
    finally:
        _OP_LOCK.release()


@router.get("/preflight/{person_id}")
def preflight(person_id: str) -> Dict[str, Any]:
    """What an export WOULD contain — from the declaration, nothing built (§16.1)."""
    _require_enabled()
    if not _SAFE_ID.match(person_id or ""):
        raise HTTPException(status_code=400, detail={"code": "unsafe_person_id"})
    rep = pkg.preflight_narrator(person_id, data_dir=_data_dir(), db_path=_db_path())
    if not rep.get("ok"):
        raise HTTPException(status_code=404 if rep.get("reason") == "narrator_not_found" else 400, detail=rep)
    rep["summary"] = summary.summarize_counts(rep["record_counts_by_lane"], rep["files_by_lane"])
    rep["summary"]["size_human"] = summary.human_bytes(rep["summary"]["bytes"])
    rep["out_dir"] = str(_out_dir())
    return rep


@router.post("/export/{person_id}", status_code=202)
def start_export(person_id: str) -> Dict[str, Any]:
    _require_enabled()
    if not _SAFE_ID.match(person_id or ""):
        raise HTTPException(status_code=400, detail={"code": "unsafe_person_id"})
    data_dir, db_path, out_dir = _data_dir(), _db_path(), _out_dir()
    con = _con()
    try:
        person = con.execute("SELECT display_name FROM people WHERE id=?", (person_id,)).fetchone()
    finally:
        con.close()
    if person is None:
        raise HTTPException(status_code=404, detail={"code": "narrator_not_found", "person_id": person_id})
    _acquire_or_409("export")
    job_id = uuid.uuid4().hex
    try:
        _export_job_create({"id": job_id, "state": "queued", "narrator_id": person_id,
                            "display_name": str(person["display_name"] or ""), "data_root": str(data_dir),
                            "out_dir": str(out_dir), "requested_by": "operator-ui", "created_at": _now()})
        t = threading.Thread(target=_run_export, args=(job_id, person_id, data_dir, db_path, out_dir),
                             name=f"narrator-export-{job_id[:8]}", daemon=True)
        t.start()
    except Exception:
        _OP_LOCK.release()
        raise
    return {"job_id": job_id, "state": "queued"}


@router.get("/export/jobs")
def list_export_jobs(limit: int = 20) -> Dict[str, Any]:
    _require_enabled()
    con = _con()
    try:
        rows = con.execute("SELECT * FROM narrator_package_export_jobs ORDER BY created_at DESC LIMIT ?",
                           (max(1, min(limit, 200)),)).fetchall()
    finally:
        con.close()
    return {"jobs": [_export_job_view(dict(r)) for r in rows]}


@router.get("/export/jobs/{job_id}")
def get_export_job(job_id: str) -> Dict[str, Any]:
    _require_enabled()
    row = _export_job_read(job_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "job_not_found"})
    return _export_job_view(row)


@router.get("/export/jobs/{job_id}/download")
def download_export(job_id: str):
    """The finished file, streamed from disk (§16.1) — never assembled in memory."""
    _require_enabled()
    row = _export_job_read(job_id)
    if not row or row["state"] != "complete" or not row.get("package_path"):
        raise HTTPException(status_code=404, detail={"code": "package_not_available"})
    path = Path(row["package_path"])
    if not path.is_file():
        raise HTTPException(status_code=410, detail={"code": "package_file_gone", "path": path.name})
    return FileResponse(str(path), media_type="application/zip", filename=path.name)


@router.post("/export/jobs/{job_id}/remove-server-copy")
def remove_server_copy(job_id: str) -> Dict[str, Any]:
    """Retention: remove the finished package file from the server. The job row stays
    as history; the narrator is untouched — this deletes a file OUTSIDE DATA_DIR that
    the operator has (or chose not to) download, never narrator data (§16.1)."""
    _require_enabled()
    row = _export_job_read(job_id)
    if not row or row["state"] != "complete" or not row.get("package_path"):
        raise HTTPException(status_code=404, detail={"code": "package_not_available"})
    path = Path(row["package_path"])
    out_dir = _out_dir()
    try:
        path.resolve().relative_to(out_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=409, detail={"code": "package_outside_out_dir", "path": str(path)})
    if path.is_file():
        path.unlink()
    _export_job_update(job_id, package_removed_at=_now())
    return {"job_id": job_id, "package_removed": True, "narrator_id": row["narrator_id"],
            "note": "Removing the server copy never removes the narrator."}


# ── import: upload → two verdicts → restore ──────────────────────────────

# In-process registry of uploads. The durable truth of a RESTORE is the 0054 job
# row; this only tracks the staged file and the thread working on it.
_UPLOADS: Dict[str, Dict[str, Any]] = {}
_UPLOADS_LOCK = threading.Lock()


def _integrity_view(rep: pkg.ValidationReport) -> Dict[str, Any]:
    return {"ok": rep.ok, "problems": rep.problems,
            "structure_safe": not any("unsafe" in p or "symlink" in p or "duplicate" in p or "too large" in p for p in rep.problems),
            "bagit_valid": not any(p.startswith("bagit validation failed") for p in rep.problems),
            "manifest_readable": rep.manifest is not None,
            "payload_files": rep.payload_files, "payload_bytes": rep.payload_bytes}


def _readiness_view(rep: pkg.DryRunReport) -> Dict[str, Any]:
    return {"ready": rep.ready, "verdict": rep.verdict, "reasons": rep.reasons,
            "collisions": rep.collisions, "unsupported_schema": rep.unsupported_schema,
            "missing_dependencies": rep.missing_dependencies, "warnings": rep.warnings,
            "records_by_lane": rep.records_by_lane, "files_by_lane": rep.files_by_lane, "total_bytes": rep.total_bytes}


IMPORT_STEPS = ("Choose package", "Upload", "Check package", "Check restore readiness", "Review", "Restore", "Verify")


def _stepper(u: Dict[str, Any]) -> Dict[str, Any]:
    """Completed / current / pending / failed per step, decided HERE from the upload's
    state so an operator who leaves and returns is re-oriented by the server (§16.1)."""
    state = u.get("state")
    integ_ok = bool((u.get("integrity") or {}).get("ok"))
    ready = bool((u.get("readiness") or {}).get("ready"))
    if state == "integrity_failed":
        cur, failed = 2, True
    elif state == "checked":
        cur, failed = (4, False) if ready else (3, True)
    elif state == "restoring":
        cur, failed = 5, False
    elif state == "restored":
        cur, failed = 7, False          # everything complete
    elif state in ("refused", "failed"):
        cur, failed = 5, True
    else:
        cur, failed = 1, False
    steps = []
    for i, name in enumerate(IMPORT_STEPS):
        if i < cur:
            st = "complete"
        elif i == cur:
            st = "failed" if failed else "current"
        else:
            st = "pending"
        steps.append({"n": i + 1, "name": name, "state": st})
    return {"steps": steps, "current": min(cur + 1, len(IMPORT_STEPS)), "total": len(IMPORT_STEPS),
            "integrity_ok": integ_ok, "ready": ready}


def _upload_view(u: Dict[str, Any]) -> Dict[str, Any]:
    v = {k: u.get(k) for k in ("upload_id", "state", "filename", "bytes", "received_at", "integrity", "readiness",
                               "restore_job_id", "restore_result", "error", "narrator_id", "narrator_display_name")}
    v["stepper"] = _stepper(u)
    if u.get("manifest"):
        v["summary"] = summary.summarize_manifest(u["manifest"])
        v["summary"]["size_human"] = summary.human_bytes(u.get("bytes") or 0)
        v["advanced"] = {k: u["manifest"].get(k) for k in (
            "package_format", "package_format_version", "package_kind", "source_commit", "source_schema_fingerprint",
            "created_at", "record_counts_by_lane", "file_counts_by_lane", "bytes_by_lane",
            "installation_dependencies", "external_person_dependencies", "warnings")}
    return v


@router.post("/import/upload", status_code=201)
async def upload_package(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Stream the ZIP to staging OUTSIDE DATA_DIR, then answer with TWO verdicts:
    package integrity, and — only if that passes — Lorevox restore readiness."""
    _require_enabled()
    staging = _staging_dir()
    upload_id = uuid.uuid4().hex
    dest_dir = staging / upload_id
    dest_dir.mkdir(parents=True, exist_ok=False)
    dest = dest_dir / "package.lorevox.zip"
    cap = _max_upload_bytes()
    n = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = await file.read(64 * 1024)
                if not chunk:
                    break
                n += len(chunk)
                if n > cap:
                    raise HTTPException(status_code=413, detail={"code": "package_too_large", "max_bytes": cap})
                out.write(chunk)
    except HTTPException:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail={"code": "upload_failed", "error": exc.__class__.__name__})
    integrity = pkg.validate_package(dest)
    u: Dict[str, Any] = {"upload_id": upload_id, "state": "checked", "path": str(dest),
                         "filename": file.filename or "package.lorevox.zip", "bytes": n, "received_at": _now(),
                         "integrity": _integrity_view(integrity), "manifest": integrity.manifest,
                         "readiness": None, "restore_job_id": None, "restore_result": None, "error": None,
                         "narrator_id": (integrity.manifest or {}).get("narrator_id"),
                         "narrator_display_name": (integrity.manifest or {}).get("narrator_display_name")}
    if integrity.ok:
        readiness = pkg.dry_run_restore(dest, data_dir=_data_dir(), db_path=_db_path())
        u["readiness"] = _readiness_view(readiness)
    else:
        u["state"] = "integrity_failed"
    with _UPLOADS_LOCK:
        _UPLOADS[upload_id] = u
    return _upload_view(u)


@router.get("/import/{upload_id}")
def get_upload(upload_id: str) -> Dict[str, Any]:
    _require_enabled()
    with _UPLOADS_LOCK:
        u = _UPLOADS.get(upload_id)
    if not u:
        raise HTTPException(status_code=404, detail={"code": "upload_not_found"})
    view = _upload_view(u)
    if u.get("restore_job_id"):
        con = _con()
        try:
            row = con.execute("SELECT state, error, counts_json FROM narrator_package_jobs WHERE id=?",
                              (u["restore_job_id"],)).fetchone()
        finally:
            con.close()
        if row:
            view["restore_job"] = {"job_id": u["restore_job_id"], "state": row["state"], "error": row["error"],
                                   "counts": json.loads(row["counts_json"] or "{}")}
    return view


def _run_restore(upload_id: str, path: Path, data_dir: Path, db_path: Path) -> None:
    try:
        res = pkg.restore_narrator(path, data_dir=data_dir, db_path=db_path, requested_by="operator-ui")
        with _UPLOADS_LOCK:
            u = _UPLOADS[upload_id]
            u.update(state="restored", restore_job_id=res.job_id,
                     restore_result={"narrator_id": res.narrator_id, "package_id": res.package_id,
                                     "records_inserted": res.records_inserted, "files_created": len(res.files_created)})
        shutil.rmtree(path.parent, ignore_errors=True)       # staging is not narrator state
    except pkg.RestoreRefused as exc:
        with _UPLOADS_LOCK:
            u = _UPLOADS[upload_id]
            u.update(state="refused", readiness=_readiness_view(exc.report))
    except Exception as exc:  # noqa: BLE001
        logger.exception("restore of upload %s failed", upload_id)
        with _UPLOADS_LOCK:
            u = _UPLOADS[upload_id]
            u.update(state="failed", error=f"{exc.__class__.__name__}: {exc}"[:2000])
            m = re.search(r"job ([0-9a-f]{32})", str(exc))
            if m:
                u["restore_job_id"] = m.group(1)
    finally:
        _OP_LOCK.release()


@router.post("/import/{upload_id}/restore", status_code=202)
def start_restore(upload_id: str) -> Dict[str, Any]:
    """Only when readiness is READY — re-checked here, and again inside the service.
    There is no parameter that overrides a refusal."""
    _require_enabled()
    with _UPLOADS_LOCK:
        u = _UPLOADS.get(upload_id)
    if not u:
        raise HTTPException(status_code=404, detail={"code": "upload_not_found"})
    if u["state"] != "checked" or not u.get("integrity", {}).get("ok"):
        raise HTTPException(status_code=409, detail={"code": "package_not_restorable", "state": u["state"]})
    path = Path(u["path"])
    if not path.is_file():
        raise HTTPException(status_code=410, detail={"code": "staged_package_gone"})
    readiness = pkg.dry_run_restore(path, data_dir=_data_dir(), db_path=_db_path())
    with _UPLOADS_LOCK:
        u["readiness"] = _readiness_view(readiness)
    if not readiness.ready:
        raise HTTPException(status_code=409, detail={"code": "restore_refused", "readiness": _readiness_view(readiness)})
    _acquire_or_409("restore")
    with _UPLOADS_LOCK:
        u["state"] = "restoring"
    try:
        t = threading.Thread(target=_run_restore, args=(upload_id, path, _data_dir(), _db_path()),
                             name=f"narrator-restore-{upload_id[:8]}", daemon=True)
        t.start()
    except Exception:
        _OP_LOCK.release()
        with _UPLOADS_LOCK:
            u["state"] = "checked"
        raise
    return {"upload_id": upload_id, "state": "restoring"}


@router.post("/import/{upload_id}/discard")
def discard_upload(upload_id: str) -> Dict[str, Any]:
    """Discard a STAGED upload that was never restored. This removes a file in the
    staging area outside DATA_DIR — it is not narrator state and never was (§16.1)."""
    _require_enabled()
    with _UPLOADS_LOCK:
        u = _UPLOADS.get(upload_id)
        if not u:
            raise HTTPException(status_code=404, detail={"code": "upload_not_found"})
        if u["state"] in ("restoring",):
            raise HTTPException(status_code=409, detail={"code": "restore_in_progress"})
        _UPLOADS.pop(upload_id, None)
    shutil.rmtree(Path(u["path"]).parent, ignore_errors=True)
    return {"upload_id": upload_id, "discarded": True}


# ── restore jobs and recovery ────────────────────────────────────────────

@router.get("/restore/jobs")
def list_restore_jobs(limit: int = 20) -> Dict[str, Any]:
    _require_enabled()
    con = _con()
    try:
        if "narrator_package_jobs" not in {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
            return {"jobs": [], "incomplete": 0}
        rows = con.execute("SELECT id, state, narrator_id, package_id, created_at, updated_at, error, counts_json "
                           "FROM narrator_package_jobs ORDER BY created_at DESC LIMIT ?",
                           (max(1, min(limit, 200)),)).fetchall()
    finally:
        con.close()
    jobs = [dict(r) for r in rows]
    for j in jobs:
        j["counts"] = json.loads(j.pop("counts_json") or "{}")
    return {"jobs": jobs, "incomplete": sum(1 for j in jobs if j["state"] not in ("complete", "failed"))}


@router.post("/recover")
def recover(job_id: Optional[str] = None) -> Dict[str, Any]:
    """Finish or undo interrupted restore jobs — the service's rules, nothing else (§33.1)."""
    _require_enabled()
    _acquire_or_409("recover")
    try:
        reports = pkg.recover_restore_jobs(data_dir=_data_dir(), db_path=_db_path(), job_id=job_id)
    finally:
        _OP_LOCK.release()
    return {"reports": reports, "refused": sum(1 for r in reports if r.get("action") == "refused")}
