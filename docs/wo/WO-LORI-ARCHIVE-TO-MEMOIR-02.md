# WO-LORI-ARCHIVE-TO-MEMOIR-02

**Status:** CURRENT — central Lori/Lorevox work order  
**Supersedes:** `WO-LORI-END-TO-END-LISTEN-RETAIN-MEMOIR-01`  
**Starting evidence:** demographic cohort `20260901T015343Z` and Walt seven-era run `20260901T003329Z`  
**Current position:** **Phase 1 CLOSED 2026-09-04** (`20260904T130158Z`, exit 0) — **Phase 2 is next**  
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

- [ ] **CANDIDATE-PRESENCE COUNT: 11 of 38 narrator turns produced a candidate (29%).**
      *(Relabelled 2026-09-04 — it was written as "story capture covered 11 of 38". It is
      not coverage: it counts candidates without measuring span, and one 452-word aggregate
      covers many statements while one 38-word atom covers exactly one. See the granularity
      finding under Phase 2.)*
- [ ] Twenty-seven turns were archived but produced no reviewable story candidate.
- [ ] Pat’s account of Jim’s death is `archived_only`; its turn recorded `story-trigger=None`.
- [ ] Reviewing every existing candidate would therefore still omit most cohort narration from memoir eligibility.
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
- [x] **Promotion → canonical → preview → export PROVEN end to end 2026-09-04** (`20260904T130158Z`, exit 0, agreement 1/1/1, control unchanged). *One passage — this is not a coverage claim.*
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

### The operator workflow under test

Phase 1 therefore exercises **two authorised mutations**, in order, both through
the real Bug Panel controls and both against the same `PATCH
/api/operator/story-candidates/{id}` endpoint:

- [ ] Record candidate ID, narrator ID, conversation ID, source-turn IDs, exact passage — and the **absence** of a placement.
- [ ] Open the real Operator review surface.
- [ ] **Place** through the real era control, then `Save placement / notes`. Selecting an era *is* the operator placement: the control writes `placement_source=operator_set` in the same gesture, and `operator_set` is deliberately not hand-selectable from the source dropdown.
- [ ] Confirm the candidate now carries `building_years` as its **sole** era with `placement_source=operator_set`, that the review version advanced, and that `review_status`, transcript and provenance are untouched.
- [ ] **Refetch the row** so the panel carries the new version. `applyReview` sends the version it last rendered; promoting without refetching sends a stale version and takes a 409.
- [ ] Promote through that row's real Promote control, at the version the placement returned.
- [ ] Confirm status becomes `promoted` without losing provenance **or the placement**.
- [ ] Query canonical memoir from the correct API origin.
- [ ] Confirm the exact passage appears once with correct narrator and era.
- [ ] Open normal memoir preview.
- [ ] Export the memoir document.
- [ ] Compare canonical response, preview and export.
- [ ] Confirm all three contain the passage exactly once.
- [ ] Confirm no incorrect structured family fact is substituted into the passage.

## ✅ PHASE 1 CLOSED — the full chain is proven (2026-09-04)

**Exit gate met.** Run `20260904T130158Z`, exit code **0**,
`Phase 1: PASS — full chain proven`.

| Link | Result |
|---|---|
| placement | `carried_forward` from `20260904T123556Z`, re-verified live |
| placement verified | **PASS** — sole era `building_years`, `operator_set`, provenance unchanged |
| promotion | **PASS** — `promoted`, placement survived |
| canonical API | **PASS** — occurrences **1**, `era=building_years`, `source_id=5d57a43ce780`, `complete=true`, `lane=read` |
| preview | **PASS** — `:popover-open` true, occurrences **1**, 1408 chars |
| export | **PASS** — `lorevox_memoir_…__pat_structured.docx`, 36,975 bytes, occurrences **1**, `bodyPersonIsPat=true` |
| agreement | **PASS** — canonical **1** / preview **1** / DOCX **1** |
| control `5a56f942` | **PASS** — byte-identical |

**Mutations in the proving run: ZERO.** It resumed at mode `promoted`, budget `0`,
observed `0`, no blocked PATCHes, no refusals. The two authorized mutations were performed
earlier, in `20260904T123556Z`, and nothing has touched the candidate since.

**Two contract guarantees held, and both are worth recording:**

- `containsSourceId: false` — **no raw UUID reached the document.** `memoir_contract`
  requires that a raw narrator or candidate id "must not appear in a document a family
  reads", and the export honoured it.
- `forbidden: []` — **none of the known bad substitutions reached the document.** The
  relationship-misbinding defect (`Jim` bound under `parents.*`) did not leak into this
  passage's export.

### What Phase 1 does NOT claim

It proves **one** passage completes the chain. It says nothing about the other 27
archived-but-uncaptured statements, nothing about capture granularity, and nothing about
whether the memoir would be *right* at scale. Those are Phase 2's subject. The value of
this result is that the chain exists and is traversable — every later finding is now a
question of coverage and correctness rather than of whether the road is there at all.

### Defects found and fixed while proving it

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
non-zero. Control candidate `5a56f942` must be byte-identical afterwards,
checked in `finally` so a crash cannot skip it.

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
### Capture granularity is not stable, and the ledger must measure it (2026-09-04)

**Discovered while selecting Pat's row for the Phase 1 live run, from a read-only DB read.**
Pat has **five** candidates, and the same narration produced two completely different
answers to *"what is a story?"*:

| Candidate | Run | Words | Chars | Source turns | Span |
|---|---|---|---|---|---|
| `24ceb055` | 2026-08-31 cohort | 461 | 2429 | 1848–1849 | aggregate |
| `6f2df375` | 2026-08-31 cohort | 452 | 2332 | 1850–1851 | aggregate |
| `f130549c` | 2026-08-31 cohort | 472 | 2474 | 1852–1853 | aggregate |
| `5a56f942` | 2026-09-01 switch | 42 | 233 | 2090–2091 | atomic |
| `447eee18` | 2026-09-01 switch | 38 | 182 | 2094–2095 | atomic |

The three cohort candidates are **not nested in one another** — they are three sequential
~450-word spans opening at birth, at Kent State, and at Jim's death. The two switch-session
candidates are single turns, and each sits **verbatim inside** a cohort candidate:
`5a56f942` ⊂ `24ceb055`, `447eee18` ⊂ `6f2df375`.

**This is not duplicate capture.** It is the same content chunked at roughly 12× different
scale depending on the run, with nothing recording which scale is correct. Promote
`447eee18` and a family reads one paragraph about Kent State; promote `6f2df375` and they
read 450 words spanning Kent State through forty-six years of hair appointments — from the
same narration.

`24ceb055` and `5a56f942` additionally render **byte-identical previews** (both truncate at
200 characters through the same opening), which is what forced row identity into the
operator UI: no text rule can separate an aggregate from an atom nested inside it.

**Pre-promotion evidence:** `docs/reports/PHASE1_PRE_PROMOTION_CANDIDATE_SNAPSHOT_20260904.json`
— full transcripts, containment and preview-clash analysis, taken read-only before Phase 1
mutates anything. `docs/reports/` is gitignored, so it is local-only by design.

### `11/38` is a CANDIDATE-PRESENCE COUNT, not statement coverage

**Do not quote it as coverage anywhere.** It counts candidates without measuring span. One
452-word aggregate covers many of the 38 statements; one 38-word atom covers exactly one.
The same conversation therefore scores wildly differently depending on which run captured
it, and a rising count can mean better capture *or* coarser chunking.

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

- [ ] **Candidate presence** — how many candidates exist (this is what `11/38` was).
- [ ] **Independently addressable statement coverage** — statements reachable as their own story, not merely present inside some aggregate.
- [ ] **Over-capture / aggregation** — statements swept into a span far larger than themselves.
- [ ] **Duplicate and containment groups** — candidates nesting or overlapping, grouped.
- [ ] **Unreachable archived statements** — archived, but reachable by no promotable candidate.

**Sequencing:** the finalized ledger is built **after** the Phase 1 live run. Phase 1 moves
`447eee18` from unplaced/unreviewed to placed/promoted, so a ledger completed first would
have a stale destination state on the day it was written.

- [ ] Selected era and era actually sent. **Record the runtime era and the story placement separately** — see Phase 1. A candidate with no `placement_source=operator_set` is UNPLACED regardless of which era the conversation was in, and the ledger must not collapse the two.
- [ ] Raw Lori response, each transformation and delivered response.
- [ ] Every extracted entity, relationship, path, value and source wording.
- [ ] Every normalization, reroute, acceptance and rejection reason.
- [ ] Final structured destination, if any.
- [ ] Fact-candidate destination, if any.
- [ ] Story-candidate ID/status, or the exact reason no candidate was created.
- [ ] Rolling-summary representation.
- [ ] Chronology and Life Map destinations.
- [ ] Memoir eligibility and provenance.
- [ ] One terminal status from Section 4 for each meaningful item.

Required aggregate totals:

- [ ] 38 statements accounted for.
- [ ] 11 current story candidates independently reproduced.
- [ ] 27 no-candidate turns independently reproduced and classified.
- [ ] Pat, Stefi, Mable, Tomasita, Richard, Joe and Frank explicitly reviewed.
- [ ] The final destinations of the previously reported accepted extraction items identified.

**Exit gate:** No statement or interpretation is represented merely as `persisted`; the ledger names its real destination, lack of destination or measurement failure.

## Phase 3 — Fix processing bypass and relationship binding

**Outcome:** Narration cannot disappear into a special route, and spouses cannot become parents.

### Correction routing

- [ ] Use Stefi’s exact Las Vegas, New Mexico statement as a regression fixture.
- [ ] Correction processing finalizes only when a concrete correction is parsed.
- [ ] `parsed={}` returns the turn to normal interview processing.
- [ ] Normal Lori response, durable persistence, extraction, trace and story consideration occur.
- [ ] No correction mutation is applied without a parsed target and value.

### Relationship binding

- [ ] Jim binds as Pat’s husband.
- [ ] Otis binds as Mable’s husband.
- [ ] Domingo binds as Tomasita’s husband.
- [ ] A spouse cannot enter `parents.*`.
- [ ] Binding checks the narrator’s actual relationship language and nearby context.
- [ ] Model confidence alone authorizes no canonical relationship.
- [ ] Weak or ambiguous binding becomes an attributed fact candidate.
- [ ] Existing synthetic mis-bound fields are inventoried before correction.

**Exit gate:** Stefi follows the normal turn path; all three spouse fixtures bind correctly; no false parent field is written; uncertain relationships remain reviewable.

## Phase 4 — Make memoir-worthy story capture dependable

**Outcome:** Important life narration becomes reviewable even when it does not resemble a travel chain.

This is the central bottleneck: the current **candidate-presence count** is 11/38 (29%) — **not** a coverage figure, for the reasons recorded under Phase 2. The goal is not to force every utterance into the memoir. The goal is to ensure every substantive autobiographical passage is either nominated or given a defensible, inspectable `not_story` reason.

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

Begin **Phase 0 only**.

After Phase 0 is pushed and reviewed, perform Phase 1’s single end-to-end memoir proof. Do not redesign extraction, response controls or story capture before that proof and the Phase 2 ledger establish precisely what the current system does.

This document is now the single shared plan. The superseded work order remains historical evidence and must not be used to direct new work.
