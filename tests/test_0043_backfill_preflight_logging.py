"""The 0043 backfill report must be silent when there is nothing to report.

WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01 Phase 1 boot-path correction,
2026-08-12.

WHAT WENT WRONG. The Phase 1 preflight logged on both paths and sat
inline in ``db.init_db()``. ``init_db()`` is not a boot-only function in
this tree -- it runs on essentially every CRUD call -- so a clean live
database produced dozens of identical

    [migrations] 0043 backfill: every legacy photo-day value carried
    over cleanly.

lines within three minutes of starting the stack, and one every thirty
seconds afterwards. Read from ``api.log`` the migration looked like it
was running continuously. The data was correct throughout; the reporting
was not.

Two defects, not one. The obvious half is that there was a message on
the clean path at all. The half worth naming is that the repetition
applied to the WARNING as well: a warning emitted 2,880 times a day is
worse than an info one, because it trains an operator to scroll past
warnings. So the correction silences the clean path completely and fires
the warning once per database per process. Every boot is a new process,
so every boot with skips still warns exactly once; what is gone is the
repetition inside a single boot.

WHY THESE TESTS DRIVE ``init_db()`` RATHER THAN THE HELPER. The defect
was not in the helper's logic -- there was no helper. It was in WHERE
the logging sat relative to a function called thousands of times. A test
that called the reporting function directly, once, would have passed
against the broken code. Everything below therefore calls the real
production entry point repeatedly, which is the shape of the failure.

Run per-module:
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_0043_backfill_preflight_logging
"""
from __future__ import annotations

import logging
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(_REPO_ROOT / "server" / "code"), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tests import trip_db_binding as _binding  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="hl-0043-log-")
# NEVER delete api.db from sys.modules -- see tests/trip_db_binding.py.
_binding.temp_data_dir(_TMP)

import api.db as db  # noqa: E402
from api.services import trip_repository as repo  # noqa: E402

_MARKER = "0043 backfill"


class _Capture(logging.Handler):
    """Every record the db module emits, at every level."""

    def __init__(self):
        super().__init__(level=logging.NOTSET)
        self.records = []

    def emit(self, record):
        self.records.append(record)

    def messages(self):
        out = []
        for r in self.records:
            try:
                out.append(r.getMessage())
            except Exception:  # a bad format string is itself a finding
                out.append("<unformattable: %r>" % (r.msg,))
        return out

    def mentioning(self, needle):
        return [m for m in self.messages() if needle in m]


class _Base(unittest.TestCase):

    def setUp(self):
        self.path = os.path.join(
            _TMP, "log_%s.sqlite3" % self.id().split(".")[-1])
        for suffix in ("", "-wal", "-shm"):
            p = self.path + suffix
            if os.path.exists(p):
                os.remove(p)

        _binding.bind_db(self, repo, self.path)

        # Capture on the module's own logger, and restore its level.
        self.cap = _Capture()
        previous_level = db.logger.level
        db.logger.addHandler(self.cap)
        db.logger.setLevel(logging.DEBUG)
        self.addCleanup(db.logger.setLevel, previous_level)
        self.addCleanup(db.logger.removeHandler, self.cap)

        # The per-process report guard is keyed by database path. Each
        # test uses its own path, so tests do not interfere -- but the
        # entry is dropped on cleanup anyway so a rerun in the same
        # interpreter starts from the same state as a fresh one.
        self.addCleanup(db._0043_SKIPS_REPORTED.discard, str(self.path))

    def seed_skips(self, rows):
        """Write rows the migration would have written on a corrupt db."""
        con = sqlite3.connect(self.path)
        try:
            for link_id, trip_id, day_id, reason in rows:
                con.execute(
                    "INSERT INTO trip_photo_day_placement_skips"
                    " (id, photo_link_id, trip_id, legacy_trip_day_id,"
                    "  reason, detected_at)"
                    " VALUES (?,?,?,?,?,'2026-08-12T00:00:00Z')",
                    (link_id + "-skip", link_id, trip_id, day_id, reason))
            con.commit()
        finally:
            con.close()

    def rearm(self):
        """Let the report run again for this database.

        Production never needs this: nothing writes to the skip ledger
        after 0043 has run, so one assessment per process is the whole
        truth. A test that seeds the ledger AFTER the first init_db does
        need it, and doing it explicitly here keeps that difference
        visible rather than hiding it behind a helper.
        """
        db._0043_SKIPS_REPORTED.discard(str(self.path))


class TheCaptureItselfWorksTest(_Base):
    """Non-vacuity. Everything else asserts an ABSENCE of log lines.

    An absence assertion passes trivially if the handler is attached to
    the wrong logger, or if the level filters the record out. This test
    emits exactly the message the old code emitted and requires the
    capture to see it -- so a green 'no 0043 lines' result elsewhere
    means the lines are not being emitted, not that the instrument is
    blind.
    """

    def test_an_info_line_on_the_db_logger_is_captured(self):
        db.logger.info("[migrations] 0043 backfill: every legacy "
                       "photo-day value carried over cleanly.")
        self.assertEqual(len(self.cap.mentioning(_MARKER)), 1)

    def test_a_warning_line_on_the_db_logger_is_captured(self):
        db.logger.warning("[migrations] 0043 backfill: 1 legacy value")
        self.assertEqual(len(self.cap.mentioning(_MARKER)), 1)


class CleanDatabaseIsSilentTest(_Base):
    """The reported defect, asserted at every level."""

    def test_repeated_init_db_emits_no_0043_line_at_any_level(self):
        for _ in range(4):
            db.init_db()
        self.assertEqual(
            self.cap.mentioning(_MARKER), [],
            "a clean database logged about 0043; the clean path must be "
            "silent, and init_db runs on nearly every CRUD call")

    def test_the_skip_ledger_really_is_clean_in_this_fixture(self):
        """Guards the test above from passing for the wrong reason.

        Silence proves nothing if there was never a ledger to read.
        """
        db.init_db()
        con = sqlite3.connect(self.path)
        try:
            names = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
                " AND name='trip_photo_day_placement_skips'")]
            self.assertEqual(names, ["trip_photo_day_placement_skips"],
                             "0043 did not run, so silence is meaningless")
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM"
                            " trip_photo_day_placement_skips").fetchone()[0],
                0)
        finally:
            con.close()

    def test_the_clean_assessment_is_not_repeated_on_every_call(self):
        """The other half of the flood: the queries themselves.

        init_db() is called thousands of times per session. Re-reading
        sqlite_master and the ledger on each one costs nothing visible
        but is work done to produce a result that cannot have changed --
        nothing writes to the ledger after 0043 runs.
        """
        db.init_db()
        self.assertIn(str(self.path), db._0043_SKIPS_REPORTED)


class SkipsStillWarnTest(_Base):
    """Preserved: a non-empty ledger must still be surfaced."""

    def warn_lines(self):
        return [r for r in self.cap.records
                if r.levelno >= logging.WARNING
                and _MARKER in r.getMessage()]

    def test_the_warning_names_the_count_the_reasons_and_the_links(self):
        db.init_db()
        self.seed_skips([
            ("L-DANGLE", "T1", "day-gone", "dangling_day"),
            ("L-CROSS", "T1", "day-of-other-trip", "cross_trip_day"),
        ])
        self.rearm()
        db.init_db()

        lines = self.warn_lines()
        self.assertEqual(len(lines), 1,
                         "expected exactly one warning, got %r"
                         % (self.cap.mentioning(_MARKER),))
        msg = lines[0].getMessage()
        self.assertIn("2 legacy photo-day value(s)", msg)
        self.assertIn("dangling_day", msg)
        self.assertIn("cross_trip_day", msg)
        self.assertIn("L-DANGLE", msg)
        self.assertIn("L-CROSS", msg)

    def test_the_warning_does_not_repeat_within_the_process(self):
        db.init_db()
        self.seed_skips([("L-DANGLE", "T1", "day-gone", "dangling_day")])
        self.rearm()
        for _ in range(5):
            db.init_db()
        self.assertEqual(
            len(self.warn_lines()), 1,
            "the warning repeated; a warning emitted every thirty seconds "
            "is the same flood as the info line it replaced")

    def test_a_fresh_process_would_warn_again(self):
        """'Once per process' must not degrade into 'once, ever'.

        The guard is in-memory and keyed by path; dropping the entry is
        what a new interpreter does implicitly. If this fails, the report
        has become a one-time event and a later boot would say nothing
        about a database that still has skips.
        """
        db.init_db()
        self.seed_skips([("L-DANGLE", "T1", "day-gone", "dangling_day")])
        self.rearm()
        db.init_db()
        self.assertEqual(len(self.warn_lines()), 1)

        self.rearm()          # stands in for a new interpreter
        db.init_db()
        self.assertEqual(len(self.warn_lines()), 2)


class BootIsNeverBlockedTest(_Base):
    """Report, never block -- the rule the pre-0034 check follows too."""

    def test_a_broken_connection_does_not_raise(self):
        con = sqlite3.connect(self.path)
        con.close()                      # every query now raises
        try:
            db._report_0043_backfill_skips(con, str(self.path))
        except Exception as exc:          # noqa: BLE001 - the point
            self.fail("the report raised and would have blocked boot: %r"
                      % (exc,))
        self.assertTrue(
            any(r.levelno >= logging.ERROR for r in self.cap.records),
            "a failed preflight must at least be visible")

    def test_a_failed_report_does_not_retry_on_every_call(self):
        con = sqlite3.connect(self.path)
        con.close()
        for _ in range(4):
            db._report_0043_backfill_skips(con, str(self.path))
        errors = [r for r in self.cap.records if r.levelno >= logging.ERROR]
        self.assertEqual(len(errors), 1,
                         "a repeating traceback is the same flood")

    def test_a_pre_0043_database_is_silent_and_stays_assessable(self):
        """No ledger table yet: say nothing, and do NOT mark it done.

        A database opened before the migration runs is not clean and not
        dirty -- it is unknown. Remembering it as assessed would silence
        the real answer once 0043 landed later in the same process.
        """
        empty = os.path.join(_TMP, "pre0043.sqlite3")
        if os.path.exists(empty):
            os.remove(empty)
        con = sqlite3.connect(empty)
        try:
            db._report_0043_backfill_skips(con, empty)
        finally:
            con.close()
        self.assertEqual(self.cap.mentioning(_MARKER), [])
        self.assertNotIn(empty, db._0043_SKIPS_REPORTED)

    def test_init_db_still_completes_and_the_table_exists(self):
        db.init_db()
        con = sqlite3.connect(self.path)
        try:
            self.assertEqual(
                con.execute(
                    "SELECT COUNT(*) FROM trip_photo_day_placements"
                ).fetchone()[0], 0)
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
