"""WO-CR-01 — Chronology Accordion Router

Read-only endpoint that merges three lanes into a decade/year accordion payload:
  Lane A: world events from historical_events_1900_2026.json (cached at startup)
  Lane B: verified personal anchors from promoted truth / profile / questionnaire
  Lane C: ghost prompt cues from static life-stage templates

Authority contract: this endpoint NEVER writes to facts, timeline, questionnaire,
archive, or any other truth table.  It only READS.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from .. import db
from ..db import (
    ensure_profile,
    ft_list_promoted,
    get_person,
    get_profile,
    get_questionnaire,
)
from ..flags import truth_v2_enabled

logger = logging.getLogger("chronology_accordion")

router = APIRouter(prefix="/api", tags=["chronology"])

# ─── ERA / AGE MAP ────────────────────────────────────────────────
# Must mirror TIMELINE_ORDER + ERA_AGE_MAP in app.js exactly.
TIMELINE_ORDER = [
    "early_childhood",
    "school_years",
    "adolescence",
    "early_adulthood",
    "midlife",
    "later_life",
]

ERA_AGE_MAP = {
    "early_childhood":  {"start": 0,  "end": 5},
    "school_years":     {"start": 6,  "end": 12},
    "adolescence":      {"start": 13, "end": 18},
    "early_adulthood":  {"start": 19, "end": 30},
    "midlife":          {"start": 31, "end": 55},
    "later_life":       {"start": 56, "end": None},
}

# ─── HISTORICAL SEED (loaded once, cached) ────────────────────────
_SEED_CACHE: Optional[List[Dict[str, Any]]] = None


def _seed_path() -> Path:
    """Resolve the historical events JSON file relative to the server dir."""
    return (
        Path(__file__).resolve().parents[3]  # routers → api → code → server
        / "data" / "historical" / "historical_events_1900_2026.json"
    )


def load_historical_seed() -> List[Dict[str, Any]]:
    """Load historical events from disk on first call, cache thereafter."""
    global _SEED_CACHE
    if _SEED_CACHE is not None:
        return _SEED_CACHE

    seed_file = _seed_path()
    if not seed_file.exists():
        logger.warning("Historical seed file not found: %s", seed_file)
        _SEED_CACHE = []
        return _SEED_CACHE

    with open(seed_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    events = data.get("events", [])
    _SEED_CACHE = events
    logger.info("Loaded %d historical events from seed file", len(events))
    return _SEED_CACHE


# ─── SCAFFOLD ─────────────────────────────────────────────────────

def build_scaffold_periods(birth_year: int) -> List[Dict[str, Any]]:
    """Build fallback life-period scaffold from birth year using ERA_AGE_MAP."""
    periods = []
    for label in TIMELINE_ORDER:
        ages = ERA_AGE_MAP[label]
        periods.append({
            "label": label,
            "start_year": birth_year + ages["start"],
            "end_year": (birth_year + ages["end"]) if ages["end"] is not None else None,
        })
    return periods


def year_to_era(year: int, periods: List[Dict[str, Any]]) -> Optional[str]:
    """Map a calendar year to an era label using the periods list.

    If year falls after the last period's start (later_life with end=None),
    it maps to later_life.  Years before birth return None.
    """
    for p in periods:
        start = p["start_year"]
        end = p.get("end_year")
        if end is None:
            # later_life — open-ended
            if year >= start:
                return p["label"]
        else:
            if start <= year <= end:
                return p["label"]
    return None


# ─── LANE A: WORLD EVENTS ────────────────────────────────────────

def filter_world_events(
    events: List[Dict[str, Any]],
    birth_year: int,
) -> List[Dict[str, Any]]:
    """Filter historical events to the narrator's lifetime.

    Only includes events from birth_year onward.
    Returns ChronologyItem-shaped dicts.
    """
    items = []
    for ev in events:
        yr = ev.get("year", 0)
        if yr < birth_year:
            continue
        items.append({
            "year": yr,
            "label": ev.get("label", ""),
            "lane": "world",
            "category": ev.get("category", ""),
            "tags": ev.get("tags", []),
            "id": ev.get("id", ""),
        })
    return items


# ─── LANE B: PERSONAL ANCHORS ────────────────────────────────────
# Strict whitelists — only these exact keys become anchors.  No substring matching.
#
# Three sources, precedence highest-to-lowest:
#   1. Promoted truth (authoritative, reviewed & approved)
#   2. Profile basics (identity fields captured during onboarding)
#   3. Interview projection / questionnaire (same key space, used as fallback)
#
# Each whitelist maps the exact source key → a short display label.
# `_value_is_date` controls whether we try to pull a year from the value.
# Values that don't yield a valid year are dropped silently (never invented).

# Promoted-truth field names (family_truth_promoted.field).
# These are what the extraction + review pipeline produces.  Expand as the
# pipeline starts promoting more fields — keep this map explicit.
_PROMOTED_ANCHOR_FIELDS: Dict[str, Dict[str, Any]] = {
    "date_of_birth":         {"label": "Born",            "date": True},
    "place_of_birth":        {"label": "Birthplace",      "date": False},
    "date_of_marriage":      {"label": "Married",         "date": True},
    "place_of_marriage":     {"label": "Wedding",         "date": False},
    "date_of_graduation":    {"label": "Graduated",       "date": True},
    "date_of_enlistment":    {"label": "Enlisted",        "date": True},
    "date_of_discharge":     {"label": "Discharged",      "date": True},
    "date_of_first_job":     {"label": "First job",       "date": True},
    "date_of_retirement":    {"label": "Retired",         "date": True},
    "date_of_immigration":   {"label": "Immigrated",      "date": True},
    "date_of_move":          {"label": "Moved",           "date": True},
    "date_of_first_child":   {"label": "First child",     "date": True},
    "date_of_divorce":       {"label": "Divorced",        "date": True},
}

# Profile basics keys (profile_json.basics.<key>).
# Only dob produces a year anchor today; pob is attached as location context.
_PROFILE_ANCHOR_KEYS: Dict[str, Dict[str, Any]] = {
    "dob": {"label": "Born",       "date": True,  "equiv_field": "date_of_birth"},
    "pob": {"label": "Birthplace", "date": False, "equiv_field": "place_of_birth"},
}

# Questionnaire / interview-projection flat keys.
# Must match the canonical key space used by bio-builder-questionnaire.js
# and projection-sync.js (verified against live DB 2026-04-14).
_QUESTIONNAIRE_ANCHOR_KEYS: Dict[str, Dict[str, Any]] = {
    "personal.dateOfBirth":   {"label": "Born",       "date": True,  "equiv_field": "date_of_birth"},
    "personal.placeOfBirth":  {"label": "Birthplace", "date": False, "equiv_field": "place_of_birth"},
    "personal.dateOfDeath":   {"label": "Died",       "date": True,  "equiv_field": "date_of_death"},
    # Future questionnaire sections — add keys explicitly as they go live.
    # "education.graduationDate": {"label": "Graduated", "date": True, "equiv_field": "date_of_graduation"},
    # "marriage.weddingDate":     {"label": "Married",   "date": True, "equiv_field": "date_of_marriage"},
}


def _extract_year(value: Any) -> Optional[int]:
    """Try to extract a 4-digit year from a value string.

    Accepts ISO dates (1962-12-24), US-style (12/24/1962), and bare years (1962).
    Returns None if no plausible year (1850-2100) is found.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    # Normalize separators so we can split once.
    parts = s.replace("-", " ").replace("/", " ").replace(",", " ").split()
    for p in parts:
        if len(p) == 4 and p.isdigit():
            yr = int(p)
            if 1850 <= yr <= 2100:
                return yr
    return None


def project_personal_anchors(
    basics: Dict[str, Any],
    questionnaire: Dict[str, Any],
    promoted_rows: List[Dict[str, Any]],
    narrator_display_name: str = "",
) -> List[Dict[str, Any]]:
    """Extract verified personal anchors — narrator (self) only.

    Precedence: promoted truth > profile basics > questionnaire/projection.
    Returns ChronologyItem-shaped dicts with lane='personal'.

    Args:
        basics: profile_json.basics dict ({"dob": "...", "pob": "...", ...})
        questionnaire: result of db.get_questionnaire(person_id) — {"questionnaire": {...}}
        promoted_rows: list of family_truth_promoted rows (list of dicts)
        narrator_display_name: used to filter promoted rows to self-subject only
    """
    items: List[Dict[str, Any]] = []
    seen_equiv_fields: set = set()

    # Helper: dedupe on equivalent field id (so promoted date_of_birth beats
    # profile dob beats questionnaire personal.dateOfBirth)
    def _already_seen(field_id: str) -> bool:
        return field_id in seen_equiv_fields

    def _remember(field_id: str) -> None:
        seen_equiv_fields.add(field_id)

    # ── 1. Promoted truth (highest authority) ────────────────────
    # Only accept rows where the subject is the narrator themselves.
    name_lower = (narrator_display_name or "").strip().lower()
    for row in promoted_rows:
        field = (row.get("field") or "").strip()
        spec = _PROMOTED_ANCHOR_FIELDS.get(field)
        if not spec:
            continue

        # Self-filter: skip rows about other subjects (spouse, parent, etc.)
        subject = (row.get("subject_name") or "").strip().lower()
        relationship = (row.get("relationship") or "").strip().lower()
        if relationship and relationship not in ("self", "narrator", ""):
            continue
        if subject and name_lower and subject != name_lower:
            continue

        if _already_seen(field):
            continue

        value = (row.get("value") or "").strip()
        if not value:
            continue

        if spec["date"]:
            yr = _extract_year(value)
            if yr is None:
                continue
            label = f"{spec['label']}: {value}"
        else:
            # Non-date promoted anchor — skip for now since accordion is year-indexed.
            # (place_of_birth will be shown as context on the date_of_birth anchor instead.)
            continue

        _remember(field)
        items.append({
            "year": yr,
            "label": label,
            "lane": "personal",
            "field": field,
            "source": "promoted_truth",
        })

    # ── 2. Profile basics (identity captured during onboarding) ─
    # Build a single enriched "Born" anchor that combines dob + pob when available.
    dob = str(basics.get("dob") or "").strip() if basics else ""
    pob = str(basics.get("pob") or "").strip() if basics else ""
    if dob and not _already_seen("date_of_birth"):
        yr = _extract_year(dob)
        if yr is not None:
            label = f"Born: {dob}" if not pob else f"Born in {pob} — {dob}"
            _remember("date_of_birth")
            _remember("place_of_birth")
            items.append({
                "year": yr,
                "label": label,
                "lane": "personal",
                "field": "date_of_birth",
                "source": "profile",
            })

    # ── 3. Questionnaire / interview projection (fallback) ──────
    q_obj = questionnaire.get("questionnaire", {}) if questionnaire else {}

    # Flatten nested section.* keys so "personal.dateOfBirth" can be looked up.
    def _flatten(obj: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if not isinstance(obj, dict):
            return out
        for k, v in obj.items():
            kp = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                out.update(_flatten(v, kp))
            else:
                out[kp] = v
        return out

    flat = _flatten(q_obj)
    for q_key, spec in _QUESTIONNAIRE_ANCHOR_KEYS.items():
        equiv = spec.get("equiv_field") or q_key
        if _already_seen(equiv):
            continue
        val = flat.get(q_key)
        if val is None or str(val).strip() == "":
            continue
        if not spec["date"]:
            continue
        yr = _extract_year(val)
        if yr is None:
            continue
        _remember(equiv)
        items.append({
            "year": yr,
            "label": f"{spec['label']}: {val}",
            "lane": "personal",
            "field": equiv,
            "source": "questionnaire",
        })

    return items


# ─── LANE C: GHOST PROMPTS ───────────────────────────────────────
# One ghost per life-stage band, placed at midpoint year.

_GHOST_TEMPLATES = {
    "early_childhood":  "What's your earliest memory from childhood?",
    "school_years":     "What was school like for you growing up?",
    "adolescence":      "What were your teenage years like?",
    "early_adulthood":  "What was life like when you were first on your own?",
    "midlife":          "What stands out about your middle years?",
    "later_life":       "What has this chapter of life been like for you?",
}


def build_band_ghosts(
    birth_year: int,
    periods: List[Dict[str, Any]],
    personal_items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Generate ghost prompt items — one per life-stage band at midpoint year.

    Suppresses ghost for a band if that band already has >=2 personal anchors.
    """
    # Count personal items per era
    era_counts: Dict[str, int] = {}
    for item in personal_items:
        era = year_to_era(item.get("year", 0), periods)
        if era:
            era_counts[era] = era_counts.get(era, 0) + 1

    items = []
    current_year = 2026  # cap for later_life

    for p in periods:
        label = p["label"]
        if label not in _GHOST_TEMPLATES:
            continue
        # Suppress if band already has 2+ personal anchors
        if era_counts.get(label, 0) >= 2:
            continue

        start = p["start_year"]
        end = p.get("end_year")
        if end is None:
            end = min(birth_year + 90, current_year)
        midpoint = (start + end) // 2

        items.append({
            "year": midpoint,
            "label": _GHOST_TEMPLATES[label],
            "lane": "ghost",
            "era": label,
        })

    return items


# ─── GROUP BY DECADE ──────────────────────────────────────────────

def group_by_decade(
    items: List[Dict[str, Any]],
    periods: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Group items into decade buckets, each containing year sub-groups.

    Returns:
      [
        {
          "decade": 1940,
          "decade_label": "1940s",
          "years": [
            {
              "year": 1940,
              "era": "early_childhood",
              "items": [ ... ]
            },
            ...
          ]
        },
        ...
      ]
    Sorted by decade ascending, years ascending within each decade.
    """
    # Collect items by decade → year
    decade_map: Dict[int, Dict[int, List[Dict[str, Any]]]] = {}
    for item in items:
        yr = item.get("year", 0)
        decade = (yr // 10) * 10
        if decade not in decade_map:
            decade_map[decade] = {}
        if yr not in decade_map[decade]:
            decade_map[decade][yr] = []
        decade_map[decade][yr].append(item)

    # Build sorted output
    result = []
    for decade in sorted(decade_map.keys()):
        year_groups = []
        for yr in sorted(decade_map[decade].keys()):
            era = year_to_era(yr, periods)
            year_groups.append({
                "year": yr,
                "era": era,
                "items": decade_map[decade][yr],
            })
        result.append({
            "decade": decade,
            "decade_label": f"{decade}s",
            "years": year_groups,
        })

    return result


# ─── MAIN BUILDER ─────────────────────────────────────────────────

def build_chronology_accordion_payload(
    person_id: str,
    profile: Dict[str, Any],
    questionnaire: Dict[str, Any],
    promoted_rows: List[Dict[str, Any]],
    narrator_display_name: str = "",
) -> Dict[str, Any]:
    """Build the full chronology accordion payload.

    Returns the complete JSON response shape for the frontend.
    """
    # Normalize incoming profile shape.  Accepts:
    #   {"basics": {...}}           → use the basics sub-dict
    #   {"dob": ..., "pob": ...}    → already a basics dict
    if isinstance(profile, dict) and "basics" in profile:
        basics = profile["basics"] or {}
    else:
        basics = profile or {}

    # Extract birth year
    dob = basics.get("dob", "")
    birth_year = None
    if dob:
        try:
            birth_year = int(str(dob).strip()[:4])
        except (ValueError, IndexError):
            pass

    if not birth_year:
        return {
            "person_id": person_id,
            "decades": [],
            "periods": [],
            "birth_year": None,
            "error": "no_dob",
        }

    # Build periods (prefer spine if available, else scaffold)
    periods = build_scaffold_periods(birth_year)

    # Load all three lanes
    seed = load_historical_seed()
    lane_a = filter_world_events(seed, birth_year)
    lane_b = project_personal_anchors(
        basics, questionnaire, promoted_rows,
        narrator_display_name=narrator_display_name,
    )
    lane_c = build_band_ghosts(birth_year, periods, lane_b)

    # Merge all items
    all_items = lane_a + lane_b + lane_c

    # Group into decades
    decades = group_by_decade(all_items, periods)

    return {
        "person_id": person_id,
        "birth_year": birth_year,
        "periods": [
            {
                "label": p["label"],
                "start_year": p["start_year"],
                "end_year": p.get("end_year"),
            }
            for p in periods
        ],
        "decades": decades,
        "lane_counts": {
            "world": len(lane_a),
            "personal": len(lane_b),
            "ghost": len(lane_c),
        },
    }


# ─── ENDPOINT ─────────────────────────────────────────────────────

@router.get("/chronology-accordion")
def api_chronology_accordion(
    person_id: str = Query(..., description="Narrator person_id"),
):
    """Read-only chronology accordion payload.

    Merges world events, personal anchors, and ghost prompts into
    a decade-grouped structure for the left-side accordion UI.
    """
    person = get_person(person_id)
    if not person:
        raise HTTPException(status_code=404, detail="person not found")

    ensure_profile(person_id)
    profile_row = get_profile(person_id)
    legacy_profile = profile_row.get("profile_json", {}) if profile_row else {}

    # Flag-gated promoted-truth profile build.  build_profile_from_promoted
    # returns {basics, kinship, pets}; legacy_profile also has that shape.
    profile_obj: Dict[str, Any] = legacy_profile or {}
    if truth_v2_enabled("profile"):
        try:
            profile_obj = db.build_profile_from_promoted(person_id)
        except Exception as exc:
            logger.warning(
                "chronology: build_profile_from_promoted failed for %s: %s",
                person_id, exc,
            )
            profile_obj = legacy_profile or {}

    promoted_rows = ft_list_promoted(person_id, limit=10_000)
    questionnaire = get_questionnaire(person_id)

    # Pull the narrator's display name for self-filtering promoted rows.
    narrator_name = (person.get("display_name") or "").strip()

    payload = build_chronology_accordion_payload(
        person_id=person_id,
        profile=profile_obj,
        questionnaire=questionnaire,
        promoted_rows=promoted_rows,
        narrator_display_name=narrator_name,
    )

    return payload
