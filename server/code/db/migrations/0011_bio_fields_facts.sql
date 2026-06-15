-- WO-LORI-BIO-BUILDER-UNIVERSAL-01 (2026-06-14)
--
-- Phase A: introduce the bio_fields schema definition table and the
-- bio_facts per-narrator value table. Together they form the universal
-- bio gap map foundation. Tiers 1-4 (extraction, document, anchored
-- asking, operator entry) all write to bio_facts; bio_fields is the
-- source of truth for which fields exist and what their authority
-- profile is.
--
-- LAW 3 INFRASTRUCTURE: This migration introduces two new tables.
-- It does NOT touch existing tables (family_truth_rows,
-- memory_archive_sessions, profiles, etc.). Bio facts are written in
-- PARALLEL to the existing family_truth_rows pipeline, not as a
-- replacement. The legacy review queue continues operating untouched.

BEGIN TRANSACTION;

-- ─────────────────────────────────────────────────────────────────────
-- bio_fields — schema definition (universal across narrators)
-- ─────────────────────────────────────────────────────────────────────
-- One row per canonical bio field. Seeded with ~80 universal entries
-- by the Python-side seed loader (bio_schema.py); operators may add
-- tenant-specific extensions in future WOs but v1 ships with the
-- universal seed only.
--
-- field_category enum (enforced by application; SQLite-free schema):
--   identity, family, education, work, military, geography,
--   relationships, milestones
--
-- field_type enum (enforced by application):
--   date, date_range, place, person, text, enum, integer
--
-- narrative_value enum (enforced by application):
--   high   — anchored-asking eligible (Tier 3 may surface in-session)
--   medium — extractor target, no in-session asking
--   low    — operator-entry only; never asked, never extractor-pushed
--
-- life_stage_range:
--   childhood, adult, all, military_only
--
-- asking_anchors is a JSON array of trigger patterns (lowercase
-- substring matches). Empty array = not eligible for anchored asking
-- regardless of narrative_value.
CREATE TABLE IF NOT EXISTS bio_fields (
    id                  TEXT PRIMARY KEY,
    field_key           TEXT NOT NULL UNIQUE,
    field_label         TEXT NOT NULL,
    field_category      TEXT NOT NULL,
    field_type          TEXT NOT NULL,
    narrative_value     TEXT NOT NULL DEFAULT 'medium',
    life_stage_range    TEXT NOT NULL DEFAULT 'all',
    asking_anchors      TEXT NOT NULL DEFAULT '[]',  -- JSON array
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bio_fields_category
    ON bio_fields(field_category);
CREATE INDEX IF NOT EXISTS idx_bio_fields_narrative_value
    ON bio_fields(narrative_value);

-- ─────────────────────────────────────────────────────────────────────
-- bio_facts — per-narrator filled values
-- ─────────────────────────────────────────────────────────────────────
-- Multiple rows per (narrator_id, field_key) are intentionally allowed
-- so conflicting sources persist as audit trail. status='conflicted'
-- marks rows that are awaiting operator resolution; conflict_with
-- links peer rows so the operator UI can surface them together.
--
-- status enum (enforced by application):
--   empty                     — placeholder; field has no row yet
--   extracted_needs_verify    — Tier 1 (extractor) wrote this
--   document_sourced          — Tier 2 (identity doc) auto-promoted
--   anchored_asked_pending    — Tier 3 ask fired; no value yet
--   anchored_asked            — Tier 3 ask fired; value extracted
--   operator_entered          — Tier 4 direct entry; immediately approved
--   approved                  — promoted to canonical truth
--   conflicted                — conflicts with peer row(s)
--   superseded                — operator chose a different row
--
-- value is stored as JSON to support typed values (dates, places,
-- enums) without per-type columns. Helpers in db.py + bio_schema.py
-- coerce on read.
--
-- source is a JSON object: {tier:1-4, session_id?, turn_id?, doc_id?,
-- operator_id?, timestamp}
--
-- chapter_continuation_metric is populated by Tier 3 (anchored asker)
-- to track Defense 1 creep telemetry. Empty/null for non-Tier-3 rows.
CREATE TABLE IF NOT EXISTS bio_facts (
    id                            TEXT PRIMARY KEY,
    tenant_id                     TEXT NOT NULL DEFAULT 'default',
    narrator_id                   TEXT NOT NULL,
    field_key                     TEXT NOT NULL,
    value                         TEXT NOT NULL DEFAULT '""',  -- JSON-encoded
    status                        TEXT NOT NULL DEFAULT 'empty',
    source                        TEXT NOT NULL DEFAULT '{}',  -- JSON
    confidence                    REAL NOT NULL DEFAULT 0.0,
    chapter_continuation_metric   TEXT,                        -- JSON; null OK
    conflict_with                 TEXT,                        -- bio_facts.id FK; null OK
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

COMMIT;
