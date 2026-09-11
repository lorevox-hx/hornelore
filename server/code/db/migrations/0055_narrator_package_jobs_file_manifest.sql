-- 0055 — the restore job carries its own payload manifest.
--
-- WO-LOREVOX-PORTABLE-NARRATOR-01 Phase 3 recovery correction, 2026-09-11.
--
-- 0054 gave a restore job `files_json`: the DATA_DIR-relative paths the job
-- CREATED. Review of the first implementation found two things that list
-- cannot do on its own:
--
--   * after a process death mid-copy, a path the job PLANNED but never
--     created may later hold someone else's bytes — recovery must not
--     delete on the strength of a pathname;
--   * after a death between COMMIT and `complete`, recovery must verify the
--     restored files without the original .lorevox.zip, which in Phase 5
--     lives in upload staging and may be gone by the time anything restarts.
--
-- So the job now records, BEFORE the first byte lands, the package's own
-- payload manifest for this narrator: relative path -> expected SHA-256.
-- Recovery deletes a file only when its bytes match that digest, and
-- verifies a committed restore against it with no package in hand.
--
-- 0054 is landed and unchanged; this is an additive column. `files_json`
-- keeps exactly the meaning 0054 gave it and is now updated as each file is
-- created, so it is never a plan masquerading as a record.

ALTER TABLE narrator_package_jobs
    ADD COLUMN file_manifest_json TEXT NOT NULL DEFAULT '{}';
