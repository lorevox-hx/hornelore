# WO-EX-PROMPTSHRINK-01 — Topic-scoped extraction prompt

**Author:** Claude (LOOP-01 R4 cleanup, task #81)
**Status:** v1 IMPLEMENTED, env-gated (default OFF). Awaiting `r4j` live eval.
**Depends on:** #67 closed (r4i clean); #63 scorer-drift audit runs in parallel, not a blocker.
**Blocks:** post-R4 freeze, R5.5 citation-grounding work.

## Revision note (2026-04-19)

The original draft of this WO proposed three workstreams — A (per-turn catalog scoping), B (few-shot audit-and-prune), C (catalog presentation restructure) — staged as separate commits and ablated individually. After the draft was written, the implementation was simplified to a single lever that does the work of all three in one pass, without touching the catalog or the rule blocks. This revision documents what shipped, the rationale for the simplification, and what remains available as follow-up if the single-lever approach doesn't move enough.

## Problem statement

`_build_extraction_prompt` (extract.py:412–757) ships a single monolithic system prompt on every extraction call. It contains:

- Preamble + compact field catalog of **108 `EXTRACTABLE_FIELDS`** rendered as a comma-joined string.
- 1 ROUTING DISTINCTIONS block.
- **33 few-shot examples** (~230 lines of prompt body).
- 4 closing rule blocks (NEGATION, SUBJECT, SAME-ENTITY ELABORATION, FIELD ROUTING).

Total prompt surface ≈ 29,700 characters — roughly 8–9k tokens on the local tokenizer. For any given extraction the vast majority of those 33 examples are off-topic and compete for the LLM's attention with the single relevant rule.

Evidence for the dilution hypothesis:
- **`dense_truth 0/8`** — when the narrator's answer is itself long and packed with facts, model attention on the prompt degrades and extraction under- or over-commits.
- **`large chunks 0/4`** — same mechanism on long chunks: prompt + answer + catalog exceeds the model's effective attention window.
- **`extract_multiple 19/52` / `extract_compound 5/13`** — compound answers need the model to hold multiple routing rules simultaneously; attention dilution forces hedging.
- **Schema-gap hallucinations** — 28 cases in r4i fail with `schema_gap` or `field_path_mismatch`. The catalog-as-string presentation lets the model confabulate plausible-looking field paths that don't exist.

Three-agent convergence (Claude / Gemini / ChatGPT) identified prompt shrink as the right R4 closeout move before pivoting to R5.5 citation grounding.

## Non-goals

- Not restructuring the Pillar 1 Draft/Project/Bind split — that's R6.
- Not adding citation grounding — that's R5.5.
- Not rewriting the span-tagger or field-classifier prompts — those are separate functions.
- **Not removing any ROUTING / NEGATION / SUBJECT / SAME-ENTITY / FIELD ROUTING rules.** All 5 rule blocks are preserved byte-for-byte — the six current distinctions are all load-bearing per api.log evidence.
- Not touching the compound-answer detection or MAX_NEW_TOKENS dispatch — separate code path.
- Not touching the two-pass (`HORNELORE_TWOPASS_EXTRACT`) path — PROMPTSHRINK is single-pass-only. If twopass is re-enabled, PROMPTSHRINK is a no-op on that path.
- No ceiling claims on `dense_truth 0/8` or `large chunks 0/4` — those remain R5.5 Pillar 1 territory. PROMPTSHRINK will not move them, and that is not a failure.

## What shipped (v1)

A new builder `_build_extraction_prompt_shrunk(answer, current_section, current_target)` dispatches alongside the legacy builder. Both live in `server/code/api/routers/extract.py`; the dispatcher in `_extract_via_singlepass` (line 843) picks which one to call based on an env flag.

```
HORNELORE_PROMPTSHRINK=1   # topic-scoped prompt
HORNELORE_PROMPTSHRINK=0   # legacy monolith (default)
HORNELORE_PROMPTSHRINK_MAX_EXAMPLES=8   # cap on included few-shots (default 8)
```

Rollback is a single env-var flip — no code change needed if the eval regresses.

### Assembly

Always-on (byte-for-byte copies from the legacy monolith):

1. Preamble (JSON format + rules).
2. Compact field catalog (unchanged — all 108 paths as a comma-joined `"path"=label` string).
3. ROUTING DISTINCTIONS block.
4. NEGATION RULE.
5. SUBJECT RULE.
6. SAME-ENTITY ELABORATION RULE (all 16 canonical narrative-catch slots).
7. FIELD ROUTING RULES.

Topic-scoped (selected from a tagged bank):

- Few-shot examples, selected by intersecting detected topic tags with each example's topic set.
- **Universal anchors** (tag `universal`) always included regardless of detected topics:
  1. The parents+siblings compound example (John Smith / Amy) — teaches family routing baseline.
  2. The first-child example (Christopher, Dec 24 1962, Williston) — teaches date format + birth-order.
  3. The Ivan-dog anti-pattern — teaches `pets.name` vs `pets.notes` discipline.

### Topic detection

Two sources union into a single topic set before selection:

1. `current_target` → `_promptshrink_topics_for_target(path)`. Prefix-matches the field path. `parents.*` → `{parents, family}`, `military.*` → `{military}`, `residence.*` → `{residence}`, etc.
2. `current_section` → `_promptshrink_topics_for_section(section)`. Substring-matches the subTopic string. "compound_family" → `{parents, siblings, family}`, "partnership_marriage" → `{marriage, family}`, etc.

When both are empty (no topic signal), selection falls back to the 3 universal anchors only — not the full 33. The rule blocks still carry routing for unknown-topic calls.

### Size reduction — smoke-test inputs

| case                      | legacy chars | shrunk chars | cut  | few-shots |
|---------------------------|-------------:|-------------:|-----:|----------:|
| birthDate (case_011 cls)  | 29,696       | 17,864       | 40%  | 8         |
| compound_family (case_053)| 29,696       | 17,413       | 41%  | 8         |
| spouse+children (case_094)| 29,696       | 17,413       | 41%  | 8         |
| dense_truth (case_080 cls)| 29,696       | 18,016       | 39%  | 8         |
| no hints                  | 29,696       | 15,618       | 47%  | 3         |
| military-targeted         | 29,696       | 16,027       | 46%  | 4         |
| pets-targeted             | 29,696       | 16,182       | 46%  | 5         |

~40% prompt-surface reduction across the distribution.

## Why this diverges from the original three-workstream draft

The draft proposed A (catalog scoping), B (static few-shot prune by log audit), C (branch-grouped catalog rendering). What shipped is dynamic few-shot scoping only — no catalog changes.

Rationale:

- **Catalog scoping (A) is genuinely risky for null_clarify / adjacent-branch co-emission.** The original draft already flagged this. Without a clear audit of which branches legitimately co-occur, narrowing the catalog risks suppressing correct extractions of incidental facts. Pushing A to a follow-up WO preserves the null_clarify suite and lets us measure few-shot impact in isolation.
- **Static log-audit prune (B) produces a stale asset.** Every new case added to the eval could require re-auditing. Dynamic selection by topic tag is maintenance-free — new few-shots just need a tag, and new sections just need a keyword map entry.
- **The hypothesis the eval needs to test is simpler.** "Does attention dilution hurt routing?" is a single lever question. Ablating three workstreams in parallel obscures which one moved the needle. A single-variable change is the cleaner experiment.
- **v1 is more aggressive than the original target (3–8 examples vs 18–22).** This is deliberate. If 18–22 was a marginal shrink and 3–8 is substantial, the bigger cut maximises the chance of a measurable signal in a single eval. If v1 over-shrinks and regresses, the log line and rollback flag make the failure mode easy to diagnose, and we can dial `HORNELORE_PROMPTSHRINK_MAX_EXAMPLES` back up or widen the topic-match criteria without a code change.

If `r4j` shows the shrunk prompt regressed, we still have:
- **v2**: less aggressive cut (widen tag matching, raise MAX_EXAMPLES, add more universal anchors).
- **v3**: the original Workstream A (catalog scoping) as a standalone follow-up WO.
- **v4**: Workstream C (branch-grouped catalog rendering) as a standalone follow-up WO.

## Default answers to #86 open questions

Adopted as v1 defaults. Flip any that are wrong and I'll re-draft.

1. **Shrink target:** few-shots only. Preamble, catalog, ROUTING DISTINCTIONS, and all 4 closing rule blocks preserved byte-for-byte. No catalog changes.
2. **Token budget:** count cap (`MAX_EXAMPLES=8`) on included few-shots, plus universal anchors. VRAM-GUARD 8192 truncation remains the backstop. Typical topic-scoped call: ~17k chars (~4.5k tokens) of system prompt, leaving ~3.7k tokens headroom for answer + output.
3. **Measurement surface:** `extract_multiple` (19/52) + `extract_compound` (5/13) are the primary win zones. `must_not_write` (currently 0.0%) is the primary loss guard. Secondary: `field_path_mismatch` (14) and `llm_hallucination` (13) should not regress.
4. **Rollback trigger:** set `HORNELORE_PROMPTSHRINK=0` if any of —
   - `must_not_write` violations > 0
   - topline pass count < 53 (r4h floor)
   - `extract_multiple` regresses by ≥ 3 cases vs r4i
   - any narrator average drops > 0.05 absolute

## Observability

New log line per extraction call when flag is on:

```
[extract][PROMPTSHRINK] topics=<sorted list> fewshots_count=<n> target=<path> section=<str>
```

Grep `api.log` for `[PROMPTSHRINK]` after the eval to confirm:
- Topic detection is firing (non-`<none>` on contract cases).
- Example counts are within the expected 3–8 band.
- No case degenerates into the empty-topic branch unexpectedly.

## Eval plan

Single eval, suffix `r4j`. Chris restarts the API with `HORNELORE_PROMPTSHRINK=1` in env, then runs the standard eval.

```bash
cd /mnt/c/Users/chris/hornelore
./scripts/run_question_bank_extraction_eval.py --mode live \
  --api http://localhost:8000 \
  --output docs/reports/master_loop01_r4j.json
grep "\[extract\]\[PROMPTSHRINK\]" .runtime/logs/api.log | tail -40
```

### Required post-eval audit block

Per CLAUDE.md standing rule — report before declaring movement real:

- total pass count (vs r4i 55/104)
- v2 contract subset (vs r4i 31/62)
- v3 contract subset (vs r4i 34/62)
- must_not_write violations (must stay at 0)
- named affected cases (newly passed / newly failed relative to r4i)
- pass↔fail flips
- scorer-drift audit on every flip — real routing change, or expectation drift?
- **extract_multiple and extract_compound deltas** specifically — the hypothesis target
- dense_truth and large chunk buckets — expected unchanged; they're R5.5 territory

## Closeout criteria

PROMPTSHRINK-01 closes when `r4j` is run, audited, and either:

- **(keep)** topline ≥ 55, must_not_write=0, and no regressions in the four failure categories → keep flag on, update CLAUDE.md to list PROMPTSHRINK as default-on, proceed to R4 freeze prep.
- **(no-move)** topline within ±1 of r4i, must_not_write=0, no regressions → WO closed as "no-move", flag stays off, move straight to R5.5.
- **(regress)** any regression trigger hits → flip flag off, WO closed as "regressed", append the data to this doc, v2 design follows.

Regardless of direction, `extract_multiple` and `extract_compound` per-bucket deltas are recorded so we know whether the hypothesis (attention dilution hurts compound routing) held or didn't.

## Files touched

- `server/code/api/routers/extract.py`:
  - Added `_PROMPTSHRINK_PREAMBLE`, `_PROMPTSHRINK_ROUTING_DISTINCTIONS`, `_PROMPTSHRINK_NEGATION_RULE`, `_PROMPTSHRINK_SUBJECT_RULE`, `_PROMPTSHRINK_SAME_ENTITY_RULE`, `_PROMPTSHRINK_FIELD_ROUTING_RULES` module-level constants.
  - Added `_PROMPTSHRINK_FEW_SHOTS` — 33 entries, each tagged with topic set. Verbatim copies of the legacy monolith examples.
  - Added `_promptshrink_topics_for_target`, `_promptshrink_topics_for_section`, `_promptshrink_select_fewshots`, `_build_extraction_prompt_shrunk`, `_promptshrink_enabled` helpers.
  - Modified `_extract_via_singlepass` (line 843) to branch on `_promptshrink_enabled()`. Legacy builder path is unchanged and byte-stable.
- `docs/reports/WO-EX-CASE053-DISPOSITION.md` — #68 disposition memo (landed same session).
- This spec.

## Out-of-scope follow-ups (if v1 doesn't move enough)

- **WO-EX-PROMPTSHRINK-02**: Workstream A (catalog scoping) from the original three-workstream draft. Gated on null_clarify regression audit.
- **WO-EX-PROMPTSHRINK-03**: Workstream C (branch-grouped catalog rendering). Independent from 02.
- **WO-EX-FEWSHOT-REGEN-01**: regenerate the few-shot set from scratch based on post-R5 case clusters. Today's few-shots are artifacts of R2/R3/R4 incremental debugging. Defer to R6.

## Disposition — measured, not adopted (r4j closeout)

**Status:** CLOSED — "no-move" track. Flag stays **off** by default. r4i remains the active post-R4 baseline.

### r4j results vs r4i

| Metric | r4i (flag off) | r4j (flag on) | Δ |
|---|---|---|---|
| Topline pass | 55/104 (52.9%) | 54/104 (51.9%) | **−1** |
| v3 contract subset | 34/62 | 33/62 | −1 |
| v2 contract subset | 31/62 | 30/62 | −1 |
| v2-compat (all) | 37/104 | 36/104 | −1 |
| must_not_write violations | 0.0% | 0.0% | 0 |
| must_extract recall | 52.0% | 51.4% | −0.6pp |
| schema_gap | 28 | 29 | +1 |
| llm_hallucination | 13 | 13 | 0 |
| field_path_mismatch | 14 | 14 | 0 |
| noise_leakage | 9 | 10 | +1 |

### Pass↔fail flips

- **Newly failed:** `case_012` (kent-james-horne, relationship_anchors, tiny, clean). Score 1.0 → 0.5, primary failure `schema_gap`.
- **Newly passed:** none.
- **Score drift ≥0.05 (non-flip):** none.

### Scorer-drift audit on the single flip

Real routing regression, not scorer drift.

- **Narrator text:** *"I married Janice Josephine Zarr on October 10th, 1959. I was nineteen and she was twenty."*
- **extractPriority:** `[family.spouse, family.marriageDate]`
- **r4i items (pass, 1.0):** `family.spouse.firstName=Janice`, `family.spouse.middleName=Josephine`, `family.spouse.lastName=Zarr`, **`family.marriageDate=1959-10-10`**.
- **r4j items (fail, 0.5, schema_gap):** `family.spouse.firstName/middleName/lastName` correct, but `family.marriageDate` **missing** and replaced by **`family.spouse.dateOfBirth=1939`** — the LLM back-computed a spouse DOB from "she was twenty" instead of routing the in-sentence date to `marriageDate`.

Root cause: the shrunk prompt dropped the few-shot demonstrating "date-in-marriage-context → marriageDate" routing. Under the legacy 33-shot monolith the model had the routing pattern in-context; under the 3-8 topic-scoped selection it did not. The hypothesis that attention dilution hurts compound routing is **not supported** — it is the opposite pattern (few-shot starvation on a specific routing template).

### Hypothesis check — extract_multiple / extract_compound

| Behavior | r4i passed | r4j passed | Δ |
|---|---|---|---|
| extract_multiple | 18/52 | 18/52 | 0 |
| extract_compound | 5/13 | 5/13 | 0 |

Target buckets did not move. The stated hypothesis (dilution-hurts-compound) did not hold up in measurement.

### Stubborn-pack r4j stability (3 runs, HORNELORE_PROMPTSHRINK=1)

- stable_pass: **0 / 15**
- stable_fail: **15 / 15**
- unstable: 0 / 15
- truncated (any run): **15 / 15** — VRAM-GUARD 8192-token ceiling fired on every stubborn case in at least one run
- score improved across runs: 0
- failure-category changed: 1
- field-path shape changed: 0

The stubborn frontier is **truncation-dominated**, not prompt-verbosity-dominated. Shrinking the prompt did not convert a single stubborn case and did not shift stability anywhere. This is the cleanest signal from r4j and it reframes the next WO (SPANTAG) — any contract change that *grows* the output budget must be paired with input-side savings or it will worsen the truncation floor.

### Decision

- **Flag left off.** `HORNELORE_PROMPTSHRINK=1` is not default. Legacy 33-shot path is the live path.
- **r4i is frozen as the active post-R4 baseline** (see `docs/reports/POST-R4-BASELINE-LOCK.md`).
- **No rollback of the code.** The shrunk path stays in-tree behind the flag — it cost nothing to keep and we may want it back when SPANTAG lands (if SPANTAG consumes output budget, freeing input budget via PROMPTSHRINK becomes valuable again).
- **Closed as "no-move / regressed-by-one".** A full rollback is not warranted — one flip, no must_not_write, hypothesis cleanly measured and falsified, truncation signal isolated.

### Follow-on

- 02 (catalog scoping) and 03 (branch-grouped catalog rendering) stay deferred.
- FEWSHOT-REGEN-01 is still valid but now gated behind SPANTAG signoff — the post-SPANTAG cluster may make today's few-shots obsolete anyway.

## Revision history

- 2026-04-19 (draft): Initial three-workstream spec (A / B / C).
- 2026-04-19 (revised): Simplified to single-lever dynamic topic-scoped few-shot selection. Shipped as v1. Rationale for divergence documented above.
- 2026-04-20: r4j measured. CLOSED as "no-move / regressed-by-one". Flag stays off; r4i is active baseline. See Disposition section.
