"""Lorevox Narrator Package v1 — WO-LOREVOX-PORTABLE-NARRATOR-01 Phases 2–3.

ONE service (§28.5): export, validate, dry-run, restore. The operator UI and
`scripts/narrator_package.py` both call this; there is never a second
implementation of portability.

RESTORE (§10–§12, Phase 3) has one meaning: restore this narrator AS this
narrator — every id verbatim, nothing overwritten, nothing merged, nothing
remapped. `dry_run_restore()` is mandatory and writes nothing. `restore_narrator()`
follows §12's fifteen steps in order: files first (no-overwrite create, re-hashed),
then the rows in ONE transaction with foreign keys deferred to COMMIT and verified
against the manifest before COMMIT, so a crash can leave a job row and staged
files but never a half-imported narrator. Path columns the source stored absolute
are rewritten under the destination root; the manifest's `path_column_basis` says
which, recorded at export.

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
_SAFE_PACKAGE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{3,63}$")   # enters a filename
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")

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


def _copy_bound(src: Path, dest: Path) -> Tuple[str, int]:
    """Copy `src` to `dest` hashing the SOURCE bytes as they are read, then hash
    the DESTINATION and require equality (§7.4: the final hash must equal the
    hash measured during collection). Returns (sha256, bytes)."""
    h = hashlib.sha256()
    n = 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    with src.open("rb") as fh, dest.open("wb") as out:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
            out.write(chunk)
            n += len(chunk)
    source_digest = h.hexdigest()
    dest_digest, dest_n = _sha256_file(dest)
    if dest_digest != source_digest or dest_n != n:
        raise ExportRefused([{"code": "copy_digest_mismatch", "path": str(src),
                              "detail": "bytes written to the package are not the bytes read from the source"}])
    return source_digest, n


def _lane_files_or_refuse(paths: Iterable[Path], refuse: "_Refusals", lane: str) -> List[Path]:
    """Every regular file under the given lane paths. A symlink ANYWHERE — a
    file, a directory, a path component — is refused, never skipped: the rule
    narrator_erasure.safe_target() established, because a link can leave one
    narrator's lane while staying inside DATA_DIR, and a package that silently
    omits one is not complete."""
    files: List[Path] = []
    for p in paths:
        if p.is_symlink():
            refuse.add("symlink_in_lane", lane=lane, path=str(p))
            continue
        if p.is_file():
            files.append(p)
            continue
        if not p.is_dir():
            continue
        for f in sorted(p.rglob("*")):
            if f.is_symlink():
                refuse.add("symlink_in_lane", lane=lane, path=str(f))
            elif f.is_file():
                files.append(f)
    return files


def _repo_root_default() -> Path:
    """The repository this service runs from: walk up until a `.git` entry is
    found. (`parents[3]` from server/code/api/services/ is `server`, not the
    repo — a fixed index recorded `unknown` for the source commit.)"""
    here = Path(__file__).resolve()
    for cand in [here] + list(here.parents):
        if (cand / ".git").exists():
            return cand
    return here.parents[4] if len(here.parents) > 4 else here.parent


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


def _measure_files(files: Iterable[Path]) -> Dict[str, Tuple[int, int]]:
    """path -> (size, mtime_ns). The independent snapshot-consistency proof
    (§8.3): measured before and after collection; byte binding is separate."""
    out: Dict[str, Tuple[int, int]] = {}
    for f in files:
        try:
            st = f.lstat()
        except FileNotFoundError:
            out[str(f)] = (-1, -1)
            continue
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
    try:
        db_path.resolve().relative_to(root)
    except ValueError:
        raise ExportRefused([{"code": "db_outside_data_dir", "db": str(db_path), "data_dir": str(root),
                              "detail": "a package must not combine one data world's rows with another's files; "
                                        "the database lives under DATA_DIR (db/<DB_NAME>)"}])
    if package_id is not None and not _SAFE_PACKAGE_ID.match(str(package_id)):
        raise ExportRefused([{"code": "unsafe_package_id", "value": str(package_id)[:64]}])
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
    repo_root = Path(repo_root) if repo_root else _repo_root_default()
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
            # §8.5: how the SOURCE stored each declared path column. Restore rewrites
            # an "absolute" column under the destination root; a "relative" column
            # stays relative. A column that mixes both cannot be restored faithfully
            # and refuses here, not on the other machine.
            path_basis_seen: Dict[str, Dict[str, Set[str]]] = {}

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
                            path_basis_seen.setdefault(table, {}).setdefault(pc, set()).add(
                                "absolute" if Path(str(raw).replace("\\", "/")).is_absolute() else "relative")
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
            path_column_basis: Dict[str, Dict[str, str]] = {}
            for table, cols_seen in path_basis_seen.items():
                for pc, kinds in cols_seen.items():
                    if len(kinds) > 1:
                        refuse.add("path_column_mixed_basis", table=table, column=pc,
                                   detail="some rows store this path absolute and some relative; "
                                          "Restore could not rewrite it faithfully (§8.5)")
                    else:
                        path_column_basis.setdefault(table, {})[pc] = next(iter(kinds))
            refuse.raise_if_any()

            # ── files: lanes, resolved through the snapshot's rows ──
            file_sets: Dict[str, List[Path]] = {}   # lane -> absolute paths (files or dirs)
            residue: List[Dict[str, Any]] = []
            expected_file_digests: Dict[str, str] = {}   # source path -> digest a ROW says it must have
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
                        cells = list(r)
                        expected_digest = None
                        if lane.verified_by_digest:
                            expected_digest = cells.pop()      # LAST column: the row's SHA-256
                        segs = [_safe_segment(v) for v in cells]
                        if not all(segs):
                            refuse.add("unsafe_row_id_for_path", lane=lane.name, value=str(tuple(r))[:64])
                            continue
                        d = base.joinpath(*segs)
                        rel_d = "/".join(lane.parts + tuple(segs))
                        if not lane.verified_by_digest:
                            if d.is_dir():
                                paths.append(d)
                            else:
                                warnings.append({"code": "conditional_lane_dir_absent", "lane": lane.name, "path": rel_d})
                            continue
                        # §29.3 — classified MECHANICALLY from the digest, never from a name:
                        digest = str(expected_digest or "").strip().lower()
                        if _SHA256_HEX.match(digest):
                            # a real verified source: it must be there and it must be those bytes
                            if not d.is_dir():
                                refuse.add("verified_source_missing", lane=lane.name, path=rel_d,
                                           expected_sha256=digest,
                                           detail="an unresolved candidate with a valid digest has no staged "
                                                  "original; the package cannot claim a byte source it lost (§29.3)")
                                continue
                            regular = _lane_files_or_refuse([d], refuse, lane.name)
                            if len(regular) != 1:
                                refuse.add("verified_source_ambiguous", lane=lane.name, path=rel_d,
                                           files=[str(f.relative_to(root)) for f in regular][:5],
                                           detail="exactly one regular file must be the verified original")
                                continue
                            actual, _n = _sha256_file(regular[0])
                            if actual != digest:
                                refuse.add("verified_source_hash_mismatch", lane=lane.name,
                                           path=str(regular[0].relative_to(root)),
                                           expected_sha256=digest, actual_sha256=actual)
                                continue
                            expected_file_digests[str(regular[0])] = digest
                            paths.append(d)
                        else:
                            # historical residue: no valid digest to verify against. The ROW
                            # travels (it is in records/); the bytes are not a verified source.
                            warnings.append({"code": "unverifiable_candidate_staging_not_packaged",
                                             "lane": lane.name, "path": rel_d, "stored_digest": digest[:32] or None,
                                             "staged_dir_present": d.is_dir(),
                                             "detail": "candidate has no valid SHA-256; its row is preserved, "
                                                       "its staging is residue"})
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

            # ── enumerate every file the package will carry; a symlink anywhere refuses ──
            lane_files: Dict[str, List[Path]] = {}
            for lane_name, paths in file_sets.items():
                lane_files[lane_name] = _lane_files_or_refuse(paths, refuse, lane_name)
            refuse.raise_if_any()
            all_files = [f for fs in lane_files.values() for f in fs]

            # ── §8.3 snapshot consistency (independent of byte binding): measure before … ──
            before = _measure_files(all_files)

            # ── collect: hash the SOURCE as it is read, hash the copy, require equality (§7.4) ──
            file_counts: Dict[str, int] = {}
            bytes_by_lane: Dict[str, int] = {}
            collected_digests: Dict[str, str] = {}   # DATA_DIR-relative -> sha256 of the source bytes
            for lane_name, files in lane_files.items():
                cnt = 0
                total = 0
                for f in files:
                    rel = f.relative_to(root)
                    digest, n = _copy_bound(f, files_dir / rel)
                    want = expected_file_digests.get(str(f))
                    if want and want != digest:
                        refuse.add("verified_source_hash_mismatch", lane=lane_name, path=rel.as_posix(),
                                   expected_sha256=want, actual_sha256=digest,
                                   detail="bytes read at collection differ from the digest the row declares")
                    collected_digests[rel.as_posix()] = digest
                    cnt += 1
                    total += n
                file_counts[lane_name] = cnt
                bytes_by_lane[lane_name] = total
            refuse.raise_if_any()
            if _after_collect_hook:
                _after_collect_hook(root)
            # … and after
            after = _measure_files(all_files)
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
                "path_column_basis": path_column_basis,
                "payload_integrity": "sha256 of source bytes at collection == sha256 of packaged copy; "
                                     "BagIt manifest-sha256.txt then binds the ZIP to that copy",
                "verified_source_digests_checked": len(expected_file_digests),
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

_MAX_MEMBER_BYTES = 8 * 1024 ** 3        # one payload file larger than 8 GiB is not a narrator's
_BOMB_RATIO = 200                        # uncompressed/compressed above this, on a big member, refuses


def _safe_extract(zip_path: Path, into: Path) -> List[str]:
    """§11: inspect every member BEFORE any byte lands; extract into `into` only.
    Returns the problems found (empty = clean). Never calls extractall()."""
    problems: List[str] = []
    seen: Set[str] = set()
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = info.filename
            parts = Path(name).parts
            if (name.startswith(("/", "\\")) or ".." in parts or (parts and ":" in parts[0])
                    or "\\" in name or any(p in ("", ".") for p in parts[:-1])):
                problems.append(f"unsafe member path: {name}")
                continue
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                problems.append(f"symlink member refused: {name}")
                continue
            key = Path(name).as_posix().lower()     # destination identity, not literal spelling
            if key in seen:
                problems.append(f"duplicate member (same destination): {name}")
                continue
            seen.add(key)
            if name.endswith("/"):
                continue
            if info.file_size > _MAX_MEMBER_BYTES:
                problems.append(f"member too large: {name} ({info.file_size} bytes)")
                continue
            if info.compress_size and info.file_size > 16 * 1024 ** 2 and info.file_size / info.compress_size > _BOMB_RATIO:
                problems.append(f"unsafe expansion ratio: {name}")
                continue
            dest = into / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, dest.open("wb") as dst:
                shutil.copyfileobj(src, dst)
    return problems


def _inspect_bag(tmp: Path) -> Tuple[Optional[Dict[str, Any]], List[str], int, int]:
    """BagIt-validate an extracted package and cross-check the manifest."""
    problems: List[str] = []
    manifest = None
    try:
        import bagit  # type: ignore
        bagit.Bag(str(tmp)).validate()
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
    n_files = n_bytes = 0
    if manifest:
        if manifest.get("package_format") != PACKAGE_FORMAT:
            problems.append("unsupported package_format")
        if str(manifest.get("package_format_version", "")).split(".")[0] != PACKAGE_FORMAT_VERSION.split(".")[0]:
            problems.append(f"unsupported package_format_version {manifest.get('package_format_version')}")
        if manifest.get("package_kind") != PACKAGE_KIND:
            problems.append(f"unsupported package_kind {manifest.get('package_kind')}")
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
    return manifest, problems, n_files, n_bytes


def validate_package(zip_path: Path) -> ValidationReport:
    """BagIt-valid (complete + every checksum verifies) AND manifest-consistent.
    Members are inspected before any byte is extracted (§11); extraction is
    into a temporary directory only."""
    zip_path = Path(zip_path)
    if not zip_path.is_file():
        return ValidationReport(False, zip_path, None, ["package file not found"], 0, 0)
    with tempfile.TemporaryDirectory(prefix="lorevox-validate-") as tmp:
        tmp = Path(tmp)
        problems = _safe_extract(zip_path, tmp)
        if problems:
            return ValidationReport(False, zip_path, None, problems, 0, 0)
        manifest, problems, n_files, n_bytes = _inspect_bag(tmp)
    return ValidationReport(not problems, zip_path, manifest, problems, n_files, n_bytes)


# ══════════════════════════════════════════════════════════════════════
# Phase 3 — dry run and Restore v1 (§10–§12)
# ══════════════════════════════════════════════════════════════════════

@dataclass
class DryRunReport:
    ready: bool
    verdict: str                                  # "RESTORE READY" | "RESTORE REFUSED"
    package_path: Path
    manifest: Optional[Dict[str, Any]]
    reasons: List[Dict[str, Any]]                 # why refused (empty when ready)
    records_by_lane: Dict[str, int]
    files_by_lane: Dict[str, int]
    total_bytes: int
    collisions: List[Dict[str, Any]]
    unsupported_schema: List[Dict[str, Any]]
    missing_dependencies: List[Dict[str, Any]]
    warnings: List[Dict[str, Any]]


@dataclass
class RestoreResult:
    job_id: str
    narrator_id: str
    package_id: str
    records_inserted: Dict[str, int]
    files_created: List[str]
    dry_run: DryRunReport


class RestoreRefused(Exception):
    def __init__(self, report: DryRunReport):
        self.report = report
        super().__init__("RESTORE REFUSED — %d reason(s): %s" % (
            len(report.reasons), "; ".join(r.get("code", "?") for r in report.reasons[:8])))


def _read_records(tmp: Path, table: str) -> Iterable[Dict[str, Any]]:
    rp = tmp / "data" / "records" / f"{table}.jsonl"
    if not rp.is_file():
        return
    with rp.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def _payload_hashes(tmp: Path) -> Dict[str, str]:
    """data/... member -> sha256 from manifest-sha256.txt (what BagIt validated)."""
    out: Dict[str, str] = {}
    mp = tmp / "manifest-sha256.txt"
    if mp.is_file():
        for line in mp.read_text(encoding="utf-8").splitlines():
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                out[parts[1].strip()] = parts[0].strip()
    return out


def _safe_destination(root: Path, rel: str) -> Optional[Path]:
    """DATA_DIR/<rel>, refusing traversal and any symlink component (§11 —
    the narrator-erasure lstat walk is the model)."""
    p = Path(rel)
    if p.is_absolute() or ".." in p.parts or not p.parts:
        return None
    cur = root
    for part in p.parts[:-1]:
        cur = cur / part
        if cur.is_symlink():
            return None
    dest = cur / p.parts[-1]
    if dest.is_symlink():
        return None
    try:
        dest.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    return dest


def _dry_run_on_extracted(tmp: Path, manifest: Dict[str, Any], root: Path, db_path: Path,
                          bag_problems: List[str], zip_path: Path) -> DryRunReport:
    reasons: List[Dict[str, Any]] = [{"code": "package_invalid", "detail": p} for p in bag_problems]
    collisions: List[Dict[str, Any]] = []
    unsupported: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = list(manifest.get("warnings") or [])
    counts = dict(manifest.get("record_counts_by_lane") or {})
    files_by_lane = dict(manifest.get("file_counts_by_lane") or {})
    total_bytes = int(sum((manifest.get("bytes_by_lane") or {}).values()))
    pid = str(manifest.get("narrator_id") or "")
    if not _safe_segment(pid):
        reasons.append({"code": "unsafe_narrator_id", "value": pid[:64]})

    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        present = _tables(con)
        # ── schema compatibility: every packaged table and column must exist here ──
        for table, n in counts.items():
            if table not in present:
                unsupported.append({"table": table, "detail": "table absent in destination schema", "rows": n})
                continue
            if table not in set(inv.narrator_owned_tables()):
                unsupported.append({"table": table, "detail": "not a narrator-owned lane in this installation's declaration"})
                continue
            live = set(_columns(con, table))
            first = next(iter(_read_records(tmp, table)), None)
            if first is not None:
                extra = sorted(set(first) - live)
                if extra:
                    unsupported.append({"table": table, "detail": "package columns absent in destination", "columns": extra})
        # ── collisions (§10.2): narrator id, any packaged id, any destination file ──
        if "people" in present and con.execute("SELECT 1 FROM people WHERE id=?", (pid,)).fetchone():
            collisions.append({"kind": "narrator_exists", "person_id": pid})
        for table in counts:
            if table not in present:
                continue
            pk = _pk_columns(con, table)
            if pk == ["rowid"]:
                continue
            where = " AND ".join(f'"{c}" = ?' for c in pk)
            hits = 0
            sample = None
            for rec in _read_records(tmp, table):
                key = tuple(rec.get(c) for c in pk)
                if con.execute(f'SELECT 1 FROM "{table}" WHERE {where}', key).fetchone():
                    hits += 1
                    sample = sample or key
            if hits:
                collisions.append({"kind": "row_id_exists", "table": table, "rows": hits, "example": [str(k) for k in sample]})
        for member in _payload_hashes(tmp):
            if not member.startswith("data/files/"):
                continue
            rel = member[len("data/files/"):]
            dest = _safe_destination(root, rel)
            if dest is None:
                reasons.append({"code": "unsafe_destination_path", "path": rel})
            elif dest.exists():
                collisions.append({"kind": "file_exists", "path": rel})
        # ── installation dependencies the package cannot carry (§5-E) ──
        for table, ids in (manifest.get("installation_dependencies") or {}).items():
            if table not in present:
                missing.append({"table": table, "ids": ids, "detail": "table absent in destination"})
                continue
            pk = _pk_columns(con, table)[0]
            absent = [i for i in ids if not con.execute(f'SELECT 1 FROM "{table}" WHERE "{pk}" = ?', (i,)).fetchone()]
            if absent:
                missing.append({"table": table, "ids": absent,
                                "detail": "installation-owned rows this narrator references; create them here first"})
        # ── external-person references are recorded, and reported: they will dangle by design (§13) ──
        for table, deps in (manifest.get("external_person_dependencies") or {}).items():
            for d in deps:
                if "people" in present and not con.execute("SELECT 1 FROM people WHERE id=?", (d["person_id"],)).fetchone():
                    warnings.append({"code": "external_person_absent_in_destination", "table": table,
                                     "row_id": d["row_id"], "person_id": d["person_id"],
                                     "detail": "kept as recorded; that person is not part of this package"})
        # ── credential shapes, again, on the receiving side ──
        for table in counts:
            for n, rec in enumerate(_read_records(tmp, table)):
                line = json.dumps(rec, ensure_ascii=False, default=str)
                for name, rx in _SECRET_PATTERNS:
                    if rx.search(line):
                        reasons.append({"code": "credential_shaped_value", "table": table, "row": n, "pattern": name})
                        break
    finally:
        con.close()

    for c in collisions:
        reasons.append({"code": "collision", **c})
    for u in unsupported:
        reasons.append({"code": "unsupported_schema", **u})
    for m in missing:
        reasons.append({"code": "missing_dependency", **m})
    ready = not reasons
    return DryRunReport(ready, "RESTORE READY" if ready else "RESTORE REFUSED", zip_path, manifest, reasons,
                        counts, files_by_lane, total_bytes, collisions, unsupported, missing, warnings)


def dry_run_restore(zip_path: Path, *, data_dir: Path, db_path: Path) -> DryRunReport:
    """§10.4 — mandatory, writes nothing. Everything Restore would check, reported."""
    zip_path = Path(zip_path)
    root = validate_root(data_dir)
    db_path = Path(db_path)
    if not zip_path.is_file():
        return DryRunReport(False, "RESTORE REFUSED", zip_path, None, [{"code": "package_not_found"}], {}, {}, 0, [], [], [], [])
    if not db_path.is_file():
        return DryRunReport(False, "RESTORE REFUSED", zip_path, None, [{"code": "db_not_found", "path": str(db_path)}], {}, {}, 0, [], [], [], [])
    with tempfile.TemporaryDirectory(prefix="lorevox-dryrun-") as tmp:
        tmp = Path(tmp)
        problems = _safe_extract(zip_path, tmp)
        if problems:
            return DryRunReport(False, "RESTORE REFUSED", zip_path, None,
                                [{"code": "package_invalid", "detail": p} for p in problems], {}, {}, 0, [], [], [], [])
        manifest, bag_problems, _n, _b = _inspect_bag(tmp)
        if manifest is None:
            return DryRunReport(False, "RESTORE REFUSED", zip_path, None,
                                [{"code": "package_invalid", "detail": p} for p in bag_problems], {}, {}, 0, [], [], [], [])
        return _dry_run_on_extracted(tmp, manifest, root, db_path, bag_problems, zip_path)


def _job_write(db_path: Path, job: Dict[str, Any]) -> None:
    """The durable job row, in its OWN connection and committed at once (§12 step 7)."""
    con = sqlite3.connect(str(db_path))
    try:
        con.execute("PRAGMA foreign_keys=ON")
        job = dict(job, updated_at=_now())
        cols = ", ".join(f'"{k}"' for k in job)
        con.execute(
            f'INSERT INTO narrator_package_jobs ({cols}) VALUES ({", ".join("?" for _ in job)}) '
            f'ON CONFLICT(id) DO UPDATE SET ' + ", ".join(f'"{k}"=excluded."{k}"' for k in job if k != "id"),
            tuple(job.values()))
        con.commit()
    finally:
        con.close()


def restore_narrator(zip_path: Path, *, data_dir: Path, db_path: Path, requested_by: str = "",
                     _crash_seam=None) -> RestoreResult:
    """§12, exactly in that order. Files first, database visibility last; one
    transaction; ids preserved verbatim (§10.1); nothing overwritten (§10.2).
    Raises RestoreRefused (nothing written) or RuntimeError after cleanup.

    THE JOB ROW IS CRASH-TRUTHFUL. Before the first destination file is created
    the job durably names every file it intends to create; `db_committed` is
    written INSIDE the narrator transaction so it and the rows become visible
    together or not at all; `complete` follows in its own write. So after a
    process death at any point, `recover_restore_jobs()` can decide from the
    job row alone what may exist and whether the narrator was published.

    `_crash_seam(point)` is a test-only hook: it is called at 'after_first_file'
    and 'after_commit' and may raise a BaseException to simulate process death
    — nothing in this function catches BaseException, exactly as a real crash
    would not be caught.
    """
    zip_path = Path(zip_path)
    root = validate_root(data_dir)
    db_path = Path(db_path)
    seam = _crash_seam or (lambda _point: None)
    with tempfile.TemporaryDirectory(prefix="lorevox-restore-") as tmp:
        tmp = Path(tmp)
        # 1–4: stage, validate structure / manifest / hashes
        problems = _safe_extract(zip_path, tmp)
        if problems:
            raise RestoreRefused(DryRunReport(False, "RESTORE REFUSED", zip_path, None,
                                              [{"code": "package_invalid", "detail": p} for p in problems], {}, {}, 0, [], [], [], []))
        manifest, bag_problems, _n, _b = _inspect_bag(tmp)
        if manifest is None:
            raise RestoreRefused(DryRunReport(False, "RESTORE REFUSED", zip_path, None,
                                              [{"code": "package_invalid", "detail": p} for p in bag_problems], {}, {}, 0, [], [], [], []))
        # 5–6: compatibility, ownership, collisions
        report = _dry_run_on_extracted(tmp, manifest, root, db_path, bag_problems, zip_path)
        if not report.ready:
            raise RestoreRefused(report)
        pid = str(manifest["narrator_id"])
        hashes = _payload_hashes(tmp)
        file_members = sorted(m for m in hashes if m.startswith("data/files/"))

        # 7: durable job, committed before the first byte lands. It carries the
        # package's own payload manifest for this narrator (relative path -> expected
        # SHA-256, 0055) so recovery can attribute and verify every file WITHOUT the
        # package; `files_json` (0054) stays what 0054 says — files CREATED — and grows
        # one entry per file as each lands.
        planned: Dict[str, str] = {}
        for member in file_members:
            rel = member[len("data/files/"):]
            if _safe_destination(root, rel) is None:
                raise RestoreRefused(DryRunReport(False, "RESTORE REFUSED", zip_path, manifest,
                                                  [{"code": "unsafe_destination_path", "path": rel}], {}, {}, 0, [], [], [], []))
            planned[rel] = hashes[member]
        job_id = uuid.uuid4().hex
        job = {"id": job_id, "kind": "restore", "state": "validated", "package_id": str(manifest["package_id"]),
               "package_path": str(zip_path), "narrator_id": pid, "data_root": str(root),
               "source_commit": str(manifest.get("source_commit") or ""), "files_json": "[]",
               "file_manifest_json": json.dumps(planned, sort_keys=True),
               "counts_json": "{}", "error": None, "requested_by": requested_by, "created_at": _now()}
        _job_write(db_path, job)

        created: List[Path] = []
        created_dirs: List[Path] = []

        def _cleanup_files() -> List[str]:
            left: List[str] = []
            for f in reversed(created):
                try:
                    f.unlink()
                except OSError:
                    left.append(str(f.relative_to(root)))
            for d in reversed(created_dirs):
                try:
                    d.rmdir()
                except OSError:
                    pass
            return left

        def _fail(stage: str, exc: Exception):
            left = _cleanup_files()
            job.update(state="cleanup_required" if left else "failed",
                       error=f"{stage}: {exc.__class__.__name__}: {exc}"[:2000],
                       files_json=json.dumps(left))
            _job_write(db_path, job)
            raise RuntimeError(f"RESTORE FAILED at {stage}; job {job_id} is {job['state']}: {exc}") from exc

        # 8–9: copy files, no overwrite, re-hash; journal each created file durably
        journal = sqlite3.connect(str(db_path))
        try:
            for member in file_members:
                rel = member[len("data/files/"):]
                dest = _safe_destination(root, rel)
                if dest is None:
                    raise ValueError(f"unsafe destination {rel}")
                # record every directory we create so a failed job removes only its own
                need = []
                cur = dest.parent
                while not cur.exists():
                    need.append(cur)
                    cur = cur.parent
                for d in reversed(need):
                    d.mkdir()
                    created_dirs.append(d)
                fd = os.open(str(dest), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)   # refuses to overwrite
                with os.fdopen(fd, "wb") as dst, (tmp / member).open("rb") as src:
                    shutil.copyfileobj(src, dst)
                created.append(dest)
                digest, _ = _sha256_file(dest)
                if digest != hashes[member]:
                    raise ValueError(f"re-hash mismatch after copy: {rel}")
                journal.execute("UPDATE narrator_package_jobs SET files_json=?, updated_at=? WHERE id=?",
                                (json.dumps([str(p.relative_to(root)) for p in created]), _now(), job_id))
                journal.commit()
                if len(created) == 1:
                    seam("after_first_file")
            job.update(state="files_copied", files_json=json.dumps([str(p.relative_to(root)) for p in created]))
            _job_write(db_path, job)
        except Exception as exc:  # noqa: BLE001
            journal.close()
            _fail("files", exc)
        finally:
            try:
                journal.close()
            except Exception:
                pass

        # 10–13: one transaction, ids verbatim, paths rewritten per the recorded basis
        basis = manifest.get("path_column_basis") or {}
        inserted: Dict[str, int] = {}
        con = sqlite3.connect(str(db_path), isolation_level=None)
        try:
            con.execute("PRAGMA foreign_keys=ON")
            con.execute("BEGIN IMMEDIATE")
            con.execute("PRAGMA defer_foreign_keys=ON")   # order-independent; violations fail at COMMIT
            try:
                for table in inv.narrator_owned_tables():          # declaration order: parents first
                    n = 0
                    for rec in _read_records(tmp, table):
                        for col, kind in (basis.get(table) or {}).items():
                            v = rec.get(col)
                            if v not in (None, "") and kind == "absolute":
                                rec[col] = str(root / v)
                        cols = ", ".join(f'"{c}"' for c in rec)
                        con.execute(f'INSERT INTO "{table}" ({cols}) VALUES ({", ".join("?" for _ in rec)})',
                                    tuple(rec.values()))
                        n += 1
                    if n:
                        inserted[table] = n
                # 12: verify counts and references before anything becomes visible
                expected = {t: n for t, n in (manifest.get("record_counts_by_lane") or {}).items() if n}
                if inserted != expected:
                    raise ValueError(f"inserted counts {inserted} != manifest {expected}")
                bad = []
                for table in inserted:      # only the tables this job wrote; pre-existing damage is not ours to judge
                    bad += con.execute(f'PRAGMA foreign_key_check("{table}")').fetchall()
                if bad:
                    raise ValueError(f"foreign_key_check: {[tuple(r) for r in bad[:10]]}")
                # `db_committed` travels in THE SAME transaction as the rows: COMMIT publishes
                # both or neither, so no crash can leave visible rows with a job that says less.
                con.execute("UPDATE narrator_package_jobs SET state='db_committed', counts_json=?, updated_at=? WHERE id=?",
                            (json.dumps(inserted), _now(), job_id))
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
        except Exception as exc:  # noqa: BLE001
            con.close()
            _fail("database", exc)
        finally:
            try:
                con.close()
            except Exception:
                pass
        seam("after_commit")
        # 14: complete — its own write; a death before it leaves `db_committed`, which recovery finishes
        job.update(state="db_committed", counts_json=json.dumps(inserted))
        job.update(state="complete")
        _job_write(db_path, job)
    # 15: staging removed by the context manager
    return RestoreResult(job_id=job_id, narrator_id=pid, package_id=str(manifest["package_id"]),
                         records_inserted=inserted, files_created=[str(p.relative_to(root)) for p in created],
                         dry_run=report)


# ── crash recovery for restore jobs ─────────────────────────────────────

def _job_set(con: sqlite3.Connection, job_id: str, **fields) -> None:
    fields["updated_at"] = _now()
    con.execute("UPDATE narrator_package_jobs SET " + ", ".join(f'"{k}"=?' for k in fields) + " WHERE id=?",
                (*fields.values(), job_id))
    con.commit()


def recover_restore_jobs(*, data_dir: Path, db_path: Path, job_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Finish or undo restore jobs a process death left behind. Decides from the
    DURABLE job row, whose states are truthful by construction:

      staged / validated / files_copied   the narrator transaction cannot have
                                          committed (db_committed is written inside
                                          it). Remove only the files this job named,
                                          each through the safe-destination walk;
                                          `failed` when clean, `cleanup_required`
                                          naming what is left.
      db_committed                        the rows ARE published. NEVER delete.
                                          Verify rows/counts and every recorded file
                                          (hash against the package if it is still
                                          there); advance to `complete`, or leave
                                          `db_committed` with error='recovery_required'
                                          and refuse automatic destruction.
      cleanup_required                    retry only the recorded set.
      complete / failed                   idempotent no-op, reported.

    Defensive check on top of the invariant: if a job below db_committed finds
    the narrator's people row present, it does NOT touch the files — that is a
    contradiction to report, not a state to repair by deleting.

    FILES ARE NEVER JUDGED BY PATHNAME. The job's `file_manifest_json` (0055) is
    the package's payload manifest for this narrator, written before the first
    byte. Below db_committed a file is removed only when its bytes hash to the
    digest the job planned for that path; anything else at a planned path is
    left and named. At db_committed every planned file is verified against
    that same map — the package ZIP is not needed and is not consulted.
    """
    root = validate_root(data_dir)
    db_path = Path(db_path)
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    out: List[Dict[str, Any]] = []
    try:
        if "narrator_package_jobs" not in _tables(con):
            return out
        rows = con.execute("SELECT * FROM narrator_package_jobs WHERE kind='restore'" +
                           (" AND id=?" if job_id else "") + " ORDER BY created_at", (job_id,) if job_id else ()).fetchall()
        for row in rows:
            jid, state, pid = row["id"], row["state"], row["narrator_id"]
            rep: Dict[str, Any] = {"job_id": jid, "narrator_id": pid, "state_before": state}
            created_list = json.loads(row["files_json"] or "[]")
            planned: Dict[str, str] = json.loads(row["file_manifest_json"] or "{}") if "file_manifest_json" in row.keys() else {}
            # every path this job may have touched: what it journaled as created, and what it planned
            candidates = sorted(set(created_list) | set(planned))
            if str(row["data_root"]) != str(root):
                rep.update(action="skipped", detail=f"job belongs to root {row['data_root']}, not {root}")
                out.append(rep)
                continue
            if state in ("complete", "failed"):
                rep.update(action="none", state_after=state)
                out.append(rep)
                continue
            narrator_present = con.execute("SELECT 1 FROM people WHERE id=?", (pid,)).fetchone() is not None

            if state in ("staged", "validated", "files_copied", "cleanup_required"):
                if narrator_present:
                    # ALL four pre-commit states, cleanup_required included: a later successful
                    # restore of the same package publishes the narrator with files whose bytes
                    # hash-match THIS job's manifest — deleting them would gut a live narrator.
                    _job_set(con, jid, error=f"recovery_required: state {state} but people row {pid} exists; "
                                             f"refusing to delete files under a published narrator")
                    rep.update(action="refused", state_after=state, detail="narrator present below db_committed")
                    out.append(rep)
                    continue
                left: List[Dict[str, str]] = []
                removed: List[str] = []
                for rel in candidates:
                    dest = _safe_destination(root, rel)
                    if dest is None:
                        left.append({"path": rel, "why": "unsafe path"})
                        continue
                    if not dest.exists():
                        continue                                  # planned, never created: nothing to remove
                    if dest.is_symlink() or not dest.is_file():
                        left.append({"path": rel, "why": "not a regular file"})
                        continue
                    expected = planned.get(rel)
                    actual, _n = _sha256_file(dest)
                    if expected is None or actual != expected:
                        # bytes at a planned path that are NOT the package's bytes: not ours to delete
                        left.append({"path": rel, "why": "bytes do not match the job's payload manifest",
                                     "expected_sha256": expected, "actual_sha256": actual})
                        continue
                    try:
                        dest.unlink()
                        removed.append(rel)
                    except OSError as exc:
                        left.append({"path": rel, "why": f"unlink failed: {exc.__class__.__name__}"})
                        continue
                    # prune directories the copy created, innermost first, only while empty
                    cur = dest.parent
                    while cur != root and cur.is_dir():
                        try:
                            cur.rmdir()
                        except OSError:
                            break
                        cur = cur.parent
                new_state = "cleanup_required" if left else "failed"
                _job_set(con, jid, state=new_state, files_json=json.dumps([l["path"] for l in left]),
                         error=(row["error"] or "") + f" | recovered {_now()}: interrupted at {state}, "
                                                      f"removed {len(removed)} matching file(s), left {len(left)}"
                               + ("; " + "; ".join(f"{l['path']}: {l['why']}" for l in left)[:1200] if left else ""))
                rep.update(action="cleaned", state_after=new_state, removed=removed, left=left)
                out.append(rep)
                continue

            # db_committed: publish is done; finish, never destroy
            problems: List[str] = []
            if not narrator_present:
                problems.append("people row absent although db_committed")
            counts = json.loads(row["counts_json"] or "{}")
            for table, n in counts.items():
                if table not in inv.narrator_owned_tables() or table not in _tables(con):
                    problems.append(f"{table}: not a narrator lane here")
                    continue
                got = con.execute(f'SELECT COUNT(*) FROM "{table}" WHERE {inv.owner_predicate(table)}', {"pid": pid}).fetchone()[0]
                if got != n:
                    problems.append(f"{table}: {got} rows, job recorded {n}")
            # every planned file, verified against the job's OWN manifest — no package needed
            if not planned and created_list:
                problems.append("job carries no payload manifest (pre-0055 job); cannot verify files without the package")
            for rel, expected in sorted(planned.items()):
                dest = _safe_destination(root, rel)
                if dest is None or not dest.is_file():
                    problems.append(f"file missing: {rel}")
                    continue
                if _sha256_file(dest)[0] != expected:
                    problems.append(f"file hash differs from the job's manifest: {rel}")
            if problems:
                _job_set(con, jid, error="recovery_required: " + "; ".join(problems)[:1900])
                rep.update(action="refused", state_after="db_committed", problems=problems)
            else:
                _job_set(con, jid, state="complete", files_json=json.dumps(sorted(planned)),
                         error=(row["error"] or "") + f" | recovered {_now()}: verified after interrupted completion")
                rep.update(action="completed", state_after="complete", verified_files=len(planned),
                           hashes_checked=len(planned))
            out.append(rep)
    finally:
        con.close()
    return out


# ══════════════════════════════════════════════════════════════════════
# Phase 4 — semantic equivalence of two packages (§28.4)
# ══════════════════════════════════════════════════════════════════════

@dataclass
class ComparisonReport:
    equivalent: bool
    a: Path
    b: Path
    differences: List[Dict[str, Any]]      # each names WHAT differs and where; empty when equivalent
    informational: List[Dict[str, Any]]    # differences §28.4 treats as non-semantic (recorded, not judged)
    compared: Dict[str, int]               # how much was compared: tables, rows, files


# Manifest fields compared for equality. Everything else in the manifest is either
# identity-of-this-export (package_id, created_at), source-machine provenance
# (source_commit, migrations, fingerprint — informational), or source-only residue
# and warnings that a restore deliberately does not carry.
_MANIFEST_SEMANTIC = ("narrator_id", "narrator_display_name", "package_kind", "path_basis",
                      "record_counts_by_lane", "file_counts_by_lane", "bytes_by_lane",
                      "path_column_basis", "installation_dependencies", "external_person_dependencies")
_MANIFEST_INFORMATIONAL = ("source_commit", "source_schema_migrations", "source_schema_fingerprint",
                           "source_app", "package_format_version", "lanes_absent_in_source",
                           "verified_source_digests_checked")
_MANIFEST_IGNORED = ("package_id", "created_at", "residue_not_packaged", "warnings", "payload_integrity",
                     "ownership_declaration", "package_format")


def _canonical_rows(tmp: Path, table: str) -> Dict[str, str]:
    """row identity -> canonical JSON of the whole row (sorted keys), independent of
    JSONL order. THE CONTRACT, exactly:

      rows WITH `id`     compared by that stable id; a changed row is reported as
                         `row_differs` with the changed columns named.
      rows WITHOUT `id`  the whole canonical row is the identity (the comparator has
                         no schema and does not know which other column is a key), and
                         identical rows keep their MULTIPLICITY through an occurrence
                         index. So an id-less row that CHANGED cannot be paired with
                         its old version: it is reported as `row_only_in_a` plus
                         `row_only_in_b` — inequality is detected, columns are not
                         named. A duplicate present twice in one package and once in
                         the other is one extra `row_only_in_…`.
    """
    out: Dict[str, str] = {}
    seen: Dict[str, int] = {}
    for rec in _read_records(tmp, table):
        canon = json.dumps(rec, sort_keys=True, ensure_ascii=False, default=str)
        if rec.get("id") is not None:
            key = f"id:{rec['id']}"
        else:
            n = seen.get(canon, 0)
            seen[canon] = n + 1
            key = f"row:{canon}" if n == 0 else f"row#{n}:{canon}"
        out[key] = canon
    return out


def compare_packages_semantically(a: Path, b: Path) -> ComparisonReport:
    """§28.4: two packages of the same narrator are equivalent when their narrator
    records agree by stable id, every payload file's SHA-256 agrees, counts by lane
    agree, and dependency/provenance declarations agree — never when their outer
    bytes do. Both packages are extracted through the same §11 inspection as a
    restore; an invalid package is a difference, not an exception."""
    a, b = Path(a), Path(b)
    diffs: List[Dict[str, Any]] = []
    info: List[Dict[str, Any]] = []
    compared = {"tables": 0, "rows": 0, "files": 0}
    with tempfile.TemporaryDirectory(prefix="lorevox-cmp-a-") as ta, tempfile.TemporaryDirectory(prefix="lorevox-cmp-b-") as tb:
        ta, tb = Path(ta), Path(tb)
        for label, zp, t in (("A", a, ta), ("B", b, tb)):
            try:
                problems = _safe_extract(zp, t) if zp.is_file() else ["package file not found"]
            except zipfile.BadZipFile as exc:
                problems = [f"not a ZIP: {exc}"]
            if not problems:
                m, problems, _n, _b = _inspect_bag(t)
                if m is None:
                    problems.append("manifest unreadable")
            for p in problems:
                diffs.append({"kind": "package_invalid", "package": label, "detail": p})
        if diffs:
            return ComparisonReport(False, a, b, diffs, info, compared)
        ma = json.loads((ta / MANIFEST_NAME).read_text(encoding="utf-8"))
        mb = json.loads((tb / MANIFEST_NAME).read_text(encoding="utf-8"))

        for key in _MANIFEST_SEMANTIC:
            if ma.get(key) != mb.get(key):
                diffs.append({"kind": "manifest", "field": key, "a": ma.get(key), "b": mb.get(key)})
        for key in _MANIFEST_INFORMATIONAL:
            if ma.get(key) != mb.get(key):
                info.append({"kind": "manifest", "field": key, "a": ma.get(key), "b": mb.get(key)})

        # records: every table either side names, compared as sets of canonical rows by id
        tables = sorted(set(ma.get("record_counts_by_lane") or {}) | set(mb.get("record_counts_by_lane") or {}))
        for table in tables:
            ra, rb = _canonical_rows(ta, table), _canonical_rows(tb, table)
            compared["tables"] += 1
            compared["rows"] += max(len(ra), len(rb))
            def _shown(key: str) -> str:      # 'id:<pk>' -> '<pk>'; whole-row keys shown as the row
                return key.split(":", 1)[1]
            for rid in sorted(set(ra) - set(rb)):
                diffs.append({"kind": "row_only_in_a", "table": table, "id": _shown(rid)})
            for rid in sorted(set(rb) - set(ra)):
                diffs.append({"kind": "row_only_in_b", "table": table, "id": _shown(rid)})
            for rid in sorted(set(ra) & set(rb)):
                if ra[rid] != rb[rid]:
                    da, db_ = json.loads(ra[rid]), json.loads(rb[rid])
                    cols = sorted(c for c in set(da) | set(db_) if da.get(c) != db_.get(c))
                    diffs.append({"kind": "row_differs", "table": table, "id": _shown(rid), "columns": cols,
                                  "a": {c: da.get(c) for c in cols}, "b": {c: db_.get(c) for c in cols}})

        # payload files: data/files/<rel> -> sha256, from the manifests BagIt just validated
        ha = {m[len("data/files/"):]: h for m, h in _payload_hashes(ta).items() if m.startswith("data/files/")}
        hb = {m[len("data/files/"):]: h for m, h in _payload_hashes(tb).items() if m.startswith("data/files/")}
        compared["files"] = max(len(ha), len(hb))
        for rel in sorted(set(ha) - set(hb)):
            diffs.append({"kind": "file_only_in_a", "path": rel})
        for rel in sorted(set(hb) - set(ha)):
            diffs.append({"kind": "file_only_in_b", "path": rel})
        for rel in sorted(set(ha) & set(hb)):
            if ha[rel] != hb[rel]:
                diffs.append({"kind": "file_hash_differs", "path": rel, "a": ha[rel], "b": hb[rel]})
    return ComparisonReport(not diffs, a, b, diffs, info, compared)


__all__ = ["export_narrator", "validate_package", "dry_run_restore", "restore_narrator", "recover_restore_jobs",
           "compare_packages_semantically", "ComparisonReport",
           "ExportRefused", "ExportResult", "ValidationReport", "DryRunReport", "RestoreResult", "RestoreRefused",
           "PACKAGE_FORMAT", "PACKAGE_FORMAT_VERSION", "PACKAGE_KIND", "MANIFEST_NAME"]
