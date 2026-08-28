# Hornelore Trip Companion — Corrected Execution Plan

> # ⚠ SUPERSEDED — HISTORICAL PLAN, NOT CURRENT AUTHORITY
>
> **Banner added 2026-08-28. The body below is unchanged and is kept as history.**
>
> **Do not execute this plan and do not take any status from it.** It describes the state
> of the work on **2026-08-01**; the checkpoint it names, `66d51c9`, is long superseded.
> Derive the live head with `git rev-parse origin/main`.
>
> **Its Photo Palette scalar wording is SUPERSEDED**, and that is the specific reason this
> banner exists rather than a general caution. The authoritative rules are now:
>
> * **A photo is unplaced when it has zero `trip_photo_day_placements`** — never
>   `trip_day_id IS NULL`. The compatibility scalar is `null` for zero **or multiple**
>   placements, so using it to decide "unplaced" silently mis-classifies every multi-day
>   photo.
> * [`WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01_Spec.md`](WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01_Spec.md)
>   and [`WO-TRIP-PHOTO-PALETTE-01_Spec.md`](WO-TRIP-PHOTO-PALETTE-01_Spec.md) own the
>   placement model; [`../architecture/TRAVEL_DOCUMENT_DOCTRINE.md`](../architecture/TRAVEL_DOCUMENT_DOCTRINE.md)
>   ruling 1.16 is the binding doctrine.
>
> **For current state:** [`../../HANDOFF.md`](../../HANDOFF.md). **For the ordered queue:**
> [`../../MASTER_WORK_ORDER_CHECKLIST.md`](../../MASTER_WORK_ORDER_CHECKLIST.md).

**Repository:** `lorevox-hx/hornelore`  
**Branch:** `main`  
**Current pushed checkpoint:** `66d51c9`  
**Status date:** 2026-08-01

---

## 1. Current truthful checkpoint

- Pushed `main` is still `66d51c9`.
- The failed combined Phase 3+4 work is preserved in a stash and is not running.
- Normal `hi` chat works.
- Building Years works.
- No prompt compaction, replacement budgeter, tail trimming, or inference coordinator from the rejected block is deployed.
- The two new untracked files are a study document and a read-only measurement script; neither is loaded by Hornelore at runtime.
- Extraction stabilization through Phase 5 remains banked and pushed.

Lori is back to the behavior she had before the rejected Phase 3+4 changes.

One pre-existing defect remains: the existing general Lori prompt is larger than the 8,192-token window, so the current code silently removes material from the front before generation. The rollback restored the previous working behavior; it did not repair that older hidden problem.

---

## 2. Why Trip Companion work touched Lori at all

The Trip Companion is primarily:

- trip, day, photo, note, and conversation records in the database;
- UI surfaces to edit and organize those records;
- database projection into the Trip Timeline;
- active trip and selected-day state;
- approved photo captions and descriptive context;
- deterministic photo counts and capability answers;
- explicit rules preventing Lori from claiming she sees raw image pixels.

That work does not require redesigning Lori’s identity, language, safety, or interviewing prompt.

A small amount of prompt/context involvement is legitimate because the language model cannot read the database directly. The backend must pass a compact current-turn summary such as:

> Active trip: Bismarck Trip. Current location in the product: Travels shelf. Two photos are attached. No approved image description is available.

That is database-derived context plumbing, not general prompt architecture.

---

## 3. Where the detour occurred

Bismarck testing exposed a separate real infrastructure problem:

- browser and backend both extracted completed turns;
- system directives were sent to extraction;
- extraction ran through Lori’s full chat composer;
- duplicate model calls competed with chat;
- the system became slow and unresponsive.

That justified the extraction stabilization work. Those fixes are pushed and retained.

The detour came afterward when the inference coordinator and a general chat-prompt budget rewrite were combined. The budget rewrite was not required for the Trip Companion and broke ordinary `hi` chat. That combined block was rejected and stashed.

The final real-token measurement localized the pre-existing prompt problem:

- `default_core`: 4,069 tokens;
- `english_first_rule`: 849 tokens;
- `lori_runtime_directives`: 3,612–3,613 tokens.

Those three existing blocks alone total about 8,530 tokens, before adding profile context, identity facts, memory, current narrator text, chat-template overhead, or answer reserve.

Trip and Life Map context are small by comparison. The pre-existing general Lori prompt—not the Trip Companion—is the source of the overflow.

---

# REVISED TRIP COMPANION EXECUTION ORDER

## Gate 1 — Freeze Lori infrastructure

Do not restore the combined Phase 3+4 stash.

Do not change during WO1E, WO2 acceptance, cleanup, or Photo Palette:

- Lori’s general core prompt;
- English-first/language rules;
- safety rules;
- model configuration;
- Whisper configuration;
- TTS configuration;
- generic chat budgeting;
- generic prompt trimming.

The current baseline is working well enough to finish the pending Trip Companion work.

---

## Gate 2 — Complete WO1E now

### WO-TRIP-NARRATOR-BRIDGE-01E
**Purpose:** Complete the clean Bismarck Narrator-shelf browser and restart acceptance.

### Browser run

1. Open Christopher in Narrator.
2. Open Travels.
3. Open the Bismarck Trip.
4. Tell the gravesite/schools/Melanie story.
5. Ask the exact photo question.
6. Close the Narrator session normally.

### Verify before restart

- trip remains `completed`;
- conversation placement is `travels_shelf_trip`;
- conversation status is `needs_day`;
- no day is inferred;
- exactly one conversation link exists for the tested turn;
- exactly one review-only story candidate exists;
- candidate has `trip_day_id=NULL`;
- photo answer states the correct attached count;
- Lori makes no raw-image or pixel-vision claim;
- no family-truth write occurs;
- no duplicate candidate exists;
- no generic `reason=error`;
- no shape exception.

### Restart verification

Chris performs the normal manual restart:

```bash
cd /mnt/c/Users/chris/hornelore
bash scripts/stop_all.sh && bash scripts/start_all.sh
```

Then verify:

- same conversation-link ID;
- same user and assistant turn-row IDs;
- same transcript hashes;
- same story-candidate ID;
- no duplicate link;
- no duplicate candidate;
- trip remains completed;
- placement remains `needs_day`.

### Decision rule

- If WO1E passes, Work Order 1 is complete.
- If it fails because of a specific trip-placement, count, or persistence defect, fix only that defect.
- If it produces direct evidence that chat and extraction overlap and destabilize generation, stop and open the Phase 3 coordinator work order alone.
- A WO1E failure does not automatically reopen prompt architecture.

---

## Gate 3 — Complete WO2 acceptance

### WO-LIVE-TRIP-COMPANION-02
**Purpose:** Accept the existing Editable Timeline implementation without adding features.

Required stages:

1. `capture`
2. Browser Stage A
3. `checkpoint`
4. Browser Stage B
5. manual restart
6. `verify`
7. restore Bismarck Day 1 placement
8. `restore-verify`

### Stage A must prove

- dirty guard appears and preserves unsaved typing;
- one day-text field can be edited;
- one existing note can be edited;
- one photo caption can be edited;
- caption editing does not grant Lori approval;
- one quick note is added exactly once;
- removing a photo from a day keeps the same link and underlying photo;
- removed photo has `trip_day_id=NULL`;
- transcript rows and hashes remain unchanged.

### Stage B must prove

- removed photo can be assigned to Day 2;
- existing conversation can be moved to Day 2;
- movement keeps the same link IDs;
- placement becomes operator-selected/confirmed;
- modal close/reopen retains a usable selected-day state;
- rail counts agree with actual rows.

### Restart and restore must prove

- all changes survive restart;
- no duplicate photo or conversation links;
- photo and conversation can be restored to Day 1;
- original link IDs remain;
- caption remains unapproved unless explicitly approved;
- quick note remains exactly once;
- final rail counts agree with the timeline rows.

No new timeline feature work is allowed during this acceptance gate.

---

## Gate 4 — Clean contaminated test artifacts

### WO-LIVE-TRIP-CLEANUP-01

After WO1E and WO2 evidence is preserved:

- identify every artifact created during the contaminated testing period;
- map each artifact to source surface and source turn;
- preserve genuine Bismarck memories;
- reversibly hide `say that again` and other command/test noise;
- place meaningful Needs-a-day conversations deliberately;
- do not physically delete evidence unless Chris explicitly approves;
- remove stale or misleading reports;
- retain only truthful final acceptance evidence.

---

## Gate 5 — Build Photo Palette

### WO-TRIP-PHOTO-PALETTE-01

Begin only after WO2 acceptance and cleanup.

Build inside the existing Trip Timeline modal using the existing trip-photo links and day-placement data.

Core requirements:

- `Timeline | Photo Palette` mode switch;
- no nested modal or second backdrop;
- shared current trip and selected day;
- filters for All, Not assigned, each day, Needs review, and Hidden;
- Not assigned means `trip_day_id IS NULL`;
- explicit multi-selection and batch movement;
- remove-from-day, hide, restore, and delete remain distinct;
- no Delete action in the Palette MVP;
- caption editing does not grant Lori approval;
- attached, assigned, and approved-for-Lori statuses are displayed separately;
- no raw storage path or raw GPS in UI payloads;
- live browser and restart acceptance.

---

# SEPARATE FOLLOW-UP WORK ORDER

## WO-LORI-PROMPT-ARCHITECTURE-01
### Repair the pre-existing oversized Lori prompt

**Priority:** Separate infrastructure follow-up  
**Does not block:** WO1E, WO2 acceptance, cleanup, Photo Palette  
**Must be complete before:** Daily Digest, full Travelogue generation, and other long-context Lori generation features  
**Baseline:** Start from a clean pushed checkpoint after the current Trip Companion gates  
**Do not restore:** the rejected Phase 4 budget/trimming implementation

---

## A. Problem statement

The existing general Lori prompt exceeds the configured 8,192-token model window before meaningful narrator context is added.

Measured plain-`hi` final prompt sizes:

- Christopher: 9,013 tokens;
- Janice: 8,965 tokens;
- Kent: 8,985 tokens;
- Melanie: 8,898 tokens.

Measured dominant blocks:

- `default_core`: 4,069 tokens;
- `english_first_rule`: 849 tokens;
- `lori_runtime_directives`: 3,612–3,613 tokens.

The current code resolves the overflow by retaining the final 8,192 tokens and silently discarding tokens from the front. In the measured plain-`hi` cases, it removed about 706–821 leading tokens, including Lori’s opening identity, name-origin explanation, Life Archive purpose, and opening role boundary. The measured acute-safety and `988` markers remained, but silent front removal is still unacceptable.

This is a pre-existing general Lori architecture defect. It was not caused by the Trip Companion.

---

## B. Goals

- Keep Lori’s essential identity, purpose, safety, fact-humility, and conversational posture intact.
- Include only rules relevant to the current turn.
- Preserve the current narrator turn verbatim.
- Preserve compact active-task context such as the selected trip, day, photo, or Life Map era.
- Reserve enough tokens for Lori’s response.
- Count the actual final prompt after the production chat template.
- Eliminate all blind front and tail slicing.
- Make omission decisions explicit, section-based, logged, and testable.
- Preserve existing product behavior unless a documented compaction decision changes it.

---

## C. Non-goals

This work order does not:

- change `MAX_CONTEXT_WINDOW`;
- change the model;
- change quantization, GPU offload, or serving configuration;
- redesign extraction;
- redesign Whisper or TTS;
- rewrite Trip Companion storage or UI;
- add new Lori features;
- restore the rejected Phase 4 files wholesale;
- use character estimates as acceptance evidence.

---

## D. Phase A — Structured composer with no behavior change

Create an internal structured representation such as:

```text
section_id
priority_tier
required
source
trim_policy
text
```

Recommended section families:

- `core_identity`
- `core_safety`
- `core_interview_posture`
- `language_policy`
- `identity_facts`
- `identity_grounding`
- `active_task_context`
- `session_runtime`
- `conversation_memory`
- `recent_history`
- `current_turn`

Requirements:

- existing public composer can still return a joined string;
- joined output remains equivalent before compaction;
- no budgeting or omission behavior in this phase;
- no production response change is claimed.

Acceptance:

- real production-sized fixtures for all four narrators;
- exact section IDs and real-token counts;
- normal `hi` works;
- Building Years works;
- no database writes beyond normal chat behavior;
- manual restart smoke passes.

Commit Phase A separately.

---

## E. Phase B — Compact measured offenders at the source

### B1. Compact `default_core`

Preserve:

- Lori identity and name;
- Lorevox meaning and Life Archive purpose;
- essential oral-history posture;
- one-question discipline;
- fact humility;
- anti-invention boundaries;
- acute-safety behavior;
- critical transparency/capability rules.

Move, shorten, gate, or remove from every-turn injection:

- long worked-example libraries;
- repeated positive/negative examples;
- inactive mode instructions;
- duplicated language material;
- feature-specific rules already supplied by runtime sections.

### B2. Compact English-first

Replace the 849-token always-on example library with a concise policy that preserves:

- English remains English despite foreign place names, food terms, and accented words;
- language changes only through explicit preference or genuine sustained foreign-language narration;
- narrator’s foreign words remain verbatim;
- translation occurs only when requested.

### B3. Split runtime directives by active branch

The 3,612-token runtime block must no longer inject instructions for every possible state.

A normal ready narrator turn should not receive inactive instructions for:

- onboarding;
- helper mode;
- unrelated cognitive modes;
- unused session styles;
- inactive factual chains;
- unused camera/photo states;
- unrelated interview passes;
- other role branches.

Each runtime subsection must have a named activation condition.

Acceptance after each B subphase:

- real-token counts for all four narrators;
- normal `hi`;
- Building Years;
- one safety route;
- one language route;
- one active-trip route;
- no loss of required identity or safety markers;
- no broad mutation campaign.

Commit B1, B2, and B3 separately unless one is genuinely inseparable.

---

## F. Phase C — Real-token budget and omission policy

Only after source compaction has created adequate headroom.

For a normal 512-token response and 128-token safety margin:

```text
maximum final prompt = 8192 - 512 - 128 = 7552 tokens
```

Requirements:

- count after the real production chat template;
- use the request’s actual output reserve;
- preserve mandatory identity and safety;
- preserve the complete current narrator turn;
- preserve active task context;
- remove oldest history only at whole-message boundaries;
- omit optional named sections by declared priority;
- never slice raw token arrays from the front or tail;
- fail visibly only when mandatory core plus current turn genuinely cannot fit;
- log section IDs and token counts, not narrator prose.

Required tiers:

1. mandatory core and safety;
2. current narrator turn;
3. active task context;
4. relevant identity facts;
5. recent conversation;
6. optional memory/RAG/examples.

Commit Phase C separately.

---

## G. Remove blind chat slicing

After Phase C is accepted:

- remove every generic `[:, -MAX_CONTEXT_WINDOW:]` chat slice;
- verify non-streaming, streaming, and WebSocket chat paths;
- extraction remains on its existing bounded raw path;
- no fallback may silently reintroduce front or tail slicing.

---

## H. Required automated evidence

Tests must use realistic prompt fixtures generated from the production composer and real narrator-shaped runtime data.

Required cases for all four narrators:

- plain `hi`;
- ordinary conversation;
- Building Years;
- active Bismarck Trip;
- selected trip photo;
- realistic recent history;
- long but valid narrator turn;
- mandatory-core-plus-turn cannot fit;
- old-history removal at whole-message boundaries;
- inactive runtime branches are absent;
- required identity and safety markers are present.

A budget test whose fixtures are smaller than the production floor is invalid.

---

## I. Required live acceptance

For each narrator:

1. `hi` produces a normal Lori response.
2. Building Years produces one appropriate question.
3. Active trip context produces a relevant response without losing Lori’s identity.
4. Selected photo context is handled without a raw-image claim.
5. Recent history remains coherent.
6. Final templated prompt stays inside the real ceiling.
7. No blind truncation log appears.
8. User and assistant turns persist correctly.
9. Browser receives the response.
10. Manual restart preserves behavior.

Also verify one acute-safety route and one language route.

---

## J. Completion gate

WO-LORI-PROMPT-ARCHITECTURE-01 is complete only when:

- structured composer is pushed;
- measured offenders are compacted;
- real-token budget is enforced;
- blind chat slices are removed;
- all four narrators pass automated and live cases;
- normal `hi` and Building Years pass after restart;
- no required identity or safety marker is missing;
- final counts and feature-state documentation are committed;
- no raw narrator prose appears in reports.

---

# PHASE 3 COORDINATOR FOLLOW-UP

## WO-INFERENCE-COORDINATOR-01

The generation coordinator remains separate from prompt architecture.

Open this work order only:

- if WO1E produces direct evidence of chat/extraction overlap; or
- after the core Trip Companion acceptance gates are complete.

Scope only:

- chat Llama generation;
- extraction Llama generation;
- warmup Llama generation.

Do not automatically include Whisper or TTS.

Acceptance must prove:

- real Lori answer generated, persisted, and delivered;
- deliberate extraction preemption;
- same claim resumes;
- no partial extraction result;
- exactly one final result row;
- peak Llama generation concurrency equals one;
- restart survival.

Never combine this work order with WO-LORI-PROMPT-ARCHITECTURE-01.

---

# Remaining product order after Photo Palette

1. WO-SESSION-HEALTH-TRANSCRIPT-01
2. WO-TRIP-STRUCTURED-DAY-CONTENT-01
3. WO-LORI-PROMPT-ARCHITECTURE-01
4. WO-TRIP-DAILY-DIGEST-01
5. WO-TRIP-TRAVELOGUE-COMPILER-01
6. WO-INFERENCE-COORDINATOR-01 if not already required
7. WO-TRIP-RELIABILITY-OFFLINE-01

Prompt architecture must be complete before Daily Digest and Travelogue generation.

---

# Working rules

- One work order at a time.
- One concern per commit.
- Basic product smoke before a large suite.
- Unit tests prove mechanisms; browser acceptance proves product outcomes.
- Lock acquisition is not a successful conversation.
- Acceptance scripts never start or stop Hornelore.
- Chris performs manual restarts.
- No mutation campaign unless it closes a known acceptance defect.
- A failed live regression is stashed or rolled back immediately.
- Every work block ends as either pushed and accepted, or preserved and rolled back.
- No new diagnostic instrument unless a specific acceptance failure cannot be explained from existing evidence.
- No prompt work may be inserted into Trip Companion work orders.

---

# Immediate instruction to Claude

The plan is corrected and locked.

1. Freeze the rejected Phase 3+4 stash.
2. Make no general Lori prompt, model, STT, or TTS changes now.
3. Complete WO1E on pushed `66d51c9`.
4. Complete WO2 staged browser/restart/restore acceptance.
5. Clean contaminated test artifacts.
6. Build Photo Palette.
7. Record the pre-existing prompt defect under `WO-LORI-PROMPT-ARCHITECTURE-01`.
8. Do not begin that prompt work order until Photo Palette is accepted, unless a direct current product failure makes it unavoidable.
9. Complete prompt architecture before Daily Digest or Travelogue generation.
10. Open the Phase 3 coordinator separately only upon direct contention evidence or after the core Trip Companion gates.

The Trip Companion remains database, projection, UI, and compact current-trip context work. General Lori prompt redesign is now explicitly separated.
