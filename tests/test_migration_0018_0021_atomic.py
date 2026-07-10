"""WO-TRIP-LANE-AUDIT-FIXPACK-01 (H2) — atomic/idempotent rebuild
migrations 0018 & 0021.

The two trip_photo_links table-rebuild migrations must:
  * run cleanly on a fresh DB and preserve data,
  * be no-ops on re-run (runner skips applied files),
  * NOT brick when a `trip_photo_links_new` temp table is left behind by
    a previously-failed run (DROP TABLE IF EXISTS clears it),
  * wrap the rebuild in BEGIN/COMMIT so a mid-rebuild failure rolls back.
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api import db as _db  # noqa: E402
from db.migrations_runner import run_pending_migrations  # noqa: E402

_MIG = _SERVER_CODE / "db" / "migrations"

# Original (pre-0018) trip_photo_links shape — 17 columns, 0015 enum
# WITHOUT trip_upload/region_upload. SELECT * copy-forward in 0018/0021
# requires the source to match this column set/order.
_ORIG_TABLE = """
CREATE TABLE trip_photo_links (
    id TEXT PRIMARY KEY,
    trip_id TEXT NOT NULL,
    trip_region_id TEXT,
    trip_stop_id TEXT,
    photo_id TEXT NOT NULL,
    ord INTEGER NOT NULL DEFAULT 0,
    taken_at TEXT,
    latitude REAL,
    longitude REAL,
    assignment_method TEXT NOT NULL DEFAULT 'exif_time'
        CHECK (assignment_method IN (
            'manual', 'exif_time', 'exif_gps', 'album', 'csv', 'operator'
        )),
    cluster_confidence REAL,
    caption TEXT,
    narrator_caption TEXT,
    include_in_memoir INTEGER NOT NULL DEFAULT 1,
    thematic_tags_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def _table_exists(con, name):
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone() is not None


class Migration0018_0021AtomicTest(unittest.TestCase):
    def setUp(self):
        self._tmpdb = tempfile.NamedTemporaryFile(
            suffix=".sqlite3", delete=False)
        self._tmpdb.close()
        self.db_path = Path(self._tmpdb.name)

    def tearDown(self):
        try:
            self.db_path.unlink()
        except OSError:
            pass

    # --- structure guards ----------------------------------------------
    def test_files_are_atomic_and_idempotent_shaped(self):
        for name in ("0018_trip_photo_links_trip_upload.sql",
                     "0021_trip_photo_links_region_upload.sql"):
            sql = (_MIG / name).read_text(encoding="utf-8")
            self.assertIn("DROP TABLE IF EXISTS trip_photo_links_new", sql,
                          name)
            self.assertIn("BEGIN;", sql, name)
            self.assertIn("COMMIT;", sql, name)

    # --- clean full-migration run + data preserved ---------------------
    def test_clean_db_accepts_new_assignment_methods(self):
        _orig = _db.DB_PATH
        _db.DB_PATH = self.db_path
        try:
            _db.init_db()
            con = sqlite3.connect(str(self.db_path))
            try:
                # both new enum values (0018 + 0021) must be accepted
                for method in ("trip_upload", "region_upload"):
                    con.execute(
                        "INSERT INTO trip_photo_links "
                        "(id, trip_id, photo_id, assignment_method) "
                        "VALUES (?, 't', ?, ?)",
                        (str(uuid.uuid4()), "photo_" + method, method))
                con.commit()
                with self.assertRaises(sqlite3.IntegrityError):
                    con.execute(
                        "INSERT INTO trip_photo_links "
                        "(id, trip_id, photo_id, assignment_method) "
                        "VALUES (?, 't', 'p', 'bogus_method')",
                        (str(uuid.uuid4()),))
                    con.commit()
            finally:
                con.close()
        finally:
            _db.DB_PATH = _orig

    def test_runner_rerun_is_noop(self):
        _orig = _db.DB_PATH
        _db.DB_PATH = self.db_path
        try:
            _db.init_db()
            con = sqlite3.connect(str(self.db_path))
            try:
                # everything already applied → second run applies nothing
                applied = run_pending_migrations(con)
                self.assertEqual(applied, [])
            finally:
                con.close()
        finally:
            _db.DB_PATH = _orig

    # --- leftover temp table must NOT brick ----------------------------
    def _leftover_scenario(self, migration_name):
        con = sqlite3.connect(str(self.db_path))
        try:
            con.executescript(_ORIG_TABLE)
            row_id = str(uuid.uuid4())
            con.execute(
                "INSERT INTO trip_photo_links "
                "(id, trip_id, photo_id, assignment_method) "
                "VALUES (?, 'trip1', 'photo1', 'exif_time')", (row_id,))
            # simulate a prior failed run that left the temp table behind
            con.execute("CREATE TABLE trip_photo_links_new (id TEXT)")
            con.commit()
            sql = (_MIG / migration_name).read_text(encoding="utf-8")
            con.executescript(sql)          # must NOT raise
            con.commit()
            # data preserved
            self.assertEqual(
                con.execute("SELECT trip_id FROM trip_photo_links "
                            "WHERE id=?", (row_id,)).fetchone()[0], "trip1")
            # temp table gone
            self.assertFalse(_table_exists(con, "trip_photo_links_new"))
            return con
        finally:
            con.close()

    def test_0018_leftover_does_not_brick(self):
        con = sqlite3.connect(str(self.db_path))
        con.close()
        self._leftover_scenario("0018_trip_photo_links_trip_upload.sql")
        # new enum available after rebuild
        con = sqlite3.connect(str(self.db_path))
        try:
            con.execute(
                "INSERT INTO trip_photo_links "
                "(id, trip_id, photo_id, assignment_method) "
                "VALUES (?, 't', 'p', 'trip_upload')", (str(uuid.uuid4()),))
            con.commit()
        finally:
            con.close()

    def test_0021_leftover_does_not_brick(self):
        self._leftover_scenario("0021_trip_photo_links_region_upload.sql")
        con = sqlite3.connect(str(self.db_path))
        try:
            con.execute(
                "INSERT INTO trip_photo_links "
                "(id, trip_id, photo_id, assignment_method) "
                "VALUES (?, 't', 'p', 'region_upload')",
                (str(uuid.uuid4()),))
            con.commit()
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
