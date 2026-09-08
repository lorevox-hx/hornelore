# WO-QB-EXTRACT-EVAL-01 — Scoring Rubric

## Field Match Scoring (per expected field)

| Score | Status    | Criteria                                                       |
|-------|-----------|----------------------------------------------------------------|
| 1.0   | Exact     | Normalized expected == normalized actual                       |
| 0.9   | Near      | All expected tokens appear in actual                           |
| 0.8   | Contained | Expected is substring of actual, or actual is substring        |
| 0.5-0.8 | Partial | ≥50% token overlap between expected and actual                |
| 0.0   | Missing   | Field not extracted at all                                     |
| 0.0   | Wrong     | Extracted value has no meaningful overlap with expected         |

### Normalization

Before comparison, both values are:

1. Lowercased
2. Leading/trailing whitespace stripped
3. Internal whitespace collapsed to single spaces

### Date Handling

Dates are compared as strings after normalization. "1962-12-24" matches
"1962-12-24" exactly. "December 24, 1962" would get partial credit via
token overlap. The extraction pipeline is expected to normalize dates to
YYYY-MM-DD format when possible.

### Name Equivalence

"Pete" and "Peter" are treated as partial matches via token overlap.
The scorer does not maintain a nickname→formal-name dictionary. Cases
where nickname equivalence matters note this in `scoringNotes`.

## Forbidden Field Violations

Each forbidden field that appears in the extraction output deducts 0.2
from the overall case score. These test the guard stack:

- **Subject guard**: narrator mentions their own DOB in a parental context
  → extractor must not re-extract `personal.dateOfBirth`
- **Birth-context filter**: early childhood question mentions school
  → extractor must not extract `education.schooling` from a Phase 1 reply
- **Overreach**: narrator mentions spouse in passing while answering about
  career → extractor must not extract `family.spouse.firstName`

## Case-Level Pass/Fail

A case **passes** when:

1. Overall score ≥ 0.7 (average of all field match scores minus penalties)
2. Zero forbidden field violations

## currentExtractorExpected Flag

Each case carries a boolean `currentExtractorExpected`:

- **true**: the current extraction pipeline (as of this WO) should handle
  this case correctly. Failure of a `true` case is a **regression**.
- **false**: this case tests a known architectural gap (e.g., compound
  entity grouping for CLAIMS-01). Failure is expected and documented.
  Passing is a positive surprise.

## Behavior Categories

| Category               | What's being tested                                      |
|------------------------|----------------------------------------------------------|
| `extract_single`       | One narrator fact → one or two extracted fields           |
| `extract_multiple`     | One reply → multiple fields, possibly across entity groups|
| `clarify_before_write` | Reply is ambiguous — extractor should low-confidence or skip|
| `forbidden_overreach`  | Extractor must NOT extract certain fields from context    |
| `correction_overwrite` | Narrator corrects earlier data — new value must override  |

## Report Interpretation

The eval report groups results by:

1. **Overall** — pass rate and average score across all 30 cases
2. **By behavior** — which case types the extractor handles well/poorly
3. **By narrator** — whether extraction quality varies by narrator template richness
4. **Expected vs actual** — regressions (expected=true but failed) vs known gaps
5. **Failure categories** — what kinds of failures are occurring
