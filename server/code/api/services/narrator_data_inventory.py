"""The ONE narrator-ownership declaration — WO-LOREVOX-PORTABLE-NARRATOR-01 Phase 1.

What belongs to a narrator, how that is PROVEN, and what follows from it:
whether the lane travels in a portable package, whether it must go when
the narrator is erased, which columns hold paths that must be rewritten
on Restore, and which columns may name a different person.

This module is a DECLARATION, not a framework. It is consumed by:

  * Portable Narrator export / dry-run / restore (Phase 2+), which read
    `select_sql()` and never reconstruct ownership from anywhere else;
  * the parity test (`tests/test_narrator_data_inventory_parity.py`),
    which holds erasure (`db._EXTENDED_PERSON_SCOPED_TABLES`, the inline
    parent-owned children in `db._extended_person_scoped_delete`, the FK
    cascade in the live schema, and `narrator_erasure` filesystem plans)
    to the same truth in BOTH directions.

Erasure itself is NOT rewritten to consume this module — WO §17 Phase 1:
"do not rewrite hard deletion wholesale". Agreement is enforced by test.

OWNERSHIP IS A PROPERTY OF ROWS (WO §29.1). Every lane carries a
SELECTOR — a predicate over the row, parameterised by the narrator id —
never a bare table name. A table can hold rows of different disposition
(`media_archive_items` with and without a person owner), and the
selector is what says which rows are the narrator's.

EVIDENCE. Every claim below cites Phase 0
(`docs/wo/WO-LOREVOX-PORTABLE-NARRATOR-01_PHASE0-OWNERSHIP-MATRIX.md`,
rules R1–R12) or a migration / `db.py` line. `on_delete` facts come from
the live schema via `PRAGMA foreign_key_list`, not from prose.

LAW 3-style isolation: stdlib only. No `api.db`, no routers, no IO.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

# ── Ownership classes (WO §5) ────────────────────────────────────────────
CLASS_AUTHORITATIVE = "A"   # original evidence / operator decisions
CLASS_DERIVED = "B"         # derived but portable
CLASS_HISTORICAL = "C"      # retired product data still owned by the narrator
CLASS_CACHE = "D"           # re-generable, excluded by declaration
CLASS_INSTALLATION = "E"    # must not travel
CLASS_SHARED_ROW = "S"      # rows in this table may be shared/unassigned (§6)

# ── How a lane is owned ──────────────────────────────────────────────────


@dataclass(frozen=True)
class Direct:
    """The row carries the narrator id in `column`."""
    column: str


@dataclass(frozen=True)
class Parent:
    """The row belongs through `fk_column -> parent_table.<pk>`; the parent
    decides. Chains compose: a parent may itself be Parent-owned."""
    fk_column: str
    parent_table: str
    parent_key: str = "id"


@dataclass(frozen=True)
class Installation:
    """Never a narrator's. Never travels."""
    reason: str


@dataclass(frozen=True)
class DbLane:
    table: str
    owner: object                       # Direct | Parent | Installation
    klass: str
    portable: str                        # "yes" | "no" | "conditional"
    erasable: bool                       # policy: must go with the narrator
    path_columns: Tuple[str, ...] = ()   # DATA_DIR-relative on Restore (§8.5)
    external_person_columns: Tuple[str, ...] = ()   # may name ANOTHER person (§13)
    note: str = ""


@dataclass(frozen=True)
class FsLane:
    name: str
    parts: Tuple[str, ...]               # under DATA_DIR
    keyed_by: str                        # "person" | "row" | "shared" | "installation"
    klass: str
    portable: str                        # "yes" | "no" | "conditional"
    erasable: bool
    resolver_sql: Optional[str] = None   # for keyed_by == "row": yields the id segment
    note: str = ""


# ══════════════════════════════════════════════════════════════════════
# Database lanes
# ══════════════════════════════════════════════════════════════════════

_D = Direct
_P = Parent
_I = Installation

DB_LANES: Tuple[DbLane, ...] = (
    # ── identity ──────────────────────────────────────────────────────
    DbLane("people", _D("id"), CLASS_AUTHORITATIVE, "yes", True,
           note="the identity row; testing_only is set here at creation and has no "
                "later write partner (db.py:2852) — Restore writes it in this insert"),
    DbLane("profiles", _D("person_id"), CLASS_DERIVED, "yes", True),
    DbLane("consent_attestations", _D("narrator_id"), CLASS_AUTHORITATIVE, "yes", True,
           note="historical evidence; does not confer authorization on the target (§15)"),
    DbLane("identity_change_log", _D("person_id"), CLASS_AUTHORITATIVE, "yes", True),
    DbLane("profile_seed_onboarding", _D("person_id"), CLASS_DERIVED, "yes", True),

    # ── conversation ──────────────────────────────────────────────────
    DbLane("sessions", _D("person_id"), CLASS_AUTHORITATIVE, "yes", True,
           note="person_id added by ALTER in 0044 with NO FK (R1); deleted explicitly "
                "by db._EXTENDED_PERSON_SCOPED_TABLES. Rows with NULL person_id are "
                "residue, reported by session_ownership_residue(), never swept"),
    DbLane("turns", _P("conv_id", "sessions", "conv_id"), CLASS_AUTHORITATIVE, "yes", True,
           note="R1: the narrator's words. turns.conv_id -> sessions ON DELETE CASCADE "
                "(db.py:595); reachable only through sessions.person_id"),
    DbLane("memory_archive_sessions", _D("person_id"), CLASS_AUTHORITATIVE, "yes", True,
           path_columns=("archive_dir",),
           note="archive_dir is already DATA_DIR-relative (Phase 0 path survey)"),
    DbLane("memory_archive_turns", _D("person_id"), CLASS_AUTHORITATIVE, "yes", True),
    DbLane("interview_sessions", _D("person_id"), CLASS_DERIVED, "yes", True),
    DbLane("interview_threads", _P("session_id", "interview_sessions"), CLASS_DERIVED, "yes", True,
           note="0009:56 FK with no ON DELETE; GAP at HEAD repaired in Phase 1 "
                "(deleted by parent interview_sessions.person_id)"),
    DbLane("interview_answers", _D("person_id"), CLASS_DERIVED, "yes", True),
    DbLane("interview_projections", _D("person_id"), CLASS_DERIVED, "yes", True),
    DbLane("segment_flags", _P("session_id", "interview_sessions"), CLASS_DERIVED, "yes", True),
    DbLane("affect_events", _P("session_id", "interview_sessions"), CLASS_DERIVED, "yes", True),
    DbLane("section_summaries", _D("person_id"), CLASS_DERIVED, "yes", True),
    DbLane("safety_events", _D("person_id"), CLASS_AUTHORITATIVE, "yes", True,
           note="§14: preserved as history; Restore never re-activates anything from it"),

    # ── structured memory ─────────────────────────────────────────────
    DbLane("bio_builder_questionnaires", _D("person_id"), CLASS_DERIVED, "yes", True),
    DbLane("bio_facts", _D("narrator_id"), CLASS_DERIVED, "yes", True),
    DbLane("facts", _D("person_id"), CLASS_DERIVED, "yes", True),
    DbLane("family_truth_notes", _D("person_id"), CLASS_DERIVED, "yes", True),
    DbLane("family_truth_rows", _D("person_id"), CLASS_DERIVED, "yes", True),
    DbLane("family_truth_promoted", _D("person_id"), CLASS_DERIVED, "yes", True),
    DbLane("graph_persons", _D("narrator_id"), CLASS_DERIVED, "yes", True),
    DbLane("graph_relationships", _D("narrator_id"), CLASS_DERIVED, "yes", True),
    DbLane("life_phases", _D("person_id"), CLASS_DERIVED, "yes", True),
    DbLane("timeline_events", _D("person_id"), CLASS_DERIVED, "yes", True),
    DbLane("follow_up_bank", _D("person_id"), CLASS_DERIVED, "yes", True),

    # ── stories / extraction ──────────────────────────────────────────
    DbLane("story_candidates", _D("narrator_id"), CLASS_DERIVED, "yes", True,
           note="review, placement and promotion state travel as-is (§14, §18)"),
    DbLane("turn_extraction_ledger", _D("narrator_id"), CLASS_DERIVED, "yes", True),
    DbLane("turn_extraction_results", _D("narrator_id"), CLASS_DERIVED, "yes", True),

    # ── photos ────────────────────────────────────────────────────────
    DbLane("photos", _D("narrator_id"), CLASS_AUTHORITATIVE, "yes", True,
           path_columns=("image_path", "thumbnail_path"),
           note="R3: both paths are ABSOLUTE on every existing row; rewritten on Restore"),
    DbLane("photo_sessions", _D("narrator_id"), CLASS_DERIVED, "yes", True),
    DbLane("photo_people", _D("person_id"), CLASS_DERIVED, "yes", True,
           note="explicit in db.py; also a photo child — both selectors agree"),
    DbLane("photo_events", _P("photo_id", "photos"), CLASS_DERIVED, "yes", True),
    DbLane("photo_session_shows", _P("photo_id", "photos"), CLASS_DERIVED, "yes", True),
    DbLane("photo_memories", _P("photo_id", "photos"), CLASS_DERIVED, "yes", True),

    # ── import provenance (R12) ───────────────────────────────────────
    DbLane("import_batch", _D("person_id"), CLASS_DERIVED, "yes", True),
    DbLane("import_candidate", _D("person_id"), CLASS_DERIVED, "yes", True,
           note="direct FK to people (corrected 2026-09-10); staged original travels "
                "conditionally — see FS lane import_staging"),

    # ── media (documents) ─────────────────────────────────────────────
    DbLane("media", _D("person_id"), CLASS_AUTHORITATIVE, "yes", True),
    DbLane("media_attachments", _D("person_id"), CLASS_AUTHORITATIVE, "yes", True),
    DbLane("media_archive_items", _D("person_id"), CLASS_SHARED_ROW, "yes", True,
           path_columns=("storage_path",),
           note="R11: rows WITH person_id are the narrator's; rows without are "
                "shared/family or unassigned (§6) — reported, never packaged"),
    DbLane("media_archive_people", _P("archive_item_id", "media_archive_items"),
           CLASS_DERIVED, "yes", True,
           external_person_columns=("person_id",),
           note="R11/§13: follows the OWNED ITEM; person_id may name another person — "
                "recorded as an external dependency, never pulled. 0003:156 FK with no "
                "ON DELETE; deleted only by its own person_id at HEAD — GAP repaired in "
                "Phase 1 (also deleted by parent item)"),
    DbLane("media_archive_family_lines", _P("archive_item_id", "media_archive_items"),
           CLASS_DERIVED, "yes", True,
           note="R11: db.py:5696-5705 already deletes by parent"),
    DbLane("media_archive_links", _P("archive_item_id", "media_archive_items"),
           CLASS_DERIVED, "yes", True,
           note="R11: db.py:5696-5705 already deletes by parent"),

    # ── travel (R4: installed, empty here; contract from schema) ──────
    DbLane("trips", _D("person_id"), CLASS_AUTHORITATIVE, "yes", True,
           note="FK to people since 0034; trip_* children cascade under foreign_keys=ON"),
    DbLane("trip_regions", _P("trip_id", "trips"), CLASS_DERIVED, "yes", True),
    DbLane("trip_stops", _P("trip_id", "trips"), CLASS_DERIVED, "yes", True),
    DbLane("trip_days", _P("trip_id", "trips"), CLASS_DERIVED, "yes", True),
    DbLane("trip_themes", _P("trip_id", "trips"), CLASS_DERIVED, "yes", True),
    DbLane("trip_location_notes", _P("trip_id", "trips"), CLASS_AUTHORITATIVE, "yes", True),
    DbLane("trip_bio_suggestions", _D("person_id"), CLASS_DERIVED, "yes", True),
    DbLane("trip_story_links", _P("trip_id", "trips"), CLASS_DERIVED, "yes", True),
    DbLane("trip_sources", _P("trip_id", "trips"), CLASS_AUTHORITATIVE, "yes", True,
           path_columns=("storage_path",),
           note="travel documents; files under trip_sources/<source-id> (FS lane, R7)"),
    DbLane("trip_public_context", _P("trip_id", "trips"), CLASS_DERIVED, "yes", True),
    DbLane("trip_photo_links", _P("trip_id", "trips"), CLASS_DERIVED, "yes", True),
    DbLane("trip_photo_context", _P("trip_id", "trips"), CLASS_DERIVED, "yes", True),
    DbLane("trip_photo_day_placements", _P("trip_day_id", "trip_days"), CLASS_DERIVED, "yes", True),
    DbLane("trip_photo_day_placement_skips", _P("trip_id", "trips"), CLASS_HISTORICAL, "yes", True,
           note="0043: historical skip ledger, NO FK at all; GAP at HEAD repaired in "
                "Phase 1 (deleted by parent trips.person_id). legacy_trip_day_id is a "
                "§14 reference and is carried as-is"),
    DbLane("trip_turn_links", _P("trip_id", "trips"), CLASS_DERIVED, "yes", True),

    # ── installation-owned (§5-E): never travel, never erased with a narrator ──
    DbLane("schema_migrations", _I("migration ledger"), CLASS_INSTALLATION, "no", False),
    DbLane("lori_guard_authority_override", _I("Guard Lab overrides, 0053"), CLASS_INSTALLATION, "no", False),
    DbLane("lori_guard_control_state", _I("Guard Lab control state, 0053"), CLASS_INSTALLATION, "no", False),
    DbLane("bio_fields", _I("global questionnaire schema"), CLASS_INSTALLATION, "no", False),
    DbLane("timeline_context_events", _I("global curated timeline library"), CLASS_INSTALLATION, "no", False),
    DbLane("interview_plans", _I("interview plan template"), CLASS_INSTALLATION, "no", False),
    DbLane("interview_sections", _I("interview plan template"), CLASS_INSTALLATION, "no", False),
    DbLane("interview_questions", _I("interview plan template"), CLASS_INSTALLATION, "no", False),
    DbLane("rag_docs", _I("retrieval store, unused"), CLASS_INSTALLATION, "no", False),
    DbLane("rag_chunks", _I("retrieval store, unused"), CLASS_INSTALLATION, "no", False),
    DbLane("narrator_delete_audit", _I("deletion audit — must survive the delete it records"),
           CLASS_INSTALLATION, "no", False),
    DbLane("narrator_erasure_jobs", _I("erasure job records, 0049/0050"), CLASS_INSTALLATION, "no", False),
)

# ══════════════════════════════════════════════════════════════════════
# Filesystem lanes (under DATA_DIR)
# ══════════════════════════════════════════════════════════════════════

FS_LANES: Tuple[FsLane, ...] = (
    FsLane("memory_archive", ("memory", "archive", "people"), "person", CLASS_AUTHORITATIVE, "yes", True,
           note="the only lane the current Archive Export covers (memory_archive.py:634). "
                "CARRIES SAVED NARRATOR AUDIO: <pid>/sessions/<conv>/audio/<turn>.webm "
                "(archive_paths.py:107, memory_archive_turns.audio_ref). Saved narrator "
                "VIDEO, when the product persists it, goes under the same session dir "
                "(WO §9) so it inherits this lane rather than needing a new one"),
    FsLane("stories_captured", ("stories-captured",), "person", CLASS_DERIVED, "yes", True),
    FsLane("photo_archive", ("memory", "archive", "photos"), "person", CLASS_AUTHORITATIVE, "yes", True,
           note="photos.image_path points here with an ABSOLUTE prefix (R3)"),
    FsLane("personal_media_archive", ("media", "archive", "people"), "person", CLASS_AUTHORITATIVE, "yes", True),
    FsLane("media_uploads", ("media",), "person", CLASS_AUTHORITATIVE, "yes", True),
    FsLane("kawa_segments", ("kawa", "people"), "person", CLASS_HISTORICAL, "yes", True,
           note="§5-C: Kawa is not a feature; its narrator data is preserved so portability "
                "cannot become deletion"),
    FsLane("trip_sources", ("trip_sources",), "row", CLASS_AUTHORITATIVE, "yes", True,
           resolver_sql="SELECT s.id FROM trip_sources s JOIN trips t ON t.id = s.trip_id "
                        "WHERE t.person_id = :pid",
           note="R7: travel documents keyed by source id; mirrors narrator_erasure.py:357-361"),
    FsLane("import_staging", ("import_staging",), "row", CLASS_AUTHORITATIVE, "conditional", True,
           resolver_sql="SELECT id FROM import_batch WHERE person_id = :pid",
           note="R12: <batch>/<candidate>/original.* travels when it is the verified byte "
                "source for an UNRESOLVED candidate (import_repository.py:231-235); "
                "redundant once the candidate has a permanent photos row"),
    FsLane("import_staging_incoming", ("import_staging", ".incoming"), "row", CLASS_CACHE, "no", True,
           resolver_sql="SELECT id FROM import_batch WHERE person_id = :pid",
           note="R12: acquisition scratch; erased with the narrator, never packaged"),
    FsLane("agent_transcripts", ("memory", "agents"), "row", CLASS_HISTORICAL, "yes", True,
           resolver_sql="SELECT conv_id FROM sessions WHERE person_id = :pid",
           note="legacy REST transcript exports, plain narrator speech on disk under "
                "memory/agents/<sub>/<slug>. The file name is produced ONLY by "
                "chat_memory_paths.export_basenames(conv_id) — never rebuilt by hand "
                "(narrator_erasure.py:376-395)"),
    FsLane("translation_cache", ("translations-cache",), "shared", CLASS_CACHE, "no", False,
           note="narrator_erasure.SHARED_PURGE; not per-narrator"),
    FsLane("backups", ("backups",), "installation", CLASS_INSTALLATION, "no", False),
    FsLane("exports", ("exports",), "installation", CLASS_INSTALLATION, "no", False),
)


# ══════════════════════════════════════════════════════════════════════
# Queries over the declaration
# ══════════════════════════════════════════════════════════════════════

_BY_TABLE: Dict[str, DbLane] = {l.table: l for l in DB_LANES}


def lane(table: str) -> DbLane:
    return _BY_TABLE[table]


def db_tables() -> List[str]:
    return [l.table for l in DB_LANES]


def narrator_owned_tables() -> List[str]:
    return [l.table for l in DB_LANES if not isinstance(l.owner, Installation)]


def installation_tables() -> List[str]:
    return [l.table for l in DB_LANES if isinstance(l.owner, Installation)]


def erasable_tables() -> List[str]:
    return [l.table for l in DB_LANES if l.erasable]


def parent_owned_tables() -> List[str]:
    return [l.table for l in DB_LANES if isinstance(l.owner, Parent)]


def owner_predicate(table: str, alias: Optional[str] = None) -> str:
    """SQL predicate selecting the rows of `table` that belong to `:pid`.

    Direct:  <alias>.<column> = :pid
    Parent:  <alias>.<fk> IN (SELECT <pk> FROM <parent> WHERE <parent predicate>)
    Chains compose by recursion, and every level binds the SAME named
    parameter, so a caller passes {"pid": person_id} once.
    """
    l = lane(table)
    a = alias or table
    if isinstance(l.owner, Direct):
        return f'"{a}"."{l.owner.column}" = :pid'
    if isinstance(l.owner, Parent):
        p = l.owner
        inner = owner_predicate(p.parent_table, p.parent_table)
        return (f'"{a}"."{p.fk_column}" IN (SELECT "{p.parent_table}"."{p.parent_key}" '
                f'FROM "{p.parent_table}" WHERE {inner})')
    raise ValueError(f"{table} is installation-owned; it has no narrator selector")


def select_sql(table: str) -> str:
    """SELECT every column of the narrator's rows in `table`; bind {"pid": id}."""
    return f'SELECT "{table}".* FROM "{table}" WHERE {owner_predicate(table)}'


def delete_sql(table: str) -> str:
    """DELETE the narrator's rows in `table`; bind {"pid": id}. Provided so
    a repair or a test can use the SAME selector portability uses — one
    truth, two verbs."""
    l = lane(table)
    if isinstance(l.owner, Direct):
        return f'DELETE FROM "{table}" WHERE "{l.owner.column}" = :pid'
    if isinstance(l.owner, Parent):
        p = l.owner
        inner = owner_predicate(p.parent_table, p.parent_table)
        return (f'DELETE FROM "{table}" WHERE "{p.fk_column}" IN '
                f'(SELECT "{p.parent_table}"."{p.parent_key}" FROM "{p.parent_table}" WHERE {inner})')
    raise ValueError(f"{table} is installation-owned; it is never deleted with a narrator")


def dependency_columns() -> Dict[str, Tuple[str, ...]]:
    """table -> columns that may reference a DIFFERENT person (§13)."""
    return {l.table: l.external_person_columns for l in DB_LANES if l.external_person_columns}


def path_columns() -> Dict[str, Tuple[str, ...]]:
    """table -> columns that hold DATA_DIR paths to rewrite on Restore (§8.5)."""
    return {l.table: l.path_columns for l in DB_LANES if l.path_columns}


def fs_lane(name: str) -> FsLane:
    for l in FS_LANES:
        if l.name == name:
            return l
    raise KeyError(name)


__all__ = [
    "CLASS_AUTHORITATIVE", "CLASS_DERIVED", "CLASS_HISTORICAL", "CLASS_CACHE",
    "CLASS_INSTALLATION", "CLASS_SHARED_ROW",
    "Direct", "Parent", "Installation", "DbLane", "FsLane",
    "DB_LANES", "FS_LANES",
    "lane", "db_tables", "narrator_owned_tables", "installation_tables",
    "erasable_tables", "parent_owned_tables", "owner_predicate", "select_sql",
    "delete_sql", "dependency_columns", "path_columns", "fs_lane",
]
