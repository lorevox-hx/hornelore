#!/usr/bin/env python3
"""Rehearse a real two-origin merge into a disposable root. READ ONLY by default.

WO-LOREVOX-MULTI-ORIGIN-MERGE-REMAP-01 §6.4 — the rehearsal that turns the synthetic
acceptance into evidence about the actual family.

WHAT THIS IS FOR
    Plan a merge from two real packages, bind it to a product-initialised target, and
    write down exactly what a run WOULD do — including, and especially, what it refuses.
    **A refusal here is the expected V1 result, not a failure.** Christopher, Kent and
    Janice each carry 4 same-key conflicts and a non-regenerable `rolling_summary.json`
    divergence, so all three are expected to stop at the conflict boundary having proven
    everything before it: package validity, the deterministic remap, the complete
    reference rewrite, zero dangling references, the safe union, file classification and
    target readiness.

WHAT IT WILL NOT DO
    * initialise, migrate, seed or repair the target — **the PRODUCT does that** (§5a).
      If the root is not initialised this refuses and prints the command that does it.
    * write anything at all without `--apply`, which additionally refuses unless the
      bound plan carries zero unresolved conflicts.
    * modify, normalise, re-zip or delete a source package. The packages are opened
      read-only and their sha256 is verified against the plan before anything is read.
    * touch either live `DATA_DIR`.

USAGE — the read-only rehearsal
    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python scripts/merge_rehearsal.py \\
        --a .runtime/two_origin/desktop/<pkg>.lorevox.zip \\
        --b .runtime/two_origin/laptop/<pkg>.lorevox.zip \\
        --label-a desktop --label-b laptop \\
        --target-root /mnt/c/hornelore_merge_rehearsal \\
        --out .runtime/merge/reports

Reports carry real narrator content and land under `.runtime/`, which is gitignored.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import importlib
import json
import os
import sqlite3
import sys
from pathlib import Path

_SERVER_CODE = str(Path(__file__).resolve().parents[1] / "server" / "code")
if _SERVER_CODE not in sys.path:
    sys.path.insert(0, _SERVER_CODE)

from api.services import narrator_merge as merge               # noqa: E402
from api.services import narrator_merge_apply as apply_mod     # noqa: E402

#: Columns that are timestamps. A conflict differing ONLY in these is worth flagging to
#: whoever adjudicates — the VALUES matched and only the clock differed — but flagging is
#: all this does.
#:
#: IT DOES NOT MEAN "VOLATILE", AND THE EVIDENCE SAYS SO. The first draft of this script
#: asserted that `people.updated_at` has the same semantics as the three columns in
#: `cross_origin_identity.VOLATILE_COLUMNS`, which are rewritten on narrator OPEN with no
#: content change (BACKLOG §5). Reading the writers disproves it: every write to
#: `people.updated_at` accompanies a real change — `display_name` (db.py:7306),
#: `date_of_birth` (:7312), `place_of_birth` (:7318), `narrator_type` (:463), and the
#: delete/restore paths (:6000, :6058). It is a LAST-MODIFIED stamp, not an open-time
#: rewrite, and the author of the volatile registry excluding `people` looks deliberate.
#:
#: So a difference here is a real fact — these two installations last changed this
#: narrator's record at different moments — even though the values agree. This report
#: says that and nothing more; what to do about it is the adjudicator's call.
TIMESTAMP_COLUMNS = {"updated_at", "created_at", "last_updated"}


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _init_hint(root: Path, db_name: str) -> str:
    return (f"DATA_DIR={root} DB_NAME={db_name} \\\n"
            f"  PYTHONPATH=server/code .venv/bin/python "
            f"-c 'from api.db import init_db; init_db()'")


def _resolve_db_path(root: Path, db_name: str) -> Path:
    """Ask the PRODUCT where its database is. Never guess.

    The first draft of this script assumed `<root>/<db_name>` and reported a correctly
    initialised root as uninitialised, because the product puts it under `<root>/db/`.
    Duplicating a path rule is how a harness comes to disagree with the thing it is
    supposed to be rehearsing — so this sets the same environment the product reads and
    takes `api.db.DB_PATH` as the answer.

    **It does not call `init_db()`.** Merge/Remap never initialises a root (§5a).

    The environment is restored afterwards, and `api.db` reloaded again, because
    `verify_target` forbids the LIVE `DATA_DIR` as a target — leaving it pointed here
    would make every rehearsal look like an attempt to merge into the live root.
    """
    saved = {k: os.environ.get(k) for k in ("DATA_DIR", "DB_NAME")}
    try:
        os.environ["DATA_DIR"] = str(root)
        if db_name:
            os.environ["DB_NAME"] = db_name
        from api import db as _db
        importlib.reload(_db)
        return Path(_db.DB_PATH)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        from api import db as _db          # leave the module as we found it
        importlib.reload(_db)


def _target_snapshot(root: Path, db_path: Path) -> dict:
    """Enough of the target to PROVE nothing was written, rather than assert it.

    The first version counted payload files and two row counts and called that zero
    mutation. It was blind to the database as a whole — a write to any other table would
    have passed it — and it reported `files: 0` on a correctly initialised root because
    it excluded the one file that was there. Now the resolved database is HASHED, and
    `-wal` / `-shm` are listed rather than hashed because a read can legitimately create
    or touch them.
    """
    snap: dict = {"payload_files": 0, "payload_bytes": 0, "db_sha256": None,
                  "db_bytes": None, "sidecars": [], "people": None, "merge_jobs": None}
    transient = {db_path.name + "-wal", db_path.name + "-shm", db_path.name + "-journal"}
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if p == db_path:
            continue
        if p.name in transient:
            snap["sidecars"].append(p.name)
            continue
        snap["payload_files"] += 1
        snap["payload_bytes"] += p.stat().st_size
    if db_path.is_file():
        snap["db_sha256"] = _sha256(db_path)
        snap["db_bytes"] = db_path.stat().st_size
        con = sqlite3.connect(str(db_path))
        try:
            for key, sql in (("people", "SELECT COUNT(*) FROM people"),
                             ("merge_jobs", "SELECT COUNT(*) FROM narrator_merge_jobs")):
                try:
                    snap[key] = con.execute(sql).fetchone()[0]
                except sqlite3.Error:
                    snap[key] = None
        finally:
            con.close()
    return snap


def _explain_target_delta(before: dict, after: dict) -> str:
    """Name WHAT moved, so a WAL checkpoint is not mistaken for a merge writing rows."""
    moved = [k for k in before if before[k] != after[k]]
    if moved == ["db_sha256"] or sorted(moved) == ["db_bytes", "db_sha256"]:
        return ("only the database FILE changed while every row count and payload file "
                "held — most likely a WAL checkpoint from opening it read-only, but "
                "verify before trusting it")
    return "changed: " + ", ".join(f"{k} {before[k]!r} -> {after[k]!r}" for k in moved)


def _timestamp_only(refusals) -> list:
    """Refusals whose MEASURED differing columns are all timestamps.

    Keyed off `columns`, which `classify_rows` reports from the same comparison that
    produced the verdict — never off the table name, which would be a guess dressed as a
    finding. A refusal reporting no columns is never called timestamp-only.
    """
    out = []
    for r in refusals:
        cols = set(r.get("columns") or [])
        if cols and cols <= TIMESTAMP_COLUMNS:
            out.append(r)
    return out


def _summarise(plan: merge.MergePlan, bound, label_a: str, label_b: str) -> str:
    L = []
    ap = L.append
    ap(f"# Merge rehearsal — narrator `{plan.narrator_id}`")
    ap("")
    ap(f"*Read-only unless --apply was given. Generated {_now()}.*")
    ap("")

    ap("## Inputs")
    ap("")
    ap("| origin | package | sha256 |")
    ap("|---|---|---|")
    for o in plan.origins:
        ap(f"| {o['label']} | `{o['package_id']}` | `{o['sha256'][:16]}…` |")
    ap("")

    ap("## Target")
    ap("")
    t = bound.target
    ap(f"- root: `{t.root}`")
    ap(f"- ready: **{t.ready}**")
    ap(f"- narrators already present: {t.checks.get('narrators_present', 0)} "
       f"(other than this one: {t.checks.get('other_narrators', [])})")
    ap(f"- migrations applied: {t.checks.get('migrations_applied')} "
       f"· missing: {t.checks.get('migrations_missing')}")
    ap(f"- installation dependencies missing: "
       f"{[m['table'] for m in t.checks.get('installation_dependencies_missing', [])]}")
    for r in t.reasons:
        ap(f"- ⚠ **{r['code']}** — {r['detail']}")
    ap("")

    ap("## Binding")
    ap("")
    ap("The source plan allocates installation-local integers from 1. Binding reallocates")
    ap("around what this target already holds; an empty target still yields 1..N.")
    ap("")
    if bound.target_remap:
        ap("| surrogate | rebound ids |")
        ap("|---|---|")
        for parent, mapping in sorted(bound.target_remap.items()):
            ap(f"| `{parent}` | {len(mapping)} |")
    else:
        ap("*Nothing rebound — the target occupied none of the planned ids.*")
    ap("")
    ap(f"- target-basis fingerprint: `{bound.basis_fingerprint[:16]}…`")
    ap(f"- execution fingerprint: `{bound.execution_fingerprint[:16]}…`")
    ap("")

    ap("## What would be written")
    ap("")
    ap(f"- rows: **{sum(len(v) for v in bound.merged_records.values())}** across "
       f"{len(bound.merged_records)} tables")
    ap(f"- files: **{len(plan.files_union)}** (plus {len(plan.files_regenerate)} "
       f"regenerated `index.json`)")
    ap(f"- reference rewrites in the source plan: {len(plan.reference_rewrites)}")
    ap(f"- dangling references after rewrite: **{len(plan.dangling_after_rewrite)}**")
    ap(f"- tables with no defensible cross-origin key (both sides preserved): "
       f"{len(plan.no_safe_key_tables)}")
    ap("")

    ap("## Refusals — the human decisions this merge is waiting on")
    ap("")
    refusals = plan.refusals + bound.refusals
    if not refusals:
        ap("**None.** This plan is executable.")
    else:
        ap(f"**{len(refusals)}**, and V1 resolves none of them. Nothing is written until")
        ap("every one is adjudicated.")
        ap("")
        ap("| # | code | detail |")
        ap("|---|---|---|")
        for i, r in enumerate(refusals, 1):
            ap(f"| {i} | `{r['code']}` | {r['detail']} |")
    ap("")

    stamps = _timestamp_only(refusals)
    if stamps:
        ap("### Worth knowing before adjudicating")
        ap("")
        ap(f"**{len(stamps)} of these refusals differ ONLY in a timestamp**, measured "
           f"from the actual differing columns — every other value on the row agrees:")
        ap("")
        for r in stamps:
            ap(f"- `{r['table']}` differs only in `{', '.join(r['columns'])}`")
        ap("")
        ap("**That is not the same as 'volatile', and the writers say so.** The three")
        ap("columns in `cross_origin_identity.VOLATILE_COLUMNS` are rewritten on narrator")
        ap("OPEN with no content change (BACKLOG §5). Every write to `people.updated_at`")
        ap("instead accompanies a real change — display name, date or place of birth,")
        ap("narrator type, delete/restore. It is a LAST-MODIFIED stamp.")
        ap("")
        ap("So this is a genuine fact rather than noise: the two installations last")
        ap("changed this record at different moments while agreeing on every value. It is")
        ap("a cheap decision, not an empty one, and the report takes no position on it.")
        ap("")

    ap("## Verdict")
    ap("")
    if refusals or not t.ready:
        ap("**REFUSED — and that is the expected V1 result.** Everything up to the conflict")
        ap("boundary is proven above and **nothing was written**. The next step is explicit")
        ap("human adjudication bound to the package ids and hashes named in Inputs, so a")
        ap("decision cannot be replayed against different source data.")
    else:
        ap("**EXECUTABLE.** No unresolved conflict; `--apply` would write this plan.")
    return "\n".join(L)


def main(argv=None) -> int:
    ap_ = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap_.add_argument("--a", required=True)
    ap_.add_argument("--b", required=True)
    ap_.add_argument("--label-a", default="A")
    ap_.add_argument("--label-b", default="B")
    ap_.add_argument("--target-root", required=True)
    ap_.add_argument("--db-name", default="",
                     help="override DB_NAME; default is whatever the product resolves")
    ap_.add_argument("--out", default=".runtime/merge/reports")
    ap_.add_argument("--apply", action="store_true",
                     help="execute a refusal-free bound plan. Refuses otherwise.")
    a = ap_.parse_args(argv)

    root = Path(a.target_root).resolve()
    sources = [Path(a.a).resolve(), Path(a.b).resolve()]
    out_base = Path(a.out).resolve()

    # The report must not land inside the thing it is reporting on: under the target it
    # would become narrator-owned payload nobody planned, and over a source tree it could
    # sit beside — or on — evidence that must stay byte-identical.
    if out_base == root or root in out_base.parents:
        print(f"REFUSED: --out {out_base} is inside the target root {root}", file=sys.stderr)
        return 2
    for src in sources:
        if out_base == src or out_base in src.parents:
            print(f"REFUSED: --out {out_base} contains source package {src}",
                  file=sys.stderr)
            return 2

    db_path = _resolve_db_path(root, a.db_name)
    if not db_path.is_file():
        print("REFUSED: the target is not initialised, and Merge/Remap never initialises "
              f"one — the product does.\n\nThe product resolves its database to:\n  "
              f"{db_path}\n\nInitialise it with:\n\n"
              f"{_init_hint(root, a.db_name or 'lorevox.sqlite3')}\n", file=sys.stderr)
        return 2

    # measured, not asserted: what the sources and the target are BEFORE anything runs
    before_src = {str(p): _sha256(p) for p in sources}
    before_target = _target_snapshot(root, db_path)

    plan = merge.plan_merge(Path(a.a), Path(a.b),
                            label_a=a.label_a, label_b=a.label_b)
    bound = apply_mod.bind_to_target(plan, data_dir=root, db_path=db_path)

    out_dir = out_base / f"merge-{plan.narrator_id[:8]}-{_now()}"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = _summarise(plan, bound, a.label_a, a.label_b)
    (out_dir / "summary.md").write_text(summary, encoding="utf-8")
    (out_dir / "report.json").write_text(json.dumps({
        "narrator_id": plan.narrator_id,
        "origins": plan.origins,
        "target_root": str(root),
        "target_db": str(db_path),
        "source_sha256_before": before_src,
        "target_before": before_target,
        "timestamp_only_refusals": _timestamp_only(plan.refusals + bound.refusals),
        "target_ready": bound.target.ready,
        "target_reasons": bound.target.reasons,
        "target_checks": bound.target.checks,
        "basis_fingerprint": bound.basis_fingerprint,
        "execution_fingerprint": bound.execution_fingerprint,
        "target_remap": {p: {str(k): str(v) for k, v in m.items()}
                         for p, m in bound.target_remap.items()},
        "keyed_verdicts": plan.keyed_verdicts,
        "no_safe_key_tables": plan.no_safe_key_tables,
        "physical_collisions": plan.physical_collisions,
        "refusals": plan.refusals + bound.refusals,
        "dangling_after_rewrite": plan.dangling_after_rewrite,
        "counts": {t: len(v) for t, v in bound.merged_records.items()},
        "files_union": len(plan.files_union),
        "files_regenerate": plan.files_regenerate,
    }, indent=2, default=str), encoding="utf-8")

    print(summary)
    print(f"\nwritten: {out_dir}")

    if not a.apply:
        after_src = {str(p): _sha256(p) for p in sources}
        after_target = _target_snapshot(root, db_path)
        src_ok = after_src == before_src
        tgt_ok = after_target == before_target
        print(f"read-only proof: source packages byte-identical after the run = {src_ok}")
        print(f"read-only proof: target database sha256 "
              f"{(before_target.get('db_sha256') or '')[:16]}… unchanged = "
              f"{before_target.get('db_sha256') == after_target.get('db_sha256')}")
        print(f"read-only proof: target unchanged after the run = {tgt_ok}")
        if not tgt_ok:
            print(f"  {_explain_target_delta(before_target, after_target)}")
        if not (src_ok and tgt_ok):
            print("\nA READ-ONLY REHEARSAL CHANGED SOMETHING. That is a defect in this "
                  "lane, not a nuisance — report it before running anything else.",
                  file=sys.stderr)
            return 4
        return 0
    if plan.refused or bound.refused:
        print("\nREFUSED: --apply was given but this plan has unresolved conflicts. "
              "Nothing was written.", file=sys.stderr)
        return 3
    result = apply_mod.apply_merge(bound, requested_by="merge_rehearsal")
    print(f"\nAPPLIED job {result.job_id}: "
          f"{sum(result.records_inserted.values())} rows, "
          f"{len(result.files_created)} files, "
          f"{len(result.index_files_regenerated)} index files regenerated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
