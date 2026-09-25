"""C-4D precondition — what the migration runner ACTUALLY guarantees.

`db/migrations_runner.py` promised "each file is applied inside its own
transaction" and "a failure leaves schema_migrations without the entry". It
calls `executescript(sql)` with no BEGIN of its own, then inserts the tracking
row, then commits. These tests pin the real behaviour on scratch databases,
connected exactly as the product connects (`api.db._connect`: WAL,
foreign_keys=ON, default isolation):

  * a migration that fails half way leaves NOTHING behind and is not recorded;
  * the next run retries it cleanly;
  * the body and its tracking row are ONE operation (a failing tracking insert
    undoes the body);
  * PRAGMA foreign_keys is ON after success and after failure;
  * files that carry their own BEGIN … COMMIT (historical, immutable) still run;
  * a table rebuild under the runner's foreign-key protocol keeps child rows
    valid, and one that would orphan them is refused and rolled back;
  * the whole historical sequence builds a clean scratch database.

Every database here is a temp file. No persistent Hornelore database is
touched.
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))
sys.path.insert(0, str(REPO))

from db import migrations_runner as R  # noqa: E402

MIG_DIR = REPO / "server" / "code" / "db" / "migrations"


def connect(path):
    """The product's connection settings (api/db.py `_connect`)."""
    con = sqlite3.connect(str(path), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    return con


class _Scratch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "migrations"
        self.dir.mkdir()
        self.db = Path(self.tmp.name) / "scratch.sqlite3"
        self.con = connect(self.db)

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def mig(self, name, sql):
        (self.dir / name).write_text(sql, encoding="utf-8")

    def run_all(self):
        return R.run_pending_migrations(self.con, migrations_dir=self.dir)

    def fresh(self):
        """What another process sees — committed state only."""
        c = connect(self.db)
        try:
            return {
                "tables": {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")},
                "applied": {r[0] for r in c.execute("SELECT filename FROM schema_migrations")},
            }
        finally:
            c.close()

    def fk_on(self):
        return self.con.execute("PRAGMA foreign_keys").fetchone()[0] == 1


class RunnerManagedMigrations(_Scratch):
    """Files with no transaction control of their own: the runner owns the
    transaction."""

    def test_a_half_failed_migration_leaves_nothing_and_is_not_recorded(self):
        self.mig("0001_bad.sql", "CREATE TABLE a (x TEXT);\nINSERT INTO a VALUES ('kept?');\n"
                                 "INSERT INTO no_such_table VALUES (1);\n")
        with self.assertRaises(sqlite3.Error):
            self.run_all()
        after = self.fresh()
        self.assertNotIn("a", after["tables"], "the half-applied CREATE TABLE survived the failure")
        self.assertNotIn("0001_bad.sql", after["applied"])
        self.assertFalse(self.con.in_transaction, "a failed migration left a transaction open")

    def test_the_next_run_retries_cleanly(self):
        self.mig("0001_bad.sql", "CREATE TABLE a (x TEXT);\nALTER TABLE a ADD COLUMN y TEXT;\n"
                                 "INSERT INTO no_such_table VALUES (1);\n")
        with self.assertRaises(sqlite3.Error):
            self.run_all()
        # the operator fixes the file (it was never applied anywhere) and boots again
        self.mig("0001_bad.sql", "CREATE TABLE a (x TEXT);\nALTER TABLE a ADD COLUMN y TEXT;\n")
        self.assertEqual(self.run_all(), ["0001_bad.sql"])
        self.assertIn("a", self.fresh()["tables"])

    def test_the_body_and_its_tracking_row_are_one_operation(self):
        # The migration itself makes the tracking insert fail: if the body
        # committed separately, table `b` would survive without its row.
        self.mig("0001_track.sql",
                 "CREATE TABLE b (x TEXT);\n"
                 "CREATE TRIGGER no_tracking BEFORE INSERT ON schema_migrations "
                 "BEGIN SELECT RAISE(ABORT, 'tracking refused'); END;\n")
        with self.assertRaises(sqlite3.Error):
            self.run_all()
        after = self.fresh()
        self.assertNotIn("b", after["tables"], "the body committed without its tracking row")
        self.assertNotIn("0001_track.sql", after["applied"])

    def test_success_records_exactly_once_and_rerun_is_a_no_op(self):
        self.mig("0001_ok.sql", "CREATE TABLE c (x TEXT);\n")
        self.assertEqual(self.run_all(), ["0001_ok.sql"])
        self.assertEqual(self.run_all(), [])
        self.assertEqual(self.fresh()["applied"], {"0001_ok.sql"})

    def test_foreign_keys_stay_on_after_success_and_after_failure(self):
        self.mig("0001_ok.sql", "CREATE TABLE c (x TEXT);\n")
        self.run_all()
        self.assertTrue(self.fk_on())
        self.mig("0002_bad.sql", "CREATE TABLE d (x TEXT);\nINSERT INTO nope VALUES (1);\n")
        with self.assertRaises(sqlite3.Error):
            self.run_all()
        self.assertTrue(self.fk_on())


class SelfManagedMigrations(_Scratch):
    """Historical files carrying their own BEGIN … COMMIT (several also
    toggling PRAGMA foreign_keys). They are immutable; they must still
    work, and a failure must not leave foreign keys off or a transaction open."""

    def test_an_own_transaction_file_still_applies(self):
        self.mig("0001_own.sql", "BEGIN IMMEDIATE;\nCREATE TABLE e (x TEXT);\nCOMMIT;\n")
        self.assertEqual(self.run_all(), ["0001_own.sql"])
        self.assertIn("e", self.fresh()["tables"])

    def test_a_failure_inside_its_own_transaction_rolls_back_and_restores_foreign_keys(self):
        self.mig("0001_own_bad.sql",
                 "PRAGMA foreign_keys = OFF;\nBEGIN IMMEDIATE;\nCREATE TABLE f (x TEXT);\n"
                 "INSERT INTO nope VALUES (1);\nCOMMIT;\nPRAGMA foreign_keys = ON;\n")
        with self.assertRaises(sqlite3.Error):
            self.run_all()
        self.assertFalse(self.con.in_transaction, "the file's transaction was left open")
        self.assertTrue(self.fk_on(), "the file switched foreign keys off and failed before switching back")
        after = self.fresh()
        self.assertNotIn("f", after["tables"])
        self.assertNotIn("0001_own_bad.sql", after["applied"])


class RebuildUnderTheRunner(_Scratch):
    """The C-4D shape: rebuild a parent table that children reference. The
    file declares `-- migration: foreign_keys=off`; the runner switches
    foreign keys off OUTSIDE its transaction (SQLite ignores the pragma
    inside one), checks for new violations before commit, and restores."""

    PARENT = ("CREATE TABLE p (id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK (kind IN ('a','b')));\n"
              "CREATE TABLE ch (id TEXT PRIMARY KEY, p_id TEXT NOT NULL REFERENCES p(id));\n"
              "INSERT INTO p VALUES ('p1','a'),('p2','b');\n"
              "INSERT INTO ch VALUES ('c1','p1'),('c2','p2');\n")
    REBUILD = ("-- migration: foreign_keys=off\n"
               "CREATE TABLE p_new (id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK (kind IN ('a','b','c')));\n"
               "INSERT INTO p_new (id, kind) SELECT id, kind FROM p {where};\n"
               "DROP TABLE p;\nALTER TABLE p_new RENAME TO p;\n")

    def test_a_faithful_rebuild_keeps_children_valid(self):
        self.mig("0001_base.sql", self.PARENT)
        self.mig("0002_rebuild.sql", self.REBUILD.format(where=""))
        self.assertEqual(self.run_all(), ["0001_base.sql", "0002_rebuild.sql"])
        self.assertTrue(self.fk_on())
        self.assertEqual(self.con.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.con.execute("INSERT INTO p VALUES ('p3','c')")          # the new member is admitted
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute("INSERT INTO ch VALUES ('c9','nobody')")   # enforcement is back on

    def test_a_rebuild_that_orphans_children_is_refused_and_rolled_back(self):
        self.mig("0001_base.sql", self.PARENT)
        self.run_all()
        self.mig("0002_rebuild.sql", self.REBUILD.format(where="WHERE id = 'p1'"))
        with self.assertRaises(sqlite3.Error):
            self.run_all()
        self.assertTrue(self.fk_on())
        c = connect(self.db)
        try:
            self.assertEqual(sorted(r[0] for r in c.execute("SELECT id FROM p")), ["p1", "p2"],
                             "the lossy rebuild committed")
            self.assertNotIn("0002_rebuild.sql", {r[0] for r in c.execute("SELECT filename FROM schema_migrations")})
        finally:
            c.close()

    def test_an_existing_violation_elsewhere_does_not_block_an_unrelated_rebuild(self):
        # A persistent database may carry an old violation the migration did
        # not cause; only NEW violations refuse the migration.
        self.mig("0001_base.sql", self.PARENT)
        self.run_all()
        self.con.execute("PRAGMA foreign_keys=OFF")
        self.con.execute("CREATE TABLE other (id TEXT, p_id TEXT REFERENCES p(id))")
        self.con.execute("INSERT INTO other VALUES ('o1','ghost')")
        self.con.commit()
        self.con.execute("PRAGMA foreign_keys=ON")
        self.mig("0002_rebuild.sql", self.REBUILD.format(where=""))
        self.assertEqual(self.run_all(), ["0002_rebuild.sql"])


class TheHistoricalSequence(unittest.TestCase):
    def test_every_shipped_migration_builds_a_clean_scratch_database(self):
        from api import db as _db
        with tempfile.TemporaryDirectory() as d:
            orig = _db.DB_PATH
            _db.DB_PATH = Path(d) / "hist.sqlite3"
            try:
                _db.init_db()
                con = connect(_db.DB_PATH)
                try:
                    applied = {r[0] for r in con.execute("SELECT filename FROM schema_migrations")}
                    shipped = {p.name for p in MIG_DIR.glob("*.sql")}
                    self.assertEqual(applied, shipped)
                    self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])
                    self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                    self.assertEqual(R.run_pending_migrations(con), [], "a rerun is a no-op")
                finally:
                    con.close()
            finally:
                _db.DB_PATH = orig


if __name__ == "__main__":
    unittest.main()
