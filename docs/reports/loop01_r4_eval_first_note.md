# LOOP-01 R4 — Pause before more patches. Measure first.

Date: 2026-04-19
Decision owner: Chris

## The position

The R4 branch has eleven patches on top of R3b. Some may be real gains,
some may be masked by scorer artifacts, some may clearly hurt. We do
**not** pile more patches on top until we understand the branch.

## Order of operations (do not skip steps)

1. **Clean restart.** Stack fully down, stack back up, model fully warm.
2. **Confirm the R4 code actually loaded.** Not just "the API responds" —
   verify R4 markers are live in the running process.
3. **Run the live master eval** against the warmed stack.
4. **Compare cleanly** across runs:
   - R2 baseline (`master_loop01_r2.json`)
   - R3   (`master_loop01_r3.json`)
   - R3b  (`master_loop01_r3b.json`)
   - R4   (this new run)
5. **Inspect the deltas on specific axes** (not the headline pass rate alone):
   - `schema_gap` change per case
   - `field_path_mismatch` change per case
   - `dense_truth` case-type subset change
   - `must_not_write` violation change (safety-critical)
   - scorer-artifact cases — where extractor output is correct but scorer
     marks partial due to surface-form mismatch (Patch H territory)
6. **Then and only then** decide per patch:
   - keep
   - surgically roll back (aliases in particular are cheap to pull)
   - isolate behind a feature flag
   - abandon

## Specific things to be suspicious of

- **Patch H (normalisation).** If pass rate moved without any real
  routing change, it may be the scorer now accepting values it would
  have marked partial. That's fine, but call it what it is — scorer
  compatibility, not extractor improvement.
- **Patch E (relation-scope guard).** Safety-critical. `must_not_write`
  count must not go up. If it does, E is wrong or too broad.
- **Patch I & J (rerouter/dup-emit).** Dup-emits are cheap; they cannot
  lower pass rate, but they can hide a routing bug. Look at the raw
  extractor output, not just the final item list.
- **Patch A (value-length cap).** Catches answer-dumps but may also
  drop legitimate long narrative values if the suffix classification
  is wrong. Diff dropped-item log volume between R3b and R4.
- **Zero-raw cases (005, 012, 013, 023).** If any of these are still
  empty-raw after R4, Patch B few-shots didn't land. Check api.log for
  JSON parse failures at those case IDs — not a patch problem then.

## Eval harness caveat (#63 unresolved)

`should_pass` prediction drift is still open. Up to 26 cases may have
drifted in either direction since R2 baseline. Any apparent delta in
pass rate must be sanity-checked against that — the fair comparison is
per-case pass/fail, not the aggregate.

## Not now

- No new patches.
- No new tests.
- No new few-shots.
- No new aliases.

Next work item is measurement, not more code.
