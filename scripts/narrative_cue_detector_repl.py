#!/usr/bin/env python3
"""WO-NARRATIVE-CUE-LIBRARY-01 Phase 2 — CLI debug runner for the
narrative_cue_detector.

Mirrors the shape of scripts/utterance_frame_repl.py.

Usage:
    # Inline text
    ./scripts/narrative_cue_detector_repl.py --text "My father worked the field."

    # File
    ./scripts/narrative_cue_detector_repl.py --file path/to/utterance.txt

    # Stdin
    echo "Mother kept seeds in her apron." | ./scripts/narrative_cue_detector_repl.py

    # Walk every case in the eval pack
    ./scripts/narrative_cue_detector_repl.py --eval

    # With section context
    ./scripts/narrative_cue_detector_repl.py --text "Father had calloused hands." --section parents

Output is JSON to stdout: detection.to_dict() per input. Eval mode
prints per-case rows + a final pass-rate footer.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api.services.narrative_cue_detector import (  # noqa: E402
    detect_cues,
)


def _emit(text: str, section: str | None = None) -> None:
    result = detect_cues(text, current_section=section)
    print(json.dumps(result.to_dict(), indent=2))


def _walk_eval_pack() -> int:
    pack_path = _REPO_ROOT / "data" / "qa" / "lori_narrative_cue_eval.json"
    if not pack_path.is_file():
        print(f"ERROR: eval pack not found at {pack_path}", file=sys.stderr)
        return 1

    with pack_path.open(encoding="utf-8") as f:
        pack = json.load(f)

    cases = pack.get("cases", [])
    hits = 0
    total = 0
    rows = []
    for case in cases:
        case_id = case.get("id", "?")
        user_text = case.get("user_text", "")
        section = case.get("current_section")
        expected = case.get("expected_cue_type")
        if not user_text or not expected:
            continue

        total += 1
        result = detect_cues(user_text, current_section=section)
        actual_type = result.top_cue.cue_type if result.top_cue else None
        actual_score = result.top_cue.score if result.top_cue else 0
        actual_triggers = list(result.top_cue.trigger_matches) if result.top_cue else []
        ok = (actual_type == expected)
        if ok:
            hits += 1
        rows.append({
            "id": case_id,
            "ok": ok,
            "expected": expected,
            "actual": actual_type,
            "score": actual_score,
            "triggers": actual_triggers,
        })

    rate = (hits / total * 100.0) if total else 0.0
    print(json.dumps({
        "summary": {
            "cases": total,
            "hits": hits,
            "misses": total - hits,
            "pass_rate_pct": round(rate, 1),
        },
        "rows": rows,
    }, indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="narrative_cue_detector debug runner")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--text", type=str, help="inline narrator text to score")
    g.add_argument("--file", type=str, help="path to a file with narrator text")
    g.add_argument("--eval", action="store_true",
                   help="walk lori_narrative_cue_eval.json and print pass rate")
    p.add_argument("--section", type=str, default=None,
                   help="optional current_section context (e.g. parents)")
    args = p.parse_args()

    if args.eval:
        return _walk_eval_pack()

    if args.text is not None:
        _emit(args.text, section=args.section)
        return 0

    if args.file is not None:
        text = Path(args.file).read_text(encoding="utf-8")
        _emit(text, section=args.section)
        return 0

    # Stdin fallback
    if not sys.stdin.isatty():
        text = sys.stdin.read()
        if text.strip():
            _emit(text, section=args.section)
            return 0

    p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
