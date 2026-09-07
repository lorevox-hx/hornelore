-- 0053 — durable Operator overrides for the Lori intervention registry.
--
-- WO-LORI-BASELINE-RESET-AND-GUARD-LAB-01 Continuation A, section F.
--
-- ── WHAT THIS IS FOR ──────────────────────────────────────────────────
--
-- `lori_guard_registry` numbers 43 authorities that can change what a
-- narrator receives from Lori — routes that skip the model entirely,
-- prompt blocks, prose transforms, validators, replacements and one
-- final writer. The Walt+John diagnostic measured the delivered text
-- against Lori's raw output on 15 turns: raw was reasonable on 12,
-- delivered was better on ZERO and worse on 11, and nobody could say
-- which layer did it.
--
-- These two tables are what let an operator turn one authority off,
-- run a turn, and find out.
--
-- ── WHY THIS IS INSTALLATION STATE, NOT NARRATOR STATE ────────────────
--
-- There is deliberately NO person_id column. These are behaviour
-- controls for the deployment, not facts about a narrator, and the work
-- order forbids storing them in `profile_json`, `runtime71`, browser
-- localStorage or any narrator/session record.
--
-- The distinction is load-bearing rather than tidy. `profile_json` and
-- `runtime71` are narrator truth: they get exported, they reach the
-- memoir, and CLAUDE.md's provenance rules govern what may be written
-- there. An experiment about whether the word-limit guard helps is not
-- something the narrator said, and filing it beside their family
-- relationships would make an operator's Tuesday-afternoon experiment
-- part of somebody's life story.
--
-- ── ABSENT IS NOT THE SAME AS DEFAULT ─────────────────────────────────
--
-- A missing row means "no override" — the canonical default in code
-- applies, and it stays live. It does NOT mean "overridden to the
-- default value".
--
-- So RESET DELETES THE ROW. It must never copy the current default in,
-- because a copied default freezes today's value into the database and
-- silently detaches that authority from the registry forever: change
-- the canonical default in code afterwards and this installation
-- quietly keeps the old one, with nothing on screen to explain why.
-- The resolver in `lori_guard_authority.resolve()` distinguishes the two
-- cases by reason (`canonical_default` vs `operator_override`).
--
-- Only SWITCHABLE authorities may have a row. PROTECTED entries — acute
-- safety, the parked safety exemption, the two fail-closed paths, the
-- Profile Seed topic ledger, narrator floor ownership — are refused by
-- the API, and refused a second time by the resolver if a row somehow
-- exists. Defence in depth, because persisted state outlives the code
-- that wrote it.
--
-- ── WHY A SINGLETON REVISION ROW ──────────────────────────────────────
--
-- `revision` answers "which persisted configuration generation was
-- active?", and it is a different question from the two fingerprints:
--
--   registry_fingerprint    which authority MAP was the code using
--   revision                which persisted generation
--   selection_fingerprint   which effective selection the turn consumed
--
-- One hash cannot answer all three, and a turn is only fully
-- attributable when it carries all of them.
--
-- It advances ONCE per successful atomic operator change, not once per
-- authority touched. `All Switchable Off` moves 37 rows and the revision
-- by one, in one transaction — because 37 sequential writes would create
-- 37 revisions and let a narrator turn begin part-way through a
-- configuration change, on a mixture that no operator ever chose.
--
-- The revision is also what stale-UI protection compares: a write
-- carries the revision it was based on, and a mismatch is a conflict
-- rather than a silent overwrite of somebody else's newer state.
--
-- ── FAIL-SAFE DIRECTION ───────────────────────────────────────────────
--
-- An empty override table is normal production: every authority resolves
-- to its canonical default. That is the safe resting state, and it is
-- what a fresh install, a restored backup and a failed migration all
-- produce.

CREATE TABLE IF NOT EXISTS lori_guard_authority_override (
    -- Stable registry id. Ids are permanent and reserved; a retired
    -- authority keeps its number, so an orphaned row here is possible
    -- and the service ignores unknown ids rather than failing a turn.
    authority_id INTEGER PRIMARY KEY,
    enabled      INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    updated_at   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lori_guard_control_state (
    -- Singleton. The CHECK is the whole point: a second row would mean
    -- two competing revisions and no way to say which one a turn used.
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    revision   INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
    updated_at TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Seed the singleton at revision 0 = "canonical defaults, never changed".
INSERT OR IGNORE INTO lori_guard_control_state (id, revision)
VALUES (1, 0);
