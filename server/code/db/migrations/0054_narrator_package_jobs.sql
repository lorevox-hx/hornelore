-- 0054 — durable restore jobs for the Lorevox Narrator Package.
--
-- WO-LOREVOX-PORTABLE-NARRATOR-01 Phase 3, §12 "Restore atomicity and
-- crash recovery".
--
-- ── WHAT THIS IS FOR ──────────────────────────────────────────────────
--
-- A Restore copies files into DATA_DIR FIRST and inserts the narrator's
-- rows in ONE transaction LAST, so a crash can leave staged files but can
-- never expose a half-imported narrator. The job row is what makes the
-- first half recoverable: it is committed in its own connection BEFORE
-- the first byte lands, it records every file the job created, and its
-- state says exactly how far the job got. A restore that stops between
-- `files_copied` and `db_committed` is a set of files this row can name
-- and remove; without the row they are orphans nobody can attribute.
--
-- ── WHY THIS IS INSTALLATION STATE, NOT NARRATOR STATE ────────────────
--
-- The row is about an OPERATION on this installation, not about a
-- person's life. It holds a narrator id, a package id, paths and counts.
-- It holds no narrator speech, no photograph, no story. It is declared
-- installation-owned in api/services/narrator_data_inventory.py: it never
-- travels in a package, and a narrator's erasure does not touch it — the
-- record of how a narrator arrived must survive the narrator, exactly as
-- narrator_delete_audit records how one left.
--
-- States: staged → validated → files_copied → db_committed → complete
--         failed            (nothing of the job remains on disk or in the DB)
--         cleanup_required  (the job failed AND could not remove what it
--                            created; `files_json` names what is left)

CREATE TABLE IF NOT EXISTS narrator_package_jobs (
    id              TEXT PRIMARY KEY,
    kind            TEXT NOT NULL DEFAULT 'restore'
        CHECK (kind IN ('restore')),
    state           TEXT NOT NULL DEFAULT 'staged'
        CHECK (state IN ('staged', 'validated', 'files_copied', 'db_committed',
                         'complete', 'failed', 'cleanup_required')),
    package_id      TEXT NOT NULL,
    package_path    TEXT NOT NULL,
    narrator_id     TEXT NOT NULL,
    data_root       TEXT NOT NULL,          -- the ABSOLUTE root the job wrote into
    source_commit   TEXT NOT NULL DEFAULT '',
    files_json      TEXT NOT NULL DEFAULT '[]',   -- DATA_DIR-relative paths this job created
    counts_json     TEXT NOT NULL DEFAULT '{}',   -- record counts inserted, by table
    error           TEXT,
    requested_by    TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_narrator_package_jobs_narrator
    ON narrator_package_jobs(narrator_id, state);
