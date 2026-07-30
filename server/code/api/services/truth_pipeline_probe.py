"""TRUTH-PIPELINE-01 Phase 1 (Gate 7) — per-turn truth-write observability.

=======================================================================
  LAW: this module is OBSERVABILITY ONLY.

    - It records WHICH truth-write stages fired during one turn.
    - It changes NO behavior. It routes nothing. It fixes nothing.
    - It writes NO database row and adds NO table or column.
    - It never reaches the narrator surface (CLAUDE.md:44, "no
      operator leakage / no diagnostic surfaces").
    - Every entry point swallows its own exceptions. A probe failure
      must never break a turn.

  Default OFF behind HORNELORE_TRUTH_PIPELINE_LOG=1.
=======================================================================

WHY THIS EXISTS
---------------
The operator harness reports `speaker_zero_delta` on interview turns:
"turn did not write anywhere". Three explanations were live, and the
record could not choose between them:

  (a) a real routing bug — the turn genuinely writes no truth,
  (b) a harness coverage gap — the turn writes, but the probe that
      measures it is looking at the wrong tables,
  (c) correct-by-design — synthetic `harness-test-<uuid>` narrators
      are not supposed to reach the family-truth pipeline at all
      (README:380).

None of the five truth-write stages was observable per turn, so all
three produced the same reading. This module makes them observable.

Phase 1 stops here on purpose. README:637 — "Phase 2/3 routing fixes
deferred until Phase 1 evidence lands." A stage that reports 0 here is
EVIDENCE, not a defect to patch in this phase.

READING A ZERO
--------------
A zero means "this stage did not fire inside this turn's server task".
It does not by itself mean "broken". Two of the five stages are known
today to be driven from the browser, not the server turn:

  - `extract_fields_called`   — `ui/js/interview.js` posts to
    /api/extract-fields; the chat_ws turn path never calls it.
  - `family_truth_written`    — `ui/js/app.js` posts the note and the
    proposal after the assistant reply lands.

Those calls arrive as SEPARATE HTTP requests with no active turn
context, so they legitimately mark nothing on the turn that provoked
them. Phase 1 records that fact rather than hiding it: the stage is
instrumented (`instrumented` is True for all five), so 0 distinguishes
"did not fire here" from "was never measured".

CORRELATION
-----------
There is no single identifier spanning all five stages in the schema —
`turns` carries no `turn_id` column, and adding one is a schema change
Phase 1 is not allowed to make. Instead the probe binds a record to the
running turn with a `contextvars.ContextVar`, so no writer signature
changes and no id has to be threaded through the nine
`persist_turn_transaction` call sites. Writers call `mark(...)`; when
no turn is active, or the flag is off, `mark(...)` returns immediately.

Completed records go to a small in-memory ring buffer (precedent:
services/stack_monitor.py) so the operator harness can read the summary
for the turn it just ran, keyed by the `turn_id` it already supplies.
Nothing is persisted; the buffer dies with the process.

ISOLATION
---------
This module imports only the standard library and `api.flags`. That is
enforced mechanically by tests/test_truth_pipeline_probe_isolation.py.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional

import contextvars

from ..flags import truth_pipeline_log_enabled

# ── The five stages ───────────────────────────────────────────────────────
# Names are fixed by MASTER_WORK_ORDER_CHECKLIST.md item 3. Do not rename
# them without moving the checklist and the doctrine forward first.
STAGES: tuple[str, ...] = (
    "raw_turn_saved",
    "archive_event_created",
    "extract_fields_called",
    "family_truth_written",
    "projection_updated",
)

_RING_MAX = 64

_ring: Deque[Dict[str, Any]] = deque(maxlen=_RING_MAX)
_ring_lock = threading.Lock()

_active: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar(
    "hornelore_truth_pipeline_probe", default=None,
)


def enabled() -> bool:
    """True when HORNELORE_TRUTH_PIPELINE_LOG is on. Default OFF."""
    return truth_pipeline_log_enabled()


def begin_turn(
    *,
    conv_id: str = "",
    person_id: str = "",
    turn_id: str = "",
    turn_mode: str = "",
) -> Optional[contextvars.Token]:
    """Open a probe for the turn running in this context.

    Returns a token to hand back to end_turn(), or None when the flag
    is off. A None return is the normal disabled path, not an error.
    """
    if not enabled():
        return None
    record: Dict[str, Any] = {
        "conv_id": str(conv_id or ""),
        "person_id": str(person_id or ""),
        "turn_id": str(turn_id or ""),
        "turn_mode": str(turn_mode or ""),
        "started_monotonic": time.monotonic(),
        "counts": {stage: 0 for stage in STAGES},
        "first_detail": {},
    }
    return _active.set(record)


def mark(stage: str, detail: str = "") -> None:
    """Record that `stage` fired in the turn active in this context.

    No-op when the flag is off, when no turn is active (for example a
    browser-driven HTTP request that arrives outside the turn task), or
    when `stage` is not one of the five. Never raises.
    """
    try:
        if stage not in STAGES:
            return
        record = _active.get()
        if record is None:
            return
        record["counts"][stage] = int(record["counts"].get(stage, 0)) + 1
        if detail and stage not in record["first_detail"]:
            # Short, non-narrator detail only — a table name, a row kind.
            record["first_detail"][stage] = str(detail)[:60]
    except Exception:
        return


def end_turn(token: Optional[contextvars.Token]) -> Optional[Dict[str, Any]]:
    """Close the probe, file the summary in the ring, and return it.

    Returns None when there was nothing to close. Never raises.
    """
    if token is None:
        return None
    try:
        record = _active.get()
        _active.reset(token)
    except Exception:
        return None
    if not record:
        return None
    try:
        summary = summarize(record)
    except Exception:
        return None
    try:
        with _ring_lock:
            _ring.append(summary)
    except Exception:
        pass
    return summary


def summarize(record: Dict[str, Any]) -> Dict[str, Any]:
    """Turn an open record into the flat, serialisable summary shape."""
    counts = {stage: int(record.get("counts", {}).get(stage, 0)) for stage in STAGES}
    fired = [stage for stage in STAGES if counts[stage] > 0]
    started = record.get("started_monotonic")
    elapsed_ms = None
    if isinstance(started, (int, float)):
        elapsed_ms = int((time.monotonic() - started) * 1000)
    return {
        "conv_id": record.get("conv_id", ""),
        "person_id": record.get("person_id", ""),
        "turn_id": record.get("turn_id", ""),
        "turn_mode": record.get("turn_mode", ""),
        "counts": counts,
        "stages_fired": fired,
        "stages_fired_count": len(fired),
        "stages_total": len(STAGES),
        # Every stage has a mark() call site in the tree, so a 0 means
        # "did not fire in this turn", never "was not measured".
        "instrumented": {stage: True for stage in STAGES},
        "elapsed_ms": elapsed_ms,
    }


def log_line(summary: Dict[str, Any]) -> str:
    """One compact line per turn.

    log_filter.py records that api.log had become roughly 95 percent
    polling noise, so this emits ONE line for the whole turn rather than
    one per stage. Carries ids and counts only — never narrator text.
    """
    counts = summary.get("counts", {}) or {}
    parts = [
        "[truth-pipeline]",
        "turn_id=%s" % (summary.get("turn_id") or "-"),
        "conv=%s" % (summary.get("conv_id") or "-"),
        "person=%s" % (summary.get("person_id") or "-"),
        "mode=%s" % (summary.get("turn_mode") or "-"),
    ]
    for stage in STAGES:
        parts.append("%s=%d" % (stage, int(counts.get(stage, 0))))
    parts.append("fired=%d/%d" % (
        int(summary.get("stages_fired_count") or 0),
        int(summary.get("stages_total") or len(STAGES)),
    ))
    elapsed = summary.get("elapsed_ms")
    if elapsed is not None:
        parts.append("ms=%d" % int(elapsed))
    return " ".join(parts)


def summary_for_turn_id(turn_id: str) -> Optional[Dict[str, Any]]:
    """Most recent completed summary for `turn_id`, or None.

    The operator harness mints `turn_id` before the turn and passes it
    through in params, so it can read its own turn back without any new
    correlation column.
    """
    key = str(turn_id or "")
    if not key:
        return None
    with _ring_lock:
        for summary in reversed(_ring):
            if summary.get("turn_id") == key:
                return dict(summary)
    return None


def recent(limit: int = 10) -> List[Dict[str, Any]]:
    """Newest-first slice of the ring, for operator diagnostics."""
    try:
        n = max(1, min(int(limit), _RING_MAX))
    except Exception:
        n = 10
    with _ring_lock:
        items = list(_ring)[-n:]
    items.reverse()
    return items


def reset_for_tests() -> None:
    """Clear the ring. Tests only — never called from a turn path."""
    with _ring_lock:
        _ring.clear()


__all__ = [
    "STAGES",
    "enabled",
    "begin_turn",
    "mark",
    "end_turn",
    "summarize",
    "log_line",
    "summary_for_turn_id",
    "recent",
    "reset_for_tests",
]
