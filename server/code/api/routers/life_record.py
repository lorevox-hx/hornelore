"""The Life Record's routes (Batch B-2). The only HTTP door to the one writer.

GET   /api/life-record/{narrator_id}   the assembled record; WRITES NOTHING
PATCH /api/life-record/{narrator_id}   {baseRevision, actor, changes[]} -> the writer

409 = a path moved (per-path conflict; nothing written).
422 = a change or the resulting record was refused (nothing written).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..db import get_person
from ..services.life_record import writer as _writer

router = APIRouter(prefix="/api/life-record", tags=["life-record"])


class LifeRecordPatch(BaseModel):
    baseRevision: Optional[int] = None
    actor: str
    changes: List[Dict[str, Any]] = Field(default_factory=list)


@router.get("/{narrator_id}", summary="The assembled Life Record (read-only)")
def api_life_record_get(narrator_id: str):
    if not get_person(narrator_id):
        raise HTTPException(status_code=404, detail="Narrator not found")
    return _writer.read_record(narrator_id)


@router.patch("/{narrator_id}", summary="Apply a change set through the one writer")
def api_life_record_patch(narrator_id: str, body: LifeRecordPatch):
    if not get_person(narrator_id):
        raise HTTPException(status_code=404, detail="Narrator not found")
    result = _writer.apply_changes(narrator_id, body.baseRevision, body.changes, body.actor)
    if result.get("ok"):
        return result
    raise HTTPException(status_code=409 if "conflict" in result else 422, detail=result)
