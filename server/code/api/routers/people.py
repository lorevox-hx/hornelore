from __future__ import annotations

"""People Router — LoreVox v8.0 (Phase 2 — Narrator Delete Cascade)

A "person" is the subject of a biography (or a family member). This is distinct
from an authenticated "user" account.

Endpoints:
- POST   /api/people                           — create a person
- GET    /api/people                           — list active people
- GET    /api/people/{person_id}               — get a specific person
- PATCH  /api/people/{person_id}               — update a person
- GET    /api/people/{person_id}/delete-inventory — dependency counts before delete
- DELETE /api/people/{person_id}               — soft delete (default) or hard delete (?mode=hard)
- POST   /api/people/{person_id}/restore       — restore a soft-deleted person

Profiles are stored separately (see profiles router).
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..db import (
    bio_fact_create,
    consent_attestation_create,
    create_person,
    get_person,
    hard_delete_person,
    list_people,
    person_delete_inventory,
    restore_person,
    soft_delete_person,
    update_person,
    update_profile_json,
)

router = APIRouter(prefix="/api/people", tags=["people"])


# WO-OPERATOR-NEW-NARRATOR-INTAKE-FORM-01 — Phase 1A enums.
_PRONOUN_CHOICES = frozenset({
    "", "she_her", "he_him", "they_them", "other",
})


class PersonCreate(BaseModel):
    display_name: str = Field(..., description="Name to show in UI")
    role: Optional[str] = Field(default=None, description="subject, father, mother, sibling, etc")
    date_of_birth: Optional[str] = None  # YYYY-MM-DD
    place_of_birth: Optional[str] = None
    # WO-13 Phase 3 — narrator_type (live | reference)
    narrator_type: Optional[str] = Field(
        default="live",
        description="'live' = real interviewable narrator; 'reference' = read-only seed narrator (Shatner/Dolly style).",
    )
    # WO-OPERATOR-NEW-NARRATOR-INTAKE-FORM-01 — Phase 1A identity intake.
    # All optional at the API layer so existing callers (templates, legacy
    # tooling, the testing-only skip path) keep working. The intake form's
    # client-side validation enforces the required-floor when the operator
    # uses the structured create flow.
    pronouns: Optional[str] = Field(
        default=None,
        description="One of '' / 'she_her' / 'he_him' / 'they_them' / 'other'.",
    )
    pronouns_other: Optional[str] = Field(
        default=None,
        description="Free-text pronoun when pronouns='other'.",
    )
    current_residence: Optional[str] = Field(
        default=None,
        description="Narrator's current city / state / region.",
    )
    consent_recording_agreement: Optional[bool] = Field(
        default=None,
        description="Narrator agrees to be recorded and have stories preserved.",
    )
    consent_disclosure_reviewed: Optional[bool] = Field(
        default=None,
        description="Narrator has reviewed (or had read to them) the Lori behavior disclosure.",
    )
    consent_checked_by_operator: Optional[str] = Field(
        default=None,
        description="Operator id when consent was checked on the narrator's behalf; '' for narrator-self attestation.",
    )
    testing_only: Optional[bool] = Field(
        default=False,
        description="True for the 'Skip — add narrator for testing only' path; bypasses consent requirements.",
    )


class PersonUpdate(BaseModel):
    display_name: Optional[str] = None
    role: Optional[str] = None
    date_of_birth: Optional[str] = None
    place_of_birth: Optional[str] = None
    # WO-13 Phase 3 — narrator_type mutation (admin-only affordance)
    narrator_type: Optional[str] = Field(
        default=None,
        description="'live' | 'reference'. Changes the write-guard policy for this narrator.",
    )


@router.post("", summary="Create a new person")
def api_create_person(payload: PersonCreate):
    """
    Creates a person row, then writes consent attestation rows in the
    same logical transaction (per WO-OPERATOR-NEW-NARRATOR-INTAKE-FORM-01
    Phase 1B). Returns 422 when:
      - testing_only is false AND either consent box is unchecked
      - pronouns is set to an unknown value
      - pronouns='other' but pronouns_other is empty
    """
    # Pronoun enum validation
    pron = (payload.pronouns or "").strip()
    if pron and pron not in _PRONOUN_CHOICES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"pronouns must be one of {sorted(_PRONOUN_CHOICES)}; "
                f"got {pron!r}"
            ),
        )
    if pron == "other" and not (payload.pronouns_other or "").strip():
        raise HTTPException(
            status_code=422,
            detail="pronouns='other' requires pronouns_other free-text",
        )

    # Consent gate — required unless caller is on the testing-only path
    is_testing = bool(payload.testing_only)
    if not is_testing:
        if not payload.consent_recording_agreement:
            raise HTTPException(
                status_code=422,
                detail=(
                    "consent_recording_agreement must be true unless "
                    "testing_only=true"
                ),
            )
        if not payload.consent_disclosure_reviewed:
            raise HTTPException(
                status_code=422,
                detail=(
                    "consent_disclosure_reviewed must be true unless "
                    "testing_only=true"
                ),
            )

    try:
        person = create_person(
            display_name=payload.display_name,
            role=payload.role,
            date_of_birth=payload.date_of_birth,
            place_of_birth=payload.place_of_birth,
            narrator_type=payload.narrator_type or "live",
            pronouns=pron,
            pronouns_other=payload.pronouns_other or "",
            current_residence=payload.current_residence or "",
            # Previously this flag only bypassed the consent gate above
            # and was echoed back in the response — it was never stored,
            # so a testing-only narrator became durably indistinguishable
            # from a real one the moment creation finished. The Guard Lab
            # gates experimental configurations on exactly this, so it
            # now has to survive the request. The column is owned by
            # init_db()'s PRAGMA-guarded people block, not by a
            # migration — migration 0013's header records why.
            testing_only=is_testing,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Defensive: support either return style (dict or id str) without crashing.
    if isinstance(person, dict):
        person_id = person.get("id")
        if not person_id:
            raise HTTPException(status_code=500, detail="create_person returned dict without 'id'")
    else:
        person_id = str(person)
        person = get_person(person_id)
        if not person:
            raise HTTPException(status_code=500, detail="Person created but could not be fetched")

    # Write consent attestations in a best-effort follow-up. Failures
    # don't roll back the people row (the person record is the source
    # of truth; consent rows are an audit ledger), but they DO produce
    # a non-fatal warning in the response so the operator dashboard
    # can flag the narrator.
    consent_written: list = []
    consent_errors: list = []
    if not is_testing:
        checked_by = (payload.consent_checked_by_operator or "").strip()
        for attestation_type in (
            "recording_agreement", "disclosure_reviewed",
        ):
            try:
                row_id = consent_attestation_create(
                    narrator_id=person_id,
                    attestation_type=attestation_type,
                    checked_by_operator=checked_by,
                )
                consent_written.append({
                    "id": row_id,
                    "type": attestation_type,
                })
            except Exception as exc:
                consent_errors.append({
                    "type": attestation_type,
                    "error": str(exc),
                })

    return {
        "person_id": person_id,
        "person": person,
        "consent_attestations": consent_written,
        "consent_errors": consent_errors,
        "testing_only": is_testing,
    }


@router.get("", summary="List people")
def api_list_people(
    limit: int = 200,
    offset: int = 0,
    include_deleted: bool = Query(False, description="Include soft-deleted narrators"),
):
    return {"people": list_people(limit=limit, offset=offset, include_deleted=include_deleted)}


@router.get("/{person_id}", summary="Get a person")
def api_get_person(person_id: str):
    row = get_person(person_id)
    if not row:
        raise HTTPException(status_code=404, detail="Person not found")
    return {"person": row}


@router.get("/{person_id}/delete-inventory", summary="Get dependency inventory before deletion")
def api_delete_inventory(person_id: str):
    inv = person_delete_inventory(person_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Person not found")
    return inv


@router.delete("/{person_id}", summary="Delete a person (soft by default, hard with ?mode=hard)")
def api_delete_person(
    person_id: str,
    mode: str = Query("soft", description="'soft' (default) or 'hard'"),
    reason: str = Query("", description="Optional reason for deletion"),
):
    if mode == "hard":
        result = hard_delete_person(person_id, requested_by="ui")
        if result is None:
            # THE PERSON ROW IS GONE, BUT THEIR FILES MAY NOT BE
            # (2026-08-20). A partial deletion used to end here: the
            # rows were deleted, the erasure failed, and the repeat
            # request answered 404 while the narrator's transcripts sat
            # on disk with no product route back to them. If a saved
            # erasure plan exists, repeating the confirmed hard delete
            # executes it instead of reporting "not found".
            from ..db import erasure_job_get, retry_person_erasure
            if erasure_job_get(person_id):
                retried = retry_person_erasure(person_id, requested_by="ui")
                if retried is not None:
                    return _delete_response(retried)
            raise HTTPException(status_code=404, detail="Person not found")
        if "error" in result:
            if result["error"] == "rollback":
                raise HTTPException(status_code=500, detail=f"Hard delete failed: {result.get('detail', 'unknown')}")
            if result["error"] == "plan_unavailable":
                # Nothing was deleted. The erasure plan could not be
                # built or saved, so the deletion refused BEFORE
                # touching a row rather than destroying the authority
                # its own retry depends on. 503: try again.
                raise HTTPException(status_code=503,
                                    detail=result.get("detail")
                                    or "erasure plan unavailable")
            raise HTTPException(status_code=400, detail=result["error"])
        return _delete_response(result)
    else:
        result = soft_delete_person(person_id, requested_by="ui", reason=reason)
        if result is None:
            raise HTTPException(status_code=404, detail="Person not found")
        if "error" in result:
            if result["error"] == "already_deleted":
                raise HTTPException(status_code=409, detail="Person is already soft-deleted")
            raise HTTPException(status_code=400, detail=result["error"])
        return result


def _delete_response(result):
    """HTTP status from the deletion OUTCOME, not from a single flag.

    Three outcomes, and only one of them is actionable (Chris,
    2026-08-20):

      * `hard_deleted`                      -> 200, nothing remains;
      * `hard_deleted_historical_residue`   -> 200, active data gone,
        shared backups or exports still contain the narrator and are
        reported rather than rewritten;
      * `hard_deleted_partial`              -> 207, the active erasure
        failed and a retry is available.

    Keying the code on `erasure_complete` made a backup produce a
    permanent 207 on a deletion where nothing had failed and
    `retry_available` was already false -- an error code an operator
    could do nothing about, on every deletion, forever.
    """
    if result.get("status") == "hard_deleted_partial":
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=207, content=result)
    return result


@router.post("/{person_id}/erase-retry",
             summary="Re-run a saved filesystem erasure plan")
def api_retry_person_erasure(person_id: str):
    """Execute the saved erasure plan again.

    A dedicated route as well as the repeat-DELETE path, because the
    two read differently to an operator: DELETE says "remove this
    narrator" about someone who no longer exists, and this says
    "finish removing their files", which is what is actually being
    asked. Idempotent -- targets already gone are counted absent -- so
    it is safe to press twice.
    """
    from ..db import retry_person_erasure
    result = retry_person_erasure(person_id, requested_by="ui")
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="No saved erasure plan for this person")
    return _delete_response(result)


@router.post("/{person_id}/restore", summary="Restore a soft-deleted person")
def api_restore_person(person_id: str):
    result = restore_person(person_id, requested_by="ui")
    if result is None:
        raise HTTPException(status_code=404, detail="Person not found")
    if "error" in result:
        if result["error"] == "not_deleted":
            raise HTTPException(status_code=409, detail="Person is not deleted")
        if result["error"] == "undo_expired":
            raise HTTPException(
                status_code=410,
                detail=f"Undo window expired at {result.get('undo_expires_at', 'unknown')}",
            )
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.patch("/{person_id}", summary="Update a person")
def api_update_person(person_id: str, payload: PersonUpdate):
    if not get_person(person_id):
        raise HTTPException(status_code=404, detail="Person not found")
    try:
        update_person(person_id, **payload.model_dump(exclude_none=True))
    except ValueError as e:
        # Raised for invalid narrator_type
        raise HTTPException(status_code=422, detail=str(e))
    return {"person": get_person(person_id)}


# ═════════════════════════════════════════════════════════════════════
# WO-OPERATOR-NEW-NARRATOR-INTAKE-FORM-01 Phase 2 — full-intake
# orchestrator. POST /api/people/intake fans out a single rich payload
# across people + consent_attestations + profiles.profile_json +
# bio_facts so the operator's pre-session knowledge lands in every
# downstream surface Lori reads.
# ═════════════════════════════════════════════════════════════════════

import json
from typing import List
from pydantic import BaseModel as _BaseModel, field_validator


class IntakeSibling(_BaseModel):
    name: str
    birth_date: Optional[str] = None
    birth_order: Optional[int] = None


class IntakeSpouse(_BaseModel):
    name: str
    year_married: Optional[int] = None
    status: Optional[str] = None  # 'current' | 'deceased' | 'divorced'

    # BUG-INTAKE-SPOUSE-YEAR-MARRIED-EMPTY-STRING-422-01 (Boris Phase 11):
    # the intake-form modal sends year_married as "" when the operator
    # leaves it blank. Without this validator Pydantic raises
    # int_parsing on "" and the entire intake POST 422s — Alex's
    # narrator never gets created. Coerce "" / whitespace / "null" to
    # None so the form can be partial.
    @field_validator("year_married", mode="before")
    @classmethod
    def _coerce_empty_year(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            stripped = v.strip()
            if not stripped or stripped.lower() in ("null", "none"):
                return None
            try:
                return int(stripped)
            except (TypeError, ValueError):
                return None
        return v


class IntakeChild(_BaseModel):
    name: str
    birth_date: Optional[str] = None


class IntakeFamilyOfOrigin(_BaseModel):
    father_name: Optional[str] = None
    father_birth_date: Optional[str] = None
    mother_name: Optional[str] = None
    mother_maiden_name: Optional[str] = None
    mother_birth_date: Optional[str] = None
    siblings: List[IntakeSibling] = []


class IntakeMarriage(_BaseModel):
    marital_status: Optional[str] = None
    number_of_marriages: Optional[int] = None
    spouses: List[IntakeSpouse] = []


class IntakeEducationWork(_BaseModel):
    highest_education_level: Optional[str] = None
    primary_career: Optional[str] = None
    years_working: Optional[str] = None


class IntakeMilitary(_BaseModel):
    served: bool = False
    branch: Optional[str] = None
    service_dates: Optional[str] = None
    rank: Optional[str] = None
    units: Optional[str] = None
    locations: Optional[str] = None
    wars_conflicts: Optional[str] = None
    decorations: Optional[str] = None
    experience_notes: Optional[str] = None


class IntakeFaith(_BaseModel):
    religion_raised: Optional[str] = None
    current_faith: Optional[str] = None
    ethnicity_heritage: Optional[str] = None
    languages_at_home: Optional[str] = None


class IntakeToday(_BaseModel):
    living_situation: Optional[str] = None
    health_considerations: Optional[str] = None


class NarratorIntakePayload(_BaseModel):
    """Full intake form payload — identity required + 7 optional sections."""
    # Identity (required for non-testing-only saves)
    full_legal_name: str
    preferred_name: str
    date_of_birth: str
    place_of_birth: str
    pronouns: str
    pronouns_other: Optional[str] = None
    current_residence: str
    # Consent
    consent_recording_agreement: bool = False
    consent_disclosure_reviewed: bool = False
    consent_checked_by_operator: Optional[str] = None
    testing_only: bool = False
    # Optional sections
    family_of_origin: Optional[IntakeFamilyOfOrigin] = None
    marriage: Optional[IntakeMarriage] = None
    children: List[IntakeChild] = []
    education_work: Optional[IntakeEducationWork] = None
    military: Optional[IntakeMilitary] = None
    faith: Optional[IntakeFaith] = None
    today: Optional[IntakeToday] = None


# ─────────────────────────────────────────────────────────────────────
# Fan-out helpers
# ─────────────────────────────────────────────────────────────────────


def _split_name(full_name: str) -> Dict[str, str]:
    """Best-effort name split. First token → firstName, last token →
    lastName, anything between → middleName. Empty/whitespace returns
    empty dict so callers can skip writes for nameless rows."""
    parts = (full_name or "").strip().split()
    if not parts:
        return {}
    if len(parts) == 1:
        return {"firstName": parts[0]}
    if len(parts) == 2:
        return {"firstName": parts[0], "lastName": parts[1]}
    return {
        "firstName": parts[0],
        "middleName": " ".join(parts[1:-1]),
        "lastName": parts[-1],
    }


def _pronoun_label(pron: str, other: str) -> str:
    """Map intake pronoun enum to a display string Lori can read."""
    if pron == "she_her": return "she/her"
    if pron == "he_him": return "he/him"
    if pron == "they_them": return "they/them"
    if pron == "other" and other.strip(): return other.strip()
    return ""


def _write_bio_fact_safe(
    narrator_id: str,
    field_key: str,
    value: Any,
    *,
    operator_id: str = "",
) -> Optional[str]:
    """Write a single bio_facts row at status='operator_entered' (Tier 4).
    Validates the field_key exists in the bio_schema seed before
    writing so a typo here can't FK-violate at INSERT time. Returns
    the new row id, or None when the field_key isn't seeded or the
    value is empty.

    Failures are caught + logged but never raised — the caller's
    fan-out loop continues with the next field.
    """
    if value is None:
        return None
    str_value = str(value).strip() if not isinstance(value, (int, float, bool)) else value
    if str_value == "" or str_value is False or str_value is None:
        return None
    try:
        from ..services.bio_schema import get_field_by_key
        if get_field_by_key(field_key) is None:
            return None
        from ..db import bio_fact_create as _bf_create
        source_payload = {
            "tier": 4,
            "operator_id": operator_id or "",
            "via": "intake_form",
        }
        return _bf_create(
            narrator_id=narrator_id,
            field_key=field_key,
            value_json=json.dumps(str_value),
            status="operator_entered",
            source_json=json.dumps(source_payload),
            confidence=1.0,
        )
    except Exception:
        # Best-effort — never let one field's failure break the fan-out.
        return None


@router.post("/intake", summary="Create a narrator from a full intake payload")
def api_create_person_intake(payload: NarratorIntakePayload):
    """Server-side fan-out for the structured intake form.

    Writes land in three places per section:
      * Identity → people row columns (existing schema)
      * Consent → consent_attestations rows
      * Family-of-origin scalars (parents) → bio_facts at
        status='operator_entered' AND mirrored into profile_json so
        chat_ws._build_profile_seed picks them up on the first turn
      * Sibling / spouse / children arrays → profile_json only
        (bio_facts is field-keyed, not entity-keyed)
      * Education / military / faith scalars → bio_facts + profile_json
      * Today (living + health) → profile_json only; operator-side
        context, not memoir field

    Failures inside individual writes are caught + counted in the
    response but don't roll back the people row. The operator dashboard
    surfaces partial-save warnings via the response's `errors` array.
    """
    # Identity required-field gate
    for field, name in (
        (payload.full_legal_name, "full_legal_name"),
        (payload.preferred_name, "preferred_name"),
        (payload.date_of_birth, "date_of_birth"),
        (payload.place_of_birth, "place_of_birth"),
        (payload.pronouns, "pronouns"),
        (payload.current_residence, "current_residence"),
    ):
        if not (field or "").strip():
            raise HTTPException(
                status_code=422,
                detail=f"{name} is required",
            )

    # Pronoun enum + other-text gate
    if payload.pronouns not in _PRONOUN_CHOICES:
        raise HTTPException(
            status_code=422,
            detail=f"pronouns must be one of {sorted(_PRONOUN_CHOICES)}",
        )
    if payload.pronouns == "other" and not (payload.pronouns_other or "").strip():
        raise HTTPException(
            status_code=422,
            detail="pronouns='other' requires pronouns_other free-text",
        )

    # Consent gate (skipped for testing_only)
    if not payload.testing_only:
        if not payload.consent_recording_agreement:
            raise HTTPException(
                status_code=422,
                detail="consent_recording_agreement must be true unless testing_only=true",
            )
        if not payload.consent_disclosure_reviewed:
            raise HTTPException(
                status_code=422,
                detail="consent_disclosure_reviewed must be true unless testing_only=true",
            )

    # ── Stage 1: create the people row ───────────────────────────────
    try:
        person = create_person(
            display_name=payload.preferred_name.strip(),
            role="",
            date_of_birth=payload.date_of_birth,
            place_of_birth=payload.place_of_birth,
            narrator_type="live",
            pronouns=payload.pronouns,
            pronouns_other=payload.pronouns_other or "",
            current_residence=payload.current_residence,
            # Same correction as the PersonCreate flow: the structured
            # intake also used this only for the consent bypass and the
            # response body. Persisted by init_db()'s PRAGMA-guarded
            # people block; there is no migration for this column.
            testing_only=bool(payload.testing_only),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    person_id = person["id"] if isinstance(person, dict) else str(person)
    if not person_id:
        raise HTTPException(status_code=500, detail="create_person returned no id")

    operator_id = (payload.consent_checked_by_operator or "").strip()

    # ── Stage 2: consent attestations ────────────────────────────────
    consent_written: list = []
    consent_errors: list = []
    if not payload.testing_only:
        for attestation_type in ("recording_agreement", "disclosure_reviewed"):
            try:
                row_id = consent_attestation_create(
                    narrator_id=person_id,
                    attestation_type=attestation_type,
                    checked_by_operator=operator_id,
                )
                consent_written.append({"id": row_id, "type": attestation_type})
            except Exception as exc:
                consent_errors.append({"type": attestation_type, "error": str(exc)})

    # ── Stage 3: build profile_json patch + scalar bio_facts ─────────
    profile_patch: Dict[str, Any] = {}
    bio_facts_written: int = 0
    bio_facts_errors: list = []

    def _try_write_fact(key: str, value: Any) -> None:
        nonlocal bio_facts_written
        rid = _write_bio_fact_safe(person_id, key, value, operator_id=operator_id)
        if rid:
            bio_facts_written += 1

    # personal block (identity mirror)
    personal: Dict[str, Any] = {
        "fullName": payload.full_legal_name.strip(),
        "preferredName": payload.preferred_name.strip(),
        "dateOfBirth": payload.date_of_birth,
        "placeOfBirth": payload.place_of_birth,
        "currentResidence": payload.current_residence,
        "pronouns": _pronoun_label(payload.pronouns, payload.pronouns_other or ""),
    }
    profile_patch["personal"] = personal

    # Family of origin → parents array + scalar bio_facts
    fam = payload.family_of_origin
    if fam:
        parents: list = []
        if (fam.father_name or "").strip():
            split = _split_name(fam.father_name)
            parents.append({
                "relation": "Father",
                "firstName": split.get("firstName", ""),
                "middleName": split.get("middleName", ""),
                "lastName": split.get("lastName", ""),
                "dateOfBirth": fam.father_birth_date or "",
            })
            _try_write_fact("father_name", fam.father_name)
            if fam.father_birth_date:
                # year-only DOBs are common at this layer
                m_year = (fam.father_birth_date or "")[:4]
                try:
                    if m_year and m_year.isdigit():
                        _try_write_fact("father_birth_year", int(m_year))
                except Exception:
                    pass
        if (fam.mother_name or "").strip():
            split = _split_name(fam.mother_name)
            parents.append({
                "relation": "Mother",
                "firstName": split.get("firstName", ""),
                "middleName": split.get("middleName", ""),
                "lastName": split.get("lastName", ""),
                "maidenName": (fam.mother_maiden_name or "").strip(),
                "dateOfBirth": fam.mother_birth_date or "",
            })
            _try_write_fact("mother_name", fam.mother_name)
            if (fam.mother_maiden_name or "").strip():
                _try_write_fact("mother_maiden_name", fam.mother_maiden_name)
            if fam.mother_birth_date:
                m_year = (fam.mother_birth_date or "")[:4]
                try:
                    if m_year and m_year.isdigit():
                        _try_write_fact("mother_birth_year", int(m_year))
                except Exception:
                    pass
        if parents:
            profile_patch["parents"] = parents

        # Siblings array → profile_json only
        if fam.siblings:
            sibs: list = []
            for sib in fam.siblings:
                split = _split_name(sib.name)
                sibs.append({
                    "firstName": split.get("firstName", ""),
                    "middleName": split.get("middleName", ""),
                    "lastName": split.get("lastName", ""),
                    "dateOfBirth": sib.birth_date or "",
                    "birthOrder": sib.birth_order or 0,
                })
            profile_patch["siblings"] = sibs
            _try_write_fact("sibling_count", len(sibs))

    # Marriage → spouse(s) + scalar bio_facts
    mar = payload.marriage
    if mar:
        if mar.spouses:
            spouses: list = []
            for sp in mar.spouses:
                split = _split_name(sp.name)
                spouses.append({
                    "firstName": split.get("firstName", ""),
                    "middleName": split.get("middleName", ""),
                    "lastName": split.get("lastName", ""),
                    "yearMarried": sp.year_married or "",
                    "status": sp.status or "",
                })
            profile_patch["spouses"] = spouses
            # Also project the first spouse into the legacy single
            # `spouse` slot for read-bridge compatibility.
            primary = spouses[0]
            profile_patch["spouse"] = primary
            _try_write_fact("spouse_name", mar.spouses[0].name)
            if mar.spouses[0].year_married:
                _try_write_fact("marriage_year", mar.spouses[0].year_married)
        if (mar.marital_status or "").strip():
            profile_patch.setdefault("marriage", {})["status"] = mar.marital_status
            # WO-LORI-PROFILE-SEED-REACHABILITY-01 Phase 1 (2026-08-26) —
            # the answer now also reaches bio_facts, which is where
            # operator entry, extraction and the Profile Seed resolver
            # all look. Until this line, "never married" existed only in
            # `profile_json.marriage.status`, which nothing outside the
            # intake form read, so the partner topic could return
            # forever to a narrator who had already answered it plainly.
            _try_write_fact("marital_status", mar.marital_status)

    # Children → profile_json only
    if payload.children:
        kids: list = []
        for ch in payload.children:
            split = _split_name(ch.name)
            kids.append({
                "firstName": split.get("firstName", ""),
                "middleName": split.get("middleName", ""),
                "lastName": split.get("lastName", ""),
                "dateOfBirth": ch.birth_date or "",
            })
        profile_patch["children"] = kids
        _try_write_fact("children_count", len(kids))

    # Education + work
    ew = payload.education_work
    if ew:
        edu_block: Dict[str, Any] = {}
        if (ew.highest_education_level or "").strip():
            edu_block["highestLevel"] = ew.highest_education_level
            _try_write_fact("highest_education_level", ew.highest_education_level)
        if (ew.years_working or "").strip():
            edu_block["careerProgression"] = ew.years_working
            # WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01 Phase 4 bug
            # fix (2026-06-16): the line below previously wrote
            # ew.years_working to bio_facts as `primary_career`, which
            # clobbered the actual career value with a duration string
            # ("30 years" overwriting "Mechanical engineer") whenever
            # both intake sub-fields were populated. years_working
            # belongs ONLY in profile_json.education.careerProgression
            # — there is no bio_schema field_key for it (verified
            # against the seed). The legitimate primary_career write
            # happens just below from ew.primary_career.
        if edu_block:
            profile_patch["education"] = edu_block
        if (ew.primary_career or "").strip():
            profile_patch.setdefault("community", {})["role"] = ew.primary_career
            _try_write_fact("primary_career", ew.primary_career)

    # Military
    #
    # WO-LORI-PROFILE-SEED-REACHABILITY-01 Phase 1 (2026-08-26) — AN
    # EXPLICIT "NO" IS AN ANSWER AND MUST BE WRITTEN DOWN.
    #
    # This block used to be `if mil and mil.served:` alone, so an
    # operator who opened the military section and left "served"
    # unchecked produced exactly the same stored state as an operator
    # who never opened it: nothing. "Did not serve" and "never asked"
    # were indistinguishable, and Lori would go on asking a
    # ninety-year-old about their service record because the system had
    # no way to remember being told there wasn't one.
    #
    # The distinction that makes this safe is `mil is not None`: the
    # section was PRESENT in the submission. An absent section still
    # writes nothing, because an untouched form is not an answer and
    # pretending otherwise would be the mirror-image defect.
    mil = payload.military
    if mil is not None and not mil.served:
        profile_patch["military"] = {"served": False}
        _try_write_fact("military_served", "no")
    if mil and mil.served:
        military_block: Dict[str, Any] = {
            "served": True,
        }
        if mil.branch: military_block["branch"] = mil.branch
        if mil.service_dates: military_block["servicePeriod"] = mil.service_dates
        if mil.rank: military_block["rank"] = mil.rank
        if mil.units: military_block["units"] = mil.units
        if mil.locations: military_block["locations"] = mil.locations
        if mil.wars_conflicts: military_block["warsConflicts"] = mil.wars_conflicts
        if mil.decorations: military_block["decorations"] = mil.decorations
        if mil.experience_notes: military_block["experienceNotes"] = mil.experience_notes
        profile_patch["military"] = military_block

        _try_write_fact("military_served", "yes")
        if mil.branch: _try_write_fact("military_branch", mil.branch)
        if mil.service_dates: _try_write_fact("military_service_period", mil.service_dates)
        if mil.rank: _try_write_fact("military_rank", mil.rank)
        if mil.locations: _try_write_fact("military_locations", mil.locations)
        if mil.wars_conflicts: _try_write_fact("military_wars_conflicts", mil.wars_conflicts)
        if mil.decorations: _try_write_fact("military_decorations", mil.decorations)
        if mil.experience_notes: _try_write_fact("military_experience_notes", mil.experience_notes)

    # Faith and heritage
    faith = payload.faith
    if faith:
        if (faith.religion_raised or "").strip():
            personal["faithRaised"] = faith.religion_raised
            _try_write_fact("religion_raised", faith.religion_raised)
        if (faith.current_faith or "").strip():
            personal["currentFaith"] = faith.current_faith
            _try_write_fact("current_faith", faith.current_faith)
        if (faith.ethnicity_heritage or "").strip():
            personal["culture"] = faith.ethnicity_heritage
            _try_write_fact("ethnicity_heritage", faith.ethnicity_heritage)
        if (faith.languages_at_home or "").strip():
            personal["languagesAtHome"] = faith.languages_at_home
            _try_write_fact("languages_spoken_home", faith.languages_at_home)
        # personal already in profile_patch — the in-place mutations
        # above propagate.

    # Today
    today_block = payload.today
    if today_block:
        today_payload: Dict[str, Any] = {}
        if (today_block.living_situation or "").strip():
            today_payload["livingSituation"] = today_block.living_situation
        if (today_block.health_considerations or "").strip():
            today_payload["healthConsiderations"] = today_block.health_considerations
        if today_payload:
            profile_patch["today"] = today_payload

    # ── Stage 4: merge profile_json ─────────────────────────────────
    profile_error: Optional[str] = None
    try:
        update_profile_json(
            person_id, profile_patch, merge=True,
            reason="WO-OPERATOR-NEW-NARRATOR-INTAKE-FORM-01",
        )
    except Exception as exc:
        profile_error = str(exc)

    # ── Response ────────────────────────────────────────────────────
    person_row = get_person(person_id) or {"id": person_id}
    return {
        "person_id": person_id,
        "person": person_row,
        "consent_attestations": consent_written,
        "consent_errors": consent_errors,
        "bio_facts_written": bio_facts_written,
        "bio_facts_errors": bio_facts_errors,
        "profile_json_error": profile_error,
        "testing_only": payload.testing_only,
    }
