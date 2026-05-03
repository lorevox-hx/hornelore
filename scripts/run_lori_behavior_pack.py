#!/usr/bin/env python3
"""WO-LORI-RESPONSE-HARNESS-01 — Lori behavior test pack runner.

Sends each case's utterances to /api/operator/harness/interview-turn,
captures Lori's response per turn, and outputs a per-case report
showing both narrator-side and Lori-side text plus metadata.

Distinct from the extractor eval (which scores what got extracted).
This harness scores how Lori RESPONDS: question count, safety-mode
detection, db-lock deltas, error events, latency, and the literal
assistant text for human review.

Requires `HORNELORE_OPERATOR_HARNESS=1` in the server env. If the
endpoint is off, this script bails with a clear message.

Usage:
  ./scripts/run_lori_behavior_pack.py --tag v1 \\
      --api http://localhost:8000 \\
      --pack tests/fixtures/lori_behavior_pack_v1.json \\
      --output docs/reports/lori_behavior_pack_v1.json

Optional:
  --filter CASE_ID_PREFIX     run only matching cases (e.g. lori_b_00 → first 9)
  --limit N                   stop after N cases
  --turn-timeout-sec SECS     per-turn timeout (default 60)
  --pause-between-turns SECS  delay between turns within a case (default 0.5)

Output:
  docs/reports/lori_behavior_pack_<TAG>.json          — full per-case JSON
  docs/reports/lori_behavior_pack_<TAG>.console.txt   — readable report
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── HTTP helpers (stdlib only — keeps the harness easy to run) ────────────

def _http_get_json(url: str, timeout: float) -> Dict[str, Any]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body)


def _http_post_json(url: str, payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        method="POST",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body)


# ── Health probe ──────────────────────────────────────────────────────────

def _probe_health(api_base: str) -> None:
    """Bail loudly if the harness endpoint is off or the API is dead."""
    url = f"{api_base.rstrip('/')}/api/operator/harness/health"
    try:
        body = _http_get_json(url, timeout=10)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            sys.stderr.write(
                "[lori-pack] harness endpoint returned 404. Set "
                "HORNELORE_OPERATOR_HARNESS=1 in .env and restart the stack.\n"
            )
        else:
            sys.stderr.write(f"[lori-pack] HTTP {e.code} on health probe: {e}\n")
        sys.exit(2)
    except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
        sys.stderr.write(f"[lori-pack] cannot reach API at {api_base}: {e}\n")
        sys.exit(2)
    if not body.get("ok"):
        sys.stderr.write(f"[lori-pack] health probe replied non-ok: {body}\n")
        sys.exit(2)


# ── Per-case runner ───────────────────────────────────────────────────────

def _run_case(
    *,
    api_base: str,
    case: Dict[str, Any],
    turn_timeout_sec: float,
    pause_between_turns: float,
) -> Dict[str, Any]:
    """Send each utterance in case to the harness endpoint; return per-case
    record with full transcript and harness-reported metadata."""
    case_id = case["case_id"]
    person_id = case["narrator_id"]
    session_id = f"{person_id}-{int(time.time())}"
    session_style = case.get("session_style", "clear_direct")
    turn_mode = case.get("turn_mode", "interview")

    record: Dict[str, Any] = {
        "case_id": case_id,
        "category": case.get("category"),
        "persona": case.get("persona"),
        "narrator_id": person_id,
        "session_id": session_id,
        "session_style": session_style,
        "turn_mode": turn_mode,
        "lookout_for": case.get("lookout_for"),
        "turns": [],
        "case_total_elapsed_ms": 0,
        "case_errors": [],
        "case_db_locked_any_turn": False,
        "case_safety_mode_any_turn": False,
        "case_story_candidate_total_delta": 0,
        "case_safety_event_total_delta": 0,
    }

    case_start = time.monotonic()
    for idx, utt in enumerate(case["utterances"]):
        turn_id = f"{session_id}-t{idx + 1:02d}"
        url = f"{api_base.rstrip('/')}/api/operator/harness/interview-turn"
        payload = {
            "person_id": person_id,
            "text": utt,
            "session_id": session_id,
            "session_style": session_style,
            "turn_mode": turn_mode,
            "turn_id": turn_id,
            "timeout_seconds": turn_timeout_sec,
        }
        try:
            resp = _http_post_json(url, payload, timeout=turn_timeout_sec + 30)
            assistant = resp.get("assistant_text", "") or ""
            turn_record = {
                "turn_index": idx + 1,
                "turn_id": turn_id,
                "narrator_text": utt,
                "lori_text": assistant,
                "lori_word_count": len(assistant.split()),
                "lori_question_count": resp.get("question_count", 0),
                "safety_mode_detected": bool(resp.get("safety_mode_detected")),
                "db_locked": bool(resp.get("db_locked")),
                "elapsed_ms": int(resp.get("elapsed_ms") or 0),
                "raw_event_count": resp.get("raw_event_count"),
                "raw_event_types_first30": resp.get("raw_event_types") or [],
                "story_candidate_delta": resp.get("story_candidate_delta", 0),
                "safety_event_delta": resp.get("safety_event_delta", 0),
                "lock_event_delta": resp.get("lock_event_delta", 0),
                "errors": list(resp.get("errors") or []),
                "ok": bool(resp.get("ok")),
            }
            record["case_db_locked_any_turn"] |= turn_record["db_locked"]
            record["case_safety_mode_any_turn"] |= turn_record["safety_mode_detected"]
            record["case_story_candidate_total_delta"] += int(turn_record["story_candidate_delta"] or 0)
            record["case_safety_event_total_delta"] += int(turn_record["safety_event_delta"] or 0)
            if turn_record["errors"]:
                record["case_errors"].extend(turn_record["errors"])
            record["turns"].append(turn_record)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            record["turns"].append({
                "turn_index": idx + 1,
                "turn_id": turn_id,
                "narrator_text": utt,
                "lori_text": None,
                "ok": False,
                "errors": [f"transport: {exc}"],
            })
            record["case_errors"].append(f"turn{idx + 1}: {exc}")
            # Don't abort the case on a single transport hiccup; continue.
        if pause_between_turns > 0 and idx < len(case["utterances"]) - 1:
            time.sleep(pause_between_turns)

    record["case_total_elapsed_ms"] = int((time.monotonic() - case_start) * 1000)
    return record


# ── Console formatting ────────────────────────────────────────────────────

def _format_console(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    sep_outer = "=" * 78
    sep_inner = "─" * 78
    lines.append(sep_outer)
    lines.append(f"  WO-LORI-RESPONSE-HARNESS-01 — pack={report['pack_path']}  tag={report['tag']}")
    lines.append(sep_outer)
    s = report["summary"]
    lines.append(f"  Cases run:                {s['cases_run']}")
    lines.append(f"  Total turns:              {s['total_turns']}")
    lines.append(f"  Turns with errors:        {s['turns_with_errors']}")
    lines.append(f"  Cases hitting safety:     {s['cases_safety_mode_any_turn']}")
    lines.append(f"  Cases hitting db_locked:  {s['cases_db_locked_any_turn']}")
    lines.append(f"  Story candidate delta:    {s['total_story_candidate_delta']}")
    lines.append(f"  Safety event delta:       {s['total_safety_event_delta']}")
    lines.append(f"  Avg turn latency:         {s['avg_turn_latency_ms']} ms")
    lines.append(f"  Wall clock:               {s['wall_clock_ms']} ms")
    lines.append("")
    for case in report["cases"]:
        lines.append(sep_inner)
        lines.append(f"  CASE {case['case_id']}  [{case.get('category','?')}]  persona={case.get('persona','?')}")
        if case.get("lookout_for"):
            lines.append(f"    lookout_for: {case['lookout_for']}")
        lines.append(f"    session_style={case['session_style']}  turn_mode={case['turn_mode']}")
        if case["case_errors"]:
            lines.append(f"    errors: {case['case_errors']}")
        for t in case["turns"]:
            lines.append("")
            lines.append(f"    ── Turn {t['turn_index']}  ({t.get('elapsed_ms','?')} ms,  "
                         f"q_count={t.get('lori_question_count','?')},  "
                         f"safety={t.get('safety_mode_detected','?')},  "
                         f"db_locked={t.get('db_locked','?')})")
            lines.append(f"      narrator › {t['narrator_text']}")
            lori = t.get("lori_text")
            if lori is None:
                lines.append(f"      lori     › <<NO RESPONSE>>")
            else:
                # Wrap-friendly rendering: narrator may be long, lori usually shorter.
                # We show the full Lori text verbatim — that's the point.
                lori_render = lori.replace("\n", "\n                  ")
                lines.append(f"      lori     › {lori_render}")
            if t.get("errors"):
                lines.append(f"      errors   › {t['errors']}")
        lines.append("")
    lines.append(sep_outer)
    return "\n".join(lines) + "\n"


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description="Lori behavior test pack runner")
    p.add_argument("--tag", required=True, help="Output suffix (e.g. v1, v1-rerun)")
    p.add_argument("--api", default="http://localhost:8000", help="API base URL")
    p.add_argument("--pack", default="tests/fixtures/lori_behavior_pack_v1.json",
                   help="Path to behavior pack JSON")
    p.add_argument("--output", default=None,
                   help="Output JSON path (default: docs/reports/lori_behavior_pack_<TAG>.json)")
    p.add_argument("--filter", default=None,
                   help="Run only cases whose case_id starts with this prefix")
    p.add_argument("--limit", type=int, default=0,
                   help="Stop after N cases (0 = all)")
    p.add_argument("--turn-timeout-sec", type=float, default=60.0,
                   help="Per-turn timeout passed to harness endpoint (default 60s)")
    p.add_argument("--pause-between-turns", type=float, default=0.5,
                   help="Pause between turns within a case (seconds)")
    args = p.parse_args()

    pack_path = Path(args.pack).resolve()
    if not pack_path.exists():
        sys.stderr.write(f"[lori-pack] pack not found: {pack_path}\n")
        return 2
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    cases = pack.get("cases") or []
    if args.filter:
        cases = [c for c in cases if c.get("case_id", "").startswith(args.filter)]
    if args.limit and args.limit > 0:
        cases = cases[: args.limit]
    if not cases:
        sys.stderr.write("[lori-pack] no cases to run after filter/limit.\n")
        return 2

    out_path = (
        Path(args.output)
        if args.output
        else Path(f"docs/reports/lori_behavior_pack_{args.tag}.json")
    ).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Bail early if the harness endpoint is off — saves the operator
    # 30 minutes of wondering why nothing is happening.
    _probe_health(args.api)

    sys.stdout.write(
        f"[lori-pack] running {len(cases)} cases against {args.api} ...\n"
    )
    wall_start = time.monotonic()

    case_records: List[Dict[str, Any]] = []
    for case in cases:
        sys.stdout.write(f"[lori-pack]   case={case['case_id']} "
                         f"({case.get('category','?')}) "
                         f"turns={len(case.get('utterances') or [])}\n")
        sys.stdout.flush()
        rec = _run_case(
            api_base=args.api,
            case=case,
            turn_timeout_sec=args.turn_timeout_sec,
            pause_between_turns=args.pause_between_turns,
        )
        case_records.append(rec)

    wall_ms = int((time.monotonic() - wall_start) * 1000)

    # ── Roll up summary ───────────────────────────────────────────────────
    total_turns = sum(len(c["turns"]) for c in case_records)
    turns_with_errors = sum(
        1 for c in case_records for t in c["turns"] if t.get("errors")
    )
    avg_latency = (
        int(sum(t.get("elapsed_ms") or 0 for c in case_records for t in c["turns"]) / total_turns)
        if total_turns else 0
    )
    summary = {
        "cases_run": len(case_records),
        "total_turns": total_turns,
        "turns_with_errors": turns_with_errors,
        "cases_safety_mode_any_turn": sum(
            1 for c in case_records if c["case_safety_mode_any_turn"]
        ),
        "cases_db_locked_any_turn": sum(
            1 for c in case_records if c["case_db_locked_any_turn"]
        ),
        "total_story_candidate_delta": sum(
            c["case_story_candidate_total_delta"] for c in case_records
        ),
        "total_safety_event_delta": sum(
            c["case_safety_event_total_delta"] for c in case_records
        ),
        "avg_turn_latency_ms": avg_latency,
        "wall_clock_ms": wall_ms,
    }

    report = {
        "tag": args.tag,
        "api_base": args.api,
        "pack_path": str(pack_path),
        "wall_started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(wall_start)),
        "summary": summary,
        "cases": case_records,
    }

    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    console_path = out_path.with_suffix("").with_suffix(".console.txt")
    console_path.write_text(_format_console(report), encoding="utf-8")
    sys.stdout.write(
        f"[lori-pack] wrote {out_path}\n[lori-pack] wrote {console_path}\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
