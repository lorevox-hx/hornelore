#!/usr/bin/env python3
"""READ ONLY. Third-generation preservation classifier and salvage map.

WO-LOREVOX-PORTABLE-NARRATOR-01, 2026-09-13.

SUPERSEDES two earlier attempts, and the reasons are the design:

  gen 1 `classify_sessions_for_preservation.py` -- keyword heuristic. Counted
        `[SYSTEM: ...]` injections as narrator speech, missed byte-identical replay,
        and let autobiographical vocabulary promote harness sessions to "narrator
        history".
  gen 2 `classify_sessions_structural.py` -- fixed identity and whole-session replay,
        but STILL let vocabulary decide inside the family set. A `guardsmoke` session
        owned by Christopher with one real sentence came out "FAMILY CONVERSATION".

THREE QUESTIONS, KEPT SEPARATE. Conflating them is what produced both failures.

  1. WHO OWNS IT      -- settled structurally by 0044 pass 1. Not revisited here.
  2. WHAT CREATED IT  -- structural provenance: the writer-assigned conv_id prefix.
                         THIS OUTRANKS VOCABULARY, inside the family set as well as
                         outside it. A test fixture that says "my father" is still a
                         test fixture; the tests were written to sound real, so
                         sounding real is evidence of nothing.
  3. IS THERE INFORMATION WORTH KEEPING -- a development session can contain true
                         facts. "Contains a true fact" must never mean "keep this
                         entire session as canonical narrator history", and equally
                         must never mean "safe to delete".

SCRIPTED-MATERIAL DETECTION. Narrator-authored turns are normalised and compared
across ALL sessions, exactly and near-exactly. A turn that recurs across a
test-prefixed session and a `switch_` session is fixture replay, and it is the
single strongest signal that a `switch_` prefix does not imply a genuine memoir
conversation.

SALVAGE MAP. For every development/mixed session, report whether its content already
survives elsewhere -- another conversation, trip records, story candidates, bio
facts, extraction results -- so development scaffolding can eventually be removed
without losing genuine family information.

PRIVACY. Bounded excerpts of real narrator speech. `.runtime/` is gitignored. Do not
commit, publish, or paste into a work order.

**OPENS THE DATABASE STRICTLY READ-ONLY.** SELECTs only. No deletes, no ownership
repair, no re-export.

    cd /mnt/c/Users/chris/hornelore
    python3 scripts/preservation_plan.py --db /mnt/c/hornelore_data/db/hornelore.sqlite3
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
from typing import Any, Dict, List, Set

FAMILY = {
    "a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2": "Christopher",
    "4aa0cc2b-1f27-433a-9152-203bb1f69a55": "Kent",
    "93479171-0b97-4072-bcf0-d44c7f9078ba": "Janice",
    "d56900b5-3dda-4f44-b419-4891e1683007": "Melanie",
    "6ad678ee-b295-49de-8578-da00200848ba": "Del",
}

#: Writer-assigned structural markers. Presence classifies the SESSION as
#: development/test. Vocabulary cannot overturn this.
_TEST_RX = re.compile(
    r"^(harness|smoke|guardsmoke|guardtest|safetylive|wordcheck|tdmodal|tdlab|"
    r"trip_canary|trip_2019|factual_chain|spanish_smoke|gate7p2|zz-probe|"
    r"step6-ws-probe|modal_boundary|eval|probe)", re.I)
_SYSTEM_TURN_RX = re.compile(r"^\s*\[SYSTEM[:\]]", re.I)
_WORD_RX = re.compile(r"[a-z0-9']+")

DANGLING_CONVS = {"switch_ms81wxvv_pxxh", "switch_ms8xrcuw_adlz", "switch_msaedccx_fkm1"}
DANGLING_TURNS = {1455, 1461, 1467, 1471, 1477, 1515, 1517, 1529, 1579}

NEAR = 0.80          # Jaccard threshold for "near-duplicate"
SUBSTANTIVE = 120    # chars of genuinely typed narrator speech


def ro(db: Path):
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _has(con, t):
    return bool(con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone())


def _cols(con, t):
    return [r["name"] for r in con.execute(f'PRAGMA table_info("{t}")')]


def _norm(s: str) -> str:
    return " ".join(_WORD_RX.findall((s or "").lower()))


def _toks(s: str) -> Set[str]:
    return set(_WORD_RX.findall((s or "").lower()))


def _ex(s: Any, n: int = 95) -> str:
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

        owned = con.execute(
            "SELECT s.conv_id, i.person_id FROM sessions s "
            "JOIN interview_sessions i ON i.id = s.conv_id "
            "WHERE (s.person_id IS NULL OR TRIM(s.person_id)='') "
            "  AND i.person_id IS NOT NULL AND TRIM(i.person_id)<>'' "
            "  AND (SELECT COUNT(DISTINCT x.person_id) FROM interview_sessions x "
            "        WHERE x.id = s.conv_id) = 1").fetchall()
        target = {r["conv_id"]: r["person_id"] for r in owned}

        # ── narrator-authored turns across EVERY session, for replay detection ──
        # Comparison must span the whole table: a fixture typed into a `switch_`
        # session is only recognisable against the test session it came from.
        all_turns = con.execute(
            "SELECT id, conv_id, role, content FROM turns WHERE role='user' ORDER BY id"
        ).fetchall()
        authored = [t for t in all_turns
                    if not _SYSTEM_TURN_RX.match(str(t["content"] or ""))
                    and _norm(t["content"])]
        norm_of = {t["id"]: _norm(t["content"]) for t in authored}
        toks_of = {t["id"]: _toks(t["content"]) for t in authored}
        conv_of = {t["id"]: t["conv_id"] for t in authored}

        by_norm: Dict[str, List[int]] = defaultdict(list)
        for t in authored:
            by_norm[norm_of[t["id"]]].append(t["id"])

        # near-duplicate pairs across DIFFERENT conversations
        ids = [t["id"] for t in authored]
        near: Dict[int, Set[str]] = defaultdict(set)
        for i, a in enumerate(ids):
            ta = toks_of[a]
            if len(ta) < 4:
                continue
            for b in ids[i + 1:]:
                if conv_of[a] == conv_of[b]:
                    continue
                tb = toks_of[b]
                if len(tb) < 4:
                    continue
                inter = len(ta & tb)
                if not inter:
                    continue
                if inter / len(ta | tb) >= NEAR:
                    near[a].add(conv_of[b])
                    near[b].add(conv_of[a])

        recs: List[Dict[str, Any]] = []
        for cid, owner in target.items():
            turns = con.execute(
                "SELECT id, role, content, ts FROM turns WHERE conv_id=? ORDER BY id",
                (cid,)).fetchall()
            mine = [t for t in turns if t["role"] == "user"
                    and not _SYSTEM_TURN_RX.match(str(t["content"] or ""))
                    and _norm(t["content"])]
            injected = sum(1 for t in turns if t["role"] == "user"
                           and _SYSTEM_TURN_RX.match(str(t["content"] or "")))

            unique_t, exact_t, near_t = [], [], []
            elsewhere: Set[str] = set()
            for t in mine:
                others = {conv_of[i] for i in by_norm[norm_of[t["id"]]]} - {cid}
                nb = near.get(t["id"], set())
                if others:
                    exact_t.append(t)
                    elsewhere |= others
                elif nb:
                    near_t.append(t)
                    elsewhere |= nb
                else:
                    unique_t.append(t)

            typed = sum(len(str(t["content"] or "").strip()) for t in mine)
            uniq_chars = sum(len(str(t["content"] or "").strip()) for t in unique_t)
            is_test = bool(_TEST_RX.match(cid))
            repeats_from_test = {c for c in elsewhere if _TEST_RX.match(c)}

            refs: Dict[str, int] = {}
            if _has(con, "trip_turn_links"):
                refs["trip_turn_links"] = con.execute(
                    "SELECT COUNT(*) FROM trip_turn_links WHERE conv_id=?",
                    (cid,)).fetchone()[0]
            tids = [t["id"] for t in turns]
            if tids:
                marks = ",".join("?" * len(tids))
                keys = [f"turnrow:{i}" for i in tids]
                if _has(con, "turn_extraction_ledger"):
                    refs["extraction_ledger"] = con.execute(
                        f"SELECT COUNT(*) FROM turn_extraction_ledger "
                        f"WHERE turn_key IN ({marks})", keys).fetchone()[0]
                if _has(con, "turn_extraction_results"):
                    try:
                        refs["extraction_results"] = con.execute(
                            f"SELECT COUNT(*) FROM turn_extraction_results "
                            f"WHERE turn_key IN ({marks})", keys).fetchone()[0]
                    except sqlite3.Error:
                        pass
                if _has(con, "bio_facts"):
                    n = 0
                    for i in tids:
                        n += con.execute(
                            "SELECT COUNT(*) FROM bio_facts WHERE source LIKE ?",
                            (f"%turnrow:{i}%",)).fetchone()[0]
                    if n:
                        refs["bio_facts"] = n
            if _has(con, "story_candidates"):
                sc = _cols(con, "story_candidates")
                col = next((c for c in ("conversation_id", "conv_id") if c in sc), None)
                if col:
                    refs["story_candidates"] = con.execute(
                        f'SELECT COUNT(*) FROM story_candidates WHERE "{col}"=?',
                        (cid,)).fetchone()[0]
            refs = {k: v for k, v in refs.items() if v}

            # ── disposition: structure first, always ──────────────────
            why: List[str] = []
            if typed == 0:
                disp = "EMPTY/STRUCTURAL SHELL"
                why.append(f"no narrator-authored text; {injected} [SYSTEM:] injections")
            elif is_test:
                if unique_t:
                    disp = "DEVELOPMENT/TEST — UNIQUE CONTENT TO SALVAGE"
                    why.append(f"test-prefixed session; {len(unique_t)} turn(s) "
                               f"({uniq_chars} chars) appear nowhere else")
                else:
                    disp = "DEVELOPMENT/TEST — CONTENT DUPLICATED ELSEWHERE"
                    why.append("test-prefixed session; all narrator content recurs "
                               f"in {len(elsewhere)} other session(s)")
                why.append("structural provenance outranks vocabulary")
            elif repeats_from_test and not unique_t:
                disp = "DEVELOPMENT/TEST — CONTENT DUPLICATED ELSEWHERE"
                why.append(f"every narrator turn replays fixtures from "
                           f"{sorted(repeats_from_test)[:3]}")
            elif repeats_from_test:
                disp = "MIXED DEVELOPMENT + REAL CONTENT"
                why.append(f"{len(exact_t) + len(near_t)} fixture turn(s) replayed from "
                           f"{sorted(repeats_from_test)[:3]}; {len(unique_t)} unique "
                           f"({uniq_chars} chars)")
            elif uniq_chars >= SUBSTANTIVE:
                disp = "CANONICAL NARRATOR HISTORY"
                why.append(f"{uniq_chars} chars of unique narrator-authored text "
                           f"across {len(unique_t)} turns; no test provenance")
            elif typed < 60:
                disp = "EMPTY/STRUCTURAL SHELL"
                why.append(f"only {typed} chars typed")
            else:
                disp = "UNCLEAR — HUMAN REVIEW"
                why.append(f"{typed} chars typed, {uniq_chars} unique — below the "
                           f"{SUBSTANTIVE}-char bar but not empty")
            if refs.get("trip_turn_links") and disp.startswith("DEVELOPMENT"):
                disp = "MIXED DEVELOPMENT + REAL CONTENT"
                why.append(f"{refs['trip_turn_links']} trip_turn_links depend on it")

            recs.append({
                "conv_id": cid, "owner": owner,
                "owner_name": people.get(owner, owner),
                "family_name": FAMILY.get(owner), "is_family": owner in FAMILY,
                "structural_provenance": "test/dev prefix" if is_test else "switch/ordinary",
                "first_ts": turns[0]["ts"] if turns else None,
                "turns_total": len(turns), "narrator_turns": len(mine),
                "system_injected": injected,
                "typed_chars": typed, "unique_chars": uniq_chars,
                "turns_unique": len(unique_t), "turns_exact_dupe": len(exact_t),
                "turns_near_dupe": len(near_t),
                "content_also_in": sorted(elsewhere)[:8],
                "replays_fixtures_from": sorted(repeats_from_test)[:8],
                "downstream_references": refs,
                "is_dangling_investigation_session": cid in DANGLING_CONVS,
                "dangling_turn_ids_here": sorted({t["id"] for t in turns} & DANGLING_TURNS),
                "unique_excerpts": [_ex(t["content"]) for t in unique_t[:3]],
                "disposition": disp, "reasons": why,
            })
    finally:
        con.close()

    out = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "read_only": True, "db": str(db),
        "supersedes": ["classify_sessions_for_preservation.py (keyword)",
                       "classify_sessions_structural.py (identity only)"],
        "privacy": "bounded narrator excerpts; .runtime is gitignored; do not commit",
        "sessions": recs,
    }
    ts = _dt.datetime.now().strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(args.out) / f"preservation-plan-{ts}"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "report.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    fam = [r for r in recs if r["is_family"]]
    non = [r for r in recs if not r["is_family"]]

    print(f"READ-ONLY preservation plan — {len(recs)} attributable sessions")
    print("Structural provenance outranks vocabulary. [SYSTEM:] turns are not speech.\n")

    by = defaultdict(list)
    for r in fam:
        by[r["family_name"]].append(r)
    for fname, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        print("#" * 76)
        print(f"# {fname}   ({len(rs)} sessions)")
        print("#" * 76)
        for r in sorted(rs, key=lambda x: (x["disposition"], x["first_ts"] or "")):
            flag = "  <<< DANGLING-REFERENCE" if r["is_dangling_investigation_session"] else ""
            print(f"\n  {r['conv_id']}{flag}")
            print(f"    {r['first_ts']}   {r['structural_provenance']}")
            print(f"    turns={r['turns_total']}  narrator={r['narrator_turns']}  "
                  f"injected={r['system_injected']}  TYPED={r['typed_chars']}  "
                  f"UNIQUE={r['unique_chars']}")
            print(f"    turns: unique={r['turns_unique']} exact-dupe={r['turns_exact_dupe']} "
                  f"near-dupe={r['turns_near_dupe']}")
            if r["replays_fixtures_from"]:
                print(f"    replays fixtures from: {r['replays_fixtures_from']}")
            elif r["content_also_in"]:
                print(f"    content also in: {r['content_also_in']}")
            if r["downstream_references"]:
                print(f"    salvage anchors: {r['downstream_references']}")
            if r["dangling_turn_ids_here"]:
                print(f"    dangling turns: {r['dangling_turn_ids_here']}")
            for e in r["unique_excerpts"]:
                print(f"      unique · {e}")
            print(f"    => {r['disposition']}")
            for w in r["reasons"]:
                print(f"       · {w}")

    print("\n" + "#" * 76)
    print(f"# TEST/HARNESS PERSONAS ({len(non)} sessions) — not family, summarised only")
    print("#" * 76)
    for nm, c in Counter(r["owner_name"] for r in non).most_common():
        d = Counter(r["disposition"] for r in non if r["owner_name"] == nm)
        print(f"  {nm:<46} {c} sessions  {dict(d)}")

    print("\n" + "=" * 76)
    print("HUMAN-REVIEW TABLE — family narrators only")
    print("=" * 76)
    for fname, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        print(f"\n  {fname}")
        for k, v in Counter(r["disposition"] for r in rs).most_common():
            print(f"      {k:<52} {v}")
        sal = [r for r in rs if "SALVAGE" in r["disposition"]
               or r["disposition"].startswith("MIXED")]
        if sal:
            print(f"      -> {len(sal)} session(s) hold content to review before any cleanup:")
            for r in sal:
                print(f"         {r['conv_id']}  unique={r['unique_chars']}ch  "
                      f"anchors={r['downstream_references'] or '-'}")
    print("\n  Nothing written. No deletion, no ownership repair, no re-export.")
    print(f"\nwritten: {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
