# WO-LORI-REFLECTION-01 — Memory Echo Before Question

**Status:** SPEC (parent-session interview-quality gate, post-atomicity)
**Owner:** Chris (scope) → Claude (build)
**Author:** 2026-04-30 evening
**Lane:** Lori-behavior, sequenced after WO-LORI-QUESTION-ATOMICITY-01
**Pre-reqs:** WO-LORI-QUESTION-ATOMICITY-01 LANDED and green;
              WO-LORI-SAFETY-INTEGRATION-01 Phase 1 LANDED;
              WO-LORI-SESSION-AWARENESS-01 Phase 2 LANDED
**Parallel blockers:** BUG-DBLOCK-01 (#344) remains its own lane

---

## 1. Why this exists

After atomicity is fixed, Lori may ask only one question per turn —
but she can still feel abrupt, generic, or extractive. The next quality
rule is:

> **Echo first. Ask second.**

A good interviewer briefly reflects what the narrator just said before
moving forward. This helps the narrator feel heard, reduces pressure,
and keeps the session grounded in the narrator's actual words.

**Bad Lori behavior** (atomic, but cold):

> *"What do you remember about Spokane?"*

**Better Lori behavior** (atomic AND grounded):

> *"You remember Spokane and your father working nights at the aluminum
> plant. What do you remember about Spokane?"*

The echo must be **short, factual, and grounded only in the narrator's
last turn**. Atomicity makes Lori clear; reflection makes her present.

### 1.1 Research grounding

**Mburu et al. 2025.** Iterative refinement of AI-generated questions
is essential to question-validity quality before participant
deployment. Reflection is one observable axis of that refinement.

**Duplex Conversation (Lin et al. 2022).** Treats turn management and
listening behavior as structural parts of dialogue, not decorative
style. Backchanneling and acknowledgment are first-class concerns,
not polish.

**Semantic prompt framework (Hu et al. 2024).** Each Lori turn is a
composition of primitives. The atomicity primitive (one question)
plus the reflection primitive (one grounded echo) compose into a
single coherent interview turn.

So the structural unit becomes:

> **`[brief grounded echo]` + `[one atomic question]`**

---

## 2. Hard rule

Every normal interview turn should follow:

1. **One brief memory echo.** Short sentence reflecting the narrator's
   last message.
2. **One atomic question.** Per WO-LORI-QUESTION-ATOMICITY-01.

The echo MUST be:

- **≤ 25 words**
- **Grounded** in narrator's last message — only facts the narrator
  actually said
- **Not interpretive** — no inferred motives, hidden meanings, or
  diagnoses
- **Not emotionally overreaching** — no "must have been traumatic",
  no "that sounds difficult"
- **Not invented** — no facts the narrator didn't provide
- **Not agenda-revealing** — no "story candidate", "archive", "field",
  "extract", "for our records"

---

## 3. Scope (locked)

**In scope:**

- One additive `LORI_MEMORY_ECHO` directive block in
  `prompt_composer.py` (composer-side, default-on, additive to the
  existing `LORI_INTERVIEW_DISCIPLINE` block)
- New `validate_memory_echo(assistant_text, user_text) -> tuple[bool, list[str]]`
  helper in a new `server/code/api/services/lori_reflection.py` module
  (standalone — same LAW-3 isolation pattern as story_preservation.py
  and question_atomicity.py)
- Validator-only wire-up in `chat_ws.py` post-stream — **no rewrite**
- Harness expansion: 6 new failure labels in
  `scripts/archive/run_golfball_interview_eval.py`
- Unit-test pack covering each illegal echo type plus a positive pack
  of grounded-echo examples

**Out of scope (explicitly):**

- Echo *generation* / *rewriting*. This WO is validator-only.
  Generation drift is the same hallucination risk we ruled out for
  atomicity, and reflection content is **more semantic** than
  atomicity — a deterministic rewriter could invent narrator facts.
  See §6 for the rationale.
- Word-count caps on the question itself (separate axis of
  WO-LORI-ACTIVE-LISTENING-01)
- Style-diff differentiation
- Safety-acute responses. The ACUTE SAFETY RULE in `prompt_composer.py`
  L108-193 has its own structure (warm acknowledgment that already
  includes echo-like reflection by design + 988 + soft re-engagement).
  Reflection guard MUST exempt category=acute responses
- Companion-mode softer echo styling. May be addressed in a follow-up
  WO if the harness shows companion mode regressing
- Atomicity rules. Atomicity is enforced by ATOMICITY-01; this WO
  layers on top

---

## 4. Allowed echo types

Each is a deterministic positive pattern.

### 4.1 Factual echo

> *"You remember Spokane and your father working nights."*

Restates 1-3 narrator-provided facts. Highest-fidelity, lowest-risk
form.

### 4.2 Place echo

> *"Spokane is coming through clearly in that memory."*

Names a single concrete place the narrator anchored on. No emotional
inference.

### 4.3 Relationship echo

> *"Your father's night work seems connected to that time."*

Surfaces a relationship the narrator mentioned. Uses hedging language
("seems", "comes through") to avoid false certainty.

### 4.4 Story-anchor echo

> *"That memory has a place, a person, and a time."*

Acknowledges the structural completeness of the narrator's story.
Useful for borderline_scene_anchor turns where narrator gave place +
person + time.

---

## 5. Illegal echo types (taxonomy)

Six categories. Each maps to a deterministic failure label.

### 5.1 `missing_memory_echo` — no reflection at all

> ❌ *"What do you remember about Spokane?"* (atomic but cold)

Pattern signal: assistant text starts with the question primitive
(`What|How|Why|Where|When|Did|Do|Are|Were|Is|Was|Tell|Share|Walk`)
without any prior content.

### 5.2 `echo_too_long` — reflection runs over budget

> ❌ *"You've shared a deeply meaningful and emotionally layered
> memory about Spokane, your medical experience, and your father's
> difficult work schedule that paints a vivid picture of your
> childhood..."*

Pattern signal: word count of pre-question content > 25.

### 5.3 `echo_not_grounded` — facts not in narrator's last message

> Narrator: *"My father drove a John Deere tractor at the Mandan farm
> in 1958."*
>
> ❌ Lori: *"Your father was clearly proud of farm life..."*

Pattern signal: echo contains content tokens (proper nouns, key noun
phrases) that don't appear in the narrator's last message AND aren't
in the small allowed-paraphrase set (e.g. *"that"*, *"there"*, *"then"*,
generic location/time hedges). Compares echo's tokens against
`user_text` tokens.

### 5.4 `echo_contains_archive_language` — agenda revealed

> ❌ *"That gives us a good story candidate for the archive."*
>
> ❌ *"I'll save that to your record."*

Pattern signal: presence of `archive`, `record`, `database`, `field`,
`extract`, `candidate`, `for our records`, `saving that`, `noting that`,
`captured` in the echo span.

### 5.5 `echo_contains_diagnostic_language` — clinical posture

> ❌ *"That must have been traumatic."*
>
> ❌ *"That sounds like it shaped you deeply."*
>
> ❌ *"That's a sign of resilience."*

Pattern signal: `must have been`, `sounds like`, `shaped you`, `traumatic`,
`resilient`, `coping`, `processing`, `deeply`, `clearly affected`.

### 5.6 `echo_contains_unstated_emotion` — narrator's feelings invented

> Narrator: *"I had a mastoidectomy when I was little, in Spokane.
> My dad worked nights at the aluminum plant."*
>
> ❌ Lori: *"You were lonely in Spokane."*

Pattern signal: echo contains an affect token (`scared`, `lonely`,
`happy`, `sad`, `proud`, `angry`, `confused`, `anxious`, `relieved`,
`hurt`) that doesn't appear in narrator's last message.

---

## 6. Architecture — validator-only

Following §1.1 STA logic: a deterministic *rewriter* of reflection
content is high-risk because reflection is more semantic than
atomicity. A bad rewrite would invent narrator facts — exactly the
hallucination class WO-LORI-STORY-CAPTURE-01 LAW 3 is built to
prevent.

So the architecture splits cleanly:

| Concern    | Layer 1 (composer)         | Layer 2 (post-stream)            |
|------------|----------------------------|----------------------------------|
| Atomicity  | LORI_QUESTION_ATOMICITY    | Truncate-only filter             |
| Reflection | LORI_MEMORY_ECHO           | **Validator-only — log & fail**  |

For this WO's first version:

- **Validator runs.** Inspects the assistant_text + user_text, returns
  `(passed: bool, failure_labels: list[str])`.
- **No mutation.** Lori's text is sent unchanged. The harness records
  the reflection pass/fail as a quality signal, not a runtime
  intervention.
- **Operator sees the failures** via `[chat_ws][reflection]` log
  marker so trends are visible across runs. Bug Panel can surface
  reflection-failure rate later (separate WO).

Reason in one line: **atomicity is structure (deterministic rewrite
safe); reflection is content (deterministic rewrite unsafe)**.

If the harness shows persistent reflection failures even after Layer 1's
prompt directive lands, a future WO can add a guarded rewrite path —
but only on heavy evidence and with narrator-fact safety gates.

---

## 7. Implementation order

1. **Layer 1 — composer directive** (`prompt_composer.py`).
   New constant `_LORI_MEMORY_ECHO` block, appended to the existing
   `LORI_INTERVIEW_DISCIPLINE` block. Default-on. ~30 lines, no flag.

   ```text
   CRITICAL RULE: ECHO FIRST, ASK SECOND.

   For normal interview turns (not safety-acute):
   - Begin with ONE short sentence reflecting the narrator's last answer.
   - Use ONLY facts the narrator gave. No invented details.
   - Do not infer feelings unless the narrator stated them.
   - Do not mention archive, extraction, database, fields, candidates.
   - Echo length: 25 words or fewer.
   - Then ask one atomic question.
   ```

2. **Validator module** (`server/code/api/services/lori_reflection.py`).
   `validate_memory_echo(assistant_text: str, user_text: str) ->
   tuple[bool, list[str]]`. Pure-function; LAW-3 isolation gate
   added to the existing isolation test (or sibling). Tokenizes both
   sides, splits assistant_text at the first question-stem to isolate
   the echo span, runs each of the 6 illegal-echo regexes/checks.

3. **Wire-up** (`chat_ws.py`).
   In `_generate_and_stream_inner` after the assembled-text completion,
   alongside the atomicity filter call, run `validate_memory_echo()`.
   Skip when `_safety_result.triggered` is True. Log failures at
   `WARNING` level with `[chat_ws][reflection]` marker. **No
   modification to assistant_text.**

4. **Harness expansion**
   (`scripts/archive/run_golfball_interview_eval.py`).
   Each turn record gains:
   - `memory_echo_present: bool`
   - `memory_echo_word_count: int`
   - `memory_echo_grounded: bool`
   - `reflection_failures: list[str]`

   Cross-run pass criterion for normal interview turns:
   `reflection_failures == []`. Safety turns exempt.

5. **Unit-test pack**
   (`tests/test_lori_reflection.py`).
   ~20 cases covering each of the 6 illegal categories (positive
   detection); plus 8 positive cases (legitimate grounded echoes
   that must NOT trip); plus 4 edge cases (single-word answers,
   safety turns, narrator only said "yes" / "no", narrator gave
   no anchorable content).

6. **Live verify** — Chris reruns golfball harness. Expectation:
   Turns 02-04 produce echoes that pass. Turn 06 safety response
   exempt. Story_candidate creation unchanged.

---

## 8. Acceptance criteria

| # | Criterion | Verification |
|---|-----------|--------------|
| 1 | Validator correctly flags all 6 illegal-echo categories | `tests/test_lori_reflection.py` — 20/20 positive |
| 2 | Validator does NOT flag legitimate grounded echoes | 8/8 positive |
| 3 | Single-word narrator answers and edge cases handled gracefully (echo absence acceptable when narrator gave nothing to anchor) | 4/4 edge |
| 4 | Reflection validator SKIPPED when `_safety_result.triggered` (acute SAFETY response unchanged) | golfball harness Turn 06 |
| 5 | Golfball harness Turns 02-04 produce `reflection_failures: []` | golfball harness self-check |
| 6 | Story_candidate creation on Turn 02 (canonical 3-anchor) still fires | golfball harness self-check |
| 7 | Atomicity remains green: `atomicity_failures: []` on same turns | both lanes' harness checks |
| 8 | LAW-3 isolation: `lori_reflection.py` imports zero `routers/extract.py`, `prompt_composer.py`, `memory_echo.py`, `chat_ws.py`, or `routers/llm_*.py` symbols | static import-graph test |
| 9 | Master extractor eval pass count unchanged | r5h-place-guard rerun shows ≥75/110 |
| 10 | No new DB lock events introduced | `db_lock_events` delta before/after equals 0 |

---

## 9. Dispositions

- **ADOPT** if criteria 1-10 all green AND golfball-v2
  reflection_failures drop to 0 on Turns 02-04 across two consecutive
  runs after Layer 1 directive lands.
- **ITERATE** if Layer 1 alone takes care of <50% of cases — the
  composer directive may need stronger phrasing or the harness may
  need finer-grained labels to attribute failures.
- **PARK** if narrator content makes some echoes legitimately fail
  the regex (e.g. narrator says "I felt lonely" → Lori echoes "you
  felt lonely" → echo_contains_unstated_emotion would false-fire
  unless we whitelist narrator-provided affect tokens). Address by
  expanding the grounded-token comparison to include narrator's
  affect tokens before shipping. (This is anticipated but worth
  flagging.)
- **ESCALATE** if the validator flags Turn 06 safety responses despite
  the exempt — that means the safety-trigger flag isn't reaching
  this code path and the architecture needs review.

---

## 10. Files touched

```
server/code/api/prompt_composer.py                     (+~30 -0)
server/code/api/services/lori_reflection.py            (NEW, ~180 lines)
server/code/api/routers/chat_ws.py                     (+~15 -0)
scripts/archive/run_golfball_interview_eval.py         (+~30 -0)
tests/test_lori_reflection.py                          (NEW, ~250 lines)
tests/test_lori_reflection_isolation.py                (NEW, ~30 lines, LAW-3 gate)
WO-LORI-REFLECTION-01_Spec.md                          (this)
```

No `extract.py` changes. No schema migration. No DB writes added.
No mutation of assistant_text — validator-only.

---

## 11. Connections to existing lanes

- **WO-LORI-QUESTION-ATOMICITY-01** — strict prerequisite. Reflection
  layered on top of an atomic question; reflection without atomicity
  produces double trouble. Build order is enforced.
- **WO-LORI-SESSION-AWARENESS-01 Phase 2 (#285)** — Layer 1 directive
  appends to the same `LORI_INTERVIEW_DISCIPLINE` block.
- **WO-LORI-SAFETY-INTEGRATION-01 Phase 1 (#289)** — exempt path uses
  the same `_safety_result.triggered` flag.
- **WO-LORI-STORY-CAPTURE-01 LAW 3** — `lori_reflection.py` honors the
  same isolation contract (no extraction-stack imports).
- **BUG-DBLOCK-01 (#344)** — orthogonal but co-blocking parent
  sessions. Three independent gates: atomicity, reflection, safety
  lock. All three must clear before parent sessions.

---

## 12. Definition of done

```
WO-LORI-QUESTION-ATOMICITY-01 remains green.

Golf Ball harness shows:
  atomicity_failures:  []
  reflection_failures: []
  on Turns 02-04 across two consecutive runs.

Story_candidate creation still fires on canonical scene-anchor turns.

Safety turns (Turn 06) produce ACUTE SAFETY response unchanged
(reflection validator exempt for safety category).

No new DB lock events introduced.

Master extractor eval pass count unchanged
(reflection is chat-side; extractor untouched).
```

---

## 13. Estimate

- §7.1 Layer 1 composer directive: 1 hour
- §7.2 lori_reflection.py validator + 6 illegal-category checks: 4 hours
  (token comparison logic, affect-token list curation, edge-case
  handling)
- §7.3 chat_ws.py wire-up + safety exempt + log marker: 1 hour
- §7.4 harness expansion + 6 reflection field labels: 1.5 hours
- §7.5 unit-test pack (~20 positive + 8 negative + 4 edge): 3 hours
- §7.6 LAW-3 isolation test: 0.5 hour
- §7.7 live verify (Chris's stack): asynchronous

Total build: ~11 hours. Lands as 4 commits, code-isolated from docs.

---

## 14. Anti-goals

- Do NOT add reflection generation. Validator only.
- Do NOT use an LLM call inside the validator. Same STA-grounded
  determinism rule as atomicity.
- Do NOT exempt the validator on session_style. Style varies tone;
  structure (echo + question) is fixed across all interview styles.
- Do NOT log narrator content in `[chat_ws][reflection]` warnings.
  Log failure labels only, plus the assistant_text echo span if
  needed for debugging — but never the user_text.
- Do NOT exempt companion mode at this stage. Companion mode may
  surface different echo styling, but the rule that an echo MUST
  exist and be grounded applies universally.

---

## 15. Future v2 considerations (parked, not in this WO)

- **Narrator-provided affect-token whitelist.** When narrator says
  *"I felt lonely"*, Lori echoing *"you felt lonely"* should pass
  even though "lonely" is in the §5.6 illegal-affect list. v2 makes
  the validator narrator-affect-aware.
- **Companion-mode echo softening.** Companion mode may favor shorter,
  more affective echoes; v2 may relax §5.6 strictness for that style
  if the harness shows regression.
- **Guarded rewrite path.** If Layer 1's prompt directive proves
  insufficient and the harness shows persistent reflection failures,
  v2 may scope a *narrator-fact-bounded* rewrite — but only with
  strong safety gates against fact invention.