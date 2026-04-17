# WO-QB-EXTRACT-EVAL-01 — Extraction Evaluation Plan

## Purpose

Validate that Hornelore's extraction pipeline (`POST /api/extract-fields`)
correctly decomposes narrator answers into structured field projections,
using real question bank prompts as input and real narrator template data
as ground truth.

## Philosophy

This evaluation is **entity-centric, not triplet-centric**. We care about
identity coherence (does "Vincent Edward" stay grouped as one child entity?)
more than isolated field-value pairs. The question bank provides the prompt
context; the narrator templates provide the truth source. No synthetic test
data — every case is grounded in the Horne family's actual biographical facts.

## Fixture Design

30 cases across three narrators (10 each):

- **Christopher Todd Horne** — youngest child, most structured template
- **Kent James Horne** — patriarch, sparse template in some areas
- **Janice Josephine Horne** — richest narrative content, multiple schools

### Case Distribution

| Category               | Count | Tests                                           |
|------------------------|-------|-------------------------------------------------|
| Clean single-fact      | 10    | One fact → one or two fields extracted           |
| Compound multi-fact    | 8     | One reply → 3+ entities with grouped fields      |
| Ambiguity / clarify    | 4     | Reply is too vague for confident extraction       |
| Forbidden overreach    | 4     | Extractor must NOT extract certain fields         |
| Correction overwrite   | 4     | Narrator corrects a previously stated fact         |

### Topic Coverage

Childhood origins, school entry, autonomy milestones, civic entry at 18,
graduation/launch, first job, partnership/marriage, children, off-ramp/
retirement, legacy/reflection.

## Dual Runner Modes

### Offline Mode (`--mode offline`)

- Imports extract.py logic directly
- Uses `mockLlmOutput` from each case as the extraction result
- Tests: scoring harness, fixture quality, guard-stack behavior
- No LLM, no server, no network required
- Exit code 0 if all `currentExtractorExpected=true` cases pass

### Live Mode (`--mode live`)

- POSTs to `http://localhost:14501/api/extract-fields`
- Real LLM extracts from real narrator replies
- Tests: end-to-end extraction quality, LLM output shape, confidence calibration
- Requires Hornelore server running with model loaded
- Maps narrator IDs to real person_id UUIDs from the database

## Scoring

Each case is scored on:

1. **Field accuracy** — does the extracted value match the expected value?
   - Exact match: 1.0
   - Substring containment: 0.8
   - Token overlap ≥50%: 0.5-0.8
   - No match: 0.0

2. **Forbidden field violations** — each violation deducts 0.2 from overall score

3. **Pass threshold** — overall score ≥ 0.7 AND zero forbidden violations

## Failure Categories

| Category              | Meaning                                                |
|-----------------------|--------------------------------------------------------|
| `schema_gap`          | Field exists in template but no EXTRACTABLE_FIELDS path |
| `guard_false_positive`| Guard stack drops a valid extraction                    |
| `llm_output_shape`    | LLM returns unparseable JSON                           |
| `llm_hallucination`   | LLM invents facts not in the narrator reply             |
| `field_path_mismatch` | Correct value under wrong fieldPath                     |
| `missing_alias`       | LLM uses alias not in FIELD_ALIASES                     |

## Running

```bash
# Offline (no server needed)
python scripts/run_question_bank_extraction_eval.py --mode offline

# Live (server must be running)
python scripts/run_question_bank_extraction_eval.py --mode live --api http://localhost:14501
```

## Output

Report JSON written to `docs/reports/question_bank_extraction_eval_report.json`.
Summary table printed to stdout including pass/fail counts, per-narrator
breakdown, per-behavior-type breakdown, and failure category distribution.

## Success Criteria

- All `currentExtractorExpected=true` cases pass in offline mode
- Known gaps (`currentExtractorExpected=false`) are documented, not hidden
- Live mode pass rate is baseline for future WO improvements (CLAIMS-01, etc.)
