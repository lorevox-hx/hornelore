#!/usr/bin/env python3
"""
Regrade existing harness reports under the hardened 16-row scorer.

BUG-HARNESS-SCORER-TOO-LENIENT-CONTENT-QUALITY-01 added 8 new content-
quality rows to scripts/harness_lib.py::score_chapter. This regrade
script lets us measure how many of the original "PASS" reports were
actually masking broken Lori output, without re-running the live
backend harnesses.

Usage:
  python3 scripts/regrade_harness_reports.py
  python3 scripts/regrade_harness_reports.py docs/reports/jake_*.txt

Reads each report .txt under docs/reports/ (or the explicit paths given),
parses out the verbatim Lori responses per chapter, and applies the new
scoring rows. Writes a regrade summary to:
  docs/reports/regrade_summary_<timestamp>.md

The regrade does NOT modify the original reports.
"""
from __future__ import annotations

import argparse
import glob
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

# Import the scorer + detection helpers from harness_lib
from harness_lib import (  # noqa: E402
    _detect_anchor_cascade,
    _detect_false_name_confirm,
    _detect_fragment,
    _detect_got_it_stub,
    _detect_meta_leak,
    _detect_titlecase_phrase_as_name,
)


# ── Report parser ────────────────────────────────────────────────────────────


CHAPTER_HEADER_RE = re.compile(
    r"^─{20,}\s*\n"
    r"^CHAPTER — (.+?)\s*\n"
    r"^─{20,}\s*\n",
    re.MULTILINE,
)

LORI_RESPONSE_BLOCK_RE = re.compile(
    r"Lori response(?: \(verbatim\))?:\s*\n"
    r"\s*┌─+\s*\n"
    r"((?:\s*│.*\n)+)"
    r"\s*└─+",
    re.MULTILINE,
)


@dataclass
class ParsedChapter:
    chapter_label: str
    lori_response: str


def parse_report(report_path: Path) -> List[ParsedChapter]:
    """Parse a harness report into chapter blocks + Lori responses."""
    try:
        content = report_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        print(f"  ✗ Cannot read {report_path}: {e}", file=sys.stderr)
        return []

    chapters: List[ParsedChapter] = []
    # Find all chapter headers
    headers = list(CHAPTER_HEADER_RE.finditer(content))
    if not headers:
        return []

    for i, header in enumerate(headers):
        chapter_label = header.group(1).strip()
        # Search Lori response in the block between this header and the next
        end = headers[i + 1].start() if i + 1 < len(headers) else len(content)
        block = content[header.end():end]
        m = LORI_RESPONSE_BLOCK_RE.search(block)
        if not m:
            continue
        raw = m.group(1)
        # Strip the leading "  │ " prefix from each line
        lines = []
        for ln in raw.splitlines():
            stripped = ln.lstrip()
            if stripped.startswith("│"):
                stripped = stripped[1:].lstrip()
            lines.append(stripped)
        lori_response = "\n".join(lines).strip()
        chapters.append(ParsedChapter(chapter_label, lori_response))
    return chapters


# ── Regrade ──────────────────────────────────────────────────────────────────


@dataclass
class RegradeRow:
    report_name: str
    chapter_label: str
    lori_response_preview: str
    no_false_name_confirmation: str
    no_got_it_stub: str
    no_titlecase_phrase_as_name: str
    response_not_fragmented: str
    no_meta_response_leak: str
    no_titlecased_anchor_cascade: str
    failed_rows: List[str]
    offenders: Dict[str, Optional[str]]


def regrade_chapter(report_name: str, parsed: ParsedChapter) -> RegradeRow:
    text = parsed.lori_response
    preview = (text[:120] + "…") if len(text) > 120 else text

    false_name = _detect_false_name_confirm(text)
    got_it = _detect_got_it_stub(text)
    titlecase_offender = _detect_titlecase_phrase_as_name(text)
    fragmented = _detect_fragment(text)
    meta_offender = _detect_meta_leak(text)
    cascade = _detect_anchor_cascade(text)

    failed: List[str] = []
    if false_name:
        failed.append("no_false_name_confirmation")
    if got_it:
        failed.append("no_got_it_stub")
    if titlecase_offender:
        failed.append("no_titlecase_phrase_as_name")
    if fragmented:
        failed.append("response_not_fragmented")
    if meta_offender:
        failed.append("no_meta_response_leak")
    if cascade:
        failed.append("no_titlecased_anchor_cascade")

    return RegradeRow(
        report_name=report_name,
        chapter_label=parsed.chapter_label,
        lori_response_preview=preview,
        no_false_name_confirmation="FAIL" if false_name else "PASS",
        no_got_it_stub="FAIL" if got_it else "PASS",
        no_titlecase_phrase_as_name="FAIL" if titlecase_offender else "PASS",
        response_not_fragmented="FAIL" if fragmented else "PASS",
        no_meta_response_leak="FAIL" if meta_offender else "PASS",
        no_titlecased_anchor_cascade="FAIL" if cascade else "PASS",
        failed_rows=failed,
        offenders={
            "titlecase_phrase": titlecase_offender,
            "meta_leak": meta_offender,
        },
    )


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Regrade harness reports under the hardened scorer."
    )
    parser.add_argument(
        "paths", nargs="*",
        help="Report paths or globs. Defaults to docs/reports/*.txt.",
    )
    args = parser.parse_args()

    if args.paths:
        report_paths: List[Path] = []
        for pat in args.paths:
            report_paths.extend(Path(p) for p in glob.glob(pat))
    else:
        reports_dir = REPO_ROOT / "docs" / "reports"
        report_paths = sorted(reports_dir.glob("*.txt"))

    if not report_paths:
        print("No report files found.", file=sys.stderr)
        return 1

    all_rows: List[RegradeRow] = []
    total_chapters = 0
    chapters_with_failures = 0

    for path in report_paths:
        chapters = parse_report(path)
        if not chapters:
            continue
        for ch in chapters:
            row = regrade_chapter(path.name, ch)
            all_rows.append(row)
            total_chapters += 1
            if row.failed_rows:
                chapters_with_failures += 1

    # Write summary
    ts = time.strftime("%Y%m%d_%H%M%S")
    summary_path = REPO_ROOT / "docs" / "reports" / f"regrade_summary_{ts}.md"
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    out: List[str] = []
    out.append(f"# Regrade Summary — {time.strftime('%Y-%m-%d %H:%M:%S')}")
    out.append("")
    out.append(f"- Reports regraded: {len(report_paths)}")
    out.append(f"- Chapters scored: {total_chapters}")
    out.append(f"- Chapters with ≥1 new-row failure: {chapters_with_failures}")
    pct = (chapters_with_failures / max(1, total_chapters)) * 100
    out.append(f"- Failure rate under hardened scorer: {pct:.1f}%")
    out.append("")
    out.append("## Per-chapter regrade")
    out.append("")
    for row in all_rows:
        marker = "✗" if row.failed_rows else "✓"
        out.append(f"### {marker} `{row.report_name}` — {row.chapter_label}")
        out.append("")
        out.append(f"  Lori response: `{row.lori_response_preview}`")
        out.append("")
        if row.failed_rows:
            out.append(f"  FAILED rows: {', '.join(row.failed_rows)}")
            for k, v in row.offenders.items():
                if v:
                    out.append(f"    - {k}: {v!r}")
        else:
            out.append("  All new content-quality rows PASS.")
        out.append("")
    summary_path.write_text("\n".join(out), encoding="utf-8")
    print(f"Regrade summary written to: {summary_path}")
    print(f"Chapters with failures: {chapters_with_failures}/{total_chapters} ({pct:.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
