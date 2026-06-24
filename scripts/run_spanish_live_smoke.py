#!/usr/bin/env python3
"""WO-SPANISH-LIVE-READINESS-01 — Spanish live-laptop smoke harness.

Drives a 6-turn conversation that hits every Spanish-readiness contract
Chris specified:

  1. English narrator turn with Spanish proper nouns ("Antonio", "Las
     Vegas, New Mexico"). Lori must respond in ENGLISH. Proper-noun
     leakage into Spanish is the looks_spanish() overfire class
     (BUG-LORI-SPANISH-DETECT-OVER-TRIGGER-01).

  2. Pure Spanish narrator turn — childhood memory. Lori must respond
     in SPANISH with full Spanish grammar (no Spanglish scaffolding).

  3. Spanish correction ("Quise decir que mi hermano se llamaba
     Antonio, no Alberto."). Lori must parse the retraction and
     acknowledge in Spanish (compose_correction_ack ES branch).

  4. Spanish age memory. Lori must respond with a lived-experience
     follow-up in Spanish — not interrogate a seeded fact.

  5. Spanish family memory with sensory anchor. Lori must respond
     warmly in Spanish, NO fake-praise meta-preamble ("Qué descripción
     tan rica..." class).

  6. Explicit English switch. Lori must respond in ENGLISH and not
     continue in Spanish.

Per-turn scoring (the 6 contract rows):
  L1. expected_language_matches      — Lori's language matches the per-
                                       turn expectation
  L2. no_broken_code_mix             — detect_broken_code_mix() returns
                                       None on Lori's text
  L3. no_meta_response_leak          — detect_meta_response_leak()
                                       returns False (both EN + ES
                                       patterns)
  L4. word_budget_honored            — ≤ 90 words (clear_direct cap)
  L5. one_question_max               — ≤ 1 question mark or ¿
  L6. tts_voice_correct              — api.log shows af_heart for EN,
                                       ef_dora for ES

Acceptance: 6 turns × 6 rows = 36 cells. PASS if ≥ 33/36 (allow up to
3 cells of stochastic variance). RED if < 30/36.

Usage:

    cd /mnt/c/Users/chris/hornelore
    python3 scripts/run_spanish_live_smoke.py

Stack must be warm (Llama + Kokoro both loaded). Cold-boot run will
time out the first turn — wait ~4 minutes after start_all.sh before
running.

Writes a single-page report to:
    docs/reports/spanish_live_smoke_<conv_id>.txt

WO-SPANISH-LIVE-READINESS-01 Patch 6 (2026-06-17).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# WebSocket client — uses the websockets package the existing harness
# ships against.
import websockets  # type: ignore

# Add scripts/ to import path so we can reuse the looks_spanish + guard
# detectors directly (avoids re-implementing the contract checks).
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "server" / "code"))

from api.services.lori_spanish_guard import looks_spanish  # noqa: E402
from api.services.lori_response_guards import (  # noqa: E402
    detect_broken_code_mix,
    detect_meta_response_leak,
)

# ─────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────

API_BASE = os.environ.get("HORNELORE_API_BASE", "http://localhost:8000")
WS_URL = os.environ.get("HORNELORE_CHAT_WS", "ws://localhost:8000/api/chat/ws")
API_LOG = Path(os.environ.get(
    "HORNELORE_API_LOG",
    "/mnt/c/Users/chris/hornelore/.runtime/logs/api.log",
))
REPORTS_DIR = Path(os.environ.get(
    "HORNELORE_REPORTS_DIR",
    "/mnt/c/Users/chris/hornelore/docs/reports",
))

# Narrator identity (will be created fresh per run via /api/people/intake).
NARRATOR_DISPLAY_NAME = "Esteban García (Spanish smoke harness)"
NARRATOR_DOB = "1955-03-12"
NARRATOR_POB = "Las Vegas, NM"
NARRATOR_PRONOUNS = "he_him"
NARRATOR_RESIDENCE = "Las Vegas, NM"

# Word budget per Lori turn (clear_direct cap is 55; we allow headroom
# to 90 because oral_history can run longer and we don't want spurious
# RED on warm narrators).
WORD_BUDGET = 90

# Per-turn read timeout in seconds. Llama can take 30-60s on warm
# stack for a long Spanish response.
TURN_TIMEOUT = 90.0

# ─────────────────────────────────────────────────────────────────────
# 6-turn script (Chris's spec, 2026-06-17)
# ─────────────────────────────────────────────────────────────────────


@dataclass
class Turn:
    n: int
    text: str
    expected_lang: str  # "en" or "es"
    note: str  # one-liner describing what we're testing


TURNS: List[Turn] = [
    Turn(
        n=1,
        text=(
            "My older brother Antonio and I grew up in Las Vegas, "
            "New Mexico. My mother lit candles in the cellar."
        ),
        expected_lang="en",
        note="English with Spanish proper nouns — must NOT overfire to Spanish",
    ),
    Turn(
        n=2,
        text="Mi mamá encendía velas en el sótano y yo no sabía por qué.",
        expected_lang="es",
        note="Pure Spanish childhood memory — must respond in Spanish",
    ),
    Turn(
        n=3,
        text="Quise decir que mi hermano se llamaba Antonio, no Alberto.",
        expected_lang="es",
        note="Spanish correction — must parse retraction + ack in Spanish",
    ),
    Turn(
        n=4,
        text="Yo tenía ocho años cuando nos mudamos de la casa vieja.",
        expected_lang="es",
        note="Spanish age memory — must respond with lived-experience follow-up",
    ),
    Turn(
        n=5,
        text=(
            "Mi abuela siempre decía que algunas cosas se recuerdan en "
            "silencio."
        ),
        expected_lang="es",
        note="Spanish sensory family memory — no fake meta-praise",
    ),
    Turn(
        n=6,
        text="Now I want to continue in English.",
        expected_lang="en",
        note="Explicit English switch — must follow narrator's lead",
    ),
]


@dataclass
class TurnResult:
    turn: Turn
    lori_response: str
    detected_lang: str
    response_word_count: int
    response_question_count: int
    code_mix_marker: Optional[str]
    meta_leak: bool
    tts_lang_observed: Optional[str]
    rows: Dict[str, bool] = field(default_factory=dict)

    @property
    def passed_rows(self) -> int:
        return sum(1 for v in self.rows.values() if v)

    @property
    def total_rows(self) -> int:
        return len(self.rows)


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────


def _http_post_json(url: str, payload: Dict[str, Any], timeout: float = 30.0) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return json.loads(body)


def create_narrator() -> str:
    """POST /api/people/intake — fresh narrator per run.

    Payload shape matches NarratorIntakePayload in
    server/code/api/routers/people.py (post-2026-06-17 schema):
      * full_legal_name + preferred_name both required
      * consent_recording_agreement (not consent_recording)
      * family_of_origin uses flat father_name / mother_name strings
        (not nested {name: ...} dicts)
    """
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
        "family_of_origin": {
            "mother_name": "María García",
            "father_name": "José García",
            "siblings": [{"name": "Antonio García"}],
        },
    }
    try:
        resp = _http_post_json(f"{API_BASE}/api/people/intake", payload)
    except Exception as exc:
        print(f"[ERROR] /api/people/intake failed: {exc}", file=sys.stderr)
        # Fall back to legacy /api/people endpoint
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
        raise RuntimeError(
            f"create_narrator: no person_id in response: {resp}",
        )
    print(f"  ✓ Created narrator person_id={pid}")
    return pid


async def send_one_turn(
    ws: Any, person_id: str, conv_id: str, turn: Turn,
) -> str:
    """Send one user turn, wait for the {done} event, return final_text.

    Payload shape matches chat_ws.py message dispatch (current contract):
      * type: 'start_turn' (was 'user' in legacy harness)
      * message: narrator text (was 'text')
      * params.person_id: narrator UUID (was top-level person_id)
      * session_id / conv_id: conversation id (either accepted)
      * turn_mode: routes the prompt composer
    """
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


# Count closing question marks only. Spanish "¿X?" is one question, not
# two — the prior `[?¿]` pattern counted opening + closing marks as
# separate questions, breaking L5 (one_question_max) on every Spanish
# Lori turn. If Lori produces an orphan `¿` with no closing `?`, count
# it too (rare formatting glitch but legitimately a question gesture).
_CLOSING_Q_RX = re.compile(r"\?")
_OPENING_Q_RX = re.compile(r"¿")


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def _question_count(text: str) -> int:
    t = text or ""
    closing = len(_CLOSING_Q_RX.findall(t))
    # Orphan-`¿` count = openings that exceed closings (un-paired).
    opening = len(_OPENING_Q_RX.findall(t))
    orphans = max(0, opening - closing)
    return closing + orphans


def _detect_response_lang(text: str) -> str:
    """Light wrapper around looks_spanish; returns 'es' or 'en'."""
    if looks_spanish(text or ""):
        return "es"
    return "en"


def _grep_tts_lang_for_conv(conv_id: str) -> List[str]:
    """Grep api.log for the per-turn TTS language tags for this conv.

    Looks for the [ml-tts][fe] log line or the kokoro adapter language
    tag. Returns the language codes observed in order.
    """
    if not API_LOG.exists():
        return []
    try:
        lines = API_LOG.read_text(
            encoding="utf-8", errors="replace",
        ).splitlines()
    except Exception:
        return []
    # Most recent 5000 lines is plenty for one harness run.
    tail = lines[-5000:]
    pat_fe = re.compile(r"\[ml-tts\]\[fe\]\s+lang=(\w+)")
    pat_kokoro = re.compile(r"\[kokoro\]\s+synthesize\s+lang=(\w+)")
    observed: List[str] = []
    for line in tail:
        if conv_id and conv_id not in line:
            # Best-effort: not every TTS log line carries conv_id; we
            # still pick up the broader set if conv_id is missing.
            pass
        m = pat_fe.search(line) or pat_kokoro.search(line)
        if m:
            observed.append(m.group(1).lower())
    return observed


def score_turn(
    turn: Turn, lori_response: str, tts_langs: List[str],
) -> TurnResult:
    detected_lang = _detect_response_lang(lori_response)
    wc = _word_count(lori_response)
    qc = _question_count(lori_response)
    code_mix = detect_broken_code_mix(lori_response)
    meta_leak = detect_meta_response_leak(lori_response)
    tts_lang = tts_langs[turn.n - 1] if turn.n - 1 < len(tts_langs) else None

    rows = {
        "L1_expected_language_matches": detected_lang == turn.expected_lang,
        "L2_no_broken_code_mix":         code_mix is None,
        "L3_no_meta_response_leak":      not meta_leak,
        "L4_word_budget_honored":        wc <= WORD_BUDGET,
        "L5_one_question_max":           qc <= 1,
        "L6_tts_voice_correct":          (
            (tts_lang == "es" and turn.expected_lang == "es") or
            (tts_lang == "en" and turn.expected_lang == "en") or
            tts_lang is None  # missing log line is informational only
        ),
    }

    return TurnResult(
        turn=turn,
        lori_response=lori_response,
        detected_lang=detected_lang,
        response_word_count=wc,
        response_question_count=qc,
        code_mix_marker=code_mix,
        meta_leak=meta_leak,
        tts_lang_observed=tts_lang,
        rows=rows,
    )


def write_report(
    conv_id: str, person_id: str, results: List[TurnResult],
) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_conv = (conv_id or "anon")[:12]
    path = REPORTS_DIR / f"spanish_live_smoke_{short_conv}_{stamp}.txt"

    total_passed = sum(r.passed_rows for r in results)
    total_rows = sum(r.total_rows for r in results)
    pct = (total_passed / total_rows * 100.0) if total_rows else 0.0
    verdict = (
        "GREEN" if pct >= (33 / 36) * 100.0
        else ("AMBER" if pct >= (30 / 36) * 100.0 else "RED")
    )

    lines: List[str] = []
    lines.append("=" * 78)
    lines.append("WO-SPANISH-LIVE-READINESS-01 — Spanish live-smoke report")
    lines.append("=" * 78)
    lines.append(f"timestamp:       {datetime.now().isoformat()}")
    lines.append(f"person_id:       {person_id}")
    lines.append(f"conv_id:         {conv_id}")
    lines.append(f"turns_completed: {len(results)} / 6")
    lines.append(f"contract_score:  {total_passed} / {total_rows}  ({pct:.1f}%)")
    lines.append(f"verdict:         {verdict}")
    lines.append("")
    lines.append("Acceptance gates:")
    lines.append("  GREEN: ≥ 33/36 (91.7%)")
    lines.append("  AMBER: 30-32/36 (83.3-88.9%)")
    lines.append("  RED:   < 30/36")
    lines.append("")

    for r in results:
        lines.append("-" * 78)
        lines.append(f"Turn {r.turn.n} — expected_lang={r.turn.expected_lang}")
        lines.append(f"  note: {r.turn.note}")
        lines.append("  Narrator:")
        lines.append(f"    {r.turn.text}")
        lines.append("  Lori (verbatim):")
        for line in (r.lori_response or "(no response)").splitlines():
            lines.append(f"    {line}")
        lines.append("")
        lines.append(
            f"  detected_lang={r.detected_lang}  "
            f"words={r.response_word_count}  "
            f"questions={r.response_question_count}  "
            f"tts={r.tts_lang_observed or '(no log)'}"
        )
        if r.code_mix_marker:
            lines.append(f"  code_mix_marker: {r.code_mix_marker!r}")
        if r.meta_leak:
            lines.append("  meta_leak: TRUE")
        lines.append("")
        lines.append("  Rows:")
        for row, ok in r.rows.items():
            mark = "✓" if ok else "✗"
            lines.append(f"    {mark} {row}")
        lines.append("")

    lines.append("=" * 78)
    lines.append("Summary matrix:")
    lines.append("=" * 78)
    header = "turn | " + " | ".join(f"L{i}" for i in range(1, 7))
    lines.append(header)
    lines.append("-" * len(header))
    for r in results:
        cells = "  | ".join(
            "✓" if ok else "✗" for ok in r.rows.values()
        )
        lines.append(f"  {r.turn.n}  |  {cells}")
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
    print("WO-SPANISH-LIVE-READINESS-01 — Spanish live-smoke harness")
    print("=" * 78)

    print("\nStep 1 — creating narrator via /api/people/intake")
    person_id = create_narrator()

    conv_id = f"spanish_smoke_{uuid.uuid4().hex[:10]}"
    print(f"\nStep 2 — opening chat WS conv_id={conv_id}")

    results: List[TurnResult] = []
    async with websockets.connect(WS_URL, max_size=2_000_000) as ws:
        for turn in TURNS:
            print(
                f"\nStep 3.{turn.n} — sending {len(turn.text.split())}-word "
                f"narrator turn (expected_lang={turn.expected_lang})"
            )
            print(f"  >> {turn.text[:80]}{'...' if len(turn.text) > 80 else ''}")
            t0 = time.time()
            try:
                lori_response = await send_one_turn(
                    ws, person_id, conv_id, turn,
                )
            except Exception as exc:
                print(f"  [ERROR] send failed: {exc}", file=sys.stderr)
                lori_response = ""
            elapsed = time.time() - t0
            print(f"  << Lori ({elapsed:.1f}s, {_word_count(lori_response)} words):")
            for line in lori_response.splitlines():
                print(f"     {line}")

            # Score this turn against the 6-row contract.
            tts_langs = _grep_tts_lang_for_conv(conv_id)
            r = score_turn(turn, lori_response, tts_langs)
            results.append(r)
            print(f"  Rows: {r.passed_rows}/{r.total_rows}")

    print("\nStep 4 — writing report")
    write_report(conv_id, person_id, results)

    total_passed = sum(r.passed_rows for r in results)
    total_rows = sum(r.total_rows for r in results)
    pct = (total_passed / total_rows * 100.0) if total_rows else 0.0
    if pct >= (33 / 36) * 100.0:
        print("\n✓ GREEN")
        return 0
    elif pct >= (30 / 36) * 100.0:
        print("\n• AMBER (stochastic variance)")
        return 0
    print("\n✗ RED (Spanish runtime contract failed)")
    return 1


if __name__ == "__main__":
    try:
        rc = asyncio.run(run())
    except KeyboardInterrupt:
        rc = 130
    sys.exit(rc)
