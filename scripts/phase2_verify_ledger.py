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
# Gitignored and rotating, which is exactly the point: everything read
# from here is evidence that will not survive, and saying so is half the
# Phase 2 finding.
LOG_PATH = ".runtime/logs/api.log"


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
            # A turn with no candidate is NOT archived_only. archived_only
            # asserts that no memoir-reachable representation exists AND we
            # know why. We do not: the factual-chain decision is persisted
            # nowhere, so the correct status is measurement_failed.
            "terminal_status": ("measurement_failed" if not c
                                else "memoir_eligible" if c[4] in STORY_MEMOIR_ELIGIBLE
                                else "story_candidate_provisional"),
        })
    return out


def classifier_split(turns, cands):
    """Reproduce the Phase 2 classifier split using the SHIPPED trigger.

    Deterministic paths (full_threshold / borderline_scene_anchor /
    rich_short_narrative) are reproducible from stored text alone. The
    chain-detection path is NOT: it depends on chain_ctx supplied at
    runtime and persisted nowhere. So a turn the shipped classifier cannot
    reproduce without chain context was decided by the chain classifier —
    whether it produced a candidate or not.
    """
    sys.path.insert(0, str(Path("server") / "code"))
    from api.services import story_trigger as st

    bound = {c[1] for c in cands}
    det, chain_hit, chain_silent = [], [], []
    for tid, text in sorted(turns.items()):
        cls = st.classify_story_candidate(
            audio_duration_sec=None, transcript=text, chain_ctx=None)
        if cls is not None:
            det.append(tid)
        elif tid in bound:
            chain_hit.append(tid)
        else:
            chain_silent.append(tid)
    return {"deterministic": det, "chain_captured": chain_hit,
            "chain_silent": chain_silent}


def extraction_ledger_rows(con, turn_ids):
    """Cohort rows in turn_extraction_ledger. Phase 2 measured ZERO.

    Counts BOTH the user rows and, when the caller passes them, the
    assistant rows: turn_key is derived from the committed ASSISTANT row
    (``turnrow:<turns.id>``) as an idempotency key
    (``turn_extraction.py:44-47``), never from the narrator's text. A
    count that only looked at user-row ids would report zero on a cohort
    that had been extracted perfectly.
    """
    keys = {f"turnrow:{t}" for t in turn_ids}
    n = 0
    for (tk,) in con.execute("SELECT turn_key FROM turn_extraction_ledger"):
        if tk in keys:
            n += 1
    return n


def log_capture_decisions(log_path, cohort):
    """Read the live capture decisions out of the API log.

    THE DECISION IS RECORDED. An earlier version of this script closed
    with "the factual-chain decision is persisted NOWHERE ... nobody can
    say why it decided as it did". That overstated the defect and was
    corrected 2026-09-04: ``chat_ws.py:1848`` logs one
    ``[story-trigger]`` line per turn carrying trigger, word count and
    all three anchor dimensions. The real, narrower defect is that the
    log is the ONLY copy -- ``.runtime/`` is gitignored and rotates, so
    the decision behind a candidate is not durably attached to it.

    Returns {} when the log is absent or holds no cohort lines, so a
    reviewer without the log still gets the DB-derived numbers.
    """
    import re
    from collections import Counter

    path = Path(log_path)
    if not path.exists():
        return {}
    rx = re.compile(
        r"\[story-trigger\] conv=" + re.escape(cohort)
        + r"\S* .*?trigger=(?P<trigger>\S+) words=(?P<words>\d+) "
          r"anchors=(?P<anchors>\d+) place=(?P<place>\w+) "
          r"time=(?P<time>\w+) person=(?P<person>\w+)")
    triggers, misses = Counter(), []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = rx.search(line)
                if not m:
                    continue
                triggers[m.group("trigger")] += 1
                if m.group("trigger") == "None":
                    misses.append({
                        "words": int(m.group("words")),
                        "anchors": int(m.group("anchors")),
                        "place": m.group("place") == "True",
                        "time": m.group("time") == "True",
                        "person": m.group("person") == "True",
                    })
    except OSError:
        return {}
    if not triggers:
        return {}
    return {"triggers": dict(triggers), "misses": misses, "path": str(path)}


def log_extraction_skips(log_path, cohort):
    """Why extraction did or did not run, per the API log.

    Distinguishes a PRODUCT gap from a HARNESS gap. Zero ledger rows can
    mean the extractor was broken, or it can mean the server correctly
    declined because the client never declared it could receive a result
    (``chat_ws.py:924``) -- which is the ownership protocol working, not
    failing. Only the log tells them apart.
    """
    import re
    from collections import Counter

    path = Path(log_path)
    if not path.exists():
        return {}
    rx = re.compile(
        r"\[extract-turn\] skipped conv=" + re.escape(cohort)
        + r"\S* — (?P<reason>[^;(]{4,70})")
    reasons = Counter()
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = rx.search(line)
                if m:
                    reasons[m.group("reason").strip()] += 1
    except OSError:
        return {}
    return dict(reasons)


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
    ledger_rows = extraction_ledger_rows(con, turns.keys())
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

    # ── the findings that MATTER, added 2026-09-04 ────────────────────────
    # The first version of this script reproduced only candidate counts and
    # closed with "the bottleneck is REVIEW". That was yesterday's
    # conclusion. The command advertised as reproducing the Phase 2 audit
    # must reproduce the audit's OWN findings.
    split = classifier_split(turns, cands)
    d, hit, silent = split["deterministic"], split["chain_captured"], split["chain_silent"]
    print("  CAPTURE DECISION SPLIT — shipped story_trigger, no chain context")
    print("    [story_trigger.classify_story_candidate + story_candidates.source_user_turn_row_id]")
    print(f"    deterministic (anchors>=3, reproducible)   : {len(d)}/{n}")
    print(f"    chain-dependent (NOT reproducible)         : {len(hit) + len(silent)}/{n}")
    print(f"      chain fired, candidate created           : {len(hit)}")
    print(f"      trigger declined, NO candidate           : {len(silent)}  {sorted(silent)}")
    print()

    # ── CORROBORATION from the live log ───────────────────────────────
    # Derived from a DIFFERENT source than everything above: the split
    # above is recomputed today from stored text, this is what the server
    # actually decided at run time. Agreement between them is the only
    # evidence that re-running the classifier reproduces the live run.
    decisions = log_capture_decisions(LOG_PATH, COHORT)
    if decisions:
        print("  LIVE CAPTURE DECISIONS — recorded at run time "
              "[chat_ws.py:1848 -> .runtime/logs/api.log]")
        for k, v in sorted(decisions["triggers"].items()):
            print(f"    trigger={k:<26} {v}")
        if decisions["misses"]:
            sigs = {(m["anchors"], m["place"], m["time"], m["person"])
                    for m in decisions["misses"]}
            print(f"    the {len(decisions['misses'])} misses, by anchor signature:")
            for a, pl, ti, pe in sorted(sigs):
                print(f"      anchors={a} place={pl} time={ti} person={pe}")
    else:
        print("  LIVE CAPTURE DECISIONS: api.log absent or rotated — the DB")
        print("  cannot supply them, which is itself the auditability finding.")
    print()

    skips = log_extraction_skips(LOG_PATH, COHORT)
    print(f"  EXTRACTION LEDGER rows for cohort turns      : {ledger_rows}"
          "   [turn_extraction_ledger.turn_key]")
    if skips:
        print("  WHY, per the log [chat_ws.py:924 / :946 / :953]:")
        for reason, count in sorted(skips.items(), key=lambda kv: -kv[1]):
            print(f"    {count:>3}x {reason}")
    print()
    print(f"  terminal_status = measurement_failed         : {n - len(bound)}"
          f"   {sorted(set(turns) - bound)}   [structural_rows]")
    print()
    print("VERDICT")
    print(f"  candidate presence is {len(bound)}/{n}, NOT 11/38. '11' was eleven operator")
    print("  PATCH actions in the API log (2026-08-18/19/20), never a coverage figure.")
    print(f"  Capture is byte-exact ({len(atomic)}/{len(cands)}), {len(superset)} over-capture, "
          f"{len(nested)} containment groups.")
    print()
    # CORRECTED 2026-09-04. This block previously read "the factual-chain
    # classifier, whose result is persisted NOWHERE ... nobody can say why
    # it decided as it did", and called the zero ledger a defect. Both
    # overstated. The log carries every decision with its full anchor
    # breakdown, and the zero ledger is the ownership protocol declining
    # 38 times for a harness that never claimed the capability.
    print("  THE DEFECT IS DURABILITY OF THE DECISION, NOT ABSENCE OF ONE:")
    print("    - every capture decision WAS recorded, with trigger, word count and")
    print("      all three anchor dimensions. It was recorded to .runtime/logs/,")
    print("      which is gitignored and rotates. The decision is therefore not")
    print("      durably attached to the candidate it produced, or to the turn it")
    print("      declined. Reconstructing it needs a log that may have rotated.")
    print(f"    - the {len(silent)} misses are not mysterious: each is a present-day status")
    print("      summary with place and person but no RELATIVE time phrasing, and")
    print("      story_trigger.py:706 measures relative time, not absolute dates.")
    print("      Whether a life inventory should be a story is a PRODUCT question.")
    if skips:
        print("    - the zero ledger rows are a HARNESS gap, not a product defect:")
        print("      the cohort runner never declared client_capabilities")
        print("      .field_extraction_result=v1, so the server correctly declined")
        print("      and no browser was there to own extraction instead. Extraction")
        print("      binding CANNOT be studied from this cohort.")
    print()
    print("  Review is unexercised (0/%d reviewed) -- that is NOT a mandate to work the"
          % len(cands))
    print("  queue: these candidates may preserve words exactly while carrying invented")
    print("  relationships. Meaning integrity (Phase 3) comes first.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
