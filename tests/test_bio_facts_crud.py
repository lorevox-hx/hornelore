"""WO-LORI-BIO-BUILDER-UNIVERSAL-01 (2026-06-14) — Phase A db.py CRUD tests.

Exercises bio_field_* + bio_fact_* accessors against an in-memory
sqlite file. Validates the conflict-as-audit-trail model (multiple
rows per narrator+field) and the seed-load path.

Follows the same in-memory-DB pattern as tests/test_thread_bank.py —
patches db._connect and db.init_db so the heavyweight production
init is skipped and the test fixture pre-builds only the bio_fields
+ bio_facts schema.
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
    """Build a temp sqlite with just the two bio tables + indexes."""
    tmpdir = tempfile.mkdtemp(prefix="hornelore_test_bio_crud_")
    db_path = os.path.join(tmpdir, "test.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS bio_fields (
                id                  TEXT PRIMARY KEY,
                field_key           TEXT NOT NULL UNIQUE,
                field_label         TEXT NOT NULL,
                field_category      TEXT NOT NULL,
                field_type          TEXT NOT NULL,
                narrative_value     TEXT NOT NULL DEFAULT 'medium',
                life_stage_range    TEXT NOT NULL DEFAULT 'all',
                asking_anchors      TEXT NOT NULL DEFAULT '[]',
                created_at          TEXT NOT NULL,
                updated_at          TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_bio_fields_category
                ON bio_fields(field_category);
            CREATE INDEX IF NOT EXISTS idx_bio_fields_narrative_value
                ON bio_fields(narrative_value);
            CREATE TABLE IF NOT EXISTS bio_facts (
                id                            TEXT PRIMARY KEY,
                tenant_id                     TEXT NOT NULL DEFAULT 'default',
                narrator_id                   TEXT NOT NULL,
                field_key                     TEXT NOT NULL,
                value                         TEXT NOT NULL DEFAULT '""',
                status                        TEXT NOT NULL DEFAULT 'empty',
                source                        TEXT NOT NULL DEFAULT '{}',
                confidence                    REAL NOT NULL DEFAULT 0.0,
                chapter_continuation_metric   TEXT,
                conflict_with                 TEXT,
                created_at                    TEXT NOT NULL,
                last_updated                  TEXT NOT NULL,
                FOREIGN KEY (field_key) REFERENCES bio_fields(field_key)
            );
            CREATE INDEX IF NOT EXISTS idx_bio_facts_narrator_field
                ON bio_facts(narrator_id, field_key);
            CREATE INDEX IF NOT EXISTS idx_bio_facts_narrator_status
                ON bio_facts(narrator_id, status);
            CREATE INDEX IF NOT EXISTS idx_bio_facts_status
                ON bio_facts(status);
        """)
        conn.commit()
    finally:
        conn.close()
    return db_path, tmpdir


class _BioDbBaseTest(unittest.TestCase):
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

        def _patched_init_db():
            return None

        db._connect = _patched_connect
        db.init_db = _patched_init_db

    @classmethod
    def tearDownClass(cls):
        cls._db_module._connect = cls._orig_connect
        cls._db_module.init_db = cls._orig_init_db
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def setUp(self):
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("DELETE FROM bio_facts")
            conn.execute("DELETE FROM bio_fields")
            conn.commit()
        finally:
            conn.close()


class BioFieldUpsertTest(_BioDbBaseTest):
    def test_insert_new_field(self):
        from api import db
        rid = db.bio_field_upsert(
            field_key="birth_date",
            field_label="Birth date",
            field_category="identity",
            field_type="date",
            narrative_value="high",
            asking_anchors_json=json.dumps(["born in"]),
        )
        self.assertTrue(rid)
        row = db.bio_field_get_by_key("birth_date")
        self.assertIsNotNone(row)
        self.assertEqual(row["field_label"], "Birth date")
        self.assertEqual(row["field_category"], "identity")
        self.assertEqual(row["narrative_value"], "high")
        self.assertEqual(json.loads(row["asking_anchors"]), ["born in"])

    def test_upsert_idempotent(self):
        from api import db
        rid1 = db.bio_field_upsert(
            field_key="birth_date",
            field_label="Birth date",
            field_category="identity",
            field_type="date",
        )
        rid2 = db.bio_field_upsert(
            field_key="birth_date",
            field_label="Date of birth (updated)",
            field_category="identity",
            field_type="date",
        )
        # Same row id reused; label updated.
        self.assertEqual(rid1, rid2)
        self.assertEqual(
            db.bio_field_get_by_key("birth_date")["field_label"],
            "Date of birth (updated)",
        )

    def test_get_by_unknown_returns_none(self):
        from api import db
        self.assertIsNone(db.bio_field_get_by_key("nope"))


class BioFieldListTest(_BioDbBaseTest):
    def _seed_three(self):
        from api import db
        db.bio_field_upsert(
            field_key="birth_date",
            field_label="Birth date",
            field_category="identity",
            field_type="date",
            narrative_value="high",
        )
        db.bio_field_upsert(
            field_key="middle_name",
            field_label="Middle name",
            field_category="identity",
            field_type="text",
            narrative_value="low",
        )
        db.bio_field_upsert(
            field_key="father_name",
            field_label="Father's name",
            field_category="family",
            field_type="person",
            narrative_value="high",
        )

    def test_list_all(self):
        from api import db
        self._seed_three()
        rows = db.bio_field_list()
        self.assertEqual(len(rows), 3)

    def test_list_filter_by_category(self):
        from api import db
        self._seed_three()
        identity = db.bio_field_list(category="identity")
        self.assertEqual(len(identity), 2)
        for r in identity:
            self.assertEqual(r["field_category"], "identity")

    def test_list_filter_by_narrative_value(self):
        from api import db
        self._seed_three()
        high = db.bio_field_list(narrative_value="high")
        self.assertEqual(len(high), 2)
        for r in high:
            self.assertEqual(r["narrative_value"], "high")

    def test_field_count(self):
        from api import db
        self.assertEqual(db.bio_field_count(), 0)
        self._seed_three()
        self.assertEqual(db.bio_field_count(), 3)


class BioFactCreateTest(_BioDbBaseTest):
    def _seed_field(self):
        from api import db
        db.bio_field_upsert(
            field_key="birth_date",
            field_label="Birth date",
            field_category="identity",
            field_type="date",
        )

    def test_create_basic_fact(self):
        from api import db
        self._seed_field()
        fid = db.bio_fact_create(
            narrator_id="N1",
            field_key="birth_date",
            value_json=json.dumps("1938"),
            status="extracted_needs_verify",
            source_json=json.dumps({"tier": 1, "session_id": "s1"}),
            confidence=0.7,
        )
        self.assertTrue(fid)
        fact = db.bio_fact_get(fid)
        self.assertEqual(fact["narrator_id"], "N1")
        self.assertEqual(fact["field_key"], "birth_date")
        self.assertEqual(json.loads(fact["value"]), "1938")
        self.assertEqual(fact["status"], "extracted_needs_verify")
        self.assertEqual(fact["confidence"], 0.7)

    def test_create_allows_duplicate_narrator_field_pair(self):
        # The conflict-as-audit-trail model — multiple rows allowed,
        # caller links via conflict_with.
        from api import db
        self._seed_field()
        a = db.bio_fact_create(
            narrator_id="N1",
            field_key="birth_date",
            value_json=json.dumps("1938"),
            status="extracted_needs_verify",
        )
        b = db.bio_fact_create(
            narrator_id="N1",
            field_key="birth_date",
            value_json=json.dumps("1937"),
            status="conflicted",
            conflict_with=a,
        )
        rows = db.bio_fact_list_by_field("N1", "birth_date")
        self.assertEqual(len(rows), 2)
        # Conflict linking persisted
        b_row = db.bio_fact_get(b)
        self.assertEqual(b_row["conflict_with"], a)


class BioFactQueryTest(_BioDbBaseTest):
    def _seed_two_narrators(self):
        from api import db
        db.bio_field_upsert(
            field_key="birth_date", field_label="Birth date",
            field_category="identity", field_type="date",
        )
        db.bio_field_upsert(
            field_key="father_name", field_label="Father",
            field_category="family", field_type="person",
        )
        db.bio_fact_create(
            narrator_id="N1", field_key="birth_date",
            value_json=json.dumps("1938"),
            status="extracted_needs_verify",
        )
        db.bio_fact_create(
            narrator_id="N1", field_key="father_name",
            value_json=json.dumps("Frank"),
            status="approved",
        )
        db.bio_fact_create(
            narrator_id="N2", field_key="birth_date",
            value_json=json.dumps("1945"),
            status="document_sourced", confidence=1.0,
        )

    def test_list_by_narrator(self):
        from api import db
        self._seed_two_narrators()
        n1 = db.bio_fact_list_by_narrator("N1")
        self.assertEqual(len(n1), 2)
        for r in n1:
            self.assertEqual(r["narrator_id"], "N1")

    def test_list_by_narrator_filter_status(self):
        from api import db
        self._seed_two_narrators()
        approved = db.bio_fact_list_by_narrator("N1", status="approved")
        self.assertEqual(len(approved), 1)
        self.assertEqual(approved[0]["field_key"], "father_name")

    def test_narrator_isolation(self):
        # N1 facts must not show up under N2 query.
        from api import db
        self._seed_two_narrators()
        n2 = db.bio_fact_list_by_narrator("N2")
        self.assertEqual(len(n2), 1)
        self.assertEqual(n2[0]["narrator_id"], "N2")


class BioFactStatusTransitionTest(_BioDbBaseTest):
    def _seed_one(self):
        from api import db
        db.bio_field_upsert(
            field_key="birth_date", field_label="Birth date",
            field_category="identity", field_type="date",
        )
        return db.bio_fact_create(
            narrator_id="N1", field_key="birth_date",
            value_json=json.dumps("1938"),
            status="extracted_needs_verify",
        )

    def test_set_status_updates_row(self):
        from api import db
        fid = self._seed_one()
        ok = db.bio_fact_set_status(fid, "approved")
        self.assertTrue(ok)
        self.assertEqual(db.bio_fact_get(fid)["status"], "approved")

    def test_set_status_with_conflict_with(self):
        from api import db
        fid = self._seed_one()
        ok = db.bio_fact_set_status(
            fid, "conflicted", conflict_with="some_other_id",
        )
        self.assertTrue(ok)
        row = db.bio_fact_get(fid)
        self.assertEqual(row["status"], "conflicted")
        self.assertEqual(row["conflict_with"], "some_other_id")

    def test_set_status_unknown_id_returns_false(self):
        from api import db
        self.assertFalse(db.bio_fact_set_status("nope_id", "approved"))


class BioSeedLoadTest(_BioDbBaseTest):
    def test_seed_load_writes_all_fields(self):
        from api import db
        from api.services.bio_schema import BIO_SCHEMA_SEED
        n = db.bio_schema_seed_load_to_db()
        self.assertEqual(n, len(BIO_SCHEMA_SEED))
        self.assertEqual(db.bio_field_count(), len(BIO_SCHEMA_SEED))

    def test_seed_load_idempotent(self):
        from api import db
        from api.services.bio_schema import BIO_SCHEMA_SEED
        db.bio_schema_seed_load_to_db()
        first = db.bio_field_count()
        db.bio_schema_seed_load_to_db()  # second call
        second = db.bio_field_count()
        self.assertEqual(first, second)
        self.assertEqual(second, len(BIO_SCHEMA_SEED))


if __name__ == "__main__":
    unittest.main(verbosity=2)
