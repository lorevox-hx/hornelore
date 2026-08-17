from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from typing import List, Optional

from ..db import get_projection, merge_projection_fields, upsert_projection

router = APIRouter(prefix="/api/interview", tags=["projection"])


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
    # Supplied -> that array is replaced. Omitted -> left alone, the same
    # rule the field mutations follow.
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
        pending_suggestions=payload.pendingSuggestions,
    )
    if saved.get("conflict"):
        # 409 with the NEWER server record in the body, so the client can
        # rebase its own dirty fields onto it instead of overwriting.
        response.status_code = 409
    return _as_response(saved)


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
