# WO-LORI-STORY-FIRST-PHASE-1-01

**Status:** SPEC — not yet started
**Severity:** HIGH (prerequisite for oral-history default flip; substrate for Phase 2+ redesign)
**Narrator generality:** UNIVERSAL — first WO authored under the framing established
in `HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md`. No Horne-specific assumptions.
**Locked principle:** *Lori behaves like a skilled life-story listener who occasionally
asks questions. Not a smart interviewer.*

## Why this WO exists

Parent of this WO: `WO-INTERVIEW-PROCESS-REDESIGN-01` Phase 1, decomposed into
four interrelated capabilities that ship together because they reference each
other and cannot be tested independently without artificial stubs:

1. **Reflection-first hardening** — every normal Lori turn begins with concrete
   reflection of narrator material before any continuation
2. **Story interruption rules** — when narrator is in story momentum, Lori does
   not interrupt for verification, clarification, schema fields, or chronology
3. **Thread banking** — Lori silently tracks unresolved story doors and surfaces
   them naturally later, instead of asking everything immediately
4. **Question hierarchy** — four-layer ladder (open recall → narrative probe →
   timeline clarification → verification) with hard rule that Layer 3-4 cannot
   fire unless Layer 1-2 has succeeded

The current system trends toward "ask question → receive answer → extract facts →
ask next question." This WO is the substrate that makes the oral-history default
(sibling WO, sequenced after this) actually feel like oral history at the
composition layer, not just at the word-cap layer.

Phase 1 is shippable in current architecture. Phase 2+ (turn classifier,
orchestrator, story momentum model, rhythm adaptation, quality harness) is the
larger architectural commitment that follows.

## Live evidence

Three failure modes Phase 1 addresses, drawn from the redesign document and
projected against universal narrators:

**Failure mode A — premature interruption / extraction redirect.**

Narrator opens with rich scene material:
> "I had a mastoidectomy when I was little, in Spokane. My dad worked nights
> at the aluminum plant."

Current architecture risk: Lori composes a Layer-2 narrative probe immediately —
"What do you remember about your father's work at the aluminum plant?" — which
narrows prematurely, skips reflection, and treats the opening as extractable
data rather than as a chapter offering.

Correct behavior: Lori reflects concretely first, then opens broad:
> "A mastoidectomy when you were little in Spokane — and your dad working
> nights at the aluminum plant. That already paints a picture. What stands
> out most when you think back on that time?"

**Failure mode B — chronology forcing.**

Narrator jumps eras:
> "When I was stationed in Germany..."

Current architecture risk: Lori redirects back to childhood material from
earlier in the session, or asks "what year was that?" to anchor chronology
before the chapter has been told.

Correct behavior: Lori follows narrator-led recall:
> "Germany sounds important. About how old were you around then?"

Chronology becomes support, not control. Chronology questions are Layer 3 and
do not fire before Layer 1-2 succeeds.

**Failure mode C — thread loss.**

Narrator names many anchors in one turn:
> "...my grandmother, the train ride, then Germany, the church choir..."

Current architecture risk: Lori picks one to ask about immediately, the others
are dropped, and the narrator finishes the session without grandmother,
train ride, or choir being revisited.

Correct behavior: Lori asks one gentle continuation now and silently banks the
other three. Later in the session, when a natural pause occurs:
> "Earlier you mentioned your grandmother — I keep thinking about her. What
> was she like?"

The unsurfaced thread is preserved as story material and returned to with
narrative weight rather than chronological order.

## Root cause

Three structural gaps in the current composition pipeline:

1. **No reflection-validator.** `lori_communication_control.py` enforces word
   caps, atomicity, and reflection presence — but the reflection check is
   shallow (does the response contain *any* acknowledging phrase) rather than
   structural (does the reflection ground in concrete narrator material from
   the most recent turn).

2. **No story-momentum awareness in composition.** The composer treats every
   narrator turn equivalently. A 200-word multi-scene chapter offering and a
   2-word factual answer get composed against the same prompt. The story-mode
   suppression of Layer 3-4 questions does not exist as a code-level rule.

3. **No persistent thread bank.** Unresolved doors mentioned by the narrator
   are visible to the LLM in conversation history but are not first-class
   data. There is no mechanism to surface a thread from 12 turns ago with
   appropriate narrative framing. The model may revisit threads if it
   happens to attend to them; nothing makes revisit reliable.

## Fix architecture

Four pieces, all in one WO because they reference each other:

### 1. Reflection validator — concrete grounding requirement

Existing `LoriResponseValidator` in `lori_communication_control.py` extended
with a new check: `_check_reflection_grounding()`.

Inputs:
- Lori's composed response
- The narrator's most recent turn (full text)

Algorithm:
- Extract content tokens from narrator turn (named entities, place names,
  numbers, distinctive nouns, verbs of action — anything that is not a
  common-stop-word)
- Require Lori's first 1-2 sentences to contain at least one content token
  from the narrator turn OR a clearly paraphrased reference to one
- Paraphrase detection uses semantic similarity (embedding-based, with a
  threshold tuned during build) for non-exact matches

If grounding check fails:
- Same regeneration loop as existing atomicity/word-cap failures: regenerate
  up to 2 times, log the failure, fall back to deterministic reflection
  template if all regenerations fail

Deterministic reflection fallback template:
```
"{narrator_anchor_phrase}. {pause_token} {continuation}"
```
where `narrator_anchor_phrase` is the most distinctive 4-8 word phrase from
the narrator turn (selected by content density), `pause_token` is a soft
acknowledgment from a small bank ("That stays with me." / "Mm." /
"That's vivid."), and `continuation` is the original LLM-composed continuation
if one exists, or omitted entirely if the validator's word-cap budget is
exhausted.

**Generic empathy phrases are explicitly forbidden in the reflection layer.**
Bank of forbidden openers (regenerate on detection):
- "That sounds difficult."
- "I can imagine."
- "That must have been..."
- "Thank you for sharing."
- Any sentence with no concrete narrator content token

### 2. Story momentum detection — composition-time signal

New service: `server/code/services/story_momentum.py`.

Cheap signals computed deterministically on every narrator turn (no LLM call):
- `word_count` — narrator turn length
- `named_entity_count` — capitalized non-stop-word tokens
- `temporal_marker_count` — "when", "then", "after", "before", "during",
  years, ages, dates
- `sensory_token_count` — vocabulary list of sensory verbs/adjectives
  (saw, smelled, cold, dark, loud, etc.) — small curated list, ~150 tokens
- `sequence_marker_count` — "first", "next", "then", "later", "finally",
  numeric ordinals
- `dialogue_present` — quoted speech or "she said" / "he told me" patterns
- `uninterrupted_run` — number of consecutive narrator turns >= 50 words
  in the current session

Composite momentum score (0.0 to 1.0):
```
momentum = weighted_sum([
    normalize(word_count, 0, 300) * 0.25,
    normalize(named_entity_count, 0, 5) * 0.15,
    normalize(temporal_marker_count, 0, 3) * 0.10,
    normalize(sensory_token_count, 0, 4) * 0.15,
    normalize(sequence_marker_count, 0, 3) * 0.10,
    (0.10 if dialogue_present else 0),
    normalize(uninterrupted_run, 0, 4) * 0.15,
])
```

Thresholds (env-tunable):
- `momentum >= 0.6` → **story mode active**, suppress Layer 3-4 questions
- `momentum >= 0.4` → **story mode emerging**, prefer Layer 1-2 continuations
- `momentum < 0.4` → **normal mode**, full question hierarchy available

The signal is composition-time only — it informs which prompt block is
assembled and which post-composition validators fire. It is not surfaced to
the narrator and not visible to the operator (deferred — out of scope).

The model is intentionally cheap and deterministic. Phase 2+ may replace
this with an LLM-derived momentum signal; Phase 1 ships with the
rule-based version because it is verifiable, fast, and good enough for
the story-vs-not-story distinction the question hierarchy needs.

### 3. Thread bank — persistent unresolved doors

New service: `server/code/services/thread_bank.py`.
New table: `interview_threads`.

Schema:
```
interview_threads
  id                  uuid pk
  session_id          uuid fk
  tenant_id           uuid                -- per universal pivot strategy
  thread_anchor       text                -- the named entity / topic
  source_turn_index   int                 -- which narrator turn introduced it
  source_excerpt      text                -- 1-2 sentence quote from source turn
  introduced_at       timestamp
  status              enum                -- 'open' | 'surfaced' | 'resolved' | 'declined'
  surfaced_at         timestamp nullable
  resolved_at         timestamp nullable
  category            enum                -- 'person' | 'place' | 'event' | 'object' | 'time_period'
```

Thread extraction runs on every narrator turn (deterministic, no LLM):
- Named-entity recognition (spaCy or equivalent — already available)
- Filter against existing open threads (deduplicate)
- Filter against thread categories the narrator has already resolved
- Write new threads as `open`

Surfacing logic — when Lori composes a turn:
- If narrator turn is in story mode (momentum >= 0.6): do not surface a
  banked thread; let the chapter continue
- If narrator turn is short or ends a chapter (momentum < 0.4, OR contains
  closing markers like "anyway", "that's about it", "I don't know what
  else", "where was I"): surface eligibility check
- Surface eligibility:
  - Thread is `open`
  - Thread is older than current narrator turn by at least 3 turns
    (banked threads need to have aged; immediate surfacing defeats the point)
  - Thread has not been declined by narrator previously (declined surfacing
    sets thread to `declined`, never re-surface)
  - Operator has not muted the thread (operator override surface, out of
    scope for Phase 1 — defer)
- If multiple threads eligible, surface the oldest open thread
- Composition of the surfacing turn uses a template:
  ```
  "Earlier you mentioned {thread_anchor}. {connecting_phrase} {open_question}"
  ```
  Example: `"Earlier you mentioned your grandmother. I keep thinking about her. What was she like?"`
- Surfacing updates thread status to `surfaced` and writes `surfaced_at`
- Narrator response to a surfaced thread is monitored on the next turn —
  substantive response (>30 words) updates to `resolved`; declination
  ("not much to say" / "let's skip" / etc.) updates to `declined`

Persistent across stack restart (DB-backed). Survives session pauses.

### 4. Question hierarchy — four-layer ladder with composition-time gating

Existing prompt blocks reference question discipline implicitly. This piece
makes the hierarchy explicit and code-enforced.

New constants in `prompt_composer.py`:
```
QUESTION_LAYER_OPEN_RECALL    = 1  # "Tell me about...", "What do you remember?"
QUESTION_LAYER_NARRATIVE      = 2  # "Who was there?", "What was the setting?"
QUESTION_LAYER_TIMELINE       = 3  # "About how old were you?", "Was this before X?"
QUESTION_LAYER_VERIFICATION   = 4  # "Was that Spokane?", "Did you mean...?"
```

Layer eligibility is computed per-composition based on session state:
- Layer 1 always eligible
- Layer 2 eligible if session has at least one narrator turn of substantive
  narrative content (>= 30 words OR contains a named entity)
- Layer 3 eligible if Layer 2 has been satisfied AND momentum < 0.6
- Layer 4 eligible if Layer 2 has been satisfied AND specific ambiguity exists
  that affects current composition (not preemptive verification)

**Hard rule (code-enforced):** No Layer 3 or 4 unless Layer 1 or 2 has
already succeeded in the current session.

Implementation: `QuestionHierarchyValidator` in `lori_communication_control.py`
checks Lori's composed response against:
- Does the response contain a question? (regex + semantic check)
- If yes, classify the question into a layer (LLM call with classification
  prompt, cached per question pattern)
- Is the classified layer currently eligible?
- If no, regenerate

Classification prompt (initial draft):
```
Classify the following question into one of four layers:

LAYER 1 (Open Recall): broad invitation to talk about a period or topic.
Examples: "Tell me about your childhood." "What stands out from that time?"
"What do you remember?"

LAYER 2 (Narrative Probe): expands an active story. References people,
places, settings, or events the narrator has already mentioned.
Examples: "Who else was there?" "What was the place like?" "What happened next?"

LAYER 3 (Timeline Clarification): anchors chronology. Asks about age, sequence,
or temporal relationship.
Examples: "About how old were you?" "Was this before the war?" "What year was that?"

LAYER 4 (Verification): confirms a specific factual detail to resolve ambiguity.
Examples: "Was that Spokane, Washington?" "Did you mean your sister?"

Return only the layer number (1, 2, 3, or 4).
```

Classification is cached by question fingerprint (normalized text hash) to
avoid re-classifying common question patterns on every turn.

### Integration with existing layers

| Existing layer | Phase 1 interaction |
|---|---|
| Atomicity check | Unchanged. Runs after Phase 1 validators. |
| Word cap | Unchanged. Story mode does NOT raise the cap; the cap is about turn density, story mode is about turn shape. |
| Question count cap | Now informed by question hierarchy validator. Layer 1-2 questions count normally; Layer 3-4 questions in story mode count as violations and trigger regeneration. |
| Reflection presence (existing shallow check) | Replaced by reflection grounding validator. Existing shallow check is removed. |
| Softened mode (sibling WO) | Phase 1 validators run in softened mode but vacuously — softened mode permits no questions, so question hierarchy never gates anything, and reflection grounding still applies. |
| Past-tense acknowledgment (sibling WO) | Phase 1 validators skipped for the acknowledgment bank turn (bank phrases are pre-validated). Resumes for subsequent softened turns. |
| Mortality reflection classification (sibling WO) | No interaction — mortality reflection just means "do not escalate"; Lori's next turn is normal composition with Phase 1 validators active. |

## Acceptance gates

1. **Reflection grounding — concrete narrator content in every normal turn.**
   - Narrator turn contains content tokens X, Y, Z
   - Lori's response opens with reflection containing at least one of X, Y, Z
     OR a paraphrased reference (semantic similarity above threshold)
   - Forbidden generic empathy phrases never appear

2. **Story mode suppresses Layer 3-4 questions.**
   - Narrator turn with momentum >= 0.6 → Lori's response contains zero
     Layer 3 or Layer 4 questions
   - If LLM generates a Layer 3-4 question, regeneration fires; if 2
     regenerations fail, deterministic continuation template is used

3. **Question hierarchy hard rule enforced.**
   - Session opens, narrator gives short response, momentum low
   - Lori's first question is Layer 1 (open recall) — Layer 2-4 not yet eligible
   - After narrator gives substantive narrative response, Layer 2 becomes eligible
   - Layer 3 not eligible until momentum drops below 0.6 AND Layer 2 has succeeded
   - Verification (Layer 4) only fires when actual ambiguity exists in
     current composition, never preemptively

4. **Thread bank captures and surfaces.**
   - Narrator turn mentions 4 distinct anchors → 4 thread rows written as `open`
   - Subsequent narrator turn at low momentum (chapter end) → oldest eligible
     thread surfaces in next Lori turn with the template format
   - Narrator substantive response → thread updates to `resolved`
   - Narrator declination → thread updates to `declined`, never re-surfaces

5. **Thread bank does NOT interrupt story mode.**
   - Narrator in story momentum (>= 0.6) → no banked thread surfaces this turn
   - Lori's response is normal continuation in story mode

6. **Persistence across stack restart.**
   - Thread bank state survives DB round-trip
   - Session resumed after stack restart sees open threads from prior session
     state

7. **Universal narrator applicability.**
   - All tests run against synthetic narrator turns AND existing Horne session
     evidence
   - No Horne-specific named entities, vocabulary, or composition examples
     appear in production code paths (only in test fixtures)

8. **Composition latency budget.**
   - All Phase 1 deterministic computations (momentum, thread extraction,
     reflection grounding) complete in <50ms per turn
   - Question layer classification (LLM) cached after first occurrence;
     cache hit rate >= 80% within first 20 turns of a session
   - Total Phase 1 overhead per turn budget: <300ms (including one LLM
     classification call on cache miss)

9. **Failure-mode evidence reproduced.**
   - Test case A (mastoidectomy / Spokane / aluminum plant opener) →
     Lori response passes reflection grounding, contains Layer 1 question,
     contains zero Layer 2-4 questions
   - Test case B (Germany era jump) → Lori response follows narrator's era,
     does not redirect to earlier material, may use Layer 3 if momentum
     low enough
   - Test case C (four-anchor turn: grandmother / train / Germany / choir) →
     all four threads banked, surfacing happens later in session, surfacing
     uses template

## Test coverage

`tests/test_reflection_grounding.py` (new):

- `ReflectionGroundingTokenMatchTest` — 8 tests: exact content token
  matching, paraphrase similarity, forbidden generic phrases, fallback
  template

`tests/test_story_momentum.py` (new):

- `StoryMomentumScoringTest` — 10 tests: individual signal calculations,
  composite score, threshold boundary behavior, env-tunable overrides

`tests/test_thread_bank.py` (new):

- `ThreadBankExtractionTest` — 6 tests: NER extraction, deduplication,
  category classification
- `ThreadBankSurfacingTest` — 8 tests: eligibility rules, age requirement,
  story-mode suppression, surfacing template, status transitions
- `ThreadBankPersistenceTest` — 4 tests: DB round-trip, session resumption,
  tenant isolation

`tests/test_question_hierarchy.py` (new):

- `QuestionLayerClassificationTest` — 12 tests: each layer with 3
  representative questions, edge cases for ambiguous questions
- `QuestionHierarchyEligibilityTest` — 8 tests: layer gating rules,
  hard-rule enforcement, regeneration on violation

`tests/test_phase_1_integration.py` (new):

- 6 end-to-end tests reproducing failure modes A, B, C with full chat_ws
  flow; verifying composition output matches desired behavior; verifying
  no Horne-specific assumptions in production paths

`tests/test_lori_communication_control.py` (extend existing):

- 4 tests: integration of Phase 1 validators with existing atomicity /
  word cap / question count layers; regeneration loop budget; vacuous
  pass in softened mode

Target: 66 new tests across 6 files, all green before merge.

## Live verification

1. Cycle stack with `HORNELORE_STORY_FIRST_PHASE_1=1` enabled
2. Run failure mode A through chat path with synthetic narrator turn:
   "I had a mastoidectomy when I was little, in Spokane. My dad worked
   nights at the aluminum plant."
   - Confirm Lori response contains "mastoidectomy" or "Spokane" or
     "aluminum plant" in opening sentence
   - Confirm Lori response contains one Layer 1 question, zero Layer 2-4
   - Log line `[composer][story_first] reflection_grounded=true layer=1`
3. Run failure mode B with era jump:
   "When I was stationed in Germany..."
   - Confirm Lori response references Germany
   - Confirm Lori response does NOT redirect to material from earlier in
     session
   - Log line `[composer][story_first] era_followed=true`
4. Run failure mode C with four-anchor turn
   - Confirm 4 `interview_threads` rows written as `open`
   - Advance session with several short turns
   - Confirm one banked thread surfaces in subsequent Lori turn
   - Confirm surfacing template format used
   - Log line `[thread_bank] surfaced thread_id=X anchor=grandmother`
5. Restart stack mid-session
   - Confirm open threads persist
   - Confirm surfacing logic continues from prior state
6. Counter-test: ensure Phase 1 changes do NOT break existing acute path,
   past-tense acknowledgment, softened mode, or extraction pipeline

## Files changed

- `server/code/services/story_momentum.py` (new, ~180 lines: signal
  computation, composite scoring, env-tunable thresholds)
- `server/code/services/thread_bank.py` (new, ~250 lines: extraction,
  surfacing logic, status transitions, persistence)
- `server/code/services/reflection_grounding.py` (new, ~120 lines:
  content token extraction, semantic similarity check, fallback template,
  forbidden phrase bank)
- `server/code/services/question_hierarchy.py` (new, ~140 lines: layer
  classification with caching, eligibility computation, hard-rule
  enforcement)
- `server/code/services/lori_communication_control.py` (+~80 lines:
  integration of four new validators into existing regeneration loop;
  removal of existing shallow reflection check)
- `server/code/services/prompt_composer.py` (+~60 lines: story-mode
  prompt block variant, question hierarchy guidance in prompt, thread
  bank surfacing template)
- `server/code/api/chat_ws.py` (+~50 lines: momentum computation at
  turn-start, thread extraction post-narrator-turn, thread surfacing
  invocation, Phase 1 validator dispatch)
- `server/data/migrations/` (new: `interview_threads` table, tenant_id
  column following universal pivot strategy)
- 6 new test files (counts above)
- `.env.example` (+~25 lines: momentum thresholds, thread bank parameters,
  Phase 1 feature flag)

## Related lanes

- **WO-INTERVIEW-PROCESS-REDESIGN-01** — parent vision document; this WO
  implements Phase 1 of its rollout order
- **HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md** — strategy doc establishing
  universal narrator framing; this WO is the first authored entirely
  under that framing
- **WO-LORI-SAFETY-PAST-TENSE-ACKNOWLEDGE-01** — sibling safety WO; Phase 1
  validators interact at composition layer (deferred to bank turn)
- **WO-LORI-SOFTENED-MODE-PERSISTENCE-01** — sibling safety WO; Phase 1
  validators run vacuously in softened mode
- **WO-LORI-ORAL-HISTORY-DEFAULT-01** (sequenced after this WO) — the
  default-style flip that Phase 1 makes meaningful. Without Phase 1, the
  oral-history default would still permit questionnaire-cadence composition
  within the longer word cap
- **WO-LORI-COMMUNICATION-CONTROL-01** — predecessor lane; Phase 1 extends
  the validator architecture established here
- **Bio Builder lane (future)** — Phase 1's thread bank and reflection
  grounding are substrate. Anchored-asking depends on thread bank;
  known-fact guard depends on reflection grounding's content token model

## Out of scope (deferred)

- **Operator visibility into thread bank.** Operator dashboard surface for
  reviewing, muting, or manually surfacing banked threads. Deferred to a
  separate operator-UX WO. Default behavior in Phase 1 is purely
  automatic.
- **Narrator-facing visibility into thread bank.** Explicitly rejected —
  calling attention to "Lori is keeping a list" would change the nature of
  the conversation.
- **LLM-derived story momentum signal.** Phase 2+ work. Phase 1 ships the
  rule-based version because it is verifiable and fast.
- **Question layer classification beyond English.** Spanish-fragment work
  is on its own lane; question hierarchy in Spanish defers to that lane
  reaching parity.
- **Rhythm adaptation per narrator.** Phase 2+ work (Part 10 of redesign
  document). Phase 1 ships with one set of momentum thresholds for all
  narrators; per-narrator tuning comes later.
- **Turn classifier (full 10-category).** Phase 2 work (Part 8 of redesign
  document). Phase 1 ships with momentum as the single composition-time
  signal; full classifier comes later and consumes momentum as one input.
- **Interview orchestrator.** Phase 2 work (Part 7 of redesign document).
  Phase 1 ships with composition-time dispatch in `chat_ws.py`; the
  dedicated orchestrator service comes later and absorbs that dispatch.
- **Interview quality harness.** Phase 3 work (Part 11 of redesign
  document). Phase 1 ships with unit and integration tests; the
  population diversity harness and quality metrics come later.
- **Population diversity testing (12 archetypes).** Phase 5 work. Phase 1
  ships with synthetic narrator test fixtures broader than Horne family
  but not yet the full archetype set.
