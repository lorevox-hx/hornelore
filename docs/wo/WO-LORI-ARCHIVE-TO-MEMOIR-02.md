# WO-LORI-ARCHIVE-TO-MEMOIR-02

**Status:** CURRENT — central Lori/Lorevox work order  
**Supersedes:** `WO-LORI-END-TO-END-LISTEN-RETAIN-MEMOIR-01`  
**Starting evidence:** demographic cohort `20260901T015343Z` and Walt seven-era run `20260901T003329Z`  
**Current position:** evidence baseline complete; product correction phases not started

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

- [ ] Story capture covered only **11 of 38 narrator turns (28%)**.
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
- [ ] Promotion-to-canonical-to-preview-to-export has not been proven end to end.
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

- [ ] Set `HORNELORE_RESPONSE_TRACE=0` for ordinary stack startup.
- [ ] Restart and verify `/api/health/response-trace` reports `enabled:false`.
- [x] Record current trace exposure numerically: 10 cohort IDs; 0 non-cohort IDs; 0 non-cohort records.
- [ ] Preserve existing synthetic trace and cohort artifacts without deletion.
- [ ] Verify future checkpoints record `durableComplete`, downloaded ZIP name, downloaded operator report name and `uiFindings` from the runner itself.
- [ ] Preserve the original and rebuilt historical checkpoints distinctly.

**Exit gate:** Trace is off; evidence is preserved; a newly constructed offline checkpoint contains all required fields.

## Phase 1 — Prove the existing memoir chain

**Outcome:** Determine whether today’s implemented chain can render and export one approved synthetic story.

Use one coherent existing provisional candidate. Do not create another narrator and do not change story-capture rules in this phase.

- [ ] Record candidate ID, narrator ID, conversation ID, source-turn IDs, exact passage and era.
- [ ] Open the real Operator review surface.
- [ ] Promote through the real operator control.
- [ ] Confirm status becomes `promoted` without losing provenance.
- [ ] Query canonical memoir from the correct API origin.
- [ ] Confirm the exact passage appears once with correct narrator and era.
- [ ] Open normal memoir preview.
- [ ] Export the memoir document.
- [ ] Compare canonical response, preview and export.
- [ ] Confirm all three contain the passage exactly once.
- [ ] Confirm no incorrect structured family fact is substituted into the passage.

**Exit gate:** One passage completes `archive → provisional story → operator promotion → canonical memoir → preview → export`, or the precise broken link is identified and corrected before proceeding.

## Phase 2 — Build the 38-turn destination ledger

**Outcome:** Account for what happened to every cohort statement and every meaningful interpretation before changing extraction or capture.

This is a read-only rebuild from existing evidence. Do not rerun the cohort.

For each of 38 narrator statements record:

- [ ] Exact narrator text, narrator, conversation, client turn and durable row IDs.
- [ ] Selected era and era actually sent.
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

This is the central bottleneck: current measured story coverage is 11/38 (28%). The goal is not to force every utterance into the memoir. The goal is to ensure every substantive autobiographical passage is either nominated or given a defensible, inspectable `not_story` reason.

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

**Claude performs NO network Git operations.** No `fetch`, `pull`, `push`,
`rebase`, branch switch, `add`, `commit` or `clean`. Claude may run read-only
local inspection (`rev-parse`, `status`, `log`, `diff`) and must record the
local HEAD it worked from.

*Why this is a rule and not a preference:* the sandbox takes `.git/index.lock`
for the duration of every git command, and a command that hits the agent's
timeout on the `/mnt/c` 9p mount leaves that lock behind — silently blocking
GitHub Desktop and Chris's own WSL git. The symptom is deliberately confusing:
`git add` appears to succeed, `git commit` then reports nothing to commit, and
Desktop keeps showing changed files after a "successful" push. Claude confirms
no `.git/*.lock` survives any read-only inspection.

| actor | does |
|---|---|
| **Claude** | records local HEAD and `git status`; edits files; runs offline tests; hands Chris a copy-paste commit block |
| **Chris** | commits from WSL, pushes from GitHub Desktop |
| **ChatGPT** | read-only review of pushed `origin/main` and the evidence |

## Start of phase

Claude must report:

```text
START PHASE:
Local HEAD (read-only, no fetch):
Working tree status:
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
   Claude does not commit, push or fetch.
2. Chris commits from WSL and pushes from GitHub Desktop.
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
