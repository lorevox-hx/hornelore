# WO-EX-FIELDPATH-NORMALIZE-01 — Field-Path Normalizer (Confusion-Table-Driven)

## Goal

Reduce `field_path_mismatch` failures in the single-pass extraction baseline by building a confusion table from observed LLM misroutes, then applying conservative, evidence-based remaps. No architecture change. No new LLM calls. Pure post-processing on existing single-pass output.

## Current State

- Single-pass baseline: **32/62 (51.6%, avg 0.590)**
- Failure breakdown: schema_gap 16-17, **field_path_mismatch 9-11**, hallucination 10-11
- Two-pass v1: shelved (regressed to 16/62)
- Target: resolve 6-8 of the 11 field_path_mismatch cases → **38-40/62**

## Acceptance Gates

| Gate | Criterion |
|------|-----------|
| **Net gain** | Pass rate ≥ 36/62 (net +4 over 32/62 baseline) |
| **No regressions** | Zero cases that currently pass (32) may flip to fail |
| **Wobble** | Two consecutive runs within ±2 of each other |
| **Method** | All changes are prompt improvements, aliases, or rerouters — no new LLM calls |

## Stop Conditions

- If confusion table shows fewer than 4 actionable misroutes → stop, not enough signal
- If any rerouter fires on a case that currently passes and breaks it → revert that rerouter
- If net gain after implementation is < +2 → do not ship, move to constrained decoding

## Non-Goals

- No new extraction architecture (two-pass stays shelved)
- No constrained decoding infrastructure (that's WO-EX-CONSTRAINED-FIELDPATH-01)
- No new eval cases (freeze at 62)
- No changes to downstream validators (claims, birth-context, field-value sanity)

---

## Phase 1: Build the Confusion Table

### Step 1A — Capture actual LLM paths on failing cases

Run the 62-case eval with a temporary logging patch that records, for every extracted item:

```
case_id | actual_fieldPath | actual_value | expected_fieldPath | expected_value | section | match_type
```

Where `match_type` is one of:
- `exact` — correct path, correct value
- `value_match_wrong_path` — value matches an expected value but under wrong fieldPath
- `no_match` — neither path nor value matches any expected field
- `extra` — extracted item has no corresponding expected field

Focus on `value_match_wrong_path` rows. These are the pure misroutes.

### Step 1B — Build confusion pairs

From the `value_match_wrong_path` rows, build a table:

```
actual_path → expected_path | count | section(s) | cue_words
```

Example (predicted from case analysis):

| Actual Path (LLM chose) | Expected Path | Count | Sections | Cue Words |
|---|---|---|---|---|
| education.careerProgression | education.earlyCareer | 2-3 | professional_genesis, career_progression_vs_early | "started out", "first job", "right out of school" |
| personal.placeOfBirth | residence.place | 1-2 | birthplace_vs_residence, first_home | "moved to", "grew up in", "lived in" |
| parents.occupation | community.organization | 1 | community_belonging | "worked on", "Garrison Dam" |
| laterYears.significantEvent | health.majorCondition | 1 | health_and_body | "knees", "gave out" |
| laterYears.significantEvent | health.lifestyleChange | 1 | health_and_body | "slow down", "had to" |
| parents.notableLifeEvents | military.significantEvent | 2 | family_stories_and_lore | "served", "Civil War", "infantry" |
| education.schooling | community.organization | 1 | community_belonging | "College of Mary", "founder" |
| family.children.placeOfBirth | residence.place | 1 | first_home | "went to Germany", "working" |

### Step 1C — Validate confusion pairs

For each pair, check:
- Does the remap make sense semantically? (not just statistically)
- Would the remap break any currently-passing case?
- Is the cue-word pattern reliable enough to avoid false positives?

Only proceed with pairs that have clear cue-word signals AND no regression risk.

---

## Phase 2: Implement Fixes (Three Layers)

### Layer A — Prompt Example Expansion

Add 3-4 new examples to the single-pass extraction prompt demonstrating the newer field families that the LLM doesn't reach for:

**Example 1 — Military (family member):**
```
Answer: "My grandfather served in the Army during World War II. He was stationed in France."
Extract: [
  {"fieldPath": "military.branch", "value": "Army", "confidence": 0.9},
  {"fieldPath": "military.significantEvent", "value": "Served in World War II", "confidence": 0.9},
  {"fieldPath": "military.deploymentLocation", "value": "France", "confidence": 0.9}
]
```

**Example 2 — Community:**
```
Answer: "My father worked on the Garrison Dam as a foreman."
Extract: [
  {"fieldPath": "community.organization", "value": "Garrison Dam project", "confidence": 0.9},
  {"fieldPath": "community.role", "value": "Foreman", "confidence": 0.9}
]
```

**Example 3 — Residence vs birthplace:**
```
Answer: "I was born in Fargo but we moved to West Fargo when I was five."
Extract: [
  {"fieldPath": "personal.placeOfBirth", "value": "Fargo", "confidence": 0.9},
  {"fieldPath": "residence.place", "value": "West Fargo", "confidence": 0.9}
]
```

**Example 4 — Early career vs career progression:**
```
Answer: "I started as a welder's helper, then worked my way up to foreman over thirty years."
Extract: [
  {"fieldPath": "education.earlyCareer", "value": "welder's helper", "confidence": 0.9},
  {"fieldPath": "education.careerProgression", "value": "foreman", "confidence": 0.9}
]
```

### Layer B — Field Label Sharpening

Update EXTRACTABLE_FIELDS labels to reduce ambiguity:

| Field | Current Label | Sharpened Label |
|---|---|---|
| education.earlyCareer | "First job or early career" | "First job or career start (before age 25)" |
| education.careerProgression | "Career progression and major changes" | "Later career changes, promotions, and long-term roles" |
| community.organization | "Community organization or group" | "Community organization, civic project, or public works" |
| health.lifestyleChange | "Significant lifestyle change for health" | "Lifestyle change forced by health (slowing down, quitting, adapting)" |

### Layer C — Section-Aware Rerouters

Add 2-3 new rerouters to `_apply_semantic_reroute()` following the existing pattern (triple-agreement: section + path + lexical cue):

**Rerouter 1 — Residence detector:**
```
IF section in (birthplace_vs_residence, first_home, moving_and_migration, settling_down)
AND fieldPath == "personal.placeOfBirth"
AND answer contains ("moved to", "grew up in", "lived in", "settled in", "that's where")
AND value != placeOfBirth already extracted
THEN reroute to residence.place
```

**Rerouter 2 — Career stage splitter:**
```
IF section in (professional_genesis, career_progression_vs_early, the_launch)
AND fieldPath == "education.careerProgression"
AND answer contains ("started out", "first job", "right out of school", "began as", "started as")
AND value describes an entry-level role (not a promotion)
THEN reroute to education.earlyCareer
```

**Rerouter 3 — Military family history:**
```
IF section in (family_stories_and_lore, grandparents_roots)
AND fieldPath in (parents.notableLifeEvents, earlyMemories.significantEvent, laterYears.significantEvent)
AND answer contains ("served", "stationed", "infantry", "regiment", "Civil War", "World War", "Army", "Navy")
THEN reroute to military.significantEvent
```

### Layer D — Targeted Alias Additions

Add aliases for observed LLM-invented paths not yet in the alias table:

```python
# Health routing — LLM uses laterYears.* for health topics
"laterYears.healthChange": "health.lifestyleChange",
"laterYears.physicalChange": "health.lifestyleChange",
"laterYears.condition": "health.majorCondition",

# Community routing — LLM confuses with education/parents
"education.workProject": "community.organization",
"parents.workProject": "community.organization",

# Travel routing — LLM doesn't know travel.* exists
"residence.travel": "travel.destination",
"laterYears.travel": "travel.significantTrip",
```

Note: aliases in Layer D are only added if the confusion table from Phase 1 confirms the actual LLM outputs these paths. Do not add speculative aliases.

---

## Phase 3: Eval

### Step 3A — Run 62-case eval twice (wobble check)

```bash
python scripts/run_question_bank_extraction_eval.py --mode live 2>&1 | tee /tmp/fieldpath_norm_r1.txt
python scripts/run_question_bank_extraction_eval.py --mode live 2>&1 | tee /tmp/fieldpath_norm_r2.txt
```

### Step 3B — Compare against baseline

| Metric | Baseline | Post-Normalize | Delta |
|---|---|---|---|
| Pass rate | 32/62 | ? | ? |
| Avg score | 0.590 | ? | ? |
| field_path_mismatch | 9-11 | ? | ? |
| schema_gap | 16-17 | ? | ? |
| hallucination | 10-11 | ? | ? |

### Step 3C — Regression check

Verify all 32 currently-passing cases still pass. List any that flipped.

---

## Exact File Scope

| File | Change |
|---|---|
| `server/code/api/routers/extract.py` | Layer B: update EXTRACTABLE_FIELDS labels. Layer C: add 2-3 rerouters to `_apply_semantic_reroute()`. Layer D: add aliases to `_FIELD_ALIASES`. |
| Extraction prompt (wherever the single-pass prompt is built) | Layer A: add 3-4 new examples covering military, community, residence, career split. |
| `scripts/run_question_bank_extraction_eval.py` | No changes. |
| `data/qa/question_bank_extraction_cases.json` | No changes (frozen at 62). |
| `HANDOFF.md` | Update with results. |

## Hard Rules

- Every rerouter must use triple-agreement (section + path + lexical cue). No single-signal reroutes.
- Every alias must be confirmed by the confusion table, not guessed.
- The confusion table logging is temporary instrumentation — remove after Phase 1.
- No new feature flags. Changes are additive improvements to the existing single-pass pipeline.
- Run eval twice. Both runs must meet the acceptance gates.

## Sequence After This WO

```
WO-EX-FIELDPATH-NORMALIZE-01 (this) → eval → WO-EX-CONSTRAINED-FIELDPATH-01 (enum decoding) → expanded eval suite
```
