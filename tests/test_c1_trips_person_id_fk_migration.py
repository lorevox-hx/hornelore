"""Bucket C.1 — real schema-level FK on trips.person_id.

Locks migration 0034_trips_person_id_fk.sql. Coverage:

  * On a fresh DB, PRAGMA foreign_key_check returns zero rows
    after init_db (proves the migration lands clean).
  * A direct-SQL INSERT of a trip whose person_id has no matching
    people.id raises IntegrityError with SQLITE_CONSTRAINT_FOREIGNKEY.
    This is the whole point — the API-level gate is defense in depth
    and the schema-level constraint is the real guarantee.
  * DELETE of a person cascade-deletes their trips (and by extension,
    their trip_regions / trip_stops / trip_photo_links / etc via the
    already-declared CASCADE chain in 0015_trip_tables.sql).
  * If the DB somehow already has orphan trips before the migration
    runs, the migration DELETEs them and boots clean. The api.log
    "[migrations] pre-0034" warning surfaces the count.
  * The API-level _validate_person_id_exists gate STILL fires (i.e.,
    the constraint doesn't replace the app-side validation — both
    layers cooperate).

Fresh sqlite fixture per test.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import types
import unittest
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

# Same fastapi/pydantic stub pattern as the sibling trip test files
# so importing api.routers.trips doesn't drag the framework in.
if "fastapi" not in sys.modules:
    stub = types.ModuleType("fastapi")

    class _APIRouter:
        def __init__(self, *a, **k): pass

        def _deco(self, *a, **k):
            def wrap(f):
                return f
            return wrap
        get = post = patch = delete = put = _deco

    class _HTTPException(Exception):
        def __init__(self, status_code=0, detail=""):
            self.status_code, self.detail = status_code, detail
            super().__init__(detail)

    stub.APIRouter = _APIRouter
    stub.HTTPException = _HTTPException
    stub.Query = lambda default=None, **k: default
    stub.File = lambda default=None, **k: default
    stub.Form = lambda default=None, **k: default
    stub.UploadFile = object
    sys.modules["fastapi"] = stub

if "pydantic" not in sys.modules:
    pstub = types.ModuleType("pydantic")

    class _BaseModel: pass
    pstub.BaseModel = _BaseModel
    pstub.Field = lambda default=None, **k: default
    pstub.field_validator = lambda *a, **k: (lambda f: f)
    pstub.validator = lambda *a, **k: (lambda f: f)
    pstub.ConfigDict = dict
    sys.modules["pydantic"] = pstub

from api import db as _db  # noqa: E402
from api.services import trip_repository  # noqa: E402
from api.routers import trips  # noqa: E402

HTTPException = trips.HTTPException


class _Req:
    def __init__(self, **kw):
        base = dict(
            person_id=None, title=None,
            start_date=None, end_date=None, summary=None,
            clear_start_date=False, clear_end_date=False, clear_summary=False,
        )
        base.update(kw)
        self.__dict__.update(base)


class _FreshDBBase(unittest.TestCase):
    def setUp(self):
        self._tmpdb = tempfile.NamedTemporaryFile(
            suffix=".sqlite3", delete=False)
        self._tmpdb.close()
        self.db_path = Path(self._tmpdb.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()
        self._orig_flag = os.environ.get("HORNELORE_TRIPS")
        os.environ["HORNELORE_TRIPS"] = "1"
        self.person_id = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO people (id, display_name, date_of_birth, "
            "created_at, updated_at) VALUES (?, 'Chris', '1962-12-24', "
            "'2026-07-23', '2026-07-23')", (self.person_id,))
        con.commit()
        con.close()

    def tearDown(self):
        if self._orig_flag is None:
            os.environ.pop("HORNELORE_TRIPS", None)
        else:
            os.environ["HORNELORE_TRIPS"] = self._orig_flag
        _db.DB_PATH = self._orig_db
        try:
            self.db_path.unlink()
        except OSError:
            pass


# ── Migration lands clean on a fresh DB ─────────────────────────

class MigrationLandsCleanTest(_FreshDBBase):
    def test_migration_recorded_in_schema_migrations(self):
        """Fresh init_db must apply 0034 and record it."""
        con = sqlite3.connect(str(self.db_path))
        try:
            rows = con.execute(
                "SELECT filename FROM schema_migrations "
                "WHERE filename = '0034_trips_person_id_fk.sql';"
            ).fetchall()
            self.assertEqual(len(rows), 1,
                             "migration 0034 should be recorded")
        finally:
            con.close()

    def test_foreign_key_check_returns_zero_rows_after_migration(self):
        """The whole point: no orphans after the migration lands."""
        con = sqlite3.connect(str(self.db_path))
        try:
            con.execute("PRAGMA foreign_keys = ON;")
            violations = con.execute(
                "PRAGMA foreign_key_check;").fetchall()
            self.assertEqual(
                violations, [],
                f"foreign_key_check should return zero rows post-migration; "
                f"got {violations!r}")
        finally:
            con.close()

    def test_trips_table_has_person_id_fk_constraint(self):
        """Confirm the CREATE TABLE now includes REFERENCES people(id)."""
        con = sqlite3.connect(str(self.db_path))
        try:
            fks = con.execute(
                "PRAGMA foreign_key_list(trips);").fetchall()
            # Each row: (id, seq, table, from, to, on_update, on_delete, match)
            matching = [
                r for r in fks
                if r[2] == "people" and r[3] == "person_id"
            ]
            self.assertEqual(
                len(matching), 1,
                f"trips.person_id must have exactly one FK to people(id); "
                f"got {fks!r}")
            on_delete = matching[0][6]
            self.assertEqual(
                on_delete, "CASCADE",
                f"person_id FK ON DELETE must be CASCADE; got {on_delete!r}")
        finally:
            con.close()

    def test_idx_trips_person_id_survives_table_rebuild(self):
        """The migration DROPs the old table (which drops the index) and
        recreates the index. If it forgets to, person-scoped queries
        would fall back to a table scan."""
        con = sqlite3.connect(str(self.db_path))
        try:
            idx = con.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND tbl_name='trips';"
            ).fetchall()
            names = {r[0] for r in idx}
            self.assertIn(
                "idx_trips_person_id", names,
                f"idx_trips_person_id must exist after rebuild; got {names!r}")
        finally:
            con.close()


# ── Schema-level constraint fires on orphan INSERT ──────────────

class OrphanInsertRefusedAtSchemaLevelTest(_FreshDBBase):
    def test_direct_sql_insert_of_orphan_trip_raises_fk_constraint(self):
        """The whole reason we did this migration. A direct SQL INSERT
        (bypassing the API's _validate_person_id_exists gate) now fails
        at the schema level. Previously it would have succeeded and
        left an orphan for the next FK-enabled write to trip on."""
        con = sqlite3.connect(str(self.db_path))
        try:
            con.execute("PRAGMA foreign_keys = ON;")
            fake = str(uuid.uuid4())
            with self.assertRaises(sqlite3.IntegrityError) as cm:
                con.execute(
                    "INSERT INTO trips (id, person_id, title, "
                    "created_at, updated_at, meta_json) VALUES "
                    "(?, ?, 'Orphan trip', '2026-07-23', "
                    "'2026-07-23', '{}');",
                    (str(uuid.uuid4()), fake),
                )
                con.commit()
            # Python 3.11+ carries the specific error name
            errname = getattr(cm.exception, "sqlite_errorname", None)
            if errname is not None:
                self.assertIn(
                    "CONSTRAINT_FOREIGNKEY", errname,
                    f"expected SQLITE_CONSTRAINT_FOREIGNKEY, "
                    f"got {errname!r}")
        finally:
            con.close()

    def test_delete_person_cascade_deletes_trips(self):
        """A person's deletion must remove their trips too."""
        # Create a trip against our valid narrator
        out = trips.create_trip(_Req(
            person_id=self.person_id,
            title="Cascade target",
            start_date="2026-08-03",
            end_date="2026-08-07"))
        trip_id = out["trip_id"]
        self.assertIsNotNone(trip_repository.trip_get(trip_id))

        # DELETE the person via direct SQL (with FKs on so cascade fires)
        con = sqlite3.connect(str(self.db_path))
        try:
            con.execute("PRAGMA foreign_keys = ON;")
            con.execute(
                "DELETE FROM people WHERE id = ?;", (self.person_id,))
            con.commit()
        finally:
            con.close()

        # Trip must be gone via cascade
        self.assertIsNone(
            trip_repository.trip_get(trip_id),
            "trip must cascade-delete when its owning person is deleted")

    def test_api_gate_still_fires_defense_in_depth(self):
        """Belt-and-braces: the API's _validate_person_id_exists
        must still return 422 on a bogus person_id. The schema
        constraint is the enforcement; the API gate is the
        actionable-error UX."""
        with self.assertRaises(HTTPException) as cm:
            trips.create_trip(_Req(
                person_id="PASTE_UUID_HERE",
                title="Should be 422"))
        self.assertEqual(cm.exception.status_code, 422)
        self.assertIn(
            "does not match any narrator", cm.exception.detail)
        # And no orphan landed:
        self.assertEqual(trip_repository.trip_list(), [])


# ── Preflight orphan cleanup (log + delete on pending migration) ─

class PreflightOrphanCleanupTest(unittest.TestCase):
    """Simulate a pre-0034 DB that already carries orphans (e.g.,
    trips created before the API gate landed in 1e388b5). Verify:
    (a) migration deletes them cleanly, (b) db.py's preflight log
    surfaces the count via logger.warning at boot."""

    def setUp(self):
        self._tmpdb = tempfile.NamedTemporaryFile(
            suffix=".sqlite3", delete=False)
        self._tmpdb.close()
        self.db_path = Path(self._tmpdb.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        # First init_db lands 0034 clean (no orphans on a fresh DB).
        _db.init_db()
        # Now simulate a pre-migration state: drop the 0034 record so
        # it re-runs, and manually insert an orphan trip (bypassing
        # FK enforcement).
        con = sqlite3.connect(str(self.db_path))
        try:
            con.execute("PRAGMA foreign_keys = OFF;")
            con.execute(
                "DELETE FROM schema_migrations WHERE filename = "
                "'0034_trips_person_id_fk.sql';")
            self.orphan_person = str(uuid.uuid4())
            for i in range(3):
                con.execute(
                    "INSERT INTO trips (id, person_id, title, "
                    "created_at, updated_at, meta_json) VALUES "
                    "(?, ?, ?, '2026-07-23', '2026-07-23', '{}');",
                    (str(uuid.uuid4()), self.orphan_person,
                     f"Pre-existing orphan {i}"),
                )
            con.commit()
        finally:
            con.close()

    def tearDown(self):
        _db.DB_PATH = self._orig_db
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def test_re_init_deletes_orphans_and_logs_count(self):
        """When 0034 re-runs against a DB with 3 pre-existing orphans,
        the migration DELETEs them and db.py's preflight logs the count."""
        # Confirm pre-state: 3 orphan trips, 0 people
        con = sqlite3.connect(str(self.db_path))
        try:
            pre_orphans = con.execute(
                "SELECT COUNT(*) FROM trips t "
                "LEFT JOIN people p ON t.person_id = p.id "
                "WHERE p.id IS NULL;").fetchone()[0]
            self.assertEqual(pre_orphans, 3)
        finally:
            con.close()

        # Capture the preflight log
        import logging
        _handler = logging.StreamHandler()
        import io
        _buf = io.StringIO()
        _handler.stream = _buf
        _handler.setLevel(logging.WARNING)
        _target_logger = logging.getLogger("api.db")
        _target_logger.addHandler(_handler)
        _prior_level = _target_logger.level
        _target_logger.setLevel(logging.WARNING)

        # Also reset the bio-seed flag so init_db re-runs fully. This
        # is legitimate for the test because we're forcing a repeat
        # of the boot sequence to prove migration idempotency.
        _db._BIO_SEED_LOADED = False

        try:
            _db.init_db()
        finally:
            _target_logger.removeHandler(_handler)
            _target_logger.setLevel(_prior_level)

        # Orphans should be gone
        con = sqlite3.connect(str(self.db_path))
        try:
            post_orphans = con.execute(
                "SELECT COUNT(*) FROM trips t "
                "LEFT JOIN people p ON t.person_id = p.id "
                "WHERE p.id IS NULL;").fetchone()[0]
            self.assertEqual(
                post_orphans, 0,
                "orphan trips must be deleted by the migration")
        finally:
            con.close()

        # And the preflight log should have surfaced the count
        log_output = _buf.getvalue()
        self.assertIn(
            "pre-0034", log_output,
            f"expected '[migrations] pre-0034' warning in log; "
            f"got: {log_output!r}")
        self.assertIn(
            "3 orphan trip", log_output,
            f"expected '3 orphan trip(s)' in the count message; "
            f"got: {log_output!r}")


# ── Regression: orphan trip DELETE cascades to children ─────────

class OrphanDeleteCascadesToChildrenTest(unittest.TestCase):
    """The load-bearing regression test for the rev 2 fix. The first
    cut of 0034 did DELETE with foreign_keys OFF, which SKIPS
    ON DELETE CASCADE. That left trip_regions / trip_stops /
    trip_photo_links / trip_days / etc. stranded pointing at trip
    ids the migration had just removed. This test simulates the
    pre-migration state (fresh legacy schema, orphan trip + fully-
    populated child rows) and asserts that after 0034 rev 2 lands,
    the orphan trip's children are ALSO gone."""

    def setUp(self):
        self._tmpdb = tempfile.NamedTemporaryFile(
            suffix=".sqlite3", delete=False)
        self._tmpdb.close()
        self.db_path = Path(self._tmpdb.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        # Standard init_db lands 0034 and 0035 clean on a fresh DB.
        _db.init_db()

    def tearDown(self):
        _db.DB_PATH = self._orig_db
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def _make_orphan_trip_with_children(self):
        """Simulate: someone inserted an orphan trip (bypassing the API
        gate) and its FULL child ecosystem via direct SQL with FKs OFF,
        then the migration should DELETE all of them via cascade.

        Populates ONE row of every trip-child table so the cascade
        regression is covered end-to-end (not just the four tables
        the earlier version of this test happened to touch).
        """
        con = sqlite3.connect(str(self.db_path))
        try:
            con.execute("PRAGMA foreign_keys = OFF;")
            # Un-apply 0034 AND 0035 so we can test the 0034 cascade
            # path alone (without 0035 muddying which layer swept
            # what).
            con.execute(
                "DELETE FROM schema_migrations WHERE filename IN ("
                "'0034_trips_person_id_fk.sql', "
                "'0035_trips_orphan_children_cleanup.sql');")
            fake_person = str(uuid.uuid4())
            trip_id = str(uuid.uuid4())
            region_id = str(uuid.uuid4())
            stop_id = str(uuid.uuid4())
            day_id = str(uuid.uuid4())
            note_id = str(uuid.uuid4())
            source_id = str(uuid.uuid4())
            theme_id = str(uuid.uuid4())
            photo_link_id = str(uuid.uuid4())
            bio_sugg_id = str(uuid.uuid4())
            story_link_id = str(uuid.uuid4())
            public_ctx_id = str(uuid.uuid4())
            photo_ctx_id = str(uuid.uuid4())

            con.execute(
                "INSERT INTO trips (id, person_id, title, "
                "created_at, updated_at, meta_json) VALUES "
                "(?, ?, 'Orphan trip', '2026-07-23', "
                "'2026-07-23', '{}');",
                (trip_id, fake_person))
            con.execute(
                "INSERT INTO trip_regions (id, trip_id, ord, title) "
                "VALUES (?, ?, 0, 'Orphan region');",
                (region_id, trip_id))
            con.execute(
                "INSERT INTO trip_stops "
                "(id, trip_id, trip_region_id, ord, "
                " stop_type, location_name) "
                "VALUES (?, ?, ?, 0, 'sight', 'Orphan stop');",
                (stop_id, trip_id, region_id))
            con.execute(
                "INSERT INTO trip_days "
                "(id, trip_id, day_index, date, "
                " places_visited_json, meals_json, "
                " created_at, updated_at) VALUES "
                "(?, ?, 1, '2026-08-03', '[]', '[]', "
                "'2026-07-23', '2026-07-23');",
                (day_id, trip_id))
            con.execute(
                "INSERT INTO trip_location_notes "
                "(id, trip_id) VALUES (?, ?);",
                (note_id, trip_id))
            con.execute(
                "INSERT INTO trip_sources (id, trip_id, title, "
                "created_at, updated_at) VALUES "
                "(?, ?, 'orphan source', '2026-07-23', '2026-07-23');",
                (source_id, trip_id))
            con.execute(
                "INSERT INTO trip_themes (id, trip_id, ord, title, tag) "
                "VALUES (?, ?, 0, 'orphan theme', 'orphan');",
                (theme_id, trip_id))
            con.execute(
                "INSERT INTO trip_photo_links (id, trip_id, photo_id) "
                "VALUES (?, ?, 'fake-photo-id');",
                (photo_link_id, trip_id))
            con.execute(
                "INSERT INTO trip_bio_suggestions "
                "(id, trip_id, person_id, field_key, "
                " suggested_value) VALUES "
                "(?, ?, ?, 'placeOfBirth', 'Orphanville');",
                (bio_sugg_id, trip_id, fake_person))
            con.execute(
                "INSERT INTO trip_story_links "
                "(id, trip_id, story_candidate_id) VALUES "
                "(?, ?, 'fake-story-id');",
                (story_link_id, trip_id))
            con.execute(
                "INSERT INTO trip_public_context "
                "(id, trip_id, source_type, result_summary, "
                " created_at, updated_at) VALUES "
                "(?, ?, 'public_web_context', 'orphan summary', "
                "'2026-07-23', '2026-07-23');",
                (public_ctx_id, trip_id))
            con.execute(
                "INSERT INTO trip_photo_context "
                "(id, trip_id, photo_link_id, photo_id, "
                " context_type, result_summary, "
                " created_at, updated_at) VALUES "
                "(?, ?, ?, 'fake-photo-id', 'ocr_text', "
                "'orphan photo context', "
                "'2026-07-23', '2026-07-23');",
                (photo_ctx_id, trip_id, photo_link_id))
            con.commit()
        finally:
            con.close()
        return {
            "trip_id": trip_id,
            "region_id": region_id,
            "stop_id": stop_id,
            "day_id": day_id,
            "note_id": note_id,
            "source_id": source_id,
            "theme_id": theme_id,
            "photo_link_id": photo_link_id,
            "bio_sugg_id": bio_sugg_id,
            "story_link_id": story_link_id,
            "public_ctx_id": public_ctx_id,
            "photo_ctx_id": photo_ctx_id,
        }

    def test_0034_rev3_cascades_all_children_of_orphan_trip(self):
        """The critical regression test. Before rev 3, the orphan
        DELETE ran with FKs OFF so the declared ON DELETE CASCADE on
        every child table did NOT fire. Every seeded child row here
        must be gone after the migration."""
        ids = self._make_orphan_trip_with_children()

        # Re-run init_db → migrations apply
        _db._BIO_SEED_LOADED = False
        _db.init_db()

        con = sqlite3.connect(str(self.db_path))
        try:
            # Per-id survival check across every seeded child row
            table_id_pairs = (
                ("trips", "trip_id"),
                ("trip_regions", "region_id"),
                ("trip_stops", "stop_id"),
                ("trip_days", "day_id"),
                ("trip_location_notes", "note_id"),
                ("trip_sources", "source_id"),
                ("trip_themes", "theme_id"),
                ("trip_photo_links", "photo_link_id"),
                ("trip_bio_suggestions", "bio_sugg_id"),
                ("trip_story_links", "story_link_id"),
                ("trip_public_context", "public_ctx_id"),
                ("trip_photo_context", "photo_ctx_id"),
            )
            for table, id_key in table_id_pairs:
                row = con.execute(
                    f"SELECT 1 FROM {table} WHERE id = ?;",
                    (ids[id_key],)).fetchone()
                self.assertIsNone(
                    row,
                    f"{table} row for orphan trip should have been "
                    f"cascade-deleted by 0034 rev 3 (or swept by "
                    f"0035 as a safety net); still present")

            # Nested chain assertion: no row in any trip-child table
            # points at a trip_id that isn't in trips.
            for table in (
                "trip_regions", "trip_stops", "trip_days",
                "trip_location_notes", "trip_sources",
                "trip_photo_links", "trip_themes",
                "trip_bio_suggestions", "trip_story_links",
                "trip_public_context", "trip_photo_context",
            ):
                orphans = con.execute(
                    f"SELECT COUNT(*) FROM {table} "
                    "WHERE trip_id NOT IN (SELECT id FROM trips);"
                ).fetchone()[0]
                self.assertEqual(
                    orphans, 0,
                    f"{table} still has {orphans} row(s) pointing "
                    f"at a gone trip after migration")

            # Final gate: PRAGMA foreign_key_check must be zero rows
            # after the migration lands. ChatGPT's specific ask.
            con.execute("PRAGMA foreign_keys = ON;")
            violations = con.execute(
                "PRAGMA foreign_key_check;").fetchall()
            self.assertEqual(
                violations, [],
                f"PRAGMA foreign_key_check must return zero rows "
                f"after 0034+0035; got {violations!r}")
        finally:
            con.close()


class Migration0035SelfHealingTest(unittest.TestCase):
    """The specific MAG-Chris post-buggy-0034 case. Simulate a DB
    where 0034 ran with the buggy FKs-OFF DELETE (stranded children
    left behind), then bump init_db and let 0035 sweep them."""

    def setUp(self):
        self._tmpdb = tempfile.NamedTemporaryFile(
            suffix=".sqlite3", delete=False)
        self._tmpdb.close()
        self.db_path = Path(self._tmpdb.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()

    def tearDown(self):
        _db.DB_PATH = self._orig_db
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def test_0035_sweeps_children_of_previously_deleted_orphan_trip(self):
        """Insert child rows referencing a trip_id that isn't in
        trips (the MAG-Chris state), un-apply 0035, re-run init_db.
        The stranded children should be gone."""
        gone_trip_id = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        try:
            con.execute("PRAGMA foreign_keys = OFF;")
            # Directly plant stranded children — no parent trip exists
            con.execute(
                "INSERT INTO trip_regions (id, trip_id, ord, title) "
                "VALUES (?, ?, 0, 'Stranded');",
                (str(uuid.uuid4()), gone_trip_id))
            con.execute(
                "INSERT INTO trip_days "
                "(id, trip_id, day_index, date, "
                " places_visited_json, meals_json, "
                " created_at, updated_at) VALUES "
                "(?, ?, 1, '2026-08-03', '[]', '[]', "
                "'2026-07-23', '2026-07-23');",
                (str(uuid.uuid4()), gone_trip_id))
            con.execute(
                "INSERT INTO trip_location_notes (id, trip_id) VALUES "
                "(?, ?);", (str(uuid.uuid4()), gone_trip_id))
            # Un-apply 0035 so init_db will run it again
            con.execute(
                "DELETE FROM schema_migrations WHERE filename = "
                "'0035_trips_orphan_children_cleanup.sql';")
            con.commit()
        finally:
            con.close()

        # Confirm the stranded rows exist
        con = sqlite3.connect(str(self.db_path))
        try:
            n = con.execute(
                "SELECT COUNT(*) FROM trip_regions "
                "WHERE trip_id NOT IN (SELECT id FROM trips);"
            ).fetchone()[0]
            self.assertGreater(n, 0,
                               "test fixture failed to plant stranded rows")
        finally:
            con.close()

        # Re-run init_db → 0035 sweeps them
        _db._BIO_SEED_LOADED = False
        _db.init_db()

        con = sqlite3.connect(str(self.db_path))
        try:
            for table in (
                "trip_regions", "trip_days", "trip_location_notes",
            ):
                orphans = con.execute(
                    f"SELECT COUNT(*) FROM {table} "
                    "WHERE trip_id NOT IN (SELECT id FROM trips);"
                ).fetchone()[0]
                self.assertEqual(
                    orphans, 0,
                    f"{table} still has {orphans} stranded row(s) "
                    "after 0035 sweep")
        finally:
            con.close()

    def test_0035_is_noop_on_clean_db(self):
        """0035 must not disturb any legitimate row. Insert a real
        trip with children, un-apply 0035, re-run, assert everything
        survives."""
        # Make a real narrator + trip + children
        con = sqlite3.connect(str(self.db_path))
        try:
            person_id = str(uuid.uuid4())
            con.execute(
                "INSERT INTO people (id, display_name, date_of_birth, "
                "created_at, updated_at) VALUES "
                "(?, 'Chris', '1962-12-24', '2026-07-23', '2026-07-23');",
                (person_id,))
            trip_id = str(uuid.uuid4())
            con.execute(
                "INSERT INTO trips (id, person_id, title, "
                "created_at, updated_at, meta_json) VALUES "
                "(?, ?, 'Real trip', '2026-07-23', '2026-07-23', '{}');",
                (trip_id, person_id))
            region_id = str(uuid.uuid4())
            con.execute(
                "INSERT INTO trip_regions (id, trip_id, ord, title) "
                "VALUES (?, ?, 0, 'Real region');",
                (region_id, trip_id))
            con.execute(
                "DELETE FROM schema_migrations WHERE filename = "
                "'0035_trips_orphan_children_cleanup.sql';")
            con.commit()
        finally:
            con.close()

        _db._BIO_SEED_LOADED = False
        _db.init_db()

        con = sqlite3.connect(str(self.db_path))
        try:
            trip_row = con.execute(
                "SELECT id FROM trips WHERE id = ?;",
                (trip_id,)).fetchone()
            self.assertIsNotNone(
                trip_row, "real trip must survive 0035 sweep")
            region_row = con.execute(
                "SELECT id FROM trip_regions WHERE id = ?;",
                (region_id,)).fetchone()
            self.assertIsNotNone(
                region_row, "real region must survive 0035 sweep")
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
