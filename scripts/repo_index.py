#!/usr/bin/env python3
"""Generate the repository index for WO-REPOSITORY-RATIONALIZATION-2026-09-08.

    cd /mnt/c/Users/chris/hornelore
    .venv/bin/python scripts/repo_index.py --out docs/repository

READ-ONLY. Enumerates tracked files, measures them, proposes a
disposition, and writes a Markdown index plus a machine-readable JSON.
It moves nothing, deletes nothing and stages nothing.

WHY GENERATED, NOT HAND-COUNTED. CLAUDE.md's rule is that counts are
derived and never written down, because a hand-maintained count of a
directory is wrong the moment anything moves. The August pass produced
three copies of one number that already disagreed with each other. This
script is the count.

THE PROPOSED DISPOSITION IS A HYPOTHESIS, NOT A VERDICT. Every rule here
is mechanical — age, path, reference count — and the work order is
explicit that none of those may decide a file's fate on their own:

    "Do not bulk-delete files based on age, filename, low reference
     count, or an ACTIVE/CLOSED header."

So the strongest thing this file emits is ADJUDICATE, and the disposition
column exists to make the adjudication tractable, not to pre-empt it. A
file's real disposition is settled by reading it against current code and
against docs/BACKLOG.md, and recorded in the manifest by a human.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

REPO = Path(__file__).resolve().parent.parent

TEXT_EXT = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".md", ".txt", ".json", ".yml",
    ".yaml", ".sh", ".bat", ".html", ".css", ".cfg", ".ini", ".toml",
    ".sql", ".csv",
}

#: Paths whose contents are production and are never archive candidates.
PRODUCTION_ROOTS = ("server/", "ui/js/", "ui/hornelore1.0.html")

#: Already-archived locations. Recorded, never re-dispositioned.
ARCHIVE_ROOTS = ("docs/archive/", "scripts/archive/", "tests/archive/")

#: Root files that genuinely belong at root (WO section 4).
ROOT_KEEP = {
    "README.md", "CLAUDE.md", "HANDOFF.md", "MASTER_WORK_ORDER_CHECKLIST.md",
    "CONTRIBUTING.md", "AGENT_CONTRACT.md", "LICENSE", ".env.example",
    ".gitignore", "package.json", "package-lock.json", "playwright.config.ts",
    "tsconfig.playwright.json", "requirements-gpu.txt", "requirements-test.txt",
    "requirements-tts.txt", "hornelore-serve.py",
}

STALE_DAYS = 45


def sh(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(REPO), *args],
        capture_output=True, text=True, check=True,
    ).stdout


def tracked_with_size(rev: str) -> Dict[str, int]:
    """Path -> blob size, from one `ls-tree` rather than one call per file."""
    out: Dict[str, int] = {}
    for line in sh("ls-tree", "-r", "-l", rev).splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if len(parts) < 4 or parts[1] != "blob":
            continue
        try:
            out[path] = int(parts[3])
        except ValueError:
            out[path] = 0
    return out


def last_touch(rev: str) -> Dict[str, tuple]:
    """Path -> (iso date, short sha) of the most recent commit touching it.

    ONE traversal of history, not one `git log` per file. At 1,300 files
    the per-file form takes minutes on the /mnt/c 9p mount and produces
    the same answer.
    """
    out: Dict[str, tuple] = {}
    cur_sha = cur_date = ""
    raw = sh("log", rev, "--format=@@%h|%ad", "--date=short", "--name-only")
    for line in raw.splitlines():
        if line.startswith("@@"):
            cur_sha, _, cur_date = line[2:].partition("|")
        elif line.strip():
            out.setdefault(line.strip(), (cur_date, cur_sha))
    return out


def reference_counts(paths: List[str]) -> Dict[str, int]:
    """How many OTHER tracked text files mention this file's basename.

    Deliberately basename-based and deliberately crude. A low count is a
    reason to look, never a reason to move: `docs/archive/INDEX.md`
    references archived files by design, and a script invoked only from a
    copy-paste block in a work order legitimately scores zero.
    """
    names = {}
    for p in paths:
        base = p.rsplit("/", 1)[-1]
        if len(base) > 3:
            names.setdefault(base, []).append(p)
    counts: Counter = Counter()
    for p in paths:
        if Path(p).suffix.lower() not in TEXT_EXT:
            continue
        try:
            body = (REPO / p).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        own = p.rsplit("/", 1)[-1]
        for base in names:
            if base != own and base in body:
                counts[base] += 1
    return {p: counts.get(p.rsplit("/", 1)[-1], 0) for p in paths}


def subsystem(path: str) -> str:
    return path.split("/", 1)[0] if "/" in path else "(root)"


def classify(path: str, days_old: Optional[int]) -> tuple:
    """(classification, proposed_disposition, note).

    Rules are conservative by construction: anything that is not
    obviously production, infrastructure or already archived is handed to
    a human as ADJUDICATE rather than being proposed for a move.
    """
    p = path
    base = p.rsplit("/", 1)[-1]
    stale = days_old is not None and days_old >= STALE_DAYS

    if p.startswith(ARCHIVE_ROOTS):
        return ("archived", "KEEP_INFRASTRUCTURE", "already archived")
    if p.startswith(PRODUCTION_ROOTS):
        return ("production", "KEEP_ACTIVE", "production source")
    if p.startswith("data/") or p.startswith("fixtures/"):
        return ("fixture", "KEEP_FIXTURE", "")
    if p.startswith("tests/"):
        return ("test", "KEEP_TEST", "test surface - coverage map required")
    if p.startswith("test/"):
        return ("test", "ADJUDICATE",
                "second test tree; WO 10.1 requires assertion mapping first")
    if p.startswith("scripts/"):
        return ("script", "ADJUDICATE" if stale else "KEEP_ACTIVE",
                "stale >= %sd" % STALE_DAYS if stale else "")
    if p.startswith("docs/wo/"):
        return ("work-order", "ADJUDICATE", "classify per WO 6.6")
    if p.startswith("docs/handoffs/"):
        return ("handoff", "ARCHIVE_SUPERSEDED", "WO 6.2")
    if p.startswith("docs/drafts/"):
        return ("draft", "ARCHIVE_SUPERSEDED", "WO 6.3")
    if p.startswith("docs/mockups/") or p.startswith("ui/mockups/"):
        return ("mockup", "ARCHIVE_MOCKUP", "WO 6.4")
    if p.startswith("docs/references/"):
        return ("reference", "REMOVE_AFTER_EXTERNAL_PRESERVATION",
                "WO 13 - checksum and externalise, separate commit")
    if p.startswith("shadow/"):
        return ("design-packet", "ADJUDICATE",
                "WO 6.5 - confirm not consumed programmatically")
    if p.startswith("docs/"):
        return ("doc", "ADJUDICATE", "")
    if "/" not in p:
        if base in ROOT_KEEP:
            return ("control" if base.endswith(".md") else "build",
                    "KEEP_ACTIVE", "")
        if base.startswith(("WO-", "BUG-")) and base.endswith(".md"):
            return ("root-spec", "ADJUDICATE",
                    "WO 6.1 - obligation must reach BACKLOG before moving")
        return ("root-other", "ADJUDICATE", "")
    return ("other", "ADJUDICATE", "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rev", default="HEAD")
    ap.add_argument("--out", default="docs/repository")
    ap.add_argument("--no-refs", action="store_true",
                    help="skip the reference scan (much faster)")
    args = ap.parse_args()

    head = sh("rev-parse", args.rev).strip()
    today = date.today()
    sizes = tracked_with_size(args.rev)
    touched = last_touch(args.rev)
    paths = sorted(sizes)
    refs = {} if args.no_refs else reference_counts(paths)

    rows = []
    for p in paths:
        d, sha = touched.get(p, ("", ""))
        days = None
        if d:
            y, m, dd = (int(x) for x in d.split("-"))
            days = (today - date(y, m, dd)).days
        cls, disp, note = classify(p, days)
        rows.append({
            "path": p,
            "ext": Path(p).suffix.lower() or "(none)",
            "subsystem": subsystem(p),
            "bytes": sizes[p],
            "last_commit_date": d,
            "last_commit_sha": sha,
            "days_since_commit": days,
            "references": refs.get(p),
            "classification": cls,
            "proposed_disposition": disp,
            "note": note,
        })

    out_dir = REPO / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = today.isoformat()

    (out_dir / "repository-index.json").write_text(json.dumps({
        "generated": stamp,
        "head": head,
        "generator": "scripts/repo_index.py",
        "file_count": len(rows),
        "files": rows,
    }, indent=1), encoding="utf-8")

    by_disp = Counter(r["proposed_disposition"] for r in rows)
    by_sub = Counter(r["subsystem"] for r in rows)
    by_cls = Counter(r["classification"] for r in rows)
    bytes_by_sub: Dict[str, int] = defaultdict(int)
    for r in rows:
        bytes_by_sub[r["subsystem"]] += r["bytes"]

    L: List[str] = []
    L.append(f"# Repository index — {stamp}")
    L.append("")
    L.append(f"**Generated by `scripts/repo_index.py` at `{head}`. "
             f"{len(rows)} tracked files.**")
    L.append("")
    L.append("Regenerate rather than edit. Every number here is derived; "
             "none of it is maintained by hand.")
    L.append("")
    L.append("```bash")
    L.append("cd /mnt/c/Users/chris/hornelore")
    L.append(".venv/bin/python scripts/repo_index.py")
    L.append("```")
    L.append("")
    L.append("**The `proposed_disposition` column is a hypothesis.** It is "
             "computed from path, age and reference count, and the work "
             "order forbids any of those deciding a file's fate alone. "
             "`ADJUDICATE` means exactly that: a human reads it against "
             "current code and `docs/BACKLOG.md`.")
    L.append("")
    L.append("## Proposed disposition")
    L.append("")
    L.append("| disposition | files |")
    L.append("|---|---|")
    for k, v in by_disp.most_common():
        L.append(f"| `{k}` | {v} |")
    L.append("")
    L.append("## By subsystem")
    L.append("")
    L.append("| subsystem | files | bytes |")
    L.append("|---|---|---|")
    for k, v in by_sub.most_common():
        L.append(f"| `{k}` | {v} | {bytes_by_sub[k]:,} |")
    L.append("")
    L.append("## By classification")
    L.append("")
    L.append("| classification | files |")
    L.append("|---|---|")
    for k, v in by_cls.most_common():
        L.append(f"| {k} | {v} |")
    L.append("")
    L.append("## Files needing adjudication")
    L.append("")
    adj = [r for r in rows if r["proposed_disposition"] == "ADJUDICATE"]
    L.append(f"**{len(adj)} files.** Sorted oldest first — age is a reason "
             "to look, never a reason to move.")
    L.append("")
    L.append("| path | last commit | days | refs | note |")
    L.append("|---|---|---|---|---|")
    for r in sorted(adj, key=lambda r: (r["last_commit_date"] or "9999")):
        rc = "-" if r["references"] is None else r["references"]
        L.append(f"| `{r['path']}` | {r['last_commit_date']} | "
                 f"{r['days_since_commit']} | {rc} | {r['note']} |")
    L.append("")
    (out_dir / f"REPOSITORY_INDEX_{stamp}.md").write_text(
        "\n".join(L) + "\n", encoding="utf-8")

    print(f"head            {head}")
    print(f"tracked files   {len(rows)}")
    print(f"adjudicate      {by_disp['ADJUDICATE']}")
    print(f"wrote           {args.out}/REPOSITORY_INDEX_{stamp}.md")
    print(f"wrote           {args.out}/repository-index.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
