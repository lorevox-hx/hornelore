"""Trip repository — pure-sqlite accessors for the trip tables.

WO-TRIP-IMPORT-AND-CLUSTER-01 Phase 1 (2026-07-02). Implements the
hierarchical schema locked in WO-TRIP-MEMOIR-01:

    trips -> trip_regions -> trip_stops (nested) -> trip_photo_links
    + trip_themes / trip_location_notes / trip_bio_suggestions
    + trip_story_links

Design rules:
- Pure stdlib (sqlite3 + json + uuid + datetime). No imports from
  extract / prompt_composer / chat_ws / llm layers (LAW 3 posture —
  the trip lane must never destabilize the interview lane).
- Connects through ``api.db.DB_PATH`` resolved AT CALL TIME so unit
  tests can patch ``db.DB_PATH`` to a temp file (same pattern as
  story_preservation tests).
- All writes commit-or-rollback per call; no long-lived connections.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _connect() -> sqlite3.Connection:
    from .. import db as _db  # late import so tests can patch DB_PATH
    con = sqlite3.connect(str(_db.DB_PATH))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON;")
    con.execute("PRAGMA busy_timeout = 5000;")
    return con


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id() -> str:
    return str(uuid.uuid4())


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    for key in ("meta_json", "theme_json", "thematic_tags_json"):
        if key in d and isinstance(d.get(key), str):
            try:
                d[key] = json.loads(d[key])
            except Exception:
                pass
    return d


# ── Trip CRUD ─────────────────────────────────────────────────────────────


def trip_create(
    person_id: str,
    title: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    summary: Optional[str] = None,
    source_document: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
    trip_id: Optional[str] = None,
) -> str:
    tid = trip_id or _new_id()
    con = _connect()
    try:
        con.execute(
            """INSERT INTO trips
               (id, person_id, title, start_date, end_date, summary,
                status, source_document, created_at, updated_at, meta_json)
               VALUES (?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?)""",
            (
                tid, person_id, title, start_date, end_date, summary,
                source_document, _now(), _now(),
                json.dumps(meta or {}, ensure_ascii=False),
            ),
        )
        con.commit()
        return tid
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def trip_list(person_id: Optional[str] = None) -> List[Dict[str, Any]]:
    con = _connect()
    try:
        if person_id:
            rows = con.execute(
                "SELECT * FROM trips WHERE person_id = ? "
                "ORDER BY start_date DESC, created_at DESC",
                (person_id,),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM trips ORDER BY start_date DESC, created_at DESC"
            ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        con.close()


def trip_get(trip_id: str) -> Optional[Dict[str, Any]]:
    con = _connect()
    try:
        row = con.execute(
            "SELECT * FROM trips WHERE id = ?", (trip_id,)
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        con.close()


# ── Regions / stops / themes ──────────────────────────────────────────────


def region_create(
    trip_id: str,
    title: str,
    ord_: int = 0,
    country_or_area: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    summary: Optional[str] = None,
    base_address: Optional[str] = None,
    themes: Optional[List[str]] = None,
    region_id: Optional[str] = None,
) -> str:
    rid = region_id or _new_id()
    con = _connect()
    try:
        con.execute(
            """INSERT INTO trip_regions
               (id, trip_id, ord, title, country_or_area, start_date,
                end_date, summary, base_address, theme_json,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rid, trip_id, ord_, title, country_or_area, start_date,
                end_date, summary, base_address,
                json.dumps(themes or [], ensure_ascii=False),
                _now(), _now(),
            ),
        )
        con.commit()
        return rid
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def stop_create(
    trip_id: str,
    trip_region_id: str,
    location_name: str,
    stop_type: str = "sight",
    ord_: int = 0,
    parent_trip_stop_id: Optional[str] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    title: Optional[str] = None,
    notes: Optional[str] = None,
    thematic_tags: Optional[List[str]] = None,
    stop_id: Optional[str] = None,
) -> str:
    sid = stop_id or _new_id()
    con = _connect()
    try:
        con.execute(
            """INSERT INTO trip_stops
               (id, trip_id, trip_region_id, parent_trip_stop_id, ord,
                stop_type, date_start, date_end, location_name,
                latitude, longitude, title, notes, thematic_tags_json,
                created_at, updated_at, meta_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}')""",
            (
                sid, trip_id, trip_region_id, parent_trip_stop_id, ord_,
                stop_type, date_start, date_end, location_name,
                latitude, longitude, title, notes,
                json.dumps(thematic_tags or [], ensure_ascii=False),
                _now(), _now(),
            ),
        )
        con.commit()
        return sid
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def theme_create(
    trip_id: str,
    title: str,
    tag: str,
    ord_: int = 0,
    description: Optional[str] = None,
) -> str:
    tid = _new_id()
    con = _connect()
    try:
        con.execute(
            """INSERT INTO trip_themes
               (id, trip_id, ord, title, description, tag, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (tid, trip_id, ord_, title, description, tag, _now()),
        )
        con.commit()
        return tid
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ── Photo links ───────────────────────────────────────────────────────────


def photo_link_upsert(
    trip_id: str,
    photo_id: str,
    trip_region_id: Optional[str] = None,
    trip_stop_id: Optional[str] = None,
    taken_at: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    assignment_method: str = "exif_time",
    cluster_confidence: Optional[float] = None,
) -> str:
    """Insert or update the (trip, photo) link. Re-clustering updates
    the assignment in place; operator-confirmed links are NOT
    overwritten by re-clustering."""
    con = _connect()
    try:
        existing = con.execute(
            "SELECT id, assignment_method FROM trip_photo_links "
            "WHERE trip_id = ? AND photo_id = ?",
            (trip_id, photo_id),
        ).fetchone()
        if existing:
            if (existing["assignment_method"] or "") in ("operator", "manual"):
                return existing["id"]  # operator truth wins
            con.execute(
                """UPDATE trip_photo_links
                   SET trip_region_id = ?, trip_stop_id = ?, taken_at = ?,
                       latitude = ?, longitude = ?, assignment_method = ?,
                       cluster_confidence = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    trip_region_id, trip_stop_id, taken_at, latitude,
                    longitude, assignment_method, cluster_confidence,
                    _now(), existing["id"],
                ),
            )
            con.commit()
            return existing["id"]
        lid = _new_id()
        con.execute(
            """INSERT INTO trip_photo_links
               (id, trip_id, trip_region_id, trip_stop_id, photo_id,
                taken_at, latitude, longitude, assignment_method,
                cluster_confidence, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                lid, trip_id, trip_region_id, trip_stop_id, photo_id,
                taken_at, latitude, longitude, assignment_method,
                cluster_confidence, _now(), _now(),
            ),
        )
        con.commit()
        return lid
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def photo_links_list(
    trip_id: str,
    max_confidence: Optional[float] = None,
) -> List[Dict[str, Any]]:
    con = _connect()
    try:
        if max_confidence is not None:
            rows = con.execute(
                "SELECT * FROM trip_photo_links WHERE trip_id = ? AND "
                "(cluster_confidence IS NULL OR cluster_confidence <= ?) "
                "ORDER BY taken_at, ord",
                (trip_id, max_confidence),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM trip_photo_links WHERE trip_id = ? "
                "ORDER BY taken_at, ord",
                (trip_id,),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        con.close()


def photo_link_update(
    link_id: str,
    trip_stop_id: Optional[str] = None,
    include_in_memoir: Optional[bool] = None,
    caption: Optional[str] = None,
    narrator_caption: Optional[str] = None,
    confirm: bool = False,
) -> bool:
    """Operator review action. ``confirm=True`` stamps the link as
    operator truth (method='operator', confidence=1.0) so re-clustering
    never overwrites it."""
    sets: List[str] = []
    args: List[Any] = []
    if trip_stop_id is not None:
        sets.append("trip_stop_id = ?")
        args.append(trip_stop_id)
    if include_in_memoir is not None:
        sets.append("include_in_memoir = ?")
        args.append(1 if include_in_memoir else 0)
    if caption is not None:
        sets.append("caption = ?")
        args.append(caption)
    if narrator_caption is not None:
        sets.append("narrator_caption = ?")
        args.append(narrator_caption)
    if confirm:
        sets.append("assignment_method = 'operator'")
        sets.append("cluster_confidence = 1.0")
    if not sets:
        return False
    sets.append("updated_at = ?")
    args.append(_now())
    args.append(link_id)
    con = _connect()
    try:
        cur = con.execute(
            f"UPDATE trip_photo_links SET {', '.join(sets)} WHERE id = ?",
            args,
        )
        con.commit()
        return cur.rowcount > 0
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ── Tree read + memoir preview ────────────────────────────────────────────


def trip_tree(trip_id: str) -> Optional[Dict[str, Any]]:
    """Full hierarchical read: trip -> regions -> stops (nested) with
    themes and photo-link counts. This is the shape the Trip Tab UI
    and the memoir preview both consume."""
    trip = trip_get(trip_id)
    if not trip:
        return None
    con = _connect()
    try:
        regions = [
            _row_to_dict(r) for r in con.execute(
                "SELECT * FROM trip_regions WHERE trip_id = ? ORDER BY ord",
                (trip_id,),
            ).fetchall()
        ]
        stops = [
            _row_to_dict(r) for r in con.execute(
                "SELECT * FROM trip_stops WHERE trip_id = ? ORDER BY ord",
                (trip_id,),
            ).fetchall()
        ]
        themes = [
            _row_to_dict(r) for r in con.execute(
                "SELECT * FROM trip_themes WHERE trip_id = ? ORDER BY ord",
                (trip_id,),
            ).fetchall()
        ]
        photo_counts: Dict[str, int] = {}
        for row in con.execute(
            "SELECT trip_stop_id, COUNT(*) AS n FROM trip_photo_links "
            "WHERE trip_id = ? GROUP BY trip_stop_id",
            (trip_id,),
        ).fetchall():
            photo_counts[row["trip_stop_id"] or ""] = row["n"]
    finally:
        con.close()

    # Nest stops under parents, then under regions.
    by_id: Dict[str, Dict[str, Any]] = {}
    for s in stops:
        s["children"] = []
        s["photo_count"] = photo_counts.get(s["id"], 0)
        by_id[s["id"]] = s
    roots_by_region: Dict[str, List[Dict[str, Any]]] = {}
    for s in stops:
        parent_id = s.get("parent_trip_stop_id")
        if parent_id and parent_id in by_id:
            by_id[parent_id]["children"].append(s)
        else:
            roots_by_region.setdefault(s["trip_region_id"], []).append(s)
    for region in regions:
        region["stops"] = roots_by_region.get(region["id"], [])
    trip["regions"] = regions
    trip["themes"] = themes
    trip["unassigned_photo_count"] = photo_counts.get("", 0)
    return trip


def trip_memoir_preview(trip_id: str) -> Optional[Dict[str, Any]]:
    """Deterministic dual-axis memoir preview per WO-TRIP-MEMOIR-01:
    Part I chronological (regions -> nested stops), Part II thematic
    (themes with their matching stops), Part III photo appendix
    counts. No LLM authoring — this is a walk of canonical rows."""
    tree = trip_tree(trip_id)
    if not tree:
        return None

    def _stop_line(stop: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "location_name": stop.get("location_name"),
            "title": stop.get("title"),
            "stop_type": stop.get("stop_type"),
            "date_start": stop.get("date_start"),
            "date_end": stop.get("date_end"),
            "notes": stop.get("notes"),
            "photo_count": stop.get("photo_count", 0),
            "day_trips": [_stop_line(c) for c in stop.get("children", [])],
        }

    part_one = []
    all_stops_flat: List[Dict[str, Any]] = []

    def _flatten(stop: Dict[str, Any]) -> None:
        all_stops_flat.append(stop)
        for c in stop.get("children", []):
            _flatten(c)

    for region in tree.get("regions", []):
        for s in region.get("stops", []):
            _flatten(s)
        part_one.append({
            "region": region.get("title"),
            "country_or_area": region.get("country_or_area"),
            "date_range": {
                "start": region.get("start_date"),
                "end": region.get("end_date"),
            },
            "base_address": region.get("base_address"),
            "summary": region.get("summary"),
            "stops": [_stop_line(s) for s in region.get("stops", [])],
        })

    part_two = []
    for theme in tree.get("themes", []):
        tag = theme.get("tag")
        matching = [
            s.get("location_name") for s in all_stops_flat
            if tag and tag in (s.get("thematic_tags_json") or [])
        ]
        part_two.append({
            "theme": theme.get("title"),
            "description": theme.get("description"),
            "tag": tag,
            "stops": matching,
        })

    total_photos = sum(s.get("photo_count", 0) for s in all_stops_flat)
    return {
        "trip_id": trip_id,
        "title": tree.get("title"),
        "date_range": {
            "start": tree.get("start_date"),
            "end": tree.get("end_date"),
        },
        "summary": tree.get("summary"),
        "part_one_journey_in_order": part_one,
        "part_two_themes": part_two,
        "part_three_photo_appendix": {
            "assigned_photos": total_photos,
            "unassigned_photos": tree.get("unassigned_photo_count", 0),
        },
    }
