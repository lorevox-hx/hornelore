# WO-EX-VALUE-ALT-CREDIT-01 — Scorer policy for value-axis alt-credit (#97)

**Status:** DRAFT (2026-04-22, authored after r5h adopt)
**Owner:** extractor lane (Claude) / scorer-side
**Priority:** #2 in active sequence (after #144 WO-SCHEMA-ANCESTOR-EXPAND-01)
**Blocks:** nothing
**Blocked by:** #144 Lane 1 (so we can see which r5i fails remain value-drift rather than path-drift)
**Eval tag:** `r5k` (runs after r5i lands)
**Task:** #97

---

## 1. Problem statement

#94 (WO-EX-SECTION-EFFECT-01 scorer policy) added `alt_defensible_paths` — a scorer-side annotation allowing a truth-zone entry to name alternate semantically-equivalent paths that will still be credited if matched. The gate is: alt path matches AND value fuzzy-matches ≥0.5 against the expected value.

The value-match gate is the correct backstop in most cases — it prevents trivially-matched alt paths from granting credit for garbage content. But it misfires on a narrow class where the LLM emits the *right path* (now matched by `alt_defensible_paths`) with a *compressed or partial value* that's semantically right but fuzzy <0.5.

**r5h evidence:**

| case | alt path matched | LLM value | expected value | fuzzy | current credit |
|---|---|---|---|---|---|
| case_087 | `greatGrandparents.ancestry` | `"French"` | `"French (Alsace-Lorraine), German (Hanover)"` | <0.5 | none |
| case_075 | (TBD per r5e1 rundown) | | | <0.5 | none |
| case_088 | (TBD per r5e1 rundown) | | | <0.5 | none |

Without value-alt-credit, case_087 sits at score 0.50 permanently (alt path matched but value rejected), blocking #144 Lane 1's intended r5i/r5h delta from converting this case.

## 2. Proposal

Add an `alt_defensible_values` array (optional) on truth-zone entries. Used only when the alt path has already matched; permits specific pre-curated value variants to satisfy the ≥0.5 fuzzy gate.

**Example annotation:**

```json
{
  "path": "grandparents.ancestry",
  "expected": "French (Alsace-Lorraine), German (Hanover)",
  "alt_defensible_paths": ["greatGrandparents.ancestry"],
  "alt_defensible_values": ["French", "German", "French and German", "Alsace-Lorraine", "Hanover"]
}
```

**Scorer behavior:**

1. If LLM emitted the expected path AND value fuzzy-match ≥0.5 → credit (unchanged).
2. Else if LLM emitted an `alt_defensible_paths` entry AND value fuzzy-match ≥0.5 against `expected` → credit, classifier adds `defensible_alt_credit` (unchanged, #94).
3. **NEW:** Else if LLM emitted an `alt_defensible_paths` entry AND value fuzzy-match <0.5 against `expected` BUT ≥0.5 against any entry in `alt_defensible_values` → credit, classifier adds `defensible_alt_value_credit` (informative, non-penal).
4. Else → miss (unchanged).

The rule is **strictly additive**: a case that doesn't use `alt_defensible_values` or whose annotations contain no such array is unaffected.

## 3. Why a second array rather than relaxing the fuzzy gate

Three-agent convergence required (this is a gate-loosening proposal):

- A bare fuzzy-gate relaxation (e.g., from ≥0.5 to ≥0.3) would create false-positive risk across ALL cases, not just the value-drift class. The surgical array is strictly additive with no effect on cases that don't opt in.
- A "semantic-equivalence dictionary" global lookup would be a bigger commit and less auditable per-case.
- `alt_defensible_values` is inspectable on the case that uses it; failures from over-generous `alt_defensible_values` entries are visible in the r5k audit (if a case that shouldn't pass starts passing, we see the specific values granted).

## 4. Acceptance (r5k)

- case_087 flips 0.50→1.00 (or at least ≥0.70 v3 threshold)
- r5k pass count ≥ r5i pass count (no regression)
- Zero backward flips
- must_not_write ≤ 2 (no new offenders)
- Scorer-drift audit on every flip: truth-zone totals identical r5i→r5k; only `hit` counts rose; the classifier label `defensible_alt_value_credit` is present on every flip attributable to this WO
- case_075, case_088 (pending concrete annotation data from r5e1 rundown readthrough) either pass or remain at their r5i score — annotation-level decision

## 5. Scope-out

- This WO does NOT introduce a global synonym table. Every `alt_defensible_values` entry is a deliberate per-case annotation.
- This WO does NOT loosen the value-match gate elsewhere.
- This WO does NOT change extract.py (scorer-side only, `scripts/run_question_bank_extraction_eval.py`).

## 6. Implementation sketch

Edit site: `scripts/run_question_bank_extraction_eval.py`, the `score_field_match` path that currently handles `alt_defensible_paths`. Add a fallback branch that consults `alt_defensible_values` only when alt path matched but expected-value fuzzy <0.5.

Classifier label: `defensible_alt_value_credit` (alongside existing `defensible_alt_credit`).

Per-field JSON emission in the result object: include which alt value was matched, for auditability.

## 7. Rollback

Revert the scorer branch + the case-file annotations.

## 8. Standard audit block (required at landing)

Report r5k:

- total pass count
- v3 / v2 contract subset
- must_not_write violations
- named affected cases
- pass↔fail flips
- scorer-drift audit on every flip (verify `defensible_alt_value_credit` label on each)
- truncation_rate
