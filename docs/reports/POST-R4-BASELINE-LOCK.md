# POST-R4 Baseline Lock

**Decision date:** 2026-04-20
**Decision owner:** Chris (with Claude / ChatGPT / Gemini convergence on r4j rejection)
**Status:** LOCKED — r4i is the active post-R4 baseline. r4j is documented but not adopted.

## Chosen baseline: r4i

`docs/reports/master_loop01_r4i.json` + `master_loop01_r4i.console.txt`

| Metric | Value |
|---|---|
| Topline pass | 55 / 104 (52.9%) |
| Avg score | 0.610 |
| v3 contract subset | 34 / 62 (54.8%) |
| v2 contract subset | 31 / 62 (50.0%) |
| v2-compat (all) | 37 / 104 (35.6%) |
| must_not_write violations | 0.0% |
| must_extract recall | 52.0% |
| may_extract bonus rate | 21.8% |
| should_ignore leak rate | 23.1% |
| clarify_before_write | 5 / 5 |
| null_case | 2 / 2 |
| schema_gap | 28 |
| llm_hallucination | 13 |
| field_path_mismatch | 14 |
| noise_leakage | 9 |
| dense_truth | 0 / 8 |
| large chunk | 0 / 4 |

R4 sequence of record: r4f (54) → r4g (+2 compound regressions, +target hit) → r4h (53, #72 CLOSED, must_not_write=0) → **r4i (55, #67 + #81-behind-flag landed, active baseline)**.

## Rejected: r4j

`docs/reports/master_loop01_r4j.json`. Run with `HORNELORE_PROMPTSHRINK=1`. Topline 54/104, one regression (`case_012` green→red via schema_gap / spouse-DOB fabrication), no gains. See `WO-EX-PROMPTSHRINK-01_Spec.md` Disposition section for the full flip audit.

r4j is **not** within stochastic noise of r4i along any surface that matters: it's one regression with a clean mechanistic cause (few-shot starvation for marriage-context date routing). It is also not a gain — zero new passes, zero score improvements, zero movement on the stubborn 15.

## What this lock means operationally

1. **All downstream specs are written against r4i metrics**, not r4j. Specifically `WO-82_POSTR4-MEMO.md` and `WO-EX-SPANTAG-01_Spec.md`.
2. `HORNELORE_PROMPTSHRINK=1` is **off by default**. The code path stays in-tree for possible reuse when SPANTAG lands (SPANTAG consumes output budget; freeing input budget may become useful again).
3. Stubborn pack is still the 15 frozen cases: `case_008, 009, 017, 018, 053, 075, 080, 081, 082, 083, 084, 085, 086, 087, 088`. r4j stability run showed 0/15 stable_pass and **15/15 VRAM-GUARD truncation in at least one run**. The frontier is truncation-dominated, not prompt-verbosity-dominated.
4. Next eval tag is **r5a** (first post-baseline-lock eval), not r4k. The R4 cleanup phase is closed.

## What unlocks before SPANTAG Phase 1 ships

- #82 post-R4 memo written (this pass).
- `WO-EX-SPANTAG-01_Spec.md` rewritten to the two-pass design with 15-case stubborn-frontier target pack (this pass).
- #63 eval-harness should_pass drift audit — still pending. Not a blocker for SPANTAG design, but a blocker for calling SPANTAG results "clean" without re-auditing the gap/should-pass tags first.

## References

- `WO-EX-PROMPTSHRINK-01_Spec.md` — full Disposition section with r4j flip audit.
- `docs/reports/master_loop01_r4i.json` / `.console.txt` — locked baseline.
- `docs/reports/master_loop01_r4j.json` / `.console.txt` — rejected measurement.
- `docs/reports/stubborn_pack_r4j_stability.json` / `.console.txt` — 0/15 pass, 15/15 truncation, truncation-dominated finding.
