#!/usr/bin/env python3
"""
Dump every eval case grouped by narrator into readable markdown so Chris can
scan loriPrompt + narratorReply + expectedFields side-by-side and flag
fact-vs-fiction against biobuilder canon.

Scope: kent-james-horne, janice-josephine-horne, christopher-todd-horne.
(Shatner and dolly are trainer-only, excluded.)

Outputs (one file per narrator):
    docs/reports/EVAL_CASES_kent-james-horne_<YYYYMMDD>.md
    docs/reports/EVAL_CASES_janice-josephine-horne_<YYYYMMDD>.md
    docs/reports/EVAL_CASES_christopher-todd-horne_<YYYYMMDD>.md

Usage:
    python3 scripts/dump_cases_per_narrator.py
    python3 scripts/dump_cases_per_narrator.py --repo /mnt/c/Users/chris/hornelore
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

SCOPED_NARRATORS = (
    "kent-james-horne",
    "janice-josephine-horne",
    "christopher-todd-horne",
)


def _q(s: str) -> str:
    """Escape pipe characters + collapse newlines for inline markdown cells."""
    if not s:
        return ""
    return str(s).replace("|", "\\|").replace("\r\n", "\n")


def _fmt_truth_zones(tz: Dict[str, Any]) -> str:
    if not tz:
        return "_none_"
    buckets = defaultdict(list)
    for path, z in tz.items():
        zone = (z or {}).get("zone", "?")
        expected = (z or {}).get("expected")
        note = (z or {}).get("note")
        tag = path
        if expected:
            tag += f' = "{expected}"'
        if note:
            tag += f"  _({note})_"
        buckets[zone].append(tag)
    lines = []
    for zone in ("must_extract", "may_extract", "should_ignore", "must_not_write"):
        if zone in buckets:
            lines.append(f"- **{zone}**")
            for item in buckets[zone]:
                lines.append(f"    - `{item}`")
    # Any zones we didn't explicitly list
    for zone, items in buckets.items():
        if zone in ("must_extract", "may_extract", "should_ignore", "must_not_write"):
            continue
        lines.append(f"- **{zone}**")
        for item in items:
            lines.append(f"    - `{item}`")
    return "\n".join(lines) if lines else "_none_"


def _fmt_expected_fields(ef: Dict[str, Any]) -> str:
    if not ef:
        return "_none_"
    lines = []
    for k, v in ef.items():
        lines.append(f'- `{k}` = "{_q(str(v))}"')
    return "\n".join(lines)


def _fmt_forbidden(fb: List[str]) -> str:
    if not fb:
        return "_none_"
    return ", ".join(f"`{p}`" for p in fb)


def render_case(c: Dict[str, Any]) -> str:
    out: List[str] = []
    cid = c.get("id", "?")
    phase = c.get("phase", "")
    sub = c.get("subTopic", "")
    qtype = c.get("questionType", "")
    case_type = c.get("caseType", "")
    style = c.get("oralHistoryStyle", "")
    cex = c.get("currentExtractorExpected")

    out.append(f"### {cid} — {phase} / {sub}")
    out.append("")
    meta_bits = []
    if qtype:
        meta_bits.append(f"questionType: {qtype}")
    if case_type:
        meta_bits.append(f"caseType: {case_type}")
    if style:
        meta_bits.append(f"style: {style}")
    if cex is not None:
        meta_bits.append(f"currentExtractorExpected: {cex}")
    if meta_bits:
        out.append("  ·  ".join(meta_bits))
        out.append("")

    # Prior context (follow-ups)
    pc = c.get("priorContext")
    if pc:
        out.append("**Prior context:**")
        out.append("")
        out.append(f"> {_q(pc)}")
        out.append("")

    # Lori asks
    lp = c.get("loriPrompt") or c.get("questionBankAnchor") or ""
    out.append("**Lori asks:**")
    out.append("")
    out.append(f"> {_q(lp)}")
    out.append("")

    # Narrator replies
    nr = c.get("narratorReply", "")
    out.append("**Narrator replies:**")
    out.append("")
    out.append(f"> {_q(nr)}")
    out.append("")

    # Expected fields
    out.append("**Expected fields:**")
    out.append("")
    out.append(_fmt_expected_fields(c.get("expectedFields") or {}))
    out.append("")

    # extractPriority
    ep = c.get("extractPriority") or []
    if ep:
        out.append("**extractPriority:** " + ", ".join(f"`{p}`" for p in ep))
        out.append("")

    # Forbidden / truth zones
    fb = c.get("forbiddenFields") or []
    if fb:
        out.append("**Forbidden fields:** " + _fmt_forbidden(fb))
        out.append("")

    tz = c.get("truthZones") or {}
    if tz:
        out.append("**Truth zones:**")
        out.append("")
        out.append(_fmt_truth_zones(tz))
        out.append("")

    # scoringNotes (often the most useful fact-check hint)
    sn = c.get("scoringNotes")
    if sn:
        out.append(f"_Scoring note: {_q(sn)}_")
        out.append("")

    return "\n".join(out)


def render_narrator(slug: str, cases: List[Dict[str, Any]]) -> str:
    out: List[str] = []
    out.append(f"# Eval Cases — {slug}")
    out.append("")
    out.append(f"Generated: {dt.datetime.utcnow().isoformat()}Z")
    out.append("")
    out.append(f"Total cases for this narrator: **{len(cases)}**")
    out.append("")
    out.append(
        "Use this as a fact-check pass. For each case, read `Lori asks`, "
        "`Narrator replies`, and `Expected fields`, then mark:"
    )
    out.append("")
    out.append("- **FACT** — narratorReply matches biobuilder canon")
    out.append("- **FICTION** — narratorReply contradicts canon or invents facts not in canon")
    out.append("- **PARTIAL** — some of the reply is canon-grounded, some is invented")
    out.append("- **CANON-GAP** — reply is plausible but canon is silent; needs canon entry")
    out.append("")
    out.append("---")
    out.append("")

    # Table of contents
    out.append("## Index")
    out.append("")
    by_phase: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for c in cases:
        by_phase[c.get("phase", "?")].append(c)
    for phase in sorted(by_phase):
        out.append(f"- **{phase}** ({len(by_phase[phase])})")
        for c in by_phase[phase]:
            cid = c.get("id", "?")
            sub = c.get("subTopic", "")
            out.append(f"    - [{cid} — {sub}](#{cid.replace('_','-')}--{phase}--{sub})")
    out.append("")
    out.append("---")
    out.append("")

    # Sort cases by id for stable reading order
    for c in sorted(cases, key=lambda x: x.get("id", "")):
        out.append(render_case(c))
        out.append("---")
        out.append("")

    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--repo",
        default="/mnt/c/Users/chris/hornelore",
        help="Hornelore repo root",
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

    cases_path = repo / "data/qa/question_bank_extraction_cases.json"
    if not cases_path.exists():
        sys.exit(f"cases file not found: {cases_path}")
    cases = json.loads(cases_path.read_text(encoding="utf-8"))["cases"]

    out_dir = Path(args.out_dir) if args.out_dir else (repo / "docs/reports")
    out_dir.mkdir(parents=True, exist_ok=True)

    stamp = dt.datetime.utcnow().strftime("%Y%m%d")

    summary: List[str] = []
    for slug in SCOPED_NARRATORS:
        nar_cases = [c for c in cases if c.get("narratorId") == slug]
        if not nar_cases:
            print(f"[dump] no cases for {slug} — skipping")
            continue
        md = render_narrator(slug, nar_cases)
        out_path = out_dir / f"EVAL_CASES_{slug}_{stamp}.md"
        out_path.write_text(md, encoding="utf-8")
        print(f"[dump] wrote {out_path}  ({len(nar_cases)} cases)")
        summary.append((slug, len(nar_cases), out_path))

    print("")
    print("Summary:")
    for slug, n, path in summary:
        print(f"  {slug:<28} {n:>3} cases  →  {path}")


if __name__ == "__main__":
    main()
