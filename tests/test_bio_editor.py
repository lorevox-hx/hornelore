"""WO-LORI-BIO-BUILDER-UNIVERSAL-01 (2026-06-14) — Phase E editor tests.

Covers acceptance gate #9 (Tier 4 operator entry promotes to approved).
The router endpoints use FastAPI; tests exercise the underlying
behavior via the same db.py CRUD that the router calls. The router
itself is just a thin HTTP wrapper around bio_fact_create /
bio_fact_set_status / bio_fact_list_by_narrator — exercising those
through the editor's contracts validates the endpoint logic without
needing the FastAPI test client.
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


def _setup_temp_bio_db():
    tmpdir = tempfile.mkdtemp(prefix="hornelore_test_bio_editor_")
    db_path = os.path.join(tmpdir, "test.sqlite")
    conn = sqlite3.connect(db_path)
    try:
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


class _EditorDbBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from api import db
        cls._db_module = db
        cls._db_path, cls._tmpdir = _setup_temp_bio_db()
        cls._orig_connect = db._connect
        cls._orig_init_db = db.init_db

        def _patched_connect(path=None):
            conn = sqlite3.connect(cls._db_path)
            conn.row_factory = sqlite3.Row
            return conn

        db._connect = _patched_connect
        db.init_db = lambda: None
        db.bio_schema_seed_load_to_db()

    @classmethod
    def tearDownClass(cls):
        cls._db_module._connect = cls._orig_connect
        cls._db_module.init_db = cls._orig_init_db
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def setUp(self):
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("DELETE FROM bio_facts")
            conn.commit()
        finally:
            conn.close()


class DirectEntryTest(_EditorDbBase):
    """Direct operator entry — POST /enter behavior. Writes a row
    at status='approved' with tier=4 source attribution per WO §Tier 4."""

    def test_direct_entry_writes_approved(self):
        from api import db
        # Simulate what the router does
        new_id = db.bio_fact_create(
            narrator_id="N1", field_key="birth_date",
            value_json=json.dumps("1938-04-12"),
            status="approved",
            source_json=json.dumps({
                "tier": 4, "operator_id": "op_test",
                "timestamp": "2026-06-14T00:00:00Z",
            }),
            confidence=1.0,
        )
        row = db.bio_fact_get(new_id)
        self.assertEqual(row["status"], "approved")
        self.assertEqual(row["confidence"], 1.0)
        src = json.loads(row["source"])
        self.assertEqual(src["tier"], 4)
        self.assertEqual(src["operator_id"], "op_test")

    def test_direct_entry_notes_preserved(self):
        from api import db
        new_id = db.bio_fact_create(
            narrator_id="N1", field_key="father_name",
            value_json=json.dumps("Frank Horne"),
            status="approved",
            source_json=json.dumps({
                "tier": 4, "operator_id": "op_test",
                "notes": "from interview with cousin",
            }),
            confidence=1.0,
        )
        row = db.bio_fact_get(new_id)
        src = json.loads(row["source"])
        self.assertEqual(src["notes"], "from interview with cousin")


class ApproveExistingTest(_EditorDbBase):
    """POST /approve — promote an extracted_needs_verify or
    document_sourced row to approved while preserving source."""

    def test_approve_extracted_row(self):
        from api import db
        original_id = db.bio_fact_create(
            narrator_id="N1", field_key="birth_date",
            value_json=json.dumps("1938"),
            status="extracted_needs_verify",
            source_json=json.dumps({"tier": 1, "session_id": "s1"}),
            confidence=0.85,
        )
        # Approve
        ok = db.bio_fact_set_status(original_id, "approved")
        self.assertTrue(ok)
        row = db.bio_fact_get(original_id)
        self.assertEqual(row["status"], "approved")
        # Source attribution preserved
        src = json.loads(row["source"])
        self.assertEqual(src["tier"], 1)
        self.assertEqual(src["session_id"], "s1")


class ConflictResolutionTest(_EditorDbBase):
    """POST /resolve-conflict — promote one row to approved,
    mark peers as superseded with conflict_with linking preserved."""

    def test_resolve_promotes_and_supersedes(self):
        from api import db
        a = db.bio_fact_create(
            narrator_id="N1", field_key="birth_date",
            value_json=json.dumps("1938"),
            status="conflicted",
        )
        b = db.bio_fact_create(
            narrator_id="N1", field_key="birth_date",
            value_json=json.dumps("1937"),
            status="conflicted",
            conflict_with=a,
        )
        # Resolve: promote a, supersede b
        db.bio_fact_set_status(a, "approved")
        db.bio_fact_set_status(b, "superseded", conflict_with=a)
        a_row = db.bio_fact_get(a)
        b_row = db.bio_fact_get(b)
        self.assertEqual(a_row["status"], "approved")
        self.assertEqual(b_row["status"], "superseded")
        # Audit trail preserved
        self.assertEqual(b_row["conflict_with"], a)

    def test_resolve_does_not_touch_unrelated_field(self):
        """Conflict resolution on field A must not affect field B."""
        from api import db
        a = db.bio_fact_create(
            narrator_id="N1", field_key="birth_date",
            value_json=json.dumps("1938"),
            status="conflicted",
        )
        other = db.bio_fact_create(
            narrator_id="N1", field_key="father_name",
            value_json=json.dumps("Frank"),
            status="extracted_needs_verify",
        )
        # Resolve birth_date conflict
        db.bio_fact_set_status(a, "approved")
        other_row = db.bio_fact_get(other)
        self.assertEqual(
            other_row["status"], "extracted_needs_verify",
        )


class MarkUnanswerableTest(_EditorDbBase):
    """POST /mark-unanswerable — write a value=null row at approved
    status with source.unanswerable=true so the gap map stops
    surfacing the field but operator review can distinguish
    'no data' from 'known no data'."""

    def test_mark_unanswerable_writes_approved_null(self):
        from api import db
        new_id = db.bio_fact_create(
            narrator_id="N1", field_key="mother_maiden_name",
            value_json="null",
            status="approved",
            source_json=json.dumps({
                "tier": 4, "operator_id": "op_test",
                "unanswerable": True,
                "notes": "known-unanswerable",
            }),
            confidence=1.0,
        )
        row = db.bio_fact_get(new_id)
        self.assertEqual(row["status"], "approved")
        self.assertEqual(row["value"], "null")
        src = json.loads(row["source"])
        self.assertTrue(src.get("unanswerable"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
