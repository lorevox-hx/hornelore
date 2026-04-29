#!/usr/bin/env python3
"""Lori behavior/safety/story-surface harness.

Run from repo root with the API stack up for live tests:

  python scripts/eval/run_lori_behavior_harness.py --api http://localhost:8000 --mode deterministic
  python scripts/eval/run_lori_behavior_harness.py --api http://localhost:8000 --mode live

This harness intentionally favors clear bug exposure over perfect coverage.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import websockets  # type: ignore
except Exception:
    websockets = None

ROOT = Path.cwd()
DEFAULT_CASES = ROOT / "tests" / "fixtures" / "lori_behavior_cases.json"
OUT_DIR = ROOT / ".runtime" / "eval" / "lori_behavior"

COMPOUND_RX = re.compile(
    r"\b(what|when|where|who|why|how|which)\b[^?]*?\b(and|or|also|plus|maybe|perhaps)\b\s+"
    r"\b(what|when|where|who|why|how|which|do|does|did|is|are|was|were|will|would|can|could|should|has|have|had)\b",
    re.I,
)
MENU_RX = re.compile(r"\b(would\s+you\s+rather|or\s+we\s+could|which\s+path)\b", re.I)

@dataclass
class Result:
    lane: str
    case_id: str
    ok: bool
    failures: List[str]
    actual: str = ""
    elapsed_ms: int = 0
    likely_files: List[str] = None  # type: ignore

    def __post_init__(self):
        if self.likely_files is None:
            self.likely_files = []

LIKELY = {
    "memory": ["server/code/api/prompt_composer.py", "server/code/api/routers/chat_ws.py"],
    "listening": ["server/code/api/prompt_composer.py", "server/code/api/routers/chat_ws.py"],
    "safety": ["server/code/api/prompt_composer.py", "server/code/api/safety.py", "server/code/api/routers/chat_ws.py", "server/code/api/routers/safety_events.py", "server/code/api/db.py"],
    "extractor": ["server/code/api/routers/extract.py"],
    "surface": ["ui/js/life-map.js", "ui/hornelore1.0.html", "ui/js/app.js", "server/code/api/routers/chronology_accordion.py"],
}

def load_cases(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))

def count_questions(text: str) -> int:
    return text.count("?")

def word_count(text: str) -> int:
    return len(re.findall(r"\b\S+\b", text or ""))

def contains_any(text: str, needles: List[str]) -> bool:
    low = text.lower()
    return any(n.lower() in low for n in needles)

def check_text(case: Dict[str, Any], actual: str) -> List[str]:
    failures: List[str] = []
    low = actual.lower()
    for n in case.get("must_include", []):
        if n.lower() not in low:
            failures.append(f"missing required text: {n!r}")
    if case.get("must_include_any") and not contains_any(actual, case["must_include_any"]):
        failures.append(f"missing any of: {case['must_include_any']!r}")
    for n in case.get("must_not_include", []):
        if n.lower() in low:
            failures.append(f"forbidden text present: {n!r}")
    for pat in case.get("must_not_match", []):
        if re.search(pat, actual, re.I):
            failures.append(f"forbidden pattern present: {pat!r}")
    if "max_questions" in case and count_questions(actual) > int(case["max_questions"]):
        failures.append(f"too many questions: {count_questions(actual)} > {case['max_questions']}")
    if "max_words" in case and word_count(actual) > int(case["max_words"]):
        failures.append(f"too many words: {word_count(actual)} > {case['max_words']}")
    if COMPOUND_RX.search(actual):
        failures.append("compound-question pattern detected")
    if MENU_RX.search(actual):
        failures.append("menu-offer pattern detected")
    return failures

async def ws_turn(api: str, message: str, turn_mode: str, runtime71: Dict[str, Any], timeout: int = 180) -> Dict[str, Any]:
    if websockets is None:
        raise RuntimeError("Missing dependency: pip install websockets")
    ws_url = api.replace("http://", "ws://").replace("https://", "wss://").rstrip("/") + "/api/chat/ws"
    session_id = f"eval_{int(time.time()*1000)}"
    person_id = runtime71.get("person_id") or "eval_person"
    params = {
        "person_id": person_id,
        "runtime71": runtime71,
        "max_new_tokens": 180,
        "temperature": 0,
        "seed": 0,
    }
    chunks: List[str] = []
    final = ""
    done_payload: Dict[str, Any] = {}
    async with websockets.connect(ws_url, max_size=2_000_000) as ws:
        # drain connected message if present
        try:
            await asyncio.wait_for(ws.recv(), timeout=2)
        except Exception:
            pass
        await ws.send(json.dumps({
            "type": "sync_session",
            "person_id": person_id,
        }))
        try:
            await asyncio.wait_for(ws.recv(), timeout=2)
        except Exception:
            pass
        await ws.send(json.dumps({
            "type": "start_turn",
            "session_id": session_id,
            "message": message,
            "turn_mode": turn_mode,
            "params": params,
        }))
        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = await asyncio.wait_for(ws.recv(), timeout=max(1, int(deadline - time.time())))
            obj = json.loads(raw)
            if obj.get("type") == "token":
                chunks.append(obj.get("delta") or "")
            elif obj.get("type") == "error":
                chunks.append(f"[ERROR] {obj.get('message') or obj.get('code')}")
            elif obj.get("type") == "done":
                done_payload = obj
                final = obj.get("final_text") or "".join(chunks)
                break
    return {"text": final or "".join(chunks), "done": done_payload, "session_id": session_id}

def http_json(url: str) -> Dict[str, Any]:
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))

async def run_memory(cases: Dict[str, Any], api: str, live: bool) -> List[Result]:
    out: List[Result] = []
    for case in cases.get("memory_echo", []):
        start = time.time()
        try:
            if live:
                resp = await ws_turn(api, case["message"], case.get("turn_mode", "memory_echo"), case.get("runtime71", {}), timeout=45)
                actual = resp["text"]
                failures = check_text(case, actual)
                if resp["done"].get("turn_mode") != "memory_echo":
                    failures.append(f"done.turn_mode not memory_echo: {resp['done'].get('turn_mode')!r}")
                # deterministic readback should be quick; not hard fail if slow on WSL, but report it.
                elapsed = int((time.time() - start) * 1000)
                if elapsed > 5000:
                    failures.append(f"memory_echo slow ({elapsed}ms) — may still depend on model/load path")
            else:
                # Deterministic mode verifies the case spec itself can be evaluated; live WebSocket is needed for real output.
                actual = "deterministic-mode placeholder: run --mode live for WebSocket memory_echo"
                failures = []
        except Exception as e:
            actual = repr(e)
            failures = [f"exception: {e}"]
        out.append(Result("memory", case["id"], not failures, failures, actual[:800], int((time.time()-start)*1000), LIKELY["memory"]))
    return out

async def run_active_listening(cases: Dict[str, Any], api: str, live: bool) -> List[Result]:
    out: List[Result] = []
    if not live:
        return out
    for case in cases.get("active_listening", []):
        start = time.time()
        try:
            rt = dict(case.get("runtime71", {}))
            rt.setdefault("person_id", "eval_active_listening")
            resp = await ws_turn(api, case["message"], "interview", rt, timeout=180)
            actual = resp["text"]
            failures = check_text(case, actual)
        except Exception as e:
            actual = repr(e)
            failures = [f"exception: {e}"]
        out.append(Result("behavior", case["id"], not failures, failures, actual[:1000], int((time.time()-start)*1000), LIKELY["listening"]))
    return out

async def run_safety(cases: Dict[str, Any], api: str, live: bool) -> List[Result]:
    out: List[Result] = []
    if not live:
        # Test endpoint shape if enabled.
        start = time.time()
        try:
            count = http_json(api.rstrip("/") + "/api/operator/safety-events/count")
            failures = [] if "unacknowledged" in count else ["count endpoint missing unacknowledged"]
            actual = json.dumps(count)
        except Exception as e:
            failures = [f"operator safety endpoint unavailable: {e}"]
            actual = repr(e)
        out.append(Result("safety", "operator_endpoint_count", not failures, failures, actual, int((time.time()-start)*1000), LIKELY["safety"]))
        return out
    for case in cases.get("safety", []):
        start = time.time()
        try:
            rt = {"person_id": f"eval_{case['id']}", "speaker_name": "Harness Narrator", "identity_complete": True}
            before = None
            try:
                before = http_json(api.rstrip("/") + "/api/operator/safety-events/count").get("unacknowledged")
            except Exception:
                pass
            resp = await ws_turn(api, case["message"], "interview", rt, timeout=180)
            actual = resp["text"]
            failures = check_text(case, actual)
            try:
                after_payload = http_json(api.rstrip("/") + "/api/operator/safety-events?unacked_only=true&limit=5")
                events = after_payload.get("events", [])
                if not events:
                    failures.append("no operator safety event found after safety trigger")
                else:
                    ev = events[0]
                    bad_keys = [k for k in ev.keys() if k.lower() in ("confidence", "severity", "risk", "score")]
                    if bad_keys:
                        failures.append(f"operator event exposes score/risk key(s): {bad_keys}")
                    if len(str(ev.get("matched_phrase") or "")) > 61:
                        failures.append("matched_phrase longer than 60+ellipsis")
                    if len(str(ev.get("turn_excerpt") or "")) > 201:
                        failures.append("turn_excerpt longer than 200+ellipsis")
            except Exception as e:
                failures.append(f"operator safety event endpoint check failed: {e}")
        except Exception as e:
            actual = repr(e)
            failures = [f"exception: {e}"]
        out.append(Result("safety", case["id"], not failures, failures, actual[:1000], int((time.time()-start)*1000), LIKELY["safety"]))
    return out

def write_report(results: List[Result]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"ok": all(r.ok for r in results), "results": [asdict(r) for r in results]}
    (OUT_DIR / "latest.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["# Lori behavior harness report", "", f"Overall: {'PASS' if payload['ok'] else 'FAIL'}", ""]
    for r in results:
        mark = "PASS" if r.ok else "FAIL"
        lines.append(f"## {mark} — {r.lane} / {r.case_id}")
        lines.append(f"Elapsed: {r.elapsed_ms} ms")
        if r.failures:
            lines.append("Failures:")
            for f in r.failures:
                lines.append(f"- {f}")
        if r.actual:
            lines.append("Actual excerpt:")
            lines.append("```text")
            lines.append(r.actual[:1200])
            lines.append("```")
        if r.likely_files:
            lines.append("Likely files:")
            for f in r.likely_files:
                lines.append(f"- {f}")
        lines.append("")
    (OUT_DIR / "latest.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_DIR / 'latest.md'}")
    print(f"Overall: {'PASS' if payload['ok'] else 'FAIL'}")
    if not payload["ok"]:
        sys.exit(1)

async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--cases", default=str(DEFAULT_CASES))
    ap.add_argument("--mode", choices=["deterministic", "live"], default="live")
    args = ap.parse_args()
    cases = load_cases(Path(args.cases))
    live = args.mode == "live"
    results: List[Result] = []
    results += await run_memory(cases, args.api, live)
    results += await run_active_listening(cases, args.api, live)
    results += await run_safety(cases, args.api, live)
    write_report(results)

if __name__ == "__main__":
    asyncio.run(main())
