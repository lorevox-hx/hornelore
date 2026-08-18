"""System-wide person-deletion coverage (WORK-AUDIT-2026-07-05 headline 3).

Verifies that hard_delete_person removes the extended person-scoped
tables that have NO FK to people (photos, story_candidates, bio_facts,
archives, safety events, trips + trip cascades) and that
person_delete_inventory counts them. Temp DB built via db.init_db()
(legacy tables + full migration chain), DB_PATH patched per test.
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


class _FullDbCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self._tmp.close()
        self.db_path = Path(self._tmp.name)
        self._original = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()
        self.person_id = str(uuid.uuid4())
        con = self._con()
        con.execute(
            "INSERT INTO people (id, display_name, created_at, updated_at) "
            "VALUES (?, 'Coverage Test', '2026-07-05', '2026-07-05');",
            (self.person_id,),
        )
        con.commit()
        con.close()

    def tearDown(self):
        _db.DB_PATH = self._original
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def _con(self):
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON;")
        return con

    def _seed(self):
        pid = self.person_id
        con = self._con()
        con.execute(
            "INSERT INTO photos (id, narrator_id, image_path, file_hash) "
            "VALUES ('ph-1', ?, '/tmp/x.jpg', 'h1');", (pid,),
        )
        con.execute(
            "INSERT INTO story_candidates (id, narrator_id, transcript, "
            "word_count, trigger_reason, created_at) "
            "VALUES ('sc-1', ?, 'a story', 2, 'full_threshold', '2026-07-05');",
            (pid,),
        )
        con.execute(
            "INSERT INTO trips (id, person_id, title, created_at, updated_at) "
            "VALUES ('tr-1', ?, 'Coverage Trip', '2026-07-05', '2026-07-05');",
            (pid,),
        )
        con.execute(
            "INSERT INTO trip_regions (id, trip_id, title, created_at, updated_at) "
            "VALUES ('re-1', 'tr-1', 'R1', '2026-07-05', '2026-07-05');",
        )
        con.execute(
            "INSERT INTO trip_stops (id, trip_id, trip_region_id, location_name, "
            "created_at, updated_at) "
            "VALUES ('st-1', 'tr-1', 're-1', 'Prague', '2026-07-05', '2026-07-05');",
        )
        con.execute(
            "INSERT INTO trip_photo_links (id, trip_id, photo_id, created_at, "
            "updated_at) VALUES ('li-1', 'tr-1', 'ph-1', '2026-07-05', '2026-07-05');",
        )
        # Phase 4 (2026-08-18): the extraction ledger. Added to the seed
        # rather than to a test of its own so it is covered by the SAME
        # deletion and residue assertions as every other person-scoped
        # table -- a table with its own bespoke test is a table the next
        # person can forget to add to the sweep.
        # `id` is INTEGER PRIMARY KEY AUTOINCREMENT here, unlike the uuid
        # text keys above, so it is deliberately not supplied.
        con.execute(
            "INSERT INTO turn_extraction_ledger "
            "(narrator_id, turn_key, outcome, created_at, updated_at) "
            "VALUES (?, 'turnrow:1', 'succeeded', '2026-08-18', '2026-08-18');",
            (self.person_id,),
        )
        con.commit()
        con.close()

    def _count(self, table, col):
        con = self._con()
        try:
            n = con.execute(
                f"SELECT COUNT(*) AS c FROM {table} WHERE {col}=?;",
                (self.person_id,),
            ).fetchone()["c"]
        finally:
            con.close()
        return n

    def test_inventory_counts_extended_tables(self):
        self._seed()
        inv = _db.person_delete_inventory(self.person_id)
        self.assertIsNotNone(inv)
        counts = inv["counts"]
        self.assertEqual(counts.get("photos"), 1)
        self.assertEqual(counts.get("story_candidates"), 1)
        self.assertEqual(counts.get("trips"), 1)

    def test_hard_delete_removes_extended_tables_and_cascades(self):
        self._seed()
        result = _db.hard_delete_person(self.person_id, requested_by="test")
        self.assertEqual(result.get("status"), "hard_deleted")
        self.assertEqual(self._count("photos", "narrator_id"), 0)
        self.assertEqual(self._count("story_candidates", "narrator_id"), 0)
        self.assertEqual(self._count("trips", "person_id"), 0)
        # Trip family cascades (no direct person column — count all rows).
        con = self._con()
        for table in ("trip_regions", "trip_stops", "trip_photo_links"):
            n = con.execute(f"SELECT COUNT(*) AS c FROM {table};").fetchone()["c"]
            self.assertEqual(n, 0, f"{table} not cascaded")
        # Audit trail SURVIVES the delete it records.
        n = con.execute(
            "SELECT COUNT(*) AS c FROM narrator_delete_audit WHERE person_id=?;",
            (self.person_id,),
        ).fetchone()["c"]
        con.close()
        self.assertGreaterEqual(n, 1)

    def test_the_extraction_ledger_is_inventoried_and_deleted(self):
        """WO-...-STORY-INTEGRATION-01 Phase 4, 2026-08-18.

        `turn_extraction_ledger` arrived with migration 0038 on 2026-07-30
        and was never added to the delete path's table list, so a
        hard-deleted narrator left ledger rows behind. The Phase 3 live
        acceptance found 2 orphans -- the only 2 in the table.

        Both halves are asserted, because they are separate promises: the
        operator must SEE the rows in the confirmation inventory before
        agreeing, and the delete must then remove them.
        """
        self._seed()
        inv = _db.person_delete_inventory(self.person_id)
        self.assertEqual(inv["counts"].get("turn_extraction_ledger"), 1,
                         "the ledger is missing from the delete inventory")
        _db.hard_delete_person(self.person_id, requested_by="test")
        self.assertEqual(self._count("turn_extraction_ledger", "narrator_id"), 0)

    def test_hard_delete_leaves_no_residue_in_any_scoped_table(self):
        """The sweep, rather than one assertion per table.

        Every entry in `_EXTENDED_PERSON_SCOPED_TABLES` is checked, so a
        table added to that list without deletion coverage fails here.
        This is the test that would have caught the ledger gap in July,
        and it is written as a loop for exactly that reason: the previous
        assertions named three tables by hand, and the one nobody named
        was the one that leaked.
        """
        self._seed()
        _db.hard_delete_person(self.person_id, requested_by="test")
        con = self._con()
        try:
            residue = {}
            for table, col in _db._EXTENDED_PERSON_SCOPED_TABLES:
                try:
                    n = con.execute(
                        f"SELECT COUNT(*) AS c FROM {table} WHERE {col}=?;",
                        (self.person_id,),
                    ).fetchone()["c"]
                except sqlite3.OperationalError:
                    continue        # table absent in this schema; guarded
                if n:
                    residue[f"{table}.{col}"] = n
        finally:
            con.close()
        self.assertEqual({}, residue,
                         "hard delete left person-scoped rows behind")

    def test_the_audit_row_is_not_swept_by_the_residue_rule(self):
        """The one table that MUST survive, so the sweep above can never
        be 'fixed' by deleting the record of the deletion."""
        self.assertNotIn(
            "narrator_delete_audit",
            [t for t, _ in _db._EXTENDED_PERSON_SCOPED_TABLES],
            "the audit trail must outlive the delete it records")

    def test_hard_delete_on_clean_person_still_works(self):
        result = _db.hard_delete_person(self.person_id, requested_by="test")
        self.assertEqual(result.get("status"), "hard_deleted")


if __name__ == "__main__":
    unittest.main()
