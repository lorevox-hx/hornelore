"""WO-BUG-PANEL-EVAL-HARNESS-01 Phase 1 — read-only operator eval cockpit.

Four endpoints, all operator-only (Bug Panel consumes them — no
narrator-side route or UI surface):

  GET /api/operator/eval-harness/summary
      Aggregate status of 4 lanes: extractor / lori_behavior / safety /
      story_surfaces. Each lane returns PASS / WARN / FAIL / MISSING /
      STALE plus pass rate, last run time, top failures, and a
      copyable run command.

  GET /api/operator/eval-harness/reports
      Lists available extractor reports on disk (newest first), with
      eval_tag + git_sha + topline metrics for each.

  GET /api/operator/eval-harness/report/{report_name}
      Returns a sanitized snapshot of a single extractor report by
      filename stem. Operator can drill into per-case results.

  GET /api/operator/eval-harness/log-tail?lines=N
      Returns the last N lines of api.log so the operator can spot
      tracebacks / crashes near a known eval window.

Backend gate: every endpoint short-circuits to 404 unless
`HORNELORE_OPERATOR_EVAL_HARNESS=1` is set in the server env. Mirror
of safety_events.py operator gate; default-OFF so the route doesn't
advertise itself.

Phase 1 is READ-ONLY. Phase 2 will add guarded run buttons —
deliberately deferred so the cockpit lands stable before we let it
launch long-running jobs.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/operator/eval-harness", tags=["operator", "eval"])


# ── Repo-rooted paths ──────────────────────────────────────────────────────
# This module lives at server/code/api/routers/, so REPO_ROOT is four
# parents up. Keep the same depth math as scripts/archive/run_*.py.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_REPORTS_DIR = _REPO_ROOT / "docs" / "reports"
_RUNTIME_LOGS = _REPO_ROOT / ".runtime" / "logs"
_RUNTIME_EVAL = _REPO_ROOT / ".runtime" / "eval"
_PLAYWRIGHT_REPORT = _REPO_ROOT / "playwright-report"
_TEST_RESULTS = _REPO_ROOT / "test-results"

# Runs older than this many days get tagged STALE in the summary.
_STALE_DAYS = 7

# Known eval-crash markers in api.log / stdout traces.
_CRASH_PATTERNS = [
    "TypeError: unsupported format string passed to NoneType",
    "Traceback (most recent call last):",
    "RuntimeError: VRAM",
    "OSError: [Errno 12] Cannot allocate memory",
    "torch.cuda.OutOfMemoryError",
]

# Copyable run commands surfaced in each card.
_RUN_COMMANDS = {
    "extractor": (
        "./scripts/archive/run_question_bank_extraction_eval.py --mode live \\\n"
        "  --api http://localhost:8000 \\\n"
        "  --output docs/reports/master_loop01_<SUFFIX>.json"
    ),
    "lori_behavior": (
        "export HORNELORE_OPERATOR_SAFETY_EVENTS=1 HORNELORE_INTERVIEW_DISCIPLINE=1\n"
        "python scripts/eval/run_lori_behavior_harness.py \\\n"
        "  --api http://localhost:8000 --mode live\n"
        "cat .runtime/eval/lori_behavior/latest.md"
    ),
    "safety": (
        "# Safety eval rides on the Lori behavior harness 'safety' lane.\n"
        "python scripts/eval/run_lori_behavior_harness.py \\\n"
        "  --api http://localhost:8000 --mode live"
    ),
    "story_surfaces": (
        "npx playwright test tests/e2e/lori_behavior_surfaces.spec.js --headed"
    ),
}


# ── Backend gate ───────────────────────────────────────────────────────────

def _operator_eval_harness_enabled() -> bool:
    """Default-OFF gate. Enable with `HORNELORE_OPERATOR_EVAL_HARNESS=1`."""
    return os.getenv("HORNELORE_OPERATOR_EVAL_HARNESS", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _require_operator_eval_harness_enabled() -> None:
    """Raise 404 (not 403) when the backend gate is off so an external
    probe can't distinguish 'endpoint exists but you can't have it' from
    'endpoint doesn't exist'."""
    if not _operator_eval_harness_enabled():
        raise HTTPException(status_code=404, detail="Not found")


# ── Helpers ────────────────────────────────────────────────────────────────

def _safe_isoformat(ts: float) -> str:
    """Format a Unix timestamp as ISO-8601 UTC. Returns empty string on
    invalid input rather than raising."""
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return ""


def _age_days(ts: float) -> Optional[float]:
    if not ts:
        return None
    return (time.time() - ts) / 86400.0


def _classify_extractor(report: Dict[str, Any]) -> str:
    """PASS / WARN / FAIL based on master report contents.

    PASS: pass_rate >= 0.65 AND mnw_rate <= 0.025 (matches r5h baseline
          band 70/104 = 0.673, mnw=2/104 ≈ 0.019).
    WARN: degraded but eval ran cleanly (lower pass rate or higher mnw).
    FAIL: pass_rate < 0.30 (catastrophic regression).
    """
    summary = report.get("summary") or {}
    pass_rate = summary.get("pass_rate") or 0
    tz = report.get("truth_zone_summary") or {}
    mnw_rate = tz.get("must_not_write_violation_rate") or 0

    if pass_rate < 0.30:
        return "fail"
    if pass_rate >= 0.65 and mnw_rate <= 0.025:
        return "pass"
    return "warn"


def _summarize_extractor_report(report_path: Path) -> Dict[str, Any]:
    """Build a compact dict summarizing a single extractor report.
    Sanitized — never returns full per-case results, just the top-level
    contracts the operator cockpit needs.

    Failure-tolerant: if the JSON is malformed (e.g. eval crashed before
    write), returns a status='fail' card with the read error so the
    operator sees the breakage instead of a silent gap.
    """
    out: Dict[str, Any] = {
        "lane": "extractor",
        "report_path": str(report_path.relative_to(_REPO_ROOT))
        if report_path.is_relative_to(_REPO_ROOT)
        else str(report_path),
        "report_name": report_path.stem,
        "status": "missing",
    }
    if not report_path.exists():
        return out

    try:
        with report_path.open("r", encoding="utf-8") as f:
            r = json.load(f)
    except Exception as e:
        out["status"] = "fail"
        out["error"] = f"read failed: {e}"
        return out

    summary = r.get("summary") or {}
    contract = r.get("contract_subset") or {}
    tz = r.get("truth_zone_summary") or {}
    md = r.get("run_metadata") or {}
    fc = r.get("failure_categories") or {}

    # Top-N failure categories by count.
    if isinstance(fc, dict):
        top_failures = sorted(fc.items(), key=lambda kv: kv[1], reverse=True)[:5]
        top_failures_dict = {k: v for k, v in top_failures}
    else:
        top_failures_dict = {}

    mtime = report_path.stat().st_mtime
    age = _age_days(mtime)

    out.update({
        "status": _classify_extractor(r),
        "eval_tag": md.get("eval_tag") or report_path.stem.replace("master_loop01_", ""),
        "mode": r.get("mode") or md.get("mode"),
        "git_sha": md.get("git_sha"),
        "git_dirty": md.get("git_dirty"),
        "branch": md.get("branch"),
        "started_at": md.get("started_at"),
        "report_mtime": _safe_isoformat(mtime),
        "age_days": round(age, 2) if age is not None else None,
        "is_stale": (age is not None and age > _STALE_DAYS),
        "total_cases": summary.get("total_cases"),
        "passed": summary.get("passed"),
        "failed": summary.get("failed"),
        "pass_rate": summary.get("pass_rate"),
        "avg_overall_score": summary.get("avg_overall_score"),
        "contract_v3_passed": contract.get("passed_v3"),
        "contract_v3_total": contract.get("total"),
        "contract_v2_passed": contract.get("passed_v2"),
        "contract_v2_total": contract.get("total"),
        "must_not_write_violation_rate": tz.get("must_not_write_violation_rate"),
        "must_extract_recall": tz.get("must_extract_recall"),
        "top_failures": top_failures_dict,
        "run_command": _RUN_COMMANDS["extractor"],
    })

    # Tag stale if too old.
    if out["is_stale"] and out["status"] == "pass":
        out["status"] = "stale"

    return out


def _latest_extractor_report() -> Optional[Path]:
    """Return the most recently modified master_loop01_*.json in
    docs/reports/. Skips .failure_pack.json sidecars."""
    if not _REPORTS_DIR.is_dir():
        return None
    candidates = [
        p for p in _REPORTS_DIR.glob("master_loop01_*.json")
        if not p.name.endswith(".failure_pack.json")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _list_extractor_reports(limit: int = 20) -> List[Dict[str, Any]]:
    """List recent extractor reports for the report-picker UI. Each entry
    has just enough metadata to surface in a dropdown without hitting the
    full report-summary path."""
    if not _REPORTS_DIR.is_dir():
        return []
    items = []
    for p in _REPORTS_DIR.glob("master_loop01_*.json"):
        if p.name.endswith(".failure_pack.json"):
            continue
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        items.append({
            "report_name": p.stem,
            "path": str(p.relative_to(_REPO_ROOT)) if p.is_relative_to(_REPO_ROOT) else str(p),
            "mtime": _safe_isoformat(mtime),
            "age_days": round(_age_days(mtime) or 0, 2),
            "size_bytes": p.stat().st_size,
        })
    items.sort(key=lambda d: d["mtime"], reverse=True)
    return items[:max(1, min(int(limit or 20), 100))]


def _summarize_lori_behavior() -> Dict[str, Any]:
    """Read .runtime/eval/lori_behavior/latest.json from the behavior
    harness. Returns MISSING when the file doesn't exist (harness has
    never been run)."""
    out: Dict[str, Any] = {
        "lane": "lori_behavior",
        "report_path": ".runtime/eval/lori_behavior/latest.json",
        "status": "missing",
        "run_command": _RUN_COMMANDS["lori_behavior"],
    }
    latest_json = _RUNTIME_EVAL / "lori_behavior" / "latest.json"
    latest_md = _RUNTIME_EVAL / "lori_behavior" / "latest.md"

    if not latest_json.exists():
        return out

    try:
        with latest_json.open("r", encoding="utf-8") as f:
            r = json.load(f)
    except Exception as e:
        out["status"] = "fail"
        out["error"] = f"read failed: {e}"
        return out

    mtime = latest_json.stat().st_mtime
    age = _age_days(mtime)
    results = r.get("results") or []
    total = len(results)
    passed = sum(1 for x in results if x.get("ok"))
    failed = total - passed

    # Lane-level rollup
    lane_counts: Dict[str, Dict[str, int]] = {}
    for x in results:
        lane = x.get("lane") or "unknown"
        d = lane_counts.setdefault(lane, {"total": 0, "passed": 0, "failed": 0})
        d["total"] += 1
        if x.get("ok"):
            d["passed"] += 1
        else:
            d["failed"] += 1

    overall_ok = bool(r.get("ok"))
    if total == 0:
        status = "missing"
    elif overall_ok:
        status = "pass"
    elif failed == total:
        status = "fail"
    else:
        status = "warn"
    if status == "pass" and age is not None and age > _STALE_DAYS:
        status = "stale"

    out.update({
        "status": status,
        "report_mtime": _safe_isoformat(mtime),
        "age_days": round(age, 2) if age is not None else None,
        "is_stale": (age is not None and age > _STALE_DAYS),
        "total": total,
        "passed": passed,
        "failed": failed,
        "by_lane": lane_counts,
        "md_available": latest_md.exists(),
    })
    return out


def _summarize_safety() -> Dict[str, Any]:
    """Read recent operator-safety events from the DB. Tags safety lane
    with READY (events ≥ 0, infrastructure present), WARN (≥ 5 unacked),
    FAIL (DB read error)."""
    out: Dict[str, Any] = {
        "lane": "safety",
        "report_path": "db: safety_events table",
        "status": "ready",
        "run_command": _RUN_COMMANDS["safety"],
    }
    try:
        from ..db import count_unacked_safety_events
        unacked = count_unacked_safety_events()
    except Exception as e:
        out["status"] = "fail"
        out["error"] = f"safety_events read failed: {e}"
        return out
    out["unacknowledged_events"] = int(unacked or 0)
    if unacked >= 5:
        out["status"] = "warn"
        out["note"] = f"{unacked} unacknowledged events — review in Bug Panel banner"
    return out


def _summarize_story_surfaces() -> Dict[str, Any]:
    """Look for Playwright artifacts. Returns MISSING when no recent run
    has produced playwright-report/ or test-results/."""
    out: Dict[str, Any] = {
        "lane": "story_surfaces",
        "report_path": "playwright-report/",
        "status": "missing",
        "run_command": _RUN_COMMANDS["story_surfaces"],
    }
    pr = _PLAYWRIGHT_REPORT
    tr = _TEST_RESULTS
    if pr.is_dir():
        try:
            mtime = pr.stat().st_mtime
            age = _age_days(mtime)
            out["status"] = "stale" if (age is not None and age > _STALE_DAYS) else "pass"
            out["report_mtime"] = _safe_isoformat(mtime)
            out["age_days"] = round(age, 2) if age is not None else None
        except OSError:
            pass
    elif tr.is_dir():
        try:
            mtime = tr.stat().st_mtime
            out["status"] = "warn"
            out["note"] = "test-results/ exists but no playwright-report/ — run ended without HTML report"
            out["report_mtime"] = _safe_isoformat(mtime)
        except OSError:
            pass
    return out


def _detect_recent_crash(api_log_tail_lines: int = 800) -> Optional[Dict[str, Any]]:
    """Scan the tail of api.log for known eval-crash patterns. Returns
    the matching line + a short context excerpt when found, else None."""
    log_path = _RUNTIME_LOGS / "api.log"
    if not log_path.exists():
        return None
    try:
        # Read tail efficiently — last ~200 KB is plenty for crash scan.
        tail_bytes = 200 * 1024
        with log_path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            offset = max(0, size - tail_bytes)
            f.seek(offset)
            tail_data = f.read().decode("utf-8", errors="replace")
        lines = tail_data.splitlines()[-api_log_tail_lines:]
    except Exception as e:
        logger.warning("[eval-harness] api.log tail read failed: %s", e)
        return None
    # Walk lines newest-first; first crash pattern wins.
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i]
        for pat in _CRASH_PATTERNS:
            if pat in line:
                # Grab a small context window (3 lines before through end).
                context_start = max(0, i - 3)
                context_end = min(len(lines), i + 6)
                return {
                    "matched_pattern": pat,
                    "matched_line": line[:300],
                    "context": "\n".join(lines[context_start:context_end])[:1500],
                    "from_log": str(log_path.relative_to(_REPO_ROOT))
                    if log_path.is_relative_to(_REPO_ROOT)
                    else str(log_path),
                }
    return None


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("/summary")
def summary():
    """Aggregate read-only summary of all 4 eval lanes.

    Returns a `cards` array — one card per lane (extractor / lori_behavior
    / safety / story_surfaces) — plus optional `recent_crash` if api.log
    contains a known eval-crash marker in its recent tail.

    Bug Panel polls this endpoint to render the cockpit. Refresh button
    re-hits the endpoint; no caching server-side.
    """
    _require_operator_eval_harness_enabled()

    # Extractor lane — most recent master_loop01_*.json.
    extractor_path = _latest_extractor_report()
    if extractor_path is not None:
        extractor_card = _summarize_extractor_report(extractor_path)
    else:
        extractor_card = {
            "lane": "extractor",
            "status": "missing",
            "report_path": str(_REPORTS_DIR.relative_to(_REPO_ROOT)) + "/",
            "note": "No master_loop01_*.json found in docs/reports/",
            "run_command": _RUN_COMMANDS["extractor"],
        }

    return {
        "generated_at": _safe_isoformat(time.time()),
        "cards": [
            extractor_card,
            _summarize_lori_behavior(),
            _summarize_safety(),
            _summarize_story_surfaces(),
        ],
        "recent_crash": _detect_recent_crash(),
    }


@router.get("/reports")
def reports(limit: int = Query(20, ge=1, le=100)):
    """List available extractor reports for the report picker."""
    _require_operator_eval_harness_enabled()
    return {"reports": _list_extractor_reports(limit=limit)}


@router.get("/report/{report_name}")
def report_detail(report_name: str):
    """Sanitized snapshot of a single extractor report by stem name.

    `report_name` is the filename without `.json` — e.g. `master_loop01_r5h-restore`.
    Path traversal is blocked: the resolved path must live inside docs/reports/.
    """
    _require_operator_eval_harness_enabled()
    # Defensive: only allow simple alnum + hyphen + underscore + dot in stem.
    if not re.fullmatch(r"[A-Za-z0-9._\-]+", report_name or ""):
        raise HTTPException(status_code=400, detail="Invalid report name")
    candidate = (_REPORTS_DIR / f"{report_name}.json").resolve()
    if not candidate.is_relative_to(_REPORTS_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Path traversal blocked")
    if not candidate.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    return _summarize_extractor_report(candidate)


@router.get("/log-tail")
def log_tail(lines: int = Query(80, ge=1, le=500)):
    """Return the last N lines of api.log. 80 is enough to spot the most
    recent traceback / discipline header / crash. Cap at 500 to keep
    responses small."""
    _require_operator_eval_harness_enabled()
    log_path = _RUNTIME_LOGS / "api.log"
    if not log_path.exists():
        return {"path": str(log_path.relative_to(_REPO_ROOT)) if log_path.is_relative_to(_REPO_ROOT) else str(log_path), "lines": [], "exists": False}
    try:
        # Same tail-read pattern as _detect_recent_crash but with caller's
        # lines parameter and no pattern matching.
        tail_bytes = max(20 * 1024, lines * 800)  # ~800 chars per line, with floor
        with log_path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            offset = max(0, size - tail_bytes)
            f.seek(offset)
            data = f.read().decode("utf-8", errors="replace")
        out_lines = data.splitlines()[-lines:]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"log read failed: {e}")
    return {
        "path": str(log_path.relative_to(_REPO_ROOT)) if log_path.is_relative_to(_REPO_ROOT) else str(log_path),
        "exists": True,
        "lines": out_lines,
        "count": len(out_lines),
    }
