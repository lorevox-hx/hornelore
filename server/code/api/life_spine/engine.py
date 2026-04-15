"""WO-LIFE-SPINE-01 — Life-spine derivation engine.

Generic dispatcher: takes a DOB and optional facts, runs each registered
era catalog, applies any confirmed-event overrides, returns a flat list
of ChronologyItem-shaped dicts ready for accordion consumption.

Adding a new era catalog (future WO-LIFE-SPINE-02 etc.):
    1. Create life_spine/<era>.py with a derive_<era>_spine(dob) function
       returning a list of items in the same shape as school.derive_school_spine.
    2. Register it in CATALOGS below.
    3. Done — the accordion picks it up automatically.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List

from .adolescence import derive_adolescence_spine
from .early_adulthood import derive_early_adulthood_spine
from .overrides import apply_overrides
from .school import derive_school_spine, school_phase_for_year


# Registered era catalogs. Each callable takes a DOB (str | date) and
# returns List[ChronologyItem]. Add new eras here as catalogs land.
CATALOGS: Dict[str, Callable[..., List[Dict[str, Any]]]] = {
    "school_years": derive_school_spine,
    "adolescence": derive_adolescence_spine,
    "early_adulthood": derive_early_adulthood_spine,
}


def derive_life_spine(
    dob: Any,
    confirmed_events: List[Dict[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    """Build the full life spine for a narrator.

    Args:
        dob: ISO date string ("YYYY-MM-DD") or date/datetime object. May be
             empty/None — returns [] in that case (no DOB → no spine).
        confirmed_events: optional list of {event_kind, year, source?} dicts
             representing facts already promoted as truth (or confirmed by
             the narrator). Each one anchors a matching spine item and
             propagates any offset to downstream UNCONFIRMED estimates only.

    Returns:
        A flat list of ChronologyItem-shaped dicts. Each carries:
            year         — calendar year
            label        — display string (suffixed "(estimated)")
            lane         — "personal"
            event_kind   — stable identifier (e.g. "school_kindergarten")
            dedup_key    — single-occurrence key for accordion dedup
            source       — "derived" (or "promoted_truth" after override)
            confidence   — "estimated" (or "confirmed" after override)
    """
    if not dob:
        return []

    items: List[Dict[str, Any]] = []
    for catalog_name, catalog_fn in CATALOGS.items():
        try:
            items.extend(catalog_fn(dob))
        except Exception:
            # A broken catalog must not poison the whole spine. Skip it
            # silently; future WO can wire structured logging here.
            continue

    items = apply_overrides(items, confirmed_events)
    return items


# Re-export for callers that want the phase-for-year helper without
# importing school.py directly. Convenient for the prompt composer.
__all__ = ["derive_life_spine", "school_phase_for_year"]
