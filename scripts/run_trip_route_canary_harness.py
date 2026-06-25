#!/usr/bin/env python3
"""Trip-route canary harness — Spring 2026 Central Europe & Northern
Italy ONLY.

This is the Trip Tab readiness gate, NOT the Trip Tab feature itself.
It does not write to any trip_* tables (none exist yet — see
WO-TRIP-IMPORT-AND-CLUSTER-01 and WO-TRIP-TAB-DB-01, both UNWRITTEN).
What it does test is the prerequisite WO that gates the trip lane:

    WO-LORI-FACTUAL-CHAIN-CAPTURE-01

Per WO-TRIP-MEMOIR-01 §"Relationship to Trips":

    Trips should not move from PARKED to ACTIVE until this WO proves
    that Lori can capture factual route/event chains. Otherwise the
    hierarchical trip schema will be technically correct but
    conversationally empty.

The Lori-listening regression harness for the broader chain class
(military, school/work, family migration, medical, etc., including
Kent's recorded canary) lives at:

    scripts/run_factual_chain_live_harness.py

This file is trip-shaped narration only. No Kent. No military induction.
No medical sequences. Just the real Spring 2026 itinerary turned into
narrator-shaped chains so we can verify:

  * Lori detects the route as a factual chain
  * Lori does not pivot to scenery / sounds / smells / atmosphere
  * The disruption return-journey class fires
  * Meta-feedback against sensory probes is honored
  * chain_meta_json lands on the story_candidates row with the
    actual European city names as anchors

Turns:

  T1  Outbound route               — Prague → Salzburg → Graz →
                                     Ljubljana → Pula → Muggia /
                                     Trieste → Mirano → Venice (long
                                     multi-place sequence)
  T2  Mirano hub-and-spoke         — Mirano base → Treviso, Padua,
                                     Cittadella, Chioggia, Mira, Venice
  T3  Pula hub-and-spoke           — Pula / Medulin base → Rovinj,
                                     Istrian coast, Pula Roman sites
  T4  Sensory setup (UNGRADED)     — one warm Venice memory so T6 has
                                     a real sensory prior to push back
                                     against
  T5  Return-journey disruption    — Venice → Dulles → Denver →
                                     Santa Fe (return-disruption class)
  T6  Meta-feedback + theme chain  — narrator rejects sensory probe AND
                                     asserts a thematic chain (Roman
                                     ruins → Venetian villa frescoes →
                                     medieval walled town) crossing the
                                     Mirano + Pula bases

Per graded turn (T1/T2/T3/T5/T6) six rows are scored:

  F1 log_chain_classification     — [chat_ws][factual-chain] log line
                                    is_chain matches expectation
  F2 log_anchor_count_meets       — log anchors count ≥ expected
  F3 log_cue_label_present        — log cue labels include at least one
                                    expected label
  F4 lori_no_sensory_pivot        — Lori reply contains no scenery /
                                    sights / sounds / smells / atmosphere
                                    vocab (canonical _SENSORY_PROBE_RX)
  F5 lori_one_question_max        — Lori reply has ≤ 1 question mark
  F6 lori_word_budget             — Lori reply ≤ 90 words

Two extras on T6:

  M1 meta_feedback_detected       — log meta_feedback=True
  M2 rejected_probe_type_sensory  — log rejected_probe_type=sensory

Two DB rows after all turns:

  D1 chain_meta_persisted         — at least floor(graded_chain_turns *
                                    0.5) narrator turns have a
                                    story_candidates row with non-empty
                                    chain_meta_json
  D2 chain_meta_shape             — chain_meta keys include
                                    chain_story_candidate=true,
                                    chain_anchors, chain_cue_labels,
                                    chain_confidence

Total: 5 graded turns × 6 + 2 meta + 2 db = 34 rows.
Acceptance: ≥ 30/34 GREEN, 26-29/34 AMBER, < 26/34 RED.

Usage:

    cd /mnt/c/Users/chris/hornelore
    .venv-gpu/bin/python scripts/run_trip_route_canary_harness.py

Stack must be warm. Cold-boot run will time out the first turn — wait
~4 minutes after start_all.sh before running.

Writes a single-page report to:
    docs/reports/trip_route_canary_<conv_id>_<stamp>.txt
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
)


# ─────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────

API_BASE = os.environ.get("HORNELORE_API_BASE", "http://localhost:8000")
WS_URL = os.environ.get(
    "HORNELORE_CHAT_WS", "ws://localhost:8000/api/chat/ws"
)
API_LOG = Path(os.environ.get(
    "HORNELORE_API_LOG",
    "/mnt/c/Users/chris/hornelore/.runtime/logs/api.log",
))
REPORTS_DIR = Path(os.environ.get(
    "HORNELORE_REPORTS_DIR",
    "/mnt/c/Users/chris/hornelore/docs/reports",
))
DB_PATH = Path(os.environ.get(
    "HORNELORE_DB_PATH",
    "/mnt/c/hornelore_data/db/hornelore.sqlite3",
))

# Test narrator: Chris-like Spring 2026 traveler. Created fresh per run
# with testing_only=True so live narrators stay isolated.
NARRATOR_DISPLAY_NAME = "Trip Canary Narrator (Spring 2026)"
NARRATOR_DOB = "1965-12-24"
NARRATOR_POB = "Bismarck, ND"
NARRATOR_PRONOUNS = "he_him"
NARRATOR_RESIDENCE = "Santa Fe, NM"

WORD_BUDGET = 90
TURN_TIMEOUT = 90.0


# ─────────────────────────────────────────────────────────────────────
# 6-turn script — Spring 2026 trip ONLY
# ─────────────────────────────────────────────────────────────────────


@dataclass
class Turn:
    n: int
    text: str
    expect_is_chain: bool
    expect_min_anchors: int
    expect_any_cue: List[str]
    expect_meta_feedback: bool
    expect_rejected_type: str
    graded: bool
    note: str


TURNS: List[Turn] = [
    Turn(
        n=1,
        text=(
            "On the outbound, we flew into Prague, then drove to "
            "Salzburg, then Graz, then crossed into Slovenia at "
            "Ljubljana, then down to Pula on the Istrian coast, "
            "then over to Muggia and Trieste, and finally settled "
            "outside Venice at Mirano."
        ),
        expect_is_chain=True,
        expect_min_anchors=6,
        expect_any_cue=["multi_place_sequence", "travel_leg_sequence"],
        expect_meta_feedback=False,
        expect_rejected_type="",
        graded=True,
        note="Spring 2026 outbound route — 8-city travel leg sequence",
    ),
    Turn(
        n=2,
        text=(
            "Mirano was our base in the Veneto. From there we went "
            "to Treviso, then Padua for the Scrovegni Chapel, then "
            "Cittadella for the medieval walls, then Chioggia and "
            "Mira along the lagoon, and then into Venice itself."
        ),
        expect_is_chain=True,
        expect_min_anchors=5,
        expect_any_cue=["multi_place_sequence", "travel_leg_sequence"],
        expect_meta_feedback=False,
        expect_rejected_type="",
        graded=True,
        note="Mirano hub-and-spoke — six day-trips from Veneto base",
    ),
    Turn(
        n=3,
        text=(
            "Before Italy we based out of Pula and Medulin on the "
            "Istrian coast. From there we did Rovinj, then drove the "
            "Istrian coast road, then came back to walk the Roman "
            "amphitheater and forum at Pula."
        ),
        expect_is_chain=True,
        expect_min_anchors=3,
        expect_any_cue=["multi_place_sequence", "travel_leg_sequence"],
        expect_meta_feedback=False,
        expect_rejected_type="",
        graded=True,
        note="Pula hub-and-spoke — Istrian coast day-trips",
    ),
    Turn(
        n=4,
        text=(
            "We stood on a balcony in Venice at sunset. The lagoon "
            "was glassy and the bells were ringing across the water."
        ),
        expect_is_chain=False,
        expect_min_anchors=0,
        expect_any_cue=[],
        expect_meta_feedback=False,
        expect_rejected_type="",
        graded=False,
        note=(
            "UNGRADED sensory setup — Lori is free to ask a sensory "
            "follow-up so T6 has a real prior assistant turn to push "
            "back against"
        ),
    ),
    Turn(
        n=5,
        text=(
            "The flight out of Venice was delayed, then we had to "
            "get through Dulles, then Denver, then finally home to "
            "Santa Fe."
        ),
        expect_is_chain=True,
        expect_min_anchors=3,
        expect_any_cue=["disruption_sequence", "multi_place_sequence"],
        expect_meta_feedback=False,
        expect_rejected_type="",
        graded=True,
        note="Return-journey disruption chain (Venice → Santa Fe)",
    ),
    Turn(
        n=6,
        text=(
            "No, not the atmosphere — what mattered was the thread "
            "across the trip. We saw the Roman amphitheater at Pula, "
            "then the Scrovegni frescoes at Padua, then the medieval "
            "walls at Cittadella. Those three connect."
        ),
        expect_is_chain=True,
        expect_min_anchors=3,
        expect_any_cue=["multi_place_sequence"],
        expect_meta_feedback=True,
        expect_rejected_type="sensory",
        graded=True,
        note=(
            "Meta-feedback rejecting sensory + asserting a thematic "
            "chain (Roman / Venetian villa / medieval walled town)"
        ),
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


# ─────────────────────────────────────────────────────────────────────
# Helpers (shared shape with run_factual_chain_live_harness.py —
# duplicated rather than imported to keep this harness self-contained)
# ─────────────────────────────────────────────────────────────────────


def _http_post_json(
    url: str, payload: Dict[str, Any], timeout: float = 30.0
) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"},
    )
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
    print(f"  ✓ Created trip-canary narrator person_id={pid}")
    return pid


async def send_one_turn(
    ws: Any, person_id: str, conv_id: str, turn: Turn,
) -> str:
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
            print(
                f"[WARN] turn {turn.n} got error event: {msg}",
                file=sys.stderr,
            )
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
        lines = API_LOG.read_text(
            encoding="utf-8", errors="replace",
        ).splitlines()
    except Exception:
        return []
    tail = lines[-15000:]
    hits: List[Dict[str, Any]] = []
    for line in tail:
        if "[chat_ws][factual-chain]" not in line:
            continue
        if conv_id not in line:
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
        cues = _CUE_RX.findall(gd["cues"])
        is_chain_str = gd["is_chain"]
        meta_str = gd["meta"]
        hits.append({
            "raw": line,
            "is_chain": (
                True if is_chain_str == "True"
                else (False if is_chain_str == "False" else None)
            ),
            "conf": conf,
            "cues": cues,
            "anchors": anchors,
            "meta_feedback": (
                True if meta_str == "True"
                else (False if meta_str == "False" else None)
            ),
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
                "SELECT id, trigger_reason, transcript, chain_meta_json, "
                "created_at FROM story_candidates "
                "WHERE narrator_id = ? ORDER BY created_at DESC LIMIT 20;",
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
        print(
            f"[WARN] sqlite query failed for narrator={person_id}: {exc}",
            file=sys.stderr,
        )
        return []


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def _question_count(text: str) -> int:
    return text.count("?") + max(0, text.count("¿") - text.count("?"))


def score_turn(
    turn: Turn, lori_response: str, log_hit: Optional[Dict[str, Any]],
) -> TurnResult:
    wc = _word_count(lori_response)
    qc = _question_count(lori_response)
    sensory_m = _SENSORY_PROBE_RX.search(lori_response or "")

    log_is_chain = log_hit.get("is_chain") if log_hit else None
    log_conf = log_hit.get("conf") if log_hit else None
    log_cues = list(log_hit.get("cues") or []) if log_hit else []
    log_anchors = log_hit.get("anchors") if log_hit else None
    log_meta = log_hit.get("meta_feedback") if log_hit else None
    log_rejected = (log_hit.get("rejected") or "") if log_hit else ""

    rows: Dict[str, bool] = {}
    if turn.graded:
        rows["F1_log_chain_classification"] = (
            log_is_chain is not None
            and log_is_chain == turn.expect_is_chain
        )
        rows["F2_log_anchor_count_meets"] = (
            log_anchors is not None
            and log_anchors >= turn.expect_min_anchors
        )
        rows["F3_log_cue_label_present"] = (
            bool(turn.expect_any_cue) is False
            or any(c in log_cues for c in turn.expect_any_cue)
        )
        rows["F4_lori_no_sensory_pivot"] = sensory_m is None
        rows["F5_lori_one_question_max"] = qc <= 1
        rows["F6_lori_word_budget"] = wc <= WORD_BUDGET
        if turn.expect_meta_feedback:
            rows["M1_meta_feedback_detected"] = log_meta is True
            rows["M2_rejected_probe_type_sensory"] = (
                log_rejected.lower() == turn.expect_rejected_type.lower()
            )

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


def score_db(
    person_id: str, results: List[TurnResult],
) -> Dict[str, bool]:
    db_rows = query_chain_meta_for_narrator(person_id)
    graded_chain_turn_count = sum(
        1 for r in results
        if r.turn.graded and r.turn.expect_is_chain
    )
    non_empty_chain_rows = [
        r for r in db_rows if isinstance(r.get("chain_meta"), dict)
        and r["chain_meta"].get("chain_story_candidate") is True
    ]
    d1_threshold = max(1, int(graded_chain_turn_count * 0.5))
    d1 = len(non_empty_chain_rows) >= d1_threshold

    d2 = False
    if non_empty_chain_rows:
        sample = non_empty_chain_rows[0]["chain_meta"]
        d2 = (
            sample.get("chain_story_candidate") is True
            and isinstance(sample.get("chain_anchors"), list)
            and isinstance(sample.get("chain_cue_labels"), list)
            and isinstance(sample.get("chain_confidence"), (int, float))
        )
    return {
        "D1_chain_meta_persisted": d1,
        "D2_chain_meta_shape":     d2,
        "_db_rows_observed":       len(db_rows),
        "_chain_rows_observed":    len(non_empty_chain_rows),
    }


def write_report(
    conv_id: str, person_id: str,
    results: List[TurnResult], db_rows_scored: Dict[str, Any],
) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_conv = (conv_id or "anon")[:12]
    path = REPORTS_DIR / f"trip_route_canary_{short_conv}_{stamp}.txt"

    total_passed = sum(r.passed_rows for r in results)
    total_rows = sum(r.total_rows for r in results)
    db_pass = sum(
        1 for k, v in db_rows_scored.items()
        if not k.startswith("_") and v
    )
    db_total = sum(
        1 for k in db_rows_scored if not k.startswith("_")
    )
    total_passed += db_pass
    total_rows += db_total

    if total_rows == 0:
        pct = 0.0
        verdict = "RED"
    else:
        pct = total_passed / total_rows * 100.0
        verdict = (
            "GREEN" if total_passed >= 30
            else ("AMBER" if total_passed >= 26 else "RED")
        )

    lines: List[str] = []
    lines.append("=" * 78)
    lines.append(
        "Trip-route canary harness — Spring 2026 Central Europe / "
        "Northern Italy"
    )
    lines.append("=" * 78)
    lines.append("(Trip Tab readiness gate — NOT the Trip Tab feature.)")
    lines.append("")
    lines.append(f"timestamp:       {datetime.now().isoformat()}")
    lines.append(f"person_id:       {person_id}")
    lines.append(f"conv_id:         {conv_id}")
    lines.append(f"turns_completed: {len(results)} / 6")
    lines.append(f"contract_score:  {total_passed} / {total_rows}  ({pct:.1f}%)")
    lines.append(f"verdict:         {verdict}")
    lines.append("")
    lines.append("Acceptance gates (34 graded rows):")
    lines.append("  GREEN: ≥ 30/34")
    lines.append("  AMBER: 26-29/34")
    lines.append("  RED:   < 26/34")
    lines.append("")

    for r in results:
        lines.append("-" * 78)
        graded_tag = "GRADED" if r.turn.graded else "ungraded"
        lines.append(f"Turn {r.turn.n} — {graded_tag}")
        lines.append(f"  note: {r.turn.note}")
        lines.append(f"  Narrator: {r.turn.text}")
        lines.append("  Lori (verbatim):")
        for line in (r.lori_response or "(no response)").splitlines():
            lines.append(f"    {line}")
        lines.append("")
        lines.append(
            f"  log:  is_chain={r.log_is_chain}  conf={r.log_confidence}  "
            f"anchors={r.log_anchor_count}  cues={r.log_cue_labels}  "
            f"meta={r.log_meta_feedback}  rejected={r.log_rejected_type!r}"
        )
        lines.append(
            f"  reply: words={r.response_word_count}  "
            f"questions={r.response_question_count}  "
            f"sensory_pivot_match={r.sensory_pivot_match!r}"
        )
        if r.turn.graded:
            lines.append("  Rows:")
            for row_name, ok in r.rows.items():
                mark = "✓" if ok else "✗"
                lines.append(f"    {mark} {row_name}")
        lines.append("")

    lines.append("-" * 78)
    lines.append("DB checks (Phase 4 — story_candidates.chain_meta_json):")
    for k, v in db_rows_scored.items():
        if k.startswith("_"):
            lines.append(f"    (info) {k} = {v}")
        else:
            mark = "✓" if v else "✗"
            lines.append(f"    {mark} {k}")
    lines.append("")
    lines.append(f"Final verdict: {verdict}")

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written: {path}")
    return path


# ─────────────────────────────────────────────────────────────────────
# Driver
# ─────────────────────────────────────────────────────────────────────


async def run() -> int:
    print("=" * 78)
    print(
        "Trip-route canary harness — Spring 2026 Central Europe / "
        "Northern Italy"
    )
    print("(Trip Tab readiness gate — NOT the Trip Tab feature.)")
    print("=" * 78)

    print("\nStep 1 — creating trip-canary narrator via /api/people/intake")
    person_id = create_narrator()
    conv_id = f"trip_canary_{uuid.uuid4().hex[:10]}"
    print(f"\nStep 2 — opening chat WS conv_id={conv_id}")

    results: List[TurnResult] = []
    async with websockets.connect(WS_URL, max_size=2_000_000) as ws:
        for turn in TURNS:
            print(
                f"\nStep 3.{turn.n} — sending {len(turn.text.split())}-word "
                f"narrator turn (graded={turn.graded})"
            )
            print(f"  >> {turn.text[:80]}{'...' if len(turn.text) > 80 else ''}")
            t0 = time.time()
            try:
                lori = await send_one_turn(ws, person_id, conv_id, turn)
            except Exception as exc:
                print(f"  [ERROR] send failed: {exc}", file=sys.stderr)
                lori = ""
            elapsed = time.time() - t0
            print(f"  << Lori ({elapsed:.1f}s, {_word_count(lori)} words):")
            for line in lori.splitlines():
                print(f"     {line}")

            hits = grep_factual_chain_log_for_conv(conv_id)
            log_hit = hits[turn.n - 1] if turn.n - 1 < len(hits) else None

            r = score_turn(turn, lori, log_hit)
            results.append(r)
            if turn.graded:
                print(f"  Rows: {r.passed_rows}/{r.total_rows}")
            else:
                print(f"  (ungraded turn — informational only)")

    print("\nStep 4 — querying story_candidates for chain_meta")
    db_scored = score_db(person_id, results)
    print(
        f"  db_rows={db_scored.get('_db_rows_observed', 0)}  "
        f"chain_rows={db_scored.get('_chain_rows_observed', 0)}"
    )

    print("\nStep 5 — writing report")
    write_report(conv_id, person_id, results, db_scored)

    total_passed = sum(r.passed_rows for r in results)
    total_rows = sum(r.total_rows for r in results)
    total_passed += sum(
        1 for k, v in db_scored.items()
        if not k.startswith("_") and v
    )
    total_rows += sum(
        1 for k in db_scored if not k.startswith("_")
    )

    if total_passed >= 30:
        print(f"\n✓ GREEN {total_passed}/{total_rows}")
        return 0
    if total_passed >= 26:
        print(f"\n• AMBER {total_passed}/{total_rows}")
        return 0
    print(f"\n✗ RED {total_passed}/{total_rows}")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
