#!/usr/bin/env python3
"""WO-EX-SENTENCE-DIAGRAM-STORY-SURVEY-01 — live story-clause survey harness.

Runs a large set of synthetic narrator utterances through:
  1) optional Lori chat path (/api/chat/ws), so the report records what was
     said to Lori and what Lori said back;
  2) optional extractor path (/api/extract-fields), so the report records what
     fields were used or missed;
  3) optional direct Story Clause Map builder, if api.services.utterance_frame
     is importable from server/code.

No DB writes are performed directly by this harness. The chat path may persist
turns because /api/chat/ws is the real runtime path. The extract path mirrors
existing extraction evals.

Example:
  python3 scripts/archive/run_sentence_diagram_story_survey.py \
    --api http://localhost:8000 \
    --cases data/qa/sentence_diagram_story_cases.json \
    --output docs/reports/sentence_diagram_story_survey_v1.json

For extractor-only no-GPU chat:
  python3 scripts/archive/run_sentence_diagram_story_survey.py --no-chat ...
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    # Supports scripts/archive/ and scripts/ placement.
    if here.parent.name == "archive":
        return here.parent.parent.parent
    if here.parent.name == "scripts":
        return here.parent.parent
    return Path.cwd()


def _add_server_code_to_path(repo: Path) -> None:
    server_code = repo / "server" / "code"
    if server_code.exists() and str(server_code) not in sys.path:
        sys.path.insert(0, str(server_code))


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _value_matches(actual: Any, expected_values: Iterable[str]) -> bool:
    a = _norm(actual)
    if not a:
        return False
    for expected in expected_values:
        e = _norm(expected)
        if not e:
            continue
        if e in a or a in e:
            return True
    return False


def _item_field(item: Dict[str, Any]) -> str:
    return str(item.get("fieldPath") or item.get("field_path") or "")


def _item_value(item: Dict[str, Any]) -> Any:
    return item.get("value")


def _score_expectations(items: List[Dict[str, Any]], case: Dict[str, Any]) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    must_not_results: List[Dict[str, Any]] = []

    for exp in case.get("expected_extract", []) or []:
        paths = [exp.get("fieldPath")]
        paths.extend(exp.get("alsoAccept") or [])
        paths = [p for p in paths if p]
        values = exp.get("anyOf") or []
        optional = bool(exp.get("optional"))
        matches = []
        for item in items:
            if _item_field(item) in paths and _value_matches(_item_value(item), values):
                matches.append(item)
        hit = bool(matches) or optional
        results.append({
            "fieldPath": exp.get("fieldPath"),
            "alsoAccept": exp.get("alsoAccept") or [],
            "anyOf": values,
            "optional": optional,
            "hit": hit,
            "matched_items": matches,
        })

    for bad in case.get("must_not_extract", []) or []:
        paths = [bad.get("fieldPath")]
        paths.extend(bad.get("alsoAccept") or [])
        paths = [p for p in paths if p]
        values = bad.get("anyOf") or []
        offenders = []
        for item in items:
            if _item_field(item) in paths and _value_matches(_item_value(item), values):
                offenders.append(item)
        must_not_results.append({
            "fieldPath": bad.get("fieldPath"),
            "anyOf": values,
            "violated": bool(offenders),
            "offenders": offenders,
        })

    required = [r for r in results if not r.get("optional")]
    expected_hits = sum(1 for r in required if r["hit"])
    expected_total = len(required)
    must_not_violations = sum(1 for r in must_not_results if r["violated"])
    passed = (expected_hits == expected_total) and must_not_violations == 0
    return {
        "expected_hits": expected_hits,
        "expected_total": expected_total,
        "must_not_violations": must_not_violations,
        "passed": passed,
        "expected_results": results,
        "must_not_results": must_not_results,
    }


def _post_json(url: str, payload: Dict[str, Any], timeout: int = 180) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"_error": f"HTTP {e.code}", "body": body[:2000]}
    except URLError as e:
        return {"_error": f"URL error: {e}"}
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {e}"}


def _extract(api: str, case: Dict[str, Any], person_id: str, session_id: str) -> Dict[str, Any]:
    payload = {
        "person_id": person_id,
        "session_id": session_id,
        "answer": case["user_text"],
        "current_section": case.get("current_section"),
        "current_target_path": case.get("current_target_path"),
        "current_era": case.get("current_era"),
        "current_pass": case.get("current_pass") or "pass1",
        "current_mode": case.get("current_mode") or "open",
        "transcript_source": "typed",
        "raw_transcript": case["user_text"],
        "normalized_transcript": case["user_text"],
        "profile_context": case.get("profile_context") or {},
    }
    if case.get("current_target_paths"):
        payload["current_target_paths"] = case["current_target_paths"]
    started = time.time()
    resp = _post_json(api.rstrip("/") + "/api/extract-fields", payload)
    elapsed_ms = int((time.time() - started) * 1000)
    items = resp.get("items") if isinstance(resp, dict) else []
    return {
        "elapsed_ms": elapsed_ms,
        "payload": payload,
        "response": resp,
        "items": items if isinstance(items, list) else [],
        "error": resp.get("_error") if isinstance(resp, dict) else "non-dict response",
    }


def _direct_frame(case: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from api.services.utterance_frame import build_frame  # type: ignore
        frame = build_frame(case["user_text"])
        if hasattr(frame, "to_dict"):
            return {"available": True, "frame": frame.to_dict()}
        return {"available": True, "frame": frame}
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}


async def _chat_one(ws_url: str, case: Dict[str, Any], person_id: str, session_id: str, timeout_s: int = 180) -> Dict[str, Any]:
    try:
        import websockets  # type: ignore
    except Exception as exc:
        return {
            "skipped": True,
            "error": "Python package 'websockets' is not importable in this environment. Run with --no-chat or install websockets.",
            "import_error": str(exc),
        }

    events: List[Dict[str, Any]] = []
    assistant_chunks: List[str] = []
    final_text = ""
    started = time.time()
    try:
        async with websockets.connect(ws_url, ping_interval=None, close_timeout=2) as ws:
            async def recv_until(predicate, soft_limit: int = 20):
                for _ in range(soft_limit):
                    raw = await asyncio.wait_for(ws.recv(), timeout=timeout_s)
                    try:
                        ev = json.loads(raw)
                    except Exception:
                        ev = {"type": "_raw", "raw": raw}
                    events.append(ev)
                    if predicate(ev):
                        return ev
                return None

            # Drain initial connected status, then verify session.
            try:
                await recv_until(lambda ev: ev.get("type") == "status", soft_limit=3)
            except Exception:
                pass
            await ws.send(json.dumps({"type": "sync_session", "person_id": person_id}))
            try:
                await recv_until(lambda ev: ev.get("type") == "session_verified", soft_limit=5)
            except Exception:
                pass

            params = {
                "person_id": person_id,
                "session_style": case.get("session_style") or "clear_direct",
                "currentMode": case.get("session_style") or "clear_direct",
                "max_new_tokens": case.get("max_new_tokens") or 140,
                "temperature": case.get("temperature") or 0.2,
            }
            await ws.send(json.dumps({
                "type": "start_turn",
                "session_id": session_id,
                "message": case["user_text"],
                "turn_mode": "interview",
                "params": params,
            }))

            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout_s)
                try:
                    ev = json.loads(raw)
                except Exception:
                    ev = {"type": "_raw", "raw": raw}
                events.append(ev)
                typ = ev.get("type")
                if typ == "token":
                    assistant_chunks.append(str(ev.get("delta") or ev.get("text") or ""))
                elif typ == "done":
                    final_text = str(ev.get("final_text") or "".join(assistant_chunks))
                    break
                elif typ == "error":
                    # Keep listening for done if backend sends it; otherwise the timeout catches it.
                    pass
    except Exception as exc:
        return {
            "skipped": False,
            "error": f"{type(exc).__name__}: {exc}",
            "events": events[-20:],
            "assistant_text": final_text or "".join(assistant_chunks),
            "elapsed_ms": int((time.time() - started) * 1000),
        }

    return {
        "skipped": False,
        "error": None,
        "assistant_text": final_text or "".join(assistant_chunks),
        "elapsed_ms": int((time.time() - started) * 1000),
        "raw_event_count": len(events),
        "raw_event_types": [e.get("type") for e in events],
    }


def _lori_grounding(case: Dict[str, Any], assistant_text: str) -> Dict[str, Any]:
    terms = case.get("lori_expectation") or []
    if not terms:
        return {"checked": False}
    hits = [t for t in terms if _norm(t) in _norm(assistant_text)]
    return {"checked": True, "terms": terms, "hits": hits, "misses": [t for t in terms if t not in hits], "passed": bool(hits)}


def _console(report: Dict[str, Any]) -> str:
    s = report["summary"]
    lines = []
    lines.append("=" * 78)
    lines.append("WO-EX-SENTENCE-DIAGRAM-STORY-SURVEY-01")
    lines.append("=" * 78)
    lines.append(f"cases:              {s['total_cases']}")
    lines.append(f"extract_passed:     {s['extract_passed']}/{s['extract_ran']}")
    lines.append(f"must_not_violations:{s['must_not_violations']}")
    lines.append(f"chat_ran:           {s['chat_ran']}")
    lines.append(f"chat_errors:        {s['chat_errors']}")
    lines.append(f"frame_available:    {s['frame_available']}")
    lines.append("")
    lines.append("Top missed expected fields:")
    for k, v in s["misses_by_field"].items():
        lines.append(f"  {k:36s} {v}")
    lines.append("")
    lines.append("Cases with misses or violations:")
    for case in report["cases"]:
        sc = case.get("score", {})
        if not sc.get("passed", True):
            miss = [r["fieldPath"] for r in sc.get("expected_results", []) if not r.get("hit")]
            bad = [r["fieldPath"] for r in sc.get("must_not_results", []) if r.get("violated")]
            lines.append(f"  {case['id']} [{case.get('group')}] misses={miss} must_not={bad}")
            lines.append(f"    said: {case['user_text'][:180]}")
            at = (case.get("chat") or {}).get("assistant_text") or ""
            if at:
                lines.append(f"    lori: {at[:180]}")
    lines.append("")
    lines.append("Report includes per-case: user_text, assistant_text, frame, extraction payload, raw items, expected hits/misses.")
    return "\n".join(lines) + "\n"


async def _amain(args: argparse.Namespace) -> int:
    repo = _repo_root()
    _add_server_code_to_path(repo)
    cases_path = Path(args.cases)
    if not cases_path.is_absolute():
        cases_path = repo / cases_path
    data = json.loads(cases_path.read_text(encoding="utf-8"))
    cases = data.get("cases", [])
    if args.group:
        groups = set(args.group.split(","))
        cases = [c for c in cases if c.get("group") in groups]
    if args.max_cases:
        cases = cases[: args.max_cases]

    person_id = args.person_id or f"sentence-diagram-harness-{uuid.uuid4()}"
    session_base = args.session_id or f"sentence-diagram-{int(time.time())}"
    ws_url = args.ws_url or args.api.rstrip("/").replace("http://", "ws://").replace("https://", "wss://") + "/api/chat/ws"

    results = []
    misses_by_field: Dict[str, int] = {}
    extract_ran = extract_passed = must_not_violations = 0
    chat_ran = chat_errors = 0
    frame_available_count = 0

    for i, case in enumerate(cases, 1):
        session_id = f"{session_base}-{i:03d}"
        row: Dict[str, Any] = {
            "id": case.get("id"),
            "group": case.get("group"),
            "title": case.get("title"),
            "watch": case.get("watch"),
            "user_text": case.get("user_text"),
            "expected_extract": case.get("expected_extract", []),
            "must_not_extract": case.get("must_not_extract", []),
        }

        if args.frame:
            frame = _direct_frame(case)
            row["utterance_frame"] = frame
            if frame.get("available"):
                frame_available_count += 1

        if args.chat:
            chat = await _chat_one(ws_url, case, person_id=person_id, session_id=session_id, timeout_s=args.timeout)
            row["chat"] = chat
            if not chat.get("skipped"):
                chat_ran += 1
            if chat.get("error"):
                chat_errors += 1
            row["lori_grounding"] = _lori_grounding(case, chat.get("assistant_text") or "")

        if args.extract:
            extract = _extract(args.api, case, person_id=person_id, session_id=session_id)
            row["extract"] = extract
            extract_ran += 1
            score = _score_expectations(extract.get("items") or [], case)
            row["score"] = score
            if score["passed"]:
                extract_passed += 1
            must_not_violations += score["must_not_violations"]
            for r in score["expected_results"]:
                if not r.get("hit") and not r.get("optional"):
                    misses_by_field[r["fieldPath"]] = misses_by_field.get(r["fieldPath"], 0) + 1

        print(f"[{i:02d}/{len(cases):02d}] {case.get('id')} done", flush=True)
        results.append(row)

        if args.sleep:
            await asyncio.sleep(args.sleep)

    misses_by_field = dict(sorted(misses_by_field.items(), key=lambda kv: (-kv[1], kv[0])))
    report = {
        "_wo": "WO-EX-SENTENCE-DIAGRAM-STORY-SURVEY-01",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "api": args.api,
        "ws_url": ws_url,
        "cases_file": str(cases_path),
        "person_id": person_id,
        "session_base": session_base,
        "summary": {
            "total_cases": len(cases),
            "extract_ran": extract_ran,
            "extract_passed": extract_passed,
            "must_not_violations": must_not_violations,
            "chat_ran": chat_ran,
            "chat_errors": chat_errors,
            "frame_available": frame_available_count,
            "misses_by_field": misses_by_field,
        },
        "cases": results,
    }
    report["cases"] = results

    out = Path(args.output)
    if not out.is_absolute():
        out = repo / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    console = _console(report)
    console_path = out.with_suffix(".console.txt")
    console_path.write_text(console, encoding="utf-8")
    print(console)
    print(f"JSON report:    {out}")
    print(f"Console report: {console_path}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run sentence-diagram story survey through Lori chat and extractor.")
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--ws-url", default=None)
    parser.add_argument("--cases", default="data/qa/sentence_diagram_story_cases.json")
    parser.add_argument("--output", default="docs/reports/sentence_diagram_story_survey_v1.json")
    parser.add_argument("--person-id", default=None)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--sleep", type=float, default=0.0)
    parser.add_argument("--max-cases", type=int, default=0)
    parser.add_argument("--group", default="", help="Comma-separated group filter, e.g. dob_pob,pets_cardinality")
    parser.add_argument("--chat", dest="chat", action="store_true", default=True)
    parser.add_argument("--no-chat", dest="chat", action="store_false")
    parser.add_argument("--extract", dest="extract", action="store_true", default=True)
    parser.add_argument("--no-extract", dest="extract", action="store_false")
    parser.add_argument("--frame", dest="frame", action="store_true", default=True)
    parser.add_argument("--no-frame", dest="frame", action="store_false")
    args = parser.parse_args(argv)
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
