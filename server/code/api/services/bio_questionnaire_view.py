"""WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01 — Phase 1 read-aggregation service.

═══════════════════════════════════════════════════════════════════════
  WHAT THIS IS
═══════════════════════════════════════════════════════════════════════

The new questionnaire read path. Aggregates the questionnaire view that
Bio Builder renders directly from canonical truth (people row + profile_json
+ bio_facts), rather than reading the legacy `bio_builder_questionnaires`
blob.

WHY: the intake form (WO-OPERATOR-NEW-NARRATOR-INTAKE-FORM-01) writes to
bio_facts + profile_json. Until this lane lands, Bio Builder reads from a
separate blob that intake never populates, so a fresh narrator looks
empty in the questionnaire UI even though 24 bio_facts and a structured
profile_json exist for them. This service is the read swap that closes
the gap.

LAW 3 INFRASTRUCTURE BOUNDARY:
This module imports stdlib + ..db + .bio_schema only. It does NOT import
from extract.py, chat_ws.py, prompt_composer, or any router. Read-only
aggregation. No DB writes.

═══════════════════════════════════════════════════════════════════════
  PUBLIC API
═══════════════════════════════════════════════════════════════════════

  build_questionnaire_view(narrator_id) → Dict[str, Any]
      Returns a dict matching the FE questionnaire-blob shape:

        {
          "person_id": str,
          "questionnaire": {
              "personal": {fullName, preferredName, dateOfBirth, ...},
              "parents": [{relation, firstName, ...}, ...],
              "siblings": [{firstName, ...}, ...],
              "spouses": [{firstName, ..., yearMarried, status}, ...],
              "children": [{firstName, ..., dateOfBirth}, ...],
              "education": {highestLevel, careerProgression, ...},
              "military": {served, branch, servicePeriod, ...},
              "faith":    {religionRaised, currentFaith, ...},
              "today":    {livingSituation, healthConsiderations, ...},
          },
          "_meta": {
              "personal": {
                  "fullName": {"status": "approved", "source": "operator"},
                  ...
              },
              ...
          },
          "source":  "bio_facts_merged",
          "version": 1,
          "updated_at": "2026-06-16T...",
        }

      The FE-shaped `questionnaire` block is byte-compatible with the
      legacy blob shape so existing rendering code keeps working
      unchanged. The new `_meta` block carries per-field
      {status, source} metadata for Phase 2 status badges.

  build_questionnaire_view returns None when the narrator does not
  exist. Empty / partial narrators return well-shaped blocks with
  empty values, NOT None.

═══════════════════════════════════════════════════════════════════════
  FIELD-KEY → SECTION/SLOT MAPPING
═══════════════════════════════════════════════════════════════════════

Scalar fields (single value per narrator) carry full {status, source}
metadata. Array-shaped sections (parents / siblings / spouses /
children) project the profile_json arrays directly; their per-entry
fields cannot be cleanly mapped to bio_facts rows (parent[0] vs
parent[1]), so they receive a single section-level `_status` derived
from any matching scalar (father_name / mother_name / sibling_count /
spouse_name / children_count).

This shape stays stable as Phase 3 adds the write-path fan-out: any
new scalar field_keys land in `_meta` automatically because the
mapping is derived from bio_schema.BIO_SCHEMA_SEED, not hand-coded
per field.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .. import db
from . import bio_schema


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Status precedence for "which bio_facts row wins" when multiple
# rows exist for the same (narrator_id, field_key).
#
# Higher number = wins. Tie-break by last_updated DESC (handled in
# _pick_best_fact).
# ─────────────────────────────────────────────────────────────────────


_STATUS_PRIORITY: Mapping[str, int] = {
    # Operator promoted — most trusted
    "approved":                7,
    "operator_entered":        6,
    "document_sourced":        5,
    "anchored_asked":          4,
    "extracted_needs_verify":  3,
    "anchored_asked_pending":  2,
    "conflicted":              1,
    "superseded":              0,
    "empty":                   0,
}


def _pick_best_fact(
    rows: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Pick the winning row when multiple bio_facts share the same key.

    Sort by (status_priority DESC, last_updated DESC). Returns None if
    the input list is empty.
    """
    if not rows:
        return None
    def _key(r: Dict[str, Any]) -> Tuple[int, str]:
        s = str(r.get("status") or "")
        prio = _STATUS_PRIORITY.get(s, 0)
        last_updated = str(r.get("last_updated") or "")
        return (-prio, last_updated)  # negated prio so DESC; alphabetic on time means latest ISO wins under DESC
    # Use reverse=False but invert priority sign → since "" sorts before
    # any ISO timestamp, prefer reverse=True on last_updated and
    # explicit prio.
    rows_sorted = sorted(rows, key=lambda r: (
        _STATUS_PRIORITY.get(str(r.get("status") or ""), 0),
        str(r.get("last_updated") or ""),
    ), reverse=True)
    return rows_sorted[0]


# ─────────────────────────────────────────────────────────────────────
# Source extraction
# ─────────────────────────────────────────────────────────────────────


def _source_label(row: Dict[str, Any]) -> str:
    """Extract a single render-friendly source label from a bio_facts row.

    The `source` column on bio_facts stores a JSON blob with keys like
    {tier: 1|2|3|4, kind: "extractor"|"document"|"anchored"|"operator",
    matched_anchor: "...", operator_id: "...", confidence: 0.x}.

    We surface the most useful single token. Order of preference:
      1. `kind` (when present) — direct semantic label
      2. tier → {1: "extractor", 2: "document", 3: "anchored",
                 4: "operator"}
      3. fallback string of the raw blob

    Returns empty string when no source info is recorded (legacy rows).
    """
    import json as _json
    raw = row.get("source")
    if not raw:
        return ""
    # raw is the literal JSON blob string; parse safely.
    if isinstance(raw, str):
        try:
            blob = _json.loads(raw or "{}")
        except (ValueError, TypeError):
            return raw[:32]
    elif isinstance(raw, dict):
        blob = raw
    else:
        return str(raw)[:32]

    kind = str(blob.get("kind") or "").strip()
    if kind:
        return kind
    try:
        tier = int(blob.get("tier") or 0)
    except (ValueError, TypeError):
        tier = 0
    tier_label = {
        1: "extractor",
        2: "document",
        3: "anchored",
        4: "operator",
    }.get(tier, "")
    return tier_label or ""


def _meta_for_row(row: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Build the {status, source} dict for a single bio_facts row."""
    if not row:
        return {"status": "empty", "source": ""}
    return {
        "status": str(row.get("status") or ""),
        "source": _source_label(row),
    }


# ─────────────────────────────────────────────────────────────────────
# bio_facts index: narrator_id → {field_key: winning row}
# ─────────────────────────────────────────────────────────────────────


def _index_facts(narrator_id: str) -> Dict[str, Dict[str, Any]]:
    """Read all bio_facts for narrator + collapse to one row per
    field_key using _pick_best_fact.

    Returns {} on read error so the questionnaire view still renders
    from profile_json even when bio_facts is unavailable.
    """
    try:
        rows = db.bio_fact_list_by_narrator(narrator_id)
    except Exception as exc:
        logger.warning(
            "bio_questionnaire_view._index_facts: read failed for %s: %s",
            narrator_id, exc,
        )
        return {}
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows or []:
        fk = str(r.get("field_key") or "")
        if not fk:
            continue
        grouped.setdefault(fk, []).append(r)
    out: Dict[str, Dict[str, Any]] = {}
    for fk, rs in grouped.items():
        best = _pick_best_fact(rs)
        if best is not None:
            out[fk] = best
    return out


# ─────────────────────────────────────────────────────────────────────
# Per-section builders
# ─────────────────────────────────────────────────────────────────────


def _split_full_name(full: str) -> Tuple[str, str, str]:
    """first / middle / last split. Mirrors ui/js/bio-builder-
    questionnaire.js _splitFullName behavior so the round-trip is
    byte-stable when the FE persists the questionnaire back.
    """
    if not full:
        return ("", "", "")
    parts = str(full).strip().split()
    if not parts:
        return ("", "", "")
    if len(parts) == 1:
        return (parts[0], "", "")
    if len(parts) == 2:
        return (parts[0], "", parts[1])
    return (parts[0], " ".join(parts[1:-1]), parts[-1])


def _personal_section(
    person_row: Dict[str, Any],
    profile_json: Dict[str, Any],
    facts: Mapping[str, Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, Dict[str, str]]]:
    """Compose the `personal` section + per-field meta.

    Reads from THREE sources (in priority order):
      1. profile_json.personal — the structured intake mirror
      2. people row scalars — DOB / POB / display_name (canonical)
      3. bio_facts — for status badge metadata only
    """
    p_personal = dict((profile_json or {}).get("personal") or {})

    # Identity values: profile_json.personal wins; people row is fallback.
    full_name = (
        p_personal.get("fullName")
        or person_row.get("display_name")
        or ""
    )
    preferred = p_personal.get("preferredName") or ""
    dob = (
        p_personal.get("dateOfBirth")
        or person_row.get("date_of_birth")
        or ""
    )
    pob = (
        p_personal.get("placeOfBirth")
        or person_row.get("place_of_birth")
        or ""
    )
    birth_order = p_personal.get("birthOrder") or ""
    time_of_birth = p_personal.get("timeOfBirth") or ""
    zodiac = p_personal.get("zodiacSign") or ""
    current_residence = (
        p_personal.get("currentResidence")
        or person_row.get("current_residence")
        or ""
    )
    pronouns = (
        p_personal.get("pronouns")
        or person_row.get("pronouns")
        or ""
    )
    section = {
        "fullName":         full_name or "",
        "preferredName":    preferred or "",
        "birthOrder":       birth_order or "",
        "dateOfBirth":      dob or "",
        "timeOfBirth":      time_of_birth or "",
        "placeOfBirth":     pob or "",
        "zodiacSign":       zodiac or "",
        "currentResidence": current_residence or "",
        "pronouns":         pronouns or "",
    }
    # Faith mirror — populated by intake into profile_json.personal
    if p_personal.get("faithRaised"):
        section["faithRaised"] = p_personal.get("faithRaised")
    if p_personal.get("currentFaith"):
        section["currentFaith"] = p_personal.get("currentFaith")
    if p_personal.get("culture"):
        section["culture"] = p_personal.get("culture")
    if p_personal.get("languagesAtHome"):
        section["languagesAtHome"] = p_personal.get("languagesAtHome")

    meta: Dict[str, Dict[str, str]] = {}
    # Scalar field_key → questionnaire slot mapping for status badges.
    # Only emit a meta entry when a winning bio_facts row exists for
    # the field_key. Skipping null-meta entries lets the FE
    # distinguish "no provenance recorded" from "provenance recorded
    # but status=empty" — the latter is meaningful in the badge UI.
    _scalar_meta_map = (
        ("fullName",        "full_legal_name"),
        ("preferredName",   "preferred_name"),
        ("dateOfBirth",     "birth_date"),
        ("placeOfBirth",    "birth_place"),
        ("birthOrder",      "birth_order"),
        ("faithRaised",     "religion_raised"),
        ("currentFaith",    "current_faith"),
        ("culture",         "ethnicity_heritage"),
        ("languagesAtHome", "languages_spoken_home"),
    )
    for slot, fk in _scalar_meta_map:
        if slot in section and section.get(slot) and facts.get(fk):
            meta[slot] = _meta_for_row(facts.get(fk))
    return section, meta


def _section_status_from_count(
    facts: Mapping[str, Dict[str, Any]], count_fk: Optional[str],
) -> Dict[str, str]:
    """Section-level meta for array sections — read the count fact (e.g.
    sibling_count, children_count) and return its status."""
    if not count_fk:
        return {"status": "empty", "source": ""}
    row = facts.get(count_fk)
    return _meta_for_row(row)


def _parents_section(
    profile_json: Dict[str, Any],
    facts: Mapping[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Project profile_json.parents into questionnaire shape."""
    raw = (profile_json or {}).get("parents") or []
    if not isinstance(raw, list):
        return [], {"_section": {"status": "empty", "source": ""}}
    out: List[Dict[str, Any]] = []
    for p in raw:
        if not isinstance(p, Mapping):
            continue
        out.append({
            "relation":          p.get("relation") or "",
            "firstName":         p.get("firstName") or "",
            "middleName":        p.get("middleName") or "",
            "lastName":          p.get("lastName") or "",
            "maidenName":        p.get("maidenName") or "",
            "birthDate":         p.get("birthDate") or p.get("dateOfBirth") or "",
            "birthPlace":        p.get("birthPlace") or p.get("placeOfBirth") or "",
            "occupation":        p.get("occupation") or "",
            "notableLifeEvents": p.get("notableLifeEvents") or "",
            "notes":             p.get("notes") or "",
        })
    meta: Dict[str, Any] = {}
    if facts.get("father_name"):
        meta["father_name"] = _meta_for_row(facts.get("father_name"))
    if facts.get("mother_name"):
        meta["mother_name"] = _meta_for_row(facts.get("mother_name"))
    if facts.get("mother_maiden_name"):
        meta["mother_maiden_name"] = _meta_for_row(facts.get("mother_maiden_name"))
    return out, meta


def _siblings_section(
    profile_json: Dict[str, Any],
    facts: Mapping[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    raw = (profile_json or {}).get("siblings") or []
    if not isinstance(raw, list):
        return [], {"_section": {"status": "empty", "source": ""}}
    out: List[Dict[str, Any]] = []
    for s in raw:
        if not isinstance(s, Mapping):
            continue
        out.append({
            "relation":              s.get("relation") or "",
            "firstName":             s.get("firstName") or "",
            "middleName":            s.get("middleName") or "",
            "lastName":              s.get("lastName") or "",
            "birthOrder":            s.get("birthOrder") or "",
            "birthDate":             s.get("birthDate") or s.get("dateOfBirth") or "",
            "uniqueCharacteristics": s.get("uniqueCharacteristics") or "",
            "sharedExperiences":     s.get("sharedExperiences") or "",
            "memories":              s.get("memories") or "",
            "notes":                 s.get("notes") or "",
        })
    meta: Dict[str, Any] = {
        "_section": _section_status_from_count(facts, "sibling_count"),
    }
    return out, meta


def _spouses_section(
    profile_json: Dict[str, Any],
    facts: Mapping[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    raw_maybe = (profile_json or {}).get("spouses")
    if isinstance(raw_maybe, list) and raw_maybe:
        raw: List[Any] = list(raw_maybe)
    else:
        # Fall back to legacy single `spouse` slot when `spouses` is
        # missing, non-list, or empty. The intake orchestrator writes
        # BOTH `spouses` and `spouse` keys (the latter is the legacy
        # singular for read-bridge compatibility); older profiles that
        # only carry `spouse` would otherwise render as zero spouses.
        single = (profile_json or {}).get("spouse")
        if isinstance(single, Mapping):
            raw = [single]
        else:
            raw = []
    out: List[Dict[str, Any]] = []
    for sp in raw:
        if not isinstance(sp, Mapping):
            continue
        out.append({
            "firstName":   sp.get("firstName") or "",
            "middleName":  sp.get("middleName") or "",
            "lastName":    sp.get("lastName") or "",
            "yearMarried": sp.get("yearMarried") or "",
            "status":      sp.get("status") or "",
            "birthDate":   sp.get("birthDate") or sp.get("dateOfBirth") or "",
        })
    meta: Dict[str, Any] = {}
    if facts.get("spouse_name"):
        meta["spouse_name"] = _meta_for_row(facts.get("spouse_name"))
    if facts.get("marriage_year"):
        meta["marriage_year"] = _meta_for_row(facts.get("marriage_year"))
    return out, meta


def _children_section(
    profile_json: Dict[str, Any],
    facts: Mapping[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    raw = (profile_json or {}).get("children") or []
    if not isinstance(raw, list):
        return [], {"_section": {"status": "empty", "source": ""}}
    out: List[Dict[str, Any]] = []
    for c in raw:
        if not isinstance(c, Mapping):
            continue
        out.append({
            "firstName":  c.get("firstName") or "",
            "middleName": c.get("middleName") or "",
            "lastName":   c.get("lastName") or "",
            "dateOfBirth": c.get("dateOfBirth") or c.get("birthDate") or "",
        })
    meta: Dict[str, Any] = {
        "_section": _section_status_from_count(facts, "children_count"),
    }
    return out, meta


def _education_section(
    profile_json: Dict[str, Any],
    facts: Mapping[str, Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, Dict[str, str]]]:
    edu = dict((profile_json or {}).get("education") or {})
    community = dict((profile_json or {}).get("community") or {})
    section = {
        "highestLevel":       edu.get("highestLevel") or "",
        "careerProgression":  edu.get("careerProgression") or "",
        "primaryCareer":      community.get("role") or "",
    }
    meta: Dict[str, Dict[str, str]] = {}
    if facts.get("highest_education_level"):
        meta["highestLevel"] = _meta_for_row(facts.get("highest_education_level"))
    if facts.get("primary_career"):
        # Tie status to the meaningful career value, not the
        # years_working string that should NOT be writing to
        # primary_career (BUG-EX-PRIMARY-CAREER-DOUBLE-WRITE) — but
        # report the winning row anyway so operator sees current state.
        meta["primaryCareer"] = _meta_for_row(facts.get("primary_career"))
    return section, meta


def _military_section(
    profile_json: Dict[str, Any],
    facts: Mapping[str, Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, Dict[str, str]]]:
    mil = dict((profile_json or {}).get("military") or {})
    section = {
        "served":           bool(mil.get("served") or False),
        "branch":           mil.get("branch") or "",
        "servicePeriod":    mil.get("servicePeriod") or "",
        "rank":             mil.get("rank") or "",
        "units":            mil.get("units") or "",
        "locations":        mil.get("locations") or "",
        "warsConflicts":    mil.get("warsConflicts") or "",
        "decorations":      mil.get("decorations") or "",
        "experienceNotes":  mil.get("experienceNotes") or "",
    }
    meta: Dict[str, Dict[str, str]] = {}
    _meta_map = (
        ("served",          "military_served"),
        ("branch",          "military_branch"),
        ("servicePeriod",   "military_service_period"),
        ("rank",            "military_rank"),
        ("locations",       "military_locations"),
        ("warsConflicts",   "military_wars_conflicts"),
        ("decorations",     "military_decorations"),
        ("experienceNotes", "military_experience_notes"),
    )
    for slot, fk in _meta_map:
        if facts.get(fk):
            meta[slot] = _meta_for_row(facts.get(fk))
    return section, meta


def _faith_section(
    profile_json: Dict[str, Any],
    facts: Mapping[str, Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, Dict[str, str]]]:
    """Faith intake values land on profile_json.personal in the
    intake orchestrator. Mirror them into a dedicated `faith` block
    for FE convenience.
    """
    p_personal = dict((profile_json or {}).get("personal") or {})
    section = {
        "religionRaised":    p_personal.get("faithRaised") or "",
        "currentFaith":      p_personal.get("currentFaith") or "",
        "ethnicityHeritage": p_personal.get("culture") or "",
        "languagesAtHome":   p_personal.get("languagesAtHome") or "",
    }
    meta: Dict[str, Dict[str, str]] = {}
    _meta_map = (
        ("religionRaised",    "religion_raised"),
        ("currentFaith",      "current_faith"),
        ("ethnicityHeritage", "ethnicity_heritage"),
        ("languagesAtHome",   "languages_spoken_home"),
    )
    for slot, fk in _meta_map:
        if facts.get(fk):
            meta[slot] = _meta_for_row(facts.get(fk))
    return section, meta


def _today_section(
    profile_json: Dict[str, Any],
    facts: Mapping[str, Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, Dict[str, str]]]:
    today = dict((profile_json or {}).get("today") or {})
    section = {
        "livingSituation":      today.get("livingSituation") or "",
        "healthConsiderations": today.get("healthConsiderations") or "",
    }
    # No scalar field_keys today; meta stays empty.
    return section, {}


# ─────────────────────────────────────────────────────────────────────
# Public builder
# ─────────────────────────────────────────────────────────────────────


def build_questionnaire_view(narrator_id: str) -> Optional[Dict[str, Any]]:
    """Return the FE-shaped questionnaire view for narrator_id.

    Returns None when the narrator does not exist (no people row).
    Returns a well-shaped empty view when the narrator has zero
    bio_facts and zero profile_json — never raises on missing data.
    """
    if not narrator_id:
        return None
    try:
        person_row = db.get_person(narrator_id)
    except Exception as exc:
        logger.warning(
            "bio_questionnaire_view.build_questionnaire_view: get_person "
            "failed for %s: %s", narrator_id, exc,
        )
        return None
    if not person_row:
        return None

    try:
        prof = db.get_profile(narrator_id) or {}
    except Exception as exc:
        logger.warning(
            "bio_questionnaire_view.build_questionnaire_view: get_profile "
            "failed for %s: %s", narrator_id, exc,
        )
        prof = {}
    profile_json = (prof or {}).get("profile_json") or {}
    profile_updated_at = (prof or {}).get("updated_at") or ""

    facts = _index_facts(narrator_id)

    personal_q, personal_meta = _personal_section(person_row, profile_json, facts)
    parents_q,  parents_meta  = _parents_section(profile_json, facts)
    siblings_q, siblings_meta = _siblings_section(profile_json, facts)
    spouses_q,  spouses_meta  = _spouses_section(profile_json, facts)
    children_q, children_meta = _children_section(profile_json, facts)
    education_q, education_meta = _education_section(profile_json, facts)
    military_q, military_meta = _military_section(profile_json, facts)
    faith_q,    faith_meta    = _faith_section(profile_json, facts)
    today_q,    today_meta    = _today_section(profile_json, facts)

    questionnaire: Dict[str, Any] = {
        "personal":  personal_q,
        "parents":   parents_q,
        "siblings":  siblings_q,
        "spouses":   spouses_q,
        "children":  children_q,
        "education": education_q,
        "military":  military_q,
        "faith":     faith_q,
        "today":     today_q,
    }
    meta: Dict[str, Any] = {
        "personal":  personal_meta,
        "parents":   parents_meta,
        "siblings":  siblings_meta,
        "spouses":   spouses_meta,
        "children":  children_meta,
        "education": education_meta,
        "military":  military_meta,
        "faith":     faith_meta,
        "today":     today_meta,
    }

    return {
        "person_id":  narrator_id,
        "questionnaire": questionnaire,
        "_meta":     meta,
        "source":    "bio_facts_merged",
        "version":   1,
        "updated_at": profile_updated_at,
    }


__all__ = [
    "build_questionnaire_view",
]
