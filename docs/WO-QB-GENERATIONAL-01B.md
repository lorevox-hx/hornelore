# WO-QB-GENERATIONAL-01B — Extraction Prompt Tuning + Runtime Wiring

**Status:** Ready to implement  
**Depends on:** WO-QB-GENERATIONAL-01 (content, done), WO-EX-GUARD-REFUSAL-01 (done)  
**Blocked by:** Nothing — can start immediately  
**Priority position:** After INTENT-01 in master sequence, but can be parallelized with it  

---

## Problem

WO-QB-GENERATIONAL-01 shipped the content: 4 decade packs, `present_life_realities` subtopic, 5 new extractable fields, and a 14-case eval pack. The eval baseline is 2/14 — both refusal-guard cases pass, but 0/12 extraction cases produce correct output. The refusal guard is solid (0 must_not_write violations). The gap is entirely in two areas:

1. **The extraction prompt has zero examples for generational answer styles.** The LLM has never seen a touchstone response ("We were in Bismarck then. Dad had the black-and-white TV on...") mapped to `laterYears.significantEvent` or `cultural.touchstoneMemory`. Without few-shot examples, it either emits nothing or routes to the wrong field.

2. **The question composer doesn't know about generational overlays.** `pick_next_question()` in `phase_aware_composer.py` walks `phases → sub_topics → questions` in JSON order. The `generational_overlays` block sits outside the phase tree and is never reached. The content exists but Lori never asks it.

This WO fixes both. It does NOT change the eval cases — those are correct as written.

---

## Non-goals

- **Do not touch the refusal guard.** It works. 0 violations. Leave it alone.
- **Do not restructure the eval cases.** The field paths in cases 201-214 are intentional. Cases 201-208 target existing fields (`laterYears.significantEvent`, `hobbies.hobbies`, `residence.place`) because those ARE the correct extraction targets for that content. `currentExtractorExpected: false` means we expect them to fail until this WO lands.
- **Do not add new extractable fields.** The 5 fields from 01 are sufficient. This WO teaches the extractor to USE them.
- **Do not wire the chronology accordion highlight.** That's a UI-only enhancement for a later WO.

---

## Part 1 — Extraction Prompt Examples

### What

Add 6 few-shot examples to `_build_extraction_prompt()` in `extract.py` covering the answer styles the generational eval pack tests. These go after the existing examples (health, community, pets, travel) and before the NEGATION RULE block.

### Why

The current prompt has 12 few-shot examples. None of them show:
- A "where were you when" touchstone response
- A late-life medication disclosure
- A memory/cognitive self-report
- A "stories I want told" response
- A frustration/personal challenge in elder voice

The LLM is pattern-matching against examples. No examples = no extraction.

### Examples to add

**Example 1 — Touchstone memory (moon landing style)**
```
Narrator says: "We were watching on a little black-and-white set when they landed on the moon. The whole family was in the living room."
Output:
[{"fieldPath":"laterYears.significantEvent","value":"watched the moon landing on TV with the whole family","confidence":0.9},
 {"fieldPath":"cultural.touchstoneMemory","value":"moon landing — watched on a black-and-white TV with the whole family in the living room","confidence":0.9}]
```
Routing note: Touchstone "where-were-you" memories get BOTH `laterYears.significantEvent` (the fact) AND `cultural.touchstoneMemory` (the vivid memory with sensory detail). If the narrator only gives a bare fact ("yeah, I saw it on TV"), use only `laterYears.significantEvent`.

**Example 2 — Touchstone with place + family context (gas lines style)**
```
Narrator says: "In Bismarck we sat in line with the engine off hoping the gas held out. My wife packed sandwiches."
Output:
[{"fieldPath":"residence.place","value":"Bismarck","confidence":0.9},
 {"fieldPath":"laterYears.significantEvent","value":"waited in gas lines during the 1970s energy crisis","confidence":0.8}]
```
Routing note: The wife and sandwiches are scene-setting, not extractable spouse facts. Do NOT create `family.spouse.relation` from a passing mention in a historical-event answer.

**Example 3 — Current medications**
```
Narrator says: "I take blood pressure medicine every morning, and something for arthritis when my hands flare up."
Output:
[{"fieldPath":"health.currentMedications","value":"blood pressure medicine daily, arthritis medication as needed","confidence":0.9},
 {"fieldPath":"health.majorCondition","value":"high blood pressure","confidence":0.8},
 {"fieldPath":"health.majorCondition","value":"arthritis","confidence":0.8}]
```
Routing note: Medications → `health.currentMedications`. The conditions those medications treat → `health.majorCondition`. Both are valid from the same answer.

**Example 4 — Memory/cognitive self-report**
```
Narrator says: "Names take longer than they used to, but the old stories are still there. It's the little daily things that slip first."
Output:
[{"fieldPath":"health.cognitiveChange","value":"names are slower to recall, small daily details slip first, but long-term memories remain","confidence":0.8}]
```
Routing note: Self-reported memory change → `health.cognitiveChange`. Do NOT write `health.majorCondition` — the narrator is describing normal aging, not a diagnosis.

**Example 5 — Frustrations / personal challenge in elder voice**
```
Narrator says: "Everything takes longer now, and younger people assume older means helpless. That gets under my skin."
Output:
[{"fieldPath":"hobbies.personalChallenges","value":"frustration with slowing down and being treated as helpless","confidence":0.9}]
```
Routing note: Late-life frustrations and complaints about aging → `hobbies.personalChallenges`. Do NOT invent field paths like `laterYears.frustrations` or `aging.complaints`.

**Example 6 — Desired stories / story priorities**
```
Narrator says: "I'd want my family to hear about my dad dying in '67, the years we built a life in Germany, and how their mother and I got started with almost nothing."
Output:
[{"fieldPath":"laterYears.desiredStory","value":"father's death in 1967","confidence":0.9},
 {"fieldPath":"laterYears.desiredStory","value":"years building a life in Germany","confidence":0.9},
 {"fieldPath":"laterYears.desiredStory","value":"early married life starting with almost nothing","confidence":0.9}]
```
Routing note: When a narrator lists stories they want told, each story is a separate `laterYears.desiredStory` item (repeatable field). Do NOT collapse them into one value. Do NOT extract the mentioned places/dates as separate `residence.*` or `parents.*` items — the narrator is listing priorities, not narrating those events.

### Placement

After the existing travel example ("We took a trip to Europe in 1985...") and before the "NEGATION RULE:" block. Group them under a comment:

```
"GENERATIONAL & LATE-LIFE EXAMPLES — touchstones, medications, memory, frustrations, desired stories:\n"
```

### File target

`server/code/api/routers/extract.py` — inside `_build_extraction_prompt()`, lines ~456-461 area.

---

## Part 2 — Runtime Question Composer Integration

### What

Extend `pick_next_question()` in `phase_aware_composer.py` to interleave generational overlay questions with the existing phase-based biographical questions.

### Design

The generational overlays sit in `question_bank.json` at `generational_overlays.decade_packs`. Each pack has a `birth_decade` range and a list of questions with `event_tags`, `phase_bias`, and `extract_priority`.

The composer integration works like this:

1. **Decade selection.** From the narrator's DOB, compute birth decade (e.g., 1948 → "1940s"). Load the matching decade pack from `generational_overlays.decade_packs`.

2. **Interleave ratio.** After Phase 1 identity is established (narrator has answered ≥5 questions), inject 1 generational question per 4 biographical questions. This is the 1:4-5 ratio from the parent spec.

3. **Phase bias filtering.** Each generational question has a `phase_bias` array (e.g., `["developmental_foundations", "early_adulthood"]`). Only offer a question when the narrator is currently in a matching phase OR has passed through it (for retrospective questions).

4. **Suppression rules.** Each decade pack has `suppression_rules` — e.g., "if narrator declines a Vietnam question, suppress all military-tagged follow-ups for this session." Wire these to the existing `asked_keys` tracking.

5. **`present_life_realities` gating.** The `late_life_only: true` flag means these questions are only offered when: (a) the narrator is in `legacy_reflection` phase, AND (b) at least 2 other legacy_reflection sub-topics have been asked (trust is established). This prevents cold-opening with "do you take medications?"

6. **Return shape.** Generational questions use the same return dict as biographical questions, with `_meta.source: "generational_overlay"` instead of `"question_bank"` so the caller can log the distinction.

### Implementation approach

Add a new function `_pick_generational_question()` that:
- Takes `dob`, `asked_keys`, `current_phase`, `question_count` (total asked so far)
- Returns a question dict or None
- Checks the interleave counter (`question_count % 5 == 4` → try generational)
- Filters by decade pack, phase bias, suppression
- Returns None if no eligible question (caller falls through to biographical)

Modify `pick_next_question()` to call `_pick_generational_question()` first when the interleave counter fires. If it returns None, fall through to the existing biographical picker.

### `present_life_realities` integration

This subtopic is already inside the `legacy_reflection` phase tree in `question_bank.json`, so the existing picker CAN reach it. But the `late_life_only: true` flag needs a gate:

Add to the sub-topic loop in `pick_next_question()`:
```python
if sub_data.get("late_life_only"):
    # Count how many other legacy_reflection sub-topics have been asked
    legacy_asked = sum(1 for k in asked if k.startswith("legacy_reflection:") 
                       and not k.startswith("legacy_reflection:present_life_realities:"))
    if legacy_asked < 2:
        continue  # Not enough trust yet
```

### File targets

- `server/code/api/phase_aware_composer.py` — new `_pick_generational_question()` + modify `pick_next_question()`
- `server/code/api/routers/interview.py` — pass `question_count` to composer if not already available

### Feature flag

Use the existing `HORNELORE_PHASE_AWARE_QUESTIONS` flag. Generational interleaving only fires when this flag is ON. When OFF, behavior is identical to pre-WO.

---

## Part 3 — Semantic Rerouter Additions

### What

Add 2 high-precision rerouter rules to `_apply_semantic_rerouter()` for the new field patterns.

### Rules

1. **Touchstone story → cultural.touchstoneMemory.** If the answer mentions a known historical event (moon landing, Vietnam, gas crisis, Challenger, 9/11, COVID) AND the LLM routed to `laterYears.significantEvent`, ADD a duplicate item routed to `cultural.touchstoneMemory` with the same value. Don't remove the original — both fields are valid.

2. **"I want to tell" / "stories I'd pick" → laterYears.desiredStory.** If the answer contains priority-listing language ("I'd want my family to hear", "if I only had time for", "the stories I'd pick") AND the LLM routed to `additionalNotes.unfinishedDreams` or `laterYears.lifeLessons`, reroute to `laterYears.desiredStory`.

### Detection patterns

Rule 1 event keywords (case-insensitive): `moon landing`, `apollo`, `vietnam`, `draft`, `gas lines`, `energy crisis`, `challenger`, `9/11`, `september 11`, `covid`, `pandemic`, `berlin wall`, `kennedy`, `jfk`, `watergate`, `sputnik`, `artemis`

Rule 2 priority phrases: `want.*family to hear`, `only had time for`, `stories I'd`, `want on the record`, `want.*written down`, `want.*told`

### File target

`server/code/api/routers/extract.py` — inside `_apply_semantic_rerouter()`

---

## Acceptance Criteria

### Eval targets

Run the generational eval pack (14 cases):
```bash
python scripts/run_question_bank_extraction_eval.py --mode live --api http://localhost:8000 --cases data/qa/question_bank_generational_cases.json
```

**Part 1 acceptance (extraction prompt):**
- Cases 201-208 (touchstone overlay): ≥4/8 pass (up from 0/8). These are `currentExtractorExpected: false` so any improvement is signal.
- Cases 209, 211, 213, 214 (contract): ≥3/4 pass (up from 0/4). These target existing fields and should be reachable with prompt examples.
- Cases 210, 212 (refusal): Stay at 2/2. Guard must not regress.
- **Overall: ≥9/14** (up from 2/14).
- **must_not_write violations: 0** (must stay at 0).

**Part 2 acceptance (runtime):**
- With `HORNELORE_PHASE_AWARE_QUESTIONS=1`, start a narrator session with a Boomer-aged narrator.
- After ~5 biographical questions, confirm a generational overlay question appears (check network tab for `_meta.source: "generational_overlay"`).
- Confirm `present_life_realities` questions do NOT appear until ≥2 other legacy_reflection sub-topics have been asked.
- Confirm that with the flag OFF, no generational overlay questions appear.

**Master suite regression:**
```bash
python scripts/run_question_bank_extraction_eval.py --mode live --api http://localhost:8000
```
- Full suite (104 cases): ≥54/104 (must not regress from 55/104 ±1 LLM variance).
- Contract subset: ≥32/62 v2 (must not regress from 33/62 ±1).
- must_not_write violations: 0.

---

## Implementation Order

1. **Part 1 — Extraction prompt examples** (extract.py). Smallest change, biggest eval impact. Ship first, re-run generational pack to measure.
2. **Part 3 — Rerouter additions** (extract.py). Small change, helps Part 1 cases that route to wrong-but-close fields.
3. **Part 2 — Runtime composer** (phase_aware_composer.py + interview.py). Larger change, needs live testing. Ship after extraction is proven.

Each part can be committed and tested independently.

---

## Risk

- **Prompt bloat.** 6 new examples add ~800 tokens to the extraction prompt. Current prompt is ~2400 tokens. Total ~3200 is still well within the 8K context window for Llama-3.1-8B, but watch for token starvation on compound answers where `max_new_tokens` is already tight. If compound detection fires AND the prompt is longer, the 384-token cap may need a bump to 448.
- **Rerouter false positives.** Rule 1 fires on event keywords, which could match in non-touchstone contexts (e.g., narrator says "my son was born during COVID" — that's a birth event, not a touchstone). Mitigate by requiring BOTH the event keyword AND `laterYears.significantEvent` routing — if the LLM already classified it correctly as a non-touchstone, the rerouter doesn't fire.
- **Interleave cadence.** 1:4 ratio is a guess. If narrators find the touchstone questions jarring mid-flow, the ratio may need to soften to 1:6. This is a content-feel issue, not a code issue — adjust the modulo constant.

---

*WO-QB-GENERATIONAL-01B — drafted 2026-04-18*
