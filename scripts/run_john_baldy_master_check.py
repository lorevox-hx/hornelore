#!/usr/bin/env python3
"""John Baldy master check — one-command orchestrator.

Bundles the four checks Chris asked for after the 2026-06-17 Chrome-MCP
harness failure surfaced multiple bugs at once:

  1. FAST UNIT TESTS — three Python suites that catch backend regressions
     in the areas most likely to break Lori's behavior:
       - tests.test_lori_communication_control (atomicity, reflection,
         word limits, stub-collapse, safety exemption, golfball)
       - tests.test_compose_memory_echo_spanish (multilingual locale,
         English byte-stability)
       - tests.test_bio_questionnaire_writer (questionnaire fan-out
         into bio_facts + profile_json)

  2. TEST LAB AVAILABILITY — probes the /api/test-lab/* router and
     checks scripts/run_test_lab.sh exists. Test Lab is the broad-
     matrix harness; the router 500s if the runner script is missing.

  3. SEVEN-ERA BACKEND WALK — runs scripts/run_john_baldy_seven_era_
     harness.py, which uses scripts/harness_lib.py to create John via
     POST /api/people/intake, open the live chat WebSocket, send seven
     narrator-voice first-person chapters (one per canonical era),
     score Lori's reply on the 8-row matrix per chapter, and write a
     report under docs/reports/john_baldy_seven_era_*.{json,md}. This
     is the corrected harness — the Chrome run that prompted this
     script confused operator directives with narrator speech; this
     replacement sends NARRATOR-VOICE only.

  4. CONSOLIDATED REPORT — one markdown file at
     docs/reports/john_baldy_master_check_<ts>.md tying everything
     together: unit-test pass/fail, Test Lab availability verdict,
     seven-era pass-counts per era, the bugs surfaced today
     (Spanish misfire, comm-control trim, VRAM-GUARD truncation,
     facts/add 422), and the recommended next action.

USAGE:
    cd /mnt/c/Users/chris/hornelore
    python3 scripts/run_john_baldy_master_check.py

ENVIRONMENT:
    HORNELORE_API_BASE — defaults to http://localhost:8000
    HORNELORE_SKIP_UNIT_TESTS=1 — skip step 1 (e.g. when you only
        want the live walk)
    HORNELORE_SKIP_SEVEN_ERA=1 — skip step 3 (e.g. when you only
        want the unit-test + Test Lab probe sanity pass)

PRECONDITIONS:
    - Hornelore stack up at the configured API base (bash scripts/
      start_all.sh; wait for "LLM is warm and ready").
    - .venv-gpu activated OR python3 with `websockets` installed (the
      seven-era harness imports it via harness_lib.py).
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


REPO_ROOT = Path("/mnt/c/Users/chris/hornelore")
REPORTS_DIR = REPO_ROOT / "docs" / "reports"
SCRIPTS_DIR = REPO_ROOT / "scripts"
TESTS_DIR = REPO_ROOT / "tests"

API_BASE = os.environ.get("HORNELORE_API_BASE", "http://localhost:8000")

UNIT_TEST_MODULES = (
    "tests.test_lori_communication_control",
    "tests.test_compose_memory_echo_spanish",
    "tests.test_bio_questionnaire_writer",
)

SEVEN_ERA_SCRIPT = SCRIPTS_DIR / "run_john_baldy_seven_era_harness.py"


# ── Helpers ─────────────────────────────────────────────────────────


def _hr(label: str = "") -> None:
    bar = "=" * 70
    print(bar)
    if label:
        print(label)
        print(bar)


def _try_get(url: str, timeout: int = 5) -> Tuple[int, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw)
            except (ValueError, TypeError):
                return resp.status, raw
    except urllib.error.HTTPError as e:
        return e.code, str(e)
    except (urllib.error.URLError, OSError) as e:
        return 0, str(e)


# ── Step 1 — unit tests ─────────────────────────────────────────────


def run_unit_tests() -> Dict[str, Any]:
    _hr("STEP 1 — FAST UNIT TESTS")
    if os.environ.get("HORNELORE_SKIP_UNIT_TESTS", "0").lower() in ("1", "true", "yes"):
        print("  ! SKIPPED (HORNELORE_SKIP_UNIT_TESTS=1)\n")
        return {"skipped": True, "modules": []}

    per_module: List[Dict[str, Any]] = []
    overall_ok = True
    for mod in UNIT_TEST_MODULES:
        print(f"  → python3 -m unittest {mod}")
        t0 = time.time()
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", mod, "-v"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
        )
        dur = time.time() - t0
        ok = proc.returncode == 0
        overall_ok = overall_ok and ok
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-12:]
        per_module.append(
            {
                "module": mod,
                "returncode": proc.returncode,
                "ok": ok,
                "seconds": round(dur, 1),
                "tail": tail,
            }
        )
        mark = "✓" if ok else "✗"
        print(f"  {mark} {mod} rc={proc.returncode} ({dur:.1f}s)")
        for line in tail[-3:]:
            print(f"      {line}")
        print()
    return {"skipped": False, "ok": overall_ok, "modules": per_module}


# ── Step 2 — Test Lab availability probe ────────────────────────────


def probe_test_lab() -> Dict[str, Any]:
    _hr("STEP 2 — TEST LAB AVAILABILITY")
    runner = SCRIPTS_DIR / "run_test_lab.sh"
    runner_present = runner.exists()
    print(f"  scripts/run_test_lab.sh present: {'yes' if runner_present else 'NO'}")

    routes = {
        "status": f"{API_BASE}/api/test-lab/status",
        "system": f"{API_BASE}/api/test-lab/system",
        "results": f"{API_BASE}/api/test-lab/results",
    }
    route_status: Dict[str, Any] = {}
    for name, url in routes.items():
        code, body = _try_get(url)
        route_status[name] = {"http": code, "preview": str(body)[:160]}
        ok = code == 200
        mark = "✓" if ok else "⚠" if code else "✗"
        print(f"  {mark} GET {url} → {code}")

    verdict = (
        "AVAILABLE"
        if runner_present and route_status["status"]["http"] == 200
        else "DEGRADED — Test Lab runs will likely 500"
        if route_status["status"]["http"] == 200
        else "OFFLINE"
    )
    print(f"  → verdict: {verdict}\n")
    return {
        "runner_present": runner_present,
        "routes": route_status,
        "verdict": verdict,
    }


# ── Step 3 — seven-era backend walk ─────────────────────────────────


def run_seven_era_walk() -> Dict[str, Any]:
    _hr("STEP 3 — SEVEN-ERA WALK (John Baldy, narrator-voice)")
    if os.environ.get("HORNELORE_SKIP_SEVEN_ERA", "0").lower() in ("1", "true", "yes"):
        print("  ! SKIPPED (HORNELORE_SKIP_SEVEN_ERA=1)\n")
        return {"skipped": True}

    if not SEVEN_ERA_SCRIPT.exists():
        print(f"  ✗ {SEVEN_ERA_SCRIPT} missing — cannot run\n")
        return {"skipped": False, "ok": False, "error": "script_missing"}

    print(f"  → python3 {SEVEN_ERA_SCRIPT.relative_to(REPO_ROOT)}")
    print("  (this drives 7 narrator-voice chapters across the live")
    print("  chat WS; ~3-5 min on a warm stack; reports written to")
    print("  docs/reports/john_baldy_seven_era_*.{json,md})")
    print()
    t0 = time.time()
    proc = subprocess.run(
        [sys.executable, str(SEVEN_ERA_SCRIPT)],
        cwd=str(REPO_ROOT),
        capture_output=False,  # let it stream to console
        timeout=900,  # 15 min hard cap
    )
    dur = time.time() - t0
    ok = proc.returncode == 0
    mark = "✓" if ok else "✗"
    print(f"\n  {mark} seven-era walk rc={proc.returncode} ({dur:.0f}s)\n")

    # Find newest matching report files
    json_reports = sorted(REPORTS_DIR.glob("john_baldy_seven_era_*.json"))
    md_reports = sorted(REPORTS_DIR.glob("john_baldy_seven_era_*.md"))
    return {
        "skipped": False,
        "ok": ok,
        "returncode": proc.returncode,
        "seconds": round(dur, 1),
        "json_report": str(json_reports[-1]) if json_reports else None,
        "md_report": str(md_reports[-1]) if md_reports else None,
    }


# ── Step 4 — consolidated report ────────────────────────────────────


def write_master_report(
    unit_results: Dict[str, Any],
    test_lab_results: Dict[str, Any],
    walk_results: Dict[str, Any],
) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = REPORTS_DIR / f"john_baldy_master_check_{ts}.md"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    lines: List[str] = []
    lines.append(f"# John Baldy Master Check — {ts}")
    lines.append("")
    lines.append(
        "Bundled run of (1) fast unit tests, (2) Test Lab availability "
        "probe, and (3) seven-era backend walk against the live stack at "
        f"`{API_BASE}`."
    )
    lines.append("")
    lines.append("## Topline")
    lines.append("")
    unit_topline = (
        "skipped"
        if unit_results.get("skipped")
        else "PASS" if unit_results.get("ok") else "FAIL"
    )
    lab_topline = test_lab_results.get("verdict", "UNKNOWN")
    walk_topline = (
        "skipped"
        if walk_results.get("skipped")
        else "PASS" if walk_results.get("ok") else "FAIL"
    )
    lines.append(f"- Unit tests: **{unit_topline}**")
    lines.append(f"- Test Lab: **{lab_topline}**")
    lines.append(f"- Seven-era walk: **{walk_topline}**")
    lines.append("")

    # Unit-test details
    lines.append("## Unit tests")
    lines.append("")
    if unit_results.get("skipped"):
        lines.append("Skipped via `HORNELORE_SKIP_UNIT_TESTS=1`.")
    else:
        for m in unit_results.get("modules", []):
            mark = "✓" if m["ok"] else "✗"
            lines.append(
                f"- {mark} `{m['module']}` rc={m['returncode']} "
                f"({m['seconds']}s)"
            )
            for tl in m["tail"][-4:]:
                lines.append(f"      {tl}")
    lines.append("")

    # Test Lab details
    lines.append("## Test Lab availability")
    lines.append("")
    lines.append(
        f"- `scripts/run_test_lab.sh` present: "
        f"`{test_lab_results.get('runner_present')}`"
    )
    for name, info in (test_lab_results.get("routes") or {}).items():
        lines.append(f"- GET `/api/test-lab/{name}` → HTTP `{info['http']}`")
    lines.append(f"- Verdict: **{test_lab_results.get('verdict')}**")
    lines.append("")

    # Seven-era details
    lines.append("## Seven-era walk")
    lines.append("")
    if walk_results.get("skipped"):
        lines.append("Skipped via `HORNELORE_SKIP_SEVEN_ERA=1`.")
    elif walk_results.get("error") == "script_missing":
        lines.append(
            "`scripts/run_john_baldy_seven_era_harness.py` not found — "
            "create it before running this orchestrator."
        )
    else:
        lines.append(
            f"- returncode: `{walk_results.get('returncode')}`"
            f"  duration: `{walk_results.get('seconds')}s`"
        )
        for k in ("md_report", "json_report"):
            v = walk_results.get(k)
            if v:
                relp = Path(v)
                try:
                    relp = relp.relative_to(REPO_ROOT)
                except ValueError:
                    pass
                lines.append(f"- {k}: `{relp}`")
    lines.append("")

    # Known open bugs from today
    lines.append("## Open bugs in scope this run")
    lines.append("")
    lines.append(
        "From the 2026-06-17 Chrome-MCP run + api.log evidence + "
        "operator log:"
    )
    lines.append("")
    lines.append(
        "- **BUG-LORI-SPANISH-MISFIRE-ENGLISH-SESSION-01** — confirmed "
        "in api.log L235170: `[chat_ws][response-guards] "
        "fired=language_drift ... before='Durante tus años más "
        "tempranos en West St. Paul...' after='Let me say that in "
        "English.'`"
    )
    lines.append(
        "- **BUG-LIFEMAP-CONTEXT-TRUNCATION-01** — VRAM-GUARD trimmed "
        "input from 12138 → 8192 tokens on a Life-Map-era turn."
    )
    lines.append(
        "- **BUG-LIFEMAP-COMM-CONTROL-TRIM-01** — comm_control fired "
        "`reflection=echo_not_grounded` warnings; multiple eras "
        "in the Chrome run came back as single-question stubs."
    )
    lines.append(
        "- **BUG-FE-FACTS-ADD-PAYLOAD-SHAPE-422-01** — `POST "
        "/api/facts/add` continues to return 422 every turn; FE "
        "swallows the failure."
    )
    lines.append(
        "- **BUG-CHATWS-CONV-FK-01** — `[chat_ws][softened] turn_count "
        "increment failed` FOREIGN KEY constraint fires on switch_* "
        "conv_ids."
    )
    lines.append("")

    lines.append("## Operator log items needing follow-up")
    lines.append("")
    lines.append(
        "From OPERATOR-LOG-2026-06-17-18-54-54.md (RED block):"
    )
    lines.append("")
    lines.append(
        "- session_style picker radio count is 5 but validator expects "
        "4 (clear_direct was added; validator missed the update)."
    )
    lines.append(
        "- Media launcher cards count is 4 but validator expects 3."
    )
    lines.append(
        "- state.session.sessionStyle returns `oral_history` but a "
        "validator gate expected `undefined` — likely a stale guard."
    )
    lines.append("")
    lines.append(
        "AMBER block flagged Memory River tab as missing — that's the "
        "retired Kawa metaphor per CLAUDE.md design principle 1, so the "
        "operator-log gate itself is stale and should be removed, not "
        "the feature restored."
    )
    lines.append("")

    lines.append("## Recommended next action")
    lines.append("")
    if walk_topline == "PASS":
        lines.append(
            "Seven-era walk passed end-to-end. Open the per-era report "
            "at `docs/reports/john_baldy_seven_era_*.md` for the matrix "
            "score per era. Then triage the open bugs above in priority "
            "order: facts/add 422 is the silent-data-loss fix and "
            "should land first."
        )
    elif walk_topline == "FAIL":
        lines.append(
            "Seven-era walk failed end-to-end. Look at the per-era "
            "report at `docs/reports/john_baldy_seven_era_*.md` to see "
            "which eras passed and which broke. Most likely "
            "explanation: VRAM-GUARD truncation on a long-prompt era, "
            "or the Spanish-misfire fires on the era directive."
        )
    else:
        lines.append(
            "Seven-era walk skipped. Re-run with "
            "`HORNELORE_SKIP_SEVEN_ERA=0` (or unset) to exercise the "
            "live backend."
        )
    lines.append("")

    out.write_text("\n".join(lines), encoding="utf-8")
    return out


# ── Entry point ─────────────────────────────────────────────────────


def main() -> int:
    _hr("JOHN BALDY MASTER CHECK")
    print(f"  API base: {API_BASE}")
    print(f"  Repo:     {REPO_ROOT}")
    print()

    # Preflight: stack ping
    code, _ = _try_get(f"{API_BASE}/api/ping")
    if code != 200:
        print(
            f"  ✗ stack ping failed (HTTP {code}). Start the stack first: "
            "bash scripts/start_all.sh"
        )
        print()
        # We still continue so unit tests can run offline.

    unit_results = run_unit_tests()
    test_lab_results = probe_test_lab()
    walk_results = run_seven_era_walk()

    out = write_master_report(unit_results, test_lab_results, walk_results)
    _hr("MASTER REPORT")
    try:
        relp = out.relative_to(REPO_ROOT)
    except ValueError:
        relp = out
    print(f"  Wrote: {relp}")
    print()

    # Exit non-zero if any step failed (skipped steps don't fail)
    any_fail = (
        (not unit_results.get("skipped") and not unit_results.get("ok"))
        or (
            not walk_results.get("skipped")
            and walk_results.get("ok") is False
        )
    )
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
