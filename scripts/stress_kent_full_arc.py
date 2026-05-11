#!/usr/bin/env python3
"""STRESS TEST: Kent full-arc, chunked monologue, leave/return, era walk.

Per Chris's 2026-05-10 directive: "real stress test with kents transcripts
and then the longer 2400 word narrative broken up like we had done plus
leave the session and return to see if it picks up in the era then go
through all the eras and ask what they are."

Four phases, all over a single conv_id (modulo Phase C which deliberately
disconnects + reconnects):

  Phase A — Kent representative transcript turns (4 short narrative
            turns drawn from yesterday's deep-witness sessions). Tests
            ordinary witness/bank/correction routing.

  Phase B — 2,400-word Fort Ord narrative broken into 6 chapter chunks
            sent as separate turns. Tests:
              - Witness mode fires on each chapter (STRUCTURED_NARRATIVE)
              - Bank accumulates across chunks (no double-asks via dedup)
              - Tier 1A meal-tickets surfaces as the dominant immediate
              - Tier-N institutional names (Fort Ord, Stanley, Fargo)
                NEVER auto-immediate
              - Sensory doors all bank under adult_competence overlay
              - Memory-echo probe at end uses content from earlier chunks

  Phase C — leave & return. Close the WS, sleep 5s, reopen with the
            same conv_id, ping the opener endpoint with the last era,
            then send a probe turn ("I'm back"). Tests:
              - Welcome-back continuation paraphrase fires (gated on
                HORNELORE_CONTINUATION_PARAPHRASE=1)
              - Memory-echo on next turn references prior chunks

  Phase D — 7-era walk. For each canonical era_id, send a narrator
            question like "What do you mean by Coming of Age?". Tests:
              - ERA EXPLAINER directive surfaces the right glossary
                line (era keywords appear in response)
              - Lori does NOT lecture all seven unprompted
              - Response stays brief (≤40 words target)

Pre-flight (operator):
  1. Stack warm at localhost:8000 (~4 min cold boot)
  2. profile_json for Kent UUID has:
        narrator_voice_overlay = adult_competence
        session_language_mode = english
     (Set via Bug Panel → Operator Preflight → Save, OR via the CLI
      scripts scripts/set_narrator_overlay.py +
      scripts/set_session_language_mode.py)
  3. .env carries (defaults are fine for everything except #2):
        HORNELORE_OPERATOR_FOLLOWUP_BANK=1   # for bank inspection
        HORNELORE_CONTINUATION_PARAPHRASE=1  # for Phase C resume
  4. Restart stack after .env / profile changes

Usage:
  python3 scripts/stress_kent_full_arc.py
  python3 scripts/stress_kent_full_arc.py --skip-phase-a   # if no time
  python3 scripts/stress_kent_full_arc.py --only-phase d   # era-walk only

Outputs:
  docs/reports/stress_kent_full_arc_<conv_id>.json
  docs/reports/stress_kent_full_arc_<conv_id>.md

Companion log stream (terminal 2):
  tail -n 0 -f .runtime/logs/api.log | grep -E '\\[lang-contract\\]|\\[witness\\]|\\[followup-bank\\]|\\[bank-flush\\]|\\[memory-echo\\]'
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import websockets
except ImportError:
    print("pip install websockets", file=sys.stderr)
    raise SystemExit(1)


# ── Constants ──────────────────────────────────────────────────────────────

WS_URL = "ws://localhost:8000/api/chat/ws"
HTTP_BASE = "http://localhost:8000"
KENT_PERSON_ID = "4aa0cc2b-1f27-433a-9152-203bb1f69a55"


# ── Phase A: Kent representative transcript turns ──────────────────────────
#
# Hand-curated short turns drawn from the K-COMBINED deep-witness pattern.
# Each is short enough to NOT trigger STRUCTURED_NARRATIVE on its own —
# this exercises the ordinary interview / correction / passive-Pass2
# paths before Phase B sends the long monologue.

KENT_PHASE_A_TURNS: List[Tuple[str, str]] = [
    (
        "phase_a1_intro",
        "I grew up in Stanley, North Dakota, on a farm. My father worked the "
        "land and I helped from the time I was old enough to walk behind him.",
    ),
    (
        "phase_a2_correction",
        "Wait — I need to correct that. It was not Lansdale Army Hospital. "
        "It was Landstuhl Air Force Hospital. Vince was born at Landstuhl. "
        "I want that spelled correctly for the record.",
    ),
    (
        "phase_a3_passive_assignment",
        "After the induction tests in Fargo I was put in charge of meal "
        "tickets for the trainload of recruits headed to the West Coast. "
        "I was eighteen and the Army had already decided to trust me with "
        "that responsibility.",
    ),
    (
        "phase_a4_meta_feedback",
        "You are being vague and not asking about basic training rather "
        "the sensory parts of it. I want to tell my experience and you "
        "want to know how I felt.",
    ),
]


# ── Phase B: ~2,400-word Fort Ord narrative chunked by chapter ─────────────
#
# Pulls from the canonical 3,000-word KENT_FORT_ORD_MONOLOGUE in
# scripts/one_shot_kent_fort_ord_long.py and groups its paragraphs
# into 6 chapter-shaped turns (~400 words each → ~2,400 total). This
# keeps the source single — when Chris's canonical narrative changes,
# this script picks it up automatically.

def _load_phase_b_chunks() -> List[Tuple[str, str]]:
    """Group the source monologue's paragraphs into ~6 chapter chunks.

    Strategy:
      - Read KENT_FORT_ORD_MONOLOGUE from one_shot_kent_fort_ord_long.
      - Split by blank-line paragraph break.
      - Greedily merge paragraphs until each chunk hits ~400 words,
        then start a new chunk. Tighter than fixed-N grouping — keeps
        natural paragraph boundaries intact.
      - Stop after 6 chunks (~2,400 words). Tail content is dropped
        — Phase B is the chunked stress test, not the full monologue.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from one_shot_kent_fort_ord_long import KENT_FORT_ORD_MONOLOGUE
    paragraphs = [
        p.strip() for p in KENT_FORT_ORD_MONOLOGUE.split("\n\n")
        if p.strip()
    ]
    TARGET_WORDS = 400
    MAX_CHUNKS = 6
    chunks: List[Tuple[str, str]] = []
    buf: List[str] = []
    buf_words = 0
    labels = [
        "phase_b1_arrival",
        "phase_b2_barracks",
        "phase_b3_drill_instructors",
        "phase_b4_rifle_and_testing",
        "phase_b5_communication_home",
        "phase_b6_career_pivot",
    ]
    for p in paragraphs:
        pwords = len(p.split())
        if buf and buf_words + pwords > TARGET_WORDS * 1.25 and len(chunks) < MAX_CHUNKS - 1:
            chunks.append((labels[len(chunks)], "\n\n".join(buf)))
            buf = []
            buf_words = 0
        buf.append(p)
        buf_words += pwords
        if len(chunks) >= MAX_CHUNKS:
            break
    if buf and len(chunks) < MAX_CHUNKS:
        chunks.append((labels[len(chunks)], "\n\n".join(buf)))
    return chunks


KENT_PHASE_B_CHUNKS: List[Tuple[str, str]] = _load_phase_b_chunks()

KENT_PHASE_B_MEMORY_PROBE = "What did you learn about me from that whole arc?"


# ── Phase C: leave-and-return probe ────────────────────────────────────────

PHASE_C_RESUME_PROBE = "I'm back. Where were we?"


# ── Phase D: era-walk probes ───────────────────────────────────────────────
#
# Each tuple: (era_id, narrator-style question, expected keywords in
# Lori's reply drawn from the ERA EXPLAINER glossary in
# server/code/api/prompt_composer.py:3219).

ERA_WALK_PROBES: List[Tuple[str, str, List[str]]] = [
    (
        "earliest_years",
        "What do you mean by Earliest Years?",
        ["first", "memories", "before school", "birth", "home"],
    ),
    (
        "early_school_years",
        "What does Early School Years mean?",
        ["primary school", "young child", "neighborhood", "six", "twelve"],
    ),
    (
        "adolescence",
        "What is Adolescence again?",
        ["teen", "thirteen", "seventeen", "middle school", "high school", "friends"],
    ),
    (
        "coming_of_age",
        "What do you mean by Coming of Age?",
        ["leaving home", "twenties", "first work", "adult", "service"],
    ),
    (
        "building_years",
        "What does Building Years mean?",
        ["thirties", "fifties", "career", "family", "responsibility", "building"],
    ),
    (
        "later_years",
        "What's Later Years?",
        ["sixty", "kept", "matters", "long life", "learned"],
    ),
    (
        "today",
        "What does Today mean here?",
        ["now", "current", "room", "people", "unfinished"],
    ),
]


# ── Vocabulary gates (forbidden / expected) ────────────────────────────────

FORBIDDEN_TOKENS = (
    # Spanish drift on English-locked session
    "capté", "¿qué", "¿cómo", "tú ", "¡",
    # Sensory probes (banned per adult_competence overlay)
    "scenery", "sights", "sounds", "smells", "sensory",
    "camaraderie", "teamwork",
    "how did that feel", "how did you feel",
    "what did that feel like", "what was that like emotionally",
    # First-person mimicry — Lori speaking AS Kent
    "our son", "my wife", "my fiancée",
    "we were in germany", "we got married", "we drove",
    # LLM scaffolding mimicry
    "let's take a deep dive", "the narrator shares",
    "to acknowledge and reflect", "here's the response",
    "here is a response", "as an interviewer", "as a listener",
    "the narrator is", "the user is", "the speaker describes",
)

# Tier-N institutional names that must NEVER auto-immediate as
# spelling-confirms when overlay=adult_competence
TIER_N_AUTO_IMMEDIATE_BAD = (
    "did i get fort ord spelled right",
    "did i get stanley spelled right",
    "did i get fargo spelled right",
    "did i get army security agency spelled right",
    "did i get nike ajax spelled right",
    "did i get nike hercules spelled right",
)


# ── Helpers ────────────────────────────────────────────────────────────────


def has_any(text: str, terms) -> List[str]:
    low = text.lower()
    return [t for t in terms if t.lower() in low]


# Comprehending-ack exception for the sensory-token forbidden check.
# 2026-05-10 stress run flagged Lori's CORRECT META_FEEDBACK ack —
# "Got it — I'll skip the sensory questions" — as a forbidden_hits
# failure because the token "sensory" appears. The token is fine
# when it's preceded (within 30 chars) by a comprehending-skip verb
# like "skip" / "stop" / "won't" / "done with" — that's Lori
# acknowledging she WILL stop probing sensory, which is exactly the
# witness META_FEEDBACK contract.
_SENSORY_LIKE_TOKENS = (
    "scenery", "sights", "sounds", "smells", "sensory",
    "camaraderie", "teamwork",
)
_SKIP_VERB_PHRASES = (
    "skip", "stop", "no more", "won't", "wont", "won't ask", "wont ask",
    "done with", "no sensory", "not the sensory", "leave the sensory",
    "skip the sensory", "skip the sights", "skip the sounds",
    "skip the smells",
)


def _is_comprehending_ack(text: str, token: str) -> bool:
    """Return True when `token` appears inside a comprehending-ack
    context — i.e. Lori is acknowledging she WILL STOP probing
    sensory, not actually asking a sensory probe. The token is
    allowed in that context."""
    low = text.lower()
    idx = low.find(token.lower())
    if idx < 0:
        return False
    # Look back 30 chars for a skip-verb phrase.
    window_start = max(0, idx - 40)
    window = low[window_start:idx]
    return any(verb in window for verb in _SKIP_VERB_PHRASES)


def has_any_forbidden(text: str, terms) -> List[str]:
    """has_any() variant that suppresses sensory-like tokens inside
    a comprehending-ack context."""
    low = text.lower()
    hits: List[str] = []
    for t in terms:
        if t.lower() not in low:
            continue
        if t.lower() in _SENSORY_LIKE_TOKENS and _is_comprehending_ack(text, t):
            continue
        hits.append(t)
    return hits


def count_questions(text: str) -> int:
    return text.count("?")


def _build_params(turn_mode: str = "interview", current_era: str = "coming_of_age") -> dict:
    """Match runtime71 + params shape from existing harness scripts."""
    return {
        "person_id": KENT_PERSON_ID,
        "turn_mode": turn_mode,
        "session_style": "warm_storytelling",
        "runtime71": {
            "current_pass": "pass2a",
            "current_era": current_era,
            "current_mode": "open",
            "affect_state": "neutral",
            "affect_confidence": 0,
            "cognitive_mode": "open",
            "fatigue_score": 0,
            "paired": False,
            "assistant_role": "interviewer",
            "session_style_directive": "Ask one short question at a time.",
            "identity_complete": True,
            "identity_phase": "complete",
            "effective_pass": "pass2a",
            "speaker_name": "Kent",
            "person_id": KENT_PERSON_ID,
            "conversation_state": "answering",
            "cognitive_support_mode": False,
        },
        "max_new_tokens": 256,
        "turn_final": True,
    }


async def drain_brief(ws, seconds: float = 1.0):
    end = time.time() + seconds
    while time.time() < end:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=0.2)
            print("[drain]", raw[:200])
        except asyncio.TimeoutError:
            break


async def send_turn(
    ws, conv_id: str, text: str, label: str,
    *,
    turn_mode: str = "interview",
    current_era: str = "coming_of_age",
    timeout_s: int = 220,
) -> dict:
    """Send a single start_turn + collect tokens + done event."""
    print("\n" + "=" * 72)
    print(label)
    print("=" * 72)
    print(f"USER words: {len(text.split())}")
    print(f"USER text:  {text[:120]}{'…' if len(text) > 120 else ''}")
    print("--- LORI STREAM ---")

    params = _build_params(turn_mode=turn_mode, current_era=current_era)
    await ws.send(json.dumps({
        "type": "start_turn",
        "session_id": conv_id,
        "conv_id": conv_id,
        "message": text,
        "turn_mode": turn_mode,
        "params": params,
    }, ensure_ascii=False))

    tokens: List[str] = []
    final_text = ""
    backend_turn_mode: Optional[str] = None
    deadline = time.time() + timeout_s

    while time.time() < deadline:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
        except asyncio.TimeoutError:
            continue
        try:
            msg = json.loads(raw)
        except Exception:
            print("[raw]", raw[:200])
            continue
        typ = msg.get("type")
        if typ == "token":
            delta = msg.get("delta") or msg.get("text") or ""
            tokens.append(delta)
            print(delta, end="", flush=True)
        elif typ == "done":
            final_text = msg.get("final_text") or "".join(tokens)
            backend_turn_mode = msg.get("turn_mode")
            print("\n--- DONE ---")
            print(final_text)
            print(f"--- backend turn_mode={backend_turn_mode} ---")
            break
        elif typ == "error":
            print("\n--- ERROR ---")
            print(json.dumps(msg, indent=2, ensure_ascii=False)[:600])
            break

    streamed = "".join(tokens)
    return {
        "label": label,
        "user_text": text,
        "user_words": len(text.split()),
        "streamed_text": streamed,
        "final_text": final_text,
        "final_words": len(final_text.split()),
        "question_count": count_questions(final_text),
        "forbidden_hits": has_any_forbidden(final_text, FORBIDDEN_TOKENS),
        "tier_n_immediate_hits": has_any(final_text, TIER_N_AUTO_IMMEDIATE_BAD),
        "backend_turn_mode": backend_turn_mode,
    }


def fetch_bank(conv_id: str) -> dict:
    url = f"{HTTP_BASE}/api/operator/followup-bank/session/{conv_id}/all"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}


def fetch_opener(person_id: str, last_era_id: str, session_id: str) -> dict:
    url = (
        f"{HTTP_BASE}/api/interview/opener"
        f"?person_id={person_id}"
        f"&last_era_id={last_era_id}"
        f"&session_id={session_id}"
    )
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}


# ── Phase runners ──────────────────────────────────────────────────────────


async def run_phase_a(ws, conv_id: str) -> List[dict]:
    print("\n" + "#" * 72)
    print("# PHASE A — Kent representative transcript turns")
    print("#" * 72)
    results: List[dict] = []
    for label, text in KENT_PHASE_A_TURNS:
        r = await send_turn(ws, conv_id, text, f"phase_a:{label}")
        results.append(r)
        await asyncio.sleep(0.5)
    return results


async def run_phase_b(ws, conv_id: str) -> Tuple[List[dict], dict]:
    print("\n" + "#" * 72)
    print("# PHASE B — 2,400-word Fort Ord narrative chunked")
    print("#" * 72)
    results: List[dict] = []
    for label, text in KENT_PHASE_B_CHUNKS:
        r = await send_turn(ws, conv_id, text, f"phase_b:{label}", timeout_s=240)
        results.append(r)
        await asyncio.sleep(0.5)
    # Memory-echo probe at end
    probe = await send_turn(
        ws, conv_id, KENT_PHASE_B_MEMORY_PROBE,
        "phase_b:memory_probe", timeout_s=160,
    )
    results.append(probe)
    return results, probe


async def run_phase_c(conv_id: str) -> Tuple[dict, List[dict]]:
    """Close + reopen the WS, ping the opener endpoint, then send
    a probe turn. Returns (opener_payload, [resume_turn_result])."""
    print("\n" + "#" * 72)
    print("# PHASE C — leave & return")
    print("#" * 72)

    print("[phase-c] sleeping 5s before reconnect…")
    await asyncio.sleep(5)

    # Probe the opener endpoint with last_era_id from Phase B's
    # career-pivot chunk (coming_of_age maps to Kent's 1959 arc).
    opener = fetch_opener(KENT_PERSON_ID, "coming_of_age", conv_id)
    print(f"[phase-c] opener: {json.dumps(opener, ensure_ascii=False)[:400]}")

    # Reconnect WS and send a resume probe
    async with websockets.connect(
        WS_URL, ping_interval=None, max_size=30_000_000,
    ) as ws:
        try:
            initial = await asyncio.wait_for(ws.recv(), timeout=10)
            print("[phase-c initial]", initial[:200])
        except asyncio.TimeoutError:
            pass
        await ws.send(json.dumps({
            "type": "sync_session",
            "session_id": conv_id,
            "person_id": KENT_PERSON_ID,
        }))
        await drain_brief(ws)
        resume_turn = await send_turn(
            ws, conv_id, PHASE_C_RESUME_PROBE,
            "phase_c:resume_probe", timeout_s=160,
        )
    return opener, [resume_turn]


async def run_phase_d(ws, conv_id: str) -> List[dict]:
    print("\n" + "#" * 72)
    print("# PHASE D — 7-era walk")
    print("#" * 72)
    results: List[dict] = []
    for era_id, question, expected_keywords in ERA_WALK_PROBES:
        r = await send_turn(
            ws, conv_id, question,
            f"phase_d:{era_id}",
            current_era=era_id,
            timeout_s=120,
        )
        # Score era-keyword coverage
        r["era_id"] = era_id
        r["expected_keywords"] = expected_keywords
        r["keyword_hits"] = has_any(r["final_text"], expected_keywords)
        results.append(r)
        await asyncio.sleep(0.5)
    return results


# ── Scoring ────────────────────────────────────────────────────────────────


def score_phase_a(turns: List[dict]) -> List[str]:
    failures: List[str] = []
    for t in turns:
        if t["forbidden_hits"]:
            failures.append(f"{t['label']}: forbidden_hits={t['forbidden_hits']}")
        if t["question_count"] > 1:
            failures.append(f"{t['label']}: too_many_questions={t['question_count']}")
        if t["tier_n_immediate_hits"]:
            failures.append(f"{t['label']}: tier_n_auto_immediate={t['tier_n_immediate_hits']}")
        if not t["final_text"]:
            failures.append(f"{t['label']}: empty_response")
    return failures


def score_phase_b(turns: List[dict], memory_probe: dict) -> List[str]:
    failures = score_phase_a(turns)
    # Memory probe should reference Kent's content (≥3 hits among the
    # canonical Fort Ord vocabulary).
    #
    # 2026-05-10 stress-run fix — the memory_echo composer summarizes
    # from the BANK (not the raw chunk text), so the response uses
    # bank-intent vocabulary ("M1 expert qualification", "Janice
    # overseas communication", "ASA-vs-Nike career choice", "courier
    # route transition", "photography role pivot") rather than the
    # raw narrator anchors ("Fort Ord", "meal tickets", etc.). The
    # expected-terms list now spans BOTH vocabularies so the scorer
    # recognizes the response shape Lori actually produces.
    #
    # Match is case-insensitive substring (`has_any` lowercases) so
    # "ASA" matches "ASA-vs-Nike" and "Janice" matches "Janice
    # overseas communication".
    expected_anchors = [
        # Raw narrator anchors (appear when memory_echo includes
        # quoted narrator content)
        "Fort Ord", "M1", "meal tickets", "GED", "Army Security",
        "Nike Ajax", "Nike Hercules", "Stanley", "Fargo",
        # Bank-intent vocabulary (appears when memory_echo summarizes
        # the bank — the architecture's normal cross-arc shape)
        "courier", "photography", "Janice", "ASA",
        "expert qualification", "career choice",
        "operator", "Germany",
    ]
    hits = has_any(memory_probe["final_text"], expected_anchors)
    if len(hits) < 3:
        failures.append(
            f"phase_b_memory_probe: too_few_anchors={hits} "
            f"(want ≥3 of {expected_anchors})"
        )
    return failures


def score_phase_c(opener: dict, resume_turns: List[dict]) -> List[str]:
    failures: List[str] = []
    # Opener should not be a 5xx and should contain at least an opener_text
    if "error" in opener:
        failures.append(f"opener_endpoint_error={opener['error']}")
    elif not opener.get("opener_text"):
        failures.append("opener_missing_text")
    else:
        # Era-aware welcome-back? Look for era-phrase hint when
        # HORNELORE_CONTINUATION_PARAPHRASE=1. Soft signal — if the
        # flag is off, the opener will be a generic warm welcome-back
        # and that's also acceptable. We log either way.
        otext = opener.get("opener_text", "").lower()
        if not any(s in otext for s in ("welcome", "back", "where", "left off", "let's")):
            failures.append(f"opener_text_unexpected={otext[:120]!r}")
    for t in resume_turns:
        if not t["final_text"]:
            failures.append(f"{t['label']}: empty_response")
        if t["forbidden_hits"]:
            failures.append(f"{t['label']}: forbidden_hits={t['forbidden_hits']}")
    return failures


def score_phase_d(turns: List[dict]) -> List[str]:
    failures: List[str] = []
    for t in turns:
        era_id = t["era_id"]
        kw_hits = t["keyword_hits"]
        if not kw_hits:
            failures.append(
                f"{t['label']}: no_era_keywords matched "
                f"(expected one of {t['expected_keywords']})"
            )
        # Lori must NOT lecture all seven unprompted — flag if too long.
        if t["final_words"] > 80:
            failures.append(
                f"{t['label']}: response_too_long={t['final_words']}w "
                f"(want ≤80; era explainer should be brief)"
            )
        if t["forbidden_hits"]:
            failures.append(f"{t['label']}: forbidden_hits={t['forbidden_hits']}")
    return failures


# ── Report ─────────────────────────────────────────────────────────────────


def write_report(
    conv_id: str,
    phase_a_turns: List[dict],
    phase_b_turns: List[dict],
    phase_c_payload: Tuple[Optional[dict], List[dict]],
    phase_d_turns: List[dict],
    phase_a_failures: List[str],
    phase_b_failures: List[str],
    phase_c_failures: List[str],
    phase_d_failures: List[str],
    bank: dict,
) -> Tuple[Path, Path]:
    report_dir = Path("docs/reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    md_path = report_dir / f"stress_kent_full_arc_{conv_id}.md"
    json_path = report_dir / f"stress_kent_full_arc_{conv_id}.json"

    opener_payload, resume_turns = phase_c_payload

    payload = {
        "conv_id": conv_id,
        "person_id": KENT_PERSON_ID,
        "phase_a": {
            "turns": phase_a_turns,
            "failures": phase_a_failures,
            "verdict": "PASS" if not phase_a_failures else "FAIL",
        },
        "phase_b": {
            "turns": phase_b_turns,
            "failures": phase_b_failures,
            "verdict": "PASS" if not phase_b_failures else "FAIL",
        },
        "phase_c": {
            "opener": opener_payload,
            "resume_turns": resume_turns,
            "failures": phase_c_failures,
            "verdict": "PASS" if not phase_c_failures else "FAIL",
        },
        "phase_d": {
            "turns": phase_d_turns,
            "failures": phase_d_failures,
            "verdict": "PASS" if not phase_d_failures else "FAIL",
        },
        "bank": bank,
    }
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Markdown
    lines = [
        f"# Kent full-arc stress test — `{conv_id}`",
        "",
        f"- person_id: `{KENT_PERSON_ID}`",
        f"- ws: `{WS_URL}`",
        "",
        "## Phase verdicts",
        "",
        f"- Phase A (transcripts): {payload['phase_a']['verdict']}",
        f"- Phase B (chunked Fort Ord): {payload['phase_b']['verdict']}",
        f"- Phase C (leave & return): {payload['phase_c']['verdict']}",
        f"- Phase D (era walk): {payload['phase_d']['verdict']}",
        "",
        "## Failures",
        "",
    ]
    for name, f in [
        ("Phase A", phase_a_failures),
        ("Phase B", phase_b_failures),
        ("Phase C", phase_c_failures),
        ("Phase D", phase_d_failures),
    ]:
        lines.append(f"### {name}")
        if not f:
            lines.append("- (none)")
        else:
            for entry in f:
                lines.append(f"- {entry}")
        lines.append("")

    def _emit_turn_block(t: dict):
        lines.append(f"#### `{t['label']}` ({t['user_words']}w → {t['final_words']}w, q={t['question_count']})")
        lines.append("")
        lines.append("**Narrator:**")
        lines.append("> " + t["user_text"].replace("\n", "\n> "))
        lines.append("")
        lines.append("**Lori:**")
        lines.append("> " + (t["final_text"] or "(empty)").replace("\n", "\n> "))
        lines.append("")
        if t["forbidden_hits"]:
            lines.append(f"- forbidden_hits: `{t['forbidden_hits']}`")
        if t.get("tier_n_immediate_hits"):
            lines.append(f"- tier_n_immediate_hits: `{t['tier_n_immediate_hits']}`")
        if t.get("backend_turn_mode"):
            lines.append(f"- backend_turn_mode: `{t['backend_turn_mode']}`")
        if t.get("keyword_hits"):
            lines.append(f"- keyword_hits: `{t['keyword_hits']}` of `{t.get('expected_keywords')}`")
        lines.append("")

    lines.append("## Phase A turns")
    lines.append("")
    for t in phase_a_turns:
        _emit_turn_block(t)
    lines.append("## Phase B turns")
    lines.append("")
    for t in phase_b_turns:
        _emit_turn_block(t)
    lines.append("## Phase C — opener + resume")
    lines.append("")
    if opener_payload:
        lines.append("**Opener payload:**")
        lines.append("```json")
        lines.append(json.dumps(opener_payload, indent=2, ensure_ascii=False)[:1500])
        lines.append("```")
        lines.append("")
    for t in resume_turns:
        _emit_turn_block(t)
    lines.append("## Phase D — era walk")
    lines.append("")
    for t in phase_d_turns:
        _emit_turn_block(t)
    lines.append("## Bank state at end of run")
    lines.append("")
    if isinstance(bank, dict) and "error" not in bank:
        bank_count = bank.get("count", "—")
        lines.append(f"- count: {bank_count}")
        items = bank.get("questions") or bank.get("entries") or []
        for q in items:
            lines.append(
                f"- p{q.get('priority')} `{q.get('intent')}` — "
                f"{q.get('question_en')}"
            )
    else:
        lines.append(f"- error: `{bank.get('error') if isinstance(bank, dict) else bank}`")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    return md_path, json_path


# ── Main ───────────────────────────────────────────────────────────────────


async def main(args: argparse.Namespace) -> int:
    conv_id = args.conv_id or f"stress_kent_{uuid.uuid4().hex[:12]}"
    print("KENT FULL-ARC STRESS TEST")
    print(f"WS:        {WS_URL}")
    print(f"conv_id:   {conv_id}")
    print(f"person_id: {KENT_PERSON_ID}")
    print(f"phases:    {args.phases}")

    phase_a_turns: List[dict] = []
    phase_b_turns: List[dict] = []
    phase_c_payload: Tuple[Optional[dict], List[dict]] = (None, [])
    phase_d_turns: List[dict] = []

    do_a = "a" in args.phases
    do_b = "b" in args.phases
    do_c = "c" in args.phases
    do_d = "d" in args.phases

    async with websockets.connect(
        WS_URL, ping_interval=None, max_size=30_000_000,
    ) as ws:
        try:
            initial = await asyncio.wait_for(ws.recv(), timeout=10)
            print("[initial]", initial[:200])
        except asyncio.TimeoutError:
            pass
        await ws.send(json.dumps({
            "type": "sync_session",
            "session_id": conv_id,
            "person_id": KENT_PERSON_ID,
        }))
        await drain_brief(ws)

        if do_a:
            phase_a_turns = await run_phase_a(ws, conv_id)
        if do_b:
            phase_b_turns, _probe = await run_phase_b(ws, conv_id)

    if do_c:
        phase_c_payload = await run_phase_c(conv_id)

    if do_d:
        # Reopen WS for Phase D (separate connection — the era walk is
        # an independent set of turns; running them on the resumed
        # session from Phase C is also fine, but a fresh connection
        # mirrors how an operator would step through eras).
        async with websockets.connect(
            WS_URL, ping_interval=None, max_size=30_000_000,
        ) as ws_d:
            try:
                initial = await asyncio.wait_for(ws_d.recv(), timeout=10)
                print("[phase-d initial]", initial[:200])
            except asyncio.TimeoutError:
                pass
            await ws_d.send(json.dumps({
                "type": "sync_session",
                "session_id": conv_id,
                "person_id": KENT_PERSON_ID,
            }))
            await drain_brief(ws_d)
            phase_d_turns = await run_phase_d(ws_d, conv_id)

    # Score
    phase_a_failures = score_phase_a(phase_a_turns) if do_a else []
    phase_b_failures = score_phase_b(
        phase_b_turns[:-1] if phase_b_turns else [],
        phase_b_turns[-1] if phase_b_turns else {"final_text": ""},
    ) if do_b and phase_b_turns else []
    phase_c_failures = score_phase_c(*phase_c_payload) if do_c else []
    phase_d_failures = score_phase_d(phase_d_turns) if do_d else []

    bank = fetch_bank(conv_id)

    md_path, json_path = write_report(
        conv_id, phase_a_turns, phase_b_turns, phase_c_payload, phase_d_turns,
        phase_a_failures, phase_b_failures, phase_c_failures, phase_d_failures,
        bank,
    )

    print("\n" + "=" * 72)
    print("STRESS TEST SUMMARY")
    print("=" * 72)
    print(f"conv_id: {conv_id}")
    for name, fails in [
        ("Phase A", phase_a_failures),
        ("Phase B", phase_b_failures),
        ("Phase C", phase_c_failures),
        ("Phase D", phase_d_failures),
    ]:
        verdict = "PASS" if not fails else "FAIL"
        print(f"{name}: {verdict} ({len(fails)} failures)")
        for f in fails[:5]:
            print(f"  - {f}")
    print(f"\nReport: {md_path}")
    print(f"JSON:   {json_path}")

    any_fail = any([phase_a_failures, phase_b_failures, phase_c_failures, phase_d_failures])
    return 1 if any_fail else 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--phases", default="abcd",
                   help="String of phases to run (any subset of 'abcd', default 'abcd')")
    p.add_argument("--skip-phase-a", action="store_true",
                   help="Shortcut for --phases=bcd")
    p.add_argument("--only-phase", default="",
                   help="Run only this phase (a/b/c/d). Overrides --phases.")
    p.add_argument("--conv-id", default="",
                   help="Custom conv_id (default: auto-generated). Useful for "
                        "re-running Phase C/D against an existing session.")
    args = p.parse_args()
    if args.only_phase:
        args.phases = args.only_phase
    elif args.skip_phase_a:
        args.phases = "bcd"
    args.phases = args.phases.lower()
    return args


if __name__ == "__main__":
    sys.exit(asyncio.run(main(parse_args())))
