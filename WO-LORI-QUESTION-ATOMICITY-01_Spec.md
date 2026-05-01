# WO-LORI-QUESTION-ATOMICITY-01 — One Thought, One Question

**Status:** SPEC (parent-session interview-quality gate)
**Owner:** Chris (scope) → Claude (build)
**Author:** 2026-04-30 evening
**Lane:** Lori-behavior, parallel to BUG-DBLOCK-01 (#344) safety-path lane
**Pre-reqs:** WO-LORI-SAFETY-INTEGRATION-01 Phase 1 LANDED; WO-LORI-SESSION-AWARENESS-01 Phase 2 LANDED; golfball-v2 harness operational

---

## 1. Why this exists

Lori is currently passing the shallow rule `question_count <= 1` but failing the
real interviewing rule **one cognitive target per turn**. The 2026-04-30 golfball
harness produced four turn responses with a single `?` that smuggled in two or
more memory targets through `and` / `or` / "tell me about X and what":

> *"What was Spokane like, and did your family travel back and forth between
> Spokane and Montreal?"* (Turn 02)
>
> *"Did your parents tell you why they chose to move from Montreal to Spokane,
> or was it a bit of a mystery to you as a child?"* (Turn 03)
>
> *"Can you tell me more about your experience as the spokesperson for
> Priceline, and what drew you to that role?"* (Turn 04)
>
> *"Would you be willing to talk more about what's been going on and what
> you're feeling?"* (Turn 05 — soft safety)

These are double-barreled questions per the standard survey-methodology
definition. For Hornelore — a life-story interview system for older
narrators with potential cognitive load fragility — compound questions
have measurable downstream costs: increased cognitive load, reduced
narrator agency, and degraded quality of remembered material.

This is **not** style preference. It is a measurable validity defect.

### 1.1 Research grounding

**Mburu et al. 2025 ("Methodological foundations for AI-driven survey question
generation," *Journal of Engineering Education*, doi:10.1002/jee.70012).**
Reports that AI-generated questions can be adaptive and contextually relevant,
but explicitly names "redundant phrasing, **double-barreled questions**, and
jargon" as clarity defects affecting question validity. Treats AI question
quality as a measurable pre-deployment validity issue requiring iterative
refinement before participant deployment. Anchors our framing: Lori's
question quality is a validity issue, not a polish issue.

**Wang et al. 2025 ("Beyond Prompt Engineering: Robust Behavior Control in
LLMs via Steering Target Atoms," ACL 2025 Long Papers).** Abstract:
*"prompt engineering is labor-intensive and sensitive to minor input
modifications, often leading to inconsistent or unpredictable model outputs.
In contrast, steering techniques provide interpretability, robustness, and
flexibility, enabling more reliable and precise control over model
behaviors."* Justifies the **two-layer defense** below: a system-prompt
rule alone is sensitive to model drift, prompt-composer reordering, and
fine-tune updates — a deterministic post-generation filter is the robust
analog to steering at our scale.

**Duplex Conversation (Lin et al. 2022).** Treats spoken-interview turn
management as a first-class concern beyond response content; supports the
posture that interview discipline is structural, not aesthetic.

**Semantic prompt framework (Hu et al. 2024).** Treats prompts as
composable primitives where each primitive performs an atomic task.
Lori's interview question is one such primitive — atomicity is the
property that makes it composable with the rest of the session loop.

---

## 2. Scope (locked)

**In scope:**

- One additive `LORI_QUESTION_ATOMICITY` directive block in
  `prompt_composer.py`, threaded into every interview-side composer
  (interview / memory_echo / correction follow-up; **NOT** safety-acute
  responses, which need different structure)
- New `enforce_question_atomicity(text: str) -> tuple[str, list[str]]`
  helper in a new `server/code/api/services/question_atomicity.py` module
  (standalone — same LAW 3 isolation pattern as story_preservation.py)
- Runtime guard wired into `chat_ws.py` post-stream, **after** safety
  scan and **before** `_ws_send` of the final assembled assistant_text
- Harness expansion: 6 new failure labels in
  `scripts/archive/run_golfball_interview_eval.py`
  (`and_pivot`, `or_speculation`, `request_plus_inquiry`,
  `choice_framing`, `hidden_second_target`, `dual_retrieval_axis`)
- 6 acceptance regex patterns plus a unit-test pack covering each
  illegal structure category, plus 5 truncation-grammar tests
  for §5.1's post-truncation gate

**Out of scope (explicitly):**

- Word-count limits, active-reflection requirements, menu-offer
  detection — those are the **other** legs of WO-LORI-ACTIVE-LISTENING-01
  and stay in their own lane. ATOMICITY-01 is specifically the
  one-cognitive-target rule, no more, no less
- Safety-path responses. The ACUTE SAFETY RULE in `prompt_composer.py`
  L108-193 has its own structure (warm acknowledgment + 988 + soft
  re-engagement). Atomicity guard MUST exempt category=acute and
  category=ideation safety responses. SAFETY-INTEGRATION-01's response
  templates are the source of truth there
- BUG-DBLOCK-01 fix or any DB-write changes
- Style-diff differentiation between session_styles
- Personality / warmth / conversational character — atomicity is
  structural; warmth is a separate axis and not constrained by this WO

---

## 3. The hard rule

**ONE THOUGHT, ONE QUESTION.**

Lori may ask exactly one question per interview turn. That question must
contain one subject, one predicate, and one memory target.

When the prompt-engineered output violates the rule, the deterministic
filter prefers **truncation over rewrite** — keep the first complete
question, drop everything after the second-question pivot point. We do
not introduce new content; we only remove.

---

## 4. Illegal structures (taxonomy)

Five categories. Each is a deterministic failure label and a regex
class.

### 4.1 `and_pivot` — second inquiry chained after the first

> ❌ *"What was it like in Spokane, **and how** did your dad's work
> affect you?"*
>
> ✅ *"What do you remember about Spokane?"*

Pattern signal: `?` preceded by content, OR the absence of `?` plus a
trailing `, and (what|how|why|where|when|did|do|are|were|is|was)` or
` and (what|how|why|where|when|did|do|are|were|is|was) +.+\?`.

**Refinement v1.1 (overfire guard).** The pattern fires only when **both
the pre-pivot and post-pivot clauses contain a verb** — i.e. two
distinct predicates separated by `, and` or `, or`. This rules out
single-predicate questions with internal `and` linking modifiers (e.g.
*"What's your relationship with reading and writing?"* — single
predicate, single retrieval axis, must NOT trip).

### 4.2 `or_speculation` — alternatives offered to the narrator

> ❌ *"Was it scary, **or** did it feel normal?"*
>
> ✅ *"How did it feel at the time?"*

Pattern signal: `, or (was|were|did|do|is|are|wasn't|weren't|didn't|don't|isn't|aren't) +.+\?`.

**Refinement v1.1 (overfire guard).** Same two-predicate rule. The
trailing-`or` clause must itself contain a verb. This rules out
*"Did your parents tell you why they chose to move from Montreal to
Spokane, or was it a bit of a mystery to you as a child?"* — both
clauses share the same yes/no operator (`Did your parents tell you...`)
and the `or` introduces a branch, not a second predicate. (Strictly: a
yes/no question with an `or it was X` branch is ONE retrieval — the
narrator can answer "no, it was a mystery" without picking a second
target.)

### 4.3 `request_plus_inquiry` — imperative followed by question

> ❌ *"Tell me more about Spokane **and what** happened next."*
>
> ✅ *"What do you remember about Spokane?"*

Pattern signal: `(tell|share|describe|walk me through|talk about) +.+ and (what|how|why|where|when)`.

### 4.4 `choice_framing` — multi-option emotional list

> ❌ *"Did you feel proud, **sad**, or confused?"*
>
> ✅ *"How did you feel then?"*

Pattern signal: triple-comma list before `?`, or `(\w+, \w+,( or)? \w+)\?`.

### 4.5 `hidden_second_target` — two distinct memory anchors in a single
question

> ❌ *"What do you remember about **Spokane and Montreal**?"*
>
> ✅ *"What do you remember about Spokane?"*

Pattern signal: harder — two proper-noun place tokens or two distinct
relation tokens (`mom and dad`, `school and church`) joined by `and`
inside a single question. Conservative: only fire when both tokens
match the existing place-anchor or person-anchor regex from
`story_trigger.py` so we don't over-fire on legitimate single-target
questions like *"What's your relationship with reading and writing?"*.

### 4.6 `dual_retrieval_axis` — one question, two retrieval systems

> ❌ *"What do you remember about Spokane **and how you felt**?"*
>
> ✅ *"What do you remember about Spokane?"*

This is a higher-level semantic catch beyond 4.5. Even when both
"targets" are technically about the same memory, asking the narrator
to retrieve **place + emotion**, **event + evaluation**, or
**person + emotion** in a single question splits cognitive load
across distinct retrieval systems. Episodic-place memory and
affective-evaluation memory are stored and surfaced differently;
asking for both simultaneously degrades both.

Pattern signal: question contains a place/event/person token AND
one of the affect tokens (`feel`, `felt`, `felt like`, `feeling`,
`emotion`, `mood`, `proud`, `scared`, `sad`, `happy`, `lonely`,
`difficult`, `meaningful`) joined by `and` or `, and`. Conservative
fire — only when the place/event/person token is the question's
primary subject (same regex hook as 4.5).

> ❌ *"What was your father's farm like **and how did it make you feel**?"* (place + emotion)
>
> ❌ *"What happened that day **and what did it mean for the family**?"* (event + evaluation)
>
> ❌ *"Tell me about your grandmother **and what she meant to you**."* (person + emotion)

Per the architecture in §5, Layer 2 truncates these at the `, and`
pivot. Resulting question keeps the narrator-friendly opening retrieval
target, drops the secondary axis.

---

## 5. Architecture — two-layer defense

Following STA (Wang et al. 2025): prompt engineering alone is sensitive
to drift. Two layers, both default-on once landed:

**Layer 1 — system-prompt directive** (composer-side, additive). Rides
on every interview-mode composer. Steers the model toward atomic
questions before generation. Catches ~80% of cases at zero runtime cost.
Subject to drift across model updates; insufficient by itself per the
STA finding.

**Layer 2 — runtime deterministic filter** (post-stream, pre-send).
Inspects the final assembled assistant_text. If atomicity violation
detected, truncates at the second-question pivot. Logs the
classification + truncation with `[chat_ws][atomicity]` log marker
so operators can see when Layer 1 missed and Layer 2 caught.

The filter never **rewrites** — only truncates. This rules out a class
of regressions where the filter introduces hallucinated content or
narrator-side text leakage. If truncation produces an empty or
<5-word output, the filter returns the original unchanged and emits
a `[chat_ws][atomicity][skip-too-short]` warning so we never silently
return a stub.

### 5.1 Truncation grammar guard (v1.1)

A naïve truncation can produce non-question artifacts. Example:

> Input: *"Tell me more about Spokane and what happened next."*
>
> Naïve truncation at `and`: *"Tell me more about Spokane"* — no `?`,
> not a question form anymore.

Layer 2 enforces this **post-truncation grammar gate**:

```
1. If truncated output ends with '?' → ACCEPT (truncation succeeded cleanly)
2. If truncated output is an imperative ("Tell me about X", "Share Y",
   "Walk me through Z") → ACCEPT (request-form is a valid alternative
   to question-form per §4.3 disposition)
3. If truncated output ends with neither '?' nor imperative-form,
   AND original contained a complete question (regex: a clause
   starting with what|how|why|where|when|did|do|are|were|is|was
   ending in '?') → fall back to that question clause, drop the
   imperative wrapper. This is the ONE allowed truncation form
   beyond pure character-range removal.
4. Otherwise → ABORT truncation, return original unchanged, emit
   [chat_ws][atomicity][skip-grammar] warning. We do NOT introduce
   new question stems or paraphrase. The "no rewrite" principle
   trumps the "must be atomic" principle when they conflict.
```

This guard is the difference between "deterministic filter" and
"clever filter." Step 4 is the load-bearing safety: when in doubt,
emit the original and let Layer 1's prompt directive carry the next
turn.

---

## 6. Implementation order

1. **Layer 1 — composer directive** (`prompt_composer.py`).
   New constant `_LORI_QUESTION_ATOMICITY` block, appended to the
   existing `LORI_INTERVIEW_DISCIPLINE` block built by
   SESSION-AWARENESS-01 Phase 2. Does NOT modify acute-safety
   templates. Default-on. ~30 lines, no flag.

2. **Layer 2 — atomicity service module**
   (`server/code/api/services/question_atomicity.py`).
   `enforce_question_atomicity(text: str) -> tuple[str, list[str]]`
   returns `(possibly_truncated_text, list_of_failure_labels)`.
   Module imports zero extraction-stack code; LAW-3 isolation test
   added to the existing `test_story_preservation_isolation.py`-style
   gate (or sibling). Pure-function, fully unit-testable.

3. **Layer 2 wire-up** (`chat_ws.py`).
   In `_generate_and_stream_inner` after the assembled-text completion
   and BEFORE the final `_ws_send({"type": "done", ...})`, call
   `enforce_question_atomicity(final_text)`. Skip when
   `_safety_result.triggered` is True (acute path keeps its own
   structure). Log classification at `WARNING` level on truncation.
   Gated behind `HORNELORE_ATOMICITY_FILTER=1` for the first eval
   cycle, default-on (=1) once we measure regressions to be zero on
   the master extractor eval.

4. **Harness expansion**
   (`scripts/archive/run_golfball_interview_eval.py`).
   Replace the existing single `compound_or_nested_question_detected`
   failure label with the five-category taxonomy. Each turn record
   gains `atomicity_failures: list[str]`. Cross-run pass criterion
   becomes `atomicity_failures == []` for normal interview turns.

5. **Unit-test pack**
   (`tests/test_question_atomicity.py`).
   ~25 cases covering each of the 5 illegal categories (positive
   detection), plus 10 negative cases (legitimate single-target
   questions that must NOT trip the regex), plus 5 truncation
   correctness cases (verify truncated text is still grammatical and
   ends in `?`).

6. **Live verify** — Chris reruns golfball harness. Expectation:
   Turns 02-05 produce single atomic questions. Story_candidate
   creation on Turn 02 unchanged. Turn 06 safety response unchanged
   (atomicity exempt for safety category). No new DB lock events.

---

## 7. Acceptance criteria

| # | Criterion | Verification |
|---|-----------|--------------|
| 1 | All 5 illegal-structure regexes correctly classify their positive examples (4.1-4.5) | `tests/test_question_atomicity.py` — 25/25 positive |
| 2 | Negative cases (legitimate single-target questions with internal "and"/"or" clauses) do NOT trip | 10/10 negative |
| 3 | Truncation produces grammatically-complete output ending in `?` for all 5 categories | 5/5 truncation cases |
| 4 | Atomicity filter SKIPPED when `_safety_result.triggered` (acute SAFETY response unchanged) | golfball harness Turn 06 |
| 5 | Golfball harness Turns 02-05 produce `atomicity_failures: []` | golfball harness self-check |
| 6 | Story_candidate creation on Turn 02 (canonical 3-anchor) still fires | golfball harness self-check |
| 7 | Master extractor eval pass count unchanged (atomicity is chat-side, never touches `extract_fields`) | r5h-place-guard rerun shows ≥75/110 |
| 8 | LAW-3 isolation: `question_atomicity.py` imports zero `routers/extract.py`, `prompt_composer.py`, `memory_echo.py`, `chat_ws.py`, or `routers/llm_*.py` symbols | static import-graph test |

---

## 8. Dispositions

- **ADOPT** if criteria 1-8 all green AND golfball-v2 atomicity_failures
  drop to 0 on Turns 02-05 across two consecutive runs.
- **ITERATE** if Layer 1 alone takes care of ≥90% of cases AND Layer 2
  truncation introduces grammatical artifacts in ≥1 case — drop Layer 2
  to gated-off, keep Layer 1 as primary, scope a Layer 2 v2 with
  per-category truncation grammar handling. STA finding still says we
  need Layer 2 eventually.
- **PARK** if the 5-category taxonomy proves too narrow on real narrator
  data (Janice / Kent / Christopher) — fall back to the simpler "single
  trailing `?` and no clause-joining `, and|, or` pattern" heuristic and
  open a follow-up WO with more empirical pattern data.
- **ESCALATE** if Layer 2 truncation begins regressing the master eval
  (criterion 7 fails) — that means atomicity is interacting with
  something extractor-relevant and the architecture needs review.

---

## 9. Files touched

```
server/code/api/prompt_composer.py                    (+~25 -0)
server/code/api/services/question_atomicity.py        (NEW, ~150 lines)
server/code/api/routers/chat_ws.py                    (+~20 -0)
scripts/archive/run_golfball_interview_eval.py        (+~30 -3)
tests/test_question_atomicity.py                      (NEW, ~200 lines)
tests/test_question_atomicity_isolation.py            (NEW, ~30 lines, LAW-3 gate)
.env.example                                          (+1)   HORNELORE_ATOMICITY_FILTER
WO-LORI-QUESTION-ATOMICITY-01_Spec.md                 (this)
```

No `extract.py` changes. No schema migration. No DB writes added or
removed.

---

## 10. Connections to existing lanes

- **WO-LORI-ACTIVE-LISTENING-01 (#314)** — partially supersedes the
  one-question-discipline component. ACTIVE-LISTENING-01's other
  pillars (active reflection, word-count caps, menu-offer detection,
  direct-answer-first patterns) remain in that WO's lane. After
  ATOMICITY-01 lands, ACTIVE-LISTENING-01's spec is amended to remove
  the atomicity bullet and link here.
- **WO-LORI-SESSION-AWARENESS-01 Phase 2 (#285)** — already shipped
  the `LORI_INTERVIEW_DISCIPLINE` composer block. ATOMICITY-01's Layer 1
  appends to that existing block rather than minting a new one.
- **WO-LORI-SAFETY-INTEGRATION-01 Phase 1+3 (#289, #291)** — Layer 2
  filter MUST exempt safety category turns. The
  `_safety_result.triggered` flag already in chat_ws.py is the gate.
- **BUG-DBLOCK-01 (#344)** — orthogonal lane, but co-blocking parent
  sessions. Atomicity fix lands chat-side; DBLOCK fix lands DB-side;
  both must be green before parent sessions.
- **WO-GOLFBALL-HARNESS-02** — the harness is the regression test;
  the new 5-label taxonomy replaces the single `compound_or_nested`
  flag and gives operators per-category attribution on every run.

---

## 11. Definition of done

```
Golf Ball harness no longer flags atomicity failures
on Turns 02-05 (normal interview turns).

Lori still creates story_candidate rows for scene-anchor turns
(Turn 02 lands a row, Turn 03 lowercase fallback also lands a row).

Safety turns (Turn 06) still produce ACUTE SAFETY response
with normal interview question suppressed.

No new DB lock events introduced.

Master extractor eval pass count unchanged (atomicity is
chat-side; extractor-side untouched).

Two-layer defense both default-on after one clean rerun.
```

---

## 12. Estimate

- §6.1 Layer 1 composer directive: 1 hour
- §6.2 question_atomicity.py module + 25 unit tests: 4-5 hours (regex
  iteration, false-positive sweep, truncation grammar)
- §6.3 chat_ws.py wire-up + safety exempt + log marker: 1.5 hours
- §6.4 harness expansion + 5-category labeling: 1.5 hours
- §6.5 LAW-3 isolation test: 0.5 hour
- §6.6 live verify (Chris's stack): asynchronous

Total build: ~9 hours. Lands as 4 commits, code-isolated from docs.

---

## 13. Anti-goals (worth saying explicitly)

- Do NOT make the filter clever. It truncates; it does not paraphrase
  or rewrite. Cleverness here is a regression vector.
- Do NOT pull in any LLM call inside the filter. The whole point of
  Layer 2 per STA is determinism.
- Do NOT exempt session_style. Whatever style is active —
  questionnaire_first, clear_direct, warm_storytelling, companion —
  every interview turn obeys atomicity. Style varies tone; structure
  is fixed.
- Do NOT log narrator content in the `[chat_ws][atomicity]` warning.
  Log the failure label only, plus character offsets if needed for
  debugging. Privacy-safe by construction.

---

## 14. Revision history

- **v1.0 (2026-04-30 evening, initial):** 5-category taxonomy
  (`and_pivot` / `or_speculation` / `request_plus_inquiry` /
  `choice_framing` / `hidden_second_target`); two-layer defense; LAW-3
  isolation gate.
- **v1.1 (2026-04-30 evening, post-review):**
  - Added §4.6 `dual_retrieval_axis` — catches single questions that
    span two retrieval systems (place + emotion, event + evaluation,
    person + emotion). Examples: *"What do you remember about Spokane
    and how you felt?"* — even when grammatically a single question,
    the dual retrieval splits cognitive load.
  - Added §5.1 truncation grammar guard — post-truncation must end in
    `?` OR be valid imperative form OR fall back to original. Closes
    the *"Tell me more about Spokane and what happened next"* edge
    case where naïve truncation produced *"Tell me more about
    Spokane"* (no `?`, not a question form). The "no rewrite"
    principle trumps the "must be atomic" principle when they
    conflict.
  - Tightened §4.1 / §4.2 patterns: `and_pivot` / `or_speculation`
    now require **two distinct predicates** (verb in both pre-pivot
    and post-pivot clauses). Closes false positives on *"Did your
    parents tell you why they chose to move..., or was it a mystery
    to you as a child?"* (single yes/no with branch — one retrieval,
    not two).
  - Failure-label list extended from 5 to 6.
  - Implementation order, acceptance criteria, and files-touched
    block updated to match.
