#!/usr/bin/env python3
"""WO-QA-01 — Hornelore Quality Harness runner.

Runs the two synthetic test narrators through a purposive config grid and a
fixed scenario set, talking to the live /api/chat/ws path exactly as the UI
does. Primary metric is archive yield (proposal rows produced by the real
extraction pipeline). Secondary metrics are TTFT, tok/s, recovery, and
contamination PASS/FAIL.

Critical edits applied (per WO-QA-01 review):
  1. TOTAL_TURN_TIMEOUT_SECONDS = 180 (was 60 — too tight for Scenario D).
  2. Persistent per-narrator session_id threaded through the contamination
     test so the "return to narrator A" step actually has history to reference.
  3. TTS drift is reported as (None, None) — the placeholder drift stub was
     removed until real TTS timestamp capture is wired (see WO-QA-01B).
  4. Contamination anchor words are unique ("schoolhouse/Helena" vs
     "letters/wartime") so substring matching is reliable in both directions.

Env:
  HORNELORE_API_BASE       default http://127.0.0.1:8000
  HORNELORE_WS_URL         default ws://127.0.0.1:8000/api/chat/ws
  HORNELORE_TEST_LAB_ROOT  default /mnt/c/hornelore_data/test_lab

Usage:
  python3 scripts/test_lab_runner.py
  python3 scripts/test_lab_runner.py --compare-to 20260414_103500
  python3 scripts/test_lab_runner.py --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import statistics
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx
import websockets

# ── Endpoints & paths ─────────────────────────────────────────────
API_BASE = os.getenv("HORNELORE_API_BASE", "http://127.0.0.1:8000")
WS_URL = os.getenv("HORNELORE_WS_URL", "ws://127.0.0.1:8000/api/chat/ws")
DATA_ROOT = Path(os.getenv(
    "HORNELORE_TEST_LAB_ROOT",
    "/mnt/c/hornelore_data/test_lab",
))
PEOPLE_ENDPOINT = f"{API_BASE}/api/people"
EXTRACT_ENDPOINT = f"{API_BASE}/api/extract-fields"

# ── Timeouts (EDIT #1) ────────────────────────────────────────────
# Inter-token recv timeout: 30s. If no token arrives within 30s of the
# previous one the server is stuck — fail the turn.
RECV_TIMEOUT_SECONDS = 30.0
# Total turn timeout: 180s. At HF INT4 on a 5080 ~30-40 tok/s; a full
# 2048-token Scenario D response takes 55-70s best case. 60s would fail
# every stress run. 180s gives headroom without hiding genuine slow paths.
TOTAL_TURN_TIMEOUT_SECONDS = 180.0
RETRY_BACKOFF_SECONDS = 7.0
MAX_RETRIES = 1

# ── Fixed runtime71 (prompt control) ──────────────────────────────
# The harness sends a minimal STABLE runtime71 so configs are compared
# under identical prompt-composer input. The real UI varies these every
# turn, which would entangle sampling effects with cognitive-state
# effects. Keep this constant.
DEFAULT_RUNTIME71 = {
    "current_pass": "pass1",
    "current_era": None,
    "current_mode": "open",
    "affect_state": "neutral",
    "affect_confidence": 0.0,
    "cognitive_mode": None,
    "fatigue_score": 0,
    "assistant_role": "interviewer",
    "identity_complete": True,
    "identity_phase": "complete",
    "effective_pass": "pass1",
}

# ── Scenarios ─────────────────────────────────────────────────────
SCENARIOS = [
    {"id": "scn_5_word",     "prompt": "Answer in exactly 5 words. Where were you born?"},
    {"id": "scn_100_word",   "prompt": "Answer in about 100 words. Tell me about your childhood home."},
    {"id": "scn_200_word",   "prompt": "Answer in about 200 words. Describe your early family life."},
    {"id": "scn_1000_word",  "prompt": "Write about 1000 words. Tell the story of your early life in detail."},
    {"id": "scn_repetition", "prompt": "Respond helpfully and do not loop: hello hello hello hello help help help help"},
]

# Real-prompt replay — pulled from typical Hornelore interview patterns
REAL_PROMPT_REPLAY = [
    "Tell me about your childhood in one paragraph.",
    "What was your mother like when you were young?",
    "Tell me one concrete memory from your teenage years.",
]

# ── Contamination test (EDIT #4: unique anchor words) ─────────────
# Structured narrator turns anchor on "schoolhouse in Helena".
# Storyteller narrator turns anchor on "wartime letters".
# Return question asks narrator A what they were discussing.
# PASS if answer mentions schoolhouse/Helena, FAIL if mentions letters/wartime.
CONTAMINATION_SCRIPT = [
    ("structured", [
        "Tell me about the old schoolhouse in Helena where you went as a child.",
        "What did the inside of that Helena schoolhouse look like?",
        "Who was your favorite teacher at the Helena schoolhouse?",
    ]),
    ("storyteller", [
        "Tell me about your father's wartime letters home.",
        "Where did he write those wartime letters from?",
        "How did your mother read those wartime letters to you?",
    ]),
]
CONTAMINATION_RETURN_STYLE = "structured"
CONTAMINATION_RETURN_PROMPT = (
    "Thinking back to what we were just discussing — remind me, "
    "what place and time in your life were we talking about?"
)

# Anchor-word sets for contamination detection
STRUCTURED_ANCHORS = ("schoolhouse", "helena")
STORYTELLER_ANCHORS = ("letters", "wartime", "father's")


# ── Data structures ───────────────────────────────────────────────
@dataclass
class TurnResult:
    response: str
    ttft_ms: int | None
    total_ms: int
    tokens_per_sec: float | None
    token_timestamps_ms: list[int] = field(default_factory=list)
    blocked: str | None = None
    oom: bool = False
    cancelled: bool = False


@dataclass
class MetricRow:
    narrator_style: str
    narrator_id: str
    config_id: str
    scenario_id: str
    prompt: str
    response: str
    proposal_row_count: int
    ttft_ms: int | None
    total_ms: int
    tokens_per_sec: float | None
    token_timestamps_ms: list[int]
    blocked: str | None
    oom: bool
    contamination_pass: bool | None
    coherence_score: int | None
    adherence_score: int | None
    style_score: int | None
    stability_score: int | None
    tts_pass: bool | None
    tts_drift_ms: float | None


# ── Utilities ─────────────────────────────────────────────────────
def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


async def fetch_people() -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(PEOPLE_ENDPOINT)
        resp.raise_for_status()
        data = resp.json()
    # /api/people returns {"people": [...]}
    if isinstance(data, dict) and "people" in data:
        return data["people"]
    if isinstance(data, list):
        return data
    raise RuntimeError(f"Unexpected /api/people shape: {type(data).__name__}")


TEST_NARRATOR_IDS = {
    "structured":  "test-structured-001",
    "storyteller": "test-storyteller-001",
}


def find_test_narrators(people: list[dict[str, Any]]) -> dict[str, str]:
    """Match by the fixed template IDs seeded from data/narrator_templates/.

    /api/people returns people-table rows only (no profile_json), so we
    cannot match on basics.style here. The seed script sets narrator_type
    to 'test' and writes well-known IDs, so we key on IDs. We also
    cross-check narrator_type as an assertion.
    """
    found: dict[str, str] = {}
    by_id = {(p.get("id") or p.get("person_id")): p for p in people}
    for style, pid in TEST_NARRATOR_IDS.items():
        row = by_id.get(pid)
        if not row:
            continue
        if (row.get("narrator_type") or "").lower() != "test":
            # Seeded narrator exists but its narrator_type was changed —
            # refuse to use it to avoid accidentally writing to a live record
            continue
        found[style] = pid
    if len(found) != len(TEST_NARRATOR_IDS):
        missing = [s for s in TEST_NARRATOR_IDS if s not in found]
        raise RuntimeError(
            f"Synthetic test narrators missing: {missing}. "
            f"Run `python3 scripts/seed_test_narrators.py` and confirm rows exist "
            f"in the people table with narrator_type='test'."
        )
    return found


def build_sync_session(person_id: str) -> dict[str, Any]:
    return {"type": "sync_session", "person_id": person_id}


def build_start_turn(
    *,
    person_id: str,
    session_id: str,
    message: str,
    sampling: dict[str, Any],
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "person_id": person_id,
        "temperature": sampling["temperature"],
        "top_p": sampling["top_p"],
        "max_new_tokens": sampling["max_new_tokens"],
        "runtime71": DEFAULT_RUNTIME71,
    }
    if sampling.get("repetition_penalty") is not None:
        params["repetition_penalty"] = sampling["repetition_penalty"]
    return {
        "type": "start_turn",
        "session_id": session_id,
        "message": message,
        "params": params,
    }


async def extract_yield(person_id: str, text: str) -> int:
    """Count proposal rows produced by /api/extract-fields on a response.

    The extract endpoint expects:
      {person_id, answer, session_id?, current_section?, current_target_path?, profile_context?}
    and returns:
      {items: [ExtractedItem], method, raw_llm_output?}
    Yield = len(items).
    """
    if not text or not text.strip():
        return 0
    payload = {
        "person_id": person_id,
        "answer": text,
    }
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(EXTRACT_ENDPOINT, json=payload)
            resp.raise_for_status()
            data = resp.json()
        if isinstance(data, dict):
            items = data.get("items")
            if isinstance(items, list):
                return len(items)
    except Exception as exc:
        # Log but don't crash — yield=0 is a legitimate value
        print(f"  [warn] extract_yield failed: {exc}", file=sys.stderr)
    return 0


# ── Heuristic scoring (objective where possible) ──────────────────
def score_adherence(scenario_id: str, response: str) -> int | None:
    wc = word_count(response)
    if scenario_id == "scn_5_word":
        return 5 if wc == 5 else max(1, 5 - abs(wc - 5))
    if scenario_id == "scn_100_word":
        return max(1, 5 - min(4, abs(wc - 100) // 20))
    if scenario_id == "scn_200_word":
        return max(1, 5 - min(4, abs(wc - 200) // 35))
    if scenario_id == "scn_1000_word":
        return max(1, 5 - min(4, abs(wc - 1000) // 125))
    return None  # no length target


def score_style(style: str, response: str) -> int | None:
    if not response.strip():
        return 1
    sentences = max(1, len(re.findall(r"[.!?]+", response)))
    avg = word_count(response) / sentences
    if style == "structured":
        return 5 if avg <= 18 else max(1, 5 - int((avg - 18) // 6))
    if style == "storyteller":
        return 5 if avg >= 14 else max(1, 5 - int((14 - avg) // 4))
    return None


def score_coherence(response: str) -> int | None:
    """Crude signal — only flags obvious breakage; manual review recommended.

    Set to None rather than a middling value when the signal is noise.
    """
    if not response.strip():
        return 1
    # Looping detector: same word repeated 4+ times in a row
    if re.search(r"\b(\w+)\b(?:\s+\1\b){3,}", response, flags=re.I):
        return 1
    if len(response) < 30:
        return 2
    return None  # insufficient signal for a gradient — let humans grade if needed


def score_stability(pre_ttft: int | None, post_ttft: int | None) -> int | None:
    """Binary pass/fail at the 15% degradation line, reported on a 1-5 scale."""
    if pre_ttft is None or post_ttft is None:
        return None
    if post_ttft <= int(pre_ttft * 1.15):
        return 5
    return 1


def tts_drift_placeholder(_text: str) -> tuple[None, None]:
    """EDIT #3: TTS drift measurement is not implemented in WO-QA-01.

    The earlier stub returned a fake 0-drift PASS regardless of reality.
    That was worse than no data. Defer to WO-QA-01B, which will wire
    real TTS chunk timestamps from _wo11eTtsPlaybackStarted.
    """
    return None, None


# ── WebSocket turn ─────────────────────────────────────────────────
async def recv_json_with_timeout(ws) -> dict[str, Any]:
    raw = await asyncio.wait_for(ws.recv(), timeout=RECV_TIMEOUT_SECONDS)
    return json.loads(raw)


async def run_turn_once(
    *,
    person_id: str,
    prompt: str,
    sampling: dict[str, Any],
    session_id: str | None = None,  # EDIT #2: accept caller-provided session_id
) -> TurnResult:
    """Execute one turn over the live /api/chat/ws path.

    If session_id is None, a fresh per-turn ID is generated (isolation).
    If caller provides one, it is reused — needed by the contamination
    test so the "return" question sees prior history.
    """
    sid = session_id or f"testlab_{uuid.uuid4().hex[:12]}"

    start = time.perf_counter()
    first_token_at: float | None = None
    token_timestamps_ms: list[int] = []
    deltas: list[str] = []
    final_text: str | None = None
    blocked: str | None = None
    oom = False
    cancelled = False

    async def _inner() -> TurnResult:
        nonlocal first_token_at, final_text, blocked, oom, cancelled

        async with websockets.connect(WS_URL, max_size=16 * 1024 * 1024) as ws:
            # Handshake
            await ws.send(json.dumps(build_sync_session(person_id)))
            while True:
                msg = await recv_json_with_timeout(ws)
                if msg.get("type") == "status":
                    continue
                if msg.get("type") == "session_verified":
                    break
                # Any other type at handshake is unexpected
                if msg.get("type") == "error":
                    raise RuntimeError(f"WS handshake error: {msg}")

            # Turn
            await ws.send(json.dumps(build_start_turn(
                person_id=person_id,
                session_id=sid,
                message=prompt,
                sampling=sampling,
            )))

            while True:
                msg = await recv_json_with_timeout(ws)
                mt = msg.get("type")

                if mt == "status":
                    continue

                if mt == "token":
                    delta = msg.get("delta", "")
                    if delta:
                        now = time.perf_counter()
                        if first_token_at is None:
                            first_token_at = now
                        token_timestamps_ms.append(int((now - start) * 1000))
                        deltas.append(delta)
                    continue

                if mt == "done":
                    final_text = msg.get("final_text")
                    blocked = msg.get("blocked")
                    oom = bool(msg.get("oom", False))
                    cancelled = bool(msg.get("cancelled", False))
                    break

                if mt == "error":
                    code = msg.get("code", "UNKNOWN")
                    if code == "VRAM_PRESSURE":
                        blocked = "vram_pressure"
                    elif code == "CUDA_OOM":
                        oom = True
                    raise RuntimeError(f"WS error {code}: {msg.get('message','')[:160]}")

        end = time.perf_counter()
        ttft = int((first_token_at - start) * 1000) if first_token_at else None
        total = int((end - start) * 1000)
        tps = None
        if token_timestamps_ms and total > 0:
            tps = len(token_timestamps_ms) / (total / 1000.0)
        response = final_text if final_text is not None else "".join(deltas)
        return TurnResult(
            response=response,
            ttft_ms=ttft,
            total_ms=total,
            tokens_per_sec=tps,
            token_timestamps_ms=token_timestamps_ms,
            blocked=blocked,
            oom=oom,
            cancelled=cancelled,
        )

    return await asyncio.wait_for(_inner(), timeout=TOTAL_TURN_TIMEOUT_SECONDS)


async def run_turn_with_retry(
    *,
    person_id: str,
    prompt: str,
    sampling: dict[str, Any],
    session_id: str | None = None,
) -> TurnResult:
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            result = await run_turn_once(
                person_id=person_id,
                prompt=prompt,
                sampling=sampling,
                session_id=session_id,
            )
            # VRAM / OOM backoff-retry
            if (result.blocked == "vram_pressure" or result.oom) and attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS)
                continue
            return result
        except asyncio.TimeoutError as exc:
            last_exc = exc
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS)
                continue
            raise RuntimeError(
                f"Turn timeout after {TOTAL_TURN_TIMEOUT_SECONDS}s for prompt: {prompt[:80]!r}"
            ) from exc
        except Exception as exc:
            last_exc = exc
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS)
                continue
            raise
    assert last_exc is not None
    raise last_exc


# ── Contamination test (EDIT #2: sticky session_ids) ──────────────
async def run_contamination_test(
    narrator_ids: dict[str, str],
    sampling: dict[str, Any],
) -> bool:
    """Run the contamination sequence with persistent session_ids.

    Each narrator gets its OWN session_id that persists across all its
    turns within this test run, so chat_ws.py::export_turns(conv_id)
    returns real history on the return question.
    """
    # Sticky session_ids scoped to this contamination run
    sid_map = {
        "structured":  f"contam_struct_{uuid.uuid4().hex[:8]}",
        "storyteller": f"contam_story_{uuid.uuid4().hex[:8]}",
    }

    for style, turns in CONTAMINATION_SCRIPT:
        pid = narrator_ids[style]
        sid = sid_map[style]
        for prompt in turns:
            await run_turn_with_retry(
                person_id=pid,
                prompt=prompt,
                sampling=sampling,
                session_id=sid,
            )

    # Return question uses the SAME session_id as the structured turns
    result = await run_turn_with_retry(
        person_id=narrator_ids[CONTAMINATION_RETURN_STYLE],
        prompt=CONTAMINATION_RETURN_PROMPT,
        sampling=sampling,
        session_id=sid_map[CONTAMINATION_RETURN_STYLE],
    )

    low = result.response.lower()
    # PASS: mentions a structured-side anchor (had history, got it right)
    # FAIL: mentions a storyteller-side anchor (cross-conv contamination)
    hit_structured = any(a in low for a in STRUCTURED_ANCHORS)
    hit_storyteller = any(a in low for a in STORYTELLER_ANCHORS)
    if hit_storyteller:
        return False
    return hit_structured


# ── Summarization / ranking ───────────────────────────────────────
def summarize_scores(metrics: list[MetricRow]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[MetricRow]] = {}
    for row in metrics:
        grouped.setdefault((row.narrator_style, row.config_id), []).append(row)

    out: list[dict[str, Any]] = []
    for (style, config_id), rows in grouped.items():
        yield_sum = sum(r.proposal_row_count for r in rows)
        ttfts = [r.ttft_ms for r in rows if r.ttft_ms is not None]
        tps = [r.tokens_per_sec for r in rows if r.tokens_per_sec is not None]
        contam_rows = [r for r in rows if r.scenario_id == "scn_contamination"]
        contam_pass = all(r.contamination_pass is not False for r in contam_rows)
        human_vals = [
            s for r in rows for s in (
                r.coherence_score, r.adherence_score, r.style_score, r.stability_score,
            ) if s is not None
        ]
        blocked_count = sum(1 for r in rows if r.blocked or r.oom)
        out.append({
            "narrator_style": style,
            "config_id": config_id,
            "proposal_row_yield": yield_sum,
            "avg_ttft_ms": round(statistics.mean(ttfts), 2) if ttfts else None,
            "avg_tokens_per_sec": round(statistics.mean(tps), 2) if tps else None,
            "contamination_pass": contam_pass,
            "avg_human_score": round(statistics.mean(human_vals), 2) if human_vals else None,
            "blocked_cells": blocked_count,
        })
    # Priority: contamination PASS > yield DESC > TTFT ASC
    out.sort(key=lambda x: (
        not x["contamination_pass"],
        -x["proposal_row_yield"],
        x["avg_ttft_ms"] if x["avg_ttft_ms"] is not None else 10**9,
    ))
    return out


def compare_runs(current: list[dict[str, Any]], baseline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prev_map = {(r["narrator_style"], r["config_id"]): r for r in baseline}
    rows = []
    for row in current:
        key = (row["narrator_style"], row["config_id"])
        prev = prev_map.get(key)
        if not prev:
            continue
        rows.append({
            "narrator_style": row["narrator_style"],
            "config_id": row["config_id"],
            "yield_delta": row["proposal_row_yield"] - prev.get("proposal_row_yield", 0),
            "ttft_delta_ms": (
                None if row["avg_ttft_ms"] is None or prev.get("avg_ttft_ms") is None
                else round(row["avg_ttft_ms"] - prev["avg_ttft_ms"], 2)
            ),
            "contamination_delta": f"{prev.get('contamination_pass')} → {row['contamination_pass']}",
        })
    return rows


# ── Pre-flight (WO-QA-01 review addition) ─────────────────────────
async def preflight_check(narrator_id: str) -> None:
    """Light smoke-test of the chat_ws pipeline before the real matrix.

    Original intent was to verify MAX_NEW_TOKENS_CHAT_HARD raised — but that
    conflates cap size with model output length, and a narrator in character
    may legitimately respond short to "count 1 to 500." The real signal is
    just: does the pipeline return ANY tokens? If yes, things are wired.
    The cap is a protection, not a pass/fail condition.
    """
    print("[preflight] smoke-testing chat_ws pipeline...")
    try:
        r = await run_turn_once(
            person_id=narrator_id,
            prompt="Say hello in one short sentence.",
            sampling={
                "temperature": 0.1,
                "top_p": 0.9,
                "repetition_penalty": 1.0,
                "max_new_tokens": 128,
            },
        )
    except Exception as exc:
        raise RuntimeError(f"[preflight] WS turn failed: {exc}") from exc

    n = len(r.token_timestamps_ms)
    text = (r.response or "")[:120]
    print(f"[preflight] streamed {n} tokens, response starts: {text!r}")
    if n < 3:
        raise RuntimeError(
            f"[preflight] FAILED — only {n} tokens streamed. Something is "
            f"wrong with chat_ws or the model isn't loaded."
        )
    print("[preflight] OK")


# ── Main ──────────────────────────────────────────────────────────
async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--configs", default="scripts/test_lab_configs.json")
    parser.add_argument("--compare-to", default=None)
    parser.add_argument("--run-label", default=None)
    parser.add_argument("--dry-run", action="store_true",
                        help="Run one cell end-to-end to verify plumbing, then exit.")
    parser.add_argument("--skip-preflight", action="store_true",
                        help="Skip the MAX_NEW_TOKENS ceiling check (use at your own risk).")
    args = parser.parse_args()

    cfg_doc = load_json(Path(args.configs))
    run_id = args.run_label or time.strftime("%Y%m%d_%H%M%S")
    run_root = DATA_ROOT / "runs" / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    print(f"[WO-QA-01] run_id={run_id}  root={run_root}")

    people = await fetch_people()
    narrator_ids = find_test_narrators(people)
    print(f"[WO-QA-01] test narrators: {narrator_ids}")

    # Pre-flight: verify ceiling
    if not args.skip_preflight:
        await preflight_check(narrator_ids["structured"])

    if args.dry_run:
        # One minimal cell, no matrix — just confirms plumbing
        print("[dry-run] executing single cell…")
        cfg = cfg_doc["configs"][0]
        sampling = {
            "temperature": cfg["temperature"],
            "top_p": cfg["top_p"],
            "repetition_penalty": cfg.get("repetition_penalty"),
            "max_new_tokens": 128,
        }
        r = await run_turn_with_retry(
            person_id=narrator_ids["structured"],
            prompt="Say hello in one short sentence.",
            sampling=sampling,
        )
        yield_count = await extract_yield(narrator_ids["structured"], r.response)
        print(f"[dry-run] OK — {len(r.token_timestamps_ms)} tokens, "
              f"ttft={r.ttft_ms}ms, yield={yield_count}, response={r.response[:120]!r}")
        # Write a marker so the router can detect dry-run completion — scores.json
        # is only written for full matrix runs. Without this marker, status stays
        # stuck at "running" after the process exits.
        (run_root / "dry_run_complete.json").write_text(
            json.dumps({
                "dry_run": True,
                "token_count": len(r.token_timestamps_ms),
                "ttft_ms": r.ttft_ms,
                "yield": yield_count,
                "response": r.response,
            }, indent=2),
            encoding="utf-8",
        )
        return

    metrics: list[MetricRow] = []
    transcripts: list[dict[str, Any]] = []

    for narrator_style, narrator_id in narrator_ids.items():
        for cfg in cfg_doc["configs"]:
            sampling = {
                "temperature": cfg["temperature"],
                "top_p": cfg["top_p"],
                "repetition_penalty": cfg.get("repetition_penalty"),
                "max_new_tokens": cfg["max_new_tokens"],
            }
            print(f"\n[run] {narrator_style} × {cfg['id']} "
                  f"(T={cfg['temperature']}, p={cfg['top_p']}, r={cfg.get('repetition_penalty')})")

            # Pre-stress baseline (for recovery measurement)
            pre = await run_turn_with_retry(
                person_id=narrator_id,
                prompt="Answer in about 100 words. Tell me about your childhood home.",
                sampling=sampling,
            )

            # Scenario matrix
            for scn in SCENARIOS:
                r = await run_turn_with_retry(
                    person_id=narrator_id,
                    prompt=scn["prompt"],
                    sampling=sampling,
                )
                y = await extract_yield(narrator_id, r.response)
                tts_pass, tts_drift = tts_drift_placeholder(r.response)
                metrics.append(MetricRow(
                    narrator_style=narrator_style,
                    narrator_id=narrator_id,
                    config_id=cfg["id"],
                    scenario_id=scn["id"],
                    prompt=scn["prompt"],
                    response=r.response,
                    proposal_row_count=y,
                    ttft_ms=r.ttft_ms,
                    total_ms=r.total_ms,
                    tokens_per_sec=r.tokens_per_sec,
                    token_timestamps_ms=r.token_timestamps_ms,
                    blocked=r.blocked,
                    oom=r.oom,
                    contamination_pass=None,
                    coherence_score=score_coherence(r.response),
                    adherence_score=score_adherence(scn["id"], r.response),
                    style_score=score_style(narrator_style, r.response),
                    stability_score=None,
                    tts_pass=tts_pass,
                    tts_drift_ms=tts_drift,
                ))
                transcripts.append({
                    "narrator_style": narrator_style,
                    "config_id": cfg["id"],
                    "scenario_id": scn["id"],
                    "prompt": scn["prompt"],
                    "response": r.response,
                })

            # Real-prompt replay
            for prompt in REAL_PROMPT_REPLAY:
                r = await run_turn_with_retry(
                    person_id=narrator_id,
                    prompt=prompt,
                    sampling=sampling,
                )
                y = await extract_yield(narrator_id, r.response)
                metrics.append(MetricRow(
                    narrator_style=narrator_style,
                    narrator_id=narrator_id,
                    config_id=cfg["id"],
                    scenario_id="scn_real_replay",
                    prompt=prompt,
                    response=r.response,
                    proposal_row_count=y,
                    ttft_ms=r.ttft_ms,
                    total_ms=r.total_ms,
                    tokens_per_sec=r.tokens_per_sec,
                    token_timestamps_ms=r.token_timestamps_ms,
                    blocked=r.blocked,
                    oom=r.oom,
                    contamination_pass=None,
                    coherence_score=score_coherence(r.response),
                    adherence_score=None,
                    style_score=score_style(narrator_style, r.response),
                    stability_score=None,
                    tts_pass=None,
                    tts_drift_ms=None,
                ))

            # Post-stress recovery (same prompt as pre, measure delta)
            post = await run_turn_with_retry(
                person_id=narrator_id,
                prompt="Answer in about 100 words. Tell me about your childhood home.",
                sampling=sampling,
            )
            metrics.append(MetricRow(
                narrator_style=narrator_style,
                narrator_id=narrator_id,
                config_id=cfg["id"],
                scenario_id="scn_recovery",
                prompt="Recovery check",
                response=post.response,
                proposal_row_count=await extract_yield(narrator_id, post.response),
                ttft_ms=post.ttft_ms,
                total_ms=post.total_ms,
                tokens_per_sec=post.tokens_per_sec,
                token_timestamps_ms=post.token_timestamps_ms,
                blocked=post.blocked,
                oom=post.oom,
                contamination_pass=None,
                coherence_score=score_coherence(post.response),
                adherence_score=None,
                style_score=score_style(narrator_style, post.response),
                stability_score=score_stability(pre.ttft_ms, post.ttft_ms),
                tts_pass=None,
                tts_drift_ms=None,
            ))

            # Contamination (sticky session_ids for real history)
            contam_pass = await run_contamination_test(narrator_ids, sampling)
            metrics.append(MetricRow(
                narrator_style=narrator_style,
                narrator_id=narrator_id,
                config_id=cfg["id"],
                scenario_id="scn_contamination",
                prompt=CONTAMINATION_RETURN_PROMPT,
                response="PASS" if contam_pass else "FAIL",
                proposal_row_count=0,
                ttft_ms=None,
                total_ms=0,
                tokens_per_sec=None,
                token_timestamps_ms=[],
                blocked=None,
                oom=False,
                contamination_pass=contam_pass,
                coherence_score=None,
                adherence_score=None,
                style_score=None,
                stability_score=None,
                tts_pass=None,
                tts_drift_ms=None,
            ))

    # Write artifacts
    (run_root / "metrics.json").write_text(
        json.dumps([asdict(m) for m in metrics], indent=2),
        encoding="utf-8",
    )
    (run_root / "transcripts.json").write_text(
        json.dumps(transcripts, indent=2),
        encoding="utf-8",
    )
    (run_root / "configs.json").write_text(
        json.dumps(cfg_doc, indent=2),
        encoding="utf-8",
    )
    scores = summarize_scores(metrics)
    (run_root / "scores.json").write_text(
        json.dumps(scores, indent=2),
        encoding="utf-8",
    )

    compare_output = None
    if args.compare_to:
        cmp_path = DATA_ROOT / "runs" / args.compare_to / "scores.json"
        if cmp_path.exists():
            baseline = json.loads(cmp_path.read_text(encoding="utf-8"))
            compare_output = compare_runs(scores, baseline)
            (run_root / "compare.json").write_text(
                json.dumps(compare_output, indent=2),
                encoding="utf-8",
            )

    # summary.md
    lines = [f"# WO-QA-01 Summary — {run_id}", ""]
    lines.append(f"- narrators: {list(narrator_ids.keys())}")
    lines.append(f"- configs: {[c['id'] for c in cfg_doc['configs']]}")
    lines.append(f"- total metric rows: {len(metrics)}")
    lines.append("")
    lines.append("## Ranked configs (contamination → yield → TTFT)")
    lines.append("")
    for row in scores[:8]:
        lines.append(
            f"- **{row['narrator_style']} / {row['config_id']}** — "
            f"yield={row['proposal_row_yield']}, "
            f"ttft={row['avg_ttft_ms']}, "
            f"tok/s={row['avg_tokens_per_sec']}, "
            f"contamination={row['contamination_pass']}, "
            f"blocked={row['blocked_cells']}, "
            f"human={row['avg_human_score']}"
        )
    if compare_output:
        lines.extend(["", "## Compare vs baseline", ""])
        for row in compare_output:
            lines.append(
                f"- **{row['narrator_style']} / {row['config_id']}** — "
                f"yield Δ={row['yield_delta']}, "
                f"ttft Δ={row['ttft_delta_ms']}, "
                f"contamination={row['contamination_delta']}"
            )
    (run_root / "summary.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"\n[WO-QA-01] complete → {run_root}")


if __name__ == "__main__":
    asyncio.run(main())
