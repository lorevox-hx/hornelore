#!/usr/bin/env python3
"""READ ONLY. Characterise dangling turn references inside ONE package.

WO-LOREVOX-PORTABLE-NARRATOR-01, reopened 2026-09-12. The two-origin comparison
found that the laptop's Christopher package carries `turn_extraction_ledger` rows
whose `turn_key` ('turnrow:<turns.id>') names turns the package does not contain.
The old exporter accepted it because that encoded TEXT relationship sat outside the
§30 closure model.

This tool answers WHAT THE PACKAGE PROVES, and says plainly what it cannot prove.
It opens the zip read-only, writes nothing, and never touches a database.

**It does not decide what should happen.** A reference pointing outside the
narrator-owned closure does NOT mean the missing turn should be imported: only the
ownership declaration decides what belongs to a narrator (WO §30). The candidate
explanations — an ownership/declaration gap, stale derived ledger rows, legacy
residue, or another defect — are distinguished by evidence, and some of that
evidence is not in the package.

USAGE
    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python scripts/dangling_turn_reference_report.py \\
        --package .runtime/two_origin/laptop/Christopher_Todd_Horne_a2f360689b58.lorevox.zip \\
        --out .runtime/two_origin/reports
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

RECORDS = "data/records/"
TURNROW = re.compile(r"^turnrow:(\d+)$")


def load(path: Path) -> Dict[str, Any]:
    out = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
           "manifest": {}, "records": {}}
    with zipfile.ZipFile(path) as zf:
        if "lorevox-manifest.json" in zf.namelist():
            out["manifest"] = json.loads(zf.read("lorevox-manifest.json").decode("utf-8"))
        for n in zf.namelist():
            if n.startswith(RECORDS) and n.endswith(".jsonl"):
                t = n[len(RECORDS):-6]
                out["records"][t] = [json.loads(l) for l in
                                     zf.read(n).decode("utf-8").splitlines() if l.strip()]
    return out


def _turn_ids(pkg) -> set:
    return {int(r["id"]) for r in pkg["records"].get("turns", [])
            if str(r.get("id", "")).lstrip("-").isdigit()}


def _json_turn_key(raw) -> Optional[int]:
    try:
        blob = json.loads(raw or "{}")
    except Exception:
        return None
    m = TURNROW.match(str((blob or {}).get("turn_key", "")))
    return int(m.group(1)) if m else None


def characterise(pkg: Dict[str, Any]) -> Dict[str, Any]:
    turns = _turn_ids(pkg)
    turns_by_id = {int(r["id"]): r for r in pkg["records"].get("turns", [])
                   if str(r.get("id", "")).lstrip("-").isdigit()}
    sessions = {r.get("conv_id"): r for r in pkg["records"].get("sessions", [])}

    ledger = pkg["records"].get("turn_extraction_ledger", [])
    results = pkg["records"].get("turn_extraction_results", [])
    facts = pkg["records"].get("bio_facts", [])
    stories = pkg["records"].get("story_candidates", [])

    results_by_key: Dict[str, List[Dict]] = defaultdict(list)
    for r in results:
        results_by_key[str(r.get("turn_key", ""))].append(r)
    results_by_ledger: Dict[Any, List[Dict]] = defaultdict(list)
    for r in results:
        results_by_ledger[r.get("ledger_id")].append(r)

    rows: List[Dict[str, Any]] = []
    for led in ledger:
        key = str(led.get("turn_key", ""))
        m = TURNROW.match(key)
        if not m:
            continue
        tid = int(m.group(1))
        if tid in turns:
            continue                                   # resolves; not our subject
        res = results_by_ledger.get(led.get("id"), []) + results_by_key.get(key, [])
        # every OTHER place in this package that names the same missing turn
        also = {
            "bio_facts.source": [f.get("id") for f in facts if _json_turn_key(f.get("source")) == tid],
            "turn_extraction_results.turn_key": [r.get("id") for r in results_by_key.get(key, [])],
            "story_candidates.source_user_turn_row_id":
                [s.get("id") for s in stories if s.get("source_user_turn_row_id") == tid],
            "story_candidates.completed_assistant_turn_row_id":
                [s.get("id") for s in stories if s.get("completed_assistant_turn_row_id") == tid],
            "trip_turn_links": [t.get("id") for t in pkg["records"].get("trip_turn_links", [])
                                if tid in (t.get("user_turn_row_id"), t.get("assistant_turn_row_id"))],
        }
        conv = led.get("conv_id") or led.get("session_id") or ""
        rows.append({
            "ledger_row_id": led.get("id"),
            "narrator_id": led.get("narrator_id"),
            "turn_key": key,
            "parsed_turns_id": tid,
            "conv_or_session_on_ledger_row": conv,
            "that_conversation_is_in_the_package": bool(conv) and conv in sessions,
            "ledger_status": led.get("status") or led.get("state") or "",
            "ledger_created_at": led.get("created_at") or led.get("claimed_at") or "",
            "has_extraction_result_row": bool(res),
            "result_row_ids": [r.get("id") for r in res],
            "also_referenced_by": {k: v for k, v in also.items() if v},
            "id_appears_elsewhere_in_package": any(also.values()),
        })

    by_turn = Counter(r["parsed_turns_id"] for r in rows)
    neighbours = {}
    if rows and turns:
        lo, hi = min(turns), max(turns)
        for tid in sorted(by_turn):
            neighbours[tid] = {
                "packaged_turn_id_range": [lo, hi],
                "inside_packaged_range": lo <= tid <= hi,
                "nearest_packaged_below": max([t for t in turns if t < tid], default=None),
                "nearest_packaged_above": min([t for t in turns if t > tid], default=None),
            }

    return {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "read_only": True,
        "package": {"path": pkg["path"], "sha256": pkg["sha256"],
                    "package_id": pkg["manifest"].get("package_id"),
                    "narrator_id": pkg["manifest"].get("narrator_id"),
                    "narrator_display_name": pkg["manifest"].get("narrator_display_name"),
                    "created_at": pkg["manifest"].get("created_at"),
                    "source_commit": pkg["manifest"].get("source_commit")},
        "packaged_turns": len(turns),
        "ledger_rows": len(ledger),
        "ledger_rows_with_turnrow_key": sum(1 for l in ledger if TURNROW.match(str(l.get("turn_key", "")))),
        "dangling_count": len(rows),
        "distinct_missing_turn_ids": len(by_turn),
        "several_rows_per_missing_turn": {k: v for k, v in by_turn.items() if v > 1},
        "missing_turn_id_neighbourhood": neighbours,
        "rows": rows,
        "what_this_package_cannot_prove": [
            "Whether the referenced turn ever existed in the laptop's live database. A "
            "package contains what the exporter selected; a row absent from it may never "
            "have existed, may have been deleted, or may exist and be owned by someone "
            "else — the package cannot distinguish these.",
            "Whether the missing turns belong to this narrator. Only the ownership "
            "declaration decides that (WO §30), and it runs against a database, not a zip.",
            "Whether the ledger rows are stale. The ledger records extraction ATTEMPTS; "
            "an attempt can outlive the turn it was about if the turn was later removed.",
        ],
        "candidate_explanations_not_yet_distinguished": [
            "ownership/declaration gap — the turns exist on the laptop and are the "
            "narrator's, but the declaration did not select them",
            "stale derived ledger rows — the turns were deleted and the ledger kept the claim",
            "legacy residue — rows predating a migration, like the 9 residue sessions §36.5 found",
            "another defect",
        ],
        "how_to_distinguish": (
            "One read-only query against the LAPTOP's live database: do rows with these "
            "turns.id values exist, and if so which conv_id do they carry and who owns that "
            "conversation under the declaration? That answer selects among the candidates "
            "above. It cannot be obtained from any package."
        ),
    }


def render(rep: Dict[str, Any]) -> str:
    p = rep["package"]
    L = [f"# Dangling turn references — {p['narrator_display_name']}", "",
         f"*Read-only. Generated {rep['generated_at']}. The package was not modified.*", "",
         f"- package `{p['package_id']}` · sha256 `{p['sha256'][:16]}…`",
         f"- exported {p['created_at']} from commit `{p['source_commit']}`",
         f"- packaged turns: **{rep['packaged_turns']}**",
         f"- extraction-ledger rows: {rep['ledger_rows']} "
         f"({rep['ledger_rows_with_turnrow_key']} carry a `turnrow:` key)",
         f"- **dangling: {rep['dangling_count']}** across "
         f"**{rep['distinct_missing_turn_ids']}** distinct missing turn ids", ""]
    if rep["several_rows_per_missing_turn"]:
        L += [f"- several ledger rows point at the same missing turn: "
              f"`{rep['several_rows_per_missing_turn']}`", ""]
    L += ["## The rows", "",
          "| ledger id | turn_key | missing turns.id | conv on row | conv in package | result row? | also referenced by |",
          "|---|---|---|---|---|---|---|"]
    for r in rep["rows"]:
        also = ", ".join(f"{k.split('.')[0]}×{len(v)}" for k, v in r["also_referenced_by"].items()) or "—"
        L.append(f"| {r['ledger_row_id']} | `{r['turn_key']}` | {r['parsed_turns_id']} | "
                 f"{r['conv_or_session_on_ledger_row'] or '—'} | "
                 f"{'yes' if r['that_conversation_is_in_the_package'] else 'no'} | "
                 f"{'yes' if r['has_extraction_result_row'] else 'no'} | {also} |")
    L += ["", "## Where the missing ids sit relative to packaged turns", ""]
    for tid, n in rep["missing_turn_id_neighbourhood"].items():
        L.append(f"- `{tid}` — packaged range {n['packaged_turn_id_range']}, "
                 f"inside range: {n['inside_packaged_range']}, "
                 f"nearest packaged below/above: {n['nearest_packaged_below']}/{n['nearest_packaged_above']}")
    L += ["", "## What this package CANNOT prove", ""]
    L += [f"- {s}" for s in rep["what_this_package_cannot_prove"]]
    L += ["", "## Candidate explanations, not yet distinguished", ""]
    L += [f"- {s}" for s in rep["candidate_explanations_not_yet_distinguished"]]
    L += ["", "## How to distinguish them", "", rep["how_to_distinguish"], "",
          "*No conclusion is drawn here. A reference pointing outside the narrator-owned",
          "closure does not mean the missing turn should be imported — only the ownership",
          "declaration decides what belongs to a narrator (WO §30).*"]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--package", required=True)
    ap.add_argument("--out", default=".runtime/two_origin/reports")
    args = ap.parse_args(argv)

    path = Path(args.package)
    pkg = load(path)
    rep = characterise(pkg)
    md = render(rep)

    ts = _dt.datetime.now().strftime("%Y%m%dT%H%M%SZ")
    name = (rep["package"]["narrator_display_name"] or "narrator").replace(" ", "_")
    outdir = Path(args.out) / f"dangling-{name}-{ts}"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    (outdir / "summary.md").write_text(md + "\n", encoding="utf-8")

    after = hashlib.sha256(path.read_bytes()).hexdigest()
    print(md)
    print(f"\nwritten: {outdir}")
    print(f"read-only proof: package byte-identical after the run = {after == pkg['sha256']}")
    return 0 if after == pkg["sha256"] else 3


if __name__ == "__main__":
    sys.exit(main())
