# WO-QB-EXTRACT-EVAL-01 — Extraction Evaluation Report

## Run Metadata

- **Date**: {date}
- **Mode**: {offline | live}
- **Cases**: 30 (10 per narrator)
- **API endpoint**: {api_url or N/A}

## Summary

| Metric              | Value    |
|---------------------|----------|
| Total cases         | {total}  |
| Passed              | {passed} |
| Failed              | {failed} |
| Pass rate           | {rate}%  |
| Avg overall score   | {avg}    |

## By Behavior Type

| Behavior               | Total | Passed | Failed |
|------------------------|-------|--------|--------|
| extract_single         |       |        |        |
| extract_multiple       |       |        |        |
| clarify_before_write   |       |        |        |
| forbidden_overreach    |       |        |        |
| correction_overwrite   |       |        |        |

## By Narrator

| Narrator                    | Total | Passed | Avg Score |
|-----------------------------|-------|--------|-----------|
| christopher-todd-horne      |       |        |           |
| kent-james-horne            |       |        |           |
| janice-josephine-horne      |       |        |           |

## Expected Extractor Results

| Category                          | Total | Actually Passed |
|-----------------------------------|-------|-----------------|
| Should pass (expected=true)       |       |                 |
| Known gaps (expected=false)       |       |                 |

## Failure Categories

| Category              | Count | Notes                                    |
|-----------------------|-------|------------------------------------------|
| schema_gap            |       |                                          |
| guard_false_positive  |       |                                          |
| llm_output_shape      |       |                                          |
| llm_hallucination     |       |                                          |
| field_path_mismatch   |       |                                          |
| missing_alias         |       |                                          |

## Failed Cases Detail

### Regressions (expected=true but failed)

| Case ID  | Narrator | Score | Behavior | Failure Categories |
|----------|----------|-------|----------|--------------------|
|          |          |       |          |                    |

### Known Gaps (expected=false, failure expected)

| Case ID  | Narrator | Score | Behavior | Notes              |
|----------|----------|-------|----------|--------------------|
|          |          |       |          |                    |

## Observations

{analyst notes — what patterns emerge, what the next WO should target}

## Recommendations

{specific fixes or WO follow-ups based on failure distribution}
