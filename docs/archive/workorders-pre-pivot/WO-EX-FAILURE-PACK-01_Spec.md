# WO-EX-FAILURE-PACK-01 — Cluster JSON output on every master eval (#141)

**Status:** DRAFT (2026-04-22, authored after r5h adopt)
**Owner:** eval-harness lane (Claude)
**Priority:** parallel cleanup lane — does not block main sequence
**Blocks:** nothing
**Blocked by:** nothing
**Eval tag:** N/A (harness-side, byte-stable scoring)
**Task:** #141

---

## 1. Problem statement

Each master eval run produces a `master_loop01_<SUFFIX>.json` (~350KB, 104 case results) and `master_loop01_<SUFFIX>.console.txt` (topline + per-case). Cross-eval triage requires hand-rolled scripts every time — see today's authoring of `FAILING_CASES_r5h_RUNDOWN.md`, which re-implemented failure-category tally, hallucination prefix rollup, and narrator × phase × score-bucket grouping from scratch.

This is a recurring task. The signal is always the same: failures grouped by `(failure_category × narrator × phase-family × score-bucket)`, with hallucination-prefix and mnw breakouts. A companion artifact written alongside the eval JSON would remove the one-off scripting cost and make the Chris / Claude / ChatGPT triangulation faster.

## 2. Proposal

Extend `scripts/run_question_bank_extraction_eval.py` to emit a second sidecar file `master_loop01_<SUFFIX>.failure_pack.json` (and a `.failure_pack.console.txt` rendering) next to the existing outputs. Byte-stable scoring behavior; additive only.

**Schema (draft):**

```jsonc
{
  "eval_tag": "r5h",
  "total_cases": 104,
  "passed": 70,
  "failed": 34,
  "failure_categories": {
    "schema_gap": { "count": 14, "cases": ["case_002", "case_024", ...] },
    "llm_hallucination": { "count": 13, "cases": [...] },
    ...
  },
  "by_narrator": {
    "christopher-todd-horne": { "failed": 11, "cases": [...] },
    "janice-josephine-horne": { "failed": 12, "cases": [...] },
    "kent-james-horne":       { "failed": 11, "cases": [...] }
  },
  "by_phase_family": {
    "developmental_foundations": { "failed": 22, "cases": [...] },
    "early_adulthood":           { "failed": 3,  "cases": [...] },
    "midlife":                   { "failed": 5,  "cases": [...] },
    ...
  },
  "by_score_bucket": {
    "0.00":      { "count": 10, "cases": [...] },
    "0.01-0.24": { "count": 0,  "cases": [] },
    "0.25-0.49": { "count": 6,  "cases": [...] },
    "0.50-0.69": { "count": 17, "cases": [...] },
    "0.70+":     { "count": 1,  "cases": [...] }
  },
  "hallucination_prefix_rollup": {
    "parents":          { "offenders": 11, "cases": [...] },
    "family":           { "offenders": 10, "cases": [...] },
    "siblings":         { "offenders": 7,  "cases": [...] },
    "greatGrandparents":{ "offenders": 5,  "cases": [...] },
    ...
  },
  "must_not_write": {
    "count": 2,
    "cases": [
      { "case_id": "case_035", "offenders": ["education.schooling"] },
      { "case_id": "case_093", "offenders": ["education.higherEducation"] }
    ]
  },
  "cross_axis_highlights": [
    { "axis": "narrator×phase", "row": "janice-josephine-horne×developmental_foundations", "failed": 7 },
    { "axis": "category×narrator", "row": "schema_gap×kent-james-horne", "failed": 4 }
  ]
}
```

**Console rendering:** A ~50-line ASCII table mirroring `FAILING_CASES_r5h_RUNDOWN.md` topline sections (category tally, narrator tally, score bucket, hallucination prefix, mnw). Written next to `.console.txt` so it lands in the same `grep`-friendly directory.

## 3. Acceptance

- Runs on every master eval with zero impact on `master_loop01_<SUFFIX>.json` (byte-identical)
- `.failure_pack.json` + `.failure_pack.console.txt` both present after an eval
- Schema tracks the r5h rundown doc 1:1 (anyone reading either should get the same picture)
- Empty-pass case (all 104 pass) writes a valid file with zeros — don't crash on the happy path
- Zero new dependencies

## 4. Scope-out

- Does NOT change any scoring logic.
- Does NOT attempt cross-eval diff (that belongs in a separate tool; failure_pack is per-eval).
- Does NOT attempt per-case failure explanations beyond the existing `failure_categories` field — no LLM usage.

## 5. Implementation note

The script already builds the in-memory data needed to produce these rollups (case_results list, invalid_field_path_hallucinations list, must_not_write_violations list). This is pure aggregation on the write-path side, not a second pass through the data.

The phase→phase-family mapping reuses the existing `_phase_to_era` helper (or a sibling) added in SECTION-EFFECT Phase 2.

## 6. Rollback

Delete the sidecar write; no other changes to rollback.

## 7. Not required to land before main sequence

This is a triage-productivity WO. It does not block #144 / #97 / #95 / #90 / LORI / INTAKE-IDENTITY. Land it whenever convenient; first beneficiary will be the next master eval that needs a rundown.
