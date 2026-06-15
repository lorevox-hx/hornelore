# WO-EX-TRUNCATION-LANE-01 — Truncation-starved dense_truth lane

**Author:** Claude (LOOP-01 R5.5 setup, task #96 / #102)
**Date:** 2026-04-20
**Status:** SPEC — no code. Parallel-track to SPANTAG; does not block it.
**Depends on:** r4i baseline locked. SECTION-EFFECT Phase 1 adjudication (`WO-EX-SECTION-EFFECT-01_ADJUDICATION.md`) classified this sub-pack as `truncation_starved` (7 of 7 runs clamped at 8192 tokens across r4j).
**Blocks:** none. SPANTAG ships independently. Once SPANTAG lands default-on, re-measure this lane — SPANTAG Pass 1's NL tag inventory changes the prompt arithmetic and may partially absorb the truncation lift.

---

## Problem framing

Seven stubborn cases never move under any R4–R5 intervention: `case_080`, `case_081`, `case_083`, `case_084`, `case_085`, `case_086`, `case_087`. All seven share a structural signature:

| ID | chunk | noise | reply_len | must_extract | r5a method | r5a score | r5a extracted_count |
|---|---|---|---|---|---|---|---|
| 080 | medium | dense_truth |   770 ch | 4 | `fallback` | 0.00 | 0 |
| 081 | large  | dense_truth | 1,032 ch | 1 | `fallback` | 0.00 | 0 |
| 083 | medium | dense_truth |   762 ch | 2 | `fallback` | 0.00 | 0 |
| 084 | medium | dense_truth |   718 ch | 2 | `fallback` | 0.00 | 0 |
| 085 | medium | dense_truth |   724 ch | 5 | `rules_fallback` | 0.20 | 2 |
| 086 | medium | dense_truth |   712 ch | 1 | `fallback` | 0.00 | 0 |
| 087 | large  | dense_truth | 1,022 ch | 2 | `fallback` | 0.00 | 0 |

The stubborn-pack wrapper confirmed 15/15 VRAM-GUARD truncation across 3 runs on the full stubborn pack; the subset mapped to this WO is the 7 where truncation is the *whole* story — there is no surviving signal for a scorer-axis or adjudication fix to credit. PROMPTSHRINK (#81) was measured (r4j) against this cluster and moved nothing — shortening the prompt freed ~7k chars but the answer itself plus the 108-path catalog plus routing rules still hit the guard on dense_truth replies.

SECTION-EFFECT Phase 1 adjudication placed these 7 cases in the `truncation_starved` bucket: neither a value-axis nor a path-axis scorer relaxation would credit them, because no emission survives. The LLM call returns nothing; the `fallback` / `rules_fallback` methods fire because the JSON parser has nothing to consume.

## The mechanism (observed, not inferred)

1. System prompt assembled in `_build_extraction_prompt` ≈ 29.7k chars ≈ 8.5k tokens (PROMPTSHRINK observation, r4j).
2. Narrator reply appended, 700–1,030 chars. Tokenizes to ~180–280 tokens but dense with proper nouns, dates, and relation cues — each of which materially competes for attention.
3. `max_new_tokens` configured at 768 for dense sections (R3 Patch 3 landed 2026-04-18).
4. VRAM-GUARD caps total context at 8,192 tokens on the RTX 50-series local model. Prompt + reply + headroom-for-generation exceeds that ceiling on every dense_truth call, so generation either (a) truncates mid-JSON and parse fails into `rules_fallback`, or (b) returns empty and falls through to the no-op `fallback` path.
5. Elapsed times (39–50s per case) confirm the model is running the full forward pass before the clamp cuts it off — this is not a timeout, it's a context-window truncation.

All three agents (Claude / ChatGPT / Gemini) independently flagged the same mechanism during the 2026-04-19 / 04-20 synthesis. The fact that PROMPTSHRINK didn't move the cluster indicates the lever to pull is not the prompt body — it's either the context budget or the pipeline shape.

## Non-goals

- Not re-running PROMPTSHRINK with different caps. That lever was measured, closed, and shelved (see `CLAUDE.md` changelog entry for 2026-04-20).
- Not changing the VRAM-GUARD 8,192 ceiling. The ceiling is a hardware-accuracy trade-off owned by the model-serving layer; this WO treats it as a fixed constraint.
- Not adding new ground-truth labels for the 7 cases. Phase 1 adjudication already labeled them `truncation_starved`, which the scorer treats as `alt_defensible_paths`-ineligible. That judgment is not revisited here.
- Not swapping the local model. Hermes 3 / Qwen evaluation is sequenced *after* SPANTAG signoff per SPANTAG spec Appendix A. This WO is about lane architecture, not model selection.
- Not writing code. This is a spec. The first experiment Chris will run after reading it comes from §Proposed first experiment.

## Scope

**In scope for this WO:**

- Enumerate the seven candidate interventions for the truncation lane, with their costs, risks, and the evidence that would falsify each.
- Propose the first experiment — the one that's (a) cheapest to run, (b) most informative about which of the remaining interventions are worth pursuing, and (c) does not foreclose any downstream option.
- Define the success metric, a disposition rule, and the ship-vs-shelve gate.

**Explicitly out of scope:**

- Implementing anything. A separate WO (likely `WO-EX-TRUNCATION-LANE-02`) will land whichever lane architecture survives the first experiment.
- Changing any existing feature flag. The seven flags in `server/code/api/flags.py` are untouched.
- Touching the TWOPASS or SPANTAG scaffolds.

---

## Interventions — enumeration

Seven options, ranked by expected information-gain per unit of implementation cost.

### Option A — Split-then-merge (decompose-then-aggregate)

Detect that a reply is `dense_truth` (via noise_profile tag or an inline heuristic — long reply, ≥ 3 distinct entity mentions, ≥ 2 relation cues). When detected, split the reply into 2–3 sentence-grouped chunks and call the extractor once per chunk with the *same* `current_section` / `current_target_path` / era / pass / mode. Concatenate items from all chunk responses before post-extraction validators run.

- **Cost:** moderate. One new function in `extract.py` (chunker + call-fan-out + item-merge). ~80–150 LOC. Observable via `[extract][lane=split_merge]` log tag.
- **Risk:** item duplicates across chunks. Mitigated by the existing TURNSCOPE filter + `_dedupe_items`. The risk surface is well-understood (r4h already de-duped children across compound answers).
- **Latency:** 2–3× per-case wall-clock. A dense_truth case already takes 39–50s; split-merge puts it at 90–120s. CLAUDE.md's 90s timeout would need a bump to 180s for this lane only.
- **What it falsifies:** if split-merge doesn't move the 7 cases, the truncation ceiling isn't the whole story — a content-comprehension limit is also in play.
- **Evidence for feasibility:** case_060 (compound spouse + children) already works because the extractor's compound-detection path essentially does this informally. Split-merge formalizes and extends the pattern.

### Option B — Lane-specific minimal prompt

Define a dedicated dense_truth prompt that strips everything except: JSON format + the single rule block most relevant to the active target + 2 universal-anchor few-shots. Aim for a ~2k-char prompt vs. today's 29.7k. Legacy catalog presentation is replaced by a 3–5-path allowlist derived from `current_target_path`.

- **Cost:** high. Requires re-deriving an allowlist from the target path, authoring a new prompt, and validating it doesn't leak into other lanes. ~200 LOC + a prompt-regression harness.
- **Risk:** high. The 108-path catalog is load-bearing across the non-dense-truth lanes — a 3-path allowlist wins truncation but loses the same-entity elaboration discipline. Likely to create a new class of `schema_gap` failures on the lane where dense_truth and mixed_narrative overlap (the gray zone).
- **What it falsifies:** if this doesn't move the 7 cases with a much smaller prompt, raw context isn't the constraint — attention-saturation within the remaining context is.
- **Flag-ability:** easy (`HORNELORE_DENSETRUTH_LANE=1`).

### Option C — Output-only truncation ceiling lift

Raise `max_new_tokens` from 768 to 1,536 for dense_truth calls only. The input side is unchanged; this gives the model more room to actually *emit* the JSON it's trying to construct.

- **Cost:** trivial. 10-line conditional in the max-tokens dispatcher.
- **Risk:** moderate. VRAM-GUARD ceiling is 8,192 *total*; if input prompt is already at 8.0k, raising output cap from 768 to 1,536 requires input < 6,656 tokens — which we don't have margin for. This option is only viable in combination with at least a partial prompt shrink (PROMPTSHRINK flag ON + max_new_tokens 1,536).
- **What it falsifies:** if this doesn't move the 7 cases, the bottleneck is the attention window under the input prompt, not the generation budget.
- **Flag-ability:** very easy; reuses existing PROMPTSHRINK flag.

### Option D — Two-pass gated by dense_truth

Re-enable `HORNELORE_TWOPASS_EXTRACT=1` for dense_truth-noise calls only. Pass 1 (span tagger) runs with a short prompt and emits JSON tags. Pass 2 (field classifier) runs with the schema catalog but against the tag inventory, not the raw reply.

- **Cost:** low. The two-pass scaffold already exists (`_extract_via_twopass` at extract.py:~2300). New code = conditional dispatch + lane tag.
- **Risk:** moderate. TWOPASS was measured on the master and kept OFF because it regressed on some classes. Lane-gating to dense_truth only reduces the blast radius but adds a two-writer problem (TWOPASS + SPANTAG will both be reading the same lane-selection plumbing).
- **What it falsifies:** if TWOPASS lane-gated moves the 7 cases, SPANTAG's value for this cluster is question — SPANTAG may be solving a problem TWOPASS also solves, just more elegantly. If it *doesn't* move them, then SPANTAG's Pass 1 NL-inventory design (which is lighter than TWOPASS Pass 1) is unlikely to either.
- **Interaction with SPANTAG:** direct. Per SPANTAG spec, TWOPASS is retired once SPANTAG ships default-on. Running TWOPASS lane-gated before SPANTAG signoff tests the "two-pass as such is the right shape" hypothesis cleanly.
- **Flag-ability:** easy. Add dispatcher condition on `noise_profile=="dense_truth"`.

### Option E — Catalog pruning by section

When `current_section` is set, prune the 108-path catalog to only paths whose prefix matches the section's local ontology (e.g., `grandparents.*` for `subTopic="great_grandparents"`). Keep the full catalog for unknown sections. This is a softer form of Option B — the rule blocks and few-shots are preserved, but the catalog shrinks.

- **Cost:** low-moderate. ~50 LOC + a section→prefix mapping table. Existing `_promptshrink_topics_for_section` provides half the wiring.
- **Risk:** moderate. Same-entity elaboration sometimes emits outside the active section's prefix (e.g., `parents.birthPlace` during a grandparent discussion). Need an allowlist, not a strict prefix filter.
- **What it falsifies:** if this doesn't move the 7 cases, the catalog presentation isn't the bottleneck — the reply itself is saturating the attention window.
- **Flag-ability:** easy (`HORNELORE_CATALOG_PRUNE=1`).

### Option F — Model-swap lane gate

When `noise_profile=="dense_truth"`, route the call to a larger or context-extended model. Hermes 3 is under review; Qwen 14B has an 8k context baseline with extended variants. Keep the 8B local model as the default for the other 97 cases.

- **Cost:** depends on serving. If a second model is already loaded, the cost is a router stub. If not, the cost is loading + maintaining a second VRAM-resident model — probably a hardware constraint on the RTX 50-series.
- **Risk:** low on correctness, high on latency and hardware sustainability.
- **What it falsifies:** if a 14k-context model moves the 7 cases, the RTX 50-series 8k-context local model is the ceiling. This confirms the truncation hypothesis absolutely but raises the question of whether the production target is the 8B or something else.
- **Blocker:** sequenced after SPANTAG per CLAUDE.md §Deferred. This option is NOT part of the first experiment.

### Option G — Refused-answer fallback (soft quit + ask-for-clarification)

When the extractor returns `fallback` after a dense_truth reply, emit a `clarification_required` envelope asking the narrator to break the answer into smaller pieces. No extraction happens; the UI tier handles the follow-up.

- **Cost:** low. The envelope shape already exists (STT-LIVE-02 `clarification_required`). New code = detect the truncation case + build the envelope.
- **Risk:** low on correctness (nothing is written), high on UX (the narrator may perceive Lori as "giving up" on rich answers).
- **What it falsifies:** nothing about the extractor. This is a product-level fallback, not a diagnostic.
- **Why it's still listed:** if none of A–F ships, G is the honest user-facing disposition — tell the narrator the system couldn't handle the dense answer in one pass and ask for a retry, rather than silently emitting `fallback` with 0 items.

---

## Proposed first experiment

**Run Option A (split-then-merge) lane-gated to `noise_profile=="dense_truth"`, behind a new flag `HORNELORE_SPLIT_MERGE=1`, default OFF.**

Rationale:

1. It's the cheapest option that changes the pipeline shape (not just the prompt body or the output budget).
2. It's the most information-rich: if it moves the 7 cases, we know the ceiling is input context — and Option C becomes redundant. If it doesn't move them, we know something other than truncation is in play (likely entity-density attention saturation), and Options B/D/E rise in priority.
3. It's reversible with a single env flip.
4. It does not touch SPANTAG or TWOPASS. Those lanes continue to evolve in parallel.
5. It is measurable with the existing eval harness — the WO-QB-EVAL-EXPAND-01 axes (`stubborn_pack_summary.truncation_starved`, `method_distribution`, `truncation_rate`) will show the delta directly.

### Experiment shape

- **Intervention:** chunk any reply whose `noise_profile=="dense_truth"` or whose character length exceeds 600 into 2–3 sentence-grouped chunks (split on `. ` boundaries, merge small tail chunks). Call `_extract_via_singlepass` per chunk with identical `current_section` / `current_target_path` / era / pass / mode. Concatenate items, then run the normal post-extraction validators + TURNSCOPE filter.
- **Flag:** `HORNELORE_SPLIT_MERGE=1`. Default OFF. Pair `split_merge_enabled()` helper into `flags.py`.
- **Log tag:** `[extract][lane=split_merge]` for the dispatcher + `[extract][lane=split_merge][chunk=i/N]` for each call.
- **Timeout:** raise per-case timeout from 90s to 180s when the flag is on. Keep 90s otherwise. Document in `CLAUDE.md` after the experiment runs.
- **Target pack:** the 7 cases in `stubborn_pack_summary.truncation_starved`.
- **Control:** r5a (flag off) vs. r5b-splitmerge (flag on, same 7 cases).

### Success metric

- **Primary:** ≥ 3 of 7 truncation-starved cases move from `overall_score=0.0` to `overall_score≥0.5` with the flag on.
- **Secondary:** 0 new `must_not_write` violations introduced anywhere in the 104-case master (the split-then-merge is not allowed to break the no-write contract).
- **Tertiary:** no regression in the non-dense-truth cases — the lane gate should be a no-op for the other 97 cases, which means master `pass_rate_v3` on the contract subset stays at ≥ r5a's 58.1% (36/62).

### Disposition rule

- **≥ 3 of 7 move:** land a lane-architecture WO (`WO-EX-TRUNCATION-LANE-02`) that productionizes split-merge + the timeout bump. Keep the flag and consider defaulting it ON after one more eval cycle confirms the 3-of-7 holds.
- **1–2 of 7 move:** the lever is directionally right but not sufficient. Pair with Option C (output-only ceiling lift, which is safe to layer on) and re-run. If the combined pair still shows only 1–2, shelve split-merge and move to Option D (lane-gated TWOPASS).
- **0 of 7 move:** truncation is not the whole story. Split-merge doesn't ship. Move to Option D as the next experiment.
- **Any secondary/tertiary violation:** roll back immediately, regardless of primary. The no-write and no-regression contracts are non-negotiable.

## Interaction with SPANTAG

Both WOs touch the same 7 cases in principle. The coordination rule:

1. SPANTAG ships first (per the active sequence in `CLAUDE.md` / SECTION-EFFECT spec). Its primary sub-pack is the 4 dual_answer_defensible cases (008, 009, 018, 082) — *not* this cluster.
2. After SPANTAG lands default-on, re-measure the truncation-starved 7. SPANTAG Pass 1's NL-tag inventory is ~20% smaller than the current single-pass prompt body, which may partially absorb the truncation ceiling even without a dedicated lane.
3. If SPANTAG's re-measure still shows 0–2 of 7 moved, run this WO's Option A experiment against the post-SPANTAG baseline (not r5a).
4. If SPANTAG moves ≥ 3 of 7 incidentally, this WO is deprioritized — file a ticket to re-measure after 30 days and close unless the cluster re-emerges.

## Deliverable

This WO delivers the spec you are reading. There is no code, no flag, no eval run. The next WO (`WO-EX-TRUNCATION-LANE-02`) will exist only if §Proposed first experiment is greenlit, runs, and the disposition rule says ship.

## Changelog

- 2026-04-20: Created. Captures the 7-case cluster, enumerates 7 interventions, proposes split-then-merge as the first experiment, and defines the disposition rule. Parallel track to SPANTAG — does not block.
