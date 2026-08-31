"""One turn-level trace across Lori's whole response and retention path.

WO-LORI-LISTEN-AND-RETAIN-01, Phase 1/2. OBSERVATION ONLY.

── WHY THIS EXISTS ───────────────────────────────────────────────────

Nine layers rewrite Lori's output after generation. Every one of them
logs that it fired; none of them logs what the model actually wrote,
and no two of them share an identifier. So the only way to ask "did
comm_control shorten this turn, and is that why the validator then
called it too_short" was to correlate log lines by `conv=` — and a
conversation has many turns, so that correlation cannot prove a
turn-level claim. The 58/77 cascade figure in the WO is explicitly
PROVISIONAL for exactly this reason.

This module closes that gap: one `trace_id` per turn, carried from the
raw model output through every transformation, the delivered text, the
persisted row, extraction, placement, and memoir-source retrieval.

── THE TWO RULES ─────────────────────────────────────────────────────

1. **It must never change what the narrator receives.** Every public
   function returns None, mutates nothing it is given, and swallows its
   own exceptions. A trace failure must never surface as a turn
   failure. `tests/test_lori_response_trace.py` asserts delivered text
   is byte-identical with the trace on and off.

2. **A failed measurement is never an absent value.** See
   `RESULT_*` below — `measurement_failed` exists so a wrong-origin 404
   can never be reported as "the memoir data is missing". The
   /api/memoir/canonical request currently goes to the static server on
   :8082, which knows nothing about that route; the correct source has
   never been queried at all.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── storage-result vocabulary (shared with the harness report) ────────
#: The correct source was queried and the value is genuinely there.
RESULT_PERSISTED = "persisted"
#: The system saw the value and declined it. Reason required.
RESULT_REJECTED = "rejected"
#: The correct source WAS successfully queried; the value is not there.
RESULT_MEASURED_ABSENT = "measured_absent"
#: The query itself failed — wrong origin, error, timeout, gated route.
#: NOT evidence of absence.
RESULT_MEASUREMENT_FAILED = "measurement_failed"
#: No instrumentation exists for this stage yet.
RESULT_NOT_MEASURED = "not_measured"

RESULTS = (RESULT_PERSISTED, RESULT_REJECTED, RESULT_MEASURED_ABSENT,
           RESULT_MEASUREMENT_FAILED, RESULT_NOT_MEASURED)

_ENV_FLAG = "HORNELORE_RESPONSE_TRACE"
_current: ContextVar[Optional[str]] = ContextVar("lori_trace_id", default=None)
_lock = threading.Lock()
_traces: Dict[str, Dict[str, Any]] = {}
_MAX_LIVE = 64


def enabled() -> bool:
    """Default ON. Set HORNELORE_RESPONSE_TRACE=0 to disable entirely."""
    return os.environ.get(_ENV_FLAG, "1").strip().lower() not in (
        "0", "false", "no", "off")


def _out_dir() -> Path:
    root = os.environ.get("HORNELORE_TRACE_DIR")
    if root:
        return Path(root)
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".runtime").is_dir():
            return parent / ".runtime" / "eval" / "response-trace"
    return Path(".runtime/eval/response-trace")


def _words(text: Optional[str]) -> int:
    return len((text or "").split())


def _questions(text: Optional[str]) -> int:
    return (text or "").count("?")


def current() -> Optional[str]:
    try:
        return _current.get()
    except Exception:
        return None


def begin(narrator_id: str = "", conversation_id: str = "",
          turn_key: str = "", **extra: Any) -> Optional[str]:
    """Open a trace for one turn. Returns the trace_id, or None."""
    if not enabled():
        return None
    try:
        trace_id = uuid.uuid4().hex
        rec: Dict[str, Any] = {
            "trace_id": trace_id,
            "narrator_id": narrator_id or "",
            "conversation_id": conversation_id or "",
            "turn_key": turn_key or "",
            "started_at": time.time(),
            "context": dict(extra) if extra else {},
            "stages": [],
            "storage": {},
            "raw_captured": False,
        }
        with _lock:
            if len(_traces) >= _MAX_LIVE:
                for k in sorted(_traces,
                                key=lambda x: _traces[x].get("started_at", 0)
                                )[:len(_traces) - _MAX_LIVE + 1]:
                    _traces.pop(k, None)
            _traces[trace_id] = rec
        _current.set(trace_id)
        return trace_id
    except Exception:
        return None


def note(key: str, value: Any, trace_id: Optional[str] = None) -> None:
    """Attach runtime context: era, pass, mode, kept_turns, turn ids."""
    try:
        tid = trace_id or current()
        if not tid:
            return
        with _lock:
            rec = _traces.get(tid)
            if rec is not None:
                rec["context"][str(key)] = value
    except Exception:
        return


def raw(text: Optional[str], trace_id: Optional[str] = None) -> None:
    """The model's output, BEFORE the first transformation.

    This is the capture the pipeline has never had. Recorded once per
    turn; a second call is ignored so a retry cannot overwrite it.
    """
    try:
        tid = trace_id or current()
        if not tid:
            return
        with _lock:
            rec = _traces.get(tid)
            if rec is None or rec.get("raw_captured"):
                return
            rec["raw_text"] = text or ""
            rec["raw_words"] = _words(text)
            rec["raw_questions"] = _questions(text)
            rec["raw_captured"] = True
    except Exception:
        return


def stage(name: str, *, fired: bool, before: Optional[str] = None,
          after: Optional[str] = None, reason: Any = None,
          trace_id: Optional[str] = None, **extra: Any) -> None:
    """Record one transformation in execution order.

    `before`/`after` are the exact strings. `fired=False` still records
    the stage — a layer that ran and declined to change anything is
    evidence, and its absence from the trace would be indistinguishable
    from the layer not existing.
    """
    try:
        tid = trace_id or current()
        if not tid:
            return
        b, a = (before or ""), (after if after is not None else before) or ""
        entry: Dict[str, Any] = {
            "stage": str(name),
            "fired": bool(fired),
            "reason": reason if reason is None or isinstance(
                reason, (str, int, float, list, dict)) else str(reason),
            "before": b,
            "after": a,
            "words_before": _words(b),
            "words_after": _words(a),
            "questions_before": _questions(b),
            "questions_after": _questions(a),
            "changed": (b != a),
        }
        entry["words_delta"] = entry["words_after"] - entry["words_before"]
        if extra:
            entry["extra"] = {k: v for k, v in extra.items()}
        with _lock:
            rec = _traces.get(tid)
            if rec is None:
                return
            entry["index"] = len(rec["stages"])
            rec["stages"].append(entry)
    except Exception:
        return


def storage(stage_name: str, result: str, *, detail: Any = None,
            trace_id: Optional[str] = None) -> None:
    """Record one retention-path result.

    `result` MUST be one of RESULTS. An unknown value is coerced to
    `not_measured` rather than silently trusted — a typo must never
    read as a pass.
    """
    try:
        tid = trace_id or current()
        if not tid:
            return
        r = result if result in RESULTS else RESULT_NOT_MEASURED
        with _lock:
            rec = _traces.get(tid)
            if rec is None:
                return
            rec["storage"][str(stage_name)] = {
                "result": r,
                "coerced_from": None if r == result else result,
                "detail": detail,
            }
    except Exception:
        return


def finish(delivered: Optional[str] = None,
           persisted: Optional[str] = None,
           trace_id: Optional[str] = None) -> None:
    """Close the trace and append it to today's JSONL artifact."""
    try:
        tid = trace_id or current()
        if not tid:
            return
        with _lock:
            rec = _traces.pop(tid, None)
        if rec is None:
            return
        if delivered is not None:
            rec["delivered_text"] = delivered
            rec["delivered_words"] = _words(delivered)
            rec["delivered_questions"] = _questions(delivered)
        if persisted is not None:
            rec["persisted_text"] = persisted
            rec["delivered_equals_persisted"] = (
                (delivered or "") == (persisted or ""))
        rec["ended_at"] = time.time()
        raw_t = rec.get("raw_text")
        if raw_t is not None and delivered is not None:
            rec["raw_equals_delivered"] = (raw_t == delivered)
            rec["net_words_removed"] = _words(raw_t) - _words(delivered)
        d = _out_dir()
        d.mkdir(parents=True, exist_ok=True)
        day = time.strftime("%Y-%m-%d", time.gmtime(rec["started_at"]))
        with (d / f"{day}.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        try:
            _current.set(None)
        except Exception:
            pass
    except Exception:
        return


def load_day(day: Optional[str] = None) -> List[Dict[str, Any]]:
    """Read a day's traces. For the harness report and for tests."""
    try:
        day = day or time.strftime("%Y-%m-%d", time.gmtime())
        path = _out_dir() / f"{day}.jsonl"
        if not path.is_file():
            return []
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
        return out
    except Exception:
        return []
