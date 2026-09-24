"""Batch C-2 — Questionnaire V2 shell: open / navigate / switch write
nothing; an edit is a narrator-scoped, revision-stamped draft; Save is one
PATCH of writer operations; a stale save is a shown conflict.

Drives tests/qv2_shell_harness.js (jsdom + the shipped UI files), whose
fake fetch hands every Life Record request to tests/qv2_bridge.py — the
shipped writer on this test's real SQLite. The UI checks are reported by
the harness; the database is then checked HERE, because "the UI said it
saved" is not "the record changed".

Skips (and says so) without node or jsdom.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))
sys.path.insert(0, str(REPO))

from api import db as _db  # noqa: E402
from tests.test_life_record_writer import NORA, OWEN, _Db  # noqa: E402

NODE = shutil.which("node")
FRESH = "narrator-fresh-fictional"
HAVE_JSDOM = bool(NODE) and subprocess.run(
    [NODE, "-e", "require('jsdom')"], cwd=REPO, capture_output=True).returncode == 0


@unittest.skipUnless(HAVE_JSDOM, "node + jsdom are required — npm install")
class QuestionnaireV2Shell(_Db):
    def setUp(self):
        super().setUp()
        self.ok([self.name(NORA, "n1", "Ines Maribel Okafor-Lund"),
                 self.assertion("bo", "person", NORA, "person.birth.order", "second of four")])
        self.ok([self.name(OWEN, "o1", "Owen Marsh")], nid=OWEN)
        # FRESH: a people row and NOTHING in the Life Record. The live smoke
        # (2026-09-24) failed on exactly this narrator; the first harness
        # pre-seeded every narrator and so could not see it.
        con = sqlite3.connect(str(_db.DB_PATH))
        con.execute("INSERT INTO people(id, display_name, created_at, updated_at) VALUES (?,?,?,?)",
                    (FRESH, "Fresh Fictional", "2026-09-24T00:00:00Z", "2026-09-24T00:00:00Z"))
        con.commit()
        con.close()
        self.assertEqual(self.rows("SELECT count(*) FROM lr_record WHERE narrator_id=?", FRESH), [(0,)])
        env = {"QV2_DB": str(_db.DB_PATH), "QV2_PY": sys.executable, "QV2_A": NORA, "QV2_B": OWEN,
               "QV2_FRESH": FRESH,
               "PATH": __import__("os").environ.get("PATH", "")}
        out = subprocess.run([NODE, str(REPO / "tests" / "qv2_shell_harness.js")], cwd=REPO, env=env,
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr[-2000:])
        self.result = json.loads(out.stdout)
        self.assertNotIn("error", self.result, self.result.get("error"))

    def rows(self, sql, *args):
        con = sqlite3.connect(str(_db.DB_PATH))
        try:
            return con.execute(sql, args).fetchall()
        finally:
            con.close()

    def test_the_shell_contract_in_the_dom_and_in_the_database(self):
        failed = [c for c in self.result["checks"] if not c["ok"]]
        self.assertEqual(failed, [], "\n".join(f"{c['name']}: {c['why']}" for c in failed))
        self.assertGreaterEqual(len(self.result["checks"]), 30)

        # Nora: exactly ONE write happened — the Save. The stale tab's save,
        # the opens, the navigation and the switches wrote nothing.
        revs = self.rows("SELECT revision, actor FROM lr_revisions WHERE narrator_id=? ORDER BY revision", NORA)
        self.assertEqual(revs, [(1, "operator:test"), (2, "operator")])
        self.assertEqual(self.result["facts"]["savedRevision"], 2)

        # the correction kept history: old account superseded and linked, new one live
        a = {r[0]: r[1:] for r in self.rows(
            "SELECT id, value_json, status, superseded_by_id, supersedes_id, source, asserted_by, recorded_by "
            "FROM lr_assertions WHERE narrator_id=? AND concept_id='person.birth.order'", NORA)}
        new = [k for k in a if k != "bo"]
        self.assertEqual(len(new), 1)
        self.assertEqual(a["bo"][:3], ('"second of four"', "superseded", new[0]))
        self.assertEqual(a[new[0]], ('"the middle child"', "operator_entered", None, "bo",
                                     "operator", "operator", "operator"),
                         "operator-typed: recorded by AND asserted by the operator, never the narrator")

        # Owen: one first-answer write; nothing from Nora's tabs leaked across
        owen = self.rows("SELECT concept_id, value_json FROM lr_assertions WHERE narrator_id=?", OWEN)
        self.assertEqual(owen, [("person.birth.order", '"only child"')])

        # Fresh: the UI's first write created the record AND the narrator's
        # own person, through the writer — no GET and no fixture did it.
        self.assertEqual(self.rows("SELECT revision FROM lr_record WHERE narrator_id=?", FRESH), [(1,)])
        self.assertEqual(self.rows("SELECT id FROM lr_people WHERE narrator_id=?", FRESH), [(FRESH,)])
        self.assertEqual(self.rows("SELECT value_json FROM lr_assertions WHERE narrator_id=?", FRESH),
                         [('"first of two"',)])


if __name__ == "__main__":
    unittest.main()
