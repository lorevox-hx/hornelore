-- 0056 — export jobs for the Lorevox Narrator Package operator surface.
--
-- WO-LOREVOX-PORTABLE-NARRATOR-01 Phase 5, §35.
--
-- ── WHY A SEPARATE TABLE ──────────────────────────────────────────────
--
-- 0054 `narrator_package_jobs` is the RESTORE ledger and its state machine
-- (validated → files_copied → db_committed → complete) is what crash
-- recovery reasons from; its `kind CHECK` admits only 'restore' and 0054 is
-- landed and immutable. An export has a different lifecycle and different
-- recovery semantics — nothing an export leaves behind on failure is
-- narrator state, only a partial file outside DATA_DIR — so it gets its own
-- ledger rather than a widened CHECK that would blur the one recovery
-- depends on (§16.1).
--
-- ── WHAT IT HOLDS ─────────────────────────────────────────────────────
--
-- Operational metadata only: which narrator, where the package was written,
-- the manifest the exporter produced (counts and warnings — no narrator
-- speech, no file bytes), and how it ended. Installation-owned: it never
-- travels in a package and erasure never touches it — an installation's
-- record of what it exported outlives the narrator it exported.
--
-- States: queued → running → complete | failed | refused
--   refused  = the exporter refused (ExportRefused); `refusal_json` names why

CREATE TABLE IF NOT EXISTS narrator_package_export_jobs (
    id              TEXT PRIMARY KEY,
    state           TEXT NOT NULL DEFAULT 'queued'
        CHECK (state IN ('queued', 'running', 'complete', 'failed', 'refused')),
    narrator_id     TEXT NOT NULL,
    display_name    TEXT NOT NULL DEFAULT '',
    data_root       TEXT NOT NULL,          -- the ABSOLUTE root the export read from
    out_dir         TEXT NOT NULL,          -- ABSOLUTE, outside DATA_DIR
    package_id      TEXT,
    package_path    TEXT,                   -- set at complete
    package_bytes   INTEGER,
    manifest_json   TEXT NOT NULL DEFAULT '{}',
    refusal_json    TEXT NOT NULL DEFAULT '[]',
    -- Stage progress for the operator: {"stage": "files", "done": 47, "total": 83,
    -- "stages": [...]} — completed / current / pending, never an invented percentage.
    progress_json   TEXT NOT NULL DEFAULT '{}',
    -- Retention: the server copy of a finished package can be removed by the
    -- operator; the job row stays as history. Removing the copy never removes
    -- the narrator (§16.1).
    package_removed_at TEXT,
    error           TEXT,
    requested_by    TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    started_at      TEXT,
    finished_at     TEXT,
    updated_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_narrator_package_export_jobs_narrator
    ON narrator_package_export_jobs(narrator_id, state);
