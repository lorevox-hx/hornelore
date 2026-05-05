# Provisional Truth Architecture Audit — 2026-05-04

**Purpose:** Per Chris's Path A directive, trace the actual write/read architecture for narrator truth before authoring schema changes. This audit replaces the speculative architecture in WO-PROVISIONAL-TRUTH-01_Spec.md with the real picture.

**Headline finding:** The schema is fine. The data IS being persisted. **The missing piece is a single read-side bridge** in `prompt_composer._build_profile_seed`. The WO scope drops from ~7 working days to ~1-2 working days.

---

## What I traced

The 9 paths Chris listed:

1. extract.py accepted-item path
2. shadow-review candidate path
3. identity_change_log path
4. bio_builder_questionnaires JSON blob writes
5. interview_projections writes
6. family_truth_rows / family_truth_promoted writes
7. memory_echo read path
8. prompt_composer read path
9. TEST-23 BB capture / read path

---

## The actual architecture (confirmed by code reads)

### Tables that hold narrator truth

| Table | Shape | Who writes | Who reads | Persists? |
|---|---|---|---|---|
| `profiles.profile_json` | JSON blob, one per narrator | template preload (`narrator-preload.js`) + promotion path | **`prompt_composer._build_profile_seed` (Lori)** | ✓ |
| `bio_builder_questionnaires.questionnaire_json` | JSON blob, one per narrator | BB UI (PUT /api/bio-builder/questionnaire) — direct trusted writes | BB UI re-render | ✓ |
| `interview_projections.projection_json` | JSON blob, one per narrator | `projection-sync.js` _debouncedPersist (every 2s) | `projection-sync.js` `_loadProjectionFromBackend` on narrator load | ✓ |
| `identity_change_log` | row-per-change, status='proposed' default | proposed identity changes | identity intake review surface | ✓ |
| `family_truth_notes` / `_rows` / `_promoted` | row-per-fact, 4-layer pipeline | shadow archive → proposal → review → promoted | family-truth UI + promotion path | ✓ |
| `facts` | legacy row-per-fact | (legacy) | (legacy, partially backfilled to family_truth_rows) | ✓ |

**Six storage layers, four read consumers, and they don't all share data.**

### The real write path for chat-extracted candidates

```
narrator types → chat_ws.py handles WS turn
↓
chat_ws.py emits the user turn + Lori's reply
↓
interview.js client-side:
  POST /api/extract-fields  (extract.py)
  ← {items: [{fieldPath, value, writeMode, confidence}]}
↓
For each item:
  LorevoxProjectionSync.project(fieldPath, value, {source: "backend_extract", ...})
↓
projection-sync.js project():
  ┌─ Protected identity (fullName/preferredName/dateOfBirth/placeOfBirth/birthOrder)
  │  AND untrusted source (anything other than human_edit/preload/profile_hydrate)
  │     → _syncSuggestOnly()  →  proj.pendingSuggestions
  │     → return false (NEVER writes proj.fields, NEVER writes bb.questionnaire)
  │
  ├─ Non-protected, prefill_if_blank
  │     → writes proj.fields[path]
  │     → _syncToBioBuilder() → _syncPrefillIfBlank() → writes bb.questionnaire if empty
  │     → _triggerBBPersist() → PUT /api/bio-builder/questionnaire → questionnaire_json (DB)
  │
  ├─ Non-protected, candidate_only (parents/siblings/etc.)
  │     → writes proj.fields[path]
  │     → _syncToBioBuilder() → _syncCandidateOnly() → writes bb.questionnaire.candidates[]
  │     → _triggerBBPersist()
  │
  └─ Non-protected, suggest_only
        → writes proj.fields[path]
        → _syncSuggestOnly() → proj.pendingSuggestions
↓
_debouncedPersist (every 2s):
  PUT /api/interview-projections → projection_json (DB) — includes proj.fields AND proj.pendingSuggestions
```

### The real read path that Lori uses

```
chat_ws.py (turn_mode = "memory_echo" or "interview"):
↓
prompt_composer.compose_memory_echo(person_id, ...)
↓
_build_profile_seed(person_id)
  → reads profiles.profile_json
  → assembles 9-bucket dict (childhood_home, parents_work, heritage, education,
    military, career, partner, children, life_stage)
↓
profile_seed → embedded into Lori's system prompt
↓
Lori responds using profile_seed values (or "(not on record yet)" if empty bucket)
```

**Critical fact:** `_build_profile_seed` reads ONLY `profiles.profile_json`. It does NOT read:

- `bio_builder_questionnaires.questionnaire_json`
- `interview_projections.projection_json` (where the pendingSuggestions live)
- `family_truth_promoted`
- `identity_change_log`

The doc-comment in `_build_profile_seed` says these other sources are "folded into profile_json by [other paths]" — but **for chat-extracted candidates, no such fold happens.** The extracted candidate sits in `projection_json.pendingSuggestions`, persists across restart, but Lori never reads it.

---

## The exact failure mechanism for Mary

Step-by-step trace for Mary v2:

1. Mary types `"mary Holts"` in chat
2. extract.py returns `[{fieldPath: "personal.fullName", value: "Mary Holts", writeMode: "prefill_if_blank", confidence: 0.92}]`
3. interview.js calls `LorevoxProjectionSync.project("personal.fullName", "Mary Holts", {source: "backend_extract"})`
4. `personal.fullName` IS protected identity. Source `"backend_extract"` is NOT trusted.
5. → `_syncSuggestOnly` fires → `proj.pendingSuggestions.push({fieldPath: "personal.fullName", value: "Mary Holts", ...})`
6. Returns `false`. `proj.fields["personal.fullName"]` is NEVER written. `bb.questionnaire.personal.fullName` is NEVER written.
7. After 2s, `_debouncedPersist` fires → PUT /api/interview-projections → `projection_json` saved with the suggestion.
8. Pre-restart "what do you know about me" → `compose_memory_echo` → `_build_profile_seed` reads `profile_json` (empty for Mary's name) → returns nothing.
9. **BUT Lori's reply still includes the name** because the chat history (recent turns) is in the LLM's context window. Lori echoes "your name is Mary Holts" from chat memory, not from profile_seed.
10. Pre-restart recall_pre returns `name=True` because the harness regex finds "Mary" or "Holts" in the reply text.
11. Cold restart: new browser context, no chat history.
12. Resume: narrator re-loaded by pid. `projection_json` IS restored to local state via `_loadProjectionFromBackend`. But Lori reads from `profile_json`, which still has nothing.
13. Resume "what do you know about me" → `compose_memory_echo` returns "(not on record yet)".
14. Resume recall_pre returns `name=False`.

**Mary loses identity post-restart because:**
- The candidate IS persisted in `projection_json.pendingSuggestions`
- Lori never reads from `projection_json.pendingSuggestions`
- Chat history is gone post-restart
- Lori has nothing to surface

### Why Marvin retained name+pob in v1 but Mary didn't

Both narrators take the same path (protected identity → suggestion queue). Both should fail equally. The reason Marvin came back True in v1 is harness scoring, not architectural difference:

- Marvin's resume "what do you know about me" reply included words like "Marvin" and "Fargo" (probably from a hallucinated guess or a bleed-through from session-2 chat history that wasn't fully cleared between voices in v1)
- The harness regex finds the tokens in Lori's reply text
- v1 marks Marvin's name=True even though `profile_json` was equally empty

Mary's reply post-restart didn't happen to mention "Mary" or "Holts" or "Minot" by chance, so her recall came back False.

**The asymmetry was scoring noise, not a real architectural difference.** Both narrators have the same broken bridge.

This refines the v1+v2 finding: it's not a "Mary correction-persistence bug" — it's a "no candidate ever reaches profile_json on chat extraction" bug, period.

### Why family_truth has a working pipeline but personal identity doesn't

`family_truth_rows` (status default `'needs_verify'`) and `family_truth_promoted` (canonical) are wired together by an explicit `ft_promote_row()` accessor and an operator review surface. WO-13 Phase 7 built that. But this pipeline is for FAMILY data (parents, siblings, spouse), not for personal identity (fullName, DOB, POB).

Personal identity goes through a DIFFERENT path:
- `identity_change_log` exists with `status='proposed'` default
- BUT chat-extracted personal identity from `_syncSuggestOnly` does NOT write to `identity_change_log` either
- It only writes to `proj.pendingSuggestions` (via projection-sync) and `interview_projections.projection_json` (via persist)

So personal identity has the worst of both worlds: a partially-built proposal table (`identity_change_log`) that nobody writes to, and a fully-built suggestion queue (`projection_json.pendingSuggestions`) that nobody reads from.

---

## What we have vs what we need

### What we have

- ✓ Schema for proposal/promotion patterns: `family_truth_*` (4 layers), `identity_change_log` (proposal), `interview_projections` (suggestion queue), `bio_builder_questionnaires` (BB UI canonical), `profiles` (Lori's read source)
- ✓ Persistence: every layer above survives cold restart
- ✓ WriteMode metadata: extract.py emits writeMode per item (prefill_if_blank / candidate_only / suggest_only)
- ✓ Confidence: extract.py emits per-item confidence
- ✓ Protected identity gate: BUG-312 routes untrusted writes to suggestions
- ✓ family_truth promotion path: working end-to-end for family domain

### What we need

**The missing bridge is from `interview_projections.projection_json.pendingSuggestions` (and `.fields`) into `_build_profile_seed`.**

That's it. One function in `prompt_composer.py` needs to read a second source.

---

## Revised WO-PROVISIONAL-TRUTH-01 scope

### What the WO ACTUALLY needs to do

**Phase A — Read-side bridge (the load-bearing fix):**

Modify `_build_profile_seed(person_id)` in `prompt_composer.py` to:
1. Continue reading `profiles.profile_json` as primary canonical source
2. ALSO read `interview_projections.projection_json` for the same narrator
3. For each bucket, prefer `profile_json` value when present; fall back to `projection_json.fields[*]` value if `profile_json` is empty for that bucket
4. ALSO surface `projection_json.pendingSuggestions` items as provisional values
5. Mark provenance: each value gets a `source` tag — "confirmed" (from profile_json) or "provisional" (from projection_json.fields or pendingSuggestions)
6. Lori's prompt template surfaces both indistinguishably during interview (no narrator-facing distinction); the source tag is for operator-side review only

**Files:** `server/code/api/prompt_composer.py` (one function, ~50 line addition)
**Scope:** ~half day

**Phase B — Verify TEST-23 v3 acceptance:**

Run TEST-23 v3 with the read-bridge landed. Acceptance gates:
- Mary post-restart `name=True pob=True` (was False)
- Marvin spouse_probe hits ≥2 of [wife, widower, letters, drawer, morning] (was 0/5)
- Both narrators' recall surfaces era seeds (was 0/7)

**Scope:** ~half day (run + readout)

**Phase C (OPTIONAL) — Inline shadow-review widget retirement:**

The widget Chris screenshotted is the in-conversation Approve/Correct/Reject popup. Once Phase A lands and provisional truth flows through `_build_profile_seed`, the widget no longer serves its in-session purpose (Lori already uses the suggestion). The widget can be retired from the narrator-facing path and replaced with an asynchronous Bug Panel "Pending Review" tab (which can use the existing pendingSuggestions data — no new schema).

**Files:** `ui/js/shadow-review.js` env-flag-gated, new `ui/js/bug-panel-pending-review.js` (similar pattern to bug-panel-eval.js)
**Scope:** ~1 day if pursued; not strictly required for the data-persistence fix

**Phase D (OPTIONAL) — Auto-promote high-confidence non-protected candidates:**

For non-protected fields (everything except fullName/DOB/POB/preferredName/birthOrder) with confidence ≥ 0.85, auto-promote from projection_json into profile_json on a debounced timer. Reduces operator review burden for routine extractions while keeping protected identity behind explicit operator approval.

**Files:** new `server/code/api/services/auto_promote.py`, hook into chat_ws or scheduled
**Scope:** ~1 day if pursued; can land after Phase A + B prove the read-bridge works

### Total revised scope

| Phase | Estimate | Necessity |
|---|---|---|
| A — Read bridge | ~half day | **REQUIRED** |
| B — TEST-23 v3 acceptance | ~half day | **REQUIRED** |
| C — Widget retirement | ~1 day | optional |
| D — Auto-promote | ~1 day | optional |
| **Required total** | **~1 day** | |
| **Full scope if all phases** | **~3 days** | |

Down from the original ~7-10 working day estimate. The schema migration, the new operator review surface, and the inline widget retirement are all simpler than I assumed because the persistence layer is already there.

---

## Why this audit changes the answer

The original WO assumed:
- BB has per-field rows that need a `status` column
- Schema needs migration `0005_provisional_truth.sql`
- Write path needs to bypass the shadow-review queue
- New operator review surface needs to be built from scratch

The reality is:
- BB lives as a JSON blob; per-field rows already exist in `family_truth_rows` (for family) and `identity_change_log` (for identity proposals)
- `interview_projections.projection_json.pendingSuggestions` IS the provisional layer; it persists across restart
- Write path already routes provisional values to projection_json (BUG-312's gate is the structural firewall)
- Operator review surface for the widget already exists (the popup); what's missing is an asynchronous Bug Panel surface that reads the same data

**The system has all the parts. They just aren't wired together at the read end.**

---

## What the spec gets RIGHT despite the wrong implementation target

The locked principle (CLAUDE.md #5) is correct as written:

> Provisional truth persists. Final truth waits for the operator. The interview never waits.

The principle holds. What changes is the implementation:

- "Provisional truth persists" is ALREADY TRUE (in `interview_projections.projection_json`)
- "Final truth waits for the operator" is TRUE for promoted truth (`profiles.profile_json` is the canonical, populated by template preload + manual promotion paths)
- "The interview never waits" is the load-bearing requirement — and it's currently violated because Lori CAN'T see provisional truth (she only reads `profile_json`)

The fix flips the third clause from broken to working by adding one read source to one Python function.

---

## Recommended next steps

1. **Update WO-PROVISIONAL-TRUTH-01_Spec.md** to replace the schema-migration approach with the read-bridge approach. Phases collapse from 7 to 4 (A-D above).
2. **Implement Phase A** (`_build_profile_seed` reads projection_json fields + pendingSuggestions). ~half day. Add unit tests + integration test.
3. **Run TEST-23 v3** to verify Mary post-restart recall succeeds. If yes, the load-bearing fix is proven.
4. **Decide on Phase C and D** based on TEST-23 v3 results. If provisional values reaching Lori is enough, defer C and D; if low-confidence noise causes problems, land D first; if operator burden is too high, land C.

This audit closes the question Chris raised. The answer to "is the correct target A) family_truth_rows, B) bio_builder_questionnaires, C) new per-field table, or D) hybrid?" is:

**E) None of the above. The data already lives in `interview_projections.projection_json`. Add a read-bridge to `_build_profile_seed`. No new schema. No new tables.**
