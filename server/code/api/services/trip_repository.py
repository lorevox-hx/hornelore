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


# WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01: tables whose PRAGMA lookups are
# legal for _table_has_column. Table names are interpolated into PRAGMA
# statements, so they are locked to this internal allowlist — never a
# caller-supplied string (parameterized-SQL doctrine; PRAGMA cannot take
# a bound parameter for the table name).
# WO-LIVE-TRIP-COMPANION-01 (2026-07-30): "trips" joined this list when
# migration 0039 added trips.live_state. The same tolerance argument that
# put the other three here applies with more force: _trips_has_live_state
# is probed on every completed interview turn, so an unmigrated database
# must answer "no live state" and let the conversation finish, not raise.
_KNOWN_TABLES = (
    "trip_location_notes", "trip_sources", "trip_photo_links",
    "trips",
    # WO-TRAVEL-DOC-CLOSEOUT-01: probed for include_in_memoir, which
    # arrives in migration 0042. day_projection has to answer
    # "unsupported" on a pre-0042 database rather than "0 days
    # approved" -- those are different facts and one of them would
    # send the operator hunting for a tick they cannot yet make.
    "trip_days",
)


def _table_has_column(con: sqlite3.Connection, table: str,
                      column: str) -> bool:
    """True when ``table`` exists on this DB and carries ``column``.

    WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01: the hidden/hidden_at columns
    land via migration 0036; reads must degrade gracefully on a DB that
    has not applied it yet (same tolerance posture as the pre-0022 /
    pre-0028 fallbacks elsewhere in this file), and a PRAGMA probe is
    more honest than parsing exception messages. ``table`` must be in
    _KNOWN_TABLES (fail-loud on programmer error)."""
    if table not in _KNOWN_TABLES:
        raise ValueError("unknown table for column probe: %r" % table)
    try:
        rows = con.execute("PRAGMA table_info(%s)" % table).fetchall()
    except sqlite3.OperationalError:
        return False
    return any(r["name"] == column for r in rows)


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


def region_get(region_id: str) -> Optional[Dict[str, Any]]:
    """Single region row. Added 2026-07-11 for the preflight lookup-
    query builder (needs region title to add safe structural context to
    a public query). Mirrors stop_get."""
    con = _connect()
    try:
        row = con.execute(
            "SELECT * FROM trip_regions WHERE id = ?", (region_id,),
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


def location_notes_list(trip_id: str,
                        include_hidden: bool = False) -> List[Dict[str, Any]]:
    """All notes for a trip, ordered. Scope filtering (trip/region/stop)
    is done by the caller so one read serves the UI and the memoir.
    Tolerant of a pre-0019 DB (old table shape / missing) — returns [].

    WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01: hidden=1 rows are EXCLUDED by
    default, which makes every consumer of this read (travelogue
    builder, Draft Assistant, narrator interview context, memoir
    preview, story capture, day counts, list endpoints) hide-aware in
    one place. ``include_hidden=True`` is the operator-review escape
    hatch (?include_hidden=1 on the list endpoint); rows carry their
    hidden/hidden_at fields either way (SELECT *)."""
    con = _connect()
    try:
        hidden_where = ("" if include_hidden
                        or not _table_has_column(
                            con, "trip_location_notes", "hidden")
                        else "AND hidden = 0 ")
        rows = con.execute(
            "SELECT * FROM trip_location_notes WHERE trip_id = ? "
            + hidden_where +
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
    hidden: Optional[bool] = None,
) -> bool:
    """Partial update. Text fields: None = unchanged. Booleans: None =
    unchanged, else written. clear_title NULLs the title.

    WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01: ``hidden=True`` stamps
    hidden=1 + hidden_at=<now>; ``hidden=False`` restores (hidden=0,
    hidden_at NULL). Hiding NEVER touches the promotion/approval flags
    — provenance and the operator's promotion work survive a
    hide/restore round-trip intact."""
    sets: List[str] = []
    args: List[Any] = []
    if hidden is not None:
        if hidden:
            sets.append("hidden = 1")
            sets.append("hidden_at = ?"); args.append(_now())
        else:
            sets.append("hidden = 0")
            sets.append("hidden_at = NULL")
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


# ── Captured-note review feed (WO-POST-LORI-CLEANUP-AND-UNBLOCK-01) ───

# Lane 3. The per-trip note list already exists and the "In memoir"
# toggle already works -- what did not exist was a way to FIND a
# captured note. trip_location_notes rows written by the Travel Doc
# modal capture path (source_surface='travel_doc_modal') land under
# whichever trip/region/stop/day scope the operator happened to be in,
# so the only way to see them was to already know where to look. Every
# one of the 12 rows on the live DB sat at include_in_memoir=0, which
# is the correct default -- but it also meant the memoir trip lane
# shipped by WO-MEMOIR-TRIP-STORY-LANE-01 could never produce output.
#
# This is a READ. It creates no new write path: promotion still goes
# through PATCH /api/trips/location-notes/{id}, the same endpoint the
# per-trip Story Notes list has always used, with the same validation.
# It does not auto-promote anything and it does not change the
# include_in_memoir=0 default. It does not touch the archive: these
# rows are trip material and the two-surface rule of 2026-07-09 is
# unaffected by reading them.
#
# Tolerant of a pre-0036 DB (no hidden/hidden_at) and of a pre-0031 DB
# (no source_surface) for the same reason location_notes_list is: a
# review feed that raises on an un-migrated DB is worse than one that
# returns fewer columns.

_CAPTURED_NOTE_BASE_COLS = (
    "n.id AS id",
    "n.trip_id AS trip_id",
    "n.trip_region_id AS trip_region_id",
    "n.trip_stop_id AS trip_stop_id",
    "n.trip_day_id AS trip_day_id",
    "n.note_title AS note_title",
    "n.note_text AS note_text",
    "n.source_type AS source_type",
    "n.source_ref AS source_ref",
    "n.include_in_memoir AS include_in_memoir",
    "n.include_in_interview_context AS include_in_interview_context",
    "n.created_at AS created_at",
    "n.updated_at AS updated_at",
    "t.title AS trip_title",
    "t.start_date AS trip_start_date",
    "t.person_id AS person_id",
    "r.title AS region_title",
    "s.title AS stop_title",
    "s.location_name AS stop_location_name",
)


def captured_notes_review_list(
    person_id: Optional[str] = None,
    source_surface: Optional[str] = None,
    include_hidden: bool = False,
    promoted: Optional[bool] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """Cross-trip review feed of story notes, newest first.

    ``person_id``      restrict to one narrator's trips (recommended).
    ``source_surface`` exact match, e.g. 'travel_doc_modal'. None = any,
                       including the NULL-surface rows written before
                       the column existed.
    ``include_hidden`` False (default) excludes hidden=1 rows, matching
                       location_notes_list and the memoir lane.
    ``promoted``       True = only include_in_memoir=1, False = only 0,
                       None = both.
    ``limit``          hard cap, clamped to 1..1000.

    Never raises on a shape problem -- returns [] so an operator review
    screen degrades to empty rather than 500-ing.
    """
    try:
        lim = int(limit)
    except (TypeError, ValueError):
        lim = 200
    lim = max(1, min(1000, lim))

    con = _connect()
    try:
        has_hidden = _table_has_column(con, "trip_location_notes", "hidden")
        has_surface = _table_has_column(
            con, "trip_location_notes", "source_surface")

        cols = list(_CAPTURED_NOTE_BASE_COLS)
        if has_surface:
            cols.append("n.source_surface AS source_surface")
            cols.append("n.source_turn_ref AS source_turn_ref")
        if has_hidden:
            cols.append("n.hidden AS hidden")
            cols.append("n.hidden_at AS hidden_at")

        where = []
        args: List[Any] = []
        if person_id:
            where.append("t.person_id = ?")
            args.append(person_id)
        if source_surface is not None:
            if not has_surface:
                return []      # cannot honour the filter -> honest empty
            where.append("n.source_surface = ?")
            args.append(source_surface)
        if promoted is not None:
            where.append("n.include_in_memoir = ?")
            args.append(1 if promoted else 0)
        if has_hidden and not include_hidden:
            where.append("n.hidden = 0")

        sql = (
            "SELECT " + ", ".join(cols) + " "
            "FROM trip_location_notes n "
            "JOIN trips t ON t.id = n.trip_id "
            "LEFT JOIN trip_regions r ON r.id = n.trip_region_id "
            "LEFT JOIN trip_stops s ON s.id = n.trip_stop_id "
            + (("WHERE " + " AND ".join(where) + " ") if where else "")
            + "ORDER BY n.created_at DESC, n.id DESC LIMIT ?"
        )
        args.append(lim)
        rows = con.execute(sql, args).fetchall()
        out = [_row_to_dict(r) for r in rows]
        for d in out:
            d["include_in_memoir"] = bool(d.get("include_in_memoir"))
            d["include_in_interview_context"] = bool(
                d.get("include_in_interview_context"))
            if "hidden" in d:
                d["hidden"] = bool(d.get("hidden"))
            else:
                d["hidden"] = False
            d.setdefault("source_surface", None)
        return out
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()


def captured_notes_review_counts(
    person_id: Optional[str] = None,
) -> Dict[str, int]:
    """Counter strip for the review screen. Same tolerance posture."""
    rows = captured_notes_review_list(
        person_id=person_id, include_hidden=True, limit=1000)
    out = {
        "total": 0, "promoted": 0, "unpromoted": 0,
        "hidden": 0, "travel_doc_modal": 0,
    }
    for r in rows:
        if r.get("hidden"):
            out["hidden"] += 1
            continue
        out["total"] += 1
        if r.get("include_in_memoir"):
            out["promoted"] += 1
        else:
            out["unpromoted"] += 1
        if r.get("source_surface") == "travel_doc_modal":
            out["travel_doc_modal"] += 1
    return out


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
                 day_id: Optional[str] = None,
                 include_hidden: bool = False) -> List[Dict[str, Any]]:
    """Tolerant of a pre-0020 DB (trip_sources missing) — returns [].
    ``day_id`` narrows to sources attached to that day card
    (trip_sources.trip_day_id, migration 0029).

    WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01: hidden=1 rows are excluded by
    default (hide-aware in one place for every consumer);
    ``include_hidden=True`` is the operator-review escape hatch. Rows
    carry hidden/hidden_at either way (SELECT *)."""
    con = _connect()
    try:
        hidden_where = ("" if include_hidden
                        or not _table_has_column(con, "trip_sources", "hidden")
                        else "AND hidden = 0 ")
        rows = con.execute(
            "SELECT * FROM trip_sources WHERE trip_id = ? "
            + hidden_where + "ORDER BY ord, created_at",
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
    hidden: Optional[bool] = None,
) -> bool:
    """Partial update. ``trip_day_id`` attaches (or moves) the source to
    a day card; ``clear_day`` detaches it (NULLs trip_day_id ONLY — the
    source row itself is never deleted by an unlink).

    WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01: ``hidden=True`` stamps
    hidden=1 + hidden_at=<now>; ``hidden=False`` restores. Hiding never
    touches include_in_memoir or storage_path — a restore returns the
    source to exactly its prior standing, file intact."""
    sets: List[str] = []
    args: List[Any] = []
    if hidden is not None:
        if hidden:
            sets.append("hidden = 1")
            sets.append("hidden_at = ?"); args.append(_now())
        else:
            sets.append("hidden = 0")
            sets.append("hidden_at = NULL")
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
    instead of SELECT l.*.

    WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01: hidden=1 links are ALWAYS
    excluded here — there is no include_hidden escape hatch on the
    narrator surface. A hidden photo link (and, transitively, its
    captions and approved photo-context rows) never reaches Lori."""
    con = _connect()
    try:
        hidden_where = ("   AND l.hidden = 0 "
                        if _table_has_column(con, "trip_photo_links", "hidden")
                        else "")
        where = (
            " FROM trip_photo_links l "
            " JOIN photos p ON p.id = l.photo_id "
            " WHERE l.trip_id = ? "
            "   AND p.narrator_ready = 1 "
            "   AND p.deleted_at IS NULL "
            + hidden_where +
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


def trip_photo_inventory(trip_id: str) -> Dict[str, int]:
    """COUNTS ONLY. Never text.

    WO-TRIP-NARRATOR-BRIDGE-01. The narrator asked "can you see any of
    the photos I added to my trip?" and Lori answered with a
    continuation question, because nothing in her context said a photo
    existed at all. The obvious fix -- count what narrator_photo_links
    returns -- is a trap. That read is the CLEARED set: it filters
    narrator_ready = 1, and on the live trip that raised the question
    both attached photos were uncleared, so the count would have been
    zero while the narrator sat looking at two. Turning a dodge into a
    confident false denial is worse than the dodge.

    So: attached, placed on a day, and cleared for Lori are THREE
    SEPARATE FACTS, and this returns all three separately. Nothing here
    may collapse them into one number, because the answer built on top
    has to be able to say "they are attached, and I cannot use them
    yet", which is the true state and is not expressible in one count.

    Returns ints and nothing else BY CONSTRUCTION: no column in this
    query can carry a caption, a filename, a path, a coordinate or an
    operator's words, so no later caller can leak one through it.
    Hidden links and deleted photos are outside every count -- a hidden
    link is not attached as far as any narrator-facing surface goes.
    """
    con = _connect()
    try:
        has_hidden = _table_has_column(con, "trip_photo_links", "hidden")
        has_day = _table_has_column(con, "trip_photo_links", "trip_day_id")
        day_expr = ("SUM(CASE WHEN l.trip_day_id IS NOT NULL THEN 1 ELSE 0 END)"
                    if has_day else "0")
        row = con.execute(
            "SELECT COUNT(*), " + day_expr + ", "
            "       SUM(CASE WHEN p.narrator_ready = 1 THEN 1 ELSE 0 END) "
            "  FROM trip_photo_links l "
            "  JOIN photos p ON p.id = l.photo_id "
            " WHERE l.trip_id = ? "
            "   AND p.deleted_at IS NULL "
            + ("   AND l.hidden = 0 " if has_hidden else ""),
            (trip_id,),
        ).fetchone()
        return {
            "attached": int((row[0] if row else 0) or 0),
            "on_a_day": int((row[1] if row else 0) or 0),
            "cleared_for_lori": int((row[2] if row else 0) or 0),
        }
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

# 2026-07-11 repo-review HIGH fix — trip_photo_links columns EXCLUDING
# raw latitude / longitude. Prior to this, photo_links_list used
# `SELECT l.*` which projected raw GPS coordinates all the way to
# GET /api/trips/{trip_id}/photo-links. CLAUDE.md doctrine
# ("raw lat/lon deliberately not projected; link_gps_present BOOLEAN
# only" — Ph1 metadata_trust decision, 2026-07-05) said this must
# never happen. Explicit column list closes the leak. A boolean
# `link_gps_present` is added so operators can still see "this photo
# link has GPS" without the actual values leaving the DB.
_PHOTO_LINK_SAFE_COLS = (
    "l.id, l.trip_id, l.trip_region_id, l.trip_stop_id, l.photo_id, "
    "l.ord, l.taken_at, "
    "l.assignment_method, l.cluster_confidence, "
    "l.caption, l.narrator_caption, l.include_in_memoir, "
    "l.thematic_tags_json, l.created_at, l.updated_at, "
    "l.caption_approved_for_lori, l.operator_context_note, "
    "l.operator_context_approved_for_lori, l.trip_day_id, "
    "(l.latitude IS NOT NULL AND l.longitude IS NOT NULL) "
    "AS link_gps_present"
)


def photo_links_list(
    trip_id: str,
    max_confidence: Optional[float] = None,
    include_hidden: bool = False,
) -> List[Dict[str, Any]]:
    """WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01: hidden=1 links are excluded
    by default so every consumer (travelogue builder, modal, lookup
    query builder, photos router) is hide-aware in one place;
    ``include_hidden=True`` is the operator-review escape hatch. Rows
    project their hidden/hidden_at fields either way (post-0036)."""
    con = _connect()
    try:
        _has_hidden = _table_has_column(con, "trip_photo_links", "hidden")
        hidden_cols = ", l.hidden, l.hidden_at" if _has_hidden else ""
        hidden_where = ("" if include_hidden or not _has_hidden
                        else "AND l.hidden = 0 ")

        def _run(cols, safe_link_cols=_PHOTO_LINK_SAFE_COLS):
            base = ("SELECT " + safe_link_cols + hidden_cols + cols +
                    " FROM trip_photo_links l "
                    "LEFT JOIN photos p ON p.id = l.photo_id "
                    "WHERE l.trip_id = ? " + hidden_where)
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
            # *_approved_for_lori flags). Degrade to the safe link cols
            # instead of 500ing — the operator loses the review
            # annotations for this read, not the whole list. A second
            # fallback drops the newest link-side columns (0022/0028)
            # for very old DBs.
            try:
                rows = _run("")
            except sqlite3.OperationalError:
                _LEGACY_LINK_COLS = (
                    "l.id, l.trip_id, l.trip_region_id, l.trip_stop_id, "
                    "l.photo_id, l.ord, l.taken_at, l.assignment_method, "
                    "l.cluster_confidence, l.caption, l.narrator_caption, "
                    "l.include_in_memoir, l.thematic_tags_json, "
                    "l.created_at, l.updated_at, "
                    "(l.latitude IS NOT NULL AND l.longitude IS NOT NULL) "
                    "AS link_gps_present"
                )
                rows = _run("", safe_link_cols=_LEGACY_LINK_COLS)
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
    hidden: Optional[bool] = None,
) -> bool:
    """Operator review action. ``confirm=True`` stamps the link as
    operator truth (method='operator', confidence=1.0) so re-clustering
    never overwrites it. BUG-TRIP-PHOTO-LINK-REGION-STOP-DESYNC-01:
    when a photo moves to a stop in another region, callers must pass
    the stop's region so the pair stays consistent.

    WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01: ``hidden=True`` stamps
    hidden=1 + hidden_at=<now>; ``hidden=False`` restores. Hiding never
    touches placement, captions, or the approval flags."""
    sets: List[str] = []
    args: List[Any] = []
    if hidden is not None:
        if hidden:
            sets.append("hidden = 1")
            sets.append("hidden_at = ?"); args.append(_now())
        else:
            sets.append("hidden = 0")
            sets.append("hidden_at = NULL")
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
    not ownership.

    WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01: the DELETE /api/trips/{id}
    endpoint no longer calls this directly — it goes through
    trip_delete_impact (impact review + force gate + audit). This
    helper remains for internal/test callers that already own the
    decision."""
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


# ── Destructive-trip controls (WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01 Ph2) ────
#
# A trip delete is only "cheap" when the trip is empty. Once evidence
# hangs off it (regions/stops/days/photo links/notes/sources/story
# links/public+photo context/bio suggestions), the FK cascade is a
# destructive, unrecoverable operation on irreplaceable family material.
# The endpoint therefore:
#   * computes dependent counts INSIDE the delete transaction,
#   * refuses (409) when any count is nonzero and force was not given,
#   * requires an exact confirm_trip_id echo for force (422 otherwise —
#     defeats stale UI selection),
#   * appends an append-only audit row (narrator_delete_audit, action
#     'trip_force_delete') in the SAME transaction as the cascade, so a
#     partial failure rolls back BOTH the delete and the audit claim.

# Response-key -> table map for the dependent counts. Table names are a
# fixed internal allowlist (interpolated into COUNT(*) SQL — never
# caller-supplied). trip_themes is intentionally NOT counted: the
# work-order contract keys the gate on evidence lanes; themes are
# lightweight labels and keep the pre-existing empty-trip semantics.
_TRIP_DEPENDENT_TABLES = (
    ("regions", "trip_regions"),
    ("stops", "trip_stops"),
    ("days", "trip_days"),
    ("photo_links", "trip_photo_links"),
    ("notes", "trip_location_notes"),
    ("sources", "trip_sources"),
    ("story_links", "trip_story_links"),
    ("public_context", "trip_public_context"),
    ("photo_context", "trip_photo_context"),
    ("bio_suggestions", "trip_bio_suggestions"),
)

# Test seam (WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01): invoked with
# (con, trip_id) AFTER the audit append + cascade delete but BEFORE
# commit. Tests monkeypatch this to raise and prove the whole
# transaction — audit row included — rolls back atomically. Always None
# in production.
_TRIP_FORCE_DELETE_PRECOMMIT_HOOK = None


def _trip_dependent_counts(con: sqlite3.Connection,
                           trip_id: str) -> Dict[str, int]:
    """Dependent-row counts for one trip, read on the CALLER's
    connection (so trip_delete_impact counts inside its own
    transaction). A table missing on an old DB counts as 0 — nothing
    that doesn't exist needs protecting."""
    counts: Dict[str, int] = {}
    for key, table in _TRIP_DEPENDENT_TABLES:
        try:
            n = con.execute(
                "SELECT COUNT(*) FROM %s WHERE trip_id = ?" % table,
                (trip_id,),
            ).fetchone()[0]
        except sqlite3.OperationalError:
            n = 0
        counts[key] = int(n)
    return counts


def trip_delete_impact(
    trip_id: str,
    force: bool = False,
    reason: Optional[str] = None,
    requested_by: str = "operator",
) -> Dict[str, Any]:
    """Impact-gated trip delete. One BEGIN IMMEDIATE transaction:

      1. re-read the trip (id/owner/title) — {'status':'not_found'} if
         it vanished,
      2. compute dependent counts,
      3. any count nonzero and not force → rollback,
         {'status':'blocked','counts':...} — NOTHING modified,
      4. force → append the narrator_delete_audit row (action=
         'trip_force_delete', person_id=trip owner, display_name=trip
         title, dependency_counts_json=counts + reason + requested_by)
         via the EXISTING db._log_delete_audit helper, then cascade
         delete, then commit. Audit and delete are atomic — a failure
         anywhere before commit rolls back both.

    The router owns the confirm_trip_id exact-match check (422) BEFORE
    calling this; empty-trip deletes (all counts zero) pass through
    without force and without an audit row — the pre-existing
    empty-trip contract is preserved byte-for-byte on that path."""
    from .. import db as _db  # late import: audit helper + shared conventions
    con = _connect()
    try:
        con.execute("BEGIN IMMEDIATE;")
        row = con.execute(
            "SELECT id, person_id, title FROM trips WHERE id = ?",
            (trip_id,),
        ).fetchone()
        if not row:
            con.rollback()
            return {"status": "not_found"}
        counts = _trip_dependent_counts(con, trip_id)
        if any(counts.values()) and not force:
            con.rollback()
            return {"status": "blocked", "counts": counts}
        if force:
            # Audit BEFORE the cascade, inside the same transaction —
            # the audit row describes exactly what is about to go, and
            # rolls back with it on any failure (never a false claim).
            audit_counts: Dict[str, Any] = dict(counts)
            audit_counts["reason"] = (reason or "").strip()
            audit_counts["requested_by"] = requested_by
            _db._log_delete_audit(
                con,
                action="trip_force_delete",
                person_id=str(row["person_id"] or ""),
                display_name=str(row["title"] or ""),
                counts=audit_counts,
                requested_by=requested_by,
            )
        cur = con.execute("DELETE FROM trips WHERE id = ?", (trip_id,))
        if cur.rowcount != 1:
            # Unreachable inside the transaction (row was just read),
            # but fail loud rather than commit a half-truth.
            raise RuntimeError(
                "trip delete touched %d rows for %s" % (cur.rowcount,
                                                        trip_id))
        if _TRIP_FORCE_DELETE_PRECOMMIT_HOOK is not None:
            _TRIP_FORCE_DELETE_PRECOMMIT_HOOK(con, trip_id)
        con.commit()
        return {"status": "deleted", "counts": counts,
                "forced": bool(force)}
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
    whose photo has been soft-deleted are excluded.

    WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01: hidden=1 links are ALWAYS
    excluded — the memoir/export path never renders hidden evidence,
    regardless of include_in_memoir."""
    con = _connect()
    try:
        where = "l.trip_id = ? AND p.deleted_at IS NULL"
        if _table_has_column(con, "trip_photo_links", "hidden"):
            where += " AND l.hidden = 0"
        if memoir_only:
            where += " AND l.include_in_memoir = 1"
        # WO-TRAVEL-DOC-CLOSEOUT-01 -- day-timeline lane. The day join is
        # here so photo_appendix_projection can group a day-placed
        # photograph under its day. Without it, a link carrying
        # trip_day_id and no stop or region fell to the "unplaced"
        # bucket, and the exported document printed the heading
        # "Unplaced" over photographs the operator had placed on a day
        # BY HAND (assignment_method='operator'). That is not a thin
        # document; it is a false statement in the artefact.
        #
        # LEFT JOIN and not INNER: a link whose day row has since been
        # removed must still reach the appendix as unplaced rather than
        # vanish from it.
        _day_cols = ""
        if _table_has_column(con, "trip_photo_links", "trip_day_id"):
            _day_cols = (",\n                       d.date AS day_date,"
                         "\n                       d.title AS day_title,"
                         "\n                       d.day_index AS day_index")
            _day_join = ("LEFT JOIN trip_days d ON d.id = l.trip_day_id")
        else:
            _day_join = ""
        rows = con.execute(
            f"""SELECT l.*, p.image_path AS photo_image_path,
                       p.description AS photo_description,
                       p.date_value AS photo_date_value,
                       p.narrator_ready AS photo_narrator_ready,
                       s.location_name AS stop_location_name,
                       r.title AS region_title{_day_cols}
                FROM trip_photo_links l
                JOIN photos p ON p.id = l.photo_id
                LEFT JOIN trip_stops s ON s.id = l.trip_stop_id
                LEFT JOIN trip_regions r ON r.id = l.trip_region_id
                {_day_join}
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
        # WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01: hidden links never count
        # — the tree/memoir-preview photo counts must match what the
        # appendix would actually render.
        _hidden_where = (" AND hidden = 0"
                         if _table_has_column(
                             con, "trip_photo_links", "hidden")
                         else "")
        for row in con.execute(
            "SELECT trip_stop_id, COUNT(*) AS n FROM trip_photo_links "
            "WHERE trip_id = ?" + _hidden_where + " GROUP BY trip_stop_id",
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


def _hidden_photo_count(trip_id: str) -> int:
    """Hidden photo links whose photograph still exists.

    [Was `_hidden_approved_photo_count` and required
    `include_in_memoir = 1`. Renamed and widened 2026-08-06: the
    document no longer asks whether anything was approved, so a count
    conditioned on approval described a gate that is not there. What
    the operator needs to know is unchanged in kind -- these rows are
    kept out BECAUSE THEY ARE HIDDEN, and un-hiding brings them back.

    A hidden link whose photograph has been soft-deleted is still
    excluded: un-hiding it would not restore anything, so counting it
    would send the operator looking for something that is gone.]
    """
    con = _connect()
    try:
        if not _table_has_column(con, "trip_photo_links", "hidden"):
            return 0
        row = con.execute(
            """SELECT COUNT(*) AS n
                 FROM trip_photo_links l
                 JOIN photos p ON p.id = l.photo_id
                WHERE l.trip_id = ? AND l.hidden = 1
                  AND p.deleted_at IS NULL""",
            (trip_id,),
        ).fetchone()
        return int(row["n"] if row else 0)
    finally:
        con.close()


def photo_appendix_projection(
    trip_id: Optional[str] = None,
    rows: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """WO-TRAVEL-DOC-CLOSEOUT-01 — ONE narrator-safe view of Part III.

    The preview and the DOCX were each deciding, separately, what the
    photo appendix contains: the builder grouped rows and chose captions
    while the preview printed a number. So the operator reviewed a count
    and the family received captions, dates and group headings nobody had
    seen. Both now consume this.

    WHAT IT GUARANTEES

    * `photo_description` is NEVER in the output. It is operator- or
      machine-written text nobody approved for a narrator to hear, and
      under a photograph in a memoir it is indistinguishable, to the
      reader, from something the narrator said. The caption is
      `_safe_caption`'s answer: narrator's own words, else an approved
      operator caption, else nothing.
    * Groups are keyed by STOP OR REGION ID, never by display text. Two
      stops both called "Hotel", or a stop and a region sharing a name,
      were merged into one appendix section by the old
      `str(stop_location_name or region_title or "Unplaced")` key -- the
      photographs of two different places silently became one.
    * File availability is resolved HERE, once. The builder skipped
      missing files and reported the shortfall only at the foot of the
      document; the preview promised the full count. Now both know.
    * `image_path` is present for the builder, which has to embed the
      bytes, and is stripped before the projection reaches the browser
      (see `trip_memoir_preview`). A filesystem path is not a thing to
      hand a browser, and `photo_id` is what a thumbnail needs.

    Rows come from `photo_links_with_photo_paths(memoir_only=True)`, so
    unapproved links, hidden links and soft-deleted photographs are
    already excluded upstream.
    """
    import os as _os

    # `rows` lets a caller that already holds the export set reuse it --
    # the DOCX builder does. ONE implementation of the grouping, because
    # two would drift and the whole point is that the preview and the
    # document describe the same appendix.
    if rows is None:
        rows = photo_links_with_photo_paths(trip_id, memoir_only=True)

    groups: List[Dict[str, Any]] = []
    index: Dict[str, int] = {}
    per_stop: Dict[str, int] = {}
    per_day: Dict[str, int] = {}
    available = 0
    unavailable = 0

    for r in rows:
        stop_id = r.get("trip_stop_id")
        region_id = r.get("trip_region_id")
        day_id = r.get("trip_day_id")
        # ── WO-TRAVEL-DOC-CLOSEOUT-01: stop -> region -> DAY -> unplaced ─
        #
        # The day case is the addition, and it goes LAST among the real
        # scopes on purpose. Stop and region are where a photograph was
        # taken; a day is when. A link that carries both has already been
        # given a place by a human, and demoting it to a date would throw
        # that away -- so every photograph that grouped under a stop or a
        # region before this change still groups there, byte for byte.
        #
        # What changes is only the case that used to be a lie: a link
        # with a trip_day_id and no stop or region fell to "Unplaced",
        # which the operator reads as "the system does not know where
        # this goes" about a placement they made themselves.
        if stop_id:
            key, scope, label = (f"stop:{stop_id}", "stop",
                                 r.get("stop_location_name") or "(unnamed stop)")
        elif region_id:
            key, scope, label = (f"region:{region_id}", "region",
                                 r.get("region_title") or "(unnamed region)")
        elif day_id:
            key, scope, label = (f"day:{day_id}", "day",
                                 _day_scope_label(r))
        else:
            key, scope, label = ("unplaced", "unplaced", "Unplaced")

        if key not in index:
            index[key] = len(groups)
            groups.append({"key": key, "scope": scope, "scope_id":
                           stop_id or region_id or day_id, "label": label,
                           "photos": []})

        path = r.get("photo_image_path")
        is_available = bool(path) and _os.path.isfile(str(path))
        if is_available:
            available += 1
        else:
            unavailable += 1
        if stop_id:
            per_stop[stop_id] = per_stop.get(stop_id, 0) + 1
        # Counted by the SAME pass that builds the groups, so the "· N
        # approved photos" line on a day in Part I cannot disagree with
        # the number of images under that day in Part III. A photograph
        # that carries a day AND a stop counts for both: the stop line
        # says where it was taken, the day line says the day held it.
        if day_id:
            per_day[day_id] = per_day.get(day_id, 0) + 1

        groups[index[key]]["photos"].append({
            "photo_id": r.get("photo_id"),
            "link_id": r.get("id"),
            "caption": _safe_photo_caption(r),
            "taken_at": r.get("taken_at") or r.get("photo_date_value") or "",
            "available": is_available,
            # Builder-only. Stripped before this reaches a browser.
            "image_path": path,
        })

    return {
        "groups": groups,
        "approved": len(rows),
        "available": available,
        "unavailable": unavailable,
        "approved_by_stop": per_stop,
        "approved_by_day": per_day,
    }


def _day_scope_label(row: Dict[str, Any]) -> str:
    """Heading for a day group in the photo appendix.

    Prefers what the operator typed, because that is what they will
    recognise: "Day 1 — Santa Fe to Bismarck" reads as their own trip;
    a bare uuid or a bare ISO date does not. Falls back through the
    date to a plain "A day on this trip" rather than to "Unplaced",
    which would re-introduce the exact false statement this grouping
    exists to remove -- the photograph IS placed; we merely could not
    read the day row.
    """
    idx = row.get("day_index")
    title = str(row.get("day_title") or "").strip()
    date = str(row.get("day_date") or "").strip()
    head = f"Day {idx}" if idx not in (None, "") else ""
    tail = title or date
    if head and tail:
        return f"{head} — {tail}"
    return head or tail or "A day on this trip"


def _safe_photo_caption(row: Dict[str, Any]) -> str:
    """Narrator caption, else an APPROVED operator caption, else nothing.

    The same rule `_NARRATOR_PHOTO_LINK_COLS` states for the narrator
    read. It lives here as well because the export query is a
    `SELECT l.*` and would otherwise hand the raw column onward -- which
    is exactly how unapproved text reached the document once already.
    `photo_description` is deliberately not consulted at all.
    """
    narrator = (row.get("narrator_caption") or "").strip()
    if narrator:
        return narrator
    if row.get("caption_approved_for_lori"):
        return (row.get("caption") or "").strip()
    return ""


# WO-TRAVEL-DOC-CLOSEOUT-01, rewritten 2026-08-06 after Chris's ruling.
#
# [This block previously held `day_projection()` and the constants
# DAY_MEMOIR_TEXT_FIELDS / DAY_MEMOIR_LIST_FIELDS. That version gated
# the export on `trip_days.include_in_memoir` and projected only the
# day card's own six text fields. It is retired, not refined: the
# product rule is now
#
#     the visible trip timeline is the editable source of truth, and
#     Export Travel Document produces a DOCX snapshot of THAT timeline
#
# so an approval gate on the day is the wrong shape, and a projection
# that reads six fields off the day row is "a second reduced
# interpretation of a day" -- exactly what rule 4 forbids. Migration
# 0042 stays applied so fresh installations match Chris's database, and
# the column is DORMANT: nothing below reads it.]
#
# What replaces it reads the SAME projection the operator is looking at.


def _strip_timeline_for_browser(days, unplaced):
    """Remove builder-only keys before a projection reaches a browser.

    Only `image_path` today. It exists so the DOCX can embed the file;
    the interface fetches by `/api/photos/{id}/thumb` and has never
    needed a storage path, and shipping one would be an operator-surface
    leak for no gain -- the rule `_day_photo_items` already states.
    """
    for bucket in (days, [unplaced]):
        for group in bucket or []:
            for item in (group or {}).get("items", []) or []:
                item.pop("image_path", None)


def trip_timeline_projection(trip_id: str,
                             with_image_paths: bool = False) -> Dict[str, Any]:
    """The visible trip timeline, day by day, as ONE projection.

    This is what the Travel Document tab renders and what the DOCX is
    built from. There is deliberately no second reading: rule 9 says the
    preview and the document consume one projection, and the cheapest
    way to guarantee that is to have only one.

    WHAT IS IN IT: every day of the trip in day_index/date order, each
    carrying its timeline items -- the day's own typed text, the
    conversations placed on it, its notes, its sources and its
    photographs -- in the order `trip_day_timeline_items` already sorts
    them for the operator. Then `unplaced`: the material that has no day
    yet, which the document prints under "Needs a day".

    WHAT IS EXCLUDED, and nothing else (rule 7): hidden rows, which
    every underlying read already drops; soft-deleted photographs;
    rejected placements; and other trips, which is the trip_id filter.
    `include_in_memoir` is NOT consulted anywhere in this function. An
    unticked note, source or photograph is visible on the timeline, so
    it is in the document.

    NO APPROVAL, NO SECOND INTERPRETATION, NO COPY. Every item is read
    live from the table that owns it, so an edit on the timeline changes
    the next export with nothing to keep in step.
    """
    days_out: List[Dict[str, Any]] = []
    item_count = 0
    for row in trip_days_list(trip_id):
        did = str(row.get("id") or "")
        items = trip_day_timeline_items(trip_id, did) if did else []
        item_count += len(items)
        days_out.append({
            "id": did,
            "day_index": row.get("day_index"),
            "date": row.get("date"),
            "title": str(row.get("title") or "").strip() or None,
            "items": items,
        })

    # ── "Needs a day" ────────────────────────────────────────────────
    #
    # Rule 6. Material with no day is still the operator's material and
    # still belongs in the snapshot; leaving it out would make the
    # document quieter than the screen.
    #
    # Rule 10 decides the boundary. A note or source that carries a STOP
    # or a REGION is already printed by the region walk in Part I, so
    # including it here as well would print it twice. The partition is
    # therefore: has a day -> the day; no day but a place -> the region
    # walk; neither -> here. A photograph has no such second home, so
    # every dayless photograph comes here.
    unplaced_items: List[Dict[str, Any]] = []
    unplaced_items.extend(trip_day_conversation_items(trip_id, None))
    con = _connect()
    try:
        for _n in location_notes_list(trip_id):
            if _n.get("trip_day_id") or _n.get("trip_stop_id") \
                    or _n.get("trip_region_id"):
                continue
            unplaced_items.append({
                "kind": "note", "id": _n.get("id"),
                "at": _n.get("created_at") or "", "ord": _n.get("ord") or 0,
                "title": _n.get("note_title") or "",
                "text": _n.get("note_text") or "",
                "source_type": _n.get("source_type") or "",
            })
        for _s in sources_list(trip_id):
            if _s.get("trip_day_id") or _s.get("trip_stop_id") \
                    or _s.get("trip_region_id"):
                continue
            unplaced_items.append({
                "kind": "source", "id": _s.get("id"),
                "at": _s.get("source_date") or _s.get("created_at") or "",
                "ord": _s.get("ord") or 0,
                "title": _s.get("title") or "",
                "source_type": _s.get("source_type") or "",
                "summary": _s.get("summary") or "",
                "link_url": _s.get("link_url") or "",
            })
        if _table_has_column(con, "trip_photo_links", "trip_day_id"):
            sql = ("SELECT l.id AS link_id, l.photo_id, l.taken_at, l.ord, "
                   "       l.caption, l.narrator_caption, "
                   "       p.description AS photo_description "
                   "  FROM trip_photo_links l "
                   "  LEFT JOIN photos p ON p.id = l.photo_id "
                   " WHERE l.trip_id = ? AND l.trip_day_id IS NULL "
                   "   AND p.deleted_at IS NULL "
                   + _timeline_hidden_clause(con, "trip_photo_links", "l") +
                   " ORDER BY l.taken_at, l.ord")
            for r in con.execute(sql, (trip_id,)):
                row = _row_to_dict(r)
                _narr = str(row.get("narrator_caption") or "").strip()
                _oper = str(row.get("caption") or "").strip()
                _mach = str(row.get("photo_description") or "").strip()
                if _narr:
                    _cap, _src = _narr, "narrator"
                elif _oper:
                    _cap, _src = _oper, "operator"
                elif _mach:
                    _cap, _src = _mach, "machine"
                else:
                    _cap, _src = "", ""
                unplaced_items.append({
                    "kind": "photo", "id": row.get("link_id"),
                    "link_id": row.get("link_id"),
                    "photo_id": row.get("photo_id"),
                    "at": row.get("taken_at") or "", "ord": row.get("ord") or 0,
                    "caption": _cap, "caption_source": _src,
                })
    finally:
        con.close()

    # Same sort the day timeline uses, so the two read alike: undated
    # items after dated ones rather than pretending to be midnight.
    _rank = {k: i for i, k in enumerate(DAY_TIMELINE_KINDS)}
    unplaced_items.sort(key=lambda i: (
        1 if not str(i.get("at") or "").strip() else 0,
        str(i.get("at") or ""),
        _rank.get(str(i.get("kind") or ""), 99),
        int(i.get("ord") or 0),
        str(i.get("id") or ""),
    ))
    unplaced = {"id": None, "day_index": None, "date": None,
                "title": "Needs a day", "items": unplaced_items}
    item_count += len(unplaced_items)

    # ── PATHS ARE OPT-IN, AND THEY ARE NOT IN THE TIMELINE ───────────
    #
    # `_day_photo_items` deliberately projects no storage path: it feeds
    # the LIVE day-timeline endpoint that the operator interface reads,
    # and `test_trip_placement` has a standing guard that no path,
    # coordinate or provider reference crosses that boundary. Putting
    # the path there for the DOCX's benefit broke that guard, and the
    # guard was right -- stripping at the memoir-preview route would
    # have left the day-timeline route still leaking.
    #
    # So the document asks for paths explicitly and nothing else ever
    # gets them. One query for the whole trip rather than one per
    # photograph.
    if with_image_paths:
        _paths: Dict[str, str] = {}
        _con = _connect()
        try:
            for _r in _con.execute(
                "SELECT p.id, p.image_path FROM photos p "
                "JOIN trip_photo_links l ON l.photo_id = p.id "
                "WHERE l.trip_id = ? AND p.deleted_at IS NULL",
                    (trip_id,)):
                _paths[str(_r["id"])] = str(_r["image_path"] or "")
        except sqlite3.Error:            # pragma: no cover
            _paths = {}
        finally:
            _con.close()
        for _group in list(days_out) + [unplaced]:
            for _it in _group.get("items", []):
                if _it.get("kind") == "photo":
                    _it["image_path"] = _paths.get(
                        str(_it.get("photo_id") or ""), "")

    return {
        "days": days_out,
        "unplaced": unplaced,
        "day_count": len(days_out),
        "days_with_items": sum(1 for d in days_out if d["items"]),
        "item_count": item_count,
    }


def trip_memoir_preview(
    trip_id: str,
    appendix: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Deterministic dual-axis memoir preview per WO-TRIP-MEMOIR-01:
    Part I chronological (regions -> nested stops), Part II thematic
    (themes with their matching stops), Part III photo appendix
    counts. No LLM authoring — this is a walk of canonical rows."""
    tree = trip_tree(trip_id)
    if not tree:
        return None

    # ── WO-TRAVEL-DOC-CLOSEOUT-01: server-authoritative export counts ──
    #
    # The browser used to reconstruct "what is in the document" from its
    # own cached arrays, and got four things wrong at once: it counted
    # hidden rows (which this function drops), counted every trip photo
    # rather than the memoir-approved ones the appendix embeds, counted
    # links whose photo has since been soft-deleted, and went stale the
    # moment anything was approved.
    #
    # None of that is fixable in the browser, because membership is
    # decided HERE. The counts are therefore computed from the same
    # filtered walks the document itself is built from, and the client
    # displays them rather than deriving them.
    # ── VISIBLE counts, not approval counts ──────────────────────────
    #
    # [Held notes_in / notes_out / sources_in / sources_out / photos_in
    # / photos_out until 2026-08-06, where "_in" meant include_in_memoir
    # = 1. That word no longer decides anything about this export, and a
    # review screen reporting a gate that is not there is worse than one
    # reporting nothing. The `_hidden_approved` counters stay: a hidden
    # row IS still withheld, and the operator needs to know the hide is
    # what is doing it.]
    _counts = {
        "notes": 0, "notes_hidden": 0,
        "sources": 0, "sources_hidden": 0,
        "photos": 0, "photos_hidden": 0,
        # [Held "days_in" / "days_out" / "days_approved_empty" on
        # 2026-08-06. Those counted an approval that no longer gates
        # this export; a review screen must not report a gate that is
        # not there. Plain day and item counts come off the timeline
        # projection instead.]
        "days": 0, "day_items": 0,
    }
    # Hidden rows are excluded from the document, so a hidden row still
    # carrying its In-memoir tick is reported separately rather than
    # silently: the operator needs to know the HIDE is what keeps it out.
    # [Required `include_in_memoir` as well until 2026-08-06, when the
    # counters were named `*_hidden_approved`. Approval decides nothing
    # about this document, so the only true statement left is the one
    # that always mattered: these rows are held back BY THE HIDE.]
    for _hn in location_notes_list(trip_id, include_hidden=True):
        if _hn.get("hidden"):
            _counts["notes_hidden"] += 1
    for _hs in sources_list(trip_id, include_hidden=True):
        if _hs.get("hidden"):
            _counts["sources_hidden"] += 1

    # Promoted story notes (include_in_memoir=1) grouped by scope. Notes
    # NOT flagged never reach the memoir (WO-TRAVEL-DOC-STORY-LAYER-01).
    _notes_stop: Dict[str, List[Dict[str, Any]]] = {}
    _notes_region: Dict[str, List[Dict[str, Any]]] = {}
    # Kept as empty lists so existing readers of `story_notes` /
    # `sources` do not break. Placeless material is the timeline's, and
    # printing it here as well was a duplication (rule 10).
    _notes_trip_placeless: List[Dict[str, Any]] = []
    for _n in location_notes_list(trip_id):
        # Rule 1: no include_in_memoir filter. A note visible on the
        # timeline is in the document.
        _counts["notes"] += 1
        _entry = {"note_title": _n.get("note_title"),
                  "note_text": _n.get("note_text"),
                  "source_type": _n.get("source_type")}
        # ── RULE 10: each item is printed exactly once ───────────────
        #
        # A note that carries a day is rendered by the timeline, under
        # that day, so it must not also be rendered here. `continue`
        # rather than a fourth bucket: the day lane reads the note
        # itself from the same table, and a second copy of the text
        # here would be the duplication rule 10 forbids.
        #
        # A note with no day but a stop or region still belongs to the
        # region walk; one with neither is printed under "Needs a day".
        _sid, _rid = _n.get("trip_stop_id"), _n.get("trip_region_id")
        if _n.get("trip_day_id"):
            continue
        if _sid:
            _notes_stop.setdefault(_sid, []).append(_entry)
        elif _rid:
            _notes_region.setdefault(_rid, []).append(_entry)
        # else: no day, no stop, no region -- the timeline prints it
        # under "Needs a day". Collecting it here as well printed all
        # eleven of Christopher's Bismarck notes twice in the same
        # document, once at the top and once at the back.

    # Promoted sources (include_in_memoir=1) grouped by scope.
    _src_stop: Dict[str, List[Dict[str, Any]]] = {}
    _src_region: Dict[str, List[Dict[str, Any]]] = {}
    _src_trip_placeless: List[Dict[str, Any]] = []
    for _s in sources_list(trip_id):
        _counts["sources"] += 1
        _se = {"title": _s.get("title"), "summary": _s.get("summary"),
               "pasted_text": _s.get("pasted_text"), "link_url": _s.get("link_url"),
               "filename": _s.get("filename"), "source_type": _s.get("source_type")}
        _ssid, _srid = _s.get("trip_stop_id"), _s.get("trip_region_id")
        if _s.get("trip_day_id"):        # printed by the timeline
            continue
        if _ssid:
            _src_stop.setdefault(_ssid, []).append(_se)
        elif _srid:
            _src_region.setdefault(_srid, []).append(_se)
        # else: printed under "Needs a day", once. See the notes above.

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

    # THE APPENDIX EMBEDS ONLY MEMOIR-APPROVED PHOTOS, so the appendix
    # block must count those and not every photo assigned to the trip.
    # `assigned_photos` said 4 while the DOCX embedded 1, which reads as
    # a broken export rather than as three unapproved photographs.
    #
    # Counted through the SAME call the exporter makes, rather than by a
    # second query that could drift from it -- it already excludes hidden
    # links and soft-deleted photos, both of which the browser's own
    # count got wrong.
    # ── WO-TRAVEL-DOC-CLOSEOUT-01 #3: ONE read per export ────────────
    #
    # `appendix` lets the export route build the projection once and hand
    # the same object to this function AND to the DOCX builder. Before
    # that, an export read the photo-link table four times and the counts
    # printed in the document came from a DIFFERENT read than the
    # appendix the operator had reviewed. The window was small and the
    # whole point of a shared projection is that there is no window.
    #
    # ── The timeline, built ONCE and carried in the preview dict ─────
    #
    # It lives in the preview because the DOCX builder already receives
    # this dict, which makes rule 9 -- one shared projection -- a
    # property of the data rather than a discipline the export route
    # has to keep. There is no second read for them to disagree about.
    #
    # Failure is contained: a preview must not die because the timeline
    # could not be read.
    try:
        _timeline = trip_timeline_projection(trip_id, with_image_paths=True)
    except Exception:            # pragma: no cover - reading must not fail a preview
        _timeline = {"days": [], "unplaced": {"title": "Needs a day",
                                              "items": []},
                     "day_count": -1, "days_with_items": -1,
                     "item_count": -1, "unknown": True}
    _counts["days"] = _timeline.get("day_count", 0)
    _counts["day_items"] = _timeline.get("item_count", 0)

    # The narrator's own name, for the conversation speaker labels. A
    # transcript that said "Narrator:" over a man's account of visiting
    # his mother's parents' graves would read as a system log rather
    # than as his trip. First token only -- "Chris:", the way Lori
    # addresses him -- and "Narrator" only when there is nothing to use.
    _narrator_label = "Narrator"
    try:
        _con = _connect()
        try:
            _pid = tree.get("person_id")
            if _pid:
                _r = _con.execute(
                    "SELECT display_name FROM people WHERE id = ?",
                    (_pid,)).fetchone()
                _dn = str((_r["display_name"] if _r else "") or "").strip()
                if _dn:
                    _narrator_label = _dn.split()[0]
        finally:
            _con.close()
    except Exception:            # pragma: no cover - a label must not fail a preview
        pass

    # Visible photographs on this trip, counted from the same unfiltered
    # read the timeline projects.
    #
    # [`_appendix` held the grouped photo-appendix projection. Retired
    # 2026-08-06 with Part III: photographs print once, under their own
    # day. `_appendix_unknown` survives as the "we could not count"
    # signal, because -1 reaching the operator is still better than a
    # confident zero.]
    _appendix_unknown = False
    try:
        _counts["photos"] = len(
            photo_links_with_photo_paths(trip_id, memoir_only=False))
        _counts["photos_hidden"] = _hidden_photo_count(trip_id)
    except Exception:            # pragma: no cover - counting must not fail a preview
        _appendix_unknown = True
        _counts["photos"] = -1
        _counts["photos_hidden"] = -1

    return {
        "trip_id": trip_id,
        "title": tree.get("title"),
        "date_range": {
            "start": tree.get("start_date"),
            "end": tree.get("end_date"),
        },
        "summary": tree.get("summary"),
        "story_notes": _notes_trip_placeless,
        "sources": _src_trip_placeless,
        "part_one_journey_in_order": part_one,
        "part_one_timeline": _timeline,
        "narrator_label": _narrator_label,
        "part_two_themes": part_two,
        # ── part_three_photo_appendix: RETIRED 2026-08-06 ────────────
        #
        # [Carried the grouped appendix projection -- approved /
        # available / unavailable, approved_by_stop and the groups
        # themselves -- so the browser could preview the photo
        # appendix the document embedded.]
        #
        # The appendix is gone: the timeline prints each photograph
        # once, under the day it is placed on, and rule 10 forbids a
        # second copy. The key stays, always `unknown`, so an older
        # client that still reads it prints nothing rather than
        # printing a confident zero about a section that no longer
        # exists.
        "part_three_photo_appendix": {"unknown": True},
        "export_summary": _counts,
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


def public_context_list_for_link(
    photo_link_id: str,
) -> List[Dict[str, Any]]:
    """Public-context rows attached to a specific photo link. Used by
    the modal to surface place_from_context and other photo-scoped
    public context alongside the OCR/vision/observation lanes.

    WO-TRAVEL-DOC-EVIDENCE-TOOLS-01 preflight (2026-07-11). Tolerant
    of a pre-0026 DB (table missing) — returns []."""
    con = _connect()
    try:
        rows = con.execute(
            "SELECT * FROM trip_public_context "
            "WHERE photo_link_id = ? "
            "ORDER BY created_at, id",
            (photo_link_id,),
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
    rejected: Optional[bool] = None,
) -> bool:
    """Partial update. Strict edit-and-approval contract, mirrored in
    photo_context_update:

    * Editing result_summary REVOKES approved_for_lori unless the same
      request explicitly sets approved_for_lori.
    * On any text edit, include_in_memoir MUST reset to 0 UNLESS the
      same request explicitly re-approves AND explicitly re-includes.
      A caller passing include_in_memoir=True with approved_for_lori=
      False (or approved_for_lori omitted) does NOT keep the row in
      the memoir. A caller passing approved_for_lori=True but omitting
      include_in_memoir does NOT keep the row in the memoir either.
    * `notes`, `source_url`, `query` are operator provenance fields;
      they are NOT the reviewed text, so touching them does not
      trigger the edit-and-approval contract.
    * `rejected` (0/1) — hide-not-delete flag (added 2026-07-11).

    2026-07-11 review-follow-up ROUND 3: tightened per Chris's edge-
    case audit. Previously only the `approved_for_lori is None + edit`
    branch cleared include; the shapes
    `{result_summary: X, approved_for_lori: False}` and
    `{result_summary: X, approved_for_lori: True}` (no include) still
    left include_in_memoir=1. Locked here."""
    sets: List[str] = []
    args: List[Any] = []
    edited_text = (result_summary is not None)

    # ── approval semantics (see photo_context_update for the same shape)
    if approved_for_lori is True:
        effective_approved = True
    elif approved_for_lori is False:
        effective_approved = False
    elif edited_text:
        effective_approved = False   # implicit revoke on edit
    else:
        effective_approved = None    # unchanged

    # ── memoir inclusion semantics ──────────────────────────────
    # Strict rule: on any text edit, include stays 0 unless the SAME
    # request explicitly re-approves AND explicitly re-includes.
    if edited_text:
        if approved_for_lori is True and include_in_memoir is True:
            effective_include = True
        else:
            effective_include = False
    elif include_in_memoir is not None:
        effective_include = bool(include_in_memoir)
    else:
        effective_include = None     # unchanged

    if result_summary is not None:
        sets.append("result_summary = ?"); args.append(result_summary)
    if notes is not None:
        sets.append("notes = ?"); args.append(notes)
    if source_url is not None:
        sets.append("source_url = ?"); args.append(source_url)
    if query is not None:
        sets.append("query = ?"); args.append(query)
    if effective_approved is not None:
        sets.append("approved_for_lori = ?")
        args.append(1 if effective_approved else 0)
    if effective_include is not None:
        sets.append("include_in_memoir = ?")
        args.append(1 if effective_include else 0)
    if rejected is not None:
        sets.append("rejected = ?")
        args.append(1 if rejected else 0)
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


# ── Photo context (OCR / vision draft evidence) ──────────────────────────
# WO-TRAVEL-DOC-EVIDENCE-TOOLS-01 Phase 1. Draft evidence extracted FROM a
# photo. Approval ladder enforced here: create defaults everything OFF;
# editing result_summary/raw_text REVOKES approved_for_lori unless the
# same request re-approves; include_in_memoir requires approved_for_lori
# (checked at the router). Rejected rows are never surfaced to Lori.
_PHOTO_CONTEXT_TYPES = (
    "ocr_text", "vision_description", "filename_context",
    "operator_photo_context",
    # WO-TRAVEL-DOC-EVIDENCE-TOOLS-01 preflight (2026-07-11) — local-LLM
    # drafted image observation. Approval ladder identical to OCR /
    # vision (confidence='draft' default; approved_for_lori=0;
    # include_in_memoir=0; rejected=0). Migration 0031 rebuilds the
    # CHECK constraint on trip_photo_context to accept this value.
    "draft_observation",
)


def photo_context_create(
    trip_id: str,
    photo_link_id: str,
    context_type: str,
    result_summary: str,
    photo_id: Optional[str] = None,
    raw_text: Optional[str] = None,
    confidence: str = "draft",
    engine: Optional[str] = None,
    model_name: Optional[str] = None,
    source_ref: Optional[str] = None,
    context_id: Optional[str] = None,
) -> str:
    if context_type not in _PHOTO_CONTEXT_TYPES:
        raise ValueError(
            "invalid context_type %r; expected one of %s"
            % (context_type, ", ".join(_PHOTO_CONTEXT_TYPES)))
    cid = context_id or _new_id()
    con = _connect()
    try:
        con.execute(
            """INSERT INTO trip_photo_context
               (id, trip_id, photo_link_id, photo_id, context_type,
                result_summary, raw_text, confidence, engine, model_name,
                source_ref, approved_for_lori, include_in_memoir, rejected,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, ?)""",
            (
                cid, trip_id, photo_link_id, photo_id, context_type,
                result_summary, raw_text, confidence or "draft", engine,
                model_name, source_ref, _now(), _now(),
            ),
        )
        con.commit()
        return cid
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def photo_context_supersede_drafts(link_id: str, context_type: str,
                                   keep_id: Optional[str] = None) -> int:
    """Retire UNAPPROVED draft rows of one context_type on a photo link.

    Re-running an extractor must not pile up drafts, and — the load-bearing
    case — a re-run that now finds NO text must not leave the previous run's
    wrong answer standing.

    LIVE PROOF (2026-07-14): the confidence gate correctly refused to write a
    new row for a photo of FOOD, but the hallucinated row from BEFORE the gate
    was still in the table, and Lori read it to the narrator verbatim:
    "The OCR draft appears to read '# : 9 #4 - s 4 | | di i s k EJ...'".
    Stopping new garbage is not the same as removing old garbage.

    Rules:
      * APPROVED rows are never touched. The operator's judgment outranks the
        engine's; if a human approved it, only a human unapproves it.
      * Rows are marked rejected=1, never DELETEd — the Lab has a locked
        no-delete posture and the provenance trail must survive.
      * keep_id lets a fresh successful row survive its own sweep.
    """
    con = _connect()
    try:
        params: List[Any] = [_now(), link_id, context_type]
        sql = ("UPDATE trip_photo_context SET rejected = 1, updated_at = ? "
               "WHERE photo_link_id = ? AND context_type = ? "
               "AND approved_for_lori = 0 AND rejected = 0")
        if keep_id:
            sql += " AND id != ?"
            params.append(keep_id)
        cur = con.execute(sql, params)
        con.commit()
        return int(cur.rowcount or 0)
    except sqlite3.OperationalError:
        return 0                      # pre-0030 DB — nothing to supersede
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def public_context_supersede_drafts(photo_link_id: str, source_type: str,
                                    keep_id: Optional[str] = None) -> int:
    """Retire UNAPPROVED public_context draft rows of one source_type on a
    photo link. Sibling of photo_context_supersede_drafts (OCR).

    Live (2026-07-23): the lookup endpoint created a NEW public_context row on
    every call without retiring the last, so running lookup twice on a photo
    made the modal read the same place context twice ("...and the place context
    suggests X, and the place context suggests X..."). Same fix posture as OCR:
    a fresh lookup retires its own prior unapproved drafts.

    APPROVED rows are never touched; rows are marked rejected=1, never DELETEd;
    keep_id lets the fresh row survive its own sweep.
    """
    con = _connect()
    try:
        params: List[Any] = [_now(), photo_link_id, source_type]
        sql = ("UPDATE trip_public_context SET rejected = 1, updated_at = ? "
               "WHERE photo_link_id = ? AND source_type = ? "
               "AND approved_for_lori = 0 AND rejected = 0")
        if keep_id:
            sql += " AND id != ?"
            params.append(keep_id)
        cur = con.execute(sql, params)
        con.commit()
        return int(cur.rowcount or 0)
    except sqlite3.OperationalError:
        return 0                      # pre-0032 DB (no rejected col) — no-op
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def photo_context_list_for_link(link_id: str) -> List[Dict[str, Any]]:
    """All photo-context rows for a link (operator view — includes drafts
    and rejected). Tolerant of a pre-0030 DB (table missing) -> []."""
    con = _connect()
    try:
        rows = con.execute(
            "SELECT * FROM trip_photo_context WHERE photo_link_id = ? "
            "ORDER BY created_at, id",
            (link_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()


def photo_context_get(context_id: str) -> Optional[Dict[str, Any]]:
    con = _connect()
    try:
        row = con.execute(
            "SELECT * FROM trip_photo_context WHERE id = ?", (context_id,),
        ).fetchone()
        return _row_to_dict(row) if row else None
    except sqlite3.OperationalError:
        return None
    finally:
        con.close()


def photo_context_update(
    context_id: str,
    result_summary: Optional[str] = None,
    raw_text: Optional[str] = None,
    approved_for_lori: Optional[bool] = None,
    include_in_memoir: Optional[bool] = None,
    rejected: Optional[bool] = None,
) -> bool:
    """Partial update. Strict edit-and-approval contract, mirrored in
    public_context_update:

    * Editing result_summary OR raw_text REVOKES approved_for_lori
      unless the same request explicitly sets approved_for_lori.
    * On any text edit, include_in_memoir MUST reset to 0 UNLESS the
      same request explicitly re-approves AND explicitly re-includes.
      A caller passing include_in_memoir=True with approved_for_lori=
      False (or approved_for_lori omitted) does NOT keep the row in
      the memoir. A caller passing approved_for_lori=True but omitting
      include_in_memoir does NOT keep the row in the memoir either.

    2026-07-11 review-follow-up ROUND 3: tightened per Chris's edge-
    case audit. The previous round only cleared include when
    approved_for_lori was omitted; the odd shapes
    `{result_summary: X, approved_for_lori: False}` and
    `{result_summary: X, approved_for_lori: True}` (no include) both
    still left include_in_memoir=1. Locked here."""
    sets: List[str] = []
    args: List[Any] = []
    edited_text = (result_summary is not None) or (raw_text is not None)

    # ── approval semantics ──────────────────────────────────────
    #   True   → explicit re-approval
    #   False  → explicit revocation
    #   None + edited_text  → implicit revocation on edit
    #   None + no edit      → unchanged
    if approved_for_lori is True:
        effective_approved = True
    elif approved_for_lori is False:
        effective_approved = False
    elif edited_text:
        effective_approved = False   # implicit revoke on edit
    else:
        effective_approved = None    # unchanged

    # ── memoir inclusion semantics ──────────────────────────────
    # Strict rule: on any text edit, include stays 0 unless the SAME
    # request explicitly re-approves AND explicitly re-includes.
    # Off-edit paths honor the caller's explicit value or leave it
    # unchanged.
    if edited_text:
        if approved_for_lori is True and include_in_memoir is True:
            effective_include = True
        else:
            effective_include = False
    elif include_in_memoir is not None:
        effective_include = bool(include_in_memoir)
    else:
        effective_include = None     # unchanged

    if result_summary is not None:
        sets.append("result_summary = ?"); args.append(result_summary)
    if raw_text is not None:
        sets.append("raw_text = ?"); args.append(raw_text)
    if effective_approved is not None:
        sets.append("approved_for_lori = ?")
        args.append(1 if effective_approved else 0)
    if effective_include is not None:
        sets.append("include_in_memoir = ?")
        args.append(1 if effective_include else 0)
    if rejected is not None:
        sets.append("rejected = ?")
        args.append(1 if rejected else 0)
    if not sets:
        return False
    sets.append("updated_at = ?"); args.append(_now())
    args.append(context_id)
    con = _connect()
    try:
        cur = con.execute(
            f"UPDATE trip_photo_context SET {', '.join(sets)} WHERE id = ?",
            args,
        )
        con.commit()
        return cur.rowcount > 0
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def photo_context_delete(context_id: str) -> bool:
    con = _connect()
    try:
        cur = con.execute(
            "DELETE FROM trip_photo_context WHERE id = ?", (context_id,),
        )
        con.commit()
        return cur.rowcount > 0
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def photo_context_trip_id(context_id: str) -> Optional[str]:
    con = _connect()
    try:
        row = con.execute(
            "SELECT trip_id FROM trip_photo_context WHERE id = ?",
            (context_id,),
        ).fetchone()
        return row["trip_id"] if row else None
    except sqlite3.OperationalError:
        return None
    finally:
        con.close()


def photo_file_for_link(link_id: str) -> Optional[Dict[str, Any]]:
    """Resolve a photo link to its local file for OCR/vision providers:
    {link_id, trip_id, photo_id, image_path}. image_path is a LOCAL path
    consumed only by a LOCAL provider — it is never serialized to Lori or
    any response. Returns None when the link is unknown."""
    con = _connect()
    try:
        row = con.execute(
            "SELECT l.id AS link_id, l.trip_id AS trip_id, "
            "l.photo_id AS photo_id, p.image_path AS image_path "
            "FROM trip_photo_links l "
            "LEFT JOIN photos p ON p.id = l.photo_id "
            "WHERE l.id = ?",
            (link_id,),
        ).fetchone()
        return _row_to_dict(row) if row else None
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
    """All day rows for a trip ordered by day_index, then date.

    2026-07-23 (follow-up) — this function used to swallow
    ``sqlite3.OperationalError`` and return ``[]`` on any operational
    failure. ChatGPT's post-1e388b5 review flagged that as HIGH
    severity: the ``/api/trips/{trip_id}/days`` endpoint returns a
    successful HTTP 200 with an empty list even when the underlying
    cause is ``database is locked``, ``no such table trip_days``,
    ``no such column``, an I/O failure, or malformed schema — all of
    which look IDENTICAL to the operator ("No day cards yet") and
    defeat the Track C load-warning path the FE added to surface real
    backend errors.

    The one legitimate reason to swallow was a fresh clone against a
    pre-0027 DB where the migration hadn't landed yet. In practice
    every deployment has been past 0027 for months and there is no
    "pre-0027 DB" left in the wild. Callers that legitimately want
    the "no cards yet" empty state get a normal empty result set from
    a successful SELECT — that path is untouched.

    Any OperationalError now bubbles up to the router, which converts
    it into an HTTPException(500) with a classified message. The FE's
    ``_captureLoadError`` catch already handles non-200s by writing
    to ``st.loadWarnings`` — so the operator sees the actual failure
    ("Day cards failed to load: database temporarily locked") instead
    of "No day cards yet." """
    con = _connect()
    try:
        rows = con.execute(
            "SELECT * FROM trip_days WHERE trip_id = ? "
            "ORDER BY day_index, date",
            (trip_id,),
        ).fetchall()
        return [_day_row_to_dict(r) for r in rows]
    finally:
        con.close()


def trip_day_get(day_id: str) -> Optional[Dict[str, Any]]:
    """Fetch one day row by id, or None if it doesn't exist.

    2026-07-23 (follow-up) — no longer swallows OperationalError.
    An operational failure (locked DB, missing table, I/O error) used
    to become ``None``, which the caller then converted to
    HTTP 404 ("day not found") — an incorrect and confusing signal for
    the operator. Now the exception bubbles up so the router can
    classify it. A row that legitimately does not exist still returns
    ``None`` via the successful SELECT path."""
    con = _connect()
    try:
        row = con.execute(
            "SELECT * FROM trip_days WHERE id = ?", (day_id,),
        ).fetchone()
        return _day_row_to_dict(row) if row else None
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

    # 2026-07-23 (follow-up) — cheap pre-flight validation.
    #
    # We used to compute start / end here from ``trip_get(trip_id)``
    # OUTSIDE the write transaction and rely on that snapshot for the
    # rest of the function. ChatGPT's post-1e388b5 review flagged the
    # race: two browser tabs saving a trip in quick succession can
    # interleave read → read → write → write, and the second writer
    # generates cards against the FIRST writer's stale dates.
    #
    # The fix (below) is to re-read the trip's start/end INSIDE the
    # BEGIN IMMEDIATE transaction and use that snapshot as the
    # generation window. We still do a pre-flight trip_get here so
    # that malformed dates fail fast with a ValueError BEFORE we
    # bother acquiring the write lock — an unusable window shouldn't
    # block another writer waiting on the same table. If the trip is
    # subsequently mutated between this pre-flight and BEGIN IMMEDIATE,
    # the transactional re-read wins.
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
        # 2026-07-23 — BEGIN IMMEDIATE upgrades the transaction to
        # writer-position at open time. SQLite's default deferred
        # transaction starts as a reader and only upgrades to writer
        # on the first write, which can fail with SQLITE_BUSY if
        # another writer is active in the interim. For the day-
        # generation + renumber sequence — short, single-writer,
        # critical — IMMEDIATE removes THAT specific deferred-to-
        # writer upgrade race: if we acquire the write lock at
        # transaction open, we hold it until commit. This does NOT
        # guarantee zero SQLITE_BUSY anywhere else in the pipeline
        # (SQLite can still surface BUSY on unrelated paths, on a
        # concurrent VACUUM/checkpoint, or on I/O contention) — it
        # narrows the specific "read-then-write" race that Chris's
        # ND live test hit. Per SQLite docs (WAL + short critical
        # writes best-practice; BEGIN IMMEDIATE contract).
        con.execute("BEGIN IMMEDIATE;")

        # 2026-07-23 (follow-up) — re-read the trip window INSIDE this
        # transaction so a concurrent PATCH cannot leave us generating
        # from a stale snapshot. If the concurrent writer moved the
        # window since our pre-flight, we honor the CURRENT dates.
        # A concurrent writer that made the window unusable (bad
        # dates, end < start) after our pre-flight is treated the
        # same way as if we'd been called with those dates — rollback
        # and raise ValueError. The pre-flight already ruled out the
        # common cases, so this is genuinely a race-only rollback path.
        snap = con.execute(
            "SELECT start_date, end_date FROM trips WHERE id = ?",
            (trip_id,),
        ).fetchone()
        if not snap:
            # Trip was deleted between pre-flight and BEGIN IMMEDIATE.
            raise ValueError("trip not found")
        snap_start_raw = (snap["start_date"] or "")[:10]
        snap_end_raw = (snap["end_date"] or "")[:10]
        if snap_start_raw != start_raw or snap_end_raw != end_raw:
            # Concurrent writer moved the window. Honor the new one,
            # re-validate under the same rules.
            if not snap_start_raw or not snap_end_raw:
                raise ValueError(
                    "trip window was cleared by a concurrent edit; "
                    "day cards not generated")
            try:
                start = _date.fromisoformat(snap_start_raw)
                end = _date.fromisoformat(snap_end_raw)
            except ValueError:
                raise ValueError(
                    "trip dates are not valid ISO dates "
                    "(changed under a concurrent edit)")
            if end < start:
                raise ValueError(
                    "trip end_date is before start_date "
                    "(changed under a concurrent edit)")
            if (end - start).days > 400:
                raise ValueError(
                    "trip window too large after a concurrent edit; "
                    "day cards not generated")

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

        # 2026-07-23 — day_index renumber pass.
        #
        # Previously: idx was computed while walking the current window,
        # so ONLY the newly-inserted rows got the "correct" idx for that
        # window. Any existing rows kept the day_index they got when
        # they were originally inserted — which was under a DIFFERENT
        # window if the operator later moved the start date. Concrete
        # bug: create 2026-07-14 to 2026-07-19 (Day 1..6), then patch
        # start_date to 2026-07-12 → new July 12 inserted as "Day 1",
        # existing July 14 still says "Day 1" too. Duplicate indexes,
        # scrambled UI order (which sorts by day_index, date).
        #
        # Fix: after any INSERTs, walk EVERY valid in-window day row in
        # chronological date order and set day_index = 1..N. Out-of-
        # range day cards keep their prior day_index untouched
        # (they're rendered separately in the reconcile drawer and
        # never mixed into the calendar order). The UPDATE is a
        # no-op for windows that were already correctly numbered, so
        # the cost is one row-scan on every reconcile — acceptable.
        #
        # Preserves EVERY other column: title, notes, places, meals,
        # region link, stop link, timestamps.
        #
        # 2026-07-23 (follow-up) — the previous version wrote
        # ``updated_at = _now()`` alongside the day_index change. That
        # made a structural calendar reshuffle (operator moves the
        # start date earlier → prior Day 3 is now Day 5) look like an
        # operator content edit on those rows. Any downstream consumer
        # that filters by updated_at (memoir "recently touched",
        # dashboards, sync jobs) got a stampede of false positives.
        # Now we UPDATE only ``day_index`` and leave updated_at alone.
        # The renumber is a pure calendar concern — it has no bearing
        # on when the row's content last changed.
        in_range_rows = con.execute(
            "SELECT id, date FROM trip_days "
            "WHERE trip_id = ? AND date >= ? AND date <= ? "
            "ORDER BY date ASC, id ASC",
            (trip_id, start.isoformat(), end.isoformat()),
        ).fetchall()
        for new_idx, row in enumerate(in_range_rows, start=1):
            con.execute(
                "UPDATE trip_days SET day_index = ? "
                "WHERE id = ? AND day_index != ?",
                (new_idx, row["id"], new_idx),
            )

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
    # [Took an `include_in_memoir` argument and wrote the column, for
    # the "Include this day in the travel document" tick. Removed
    # 2026-08-06 with that design. Migration 0042 stays applied so a
    # fresh installation matches Chris's database, and the column is
    # DORMANT -- nothing reads it and nothing writes it. Leaving the
    # writer in place would have kept a control alive with no reader,
    # which is how a dead field comes back to life by accident.]
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
    #
    # 2026-07-23 (follow-up, Bucket B) — the previous version wrapped
    # BOTH the outer 0028 query AND the inner date-fallback query in
    # bare ``except sqlite3.OperationalError: ... = {}``. That silently
    # converted EVERY operational failure — locks, I/O errors, missing
    # tables, unrelated malformed queries — into "zero photos" for
    # every day card. The whole point of ChatGPT's review §4 was:
    # a locked or damaged photo-counts query then LOOKS EXACTLY LIKE
    # a legitimate day with no evidence.
    #
    # Fix: swallow ONLY the specific pre-0028 signal ("no such column"
    # for the trip_day_id column that migration 0028 added). Every
    # other operational error re-raises to the caller so the router
    # can surface a counts_warning on the /days response. The inner
    # date-only query does NOT reference trip_day_id, so a failure
    # there is a real error (never a legacy signal) and re-raises
    # too.
    by_date: Dict[str, int] = {}
    by_day: Dict[str, int] = {}
    con = _connect()
    try:
        # WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01: hidden links never count
        # on a day card (honest-counts rule — a hidden photo must not
        # look like present evidence). Probed once, applied to every
        # branch including the pre-0028 fallback.
        _hidden_where = ("  AND l.hidden = 0\n"
                         if _table_has_column(
                             con, "trip_photo_links", "hidden")
                         else "")
        try:
            rows = con.execute(
                """SELECT l.trip_day_id AS d, COUNT(*) AS n
                   FROM trip_photo_links l
                   LEFT JOIN photos p ON p.id = l.photo_id
                   WHERE l.trip_id = ?
                     AND l.trip_day_id IS NOT NULL
                     AND (p.id IS NULL OR p.deleted_at IS NULL)
                """ + _hidden_where + """
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
                """ + _hidden_where + """
                   GROUP BY d""",
                (trip_id,),
            ).fetchall()
            by_date = {str(r["d"]): int(r["n"]) for r in rows if r["d"]}
        except sqlite3.OperationalError as exc:
            # Pre-0028 DB fallback: swallow ONLY the exact "no such
            # column" for the trip_day_id column. Anything else — a
            # lock, an I/O failure, a missing trip_photo_links
            # TABLE (pre-0015), any unrelated SQL error — must
            # re-raise so the caller can surface it honestly.
            msg = str(exc).lower()
            if ("no such column" in msg
                    and "trip_day_id" in msg):
                # Confirmed pre-0028 signal: fall back to date-only.
                # The inner query does not reference trip_day_id;
                # any failure there is a REAL error, not a legacy
                # signal, so it re-raises unchecked.
                by_day = {}
                rows = con.execute(
                    """SELECT substr(COALESCE(l.taken_at, p.date_value), 1, 10)
                              AS d, COUNT(*) AS n
                       FROM trip_photo_links l
                       LEFT JOIN photos p ON p.id = l.photo_id
                       WHERE l.trip_id = ?
                         AND (p.id IS NULL OR p.deleted_at IS NULL)
                         AND COALESCE(l.taken_at, p.date_value) IS NOT NULL
                    """ + _hidden_where + """
                       GROUP BY d""",
                    (trip_id,),
                ).fetchall()
                by_date = {str(r["d"]): int(r["n"]) for r in rows if r["d"]}
            else:
                # Not the legacy signal — real failure, re-raise so
                # the router can classify + surface counts_warning.
                raise
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



# ── What a day card actually holds (WO-TRIP-PLAN-AS-HUB-01 Phase A) ───────
#
# Two different questions, two different answers, and conflating them is
# the bug this section exists to prevent:
#
#   "What should this card show?"  -> trip_day_counts, above. Generous
#      on purpose: photos matched by taken-date, notes and sources
#      inherited through the day's stop or region. The operator wants to
#      see what belongs to that date, however it got there.
#
#   "What would removing this card destroy?"  -> the functions below.
#      Strict on purpose: only rows fastened to this day by trip_day_id,
#      plus the text typed into the day row itself. Everything the
#      generous answer adds survives the delete untouched -- the photo
#      link keeps its taken_at, the region-scoped note keeps its region.
#
# Answering the second question with the first one's numbers would be
# safe in the trivial sense and useless in practice: trip_days_generate
# auto-fills trip_region_id, so on a trip with any region-scoped notes
# every generated card reports content, and a rule that removes empty
# cards would never find one.

# Operator-typed fields that live IN the trip_days row and die with it.
# trip_region_id is absent deliberately: generation fills it in from the
# region date ranges, so its presence says nothing about whether a
# person has touched this card. trip_stop_id is present for the mirror
# reason -- nothing sets it but a person.
DAY_OWN_TEXT_FIELDS = (
    "title", "main_location", "lodging_base",
    "morning_notes", "afternoon_notes", "evening_notes",
)
DAY_OWN_LIST_FIELDS = ("places_visited_json", "meals_json")


def day_own_content(day: Dict[str, Any]) -> List[str]:
    """Names of the day row's own fields that carry operator content.

    Empty list means the row is a bare generated card: a date, an index,
    and whatever the generator filled in. Order is stable so a caller can
    show it to a person without sorting it first."""
    held: List[str] = []
    for f in DAY_OWN_TEXT_FIELDS:
        if str(day.get(f) or "").strip():
            held.append(f)
    for f in DAY_OWN_LIST_FIELDS:
        v = day.get(f)
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except Exception:
                v = []
        if v:
            held.append(f)
    if day.get("trip_stop_id"):
        held.append("trip_stop_id")
    return held


def _day_attachment_counts(con: sqlite3.Connection,
                           trip_id: str) -> Dict[str, Dict[str, int]]:
    """Rows fastened to each day by trip_day_id, keyed by day id.

    Takes an open connection so the caller can run this INSIDE the same
    transaction as a delete. A count read outside the write lock and
    acted on inside it is exactly the read-then-write race that
    trip_days_generate was already corrected for on 2026-07-23.

    Hidden photo links count. A hidden link is still an attachment: the
    delete would null its trip_day_id and the operator would unhide it
    later onto no day at all. Honest-counts (a hidden photo must not
    look like present evidence) governs what a card DISPLAYS; it has no
    bearing on what a delete would detach.

    A pre-0028 / pre-0029 database has no trip_day_id column on one or
    more of these tables, which means nothing can be attached through
    it, which means zero -- that specific absence is the one thing
    swallowed here. Every other operational error re-raises, because a
    lock or an I/O failure reported as "zero attachments" would license
    a delete on a day nobody could read."""
    out: Dict[str, Dict[str, int]] = {}

    def _tally(table: str, bucket: str) -> None:
        if not _table_has_column(con, table, "trip_day_id"):
            return
        rows = con.execute(
            "SELECT trip_day_id AS d, COUNT(*) AS n FROM " + table
            + " WHERE trip_id = ? AND trip_day_id IS NOT NULL"
              " GROUP BY trip_day_id",
            (trip_id,),
        ).fetchall()
        for r in rows:
            did = str(r["d"] or "")
            if not did:
                continue
            slot = out.setdefault(
                did, {"photos": 0, "notes": 0, "sources": 0})
            slot[bucket] = int(r["n"])

    _tally("trip_photo_links", "photos")
    _tally("trip_location_notes", "notes")
    _tally("trip_sources", "sources")
    return out


def trip_day_attached_counts(trip_id: str) -> Dict[str, Dict[str, int]]:
    """Public read-only wrapper over _day_attachment_counts."""
    con = _connect()
    try:
        return _day_attachment_counts(con, trip_id)
    finally:
        con.close()


def _day_is_empty(day: Dict[str, Any],
                  attached: Dict[str, Dict[str, int]]) -> bool:
    """True when removing this day row would destroy or detach nothing."""
    if day_own_content(day):
        return False
    a = attached.get(str(day.get("id")), {})
    return not (a.get("photos") or a.get("notes") or a.get("sources"))


# ── Trip-day date-range reconcile (WO-TRAVEL-DOC-UI-LAB-03) ────────────────
#
# When trip start/end dates change AFTER day cards exist, generation only
# appends missing dates — it never deletes operator work. The reconcile
# pair below makes that state visible and operator-resolvable:
#   * preview — read-only diff of the trip window vs. existing day rows.
#   * reconcile — add missing in-range days, acknowledge out-of-range
#     days (reconcile_status, migration 0029), and, since 2026-07-28,
#     drop the out-of-range days that hold nothing.
#
# [This block ended "NOTHING is ever deleted; out-of-range day cards are
# kept to protect notes." until 2026-07-28. See the retirement note in
# trip_days_reconcile's docstring for why that rule was right and why it
# was not sufficient. The half of it that still holds, and always will:
# a day card that holds anything is never deleted here, by any flag.]

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
    called missing or out of range).

    2026-07-28 (WO-TRIP-PLAN-AS-HUB-01 Phase A) — each out-of-range row
    additionally carries ``holds`` {photos, notes, sources, own} and
    ``is_empty``, so a caller can tell the two out-of-range cases apart
    without a second round trip: a bare generated card the dates moved
    past, and a card somebody worked on. ``holds`` counts ATTACHED rows
    only and is a different number from the ``counts`` the /days route
    merges in — see the section above for why the display number is the
    wrong one to make a delete decision with. Still read-only."""
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

    # Only pay for the attachment queries when there is something to
    # describe. A trip whose dates never moved has no out-of-range rows
    # and this preview runs on every load of the surface.
    if out_of_range:
        con = _connect()
        try:
            attached = _day_attachment_counts(con, trip_id)
        finally:
            con.close()
        for d in out_of_range:
            a = attached.get(str(d.get("id")), {})
            own = day_own_content(d)
            d["holds"] = {
                "photos": int(a.get("photos", 0)),
                "notes": int(a.get("notes", 0)),
                "sources": int(a.get("sources", 0)),
                "own": own,
            }
            d["is_empty"] = _day_is_empty(d, attached)

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
    drop_empty_out_of_range: bool = False,
) -> Dict[str, Any]:
    """Apply the operator-requested reconcile actions.

    * ``add_missing`` creates ONLY the missing in-range day rows — it
      delegates to trip_days_generate, which skips every existing date,
      so operator-edited day cards are never overwritten.
    * ``mark_out_of_range`` stamps reconcile_status =
      'out_of_range_acknowledged' on out-of-range day rows, and resets
      in-range rows that were previously acknowledged back to 'active'
      (honest status when trip dates change again).
    * ``drop_empty_out_of_range`` deletes out-of-range day rows that
      hold nothing — no rows attached by trip_day_id, no text in the
      row itself (see _day_is_empty). A day that holds anything is left
      exactly where it is and reported back in ``kept_out_of_range``.

    2026-07-28 (WO-TRIP-PLAN-AS-HUB-01 Phase A) — this function used to
    end: "NOTHING is ever deleted here — out-of-range day cards are kept
    to protect the operator's notes." That stopped being true when
    ``drop_empty_out_of_range`` was added on Chris's instruction:

        Implement the complete shrinking-date rule: remove empty
        out-of-range days; refuse and clearly list out-of-range days
        containing work.

    The reason the old sentence was right and is no longer sufficient:
    it was written for the reconcile drawer, where an operator reviews
    cards one at a time and every card on screen is one somebody might
    want. It also had to cover the case where nobody could tell an
    untouched card from a worked-on one, because until now nothing here
    could. A bare generated card that the trip dates moved past holds no
    notes to protect, and leaving it drawn under a header that says the
    trip ended three days earlier is its own kind of dishonesty.

    What did NOT change: a day card that holds anything is still never
    deleted by this function, by any flag, and the emptiness test is
    re-run inside the write transaction rather than trusted from the
    preview. Migration 0029's header comment still states the older,
    absolute rule; it is left as written because an applied migration is
    a record of what that migration did."""
    preview = trip_days_reconcile_preview(trip_id)
    added = 0
    if add_missing and preview["missing_dates"]:
        added = trip_days_generate(trip_id)["created"]

    dropped: List[Dict[str, Any]] = []
    kept: List[Dict[str, Any]] = []
    if drop_empty_out_of_range:
        # Re-preview: an add_missing in the same call can have moved
        # rows in or out of range, and acting on the stale list would
        # delete against a window that no longer applies.
        fresh = trip_days_reconcile_preview(trip_id)
        candidates = [d for d in fresh["out_of_range_days"]
                      if d.get("is_empty")]
        if candidates:
            con = _connect()
            try:
                # BEGIN IMMEDIATE for the same reason trip_days_generate
                # takes it: the emptiness test and the delete have to be
                # one decision. Reading "empty" outside the write lock
                # and deleting inside it is a window in which another
                # tab attaches a photo to a card this call then removes.
                con.execute("BEGIN IMMEDIATE;")
                attached = _day_attachment_counts(con, trip_id)
                for d in candidates:
                    did = str(d["id"])
                    row = con.execute(
                        "SELECT * FROM trip_days WHERE id = ?", (did,),
                    ).fetchone()
                    if row is None:
                        continue          # already gone; nothing to do
                    live = _day_row_to_dict(row)
                    if not _day_is_empty(live, attached):
                        # It filled up between the preview and the lock.
                        kept.append({"id": did, "date": live.get("date")})
                        continue
                    con.execute("DELETE FROM trip_days WHERE id = ?", (did,))
                    dropped.append({"id": did, "date": live.get("date")})
                con.commit()
            except Exception:
                con.rollback()
                raise
            finally:
                con.close()

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
        "dropped_empty_out_of_range": len(dropped),
        "dropped_days": dropped,
        "kept_out_of_range": kept,
        "preview": trip_days_reconcile_preview(trip_id),
    }


# ═══════════════════════════════════════════════════════════════════
#  WO-LIVE-TRIP-COMPANION-01 Vertical Slice 1 (2026-07-30)
#  Trip lifecycle, remembered day selection, and turn placement.
#
#  Everything below reads or writes only the two things migration 0039
#  added: the two new columns on `trips`, and the `trip_turn_links`
#  table. Nothing here writes narrative content, family truth, or a
#  correction projection.
# ═══════════════════════════════════════════════════════════════════

# The lived lifecycle of a journey. Deliberately NOT trips.status,
# which is the authoring state of the write-up. See migration 0039 for
# why the two are separate columns rather than one merged enum.
LIVE_STATES = ("planning", "active", "completed", "archived")

# How a conversation's day was chosen.
PLACEMENT_SOURCES = (
    "active_trip_day",      # the narrator was on this trip, on this day
    "travels_shelf_trip",   # he opened a finished trip and told a story
    "operator_selected",    # a human moved it here
    "timestamp_suggested",  # derived from a timestamp, not yet accepted
    "later_reconciled",     # placed after the fact by a repair pass
)
# WO-TRIP-NARRATOR-BRIDGE-01 added 'travels_shelf_trip'. It had to be
# added HERE and not only at the call site: an unrecognized source is
# silently rewritten to 'active_trip_day' twenty lines below, so a link
# created from the shelf would have claimed the narrator was live on the
# trip that day. The coercion is a reasonable default for a typo and a
# quiet forgery for a new vocabulary word, which is why every new word
# lands in this tuple in the same commit as the code that emits it.

# Whether a human has accepted the placement. `needs_day` is the
# reconciliation item required by the work order ("A failure to link the
# trip should not lose the conversation"), not an error to be cleaned up.
PLACEMENT_STATUSES = ("suggested", "confirmed", "needs_day", "rejected")


class TripStateError(Exception):
    """A refused lifecycle transition, carrying the reason.

    Raised rather than silently corrected. Starting a second trip while
    one is already active is the case this exists for: the work order
    requires the operator to start and finish trips deliberately, so the
    right response is to name the trip that is in the way, not to demote
    it behind the operator's back.
    """

    def __init__(self, message: str, conflict: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.conflict = conflict or {}


def _trips_has_live_state(con: sqlite3.Connection) -> bool:
    """True once migration 0039 has been applied.

    Every accessor below checks this. A DB that has not been migrated
    yet must degrade to "no active trip" rather than raise, because the
    completed-turn hook runs on every interview turn and a missing
    column must never be able to break a conversation.
    """
    return _table_has_column(con, "trips", "live_state")


def trip_live_state_set(trip_id: str, state: str) -> Dict[str, Any]:
    """Move a trip through the lived lifecycle. Returns the updated trip.

    Refuses, rather than resolves, the one conflict that matters: a
    narrator may be on only one trip at a time. The partial unique index
    ux_trips_one_live_active_per_person would refuse it anyway; this
    check runs first only so the caller gets a message naming the other
    trip instead of a bare IntegrityError.
    """
    state = str(state or "").strip().lower()
    if state not in LIVE_STATES:
        raise TripStateError(
            "unknown trip state: " + repr(state)
            + " (expected one of " + ", ".join(LIVE_STATES) + ")")

    con = _connect()
    try:
        if not _trips_has_live_state(con):
            raise TripStateError(
                "this database has not applied migration 0039, so trips "
                "have no live state yet")

        row = con.execute(
            "SELECT id, person_id, title, live_state FROM trips WHERE id=?;",
            (trip_id,)).fetchone()
        if not row:
            raise TripStateError("trip not found: " + str(trip_id))

        if state == "active":
            other = con.execute(
                "SELECT id, title FROM trips "
                "WHERE person_id=? AND live_state='active' AND id<>?;",
                (row["person_id"], trip_id)).fetchone()
            if other:
                raise TripStateError(
                    "another trip is already active for this narrator; "
                    "finish it before starting a new one",
                    # Keyed "id", not "trip_id": every other trip payload
                    # this API returns carries the trip under "id", and a
                    # conflict the UI has to render ("finish <title> first")
                    # is one of those payloads, not a different shape.
                    conflict={"id": other["id"],
                              "title": other["title"]})

        now = _now()
        # Leaving 'active' clears the remembered day. A day selection is
        # meaningful only while the narrator is on the trip; keeping it
        # would make a completed trip reopen onto a day chosen months
        # earlier and look like live state that is not live.
        if state == "active":
            con.execute(
                "UPDATE trips SET live_state=?, updated_at=? WHERE id=?;",
                (state, now, trip_id))
        else:
            con.execute(
                "UPDATE trips SET live_state=?, active_trip_day_id=NULL, "
                "updated_at=? WHERE id=?;",
                (state, now, trip_id))
        con.commit()
    finally:
        con.close()

    updated = trip_get(trip_id)
    return updated or {}


def trip_active_get(person_id: str) -> Optional[Dict[str, Any]]:
    """The one trip this narrator is currently on, or None.

    This is the durable answer to "which trip is Lori working on". It is
    read from the database on every completed turn and on every page
    load, which is what makes the placement survive a restart -- the
    browser's ``runtime71.active_trip_id`` is a convenience for the
    current tab and is never the authority.
    """
    person_id = str(person_id or "").strip()
    if not person_id:
        return None
    con = _connect()
    try:
        if not _trips_has_live_state(con):
            return None
        row = con.execute(
            "SELECT * FROM trips WHERE person_id=? AND live_state='active' "
            "ORDER BY updated_at DESC LIMIT 1;", (person_id,)).fetchone()
        return _row_to_dict(row) if row else None
    except Exception:
        # An interview turn must not fail because the trip lane is
        # unreadable. No active trip is a valid answer; a broken turn
        # is not. Deliberately broader than sqlite3.Error: the schema
        # probe can raise ValueError, and the caller cannot tell the
        # difference between "unreadable" and "unmigrated" anyway.
        return None
    finally:
        con.close()


def trip_selected_day_set(trip_id: str, trip_day_id: Optional[str]) -> Dict[str, Any]:
    """Remember which day the operator has open. Returns the updated trip.

    Validated against the trip so a day from another trip can never
    become the destination for this trip's conversations.
    """
    con = _connect()
    try:
        if not _trips_has_live_state(con):
            raise TripStateError(
                "this database has not applied migration 0039")
        trip_row = con.execute(
            "SELECT id FROM trips WHERE id=?;", (trip_id,)).fetchone()
        if not trip_row:
            raise TripStateError("trip not found: " + str(trip_id))

        day_id = str(trip_day_id or "").strip() or None
        if day_id:
            owns = con.execute(
                "SELECT 1 FROM trip_days WHERE id=? AND trip_id=?;",
                (day_id, trip_id)).fetchone()
            if not owns:
                raise TripStateError(
                    "that day does not belong to this trip")

        con.execute(
            "UPDATE trips SET active_trip_day_id=?, updated_at=? WHERE id=?;",
            (day_id, _now(), trip_id))
        con.commit()
    finally:
        con.close()
    return trip_get(trip_id) or {}


def trip_day_for_date(trip_id: str, date_text: str) -> Optional[Dict[str, Any]]:
    """The day card whose date matches, or None.

    Used only as a SUGGESTION source. A match here produces
    placement_source='timestamp_suggested' and placement_status=
    'suggested', never 'confirmed' -- the travel-document rule that a
    date suggestion is not an operator choice applies to conversations
    exactly as it applies to photographs.
    """
    d = str(date_text or "").strip()[:10]
    if not d:
        return None
    con = _connect()
    try:
        row = con.execute(
            "SELECT * FROM trip_days WHERE trip_id=? AND date=? LIMIT 1;",
            (trip_id, d)).fetchone()
        return _day_row_to_dict(row) if row else None
    except sqlite3.Error:
        return None
    finally:
        con.close()


def trip_turn_link_claim(
    trip_id: str,
    assistant_turn_row_id: int,
    trip_day_id: Optional[str] = None,
    user_turn_row_id: Optional[int] = None,
    conv_id: str = "",
    captured_at: str = "",
    placement_source: str = "active_trip_day",
    placement_status: str = "confirmed",
) -> Dict[str, Any]:
    """Place one persisted turn on one trip day. Idempotent by the database.

    Returns ``{"outcome": "created"|"duplicate"|"rejected"|"noop",
    "link": {...}}``.

    The idempotency mechanism is the UNIQUE INDEX on
    assistant_turn_row_id, not a lookup-then-insert: two concurrent
    completed-turn hooks for the same turn both attempt the INSERT and
    exactly one wins. The loser reads the winner's row and reports
    'duplicate'. This is the same shape as the extraction ledger claim
    in migration 0038, keyed off the same committed assistant row, so a
    turn's extraction record and its trip placement can never disagree
    about which turn they describe.

    A 'duplicate' result deliberately does NOT overwrite the existing
    placement. If a human has moved a conversation to another day, a
    replayed turn must not drag it back.

    'rejected' means the database refused the row for some reason that
    is not idempotency -- a CHECK, a foreign key, a NOT NULL. Nothing
    was written and nothing will be until the cause is removed. It is
    reported separately from 'duplicate' because the two look identical
    from the exception (both are sqlite3.IntegrityError) and mean
    opposite things to the caller: one says the turn is already placed,
    the other says it is placed nowhere.
    """
    if not trip_id or not assistant_turn_row_id:
        return {"outcome": "noop", "link": None}

    source = str(placement_source or "").strip() or "active_trip_day"
    status = str(placement_status or "").strip() or "confirmed"
    if source not in PLACEMENT_SOURCES:
        source = "active_trip_day"
    if status not in PLACEMENT_STATUSES:
        status = "confirmed"
    # A conversation with no resolvable day is the reconciliation item,
    # and it must say so rather than claim to be confirmed on nothing.
    if not trip_day_id:
        status = "needs_day"

    now = _now()
    link_id = _new_id()
    con = _connect()
    try:
        try:
            con.execute(
                "INSERT INTO trip_turn_links("
                "id, trip_id, trip_day_id, conv_id, user_turn_row_id, "
                "assistant_turn_row_id, captured_at, placement_source, "
                "placement_status, created_at, updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?);",
                (link_id, trip_id, trip_day_id, str(conv_id or ""),
                 user_turn_row_id, int(assistant_turn_row_id),
                 str(captured_at or ""), source, status, now, now),
            )
            con.commit()
            outcome = "created"
        except sqlite3.IntegrityError:
            con.rollback()
            # A refused INSERT is not automatically a duplicate. The
            # UNIQUE index on assistant_turn_row_id raises
            # IntegrityError, and so does every CHECK on this table, so
            # the exception class cannot tell "already placed" from
            # "not allowed". Asking the database which one happened --
            # is there a row for this turn or is there not -- is the
            # only answer that does not go stale the next time someone
            # adds a constraint.
            #
            # WO-TRIP-NARRATOR-BRIDGE-01: this was an unconditional
            # "duplicate". When 'travels_shelf_trip' was added to
            # PLACEMENT_SOURCES but not yet to the schema CHECK, every
            # shelf placement was refused by the database and reported
            # to the caller as already-placed, which
            # PlacementOutcome.linked reads as "a link row now exists".
            # Nothing existed. The turn was delivered and attached to
            # nothing, silently, which is the failure the work order
            # exists to end.
            outcome = "duplicate" if con.execute(
                "SELECT 1 FROM trip_turn_links "
                "WHERE assistant_turn_row_id=?;",
                (int(assistant_turn_row_id),)).fetchone() else "rejected"

        row = con.execute(
            "SELECT * FROM trip_turn_links WHERE assistant_turn_row_id=?;",
            (int(assistant_turn_row_id),)).fetchone()
        return {"outcome": outcome,
                "link": _row_to_dict(row) if row else None}
    finally:
        con.close()


def trip_turn_link_move(link_id: str, trip_day_id: Optional[str]) -> Dict[str, Any]:
    """An operator moves a conversation to another day of the same trip.

    Sets placement_source='operator_selected' and status='confirmed',
    because a human choosing a day IS the confirmation. Moving to no day
    is allowed and returns the row to the reconciliation state.
    """
    con = _connect()
    try:
        row = con.execute(
            "SELECT * FROM trip_turn_links WHERE id=?;", (link_id,)).fetchone()
        if not row:
            raise TripStateError("link not found: " + str(link_id))
        day_id = str(trip_day_id or "").strip() or None
        if day_id:
            owns = con.execute(
                "SELECT 1 FROM trip_days WHERE id=? AND trip_id=?;",
                (day_id, row["trip_id"])).fetchone()
            if not owns:
                raise TripStateError("that day does not belong to this trip")
        con.execute(
            "UPDATE trip_turn_links SET trip_day_id=?, "
            "placement_source='operator_selected', placement_status=?, "
            "updated_at=? WHERE id=?;",
            (day_id, "confirmed" if day_id else "needs_day", _now(), link_id))
        con.commit()
        moved = con.execute(
            "SELECT * FROM trip_turn_links WHERE id=?;", (link_id,)).fetchone()
        return _row_to_dict(moved) if moved else {}
    finally:
        con.close()


def trip_turn_links_list(trip_id: str,
                         trip_day_id: Optional[str] = None,
                         include_unplaced: bool = False) -> List[Dict[str, Any]]:
    """Placement rows for a trip, optionally narrowed to one day."""
    con = _connect()
    try:
        # WO-TRAVEL-DOC-CLOSEOUT-01: 'rejected' is the placement the
        # operator threw away. It was already invisible in practice
        # because nothing rendered it, but the export is built from this
        # read now, so the exclusion has to be real rather than
        # incidental.
        _live = " AND placement_status != 'rejected' "
        if trip_day_id:
            sql = ("SELECT * FROM trip_turn_links WHERE trip_id=? AND "
                   "trip_day_id=?" + _live +
                   "ORDER BY captured_at, assistant_turn_row_id;")
            rows = con.execute(sql, (trip_id, trip_day_id)).fetchall()
        elif include_unplaced:
            rows = con.execute(
                "SELECT * FROM trip_turn_links WHERE trip_id=? AND "
                "trip_day_id IS NULL" + _live +
                "ORDER BY captured_at, assistant_turn_row_id;",
                (trip_id,)).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM trip_turn_links WHERE trip_id=? "
                "ORDER BY captured_at, assistant_turn_row_id;",
                (trip_id,)).fetchall()
        return [_row_to_dict(r) for r in rows]
    except sqlite3.Error:
        return []
    finally:
        con.close()


def trip_turn_link_counts(trip_id: str) -> Dict[str, int]:
    """Conversation count per day id, plus 'unplaced' for NULL days.

    Feeds the calendar's per-date indicators. Counts only -- the
    calendar shows that something happened on a day, never what was
    said.
    """
    out: Dict[str, int] = {}
    con = _connect()
    try:
        for row in con.execute(
            "SELECT trip_day_id, COUNT(*) AS n FROM trip_turn_links "
            "WHERE trip_id=? GROUP BY trip_day_id;", (trip_id,)
        ):
            key = row["trip_day_id"] or "unplaced"
            out[key] = int(row["n"])
        return out
    except sqlite3.Error:
        return {}
    finally:
        con.close()


def trip_day_conversation_items(trip_id: str,
                                trip_day_id: Optional[str]) -> List[Dict[str, Any]]:
    """Timeline items for the conversations placed on one day.

    THE TEXT IS READ BACK OUT OF `turns`, NOT OUT OF THE LINK TABLE.
    That is the whole point of the link table being a link table: there
    is one conversation store, and this projects it. If a turn is edited
    or removed in `turns`, the timeline follows automatically because it
    never held a copy.

    Pass trip_day_id=None to get the trip's unplaced conversations --
    the reconciliation items.
    """
    links = trip_turn_links_list(
        trip_id, trip_day_id,
        include_unplaced=(trip_day_id is None))
    if not links:
        return []

    ids: List[int] = []
    for link in links:
        for key in ("user_turn_row_id", "assistant_turn_row_id"):
            v = link.get(key)
            if isinstance(v, int):
                ids.append(v)
    if not ids:
        return []

    texts: Dict[int, Dict[str, Any]] = {}
    con = _connect()
    try:
        marks = ",".join("?" for _ in ids)
        for row in con.execute(
            "SELECT id, role, content, ts FROM turns WHERE id IN (" + marks + ");",
            ids,
        ):
            texts[int(row["id"])] = {
                "role": row["role"], "content": row["content"], "ts": row["ts"]}
    except sqlite3.Error:
        texts = {}
    finally:
        con.close()

    items: List[Dict[str, Any]] = []
    for link in links:
        a_id = link.get("assistant_turn_row_id")
        u_id = link.get("user_turn_row_id")
        assistant = texts.get(a_id) if isinstance(a_id, int) else None
        user = texts.get(u_id) if isinstance(u_id, int) else None
        when = (link.get("captured_at")
                or (user or {}).get("ts")
                or (assistant or {}).get("ts")
                or "")
        # ── A DIRECTIVE IS NOT SOMETHING THE NARRATOR SAID ───────────
        #
        # `[SYSTEM: ...]` turns are instructions this system sends to
        # Lori through the user channel -- "the narrator has been quiet
        # for a while", "the narrator just opened their trip". They are
        # stored in `turns` with role='user', so a projection that reads
        # the column and stops there attributes them to the narrator.
        # In the exported document that appeared as
        #
        #     Christopher: [SYSTEM: The narrator has been quiet for a
        #     while. Offer a gentle, warm invitation...]
        #
        # which puts words in a man's mouth in the artefact his family
        # reads. Same class as the directive-concatenation bug of
        # 2026-07-14, one layer further out.
        #
        # The narrator half is dropped and the fact is recorded rather
        # than hidden: Lori's reply is real and stays, and
        # `narrator_directive` lets any surface say why there is nothing
        # above it. The text is NOT rendered anywhere.
        _said = str((user or {}).get("content") or "")
        _is_directive = _said.lstrip().startswith("[SYSTEM")
        items.append({
            "kind": "conversation",
            "link_id": link.get("id"),
            "trip_day_id": link.get("trip_day_id"),
            "conv_id": link.get("conv_id"),
            "at": when,
            "placement_source": link.get("placement_source"),
            "placement_status": link.get("placement_status"),
            # Source navigation: the ids the UI needs to open the
            # underlying conversation at the right turn.
            "user_turn_row_id": u_id,
            "assistant_turn_row_id": a_id,
            "narrator_said": "" if _is_directive else _said,
            "narrator_directive": _is_directive,
            "lori_said": (assistant or {}).get("content") or "",
        })
    items.sort(key=lambda i: (str(i.get("at") or ""),
                             i.get("assistant_turn_row_id") or 0))
    return items


# ── The day timeline ───────────────────────────────────────────────────────
#
# WO-LIVE-TRIP-COMPANION-01 VS1, corrected 2026-07-30 after the first
# live run.
#
# The first cut of this projected trip_turn_links and nothing else, so a
# day that already held a photograph and a story note reported "nothing
# has been recorded on this day yet". That sentence was false, and it
# was false in the one place the operator goes to find out what a day
# held. A timeline that can only see the newest table is not a timeline;
# it is a view of the newest table.
#
# So this is a READ PROJECTION over everything already fastened to a
# trip day, and it owns no storage of its own. Every item is read live
# from the table that already holds it -- turns, trip_photo_links,
# trip_location_notes, trip_sources, and the day row's own operator
# text. Nothing is copied forward, which is what makes an edit anywhere
# else show up here without a sync step, and what stops this from
# becoming the second data model the work order forbids.
#
# HIDDEN ROWS DO NOT APPEAR. Honest-counts governs display: a hidden
# photo must not read as present evidence. (_day_attachment_counts
# counts hidden rows on purpose, because it answers a different
# question -- what a delete would detach -- and that answer must
# include rows the operator cannot currently see.)

DAY_TIMELINE_KINDS = ("conversation", "photo", "note", "source", "day_text")

_DAY_TEXT_LABELS = {
    "morning_notes": "Morning",
    "afternoon_notes": "Afternoon",
    "evening_notes": "Evening",
    "main_location": "Where we were",
    "lodging_base": "Where we stayed",
}


def _timeline_hidden_clause(con: sqlite3.Connection, table: str,
                            alias: str) -> str:
    """`AND alias.hidden = 0`, or nothing on a database without it."""
    if _table_has_column(con, table, "hidden"):
        return " AND " + alias + ".hidden = 0 "
    return ""


def _day_photo_items(con: sqlite3.Connection, trip_id: str,
                     day_id: str) -> List[Dict[str, Any]]:
    """Photographs fastened to this day.

    No path, no URL and no coordinate crosses this boundary. The
    interface already builds its thumbnail from
    /api/photos/{id}/thumb, so a photo_id is the whole of what it
    needs, and a storage path here would be an operator-surface leak
    for no gain.
    """
    if not _table_has_column(con, "trip_photo_links", "trip_day_id"):
        return []
    # WO-TRAVEL-DOC-CLOSEOUT-01 (2026-08-06): a soft-deleted photograph
    # is not visible material and must not reach the timeline or the
    # document. `p.deleted_at IS NULL` is TRUE for a LEFT JOIN miss, so
    # a link whose photo row is absent entirely still comes through as
    # it did before -- only genuinely deleted photographs are dropped.
    sql = ("SELECT l.id AS link_id, l.photo_id, l.taken_at, l.ord, "
           "       l.caption, l.narrator_caption, "
           "       p.description AS photo_description "
           "  FROM trip_photo_links l "
           "  LEFT JOIN photos p ON p.id = l.photo_id "
           " WHERE l.trip_id = ? AND l.trip_day_id = ? "
           "   AND p.deleted_at IS NULL "
           + _timeline_hidden_clause(con, "trip_photo_links", "l") +
           " ORDER BY l.taken_at, l.ord")
    out: List[Dict[str, Any]] = []
    for r in con.execute(sql, (trip_id, day_id)):
        row = _row_to_dict(r)
        # ── CAPTION PROVENANCE ───────────────────────────────────────
        #
        # This used to collapse three different things into one string:
        # `narrator_caption or caption or photo_description`. The third
        # is MACHINE text -- a vision description this system generated
        # -- and once flattened it was indistinguishable from something
        # Chris had written about his own photograph, on the timeline
        # and in anything built from it.
        #
        # The choice is unchanged; what is added is a name for which of
        # the three won, so both the timeline and the document can say
        # "draft, machine-written" where that is the truth. A caption is
        # never silently attributed to a person who did not write it.
        _narr = str(row.get("narrator_caption") or "").strip()
        _oper = str(row.get("caption") or "").strip()
        _mach = str(row.get("photo_description") or "").strip()
        if _narr:
            _cap, _src = _narr, "narrator"
        elif _oper:
            _cap, _src = _oper, "operator"
        elif _mach:
            _cap, _src = _mach, "machine"
        else:
            _cap, _src = "", ""
        out.append({
            "kind": "photo",
            "id": row.get("link_id"),
            "link_id": row.get("link_id"),
            "photo_id": row.get("photo_id"),
            "at": row.get("taken_at") or "",
            "ord": row.get("ord") or 0,
            "caption": _cap,
            "caption_source": _src,
        })
    return out


def _day_note_items(con: sqlite3.Connection, trip_id: str,
                    day_id: str) -> List[Dict[str, Any]]:
    """Story notes and location notes fastened to this day."""
    if not _table_has_column(con, "trip_location_notes", "trip_day_id"):
        return []
    sql = ("SELECT n.id, n.note_title, n.note_text, n.source_type, "
           "       n.source_surface, n.created_at, n.ord "
           "  FROM trip_location_notes n "
           " WHERE n.trip_id = ? AND n.trip_day_id = ? "
           + _timeline_hidden_clause(con, "trip_location_notes", "n") +
           " ORDER BY n.created_at, n.ord")
    out: List[Dict[str, Any]] = []
    for r in con.execute(sql, (trip_id, day_id)):
        row = _row_to_dict(r)
        out.append({
            "kind": "note",
            "id": row.get("id"),
            "note_id": row.get("id"),
            "at": row.get("created_at") or "",
            "ord": row.get("ord") or 0,
            "title": row.get("note_title") or "",
            "text": row.get("note_text") or "",
            "source_type": row.get("source_type") or "",
            "source_surface": row.get("source_surface") or "",
        })
    return out


def _day_source_items(con: sqlite3.Connection, trip_id: str,
                      day_id: str) -> List[Dict[str, Any]]:
    """Sources fastened to this day.

    `storage_path` and `filename` are read but never projected: the
    operator sees a title and a kind, which is the plain language the
    travel workspace uses everywhere else.
    """
    if not _table_has_column(con, "trip_sources", "trip_day_id"):
        return []
    sql = ("SELECT s.id, s.title, s.source_type, s.summary, s.link_url, "
           "       s.source_date, s.created_at, s.ord "
           "  FROM trip_sources s "
           " WHERE s.trip_id = ? AND s.trip_day_id = ? "
           + _timeline_hidden_clause(con, "trip_sources", "s") +
           " ORDER BY s.created_at, s.ord")
    out: List[Dict[str, Any]] = []
    for r in con.execute(sql, (trip_id, day_id)):
        row = _row_to_dict(r)
        out.append({
            "kind": "source",
            "id": row.get("id"),
            "source_id": row.get("id"),
            "at": row.get("source_date") or row.get("created_at") or "",
            "ord": row.get("ord") or 0,
            "title": row.get("title") or "",
            "source_type": row.get("source_type") or "",
            "summary": row.get("summary") or "",
            "link_url": row.get("link_url") or "",
        })
    return out


def _day_own_text_items(day: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The day row's own operator text, places and meals.

    These are not attachments -- they live on the day card itself --
    but the operator wrote them about this day, so a timeline that
    omitted them would again be describing a table rather than a day.
    """
    out: List[Dict[str, Any]] = []
    base = str(day.get("date") or "")
    # `ord` is the day-card reading order, not a clock. These items all
    # share the day's date and nothing finer, so without it the sort
    # falls through to the id and the operator gets where they slept
    # before where they were --- the day card's own order, scrambled.
    _ord = 0
    for field in ("main_location", "lodging_base",
                  "morning_notes", "afternoon_notes", "evening_notes"):
        _ord += 1
        text = str(day.get(field) or "").strip()
        if not text:
            continue
        out.append({
            "kind": "day_text",
            "id": str(day.get("id") or "") + ":" + field,
            "field": field,
            "label": _DAY_TEXT_LABELS.get(field, field),
            "at": base,
            "ord": _ord,
            "text": text,
        })
    for field, label in (("places_visited_json", "Places"),
                         ("meals_json", "Meals")):
        _ord += 1
        value = day.get(field)
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except Exception:
                value = []
        if not value:
            continue
        parts: List[str] = []
        for entry in value:
            if isinstance(entry, dict):
                parts.append(str(entry.get("name")
                                 or entry.get("label")
                                 or entry.get("text") or "").strip())
            else:
                parts.append(str(entry).strip())
        parts = [p for p in parts if p]
        if not parts:
            continue
        out.append({
            "kind": "day_text",
            "id": str(day.get("id") or "") + ":" + field,
            "field": field,
            "label": label,
            "at": base,
            "ord": _ord,
            "text": ", ".join(parts),
        })
    return out


def trip_day_timeline_items(trip_id: str,
                            trip_day_id: str) -> List[Dict[str, Any]]:
    """Everything on one trip day, in the order it happened.

    Conversations, photographs, notes, sources and the day's own
    operator text, merged and sorted. Items with no time of their own
    sort after the timed ones rather than pretending to be midnight.
    """
    day = trip_day_get(trip_day_id)
    items: List[Dict[str, Any]] = list(
        trip_day_conversation_items(trip_id, trip_day_id))
    con = _connect()
    try:
        items.extend(_day_photo_items(con, trip_id, trip_day_id))
        items.extend(_day_note_items(con, trip_id, trip_day_id))
        items.extend(_day_source_items(con, trip_id, trip_day_id))
    finally:
        con.close()
    if day:
        items.extend(_day_own_text_items(day))
    kind_rank = {k: i for i, k in enumerate(DAY_TIMELINE_KINDS)}
    items.sort(key=lambda i: (
        1 if not str(i.get("at") or "").strip() else 0,
        str(i.get("at") or ""),
        kind_rank.get(str(i.get("kind") or ""), 99),
        int(i.get("ord") or 0),
        str(i.get("id") or ""),
    ))
    return items


def trip_day_item_counts(trip_id: str) -> Dict[str, Dict[str, int]]:
    """Per-day counts for the calendar rail, keyed by day id.

    The rail needs to say what a day holds before the operator clicks
    it. Conversations come from trip_turn_links; the rest is the same
    attachment tally the day cards already use, minus hidden rows,
    because this one is a display count.
    """
    conv = trip_turn_link_counts(trip_id)
    out: Dict[str, Dict[str, int]] = {}
    # EVERY day of the trip gets an entry, and every entry gets all four
    # keys. A sparse map would make each caller invent its own default
    # for a day with nothing on it, and "no key" and "zero" would drift
    # apart the first time one of them forgot. A day with nothing on it
    # is a fact this function knows; it should say so.
    for _d in trip_days_list(trip_id):
        out[str(_d.get("id") or "")] = {
            "photos": 0, "notes": 0, "sources": 0, "conversations": 0}
    out.pop("", None)
    con = _connect()
    try:
        for table, alias, bucket in (
            ("trip_photo_links", "l", "photos"),
            ("trip_location_notes", "l", "notes"),
            ("trip_sources", "l", "sources"),
        ):
            if not _table_has_column(con, table, "trip_day_id"):
                continue
            sql = ("SELECT " + alias + ".trip_day_id AS d, COUNT(*) AS n "
                   "  FROM " + table + " " + alias +
                   " WHERE " + alias + ".trip_id = ? "
                   "   AND " + alias + ".trip_day_id IS NOT NULL "
                   + _timeline_hidden_clause(con, table, alias) +
                   " GROUP BY " + alias + ".trip_day_id")
            for r in con.execute(sql, (trip_id,)):
                did = str(r["d"] or "")
                if not did:
                    continue
                slot = out.setdefault(did, {
                    "photos": 0, "notes": 0, "sources": 0,
                    "conversations": 0})
                slot[bucket] = int(r["n"])
    except sqlite3.Error:
        pass
    finally:
        con.close()
    for did, n in conv.items():
        if did == "unplaced":
            continue
        out.setdefault(str(did), {
            "photos": 0, "notes": 0, "sources": 0,
            "conversations": 0})["conversations"] = int(n)
    return out
