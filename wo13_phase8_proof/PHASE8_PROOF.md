# WO-13 Phase 8 — Proof Packet

**Downstream rewiring: flag-gated read seam + hybrid read + cold-start backfill**

Date: 2026-04-11
Harness: `/sessions/nice-fervent-clarke/wo13_test/run_phase8_test.py`
Result: **19 / 19 assertions passed; Phase 4/5/6/7 regressions all green**

---

## 1. Design in one paragraph

Phase 8 rewires the *read* side of the narrative memory pipeline. Phase 7
already made `family_truth_promoted` a real UPSERT-backed table with content
hashing and op classification; Phase 8 makes that table the source of truth
the UI actually reads from — without breaking any narrator who hasn't yet
reviewed their queue. There is **one read seam**: `GET /api/profiles/{id}`.
Every downstream consumer (profile form, obituary identity card, memoir
source name, timeline spine, chat context via `session_payload.profile`)
reads `state.profile` on the client, and `state.profile` is populated from
exactly that one fetch. Collapsing the surface from "five rewires" to
"one flag, one builder, one shim" is the core architectural move of this
phase.

## 2. Surface map (what changed)

| File | Change |
|---|---|
| `server/code/api/flags.py` | **NEW.** Shared `truth_v2_enabled(consumer)` helper. One place to read `HORNELORE_TRUTH_V2` and `HORNELORE_TRUTH_V2_PROFILE`. |
| `server/code/api/db.py` | **NEW functions.** `_PROMOTED_TO_BASICS` mapping, `build_profile_from_promoted()`, `ft_backfill_from_profile_json()`. |
| `server/code/api/routers/profiles.py` | Flag-gated read in `api_get_profile` with try/except `legacy_fallback` path. Adds `source` diagnostic key. |
| `server/code/api/routers/facts.py` | `_truth_v2_enabled()` now delegates to the shared helper. Behaviour unchanged. |
| `server/code/api/routers/family_truth.py` | **NEW endpoint.** `POST /api/family-truth/backfill` — seeds shadow notes + `needs_verify` proposal rows from an existing `profile_json`. |
| `ui/js/app.js` | **NEW.** `window.lvxRefreshProfileFromServer(pid)` — re-fetches profile and repopulates `state.profile`, obit card, memoir source name, timeline, and session payload after a promote. |
| `ui/js/wo13-review.js` | `wo13PromoteClicked` calls the refresh shim after a successful bulk promote. |

## 3. The single read seam

```
┌──────────────────────────────────────────────────────────────────────┐
│  GET /api/profiles/{person_id}                                       │
│                                                                      │
│  if HORNELORE_TRUTH_V2_PROFILE:                                      │
│      try:                                                            │
│          profile = build_profile_from_promoted(person_id)            │
│          source = "promoted_truth"                                   │
│      except Exception:                                               │
│          profile = legacy_blob        ◄── defensive; never 500s      │
│          source = "legacy_fallback"                                  │
│  else:                                                               │
│      profile = legacy_blob                                           │
│      source = "legacy"                                               │
└──────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
        state.profile ─► profile form, obituary card, memoir source,
                         timeline spine, session payload (chat context)
```

The client never reads from `family_truth_*` directly. The server never
composes downstream deliverables from anything but `state.profile`. One
endpoint, one flag, one code path.

## 4. Builder contract (`build_profile_from_promoted`)

Input: `person_id`.
Output: dict in `profile_json` shape (`basics`, `kinship`, `pets`).

Rules, in order:

1. Load the legacy blob unconditionally — this is the passthrough layer.
2. If there are zero rows in `family_truth_promoted` for this person,
   return the legacy shape verbatim (no sidecar keys added). This is the
   **empty-promoted fallback** — a flag-flip on an unreviewed narrator
   produces the same output as flag-off.
3. Otherwise, walk the promoted rows:
   - If the row's `field` is one of the five protected identity fields
     (`personal.fullName`, `personal.preferredName`, `personal.dateOfBirth`,
     `personal.placeOfBirth`, `personal.birthOrder`), write the value
     directly into `basics.<mapped key>` via `_PROMOTED_TO_BASICS`.
   - Otherwise, append the row to `basics.truth[]`.
   - If `qualification` is non-empty (approve_q path), index it in
     `basics._qualifications[<field>]`.
4. Return `{basics, kinship, pets}`. `kinship` and `pets` are pure
   passthrough.

The two sidecar keys (`basics._qualifications`, `basics.truth[]`) are
**additive** — `normalizeProfile` on the client tolerates extra keys, so
legacy narrators are unaffected.

## 5. Cold-start: `ft_backfill_from_profile_json`

Problem: the moment `HORNELORE_TRUTH_V2_PROFILE` flips on, a narrator who
has never touched the review queue would see an empty promoted-truth set.
The empty-promoted fallback solves the rendering problem, but the reviewer
still needs *something to approve*.

Solution: the backfill endpoint seeds the proposal layer from the legacy
blob. For each non-empty mapped protected field on `basics.*`, it creates
a shadow note (`source_kind='backfill'`) and a `needs_verify` proposal row
(`extraction_method='manual'`, `confidence=1.0`). Nothing is auto-promoted.
The reviewer then walks the queue in the Phase 6 drawer exactly as they
would for any other narrator.

Guarantees:
- **Idempotent** on the `(subject_name, field)` key. Re-running on a
  partially-reviewed narrator creates zero duplicates.
- **Reference narrators are refused** with a `reference_refused=true`
  return at the db layer and a 403 at the router.
- **Never touches `family_truth_promoted`.** Promoted truth stays reviewer-authored.

## 6. Test evidence (19 / 19 PASS)

```
==============================================================
WO-13 Phase 8 — Downstream rewiring (flag seam + hybrid read)
==============================================================
  OK  flags: truth_v2_enabled('facts_write'|'profile'|unknown) honours env
  OK  seed: Ada (live) + Shatner (reference) + legacy profile_json
  OK  builder: zero promoted rows → returns legacy shape verbatim
  OK  seed: promoted truth populated for Ada (2 protected + 2 freeform; 1 blocked)
  OK  builder: 5 protected basics.* fields — promoted wins, legacy fills gaps
  OK  builder: free-form rows land in basics.truth[] with subject/relation/value/status
  OK  builder: qualification surfaces in basics._qualifications[<field>]
  OK  builder: rules_fallback-blocked protected field never leaks into output
  OK  builder: unmapped basics.*, kinship, pets pass through under the flag
  OK  endpoint: flag OFF → source='legacy', no promoted sidecar
  OK  endpoint: flag ON → source='promoted_truth' + sidecar + passthrough
  OK  endpoint: builder exception → source='legacy_fallback', no 500
  OK  backfill: seeds 4 needs_verify rows + 1 skipped_empty; promoted empty
  OK  backfill: idempotent — second call creates 0, skips 4 existing
  OK  backfill guards: db returns reference_refused; router raises 403
  OK  reference narrator: profile read under flag falls through to legacy data
  OK  regression: Phase 4 /facts/add 410 Gone still enforced via shared flag helper
  OK  end-to-end trace: saved to phase8_e2e_trace.json
  OK  regression: FT tables present, protected set unchanged, UPSERT still idempotent

==============================================================
  WO-13 Phase 8 — ALL ASSERTIONS PASSED
==============================================================
```

### End-to-end trace (Ada Lovelace fixture)

Legacy blob seeds five protected basics + seven unmapped basics + kinship
+ pets. Promoted truth is then seeded with:

- `personal.preferredName = "Ada"` (manual) → created
- `employment = "Collaborated with Charles Babbage..."` (manual, approve_q
  with qualification "Exact dates of the collaboration are disputed...") → created
- `personal.dateOfBirth = "1815-12-10"` (rules_fallback) → **blocked**
- `residence = "Lived in London, England."` (manual) → created

Result with `HORNELORE_TRUTH_V2_PROFILE=1`:

| Field | Value in response | Source |
|---|---|---|
| `basics.preferred` | "Ada" | promoted_truth |
| `basics.fullname` | "Augusta Ada King-Noel" | legacy passthrough |
| `basics.dob` | "1815-12-10" | legacy passthrough (promoted attempt was blocked) |
| `basics.pob` | "London, England" | legacy passthrough |
| `basics.birthOrder` | "only" | legacy passthrough |
| `basics.culture` | "English" | legacy passthrough (unmapped) |
| `basics.country` | "United Kingdom" | legacy passthrough (unmapped) |
| `basics.truth[0]` | residence | from promoted truth |
| `basics.truth[1]` | employment (approve_q) | from promoted truth |
| `basics._qualifications.employment` | "Exact dates of the collaboration are disputed..." | from promoted truth |
| `kinship` | 2 entries | legacy passthrough |
| `pets` | 1 entry | legacy passthrough |

The blocked `personal.dateOfBirth` never leaks into `basics.truth[]` or
`basics._qualifications` — the Phase 7 UPSERT gate held, and the builder
has nothing to surface.

### Cold-start backfill (Lord Byron fixture)

Fresh narrator with legacy blob: `fullname`, `preferred`, `dob`, `pob` set;
`birthOrder` empty. One call to `ft_backfill_from_profile_json`:

```json
{
  "created_rows": 4,
  "skipped_existing": 0,
  "skipped_empty": 1,
  "reference_refused": false
}
```

All four rows written as `status='needs_verify'`, `extraction_method='manual'`,
`subject_name='George Gordon Byron'`, `relationship='self'`. Zero rows in
`family_truth_promoted`. Second call returns `created_rows=0, skipped_existing=4` —
fully idempotent.

### Reference-narrator guard (Shatner)

- `H.ft_backfill_from_profile_json(shatner_id)` → `{reference_refused: true, created_rows: 0}`. `family_truth_rows` count for Shatner remains 0.
- `ft_router.api_backfill(BackfillRequest(person_id=shatner_id))` → `HTTPException(403)`.
- `api_get_profile(shatner_id)` with flag on → returns legacy blob (empty-promoted fallback inside the builder), `source='promoted_truth'`, no 500, no sidecar keys.

## 7. Regression matrix

| Phase | Suite | Result |
|---|---|---|
| 4 | `run_phase4_test.py` (facts-write freeze + reference guard) | 18 / 18 PASS |
| 5 | `run_phase5_test.py` (rolling-summary filter, WO-9 legacy drop) | 16 / 16 PASS |
| 6 | `run_phase6_test.js` (review drawer JS + CSS + routing) | 83 / 83 PASS |
| 7 | `run_phase7_test.py` (UPSERT, idempotency, block, bulk) | 23 / 23 PASS |
| 8 | `run_phase8_test.py` (flag seam, hybrid read, backfill) | **19 / 19 PASS** |

Total: **159 / 159** across five suites with both flags OFF by default.

## 8. Rollout recipe

1. Land the Phase 8 commit with `HORNELORE_TRUTH_V2_PROFILE` **unset** in
   production. Every narrator still gets `source='legacy'` — zero risk.
2. Pick one live narrator (e.g. Kent). Call
   `POST /api/family-truth/backfill` with `{person_id: kent_id}`. This
   seeds `needs_verify` rows from their current `profile_json`.
3. Review the queue in the Phase 6 drawer. Approve the five protected
   identity fields you recognize; qualify the ones you don't; reject the
   ones that are wrong.
4. Click "Promote approved". The review drawer calls
   `wo13PromoteApproved`, then `wo13PromoteClicked` triggers
   `lvxRefreshProfileFromServer(kent_id)` — the profile state is re-read
   from the server and every downstream surface updates without a page
   reload. At this point the flag is still off, so
   `GET /api/profiles/{kent_id}` returns `source='legacy'` but the
   promoted-truth rows are sitting in the table waiting for the flip.
5. Flip `HORNELORE_TRUTH_V2_PROFILE=1` in this one narrator's process.
   Their profile now returns `source='promoted_truth'`. If anything goes
   sideways, the builder's try/except hands back
   `source='legacy_fallback'`; if that's not enough, unsetting the env
   var returns to the Phase 7 state in one restart.
6. Expand to the full narrator set once Kent is stable.

No changes to chat prompt composition are needed. Chat context is
hydrated from `session_payload.profile`, which is populated from
`state.profile`, which came from the single read seam. Shadow notes and
proposals are structurally invisible to the prompt composer — they live
in different tables that `build_profile_from_promoted` does not read.

## 9. Files in this proof

- `PHASE8_PROOF.md` — this document
- `../wo13_test/run_phase8_test.py` — harness (19 assertions)
- `../wo13_test/data/phase8_e2e_trace.json` — machine-readable e2e trace
