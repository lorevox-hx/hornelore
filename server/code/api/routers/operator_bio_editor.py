"""WO-LORI-BIO-BUILDER-UNIVERSAL-01 (2026-06-14) — Phase E Tier 4 router.

Operator-only bio editor endpoints. The Bug Panel surface
(bug-panel-bio-editor.js) consumes these endpoints; there is no
narrator-side route or surface. Per WO §Tier 4:

  - Operator entries write to bio_facts with status='operator_entered'
    and are immediately promoted to 'approved' (operator authority)
  - Conflict resolution promotes one row to 'approved' and marks the
    other rows 'superseded' with audit trail preserved

ENDPOINTS:

  GET /api/operator/bio-editor/facts?narrator_id=N1
      Lists all bio_facts rows for a narrator, grouped under their
      schema field definition. Shape:
        {
          "narrator_id": "N1",
          "fields": [
            {"field_key": ..., "field_label": ..., "field_category": ...,
             "narrative_value": ..., "rows": [...]},
            ...
          ],
          "fetched_at": "ISO8601"
        }
      Field entries appear in BIO_SCHEMA_SEED order so the UI renders
      categories together deterministically.

  POST /api/operator/bio-editor/enter
      Direct entry. Body: {"narrator_id": "N1", "field_key": "...",
      "value": <any>, "notes": "..." (optional)}. Writes a new
      bio_facts row at status='approved' with source
      tier=4 + operator_id + timestamp + notes.
      Returns the new fact_id.

  POST /api/operator/bio-editor/approve
      Promote an existing row to approved (operator confirming an
      extraction or document source). Body: {"fact_id": "..."}.
      Updates status; preserves source attribution.

  POST /api/operator/bio-editor/resolve-conflict
      Body: {"narrator_id": "N1", "field_key": "...",
      "promote_fact_id": "...", "supersede_fact_ids": [...]}.
      Promotes one row to 'approved'; marks listed rows 'superseded'.
      Both transitions preserve the source attribution + the
      conflict_with linking so the audit trail survives.

  POST /api/operator/bio-editor/mark-unanswerable
      Body: {"narrator_id": "N1", "field_key": "..."}. Writes a row
      at status='operator_entered' (treated as approved-empty) with
      value=null + source.unanswerable=true + tier=4. Used when the
      operator knows the field cannot be filled (narrator no longer
      remembers, no document, no living relative who knows).

BACKEND GATE: every endpoint short-circuits to 404 unless
HORNELORE_OPERATOR_BIO_EDITOR=1 is set in the server env. Mirrors
operator_eval_harness + operator_story_review default-OFF posture.

LAW 3 INFRASTRUCTURE: router imports stdlib + fastapi + ..db +
..services.bio_schema only. No extract.py or chat_ws.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .. import db
from ..services import bio_schema


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/operator/bio-editor",
                   tags=["operator", "bio-editor"])


# ─────────────────────────────────────────────────────────────────────
# Backend gate
# ─────────────────────────────────────────────────────────────────────


def _enabled() -> bool:
    """Default-OFF gate. Enable with HORNELORE_OPERATOR_BIO_EDITOR=1."""
    return os.environ.get(
        "HORNELORE_OPERATOR_BIO_EDITOR", "0",
    ).strip().lower() in ("1", "true", "yes", "on")


def _require_enabled() -> None:
    if not _enabled():
        raise HTTPException(
            status_code=404,
            detail="bio editor surface disabled",
        )


# ─────────────────────────────────────────────────────────────────────
# Request payloads
# ─────────────────────────────────────────────────────────────────────


class _DirectEntryRequest(BaseModel):
    narrator_id: str = Field(..., min_length=1)
    field_key: str = Field(..., min_length=1)
    value: Any
    notes: Optional[str] = None
    operator_id: Optional[str] = None


class _ApproveRequest(BaseModel):
    fact_id: str = Field(..., min_length=1)
    operator_id: Optional[str] = None


class _ResolveConflictRequest(BaseModel):
    narrator_id: str = Field(..., min_length=1)
    field_key: str = Field(..., min_length=1)
    promote_fact_id: str = Field(..., min_length=1)
    supersede_fact_ids: List[str] = Field(default_factory=list)
    operator_id: Optional[str] = None


class _MarkUnanswerableRequest(BaseModel):
    narrator_id: str = Field(..., min_length=1)
    field_key: str = Field(..., min_length=1)
    operator_id: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _operator_source(
    operator_id: Optional[str] = None,
    notes: Optional[str] = None,
    unanswerable: bool = False,
) -> str:
    payload = {
        "tier": 4,
        "operator_id": operator_id or "unknown",
        "timestamp": _now_iso(),
    }
    if notes:
        payload["notes"] = notes
    if unanswerable:
        payload["unanswerable"] = True
    return json.dumps(payload)


def _field_def_or_404(field_key: str) -> Any:
    fd = bio_schema.get_field_by_key(field_key)
    if not fd:
        raise HTTPException(
            status_code=400,
            detail=f"unknown field_key: {field_key}",
        )
    return fd


# ─────────────────────────────────────────────────────────────────────
# GET facts (grouped by field)
# ─────────────────────────────────────────────────────────────────────


@router.get("/facts")
def get_facts(
    narrator_id: str = Query(..., min_length=1),
) -> Dict[str, Any]:
    """List bio_facts grouped under their schema field definition.

    Fields appear in BIO_SCHEMA_SEED order so categories stay together
    in the operator UI; each field carries its rows (may be empty,
    one, or multiple — conflicts and audit trail).
    """
    _require_enabled()
    try:
        rows = db.bio_fact_list_by_narrator(narrator_id)
    except Exception as exc:
        logger.exception("[bio_editor] list_by_narrator failed")
        raise HTTPException(
            status_code=500,
            detail=f"db read failed: {exc}",
        )
    # Bucket rows by field_key
    by_field: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        fk = str(r.get("field_key") or "")
        by_field.setdefault(fk, []).append(r)
    # Walk the seed in deterministic order
    fields_out: List[Dict[str, Any]] = []
    for fd in bio_schema.iter_seed():
        fields_out.append({
            "field_key": fd.field_key,
            "field_label": fd.field_label,
            "field_category": fd.field_category,
            "field_type": fd.field_type,
            "narrative_value": fd.narrative_value,
            "rows": by_field.get(fd.field_key, []),
        })
    return {
        "narrator_id": narrator_id,
        "fields": fields_out,
        "fetched_at": _now_iso(),
    }


# ─────────────────────────────────────────────────────────────────────
# POST direct entry
# ─────────────────────────────────────────────────────────────────────


@router.post("/enter")
def post_enter(req: _DirectEntryRequest) -> Dict[str, Any]:
    """Direct operator entry. Per WO §Tier 4: writes a new bio_facts
    row at status='approved' (operator authority promotes immediately).
    Source carries operator_id + notes + tier=4.
    """
    _require_enabled()
    _field_def_or_404(req.field_key)
    try:
        new_id = db.bio_fact_create(
            narrator_id=req.narrator_id,
            field_key=req.field_key,
            value_json=json.dumps(req.value),
            status="approved",
            source_json=_operator_source(
                operator_id=req.operator_id,
                notes=req.notes,
            ),
            confidence=1.0,
        )
        logger.info(
            "[bio_editor] direct-entry narrator=%s field=%s row=%s",
            req.narrator_id, req.field_key, new_id,
        )
        return {
            "fact_id": new_id,
            "status": "approved",
            "fetched_at": _now_iso(),
        }
    except Exception as exc:
        logger.exception("[bio_editor] direct-entry failed")
        raise HTTPException(
            status_code=500, detail=f"create failed: {exc}",
        )


# ─────────────────────────────────────────────────────────────────────
# POST approve existing row
# ─────────────────────────────────────────────────────────────────────


@router.post("/approve")
def post_approve(req: _ApproveRequest) -> Dict[str, Any]:
    """Promote an existing bio_facts row to status='approved'. Used
    when the operator confirms a Tier 1 extracted_needs_verify row or
    a Tier 2 document_sourced row.

    The original source attribution is preserved; only status changes.
    """
    _require_enabled()
    row = db.bio_fact_get(req.fact_id)
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"fact_id not found: {req.fact_id}",
        )
    try:
        ok = db.bio_fact_set_status(req.fact_id, "approved")
        if not ok:
            raise HTTPException(
                status_code=500,
                detail="status update returned no rows",
            )
        logger.info(
            "[bio_editor] approve fact=%s prev_status=%s",
            req.fact_id, row.get("status"),
        )
        return {
            "fact_id": req.fact_id,
            "status": "approved",
            "previous_status": row.get("status"),
            "fetched_at": _now_iso(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[bio_editor] approve failed")
        raise HTTPException(
            status_code=500, detail=f"approve failed: {exc}",
        )


# ─────────────────────────────────────────────────────────────────────
# POST resolve conflict
# ─────────────────────────────────────────────────────────────────────


@router.post("/resolve-conflict")
def post_resolve_conflict(
    req: _ResolveConflictRequest,
) -> Dict[str, Any]:
    """Promote one row to approved; mark listed peer rows as
    superseded. Conflict_with linking is preserved so the operator UI
    can still show the audit trail.
    """
    _require_enabled()
    promote_row = db.bio_fact_get(req.promote_fact_id)
    if not promote_row:
        raise HTTPException(
            status_code=404,
            detail=f"promote fact_id not found: {req.promote_fact_id}",
        )
    if str(promote_row.get("narrator_id") or "") != req.narrator_id:
        raise HTTPException(
            status_code=400,
            detail="promote fact does not belong to narrator",
        )
    if str(promote_row.get("field_key") or "") != req.field_key:
        raise HTTPException(
            status_code=400,
            detail="promote fact does not match field_key",
        )
    try:
        # Promote
        db.bio_fact_set_status(req.promote_fact_id, "approved")
        # Supersede peers
        superseded: List[str] = []
        for sup_id in req.supersede_fact_ids:
            if sup_id == req.promote_fact_id:
                continue
            sup_row = db.bio_fact_get(sup_id)
            if not sup_row:
                continue
            if str(sup_row.get("narrator_id") or "") != req.narrator_id:
                continue
            if str(sup_row.get("field_key") or "") != req.field_key:
                continue
            db.bio_fact_set_status(
                sup_id, "superseded",
                conflict_with=req.promote_fact_id,
            )
            superseded.append(sup_id)
        logger.info(
            "[bio_editor] resolve-conflict narrator=%s field=%s "
            "promoted=%s superseded=%s",
            req.narrator_id, req.field_key,
            req.promote_fact_id, ",".join(superseded),
        )
        return {
            "promoted": req.promote_fact_id,
            "superseded": superseded,
            "fetched_at": _now_iso(),
        }
    except Exception as exc:
        logger.exception("[bio_editor] resolve-conflict failed")
        raise HTTPException(
            status_code=500, detail=f"resolve failed: {exc}",
        )


# ─────────────────────────────────────────────────────────────────────
# POST mark unanswerable
# ─────────────────────────────────────────────────────────────────────


@router.post("/mark-unanswerable")
def post_mark_unanswerable(
    req: _MarkUnanswerableRequest,
) -> Dict[str, Any]:
    """Operator marks a field as known-unanswerable. Writes a row
    with value=null at status='approved' with source.unanswerable=true
    so the gap map stops surfacing the field as a suggested ask but
    operator review can distinguish "no data" from "known no data."
    """
    _require_enabled()
    _field_def_or_404(req.field_key)
    try:
        new_id = db.bio_fact_create(
            narrator_id=req.narrator_id,
            field_key=req.field_key,
            value_json="null",
            status="approved",
            source_json=_operator_source(
                operator_id=req.operator_id,
                notes="known-unanswerable",
                unanswerable=True,
            ),
            confidence=1.0,
        )
        logger.info(
            "[bio_editor] mark-unanswerable narrator=%s field=%s row=%s",
            req.narrator_id, req.field_key, new_id,
        )
        return {
            "fact_id": new_id,
            "status": "approved",
            "unanswerable": True,
            "fetched_at": _now_iso(),
        }
    except Exception as exc:
        logger.exception("[bio_editor] mark-unanswerable failed")
        raise HTTPException(
            status_code=500, detail=f"mark failed: {exc}",
        )


__all__ = ["router"]
