"""WO-LORI-BIO-BUILDER-UNIVERSAL-01 (2026-06-14) — Phase C Tier 2 tests.

Covers acceptance gates #4 (identity documents auto-promote) and
#5 (non-identity documents propose, never auto-promote regardless
of confidence). Plus the document → narrator-memory conflict
resolution and the "narrator can correct the document" path
(approved/operator_entered rows hold against identity docs).
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
# Pure classifier tests (no DB)
# ─────────────────────────────────────────────────────────────────────


class IdentityDocumentTest(unittest.TestCase):
    def test_birth_certificate_is_identity(self):
        from api.services.document_authority import is_identity_document
        self.assertTrue(is_identity_document("birth_certificate"))

    def test_marriage_certificate_is_identity(self):
        from api.services.document_authority import is_identity_document
        self.assertTrue(is_identity_document("marriage_certificate"))

    def test_dd214_is_identity(self):
        from api.services.document_authority import is_identity_document
        # Both alias forms recognized
        self.assertTrue(is_identity_document("military_dd214"))
        self.assertTrue(is_identity_document("dd_214"))
        self.assertTrue(is_identity_document("dd214"))

    def test_diploma_not_identity(self):
        # Diploma is HIGH-confidence document_sourced (0.95) but
        # NOT in the identity class — distinct meaning.
        from api.services.document_authority import is_identity_document
        self.assertFalse(is_identity_document("diploma"))

    def test_letter_not_identity(self):
        from api.services.document_authority import is_identity_document
        self.assertFalse(is_identity_document("handwritten_letter"))

    def test_empty_doc_type_not_identity(self):
        from api.services.document_authority import is_identity_document
        self.assertFalse(is_identity_document(""))
        self.assertFalse(is_identity_document(None))


class ClassifyDocumentAuthorityTest(unittest.TestCase):
    def test_birth_certificate_auto_promotes(self):
        from api.services.document_authority import classify_document_authority
        status, conf = classify_document_authority("birth_certificate")
        self.assertEqual(status, "document_sourced")
        self.assertEqual(conf, 1.0)

    def test_diploma_high_confidence_document_sourced(self):
        from api.services.document_authority import classify_document_authority
        status, conf = classify_document_authority("diploma")
        self.assertEqual(status, "document_sourced")
        self.assertEqual(conf, 0.95)

    def test_prior_memoir_proposes(self):
        from api.services.document_authority import classify_document_authority
        status, conf = classify_document_authority("prior_memoir")
        self.assertEqual(status, "extracted_needs_verify")
        self.assertEqual(conf, 0.7)

    def test_handwritten_letter_low_confidence_proposes(self):
        from api.services.document_authority import classify_document_authority
        status, conf = classify_document_authority("handwritten_letter")
        self.assertEqual(status, "extracted_needs_verify")
        self.assertEqual(conf, 0.5)

    def test_photograph_proposes(self):
        from api.services.document_authority import classify_document_authority
        status, conf = classify_document_authority("photograph")
        self.assertEqual(status, "extracted_needs_verify")
        self.assertEqual(conf, 0.4)

    def test_unknown_defaults_safely(self):
        from api.services.document_authority import classify_document_authority
        for v in (None, "", "weird_unknown_type", "made_up"):
            with self.subTest(doc_type=v):
                status, conf = classify_document_authority(v)
                self.assertEqual(status, "extracted_needs_verify")
                self.assertLessEqual(conf, 0.30)


# ─────────────────────────────────────────────────────────────────────
# DB-backed routing tests
# ─────────────────────────────────────────────────────────────────────


def _setup_temp_bio_db():
    tmpdir = tempfile.mkdtemp(prefix="hornelore_test_doc_authority_")
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


class _DocDbBase(unittest.TestCase):
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


class DocumentRoutingBasicTest(_DocDbBase):
    def test_birth_certificate_writes_document_sourced(self):
        from api.services.document_authority import route_document_to_bio_facts
        from api import db
        facts = [{"fieldPath": "personal.dateOfBirth", "value": "1938"}]
        summary = route_document_to_bio_facts(
            facts, narrator_id="N1",
            doc_type="birth_certificate", doc_id="doc_001",
        )
        self.assertEqual(summary.document_sourced, 1)
        self.assertEqual(summary.proposed, 0)
        rows = db.bio_fact_list_by_field("N1", "birth_date")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "document_sourced")
        self.assertEqual(rows[0]["confidence"], 1.0)
        src = json.loads(rows[0]["source"])
        self.assertEqual(src["tier"], 2)
        self.assertEqual(src["doc_type"], "birth_certificate")
        self.assertEqual(src["doc_id"], "doc_001")

    def test_diploma_writes_document_sourced(self):
        from api.services.document_authority import route_document_to_bio_facts
        from api import db
        facts = [{
            "fieldPath": "education.college",
            "value": "Pasco High School",
        }]
        summary = route_document_to_bio_facts(
            facts, narrator_id="N1",
            doc_type="diploma", doc_id="doc_002",
        )
        # Diploma is high-confidence document_sourced (0.95) but
        # NOT identity-class. Status still document_sourced.
        self.assertEqual(summary.document_sourced, 1)
        rows = db.bio_fact_list_by_field("N1", "college_attended")
        self.assertEqual(rows[0]["confidence"], 0.95)

    def test_handwritten_letter_proposes_only(self):
        from api.services.document_authority import route_document_to_bio_facts
        from api import db
        facts = [{
            "fieldPath": "personal.placeOfBirth",
            "value": "Spokane",
        }]
        summary = route_document_to_bio_facts(
            facts, narrator_id="N1",
            doc_type="handwritten_letter", doc_id="doc_003",
        )
        # Even though confidence might be relatively low (0.5), this
        # is NEVER auto-promoted.
        self.assertEqual(summary.document_sourced, 0)
        self.assertEqual(summary.proposed, 1)
        rows = db.bio_fact_list_by_field("N1", "birth_place")
        self.assertEqual(rows[0]["status"], "extracted_needs_verify")
        self.assertEqual(rows[0]["confidence"], 0.5)

    def test_unmapped_path_counted_no_write(self):
        from api.services.document_authority import route_document_to_bio_facts
        from api import db
        facts = [{"fieldPath": "narrative.unknown", "value": "x"}]
        summary = route_document_to_bio_facts(
            facts, narrator_id="N1",
            doc_type="birth_certificate", doc_id="doc_004",
        )
        self.assertEqual(summary.unmapped, 1)
        self.assertEqual(db.bio_fact_list_by_narrator("N1"), [])


class IdentityDocConflictTest(_DocDbBase):
    def test_identity_doc_overrides_narrator_memory(self):
        """Birth certificate overrides extracted_needs_verify narrator
        memory by marking the memory row conflicted + linking back."""
        from api.services.document_authority import route_document_to_bio_facts
        from api import db
        # Narrator memory wrote 1938 from extraction
        memory_id = db.bio_fact_create(
            narrator_id="N1", field_key="birth_date",
            value_json=json.dumps("1938"),
            status="extracted_needs_verify", confidence=0.85,
        )
        # Identity doc says 1937
        summary = route_document_to_bio_facts(
            [{"fieldPath": "personal.dateOfBirth", "value": "1937"}],
            narrator_id="N1",
            doc_type="birth_certificate", doc_id="cert_001",
        )
        self.assertEqual(summary.document_sourced, 1)
        self.assertEqual(summary.overridden_narrator_memory, 1)
        # Now two rows exist; the original narrator memory is conflicted
        # and linked to the new document row.
        rows = db.bio_fact_list_by_field("N1", "birth_date")
        self.assertEqual(len(rows), 2)
        doc_row = next(
            r for r in rows if r["status"] == "document_sourced"
        )
        memory_row = next(
            r for r in rows if r["id"] == memory_id
        )
        self.assertEqual(memory_row["status"], "conflicted")
        self.assertEqual(memory_row["conflict_with"], doc_row["id"])

    def test_approved_row_holds_against_identity_doc(self):
        """If operator already approved a value, the identity doc
        does NOT supersede — it writes but the existing approved row
        stays approved (the narrator-correct-the-document path)."""
        from api.services.document_authority import route_document_to_bio_facts
        from api import db
        approved_id = db.bio_fact_create(
            narrator_id="N1", field_key="birth_date",
            value_json=json.dumps("1938"),
            status="approved", confidence=1.0,
        )
        summary = route_document_to_bio_facts(
            [{"fieldPath": "personal.dateOfBirth", "value": "1937"}],
            narrator_id="N1",
            doc_type="birth_certificate", doc_id="cert_001",
        )
        # Document row was still written + linked back via conflict_with
        self.assertEqual(summary.document_sourced, 1)
        rows = db.bio_fact_list_by_field("N1", "birth_date")
        self.assertEqual(len(rows), 2)
        doc_row = next(
            r for r in rows if r["status"] == "document_sourced"
        )
        # The doc row points at the approved row as its conflict
        self.assertEqual(doc_row["conflict_with"], approved_id)
        # But the approved row stays approved (operator override
        # of doc).
        approved_row = next(
            r for r in rows if r["id"] == approved_id
        )
        self.assertEqual(approved_row["status"], "approved")

    def test_letter_does_not_override_narrator_memory(self):
        """Non-identity docs propose; they should NOT mark narrator
        memory conflicted — both rows coexist as candidates."""
        from api.services.document_authority import route_document_to_bio_facts
        from api import db
        memory_id = db.bio_fact_create(
            narrator_id="N1", field_key="birth_date",
            value_json=json.dumps("1938"),
            status="extracted_needs_verify", confidence=0.85,
        )
        summary = route_document_to_bio_facts(
            [{"fieldPath": "personal.dateOfBirth", "value": "1937"}],
            narrator_id="N1",
            doc_type="handwritten_letter", doc_id="letter_001",
        )
        self.assertEqual(summary.proposed, 1)
        # Narrator memory row stays extracted_needs_verify, NOT
        # promoted to conflicted (the letter has no superseding
        # authority).
        memory_row = db.bio_fact_get(memory_id)
        self.assertEqual(memory_row["status"], "extracted_needs_verify")
        self.assertEqual(summary.overridden_narrator_memory, 0)


class RoutingEnabledFlagTest(unittest.TestCase):
    def test_default_off(self):
        from api.services.document_authority import routing_enabled
        os.environ.pop("HORNELORE_BIO_DOC_ROUTING", None)
        self.assertFalse(routing_enabled())

    def test_on_when_flag_set(self):
        from api.services.document_authority import routing_enabled
        os.environ["HORNELORE_BIO_DOC_ROUTING"] = "1"
        try:
            self.assertTrue(routing_enabled())
        finally:
            os.environ.pop("HORNELORE_BIO_DOC_ROUTING", None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
