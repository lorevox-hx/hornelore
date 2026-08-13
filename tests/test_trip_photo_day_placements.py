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

from tests import trip_db_binding as _binding  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="hl-0043-")
# NEVER delete api.db from sys.modules here. Doing so forks the
# module object; trip_repository._connect() late-imports api.db and
# would then read a DIFFERENT database than the one this suite set
# up. See tests/trip_db_binding.py for the measured failure.
_binding.temp_data_dir(_TMP)

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
        # Bind EVERY production connection path to this test's database
        # and prove the repository actually opens it. Restored on
        # cleanup, so this suite cannot leak its temp db into the next.
        _binding.bind_db(self, repo, self.path)

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


class TheBridgeIsRetiredTest(_Base):
    """RETIRED HERE 2026-08-13, and the retirement is itself a gate.

    This class used to be ``BridgeMirrorsTheScalarTest`` and it asserted
    the four Phase 1 transitions of ``photo_links_set_day`` --

        null -> B   placements become {B}
        A    -> B   placements become {B}
        A    -> null placements become {}
        A    -> A   unchanged, no duplicate

    Every one of those was correct for Phase 1, whose whole point was
    that storage changed and product semantics did not. Phase 2 changes
    the semantics: placing a second day is now an ADD, so a test
    demanding that the first placement disappear would now be demanding
    the defect back.

    The tests are replaced rather than deleted, and what replaces them
    is the stronger claim: the function is GONE and nothing writes the
    legacy column any more. A silent reappearance of either -- a
    convenience helper here, a stray UPDATE there -- is exactly how a
    retired representation comes back to life and starts disagreeing
    with the real one.
    """

    def setUp(self):
        super().setUp()
        self.migrate()

    def test_photo_links_set_day_no_longer_exists(self):
        self.assertFalse(
            hasattr(repo, "photo_links_set_day"),
            "the Phase 1 dual-write bridge is back; placements are the "
            "only representation Phase 2 writes")

    def test_no_production_module_writes_the_legacy_photo_day_column(self):
        """Source scan, and deliberately so.

        A behavioural test can only prove that the paths it happens to
        drive leave the column alone. The claim being made is about
        every path, including ones nobody has written yet, so it is
        asserted against the text: no UPDATE of trip_photo_links may
        name trip_day_id anywhere under server/code.
        """
        import re
        server = _REPO_ROOT / "server" / "code"
        offenders = []
        for path in server.rglob("*.py"):
            src = path.read_text(encoding="utf-8", errors="replace")
            # Comments and docstrings discuss the retired column by
            # name on purpose; only executable UPDATEs are forbidden.
            for match in re.finditer(
                    r"UPDATE\s+trip_photo_links\s+SET\s+([^\"']*)", src,
                    re.IGNORECASE):
                if "trip_day_id" in match.group(1):
                    offenders.append("%s: %s" % (path.name, match.group(0)))
        self.assertEqual(offenders, [],
                         "something writes the legacy scalar again: %r"
                         % (offenders,))

    def test_a_hand_written_scalar_is_never_resurrected_as_a_placement(self):
        """The state Phase 2 will not invent its way out of.

        Review caution, 2026-08-13: it is too strong to say a populated
        scalar with no placement cannot happen. Nothing in the PRODUCT
        creates it -- 0043 backfilled every live scalar and no code
        writes the column afterwards -- but manual SQL, an old external
        script, or a restored malformed backup can, for as long as the
        column physically exists.

        The correct answer to finding one is to treat it as
        non-authoritative, which is what every read here does. The
        answer this test forbids is the tempting one: quietly promoting
        it into a placement on the next read. That would resurrect a
        value nobody can date, from a column the system has stopped
        believing, and make it indistinguishable from an operator's
        deliberate choice.
        """
        con = sqlite3.connect(self.path)
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute("UPDATE trip_photo_links SET trip_day_id='d3'"
                    " WHERE id='L2'")
        con.commit(); con.close()

        # Read it every way a consumer can.
        self.assertEqual(self.days_of("L2"), [],
                         "a hand-written scalar became a placement")
        row = repo.photo_link_get("L2")
        self.assertIsNone(row["trip_day_id"],
                          "the fossil scalar was served as authority")
        self.assertEqual(row["trip_day_ids"], [])
        # (photo_links_list needs the real `photos` table, which this
        # suite's minimal schema does not build; the same assertion
        # against the list read lives in
        # tests.test_trip_photo_placement_api, on the full chain.)
        # And it still is not a placement afterwards: reading did not
        # write.
        self.assertEqual(self.days_of("L2"), [])
        self.assertEqual(
            self.q("SELECT trip_day_id FROM trip_photo_links WHERE id='L2'"
                   )[0]["trip_day_id"], "d3",
            "the read erased the stray value instead of ignoring it")

    def test_the_stored_scalar_is_left_exactly_as_the_migration_found_it(self):
        """Not written, and not cleaned up either.

        Phase 6 drops the column. Until then its historical values are
        the only record of what the pre-placement world believed, and
        blanking them now would destroy evidence to tidy a column that
        is about to be deleted anyway.
        """
        before = self.q("SELECT id, trip_day_id FROM trip_photo_links"
                        " ORDER BY id")
        repo.day_placements_add(["L2"], "d2", self.TRIP)
        repo.day_placements_remove(["L1"], "d1", self.TRIP)
        self.assertEqual(
            self.q("SELECT id, trip_day_id FROM trip_photo_links ORDER BY id"),
            before, "a placement operation touched the legacy column")


class PlacementApiTest(_Base):
    """The Section 6 contracts, at the repository boundary the router
    calls. Route-level behaviour is asserted in
    tests.test_trip_photo_placement_api."""

    def setUp(self):
        super().setUp()
        self.migrate()

    def test_adding_a_second_day_keeps_the_first(self):
        """The product ruling, in one assertion."""
        repo.day_placements_add(["L1"], "d2", self.TRIP)
        self.assertEqual(self.days_of("L1"), ["d1", "d2"])

    def test_add_is_idempotent_and_says_so(self):
        first = repo.day_placements_add(["L2"], "d2", self.TRIP)
        second = repo.day_placements_add(["L2"], "d2", self.TRIP)
        self.assertEqual(len(first["created"]), 1)
        self.assertEqual(second["created"], [])
        self.assertEqual(second["already_present"], ["L2"])
        self.assertEqual(len(self.placements("L2")), 1)

    def test_add_many_assigns_increasing_ord_in_request_order(self):
        repo.day_placements_add(["L3", "L2"], "d3", self.TRIP)
        rows = self.q("SELECT photo_link_id, ord FROM"
                      " trip_photo_day_placements WHERE trip_day_id='d3'"
                      " ORDER BY ord")
        self.assertEqual([r["photo_link_id"] for r in rows], ["L3", "L2"])
        self.assertEqual([r["ord"] for r in rows], [0, 1])

    def test_add_many_continues_after_the_days_existing_maximum(self):
        """Leaving every new row at 0 and relying on the id tie-breaker
        would order a day by random uuid."""
        repo.day_placements_add(["L2"], "d1", self.TRIP)
        rows = self.q("SELECT photo_link_id, ord FROM"
                      " trip_photo_day_placements WHERE trip_day_id='d1'"
                      " ORDER BY ord")
        self.assertEqual([r["ord"] for r in rows], [0, 1])
        self.assertEqual(rows[-1]["photo_link_id"], "L2")

    def test_remove_takes_only_that_occurrence(self):
        repo.day_placements_add(["L1"], "d2", self.TRIP)
        repo.day_placements_remove(["L1"], "d1", self.TRIP)
        self.assertEqual(self.days_of("L1"), ["d2"],
                         "removing one day removed the other too")

    def test_remove_preserves_the_link_and_the_photo(self):
        before = self.q("SELECT * FROM trip_photo_links WHERE id='L1'")
        repo.day_placements_remove(["L1"], "d1", self.TRIP)
        self.assertEqual(
            self.q("SELECT * FROM trip_photo_links WHERE id='L1'"), before,
            "taking a photo off a day changed its trip membership")

    def test_remove_reports_what_was_not_there(self):
        out = repo.day_placements_remove(["L2"], "d1", self.TRIP)
        self.assertEqual(out["removed"], 0)
        self.assertEqual(out["not_present"], ["L2"])

    def test_move_changes_one_occurrence_and_leaves_the_other(self):
        repo.day_placements_add(["L1"], "d2", self.TRIP)
        out = repo.day_placement_move("L1", "d1", "d3", self.TRIP)
        self.assertTrue(out["moved"])
        self.assertEqual(self.days_of("L1"), ["d2", "d3"])

    def test_move_from_a_day_it_is_not_on_writes_nothing(self):
        before = self.placements()
        out = repo.day_placement_move("L1", "d3", "d2", self.TRIP)
        self.assertFalse(out["moved"])
        self.assertEqual(out["reason"], "source_placement_not_found")
        self.assertEqual(self.placements(), before)

    def test_move_onto_a_day_it_already_occupies_removes_the_source(self):
        repo.day_placements_add(["L1"], "d2", self.TRIP)
        out = repo.day_placement_move("L1", "d1", "d2", self.TRIP)
        self.assertTrue(out["moved"])
        self.assertTrue(out["destination_existed"])
        self.assertEqual(self.days_of("L1"), ["d2"])


class RefusalsWriteNothingTest(_Base):

    def setUp(self):
        super().setUp()
        self.migrate()

    def test_cross_trip_day_writes_nothing(self):
        before = self.placements()
        with self.assertRaises(ValueError):
            repo.day_placements_add(["L2"], "x1", self.TRIP)
        self.assertEqual(self.placements(), before)

    def test_cross_trip_link_writes_nothing(self):
        before = self.placements()
        with self.assertRaises(ValueError):
            repo.day_placements_add(["LX"], "d1", self.TRIP)
        self.assertEqual(self.placements(), before)

    def test_missing_day_writes_nothing(self):
        before = self.placements()
        with self.assertRaises(ValueError):
            repo.day_placements_add(["L2"], "no-such-day", self.TRIP)
        self.assertEqual(self.placements(), before)

    def test_a_batch_with_one_bad_link_writes_none_of_it(self):
        """Partial application is the failure mode that is hardest to
        see afterwards: some photographs moved, some did not, and the
        response said 400."""
        before = self.placements()
        with self.assertRaises(ValueError):
            repo.day_placements_add(["L2", "LX"], "d2", self.TRIP)
        self.assertEqual(self.placements(), before)

    def test_injected_failure_rolls_the_whole_add_back(self):
        before = self.placements()
        real = repo.placement_add_many

        def boom(con, link_ids, day_id, trip_id, method="operator"):
            con.execute("SELECT 1")          # prove we are mid-transaction
            raise RuntimeError("injected failure mid-add")

        repo.placement_add_many = boom
        try:
            with self.assertRaises(RuntimeError):
                repo.day_placements_add(["L2", "L3"], "d3", self.TRIP)
        finally:
            repo.placement_add_many = real
        self.assertEqual(self.placements(), before)

    def test_a_failed_destination_leaves_the_source_placement(self):
        """Move is one transaction: a photograph cannot end up on
        neither day."""
        before = self.days_of("L1")
        real = repo.placement_add_many

        def boom(con, link_ids, day_id, trip_id, method="operator"):
            raise RuntimeError("destination add failed")

        repo.placement_add_many = boom
        try:
            with self.assertRaises(RuntimeError):
                repo.day_placement_move("L1", "d1", "d3", self.TRIP)
        finally:
            repo.placement_add_many = real
        self.assertEqual(self.days_of("L1"), before)

    def test_the_unique_race_is_classified_not_a_500(self):
        """A concurrent duplicate loses at the INSERT. The pair exists
        afterwards, which is what the caller wanted, so it is reported
        as already-present -- and only for THAT constraint."""
        real = repo.placement_add_many

        def racer(con, link_ids, day_id, trip_id, method="operator"):
            raise sqlite3.IntegrityError(
                "UNIQUE constraint failed: "
                "trip_photo_day_placements.photo_link_id, "
                "trip_photo_day_placements.trip_day_id")

        repo.placement_add_many = racer
        try:
            out = repo.day_placements_add(["L2"], "d2", self.TRIP)
        finally:
            repo.placement_add_many = real
        self.assertEqual(out["created"], [])
        self.assertEqual(out["already_present"], ["L2"])

    def test_a_foreign_key_violation_is_not_swallowed_as_already_present(self):
        """The reason the race check is classified rather than a bare
        `except IntegrityError`: a placement pointing at a row that does
        not exist is corruption, and reporting it as 'already on that
        day' would be a lie about a failed write."""
        real = repo.placement_add_many

        def broken(con, link_ids, day_id, trip_id, method="operator"):
            raise sqlite3.IntegrityError("FOREIGN KEY constraint failed")

        repo.placement_add_many = broken
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                repo.day_placements_add(["L2"], "d2", self.TRIP)
        finally:
            repo.placement_add_many = real


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

    def test_a_move_protects_the_destination_and_frees_the_source(self):
        """§9.11, both halves. Was driven through the Phase 1 bridge;
        driven through the Phase 2 move operation since 2026-08-13,
        which is now the only way a photograph changes days."""
        repo.day_placement_move("L1", "d1", "d3", self.TRIP)
        self.assertFalse(self._is_empty("d3"), "destination unprotected")
        self.assertTrue(self._is_empty("d1"),
                        "source still counts a photo it no longer holds")

    def test_a_second_day_protects_BOTH_days_from_a_date_shrink(self):
        """New in Phase 2, and the reason the deletion gate had to be
        re-checked: a photograph on two days makes two days non-empty,
        and shrinking the trip's dates must refuse to delete either."""
        repo.day_placements_add(["L1"], "d3", self.TRIP)
        self.assertFalse(self._is_empty("d1"))
        self.assertFalse(self._is_empty("d3"))

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

    def test_the_placement_api_refuses_a_database_without_the_table(self):
        """REWRITTEN 2026-08-13. This asserted that the Phase 1 bridge
        still wrote the scalar on a pre-0043 database. That function is
        gone, and the honest Phase 2 answer to "place this photograph"
        on a database with no placement table is a refusal, not a
        silent write to a column the rest of the system has stopped
        reading. Refusing is also what makes the WRITE path fail loudly
        while the READ paths below keep degrading gracefully -- a
        half-migrated database can still be looked at, and cannot be
        written into a shape it cannot represent."""
        with self.assertRaises(RuntimeError):
            repo.day_placements_add(["L2"], "d2", self.TRIP)
        self.assertIsNone(self.scalar_of("L2"),
                          "the refusal wrote the legacy column anyway")

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


class MoveRequiresAnExistingSourceTest(_Base):
    """Correction 2026-08-12: a move with a missing source was an ADD.

    The first version added the destination and then removed the source,
    returning moved=True with removed=0 when the source was not there.
    "Move this occurrence" silently became "add another occurrence" --
    creating exactly the multi-day data Phase 1 must not be able to
    produce.
    """

    def setUp(self):
        super().setUp()
        self.migrate()
        self.con = sqlite3.connect(self.path)
        self.con.row_factory = sqlite3.Row

    def tearDown(self):
        self.con.close()

    def test_a_missing_source_performs_zero_writes(self):
        before = self.placements()
        out = repo.placement_move(self.con, "L1", "d3", "d2", self.TRIP)
        self.con.commit()
        self.assertFalse(out["moved"])
        self.assertEqual(out["reason"], "source_placement_not_found")
        self.assertEqual(out["created"], [])
        self.assertEqual(out["removed"], 0)
        self.assertEqual(self.placements(), before,
                         "a move with no source wrote something")

    def test_a_missing_source_does_not_create_the_destination(self):
        """The precise regression: the add must not happen."""
        repo.placement_move(self.con, "L1", "d3", "d2", self.TRIP)
        self.con.commit()
        self.assertNotIn("d2", self.days_of("L1"),
                         "a move with no source created the destination")
        self.assertEqual(self.days_of("L1"), ["d1"])

    def test_a_normal_move_still_works(self):
        out = repo.placement_move(self.con, "L1", "d1", "d3", self.TRIP)
        self.con.commit()
        self.assertTrue(out["moved"])
        self.assertEqual(out["removed"], 1)
        self.assertEqual(self.days_of("L1"), ["d3"])

    def test_destination_already_existing_still_removes_the_source(self):
        """A real operator situation: the photo is on both days and they
        want the source occurrence gone."""
        repo.placement_add_many(self.con, ["L1"], "d2", self.TRIP)
        self.con.commit()
        out = repo.placement_move(self.con, "L1", "d1", "d2", self.TRIP)
        self.con.commit()
        self.assertTrue(out["moved"])
        self.assertTrue(out["destination_existed"])
        self.assertEqual(out["removed"], 1)
        self.assertEqual(self.days_of("L1"), ["d2"])

    def test_injected_destination_failure_preserves_the_source(self):
        real = repo.placement_add_many

        def boom(con, link_ids, day_id, trip_id, method="operator"):
            raise RuntimeError("injected destination failure")

        repo.placement_add_many = boom
        try:
            with self.assertRaises(RuntimeError):
                repo.placement_move(self.con, "L1", "d1", "d3", self.TRIP)
        finally:
            repo.placement_add_many = real
        self.con.rollback()
        self.assertEqual(self.days_of("L1"), ["d1"],
                         "a failed destination lost the source placement")


class CorruptionIsSurfacedTest(_Base):
    """Correction 2026-08-12: skipping is right; SILENT skipping is not.

    0043 must not copy a legacy scalar pointing at a missing day (the
    new FK would fail the whole migration) or at another trip's day
    (propagating corruption SQLite cannot forbid). But a placement the
    operator can see in the old column must not simply stop existing
    with nothing saying so.
    """

    def _corrupt(self, link_id, day_id):
        con = sqlite3.connect(self.path)
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute("UPDATE trip_photo_links SET trip_day_id=? WHERE id=?",
                    (day_id, link_id))
        con.commit(); con.close()

    def skips(self):
        return self.q("SELECT * FROM trip_photo_day_placement_skips"
                      " ORDER BY photo_link_id")

    def test_a_dangling_day_is_recorded_with_its_reason(self):
        self._corrupt("L1", "ghost")
        self.migrate()
        rows = self.skips()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["photo_link_id"], "L1")
        self.assertEqual(rows[0]["reason"], "dangling_day")
        self.assertEqual(rows[0]["legacy_trip_day_id"], "ghost")
        self.assertTrue(rows[0]["detected_at"])

    def test_a_cross_trip_day_is_recorded_with_its_reason(self):
        self._corrupt("L1", "x1")          # trip-1 link, trip-2 day
        self.migrate()
        rows = self.skips()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reason"], "cross_trip_day")

    def test_a_healthy_database_records_nothing(self):
        self.migrate()
        self.assertEqual(self.skips(), [],
                         "a clean database produced skip rows")

    def test_the_ledger_is_idempotent(self):
        self._corrupt("L1", "ghost")
        self.migrate()
        self.migrate()
        self.assertEqual(len(self.skips()), 1,
                         "re-running 0043 duplicated the skip record")

    def test_the_preflight_reports_the_skip_out_loud(self):
        """The migration cannot log for itself; this is where the skip
        reaches an operator."""
        import logging
        self._corrupt("L1", "ghost")
        self.migrate()
        with self.assertLogs("lorevox.trips", level="WARNING") as cap:
            out = repo.placement_backfill_preflight()
        self.assertEqual(out["count"], 1)
        self.assertEqual(out["by_reason"], {"dangling_day": 1})
        joined = "\n".join(cap.output)
        self.assertIn("L1", joined)
        self.assertIn("dangling_day", joined)

    def test_the_preflight_is_quiet_on_a_clean_database(self):
        self.migrate()
        out = repo.placement_backfill_preflight()
        self.assertEqual(out["count"], 0)
        self.assertTrue(out["supported"])

    def test_the_preflight_is_safe_before_0043(self):
        out = repo.placement_backfill_preflight()   # no migrate()
        self.assertEqual(out["count"], 0)
        self.assertFalse(out["supported"])


class SoftDeletedPhotoDeletionSafetyTest(_Base):
    """A soft-deleted photo's placement still protects its day.

    Same rule as hidden links: what a card DISPLAYS is governed by
    honest counts; what a DELETE would detach is not. A soft delete is
    reversible, so a day still holding one is not empty -- destroying
    the day row would make that restore land nowhere.
    """

    def setUp(self):
        super().setUp()
        con = sqlite3.connect(self.path)
        con.executescript("""
            CREATE TABLE IF NOT EXISTS photos(
                id TEXT PRIMARY KEY, narrator_id TEXT, deleted_at TEXT);
            INSERT INTO photos(id, narrator_id, deleted_at)
                VALUES ('ph1','p1',NULL);
        """)
        con.commit(); con.close()
        self.migrate()

    def _is_empty(self, day_id):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            attached = repo._day_attachment_counts(con, self.TRIP)
        finally:
            con.close()
        return repo._day_is_empty({"id": day_id}, attached)

    def test_a_soft_deleted_photos_placement_still_protects_its_day(self):
        con = sqlite3.connect(self.path)
        con.execute("UPDATE photos SET deleted_at='2026-08-12T00:00:00Z'"
                    " WHERE id='ph1'")
        con.commit(); con.close()
        self.assertFalse(
            self._is_empty("d1"),
            "a soft-deleted photo's day read as empty and could be deleted")
