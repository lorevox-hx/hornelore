#!/usr/bin/env python3
"""BANK_PRIORITY_REBUILD 2026-05-10 — multi-turn Kent continuity test.

Per Chris's 2026-05-10 spec (replaces single-shot one_shot_kent_fort_ord
as the parent-session readiness gate):

  Turn 1 — Kent's long Fort Ord monologue (read from /tmp/kent_fort_ord_3000.txt)
  Turn 2 — "What did you learn about me from that?" (memory-echo check)
  Turn 3 — Kent's Nike missile / operator chapter (continuation in same session)

The KEY new proof is Turn 2. If Lori cannot answer "what did you learn
about me from that?" using Kent's actual Fort Ord content, the system
is responding turn-by-turn instead of listening across the chapter.

Pre-reqs:
  - Stack warm at localhost:8000 with bank-priority rebuild patches in
  - HORNELORE_OPERATOR_FOLLOWUP_BANK=1 (for bank inspection)
  - Kent narrator_voice_overlay=adult_competence (operator script)
  - /tmp/kent_fort_ord_3000.txt populated with the 3,000-word Fort Ord text
    (extract from one_shot_kent_fort_ord_long.py FORT_ORD_TEXT or paste fresh)

Usage:
  python3 scripts/replay_kent_fortord_then_nike_multiturn.py
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import time
import urllib.request
import uuid
from pathlib import Path
from typing import List, Optional

try:
    import websockets
except ImportError:
    print("pip install websockets", file=sys.stderr)
    raise SystemExit(1)


# ── Constants ─────────────────────────────────────────────────────────
WS_URL = "ws://localhost:8000/api/chat/ws"
KENT_PERSON_ID = "4aa0cc2b-1f27-433a-9152-203bb1f69a55"
FORT_ORD_PATH = Path("/tmp/kent_fort_ord_3000.txt")


# ── Test data ─────────────────────────────────────────────────────────
NIKE_OPERATOR_NARRATIVE = """
After Fort Ord and the decision not to wait around for Army Security Agency, I went into the Nike Ajax and Nike Hercules guided missile path. I was not working on that as some glamorous thing. It was a technical Army assignment, and the Army was interested in whether I could learn the radar and computer operator side of the missile system. The training was organized, repetitive, and full of procedures. You had to learn what each station did, what the radar picture meant, what information was being passed from one man to another, and how your piece fit into the larger crew.

The first training I remember was around Detroit, Michigan, at a base name I have not always had clear in my head. I have said Southridge before, but it may have been Selfridge Air Force Base, and I would want that checked. The work involved Nike Ajax and then Nike Hercules systems. We learned about acquisition radar, tracking radar, computer work, and the way operators had to keep attention on the scopes and instructions. I was not designing the system. I was learning to operate inside it, to follow procedure, and to understand what the crew needed from the operator position.

A lot of it was discipline and attention. You were watching screens, listening to commands, and keeping track of what the system was doing. There was a difference between classroom understanding and doing it as part of a crew. In class you could learn the terms. On the equipment, you had to keep your place. If you missed something, somebody else down the line might be waiting on information. That is one reason the earlier testing mattered. The Army had already decided I could handle technical material, and this was where that decision became real.

The Nike Ajax and Nike Hercules work also put me on the path to Germany. After about a year in training or assignment around the States, I was notified that I would be sent to Germany to work with the same systems there. That changed everything. It was not just another post. Germany became the place where my Army work and my personal life came together. I had to go home first on required leave, and then I traveled overseas. Once I was there, I thought Germany was a wonderful place, and that is what led me to contact Janice and tell her that if we were going to get married, we should get married and live there together.

As an operator, the thing to understand is that you were part of a system bigger than yourself. The equipment, the radar, the computer, the crew, the orders, the maintenance people, the officers, and the site all had to work together. You had a role, and the role mattered because the system depended on people doing their pieces correctly. I was still young, but I was not just drifting. I had gone from recruit to basic trainee to someone the Army was moving into technical missile work. That path is what took me to Germany, and Germany opened the next chapter with Janice.
""".strip()


# ── Gate vocabulary ───────────────────────────────────────────────────
FORBIDDEN = [
    # Spanish drift
    "capté", "¿qué", "tú ",
    # Sensory probes (banned per Kent overlay)
    "scenery", "sights", "sounds", "smells",
    "sensory", "camaraderie", "teamwork",
    "how did that feel", "how did you feel",
    # Made-up family / location facts
    "our son", "my wife", "we were in germany",
]

BAD_META_STREAM = [
    # Third-person narrator-voice mimicry the LLM emits before
    # validation — these are tested against the STREAMED text, not
    # the final. With the buffered-stream fix (deferred token emit
    # AFTER witness validator runs) these should be EMPTY in the
    # streamed_text capture. Any hit means the buffer leaked.
    "let's take a deep dive",
    "the narrator shares",
    "to acknowledge and reflect",
    "here's the",
    # 2026-05-10 multi-turn caught these LLM mimicry patterns the
    # validator catches downstream — must NOT be visible to client.
    "here is a response",
    "here is the response",
    "following the guidelines",
    "as an interviewer",
    "as a listener",
    "the narrator is",
    "the user is",
    "the speaker describes",
]

BAD_SPELLING_QUESTIONS = [
    "did i get army security agency spelled right",
    "did i get nike ajax spelled right",
    "did i get nike hercules spelled right",
    "did i get fort ord spelled right",
]

EXPECTED_FIRST_MEMORY_TERMS = [
    "Fort Ord",
    "meal tickets",
    "M1",
    "GED",
    "Army Security Agency",
    "Nike Ajax",
    "Nike Hercules",
]

EXPECTED_NIKE_TERMS = [
    "Nike Ajax",
    "Nike Hercules",
    "radar",
    "computer",
    "operator",
    "Germany",
    "Janice",
    # 2026-05-10 broadening — record-critical correction questions
    # (Southridge vs Selfridge, Detroit, Michigan) are valid Nike-
    # chapter outputs even when the wider operator/radar/Germany
    # frame is missing. ≥3 hits across this expanded list passes.
    "Detroit",
    "Michigan",
    "Southridge",
    "Selfridge",
]


# ── Helpers ───────────────────────────────────────────────────────────
def has_any(text: str, terms: List[str]) -> List[str]:
    low = text.lower()
    return [t for t in terms if t.lower() in low]


def count_questions(text: str) -> int:
    return text.count("?")


async def drain_brief(ws, seconds: float = 1.0):
    end = time.time() + seconds
    while time.time() < end:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=0.2)
            print("[drain]", raw[:300])
        except asyncio.TimeoutError:
            break


def _build_params(turn_mode: str = "interview") -> dict:
    """Match the runtime71 + params shape of the working one_shot."""
    return {
        "person_id": KENT_PERSON_ID,
        "turn_mode": turn_mode,
        "session_style": "clear_direct",
        "runtime71": {
            "current_pass": "pass2a",
            "current_era": "coming_of_age",
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


async def send_turn(
    ws,
    conv_id: str,
    text: str,
    label: str,
    *,
    turn_mode: str = "interview",
    timeout_s: int = 220,
) -> dict:
    """Send one start_turn + collect token stream + done event."""
    print("\n" + "=" * 72)
    print(label)
    print("=" * 72)
    print(f"USER words: {len(text.split())}")
    print("--- sending ---")

    params = _build_params(turn_mode=turn_mode)

    # CRITICAL: server expects "start_turn", not "message". The "message"
    # key inside is the user text payload (ChatGPT's draft used "type":
    # "message" which the server silently drops).
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
    events: List[dict] = []
    deadline = time.time() + timeout_s

    print("--- LORI STREAM ---")
    while time.time() < deadline:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
        except asyncio.TimeoutError:
            continue

        try:
            msg = json.loads(raw)
        except Exception:
            print("[raw]", raw)
            continue

        events.append(msg)
        typ = msg.get("type")

        if typ == "token":
            delta = msg.get("delta") or msg.get("text") or ""
            tokens.append(delta)
            print(delta, end="", flush=True)
        elif typ == "done":
            final_text = msg.get("final_text") or "".join(tokens)
            print("\n--- DONE ---")
            print(final_text)
            break
        elif typ == "error":
            print("\n--- ERROR ---")
            print(json.dumps(msg, indent=2, ensure_ascii=False))
            break
        else:
            if typ not in ("pong",):
                print(
                    f"\n[{typ}] "
                    f"{json.dumps(msg, ensure_ascii=False)[:500]}"
                )

    streamed = "".join(tokens)
    if not final_text:
        raise RuntimeError(f"No final_text for {label}")

    return {
        "label": label,
        "user_words": len(text.split()),
        "streamed_text": streamed,
        "final_text": final_text,
        "final_words": len(final_text.split()),
        "question_count": count_questions(final_text),
        "forbidden_hits": has_any(final_text, FORBIDDEN),
        "bad_meta_stream_hits": has_any(streamed, BAD_META_STREAM),
        "bad_spelling_question_hits": has_any(final_text, BAD_SPELLING_QUESTIONS),
        "events": events,
    }


def fetch_bank(conv_id: str) -> dict:
    url = (
        f"http://localhost:8000/api/operator/followup-bank/"
        f"session/{conv_id}/all"
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}


def score_result(
    result: dict,
    expected_terms: Optional[List[str]] = None,
) -> tuple:
    final = result["final_text"]
    hits = has_any(final, expected_terms or [])
    failures: List[str] = []

    if result["forbidden_hits"]:
        failures.append(f"forbidden_hits={result['forbidden_hits']}")
    # The buffered-stream fix is the proof point — bad LLM tokens must
    # never reach the client during witness-receipt mode. Empty
    # bad_meta_stream_hits = the buffer worked.
    if result["bad_meta_stream_hits"]:
        failures.append(
            f"raw_meta_streamed_to_client={result['bad_meta_stream_hits']} "
            f"(buffered-stream fix violated)"
        )
    if result["bad_spelling_question_hits"]:
        failures.append(
            f"bad_spelling_question={result['bad_spelling_question_hits']}"
        )
    if result["question_count"] > 1:
        failures.append(f"too_many_questions={result['question_count']}")
    # Memory-echo turn (Turn 2) is short-by-design — exempt the
    # 35-word floor for that one.
    is_memory_echo = "memory" in result["label"].lower() or (
        "learn about me" in (result.get("user_text") or "").lower()
    )
    if result["final_words"] < 30 and not is_memory_echo:
        failures.append(f"too_short={result['final_words']}w (want ≥30)")

    if expected_terms:
        # Receipt/memory checks: require ≥3 expected terms. Memory-
        # echo Turn 2 is the strict gate per Chris's 2026-05-10 spec.
        if len(hits) < 3:
            failures.append(
                f"too_few_expected_terms={hits} "
                f"(want ≥3 of {expected_terms})"
            )

    return hits, failures


def _load_fort_ord_text() -> str:
    """Load the Fort Ord monologue. Prefers /tmp/kent_fort_ord_3000.txt
    when it exists (operator-customizable); falls back to the embedded
    KENT_FORT_ORD_MONOLOGUE constant from one_shot_kent_fort_ord_long
    so the script runs out-of-the-box."""
    if FORT_ORD_PATH.exists():
        text = FORT_ORD_PATH.read_text(encoding="utf-8").strip()
        if text:
            return text
        print(
            f"WARN: {FORT_ORD_PATH} is empty — falling back to "
            f"embedded one_shot KENT_FORT_ORD_MONOLOGUE",
            file=sys.stderr,
        )
    # Fallback: import from sibling one-shot script
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from one_shot_kent_fort_ord_long import KENT_FORT_ORD_MONOLOGUE
        return KENT_FORT_ORD_MONOLOGUE.strip()
    except Exception as exc:
        print(
            f"\nERROR: could not load Fort Ord text. "
            f"{FORT_ORD_PATH} missing AND fallback import failed: {exc}\n",
            file=sys.stderr,
        )
        raise


async def main() -> int:
    fort_ord_text = _load_fort_ord_text()
    if not fort_ord_text:
        print("\nERROR: Fort Ord text empty.\n", file=sys.stderr)
        return 2

    conv_id = f"kent_multi_fortord_nike_{uuid.uuid4().hex[:12]}"

    print("KENT MULTI-TURN FORT ORD → MEMORY ECHO → NIKE TEST")
    print(f"WS:        {WS_URL}")
    print(f"conv_id:   {conv_id}")
    print(f"person_id: {KENT_PERSON_ID}")
    print(f"Fort Ord words: {len(fort_ord_text.split())}")
    print(f"Nike words:     {len(NIKE_OPERATOR_NARRATIVE.split())}")

    async with websockets.connect(
        WS_URL, ping_interval=None, max_size=30_000_000,
    ) as ws:
        try:
            first = await asyncio.wait_for(ws.recv(), timeout=10)
            print("[initial]", first[:500])
        except asyncio.TimeoutError:
            print("[initial] no status")

        await ws.send(json.dumps({
            "type": "sync_session",
            "session_id": conv_id,
            "person_id": KENT_PERSON_ID,
        }))
        await drain_brief(ws)

        r1 = await send_turn(
            ws, conv_id, fort_ord_text,
            "TURN 1 — KENT LONG FORT ORD MONOLOGUE",
            timeout_s=240,
        )

        # Brief breath between turns.
        await asyncio.sleep(0.5)

        r2 = await send_turn(
            ws, conv_id,
            "What did you learn about me from that?",
            "TURN 2 — KENT MEMORY-ECHO CHECK",
            timeout_s=160,
        )

        await asyncio.sleep(0.5)

        r3 = await send_turn(
            ws, conv_id, NIKE_OPERATOR_NARRATIVE,
            "TURN 3 — KENT NIKE MISSILE OPERATOR CHAPTER",
            timeout_s=240,
        )

    bank = fetch_bank(conv_id)

    # ── Scoring ──────────────────────────────────────────────────────
    scores = []
    h1, f1 = score_result(r1, EXPECTED_FIRST_MEMORY_TERMS)
    scores.append(("TURN 1 Fort Ord", h1, f1))

    h2, f2 = score_result(r2, EXPECTED_FIRST_MEMORY_TERMS)
    # Turn 2 is the memory-echo proof. Lori must answer the question
    # using Fort Ord content, not pivot to a new question.
    if "learn" not in r2["final_text"].lower() \
            and "know" not in r2["final_text"].lower() \
            and "you " not in r2["final_text"].lower()[:20]:
        f2.append("memory_echo_did_not_address_kents_question")
    scores.append(("TURN 2 Memory echo", h2, f2))

    h3, f3 = score_result(r3, EXPECTED_NIKE_TERMS)
    scores.append(("TURN 3 Nike", h3, f3))

    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)
    print(f"conv_id: {conv_id}")
    for name, hits, failures in scores:
        verdict = "PASS" if not failures else "FAIL"
        print(f"\n{name}: {verdict}")
        print(f"  expected_hits: {hits}")
        print(f"  failures: {failures or 'NONE'}")

    bank_count = bank.get("count") if isinstance(bank, dict) else None
    print(f"\nBank count: {bank_count}")
    if isinstance(bank, dict) and "questions" in bank:
        print("Bank intents:")
        for q in bank["questions"]:
            print(
                f"  - p{q.get('priority')} {q.get('intent')}: "
                f"{q.get('question_en')}"
            )
    elif isinstance(bank, dict) and "entries" in bank:
        # Newer API shape
        print("Bank entries:")
        for q in bank["entries"]:
            print(
                f"  - p{q.get('priority')} {q.get('intent')}: "
                f"{q.get('question_en')}"
            )

    # ── Persist report ───────────────────────────────────────────────
    report_dir = Path("docs/reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    md_path = report_dir / f"kent_multiturn_fortord_nike_{conv_id}.md"
    json_path = report_dir / f"kent_multiturn_fortord_nike_{conv_id}.json"

    report = {
        "conv_id": conv_id,
        "person_id": KENT_PERSON_ID,
        "turns": [r1, r2, r3],
        "scores": [
            {"name": n, "hits": h, "failures": f}
            for n, h, f in scores
        ],
        "bank": bank,
    }
    for turn in report["turns"]:
        turn.pop("events", None)  # bulky

    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    lines = [
        "# Kent multi-turn Fort Ord → memory echo → Nike test",
        "",
        f"- conv_id: `{conv_id}`",
        f"- person_id: `{KENT_PERSON_ID}`",
        f"- Fort Ord words: {len(fort_ord_text.split())}",
        f"- Nike words: {len(NIKE_OPERATOR_NARRATIVE.split())}",
        "",
    ]
    for idx, r in enumerate([r1, r2, r3], start=1):
        lines += [
            f"## Turn {idx}: {r['label']}",
            "",
            f"- user_words: {r['user_words']}",
            f"- final_words: {r['final_words']}",
            f"- question_count: {r['question_count']}",
            f"- forbidden_hits: {r['forbidden_hits']}",
            f"- raw_meta_stream_hits: {r['bad_meta_stream_hits']}",
            f"- bad_spelling_question_hits: {r['bad_spelling_question_hits']}",
            "",
            "**Lori final:**",
            "",
            "> " + r["final_text"].replace("\n", "\n> "),
            "",
        ]
    lines += [
        "## Score",
        "",
    ]
    for name, hits, failures in scores:
        verdict = "PASS" if not failures else "FAIL"
        lines += [
            f"### {name}: {verdict}",
            f"- expected_hits: {hits}",
            f"- failures: {failures or 'NONE'}",
            "",
        ]
    lines += [
        "## Bank",
        "",
        f"- count: {bank_count or 'ERR'}",
        "",
    ]
    bank_items = []
    if isinstance(bank, dict):
        bank_items = bank.get("questions") or bank.get("entries") or []
    for q in bank_items:
        lines.append(
            f"- p{q.get('priority')} `{q.get('intent')}` — "
            f"{q.get('question_en')}"
        )
    md_path.write_text("\n".join(lines), encoding="utf-8")

    print("\nReport written:")
    print(f"  {md_path}")
    print(f"  {json_path}")

    any_fail = any(f for _, _, f in scores)
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
