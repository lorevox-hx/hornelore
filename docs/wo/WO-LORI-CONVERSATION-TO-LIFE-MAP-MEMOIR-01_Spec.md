# WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01

**Conversation → capture → extraction → review → chronology/Life Map → memoir.**

**STATUS: ACCEPTED AND COMPLETE — 2026-08-20.**

*This file was written at closeout. The work order ran as a supervised
sequence of instructions rather than from a pre-written spec, so this
records what was built and what was proven, not what was planned. That
is stated plainly because a spec that pretends to predate its
implementation is a spec nobody can trust about anything else.*

---

## 1. The gap this closed

Both ends of the pipeline worked and there was no joint in the middle.

Lori asked good questions and the narrator's answers were preserved.
Extraction ran and produced structured evidence. The operator had a
review surface. The Life Map drew eras. The memoir exported. But a
story captured in conversation could not be traced to the turns it came
from; extraction output existed in `turn_extraction_results` and no
reviewer could see it; a placed story did not reliably reach the
chronology; and the memoir preview, the TXT export and the DOCX export
each produced a different document.

The narrator could speak, and the system could not carry what they said
from one end of itself to the other.

## 2. Binding protections, stated by Chris and held throughout

Quoted because they governed every decision in the lane:

> Preserve Lori's natural questioning and Witness behavior. Preserve the
> ten-topic Profile Seed workflow. Safety remains parked. Do not change
> the model. Do not activate the inert directive-family consumer.
> Preserve Spanish/English handling and prevent place names or bilingual
> narration from causing false language switches. Narrator speech
> remains provisional until operator review. Nothing enters the Life Map
> as approved or reaches the memoir merely because extraction found it.
> Travel Document consumes canonical chronology; it does not become a
> competing memory authority.

All held. None was traded for progress.

## 3. What landed

**Commit 1 — provenance.** Migration 0047 adds
`source_user_turn_row_id` and `completed_assistant_turn_row_id` to
`story_candidates`; 0048 adds two `AFTER DELETE ON turns` triggers that
clear each column independently so a deleted turn never takes the story
with it. `story_candidate_bind_turn_rows()` takes the write lock first
and proves five things before binding — the candidate exists, the
narrator matches, the conversation matches, both rows are in that
conversation, and each row has the expected role. Write-once, idempotent
on the same pair.

**Commit 2 — placement truthfulness.** `story_projection` became the
ONE interpretation of `review_status`. A placement requires an era: a
year alone does not place a story, because the Life Map is drawn in
eras. `placement_source` is recorded, never inferred. The review
transaction refuses an incoherent placement — a source with no era, or
an era with no source — and the projection reads legacy rows carrying
those combinations honestly rather than promoting a guess into a
chapter heading.

**Commit 3 / A / B — one canonical memoir.** `services/memoir_contract.py`
is the single reviewed-evidence read. Preview, TXT and DOCX consume it,
and every item carries a provenance digest so "exactly once" is
checkable across all three rather than hoped for. The DOCX route makes
ONE `canonical_memoir()` call; the independent lane reads are gone as
executable authorities.

**Browser lifecycle.** The canonical load runs independently of the
facts lane, both completion orders converge on one visible result, a
narrator switch resets memoir state before hydration inside
`lvxSwitchNarratorSafe()`, identical story texts keep separate source
ids, and export is refused while the evidence is loading, unreadable,
incomplete or owned by another narrator.

**Deletion integrity.** The story chain's own cleanup step exposed a
privacy defect: `hard_delete_person` removed every database row,
answered 200, and left eight files on disk — five of them verbatim
narrator speech. `services/narrator_erasure.py` now plans before the
database authority is destroyed, refuses every symlink below the data
root, covers eleven stores, and reports three outcomes truthfully.
Migrations 0049 and 0050 persist the plan and bind it to the canonical
absolute `DATA_DIR` it was built for.

## 4. Acceptance

### 4.1 Story-to-memoir synthetic chain — 11/11 PASSED (2026-08-20)

Live, on the running stack, synthetic narrator only. No family narrator
was touched.

| # | Step | Evidence |
|---|---|---|
| 1 | Real intake creates the narrator | `POST /api/people/intake` 200, `testing_only: true` |
| 2 | Lori asks one natural question | *"During your early school years, what was daily life like when you were attending elementary school in Terre Haute, Indiana?"* — one question, grounded in seeded identity, no compound, no menu |
| 3 | The answer creates ONE preserved story | `trigger=borderline_scene_anchor words=79 anchors=3`; one row |
| 4 | The candidate links to both committed rows | `source_user_turn_row_id=1710`, `completed_assistant_turn_row_id=1711` — the narrator's answer and Lori's reply |
| 5 | Extraction evidence appears in operator review | `extraction: {status: succeeded, method: llm, item_count: 4}` with `turn_linked: true` |
| 6 | Approval and placement land atomically | stale version → **409**; correct version → 200, `promoted` / `early_school_years` / `operator_set` / 1945, version 1→2 |
| 7 | Chronology and Life Map show it | lane `story_evidence: read/1`; Life Map reader counts it in `early_school_years`, `unplaced: 0` |
| 8 | Preview contains it exactly once | 1 occurrence, 1 evidence block, `data-export-exclude="true"`, one `data-source-id` |
| 9 | TXT and DOCX each contain it once | TXT 1; DOCX `word/document.xml` inflated and counted — 1, under *"In their own words — Early School Years"* |
| 10 | A narrator switch shows nothing prior | before hydration: cache dropped, block removed, export refused by ownership; after: 0 evidence lines, chronology `read/0` |
| 11 | Cleanup reports residue explicitly | DB clean; **filesystem residue found and reported, not glossed** — see §5 |

Provenance agreed across all three surfaces: the preview rendered
`data-source-id="0bf8661d1823"` and the DOCX core properties carried
`lorevox-story-sources: captured_stories_early_school_years:0=0bf8661d1823`.

### 4.2 Deletion-integrity acceptance — 10/10 PASSED (2026-08-20)

| # | Step | Evidence |
|---|---|---|
| 1 | Migration 0050 applied | `narrator_erasure_jobs.data_root` present; live jobs record `/mnt/c/hornelore_data` |
| 2 | Clean hard delete | 200 `hard_deleted`, `erasure_complete: true`, 7 files across seven stores including the translation cache |
| 3 | Second synthetic narrator created | via real intake |
| 4 | Controlled filesystem refusal | internal symlink `stories-captured/C → stories-captured/B` — the destructive case |
| 5 | Partial reported honestly | **207** `hard_deleted_partial`, 3 of 4 removed, DB authority gone, job `partial` with the correct root and a 7-entry plan, `retry_available: true` |
| 6 | Obstruction removed only | the link moved aside; its target untouched |
| 7 | Retry through the endpoint | `POST /api/people/{pid}/erase-retry` |
| 8 | Complete, idempotent, audited | 200 `hard_deleted`, active residue zero, job `complete`; audit reads `hard_delete/partial` → `hard_delete_retry/success`; second retry `already_completed: true`, `database_rows_deleted: {}` |
| 9 | Bystander byte-identical | narrator B unchanged at every checkpoint (`89593de7…`, `96c875c2…`) |
| 10 | Stack stopped | by Chris |

### 4.3 Verification method

Every claim in both acceptances was checked against the **filesystem
and direct SQL**, never the response body. A harness that believed the
response would have passed on the exact defect this lane closed — the
body said `hard_deleted` and the files were there.

## 5. Final state

* All synthetic narrators removed; acceptance residue removed.
* **The five family narrators are untouched** — Del, Melanie Zollner,
  Janice, Kent, Christopher Todd Horne.
* `PRAGMA integrity_check` → **ok**.
* **Six pre-existing `harness-test-gate7p2` foreign-key violations in
  `interview_sessions`, unchanged.** None is an acceptance id. They
  predate this lane and are not closed by it.
* Gate B **OPEN**.
* Lean Lori L2 **PARTIAL** and closed by product-priority decision —
  not resumed.
* **The ten-topic Profile Seed onboarding is preserved for new Lorevox
  narrators regardless of narrator type.** Ordinary new-narrator
  reachability is still owed and is the next substantive lane.
* The directive-family registry remains **inert** — built, gated, and
  deliberately not activated.
* Kawa appears in this lane only as frozen legacy UI and as one storage
  directory in the erasure inventory. **It is not an active product
  surface** and nothing here revived it.

## 6. Corrections made during the lane, recorded rather than buried

Each of these was a claim of mine that turned out to be wrong. They are
kept because the pattern matters more than any one of them.

* **A plausible mechanism found by reading source is a hypothesis, not a
  cause.** A missing `drop_order` was written into four governing
  documents as the cause of a failure. Verified afterwards: nothing
  consumed the classification at all. Withdrawn, with the retired text
  quoted.
* **"Operator review never happened"** → corrected to *no retained
  operator-reviewed stories*. **"Extraction output is discarded"** →
  it was durable all along; the gap was a missing join.
* **A guard written against a word fires on the prose that explains the
  word.** Six times in this repository. Every source scan in this lane
  strips comments first and carries a positive control.
* **A test that passes on the defect it was written for is decoration.**
  Mutation testing found survivors in nine separate rounds here, and in
  most of them the survivor was a weakness in my test rather than
  correctness in the code.
* **I contaminated a bystander during the deletion acceptance.** My own
  shell `mkdir` followed the symlink before I moved it aside, writing a
  stray file into narrator B. The product refused that exact link; the
  tool that followed it was me. Corrected and re-verified before
  continuing.

## 7. What this work order does NOT claim

* It does not close Gate B or any Lean Lori phase.
* It does not make Profile Seed reachable for an ordinary new narrator.
* It does not repair the six pre-existing FK orphans.
* It does not activate the directive-family registry.
* It does not remove the frozen Kawa / Memory River UI.
* Safety remains parked, exactly as it was.
