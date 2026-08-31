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

This module closes that gap for the RESPONSE half: one `trace_id` per
turn, from the raw model output through every transformation, the
delivered text and the persisted rows.

── WHAT IS AND IS NOT WIRED (2026-08-31) ─────────────────────────────

An earlier version of this docstring claimed the module traced
"extraction, placement, and memoir-source retrieval". It did not — there
was exactly ONE `storage()` call in product code (`durable_turns`), and
the claim was ahead of the implementation. Corrected here, and the
inventory is kept in `RETENTION_STAGES` so the report renders the truth
rather than a promise:

    durable_turns      wired in chat_ws after persist_turn_transaction
    extraction         wired via park/attach from the extraction hook
    bio_facts          attached by the harness from /api/facts/list
    chronology         attached by the harness
    life_map           attached by the harness
    rolling_summary    NOT WIRED -> not_measured
    archive            NOT WIRED -> not_measured
    memoir_source      attached by the harness; expect measurement_failed

Any stage not attached by the time the record is written is emitted as
`not_measured`. Missing instrumentation must never render as a pass.

── CONTINUATION ──────────────────────────────────────────────────────

Extraction runs as a background task AFTER the response is persisted, so
the trace cannot close at persistence or the retention half is lost.
`park()` moves a finished response-trace into a holding area keyed by
trace id AND by durable row id; `attach()` adds retention results as they
arrive; `close()` writes it. A parked record that is never closed is
swept out on a later turn with its unattached stages marked
`not_measured`, so a crash loses the attachment, never the evidence.

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
_parked: Dict[str, Dict[str, Any]] = {}
_parked_keys: Dict[str, str] = {}
_MAX_LIVE = 64


#: Retention stages the report must account for, wired or not.
RETENTION_STAGES = (
    "durable_turns", "extraction", "bio_facts", "chronology",
    "life_map", "rolling_summary", "archive", "memoir_source",
)


def enabled() -> bool:
    """OPT-IN. Off unless HORNELORE_RESPONSE_TRACE is explicitly truthy.

    Default-on would have every ordinary production turn writing an
    evidence record indefinitely, which is neither wanted nor consented
    to. The evaluation stack is launched with the flag set; the harness
    refuses to run if tracing is unavailable rather than producing a
    report with no trace in it.
    """
    return os.environ.get(_ENV_FLAG, "0").strip().lower() in (
        "1", "true", "yes", "on")


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
            "schema_version": SCHEMA_VERSION,
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


SCHEMA_VERSION = 2

#: Context keys a usable trace MUST carry. A record missing any of these
#: is marked instrumentation_failed so the report can refuse it rather
#: than quietly rendering a turn with no interpretable context.
REQUIRED_CONTEXT = ("narrator_input", "runtime71_current_era",
                    "prompt_tokens", "prompt_budget")


def require(keys: Optional[List[str]] = None, *, failed: Optional[str] = None,
            trace_id: Optional[str] = None) -> None:
    """Assert required context is present. Records a failure if not.

    The previous version read required values through `locals()` inside
    a bare `except`, so five of seven names silently did not exist and
    the trace looked populated while carrying almost nothing. Missing
    required evidence is now a recorded INSTRUMENTATION FAILURE.
    """
    try:
        tid = trace_id or current()
        if not tid:
            return
        with _lock:
            rec = _traces.get(tid)
            if rec is None:
                return
            ctx = rec.get("context") or {}
            missing = [k for k in (keys or REQUIRED_CONTEXT)
                       if k not in ctx or ctx[k] in (None, "")]
            if failed or missing:
                rec["instrumentation_failed"] = True
                rec["instrumentation_error"] = failed
                rec["missing_required_context"] = missing
            else:
                rec.setdefault("instrumentation_failed", False)
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


def _seal_rec(rec: Dict[str, Any], delivered: Optional[str],
              persisted: Optional[str]) -> None:
    """Fill the delivered/persisted comparison. Does NOT write."""
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


def seal(delivered: Optional[str] = None, persisted: Optional[str] = None,
         trace_id: Optional[str] = None) -> None:
    """Close the RESPONSE half without writing, so `park` can continue it."""
    try:
        tid = trace_id or current()
        if not tid:
            return
        with _lock:
            rec = _traces.get(tid)
            if rec is not None:
                _seal_rec(rec, delivered, persisted)
    except Exception:
        return


def finish(delivered: Optional[str] = None, persisted: Optional[str] = None,
           trace_id: Optional[str] = None) -> None:
    """Seal AND write immediately. Use `seal` + `park` when retention
    results still need to attach."""
    try:
        tid = trace_id or current()
        if not tid:
            return
        with _lock:
            rec = _traces.pop(tid, None)
        if rec is None:
            return
        _seal_rec(rec, delivered, persisted)
        _write(rec)
        try:
            _current.set(None)
        except Exception:
            pass
    except Exception:
        return


def park(keys: Optional[List[str]] = None,
         trace_id: Optional[str] = None) -> None:
    """Hold a finished response-trace open for retention attachment.

    Indexed by trace id and by every durable row id supplied, because
    the extraction hook knows the row, not the trace.
    """
    try:
        tid = trace_id or current()
        if not tid:
            return
        with _lock:
            rec = _traces.pop(tid, None)
            if rec is None:
                return
            rec["parked_at"] = time.time()
            _parked[tid] = rec
            for k in (keys or []):
                if k:
                    _parked_keys[str(k)] = tid
        _sweep()
    except Exception:
        return


def attach(key: str, stage_name: str, result: str, *,
           detail: Any = None) -> bool:
    """Add a retention result to a parked trace. True if it landed."""
    try:
        with _lock:
            tid = _parked_keys.get(str(key)) or (
                str(key) if str(key) in _parked else None)
            rec = _parked.get(tid) if tid else None
            if rec is None:
                return False
            r = result if result in RESULTS else RESULT_NOT_MEASURED
            rec["storage"][str(stage_name)] = {
                "result": r,
                "coerced_from": None if r == result else result,
                "detail": detail,
            }
            return True
    except Exception:
        return False


def close(key: str) -> None:
    """Write a parked trace out, by trace id or durable row id."""
    try:
        with _lock:
            tid = _parked_keys.get(str(key)) or (
                str(key) if str(key) in _parked else None)
            rec = _parked.pop(tid, None) if tid else None
            if rec is not None:
                for k in [k for k, v in _parked_keys.items() if v == tid]:
                    _parked_keys.pop(k, None)
        if rec is not None:
            _write(rec)
    except Exception:
        return


def _sweep(max_age_s: float = 180.0) -> None:
    """Write out parked traces nobody closed. Evidence is never dropped."""
    try:
        now = time.time()
        stale = []
        with _lock:
            for tid, rec in list(_parked.items()):
                if now - rec.get("parked_at", now) > max_age_s:
                    stale.append(_parked.pop(tid))
                    for k in [k for k, v in _parked_keys.items() if v == tid]:
                        _parked_keys.pop(k, None)
        for rec in stale:
            rec["swept"] = True
            _write(rec)
    except Exception:
        return


def _write(rec: Dict[str, Any]) -> None:
    """Emit one record. Unattached retention stages are not_measured."""
    try:
        for name in RETENTION_STAGES:
            rec["storage"].setdefault(name, {
                "result": RESULT_NOT_MEASURED,
                "coerced_from": None,
                "detail": {"why": "no instrumentation attached this stage"},
            })
        rec["ended_at"] = rec.get("ended_at") or time.time()
        d = _out_dir()
        d.mkdir(parents=True, exist_ok=True)
        day = time.strftime("%Y-%m-%d", time.gmtime(rec.get("started_at", 0)))
        with (d / f"{day}.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
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


def health() -> Dict[str, Any]:
    """Read-only status for the harness preflight.

    The harness previously probed a route that did not exist and then
    accepted the mere presence of an old trace directory, so a stale
    directory could satisfy preflight while the API had tracing off.
    `enabled` here is the live value from this process.
    """
    d = _out_dir()
    return {
        "enabled": enabled(),
        "schema_version": SCHEMA_VERSION,
        "env_flag": _ENV_FLAG,
        "output_dir": str(d),
        "output_dir_exists": d.is_dir(),
        "retention_stages": list(RETENTION_STAGES),
        "required_context": list(REQUIRED_CONTEXT),
    }
