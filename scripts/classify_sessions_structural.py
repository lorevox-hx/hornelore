#!/usr/bin/env python3
"""READ ONLY. Preservation classification by STRUCTURE, replacing the keyword version.

WO-LOREVOX-PORTABLE-NARRATOR-01, 2026-09-13.

WHY THIS REPLACES `classify_sessions_for_preservation.py`. That script's keyword
heuristic produced misleading verdicts and its own output proves it:

  * It counted `[SYSTEM: ...]` injected prompts as narrator speech. Those are stored
    as `role='user'` turns, so `switch_msaedccx_fkm1` reported 2170 "narrator chars"
    when the narrator actually typed "hi". Every such figure was inflated.
  * It called seven byte-identical Walt replays (14,420 chars each) and four
    identical `factual_chain_live_*` replays (719 chars each) "PRESERVE AS NARRATOR
    HISTORY".
  * It ignored narrator display names that say `harness`, `smoke` or `canary`.

THE THREE STRUCTURAL SIGNALS IT SHOULD HAVE USED, in order of strength:

  1. IDENTITY. Only five narrators are family: Christopher, Kent, Janice, Melanie,
     Del. Everyone else is a synthetic/harness identity and their sessions are not
     family history, whatever the prose sounds like. A display name containing
     harness/canary/smoke/probe/test is decisive on its own.
  2. REPLAY. Byte-identical narrator input across two or more sessions is a harness
     fingerprint. A person does not retype 14,420 characters identically.
  3. REAL NARRATOR SPEECH. Turns the human actually typed -- `role='user'` MINUS
     `[SYSTEM:` injections. A session where that is empty or near-empty is a probe,
     regardless of how long the assistant's reply was.

Content is still used ONLY for preservation disposition, NEVER for ownership.
Ownership was settled structurally by 0044 pass 1 and is not revisited.

PRIVACY. Bounded excerpts of real narrator speech. `.runtime/` is gitignored. Do not
commit, publish, or paste into a work order.

**OPENS THE DATABASE STRICTLY READ-ONLY.** SELECTs only.

    cd /mnt/c/Users/chris/hornelore
    python3 scripts/classify_sessions_structural.py \\
        --db /mnt/c/hornelore_data/db/hornelore.sqlite3
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

FAMILY = {
    "a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2": "Christopher",
    "4aa0cc2b-1f27-433a-9152-203bb1f69a55": "Kent",
    "93479171-0b97-4072-bcf0-d44c7f9078ba": "Janice",
    "d56900b5-3dda-4f44-b419-4891e1683007": "Melanie",
    "6ad678ee-b295-49de-8578-da00200848ba": "Del",
}
_SYNTH_NAME_RX = re.compile(r"harness|canary|smoke|probe|\btest\b|^ZZ\b", re.I)
_SYSTEM_TURN_RX = re.compile(r"^\s*\[SYSTEM[:\]]", re.I)

DANGLING_CONVS = {"switch_ms81wxvv_pxxh", "switch_ms8xrcuw_adlz", "switch_msaedccx_fkm1"}
DANGLING_TURNS = {1455, 1461, 1467, 1471, 1477, 1515, 1517, 1529, 1579}


def ro(db: Path):
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _has(con, t):
    return bool(con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone())


def _cols(con, t):
    return [r["name"] for r in con.execute(f'PRAGMA table_info("{t}")')]


def _ex(s: Any, n: int = 100) -> str:
    t = " ".join(str(s or "").split())
    return (t[:n] + f"…(+{len(t) - n})") if len(t) > n else t


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

        recs: List[Dict[str, Any]] = []
        for r in rows:
            cid, owner = r["conv_id"], r["person_id"]
            turns = con.execute(
                "SELECT id, role, content, ts FROM turns WHERE conv_id=? ORDER BY id",
                (cid,)).fetchall()
            real = [t for t in turns if t["role"] == "user"
                    and not _SYSTEM_TURN_RX.match(str(t["content"] or ""))]
            injected = [t for t in turns if t["role"] == "user"
                        and _SYSTEM_TURN_RX.match(str(t["content"] or ""))]
            real_txt = "\n".join(str(t["content"] or "").strip() for t in real)

            name = people.get(owner, owner or "")
            rec: Dict[str, Any] = {
                "conv_id": cid, "owner": owner, "owner_name": name,
                "is_family": owner in FAMILY,
                "family_name": FAMILY.get(owner),
                "name_marks_synthetic": bool(_SYNTH_NAME_RX.search(name or "")),
                "turns_total": len(turns),
                "narrator_turns_real": len(real),
                "system_injected_user_turns": len(injected),
                "narrator_chars_real": len(real_txt),
                "content_fingerprint": hashlib.sha256(
                    real_txt.encode("utf-8")).hexdigest()[:16] if real_txt else None,
                "first_ts": turns[0]["ts"] if turns else None,
                "last_ts": turns[-1]["ts"] if turns else None,
                "excerpts": [_ex(t["content"]) for t in real[:3]],
                "is_dangling_investigation_session": cid in DANGLING_CONVS,
                "dangling_turn_ids_here": sorted(
                    {t["id"] for t in turns} & DANGLING_TURNS),
            }
            refs: Dict[str, int] = {}
            if _has(con, "trip_turn_links"):
                refs["trip_turn_links"] = con.execute(
                    "SELECT COUNT(*) FROM trip_turn_links WHERE conv_id=?",
                    (cid,)).fetchone()[0]
            tids = [t["id"] for t in turns]
            if tids and _has(con, "turn_extraction_ledger"):
                marks = ",".join("?" * len(tids))
                refs["extraction_ledger"] = con.execute(
                    f"SELECT COUNT(*) FROM turn_extraction_ledger "
                    f"WHERE turn_key IN ({marks})",
                    [f"turnrow:{i}" for i in tids]).fetchone()[0]
            rec["downstream_references"] = {k: v for k, v in refs.items() if v}
            recs.append(rec)
    finally:
        con.close()

    # REPLAY DETECTION — identical narrator input across sessions
    fp = Counter(r["content_fingerprint"] for r in recs if r["content_fingerprint"])
    for r in recs:
        f = r["content_fingerprint"]
        r["replay_count"] = fp.get(f, 0) if f else 0
        r["is_replayed_fixture"] = bool(f) and fp.get(f, 0) > 1

    # DISPOSITION — structure first, content only for family narrators
    for r in recs:
        why: List[str] = []
        if not r["is_family"]:
            d = "NOT FAMILY — synthetic/harness identity, outside the family archive"
            why.append(f"owner '{r['owner_name']}' is not one of the five family narrators")
            if r["name_marks_synthetic"]:
                why.append("display name itself marks it synthetic")
            if r["is_replayed_fixture"]:
                why.append(f"narrator input byte-identical across {r['replay_count']} sessions")
        elif r["turns_total"] == 0:
            d, why = "EMPTY — no turns at all", ["nothing to preserve"]
        elif r["is_replayed_fixture"]:
            d = "DEVELOPMENT/TEST — replayed fixture"
            why.append(f"narrator input byte-identical across {r['replay_count']} sessions")
        elif r["narrator_chars_real"] == 0:
            d = "DEVELOPMENT/TEST — no narrator speech"
            why.append(f"all {r['system_injected_user_turns']} user turns are [SYSTEM:] injections")
        elif r["narrator_chars_real"] < 60:
            d = "DEVELOPMENT/TEST — negligible narrator speech"
            why.append(f"{r['narrator_chars_real']} chars actually typed")
        else:
            d = "FAMILY CONVERSATION — review for preservation"
            why.append(f"{r['narrator_chars_real']} chars actually typed across "
                       f"{r['narrator_turns_real']} turns")
        if r["downstream_references"].get("trip_turn_links") and d.startswith("DEVELOPMENT"):
            d = "MIXED — linked travel rows depend on it"
            why.append(f"{r['downstream_references']['trip_turn_links']} trip_turn_links")
        r["disposition"] = d
        r["reasons"] = why

    out = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "read_only": True, "db": str(db),
        "supersedes": "classify_sessions_for_preservation.py (keyword heuristic; "
                      "counted [SYSTEM:] injections as narrator speech, missed "
                      "byte-identical replay, ignored synthetic display names)",
        "privacy": "bounded narrator excerpts; .runtime is gitignored; do not commit",
        "sessions": recs,
    }
    ts = _dt.datetime.now().strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(args.out) / f"structural-classification-{ts}"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "report.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    fam = [r for r in recs if r["is_family"]]
    non = [r for r in recs if not r["is_family"]]

    print(f"READ-ONLY structural classification — {len(recs)} attributable sessions")
    print(f"family-narrator sessions: {len(fam)}   synthetic/harness: {len(non)}\n")
    print("SUPERSEDES the keyword classifier; see this file's header for why.\n")

    by = defaultdict(list)
    for r in fam:
        by[r["family_name"]].append(r)
    for fname, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        print("#" * 74)
        print(f"# {fname}   ({len(rs)} sessions)")
        print("#" * 74)
        for r in sorted(rs, key=lambda x: x["first_ts"] or ""):
            flag = "  <<< DANGLING-REFERENCE" if r["is_dangling_investigation_session"] else ""
            print(f"\n  {r['conv_id']}{flag}")
            print(f"    {r['first_ts']}   turns={r['turns_total']} "
                  f"(narrator {r['narrator_turns_real']}, injected "
                  f"{r['system_injected_user_turns']})   "
                  f"TYPED={r['narrator_chars_real']} chars")
            if r["downstream_references"]:
                print(f"    refs={r['downstream_references']}")
            if r["dangling_turn_ids_here"]:
                print(f"    dangling turns: {r['dangling_turn_ids_here']}")
            if r["is_replayed_fixture"]:
                print(f"    REPLAYED across {r['replay_count']} sessions")
            for e in r["excerpts"]:
                print(f"      · {e}")
            print(f"    => {r['disposition']}")
            for w in r["reasons"]:
                print(f"       · {w}")

    print("\n" + "#" * 74)
    print(f"# NON-FAMILY IDENTITIES ({len(non)} sessions) — outside the family archive")
    print("#" * 74)
    for nm, c in Counter(r["owner_name"] for r in non).most_common():
        reps = sum(1 for r in non if r["owner_name"] == nm and r["is_replayed_fixture"])
        print(f"  {nm:<46} {c} sessions  ({reps} replayed fixtures)")

    print("\n" + "=" * 74)
    print("DISPOSITION TABLE")
    print("=" * 74)
    grid = defaultdict(Counter)
    for r in fam:
        grid[r["family_name"]][r["disposition"]] += 1
    for fname, c in grid.items():
        print(f"  {fname}")
        for k, v in c.most_common():
            print(f"      {k:<52} {v}")
    print(f"\n  non-family / synthetic identities: {len(non)} sessions, no action")
    print("\n  Nothing written. No package re-exported. Dispositions are proposals.")
    print(f"\nwritten: {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
