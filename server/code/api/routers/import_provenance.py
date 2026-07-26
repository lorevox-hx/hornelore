"""Import provenance router -- WO-TRAVEL-DOC-IMPORT-PROVENANCE-FOUNDATION-01
Phase 4, the minimal verification surface (2026-07-26).

This is not the Evidence Review Queue. It is the least API that lets a
human prove, through the real backend boundary, that the Phase 3
repository behaves the way Phase 3 claims it does: that intake is not
approval, that a batch cannot reach across people, that a candidate
cannot claim another person's trip or another person's photo, and that
nothing in the evidence lane is ever deleted.

ALL routes are gated behind ``HORNELORE_IMPORT_PROVENANCE=1`` and 404
when it is off, mirroring the ``HORNELORE_TRIPS`` posture in trips.py.

Endpoints:

    POST   /api/import-provenance/batches
    GET    /api/import-provenance/batches?person_id=&status=&include_hidden=
    GET    /api/import-provenance/batches/{batch_id}
    GET    /api/import-provenance/batches/{batch_id}/counts
    PATCH  /api/import-provenance/batches/{batch_id}/trip     {trip_id|null}
    POST   /api/import-provenance/batches/{batch_id}/close    {failed?, failure_reason?}
    POST   /api/import-provenance/batches/{batch_id}/reopen
    PATCH  /api/import-provenance/batches/{batch_id}/hidden   {hidden}

    POST   /api/import-provenance/batches/{batch_id}/candidates
    GET    /api/import-provenance/candidates?batch_id=&person_id=&trip_id=&state=&include_hidden=&limit=
    GET    /api/import-provenance/candidates/{candidate_id}
    PATCH  /api/import-provenance/candidates/{candidate_id}/trip    {trip_id|null}
    POST   /api/import-provenance/candidates/{candidate_id}/decision
    PATCH  /api/import-provenance/candidates/{candidate_id}/hidden  {hidden}

Deliberately absent, and to stay absent:

  * There is no DELETE. Retirement is ``hidden``, per the evidence-lane
    rule this project has held since WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01.
  * There is no ``person_id`` on the candidate-create body. A candidate's
    person is copied from its batch and cannot be asserted by a caller,
    so the route layer cannot express a cross-person candidate at all.
  * There is no route that sets ``narrator_ready`` or
    ``include_in_memoir``, and no route that materializes a photo.
    Accepting a candidate records a promotion that already happened
    somewhere else; it cannot cause one.
  * There is no Google Photos, no Takeout, no Evidence Queue UI and no
    Lori behavior here. Those are WO-2 through WO-5.

The route layer re-checks the person/trip/photo boundaries itself rather
than trusting the repository to be the only guard. The repository check
is the one that matters -- it holds inside the write transaction -- but a
route that only forwarded would mean the HTTP surface had no opinion, and
a later caller could be added that never reaches the repository at all.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..services import import_repository as repo

logger = logging.getLogger("code.api.routers.import_provenance")

router = APIRouter(prefix="/api/import-provenance", tags=["import-provenance"])


# -- gate -------------------------------------------------------------------

def _import_provenance_enabled() -> bool:
    """Default-OFF gate. Enable with `HORNELORE_IMPORT_PROVENANCE=1`."""
    return os.getenv("HORNELORE_IMPORT_PROVENANCE", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _require_enabled() -> None:
    if not _import_provenance_enabled():
        raise HTTPException(status_code=404, detail="Not found")


# -- error mapping ----------------------------------------------------------

# Every refusal the repository can make, mapped to the status code that
# says what actually happened. The point of this table is that a refused
# token or a cross-person write must never reach the client as a 500:
# a 500 reads as "the server broke", and these are the server working.
_STATUS_BY_ERROR = (
    (repo.BatchNotFoundError, 404),
    (repo.CandidateNotFoundError, 404),
    (repo.CrossPersonError, 409),
    (repo.CrossTripError, 409),
    (repo.IntakeIsNotApprovalError, 409),
    (repo.BatchClosedError, 409),
    (repo.ExternalTokenError, 400),
    (repo.InvalidStateError, 400),
)


def _status_for(exc: Exception) -> int:
    for kind, status in _STATUS_BY_ERROR:
        if isinstance(exc, kind):
            return status
    # The base ImportRepositoryError. Raised when the database itself has
    # drifted (0037 not applied, an approval column grown by hand). That
    # is a server-side condition, not a bad request.
    return 500


def _call(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a repository call and turn its refusals into HTTP.

    The repository's messages are safe to surface: they name the field
    and the rule, never the offending value, so a rejected credential is
    not echoed back in the response body."""
    try:
        return fn(*args, **kwargs)
    except repo.ImportRepositoryError as exc:
        status = _status_for(exc)
        if status >= 500:
            logger.error("import provenance repository error: %s", exc)
        raise HTTPException(status_code=status, detail=str(exc))


# -- route-layer boundary checks --------------------------------------------

def _read_one(sql: str, args: tuple) -> Optional[sqlite3.Row]:
    """One read-only row, on the same database the repository writes.

    Late import of `..db` so a test that repoints DB_PATH is honored,
    exactly as import_repository._connect does it."""
    from .. import db as _db

    con = sqlite3.connect(str(_db.DB_PATH))
    try:
        con.row_factory = sqlite3.Row
        return con.execute(sql, args).fetchone()
    finally:
        con.close()


def _assert_trip_belongs_to(trip_id: Optional[str],
                            person_id: str,
                            what: str) -> None:
    """Refuse, at the route, a trip that is not this person's.

    409 and not 404: the trip exists, the person exists, and the request
    is coherent enough to answer -- what it is not is allowed."""
    if not trip_id:
        return
    row = _read_one("SELECT person_id FROM trips WHERE id = ?", (trip_id,))
    if row is None:
        raise HTTPException(
            status_code=409,
            detail="no trip with id %r (%s)" % (trip_id, what),
        )
    if row["person_id"] != person_id:
        raise HTTPException(
            status_code=409,
            detail="trip %s belongs to another person; %s cannot reach "
                   "across people" % (trip_id, what),
        )


def _assert_photo_belongs_to(photo_id: Optional[str],
                             person_id: str) -> None:
    """Refuse, at the route, accepting a candidate onto a photo that
    belongs to somebody else. Photos are owned by `narrator_id`."""
    if not photo_id:
        return
    row = _read_one("SELECT narrator_id FROM photos WHERE id = ?", (photo_id,))
    if row is None:
        raise HTTPException(
            status_code=409, detail="no photo with id %r" % photo_id,
        )
    if row["narrator_id"] != person_id:
        raise HTTPException(
            status_code=409,
            detail="photo %s belongs to another narrator; accepting a "
                   "candidate onto it would merge two people's evidence"
                   % photo_id,
        )


def _require_batch(batch_id: str) -> Dict[str, Any]:
    batch = repo.batch_get(batch_id)
    if batch is None:
        raise HTTPException(
            status_code=404, detail="no import batch with id %r" % batch_id,
        )
    return batch


def _require_candidate(candidate_id: str) -> Dict[str, Any]:
    cand = repo.candidate_get(candidate_id)
    if cand is None:
        raise HTTPException(
            status_code=404,
            detail="no import candidate with id %r" % candidate_id,
        )
    return cand


def _require_nonblank(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=400, detail="%s is required" % field)
    return value.strip()


# -- request models ---------------------------------------------------------

class BatchCreateRequest(BaseModel):
    person_id: str
    source: str
    trip_id: Optional[str] = None
    external_ref: Optional[str] = None
    label: Optional[str] = None
    notes: Optional[str] = None
    created_by_user_id: Optional[str] = None


class BatchTripRequest(BaseModel):
    # Explicitly nullable: passing null unbinds, which is a real operator
    # act and not a missing field.
    trip_id: Optional[str] = None


class BatchCloseRequest(BaseModel):
    failed: bool = False
    failure_reason: Optional[str] = None


class HiddenRequest(BaseModel):
    hidden: bool = True


class CandidateCreateRequest(BaseModel):
    # No person_id and no state. Person is the batch's; state is born
    # 'pending'. Both are refusals, not omissions.
    external_id: Optional[str] = None
    file_hash: Optional[str] = None
    filename: Optional[str] = None
    mime_type: Optional[str] = None
    byte_size: Optional[int] = None
    taken_at: Optional[str] = None
    taken_at_source: str = "unknown"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_source: str = "unknown"
    match_reason: Optional[Dict[str, Any]] = None
    match_confidence: Optional[float] = None
    trip_id: Optional[str] = None


class CandidateTripRequest(BaseModel):
    trip_id: Optional[str] = None


class CandidateDecisionRequest(BaseModel):
    """The 0037 column names, not the Epic Plan's working names.

    The plan drafted `review_status` and `operator_decision_json`;
    migration 0037 shipped `state`, `state_reason`, `reviewed_by_user_id`
    and `reviewed_at`. The shipped names win."""
    state: str = Field(..., description="accepted | rejected | duplicate | error")
    state_reason: Optional[str] = None
    reviewed_by_user_id: Optional[str] = None
    photo_id: Optional[str] = None


# -- batches ----------------------------------------------------------------

@router.post("/batches")
def create_batch_route(payload: BatchCreateRequest) -> Dict[str, Any]:
    _require_enabled()
    person_id = _require_nonblank(payload.person_id, "person_id")
    source = _require_nonblank(payload.source, "source")
    if source not in repo.IMPORT_SOURCES:
        raise HTTPException(
            status_code=400,
            detail="unknown import source %r; known sources are %s"
                   % (source, ", ".join(repo.IMPORT_SOURCES)),
        )
    _assert_trip_belongs_to(payload.trip_id, person_id, "an import batch")
    batch_id = _call(
        repo.batch_create,
        person_id=person_id,
        source=source,
        trip_id=payload.trip_id,
        external_ref=payload.external_ref,
        label=payload.label,
        notes=payload.notes,
        created_by_user_id=payload.created_by_user_id,
    )
    return {"ok": True, "batch": repo.batch_get(batch_id)}


@router.get("/batches")
def list_batches_route(
    person_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    include_hidden: bool = Query(False),
) -> Dict[str, Any]:
    _require_enabled()
    batches = _call(
        repo.batch_list,
        person_id=person_id,
        status=status,
        include_hidden=include_hidden,
    )
    return {"ok": True, "count": len(batches), "batches": batches}


@router.get("/batches/{batch_id}")
def get_batch_route(batch_id: str) -> Dict[str, Any]:
    _require_enabled()
    return {"ok": True, "batch": _require_batch(batch_id)}


@router.get("/batches/{batch_id}/counts")
def batch_counts_route(batch_id: str) -> Dict[str, Any]:
    _require_enabled()
    _require_batch(batch_id)
    return {"ok": True, "counts": _call(repo.batch_counts, batch_id)}


@router.patch("/batches/{batch_id}/trip")
def bind_batch_trip_route(batch_id: str,
                          payload: BatchTripRequest) -> Dict[str, Any]:
    _require_enabled()
    batch = _require_batch(batch_id)
    _assert_trip_belongs_to(payload.trip_id, batch["person_id"],
                            "an import batch")
    _call(repo.batch_bind_trip, batch_id, payload.trip_id)
    return {"ok": True, "batch": repo.batch_get(batch_id)}


@router.post("/batches/{batch_id}/close")
def close_batch_route(batch_id: str,
                      payload: BatchCloseRequest) -> Dict[str, Any]:
    _require_enabled()
    _require_batch(batch_id)
    _call(repo.batch_close, batch_id, failed=payload.failed,
          failure_reason=payload.failure_reason)
    return {"ok": True, "batch": repo.batch_get(batch_id)}


@router.post("/batches/{batch_id}/reopen")
def reopen_batch_route(batch_id: str) -> Dict[str, Any]:
    _require_enabled()
    _require_batch(batch_id)
    _call(repo.batch_reopen, batch_id)
    return {"ok": True, "batch": repo.batch_get(batch_id)}


@router.patch("/batches/{batch_id}/hidden")
def hide_batch_route(batch_id: str,
                     payload: HiddenRequest) -> Dict[str, Any]:
    """Retire or restore a batch. This is the closest thing to a delete
    the evidence lane offers, and it is reversible on purpose."""
    _require_enabled()
    _require_batch(batch_id)
    _call(repo.batch_hide, batch_id, hidden=payload.hidden)
    return {"ok": True, "batch": repo.batch_get(batch_id)}


# -- candidates -------------------------------------------------------------

@router.post("/batches/{batch_id}/candidates")
def create_candidate_route(batch_id: str,
                           payload: CandidateCreateRequest) -> Dict[str, Any]:
    _require_enabled()
    batch = _require_batch(batch_id)
    if payload.taken_at_source not in repo.TAKEN_AT_SOURCES:
        raise HTTPException(
            status_code=400,
            detail="unknown taken_at_source %r; known sources are %s"
                   % (payload.taken_at_source,
                      ", ".join(repo.TAKEN_AT_SOURCES)),
        )
    if payload.location_source not in repo.CANDIDATE_LOCATION_SOURCES:
        raise HTTPException(
            status_code=400,
            detail="unknown location_source %r; known sources are %s"
                   % (payload.location_source,
                      ", ".join(repo.CANDIDATE_LOCATION_SOURCES)),
        )
    _assert_trip_belongs_to(payload.trip_id, batch["person_id"],
                            "an import candidate")
    candidate_id = _call(
        repo.candidate_create,
        batch_id=batch_id,
        external_id=payload.external_id,
        file_hash=payload.file_hash,
        filename=payload.filename,
        mime_type=payload.mime_type,
        byte_size=payload.byte_size,
        taken_at=payload.taken_at,
        taken_at_source=payload.taken_at_source,
        latitude=payload.latitude,
        longitude=payload.longitude,
        location_source=payload.location_source,
        match_reason=payload.match_reason,
        match_confidence=payload.match_confidence,
        trip_id=payload.trip_id,
    )
    return {"ok": True, "candidate": repo.candidate_get(candidate_id)}


@router.get("/candidates")
def list_candidates_route(
    batch_id: Optional[str] = Query(None),
    person_id: Optional[str] = Query(None),
    trip_id: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    include_hidden: bool = Query(False),
    limit: Optional[int] = Query(None, ge=0),
) -> Dict[str, Any]:
    """The read the Evidence Review Queue will eventually be built on.

    When both person_id and trip_id are given they must agree. Filtering
    on a mismatched pair would return an empty list, which reads as "this
    person has nothing on that trip" when the truth is "that trip is not
    theirs" -- two different facts that should not share an answer."""
    _require_enabled()
    if person_id and trip_id:
        _assert_trip_belongs_to(trip_id, person_id, "this query")
    candidates: List[Dict[str, Any]] = _call(
        repo.candidates_list,
        batch_id=batch_id,
        person_id=person_id,
        trip_id=trip_id,
        state=state,
        include_hidden=include_hidden,
        limit=limit,
    )
    return {"ok": True, "count": len(candidates), "candidates": candidates}


@router.get("/candidates/{candidate_id}")
def get_candidate_route(candidate_id: str) -> Dict[str, Any]:
    _require_enabled()
    return {"ok": True, "candidate": _require_candidate(candidate_id)}


@router.patch("/candidates/{candidate_id}/trip")
def set_candidate_trip_route(candidate_id: str,
                             payload: CandidateTripRequest) -> Dict[str, Any]:
    _require_enabled()
    cand = _require_candidate(candidate_id)
    _assert_trip_belongs_to(payload.trip_id, cand["person_id"],
                            "an import candidate")
    _call(repo.candidate_set_trip, candidate_id, payload.trip_id)
    return {"ok": True, "candidate": repo.candidate_get(candidate_id)}


@router.post("/candidates/{candidate_id}/decision")
def decide_candidate_route(
    candidate_id: str,
    payload: CandidateDecisionRequest,
) -> Dict[str, Any]:
    """Record an operator decision.

    'accepted' requires the photo_id of a photos row that already exists
    and already belongs to this candidate's person. This route does not
    create that photo, does not set narrator_ready on it and does not put
    it in a memoir. Intake is not approval, and neither is acceptance:
    acceptance only records that a promotion happened elsewhere."""
    _require_enabled()
    cand = _require_candidate(candidate_id)
    state = _require_nonblank(payload.state, "state")
    if state not in repo.DECIDABLE_STATES:
        raise HTTPException(
            status_code=400,
            detail="%r is not a decision; decidable states are %s"
                   % (state, ", ".join(repo.DECIDABLE_STATES)),
        )
    if state == "accepted" and not payload.photo_id:
        raise HTTPException(
            status_code=409,
            detail="accepting a candidate requires the photo_id of the "
                   "photos row it was materialized into",
        )
    if state != "accepted" and payload.photo_id:
        raise HTTPException(
            status_code=400,
            detail="a %r candidate cannot carry a photo_id" % state,
        )
    _assert_photo_belongs_to(payload.photo_id, cand["person_id"])
    _call(
        repo.candidate_decide,
        candidate_id,
        state,
        reason=payload.state_reason,
        reviewed_by_user_id=payload.reviewed_by_user_id,
        photo_id=payload.photo_id,
    )
    return {"ok": True, "candidate": repo.candidate_get(candidate_id)}


@router.patch("/candidates/{candidate_id}/hidden")
def hide_candidate_route(candidate_id: str,
                         payload: HiddenRequest) -> Dict[str, Any]:
    """Retire or restore one candidate. The match reason and the decision
    survive; hiding is retirement from a view, not a claim the import
    never happened."""
    _require_enabled()
    _require_candidate(candidate_id)
    _call(repo.candidate_hide, candidate_id, hidden=payload.hidden)
    return {"ok": True, "candidate": repo.candidate_get(candidate_id)}


# -- introspection ----------------------------------------------------------

@router.get("/enums")
def enums_route() -> Dict[str, Any]:
    """What the vocabulary actually is, read from the repository rather
    than restated here, so this endpoint cannot drift from 0037."""
    _require_enabled()
    return {
        "ok": True,
        "import_sources": list(repo.IMPORT_SOURCES),
        "batch_statuses": list(repo.BATCH_STATUSES),
        "candidate_states": list(repo.CANDIDATE_STATES),
        "decidable_states": list(repo.DECIDABLE_STATES),
        "taken_at_sources": list(repo.TAKEN_AT_SOURCES),
        "location_sources": list(repo.CANDIDATE_LOCATION_SOURCES),
    }
