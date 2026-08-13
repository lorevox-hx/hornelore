"""WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01 Phase 1.

Migration 0043, the repository placement primitives, the temporary
dual-write bridge in ``photo_links_set_day``, and the switch of
``_day_attachment_counts`` to the placement table.

WHAT THIS SUITE IS REALLY FOR. The work order's §3.3 names one hazard
above all others: ``_day_attachment_counts`` feeds ``_day_is_empty``,
which gates ``drop_empty_out_of_range``, which DELETES day rows when a
trip's dates shrink. A day holding only new-style placements that
reported zero attachments would be destroyed by an operator action as
unrelated as correcting an end date. Every test below either proves that
cannot happen or proves something the bridge needs in order for it to
stay true.

BEHAVIORAL, not source-shape: real sqlite, real migration file, real
repository functions, assertions on rows and on refusals.

Run per-module:
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_trip_photo_day_placements
"""
from __future__ import annotations

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

_TMP = tempfile.mkdtemp(prefix="hl-0043-")
os.environ["DATA_DIR"] = _TMP

for _m in [m for m in list(sys.modules) if m.endswith("api.db") or m == "api.db"]:
    del sys.modules[_m]

import api.db as db  # noqa: E402
from api.services import trip_repository as repo  # noqa: E402

_MIGRATION = (_REPO_ROOT / "server" / "code" / "db" / "migrations"
              / "0043_trip_photo_day_placements.sql")


def _minimal_schema(con):
    """The subset 0043 needs, mirroring the real column shapes."""
    con.executescript("""
        CREATE TABLE IF NOT EXISTS trips(
            id TEXT PRIMARY KEY, person_id TEXT);
        CREATE TABLE IF NOT EXISTS trip_days(
            id TEXT PRIMARY KEY,
            trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
            date TEXT, day_index INTEGER, title TEXT);
        CREATE TABLE IF NOT EXISTS trip_photo_links(
            id TEXT PRIMARY KEY,
            trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
            photo_id TEXT NOT NULL,
            trip_day_id TEXT REFERENCES trip_days(id) ON DELETE SET NULL,
            trip_stop_id TEXT,
            ord INTEGER NOT NULL DEFAULT 0,
            hidden INTEGER NOT NULL DEFAULT 0,
            created_at TEXT, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS trip_location_notes(
            id TEXT PRIMARY KEY, trip_id TEXT, trip_day_id TEXT);
        CREATE TABLE IF NOT EXISTS trip_sources(
            id TEXT PRIMARY KEY, trip_id TEXT, trip_day_id TEXT);
    """)


class _Base(unittest.TestCase):
    TRIP = "trip-1"
    OTHER_TRIP = "trip-2"

    def setUp(self):
        self.path = os.path.join(_TMP, "t_%s.sqlite3" % self.id().split(".")[-1])
        if os.path.exists(self.path):
            os.remove(self.path)
        db.DB_PATH = Path(self.path)
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        _minimal_schema(con)
        con.executescript("""
            INSERT INTO trips(id, person_id) VALUES
                ('trip-1','p1'), ('trip-2','p2');
            INSERT INTO trip_days(id, trip_id, date, day_index) VALUES
                ('d1','trip-1','2026-07-14',1),
                ('d2','trip-1','2026-07-15',2),
                ('d3','trip-1','2026-07-16',3),
                ('x1','trip-2','2026-09-01',1);
            INSERT INTO trip_photo_links
                (id, trip_id, photo_id, trip_day_id, ord, created_at, updated_at)
            VALUES
                ('L1','trip-1','ph1','d1',0,'2026-07-01T00:00:00Z','2026-07-01T00:00:00Z'),
                ('L2','trip-1','ph2',NULL,0,'2026-07-01T00:00:00Z','2026-07-01T00:00:00Z'),
                ('L3','trip-1','ph3','d2',0,'2026-07-01T00:00:00Z','2026-07-01T00:00:00Z'),
                ('LX','trip-2','ph9','x1',0,'2026-07-01T00:00:00Z','2026-07-01T00:00:00Z');
        """)
        con.commit()
        con.close()

    def migrate(self):
        con = sqlite3.connect(self.path)
        con.executescript(_MIGRATION.read_text(encoding="utf-8"))
        con.commit()
        con.close()

    def q(self, sql, args=()):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in con.execute(sql, args).fetchall()]
        finally:
            con.close()

    def placements(self, link_id=None):
        if link_id:
            return self.q("SELECT * FROM trip_photo_day_placements"
                          " WHERE photo_link_id=? ORDER BY ord,id", (link_id,))
        return self.q("SELECT * FROM trip_photo_day_placements ORDER BY id")

    def days_of(self, link_id):
        return sorted(p["trip_day_id"] for p in self.placements(link_id))

    def scalar_of(self, link_id):
        return self.q("SELECT trip_day_id FROM trip_photo_links WHERE id=?",
                      (link_id,))[0]["trip_day_id"]


class MigrationAndBackfillTest(_Base):

    def test_backfill_creates_exactly_one_placement_per_live_scalar(self):
        self.migrate()
        rows = self.placements()
        # L1->d1 and L3->d2 in trip-1; LX->x1 in trip-2. L2 has no day.
        self.assertEqual(len(rows), 3)
        self.assertEqual(self.days_of("L1"), ["d1"])
        self.assertEqual(self.days_of("L3"), ["d2"])
        self.assertEqual(self.days_of("LX"), ["x1"])
        self.assertEqual(self.days_of("L2"), [])

    def test_backfill_stamps_its_own_provenance(self):
        """A backfilled row is the migration's reading of a one-day
        column, not an operator's choice. The two must be tellable
        apart afterwards."""
        self.migrate()
        self.assertTrue(all(p["placement_method"] == "backfill"
                            for p in self.placements()))

    def test_backfill_preserves_the_link_and_the_scalar(self):
        before = self.q("SELECT * FROM trip_photo_links ORDER BY id")
        self.migrate()
        self.assertEqual(self.q("SELECT * FROM trip_photo_links ORDER BY id"),
                         before, "migration altered trip_photo_links")

    def test_rerunning_the_migration_is_a_no_op(self):
        self.migrate()
        first = self.placements()
        self.migrate()
        self.assertEqual(self.placements(), first,
                         "re-running 0043 duplicated placements")

    def test_unique_pair_is_enforced(self):
        self.migrate()
        con = sqlite3.connect(self.path)
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute(
                "INSERT INTO trip_photo_day_placements"
                " (id, photo_link_id, trip_day_id, ord, placement_method,"
                "  created_at, updated_at)"
                " VALUES ('dup','L1','d1',0,'operator','t','t')")
            con.commit()
        con.close()

    def test_a_dangling_day_reference_is_skipped_not_fatal(self):
        """A restored or hand-edited database can carry a link whose day
        is gone. Backfilling it would fail the FK and take the whole
        migration down with it."""
        con = sqlite3.connect(self.path)
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute("UPDATE trip_photo_links SET trip_day_id='ghost'"
                    " WHERE id='L1'")
        con.commit(); con.close()
        self.migrate()  # must not raise
        self.assertEqual(self.days_of("L1"), [])
        self.assertEqual(self.days_of("L3"), ["d2"])

    def test_a_cross_trip_scalar_is_not_propagated(self):
        """Corruption SQLite cannot forbid must not be copied forward."""
        con = sqlite3.connect(self.path)
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute("UPDATE trip_photo_links SET trip_day_id='x1'"
                    " WHERE id='L1'")   # trip-1 link, trip-2 day
        con.commit(); con.close()
        self.migrate()
        self.assertEqual(self.days_of("L1"), [])


class BridgeMirrorsTheScalarTest(_Base):
    """The four transitions, exactly as the work order specifies."""

    def setUp(self):
        super().setUp()
        self.migrate()

    def test_null_to_B(self):
        repo.photo_links_set_day(["L2"], "d2", self.TRIP)
        self.assertEqual(self.scalar_of("L2"), "d2")
        self.assertEqual(self.days_of("L2"), ["d2"])

    def test_A_to_B_moves_and_does_not_leave_A_behind(self):
        """The failure the bridge exists to prevent: two-day data
        produced by an action the UI calls a move."""
        repo.photo_links_set_day(["L1"], "d2", self.TRIP)
        self.assertEqual(self.scalar_of("L1"), "d2")
        self.assertEqual(self.days_of("L1"), ["d2"],
                         "the old placement survived a move")

    def test_A_to_null(self):
        repo.photo_links_set_day(["L1"], None, self.TRIP)
        self.assertIsNone(self.scalar_of("L1"))
        self.assertEqual(self.days_of("L1"), [])

    def test_A_to_A_is_idempotent(self):
        repo.photo_links_set_day(["L1"], "d1", self.TRIP)
        repo.photo_links_set_day(["L1"], "d1", self.TRIP)
        self.assertEqual(self.days_of("L1"), ["d1"])
        self.assertEqual(len(self.placements("L1")), 1)

    def test_a_move_only_touches_its_own_links_placements(self):
        """Deletion is scoped by (link, its prior day) -- not by day,
        which would clear the day, and not by link, which would clear
        every day."""
        repo.photo_links_set_day(["L2"], "d1", self.TRIP)   # d1 now L1+L2
        repo.photo_links_set_day(["L1"], "d3", self.TRIP)   # move L1 only
        self.assertEqual(self.days_of("L1"), ["d3"])
        self.assertEqual(self.days_of("L2"), ["d1"],
                         "moving one photo cleared another off the day")

    def test_batch_of_links_each_leaves_its_own_prior_day(self):
        repo.photo_links_set_day(["L1", "L3"], "d3", self.TRIP)
        self.assertEqual(self.days_of("L1"), ["d3"])
        self.assertEqual(self.days_of("L3"), ["d3"])
        self.assertEqual(
            [p["trip_day_id"] for p in self.placements()].count("d1"), 0)


class RefusalsWriteNothingTest(_Base):

    def setUp(self):
        super().setUp()
        self.migrate()

    def test_cross_trip_day_writes_nothing(self):
        before = (self.placements(), self.scalar_of("L2"))
        with self.assertRaises(ValueError):
            repo.photo_links_set_day(["L2"], "x1", self.TRIP)
        self.assertEqual((self.placements(), self.scalar_of("L2")), before)

    def test_cross_trip_link_writes_nothing(self):
        before = (self.placements(), self.scalar_of("LX"))
        with self.assertRaises(ValueError):
            repo.photo_links_set_day(["LX"], "d1", self.TRIP)
        self.assertEqual((self.placements(), self.scalar_of("LX")), before)

    def test_missing_day_writes_nothing(self):
        before = self.placements()
        with self.assertRaises(ValueError):
            repo.photo_links_set_day(["L2"], "no-such-day", self.TRIP)
        self.assertEqual(self.placements(), before)

    def test_injected_failure_rolls_back_BOTH_representations(self):
        """Scalar and placement move together or not at all."""
        before_scalar, before_days = self.scalar_of("L1"), self.days_of("L1")
        real = repo.placement_add_many

        def boom(con, link_ids, day_id, trip_id, method="operator"):
            con.execute("SELECT 1")          # prove we are mid-transaction
            raise RuntimeError("injected failure after the scalar UPDATE")

        repo.placement_add_many = boom
        try:
            with self.assertRaises(RuntimeError):
                repo.photo_links_set_day(["L1"], "d3", self.TRIP)
        finally:
            repo.placement_add_many = real
        self.assertEqual(self.scalar_of("L1"), before_scalar,
                         "scalar survived a rolled-back transaction")
        self.assertEqual(self.days_of("L1"), before_days)


class DeletionSafetyTest(_Base):
    """§3.3 — the blocking gate."""

    def setUp(self):
        super().setUp()
        self.migrate()

    def _attached(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            return repo._day_attachment_counts(con, self.TRIP)
        finally:
            con.close()

    def _is_empty(self, day_id):
        day = {"id": day_id, "title": None, "main_location": None}
        return repo._day_is_empty(day, self._attached())

    def test_a_day_holding_only_a_placement_is_not_empty(self):
        self.assertEqual(self._attached().get("d1", {}).get("photos"), 1)
        self.assertFalse(self._is_empty("d1"))

    def test_a_day_with_nothing_is_empty(self):
        self.assertTrue(self._is_empty("d3"))

    def test_a_legacy_path_move_protects_the_destination_and_frees_the_source(self):
        """§9.11, both halves. The bridge is what makes this true."""
        repo.photo_links_set_day(["L1"], "d3", self.TRIP)
        self.assertFalse(self._is_empty("d3"), "destination unprotected")
        self.assertTrue(self._is_empty("d1"),
                        "source still counts a photo it no longer holds")

    def test_a_hidden_links_placement_still_protects_its_day(self):
        """Honest counts govern what a card DISPLAYS; they have no
        bearing on what a delete would detach."""
        con = sqlite3.connect(self.path)
        con.execute("UPDATE trip_photo_links SET hidden=1 WHERE id='L1'")
        con.commit(); con.close()
        self.assertFalse(self._is_empty("d1"))

    def test_the_tally_counts_placements_not_the_scalar(self):
        """Non-vacuity for the switch: a placement with NO scalar must
        still be counted. Under the old query this returns zero."""
        con = sqlite3.connect(self.path)
        con.execute(
            "INSERT INTO trip_photo_day_placements"
            " (id, photo_link_id, trip_day_id, ord, placement_method,"
            "  created_at, updated_at)"
            " VALUES ('p-extra','L2','d3',0,'operator','t','t')")
        con.commit(); con.close()
        self.assertEqual(self._attached().get("d3", {}).get("photos"), 1)
        self.assertIsNone(self.scalar_of("L2"))
        self.assertFalse(self._is_empty("d3"))

    def test_a_failed_count_query_raises_and_never_reads_as_zero(self):
        """§9.5 fail-closed. Zero attachments licenses a delete, so a
        broken query must never be able to produce one."""
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        con.execute("DROP TABLE trip_photo_links")
        try:
            with self.assertRaises(sqlite3.OperationalError):
                repo._day_attachment_counts(con, self.TRIP)
        finally:
            con.close()


class PreMigrationCompatibilityTest(_Base):
    """A pre-0043 database must keep working, unchanged."""

    def test_legacy_scalar_behaviour_survives_without_the_table(self):
        repo.photo_links_set_day(["L2"], "d2", self.TRIP)   # no migrate()
        self.assertEqual(self.scalar_of("L2"), "d2")

    def test_legacy_tally_is_used_when_the_table_is_absent(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            counts = repo._day_attachment_counts(con, self.TRIP)
        finally:
            con.close()
        self.assertEqual(counts.get("d1", {}).get("photos"), 1,
                         "pre-0043 database lost its attachment counts")

    def test_placement_primitives_no_op_without_the_table(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            self.assertEqual(repo.placements_for_link(con, "L1"), [])
            self.assertEqual(
                repo.placement_add_many(con, ["L2"], "d1", self.TRIP), [])
        finally:
            con.close()


class PrimitivesTest(_Base):

    def setUp(self):
        super().setUp()
        self.migrate()
        self.con = sqlite3.connect(self.path)
        self.con.row_factory = sqlite3.Row

    def tearDown(self):
        self.con.close()

    def test_add_many_assigns_increasing_ord_after_the_days_max(self):
        repo.placement_add_many(self.con, ["L2", "L3"], "d1", self.TRIP)
        self.con.commit()
        ords = [p["ord"] for p in self.q(
            "SELECT * FROM trip_photo_day_placements WHERE trip_day_id='d1'"
            " ORDER BY ord")]
        self.assertEqual(ords, sorted(ords))
        self.assertEqual(len(set(ords)), len(ords), "ord values collided")

    def test_add_many_is_idempotent_per_pair(self):
        a = repo.placement_add_many(self.con, ["L2"], "d1", self.TRIP)
        b = repo.placement_add_many(self.con, ["L2"], "d1", self.TRIP)
        self.con.commit()
        self.assertEqual(len(a), 1)
        self.assertEqual(b, [], "a duplicate pair created a second row")

    def test_one_photo_on_several_days(self):
        """The capability the whole work order exists for."""
        repo.placement_add_many(self.con, ["L1"], "d2", self.TRIP)
        repo.placement_add_many(self.con, ["L1"], "d3", self.TRIP)
        self.con.commit()
        self.assertEqual(self.days_of("L1"), ["d1", "d2", "d3"])

    def test_remove_from_day_leaves_other_placements_and_the_link(self):
        repo.placement_add_many(self.con, ["L1"], "d2", self.TRIP)
        self.con.commit()
        repo.placement_remove_from_day(self.con, ["L1"], "d1")
        self.con.commit()
        self.assertEqual(self.days_of("L1"), ["d2"])
        self.assertEqual(
            len(self.q("SELECT 1 FROM trip_photo_links WHERE id='L1'")), 1,
            "removing a placement removed the trip membership")

    def test_move_names_its_source(self):
        repo.placement_add_many(self.con, ["L1"], "d2", self.TRIP)
        self.con.commit()
        repo.placement_move(self.con, "L1", "d1", "d3", self.TRIP)
        self.con.commit()
        self.assertEqual(self.days_of("L1"), ["d2", "d3"],
                         "move took the wrong placement")

    def test_reorder(self):
        repo.placement_add_many(self.con, ["L2", "L3"], "d1", self.TRIP)
        self.con.commit()
        ids = [p["id"] for p in repo.placements_for_day(self.con, "d1")]
        repo.placement_reorder(self.con, "d1", list(reversed(ids)))
        self.con.commit()
        self.assertEqual(
            [p["id"] for p in repo.placements_for_day(self.con, "d1")],
            list(reversed(ids)))

    def test_deleting_a_link_cascades_only_its_placements(self):
        repo.placement_add_many(self.con, ["L1"], "d2", self.TRIP)
        self.con.commit()
        con = sqlite3.connect(self.path)
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("DELETE FROM trip_photo_links WHERE id='L1'")
        con.commit(); con.close()
        self.assertEqual(self.placements("L1"), [])
        self.assertEqual(self.days_of("L3"), ["d2"], "cascade over-reached")


if __name__ == "__main__":
    unittest.main()
