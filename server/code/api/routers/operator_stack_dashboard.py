"""WO-OPERATOR-RESOURCE-DASHBOARD-01 — operator stack-dashboard router.

Five endpoints, all gated behind `HORNELORE_OPERATOR_STACK_DASHBOARD=1`:

  GET  /api/operator/stack-dashboard/summary
       Live snapshot — services, system, gpu, capture, archive, eval,
       warnings. Cheap (~50ms when GPU cached, ~200ms cold). Polled at
       5s while Bug Panel is open, 30s while closed.

  GET  /api/operator/stack-dashboard/history?minutes=10
       Recent JSONL rows from the resource-logger script — Phase 1 just
       reads the latest.jsonl file the logger writes. If logger isn't
       running, returns an empty list with `available=false`.

  GET  /api/operator/stack-dashboard/log-tail?source=api|ui|tts|monitor&lines=80
       Tail of one of the runtime logs. Hard-bounded line count so a
       runaway client can't ask for the whole 50MB api.log.

  POST /api/operator/stack-dashboard/mark
       Operator marker. {label: "..."}. Bounded length, rate-limited.

  POST /api/operator/stack-dashboard/ui-heartbeat
       Frontend pushes camera/mic/TTS state here every ~5s. Backend
       caches with TTL — stale heartbeats surface as `unknown`, not
       `active`. Pre-work review #4: this is sender-trusted; a closed
       UI tab will age out within 30s.

Pre-work review notes:
  - Default-OFF gate returns 404 (not 403) — same posture as the eval
    harness router, so the surface doesn't advertise itself.
  - log-tail accepts a fixed enum of sources to prevent path traversal
    (no arbitrary filenames).
  - Marker rate-limit is naive (1/sec per process, not per IP) — adequate
    for operator-only single-instance Hornelore. If this ever ships to
    a multi-tenant context, swap for slowapi.
  - ui-heartbeat payload size is capped via FastAPI's default body limit;
    additional length checks happen inside stack_monitor.record_ui_heartbeat.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from ..services import stack_monitor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/operator/stack-dashboard", tags=["operator", "dashboard"])


# Repo root for log-tail / history.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_RUNTIME_LOGS = _REPO_ROOT / ".runtime" / "logs"
_RUNTIME_MONITOR = _REPO_ROOT / ".runtime" / "monitor"

# log-tail source enum → file path. Pre-work review #6: don't let an
# arbitrary `source` query param become a path-traversal vector.
_LOG_SOURCES: Dict[str, Path] = {
    "api": _RUNTIME_LOGS / "api.log",
    "ui": _RUNTIME_LOGS / "ui.log",
    "tts": _RUNTIME_LOGS / "tts.log",
    "monitor": _RUNTIME_MONITOR / "latest.jsonl",
}

# Marker rate-limit (1 marker per second across all worker threads).
# Post-build review #1: read/write of _last_mark_time MUST be locked —
# uvicorn can use threadpool execution for sync route handlers, and two
# concurrent POST /mark requests racing this float can both pass the
# `now - _last_mark_time >= _MARK_RATE_LIMIT_SEC` check.
_MARK_RATE_LIMIT_SEC = 1.0
_mark_rate_lock = threading.Lock()
_last_mark_time: float = 0.0


# ── Backend gate ───────────────────────────────────────────────────────────

def _operator_stack_dashboard_enabled() -> bool:
    """Default-OFF gate. Enable with `HORNELORE_OPERATOR_STACK_DASHBOARD=1`."""
    return os.getenv("HORNELORE_OPERATOR_STACK_DASHBOARD", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _require_enabled() -> None:
    """Raise 404 (not 403) when the backend gate is off so an external
    probe can't distinguish 'endpoint exists but you can't have it' from
    'endpoint doesn't exist'."""
    if not _operator_stack_dashboard_enabled():
        raise HTTPException(status_code=404, detail="Not found")


# ── Pydantic models ────────────────────────────────────────────────────────

class MarkRequest(BaseModel):
    label: str = Field(..., max_length=200, min_length=1)
    source: Optional[str] = Field(default="operator", max_length=32)


class UiHeartbeatCamera(BaseModel):
    active: bool = False
    width: Optional[int] = None
    height: Optional[int] = None
    track_state: Optional[str] = Field(default=None, max_length=32)


class UiHeartbeatMic(BaseModel):
    active: bool = False
    rms_level: Optional[float] = None
    track_state: Optional[str] = Field(default=None, max_length=32)


class UiHeartbeatTts(BaseModel):
    speaking: bool = False
    queue_length: Optional[int] = None


class UiHeartbeatArchive(BaseModel):
    current_session_id: Optional[str] = Field(default=None, max_length=64)


class UiHeartbeat(BaseModel):
    person_id: Optional[str] = Field(default=None, max_length=64)
    session_id: Optional[str] = Field(default=None, max_length=64)
    camera: Optional[UiHeartbeatCamera] = None
    microphone: Optional[UiHeartbeatMic] = None
    tts: Optional[UiHeartbeatTts] = None
    archive: Optional[UiHeartbeatArchive] = None


# ── Routes ─────────────────────────────────────────────────────────────────

@router.get("/summary")
def summary(person_id: Optional[str] = Query(default=None, max_length=64)):
    """Live dashboard snapshot. ~50ms when caches are warm, ~200ms cold."""
    _require_enabled()
    try:
        return stack_monitor.build_summary(person_id=person_id)
    except Exception as e:  # type: ignore[unreachable]
        # Diagnostic infrastructure must never 500 — return a degraded
        # payload that the UI can still render.
        logger.exception("[stack-dashboard] summary failed")
        return {
            "generated_at": stack_monitor._utc_now(),
            "status": "fail",
            "_error": f"summary build failed: {e}",
            "warnings": [{"category": "dashboard", "message": str(e)}],
        }


@router.get("/system-status")
def system_status(person_id: Optional[str] = Query(default=None, max_length=64)):
    """WO-OPERATOR-DASHBOARD-MERGE-01 — compatibility alias for the unified
    operator cockpit. The Bug Panel eval-harness merge fetches this so the
    cockpit can surface system health alongside eval status. Returns the
    same payload as /summary; kept as a separate route so the cockpit can
    swap endpoints later without churn."""
    _require_enabled()
    try:
        return stack_monitor.build_summary(person_id=person_id)
    except Exception as e:
        # Diagnostic infrastructure must never 500 — return a degraded
        # payload that the UI can still render.
        logger.exception("[stack-dashboard] summary failed")
        return {
            "generated_at": stack_monitor._utc_now(),
            "status": "fail",
            "_error": f"summary build failed: {e}",
            "warnings": [{"category": "dashboard", "message": str(e)}],
        }


@router.get("/history")
def history(minutes: int = Query(default=10, ge=1, le=120)):
    """Read tail of `.runtime/monitor/latest.jsonl` (the resource-logger
    script's output). Returns empty list with `available=false` if the
    logger isn't running."""
    _require_enabled()
    latest = _RUNTIME_MONITOR / "latest.jsonl"
    if not latest.exists():
        return {"available": False, "rows": [], "minutes_requested": minutes}

    cutoff_ts = time.time() - (minutes * 60)
    rows: List[Dict[str, Any]] = []
    try:
        # Read from the tail. JSONL lines are typically <2KB each, so
        # tailing the last 100KB reliably gets ~minutes worth of data.
        with open(latest, "r", encoding="utf-8", errors="replace") as f:
            f.seek(0, 2)  # end
            size = f.tell()
            tail_bytes = min(size, 256 * 1024)
            f.seek(size - tail_bytes)
            # Skip partial first line
            if size > tail_bytes:
                f.readline()
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    import json as _json
                    obj = _json.loads(ln)
                except Exception:
                    continue
                # Filter by `ts` within window if present
                row_ts_str = obj.get("ts")
                if row_ts_str:
                    try:
                        from datetime import datetime
                        row_dt = datetime.strptime(row_ts_str.replace("Z", ""), "%Y-%m-%dT%H:%M:%S")
                        if row_dt.timestamp() < cutoff_ts:
                            continue
                    except Exception:
                        pass
                rows.append(obj)
    except Exception as e:
        logger.warning("[stack-dashboard] history read failed: %s", e)
        return {"available": False, "rows": [], "error": str(e)[:200]}

    return {"available": True, "rows": rows, "minutes_requested": minutes,
            "row_count": len(rows)}


@router.get("/log-tail")
def log_tail(
    source: str = Query(default="api"),
    lines: int = Query(default=80, ge=1, le=500),
):
    """Return the last N lines of one of the runtime logs. `source`
    must be one of api/ui/tts/monitor — pre-work review #6: enum-only
    to prevent path traversal."""
    _require_enabled()
    if source not in _LOG_SOURCES:
        raise HTTPException(
            status_code=400,
            detail=f"source must be one of: {', '.join(sorted(_LOG_SOURCES.keys()))}",
        )
    path = _LOG_SOURCES[source]
    if not path.exists():
        return {"available": False, "source": source, "lines": []}

    # Read tail efficiently — seek to end and walk backward.
    # Post-build review MEDIUM #2: this assumes log files end with a
    # trailing newline (the standard for line-buffered loggers like
    # uvicorn / Python logging / appended JSONL writers — which all the
    # _LOG_SOURCES paths are). The `lines + 1` reads one extra newline
    # so we can safely discard a partial first line. If a file ever lands
    # without a trailing newline AND the last line is exactly at a block
    # boundary, we may return one fewer line than requested; never more.
    # `splitlines()[-lines:]` then bounds the result so we can't over-return.
    out: List[str] = []
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            end = f.tell()
            block_size = 4096
            data = b""
            while end > 0 and data.count(b"\n") < lines + 1:
                read = min(block_size, end)
                end -= read
                f.seek(end)
                data = f.read(read) + data
            text = data.decode("utf-8", errors="replace")
            all_lines = text.splitlines()
            out = all_lines[-lines:]
    except Exception as e:
        return {"available": False, "source": source, "error": str(e)[:200], "lines": []}

    return {
        "available": True,
        "source": source,
        "path": str(path.relative_to(_REPO_ROOT)) if path.is_relative_to(_REPO_ROOT) else str(path),
        "line_count": len(out),
        "lines": out,
    }


@router.post("/mark")
def mark(request: MarkRequest):
    """Append an operator marker to the in-process buffer. Rate-limited
    1/sec across all uvicorn worker threads (post-build review #1: the
    earlier lock-free version could race two concurrent POSTs through
    the timestamp check). Pre-work review #6: bounds + cap."""
    _require_enabled()
    global _last_mark_time
    now = time.time()
    with _mark_rate_lock:
        if (now - _last_mark_time) < _MARK_RATE_LIMIT_SEC:
            raise HTTPException(status_code=429, detail="Too many marks; wait 1 second")
        _last_mark_time = now
    return stack_monitor.add_marker(request.label, source=request.source or "operator")


@router.get("/markers")
def list_markers_endpoint(limit: int = Query(default=50, ge=1, le=200)):
    """Return recent operator markers."""
    _require_enabled()
    return {"markers": stack_monitor.list_markers(limit=limit)}


@router.post("/ui-heartbeat")
def ui_heartbeat(payload: UiHeartbeat):
    """Frontend reports browser-only camera/mic/TTS state. Backend
    caches with TTL — stale heartbeats from closed tabs surface as
    `unknown` automatically (pre-work review #4)."""
    _require_enabled()
    # Coerce the validated pydantic model into the dict shape the
    # service module expects.
    raw: Dict[str, Any] = {
        "person_id": payload.person_id,
        "session_id": payload.session_id,
    }
    if payload.camera is not None:
        raw["camera"] = payload.camera.model_dump()
    if payload.microphone is not None:
        raw["microphone"] = payload.microphone.model_dump()
    if payload.tts is not None:
        raw["tts"] = payload.tts.model_dump()
    if payload.archive is not None:
        raw["archive"] = payload.archive.model_dump()
    entry = stack_monitor.record_ui_heartbeat(raw)
    return {"ok": True, "ttl_sec": stack_monitor._UI_HEARTBEAT_TTL_SEC,
            "person_id": entry.get("person_id"),
            "session_id": entry.get("session_id")}


# ── KV / VRAM cleanup endpoint (WO-OPS-STRESS-TELEMETRY-KV-01 Phase A) ────

def _operator_clear_kv_enabled() -> bool:
    """Default-OFF gate. Compounds with the dashboard gate above.
    Enable BOTH `HORNELORE_OPERATOR_STACK_DASHBOARD=1` AND
    `HORNELORE_OPERATOR_CLEAR_KV=1`. Two gates because clear-kv mutates
    runtime state (vs. read-only summary/history) — opt-in only."""
    if not _operator_stack_dashboard_enabled():
        return False
    return os.getenv("HORNELORE_OPERATOR_CLEAR_KV", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


@router.post("/clear-kv")
def clear_kv():
    """Force a CUDA cleanup pass. Returns before/after VRAM stats so the
    rehearsal harness (WO-OPS-STRESS-TELEMETRY-KV-01 Phase B) can observe
    KV-clear effectiveness between voice loops in the stress run.

    Sequence:
      1. torch.cuda.synchronize() — flush in-flight ops so we measure clean
      2. snapshot VRAM via collect_gpu(force=True) (bypass 4s cache)
      3. gc.collect() — Python objects holding tensor refs
      4. torch.cuda.empty_cache() — release cached blocks back to driver
      5. torch.cuda.ipc_collect() — clean inter-process tensor refs
      6. torch.cuda.synchronize() — ensure cleanup ops finish before measure
      7. snapshot VRAM again
      8. return delta

    Safety:
      - Both env gates must be ON (HORNELORE_OPERATOR_STACK_DASHBOARD +
        HORNELORE_OPERATOR_CLEAR_KV) — endpoint returns 404 otherwise.
      - 30s hard timeout — if any cuda op hangs longer than that, we
        return what we have rather than blocking the harness indefinitely.
      - Wrapped in try/except — failures return 200 with diagnostic
        payload, never 500. Diagnostic infrastructure must never crash
        the running stack.
      - Operates on whichever CUDA device is currently active. Hornelore
        is single-GPU; multi-GPU isn't in scope.
    """
    if not _operator_clear_kv_enabled():
        raise HTTPException(status_code=404, detail="Not found")

    import gc as _gc
    started_at = time.time()
    elapsed_ms_cap = 30_000

    result: Dict[str, Any] = {
        "ok": False,
        "before": None,
        "after": None,
        "freed_mb": None,
        "elapsed_ms": 0,
        "gc_collected_objects": 0,
        "ops_completed": [],
        "errors": [],
    }

    # Try to import torch — gracefully degrade if unavailable
    try:
        import torch  # type: ignore
        cuda_available = torch.cuda.is_available()
    except Exception as e:
        logger.warning("[stack-dashboard][clear-kv] torch import failed: %s", e)
        result["errors"].append(f"torch_import: {str(e)[:200]}")
        result["elapsed_ms"] = int((time.time() - started_at) * 1000)
        return result

    if not cuda_available:
        result["errors"].append("cuda_not_available")
        result["elapsed_ms"] = int((time.time() - started_at) * 1000)
        return result

    # Step 1: synchronize before measuring (flush in-flight)
    try:
        torch.cuda.synchronize()
        result["ops_completed"].append("synchronize_pre")
    except Exception as e:
        result["errors"].append(f"synchronize_pre: {str(e)[:200]}")

    # Step 2: snapshot before
    try:
        before = stack_monitor.collect_gpu(force=True)
        result["before"] = {
            "vram_used_mb": before.get("vram_used_mb"),
            "vram_free_mb": before.get("vram_free_mb"),
            "vram_total_mb": before.get("vram_total_mb"),
            "util_percent": before.get("util_percent"),
            "temperature_c": before.get("temperature_c"),
        }
    except Exception as e:
        result["errors"].append(f"snapshot_pre: {str(e)[:200]}")

    # Step 3: gc.collect()
    try:
        gc_collected = _gc.collect()
        result["gc_collected_objects"] = gc_collected
        result["ops_completed"].append("gc_collect")
    except Exception as e:
        result["errors"].append(f"gc_collect: {str(e)[:200]}")

    # Bail early if we've blown the time cap (paranoid)
    if (time.time() - started_at) * 1000 > elapsed_ms_cap:
        result["errors"].append("elapsed_ms_cap_hit_pre_cuda_ops")
        result["elapsed_ms"] = int((time.time() - started_at) * 1000)
        return result

    # Step 4: torch.cuda.empty_cache()
    try:
        torch.cuda.empty_cache()
        result["ops_completed"].append("empty_cache")
    except Exception as e:
        result["errors"].append(f"empty_cache: {str(e)[:200]}")

    # Step 5: torch.cuda.ipc_collect() — best-effort, may not exist on all torch versions
    try:
        if hasattr(torch.cuda, "ipc_collect"):
            torch.cuda.ipc_collect()
            result["ops_completed"].append("ipc_collect")
        else:
            result["ops_completed"].append("ipc_collect_skipped_no_attr")
    except Exception as e:
        result["errors"].append(f"ipc_collect: {str(e)[:200]}")

    # Step 6: synchronize after
    try:
        torch.cuda.synchronize()
        result["ops_completed"].append("synchronize_post")
    except Exception as e:
        result["errors"].append(f"synchronize_post: {str(e)[:200]}")

    # Step 7: snapshot after
    try:
        after = stack_monitor.collect_gpu(force=True)
        result["after"] = {
            "vram_used_mb": after.get("vram_used_mb"),
            "vram_free_mb": after.get("vram_free_mb"),
            "vram_total_mb": after.get("vram_total_mb"),
            "util_percent": after.get("util_percent"),
            "temperature_c": after.get("temperature_c"),
        }
    except Exception as e:
        result["errors"].append(f"snapshot_post: {str(e)[:200]}")

    # Compute freed_mb
    try:
        bu = (result.get("before") or {}).get("vram_used_mb")
        au = (result.get("after") or {}).get("vram_used_mb")
        if isinstance(bu, (int, float)) and isinstance(au, (int, float)):
            result["freed_mb"] = round(bu - au, 1)
    except Exception:
        pass

    result["elapsed_ms"] = int((time.time() - started_at) * 1000)
    result["ok"] = (
        len(result["errors"]) == 0
        and "empty_cache" in result["ops_completed"]
        and result["before"] is not None
        and result["after"] is not None
    )

    # Single-line summary log so post-run grep can correlate with rest
    # of the stress run. Match `[stack-dashboard][clear-kv]` for the
    # telemetry harness aggregator.
    logger.info(
        "[stack-dashboard][clear-kv] freed_mb=%s elapsed_ms=%s gc=%s ok=%s ops=%s errors=%s",
        result.get("freed_mb"),
        result.get("elapsed_ms"),
        result.get("gc_collected_objects"),
        result.get("ok"),
        len(result.get("ops_completed", [])),
        len(result.get("errors", [])),
    )

    return result
