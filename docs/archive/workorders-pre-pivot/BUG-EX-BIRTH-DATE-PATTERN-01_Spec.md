# BUG-EX-BIRTH-DATE-PATTERN-01 — Deterministic DOB capture for canonical birth-sentence patterns

**Status:** SPEC — scoped, not yet implemented
**Date:** 2026-05-02
**Lane:** Extractor cleanup. Parallel to BINDING-01 / SPANTAG. Touches the post-LLM emit phase only — no Pass 2 prompt change, no LLM round-trip.
**Sequencing:** Opens after BUG-EX-SPOUSE-ALIAS-01 case-bank normalize lands. Independent of BINDING-01 second iteration.
**Blocks:** Nothing.
**Lights up:** case_049 (Janice DOB miss on `"I was born in Spokane, Washington, on August 30th, 1939."`) and the broader class of "narrator clearly stated DOB but LLM stochastically omitted it" misses.

---

## What this WO is NOT

```
- NOT a date-format normalizer fix.
  The R4-H normalizer is fine. api.log proof:
    2026-05-02 16:50:16  [extract][R4-H] normalise personal.dateOfBirth:
                         'August 30, 1939' → '1939-08-30'
    2026-05-02 19:40:01  [extract][R4-H] normalise personal.dateOfBirth:
                         'August 30, 1939' → '1939-08-30'
    2026-04-29 10:00:56  (same pattern, same case, same conversion)
    2026-04-29 21:50:44  (same)
  Multiple successful conversions of the EXACT format on the EXACT
  case. R4-H works perfectly when the LLM emits personal.dateOfBirth.

- NOT a Pass 2 prompt change.
  We do not iterate the LLM prompt to "remember to extract DOB."
  Prompt-side fixes for recall failures are stochastic by nature
  (cf. BUG-LORI-REFLECTION-01 Patch B locked principle).
```

## What this WO IS

A deterministic post-LLM regex fallback that fires AFTER the LLM
emit phase, scans the narrator's answer for canonical birth-sentence
templates, and emits any missing fields under method=`birth_pattern_fallback`.

```
The LLM is variable on whether it surfaces DOB in any given sample.
The narrator's words are not.
Extract the deterministic signal deterministically.
```

## Why now (case_049 evidence)

```
Narrator answer:
  "I was born in Spokane, Washington, on August 30th, 1939.
   My dad Pete worked at an aluminum factory there."

This is the cleanest possible birth sentence. Place + DOB explicit,
canonical preposition templates, comma-delimited, no ambiguity.

In one master eval (this run), the LLM emitted:
  personal.placeOfBirth = 'Spokane, Washington'  ✓
  parents.firstName     = 'Pete'
  parents.occupation    = 'aluminum factory worker'
  ✗ NO personal.dateOfBirth

In other runs of the SAME case (api.log), the LLM emitted DOB cleanly.
This is pure sampling stochasticity on a deterministic input.
The deterministic regex layer makes the stochasticity irrelevant.
```

## Scope (Phase 1 — birth sentence)

Three regex patterns, ordered most-specific to least-specific:

```
Pattern A: "born in PLACE, on DATE"
  r"\bborn\s+in\s+([A-Z][\w\-' ,]+?)\s*,?\s+on\s+
    ((?:January|February|March|April|May|June|July|August|
        September|October|November|December)
     \s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})"

Pattern B: "born on DATE in PLACE"
  r"\bborn\s+on\s+
    ((?:January|February|March|April|May|June|July|August|
        September|October|November|December)
     \s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})
    \s+in\s+([A-Z][\w\-' ,]+)"

Pattern C: "born DATE" (date-only, place-optional)
  r"\bborn\s+
    ((?:January|February|March|April|May|June|July|August|
        September|October|November|December)
     \s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})"

Plus minimal numeric-format support:
Pattern D: "born MM/DD/YYYY" or "born YYYY-MM-DD"
  (covers digital-form narrator inputs)
```

All patterns capture into `personal.dateOfBirth` via R4-H normalize
(reuses the existing normalizer — DO NOT add a parallel normalizer).
Place capture (Patterns A and B) is already covered by existing
extraction; the regex SHOULD NOT emit `personal.placeOfBirth` from
this fallback — placeOfBirth has its own extraction path that the
LLM consistently hits.

## Integration point

Two viable spots, in priority order:

```
Option 1 (preferred): post-LLM, pre-validator
  Location: extract.py inside the main extraction loop, after
            `_parse_llm_json` returns and before `_validate_item`
            iterates.
  Logic:    if `personal.dateOfBirth` is NOT present in the parsed
            items AND the narrator answer matches one of the birth
            patterns, emit a synthetic item with
              method='birth_pattern_fallback'
              confidence=0.9 (deterministic, regex-grounded)
            Then proceed through the existing validate/normalize
            pipeline.

Option 2 (fallback): in the `[silent-root]` fallback branch
  Only fires when the LLM returned ZERO items at all.
  Less surface — wouldn't catch the "LLM returned 4 items but
  forgot DOB" case (which is exactly case_049's failure mode).
  Listed here for completeness; Option 1 is the right choice.
```

## Locked design rules

```
1. Narrator-text-only.
   The fallback reads `req.answer`. It does NOT read prior turns,
   does NOT read profile, does NOT consult any LLM.

2. Personal-only.
   The pattern only emits `personal.dateOfBirth` (narrator's own
   DOB). Parent / sibling / child DOB extraction stays in the LLM
   path. Reason: "I was born" is unambiguously narrator-self;
   "My mother was born" / "My sister was born" need subject
   resolution that this fallback deliberately does not do.

3. Suppress-if-already-emitted.
   If `personal.dateOfBirth` is already in the parsed items list,
   the fallback DOES NOT add a duplicate. This is a fallback, not
   a forced override.

4. Log every fire.
   `[extract][birth-pattern-fallback] fired pattern=A value='August 30, 1939' → '1939-08-30'`
   So operators can see when the fallback rescued a DOB.

5. No Pass 2 prompt changes. Period.
```

## Acceptance gates

```
Phase 1  [ ] case_049 passes consistently (3 consecutive eval runs)
         [ ] No new must_not_write violations introduced
         [ ] v3 contract subset stays at 48/72 or improves
         [ ] v2 contract subset stays at 42/72 or improves
         [ ] mnw stays at 2 or improves
         [ ] [extract][birth-pattern-fallback] log marker visible
             in api.log on the case_049 turn
         [ ] Pattern false-positive rate ≤1 case across the 114-case
             eval (i.e., the fallback shouldn't introduce any
             newly-failing case via DOB hallucination)
```

## What this WO does NOT do (deliberate scope wall)

- DOB extraction for parents/siblings/children/spouse/grandparents
  (those need subject resolution; lane = BINDING-01 second iteration)
- Year-only patterns ("born in 1939")
  (deferred to Phase 2 if Phase 1 evidence supports it)
- Date-range or "born around" patterns
  (deferred to dateRange WO; LORI-CONFIRM-01 v1.1 territory)
- Invalid-date detection ("February 30")
  (R4-H already handles malformed dates; we don't duplicate)

## Sequencing relative to other lanes

```
WO-EX-CASE-BANK-FIXUP-01     ← scorer/data side, parallel
BUG-EX-BIRTH-DATE-PATTERN-01 ← THIS (extractor fallback, parallel)
WO-EX-BINDING-01 second iter ← parent/sibling/spouse DOB binding
WO-EX-FIELD-CARDINALITY-01   ← multi-entity splitting
```

Independent rollback per lane. No shared dependencies.

## Cost estimate

- Implementation: ~30 lines (4 regex patterns + integration + log)
- Unit tests: ~10 cases (positive matches + negation guards + cross-narrator subject suppression)
- Master 114 verification: 1 run (~6-7 min on warm stack)
- Total: half a session

## Bumper sticker

```
The R4-H date normalizer is fine.
The LLM is variable on what it chooses to extract.
Variable LLM + deterministic narrator text = deterministic regex layer.
This WO adds the layer.
```
