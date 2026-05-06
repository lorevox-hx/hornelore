-- WO-TIMELINE-CONTEXT-EVENTS-01 Phase A — timeline_context_events table.
--
-- Operator-curated cohort memory scaffolding. Holds historical context
-- packs filtered per narrator by region/heritage/cohort tags. Lori does
-- NOT write to this table — ever. Operator-only curation, narrator-
-- visible at render time when narrator_visible=1 AND deleted_at IS NULL.
--
-- Per CLAUDE.md design principle 8 ("Operator seeds known structure;
-- Lori reflects what is there") this is operator-seeded historical
-- scaffolding the renderer surfaces deterministically. No LLM call.
-- No web fetch. Stored, not retrieved.
--
-- LAW 3 [INFRASTRUCTURE]: schema-side enforcement. CHECK constraints
-- guarantee scope and source_kind enums. Validator (Phase B) enforces
-- tag vocabulary + citation discipline. The build-gate isolation test
-- enforces the no-Lori-import rule on the repository module.
--
-- See WO-TIMELINE-CONTEXT-EVENTS-01_Spec.md §"Schema (locked v1)" for
-- the full rationale per column.
--
-- Idempotent: CREATE TABLE IF NOT EXISTS so re-running migration is a
-- no-op. Migration runner tracks applied filenames in schema_migrations
-- so this file only executes once per fresh DB anyway.

BEGIN;

CREATE TABLE IF NOT EXISTS timeline_context_events (
    -- Identity
    id              TEXT PRIMARY KEY,                  -- stable slug, e.g. "nd_1957_prairie_drought"

    -- Render payload
    title           TEXT NOT NULL,                     -- short, render-friendly: "Prairie drought"
    summary         TEXT NOT NULL,                     -- 1-3 sentences: what happened and why it matters

    -- Temporal range — single-year events set year_start = year_end
    year_start      INTEGER,
    year_end        INTEGER,

    -- Scope: who sees this event when narrator filters apply
    --   global   = everyone (subject to time-range)
    --   national = everyone in same country (subject to time-range)
    --   regional = only narrators with overlapping region_tags
    --   local    = only narrators with overlapping region_tags (tighter geography)
    --   cultural = only narrators with overlapping heritage_tags
    scope           TEXT NOT NULL CHECK (scope IN (
                        'global',
                        'national',
                        'regional',
                        'local',
                        'cultural'
                    )),

    -- Tag arrays — JSON, validated against tag_vocabulary.json by Phase B
    region_tags     TEXT NOT NULL,                     -- JSON array: ["nd", "great_plains"]
    heritage_tags   TEXT NOT NULL,                     -- JSON array: ["germans_from_russia", "rural_us"]

    -- Provenance
    source_kind     TEXT NOT NULL CHECK (source_kind IN (
                        'local_oral_history',
                        'archived_newspaper',
                        'historical_society',
                        'academic',
                        'reference_work',
                        'web_resource',
                        'family_archive',
                        'operator_research_note'
                    )),
    source_citation TEXT NOT NULL,                     -- "general knowledge" fails the validator

    -- Visibility
    -- narrator_visible=0 ships for operator_research_note rows by default;
    -- promoted rows flip to 1 after operator review.
    narrator_visible INTEGER NOT NULL DEFAULT 1,

    -- Audit
    created_by      TEXT NOT NULL,                     -- operator user_id
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_by     TEXT,                              -- nullable; set on promote_research_note
    reviewed_at     TEXT,
    updated_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at      TEXT,                              -- soft-delete preserves audit trail

    notes           TEXT                               -- operator notes: "see also nd_1958_continued_drought"
);

-- Indexes match the renderer's query pattern:
--   WHERE deleted_at IS NULL
--     AND narrator_visible = 1
--     AND year_start <= narrator_lifetime_end
--     AND year_end   >= narrator_lifetime_start
-- Tag-overlap filtering happens in Python (JSON parse + intersection).
CREATE INDEX IF NOT EXISTS idx_tce_year_start  ON timeline_context_events(year_start);
CREATE INDEX IF NOT EXISTS idx_tce_year_end    ON timeline_context_events(year_end);
CREATE INDEX IF NOT EXISTS idx_tce_scope       ON timeline_context_events(scope);
CREATE INDEX IF NOT EXISTS idx_tce_deleted     ON timeline_context_events(deleted_at);
CREATE INDEX IF NOT EXISTS idx_tce_visible     ON timeline_context_events(narrator_visible, deleted_at);

COMMIT;
