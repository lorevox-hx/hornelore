"""WO-OPERATOR-NEW-NARRATOR-INTAKE-FORM-01 — Phase 1 backend tests.

Covers:
  - consent_attestation_create CRUD + enum validation
  - consent_attestation_list_for_narrator filtering + sort
  - consent_attestation_has_complete_set boolean rollup
  - PersonCreate Pydantic source contract — confirms the new fields
    (pronouns, current_residence, consent flags) are part of the
    payload schema
  - POST /api/people validation contract via source-inspection of
    the route handler (validates the consent + pronoun gates fire
    BEFORE create_person is called)

Uses the same in-memory sqlite pattern as other bio + narrator tests —
patches db._connect to a temp file and neuters init_db so the
heavyweight production schema chain stays out of the way.
"""
from __future__ import annotations

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


def _setup_temp_intake_db():
    """Build a temp sqlite with people + consent_attestations only."""
    tmpdir = tempfile.mkdtemp(prefix="hornelore_test_intake_")
    db_path = os.path.join(tmpdir, "test.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS people (
                id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                role TEXT DEFAULT '',
                date_of_birth TEXT DEFAULT '',
                place_of_birth TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                narrator_type TEXT DEFAULT 'live',
                pronouns TEXT DEFAULT '',
                pronouns_other TEXT DEFAULT '',
                current_residence TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS consent_attestations (
                id TEXT PRIMARY KEY,
                narrator_id TEXT NOT NULL,
                attestation_type TEXT NOT NULL,
                attested_at TEXT NOT NULL,
                checked_by_operator TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                FOREIGN KEY (narrator_id) REFERENCES people(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_consent_attest_narrator
                ON consent_attestations(narrator_id);
            CREATE INDEX IF NOT EXISTS idx_consent_attest_type
                ON consent_attestations(narrator_id, attestation_type);
        """)
        conn.commit()
    finally:
        conn.close()
    return db_path, tmpdir


class _IntakeDbBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from api import db
        cls._db_module = db
        cls._db_path, cls._tmpdir = _setup_temp_intake_db()
        cls._orig_connect = db._connect
        cls._orig_init_db = db.init_db

        def _patched_connect(path=None):
            conn = sqlite3.connect(cls._db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON;")
            return conn

        db._connect = _patched_connect
        db.init_db = lambda: None

    @classmethod
    def tearDownClass(cls):
        cls._db_module._connect = cls._orig_connect
        cls._db_module.init_db = cls._orig_init_db
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def setUp(self):
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("DELETE FROM consent_attestations")
            conn.execute("DELETE FROM people")
            # Seed a narrator we can attach attestations to
            conn.execute(
                "INSERT INTO people (id, display_name, role, "
                "created_at, updated_at) VALUES "
                "('N_test', 'Test Narrator', '', "
                "'2026-06-15T00:00:00Z', '2026-06-15T00:00:00Z');"
            )
            conn.commit()
        finally:
            conn.close()


class ConsentAttestationCreateTest(_IntakeDbBase):
    def test_create_recording_agreement(self):
        from api import db
        new_id = db.consent_attestation_create(
            narrator_id="N_test",
            attestation_type="recording_agreement",
        )
        self.assertTrue(new_id)

    def test_create_disclosure_reviewed(self):
        from api import db
        new_id = db.consent_attestation_create(
            narrator_id="N_test",
            attestation_type="disclosure_reviewed",
            checked_by_operator="op_alice",
            notes="checked on narrator's behalf — narrator has tremor",
        )
        self.assertTrue(new_id)
        rows = db.consent_attestation_list_for_narrator("N_test")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["checked_by_operator"], "op_alice")
        self.assertEqual(row["notes"],
                         "checked on narrator's behalf — narrator has tremor")

    def test_unknown_attestation_type_raises(self):
        from api import db
        with self.assertRaises(ValueError):
            db.consent_attestation_create(
                narrator_id="N_test",
                attestation_type="not_a_real_type",
            )

    def test_fk_violation_unknown_narrator(self):
        # FK enforcement is on — INSERT against a non-existent
        # narrator_id should fail.
        from api import db
        with self.assertRaises(sqlite3.IntegrityError):
            db.consent_attestation_create(
                narrator_id="NEVER_EXISTED",
                attestation_type="recording_agreement",
            )


class ConsentAttestationListTest(_IntakeDbBase):
    def _create_both(self):
        from api import db
        db.consent_attestation_create(
            narrator_id="N_test",
            attestation_type="recording_agreement",
        )
        db.consent_attestation_create(
            narrator_id="N_test",
            attestation_type="disclosure_reviewed",
        )

    def test_list_all_for_narrator(self):
        from api import db
        self._create_both()
        rows = db.consent_attestation_list_for_narrator("N_test")
        self.assertEqual(len(rows), 2)
        types = {r["attestation_type"] for r in rows}
        self.assertEqual(types, {"recording_agreement", "disclosure_reviewed"})

    def test_list_filter_by_type(self):
        from api import db
        self._create_both()
        rec = db.consent_attestation_list_for_narrator(
            "N_test", attestation_type="recording_agreement",
        )
        self.assertEqual(len(rec), 1)
        self.assertEqual(rec[0]["attestation_type"], "recording_agreement")

    def test_unknown_narrator_returns_empty(self):
        from api import db
        rows = db.consent_attestation_list_for_narrator("nope_id")
        self.assertEqual(rows, [])


class HasCompleteSetTest(_IntakeDbBase):
    def test_no_attestations_incomplete(self):
        from api import db
        self.assertFalse(db.consent_attestation_has_complete_set("N_test"))

    def test_only_one_type_incomplete(self):
        from api import db
        db.consent_attestation_create(
            narrator_id="N_test",
            attestation_type="recording_agreement",
        )
        self.assertFalse(db.consent_attestation_has_complete_set("N_test"))

    def test_both_types_complete(self):
        from api import db
        db.consent_attestation_create(
            narrator_id="N_test",
            attestation_type="recording_agreement",
        )
        db.consent_attestation_create(
            narrator_id="N_test",
            attestation_type="disclosure_reviewed",
        )
        self.assertTrue(db.consent_attestation_has_complete_set("N_test"))


# ─────────────────────────────────────────────────────────────────────
# Source-inspection contract checks — these don't need DB at all
# ─────────────────────────────────────────────────────────────────────


class PersonCreateModelSourceTest(unittest.TestCase):
    """The new identity + consent fields must be present on the
    PersonCreate Pydantic model. Source-inspect rather than import,
    because the router pulls in FastAPI which isn't available in
    every test sandbox."""

    def test_pronouns_field_declared(self):
        src = (_SERVER_CODE / "api" / "routers" / "people.py").read_text(encoding="utf-8")
        self.assertIn("pronouns: Optional[str]", src)
        self.assertIn("pronouns_other: Optional[str]", src)

    def test_current_residence_field_declared(self):
        src = (_SERVER_CODE / "api" / "routers" / "people.py").read_text(encoding="utf-8")
        self.assertIn("current_residence: Optional[str]", src)

    def test_consent_fields_declared(self):
        src = (_SERVER_CODE / "api" / "routers" / "people.py").read_text(encoding="utf-8")
        self.assertIn("consent_recording_agreement: Optional[bool]", src)
        self.assertIn("consent_disclosure_reviewed: Optional[bool]", src)
        self.assertIn("consent_checked_by_operator: Optional[str]", src)

    def test_testing_only_field_declared(self):
        src = (_SERVER_CODE / "api" / "routers" / "people.py").read_text(encoding="utf-8")
        self.assertIn("testing_only: Optional[bool]", src)


class RouteValidationSourceTest(unittest.TestCase):
    """POST /api/people must validate pronoun enum + consent
    gating BEFORE calling create_person. Source-inspection contract
    keeps the order honest if anyone refactors the route."""

    def setUp(self):
        self.src = (
            _SERVER_CODE / "api" / "routers" / "people.py"
        ).read_text(encoding="utf-8")

    def test_pronoun_enum_validated_before_create_person(self):
        # The pronoun enum check must appear textually before
        # the create_person(...) call inside api_create_person.
        body_start = self.src.find("def api_create_person")
        self.assertGreater(body_start, 0)
        body = self.src[body_start:body_start + 4000]
        pron_check_idx = body.find("_PRONOUN_CHOICES")
        create_idx = body.find("person = create_person(")
        self.assertGreater(pron_check_idx, 0,
                           msg="pronoun enum check missing from route")
        self.assertGreater(create_idx, 0,
                           msg="create_person call missing from route")
        self.assertLess(
            pron_check_idx, create_idx,
            msg=(
                "pronoun validation must run BEFORE create_person; "
                "otherwise an invalid pronoun writes a malformed people "
                "row before we reject it"
            ),
        )

    def test_consent_gate_validated_before_create_person(self):
        body_start = self.src.find("def api_create_person")
        body = self.src[body_start:body_start + 4000]
        consent_check_idx = body.find("consent_recording_agreement must be true")
        create_idx = body.find("person = create_person(")
        self.assertGreater(consent_check_idx, 0)
        self.assertGreater(create_idx, 0)
        self.assertLess(
            consent_check_idx, create_idx,
            msg=(
                "consent gate must run BEFORE create_person; "
                "otherwise a no-consent narrator gets persisted"
            ),
        )

    def test_testing_only_bypasses_consent(self):
        body_start = self.src.find("def api_create_person")
        body = self.src[body_start:body_start + 4000]
        # The testing-only path must explicitly bypass the consent
        # gate. The string "not is_testing" should appear before
        # the consent_recording_agreement check.
        not_testing_idx = body.find("if not is_testing")
        rec_check_idx = body.find("consent_recording_agreement must be true")
        self.assertGreater(not_testing_idx, 0)
        self.assertLess(not_testing_idx, rec_check_idx)


class InitDbSchemaSourceTest(unittest.TestCase):
    """init_db must carry the consent_attestations CREATE TABLE +
    the idempotent people-column ALTER block."""

    def setUp(self):
        self.src = (_SERVER_CODE / "api" / "db.py").read_text(encoding="utf-8")

    def test_consent_attestations_table_in_init_db(self):
        self.assertIn(
            "CREATE TABLE IF NOT EXISTS consent_attestations",
            self.src,
        )

    def test_people_column_add_block_present(self):
        # The idempotent ALTER block adds pronouns / pronouns_other /
        # current_residence to people. Each column name must appear
        # in the ALTER block.
        for col in ("pronouns", "pronouns_other", "current_residence"):
            with self.subTest(column=col):
                self.assertIn(
                    f'("{col}", "TEXT DEFAULT \'\'")',
                    self.src,
                )

    def test_consent_indexes_present(self):
        for idx in (
            "idx_consent_attest_narrator",
            "idx_consent_attest_type",
        ):
            with self.subTest(index=idx):
                self.assertIn(idx, self.src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
