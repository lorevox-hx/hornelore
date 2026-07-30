"""WO-LIVE-TRIP-COMPANION-01 Vertical Slice 1 --- the trip placement service.

=======================================================================
  THE GOVERNING RULE

    Link a completed turn to the trip and the day it happened on.
    Do NOT copy the turn into the trip.
=======================================================================

WHAT THIS CLOSES
----------------
Two subsystems worked and were never joined. Lori persisted interview
turns to `turns`, wrote archive events, and (since Gate 7 Phase 2)
dispatched field extraction. The travel-document system held trips,
generated trip days, imported and placed photographs. Nothing connected
a conversation to a day.

The only notion of "the trip Lori is working on" was
`runtime71.active_trip_id`, which is `state.session.activeTripId` in
ui/js/travels-shelf.js, forwarded by ui/js/app.js. That is a browser
fact. It does not survive a page reload and it does not survive a server
restart, so it cannot be the thing a persisted link is built from. This
service resolves the trip and the day from the DATABASE, every time.

WHAT A LINK IS, AND WHAT IT IS NOT
----------------------------------
A row in `trip_turn_links` carries identifiers only: which trip, which
day, which conversation, which two rows in `turns`, when, how the
placement was decided, and whether a human confirmed it. It carries no
narrative text. There is exactly one conversation store and it is
`turns`. The timeline reads the words back out of `turns` by row id, so
an edited or removed turn changes the timeline automatically, because
the timeline never held a copy.

THE FOUR PROPERTIES, AND WHERE EACH LIVES
-----------------------------------------
SHARED     -- link_completed_turn() is the single implementation.
              chat_ws calls it after a turn completes; the operator
              routes in routers/trips.py call the same repository
              primitives underneath it. There is no second placement
              path and no placement logic inside chat_ws.

IDEMPOTENT -- trip_repository.trip_turn_link_claim() INSERTs against
              the UNIQUE INDEX ux_trip_turn_links_assistant_row. The
              database decides who wins. The key is the committed
              assistant row id -- the same key Gate 7's extraction
              ledger uses -- so a turn's extraction record and its trip
              placement can never disagree about which turn they mean.
              Linking the same completed turn twice produces exactly
              one row and reports 'duplicate'. A duplicate never
              overwrites an existing placement: if an operator has
              moved a conversation to another day, a replayed turn must
              not drag it back.

OBSERVABLE -- five events in PLACEMENT_EVENTS, one vocabulary.
              Identifiers, counts, and classifications only. The
              narrator's words are never logged here and never stored
              in the link table. A turn that arrives with an active
              trip but no chosen day is NOT dropped -- it is linked at
              placement_status='needs_day', which is the observable
              reconciliation item the work order requires: "A failure
              to link the trip should not lose the conversation. It
              should leave an observable reconciliation item."

FAILURE-   -- link_completed_turn() cannot raise. Every exit path
ISOLATED      returns a PlacementOutcome, including the catastrophic
              one. It runs after the turn has persisted, after the
              archive event has persisted, and after the browser has
              its `done` frame, so no failure here can roll back a
              turn, roll back an archive event, terminate the socket,
              replace the assistant reply, or leave the browser
              waiting. Losing a link costs a timeline entry. It must
              never cost a conversation.

WHY THIS IS INLINE AND NOT A HELD TASK
--------------------------------------
Gate 7 Phase 2 had to move field extraction onto a held task because
the extractor makes a model call and the socket closes the moment
`done` arrives -- every awaited extraction died at ~830ms with
CancelledError. Placement is different in kind: three small SQLite
statements against a local file, single-digit milliseconds, no network
and no model. It runs inline on the turn's own task, inside the turn's
probe window, for the same reason the extraction CLAIM stayed inline --
the record must belong to the turn that caused it. If placement ever
grows a remote call, it moves to the held-task shape and this paragraph
gets corrected in place with the date it stopped being true.

WHAT THIS SERVICE NEVER DOES
----------------------------
It does not write family truth. It does not call ft_add_note,
ft_add_row, or any other family-truth writer. It does not call
projection_writer.apply_correction and it does not touch correction
behaviour in any way. Gate 7 Phase 1 measured both of those boundaries
and proved the zeroes were correct by design -- family truth is
operator-gated behind POST /api/family-truth/*, projections are
reachable only from the `turn_mode == "correction"` branch in chat_ws.
Placing a conversation on a calendar day is not a claim about a family.
The work order says it directly: "no family-truth write caused by
linking; no change to correction projection behavior."

It also does not decide that a date is an operator's choice. A day
resolved from the trip's own remembered selection is 'confirmed'
because a human chose it. A day inferred from a timestamp would be
'suggested' -- the travel-document rule that a date suggestion is not
an operator choice applies to conversations exactly as it applies to
photographs. Vertical Slice 1 only ever produces the first kind; the
suggestion path exists in the repository and is not wired here yet.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── The five-outcome observability vocabulary ────────────────────────────
# Fixed by Vertical Slice 1. A new event means moving the work order and
# the runtime-architecture doc forward first, not appending here quietly.
PLACEMENT_EVENTS: tuple = (
    "trip_link_requested",
    "trip_link_linked",
    "trip_link_noop",
    "trip_link_duplicate",
    "trip_link_failed",
)

# Statuses a PlacementOutcome can carry. All five are terminal.
#
#   linked    -- a new row exists, on a day, confirmed
#   needs_day -- a new row exists, on the trip, with no day yet.
#                THIS IS A SUCCESS. The conversation is attached to the
#                trip and visible in the reconciliation list; only its
#                day is unanswered.
#   duplicate -- this turn was already placed; nothing changed
#   noop      -- correctly skipped (no active trip, ineligible mode,
#                no committed row id). The overwhelming majority of
#                turns in normal family interviewing land here.
#   failed    -- something broke. The turn is untouched.
PLACEMENT_STATUSES: tuple = (
    "linked",
    "needs_day",
    "duplicate",
    "noop",
    "failed",
)

# Which turn modes are eligible for trip placement.
#
# Vertical Slice 1's acceptance path is "complete a normal interview
# turn", so `interview` is the whole set. The deterministic
# short-circuit modes are deliberately excluded: floor_hold is the
# narrator saying "let me think", meta_question is a question about the
# interview rather than a moment in the trip, and `correction` must stay
# out for the same reason it stays out of extraction -- it has its own
# guarded projection path and this slice was told not to change
# correction behaviour. Widening this set is a later-phase decision with
# a visible cost: every mode added here puts more rows on the operator's
# timeline.
PLACEMENT_ELIGIBLE_TURN_MODES: frozenset = frozenset({"interview"})

_SOURCE_CHAT_WS = "chat_ws"


@dataclass
class PlacementOutcome:
    """What happened when a completed turn asked to be placed on a trip.

    Never an exception. Every entry point returns one of these on every
    path including catastrophic failure, because the caller is a turn
    that has already succeeded from the narrator's point of view and
    must not be disturbed.
    """

    status: str                        # one of PLACEMENT_STATUSES
    reason: str = ""                   # why, for noop/failed; short slug
    trip_id: str = ""
    trip_day_id: str = ""
    link_id: str = ""
    conv_id: str = ""
    narrator_id: str = ""
    turn_id: str = ""
    turn_mode: str = ""
    source: str = ""
    assistant_turn_row_id: Optional[int] = None
    user_turn_row_id: Optional[int] = None
    placement_source: str = ""
    placement_status: str = ""
    error_class: str = ""              # class name only -- never a message
    duration_ms: int = 0

    @property
    def ok(self) -> bool:
        """True when placement ran or was correctly skipped."""
        return self.status in ("linked", "needs_day", "duplicate", "noop")

    @property
    def linked(self) -> bool:
        """True when a link row now exists for this turn."""
        return self.status in ("linked", "needs_day", "duplicate")

    @property
    def event(self) -> str:
        """The PLACEMENT_EVENTS name for this outcome."""
        if self.status in ("linked", "needs_day"):
            return "trip_link_linked"
        if self.status == "duplicate":
            return "trip_link_duplicate"
        if self.status == "failed":
            return "trip_link_failed"
        return "trip_link_noop"

    def as_log_fields(self) -> str:
        """Identifier/classification summary. No narrative text, ever."""
        return (
            f"event={self.event} "
            f"outcome={self.status} "
            f"reason={self.reason or '-'} "
            f"trip={self.trip_id or '-'} "
            f"day={self.trip_day_id or '-'} "
            f"link={self.link_id or '-'} "
            f"conv={self.conv_id or '-'} "
            f"narrator={self.narrator_id or '-'} "
            f"turn_id={self.turn_id or '-'} "
            f"mode={self.turn_mode or '-'} "
            f"source={self.source or '-'} "
            f"arow={self.assistant_turn_row_id if self.assistant_turn_row_id else '-'} "
            f"urow={self.user_turn_row_id if self.user_turn_row_id else '-'} "
            f"placement={self.placement_source or '-'}/{self.placement_status or '-'} "
            f"error={self.error_class or '-'} "
            f"duration_ms={self.duration_ms}"
        )


# ── The test seam ────────────────────────────────────────────────────────
class ForcedPlacementFailure(RuntimeError):
    """Raised only by the acceptance seam. Never raised in production."""


def forced_failure_armed() -> bool:
    """True when the placement forced-failure seam is live in THIS process.

    Vertical Slice 1 requires proving that "a failure to link the trip
    should not lose the conversation." The only honest way to show that
    live is to make linking fail on purpose while a real turn runs --
    and the standing rule is "do not corrupt production configuration to
    create this failure." So the failure has its own harness-only
    environment switch, exactly like the Gate 7 extraction seam, and the
    operator harness health route reports its state as a boolean.

    That boolean matters: the first Gate 7 live run was voided because
    the seam was set in a shell that never reached the server process.
    Reading the flag from the server itself closes that hole.

    Default OFF. Must be unset again after a verification run.
    """
    return bool((os.environ.get("HORNELORE_TRIP_LINK_FORCE_FAILURE") or "").strip())


def placement_eligible(turn_mode: Optional[str]) -> bool:
    """True when this turn mode may be placed on a trip timeline."""
    return str(turn_mode or "").strip() in PLACEMENT_ELIGIBLE_TURN_MODES


def resolve_placement(narrator_id: str) -> Dict[str, Any]:
    """Answer 'which trip and which day is this narrator living in?'

    Reads the DATABASE, not the browser. `runtime71.active_trip_id` is
    deliberately not consulted anywhere in this module: it is a
    client-side value that dies on reload and on restart, and the whole
    point of Vertical Slice 1 is that reopening the trip after a restart
    shows the same linked timeline event.

    Returns ``{"trip": {...}|None, "day": {...}|None, "reason": str}``.
    Never raises: an unreadable trip lane must degrade to "no active
    trip", because an interview turn must not fail because the travel
    subsystem is having a bad day.
    """
    out: Dict[str, Any] = {"trip": None, "day": None, "reason": ""}
    nid = str(narrator_id or "").strip()
    if not nid:
        out["reason"] = "no_narrator"
        return out
    try:
        from . import trip_repository as _tr
    except Exception:
        out["reason"] = "trip_repository_unavailable"
        return out

    try:
        trip = _tr.trip_active_get(nid)
    except Exception:
        # trip_active_get already swallows sqlite errors; this is the
        # second wall, for an import-time or programming failure.
        out["reason"] = "trip_lookup_failed"
        return out

    if not trip:
        out["reason"] = "no_active_trip"
        return out
    out["trip"] = trip

    day_id = str(trip.get("active_trip_day_id") or "").strip()
    if not day_id:
        out["reason"] = "no_selected_day"
        return out

    try:
        day = _tr.trip_day_get(day_id)
    except Exception:
        # The existing trip_day_get deliberately lets operational
        # errors bubble (2026-07-23) so routers can classify them.
        # Here the correct classification is "we still link the turn to
        # the trip, we just cannot name the day yet."
        out["reason"] = "day_lookup_failed"
        return out

    if not day or str(day.get("trip_id") or "") != str(trip.get("id") or ""):
        # A selected day that has been deleted or re-parented. Link to
        # the trip and let reconciliation ask a human.
        out["reason"] = "selected_day_missing"
        return out

    out["day"] = day
    return out


def link_completed_turn(
    narrator_id: str,
    assistant_turn_row_id: Optional[int],
    conv_id: str = "",
    turn_id: str = "",
    turn_mode: str = "",
    user_turn_row_id: Optional[int] = None,
    captured_at: str = "",
    source: str = _SOURCE_CHAT_WS,
) -> PlacementOutcome:
    """Place one completed, persisted turn on the narrator's active trip.

    THE ONE ENTRY POINT. chat_ws calls this and nothing else.

    Preconditions, all checked here rather than assumed:
      * an eligible turn mode
      * a committed assistant row id -- the idempotency key. Without a
        persisted row there is nothing stable to key on and nothing
        for the timeline to read text back out of, so the answer is
        noop, not a guess.
      * an active trip for this narrator, in the database

    Outcomes, in the order they are decided:
      noop      -- ineligible mode, no narrator, no committed row, or
                   no active trip. Normal. Most turns are this.
      needs_day -- active trip, no usable day. Linked anyway, flagged
                   for reconciliation. The conversation is NOT lost.
      linked    -- active trip and a day the operator chose. Recorded
                   placement_source='active_trip_day',
                   placement_status='confirmed'.
      duplicate -- already placed. Nothing written, nothing overwritten.
      failed    -- something broke. Nothing about the turn changed.

    Cannot raise.
    """
    started = time.time()
    mode = str(turn_mode or "").strip()
    nid = str(narrator_id or "").strip()
    cid = str(conv_id or "")

    def _out(status: str, **kw: Any) -> PlacementOutcome:
        return PlacementOutcome(
            status=status,
            conv_id=cid,
            narrator_id=nid,
            turn_id=str(turn_id or ""),
            turn_mode=mode,
            source=str(source or ""),
            assistant_turn_row_id=assistant_turn_row_id,
            user_turn_row_id=user_turn_row_id,
            duration_ms=int((time.time() - started) * 1000),
            **kw,
        )

    try:
        if not placement_eligible(mode):
            return _out("noop", reason="ineligible_turn_mode")
        if not nid:
            return _out("noop", reason="no_narrator")

        try:
            arow = int(assistant_turn_row_id or 0)
        except (TypeError, ValueError):
            arow = 0
        if arow <= 0:
            return _out("noop", reason="no_committed_turn_row")

        resolved = resolve_placement(nid)
        trip = resolved.get("trip")
        if not trip:
            return _out("noop", reason=resolved.get("reason") or "no_active_trip")

        trip_id = str(trip.get("id") or "")
        day = resolved.get("day")
        day_id = str((day or {}).get("id") or "")

        if forced_failure_armed():
            # Harness-only. Proves the required property live: the turn
            # is already persisted and delivered, so this raises into
            # the except below, records 'failed', and costs a timeline
            # entry rather than a conversation.
            raise ForcedPlacementFailure("placement seam armed")

        from . import trip_repository as _tr

        claim = _tr.trip_turn_link_claim(
            trip_id=trip_id,
            assistant_turn_row_id=arow,
            trip_day_id=day_id or None,
            user_turn_row_id=user_turn_row_id,
            conv_id=cid,
            captured_at=str(captured_at or ""),
            # A day the operator selected on the trip IS an operator
            # choice, so this is 'confirmed', not 'suggested'. Nothing
            # in this slice infers a day from a timestamp.
            placement_source="active_trip_day",
            placement_status="confirmed" if day_id else "needs_day",
        )

        link = claim.get("link") or {}
        outcome = str(claim.get("outcome") or "")
        placed_day = str(link.get("trip_day_id") or "")
        pstatus = str(link.get("placement_status") or "")

        if outcome == "duplicate":
            return _out(
                "duplicate",
                reason="already_placed",
                trip_id=trip_id,
                trip_day_id=placed_day,
                link_id=str(link.get("id") or ""),
                placement_source=str(link.get("placement_source") or ""),
                placement_status=pstatus,
            )
        if outcome != "created":
            return _out("noop", reason="claim_" + (outcome or "empty"),
                        trip_id=trip_id)

        return _out(
            "needs_day" if pstatus == "needs_day" else "linked",
            reason="" if placed_day else (resolved.get("reason") or "no_selected_day"),
            trip_id=trip_id,
            trip_day_id=placed_day,
            link_id=str(link.get("id") or ""),
            placement_source=str(link.get("placement_source") or ""),
            placement_status=pstatus,
        )
    except Exception as exc:
        # Class name only. A repository message can quote a trip title
        # or a day label, and this line goes to api.log.
        return _out("failed", error_class=exc.__class__.__name__)
