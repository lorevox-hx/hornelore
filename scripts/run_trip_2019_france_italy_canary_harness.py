#!/usr/bin/env python3
"""2019 France / Italy trip canary harness.

Source outline:
    May 26 thru June 15.docx

Purpose:
    Exercise Lori's live chat behavior on an older trip itinerary that has:
      - multi-airport travel chain: ABQ -> DFW -> LHR -> CDG
      - Paris hub-and-spoke sightseeing sequence
      - Paris -> Aix-en-Provence TGV transition
      - Provence day-trip chain: Avignon / Palais des Papes / bridge / Arles
      - Rome close and FCO -> DFW -> ABQ return
      - foreign words / accents that must NOT switch Lori out of English

This is a behavior harness, not a Trip Tab implementation.
It also writes a UI fixture JSON that later browser/UI tests can consume.

Usage:
    cd /mnt/c/Users/chris/hornelore
    .venv-gpu/bin/python scripts/run_trip_2019_france_italy_canary_harness.py

Assumes the stack is warm.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
import sys
import time
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import websockets  # type: ignore

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "server" / "code"))

from api.services.factual_chain_capture import (  # noqa: E402
    _SENSORY_PROBE_RX,
    build_factual_chain_followup_context,
)
from api.services.lori_response_guards import _looks_spanish  # noqa: E402


API_BASE = os.environ.get("HORNELORE_API_BASE", "http://localhost:8000")
WS_URL = os.environ.get("HORNELORE_CHAT_WS", "ws://localhost:8000/api/chat/ws")
API_LOG = Path(os.environ.get("HORNELORE_API_LOG", "/mnt/c/Users/chris/hornelore/.runtime/logs/api.log"))
REPORTS_DIR = Path(os.environ.get("HORNELORE_REPORTS_DIR", "/mnt/c/Users/chris/hornelore/docs/reports"))
DB_PATH = Path(os.environ.get("HORNELORE_DB_PATH", "/mnt/c/hornelore_data/db/hornelore.sqlite3"))
UI_FIXTURE_PATH = Path(os.environ.get(
    "HORNELORE_2019_TRIP_FIXTURE",
    "/mnt/c/Users/chris/hornelore/fixtures/trips/trip_2019_france_italy_fixture.json",
))

NARRATOR_DISPLAY_NAME = "Trip Canary Narrator (2019 France Italy)"
NARRATOR_DOB = "1965-12-24"
NARRATOR_POB = "Bismarck, ND"
NARRATOR_PRONOUNS = "he_him"
NARRATOR_RESIDENCE = "Santa Fe, NM"

WORD_BUDGET = 95
TURN_TIMEOUT = 90.0

_DRIFT_REPAIR_SIGNATURES = (
    "sorry — let's continue",
    "sorry, let's continue",
    "disculpa, continuemos",
    "what would you like to tell me next",
    "let's keep going in english",
    "let's stay with that in english",
)


def _reply_is_drift_repair(reply: str) -> bool:
    if not reply:
        return True
    rl = reply.strip().lower()
    return any(sig in rl for sig in _DRIFT_REPAIR_SIGNATURES)


def _anchor_echo_count(reply: str, anchors: List[str]) -> int:
    if not reply or not anchors:
        return 0
    rl = reply.lower()
    return sum(1 for a in anchors if a and a.lower() in rl)


def _is_stub_collapse(reply: str) -> bool:
    text = (reply or "").strip()
    if not text:
        return True
    # One-word or tiny fragment answers like "Roman." are never acceptable
    # for substantive trip narration.
    words = re.findall(r"\b\w+\b", text)
    return len(words) < 6


@dataclass
class Turn:
    n: int
    text: str
    expect_is_chain: bool
    expect_min_anchors: int
    expect_any_cue: List[str]
    expect_meta_feedback: bool = False
    expect_rejected_type: str = ""
    graded: bool = True
    note: str = ""


TURNS: List[Turn] = [
    Turn(
        n=1,
        text=(
            "For the 2019 trip, we started in Albuquerque, then flew to Dallas Fort Worth, "
            "then overnight to London Heathrow, then British Airways to Paris Charles de Gaulle, "
            "and after that we settled at the apartment on Rue de Reuilly."
        ),
        expect_is_chain=True,
        expect_min_anchors=5,
        expect_any_cue=["multi_place_sequence", "travel_leg_sequence"],
        note="Outbound airport chain ABQ -> DFW -> LHR -> CDG -> Paris lodging.",
    ),
    Turn(
        n=2,
        text=(
            "Our first big Paris day went from Jardin du Luxembourg to the Panthéon, "
            "then the Latin Quarter, then Sainte-Chapelle, Notre-Dame, and the Centre Pompidou."
        ),
        expect_is_chain=True,
        expect_min_anchors=5,
        expect_any_cue=["multi_place_sequence"],
        note="Paris day-one sightseeing chain.",
    ),
    Turn(
        n=3,
        text=(
            "The Paris museum run included the Eiffel Tower, Trocadéro Gardens, Palais de Chaillot, "
            "the Champs Élysées, Musée d'Orsay, Sacré-Cœur, Montmartre, the Louvre, Arc de Triomphe, "
            "Musée Nissim de Camondo, and Galeries Lafayette."
        ),
        expect_is_chain=True,
        expect_min_anchors=7,
        expect_any_cue=["multi_place_sequence"],
        note="Dense Paris monuments / museums chain.",
    ),
    Turn(
        n=4,
        text=(
            "At Marché d'Aligre there were market stalls, food smells, voices, and the feeling of a neighborhood morning."
        ),
        expect_is_chain=False,
        expect_min_anchors=0,
        expect_any_cue=[],
        graded=False,
        note="UNGRADED sensory setup so the meta-feedback turn has a real prior sensory opening.",
    ),
    Turn(
        n=5,
        text=(
            "Then we left Paris from Gare de Lyon at 11:37, took the TGV south, "
            "arrived in Aix-en-Provence around 4:27, and stayed on rue Suffren."
        ),
        expect_is_chain=True,
        expect_min_anchors=4,
        expect_any_cue=["multi_place_sequence", "travel_leg_sequence"],
        note="Paris -> Aix TGV transition.",
    ),
    Turn(
        n=6,
        text=(
            "From Aix we did the Provence side trip to Avignon, saw the Palais des Papes "
            "and the Avignon Bridge, then went on to Arles."
        ),
        expect_is_chain=True,
        expect_min_anchors=4,
        expect_any_cue=["multi_place_sequence", "travel_leg_sequence"],
        note="Aix base -> Avignon -> Palais des Papes -> bridge -> Arles.",
    ),
    Turn(
        n=7,
        text=(
            "Near the end we had Rome at Via Francesco Carletti, then flew home from Fiumicino "
            "to Dallas Fort Worth and finally back to Albuquerque."
        ),
        expect_is_chain=True,
        expect_min_anchors=4,
        expect_any_cue=["multi_place_sequence", "travel_leg_sequence"],
        note="Rome close and FCO -> DFW -> ABQ return chain.",
    ),
    Turn(
        n=8,
        text=(
            "No, not the market atmosphere — the thread I want is how the trip moved from Paris museums "
            "to Provence history to Rome at the end. The Louvre, Avignon, Arles, and Rome connect for me."
        ),
        expect_is_chain=True,
        expect_min_anchors=4,
        expect_any_cue=["multi_place_sequence"],
        expect_meta_feedback=True,
        expect_rejected_type="sensory",
        note="Meta-feedback rejecting sensory + asserting cross-region theme chain.",
    ),
]


@dataclass
class TurnResult:
    turn: Turn
    lori_response: str
    log_is_chain: Optional[bool]
    log_confidence: Optional[float]
    log_cue_labels: List[str]
    log_anchor_count: Optional[int]
    log_meta_feedback: Optional[bool]
    log_rejected_type: Optional[str]
    response_word_count: int
    response_question_count: int
    sensory_pivot_match: Optional[str]
    rows: Dict[str, bool] = field(default_factory=dict)

    @property
    def passed_rows(self) -> int:
        return sum(1 for v in self.rows.values() if v)

    @property
    def total_rows(self) -> int:
        return len(self.rows)


def _http_post_json(url: str, payload: Dict[str, Any], timeout: float = 30.0) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return json.loads(body)


def create_narrator() -> str:
    payload = {
        "full_legal_name": NARRATOR_DISPLAY_NAME,
        "preferred_name": NARRATOR_DISPLAY_NAME,
        "date_of_birth": NARRATOR_DOB,
        "place_of_birth": NARRATOR_POB,
        "pronouns": NARRATOR_PRONOUNS,
        "current_residence": NARRATOR_RESIDENCE,
        "consent_recording_agreement": True,
        "consent_disclosure_reviewed": True,
        "testing_only": True,
    }
    try:
        resp = _http_post_json(f"{API_BASE}/api/people/intake", payload)
    except Exception as exc:
        print(f"[ERROR] /api/people/intake failed: {exc}", file=sys.stderr)
        resp = _http_post_json(
            f"{API_BASE}/api/people",
            {
                "display_name": NARRATOR_DISPLAY_NAME,
                "date_of_birth": NARRATOR_DOB,
                "place_of_birth": NARRATOR_POB,
                "pronouns": NARRATOR_PRONOUNS,
                "current_residence": NARRATOR_RESIDENCE,
            },
        )
    pid = resp.get("person_id") or resp.get("id")
    if not pid:
        raise RuntimeError(f"create_narrator: no person_id in response: {resp}")
    print(f"  ✓ Created 2019 trip-canary narrator person_id={pid}")
    return pid


async def send_one_turn(ws: Any, person_id: str, conv_id: str, turn: Turn) -> str:
    payload = {
        "type": "start_turn",
        "session_id": conv_id,
        "conv_id": conv_id,
        "message": turn.text,
        "turn_mode": "interview",
        "turn_id": str(uuid.uuid4()),
        "params": {
            "person_id": person_id,
            "turn_id": str(uuid.uuid4()),
            # 2026-06-25: surface and trip_id live at params TOP
            # LEVEL, not nested under runtime71. chat_ws.py:3791
            # reads params.get("surface") directly; nesting under
            # runtime71 (the original package shape) left the
            # surface marker as dead payload. Currently the
            # iteration-2 _SURFACES_WITHOUT_LANGUAGE_DRIFT_REPAIR
            # is empty so surface routing is a no-op, but this
            # places the marker where the API expects it.
            "surface": "trip",
            "trip_id": "trip_2019_france_italy_paris_aix_rome",
        },
    }
    await ws.send(json.dumps(payload))
    final_text = ""
    deadline = time.time() + TURN_TIMEOUT
    while time.time() < deadline:
        remaining = deadline - time.time()
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        except asyncio.TimeoutError:
            break
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue
        evt = msg.get("event") or msg.get("type")
        if evt == "done":
            final_text = (msg.get("final_text") or "").strip()
            break
        if evt == "error":
            print(f"[WARN] turn {turn.n} got error event: {msg}", file=sys.stderr)
            break
    return final_text


_FC_LOG_RX = re.compile(
    r"\[chat_ws\]\[factual-chain\]\s+"
    r"conv=(?P<conv>\S+)\s+"
    r"narrator=\S+\s+"
    r"is_chain=(?P<is_chain>True|False|None)\s+"
    r"conf=(?P<conf>\S+)\s+"
    r"cues=(?P<cues>\[.*?\])\s+"
    r"anchors=(?P<anchors>\d+)\s+"
    r"meta_feedback=(?P<meta>True|False|None)\s+"
    r"rejected=(?P<rejected>\S*)"
)
_CUE_RX = re.compile(r"'([a-z_]+)'")


def grep_factual_chain_log_for_conv(conv_id: str) -> List[Dict[str, Any]]:
    if not API_LOG.exists():
        return []
    try:
        lines = API_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    hits: List[Dict[str, Any]] = []
    for line in lines[-15000:]:
        if "[chat_ws][factual-chain]" not in line or conv_id not in line:
            continue
        m = _FC_LOG_RX.search(line)
        if not m:
            continue
        gd = m.groupdict()
        try:
            conf = float(gd["conf"])
        except Exception:
            conf = None
        try:
            anchors = int(gd["anchors"])
        except Exception:
            anchors = None
        is_chain_str = gd["is_chain"]
        meta_str = gd["meta"]
        hits.append({
            "raw": line,
            "is_chain": True if is_chain_str == "True" else (False if is_chain_str == "False" else None),
            "conf": conf,
            "cues": _CUE_RX.findall(gd["cues"]),
            "anchors": anchors,
            "meta_feedback": True if meta_str == "True" else (False if meta_str == "False" else None),
            "rejected": gd["rejected"] or "",
        })
    return hits


def query_chain_meta_for_narrator(person_id: str) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    try:
        con = sqlite3.connect(str(DB_PATH))
        try:
            cur = con.execute(
                "SELECT id, trigger_reason, transcript, chain_meta_json, created_at "
                "FROM story_candidates WHERE narrator_id = ? ORDER BY created_at DESC LIMIT 20;",
                (person_id,),
            )
            rows: List[Dict[str, Any]] = []
            for r in cur.fetchall():
                try:
                    meta = json.loads(r[3] or "{}")
                except Exception:
                    meta = {}
                rows.append({
                    "id": r[0],
                    "trigger_reason": r[1],
                    "transcript": r[2],
                    "chain_meta": meta,
                    "created_at": r[4],
                })
            return rows
        finally:
            con.close()
    except Exception as exc:
        print(f"[WARN] sqlite query failed for narrator={person_id}: {exc}", file=sys.stderr)
        return []


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def _question_count(text: str) -> int:
    return text.count("?") + max(0, text.count("¿") - text.count("?"))


def score_turn(turn: Turn, lori_response: str, log_hit: Optional[Dict[str, Any]]) -> TurnResult:
    wc = _word_count(lori_response)
    qc = _question_count(lori_response)
    sensory_m = _SENSORY_PROBE_RX.search(lori_response or "")

    log_is_chain = log_hit.get("is_chain") if log_hit else None
    log_conf = log_hit.get("conf") if log_hit else None
    log_cues = list(log_hit.get("cues") or []) if log_hit else []
    log_anchors = log_hit.get("anchors") if log_hit else None
    log_meta = log_hit.get("meta_feedback") if log_hit else None
    log_rejected = (log_hit.get("rejected") or "") if log_hit else ""

    try:
        narrator_ctx = build_factual_chain_followup_context(turn.text, prior_turns=[])
        narrator_anchors = list(narrator_ctx.get("anchors") or [])
    except Exception:
        narrator_anchors = []

    anchor_hits = _anchor_echo_count(lori_response, narrator_anchors)
    is_drift_repair = _reply_is_drift_repair(lori_response)
    is_spanish = _looks_spanish(lori_response)
    is_stub = _is_stub_collapse(lori_response)

    rows: Dict[str, bool] = {}
    # G4 stub-collapse - ALWAYS graded. Every narrator-visible Lori
    # reply must be >= 6 words on a substantive narrator turn. Ungraded
    # turns still gate this because the narrator saw the stub.
    rows["G4_no_stub_collapse"] = not _is_stub_collapse(lori_response)
    if turn.graded:
        rows["F1_log_chain_classification"] = (log_is_chain == turn.expect_is_chain)
        rows["F2_log_anchor_count_meets"] = (
            (log_anchors or 0) >= turn.expect_min_anchors
            if turn.expect_is_chain
            else (log_anchors in (0, None))
        )
        rows["F3_log_cue_label_present"] = (
            not turn.expect_any_cue
            or any(c in log_cues for c in turn.expect_any_cue)
        )
        rows["F4_lori_no_sensory_pivot"] = sensory_m is None
        rows["F5_lori_one_question_max"] = qc <= 1
        rows["F6_lori_word_budget"] = wc <= WORD_BUDGET
        rows["G1_narrator_anchor_echo"] = anchor_hits >= min(2, max(1, len(narrator_anchors)))
        rows["G2_not_drift_repair_boilerplate"] = not is_drift_repair
        rows["G3_lori_reply_is_english"] = not is_spanish
        if turn.expect_meta_feedback:
            rows["M1_meta_feedback_detected"] = bool(log_meta)
            rows["M2_rejected_probe_type_sensory"] = (
                log_rejected == turn.expect_rejected_type
            )
    else:
        rows["U_ungraded_informational"] = True

    return TurnResult(
        turn=turn,
        lori_response=lori_response,
        log_is_chain=log_is_chain,
        log_confidence=log_conf,
        log_cue_labels=log_cues,
        log_anchor_count=log_anchors,
        log_meta_feedback=log_meta,
        log_rejected_type=log_rejected,
        response_word_count=wc,
        response_question_count=qc,
        sensory_pivot_match=sensory_m.group(0) if sensory_m else None,
        rows=rows,
    )


def write_ui_fixture() -> None:
    data = {
        "trip_id": "trip_2019_france_italy_paris_aix_rome",
        "title": "2019 France / Italy: Paris, Aix-en-Provence, Rome",
        "source_document": "May 26 thru June 15.docx",
        "date_range": {"start": "2019-05-26", "end": "2019-07-02"},
        "regions": [
            {
                "region_id": "paris",
                "title": "Paris base",
                "date_range": {"start": "2019-05-28", "end": "2019-06-06"},
                "base_address": "41 Rue de Reuilly, Paris",
                "stops": [
                    "Jardin du Luxembourg / Panthéon / Latin Quarter",
                    "Sainte-Chapelle / Notre-Dame / Centre Pompidou",
                    "Eiffel Tower / Trocadéro / Musée d'Orsay",
                    "Sacré-Cœur / Montmartre / Place du Tertre",
                    "Marché d'Aligre",
                    "Musée du Louvre",
                    "Arc de Triomphe / Nissim de Camondo / Galeries Lafayette",
                ],
            },
            {
                "region_id": "provence",
                "title": "Aix-en-Provence base",
                "date_range": {"start": "2019-06-06", "end": "2019-06-13"},
                "base_address": "15 rue Suffren, Aix-en-Provence",
                "stops": [
                    "Paris Gare de Lyon to Aix TGV",
                    "Aix base days",
                    "Avignon / Palais des Papes / Avignon Bridge / Arles",
                ],
            },
            {
                "region_id": "rome",
                "title": "Rome close and return",
                "date_range": {"start": "2019-06-28", "end": "2019-07-02"},
                "base_address": "Via Francesco Carletti, 1, Rome",
                "stops": ["Rome apartment", "FCO -> DFW -> ABQ return flights"],
            },
        ],
        "future_ui_tests": [
            "Trip detail renders date range and all regions.",
            "Paris region nests day chains under Paris base.",
            "Provence region includes Paris-to-Aix TGV transition and Avignon/Arles day trip.",
            "Rome close renders lodging and return flight chain.",
            "Location Guide explains French/Italian terms in English without switching chat language.",
        ],
    }
    UI_FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    UI_FIXTURE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


async def run() -> int:
    print("=" * 78)
    print("2019 France / Italy trip canary harness")
    print("(Lori behavior now; Trip UI fixture for later browser tests.)")
    print("=" * 78)
    write_ui_fixture()
    print(f"UI fixture written: {UI_FIXTURE_PATH}")

    print("\nStep 1 — creating 2019 trip-canary narrator")
    person_id = create_narrator()

    conv_id = f"trip_2019_france_italy_{uuid.uuid4().hex[:10]}"
    print(f"\nStep 2 — opening chat WS conv_id={conv_id}")

    results: List[TurnResult] = []
    async with websockets.connect(WS_URL, ping_interval=None, close_timeout=5) as ws:
        # Drain connected/status events opportunistically.
        try:
            await asyncio.wait_for(ws.recv(), timeout=2.0)
        except Exception:
            pass

        for turn in TURNS:
            print(f"\nStep 3.{turn.n} — sending {len(turn.text.split())}-word narrator turn (graded={turn.graded})")
            print(f"  >> {turn.text[:90]}{'...' if len(turn.text) > 90 else ''}")
            start = time.time()
            reply = await send_one_turn(ws, person_id, conv_id, turn)
            elapsed = time.time() - start
            print(f"  << Lori ({elapsed:.1f}s, {_word_count(reply)} words):")
            print(f"     {reply}")

            # Give api.log a moment to flush and read the most recent matching line.
            time.sleep(0.5)
            hits = grep_factual_chain_log_for_conv(conv_id)
            log_hit = hits[-1] if hits else None
            result = score_turn(turn, reply, log_hit)
            results.append(result)

            if turn.graded:
                print(f"  Rows: {result.passed_rows}/{result.total_rows}")
                failed = [k for k, v in result.rows.items() if not v]
                if failed:
                    print(f"  Failed: {', '.join(failed)}")
            else:
                print("  (ungraded turn — informational only)")

    print("\nStep 4 — querying story_candidates for chain_meta")
    chain_rows = [
        r for r in query_chain_meta_for_narrator(person_id)
        if (r.get("chain_meta") or {}).get("chain_story_candidate")
    ]
    print(f"  chain_rows={len(chain_rows)}  (informational; text-only WS may not persist)")

    total = sum(r.total_rows for r in results if r.turn.graded)
    passed = sum(r.passed_rows for r in results if r.turn.graded)

    graded_results = [r for r in results if r.turn.graded]
    drift_fail_count = sum(
        1 for r in graded_results
        if not r.rows.get("G2_not_drift_repair_boilerplate", True)
    )
    english_fail = any(
        not r.rows.get("G3_lori_reply_is_english", True)
        for r in graded_results
    )
    # G4 stub-collapse fires on EVERY visible Lori reply (graded
    # AND ungraded) per ChatGPT 2026-06-25 correction. T4 "Aligre."
    # was ungraded and the clamp missed it on the 2026-06-25 run.
    stub_fail = any(
        not r.rows.get("G4_no_stub_collapse", True)
        for r in results
    )
    meta_sensory_fail = any(
        r.turn.expect_meta_feedback
        and not r.rows.get("F4_lori_no_sensory_pivot", True)
        for r in graded_results
    )

    hard_clamps: List[str] = []
    if drift_fail_count >= max(1, len(graded_results) // 2):
        hard_clamps.append(f"G2_drift_repair_dominance ({drift_fail_count}/{len(graded_results)})")
    if english_fail:
        hard_clamps.append("G3_english_first_violation")
    if stub_fail:
        hard_clamps.append("G4_stub_collapse")
    if meta_sensory_fail:
        hard_clamps.append("F4_meta_feedback_sensory_pivot")

    pct = passed / total if total else 0.0
    verdict = "GREEN" if pct >= 0.86 else ("AMBER" if pct >= 0.76 else "RED")
    if hard_clamps:
        verdict = "RED"

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_DIR / f"trip_2019_france_italy_{conv_id}_{stamp}.txt"

    lines: List[str] = []
    lines.append("2019 France / Italy trip canary harness")
    lines.append(f"conv_id={conv_id}")
    lines.append(f"person_id={person_id}")
    lines.append(f"verdict={verdict} score={passed}/{total}")
    if hard_clamps:
        lines.append(f"hard_clamps={', '.join(hard_clamps)}")
    lines.append("")
    for r in results:
        lines.append(f"T{r.turn.n} {r.turn.note}")
        lines.append(f"USER: {r.turn.text}")
        lines.append(f"LORI: {r.lori_response}")
        lines.append(f"ROWS: {r.passed_rows}/{r.total_rows} {r.rows}")
        lines.append(f"LOG: is_chain={r.log_is_chain} anchors={r.log_anchor_count} cues={r.log_cue_labels} meta={r.log_meta_feedback} rejected={r.log_rejected_type}")
        lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")

    print("\nStep 5 — writing report")
    print(f"Report written: {report_path}")
    print()
    if hard_clamps:
        print(f"✗ {verdict} {passed}/{total} — hard clamps: {', '.join(hard_clamps)}")
    else:
        print(f"✓ {verdict} {passed}/{total}")
    return 0 if verdict == "GREEN" else 1


def main() -> None:
    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
