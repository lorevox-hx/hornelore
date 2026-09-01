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

FAILURE-   -- neither begin_completed_turn_extraction() nor
ISOLATED      extract_completed_turn() can raise. Every exit path
              returns an ExtractionOutcome. Extraction runs AFTER the
              turn has persisted, AFTER the archive event has
              persisted, and AFTER the user-facing `done` frame has
              been sent, so no failure here can roll back a turn, roll
              back an archive event, terminate the WebSocket response,
              replace the assistant reply, or leave the browser
              waiting.

THE TWO HALVES, AND WHY THE WORK MOVED OFF THE TURN'S OWN TASK
--------------------------------------------------------------
CORRECTED 2026-07-30, by the first live acceptance run. Until that run
this docstring carried a section headed "WHY INLINE-AFTER-RESPONSE AND
NOT A DETACHED TASK" which asserted:

    "Running inside the turn's own task instead means: (a) the claim
    row is already persisted at outcome='started' before any work
    begins, so an abandoned attempt is auditable rather than
    invisible; and (b) CancelledError is caught, recorded as
    failed/CancelledError, and re-raised so asyncio's cancellation
    contract is not broken."

Half (a) and half (b) were both true and both still hold. The
CONCLUSION drawn from them -- that awaiting extraction inside the turn
task was therefore safe -- was wrong, and the live run is what proved
it. Every interview turn in that run recorded outcome='failed',
error_class='CancelledError', duration_ms 815 and 839: the harness (and
any real browser that navigates away, refreshes, or drops its socket)
closes the connection as soon as the `done` frame arrives, chat_ws
cancels the in-flight turn task, and the extraction awaiting inside it
died every single time. Extraction that is cancelled 100% of the time
is not connected to anything.

It also had a second effect nobody had measured for: the awaited
extraction extended the turn body by ~830ms, and the truth-pipeline
probe files its record in a `finally` that runs only after the body
returns -- past the operator harness's read window. The instrument
reported "no probe record at all" for turns that had in fact succeeded.

So the service is now two halves:

  begin_completed_turn_extraction()  -- eligibility, the persisted
      claim, and the probe mark. Sqlite only, no model call, single
      -digit milliseconds. Runs INLINE on the turn's task, inside the
      turn's probe context, because the probe mark and the claim must
      belong to the turn that caused them.

  _complete_claim()                  -- the extractor itself, and the
      ledger close. Runs on a task of its own.

schedule_completed_turn_extraction() joins them for the chat_ws path:
begin inline, then hand the completion to a task registered in
_PENDING_EXTRACTIONS. This is NOT the "fragile detached task" Phase 2
Step 4 forbids, and the distinction is exactly what Step 4 asks for --
"Do not introduce a fragile detached task that can silently disappear
on process shutdown without recording its state":

  * State is recorded BEFORE the task exists. The ledger row is
    committed at outcome='started' by the inline half. A process killed
    mid-extraction leaves a visibly unfinished row, not a silent gap.
  * The task is held, not dropped. _PENDING_EXTRACTIONS keeps a strong
    reference, so the garbage collector cannot eat a running
    extraction -- the classic create_task() leak.
  * Shutdown drains it. drain_pending_extractions() is wired to the
    application's shutdown event; tasks still running past the ceiling
    are cancelled, and cancellation writes failed/CancelledError to the
    ledger before re-raising.
  * A wall-clock ceiling (EXTRACTION_TIMEOUT_S) bounds the extractor so
    a hung LLM call cannot accumulate tasks forever.

extract_completed_turn() remains begin-then-await-complete in one call.
It is the synchronous-semantics entry point: the HTTP-adjacent replay
path and the whole automated suite use it, and it behaves exactly as it
did before the split.

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
from typing import Any, Dict, List, Optional, Set, Tuple

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

# Statuses an ExtractionOutcome can carry.
#
# The first four are terminal and are what the ledger stores.
# "scheduled" is NOT terminal and is NEVER stored: it is what
# schedule_completed_turn_extraction() hands back to chat_ws to say "the
# claim is won, the ledger row is committed at 'started', and the work
# is running on its own task now." The ledger, not this value, is where
# that attempt's real outcome will be written.
EXTRACTION_STATUSES: tuple[str, ...] = (
    "succeeded",
    "noop",
    "duplicate",
    "failed",
    "scheduled",
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

# How long shutdown waits for in-flight extractions before cancelling
# them. Deliberately shorter than EXTRACTION_TIMEOUT_S: a stack restart
# should not block for a minute and a half on one hung model call, and a
# cancelled attempt still writes failed/CancelledError to its ledger row
# on the way out.
EXTRACTION_DRAIN_TIMEOUT_S: float = 20.0

_SOURCE_HTTP = "http"
_SOURCE_CHAT_WS = "chat_ws"
_SOURCE_HARNESS_REPLAY = "harness_replay"

# Strong references to running completion tasks.
#
# asyncio.create_task() only holds a WEAK reference to its task. Without
# this set the garbage collector is free to collect a running extraction
# mid-flight -- the documented create_task() footgun. Membership is also
# what makes the shutdown drain possible at all.
_PENDING_EXTRACTIONS: Set["asyncio.Task[Any]"] = set()


@dataclass
class ExtractionOutcome:
    """What happened when a completed turn asked for extraction.

    Never an exception. Every entry point returns one of these on every
    path including catastrophic failure, because the caller is a turn
    that has already succeeded from the narrator's point of view and
    must not be disturbed.
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
        """True when extraction ran, was correctly skipped, or is running.

        'scheduled' is ok because the caller -- a turn the narrator has
        already seen complete -- has nothing left to do about it. The
        ledger row carries the real answer.
        """
        return self.status in ("succeeded", "noop", "duplicate", "scheduled")

    @property
    def terminal(self) -> bool:
        """True when this outcome is the final word on the attempt."""
        return self.status in ("succeeded", "noop", "duplicate", "failed")

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


@dataclass
class _Claim:
    """A won claim, carrying everything the completion half needs.

    Built only by _begin() and only after the ledger INSERT succeeded,
    so a _Claim in hand always means "this process owns this turn."
    """

    ledger_id: int
    started: float
    narrator_id: str
    turn_id: str
    turn_key: str
    session_id: str
    turn_mode: str
    source: str
    user_text: str
    current_section: Optional[str] = None
    current_target_path: Optional[str] = None
    current_era: Optional[str] = None
    current_pass: Optional[str] = None
    current_mode: Optional[str] = None

    # WO-EXTRACTION-OWNERSHIP-AND-VRAM-STABILITY-01 Phase 2. An awaitable
    # the completion half calls once, with the terminal outcome, after
    # the result is durable.
    #
    # A CALLBACK RATHER THAN AN IMPORT. The result has to reach the
    # socket the turn arrived on, and this module may not import
    # chat_ws -- the dependency runs the other way and reversing it
    # would put a router inside a service. chat_ws supplies a closure
    # over its own `ws`; this module never learns what a WebSocket is.
    #
    # Delivery is best-effort BY DESIGN. The durable row is the promise;
    # this is only the fast path to a browser that is still listening.
    on_result: Optional[Any] = None


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


def forced_failure_armed() -> bool:
    """True when the Test C seam is live in THIS process.

    Read by the operator harness health route so an acceptance run can
    verify which environment the SERVER is actually in rather than
    trusting the shell it was launched from. The first live run of this
    work order failed exactly there: Phase 2 was executed without the
    intervening restart, the seam never reached the server process, and
    the resulting evidence was void. A boolean on a route that is
    already 404-gated closes that hole without leaking a value.
    """
    return forced_failure_mode() in ("raise", "timeout")


class ForcedExtractionFailure(RuntimeError):
    """Raised only by the Test C seam. Never raised in production."""


# ── Probe bridge ─────────────────────────────────────────────────────────
def _mark_probe(detail: str) -> None:
    """Mark `extract_fields_called` on the running turn probe.

    Gate 7 Phase 2 Step 5 moved this mark out of the HTTP route and into
    the shared service, so the stage now reflects an actual invocation of
    the extraction capability rather than "somebody hit that route".
    Both callers pass through here.

    MUST be called on the turn's own task. The probe is keyed to the
    turn context, so a mark made from the completion task would land
    nowhere. That is why the mark lives in the inline half.

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


def _outcome_for(
    claim_like: Dict[str, Any],
    status: str,
    *,
    started: float,
    item_count: int = 0,
    method: str = "",
    error_class: str = "",
    ledger_id: Optional[int] = None,
    items: Optional[List[Dict[str, Any]]] = None,
) -> ExtractionOutcome:
    return ExtractionOutcome(
        status=status,
        turn_key=claim_like.get("turn_key", ""),
        turn_id=claim_like.get("turn_id", ""),
        narrator_id=claim_like.get("narrator_id", ""),
        session_id=claim_like.get("session_id", "") or "",
        turn_mode=claim_like.get("turn_mode", ""),
        source=claim_like.get("source", ""),
        item_count=item_count,
        method=method,
        error_class=error_class,
        duration_ms=int((time.monotonic() - started) * 1000),
        ledger_id=ledger_id,
        items=items or [],
    )


def _finish_ledger(
    ledger_id: Optional[int],
    outcome: str,
    *,
    item_count: int = 0,
    method: str = "",
    error_class: str = "",
    duration_ms: int = 0,
) -> None:
    """Close the ledger row. Ledger failure must not mask the turn."""
    if ledger_id is None:
        return
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


def _begin(
    *,
    narrator_id: str,
    turn_id: str,
    user_text: str,
    session_id: Optional[str],
    turn_key: str,
    turn_mode: str,
    source: str,
    current_section: Optional[str],
    current_target_path: Optional[str],
    current_era: Optional[str],
    current_pass: Optional[str],
    current_mode: Optional[str],
    is_system_directive: bool = False,
) -> Tuple[Optional[ExtractionOutcome], Optional[_Claim]]:
    """The inline half: decide, claim, mark the probe. Never raises.

    Returns exactly one of:
      (terminal_outcome, None) -- nothing more to do; noop, duplicate,
                                  or a failure in the claim itself.
      (None, claim)            -- the claim is won and committed at
                                  outcome='started'; the caller owns the
                                  obligation to run _complete_claim().

    Everything here is sqlite and string work. No model call, no thread,
    no await. It is safe to run on the turn's own task because it costs
    single-digit milliseconds -- which is the whole point, since the
    truth-pipeline probe cannot file its record until the turn body
    returns.
    """
    started = time.monotonic()
    narrator_id = (narrator_id or "").strip()
    turn_id = (turn_id or "").strip()
    turn_key = (turn_key or "").strip()
    turn_mode = (turn_mode or "").strip()
    ident = {
        "turn_key": turn_key, "turn_id": turn_id,
        "narrator_id": narrator_id, "session_id": session_id or "",
        "turn_mode": turn_mode, "source": source,
    }

    # ── The turn must be the NARRATOR'S ──────────────────────────────
    # WO-EXTRACTION-OWNERSHIP-AND-VRAM-STABILITY-01 Phase 1.
    #
    # ui/js/session-loop.js sends `[SYSTEM: ...]` guidance to Lori as a
    # user-role WebSocket payload. It carries turn_mode='interview' and
    # persists an ordinary `turns` row, so every guard below said yes to
    # it and the extractor was handed an operator instruction to mine
    # for biography. On 2026-07-31 that ran four times in one session
    # and one of them came back
    #
    #     fieldPath="system.message"  value="The narrator has been quiet
    #                                        for a while. Offer a gentle
    #                                        warm invitation..."
    #
    # rejected by EXTRACTABLE_FIELDS -- but only after the model call was
    # paid for, twice, on a GPU the narrator was waiting on.
    #
    # FIRST, ahead of the requested log and every other guard, because
    # the work order requires zero ledger claims for a directive and the
    # claim is taken a few lines below. A directive is not a turn that
    # was declined; it is a turn that was never his.
    #
    # A BOOLEAN, never the text. This service does not inspect
    # transcripts -- the boundary that read the payload already knows the
    # answer and passes it, the same shape trip_placement uses. Giving
    # this module its own opinion about what a directive looks like would
    # create a second definition to drift from the first.
    if is_system_directive:
        out = _outcome_for(ident, "noop", started=started,
                           method="system_directive")
        logger.info("[extract-turn] extract_fields_noop %s", out.as_log_fields())
        return out, None

    logger.info(
        "[extract-turn] extract_fields_requested turn_id=%s turn_key=%s "
        "narrator=%s session=%s mode=%s source=%s",
        turn_id or "-", turn_key or "-", narrator_id or "-",
        session_id or "-", turn_mode or "-", source,
    )

    # ── Guard rails before any claim is taken ────────────────────────
    if not extraction_eligible(turn_mode):
        out = _outcome_for(ident, "noop", started=started,
                           method="ineligible_turn_mode")
        logger.info("[extract-turn] extract_fields_noop %s", out.as_log_fields())
        return out, None

    if not narrator_id or not (user_text or "").strip():
        out = _outcome_for(ident, "noop", started=started,
                           method="missing_narrator_or_text")
        logger.info("[extract-turn] extract_fields_noop %s", out.as_log_fields())
        return out, None

    if not turn_key:
        # No committed row id means no stable key. Phase 2 requires the
        # key to come from the persisted turn, so the correct answer is
        # to decline rather than fall back to hashing the narrator's
        # words -- a text key would collide across legitimately
        # identical answers and would defeat replay detection anyway.
        out = _outcome_for(ident, "noop", started=started,
                           method="no_stable_turn_key")
        logger.warning(
            "[extract-turn] extract_fields_noop %s "
            "(no committed turn row id -- extraction declined rather "
            "than keyed on text)", out.as_log_fields(),
        )
        return out, None

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
        out = _outcome_for(ident, "failed", started=started,
                           error_class=claim_exc.__class__.__name__)
        logger.error(
            "[extract-turn] extract_fields_failed %s (claim stage)",
            out.as_log_fields(),
        )
        return out, None

    if ledger_id is None:
        # Replay, reconnect, or retry of a turn that is already owned.
        out = _outcome_for(ident, "duplicate", started=started,
                           method="already_processed")
        logger.info(
            "[extract-turn] extract_fields_duplicate %s", out.as_log_fields(),
        )
        return out, None

    logger.info(
        "[extract-turn] extract_fields_started turn_id=%s turn_key=%s "
        "narrator=%s ledger_id=%s",
        turn_id or "-", turn_key, narrator_id, ledger_id,
    )

    # THE STAGE MEANS "ASKED", NOT "SUCCEEDED". Until 2026-07-30 this
    # mark lived inside the extractor thread, below the forced-failure
    # seam, so a turn whose extraction was invoked and then failed
    # reported `extract_fields_called=0` --- the exact reading the
    # original defect produced. Gate 7 exists because three identical
    # zeroes meant three different things; an observability stage that
    # cannot tell "never asked" from "asked and failed" reintroduces the
    # confusion it was built to remove. The claim is won and the attempt
    # is about to run, so the stage is true from here on.
    #
    # It is marked HERE, in the inline half, and nowhere else. The probe
    # is scoped to the turn; a mark issued from the completion task
    # would be filed against no turn at all.
    _mark_probe("turn-extraction")

    return None, _Claim(
        ledger_id=int(ledger_id),
        started=started,
        narrator_id=narrator_id,
        turn_id=turn_id,
        turn_key=turn_key,
        session_id=session_id or "",
        turn_mode=turn_mode,
        source=source,
        user_text=user_text or "",
        current_section=current_section,
        current_target_path=current_target_path,
        current_era=current_era,
        current_pass=current_pass,
        current_mode=current_mode,
    )


def _clarifications(resp: Any) -> List[Dict[str, Any]]:
    """The fragile-fact clarification envelope, if the extractor built one.

    WO-STT-LIVE-02 added `clarification_required` to
    ExtractFieldsResponse so a dictated answer touching an identity
    field is confirmed rather than silently written. The browser is what
    surfaces it, so it has to travel with the items rather than be
    recomputed on the far side.
    """
    try:
        raw = getattr(resp, "clarification_required", None) or []
        out: List[Dict[str, Any]] = []
        for c in raw:
            if hasattr(c, "model_dump"):
                out.append(c.model_dump())
            elif hasattr(c, "dict"):
                out.append(c.dict())
            elif isinstance(c, dict):
                out.append(c)
        return out
    except Exception:
        # A missing or odd envelope costs the clarification prompt, not
        # the extraction.
        return []


def _store_result(
    claim: _Claim,
    items: List[Dict[str, Any]],
    clarification_required: List[Dict[str, Any]],
    method: str,
) -> None:
    """Persist an applicable result. Never raises.

    IDENTITY IS BOUND HERE, FROM THE CLAIM -- not read from whoever is
    active when the result is eventually applied. An operator can switch
    narrator while extraction is running, and a result that learned its
    owner at delivery time would attach one man's biography to whoever
    happened to be on screen.

    A storage failure costs catch-up, never the turn: the caller is a
    turn the narrator already watched complete.
    """
    if not items:
        return
    try:
        from .. import db as _db
        _db.turn_extraction_result_store(
            narrator_id=claim.narrator_id,
            turn_key=claim.turn_key,
            turn_id=claim.turn_id,
            session_id=claim.session_id,
            status="succeeded",
            method=method or "",
            items=items,
            clarification_required=clarification_required,
            ledger_id=claim.ledger_id,
        )
    except Exception as store_exc:
        logger.error(
            "[extract-turn] result store failed turn_key=%s err=%s "
            "(extraction succeeded; the browser will not get a catch-up "
            "copy of this one)",
            claim.turn_key, store_exc.__class__.__name__,
        )


async def _complete_claim(claim: _Claim) -> ExtractionOutcome:
    """Trace-finalized wrapper around the extractor.

    ── WHY THIS WRAPPER AND NOT extract_completed_turn ──────────────
    The previous correction wrapped `extract_completed_turn`. The
    WebSocket path does not call it: chat_ws calls
    `schedule_completed_turn_extraction`, which runs `_complete_claim`
    on a task. So the finalizer never fired, every trace stayed parked,
    and the sweep only runs inside a later `park()` after 180s — the
    20260831T152542Z run lasted 182s with its last park at 119s of age,
    so the sweep never fired either and all fifteen traces died in
    memory. Wrapping HERE covers both entry points, because both end up
    in this function.
    """
    _tk = str(getattr(claim, "turn_key", "") or "")
    try:
        out = await _complete_claim_inner(claim)
    except BaseException as exc:            # includes CancelledError
        _finalize_extraction_trace(
            _tk, "exception", error_class=type(exc).__name__,
            detail={"why": "extractor raised; no outcome produced"})
        raise
    try:
        _finalize_extraction_trace(
            _tk or getattr(out, "turn_key", ""),
            getattr(out, "status", "unknown"),
            item_count=getattr(out, "item_count", 0),
            method=getattr(out, "method", "") or "",
            error_class=getattr(out, "error_class", "") or "")
    except Exception:
        pass
    return out


async def _complete_claim_inner(claim: _Claim) -> ExtractionOutcome:
    """The working half: run the extractor, close the ledger row.

    NEVER RAISES except asyncio.CancelledError, which is recorded as
    failed/CancelledError and then re-raised so asyncio's cancellation
    contract stays intact. Every other path -- a broken database, a
    missing extractor, a hung LLM -- returns an ExtractionOutcome.

    Writes NO family truth and touches NO projection. Both boundaries
    are Phase 1 findings that Phase 2 preserved on purpose.
    """
    ident = {
        "turn_key": claim.turn_key, "turn_id": claim.turn_id,
        "narrator_id": claim.narrator_id, "session_id": claim.session_id,
        "turn_mode": claim.turn_mode, "source": claim.source,
    }
    ledger_id = claim.ledger_id
    started = claim.started

    def _run_sync() -> Any:
        """Body executed off the event loop. Builds the request, extracts."""
        forced = forced_failure_mode()
        if forced == "raise":
            raise ForcedExtractionFailure(
                "HORNELORE_EXTRACTION_FORCE_FAILURE=raise "
                "(Gate 7 Phase 2 live Test C seam)"
            )
        if forced == "timeout":
            time.sleep(EXTRACTION_TIMEOUT_S + 30.0)
        req = build_extraction_request(
            narrator_id=claim.narrator_id,
            user_text=claim.user_text,
            session_id=claim.session_id or None,
            current_section=claim.current_section,
            current_target_path=claim.current_target_path,
            current_era=claim.current_era,
            current_pass=claim.current_pass,
            current_mode=claim.current_mode,
        )
        return _call_extractor(req)

    try:
        resp = await asyncio.wait_for(
            asyncio.to_thread(_run_sync), timeout=EXTRACTION_TIMEOUT_S,
        )
    except asyncio.CancelledError:
        # Shutdown drain, or a caller that cancelled us. Record it, then
        # honour the cancellation contract -- an abandoned attempt
        # leaves a closed row behind rather than a row stuck at
        # 'started' that nobody can explain later.
        out = _outcome_for(ident, "failed", started=started,
                           error_class="CancelledError", ledger_id=ledger_id)
        _finish_ledger(ledger_id, "failed", error_class="CancelledError",
                       duration_ms=out.duration_ms)
        logger.warning(
            "[extract-turn] extract_fields_failed %s (extraction cancelled; "
            "the narrator's turn was delivered and persisted regardless)",
            out.as_log_fields(),
        )
        raise
    except asyncio.TimeoutError:
        out = _outcome_for(ident, "failed", started=started,
                           error_class="TimeoutError", ledger_id=ledger_id)
        _finish_ledger(ledger_id, "failed", error_class="TimeoutError",
                       duration_ms=out.duration_ms)
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
        out = _outcome_for(ident, "failed", started=started,
                           error_class=exc.__class__.__name__,
                           ledger_id=ledger_id)
        _finish_ledger(ledger_id, "failed", error_class=exc.__class__.__name__,
                       duration_ms=out.duration_ms)
        logger.error(
            "[extract-turn] extract_fields_failed %s", out.as_log_fields(),
        )
        return out

    # ── Interpret the result ─────────────────────────────────────────
    items: List[Dict[str, Any]] = []
    method = ""
    _raw_count = 0
    try:
        raw_items = getattr(resp, "items", None) or []
        _raw_count = len(raw_items)
        method = str(getattr(resp, "method", "") or "")
        for it in raw_items:
            if hasattr(it, "model_dump"):
                items.append(it.model_dump())
            elif hasattr(it, "dict"):
                items.append(it.dict())
            elif isinstance(it, dict):
                items.append(it)
            # Anything else falls through and is COUNTED as dropped
            # below. It used to fall through silently, which meant an
            # extractor returning three unusable objects reported
            # "found nothing" -- indistinguishable from a narrator turn
            # with no facts in it. Those are different events and the
            # operator surfaces built on this cannot tell them apart
            # afterwards.
    except Exception as shape_exc:
        # The extractor returned something unexpected. That is a failure
        # of this integration, not of the turn.
        out = _outcome_for(ident, "failed", started=started,
                           error_class=shape_exc.__class__.__name__,
                           ledger_id=ledger_id)
        _finish_ledger(ledger_id, "failed",
                       error_class=shape_exc.__class__.__name__,
                       duration_ms=out.duration_ms)
        logger.error(
            "[extract-turn] extract_fields_failed %s (result shape)",
            out.as_log_fields(),
        )
        return out

    # ── The payload must be the shape the browser is promised ────────
    # WO-EXTRACTION-OWNERSHIP-AND-VRAM-STABILITY-01 Phase 2.
    #
    # Until Phase 2 this result went straight into the HTTP response and
    # the browser dealt with whatever arrived. It now becomes a durable
    # row AND a WebSocket frame, so a malformed payload would be stored,
    # replayed on every reconnect, and handed to Projection Sync -- a
    # bad shape that persists is worse than one that fails once.
    #
    # A malformed result is a FAILURE, not a smaller success. Silently
    # dropping the bad items and delivering the rest would write a
    # partial biography and report it as complete.
    _clar = _clarifications(resp)
    _dropped = _raw_count - len(items)
    if _dropped > 0 or not isinstance(items, list) \
            or not all(isinstance(i, dict) for i in items) \
            or not isinstance(_clar, list):
        out = _outcome_for(ident, "failed", started=started,
                           error_class="MalformedExtractionPayload",
                           ledger_id=ledger_id)
        _finish_ledger(ledger_id, "failed",
                       error_class="MalformedExtractionPayload",
                       duration_ms=out.duration_ms)
        logger.error(
            "[extract-turn] extract_fields_failed %s (payload shape: "
            "raw=%d usable=%d dropped=%d clarifications=%s -- nothing "
            "stored, nothing sent)",
            out.as_log_fields(), _raw_count, len(items), _dropped,
            type(_clar).__name__,
        )
        return out

    if not items:
        # Ran cleanly, found nothing. A narrator can say something with
        # no extractable field in it; that is not an error.
        out = _outcome_for(ident, "noop", started=started,
                           method=method or "no_items", ledger_id=ledger_id)
        _finish_ledger(ledger_id, "noop", item_count=0,
                       method=method or "no_items", duration_ms=out.duration_ms)
        logger.info("[extract-turn] extract_fields_noop %s", out.as_log_fields())
        return out

    out = _outcome_for(ident, "succeeded", started=started,
                       item_count=len(items), method=method,
                       ledger_id=ledger_id, items=items)
    _finish_ledger(ledger_id, "succeeded", item_count=len(items),
                   method=method, duration_ms=out.duration_ms)

    # DURABLE BEFORE DELIVERABLE. The browser still owns projection,
    # Shadow Review, repeatable grouping and fragile-fact clarification,
    # so this result has to cross a process boundary to be of any use --
    # and the narrator can close the tab, reload, lose the socket or
    # switch narrator while the extraction that produced it was still
    # running. A result that exists only inside a WebSocket frame is a
    # result those four ordinary things destroy.
    #
    # Stored here, before any send is attempted, so that a send which
    # never lands costs a round trip rather than the extraction.
    _store_result(claim, items, _clar, method)

    logger.info("[extract-turn] extract_fields_succeeded %s", out.as_log_fields())
    await _offer_result(claim, out, _clar)
    return out


# ── WO-LORI-LISTEN-AND-RETAIN-01 · retention attachment ──────────────
# Extraction runs as a background task after the response is persisted,
# so this is where the retention half of the trace is written. The hook
# knows the turn ROW, not the trace id, which is why the trace is parked
# under both. Observation only: it reads the outcome that already
# exists and never alters extraction.
try:
    from . import lori_response_trace as _rt
except Exception:  # pragma: no cover - defensive
    _rt = None  # type: ignore


def _finalize_extraction_trace(turn_key, status, *, item_count=0,
                               method="", error_class="", detail=None):
    """THE single funnel. Every terminal extraction outcome ends here.

    The previous version was called from two places — success and one
    noop — so malformed results, exceptions, the cancellation path, the
    ceiling timeout and the claim-stage failures all returned without
    attaching anything. Those traces stayed parked, and sweeping only
    happens on a later `park()` after 180s while the harness waits
    four, so the last failed turn of a run could never appear at all.

    Now: success with items is `persisted`; a clean run that found
    nothing is `measured_absent` (the source WAS queried, so it is a
    real negative); anything else — failure, malformed shape, timeout,
    cancellation, exception — is `measurement_failed`, which is NOT
    evidence that the narrator's information was absent.
    """
    if _rt is None:
        return
    try:
        key = str(turn_key or "")
        if not key:
            return
        n = int(item_count or 0)
        if status == "succeeded" and n > 0:
            result = _rt.RESULT_PERSISTED
        elif status in ("succeeded", "noop"):
            result = _rt.RESULT_MEASURED_ABSENT
        else:
            result = _rt.RESULT_MEASUREMENT_FAILED
        payload = {"status": status, "items": n, "method": method,
                   "error_class": error_class, "turn_key": key}
        if detail:
            payload.update(detail)
        _rt.attach(key, "extraction", result, detail=payload)
        _rt.close(key)
    except Exception:
        return


async def _offer_result(
    claim: _Claim,
    out: ExtractionOutcome,
    clarification_required: List[Dict[str, Any]],
) -> None:
    """Hand the finished result to whoever asked to be told. Never raises.

    Runs AFTER the durable write and AFTER the ledger close, so a
    browser that vanished mid-send costs a round trip and nothing else --
    the row is already sitting in the outbox for catch-up.

    Delivery is stamped only if the callback returns without raising,
    and `delivered_at` is explicitly NOT the end of the obligation:
    a frame leaving this process says nothing about a browser that was
    closing as it arrived. Only the browser's acknowledgment sets
    applied_at.
    """
    cb = claim.on_result
    if cb is None:
        return
    try:
        # The claim's OWN text travels with the result. The browser needs
        # it to show Shadow Review what these claims came from, and the
        # only other source it has is "whatever was typed most recently"
        # -- which is a different turn whenever two extractions finish
        # out of order. Turn B's words beside Turn A's extracted fields
        # is a quiet mis-attribution in the one surface an operator uses
        # to check attribution.
        #
        # Carried on the FRAME, not stored in the result table: the work
        # order forbids duplicating the transcript for convenience, and
        # `turns` already holds it.
        await cb(out, clarification_required, claim.user_text)
    except asyncio.CancelledError:
        raise
    except Exception as send_exc:
        logger.info(
            "[extract-turn] result not delivered live turn_key=%s err=%s "
            "(durable copy stands; the browser will catch up)",
            claim.turn_key, send_exc.__class__.__name__,
        )
        return
    try:
        from .. import db as _db
        _db.turn_extraction_result_mark_delivered(
            claim.narrator_id, claim.turn_key)
    except Exception:
        # Losing the delivered stamp costs one redundant re-offer on
        # reconnect, which the browser deduplicates by turn_key anyway.
        pass


def begin_completed_turn_extraction(
    *,
    narrator_id: str,
    turn_id: str,
    user_text: str,
    session_id: Optional[str] = None,
    turn_key: str = "",
    turn_mode: str = "interview",
    source: str = _SOURCE_CHAT_WS,
    current_section: Optional[str] = None,
    current_target_path: Optional[str] = None,
    current_era: Optional[str] = None,
    current_pass: Optional[str] = None,
    current_mode: Optional[str] = None,
    # WO-EXTRACTION-OWNERSHIP-AND-VRAM-STABILITY-01 Phase 1. Decided at
    # the request boundary and passed as a boolean; see _begin().
    is_system_directive: bool = False,
) -> Tuple[Optional[ExtractionOutcome], Optional[_Claim]]:
    """Public name for the inline half. See _begin()."""
    return _begin(
        narrator_id=narrator_id, turn_id=turn_id, user_text=user_text,
        session_id=session_id, turn_key=turn_key, turn_mode=turn_mode,
        source=source, current_section=current_section,
        current_target_path=current_target_path, current_era=current_era,
        current_pass=current_pass, current_mode=current_mode,
        is_system_directive=is_system_directive,
    )


def _on_extraction_task_done(task: "asyncio.Task[Any]") -> None:
    """Release the strong reference and account for anything unexpected.

    _complete_claim() only ever propagates CancelledError, and the
    cancelled path has already written its ledger row by the time we get
    here. Anything else arriving in this callback is a bug in this
    module, so it is logged loudly rather than swallowed into the
    "Task exception was never retrieved" void.
    """
    _PENDING_EXTRACTIONS.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error(
            "[extract-turn] completion task ended on an unexpected "
            "exception class=%s (the narrator's turn was unaffected)",
            exc.__class__.__name__,
        )


def schedule_completed_turn_extraction(
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
    # WO-EXTRACTION-OWNERSHIP-AND-VRAM-STABILITY-01 Phase 1. Decided at
    # the request boundary and passed as a boolean; see _begin().
    is_system_directive: bool = False,
    # Phase 2. Awaited once with (outcome, clarification_required) after
    # the result is durable. Optional: a caller with no live socket --
    # the replay path, the suite -- simply does not pass one.
    on_result: Optional[Any] = None,
) -> ExtractionOutcome:
    """The chat_ws entry point. Claim inline, extract on a held task.

    NEVER RAISES, never awaits, and never blocks the turn. Returns a
    terminal outcome when there was nothing to run, or status
    'scheduled' when the claim was won and the completion task is
    registered.

    Preconditions the CALLER must satisfy before calling:
      * the raw turn has been committed
      * the required archive event has been written
      * the user-facing response has already been sent

    `assistant_text` is accepted for symmetry with
    extract_completed_turn() and for future two-sided extraction; it is
    NOT fed to the extractor today (see build_extraction_request).
    """
    outcome, claim = _begin(
        narrator_id=narrator_id, turn_id=turn_id, user_text=user_text,
        session_id=session_id, turn_key=turn_key, turn_mode=turn_mode,
        source=source, current_section=current_section,
        current_target_path=current_target_path, current_era=current_era,
        current_pass=current_pass, current_mode=current_mode,
        is_system_directive=is_system_directive,
    )
    if claim is None:
        return outcome  # type: ignore[return-value]

    # Attached after the claim is won rather than threaded through
    # _begin(): the inline half decides whether there is work, and only
    # then does it matter who wants telling about it.
    claim.on_result = on_result

    ident = {
        "turn_key": claim.turn_key, "turn_id": claim.turn_id,
        "narrator_id": claim.narrator_id, "session_id": claim.session_id,
        "turn_mode": claim.turn_mode, "source": claim.source,
    }
    try:
        task = asyncio.get_running_loop().create_task(
            _complete_claim(claim),
            name=f"extract-turn:{claim.narrator_id}:{claim.turn_key}",
        )
    except RuntimeError as loop_exc:
        # No running loop. This entry point is for the async turn path;
        # a caller without a loop wants extract_completed_turn(). The
        # claim is already committed, so close its row rather than
        # abandon it at 'started'.
        out = _outcome_for(ident, "failed", started=claim.started,
                           error_class=loop_exc.__class__.__name__,
                           ledger_id=claim.ledger_id)
        _finish_ledger(claim.ledger_id, "failed",
                       error_class=loop_exc.__class__.__name__,
                       duration_ms=out.duration_ms)
        logger.error(
            "[extract-turn] extract_fields_failed %s (no running event loop "
            "-- use extract_completed_turn() from synchronous callers)",
            out.as_log_fields(),
        )
        return out

    _PENDING_EXTRACTIONS.add(task)
    task.add_done_callback(_on_extraction_task_done)
    return _outcome_for(ident, "scheduled", started=claim.started,
                        method="background_task", ledger_id=claim.ledger_id)


async def _extract_completed_turn_inner(
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
    # WO-EXTRACTION-OWNERSHIP-AND-VRAM-STABILITY-01 Phase 1. Decided at
    # the request boundary and passed as a boolean; see _begin().
    is_system_directive: bool = False,
) -> ExtractionOutcome:
    """Request field extraction for one completed turn and await it.

    Begin-then-complete in a single await. The replay path and the
    automated suite use this because they want the terminal outcome in
    hand; chat_ws uses schedule_completed_turn_extraction() instead,
    because a turn task can be cancelled the instant its socket closes.

    NEVER RAISES except asyncio.CancelledError, which is recorded and
    then re-raised so cancellation semantics stay intact.

    Preconditions the CALLER must satisfy before calling:
      * the raw turn has been committed
      * the required archive event has been written
      * the user-facing response has already been sent

    Writes NO family truth and touches NO projection.

    `assistant_text` is accepted for outcome logging and future
    two-sided extraction; it is NOT fed to the extractor today (see
    build_extraction_request).
    """
    outcome, claim = _begin(
        narrator_id=narrator_id, turn_id=turn_id, user_text=user_text,
        session_id=session_id, turn_key=turn_key, turn_mode=turn_mode,
        source=source, current_section=current_section,
        current_target_path=current_target_path, current_era=current_era,
        current_pass=current_pass, current_mode=current_mode,
        is_system_directive=is_system_directive,
    )
    if claim is None:
        return outcome  # type: ignore[return-value]
    return await _complete_claim(claim)


# ── Shutdown ─────────────────────────────────────────────────────────────
def pending_extraction_count() -> int:
    """How many completion tasks are in flight right now."""
    return len(_PENDING_EXTRACTIONS)


async def drain_pending_extractions(
    timeout: float = EXTRACTION_DRAIN_TIMEOUT_S,
) -> Dict[str, Any]:
    """Let in-flight extractions finish, then cancel whatever is left.

    Wired to the application's shutdown event. This is the half of Phase
    2 Step 4 that makes the completion task not-fragile: "Do not
    introduce a fragile detached task that can silently disappear on
    process shutdown without recording its state."

    Every task here already has a committed ledger row at
    outcome='started'. Tasks that finish within the ceiling close their
    own rows normally. Tasks that do not are cancelled, and the
    CancelledError handler in _complete_claim() writes
    failed/CancelledError before re-raising. Either way no attempt
    vanishes without a record.

    Never raises. A shutdown path that can throw is a shutdown path that
    leaves the process wedged.
    """
    pending = [t for t in _PENDING_EXTRACTIONS if not t.done()]
    report: Dict[str, Any] = {
        "pending_at_shutdown": len(pending),
        "finished_within_timeout": 0,
        "cancelled": 0,
        "timeout_s": timeout,
    }
    if not pending:
        logger.info("[extract-turn] shutdown drain: nothing in flight")
        return report
    logger.info(
        "[extract-turn] shutdown drain: waiting up to %.0fs for %d "
        "in-flight extraction(s)", timeout, len(pending),
    )
    try:
        done, still_running = await asyncio.wait(pending, timeout=timeout)
    except Exception as wait_exc:
        logger.error("[extract-turn] shutdown drain wait failed err=%s",
                     wait_exc.__class__.__name__)
        return report
    report["finished_within_timeout"] = len(done)
    report["cancelled"] = len(still_running)
    for task in still_running:
        task.cancel()
    if still_running:
        # Give each cancelled task the chance to write its ledger row on
        # the way out. return_exceptions=True because every one of them
        # is expected to raise CancelledError.
        try:
            await asyncio.gather(*still_running, return_exceptions=True)
        except Exception as gather_exc:
            logger.error("[extract-turn] shutdown drain gather failed err=%s",
                         gather_exc.__class__.__name__)
    logger.info(
        "[extract-turn] shutdown drain complete: %d finished, %d cancelled "
        "(every cancelled attempt closed its ledger row as "
        "failed/CancelledError)",
        report["finished_within_timeout"], report["cancelled"],
    )
    return report


async def extract_completed_turn(**kwargs) -> ExtractionOutcome:
    """Public entry point. Guarantees the trace is finalized exactly once.

    Wrapping here rather than patching each `return` is deliberate: the
    inner function has more than a dozen terminal paths, and two of them
    (`asyncio.CancelledError` and an unexpected exception) do not return
    at all. A wrapper is the only place that covers every one.
    """
    turn_key = str(kwargs.get("turn_key") or "")
    # Finalization lives in `_complete_claim`, which BOTH entry points
    # reach. Only the paths that return before ever claiming need
    # covering here — those never run the extractor at all.
    try:
        out = await _extract_completed_turn_inner(**kwargs)
    except BaseException as exc:            # includes CancelledError
        _finalize_extraction_trace(
            turn_key, "exception", error_class=type(exc).__name__,
            detail={"why": "extraction raised before or outside a claim"})
        raise
    if getattr(out, "status", "") in ("noop", "failed") and turn_key:
        _finalize_extraction_trace(
            turn_key, getattr(out, "status", "unknown"),
            item_count=getattr(out, "item_count", 0),
            method=getattr(out, "method", "") or "",
            error_class=getattr(out, "error_class", "") or "",
            detail={"why": "terminal before the claim stage"})
    return out
