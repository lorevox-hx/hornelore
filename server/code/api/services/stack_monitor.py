"""WO-OPERATOR-RESOURCE-DASHBOARD-01 — stack monitor service module.

Read-only collectors for the operator stack dashboard. Imported by
`routers/operator_stack_dashboard.py` (live HTTP) and by the standalone
`scripts/monitor/stack_resource_logger.py` (long-running JSONL writer).

Every collector is wrapped in a try/except — a failed nvidia-smi or
psutil call returns a `{"status": "unavailable", "error": "..."}` block,
never raises into the calling endpoint. The dashboard is diagnostic
infrastructure: it must never become a reason the API returns 500.

Cost discipline:
  - psutil cpu/ram/disk/io snapshots are sub-millisecond
  - nvidia-smi runs in a subprocess with a hard 2-second timeout, output
    cached for 4 seconds (so 5-second poll cadence does at most one
    real subprocess call per cycle)
  - api.log scans cache by mtime — only re-tail the tail when the file
    has actually grown since last call
  - service pings use connect-only sockets (no body, 1.5s timeout)

Design notes flagged in pre-work review:
  - UI port assumption corrected: probe `/ui/hornelore1.0.html` on the
    SAME origin as the API (FastAPI mounts /ui), not a separate :8082
  - GPU subprocess is bounded; failure → `unavailable`, never red
  - OOM/`error_ConnectionError` log scans cache by `(path, mtime, size)`
  - UI-heartbeat camera/mic cache has a 30s TTL — stale heartbeat
    surfaces as `unknown` not `active`
  - Status-color thresholds are documented inline in `_classify_*`

This module is import-safe (no FastAPI deps). Routers compose its output.
"""
from __future__ import annotations

import json
import logging
import os
import re
import socket
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Repo-rooted paths ──────────────────────────────────────────────────────
# This module lives at server/code/api/services/, so REPO_ROOT is five
# parents up. Mirror of operator_eval_harness.py path math (which is four
# parents up from routers/) — be careful: services/ adds one more.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_REPORTS_DIR = _REPO_ROOT / "docs" / "reports"
_RUNTIME_LOGS = _REPO_ROOT / ".runtime" / "logs"
_RUNTIME_MONITOR = _REPO_ROOT / ".runtime" / "monitor"
_API_LOG = _RUNTIME_LOGS / "api.log"

# DATA_DIR for archive-write freshness probes — env-driven so it matches
# whatever the running stack writes to.
_DATA_DIR = Path(os.getenv("DATA_DIR", "/mnt/c/hornelore_data"))
_MEMORY_ARCHIVE = _DATA_DIR / "memory" / "archive"
_UPLOADS_DIR = Path(os.getenv("UPLOADS_DIR", str(_DATA_DIR / "uploads")))

# ── Status-color thresholds (operator-tunable; documented for transparency) ─
# Pre-work review #9: spec said "amber: nearing limit" without numbers.
# These are conservative defaults; bump in env if your box is comfortable
# running hot.
_CPU_AMBER_PCT = float(os.getenv("DASH_CPU_AMBER", "80"))
_CPU_RED_PCT = float(os.getenv("DASH_CPU_RED", "95"))
_RAM_AMBER_PCT = float(os.getenv("DASH_RAM_AMBER", "80"))
_RAM_RED_PCT = float(os.getenv("DASH_RAM_RED", "95"))
_DISK_AMBER_PCT = float(os.getenv("DASH_DISK_AMBER", "85"))
_DISK_RED_PCT = float(os.getenv("DASH_DISK_RED", "95"))
_VRAM_FREE_AMBER_MB = float(os.getenv("DASH_VRAM_FREE_AMBER_MB", "2048"))
_VRAM_FREE_RED_MB = float(os.getenv("DASH_VRAM_FREE_RED_MB", "512"))
_GPU_TEMP_AMBER_C = float(os.getenv("DASH_GPU_TEMP_AMBER", "82"))
_GPU_TEMP_RED_C = float(os.getenv("DASH_GPU_TEMP_RED", "92"))
_SVC_LATENCY_AMBER_MS = float(os.getenv("DASH_SVC_LATENCY_AMBER_MS", "2000"))
_SVC_LATENCY_RED_MS = float(os.getenv("DASH_SVC_LATENCY_RED_MS", "10000"))

# Capture-state TTL: if the UI hasn't sent a heartbeat in this many
# seconds, the camera/mic card flips to `unknown` rather than `active`.
# Pre-work review #4: stale heartbeat must not pretend the camera is on.
_UI_HEARTBEAT_TTL_SEC = int(os.getenv("DASH_UI_HEARTBEAT_TTL_SEC", "30"))

# Archive-write staleness: if no new file in this many seconds while the
# UI claims a session is active, the archive card goes amber.
_ARCHIVE_STALE_AMBER_SEC = int(os.getenv("DASH_ARCHIVE_STALE_AMBER_SEC", "60"))
_ARCHIVE_STALE_RED_SEC = int(os.getenv("DASH_ARCHIVE_STALE_RED_SEC", "300"))

# Eval-progress staleness: api.log silence during an active eval.
_EVAL_STALE_AMBER_SEC = int(os.getenv("DASH_EVAL_STALE_AMBER_SEC", "30"))
_EVAL_STALE_RED_SEC = int(os.getenv("DASH_EVAL_STALE_RED_SEC", "120"))

# ── Caches ────────────────────────────────────────────────────────────────
_GPU_CACHE_TTL_SEC = 4.0
_LOG_SCAN_CACHE_TTL_SEC = 4.0
_gpu_cache_lock = threading.Lock()
_gpu_cache: Dict[str, Any] = {"ts": 0.0, "value": None}

_log_scan_lock = threading.Lock()
_log_scan_cache: Dict[str, Any] = {
    "mtime": 0.0,
    "size": 0,
    "ts": 0.0,
    "oom_count": 0,
    "last_oom_at": None,
    "connection_refused_count": 0,
    "last_connection_refused_at": None,
    "current_extract_at": None,
    "llm_warm_at": None,
}

# UI-heartbeat in-process store. Keyed by (person_id, session_id) so two
# operator tabs don't fight; surfaces as `unknown` past TTL.
_ui_heartbeat_lock = threading.Lock()
_ui_heartbeat_store: Dict[str, Dict[str, Any]] = {}

# Operator markers (POST /mark) — capped buffer so a runaway client can't
# grow this unbounded.
_MARKERS_MAX = 200
_MARKER_LABEL_MAX = 200
_markers_lock = threading.Lock()
_markers: List[Dict[str, Any]] = []


# ────────────────────────────────────────────────────────────────────────
# Time helpers
# ────────────────────────────────────────────────────────────────────────

def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _age_seconds(ts: Optional[float]) -> Optional[float]:
    if ts is None:
        return None
    try:
        return max(0.0, time.time() - float(ts))
    except (TypeError, ValueError):
        return None


# ────────────────────────────────────────────────────────────────────────
# psutil-backed system collectors
# ────────────────────────────────────────────────────────────────────────

def collect_system() -> Dict[str, Any]:
    """CPU / RAM / disk / I/O snapshot. Sub-millisecond on healthy box."""
    try:
        import psutil  # type: ignore
    except Exception as e:
        return {"status": "unavailable", "error": f"psutil import failed: {e}"}

    out: Dict[str, Any] = {"status": "ok"}

    # CPU — interval=None returns immediate value; first call after import
    # may return 0.0, that's fine for a 5-second poll cadence.
    try:
        out["cpu_percent"] = round(float(psutil.cpu_percent(interval=None)), 1)
        out["cpu_count"] = psutil.cpu_count(logical=True)
    except Exception as e:
        out["cpu_percent"] = None
        out["cpu_error"] = str(e)

    try:
        vm = psutil.virtual_memory()
        out["memory_percent"] = round(float(vm.percent), 1)
        out["memory_used_gb"] = round(vm.used / (1024 ** 3), 2)
        out["memory_total_gb"] = round(vm.total / (1024 ** 3), 2)
        out["memory_available_gb"] = round(vm.available / (1024 ** 3), 2)
    except Exception as e:
        out["memory_error"] = str(e)

    # Disk — probe the partition that DATA_DIR lives on (fall back to /).
    try:
        target = str(_DATA_DIR) if _DATA_DIR.exists() else "/"
        du = psutil.disk_usage(target)
        out["disk_path"] = target
        out["disk_percent"] = round(float(du.percent), 1)
        out["disk_used_gb"] = round(du.used / (1024 ** 3), 1)
        out["disk_free_gb"] = round(du.free / (1024 ** 3), 1)
        out["disk_total_gb"] = round(du.total / (1024 ** 3), 1)
    except Exception as e:
        out["disk_error"] = str(e)

    # I/O rate — system-wide. Pre-work review #7: WSL2 /mnt/c accounting
    # is host-blended; we surface this as system-wide I/O, not "WSL I/O".
    try:
        io = psutil.disk_io_counters()
        if io is not None:
            out["io_read_bytes"] = int(io.read_bytes)
            out["io_write_bytes"] = int(io.write_bytes)
    except Exception as e:
        out["io_error"] = str(e)

    try:
        out["process_count"] = len(psutil.pids())
    except Exception:
        pass

    return out


def _classify_system(sys_block: Dict[str, Any]) -> str:
    """Roll up CPU/RAM/disk into a single status."""
    if sys_block.get("status") == "unavailable":
        return "unavailable"
    statuses: List[str] = []
    cpu = sys_block.get("cpu_percent")
    ram = sys_block.get("memory_percent")
    disk = sys_block.get("disk_percent")
    if isinstance(cpu, (int, float)):
        if cpu >= _CPU_RED_PCT:
            statuses.append("fail")
        elif cpu >= _CPU_AMBER_PCT:
            statuses.append("warn")
    if isinstance(ram, (int, float)):
        if ram >= _RAM_RED_PCT:
            statuses.append("fail")
        elif ram >= _RAM_AMBER_PCT:
            statuses.append("warn")
    if isinstance(disk, (int, float)):
        if disk >= _DISK_RED_PCT:
            statuses.append("fail")
        elif disk >= _DISK_AMBER_PCT:
            statuses.append("warn")
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "ok"


# ────────────────────────────────────────────────────────────────────────
# GPU collector (nvidia-smi, bounded subprocess, cached)
# ────────────────────────────────────────────────────────────────────────

_NVSMI_QUERY = (
    "name,utilization.gpu,memory.used,memory.total,"
    "memory.free,temperature.gpu,power.draw"
)


def collect_gpu(force: bool = False) -> Dict[str, Any]:
    """nvidia-smi snapshot, cached 4s. Returns `unavailable` not `fail`
    when nvidia-smi missing — pre-work review #2."""
    now = time.time()
    with _gpu_cache_lock:
        if not force and _gpu_cache["value"] is not None:
            if (now - _gpu_cache["ts"]) < _GPU_CACHE_TTL_SEC:
                return _gpu_cache["value"]

    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                f"--query-gpu={_NVSMI_QUERY}",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except FileNotFoundError:
        result = {"status": "unavailable", "error": "nvidia-smi not on PATH"}
    except subprocess.TimeoutExpired:
        result = {"status": "unavailable", "error": "nvidia-smi timed out (>2s)"}
    except Exception as e:
        result = {"status": "unavailable", "error": f"nvidia-smi failed: {e}"}
    else:
        if proc.returncode != 0:
            result = {
                "status": "unavailable",
                "error": (proc.stderr or "nvidia-smi non-zero exit").strip()[:200],
            }
        else:
            line = (proc.stdout or "").strip().splitlines()
            if not line:
                result = {"status": "unavailable", "error": "empty nvidia-smi output"}
            else:
                # First GPU only (Hornelore is single-GPU; multi-GPU not
                # in scope for Phase 1).
                fields = [c.strip() for c in line[0].split(",")]
                if len(fields) < 6:
                    result = {
                        "status": "unavailable",
                        "error": f"unexpected nvidia-smi field count: {len(fields)}",
                    }
                else:
                    def _f(idx: int) -> Optional[float]:
                        try:
                            v = fields[idx]
                            if v in ("[N/A]", "N/A", ""):
                                return None
                            return float(v)
                        except (ValueError, IndexError):
                            return None

                    name = fields[0]
                    util = _f(1)
                    used = _f(2)
                    total = _f(3)
                    free = _f(4)
                    temp = _f(5)
                    power = _f(6) if len(fields) > 6 else None

                    block = {
                        "status": "ok",
                        "name": name,
                        "util_percent": util,
                        "vram_used_mb": used,
                        "vram_total_mb": total,
                        "vram_free_mb": free,
                        "temperature_c": temp,
                    }
                    if power is not None:
                        block["power_draw_w"] = power
                    block["status"] = _classify_gpu(block)
                    result = block

    with _gpu_cache_lock:
        _gpu_cache["ts"] = now
        _gpu_cache["value"] = result
    return result


def _classify_gpu(g: Dict[str, Any]) -> str:
    free = g.get("vram_free_mb")
    temp = g.get("temperature_c")
    if isinstance(free, (int, float)):
        if free <= _VRAM_FREE_RED_MB:
            return "fail"
        if free <= _VRAM_FREE_AMBER_MB:
            return "warn"
    if isinstance(temp, (int, float)):
        if temp >= _GPU_TEMP_RED_C:
            return "fail"
        if temp >= _GPU_TEMP_AMBER_C:
            return "warn"
    return "ok"


# ────────────────────────────────────────────────────────────────────────
# Service ping helpers
# ────────────────────────────────────────────────────────────────────────

def _tcp_ping(host: str, port: int, timeout_sec: float = 1.5) -> Tuple[bool, float]:
    """Connect-only ping. Returns (ok, latency_ms)."""
    t0 = time.perf_counter()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout_sec)
    try:
        s.connect((host, port))
        s.close()
        return True, (time.perf_counter() - t0) * 1000.0
    except Exception:
        return False, (time.perf_counter() - t0) * 1000.0


def _http_ping(url: str, timeout_sec: float = 1.5) -> Dict[str, Any]:
    """HEAD/GET ping with latency. Uses requests (already pinned)."""
    try:
        import requests  # type: ignore
    except Exception as e:
        return {"ok": False, "error": f"requests import failed: {e}"}
    t0 = time.perf_counter()
    try:
        r = requests.get(url, timeout=timeout_sec)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "ok": r.status_code < 500,
            "status_code": r.status_code,
            "latency_ms": round(latency_ms, 1),
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e)[:200],
            "latency_ms": round((time.perf_counter() - t0) * 1000.0, 1),
        }


def _classify_service(probe: Dict[str, Any]) -> str:
    if not probe.get("ok"):
        return "fail"
    lat = probe.get("latency_ms")
    if isinstance(lat, (int, float)):
        if lat >= _SVC_LATENCY_RED_MS:
            return "fail"
        if lat >= _SVC_LATENCY_AMBER_MS:
            return "warn"
    return "ok"


def collect_services() -> Dict[str, Any]:
    """API + UI + TTS + LLM-warm probes.

    Pre-work review #1: UI is served by the same API (FastAPI mounts
    /ui), so the UI card probes the API origin's /ui path, not :8082.
    """
    api_host = os.getenv("HOST", "127.0.0.1")
    api_port = int(os.getenv("PORT", "8000"))
    tts_port = int(os.getenv("TTS_PORT", "8001"))

    # API ping — cheap GET on /api/ping or fall through to TCP-only.
    api_url = f"http://{api_host}:{api_port}/api/ping"
    api_probe = _http_ping(api_url, timeout_sec=1.5)
    api_status = _classify_service(api_probe)

    # UI/static — same origin as API.
    ui_url = f"http://{api_host}:{api_port}/ui/hornelore1.0.html"
    ui_probe = _http_ping(ui_url, timeout_sec=1.5)
    ui_status = _classify_service(ui_probe)

    # TTS — separate process at TTS_PORT.
    tts_url = f"http://{api_host}:{tts_port}/api/tts/voices"
    tts_probe = _http_ping(tts_url, timeout_sec=1.5)
    tts_status = _classify_service(tts_probe)

    # LLM warm signal: derived from VRAM-free numbers + recent api.log
    # cache-hit grep. Pre-work review #8: we do NOT call /api/warmup on
    # every poll — that's a heavy load operation reserved for the
    # operator's manual warm-check button.
    log_scan = _scan_api_log()
    llm_block: Dict[str, Any] = {"status": "unknown"}
    gpu = collect_gpu()
    if gpu.get("status") in ("ok", "warn"):
        free_mb = gpu.get("vram_free_mb")
        if isinstance(free_mb, (int, float)):
            llm_block["vram_free_mb"] = free_mb
    last_warm = log_scan.get("llm_warm_at")
    if last_warm is not None:
        age = _age_seconds(last_warm)
        llm_block["last_warm_age_sec"] = round(age, 1) if age is not None else None
        if age is not None and age < 90:
            llm_block["status"] = "warm"
        elif age is not None and age < 600:
            llm_block["status"] = "idle_recent"
        else:
            llm_block["status"] = "cold"
    elif llm_block.get("vram_free_mb") is not None:
        # No log signal but GPU is reachable; we can at least say the
        # GPU is up — operator can hit the explicit warm-check button.
        llm_block["status"] = "unknown"

    return {
        "api": {
            "status": api_status,
            "latency_ms": api_probe.get("latency_ms"),
            "url": api_url,
            "error": api_probe.get("error"),
        },
        "ui": {
            "status": ui_status,
            "latency_ms": ui_probe.get("latency_ms"),
            "url": ui_url,
            "error": ui_probe.get("error"),
        },
        "tts": {
            "status": tts_status,
            "latency_ms": tts_probe.get("latency_ms"),
            "url": tts_url,
            "error": tts_probe.get("error"),
        },
        "llm": llm_block,
    }


# ────────────────────────────────────────────────────────────────────────
# api.log scanner (cached by mtime + size)
# ────────────────────────────────────────────────────────────────────────

_RE_OOM = re.compile(r"OutOfMemoryError|VRAM-GUARD.*OOM|cannot allocate", re.IGNORECASE)
_RE_CONN_REFUSED = re.compile(r"ConnectionError|Connection refused", re.IGNORECASE)
_RE_LLM_WARM = re.compile(r"\[extract\] LLM availability cache hit: available")
_RE_EXTRACT_ATTEMPT = re.compile(r"\[extract\] Attempting LLM extraction")
_RE_EVAL_TAG = re.compile(r"\[discipline\] eval_tag=(\S+)")
_RE_TS = re.compile(r"^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)")


def _parse_log_ts(line: str) -> Optional[float]:
    m = _RE_TS.match(line)
    if not m:
        return None
    s = m.group(1).replace(",", ".").replace(" ", "T")
    # Strip subsecond fraction if present
    if "." in s:
        s = s.split(".", 1)[0]
    try:
        dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
        # api.log is local-time; treat as local naive then convert via mktime
        return time.mktime(dt.timetuple())
    except Exception:
        return None


def _scan_api_log() -> Dict[str, Any]:
    """Scan tail of api.log for OOMs / ConnectionErrors / warm signals.

    Pre-work review #5: the file can be 50+ MB; we cache by (mtime, size)
    so repeated polls don't re-tail the file. Tail-only scan when the
    file has grown since last call."""
    if not _API_LOG.exists():
        return dict(_log_scan_cache, available=False)

    try:
        st = _API_LOG.stat()
    except OSError:
        return dict(_log_scan_cache, available=False)

    now = time.time()
    with _log_scan_lock:
        cached_mtime = _log_scan_cache.get("mtime", 0.0)
        cached_size = _log_scan_cache.get("size", 0)
        if (
            st.st_mtime == cached_mtime
            and st.st_size == cached_size
            and (now - _log_scan_cache.get("ts", 0.0)) < _LOG_SCAN_CACHE_TTL_SEC
        ):
            return dict(_log_scan_cache, available=True)

        # Determine where to start reading — full scan if first call OR
        # if file has been rotated (size shrank); incremental tail
        # otherwise.
        start_offset = 0
        if cached_size > 0 and st.st_size >= cached_size:
            start_offset = cached_size

        oom_count = _log_scan_cache.get("oom_count", 0)
        conn_count = _log_scan_cache.get("connection_refused_count", 0)
        last_oom_at = _log_scan_cache.get("last_oom_at")
        last_conn_at = _log_scan_cache.get("last_connection_refused_at")
        last_warm_at = _log_scan_cache.get("llm_warm_at")
        last_extract_at = _log_scan_cache.get("current_extract_at")
        active_eval_tag: Optional[str] = _log_scan_cache.get("active_eval_tag")

        try:
            with open(_API_LOG, "r", encoding="utf-8", errors="replace") as f:
                if start_offset > 0:
                    f.seek(start_offset)
                # Read in 1MB chunks to avoid pulling the whole file at once
                # if a fresh start is required (cold cache + 50MB file).
                while True:
                    chunk = f.readlines(1 << 20)
                    if not chunk:
                        break
                    for ln in chunk:
                        ts = _parse_log_ts(ln) or now
                        if _RE_OOM.search(ln):
                            oom_count += 1
                            last_oom_at = ts
                        if _RE_CONN_REFUSED.search(ln):
                            conn_count += 1
                            last_conn_at = ts
                        if _RE_LLM_WARM.search(ln):
                            last_warm_at = ts
                        if _RE_EXTRACT_ATTEMPT.search(ln):
                            last_extract_at = ts
                        m = _RE_EVAL_TAG.search(ln)
                        if m:
                            active_eval_tag = m.group(1)
        except Exception as e:
            logger.warning("[stack-monitor] api.log scan failed: %s", e)

        _log_scan_cache.update({
            "mtime": st.st_mtime,
            "size": st.st_size,
            "ts": now,
            "oom_count": oom_count,
            "last_oom_at": last_oom_at,
            "connection_refused_count": conn_count,
            "last_connection_refused_at": last_conn_at,
            "llm_warm_at": last_warm_at,
            "current_extract_at": last_extract_at,
            "active_eval_tag": active_eval_tag,
        })
        return dict(_log_scan_cache, available=True)


# ────────────────────────────────────────────────────────────────────────
# Archive / file freshness
# ────────────────────────────────────────────────────────────────────────

def _newest_file_age_sec(root: Path, glob: str = "*", max_scan: int = 200) -> Optional[float]:
    """Return age (seconds) of the most-recently-modified file matching
    `glob` under `root`, scanning at most `max_scan` candidates. Returns
    None if root doesn't exist or no files matched."""
    try:
        if not root.exists():
            return None
        newest_mtime = 0.0
        scanned = 0
        for p in root.rglob(glob):
            if scanned >= max_scan:
                break
            scanned += 1
            try:
                m = p.stat().st_mtime
                if m > newest_mtime:
                    newest_mtime = m
            except OSError:
                continue
        if newest_mtime == 0.0:
            return None
        return max(0.0, time.time() - newest_mtime)
    except Exception:
        return None


def collect_archive() -> Dict[str, Any]:
    """Memory-archive write freshness."""
    if not _MEMORY_ARCHIVE.exists():
        return {"status": "unavailable", "error": f"path missing: {_MEMORY_ARCHIVE}"}
    txt_age = _newest_file_age_sec(_MEMORY_ARCHIVE, "*.txt")
    jsonl_age = _newest_file_age_sec(_MEMORY_ARCHIVE, "*.jsonl")
    # Use the freshest of the two as the primary "is anything writing?"
    # signal.
    youngest = None
    for a in (txt_age, jsonl_age):
        if a is None:
            continue
        if youngest is None or a < youngest:
            youngest = a

    if youngest is None:
        status = "idle"
    elif youngest < _ARCHIVE_STALE_AMBER_SEC:
        status = "writing"
    elif youngest < _ARCHIVE_STALE_RED_SEC:
        status = "stale"
    else:
        status = "idle"

    return {
        "status": status,
        "latest_txt_age_sec": round(txt_age, 1) if txt_age is not None else None,
        "latest_jsonl_age_sec": round(jsonl_age, 1) if jsonl_age is not None else None,
        "path": str(_MEMORY_ARCHIVE),
    }


def collect_capture(person_id: Optional[str] = None) -> Dict[str, Any]:
    """Capture state — backend file probes + UI heartbeat (TTL-gated)."""
    audio_root = _MEMORY_ARCHIVE
    audio_age = _newest_file_age_sec(audio_root, "*.webm") or _newest_file_age_sec(
        audio_root, "*.wav"
    )

    audio_block: Dict[str, Any] = {}
    if audio_age is None:
        audio_block = {"status": "idle", "latest_file_age_sec": None}
    elif audio_age < _ARCHIVE_STALE_AMBER_SEC:
        audio_block = {"status": "writing", "latest_file_age_sec": round(audio_age, 1)}
    else:
        audio_block = {"status": "idle", "latest_file_age_sec": round(audio_age, 1)}

    # UI-heartbeat-derived camera/mic state
    cam_block: Dict[str, Any] = {"status": "unknown"}
    mic_block: Dict[str, Any] = {"status": "unknown"}
    tts_block: Dict[str, Any] = {"status": "unknown"}

    hb = _get_active_heartbeat(person_id=person_id)
    if hb is not None:
        cam = hb.get("camera") or {}
        if cam.get("active"):
            cam_block = {
                "status": "active",
                "reported_by_ui": True,
                "width": cam.get("width"),
                "height": cam.get("height"),
                "track_state": cam.get("track_state"),
            }
        else:
            cam_block = {"status": "off", "reported_by_ui": True}

        mic = hb.get("microphone") or {}
        if mic.get("active"):
            mic_block = {
                "status": "active",
                "reported_by_ui": True,
                "rms_level": mic.get("rms_level"),
                "track_state": mic.get("track_state"),
            }
        else:
            mic_block = {"status": "off", "reported_by_ui": True}

        tts = hb.get("tts") or {}
        if tts.get("speaking"):
            tts_block = {"status": "speaking", "reported_by_ui": True,
                         "queue_length": tts.get("queue_length")}
        else:
            tts_block = {"status": "idle", "reported_by_ui": True}

    return {
        "camera": cam_block,
        "microphone": mic_block,
        "tts_state": tts_block,
        "audio_archive": audio_block,
        "video_archive": {"status": "disabled"},  # Hornelore is audio-only
    }


# ────────────────────────────────────────────────────────────────────────
# UI heartbeat store
# ────────────────────────────────────────────────────────────────────────

def record_ui_heartbeat(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Store an operator-tab heartbeat. Bounded by TTL — old entries
    surface as `unknown`. Returns the stored canonical entry."""
    person_id = str(payload.get("person_id") or "unknown").strip()[:64]
    session_id = str(payload.get("session_id") or "unknown").strip()[:64]
    key = f"{person_id}::{session_id}"
    entry = {
        "person_id": person_id,
        "session_id": session_id,
        "received_at": time.time(),
        "camera": payload.get("camera") or {},
        "microphone": payload.get("microphone") or {},
        "tts": payload.get("tts") or {},
        "archive": payload.get("archive") or {},
    }
    with _ui_heartbeat_lock:
        _ui_heartbeat_store[key] = entry
        # Cap the store size to prevent unbounded growth from rotating
        # session ids.
        if len(_ui_heartbeat_store) > 32:
            # Drop oldest.
            stalest = min(_ui_heartbeat_store.items(),
                          key=lambda kv: kv[1].get("received_at", 0))
            _ui_heartbeat_store.pop(stalest[0], None)
    return entry


def _get_active_heartbeat(person_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Return the freshest non-stale heartbeat. If person_id is given,
    prefer matches; else any tab. Returns None when no fresh heartbeat
    exists."""
    cutoff = time.time() - _UI_HEARTBEAT_TTL_SEC
    with _ui_heartbeat_lock:
        candidates = [v for v in _ui_heartbeat_store.values()
                      if v.get("received_at", 0) >= cutoff]
        if not candidates:
            return None
        if person_id:
            matched = [c for c in candidates if c.get("person_id") == person_id]
            if matched:
                candidates = matched
        candidates.sort(key=lambda v: v.get("received_at", 0), reverse=True)
        return candidates[0]


# ────────────────────────────────────────────────────────────────────────
# Eval progress probe
# ────────────────────────────────────────────────────────────────────────

def collect_eval() -> Dict[str, Any]:
    """Read the most-recent extractor report on disk + api.log signals.
    Distinguishes 'completed' (report exists, eval no longer running)
    from 'running' (no report yet OR api.log is still emitting [extract]
    lines). Phase 1: best-effort heuristic, no eval-runner heartbeat
    file required."""
    log = _scan_api_log()
    last_extract_age = _age_seconds(log.get("current_extract_at"))
    eval_tag = log.get("active_eval_tag")
    conn_refused = log.get("connection_refused_count", 0)
    last_conn_age = _age_seconds(log.get("last_connection_refused_at"))

    # Find newest extractor report in docs/reports
    latest_report: Optional[Dict[str, Any]] = None
    if _REPORTS_DIR.exists():
        try:
            json_reports = sorted(
                _REPORTS_DIR.glob("master_loop01_*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:1]
            if json_reports:
                p = json_reports[0]
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        payload = json.load(f)
                    summary = payload.get("summary") or {}
                    contract = payload.get("contract_subset") or {}
                    latest_report = {
                        "report_name": p.stem,
                        "tag": (payload.get("run_metadata") or {}).get("eval_tag"),
                        "passed": summary.get("passed"),
                        "failed": summary.get("failed"),
                        "total": summary.get("total_cases"),
                        "v3_pass": contract.get("passed_v3"),
                        "v2_pass": contract.get("passed_v2"),
                        "mtime": p.stat().st_mtime,
                        "age_sec": _age_seconds(p.stat().st_mtime),
                    }
                except Exception as e:
                    logger.debug("[stack-monitor] could not read report %s: %s", p, e)
        except Exception as e:
            logger.debug("[stack-monitor] reports glob failed: %s", e)

    # Status: running if api.log saw an [extract] in the last
    # _EVAL_STALE_RED_SEC seconds; stale if older; idle otherwise.
    if last_extract_age is not None and last_extract_age < _EVAL_STALE_AMBER_SEC:
        status = "running"
    elif last_extract_age is not None and last_extract_age < _EVAL_STALE_RED_SEC:
        status = "slow"
    else:
        status = "idle"

    return {
        "status": status,
        "tag": eval_tag,
        "last_extract_age_sec": round(last_extract_age, 1)
            if last_extract_age is not None else None,
        "connection_refused_count_rolling": conn_refused,
        "last_connection_refused_age_sec": round(last_conn_age, 1)
            if last_conn_age is not None else None,
        "latest_report": latest_report,
    }


# ────────────────────────────────────────────────────────────────────────
# Markers (operator notes)
# ────────────────────────────────────────────────────────────────────────

def add_marker(label: str, source: str = "operator") -> Dict[str, Any]:
    """Append a marker, capped at _MARKERS_MAX entries. Pre-work review
    #6: bound the label length and the buffer."""
    label = (label or "").strip()
    if not label:
        return {"ok": False, "error": "empty label"}
    if len(label) > _MARKER_LABEL_MAX:
        label = label[:_MARKER_LABEL_MAX]
    entry = {
        "ts": _utc_now(),
        "label": label,
        "source": source,
    }
    with _markers_lock:
        _markers.append(entry)
        # Drop oldest if cap exceeded.
        while len(_markers) > _MARKERS_MAX:
            _markers.pop(0)
    return {"ok": True, "entry": entry}


def list_markers(limit: int = 50) -> List[Dict[str, Any]]:
    with _markers_lock:
        return list(_markers[-limit:])


# ────────────────────────────────────────────────────────────────────────
# Top-level summary
# ────────────────────────────────────────────────────────────────────────

def build_summary(person_id: Optional[str] = None) -> Dict[str, Any]:
    """Compose the full dashboard payload. Each sub-collector is wrapped
    in try/except so any one source can fail without breaking the
    response."""
    warnings: List[Dict[str, Any]] = []

    try:
        services = collect_services()
    except Exception as e:
        services = {"_error": str(e)}
        warnings.append({"category": "services", "message": f"services probe crashed: {e}"})

    try:
        system = collect_system()
        system["status"] = _classify_system(system)
    except Exception as e:
        system = {"status": "unavailable", "error": str(e)}
        warnings.append({"category": "system", "message": f"system probe crashed: {e}"})

    try:
        gpu = collect_gpu()
    except Exception as e:
        gpu = {"status": "unavailable", "error": str(e)}
        warnings.append({"category": "gpu", "message": f"gpu probe crashed: {e}"})

    try:
        capture = collect_capture(person_id=person_id)
    except Exception as e:
        capture = {"_error": str(e)}
        warnings.append({"category": "capture", "message": f"capture probe crashed: {e}"})

    try:
        archive = collect_archive()
    except Exception as e:
        archive = {"status": "unavailable", "error": str(e)}
        warnings.append({"category": "archive", "message": f"archive probe crashed: {e}"})

    try:
        eval_block = collect_eval()
    except Exception as e:
        eval_block = {"status": "unavailable", "error": str(e)}
        warnings.append({"category": "eval", "message": f"eval probe crashed: {e}"})

    # Roll-up status
    statuses = []
    for block in (services.get("api"), services.get("ui"), services.get("tts"),
                  services.get("llm"), gpu, system, archive):
        if isinstance(block, dict):
            s = block.get("status")
            if s in ("fail", "down"):
                statuses.append("fail")
            elif s in ("warn", "slow", "stale", "cold"):
                statuses.append("warn")
    if "fail" in statuses:
        roll_up = "fail"
    elif "warn" in statuses:
        roll_up = "warn"
    else:
        roll_up = "ok"

    # Auto-derived warnings (not exhaustive — Phase 1):
    log = _scan_api_log()
    last_oom_age = _age_seconds(log.get("last_oom_at"))
    if last_oom_age is not None and last_oom_age < 600:
        warnings.append({
            "category": "gpu",
            "message": f"OOM observed in api.log within last {int(last_oom_age)}s",
            "first_seen_at": _utc_now(),
        })
    last_conn_age = _age_seconds(log.get("last_connection_refused_at"))
    if last_conn_age is not None and last_conn_age < 60:
        warnings.append({
            "category": "api",
            "message": (
                f"Connection refused in api.log {int(last_conn_age)}s ago — "
                "stack may have been restarted mid-eval"
            ),
            "first_seen_at": _utc_now(),
        })

    return {
        "generated_at": _utc_now(),
        "status": roll_up,
        "services": services,
        "system": system,
        "gpu": gpu,
        "capture": capture,
        "archive": archive,
        "eval": eval_block,
        "warnings": warnings,
        "markers": list_markers(limit=10),
    }


# ────────────────────────────────────────────────────────────────────────
# Public surface (for the logger script)
# ────────────────────────────────────────────────────────────────────────

__all__ = [
    "build_summary",
    "collect_system",
    "collect_gpu",
    "collect_services",
    "collect_archive",
    "collect_capture",
    "collect_eval",
    "record_ui_heartbeat",
    "add_marker",
    "list_markers",
]
