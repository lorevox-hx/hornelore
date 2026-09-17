from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..db import get_questionnaire
# db.upsert_questionnaire is DELIBERATELY NOT IMPORTED HERE. It is the blind
# whole-document replace this route used to call, it now refuses by default,
# and an unused import is how it would find its way back into a future edit.
from ..services import questionnaire_persistence as _qp

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
    # The write revision the caller should echo back as `base_revision`.
    # 0 when the narrator has no stored questionnaire, or when the response
    # came from the bio_facts projection rather than the stored row.
    revision: int = 0
    updated_at: str

    class Config:
        populate_by_name = True


class QuestionnairePutRequest(BaseModel):
    person_id: str
    questionnaire: Dict[str, Any] = Field(default_factory=dict)
    source: str = "ui_save"
    # SCHEMA version. NOT a revision counter — every client hard-codes this
    # to 1 / DRAFT_SCHEMA_VERSION, so a stale client sends exactly what a
    # fresh one sends and it can never carry concurrency. Optimistic
    # concurrency is `base_revision` / `base_fields` below. (Confusingly,
    # on interview_projections `version` IS the revision counter. Same name,
    # opposite meanings, adjacent tables — see 0058.)
    version: int = 1
    # Optional operator identifier for source provenance on the new
    # fan-out writes; falls through to "" when the FE doesn't set it.
    operator_id: str = ""

    # ── optimistic concurrency, both optional during rollout ──────────
    # `base_revision` is what the caller hydrated. `base_fields` is the
    # stronger claim: the value it hydrated FOR EACH PATH it is writing. A
    # global revision proves only that SOMETHING moved, not what, so a
    # caller that can show its working gets per-path checking and a
    # disjoint edit rebases on the server in one round trip. A caller that
    # sends neither is trusted, exactly as today — the rollout does not
    # break clients that have not been converted yet.
    base_revision: Optional[int] = None
    base_fields: Optional[Dict[str, Any]] = None


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
        revision=int(row.get("revision") or 0),
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
    #
    # WO-QUESTIONNAIRE-PERSISTENCE-INTEGRITY-01 (2026-09-17): this used to
    # call db.upsert_questionnaire, a blind whole-document replace. It now
    # goes through questionnaire_persistence.merge_whole_document, which
    # flattens the incoming document to its populated leaves and applies
    # them as mutations with NO removals.
    #
    # WHAT THAT CHANGES, in one sentence: a key the caller omitted is
    # untouched instead of deleted. Every existing client keeps working and
    # none of them can silently destroy a field it does not render — which
    # is how BUG-BIO-QUESTIONNAIRE-LOSSY-ROUNDTRIP-01 deleted ten populated
    # values, including several hundred words of hand-typed family history,
    # from a real narrator on 2026-09-15.
    #
    # WHAT IT DELIBERATELY BREAKS: removal through this route. A client that
    # genuinely needs to delete must send `removals`, or call the explicit
    # replace/reset operations. Until each client is converted, a deletion
    # will appear not to take effect. That is a visible, recoverable failure
    # and it is the correct trade against an invisible destructive one.
    legacy_blob_written = False
    saved: Dict[str, Any]
    if _legacy_blob_write_enabled():
        try:
            merged = _qp.merge_whole_document(
                payload.person_id,
                payload.questionnaire or {},
                source=payload.source,
                base_revision=payload.base_revision,
                base_fields=payload.base_fields,
                schema_version=payload.version,
            )
        except _qp.QuestionnaireConflict as conflict:
            # A stale client. Refuse rather than rebase: rebasing is safe
            # when the server touched different paths and silently
            # destructive when it touched the same one, so the conflict is
            # surfaced and the caller must not retry blind.
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "stale_questionnaire",
                    "conflicting_paths": sorted(set(conflict.paths)),
                    "current_revision": conflict.revision,
                    "detail": (
                        "The stored value of at least one path you are writing "
                        "is not the value you hydrated. Re-read the "
                        "questionnaire and reapply your edit; do not retry "
                        "this write unchanged."
                    ),
                },
            )
        saved = {
            "person_id":     payload.person_id,
            "questionnaire": merged["questionnaire"],
            "source":        payload.source,
            "version":       payload.version,
            "updated_at":    merged.get("updated_at")
                             or datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        }
        fanout_summary["revision"] = merged.get("revision")
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
