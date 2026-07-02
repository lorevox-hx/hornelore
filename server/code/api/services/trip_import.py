"""Trip itinerary import — JSON fixture shape + CSV.

WO-TRIP-IMPORT-AND-CLUSTER-01 Phase 1 (2026-07-02).

Two input shapes:

1. Itinerary JSON — the shape banked at
   ``fixtures/trips/trip_2019_france_italy_fixture.json``:
   ``{trip_id?, title, source_document?, date_range{start,end},
   regions:[{region_id?, title, date_range{start,end}, base_address?,
   stops:[<str> | <stop dict>]}], themes?:[{title, tag, description?}]}``
   String stops become ``stop_type='sight'`` rows; dict stops may carry
   ``stop_type / date_start / date_end / latitude / longitude / title /
   notes / thematic_tags / day_trips:[...]`` (day_trips nest via
   ``parent_trip_stop_id``).

2. CSV — one row per stop:
   ``region,location,stop_type,date_start,date_end,lat,lng,parent,title,notes,themes``
   ``region`` groups rows in first-seen order; ``parent`` names an
   earlier ``location`` in the same region to nest under; ``themes`` is
   ``;``-separated tags.

Pure stdlib. Writes through trip_repository only.
"""
from __future__ import annotations

import csv
import io
import re
from typing import Any, Dict, List, Optional

from . import trip_repository as repo


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return s or "item"


def _import_stop(
    trip_id: str,
    region_id: str,
    stop: Any,
    ord_: int,
    parent_id: Optional[str] = None,
) -> str:
    if isinstance(stop, str):
        return repo.stop_create(
            trip_id=trip_id,
            trip_region_id=region_id,
            location_name=stop,
            stop_type="sight",
            ord_=ord_,
            parent_trip_stop_id=parent_id,
        )
    if not isinstance(stop, dict):
        raise ValueError(f"stop must be str or dict, got {type(stop)!r}")
    location = stop.get("location_name") or stop.get("location") or stop.get("title")
    if not location:
        raise ValueError("stop dict needs location_name/location/title")
    sid = repo.stop_create(
        trip_id=trip_id,
        trip_region_id=region_id,
        location_name=str(location),
        stop_type=str(stop.get("stop_type") or "sight"),
        ord_=ord_,
        parent_trip_stop_id=parent_id,
        date_start=stop.get("date_start"),
        date_end=stop.get("date_end"),
        latitude=stop.get("latitude"),
        longitude=stop.get("longitude"),
        title=stop.get("title"),
        notes=stop.get("notes"),
        thematic_tags=list(stop.get("thematic_tags") or []),
    )
    for i, child in enumerate(stop.get("day_trips") or []):
        _import_stop(trip_id, region_id, child, i, parent_id=sid)
    return sid


def import_itinerary(person_id: str, itinerary: Dict[str, Any]) -> str:
    """Import an itinerary JSON document. Returns the trip id."""
    if not isinstance(itinerary, dict):
        raise ValueError("itinerary must be a dict")
    title = itinerary.get("title")
    if not title:
        raise ValueError("itinerary needs a title")
    date_range = itinerary.get("date_range") or {}
    trip_id = repo.trip_create(
        person_id=person_id,
        title=str(title),
        start_date=date_range.get("start"),
        end_date=date_range.get("end"),
        summary=itinerary.get("summary"),
        source_document=itinerary.get("source_document"),
        meta={"itinerary_trip_id": itinerary.get("trip_id")},
    )
    for r_ord, region in enumerate(itinerary.get("regions") or []):
        r_dates = region.get("date_range") or {}
        region_id = repo.region_create(
            trip_id=trip_id,
            title=str(region.get("title") or region.get("region_id") or f"Region {r_ord + 1}"),
            ord_=r_ord,
            country_or_area=region.get("country_or_area"),
            start_date=r_dates.get("start"),
            end_date=r_dates.get("end"),
            summary=region.get("summary"),
            base_address=region.get("base_address"),
            themes=list(region.get("themes") or []),
        )
        for s_ord, stop in enumerate(region.get("stops") or []):
            _import_stop(trip_id, region_id, stop, s_ord)
    for t_ord, theme in enumerate(itinerary.get("themes") or []):
        if isinstance(theme, str):
            repo.theme_create(trip_id, title=theme, tag=_slug(theme), ord_=t_ord)
        elif isinstance(theme, dict) and theme.get("title"):
            repo.theme_create(
                trip_id,
                title=str(theme["title"]),
                tag=str(theme.get("tag") or _slug(theme["title"])),
                ord_=t_ord,
                description=theme.get("description"),
            )
    return trip_id


_CSV_COLUMNS = (
    "region", "location", "stop_type", "date_start", "date_end",
    "lat", "lng", "parent", "title", "notes", "themes",
)


def import_csv(
    person_id: str,
    csv_text: str,
    title: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    summary: Optional[str] = None,
) -> str:
    """Import a CSV itinerary (one row per stop). Returns the trip id."""
    reader = csv.DictReader(io.StringIO(csv_text or ""))
    if not reader.fieldnames or "region" not in reader.fieldnames \
            or "location" not in reader.fieldnames:
        raise ValueError(
            "CSV needs at least 'region' and 'location' columns "
            f"(full set: {', '.join(_CSV_COLUMNS)})"
        )
    trip_id = repo.trip_create(
        person_id=person_id,
        title=title,
        start_date=start_date,
        end_date=end_date,
        summary=summary,
        source_document="csv_import",
    )
    region_ids: Dict[str, str] = {}
    region_ord = 0
    stop_ids_by_region: Dict[str, Dict[str, str]] = {}
    stop_ord: Dict[str, int] = {}
    for row in reader:
        region_name = (row.get("region") or "").strip()
        location = (row.get("location") or "").strip()
        if not region_name or not location:
            continue
        if region_name not in region_ids:
            region_ids[region_name] = repo.region_create(
                trip_id=trip_id, title=region_name, ord_=region_ord,
            )
            region_ord += 1
            stop_ids_by_region[region_name] = {}
            stop_ord[region_name] = 0
        region_id = region_ids[region_name]
        parent_name = (row.get("parent") or "").strip()
        parent_id = stop_ids_by_region[region_name].get(parent_name) or None

        def _f(key: str) -> Optional[float]:
            v = (row.get(key) or "").strip()
            try:
                return float(v) if v else None
            except ValueError:
                return None

        themes_raw = (row.get("themes") or "").strip()
        tags = [t.strip() for t in themes_raw.split(";") if t.strip()]
        sid = repo.stop_create(
            trip_id=trip_id,
            trip_region_id=region_id,
            location_name=location,
            stop_type=(row.get("stop_type") or "sight").strip() or "sight",
            ord_=stop_ord[region_name],
            parent_trip_stop_id=parent_id,
            date_start=(row.get("date_start") or "").strip() or None,
            date_end=(row.get("date_end") or "").strip() or None,
            latitude=_f("lat"),
            longitude=_f("lng"),
            title=(row.get("title") or "").strip() or None,
            notes=(row.get("notes") or "").strip() or None,
            thematic_tags=tags,
        )
        stop_ids_by_region[region_name][location] = sid
        stop_ord[region_name] += 1
    return trip_id
