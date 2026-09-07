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
    extraction         wired for BOTH scheduler paths — the claim path
                       via _complete_claim, and the no-claim path
                       (Life Map era prompts are internal directives)
                       which returns not_applicable, since extraction
                       was deliberately not attempted
    bio_facts          attached by the harness from /api/facts/list
    chronology         attached by the harness, before/after compared
    life_map           attached by the harness, before/after compared
    rolling_summary    MEASURED BY THE HARNESS. Previously listed here
                       as "NOT WIRED", which was wrong: the endpoint is
                       live and takes GET and POST after every turn. It
                       was never READ, which is a different thing.
    archive            genuinely uninstrumented -> not_measured
    memoir_source      attached by the harness at the API origin

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
#: The system deliberately excluded this turn from the stage. Nothing
#: was attempted, so "measured and found nothing" would be a false
#: claim — a Life Map era prompt is an internal directive and is not
#: eligible for extraction by design.
RESULT_NOT_APPLICABLE = "not_applicable"
#: No instrumentation exists for this stage yet.
RESULT_NOT_MEASURED = "not_measured"

RESULTS = (RESULT_PERSISTED, RESULT_REJECTED, RESULT_MEASURED_ABSENT,
           RESULT_MEASUREMENT_FAILED, RESULT_NOT_APPLICABLE,
           RESULT_NOT_MEASURED)

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


#: Closed vocabulary of pre-generation terminal outcomes.
#:
#: Each names a turn where the model was NEVER CALLED. They are not
#: response outcomes and must never be counted among them.
TERMINAL_PROMPT_TOO_LARGE = "prompt_too_large"
TERMINAL_VRAM_PRESSURE = "vram_pressure"
#: The BUDGET said the prompt fitted and the real tokenizer disagreed.
#: A different event from `prompt_too_large`: that one is the budget
#: working as designed, this one is the budget being WRONG. Collapsing
#: them would hide a measurement disagreement inside an expected refusal.
TERMINAL_PROMPT_BUDGET_BACKSTOP = "prompt_budget_backstop"
#: A previous generation thread would not exit, so this turn never
#: started. Pre-generation like the others, and just as much a turn the
#: narrator lost.
TERMINAL_GENERATION_BUSY = "generation_busy"

#: Outcomes where GENERATION DID START and then failed. Separate from the
#: pre-generation set on purpose: `generation_attempted` is True for
#: these, and a report that merged them would count a turn the model
#: began among turns it was never asked to begin.
TERMINAL_CUDA_OOM = "cuda_oom"
#: The narrator or the socket ended the turn after generation began.
#: Closed through `abort()`, not `terminal()` — the model DID speak, and
#: filing it among turns never asked to speak would blur the one
#: distinction a VRAM diagnostic most needs.
TERMINAL_CANCELLED = "cancelled"
TERMINAL_GENERATION_FAILED = "generation_failed"

#: What a terminal record must carry to be worth having.
#:
#: Deliberately NOT `REQUIRED_CONTEXT`. That contract describes a turn
#: with a response in it and demands fields a never-generated turn cannot
#: have; reusing it would force a refusal to impersonate an ordinary
#: trace missing some values, which is precisely the confusion this API
#: exists to end.
REQUIRED_TERMINAL_CONTEXT = ("narrator_input", "runtime71_current_era",
                             "prompt_budget", "terminal_outcome",
                             "generation_attempted")

#: The VRAM refusal additionally has to say what it refused and why.
#: A guard decision without the numbers behind it is an assertion.
REQUIRED_TERMINAL_VRAM_CONTEXT = ("prompt_tokens", "max_new_requested",
                                  "max_new_effective", "vram_free_pre_mb",
                                  "vram_total_mb", "vram_required_mb",
                                  "vram_guard_decision")


def terminal(outcome: str, *, generation_attempted: bool = False,
             detail: Optional[Dict[str, Any]] = None,
             trace_id: Optional[str] = None) -> None:
    """Close a turn where GENERATION NEVER HAPPENED, and write it.

    `WO-LORI-LISTEN-AND-RETAIN-01` §9.

    ── WHY NOT `seal()`/`finish()`, 2026-09-06 ─────────────────────────

    `seal` closes the RESPONSE half of a trace. A prompt-budget or VRAM
    refusal has no response half at all — no model ran. Passing empty
    strings through `seal` would manufacture `delivered_text=""` and
    `persisted_text=""`, and a reader could not then distinguish

        the model was never called

    from

        the model was called and returned nothing

    which are different failures with different owners. **The JSON has to
    say which, rather than leaving a report to infer it from an absent
    field.** So this writes `terminal_outcome` and
    `generation_attempted` explicitly, and touches none of the response
    fields: `raw_captured` stays False, and `raw_text`, `delivered_text`
    and `persisted_text` are never created.

    The record is written immediately and the current trace cleared —
    there is no retention half to wait for, because nothing was said to
    persist.
    """
    try:
        tid = trace_id or current()
        if not tid:
            return
        with _lock:
            rec = _traces.pop(tid, None)
        if rec is None:
            return
        rec["terminal_outcome"] = outcome
        rec["generation_attempted"] = bool(generation_attempted)
        # A turn that began generating and then failed still has no
        # response, but it is NOT the same event as one the model was
        # never asked to run. Both belong here — the alternative is a
        # leaked, unwritten trace, which is the worst of the three — and
        # `generation_attempted` is what separates them.
        if detail:
            rec.setdefault("context", {}).update(detail)
        # `ended_at` WITHOUT `_seal_rec`, which is the whole point: that
        # helper's job is the delivered/persisted comparison, and there
        # is nothing to compare.
        rec["ended_at"] = time.time()

        required = list(REQUIRED_TERMINAL_CONTEXT)
        if outcome == TERMINAL_VRAM_PRESSURE:
            required += list(REQUIRED_TERMINAL_VRAM_CONTEXT)
        elif generation_attempted:
            # A failure DURING generation cannot be held to the
            # pre-generation contract: it has prompt evidence but the
            # outcome is about what happened after the model started.
            # Demanding the pre-generation set would mark every one of
            # these incomplete for fields that do not apply.
            required = ["narrator_input", "terminal_outcome",
                        "generation_attempted"]
        ctx = rec.get("context") or {}
        missing = [k for k in required if k not in ctx]
        rec["terminal_context_complete"] = not missing
        if missing:
            # Recorded, not raised. A trace that refuses to write is a
            # trace nobody has; naming the gap keeps the record honest
            # and still leaves the evidence on disk.
            rec["terminal_context_missing"] = missing
        _write(rec)
        try:
            _current.set(None)
        except Exception:
            pass
    except Exception:
        return


def abort(outcome: str, *, detail: Optional[Dict[str, Any]] = None,
          trace_id: Optional[str] = None) -> None:
    """Close a turn that GENERATED but delivered nothing, and write it.

    `WO-LORI-LISTEN-AND-RETAIN-01` §9, added 2026-09-06 after review.

    ── WHY NOT `terminal()`, WHICH ALREADY EXISTS ──────────────────────

    `terminal()` means *the model was never called*. A cancelled turn is
    the opposite: the model ran, tokens arrived, and then the narrator or
    the socket ended it before anything was delivered or persisted. Both
    end with no response, and treating them as the same event would put a
    turn Lori spoke into the same bucket as turns she was never asked to
    speak — while a VRAM diagnostic is trying to tell exactly those apart.

    So this is a third shape, and it is deliberately narrow:

    * `generation_attempted` is **True**;
    * whatever `raw()` already captured is **kept** — partial output is
      real evidence about what the model was doing when it was stopped,
      and discarding it would lose the only record of a turn that cost
      real VRAM and real time;
    * `delivered_text` and `persisted_text` are **never created**,
      because nothing was delivered and nothing was persisted.

    Written immediately; there is no retention half, since nothing
    reached storage to attach to.
    """
    try:
        tid = trace_id or current()
        if not tid:
            return
        with _lock:
            rec = _traces.pop(tid, None)
        if rec is None:
            return
        rec["terminal_outcome"] = outcome
        rec["generation_attempted"] = True
        rec["delivered_anything"] = False
        if detail:
            rec.setdefault("context", {}).update(detail)
        # NOT `_seal_rec`: that helper's job is the delivered/persisted
        # comparison, and there is no delivered text to compare against.
        rec["ended_at"] = time.time()
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
