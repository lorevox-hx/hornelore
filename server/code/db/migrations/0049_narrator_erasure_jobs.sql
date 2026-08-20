-- 0049 — the erasure plan outlives the narrator it is about.
--
-- WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01, deletion integrity
-- (2026-08-20).
--
-- THE PROBLEM THIS TABLE EXISTS FOR. Every filesystem target a
-- narrator owns is derived from database rows -- their trips name the
-- trip-source directories, their import batches name the staging
-- directories, their conversations name the legacy transcript exports.
-- The moment the `people` row is deleted those rows cascade away, and
-- with them the only record of which directories were ever theirs.
--
-- So a deletion that removed the rows and then failed on the files had
-- destroyed its own ability to try again: the person row was gone, the
-- route answered 404, and the operator had no product path back to the
-- surviving directories. "Safe to retry" was true of the service and
-- false of the product.
--
-- The plan is therefore computed and COMMITTED BEFORE the authority is
-- destroyed, in its own connection so it survives a rollback of the
-- delete itself, and it is what a retry executes. It holds paths and
-- counts. It holds no narrator speech.
--
-- `status` is the honest three: `pending` written before the database
-- phase, then `complete` or `partial`. A crash between the two phases
-- leaves a pending row, which is a recoverable job rather than a
-- silent loss.

CREATE TABLE IF NOT EXISTS narrator_erasure_jobs (
    person_id       TEXT PRIMARY KEY,
    display_name    TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'complete', 'partial')),
    plan_json       TEXT NOT NULL DEFAULT '[]',
    result_json     TEXT NOT NULL DEFAULT '{}',
    attempts        INTEGER NOT NULL DEFAULT 0,
    requested_by    TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_erasure_jobs_status
    ON narrator_erasure_jobs(status, updated_at);
