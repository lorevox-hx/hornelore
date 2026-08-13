"""Migration 0043 through the REAL runner and the full 0001-0043 chain.

WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01 Phase 1 correction, 2026-08-12.

Why this exists separately from tests.test_trip_photo_day_placements:
that suite executes 0043 directly against a hand-built minimal schema.
That is strong evidence about the migration's own logic and useless
evidence about how it behaves in production, where it runs through
``db.init_db()`` after forty-two predecessors, against tables whose real
shapes it did not choose, with the runner's ledger deciding whether it
runs at all. A migration can be perfectly correct in isolation and still
fail on the real chain -- wrong column type, a table that does not exist
yet at that point in the order, or a ledger entry that makes it run
twice.

Everything here therefore uses the production entry point and asserts on
the resulting database, never on a constructed one.

Run per-module:
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_trip_photo_day_placements_full_chain
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

_TMP = tempfile.mkdtemp(prefix="hl-0043-chain-")
os.environ["DATA_DIR"] = _TMP

for _m in [m for m in list(sys.modules) if m.endswith("api.db") or m == "api.db"]:
    del sys.modules[_m]

import api.db as db  # noqa: E402
from api.services import trip_repository as repo  # noqa: E402

_TABLE = "trip_photo_day_placements"
_MIGRATION_NAME = "0043_trip_photo_day_placements.sql"


class _Chain(unittest.TestCase):
    """Build a real database through db.init_db()."""

    def setUp(self):
        self.path = os.path.join(
            _TMP, "chain_%s.sqlite3" % self.id().split(".")[-1])
        for suffix in ("", "-wal", "-shm"):
            p = self.path + suffix
            if os.path.exists(p):
                os.remove(p)
        db.DB_PATH = Path(self.path)
        db.init_db()

    def q(self, sql, args=()):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in con.execute(sql, args).fetchall()]
        finally:
            con.close()

    def exec_(self, sql, args=()):
        con = sqlite3.connect(self.path)
        try:
            con.execute("PRAGMA foreign_keys=ON")
            con.execute(sql, args)
            con.commit()
        finally:
            con.close()


class RealRunnerTest(_Chain):

    def test_0043_is_recorded_in_the_ledger_exactly_once(self):
        rows = self.q(
            "SELECT filename FROM schema_migrations WHERE filename = ?",
            (_MIGRATION_NAME,))
        self.assertEqual(len(rows), 1, "0043 missing or double-recorded")

    def test_every_migration_on_disk_was_applied(self):
        on_disk = sorted(
            p.name for p in
            (_REPO_ROOT / "server" / "code" / "db" / "migrations").glob("*.sql"))
        applied = {r["filename"] for r in
                   self.q("SELECT filename FROM schema_migrations")}
        missing = [n for n in on_disk if n not in applied]
        self.assertEqual(missing, [], "migrations did not all apply")

    def test_foreign_key_check_is_clean(self):
        self.assertEqual(self.q("PRAGMA foreign_key_check"), [],
                         "the full chain left foreign key violations")

    def test_a_second_init_is_a_no_op(self):
        before_led = self.q("SELECT filename FROM schema_migrations")
        before_rows = self.q("SELECT * FROM %s" % _TABLE)
        db.init_db()
        self.assertEqual(self.q("SELECT filename FROM schema_migrations"),
                         before_led, "a second init re-recorded a migration")
        self.assertEqual(self.q("SELECT * FROM %s" % _TABLE), before_rows)

    def test_the_real_table_shape(self):
        cols = {r["name"]: r for r in
                self.q("PRAGMA table_info(%s)" % _TABLE)}
        # Alphabetical: 'photo_link_id' < 'placement_method' ('ph' < 'pl').
        # The first version of this list was mis-sorted and failed against
        # a correct table.
        self.assertEqual(
            sorted(cols),
            ["created_at", "id", "ord", "photo_link_id", "placement_method",
             "placement_note", "trip_day_id", "updated_at"])
        for required in ("photo_link_id", "trip_day_id", "ord",
                         "placement_method", "created_at", "updated_at"):
            self.assertEqual(cols[required]["notnull"], 1,
                             "%s should be NOT NULL" % required)

    def test_the_real_indexes_and_unique_pair(self):
        names = {r["name"] for r in
                 self.q("PRAGMA index_list(%s)" % _TABLE)}
        self.assertIn("idx_trip_photo_day_placements_day_ord", names)
        self.assertIn("idx_trip_photo_day_placements_link", names)
        uniques = [r for r in self.q("PRAGMA index_list(%s)" % _TABLE)
                   if r["unique"]]
        pairs = []
        for u in uniques:
            cols = [c["name"] for c in
                    self.q("PRAGMA index_info(%s)" % u["name"])]
            pairs.append(sorted(cols))
        self.assertIn(["photo_link_id", "trip_day_id"], pairs,
                      "UNIQUE(photo_link_id, trip_day_id) is not enforced")

    def test_the_foreign_keys_are_real_and_cascade(self):
        fks = {r["table"]: r for r in
               self.q("PRAGMA foreign_key_list(%s)" % _TABLE)}
        self.assertIn("trip_photo_links", fks)
        self.assertIn("trip_days", fks)
        for t in ("trip_photo_links", "trip_days"):
            self.assertEqual(fks[t]["on_delete"], "CASCADE")

    def test_the_skip_ledger_exists_and_is_empty_on_a_clean_chain(self):
        self.assertEqual(self.q("SELECT * FROM trip_photo_day_placement_skips"),
                         [])


class RealChainBackfillTest(_Chain):
    """Backfill correctness against the REAL table shapes.

    Rows are seeded through the repository's own creators where they
    exist, so the columns are whatever production actually writes rather
    than whatever this test imagines.
    """

    def setUp(self):
        super().setUp()
        # A person and trip, then days, then photo links carrying the
        # legacy scalar -- then 0043 is re-run against that data.
        self.exec_("INSERT INTO people(id, display_name, created_at,"
                   " updated_at) VALUES ('p1','P',datetime('now'),"
                   "datetime('now'))")
        self.exec_("INSERT INTO trips(id, person_id, title, created_at,"
                   " updated_at) VALUES ('T1','p1','Trip',datetime('now'),"
                   "datetime('now'))")
        for did, idx in (("D1", 1), ("D2", 2)):
            self.exec_(
                "INSERT INTO trip_days(id, trip_id, day_index, date,"
                " created_at, updated_at) VALUES (?,?,?,?,datetime('now'),"
                "datetime('now'))", (did, "T1", idx, "2026-07-1%d" % idx))
        # trip_photo_links.photo_id REFERENCES photos(id) since migration
        # 0037, and photos requires narrator_id / image_path / file_hash.
        # Seeding links without the photo rows fails the FK -- which is the
        # whole reason this suite exists: the minimal-schema suite cannot
        # see constraints it did not declare.
        for lid, day in (("PL1", "D1"), ("PL2", "D2"), ("PL3", None)):
            self.exec_(
                "INSERT INTO photos(id, narrator_id, image_path, file_hash,"
                " uploaded_by_user_id) VALUES (?,?,?,?,?)",
                ("ph-" + lid, "p1", "/tmp/%s.jpg" % lid, "hash-" + lid, "op"))
            self.exec_(
                "INSERT INTO trip_photo_links(id, trip_id, photo_id,"
                " trip_day_id, created_at, updated_at)"
                " VALUES (?,?,?,?,datetime('now'),datetime('now'))",
                (lid, "T1", "ph-" + lid, day))
        # Re-run the migration file over the now-populated database.
        con = sqlite3.connect(self.path)
        con.executescript(
            (_REPO_ROOT / "server" / "code" / "db" / "migrations"
             / _MIGRATION_NAME).read_text(encoding="utf-8"))
        con.commit()
        con.close()

    def test_exact_backfill_against_real_tables(self):
        rows = self.q("SELECT photo_link_id, trip_day_id, placement_method"
                      " FROM %s ORDER BY photo_link_id" % _TABLE)
        self.assertEqual(
            [(r["photo_link_id"], r["trip_day_id"]) for r in rows],
            [("PL1", "D1"), ("PL2", "D2")])
        self.assertTrue(all(r["placement_method"] == "backfill" for r in rows))

    def test_foreign_key_check_still_clean_after_backfill(self):
        self.assertEqual(self.q("PRAGMA foreign_key_check"), [])

    def test_the_bridge_works_on_the_real_schema(self):
        """End to end on production table shapes, not a stand-in."""
        repo.photo_links_set_day(["PL1"], "D2", "T1")
        days = [r["trip_day_id"] for r in self.q(
            "SELECT trip_day_id FROM %s WHERE photo_link_id='PL1'" % _TABLE)]
        self.assertEqual(days, ["D2"], "bridge left the old placement behind")
        self.assertEqual(
            self.q("SELECT trip_day_id FROM trip_photo_links WHERE id='PL1'"
                   )[0]["trip_day_id"], "D2")

    def test_the_deletion_tally_reads_placements_on_the_real_schema(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            counts = repo._day_attachment_counts(con, "T1")
        finally:
            con.close()
        self.assertEqual(counts.get("D1", {}).get("photos"), 1)
        self.assertFalse(repo._day_is_empty({"id": "D1"}, counts))


if __name__ == "__main__":
    unittest.main()
