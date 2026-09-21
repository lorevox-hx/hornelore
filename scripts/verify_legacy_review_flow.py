"""Drive REAL legacy suggestions through the REAL review service.

ON A COPY. The live database is opened read-only, copied, and never
written.

WHY A SEPARATE HARNESS
----------------------
`tests/test_suggestion_flags.py` proves the guard against constructed
rows. That is the right shape for a unit test and the wrong evidence for
this question. What has to be shown here is that CHRISTOPHER'S AND
KENT'S OWN queued proposals — the fossils, with their real values, their
real unresolvable turn citations and their real destinations — can be
found by id, are refused when accepted bare, and can be completed by the
act each one actually requires.

The earlier report claimed the thirty were protected at the acceptance
boundary. That claim was measured against rows whose ids I had invented
for the measurement. This runs against the ids the backfill actually
assigns.

    python3 scripts/verify_legacy_review_flow.py
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))
sys.path.insert(0, str(REPO / "scripts"))

DB = os.environ.get("HORNELORE_DB", "/mnt/c/hornelore_data/db/hornelore.sqlite3")
G, R, Y, X = "\033[32m", "\033[31m", "\033[33m", "\033[0m"

_fail = 0


def check(good: bool, msg: str, detail: str = "") -> None:
    global _fail
    if good:
        print(f"    {G}PASS{X}  {msg}")
    else:
        _fail += 1
        print(f"    {R}FAIL{X}  {msg}")
        if detail:
            print(f"          {detail}")


def main() -> int:
    src = Path(DB)
    if not src.exists():
        print(f"{R}No database at {DB}{X}")
        return 1
    tmp = Path(tempfile.mkdtemp(prefix="flowverify_")) / "copy.sqlite3"
    shutil.copy2(src, tmp)
    for sfx in ("-wal", "-shm"):
        if Path(str(src) + sfx).exists():
            shutil.copy2(str(src) + sfx, str(tmp) + sfx)

    print(f"\n{'='*74}\n  LEGACY REVIEW FLOW — real suggestions, on a copy\n{'='*74}")
    print(f"  {tmp}\n")

    from api import db as _db

    def _connect():
        c = sqlite3.connect(tmp)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        return c

    _db._connect = _connect
    _db.init_db = lambda *a, **k: None

    # ── step 1: the backfill, through its own code ───────────────────
    import backfill_suggestion_ids as bf
    bf.DB = str(tmp)
    con = _connect()
    plan = bf._plan(con)
    bf._apply(con, plan, "verify_legacy_review_flow")
    con.close()
    print(f"  Identified {len(plan)} pre-cutover entries.\n")

    from api.services import suggestion_review as sr
    from api.services import suggestion_flags as flags
    import api.services.questionnaire_persistence as _qp

    def q(pid):
        c = _connect()
        r = c.execute("SELECT questionnaire_json FROM bio_builder_questionnaires "
                      "WHERE person_id=?", (pid,)).fetchone()
        c.close()
        return _qp.flatten_document(json.loads(r["questionnaire_json"] or "{}")) if r else {}

    def queue(pid):
        c = _connect()
        r = c.execute("SELECT projection_json FROM interview_projections "
                      "WHERE person_id=?", (pid,)).fetchone()
        c.close()
        return (json.loads(r["projection_json"] or "{}") or {}).get("pendingSuggestions") or []

    def review_of(pid, sid):
        c = _connect()
        r = c.execute("SELECT * FROM suggestion_reviews WHERE person_id=? AND suggestion_id=?",
                      (pid, sid)).fetchone()
        c.close()
        return dict(r) if r else None

    def prov(pid, section, field):
        c = _connect()
        r = c.execute("SELECT * FROM bio_builder_answer_provenance WHERE person_id=? "
                      "AND section=? AND field=?", (pid, section, field)).fetchall()
        c.close()
        return [dict(x) for x in r]

    def pick(name_starts, path):
        for p in plan:
            if p["name"].startswith(name_starts) and p["entry"].get("fieldPath") == path:
                return p
        raise SystemExit(f"{R}could not find {name_starts} {path} in the plan{X}")

    # ══ CASE 1 — an ACKNOWLEDGE row at a destination that always existed
    #
    # `education.gradeLevel` and not `education.schooling`, which was the
    # first pick and turned out to be a better test of something else:
    # that destination already holds "Graduated from Bismarck High
    # School, 1981", so the C3 conflict rule refuses the acceptance
    # before either tier is reached. Nine of the nineteen are like that.
    # Case 4 covers it deliberately; this case needs an empty
    # destination to exercise the acknowledge path at all.
    p = pick("Christopher", "education.gradeLevel")
    pid, sid = p["pid"], p["adds"]["suggestion_id"]
    val = p["entry"]["value"]
    print(f"  CASE 1  Christopher  education.gradeLevel = {val!r}")
    print(f"          {sid}   (legacy, destination existed all along)\n")

    c = _connect()
    found = sr.find_suggestion(c, pid, sid)
    c.close()
    check(found is not None, "addressable by its new id through find_suggestion()")
    check(found and found.get("value") == val, "the value it finds is the original, unchanged")
    check(found and "destination_undefined" not in found,
          "still legacy — destination_undefined was not written")

    before_q, before_queue = q(pid), len(queue(pid))
    try:
        sr.accept(pid, sid)
        check(False, "bare acceptance is refused", "IT WAS ACCEPTED")
    except flags.SuggestionFlagged as e:
        check(e.requirement == flags.REQUIRE_ACKNOWLEDGE,
              f"bare acceptance refused at the acknowledge tier ({e.reason})")
    check(q(pid) == before_q, "nothing was written by the refusal")
    check(len(queue(pid)) == before_queue, "still queued after the refusal")

    res = sr.accept(pid, sid, acknowledge_legacy=True, reviewed_by="chris")
    after = q(pid)
    check(after.get("education.gradeLevel") == val,
          f"acknowledged acceptance persisted the ORIGINAL value ({val!r})")
    check(res.get("accept_mode") == "acknowledged_legacy",
          "recorded as acknowledged_legacy, not as an ordinary accept")
    rv = review_of(pid, sid)
    check(rv is not None and rv["verdict"] == "accepted", "a review record exists")
    check(rv and rv["accept_mode"] == "acknowledged_legacy", "the record says how it was accepted")
    check(rv and rv["corrected_value"] is None, "nothing recorded as a correction")
    check(rv and rv["proposed_value"] == val, "the original proposal is preserved on the record")
    check(rv and rv["turn_evidence"] == "unverified",
          "the measured turn verdict travelled onto the record")
    pr = [x for x in prov(pid, "education", "gradeLevel")]
    check(len(pr) == 1 and pr[0]["origin"] == "ai_suggested",
          "provenance: still Lori's value, not laundered into an operator entry")
    check(len(pr) == 1 and pr[0]["confirmed_via"] == "acceptance",
          "provenance: carries the confirmation")
    check(len(queue(pid)) == before_queue - 1, "removed from the queue")
    check(all(s.get("suggestion_id") != sid for s in queue(pid)), "and only that one")

    # ══ CASE 2 — a CORRECT row, repeatable section, Kent's missile site
    p = pick("Kent", "military.branch")
    pid2, sid2 = p["pid"], p["adds"]["suggestion_id"]
    val2 = p["entry"]["value"]
    print(f"\n  CASE 2  Kent  military.branch = {val2!r}")
    print(f"          {sid2}   (legacy, section created by WO-04)\n")

    check(p["adds"].get("destination_unresolved") is True,
          "carries destination_unresolved, so the surface draws an entry picker")

    before_q2, before_queue2 = q(pid2), len(queue(pid2))
    try:
        sr.accept(pid2, sid2, entry_id="__new__")
        check(False, "bare acceptance is refused", "IT WAS ACCEPTED")
    except flags.SuggestionFlagged as e:
        check(e.requirement == flags.REQUIRE_CORRECT,
              f"bare acceptance refused at the correct tier ({e.reason})")

    try:
        sr.accept(pid2, sid2, entry_id="__new__", acknowledge_legacy=True)
        check(False, "a checkbox does NOT satisfy the correct tier", "IT WAS ACCEPTED")
    except flags.SuggestionFlagged as e:
        check(e.requirement == flags.REQUIRE_CORRECT,
              "a checkbox does NOT satisfy the correct tier — still refused")
    check(q(pid2) == before_q2, "nothing written by either refusal")
    check(len(queue(pid2)) == before_queue2, "still queued after both refusals")

    try:
        sr.accept(pid2, sid2, entry_id="__new__", corrected_value=val2)
        check(False, "an identical 'correction' is refused", "IT WAS ACCEPTED")
    except flags.SuggestionFlagged:
        check(True, "an identical 'correction' is refused as no correction at all")

    res2 = sr.accept(pid2, sid2, entry_id="__new__", corrected_value="Army",
                     correction_reason="value_not_a_field", reviewed_by="chris")
    a2 = q(pid2)
    landed = [k for k in a2 if k.startswith("military[") and k.endswith(".branch")]
    check(len(landed) == 1 and a2[landed[0]] == "Army",
          f"the corrected value persisted at {landed[0] if landed else '(nowhere)'}")
    check(res2.get("accept_mode") == "corrected", "recorded as corrected")
    rv2 = review_of(pid2, sid2)
    check(rv2 and rv2["proposed_value"] == val2,
          "Lori's original proposal is preserved beside the correction")
    check(rv2 and rv2["corrected_value"] == "Army", "the person's value is recorded separately")
    pr2 = prov(pid2, "military", "branch")
    check(len(pr2) == 1 and pr2[0]["origin"] == "operator_direct",
          "provenance: a corrected acceptance is the PERSON'S entry")
    check(len(pr2) == 1 and not pr2[0]["confirmed_via"],
          "provenance: no confirmed_via — nothing of Lori's was confirmed")
    check(len(queue(pid2)) == before_queue2 - 1, "removed from the queue")

    # ══ CASE 3 — decline, which must stay easy
    p = pick("Kent", "military.rank")
    pid3, sid3 = p["pid"], p["adds"]["suggestion_id"]
    print(f"\n  CASE 3  Kent  military.rank  (decline)\n")
    n3 = len(queue(pid3))
    q3 = q(pid3)
    sr.decline(pid3, sid3, reviewed_by="chris")
    check(len(queue(pid3)) == n3 - 1, "declining a flagged legacy proposal is not blocked")
    check(q(pid3) == q3, "a decline writes no biographical answer")
    rv3 = review_of(pid3, sid3)
    check(rv3 and rv3["verdict"] == "declined", "the refusal is on the record")
    check(rv3 and rv3["accept_mode"] is None, "accept_mode is NULL on a decline")

    # ══ CASE 4 — a third layer nobody designed for this, doing real work
    #
    # Nine of the nineteen legacy proposals at defined destinations aim
    # at fields that ALREADY HOLD a better answer. Ruling C3's conflict
    # refusal catches those before either review tier is consulted, and
    # it is the strongest of the three because it needs no flag, no
    # acknowledgement and no correction — there is simply a real answer
    # there and a machine does not get to replace it by one click.
    #
    # `personal.fullName` is the emblem: the queue proposes "kind of
    # scared" and the record already says "Christopher Todd Horne".
    p = pick("Christopher", "personal.fullName")
    pid4, sid4 = p["pid"], p["adds"]["suggestion_id"]
    val4 = p["entry"]["value"]
    print(f"\n  CASE 4  Christopher  personal.fullName = {val4!r}")
    print(f"          the record already holds a real name\n")

    q4, n4 = q(pid4), len(queue(pid4))
    for kw in ({}, {"acknowledge_legacy": True}):
        try:
            sr.accept(pid4, sid4, **kw)
            check(False, f"refused with {kw or 'nothing'}", "IT WAS ACCEPTED")
        except sr.SuggestionConflict as e:
            check(str(e.stored) == q4.get("personal.fullName"),
                  f"refused as a conflict, naming the stored value "
                  f"({str(e.stored)[:30]!r})")
        except flags.SuggestionFlagged:
            check(True, f"refused by the review tier with {kw or 'nothing'}")
    check(q(pid4) == q4, "the real name is untouched by every attempt")
    check(len(queue(pid4)) == n4, "and the proposal is still queued, not silently dropped")

    # ══ the untouched promise
    print(f"\n  UNTOUCHED\n")
    c = _connect()
    others = c.execute(
        "SELECT COUNT(*) FROM suggestion_reviews WHERE person_id NOT IN (?,?,?)",
        (pid, pid2, pid3)).fetchone()[0]
    c.close()
    check(others == 12, f"the 12 pre-existing ZZ review records are intact ({others})")
    live = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    n_live = live.execute("SELECT COUNT(*) FROM suggestion_reviews").fetchone()[0]
    nf_live = live.execute("SELECT COUNT(*) FROM suggestion_flags").fetchone()[0]
    live.close()
    check(n_live == 12, f"the LIVE database still has 12 reviews ({n_live}) — not touched")
    check(nf_live == 0, f"the LIVE database still has 0 flags ({nf_live}) — not touched")

    shutil.rmtree(tmp.parent, ignore_errors=True)
    print()
    if _fail:
        print(f"  {R}{_fail} checks failed.{X}\n")
        return 1
    print(f"  {G}Every check passed. The copy was discarded.{X}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
