#!/usr/bin/env python3
"""WO-EX-UTTERANCE-FRAME-01 Phase 0-2 — CLI debug runner.

Reads narrator text from --text, --file, or stdin and prints the
Story Clause Map JSON to stdout. No flags, no behavior change, no
side effects on the running stack.

Usage:
    # One-shot via argv
    ./scripts/utterance_frame_repl.py --text "My dad was born in Stanley."

    # One-shot from a file
    ./scripts/utterance_frame_repl.py --file path/to/turn.txt

    # Pipe in
    echo "My dad was born in Stanley." | ./scripts/utterance_frame_repl.py

    # Run all fixture cases
    ./scripts/utterance_frame_repl.py --fixtures

This script exists so Chris (or future agents) can quickly probe
how the frame parses a given utterance without standing the stack
up. The frame is pure deterministic — output is the same as what
chat_ws will log when HORNELORE_UTTERANCE_FRAME_LOG=1.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _add_server_code_to_path() -> None:
    """Add server/code/ to sys.path so `import api.services.*` works
    regardless of where this script is invoked from."""
    here = Path(__file__).resolve()
    repo_root = here.parent.parent
    server_code = repo_root / "server" / "code"
    if str(server_code) not in sys.path:
        sys.path.insert(0, str(server_code))


def _read_text(args: argparse.Namespace) -> str:
    if args.text is not None:
        return args.text
    if args.file is not None:
        return Path(args.file).read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


def _run_one(text: str, label: str | None = None) -> None:
    from api.services.utterance_frame import build_frame  # type: ignore

    frame = build_frame(text)
    payload = {
        "label": label,
        "input": text,
        "frame": frame.to_dict(),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _run_fixtures() -> int:
    here = Path(__file__).resolve()
    repo_root = here.parent.parent
    fixtures_path = repo_root / "tests" / "fixtures" / "utterance_frame_cases.json"
    if not fixtures_path.is_file():
        print(f"fixture file missing: {fixtures_path}", file=sys.stderr)
        return 2
    with fixtures_path.open(encoding="utf-8") as fp:
        data = json.load(fp)
    for case in data.get("cases", []):
        print("=" * 72)
        _run_one(case["narrator_text"], label=case.get("id"))
    return 0


def main(argv: list[str] | None = None) -> int:
    _add_server_code_to_path()

    parser = argparse.ArgumentParser(
        description="Inspect the Narrator Utterance Frame for arbitrary text.",
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--text", help="Inline narrator text to parse.")
    src.add_argument("--file", help="Path to a file containing narrator text.")
    src.add_argument(
        "--fixtures",
        action="store_true",
        help="Run every fixture in tests/fixtures/utterance_frame_cases.json.",
    )
    args = parser.parse_args(argv)

    if args.fixtures:
        return _run_fixtures()

    text = _read_text(args)
    if not text.strip():
        parser.error(
            "no input — pass --text, --file, --fixtures, or pipe text on stdin"
        )

    _run_one(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
