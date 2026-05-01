"""WO-LORI-HARNESS-01 — Golfball style-diff extension.

Companion module to scripts/archive/run_golfball_interview_eval.py.
Provides the style-diff probe block that answers the load-bearing
question: are session_style modes BEHAVIORALLY wired or just UI labels?

Hits POST /api/operator/harness/interview-turn (gated by
HORNELORE_OPERATOR_HARNESS=1) with the same prompt under all four
styles, measures word count / question count / scene markers / direct
markers / questionnaire markers / agenda markers, then asserts
cross-style differentiation.

Pass/fail contract:
  1. Every style must keep one-question law (turn-level).
  2. Clear & Direct must be shorter than Warm Storytelling.
  3. Warm Storytelling must contain more scene/emotion language.
  4. Questionnaire First must ask structured/basic-info-style questions.
  5. Companion must avoid extraction/interview-agenda language.
  6. If Clear & Direct and Warm Storytelling are too similar — FAIL
     as likely eyecandy / unwired mode.

Thresholds (in `THRESHOLDS` dict) are first-pass guesses. After a clean
calibration run, tune them based on the recorded `cross_style_metrics`
in the report. They are intentionally STRICT so unwired modes surface
loudly. If LLM stochasticity blows them on a clean run, that itself is
a signal that the prompt-side differentiation is too thin.
"""
from __future__ import annotations

import dataclasses
import re
import time
from typing import Any, Dict, List, Optional

import requests


# ── Markers / regexes ──────────────────────────────────────────────────────

SCENE_RE = re.compile(
    r"\b(remember|memory|place|room|kitchen|house|home|street|school|"
    r"who was there|what did it look like|what stands out|scene|"
    r"sounds|smell|felt like|feel|feeling|details|moment)\b",
    re.IGNORECASE,
)
DIRECT_RE = re.compile(
    r"\b(one thing|one detail|one fact|just|first|start with|short|"
    r"specific|name|date|place)\b",
    re.IGNORECASE,
)
QUESTIONNAIRE_RE = re.compile(
    r"\b(full name|preferred name|born|birth|date of birth|"
    r"place of birth|birth order|parents|siblings|"
    r"where were you born|when were you born)\b",
    re.IGNORECASE,
)
AGENDA_RE = re.compile(
    r"\b(questionnaire|field|date of birth|place of birth|birth order|"
    r"let's fill|next section|structured basics|extraction|archive)\b",
    re.IGNORECASE,
)
COMPOUND_QUESTION_RE = re.compile(
    r"\?\s*(?:and|also|what|where|when|who|why|how|did|do|were|was|"
    r"can|could)\b|"
    r"\b(and|also)\b[^.?!]{0,120}\?",
    re.IGNORECASE,
)


# ── Probe definitions ──────────────────────────────────────────────────────

@dataclasses.dataclass
class StyleProbe:
    style: str
    text: str
    expected_max_questions: int = 1
    max_words: Optional[int] = None
    min_words: Optional[int] = None
    require_scene_score_at_least: Optional[int] = None
    require_direct_score_at_least: Optional[int] = None
    require_questionnaire_score_at_least: Optional[int] = None
    forbid_agenda_language: bool = False


# Single shared prompt across all styles. Keeps the comparison clean.
STYLE_DIFF_PROMPT = (
    "I remember being young in Spokane. My dad worked nights at the "
    "aluminum plant, and I can still picture the house and the quiet "
    "mornings."
)

STYLE_PROBES: List[StyleProbe] = [
    StyleProbe(
        style="questionnaire_first",
        text=STYLE_DIFF_PROMPT,
        max_words=85,
        require_questionnaire_score_at_least=1,
    ),
    StyleProbe(
        style="clear_direct",
        text=STYLE_DIFF_PROMPT,
        max_words=55,
        require_direct_score_at_least=1,
    ),
    StyleProbe(
        style="warm_storytelling",
        text=STYLE_DIFF_PROMPT,
        min_words=35,
        require_scene_score_at_least=2,
    ),
    StyleProbe(
        style="companion",
        text=STYLE_DIFF_PROMPT,
        max_words=70,
        forbid_agenda_language=True,
    ),
]

THRESHOLDS = {
    "max_questions_per_turn": 1,
    "clear_direct_max_words": 55,
    "warm_storytelling_min_words": 35,
    "clear_vs_warm_similarity_must_be_below": 0.72,
    "clear_vs_warm_word_delta_min": 12,
    "warm_scene_score_must_exceed_clear_by_at_least": 1,
    "companion_agenda_score_must_equal": 0,
}


# ── Helpers ────────────────────────────────────────────────────────────────

def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))


def _question_count(text: str) -> int:
    return (text or "").count("?")


def _score(regex: re.Pattern[str], text: str) -> int:
    return len(regex.findall(text or ""))


def _similarity(a: str, b: str) -> float:
    """Token Jaccard similarity. Catches eyecandy / no-op styles."""
    ta = set(re.findall(r"\b[a-z]{3,}\b", (a or "").lower()))
    tb = set(re.findall(r"\b[a-z]{3,}\b", (b or "").lower()))
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(1, len(ta | tb))


def call_harness_turn(
    *,
    api: str,
    person_id: str,
    text: str,
    session_style: str,
    session_id: str,
    timeout_seconds: int = 120,
) -> Dict[str, Any]:
    """POST one turn to /api/operator/harness/interview-turn."""
    payload = {
        "person_id": person_id,
        "text": text,
        "session_style": session_style,
        "turn_mode": "interview",
        "session_id": session_id,
        "timeout_seconds": timeout_seconds,
    }
    try:
        r = requests.post(
            api.rstrip("/") + "/api/operator/harness/interview-turn",
            json=payload,
            timeout=timeout_seconds + 15,
        )
    except Exception as exc:
        return {
            "ok": False,
            "http_status": -1,
            "http_ok": False,
            "assistant_text": "",
            "errors": [f"http_error: {exc!r}"],
        }
    try:
        data = r.json()
    except Exception:
        data = {"ok": False, "assistant_text": "",
                "errors": [r.text[:500]]}
    data["http_status"] = r.status_code
    data["http_ok"] = r.ok
    return data


# ── Main entry point ───────────────────────────────────────────────────────

def run_style_diff_block(
    *,
    api: str,
    person_id: str,
    session_id_prefix: str = "style-diff",
    delay_seconds: float = 3.0,
    turn_timeout_seconds: int = 120,
) -> Dict[str, Any]:
    """Run all four style probes and return a report block.

    Returns a dict with shape:
      {
        "ok": bool,
        "purpose": "...",
        "prompt_used_for_all_styles": "...",
        "results": [<per-style result dict>, ...],
        "cross_style_metrics": {...},
        "cross_style_failures": [...],
        "thresholds": {...},
      }
    """
    results: List[Dict[str, Any]] = []
    by_style: Dict[str, Dict[str, Any]] = {}

    for probe in STYLE_PROBES:
        session_id = f"{session_id_prefix}-{probe.style}-{int(time.time())}"
        data = call_harness_turn(
            api=api,
            person_id=person_id,
            text=probe.text,
            session_style=probe.style,
            session_id=session_id,
            timeout_seconds=turn_timeout_seconds,
        )
        assistant_text = data.get("assistant_text", "") or ""
        metrics = {
            "word_count": _word_count(assistant_text),
            "question_count": _question_count(assistant_text),
            "compound_question": bool(
                COMPOUND_QUESTION_RE.search(assistant_text)
            ),
            "scene_score": _score(SCENE_RE, assistant_text),
            "direct_score": _score(DIRECT_RE, assistant_text),
            "questionnaire_score": _score(QUESTIONNAIRE_RE, assistant_text),
            "agenda_score": _score(AGENDA_RE, assistant_text),
        }
        failures: List[str] = []

        # ── Endpoint health checks ────────────────────────────────────────
        if not data.get("http_ok"):
            failures.append(f"http_status={data.get('http_status')}")
        if not data.get("ok"):
            failures.append("endpoint_ok_false")
        if data.get("db_locked") or data.get("lock_event_delta", 0) > 0:
            failures.append("db_lock_during_style_probe")
        # Empty assistant_text would make every downstream metric trivially
        # "pass" (sim=0, low word_count, zero scene_score). Catch it
        # per-style so a silent LLM failure doesn't masquerade as a clean
        # style separation.
        if not assistant_text.strip():
            failures.append("empty_assistant_text")

        # ── Discipline (per-style) ────────────────────────────────────────
        if metrics["question_count"] > probe.expected_max_questions:
            failures.append(
                f"too_many_questions={metrics['question_count']}"
            )
        if metrics["compound_question"]:
            failures.append("compound_question")

        if probe.max_words is not None \
                and metrics["word_count"] > probe.max_words:
            failures.append(
                f"too_long={metrics['word_count']}>{probe.max_words}"
            )
        if probe.min_words is not None \
                and metrics["word_count"] < probe.min_words:
            failures.append(
                f"too_short={metrics['word_count']}<{probe.min_words}"
            )
        if probe.require_scene_score_at_least is not None \
                and metrics["scene_score"] < probe.require_scene_score_at_least:
            failures.append(
                f"scene_score_low={metrics['scene_score']}<"
                f"{probe.require_scene_score_at_least}"
            )
        if probe.require_direct_score_at_least is not None \
                and metrics["direct_score"] < probe.require_direct_score_at_least:
            failures.append(
                f"direct_score_low={metrics['direct_score']}<"
                f"{probe.require_direct_score_at_least}"
            )
        if probe.require_questionnaire_score_at_least is not None \
                and metrics["questionnaire_score"] < probe.require_questionnaire_score_at_least:
            failures.append(
                f"questionnaire_score_low={metrics['questionnaire_score']}<"
                f"{probe.require_questionnaire_score_at_least}"
            )
        if probe.forbid_agenda_language and metrics["agenda_score"] > 0:
            failures.append(
                f"companion_has_agenda_language={metrics['agenda_score']}"
            )

        row = {
            "style": probe.style,
            "prompt": probe.text,
            "assistant_text": assistant_text,
            "metrics": metrics,
            "endpoint": {
                "ok": data.get("ok"),
                "http_status": data.get("http_status"),
                "elapsed_ms": data.get("elapsed_ms"),
                "story_candidate_delta": data.get("story_candidate_delta"),
                "safety_event_delta": data.get("safety_event_delta"),
                "lock_event_delta": data.get("lock_event_delta"),
                "errors": data.get("errors", []),
            },
            "passed": not failures,
            "failures": failures,
        }
        results.append(row)
        by_style[probe.style] = row
        time.sleep(delay_seconds)

    # ── Cross-style assertions: settle the eyecandy question ──────────────
    cross_failures: List[str] = []
    clear = by_style.get("clear_direct", {})
    warm = by_style.get("warm_storytelling", {})
    companion = by_style.get("companion", {})
    questionnaire = by_style.get("questionnaire_first", {})

    clear_text = clear.get("assistant_text", "") or ""
    warm_text = warm.get("assistant_text", "") or ""
    clear_m = clear.get("metrics", {})
    warm_m = warm.get("metrics", {})

    sim = _similarity(clear_text, warm_text) if clear_text and warm_text else 0.0
    word_delta = abs(
        int(warm_m.get("word_count", 0)) - int(clear_m.get("word_count", 0))
    )
    scene_delta = (
        int(warm_m.get("scene_score", 0)) - int(clear_m.get("scene_score", 0))
    )

    # Cross-style assertions only have meaning when BOTH responses are
    # non-empty. If either is empty, the style-diff lane is inconclusive,
    # not passing — flag it explicitly so the report doesn't claim a
    # clean differentiation that was actually a silent LLM failure.
    if not clear_text.strip() or not warm_text.strip():
        cross_failures.append(
            "cross_style_inconclusive_empty_response"
            f"_clear={'empty' if not clear_text.strip() else 'present'}"
            f"_warm={'empty' if not warm_text.strip() else 'present'}"
        )
    else:
        if sim >= THRESHOLDS["clear_vs_warm_similarity_must_be_below"]:
            cross_failures.append(
                f"clear_direct_and_warm_storytelling_too_similar={sim:.2f}"
            )
        if word_delta < THRESHOLDS["clear_vs_warm_word_delta_min"]:
            cross_failures.append(
                f"style_word_delta_too_small={word_delta}<"
                f"{THRESHOLDS['clear_vs_warm_word_delta_min']}"
            )
        if scene_delta < THRESHOLDS["warm_scene_score_must_exceed_clear_by_at_least"]:
            cross_failures.append(
                f"warm_scene_score_not_higher_than_clear={scene_delta}"
            )
        # Clear & Direct should be shorter or equal to Warm.
        if int(clear_m.get("word_count", 999)) > int(warm_m.get("word_count", 0)):
            cross_failures.append("clear_direct_longer_than_warm_storytelling")

    # Companion shouldn't be more questionnaire-like than Questionnaire First.
    comp_q = int(companion.get("metrics", {}).get("questionnaire_score", 0))
    qf_q = int(questionnaire.get("metrics", {}).get("questionnaire_score", 0))
    if comp_q > qf_q:
        cross_failures.append(
            "companion_more_questionnaire_like_than_questionnaire_first"
        )

    return {
        "ok": all(r["passed"] for r in results) and not cross_failures,
        "purpose": (
            "Detect whether session_style changes Lori behavior or is "
            "only UI state. If clear_direct vs warm_storytelling fall "
            "below the differentiation thresholds, modes are likely "
            "eyecandy / prompt-composer not yet wired to session_style."
        ),
        "prompt_used_for_all_styles": STYLE_DIFF_PROMPT,
        "results": results,
        "cross_style_metrics": {
            "clear_vs_warm_similarity": sim,
            "clear_vs_warm_word_delta": word_delta,
            "warm_minus_clear_scene_score": scene_delta,
        },
        "cross_style_failures": cross_failures,
        "thresholds": THRESHOLDS,
    }


__all__ = [
    "STYLE_DIFF_PROMPT",
    "STYLE_PROBES",
    "THRESHOLDS",
    "call_harness_turn",
    "run_style_diff_block",
]


if __name__ == "__main__":
    print(
        "This module is the style-diff extension for the golfball "
        "harness. Import run_style_diff_block from "
        "run_golfball_interview_eval.py."
    )
