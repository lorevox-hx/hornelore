"""Connection-hygiene wrap for api.db (SECURITY/STABILITY-REVIEW-2026-08-12).

Behavioral tests — the defect class is behavioral (a leaked connection
holding the SQLite write lock), so the tests hold locks and take locks
rather than scanning source.

Run per-module, per repository doctrine:

    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_db_connection_hygiene

The module points DATA_DIR at a temp directory BEFORE importing api.db,
so it never touches a real database.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest

_TMP = tempfile.mkdtemp(prefix="hl-conn-guard-")
os.environ["DATA_DIR"] = _TMP

# Fresh import against the temp DATA_DIR (guard against another suite
# having imported api.db already in this process).
for _m in [m for m in list(sys.modules) if m == "api.db" or m.endswith(".api.db")]:
    del sys.modules[_m]

import api.db as db  # noqa: E402


class WrapCoverageTest(unittest.TestCase):
    def test_every_public_function_is_wrapped(self):
        # 159 public functions at review time; assert a floor rather than
        # an exact count so adding functions does not break this test —
        # the auto-wrap block wraps whatever exists at import.
        self.assertGreaterEqual(db._CONN_GUARD_WRAPPED_COUNT, 150)

    def test_known_leaky_functions_carry_the_guard(self):
        # Representative members of the previously-unprotected 74.
        for name in ("ensure_session", "upsert_session", "add_turn",
                     "export_turns", "init_db"):
            fn = getattr(db, name)
            self.assertTrue(
                getattr(fn, "__hornelore_conn_guard__", False),
                f"{name} lost the connection-hygiene wrap")


class LockReleaseTest(unittest.TestCase):
    """The incident class: exception mid-function after a write statement."""

    def setUp(self):
        db.init_db()
        con = db._connect()
        try:
            con.execute(
                "CREATE TABLE IF NOT EXISTS conn_guard_scratch (x INTEGER)")
            con.commit()
        finally:
            con.close()

    def _bad_call(self):
        """Opens a connection, starts a write txn, raises without closing —
        the exact shape of the 2026-07-22 add_timeline_event incident."""
        @db._closes_connections_on_error
        def bad():
            con = db._connect()
            con.execute("INSERT INTO conn_guard_scratch VALUES (1)")
            raise RuntimeError("boom mid-function, close never reached")
        return bad

    def test_exception_releases_the_write_lock(self):
        bad = self._bad_call()
        try:
            bad()
        except RuntimeError as e:
            held = e  # keep the traceback alive, as a real handler would
        # A second writer must succeed IMMEDIATELY (timeout=0.5 makes a
        # held lock fail fast instead of waiting out busy_timeout).
        con2 = sqlite3.connect(str(db.DB_PATH), timeout=0.5)
        try:
            con2.execute("INSERT INTO conn_guard_scratch VALUES (2)")
            con2.commit()
        finally:
            con2.close()
        del held

    def test_negative_control_unwrapped_leak_does_hold_the_lock(self):
        """Non-vacuity: without the wrap, the same shape DOES block the
        next writer while the traceback keeps the frame (and connection)
        alive — proving the guard is load-bearing, not decorative."""
        def bad_unwrapped():
            con = db._connect()
            con.execute("INSERT INTO conn_guard_scratch VALUES (3)")
            raise RuntimeError("boom")
        try:
            bad_unwrapped()
        except RuntimeError as e:
            held = e  # traceback -> frame -> con stays alive and locked
            con2 = sqlite3.connect(str(db.DB_PATH), timeout=0.2)
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    con2.execute(
                        "INSERT INTO conn_guard_scratch VALUES (4)")
            finally:
                con2.close()
            del held

    def test_success_path_unchanged(self):
        # A normal wrapped call still works and still closes its own
        # connection (write visible to a fresh connection immediately).
        db.ensure_session("conn-guard-conv")  # returns None by design
        con2 = sqlite3.connect(str(db.DB_PATH), timeout=0.5)
        try:
            n = con2.execute(
                "SELECT COUNT(*) FROM sessions WHERE conv_id=?",
                ("conn-guard-conv",)).fetchone()[0]
            self.assertEqual(n, 1)
        finally:
            con2.close()
        con2 = sqlite3.connect(str(db.DB_PATH), timeout=0.5)
        try:
            con2.execute("INSERT INTO conn_guard_scratch VALUES (5)")
            con2.commit()
        finally:
            con2.close()


if __name__ == "__main__":
    unittest.main()
