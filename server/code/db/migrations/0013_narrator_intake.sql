-- WO-OPERATOR-NEW-NARRATOR-INTAKE-FORM-01 — Phase 1A schema additions.
--
-- Adds operator-side intake fields that Lori reads on every turn:
--   * people.pronouns        — enum string (she_her / he_him / they_them / other)
--   * people.pronouns_other  — free-text when pronouns='other'
--   * people.current_residence — anchors today-era + situational framing
--
-- Plus a new consent_attestations table so consent state has a proper
-- audit trail (timestamp + which operator checked the box) rather than
-- a single boolean column on people.
--
-- All ALTER TABLEs use the same SQLite-compatible idempotency check we use
-- elsewhere — if a prior schema-drift handler already added the column,
-- the migration silently no-ops via the IF NOT EXISTS guard built into
-- the migration runner.

BEGIN TRANSACTION;

-- people.pronouns
ALTER TABLE people ADD COLUMN pronouns TEXT DEFAULT '';

-- people.pronouns_other
ALTER TABLE people ADD COLUMN pronouns_other TEXT DEFAULT '';

-- people.current_residence
ALTER TABLE people ADD COLUMN current_residence TEXT DEFAULT '';

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
