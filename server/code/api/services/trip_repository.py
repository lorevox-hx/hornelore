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


def region_delete(region_id: str) -> bool:
    """Delete a region and its stops (FK cascade)."""
    con = _connect()
    try:
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


def narrator_photo_links(trip_id: str) -> List[Dict[str, Any]]:
    """Narrator-safe link read — BUG-TRAVELS-PHOTO-STRIP-LEAKS-NON-
    NARRATOR-READY-PHOTOS-01: the Travels shelf strip must only show
    photos the narrator is cleared to see (BUG-238 rule: unvetted
    intake photos never reach narrator-visible surfaces). Joins photos
    and filters narrator_ready=1 + not deleted. The operator Trip Tab
    keeps the unfiltered photo_links_list."""
    con = _connect()
    try:
        rows = con.execute(
            """SELECT l.* FROM trip_photo_links l
               JOIN photos p ON p.id = l.photo_id
               WHERE l.trip_id = ?
                 AND p.narrator_ready = 1
                 AND p.deleted_at IS NULL
               ORDER BY l.taken_at, l.ord""",
            (trip_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
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
    trip_region_id: Optional[str] = None,
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
                       s.location_name AS stop_location_name
                FROM trip_photo_links l
                JOIN photos p ON p.id = l.photo_id
                LEFT JOIN trip_stops s ON s.id = l.trip_stop_id
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
