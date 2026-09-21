from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from typing import List, Optional

from ..db import get_projection, merge_projection_fields, upsert_projection

router = APIRouter(prefix="/api/interview", tags=["projection"])

logger = logging.getLogger(__name__)


class ProjectionEnvelope(BaseModel):
    fields: Dict[str, Any] = Field(default_factory=dict)
    pendingSuggestions: list[Dict[str, Any]] = Field(default_factory=list)
    syncLog: list[Dict[str, Any]] = Field(default_factory=list)


class ProjectionGetResponse(BaseModel):
    ok: bool = True
    person_id: str
    projection: ProjectionEnvelope = Field(default_factory=ProjectionEnvelope)
    source: str = "unknown"
    version: int = 1
    updated_at: str


class ProjectionPutRequest(BaseModel):
    person_id: str
    projection: ProjectionEnvelope = Field(default_factory=ProjectionEnvelope)
    source: str = "projection_sync"
    # WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 R1.4: advisory only. The
    # server owns version and increments it monotonically. Retained so
    # existing clients (which hardcode 1) keep validating.
    version: int = 1
    # Supervisor review 2026-08-17: an UNRESTRICTED replacement endpoint
    # defeats the field-level PATCH beside it. A non-empty stale envelope
    # would still erase server-authored keys, so `allow_empty` alone was
    # never the whole guard.
    #
    # Default is now MERGE: keys the body does not mention are left
    # alone. True replacement requires BOTH replace=True and a matching
    # base_version -- explicitly authorized, under optimistic
    # concurrency. That is the reset operation, and nothing else.
    replace: bool = False
    # R1.5 — a deliberate wipe stays possible and must be explicit. The
    # hazard this closes: `projection` has a default_factory, so a body
    # that omits it (or puts `fields` at the top level, as bio-builder's
    # deep reset did) validates fine and would otherwise silently write an
    # empty envelope over a populated row.
    allow_empty: bool = False
    # Supervisor requirement (2026-08-16): the version the client
    # hydrated from. A mismatch is a 409 that PRESERVES the newer server
    # record. Omitting it means "not claiming to know the base".
    base_version: Optional[int] = None


class ProjectionPatchRequest(BaseModel):
    """FIELD-LEVEL mutation. This is the ordinary write path.

    Whole-document PUT could not be made safe by guarding it: the
    browser's envelope is not a superset of the server's, so replacing
    the document erases server-authored keys (corrections written
    mid-turn by `projection_writer.apply_correction`, and anything added
    to that blob later) even when the replacement is fresh and
    non-empty. A per-field write leaves untouched keys untouched.
    """

    person_id: str
    # field_path -> field object. Absent paths are left alone.
    mutations: Dict[str, Any] = Field(default_factory=dict)
    removals: List[str] = Field(default_factory=list)
    # WO-03B Step 0, condition C1 — THE ORDINARY PATCH NO LONGER TOUCHES
    # THE QUEUE.
    #
    # This used to mean "supplied -> that array is replaced". A dedicated
    # append endpoint is pointless while any ordinary caller can still
    # replace the whole array: whoever can replace it owns it, and a
    # later acceptance "verified against the stored queue" would be
    # verified against whatever a client last wrote.
    #
    # The field is retained so an older client sending it still
    # validates, and it is now IGNORED rather than honoured — the route
    # says so in its response. Dropping the field outright would 422 a
    # stale client and lose its field mutations too, which is a worse
    # failure than ignoring one key.
    #
    # Nothing is lost by this: `_sendMutations` (projection-sync.js:796)
    # never sent it, so on the live installation the field has no caller
    # at all. Replacement survives only on the deliberate reset path
    # (PUT replace=true + base_version).
    pendingSuggestions: Optional[List[Any]] = None
    source: str = "projection_sync"
    base_version: Optional[int] = None
    # PER-PATH optimistic concurrency: the value this caller hydrated for
    # each path it is writing. A global version proves only that
    # SOMETHING moved, not what -- rebasing a dirty path onto a newer
    # record is safe for a disjoint edit and silently destructive for a
    # same-path one. Omitting this means the caller cannot demonstrate
    # safety, and a version mismatch then contests every path.
    base_fields: Optional[Dict[str, Any]] = None


class ProjectionPutResponse(BaseModel):
    ok: bool = True
    person_id: str
    projection: ProjectionEnvelope = Field(default_factory=ProjectionEnvelope)
    source: str = "projection_sync"
    version: int = 1
    updated_at: str
    # R1.3 — False means the stored row was protected and left untouched.
    # Reported rather than swallowed: a caller must be able to tell a
    # refusal from a success.
    write_applied: bool = True
    # True only on a contested-path refusal (served with HTTP 409).
    conflict: bool = False
    # Exactly which paths the server found changed since the caller
    # hydrated. The caller keeps its mutation and surfaces these; it must
    # NOT retry them, because a retry would overwrite the newer value.
    conflicting_paths: List[str] = Field(default_factory=list)
    # WO-03B C1 — true when this PATCH carried a pendingSuggestions array
    # that was ignored. A caller that thought it wrote the queue must be
    # able to learn that it did not.
    suggestions_ignored: bool = False


class SuggestionAppendRequest(BaseModel):
    """One proposal. The server assigns its identity and checks its
    evidence; the client supplies the claim."""

    person_id: str
    fieldPath: str
    value: Any
    confidence: float = 0.0
    # WO-03B C2 — a CLAIM, verified before anything is stored. Never
    # promoted to evidence on the client's say-so.
    turnId: str = ""
    origin: str = "extraction"
    source: str = "projection_suggest"


class SuggestionAppendResponse(BaseModel):
    ok: bool = True
    person_id: str
    suggestion_id: str
    # False when an identical proposal was already outstanding.
    appended: bool = True
    duplicate: bool = False
    # True when a person already DECLINED this exact value. Not queued;
    # counted. `repeats` then reports the re-proposal count.
    suppressed: bool = False
    repeats: int = 1
    # verified | unverified | absent — WO-03A's three states, decided
    # here at creation and never re-decided downstream.
    turn_evidence: str = "absent"
    # True when the questionnaire defines no such field. The proposal is
    # still recorded and inspectable, but it is kept out of the
    # actionable review queue — accepting it would store a value no form
    # can show.
    destination_undefined: bool = False
    pending_count: int = 0
    version: int = 0
    updated_at: str = ""


@router.get("/projection", response_model=ProjectionGetResponse)
def get_projection_route(
    person_id: str = Query(..., description="Lorevox narrator/person id"),
) -> ProjectionGetResponse:
    row = get_projection(person_id)
    if not row:
        # Supervisor requirement (2026-08-16): a client must be able to
        # tell "no row" from "version 1". This returned 1 for both, which
        # made base_version unusable for conflict detection -- an absent
        # row and a once-written row were indistinguishable. 0 means
        # absent, and it is what db.get_projection has always reported.
        return ProjectionGetResponse(
            person_id=person_id,
            projection=ProjectionEnvelope(),
            source="empty",
            version=0,
            updated_at=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        )

    return ProjectionGetResponse(
        person_id=person_id,
        projection=ProjectionEnvelope(**row.get("projection", {})),
        source=row.get("source", "unknown"),
        version=int(row.get("version", 0)),
        updated_at=row.get("updated_at") or datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
    )


def _as_response(saved: Dict[str, Any]) -> ProjectionPutResponse:
    return ProjectionPutResponse(
        person_id=saved["person_id"],
        projection=ProjectionEnvelope(**(saved.get("projection") or {})),
        source=saved.get("source") or "unknown",
        version=int(saved.get("version") or 0),
        updated_at=saved.get("updated_at") or "",
        write_applied=bool(saved.get("write_applied", True)),
        conflict=bool(saved.get("conflict", False)),
        conflicting_paths=list(saved.get("conflicting_paths") or []),
    )


@router.patch("/projection", response_model=ProjectionPutResponse)
def patch_projection_route(payload: ProjectionPatchRequest, response: Response) -> ProjectionPutResponse:
    """Ordinary write path — field-level, conflict-aware, non-destructive."""
    if not payload.person_id.strip():
        raise HTTPException(status_code=400, detail="person_id is required")

    saved = merge_projection_fields(
        person_id=payload.person_id,
        mutations=payload.mutations,
        removals=payload.removals,
        source=payload.source,
        base_version=payload.base_version,
        base_fields=payload.base_fields,
        # C1: never forwarded. The queue is server-owned; see the field's
        # note on the request model for why ignoring beats rejecting.
        pending_suggestions=None,
    )
    if saved.get("conflict"):
        # 409 with the NEWER server record in the body, so the client can
        # rebase its own dirty fields onto it instead of overwriting.
        response.status_code = 409
    out = _as_response(saved)
    if payload.pendingSuggestions is not None:
        # Reported, not swallowed. A caller that believed it was writing
        # the queue must be able to find out that it was not — the same
        # rule `write_applied` follows.
        out.suggestions_ignored = True
        logger.info(
            "patch_projection_route: ignored a pendingSuggestions array "
            "from %s (%d entries) — the queue is server-owned; use POST "
            "/api/interview/projection/suggestion",
            payload.source, len(payload.pendingSuggestions),
        )
    return out


@router.post("/projection/suggestion", response_model=SuggestionAppendResponse)
def append_suggestion_route(payload: SuggestionAppendRequest) -> SuggestionAppendResponse:
    """Queue ONE proposal, server-owned. WO-03B Step 0.

    This is the only way a new suggestion reaches the queue. The client
    cannot replace the array, so a proposal's identity, timestamp and
    evidence are all established here rather than asserted by whoever
    posted.

    WHAT IS DECIDED HERE AND NEVER RE-DECIDED
      suggestion_id  minted server-side; it identifies this proposal
                     through review, acceptance and decline
      ts             server clock, not the caller's
      turn_evidence  the verdict from WO-03A's verify_turn

    ON THE TURN CITATION. `turnId` is a claim. It is checked with the
    same join WO-03A uses — the turn must resolve to THIS narrator
    through `sessions.person_id`, be a `role='user'` row, and not be a
    system directive. A proposal citing an unverifiable turn is still
    queued; it simply does not carry verified evidence into review.

    That check belongs here rather than at acceptance because the accept
    path writes provenance, and a citation that was never checked must
    not be able to become a verified `narrator_direct` claim later by
    the act of someone clicking Accept.

    WHAT THIS ROUTE DOES NOT DO: it does not write the value into the
    questionnaire. A proposal is not an answer. Acceptance is a separate,
    transactional operation (WO-03B step 2) and is not built yet.
    """
    import uuid

    from ..db import append_projection_suggestion
    from ..services.answer_provenance import verify_turn

    if not payload.person_id.strip():
        raise HTTPException(status_code=400, detail="person_id is required")
    if not payload.fieldPath.strip():
        raise HTTPException(status_code=400, detail="fieldPath is required")

    from ..db import _connect as _db_connect
    from ..services.suggestion_review import is_suppressed, note_reproposal

    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    con = _db_connect()
    try:
        evidence = verify_turn(con, payload.person_id, payload.turnId)
        # Ruling requirement 3: a value a person already declined is not
        # offered again. It is COUNTED, so "Lori keeps trying to tell you
        # X" stays observable, and the response says so rather than
        # pretending it was queued. A materially different value for the
        # same field is not suppressed — the person has not seen it.
        prior = is_suppressed(con, payload.person_id, payload.fieldPath, payload.value)
        if prior is not None:
            con.execute("BEGIN IMMEDIATE")
            note_reproposal(con, payload.person_id, payload.fieldPath, payload.value, now)
            con.commit()
            return SuggestionAppendResponse(
                person_id=payload.person_id,
                suggestion_id=prior["suggestion_id"] or "",
                appended=False, duplicate=False, suppressed=True,
                repeats=int(prior["reproposals"] or 0) + 1,
                turn_evidence=evidence,
                pending_count=0, version=0, updated_at=now,
            )
    finally:
        con.close()

    sid = "sg_" + uuid.uuid4().hex[:16]
    entry: Dict[str, Any] = {
        "suggestion_id": sid,
        "fieldPath": payload.fieldPath,
        "value": payload.value,
        "confidence": float(payload.confidence or 0.0),
        "origin": payload.origin or "extraction",
        # The CLAIMED turn, kept whatever the verdict — the WO-03A rule:
        # nulling it would erase the difference between "no citation" and
        # "a citation that did not check out".
        "source_turn_id": payload.turnId or None,
        "turn_evidence": evidence,
        "ts": now,
        "repeats": 1,
        # WO-03B — can the form render an answer here at all?
        #
        # Recorded so the review surface can keep it OUT of the
        # actionable queue and say why, rather than offering an Accept
        # that would store the value where nobody can see it. This flag
        # is a statement about NOW; acceptance re-checks, because the
        # schema can change while a proposal waits.
        #
        # Measured live 2026-09-20: 20 of 30 queued suggestions fail this
        # — `extract.py`'s EXTRACTABLE_FIELDS has drifted from the
        # questionnaire and proposes `military.*`, `residence.*`,
        # `travel.*` paths the form never defines.
        "destination_undefined": _destination_undefined(payload.fieldPath),
        # C4 — a proposal aimed at a repeatable section cannot name an
        # entry that does not exist yet, and MUST NOT fall back to an
        # ordinal: after an insertion or reorder that names a different
        # relative. Flagged here, resolved by a person at review, and
        # the accept path will refuse a proposal still carrying this.
        "destination_unresolved": _is_unresolved_destination(payload.fieldPath),
    }

    res = append_projection_suggestion(payload.person_id, entry, source=payload.source)
    if entry["destination_undefined"]:
        logger.warning(
            "suggestion %s for %s targets %s, which the questionnaire does not "
            "define — queued as non-actionable, not silently dropped",
            sid, payload.person_id, payload.fieldPath)
    return SuggestionAppendResponse(
        person_id=payload.person_id,
        suggestion_id=res.get("suggestion_id") or sid,
        appended=bool(res.get("appended")),
        duplicate=bool(res.get("duplicate")),
        repeats=int(res.get("repeats") or 1),
        turn_evidence=evidence,
        destination_undefined=bool(entry["destination_undefined"]),
        pending_count=int(res.get("pending_count") or 0),
        version=int(res.get("version") or 0),
        updated_at=res.get("updated_at") or now,
    )


# The eight repeatable questionnaire sections. A proposal aimed at one of
# them has no entry to attach to until a person says which, so it is
# marked for resolution at review rather than guessed. One definition,
# owned by the review service; imported so the two cannot drift.
from ..services.suggestion_review import REPEATABLE_SECTIONS as _REPEATABLE_SECTIONS  # noqa: E402


def _is_unresolved_destination(field_path: str) -> bool:
    head = (field_path or "").split(".")[0].split("[")[0]
    return head in _REPEATABLE_SECTIONS


def _destination_undefined(field_path: str) -> bool:
    """True when the questionnaire has no such field.

    Fails CLOSED: if the schema cannot be read we mark the proposal
    undefined rather than assume it is fine. A proposal wrongly held back
    is visible and recoverable; a value accepted into a field nobody can
    render is neither.
    """
    from ..services import questionnaire_schema as _qs
    from ..services.suggestion_review import split_destination
    section, field, _rep = split_destination(field_path or "")
    try:
        return not _qs.is_defined(section, field)
    except _qs.SchemaUnavailable as exc:
        logger.error(
            "questionnaire schema unavailable while queueing %s — marking the "
            "proposal undefined rather than guessing: %s", field_path, exc)
        return True


# ── review: accept / decline by suggestion_id ────────────────────────
#
# Both act on the queued proposal that actually exists, looked up by the
# id the server minted — never on a field path and a value the client
# asserts were offered (ruling C3). Both are one transaction.


class ReviewRequest(BaseModel):
    person_id: str
    # WO-04 requirement 3. A flagged proposal cannot be accepted by
    # confirming a warning: the person supplies the value they actually
    # want, or picks a different destination. The original proposal is
    # preserved on the review record either way.
    corrected_value: Optional[Any] = None
    correction_reason: str = ""
    # For a LEGACY proposal at a destination that already existed: the
    # caller states that a person has read it and accepts it as it
    # stands. Satisfies the acknowledge tier and NOTHING ELSE — a
    # flagged value, or a proposal queued before its section existed,
    # still needs `corrected_value`. Sending this on an unflagged
    # proposal changes nothing.
    acknowledge_legacy: bool = False
    # For a proposal aimed at a repeatable section: the `_entryId` the
    # person chose, or "__new__" to add one. Refused if absent for an
    # unresolved destination — an ordinal is never inferred.
    entry_id: str = ""
    # Unverified, as everywhere. Who the caller SAID was reviewing.
    reviewed_by: str = ""


class ReviewResponse(BaseModel):
    ok: bool = True
    person_id: str
    suggestion_id: str
    verdict: str
    # accept only
    path: str = ""
    entry_id: str = ""
    revision: int = 0
    write_applied: bool = False
    # HOW the acceptance was arrived at: direct / acknowledged_legacy /
    # corrected. The service has always returned it; the response model
    # dropped it, so the page could not tell a person which act had just
    # completed and said "Accepted as Lori's suggestion" even when they
    # had typed their own value. Empty on a decline.
    accept_mode: str = ""


@router.post("/projection/suggestion/{suggestion_id}/accept", response_model=ReviewResponse)
def accept_suggestion_route(suggestion_id: str, payload: ReviewRequest) -> ReviewResponse:
    """Write the proposal as an ACCEPTED AI SUGGESTION. Never as a human entry.

    The answer lands with origin='ai_suggested', proposed_by='lori',
    confirmed_via='acceptance' — and stays that way. "Lori proposed it and
    a person agreed" is a weaker fact than "a person said it".

    409 when the destination already holds a different value. The body
    carries both, and the person decides. Accepting a machine's date over
    an operator's date by one click is the silent overwrite this refuses;
    an operator who wants the proposed value anyway makes an ordinary
    entry through the WO-03A route, which records it as theirs.

    422 when the destination is a repeatable section and no entry was
    chosen. The ordinal is never guessed.
    """
    from ..services import suggestion_review as sr
    from ..services import suggestion_flags as _flags_mod

    if not payload.person_id.strip():
        raise HTTPException(status_code=400, detail="person_id is required")
    try:
        res = sr.accept(payload.person_id, suggestion_id,
                        entry_id=(payload.entry_id or None),
                        reviewed_by=payload.reviewed_by,
                        corrected_value=payload.corrected_value,
                        correction_reason=payload.correction_reason,
                        acknowledge_legacy=bool(payload.acknowledge_legacy))
    except sr.SuggestionNotFound as e:
        raise HTTPException(status_code=404, detail={
            "error": "suggestion_not_found", "detail": str(e)})
    except sr.SuggestionUnresolved as e:
        raise HTTPException(status_code=422, detail={
            "error": "destination_unresolved",
            "section": str(e),
            "detail": "This proposal is aimed at a repeatable section. Choose "
                      "which entry it belongs to, or '__new__', before accepting.",
        })
    except sr.DestinationUndefined as e:
        # Nothing was written: the check runs before the write, and the
        # in-transaction re-check rolls everything back if the schema
        # moved underneath it.
        raise HTTPException(status_code=422, detail={
            "error": "destination_undefined",
            "section": e.section, "field": e.field,
            "detail": e.detail,
        })
    except _flags_mod.SuggestionFlagged as e:
        # 422, not 409: the request is not in conflict with the record,
        # it is incomplete. Nothing was written — the check runs before
        # the write AND inside the transaction.
        #
        # TWO ERROR NAMES, because the two requirements are different
        # claims and a surface that showed one message for both would
        # be telling a person that thirty old proposals are wrong.
        # `legacy_review_required` asserts nothing about the value.
        _ack = e.requirement == _flags_mod.REQUIRE_ACKNOWLEDGE
        raise HTTPException(status_code=422, detail={
            "error": "legacy_review_required" if _ack else "suggestion_flagged",
            "requirement": e.requirement,
            "reason": e.reason,
            "detail": e.detail,
            "proposed_value": e.proposed_value,
            "source_note": e.source_note,
            "field_path": e.field_path,
            "remedy": (
                "This proposal is old and unreviewed. Send "
                "`acknowledge_legacy: true` to accept it as it stands, or "
                "`corrected_value` to change it first. Neither asserts the "
                "value is wrong."
                if _ack else
                "Send `corrected_value` with the value you want, or accept "
                "it at a different destination. Confirming the warning "
                "alone is not enough, and `acknowledge_legacy` does not "
                "satisfy this."),
        })
    except sr.SuggestionConflict as e:
        raise HTTPException(status_code=409, detail={
            "error": "destination_holds_a_different_value",
            "path": e.path, "stored": e.stored, "proposed": e.proposed,
            "detail": "The record already holds a different answer here. "
                      "Accepting would replace it. Decline the suggestion to "
                      "keep the record, or enter the value yourself.",
        })
    return ReviewResponse(
        person_id=payload.person_id, suggestion_id=suggestion_id,
        verdict="accepted", path=res.get("path") or "",
        entry_id=res.get("entry_id") or "",
        revision=int(res.get("revision") or 0),
        write_applied=bool(res.get("write_applied")),
        accept_mode=res.get("accept_mode") or "",
    )


@router.post("/projection/suggestion/{suggestion_id}/decline", response_model=ReviewResponse)
def decline_suggestion_route(suggestion_id: str, payload: ReviewRequest) -> ReviewResponse:
    """Record the refusal, THEN remove from the queue. One transaction.

    The record is what stops the same value being offered again. It is
    NOT a biographical fact: declining "born in Duluth" does not establish
    where they were born, and nothing may read it that way.
    """
    from ..services import suggestion_review as sr

    if not payload.person_id.strip():
        raise HTTPException(status_code=400, detail="person_id is required")
    try:
        sr.decline(payload.person_id, suggestion_id, reviewed_by=payload.reviewed_by)
    except sr.SuggestionNotFound as e:
        raise HTTPException(status_code=404, detail={
            "error": "suggestion_not_found", "detail": str(e)})
    return ReviewResponse(person_id=payload.person_id, suggestion_id=suggestion_id,
                          verdict="declined")


@router.put("/projection", response_model=ProjectionPutResponse)
def put_projection_route(payload: ProjectionPutRequest, response: Response) -> ProjectionPutResponse:
    """Whole-envelope write. MERGES by default; replaces only on request.

    Supervisor review 2026-08-17. Keeping an unrestricted replacement
    route beside the field-level PATCH would have defeated the PATCH: a
    non-empty but stale envelope still erases server-authored keys, and
    `allow_empty` guards only the empty case.

    So the default path no longer replaces. It merges the envelope's
    fields, leaving every key the body does not mention alone -- which is
    the property the work order actually required. True replacement is
    the RESET operation and needs `replace=true` PLUS a `base_version`
    that still matches; anything else is 409.
    """
    if not payload.person_id.strip():
        raise HTTPException(status_code=400, detail="person_id is required")

    envelope = payload.projection.model_dump()

    if not payload.replace:
        # Merge. Unmentioned keys survive; pendingSuggestions is replaced
        # only because the caller sent a whole envelope containing it.
        saved = merge_projection_fields(
            person_id=payload.person_id,
            mutations=dict(envelope.get("fields") or {}),
            removals=[],
            source=payload.source,
            base_version=payload.base_version,
            # STRICTLY NON-ERASING. ProjectionEnvelope defaults
            # pendingSuggestions to [], so a merge cannot tell "I sent an
            # empty list" from "I omitted it" -- and guessing wrong erases
            # the operator's queue. Only a non-empty list is treated as
            # mentioned. Clearing the queue is PATCH's job: its field is
            # Optional, so it CAN tell the two apart.
            pending_suggestions=(envelope.get("pendingSuggestions") or None),
        )
        if saved.get("conflict"):
            response.status_code = 409
        return _as_response(saved)

    # Explicitly authorized replacement. Optimistic concurrency is
    # MANDATORY here -- a replace without a base cannot be shown safe.
    if payload.base_version is None:
        raise HTTPException(
            status_code=400,
            detail="replace=true requires base_version (explicitly authorized "
                   "replacement runs under optimistic concurrency)",
        )
    saved = upsert_projection(
        person_id=payload.person_id,
        projection=envelope,
        source=payload.source,
        version=payload.version,
        allow_empty=payload.allow_empty,
        base_version=payload.base_version,
    )
    if saved.get("conflict"):
        response.status_code = 409
    return _as_response(saved)
