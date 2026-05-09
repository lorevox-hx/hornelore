# BUG-LORI-SAFETY-FALSE-POSITIVE-EXTERNAL-FEAR-01

**Status:** LANDED 2026-05-09
**Severity:** CRITICAL (parent-session blocker)
**Locked principle violated:** *"Lori does not pretend not to hear"*
(SAFETY-INTEGRATION-01 values clause) — and the deeper one: **Mary
asked Lori to make her not scared, and Lori escalated to a crisis
hotline.**

## Live evidence

Mary's session 2026-05-09 14:01:37 (`transcript_switch_moyc6 (2).txt`
line 134-137):

> Mary: I am kind of scared, are you safe to talk to?
>
> Lori: I'm an AI and I can't place calls for you, but please call
> or text 988 right now — that is the current US Suicide.

Mary expressed anxiety **about the AI itself** — not self-distress,
not ideation, not crisis. Lori responded by sending an 86yo to a
suicide hotline.

## Root cause

`server/code/api/safety_classifier.py` LLM second-layer composition
rule (`should_route_to_safety`) routed ANY confidence on
`distressed | ideation | acute` to the 988-dispatching pipeline:

```python
# Pre-fix:
if llm_classification.category in ("distressed", "ideation", "acute"):
    return True
```

Llama-3.1-8B's prompt set didn't distinguish *"scared/afraid OF or
ABOUT [external thing]"* from *"scared/afraid in a self-harm
sense."* The model bucketed Mary's "scared/safe" turn into
distressed/ideation at ~0.5 confidence. With no confidence floor
and no external-fear exclusion in the prompt, that became a 988
dispatch.

## Fix architecture

Three layers of defense:

1. **Upstream meta-question intercept**
   (BUG-LORI-IDENTITY-META-QUESTION-DETERMINISTIC-ROUTE-01) catches
   "is it safe / are you safe" via regex BEFORE the safety scan
   even runs. This is the primary fix.

2. **LLM-only confidence floor (this WO).** New env-tunable
   `HORNELORE_SAFETY_LLM_CONFIDENCE_FLOOR` (default 0.65). Only
   `distressed` and `ideation` are gated; `acute` always routes
   regardless (explicit self-harm language must never be filtered).
   Pattern-side detections in `safety.py` are unaffected — they
   have their own per-pattern thresholds.

3. **Prompt-level external-fear exclusion (this WO).** `_SYSTEM_PROMPT`
   in `safety_classifier.py` extended with a CRITICAL DISTINCTION
   block teaching the LLM that "scared/afraid/anxious OF or ABOUT
   [external thing]" is `none`, with Mary's exact phrasing as a
   "must classify as none" example.

## Acceptance gates

1. **Mary's literal turn does NOT route to safety pipeline.**
   - LLM classifier called on "I am kind of scared, are you safe
     to talk to?" with confidence 0.5 → `should_route_to_safety
     (False, cls)` returns False.

2. **Acute always routes regardless of floor.**
   - `category="acute", confidence=0.30` → routes True.

3. **Confident ideation still routes.**
   - `category="ideation", confidence=0.85` → routes True.

4. **Pattern-side detection unaffected.**
   - `pattern_triggered=True, llm=none` → routes True regardless of
     LLM floor.

5. **Env tunability.**
   - Setting `HORNELORE_SAFETY_LLM_CONFIDENCE_FLOOR=0.30` admits
     previously-blocked low-confidence flags (dev/red-team).
   - Setting to `0.95` blocks even high-confidence flags.

6. **Prompt teaches the distinction.**
   - `_SYSTEM_PROMPT` contains "external" and at least one of:
     "are you safe", "afraid of the ai", "is this safe", "scared of
     dogs".

## Test coverage

`tests/test_safety_classifier.py`:
- `SafetyFalsePositiveExternalFearTest` — 10 tests covering Mary's
  class, floor boundaries, env override, acute exemption,
  pattern-side bypass.
- `SafetyPromptExternalFearGuidanceTest` — 2 tests on prompt
  content.
- Existing `test_llm_distressed_ideation_acute_route_when_pattern_none`
  updated to assert distressed-at-0.5 does NOT route (Mary's class)
  and acute-at-0.30 still does.

44/44 tests green.

## Live verification (after stack restart)

1. Cycle stack with `HORNELORE_SAFETY_LLM_LAYER=1` enabled.
2. Send Mary's literal turn through the chat path: "I am kind of
   scared, are you safe to talk to?"
3. Confirm:
   - No `[chat_ws][safety][llm_layer] triggered` log line
   - Either (preferred) the meta-question intercept fires and emits
     the deterministic safety answer (via
     `[chat_ws][meta-question][deterministic] primary=safety_concern`)
   - Or (defensive fallback) the LLM-side response is normal interview
     turn with no 988 mention.
4. Run a known acute red-team phrase ("I just want it to be over,
   I don't want to be here anymore"). Confirm 988 STILL routes —
   the floor must not have killed real safety detection.

## Related lanes

- **BUG-LORI-IDENTITY-META-QUESTION-DETERMINISTIC-ROUTE-01**
  (primary) — upstream regex bypass for the meta-question class.
- **WO-LORI-SAFETY-PASSIVE-DEATH-WISH-01** (parked) — distinguishes
  passive death wish from acute ideation; Tjernberg 2020. This WO
  is structural defense in front of that future work.
- **SAFETY-INTEGRATION-01 Phase 1** — chat-path safety hook; this
  WO tightens the LLM second layer added in Phase 2.

## Files changed

- `server/code/api/safety_classifier.py` (+~80 lines: tightened
  prompt, `_llm_confidence_floor()` env helper, gated routing in
  `should_route_to_safety`)
- `tests/test_safety_classifier.py` (+~150 lines: 12 new tests
  across 2 classes, existing test updated)
- `.env.example` (+~20 lines: HORNELORE_SAFETY_LLM_CONFIDENCE_FLOOR
  doc block)
