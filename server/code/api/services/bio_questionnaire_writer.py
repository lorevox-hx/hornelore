"""WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01 Phase 3 — write fan-out.

═══════════════════════════════════════════════════════════════════════
  WHAT THIS IS
═══════════════════════════════════════════════════════════════════════

The inverse of bio_questionnaire_view: takes a questionnaire blob from
PUT /api/bio-builder/questionnaire and fans it out to canonical truth:

  - Scalar fields → bio_facts at status='operator_entered', tier=4,
    via='questionnaire_put'
  - Structured arrays (parents / siblings / spouses / children) +
    blocks (education / military / faith / today) → profile_json via
    update_profile_json(merge=True)

Pairs with bio_questionnaire_view to close the read+write loop. After
Phase 3, the legacy bio_builder_questionnaires blob becomes optional
storage — flagged via HORNELORE_QUESTIONNAIRE_LEGACY_BLOB_WRITE for
rollback safety during the dual-write rollout.

LAW 3 INFRASTRUCTURE BOUNDARY:
This module imports stdlib + ..db + .bio_schema only. It does NOT
import from extract.py, chat_ws.py, prompt_composer, family_truth,
safety, or any router. The writer is a pure projection from the FE
questionnaire blob → canonical truth.

═══════════════════════════════════════════════════════════════════════
  PUBLIC API
═══════════════════════════════════════════════════════════════════════

  apply_questionnaire_writes(narrator_id, questionnaire, *, operator_id="")
      → Dict[str, Any]

      Returns:
        {
          "bio_facts_written": int,
          "bio_facts_errors":  List[Dict[str, str]],
          "profile_patch":     Dict[str, Any],
          "profile_error":     Optional[str],
        }

      Failures inside individual writes are caught + counted but never
      raised — the caller's PUT response surfaces partial-save warnings
      via the errors arrays. Mirrors the failure-tolerance contract in
      the intake orchestrator at routers/people.py.

  The field_key → questionnaire-slot mapping is symmetric with
  bio_questionnaire_view._personal_section / _education_section /
  _faith_section / _military_section. When the read view evolves, the
  writer must follow it in lockstep — Phase 5 test pack pins both
  surfaces to the same shape with parity tests.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Mapping, Optional

from .. import db
from . import bio_schema


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Scalar bio_facts write helper — LAW-3-safe (no routers import).
# ─────────────────────────────────────────────────────────────────────


def _write_bio_fact(
    narrator_id: str,
    field_key: str,
    value: Any,
    operator_id: str,
    errors: Optional[List[Dict[str, str]]] = None,
) -> Optional[str]:
    """Write a single bio_facts row at Tier 4 / operator_entered.

    Mirrors routers/people.py:_write_bio_fact_safe but lives inside
    services/ to keep the writer LAW-3 isolated.

    Returns the new row id, or None when:
      * value is empty / None / blank string,
      * field_key is not in the bio_schema seed,
      * the underlying CRUD raises.

    When ``errors`` is provided, appends per-field error rows so the
    PUT response can surface partial-save failures to the operator
    UI (closes the silent-drop gap caught by code review 2026-06-16).
    Schema-mismatch + empty-value skips are NOT errors — they're
    expected drops — so they do not append to ``errors``.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        # Booleans serialize to "True"/"False" — keep them but skip the
        # blank check below.
        str_value: Any = value
    elif isinstance(value, (int, float)):
        str_value = value
    else:
        str_value = str(value).strip()
        if str_value == "":
            return None
    try:
        if bio_schema.get_field_by_key(field_key) is None:
            return None
        source_payload = {
            "tier": 4,
            "kind": "operator",
            "operator_id": operator_id or "",
            "via": "questionnaire_put",
        }
        return db.bio_fact_create(
            narrator_id=narrator_id,
            field_key=field_key,
            value_json=json.dumps(str_value),
            status="operator_entered",
            source_json=json.dumps(source_payload),
            confidence=1.0,
        )
    except Exception as exc:
        logger.warning(
            "bio_questionnaire_writer: bio_fact_create failed for %s/%s: %s",
            narrator_id, field_key, exc,
        )
        if errors is not None:
            errors.append({
                "field_key": field_key,
                "error": str(exc),
            })
        return None


# ─────────────────────────────────────────────────────────────────────
# Section projections (questionnaire blob → profile_patch + scalar writes)
# ─────────────────────────────────────────────────────────────────────


# Personal section: scalar fields → bio_facts; also mirror into
# profile_json.personal so chat_ws._build_profile_seed sees them.
_PERSONAL_SCALAR_MAP = (
    ("fullName",        "full_legal_name"),
    ("preferredName",   "preferred_name"),
    ("dateOfBirth",     "birth_date"),
    ("placeOfBirth",    "birth_place"),
    ("birthOrder",      "birth_order"),
)


def _apply_personal(
    section: Mapping[str, Any],
    *,
    narrator_id: str,
    operator_id: str,
    written: List[str],
    errors: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Project the personal block into profile_patch.personal +
    scalar bio_facts writes. Returns the personal dict to merge into
    profile_json.personal."""
    out: Dict[str, Any] = {}
    if not isinstance(section, Mapping):
        return out
    if section.get("fullName"):           out["fullName"] = section.get("fullName")
    if section.get("preferredName"):      out["preferredName"] = section.get("preferredName")
    if section.get("dateOfBirth"):        out["dateOfBirth"] = section.get("dateOfBirth")
    if section.get("placeOfBirth"):       out["placeOfBirth"] = section.get("placeOfBirth")
    if section.get("currentResidence"):   out["currentResidence"] = section.get("currentResidence")
    if section.get("pronouns"):           out["pronouns"] = section.get("pronouns")
    if section.get("timeOfBirth"):        out["timeOfBirth"] = section.get("timeOfBirth")
    if section.get("zodiacSign"):         out["zodiacSign"] = section.get("zodiacSign")
    if section.get("birthOrder"):         out["birthOrder"] = section.get("birthOrder")

    for slot, field_key in _PERSONAL_SCALAR_MAP:
        v = section.get(slot)
        if v:
            rid = _write_bio_fact(narrator_id, field_key, v, operator_id, errors=errors)
            if rid:
                written.append(field_key)
    return out


def _apply_parents(
    section: Any,
    *,
    narrator_id: str,
    operator_id: str,
    written: List[str],
    errors: Optional[List[Dict[str, str]]] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Project the parents array. Father/mother/maiden-name scalars
    additionally land in bio_facts when the relation can be inferred."""
    if not isinstance(section, list):
        return None
    out: List[Dict[str, Any]] = []
    saw_father = False
    saw_mother = False
    for p in section:
        if not isinstance(p, Mapping):
            continue
        first = (p.get("firstName") or "").strip()
        middle = (p.get("middleName") or "").strip()
        last = (p.get("lastName") or "").strip()
        relation = (p.get("relation") or "").strip()
        if not (first or last or relation):
            continue
        full_name = " ".join(x for x in (first, middle, last) if x)
        out.append({
            "relation":          relation or "",
            "firstName":         first,
            "middleName":        middle,
            "lastName":          last,
            "maidenName":        p.get("maidenName") or "",
            "birthDate":         p.get("birthDate") or "",
            "birthPlace":        p.get("birthPlace") or "",
            "occupation":        p.get("occupation") or "",
            "notableLifeEvents": p.get("notableLifeEvents") or "",
            "notes":             p.get("notes") or "",
        })
        rel_low = relation.lower()
        if "father" in rel_low or "dad" in rel_low:
            if not saw_father and full_name:
                rid = _write_bio_fact(narrator_id, "father_name", full_name, operator_id, errors=errors)
                if rid:
                    written.append("father_name")
                    saw_father = True
        elif "mother" in rel_low or "mom" in rel_low:
            if not saw_mother and full_name:
                rid = _write_bio_fact(narrator_id, "mother_name", full_name, operator_id, errors=errors)
                if rid:
                    written.append("mother_name")
                    saw_mother = True
                maiden = (p.get("maidenName") or "").strip()
                if maiden:
                    rid2 = _write_bio_fact(narrator_id, "mother_maiden_name", maiden, operator_id, errors=errors)
                    if rid2:
                        written.append("mother_maiden_name")
    return out if out else None


def _apply_array_section(
    section: Any,
    *,
    narrator_id: str,
    operator_id: str,
    written: List[str],
    errors: Optional[List[Dict[str, str]]] = None,
    count_field_key: Optional[str],
    primary_scalar: Optional[Dict[str, str]] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Project an array-shaped section (siblings / spouses / children).

    primary_scalar: when set, write the first entry's composed name into
    `bio_facts[field_key]` (e.g. spouse_name). Shape:
      {"name_field_key": "spouse_name", "year_slot": "yearMarried",
       "year_field_key": "marriage_year"}
    """
    if not isinstance(section, list):
        return None
    out: List[Dict[str, Any]] = []
    for entry in section:
        if not isinstance(entry, Mapping):
            continue
        first = (entry.get("firstName") or "").strip()
        last = (entry.get("lastName") or "").strip()
        middle = (entry.get("middleName") or "").strip()
        if not (first or last):
            # tolerate empty rows the FE may emit before the operator
            # finishes typing — skip cleanly.
            continue
        row = {
            "firstName":  first,
            "middleName": middle,
            "lastName":   last,
        }
        for opt in ("relation", "birthOrder", "yearMarried", "status",
                    "dateOfBirth", "birthDate", "birthPlace",
                    "uniqueCharacteristics", "sharedExperiences",
                    "memories", "notes", "occupation", "maidenName",
                    "narrative"):
            if entry.get(opt):
                row[opt] = entry.get(opt)
        out.append(row)
    if not out:
        return None
    if count_field_key:
        rid = _write_bio_fact(narrator_id, count_field_key, len(out), operator_id, errors=errors)
        if rid:
            written.append(count_field_key)
    if primary_scalar:
        first_entry = out[0]
        composed = " ".join(
            x for x in (
                first_entry.get("firstName", ""),
                first_entry.get("middleName", ""),
                first_entry.get("lastName", ""),
            ) if x
        ).strip()
        name_fk = primary_scalar.get("name_field_key")
        if name_fk and composed:
            rid = _write_bio_fact(narrator_id, name_fk, composed, operator_id, errors=errors)
            if rid:
                written.append(name_fk)
        year_slot = primary_scalar.get("year_slot")
        year_fk = primary_scalar.get("year_field_key")
        if year_slot and year_fk:
            year_val = first_entry.get(year_slot)
            if year_val:
                rid = _write_bio_fact(narrator_id, year_fk, year_val, operator_id, errors=errors)
                if rid:
                    written.append(year_fk)
    return out


def _apply_education(
    section: Any,
    *,
    narrator_id: str,
    operator_id: str,
    written: List[str],
    errors: Optional[List[Dict[str, str]]] = None,
    profile_patch: Dict[str, Any],
) -> None:
    """Project education block. highestLevel + careerProgression land
    in profile_json.education; primaryCareer lands in profile_json.
    community.role (mirroring the intake orchestrator's shape)."""
    if not isinstance(section, Mapping):
        return
    edu_block: Dict[str, Any] = {}
    if section.get("highestLevel"):
        edu_block["highestLevel"] = section.get("highestLevel")
        rid = _write_bio_fact(narrator_id, "highest_education_level",
                              section.get("highestLevel"), operator_id,
                              errors=errors)
        if rid:
            written.append("highest_education_level")
    if section.get("careerProgression"):
        edu_block["careerProgression"] = section.get("careerProgression")
    if edu_block:
        profile_patch["education"] = edu_block
    primary_career = section.get("primaryCareer")
    if primary_career:
        profile_patch.setdefault("community", {})["role"] = primary_career
        rid = _write_bio_fact(narrator_id, "primary_career", primary_career, operator_id, errors=errors)
        if rid:
            written.append("primary_career")


def _apply_military(
    section: Any,
    *,
    narrator_id: str,
    operator_id: str,
    written: List[str],
    errors: Optional[List[Dict[str, str]]] = None,
    profile_patch: Dict[str, Any],
) -> None:
    if not isinstance(section, Mapping):
        return

    # External-review fix (2026-06-16): the Operator Intake tab sends
    # `served` as a string ("" / "no" / "yes") from a select element,
    # NOT as a Python bool. The previous `bool(section.get("served"))`
    # collapsed "no" -> True (non-empty string is truthy in Python),
    # and the scalar write then converted it back to "yes". Result:
    # operator picks "no" -> system records military_served="yes".
    #
    # Parse explicitly:
    #   - empty / None       -> not set (served_explicit=False)
    #   - True / "yes"/"true"/"1" / 1 -> True
    #   - False / "no"/"false"/"0" / 0 -> False
    #
    # The intake-form modal (routers/people.py) sends Python bool;
    # the Operator Intake tab sends string. Both are handled.
    served_raw = section.get("served")
    served_explicit = served_raw not in (None, "")
    if isinstance(served_raw, bool):
        served = served_raw
    else:
        served = str(served_raw).strip().lower() in ("yes", "true", "1")

    has_other_fields = any(section.get(k) for k in (
        "branch", "servicePeriod", "rank", "units", "locations",
        "warsConflicts", "decorations", "experienceNotes",
    ))
    if not served_explicit and not has_other_fields:
        return

    block: Dict[str, Any] = {"served": served}
    for slot in ("branch", "servicePeriod", "rank", "units", "locations",
                 "warsConflicts", "decorations", "experienceNotes"):
        v = section.get(slot)
        if v:
            block[slot] = v
    profile_patch["military"] = block

    _mil_scalar_map = (
        ("served",          "military_served"),
        ("branch",          "military_branch"),
        ("servicePeriod",   "military_service_period"),
        ("rank",            "military_rank"),
        ("locations",       "military_locations"),
        ("warsConflicts",   "military_wars_conflicts"),
        ("decorations",     "military_decorations"),
        ("experienceNotes", "military_experience_notes"),
    )
    for slot, field_key in _mil_scalar_map:
        if slot == "served":
            # External-review fix: only write the served scalar when
            # the operator explicitly set it. Preserve "no" by writing
            # the string "no" — previously "no" was treated as truthy
            # and silently flipped to "yes".
            if not served_explicit:
                continue
            v_write = "yes" if served else "no"
            rid = _write_bio_fact(narrator_id, field_key, v_write,
                                  operator_id, errors=errors)
            if rid:
                written.append(field_key)
            continue
        v = section.get(slot)
        if v in (None, "", False):
            continue
        rid = _write_bio_fact(narrator_id, field_key, v, operator_id, errors=errors)
        if rid:
            written.append(field_key)


def _apply_faith(
    section: Any,
    *,
    narrator_id: str,
    operator_id: str,
    written: List[str],
    errors: Optional[List[Dict[str, str]]] = None,
    personal_block: Dict[str, Any],
) -> None:
    """Faith block mirrors into profile_json.personal (matches the
    intake orchestrator) AND writes scalar bio_facts."""
    if not isinstance(section, Mapping):
        return
    _faith_map = (
        ("religionRaised",    "faithRaised",     "religion_raised"),
        ("currentFaith",      "currentFaith",    "current_faith"),
        ("ethnicityHeritage", "culture",         "ethnicity_heritage"),
        ("languagesAtHome",   "languagesAtHome", "languages_spoken_home"),
    )
    for q_slot, p_slot, field_key in _faith_map:
        v = section.get(q_slot)
        if not v:
            continue
        personal_block[p_slot] = v
        rid = _write_bio_fact(narrator_id, field_key, v, operator_id, errors=errors)
        if rid:
            written.append(field_key)


def _apply_today(
    section: Any,
    profile_patch: Dict[str, Any],
) -> None:
    if not isinstance(section, Mapping):
        return
    today_block: Dict[str, Any] = {}
    if section.get("livingSituation"):
        today_block["livingSituation"] = section.get("livingSituation")
    if section.get("healthConsiderations"):
        today_block["healthConsiderations"] = section.get("healthConsiderations")
    if today_block:
        profile_patch["today"] = today_block


# ─────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────


def apply_questionnaire_writes(
    narrator_id: str,
    questionnaire: Mapping[str, Any],
    *,
    operator_id: str = "",
) -> Dict[str, Any]:
    """Fan out a questionnaire blob to bio_facts + profile_json.

    Returns a summary dict the PUT route surfaces to the operator UI.
    Never raises on individual write failures — partial-save semantics
    mirror the intake orchestrator. Individual write failures are
    captured in `bio_facts_errors` so the operator UI can render
    partial-save warnings (see code review 2026-06-16 issue #1).
    """
    out: Dict[str, Any] = {
        "bio_facts_written": 0,
        "bio_facts_errors":  [],
        "profile_patch":     {},
        "profile_error":     None,
    }
    if not narrator_id:
        return out
    q = questionnaire or {}

    written: List[str] = []
    errors: List[Dict[str, str]] = out["bio_facts_errors"]
    profile_patch: Dict[str, Any] = {}

    # Helper closure so the per-section functions don't all need a
    # new `errors=` kwarg signature — the closure carries it via
    # `_wb(field_key, value)` rather than threading it through each
    # call site.
    def _wb(field_key: str, value: Any) -> Optional[str]:
        return _write_bio_fact(
            narrator_id, field_key, value, operator_id, errors=errors,
        )

    # Personal block — mirrored to profile_json.personal AND scalar
    # bio_facts. Faith section threads back into the same personal
    # dict, so build it first, then mutate.
    personal = _apply_personal(
        q.get("personal") or {},
        narrator_id=narrator_id,
        operator_id=operator_id,
        written=written,
        errors=errors,
    )

    # Parents (array + father/mother scalars)
    parents = _apply_parents(
        q.get("parents"),
        narrator_id=narrator_id,
        operator_id=operator_id,
        written=written,
        errors=errors,
    )
    if parents is not None:
        profile_patch["parents"] = parents

    # Siblings (array + sibling_count scalar)
    # External-review fix (2026-06-16): pass errors=errors so per-field
    # write failures inside the count/primary scalar pass surface in
    # the PUT response. Previously omitted; the helper signature
    # accepts the kwarg but the call sites for siblings/spouses/
    # children weren't threading it.
    sibs = _apply_array_section(
        q.get("siblings"),
        narrator_id=narrator_id,
        operator_id=operator_id,
        written=written,
        errors=errors,
        count_field_key="sibling_count",
    )
    if sibs is not None:
        profile_patch["siblings"] = sibs

    # Spouses (array + spouse_name + marriage_year scalars)
    spouses = _apply_array_section(
        q.get("spouses") or q.get("spouse"),
        narrator_id=narrator_id,
        operator_id=operator_id,
        written=written,
        errors=errors,
        count_field_key=None,
        primary_scalar={
            "name_field_key": "spouse_name",
            "year_slot": "yearMarried",
            "year_field_key": "marriage_year",
        },
    )
    if spouses is not None:
        profile_patch["spouses"] = spouses
        # legacy single `spouse` slot for read-bridge compatibility
        profile_patch["spouse"] = spouses[0]

    # Children (array + children_count scalar)
    kids = _apply_array_section(
        q.get("children"),
        narrator_id=narrator_id,
        operator_id=operator_id,
        written=written,
        errors=errors,
        count_field_key="children_count",
    )
    if kids is not None:
        profile_patch["children"] = kids

    # Education + work
    _apply_education(
        q.get("education"),
        narrator_id=narrator_id,
        operator_id=operator_id,
        written=written,
        errors=errors,
        profile_patch=profile_patch,
    )

    # Military
    _apply_military(
        q.get("military"),
        narrator_id=narrator_id,
        operator_id=operator_id,
        written=written,
        errors=errors,
        profile_patch=profile_patch,
    )

    # Faith mirrors into personal dict
    _apply_faith(
        q.get("faith"),
        narrator_id=narrator_id,
        operator_id=operator_id,
        written=written,
        errors=errors,
        personal_block=personal,
    )

    # Today
    _apply_today(q.get("today"), profile_patch)

    # Personal block goes into profile_patch LAST so faith merges land.
    if personal:
        profile_patch["personal"] = personal

    # Merge into profile_json — best-effort, captured if it errors.
    if profile_patch:
        try:
            db.update_profile_json(
                narrator_id, profile_patch, merge=True,
                reason="WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01:put",
            )
        except Exception as exc:
            out["profile_error"] = str(exc)
            logger.warning(
                "bio_questionnaire_writer: update_profile_json failed "
                "for %s: %s", narrator_id, exc,
            )

    out["bio_facts_written"] = len(written)
    out["profile_patch"] = profile_patch
    return out


__all__ = [
    "apply_questionnaire_writes",
]
