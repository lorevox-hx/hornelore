"""WO-TRUTH-PIPELINE-01 Phase 2 (Gate 7) --- the shared extraction service.

=======================================================================
  THE GOVERNING RULE

    Connect completed turns to extraction through one shared,
    idempotent, observable, failure-isolated service.
    Do NOT connect interview turns directly to truth.
=======================================================================

WHAT PHASE 1 PROVED, AND WHAT THIS MODULE DOES ABOUT IT
-------------------------------------------------------
Gate 7 Phase 1 instrumented five truth-write stages per narrator turn
and separated three superficially identical zeroes:

  raw_turn_saved=1        the turn DOES persist
  archive_event_created=2 the archive event DOES persist
  extract_fields_called=0 THE ONE REAL DEFECT
  family_truth_written=0  correct by design -- operator-gated
  projection_updated=0    correct by design -- correction-mode-gated

/api/extract-fields had no internal Python caller anywhere under
server/code/api/ (131 files checked, AST-level). Only
ui/js/interview.js:1301 posted to it. A chat_ws-driven turn therefore
never requested field extraction, and nothing downstream of extraction
could fire. This module closes exactly that gap and nothing else.

The two zeroes that were correct stay zero. This service NEVER calls
ft_add_note, ft_add_row, any other family-truth writer, or
projection_writer.apply_correction. Family truth remains operator-gated
behind POST /api/family-truth/*; projections remain reachable only from
the `turn_mode == "correction"` branch in chat_ws. Phase 2 did not
redesign either boundary -- it deliberately left both standing.

THE FOUR PROPERTIES, AND WHERE EACH LIVES
-----------------------------------------
SHARED     -- run_field_extraction() in routers/extract.py is the single
              implementation. run_http_extraction() and
              extract_completed_turn() both call it. The WebSocket path
              does not make an HTTP request to its own server, and
              chat_ws.py holds no copy of the extractor.

IDEMPOTENT -- db.turn_extraction_claim() INSERTs against a UNIQUE INDEX
              on (narrator_id, turn_key). The database decides who wins.
              turn_key is derived from the committed assistant row
              (`turnrow:<turns.id>`), never from a hash of the
              narrator's words: two turns that happen to say the same
              thing are two turns, and one replayed committed turn is
              one turn. See migration 0038 for why this is a table and
              not an in-process set.

OBSERVABLE -- six distinct events, one vocabulary, in EXTRACTION_EVENTS.
              Identifiers, counts, and classifications only. The
              narrator's text is never logged here and never persisted
              to the ledger.

FAILURE-   -- extract_completed_turn() cannot raise. Every exit path
ISOLATED      returns an ExtractionOutcome. It runs AFTER the turn has
              persisted, AFTER the archive event has persisted, and
              AFTER the user-facing `done` frame has been sent, so no
              failure here can roll back a turn, roll back an archive
              event, terminate the WebSocket response, replace the
              assistant reply, or leave the browser waiting.

WHY INLINE-AFTER-RESPONSE AND NOT A DETACHED TASK
-------------------------------------------------
The hook sits in chat_ws.generate_and_stream() between the awaited turn
body and the probe close. By that point _generate_and_stream_inner()
has already sent {"type": "done"} -- the browser's completed-turn signal
is out the door before extraction starts, so extraction adds zero
latency to the turn the user is waiting on.

The repo's only post-response async mechanism is
`asyncio.create_task` at the start_turn handler, and a bare detached
task there would be cancelled by the NEXT start_turn with nothing
written down -- the "silently disappears on process shutdown" failure
mode Phase 2 was told not to introduce. Running inside the turn's own
task instead means: (a) the claim row is already persisted at
outcome='started' before any work begins, so an abandoned attempt is
auditable rather than invisible; and (b) CancelledError is caught,
recorded as failed/CancelledError, and re-raised so asyncio's
cancellation contract is not broken.

A wall-clock ceiling (EXTRACTION_TIMEOUT_S) bounds the extractor so a
hung LLM call cannot pin the socket's task indefinitely.

PRIVACY
-------
Gate 7 Step 5: "Do not log raw private narrative text unless existing
privacy policy explicitly permits it." Nothing in this module logs or
persists narrator text, extracted values, or field paths. Failures
report `exc.__class__.__name__` only -- never a message and never a
traceback, because an extractor message can quote the narrator back.

CLAUDE.md:44 -- no operator leakage. Output goes to api.log, the
truth-pipeline probe ring buffer, and the ledger table. Never to the
narrator surface.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── The six-outcome observability vocabulary ─────────────────────────────
# Fixed by the Phase 2 work order. A new outcome means moving the work
# order and the runtime-architecture doc forward first, not appending
# here quietly.
EXTRACTION_EVENTS: tuple[str, ...] = (
    "extract_fields_requested",
    "extract_fields_started",
    "extract_fields_succeeded",
    "extract_fields_noop",
    "extract_fields_duplicate",
    "extract_fields_failed",
)

# Terminal statuses an ExtractionOutcome can carry. "requested" and
# "started" are events, not terminal states -- they never appear here.
EXTRACTION_STATUSES: tuple[str, ...] = (
    "succeeded",
    "noop",
    "duplicate",
    "failed",
)

# Which turn modes are eligible for completed-turn extraction.
#
# Phase 2 scope is the interview turn -- the one Phase 1 proved silent.
# The deterministic short-circuit modes (floor_hold, meta_question,
# witness, memory_echo, age_recall, correction) are NOT interview turns
# and are NOT in scope. `correction` in particular must stay out: it
# already has its own guarded projection path, and routing it through
# extraction as well would change correction behaviour, which Phase 2
# was explicitly told not to do.
EXTRACTION_ELIGIBLE_TURN_MODES: frozenset = frozenset({"interview"})

# Wall-clock ceiling for one extraction. The extractor makes a local LLM
# call; 90s matches the operator harness's own default turn timeout so
# the two cannot disagree about what "hung" means.
EXTRACTION_TIMEOUT_S: float = 90.0

_SOURCE_HTTP = "http"
_SOURCE_CHAT_WS = "chat_ws"
_SOURCE_HARNESS_REPLAY = "harness_replay"


@dataclass
class ExtractionOutcome:
    """What happened when a completed turn asked for extraction.

    Never an exception. extract_completed_turn() returns one of these on
    every path including catastrophic failure, because the caller is a
    turn that has already succeeded from the narrator's point of view
    and must not be disturbed.
    """

    status: str                       # one of EXTRACTION_STATUSES
    turn_key: str = ""
    turn_id: str = ""
    narrator_id: str = ""
    session_id: str = ""
    turn_mode: str = ""
    source: str = ""
    item_count: int = 0
    method: str = ""
    error_class: str = ""             # class name only -- never a message
    duration_ms: int = 0
    ledger_id: Optional[int] = None
    items: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when extraction ran or was correctly skipped as a dup."""
        return self.status in ("succeeded", "noop", "duplicate")

    def as_log_fields(self) -> str:
        """Identifier/count/classification summary. No narrative text."""
        return (
            f"turn_id={self.turn_id or '-'} "
            f"turn_key={self.turn_key or '-'} "
            f"narrator={self.narrator_id or '-'} "
            f"session={self.session_id or '-'} "
            f"mode={self.turn_mode or '-'} "
            f"source={self.source or '-'} "
            f"outcome={self.status} "
            f"items={self.item_count} "
            f"method={self.method or '-'} "
            f"error={self.error_class or '-'} "
            f"duration_ms={self.duration_ms}"
        )


# ── The test seam ────────────────────────────────────────────────────────
def forced_failure_mode() -> str:
    """Harness-only forced-failure seam for Gate 7 Phase 2 live Test C.

    Returns "" (the production value) unless
    HORNELORE_EXTRACTION_FORCE_FAILURE is set. This exists so a live
    acceptance run can prove failure isolation -- turn still saved,
    archive event still saved, browser turn still completes, failure
    still recorded -- WITHOUT corrupting production configuration to
    manufacture the failure.

    Recognised values:
      "raise"   -- the extractor call raises before doing any work
      "timeout" -- the extractor call sleeps past EXTRACTION_TIMEOUT_S

    Default OFF. Like the operator harness flag, this must be unset
    again after a verification run.
    """
    return (os.environ.get("HORNELORE_EXTRACTION_FORCE_FAILURE") or "").strip().lower()


class ForcedExtractionFailure(RuntimeError):
    """Raised only by the Test C seam. Never raised in production."""


# ── Probe bridge ─────────────────────────────────────────────────────────
def _mark_probe(detail: str) -> None:
    """Mark `extract_fields_called` on the running turn probe.

    Gate 7 Phase 2 Step 5 moved this mark out of the HTTP route and into
    the shared service, so the stage now reflects an actual invocation of
    the extraction capability rather than "somebody hit that route".
    Both callers pass through here.

    Swallows everything: probe failure must never affect a turn.
    """
    try:
        from . import truth_pipeline_probe as _tp
        _tp.mark("extract_fields_called", detail)
    except Exception:
        pass


def _call_extractor(req: Any) -> Any:
    """Invoke the single extraction implementation.

    Imported lazily and by name so this module does not import a router
    at module scope (routers/extract.py imports this module from inside
    its route function -- the pair is deliberately lazy on both sides).
    """
    from ..routers.extract import run_field_extraction
    return run_field_extraction(req)


# ── Caller 1: the HTTP endpoint ──────────────────────────────────────────
def run_http_extraction(req: Any) -> Any:
    """POST /api/extract-fields goes through here.

    Behaviour-preserving wrapper: same probe mark the route used to make
    itself, then the same extraction body it used to contain. The HTTP
    request carries no committed turn identity, so this path takes NO
    idempotency claim -- a browser that posts the same answer twice
    deliberately gets two extractions, exactly as it did before Phase 2.
    Turn-scoped idempotency belongs to the turn path, which has a
    persisted row to key on.
    """
    _mark_probe("extract-fields")
    return _call_extractor(req)


# ── Caller 2: the chat_ws completed-turn path ────────────────────────────
def extraction_eligible(turn_mode: Optional[str]) -> bool:
    """True when this turn mode participates in completed-turn extraction."""
    return (turn_mode or "").strip().lower() in EXTRACTION_ELIGIBLE_TURN_MODES


def build_extraction_request(
    *,
    narrator_id: str,
    user_text: str,
    session_id: Optional[str] = None,
    current_section: Optional[str] = None,
    current_target_path: Optional[str] = None,
    current_era: Optional[str] = None,
    current_pass: Optional[str] = None,
    current_mode: Optional[str] = None,
) -> Any:
    """Build the ExtractFieldsRequest for a completed turn.

    `answer` is the NARRATOR's text. The assistant reply is not the
    subject of extraction -- extracting from Lori's own words would let
    the model's phrasing become the narrator's biography.

    transcript_source is left None rather than guessed. The chat_ws turn
    does not know whether the browser typed or dictated, and inventing
    "typed" here would silently bypass the WO-STT-LIVE-02 fragile-field
    confirmation gate for dictated answers.
    """
    from ..routers.extract import ExtractFieldsRequest
    return ExtractFieldsRequest(
        person_id=narrator_id,
        session_id=session_id or None,
        answer=user_text or "",
        current_section=current_section,
        current_target_path=current_target_path,
        current_era=current_era,
        current_pass=current_pass,
        current_mode=current_mode,
    )


async def extract_completed_turn(
    *,
    narrator_id: str,
    turn_id: str,
    user_text: str,
    assistant_text: Optional[str] = None,
    session_id: Optional[str] = None,
    turn_key: str = "",
    turn_mode: str = "interview",
    source: str = _SOURCE_CHAT_WS,
    current_section: Optional[str] = None,
    current_target_path: Optional[str] = None,
    current_era: Optional[str] = None,
    current_pass: Optional[str] = None,
    current_mode: Optional[str] = None,
) -> ExtractionOutcome:
    """Request field extraction for one completed, persisted turn.

    NEVER RAISES except asyncio.CancelledError, which is recorded and
    then re-raised so cancellation semantics stay intact. Every other
    path -- including a broken database, a missing extractor, or a hung
    LLM -- returns an ExtractionOutcome describing what happened.

    Preconditions the CALLER must satisfy before calling:
      * the raw turn has been committed
      * the required archive event has been written
      * the user-facing response has already been sent

    Writes NO family truth and touches NO projection. Both boundaries
    are Phase 1 findings that Phase 2 preserved on purpose.

    `assistant_text` is accepted for outcome logging and future
    two-sided extraction; it is NOT fed to the extractor today (see
    build_extraction_request).
    """
    started = time.monotonic()
    narrator_id = (narrator_id or "").strip()
    turn_id = (turn_id or "").strip()
    turn_key = (turn_key or "").strip()
    turn_mode = (turn_mode or "").strip()

    def _outcome(
        status: str,
        *,
        item_count: int = 0,
        method: str = "",
        error_class: str = "",
        ledger_id: Optional[int] = None,
        items: Optional[List[Dict[str, Any]]] = None,
    ) -> ExtractionOutcome:
        return ExtractionOutcome(
            status=status,
            turn_key=turn_key,
            turn_id=turn_id,
            narrator_id=narrator_id,
            session_id=session_id or "",
            turn_mode=turn_mode,
            source=source,
            item_count=item_count,
            method=method,
            error_class=error_class,
            duration_ms=int((time.monotonic() - started) * 1000),
            ledger_id=ledger_id,
            items=items or [],
        )

    logger.info(
        "[extract-turn] extract_fields_requested turn_id=%s turn_key=%s "
        "narrator=%s session=%s mode=%s source=%s",
        turn_id or "-", turn_key or "-", narrator_id or "-",
        session_id or "-", turn_mode or "-", source,
    )

    # ── Guard rails before any claim is taken ────────────────────────
    if not extraction_eligible(turn_mode):
        out = _outcome("noop", method="ineligible_turn_mode")
        logger.info("[extract-turn] extract_fields_noop %s", out.as_log_fields())
        return out

    if not narrator_id or not (user_text or "").strip():
        out = _outcome("noop", method="missing_narrator_or_text")
        logger.info("[extract-turn] extract_fields_noop %s", out.as_log_fields())
        return out

    if not turn_key:
        # No committed row id means no stable key. Phase 2 requires the
        # key to come from the persisted turn, so the correct answer is
        # to decline rather than fall back to hashing the narrator's
        # words -- a text key would collide across legitimately
        # identical answers and would defeat replay detection anyway.
        out = _outcome("noop", method="no_stable_turn_key")
        logger.warning(
            "[extract-turn] extract_fields_noop %s "
            "(no committed turn row id -- extraction declined rather "
            "than keyed on text)", out.as_log_fields(),
        )
        return out

    # ── The persisted claim. The database decides who runs. ──────────
    ledger_id: Optional[int] = None
    try:
        from .. import db as _db
        ledger_id = _db.turn_extraction_claim(
            narrator_id=narrator_id,
            turn_key=turn_key,
            turn_id=turn_id,
            session_id=session_id or "",
            turn_mode=turn_mode,
            source=source,
        )
    except Exception as claim_exc:
        out = _outcome("failed", error_class=claim_exc.__class__.__name__)
        logger.error(
            "[extract-turn] extract_fields_failed %s (claim stage)",
            out.as_log_fields(),
        )
        return out

    if ledger_id is None:
        # Replay, reconnect, or retry of a turn that is already owned.
        out = _outcome("duplicate", method="already_processed")
        logger.info(
            "[extract-turn] extract_fields_duplicate %s", out.as_log_fields(),
        )
        return out

    # ── Run it ───────────────────────────────────────────────────────
    logger.info(
        "[extract-turn] extract_fields_started turn_id=%s turn_key=%s "
        "narrator=%s ledger_id=%s",
        turn_id or "-", turn_key, narrator_id, ledger_id,
    )

    # THE STAGE MEANS "ASKED", NOT "SUCCEEDED". Until 2026-07-30 this
    # mark lived inside _run_sync, below the forced-failure seam, so a
    # turn whose extraction was invoked and then failed reported
    # `extract_fields_called=0` --- the exact reading the original
    # defect produced. Gate 7 exists because three identical zeroes
    # meant three different things; an observability stage that cannot
    # tell "never asked" from "asked and failed" reintroduces the
    # confusion it was built to remove. The claim is won and the
    # attempt is about to run, so the stage is true from here on.
    # Marked on the event loop, inside the turn's own probe context,
    # rather than in the worker thread.
    _mark_probe("turn-extraction")

    def _finish(
        outcome: str,
        *,
        item_count: int = 0,
        method: str = "",
        error_class: str = "",
        duration_ms: int = 0,
    ) -> None:
        """Close the ledger row. Ledger failure must not mask the turn."""
        try:
            from .. import db as _db
            _db.turn_extraction_finish(
                ledger_id=int(ledger_id),
                outcome=outcome,
                item_count=item_count,
                method=method,
                error_class=error_class,
                duration_ms=duration_ms,
            )
        except Exception as fin_exc:
            logger.error(
                "[extract-turn] ledger close failed ledger_id=%s outcome=%s "
                "err=%s (turn unaffected)",
                ledger_id, outcome, fin_exc.__class__.__name__,
            )

    def _run_sync() -> Any:
        """Body executed off the event loop. Marks the probe, extracts."""
        forced = forced_failure_mode()
        if forced == "raise":
            raise ForcedExtractionFailure(
                "HORNELORE_EXTRACTION_FORCE_FAILURE=raise "
                "(Gate 7 Phase 2 live Test C seam)"
            )
        if forced == "timeout":
            time.sleep(EXTRACTION_TIMEOUT_S + 30.0)
        req = build_extraction_request(
            narrator_id=narrator_id,
            user_text=user_text,
            session_id=session_id,
            current_section=current_section,
            current_target_path=current_target_path,
            current_era=current_era,
            current_pass=current_pass,
            current_mode=current_mode,
        )
        return _call_extractor(req)

    try:
        resp = await asyncio.wait_for(
            asyncio.to_thread(_run_sync), timeout=EXTRACTION_TIMEOUT_S,
        )
    except asyncio.CancelledError:
        # A new start_turn cancelled this socket's task mid-extraction.
        # Record it, then honour the cancellation contract -- an
        # abandoned attempt leaves a row behind rather than vanishing.
        out = _outcome(
            "failed", error_class="CancelledError", ledger_id=ledger_id,
        )
        _finish(
            "failed", error_class="CancelledError",
            duration_ms=out.duration_ms,
        )
        logger.warning(
            "[extract-turn] extract_fields_failed %s (turn cancelled "
            "mid-extraction; response already delivered)",
            out.as_log_fields(),
        )
        raise
    except asyncio.TimeoutError:
        out = _outcome(
            "failed", error_class="TimeoutError", ledger_id=ledger_id,
        )
        _finish(
            "failed", error_class="TimeoutError", duration_ms=out.duration_ms,
        )
        logger.error(
            "[extract-turn] extract_fields_failed %s (ceiling %.0fs)",
            out.as_log_fields(), EXTRACTION_TIMEOUT_S,
        )
        return out
    except BaseException as exc:  # noqa: BLE001 -- see module docstring
        # Deliberately broad. The caller is a turn the narrator already
        # saw succeed; nothing the extractor can raise may reach them.
        # Class name only, never str(exc) -- an extractor message can
        # quote the narrator's own words back into the log.
        out = _outcome(
            "failed", error_class=exc.__class__.__name__, ledger_id=ledger_id,
        )
        _finish(
            "failed", error_class=exc.__class__.__name__,
            duration_ms=out.duration_ms,
        )
        logger.error(
            "[extract-turn] extract_fields_failed %s", out.as_log_fields(),
        )
        return out

    # ── Interpret the result ─────────────────────────────────────────
    items: List[Dict[str, Any]] = []
    method = ""
    try:
        raw_items = getattr(resp, "items", None) or []
        method = str(getattr(resp, "method", "") or "")
        for it in raw_items:
            if hasattr(it, "model_dump"):
                items.append(it.model_dump())
            elif hasattr(it, "dict"):
                items.append(it.dict())
            elif isinstance(it, dict):
                items.append(it)
    except Exception as shape_exc:
        # The extractor returned something unexpected. That is a failure
        # of this integration, not of the turn.
        out = _outcome(
            "failed", error_class=shape_exc.__class__.__name__,
            ledger_id=ledger_id,
        )
        _finish(
            "failed", error_class=shape_exc.__class__.__name__,
            duration_ms=out.duration_ms,
        )
        logger.error(
            "[extract-turn] extract_fields_failed %s (result shape)",
            out.as_log_fields(),
        )
        return out

    if not items:
        # Ran cleanly, found nothing. A narrator can say something with
        # no extractable field in it; that is not an error.
        out = _outcome(
            "noop", method=method or "no_items", ledger_id=ledger_id,
        )
        _finish(
            "noop", item_count=0, method=method or "no_items",
            duration_ms=out.duration_ms,
        )
        logger.info("[extract-turn] extract_fields_noop %s", out.as_log_fields())
        return out

    out = _outcome(
        "succeeded", item_count=len(items), method=method,
        ledger_id=ledger_id, items=items,
    )
    _finish(
        "succeeded", item_count=len(items), method=method,
        duration_ms=out.duration_ms,
    )
    logger.info("[extract-turn] extract_fields_succeeded %s", out.as_log_fields())
    return out
