#!/usr/bin/env python3
"""READ ONLY. Which NULL-owner sessions are family history worth preserving, and
which are development/test residue?

WO-LOREVOX-PORTABLE-NARRATOR-01, 2026-09-13.

OWNERSHIP IS ALREADY SETTLED AND IS NOT REVISITED HERE. Every session this script
reports has exactly one accepted owner under migration 0044's pass-1 relationship
(`interview_sessions.id = sessions.conv_id`), proven structurally.

CONTENT IS USED HERE, AND ONLY FOR ONE PURPOSE. It decides PRESERVATION DISPOSITION
-- is this a real conversation or a development exercise. It is NEVER used to decide
ownership. That line is the whole reason this is a separate script from the
provenance ones: 0044's refusal list governs attribution, and nothing here touches
attribution.

PRIVACY. This report quotes bounded excerpts of real narrator speech. It is written
under `.runtime/`, which is gitignored, and must not be committed, pasted into a
work order, or published. Excerpts are capped; the JSON carries no more than the
console does. `docs/reports/` is gitignored for exactly this reason (CLAUDE.md).

THE DEVELOPMENT SIGNAL IS A HINT, NOT A VERDICT. Keyword scanning cannot tell a
narrator discussing their job from an operator testing a feature. Every flag it
raises is presented as a reason for Chris to look, and the suggested disposition is
labelled with the evidence behind it. Sessions it cannot read confidently are
returned as UNCLEAR rather than guessed.

**OPENS THE DATABASE STRICTLY READ-ONLY.** SELECTs only.

    cd /mnt/c/Users/chris/hornelore
    python3 scripts/classify_sessions_for_preservation.py \\
        --db /mnt/c/hornelore_data/db/hornelore.sqlite3
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

#: The three conversations whose turns the dangling-reference investigation exposed.
DANGLING_CONVS = {"switch_ms81wxvv_pxxh", "switch_ms8xrcuw_adlz", "switch_msaedccx_fkm1"}
DANGLING_TURNS = {1455, 1461, 1467, 1471, 1477, 1515, 1517, 1529, 1579}

#: Vocabulary that suggests the operator was exercising the product rather than a
#: narrator telling their life. A HINT ONLY -- a narrator may legitimately say
#: "testing" about their job, and an operator may type real memories.
_DEV_RX = re.compile(
    r"\b(test(ing|ed)?|debug|localhost|端|traceback|error|exception|console|"
    r"refresh|reload|browser|button|click(ed|ing)?|endpoint|api|json|sql|"
    r"migration|deploy|commit|bug|crash|placeholder|lorem|asdf|qwerty|"
    r"ignore this|does this work|checking|check if|one two three)\b", re.I)
#: Vocabulary that suggests genuine autobiographical narration.
_LIFE_RX = re.compile(
    r"\b(remember|grew up|my (mother|father|mom|dad|wife|husband|brother|sister|son|"
    r"daughter|grandmother|grandfather|family)|when i was|years? old|born|"
    r"childhood|school|church|married|moved to|back then|those days)\b", re.I)


def ro(db: Path):
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _has(con, t):
    return bool(con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone())


def _cols(con, t):
    return [r["name"] for r in con.execute(f'PRAGMA table_info("{t}")')]


def _ex(s: Any, n: int = 110) -> str:
    t = " ".join(str(s or "").split())
    return (t[:n] + f"…(+{len(t) - n})") if len(t) > n else t


def inspect(con, cid: str) -> Dict[str, Any]:
    rec: Dict[str, Any] = {"conv_id": cid}
    s = con.execute("SELECT conv_id, title, updated_at, person_id, person_id_source "
                    "FROM sessions WHERE conv_id=?", (cid,)).fetchone()
    rec["session"] = dict(s) if s else None

    i = con.execute("SELECT person_id, plan_id, started_at, turn_count "
                    "FROM interview_sessions WHERE id=?", (cid,)).fetchone()
    rec["interview"] = dict(i) if i else None
    rec["accepted_owner"] = i["person_id"] if i else None
    rec["accepted_owner_source"] = "interview_sessions.id (0044 pass 1)" if i else None

    turns = con.execute(
        "SELECT id, role, content, ts FROM turns WHERE conv_id=? ORDER BY id", (cid,)
    ).fetchall()
    rec["turn_count"] = len(turns)
    rec["first_ts"] = turns[0]["ts"] if turns else None
    rec["last_ts"] = turns[-1]["ts"] if turns else None
    rec["roles"] = dict(Counter(t["role"] for t in turns))

    user_txt = " ".join(str(t["content"] or "") for t in turns if t["role"] == "user")
    rec["user_chars"] = len(user_txt)
    dev_hits = sorted({m.group(0).lower() for m in _DEV_RX.finditer(user_txt)})
    life_hits = sorted({m.group(0).lower() for m in _LIFE_RX.finditer(user_txt)})
    rec["dev_signals"] = dev_hits[:12]
    rec["life_signals"] = life_hits[:12]

    # a recognisable, bounded trace: first two narrator turns, first assistant, last narrator
    trace: List[Dict[str, Any]] = []
    users = [t for t in turns if t["role"] == "user"]
    for t in users[:2]:
        trace.append({"id": t["id"], "role": "user", "ts": t["ts"],
                      "excerpt": _ex(t["content"])})
    asst = [t for t in turns if t["role"] == "assistant"]
    if asst:
        trace.append({"id": asst[0]["id"], "role": "assistant", "ts": asst[0]["ts"],
                      "excerpt": _ex(asst[0]["content"])})
    if len(users) > 2:
        trace.append({"id": users[-1]["id"], "role": "user", "ts": users[-1]["ts"],
                      "excerpt": _ex(users[-1]["content"])})
    rec["trace"] = trace

    # downstream references
    refs: Dict[str, int] = {}
    if _has(con, "trip_turn_links"):
        refs["trip_turn_links"] = con.execute(
            "SELECT COUNT(*) FROM trip_turn_links WHERE conv_id=?", (cid,)).fetchone()[0]
    tids = [t["id"] for t in turns]
    if tids and _has(con, "turn_extraction_ledger"):
        marks = ",".join("?" * len(tids))
        refs["extraction_ledger"] = con.execute(
            f"SELECT COUNT(*) FROM turn_extraction_ledger WHERE turn_key IN ({marks})",
            [f"turnrow:{i}" for i in tids]).fetchone()[0]
    if tids and _has(con, "turn_extraction_results"):
        marks = ",".join("?" * len(tids))
        try:
            refs["extraction_results"] = con.execute(
                f"SELECT COUNT(*) FROM turn_extraction_results WHERE turn_key IN ({marks})",
                [f"turnrow:{i}" for i in tids]).fetchone()[0]
        except sqlite3.Error:
            pass
    if _has(con, "story_candidates"):
        sc = _cols(con, "story_candidates")
        col = next((c for c in ("conversation_id", "conv_id") if c in sc), None)
        if col:
            refs["story_candidates"] = con.execute(
                f'SELECT COUNT(*) FROM story_candidates WHERE "{col}"=?', (cid,)
            ).fetchone()[0]
    if _has(con, "bio_facts") and tids:
        n = 0
        for i in tids:
            n += con.execute("SELECT COUNT(*) FROM bio_facts WHERE source LIKE ?",
                             (f'%turnrow:{i}%',)).fetchone()[0]
        refs["bio_facts_from_these_turns"] = n
    rec["downstream_references"] = {k: v for k, v in refs.items() if v}

    rec["is_dangling_investigation_session"] = cid in DANGLING_CONVS
    rec["dangling_turn_ids_here"] = sorted(set(tids) & DANGLING_TURNS)

    # suggested disposition — evidence shown, never a bare verdict
    why: List[str] = []
    if rec["turn_count"] == 0:
        disp, why = "UNCLEAR", ["no turns at all — nothing to preserve or review"]
    elif dev_hits and not life_hits:
        disp = "DEVELOPMENT/TEST — CANDIDATE FOR CLEANUP"
        why.append(f"development vocabulary only: {dev_hits[:6]}")
    elif life_hits and not dev_hits:
        disp = "PRESERVE AS NARRATOR HISTORY"
        why.append(f"autobiographical vocabulary, no development markers: {life_hits[:6]}")
    elif life_hits and dev_hits:
        disp = "MIXED — PRESERVE UNTIL HUMAN REVIEW"
        why.append(f"both present: life={life_hits[:4]} dev={dev_hits[:4]}")
    elif rec["user_chars"] < 40:
        disp = "DEVELOPMENT/TEST — CANDIDATE FOR CLEANUP"
        why.append(f"almost no narrator speech ({rec['user_chars']} chars)")
    else:
        disp, why = "UNCLEAR", ["no decisive vocabulary either way — read the trace"]
    if rec["downstream_references"].get("trip_turn_links"):
        why.append(f"has {rec['downstream_references']['trip_turn_links']} trip_turn_links "
                   f"— real travel-domain linkage")
        if disp.startswith("DEVELOPMENT"):
            disp = "MIXED — PRESERVE UNTIL HUMAN REVIEW"
            why.append("downgraded from cleanup: linked travel rows depend on it")
    rec["suggested_disposition"] = disp
    rec["disposition_reasons"] = why
    return rec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", default=".runtime/two_origin/reports")
    args = ap.parse_args(argv)

    db = Path(args.db)
    if not db.is_file():
        print(f"database not found: {db}", file=sys.stderr)
        return 2

    con = ro(db)
    try:
        pcols = _cols(con, "people")
        ncol = next((c for c in ("display_name", "name") if c in pcols), None)
        people = {r["id"]: (r[ncol] if ncol else r["id"]) for r in con.execute(
            f'SELECT id{"," + ncol if ncol else ""} FROM people')}
        rows = con.execute(
            "SELECT s.conv_id, i.person_id FROM sessions s "
            "JOIN interview_sessions i ON i.id = s.conv_id "
            "WHERE (s.person_id IS NULL OR TRIM(s.person_id)='') "
            "  AND i.person_id IS NOT NULL AND TRIM(i.person_id)<>'' "
            "  AND (SELECT COUNT(DISTINCT x.person_id) FROM interview_sessions x "
            "        WHERE x.id = s.conv_id) = 1").fetchall()
        recs = []
        for r in rows:
            rec = inspect(con, r["conv_id"])
            rec["owner_name"] = people.get(r["person_id"], r["person_id"])
            recs.append(rec)
    finally:
        con.close()

    out = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "read_only": True, "db": str(db),
        "privacy": "Contains bounded excerpts of real narrator speech. .runtime is "
                   "gitignored. Do not commit, publish, or paste into a work order.",
        "ownership_note": "Ownership settled structurally by 0044 pass 1. Content here "
                          "decides PRESERVATION only, never attribution.",
        "sessions": recs,
    }
    ts = _dt.datetime.now().strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(args.out) / f"preservation-classification-{ts}"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "report.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    by_owner = defaultdict(list)
    for r in recs:
        by_owner[r["owner_name"]].append(r)

    print(f"READ-ONLY preservation classification — {len(recs)} attributable sessions")
    print("PRIVACY: bounded narrator excerpts below; .runtime is gitignored.\n")

    for owner, rs in sorted(by_owner.items(), key=lambda kv: -len(kv[1])):
        print("#" * 74)
        print(f"# {owner}   ({len(rs)} sessions)")
        print("#" * 74)
        rs.sort(key=lambda r: (r["first_ts"] or ""))
        for r in rs:
            flag = "  <<< DANGLING-REFERENCE SESSION" if r["is_dangling_investigation_session"] else ""
            print(f"\n  {r['conv_id']}{flag}")
            print(f"    {r['first_ts']} .. {r['last_ts']}   turns={r['turn_count']} "
                  f"{r['roles']}   plan={(r['interview'] or {}).get('plan_id')}")
            print(f"    narrator chars={r['user_chars']}   refs={r['downstream_references'] or '-'}")
            if r["dangling_turn_ids_here"]:
                print(f"    dangling turn ids here: {r['dangling_turn_ids_here']}")
            if r["dev_signals"]:
                print(f"    dev signals : {r['dev_signals']}")
            if r["life_signals"]:
                print(f"    life signals: {r['life_signals']}")
            for t in r["trace"]:
                print(f"      [{t['id']:>5} {t['role']:<9}] {t['excerpt']}")
            print(f"    => {r['suggested_disposition']}")
            for w in r["disposition_reasons"]:
                print(f"       · {w}")

    print("\n" + "=" * 74)
    print("DISPOSITION TABLE")
    print("=" * 74)
    grid = defaultdict(Counter)
    for r in recs:
        grid[r["owner_name"]][r["suggested_disposition"]] += 1
    for owner, c in sorted(grid.items(), key=lambda kv: -sum(kv[1].values())):
        print(f"  {owner}")
        for k, v in c.most_common():
            print(f"      {k:<44} {v}")
    print("\n  TOTALS")
    for k, v in Counter(r["suggested_disposition"] for r in recs).most_common():
        print(f"      {k:<44} {v}")
    print("\n  Suggested dispositions are evidence-backed proposals for Chris, not")
    print("  decisions. Nothing was written. No package was re-exported.")
    print(f"\nwritten: {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
