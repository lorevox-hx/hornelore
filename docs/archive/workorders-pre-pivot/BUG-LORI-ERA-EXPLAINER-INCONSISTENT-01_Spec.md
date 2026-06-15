# BUG-LORI-ERA-EXPLAINER-INCONSISTENT-01 — Era-explainer ("what are the building years") inconsistent across narrators and turns

**Status:** OPEN — likely partially-resolves via WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01 Phase 1; verify after Phase 1 lands.
**Severity:** AMBER — narrator-visible, narrator-explicit confusion. Older narrators with cognitive load can't track which turn produced which response.
**Surfaced by:** Manual switch transcript 2026-05-06 02:59–03:01 (`transcript_switch_motgx.txt`). Mary asked "what are the building years" three times across 90 seconds and got three different responses — none of which actually explained the era.
**Author:** Chris + Claude (2026-05-05; filed during night-shift Phase 0 BUG sweep)
**Lane:** Lane 2 / parent-session blockers — subordinate to QF-RETIRE Phase 1.

---

## Problem

The "Era Explainer" feature (added 2026-05-04 in `prompt_composer.py` listener-arc polish) was supposed to give Lori a consistent way to respond when the narrator asks what an era means. The block reads roughly: when narrator references one of the 7 canonical eras, explain it warmly with a narrator-friendly description ("the years before you started school" / "the building years when you were starting your family or career") rather than treating the era_id as opaque.

In practice, the explainer fires inconsistently — different responses to the same question across consecutive turns, sometimes dodging the request entirely.

## Evidence

`transcript_switch_motgx.txt` — Mary mid-session, after the operator clicked "Building Years" on her Life Map:

```
[2026-05-06 02:59:56] USER: what are the building years

[2026-05-06 03:00:01] ASSISTANT: The building years — that's a great term
for this period in your life. What do you remember about where you were
living during your building years?

[2026-05-06 03:00:13] USER: [SYSTEM: The narrator just selected 'Building
Years' on the Life Map — they want to talk about this era of their life.
Ask ONE warm, open question about this period...]

[2026-05-06 03:00:18] ASSISTANT: During your building years, what do you
remember about your daily routine when you were working and raising your
family?

[2026-05-06 03:00:26] USER: what are the building years

[2026-05-06 03:00:31] ASSISTANT: During your building years, what do you
remember about your daily routine when you were working and raising your
family?

[2026-05-06 03:01:12] USER: what are the building years

[2026-05-06 03:01:18] ASSISTANT: It seems like you'd like to revisit what
the building years mean to you. Shall we go back to exploring what that
era entails?
```

Three distinct failure modes in one minute:
1. **First ask (02:59:56):** Lori acknowledges the term but doesn't explain it; pivots to a question.
2. **Second ask (03:00:26):** Lori repeats her prior turn verbatim — completely fails to explain.
3. **Third ask (03:01:12):** Lori meta-acknowledges Mary wants the explanation but offers to "explore" it instead of just explaining it.

A narrator who explicitly asks "what are the building years" three times deserves a definition. None of those three responses contain one.

For comparison, in earlier production transcripts where SYSTEM_QF was NOT racing the turn, Lori has produced clean era explanations like "The building years are the years when you're typically establishing your career, raising children, putting down roots in a community — usually mid-20s through mid-50s."

## Diagnosis hypotheses (ranked)

**Hypothesis 1 (likely): SYSTEM_QF preemption was a major factor.** The transcript shows SYSTEM_QF active alongside Mary's session (the birth-order question fired at 02:59:32). The era explainer block in `prompt_composer.py` may have lost turn ownership when SYSTEM_QF / Life Map system prompts competed for the response slot. After WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01 Phase 1 lands, re-test — if the explainer fires consistently, this BUG closes via that retirement.

**Hypothesis 2: Era-click system prompt overrides the explainer.** At 03:00:13 a `[SYSTEM: The narrator just selected 'Building Years' on the Life Map — ... Ask ONE warm, open question...]` directive fires, instructing Lori to ASK rather than EXPLAIN. The era-click directive is upstream of the era-explainer block; when both apply, the era-click "ask one question" wins. Mary asking "what are the building years" is treated as engagement with the era (so the directive fires) instead of a request for a definition (which would route to the explainer).

**Hypothesis 3: The explainer block lacks discriminator logic for "explain vs ask."** Per `prompt_composer.py` listener-arc polish (2026-05-04), the explainer instructs Lori to use warm era labels when REFERENCING an era. It does not include a "when narrator explicitly asks 'what are the X years'" branch that would force a definition. The composer sees "building years" mentioned by the narrator and routes to the warm-label-reference path, not the define-the-era path.

**Hypothesis 4: Caching / deduplication produces verbatim repetition.** The 03:00:26 → 03:00:31 turn pair shows Lori's response IS bit-identical to the previous turn. That suggests either a response cache, a turn-loop reset that re-fires the same composer with same inputs, or the LLM sampling at low temperature with identical context — all of which produce repetition. Separate BUG (BUG-LORI-DUPLICATE-RESPONSE-01).

## Reproduction

After QF-RETIRE Phase 1 lands:

1. Open Mary in a real browser (returning narrator with prior turns).
2. Click "Building Years" on her Life Map.
3. After Lori asks her opening question for that era, type: `what are the building years`.
4. Expected: Lori produces a definition like *"The building years are the years when you're typically raising a family or building a career — roughly mid-20s through mid-50s."*
5. Failure mode: Lori asks another question, repeats a previous turn, or offers to "explore" without defining.

Run this test 5 times consecutively. The explainer should fire consistently across all 5 — same shape, possibly varied wording.

## Fix shape

**Phase 1 — Verify QF-RETIRE auto-resolution.** After WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01 Phase 1 lands, re-run the reproduction above. If the explainer fires consistently for all 5 attempts, this BUG closes.

**Phase 2 (only if Phase 1 doesn't auto-resolve)** — sharpen the explainer block. Two candidate sub-fixes:

(a) Add a deterministic "explainer trigger" detector to `prompt_composer.py`: regex `\bwhat\s+(are|is)\s+the\s+(\w+\s+)?(years|era|period)\b` matched against narrator text. When matched AND narrator's text is otherwise short (≤ 10 words), force a DEFINITION response template, not a question template. Override era-click directive when this matches.

(b) Add a deterministic "explainer dispatch" surface in `lori_communication_control.py` Step 4 (between memory_echo / interview_question / repair) that detects era-explanation-requests and routes them to a new `compose_era_explanation()` deterministic composer. Same posture as `compose_memory_echo` — pure, no LLM, reads the era_id from `state.session.currentEra` and emits a fixed-shape definition from a `_LV_ERA_DEFINITIONS` dict.

Option (b) is cleaner — gives the era-explainer its own deterministic surface, immune to LLM sampling variability and prompt-rule competition.

## Acceptance gate

After fix:
- 5/5 attempts at "what are the building years" (and equivalent across other 6 eras) produce a recognizable definition that includes the era's defining feature (years before school / school / adolescence / coming of age / building / later / today).
- No verbatim repetition of prior turn responses.
- Era-click warm-prompt path still works (clicking an era still produces an era-anchored question; explanation path only fires for explicit questions).
- 30 minutes of manual testing across both Mary and Marvin, both narrators get consistent explainer behavior.

## Files (planned, only if Phase 2 needed)

- `server/code/api/prompt_composer.py` — add explainer trigger detection OR `compose_era_explanation()` function + warm-definition map.
- `server/code/api/services/lori_communication_control.py` — Step 4 routing addition (only if option b chosen).
- `tests/test_compose_era_explanation.py` — 7 era × 3 question-shape unit tests.

## Risks and rollback

**Risk 1: false-positive explainer.** A narrator saying "the building years were hard for us" might match the regex and get a definition rather than an empathetic engagement. Mitigation: trigger requires the question word ("what / what are / what is") AND the era reference; affirmative statements with era references don't trigger.

**Risk 2: explainer wording feels canned across many sessions.** Same definition every time. Mitigation: the warm-definition map can have 2-3 variants per era; pick one by `hash(session_id) % len(variants)`. v1 ships with one variant per era; variation is a v1.1.

**Rollback:** revert. Era explainer returns to the listener-arc polish behavior. Mary still gets inconsistent responses but no regression on other surfaces.

## Sequencing

**Land AFTER WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01 Phase 1.** That retirement is likely the largest single contributor to the inconsistency. After Phase 1, re-test before scoping any code change for this BUG. If still failing, Phase 2 of THIS bug is a small focused change (~50 lines + tests).

## Cross-references

- **WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01** — landing Phase 1 likely partially-resolves this BUG (verify after Phase 1).
- **BUG-LORI-SYSTEM-QF-PREEMPTION-01** — closes when QF-RETIRE Phase 1 lands; this BUG is a downstream symptom.
- **BUG-LORI-DUPLICATE-RESPONSE-01** — separate BUG covering the verbatim repetition at 03:00:26 → 03:00:31. Same Mary transcript, different mechanism.
- **CLAUDE.md design principle 6** ("Lorevox is the memory system; Lori is the conversational interface to it") — era definitions belong in deterministic system data, not LLM-generated prose. Option (b) of Phase 2 fix aligns with principle 6.

## Changelog

- 2026-05-05: Spec authored during night-shift Phase 0 BUG sweep after re-reading `transcript_switch_motgx.txt` for the QF-retirement context. Sequenced after QF-RETIRE Phase 1 to avoid premature implementation when the root may be QF preemption.
