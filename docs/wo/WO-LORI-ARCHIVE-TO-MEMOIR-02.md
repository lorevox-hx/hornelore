# WO-LORI-ARCHIVE-TO-MEMOIR-02

**Status:** CURRENT — central Lori/Lorevox work order  
**Supersedes:** `WO-LORI-END-TO-END-LISTEN-RETAIN-MEMOIR-01`  
**Starting evidence:** demographic cohort `20260901T015343Z` and Walt seven-era run `20260901T003329Z`  
**Current position:** **Phase 0, 1, 2 and 3 CLOSED. Phase 4 is the CURRENT ACTION** —
durably attach story-capture decisions and diagnostics to their source turns, **including
turns that produce no candidate**. *(Phase 1 proof: mutations `20260904T123556Z`, carried
forward at zero mutations in `20260904T130525Z`, exit 0. Phase 2 audit: `python3
scripts/phase2_verify_ledger.py`. Phase 3 live gate: Stefi correction-fallthrough
`20260905-021741`, 9/9 over the production WebSocket.)*
**Phase 0:** accepted by ChatGPT against pushed commit `fdaa255`

## 1. Goal

Make Lorevox turn a person’s spoken life story into a faithful, reviewable memoir without losing the narrator’s voice or inventing relationships.

The required product chain is:

```text
Narrator speaks
→ exact words are archived
→ Lori responds naturally
→ people, events and eras are interpreted accurately
→ uncertain interpretations remain reviewable
→ memoir-worthy passages become story candidates
→ the operator reviews them
→ approved passages reach canonical memoir, preview and export
```

Lorevox is not accepted merely because a transcript exists, an endpoint returns 200, a UI tab opens, or a harness reports PASS. Acceptance requires the narrator’s material to remain accurate and to reach the memoir when approved.

## 2. Non-negotiable rules

- The exact narrator statement remains archived verbatim.
- Extraction organizes the archive; it never replaces the archive.
- `archived` does not mean `memoir_reachable`.
- Fact candidates and story candidates are separate products.
- A schema or validator may decide destination, but may not silently erase meaningful interpretation.
- Numeric model confidence is not proof that a relationship was bound correctly.
- Uncertain facts remain attributed to their source turn and reviewable.
- Memoir-worthy narration must not depend only on travel-chain or multi-place heuristics.
- Only operator-approved stories become canonical memoir evidence.
- Every memoir passage must trace back to the narrator’s archived words.
- Response tracing is enabled only during bounded synthetic evaluation.
- Safety expansion, camera, Travel Document, Spanish expansion, mutation campaigns and unrelated audits are out of scope.

## 3. Verified baseline

### Working

- [x] 10 demographic synthetic narrators completed.
- [x] 38/38 narrator statements were archived verbatim.
- [x] 76/76 Lori responses completed with TTS.
- [x] All ten durable transcripts were complete.
- [x] TXT, JSON and session archives were produced.
- [x] Era routing matched the selected era.
- [x] The Life Map seven-era path completed for Walt.
- [x] Story candidates preserve source-turn binding when created.
- [x] Operator story-review PATCH actions have been used historically.
- [x] Canonical memoir code selects promoted or memoir-only stories and approved trip notes.
- [x] Current response traces contain 10 cohort narrator IDs, 0 non-cohort IDs and 0 non-cohort records.

### Defective or incomplete

- [x] **CORRECTED 2026-09-04: candidate presence is 35 of 38 (92.1%), not 11 of 38.** The
      `11` was **eleven operator PATCH actions in the API log**, dated 08-18/19/20 on other
      narrators, welded to the cohort's 38 statements. Never a coverage measurement. See the
      Phase 2 ledger.
- [x] **CORRECTED 2026-09-04: THREE turns produced no candidate, not twenty-seven** — `1846` (John), `1864` (Frank), `1870` (Stefi).
- [x] **CORRECTED 2026-09-04: Pat's account of Jim's death is NOT `archived_only`.** Turn `1852` produced candidate `f130549c` (472 words, `borderline_scene_anchor`), transcript byte-identical to the statement. It is `story_candidate_provisional` — captured and awaiting review, not lost.
- [x] **CORRECTED 2026-09-04: reviewing every existing candidate would make 35 of 38 statements memoir-eligible.** All 35 are `unreviewed`. *(Capture was never the central bottleneck. The two real capture defects are that the factual-chain decision is not persisted and the extraction ledger was never written — see the Phase 2 closeout.)*
- [ ] Stefi’s clarification was misrouted as a correction and received form instructions.
- [ ] Stefi’s route bypassed normal response tracing, extraction and story capture.
- [ ] Pat’s husband Jim, Mable’s husband Otis and Tomasita’s husband Domingo were bound or proposed under `parents.*`.
- [ ] Incorrect relationship bindings carried high model confidence.
- [ ] Family wording such as `daddy`, `mama`, `ex-spouse`, `adult child` and qualified siblings can be rejected after being understood.
- [ ] Thirty of 76 delivered responses were changed after generation.
- [ ] Post-generation controls exposed reasoning, UI labels, fragments or inferior anchors.
- [ ] Accepted extraction items have not been joined to their final durable destinations.
- [ ] Rolling-summary retention is demonstrated but accuracy, duplication and topic placement are not accepted.
- [ ] Life Map fact placement is not measured.
- [x] **Promotion → canonical → preview → export PROVEN end to end 2026-09-04.** Mutations in
      `20260904T123556Z`; proof carried forward at **zero mutations** in `20260904T130525Z`,
      exit 0, agreement 1/1/1, control unchanged. *One passage — this is NOT a coverage claim.*
- [ ] Future demographic checkpoints still need their own durability and artifact fields verified from code.

## 4. Status vocabulary

Every material unit must end with one explicit status:

| Status | Meaning |
|---|---|
| `archived_only` | Exact narration exists, but no structured or memoir-reachable representation exists. |
| `structured_correctly` | A verified interpretation reached the correct field/person/era. |
| `structured_incorrectly` | An interpretation reached the wrong field, person or era. |
| `fact_candidate` | Meaningful interpretation is preserved for review but is not canonical. |
| `story_candidate_provisional` | Coherent passage is reviewable but not memoir eligible. |
| `story_candidate_approved` | Operator approved the story. |
| `memoir_eligible` | Canonical memoir source can retrieve it. |
| `invalid_inference_rejected` | Unsupported inference was rejected with a recorded reason. |
| `processing_bypassed` | A product route skipped normal response/extraction/story processing. |
| `lost` | Neither archived source nor recoverable representation exists. |
| `not_measured` | No instrument attempted this stage. |
| `measurement_failed` | The measurement was attempted but failed. |

`rejected`, `discarded`, `saved` and `persisted` must not appear alone in reports. They require a destination and one of the statuses above.

# 5. Work phases

Only one phase may be active at a time. Each phase ends with a pushed commit or a read-only evidence report and an explicit gate decision.

## Phase 0 — Close and freeze the evaluation

**Outcome:** Temporary instrumentation is off, baseline evidence is preserved, and future reports are self-contained.

- [x] Set `HORNELORE_RESPONSE_TRACE=0` for ordinary stack startup.
- [x] Restart and verify `/api/health/response-trace` reports `enabled:false`.
- [x] Record current trace exposure numerically: 10 cohort IDs; 0 non-cohort IDs; 0 non-cohort records.
- [x] Preserve existing synthetic trace and cohort artifacts without deletion.
- [x] Verify future checkpoints record `durableComplete`, downloaded ZIP name, downloaded operator report name and `uiFindings` from the runner itself.
- [x] Preserve the original and rebuilt historical checkpoints distinctly.

**Exit gate:** Trace is off; evidence is preserved; a newly constructed offline checkpoint contains all required fields.

**CLOSED.** Accepted by ChatGPT against pushed commit `fdaa255`, reviewed from
`origin/main` rather than from the completion report. Live startup printed
`Response trace: off` and `/api/health/response-trace` returned
`enabled:false` with `output_dir_exists:true` — instrumentation off, evidence
preserved rather than cleaned up.

## Phase 1 — Prove the existing memoir chain

**Outcome:** Determine whether today’s implemented chain can render and export one approved synthetic story.

Use one coherent existing provisional candidate. Do not create another narrator and do not change story-capture rules in this phase.

### Runtime era is not a story placement (established 2026-09-01)

The first live run, `20260901T212134Z`, **refused before promoting** and was
right to. Its precondition demanded that target `447eee18` already sit in
`building_years`; the candidate's own record read `era_candidates: []`,
`placement_source: "unknown"`, no year range. Nothing was mutated, the control
was verified identical, and the run exited non-zero. **That run is preserved
unchanged as the evidence for this section.**

The refusal exposed a distinction this work order had blurred, and every later
phase depends on keeping it:

| | What it is | Where it lives |
|---|---|---|
| **Runtime era** | the era the conversation was in when the narrator spoke | the turn / Life Map selection |
| **Story placement** | the era an operator has *confirmed* the story belongs to | `era_candidates` + `placement_source` on the candidate |

`story_preservation.preserve` writes every candidate with `era_candidates=[]`
and `placement_source=None` (`story_preservation.py:225`). That is **deliberate,
not a gap.** Deriving a placement from whichever screen the narrator happened to
be on is exactly how a story gets filed into the wrong memoir chapter, and
`story_projection` already refuses it: an era candidate nobody confirmed is not
a placement. The route enforces the same rule from the other side — *"an
operator-set placement needs exactly one era; two eras is not a placement, it is
a pair of guesses"* (`operator_story_review.py:366`).

**Consequence for the memoir, and for Phase 2:** a candidate can be promoted and
still reach canonical memoir **unplaced**. Promotion decides whether a story is
*eligible*; placement decides where it *goes*. Phase 2's ledger must record them
as two separate destinations, never one.

### The operator workflow under test — ALL PERFORMED AND VERIFIED

*(Checked 2026-09-04. Placement and promotion were performed in `20260904T123556Z`;
canonical, preview, export and agreement were proven at zero mutations in
`20260904T130525Z`. See the acceptance record above.)*

Phase 1 therefore exercises **two authorised mutations**, in order, both through
the real Bug Panel controls and both against the same `PATCH
/api/operator/story-candidates/{id}` endpoint:

- [x] Record candidate ID, narrator ID, conversation ID, source-turn IDs, exact passage — and the **absence** of a placement.
- [x] Open the real Operator review surface.
- [x] **Place** through the real era control, then `Save placement / notes`. Selecting an era *is* the operator placement: the control writes `placement_source=operator_set` in the same gesture, and `operator_set` is deliberately not hand-selectable from the source dropdown.
- [x] Confirm the candidate now carries `building_years` as its **sole** era with `placement_source=operator_set`, that the review version advanced, and that `review_status`, transcript and provenance are untouched.
- [x] **Refetch the row** so the panel carries the new version. `applyReview` sends the version it last rendered; promoting without refetching sends a stale version and takes a 409.
- [x] Promote through that row's real Promote control, at the version the placement returned.
- [x] Confirm status becomes `promoted` without losing provenance **or the placement**.
- [x] Query canonical memoir from the correct API origin.
- [x] Confirm the exact passage appears once with correct narrator and era.
- [x] Open normal memoir preview.
- [x] Export the memoir document.
- [x] Compare canonical response, preview and export.
- [x] Confirm all three contain the passage exactly once.
- [x] Confirm no incorrect structured family fact is substituted into the passage.

## ✅ PHASE 1 ACCEPTED — the full chain is proven (2026-09-04)

**The proof is TWO runs, and the division between them is the point.**

| Run | What it did | Mutations |
|---|---|---|
| `20260904T123556Z` | **Performed the only two authorized mutations** — placement `v1→v2`, then promotion `v2→v3`, in that order, through the real operator controls | **2** (`placement>promotion`, both conforming) |
| `20260904T130525Z` | **Carried that proof forward and completed preview and export.** Re-read the candidate, re-verified the placement and provenance against the prior report, and traversed canonical → preview → export | **0** |

> **The resume did NOT place and did NOT promote.** It entered mode `promoted` with a PATCH
> budget of **0**, observed **0**, recorded no blocked PATCHes and no refusals. `3a_placed`
> reads `carried_forward`, not `PASS`, precisely so this can never be misread. Any statement
> that the successful run performed the mutations is wrong.

`20260904T130158Z` produced the same passing result an hour earlier on a marginally
different instrument; `130525Z` reproduced it on the fallback-free `PANEL_STATE` that
ships. Both are preserved.

**Exit gate met.** Exit code **0**, `Phase 1: PASS — full chain proven`.

| Link | Result |
|---|---|
| placement | `carried_forward` from `20260904T123556Z`, re-verified live |
| placement verified | **PASS** — sole era `building_years`, `operator_set`, provenance unchanged |
| promotion | **PASS** — `promoted`, placement survived |
| canonical API | **PASS** — occurrences **1**, `era=building_years`, `source_id=5d57a43ce780`, `complete=true`, `lane=read` |
| preview | **PASS** — `:popover-open` true, occurrences **1**, 1408 chars |
| export | **PASS** — `lorevox_memoir_…__pat_structured.docx`, 36,975 bytes, occurrences **1**, `bodyPersonIsPat=true` |
| agreement | **PASS** — canonical **1** / preview **1** / DOCX **1** |
| control `5a56f942` | **PASS** — item identical; the changing `fetched_at` envelope is excluded by design |

**Supporting gates:** 141 Python tests (zero skips on `.venv`) and all four DOM suites —
launcher, memoir popover, placement workflow, row selection.

**Two contract guarantees held, and both are worth recording:**

- `containsSourceId: false` — **no raw UUID reached the document.** `memoir_contract`
  requires that a raw narrator or candidate id "must not appear in a document a family
  reads", and the export honoured it.
- `forbidden: []` — **none of the known bad substitutions reached the document.** The
  relationship-misbinding defect (`Jim` bound under `parents.*`) did not leak into this
  passage's export.

### Two defects were corrected to reach this, one product and one harness

**PRODUCT — relative canonical origin.** `ui/hornelore1.0.html` fetched
`/api/memoir/canonical` with a bare relative URL, resolving against the UI static server on
`:8082`, which does not proxy `/api/*`. Three UI-issued 404s were observed live while the
identical query against the API origin returned 200. Same class as **BUG-224**, fixed
2026-05-01 in the Bug Panel modules and missed in the page's own inline script. Corrected
to the documented `ORIGIN` pattern from `api.js`; a regression guard now refuses any bare
relative `/api` fetch anywhere in the page.

**HARNESS — `offsetParent` used to test popover visibility.** `PANEL_STATE` treated
`offsetParent !== null` as visible. `#memoirScrollPopover` is `<div popover="auto">`; native
popovers render in the top layer at `position: fixed`, where `offsetParent` is always
`null` — a guaranteed false negative on an **open** panel. It reported the memoir shut while
reading 1,408 characters of the passage out of it. Now gated on `:popover-open` alone, with
no fallback basis.

### What Phase 1 does NOT claim

It proves **one** passage completes the chain. It says nothing about the other 27
archived-but-uncaptured statements, nothing about capture granularity, and nothing about
whether the memoir would be *right* at scale. Those are Phase 2's subject. The value of
this result is that the chain exists and is traversable — every later finding is now a
question of coverage and correctness rather than of whether the road is there at all.

### Every defect found while proving it

| Defect | Where | Fixed by |
|---|---|---|
| Runtime era treated as story placement | probe precondition | reversed; became permanent doctrine |
| Bug Panel launcher id did not exist | probe | `#lv10dBugBtn`, gated on `:popover-open` |
| Story rows unaddressable by identity | **product** | `data-story-candidate-id` on the operator row |
| Canonical fetched from a relative URL | **product** | BUG-224 pattern, `ORIGIN` from `api.js` |
| `NameError` on the safety-routed path | **product** | `_safety_path` locals initialized |
| Resume expected the placement's version after a promotion | probe | derived per mode |
| `offsetParent` used to test a native popover's visibility | probe | `:popover-open` alone |

**Mutation budget.** Exactly two PATCHes to the target in a fresh run —
placement then promotion, in that order — and none to any other candidate.
The budget is enforced in-flight: a third PATCH, a wrong order, or a foreign
candidate is aborted before the request leaves the browser and the run exits
non-zero. Control candidate `5a56f942` must be **item-identical** afterwards — the
always-changing `fetched_at` envelope is excluded by design — checked in `finally` so a
crash cannot skip it.

**Resumability.** A resumed run's mode is read from the **named prior report**,
never from the database: a row that is already placed or promoted says nothing
about who did it or against which provenance, and a probe that accepts the row's
own state as proof of its own prior work can be satisfied by any mutation from
any source. Three states, with the PATCH allowance that makes each one a
guarantee rather than an intention:

| Prior report proves | Mode | PATCH budget |
|---|---|---|
| nothing (fresh run) | `full` | 2 — place, then promote |
| placement only | `placed` | 1 — promote only |
| placement and promotion | `promoted` | **0** — verify and continue downstream |

Every resumed run re-verifies the prior report's exact provenance *and* its exact
placement before skipping any step.

**Exit gate:** One passage completes `archive → provisional story → operator
placement → operator promotion → canonical memoir → preview → export`, or the
precise broken link is identified and corrected before proceeding.

**A refusal is a result.** A run that stops before mutating, names the failing
link and exits non-zero has done its job; it is not a failed attempt to be
retried until it passes. Run `20260901T212134Z` is the reference example.

## Phase 2 — Build the 38-turn destination ledger

**Outcome:** Account for what happened to every cohort statement and every meaningful interpretation before changing extraction or capture.

This is a read-only rebuild from existing evidence. Do not rerun the cohort.

For each of 38 narrator statements record:

- [ ] Exact narrator text, narrator, conversation, client turn and durable row IDs.
### PHASE 2 LEDGER BUILT — and it overturns this work order's headline defect (2026-09-04)

**Ledger:** `docs/reports/PHASE2_38_TURN_SPAN_LEDGER_20260904.json` — read-only, built from
the live DB. **The cohort was NOT rerun.**

#### `11 of 38` was never a coverage measurement

The figure came from `MEMOIR-PATH-FINDING.md`, which says: *"**11** review actions ever
applied (`PATCH /api/operator/story-candidates/{id}`) … those 11 actions fall on 2026-08-18,
08-19 and 08-20"* — **eleven operator PATCHes in the API log, on other narrators, eleven
days before the cohort existed.** It was welded to the cohort's 38 statements to make a
ratio. The two numbers were never about the same thing.

Every downstream claim inherited the error: *"twenty-seven turns were archived but produced
no reviewable story candidate"* is wrong by an order of magnitude, and *"story capture is
the central bottleneck"* was never demonstrated.

#### What the data actually shows

| Metric | Result |
|---|---|
| Narrator statements | **38** |
| **Candidate presence** | **35 / 38 — 92.1%** |
| **Independently addressable statement coverage** | **35 / 38 — 92.1%** |
| **Over-capture / aggregation** | **0** |
| **Duplicate or containment groups** | **0** |
| **Unreachable archived statements** | **38 / 38** |

**Capture is exactly faithful.** All **35/35** candidate transcripts are byte-identical to
their source user turn — zero strict subsets, zero strict supersets, one candidate per
statement. Presence and independently-addressable coverage are therefore the *same number*,
which is what a clean 1:1 capture looks like.

Only **three** statements produced no candidate: turns `1846` (John), `1864` (Frank),
`1870` (Stefi). Those three, not twenty-seven, are the capture gap.

#### Review is unexercised — but that does NOT make mass review the next action

**92% captured. 0% reviewed. 0% memoir-reachable.** All 35 candidates are `unreviewed`, so
none satisfies `STORY_MEMOIR_ELIGIBLE`. Phase 1 proved the review path works, so this is
unexercised rather than blocked.

**That is not a reason to work the queue.** These candidates preserve their words exactly
while potentially carrying **invented family relationships** — husbands bound under
`parents.*` — and dropped kinship wording. **A preserved story with a wrong relationship is
not a faithful memoir**, and promoting it would carry the error into canonical output.
Meaning integrity (Phase 3) comes before review volume. The cohort is synthetic test
material besides: its queue is worth nothing to curate.

#### A correction to this document's own 2026-09-04 entry

An earlier version of this section claimed *"capture granularity is not stable — the same
content chunked at roughly 12× different scale"*, comparing Pat's ~450-word cohort
candidates to her 38-word switch-session ones. **That was wrong, and the ledger disproves
it.** Capture was 1:1 and exact in BOTH runs. The size difference is a property of the
SCRIPT: cohort statements are 230–551 words (median **441**) because the synthetic narrator
speaks in long monologues, while the switch-session statements were single sentences.
Capture faithfully mirrored each. The containment observed between Pat's runs
(`447eee18` ⊂ `6f2df375`) is the same content said twice at different lengths in two
different conversations — not two chunkings of one narration.

**The span-aware ledger is still the right instrument.** It is what proved granularity
stable rather than unstable, and what separated an eleven-PATCH log line from a coverage
figure. Keep every metric below; they simply report better news than expected.

### The ledger is SPAN-AWARE — required per row

- [ ] Narrator statement / turn.
- [ ] Candidate ID.
- [ ] Candidate word count.
- [ ] Source session and source-turn range.
- [ ] Number of narrator statements the candidate covers.
- [ ] Span class: `atomic` · `multi-turn` · `aggregate`.
- [ ] Contained-by / contains / overlaps candidate IDs.
- [ ] Placement state and promotion state, **recorded separately** (see Phase 1).
- [ ] Canonical memoir reachability.

### The ledger reports FIVE separate metrics — never one number

- [x] **Candidate presence** — **35/38 (92.1%)**. *(`11/38` was never this metric, or any metric: it was eleven operator PATCHes in the API log.)*
- [x] **Independently addressable statement coverage** — **35/38 (92.1%)**. Identical to presence, because every candidate is exactly its own statement.
- [x] **Over-capture / aggregation** — **0**. No candidate transcript is a strict superset of its source statement.
- [x] **Duplicate and containment groups** — **0** within the cohort.
- [x] **Unreachable archived statements** — **38/38**. All 35 candidates are `unreviewed`, so none satisfies `STORY_MEMOIR_ELIGIBLE`. *(Unexercised, not blocked: Phase 1 proved the path works. **Do not read this as a mandate to review the queue** — the candidates may preserve words exactly while carrying wrong relationships, so meaning integrity comes first.)*

**Sequencing:** the finalized ledger is built **after** the Phase 1 live run. Phase 1 moves
`447eee18` from unplaced/unreviewed to placed/promoted, so a ledger completed first would
have a stale destination state on the day it was written.

- [ ] Selected era and era actually sent. **Record the runtime era and the story placement separately** — see Phase 1. A candidate with no `placement_source=operator_set` is UNPLACED regardless of which era the conversation was in, and the ledger must not collapse the two.
- [→] Raw Lori response, each transformation and delivered response. **→ TRANSFERRED to Phase 6** — not done in Phase 2.
- [→] Every extracted entity, relationship, path, value and source wording. **→ TRANSFERRED to Phase 3 + Phase 5** — not done in Phase 2.
- [→] Every normalization, reroute, acceptance and rejection reason. **→ TRANSFERRED to Phase 5** — not done in Phase 2.
- [→] Final structured destination, if any. **→ TRANSFERRED to Phase 5** — not done in Phase 2.
- [→] Fact-candidate destination, if any. **→ TRANSFERRED to Phase 5** — not done in Phase 2.
- [ ] Story-candidate ID/status, or the exact reason no candidate was created.
- [→] Rolling-summary representation. **→ TRANSFERRED to Phase 8** — not done in Phase 2.
- [→] Chronology and Life Map destinations. **→ TRANSFERRED to Phase 8** — not done in Phase 2.
- [ ] Memoir eligibility and provenance.
- [→] One terminal status from Section 4 for each meaningful item. **→ TRANSFERRED to Phase 5 (turn-level done; item-level owed)** — not done in Phase 2.

Required aggregate totals:

- [ ] 38 statements accounted for.
- [x] **35** current story candidates independently reproduced *(was written as 11 — that was eleven operator PATCH actions in the API log, never a candidate count)*.
- [x] **3** no-candidate turns — `1846`, `1864`, `1870` — reproduced **and classified:
      `measurement_failed`.** *(This said "classification still owed: each needs a
      defensible, inspectable `not_story` reason." That is unsatisfiable and was removed:
      the deciding signal — the factual-chain result — is persisted nowhere, so no
      evidence-backed `not_story` reason can exist. `measurement_failed` IS the defensible
      classification. A `not_story` reason becomes possible only after Phase 4 persists the
      capture decision.)*
- [→] Pat, Stefi, Mable, Tomasita, Richard, Joe and Frank explicitly reviewed. **→ TRANSFERRED to DECLINED — synthetic; real-narrator validation in Phase 8** — not done in Phase 2.
- [→] The final destinations of the previously reported accepted extraction items identified. **→ TRANSFERRED to Phase 5** — not done in Phase 2.

**Exit gate:** No statement or interpretation is represented merely as `persisted`; the ledger names its real destination, lack of destination or measurement failure.


## ✅ PHASE 2 CLOSED — mechanism audit complete (2026-09-04)

**Read-only throughout. The cohort was not rerun, no candidate was curated, no threshold
was touched.** Reproduce with `python3 scripts/phase2_verify_ledger.py`.

### The classifier split — measured by running the SHIPPED trigger over all 38 turns

No cohort turn reached `full_threshold`: these narrators typed, so `audio_duration_sec = 0`
and that path requires ≥ 30 s. Capture therefore rested on two mechanisms:

| Decision path | Turns | Candidate created |
|---|---|---|
| **Deterministic** — `anchors ≥ 3` → `borderline_scene_anchor` | **18** | 18 |
| **Factual-chain classifier** — `chain_ctx["is_factual_chain"]` | **20** | **17** |
| — of which the chain was silent | 3 | **0** |

`story_trigger.classify_story_candidate` reproduces all 18 deterministic decisions from the
stored text alone. It reproduces **none** of the other 20 without runtime chain context.

### Turns `1846`, `1864`, `1870` — `measurement_failed`, NOT `not_story`

They are **indistinguishable from captured turns on every stored signal**: all three have
`anchor_count = 2`, `place_anchor = true`, `person_anchor = true`, `time_anchor = false`,
236–536 words. Captured turns `1830`, `1832`, `1836`, `1840`, `1850`, `1856` carry the
identical profile.

The only differing input is the factual-chain result, and **that decision is persisted
nowhere** — not in `turns.meta_json` (empty for all three), not in `chain_meta_json`, not in
any ledger. No evidence-backed `not_story` reason exists, so none is recorded. Inventing one
would be fabrication.

### DEFECT — the deciding signal for 53% of story capture leaves no audit trail

`trigger_diagnostic()` already computes exactly the required numbers and is never persisted.
**For any turn — captured or missed — nobody can say why the classifier decided as it did.**
This is not a synthetic-cohort problem: if a story of Kent's or Janice's is missed, there is
today no way to find out why. **Fixed in Phase 4, where story capture lives — NOT in Phase 3.**

### DEFECT — the extraction ledger is absent for every cohort turn

`turn_extraction_ledger` holds **zero rows** for any of turns 1828–1902. Its rows for these
same narrators are all `turnrow:1923+` and `2063+`, from later sessions. Extraction evidence
for the audited cohort is therefore `measurement_failed` in full — for the 35 captured turns
as much as the 3 missed ones.

### Mechanism verdicts

| Mechanism | Verdict |
|---|---|
| Turn archival | **WORKS** — 38/38 verbatim |
| Candidate creation | **WORKS** — 35/38, one per turn |
| Word preservation | **WORKS** — 35/35 byte-exact, zero over-capture, zero containment |
| Source-turn binding | **WORKS** — every candidate bound to its turn |
| Deterministic anchor trigger | **WORKS** — 18/38 reproducible from stored text |
| Factual-chain trigger | **UNAUDITABLE** — decides 20/38, records nothing |
| Extraction ledger | **NOT WRITTEN** for any cohort turn |
| Operator review | **NEVER EXERCISED** — 35/35 unreviewed |
| Memoir chain | **PROVEN** — Phase 1, one passage, canonical = preview = DOCX |

### What this does NOT establish

**Candidate presence is not story quality.** 35/38 says a candidate exists per turn and
preserves its words exactly. It says nothing about whether a 450-word turn holds one memoir
episode or four. Semantic granularity is **unmeasured**, and deliberately so: the cohort is
synthetic test material, and curating it would prove nothing about Kent or Janice.

### THE SCOPE WAS NARROWED. Here is exactly what that means.

**Phase 2 as originally written required a full destination ledger** — raw and delivered Lori
response, every transformation, every extracted entity and relationship, normalizations and
rejection reasons, structured destination, fact-candidate destination, rolling summary,
chronology and Life Map placement, and a terminal status for every meaningful item.

**That is NOT what was delivered, and this closeout does not claim it was.** What was
delivered is a **mechanism audit** of the archive → capture → review path, run read-only over
synthetic test material. The narrowing was deliberate — the cohort is test data whose story
quality is worth nothing to curate — but it must be recorded as a **TRANSFER, not a
completion**:

| Original Phase 2 obligation | Status | Now owed by |
|---|---|---|
| Raw vs delivered Lori response, each transformation | **NOT DONE — transferred** | **Phase 6** (30/76 altered responses) |
| Every extracted entity, relationship, path, value, source wording | **NOT DONE — transferred** | **Phase 3** (binding) + **Phase 5** (meaning) |
| Normalizations, reroutes, acceptance and rejection reasons | **NOT DONE — transferred** | **Phase 5** |
| Final structured destination · fact-candidate destination | **NOT DONE — transferred** | **Phase 5** |
| Rolling-summary representation | **NOT DONE — transferred** | **Phase 8** |
| Chronology and Life Map destinations | **NOT DONE — transferred** | **Phase 8** |
| Terminal status for every *meaningful item* | **PARTIAL — transferred** | **Phase 5**. Every *turn* has one; every extracted item does not |
| Narrator-by-narrator review (Pat, Stefi, Mable, Tomasita, Richard, Joe, Frank) | **NOT DONE — declined** | Synthetic material; superseded by real-narrator validation in **Phase 8** |
| Destinations of previously reported accepted extraction items | **NOT DONE — transferred** | **Phase 5** |

**Exit gate — MET FOR THE NARROWED SCOPE ONLY.** All 38 turns carry a terminal status at the
*turn* level; the three misses have an evidence-backed classification; the mechanism verdicts
are recorded. **The correctness obligations in the table above remain OPEN.** Anyone reading
this closeout as "Phase 2 is finished" is reading it wrong: the question it answered was
*does the machinery work*, not *is the interpretation right*.

### CORRECTED 2026-09-04 — two Phase 2 verdicts overstated the defect

Both corrections came from reading a source the original audit never opened: the API log.
They are recorded here rather than quietly edited, because a closeout that revises itself
without saying so is worth less than one that was wrong out loud.

**1. "The capture decision is persisted NOWHERE" — WRONG AS STATED.** `chat_ws.py:1848`
logs one `[story-trigger]` line per turn carrying trigger, word count and all three anchor
dimensions. All 38 cohort decisions are in `.runtime/logs/api.log`, and they agree with the
recomputed split *exactly* — 18 `borderline_scene_anchor`, 17 `chain_detection`, 3 `None`.

That agreement is the first independent corroboration this lane has: the split was derived
today from stored text, the log is what the server decided at run time on 2026-08-30, and
they match. The real defect is **narrower and more fixable**: the decision is recorded only
to a gitignored, rotating log, so it is not durably attached to the candidate it produced or
the turn it declined.

**2. The three misses are NOT unexplained.** `1846`, `1864` and `1870` share one signature —
`anchors=2 place=True time=False person=True` — in the live log *and* under the shipped
trigger re-run today. All three are present-day status summaries ("Today I live alone…",
"I am eighty-nine years old…"). They carry absolute dates but no *relative* time phrasing,
and `story_trigger.py:706` measures `_matches_relative_time`. **Whether a life inventory
should count as a story is a product question for Phase 4, not a classifier bug.**

**3. The zero extraction-ledger rows are a HARNESS gap, not a product defect.** All 38 turns
logged the same skip: *"client did not declare field_extraction_result=v1"*
(`chat_ws.py:924`). `run_narrator_cohort_acceptance.py` never declares
`client_capabilities`, so the server correctly ceded extraction to a client that was not a
browser and never ran it. **Extraction binding cannot be studied from this cohort at all** —
the Otis and Domingo mis-bindings below come from a real browser session
(`switch_mti0ucwl_ikwb`), not from the cohort.

`scripts/phase2_verify_ledger.py` now reads both log sources and prints the corroboration
alongside every DB-derived number, each labelled with the symbol that produced it.

## Phase 3 — Fix processing bypass and relationship binding  ✅ **ACCEPTED 2026-09-05**

**Outcome:** Narration cannot disappear into a special route, and spouses cannot become parents.

### Claim status vocabulary (adopted 2026-09-04)

Every mechanism claim below carries one of four labels. The rule that produced them:

> **A claim about what code does with a value must cite the line that READS the value, not a
> line that names, produces, or resembles it. If the reading line is on the other side of a
> process boundary, the claim is `unverified` until that side is read.**

`verified_by_read` (line cited) · `verified_by_execution` (ran it) · `inferred` (plausible,
unconfirmed — **may not be stated as fact**) · `unverified`.

**Two withdrawn claims, and why the rule exists.** A read-only investigation on 2026-09-04
reported that (a) Stefi's wording *would not* reach the correction branch, and (b) extraction
*was reading Lori's replies*. Both were wrong, and both failed the same way: a property was
inferred from a name or a nearby producer instead of from the line that consumes the value.
(a) cited a server-side classifier that *could* set `turn_mode` without ever asking what
actually sets it — **the browser does**. (b) cited a column name, `turnrow:<assistant id>`,
without reading what is passed to the extractor. Neither would have survived the rule above.

### Correction routing

**The routing chain, end to end — `verified_by_read` + `verified_by_execution`:**

| Step | Line | What it does |
|---|---|---|
| 1 | `ui/js/app.js:2599` | `/\b(?:not\|wasn't\|…)\s+(?:\d+\|that\|him\|her\|them\|me\|my\|the\|a\|an\|in\|on)\b/` |
| 2 | `ui/js/app.js:2713` | `if (_looksLikeStrongCorrection(text)) return TURN_CORRECTION;` |
| 3 | `ui/js/app.js:6627` | `const routedMode = lvRouteTurn(text);` |
| 4 | `ui/js/app.js:6691` | `ws.send(JSON.stringify({type:"start_turn", … turn_mode:routedMode …}))` |
| 5 | `chat_ws.py:6743` | `params["turn_mode"] = (msg.get("turn_mode") or "interview")…` — lifts the frame field |
| 6 | `chat_ws.py:3340` | `turn_mode = (params.get("turn_mode") or "interview")…` — **the READ line** |
| 7 | `chat_ws.py:4341` | `if turn_mode == "correction":` |
| 8 | `chat_ws.py:4413` | `return` — **unconditional**, whether or not `parsed` is empty |

Executed against Stefi's exact text, the step-1 regex returns **true**, matching the
substring `"not the"` in *"— not the Nevada one, the New Mexico one —"*. **The narrator's
clarification of which Las Vegas she was born in is routed as a self-correction by two words
of ordinary English.** The server parser then returns `{}`, `apply_correction` is correctly
skipped, and step 8 swallows the turn anyway.

**`_finalize_deterministic_turn` never writes `_persisted_turn_row_id`,
`_archive_event_persisted` or `_persisted_user_turn_row_id`** (`chat_ws.py:322-330`), which
is what holds the completed-turn hooks out — so the turn is extraction- and
placement-ineligible **by construction, not by a mode gate**. That is deliberate and
documented; the defect is reaching it with an empty parse, not the ineligibility itself.

**Story capture is NOT affected** — `inferred` corrected to `verified_by_read`: preservation
runs at `chat_ws.py:1811-1939`, roughly 2,500 lines *before* the `turn_mode` dispatch, so a
correction-routed turn is still considered for a story candidate.

- [ ] Use Stefi’s exact Las Vegas, New Mexico statement as a regression fixture.

- [x] **Correction processing finalizes only when a concrete correction is parsed.**
- [x] **`parsed={}` returns the turn to normal interview processing.** Both copies of
      the mode are reset — the local variable AND `params["turn_mode"]`, because the
      completed-turn hooks read the mode from `params` (`chat_ws.py:896`, `:1089`) and
      a single-copy reset would leave extraction still refusing the turn. The correction
      body now sits under an `else`, so the ack, the projection write and
      `_finalize_deterministic_turn` cannot run on an empty parse.
- [x] **Normal Lori response, durable persistence, extraction, trace and story
      consideration occur** — `extraction_eligible("interview")` is True and
      `"correction"` is False, which is what the reset buys.
- [x] **No correction mutation is applied without a parsed target and value** — unchanged;
      `apply_correction` was already gated on `parsed`.

### Kinship binding guard — BUILT, MEASURED, REVERTED (2026-09-04)

`add4753` added `_apply_kinship_binding_guard`. It was **reverted in full at
`1c70567`** on two independent grounds: a reproduced eval regression, and deterministic
production-path defects found by external code review that hold regardless of the eval.

| Run | Code | Total | v3 | v2 | must_not_write |
|---|---|---|---|---|---|
| `r5h-followup-guard-v1` | baseline | **78**/114 | 49/72 | 43/72 | present |
| `r5i-kinship-guard-v1` | `add4753` | **74**/114 | 45/72 | 40/72 | present (`case_066`) |
| `r5i-kinship-guard-rerun` | `add4753`, byte-identical | **73**/114 | 44/72 | 39/72 | present (`case_066`) |

**The loss repeated at every principal score, and the guard did not close the dangerous
write it existed to stop** — `parents.notableLifeEvents` still violated must-not-write on
`case_066` in both guarded runs.

**A variance claim of mine is refuted by this data.** After one paired diff I asserted a
"±4–5 case variance floor". The two identical-code runs differ by **exactly one case**
(`case_031`); observed guarded-run variation is 1, not 4–5. And all eight kinship-scored
losses (`032 053 060 073 075 077 107 108`) failed in **both** guarded runs with identical
scores — consistent, not noise. The inference was wrong in both directions: it overstated
the noise and would have excused a real regression.

**Why it was unsafe independent of the numbers** — five deterministic defects, each
verified against the shipped file:

1. **The downgrade never reached output.** `extract.py:8677` sets
   `write_mode = meta.get("writeMode", ...)` from the SCHEMA and `:8757` passes that to
   `ExtractedItem`, which accepts no `needs_confirmation`. Only the confidence cap
   survived, so a "downgraded" `family.spouse.*` item stayed `prefill_if_blank`.
2. **Grouping had not happened.** The field is `_repeatableGroup` until `:8783`, after
   `run_field_extraction` returns; the guard read `repeatableGroup`, always got `None`,
   and its `f"@{role}"` fallback then collapsed every item of a role into one bucket — so
   one collision could remove unrelated parent facts.
3. **First-name equality is not identity.** Father John and spouse John collide.
4. **Rule 1 was answer-wide.** One "my father" authorised every `parents.*` proposal in a
   long turn. Widening the anchor vocabulary cannot fix that; evidence must bind locally.
5. **Rule 2b only guarded `firstName`.** Dates, events and notes kept full authority under
   the same identity doubt.

**The tests passed anyway** because they exercised the helper directly and supplied
`repeatableGroup` by hand — a shape production never has at that point. Same failure as
the anchor fixtures: a property supplied instead of measured. **Any rebuild is tested
through `run_field_extraction`, both the LLM and rules-fallback paths, asserting the FINAL
emitted `writeMode` and confirmation metadata.**

Requirements carried forward to the rebuild are in the checklist below.

### Relationship binding

**The extractor reads the NARRATOR's words — `verified_by_read`, three independent lines.**
`turn_extraction.py:419-421` states it: *"`answer` is the NARRATOR's text. The assistant reply
is not the subject of extraction."* `chat_ws.py:963-965` passes `user_text=user_text` and
**`assistant_text=None`** literally. `turn_extraction.py:44-47` says `turn_key` is derived
from the committed assistant row *"never from a hash of the narrator's words"* — it is an
idempotency key and nothing else. **This makes the mis-binding worse, not better:** it is a
binding failure on the narrator's own sentence, not contamination from Lori's phrasing.

**The two live mis-bindings — `verified_by_execution`, read from `turn_extraction_results`:**

| Row | Narrator said (their own words) | Extractor proposed |
|---|---|---|
| `turnrow:2111` | *"Otis died in 2005. Heart attack at sixty-three."* | `parents.firstName=Otis` @0.9 · `parents.deathDate=2005` @0.9 · `parents.notableLifeEvents="died 2005"` @0.8 |
| `turnrow:2159` | *"Domingo passed in 2008."* | `parents.firstName=Domingo` @0.9 · `parents.deathDate=2008` @0.9 |

**Neither sentence contains a relationship word at all.** No "father", no "husband", nothing.
The extractor supplied `parents_0` on its own and stamped 0.9 on it — the binding-layer
causal-attribution failure the extractor architecture names as the primary failure surface.
Both are `writeMode: candidate_only` with `applied_at = NULL`, so **neither reached stored
`profiles`**; they were proposed and delivered, not applied. The containment held.

- [x] **A FABRICATED VALUE, not a mis-binding — CLOSED 2026-09-04.** The same row
      proposed `parents.birthDate = "1922"` at 0.7. Mable said *"died in 2005"* and
      *"sixty-three"*; 2005 − 63 is 1942, and 1922 appears nowhere in her words and is not
      derivable from them.

      `_value_grounding()` classifies each proposed value **individually** as
      `spoken` / `derived` / `unsupported` / `not_checked`. Against her live turn:

      | proposed | grounding |
      |---|---|
      | `parents.firstName = Otis` | spoken |
      | `parents.deathDate = 2005` | spoken |
      | `parents.notableLifeEvents = "died 2005"` | not_checked — narrative fields may summarise |
      | `parents.birthDate = 1922` | **unsupported** (`spoken_years: [2005]`) |

      **Per value, never per group.** Marking the whole quarantine unsupported would
      erase exactly the distinction an operator needs to rebind safely. Where the
      relationship IS supported and one value is not, only that value is withheld.

      **Derived ≠ spoken.** A year reproducible by a named rule from spoken operands
      (`anchor_year_minus_age`, `{anchor_year: 2005, age: 63}` → 1942) is recorded with
      its rule and operands and still does not execute — an inferred date must not
      inherit the authority of narrator wording. 1922 is not even that; it is invented.

      **Deliberate limit, named:** for dates the bar is the YEAR appearing in the
      narration. A value whose year is spoken but whose month/day are not is left alone.
      Tightening that would quarantine ordinary "born in 1962" → "1962-12-24"
      completions corpus-wide, and this lane has already measured what an over-broad
      guard costs. The demonstrated defect is a year nobody said.
**The enforcement boundary was broken too — found by consumer tracing, 2026-09-04.**
The server's downgrade did not bind the browser. `interview.js:1441` read
`item.writeMode` and never passed it on, and `projection-sync.js:314`
re-derived authority with `_map.getWriteMode(fieldPath)`. So a
`suggest_only` + `needs_confirmation` item was still processed at the browser
schema's `prefill_if_blank`: **the narrator got a clarification prompt and the
prefill both.** This predates the kinship guard — it means the shipped
transcript-safety downgrade has the same hole. `projectValue` now resolves an
effective mode ONCE and hands it down; the reduction is one-way, so a response
body can tighten authority but never widen it, and `needs_confirmation` is a
defensive floor to `suggest_only`. Mutation-checked: three separate mutations of
the product each turn the guard red.

**TESTING DOCTRINE ADOPTED 2026-09-04 — [`docs/TESTING-DOCTRINE.md`](../TESTING-DOCTRINE.md).**
Eight instances in this lane of one failure: *a test constructs the property it
intends to prove, exercises a helper against that constructed shape, and passes
without crossing the production boundary.* Fabricated anchor counts, supplied
`repeatableGroup`, guessed questionnaire nesting, helper-only decision tests,
vacuous mutations, and a question-bank shape no real case uses — the last of
which returned empty preservation fates for all 114 live cases while seven
synthetic tests stayed green. **A fixture may supply values, but not the
property being proven.** Every helper assertion needs a production-boundary
companion, and every mutation must make that companion fail. The audit table
and the one gap it closed are in that document. **To be folded into `CLAUDE.md`
at the Phase 3 reconciliation.**

**Rebuild requirements — every one of these is a defect `add4753` shipped:**

- [ ] Runs AFTER relationship grouping, or against the final extraction representation.
- [ ] Evidence is inspected LOCALLY per proposed person/group, never answer-wide.
- [ ] `suggest_only`, `needs_confirmation` and the REASON survive serialization into the
      emitted item. A downgrade that a downstream constructor discards is not a downgrade.
- [ ] Never hard-refuses on first-name equality alone; same-name ambiguity DOWNGRADES.
- [ ] Refuses on a known other-role identity only when identity evidence is strong.
- [ ] Downgrades or quarantines the WHOLE uncertain group, not just `firstName`.
- [ ] Mixed spouse-and-parent narration produces no collateral removal.
- [ ] Quarantines an uncertain relationship as an attributed fact rather than presenting
      `parents.firstName=Otis` as a merely lower-confidence parent.
- [ ] Tested through `run_field_extraction` on BOTH paths with real ungrouped input,
      including father-John/spouse-John, asserting final emitted writeMode + metadata.
- [ ] One new live eval against the CORRECTED implementation — not another run of `add4753`.
- [ ] Jim binds as Pat’s husband.
- [ ] Otis binds as Mable’s husband.
- [ ] Domingo binds as Tomasita’s husband.
- [ ] A spouse cannot enter `parents.*`.
- [ ] Binding checks the narrator’s actual relationship language and nearby context.
- [ ] Model confidence alone authorizes no canonical relationship.
- [ ] Weak or ambiguous binding becomes an attributed fact candidate.
- [ ] Existing synthetic mis-bound fields are inventoried before correction.

**Exit gate:** Stefi follows the normal turn path; all three spouse fixtures bind correctly; no false parent field is written; uncertain relationships remain reviewable.

## ✅ PHASE 3 ACCEPTED — the exit gate is met (2026-09-05)

**Every clause of the exit gate above is satisfied, and the last one open — "Stefi follows
the normal turn path" — was proven live over the production WebSocket rather than argued
from source.**

### The accepted evidence

| Obligation | Evidence |
|---|---|
| **Kinship containment and value grounding** | Group-local guard quarantines an unstated relationship whole-group and entity-bound; grounding is annotated **per value** (`spoken`/`derived`/`unsupported`), never per group. `parents.birthDate=1922` was fabricated and is now caught |
| **Review-only preservation** | Review-only results travel end to end; a quarantined value is **preserved for review, not lost** |
| **Browser authority enforcement** | The server's authority decision now binds the browser — it previously did not, which also silently affected shipped transcript safety. Effective mode resolved ONCE and handed down; reduction is one-way, so a response body can tighten authority but never widen it. Three separate product mutations each turn the guard red |
| **Stefi live WebSocket pass** | `20260905-021741` — see below |
| **Clean final evaluations** | `r5k-guard-v2` 71/114 at `5afead5`, **clean tree**, 0 `must_not_write`; `r5k-generational` 7/14 at `4ab00fc`, clean tree, 0 `must_not_write` |

### The Stefi live gate — `20260905-021741`

Run by `scripts/stefi_correction_fallthrough_probe.py` against the production WebSocket.
Narrator `5e6a3d6c-c037-41e8-b260-d72e79f84fb5`, conversation
`stefi-fallthrough-20260905-021741`. **9/9, zero unverified.**

* Her exact statement routes as `correction` — the SHIPPED `app.js` regex, extracted from
  the file and evaluated with node, not retyped.
* The server parser finds no actionable target/value — with a non-vacuity control: a real
  correction still parses to `{'family.children.count': 2, '_retracted': [3]}`.
* `[correction-fallthrough]` emitted for this conversation.
* **No correction mutation and no acknowledgement** — no `correction_payload` frame, no
  `correction-apply` line. Those are the only two things the `else` branch performs.
* A nonempty ordinary response committed; both turns persisted.
* **No `correction` mode persisted.** Absence is how ordinary turns are stored:
  `_finalize_deterministic_turn` (`chat_ws.py:278`) is the ONLY writer of `turn_mode` into
  turn meta, and ordinary turns finalise with `meta={"ws": True}`.
* **The turn ran the ordinary pipeline**: `[story-trigger] preserved
  candidate_id=bf8f41e6…` then `[story-trigger][bind] user_row=2202 assistant_row=2203`. A
  deterministic correction turn preserves and binds nothing, so this is the positive proof.
* The candidate carries **no placement** — `placement_source=unknown`, `era_candidates=[]`,
  per the standing rule that an era nobody confirmed is not a placement.

### What Phase 3 does NOT claim

* **No extraction-quality claim.** The r5h→r5k comparison spans three different scorers and
  two dirty trees; the −7 measures scorer and extractor together and is registered as
  nonblocking measurement debt in [`docs/BACKLOG.md`](../BACKLOG.md) §6a. `r5k`'s 0
  `must_not_write` is solid current evidence; the `2 → 0` delta is **not** established.
* **Field extraction was not exercised by the live gate.** The probe does not declare
  `field_extraction_result=v1`, so the server correctly deferred extraction to the client.
  The hook evidence is story-trigger.
* **The response was `'Cuéntame más sobre eso.'`** — 23 characters, in Spanish, to a
  2,565-character chapter. The fallthrough is proven; whether that is the right *reply* to
  that passage is a Lori-behaviour question, not a Phase 3 one.

### Testing doctrine — folded in

[`docs/TESTING-DOCTRINE.md`](../TESTING-DOCTRINE.md) was adopted during this phase and is
referenced from `CLAUDE.md`. Three further instances of the same family were found while
closing it, all in the instruments rather than the product: a raw-text guard that failed on
its own file's post-mortem (three times, now scanning executable source in all three
places); a browser lane whose `[].every()` would have reported a pass having walked no tab;
and a probe assertion first overstated ("stamped interview") and then over-corrected
("vacuous") before being measured.

## Phase 4 — Make memoir-worthy story capture dependable  ⬅ **CURRENT ACTION**

**Outcome:** Important life narration becomes reviewable even when it does not resemble a
travel chain — and every capture decision is inspectable.

### THE CORRECTED SCOPE — read this before anything below (2026-09-05)

**Phase 4's first job is auditability, not capture rate.** The list further down still
describes broadening what counts as a story, and that work is real, but it is **not what
this phase starts with** and a percentage must not be raised first.

> **Durably attach story-capture decisions and diagnostics to their source turns,
> INCLUDING turns that produced no candidate.**

Three facts fix that scope, and each was measured rather than assumed:

* **The decision is already recorded — just not durably.** All 38 cohort turns emit trigger,
  word count and every anchor dimension at `chat_ws.py:1848`, into `.runtime/logs/api.log`,
  which is **gitignored and rotates**. The job is to attach an existing record to the row it
  explains, not to start recording.
* **Candidate presence is 35/38, byte-exact, with zero over-capture.** Raising a threshold
  was never the work.
* **A missed turn has no candidate**, so `story_candidates` cannot hold the record by
  construction. It belongs on the turn, or in a per-turn decision table.

**The declined captures are the point.** The three cohort misses have a named cause — no
relative-time phrasing in a present-day life inventory — precisely because the decision was
inspectable. A threshold change would have buried that. **Tuning a classifier whose
decisions cannot be inspected is guesswork**, so no capture threshold moves until the
decisions can be read back.

Live confirmation from the Phase 3 gate: Stefi's turn logged
`[chat_ws][trip-story-capture] captured=False reason=shelf_closed scope=None` — a declined
capture, with its reason, **existing only in a rotating log**. That is exactly the record
this phase must make durable.

### FIRST, BEFORE ANY THRESHOLD CHANGE: persist the capture decision

**REFRAMED 2026-09-04 — the decision is recorded, just not durably.** This section
previously read "the deciding signal for 20 of 38 turns is recorded nowhere". It is recorded
for **all 38**, at `chat_ws.py:1848`, with trigger, word count and every anchor dimension —
into `.runtime/logs/api.log`, which is gitignored and rotates. So the work is not *start
recording it*; it is **attach the existing record to the row it explains, durably**, which is
a smaller and better-specified job. A missed turn still has no candidate to attach it to,
so the record belongs on the turn.

The three cohort misses now have a named cause rather than a shrug — no relative time
phrasing in a present-day life inventory — which is exactly the kind of finding a threshold
change would have buried. Tuning a
classifier whose decisions cannot be inspected is guesswork.

- [ ] Persist **one decision record per narrator turn — including turns that create no candidate.**
- [ ] Attach it to the **source turn**, or to a dedicated per-turn decision table. *(Putting it on `story_candidates` is insufficient by construction: a missed turn has no candidate.)*
- [ ] Record: source turn · narrator · the deterministic `trigger_diagnostic` measurements · the factual-chain result · the final nomination decision · the decision reason · the classifier/trigger version · the candidate id when one was created.
- [ ] **Do NOT change any capture threshold until those decisions can be inspected.**
- [ ] Also fix the absent `turn_extraction_ledger` writes — extraction evidence was missing for every cohort turn.

**REFRAMED 2026-09-04 by the Phase 2 closeout.** Candidate presence is **35/38** with
capture byte-exact and zero over-capture, so raising a percentage was never the work. The
real capture defects are **auditability**: the factual-chain decision that determines 20 of
38 turns is persisted nowhere, and `turn_extraction_ledger` was never written for this
cohort. Fix those first — see the block above. The goal stated below still holds: every substantive passage should be either nominated or given a defensible,
inspectable `not_story` reason. What is owed is the `not_story` reason for the three, and
an operator pass over the thirty-five.

- [ ] Treat the full coherent narrator passage as the source unit.
- [ ] Add Pat’s Jim passage as the primary regression fixture.
- [ ] Detect meaningful events involving relationships, loss, identity, work, migration, community, belief and turning points—not only place chains.
- [ ] Preserve exact wording, source turn, narrator, era and involved people.
- [ ] Never manufacture a story from extractor-only structured fields.
- [ ] Keep fact candidates separate from story candidates.
- [ ] Avoid duplicate candidates for one passage.
- [ ] Record why a substantive turn was or was not nominated.
- [ ] Re-evaluate the 27 baseline no-candidate turns without rewriting historical evidence.
- [ ] Human-review the new candidate set for relevance, coherence and overcapture.

**Exit gate:** Pat’s Jim passage is reviewable; every substantive baseline passage has a candidate or defensible recorded reason; no unsupported story is created; candidate provenance is complete.

## Phase 5 — Preserve and organize extracted meaning

**Outcome:** Understood meaning reaches a correct structured field or an attributed review lane without weakening canonical truth.

- [ ] Normalize `daddy → father` while retaining `daddy` in provenance.
- [ ] Normalize `mama → mother` while retaining `mama`.
- [ ] Support ex-spouse status without losing `ex-spouse`.
- [ ] Normalize `adult child → child` while retaining `adult`.
- [ ] Preserve older/younger sibling qualifiers.
- [ ] Do not add `partner`; verify its existing path instead.
- [ ] Confident source-bound fact → structured field.
- [ ] Meaningful unmapped fact → attributed fact candidate.
- [ ] Weak relationship binding → review candidate.
- [ ] Genuine parse debris → rejected with source and reason.
- [ ] No meaningful interpretation silently disappears.
- [ ] Group candidates by narrator, era, person and event so review remains usable.
- [ ] Link every structured or candidate item to its source turn.

Do not disable `HORNELORE_CLAIMS_VALIDATORS` as a product fix. That switch gates multiple safeguards while leaving the parse-time whitelist active; it is not a clean return to earlier extraction behavior.

**Exit gate:** Every extracted proposal has a correct field, attributed candidate or defensible rejection; no valid information is forced into a false schema field.

## Phase 6 — Restore Lori’s conversational quality

**Outcome:** Delivered Lori is at least as grounded, grammatical and attentive as raw Lori.

- [ ] No model reasoning reaches the narrator.
- [ ] No form machinery or internal directive language reaches the narrator.
- [ ] No `Life Map` or cohort marker is used as a conversational anchor.
- [ ] Anchors come from narrator language or are omitted.
- [ ] Atomicity enforcement never truncates a sentence or conjunction.
- [ ] One-question enforcement does not lengthen a compliant response.
- [ ] Era repair never produces fragments or ungrammatical text.
- [ ] A clarification does not become a form correction.
- [ ] A bilingual phrase does not lock later English turns into Spanish.
- [ ] Bounded synthetic tracing compares raw, transformed and delivered text.
- [ ] A human reviewer scores listening, warmth, dignity and conversational continuity.

**Exit gate:** Focused fixtures show zero system leaks, zero fragments, zero UI anchors, zero clarification misroutes and meaning-preserving delivered replies; human review finds Lori attentive rather than interrogating.

## Phase 7 — Make review and memoir creation a normal Operator workflow

**Outcome:** A family operator can convert provisional stories into a memoir without developer tools.

- [ ] Pending story count appears in the Operator tab.
- [ ] Review queue is accessible outside the Bug Panel.
- [ ] Candidate displays narrator, era, full source passage and provenance.
- [ ] Fact candidates and story candidates are visibly distinct.
- [ ] Operator can promote, reject, edit placement and defer.
- [ ] UI explains that unreviewed stories remain archived but do not enter canonical memoir.
- [ ] Conflict handling preserves operator edits.
- [ ] Preview updates after promotion.
- [ ] Wrap-up reports pending and approved story counts.
- [ ] Export uses the same canonical sources shown in preview.

**Exit gate:** An ordinary operator can finish a session, review its stories, preview the memoir and export the same content without using logs, scripts or direct API calls.

## Phase 8 — Focused acceptance, then full cohort

Do not begin with all ten narrators.

### Focused narrators

- [ ] Stefi — clarification/correction routing.
- [ ] Pat — spouse binding, Jim story capture, promotion and memoir.
- [ ] Mable — spouse binding and family vocabulary.
- [ ] Tomasita — spouse binding and language stability.
- [ ] Walt — seven-era continuity and cross-era memory.

### Required evidence

- [ ] Exact transcript and TTS completion.
- [ ] Correct era and runtime context.
- [ ] Raw, transformed and delivered Lori response.
- [ ] Structured fields and fact candidates.
- [ ] Story candidates and recorded no-candidate reasons.
- [ ] Rolling summary, chronology and Life Map placement.
- [ ] Operator review actions.
- [ ] Canonical memoir, preview and export comparison.
- [ ] End-to-end provenance.

### Full cohort gate

Only after all five focused narrators pass:

- [ ] Run the ten synthetic demographic narrators.
- [ ] Inspect actual conversations, not only PASS totals.
- [ ] Confirm all statements remain archived.
- [ ] Confirm zero false relationship bindings.
- [ ] Confirm important passages are reviewable.
- [ ] Review and promote a representative candidate set.
- [ ] Generate memoir previews and exports.
- [ ] Confirm every memoir passage traces to narrator words.

**Final exit gate:** Lorevox archives faithfully, Lori responds naturally, structured memory is correctly attributed, memoir-worthy narration is reviewable, and approved passages appear identically in canonical memoir, preview and export.

# 6. Shared working protocol

## Git responsibilities

**Claude runs NO Git command of any kind from the sandbox — including
read-only ones.** Not `fetch`, `pull`, `push`, `rebase`, branch switch, `add`,
`commit`, `clean`, and **not `status`, `rev-parse`, `log`, `diff` or
`check-ignore` either.

*Why read-only is not the safe category.* The rule first said Claude could run
read-only inspection. During Phase 0 a plain `git status` from the sandbox
stranded a zero-byte `.git/index.lock` that the sandbox could not then remove
(`Operation not permitted`), and Chris had to clear it by hand. A stranded lock
blocks GitHub Desktop and WSL git, and its symptom is deliberately confusing:
`git add` appears to succeed, `git commit` reports nothing to commit, and
Desktop keeps showing changed files after a "successful" push. **The hazard is
sandbox git, not write-mode git.**

**Chris supplies the starting HEAD and working-tree status at the start of each
phase.** Claude records what it is given and does not verify it with git.

| actor | does |
|---|---|
| **Claude** | edits files; runs offline tests; hands Chris a copy-paste commit block. Runs no git. |
| **Chris** | supplies HEAD and status; commits and pushes **using WSL or GitHub Desktop, whichever he prefers** |
| **ChatGPT** | read-only review of pushed `origin/main` and the evidence |

## Start of phase

Claude must report:

```text
START PHASE:
Starting HEAD (supplied by Chris; Claude runs no git):
Working tree status (supplied by Chris):
Active phase:
Scope:
Expected files:
Offline or live:
Explicitly out of scope:
Exit gate:
```

## During phase

- Claude works only on the active phase.
- Chrome and WSL may be used for genuine live testing.
- Product defects are reported; the harness may not work around them to obtain PASS.
- Unknown is `not_measured`, never PASS.
- Existing synthetic narrators are reused when possible.
- Nothing is deleted without Chris’s explicit authorization.
- No next phase begins early.
- No unrelated mini-work order is opened.

## End of phase

Claude must report:

```text
END PHASE:
Local HEAD worked from (Claude does not commit):
Files changed:
Product behavior changed:
Tests run:
Live evidence:
Evidence/report paths:
Exit gate result:
Remaining failures:
Not measured:
Next phase — NOT STARTED:
```

## Push and supervisory review

1. Claude completes one phase and hands Chris a copy-paste commit block.
   Claude runs no git at all.
2. Chris commits and pushes, using WSL or GitHub Desktop as he prefers.
3. Chris tells ChatGPT it is pushed.
4. ChatGPT fetches `origin/main` before reviewing.
5. ChatGPT reviews pushed code and evidence, not only Claude’s summary.
6. ChatGPT updates this work order’s checklist and gives one next-phase direction.
7. Chris decides whether the next phase begins.

Pasted completion reports are treated as committed and pushed unless Chris explicitly says otherwise.

# 7. Immediate active phase

**IMMEDIATE INSTRUCTION — updated 2026-09-04.** Phase 0 is accepted (`fdaa255`) and
**Phase 1 is ACCEPTED** — the chain is proven end to end and no further mutation is
authorized.

Begin **Phase 2 only: the READ-ONLY 38-turn span/granularity ledger.** Do NOT rerun the
cohort, do not create a narrator, and do not change extraction, response controls or story
capture. The first pass is built at
`docs/reports/PHASE2_38_TURN_SPAN_LEDGER_20260904.json` and has already overturned this
work order's headline defect; what remains is adjudicating the eleven correctness defects
the corrected numbers leave standing.

This document is now the single shared plan. The superseded work order remains historical evidence and must not be used to direct new work.
