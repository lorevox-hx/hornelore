"""Save it, reopen it, restart, and see whether Lori has it.

WO-QUESTIONNAIRE-REACHES-LORI-01 acceptance.

SYNTHETIC NARRATORS ONLY. No family record is read or written. The live
database is not opened at all.

WHAT THIS SHOWS THAT THE UNIT TESTS DO NOT
-------------------------------------------
The tests call `_build_profile_seed` and assert on its output. This
drives the sequence a person actually performs, in the order they
perform it, ACROSS A PROCESS BOUNDARY:

    1. an operator saves a parent's occupation in Bio Builder
    2. the page is reopened and the value is read back
    3. THE PROCESS EXITS — a fresh one starts, as after a restart
    4. the prompt is composed, and the fact is in it

Step 3 is the point. A seed cached in memory would pass steps 1, 2 and
4 in one process and fail a narrator the next morning.

    python3 scripts/verify_questionnaire_reaches_lori.py
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
sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(REPO / "tests" / "harness"))

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


# What a fresh process does: import nothing from this one, read the DB,
# compose. Run as a subprocess so the isolation is real.
_CHILD = r'''
import json, sqlite3, sys
sys.path.insert(0, %(code)r)
sys.path.insert(0, %(tests)r)
from fastapi_stub import install; install()
from api import db as _db
def _c():
    c = sqlite3.connect(%(db)r); c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON"); return c
_db._connect = _c
_db.init_db = lambda *a, **k: None
from api import prompt_composer as pc
seed = pc._build_profile_seed(%(pid)r) or {}
print("@@@" + json.dumps({
    "block": seed.get("biography_block") or "",
    "conflicts": seed.get("biography_conflicts") or [],
    "fact_count": len(seed.get("biography_facts") or []),
}))
'''


def in_a_fresh_process(db, pid):
    src = _CHILD % {"code": str(REPO / "server" / "code"),
                    "tests": str(REPO / "tests"),
                    "db": str(db), "pid": pid}
    p = subprocess.run([sys.executable, "-c", src], capture_output=True, text=True)
    for line in p.stdout.splitlines():
        if line.startswith("@@@"):
            return json.loads(line[3:])
    print(p.stdout[-800:]); print(p.stderr[-800:])
    raise SystemExit(f"{R}the fresh process produced nothing{X}")


def main() -> int:
    import synthetic_narrator as syn

    print(f"\n{'='*72}\n  QUESTIONNAIRE -> LORI — synthetic narrators, across a restart\n{'='*72}\n")
    db = syn.build()
    print(f"  {db}\n")

    # ── 1. an operator fills in the biography ────────────────────────
    doc = {
        "personal": {"fullName": "Alda Quillfeather", "placeOfBirth": "Marrow Bay"},
        "parents": [
            {"_entryId": "e-father", "relation": "father", "firstName": "Bertil",
             "occupation": "ore dock foreman", "birthPlace": "Marrow Bay"},
            {"_entryId": "e-mother", "relation": "mother", "firstName": "Sigrid",
             "occupation": "schoolteacher"},
        ],
    }
    c = sqlite3.connect(db)
    c.execute("UPDATE bio_builder_questionnaires SET questionnaire_json=?, "
              "revision=revision+1 WHERE person_id=?", (json.dumps(doc), syn.ALDA))
    for section, eid, field, origin in (
            ("parents", "e-father", "occupation", "operator_direct"),
            ("parents", "e-mother", "occupation", "operator_direct"),
            ("personal", "", "placeOfBirth", "operator_direct"),
            ("parents", "e-father", "birthPlace", "ai_suggested")):
        c.execute("INSERT OR REPLACE INTO bio_builder_answer_provenance "
                  "(person_id, section, entry_id, field, origin, origin_at) "
                  "VALUES (?,?,?,?,?,?)",
                  (syn.ALDA, section, eid, field, origin, "2026-09-20T00:00:00"))
    c.commit(); c.close()
    print("  1. SAVED  parents[father].occupation = 'ore dock foreman'\n")

    # ── 2. reopened ──────────────────────────────────────────────────
    c = sqlite3.connect(db)
    back = json.loads(c.execute(
        "SELECT questionnaire_json FROM bio_builder_questionnaires WHERE person_id=?",
        (syn.ALDA,)).fetchone()[0])
    c.close()
    print("  2. REOPENED\n")
    check(back["parents"][0]["occupation"] == "ore dock foreman",
          "the value reads back unchanged")
    check(len(back["parents"]) == 2, "both parents survive the round trip")

    # ── 3 & 4. a fresh process composes the prompt ───────────────────
    print("\n  3. FRESH PROCESS — nothing carried over in memory\n")
    out = in_a_fresh_process(db, syn.ALDA)
    block = out["block"]
    check(bool(block), "the biography reached the prompt at all")
    check("ore dock foreman" in block,
          "THE WORK ORDER'S OWN FACT is in Lori's prompt")
    check("schoolteacher" in block, "and so is the second parent's")
    check("Bertil" in block and "Sigrid" in block,
          "each attached to the person it is about")
    check("Lori proposed this" in block,
          "an accepted suggestion is still labelled as one")
    check("ore dock foreman  [" not in block,
          "an operator entry is not labelled — the default carries no marker")
    check("NEVER narrate one of these as the narrator's own memory" in block,
          "facts are not recollections, and the prompt says so")

    # ── 5. a disagreement is shown, not resolved ─────────────────────
    print("\n  5. TWO RECORDS DISAGREE\n")
    c = sqlite3.connect(db)
    c.execute("INSERT OR REPLACE INTO interview_projections "
              "(person_id, projection_json, source, version, updated_at) "
              "VALUES (?,?,?,?,?)",
              (syn.ALDA, json.dumps({
                  "fields": {"personal.placeOfBirth": {
                      "value": "Ferrous Gate", "source": "human_edit", "locked": True}},
                  "pendingSuggestions": []}), "seed", 2, "t"))
    c.commit(); c.close()
    out2 = in_a_fresh_process(db, syn.ALDA)
    b2 = out2["block"]
    check("TWO RECORDS DISAGREE" in b2, "the disagreement is surfaced")
    check("Marrow Bay" in b2, "the form's value is preserved")
    check("Ferrous Gate" in b2, "the competing value is preserved")
    check("ask which is right" in b2, "and Lori is told to ask, not to choose")
    check(len(out2["conflicts"]) == 1,
          f"one conflict recorded ({len(out2['conflicts'])})")

    # ── 6. narrator isolation ────────────────────────────────────────
    print("\n  6. ISOLATION\n")
    other = in_a_fresh_process(db, syn.BRENNIG)
    check("ore dock foreman" not in (other["block"] or ""),
          "the second narrator's prompt has none of the first's biography")
    check("Taught at home by an aunt" in (other["block"] or ""),
          "and does carry their own")

    # ── 7. the queue stays out ───────────────────────────────────────
    print("\n  7. PENDING SUGGESTIONS STAY OUT\n")
    check("4th grade" not in block and "Ferrous Gate battery" not in block,
          "a queued proposal is not in the biography block")

    shutil.rmtree(Path(db).parent, ignore_errors=True)
    print()
    if _fail:
        print(f"  {R}{_fail} checks failed.{X}\n")
        return 1
    print(f"  {G}The saved biography reaches Lori, survives a restart, and "
          f"says what it is.{X}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
