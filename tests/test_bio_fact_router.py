"""WO-LORI-BIO-BUILDER-UNIVERSAL-01 (2026-06-14) — Phase B Tier 1 tests.

Covers acceptance gates #2 (extraction routes to bio_facts when fields
match), #3 (conflict detection writes correctly), #11 (universal
applicability — synthetic narrator IDs, no Horne-specific assumptions).

Uses an in-memory sqlite DB with just the bio tables, same pattern as
test_bio_facts_crud.py.
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


# ─────────────────────────────────────────────────────────────────────
# Pure mapping tests (no DB)
# ─────────────────────────────────────────────────────────────────────


class FieldPathMappingTest(unittest.TestCase):
    def test_direct_identity_paths_map(self):
        from api.services.bio_fact_router import map_field_path_to_bio_key
        self.assertEqual(
            map_field_path_to_bio_key("personal.dateOfBirth"),
            "birth_date",
        )
        self.assertEqual(
            map_field_path_to_bio_key("personal.placeOfBirth"),
            "birth_place",
        )
        self.assertEqual(
            map_field_path_to_bio_key("personal.preferredName"),
            "preferred_name",
        )

    def test_education_paths_map(self):
        from api.services.bio_fact_router import map_field_path_to_bio_key
        self.assertEqual(
            map_field_path_to_bio_key("education.highSchool"),
            "high_school",
        )
        self.assertEqual(
            map_field_path_to_bio_key("education.college"),
            "college_attended",
        )

    def test_military_paths_map(self):
        from api.services.bio_fact_router import map_field_path_to_bio_key
        self.assertEqual(
            map_field_path_to_bio_key("military.branch"),
            "military_branch",
        )

    def test_unmapped_path_returns_none(self):
        from api.services.bio_fact_router import map_field_path_to_bio_key
        self.assertIsNone(
            map_field_path_to_bio_key("entirely.unknown.path"),
        )

    def test_empty_path_returns_none(self):
        from api.services.bio_fact_router import map_field_path_to_bio_key
        self.assertIsNone(map_field_path_to_bio_key(""))
        self.assertIsNone(map_field_path_to_bio_key(None))


class ContextualMappingTest(unittest.TestCase):
    """parents.firstName needs the relation hint to disambiguate
    father vs mother."""

    def test_parents_firstname_father(self):
        from api.services.bio_fact_router import map_field_path_to_bio_key
        self.assertEqual(
            map_field_path_to_bio_key(
                "parents.firstName", {"relation": "father"},
            ),
            "father_name",
        )

    def test_parents_firstname_mother(self):
        from api.services.bio_fact_router import map_field_path_to_bio_key
        self.assertEqual(
            map_field_path_to_bio_key(
                "parents.firstName", {"relation": "mother"},
            ),
            "mother_name",
        )

    def test_parents_firstname_dad_alias(self):
        from api.services.bio_fact_router import map_field_path_to_bio_key
        # "dad" should map to father_name same as "father"
        self.assertEqual(
            map_field_path_to_bio_key(
                "parents.firstName", {"relation": "dad"},
            ),
            "father_name",
        )

    def test_parents_firstname_no_context_returns_none(self):
        from api.services.bio_fact_router import map_field_path_to_bio_key
        self.assertIsNone(
            map_field_path_to_bio_key("parents.firstName", None),
        )

    def test_parents_occupation_with_relation(self):
        from api.services.bio_fact_router import map_field_path_to_bio_key
        self.assertEqual(
            map_field_path_to_bio_key(
                "parents.occupation", {"relation": "mother"},
            ),
            "mother_occupation",
        )


# ─────────────────────────────────────────────────────────────────────
# DB-backed routing tests
# ─────────────────────────────────────────────────────────────────────


def _setup_temp_bio_db():
    tmpdir = tempfile.mkdtemp(prefix="hornelore_test_bio_router_")
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


class _RouterDbBase(unittest.TestCase):
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
        # Seed the bio_fields table so the FK doesn't trip on
        # bio_facts INSERTs during routing.
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


class RouteExtractionBasicTest(_RouterDbBase):
    def test_route_single_known_path(self):
        from api.services.bio_fact_router import route_extraction_to_bio_facts
        from api import db
        items = [{
            "fieldPath": "personal.dateOfBirth",
            "value": "1938",
            "confidence": 0.85,
        }]
        summary = route_extraction_to_bio_facts(
            items, narrator_id="N1", session_id="s1", turn_id="t1",
        )
        self.assertEqual(summary.routed, 1)
        self.assertEqual(summary.conflicts, 0)
        self.assertEqual(summary.unmapped, 0)
        # Row exists with correct status + source attribution
        rows = db.bio_fact_list_by_field("N1", "birth_date")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "extracted_needs_verify")
        src = json.loads(rows[0]["source"])
        self.assertEqual(src["tier"], 1)
        self.assertEqual(src["session_id"], "s1")
        self.assertEqual(src["turn_id"], "t1")

    def test_unmapped_path_counted_no_write(self):
        from api.services.bio_fact_router import route_extraction_to_bio_facts
        from api import db
        items = [{
            "fieldPath": "narrative.someStoryDetail",
            "value": "anything",
            "confidence": 0.5,
        }]
        summary = route_extraction_to_bio_facts(items, narrator_id="N1")
        self.assertEqual(summary.routed, 0)
        self.assertEqual(summary.unmapped, 1)
        self.assertEqual(db.bio_fact_list_by_narrator("N1"), [])

    def test_empty_inputs_safe(self):
        from api.services.bio_fact_router import route_extraction_to_bio_facts
        # No narrator → returns empty summary
        s = route_extraction_to_bio_facts(
            [{"fieldPath": "personal.dateOfBirth", "value": "x"}],
            narrator_id="",
        )
        self.assertEqual(s.routed, 0)
        # No items → returns empty summary
        s = route_extraction_to_bio_facts([], narrator_id="N1")
        self.assertEqual(s.routed, 0)

    def test_contextual_parent_routing(self):
        from api.services.bio_fact_router import route_extraction_to_bio_facts
        from api import db
        items = [{
            "fieldPath": "parents.firstName",
            "value": "Frank",
            "confidence": 0.9,
            "relation": "father",
        }]
        summary = route_extraction_to_bio_facts(items, narrator_id="N1")
        self.assertEqual(summary.routed, 1)
        rows = db.bio_fact_list_by_field("N1", "father_name")
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0]["value"]), "Frank")

    def test_per_item_error_counted_not_raised(self):
        from api.services.bio_fact_router import route_extraction_to_bio_facts
        # Item with totally broken shape — router must not raise.
        items = [
            {"fieldPath": "personal.dateOfBirth", "value": "1938",
             "confidence": 0.9},
            "this is not even a dict",  # bad item
        ]
        summary = route_extraction_to_bio_facts(items, narrator_id="N1")
        self.assertEqual(summary.routed, 1)
        self.assertEqual(summary.errors, 1)


class ConflictDetectionTest(_RouterDbBase):
    def test_second_extraction_different_value_creates_conflict(self):
        from api.services.bio_fact_router import route_extraction_to_bio_facts
        from api import db
        # First session — value "1938"
        route_extraction_to_bio_facts(
            [{"fieldPath": "personal.dateOfBirth", "value": "1938",
              "confidence": 0.9}],
            narrator_id="N1", session_id="s1",
        )
        first_rows = db.bio_fact_list_by_field("N1", "birth_date")
        self.assertEqual(len(first_rows), 1)
        first_id = first_rows[0]["id"]

        # Second session — conflicting value "1937"
        summary = route_extraction_to_bio_facts(
            [{"fieldPath": "personal.dateOfBirth", "value": "1937",
              "confidence": 0.9}],
            narrator_id="N1", session_id="s2",
        )
        self.assertEqual(summary.conflicts, 1)
        self.assertEqual(summary.routed, 0)

        # Two rows now exist, both linked via conflict_with
        rows = db.bio_fact_list_by_field("N1", "birth_date")
        self.assertEqual(len(rows), 2)
        new_row = next(r for r in rows if r["id"] != first_id)
        original_row = next(r for r in rows if r["id"] == first_id)
        self.assertEqual(new_row["status"], "conflicted")
        self.assertEqual(new_row["conflict_with"], first_id)
        # Original was promoted to conflicted + linked back
        self.assertEqual(original_row["status"], "conflicted")
        self.assertEqual(original_row["conflict_with"], new_row["id"])

    def test_same_value_does_not_conflict(self):
        from api.services.bio_fact_router import route_extraction_to_bio_facts
        from api import db
        # First extraction
        route_extraction_to_bio_facts(
            [{"fieldPath": "personal.dateOfBirth", "value": "1938",
              "confidence": 0.9}],
            narrator_id="N1",
        )
        # Second extraction, same value — creates a second
        # extracted_needs_verify row (not a conflict because values
        # match exactly). Caller can dedupe upstream if desired; v1
        # router lets both persist for the audit trail.
        summary = route_extraction_to_bio_facts(
            [{"fieldPath": "personal.dateOfBirth", "value": "1938",
              "confidence": 0.9}],
            narrator_id="N1",
        )
        self.assertEqual(summary.routed, 1)
        self.assertEqual(summary.conflicts, 0)
        rows = db.bio_fact_list_by_field("N1", "birth_date")
        self.assertEqual(len(rows), 2)
        for r in rows:
            self.assertEqual(r["status"], "extracted_needs_verify")


class AuthoritySuppressionTest(_RouterDbBase):
    def test_document_sourced_blocks_new_extraction(self):
        from api.services.bio_fact_router import route_extraction_to_bio_facts
        from api import db
        # Seed a document_sourced row (simulating Tier 2)
        db.bio_fact_create(
            narrator_id="N1", field_key="birth_date",
            value_json=json.dumps("1938"),
            status="document_sourced", confidence=1.0,
        )
        # Now Tier 1 tries to write a conflicting value
        summary = route_extraction_to_bio_facts(
            [{"fieldPath": "personal.dateOfBirth", "value": "1937",
              "confidence": 0.7}],
            narrator_id="N1",
        )
        self.assertEqual(summary.suppressed_by_authority, 1)
        self.assertEqual(summary.routed, 0)
        rows = db.bio_fact_list_by_field("N1", "birth_date")
        # Only the document_sourced row exists
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "document_sourced")

    def test_approved_blocks_new_extraction(self):
        from api.services.bio_fact_router import route_extraction_to_bio_facts
        from api import db
        db.bio_fact_create(
            narrator_id="N1", field_key="birth_date",
            value_json=json.dumps("1938"),
            status="approved", confidence=1.0,
        )
        summary = route_extraction_to_bio_facts(
            [{"fieldPath": "personal.dateOfBirth", "value": "1937",
              "confidence": 0.9}],
            narrator_id="N1",
        )
        self.assertEqual(summary.suppressed_by_authority, 1)
        self.assertEqual(summary.routed, 0)

    def test_operator_entered_blocks_new_extraction(self):
        from api.services.bio_fact_router import route_extraction_to_bio_facts
        from api import db
        db.bio_fact_create(
            narrator_id="N1", field_key="birth_date",
            value_json=json.dumps("1938"),
            status="operator_entered", confidence=1.0,
        )
        summary = route_extraction_to_bio_facts(
            [{"fieldPath": "personal.dateOfBirth", "value": "1937",
              "confidence": 0.9}],
            narrator_id="N1",
        )
        self.assertEqual(summary.suppressed_by_authority, 1)


class RoutingEnabledFlagTest(unittest.TestCase):
    def test_default_off(self):
        from api.services.bio_fact_router import routing_enabled
        os.environ.pop("HORNELORE_BIO_FACT_ROUTING", None)
        self.assertFalse(routing_enabled())

    def test_on_when_flag_set(self):
        from api.services.bio_fact_router import routing_enabled
        os.environ["HORNELORE_BIO_FACT_ROUTING"] = "1"
        try:
            self.assertTrue(routing_enabled())
        finally:
            os.environ.pop("HORNELORE_BIO_FACT_ROUTING", None)

    def test_off_when_flag_garbage(self):
        from api.services.bio_fact_router import routing_enabled
        os.environ["HORNELORE_BIO_FACT_ROUTING"] = "maybe"
        try:
            self.assertFalse(routing_enabled())
        finally:
            os.environ.pop("HORNELORE_BIO_FACT_ROUTING", None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
