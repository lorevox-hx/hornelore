# WO-EX-SECTION-EFFECT-01 — Life-map stage as an explicit eval variable

**Author:** Claude (LOOP-01 R5.5 setup, post-three-agent convergence on section-conditioned schema coercion)
**Date:** 2026-04-20
**Status:** ACTIVE — prerequisite WO. **Blocks WO-EX-SPANTAG-01 implementation.** Was originally tracked as #63 "eval-harness should_pass drift audit / retag guard_false_positive → scope_escape"; promoted from cleanup to prerequisite on 2026-04-20 after Chris / Claude / ChatGPT agreement that SPANTAG Pass 2 success can't be read cleanly without this.
**Depends on:** r4i baseline locked. Stubborn-pack stability data from r4j already on hand.
**Blocks:** WO-EX-SPANTAG-01 implementation (all commits). SPANTAG can proceed after Phase 1 of this WO signs off; Phases 2 and 3 can land in parallel with SPANTAG commits as long as the payload extension (Phase 2) ships before the SPANTAG eval report.

---

## Why this is now a prerequisite, not a cleanup

Three-agent convergence on 2026-04-20 (Chris / Claude / ChatGPT) established:

1. Stubborn-frontier failures split into (a) bind/project under section pressure (008, 009, 082), (b) coverage starvation under truncation (080–087 dense_truth cluster), and (c) stable-wrong-shape where the same wrong path family emits across multiple runs (082 is the archetype).
2. The life-map stage — `currentEra` × `currentPass` × `currentMode` — shapes upstream question selection, which sets `current_section` and `current_target_path` in the extraction payload. The extractor then leans toward that target's local ontology. This is **by design** in the single-pass contract — without the section prior the extractor would scatter-shoot the catalog — but it silently wins over subject-binding when the two disagree.
3. For cases like 008 and 009 both the section-driven path (`earlyMemories.significantEvent`, `education.careerProgression`) and the subject-driven path (`parents.notableLifeEvents`, `education.earlyCareer`) are *defensible*. The scorer's expected-truth labels picked subject-driven. Without adjudication, we can't tell whether SPANTAG Pass 2 "fixing" case_008 is a real win or merely agreeing with a labeler preference.

Without this WO landed, SPANTAG's Stubborn-15 movement metric is unreadable.

## Problem framing

Two questions to answer, three deliverables to produce.

### Question 1 — Adjudication

For each of the 15 stubborn cases: **is the expected-truth path the only defensible answer, or is a section-driven alternative also defensible?** If the latter, mark the case dual-answer so the eval scorer and downstream WOs can distinguish "real win" from "labeler coin-flip".

### Question 2 — Causal chain

When extraction produces a wrong field path: **how much of the outcome is explained by `currentEra` / `currentPass` / `currentMode`, how much by `current_target_path` / `current_section`, and how much by the narrator reply text alone?**

Today's extractor payload carries only `current_section` and `current_target_path` — `currentEra`, `currentPass`, `currentMode` shape question selection upstream but do not propagate to the backend. The causal chain is unmeasurable without that propagation. ChatGPT (2026-04-20): *"If you want to truly evaluate life-map stage effect, you should add `currentEra`, `currentPass`, and `currentMode` to the extraction payload or at least to the extraction log."*

## Scope

**In scope:**

- **Phase 1 — Adjudication pass** over the 15 stubborn cases' expected-truth labels. For each case: read the narrator reply, the active `current_section` / `current_target_path`, the expected-truth field paths, and the r4j actual emissions. Classify each case into one of: `subject_only_defensible`, `section_only_defensible`, `dual_answer_defensible`. Output: `docs/reports/WO-EX-SECTION-EFFECT-01_ADJUDICATION.md` plus a patch to `data/qa/question_bank_extraction_cases.json` that adds an `alt_defensible_paths` array per case where applicable.
- **Phase 2 — Payload extension.** Thread `currentEra`, `currentPass`, `currentMode` from the interview runtime into the extraction payload and into `[extract]` log lines. Pure plumbing; no behavior change. Required *before* the SPANTAG eval report so SPANTAG's measurement #10 (section-effect causal chain) can populate.
- **Phase 3 — Minimal causal matrix.** For 2–3 of the Phase-1-adjudicated cases, run the same narrator reply under varied stage context: (correct era, expected section), (correct era, neighboring section), (same era, same section, no target path), (same era, same target path, different mode). Compare emissions. Output: `docs/reports/WO-EX-SECTION-EFFECT-01_CAUSAL.md` — short readout on whether era/pass/mode change outcomes when target path is held fixed.
- **Scorer policy update.** The v3 scorer treats `alt_defensible_paths` as acceptable primary-write targets — matching any listed alt counts as pass, not fail. This is a one-file change in the eval harness.
- **Retag** `guard_false_positive` → `scope_escape` across the existing eval-case files now that #72 TURNSCOPE is closed. (The original #63 cleanup task, preserved here.)

**Out of scope:**

- Running a full master eval under Phase 3's matrix (it's a targeted 2-3-case diagnostic, not a 104-case sweep).
- Changing the upstream interview runtime to emit different section/target-path choices. We are *measuring* the existing behavior, not modifying it.
- SPANTAG implementation (that's WO-EX-SPANTAG-01, which this WO unblocks).
- Learned section-vs-subject weighting (that's SPANTAG v2 if v1 moves the stubborn pack).

## Adjudication questions — the three cases Chris named

These are the adjudications that most directly gate SPANTAG.

### case_008

Narrator reply mentions `"my mom's brother James was born in a car during a blizzard"`. Active section: `earlyMemories`. Active target path: `earlyMemories.*`. Expected-truth primary: `parents.notableLifeEvents`. r4j emitted: `earlyMemories.significantEvent` (one item, schema_gap reported).

**Adjudication question:** If the narrator is answering in the `earlyMemories` section but tells a story *about* their mother's brother, does the expected-truth label accept `earlyMemories.significantEvent` as a defensible alternative, or strictly require `parents.notableLifeEvents`?

**Recommendation (subject to Chris review):** `dual_answer_defensible`. Both paths preserve the fact with different primary subjects. The semantic graph downstream can cross-reference them.

### case_009

Narrator reply about early occupational therapy work. Active section: `education`. Active target path likely `education.*`. Expected-truth primary: `education.earlyCareer`. r4j emitted: `education.careerProgression` and `education.training`.

**Adjudication question:** Within the `education.*` local ontology, is `education.earlyCareer` the only correct first-career path, or are adjacent-neighbor paths (`education.careerProgression`, `education.training`) also defensible when a narrator describes *becoming* an occupational therapist?

**Recommendation (subject to Chris review):** Likely `subject_only_defensible` with a tighter eval-harness note — the three paths have subtly different semantics (earlyCareer = first job, careerProgression = trajectory, training = formal prep). A better answer would split the reply into multiple claims across the three paths, not pick one.

### case_082

Stable across 3 r4j runs: always emits `parents.firstName`, `parents.occupation`, `siblings.firstName`, `siblings.relation`, `residence.place`. That's a `dense_truth` large-chunk case. The consistency across runs rules out stochastic drift.

**Adjudication question:** What *is* the canonical truth shape for case_082? And is the currently-emitted wrong shape (parents.* + siblings.* + residence.*) a section-coercion miss or a schema-neighborhood drift?

**Recommendation (subject to Chris review):** Read the full reply and expected labels before classifying. This case may be primarily a coverage failure (model bailed early under truncation and emitted a plausible-but-underspecified skeleton) rather than a section-coercion miss.

## Phase 1 deliverable shape

`docs/reports/WO-EX-SECTION-EFFECT-01_ADJUDICATION.md` — one row per stubborn case:

| case | narrator reply (trimmed) | active_section | active_target_path | expected_primary | r4j_emitted | classification | alt_defensible_paths | notes |
|---|---|---|---|---|---|---|---|---|

Plus a one-paragraph rollup: "N of 15 are subject_only, N are section_only, N are dual_answer, N are primarily truncation-starved and adjudication is indeterminate until coverage improves."

And a patch to `data/qa/question_bank_extraction_cases.json` adding the `alt_defensible_paths` field to the N dual-answer cases.

## Phase 2 deliverable shape

- Interview runtime change: existing session-state fields `currentEra`, `currentPass`, `currentMode` added to the extraction payload (`server/code/api/routers/extract.py` request model + `server/code/chat_ws.py` caller).
- Log format: `[extract]` log lines gain `era=<>`, `pass=<>`, `mode=<>` fields.
- Eval harness: `scripts/run_question_bank_extraction_eval.py` passes synthesized stage context per case (it already passes section / target path; this adds era/pass/mode).
- Unit test: smoke test confirms the payload round-trips and log lines include the three new fields.
- **No behavior change.** Pure plumbing. Payload extension is strictly additive.

## Phase 3 deliverable shape

`docs/reports/WO-EX-SECTION-EFFECT-01_CAUSAL.md` — for 2–3 adjudicated cases, a small matrix table:

| case | variant | era | pass | mode | section | target_path | emitted paths | score | category |
|---|---|---|---|---|---|---|---|---|---|

Plus a one-paragraph read: "Varying era/pass/mode with target path held fixed (did / did not) change extraction outcomes. Varying target path with section held fixed (did / did not) change outcomes. The load-bearing upstream signal is (era / pass / mode / section / target_path)."

## Goals (concrete, measurable)

1. **Stubborn-15 expected-truth labels adjudicated.** Every case classified into subject_only / section_only / dual_answer / truncation_indeterminate. Dual_answer cases patched into the cases file with `alt_defensible_paths`.
2. **Extraction payload extended.** `currentEra` / `currentPass` / `currentMode` round-trip from interview runtime into backend extractor and into `[extract]` logs. Smoke test green.
3. **Causal matrix filed for ≥ 2 stubborn cases.** Answer recorded: is the load-bearing upstream signal `currentEra/currentPass/currentMode`, or is it only `current_section/current_target_path`, or is neither sufficient to explain the outcome?
4. **Scorer policy updated.** Eval harness accepts matches against `alt_defensible_paths` as primary-write passes. Regression test confirms existing subject_only cases still score the same.
5. **#72-leftover retag.** `guard_false_positive` → `scope_escape` across eval cases, documented in the same commit.

## Acceptance gate

SPANTAG implementation unblocks once Phase 1 signs off with adjudicated labels for 008 / 009 / 082 minimum. Phases 2 and 3 can ship in parallel with SPANTAG commits 1–3 as long as Phase 2 lands before SPANTAG's Commit 5 eval report. Phase 3 is nice-to-have for SPANTAG's measurement #10 population but not a blocker.

## Implementation plan (commits)

1. **Commit 1 — Phase 1 adjudication pass.** Read the 15 cases. Classify. Write `WO-EX-SECTION-EFFECT-01_ADJUDICATION.md`. Patch `question_bank_extraction_cases.json` with `alt_defensible_paths`.
2. **Commit 2 — Scorer policy.** Update `scripts/run_question_bank_extraction_eval.py` (and the scorer module it calls) to treat `alt_defensible_paths` matches as primary-write passes. Regression test.
3. **Commit 3 — Phase 2 payload extension.** Thread `currentEra`/`currentPass`/`currentMode` into extraction payload. Update log format. Smoke test.
4. **Commit 4 — #72-leftover retag.** `guard_false_positive` → `scope_escape` across eval cases. Closes the original #63 cleanup.
5. **Commit 5 — Phase 3 causal matrix.** Run 2–3 stubborn cases under varied stage context. Write `WO-EX-SECTION-EFFECT-01_CAUSAL.md`.
6. **SPANTAG unblocks after Commit 1 signoff.** Commits 2–5 can land in parallel with SPANTAG commits 1–3.

## Related work

- `WO-EX-SPANTAG-01_Spec.md` — the WO this one unblocks. Pass 2 design consumes this WO's adjudicated labels and payload extension.
- `docs/reports/stubborn_pack_r4j_stability.console.txt` — input data: 15 stubborn cases, 3 runs, 15/15 truncation.
- `docs/reports/WO-82_POSTR4-MEMO.md` — broader R4 closeout context.
- ChatGPT's 2026-04-20 analysis — naming "section-conditioned schema coercion" as the mechanism; proposing the causal-chain eval design.

## Revision history

- 2026-04-20: Initial draft. Promoted from #63 cleanup (retag only) to prerequisite WO after three-agent convergence. Three phases: adjudication, payload extension, causal matrix. Blocks SPANTAG implementation.
