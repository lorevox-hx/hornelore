------------------------------------------------------------
-- 0037_import_provenance_foundation.sql
-- WO-TRAVEL-DOC-IMPORT-PROVENANCE-FOUNDATION-01 Phase 2 (2026-07-26)
--
-- Two jobs, in this order:
--
--   A. FK HARDENING. Close the two missing constraints that let a
--      photo belong to a person id that does not exist, and let a
--      trip link point at a photo that does not exist:
--
--          photos.narrator_id      -> people(id) ON DELETE CASCADE
--          trip_photo_links.photo_id -> photos(id) ON DELETE CASCADE
--
--      These are the exact two gaps the Phase 0/1 identity pre-flight
--      found. photos.narrator_id has been TEXT NOT NULL with no
--      REFERENCES since 0001_lori_photo_shared.sql, while
--      trips.person_id got a real FK in 0034. The same human was
--      addressable two ways with no schema opinion about it, and
--      _photos_for_narrator() returns an EMPTY LIST rather than an
--      error when the id is wrong -- a silent wrong answer.
--
--   B. THE IMPORT LANDING ZONE. Create import_batch and
--      import_candidate so external photo sources (Google Photos
--      Picker, Takeout, local upload) have somewhere to land that is
--      NOT the photos table.
--
-- ============================================================
--   INTAKE IS NOT APPROVAL
-- ============================================================
--
-- import_candidate deliberately has NO narrator_ready column and NO
-- include_in_memoir column. That absence is the enforcement, not an
-- oversight: there is no way to express "this candidate is ready for
-- the narrator" or "this candidate is in the memoir", because a
-- candidate is neither. Those states live on photos and
-- trip_photo_links, and a candidate only reaches them by an explicit
-- operator acceptance that materializes a photos row.
--
--   * creating a candidate does not mean narrator-ready
--   * creating a candidate does not mean memoir inclusion
--   * creating a candidate does not mean the operator has seen it
--
-- ============================================================
--   NO RAW TOKENS
-- ============================================================
--
-- Neither table has a column for an OAuth token, refresh token,
-- access token, cookie, or authorization header. external_ref /
-- external_id hold opaque provider-side identifiers ONLY. Anything
-- that could be replayed to a third-party API belongs in the process
-- environment, never in the database.
--
-- ============================================================
--   REVERSIBLE, NOT DESTRUCTIVE
-- ============================================================
--
-- Both tables carry the hidden / hidden_at pair established for the
-- trip evidence lanes in 0036. Retiring a batch or a candidate is a
-- stamp, not a DELETE, and clearing hidden restores the row with its
-- match reasons and review history intact.
--
-- ============================================================
--   MIGRATION SHAPE
-- ============================================================
--
-- Part A follows the 0034_trips_person_id_fk.sql precedent exactly,
-- because 0034 rev-1 shipped a real bug that this shape avoids:
--
--   * PRAGMA foreign_keys is a NO-OP inside a transaction. Every
--     PRAGMA below is therefore OUTSIDE any BEGIN/COMMIT.
--   * The orphan cleanup runs with foreign_keys ON so the cascades
--     actually fire. 0034 rev-1 did the DELETE with FKs OFF, the
--     cascades did not fire, and it left the children behind.
--   * The table rebuild runs with foreign_keys OFF so the DROP +
--     RENAME is not blocked by child tables that reference it.
--   * FKs are re-armed and PRAGMA foreign_key_check runs at the end.
--
-- On the live database as surveyed 2026-07-26 the orphan counts in
-- Part A are all zero, so Part A is a pure schema tightening there.
-- The DELETEs exist so the migration is correct on any machine.
------------------------------------------------------------


------------------------------------------------------------
-- PART A1 -- orphan cleanup, WITH FOREIGN KEYS ON
--
-- Order matters. Orphan photos go first; that cascades their
-- photo_people / photo_events / photo_memories / photo_session_shows
-- children, which in turn strands their trip_photo_links and
-- trip_photo_context rows, which the next two statements sweep. Doing
-- it the other way round would leave the links behind.
------------------------------------------------------------

PRAGMA foreign_keys = ON;

BEGIN IMMEDIATE;

DELETE FROM photos
 WHERE NOT EXISTS (SELECT 1 FROM people WHERE people.id = photos.narrator_id);

DELETE FROM trip_photo_links
 WHERE NOT EXISTS (SELECT 1 FROM photos WHERE photos.id = trip_photo_links.photo_id);

-- trip_photo_context.photo_id gets no FK in this migration (it is not
-- in the Phase 2 scope), but the statement above and the photo delete
-- can strand rows here, and a migration must not leave garbage it
-- created itself.
DELETE FROM trip_photo_context
 WHERE NOT EXISTS (SELECT 1 FROM photos WHERE photos.id = trip_photo_context.photo_id);

COMMIT;


------------------------------------------------------------
-- PART A2 -- rebuild photos with the people FK
--
-- Column list is copied verbatim from the live schema, including the
-- columns appended later by ALTER TABLE (metadata_trust, date_source,
-- taken_at_filename_guess, date_approved_for_lori,
-- location_approved_for_lori). The only change is the REFERENCES
-- clause on narrator_id.
------------------------------------------------------------

PRAGMA foreign_keys = OFF;

BEGIN IMMEDIATE;

CREATE TABLE photos_new (
    id TEXT PRIMARY KEY,
    narrator_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,

    image_path TEXT NOT NULL,
    thumbnail_path TEXT,
    media_url TEXT,
    thumbnail_url TEXT,

    file_hash TEXT NOT NULL UNIQUE,

    description TEXT,

    date_value TEXT,
    date_precision TEXT NOT NULL DEFAULT 'unknown'
        CHECK (date_precision IN ('exact', 'month', 'year', 'decade', 'unknown')),

    location_label TEXT,
    location_source TEXT NOT NULL DEFAULT 'unknown'
        CHECK (location_source IN (
            'exif_gps',
            'typed_address',
            'spoken_place',
            'description_geocode',
            'unknown'
        )),

    latitude REAL,
    longitude REAL,

    narrator_ready INTEGER NOT NULL DEFAULT 0,
    needs_confirmation INTEGER NOT NULL DEFAULT 1,

    uploaded_by_user_id TEXT,
    uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_edited_by_user_id TEXT,
    last_edited_at TEXT,
    deleted_at TEXT,

    metadata_json TEXT NOT NULL DEFAULT '{}',

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    metadata_trust TEXT NOT NULL DEFAULT 'unknown',
    date_source TEXT NOT NULL DEFAULT 'unknown',
    taken_at_filename_guess TEXT,
    date_approved_for_lori INTEGER NOT NULL DEFAULT 0,
    location_approved_for_lori INTEGER NOT NULL DEFAULT 0
);

INSERT INTO photos_new (
    id, narrator_id, image_path, thumbnail_path, media_url, thumbnail_url,
    file_hash, description, date_value, date_precision, location_label,
    location_source, latitude, longitude, narrator_ready, needs_confirmation,
    uploaded_by_user_id, uploaded_at, last_edited_by_user_id, last_edited_at,
    deleted_at, metadata_json, created_at, updated_at, metadata_trust,
    date_source, taken_at_filename_guess, date_approved_for_lori,
    location_approved_for_lori
)
SELECT
    id, narrator_id, image_path, thumbnail_path, media_url, thumbnail_url,
    file_hash, description, date_value, date_precision, location_label,
    location_source, latitude, longitude, narrator_ready, needs_confirmation,
    uploaded_by_user_id, uploaded_at, last_edited_by_user_id, last_edited_at,
    deleted_at, metadata_json, created_at, updated_at, metadata_trust,
    date_source, taken_at_filename_guess, date_approved_for_lori,
    location_approved_for_lori
FROM photos;

DROP TABLE photos;
ALTER TABLE photos_new RENAME TO photos;

CREATE INDEX IF NOT EXISTS idx_photos_narrator_id
    ON photos(narrator_id);
CREATE INDEX IF NOT EXISTS idx_photos_narrator_ready
    ON photos(narrator_id, narrator_ready);
CREATE INDEX IF NOT EXISTS idx_photos_date
    ON photos(date_value, date_precision);
CREATE INDEX IF NOT EXISTS idx_photos_uploaded_by
    ON photos(uploaded_by_user_id);
CREATE INDEX IF NOT EXISTS idx_photos_deleted_at
    ON photos(deleted_at);

COMMIT;


------------------------------------------------------------
-- PART A3 -- rebuild trip_photo_links with the photos FK
--
-- Existing FKs to trips / trip_regions / trip_stops / trip_days are
-- preserved verbatim. The only change is the REFERENCES clause on
-- photo_id. Note the pairing: photos now cascades from people, and
-- links now cascade from photos, so deleting a narrator finally
-- reaches the trip links instead of stranding them.
------------------------------------------------------------

BEGIN IMMEDIATE;

CREATE TABLE trip_photo_links_new (
    id TEXT PRIMARY KEY,
    trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    trip_region_id TEXT REFERENCES trip_regions(id) ON DELETE SET NULL,
    trip_stop_id TEXT REFERENCES trip_stops(id) ON DELETE SET NULL,
    photo_id TEXT NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
    ord INTEGER NOT NULL DEFAULT 0,
    taken_at TEXT,
    latitude REAL,
    longitude REAL,
    assignment_method TEXT NOT NULL DEFAULT 'exif_time'
        CHECK (assignment_method IN (
            'manual', 'exif_time', 'exif_gps', 'album', 'csv', 'operator',
            'trip_upload', 'region_upload'
        )),
    cluster_confidence REAL,
    caption TEXT,
    narrator_caption TEXT,
    include_in_memoir INTEGER NOT NULL DEFAULT 1,
    thematic_tags_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    caption_approved_for_lori INTEGER NOT NULL DEFAULT 0,
    operator_context_note TEXT,
    operator_context_approved_for_lori INTEGER NOT NULL DEFAULT 0,
    trip_day_id TEXT REFERENCES trip_days(id) ON DELETE SET NULL,
    hidden INTEGER NOT NULL DEFAULT 0,
    hidden_at TEXT
);

INSERT INTO trip_photo_links_new (
    id, trip_id, trip_region_id, trip_stop_id, photo_id, ord, taken_at,
    latitude, longitude, assignment_method, cluster_confidence, caption,
    narrator_caption, include_in_memoir, thematic_tags_json, created_at,
    updated_at, caption_approved_for_lori, operator_context_note,
    operator_context_approved_for_lori, trip_day_id, hidden, hidden_at
)
SELECT
    id, trip_id, trip_region_id, trip_stop_id, photo_id, ord, taken_at,
    latitude, longitude, assignment_method, cluster_confidence, caption,
    narrator_caption, include_in_memoir, thematic_tags_json, created_at,
    updated_at, caption_approved_for_lori, operator_context_note,
    operator_context_approved_for_lori, trip_day_id, hidden, hidden_at
FROM trip_photo_links;

DROP TABLE trip_photo_links;
ALTER TABLE trip_photo_links_new RENAME TO trip_photo_links;

CREATE INDEX IF NOT EXISTS idx_trip_photo_links_trip_id
    ON trip_photo_links(trip_id);
CREATE INDEX IF NOT EXISTS idx_trip_photo_links_stop_id
    ON trip_photo_links(trip_stop_id);
CREATE INDEX IF NOT EXISTS idx_trip_photo_links_confidence
    ON trip_photo_links(trip_id, cluster_confidence);
CREATE UNIQUE INDEX IF NOT EXISTS idx_trip_photo_links_trip_photo
    ON trip_photo_links(trip_id, photo_id);
CREATE INDEX IF NOT EXISTS idx_trip_photo_links_day
    ON trip_photo_links(trip_day_id);
CREATE INDEX IF NOT EXISTS idx_trip_photo_links_hidden
    ON trip_photo_links(trip_id, hidden);

COMMIT;

PRAGMA foreign_keys = ON;


------------------------------------------------------------
-- PART B -- the import landing zone
------------------------------------------------------------

BEGIN IMMEDIATE;

------------------------------------------------------------
-- import_batch -- one external fetch, one row.
--
-- A batch is scoped to exactly one person. trip_id is nullable
-- because intake can happen before the operator has decided which
-- trip (if any) the material belongs to; binding it later is an
-- UPDATE, not a new batch.
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS import_batch (
    id TEXT PRIMARY KEY,

    person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    trip_id   TEXT REFERENCES trips(id) ON DELETE SET NULL,

    -- Where the material came from. Widening this list is a migration,
    -- which is the point: an unknown source cannot be written silently.
    source TEXT NOT NULL
        CHECK (source IN (
            'google_photos_picker',
            'google_takeout',
            'local_upload',
            'csv',
            'manual'
        )),

    -- Opaque provider-side handle for the fetch (an album id, a Takeout
    -- archive name, an upload session id). NOT a token, NOT a URL with
    -- credentials in it.
    external_ref TEXT,

    label TEXT,
    notes TEXT,

    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'closed', 'failed')),
    failure_reason TEXT,

    -- Denormalized progress counters. The repository layer owns these;
    -- they are a display convenience, never the source of truth.
    candidate_count INTEGER NOT NULL DEFAULT 0,
    accepted_count  INTEGER NOT NULL DEFAULT 0,
    rejected_count  INTEGER NOT NULL DEFAULT 0,

    created_by_user_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at  TEXT,

    -- Reversible retirement, same pattern as 0036.
    hidden INTEGER NOT NULL DEFAULT 0,
    hidden_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_import_batch_person
    ON import_batch(person_id, hidden);
CREATE INDEX IF NOT EXISTS idx_import_batch_trip
    ON import_batch(trip_id);
CREATE INDEX IF NOT EXISTS idx_import_batch_status
    ON import_batch(person_id, status);


------------------------------------------------------------
-- import_candidate -- one incoming item, one row.
--
-- Read the header before adding a column here. There is deliberately
-- no narrator_ready and no include_in_memoir. A candidate cannot be
-- narrator-ready or in the memoir, because it is not yet a photo.
--
-- person_id is denormalized from the batch on purpose so the
-- cross-person boundary check is a WHERE clause and not a join the
-- caller can forget.
--
-- photo_id is NULL until the operator accepts the candidate and it is
-- materialized into a photos row. ON DELETE SET NULL, not CASCADE:
-- if the photo is later removed, the candidate and its match reasons
-- survive as the record that the import happened.
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS import_candidate (
    id TEXT PRIMARY KEY,

    batch_id  TEXT NOT NULL REFERENCES import_batch(id) ON DELETE CASCADE,
    person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    trip_id   TEXT REFERENCES trips(id) ON DELETE SET NULL,
    photo_id  TEXT REFERENCES photos(id) ON DELETE SET NULL,

    -- Provider-side identity. Opaque, non-secret, non-replayable.
    external_id TEXT,

    file_hash TEXT,
    filename  TEXT,
    mime_type TEXT,
    byte_size INTEGER,

    taken_at TEXT,
    taken_at_source TEXT NOT NULL DEFAULT 'unknown'
        CHECK (taken_at_source IN (
            'exif', 'provider_metadata', 'filename_guess', 'operator', 'unknown'
        )),

    latitude  REAL,
    longitude REAL,
    location_source TEXT NOT NULL DEFAULT 'unknown'
        CHECK (location_source IN (
            'exif_gps', 'provider_metadata', 'typed_address', 'operator', 'unknown'
        )),

    -- Why the importer thinks this belongs where it says. JSON so the
    -- repository can round-trip the reasons back out unchanged for the
    -- Evidence Review Queue to display. Never prose, never a summary.
    match_reason_json TEXT NOT NULL DEFAULT '{}',
    match_confidence REAL,

    -- Intake state only. 'accepted' means an operator promoted it to a
    -- photos row; it says nothing about narrator readiness or memoir
    -- inclusion, and there is no column here that could.
    state TEXT NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'accepted', 'rejected', 'duplicate', 'error')),
    state_reason TEXT,

    reviewed_by_user_id TEXT,
    reviewed_at TEXT,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    hidden INTEGER NOT NULL DEFAULT 0,
    hidden_at TEXT
);

-- One provider item lands at most once per batch. Re-running the same
-- fetch is idempotent rather than duplicative.
CREATE UNIQUE INDEX IF NOT EXISTS idx_import_candidate_batch_external
    ON import_candidate(batch_id, external_id);

CREATE INDEX IF NOT EXISTS idx_import_candidate_batch_state
    ON import_candidate(batch_id, state);
CREATE INDEX IF NOT EXISTS idx_import_candidate_person_state
    ON import_candidate(person_id, state, hidden);
CREATE INDEX IF NOT EXISTS idx_import_candidate_trip
    ON import_candidate(trip_id);
CREATE INDEX IF NOT EXISTS idx_import_candidate_photo
    ON import_candidate(photo_id);
CREATE INDEX IF NOT EXISTS idx_import_candidate_hash
    ON import_candidate(person_id, file_hash);

COMMIT;

PRAGMA foreign_key_check;
