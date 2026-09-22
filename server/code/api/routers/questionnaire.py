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
    # The write revision after this PUT. Echo it back as `base_revision`.
    revision: int = 0
    # Paths where this caller sent an empty value over something stored.
    # NOT acted on — an omitted or blank value means "untouched", which is
    # what stops a six-field form deleting five stored ones. Reported so
    # the UI can ask "you cleared X — delete it?" and then send a real
    # `removals`, instead of the operator seeing "Saved" while the old
    # value quietly survives.
    ignored_blank_paths: List[str] = Field(default_factory=list)
    # The paths this PUT actually changed. WO-BIO-VIEW-SAFETY-01
    # (2026-09-21). merge_whole_document has always computed this and
    # written it into the revision row; the router dropped it, so the
    # browser had no way to tell an edited field from one that merely
    # happened to be on the form. The projection layer then marked every
    # populated field in the saved section as a human edit and locked it.
    # Returned so attribution can be as narrow as the write was.
    changed_paths: List[str] = Field(default_factory=list)
    # BUG-QUESTIONNAIRE-NOOP-REPORTED-AS-WRITE-01 (2026-09-20). Whether this
    # PUT changed the stored document. merge_whole_document has computed this
    # since 6b0a877 ("a save that changes nothing is not a write") and the
    # router dropped it, so the browser's no-op detection — `j.write_applied
    # === false` — could never fire against the real server, and an unchanged
    # save rendered green "Saved (revision N)". Found on the WO-01 live test:
    # the operator saved Personal Information untouched, saw green, and the
    # revision counter had not moved. The behavioural harness had passed
    # because its server double returned this field; the real route did not.
    write_applied: bool = True


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
    """The shared legacy PUT. **Writes no provenance, deliberately.**

    ~20 callers across five modules funnel through `_persistQuestionnaire`
    with the literal `source: "ui_save"`, and two of them are Lori's own
    writers — `_syncIdentityToBB` (app.js:6072, 6113, 6208, 6237, 6294)
    and `_syncPrefillIfBlank` (projection-sync.js:407-435). Classifying
    this route as human entry would hand the model the authority of the
    person sitting at the keyboard, which is the precise failure WO-03
    exists to remove. It was proposed in revision 1 of the design and
    caught in review.

    Those callers move to the propose operation in WO-03B. Until then no
    row is written for them and they read as `unknown`, which is the
    honest record rather than a gap.
    """
    if not payload.person_id.strip():
        raise HTTPException(status_code=400, detail="person_id is required")
    return _persist(payload, provenance=None)


def _persist(
    payload: QuestionnairePutRequest,
    *,
    provenance: Optional[Any],
) -> QuestionnairePutResponse:
    """The write body, shared by the PUT and the two entry routes.

    `provenance` is an `AnswerOrigin` or None, and it is the ONLY
    difference between them. It is built by the route from the endpoint
    that was called, never parsed out of the request — see
    answer_provenance for why a client-declared operation would recreate
    the trust problem this work order is closing.
    """

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
                provenance=provenance,
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
        fanout_summary["revision"] = merged.get("revision") or 0
        fanout_summary["ignored_blank_paths"] = list(merged.get("ignored_blank_paths") or [])
        fanout_summary["changed_paths"] = list(merged.get("changed_paths") or [])
        # Carry the writer's own verdict through. Default True only when the
        # writer did not say — never as a way of calling a no-op a write.
        fanout_summary["write_applied"] = bool(merged.get("write_applied", True))
        legacy_blob_written = True
    else:
        # Canonical-only mode: skip the legacy blob write entirely.
        #
        # An entry route CANNOT run here. Provenance is written inside the
        # questionnaire write transaction, so with that write skipped there
        # is nowhere to record it — and a route whose entire purpose is to
        # establish who said something, silently not recording it, is worse
        # than the route not existing. Fail loudly, as the both-flags-off
        # guard above does.
        if provenance is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Answer-entry routes require "
                    "HORNELORE_QUESTIONNAIRE_LEGACY_BLOB_WRITE=1. Provenance "
                    "commits inside the questionnaire write transaction and "
                    "cannot be recorded when that write is skipped."
                ),
            )
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
        revision=int(fanout_summary.get("revision") or 0),
        ignored_blank_paths=list(fanout_summary.get("ignored_blank_paths") or []),
        changed_paths=list(fanout_summary.get("changed_paths") or []),
        write_applied=bool(fanout_summary.get("write_applied", True)),
    )


# ── the entry routes ─────────────────────────────────────────────────
#
# TWO ENDPOINTS RATHER THAN ONE ENDPOINT WITH AN `operation` FIELD.
#
# A client-declared operation would recreate the exact trust problem
# WO-03 is closing: whichever module posts the body decides its own
# authority, and the module we most need not to trust is the one that
# composes text. Separating the endpoints makes the classification a
# fact about WHICH ROUTE WAS CALLED — something the server observes —
# instead of a claim the server has to take on faith.
#
# The asymmetry that makes this sound: a caller claiming LOWER authority
# is safe to believe, because nothing gains by falsely calling itself a
# machine. A caller claiming HIGHER authority is not. So the human-entry
# cases get dedicated routes and everything else keeps the silent PUT.


class AnswerEntryRequest(QuestionnairePutRequest):
    """An operator typed this into the Bio Builder form.

    `sections` is what the form actually saved. Provenance is stamped
    ONLY for changed paths within those sections: the form sends the
    whole document, so a path that moved elsewhere in the same request
    moved for some other reason — a draft mirror, a prefill, an identity
    sync — and attributing it to the operator would credit them with
    something they did not do.
    """

    sections: List[str] = Field(default_factory=list)


class NarratorAnswerRequest(QuestionnairePutRequest):
    """The narrator said this, in chat.

    `source_turn_id` is a CLAIM. It is checked against the turn record
    before anything is written, and the verdict — not the claim — is what
    gets stored.
    """

    sections: List[str] = Field(default_factory=list)
    source_turn_id: str = ""
    # The narrator's own words, before any normalisation. Stored as given
    # so a consumer can see whether the answer in the document is what
    # they said or a tidied rendering of it.
    original_text: str = ""


class AnswerEntryResponse(QuestionnairePutResponse):
    # Only 'verified' may be read as evidence. 'unverified' means a turn
    # was cited and did not check out — the answer was still saved, and
    # the citation is retained precisely so it can be investigated.
    turn_evidence: str = "absent"


@router.post("/questionnaire/answer", response_model=AnswerEntryResponse)
def post_operator_answer_route(payload: AnswerEntryRequest) -> AnswerEntryResponse:
    """A person entered this directly. Exactly one caller: `_saveSection`.

    Enforcement that no Lori-derived writer reaches this route is a test,
    not a promise — the harness's server double records which endpoint
    each write hit and the suite fails if any of them lands here.
    """
    from ..services.answer_provenance import AnswerOrigin, ORIGIN_OPERATOR

    if not payload.person_id.strip():
        raise HTTPException(status_code=400, detail="person_id is required")

    origin = AnswerOrigin(
        ORIGIN_OPERATOR,
        actor_id=payload.operator_id or "",
        # None means "every path this write touches". The form always
        # names its section; an empty list would silently classify
        # nothing, which fails quietly, so it is refused instead.
        sections=payload.sections or None,
    )
    if not payload.sections:
        raise HTTPException(
            status_code=400,
            detail=(
                "sections is required: this route stamps provenance only "
                "for the section the form saved, and an unscoped entry "
                "would attribute unrelated changes in the same document "
                "to the operator."
            ),
        )
    out = _persist(payload, provenance=origin)
    return AnswerEntryResponse(**out.model_dump(), turn_evidence="absent")


@router.post("/questionnaire/narrator-answer", response_model=AnswerEntryResponse)
def post_narrator_answer_route(payload: NarratorAnswerRequest) -> AnswerEntryResponse:
    """The narrator said this. Verified against the turn record first.

    THE ANSWER IS SAVED WHETHER OR NOT VERIFICATION PASSES. A bookkeeping
    failure must not discard what the narrator said — that would be the
    system deleting testimony because it could not file the receipt. What
    a failure changes is the CLAIM, not the answer: `turn_evidence`
    records `unverified`, the cited id is kept so the failure can be
    investigated, and no consumer may read it as support.

    Coverage is thin and this route does not pretend otherwise. 1,468 of
    1,487 existing turns have no resolvable owner, so a citation to one
    of them returns `unverified`. `memory_archive_turns`, which the first
    revision of the design verified against, has never held a single row.
    """
    from .. import db as _db
    from ..services.answer_provenance import (
        AnswerOrigin, ORIGIN_NARRATOR, verify_turn, EVIDENCE_ABSENT,
    )

    if not payload.person_id.strip():
        raise HTTPException(status_code=400, detail="person_id is required")
    if not payload.sections:
        raise HTTPException(
            status_code=400, detail="sections is required",
        )

    # Verified BEFORE the write, on its own connection, so a verification
    # that errors cannot roll back the narrator's answer. The verdict is
    # settled once here and carried; nothing downstream re-decides it,
    # because a second opinion on evidence is how an unverified claim
    # becomes a verified one by accident.
    con = _db._connect()
    try:
        evidence = verify_turn(con, payload.person_id, payload.source_turn_id)
    finally:
        con.close()

    origin = AnswerOrigin(
        ORIGIN_NARRATOR,
        actor_id=payload.person_id,
        # The CLAIMED id, kept in every state where one was given.
        # Nulling it on failure would erase the difference between "no
        # citation" and "a citation that did not check out", and the
        # second is the one worth investigating.
        source_turn_id=(payload.source_turn_id or None),
        turn_evidence=evidence,
        original_text=(payload.original_text or None),
        sections=payload.sections,
    )
    if evidence != EVIDENCE_ABSENT and not payload.source_turn_id.strip():
        # Unreachable by construction; asserted because the alternative is
        # a verified claim with nothing behind it.
        raise HTTPException(status_code=500, detail="evidence without a citation")

    out = _persist(payload, provenance=origin)
    return AnswerEntryResponse(**out.model_dump(), turn_evidence=evidence)
