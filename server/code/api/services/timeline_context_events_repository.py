"""WO-TIMELINE-CONTEXT-EVENTS-01 Phase A — repository module.

═══════════════════════════════════════════════════════════════════════
  WHAT THIS IS
═══════════════════════════════════════════════════════════════════════

The read+write accessor for the `timeline_context_events` table. Pure
DB layer: no LLM call, no web fetch, no chat-path import. The renderer
(WO-TIMELINE-RENDER-01) reads from here; the seed loader writes to
here; operator review surfaces (Phase C, deferred) edit through here.

Lori does NOT write to this table. EVER. This module is allow-listed
to be imported by:
  - api.routers.timeline_render (the read endpoint, Phase C of pair WO)
  - scripts.seed_timeline_context_events (the bulk JSON loader)
  - scripts.validate_timeline_context_events (the validator — read-only)

It is FORBIDDEN to be imported by:
  - api.routers.extract / api.prompt_composer / api.memory_echo
  - api.routers.llm_api / api.routers.chat_ws
  - api.routers.family_truth
  - api.services.story_preservation / api.services.story_trigger
  - api.services.lori_*
  - api.services.utterance_frame
  - any code path the live narrator session can reach

Enforcement: tests/test_timeline_context_events_isolation.py walks
the AST of this module + transitive imports and fails the build if
any forbidden prefix is reached.

═══════════════════════════════════════════════════════════════════════
  PHASE A SCOPE (THIS FILE)
═══════════════════════════════════════════════════════════════════════

  - schema-validated CRUD on timeline_context_events
  - tag-vocabulary enforcement (deferred to validator script for now;
    repository accepts any tag passed in — Phase A intentionally does
    not import the validator to keep this module purely DB-shaped)
  - narrator-filter query: by lifetime year-range + tag overlap
  - soft-delete (UPDATE deleted_at instead of DELETE)
  - operator_research_note → published-source promotion path

NOT IN PHASE A:
  - operator UI (Phase C)
  - bulk import from external corpora
  - language localization
  - per-narrator hide/show preferences
  - composer-hook integration (future WO, gated behind BINDING-01 +
    parent-session readiness)

═══════════════════════════════════════════════════════════════════════
  STATUS
═══════════════════════════════════════════════════════════════════════

  Skeleton banked 2026-05-05 night-shift. NOT yet wired into main.py.
  Operator review + Phase A landing decision pending Chris's review.
  Migration 0005_timeline_context_events.sql is the partner artifact.

  Until the migration runs and main.py routes anything to this module,
  the runtime treats this file as dead code. It exists in the tree so
  Phase A can land in one focused commit when Chris is ready.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger("lorevox.timeline_context_events")


# ── Public dataclass ──────────────────────────────────────────────────────


@dataclasses.dataclass(frozen=True)
class ContextEvent:
    """In-memory shape of a timeline_context_events row. Frozen so a row
    pulled out of the DB can't be mutated in place by a caller."""

    id: str
    title: str
    summary: str
    year_start: Optional[int]
    year_end: Optional[int]
    scope: str
    region_tags: Tuple[str, ...]
    heritage_tags: Tuple[str, ...]
    source_kind: str
    source_citation: str
    narrator_visible: bool
    created_by: str
    created_at: str
    reviewed_by: Optional[str]
    reviewed_at: Optional[str]
    updated_at: str
    deleted_at: Optional[str]
    notes: Optional[str]

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ContextEvent":
        """Build from a sqlite3.Row. Decodes JSON tag arrays.

        Raises ValueError if region_tags / heritage_tags JSON is malformed.
        """
        try:
            region_tags = tuple(json.loads(row["region_tags"] or "[]"))
            heritage_tags = tuple(json.loads(row["heritage_tags"] or "[]"))
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError(
                f"timeline_context_events.id={row['id']!r}: "
                f"malformed tag JSON: {exc}"
            )

        return cls(
            id=row["id"],
            title=row["title"],
            summary=row["summary"],
            year_start=row["year_start"],
            year_end=row["year_end"],
            scope=row["scope"],
            region_tags=region_tags,
            heritage_tags=heritage_tags,
            source_kind=row["source_kind"],
            source_citation=row["source_citation"],
            narrator_visible=bool(row["narrator_visible"]),
            created_by=row["created_by"],
            created_at=row["created_at"],
            reviewed_by=row["reviewed_by"],
            reviewed_at=row["reviewed_at"],
            updated_at=row["updated_at"],
            deleted_at=row["deleted_at"],
            notes=row["notes"],
        )

    def to_dict(self) -> Dict[str, Any]:
        """JSON-serializable dict for renderer / API responses."""
        d = dataclasses.asdict(self)
        d["region_tags"] = list(self.region_tags)
        d["heritage_tags"] = list(self.heritage_tags)
        return d


# ── Constants (mirrored from migration; kept here for input validation) ──


_VALID_SCOPES: frozenset = frozenset({
    "global", "national", "regional", "local", "cultural",
})

_VALID_SOURCE_KINDS: frozenset = frozenset({
    "local_oral_history",
    "archived_newspaper",
    "historical_society",
    "academic",
    "reference_work",
    "web_resource",
    "family_archive",
    "operator_research_note",
})


# ── Internal helpers ──────────────────────────────────────────────────────


def _connect() -> sqlite3.Connection:
    """Open a sqlite3 connection to the live DB.

    Lazy-imports `..db` to keep this module's import graph minimal —
    the LAW 3 isolation test allow-lists `api.db` and is happy with
    a lazy import here.
    """
    from .. import db as _db
    conn = _db._connect()  # noqa: SLF001 — module-private accessor reuse is intentional
    conn.row_factory = sqlite3.Row
    return conn


def _validate_event_data(data: Dict[str, Any]) -> List[str]:
    """Return a list of error strings for invalid event_data, empty list if ok.

    Catches schema-shaped errors at the repository layer. The validator
    script (Phase B) catches richer errors (tag vocabulary, citation
    discipline) before data reaches this module.
    """
    errors: List[str] = []

    required = (
        "id", "title", "summary", "scope",
        "region_tags", "heritage_tags",
        "source_kind", "source_citation",
    )
    for field in required:
        v = data.get(field)
        if v is None or (isinstance(v, str) and not v.strip()):
            errors.append(f"missing or empty required field: {field}")

    scope = data.get("scope")
    if scope and scope not in _VALID_SCOPES:
        errors.append(f"invalid scope: {scope!r} (must be one of {sorted(_VALID_SCOPES)})")

    sk = data.get("source_kind")
    if sk and sk not in _VALID_SOURCE_KINDS:
        errors.append(
            f"invalid source_kind: {sk!r} (must be one of {sorted(_VALID_SOURCE_KINDS)})"
        )

    rt = data.get("region_tags")
    if rt is not None and not isinstance(rt, (list, tuple)):
        errors.append("region_tags must be a list of strings")
    ht = data.get("heritage_tags")
    if ht is not None and not isinstance(ht, (list, tuple)):
        errors.append("heritage_tags must be a list of strings")

    ys = data.get("year_start")
    ye = data.get("year_end")
    if ys is not None and not isinstance(ys, int):
        errors.append(f"year_start must be int or None, got {type(ys).__name__}")
    if ye is not None and not isinstance(ye, int):
        errors.append(f"year_end must be int or None, got {type(ye).__name__}")
    if isinstance(ys, int) and isinstance(ye, int) and ys > ye:
        errors.append(f"year_start ({ys}) > year_end ({ye})")

    citation = (data.get("source_citation") or "").strip().lower()
    _LOW_RIGOR_PATTERNS = (
        "general knowledge", "common knowledge", "i remember",
        "wikipedia",  # bare wikipedia without article + access date
    )
    for pat in _LOW_RIGOR_PATTERNS:
        if pat in citation:
            # `wikipedia` substring catches the bare case but allows
            # "wikipedia article: <title>, accessed <date>" through
            # the validator script's stricter check.
            if pat == "wikipedia" and ":" in citation and "accessed" in citation:
                continue
            errors.append(
                f"source_citation looks low-rigor (matches {pat!r}); "
                f"use a real citation or set source_kind='local_oral_history' "
                f"with a named person + date"
            )
            break

    return errors


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Public API ────────────────────────────────────────────────────────────


def query_events_for_narrator(
    *,
    lifetime_year_start: int,
    lifetime_year_end: int,
    region_tags: Sequence[str],
    heritage_tags: Sequence[str],
    include_operator_only: bool = False,
) -> List[ContextEvent]:
    """Return context events whose temporal range overlaps the narrator's
    lifetime AND whose tags overlap the narrator's tags (or whose scope
    is global/national).

    Args:
      lifetime_year_start: narrator's birth year (or earliest known year).
      lifetime_year_end: render-target year (typically current year or
        the renderer's "today" year for memoir export purposes).
      region_tags: narrator's region tags from intake (e.g. ["nd",
        "great_plains"]). Operator-recorded; never inferred at runtime.
      heritage_tags: narrator's heritage tags from intake (e.g.
        ["germans_from_russia"]). Operator-recorded; never inferred.
      include_operator_only: when True, return narrator_visible=0 rows
        for operator review surfaces. Default False — narrator-facing.

    Returns:
      List[ContextEvent], soft-deleted rows excluded.

    Filter logic:
      Event scope == 'global' OR 'national'  → always included (subject to year-range).
      Event scope == 'regional' OR 'local'   → only included when region_tags overlap.
      Event scope == 'cultural'              → only included when heritage_tags overlap.

    Year range is inclusive on both ends. An event with
    year_start=1955, year_end=1959 matches a narrator lifetime
    1940-2026 because [1955,1959] overlaps [1940,2026].
    """
    region_set = set(region_tags or ())
    heritage_set = set(heritage_tags or ())

    # SQL prefilter: year range + visibility + soft-delete only.
    # Tag intersection happens in Python because SQLite has no native
    # JSON intersection operator (json_each works but isn't worth the
    # ceremony for a 50-200 row table).
    sql = """
        SELECT * FROM timeline_context_events
         WHERE deleted_at IS NULL
           AND year_start <= ?
           AND year_end   >= ?
    """
    if not include_operator_only:
        sql += " AND narrator_visible = 1"

    conn = _connect()
    try:
        cur = conn.execute(sql, (lifetime_year_end, lifetime_year_start))
        rows = cur.fetchall()
    finally:
        conn.close()

    out: List[ContextEvent] = []
    for row in rows:
        try:
            event = ContextEvent.from_row(row)
        except ValueError as exc:
            logger.warning("[tce] skipping malformed row: %s", exc)
            continue

        # Tag overlap rule by scope
        if event.scope in ("global", "national"):
            out.append(event)
            continue
        if event.scope in ("regional", "local"):
            if region_set & set(event.region_tags):
                out.append(event)
            continue
        if event.scope == "cultural":
            if heritage_set & set(event.heritage_tags):
                out.append(event)
            continue
        # Unknown scope (CHECK constraint should make this impossible,
        # but be defensive against schema drift)
        logger.warning("[tce] event %r has unknown scope %r", event.id, event.scope)

    return out


def get_event(event_id: str) -> Optional[ContextEvent]:
    """Return the row by id (including soft-deleted), or None."""
    conn = _connect()
    try:
        cur = conn.execute(
            "SELECT * FROM timeline_context_events WHERE id = ?",
            (event_id,),
        )
        row = cur.fetchone()
    finally:
        conn.close()

    if row is None:
        return None
    try:
        return ContextEvent.from_row(row)
    except ValueError as exc:
        logger.warning("[tce] get_event: malformed row %r: %s", event_id, exc)
        return None


def add_event(
    event_data: Dict[str, Any],
    *,
    created_by_user_id: str,
) -> ContextEvent:
    """Insert a new context event. Returns the created row.

    Raises ValueError on schema violation. Does NOT enforce tag
    vocabulary — that's the validator's job (Phase B). The repository
    layer enforces type/shape/CHECK-constraint-equivalent rules only.
    """
    errors = _validate_event_data(event_data)
    if errors:
        raise ValueError(
            "add_event validation failed: " + "; ".join(errors)
        )
    if not (created_by_user_id and created_by_user_id.strip()):
        raise ValueError("add_event: created_by_user_id is required")

    now = _now_iso()
    region_tags_json = json.dumps(list(event_data.get("region_tags") or []))
    heritage_tags_json = json.dumps(list(event_data.get("heritage_tags") or []))

    # operator_research_note rows ship with narrator_visible=0 by default
    default_visible = 0 if event_data["source_kind"] == "operator_research_note" else 1
    narrator_visible = int(bool(
        event_data.get("narrator_visible", default_visible)
    ))

    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO timeline_context_events (
                id, title, summary,
                year_start, year_end,
                scope, region_tags, heritage_tags,
                source_kind, source_citation,
                narrator_visible,
                created_by, created_at, updated_at,
                notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_data["id"],
                event_data["title"],
                event_data["summary"],
                event_data.get("year_start"),
                event_data.get("year_end"),
                event_data["scope"],
                region_tags_json,
                heritage_tags_json,
                event_data["source_kind"],
                event_data["source_citation"],
                narrator_visible,
                created_by_user_id,
                now,
                now,
                event_data.get("notes"),
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise ValueError(f"add_event integrity error: {exc}") from exc
    finally:
        conn.close()

    out = get_event(event_data["id"])
    if out is None:
        raise RuntimeError(
            f"add_event: row not found after insert (id={event_data['id']!r})"
        )
    return out


def update_event(
    event_id: str,
    patch: Dict[str, Any],
    *,
    edited_by_user_id: str,
) -> ContextEvent:
    """Apply patch to an existing row. Returns the updated row.

    Patchable fields: title, summary, year_start, year_end, scope,
    region_tags, heritage_tags, source_kind, source_citation,
    narrator_visible, notes.

    Audit columns (created_by, created_at, deleted_at) are NOT
    patchable here. Use soft_delete_event for the deleted_at path
    and promote_research_note for the reviewed_by/reviewed_at path.
    """
    if not (edited_by_user_id and edited_by_user_id.strip()):
        raise ValueError("update_event: edited_by_user_id is required")

    existing = get_event(event_id)
    if existing is None:
        raise ValueError(f"update_event: id not found: {event_id!r}")

    PATCHABLE = {
        "title", "summary", "year_start", "year_end", "scope",
        "region_tags", "heritage_tags", "source_kind", "source_citation",
        "narrator_visible", "notes",
    }
    bad = set(patch.keys()) - PATCHABLE
    if bad:
        raise ValueError(f"update_event: non-patchable field(s): {sorted(bad)}")

    # Re-validate the merged payload as if it were a new row, so
    # invariants are preserved.
    merged = existing.to_dict()
    merged.update(patch)
    errors = _validate_event_data(merged)
    if errors:
        raise ValueError(
            "update_event validation failed: " + "; ".join(errors)
        )

    set_clauses: List[str] = []
    params: List[Any] = []
    for k, v in patch.items():
        if k in ("region_tags", "heritage_tags"):
            v = json.dumps(list(v or []))
        if k == "narrator_visible":
            v = int(bool(v))
        set_clauses.append(f"{k} = ?")
        params.append(v)
    set_clauses.append("updated_at = ?")
    params.append(_now_iso())
    params.append(event_id)

    conn = _connect()
    try:
        conn.execute(
            f"UPDATE timeline_context_events SET {', '.join(set_clauses)} WHERE id = ?",
            params,
        )
        conn.commit()
    finally:
        conn.close()

    out = get_event(event_id)
    if out is None:
        raise RuntimeError(
            f"update_event: row not found after UPDATE (id={event_id!r})"
        )
    return out


def soft_delete_event(
    event_id: str,
    *,
    deleted_by_user_id: str,
) -> None:
    """Mark a row as soft-deleted by setting deleted_at + updated_at.

    Soft-delete preserves the audit trail; the row stays in the table
    but is excluded from all narrator-facing queries.
    """
    if not (deleted_by_user_id and deleted_by_user_id.strip()):
        raise ValueError("soft_delete_event: deleted_by_user_id is required")

    now = _now_iso()
    conn = _connect()
    try:
        cur = conn.execute(
            """
            UPDATE timeline_context_events
               SET deleted_at = ?, updated_at = ?
             WHERE id = ?
               AND deleted_at IS NULL
            """,
            (now, now, event_id),
        )
        if cur.rowcount == 0:
            # Either id doesn't exist or already soft-deleted. Surface
            # as a non-fatal warning; caller can decide.
            logger.warning(
                "[tce] soft_delete_event: %r not found or already deleted",
                event_id,
            )
        conn.commit()
    finally:
        conn.close()


def promote_research_note(
    event_id: str,
    *,
    new_source_kind: str,
    new_citation: str,
    reviewed_by_user_id: str,
) -> ContextEvent:
    """Promote an operator_research_note row to a published source kind.

    Sets:
      source_kind = new_source_kind
      source_citation = new_citation
      narrator_visible = 1
      reviewed_by = reviewed_by_user_id
      reviewed_at = now
      updated_at = now
    """
    if not (reviewed_by_user_id and reviewed_by_user_id.strip()):
        raise ValueError("promote_research_note: reviewed_by_user_id is required")
    if new_source_kind == "operator_research_note":
        raise ValueError(
            "promote_research_note: cannot promote to operator_research_note "
            "(that's where it started)"
        )
    if new_source_kind not in _VALID_SOURCE_KINDS:
        raise ValueError(
            f"promote_research_note: invalid new_source_kind {new_source_kind!r}"
        )
    if not (new_citation and new_citation.strip()):
        raise ValueError("promote_research_note: new_citation is required")

    existing = get_event(event_id)
    if existing is None:
        raise ValueError(f"promote_research_note: id not found: {event_id!r}")
    if existing.source_kind != "operator_research_note":
        raise ValueError(
            f"promote_research_note: row {event_id!r} is not an operator_research_note "
            f"(current source_kind={existing.source_kind!r})"
        )

    # Re-validate the merged payload, then write
    merged = existing.to_dict()
    merged["source_kind"] = new_source_kind
    merged["source_citation"] = new_citation
    errors = _validate_event_data(merged)
    if errors:
        raise ValueError(
            "promote_research_note validation failed: " + "; ".join(errors)
        )

    now = _now_iso()
    conn = _connect()
    try:
        conn.execute(
            """
            UPDATE timeline_context_events
               SET source_kind = ?,
                   source_citation = ?,
                   narrator_visible = 1,
                   reviewed_by = ?,
                   reviewed_at = ?,
                   updated_at = ?
             WHERE id = ?
            """,
            (new_source_kind, new_citation, reviewed_by_user_id, now, now, event_id),
        )
        conn.commit()
    finally:
        conn.close()

    out = get_event(event_id)
    if out is None:
        raise RuntimeError(
            f"promote_research_note: row not found after UPDATE (id={event_id!r})"
        )
    return out


__all__ = [
    "ContextEvent",
    "query_events_for_narrator",
    "get_event",
    "add_event",
    "update_event",
    "soft_delete_event",
    "promote_research_note",
]
