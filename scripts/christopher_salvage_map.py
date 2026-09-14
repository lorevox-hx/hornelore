#!/usr/bin/env python3
"""READ ONLY. For every unique narrator turn in Christopher's development sessions:
does this fact already survive somewhere clean?

WO-LOREVOX-PORTABLE-NARRATOR-01, 2026-09-13.

THE QUESTION THIS ANSWERS. `preservation_plan.py` identified 16 Christopher sessions
that are structurally development/test but hold narrator-authored content appearing
nowhere else in `turns`. "Appears nowhere else in turns" is NOT the same as "would be
lost" -- a fact can survive as a trip note, a story candidate, a bio fact, or an
extraction result even when the conversation that produced it is discarded.

So this asks, per unique turn:

  ALREADY PRESERVED EXACTLY     the same text exists in a clean destination
  ALREADY PRESERVED SEMANTICALLY the same fact exists, differently worded
  UNIQUE FACT/STORY WORTH SALVAGING  real life/travel content with no clean home
  CAPABILITY/TEST UTTERANCE — NO SALVAGE  "can you see my trip", CAPPROBE, probes
  UNCERTAIN — HUMAN REVIEW

CAPABILITY QUESTIONS ARE NOT LIFE HISTORY. "can you see the pictures in my trip",
"tell me about this photo", CAPPROBE/MODAL_BOUNDARY_PROBE wrappers, "i asked you a
question", and conversational filler are the operator exercising the product. They
are development material however ordinary they read.

SAFETY-PROBE STRINGS. Sessions prefixed `safetylive_` / `smoke_` contain deliberate
distress phrases typed to exercise the safety path. They are test fixtures, not
statements by anyone, and are classified as such by structural provenance. They are
reported by reference, not quoted at length.

CONTENT IS USED FOR PRESERVATION ONLY, never ownership. Ownership was settled by
0044 pass 1 and is not revisited.

PRIVACY. Bounded excerpts of real narrator speech. `.runtime/` is gitignored. Do not
commit or publish.

**OPENS THE DATABASE STRICTLY READ-ONLY.** SELECTs only. Nothing is written,
discarded, repaired or re-exported.

    cd /mnt/c/Users/chris/hornelore
    python3 scripts/christopher_salvage_map.py \\
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
from typing import Any, Dict, List, Set, Tuple

CHRIS = "a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2"

#: The 16 from preservation_plan.py — MIXED or UNIQUE CONTENT TO SALVAGE.
DEFAULT_SESSIONS = [
    "switch_mre0txvh_tb7w", "tdmodal_e4a7a5aa-82e0-4d20-b8df-b8996f37ffd7",
    "tdlab_e4a7a5aa-82e0-4d20-b8df-b8996f37ffd7", "switch_mrkpipjr_twr7",
    "switch_mrkrk19b_0mfq", "tdmodal_boundary", "tdmodal_wording", "tdmodal_cap",
    "safetylive_1784843262386", "safetylive_1784843290401",
    "smoke_1784847585363", "smoke_1784847598215",
    "tdlab_9538cd88-5c8b-4da4-b2a9-2a03f8db32a3", "switch_ms81wxvv_pxxh",
    "switch_mseorb11_acy7", "switch_msf4yyl8_pw10",
]
DANGLING = {"switch_ms81wxvv_pxxh", "switch_ms8xrcuw_adlz", "switch_msaedccx_fkm1"}

#: Clean destinations a fact can survive in, independent of its conversation.
DESTINATIONS = ["trip_location_notes", "trip_photo_context", "trip_days", "trip_stops",
                "trip_public_context", "trip_bio_suggestions", "story_candidates",
                "bio_facts", "turn_extraction_results", "timeline_events", "photos"]

_SYSTEM_RX = re.compile(r"^\s*\[SYSTEM[:\]]", re.I)
_WORD_RX = re.compile(r"[a-z0-9']+")
_CAPABILITY_RX = re.compile(
    r"(capprobe|modal_boundary_probe|"
    r"can you (see|read|tell me|access|look)|"
    r"what can you tell me|tell me ab?n?out (this|that) photo|"
    r"are you speaking to me|i asked you a question|"
    r"what is your name and what is your purpose|"
    r"why arent they cleared|how many pictures can you see|"
    r"^(hi|hello|hey)\b|i'?m not sure what else to say|"
    r"what should we talk about next)", re.I)
_TEST_PREFIX_RX = re.compile(r"^(safetylive|smoke|guardsmoke|guardtest|wordcheck|"
                             r"tdmodal|tdlab|harness)", re.I)
_STOP = set("the a an and or but if then than that this those these of in on at to "
            "for with from by is was were are be been being i me my we our you your "
            "it its as so not no yes do did does have has had can could would will "
            "just about there here what when where who how which".split())

EXACT = 0.95
SEMANTIC = 0.45


def ro(db: Path):
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _has(con, t):
    return bool(con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone())


def _cols(con, t):
    return [(r["name"], (r["type"] or "").upper())
            for r in con.execute(f'PRAGMA table_info("{t}")')]


def _toks(s: str) -> Set[str]:
    return {w for w in _WORD_RX.findall((s or "").lower()) if w not in _STOP}


def _jac(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _key_terms(s: str, n: int = 4) -> List[str]:
    ws = sorted({w for w in _toks(s) if len(w) >= 5}, key=len, reverse=True)
    return ws[:n]


def _ex(s: Any, n: int = 100) -> str:
    t = " ".join(str(s or "").split())
    return (t[:n] + f"…(+{len(t) - n})") if len(t) > n else t


def search_destinations(con, text: str, dests: Dict[str, List[str]]
                        ) -> List[Tuple[float, str, str]]:
    """Best matches for `text` in clean destinations. (score, where, excerpt)."""
    terms = _key_terms(text)
    if not terms:
        return []
    tt = _toks(text)
    hits: List[Tuple[float, str, str]] = []
    for table, cols in dests.items():
        for col in cols:
            for term in terms:
                try:
                    rows = con.execute(
                        f'SELECT "{col}" AS v FROM "{table}" WHERE "{col}" LIKE ? LIMIT 40',
                        (f"%{term}%",)).fetchall()
                except sqlite3.Error:
                    continue
                for r in rows:
                    sc = _jac(tt, _toks(r["v"]))
                    if sc >= 0.25:
                        hits.append((sc, f"{table}.{col}", _ex(r["v"], 90)))
    hits.sort(key=lambda h: -h[0])
    return hits[:3]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True)
    ap.add_argument("--sessions", default="")
    ap.add_argument("--out", default=".runtime/two_origin/reports")
    args = ap.parse_args(argv)

    sessions = [s.strip() for s in args.sessions.split(",") if s.strip()] or DEFAULT_SESSIONS
    db = Path(args.db)
    if not db.is_file():
        print(f"database not found: {db}", file=sys.stderr)
        return 2

    con = ro(db)
    try:
        dests: Dict[str, List[str]] = {}
        for t in DESTINATIONS:
            if not _has(con, t):
                continue
            cols = [c for c, ty in _cols(con, t)
                    if ("CHAR" in ty or "TEXT" in ty or "CLOB" in ty or ty == "")
                    and not c.endswith("_id") and c not in ("id", "created_at",
                                                            "updated_at", "source")]
            if cols:
                dests[t] = cols

        # every narrator-authored turn everywhere, to find "already preserved exactly"
        all_user = con.execute(
            "SELECT id, conv_id, content FROM turns WHERE role='user'").fetchall()
        authored = [t for t in all_user if not _SYSTEM_RX.match(str(t["content"] or ""))]

        results = []
        for cid in sessions:
            turns = con.execute(
                "SELECT id, role, content, ts FROM turns WHERE conv_id=? ORDER BY id",
                (cid,)).fetchall()
            mine = [t for t in turns if t["role"] == "user"
                    and not _SYSTEM_RX.match(str(t["content"] or ""))
                    and _toks(t["content"])]
            is_test_session = bool(_TEST_PREFIX_RX.match(cid))

            turn_recs = []
            for t in mine:
                txt = str(t["content"] or "").strip()
                tt = _toks(txt)
                # unique within turns? (exclude same conversation)
                same = [o for o in authored
                        if o["conv_id"] != cid and _jac(tt, _toks(o["content"])) >= EXACT]
                if same:
                    verdict = "ALREADY PRESERVED EXACTLY"
                    where = [f"turns:{o['conv_id']}" for o in same[:3]]
                    hits = []
                elif _CAPABILITY_RX.search(txt):
                    verdict = "CAPABILITY/TEST UTTERANCE — NO SALVAGE"
                    where, hits = [], []
                elif is_test_session and re.match(r"^(safetylive|smoke)", cid, re.I):
                    verdict = "SAFETY-PATH TEST FIXTURE — NO SALVAGE"
                    where, hits = [], []
                else:
                    hits = search_destinations(con, txt, dests)
                    if hits and hits[0][0] >= SEMANTIC:
                        verdict = "ALREADY PRESERVED SEMANTICALLY"
                        where = [f"{h[1]} ({h[0]:.2f})" for h in hits[:2]]
                    elif len(tt) >= 5:
                        verdict = "UNIQUE FACT/STORY WORTH SALVAGING"
                        where = []
                    else:
                        verdict = "UNCERTAIN — HUMAN REVIEW"
                        where = []
                turn_recs.append({
                    "turn_id": t["id"], "ts": t["ts"], "excerpt": _ex(txt),
                    "verdict": verdict, "found_in": where,
                    "near_matches": [{"score": round(h[0], 2), "where": h[1],
                                      "excerpt": h[2]} for h in hits],
                })

            salv = [r for r in turn_recs
                    if r["verdict"] == "UNIQUE FACT/STORY WORTH SALVAGING"]
            unc = [r for r in turn_recs if r["verdict"] == "UNCERTAIN — HUMAN REVIEW"]
            if not turn_recs:
                disp = "WHOLE SESSION SAFE TO DISCARD LATER"
            elif not salv and not unc:
                disp = "WHOLE SESSION SAFE TO DISCARD LATER"
            elif salv and sum(len(r["excerpt"]) for r in salv) < 200:
                disp = "MAY BE DISCARDED AFTER SPECIFIC FACTS ARE SALVAGED"
            elif salv:
                disp = "PRESERVE SESSION TEMPORARILY — substantial unique narrator history"
            else:
                disp = "UNCERTAIN — HUMAN REVIEW"

            results.append({
                "conv_id": cid, "is_test_prefixed": is_test_session,
                "is_dangling_reference_session": cid in DANGLING,
                "narrator_turns": len(mine), "turns": turn_recs,
                "salvage_count": len(salv), "uncertain_count": len(unc),
                "proposed_disposition": disp,
            })
    finally:
        con.close()

    out = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "read_only": True, "db": str(db), "narrator": CHRIS,
        "destinations_searched": sorted(dests) if (dests := dests) else [],
        "privacy": "bounded narrator excerpts; .runtime is gitignored; do not commit",
        "sessions": results,
    }
    ts = _dt.datetime.now().strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(args.out) / f"christopher-salvage-{ts}"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "report.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print(f"READ-ONLY Christopher salvage map — {len(results)} sessions")
    print(f"clean destinations searched: {sorted(dests)}\n")

    for r in results:
        flag = "  <<< DANGLING-REFERENCE" if r["is_dangling_reference_session"] else ""
        print("=" * 76)
        print(f"{r['conv_id']}{flag}")
        print(f"  {'test-prefixed' if r['is_test_prefixed'] else 'switch/ordinary'}"
              f"   narrator turns={r['narrator_turns']}")
        print("=" * 76)
        for t in r["turns"]:
            print(f"  [{t['turn_id']:>5}] {t['excerpt']}")
            print(f"          => {t['verdict']}")
            if t["found_in"]:
                print(f"             survives in: {t['found_in']}")
            for m in t["near_matches"][:2]:
                if t["verdict"] != "ALREADY PRESERVED SEMANTICALLY":
                    print(f"             (nearest {m['score']} {m['where']}: {m['excerpt']})")
        print(f"  ==> {r['proposed_disposition']}")

    print("\n" + "=" * 76)
    print("PROPOSED DISPOSITION SUMMARY")
    print("=" * 76)
    for k, v in Counter(r["proposed_disposition"] for r in results).most_common():
        print(f"  {k:<56} {v}")

    print("\n  FACTS TO SALVAGE BEFORE ANY CLEANUP")
    n = 0
    for r in results:
        for t in r["turns"]:
            if t["verdict"] == "UNIQUE FACT/STORY WORTH SALVAGING":
                n += 1
                print(f"    {r['conv_id']:<46} [{t['turn_id']}] {t['excerpt']}")
    print(f"    total: {n}")

    print("\n  DANGLING-REFERENCE SESSIONS — semantic-reference problem still open")
    for r in results:
        if r["is_dangling_reference_session"]:
            print(f"    {r['conv_id']}  => {r['proposed_disposition']}")

    print("\n  Nothing written, discarded, repaired or re-exported.")
    print(f"\nwritten: {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
