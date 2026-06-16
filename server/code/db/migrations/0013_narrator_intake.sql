-- WO-OPERATOR-NEW-NARRATOR-INTAKE-FORM-01 — Phase 1A schema additions.
--
-- Creates the consent_attestations table for the new intake form, and
-- the associated indexes.
--
-- HISTORY NOTE (2026-06-15): An earlier version of this migration tried
-- to ALTER TABLE people ADD COLUMN pronouns / pronouns_other /
-- current_residence. SQLite doesn't support "ADD COLUMN IF NOT EXISTS",
-- so on every init_db retry (e.g. when one bad endpoint triggers a
-- re-init), the migration would re-run, fail with
-- "duplicate column name: pronouns", and never mark itself complete —
-- knocking out every endpoint that consulted the schema.
--
-- The fix is to let init_db's idempotent PRAGMA-guarded ALTER block in
-- db.py handle those three column adds (it checks pragma_table_info
-- before each ALTER, so re-runs are safe). This migration now only
-- creates the new table + indexes, which use IF NOT EXISTS guards that
-- are well-behaved across SQLite re-runs.

BEGIN TRANSACTION;

-- consent_attestations — one row per attestation event
CREATE TABLE IF NOT EXISTS consent_attestations (
    id TEXT PRIMARY KEY,
    narrator_id TEXT NOT NULL,
    attestation_type TEXT NOT NULL,
    -- 'recording_agreement' | 'disclosure_reviewed'
    attested_at TEXT NOT NULL,
    checked_by_operator TEXT DEFAULT '',
    -- Free-text operator identifier; lands as '' when the narrator
    -- ticked the box themselves with no operator-on-behalf attestation
    notes TEXT DEFAULT '',
    FOREIGN KEY (narrator_id) REFERENCES people(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_consent_attest_narrator
    ON consent_attestations(narrator_id);

CREATE INDEX IF NOT EXISTS idx_consent_attest_type
    ON consent_attestations(narrator_id, attestation_type);

COMMIT;
