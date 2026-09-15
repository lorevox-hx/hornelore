"""WO-LOREVOX-CLEAN-DATA-WORLD-01 (Phase 7) — what may a bulk purge delete?

THE DEFECT THIS PINS, found while removing the Horne family lock:

`lvBbPurgeTestNarrators` defined "test narrator" as EVERY NARRATOR NOT ON A
FIVE-NAME WHITELIST (three Hornes and two trainers) and soft-deleted all of
them. On the Horne laptop that reads as a tidy-up. On a clean Lorevox root it
deletes every narrator in the installation, because nobody there is on the
list — and a restored narrator whose display name differs by one character
from the hard-coded string is not on the list either. Inverting a name
whitelist is a heuristic, and the most dangerous kind: everything unknown
falls on the DELETE side.

THE BOUNDARY, and why it is this one. `people.testing_only` is set explicitly
at narrator creation, is persisted, and is deliberately not mutable through
PersonUpdate — which is why the server already treats it as the fail-closed
authority for experimental eligibility (`person_is_testing_only`,
`list_testing_only_people`). A narrator's NAME is not a disposition. A real
narrator may be called "Tess Terry"; a testing-only narrator may be called
"Margaret Wilson". Nothing about how a name reads may decide a deletion.

`lv80NarratorKind()` stays heuristic and stays PRESENTATION-ONLY: it picks a
badge, and a wrong badge is a cosmetic defect. These tests hold the line
between the two — the heuristic classifier and the destructive selector must
never be the same function, and the destructive one must fail closed when the
disposition is absent.

Both boundaries are exercised against SHIPPED code: the Python side against a
real SQLite database through `db.list_people`, the JavaScript side by
evaluating the shipped predicates out of the source files under node.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_HTML = _REPO / "ui" / "hornelore1.0.html"
_BBCORE = _REPO / "ui" / "js" / "bio-builder-core.js"


# --------------------------------------------------------------------------
# JavaScript side — the shipped predicates, run under node
# --------------------------------------------------------------------------

def _node(script: str, *args: str):
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node not available")
    out = subprocess.run([node, "-e", script, *args],
                         capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise AssertionError(out.stderr[:600])
    return json.loads(out.stdout.strip())


_ELIGIBLE_HARNESS = r"""
const fs = require('fs');
const s = fs.readFileSync(process.argv[1], 'utf8');
const i = s.indexOf('function _isPurgeEligible');
const j = s.indexOf('function _setPurgeStatus');
if (i < 0 || j < 0 || j < i) {
  console.log(JSON.stringify({error: 'purge predicate not found in bio-builder-core.js'}));
  process.exit(0);
}
eval(s.slice(i, j));
const people = JSON.parse(process.argv[2]);
console.log(JSON.stringify(people.filter(_isPurgeEligible).map(p => p.id)));
"""


_KIND_HARNESS = r"""
const fs = require('fs');
const s = fs.readFileSync(process.argv[1], 'utf8');
const i = s.indexOf('function lv80NarratorKind');
const j = s.indexOf('function lv80CalcAge');
if (i < 0 || j < 0 || j < i) {
  console.log(JSON.stringify({error: 'lv80NarratorKind not found in hornelore1.0.html'}));
  process.exit(0);
}
eval(s.slice(i, j));
const people = JSON.parse(process.argv[2]);
console.log(JSON.stringify(people.map(lv80NarratorKind)));
"""


def _purge_eligible_ids(people):
    got = _node(_ELIGIBLE_HARNESS, str(_BBCORE), json.dumps(people))
    if isinstance(got, dict) and got.get("error"):
        raise AssertionError(got["error"])
    return got


def _kinds(people):
    got = _node(_KIND_HARNESS, str(_HTML), json.dumps(people))
    if isinstance(got, dict) and got.get("error"):
        raise AssertionError(got["error"])
    return got


class PurgeEligibilityTests(unittest.TestCase):
    """Only the persisted disposition may select a narrator for deletion."""

    def test_test_looking_name_is_not_purge_eligible(self):
        # Every one of these would have been classified "test" by the badge
        # heuristic, and every one of them is a real narrator.
        people = [
            {"id": "r1", "display_name": "Test Pilot Reunion", "testing_only": False},
            {"id": "r2", "display_name": "Sherlock Holmes", "testing_only": False},
            {"id": "r3", "display_name": "Tess Terry", "testing_only": False},
            {"id": "r4", "display_name": "Walter", "role": "test",
             "testing_only": False},
            {"id": "r5", "display_name": "Corky", "is_test": True,
             "testing_only": False},
        ]
        self.assertEqual(
            _purge_eligible_ids(people), [],
            "a real narrator was selected for deletion because of how its "
            "NAME or a presentation hint reads")

    def test_ordinary_name_with_testing_only_is_purge_eligible(self):
        people = [
            {"id": "t1", "display_name": "Margaret Wilson", "testing_only": True},
            {"id": "r1", "display_name": "Margaret Wilson", "testing_only": False},
        ]
        # Same name, opposite dispositions: the name decides nothing.
        self.assertEqual(_purge_eligible_ids(people), ["t1"])

    def test_absence_from_any_whitelist_does_not_make_a_narrator_eligible(self):
        # THE ORIGINAL DEFECT. None of these is a Horne or a trainer, so the
        # old purge would have deleted all four.
        people = [
            {"id": "a", "display_name": "Mary Okonkwo", "testing_only": False},
            {"id": "b", "display_name": "Giuseppe Rossi", "testing_only": False},
            {"id": "c", "display_name": "Kent James Horn", "testing_only": False},
            {"id": "d", "display_name": "", "testing_only": False},
        ]
        self.assertEqual(
            _purge_eligible_ids(people), [],
            "the purge still treats 'not on a known list' as 'delete me'")

    def test_a_missing_disposition_fails_closed(self):
        # An older server, a partial payload, a row predating the column.
        # Absence is not permission.
        people = [
            {"id": "u1", "display_name": "Unknown Provenance"},
            {"id": "u2", "display_name": "Null Disposition", "testing_only": None},
            {"id": "u3", "display_name": "Stringly Typed", "testing_only": "true"},
            {"id": "u4", "display_name": "Integer One", "testing_only": 1},
        ]
        self.assertEqual(
            _purge_eligible_ids(people), [],
            "a non-boolean or absent testing_only was read as permission to "
            "delete — the predicate must require a literal true")

    def test_empty_root_purges_nothing(self):
        self.assertEqual(_purge_eligible_ids([]), [])


class PurgeSelectorSourceTests(unittest.TestCase):
    """The selector must BE the predicate, and the whitelist must be gone.

    Source assertions are never acceptance evidence on their own — the
    behavioural tests above are. These catch the specific regression where the
    predicate survives but something else does the selecting.
    """

    def setUp(self):
        self.src = _BBCORE.read_text(encoding="utf-8")

    def test_the_canonical_name_whitelist_is_gone(self):
        for token in ("_CANONICAL_NARRATOR_NAMES", "_isCanonicalNarrator"):
            self.assertNotIn(
                token + " =", self.src,
                f"{token} is back — the purge has a name whitelist again")

    def test_the_purge_selects_through_the_predicate(self):
        self.assertIn("filter(_isPurgeEligible)", self.src,
                      "the purge no longer selects through _isPurgeEligible")

    def test_the_purge_loop_reasserts_before_deleting(self):
        # The check must sit next to the delete, not only next to the filter.
        body = self.src[self.src.index("async function lvBbPurgeTestNarrators"):]
        self.assertLess(
            body.index("if (!_isPurgeEligible(narrator))"),
            body.index("_softDeleteNarrator(pid)"),
            "nothing re-checks eligibility immediately before the delete")


class NarratorKindTests(unittest.TestCase):
    """The badge prefers the persisted disposition; heuristics are fallback."""

    def test_testing_only_wins_over_an_ordinary_name(self):
        self.assertEqual(
            _kinds([{"id": "t", "display_name": "Margaret Wilson",
                     "testing_only": True}]),
            ["test"],
            "a testing-only narrator with an ordinary name is badged as real")

    def test_a_real_narrator_is_not_demoted_by_the_flag_being_false(self):
        self.assertEqual(
            _kinds([{"id": "r", "display_name": "Margaret Wilson",
                     "testing_only": False}]),
            ["real"])

    def test_heuristics_still_classify_rows_without_the_field(self):
        # Historical fixtures predating the column keep their badge.
        self.assertEqual(
            _kinds([{"id": "h", "display_name": "Walter Test Harness"}]),
            ["test"])

    def test_a_heuristic_hit_is_not_a_deletion(self):
        # The two classifiers MUST disagree here, and that disagreement is the
        # whole point: badge says "test", purge says "not eligible".
        person = {"id": "x", "display_name": "Sherlock Holmes",
                  "testing_only": False}
        self.assertEqual(_kinds([person]), ["test"])
        self.assertEqual(_purge_eligible_ids([person]), [])


# --------------------------------------------------------------------------
# Python side — list_people must actually carry the disposition
# --------------------------------------------------------------------------

class ListPeopleCarriesDispositionTests(unittest.TestCase):
    """`/api/people` is the payload every client purges and badges from.

    Isolation is load-bearing here for the reason
    tests/test_people_testing_only_persistence.py records: `db.py` resolves
    DB_PATH at IMPORT time from a RELATIVE default, so a suite that forgets to
    repoint it creates narrators in the developer's real database.
    """

    def setUp(self):
        import importlib

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._prev = {k: os.environ.get(k) for k in ("DATA_DIR", "DB_NAME")}

        os.environ["DATA_DIR"] = self._tmp.name
        os.environ["DB_NAME"] = "test_purge_eligibility.sqlite3"

        from api import db as _db
        importlib.reload(_db)
        self.db = _db
        self.db.init_db()

        self.assertTrue(
            str(self.db.DB_PATH).startswith(self._tmp.name),
            f"Refusing to run against {self.db.DB_PATH} — this suite creates "
            "and deletes narrators")

    def tearDown(self):
        import importlib

        for key, value in self._prev.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        from api import db as _db
        importlib.reload(_db)

    def _rows_by_name(self, **kwargs):
        return {r["display_name"]: r for r in self.db.list_people(**kwargs)}

    def test_list_people_exposes_testing_only_as_a_bool(self):
        self.db.create_person(display_name="Real Person", testing_only=False)
        self.db.create_person(display_name="Synthetic Person", testing_only=True)

        rows = self._rows_by_name()
        self.assertIn("testing_only", rows["Real Person"],
                      "list_people does not carry testing_only, so no client "
                      "reading this payload can tell a test narrator apart")

        for name, expected in (("Real Person", False), ("Synthetic Person", True)):
            with self.subTest(name=name):
                value = rows[name]["testing_only"]
                self.assertIs(
                    type(value), bool,
                    f"{name}.testing_only is {type(value).__name__}, not bool "
                    "— an integer 0 is truthy-by-presence to a JS client")
                self.assertEqual(value, expected)

    def test_include_deleted_branch_carries_it_too(self):
        # The two SELECTs are separate statements; fixing one is how they drift.
        self.db.create_person(display_name="Synthetic Person", testing_only=True)
        rows = self._rows_by_name(include_deleted=True)
        self.assertIs(rows["Synthetic Person"]["testing_only"], True)

    def test_the_single_person_route_still_agrees(self):
        # get_person() already exposed it. The two must not disagree.
        pid = self.db.create_person(display_name="Synthetic Person",
                                    testing_only=True)["id"]
        listed = self._rows_by_name()["Synthetic Person"]["testing_only"]
        single = self.db.get_person(pid)["testing_only"]
        self.assertEqual(listed, single)
        self.assertIs(single, True)


if __name__ == "__main__":
    unittest.main()
