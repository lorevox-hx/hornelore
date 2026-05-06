"""
Lorevox Canonical Life Spine — backend mirror of ui/js/lv-eras.js.

Single source of truth for life-period taxonomy on the server side.
Imported by:
  - server/code/api/prompt_composer.py     Lori's era support cards
  - server/code/api/routers/chronology_accordion.py    Era anchors
  - server/code/api/routers/extract.py     Compatibility boundary
  - server/code/api/life_spine/engine.py   Dispatch keyed off era_ids

Architecture:
  7 buckets total — 6 historical eras + Today (separate current-life).

Field reference (mirrors ui/js/lv-eras.js exactly; keep these in sync):
  era_id      stable internal key (passed through runtime71, log lines,
              prompts, state.session.currentEra, etc.) — NEVER prefixed
              with "era:" or any other namespace at canonical boundary
  label       warm display string (heading shown in UI)
  memoirTitle literary subtitle (shown UNDER the warm heading in
              Peek at Memoir, e.g. "Earliest Years / The Legend Begins")
  ageStart    inclusive lower bound for historical-era lookup
  ageEnd      inclusive upper bound; None = open-ended (Later Years)
  loriFocus   user-facing description text for Life Map click-confirm
              and Lori's prompts
  legacyKeys  old v7.1 era names retained as aliases only

Today has ageStart=None, ageEnd=None and is NEVER returned by
era_id_from_age() — current-life is selected explicitly, not derived.

Phase 1 design choice: this is a list[dict] mirror, not a database
table. No DB migration. Era IDs are stable strings passed through
runtime71. The frontend mirror at ui/js/lv-eras.js holds the same
data — keep them in sync. Phase 2 may promote backend to canonical
(with an endpoint and frontend fetch) if server-side era reasoning
grows beyond what this mirror supports.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Union


LV_ERAS: List[Dict[str, Any]] = [
    {
        "era_id":      "earliest_years",
        "legacyKeys":  ["early_childhood"],
        "label":       "Earliest Years",
        "memoirTitle": "The Legend Begins",
        "ageStart":    0,
        "ageEnd":      5,
        "loriFocus":   "birth, first home, parents and siblings, the places that shaped early childhood",
    },
    {
        "era_id":      "early_school_years",
        "legacyKeys":  ["school_years"],
        "label":       "Early School Years",
        "memoirTitle": "Formative Years",
        "ageStart":    6,
        "ageEnd":      12,
        "loriFocus":   "elementary school, teachers, neighborhood, family routines, early friendships",
    },
    {
        "era_id":      "adolescence",
        "legacyKeys":  ["adolescence"],
        "label":       "Adolescence",
        "memoirTitle": "Adolescence",
        "ageStart":    13,
        "ageEnd":      17,
        "loriFocus":   "teen years, identity, friends, high school, growing independence",
    },
    {
        "era_id":      "coming_of_age",
        "legacyKeys":  ["early_adulthood"],
        "label":       "Coming of Age",
        "memoirTitle": "Crossroads",
        "ageStart":    18,
        "ageEnd":      30,
        "loriFocus":   "leaving home, first work, marriage, moves, finding your adult self",
    },
    {
        "era_id":      "building_years",
        "legacyKeys":  ["midlife"],
        "label":       "Building Years",
        "memoirTitle": "Peaks & Valleys",
        "ageStart":    31,
        "ageEnd":      59,
        "loriFocus":   "work, family, responsibility, caregiving, community",
    },
    {
        "era_id":      "later_years",
        "legacyKeys":  ["later_life"],
        "label":       "Later Years",
        "memoirTitle": "The Compass",
        "ageStart":    60,
        "ageEnd":      None,
        "loriFocus":   "retirement, reflection, health, family, lessons, and what matters most now",
    },
    {
        "era_id":      "today",
        "legacyKeys":  ["current_horizon"],
        "label":       "Today",
        "memoirTitle": "Current Horizon",
        "ageStart":    None,
        "ageEnd":      None,
        "loriFocus":   "current life, routines, the people you see most, hopes, unfinished stories",
    },
]


# Build lookup indexes once at import.
_BY_ID:     Dict[str, Dict[str, Any]] = {e["era_id"]: e for e in LV_ERAS}
_BY_LEGACY: Dict[str, Dict[str, Any]] = {}
for _e in LV_ERAS:
    for _legacy in _e.get("legacyKeys") or []:
        _BY_LEGACY[_legacy] = _e


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(s: str) -> str:
    """Lowercase + collapse non-alphanum runs to single underscore."""
    return _SLUG_RE.sub("_", s.lower()).strip("_")


def legacy_key_to_era_id(value: Optional[str]) -> Optional[str]:
    """Normalize any era identifier to canonical era_id. Defensive against
    every transitional form we know about. Resolution order:

    1. trim
    2. strip leading ``"era:"`` prefix if present
    3. exact canonical era_id match  (e.g. ``"earliest_years"``)
    4. legacy v7.1 key match         (e.g. ``"early_childhood"``)
    5. warm label match              (e.g. ``"Earliest Years"``, case-insensitive)
    6. memoir title match            (e.g. ``"The Legend Begins"``, case-insensitive)
    7. normalized slug match         (e.g. ``"Earliest-Years"`` → ``"earliest_years"``)
    8. return cleaned input unchanged (forwards-compat; callers wanting
       strict validation should check ``result in _BY_ID``)

    Returns None for None / empty input.
    """
    if value is None:
        return None
    raw = str(value).strip()
    if raw == "":
        return None
    # Step 2: strip transitional "era:" prefix (case-insensitive — handles
    # ERA:Today, Era:Earliest Years, etc.).
    if raw.lower().startswith("era:"):
        raw = raw[4:].strip()
    if raw == "":
        return None
    # Step 3: canonical era_id direct.
    if raw in _BY_ID:
        return _BY_ID[raw]["era_id"]
    # Step 4: legacy v7.1 key.
    if raw in _BY_LEGACY:
        return _BY_LEGACY[raw]["era_id"]
    # Step 5: warm label (case-insensitive).
    raw_lower = raw.lower()
    for e in LV_ERAS:
        if e["label"].lower() == raw_lower:
            return e["era_id"]
    # Step 6: memoir title (case-insensitive).
    for e in LV_ERAS:
        mt = e.get("memoirTitle") or ""
        if mt and mt.lower() == raw_lower:
            return e["era_id"]
    # Step 7: slug match (handles "Earliest-Years", "EARLIEST YEARS", etc.).
    slug = _slugify(raw)
    if slug:
        if slug in _BY_ID:
            return _BY_ID[slug]["era_id"]
        if slug in _BY_LEGACY:
            return _BY_LEGACY[slug]["era_id"]
    # Step 8: forwards-compat passthrough.
    return raw


def era_id_to_warm_label(era_id: Optional[str]) -> str:
    """Return the user-facing warm label for an era_id (e.g. 'Earliest Years')."""
    canonical = legacy_key_to_era_id(era_id)
    e = _BY_ID.get(canonical) if canonical else None
    return e["label"] if e else (str(era_id) if era_id else "")


def era_id_to_memoir_title(era_id: Optional[str]) -> str:
    """Return the memoir literary subtitle for an era_id (e.g. 'The Legend Begins')."""
    canonical = legacy_key_to_era_id(era_id)
    e = _BY_ID.get(canonical) if canonical else None
    return e["memoirTitle"] if e else ""


def era_id_to_lori_focus(era_id: Optional[str]) -> str:
    """Return the Lori-prompt focus description for an era_id."""
    canonical = legacy_key_to_era_id(era_id)
    e = _BY_ID.get(canonical) if canonical else None
    return e["loriFocus"] if e else ""


# Sentence-shaped warm phrases for use INSIDE Lori's narrator-facing
# prose — fit naturally in templates like "Last time we were in {phrase}…"
# Distinct from era_id_to_warm_label which returns the title-cased label
# ("Earliest Years") suitable for headings, NOT inside a sentence.
#
# Used by WO-BUG-LORI-SWITCH-FRESH-GREETING-01 Phase 2 continuation
# paraphrase composer (Slice 2a — Tier C era-only template).
_LV_ERA_CONTINUATION_PHRASES: Dict[str, str] = {
    "earliest_years":     "the years before you started school",
    "early_school_years": "your early school years",
    "adolescence":        "your adolescence",
    "coming_of_age":      "the years when you were coming of age",
    "building_years":     "your building years",
    "later_years":        "the later years",
    "today":              "today",
}


def era_id_to_continuation_phrase(era_id: Optional[str]) -> Optional[str]:
    """Return a sentence-shaped warm phrase for an era_id, suitable for
    inclusion inside Lori's narrator-facing prose. Returns None when
    era_id is unknown so callers can degrade gracefully (e.g. fall back
    to a bare "Welcome back, {name}." template).

    Examples:
      era_id_to_continuation_phrase("earliest_years") → "the years before you started school"
      era_id_to_continuation_phrase("building_years") → "your building years"
      era_id_to_continuation_phrase("today")          → "today"
      era_id_to_continuation_phrase(None)             → None
      era_id_to_continuation_phrase("unknown_era")    → None
    """
    canonical = legacy_key_to_era_id(era_id)
    if canonical is None:
        return None
    return _LV_ERA_CONTINUATION_PHRASES.get(canonical)


def era_id_from_age(age: Union[int, float, str, None]) -> Optional[str]:
    """Map age in years to a canonical era_id.

    IMPORTANT: never returns ``"today"`` — Today is a current-life bucket
    selected explicitly by the narrator/operator, not derived from
    birth-year math. Out-of-range / negative ages return None.
    """
    if age is None:
        return None
    try:
        n = float(age)
    except (TypeError, ValueError):
        return None
    if n != n:    # NaN check
        return None
    for e in LV_ERAS:
        if e["era_id"] == "today":
            continue                                 # never derive today from age
        if e["ageStart"] is None:
            continue                                 # defensive: skip non-historical entries
        if e["ageEnd"] is None:
            if n >= e["ageStart"]:
                return e["era_id"]
        else:
            if e["ageStart"] <= n <= e["ageEnd"]:
                return e["era_id"]
    return None


_YEAR_RE = re.compile(r"\b(?:18|19|20)\d{2}\b")


def era_id_from_year(
    year: Union[int, float, str, None],
    dob: Union[str, None],
) -> Optional[str]:
    """Map a calendar year + DOB to a canonical era_id.

    Year is the year being asked about; dob is the narrator's birth date
    (any string with a YYYY anywhere in it). Returns None if either is
    missing or non-parseable. Like era_id_from_age, never returns today.
    """
    birth_year: Optional[int] = None
    if dob is not None:
        m = _YEAR_RE.search(str(dob))
        if m:
            birth_year = int(m.group(0))
    if not birth_year:
        return None
    try:
        year_n = float(year)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return era_id_from_age(year_n - birth_year)


def all_eras() -> List[Dict[str, Any]]:
    """Return a shallow copy of LV_ERAS for safe iteration."""
    return list(LV_ERAS)


__all__ = [
    "LV_ERAS",
    "legacy_key_to_era_id",
    "era_id_to_warm_label",
    "era_id_to_memoir_title",
    "era_id_to_lori_focus",
    "era_id_to_continuation_phrase",
    "era_id_from_age",
    "era_id_from_year",
    "all_eras",
]
