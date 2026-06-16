#!/usr/bin/env python3
"""Shared long-narration harness scaffold.

Extracted from scripts/run_jake_long_narration_harness.py (2026-06-15)
so the same WS-send / scorer / report-writer / log-grep stack can drive
multiple narrator personas without copy-paste drift.

The Jake harness stays as a complete standalone (it's a known-working
reference). New harnesses (Shatner, they/them, late-coming-out gay
narrator, female teacher + Betty, multicultural regional variants)
import HarnessConfig + run_harness from this module and provide
narrator-specific data.

USAGE:
    from harness_lib import HarnessConfig, ChapterConfig, run_harness

    cfg = HarnessConfig(
        narrator_label="William Shatner",
        intake_payload={...},          # full /api/people/intake body
        chapters=[
            ChapterConfig(
                label="Earliest Years",
                runtime71_era="earliest_years",
                text="I was born ...",
                anchors=["born", "montreal", ...],
            ),
            # ...two more chapters...
        ],
        bonus_probe="Anyway, that's about it for what I wanted to say today.",
        report_prefix="shatner_long_narration",
    )
    asyncio.run(run_harness(cfg))

LAW: scoring rows + report shape match the Jake harness exactly so
results across narrators are comparable on the 8-row matrix.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import websockets  # type: ignore
except ImportError:
    print(
        "Missing dependency: websockets. Try: python3 -m pip install websockets",
        file=sys.stderr,
    )
    raise

import urllib.error
import urllib.request


# ── Configuration ──────────────────────────────────────────────────────────


API_BASE = os.environ.get("HORNELORE_API_BASE", "http://localhost:8000")
WS_URL = f"{API_BASE.replace('http', 'ws')}/api/chat/ws"
INTAKE_URL = f"{API_BASE}/api/people/intake"
PING_URL = f"{API_BASE}/api/ping"

REPO_ROOT = Path("/mnt/c/Users/chris/hornelore")
API_LOG = REPO_ROOT / ".runtime" / "logs" / "api.log"
REPORTS_DIR = REPO_ROOT / "docs" / "reports"


# Forbidden empathy openers — Lori must not start her response with
# any of these (they signal therapist-bot / chatbot-empathy register
# that breaks the oral-history posture).
FORBIDDEN_OPENERS: Tuple[str, ...] = (
    "thank you for sharing",
    "that's beautiful",
    "what a beautiful",
    "what a wonderful",
    "i'm so glad",
    "i love that",
    "wow, ",
    "wow.",
    "incredible.",
    "incredible,",
)


# Era-label menu patterns — single canonical era labels firing in
# Lori's response is fine; multiple labels in one sentence ("Would
# you rather talk about your earliest years or your building years?")
# is the failure mode this guard catches.
ERA_LABEL_MENU_PATTERNS: Tuple[str, ...] = (
    "earliest years", "early school years", "adolescence",
    "coming of age", "building years", "later years",
)


# ── Data classes ───────────────────────────────────────────────────────────


@dataclass
class ChapterConfig:
    """One narrator chapter to send."""
    label: str               # human-readable, e.g. "Earliest Years"
    runtime71_era: str       # canonical era_id, e.g. "earliest_years"
    text: str                # the narrator monologue
    anchors: List[str]       # lowercase substrings Lori must reference
    word_budget: int = 110   # how long Lori's reply may be

    @property
    def key(self) -> str:
        return self.runtime71_era


@dataclass
class HarnessConfig:
    """Per-narrator harness config."""
    narrator_label: str
    intake_payload: Dict[str, Any]
    chapters: List[ChapterConfig]
    bonus_probe: str = "Anyway, that's about it for what I wanted to say today."
    report_prefix: str = "long_narration"
    # When False, harness keeps testing_only=True so we don't pollute the
    # consent_attestations table with non-consenting test rows.
    testing_only: bool = True


# ── HTTP helpers ───────────────────────────────────────────────────────────


def _http_post_json(
    url: str, body: Dict[str, Any], timeout: int = 30,
) -> Tuple[int, Any]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw)
            except (ValueError, TypeError):
                return resp.status, raw
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", errors="replace"))
        except (ValueError, TypeError):
            return e.code, None
    except (urllib.error.URLError, OSError) as e:
        return 0, str(e)


def ping_stack(timeout: int = 5) -> bool:
    try:
        with urllib.request.urlopen(PING_URL, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


# ── Step 1: intake ─────────────────────────────────────────────────────────


def create_narrator(cfg: HarnessConfig) -> Optional[str]:
    """POST /api/people/intake. Returns the new person_id or None on failure."""
    print("=" * 70)
    print(f"STEP 1 — Creating {cfg.narrator_label} via POST /api/people/intake")
    print("=" * 70)

    payload = dict(cfg.intake_payload)
    # Force testing_only if the config asks for it, so we don't
    # spuriously write consent rows for fictional personas.
    if cfg.testing_only:
        payload["testing_only"] = True
        payload["consent_recording_agreement"] = True
        payload["consent_disclosure_reviewed"] = True

    status, body = _http_post_json(INTAKE_URL, payload, timeout=30)
    if status != 200:
        print(f"  ✗ INTAKE FAILED — HTTP {status}")
        print(f"  Body: {json.dumps(body, indent=2) if isinstance(body, dict) else body}")
        return None
    if not isinstance(body, dict):
        print(f"  ✗ INTAKE returned non-dict body: {body}")
        return None
    pid = body.get("person_id") or (body.get("person") or {}).get("id")
    if not pid:
        print(f"  ✗ INTAKE returned no person_id: {json.dumps(body)[:300]}")
        return None
    print(f"  ✓ {cfg.narrator_label} created — person_id={pid}")
    print(f"  ✓ bio_facts_written: {body.get('bio_facts_written')}")
    if body.get("profile_json_error"):
        print(f"  ⚠ profile_json_error: {body['profile_json_error']}")
    print()
    return pid


# ── Step 2: WS chat helper ─────────────────────────────────────────────────


async def _send_turn_and_capture(
    ws,
    *,
    text: str,
    conv_id: str,
    person_id: str,
    speaker_name: str,
    runtime71_era: str,
    chapter_label: str,
    timeout_s: int = 240,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Send one narrator turn, stream tokens, return (final_text, events)."""

    params = {
        "person_id": person_id,
        "turn_mode": "interview",
        "session_style": "oral_history",
        "runtime71": {
            "current_pass": "pass2a",
            "current_era": runtime71_era,
            "current_mode": "open",
            "affect_state": "neutral",
            "affect_confidence": 0,
            "cognitive_mode": "open",
            "fatigue_score": 0,
            "paired": False,
            "assistant_role": "interviewer",
            "session_style_directive": (
                "Listen long. Reflect with one specific anchor. "
                "Ask one short question at most."
            ),
            "identity_complete": True,
            "identity_phase": "complete",
            "effective_pass": "pass2a",
            "speaker_name": speaker_name,
            "person_id": person_id,
            "conversation_state": "answering",
            "cognitive_support_mode": False,
        },
        "max_new_tokens": 256,
        "turn_final": True,
    }
    print(f"  --- SENDING {chapter_label} ({len(text.split())} words) ---")
    send_start = time.time()
    await ws.send(json.dumps({
        "type": "start_turn",
        "session_id": conv_id,
        "conv_id": conv_id,
        "message": text,
        "turn_mode": "interview",
        "params": params,
    }, ensure_ascii=False))

    tokens: List[str] = []
    events: List[Dict[str, Any]] = []
    final_text = ""

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=10)
        except asyncio.TimeoutError:
            continue
        try:
            msg = json.loads(raw)
        except Exception:
            continue
        events.append(msg)
        typ = msg.get("type")
        if typ == "token":
            delta = msg.get("delta") or msg.get("text") or ""
            tokens.append(delta)
            print(delta, end="", flush=True)
        elif typ == "done":
            final_text = msg.get("final_text") or "".join(tokens)
            elapsed = time.time() - send_start
            print(f"\n  --- {chapter_label} DONE in {elapsed:.1f}s ---")
            return final_text, events
        elif typ == "error":
            print(f"\n  ✗ ERROR on {chapter_label}: {json.dumps(msg)[:400]}")
            return "", events
    raise TimeoutError(f"No done event for {chapter_label} after {timeout_s}s")


# ── Step 3: scorer ────────────────────────────────────────────────────────


def score_chapter(
    chapter: ChapterConfig,
    response_text: str,
    *,
    is_bonus: bool = False,
) -> Dict[str, Any]:
    """8-row checklist scorer — matches the Jake harness shape exactly."""
    text = (response_text or "").strip()
    lower = text.lower()
    words = text.split()
    word_count = len(words)
    question_count = text.count("?")

    # 1. Reflection grounded
    anchor_hits = [a for a in chapter.anchors if a.lower() in lower]
    reflection_grounded = "PASS" if anchor_hits else "FAIL"

    # 2. One question max
    if question_count <= 1:
        one_question_max = "PASS"
    elif question_count == 2:
        one_question_max = "PARTIAL"
    else:
        one_question_max = "FAIL"

    # 3. No questionnaire interrogation
    interrogation_patterns = [
        r"\bwhat was your\b", r"\bwhen exactly\b",
        r"\bwhat year\b", r"\bwhat is your\b",
        r"\bmaiden name\b", r"\bbirth order\b",
    ]
    interrogation_hits = sum(
        1 for p in interrogation_patterns if re.search(p, lower)
    )
    no_questionnaire = (
        "FAIL" if interrogation_hits >= 2
        else "PARTIAL" if interrogation_hits == 1
        else "PASS"
    )

    # 4. No forbidden empathy
    forbidden_hits = [
        op for op in FORBIDDEN_OPENERS
        if lower.startswith(op) or f". {op}" in lower
    ]
    no_forbidden_empathy = "FAIL" if forbidden_hits else "PASS"

    # 5. No era-label menu
    era_menu_hits = [p for p in ERA_LABEL_MENU_PATTERNS if p in lower]
    era_label_count = len(era_menu_hits)
    no_era_label_menu = "FAIL" if era_label_count >= 2 else "PASS"

    # 6. Same-anchor loop — meta, populated by caller
    no_same_anchor_loop = "PENDING"

    # 7. Word budget honored
    if word_count <= chapter.word_budget:
        word_budget_honored = "PASS"
    elif word_count <= chapter.word_budget + 20:
        word_budget_honored = "PARTIAL"
    else:
        word_budget_honored = "FAIL"

    # 8. Translation / refusal absent
    refusal_patterns = [
        "let me say that in english", "i cannot answer", "i can't answer",
        "i'm not able to", "i am not able to",
    ]
    refusal_hit = any(p in lower for p in refusal_patterns)
    translation_refusal_absent = (
        "FAIL" if (not text or refusal_hit) else "PASS"
    )

    return {
        "label": chapter.label,
        "chapter_key": chapter.key,
        "word_count": word_count,
        "question_count": question_count,
        "anchor_hits": anchor_hits,
        "rows": {
            "reflection_grounded": reflection_grounded,
            "one_question_max": one_question_max,
            "no_questionnaire_interrogation": no_questionnaire,
            "no_forbidden_empathy_openers": no_forbidden_empathy,
            "no_era_label_menu": no_era_label_menu,
            "no_same_anchor_loop": no_same_anchor_loop,
            "word_budget_honored": word_budget_honored,
            "translation_refusal_absent": translation_refusal_absent,
        },
        "forbidden_openers_hit": forbidden_hits,
        "interrogation_hits": interrogation_hits,
        "era_label_hits": era_menu_hits,
        "is_bonus": is_bonus,
    }


def cross_chapter_anchor_loop_check(scores: List[Dict[str, Any]]) -> None:
    """Detect shared anchors across chapters — mutates in place."""
    for i, s in enumerate(scores):
        if s["is_bonus"]:
            s["rows"]["no_same_anchor_loop"] = "PASS"
            continue
        loop_hits: List[str] = []
        for j, other in enumerate(scores):
            if i == j or other["is_bonus"]:
                continue
            shared = set(s["anchor_hits"]) & set(other["anchor_hits"])
            if shared:
                loop_hits.extend(shared)
        if loop_hits:
            s["rows"]["no_same_anchor_loop"] = "FAIL"
            s["repeated_anchors"] = sorted(set(loop_hits))
        else:
            s["rows"]["no_same_anchor_loop"] = "PASS"


# ── Step 4: log greps ─────────────────────────────────────────────────────


def log_grep_summary() -> Dict[str, Any]:
    if not API_LOG.exists():
        return {"error": f"api.log not found at {API_LOG}"}
    try:
        text = API_LOG.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"error": f"Cannot read api.log: {e}"}

    return {
        "oral_history_style_lines": len(re.findall(
            r"composer.*style[= ]oral_history", text, flags=re.IGNORECASE,
        )),
        "reflection_not_grounded_lines": len(re.findall(
            r"reflection_not_grounded|question_layer_ineligible", text,
        )),
        "extract_accepted_lines": len(re.findall(r"extract.*accepted=", text)),
        "spantag_flag_on_lines_observed": "[extract][spantag] flag ON" in text,
    }


# ── Step 5: report writer ────────────────────────────────────────────────


def write_report(
    cfg: HarnessConfig,
    conv_id: str,
    person_id: str,
    chapter_results: List[Tuple[ChapterConfig, str, Dict[str, Any]]],
    bonus_result: Optional[Tuple[str, Dict[str, Any]]],
    log_summary: Dict[str, Any],
) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{cfg.report_prefix}_{conv_id}.txt"
    lines: List[str] = []
    lines.append("=" * 80)
    lines.append(f"{cfg.narrator_label.upper()} — LONG-NARRATION HARNESS REPORT")
    lines.append("=" * 80)
    lines.append(f"conv_id:    {conv_id}")
    lines.append(f"person_id:  {person_id}")
    lines.append(f"run_time:   {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    overall_pass = 0
    overall_total = 0
    for chapter, response_text, score in chapter_results:
        lines.append("─" * 80)
        lines.append(f"CHAPTER — {chapter.label}")
        lines.append("─" * 80)
        lines.append(f"  word_count:     {score['word_count']}")
        lines.append(f"  question_count: {score['question_count']}")
        lines.append(f"  anchor_hits:    {', '.join(score['anchor_hits']) or '(none)'}")
        lines.append("")
        lines.append("  Lori response (verbatim):")
        lines.append("  ┌" + "─" * 76)
        for ln in (response_text or "(no response)").splitlines() or [response_text or ""]:
            lines.append(f"  │ {ln}")
        lines.append("  └" + "─" * 76)
        lines.append("")
        lines.append("  Scoring matrix:")
        for row_name, row_val in score["rows"].items():
            mark = ("✓" if row_val == "PASS" else
                    "⚠" if row_val == "PARTIAL" else
                    "✗" if row_val == "FAIL" else "·")
            lines.append(f"    {mark} {row_name}: {row_val}")
            overall_total += 1
            if row_val == "PASS":
                overall_pass += 1
        lines.append("")
    if bonus_result is not None:
        text, bs = bonus_result
        lines.append("─" * 80)
        lines.append("BONUS PROBE — closing marker")
        lines.append("─" * 80)
        lines.append(f"  Probe sent: {cfg.bonus_probe}")
        lines.append("")
        lines.append("  Lori response:")
        lines.append("  ┌" + "─" * 76)
        for ln in (text or "(no response)").splitlines() or [text or ""]:
            lines.append(f"  │ {ln}")
        lines.append("  └" + "─" * 76)
        lines.append("")
    lines.append("─" * 80)
    lines.append("BACKEND LOG GREP SUMMARY")
    lines.append("─" * 80)
    for k, v in log_summary.items():
        lines.append(f"  {k}: {v}")
    lines.append("")
    lines.append("─" * 80)
    lines.append(f"OVERALL: {overall_pass}/{overall_total} rows PASS")
    lines.append("─" * 80)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written: {report_path}")
    return report_path


# ── Public entry point ───────────────────────────────────────────────────


async def run_harness(cfg: HarnessConfig) -> int:
    """Top-level entry. Returns 0 on success, non-zero on failure."""
    if not ping_stack():
        print(f"✗ Stack not reachable at {PING_URL} — start the API first.",
              file=sys.stderr)
        return 1

    pid = create_narrator(cfg)
    if not pid:
        return 1

    conv_id = str(uuid.uuid4())[:12]
    speaker_name = cfg.intake_payload.get("preferred_name") or "the narrator"

    print(f"\nOpening chat WS: {WS_URL}  conv_id={conv_id}\n")
    chapter_results: List[Tuple[ChapterConfig, str, Dict[str, Any]]] = []
    bonus_result: Optional[Tuple[str, Dict[str, Any]]] = None
    async with websockets.connect(WS_URL, max_size=1 << 22) as ws:
        for ch in cfg.chapters:
            text, _events = await _send_turn_and_capture(
                ws,
                text=ch.text,
                conv_id=conv_id,
                person_id=pid,
                speaker_name=speaker_name,
                runtime71_era=ch.runtime71_era,
                chapter_label=ch.label,
            )
            score = score_chapter(ch, text)
            chapter_results.append((ch, text, score))
            print()
        # Bonus probe — fixed bonus era ("today") since it's the closing marker
        if cfg.bonus_probe:
            text, _events = await _send_turn_and_capture(
                ws,
                text=cfg.bonus_probe,
                conv_id=conv_id,
                person_id=pid,
                speaker_name=speaker_name,
                runtime71_era="today",
                chapter_label="Bonus probe",
            )
            # Fake chapter-config for scoring shape
            fake_bonus_ch = ChapterConfig(
                label="Bonus probe", runtime71_era="today",
                text=cfg.bonus_probe, anchors=[], word_budget=60,
            )
            bonus_score = score_chapter(fake_bonus_ch, text, is_bonus=True)
            chapter_results.append((fake_bonus_ch, text, bonus_score))
            bonus_result = (text, bonus_score)

    # Cross-chapter anchor-loop pass
    cross_chapter_anchor_loop_check([s for (_c, _t, s) in chapter_results])

    log_summary = log_grep_summary()
    write_report(cfg, conv_id, pid, chapter_results[:len(cfg.chapters)],
                 bonus_result, log_summary)
    return 0
