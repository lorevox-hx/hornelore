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

# WO-TRIP-LANE-AUDIT-FIXPACK-01 (H1): single source of truth for the
# trip_stops.stop_type CHECK enum (migration 0015). API + import
# layers validate against this so an off-enum value is rejected
# cleanly instead of surfacing as an unhandled 500 when SQLite
# raises IntegrityError on insert/update.
STOP_TYPES = (
    "base", "day_trip", "transit", "lodging",
    "meal", "disruption", "sight", "memory_anchor",
)


# WO-TRIP-LANE-AUDIT-FIXPACK-02 (M1): raised when a region delete is
# refused because the region still has stops (whose FK cascade would
# destroy operator-authored titles/notes/dates). Callers move or delete
# the stops first, or pass force=True to accept the cascade explicitly.
class RegionNotEmptyError(Exception):
    pass


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


def trip_update(
    trip_id: str,
    title: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    summary: Optional[str] = None,
    clear_start_date: bool = False,
    clear_end_date: bool = False,
    clear_summary: bool = False,
) -> bool:
    """Operator edit of trip-level fields. Non-None fields are written; a
    matching clear_* flag NULLs a field (blank-means-unchanged otherwise, so
    the operator can actually erase a date or summary). Returns True if a row
    changed. Mirrors region_update / stop_update; trip meta_json has its own
    trip_meta_* helpers."""
    sets: List[str] = []
    args: List[Any] = []
    if title is not None:
        sets.append("title = ?"); args.append(title)
    if clear_start_date:
        sets.append("start_date = NULL")
    elif start_date is not None:
        sets.append("start_date = ?"); args.append(start_date)
    if clear_end_date:
        sets.append("end_date = NULL")
    elif end_date is not None:
        sets.append("end_date = ?"); args.append(end_date)
    if clear_summary:
        sets.append("summary = NULL")
    elif summary is not None:
        sets.append("summary = ?"); args.append(summary)
    if not sets:
        return False
    sets.append("updated_at = ?"); args.append(_now())
    args.append(trip_id)
    con = _connect()
    try:
        cur = con.execute(
            f"UPDATE trips SET {', '.join(sets)} WHERE id = ?", args,
        )
        con.commit()
        return cur.rowcount > 0
    except Exception:
        con.rollback()
        raise
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


def stop_trip_id(stop_id: str) -> Optional[str]:
    con = _connect()
    try:
        row = con.execute(
            "SELECT trip_id FROM trip_stops WHERE id = ?", (stop_id,),
        ).fetchone()
        return row["trip_id"] if row else None
    finally:
        con.close()


def stop_get(stop_id: str) -> Optional[Dict[str, Any]]:
    """Single stop row (Phase C2 — stop-scoped upload needs the stop's
    dates/GPS/region for the mismatch cross-check + link write)."""
    con = _connect()
    try:
        row = con.execute(
            "SELECT * FROM trip_stops WHERE id = ?", (stop_id,),
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        con.close()


def region_trip_id(region_id: str) -> Optional[str]:
    con = _connect()
    try:
        row = con.execute(
            "SELECT trip_id FROM trip_regions WHERE id = ?", (region_id,),
        ).fetchone()
        return row["trip_id"] if row else None
    finally:
        con.close()


def trip_meta_update(trip_id: str, meta: Dict[str, Any]) -> bool:
    """Replace trips.meta_json wholesale (callers read-modify-write).
    Prefer trip_meta_merge for concurrent-safe key updates."""
    con = _connect()
    try:
        cur = con.execute(
            "UPDATE trips SET meta_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(meta or {}, ensure_ascii=False), _now(), trip_id),
        )
        con.commit()
        return cur.rowcount > 0
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def trip_meta_merge(trip_id: str, patch: Dict[str, Any]) -> bool:
    """Merge keys into trips.meta_json atomically — the read-modify-
    write happens inside a single BEGIN IMMEDIATE transaction so two
    concurrent syncs can't clobber each other's keys (review fix
    2026-07-05)."""
    con = _connect()
    try:
        con.execute("BEGIN IMMEDIATE;")
        row = con.execute(
            "SELECT meta_json FROM trips WHERE id = ?", (trip_id,),
        ).fetchone()
        if not row:
            con.rollback()
            return False
        try:
            meta = json.loads(row["meta_json"] or "{}")
            if not isinstance(meta, dict):
                meta = {}
        except Exception:
            meta = {}
        meta.update(patch or {})
        con.execute(
            "UPDATE trips SET meta_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(meta, ensure_ascii=False), _now(), trip_id),
        )
        con.commit()
        return True
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def bio_suggestion_replace_for_trip(
    trip_id: str,
    person_id: str,
    field_key: str,
    suggested_value: str,
) -> str:
    """One suggestion row per (trip, field_key) — replace on re-sync.
    Stays status='suggested'; promotion to bio truth is a review
    decision, never automatic (locked principle 5)."""
    con = _connect()
    try:
        con.execute(
            "DELETE FROM trip_bio_suggestions WHERE trip_id = ? AND field_key = ?",
            (trip_id, field_key),
        )
        sid = _new_id()
        con.execute(
            """INSERT INTO trip_bio_suggestions
               (id, trip_id, person_id, field_key, suggested_value,
                status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'suggested', ?, ?)""",
            (sid, trip_id, person_id, field_key, suggested_value,
             _now(), _now()),
        )
        con.commit()
        return sid
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def region_update(
    region_id: str,
    title: Optional[str] = None,
    country_or_area: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    summary: Optional[str] = None,
    base_address: Optional[str] = None,
    ord_: Optional[int] = None,
    clear_country_or_area: bool = False,
    clear_start_date: bool = False,
    clear_end_date: bool = False,
    clear_summary: bool = False,
    clear_base_address: bool = False,
) -> bool:
    sets: List[str] = []
    args: List[Any] = []
    if title is not None:
        sets.append("title = ?"); args.append(title)
    if clear_country_or_area:
        sets.append("country_or_area = NULL")
    elif country_or_area is not None:
        sets.append("country_or_area = ?"); args.append(country_or_area)
    if clear_start_date:
        sets.append("start_date = NULL")
    elif start_date is not None:
        sets.append("start_date = ?"); args.append(start_date)
    if clear_end_date:
        sets.append("end_date = NULL")
    elif end_date is not None:
        sets.append("end_date = ?"); args.append(end_date)
    if clear_summary:
        sets.append("summary = NULL")
    elif summary is not None:
        sets.append("summary = ?"); args.append(summary)
    if clear_base_address:
        sets.append("base_address = NULL")
    elif base_address is not None:
        sets.append("base_address = ?"); args.append(base_address)
    if ord_ is not None:
        sets.append("ord = ?"); args.append(int(ord_))
    if not sets:
        return False
    sets.append("updated_at = ?"); args.append(_now())
    args.append(region_id)
    con = _connect()
    try:
        cur = con.execute(
            f"UPDATE trip_regions SET {', '.join(sets)} WHERE id = ?", args,
        )
        con.commit()
        return cur.rowcount > 0
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def region_delete(region_id: str, force: bool = False) -> bool:
    """Delete a region. WO-TRIP-LANE-AUDIT-FIXPACK-02 (M1): by default
    REFUSES to delete a region that still has stops, because the FK
    cascade would destroy operator-authored stop content (titles,
    location names, notes, date work, structure). Move or delete the
    stops first, or pass force=True to accept the cascade explicitly.
    Raises RegionNotEmptyError when blocked."""
    con = _connect()
    try:
        if not force:
            n = con.execute(
                "SELECT COUNT(*) FROM trip_stops WHERE trip_region_id = ?",
                (region_id,),
            ).fetchone()[0]
            if n:
                raise RegionNotEmptyError(
                    "region has %d stop(s); move or delete them first, "
                    "or delete with force=true" % n)
        cur = con.execute(
            "DELETE FROM trip_regions WHERE id = ?", (region_id,),
        )
        con.commit()
        return cur.rowcount > 0
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def stop_delete(stop_id: str) -> bool:
    """Delete a stop. Child day-trips survive with parent SET NULL
    (they become top-level stops in the region); photo links keep
    the trip but lose the stop assignment (SET NULL) so re-clustering
    or operator review can re-home them."""
    con = _connect()
    try:
        cur = con.execute(
            "DELETE FROM trip_stops WHERE id = ?", (stop_id,),
        )
        con.commit()
        return cur.rowcount > 0
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def theme_delete(theme_id: str) -> bool:
    con = _connect()
    try:
        cur = con.execute(
            "DELETE FROM trip_themes WHERE id = ?", (theme_id,),
        )
        con.commit()
        return cur.rowcount > 0
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ── Reorder / move (WO-TRAVEL-DOC-EDITABLE-ITINERARY-TILES-01) ─────────────
#
# Operator tile order is the route authority (dates are metadata). The
# `ord` column already exists on trip_regions / trip_stops and the tree
# read + memoir preview already sort by it — these helpers renumber
# siblings cleanly (0, 1, 2, …) inside ONE transaction so no two siblings
# ever share an ord. The router validates ownership/completeness before
# calling; each UPDATE is also scoped in its WHERE clause so a foreign id
# simply doesn't match (defence in depth). Rows updated is returned so the
# router can assert the full sibling set moved.


def regions_reorder(trip_id: str, ordered_ids: List[str]) -> int:
    """Renumber a trip's regions to match ``ordered_ids`` (index -> ord).
    Only rows that belong to ``trip_id`` are touched. Returns rows updated."""
    con = _connect()
    try:
        n = 0
        for i, rid in enumerate(ordered_ids):
            cur = con.execute(
                "UPDATE trip_regions SET ord = ?, updated_at = ? "
                "WHERE id = ? AND trip_id = ?",
                (i, _now(), rid, trip_id),
            )
            n += cur.rowcount
        con.commit()
        return n
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def stops_reorder(
    trip_id: str,
    region_id: str,
    parent_trip_stop_id: Optional[str],
    ordered_ids: List[str],
) -> int:
    """Renumber one sibling group of stops. Siblings = same trip + same
    region + same parent (NULL parent = top-level stops). Only rows that
    match that scope are touched. Returns rows updated."""
    con = _connect()
    try:
        n = 0
        for i, sid in enumerate(ordered_ids):
            if parent_trip_stop_id is None:
                cur = con.execute(
                    "UPDATE trip_stops SET ord = ?, updated_at = ? "
                    "WHERE id = ? AND trip_id = ? AND trip_region_id = ? "
                    "AND parent_trip_stop_id IS NULL",
                    (i, _now(), sid, trip_id, region_id),
                )
            else:
                cur = con.execute(
                    "UPDATE trip_stops SET ord = ?, updated_at = ? "
                    "WHERE id = ? AND trip_id = ? AND trip_region_id = ? "
                    "AND parent_trip_stop_id = ?",
                    (i, _now(), sid, trip_id, region_id, parent_trip_stop_id),
                )
            n += cur.rowcount
        con.commit()
        return n
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def sibling_stop_ids(
    trip_id: str,
    region_id: str,
    parent_trip_stop_id: Optional[str],
) -> List[str]:
    """Current sibling stop ids (in ord order) for a region + parent scope.
    Used by the router to validate a reorder covers exactly the group, and
    to build the insert order for a move."""
    con = _connect()
    try:
        if parent_trip_stop_id is None:
            rows = con.execute(
                "SELECT id FROM trip_stops WHERE trip_id = ? "
                "AND trip_region_id = ? AND parent_trip_stop_id IS NULL "
                "ORDER BY ord, created_at",
                (trip_id, region_id),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT id FROM trip_stops WHERE trip_id = ? "
                "AND trip_region_id = ? AND parent_trip_stop_id = ? "
                "ORDER BY ord, created_at",
                (trip_id, region_id, parent_trip_stop_id),
            ).fetchall()
        return [r["id"] for r in rows]
    finally:
        con.close()


def stop_child_ids(parent_stop_id: str) -> List[str]:
    """Direct child stop ids of a parent (used to detect promotion on delete —
    when a parent stop is deleted the FK SET NULLs its children up to top
    level, and their ord then needs renumbering)."""
    con = _connect()
    try:
        rows = con.execute(
            "SELECT id FROM trip_stops WHERE parent_trip_stop_id = ?",
            (parent_stop_id,),
        ).fetchall()
        return [r["id"] for r in rows]
    finally:
        con.close()


def stop_move(
    trip_id: str,
    stop_id: str,
    region_id: str,
    parent_trip_stop_id: Optional[str] = None,
    before_stop_id: Optional[str] = None,
    after_stop_id: Optional[str] = None,
) -> bool:
    """Move a stop to a target region/parent and position it relative to a
    sibling — all in one transaction so ord stays clean. If neither
    before_stop_id nor after_stop_id resolves, the stop is appended to the
    end of the target sibling group. Returns False if the stop row (scoped
    to trip_id) didn't exist. The router owns validation (parent/region
    ownership, cycle protection)."""
    con = _connect()
    try:
        prior = con.execute(
            "SELECT trip_region_id, parent_trip_stop_id FROM trip_stops "
            "WHERE id = ? AND trip_id = ?", (stop_id, trip_id),
        ).fetchone()
        if not prior:
            con.rollback()
            return False
        old_region = prior["trip_region_id"]
        old_parent = prior["parent_trip_stop_id"]

        con.execute(
            "UPDATE trip_stops SET trip_region_id = ?, "
            "parent_trip_stop_id = ?, updated_at = ? "
            "WHERE id = ? AND trip_id = ?",
            (region_id, parent_trip_stop_id, _now(), stop_id, trip_id),
        )
        # Photo links carry a denormalized trip_region_id; when the stop
        # changes region its links must follow, or memoir/cluster reads see a
        # link pointing at the wrong region.
        con.execute(
            "UPDATE trip_photo_links SET trip_region_id = ?, updated_at = ? "
            "WHERE trip_id = ? AND trip_stop_id = ?",
            (region_id, _now(), trip_id, stop_id),
        )

        # A parent moves as a UNIT: on a region change, every descendant
        # (day-trips nested under the moved stop, at any depth) follows it to
        # the new region, and so do their photo links. The parent chain is
        # untouched, so the subtree keeps its shape — only trip_region_id
        # moves. Without this the tree would show a child under a parent in a
        # different region (a cross-region parent/child inconsistency).
        if old_region != region_id:
            subtree = [stop_id]
            frontier = [stop_id]
            while frontier:
                qs = ",".join("?" * len(frontier))
                kids = [r["id"] for r in con.execute(
                    "SELECT id FROM trip_stops WHERE trip_id = ? "
                    "AND parent_trip_stop_id IN (%s)" % qs,
                    [trip_id] + frontier).fetchall()]
                subtree.extend(kids)
                frontier = kids
            descendants = subtree[1:]  # moved stop itself already updated
            if descendants:
                qs = ",".join("?" * len(descendants))
                con.execute(
                    "UPDATE trip_stops SET trip_region_id = ?, updated_at = ? "
                    "WHERE id IN (%s)" % qs,
                    [region_id, _now()] + descendants)
                con.execute(
                    "UPDATE trip_photo_links SET trip_region_id = ?, "
                    "updated_at = ? "
                    "WHERE trip_id = ? AND trip_stop_id IN (%s)" % qs,
                    [region_id, _now(), trip_id] + descendants)

        def _group_ids(reg, par):
            if par is None:
                rows2 = con.execute(
                    "SELECT id FROM trip_stops WHERE trip_id = ? "
                    "AND trip_region_id = ? AND parent_trip_stop_id IS NULL "
                    "ORDER BY ord, created_at", (trip_id, reg)).fetchall()
            else:
                rows2 = con.execute(
                    "SELECT id FROM trip_stops WHERE trip_id = ? "
                    "AND trip_region_id = ? AND parent_trip_stop_id = ? "
                    "ORDER BY ord, created_at", (trip_id, reg, par)).fetchall()
            return [r["id"] for r in rows2]

        # Renumber the target group with the moved stop positioned relative
        # to a sibling (or appended).
        target = [sid for sid in _group_ids(region_id, parent_trip_stop_id)
                  if sid != stop_id]
        if before_stop_id and before_stop_id in target:
            idx = target.index(before_stop_id)
        elif after_stop_id and after_stop_id in target:
            idx = target.index(after_stop_id) + 1
        else:
            idx = len(target)  # append
        ordered = target[:idx] + [stop_id] + target[idx:]
        for i, sid in enumerate(ordered):
            con.execute("UPDATE trip_stops SET ord = ? WHERE id = ?", (i, sid))

        # If the stop left a different group, close the gap it left behind by
        # renumbering that old group 0..n too.
        if (old_region, old_parent) != (region_id, parent_trip_stop_id):
            for i, sid in enumerate(_group_ids(old_region, old_parent)):
                con.execute(
                    "UPDATE trip_stops SET ord = ? WHERE id = ?", (i, sid))

        con.commit()
        return True
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()




# ── Location notes (story layer — WO-TRAVEL-DOC-STORY-LAYER-01) ─────────────
#
# Many notes per place, with provenance (source_type) and two promotion
# flags that default OFF. Nothing here reaches the memoir or the interview
# lane until the operator flips include_in_memoir / include_in_interview_context.

_LOCATION_NOTE_SOURCE_TYPES = ("operator", "lori", "external", "draft")


def location_note_create(
    trip_id: str,
    note_text: str,
    note_title: Optional[str] = None,
    trip_region_id: Optional[str] = None,
    trip_stop_id: Optional[str] = None,
    source_type: str = "operator",
    source_ref: Optional[str] = None,
    include_in_memoir: bool = False,
    include_in_interview_context: bool = False,
    target_language: str = "en",
    ord_: int = 0,
    note_id: Optional[str] = None,
    source_surface: Optional[str] = None,
    source_turn_ref: Optional[str] = None,
    photo_link_id: Optional[str] = None,
    trip_day_id: Optional[str] = None,
) -> str:
    if source_type not in _LOCATION_NOTE_SOURCE_TYPES:
        source_type = "operator"
    nid = note_id or _new_id()
    con = _connect()
    try:
        con.execute(
            """INSERT INTO trip_location_notes
               (id, trip_id, trip_region_id, trip_stop_id, trip_day_id,
                note_title,
                note_text, source_type, source_ref, source_surface,
                source_turn_ref, photo_link_id,
                include_in_memoir,
                include_in_interview_context, target_language, ord,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       ?, ?)""",
            (
                nid, trip_id, trip_region_id, trip_stop_id, trip_day_id,
                note_title,
                note_text, source_type, source_ref, source_surface,
                source_turn_ref, photo_link_id,
                1 if include_in_memoir else 0,
                1 if include_in_interview_context else 0,
                target_language, int(ord_), _now(), _now(),
            ),
        )
        con.commit()
        return nid
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def location_notes_list(trip_id: str) -> List[Dict[str, Any]]:
    """All notes for a trip, ordered. Scope filtering (trip/region/stop)
    is done by the caller so one read serves the UI and the memoir.
    Tolerant of a pre-0019 DB (old table shape / missing) — returns []."""
    con = _connect()
    try:
        rows = con.execute(
            "SELECT * FROM trip_location_notes WHERE trip_id = ? "
            "ORDER BY ord, created_at",
            (trip_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()


def location_note_get(note_id: str) -> Optional[Dict[str, Any]]:
    con = _connect()
    try:
        row = con.execute(
            "SELECT * FROM trip_location_notes WHERE id = ?", (note_id,),
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        con.close()


def location_note_trip_id(note_id: str) -> Optional[str]:
    con = _connect()
    try:
        row = con.execute(
            "SELECT trip_id FROM trip_location_notes WHERE id = ?", (note_id,),
        ).fetchone()
        return row["trip_id"] if row else None
    finally:
        con.close()


def location_note_update(
    note_id: str,
    note_title: Optional[str] = None,
    note_text: Optional[str] = None,
    source_type: Optional[str] = None,
    source_ref: Optional[str] = None,
    include_in_memoir: Optional[bool] = None,
    include_in_interview_context: Optional[bool] = None,
    ord_: Optional[int] = None,
    clear_title: bool = False,
) -> bool:
    """Partial update. Text fields: None = unchanged. Booleans: None =
    unchanged, else written. clear_title NULLs the title."""
    sets: List[str] = []
    args: List[Any] = []
    if clear_title:
        sets.append("note_title = NULL")
    elif note_title is not None:
        sets.append("note_title = ?"); args.append(note_title)
    if note_text is not None:
        sets.append("note_text = ?"); args.append(note_text)
    if source_type is not None and source_type in _LOCATION_NOTE_SOURCE_TYPES:
        sets.append("source_type = ?"); args.append(source_type)
    if source_ref is not None:
        sets.append("source_ref = ?"); args.append(source_ref)
    if include_in_memoir is not None:
        sets.append("include_in_memoir = ?"); args.append(1 if include_in_memoir else 0)
    if include_in_interview_context is not None:
        sets.append("include_in_interview_context = ?")
        args.append(1 if include_in_interview_context else 0)
    if ord_ is not None:
        sets.append("ord = ?"); args.append(int(ord_))
    if not sets:
        return False
    sets.append("updated_at = ?"); args.append(_now())
    args.append(note_id)
    con = _connect()
    try:
        cur = con.execute(
            f"UPDATE trip_location_notes SET {', '.join(sets)} WHERE id = ?", args,
        )
        con.commit()
        return cur.rowcount > 0
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def location_note_delete(note_id: str) -> bool:
    con = _connect()
    try:
        cur = con.execute(
            "DELETE FROM trip_location_notes WHERE id = ?", (note_id,),
        )
        con.commit()
        return cur.rowcount > 0
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ── Sources (documents — WO-TRAVEL-DOC-SOURCES-01) ─────────────────────────
#
# Non-photo source material (files, pasted text, links) attached to a
# trip/region/stop. Separate from the photo pipeline. include_in_memoir
# defaults OFF.

_TRIP_SOURCE_TYPES = ("itinerary", "receipt", "hotel", "ticket",
                      "note", "map", "link", "other")


def source_create(
    trip_id: str,
    source_type: str = "other",
    title: Optional[str] = None,
    trip_region_id: Optional[str] = None,
    trip_stop_id: Optional[str] = None,
    filename: Optional[str] = None,
    mime_type: Optional[str] = None,
    storage_path: Optional[str] = None,
    pasted_text: Optional[str] = None,
    link_url: Optional[str] = None,
    source_date: Optional[str] = None,
    summary: Optional[str] = None,
    include_in_memoir: bool = False,
    ord_: int = 0,
    source_id: Optional[str] = None,
    trip_day_id: Optional[str] = None,
) -> str:
    if source_type not in _TRIP_SOURCE_TYPES:
        source_type = "other"
    sid = source_id or _new_id()
    con = _connect()
    try:
        con.execute(
            """INSERT INTO trip_sources
               (id, trip_id, trip_region_id, trip_stop_id, trip_day_id,
                source_type,
                title, filename, mime_type, storage_path, pasted_text,
                link_url, source_date, summary, include_in_memoir, ord,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       ?)""",
            (
                sid, trip_id, trip_region_id, trip_stop_id, trip_day_id,
                source_type,
                title, filename, mime_type, storage_path, pasted_text,
                link_url, source_date, summary,
                1 if include_in_memoir else 0, int(ord_), _now(), _now(),
            ),
        )
        con.commit()
        return sid
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def sources_list(trip_id: str,
                 day_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Tolerant of a pre-0020 DB (trip_sources missing) — returns [].
    ``day_id`` narrows to sources attached to that day card
    (trip_sources.trip_day_id, migration 0029)."""
    con = _connect()
    try:
        rows = con.execute(
            "SELECT * FROM trip_sources WHERE trip_id = ? ORDER BY ord, created_at",
            (trip_id,),
        ).fetchall()
        out = [_row_to_dict(r) for r in rows]
        if day_id:
            out = [s for s in out
                   if str(s.get("trip_day_id") or "") == str(day_id)]
        return out
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()


def source_get(source_id: str) -> Optional[Dict[str, Any]]:
    con = _connect()
    try:
        row = con.execute(
            "SELECT * FROM trip_sources WHERE id = ?", (source_id,),
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        con.close()


def source_trip_id(source_id: str) -> Optional[str]:
    con = _connect()
    try:
        row = con.execute(
            "SELECT trip_id FROM trip_sources WHERE id = ?", (source_id,),
        ).fetchone()
        return row["trip_id"] if row else None
    finally:
        con.close()


def source_update(
    source_id: str,
    source_type: Optional[str] = None,
    title: Optional[str] = None,
    pasted_text: Optional[str] = None,
    link_url: Optional[str] = None,
    source_date: Optional[str] = None,
    summary: Optional[str] = None,
    include_in_memoir: Optional[bool] = None,
    ord_: Optional[int] = None,
    trip_day_id: Optional[str] = None,
    clear_day: bool = False,
) -> bool:
    """Partial update. ``trip_day_id`` attaches (or moves) the source to
    a day card; ``clear_day`` detaches it (NULLs trip_day_id ONLY — the
    source row itself is never deleted by an unlink)."""
    sets: List[str] = []
    args: List[Any] = []
    if clear_day:
        sets.append("trip_day_id = NULL")
    elif trip_day_id is not None:
        sets.append("trip_day_id = ?"); args.append(trip_day_id)
    if source_type is not None and source_type in _TRIP_SOURCE_TYPES:
        sets.append("source_type = ?"); args.append(source_type)
    if title is not None:
        sets.append("title = ?"); args.append(title)
    if pasted_text is not None:
        sets.append("pasted_text = ?"); args.append(pasted_text)
    if link_url is not None:
        sets.append("link_url = ?"); args.append(link_url)
    if source_date is not None:
        sets.append("source_date = ?"); args.append(source_date)
    if summary is not None:
        sets.append("summary = ?"); args.append(summary)
    if include_in_memoir is not None:
        sets.append("include_in_memoir = ?"); args.append(1 if include_in_memoir else 0)
    if ord_ is not None:
        sets.append("ord = ?"); args.append(int(ord_))
    if not sets:
        return False
    sets.append("updated_at = ?"); args.append(_now())
    args.append(source_id)
    con = _connect()
    try:
        cur = con.execute(
            f"UPDATE trip_sources SET {', '.join(sets)} WHERE id = ?", args,
        )
        con.commit()
        return cur.rowcount > 0
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def source_delete(source_id: str) -> bool:
    con = _connect()
    try:
        cur = con.execute(
            "DELETE FROM trip_sources WHERE id = ?", (source_id,),
        )
        con.commit()
        return cur.rowcount > 0
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


def photo_link_get(link_id: str) -> Optional[Dict[str, Any]]:
    """Single link row — BUG-TRIP-PHOTO-LINK-CROSS-TRIP-STOP-ASSIGNMENT-01:
    patch callers need the link's trip_id to validate the target stop."""
    con = _connect()
    try:
        row = con.execute(
            "SELECT * FROM trip_photo_links WHERE id = ?", (link_id,),
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        con.close()


# WO-TRIP-LANE-AUDIT-FIXPACK-01 (C1): the narrator read is an EXPLICIT
# allowlist, never SELECT l.*. Raw latitude/longitude are NEVER
# projected (only a gps_present boolean). The operator caption reaches
# the narrator ONLY when caption_approved_for_lori=1; operator_context_
# note ONLY when operator_context_approved_for_lori=1. narrator_caption
# (the narrator's own words) is preferred and always safe. The single
# `caption` field the Travels shelf renders is the SAFE caption:
# narrator_caption first, else approved operator caption, else NULL.
_NARRATOR_PHOTO_LINK_COLS = (
    "l.id, l.trip_id, l.trip_region_id, l.trip_stop_id, l.photo_id, "
    "l.taken_at, l.ord, l.include_in_memoir, l.thematic_tags_json, "
    "l.created_at, l.updated_at, l.narrator_caption, "
    "l.caption_approved_for_lori, l.operator_context_approved_for_lori, "
    "CASE "
    "  WHEN l.narrator_caption IS NOT NULL AND l.narrator_caption <> '' "
    "    THEN l.narrator_caption "
    "  WHEN l.caption_approved_for_lori = 1 THEN l.caption "
    "  ELSE NULL "
    "END AS caption, "
    "CASE WHEN l.operator_context_approved_for_lori = 1 "
    "  THEN l.operator_context_note ELSE NULL END AS operator_context_note, "
    "(l.latitude IS NOT NULL) AS gps_present"
)

# Pre-0022 fallback: approval columns absent. Safe direction — expose
# only narrator_caption as the caption; never any operator text.
_NARRATOR_PHOTO_LINK_COLS_LEGACY = (
    "l.id, l.trip_id, l.trip_region_id, l.trip_stop_id, l.photo_id, "
    "l.taken_at, l.ord, l.include_in_memoir, l.thematic_tags_json, "
    "l.created_at, l.updated_at, l.narrator_caption, "
    "l.narrator_caption AS caption, "
    "(l.latitude IS NOT NULL) AS gps_present"
)


def narrator_photo_links(trip_id: str) -> List[Dict[str, Any]]:
    """Narrator-safe link read — BUG-TRAVELS-PHOTO-STRIP-LEAKS-NON-
    NARRATOR-READY-PHOTOS-01: the Travels shelf strip must only show
    photos the narrator is cleared to see (BUG-238 rule: unvetted
    intake photos never reach narrator-visible surfaces). Joins photos
    and filters narrator_ready=1 + not deleted. The operator Trip Tab
    keeps the unfiltered photo_links_list.

    WO-TRIP-LANE-AUDIT-FIXPACK-01 (C1): returns an explicit narrator-
    safe allowlist (no raw GPS, approval-gated operator caption/context)
    instead of SELECT l.*."""
    con = _connect()
    try:
        where = (
            " FROM trip_photo_links l "
            " JOIN photos p ON p.id = l.photo_id "
            " WHERE l.trip_id = ? "
            "   AND p.narrator_ready = 1 "
            "   AND p.deleted_at IS NULL "
            " ORDER BY l.taken_at, l.ord"
        )
        try:
            rows = con.execute(
                "SELECT " + _NARRATOR_PHOTO_LINK_COLS + where,
                (trip_id,),
            ).fetchall()
        except sqlite3.OperationalError:
            # DB behind on migration 0022 — degrade closed (no operator
            # text), never fall through to SELECT l.*.
            rows = con.execute(
                "SELECT " + _NARRATOR_PHOTO_LINK_COLS_LEGACY + where,
                (trip_id,),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        con.close()


# Ph1 (WO-TRIP-PHOTO-CONTEXT-ENRICHMENT-FOR-LORI-01): the OPERATOR
# photo-link read carries reviewable photo metadata (date provenance,
# gps PRESENCE, place label, approval flags) so the Travel Doc can show
# "date found / guessed / no embedded EXIF" and the approval toggles.
# Raw GPS coordinates are deliberately NOT projected here — gps_present
# is a boolean. This is the operator surface; the narrator read
# (narrator_photo_links) is untouched.
_PHOTO_REVIEW_COLS = (
    "p.date_value AS photo_date_value, "
    "p.date_precision AS photo_date_precision, "
    "p.date_source AS photo_date_source, "
    "p.taken_at_filename_guess AS photo_taken_at_filename_guess, "
    "p.location_label AS photo_location_label, "
    "p.metadata_trust AS photo_metadata_trust, "
    "p.date_approved_for_lori AS photo_date_approved_for_lori, "
    "p.location_approved_for_lori AS photo_location_approved_for_lori, "
    "p.narrator_ready AS photo_narrator_ready, "
    "(p.latitude IS NOT NULL) AS photo_gps_present"
)


def photo_links_list(
    trip_id: str,
    max_confidence: Optional[float] = None,
) -> List[Dict[str, Any]]:
    con = _connect()
    try:
        def _run(cols):
            base = ("SELECT l.*" + cols +
                    " FROM trip_photo_links l "
                    "LEFT JOIN photos p ON p.id = l.photo_id "
                    "WHERE l.trip_id = ? ")
            if max_confidence is not None:
                return con.execute(
                    base +
                    "AND (l.cluster_confidence IS NULL "
                    "OR l.cluster_confidence <= ?) "
                    "ORDER BY l.taken_at, l.ord",
                    (trip_id, max_confidence),
                ).fetchall()
            return con.execute(
                base + "ORDER BY l.taken_at, l.ord",
                (trip_id,),
            ).fetchall()
        try:
            rows = _run(", " + _PHOTO_REVIEW_COLS)
        except sqlite3.OperationalError:
            # WO-TRIP-LANE-AUDIT-FIXPACK-02 (M4): DB behind on the 0016/
            # 0023 review columns (date_precision, metadata_trust, the
            # *_approved_for_lori flags). Degrade to the base link row
            # instead of 500ing — the operator loses the review
            # annotations for this read, not the whole list.
            rows = _run("")
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
    trip_region_id: Optional[str] = None,
    caption_approved_for_lori: Optional[bool] = None,
    operator_context_note: Optional[str] = None,
    clear_operator_context_note: bool = False,
    operator_context_approved_for_lori: Optional[bool] = None,
) -> bool:
    """Operator review action. ``confirm=True`` stamps the link as
    operator truth (method='operator', confidence=1.0) so re-clustering
    never overwrites it. BUG-TRIP-PHOTO-LINK-REGION-STOP-DESYNC-01:
    when a photo moves to a stop in another region, callers must pass
    the stop's region so the pair stays consistent."""
    sets: List[str] = []
    args: List[Any] = []
    if trip_stop_id is not None:
        sets.append("trip_stop_id = ?")
        args.append(trip_stop_id)
    if trip_region_id is not None:
        sets.append("trip_region_id = ?")
        args.append(trip_region_id)
    if include_in_memoir is not None:
        sets.append("include_in_memoir = ?")
        args.append(1 if include_in_memoir else 0)
    if caption is not None:
        sets.append("caption = ?")
        args.append(caption)
    if narrator_caption is not None:
        sets.append("narrator_caption = ?")
        args.append(narrator_caption)
    # WO-TRIP-PHOTO-CONTEXT-ENRICHMENT-FOR-LORI-01 Ph5: approval-gated
    # photo context. Editing the operator caption REVOKES its approval
    # unless the same request re-approves it — approval always refers
    # to the text the operator actually reviewed.
    if caption is not None and caption_approved_for_lori is None:
        sets.append("caption_approved_for_lori = 0")
    if caption_approved_for_lori is not None:
        sets.append("caption_approved_for_lori = ?")
        args.append(1 if caption_approved_for_lori else 0)
    if clear_operator_context_note:
        sets.append("operator_context_note = NULL")
        sets.append("operator_context_approved_for_lori = 0")
    elif operator_context_note is not None:
        sets.append("operator_context_note = ?")
        args.append(operator_context_note)
        if operator_context_approved_for_lori is None:
            sets.append("operator_context_approved_for_lori = 0")
    if operator_context_approved_for_lori is not None and not clear_operator_context_note:
        sets.append("operator_context_approved_for_lori = ?")
        args.append(1 if operator_context_approved_for_lori else 0)
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


def stop_update(
    stop_id: str,
    location_name: Optional[str] = None,
    stop_type: Optional[str] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    title: Optional[str] = None,
    notes: Optional[str] = None,
    thematic_tags: Optional[List[str]] = None,
    clear_dates: bool = False,
    clear_start_date: bool = False,
    clear_end_date: bool = False,
    clear_notes: bool = False,
    ord_: Optional[int] = None,
    parent_trip_stop_id: Optional[str] = None,
    clear_parent: bool = False,
) -> bool:
    """Operator correction surface — tightening stop dates/GPS is how
    clustering confidence improves on real photo sets. ``clear_dates``
    nulls both date columns (dates are None-means-unchanged otherwise)."""
    sets: List[str] = []
    args: List[Any] = []
    if location_name is not None:
        sets.append("location_name = ?"); args.append(location_name)
    if stop_type is not None:
        sets.append("stop_type = ?"); args.append(stop_type)
    if clear_dates or clear_start_date:
        sets.append("date_start = NULL")
    elif date_start is not None:
        sets.append("date_start = ?"); args.append(date_start)
    if clear_dates or clear_end_date:
        sets.append("date_end = NULL")
    elif date_end is not None:
        sets.append("date_end = ?"); args.append(date_end)
    if latitude is not None:
        sets.append("latitude = ?"); args.append(latitude)
    if longitude is not None:
        sets.append("longitude = ?"); args.append(longitude)
    if title is not None:
        sets.append("title = ?"); args.append(title)
    if clear_notes:
        sets.append("notes = NULL")
    elif notes is not None:
        sets.append("notes = ?"); args.append(notes)
    if thematic_tags is not None:
        sets.append("thematic_tags_json = ?")
        args.append(json.dumps(thematic_tags, ensure_ascii=False))
    if ord_ is not None:
        sets.append("ord = ?"); args.append(int(ord_))
    if clear_parent:
        sets.append("parent_trip_stop_id = NULL")
    elif parent_trip_stop_id is not None:
        sets.append("parent_trip_stop_id = ?"); args.append(parent_trip_stop_id)
    if not sets:
        return False
    sets.append("updated_at = ?"); args.append(_now())
    args.append(stop_id)
    con = _connect()
    try:
        cur = con.execute(
            f"UPDATE trip_stops SET {', '.join(sets)} WHERE id = ?", args,
        )
        con.commit()
        return cur.rowcount > 0
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def trip_delete(trip_id: str) -> bool:
    """Delete a trip and everything under it (FK cascades cover
    regions/stops/themes/photo-links/notes/suggestions/story-links).
    Photos themselves are NOT touched — trip_photo_links are joins,
    not ownership."""
    con = _connect()
    try:
        cur = con.execute("DELETE FROM trips WHERE id = ?", (trip_id,))
        con.commit()
        return cur.rowcount > 0
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def photo_links_with_photo_paths(
    trip_id: str,
    memoir_only: bool = True,
) -> List[Dict[str, Any]]:
    """Photo links joined to the photos authority table for rendering
    (image_path for DOCX embedding, description for captions). Rows
    whose photo has been soft-deleted are excluded."""
    con = _connect()
    try:
        where = "l.trip_id = ? AND p.deleted_at IS NULL"
        if memoir_only:
            where += " AND l.include_in_memoir = 1"
        rows = con.execute(
            f"""SELECT l.*, p.image_path AS photo_image_path,
                       p.description AS photo_description,
                       p.date_value AS photo_date_value,
                       p.narrator_ready AS photo_narrator_ready,
                       s.location_name AS stop_location_name,
                       r.title AS region_title
                FROM trip_photo_links l
                JOIN photos p ON p.id = l.photo_id
                LEFT JOIN trip_stops s ON s.id = l.trip_stop_id
                LEFT JOIN trip_regions r ON r.id = l.trip_region_id
                WHERE {where}
                ORDER BY l.taken_at, l.ord""",
            (trip_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
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

    # Promoted story notes (include_in_memoir=1) grouped by scope. Notes
    # NOT flagged never reach the memoir (WO-TRAVEL-DOC-STORY-LAYER-01).
    _notes_stop: Dict[str, List[Dict[str, Any]]] = {}
    _notes_region: Dict[str, List[Dict[str, Any]]] = {}
    _notes_trip: List[Dict[str, Any]] = []
    for _n in location_notes_list(trip_id):
        if not _n.get("include_in_memoir"):
            continue
        _entry = {"note_title": _n.get("note_title"),
                  "note_text": _n.get("note_text"),
                  "source_type": _n.get("source_type")}
        _sid, _rid = _n.get("trip_stop_id"), _n.get("trip_region_id")
        if _sid:
            _notes_stop.setdefault(_sid, []).append(_entry)
        elif _rid:
            _notes_region.setdefault(_rid, []).append(_entry)
        else:
            _notes_trip.append(_entry)

    # Promoted sources (include_in_memoir=1) grouped by scope.
    _src_stop: Dict[str, List[Dict[str, Any]]] = {}
    _src_region: Dict[str, List[Dict[str, Any]]] = {}
    _src_trip: List[Dict[str, Any]] = []
    for _s in sources_list(trip_id):
        if not _s.get("include_in_memoir"):
            continue
        _se = {"title": _s.get("title"), "summary": _s.get("summary"),
               "pasted_text": _s.get("pasted_text"), "link_url": _s.get("link_url"),
               "filename": _s.get("filename"), "source_type": _s.get("source_type")}
        _ssid, _srid = _s.get("trip_stop_id"), _s.get("trip_region_id")
        if _ssid:
            _src_stop.setdefault(_ssid, []).append(_se)
        elif _srid:
            _src_region.setdefault(_srid, []).append(_se)
        else:
            _src_trip.append(_se)

    def _stop_line(stop: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": stop.get("id"),
            "location_name": stop.get("location_name"),
            "title": stop.get("title"),
            "stop_type": stop.get("stop_type"),
            "date_start": stop.get("date_start"),
            "date_end": stop.get("date_end"),
            "notes": stop.get("notes"),
            "story_notes": _notes_stop.get(stop.get("id"), []),
            "sources": _src_stop.get(stop.get("id"), []),
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
            "story_notes": _notes_region.get(region.get("id"), []),
            "sources": _src_region.get(region.get("id"), []),
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
        "story_notes": _notes_trip,
        "sources": _src_trip,
        "part_one_journey_in_order": part_one,
        "part_two_themes": part_two,
        "part_three_photo_appendix": {
            "assigned_photos": total_photos,
            "unassigned_photos": tree.get("unassigned_photo_count", 0),
        },
    }


# ── Public context (WO-TRAVEL-DOC-EVIDENCE-RICH-TRAVELOGUE-01) ──────────────
#
# Web/public-derived evidence for the OPERATOR Travel Doc workspace
# (holidays, local events, museum/site background, food context, reverse-
# geocoded broad place names). Locked doctrine: labeled as public/draft
# until the operator confirms; never presented as personal memory.
# approved_for_lori / include_in_memoir DEFAULT OFF. Scope validation
# (trip-ownership of region/stop/photo-link ids) belongs to the router.

_PUBLIC_CONTEXT_SOURCE_TYPES = (
    "public_web_context", "reverse_geocode", "calendar_context",
    "food_context", "place_context",
)


def public_context_create(
    trip_id: str,
    result_summary: str,
    source_type: str = "public_web_context",
    trip_region_id: Optional[str] = None,
    trip_stop_id: Optional[str] = None,
    photo_link_id: Optional[str] = None,
    query: Optional[str] = None,
    source_url: Optional[str] = None,
    confidence: str = "draft",
    notes: Optional[str] = None,
    approved_for_lori: bool = False,
    include_in_memoir: bool = False,
    context_id: Optional[str] = None,
) -> str:
    if source_type not in _PUBLIC_CONTEXT_SOURCE_TYPES:
        source_type = "public_web_context"
    cid = context_id or _new_id()
    con = _connect()
    try:
        con.execute(
            """INSERT INTO trip_public_context
               (id, trip_id, trip_region_id, trip_stop_id, photo_link_id,
                query, source_type, source_url, result_summary, confidence,
                notes, approved_for_lori, include_in_memoir,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                cid, trip_id, trip_region_id, trip_stop_id, photo_link_id,
                query, source_type, source_url, result_summary,
                confidence or "draft", notes,
                1 if approved_for_lori else 0,
                1 if include_in_memoir else 0,
                _now(), _now(),
            ),
        )
        con.commit()
        return cid
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def public_context_list(trip_id: str) -> List[Dict[str, Any]]:
    """All public-context rows for a trip. Scope filtering is done by the
    caller. Tolerant of a pre-0026 DB (table missing) — returns []."""
    con = _connect()
    try:
        rows = con.execute(
            "SELECT * FROM trip_public_context WHERE trip_id = ? "
            "ORDER BY created_at, id",
            (trip_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()


def public_context_get(context_id: str) -> Optional[Dict[str, Any]]:
    con = _connect()
    try:
        row = con.execute(
            "SELECT * FROM trip_public_context WHERE id = ?", (context_id,),
        ).fetchone()
        return _row_to_dict(row) if row else None
    except sqlite3.OperationalError:
        return None
    finally:
        con.close()


def public_context_update(
    context_id: str,
    result_summary: Optional[str] = None,
    notes: Optional[str] = None,
    source_url: Optional[str] = None,
    query: Optional[str] = None,
    approved_for_lori: Optional[bool] = None,
    include_in_memoir: Optional[bool] = None,
) -> bool:
    """Partial update. Revoke-on-edit (mirrors photo_link_update caption
    semantics): editing result_summary REVOKES approved_for_lori unless
    the same request re-approves — approval always refers to the text
    the operator actually reviewed."""
    sets: List[str] = []
    args: List[Any] = []
    if result_summary is not None:
        sets.append("result_summary = ?"); args.append(result_summary)
        if approved_for_lori is None:
            sets.append("approved_for_lori = 0")
    if notes is not None:
        sets.append("notes = ?"); args.append(notes)
    if source_url is not None:
        sets.append("source_url = ?"); args.append(source_url)
    if query is not None:
        sets.append("query = ?"); args.append(query)
    if approved_for_lori is not None:
        sets.append("approved_for_lori = ?")
        args.append(1 if approved_for_lori else 0)
    if include_in_memoir is not None:
        sets.append("include_in_memoir = ?")
        args.append(1 if include_in_memoir else 0)
    if not sets:
        return False
    sets.append("updated_at = ?"); args.append(_now())
    args.append(context_id)
    con = _connect()
    try:
        cur = con.execute(
            f"UPDATE trip_public_context SET {', '.join(sets)} WHERE id = ?",
            args,
        )
        con.commit()
        return cur.rowcount > 0
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def public_context_delete(context_id: str) -> bool:
    con = _connect()
    try:
        cur = con.execute(
            "DELETE FROM trip_public_context WHERE id = ?", (context_id,),
        )
        con.commit()
        return cur.rowcount > 0
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def public_context_trip_id(context_id: str) -> Optional[str]:
    con = _connect()
    try:
        row = con.execute(
            "SELECT trip_id FROM trip_public_context WHERE id = ?",
            (context_id,),
        ).fetchone()
        return row["trip_id"] if row else None
    except sqlite3.OperationalError:
        return None
    finally:
        con.close()


def photo_raw_gps(photo_id: str):
    """SERVER-SIDE ONLY raw GPS read for the reverse-geocode lane.
    The returned coordinates are consumed by the local resolver and are
    NEVER serialized into any response, preview JSON, or Lori surface —
    only the resolved broad place label is stored (as draft public
    context). Returns (None, None) when absent."""
    con = _connect()
    try:
        row = con.execute(
            "SELECT latitude, longitude FROM photos WHERE id = ?",
            (photo_id,),
        ).fetchone()
        if not row:
            return (None, None)
        return (row["latitude"], row["longitude"])
    except sqlite3.OperationalError:
        return (None, None)
    finally:
        con.close()


# ── Trip days (WO-TRAVEL-DOC-UI-LAB-01 — Trip Calendar layer) ──────────────
#
# One editable row per calendar date inside the trip window. Generated
# idempotently from trips.start_date/end_date; the itinerary tree stays
# the route authority — day rows are the operator's memory-workflow
# surface (Trip Calendar day cards + day-detail inspector).


def _day_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    for key in ("places_visited_json", "meals_json"):
        if isinstance(d.get(key), str):
            try:
                d[key] = json.loads(d[key])
            except Exception:
                d[key] = []
    return d


def trip_days_list(trip_id: str) -> List[Dict[str, Any]]:
    """All day rows for a trip ordered by day_index. Tolerant of a
    pre-0027 DB — returns []."""
    con = _connect()
    try:
        rows = con.execute(
            "SELECT * FROM trip_days WHERE trip_id = ? "
            "ORDER BY day_index, date",
            (trip_id,),
        ).fetchall()
        return [_day_row_to_dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()


def trip_day_get(day_id: str) -> Optional[Dict[str, Any]]:
    con = _connect()
    try:
        row = con.execute(
            "SELECT * FROM trip_days WHERE id = ?", (day_id,),
        ).fetchone()
        return _day_row_to_dict(row) if row else None
    except sqlite3.OperationalError:
        return None
    finally:
        con.close()


def _covering_region_id(regions: List[Dict[str, Any]], date_str: str) -> Optional[str]:
    """Best-effort auto-link: return a region id only when EXACTLY ONE
    region's [start_date, end_date] range covers the date (ISO string
    compare on the date prefix). Ambiguity or no coverage -> None."""
    hits: List[str] = []
    for r in regions:
        rs = (r.get("start_date") or "")[:10]
        re_ = (r.get("end_date") or "")[:10]
        if rs and re_ and rs <= date_str <= re_:
            hits.append(str(r["id"]))
    return hits[0] if len(hits) == 1 else None


def trip_days_generate(trip_id: str) -> Dict[str, Any]:
    """Create one trip_days row per date in the trip's start/end window
    (inclusive), day_index 1..n. Idempotent: dates that already have a
    row are SKIPPED (existing operator edits are never overwritten).
    Auto-fills trip_region_id when exactly one region's date range
    covers the date. Raises ValueError when the trip has no parseable
    start/end dates or end < start."""
    from datetime import date as _date, timedelta as _timedelta

    trip = trip_get(trip_id)
    if not trip:
        raise ValueError("trip not found")
    start_raw = (trip.get("start_date") or "")[:10]
    end_raw = (trip.get("end_date") or "")[:10]
    if not start_raw or not end_raw:
        raise ValueError("trip needs both start_date and end_date "
                         "to generate day cards")
    try:
        start = _date.fromisoformat(start_raw)
        end = _date.fromisoformat(end_raw)
    except ValueError:
        raise ValueError("trip dates are not valid ISO dates")
    if end < start:
        raise ValueError("trip end_date is before start_date")
    if (end - start).days > 400:
        raise ValueError("trip window too large to generate day cards")

    tree = trip_tree(trip_id) or {}
    regions = tree.get("regions", [])

    con = _connect()
    try:
        existing = {
            str(r["date"])[:10]
            for r in con.execute(
                "SELECT date FROM trip_days WHERE trip_id = ?",
                (trip_id,),
            ).fetchall()
        }
        created = 0
        cur_date = start
        idx = 0
        while cur_date <= end:
            idx += 1
            iso = cur_date.isoformat()
            if iso not in existing:
                con.execute(
                    """INSERT INTO trip_days
                       (id, trip_id, day_index, date, trip_region_id,
                        places_visited_json, meals_json,
                        created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, '[]', '[]', ?, ?)""",
                    (
                        _new_id(), trip_id, idx, iso,
                        _covering_region_id(regions, iso),
                        _now(), _now(),
                    ),
                )
                created += 1
            cur_date = cur_date + _timedelta(days=1)
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

    total = len(trip_days_list(trip_id))
    return {"created": created, "total": total}


def trip_day_update(
    day_id: str,
    title: Optional[str] = None,
    main_location: Optional[str] = None,
    lodging_base: Optional[str] = None,
    trip_region_id: Optional[str] = None,
    trip_stop_id: Optional[str] = None,
    morning_notes: Optional[str] = None,
    afternoon_notes: Optional[str] = None,
    evening_notes: Optional[str] = None,
    places_visited: Optional[List[str]] = None,
    meals: Optional[List[str]] = None,
    clear_title: bool = False,
    clear_main_location: bool = False,
    clear_lodging_base: bool = False,
    clear_morning_notes: bool = False,
    clear_afternoon_notes: bool = False,
    clear_evening_notes: bool = False,
    clear_region: bool = False,
    clear_stop: bool = False,
) -> bool:
    """Partial day update — None means unchanged; the matching clear_*
    flag NULLs a field (same posture as trip_update/stop_update).
    List fields replace wholesale when given."""
    sets: List[str] = []
    args: List[Any] = []
    text_fields = (
        ("title", title, clear_title),
        ("main_location", main_location, clear_main_location),
        ("lodging_base", lodging_base, clear_lodging_base),
        ("morning_notes", morning_notes, clear_morning_notes),
        ("afternoon_notes", afternoon_notes, clear_afternoon_notes),
        ("evening_notes", evening_notes, clear_evening_notes),
    )
    for col, value, clear in text_fields:
        if clear:
            sets.append(f"{col} = NULL")
        elif value is not None:
            sets.append(f"{col} = ?"); args.append(value)
    if clear_region:
        sets.append("trip_region_id = NULL")
    elif trip_region_id is not None:
        sets.append("trip_region_id = ?"); args.append(trip_region_id)
    if clear_stop:
        sets.append("trip_stop_id = NULL")
    elif trip_stop_id is not None:
        sets.append("trip_stop_id = ?"); args.append(trip_stop_id)
    if places_visited is not None:
        sets.append("places_visited_json = ?")
        args.append(json.dumps([str(p) for p in places_visited],
                               ensure_ascii=False))
    if meals is not None:
        sets.append("meals_json = ?")
        args.append(json.dumps([str(m) for m in meals], ensure_ascii=False))
    if not sets:
        return False
    sets.append("updated_at = ?"); args.append(_now())
    args.append(day_id)
    con = _connect()
    try:
        cur = con.execute(
            f"UPDATE trip_days SET {', '.join(sets)} WHERE id = ?", args,
        )
        con.commit()
        return cur.rowcount > 0
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def photo_links_set_day(
    link_ids: List[str],
    day_id: Optional[str],
    trip_id: str,
) -> int:
    """Attach (or detach, day_id=None) trip photo links to a day card
    (WO-TRAVEL-DOC-UI-LAB-02). Validates that the day AND every link
    belong to ``trip_id`` — cross-trip ids raise ValueError and nothing
    is written (one transaction). Returns the number of links updated."""
    ids = [str(l) for l in (link_ids or []) if l]
    if not ids:
        return 0
    if day_id:
        day = trip_day_get(day_id)
        if not day or day.get("trip_id") != trip_id:
            raise ValueError("day not in this trip")
    con = _connect()
    try:
        for lid in ids:
            row = con.execute(
                "SELECT trip_id FROM trip_photo_links WHERE id = ?",
                (lid,),
            ).fetchone()
            if not row or row["trip_id"] != trip_id:
                raise ValueError("photo link not in this trip: %s" % lid)
        updated = 0
        for lid in ids:
            cur = con.execute(
                "UPDATE trip_photo_links SET trip_day_id = ?, "
                "updated_at = ? WHERE id = ?",
                (day_id, _now(), lid),
            )
            updated += cur.rowcount
        con.commit()
        return updated
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def trip_day_counts(trip_id: str) -> Dict[str, Dict[str, int]]:
    """Honest per-day evidence counts keyed by day id.

    - photos: links attached to the day (trip_day_id, migration 0028)
      count on THAT day first; links without a day attachment fall back
      to the taken-date match (COALESCE(link.taken_at, photos.date_value)
      date prefix). Undated, unattached links count nowhere.
    - notes: rows attached to the day (trip_day_id) count on that day;
      unattached rows count only via the day's linked stop/region scope.
    - sources: rows attached to the day (trip_sources.trip_day_id,
      migration 0029) count on THAT day first; un-day-linked rows keep
      the stop/region-scope fallback. Never double-counted — the scope
      fallback skips any row that carries a trip_day_id.
    - public_context: NOT date- or day-scoped in schema, so a row counts
      for a day ONLY when its scope link (trip_stop_id, else
      trip_region_id) equals the day's linked stop/region. Days with no
      link get 0 — no fake numbers.
    """
    days = trip_days_list(trip_id)
    if not days:
        return {}

    # Photo counts: day-attached links first (0028), then date-prefix
    # fallback for unattached links only.
    by_date: Dict[str, int] = {}
    by_day: Dict[str, int] = {}
    con = _connect()
    try:
        try:
            rows = con.execute(
                """SELECT l.trip_day_id AS d, COUNT(*) AS n
                   FROM trip_photo_links l
                   LEFT JOIN photos p ON p.id = l.photo_id
                   WHERE l.trip_id = ?
                     AND l.trip_day_id IS NOT NULL
                     AND (p.id IS NULL OR p.deleted_at IS NULL)
                   GROUP BY l.trip_day_id""",
                (trip_id,),
            ).fetchall()
            by_day = {str(r["d"]): int(r["n"]) for r in rows if r["d"]}
            rows = con.execute(
                """SELECT substr(COALESCE(l.taken_at, p.date_value), 1, 10)
                          AS d, COUNT(*) AS n
                   FROM trip_photo_links l
                   LEFT JOIN photos p ON p.id = l.photo_id
                   WHERE l.trip_id = ?
                     AND l.trip_day_id IS NULL
                     AND (p.id IS NULL OR p.deleted_at IS NULL)
                     AND COALESCE(l.taken_at, p.date_value) IS NOT NULL
                   GROUP BY d""",
                (trip_id,),
            ).fetchall()
            by_date = {str(r["d"]): int(r["n"]) for r in rows if r["d"]}
        except sqlite3.OperationalError:
            # Pre-0028 DB: no trip_day_id column — date match only.
            by_day = {}
            try:
                rows = con.execute(
                    """SELECT substr(COALESCE(l.taken_at, p.date_value), 1, 10)
                              AS d, COUNT(*) AS n
                       FROM trip_photo_links l
                       LEFT JOIN photos p ON p.id = l.photo_id
                       WHERE l.trip_id = ?
                         AND (p.id IS NULL OR p.deleted_at IS NULL)
                         AND COALESCE(l.taken_at, p.date_value) IS NOT NULL
                       GROUP BY d""",
                    (trip_id,),
                ).fetchall()
                by_date = {str(r["d"]): int(r["n"]) for r in rows if r["d"]}
            except sqlite3.OperationalError:
                by_date = {}
    finally:
        con.close()

    notes = location_notes_list(trip_id)
    sources = sources_list(trip_id)
    pub = public_context_list(trip_id)

    def _scoped_count(rows: List[Dict[str, Any]], day: Dict[str, Any]) -> int:
        stop_id = day.get("trip_stop_id")
        region_id = day.get("trip_region_id")
        if stop_id:
            return sum(1 for r in rows if r.get("trip_stop_id") == stop_id
                       and not r.get("trip_day_id"))
        if region_id:
            return sum(1 for r in rows
                       if r.get("trip_region_id") == region_id
                       and not r.get("trip_stop_id")
                       and not r.get("trip_day_id"))
        return 0

    def _day_attached_count(rows: List[Dict[str, Any]],
                            day: Dict[str, Any]) -> int:
        did = str(day.get("id"))
        return sum(1 for r in rows
                   if str(r.get("trip_day_id") or "") == did)

    out: Dict[str, Dict[str, int]] = {}
    for day in days:
        out[str(day["id"])] = {
            "photos": by_day.get(str(day["id"]), 0)
            + by_date.get(str(day.get("date") or "")[:10], 0),
            "notes": _day_attached_count(notes, day)
            + _scoped_count(notes, day),
            "sources": _day_attached_count(sources, day)
            + _scoped_count(sources, day),
            "public_context": _scoped_count(pub, day),
        }
    return out



# ── Trip-day date-range reconcile (WO-TRAVEL-DOC-UI-LAB-03) ────────────────
#
# When trip start/end dates change AFTER day cards exist, generation only
# appends missing dates — it never deletes operator work. The reconcile
# pair below makes that state visible and operator-resolvable:
#   * preview — read-only diff of the trip window vs. existing day rows.
#   * reconcile — add ONLY missing in-range days and/or acknowledge
#     out-of-range days (reconcile_status, migration 0029). NOTHING is
#     ever deleted; out-of-range day cards are kept to protect notes.

RECONCILE_STATUS_ACTIVE = "active"
RECONCILE_STATUS_OUT_OF_RANGE_ACK = "out_of_range_acknowledged"


def _parse_iso_date(value):
    from datetime import date as _date

    raw = (value or "")[:10]
    if not raw:
        return None
    try:
        return _date.fromisoformat(raw)
    except ValueError:
        return None


def trip_days_reconcile_preview(trip_id: str) -> Dict[str, Any]:
    """READ-ONLY diff between the trip's start/end window and its
    existing trip_days rows. No writes of any kind.

    Returns {trip_id, trip_start_date, trip_end_date, existing_days,
    missing_dates, out_of_range_days, duplicate_or_invalid_days}.
    When the trip has no usable date window, missing_dates and
    out_of_range_days are [] (no window means nothing can honestly be
    called missing or out of range)."""
    from datetime import timedelta as _timedelta

    trip = trip_get(trip_id)
    if not trip:
        raise ValueError("trip not found")
    start_raw = (trip.get("start_date") or "")[:10]
    end_raw = (trip.get("end_date") or "")[:10]
    start = _parse_iso_date(start_raw)
    end = _parse_iso_date(end_raw)
    window_ok = bool(start and end and start <= end
                     and (end - start).days <= 400)

    days = trip_days_list(trip_id)
    seen_dates: set = set()
    duplicate_or_invalid: List[Dict[str, Any]] = []
    out_of_range: List[Dict[str, Any]] = []
    for d in days:
        pd = _parse_iso_date(d.get("date"))
        if pd is None:
            duplicate_or_invalid.append(d)
            continue
        iso = pd.isoformat()
        if iso in seen_dates:
            # UNIQUE(trip_id, date) should make this unreachable for
            # byte-identical dates; defensive for prefix collisions.
            duplicate_or_invalid.append(d)
        seen_dates.add(iso)
        if window_ok and not (start <= pd <= end):
            out_of_range.append(d)

    missing: List[str] = []
    if window_ok:
        cur = start
        while cur <= end:
            iso = cur.isoformat()
            if iso not in seen_dates:
                missing.append(iso)
            cur = cur + _timedelta(days=1)

    return {
        "trip_id": trip_id,
        "trip_start_date": start_raw or None,
        "trip_end_date": end_raw or None,
        "existing_days": len(days),
        "missing_dates": missing,
        "out_of_range_days": out_of_range,
        "duplicate_or_invalid_days": duplicate_or_invalid,
    }


def trip_days_reconcile(
    trip_id: str,
    add_missing: bool = False,
    mark_out_of_range: bool = False,
) -> Dict[str, Any]:
    """Apply the operator-requested reconcile actions.

    * ``add_missing`` creates ONLY the missing in-range day rows — it
      delegates to trip_days_generate, which skips every existing date,
      so operator-edited day cards are never overwritten.
    * ``mark_out_of_range`` stamps reconcile_status =
      'out_of_range_acknowledged' on out-of-range day rows, and resets
      in-range rows that were previously acknowledged back to 'active'
      (honest status when trip dates change again).

    NOTHING is ever deleted here — out-of-range day cards are kept to
    protect the operator's notes."""
    preview = trip_days_reconcile_preview(trip_id)
    added = 0
    if add_missing and preview["missing_dates"]:
        added = trip_days_generate(trip_id)["created"]

    marked = 0
    reactivated = 0
    if mark_out_of_range:
        trip = trip_get(trip_id) or {}
        start = _parse_iso_date(trip.get("start_date"))
        end = _parse_iso_date(trip.get("end_date"))
        window_ok = bool(start and end and start <= end
                         and (end - start).days <= 400)
        out_ids = {str(d["id"]) for d in preview["out_of_range_days"]}
        con = _connect()
        try:
            for did in out_ids:
                cur = con.execute(
                    "UPDATE trip_days SET reconcile_status = ?, "
                    "updated_at = ? WHERE id = ? AND reconcile_status != ?",
                    (RECONCILE_STATUS_OUT_OF_RANGE_ACK, _now(), did,
                     RECONCILE_STATUS_OUT_OF_RANGE_ACK),
                )
                marked += cur.rowcount
            if window_ok:
                for d in trip_days_list(trip_id):
                    did = str(d["id"])
                    if did in out_ids:
                        continue
                    pd = _parse_iso_date(d.get("date"))
                    if pd is None or not (start <= pd <= end):
                        continue
                    if d.get("reconcile_status") == \
                            RECONCILE_STATUS_OUT_OF_RANGE_ACK:
                        cur = con.execute(
                            "UPDATE trip_days SET reconcile_status = ?, "
                            "updated_at = ? WHERE id = ?",
                            (RECONCILE_STATUS_ACTIVE, _now(), did),
                        )
                        reactivated += cur.rowcount
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    return {
        "trip_id": trip_id,
        "added": added,
        "marked_out_of_range": marked,
        "reactivated": reactivated,
        "preview": trip_days_reconcile_preview(trip_id),
    }
