# WO-LORI-ACTIVE-LISTENING-01 — One-question interview discipline + active reflection

**Status:** SPEC (companion to WO-LORI-SESSION-AWARENESS-01 Phase 2)
**Authors:** Chris Horne + ChatGPT (behavior diagnosis), Claude (synthesis)
**Date:** 2026-04-29
**Sequencing:** Behavior lane. Companion to WO-LORI-SESSION-AWARENESS-01 Phase 2 ("interview discipline composer guard"). Different surface, same evaluation harness (`WO-LORI-RESPONSE-HARNESS-01` Test Type A).
**Lane:** Lori behavior. NOT extractor lane. Do NOT mix with SPANTAG / BINDING / LORI-CONFIRM work.
**Blocks:** parent sessions — Janice + Kent need single-question discipline before first contact (high cognitive load risk for older narrators).

---

## Why this exists

Two parallel observations during Hornelore live testing surfaced the same root cause:

1. **Chris's read** (2026-04-29): "Lori talks too much. She asks more than one question. She nests questions. She does not always practice active listening."

2. **The Christopher live test** (2026-04-28): When Lori responded to Chris's
   long autobiographical answer, she replied:
   > "Chris, I'm so glad you shared this rich and detailed account of your life. As you reflect on the journey you've been on, what do you remember about the daily life, routines, and rhythms of growing up in Williston, North Dakota, during your childhood?"
   >
   That sentence has FOUR question hooks ("daily life", "routines", "rhythms",
   "growing up") AND assumes the narrator's interpretive lens ("the journey
   you've been on"), AND restates context the narrator already established.
   It's verbose and high-cognitive-load.

The narrator-trust impact is severe: **older narrators (the parent-session
target audience) will freeze, ask "which question first?", or pick the easiest
question and skip the rest.** Lori must speak like a human interviewer, not a
questionnaire menu.

## The behavior contract

### Rules (load-bearing — these go in the system prompt as `LORI_INTERVIEW_DISCIPLINE`)

```
For ordinary narrator turns:
- Acknowledge what the narrator said.
- Reflect ONE concrete detail from their last turn.
- Ask ONE question only.
- No nested questions.
- No "and also" follow-up questions in the same turn.
- No question lists.
- No "or we could…" / "would you rather…" / "which path…" menu offers.
- Maximum 90 words per turn (target ≤ 55 unless the narrator explicitly
  asks for a summary).
- If the narrator asks a direct question, ANSWER IT FIRST. Then
  ask one follow-up if appropriate.
- If the narrator seems unsure, simplify the question instead of
  adding choices.
- Do not summarize the whole life story unless the narrator asks.
- After a long disclosure: reflect ONE specific detail, then ask ONE
  concrete follow-up.
```

### Bad / Good examples

**Bad** (compound + nested):
> "That sounds meaningful. What was your mother like, and where were you
> living then, and did your siblings feel the same way?"

**Good** (single concrete reflection + single question):
> "That sounds like your mother carried a lot of steadiness in the family.
> What is one scene that shows what she was like?"

**Bad** (menu offer):
> "Would you like to talk about your father's work, or would you rather
> tell me about your school years, or maybe move forward to your career?"

**Good** (one path, narrator-led):
> "What part of your father's work stayed with you?"

**Bad** (restates context + nests):
> "As you reflect on the journey you've been on, what do you remember
> about the daily life, routines, and rhythms of growing up in
> Williston, North Dakota, during your childhood?"

**Good** (specific anchor + single question):
> "You mentioned long winters and exploring outdoors with your brothers.
> What was a typical winter day like for the three of you?"

## Implementation

### Two-layer defense (both layers ship together)

**Layer 1 — System prompt block (primary).** Inject `LORI_INTERVIEW_DISCIPLINE` constant into the system prompt after the session-style block and before any question-generation instructions.

```python
# server/code/api/prompt_composer.py

LORI_INTERVIEW_DISCIPLINE = """
INTERVIEW DISCIPLINE — STRICT

You are an oral-history interviewer, not a questionnaire menu.

For ordinary narrator turns:
- Maximum 90 words.
- Ask at most ONE question.
- Ask at most ONE actual thing.
- Do not ask compound, double-barreled, or multi-part questions.
- Do not offer menus such as "or we could..." / "would you rather..."
  / "which path...".
- Do not summarize the whole life story unless the narrator asks.
- After a long disclosure: reflect ONE specific detail, then ask
  ONE concrete follow-up.
- If the narrator seems unsure, simplify the question instead of
  adding choices.
- If the narrator asks a direct question, answer it first.

Preferred shape:
1. One brief reflection anchored to the narrator's exact words.
2. One concrete follow-up question.
"""
```

The composer guards:
- Inject after session_style_directive block, before pass-mode directives
- Keep the constant visible in the discipline-header logging so the operator can confirm it's loaded

**Layer 2 — Runtime filter (fallback).** When the LLM drifts past 1 question, trim. Live-tested regex pattern set:

```python
# Detect compound / nested
COMPOUND_QUESTION_RX = re.compile(
    r'\?[^?]*\b(and|or|also|plus|maybe|perhaps)\b[^?]*\?',
    re.IGNORECASE
)

# Detect menu-offer phrases (per ChatGPT's lock — refined to avoid
# false positives on legitimate "would you like to" structure)
MENU_OFFER_RX = re.compile(
    r'\b(would you like to .{0,80}\bor\b)|'
    r'\b(would you rather)\b|'
    r'\b(which path)\b|'
    r'\b(or we could)\b',
    re.IGNORECASE
)

def _trim_to_one_question(text: str) -> str:
    """Keep the first question; drop subsequent ones with a 'we can come
    back to that' bridge."""
    parts = re.split(r'(?<=\?)\s+', text, maxsplit=1)
    if len(parts) <= 1:
        return text
    head = parts[0]
    return head + " (We can come back to the rest in a moment.)"
```

The filter is the safety net, not the primary defense — Layer 1's prompt
discipline does the real work. Layer 2 catches the LLM drifts the prompt
discipline misses.

### Eval metrics (added to existing WO-LORI-RESPONSE-HARNESS-01 Test Type A)

```
question_count                    Per Lori turn. Must be ≤ 1 except
                                  in summary turns (memory-echo, etc.).
nested_question_count             Must be 0.
word_count                        Target ≤ 90 except summary turns.
direct_answer_first               Boolean. True if narrator asked a
                                  direct question. Must be true if
                                  user_turn_had_direct_question.
active_reflection_present         Boolean. True if Lori turn echoes a
                                  specific detail from the prior
                                  narrator turn (heuristic: first
                                  10 words contain a noun or noun
                                  phrase from prior narrator turn).
asks_question_after_user_question Allowed only after answering.
                                  False = pass; True without
                                  direct_answer_first = fail.
menu_offer_count                  Count of "or we could / would you
                                  rather / which path" patterns.
                                  Must be 0.
```

These metrics ride on the existing WO-LORI-RESPONSE-HARNESS-01 harness
(no new harness needed). Add them as Test Type A scoring rules.

## Phase plan

```
Phase 1 — System prompt block (primary defense)
  - Add LORI_INTERVIEW_DISCIPLINE constant to prompt_composer.py
  - Inject in compose_system_prompt() after session_style_directive
  - Verify via discipline-header that the block is loaded
  Risk: low. Pure additive prompt change.

Phase 2 — Runtime filter (safety net)
  - Add _trim_to_one_question helper to prompt_composer.py
  - Wire into chat_ws.py post-LLM-response path
  - Log filter hits as [filter][trim-to-one-q] for operator audit
  Risk: medium. Filters real LLM output. Default off (env flag);
  enable after Phase 1 + eval shows the prompt-only path isn't
  enough.

Phase 3 — Eval metrics
  - Extend WO-LORI-RESPONSE-HARNESS-01 Test Type A scoring with the
    six metrics above
  - Run baseline (current behavior) → snapshot
  - Run with Phase 1 active → snapshot
  - Run with Phase 1+2 active → snapshot
  - Compare regressions per metric
  Risk: zero. Eval-only.
```

## Acceptance gates

```
Phase 1 (prompt-only)
  [ ] LORI_INTERVIEW_DISCIPLINE present in system prompt
  [ ] Discipline header logs the block on every chat turn
  [ ] Eval Test Type A baseline score improves (question_count
      median drops from baseline to ≤ 1.5)
  [ ] Manual smoke: ask Lori an open question, confirm reply has
      ≤ 1 question

Phase 2 (filter)
  [ ] _trim_to_one_question helper unit-tested with known compound
      + nested + menu-offer inputs
  [ ] Filter hits logged at INFO level
  [ ] Eval Test Type A score reaches 0 nested_question_count and 0
      menu_offer_count even on adversarial inputs

Phase 3 (eval)
  [ ] All six metrics implemented in WO-LORI-RESPONSE-HARNESS-01
  [ ] Three baseline runs banked (pre-discipline / Phase 1 / Phase 1+2)
  [ ] Regression report generated comparing the three
```

## Out of scope

- Restricting Lori's vocabulary or warmth. The discipline is about
  STRUCTURE, not tone. Lori can still be warm + curious; she just
  has to be brief and singular.
- Special handling for memory-echo turns — those are already
  exempt (memory-echo is allowed to be longer + structured because
  the narrator explicitly asked for a summary).
- Adversarial / tricky narrator inputs (sarcasm, hostility,
  cognitive variability) — handled in WO-10C Cognitive Support Mode
  + WO-LORI-SAFETY-INTEGRATION-01.

## Sequencing relative to other Lori-behavior WOs

```
WO-LORI-SESSION-AWARENESS-01 Phase 1   (memory echo fix)
WO-LORI-SESSION-AWARENESS-01 Phase 2   (interview discipline composer)
                                       ↑
                                       This WO is the spec for that phase's
                                       discipline rules + filter implementation.
                                       Land both together.
WO-LORI-RESPONSE-HARNESS-01 Test A     (eval surface; consume the metrics
                                        added here)
WO-LORI-CONFIRM-01                     (confirmation pass; depends on
                                        SESSION-AWARENESS Phase 1 facts
                                        being trustworthy)
WO-LORI-SAFETY-INTEGRATION-01          (parallel, independent)
```

## The product rule

```
Schema    = what Lori CAN know.
Truth     = what Lori is allowed to TRUST.
Behavior  = how Lori SPEAKS when asked.

Brevity   = respect for the narrator's cognitive load.
Singular  = respect for the narrator's autonomy.
Reflection = proof Lori was actually listening.
Direct-answer-first = respect for the narrator's question.
```
