#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, List

BAD_PATTERNS: Dict[str, re.Pattern] = {
    "no_false_name_confirmation": re.compile(r"Did I get that name right\?", re.I),
    "no_got_it_stub": re.compile(r"\bGot it\s+[—-]\s+.{1,90}\bWhat happened next\?", re.I | re.S),
    "no_meta_response_leak": re.compile(
        r"Here is a response|This response reflects|follows the rules|Let me capture a few key points|rich and evocative narrative",
        re.I,
    ),
    "no_titlecased_anchor_cascade": re.compile(r"You went from .{1,80} to .{1,80}, then .{1,160}What happened next\?", re.I | re.S),
    "response_not_fragmented": re.compile(r"│\s*(West St\.|St\.|Began\.)\s*$", re.I | re.M),
    "no_broken_code_mix": re.compile(r"\bTú\s+\w+|,\s*y\s+\w+.*\?|¿Qué pasó después\?", re.I),
    "no_seeded_fact_intake_question": re.compile(r"You were born in .{1,80}\?", re.I),
}

def scan_file(path: Path) -> Dict[str, int]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {name: len(rx.findall(text)) for name, rx in BAD_PATTERNS.items()}

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+", help="Report .txt/.md files to regrade")
    ap.add_argument("--out", default="docs/reports/boris_regrade_summary.md")
    args = ap.parse_args()

    rows: List[str] = []
    rows.append("# Boris Report Regrade Summary")
    rows.append("")
    rows.append("| Report | " + " | ".join(BAD_PATTERNS.keys()) + " |")
    rows.append("|---|" + "|".join(["---:"] * len(BAD_PATTERNS)) + "|")

    grand = {k: 0 for k in BAD_PATTERNS}
    for raw in args.paths:
        p = Path(raw)
        if not p.exists():
            continue
        counts = scan_file(p)
        for k, v in counts.items():
            grand[k] += v
        rows.append("| `" + str(p) + "` | " + " | ".join(str(counts[k]) for k in BAD_PATTERNS) + " |")

    rows.append("")
    rows.append("## Totals")
    rows.append("")
    for k, v in grand.items():
        rows.append(f"- {k}: {v}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(rows), encoding="utf-8")
    print(out)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
