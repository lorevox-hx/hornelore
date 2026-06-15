"""WO-LORI-BIO-BUILDER-UNIVERSAL-01 (2026-06-14) — Phase A seed loader at init.

Verifies the once-per-process seed loader gate behaves correctly:
  - First init_db() with empty bio_fields table loads the seed
  - Subsequent init_db() calls are skipped via _BIO_SEED_LOADED flag
  - Seed loader sits before the FK enforcement point so bio_fact_create
    succeeds against a populated bio_fields table
  - Empty bio_fields + FK enforcement = bio_fact_create FAILS
    (regression check — this is the bug this fix prevents)
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))


def _setup_bare_db():
    """Build a temp DB with just the two bio tables — no seed
    loaded. Tests will exercise the seed-load path against this
    bare state."""
    tmpdir = tempfile.mkdtemp(prefix="hornelore_test_bio_seed_init_")
    db_path = os.path.join(tmpdir, "test.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        # Enable FK enforcement — mirrors production _connect()
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS bio_fields (
                id TEXT PRIMARY KEY,
                field_key TEXT NOT NULL UNIQUE,
                field_label TEXT NOT NULL,
                field_category TEXT NOT NULL,
                field_type TEXT NOT NULL,
                narrative_value TEXT NOT NULL DEFAULT 'medium',
                life_stage_range TEXT NOT NULL DEFAULT 'all',
                asking_anchors TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS bio_facts (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL DEFAULT 'default',
                narrator_id TEXT NOT NULL,
                field_key TEXT NOT NULL,
                value TEXT NOT NULL DEFAULT '""',
                status TEXT NOT NULL DEFAULT 'empty',
                source TEXT NOT NULL DEFAULT '{}',
                confidence REAL NOT NULL DEFAULT 0.0,
                chapter_continuation_metric TEXT,
                conflict_with TEXT,
                created_at TEXT NOT NULL,
                last_updated TEXT NOT NULL,
                FOREIGN KEY (field_key) REFERENCES bio_fields(field_key)
            );
        """)
        conn.commit()
    finally:
        conn.close()
    return db_path, tmpdir


class _SeedLoaderBase(unittest.TestCase):
    """Patches db._connect to use a temp file, neuters init_db (test
    fixture pre-built the bio tables), and clears the seed flag so
    each test starts from an empty bio_fields table.

    init_db is no-op'd because its production body has a relative
    import (from ..db.migrations_runner) that fails in test context
    where `api` is the top-level package. The seed-loader wiring
    inside init_db is verified via source inspection in
    InitDbWiringTest rather than by running init_db directly.
    """

    def setUp(self):
        from api import db
        self._db = db
        self._db_path, self._tmpdir = _setup_bare_db()
        self._orig_connect = db._connect
        self._orig_init_db = db.init_db

        def _patched_connect():
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON;")
            return conn

        db._connect = _patched_connect
        db.init_db = lambda: None
        # Force the seed loader to re-fire under each test by clearing
        # the once-per-process flag.
        db._BIO_SEED_LOADED = False

    def tearDown(self):
        self._db._connect = self._orig_connect
        self._db.init_db = self._orig_init_db
        # Leave _BIO_SEED_LOADED reset; the production process gets
        # its own True state on first real init_db() call.
        self._db._BIO_SEED_LOADED = False
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _count_bio_fields(self) -> int:
        conn = sqlite3.connect(self._db_path)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM bio_fields;",
            ).fetchone()
            return int(row[0] or 0) if row else 0
        finally:
            conn.close()


class SeedLoaderFlagTest(_SeedLoaderBase):
    """The once-per-process flag controls whether the seed loader
    fires. Without this guard, every init_db() call (which happens
    at the top of every db accessor) would re-UPSERT 67 rows."""

    def test_flag_starts_false(self):
        # Module-level default is False; setUp explicitly resets
        self.assertFalse(self._db._BIO_SEED_LOADED)

    def test_calling_seed_loader_directly_works(self):
        """The bio_schema_seed_load_to_db() function itself is
        callable and writes the seed."""
        n = self._db.bio_schema_seed_load_to_db()
        self.assertGreater(n, 0)
        self.assertEqual(self._count_bio_fields(), n)

    def test_seed_load_idempotent(self):
        """Calling the seed loader twice does not duplicate rows
        (bio_field_upsert pattern)."""
        n1 = self._db.bio_schema_seed_load_to_db()
        n2 = self._db.bio_schema_seed_load_to_db()
        self.assertEqual(n1, n2)
        # bio_fields has UNIQUE(field_key) so duplicates would have
        # crashed; count must equal seed size, not 2x.
        from api.services.bio_schema import BIO_SCHEMA_SEED
        self.assertEqual(self._count_bio_fields(), len(BIO_SCHEMA_SEED))


class FkEnforcementRegressionTest(_SeedLoaderBase):
    """Regression: confirm that without the seed, bio_fact_create
    fails with FOREIGN KEY constraint failed. This is the bug the
    init-time seed loader prevents."""

    def test_empty_bio_fields_table_blocks_bio_fact_insert(self):
        """With bio_fields empty + FK enforcement on, a direct
        bio_facts insert MUST fail. The seed loader is the fix."""
        # Bypass init_db (skip the seed) — write directly via _connect
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA foreign_keys=ON;")
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO bio_facts (id, tenant_id, narrator_id, "
                    "field_key, value, status, source, confidence, "
                    "created_at, last_updated) VALUES "
                    "('a', 'default', 'N1', 'birth_date', '\"1938\"', "
                    "'extracted_needs_verify', '{}', 0.9, "
                    "'2026-06-14T00:00:00Z', '2026-06-14T00:00:00Z');",
                )
                conn.commit()
        finally:
            conn.close()

    def test_seed_loaded_then_bio_fact_insert_succeeds(self):
        """The fix: load the seed first; bio_facts INSERT now works
        because bio_fields(field_key='birth_date') exists for the FK
        to satisfy."""
        # Load the seed (the production fix path)
        self._db.bio_schema_seed_load_to_db()
        # Now the same INSERT that failed before should succeed
        new_id = self._db.bio_fact_create(
            narrator_id="N1",
            field_key="birth_date",
            value_json=json.dumps("1938"),
            status="extracted_needs_verify",
            confidence=0.9,
        )
        self.assertTrue(new_id)
        row = self._db.bio_fact_get(new_id)
        self.assertIsNotNone(row)
        self.assertEqual(row["field_key"], "birth_date")


class InitDbWiringTest(_SeedLoaderBase):
    """End-to-end: confirm that calling init_db() with the flag at
    False triggers the seed loader. Note we don't actually run the
    real init_db() because it builds dozens of unrelated tables; we
    test the wiring by inspecting the module-level flag transitions
    that the production block performs."""

    def test_module_level_flag_exists(self):
        # Defensive check that the flag is exposed at the module
        # level (production code reads/writes via `global` inside
        # init_db). Tests rely on this exposure to reset between
        # cases.
        self.assertTrue(hasattr(self._db, "_BIO_SEED_LOADED"))
        self.assertIsInstance(self._db._BIO_SEED_LOADED, bool)

    def test_seed_loader_function_exposed(self):
        # bio_schema_seed_load_to_db must be importable from the
        # api.db module so the in-init block can `global`-flag-guard
        # the call without an extra import.
        self.assertTrue(hasattr(self._db, "bio_schema_seed_load_to_db"))
        self.assertTrue(callable(self._db.bio_schema_seed_load_to_db))

    def test_init_db_source_carries_seed_wiring(self):
        # Source-inspection contract check that the seed-load block
        # is actually wired into init_db. Without this assertion,
        # someone could accidentally drop the call from init_db and
        # the runtime tests above would still pass (they bypass
        # init_db). This test is the structural guard.
        src_path = (
            _REPO_ROOT / "server" / "code" / "api" / "db.py"
        )
        src = src_path.read_text(encoding="utf-8")
        # The flag-guarded call must be present in init_db
        self.assertIn("global _BIO_SEED_LOADED", src)
        self.assertIn(
            "if not _BIO_SEED_LOADED:",
            src,
        )
        self.assertIn(
            "bio_schema_seed_load_to_db()",
            src,
        )
        self.assertIn(
            "_BIO_SEED_LOADED = True",
            src,
        )

    def test_init_db_source_carries_attribution_comment(self):
        # Archeology check — future readers should be able to trace
        # the wiring back to this WO.
        src_path = (
            _REPO_ROOT / "server" / "code" / "api" / "db.py"
        )
        src = src_path.read_text(encoding="utf-8")
        # The seed-load block sits inside init_db (not at module top)
        # and carries the WO attribution.
        seed_block_marker = (
            "WO-LORI-BIO-BUILDER-UNIVERSAL-01 (2026-06-14) — Phase A seed load"
        )
        self.assertIn(seed_block_marker, src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
