#!/usr/bin/env python3
"""READ ONLY. Phase 0 of WO-LOREVOX-PORTABLE-NARRATOR-01: the narrator-ownership audit.

Answers one question from three independent sources and shows where they
disagree: WHAT IN THIS INSTALLATION BELONGS TO A NARRATOR?

  1. LIVE database — PRIMARY.   The real SQLite file, opened read-only via
     URI `mode=ro`, path passed EXPLICITLY (the WSL profile carries stale
     DATA_DIR / DB_NAME exports; nothing here reads the environment). The
     script REFUSES to run unless it has proven the connection cannot
     write. Reads sqlite_master, PRAGMA table_info, PRAGMA foreign_key_list,
     and per-narrator row counts.
  2. REPO derivation — RECONCILIATION.  Table names created by migrations
     0001-current, `_EXTENDED_PERSON_SCOPED_TABLES` from db.py, and the
     erasure plan constants from narrator_erasure.py. All parsed from
     SOURCE TEXT with `ast` — nothing under `api/` is imported, so nothing
     resolves DATA_DIR, binds DB_PATH, or can create a database.
  3. FILESYSTEM inventory — READ ONLY.  Per-narrator directories under the
     erasure plan's roots, counted and sized, matched against the people
     table. Orphans are CLASSIFIED, never deleted or guessed into an owner.

What it writes: one markdown report and one JSON file, under --out, which
MUST be under .runtime/ or docs/reports/ (both gitignored; the report
carries real-family counts and paths). It refuses any other destination.

What it never does: write to the database, create -journal/-wal files,
touch DATA_DIR, import api.db, start the stack, or delete anything.

USAGE (stack down; Chris's whole part):

    cd /mnt/c/Users/chris/hornelore
    python3 scripts/phase0_narrator_ownership_audit.py \\
        --db /mnt/c/hornelore_data/db/hornelore.sqlite3 \\
        --data-root /mnt/c/hornelore_data \\
        --label desktop-live

`--label` names WHICH COPY this is (machine + root). The report header
records hostname, label and the repo commit (read from .git files, no git
process) so two machines' audits cannot be mistaken for each other.
Narrator data has provably been distributed across roots and backups
(WO §30); one root is never assumed to be everything.

Doctrine (CLAUDE.md): a claim about what code does with a value cites the
line that reads the value. Every classification below carries its
evidence columns so the reader can see WHY a table landed where it did,
and "unknown" is an honest answer the table is allowed to give.
"""
from __future__ import annotations

import argparse
import ast
import datetime as _dt
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

# Columns that name a person directly. Evidence, not a verdict (WO §4.3).
_PERSON_COLS = ("person_id", "narrator_id", "people_id", "subject_person_id")

# Tables this audit treats as INSTALLATION-owned on documented grounds.
# Each carries the reason so it can be argued with.
_INSTALLATION_TABLES = {
    "schema_migrations": "migration ledger — target configuration, not narrator data",
    # Migration 0053 creates these two (singular). The first run of this
    # audit looked for a plural name that does not exist and reported both
    # UNKNOWN — a name that resembled the thing, not the thing.
    "lori_guard_authority_override": "Guard Lab overrides, migration 0053 — installation-scoped (WO §5-E)",
    "lori_guard_control_state": "Guard Lab revision/control state, migration 0053 (WO §5-E)",
    "bio_fields": "global questionnaire schema definitions (WO §5-E)",
    "timeline_context_events": "global curated timeline-context library (WO §5-E)",
    "narrator_delete_audit": "deletion audit history — installation audit authority (WO §5-E)",
    "narrator_erasure_jobs": "erasure job records, migration 0049/0050 — operational, not life-story (WO §5-E, §12)",
    "sqlite_sequence": "SQLite internal",
}

# Filesystem roots the erasure plan does NOT treat as per-narrator, for the
# inventory's own classification. Taken from narrator_erasure.py at runtime
# too; these are the fallback labels.
_SHARED_ROOT_LABELS = {
    "backups": "historical backup — not per-narrator",
    "exports": "historical export — not per-narrator",
    "translations-cache": "shared cache (SHARED_PURGE)",
    "tts_cache": "installation cache",
    "authors": "installation / operator content",
    "uploads": "uploads — ownership decided by rows, see media_uploads",
}


# ══════════════════════════════════════════════════════════════════════
# Read-only database access — refuses unless proven
# ══════════════════════════════════════════════════════════════════════

def open_readonly_or_refuse(db_path: Path) -> sqlite3.Connection:
    """Open via URI mode=ro and PROVE it by attempting a write lock.

    `mode=ro` is the request; the proof is that BEGIN IMMEDIATE — which
    takes a RESERVED lock and is the first thing any write does — is
    refused by SQLite itself. A connection that accepted it is not
    read-only whatever the URI said, and this script exits.
    """
    if not db_path.is_file():
        raise SystemExit(f"REFUSING: database does not exist: {db_path}")
    uri = f"file:{db_path.as_posix()}?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True)
    except sqlite3.OperationalError as exc:
        raise SystemExit(f"REFUSING: could not open read-only: {exc}")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only = ON")
    try:
        con.execute("BEGIN IMMEDIATE")
        # If we get here the database accepted a write lock.
        try:
            con.execute("ROLLBACK")
        finally:
            con.close()
        raise SystemExit(
            "REFUSING: the connection accepted BEGIN IMMEDIATE, so read-only "
            "is NOT proven. Nothing was written (the transaction was rolled "
            "back), but this script will not proceed on an unproven "
            "connection.")
    except sqlite3.OperationalError as exc:
        msg = str(exc).lower()
        if "readonly" not in msg and "read-only" not in msg and "query_only" not in msg:
            con.close()
            raise SystemExit(
                f"REFUSING: unexpected error while proving read-only: {exc}")
    return con


# ══════════════════════════════════════════════════════════════════════
# 1. Live schema
# ══════════════════════════════════════════════════════════════════════

def live_schema(con: sqlite3.Connection) -> Dict[str, Dict[str, Any]]:
    tables: Dict[str, Dict[str, Any]] = {}
    rows = con.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
    for r in rows:
        name = r["name"]
        cols = [dict(c) for c in con.execute(f'PRAGMA table_info("{name}")')]
        fks = [dict(f) for f in con.execute(f'PRAGMA foreign_key_list("{name}")')]
        try:
            count = con.execute(f'SELECT COUNT(*) AS n FROM "{name}"').fetchone()["n"]
        except sqlite3.Error as exc:
            count = f"ERROR: {exc}"
        tables[name] = {
            "columns": [c["name"] for c in cols],
            "column_types": {c["name"]: c["type"] for c in cols},
            # on_delete is what decides whether erasure reaches a child row by
            # cascade or has to name it. Captured here so no reader has to
            # assert it from a migration's prose.
            "fks": [{"from": f["from"], "table": f["table"], "to": f["to"],
                     "on_delete": f.get("on_delete")} for f in fks],
            "row_count": count,
            "sql": r["sql"] or "",
        }
    return tables


def people_rows(con: sqlite3.Connection) -> List[Dict[str, Any]]:
    cols = {c["name"] for c in con.execute('PRAGMA table_info("people")')}
    want = [c for c in ("id", "display_name", "narrator_type", "testing_only",
                        "is_deleted", "deleted_at", "created_at") if c in cols]
    return [dict(r) for r in con.execute(
        f'SELECT {", ".join(want)} FROM people ORDER BY created_at')]


# ══════════════════════════════════════════════════════════════════════
# 2. Repo derivation — parsed from source, never imported
# ══════════════════════════════════════════════════════════════════════

_CREATE_RX = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"'`]?(\w+)[\"'`]?", re.IGNORECASE)
_ALTER_ADD_RX = re.compile(
    r"ALTER\s+TABLE\s+[\"'`]?(\w+)[\"'`]?\s+ADD\s+(?:COLUMN\s+)?[\"'`]?(\w+)", re.IGNORECASE)


def migration_tables(repo: Path) -> Dict[str, Dict[str, Any]]:
    """{table: {created_in, columns_mentioned}} from migrations/*.sql."""
    mig_dir = repo / "server" / "code" / "db" / "migrations"
    out: Dict[str, Dict[str, Any]] = {}
    files = sorted(mig_dir.glob("*.sql"))
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        # Statements only: drop `--` comment lines before matching. The first
        # run matched "CREATE TABLE" inside prose comments and reported
        # tables named 'IF', 'above', 'block', 'so' and 'statement'.
        code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("--"))
        for m in _CREATE_RX.finditer(code):
            out.setdefault(m.group(1), {"created_in": f.name, "added_columns": []})
        for m in _ALTER_ADD_RX.finditer(code):
            out.setdefault(m.group(1), {"created_in": None, "added_columns": []})
            out[m.group(1)]["added_columns"].append((m.group(2), f.name))
    out["_files"] = {"count": len(files), "first": files[0].name if files else None,
                     "last": files[-1].name if files else None}
    return out


def _literal_assignment(source: str, name: str) -> Any:
    """Return the literal value assigned to `name` at module level, via ast.

    Refuses (returns a marker) if the value is not a pure literal, so a
    future edit that makes it computed is visible rather than silently
    dropped.
    """
    tree = ast.parse(source)
    for node in tree.body:
        targets = []
        if isinstance(node, ast.Assign):
            targets = [t for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
            value = node.value
        else:
            continue
        if any(t.id == name for t in targets) and value is not None:
            try:
                return ast.literal_eval(value)
            except (ValueError, SyntaxError):
                return {"_not_literal": ast.get_source_segment(source, value)[:200]}
    return {"_absent": True}


def repo_constants(repo: Path) -> Dict[str, Any]:
    dbpy = (repo / "server" / "code" / "api" / "db.py").read_text(encoding="utf-8", errors="replace")
    erasure = (repo / "server" / "code" / "api" / "services" / "narrator_erasure.py").read_text(
        encoding="utf-8", errors="replace")
    return {
        "_EXTENDED_PERSON_SCOPED_TABLES": _literal_assignment(dbpy, "_EXTENDED_PERSON_SCOPED_TABLES"),
        "FIXED_TARGETS": _literal_assignment(erasure, "FIXED_TARGETS"),
        "SHARED_PURGE": _literal_assignment(erasure, "SHARED_PURGE"),
        "_LANE_TABLES": _literal_assignment(erasure, "_LANE_TABLES"),
    }


# ══════════════════════════════════════════════════════════════════════
# 3. Ownership evidence per table
# ══════════════════════════════════════════════════════════════════════

def _person_column(cols: List[str]) -> Optional[str]:
    for c in _PERSON_COLS:
        if c in cols:
            return c
    return None


def fk_path_to_people(name: str, schema: Dict[str, Dict[str, Any]],
                      seen: Optional[set] = None) -> Optional[List[str]]:
    """Shortest FK chain from `name` to an OWNED table, or None.

    An owned table is `people` itself, or any table carrying a direct
    person column. The first run of this audit required the chain to end
    at `people` by declared FK and so reported `turns` (23,652 rows — the
    conversation itself) as UNKNOWN: `turns` FKs to `sessions`, but
    `sessions.person_id` was added by ALTER in migration 0044 WITHOUT a
    foreign key. The chain is real; the constraint is just not declared.
    The report shows where the chain ends so the reader can see which
    hop is a column rather than a constraint.
    """
    seen = seen or set()
    if name in seen:
        return None
    seen = seen | {name}
    fks = schema.get(name, {}).get("fks", [])
    # A DIRECT FK to people wins over any longer chain. The first run
    # walked FKs in PRAGMA order and reported import_candidate through
    # photos, while its own "FKs->people: 1" column said otherwise.
    for fk in fks:
        if fk["table"] == "people":
            return [name, f"people (ON DELETE {fk.get('on_delete') or 'NO ACTION'})"]
    for fk in fks:
        parent = fk["table"]
        if _person_column(schema.get(parent, {}).get("columns", [])):
            return [name, f"{parent}(.{_person_column(schema[parent]['columns'])}, "
                          f"child FK ON DELETE {fk.get('on_delete') or 'NO ACTION'}; no FK to people)"]
        sub = fk_path_to_people(parent, schema, seen)
        if sub:
            return [name] + sub
    return None


def classify_tables(schema, migrations, consts) -> List[Dict[str, Any]]:
    ext = consts["_EXTENDED_PERSON_SCOPED_TABLES"]
    ext_tables = {t for t, _c in ext} if isinstance(ext, list) else set()
    lanes = consts["_LANE_TABLES"]
    lane_tables = set()
    if isinstance(lanes, dict):
        for _lane, (required, _opt) in lanes.items():
            lane_tables.update(required)

    rows = []
    for name, info in sorted(schema.items()):
        cols = info["columns"]
        pcol = _person_column(cols)
        chain = fk_path_to_people(name, schema)
        people_fks = [fk for fk in info["fks"] if fk["table"] == "people"]
        in_mig = name in migrations and name != "_files"
        # Columns the migrations never mention -> likely init_db()-owned.
        mig_text_cols = set()
        if in_mig:
            mig_text_cols = {c for c, _f in migrations[name].get("added_columns", [])}
        unmentioned = []
        if in_mig:
            sql_in_mig = _migration_create_sql(migrations, name)
            for c in cols:
                if c not in sql_in_mig and c not in mig_text_cols:
                    unmentioned.append(c)

        evidence = {
            "person_column": pcol,
            "fk_chain_to_people": " -> ".join(chain) if chain else None,
            "fks_to_people": len(people_fks),
            "in_extended_person_scoped": name in ext_tables,
            "in_erasure_lane_tables": name in lane_tables,
            "created_by_migration": migrations.get(name, {}).get("created_in") if in_mig else None,
            "columns_not_in_any_migration": unmentioned,
            "row_count": info["row_count"],
        }

        if name in _INSTALLATION_TABLES:
            proposed, why = "installation-owned", _INSTALLATION_TABLES[name]
        elif name == "people":
            proposed, why = "narrator-authoritative", "the identity row itself"
        elif evidence["in_extended_person_scoped"] or evidence["in_erasure_lane_tables"]:
            proposed, why = "narrator-owned (explicit)", "named by db.py / narrator_erasure.py"
        elif chain and pcol:
            proposed, why = "narrator-owned (FK + column)", "FK chain to people and a person column"
        elif chain:
            proposed, why = "narrator-owned (FK child)", "reachable from people by FK; verify parent"
        elif pcol:
            proposed, why = "UNKNOWN — person column, no FK", "WO §4.3: a column name alone is not ownership; decide"
        elif not in_mig:
            proposed, why = "UNKNOWN — not in migrations", "created by init_db() or elsewhere; decide"
        else:
            proposed, why = "UNKNOWN — no person link found", "global, cache, or orphan lane; decide"
        rows.append({"table": name, "proposed_class": proposed, "why": why, **evidence})
    return rows


def _migration_create_sql(migrations: Dict[str, Any], name: str) -> str:
    """Return the migration file text that created `name` (for column checks)."""
    created = migrations.get(name, {}).get("created_in")
    if not created:
        return ""
    p = REPO_ROOT / "server" / "code" / "db" / "migrations" / created
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# ══════════════════════════════════════════════════════════════════════
# 4. Per-narrator row counts
# ══════════════════════════════════════════════════════════════════════

def per_narrator_counts(con, schema, table_rows, people) -> Dict[str, Dict[str, Any]]:
    """{person_id: {table: count}} for every table with a direct person column,
    plus one-level FK children whose parent has a direct column."""
    out: Dict[str, Dict[str, Any]] = {p["id"]: {} for p in people}
    direct = {r["table"]: r["person_column"] for r in table_rows if r["person_column"]}
    for table, col in direct.items():
        try:
            for r in con.execute(
                    f'SELECT "{col}" AS pid, COUNT(*) AS n FROM "{table}" GROUP BY "{col}"'):
                pid = r["pid"]
                if pid in out:
                    out[pid][table] = r["n"]
                else:
                    out.setdefault("_unmatched_person_ids", {}).setdefault(table, {})[str(pid)] = r["n"]
        except sqlite3.Error as exc:
            out.setdefault("_errors", {})[table] = str(exc)
    # One-level FK children of direct tables.
    for name, info in schema.items():
        if name in direct:
            continue
        for fk in info["fks"]:
            parent = fk["table"]
            if parent in direct:
                pcol = direct[parent]
                try:
                    q = (f'SELECT p."{pcol}" AS pid, COUNT(*) AS n FROM "{name}" c '
                         f'JOIN "{parent}" p ON c."{fk["from"]}" = p."{fk["to"]}" GROUP BY p."{pcol}"')
                    for r in con.execute(q):
                        if r["pid"] in out:
                            out[r["pid"]][f"{name} (via {parent})"] = r["n"]
                except sqlite3.Error as exc:
                    out.setdefault("_errors", {})[f"{name} via {parent}"] = str(exc)
                break
    return out


# ══════════════════════════════════════════════════════════════════════
# 5. Path columns — source-machine absolute vs relative (WO §8.5)
# ══════════════════════════════════════════════════════════════════════

_PATHISH_COL_RX = re.compile(r"(path|file|uri|url|dir|location|ref)", re.IGNORECASE)


def path_column_survey(con, schema, data_root: Path) -> List[Dict[str, Any]]:
    root_str = data_root.as_posix()
    out = []
    for name, info in schema.items():
        for col in info["columns"]:
            if not _PATHISH_COL_RX.search(col):
                continue
            if not (info["column_types"].get(col, "") or "TEXT").upper().startswith(("TEXT", "VARCHAR", "CHAR", "")):
                continue
            try:
                total = con.execute(f'SELECT COUNT(*) AS n FROM "{name}" WHERE "{col}" IS NOT NULL AND "{col}" != \'\'').fetchone()["n"]
                if not total:
                    continue
                absolute = con.execute(
                    f'SELECT COUNT(*) AS n FROM "{name}" WHERE "{col}" LIKE \'/%\' OR "{col}" LIKE \'_:\\%\'').fetchone()["n"]
                under_root = con.execute(
                    f'SELECT COUNT(*) AS n FROM "{name}" WHERE "{col}" LIKE ?', (root_str + "%",)).fetchone()["n"]
                sample = con.execute(
                    f'SELECT "{col}" AS v FROM "{name}" WHERE "{col}" IS NOT NULL AND "{col}" != \'\' LIMIT 1').fetchone()["v"]
            except sqlite3.Error as exc:
                out.append({"table": name, "column": col, "error": str(exc)})
                continue
            out.append({"table": name, "column": col, "non_empty": total,
                        "absolute": absolute, "under_data_root": under_root,
                        "sample": str(sample)[:120]})
    return out


# ══════════════════════════════════════════════════════════════════════
# 6. Filesystem inventory — read only
# ══════════════════════════════════════════════════════════════════════

def _dir_stats(p: Path, max_files: int = 200000) -> Tuple[int, int, bool]:
    files = 0
    size = 0
    truncated = False
    for dirpath, _dirs, filenames in os.walk(p):
        for fn in filenames:
            files += 1
            try:
                size += os.lstat(os.path.join(dirpath, fn)).st_size
            except OSError:
                pass
            if files >= max_files:
                truncated = True
                return files, size, truncated
    return files, size, truncated


def dynamic_lane_inventory(con, data_root: Path, people) -> Dict[str, Any]:
    """Files whose ownership is proven THROUGH ROWS, not by directory name.

    Mirrors narrator_erasure._dynamic_plan (narrator_erasure.py:357-373):
      trip_sources    DATA_DIR/trip_sources/<source-id>       via trip_sources.trip_id -> trips.person_id
      import_staging  DATA_DIR/import_staging/<batch-id>       via import_batch.person_id
                      DATA_DIR/import_staging/.incoming/<batch-id>
    Travel documents live here, keyed by source id — a per-person walk
    cannot see them. Directories on disk that NO row names are reported
    as orphans, never touched.
    """
    known = {p["id"]: p for p in people}
    out: Dict[str, Any] = {"lanes": [], "orphan_dirs": []}

    def _lane(label, root_parts, rows, id_col, pid_col):
        root = data_root.joinpath(*root_parts)
        entry = {"lane": label, "root": root.as_posix(), "exists": root.is_dir(),
                 "referenced": [], "orphans": []}
        referenced_ids = set()
        for r in rows:
            sid, pid = str(r[id_col]), r[pid_col]
            referenced_ids.add(sid)
            d = root / sid
            files, size, trunc = _dir_stats(d) if d.is_dir() else (0, 0, False)
            p = known.get(pid)
            entry["referenced"].append({
                "id": sid, "person_id": pid,
                "display_name": p.get("display_name") if p else None,
                "person_class": ("known narrator" if p and not p.get("is_deleted")
                                 else "soft-deleted narrator" if p else "UNKNOWN person id"),
                "dir_exists": d.is_dir(), "files": files, "bytes": size, "truncated": trunc})
        if root.is_dir():
            for child in sorted(root.iterdir()):
                if child.is_dir() and not child.name.startswith(".") and child.name not in referenced_ids:
                    files, size, trunc = _dir_stats(child)
                    entry["orphans"].append({"id": child.name, "files": files, "bytes": size})
                    out["orphan_dirs"].append({"lane": label, "id": child.name, "files": files, "bytes": size})
        out["lanes"].append(entry)

    try:
        rows = [dict(r) for r in con.execute(
            "SELECT s.id AS id, t.person_id AS person_id FROM trip_sources s "
            "JOIN trips t ON t.id = s.trip_id")]
        _lane("trip_sources", ("trip_sources",), rows, "id", "person_id")
    except sqlite3.Error as exc:
        out["lanes"].append({"lane": "trip_sources", "error": str(exc)})
    try:
        rows = [dict(r) for r in con.execute("SELECT id, person_id FROM import_batch")]
        _lane("import_staging", ("import_staging",), rows, "id", "person_id")
        _lane("import_staging_incoming", ("import_staging", ".incoming"), rows, "id", "person_id")
    except sqlite3.Error as exc:
        out["lanes"].append({"lane": "import_staging", "error": str(exc)})
    return out


def filesystem_inventory(data_root: Path, consts, people) -> Dict[str, Any]:
    known = {p["id"]: p for p in people}
    fixed = consts["FIXED_TARGETS"]
    per_narrator_roots = [(k, parts) for k, parts in fixed] if isinstance(fixed, (list, tuple)) else []
    result: Dict[str, Any] = {"per_narrator_roots": [], "top_level": [], "unknown_ids": []}

    for key, parts in per_narrator_roots:
        root = data_root.joinpath(*parts)
        entry = {"target": key, "root": root.as_posix(), "exists": root.is_dir(), "narrators": []}
        if root.is_dir():
            for child in sorted(root.iterdir()):
                if not child.is_dir():
                    continue
                files, size, trunc = _dir_stats(child)
                pid = child.name
                p = known.get(pid)
                cls = ("known narrator" if p and not p.get("is_deleted")
                       else "soft-deleted narrator" if p
                       else "UNKNOWN id — orphan, classify")
                if cls.startswith("UNKNOWN"):
                    result["unknown_ids"].append({"target": key, "id": pid, "files": files, "bytes": size})
                entry["narrators"].append({"id": pid, "class": cls,
                                           "display_name": p.get("display_name") if p else None,
                                           "files": files, "bytes": size, "truncated": trunc})
        result["per_narrator_roots"].append(entry)

    # Top level, shallow: what else is in the data root.
    for child in sorted(data_root.iterdir()):
        if child.name in ("backups",):
            # Do not walk backups; report presence and immediate size only.
            result["top_level"].append({"name": child.name, "kind": "dir", "note": "NOT walked — historical backup root"})
            continue
        if child.is_dir():
            files, size, trunc = _dir_stats(child, max_files=50000)
            result["top_level"].append({"name": child.name, "kind": "dir", "files": files, "bytes": size,
                                        "truncated": trunc,
                                        "label": _SHARED_ROOT_LABELS.get(child.name, "")})
        else:
            try:
                result["top_level"].append({"name": child.name, "kind": "file", "bytes": child.stat().st_size})
            except OSError:
                result["top_level"].append({"name": child.name, "kind": "file", "bytes": None})
    return result


# ══════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════

def _fmt_bytes(n: Any) -> str:
    if not isinstance(n, (int, float)):
        return str(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _machine_name() -> str:
    import socket
    try:
        return socket.gethostname()
    except Exception:
        return "unknown-host"


def _repo_head_without_git(repo: Path) -> str:
    """The commit the audit code came from, read from `.git/` FILES.

    No `git` subprocess: CLAUDE.md records that a git command from a
    sandbox can leave `.git/index.lock` behind, and an audit that is
    read-only by contract must not take any lock at all. Returns
    `unknown (<reason>)` rather than guessing.
    """
    try:
        head = (repo / ".git" / "HEAD").read_text(encoding="utf-8").strip()
    except OSError as exc:
        return f"unknown ({exc.__class__.__name__})"
    if not head.startswith("ref:"):
        return head[:12] + " (detached)"
    ref = head.split(":", 1)[1].strip()
    loose = repo / ".git" / ref
    try:
        if loose.is_file():
            return loose.read_text(encoding="utf-8").strip()[:12] + f" ({ref})"
        packed = (repo / ".git" / "packed-refs").read_text(encoding="utf-8")
        for line in packed.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1] == ref:
                return parts[0][:12] + f" ({ref}, packed)"
    except OSError as exc:
        return f"unknown ({exc.__class__.__name__})"
    return f"unknown ({ref} not found)"


def build_report(ctx: Dict[str, Any]) -> str:
    L: List[str] = []
    w = L.append
    w("# Phase 0 — narrator ownership audit (READ ONLY)")
    w("")
    w(f"**Machine:** `{ctx['machine']}`  ·  **Label:** `{ctx['label']}`  ·  "
      f"**Repo commit:** `{ctx['commit']}`")
    w(f"**Database:** `{ctx['db']}`  ·  opened `mode=ro`, write lock refused by SQLite: **proven**")
    w(f"**Data root:** `{ctx['data_root']}`  ·  **Repo:** `{ctx['repo']}`")
    w(f"**Interpreter:** `{sys.executable}` {sys.version.split()[0]}  ·  **Run:** {ctx['when']}")
    w(f"**Migrations parsed:** {ctx['migrations']['_files']['count']} "
      f"(`{ctx['migrations']['_files']['first']}` … `{ctx['migrations']['_files']['last']}`)")
    w("")
    w("Every classification is PROPOSED with its evidence beside it. `UNKNOWN` is an "
      "honest answer this table is allowed to give; Phase 1 decides those rows, this "
      "audit does not.")
    w("")

    # People
    w("## People (live)")
    w("")
    w("| id | display_name | narrator_type | testing_only | deleted |")
    w("|---|---|---|---|---|")
    for p in ctx["people"]:
        w(f"| `{p['id'][:8]}` | {p.get('display_name')} | {p.get('narrator_type')} "
          f"| {p.get('testing_only')} | {p.get('is_deleted') or p.get('deleted_at') or ''} |")
    w("")

    # Repo constants
    c = ctx["consts"]
    w("## Repo constants (parsed from source, not imported)")
    w("")
    ext = c["_EXTENDED_PERSON_SCOPED_TABLES"]
    w(f"* `db.py::_EXTENDED_PERSON_SCOPED_TABLES` — {len(ext) if isinstance(ext, list) else ext} entries")
    ft = c["FIXED_TARGETS"]
    w(f"* `narrator_erasure.py::FIXED_TARGETS` — {[k for k, _ in ft] if isinstance(ft, (list, tuple)) else ft}")
    sp = c["SHARED_PURGE"]
    w(f"* `narrator_erasure.py::SHARED_PURGE` — {[k for k, _ in sp] if isinstance(sp, (list, tuple)) else sp}")
    lt = c["_LANE_TABLES"]
    w(f"* `narrator_erasure.py::_LANE_TABLES` — {list(lt.keys()) if isinstance(lt, dict) else lt}")
    w("")

    # Table matrix
    rows = ctx["table_rows"]
    w("## Table ownership matrix (live schema × repo evidence)")
    w("")
    w("| table | rows | person col | FK chain to people | FKs→people | in _EXTENDED | in erasure lanes | migration | cols not in any migration | PROPOSED | why |")
    w("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        w(f"| `{r['table']}` | {r['row_count']} | {r['person_column'] or ''} | {r['fk_chain_to_people'] or ''} "
          f"| {r['fks_to_people']} | {'✓' if r['in_extended_person_scoped'] else ''} "
          f"| {'✓' if r['in_erasure_lane_tables'] else ''} | {r['created_by_migration'] or '—'} "
          f"| {', '.join(r['columns_not_in_any_migration']) or ''} | **{r['proposed_class']}** | {r['why']} |")
    w("")
    unknown = [r for r in rows if r["proposed_class"].startswith("UNKNOWN")]
    w(f"**Tables needing a Phase 1 decision: {len(unknown)}** — "
      + (", ".join(f"`{r['table']}`" for r in unknown) if unknown else "none"))
    multi = [r for r in rows if r["fks_to_people"] > 1]
    w(f"**Tables with more than one FK to people (possible cross-person references, WO §13): "
      f"{len(multi)}** — " + (", ".join(f"`{r['table']}`" for r in multi) if multi else "none"))
    w("")

    # Reconciliation
    w("## Reconciliation — where the sources disagree")
    w("")
    live = set(ctx["schema"].keys())
    mig = {k for k in ctx["migrations"].keys() if k != "_files"}
    only_live = sorted(live - mig)
    only_mig = sorted(mig - live)
    w(f"* Tables in the LIVE database but in no migration: {only_live or 'none'} — "
      "created by `init_db()` or by hand; ownership must be decided, not assumed")
    w(f"* Tables in migrations but ABSENT live: {only_mig or 'none'} — dropped, renamed, or a migration never ran here")
    ext_tables = {t for t, _ in ext} if isinstance(ext, list) else set()
    w(f"* `_EXTENDED_PERSON_SCOPED_TABLES` entries with NO live table: {sorted(ext_tables - live) or 'none'}")
    lane_tables = set()
    if isinstance(lt, dict):
        for _l, (req, _o) in lt.items():
            lane_tables.update(req)
    w(f"* Erasure lane tables with NO live table: {sorted(lane_tables - live) or 'none'}")
    w("")

    # Per narrator
    w("## Per-narrator row counts (direct person columns + one-level FK children)")
    w("")
    pn = ctx["per_narrator"]
    for p in ctx["people"]:
        counts = pn.get(p["id"], {})
        w(f"### `{p['id'][:8]}` {p.get('display_name')}  (testing_only={p.get('testing_only')})")
        w("")
        if not counts:
            w("_no rows in any person-linked table_")
        else:
            for t, n in sorted(counts.items(), key=lambda kv: -kv[1] if isinstance(kv[1], int) else 0):
                w(f"* `{t}`: {n}")
        w("")
    if "_unmatched_person_ids" in pn:
        w("### Rows whose person id matches NO people row — orphans to classify")
        w("")
        for t, ids in pn["_unmatched_person_ids"].items():
            for pid, n in ids.items():
                w(f"* `{t}` → `{pid[:8] if pid else pid}`: {n} rows")
        w("")
    if "_errors" in pn:
        w("### Count errors (reported, not hidden)")
        w("")
        for t, e in pn["_errors"].items():
            w(f"* `{t}`: {e}")
        w("")

    # Paths
    w("## Path-like columns (WO §8.5 — absolute source paths must not restore literally)")
    w("")
    w("| table.column | non-empty | absolute | under data root | sample |")
    w("|---|---|---|---|---|")
    for r in ctx["paths"]:
        if "error" in r:
            w(f"| `{r['table']}.{r['column']}` | ERROR | | | {r['error']} |")
        else:
            w(f"| `{r['table']}.{r['column']}` | {r['non_empty']} | {r['absolute']} | {r['under_data_root']} | `{r['sample']}` |")
    w("")

    # Filesystem
    fs = ctx["fs"]
    w("## Filesystem inventory (read only) — erasure FIXED_TARGETS roots")
    w("")
    for e in fs["per_narrator_roots"]:
        w(f"### `{e['target']}` — `{e['root']}` — {'exists' if e['exists'] else 'ABSENT'}")
        w("")
        if e["narrators"]:
            w("| id | class | display_name | files | bytes |")
            w("|---|---|---|---|---|")
            for n in e["narrators"]:
                w(f"| `{n['id'][:8]}` | {n['class']} | {n['display_name'] or ''} | {n['files']}{'+' if n['truncated'] else ''} | {_fmt_bytes(n['bytes'])} |")
        elif e["exists"]:
            w("_empty_")
        w("")
    if fs["unknown_ids"]:
        w(f"**Orphan narrator directories (id matches no people row): {len(fs['unknown_ids'])}** — classify in Phase 1, never delete here.")
        w("")

    dyn = ctx["dyn"]
    w("## Dynamic lanes — ownership proven through rows (travel documents, import staging)")
    w("")
    w("Mirrors `narrator_erasure._dynamic_plan` (`narrator_erasure.py:357-373`). These "
      "directories are keyed by source/batch id, not person id, so a per-person walk cannot "
      "see them; the owning narrator is the row's `trips.person_id` / `import_batch.person_id`.")
    w("")
    for lane in dyn["lanes"]:
        if "error" in lane:
            w(f"### `{lane['lane']}` — ERROR: {lane['error']}")
            w("")
            continue
        w(f"### `{lane['lane']}` — `{lane['root']}` — {'exists' if lane['exists'] else 'ABSENT'}")
        w("")
        if lane["referenced"]:
            w("| id | owner | owner class | dir exists | files | bytes |")
            w("|---|---|---|---|---|---|")
            for r in lane["referenced"]:
                w(f"| `{r['id'][:8]}` | `{(r['person_id'] or '')[:8]}` {r['display_name'] or ''} "
                  f"| {r['person_class']} | {r['dir_exists']} | {r['files']}{'+' if r['truncated'] else ''} | {_fmt_bytes(r['bytes'])} |")
        else:
            w("_no rows reference this lane_")
        if lane["orphans"]:
            w("")
            w(f"Orphan directories here (no row names them): {len(lane['orphans'])} — "
              + ", ".join(f"`{o['id'][:8]}` ({o['files']} files)" for o in lane["orphans"][:20]))
        w("")

    w("### Data root, top level (shallow)")
    w("")
    w("| entry | kind | files | bytes | label |")
    w("|---|---|---|---|---|")
    for t in fs["top_level"]:
        w(f"| `{t['name']}` | {t['kind']} | {t.get('files', '')}{'+' if t.get('truncated') else ''} "
          f"| {_fmt_bytes(t.get('bytes'))} | {t.get('label') or t.get('note') or ''} |")
    w("")

    w("## What this audit did NOT do")
    w("")
    w("* Did not write to the database (proven), create journal files, or touch `DATA_DIR`.")
    w("* Did not import `api.db` or any module under `api/` — constants were parsed from source text.")
    w("* Did not walk `backups/`. Did not hash files. Did not follow symlinks into per-narrator dirs.")
    w("* Did not decide any `UNKNOWN` row. That is Phase 1's job, with this table in front of it.")
    return "\n".join(L) + "\n"


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

def _refuse_unless_gitignored_out(out: Path, repo: Path) -> None:
    try:
        rel = out.resolve().relative_to(repo.resolve())
    except ValueError:
        return  # outside the repo entirely is fine
    top = rel.parts[0] if rel.parts else ""
    if top == ".runtime" or (len(rel.parts) > 1 and rel.parts[0] == "docs" and rel.parts[1] == "reports"):
        return
    raise SystemExit(
        f"REFUSING: --out {out} is inside the repository but not under .runtime/ "
        f"or docs/reports/. This report carries real-family counts and paths and "
        f"must never be stageable.")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True, type=Path,
                    help="ABSOLUTE path to the live SQLite file. Required; the environment is never consulted.")
    ap.add_argument("--data-root", required=True, type=Path,
                    help="ABSOLUTE DATA_DIR the running product uses (e.g. /mnt/c/hornelore_data).")
    ap.add_argument("--repo", type=Path, default=REPO_ROOT)
    ap.add_argument("--out", type=Path, default=None,
                    help="report directory; default .runtime/eval/phase0-ownership-audit-<label>-<ts>/")
    ap.add_argument("--label", default="",
                    help="which copy this is (e.g. desktop-live, desktop-backup-0723, laptop-live). "
                         "Goes into the report header and the output directory name so two "
                         "machines' reports cannot be confused.")
    args = ap.parse_args(argv)

    if not args.db.is_absolute() or not args.data_root.is_absolute():
        raise SystemExit("REFUSING: --db and --data-root must be absolute paths.")
    if not args.data_root.is_dir():
        raise SystemExit(f"REFUSING: data root is not a directory: {args.data_root}")

    when = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    label = re.sub(r"[^A-Za-z0-9._-]+", "-", args.label.strip()) or "unlabelled"
    out = args.out or (args.repo / ".runtime" / "eval" / f"phase0-ownership-audit-{label}-{when}")
    _refuse_unless_gitignored_out(out, args.repo)

    con = open_readonly_or_refuse(args.db)
    try:
        schema = live_schema(con)
        people = people_rows(con)
        migrations = migration_tables(args.repo)
        consts = repo_constants(args.repo)
        table_rows = classify_tables(schema, migrations, consts)
        per_narrator = per_narrator_counts(con, schema, table_rows, people)
        paths = path_column_survey(con, schema, args.data_root)
        dyn = dynamic_lane_inventory(con, args.data_root, people)
    finally:
        con.close()
    fs = filesystem_inventory(args.data_root, consts, people)

    ctx = {"db": args.db.as_posix(), "data_root": args.data_root.as_posix(), "repo": args.repo.as_posix(),
           "when": when, "label": label, "machine": _machine_name(),
           "commit": _repo_head_without_git(args.repo), "schema": schema, "people": people, "migrations": migrations, "consts": consts,
           "table_rows": table_rows, "per_narrator": per_narrator, "paths": paths, "fs": fs, "dyn": dyn}
    report = build_report(ctx)

    out.mkdir(parents=True, exist_ok=True)
    (out / "ownership-audit.md").write_text(report, encoding="utf-8")
    slim = {k: v for k, v in ctx.items() if k != "schema"}
    slim["schema"] = {t: {k: v for k, v in i.items() if k != "sql"} for t, i in schema.items()}
    (out / "ownership-audit.json").write_text(json.dumps(slim, indent=2, default=str), encoding="utf-8")

    unknown = sum(1 for r in table_rows if r["proposed_class"].startswith("UNKNOWN"))
    print(f"wrote {out / 'ownership-audit.md'}")
    dyn_refs = sum(len(l.get("referenced", [])) for l in dyn["lanes"])
    print(f"tables={len(schema)} people={len(people)} unknown_tables={unknown} "
          f"orphan_dirs={len(fs['unknown_ids'])} path_columns={len(paths)} "
          f"dynamic_lane_refs={dyn_refs} dynamic_lane_orphans={len(dyn['orphan_dirs'])} "
          f"migrations={migrations['_files']['count']}")
    print("read-only: PROVEN (BEGIN IMMEDIATE refused by SQLite)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
