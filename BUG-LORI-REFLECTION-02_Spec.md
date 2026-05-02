# BUG-LORI-REFLECTION-02 — Runtime-shaped reflection enforcement

**Status:** SPEC — scoped, not yet implemented
**Date:** 2026-05-02
**Lane:** Lori behavior. Successor to BUG-LORI-REFLECTION-01 (committed 2026-05-02 morning at SHA `ea13cbf`).
**Sequencing:** Opens after one cooling-off session. Patch B's failure (see Lessons Learned below) is fresh; next iteration must approach from a different angle, not a tighter version of the same angle.
**Blocks:** Nothing. v1's 4/8 floor is preserved as the active baseline; this WO targets pushing toward 6-7/8 without the regression risk that prompt-only iteration carries.

---

## The locked design constraint (PRINCIPLE, not finding)

```
Prompt-heavy reflection rules make Lori worse, not better.

The next reflection iteration MUST be runtime shaping,
NOT more prompt paragraphs.
```

This is not a hypothesis. It is the empirical lesson banked from BUG-LORI-REFLECTION-01 Patch B (2026-05-02 evening), which regressed golfball from **4/8 → 1/8** by adding two new prompt rules and extending one. The prompt+LLM interaction interpreted the additions as "always reflect, fill the budget" — exactly the behavior we wanted to suppress.

This WO opens FROM that constraint, not toward discovering it.

## Mission

Move reflection enforcement from prompt-only to runtime shaping. The prompt can ASK Lori to echo briefly; the code ENFORCES the final shape.

```
Stop hoping the model obeys:
    "Never skip the reflection."

Instead enforce:
    If assistant_text has no echo anchor:
        prepend a short deterministic anchor sentence.
    If assistant_text echo exceeds 25 words:
        truncate to first concrete-noun mention + question.
    If softened mode is active:
        apply a separate, tighter shape contract.
```

## Three runtime layers (build all three; ship behind a flag)

### Layer 1 — Anchor extraction

A small deterministic function `extract_concrete_anchor(narrator_text) -> str | None` that returns one short noun-phrase suitable for an echo opener. Pulled from narrator text only. Never invented.

```
Inputs:  narrator_text (the user's last turn)
Output:  one short string, e.g. "Spokane", "Captain Kirk", "the
         aluminum plant", "your dad" — OR None if nothing extractable
         (trivial response, garbled STT, etc.)

Algorithm:
  1. Tokenize. Apply existing _content_tokens() pipeline (kinship
     canon, stem, possessive strip — already in tree from
     BUG-LORI-REFLECTION-01 A.2).
  2. Score tokens by anchor-suitability (proper nouns > kinship terms
     > common content nouns > everything else).
  3. Return the highest-scoring concrete-noun phrase, or None.

Coupling to WO-EX-UTTERANCE-FRAME-01:
  When the Utterance Frame WO eventually lands, this anchor extraction
  becomes a thin wrapper over frame.clauses[*].place ∪ object ∪
  who_canonical. Until then, this is a standalone deterministic
  function with its own tests.
```

### Layer 2 — Echo prepend / trim

A runtime check on the LLM's emitted assistant_text:

```
def shape_reflection(assistant_text, narrator_text) -> str:
    anchor = extract_concrete_anchor(narrator_text)
    echo_span, question_span = _split_echo_and_question(assistant_text)

    # Case A: trivial narrator → no shaping needed
    if narrator is trivial-response (existing rule):
        return assistant_text

    # Case B: Lori produced no echo → prepend anchor
    if not echo_span and anchor:
        return f"{anchor}. {assistant_text}"

    # Case C: Lori's echo is too long → trim to anchor + question
    if echo_span and len(echo_span.split()) > ECHO_WORD_BUDGET:
        if anchor and anchor.lower() in echo_span.lower():
            return f"{anchor}. {question_span}"
        return question_span  # drop bloated reflection entirely

    # Case D: echo present + within budget → pass through
    return assistant_text
```

Behavior contract:
- Pure post-LLM transformation; no LLM round-trip.
- Idempotent: calling twice produces the same output.
- Logs `[lori][reflection-shape]` for every shaping action so operators see what got rewritten.
- Default-OFF behind `HORNELORE_REFLECTION_SHAPING=1` for the first eval cycle.

### Layer 3 — Softened-mode separate cap

Softened-mode turns (post-safety, distress-acknowledgment, presence) have their own shape contract that's TIGHTER than ordinary turns:

```
Softened-mode shape contract:
  - Max 30 words per turn (vs 55 for ordinary)
  - Max 1 short sentence reflecting narrator's words
  - Max 1 invitation question (NOT a probe)
  - No memoir pivot
  - No "would you like to..." / "tell me about..." menus

Runtime enforcement:
  if softened_mode_active and len(assistant_text.split()) > 30:
      truncate to first sentence + drop trailing question if needed.
```

This addresses the v2 T07/T08 regressions (Lori's softened-mode responses ballooning to 40-50 words of supportive monologue). Softened mode shouldn't share the ordinary 55-word cap.

## What this WO does NOT do

- **Add prompt paragraphs.** Period. The constraint at the top is non-negotiable for this iteration.
- **Touch the existing kinship canon / stemmer / possessive strip / comma-boundary regex.** Those are A.2 base, already in tree, working.
- **Replace LORI_INTERVIEW_DISCIPLINE.** The existing prompt block stays as-is. We're adding runtime shaping AROUND it, not replacing it.
- **Solve the safety-classification nuance.** T05 stays in WO-LORI-SAFETY-PASSIVE-DEATH-WISH-01's lane.
- **Solve the same-place dual-subject extraction gap.** That's WO-EX-UTTERANCE-FRAME-01 territory.

## Phase plan

```
Phase 0 — Reset baseline
  - Confirm v1's 4/8 is still the active golfball floor.
  - Run golfball-baseline-confirm to lock the number before any
    Phase 1 work.
  Risk: zero (read-only).

Phase 1 — Layer 1 (anchor extraction, standalone)
  - Build extract_concrete_anchor() in lori_reflection.py or a
    new lori_anchor.py.
  - Unit tests against the actual narrator turns from golfball T01-T08
    + canon-grounded eval cases.
  - NOT wired into chat path yet.
  Risk: zero (no integration).

Phase 2 — Layer 2 (echo prepend / trim, default-off)
  - Implement shape_reflection() per the contract above.
  - Wire into chat_ws.py post-LLM-response path, behind
    HORNELORE_REFLECTION_SHAPING=1.
  - Log every shaping action via [lori][reflection-shape] marker.
  - Run golfball with flag ON; compare against v1's 4/8 baseline.
  Risk: medium (rewrites real LLM output).
  Acceptance: ≥ 5/8 turns pass, no DB lock regression, no T01/T03/T07
  regressions vs v1 baseline.

Phase 3 — Layer 3 (softened-mode separate cap, default-off)
  - Add softened-mode shape contract to shape_reflection().
  - Behind HORNELORE_REFLECTION_SHAPING=1 (same flag as Layer 2).
  - Run golfball with flag ON; T07/T08 should clear.
  Risk: medium (changes softened-mode visible behavior).
  Acceptance: 6+/8 turns pass with non-safety turns clean.

Phase 4 — Default-on after two clean golfball reruns
  - Two consecutive golfball passes at ≥ 6/8 with the flag ON.
  - Then flip HORNELORE_REFLECTION_SHAPING=1 in .env.example.
  - Document the cutover in CLAUDE.md changelog.
```

## Acceptance gates (per phase)

```
Phase 0  [ ] golfball-baseline-confirm rerun banks at 4/8
         [ ] No tree dirt before Phase 1 starts

Phase 1  [ ] extract_concrete_anchor() unit tests pass on:
             - simple identity ("born in Montreal" → "Montreal")
             - multi-noun ("Captain Kirk and T.J. Hooker" → either)
             - kinship ("my dad" → "your dad" / "father")
             - trivial ("Thank you" → None)
             - garbled STT ("um yeah I think" → None)
         [ ] Pure deterministic; no LLM, no DB, no IO

Phase 2  [ ] golfball with flag ON ≥ 5/8 (improvement vs v1's 4/8)
         [ ] T01/T03/T07 do NOT regress vs v1 (these were Patch B's
             casualty list; we don't repeat that)
         [ ] [lori][reflection-shape] logs visible in api.log for
             every shaped turn
         [ ] Pure post-LLM; flag OFF returns to v1 byte-stable

Phase 3  [ ] golfball with flag ON ≥ 6/8
         [ ] T07/T08 specifically clear (softened-mode brevity)
         [ ] No new failure modes vs Phase 2

Phase 4  [ ] Two consecutive golfball passes at ≥ 6/8 with flag ON
         [ ] .env.example default flipped to =1
         [ ] CLAUDE.md changelog cutover entry banked
```

## Lessons learned (preamble carried forward from Patch B)

For posterity and to prevent re-litigation in future iterations:

```
2026-05-02 Patch B postmortem:

We added two new prompt rules (Rule 5 NEVER SKIP + extended Rule 4
INVENTED CONTEXT) plus two validator changes (trivial-response
symmetry + broadened pseudo-empathy regex). The validator changes
were neutral. The prompt changes regressed golfball from 4/8 to 1/8.

Root cause: the prompt told Lori "≤25 words for reflection" in one
rule and "≤55 words per turn" in another. The LLM interpreted this
as "I have 55 words to spend on reflection if I want." Adding Rule 5
("never skip the reflection") removed the safety valve and pushed
Lori to fill the budget. Patch B's "be more careful" framing made
Lori try harder, and trying harder under contradictory rules
produced longer, more invented, more abstract reflections.

Lesson: the model is not consistently obeying more prompt text.
Adding more instructions to a system that's already over-instructed
is negative-progress. The path forward is to enforce the shape in
code, not in prose.

Implementation rule for this WO and successors:
  Never solve a Lori-behavior problem by adding more prompt text
  unless ALL of these are true:
    (a) The current prompt has fewer than 5 explicit reflection
        rules covering the specific behavior class.
    (b) The proposed rule replaces an existing rule, not stacks
        on top of it.
    (c) An adversarial harness eval has been pre-run to confirm
        the prompt change doesn't regress orthogonal turns.
  Otherwise: build runtime enforcement.
```

## Sequencing relative to other lanes

```
BUG-LORI-REFLECTION-01 (committed ea13cbf) — A.1 prompt + A.2 base
                                              validator. v1 = 4/8 floor.
                                              ↓
BUG-LORI-REFLECTION-01 Patch B (REJECTED)  — Tried more prompt rules.
                                              Regressed to 1/8. Reverted.
                                              ↓
BUG-LORI-REFLECTION-02 (this WO)          — Runtime shaping. Anchor
                                              extraction → echo prepend
                                              / trim → softened-mode
                                              separate cap.
                                              ↓
WO-EX-UTTERANCE-FRAME-01 (parked)         — Provides the structural
                                              representation that
                                              Layer 1's anchor
                                              extraction eventually
                                              consumes (frame.clauses
                                              [*].place ∪ object ∪
                                              who_canonical).
```

## The product rule (echoes WO-LORI-LANGUAGE-CANON-01)

```
Prompt   = what we ASK Lori to do.
Runtime  = what we ENFORCE on Lori's output.
Schema   = what Lori CAN know.
Truth    = what Lori is allowed to TRUST.

The prompt's role is guidance.
The runtime's role is shape.
When guidance and shape conflict, shape wins.
```
