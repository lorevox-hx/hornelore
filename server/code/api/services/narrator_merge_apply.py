"""Multi-Origin Merge/Remap — THE EXECUTOR. The only module in this lane that writes.

WO-LOREVOX-MULTI-ORIGIN-MERGE-REMAP-01, implementation block 2.

`narrator_merge` decides what a merged root WOULD contain and cannot write; this module
takes that plan and applies it. **They are deliberately separate files.** The planner's
"no writer exists in this module" is a property a reviewer can check by reading it, and
folding a `sqlite3.connect(...).execute("INSERT ...")` into it would quietly destroy that
— `tests/test_narrator_merge_apply.py` pins the separation with a source guard.

━━━ THE TARGET IS INITIALISED BY THE PRODUCT, NEVER BY THIS MODULE ━━━
Decided 2026-09-14. The canonical sequence is:

    product creates a fresh DATA_DIR  ->  normal migrations / init_db() / seed state
    ->  Merge/Remap verifies that root READ-ONLY  ->  only then does it populate it

This is a hard precondition, not a convenience, and Phase 5a is why. A never-used clean
installation refused every narrator with a questionnaire because dry-run matched
installation dependencies on `bio_fields`' primary key instead of the column the rows
actually reference, and a clean root had no `chat_ws` interview plan until somebody had
chatted. Both were fixed in ordinary product initialisation. **A merge that built its own
schema or seeded its own dependencies would be re-deciding what a clean Lorevox
installation is** — the one definition Phase 7 also depends on. So this module never
creates, migrates, seeds or repairs a target: it looks, and it refuses.

Readiness is answered by the product's OWN `dry_run_restore` against the target, per
source package, plus the merge-specific checks below. That keeps "clean installation"
one definition rather than two that will disagree.

━━━ V1 REFUSES. THE REFUSAL IS THE RESULT. ━━━━━━━━━━━━━━━━━━━━━━━━━━━
A plan carrying any unresolved conflict is not executed, and **that is a successful V1
outcome rather than a failure**. The first real Christopher rehearsal is expected to
prove everything up to the conflict boundary — package validity, deterministic remap,
the complete reference rewrite, zero dangling references, the safe union, file
classification, target readiness — and then stop with 4 keyed row conflicts plus the
`rolling_summary.json` divergence, having written nothing. `index.json` is regenerated
and is not a conflict; `rolling_summary.json` is pruned LLM memory where neither side is
a superset, so V1 refuses it.

**No automatic resolution belongs here, now or later.** The refusal report is shaped so
an explicit, auditable human adjudication artifact can be bound to it *without changing
this engine* — each conflict is addressable, both origins' provenance is preserved, and
the report names the exact package ids and sha256s the decisions would apply to, so an
adjudication cannot be replayed against different source data. Building that artifact is
separate work.

━━━ CRASH TRUTHFULNESS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The shape is Phase 3's, reused rather than reinvented (`narrator_package.restore_narrator`,
WO §33/§33.1): a durable job row that names every file it intends to create BEFORE the
first byte lands, files first with `O_EXCL` so nothing is ever overwritten, each created
file journalled as it lands, one `BEGIN IMMEDIATE` with `defer_foreign_keys`, and
`db_committed` written INSIDE that transaction so rows and job state become visible
together or not at all. A failure at any point removes only the files this job created.

**THE LEDGER IS 0057, NOT 0054.** The first draft wrote merge jobs into
`narrator_package_jobs` with `kind='merge'` and its `CHECK (kind IN ('restore'))` refused
the very first write — correctly. 0054's contract is *one package arrived*; a merge is two
immutable packages plus one deterministic plan, and its singular `package_id` /
`package_path` columns cannot say that without lying about their own names. So the Phase 3
durability SHAPE is reused and the Phase 3 TABLE is not: `narrator_merge_jobs` (0057) pins
both sources by id AND full sha256, the plan by fingerprint, and the intended file manifest
by path → expected sha256 before the first byte. `recover_merge_jobs` is the merge's own
equivalent of `recover_restore_jobs`; restore's ledger and recovery semantics are untouched.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import narrator_data_inventory as inv
from . import narrator_merge as merge
from . import narrator_package as pkg
from .narrator_erasure import validate_root

#: Provenance columns the planner attaches. They are evidence, not schema, and must be
#: stripped before a row reaches a column.
PROVENANCE_KEYS = ("_origin", "_origin_package")

ARCHIVE_INDEX_NAME = "index.json"

# ── refusal reason codes ──────────────────────────────────────────────
R_PLAN_UNRESOLVED = "plan_has_unresolved_conflicts"
R_TARGET_IS_A_SOURCE = "target_root_is_a_source_or_live_root"
R_TARGET_DB_MISSING = "target_database_not_initialised"
R_TARGET_SCHEMA_STALE = "target_schema_not_current"
R_TARGET_NARRATOR_PRESENT = "target_already_holds_this_narrator"
R_TARGET_PAYLOAD_PRESENT = "target_already_holds_narrator_owned_files"
R_TARGET_NOT_READY = "target_not_ready_for_a_source_package"
R_SOURCE_CHANGED = "source_package_changed_since_the_plan"
R_TARGET_CHANGED = "target_changed_since_the_binding"
R_UNSAFE_DESTINATION = "unsafe_destination_path"
#: A physical id already in the TARGET, in a table whose closure is not established.
R_UNKNOWN_COLLISION_CLOSURE = merge.R_UNKNOWN_COLLISION_CLOSURE


class MergeApplyRefused(Exception):
    """A refusal is a result: it names the reason, and nothing was written."""

    def __init__(self, code: str, detail: str = "", report: Any = None) -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail
        self.report = report


@dataclass
class TargetReport:
    ready: bool
    root: Path
    db_path: Path
    reasons: List[Dict[str, str]] = field(default_factory=list)
    checks: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MergeApplyResult:
    job_id: str
    narrator_id: str
    records_inserted: Dict[str, int]
    files_created: List[str]
    index_files_regenerated: List[str]
    target: TargetReport


# ══════════════════════════════════════════════════════════════════════
# Target readiness — READ ONLY. Never creates, migrates, seeds or repairs.
# ══════════════════════════════════════════════════════════════════════

def _manifest_of(zip_path: Path) -> Dict[str, Any]:
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            if name.endswith(merge.MANIFEST_NAME):
                return json.loads(zf.read(name).decode("utf-8"))
    return {}


def plan_fingerprint(plan: merge.MergePlan) -> str:
    """Same inputs, same decision, same fingerprint.

    Binds a durable job — and any later human adjudication of the conflicts a refused
    merge reported — to the exact decision it was made against. It covers the inputs and
    every output that decides what gets written: the remap, the union, and the counts.
    """
    payload = {
        "narrator_id": plan.narrator_id,
        "origins": [{"package_id": o["package_id"], "sha256": o["sha256"]}
                    for o in plan.origins],
        "remap": {p: {label: {str(k): str(v) for k, v in m.items()}
                      for label, m in per.items()}
                  for p, per in sorted(plan.remap.items())},
        "files": sorted((e["path"], e["sha256"], e["origin"]) for e in plan.files_union),
        "regenerate": sorted(plan.files_regenerate),
        "counts": dict(sorted(plan.carried_rows.items())),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


# ── the merge ledger (0057). NOT narrator_package_jobs, which is a restore
# ── ledger by contract and refuses any other kind at the CHECK constraint.

#: MUST match 0057's columns exactly. `_merge_job_write` inserts only the keys listed
#: here, so a column missing from this tuple is silently DROPPED rather than refused —
#: which is exactly what happened to `target_basis` on 2026-09-14: the executor computed
#: the basis fingerprint, passed it to the writer, and the writer quietly discarded it.
#: `test_the_ledger_writer_covers_every_column_of_0057` pins the two together.
_MERGE_JOB_COLUMNS = (
    "id", "state", "narrator_id", "target_root",
    "source_a_package_id", "source_a_sha256", "source_a_path",
    "source_b_package_id", "source_b_sha256", "source_b_path",
    "plan_fingerprint", "target_basis", "file_manifest_json", "files_json",
    "expected_counts_json", "counts_json", "error", "recovery",
    "requested_by", "created_at", "updated_at",
)


def _merge_job_write(db_path: Path, job: Dict[str, Any]) -> None:
    """Upsert the job in its OWN connection, committed immediately — the row has to be
    durable before the first byte lands or it cannot make that byte recoverable."""
    job["updated_at"] = pkg._now()
    cols = [c for c in _MERGE_JOB_COLUMNS if c in job]
    con = sqlite3.connect(str(db_path))
    try:
        con.execute(
            f'INSERT INTO narrator_merge_jobs ({", ".join(cols)}) '
            f'VALUES ({", ".join("?" for _ in cols)}) '
            f'ON CONFLICT(id) DO UPDATE SET '
            + ", ".join(f'"{c}"=excluded."{c}"' for c in cols if c != "id"),
            tuple(job[c] for c in cols))
        con.commit()
    finally:
        con.close()


def _merge_job_rows(db_path: Path, job_id: Optional[str] = None) -> List[Dict[str, Any]]:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        sql = "SELECT * FROM narrator_merge_jobs"
        args: Tuple[Any, ...] = ()
        if job_id:
            sql += " WHERE id=?"
            args = (job_id,)
        return [dict(r) for r in con.execute(sql, args).fetchall()]
    finally:
        con.close()


def _applied_migrations(con: sqlite3.Connection) -> List[str]:
    try:
        return [r[0] for r in con.execute("SELECT filename FROM schema_migrations").fetchall()]
    except sqlite3.Error:
        try:
            return [r[0] for r in con.execute("SELECT name FROM schema_migrations").fetchall()]
        except sqlite3.Error:
            return []


def _migrations_on_disk() -> List[str]:
    here = Path(__file__).resolve()
    for parent in here.parents:
        d = parent / "db" / "migrations"
        if d.is_dir():
            return sorted(p.name for p in d.glob("*.sql"))
    return []


def verify_target(*, data_dir: Path, db_path: Path, plan: merge.MergePlan,
                  forbidden_roots: Sequence[Path] = ()) -> TargetReport:
    """Is this root a product-initialised, empty Lorevox installation ready to receive
    the planned narrator? **Reads only.** Never initialises, never repairs.

    The root is the exact one supplied. `DATA_DIR` is consulted only to FORBID the live
    root, never to find a target — a merge that fell back to an environment default
    would be one typo away from writing into the family's live installation.
    """
    root = validate_root(data_dir)
    db_path = Path(db_path).resolve()
    reasons: List[Dict[str, str]] = []
    checks: Dict[str, Any] = {}

    forbidden = [Path(p).resolve() for p in forbidden_roots if p]
    live = os.environ.get("DATA_DIR")
    if live:
        forbidden.append(Path(live).resolve())
    for bad in forbidden:
        if root == bad or bad in root.parents or root in bad.parents:
            reasons.append({"code": R_TARGET_IS_A_SOURCE,
                            "detail": f"target {root} overlaps a source or live root {bad}"})
    checks["forbidden_roots"] = [str(p) for p in forbidden]

    if not db_path.is_file():
        reasons.append({"code": R_TARGET_DB_MISSING,
                        "detail": f"{db_path} does not exist — the PRODUCT initialises the "
                                  f"root (migrations + init_db + seeds); Merge/Remap populates it"})
        return TargetReport(False, root, db_path, reasons, checks)
    if db_path.parent != root and root not in db_path.parents:
        reasons.append({"code": R_TARGET_IS_A_SOURCE,
                        "detail": f"database {db_path} is not inside the target root {root}"})

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        applied = set(_applied_migrations(con))
        on_disk = _migrations_on_disk()
        missing = [m for m in on_disk if m not in applied]
        checks["migrations_applied"] = len(applied)
        checks["migrations_missing"] = missing
        if on_disk and missing:
            reasons.append({"code": R_TARGET_SCHEMA_STALE,
                            "detail": f"{len(missing)} migration(s) not applied, first: {missing[0]}"})

        try:
            people = con.execute(
                "SELECT id, COALESCE(testing_only, 0) AS testing FROM people").fetchall()
        except sqlite3.Error as exc:
            reasons.append({"code": R_TARGET_DB_MISSING, "detail": f"people unreadable: {exc}"})
            people = []
        real = [r["id"] for r in people if not r["testing"]]
        checks["narrators_present"] = len(people)
        checks["real_narrators_present"] = len(real)
        checks["other_narrators"] = [i for i in real if i != plan.narrator_id]
        # OTHER NARRATORS ARE ALLOWED, and refusing them was a real defect.
        # The family root is built by accumulation — Christopher, then Kent, then
        # Janice, into ONE installation — so "the target already holds a narrator"
        # cannot be a refusal or the second merge is impossible. What must be refused
        # is THIS narrator already being there. The ids the other narrators occupy are
        # handled by `bind_to_target`, not by keeping the root empty.
        if any(r["id"] == plan.narrator_id for r in people):
            reasons.append({"code": R_TARGET_NARRATOR_PRESENT,
                            "detail": f"{plan.narrator_id} already exists in the target"})
    finally:
        con.close()

    # Any narrator-owned file already sitting where this merge would write is a refusal:
    # O_EXCL would fail mid-run otherwise, and a half-populated root is the one outcome
    # that must never exist.
    present = []
    for entry in plan.files_union:
        dest = pkg._safe_destination(root, entry["path"])
        if dest is None:
            reasons.append({"code": R_UNSAFE_DESTINATION, "detail": entry["path"]})
        elif dest.exists():
            present.append(entry["path"])
    checks["colliding_files"] = present[:20]
    if present:
        reasons.append({"code": R_TARGET_PAYLOAD_PRESENT,
                        "detail": f"{len(present)} planned file(s) already exist, first: {present[0]}"})

    # Installation dependencies, through the SHARED helper rather than through restore's
    # verdict. A merge is not two restores: `narrator_exists` and single-package row
    # collisions are rules Merge/Remap deliberately supersedes, and inheriting them would
    # make a merge refuse for reasons about restoring one package. What it must inherit is
    # the DEPENDENCY LOOKUP, because that is the rule Phase 5a proved is easy to get wrong
    # — the ids name a referenced column, not always a primary key. One definition
    # (`narrator_package.missing_installation_dependencies`), two workflows.
    declared_union: Dict[str, set] = {}
    for origin in plan.origins:
        for table, ids in (_manifest_of(Path(origin["path"]))
                           .get("installation_dependencies") or {}).items():
            declared_union.setdefault(table, set()).update(ids)
    union = {t: sorted(v) for t, v in declared_union.items()}
    checks["installation_dependencies_required"] = union

    con = sqlite3.connect(str(db_path))
    try:
        missing = pkg.missing_installation_dependencies(con, union)
    finally:
        con.close()
    checks["installation_dependencies_missing"] = missing
    if missing:
        reasons.append({
            "code": R_TARGET_NOT_READY,
            "detail": f"the target lacks installation-owned state both origins reference: "
                      f"{[m['table'] for m in missing]} — the PRODUCT provides this, "
                      f"not the merge",
        })

    return TargetReport(not reasons, root, db_path, reasons, checks)


# ══════════════════════════════════════════════════════════════════════
# Target binding — READ ONLY. Between the source plan and the write.
# ══════════════════════════════════════════════════════════════════════
#
# THE SOURCE PLANNER ALLOCATES FROM 1, AND THAT IS ONLY RIGHT ONCE.
#
# `narrator_merge` renumbers the three installation-local integer families from 1 in
# deterministic order. For the first narrator into a fresh root that is exactly right.
# For the second it is wrong: Christopher lands holding `turns.id = 1..N`, and Kent's
# independently planned two-origin merge asks for the same 1..N. Refusing a target that
# already holds a narrator would "solve" that by making the family root impossible to
# build — and a single accumulated root is the whole point of Phase 7.
#
# So binding is its own stage, and it stays READ-ONLY:
#
#     two packages -> source merge plan -> inspect initialised target
#     -> bind around occupied ids -> execution plan -> apply
#
# The planner never learns about targets (it stays pure and writer-free, which is what
# makes it reviewable); the executor never silently replans (the basis is fingerprinted,
# and a target that moved between bind and apply is a REFUSAL, not a recomputation).


@dataclass
class BoundPlan:
    """A source plan rebound around what the target already holds."""
    plan: merge.MergePlan
    root: Path
    db_path: Path
    #: parent -> plan id -> final target id
    target_remap: Dict[str, Dict[Any, Any]]
    merged_records: Dict[str, List[Dict[str, Any]]]
    target_basis: Dict[str, Any]
    basis_fingerprint: str
    execution_fingerprint: str
    target: TargetReport
    refusals: List[Dict[str, str]] = field(default_factory=list)
    rebinds: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def refused(self) -> bool:
        return bool(self.refusals) or not self.target.ready


def _occupied(con: sqlite3.Connection, table: str, column: str = "id") -> List[Any]:
    try:
        return [r[0] for r in con.execute(f'SELECT "{column}" FROM "{table}"').fetchall()
                if r[0] is not None]
    except sqlite3.Error:
        return []


def target_basis(root: Path, db_path: Path, plan: merge.MergePlan) -> Dict[str, Any]:
    """The target state a binding depends on — and NOTHING ELSE.

    Deliberately not a fingerprint of the whole installation: writing the merge job row
    would change that, so a merge would invalidate its own basis and could never execute.
    What is included is only what the allocation and the refusals actually read.
    """
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        basis: Dict[str, Any] = {
            "migrations": sorted(_applied_migrations(con)),
            "schema": pkg._schema_fingerprint(con),
            "narrators": sorted(r[0] for r in con.execute("SELECT id FROM people")),
        }
        occupied: Dict[str, List[Any]] = {}
        for table in sorted(plan.merged_records):
            if table in ("narrator_merge_jobs", "narrator_package_jobs"):
                continue                       # operational churn is not part of the basis
            cols = merge.physical_key_columns(table)
            if len(cols) != 1:
                continue
            ids = _occupied(con, table, cols[0])
            if ids:
                occupied[table] = sorted((str(i) for i in ids))
        basis["occupied_physical_keys"] = occupied
        deps: Dict[str, Any] = {}
        for origin in plan.origins:
            for t, ids in (_manifest_of(Path(origin["path"]))
                           .get("installation_dependencies") or {}).items():
                deps.setdefault(t, set()).update(ids)
        basis["installation_dependencies"] = {t: sorted(v) for t, v in deps.items()}
        basis["missing_dependencies"] = pkg.missing_installation_dependencies(
            con, basis["installation_dependencies"])
    finally:
        con.close()
    basis["planned_paths_present"] = sorted(
        e["path"] for e in plan.files_union
        if (d := pkg._safe_destination(root, e["path"])) is not None and d.exists())
    return basis


def _fingerprint(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                     default=str).encode("utf-8")).hexdigest()


def _rebind(records: Dict[str, List[Dict[str, Any]]],
            remap: Dict[str, Dict[Any, Any]]
            ) -> Tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
    """Apply a SECOND remap — plan id -> target id — across the full closure.

    Simpler than the planner's first pass because plan ids are already globally unique
    across both origins, so one mapping per parent suffices with no per-origin dimension.
    """
    out = {t: [dict(r) for r in rows] for t, rows in records.items()}
    done: List[Dict[str, Any]] = []
    for parent, mapping in remap.items():
        if not mapping:
            continue
        table, _, column = parent.partition(".")
        for row in out.get(table, []):
            if row.get(column) in mapping:
                new = mapping[row[column]]
                done.append({"table": table, "column": column, "kind": "physical_id",
                             "old": row[column], "new": new})
                row[column] = new
        for site in merge.reference_sites(parent):
            for row in out.get(site.table, []):
                raw = row.get(site.column)
                if raw is None or raw == "":
                    continue
                if site.encoded is None:
                    if raw in mapping:
                        done.append({"table": site.table, "column": site.column,
                                     "kind": "reference", "old": raw, "new": mapping[raw]})
                        row[site.column] = mapping[raw]
                    continue
                old_id, malformed = site.encoded.parse(raw)
                if malformed or old_id is None or old_id not in mapping:
                    continue
                done.append({"table": site.table, "column": site.column,
                             "kind": "reference", "old": old_id, "new": mapping[old_id]})
                row[site.column] = merge.render_encoded(site.encoded, raw, mapping[old_id])
    return out, done


def _free_integers(occupied: Sequence[Any], count: int) -> List[int]:
    """The lowest free positive integers, deterministically. An empty target therefore
    still yields 1..N — binding changes nothing when there is nothing to avoid."""
    taken = set()
    for v in occupied:
        try:
            taken.add(int(v))
        except (TypeError, ValueError):
            continue
    out, candidate = [], 1
    while len(out) < count:
        if candidate not in taken:
            out.append(candidate)
        candidate += 1
    return out


def bind_to_target(plan: merge.MergePlan, *, data_dir: Path, db_path: Path) -> BoundPlan:
    """Rebind a source plan around what the target already holds. **Writes nothing.**"""
    # the source packages' own directories are forbidden targets, exactly as the live
    # DATA_DIR is — a merge must never write into the evidence it is reading
    target = verify_target(data_dir=data_dir, db_path=db_path, plan=plan,
                           forbidden_roots=[Path(o["path"]).parent for o in plan.origins])
    root, db_path = target.root, target.db_path
    basis = target_basis(root, db_path, plan)
    refusals: List[Dict[str, str]] = []
    remap: Dict[str, Dict[Any, Any]] = {}

    con = sqlite3.connect(str(db_path))
    try:
        # 1. the three installation-local integer families
        for parent in merge.REMAP_TARGETS:
            table, _, column = parent.partition(".")
            rows = plan.merged_records.get(table, [])
            plan_ids = sorted({r[column] for r in rows if isinstance(r.get(column), int)})
            if not plan_ids:
                continue
            free = _free_integers(_occupied(con, table, column), len(plan_ids))
            mapping = {old: new for old, new in zip(plan_ids, free) if old != new}
            if mapping:
                remap[parent] = mapping

        # 2. non-integer physical keys colliding with rows ALREADY in the target — a
        #    different narrator's row wearing the same id. Never overwritten, and equal
        #    bytes are never proof of cross-narrator identity.
        for table in sorted(plan.merged_records):
            cols = merge.physical_key_columns(table)
            parent = f"{table}.{cols[0]}"
            if parent in merge.REMAP_TARGETS or len(cols) != 1:
                continue
            here = {r[cols[0]] for r in plan.merged_records[table] if cols[0] in r}
            clash = sorted(here & set(_occupied(con, table, cols[0])), key=str)
            if not clash:
                continue
            if parent not in merge.CLOSURE_ESTABLISHED:
                refusals.append({
                    "code": R_UNKNOWN_COLLISION_CLOSURE,
                    "detail": f"{len(clash)} {table} id(s) already exist in the target and "
                              f"{parent} has no established reference closure — first: "
                              f"{clash[0]}",
                })
                continue
            taken = set(_occupied(con, table, cols[0])) | here
            mapping = {}
            for old in clash:
                new = str(uuid.uuid5(merge.REMAP_NAMESPACE, f"target|{table}|{old}"))
                salt = 0
                while new in taken:
                    salt += 1
                    new = str(uuid.uuid5(merge.REMAP_NAMESPACE,
                                         f"target|{table}|{old}|{salt}"))
                taken.add(new)
                mapping[old] = new
            remap[parent] = mapping
    finally:
        con.close()

    records, rebinds = _rebind(plan.merged_records, remap)
    basis_fp = _fingerprint(basis)
    execution_fp = _fingerprint({
        "source": plan_fingerprint(plan),
        "target_basis": basis_fp,
        "target_remap": {p: {str(k): str(v) for k, v in m.items()}
                         for p, m in sorted(remap.items())},
    })
    return BoundPlan(plan=plan, root=root, db_path=db_path, target_remap=remap,
                     merged_records=records, target_basis=basis,
                     basis_fingerprint=basis_fp, execution_fingerprint=execution_fp,
                     target=target, refusals=refusals, rebinds=rebinds)


# ══════════════════════════════════════════════════════════════════════
# Applying the plan
# ══════════════════════════════════════════════════════════════════════

def _strip(row: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in row.items() if k not in PROVENANCE_KEYS}


def _open_sources(plan: merge.MergePlan) -> Dict[str, Dict[str, Any]]:
    """Bind execution to the EXACT packages the plan was made from.

    A plan is a decision about specific bytes. Re-reading a package that has changed
    since — or a different file at the same path — would apply those decisions to data
    nobody adjudicated, so the sha256 is re-checked before anything is read out of it.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for origin in plan.origins:
        path = Path(origin["path"])
        digest = merge._sha256_file(path)
        if digest != origin["sha256"]:
            raise MergeApplyRefused(
                R_SOURCE_CHANGED,
                f"{path.name}: plan recorded {origin['sha256'][:12]}…, file is {digest[:12]}…")
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            manifest = {}
            for name in names:
                if name.endswith(merge.MANIFEST_NAME):
                    manifest = json.loads(zf.read(name).decode("utf-8"))
                    break
        out[origin["label"]] = {"path": path, "manifest": manifest,
                                "package_id": origin["package_id"]}
    return out


def _file_member(zf: zipfile.ZipFile, rel: str) -> Optional[str]:
    want = merge.FILES_PREFIX + rel
    for name in zf.namelist():
        if name.endswith(want) or name == want:
            return name
    return None


def _regenerate_archive_index(root: Path, paths: Sequence[str]) -> List[str]:
    """Rebuild each `index.json` from the merged sessions' own `meta.json` files.

    §3b, decided from code rather than from the filename: `_register_session_in_index`
    writes only `{session_id, title, mode, started_at}` (`archive.py:1216-1224`), and
    every one of those fields is already in `sessions/<id>/meta.json` (`archive.py:90-97`).
    So a differing `index.json` is a derived registry, fully regenerable, and must NOT be
    surfaced as a narrator-content conflict. `rolling_summary.json` is the opposite — LLM
    memory, scored and pruned — and V1 refuses it instead.
    """
    written: List[str] = []
    for rel in paths:
        index_path = pkg._safe_destination(root, rel)
        if index_path is None:
            continue
        sessions_dir = index_path.parent / "sessions"
        entries: List[Dict[str, Any]] = []
        if sessions_dir.is_dir():
            for meta_path in sorted(sessions_dir.glob("*/meta.json")):
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                entries.append({"session_id": meta.get("session_id"),
                                "title": meta.get("title", ""),
                                "mode": meta.get("mode"),
                                "started_at": meta.get("started_at")})
        person_id = index_path.parent.name
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(
            json.dumps({"person_id": person_id, "sessions": entries},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        written.append(rel)
    return written


def apply_merge(bound: BoundPlan, *, requested_by: str = "",
                _crash_seam=None) -> MergeApplyResult:
    """Apply a REFUSAL-FREE BOUND plan into its product-initialised target.

    Refuses — writing nothing — if the source plan carries any unresolved conflict, if
    binding refused, if a source package has changed since the plan was made, or if the
    **target moved since the binding was computed**. That last one is deliberately a
    refusal rather than a quiet recomputation: the ids this merge is about to write were
    chosen against a specific target state, and re-deriving them mid-apply would mean
    executing a plan nobody dry-ran.

    `_crash_seam(point)` is a test-only hook called at 'after_first_file' and
    'after_commit'; nothing here catches BaseException, exactly as a real process death
    would not be caught.
    """
    seam = _crash_seam or (lambda _point: None)
    plan, target = bound.plan, bound.target
    root, db_path = bound.root, bound.db_path

    if plan.refused:
        raise MergeApplyRefused(
            R_PLAN_UNRESOLVED,
            f"{len(plan.refusals)} conflict(s) and {len(plan.dangling_after_rewrite)} "
            f"dangling reference(s) need a human decision; nothing was written",
            report={"refusals": plan.refusals,
                    "dangling": plan.dangling_after_rewrite,
                    "origins": plan.origins})
    if bound.refused:
        raise MergeApplyRefused(
            R_TARGET_NOT_READY,
            "; ".join(r["code"] for r in (bound.refusals + target.reasons)),
            report={"target": target, "binding": bound.refusals})

    sources = _open_sources(plan)

    current = _fingerprint(target_basis(root, db_path, plan))
    if current != bound.basis_fingerprint:
        raise MergeApplyRefused(
            R_TARGET_CHANGED,
            f"the target changed since it was bound ({bound.basis_fingerprint[:12]}… -> "
            f"{current[:12]}…); dry-run again rather than executing a plan nobody saw",
            report={"bound": bound.basis_fingerprint, "now": current})

    # ── the durable job, committed before the first byte lands ────────
    planned: Dict[str, str] = {}
    for entry in plan.files_union:
        if pkg._safe_destination(root, entry["path"]) is None:
            raise MergeApplyRefused(R_UNSAFE_DESTINATION, entry["path"])
        planned[entry["path"]] = entry["sha256"]
    a_origin, b_origin = plan.origins[0], plan.origins[1]
    job_id = uuid.uuid4().hex
    job = {"id": job_id, "state": "validated",
           "narrator_id": plan.narrator_id, "target_root": str(root),
           "source_a_package_id": a_origin["package_id"],
           "source_a_sha256": a_origin["sha256"], "source_a_path": a_origin["path"],
           "source_b_package_id": b_origin["package_id"],
           "source_b_sha256": b_origin["sha256"], "source_b_path": b_origin["path"],
           # the BOUND fingerprint: what actually lands, not what the source plan
           # proposed before it knew what the target already held
           "plan_fingerprint": bound.execution_fingerprint,
           "target_basis": bound.basis_fingerprint,
           "file_manifest_json": json.dumps(planned, sort_keys=True),
           "files_json": "[]",
           "expected_counts_json": json.dumps(
               {t: len(rows) for t, rows in bound.merged_records.items() if rows},
               sort_keys=True),
           "counts_json": "{}", "error": None, "recovery": None,
           "requested_by": requested_by, "created_at": pkg._now()}
    _merge_job_write(db_path, job)

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
        _merge_job_write(db_path, job)
        raise RuntimeError(f"MERGE FAILED at {stage}; job {job_id} is {job['state']}: {exc}") from exc

    # ── files first, O_EXCL, re-hashed, journalled one by one ─────────
    journal = sqlite3.connect(str(db_path))
    handles: Dict[str, zipfile.ZipFile] = {}
    try:
        for label, src in sources.items():
            handles[label] = zipfile.ZipFile(src["path"])
        rank0 = plan.origins[0]["label"]
        for entry in plan.files_union:
            rel, origin = entry["path"], entry["origin"]
            zf = handles[rank0 if origin == "both" else origin]
            member = _file_member(zf, rel)
            if member is None:
                raise ValueError(f"{rel} is in the plan but not in {origin}'s package")
            dest = pkg._safe_destination(root, rel)
            if dest is None:
                raise ValueError(f"unsafe destination {rel}")
            need = []
            cur = dest.parent
            while not cur.exists():
                need.append(cur)
                cur = cur.parent
            for d in reversed(need):
                d.mkdir()
                created_dirs.append(d)
            fd = os.open(str(dest), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            with os.fdopen(fd, "wb") as dst, zf.open(member) as srcf:
                shutil.copyfileobj(srcf, dst)
            created.append(dest)
            digest, _ = pkg._sha256_file(dest)
            if digest != entry["sha256"]:
                raise ValueError(f"re-hash mismatch after copy: {rel}")
            journal.execute(
                "UPDATE narrator_merge_jobs SET files_json=?, updated_at=? WHERE id=?",
                (json.dumps([str(p.relative_to(root)) for p in created]), pkg._now(), job_id))
            journal.commit()
            if len(created) == 1:
                seam("after_first_file")
        job.update(state="files_copied",
                   files_json=json.dumps([str(p.relative_to(root)) for p in created]))
        _merge_job_write(db_path, job)
    except Exception as exc:  # noqa: BLE001
        journal.close()
        for zf in handles.values():
            zf.close()
        _fail("files", exc)
    finally:
        try:
            journal.close()
        except Exception:
            pass
        for zf in handles.values():
            try:
                zf.close()
            except Exception:
                pass

    # ── one transaction; nothing visible until it commits ─────────────
    basis_by_origin = {label: (src["manifest"].get("path_column_basis") or {})
                       for label, src in sources.items()}
    inserted: Dict[str, int] = {}
    con = sqlite3.connect(str(db_path), isolation_level=None)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("BEGIN IMMEDIATE")
        con.execute("PRAGMA defer_foreign_keys=ON")
        try:
            for table in inv.narrator_owned_tables():     # declaration order: parents first
                n = 0
                for raw in bound.merged_records.get(table, []):
                    origin = raw.get("_origin") or plan.origins[0]["label"]
                    rec = _strip(raw)
                    # absolute path columns belong to the ORIGIN's root; rewrite under
                    # the new one, using the basis the exporter recorded per package
                    basis = basis_by_origin.get(
                        origin if origin != "both" else plan.origins[0]["label"], {})
                    for col, kind in (basis.get(table) or {}).items():
                        v = rec.get(col)
                        if v not in (None, "") and kind == "absolute":
                            rec[col] = str(root / v)
                    cols = ", ".join(f'"{c}"' for c in rec)
                    con.execute(
                        f'INSERT INTO "{table}" ({cols}) VALUES ({", ".join("?" for _ in rec)})',
                        tuple(rec.values()))
                    n += 1
                if n:
                    inserted[table] = n

            expected = {t: len(rows) for t, rows in bound.merged_records.items() if rows}
            if inserted != expected:
                raise ValueError(f"inserted {inserted} != bound plan {expected}")

            # SQLite's own check, on the tables this job wrote…
            bad = []
            for table in inserted:
                bad += con.execute(f'PRAGMA foreign_key_check("{table}")').fetchall()
            if bad:
                raise ValueError(f"foreign_key_check: {[tuple(r) for r in bad[:10]]}")

            # …and the one SQLite cannot do. No migration declares `REFERENCES turns`,
            # so a merged database can pass the check above and still be broken. This
            # reads back what ACTUALLY LANDED rather than trusting the plan.
            readback: Dict[str, List[Dict[str, Any]]] = {}
            for parent in merge.CLOSURE_ESTABLISHED:
                wanted = {parent.split(".")[0]}
                wanted |= {s.table for s in merge.reference_sites(parent)}
                for t in wanted:
                    if t in readback or t not in inserted:
                        continue
                    readback[t] = [dict(r) for r in
                                   con.execute(f'SELECT * FROM "{t}"').fetchall()]
            dangling = merge.validate_semantic_references(readback)
            if dangling:
                raise ValueError(f"semantic reference validation failed: {dangling[:10]}")

            # `db_committed` travels in THE SAME transaction as the rows: COMMIT
            # publishes both or neither, so no crash can leave visible rows beside a
            # job row that says less happened than did.
            con.execute(
                "UPDATE narrator_merge_jobs SET state='db_committed', counts_json=?, "
                "updated_at=? WHERE id=?",
                (json.dumps(inserted), pkg._now(), job_id))
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
    regenerated = _regenerate_archive_index(root, plan.files_regenerate)
    job.update(state="db_committed", counts_json=json.dumps(inserted))
    job.update(state="complete")
    _merge_job_write(db_path, job)

    return MergeApplyResult(
        job_id=job_id, narrator_id=plan.narrator_id, records_inserted=inserted,
        files_created=[str(p.relative_to(root)) for p in created],
        index_files_regenerated=regenerated, target=target)


# ══════════════════════════════════════════════════════════════════════
# Crash recovery — from the durable ledger alone
# ══════════════════════════════════════════════════════════════════════

def recover_merge_jobs(*, data_dir: Path, db_path: Path,
                       job_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Finish or undo merge jobs a process death left behind.

    Decides from the DURABLE job row, whose states are truthful by construction because
    `db_committed` is written inside the narrator transaction:

      staged / validated / files_copied   the transaction CANNOT have committed. Remove
                                          only the files this job created; `failed` when
                                          clean, `cleanup_required` naming what is left.
      db_committed                        the rows ARE published. **NEVER delete.**
                                          Verify the counts, advance to `complete`, or
                                          leave `db_committed` with a recovery note and
                                          refuse automatic destruction.
      cleanup_required                    retry only the recorded set.
      complete / failed                   idempotent no-op, reported.

    **FILES ARE NEVER JUDGED BY PATHNAME.** `file_manifest_json` was written before the
    first byte and gives the sha256 each planned path must have. Below `db_committed` a
    file is removed only when its bytes hash to that digest; anything else at a planned
    path was not created by this job and is left alone and named. That is what stops
    recovery from deleting a pre-existing file — the one thing a recovery pass must
    never do.

    Defensive check on top of the invariant: a job below `db_committed` that finds the
    narrator's `people` row present is a CONTRADICTION to report, not a state to repair
    by deleting files out from under a published narrator.
    """
    root = validate_root(data_dir)
    db_path = Path(db_path)
    out: List[Dict[str, Any]] = []

    for row in _merge_job_rows(db_path, job_id):
        state = row["state"]
        result = {"job_id": row["id"], "was": state, "narrator_id": row["narrator_id"]}

        if state in ("complete", "failed"):
            result.update(now=state, action="none")
            out.append(result)
            continue

        if str(row.get("target_root") or "") != str(root):
            result.update(now=state, action="skipped",
                          detail=f"job targets {row.get('target_root')!r}, not {root}")
            out.append(result)
            continue

        planned: Dict[str, str] = json.loads(row.get("file_manifest_json") or "{}")
        recorded: List[str] = json.loads(row.get("files_json") or "[]")

        if state == "db_committed":
            con = sqlite3.connect(str(db_path))
            con.row_factory = sqlite3.Row
            try:
                expected = json.loads(row.get("counts_json") or "{}")
                actual = {}
                for table in expected:
                    try:
                        actual[table] = con.execute(
                            f'SELECT COUNT(*) c FROM "{table}"').fetchone()["c"]
                    except sqlite3.Error:
                        actual[table] = None
            finally:
                con.close()
            short = {t: (expected[t], actual.get(t)) for t in expected
                     if actual.get(t) is None or actual[t] < expected[t]}
            if short:
                _merge_job_write(db_path, {**row, "state": "db_committed",
                                           "recovery": f"recovery_required: {short}"})
                result.update(now="db_committed", action="reported",
                              detail="rows are published but counts do not verify; "
                                     "refusing automatic destruction")
            else:
                _merge_job_write(db_path, {**row, "state": "complete",
                                           "recovery": "completed_by_recovery"})
                result.update(now="complete", action="finished")
            out.append(result)
            continue

        # Below db_committed: the transaction cannot have committed.
        con = sqlite3.connect(str(db_path))
        try:
            published = con.execute("SELECT 1 FROM people WHERE id=?",
                                    (row["narrator_id"],)).fetchone()
        except sqlite3.Error:
            published = None
        finally:
            con.close()
        if published:
            _merge_job_write(db_path, {**row, "recovery": "contradiction: narrator present "
                                                          "below db_committed"})
            result.update(now=state, action="reported",
                          detail="the narrator exists while the job says the transaction "
                                 "never committed — reported, nothing touched")
            out.append(result)
            continue

        removed, left = [], []
        for rel in recorded or list(planned):
            dest = pkg._safe_destination(root, rel)
            if dest is None or not dest.is_file():
                continue
            want = planned.get(rel)
            digest, _ = pkg._sha256_file(dest)
            if want and digest == want:
                try:
                    dest.unlink()
                    removed.append(rel)
                except OSError:
                    left.append(rel)
            else:
                # Not the bytes this job planned: somebody else's file at a planned path.
                left.append(rel)
        now = "cleanup_required" if left else "failed"
        _merge_job_write(db_path, {**row, "state": now,
                                   "files_json": json.dumps(left),
                                   "recovery": f"removed {len(removed)}, left {len(left)}"})
        result.update(now=now, action="cleaned", removed=removed, left=left)
        out.append(result)
    return out
