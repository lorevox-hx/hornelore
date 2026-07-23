from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..db import get_questionnaire, upsert_questionnaire

router = APIRouter(prefix="/api/bio-builder", tags=["questionnaire"])

logger = logging.getLogger(__name__)


class QuestionnaireGetResponse(BaseModel):
    ok: bool = True
    person_id: str
    questionnaire: Dict[str, Any] = Field(default_factory=dict)
    # WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01 Phase 2: per-field
    # {status, source} metadata returned by the new view service.
    # Optional so legacy-blob responses (no _meta) still validate.
    meta: Optional[Dict[str, Any]] = Field(default=None, alias="_meta")
    source: str = "unknown"
    version: int = 1
    updated_at: str

    class Config:
        populate_by_name = True


class QuestionnairePutRequest(BaseModel):
    person_id: str
    questionnaire: Dict[str, Any] = Field(default_factory=dict)
    source: str = "ui_save"
    version: int = 1
    # Optional operator identifier for source provenance on the new
    # fan-out writes; falls through to "" when the FE doesn't set it.
    operator_id: str = ""


class QuestionnairePutResponse(BaseModel):
    ok: bool = True
    person_id: str
    questionnaire: Dict[str, Any] = Field(default_factory=dict)
    source: str = "ui_save"
    version: int = 1
    updated_at: str
    # Phase 3 write-fan-out summary. Always present; zero/empty when
    # the bio_facts write fan-out flag is OFF.
    bio_facts_written: int = 0
    bio_facts_errors: List[Dict[str, str]] = Field(default_factory=list)
    profile_error: Optional[str] = None
    legacy_blob_written: bool = True


def _fanout_writes_enabled() -> bool:
    return os.getenv(
        "HORNELORE_QUESTIONNAIRE_BIO_FACTS_WRITE", "0",
    ).strip() == "1"


def _legacy_blob_write_enabled() -> bool:
    # Default ON for rollout safety — only flips OFF after the
    # Phase 7.5 backfill-readiness report says the legacy table can
    # retire.
    return os.getenv(
        "HORNELORE_QUESTIONNAIRE_LEGACY_BLOB_WRITE", "1",
    ).strip() == "1"


@router.get("/questionnaire", response_model=QuestionnaireGetResponse)
def get_questionnaire_route(
    person_id: str = Query(..., description="Lorevox narrator/person id"),
) -> QuestionnaireGetResponse:
    row = get_questionnaire(person_id)
    if not row:
        return QuestionnaireGetResponse(
            person_id=person_id,
            questionnaire={},
            meta=None,
            source="empty",
            version=1,
            updated_at=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        )

    return QuestionnaireGetResponse(
        person_id=person_id,
        questionnaire=row.get("questionnaire", {}),
        meta=row.get("_meta"),
        source=row.get("source", "unknown"),
        version=int(row.get("version", 1)),
        updated_at=row.get("updated_at") or datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
    )


@router.put("/questionnaire", response_model=QuestionnairePutResponse)
def put_questionnaire_route(payload: QuestionnairePutRequest) -> QuestionnairePutResponse:
    if not payload.person_id.strip():
        raise HTTPException(status_code=400, detail="person_id is required")

    # Code-review issue #3 guard (2026-06-16): refuse the no-write
    # configuration. If both flags are off the questionnaire would be
    # silently discarded — the operator UI shows "saved" and nothing
    # persists anywhere. Surface a 409 so misconfigured stacks fail
    # loudly instead of dropping data on the floor.
    if not _fanout_writes_enabled() and not _legacy_blob_write_enabled():
        raise HTTPException(
            status_code=409,
            detail=(
                "Questionnaire PUT misconfigured: both "
                "HORNELORE_QUESTIONNAIRE_BIO_FACTS_WRITE and "
                "HORNELORE_QUESTIONNAIRE_LEGACY_BLOB_WRITE are 0. "
                "Set at least one to 1 in .env and restart the stack."
            ),
        )

    # WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01 Phase 3 — write fan-out.
    # When enabled, project the questionnaire blob into bio_facts +
    # profile_json BEFORE the legacy blob write. The two flags compose:
    #   BIO_FACTS_WRITE=0 + LEGACY_BLOB_WRITE=1 → status quo (legacy only)
    #   BIO_FACTS_WRITE=1 + LEGACY_BLOB_WRITE=1 → dual-write (rollout)
    #   BIO_FACTS_WRITE=1 + LEGACY_BLOB_WRITE=0 → canonical-only
    #     (post-Phase-7.5 retirement state)
    fanout_summary: Dict[str, Any] = {
        "bio_facts_written": 0,
        "bio_facts_errors":  [],
        "profile_error":     None,
    }
    if _fanout_writes_enabled():
        try:
            from ..services.bio_questionnaire_writer import (
                apply_questionnaire_writes as _apply,
            )
            res = _apply(
                payload.person_id,
                payload.questionnaire or {},
                operator_id=payload.operator_id or "",
            )
            fanout_summary["bio_facts_written"] = int(
                res.get("bio_facts_written") or 0,
            )
            fanout_summary["profile_error"] = res.get("profile_error")
            # External-review fix (2026-06-16): copy per-field error rows
            # from the writer result. Previously these were collected by
            # the writer but never threaded into the PUT response, so
            # partial bio_fact_create failures stayed hidden from the
            # operator UI (the response carried bio_facts_errors=[]
            # unless apply_questionnaire_writes itself raised).
            fanout_summary["bio_facts_errors"] = list(
                res.get("bio_facts_errors") or []
            )
        except Exception as exc:
            # Catch-all so the legacy blob write still runs; the
            # operator UI surfaces the failure via the response.
            logger.warning(
                "put_questionnaire_route: bio_facts write fan-out "
                "failed for %s: %s", payload.person_id, exc,
            )
            fanout_summary["bio_facts_errors"].append({
                "stage": "apply_questionnaire_writes",
                "error": str(exc),
            })

    # Legacy blob write — gated separately so it can retire cleanly
    # post-Phase-7.5. Default ON during rollout for rollback safety.
    legacy_blob_written = False
    saved: Dict[str, Any]
    if _legacy_blob_write_enabled():
        saved = upsert_questionnaire(
            person_id=payload.person_id,
            questionnaire=payload.questionnaire,
            source=payload.source,
            version=payload.version,
        )
        legacy_blob_written = True
    else:
        # Canonical-only mode: skip the legacy blob write entirely.
        # The response still echoes the payload + a now-ISO timestamp
        # so the FE's optimistic UI keeps working.
        saved = {
            "person_id":     payload.person_id,
            "questionnaire": payload.questionnaire or {},
            "source":        payload.source,
            "version":       payload.version,
            "updated_at":    datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        }

    return QuestionnairePutResponse(
        person_id=saved["person_id"],
        questionnaire=saved["questionnaire"],
        source=saved["source"],
        version=int(saved["version"]),
        updated_at=saved["updated_at"],
        bio_facts_written=int(fanout_summary["bio_facts_written"]),
        bio_facts_errors=fanout_summary["bio_facts_errors"],
        profile_error=fanout_summary["profile_error"],
        legacy_blob_written=legacy_blob_written,
    )
