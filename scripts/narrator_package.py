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

Export is read-only against the source. `--out` must be OUTSIDE the data
root. Nothing here deletes, restores or merges (Phases 3 and 7).
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
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
