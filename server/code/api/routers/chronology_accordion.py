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
# Projection whitelist — only these promoted-truth fields become anchors.

_ANCHOR_FIELDS = {
    "date_of_birth":       "Born",
    "place_of_birth":      "Birthplace",
    "date_of_marriage":    "Married",
    "place_of_marriage":   "Wedding",
    "date_of_graduation":  "Graduated",
    "date_of_enlistment":  "Enlisted",
    "date_of_retirement":  "Retired",
    "date_of_immigration": "Immigrated",
    "date_of_move":        "Moved",
    "first_job":           "First job",
    "first_child_born":    "First child born",
}


def _extract_year(value: str) -> Optional[int]:
    """Try to extract a 4-digit year from a value string."""
    if not value:
        return None
    # Try first 4 chars
    candidate = str(value).strip()[:10]
    for part in candidate.replace("-", "/").split("/"):
        part = part.strip()
        if len(part) == 4 and part.isdigit():
            yr = int(part)
            if 1850 <= yr <= 2100:
                return yr
    return None


def project_personal_anchors(
    profile: Dict[str, Any],
    questionnaire: Dict[str, Any],
    promoted_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Extract verified personal anchors from promoted truth, profile, and questionnaire.

    Only uses fields in _ANCHOR_FIELDS whitelist.  Never invents data.
    Returns ChronologyItem-shaped dicts with lane='personal'.
    """
    items = []
    seen_fields = set()

    # 1. Promoted truth rows (highest authority)
    for row in promoted_rows:
        field = row.get("field", "")
        if field not in _ANCHOR_FIELDS:
            continue
        if field in seen_fields:
            continue
        value = row.get("value", "")
        yr = _extract_year(value)
        if yr is None:
            continue
        seen_fields.add(field)
        items.append({
            "year": yr,
            "label": f"{_ANCHOR_FIELDS[field]}: {value}",
            "lane": "personal",
            "field": field,
            "source": "promoted_truth",
        })

    # 2. Profile basics (fallback for fields not yet in promoted truth)
    basics = profile.get("basics", {}) if profile else {}
    profile_field_map = {
        "dob": "date_of_birth",
        "pob": "place_of_birth",
    }
    for profile_key, field in profile_field_map.items():
        if field in seen_fields or field not in _ANCHOR_FIELDS:
            continue
        value = basics.get(profile_key, "")
        yr = _extract_year(str(value))
        if yr is None:
            continue
        seen_fields.add(field)
        items.append({
            "year": yr,
            "label": f"{_ANCHOR_FIELDS[field]}: {value}",
            "lane": "personal",
            "field": field,
            "source": "profile",
        })

    # 3. Questionnaire (fallback for date-bearing answers)
    q_data = questionnaire.get("questionnaire", {}) if questionnaire else {}
    # Walk flat questionnaire keys looking for whitelisted field patterns
    for q_key, q_val in q_data.items():
        if not isinstance(q_val, str):
            continue
        # Map questionnaire keys to anchor fields
        for anchor_field in _ANCHOR_FIELDS:
            if anchor_field in seen_fields:
                continue
            if anchor_field.replace("date_of_", "") in q_key.lower():
                yr = _extract_year(q_val)
                if yr is not None:
                    seen_fields.add(anchor_field)
                    items.append({
                        "year": yr,
                        "label": f"{_ANCHOR_FIELDS[anchor_field]}: {q_val}",
                        "lane": "personal",
                        "field": anchor_field,
                        "source": "questionnaire",
                    })
                    break

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
) -> Dict[str, Any]:
    """Build the full chronology accordion payload.

    Returns the complete JSON response shape for the frontend.
    """
    basics = (profile.get("profile") or profile.get("basics") or {})
    if "basics" in basics:
        basics = basics["basics"]

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
    lane_b = project_personal_anchors(basics, questionnaire, promoted_rows)
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
    profile_obj = profile_row.get("profile_json", {}) if profile_row else {}

    # Flag-gated promoted-truth profile build
    if truth_v2_enabled("profile"):
        try:
            profile_obj = db.build_profile_from_promoted(person_id)
        except Exception as exc:
            logger.warning(
                "chronology: build_profile_from_promoted failed for %s: %s",
                person_id, exc,
            )

    promoted_rows = ft_list_promoted(person_id, limit=10_000)
    questionnaire = get_questionnaire(person_id)

    payload = build_chronology_accordion_payload(
        person_id=person_id,
        profile={"basics": profile_obj} if "basics" not in profile_obj else profile_obj,
        questionnaire=questionnaire,
        promoted_rows=promoted_rows,
    )

    return payload
