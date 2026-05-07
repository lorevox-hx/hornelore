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


# WO-ML-03A (Phase 3 of the multilingual project, 2026-05-07) —
# locale-aware era warm labels + memoir titles. Default locale 'en'
# falls through to the canonical LV_ERAS entries above, preserving
# byte-stable behavior for every existing caller. Other locales are
# additive translation tables consulted ONLY when the caller passes
# locale=...
#
# Initial locale support: 'en' (canonical, defaults), 'es' (Spanish).
# es translations are the agent's best-effort first pass; final
# wording for narrator-facing surfaces (Life Map era buttons, memoir
# headings, Lori's continuation greetings) should be reviewed by a
# native Spanish speaker before production launch — same posture as
# the Phase 4 safety patterns. Captured here as a TODO so future
# contributors see why this isn't already locked: see the
# multilingual project plan §Phase 3 + the cultural-context cases at
# data/evals/sentence_diagram_cultural_context_cases_sd044_sd065.json.
#
# Adding a new locale: drop a new key into each of the three dicts
# below (LABELS, MEMOIR_TITLES, CONTINUATION_PHRASES) covering all
# seven era_ids. The lookup helpers fall back to 'en' on any missing
# locale-or-era_id entry, so a partial translation degrades to
# English rather than crashing.
_LV_ERA_LABELS_BY_LOCALE: Dict[str, Dict[str, str]] = {
    "en": {
        "earliest_years":     "Earliest Years",
        "early_school_years": "Early School Years",
        "adolescence":        "Adolescence",
        "coming_of_age":      "Coming of Age",
        "building_years":     "Building Years",
        "later_years":        "Later Years",
        "today":              "Today",
    },
    "es": {
        # Best-effort first pass — pending native review.
        "earliest_years":     "Primeros Años",
        "early_school_years": "Primeros Años Escolares",
        "adolescence":        "Adolescencia",
        "coming_of_age":      "Mayoría de Edad",
        "building_years":     "Años de Construcción",
        "later_years":        "Años Posteriores",
        "today":              "Hoy",
    },
}

_LV_ERA_MEMOIR_TITLES_BY_LOCALE: Dict[str, Dict[str, str]] = {
    "en": {
        "earliest_years":     "The Legend Begins",
        "early_school_years": "Formative Years",
        "adolescence":        "Adolescence",
        "coming_of_age":      "Crossroads",
        "building_years":     "Peaks & Valleys",
        "later_years":        "The Compass",
        "today":              "Current Horizon",
    },
    "es": {
        # Best-effort first pass — pending native review.
        "earliest_years":     "Comienza la Leyenda",
        "early_school_years": "Años Formativos",
        "adolescence":        "Adolescencia",
        "coming_of_age":      "Encrucijada",
        "building_years":     "Cumbres y Valles",
        "later_years":        "La Brújula",
        "today":              "Horizonte Actual",
    },
}


def _resolve_locale(locale: Optional[str]) -> str:
    """Normalize a locale tag for the BY_LOCALE lookup tables.
    Accepts 'en', 'en-US', 'es', 'es-MX', 'ES', None, '' — collapses to
    a 2-letter language code. Falls back to 'en' on unknown or
    unsupported locales so callers don't have to special-case.
    """
    if not locale:
        return "en"
    s = str(locale).strip().lower()
    if not s:
        return "en"
    if "-" in s:
        s = s.split("-", 1)[0]
    if s in _LV_ERA_LABELS_BY_LOCALE:
        return s
    return "en"


def era_id_to_warm_label(era_id: Optional[str], locale: Optional[str] = None) -> str:
    """Return the user-facing warm label for an era_id (e.g. 'Earliest Years').

    locale (optional): ISO-639-1 language code ('en' default, 'es' supported).
    Falls back to English on unknown locales or untranslated era_ids so
    legacy callers (no locale param) preserve byte-stable English output.
    """
    canonical = legacy_key_to_era_id(era_id)
    if not canonical:
        return str(era_id) if era_id else ""
    loc = _resolve_locale(locale)
    table = _LV_ERA_LABELS_BY_LOCALE.get(loc) or _LV_ERA_LABELS_BY_LOCALE["en"]
    if canonical in table:
        return table[canonical]
    # Locale-specific translation missing for this era_id — fall back to
    # the canonical English label rather than echoing the raw era_id.
    return _LV_ERA_LABELS_BY_LOCALE["en"].get(canonical) or (
        _BY_ID[canonical]["label"] if canonical in _BY_ID else str(era_id)
    )


def era_id_to_memoir_title(era_id: Optional[str], locale: Optional[str] = None) -> str:
    """Return the memoir literary subtitle for an era_id (e.g. 'The Legend Begins').

    locale (optional): see era_id_to_warm_label for behavior.
    """
    canonical = legacy_key_to_era_id(era_id)
    if not canonical:
        return ""
    loc = _resolve_locale(locale)
    table = _LV_ERA_MEMOIR_TITLES_BY_LOCALE.get(loc) or _LV_ERA_MEMOIR_TITLES_BY_LOCALE["en"]
    if canonical in table:
        return table[canonical]
    return _LV_ERA_MEMOIR_TITLES_BY_LOCALE["en"].get(canonical) or (
        _BY_ID[canonical]["memoirTitle"] if canonical in _BY_ID else ""
    )


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

# WO-ML-03A (Phase 3, 2026-05-07) — locale-aware continuation phrases.
# Same posture as _LV_ERA_LABELS_BY_LOCALE above: 'en' is canonical
# (mirrors _LV_ERA_CONTINUATION_PHRASES exactly so legacy code without
# locale param is byte-stable), 'es' is best-effort first pass pending
# native review. Phrases are designed to fit naturally inside Lori's
# narrator-facing prose, e.g. "La última vez estábamos en {phrase}…"
# — preserve that grammatical fit when reviewing translations.
_LV_ERA_CONTINUATION_PHRASES_BY_LOCALE: Dict[str, Dict[str, str]] = {
    "en": dict(_LV_ERA_CONTINUATION_PHRASES),
    "es": {
        # Best-effort first pass — pending native review.
        # Designed to slot into "La última vez estábamos en {phrase}…"
        # except 'today' which uses present-tense framing.
        "earliest_years":     "los años antes de que empezaras la escuela",
        "early_school_years": "tus primeros años escolares",
        "adolescence":        "tu adolescencia",
        "coming_of_age":      "los años en los que estabas alcanzando la mayoría de edad",
        "building_years":     "tus años de construcción",
        "later_years":        "los años posteriores",
        "today":              "hoy",
    },
}


def era_id_to_continuation_phrase(
    era_id: Optional[str],
    locale: Optional[str] = None,
) -> Optional[str]:
    """Return a sentence-shaped warm phrase for an era_id, suitable for
    inclusion inside Lori's narrator-facing prose. Returns None when
    era_id is unknown so callers can degrade gracefully (e.g. fall back
    to a bare "Welcome back, {name}." template).

    locale (optional): ISO-639-1 language code ('en' default, 'es'
    supported). Falls back to English on unknown locales or untranslated
    era_ids — legacy callers without locale param are byte-stable.

    Examples (en, default):
      era_id_to_continuation_phrase("earliest_years") → "the years before you started school"
      era_id_to_continuation_phrase("building_years") → "your building years"
      era_id_to_continuation_phrase("today")          → "today"
      era_id_to_continuation_phrase(None)             → None
      era_id_to_continuation_phrase("unknown_era")    → None

    Examples (es):
      era_id_to_continuation_phrase("earliest_years", locale="es")
        → "los años antes de que empezaras la escuela"
      era_id_to_continuation_phrase("today", locale="es") → "hoy"
    """
    canonical = legacy_key_to_era_id(era_id)
    if canonical is None:
        return None
    loc = _resolve_locale(locale)
    table = _LV_ERA_CONTINUATION_PHRASES_BY_LOCALE.get(loc) or _LV_ERA_CONTINUATION_PHRASES_BY_LOCALE["en"]
    phrase = table.get(canonical)
    if phrase is not None:
        return phrase
    # Locale-specific translation missing — fall back to English rather
    # than returning None (None means era_id unknown, which is a
    # different signal callers may handle differently).
    return _LV_ERA_CONTINUATION_PHRASES_BY_LOCALE["en"].get(canonical)


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
