"""Import provenance router -- WO-TRAVEL-DOC-IMPORT-PROVENANCE-FOUNDATION-01
Phase 4, the minimal verification surface (2026-07-26), plus
WO-TRAVEL-DOC-EVIDENCE-REVIEW-QUEUE-01 Phase 1, the queue read
(2026-07-26), and Phase 3, promotion (2026-07-27).

Phase 4 is the least API that lets a human prove, through the real
backend boundary, that the Phase 3 repository behaves the way Phase 3
claims it does: that intake is not approval, that a batch cannot reach
across people, that a candidate cannot claim another person's trip or
another person's photo, and that nothing in the evidence lane is ever
deleted.

WO-2 Phase 1 adds exactly one route to that surface -- ``GET /queue``,
the read a review screen is built on. It is a read and nothing else.

WO-2 Phase 3 adds the one write that was missing: ``POST
/candidates/{id}/promote``. Acceptance has always required a photo_id
of a photos row that already exists, and until now nothing in this lane
could produce one, so 'accepted' was a state the review queue could not
reach. Promotion produces it -- and stops there. It does not decide, it
does not approve, and it is a separate request from the decision on
purpose (WO-2 Decision 3, option B). Placement is still trip
granularity and nothing finer (Decision 1), and the candidate states
are still the five that shipped in 0037 (Decision 2).

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
    POST   /api/import-provenance/candidates/{candidate_id}/promote  (multipart)
    PATCH  /api/import-provenance/candidates/{candidate_id}/hidden  {hidden}

    GET    /api/import-provenance/queue?person_id=&trip_id=&batch_id=&state=&include_hidden=&limit=&offset=
    GET    /api/import-provenance/enums

Deliberately absent, and to stay absent:

  * There is no DELETE. Retirement is ``hidden``, per the evidence-lane
    rule this project has held since WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01.
  * There is no ``person_id`` on the candidate-create body. A candidate's
    person is copied from its batch and cannot be asserted by a caller,
    so the route layer cannot express a cross-person candidate at all.
  * There is no route that sets ``narrator_ready`` or
    ``include_in_memoir``. ``POST /promote`` materializes a photo, and
    that photo is born narrator_ready = 0, needs_confirmation = 1 and
    unapproved for Lori on both the date and the location. Accepting a
    candidate still only RECORDS a promotion; it still cannot cause one.
  * ``POST /promote`` accepts an UPLOADED FILE only for ``local_upload``
    and ``manual`` batches. Until 2026-07-29 this bullet read:

        "``POST /promote`` is restricted to ``local_upload`` and
        ``manual`` batches. The provider-side sources have no fetch yet,
        and promotion without bytes would mean inventing an
        ``image_path``."

    The second sentence gave the reason, and the Picker lane then went
    and satisfied it: it fetches, hashes and stages the original before
    a candidate is ever offered for review, so promoting one invents
    nothing. What survives is the narrower rule the sentence was
    protecting -- the operator must never be asked to supply a file the
    system already holds -- so an upload is refused for the
    provider-side sources instead of the promotion being refused.
    ``google_takeout`` and ``csv`` remain unpromotable in fact: they
    have no lane that stages bytes, so there is nothing to verify.
  * There is no Google Photos and no Takeout here. ``GET /queue`` is the
    queue's read and ``POST /promote`` is its one write; WO-3 through
    WO-5 are elsewhere.
  * ``GET /queue`` has no ``proposed_trip_day_id`` /
    ``proposed_region_id`` / ``proposed_stop_id``. Migration 0037 has no
    such columns and this work order did not add any. Until 2026-07-29
    the reason given was:

        "so placement in this system is trip-granularity and nothing
        finer. The route does not invent a finer answer than the schema
        can hold."

    The first half was never true of the system, only of this table:
    ``trip_photo_links`` has carried ``trip_day_id`` since 0015. What is
    true is that a CANDIDATE has no day, because a candidate is a review
    record and the day is a placement. The day is chosen by the operator
    at the placement step, immediately after promotion, and written to
    the link -- so no pending destination has to be parked on the
    candidate and no migration is owed. The route still does not invent
    a finer answer than the schema can hold.

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
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from pydantic import BaseModel, Field

from ..services import import_repository as repo

logger = logging.getLogger("code.api.routers.import_provenance")


# -- gate -------------------------------------------------------------------

def _import_provenance_enabled() -> bool:
    """Default-OFF gate. Enable with `HORNELORE_IMPORT_PROVENANCE=1`."""
    return os.getenv("HORNELORE_IMPORT_PROVENANCE", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _require_enabled() -> None:
    if not _import_provenance_enabled():
        raise HTTPException(status_code=404, detail="Not found")


# The gate is a router-level dependency, NOT only a first line inside each
# handler. FastAPI validates the request body before it calls the handler,
# so a gate that lives only in the handler never runs for a malformed
# body: `POST /batches {}` came back 422 with the required field names
# while the flag was off, which announces both that the route exists and
# what it wants. A dependency is solved before body validation, so the
# 404 wins. The per-handler `_require_enabled()` calls are kept as well --
# they cost nothing and they keep each handler correct on its own.
router = APIRouter(
    prefix="/api/import-provenance",
    tags=["import-provenance"],
    dependencies=[Depends(_require_enabled)],
)


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
    # Also 409 rather than 400, and for the same reason as BatchClosed:
    # 'rejected' is a perfectly valid decision, it is this candidate's
    # current state that refuses it. A 400 would tell the caller to fix
    # its payload, and there is nothing wrong with the payload.
    (repo.CandidateAlreadyDecidedError, 409),
    # 409 and not 400: the request is well formed and the candidate is
    # real. What is missing is the image, which is a fact about the
    # state of the world, not about the request.
    (repo.PhotoBytesMissingError, 409),
    # The same reasoning, one step further in. These two say the import
    # lane's own copy of the picture is gone or is not the file the
    # candidate describes. Nothing about the request is wrong and there
    # is nothing the caller can put in the payload to fix it -- the fix
    # is to run the import again -- so 409, and never 400 or 500.
    (repo.StagedOriginalMissingError, 409),
    (repo.StagedOriginalMismatchError, 409),
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


# Copied value-for-value from `_ALLOWED_IMAGE_MIME_PREFIXES` in
# routers/photos.py. Restated rather than imported because importing it
# would drag the whole photo router -- and its own separate flag gate --
# into this module's import graph. Deliberately the same narrow list and
# not a loose "image/" prefix: a promoted photo and an uploaded photo
# land in the same archive under the same rules, and a file the upload
# route would refuse must not get in through the side door.
_PROMOTE_MIME_PREFIXES = (
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
    "image/gif",
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


@router.post("/candidates/{candidate_id}/promote")
async def promote_candidate_route(
    candidate_id: str,
    file: Optional[UploadFile] = File(None),
    promoted_by_user_id: Optional[str] = Form(None),
) -> Dict[str, Any]:
    """Materialize a candidate into a photos row. Does not decide it.

    Multipart, and ``file`` is optional. Until 2026-07-29 this docstring
    ended the list of ways to promote with:

        "When neither holds, the file IS the request: an import_candidate
        carries a filename and a byte count, never the image, so there is
        nothing else promotion could build `photos.image_path` out of."

    That was true of every import lane that existed when it was written,
    all of which began with the operator holding the file. It stopped
    being true when the Picker lane started downloading the original
    itself, hashing it, and keeping the verified copy server-side. For
    those candidates an upload would mean asking the operator to fetch
    their own photo back out of Google and hand it to a program that
    already has it.

    So there are now four ways this ends with a photo_id and only one of
    them needs an upload: the candidate is already promoted; its
    ``file_hash`` matches a photo this person already has; the import
    lane's own verified copy is on disk; or the operator supplied the
    file. The repository decides between them in that order --
    ``candidate_promote`` owns the rule, this route only carries the
    bytes when there are bytes to carry.

    An upload is accepted only for the lanes where the operator is the
    one holding the picture. Supplying one for a provider-side import is
    refused rather than quietly ignored, which is a 400 out of
    ``InvalidStateError``.

    The candidate is still ``pending`` when this returns. Accepting it
    is the next, separate request, to ``POST /decision`` with the
    ``photo_id`` this one hands back.
    """
    _require_enabled()
    _require_candidate(candidate_id)

    if file is None:
        return {
            "ok": True,
            **_call(
                repo.candidate_promote,
                candidate_id,
                source_path=None,
                original_filename=None,
                promoted_by_user_id=promoted_by_user_id,
            ),
        }

    mime = (file.content_type or "").lower()
    if mime and not any(mime.startswith(p) for p in _PROMOTE_MIME_PREFIXES):
        raise HTTPException(
            status_code=415, detail="unsupported media type: %s" % mime,
        )

    # Stream to a temp file rather than reading into memory, and let the
    # repository move it from there -- the same shape POST /api/photos
    # uses, so both paths hit `store_photo_file` with a real path and
    # neither has to know how the bytes arrived.
    tmp_fd, tmp_path = tempfile.mkstemp(prefix="promote_", suffix=".bin")
    try:
        with os.fdopen(tmp_fd, "wb") as out:
            while True:
                chunk = await file.read(65536)
                if not chunk:
                    break
                out.write(chunk)
        result = _call(
            repo.candidate_promote,
            candidate_id,
            source_path=tmp_path,
            original_filename=file.filename,
            promoted_by_user_id=promoted_by_user_id,
        )
    finally:
        # On success the repository moved the temp file into the archive
        # and this unlink finds nothing; on any refusal it is still here
        # and must not be left behind.
        try:
            if Path(tmp_path).exists():
                Path(tmp_path).unlink()
        except OSError:
            pass

    return {"ok": True, **result}


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


# -- evidence review queue --------------------------------------------------
#
# WO-TRAVEL-DOC-EVIDENCE-REVIEW-QUEUE-01 Phase 1 (2026-07-26).
#
# `GET /candidates` above is the raw table read. This is the page read:
# the same rows, but each one carrying the batch it arrived in and the
# trip it is filed under, plus the counts a reviewer needs to know how
# much is behind the page. See `import_repository.queue_read` for why it
# is one query and not one-per-batch.
#
# It is still a read. It sets nothing, decides nothing, and materializes
# no photo. The decision path is unchanged: POST /candidates/{id}/decision,
# which still refuses `accepted` without a photo_id of a photos row the
# caller already created. Phase 1 can show and reject; it cannot accept
# until a promotion path exists, and that is a WO-2 decision, not a gap
# this route is allowed to paper over.

@router.get("/queue")
def queue_route(
    person_id: str = Query(..., min_length=1),
    trip_id: Optional[str] = Query(None),
    batch_id: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    include_hidden: bool = Query(False),
    limit: Optional[int] = Query(None, ge=0),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """One page of the Evidence Review Queue for one person.

    `person_id` is required and is not defaulted from anywhere. A queue
    that inferred its person would be one bad inference away from showing
    a reviewer another person's evidence, and the evidence lane is the
    last place in this system that should guess.

    `state` filters the page but deliberately does NOT filter
    `state_counts`: the counts describe the whole queue behind the page,
    so a reviewer looking at `pending` can still see how much has been
    accepted, rejected or errored without changing the filter to find out.
    """
    _require_enabled()
    _assert_trip_belongs_to(trip_id, person_id, "this queue")
    result: Dict[str, Any] = _call(
        repo.queue_read,
        person_id=person_id,
        trip_id=trip_id,
        batch_id=batch_id,
        state=state,
        include_hidden=include_hidden,
        limit=limit,
        offset=offset,
    )
    return {"ok": True, **result}
