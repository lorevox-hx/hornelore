"""Google Photos Picker router -- WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01
Phase 1 (2026-07-27): credentials, health, and session lifecycle.
Phase 2B (2026-07-28): the ingest route.

WHAT THIS ROUTER DOES

    GET    /api/google-picker/health
    POST   /api/google-picker/sessions              {person_id, trip_id?, label?}
    GET    /api/google-picker/sessions/{batch_id}
    DELETE /api/google-picker/sessions/{batch_id}
    POST   /api/google-picker/sessions/{batch_id}/ingest

``POST /sessions`` creates the Picker session at Google AND opens the
matching ``import_batch`` with ``source='google_photos_picker'``, storing
the Picker session id in the batch's ``external_ref``. That column was
built for exactly this -- migration 0037 describes it as an "opaque
provider-side handle for the fetch (an album id, a Takeout archive name,
an upload session id). NOT a token, NOT a URL with credentials in it."
The batch is the durable handle; every later route in this lane is
addressed by ``batch_id``, never by the Google session id, so the
provider handle never has to travel through a URL the operator pastes.

WHAT THE INGEST ROUTE DOES, IN ONE PARAGRAPH

``POST /sessions/{batch_id}/ingest`` lists what the operator picked,
downloads each item's original bytes, verifies them by content, reads
EXIF off the file, calls ``candidate_create()`` and only then moves the
bytes into the id that call actually returned. Every item is independent:
one failure does not stop the ones after it, and the run answers with a
per-item outcome list. It creates ``pending`` candidates and nothing
else. Spec 12.3: **an ingest failure is not a candidate decision**, so
``candidate_decide()`` is never called here, and an item that could not
be acquired produces no candidate row at all rather than an ``error``
candidate nobody can undo.

WHAT THIS ROUTER STILL DELIBERATELY DOES NOT DO, AND WHY

  * It writes no ``photos`` row and performs no promotion. Ingest ends at
    a ``pending`` candidate in the existing Evidence Review Queue; the
    operator is the next step, not this code.
  * It does not add ``google_photos_picker`` to
    ``import_repository.PROMOTABLE_SOURCES``. That happens in Phase 3,
    and only after Phase 2 has proven it can stage real bytes. The
    existing comment on that tuple is the reason: adding a provider
    source without its fetch "would turn promotion into a way to mint
    photo rows for images that do not exist."
  * It has no DELETE on the evidence lane. ``DELETE /sessions/{id}``
    ends the PICKING SESSION AT GOOGLE. The ``import_batch`` survives it
    untouched -- it can be closed, reopened or hidden through the
    existing import-provenance routes, and it is never removed.

THE GATE

Both flags must be on: ``HORNELORE_GOOGLE_PICKER=1`` (new, default OFF)
and ``HORNELORE_IMPORT_PROVENANCE=1`` (existing). The second is not
decoration -- this router writes ``import_batch`` rows through
``import_repository``, so a picker lane running while the provenance
lane is off would be creating batches that no route can read. Either
flag off means 404 on every route here, including ``/health``, matching
the posture of every other lane and matching what the Travel Doc Lab UI
already knows how to render (it treats 404 as "this lane is switched
off" and shows an explanatory panel rather than an error).

THE CREDENTIAL RULE

``GET /health`` reports credential PRESENCE as booleans. It does not
report values, prefixes, lengths or masked tails. See
``services/google_picker/oauth.py`` for the full statement of the rule;
the short version is that credentials live in the process environment
and nothing here writes one to the database, returns one, or logs one.

The ingest route extends that rule to one more value. A picked item's
``baseUrl`` is a bearer-scoped download URL -- possession of it is
possession of the photograph. It travels from ``list_media_items`` into
``download_original`` and stops there. It is never logged, never put in
an exception message, never stored in ``match_reason``, and never
returned. The per-item results below identify an item by its opaque
``media_item_id`` only, which is the same value that lands in
``external_id`` and is what the repository's token scanner was written
to permit.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..services import import_repository as repo
from ...services.google_picker import acquire, oauth, picker_client

logger = logging.getLogger("code.api.routers.google_picker")

PICKER_SOURCE = "google_photos_picker"


# -- gate -------------------------------------------------------------------

def _truthy(raw: Optional[str]) -> bool:
    return (raw or "").strip().lower() in ("1", "true", "yes", "on")


def _picker_enabled() -> bool:
    """Default-OFF gate. Enable with `HORNELORE_GOOGLE_PICKER=1`."""
    return _truthy(os.getenv("HORNELORE_GOOGLE_PICKER", "0"))


def _provenance_enabled() -> bool:
    """The lane this one writes into. Read the same way
    ``import_provenance.py`` reads it, rather than importing its private
    helper, so neither router can quietly change the other's gate."""
    return _truthy(os.getenv("HORNELORE_IMPORT_PROVENANCE", "0"))


def _require_enabled() -> None:
    if not (_picker_enabled() and _provenance_enabled()):
        raise HTTPException(status_code=404, detail="Not found")


# Router-level dependency, not merely a first line in each handler:
# FastAPI validates the request body BEFORE calling the handler, so a
# gate that lived only in the handler would let `POST /sessions {}`
# answer 422 with the required field names while the flag was off --
# announcing both that the route exists and what it wants. A dependency
# resolves before body validation, so the 404 wins. The per-handler
# calls are kept as well; they cost nothing and keep each handler
# correct on its own.
router = APIRouter(
    prefix="/api/google-picker",
    tags=["google-picker"],
    dependencies=[Depends(_require_enabled)],
)


# -- error mapping ----------------------------------------------------------

# Repository refusals that this router can provoke, mapped to the status
# that says what actually happened. A cross-person trip or a token-shaped
# external_ref must never reach the client as a 500.
_REPO_STATUS = {
    repo.CrossPersonError: 409,
    repo.CrossTripError: 409,
    repo.ExternalTokenError: 400,
    repo.IntakeIsNotApprovalError: 409,
    repo.InvalidStateError: 400,
    repo.BatchNotFoundError: 404,
    # Ingest can provoke this one and Phase 1 could not: landing a
    # candidate in a closed or failed batch. 409 rather than 400 -- the
    # request was well formed, the batch is simply not accepting, and
    # `POST /api/import/batches/{id}/reopen` is the fix.
    repo.BatchClosedError: 409,
}

# Auth failures, mapped. `credentials_missing` is 503 rather than 500
# because the service genuinely is not configured yet, and
# `refresh_token_expired` is its own code so the operator is told to
# re-authorize instead of hunting a broken route.
_AUTH_STATUS = {
    "credentials_missing": 503,
    "refresh_token_expired": 503,
    "network": 502,
    "auth_failed": 502,
}

_UPSTREAM_STATUS = {
    "network": 502,
    "upstream_forbidden": 502,
    "session_not_found": 404,
    "upstream_rate_limited": 503,
    "upstream_error": 502,
}


def _repo_http(exc: Exception) -> HTTPException:
    for cls, status in _REPO_STATUS.items():
        if isinstance(exc, cls):
            return HTTPException(status_code=status, detail=str(exc))
    logger.exception("google_picker: unmapped repository error")
    return HTTPException(status_code=500, detail="import repository error")


def _access_token() -> str:
    try:
        return oauth.get_access_token()
    except oauth.PickerAuthError as exc:
        raise HTTPException(
            status_code=_AUTH_STATUS.get(exc.reason, 502),
            detail={"detail": str(exc), "reason": exc.reason},
        ) from None


def _upstream_http(exc: picker_client.PickerApiError) -> HTTPException:
    return HTTPException(
        status_code=_UPSTREAM_STATUS.get(exc.reason, 502),
        detail={"detail": str(exc), "reason": exc.reason,
                "upstream_status": exc.status},
    )


# -- batch lookup -----------------------------------------------------------

def _picker_batch(batch_id: str) -> Dict[str, Any]:
    """Load a batch and refuse it if it is not a picker batch.

    Addressing a Takeout or local_upload batch through a picker route
    would be a caller mistake that this lane should name, not absorb --
    its ``external_ref`` would not be a Picker session id and the call to
    Google would fail with something far less legible.
    """
    batch = repo.batch_get(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="batch not found")
    if batch.get("source") != PICKER_SOURCE:
        raise HTTPException(
            status_code=409,
            detail="batch %s is a %r import, not a %s batch; picker session "
                   "routes only address picker batches."
                   % (batch_id, batch.get("source"), PICKER_SOURCE),
        )
    session_id = (batch.get("external_ref") or "").strip()
    if not session_id:
        raise HTTPException(
            status_code=409,
            detail="batch %s has no picker session id in external_ref. It was "
                   "opened without a Google session, or the session was never "
                   "recorded." % batch_id,
        )
    return batch


# -- bodies -----------------------------------------------------------------

class SessionCreateBody(BaseModel):
    """``person_id`` is required and is never defaulted, here or in the
    repository. A picker session that inferred its person would be one
    bad inference away from landing someone else's photographs in a
    narrator's evidence queue.

    ``trip_id`` is optional. When the operator is standing in a trip the
    UI passes it and the batch auto-binds (Chris's decision (e)); the
    repository independently refuses a trip that belongs to a different
    person, and ``PATCH /batches/{id}/trip`` on the provenance router
    corrects a mistake afterward.
    """
    person_id: str = Field(..., min_length=1)
    trip_id: Optional[str] = None
    label: Optional[str] = None
    created_by_user_id: Optional[str] = None


class IngestBody(BaseModel):
    """Optional. ``POST .../ingest`` with no body ingests the whole
    selection, which is the ordinary case.

    ``max_items`` exists for the first real run against a large
    selection, where downloading five hundred originals to discover a
    configuration problem is an expensive way to learn it. When it
    truncates, the response says so in three fields rather than one:
    ``picked`` is the true size of the selection, ``truncated`` is true,
    and ``remaining`` counts what was left behind. A cap that quietly
    reported success over a partial run would read as "the operator
    picked fewer photos" -- the same lie ``list_media_items`` refuses to
    tell about a partial page listing.
    """
    max_items: Optional[int] = Field(default=None, ge=1, le=1000)


# -- routes -----------------------------------------------------------------

@router.get("/health")
def picker_health() -> Dict[str, Any]:
    """Configuration readout. Presence booleans only -- never a value.

    A 404 from this route means one of the two flags is off; that IS the
    diagnosis, and it is why the route is behind the gate like every
    other one here.
    """
    _require_enabled()
    present = oauth.credentials_present()
    return {
        "ok": True,
        "lane": "google_photos_picker",
        # 2, not 1. This number is read by an operator deciding whether
        # the stack in front of them can ingest; it said 1 for a day
        # after the acquisition module landed and would have said 1
        # forever if nobody had gone looking for the statements the
        # route falsified.
        "phase": 2,
        "flags": {
            "HORNELORE_GOOGLE_PICKER": _picker_enabled(),
            "HORNELORE_IMPORT_PROVENANCE": _provenance_enabled(),
        },
        # Booleans. Not values, not prefixes, not lengths.
        "credentials_present": present,
        "credentials_complete": all(present.values()),
        "token_cache": oauth.cache_state(),
        "scope": oauth.PICKER_SCOPE,
        # Stated in the payload so an operator reading /health knows why
        # re-authorization keeps coming round, without reading the spec.
        "notes": [
            "Credentials are read from the process environment only; this "
            "endpoint reports presence, never values.",
            "A project in 'Testing' publishing status expires refresh tokens "
            "every 7 days for this scope.",
            "Ingest downloads original bytes and creates pending candidates "
            "in the existing evidence review queue. It never promotes, and "
            "it never records an operator decision.",
        ],
        "max_item_bytes": acquire.max_bytes(),
        "ingest_available": True,
    }


@router.post("/sessions")
def create_picker_session(body: SessionCreateBody) -> Dict[str, Any]:
    """Create a Picker session at Google and open the matching batch.

    Order matters. Google is called FIRST: if the session cannot be
    created, no batch row is written, and the operator does not end up
    with an empty picker batch that can never receive candidates. The
    reverse order would leave debris on every upstream failure, and this
    lane has no DELETE to clean it up with.
    """
    _require_enabled()
    token = _access_token()

    try:
        session = picker_client.create_session(token)
    except picker_client.PickerApiError as exc:
        raise _upstream_http(exc) from None

    try:
        batch_id = repo.batch_create(
            person_id=body.person_id,
            source=PICKER_SOURCE,
            trip_id=body.trip_id,
            external_ref=session["session_id"],
            label=body.label,
            created_by_user_id=body.created_by_user_id,
        )
    except Exception as exc:
        # The batch could not be opened -- most likely an unknown person
        # or a trip that belongs to someone else. Hand the Google session
        # back rather than abandoning it: it costs one call and leaves no
        # orphaned session sitting in the operator's Google account.
        try:
            picker_client.delete_session(token, session["session_id"])
        except picker_client.PickerApiError:
            logger.warning("google_picker: could not release the picker "
                           "session after a failed batch open")
        raise _repo_http(exc) from None

    logger.info("google_picker: opened batch %s for person %s (trip=%s)",
                batch_id, body.person_id, body.trip_id)
    return {
        "ok": True,
        "batch_id": batch_id,
        "person_id": body.person_id,
        "trip_id": body.trip_id,
        "picker_uri": session["picker_uri"],
        "media_items_set": session["media_items_set"],
        "poll_interval": session["poll_interval"],
        "timeout_in": session["timeout_in"],
        "expire_time": session["expire_time"],
        "next": "Open picker_uri, choose photos, then poll "
                "GET /api/google-picker/sessions/{batch_id} until "
                "media_items_set is true, then POST "
                "/api/google-picker/sessions/{batch_id}/ingest.",
    }


@router.get("/sessions/{batch_id}")
def get_picker_session(batch_id: str) -> Dict[str, Any]:
    """Poll Google for this batch's session.

    ``media_items_set`` flipping to true means the operator has finished
    picking, which is the precondition ingest checks for. This route
    reports it and does nothing else -- polling must stay free of side
    effects, because the UI calls it on a timer.
    """
    _require_enabled()
    batch = _picker_batch(batch_id)
    token = _access_token()

    try:
        session = picker_client.get_session(token, batch["external_ref"])
    except picker_client.PickerApiError as exc:
        raise _upstream_http(exc) from None

    return {
        "ok": True,
        "batch_id": batch_id,
        "batch_status": batch.get("status"),
        "person_id": batch.get("person_id"),
        "trip_id": batch.get("trip_id"),
        "media_items_set": session["media_items_set"],
        "poll_interval": session["poll_interval"],
        "timeout_in": session["timeout_in"],
        "expire_time": session["expire_time"],
        "phase": 2,
        # True now, and gated on the same two things the route itself
        # checks so the UI is never told to offer a button that will
        # answer 409: the operator has finished picking, and the batch
        # can still accept candidates.
        "ingest_available": bool(session["media_items_set"])
                            and batch.get("status") == "open",
        "ingest_path": "/api/google-picker/sessions/%s/ingest" % batch_id,
    }


# -- ingest -----------------------------------------------------------------
#
# Spec 12.2's required order, which the rest of this section exists to
# keep:
#
#     download to a temp file -> validate it -> extract metadata ->
#     candidate_create() -> take the id it ACTUALLY returned ->
#     move the bytes into that id's directory
#
# The order is not stylistic. `candidate_create()` is idempotent on
# `(batch_id, external_id)` and DISCARDS any `candidate_id` the caller
# passes when a row already exists, so bytes staged under a preallocated
# id are orphaned on the first re-ingest -- a directory of real
# photographs that no row points at and no operator will ever see.

# The upstream failures that mean the PICKING SESSION ITSELF is gone,
# rather than a bad moment on the way to it. Only these close the batch.
_SESSION_UNUSABLE = ("session_not_found",)

# The per-item outcomes this route reports. `failed` is the only one that
# carries a `reason` and a `retryable` flag; the other three succeeded.
INGEST_OUTCOMES = ("created", "repaired", "unchanged", "failed")

# Failure reasons this ROUTE adds to the ones `acquire` already
# classifies, with the same retryable/permanent split. Kept as data for
# the same reason `acquire` keeps its own: so the `reason` field in the
# response has exactly one vocabulary behind it, and so a new reason
# cannot be introduced without landing somewhere in it.
_ROUTE_REASONS: Dict[str, bool] = {
    "candidate_already_promoted": False,
    "repository_refused": False,
    "unexpected_error": True,
}

# `hash_mismatch` was in this table until 2026-07-29 and is deliberately
# gone rather than merely unused. It was emitted when a fresh Google
# download hashed differently from the candidate row -- which doctrine
# 1.14 established is the ordinary behaviour of the provider and not a
# fault of any kind. Chris, 2026-07-29: "A hash_mismatch should remain an
# error only for a local integrity problem or an unsafe write
# condition -- not because two separate Google fetches differ." Nothing
# in this lane now meets that description, because the local copy is
# checked against its own row before any network call and a failed check
# is repaired rather than reported. Leaving the name here unemitted would
# advertise a classification this route can no longer make.

# Asserted at import, not tested for politely at runtime: a reason that
# existed in both vocabularies would resolve to whichever one the reader
# happened to consult, and the two would disagree about whether an
# operator should retry.
for _reason in _ROUTE_REASONS:
    if (_reason in acquire.RETRYABLE_REASONS
            or _reason in acquire.PERMANENT_REASONS):
        raise AssertionError(
            "google_picker router: %r is classified both here and in "
            "acquire" % _reason)
del _reason


# What `_ingest_one` hands `_settle_existing` in place of a download it
# has already performed: a zero-argument call returning the
# `(downloaded, meta)` pair, to be made only if the local copy turns out
# to need repairing. Named rather than spelled out at the one use site
# because the point of the type is that the fetch has not happened yet.
_Fetch = Callable[[], Tuple[Dict[str, Any], Dict[str, Any]]]


def _discard(tmp_path: Optional[str]) -> None:
    """Remove a temporary download that never became a staged original.

    Every item path ends here, success or failure. After a successful
    staging the file has already been renamed away and this is a no-op;
    after any failure downstream of the download it is the only thing
    standing between a partial run and an incoming directory that gains
    a full-size photograph nobody holds a reference to, every time an
    item fails.
    """
    if not tmp_path:
        return
    try:
        os.unlink(tmp_path)
    except OSError:
        pass


def _staged_original(batch_id: str, candidate_id: str) -> Optional[Path]:
    """The one ``original.*`` in a candidate's staging directory, or None.

    None means "not staged as Phase 3 will require it" and deliberately
    covers three cases that all want the same answer: the directory does
    not exist, it is empty, or it holds more than one ``original.*``.
    Phase 3 resolves the directory and requires exactly one file in it,
    so a directory holding two is already broken -- and re-staging is
    the repair, because ``stage_original`` writes the new one and then
    removes the stale extensions.
    """
    try:
        target_dir = acquire.staging_dir_for(batch_id, candidate_id)
    except acquire.AcquireError:
        return None
    try:
        found = sorted(p for p in target_dir.glob("original.*") if p.is_file())
    except OSError:
        return None
    return found[0] if len(found) == 1 else None


def _existing_by_external_id(batch_id: str) -> Dict[str, Dict[str, Any]]:
    """The batch's candidates, read once, indexed by provider item id.

    Read once before the loop rather than once per item: a five-hundred
    photo selection would otherwise be five hundred extra queries to
    answer a question one query answers.

    ``include_hidden=True`` on purpose. A hidden candidate is still a row
    that owns ``(batch_id, external_id)``, and the UNIQUE index does not
    care that an operator retired it. Ingest must find it and take the
    re-ingest branch rather than trying to create a second row behind it.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for cand in repo.candidates_list(batch_id=batch_id, include_hidden=True):
        ext = cand.get("external_id")
        if isinstance(ext, str) and ext:
            out[ext] = cand
    return out


def _match_reason(item: Dict[str, Any], downloaded: Dict[str, Any],
                  meta: Dict[str, Any]) -> Dict[str, Any]:
    """What the review queue is told about how this candidate arrived.

    Three rules govern what may go in here, and each of them is a rule
    because breaking it would be invisible afterwards.

    IT CARRIES NO CREDENTIAL AND NO DOWNLOAD URL. ``baseUrl`` is absent
    by construction, and ``import_repository._assert_reason_clean`` would
    refuse it anyway -- along with any key containing ``token``, ``auth``,
    ``secret`` or ``session_id``, which is why nothing here is named
    after the picking session even though naming it would be convenient.

    IT CARRIES NO STAGING PATH. Spec 12.5: ``match_reason`` is
    effectively write-once, because the repository offers
    ``candidate_set_trip``, ``candidate_decide`` and ``candidate_hide``
    and no function at all that updates candidate metadata. A path or a
    ``{"staging": {"verified": true}}`` claim recorded here could never
    be corrected after the file was repaired, moved or found corrupt.
    Phase 3 derives the path from the two ids it already holds.

    IT DOES CARRY ``gps_present_unparseable``, and this is the only place
    that value can live. ``photo_intake/exif.py`` distinguishes three
    states: GPS read, GPS absent, and GPS present but undecodable. The
    candidate columns express the first two -- coordinates plus
    ``location_source`` -- and have nowhere to put the third. Dropping it
    would tell a reviewer "this photograph has no location" about a
    photograph that plainly has one, so it is recorded as the fact it is.
    The location columns still stay null: an unparseable tag is evidence
    that a coordinate exists, not a coordinate.
    """
    reason: Dict[str, Any] = {
        "source": PICKER_SOURCE,
        "provider_media_type": item.get("media_type"),
        "provider_mime_type": item.get("mime_type"),
        "verified_mime": downloaded["verified_mime"],
        "metadata_trust": meta.get("metadata_trust"),
    }
    if meta.get("trust_reasons"):
        reason["trust_reasons"] = list(meta["trust_reasons"])

    width, height = item.get("width"), item.get("height")
    if isinstance(width, int) and isinstance(height, int):
        reason["provider_dimensions"] = {"width": width, "height": height}

    # Recorded only when true, and only ever as true. A `false` on every
    # ordinary photograph would read as a checked-and-cleared claim and
    # would bury the handful of cases that mean something; its absence
    # is the ordinary case.
    if meta.get("gps_present_unparseable"):
        reason["gps_present_unparseable"] = True

    # The provider disagreed with the bytes. Not an error -- the bytes
    # won, which is the entire point of sniffing rather than trusting a
    # declared MIME type -- but worth having on the record if a
    # photograph later turns out to be something other than it claimed.
    if downloaded["verified_mime"] != (item.get("mime_type") or ""):
        reason["provider_mime_disagreed"] = True

    return reason


def _settle_existing(batch_id: str, existing: Dict[str, Any],
                     result: Dict[str, Any],
                     fetch: _Fetch) -> Dict[str, Any]:
    """The re-ingest branch: THE LOCAL COPY IS EXAMINED BEFORE THE NETWORK.

    Doctrine 1.14. ``external_id`` is the identity of the picked item and
    ``file_hash`` is the checksum of the working copy Hornelore staged.
    Those are two different facts about two different objects, and a
    later fetch from the provider is not expected to reproduce the
    earlier bytes -- three separate fetches of the same seven
    photographs returned three different byte counts for two of them and
    disagreed with the stored size on all seven. A fresh download
    therefore cannot be used to decide whether an existing candidate is
    intact. Only the staged file can answer that, and it is already on
    disk.

    So the order below is the entire correction:

        candidate exists
        |
        +- staged copy hashes to the stored file_hash
        |     -> unchanged, AND NOTHING IS FETCHED
        |
        +- staged copy missing or corrupt, photo_id is null
        |     -> fetch, re-stamp the byte-derived row fields, re-stage
        |     -> repaired
        |
        +- staged copy missing or corrupt, photo_id is set
              -> refuse: candidate_already_promoted, permanent

    WHAT THIS USED TO DO, because the change is a reversal and not a
    refinement. Until 2026-07-29 the download happened first and its hash
    was compared against the row: equal meant ``unchanged``, different
    meant a permanent ``hash_mismatch`` failure. Both halves were wrong
    at once. It spent a full-size download on every already-complete
    item, and it then read the provider's ordinary byte jitter as a local
    integrity fault -- a live second ingest of seven intact photographs
    refused all seven. Chris, 2026-07-29: "Why are we downloading again
    at all? ... That avoids Google's byte jitter entirely."

    THE STAGED FILE IS HASHED, NOT MERELY COUNTED, and that survives the
    reversal unchanged. "A file called ``original.jpg`` is present" is a
    weaker claim than "the bytes this candidate row describes are on
    disk", and only the second is worth reporting as ``unchanged``; the
    first would let a truncated or overwritten original sit behind a row
    that says it is fine. The digest costs one read of a local file,
    which is now the cheap half of the comparison rather than the
    expensive one.

    A ROW CARRYING NO ``file_hash`` IS REPAIRED RATHER THAN REFUSED, and
    this too changed direction. It used to be treated as a mismatch on
    the grounds that this lane always writes a hash, so a row without one
    came from somewhere else. That reasoning assumed the repair could not
    write a hash. It can now: the fetch produces bytes, the bytes produce
    a digest, and ``candidate_restage`` stamps it. An unverifiable row is
    exactly the condition a repair exists to end.

    THE REFUSAL IS STILL NOT A CANDIDATE STATE. Marking the row ``error``
    would mean ``candidate_decide()``, which is hard one-way -- it raises
    ``CandidateAlreadyDecidedError`` on anything but ``pending``, there is
    no undecide, and there is no DELETE on this lane -- so a refusal
    would become a permanent operator-review verdict that no operator
    made (spec 12.3). It is reported as a per-item failure instead, and
    the row and its bytes are left exactly as they were.
    """
    candidate_id = existing["id"]
    result["candidate_id"] = candidate_id
    stored_hash = existing.get("file_hash")

    staged = _staged_original(batch_id, candidate_id)
    on_disk: Optional[str] = None
    if staged is not None:
        try:
            on_disk = acquire.hash_file(staged)
        except OSError:
            # A staged file that cannot be read is a staged file that
            # cannot be trusted, which is the repair condition rather
            # than an error to report. It falls through.
            on_disk = None

    if stored_hash and on_disk == stored_hash:
        # Reported from the ROW, deliberately. Nothing was fetched, so
        # the row is the only description of these bytes in existence,
        # and a result dict missing `file_hash` and `byte_size` on the
        # ordinary re-ingest path would read as "not known" rather than
        # "not re-measured".
        result["staged_verified"] = True
        result["file_hash"] = stored_hash
        result["byte_size"] = existing.get("byte_size")
        result["mime_type"] = existing.get("mime_type")
        result["taken_at"] = existing.get("taken_at")
        result["taken_at_source"] = existing.get("taken_at_source")
        result["location_source"] = existing.get("location_source")
        result["has_exif_gps"] = existing.get("location_source") == "exif_gps"
        return dict(result, outcome="unchanged",
                    detail="candidate %s already exists and its staged "
                           "original still hashes to the file_hash on the "
                           "row. Nothing was written and nothing was "
                           "downloaded." % candidate_id)

    if not stored_hash:
        repaired_from, was = ("unverifiable_row",
                              "a candidate row carrying no file hash, so "
                              "the bytes on disk could not be shown to "
                              "match it")
    elif staged is None:
        repaired_from, was = ("missing", "no staged original")
    else:
        repaired_from, was = ("hash_disagreement",
                              "a staged original whose bytes did not hash "
                              "to the candidate's file_hash")

    # Doctrine 1.14's archive boundary, checked BEFORE the fetch so a
    # refusal costs no bandwidth and touches no file. `candidate_restage`
    # refuses the same case at the repository; that is the enforcement
    # and this is the early exit, and the two are not redundant -- a
    # guard that lives only in a caller is a guard the next caller does
    # not inherit.
    if existing.get("photo_id"):
        return dict(result, outcome="failed",
                    reason="candidate_already_promoted", retryable=False,
                    file_hash=stored_hash,
                    staged_verified=False,
                    detail="candidate %s already points to a permanent "
                           "archive photo. Re-staging the working copy "
                           "cannot rewrite the candidate hash or re-point "
                           "the archive. The staging directory held %s, and "
                           "the repair this case needs is restoring the "
                           "working copy from the archive object rather "
                           "than fetching the provider again. That is not "
                           "built, so nothing was touched."
                           % (candidate_id, was))

    downloaded, meta = fetch()

    # THE ROW FIRST, THE BYTES SECOND, and the order is the safe one of
    # the two. `candidate_restage` is where the promoted-candidate
    # refusal is enforced, so calling it before anything moves means a
    # refusal leaves the staging directory exactly as it was found; the
    # reverse order would replace a promoted candidate's working copy and
    # only then discover it was not allowed to. The cost of this order is
    # that a crash between the two leaves a row describing bytes that are
    # not on disk -- which is precisely the condition the branch above
    # detects and repairs on the next run, so the failure mode is
    # self-healing in a way the other order's is not.
    repo.candidate_restage(
        candidate_id,
        file_hash=downloaded["file_hash"],
        byte_size=downloaded["byte_size"],
        mime_type=downloaded["verified_mime"],
        taken_at=meta["taken_at"],
        taken_at_source=meta["taken_at_source"],
        latitude=meta["latitude"],
        longitude=meta["longitude"],
        location_source=meta["location_source"],
    )
    acquire.stage_original(downloaded["tmp_path"], batch_id, candidate_id,
                           downloaded["verified_ext"])

    logger.info("google_picker: repaired candidate %s in batch %s (%s)",
                candidate_id, batch_id, repaired_from)
    return dict(result, outcome="repaired", staged_verified=True,
                repaired_from=repaired_from,
                previous_file_hash=stored_hash,
                detail="candidate %s already existed but the staging "
                       "directory held %s. The item was fetched again as a "
                       "repair, the working copy was replaced atomically, "
                       "and the byte-derived fields on the row were "
                       "re-stamped to describe the bytes now on disk. The "
                       "candidate's identity, state, placement and review "
                       "fields were not touched." % (candidate_id, was))


def _ingest_one(token: str, batch_id: str, item: Dict[str, Any],
                existing: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """One picked item, start to finish, never raising.

    Every exit is a result dict, because the run must not stop. An item
    that fails is one photograph the operator retries; an exception that
    escapes here is every photograph after it, silently not attempted.

    THE DOWNLOAD SITS BEHIND A CALLABLE, and that is the shape of the
    2026-07-29 correction rather than a decoration on it. `_settle_existing`
    has to be able to answer `unchanged` without fetching and to fetch
    when it decides to repair, so the download cannot happen before the
    branch -- and it still has to leave its temporary file somewhere the
    single `finally` below can reach it, and still has to stamp the
    byte-derived fields onto `result` exactly once, whichever branch
    asked for it. `_fetch` closes over all three obligations so that
    neither branch can forget one.
    """
    item_id = item["media_item_id"]
    result: Dict[str, Any] = {"media_item_id": item_id,
                              "filename": item.get("filename")}

    # A provider-declared VIDEO is refused before a byte is fetched, and
    # note the direction carefully: the declared type is trusted to
    # REFUSE and never to ACCEPT. An item Google calls a photo is still
    # identified by its own leading bytes in `sniff_image`, so a
    # mislabelled video cannot get in this way. The only cost of a
    # mislabelled photo is that this lane skips it and says so, against
    # the alternative of streaming a multi-gigabyte movie to reach the
    # same conclusion. Consistent with `acquire`: video produces no
    # candidate row at all, because an `error` candidate would be a
    # decision nobody made and could never be cleared.
    if (item.get("media_type") or "").upper() == "VIDEO":
        return dict(result, outcome="failed", reason="unsupported_content",
                    retryable=False,
                    detail="Google lists this item as a video. This lane "
                           "stages photographs only; no candidate row was "
                           "created for it.")

    tmp_path: Optional[str] = None

    def _fetch() -> Tuple[Dict[str, Any], Dict[str, Any]]:
        nonlocal tmp_path
        downloaded = acquire.download_original(
            token, item["base_url"], item_id=item_id, batch_id=batch_id)
        tmp_path = downloaded["tmp_path"]
        meta = acquire.read_evidence_metadata(
            tmp_path, provider_create_time=item.get("create_time"))

        result.update({
            "byte_size": downloaded["byte_size"],
            "file_hash": downloaded["file_hash"],
            "mime_type": downloaded["verified_mime"],
            "taken_at": meta["taken_at"],
            "taken_at_source": meta["taken_at_source"],
            "location_source": meta["location_source"],
            "has_exif_gps": meta["location_source"] == "exif_gps",
        })
        if meta.get("gps_present_unparseable"):
            result["gps_present_unparseable"] = True
        return downloaded, meta

    try:
        if existing is not None:
            return _settle_existing(batch_id, existing, result, _fetch)

        downloaded, meta = _fetch()

        # Spec 12.2, in order. The id is taken from the return value and
        # is never assumed to be one we chose.
        candidate_id = repo.candidate_create(
            batch_id=batch_id,
            external_id=item_id,
            file_hash=downloaded["file_hash"],
            filename=item.get("filename"),
            mime_type=downloaded["verified_mime"],
            byte_size=downloaded["byte_size"],
            taken_at=meta["taken_at"],
            taken_at_source=meta["taken_at_source"],
            # EXIF GPS reaches the candidate here, and only EXIF GPS.
            # `acquire.read_evidence_metadata` has already refused to let
            # provider metadata become a location source, so these three
            # values are either a real coordinate pair with
            # `exif_gps`, or null/null/`unknown`.
            latitude=meta["latitude"],
            longitude=meta["longitude"],
            location_source=meta["location_source"],
            match_reason=_match_reason(item, downloaded, meta),
        )
        result["candidate_id"] = candidate_id

        # Only now do the bytes move, and they move into the id the
        # repository actually returned.
        acquire.stage_original(tmp_path, batch_id, candidate_id,
                               downloaded["verified_ext"])
        return dict(result, outcome="created")

    except acquire.AcquireError as exc:
        # `retryable` is read off the exception rather than decided here.
        # It is derived in `acquire` from the reason, through one table,
        # so this route cannot tell an operator something the module
        # would contradict.
        return dict(result, outcome="failed", reason=exc.reason,
                    retryable=exc.retryable, detail=str(exc))

    except repo.CandidateAlreadyPromotedError as exc:
        # Caught ahead of `ImportRepositoryError` on purpose. The branch
        # in `_settle_existing` normally returns this refusal before a
        # byte is fetched; reaching it here means the candidate was
        # promoted between that read and this write. It is the same
        # refusal and must carry the same name, because an operator
        # reading `repository_refused` would have no way to tell it from
        # an off-enum value or a cross-person trip.
        return dict(result, outcome="failed",
                    reason="candidate_already_promoted", retryable=False,
                    detail=str(exc))

    except repo.ImportRepositoryError as exc:
        # A repository refusal about ONE item -- an off-enum value, a
        # token-shaped filename, a trip that belongs to someone else.
        # Permanent, because re-running produces the same refusal.
        #
        # `BatchClosedError` reaches here too, if the batch is closed
        # between the route's pre-check and this item. Every remaining
        # item then fails the same way and says so, which is verbose but
        # true; it is not allowed to abort the loop, because "one failed
        # item does not stop later items" should hold without an
        # exception clause that has to be remembered.
        return dict(result, outcome="failed", reason="repository_refused",
                    retryable=False, detail=str(exc))

    except Exception as exc:
        # Class name only, and no traceback. A traceback logged here
        # could carry a `requests` exception whose string form is the
        # full bearer-scoped download URL -- which is the one value in
        # this lane that must never reach a log file.
        logger.error("google_picker: unexpected %s while ingesting one item "
                     "in batch %s", exc.__class__.__name__, batch_id)
        return dict(result, outcome="failed", reason="unexpected_error",
                    retryable=True,
                    detail="an unexpected %s occurred while ingesting this "
                           "item" % exc.__class__.__name__)

    finally:
        # Unconditional, and it reads the value `_fetch` set rather than
        # one this function assigned, so the `unchanged` path -- which
        # never fetches and leaves this None -- is covered by the same
        # line as every other. On the created and repaired paths the file
        # has already been renamed away and this does nothing.
        _discard(tmp_path)


def _session_http(batch_id: str,
                  exc: picker_client.PickerApiError) -> HTTPException:
    """Map an upstream failure, and close the batch ONLY when the picking
    session itself is gone.

    Spec 12.4 is precise about this and the precision is the point. There
    is no column that can hold a per-run partial failure summary: the
    only writer of ``import_batch.failure_reason`` is
    ``batch_close(failed=True, ...)``, which also sets the status to
    ``failed``, and ``batch_reopen()`` clears it outright -- so
    persisting a partial summary and then retrying are mutually
    exclusive under today's schema. ``failed`` is therefore reserved for
    the batch-level failure the column was actually built for: the
    picking session no longer exists, so nothing further can ever be
    listed or downloaded from it.

    A network blip, a rate limit, or a token that needs re-minting are
    moments, not verdicts. The batch stays open through all of them,
    because a retryable failure with the batch closed behind it is not
    retryable at all -- somebody would have to reopen the batch by hand
    before the retry the response invited could work.
    """
    if exc.reason in _SESSION_UNUSABLE:
        try:
            repo.batch_close(
                batch_id, failed=True,
                failure_reason="the Google picking session for this batch is "
                               "no longer available, so no further items can "
                               "be listed or downloaded from it. Candidates "
                               "that already landed are untouched. Reopen "
                               "the batch only if a new picking session is "
                               "created for it.")
            logger.info("google_picker: closed batch %s failed -- its picking "
                        "session no longer exists", batch_id)
        except Exception as close_exc:
            # The upstream failure is still the operator's answer; being
            # unable to record it must not replace it with a different
            # error about bookkeeping.
            logger.warning("google_picker: could not record the batch-level "
                           "failure for batch %s (%s)",
                           batch_id, close_exc.__class__.__name__)
    return _upstream_http(exc)


@router.post("/sessions/{batch_id}/ingest")
def ingest_picker_session(
    batch_id: str,
    body: Optional[IngestBody] = None,
) -> Dict[str, Any]:
    """Download what the operator picked and land it as pending candidates.

    Idempotent, and idempotent WITHOUT RE-FETCHING. Running it twice over
    the same selection creates nothing the second time and downloads
    nothing the second time: ``candidate_create()`` is idempotent on
    ``(batch_id, external_id)``, and the re-ingest branch above hashes
    the staged working copy against the ``file_hash`` already on the row
    before any request is made. Only a working copy that is missing or no
    longer hashes to its row reaches the network, and then as a repair --
    the fresh bytes become the staged copy and the row is re-stamped to
    describe them. Running it again after a partial failure is the
    retry -- that is what "leave the batch open" is for.

    Until 2026-07-29 this docstring claimed the same idempotence while
    the code downloaded every item first and compared the fresh hash to
    the row, which made a second run over an intact selection fetch
    everything and then refuse everything. The claim is true now because
    the order changed, not because the wording did.

    What it never does: promote, write a ``photos`` row, or call
    ``candidate_decide()``. Every candidate it creates is born
    ``pending`` and visible in the existing Evidence Review Queue with
    no further step, because ``candidates_list`` reads ``hidden = 0``
    ordered oldest-first and a new row satisfies that by existing.
    """
    _require_enabled()
    batch = _picker_batch(batch_id)

    if batch.get("status") != "open":
        raise HTTPException(
            status_code=409,
            detail="batch %s is %s; candidates cannot land in it. Reopen it "
                   "with POST /api/import-provenance/batches/%s/reopen and "
                   "run ingest again."
                   % (batch_id, batch.get("status"), batch_id),
        )

    token = _access_token()

    # Poll first. Ingesting a selection the operator has not finished
    # making would download a half-chosen set and record it as the
    # import -- and the second run would then see every later photo as
    # new while the first batch already claimed to be complete.
    try:
        session = picker_client.get_session(token, batch["external_ref"])
    except picker_client.PickerApiError as exc:
        raise _session_http(batch_id, exc) from None

    if not session.get("media_items_set"):
        raise HTTPException(
            status_code=409,
            detail={"detail": "the operator has not finished picking for "
                              "batch %s. Poll GET "
                              "/api/google-picker/sessions/%s until "
                              "media_items_set is true, then ingest."
                              % (batch_id, batch_id),
                    "reason": "selection_incomplete",
                    "media_items_set": False},
        )

    try:
        items = picker_client.list_media_items(token, batch["external_ref"])
    except picker_client.PickerApiError as exc:
        raise _session_http(batch_id, exc) from None

    picked = len(items)
    limit = body.max_items if (body is not None and body.max_items) else None
    if limit is not None and picked > limit:
        items = items[:limit]
        # Said out loud. A cap that truncates silently is indistinguishable
        # from a selection that was smaller than the operator remembers.
        logger.info("google_picker: max_items=%d truncated the run for batch "
                    "%s -- attempting %d of %d picked item(s)",
                    limit, batch_id, len(items), picked)

    existing = _existing_by_external_id(batch_id)

    results: List[Dict[str, Any]] = []
    for item in items:
        results.append(
            _ingest_one(token, batch_id, item,
                        existing.get(item["media_item_id"])))

    counts = {outcome: 0 for outcome in INGEST_OUTCOMES}
    for entry in results:
        counts[entry["outcome"]] = counts.get(entry["outcome"], 0) + 1
    retryable_failures = sum(1 for entry in results
                             if entry["outcome"] == "failed"
                             and entry.get("retryable"))
    permanent_failures = counts["failed"] - retryable_failures

    logger.info("google_picker: ingest for batch %s -- %d picked, %d "
                "attempted, %d created, %d repaired, %d unchanged, %d failed "
                "(%d retryable)", batch_id, picked, len(items),
                counts["created"], counts["repaired"], counts["unchanged"],
                counts["failed"], retryable_failures)

    # Read the batch back rather than reporting what we loaded at the
    # top. The only thing in this route that closes a batch is
    # `_session_http`, which raises rather than returning -- so this
    # should always be `open`, and reporting the value rather than the
    # assumption is how a future change that breaks that gets noticed.
    batch_after = repo.batch_get(batch_id) or batch
    visible = repo.candidates_list(batch_id=batch_id)

    # Assembled from what actually happened rather than written once and
    # hoped over. Retry advice is offered only when there is something
    # retryable to offer it about: an operator told to "run ingest again"
    # after a run whose every failure was permanent will run it again,
    # get the identical refusals, and reasonably conclude the system is
    # broken. And the last sentence is a statement of the re-ingest rule
    # that is now true -- its predecessor, "nothing already landed is
    # re-downloaded", was false on the day it was written, because
    # everything already landed was re-downloaded and then refused.
    next_parts = ["Review the new candidates in the evidence queue."]
    if retryable_failures:
        next_parts.append(
            "%d item(s) failed retryably and can be picked up by running "
            "ingest again." % retryable_failures)
    if permanent_failures:
        next_parts.append(
            "%d item(s) failed permanently; running ingest again produces "
            "the same refusal, so read the per-item detail rather than "
            "retrying." % permanent_failures)
    next_parts.append(
        "Complete, locally verified candidates are not downloaded again. "
        "Missing or damaged staged files may be downloaded again for "
        "repair.")
    next_step = " ".join(next_parts)

    return {
        "ok": True,
        "batch_id": batch_id,
        "person_id": batch.get("person_id"),
        "trip_id": batch.get("trip_id"),
        "batch_status": batch_after.get("status"),
        "picked": picked,
        "attempted": len(items),
        "truncated": len(items) < picked,
        "remaining": picked - len(items),
        "created": counts["created"],
        "repaired": counts["repaired"],
        "unchanged": counts["unchanged"],
        "failed": counts["failed"],
        "retryable_failures": retryable_failures,
        "permanent_failures": permanent_failures,
        # Per-item, in the order Google listed the selection. This is the
        # only home a partial-run summary has -- spec 12.4 -- so it is
        # complete rather than truncated to the failures.
        "results": results,
        # Where the new candidates already are. Ingest does not build a
        # second review queue and does not need to: these rows are in
        # the existing one the moment they are created.
        "queue": {
            "candidates_in_batch": len(visible),
            "pending_in_batch": sum(1 for c in visible
                                    if c.get("state") == "pending"),
            "path": "/api/import-provenance/queue?person_id=%s&batch_id=%s"
                    % (batch.get("person_id"), batch_id),
        },
        "next": next_step,
    }


@router.delete("/sessions/{batch_id}")
def delete_picker_session(batch_id: str) -> Dict[str, Any]:
    """End the picking session AT GOOGLE. The batch survives.

    This is the one route in this lane whose verb is DELETE, and it is
    worth being precise about what it removes: a session handle in
    Google's system. It touches no row in this database. The evidence
    lane's no-DELETE rule is intact -- the ``import_batch`` and any
    candidates on it remain, and retirement is still ``hidden``.
    """
    _require_enabled()
    batch = _picker_batch(batch_id)
    token = _access_token()

    try:
        picker_client.delete_session(token, batch["external_ref"])
    except picker_client.PickerApiError as exc:
        if exc.reason == "session_not_found":
            # Google already dropped it. Nothing to do, and reporting a
            # 404 here would suggest the batch was missing.
            return {"ok": True, "batch_id": batch_id,
                    "picker_session_released": True,
                    "already_gone": True,
                    "batch_deleted": False}
        raise _upstream_http(exc) from None

    return {"ok": True, "batch_id": batch_id,
            "picker_session_released": True,
            "already_gone": False,
            # Said explicitly, in the payload, because this is the one
            # place in the lane where the word "delete" appears.
            "batch_deleted": False,
            "note": "The Google picking session was released. The import "
                    "batch and its candidates are untouched -- there is no "
                    "DELETE on the evidence lane."}
