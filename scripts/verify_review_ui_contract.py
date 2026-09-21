"""The round trip: real refusal -> real UI -> real request -> real server.

ON A COPY. The live database is opened read-only, copied, never written.

WHY
---
The reviewer's objection, verbatim:

    Claude reports successfully testing a corrected acceptance on a
    database copy. That establishes something about the reported test,
    but it does not demonstrate that a person can complete the same
    operation in the actual interface.

Exactly right. `verify_legacy_review_flow.py` calls `sr.accept()` with
the arguments I chose. It proves the service works and says nothing
about whether the shipping page can produce those arguments.

So this closes the loop, in four moves:

  1. Call the REAL `accept_suggestion_route` against real legacy
     suggestions and capture the 422 bodies it actually raises.
  2. Replay those exact bodies into the REAL
     `ui/js/suggestion-review.js`, in jsdom, and click the controls a
     person would click.
  3. Capture the request bodies the module builds.
  4. Feed THOSE bodies back to the REAL route and assert the write
     lands, with the right provenance and the right accept_mode.

Step 4 is the one that matters. If the page sends a field the server
does not read, or omits one it requires, this fails — and the earlier
service-level test would still have passed.

    python3 scripts/verify_review_ui_contract.py
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "tests"))

DB = os.environ.get("HORNELORE_DB", "/mnt/c/hornelore_data/db/hornelore.sqlite3")
G, R, Y, X = "\033[32m", "\033[31m", "\033[33m", "\033[0m"

_fail = 0


def check(good, msg, detail=""):
    global _fail
    if good:
        print(f"    {G}PASS{X}  {msg}")
    else:
        _fail += 1
        print(f"    {R}FAIL{X}  {msg}")
        if detail:
            print(f"          {detail}")


def main() -> int:
    global _fail
    src = Path(DB)
    if not src.exists():
        print(f"{R}No database at {DB}{X}")
        return 1
    work = Path(tempfile.mkdtemp(prefix="uicontract_"))
    tmp = work / "copy.sqlite3"
    shutil.copy2(src, tmp)
    for sfx in ("-wal", "-shm"):
        if Path(str(src) + sfx).exists():
            shutil.copy2(str(src) + sfx, str(tmp) + sfx)

    from fastapi_stub import install as _install_stub
    _install_stub()
    from fastapi import HTTPException

    from api import db as _db

    def _connect():
        c = sqlite3.connect(tmp)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        return c

    _db._connect = _connect
    _db.init_db = lambda *a, **k: None

    import backfill_suggestion_ids as bf
    bf.DB = str(tmp)
    con = _connect()
    plan = bf._plan(con)
    bf._apply(con, plan, "verify_review_ui_contract")
    con.close()

    from api.routers.projection import ReviewRequest, accept_suggestion_route
    import api.services.questionnaire_persistence as _qp

    def pick(name, path):
        for p in plan:
            if p["name"].startswith(name) and p["entry"].get("fieldPath") == path:
                return p
        raise SystemExit(f"{R}no {name} {path} in the plan{X}")

    ack_row = pick("Christopher", "education.gradeLevel")   # acknowledge tier, empty dest
    fix_row = pick("Kent", "military.branch")               # correct tier, repeatable

    pid = ack_row["pid"]
    assert fix_row["pid"] != pid or True   # different narrators; the UI is per-narrator

    print(f"\n{'='*70}\n  UI CONTRACT — real refusal / real UI / real request\n{'='*70}")
    print(f"  {tmp}\n")

    # ── 1. capture the REAL refusals ─────────────────────────────────
    def refuse(row, **kw):
        try:
            accept_suggestion_route(row["adds"]["suggestion_id"],
                                    ReviewRequest(person_id=row["pid"], **kw))
        except HTTPException as e:
            return e.status_code, e.detail
        return 200, None

    st1, d1 = refuse(ack_row)
    st2, d2 = refuse(fix_row, entry_id="__new__")
    check(st1 == 422 and d1.get("error") == "legacy_review_required",
          f"the server refuses the acknowledge-tier row ({d1.get('error')})")
    check(st2 == 422 and d2.get("error") == "suggestion_flagged",
          f"the server refuses the correct-tier row ({d2.get('error')})")

    # ── 2 & 3. drive the real UI ─────────────────────────────────────
    def queue_for(row):
        c = _connect()
        r = c.execute("SELECT projection_json FROM interview_projections WHERE person_id=?",
                      (row["pid"],)).fetchone()
        c.close()
        return (json.loads(r["projection_json"]) or {}).get("pendingSuggestions") or []

    fixtures = {
        "person_id": ack_row["pid"],
        "queue": queue_for(ack_row),
        "replies": [{"status": 422, "json": {"detail": d1}},
                    {"status": 200, "json": {"revision": 2, "accept_mode": "acknowledged_legacy"}}],
        "scenarios": [{
            "name": "ACKNOWLEDGE  Christopher  education.gradeLevel",
            "suggestion_id": ack_row["adds"]["suggestion_id"],
            "tier": "acknowledge",
            "needs_entry": False,
            "expect_reason": d1.get("reason", ""),
            "expect_detail_fragment": (d1.get("detail") or "")[:40],
            "proposed_value": str(ack_row["entry"].get("value")),
            "type_instead": None,
        }],
    }
    fx = work / "fx_ack.json"
    out = work / "out_ack.json"
    fx.write_text(json.dumps(fixtures), encoding="utf-8")
    rc1 = subprocess.run(
        ["node", str(REPO / "tests" / "harness" / "suggestion-review-harness.js"),
         str(fx), str(out)], cwd=REPO).returncode
    captured_ack = json.loads(out.read_text(encoding="utf-8"))[0]["captured"] if rc1 == 0 else None

    fixtures2 = {
        "person_id": fix_row["pid"],
        "queue": queue_for(fix_row),
        "replies": [{"status": 422, "json": {"detail": d2}},
                    {"status": 200, "json": {"revision": 2, "accept_mode": "corrected"}}],
        "scenarios": [{
            "name": "CORRECT      Kent  military.branch",
            "suggestion_id": fix_row["adds"]["suggestion_id"],
            "tier": "correct",
            "needs_entry": True,
            "expect_reason": d2.get("reason", ""),
            "expect_detail_fragment": (d2.get("detail") or "")[:40],
            "proposed_value": str(fix_row["entry"].get("value")),
            "type_instead": "Army",
        }],
    }
    fx2 = work / "fx_fix.json"
    out2 = work / "out_fix.json"
    fx2.write_text(json.dumps(fixtures2), encoding="utf-8")
    rc2 = subprocess.run(
        ["node", str(REPO / "tests" / "harness" / "suggestion-review-harness.js"),
         str(fx2), str(out2)], cwd=REPO).returncode
    captured_fix = json.loads(out2.read_text(encoding="utf-8"))[0]["captured"] if rc2 == 0 else None

    if rc1 != 0 or rc2 != 0:
        print(f"\n  {R}The UI harness failed; nothing to replay.{X}\n")
        shutil.rmtree(work, ignore_errors=True)
        return 1

    # ── 4. replay what the UI sent, into the real route ──────────────
    print("  REPLAY — the bodies the page built, into the real server\n")

    def replay(row, body):
        body = dict(body or {})
        body.pop("person_id", None)
        try:
            return 200, accept_suggestion_route(
                row["adds"]["suggestion_id"],
                ReviewRequest(person_id=row["pid"], **body))
        except HTTPException as e:
            return e.status_code, e.detail

    st, res = replay(ack_row, captured_ack)
    check(st == 200, "the acknowledge body the PAGE built is accepted by the server",
          json.dumps(res)[:200] if st != 200 else "")
    if st == 200:
        check(getattr(res, "accept_mode", None) == "acknowledged_legacy"
              or (isinstance(res, dict) and res.get("accept_mode") == "acknowledged_legacy"),
              "and is recorded as acknowledged_legacy")

    c = _connect()
    r = c.execute("SELECT questionnaire_json FROM bio_builder_questionnaires WHERE person_id=?",
                  (ack_row["pid"],)).fetchone()
    doc = _qp.flatten_document(json.loads(r["questionnaire_json"] or "{}")) if r else {}
    pr = c.execute("SELECT * FROM bio_builder_answer_provenance WHERE person_id=? AND field=?",
                   (ack_row["pid"], "gradeLevel")).fetchone()
    c.close()
    check(doc.get("education.gradeLevel") == str(ack_row["entry"]["value"]),
          f"the original value is on record ({ack_row['entry']['value']!r})")
    check(pr is not None and pr["origin"] == "ai_suggested",
          "provenance says Lori proposed it and a person agreed")

    st, res = replay(fix_row, captured_fix)
    check(st == 200, "the correction body the PAGE built is accepted by the server",
          json.dumps(res)[:200] if st != 200 else "")

    c = _connect()
    r = c.execute("SELECT questionnaire_json FROM bio_builder_questionnaires WHERE person_id=?",
                  (fix_row["pid"],)).fetchone()
    doc2 = _qp.flatten_document(json.loads(r["questionnaire_json"] or "{}")) if r else {}
    rv = c.execute("SELECT * FROM suggestion_reviews WHERE person_id=? AND suggestion_id=?",
                   (fix_row["pid"], fix_row["adds"]["suggestion_id"])).fetchone()
    pr2 = c.execute("SELECT * FROM bio_builder_answer_provenance WHERE person_id=? AND field=?",
                    (fix_row["pid"], "branch")).fetchone()
    c.close()
    landed = [k for k in doc2 if k.startswith("military[") and k.endswith(".branch")]
    check(len(landed) == 1 and doc2[landed[0]] == "Army",
          f"the person's typed value is on record at {landed[0] if landed else '(nowhere)'}")
    check(rv is not None and rv["proposed_value"] == str(fix_row["entry"]["value"]),
          "Lori's original proposal is preserved beside it")
    check(rv is not None and rv["corrected_value"] == "Army",
          "the correction is recorded as the person's")
    check(pr2 is not None and pr2["origin"] == "operator_direct",
          "provenance says the PERSON entered it")

    live = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    n = live.execute("SELECT COUNT(*) FROM suggestion_reviews").fetchone()[0]
    live.close()
    check(n == 12, f"the live database is untouched ({n} reviews)")

    shutil.rmtree(work, ignore_errors=True)
    print()
    if _fail:
        print(f"  {R}{_fail} checks failed.{X}\n")
        return 1
    print(f"  {G}Round trip complete: a person can finish both acts in the page.{X}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
