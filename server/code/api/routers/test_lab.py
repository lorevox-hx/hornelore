"""WO-QA-01 — Hornelore Quality Harness operator API.

Thin wrapper over scripts/run_test_lab.sh. Writes status to a file so the
FastAPI process can restart mid-run without losing state. Never serves up
its own scoring — UI reads the JSON artifacts the runner produces.

Endpoints:
  POST /api/test-lab/run           — launch harness (optional compare_to / run_label)
  GET  /api/test-lab/status        — running / finished / failed / idle
  GET  /api/test-lab/results       — list prior run_ids
  GET  /api/test-lab/results/{id}  — scores / metrics / transcripts / compare / summary
  POST /api/test-lab/reset         — reset status.json to idle
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/test-lab", tags=["test-lab"])

TEST_LAB_ROOT = Path(os.getenv(
    "HORNELORE_TEST_LAB_ROOT",
    "/mnt/c/hornelore_data/test_lab",
))
RUNS_ROOT = TEST_LAB_ROOT / "runs"
STATUS_FILE = TEST_LAB_ROOT / "status.json"

# Resolve scripts/run_test_lab.sh relative to this file.
# routers → api → code → server → (repo root)
REPO_ROOT = Path(__file__).resolve().parents[4]
RUNNER_SCRIPT = REPO_ROOT / "scripts" / "run_test_lab.sh"


def _ensure_root() -> None:
    TEST_LAB_ROOT.mkdir(parents=True, exist_ok=True)
    RUNS_ROOT.mkdir(parents=True, exist_ok=True)


def _write_status(payload: Dict[str, Any]) -> None:
    _ensure_root()
    STATUS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _read_status() -> Dict[str, Any]:
    if not STATUS_FILE.exists():
        return {"state": "idle"}
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"state": "unknown"}


def _proc_alive(pid: int) -> bool:
    """Is the PID still running? POSIX-only; returns False on any error."""
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError, PermissionError):
        return False
    return True


@router.post("/run")
async def run_test_lab(payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if not RUNNER_SCRIPT.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Runner script not found at {RUNNER_SCRIPT}",
        )

    current = _read_status()
    if current.get("state") == "running" and current.get("pid") and _proc_alive(int(current["pid"])):
        raise HTTPException(status_code=409, detail="Test Lab already running")

    payload = payload or {}
    compare_to = payload.get("compare_to")
    run_label = payload.get("run_label")
    dry_run = bool(payload.get("dry_run", False))

    cmd = ["bash", str(RUNNER_SCRIPT)]
    if compare_to:
        cmd.extend(["--compare-to", str(compare_to)])
    if run_label:
        cmd.extend(["--run-label", str(run_label)])
    if dry_run:
        cmd.append("--dry-run")

    _ensure_root()
    log_path = TEST_LAB_ROOT / "runner.log"
    log_f = log_path.open("a", encoding="utf-8")

    proc = subprocess.Popen(
        cmd,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        cwd=str(REPO_ROOT),
    )

    _write_status({
        "state": "running",
        "pid": proc.pid,
        "cmd": cmd,
        "compare_to": compare_to,
        "run_label": run_label,
        "dry_run": dry_run,
        "log_path": str(log_path),
    })
    return {"ok": True, "pid": proc.pid, "log_path": str(log_path)}


@router.get("/status")
async def get_status() -> Dict[str, Any]:
    state = _read_status()
    if state.get("state") == "running":
        pid = state.get("pid")
        if not pid or not _proc_alive(int(pid)):
            # Process finished — try to determine success from whether the
            # most recent run dir has a scores.json.
            RUNS_ROOT.mkdir(parents=True, exist_ok=True)
            runs = sorted([p.name for p in RUNS_ROOT.iterdir() if p.is_dir()], reverse=True)
            latest = runs[0] if runs else None
            if latest and (RUNS_ROOT / latest / "scores.json").exists():
                state["state"] = "finished"
                state["latest_run"] = latest
            else:
                state["state"] = "failed"
            _write_status(state)
    return state


@router.get("/results")
async def list_results() -> Dict[str, Any]:
    _ensure_root()
    runs = sorted([p.name for p in RUNS_ROOT.iterdir() if p.is_dir()], reverse=True)
    return {"runs": runs}


@router.get("/results/{run_id}")
async def get_result(run_id: str) -> Dict[str, Any]:
    run_dir = RUNS_ROOT / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run not found")

    def load(name: str) -> Any:
        p = run_dir / name
        if not p.exists():
            return None
        if p.suffix == ".md":
            return p.read_text(encoding="utf-8")
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

    return {
        "run_id": run_id,
        "scores": load("scores.json"),
        "metrics": load("metrics.json"),
        "summary": load("summary.md"),
        "transcripts": load("transcripts.json"),
        "compare": load("compare.json"),
        "configs": load("configs.json"),
    }


@router.post("/reset")
async def reset_status() -> Dict[str, Any]:
    _write_status({"state": "idle"})
    return {"ok": True}


@router.get("/gpu")
async def gpu_stats() -> Dict[str, Any]:
    """One-shot nvidia-smi scrape for in-UI live monitoring."""
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=4,
        ).strip()
    except FileNotFoundError:
        return {"ok": False, "error": "nvidia-smi not on PATH"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "nvidia-smi timeout"}
    except subprocess.CalledProcessError as exc:
        return {"ok": False, "error": f"nvidia-smi failed: {exc}"}

    # First GPU only — Hornelore is single-GPU.
    first = out.splitlines()[0] if out else ""
    parts = [p.strip() for p in first.split(",")]
    if len(parts) < 6:
        return {"ok": False, "error": f"unexpected nvidia-smi output: {first!r}"}
    try:
        name, util, vram_used, vram_total, temp, power = parts
        return {
            "ok": True,
            "name": name,
            "util_pct": int(util),
            "vram_used_mib": int(vram_used),
            "vram_total_mib": int(vram_total),
            "temp_c": int(temp),
            "power_w": float(power),
        }
    except ValueError as exc:
        return {"ok": False, "error": f"parse failed: {exc}"}


@router.get("/log-tail")
async def log_tail(lines: int = 30) -> Dict[str, Any]:
    """Return the last N lines of runner.log for in-UI log viewing."""
    log_path = TEST_LAB_ROOT / "runner.log"
    if not log_path.exists():
        return {"ok": True, "lines": [], "note": "no runner.log yet"}
    n = max(1, min(int(lines), 500))
    try:
        # Read full file (logs stay small); slice last N lines.
        content = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return {"ok": True, "lines": content[-n:], "total_lines": len(content)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
