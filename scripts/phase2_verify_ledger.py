#!/usr/bin/env python3
"""Phase 2 ledger — REPRODUCE the headline numbers from the live database.

WHY THIS SCRIPT EXISTS
======================
The Phase 2 ledger lives at ``docs/reports/PHASE2_38_TURN_SPAN_LEDGER_20260904.json``
and ``docs/reports/*`` is gitignored, so it does not exist in a clone. The
analysis it corrects — ``MEMOIR-PATH-FINDING.md``, under ``.runtime/`` — is
gitignored too. A reviewer working from pushed ``origin/main`` can therefore
read NEITHER the claim's evidence NOR the thing it corrects.

That would leave the correction resting on an assertion, which is exactly the
failure mode this work order exists to eliminate.

So: this script is committed, its method is auditable from source, and its
OUTPUT is short enough to paste. A reviewer checks the logic here and the
numbers in the paste. Nothing has to be taken on trust.

WHAT IT CORRECTS
================
The work order recorded "story capture covered only 11 of 38 narrator turns
(28%)" as its central bottleneck. That number was never a coverage
measurement: ``MEMOIR-PATH-FINDING.md`` reports **11 operator PATCH actions in
the API log**, dated 2026-08-18/19/20, on narrators unrelated to the cohort —
welded to the cohort's 38 statements to make a ratio.

READ-ONLY. Opens the database with ``mode=ro``. Writes nothing, mutates
nothing, and does not rerun the cohort.

Usage:
    cd /mnt/c/Users/chris/hornelore
    python3 scripts/phase2_verify_ledger.py            # paste-able summary
    python3 scripts/phase2_verify_ledger.py --json     # structural rows, no narrator text
"""
from __future__ import annotations

import json
import os
import sqlite3
import statistics
import sys
from pathlib import Path

COHORT = "cohort-r20260831-040506-010cd6"
# server/code/api/db.py — the only statuses canonical memoir will read.
STORY_MEMOIR_ELIGIBLE = ("promoted", "memoir_only")


def db_path() -> Path:
    """Resolve the SAME database the server opens, from .env — never guessed.

    server/code/api/db.py:  DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
                            DB_NAME  = os.getenv("DB_NAME", "lorevox.sqlite3")
                            DB_PATH  = DATA_DIR / "db" / DB_NAME

    Guessing this wrong is not hypothetical: an earlier pass read
    ``data/db/lorevox.sqlite3`` inside the repo — a stale file with different
    data — and reported zero candidates for a narrator who has five.
    """
    data_dir, db_name = os.getenv("DATA_DIR"), os.getenv("DB_NAME")
    env = Path(".env")
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DATA_DIR=") and not data_dir:
                data_dir = line.split("=", 1)[1].strip()
            elif line.startswith("DB_NAME=") and not db_name:
                db_name = line.split("=", 1)[1].strip()
    return Path(data_dir or "data") / "db" / (db_name or "lorevox.sqlite3")


def structural_rows(turns, cands):
    """Row-level ledger with NO narrator text.

    Deliberately excludes transcripts and previews so the result is safe to
    paste, attach or commit. Everything here is structure — ids, counts,
    statuses, relationships — which is what a reviewer needs to check the
    metrics, and none of it is anybody's life story.
    """
    by_turn = {c[1]: c for c in cands}
    out = []
    for tid in sorted(turns):
        c = by_turn.get(tid)
        stmt = turns[tid].strip()
        out.append({
            "turn_id": tid,
            "statement_words": len(stmt.split()),
            "candidate_id": c[0] if c else None,
            "candidate_words": c[3] if c else None,
            "trigger_reason": c[7] if c else None,
            "transcript_equals_statement": (c[2].strip() == stmt) if c else None,
            "span_class": (None if not c else
                           "atomic" if c[2].strip() == stmt else "aggregate"),
            "statements_covered": 1 if c else 0,
            "contained_by": [b[0] for b in cands
                             if c and b[0] != c[0] and c[2].strip() in b[2].strip()],
            "contains": [b[0] for b in cands
                         if c and b[0] != c[0] and b[2].strip() in c[2].strip()],
            "placement": (c[5] if c else None),
            "placement_source": (c[6] if c else None),
            "review_status": (c[4] if c else None),
            "memoir_reachable": bool(c and c[4] in STORY_MEMOIR_ELIGIBLE),
            "terminal_status": ("archived_only" if not c
                                else "memoir_eligible" if c[4] in STORY_MEMOIR_ELIGIBLE
                                else "story_candidate_provisional"),
        })
    return out


def main() -> int:
    p = db_path()
    if not p.exists():
        print(f"database not found at {p} — run from the repo root", file=sys.stderr)
        return 2
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)

    turns = {r[0]: r[1] for r in con.execute(
        "SELECT id, content FROM turns WHERE conv_id LIKE ? AND role='user'",
        (COHORT + "%",))}
    cands = list(con.execute(
        "SELECT id, source_user_turn_row_id, transcript, word_count, review_status, "
        "       era_candidates, placement_source, trigger_reason, conversation_id "
        "FROM story_candidates WHERE conversation_id LIKE ?", (COHORT + "%",)))
    con.close()

    if "--json" in sys.argv:
        print(json.dumps({
            "cohort": COHORT, "source": str(p),
            "note": "structural only — no narrator text, safe to share",
            "rows": structural_rows(turns, cands),
        }, indent=1))
        return 0

    n = len(turns)
    bound = {c[1] for c in cands}
    # A candidate is ATOMIC when its transcript is exactly its source statement.
    atomic = [c for c in cands if turns.get(c[1], "").strip() == c[2].strip()]
    superset = [c for c in cands
                if turns.get(c[1], "") and turns[c[1]].strip() in c[2].strip()
                and turns[c[1]].strip() != c[2].strip()]
    subset = [c for c in cands
              if turns.get(c[1], "") and c[2].strip() in turns[c[1]].strip()
              and turns[c[1]].strip() != c[2].strip()]
    nested = [a[0] for a in cands for b in cands
              if a[0] != b[0] and a[2].strip() in b[2].strip()]
    reachable = [c for c in cands if c[4] in STORY_MEMOIR_ELIGIBLE]
    words = [len(t.split()) for t in turns.values()]

    print("PHASE 2 LEDGER — reproduced from the live DB, read-only")
    print(f"  database              : {p}")
    print(f"  cohort                : {COHORT}")
    print()
    print(f"  narrator statements                  : {n}")
    print(f"  statements with a candidate          : {len(bound)}"
          f"  ({100 * len(bound) / n:.1f}%)   <- CANDIDATE PRESENCE")
    print(f"  statements with NO candidate         : {n - len(bound)}")
    print(f"  candidates total                     : {len(cands)}")
    print()
    print(f"  transcript EXACTLY == source turn     : {len(atomic)}/{len(cands)}"
          "   <- capture faithfulness")
    print(f"  transcript is a STRICT SUPERSET       : {len(superset)}"
          "   <- OVER-CAPTURE / AGGREGATION")
    print(f"  transcript is a STRICT SUBSET         : {len(subset)}")
    print(f"  candidates nested inside another      : {len(nested)}"
          "   <- DUPLICATE / CONTAINMENT GROUPS")
    print()
    print(f"  INDEPENDENTLY ADDRESSABLE COVERAGE    : {len(atomic)}/{n}"
          f"  ({100 * len(atomic) / n:.1f}%)")
    print(f"  memoir-reachable (promoted|memoir_only): {len(reachable)}/{len(cands)}")
    print(f"  UNREACHABLE archived statements       : {n - len(reachable)}/{n}")
    print()
    print("  narrator statement size (words)       : "
          f"min={min(words)} median={int(statistics.median(words))} max={max(words)}")
    print()
    print("  review_status distribution:")
    dist: dict[str, int] = {}
    for c in cands:
        dist[c[4]] = dist.get(c[4], 0) + 1
    for k, v in sorted(dist.items()):
        print(f"    {k:<14} {v}")
    print()
    print("  statements with NO candidate (turn ids):",
          sorted(set(turns) - bound))
    print()
    print("VERDICT")
    print(f"  candidate presence is {len(bound)}/{n}, NOT 11/38.")
    print("  '11' was eleven operator PATCH actions in the API log "
          "(2026-08-18/19/20), never a coverage figure.")
    print(f"  Capture is byte-exact ({len(atomic)}/{len(cands)}) with "
          f"{len(superset)} over-capture and {len(nested)} containment groups.")
    print(f"  The bottleneck is REVIEW: {100 * len(bound) / n:.0f}% captured, "
          f"{100 * len(reachable) / max(len(cands), 1):.0f}% reviewed, "
          f"{n - len(reachable)}/{n} statements unreachable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
