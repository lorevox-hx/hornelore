# WO-EX-PROMPTSHRINK-01 — Extraction prompt catalog shrink

**Author:** Claude (LOOP-01 R4 cleanup, task #81)
**Status:** DRAFT — awaiting Chris review. Do NOT implement until spec is signed off.
**Depends on:** #67 closed (r4i clean); #63 scorer-drift audit runs in parallel, not a blocker.
**Blocks:** post-R4 freeze, R5.5 citation-grounding work.

## Problem statement

The extraction system prompt (`_build_extraction_prompt`, extract.py:412–894) is 466 source-lines and carries:

- A full field catalog of **108 `EXTRACTABLE_FIELDS`** rendered as a comma-joined string on every call.
- **33 few-shot examples** spanning routing edges, relation distinctions, career tracks, touchstone-event anchors, pet routing, contrast-affirmation, grandparent vs great-grandparent, military rollup, dense-life-history, etc.
- A dense block of ROUTING DISTINCTIONS (pets vs hobbies, siblings vs children, birthplace vs residence, earlyCareer vs careerProgression).

This prompt has grown incrementally across R2, R3, and R4 — each patch adding a few-shot or rule to close one observed failure. The structural cost is now showing up in three places simultaneously:

1. **`dense_truth 0/8`** — when the narrator's answer is itself long and packed with facts, model attention on the prompt's instructions degrades and the extractor either under-extracts or emits hallucinated paths.
2. **`large chunks 0/4`** — same mechanism on long chunks: prompt + answer + catalog exceeds the model's effective attention window.
3. **Schema-gap hallucinations** — 29 cases in r4f/r4h fail with `schema_gap` or `field_path_mismatch`. The catalog-as-string presentation lets the model confabulate plausible-looking field paths (`career.fieldOfStudy`, `employment.organization`) that don't exist.

Evidence from research synthesis (`docs/reports/loop01_research_synthesis.md` citing *Order Is Not Layout*, *Self-Aware Language Models*, *Draft-Conditioned Constrained Decoding*): long, unstructured prompt catalogs are the single highest-leverage lever for LLM extraction quality on small local models. Research-agent convergence (Claude + Gemini + ChatGPT) identified prompt shrink as the right R4 closeout move before pivoting to R5.5 citation grounding.

## Non-goals

- **Not restructuring the Pillar 1 Draft/Project/Bind split** — that's R6.
- **Not adding citation grounding** — that's R5.5.
- **Not rewriting the span-tagger or field-classifier prompts** — those are separate functions with their own shape; this WO only touches `_build_extraction_prompt`.
- **Not removing any ROUTING DISTINCTIONS rules** — the six current rules are all load-bearing per api.log evidence.
- **Not removing few-shots "by author's intuition"** — every removal must be backed by either a log-audit showing the few-shot is never actively used, or an ablation eval showing removal doesn't regress a named case.

## Goals

Three cumulative goals, each individually valuable:

1. **Scope the field catalog per turn.** Send only the fields reachable from the current extraction target (`current_target_paths`) plus their near-siblings, instead of all 108. Cut the catalog string by ~60–70%.
2. **Audit and prune few-shots.** Identify which of the 33 examples are never reinforced by actual cases (dead weight) and which are doing most of the guard work (keep).
3. **Restructure catalog presentation.** Move from a comma-joined string to a structured, deduplicated per-branch listing that's easier for the model to parse.

Success threshold: `r4j` eval maintains or improves on `r4i` for:
- **Topline pass rate:** ≥ r4i.
- **v3 subset:** ≥ r4i.
- **`must_not_write` violations:** ≤ r4i (must not regress).
- **`dense_truth` subset:** improvement of ≥ 1/8 (any movement off zero is a win).
- **Schema-gap failure category:** reduction of ≥ 5 cases.
- **No new regressions on the named cases** currently passing (case_094, case_060, case_062, case_011 after r4i, and all of the null_clarify suite).

## Scope breakdown

### Workstream A — Per-turn catalog scoping

**Mechanism:** When `current_target_paths` is non-empty, derive the "allowed set" of field paths to include in the prompt catalog from:
- All paths in `current_target_paths` themselves.
- All paths sharing the same branch root (e.g. `family.children.*` if `current_target_paths` contains `family.children.firstName`).
- A small always-on core (e.g. `personal.firstName`, `personal.lastName`, `personal.dateOfBirth`) so the LLM can still extract identity facts mentioned in passing.

**When `current_target_paths` is empty / None:** fall back to full catalog (current behavior). This preserves null_clarify and open-turn cases.

**Exit criteria:** field catalog string shrinks from ~108 entries to 15–40 entries on 80%+ of eval cases, with zero regression on the null_clarify subset.

**Risk:** LLM misses legitimate facts in adjacent branches because they were filtered out. Mitigation: the "core" set + branch-sibling inclusion. Further mitigation: always-on branches for common co-emission patterns (`family.spouse.*` ↔ `family.children.*`, `parents.*` ↔ `siblings.*`).

### Workstream B — Few-shot audit

**Mechanism:** Log-based audit. Grep `api.log` across the last 20 evals for `[extract][prompt]` lines that record which few-shot pattern the LLM's output resembles. For each of the 33 few-shots:

- If 0 matches across 20 runs → candidate for removal.
- If 1–3 matches → candidate for merging with a sibling few-shot.
- If >3 matches → keep as-is.

Additionally: identify which few-shots map to an active eval case (case_011 matches the Christmas Eve children-birth few-shot). Keep any few-shot whose target case is in the eval suite.

**Exit criteria:** drop from 33 few-shots to 18–22, with every dropped example paired with either "no audit hits" or "absorbed into a surviving merged example."

**Risk:** pruning a few-shot that the LLM needed but didn't make obvious log traces for. Mitigation: run an offline-mode eval against the pruned prompt BEFORE running live to cheaply catch most regressions. Further mitigation: the pruned few-shots are kept in a `# ARCHIVED FEW-SHOTS` comment block at the bottom of `_build_extraction_prompt` so they can be resurrected individually if a case regresses.

### Workstream C — Catalog presentation

**Mechanism:** Move from the current single-line comma-joined catalog:

```
"personal.firstName"=First name, "personal.lastName"=Last name, ...
```

to a per-branch structured listing:

```
BRANCH personal:
  firstName (label: First name)
  lastName (label: Last name)
  dateOfBirth (label: Birth date, format: YYYY-MM-DD)
  placeOfBirth (label: Birthplace)
BRANCH family.spouse:
  firstName (label: Spouse first name)
  ...
```

This gives the model a clearer mental model of path structure AND cuts duplication — the branch header is named once per branch instead of repeated N times in the dotted paths.

**Exit criteria:** prompt character count drops by ≥ 25% relative to r4i baseline while presenting the same or fewer fields.

**Risk:** the model's learned associations rely on the old dotted format. Mitigation: present BOTH for one eval cycle (structured block + the dotted form retained as a one-line compact list for fallback pattern matching), measure, then drop the redundant form in a follow-up WO if clean.

## Measurement plan

Before/after metrics, captured in `docs/reports/WO-EX-PROMPTSHRINK-01_REPORT.md`:

1. **Prompt character count** at each call site: mean, median, p95 across all 104 eval cases. Token count via tiktoken (or estimate chars/4).
2. **Eval topline delta**: r4j vs r4i on pass/v3/v2/must_not_write/dense_truth/schema_gap.
3. **Per-case flip audit**: every pass↔fail flip inspected for scorer drift per the standard post-eval audit block.
4. **Ablation pass**: run the eval TWICE — once with Workstream A only, once with A+B, once with A+B+C. Isolates which lever contributes which delta.

## Implementation plan

In order, each landing as its own commit:

1. **Commit 1 — Workstream A only.** Add `_scope_catalog_for_targets()` helper. Wire into `_build_extraction_prompt`. Run `r4j-a` eval.
2. **Commit 2 — Workstream B only.** Audit log, identify prunable few-shots, remove them, retain the archived comment block. Run `r4j-ab` eval.
3. **Commit 3 — Workstream C only.** Restructure the catalog string format. Run `r4j-abc` eval.
4. **Commit 4 — Final WO report** with the 4-way comparison (r4i baseline → r4j-a → r4j-ab → r4j-abc).

Each commit is independently reversible.

## Out-of-scope follow-ups

- **WO-EX-FEWSHOT-REGEN-01**: regenerate the few-shot set from scratch based on post-R5 case clusters. Today's few-shots are artifacts of R2/R3/R4's incremental debugging and are biased toward the cases that failed first rather than the cases that matter most. Defer to R6.
- **WO-EX-PROMPT-DSL-01**: move from inline-string prompt construction to a declarative DSL (e.g., JSON template + renderer). Reduces edit risk but is architectural and defers to R6.

## Open questions for Chris

1. **Workstream A "always-on core" list** — should it include identity (`personal.firstName/lastName/dateOfBirth/placeOfBirth`) only, or also common relational roots (`parents.relation`, `siblings.relation`, `family.spouse.firstName`)? More permissive = safer, but less shrink.
2. **Branch-sibling inclusion rule** — do we include the full branch (`family.children.*` = all 8 child fields) or just the specific sibling-of-target? Full branch is safer; target-only is sharper.
3. **`extractPriority=None` case** — keep full-catalog fallback, or try a narrower "phase-based" catalog scoped by `current_section`? The latter is more aggressive but risks regressing the null_clarify suite.
4. **Ablation ordering** — the plan above runs A first, then A+B, then A+B+C. Would you prefer to isolate B (few-shot prune) before A (catalog scope), since B is the lower-risk and would let us measure catalog size effects independently?

## Revision history

- 2026-04-19: Initial draft.
