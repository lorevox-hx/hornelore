#!/usr/bin/env python3
"""READ ONLY. Classify the NULL-owner sessions before anyone repairs one.

WO-LOREVOX-PORTABLE-NARRATOR-01, 2026-09-13.

WHY THIS COMES BEFORE A BACKFILL. `audit_null_owner_sessions.py` found 81 NULL-owner
sessions with a unique accepted owner. That is NOT 81 production narrator sessions
that lost their ownership: the same 81 include `harness-test-*` ids, and 42 of them
are Christopher during the period he was building the travel-document system using
himself as the narrator. "Attributable" and "should have been attributed at creation"
are different claims, and only the first has been measured.

THE QUESTION THAT DECIDES WHETHER A DEFECT IS STILL LIVE

    Are there any genuine, non-test NULL-owner sessions created AFTER the
    2026-08-16 R2.3/R2.4 ownership fix?

  no  -> the production writer is healthy; this is historical cleanup plus an
         ownership-declaration question for portability.
  yes -> an active writer/materialisation defect, and that is a different lane.

TWO KINDS OF EVIDENCE, KEPT STRICTLY APART

  ATTRIBUTION (who owns it) uses ONLY what 0044/0045 accepted: interview_sessions,
  memory_archive_sessions, turns.meta_json, and the two structured payload keys.
  Never directory proximity, timestamps, or prose.

  CLASSIFICATION (what created it) uses writer-assigned structural markers: the
  conv_id prefix a writer chose (`switch_`, `tdlab_`, `tdmodal_`, `smoke_`,
  `guardsmoke`, `safetylive_`, `zz-probe-`...), `interview_sessions.plan_id`, and
  whether travel tables reference the conversation. These say which code path made
  the row. They are NOT used to decide ownership, and nothing here writes anything.

**OPENS THE DATABASE STRICTLY READ-ONLY.** SELECTs only.

    cd /mnt/c/Users/chris/hornelore
    python3 scripts/classify_null_owner_sessions.py \\
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

#: WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 R2.3/R2.4 — chat_ws began passing
#: person_id through persist_turn_transaction (chat_ws.py:590-593).
OWNERSHIP_FIX = "2026-08-16"
#: schema_migrations records 0044 applied 2026-08-17 03:06:39 on this installation;
#: read from the table when present rather than trusted from here.
M0044_FALLBACK = "2026-08-17 03:06:39"

_PREFIX_RX = re.compile(r"^(switch|tdlab|tdmodal|smoke|guardsmoke|guardtest|safetylive"
                        r"|step6-ws-probe|zz-probe|harness|eval|probe)[-_]", re.I)


def ro(db: Path):
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _cols(con, t):
    return [r["name"] for r in con.execute(f'PRAGMA table_info("{t}")')]


def _has(con, t):
    return bool(con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone())


def _prefix(cid: str) -> str:
    m = _PREFIX_RX.match(cid or "")
    if m:
        return m.group(1).lower()
    return (cid or "").split("_")[0][:24] or "(blank)"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", default=".runtime/two_origin/reports")
    ap.add_argument("--fix-date", default=OWNERSHIP_FIX)
    args = ap.parse_args(argv)

    db = Path(args.db)
    if not db.is_file():
        print(f"database not found: {db}", file=sys.stderr)
        return 2
    con = ro(db)
    try:
        pcols = _cols(con, "people")
        name_col = next((c for c in ("display_name", "name", "full_name") if c in pcols), None)
        people = {r["id"]: (r[name_col] if name_col else r["id"])
                  for r in con.execute(
                      f'SELECT id{"," + name_col if name_col else ""} FROM people')}
        testing_only = {}
        if "testing_only" in pcols:
            testing_only = {r["id"]: r["testing_only"]
                            for r in con.execute("SELECT id, testing_only FROM people")}

        m0044 = M0044_FALLBACK
        if _has(con, "schema_migrations") and "applied_at" in _cols(con, "schema_migrations"):
            r = con.execute("SELECT applied_at FROM schema_migrations "
                            "WHERE filename LIKE '%0044%'").fetchone()
            if r and r["applied_at"]:
                m0044 = r["applied_at"]

        has_is = _has(con, "interview_sessions")
        has_ttl = _has(con, "trip_turn_links")

        rows: List[Dict[str, Any]] = []
        for s in con.execute(
                "SELECT conv_id, title, updated_at, person_id FROM sessions "
                "WHERE person_id IS NULL OR TRIM(person_id)=''"):
            cid = s["conv_id"]
            rec: Dict[str, Any] = {"conv_id": cid, "prefix": _prefix(cid),
                                   "updated_at": s["updated_at"]}

            t = con.execute("SELECT MIN(ts) a, MAX(ts) b, COUNT(*) n "
                            "FROM turns WHERE conv_id=?", (cid,)).fetchone()
            rec["first_turn_ts"], rec["last_turn_ts"], rec["turns"] = t["a"], t["b"], t["n"]

            # ATTRIBUTION — accepted sources only
            owners = set()
            if has_is:
                for r in con.execute(
                        "SELECT DISTINCT person_id FROM interview_sessions WHERE id=? "
                        "AND person_id IS NOT NULL AND TRIM(person_id)<>''", (cid,)):
                    owners.add(r[0])
                ip = con.execute("SELECT plan_id, started_at FROM interview_sessions "
                                 "WHERE id=?", (cid,)).fetchone()
                rec["plan_id"] = ip["plan_id"] if ip else None
                rec["interview_started_at"] = ip["started_at"] if ip else None
            if _has(con, "memory_archive_sessions"):
                for r in con.execute(
                        "SELECT DISTINCT person_id FROM memory_archive_sessions WHERE conv_id=? "
                        "AND person_id IS NOT NULL AND TRIM(person_id)<>''", (cid,)):
                    owners.add(r[0])
            for r in con.execute(
                    "SELECT DISTINCT json_extract(meta_json,'$.person_id') p FROM turns "
                    "WHERE conv_id=? AND json_valid(meta_json) "
                    "AND json_extract(meta_json,'$.person_id') IS NOT NULL", (cid,)):
                if r["p"]:
                    owners.add(r["p"])
            rec["accepted_owners"] = sorted(owners)
            rec["attributable"] = len(owners) == 1
            owner = next(iter(owners)) if len(owners) == 1 else None
            rec["owner"] = owner
            rec["owner_name"] = people.get(owner) if owner else None
            rec["owner_testing_only"] = testing_only.get(owner) if owner else None
            rec["owner_in_people"] = owner in people if owner else None

            # CLASSIFICATION — structural markers only
            rec["travel_links"] = (con.execute(
                "SELECT COUNT(*) FROM trip_turn_links WHERE conv_id=?", (cid,)
            ).fetchone()[0] if has_ttl else 0)

            stamp = rec["first_turn_ts"] or rec["updated_at"] or ""
            rec["after_ownership_fix"] = bool(stamp) and stamp >= args.fix_date
            rec["after_0044"] = bool(stamp) and stamp >= m0044.replace(" ", "T")

            nm = (rec["owner_name"] or "") if owner else ""
            oid = owner or ""
            if oid.startswith("harness-test"):
                cat = "harness_or_test_id"
            elif nm.startswith("ZZ ") or nm.startswith("ZZ"):
                cat = "zz_synthetic_narrator"
            elif rec["owner_testing_only"]:
                cat = "testing_only_narrator"
            elif not rec["attributable"]:
                cat = "no_unique_attribution"
            else:
                cat = "attributable_real_narrator"
            rec["category"] = cat
            rows.append(rec)
    finally:
        con.close()

    attributable = [r for r in rows if r["attributable"]]
    post_fix = [r for r in attributable if r["after_ownership_fix"]]
    post_fix_real = [r for r in post_fix if r["category"] == "attributable_real_narrator"]

    out = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "read_only": True, "db": str(db),
        "ownership_fix_date": args.fix_date, "migration_0044_applied_at": m0044,
        "null_owner_sessions": len(rows),
        "with_unique_accepted_owner": len(attributable),
        "rows": rows,
    }
    ts = _dt.datetime.now().strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(args.out) / f"null-owner-classification-{ts}"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "report.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print(f"READ-ONLY classification of {db}")
    print(f"ownership fix (R2.3/R2.4): {args.fix_date}   0044 applied: {m0044}")
    print(f"NULL-owner sessions: {len(rows)}   with a unique accepted owner: "
          f"{len(attributable)}\n")

    print("=" * 74)
    print("THE QUESTION: attributable NULL-owner sessions created AFTER the fix")
    print("=" * 74)
    print(f"  after {args.fix_date}, any category   : {len(post_fix)}")
    print(f"  after {args.fix_date}, REAL narrator   : {len(post_fix_real)}")
    if post_fix_real:
        print("  *** AN ACTIVE WRITER DEFECT IS INDICATED — these are not historical ***")
        for r in post_fix_real[:20]:
            print(f"      {r['conv_id']:<34} {r['first_turn_ts']}  owner={r['owner_name']}"
                  f"  prefix={r['prefix']}  plan={r.get('plan_id')}  turns={r['turns']}")
    else:
        print("  -> none. Consistent with the production writer being healthy since the")
        print("     fix; this would be historical residue plus a declaration question.")
        if post_fix:
            print(f"  ({len(post_fix)} post-fix rows exist but are test/synthetic ids:)")
            for r in post_fix[:10]:
                print(f"      {r['conv_id']:<34} {r['first_turn_ts']}  {r['category']}")

    print("\n" + "=" * 74)
    print("CATEGORIES (attributable rows)")
    print("=" * 74)
    for k, v in Counter(r["category"] for r in attributable).most_common():
        print(f"  {k:<34} {v}")

    print("\nBY NARRATOR (attributable)")
    per = defaultdict(list)
    for r in attributable:
        per[r["owner"]].append(r)
    for oid, rs in sorted(per.items(), key=lambda kv: -len(kv[1])):
        nm = rs[0]["owner_name"]
        pre = Counter(r["prefix"] for r in rs)
        trav = sum(1 for r in rs if r["travel_links"])
        span = (min(r["first_turn_ts"] or "" for r in rs),
                max(r["last_turn_ts"] or "" for r in rs))
        post = sum(1 for r in rs if r["after_ownership_fix"])
        print(f"  {nm}  [{oid[:8]}]  sessions={len(rs)}  post_fix={post}")
        print(f"      prefixes={dict(pre)}  with_travel_links={trav}")
        print(f"      span={span[0]} .. {span[1]}")

    print("\nBY WRITER PREFIX (attributable) — what code path made these")
    for k, v in Counter(r["prefix"] for r in attributable).most_common():
        print(f"  {k:<20} {v}")

    print(f"\nwritten: {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
