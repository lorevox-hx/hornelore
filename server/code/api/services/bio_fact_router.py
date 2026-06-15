"""WO-LORI-BIO-BUILDER-UNIVERSAL-01 (2026-06-14) — Phase B Tier 1 router.

═══════════════════════════════════════════════════════════════════════
  WHAT THIS IS
═══════════════════════════════════════════════════════════════════════

The Tier 1 (chapter-driven extraction) routing layer for bio_facts.
The extractor in routers/extract.py already produces fact proposals
with dotted-path fieldPaths (`personal.dateOfBirth`,
`personal.placeOfBirth`, `parents.firstName`, etc.) — that pipeline
continues writing to `family_truth_rows` as it always has.

This service runs in PARALLEL: it inspects each extracted item, maps
its fieldPath onto a `bio_fields.field_key` when possible, and writes
a `bio_facts` row alongside the legacy write. Items whose fieldPath
has no bio_fields mapping skip the bio write — the legacy
`family_truth_rows` pipeline is the catch-all for non-bio-schema
proposals (story details, named individuals, etc.).

LAW 3 INFRASTRUCTURE BOUNDARY:
This module imports from stdlib + `..db` + `.bio_schema` only. It
does NOT import from extract.py, prompt_composer, or chat_ws. The
integration point is one call from extract.py at the per-item
commit loop, behind an env flag default-off so the new write path
can be observed before it goes live.

═══════════════════════════════════════════════════════════════════════
  CONFLICT MODEL
═══════════════════════════════════════════════════════════════════════

Per WO §Tier 1:
  - No prior row for (narrator, field_key) → write needs_verify
  - Prior `approved` or `document_sourced` row exists → log candidate,
    do NOT write a new row (document/operator authority wins)
  - Prior `extracted_needs_verify` row exists → write new row with
    `status='conflicted'` and link via `conflict_with`

═══════════════════════════════════════════════════════════════════════
  PUBLIC API
═══════════════════════════════════════════════════════════════════════

  route_extraction_to_bio_facts(items, narrator_id, *,
                                session_id=None, turn_id=None,
                                tenant_id='default') → RouteSummary
      Per-item routing. Returns a typed summary so the caller can
      log + emit metrics. Failures inside individual items never
      raise — the caller's extraction loop continues regardless.

  map_field_path_to_bio_key(field_path, item_context=None)
      → Optional[str]
      Pure mapping function (no DB). Used by routing AND by tests.

  routing_enabled() → bool
      Reads HORNELORE_BIO_FACT_ROUTING env flag. Default OFF so we
      can stage the integration without affecting production
      extraction behavior.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from .. import db
from . import bio_schema


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Field-path → bio_fields.field_key mapping
# ─────────────────────────────────────────────────────────────────────
#
# The legacy extractor produces dotted-path fieldPaths into a
# nested profile JSON schema. The bio_fields schema is flat. This
# table maps the most common high-traffic dotted-paths onto their
# canonical bio_fields keys.
#
# Context-sensitive paths (e.g., parents.firstName needs to know
# whether the parent is father or mother) are handled by
# _resolve_contextual_key() which inspects sibling fields in the
# same item's context.
#
# Unmapped paths return None — the bio write is skipped and the
# legacy family_truth_rows pipeline catches the proposal.

_DIRECT_FIELD_PATH_MAP: Dict[str, str] = {
    # ── identity ────────────────────────────────────────────────────
    "personal.dateOfBirth": "birth_date",
    "personal.placeOfBirth": "birth_place",
    "personal.fullName": "full_legal_name",
    "personal.preferredName": "preferred_name",
    "personal.middleName": "middle_name",
    "personal.nickname": "nickname",
    "personal.religionRaised": "religion_raised",
    "personal.faith": "religion_raised",
    "personal.ethnicity": "ethnicity_heritage",
    "personal.languagesAtHome": "languages_spoken_home",
    # ── family (non-context-sensitive) ──────────────────────────────
    "family.siblingCount": "sibling_count",
    "family.birthOrder": "birth_order",
    "siblings.birthOrder": "birth_order",
    # ── education ───────────────────────────────────────────────────
    "education.elementarySchool": "elementary_school",
    "education.schooling": "elementary_school",
    "education.highSchool": "high_school",
    "education.highSchoolGraduationYear": "high_school_graduation_year",
    "education.college": "college_attended",
    "education.collegeDegree": "college_degree",
    "education.collegeGraduationYear": "college_graduation_year",
    "education.gradSchool": "graduate_school",
    "education.higherEducation": "college_attended",
    "education.vocational": "vocational_training",
    # ── work ────────────────────────────────────────────────────────
    "work.firstJob": "first_job",
    "work.primaryCareer": "primary_career",
    "work.primaryEmployer": "primary_employer",
    "work.retirementYear": "retirement_year",
    "work.union": "union_membership",
    "community.role": "primary_career",
    "community.organization": "community_involvement",
    # ── military ────────────────────────────────────────────────────
    "military.branch": "military_branch",
    "military.servicePeriod": "military_service_period",
    "military.rank": "military_rank",
    "military.locations": "military_locations",
    "military.decorations": "military_decorations",
    # ── geography ───────────────────────────────────────────────────
    "residence.place": "current_residence",
    "residence.childhood": "childhood_geography",
    "residence.adultHomes": "adult_homes",
    # ── relationships (spouse non-indexed) ──────────────────────────
    "spouse.firstName": "spouse_name",
    "spouse.lastName": "spouse_name",
    "spouse.name": "spouse_name",
    "spouse.marriageYear": "marriage_year",
    "spouse.howMet": "how_met_spouse",
    "family.spouse.firstName": "spouse_name",
    "family.spouse.lastName": "spouse_name",
    "family.spouse.marriageYear": "marriage_year",
    "family.children.count": "children_count",
    "children.count": "children_count",
    "grandparents.count": "grandparents_named",
    # ── milestones ──────────────────────────────────────────────────
    "milestones.firstCar": "first_car",
    "milestones.firstHome": "first_home_purchase",
    "milestones.formative": "formative_event",
    "hobbies.primary": "hobby_primary",
    "laterYears.communityInvolvement": "community_involvement",
    "laterYears.hardship": "hardship_overcome",
}


# Contextual mapping rules — these fire when the bare path isn't
# enough. Each rule consumes the item's context (its peers in the same
# extraction batch) and returns the canonical key.
#
# Format: (fieldPath, [keys-that-must-equal-trigger]) → bio_key
# Example for parents.firstName with relation=father → father_name
_CONTEXTUAL_MAPPING_RULES = (
    # parents.* depends on parents.relation in the same item's context
    ("parents.firstName", "father", "father_name"),
    ("parents.firstName", "mother", "mother_name"),
    ("parents.firstName", "dad", "father_name"),
    ("parents.firstName", "mom", "mother_name"),
    ("parents.lastName", "father", "father_name"),
    ("parents.lastName", "mother", "mother_name"),
    ("parents.occupation", "father", "father_occupation"),
    ("parents.occupation", "mother", "mother_occupation"),
    ("parents.occupation", "dad", "father_occupation"),
    ("parents.occupation", "mom", "mother_occupation"),
    ("parents.placeOfBirth", "father", "father_birth_place"),
    ("parents.placeOfBirth", "mother", "mother_birth_place"),
    ("parents.birthYear", "father", "father_birth_year"),
    ("parents.birthYear", "mother", "mother_birth_year"),
    ("parents.maidenName", "mother", "mother_maiden_name"),
)


def _resolve_contextual_key(
    field_path: str,
    item_context: Optional[Dict[str, Any]],
) -> Optional[str]:
    """When a fieldPath needs sibling context (e.g., parents.firstName
    needs parents.relation), look up the relation hint in item_context
    and return the resolved bio_key. None when no rule matches."""
    if not item_context:
        return None
    relation = str(item_context.get("relation") or "").strip().lower()
    if not relation:
        return None
    for rule_path, rule_trigger, bio_key in _CONTEXTUAL_MAPPING_RULES:
        if rule_path == field_path and rule_trigger == relation:
            return bio_key
    return None


def map_field_path_to_bio_key(
    field_path: str,
    item_context: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Map a legacy dotted-path fieldPath onto a canonical bio_fields
    field_key, or None if no mapping exists.

    Tries direct lookup first; falls back to contextual rules when
    item_context (sibling fields from the same extraction batch) is
    available.
    """
    if not field_path:
        return None
    direct = _DIRECT_FIELD_PATH_MAP.get(field_path)
    if direct:
        return direct
    return _resolve_contextual_key(field_path, item_context)


# ─────────────────────────────────────────────────────────────────────
# Routing summary
# ─────────────────────────────────────────────────────────────────────


@dataclass
class RouteSummary:
    """Per-call summary from route_extraction_to_bio_facts.

    routed: bio_facts rows newly written
    conflicts: rows written with status='conflicted'
    suppressed_by_authority: items skipped because a higher-authority
        row already exists (document_sourced or approved)
    unmapped: items whose fieldPath had no bio_key mapping
    errors: items that raised during routing — counted, not raised
    """
    routed: int = 0
    conflicts: int = 0
    suppressed_by_authority: int = 0
    unmapped: int = 0
    errors: int = 0
    routed_ids: List[str] = field(default_factory=list)
    conflicted_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "routed": self.routed,
            "conflicts": self.conflicts,
            "suppressed_by_authority": self.suppressed_by_authority,
            "unmapped": self.unmapped,
            "errors": self.errors,
            "routed_ids": list(self.routed_ids),
            "conflicted_ids": list(self.conflicted_ids),
        }


# ─────────────────────────────────────────────────────────────────────
# Authority hierarchy
# ─────────────────────────────────────────────────────────────────────

# Statuses that block Tier 1 from writing a new conflicting row for
# the same (narrator, field_key). These represent operator or document
# authority that should not be silently overwritten by re-extraction.
_HIGHER_AUTHORITY_STATUSES: Set[str] = {
    "approved",
    "document_sourced",
    "operator_entered",
}


# ─────────────────────────────────────────────────────────────────────
# Public router
# ─────────────────────────────────────────────────────────────────────


def routing_enabled() -> bool:
    """Phase B is shipped behind a default-off env flag so production
    extraction stays byte-stable until the routing is verified end to
    end. Set HORNELORE_BIO_FACT_ROUTING=1 to enable."""
    return os.environ.get(
        "HORNELORE_BIO_FACT_ROUTING", "0",
    ).strip().lower() in ("1", "true", "yes", "on")


def route_extraction_to_bio_facts(
    items: List[Dict[str, Any]],
    narrator_id: str,
    *,
    session_id: Optional[str] = None,
    turn_id: Optional[str] = None,
    tenant_id: str = "default",
) -> RouteSummary:
    """Tier 1 router — for each extracted item, write a bio_facts row
    when its fieldPath maps to a bio_fields key and no higher-authority
    row already blocks it.

    Items must each carry at minimum: fieldPath, value, confidence.
    Optional: writeMode, relation (used by contextual mapping).

    The routing layer NEVER raises — per-item exceptions are caught,
    counted as errors, and the routing loop continues. This protects
    the caller's extraction commit loop from cascading failures.
    """
    summary = RouteSummary()
    if not narrator_id or not items:
        return summary

    bio_field_keys = bio_schema.get_field_keys()

    for raw in items:
        try:
            field_path = str(raw.get("fieldPath") or "").strip()
            value = raw.get("value")
            confidence = float(raw.get("confidence") or 0.0)
            # Build a small context dict for contextual mapping.
            # In v1, only `relation` is consulted; future rules may
            # extend with more peer fields.
            item_context = {
                "relation": raw.get("relation"),
            }
            bio_key = map_field_path_to_bio_key(field_path, item_context)
            if not bio_key:
                summary.unmapped += 1
                continue
            # Defensive: ensure the mapped key actually exists in the
            # seeded schema. If a mapping points at a key that was
            # since removed from the seed, skip cleanly rather than
            # FK-violate at INSERT time.
            if bio_key not in bio_field_keys:
                summary.unmapped += 1
                continue

            # Check existing rows for this (narrator, field_key)
            existing = db.bio_fact_list_by_field(narrator_id, bio_key)

            # Authority gate — higher authority blocks new write
            higher = next(
                (
                    r for r in existing
                    if r.get("status") in _HIGHER_AUTHORITY_STATUSES
                ),
                None,
            )
            if higher is not None:
                summary.suppressed_by_authority += 1
                continue

            # Conflict detection — any existing extracted_needs_verify
            # with different value → write new row as conflicted +
            # link
            value_json = json.dumps(value)
            conflict_with_id: Optional[str] = None
            new_status = "extracted_needs_verify"
            for r in existing:
                if r.get("status") == "extracted_needs_verify":
                    existing_value_json = r.get("value") or ""
                    if existing_value_json != value_json:
                        conflict_with_id = r.get("id")
                        new_status = "conflicted"
                        break

            source_payload = {
                "tier": 1,
                "session_id": session_id,
                "turn_id": turn_id,
                "field_path": field_path,
            }
            new_id = db.bio_fact_create(
                narrator_id=narrator_id,
                field_key=bio_key,
                value_json=value_json,
                status=new_status,
                source_json=json.dumps(source_payload),
                confidence=confidence,
                conflict_with=conflict_with_id,
                tenant_id=tenant_id,
            )
            if new_status == "conflicted" and conflict_with_id:
                # Promote the original peer to 'conflicted' too so
                # operator review surfaces both rows.
                try:
                    db.bio_fact_set_status(
                        conflict_with_id, "conflicted",
                        conflict_with=new_id,
                    )
                except Exception:
                    # Best-effort — original row stays in its
                    # current status if the linking update fails.
                    pass
                summary.conflicts += 1
                summary.conflicted_ids.append(new_id)
            else:
                summary.routed += 1
                summary.routed_ids.append(new_id)
        except Exception:
            # Per-item error — count and continue. Never let bio
            # routing break the caller's extraction loop.
            summary.errors += 1
            try:
                logger.exception(
                    "[bio_fact_router] per-item routing failed",
                )
            except Exception:
                pass

    return summary


__all__ = [
    "RouteSummary",
    "map_field_path_to_bio_key",
    "route_extraction_to_bio_facts",
    "routing_enabled",
]
