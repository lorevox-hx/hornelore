#!/usr/bin/env python3
"""In-process wire verification for WO-LORI-FACTUAL-CHAIN-CAPTURE-01
Commit B (Phase 2+3+4).

Verifies that:
  1. build_factual_chain_followup_context produces a composer_directive
     for the Kent canary turn AND escalates when narrator meta-feedback
     rejects a sensory probe in the prior assistant turn.
  2. compose_system_prompt injects a [FACTUAL_CHAIN_DIRECTIVE] block
     when runtime71 carries factual_chain_directive — and does NOT
     inject when the key is absent / empty.
  3. The story_candidates table carries the chain_meta_json column
     (migration 0014_story_candidates_chain_meta.sql applied).

No stack required. No DB writes. Pure in-process imports + a single
PRAGMA call.

Usage:
    cd /mnt/c/Users/chris/hornelore
    .venv-gpu/bin/python scripts/verify_factual_chain_wire.py

Exit code 0 = GREEN, 1 = RED.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from typing import List, Tuple


REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_CODE = REPO_ROOT / "server" / "code"
sys.path.insert(0, str(SERVER_CODE))


def _ok(name: str) -> Tuple[bool, str]:
    return True, f"[PASS] {name}"


def _fail(name: str, msg: str) -> Tuple[bool, str]:
    return False, f"[FAIL] {name}: {msg}"


def verify_classifier_directive() -> Tuple[bool, str]:
    """Phase 2/3 source: build_factual_chain_followup_context."""
    try:
        from api.services.factual_chain_capture import (
            build_factual_chain_followup_context,
        )
    except Exception as exc:
        return _fail("import factual_chain_capture", str(exc))

    kent = (
        "They took us from Stanley to Fargo for the exam. "
        "I got the top score, and then they gave us meal tickets "
        "and sent us west."
    )
    # No prior assistant turn — chain-only directive.
    chain_only = build_factual_chain_followup_context(kent, prior_turns=[])
    if not chain_only.get("is_factual_chain"):
        return _fail("kent chain detected", repr(chain_only))
    directive = (chain_only.get("composer_directive") or "").lower()
    if "factual chain" not in directive:
        return _fail("composer_directive mentions factual chain", repr(directive))

    # Meta-feedback escalation — prior assistant asked a sensory probe;
    # narrator pushes back. Directive should add the rejection line.
    prior = [
        {"role": "user", "content": kent},
        {
            "role": "assistant",
            "content": "What was the scenery like on the way to Fargo?",
        },
    ]
    push_back = (
        "Not the scenery — I want to talk about the test and the score."
    )
    ctx = build_factual_chain_followup_context(push_back, prior_turns=prior)
    meta = ctx.get("meta_feedback") or {}
    if not meta.get("is_meta_feedback"):
        return _fail("meta_feedback detected", repr(ctx))
    if meta.get("last_rejected_probe_type") != "sensory":
        return _fail("rejected probe type sensory", repr(meta))
    directive_meta = (ctx.get("composer_directive") or "").lower()
    if "rejected" not in directive_meta or "sensory" not in directive_meta:
        return _fail(
            "directive includes rejection clause",
            repr(directive_meta),
        )

    return _ok("classifier directive surface (kent + meta-feedback)")


def verify_composer_injection() -> Tuple[bool, str]:
    """Phase 2 sink: compose_system_prompt with runtime71 directive."""
    try:
        from api.prompt_composer import compose_system_prompt
    except Exception as exc:
        return _fail("import compose_system_prompt", str(exc))

    runtime_with = {
        "current_pass": "pass1",
        "current_era": "earliest_years",
        "current_mode": "open",
        "factual_chain_directive": (
            "The narrator is giving a factual chain. Do not pivot to "
            "scenery, sounds, smells, atmosphere, or generalized feeling."
        ),
    }
    try:
        out_with = compose_system_prompt(
            "wire_verify_with",
            ui_system=None,
            user_text="placeholder",
            runtime71=runtime_with,
        )
    except Exception as exc:
        return _fail("compose with directive", str(exc))

    if "[FACTUAL_CHAIN_DIRECTIVE]" not in out_with:
        return _fail(
            "[FACTUAL_CHAIN_DIRECTIVE] block present",
            "block missing from composed system prompt",
        )
    if "Do not pivot to scenery" not in out_with:
        return _fail(
            "directive body present in output",
            "directive text not found in composed system prompt",
        )

    runtime_without = dict(runtime_with)
    runtime_without.pop("factual_chain_directive")
    try:
        out_without = compose_system_prompt(
            "wire_verify_without",
            ui_system=None,
            user_text="placeholder",
            runtime71=runtime_without,
        )
    except Exception as exc:
        return _fail("compose without directive", str(exc))

    if "[FACTUAL_CHAIN_DIRECTIVE]" in out_without:
        return _fail(
            "[FACTUAL_CHAIN_DIRECTIVE] absent when key missing",
            "block leaked into composed system prompt",
        )

    return _ok("compose_system_prompt directive injection")


def verify_db_column() -> Tuple[bool, str]:
    """Phase 4 schema: chain_meta_json column on story_candidates."""
    data_dir = os.getenv("DATA_DIR", "/mnt/c/hornelore_data")
    db_name = os.getenv("DB_NAME", "hornelore.sqlite3")
    db_path = Path(data_dir) / db_name
    if not db_path.exists():
        return _fail(
            "story_candidates schema check",
            f"db file not found at {db_path} — stack may not have "
            f"been started since migration landed",
        )

    try:
        con = sqlite3.connect(str(db_path))
        try:
            cur = con.execute("PRAGMA table_info(story_candidates);")
            cols = {row[1] for row in cur.fetchall()}
        finally:
            con.close()
    except Exception as exc:
        return _fail("story_candidates PRAGMA", str(exc))

    if "chain_meta_json" not in cols:
        return _fail(
            "chain_meta_json column present",
            f"columns={sorted(cols)} — migration 0014 may not have been "
            f"applied (cycle the stack to apply pending migrations)",
        )

    return _ok("story_candidates.chain_meta_json present")


def main() -> int:
    print("=" * 70)
    print("WO-LORI-FACTUAL-CHAIN-CAPTURE-01 Commit B — wire verification")
    print("=" * 70)

    results: List[Tuple[bool, str]] = [
        verify_classifier_directive(),
        verify_composer_injection(),
        verify_db_column(),
    ]

    all_pass = True
    for passed, line in results:
        if not passed:
            all_pass = False
        print(line)

    print("=" * 70)
    pass_count = sum(1 for r, _ in results if r)
    total = len(results)
    if all_pass:
        print(f"GREEN factual_chain_wire  ({pass_count}/{total})")
        return 0
    print(f"RED factual_chain_wire  ({pass_count}/{total})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
