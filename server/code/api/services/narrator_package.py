"""Lorevox Narrator Package v1 — WO-LOREVOX-PORTABLE-NARRATOR-01 Phase 2 (export + validate).

ONE service (§28.5). The operator UI and `scripts/narrator_package.py` both call
this; there is never a second implementation of portability. Dry-run and
Restore are Phase 3 and are not here.

THE INVARIANT (§30): given ONE selected narrator id, follow
`narrator_data_inventory.py` and export that narrator's complete portable
state — the complete travel domain whenever present — without sweeping any
other narrator, any test data, or any unreferenced filesystem residue into
the package. Nothing in this module knows a narrator's name.

How an export is built:

  1. SNAPSHOT (§28.2)   `sqlite3.Connection.backup()` of the live database into
                         the exporter's temporary directory. Every row below is
                         read from that copy; the live file is never read twice.
  2. SELECT              for each narrator-owned lane in the declaration, in
                         declaration order: `select_sql(table)` bound to `:pid`.
                         A lane whose table the source schema lacks is recorded
                         as `lane_absent`, never treated as empty.
  3. INTEGRITY (§30)     every FK the snapshot declares, plus every declared
                         `ColumnRef`, from every exported row: the referenced row
                         must be in the package (narrator-owned parent), or be an
                         installation row (recorded as an installation dependency
                         Restore must satisfy), or be a different person named by a
                         declared `external_person_columns` column (recorded, never
                         pulled). Anything else is UNRESOLVED → refuse, naming it.
  4. PATHS (§8.5)        declared `path_columns` are normalised to DATA_DIR-relative;
                         a value outside DATA_DIR, or naming nothing on disk, refuses.
  5. FILES               person-keyed lanes are walked whole; row-keyed lanes only
                         for the ids the snapshot's rows resolve; conditional lanes
                         only for the sub-paths their `conditional_sql` returns.
                         Unreferenced directories are residue: reported, not packed,
                         and never a reason to refuse.
  6. CONSISTENCY (§8.3)  the file set is measured (path, size, mtime) before and
                         after collection; any change refuses the package.
  7. SECRETS (§8.6)      record text is scanned for credential shapes; a hit refuses.
  8. BAG (§28.1)         `bagit.make_bag` on the temporary staging dir ONLY,
                         SHA-256, `lorevox-manifest.json` as a tag file, validated.
  9. ZIP (§28.3)         streamed into a temporary file with ZIP64, then renamed.

Refusal is a first-class outcome: `ExportRefused.reasons` names every reason
found (not just the first) so the operator can fix them in one pass. No
"best effort" package is ever labelled complete (§7.4).
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from . import narrator_data_inventory as inv
from .chat_memory_paths import export_basenames
from .narrator_erasure import validate_root

PACKAGE_FORMAT = "lorevox-narrator-package"
PACKAGE_FORMAT_VERSION = "1.0"
PACKAGE_KIND = "restore_only_v1"      # §10.1: one import meaning — this narrator as this narrator
SOURCE_APP = "hornelore"
MANIFEST_NAME = "lorevox-manifest.json"

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

# §8.6 — credential shapes. Ordinary URLs and narrator text do not match these.
_SECRET_PATTERNS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    ("authorization_header", re.compile(r"\bAuthorization\s*:\s*(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{8,}", re.I)),
    ("bearer_token",         re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{20,}")),
    ("google_oauth_token",   re.compile(r"\bya29\.[A-Za-z0-9._-]{20,}")),
    ("google_api_key",       re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("oauth_refresh_token",  re.compile(r"\b1//0[A-Za-z0-9_-]{20,}")),
    ("signed_query_credential", re.compile(r"[?&](access_token|refresh_token|client_secret|api_key|X-Goog-Signature|Signature)=[^&\s\"']{8,}", re.I)),
    ("cookie_header",        re.compile(r"\b(Set-Cookie|Cookie)\s*:\s*\S+=\S{8,}", re.I)),
    ("private_key_block",    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("dotenv_secret_line",   re.compile(r"^(?:[A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|API_KEY)[A-Z0-9_]*)=\S{8,}$", re.M)),
)


class ExportRefused(Exception):
    """The package was NOT produced. `reasons` is the complete list."""

    def __init__(self, reasons: List[Dict[str, Any]]):
        self.reasons = reasons
        super().__init__("EXPORT REFUSED — %d reason(s): %s" % (
            len(reasons), "; ".join(r.get("code", "?") for r in reasons[:8])))


@dataclass
class ExportResult:
    package_path: Path
    package_id: str
    manifest: Dict[str, Any]
    warnings: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ValidationReport:
    ok: bool
    package_path: Path
    manifest: Optional[Dict[str, Any]]
    problems: List[str]
    payload_files: int
    payload_bytes: int


# ── small helpers ────────────────────────────────────────────────────────

def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_file(path: Path) -> Tuple[str, int]:
    h = hashlib.sha256()
    n = 0
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


def _safe_segment(value: Any) -> Optional[str]:
    s = str(value or "").strip()
    if not s or not _SAFE_ID.match(s) or s in (".", ".."):
        return None
    return s


def _repo_head(repo: Path) -> str:
    """Commit of the code doing the export, read from .git FILES (no git process)."""
    try:
        head = (repo / ".git" / "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith("ref:"):
            return head[:40]
        ref = head.split(":", 1)[1].strip()
        loose = repo / ".git" / ref
        if loose.is_file():
            return loose.read_text(encoding="utf-8").strip()[:40]
        for line in (repo / ".git" / "packed-refs").read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1] == ref:
                return parts[0][:40]
    except OSError:
        pass
    return "unknown"


def _display_slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", (name or "").strip()).strip("_")
    return s[:48] or "Narrator"


def _measure_tree(paths: Iterable[Path]) -> Dict[str, Tuple[int, int]]:
    """path -> (size, mtime_ns) for every FILE under the given paths."""
    out: Dict[str, Tuple[int, int]] = {}
    for p in paths:
        if p.is_file():
            st = p.stat()
            out[str(p)] = (st.st_size, st.st_mtime_ns)
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_symlink():
                    continue
                if f.is_file():
                    st = f.stat()
                    out[str(f)] = (st.st_size, st.st_mtime_ns)
    return out


# ── the snapshot ─────────────────────────────────────────────────────────

def _snapshot(db_path: Path, into: Path) -> sqlite3.Connection:
    """§28.2: one consistent point-in-time copy, read from thereafter."""
    src = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(str(into))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    con = sqlite3.connect(f"file:{into.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _tables(con: sqlite3.Connection) -> Set[str]:
    return {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}


def _columns(con: sqlite3.Connection, table: str) -> List[str]:
    return [r["name"] for r in con.execute(f'PRAGMA table_info("{table}")')]


def _pk_columns(con: sqlite3.Connection, table: str) -> List[str]:
    rows = [r for r in con.execute(f'PRAGMA table_info("{table}")') if r["pk"]]
    rows.sort(key=lambda r: r["pk"])
    cols = [r["name"] for r in rows]
    return cols or ["rowid"]


def _fks(con: sqlite3.Connection, table: str) -> List[Tuple[str, str, str]]:
    """(from_column, parent_table, parent_column)"""
    out = []
    for r in con.execute(f'PRAGMA foreign_key_list("{table}")'):
        out.append((r["from"], r["table"], r["to"] or "id"))
    return out


def _schema_fingerprint(con: sqlite3.Connection) -> str:
    h = hashlib.sha256()
    for r in con.execute("SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name"):
        h.update((r[0] + "\x00" + r[1] + "\x00" + r[2] + "\n").encode("utf-8"))
    return h.hexdigest()[:16]


def _applied_migrations(con: sqlite3.Connection) -> List[str]:
    if "schema_migrations" not in _tables(con):
        return []
    cols = _columns(con, "schema_migrations")
    col = "filename" if "filename" in cols else ("name" if "name" in cols else cols[0])
    return [str(r[0]) for r in con.execute(f'SELECT "{col}" FROM schema_migrations ORDER BY 1')]


# ── the export ───────────────────────────────────────────────────────────

class _Refusals:
    def __init__(self):
        self.items: List[Dict[str, Any]] = []

    def add(self, code: str, **detail):
        self.items.append({"code": code, **detail})

    def raise_if_any(self):
        if self.items:
            raise ExportRefused(self.items)


def export_narrator(person_id: str, *, data_dir: Path, db_path: Path, out_dir: Path,
                    package_id: Optional[str] = None, repo_root: Optional[Path] = None,
                    _after_collect_hook=None) -> ExportResult:
    """Build `<Narrator>_<package-id>.lorevox.zip` under `out_dir`, or raise ExportRefused.

    Read-only against the source (§8.1). `data_dir` and `db_path` are explicit —
    the environment is never consulted, so a stale export cannot pick the wrong
    root. `_after_collect_hook` exists for the consistency test only.
    """
    pid = _safe_segment(person_id)
    if not pid:
        raise ExportRefused([{"code": "unsafe_person_id", "value": str(person_id)[:64]}])
    root = validate_root(data_dir)
    db_path = Path(db_path)
    if not db_path.is_absolute() or not db_path.is_file():
        raise ExportRefused([{"code": "db_not_found", "path": str(db_path)}])
    out_dir = Path(out_dir)
    if not out_dir.is_absolute():
        raise ExportRefused([{"code": "out_dir_not_absolute", "path": str(out_dir)}])
    try:
        out_dir.resolve().relative_to(root)
        raise ExportRefused([{"code": "out_dir_inside_data_dir", "path": str(out_dir),
                              "detail": "a package must never be written into the data root it exports"}])
    except ValueError:
        pass
    out_dir.mkdir(parents=True, exist_ok=True)
    repo_root = repo_root or Path(__file__).resolve().parents[3]
    package_id = package_id or uuid.uuid4().hex[:12]
    refuse = _Refusals()
    warnings: List[Dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="lorevox-pkg-") as tmp:
        tmp = Path(tmp)
        staging = tmp / "bag"
        records_dir = staging / "records"
        files_dir = staging / "files"
        records_dir.mkdir(parents=True)
        files_dir.mkdir(parents=True)

        con = _snapshot(db_path, tmp / "snapshot.sqlite3")
        try:
            present = _tables(con)
            if "people" not in present:
                raise ExportRefused([{"code": "no_people_table", "db": str(db_path)}])
            person = con.execute("SELECT * FROM people WHERE id = ?", (pid,)).fetchone()
            if person is None:
                raise ExportRefused([{"code": "narrator_not_found", "person_id": pid}])
            display_name = str(person["display_name"] or "")

            # ── pass 1: which rows are the narrator's (primary keys only) ──
            owned_tables = [t for t in inv.narrator_owned_tables()]
            lanes_absent: List[str] = []
            ids: Dict[str, Set[Tuple[Any, ...]]] = {}
            pk_cols: Dict[str, List[str]] = {}
            for table in owned_tables:
                if table not in present:
                    lanes_absent.append(table)
                    continue
                pk_cols[table] = _pk_columns(con, table)
                sel = ", ".join(f'"{table}"."{c}"' for c in pk_cols[table])
                sql = f'SELECT {sel} FROM "{table}" WHERE {inv.owner_predicate(table)}'
                try:
                    ids[table] = {tuple(r) for r in con.execute(sql, {"pid": pid})}
                except sqlite3.Error as exc:
                    refuse.add("lane_unqueryable", table=table, error=str(exc))
            refuse.raise_if_any()
            if lanes_absent:
                warnings.append({"code": "lanes_absent_in_source_schema", "tables": sorted(lanes_absent)})

            owned_set = set(owned_tables)
            installation_set = set(inv.installation_tables())
            external_cols = inv.dependency_columns()
            path_cols = inv.path_columns()
            col_refs: Dict[str, List[inv.ColumnRef]] = {}
            for ref in inv.COLUMN_ONLY_REFERENCES:
                col_refs.setdefault(ref.table, []).append(ref)

            # ── pass 2: write records, check every reference, normalise paths ──
            record_counts: Dict[str, int] = {}
            external_person_deps: Dict[str, List[Dict[str, Any]]] = {}
            installation_deps: Dict[str, Set[str]] = {}
            referenced_files: Dict[str, Tuple[str, str, str]] = {}  # rel -> (table, column, id)
            secret_hits: List[Dict[str, Any]] = []

            owned_values: Dict[Tuple[str, str], Set[Any]] = {}

            def _owned_values(parent: str, key: str) -> Set[Any]:
                """Every value of parent.<key> among THIS narrator's parent rows."""
                k = (parent, key)
                if k not in owned_values:
                    if key in pk_cols.get(parent, []) and len(pk_cols[parent]) == 1:
                        owned_values[k] = {t[0] for t in ids[parent]}
                    else:
                        owned_values[k] = {r[0] for r in con.execute(
                            f'SELECT "{parent}"."{key}" FROM "{parent}" WHERE {inv.owner_predicate(parent)}',
                            {"pid": pid})}
                return owned_values[k]

            def _check_ref(table: str, row_id: str, column: str, value: Any,
                           parent: str, parent_key: str, empty_means_none: bool):
                if value is None or (empty_means_none and value == ""):
                    return
                if parent == "people":
                    if str(value) == pid:
                        return
                    if column in external_cols.get(table, ()):
                        external_person_deps.setdefault(table, []).append(
                            {"row_id": row_id, "column": column, "person_id": str(value)})
                        return
                    refuse.add("row_names_another_person", table=table, row_id=row_id,
                               column=column, person_id=str(value),
                               detail="not a declared external_person_column")
                    return
                if parent in installation_set:
                    installation_deps.setdefault(parent, set()).add(str(value))
                    return
                if parent in owned_set:
                    if parent not in ids:
                        refuse.add("unresolved_reference_parent_lane_absent", table=table,
                                   row_id=row_id, column=column, parent=parent)
                        return
                    if value not in _owned_values(parent, parent_key):
                        refuse.add("unresolved_reference", table=table, row_id=row_id, column=column,
                                   parent=parent, parent_key=parent_key, value=str(value),
                                   detail="the package would omit the row this narrator-owned row points at (WO §30)")
                    return
                # parent is neither owned nor installation: undeclared — refuse rather than guess
                refuse.add("reference_to_undeclared_table", table=table, row_id=row_id,
                           column=column, parent=parent)

            for table in owned_tables:
                if table not in ids:
                    continue
                cols = _columns(con, table)
                fks = [(c, p, k) for c, p, k in _fks(con, table)]
                refs = col_refs.get(table, [])
                pcols = path_cols.get(table, ())
                n = 0
                out_path = records_dir / f"{table}.jsonl"
                with out_path.open("w", encoding="utf-8") as fh:
                    sql = inv.select_sql(table) + " ORDER BY " + ", ".join(f'"{table}"."{c}"' for c in pk_cols[table])
                    for row in con.execute(sql, {"pid": pid}):
                        rec = {c: row[c] for c in cols}
                        row_id = "|".join(str(rec.get(c)) for c in pk_cols[table]) if pk_cols[table] != ["rowid"] else str(n)
                        for c, p, k in fks:
                            _check_ref(table, row_id, c, rec.get(c), p, k, True)
                        for ref in refs:
                            _check_ref(table, row_id, ref.column, rec.get(ref.column),
                                       ref.parent_table, ref.parent_key, ref.empty_means_none)
                        # §13: a declared external-person column may name someone else,
                        # FK or not — recorded as a dependency, never pulled.
                        for ec in external_cols.get(table, ()):
                            v = rec.get(ec)
                            if v not in (None, "") and str(v) != pid and ec not in {c for c, _p, _k in fks}:
                                external_person_deps.setdefault(table, []).append(
                                    {"row_id": row_id, "column": ec, "person_id": str(v)})
                        for pc in pcols:
                            raw = rec.get(pc)
                            if raw in (None, ""):
                                continue
                            rel = _normalise_path(str(raw), root)
                            if rel is None:
                                refuse.add("path_outside_data_dir", table=table, row_id=row_id, column=pc, value=str(raw)[:200])
                                continue
                            rec[pc] = rel
                            target = root / rel
                            if not target.exists():
                                refuse.add("referenced_file_missing", table=table, row_id=row_id, column=pc, path=rel,
                                           detail="a narrator-owned row names a file that is not on disk (WO §30)")
                                continue
                            if target.is_file():
                                referenced_files[rel] = (table, pc, row_id)
                        line = json.dumps(rec, ensure_ascii=False, default=str)
                        for name, rx in _SECRET_PATTERNS:
                            if rx.search(line):
                                secret_hits.append({"table": table, "row_id": row_id, "pattern": name})
                                break
                        fh.write(line + "\n")
                        n += 1
                record_counts[table] = n
            for hit in secret_hits:
                refuse.add("credential_shaped_value", **hit)
            refuse.raise_if_any()

            # ── files: lanes, resolved through the snapshot's rows ──
            file_sets: Dict[str, List[Path]] = {}   # lane -> absolute paths (files or dirs)
            residue: List[Dict[str, Any]] = []
            for lane in inv.FS_LANES:
                base = root.joinpath(*lane.parts)
                if lane.keyed_by == "person":
                    d = base / pid
                    if d.is_symlink():
                        refuse.add("symlink_in_lane", lane=lane.name, path=str(d))
                    elif d.is_dir():
                        file_sets[lane.name] = [d]
                elif lane.keyed_by == "row" and lane.portable == "yes" and lane.resolver_sql:
                    if lane.name == "agent_transcripts":
                        if "sessions" in ids:
                            paths = []
                            for r in con.execute(lane.resolver_sql, {"pid": pid}):
                                for sub, fname in export_basenames(str(r[0] or "")):
                                    p = base / sub / fname
                                    if p.is_file():
                                        paths.append(p)
                            if paths:
                                file_sets[lane.name] = paths
                        continue
                    try:
                        rows = con.execute(lane.resolver_sql, {"pid": pid}).fetchall()
                    except sqlite3.Error as exc:
                        if "no such table" in str(exc):
                            continue
                        refuse.add("lane_unqueryable", table=lane.name, error=str(exc))
                        continue
                    paths = []
                    for r in rows:
                        seg = _safe_segment(r[0])
                        if not seg:
                            refuse.add("unsafe_row_id_for_path", lane=lane.name, value=str(r[0])[:64])
                            continue
                        d = base / seg
                        if d.is_dir():
                            paths.append(d)
                    if paths:
                        file_sets[lane.name] = paths
                elif lane.portable == "conditional" and lane.conditional_sql:
                    try:
                        rows = con.execute(lane.conditional_sql, {"pid": pid}).fetchall()
                    except sqlite3.Error as exc:
                        if "no such table" in str(exc):
                            continue
                        refuse.add("lane_unqueryable", table=lane.name, error=str(exc))
                        continue
                    paths = []
                    for r in rows:
                        segs = [_safe_segment(v) for v in r]
                        if not all(segs):
                            refuse.add("unsafe_row_id_for_path", lane=lane.name, value=str(tuple(r))[:64])
                            continue
                        d = base.joinpath(*segs)
                        if d.is_dir():
                            paths.append(d)
                        else:
                            warnings.append({"code": "unresolved_candidate_without_staged_original",
                                             "lane": lane.name, "path": str(d.relative_to(root))})
                    if paths:
                        file_sets[lane.name] = paths
                    # everything else under this narrator's batch dirs is residue
                    if lane.resolver_sql:
                        try:
                            for r in con.execute(lane.resolver_sql, {"pid": pid}):
                                seg = _safe_segment(r[0])
                                if seg and (base / seg).is_dir():
                                    total = sum(f.stat().st_size for f in (base / seg).rglob("*") if f.is_file())
                                    packed = sum(f.stat().st_size for p in paths if p.is_relative_to(base / seg)
                                                 for f in p.rglob("*") if f.is_file())
                                    if total > packed:
                                        residue.append({"lane": lane.name, "path": f"{'/'.join(lane.parts)}/{seg}",
                                                        "bytes_not_packaged": total - packed,
                                                        "why": "resolved or non-pending candidates; erasable, not portable"})
                        except sqlite3.Error:
                            pass
                elif lane.keyed_by == "row" and lane.portable == "no" and lane.resolver_sql:
                    try:
                        for r in con.execute(lane.resolver_sql, {"pid": pid}):
                            seg = _safe_segment(r[0])
                            if seg and (base / seg).is_dir():
                                n_files = sum(1 for f in (base / seg).rglob("*") if f.is_file())
                                residue.append({"lane": lane.name, "path": f"{'/'.join(lane.parts)}/{seg}",
                                                "files_not_packaged": n_files, "why": lane.note[:80]})
                    except sqlite3.Error:
                        pass
                # shared / installation lanes: never the narrator's; nothing to do.
            refuse.raise_if_any()

            # every file a row referenced must fall inside a lane that is being collected
            lane_roots = [p for ps in file_sets.values() for p in ps]
            for rel, (table, col, row_id) in referenced_files.items():
                abs_p = root / rel
                if not any(abs_p == lr or (lr.is_dir() and abs_p.is_relative_to(lr)) for lr in lane_roots):
                    refuse.add("referenced_file_outside_declared_lanes", table=table, row_id=row_id,
                               column=col, path=rel,
                               detail="the row's file is on disk but no declared narrator lane contains it")
            refuse.raise_if_any()

            # ── consistency: measure, copy+hash, re-measure ──
            before = _measure_tree(lane_roots)
            file_counts: Dict[str, int] = {}
            bytes_by_lane: Dict[str, int] = {}
            for lane_name, paths in file_sets.items():
                cnt = 0
                total = 0
                for p in paths:
                    files = [p] if p.is_file() else [f for f in sorted(p.rglob("*")) if f.is_file() and not f.is_symlink()]
                    for f in files:
                        rel = f.relative_to(root)
                        dest = files_dir / rel
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(f, dest)
                        _, n = _sha256_file(dest)
                        cnt += 1
                        total += n
                file_counts[lane_name] = cnt
                bytes_by_lane[lane_name] = total
            if _after_collect_hook:
                _after_collect_hook(root)
            after = _measure_tree(lane_roots)
            if before != after:
                changed = sorted(set(before) ^ set(after)) or sorted(k for k in before if before[k] != after.get(k))
                raise ExportRefused([{"code": "refused_changed_during_snapshot",
                                      "detail": "narrator files changed while the package was being built (§8.3)",
                                      "paths": [str(Path(c).relative_to(root)) for c in changed[:20]]}])

            # ── §6 residue that is installation-wide, reported honestly ──
            if "sessions" in present and "person_id" in _columns(con, "sessions"):
                unowned = con.execute("SELECT COUNT(*) FROM sessions WHERE person_id IS NULL").fetchone()[0]
                if unowned:
                    residue.append({"lane": "sessions", "rows_with_no_owner_on_source": int(unowned),
                                    "why": "§6: never attributed, never swept; not this narrator's by any declaration"})

            manifest = {
                "package_format": PACKAGE_FORMAT,
                "package_format_version": PACKAGE_FORMAT_VERSION,
                "package_id": package_id,
                "package_kind": PACKAGE_KIND,
                "created_at": _now(),
                "narrator_id": pid,
                "narrator_display_name": display_name,
                "source_app": SOURCE_APP,
                "source_commit": _repo_head(repo_root),
                "source_schema_migrations": _applied_migrations(con),
                "source_schema_fingerprint": _schema_fingerprint(con),
                "path_basis": "DATA_DIR-relative",
                "ownership_declaration": "api.services.narrator_data_inventory",
                "record_counts_by_lane": record_counts,
                "file_counts_by_lane": file_counts,
                "bytes_by_lane": bytes_by_lane,
                "lanes_absent_in_source": sorted(lanes_absent),
                "external_person_dependencies": external_person_deps,
                "installation_dependencies": {k: sorted(v) for k, v in installation_deps.items()},
                "residue_not_packaged": residue,
                "warnings": warnings,
            }
        finally:
            con.close()

        # ── bag it (temporary directory ONLY), validate, zip ──
        try:
            import bagit  # type: ignore
        except ImportError as exc:  # pragma: no cover - environment
            raise ExportRefused([{"code": "bagit_not_installed",
                                  "detail": "pin bagit==1.8.1 (requirements-gpu.txt / requirements-test.txt)",
                                  "error": str(exc)}])
        bag = bagit.make_bag(str(staging), checksums=["sha256"], bag_info={
            "Source-Organization": SOURCE_APP,
            "External-Identifier": f"{PACKAGE_FORMAT}:{package_id}",
            "External-Description": f"Lorevox narrator package for narrator {pid}",
            "Bagging-Date": _dt.date.today().isoformat(),
        })
        (staging / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        bag.save(manifests=True)
        bag.validate()

        final_name = f"{_display_slug(display_name)}_{package_id}.lorevox.zip"
        final_path = out_dir / final_name
        if final_path.exists():
            raise ExportRefused([{"code": "package_exists", "path": str(final_path)}])
        tmp_zip = out_dir / (final_name + ".part")
        try:
            with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
                for f in sorted(staging.rglob("*")):
                    if f.is_file():
                        zf.write(f, f.relative_to(staging).as_posix())
            os.replace(tmp_zip, final_path)
        finally:
            if tmp_zip.exists():
                tmp_zip.unlink()
    return ExportResult(package_path=final_path, package_id=package_id, manifest=manifest, warnings=warnings)


def _normalise_path(raw: str, root: Path) -> Optional[str]:
    """DATA_DIR-relative POSIX path, or None if the value points outside DATA_DIR."""
    s = raw.replace("\\", "/")
    p = Path(s)
    if p.is_absolute():
        try:
            rel = p.resolve().relative_to(root)
        except (ValueError, OSError):
            return None
    else:
        rel = Path(s)
        if any(part == ".." for part in rel.parts):
            return None
    return rel.as_posix()


# ── validate a package (the half of Phase 3 the exporter's own tests need) ──

def validate_package(zip_path: Path) -> ValidationReport:
    """BagIt-valid (complete + every checksum verifies) AND manifest-consistent.
    Members are inspected before any byte is extracted (§11); extraction is
    into a temporary directory only."""
    zip_path = Path(zip_path)
    problems: List[str] = []
    manifest = None
    n_files = 0
    n_bytes = 0
    if not zip_path.is_file():
        return ValidationReport(False, zip_path, None, ["package file not found"], 0, 0)
    with tempfile.TemporaryDirectory(prefix="lorevox-validate-") as tmp:
        tmp = Path(tmp)
        seen: Set[str] = set()
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                name = info.filename
                if name.startswith("/") or name.startswith("\\") or ".." in Path(name).parts or ":" in name.split("/")[0]:
                    problems.append(f"unsafe member path: {name}")
                    continue
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    problems.append(f"symlink member refused: {name}")
                    continue
                if name in seen:
                    problems.append(f"duplicate member: {name}")
                    continue
                seen.add(name)
                if name.endswith("/"):
                    continue
                dest = tmp / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, dest.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
        if problems:
            return ValidationReport(False, zip_path, None, problems, 0, 0)
        try:
            import bagit  # type: ignore
            bag = bagit.Bag(str(tmp))
            bag.validate()
        except Exception as exc:
            problems.append(f"bagit validation failed: {exc}")
        mpath = tmp / MANIFEST_NAME
        if not mpath.is_file():
            problems.append(f"{MANIFEST_NAME} missing")
        else:
            try:
                manifest = json.loads(mpath.read_text(encoding="utf-8"))
            except ValueError as exc:
                problems.append(f"{MANIFEST_NAME} unreadable: {exc}")
        if manifest:
            if manifest.get("package_format") != PACKAGE_FORMAT:
                problems.append("unsupported package_format")
            for table, n in (manifest.get("record_counts_by_lane") or {}).items():
                rp = tmp / "data" / "records" / f"{table}.jsonl"
                if not rp.is_file():
                    problems.append(f"records/{table}.jsonl declared, absent")
                    continue
                with rp.open(encoding="utf-8") as fh:
                    lines = sum(1 for _ in fh)
                if lines != n:
                    problems.append(f"records/{table}.jsonl has {lines} rows, manifest says {n}")
            files_root = tmp / "data" / "files"
            actual = [f for f in files_root.rglob("*") if f.is_file()] if files_root.is_dir() else []
            n_files = len(actual)
            n_bytes = sum(f.stat().st_size for f in actual)
            declared = sum((manifest.get("file_counts_by_lane") or {}).values())
            if declared != n_files:
                problems.append(f"manifest declares {declared} payload files, package holds {n_files}")
    return ValidationReport(not problems, zip_path, manifest, problems, n_files, n_bytes)


__all__ = ["export_narrator", "validate_package", "ExportRefused", "ExportResult", "ValidationReport",
           "PACKAGE_FORMAT", "PACKAGE_FORMAT_VERSION", "PACKAGE_KIND", "MANIFEST_NAME"]
