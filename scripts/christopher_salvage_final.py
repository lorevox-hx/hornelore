#!/usr/bin/env python3
"""READ ONLY. The smallest defensible list of genuine facts requiring salvage.

WO-LOREVOX-PORTABLE-NARRATOR-01, 2026-09-13. Final pass over
`christopher_salvage_map.py`, whose nine-item list was still over-inclusive.

THREE CORRECTIONS, each for a demonstrated false positive:

  1. CONTROL APPENDAGES. Turns carrying `[SAFETY MODE: ACTIVE ...]`, `CAPPROBE`,
     `MODAL_BOUNDARY_PROBE` and similar are the operator exercising a path. The
     appendage is stripped and what REMAINS is judged; if the remainder is
     capability talk or trivially short, the turn is development material. Unique
     text is not the same as memoir content.

  2. OPERATOR TALK ABOUT THE PRODUCT. "Nobody talked about suicide...", "I asked
     about the location...", "can you see...", "why aren't they cleared..." are
     Christopher debugging Lori, not Christopher recounting his life. Valuable as
     test evidence; not narrator history, and not migrated into the clean record.

  3. IN-SESSION REPETITION. `tdlab_9538...` repeats "We spent the morning
     walking..." three times. That is one candidate, not three, and its recurrence
     inside a lab session is itself evidence it was being replayed.

FIXTURE-VARIATION DETECTION. A turn that is a known fixture plus a short suffix --
"My mother sewed all our clothes." + " She was patient with me." -- is reported with
its delta isolated, so the question becomes whether the DELTA is worth keeping rather
than whether the whole sentence is unique.

FINAL CATEGORIES
    NO SALVAGE — development/operator/test utterance
    ALREADY SURVIVES IN CLEAN DATA
    GENUINE UNIQUE FACT TO SALVAGE
    UNCERTAIN — CHRIS REVIEW

**READ ONLY.** SELECTs only. Nothing written, deleted, repaired or exported.

    cd /mnt/c/Users/chris/hornelore
    python3 scripts/christopher_salvage_final.py \\
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
from typing import Any, Dict, List, Set

#: The nine candidates the previous pass produced, by (conv_id, turn_id).
CANDIDATES = [
    ("switch_mrkpipjr_twr7", 1218), ("switch_mrkpipjr_twr7", 1232),
    ("switch_mrkpipjr_twr7", 1236),
    ("tdlab_9538cd88-5c8b-4da4-b2a9-2a03f8db32a3", 1448),
    ("tdlab_9538cd88-5c8b-4da4-b2a9-2a03f8db32a3", 1450),
    ("tdlab_9538cd88-5c8b-4da4-b2a9-2a03f8db32a3", 1452),
    ("tdlab_9538cd88-5c8b-4da4-b2a9-2a03f8db32a3", 1482),
    ("switch_mseorb11_acy7", 1614), ("switch_mseorb11_acy7", 1616),
]
#: Plus the two the previous pass left UNCERTAIN and one flagged for re-check.
EXTRA = [("switch_mre0txvh_tb7w", 1174), ("switch_mre0txvh_tb7w", 1182),
         ("tdlab_9538cd88-5c8b-4da4-b2a9-2a03f8db32a3", 1532)]

_APPENDAGE_RX = re.compile(
    r"\[SAFETY MODE[^\]]*\]|\[SYSTEM[^\]]*\]|\[EVAL[^\]]*\]|\[TEST[^\]]*\]|"
    r"CAPPROBE|MODAL_BOUNDARY_PROBE_?\d*", re.I)
_OPERATOR_RX = re.compile(
    r"(nobody talked about|i asked (about|you) |can you (see|locate|read|tell|look)|"
    r"why aren'?t|why arent|are you speaking to me|what do you know about me so far|"
    r"say that again|tell me ab?n?out (this|that) photo|what date was that taken|"
    r"what can you tell me|i'?m not sure what else to say|what should we talk about|"
    r"what is your name and what is your purpose)", re.I)
_WORD_RX = re.compile(r"[a-z0-9']+")
_STOP = set("the a an and or but if then than that this those these of in on at to for "
            "with from by is was were are be been being i me my we our you your it its "
            "as so not no yes do did does have has had can could would will just about "
            "there here what when where who how which".split())
_TEST_PREFIX_RX = re.compile(r"^(safetylive|smoke|guardsmoke|guardtest|wordcheck|"
                             r"tdmodal|tdlab|harness|trip_canary|factual_chain)", re.I)
_SYSTEM_RX = re.compile(r"^\s*\[SYSTEM[:\]]", re.I)

DESTINATIONS = ["trip_location_notes", "trip_photo_context", "trip_days", "trip_stops",
                "trip_public_context", "trip_bio_suggestions", "story_candidates",
                "timeline_events", "photos"]
SEMANTIC = 0.45
FIXTURE_SIM = 0.55


def ro(db: Path):
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _has(con, t):
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                            (t,)).fetchone())


def _cols(con, t):
    return [(r["name"], (r["type"] or "").upper())
            for r in con.execute(f'PRAGMA table_info("{t}")')]


def _toks(s: str) -> Set[str]:
    return {w for w in _WORD_RX.findall((s or "").lower()) if w not in _STOP}


def _jac(a, b) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _strip(s: str) -> str:
    return " ".join(_APPENDAGE_RX.sub(" ", s or "").split())


def _ex(s: Any, n: int = 110) -> str:
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
        dests: Dict[str, List[str]] = {}
        for t in DESTINATIONS:
            if not _has(con, t):
                continue
            cols = [c for c, ty in _cols(con, t)
                    if ("CHAR" in ty or "TEXT" in ty or "CLOB" in ty or ty == "")
                    and not c.endswith("_id")
                    and c not in ("id", "created_at", "updated_at", "source")]
            if cols:
                dests[t] = cols

        authored = [r for r in con.execute(
            "SELECT id, conv_id, content FROM turns WHERE role='user'")
            if not _SYSTEM_RX.match(str(r["content"] or ""))]

        recs = []
        for cid, tid in CANDIDATES + EXTRA:
            row = con.execute("SELECT id, conv_id, content, ts FROM turns WHERE id=?",
                              (tid,)).fetchone()
            if row is None:
                continue
            raw = str(row["content"] or "").strip()
            core = _strip(raw)
            had_appendage = core != " ".join(raw.split())
            ct = _toks(core)

            # fixture variation: closest other authored turn
            best = (0.0, None, None)
            for o in authored:
                if o["id"] == tid:
                    continue
                s = _jac(ct, _toks(_strip(str(o["content"] or ""))))
                if s > best[0]:
                    best = (s, o["conv_id"], _strip(str(o["content"] or "")))
            fixture_sim, fixture_conv, fixture_txt = best
            delta = ""
            if fixture_txt and fixture_sim >= FIXTURE_SIM:
                ft = _toks(fixture_txt)
                delta = " ".join(sorted(ct - ft))

            # clean-destination survival
            hits = []
            terms = sorted({w for w in ct if len(w) >= 5}, key=len, reverse=True)[:4]
            for table, cols in dests.items():
                for col in cols:
                    for term in terms:
                        try:
                            rows = con.execute(
                                f'SELECT "{col}" AS v FROM "{table}" '
                                f'WHERE "{col}" LIKE ? LIMIT 40', (f"%{term}%",)).fetchall()
                        except sqlite3.Error:
                            continue
                        for r2 in rows:
                            sc = _jac(ct, _toks(r2["v"]))
                            if sc >= 0.3:
                                hits.append((sc, f"{table}.{col}", _ex(r2["v"], 80)))
            hits.sort(key=lambda h: -h[0])
            hits = hits[:2]

            # ── verdict ──────────────────────────────────────────────
            why: List[str] = []
            if had_appendage:
                why.append("carried a control appendage; judged on the remainder")
            if _OPERATOR_RX.search(core) or len(ct) < 3:
                v = "NO SALVAGE — development/operator/test utterance"
                why.append("operator talking about the product, or no substantive content")
            elif hits and hits[0][0] >= SEMANTIC:
                v = "ALREADY SURVIVES IN CLEAN DATA"
                why.append(f"{hits[0][1]} at {hits[0][0]:.2f}")
            elif fixture_sim >= FIXTURE_SIM and _TEST_PREFIX_RX.match(fixture_conv or ""):
                v = "UNCERTAIN — CHRIS REVIEW"
                why.append(f"variation on fixture in {fixture_conv} (sim {fixture_sim:.2f})")
                why.append(f"only novel words: '{delta}'" if delta else "no novel words")
            elif fixture_sim >= 0.9:
                v = "ALREADY SURVIVES IN CLEAN DATA"
                why.append(f"near-identical turn in {fixture_conv}")
            else:
                v = "GENUINE UNIQUE FACT TO SALVAGE"
                why.append(f"no clean destination (best {hits[0][0]:.2f} "
                           f"{hits[0][1]})" if hits else "no clean destination match")
            recs.append({
                "conv_id": cid, "turn_id": tid, "ts": row["ts"],
                "raw_excerpt": _ex(raw), "core_excerpt": _ex(core),
                "had_control_appendage": had_appendage,
                "nearest_other_turn": {"similarity": round(fixture_sim, 2),
                                       "conv_id": fixture_conv,
                                       "novel_words": delta},
                "clean_destination_hits": [{"score": round(h[0], 2), "where": h[1],
                                            "excerpt": h[2]} for h in hits],
                "verdict": v, "reasons": why,
            })

        # in-session dedupe of equivalent candidates
        seen: Dict[Any, str] = {}
        for r in recs:
            key = (r["conv_id"], " ".join(sorted(_toks(r["core_excerpt"]))))
            if key in seen:
                r["duplicate_of_turn"] = seen[key]
                r["verdict"] = "NO SALVAGE — repeated within the same session"
                r["reasons"] = [f"same content as turn {seen[key]} in this session; "
                                f"repetition inside a lab session is replay, not "
                                f"three independent facts"]
            else:
                seen[key] = r["turn_id"]
    finally:
        con.close()

    out = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "read_only": True, "db": str(db),
        "supersedes": "the nine-item list in christopher_salvage_map.py",
        "privacy": "bounded narrator excerpts; .runtime is gitignored; do not commit",
        "candidates": recs,
    }
    ts = _dt.datetime.now().strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(args.out) / f"christopher-salvage-final-{ts}"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "report.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print(f"READ-ONLY final salvage pass — {len(recs)} candidates re-judged\n")
    for r in recs:
        print("-" * 76)
        print(f"{r['conv_id']}  [{r['turn_id']}]")
        print(f"  raw : {r['raw_excerpt']}")
        if r["had_control_appendage"]:
            print(f"  core: {r['core_excerpt']}")
        n = r["nearest_other_turn"]
        if n["similarity"] >= 0.5:
            print(f"  nearest turn: {n['similarity']} in {n['conv_id']}"
                  + (f"   novel words: '{n['novel_words']}'" if n["novel_words"] else ""))
        for h in r["clean_destination_hits"]:
            print(f"  clean data  : {h['score']} {h['where']}: {h['excerpt']}")
        print(f"  => {r['verdict']}")
        for w in r["reasons"]:
            print(f"     · {w}")

    print("\n" + "=" * 76)
    print("FINAL SALVAGE RESULT")
    print("=" * 76)
    for k, v in Counter(r["verdict"] for r in recs).most_common():
        print(f"  {k:<56} {v}")
    keep = [r for r in recs if r["verdict"] == "GENUINE UNIQUE FACT TO SALVAGE"]
    rev = [r for r in recs if r["verdict"] == "UNCERTAIN — CHRIS REVIEW"]
    print(f"\n  GENUINE FACTS REQUIRING ACTION ({len(keep)})")
    for r in keep:
        print(f"    {r['conv_id']} [{r['turn_id']}] {r['core_excerpt']}")
    print(f"\n  FOR CHRIS TO DECIDE ({len(rev)})")
    for r in rev:
        print(f"    {r['conv_id']} [{r['turn_id']}] {r['core_excerpt']}")
        print(f"        {r['reasons'][-1]}")
    print("\n  Nothing written, deleted, repaired or exported.")
    print(f"\nwritten: {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
