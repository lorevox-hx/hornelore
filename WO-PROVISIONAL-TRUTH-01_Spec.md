# WO-PROVISIONAL-TRUTH-01 — Provisional truth as default extraction destination

**Status:** ACTIVE — Phase A IN PROGRESS
**Authored:** 2026-05-04 (initial)
**Revised:** 2026-05-04 (scope drastically reduced after Path A architecture audit)
**Author lane:** Chris + Claude
**Locked principle:** CLAUDE.md principle #5 — *Provisional truth persists. Final truth waits for the operator. The interview never waits.*
**Prerequisite reading:** `docs/reports/PROVISIONAL_TRUTH_ARCHITECTURE_AUDIT_2026-05-04.md`

---

## One-line summary

Bridge `interview_projections.projection_json.pendingSuggestions` (where chat-extracted candidates already persist) into `_build_profile_seed` (what Lori reads). One Python function. No schema migration. No new tables.

---

## Why this WO exists (revised)

TEST-23 v1+v2 (2026-05-04) showed Mary's identity loss across cold restart. The original WO assumed BB needed a new `status`+`provenance` schema. The Path A architecture audit (2026-05-04) found the actual cause:

- Chat-extracted protected identity (fullName/DOB/POB) routes through projection-sync `_syncSuggestOnly` → `proj.pendingSuggestions`
- That array IS persisted to `interview_projections.projection_json` via PUT every 2s
- The data SURVIVES cold restart — `_loadProjectionFromBackend` restores it on narrator load
- BUT Lori's read function `_build_profile_seed` reads ONLY `profiles.profile_json`
- `profile_json` only gets updated by template preload + manual promotion paths — chat extractions never reach it

**The storage works. The bridge is missing.** Add the bridge, the Mary-loses-identity class closes.

---

## Locked principle (unchanged)

> Provisional truth persists. Final truth waits for the operator. The interview never waits.

The principle holds verbatim. What changed is how to enforce it: instead of new schema + write-path rerouting + operator surface + widget retirement, all that's needed is to teach `_build_profile_seed` to read provisional suggestions in addition to confirmed truth.

---

## Goals

1. **Read-side bridge.** `_build_profile_seed` reads `profiles.profile_json` (canonical) AND `interview_projections.projection_json.pendingSuggestions` (provisional). Provisional fills gaps where canonical is empty.
2. **No schema changes.** Existing tables hold all needed data.
3. **No write-path changes.** projection-sync's protected-identity gate (BUG-312) stays exactly as-is.
4. **Cross-restart proof.** TEST-23 v3 confirms Mary post-restart has name + DOB + POB recalled.

## Non-goals

- No migration `0005_*.sql`
- No new operator review surface (deferred to optional Phase D)
- No retirement of inline shadow-review widget (deferred to optional Phase C)
- No changes to extraction logic, BINDING-01, master eval, or extractor lane

---

## Architecture (confirmed by audit)

```
WRITE PATH (already works):
  narrator chat → extract.py → interview.js → projection-sync.project()
  → for protected identity from chat: _syncSuggestOnly → proj.pendingSuggestions
  → _debouncedPersist (every 2s) → PUT /api/interview-projections
  → interview_projections.projection_json in DB ✓

CROSS-RESTART (already works):
  cold reload → narrator re-selected by pid → _loadProjectionFromBackend
  → GET /api/interview-projections/<pid>
  → restores proj.fields and proj.pendingSuggestions to local state ✓

READ PATH (missing bridge):
  Lori turn → compose_memory_echo → _build_profile_seed(person_id)
  → reads profiles.profile_json ← ONLY THIS
  → assembles 9-bucket dict
  → ❌ never sees pendingSuggestions
  → returns empty buckets → Lori says "(not on record yet)"
```

After Phase A:

```
READ PATH (with bridge):
  Lori turn → compose_memory_echo → _build_profile_seed(person_id)
  → reads profiles.profile_json (primary, canonical)
  → reads interview_projections.projection_json (secondary, provisional)
  → assembles 9-bucket dict, preferring canonical when present, falling back to provisional
  → returns full dict ✓
```

---

## Phase breakdown

### Phase A — read-side bridge in `_build_profile_seed`

**Goal:** `_build_profile_seed(person_id)` reads from BOTH `profiles.profile_json` AND `interview_projections.projection_json`. Each bucket prefers canonical when present; falls back to provisional from `projection_json.fields[*].value` or `projection_json.pendingSuggestions[*].value`.

**Files:**
- `server/code/api/prompt_composer.py` — `_build_profile_seed` modified to merge from both sources
- `tests/test_provisional_profile_seed.py` (new) — unit tests covering: canonical-only, provisional-only, both (canonical wins), neither, narrator with pendingSuggestions only

**Acceptance:**
- `_build_profile_seed(pid)` returns the bucket dict assembled from profile_json + projection_json
- When profile_json has a value for a field, that wins (canonical priority preserved)
- When profile_json is empty for a field, the corresponding value from projection_json.fields[*] OR projection_json.pendingSuggestions[*] surfaces
- When both are empty, the bucket is omitted (existing behavior)
- Unit tests pass with 100% branch coverage on the new merge logic

**Scope:** ~half day.

### Phase B — TEST-23 v3 retest

**Goal:** verify Phase A landing closes the Mary-loses-identity class.

**Pre-conditions:**
- Phase A landed, AST green, unit tests pass
- Stack restarted to pick up the new prompt_composer

**Run:**

```bash
cd /mnt/c/Users/chris/hornelore && python -m scripts.ui.run_test23_two_person_resume --tag test23_v3 --clear-kv-between-narrators
```

**Acceptance gates (per Chris's spec):**
- Mary resume recall surfaces name/DOB/POB from projection pendingSuggestions
- Marvin resume recall surfaces name/DOB/POB
- pendingSuggestions survive restart (already working pre-Phase-A; v3 confirms it)
- profile_json remains untouched (no schema changes)
- No schema migrations applied (verify schema_migrations table count unchanged)
- No regression on Mary v2 era cell PASSes (5/7) or Marvin v2 era cell PASSes (4/7)
- Bonus: Marvin spouse_probe hits ≥2 of [wife, widower, letters, drawer, morning] (was 1/5 in v2)

**Scope:** ~half day (run + readout + side-by-side diff against v2).

### Phase C (OPTIONAL) — Retire inline shadow-review widget

**Goal:** the narrator-facing shadow-review popup (the `EDUCATION › EARLYCAREER` widget Chris screenshotted) becomes optional / dev-only since Lori now uses provisional values directly.

**Files:**
- `ui/js/shadow-review.js` — wrap widget render call in `window.LV_INLINE_SHADOW_REVIEW || false` env flag (default OFF)
- `WO-SOFT-TRANSCRIPT-REVIEW-CUE-01` (task #226) reframe: cue is informational only, not a write-blocker (it isn't anymore — provisional values flow regardless)

**Acceptance:**
- Default behavior: no inline shadow-review popup during narrator interview
- `LV_INLINE_SHADOW_REVIEW=true` re-enables for dev observation
- TEST-23 v3 confirms widget never appears during the run

**Scope:** ~half day. Optional — only ship after Phase A+B verify the read bridge works.

### Phase D (OPTIONAL) — Operator promotion surface

**Goal:** asynchronous Bug Panel "Pending Review" tab that lists provisional suggestions for the active narrator with Approve / Correct / Reject. Approve writes to `profiles.profile_json` (promoting provisional → canonical) and removes from pendingSuggestions.

**Files:**
- `server/code/api/routers/operator_pending_review.py` (new)
- `ui/js/bug-panel-pending-review.js` (new)
- `ui/css/bug-panel-pending-review.css` (new)
- `ui/hornelore1.0.html` — Bug Panel mount

**Acceptance:**
- Endpoint returns provisional rows from `interview_projections.projection_json.pendingSuggestions` for active narrator
- Approve: write to profile_json + remove from pendingSuggestions + persist projection
- Reject: remove from pendingSuggestions + log to audit
- Default-off env flag during initial rollout

**Scope:** ~1.5 days. Optional — Phase A is sufficient for the data-persistence fix; this phase formalizes operator-side review without requiring it.

### Phase E — Frontend BB state mirror sync (PROMOTED FROM PARKED 2026-05-05)

**Goal:** close the v6 audit gap where `state.bioBuilder.personal.firstName=None` despite `identityPhase=complete` and `basicsComplete=true`. Phase A fixed Lori's runtime knowledge (server-side prompt-composer reads from both surfaces). Phase E fixes the frontend's BB UI mirror so the narrator-room display reflects what the server already knows.

**Why this is now required, not optional:** the v6 TEST-23 evidence (2026-05-05) showed BB state firstName=None for both Mary and Marvin even though their identity values DO live in the backing stores. The harness scores narrator identity by reading `state.bioBuilder.personal.firstName` — and graded both narrators RED on identity even though Lori knew the values fine via memory_echo. Without Phase E, the harness can't grade narrator identity correctly AND the operator-facing BB UI looks broken to anyone looking at it.

**Scope:** when `projection_json` or `profile_json` gains a value (via narrator confirmation, operator promotion, or extractor projection update), mirror the value into the frontend `state.bioBuilder.personal` so the BB display surfaces match.

**Files:**
- `ui/js/projection-sync.js` — extend to write protected identity fields into `state.bioBuilder.personal` after the projection-sync round-trip completes successfully (subject to the BUG-312 protected_identity gate that already lives there)
- `ui/js/state.js` — possibly add a `_mirrorBioBuilderFromProjection()` helper that the projection-sync code calls
- `ui/js/app.js` — on narrator load (initial + post-restart re-select), trigger a one-shot hydrate from the latest `profile_json` + `projection_json.fields` into `state.bioBuilder.personal`
- New unit test fixture verifying that mirror is bidirectional + protected-identity-gated

**Acceptance:**

- After narrator onboarding completes (Mary types `mary Holts` → `2/29 1940` → `Minot ND` → correction), `state.bioBuilder.personal.firstName === "Mary"` is observable via `_capture_bb_state(page)` in the harness
- Same for `lastName`, `dateOfBirth`, `placeOfBirth` (the four BB-state-probe fields the v6 audit flagged)
- After cold-restart + re-select, the same fields are populated from `profile_json` (canonical) WITHOUT requiring an interview turn to fire — hydration happens at narrator-load time
- BUG-312 protected_identity gate continues to enforce that protected fields require a trusted source (`human_edit` / `preload` / `profile_hydrate` / `projection_promote`) — no silent overwrite via stochastic provisional values
- TEST-23 v7+ shows Mary's `bb_state_after_onboard.firstName === "Mary"` (was None in v4-v6); same for Marvin
- TEST-23 v7+ shows `bb_state_after_resume.firstName === "Mary"` post-restart (was None)

**Scope:** ~half day to one day. The protected-identity gate already exists (BUG-312, banked 2026-04-29); Phase E adds the WRITE side that BUG-312's READ guards already protect against.

**Risks:**

- **Mirror drift** — frontend `state.bioBuilder.personal` and backend `profile_json` could desync if the mirror logic has bugs. Mitigation: mirror is one-way (projection → BB display), never the reverse. BB display is read-only from the narrator's perspective in v1 (no narrator-side BB editing surface for protected identity).
- **Protected-identity gate friction** — if an extractor candidate has confidence ≥ 0.65 (provisional threshold) but the value is wrong, the mirror could surface wrong data to the BB display. Mitigation: BUG-312 gate already requires trusted source for write; mirror calls through that gate.
- **Resume hydration race** — on cold-restart, the mirror might fire before profile_json has loaded. Mitigation: hydration runs after `loadNarrator()` completes its profile_json fetch.

**Rollback:** revert the mirror logic. BB state mirror returns to v6 baseline (firstName=None despite truth being persisted). No regression on Lori's runtime knowledge (Phase A read-bridge stays intact).

**Sequencing:** lands AFTER BUG-UI-POSTRESTART-SESSION-START-01 because Phase E's acceptance includes post-restart BB state, and post-restart phases can't run until the cold-restart resume UI bug is fixed. Compose with WO-TIMELINE-RENDER-01 — the timeline reads from `profile_json` directly (NOT from `state.bioBuilder`), so Phase E doesn't gate the timeline lane.

---

## Total revised scope

| Phase | Estimate | Required? |
|---|---|---|
| **A — Read-bridge in `_build_profile_seed`** | ~half day | **LANDED 2026-05-04** |
| **B — TEST-23 v3 acceptance** | ~half day | **LANDED 2026-05-04** |
| C — Inline widget retirement | ~half day | optional |
| D — Operator promotion surface | ~1.5 days | optional |
| **E — Frontend BB state mirror sync (PROMOTED 2026-05-05)** | **~half to one day** | **YES — pre-parent-session blocker** |
| **Required remaining** | **~half to one day (Phase E)** | |
| **Full scope all phases** | **~3 days** | |

Down from the original 7-10 working day estimate. The architecture audit found that the persistence layer was already complete; what was missing was a single function-level bridge.

---

## What's NOT in this WO

- ~~Schema migration `0005_provisional_truth.sql`~~ — not needed
- ~~Add `status` + `provenance` columns to BB tables~~ — not needed
- ~~Backfill existing rows as `confirmed`~~ — not needed
- ~~New `bb_write_provisional` accessor~~ — not needed
- ~~Write-path retirement of shadow-review queue intermediate~~ — not needed (the queue IS the persistence layer; bridging the read end is sufficient)
- ~~Read-path harmonization across multiple read consumers~~ — not needed (only `_build_profile_seed` matters)

These were all in the original WO but turned out to be unnecessary once the audit revealed the actual data flow.

---

## Risk + rollback

**Risk 1: provisional values surface low-confidence noise to Lori.**
Mitigation: filter pendingSuggestions by confidence ≥ 0.65 in the bridge. Adjust threshold based on Phase B observations.
Rollback: revert `_build_profile_seed` to canonical-only.

**Risk 2: provisional values conflict with canonical (e.g., wrong name promoted via correction).**
Mitigation: canonical (profile_json) always wins when present. Provisional only fills gaps.
Rollback: same as above.

**Risk 3: TEST-23 v3 surfaces a regression on era cell PASSes.**
Mitigation: Phase A only adds reads; doesn't change Lori's prompt structure or extraction logic.
Rollback: revert.

---

## Acceptance summary

When Phase A + B land:

1. `_build_profile_seed` reads from both profile_json and projection_json
2. TEST-23 v3 Mary post-restart returns `name=True pob=True` (was False in v1+v2)
3. TEST-23 v3 Marvin post-restart name+pob retained
4. pendingSuggestions verified to survive cold restart (already true; just confirmed)
5. No schema changes applied
6. Master extractor eval unchanged (no regression on `r5h-followup-guard-v1`)

When those land, principle #5 is enforced in code via the read bridge, and Mary-loses-identity is closed permanently. Phase C and D become deferred polish.

---

## What goes into CLAUDE.md changelog when this WO lands

A single dated entry summarizing:
- Audit found the bridge was the whole problem; no schema work needed
- Phase A landed (read-side merge in `_build_profile_seed`)
- TEST-23 v3 result vs v2 baseline (Mary post-restart, Marvin post-restart, era cells)
- Master extractor eval unchanged
- Locked principle #5 enforced in code via the read bridge

Roughly 30-50 lines, much shorter than the original spec's planned changelog entry because the scope landed so much smaller.
