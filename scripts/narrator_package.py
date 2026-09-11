#!/usr/bin/env python3
"""Recovery CLI for the Lorevox Narrator Package — WO-LOREVOX-PORTABLE-NARRATOR-01 §28.5.

A thin front end over `api.services.narrator_package`. It exists for when the
operator UI is unavailable; it is not the normal way to operate Lorevox, and
it contains no portability logic of its own.

Paths are EXPLICIT. The environment is never consulted (the WSL profile has
carried stale DATA_DIR / DB_NAME exports before, and a package built from the
wrong root is worse than no package).

    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python scripts/narrator_package.py export \\
        --narrator <people.id> \\
        --data-dir /mnt/c/hornelore_data \\
        --db /mnt/c/hornelore_data/db/hornelore.sqlite3 \\
        --out /mnt/c/lorevox_packages

    PYTHONPATH=server/code .venv/bin/python scripts/narrator_package.py validate \\
        /mnt/c/lorevox_packages/<Narrator>_<id>.lorevox.zip

    PYTHONPATH=server/code .venv/bin/python scripts/narrator_package.py dry-run \\
        <package.lorevox.zip> --data-dir /mnt/c/lorevox_data --db /mnt/c/lorevox_data/db/lorevox.sqlite3

    PYTHONPATH=server/code .venv/bin/python scripts/narrator_package.py restore \\
        <package.lorevox.zip> --data-dir /mnt/c/lorevox_data --db /mnt/c/lorevox_data/db/lorevox.sqlite3 --yes

Export is read-only against the source. `--out` must be OUTSIDE the data
root. `restore` writes the DESTINATION database and root — STACK DOWN — and
always dry-runs first; it restores this narrator as this narrator (ids
verbatim) and refuses any collision. Nothing here deletes or merges (Phase 7).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "server" / "code"))

from api.services import narrator_package as pkg  # noqa: E402


def _export(args) -> int:
    try:
        res = pkg.export_narrator(args.narrator, data_dir=Path(args.data_dir), db_path=Path(args.db),
                                  out_dir=Path(args.out), package_id=args.package_id, repo_root=REPO_ROOT)
    except pkg.ExportRefused as exc:
        print("EXPORT REFUSED — no package was written")
        for r in exc.reasons:
            print("  " + json.dumps(r, ensure_ascii=False))
        return 2
    m = res.manifest
    print(f"wrote {res.package_path}")
    print(f"narrator={m['narrator_id']} package_id={m['package_id']} source_commit={m['source_commit']}")
    print("records_by_lane=" + json.dumps({k: v for k, v in m["record_counts_by_lane"].items() if v}, sort_keys=True))
    print("files_by_lane=" + json.dumps(m["file_counts_by_lane"], sort_keys=True))
    print(f"lanes_absent={m['lanes_absent_in_source']} external_person_dependencies="
          f"{sum(len(v) for v in m['external_person_dependencies'].values())} "
          f"installation_dependencies={ {k: len(v) for k, v in m['installation_dependencies'].items()} }")
    for w in res.warnings:
        print("warning: " + json.dumps(w, ensure_ascii=False))
    for r in m["residue_not_packaged"]:
        print("residue (not packaged): " + json.dumps(r, ensure_ascii=False))
    return 0


def _validate(args) -> int:
    rep = pkg.validate_package(Path(args.package))
    print(("VALID" if rep.ok else "INVALID") + f" {rep.package_path} payload_files={rep.payload_files} payload_bytes={rep.payload_bytes}")
    for p in rep.problems:
        print("  problem: " + p)
    if rep.manifest:
        print(f"narrator={rep.manifest.get('narrator_id')} package_id={rep.manifest.get('package_id')} "
              f"format={rep.manifest.get('package_format')}/{rep.manifest.get('package_format_version')}")
    return 0 if rep.ok else 2


def _print_dry_run(rep) -> None:
    print(rep.verdict + f"  {rep.package_path}")
    if rep.manifest:
        m = rep.manifest
        print(f"narrator={m.get('narrator_id')} {m.get('narrator_display_name')!r} package_id={m.get('package_id')} "
              f"format={m.get('package_format')}/{m.get('package_format_version')} created={m.get('created_at')} "
              f"source_commit={m.get('source_commit')}")
    print("records_by_lane=" + json.dumps({k: v for k, v in rep.records_by_lane.items() if v}, sort_keys=True))
    print("files_by_lane=" + json.dumps(rep.files_by_lane, sort_keys=True) + f" total_bytes={rep.total_bytes}")
    for r in rep.reasons:
        print("  refused: " + json.dumps(r, ensure_ascii=False))
    for w in rep.warnings:
        print("  warning: " + json.dumps(w, ensure_ascii=False))


def _dry_run(args) -> int:
    rep = pkg.dry_run_restore(Path(args.package), data_dir=Path(args.data_dir), db_path=Path(args.db))
    _print_dry_run(rep)
    return 0 if rep.ready else 2


def _restore(args) -> int:
    """Dry run first, always; then restore. Stack must be DOWN — this writes the live database."""
    rep = pkg.dry_run_restore(Path(args.package), data_dir=Path(args.data_dir), db_path=Path(args.db))
    _print_dry_run(rep)
    if not rep.ready:
        return 2
    if not args.yes:
        print("dry run is READY. Re-run with --yes to restore (stack down).")
        return 3
    try:
        res = pkg.restore_narrator(Path(args.package), data_dir=Path(args.data_dir), db_path=Path(args.db),
                                   requested_by=args.requested_by)
    except pkg.RestoreRefused as exc:
        _print_dry_run(exc.report)
        return 2
    except RuntimeError as exc:
        print(str(exc))
        return 4
    print(f"RESTORED narrator={res.narrator_id} package_id={res.package_id} job={res.job_id}")
    print("records_inserted=" + json.dumps(res.records_inserted, sort_keys=True))
    print(f"files_created={len(res.files_created)}")
    return 0


def _recover(args) -> int:
    """Finish or undo restore jobs a process death left incomplete (stack DOWN)."""
    reports = pkg.recover_restore_jobs(data_dir=Path(args.data_dir), db_path=Path(args.db), job_id=args.job)
    if not reports:
        print("no restore jobs")
        return 0
    worst = 0
    for r in reports:
        print(json.dumps(r, ensure_ascii=False))
        if r.get("action") == "refused":
            worst = 2
    return worst


def _compare(args) -> int:
    rep = pkg.compare_packages_semantically(Path(args.a), Path(args.b))
    print(("EQUIVALENT" if rep.equivalent else "DIFFERENT") +
          f"  tables={rep.compared['tables']} rows={rep.compared['rows']} files={rep.compared['files']}")
    for d in rep.differences:
        print("  differs: " + json.dumps(d, ensure_ascii=False, default=str)[:400])
    for i in rep.informational:
        print("  informational: " + json.dumps(i, ensure_ascii=False, default=str)[:200])
    return 0 if rep.equivalent else 2


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    cp = sub.add_parser("compare", help="semantic equivalence of two packages (§28.4); never outer bytes")
    cp.add_argument("a")
    cp.add_argument("b")
    cp.set_defaults(fn=_compare)
    rc = sub.add_parser("recover", help="finish or undo interrupted restore jobs (stack DOWN)")
    rc.add_argument("--data-dir", required=True)
    rc.add_argument("--db", required=True)
    rc.add_argument("--job", default=None, help="one job id; default every incomplete restore job")
    rc.set_defaults(fn=_recover)
    for name, fn, help_ in (("dry-run", _dry_run, "everything restore would check; writes nothing"),
                            ("restore", _restore, "dry-run, then restore this narrator as this narrator (stack DOWN)")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("package")
        p.add_argument("--data-dir", required=True, help="ABSOLUTE DATA_DIR of the DESTINATION installation")
        p.add_argument("--db", required=True, help="ABSOLUTE path to the DESTINATION SQLite file")
        if name == "restore":
            p.add_argument("--yes", action="store_true", help="actually restore after a READY dry run")
            p.add_argument("--requested-by", default="cli")
        p.set_defaults(fn=fn)
    e = sub.add_parser("export", help="build one narrator's package (read-only against the source)")
    e.add_argument("--narrator", required=True, help="people.id")
    e.add_argument("--data-dir", required=True, help="ABSOLUTE DATA_DIR of the source installation")
    e.add_argument("--db", required=True, help="ABSOLUTE path to the source SQLite file")
    e.add_argument("--out", required=True, help="ABSOLUTE directory for the package; must be outside --data-dir")
    e.add_argument("--package-id", default=None)
    e.set_defaults(fn=_export)
    v = sub.add_parser("validate", help="BagIt-validate a package and check its manifest")
    v.add_argument("package")
    v.set_defaults(fn=_validate)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
