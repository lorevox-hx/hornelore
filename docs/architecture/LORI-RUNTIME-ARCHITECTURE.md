# LORI-RUNTIME-ARCHITECTURE

**Status:** ACTIVE — architectural decision record (synthesis document)
**Date:** 2026-05-24

> ## ⚠️ AMENDMENT 2026-08-14 — STAGE 1 IS INACTIVE AT RUNTIME
>
> **Nothing below is retracted; the nine-stage model still describes the pipeline's shape.**
> But this ADR predates the safety park and, read cold, it tells a reader that Stage 1
> classifies every turn. **It does not.**
>
> `WO-LEAN-LORI-RUNTIME-01` §3C **parked the entire runtime safety feature** on 2026-08-04
> (`docs/decisions/2026-08-04-park-safety-feature.md`). In the parked state the LLM safety
> classifier performs **zero generations**, the safety protocol contributes **zero prompt
> tokens**, and deterministic scanning is inactive on both the WebSocket and the legacy REST
> path. The state is server-authoritative via `HORNELORE_SAFETY_STATE` (`flags.py:250-275`),
> **defaults to `parked`**, and an unrecognised value resolves to `parked` deliberately so a
> typo cannot switch the family back on.
>
> **Parked is not deleted.** Every module, corpus and test is preserved — that is the point of
> parking rather than removing, and `tests/test_safety_parked.py` (54 tests) proves it.
> **Reactivation is Chris's explicit decision, never an environment value.**
>
> So when reading **Stage 1 — Safety Classification** below: it is the design of record and
> what reactivation lands on, **not a description of what runs today.** Current state:
> `docs/wo/WO-LEAN-LORI-PHASE-0-MAP-2026-08-14.md`.
**Decision owner:** Chris Horne
**Type:** Architectural Decision Record (ADR) — not a Work Order
**Companion to:** `HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md`

---

## TL;DR

Lori is not an interviewer with safety bolted on. Lori is a story listener
whose behavior is shaped by a nine-stage deterministic runtime pipeline.
The LLM call is one stage of nine — most of the gates that determine
whether Lori behaves well are rule-based checks happening before and
after the model is asked anything.

This document names the pipeline, defines each stage's contract, points
at the WO that implements each stage, and explicitly resolves the
original `WO-INTERVIEW-PROCESS-REDESIGN-01` turn-mode list against
current architecture so unbuilt scope doesn't haunt future work.

The companion document `HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md` answers
*who is Lori for and what kind of project is this*. This document
answers *what is the control flow that produces Lori's behavior*.

---

## The pipeline

```
Narrator Turn
   ↓
[1] Safety Classification
   ↓
[2] Story Momentum
   ↓
[3] Session Style + Mode Resolution
   ↓
[4] Question Hierarchy Gate
   ↓
[5] Composition (LLM call)
   ↓
[6] Reflection Grounding Validator
   ↓
[7] Thread Bank
   ↓
[8] Bio Anchored Asker
   ↓
[9] Communication Control Wrapper
   ↓
Lori Response
```

Stages 1-4 run **before** the LLM. They shape what prompt is assembled
and what behaviors are permitted.

Stage 5 is the LLM call itself.

Stages 6-9 run **after** the LLM. They validate, augment, and constrain
what the model produced. Failures trigger regeneration; persistent
failures fall back to deterministic templates.

This is not a microservices architecture — most stages are functions in
the composition pipeline within `chat_ws.py` and `prompt_composer.py`.
But the conceptual separation is load-bearing: each stage has a single
responsibility, a defined input contract, and a defined output contract.
Stages can be tested in isolation. New behaviors are added by extending
or inserting stages, not by complicating prompts.

---

## Stage definitions

### Stage 1 — Safety Classification

**Implements:**
- `WO-LORI-SAFETY-PAST-TENSE-ACKNOWLEDGE-01` (sibling spec)
- Existing `SAFETY-INTEGRATION-01` Phase 0+1 (landed)

**Input:** Narrator turn text, conversation history, current session state.

**Output:** One of five routing decisions:
- `acute` — present-tense self-directed ideation; 988 dispatched, operator notified
- `past_tense_acknowledge` — past-tense memoir ideation; deterministic acknowledgment bank
- `mortality_reflection` — normal older-adult mortality talk; no Lori action, classifier suppresses false escalation only
- `pattern_triggered` — regex-side detector fired regardless of LLM classification; routes acute
- `none` — no safety signal; continue to stage 2

**Contract:** Safety classification is always the first stage. It can short-circuit
all subsequent stages (acute / past_tense_acknowledge paths skip directly to a
deterministic response). It uses three classifier dimensions: `category`,
`tense`, `subject`. The pattern-side detector retains authority — if patterns
fire, the LLM tense/subject classification cannot override.

**Why first:** Safety overrides everything else, including oral-history posture
and chapter momentum. The system must not be in a state where a different
stage's logic prevents safety from firing.

---

### Stage 2 — Story Momentum

**Implements:**
- `WO-LORI-STORY-FIRST-PHASE-1-01` (piece 2 of 4)

**Input:** Narrator turn text plus last 4 narrator turns from session state.

**Output:** Momentum score `0.0 - 1.0` with thresholds:
- `>= 0.6` → **story mode active** — suppress Layer 3-4 questions, suppress thread bank surfacing, suppress bio anchored asking
- `>= 0.4` → **story mode emerging** — prefer Layer 1-2 continuations
- `< 0.4` → **normal mode** — full question hierarchy and gate logic available

**Contract:** Rule-based composite score from seven cheap signals
(word count, named entity count, temporal markers, sensory tokens,
sequence markers, dialogue presence, uninterrupted run). Phase 1 ships
the rule-based version; Phase 2+ may upgrade to an LLM-derived signal,
but the score interface remains `0.0-1.0` for downstream consumers.

**Why second:** Momentum is the primary input to which prompt block is
assembled and which gates fire. Computing it cheap and deterministic
makes the rest of the pipeline's behavior reproducible.

---

### Stage 3 — Session Style + Mode Resolution

**Implements:**
- `WO-LORI-ORAL-HISTORY-DEFAULT-01` (default flip + per-style parameter table)
- Existing session-style infrastructure (`WO-UI-SHELL-01`,
  `WO-SESSION-STYLE-WIRING-01`, etc.)

**Input:** Session row (`session_style` column), momentum from stage 2,
softened-mode state from `db.get_softened()`.

**Output:** Effective composition mode, one of:
- `oral_history_normal` — default; full Phase 1 substrate active
- `oral_history_story` — momentum >= 0.6 in oral_history style
- `warm_storytelling_normal` / `warm_storytelling_story`
- `companion_normal` / `companion_story`
- `memory_exercise_normal` (if implementation exists — see memory_exercise decision)
- `questionnaire_first_normal` — orchestrator runs; thread bank inactive
- `softened_acute` — N=5 turns after acute trigger
- `softened_past_tense` — N=2 turns after past-tense trigger
- `softened_exiting` — one-turn recovery state after softened expires

**Contract:** Effective mode is the deterministic product of session style
and current state. It determines which prompt block is assembled, which
per-style parameters apply (word cap, momentum thresholds, ladder values),
and which downstream stages are active vs vacuous.

Softened-mode states (`softened_acute`, `softened_past_tense`,
`softened_exiting`) override session-style modes — when softened state is
active, the session-style mode is computed but not used; the softened
mode wins until the counter expires.

**Why third:** Session style is the operator's posture choice; momentum
is the moment's posture signal; softened mode is the safety system's
posture override. Resolving all three into a single effective mode here
means downstream stages only need to consult one value.

---

### Stage 4 — Question Hierarchy Gate

**Implements:**
- `WO-LORI-STORY-FIRST-PHASE-1-01` (piece 4 of 4)

**Input:** Effective mode from stage 3, session-level question-layer-success
history, current chapter context (last 3-5 narrator turns).

**Output:** Per-layer eligibility:
- `L1_eligible: True` — Layer 1 (open recall) always eligible
- `L2_eligible: True/False` — eligible if session has at least one
  substantive narrative turn
- `L3_eligible: True/False` — eligible only if L2 has succeeded AND
  momentum < 0.6 AND mode is not `softened_*`
- `L4_eligible: True/False` — eligible only if L2 has succeeded AND
  specific ambiguity exists in current composition

**Contract:** Hard rule (code-enforced): no Layer 3 or Layer 4 question
unless Layer 1 or Layer 2 has already succeeded in the current session.
This rule cannot be overridden by prompt instructions to the LLM — it
is enforced post-composition by the validator (stage 6 family).

Question layer is determined post-composition by classification of Lori's
output. If the composed question is in an ineligible layer, regeneration
fires up to 2 times; if all regenerations fail, a deterministic
continuation template replaces the question.

**Why fourth:** The hierarchy gate shapes what the LLM is told it may ask
in this turn. Without this stage, the model often defaults to Layer 3-4
questions (chronology, verification) when narrator material is rich
enough to support them, which is exactly when the chapter should be
allowed to breathe instead.

---

### Stage 5 — Composition (LLM call)

**Implements:**
- Existing `prompt_composer.py` extended by every Phase 1 piece
- Llama 3.1 8B Instruct, 4-bit quantized, hosted at port 8000

**Input:** Assembled prompt containing:
- `LORI_INTERVIEW_DISCIPLINE` block (from `SESSION-AWARENESS-01` Phase 2)
- Effective mode's prompt block (e.g., `LORI_SOFTENED_RESPONSE`,
  `LORI_RECOVERING_RESPONSE`, oral-history-specific guidance)
- Question hierarchy guidance (which layers are eligible)
- Recent narrator turns
- Reflection grounding guidance (concrete content tokens to reference)
- Story momentum context
- Existing `chronology_context`, `memoir_context`, `projection_family` blocks

**Output:** Lori's composed response text.

**Contract:** The LLM call is one stage of nine. It does not have authority
over safety routing (stage 1), mode resolution (stage 3), or question
hierarchy enforcement (stage 4 + 6). It composes within the prompt
shape these stages produce.

For deterministic-response paths (`acute`, `past_tense_acknowledge`,
parts of `softened_exiting`), the LLM is not called at all — the response
comes from a curated bank.

**Why fifth:** Composition happens after all behavior-shaping decisions
are made and before all validators run. Centralizing the LLM call here
means prompt assembly is bounded and validators have a known input.

---

### Stage 6 — Reflection Grounding Validator

**Implements:**
- `WO-LORI-STORY-FIRST-PHASE-1-01` (piece 1 of 4)
- Replaces existing shallow reflection check from
  `WO-LORI-REFLECTION-01`

**Input:** Lori's composed response from stage 5, narrator's most recent turn.

**Output:** Pass/fail. On fail: regeneration request (up to 2 retries),
then deterministic reflection-template fallback.

**Contract:** First 1-2 sentences of Lori's response must contain at
least one content token from the narrator turn OR a semantically similar
paraphrase (embedding similarity above threshold). Generic empathy
phrases ("that sounds difficult", "I can imagine", "thank you for
sharing") are explicitly forbidden — regeneration fires on detection.

In softened modes, this validator runs but is partially vacuous —
softened mode permits short acknowledgments which may or may not contain
narrator content tokens depending on what the narrator turn was. The
validator's forbidden-phrase check still applies (no generic empathy
even in softened mode).

**Why sixth:** Reflection grounding is the first post-LLM validator
because it determines whether the response respects the narrator's
material. If grounding fails, no downstream augmentation matters.

---

### Stage 7 — Thread Bank

**Implements:**
- `WO-LORI-STORY-FIRST-PHASE-1-01` (piece 3 of 4)

**Input:** Narrator's most recent turn (for extraction), Lori's composed
response from stage 5 (for surfacing decision), session state, effective
mode.

**Output (two sub-stages):**

7a — Extraction (always runs):
- Named-entity recognition on narrator turn
- New entities written to `interview_threads` as `open`
- Deduplication against existing open threads

7b — Surfacing (conditional):
- Only runs when mode is `oral_history_normal`, `warm_storytelling_normal`,
  `companion_normal`, or `memory_exercise_normal` AND momentum < 0.4
  AND no thread has been surfaced in the last 4 turns
- If eligible: select oldest open thread, augment Lori's composed
  response to include the surfacing prefix
- Surfacing template: `"Earlier you mentioned {anchor}. {connecting} {open_question}"`

**Contract:** Extraction is always-on. Surfacing is suppressed in story
mode, in questionnaire_first mode, and in all softened modes. The bank
persists across stack restarts (DB-backed). Operator may eventually mute
threads (deferred operator-UX work).

**Why seventh:** Thread surfacing happens after composition so it can
either replace or augment what the LLM produced. Thread extraction
happens here so it benefits from the same narrator-turn context the
validators just used, without re-parsing.

---

### Stage 8 — Bio Anchored Asker

**Implements:**
- `WO-LORI-BIO-BUILDER-UNIVERSAL-01` (Tier 3)

**Input:** Bio gaps for current narrator (from `bio_facts` table where
status is `empty`), chapter context (last 3-5 narrator turns), effective
mode, frequency cap state.

**Output:** Optional augmentation of Lori's composed response with an
anchored bio question, OR no-op.

**Contract:** Fires only when:
- Mode is `oral_history_normal`, `warm_storytelling_normal`,
  `companion_normal`, or `memory_exercise_normal`
- Momentum < 0.4
- 4+ narrator turns have elapsed since last anchored ask
- Session has had fewer than 3 anchored asks total
- Chapter context matches at least one `asking_anchors` pattern for an
  empty `narrative_value='high'` bio field
- Thread bank (stage 7b) did NOT surface a thread this turn (one
  augmentation max per turn)

Anchored ask composition uses LLM with explicit guidance to phrase
chapter-naturally; never replaces composition entirely.

**Why eighth:** Bio anchored asking is the last augmentation stage
because it competes with thread surfacing for the same compositional
slot. Putting it after thread bank gives narrative continuity priority
over bio completeness (deliberate — narrative is the memoir, bio is
the index).

---

### Stage 9 — Communication Control Wrapper

**Implements:**
- Existing `WO-LORI-COMMUNICATION-CONTROL-01` (landed)
- Extended by `WO-LORI-ORAL-HISTORY-DEFAULT-01` per-style parameters
- Extended by `WO-LORI-SOFTENED-MODE-PERSISTENCE-01` softened caps

**Input:** Lori's response (composed + possibly augmented by stages 7-8),
effective mode, per-mode parameters.

**Output:** Final response, with enforcement of:
- Word cap (per-mode)
- Question count cap (per-mode)
- Atomicity check (no compound questions)
- Acute-safety exemption (no truncation of safety responses)

**Contract:** Final guard before the response goes out. Enforces
deterministic limits that no upstream stage is authorized to override.
The wrapper exists per the STA-grounded architecture rationale (Wang
et al. 2025) — prompt engineering alone is fragile at the scale the
system needs.

In softened modes, word caps tighten (acute=30, past_tense=35, exiting=50);
question count drops to 0. In story mode, caps stay at the session-style
default (the cap is about turn density, not turn shape).

**Why last:** Communication control runs last because it is the
unconditional final word on response shape. Any earlier stage producing
output that violates a cap or atomicity rule is wrong by definition; the
wrapper catches it.

---

## Stage interaction matrix

This matrix shows which stages are active in which effective mode. A "✓"
means the stage runs and influences the response; "vacuous" means the
stage runs but produces a no-op result; "—" means the stage is bypassed.

| Stage | oral_history | story mode | softened (acute) | softened (past_tense) | exiting | questionnaire_first |
|---|---|---|---|---|---|---|
| 1. Safety classification | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 2. Story momentum | ✓ | ✓ | vacuous | vacuous | vacuous | ✓ |
| 3. Mode resolution | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 4. Question hierarchy | ✓ | L3-4 suppressed | all suppressed | all suppressed | all suppressed | L1-4 available |
| 5. LLM composition | ✓ | ✓ | — (bank) | — (bank) | ✓ | ✓ |
| 6. Reflection grounding | ✓ | ✓ | vacuous | vacuous | ✓ | ✓ |
| 7a. Thread extraction | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 7b. Thread surfacing | ✓ | — | — | — | — | — |
| 8. Bio anchored asker | ✓ | — | — | — | — | — |
| 9. Communication control | ✓ | ✓ | ✓ tight | ✓ tight | ✓ moderate | ✓ |

This matrix is testable. Every cell corresponds to a code path that can
be exercised in isolation. Future regression tests should cover the
matrix exhaustively rather than testing arbitrary scenarios.

---

## Resolution of the original turn-mode list

The original `WO-INTERVIEW-PROCESS-REDESIGN-01` document proposed seven
turn modes. After the trio + Phase 1 + oral-history-default WOs, those
seven resolve to current architecture as follows:

| Original turn mode | Resolution in current architecture |
|---|---|
| Orientation mode | Absorbed into session-creation composition logic and Layer 1 (open recall) of the question hierarchy. Not a separate stage. |
| Story Capture mode | Replaced by stage 2 (momentum) + Layer 3-4 suppression in stage 4 + thread bank in stage 7. Same behavior, deterministically gated rather than mode-flagged. |
| Timeline Anchor mode | Replaced by bio anchored asker (stage 8) when chapter context provides anchor; absorbed into Layer 3 of question hierarchy otherwise. |
| Memory Echo mode | Not yet covered by drafted WOs. Worth a small dedicated WO when the "what did you know about me" surface is built. Distinctive composition shape (narrator-facing summary). Low urgency. |
| Clarification mode | Absorbed into Layer 4 of the question hierarchy. Single ambiguity repair only when actual ambiguity exists in current composition. |
| Companion mode | Existing session style, not a turn mode. Selectable by operator. |
| Safety / Softened mode | Implemented by trio (past-tense + softened-mode-persistence WOs). |

Net result: 4 covered by current architecture, 2 absorbed into existing
infrastructure, 1 pending (Memory Echo).

The Memory Echo WO is the only piece of unbuilt scope from the original
redesign document. It should be drafted when the "what did you know
about me" narrator-facing surface is being built; not urgent today.

---

## What this architecture is and is not

**This architecture IS:**
- A nine-stage deterministic pipeline producing every Lori response
- Testable per-stage and per-mode via the interaction matrix
- The synthesis point that the seven WO specs assemble into
- Designed to extend by inserting/extending stages, not by complicating prompts
- The technical anchor for everything beyond Phase 1 of the redesign

**This architecture IS NOT:**
- A microservices design (most stages are in-process functions)
- A complete reimplementation (most stages already exist; this doc
  names the synthesis)
- A workflow engine or DAG framework (the pipeline is hardcoded in
  `chat_ws.py` and `prompt_composer.py`)
- A real-time UI (the pipeline runs once per narrator turn)
- An API specification (stages have internal contracts, not REST
  endpoints)

---

## Stage contracts as code locations

Approximate file map after all drafted WOs land. Useful as a
mental model for where to look when debugging a specific stage's
behavior.

| Stage | Primary file | Secondary files |
|---|---|---|
| 1. Safety | `services/safety_classifier.py` | `services/safety.py` (pattern-side), `services/safety_acknowledgments.py` (bank) |
| 2. Momentum | `services/story_momentum.py` | — |
| 3. Mode resolution | `services/prompt_composer.py` (mode dispatch) | `api/db.py` (softened state), `services/session_loop_orchestrator.py` (style-based gating) |
| 4. Question hierarchy | `services/question_hierarchy.py` | `services/lori_communication_control.py` (validator) |
| 5. LLM composition | `services/prompt_composer.py` | upstream Llama 3.1 8B service |
| 6. Reflection grounding | `services/reflection_grounding.py` | `services/lori_communication_control.py` (validator) |
| 7. Thread bank | `services/thread_bank.py` | `api/db.py` (`interview_threads` table) |
| 8. Bio anchored asker | `services/bio_anchored_asker.py` | `services/bio_schema.py`, `services/bio_fact_router.py` |
| 9. Communication control | `services/lori_communication_control.py` | per-style parameter table |
| Pipeline orchestration | `api/chat_ws.py` | — |

This map is the closest thing the system has to "an architecture
diagram." Pin it in your operator runbook or repo root README so future
contributors (and future you) can navigate the codebase by stage
responsibility rather than by file proximity.

---

## Diagnostic contract

When a Lori response is wrong, the diagnostic path is:

1. **Identify which stage produced the wrong behavior.** If safety
   should have fired but didn't: stage 1. If the response was too
   long: stage 9. If a Layer 3 question fired when story mode was
   active: stage 4. If reflection was generic: stage 6.

2. **Check that stage's input contract.** Was the stage given correct
   inputs? (Often the bug is upstream — wrong momentum score caused
   the wrong gate decision.)

3. **Check that stage's output contract.** Did the stage produce a
   structurally valid output that downstream stages misused?

4. **Fix at the right stage.** Resist fixing the prompt when the bug
   is in a validator, and vice versa.

This diagnostic contract is what makes the runtime architecture
materially better than prompt-tuning: when something is wrong, the
investigation has a path, and the fix has a known scope.

---

## Truth-write observability (Gate 7)

**Added 2026-07-30, TRUTH-PIPELINE-01 Phase 1.** The diagnostic contract
above answers *which stage produced the wrong words*. It said nothing
about *whether the turn wrote anything down*, and for two months that
gap was filled by a single number from an archived probe:
`speaker_zero_delta`, glossed as **"turn did not write anywhere"**.
Phase 1 exists because that number could not be read. It had at least
four incompatible meanings and no way to choose between them.

### What is instrumented

Five truth-write stages, one `mark()` call site each, correlated to a
turn by `contextvars` rather than by threading an id through the call
chain:

| Stage | Call site | Fires on a chat_ws turn? |
|---|---|---|
| `raw_turn_saved` | `db.py`, after `persist_turn_transaction` | **Yes, always** |
| `archive_event_created` | `archive.py`, after the JSONL append | **Yes, always** (twice) |
| `extract_fields_called` | `services/turn_extraction.py::_mark_probe`, reached by both `/api/extract-fields` and the chat_ws completed-turn path (moved there 2026-07-30; it was `routers/extract.py`) | **Yes on an interview turn, since 2026-07-30.** Corrected in place: this cell read *"No — and that is the defect"*, which was true from Phase 1's reading until Phase 2 landed the same day |
| `family_truth_written` | `db.py`, in `ft_add_note` / `ft_add_row` | **No, by design** |
| `projection_updated` | `services/projection_writer.py` | **Only on a correction turn** |

The probe is default-OFF behind `HORNELORE_TRUTH_PIPELINE_LOG`. With the
flag off, `begin_turn()` returns `None` and `mark()` allocates nothing.
Every call site is exception-swallowed and every import is lazy, because
one of them sits inside db.py's turn commit and a probe must never be
able to take a turn down. Output goes to `api.log` (exactly one line per
turn) and to the operator-harness JSON response — never to the narrator
surface. CLAUDE.md:44 forbids diagnostic surfaces in the narrator flow,
and that applies to this as much as to a Return-to-Operator button.

### The reading, 2026-07-30

Two live harness turns, one synthetic narrator and one real one (Kent),
same text, `turn_mode="interview"`. Byte-identical results:

    raw_turn_saved=1  archive_event_created=2  extract_fields_called=0
    family_truth_written=0  projection_updated=0  fired=2/5

Read against a caller trace of the whole tree, the five numbers separate
into three different kinds of thing, which is the entire point of the
phase:

1. **The turn does write.** "Turn did not write anywhere" was false as
   worded. `turns` and the transcript JSONL move on every turn.

2. **`extract_fields_called=0` is a real gap.** `/api/extract-fields`
   has **no internal Python caller anywhere in the tree**. The only
   entries are the route itself and `ui/js/interview.js`. A turn driven
   through the internal WebSocket — which is what the operator harness
   does — therefore never extracts, and nothing downstream of
   extraction can fire either. **This is one defect, and it is the
   whole of Phase 2.**

3. **`family_truth_written=0` and `projection_updated=0` are correct by
   design, not gaps.** Family truth is a review-gated pipeline: every
   path into `ft_add_note` / `ft_add_row` is an explicit operator HTTP
   action (`POST /note`, `POST /note/{id}/propose`, and `POST /backfill`
   as the sole caller of `ft_backfill_from_profile_json`). A turn is not
   supposed to write it, and a turn that did would be the bug. The
   projection is reachable from chat_ws only inside the
   `turn_mode == "correction"` branch, so an interview turn reading 0 is
   the expected value.

A fourth candidate reading — *correct-by-design silence for a synthetic
or trainer narrator* — was **refuted**. No file under
`server/code/api/` mentions `trainer` at all; the real read-only
mechanism is `narrator_type='reference'`, enforced with 403 at the
family-truth routes. And empirically, a real narrator produced counts
identical to a throwaway synthetic id.

### How to read future evidence

- An **interview** turn reporting `2/5` is healthy-as-designed except
  for the extraction gap. It is not five failures.
- A **correction** turn reporting `projection_updated=0` **is** a
  defect. The interview-turn exemption does not transfer.
- Any turn reporting `family_truth_written>0` means something has wired
  a turn into the review-gated pipeline. Treat that as a finding, not a
  success.
- A stage reading 0 is only meaningful because it is *instrumented*.
  `CallSiteCoverageTest` and `TurnPathReachabilityTest` in
  `tests/test_truth_pipeline_probe.py` fail the build if a call site
  vanishes or if any of the three structural facts above stops holding.
  A reading kept only in prose goes stale silently; these tests are what
  force the correction into the record instead.

### Scope wall

Phase 1 was observability only: no schema change, no migration, no
behavior change.

**Corrected 2026-07-30.** The rest of this section read:

> *"Phase 2 (the extraction routing fix) and Phase 3 are **not started**
> and are Chris's to open. README's condition — 'Phase 2/3 routing fixes
> deferred until Phase 1 evidence lands' — is met, but a met condition is
> permission to ask, not permission to build."*

That was accurate for the few hours it stood. Chris opened Phase 2 the
same day and it is landed and live-verified; the section below is what
replaced it. Phase 3 remains not started.

---

## Completed-turn field extraction (Gate 7, Phase 2)

**Added 2026-07-30, TRUTH-PIPELINE-01 Phase 2.** Phase 1 proved exactly
one defect: a completed chat_ws interview turn never invoked the
extraction capability. This section is what closed it.

### The shape

    user turn completes
      → raw turn persists                    (db.py, persist_turn_transaction)
      → archive event persists               (archive.py, JSONL append)
      → the completed-turn response is sent to the browser
      → extraction is REQUESTED              (services/turn_extraction.py)
      → its outcome or its failure is recorded observably
      → the turn stays successful either way
      → no family truth is written
      → no correction projection is updated

The governing rule, in Chris's words: *connect completed turns to
extraction through one shared, idempotent, observable, failure-isolated
service; do not connect interview turns directly to truth.*

### One service, two callers

`server/code/api/services/turn_extraction.py` holds the extraction
capability. `POST /api/extract-fields` and the chat_ws completed-turn
hook both enter through it. The WebSocket server does **not** call its
own HTTP endpoint, and the extractor is not duplicated in `chat_ws.py`.
The route's external behaviour is unchanged — that is pinned by test,
not by inspection.

The `extract_fields_called` probe mark moved out of the HTTP route and
into the service at the same time, so the stage now means *the
extraction capability was invoked* rather than *somebody hit that
route*. Both callers pass through the one `_mark_probe`.

### Idempotency boundary

The key is `turnrow:<rowid>` — the AUTOINCREMENT id of the **committed
assistant turn row**, returned by `persist_turn_transaction` and carried
forward as `params["_persisted_turn_row_id"]`. Not the request's
`turn_id`, which the client supplies, and never the raw text, which
repeats legitimately.

It is enforced in the database, not in memory:
`turn_extraction_ledger` (migration `0038`) carries
`UNIQUE INDEX ux_turn_extraction_ledger_key ON (narrator_id, turn_key)`.
A claim is an insert. A replay loses the insert and returns `duplicate`
without doing any work. A process restart does not reopen the window,
which is the property an in-memory guard could not have given.

`duplicate` is deliberately **not** a stored outcome. The stored set is
`started` / `succeeded` / `noop` / `failed`; "duplicate" describes the
*caller's* result on a claim that someone else already holds, and
writing it would overwrite the real row's outcome.

### Failure isolation, and why the task is held

The order is: persist the critical turn data, complete the user-facing
response, then extract. Extraction cannot delay or fail the turn.

The first live run on 2026-07-30 failed here, and the failure is worth
recording because the obvious implementation is the wrong one. The
extraction was `await`ed on the turn's own task, after the `done` frame
was sent. The browser then disconnected — correctly, it had its answer —
the turn task was cancelled, and the extraction was cancelled with it:
both interview turns recorded `outcome='failed'`
`error_class='CancelledError'` at 815 ms and 839 ms.

The fix is `schedule_completed_turn_extraction()`, which does the
eligibility check, the ledger claim, and the probe mark **inline** on
the turn task, then hands the extractor call to a task created as a
*sibling* rather than awaited. A sibling task is not cancelled when its
parent is. Two details make that safe rather than fragile:

- `asyncio.create_task` holds only a **weak** reference, so a running
  task can be garbage-collected mid-flight. The tasks are held in a
  module-level strong-reference set and discarded by a done-callback.
- A process that exited without draining would strand ledger rows at
  `outcome='started'` forever. `main.py` therefore carries an
  `@app.on_event("shutdown")` handler — the first event handler that
  file has ever had — which awaits `drain_pending_extractions()`.
  Anything still running is given a bounded window and then cancelled
  *and recorded as cancelled*, so the ledger never lies about what
  happened.

The probe mark has to stay in the inline half for a mechanical reason:
`contextvars` are copied at `create_task` time, but the truth-pipeline
probe files its line in a `finally` after the turn body returns, so a
mark made from the completion task would land nowhere.

### Observability

Event vocabulary, all on the `[extract-turn]` prefix in `api.log`:
`extract_fields_requested`, `extract_fields_started`,
`extract_fields_succeeded`, `extract_fields_noop`,
`extract_fields_duplicate`, `extract_fields_failed`.

Each carries `turn_id`, `narrator_id`, `session_id`, `turn_mode`,
outcome, duration, and an error **classification**. The ledger stores
the same fields plus `item_count` and `method`.

`error_class` is a bare exception class name and nothing else. No
message, no traceback, no narrator text — a message can quote the
narrative that provoked it, and the acceptance test asserts the stored
value contains neither a space nor an `=` for exactly that reason. No
raw private narrative text is logged anywhere on this path.

### The two boundaries this phase did not move

- **Family truth stays review-gated.** An interview turn writes none.
  Every path into `ft_add_note` / `ft_add_row` remains an explicit
  operator HTTP action.
- **Correction projections stay mode-gated.** An interview turn performs
  no projection update; a correction turn still reaches
  `projection_writer.apply_correction` through the existing guarded
  path. Correction behaviour was not redesigned here.

Both are asserted structurally rather than by substring, so a docstring
or comment quoting a function name cannot pass or fail the check.

### Live evidence, 2026-07-30

Against the running stack on Chris's machine, narrator
`harness-test-gate7p2-002608f7`, via the operator harness. Evidence
JSON in `<DATA_DIR>/_xfer/gate7_phase2_evidence_phase{1,2,3}.json`.

| Test | Turn | raw_turn | archive | extract_called | family_truth | projection | Outcome |
|---|---|---|---|---|---|---|---|
| A | normal interview | 1 | 2 | **1** | 0 | 0 | ledger `succeeded`, browser `done` |
| B | replay of A | — | — | — | — | — | `duplicate (already_processed)`, no second ledger row |
| C | forced failure | 1 | 2 | **1** | 0 | 0 | ledger `failed`, `error_class=ForcedExtractionFailure`, browser `done` |
| D | correction control | 1 | 1 | 0 | 0 | **1** | projection version `None -> 1`, field source `correction` |
| E | flags off | — | — | — | — | — | `/api/operator/harness/*` → 404, disposable narrator fully removed |

The number that closed the gate is Test A's `extract_fields_called=1`.
The Phase 1 reading of the same stage, on the same path, was `0`.

Test C's value is that `1` and not `0`: a failed extraction must not be
indistinguishable from never having asked. Its `family_truth_written=0`
and `projection_updated=0` also hold — a failure does not open a
side door.

Test D is the control that proves the mode gate still works in the
direction it is supposed to fire, not merely in the direction it is
supposed to stay silent.

**A note on Test C's `story_candidates` delta of 1**, which is not
extraction. That row comes from `story_preservation.preserve_turn` on
the story-trigger path in `chat_ws.py`, and `api.log` shows it firing
99 ms after classification and roughly ten seconds before the forced
extraction failure was recorded. The Test C text carries three scene
anchors and trips `borderline_scene_anchor`; the Test A text carries
two and logs `trigger=None`. Field extraction only ever *updates*
`story_candidates.extracted_fields`; the single `INSERT` in the tree is
the preservation path.

### The forced-failure seam

Test C's failure comes from `HORNELORE_EXTRACTION_FORCE_FAILURE`, which
exists only for this test, is read at extraction time, is off by
default, and short-circuits before the extractor is built so no model
call is spent. No production configuration is touched to produce the
failure.

Because it is read in-process, an unrestarted server silently produces a
meaningless result — that happened on the first attempt and the run had
to be discarded. The harness health route therefore reports
`forced_failure_armed` as a **boolean only**, and the acceptance driver
refuses to run Phase 1 if the seam is armed and refuses to run Phase 2
if it is not.

---

## Maintenance

This document is updated whenever:
- A new stage is introduced (rare; should be deliberate, not incremental)
- A stage's contract changes (input/output interface, eligibility rules)
- A stage's primary file moves
- A new effective mode is added (extend interaction matrix)
- The original redesign turn-mode resolution changes (e.g., when
  Memory Echo gets its own WO)
- A truth-write stage gains, loses, or moves a `mark()` call site, or a
  stage changes which turn shapes can legitimately reach it (added
  2026-07-30 — the Gate 7 section's per-stage table and its
  "how to read future evidence" rules are only correct while that
  mapping holds, and `TurnPathReachabilityTest` will fail the build
  before this document is noticed)

Strategy doc and runtime architecture doc are read together by every
WO author before authoring a new WO that touches Lori behavior. WOs
declare which stage(s) they implement or modify in their first
section.

---

## Related artifacts

- `HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md` — companion ADR; answers
  the "who is Lori for" question this doc does not address
- `WO-INTERVIEW-PROCESS-REDESIGN-01` — historical predecessor;
  should be headered with archival note pointing to this doc and
  the strategy doc
- `WO-LORI-SAFETY-PAST-TENSE-ACKNOWLEDGE-01` — implements stage 1
- `WO-LORI-SOFTENED-MODE-PERSISTENCE-01` — implements stage 3
  softened-mode states
- `WO-LORI-PHASE-9-DISCLOSURE-UPDATE-01` — describes pipeline
  behavior to families and operators
- `WO-LORI-STORY-FIRST-PHASE-1-01` — implements stages 2, 4, 6, 7
- `WO-LORI-ORAL-HISTORY-DEFAULT-01` — implements stage 3 default
  and per-style parameter table
- `WO-LORI-BIO-BUILDER-UNIVERSAL-01` — implements stage 8
- README (Lane 2 section) — describes the existing Layer 1 + 2
  architecture this synthesis extends; should be updated post-merge
  to point at this doc as the canonical pipeline description

---

## Closing note

Three weeks ago, "improve Lori" mostly meant "tune the prompt."

After Phase 1 and the trio land, "improve Lori" mostly means "tune the
stages." Stages are testable, debuggable, and reproducible in ways
prompts aren't.

This is the architectural maturation the system needed in order to
serve narrators beyond people whose voices Chris already knows well.

The strategy doc establishes the why. This doc establishes the how.
The seven WOs build the parts. The pipeline is what they assemble into.
