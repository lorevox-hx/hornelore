"""The two Phase 1 suites must coexist in one interpreter.

WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01 Phase 1 isolation correction,
2026-08-12.

Running the required verification command --

    python -m unittest tests.test_trip_photo_day_placements \\
                       tests.test_trip_photo_day_placements_full_chain

-- produced 2 failures and 12 errors while each suite passed alone.
Repository calls were reading a database with no ``trip_days`` and no
``trip_photo_links``.

Measured cause, not inferred: each suite deleted ``api.db`` from
``sys.modules`` at import time and re-imported it, so two module objects
existed (``A.db is B.db`` was False) while ``trip_repository`` stayed
shared (``A.repo is B.repo`` was True). ``trip_repository._connect()``
late-imports ``from .. import db``, resolving ``sys.modules["api.db"]``
at CALL time -- the second object. The first suite therefore created its
schema in one file and the repository read another.

THIS SUITE ASSERTS THE MECHANISM, NOT THE SYMPTOM. "The combined command
is green" is what the reviewer already has; it would also be green if
both suites silently stopped exercising anything. These tests import
both modules into this interpreter and check the properties that make
the green result mean something: one live ``api.db``, a repository whose
connection resolves to the bound file, and a binding that is restored
afterwards.

Run per-module:
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_trip_photo_placement_suite_isolation
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(_REPO_ROOT / "server" / "code"), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tests import trip_db_binding as binding  # noqa: E402

# Import BOTH suites, in the order the failing command loaded them.
import tests.test_trip_photo_day_placements as suite_minimal  # noqa: E402
import tests.test_trip_photo_day_placements_full_chain as suite_chain  # noqa: E402

import api.db as db  # noqa: E402
from api.services import trip_repository as repo  # noqa: E402


class ModuleIdentityTest(unittest.TestCase):
    """The precise conditions that produced the 12 errors."""

    def test_there_is_exactly_one_live_api_db_module(self):
        self.assertIs(suite_minimal.db, suite_chain.db,
                      "api.db is forked: the two suites hold different "
                      "module objects, so DB_PATH set by one is invisible "
                      "to the repository used by the other")
        self.assertIs(suite_minimal.db, sys.modules["api.db"])
        self.assertIs(db, sys.modules["api.db"])

    def test_the_repository_is_shared_which_is_why_forking_db_breaks_it(self):
        self.assertIs(suite_minimal.repo, suite_chain.repo)
        self.assertIs(suite_minimal.repo, repo)

    def test_neither_suite_removes_api_db_from_sys_modules(self):
        """A source check, deliberately: the delete happens at IMPORT
        time, so by the time any behavioural test runs the damage is
        either already done or already avoided. This is the one property
        that has to be asserted against the text."""
        for mod in (suite_minimal, suite_chain):
            src = Path(mod.__file__).read_text(encoding="utf-8")
            stripped = "\n".join(
                l for l in src.split("\n") if not l.strip().startswith("#"))
            self.assertNotIn("del sys.modules[", stripped,
                             "%s deletes a module from sys.modules; that "
                             "forks api.db" % Path(mod.__file__).name)


class BindingResolvesToOneDatabaseTest(unittest.TestCase):
    """Schema-creation path and repository path must be the same file."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="hl-isolation-")
        self.path = os.path.join(self.tmp, "bound.sqlite3")

    def test_bind_db_points_the_repository_at_the_test_database(self):
        binding.bind_db(self, repo, self.path)
        self.assertEqual(
            os.path.abspath(binding.connected_path(repo)),
            os.path.abspath(self.path))

    def test_bind_db_refuses_a_binding_that_did_not_take(self):
        """Non-vacuity for bind_db's proof step.

        REWRITTEN 2026-08-12: the first version performed its own
        set-then-revert dance and asserted on an AssertionError it raised
        itself, so it tested the test and would have passed with bind_db
        deleted entirely. This drives the REAL function against a
        repository whose connection ignores DB_PATH -- exactly what the
        forked-module bug did -- and requires bind_db to notice.
        """
        import sqlite3
        import types

        elsewhere = os.path.join(self.tmp, "not-the-bound-one.sqlite3")

        fake_repo = types.SimpleNamespace(
            _connect=lambda: sqlite3.connect(elsewhere))

        live = binding.live_db_module()
        previous = live.DB_PATH
        try:
            with self.assertRaises(AssertionError) as caught:
                binding.bind_db(self, fake_repo, self.path)
            self.assertIn("binding failed", str(caught.exception))
        finally:
            live.DB_PATH = previous

    def test_the_binding_is_restored_after_the_test(self):
        """A suite must not leak its temporary database into the next
        one -- the other half of the same isolation failure."""
        live = binding.live_db_module()
        before = live.DB_PATH

        class _Case(unittest.TestCase):
            def runTest(self):
                binding.bind_db(self, repo, os.path.join(
                    tempfile.mkdtemp(prefix="hl-leak-"), "x.sqlite3"))

        case = _Case()
        result = case.run()
        self.assertTrue(result.wasSuccessful(), "inner binding failed")
        self.assertEqual(live.DB_PATH, before,
                         "DB_PATH leaked out of the test that set it")


class CombinedRunIsNotVacuousTest(unittest.TestCase):
    """Green is only meaningful if the suites still exercise something."""

    def test_both_suites_still_carry_their_tests(self):
        loader = unittest.TestLoader()
        n_min = loader.loadTestsFromModule(suite_minimal).countTestCases()
        n_chain = loader.loadTestsFromModule(suite_chain).countTestCases()
        self.assertGreaterEqual(n_min, 46, "the minimal-schema suite shrank")
        self.assertGreaterEqual(n_chain, 12, "the full-chain suite shrank")
        self.assertGreaterEqual(n_min + n_chain, 58)


if __name__ == "__main__":
    unittest.main()
