"""Google Photos Picker router -- WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01
Phase 1 (2026-07-27): credentials, health, and session lifecycle.

WHAT PHASE 1 DOES

    GET    /api/google-picker/health
    POST   /api/google-picker/sessions              {person_id, trip_id?, label?}
    GET    /api/google-picker/sessions/{batch_id}
    DELETE /api/google-picker/sessions/{batch_id}

``POST /sessions`` creates the Picker session at Google AND opens the
matching ``import_batch`` with ``source='google_photos_picker'``, storing
the Picker session id in the batch's ``external_ref``. That column was
built for exactly this -- migration 0037 describes it as an "opaque
provider-side handle for the fetch (an album id, a Takeout archive name,
an upload session id). NOT a token, NOT a URL with credentials in it."
The batch is the durable handle; every later route in this lane is
addressed by ``batch_id``, never by the Google session id, so the
provider handle never has to travel through a URL the operator pastes.

WHAT PHASE 1 DELIBERATELY DOES NOT DO, AND WHY

  * It downloads no bytes and creates no candidates. That is Phase 2.
    The listing call is not even implemented in ``picker_client`` -- an
    unused function is an invitation to reach past the phase wall.
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
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..services import import_repository as repo
from ...services.google_picker import oauth, picker_client

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
        "phase": 1,
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
            "Phase 1 creates sessions only. It downloads no bytes and creates "
            "no candidates.",
        ],
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
                "media_items_set is true. Ingest is Phase 2 and does not "
                "exist yet.",
    }


@router.get("/sessions/{batch_id}")
def get_picker_session(batch_id: str) -> Dict[str, Any]:
    """Poll Google for this batch's session.

    ``media_items_set`` flipping to true means the operator has finished
    picking. In Phase 1 that is the end of the road -- there is nothing
    to ingest with yet, and this route says so rather than implying a
    next step that does not exist.
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
        "phase": 1,
        "ingest_available": False,
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
