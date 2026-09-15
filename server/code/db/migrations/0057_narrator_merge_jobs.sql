-- 0057 — durable merge jobs for Multi-Origin Merge/Remap.
--
-- WO-LOREVOX-MULTI-ORIGIN-MERGE-REMAP-01 §5, executor block.
--
-- ── WHY THIS IS NOT narrator_package_jobs ─────────────────────────────
--
-- 0054 is a RESTORE ledger and says so: `CHECK (kind IN ('restore'))`. The
-- first executor draft reused it with kind='merge' and the constraint
-- refused the very first job write — correctly. A restore is ONE package
-- into one root; a merge is TWO immutable packages plus one deterministic
-- plan into one root, and the singular `package_id` / `package_path`
-- columns cannot represent that without lying about their own names.
-- Widening 0054's CHECK would have made a table whose contract is "one
-- package arrived" quietly describe something else.
--
-- So: the Phase 3 durability SHAPE is reused, the Phase 3 TABLE is not.
--
-- ── WHAT IT MUST PROVE ────────────────────────────────────────────────
--
-- A merge copies files into the target root FIRST and inserts every row in
-- ONE transaction LAST, so a crash can leave staged files but can never
-- expose a half-merged narrator. This row is what makes the first half
-- recoverable: it is committed in its own connection BEFORE the first byte
-- lands, it names every file the job MAY create together with the sha256
-- that file must have, and its state says exactly how far the job got.
--
-- A file is therefore never judged by its pathname during recovery. Below
-- `db_committed` a file is removed only when its bytes hash to the digest
-- this job planned for that path; anything else sitting at a planned path
-- was not created by this job and is left alone and named. That is the
-- rule that stops recovery from deleting a pre-existing file.
--
-- Both source packages are pinned by full sha256, and the plan by its own
-- fingerprint, so a recovery — or a later human adjudication of the
-- conflicts a refused merge reported — can prove it is acting on exactly
-- the same inputs the decision was made against, never on data that has
-- since changed underneath it.
--
-- ── WHY THIS IS INSTALLATION STATE, NOT NARRATOR STATE ────────────────
--
-- The row is about an OPERATION on this installation. It holds ids, roots,
-- hashes and counts; no narrator speech, no photograph, no story. Declared
-- installation-owned in api/services/narrator_data_inventory.py: it never
-- travels in a package, and a narrator's erasure does not touch it — the
-- record of how a narrator was assembled must survive the narrator,
-- exactly as narrator_delete_audit records how one left.
--
-- States: staged → validated → files_copied → db_committed → complete
--         failed            (nothing of the job remains on disk or in the DB)
--         cleanup_required  (the job failed AND could not remove what it
--                            created; `files_json` names what is left)

CREATE TABLE IF NOT EXISTS narrator_merge_jobs (
    id                   TEXT PRIMARY KEY,
    state                TEXT NOT NULL DEFAULT 'staged'
        CHECK (state IN ('staged', 'validated', 'files_copied', 'db_committed',
                         'complete', 'failed', 'cleanup_required')),
    narrator_id          TEXT NOT NULL,
    target_root          TEXT NOT NULL,          -- the ABSOLUTE root the job wrote into

    -- the two immutable inputs, pinned by identity AND by bytes
    source_a_package_id  TEXT NOT NULL,
    source_a_sha256      TEXT NOT NULL,
    source_a_path        TEXT NOT NULL DEFAULT '',
    source_b_package_id  TEXT NOT NULL,
    source_b_sha256      TEXT NOT NULL,
    source_b_path        TEXT NOT NULL DEFAULT '',

    -- the decision those inputs produced, BOUND TO THIS TARGET: the source plan
    -- allocates installation-local integers from 1, which is right for the first
    -- narrator in a fresh root and wrong for the second — Kent's independently
    -- planned merge would ask for ids Christopher already occupies. Binding
    -- reallocates around what the target holds, so what lands is the BOUND plan
    -- and that is what this fingerprint covers.
    plan_fingerprint     TEXT NOT NULL,
    -- the target state the binding was computed against: schema, migrations,
    -- installation dependencies, occupied physical keys, planned-path occupancy.
    -- Deliberately NOT the whole installation — writing this very job row would
    -- change that, and a merge must not invalidate its own basis.
    target_basis         TEXT NOT NULL DEFAULT '',

    -- written BEFORE the first byte: target-relative path -> expected sha256
    file_manifest_json   TEXT NOT NULL DEFAULT '{}',
    -- grows as each file lands: target-relative paths this job CREATED
    files_json           TEXT NOT NULL DEFAULT '[]',
    -- what the plan says will be inserted, by table, and what was
    expected_counts_json TEXT NOT NULL DEFAULT '{}',
    counts_json          TEXT NOT NULL DEFAULT '{}',

    error                TEXT,
    recovery             TEXT,                   -- what a recovery pass decided, if any
    requested_by         TEXT NOT NULL DEFAULT '',
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_narrator_merge_jobs_narrator
    ON narrator_merge_jobs(narrator_id, state);

CREATE INDEX IF NOT EXISTS idx_narrator_merge_jobs_state
    ON narrator_merge_jobs(state);
