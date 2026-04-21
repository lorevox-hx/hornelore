#!/usr/bin/env python3
"""
Canon-gap audit — WO-EVAL-CANON-REBUILD-00 (prerequisite).

For every (narrator, fieldPath) referenced by a test case in
data/qa/question_bank_extraction_cases.json, check whether the narrator's
biobuilder template (ui/templates/<narrator>.json) has canon populated for
that field. Outputs a targeted gap list Chris can fill *before* the eval-v2
rebuild, so the rebuild has authoritative canon to rewrite narratorReply
and expectedFields against.

Scope: kent-james-horne, janice-josephine-horne, christopher-todd-horne only.
shatner / dolly are trainer narrators and excluded.

Classifications per (narrator, fieldPath, case_id):
    POPULATED          — canon has a non-empty value for this field leaf
    EMPTY              — canon has the field but it is blank/null/""
    MISSING_IN_CANON   — canon has no such field at all (includes array-leaf
                         paths where the array is empty)
    SCHEMA_MISMATCH    — schema path uses an alias not present in the template
                         key structure; resolver mapped it, report documents

Sources pulled from test cases (union per narrator):
    - expectedFields keys
    - extractPriority entries
    - truthZones keys where zone in {must_extract, may_extract}
    (forbiddenFields / must_not_write are NOT audited — we want those empty.)

Outputs:
    docs/reports/CANON_GAP_AUDIT_<YYYYMMDD>.json
    docs/reports/CANON_GAP_AUDIT_<YYYYMMDD>.md

Usage:
    python3 scripts/audit_canon_gaps.py
    python3 scripts/audit_canon_gaps.py --repo /mnt/c/Users/chris/hornelore
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

SCOPED_NARRATORS = (
    "kent-james-horne",
    "janice-josephine-horne",
    "christopher-todd-horne",
)

# Schema-fieldpath → template-path rewrite rules.
# Keys are prefixes of the schema path; value is the prefix in the template.
# These are known eval-schema-vs-biobuilder-template aliases. When the
# audit rewrites a path, the `resolved` column in the markdown report
# flags it so the eval-harness team knows to fix the alias upstream.
SCHEMA_TO_TEMPLATE_PREFIX = {
    "family.spouse.": "spouse.",
    "family.spouse": "spouse",
    "family.marriageDate": "marriage.weddingDetails",  # lives in freeform text
    "family.marriagePlace": "marriage.weddingDetails",
    "family.children.": "children.",
    "family.children": "children",
    "grandparents.memorableStory": "grandparents.memorableStories",
}

# Sections whose template form is an array of entries. A path like
# "parents.firstName" is audited as "does any parent in the array have
# a non-empty firstName leaf?"
ARRAY_SECTIONS = {
    "parents",
    "grandparents",
    "greatGrandparents",
    "siblings",
    "children",
    "pets",
    "relatives",
    "familyTraditions",
}

# Sections whose template form is an object with leaf fields.
OBJECT_SECTIONS = {
    "personal",
    "spouse",
    "marriage",
    "earlyMemories",
    "education",
    "laterYears",
    "hobbies",
    "health",
    "technology",
    "additionalNotes",
}


def resolve_schema_path(path: str) -> str:
    """Apply schema→template prefix rewrites.

    Exact-match entries are checked before prefix entries so that
    "family.children" (exact) doesn't get swallowed by "family.children."
    """
    if path in SCHEMA_TO_TEMPLATE_PREFIX:
        return SCHEMA_TO_TEMPLATE_PREFIX[path]
    for k, v in SCHEMA_TO_TEMPLATE_PREFIX.items():
        if k.endswith(".") and path.startswith(k):
            return v + path[len(k):]
    return path


def _is_populated(val: Any) -> bool:
    if val is None:
        return False
    if isinstance(val, str):
        return val.strip() != ""
    if isinstance(val, (list, dict)):
        return len(val) > 0
    return True


def lookup_template_leaf(tpl: Dict[str, Any], path: str) -> Tuple[str, Any]:
    """
    Return (classification, evidence) for a dotted path against the template.

    classification ∈ {POPULATED, EMPTY, MISSING_IN_CANON}
    evidence is the value found (trimmed to 120 chars) or None.
    """
    parts = path.split(".")
    if not parts:
        return "MISSING_IN_CANON", None

    top = parts[0]
    rest = parts[1:]

    node = tpl.get(top)
    if node is None:
        return "MISSING_IN_CANON", None

    # Array sections: audit as "any entry with this leaf populated"
    if top in ARRAY_SECTIONS and isinstance(node, list):
        if not node:
            return "MISSING_IN_CANON", None
        if not rest:
            # Just "parents" with no leaf — array itself is populated
            return "POPULATED", f"<{len(node)} entries>"
        leaf = rest[-1]
        hits = []
        for entry in node:
            if not isinstance(entry, dict):
                continue
            # Walk nested path inside each entry (rare: grandparents only has flat leaves)
            cur = entry
            for p in rest:
                if isinstance(cur, dict) and p in cur:
                    cur = cur[p]
                else:
                    cur = None
                    break
            if _is_populated(cur):
                hits.append(str(cur)[:80])
        if hits:
            sample = " | ".join(hits[:3])
            return "POPULATED", f"[{len(hits)}/{len(node)}] {sample}"
        return "EMPTY", f"0/{len(node)} entries have {leaf}"

    # Object sections: nested dict walk
    cur = node
    for p in rest:
        if isinstance(cur, dict):
            if p in cur:
                cur = cur[p]
            else:
                return "MISSING_IN_CANON", None
        else:
            return "MISSING_IN_CANON", None

    if _is_populated(cur):
        val = str(cur)[:120]
        return "POPULATED", val
    return "EMPTY", None


def collect_referenced_paths(case: Dict[str, Any]) -> List[str]:
    """Pull fieldPaths out of expectedFields + extractPriority + positive truthZones."""
    paths: List[str] = []

    ef = case.get("expectedFields") or {}
    paths.extend(ef.keys())

    ep = case.get("extractPriority") or []
    paths.extend(ep)

    tz = case.get("truthZones") or {}
    for path, z in tz.items():
        if isinstance(z, dict) and z.get("zone") in ("must_extract", "may_extract"):
            paths.append(path)

    # De-dupe while preserving order
    seen = set()
    out = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def audit(repo: Path) -> Dict[str, Any]:
    cases_path = repo / "data/qa/question_bank_extraction_cases.json"
    tpl_dir = repo / "ui/templates"

    if not cases_path.exists():
        sys.exit(f"cases file not found: {cases_path}")
    cases = json.loads(cases_path.read_text(encoding="utf-8"))["cases"]

    templates: Dict[str, Dict[str, Any]] = {}
    for slug in SCOPED_NARRATORS:
        tpath = tpl_dir / f"{slug}.json"
        if not tpath.exists():
            sys.exit(f"template not found: {tpath}")
        templates[slug] = json.loads(tpath.read_text(encoding="utf-8"))

    # Per-narrator gap structures
    result: Dict[str, Any] = {
        "_meta": {
            "generated": dt.datetime.utcnow().isoformat() + "Z",
            "repo": str(repo),
            "narrators": list(SCOPED_NARRATORS),
            "cases_total": len(cases),
        },
        "narrators": {},
    }

    for slug in SCOPED_NARRATORS:
        tpl = templates[slug]
        narrator_cases = [c for c in cases if c.get("narratorId") == slug]

        # path → {classification, evidence, cases:[ids], resolved_path}
        path_reports: Dict[str, Dict[str, Any]] = {}

        for c in narrator_cases:
            for path in collect_referenced_paths(c):
                resolved = resolve_schema_path(path)
                entry = path_reports.setdefault(path, {
                    "resolved_path": resolved,
                    "schema_mismatch": resolved != path,
                    "classification": None,
                    "evidence": None,
                    "cases": [],
                })
                if c["id"] not in entry["cases"]:
                    entry["cases"].append(c["id"])

        # Now classify each referenced path against the template
        for path, entry in path_reports.items():
            cls, ev = lookup_template_leaf(tpl, entry["resolved_path"])
            entry["classification"] = cls
            entry["evidence"] = ev

        # Summary counters
        cls_counts = Counter(e["classification"] for e in path_reports.values())

        result["narrators"][slug] = {
            "cases_count": len(narrator_cases),
            "unique_paths_referenced": len(path_reports),
            "classification_counts": dict(cls_counts),
            "paths": path_reports,
        }

    return result


def render_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    meta = report["_meta"]
    lines.append(f"# Canon Gap Audit — {meta['generated'][:10]}")
    lines.append("")
    lines.append(f"Total cases scanned: **{meta['cases_total']}**  ")
    lines.append(f"Narrators in scope: {', '.join(meta['narrators'])}  ")
    lines.append("Trainer narrators (shatner, dolly) excluded.")
    lines.append("")
    lines.append("Classifications:")
    lines.append("")
    lines.append("- **POPULATED** — canon has a non-empty value")
    lines.append("- **EMPTY** — canon has the field, value is blank")
    lines.append("- **MISSING_IN_CANON** — canon has no such field / empty array")
    lines.append("")

    for slug, nrep in report["narrators"].items():
        lines.append("---")
        lines.append("")
        lines.append(f"## {slug}")
        lines.append("")
        lines.append(
            f"Cases: {nrep['cases_count']}  |  Unique fieldPaths referenced: {nrep['unique_paths_referenced']}"
        )
        lines.append("")
        counts = nrep["classification_counts"]
        lines.append(
            f"POPULATED: {counts.get('POPULATED', 0)}  |  "
            f"EMPTY: {counts.get('EMPTY', 0)}  |  "
            f"MISSING_IN_CANON: {counts.get('MISSING_IN_CANON', 0)}"
        )
        lines.append("")

        # Bucket by classification for readability
        buckets = defaultdict(list)
        for path, entry in nrep["paths"].items():
            buckets[entry["classification"]].append((path, entry))

        for bucket_name in ("MISSING_IN_CANON", "EMPTY", "POPULATED"):
            items = buckets.get(bucket_name, [])
            if not items:
                continue
            lines.append(f"### {bucket_name} ({len(items)})")
            lines.append("")
            lines.append("| fieldPath | resolved | evidence | cases |")
            lines.append("|---|---|---|---|")
            for path, entry in sorted(items, key=lambda x: x[0]):
                resolved = entry["resolved_path"]
                resolved_cell = resolved if entry["schema_mismatch"] else "—"
                ev = entry["evidence"] or ""
                ev = ev.replace("|", "\\|").replace("\n", " ")
                if len(ev) > 80:
                    ev = ev[:77] + "..."
                case_ids = entry["cases"]
                case_cell = ", ".join(case_ids[:5])
                if len(case_ids) > 5:
                    case_cell += f" (+{len(case_ids)-5} more)"
                lines.append(f"| `{path}` | {resolved_cell} | {ev} | {case_cell} |")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## What to do with this report")
    lines.append("")
    lines.append(
        "The **MISSING_IN_CANON** and **EMPTY** buckets are the shopping list. "
        "For each narrator, fill the canon fields the eval actually references "
        "(not the whole template tree). Fields you genuinely don't know — lost "
        "ancestor dates, etc. — can stay empty; the scorer policy should "
        "distinguish \"canon says X\" from \"canon silent.\""
    )
    lines.append("")
    lines.append(
        "Schema-mismatch rows (non-`—` in the `resolved` column) indicate "
        "fieldPath aliases the extractor/eval use that don't match the template "
        "key structure (e.g., `family.spouse.*` → `spouse.*`). Those are "
        "eval-harness issues, not canon gaps, and should be fixed in the "
        "eval-v2 rebuild WO."
    )
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--repo",
        default="/mnt/c/Users/chris/hornelore",
        help="Hornelore repo root (default: /mnt/c/Users/chris/hornelore)",
    )
    ap.add_argument(
        "--out-dir",
        default=None,
        help="Output directory (default: <repo>/docs/reports)",
    )
    args = ap.parse_args()

    repo = Path(args.repo)
    if not repo.exists():
        sys.exit(f"repo not found: {repo}")

    out_dir = Path(args.out_dir) if args.out_dir else (repo / "docs/reports")
    out_dir.mkdir(parents=True, exist_ok=True)

    report = audit(repo)

    stamp = dt.datetime.utcnow().strftime("%Y%m%d")
    json_path = out_dir / f"CANON_GAP_AUDIT_{stamp}.json"
    md_path = out_dir / f"CANON_GAP_AUDIT_{stamp}.md"

    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    # Console summary
    print(f"[canon-audit] wrote {json_path}")
    print(f"[canon-audit] wrote {md_path}")
    print("")
    print("Per-narrator summary:")
    for slug, nrep in report["narrators"].items():
        counts = nrep["classification_counts"]
        print(
            f"  {slug:<28} cases={nrep['cases_count']:>3}  "
            f"paths={nrep['unique_paths_referenced']:>3}  "
            f"POPULATED={counts.get('POPULATED', 0):>3}  "
            f"EMPTY={counts.get('EMPTY', 0):>3}  "
            f"MISSING={counts.get('MISSING_IN_CANON', 0):>3}"
        )


if __name__ == "__main__":
    main()
