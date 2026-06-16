# WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01

**Status:** ACTIVE (drafted 2026-06-16, post WO-OPERATOR-NEW-NARRATOR-INTAKE-FORM-01 live verify)
**Owner:** Chris (sole developer)
**Lane:** Lori-behavior / Bio Builder consolidation
**Boris-style execution pack:** Phase 0 audit (done in WO draft) → Phase 1-4 build → Phase 5 tests → Phase 6 code review → Phase 7 live verify → Phase 7.5 backfill readiness report
**Branch policy:** Per CLAUDE.md 2026-06-15 rule — commits land directly on `main`. No feature branch.
**Three-agent scope convergence (2026-06-16):** Claude + ChatGPT + Gemini agree on tight scope. META_FEEDBACK / forbidden-empathy / VRAM-GUARD stay separate (different lanes). Full backfill stays separate (different risk class). This WO ships the read-source migration + the `primary_career` bug fix + a backfill **readiness report** (Phase 7.5) that scopes the future backfill WO.

---

## §1. Context

WO-OPERATOR-NEW-NARRATOR-INTAKE-FORM-01 landed yesterday (Phase 2B orchestrator at
`POST /api/people/intake` writing to `people` + `consent_attestations` +
`profiles.profile_json` + `bio_facts`). Live verify with the Jake Max Miller
harness confirmed 24 bio_facts rows + 2 consent rows + profile_json merge land
correctly on every run.

But the **Bio Builder questionnaire UI shows empty** for Jake despite all 24
operator-entered facts being live in the database. The questionnaire is the
operator's main interactive bio-data surface — if the intake form's writes
don't pre-populate the questionnaire walk, the operator has to re-enter every
field they already typed once. The WO didn't deliver what it was supposed to.

Root cause is straightforward: the questionnaire UI reads from a **separate
storage system** (`bio_builder_questionnaires.questionnaire_json` blob) that
predates the universal bio_facts seed work. The intake orchestrator writes to
`bio_facts` and `profile_json` but not to that legacy blob.

Two options for the long-term fix were considered:

- **Option A (dual-write):** Add a step to the intake orchestrator that also
  writes the bio_facts content into `bio_builder_questionnaires`. Keeps the
  legacy blob alive. Lower implementation cost. Permanent divergence risk
  between the two storage systems forever.

- **Option B (migrate questionnaire reads):** Repoint `get_questionnaire()` to
  read from `bio_facts` + `profile_json` (transforming into the section-keyed
  shape the UI expects), making bio_facts the single source of truth. Higher
  one-time implementation cost. Eliminates the divergence risk class entirely.

**Decision: Option B.** Three reasons: (1) single source of truth aligns with
the WO-BIO-UNIVERSAL Phase A-EF.5 architecture investment; (2) eliminates
the dual-write maintenance burden; (3) bio_facts carries status / source /
confidence metadata the questionnaire UI can use to distinguish operator-
entered from chat-extracted-provisional, which the legacy blob can't express.

The legacy `bio_builder_questionnaires` table stays in place during the
transition behind a default-off env flag (rollback path). Once Phase 7
verification is clean across all live narrators, the legacy table can be
read-only-archived in a later WO.

---

## §2. Acceptance gates

Numbered, atomic, all must pass before WO is called done.

1. **Bio Builder questionnaire UI loads Jake's 24 bio_facts** when the operator
   navigates to questionnaire for Jake. Personal section shows DOB
   1939-12-24, POB Stanley ND. Family section shows father Ervin, mother Leila
   Carkuff. Spouse section shows Janice 1959. Children section shows 3 entries.
   Military section shows Army + locations + rank. Faith section shows
   Catholic + heritage.

2. **Question walk skips fields already filled at `status='operator_entered'`.**
   The questionnaire doesn't re-ask the operator for things they entered via
   the intake form. Fields at `status='provisional'` are presented as "draft
   — please confirm" rather than blank.

3. **Writes during questionnaire walk land in `bio_facts`** at
   `status='operator_entered'`. The legacy `bio_builder_questionnaires` table
   receives ZERO new writes by default (env flag controls this — see §6 risk).

4. **`profile_json` stays in sync** as the projection mirror. After a
   questionnaire write, `_build_profile_seed` reads the same value Lori would
   see. Verified by hitting `/api/chat/ws` after a questionnaire write and
   confirming the seed has the new value.

5. **No regression on existing narrators.** Kent, Janice, Christopher,
   Mary, Marvin, and every other live narrator either show the same
   questionnaire content they did before (if they were on the legacy blob and
   not in bio_facts) OR show enriched content from bio_facts (whichever is
   richer per the merge rule in §4.3). Critically: no narrator goes BACKWARDS
   in what the questionnaire surface displays.

6. **`chronology_accordion` Born event still computes correctly.** The Lane B
   questionnaire fallback at `chronology_accordion.py:158-220` (strict subset
   `personal.dateOfBirth` / `personal.placeOfBirth` only) must continue to
   produce a Born event for narrators whose DOB/POB lives in bio_facts (or
   legacy blob, depending on which surface holds the value).

7. **Bug fix:** `primary_career` is written ONCE per intake, not twice.
   Currently the orchestrator double-writes (see §5).

8. **57 prior intake-form tests + new questionnaire tests all pass.**
   Specifically: `tests/test_narrator_intake_form.py` (20 tests),
   `tests/test_narrator_intake_orchestrator.py` (37 tests), and new test files
   from §5 (`test_bio_questionnaire_bio_facts_read.py`,
   `test_bio_questionnaire_section_transform.py`,
   `test_intake_orchestrator_primary_career_single_write.py`).

9. **Code review checklist signed off** — every box in §6 ticked before commit.

10. **Live verify passes** — Phase 7 manual eyeball on Jake + at least one
    other narrator confirms questionnaire UI loads cleanly with intake data.

11. **Phase 7.5 backfill readiness report delivered** at
    `docs/reports/WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01_BACKFILL_READINESS.md`,
    inventorying per-narrator gap + status-decision matrix + entity-array
    shape diff + recommended future-backfill approach. This is the deliverable
    that scopes the follow-up backfill WO so we're not guessing then.

---

## §3. Files to touch (final list, no placeholders)

### Backend

- `server/code/api/routers/questionnaire.py` — handler endpoints. Read path
  delegates to a new section transformer; write path fans out to bio_facts
  + profile_json instead of (or in addition to) the legacy blob.
- `server/code/api/services/bio_questionnaire_view.py` — **NEW**. Pure-stdlib
  service that takes `narrator_id` and returns the section-keyed dict the
  questionnaire UI expects, sourced from bio_facts + profile_json + (optional
  fallback) the legacy blob.
- `server/code/api/db.py` — extend `get_questionnaire()` + `upsert_questionnaire()`
  to consult the new service. Keep the legacy blob persistence functions intact
  for the rollback path.
- `server/code/api/routers/people.py` — **bug fix:** remove the duplicate
  `_try_write_fact("primary_career", ...)` call. Currently fires once with
  `years_working` value and again with `primary_career` value (lines under
  `# Education + work`); the second wins. Should be a single write of the
  `primary_career` field with the `primary_career` value, plus a separate
  `work_years` / `careerProgression` field for the years.

### Frontend

- `ui/js/bio-builder-questionnaire.js` — render status badges per field
  (operator_entered / provisional / confirmed / blank). No URL changes —
  the existing `BB_QQ_GET` / `BB_QQ_PUT` endpoints stay; their payload shape
  changes minimally (extra `status` / `source` fields per question).
- `ui/js/bio-builder-core.js` — surface the new per-field metadata in the
  section walk so already-filled fields are visually marked as "operator-
  entered" and skipped from "needs to be asked" counts.
- `ui/js/api.js` — no changes. `BB_QQ_GET` and `BB_QQ_PUT` URLs stay
  identical; only response/request body shape evolves (backwards-compatible).

### Tests

- `tests/test_bio_questionnaire_bio_facts_read.py` — **NEW**. Unit tests
  for the new `bio_questionnaire_view.py` service.
- `tests/test_bio_questionnaire_section_transform.py` — **NEW**. Tests for
  the bio_facts → section-keyed dict transformation.
- `tests/test_intake_orchestrator_primary_career_single_write.py` — **NEW**.
  Regression test for the §5 bug fix.

### Env / config

- `.env.example` — add `HORNELORE_QUESTIONNAIRE_BIO_FACTS_READ=1`
  (default-on after Phase 7 sign-off; default-off during rollout for the
  rollback path).

### Migrations

- None. No schema changes. Both `bio_facts` and `bio_builder_questionnaires`
  tables already exist.

### Docs

- `docs/architecture/BIO-QUESTIONNAIRE-MIGRATION.md` — **NEW**. Captures the
  before/after read paths, the transformer schema, the rollback procedure, and
  the rationale for retiring the legacy blob.
- `docs/reports/WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01_BACKFILL_READINESS.md`
  — **NEW** (Phase 7.5 deliverable). Per-narrator backfill inventory + decision
  matrix.
- `CLAUDE.md` changelog entry on landing.

---

## §4. Phase plan

### Phase 0: Audit (DONE in WO draft, 2026-06-16)

Findings logged in §1 + §3. The audit revealed:

- Questionnaire UI reads `bio_builder_questionnaires.questionnaire_json` blob
  via `get_questionnaire()` at `db.py:4545-4571`
- Blob format is hierarchical: `{personal: {...}, family: {...}, ...}` with
  `_legacyRemovedSections` migration markers
- `chronology_accordion.py:367` reads `questionnaire.get("questionnaire", {})`
  for the Born event Lane B (strict subset: only `personal.dateOfBirth` and
  `personal.placeOfBirth` are promoted from questionnaire to chronology)
- `bio_gap_map.py` and `operator_bio_editor.py` already read bio_facts — they
  are the model for what the new questionnaire path should look like

### Phase 1: Backend read swap (~2 hours)

1. Create `server/code/api/services/bio_questionnaire_view.py` with one
   public function `build_questionnaire_view(narrator_id, source_preference="bio_facts")`
   returning the section-keyed dict the UI expects.
2. Implement the transformer: for each `field_key` in `bio_schema`, look up
   the bio_facts row at `status in ('operator_entered', 'confirmed', 'provisional')`,
   map field_key → section path (e.g., `father_name` → `family.parents.fatherFullName`),
   attach `{value, status, source}` metadata per question.
3. For entity arrays (siblings, spouses, children) that don't fit the
   field-keyed bio_facts shape, read from `profile_json.siblings[]`,
   `profile_json.spouses[]`, `profile_json.children[]` (which the intake
   orchestrator already writes).
4. In `get_questionnaire()` at `db.py`, add a gated call to the new
   transformer behind `HORNELORE_QUESTIONNAIRE_BIO_FACTS_READ` env flag.
   Default OFF during initial rollout. Legacy blob read path remains the
   fallback when flag is OFF.

### Phase 2: Frontend rendering (~1.5 hours)

1. Extend the questionnaire question renderer in `bio-builder-questionnaire.js`
   to read `status` / `source` per question and render:
   - `operator_entered` → ✓ checkmark + "you entered this" hover
   - `provisional` → ⚠ amber + "Lori extracted this — confirm or correct"
   - `confirmed` → ✓ checkmark + "confirmed earlier"
   - `blank` → standard input prompt
2. Update the section-progress counter in `bio-builder-core.js` to count only
   `blank` questions as "needs asking", so already-filled questions don't
   inflate the "X of Y unanswered" stat.

### Phase 3: Write path (~2 hours)

1. Extend `put_questionnaire_route()` to fan out writes:
   - For scalar field_keys present in `bio_schema`: write to `bio_facts` at
     `status='operator_entered'` via the existing `bio_fact_create()` helper
   - For entity arrays (siblings/spouses/children): merge into `profile_json`
     via `update_profile_json(merge=True)`
   - Legacy blob write at `upsert_questionnaire()` gated behind a SECOND env
     flag `HORNELORE_QUESTIONNAIRE_LEGACY_BLOB_WRITE=0` (default-off after
     Phase 7) so the blob can be retired cleanly later
2. Reuse the `_split_name` / `_pronoun_label` / `_write_bio_fact_safe` helpers
   already in `routers/people.py` to keep one canonical write path.

### Phase 4: Bug fix — `primary_career` single-write (~30 min)

1. In `routers/people.py`, the Education + work block currently writes
   `primary_career` twice:
   - Once with `ew.years_working` value (alongside `careerProgression`)
   - Once with `ew.primary_career` value
2. Fix: `primary_career` field_key gets ONE write with `ew.primary_career`
   value. The `years_working` value goes to a separate `work_years_range`
   field_key (or to `profile_json.education.careerProgression` only — bio_facts
   row only if the bio_schema seed defines `work_years_range`).
3. Add regression test `test_intake_orchestrator_primary_career_single_write.py`
   that creates a narrator with both fields populated and asserts exactly ONE
   bio_facts row with field_key=`primary_career` exists.

### Phase 5: Tests (~1.5 hours)

1. `tests/test_bio_questionnaire_bio_facts_read.py` — 12 tests:
   - Empty narrator returns empty sections
   - Narrator with operator_entered facts returns those + status='operator_entered'
   - Narrator with mixed provisional + operator_entered renders correctly
   - Entity arrays sourced from profile_json with correct shape
   - Status flag controls source (bio_facts vs legacy blob fallback)
   - Section transformer handles all 5 sections (identity, family,
     marriage, education, military, faith, today) — one test per section
   - Unknown field_key in bio_facts is gracefully ignored (no crash)
2. `tests/test_bio_questionnaire_section_transform.py` — 8 tests:
   - field_key → section path mapping is exhaustive
   - Multiple bio_facts rows with same field_key resolve via status priority
     (confirmed > operator_entered > provisional)
   - profile_json arrays merged into entity sections correctly
3. `tests/test_intake_orchestrator_primary_career_single_write.py` — 3 tests:
   - Single write when only primary_career provided
   - Single write when both primary_career and years_working provided
   - No write when neither provided

### Phase 6: Code review checklist (§6)

Every box ticked before commit.

### Phase 7: Live verify (~30 min)

1. Restart stack with `HORNELORE_QUESTIONNAIRE_BIO_FACTS_READ=1` set
2. Open the FE, hard-refresh
3. Click into Jake's questionnaire — confirm acceptance gate #1 (all 24
   intake fields surface as `operator_entered`)
4. Walk into the family section — confirm parents/siblings/spouse/children
   all populate from profile_json
5. Edit one field in the questionnaire and save — confirm a new bio_facts
   row appears at `status='operator_entered'` with the new value
6. Restart stack — confirm the new value persists and is the one shown
7. Click into Kent's questionnaire — confirm his old questionnaire content
   still shows (whether sourced from legacy blob via fallback or already
   migrated to bio_facts)
8. Eyeball the chronology accordion for Jake — confirm Born event still
   computes from his DOB + POB

### Phase 7.5: Legacy backfill readiness report (~1.5 hours)

**Purpose:** Inventory-only. The report does NOT migrate any data. It captures
exactly what a future backfill WO will need to decide, so when that WO opens
we're not guessing about scope.

**Deliverable:** `docs/reports/WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01_BACKFILL_READINESS.md`

**Sections of the report:**

1. **Per-narrator inventory.** For every narrator in the people table, count:
   - Number of bio_facts rows by status (operator_entered / confirmed /
     provisional / etc.)
   - Whether `bio_builder_questionnaires` blob exists and has content
   - Whether `profiles.profile_json` is populated
   - Overlap: which legacy blob field_keys also have bio_facts rows (potential
     conflict territory)

2. **Per-field-key mapping.** For each section in the legacy blob format,
   identify the bio_schema field_key it maps to. Flag fields where the legacy
   blob has content but no bio_schema field exists (orphaned data — design
   decision needed).

3. **Status decision matrix.** Each row of the legacy blob backfill needs a
   `status` value when it lands in bio_facts. Options and their tradeoffs:
   - `operator_entered` — wrong if the legacy blob row came from a chat extraction
   - `confirmed` — wrong if it didn't go through the promotion pipeline
   - `provisional` — re-asks the operator unnecessarily for content they may
     already have confirmed
   - **New status `legacy_blob_migrated`** — clean separation but requires
     a bio_facts schema enum extension
   - Recommendation column for each field_key.

4. **Entity-array shape diff.** Legacy blob has `personal.parents` /
   `family.siblings` etc. The new profile_json schema (from intake orchestrator)
   has `parents[]` / `siblings[]` arrays with different key naming
   (`firstName` vs `name`, etc.). Document the shape mismatch and propose a
   normalization adapter.

5. **Per-narrator risk classification.** For each narrator, classify:
   - **Clean** — legacy blob maps 1:1 to bio_schema, no conflicts, safe to backfill
   - **Conflict** — legacy blob has values that differ from existing bio_facts;
     need merge rules
   - **Orphaned** — legacy blob has data with no bio_schema field; need design call
   - **Skip** — narrator was never actively used; backfill not needed

6. **Recommended future backfill approach.** Should the backfill WO use:
   - Dry-run-first script that writes to a shadow table for operator review?
   - Per-narrator opt-in (operator clicks "migrate this narrator" in Bug Panel)?
   - All-narrators batch with rollback via the legacy blob fallback?
   - The new `legacy_blob_migrated` status idea, or one of the existing statuses?

7. **Cost estimate** for the future backfill WO based on the inventory results.

**Implementation:** Write a small audit script
`scripts/audit_legacy_questionnaire_backfill.py` that runs read-only against
the live DB, emits the inventory tables as the report's data sections. The
human-judgment sections (recommendations, design calls) get written into the
report manually based on the audit script's output.

---

## §5. Bug fix (Phase 4 detail)

**Bug:** `primary_career` written twice per intake.

**Repro:** Run the Jake harness or POST a minimal intake payload with both
`education_work.primary_career` and `education_work.years_working` set.
Inspect the bio_facts table afterward — you'll find either two rows with
`field_key='primary_career'` (if the schema allows duplicates) or one row
whose value was overwritten by the second write.

**Code location:** `server/code/api/routers/people.py`, in the intake
orchestrator's Education + work block (search for `_try_write_fact("primary_career"`).

**Current code (paraphrased):**
```python
if (ew.years_working or "").strip():
    edu_block["careerProgression"] = ew.years_working
    _try_write_fact("primary_career", ew.years_working)   # ← first write
if edu_block:
    profile_patch["education"] = edu_block
if (ew.primary_career or "").strip():
    profile_patch.setdefault("community", {})["role"] = ew.primary_career
    _try_write_fact("primary_career", ew.primary_career)  # ← second write
```

**Fix:** Move the `primary_career` write into the `if ew.primary_career` block
only. If the bio_schema seed defines a `work_years_range` (or similar) field
for the years-worked value, the `years_working` write goes there. Otherwise,
`years_working` lives only in `profile_json.education.careerProgression`.

**Regression test:** `test_intake_orchestrator_primary_career_single_write.py`.

---

## §6. Code review checklist (mandatory pre-commit)

Reviewer (or self-review if solo): tick every box before commit.

### Backend
- [ ] `bio_questionnaire_view.py` has no imports from `extract.py`,
      `prompt_composer.py`, `memory_echo.py`, `llm_api.py`, `chat_ws.py`,
      `family_truth.py`, or `safety.py` (LAW 3 isolation — purity gate)
- [ ] All new database reads use `_connect()` + try/finally + `con.close()`
      (matches BUG-DBLOCK-01 hygiene pattern)
- [ ] All writes go through `bio_fact_create()` / `update_profile_json()` —
      no raw SQL writes to bio_facts or profile_json from the questionnaire
      router
- [ ] Env flag `HORNELORE_QUESTIONNAIRE_BIO_FACTS_READ` is documented in
      `.env.example` with a comment explaining default-off rollout posture
- [ ] Env flag `HORNELORE_QUESTIONNAIRE_LEGACY_BLOB_WRITE` is also documented
- [ ] `get_questionnaire()` behavior with flag OFF is byte-identical to the
      pre-WO behavior — verified by a regression test
- [ ] `chronology_accordion.py:367` still computes a Born event for narrators
      whose DOB/POB lives in bio_facts (not just legacy blob)
- [ ] Per-question response payload includes `{value, status, source}` triple
      — UI can render badge per question without re-querying

### Frontend
- [ ] Questionnaire UI renders status badges (✓ / ⚠ / blank) per question
- [ ] Operator-entered questions don't count toward the "X of Y unanswered"
      stat — confirmed via DOM inspection on Jake
- [ ] Questionnaire string changes are narrator-respectful (no "field" /
      "schema" / "database" jargon visible to the operator)
- [ ] No legacy questionnaire-only state code paths (search for
      `_legacyRemovedSections` writes — read-only is fine, writes are not)

### Tests
- [ ] All 12 tests in `test_bio_questionnaire_bio_facts_read.py` green
- [ ] All 8 tests in `test_bio_questionnaire_section_transform.py` green
- [ ] All 3 tests in `test_intake_orchestrator_primary_career_single_write.py`
      green
- [ ] Prior 57 intake-form tests still green (regression check)
- [ ] Prior bio_facts CRUD + bio_schema seed tests still green

### Live (after Phase 7)
- [ ] Jake's questionnaire shows all 24 intake fields as `operator_entered`
- [ ] Kent's questionnaire shows his pre-existing content (no regression)
- [ ] A fresh questionnaire write for any narrator produces a new bio_facts
      row at `status='operator_entered'`
- [ ] Lori sees the new value on the next chat turn via `_build_profile_seed`
- [ ] `chronology_accordion` Born event still computes
- [ ] `meal_tickets` substring still absent from Lori's output (the May 11
      regression marker)

### Backfill readiness (Phase 7.5)
- [ ] Audit script `scripts/audit_legacy_questionnaire_backfill.py` runs
      read-only — confirmed via code review that no writes occur
- [ ] Per-narrator inventory rendered into report — all narrators in people
      table counted
- [ ] Status decision matrix populated with a recommendation per field_key
- [ ] Entity-array shape diff documented with normalization adapter sketch
- [ ] Per-narrator risk classification (clean / conflict / orphaned / skip)
      complete
- [ ] Recommended future-backfill approach selected with rationale
- [ ] Cost estimate for the future backfill WO included

### Hygiene
- [ ] Tree was clean before this WO started (per CLAUDE.md git hygiene gate)
- [ ] CLAUDE.md changelog entry added on landing
- [ ] `MASTER_WORK_ORDER_CHECKLIST.md` updated to mark this WO complete

---

## §7. Risk / rollback

**Default-off rollout posture.** Both env flags default to OFF in `.env.example`.
After Phase 7 verify passes for Jake AND at least one pre-existing live narrator
(Kent or Janice), Chris flips `HORNELORE_QUESTIONNAIRE_BIO_FACTS_READ=1` in
his local `.env` and restarts the stack. If anything misbehaves on the live
narrators, flip the flag back to 0 and the legacy blob read path resumes.

**Legacy blob writes** stay enabled (`HORNELORE_QUESTIONNAIRE_LEGACY_BLOB_WRITE=1`
default during Phase 6 transition) so the legacy table stays in sync as a
fallback safety net. Once we're confident in the new read path, that second
flag flips to 0 and the legacy table goes read-only-archive.

**Out of scope for this WO:** Migrating existing narrators' legacy blob
content INTO bio_facts. The transformer in Phase 1 step 4 falls back to the
legacy blob when bio_facts is empty for a given field. A one-time backfill
migration is a separate follow-up WO (`WO-BIO-QUESTIONNAIRE-LEGACY-BACKFILL-01`,
to be drafted after Phase 7.5 readiness report sign-off).

---

## §8. Estimated effort

- Phase 0 audit: DONE (~30 min sunk in WO draft)
- Phase 1 backend read: 2 hours
- Phase 2 frontend rendering: 1.5 hours
- Phase 3 write path: 2 hours
- Phase 4 bug fix: 30 min
- Phase 5 tests: 1.5 hours
- Phase 6 code review: 30 min
- Phase 7 live verify: 30 min
- Phase 7.5 backfill readiness report: 1.5 hours

**Total: ~10 hours of focused work.** Realistic 1.5-day landing if no
unexpected schema or LAW 3 surprises surface during Phase 1. Single-day is
possible if Phase 7.5's audit script comes together quickly.

---

## §9. Out of scope

Per three-agent scope convergence (Claude + ChatGPT + Gemini, 2026-06-16):
the following are real bugs / real future work but live in different lanes.
Bundling them with this WO would force one commit to touch unrelated surfaces
and make rollback messy. Each gets its own WO.

- **Bonus-probe forbidden-empathy** (Lori-behavior lane). Run 1 of the Jake
  harness had Lori reply to the closing-marker probe with the forbidden
  "Thank you for sharing your story…" opener. Lives in prompt_composer or
  a runtime filter. Different code, different tests, different rollback. **Separate WO.**

- **META_FEEDBACK classifier mis-tagging chapters 1+2 as corrections** (task
  #88). chat_ws.py witness classifier produces "Got it — [Title Cased]. Did I
  get that name right?" deterministic template on the first two narrator
  turns of a long-narration session. Smoking gun in api.log already
  identified. Different code lane (chat_ws.py, not bio-builder), different
  test surface. **Separate WO.**

- **VRAM-GUARD truncating long-chapter prompts** from 10938 → 8192 tokens
  (Phase 3 of a later context-budget WO). Engineering problem in prompt
  assembly + token budgeting. Now that intake seeds 24 bio_facts into
  runtime71, prompts are pushing past the soft cap. Affects every narrator
  with a rich profile, not just bio-builder. **Separate WO.**

- **Full legacy blob backfill** (`WO-BIO-QUESTIONNAIRE-LEGACY-BACKFILL-01`,
  to be drafted). Phase 7.5 of THIS WO scopes that future WO via a
  readiness report — what fields, what statuses, what shape adapters, what
  risk classification per narrator. The backfill itself stays separate
  because (a) the status decision is its own design call; (b) the entity-
  array shape diff needs a normalization adapter; (c) touching production
  data on every existing narrator at once is a different risk class than a
  flag-gated read-source swap.

- **Retiring the `bio_builder_questionnaires` table entirely**. Once this WO
  ships and runs clean for ~2 weeks with both env flags flipped to the new
  defaults, the legacy table holds nothing new and can be archived /
  dropped. Future quiet-session WO, not blocked by anything.

---

## §10. References

- WO-OPERATOR-NEW-NARRATOR-INTAKE-FORM-01 (parent — landed 2026-06-15)
- WO-BIO-UNIVERSAL Phase A-EF.5 (the bio_facts surface this WO unifies on)
- `docs/specs/JAKE-LONG-NARRATION-TEST-SPEC.md` (the harness that surfaced
  this gap in live verify)
- CLAUDE.md design principles 5 (provisional truth persists), 6 (Lorevox is
  the memory system), 7 (visible projection), 8 (operator seeds known structure)
- Task #88 (META_FEEDBACK investigation — separate Lori-behavior lane, not
  blocked by this WO)
- Three-agent scope convergence note (Claude + ChatGPT + Gemini, 2026-06-16)
  agreeing on tight scope: don't bundle META_FEEDBACK, forbidden-empathy,
  VRAM-GUARD, or full backfill. Do add Phase 7.5 readiness report.
