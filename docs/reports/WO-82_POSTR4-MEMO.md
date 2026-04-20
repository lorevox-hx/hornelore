# WO-82 — Post-R4 Memo and R5.5 Bridge

**Author:** Claude (LOOP-01 R4 cleanup closeout)
**Date:** 2026-04-20
**Status:** Canonical post-R4 strategy bridge. Written from **r4i** metrics. r4j was measured and rejected — see `POST-R4-BASELINE-LOCK.md`.

## 1. Where R4 landed

R4 was a tactical cleanup phase. The goal was to lift the topline and close specific known-bad routing patterns without architectural change. It did that modestly.

- **Topline:** 55 / 104 (52.9%) at r4i, up from 52 / 104 at R3 close. Four-point absolute lift across R4a-i.
- **Contract guard:** v3 34/62, v2 31/62, must_not_write **0.0%** sustained across r4g → r4h → r4i. The regression guard is green.
- **WOs closed inside R4:**
  - **#72 / WO-EX-TURNSCOPE-01** — case_094 pass restored, 060/062 repaired, must_not_write driven to zero.
  - **#67 / WO-EX-PATCH-H-DATEFIELD-01** — case_011 and case_012 flipped green under legacy prompt at r4i.
  - **#68 / case_053 wrong-entity** — disposition memo written, deferred to R5 Pillar 2 as architectural (OTS/entity-binding), not tactical.
  - **#81 / WO-EX-PROMPTSHRINK-01** — landed behind `HORNELORE_PROMPTSHRINK=1`, measured at r4j, **not adopted**. Closed as "no-move / regressed-by-one". Flag left in-tree for possible pairing with SPANTAG.
- **WOs still open from R4:** **#63** (should_pass drift audit, retag `guard_false_positive` → `scope_escape` now that #72 is closed). Not a shipping blocker but a prerequisite for calling R5.5 results "clean".

## 2. What R4 could not move

Three cliffs sat still across the whole phase:

- **dense_truth: 0 / 8 passed.** Avg score 0.083. Eight cases, all failing on schema_gap or noise_leakage, large/medium chunks with compound same-turn bindings.
- **large chunks: 0 / 4 passed.** Avg score 0.242.
- **Stubborn-15 frontier:** `case_008, 009, 017, 018, 053, 075, 080-087, 088`. At r4j stability (3 runs, PROMPTSHRINK on), **0 / 15 stable_pass, 15 / 15 stable_fail, 15 / 15 truncated in at least one run**.

Every stubborn case hit VRAM-GUARD's 8192-token ceiling at least once. Prompt-verbosity is not the bottleneck on the frontier — truncation is. The interesting corollary: every R4 lever that reduced *input* tokens (PROMPTSHRINK being the headline one) did nothing for these cases because the *output* was still getting chopped, or the input was already not the constraining factor.

## 3. Architectural read across the whole system

Quick orientation, because #89's context packet asked for it. The Hornelore pipeline:

- **Interview loop** — `chat_ws.py` + `prompt_composer.py` compose narrator-specific prompts from `data/prompts/question_bank.json` (36 sub_topics, each with `extract_priority` field list). Phase-aware composer picks the sub_topic; life-spine derivations drive phase gating (`server/code/life_spine/`).
- **Extraction** — `server/code/api/routers/extract.py`. Canonical catalog of ~108 extractable field paths hardcoded (lines 88-302). `_extract_via_singlepass` → LLM (llama.cpp) → `_parse_extraction_response` → guardrail stack: `_apply_narrator_identity_subject_filter` → `_apply_birth_context_filter` → `_apply_turn_scope_filter` (r4h) → `_apply_write_time_normalisation` (Patch H) → `_apply_semantic_rerouter` → `_apply_claims_validators` → rules fallback.
- **Truth pipeline** — four layers: shadow archive → proposal → human review → promoted truth. Writes land in shadow; only review promotes. `HORNELORE_TRUTH_V2=1` is on.
- **Projection** — Kawa River View projection exists but is deferred to R5. We do not write into the public projection until review promotes.
- **Eval harness** — `scripts/run_question_bank_extraction_eval.py` (104 cases, live API mode) plus `scripts/run_stubborn_pack_eval.py` (15 frozen cases, 3 runs, VRAM-GUARD truncation attribution from api.log delta). Contract uses v3 truth zones (must_extract / may_extract / should_ignore / must_not_write) with v2 field-average as a legacy guard.
- **Feature flags:** `HORNELORE_TRUTH_V2=1` (on), `HORNELORE_TWOPASS_EXTRACT=0` (off — old abandoned lane, not the SPANTAG two-pass), `HORNELORE_PROMPTSHRINK=0` (off post-r4j).

The architecture's load-bearing bet is: **the guardrail stack is cheap and the LLM is expensive**. Everything the rails can fix after LLM emission is preferred over making the LLM smarter. R4 kept spending on rails. The cliffs at dense_truth / large / stubborn-15 are telling us the rails can't reach — the LLM is emitting the wrong *shape*, not just the wrong *value*, and the rails only edit values.

## 4. Why R5.5, not R5

R5 as originally scoped was Pillar 1 (citation grounding) + Pillar 2 (entity-role binding) + Pillar 3 (long-context handling). Three pillars, three architectures, one roadmap. That was right at the time.

After R4, the order changed. The stubborn frontier tells us:

- **Truncation is the common root cause.** Fix the shape of what the LLM emits, and the truncation pressure drops.
- **Provenance is a precondition, not a feature.** We cannot measure whether the rails are correctly filtering "hallucinated value vs real-but-wrongly-routed value" without a span-level link from emission to source text.
- **Entity binding (Pillar 2) is ill-posed until we have provenance.** You cannot debug "the model bound Janice to the wrong role" if you don't know whether the model was even reading the Janice sentence.

So R5.5 = **citation grounding first**, via SPANTAG. Pillars 2 and 3 stay deferred. R5.5 delivers the primitive (span-offset provenance per emitted item) that R6 Pillar 2 needs anyway.

## 5. The SPANTAG bet (two-pass)

Full spec in `WO-EX-SPANTAG-01_Spec.md`. One-paragraph frame here:

Separate **what is said** from **what it means**. Pass 1 asks the LLM to tag evidence in the narrator reply using a narrow natural-language inventory (`person`, `relation_cue`, `date_text`, `place`, `organization`, `role_or_job`, `event_phrase`, `object`, `uncertainty_cue`, `quantity_or_ordinal`) with substring-invariant tags. The tag set is small enough for zero-shot 8B and never mentions our schema. Pass 2 takes Pass 1's output plus the question-bank `extract_priority` and the schema, and binds tagged evidence to field paths, normalizes, and decides what to write. Write-gating moves into Pass 2.

Why this helps:

- **Pass 1 output is cacheable.** Re-asking the same question with a different extract_priority re-runs Pass 2 only. Net LLM tokens per turn drop.
- **Pass 1 is a much smaller problem.** Ten NL tag types, no dotted field paths, no schema knowledge required — the kind of thing a quantized 8B is actually good at.
- **Pass 2 is doing what the rails already do today.** Which means it's cheap to prototype, and the rails become *redundant* rather than *load-bearing* once Pass 2 is reliable.
- **Truncation gets easier.** The Pass 1 output is not `"re-emit the whole reply with span tags"` — it's a small JSON array of `{type, text, span: [start, end]}` entries. Output budget stays small even on long inputs.

## 6. Explicit non-goals for R5.5

- Not switching models. Llama 3.1 8B Instruct INT4 stays.
- Not rewriting the guardrail stack. Pass 2 uses it.
- Not adopting PROMPTSHRINK as default. Flag stays off. If SPANTAG's Pass 1 input grows, we revisit.
- Not touching the truth pipeline / projection / review UI.
- Not claiming SPANTAG will close the dense_truth cliff on its own. Two-pass decoupling plus provenance are a prerequisite for closing dense_truth, not the cure.

## 7. Conditional lanes (defer, do not start)

- **KORIE-style staged-pipeline** (detection → OCR → IE): referenced in research synthesis. **Only consider if SPANTAG Phase 1 delivers ≥20% topline lift or closes ≥3 of the stubborn 15.** Otherwise the staged-pipeline cost is not justified at our scale.
- **Hermes 3 / chat-template A/B:** deferred behind SPANTAG. Chat-template parity is a prerequisite (ChatML vs Llama-3 template). No A/B until SPANTAG lands and gives us a stable baseline to measure against.

## 8. Acceptance for "R4 is done"

- ✅ r4j measured, rejected, documented. `WO-EX-PROMPTSHRINK-01` Disposition section written.
- ✅ r4i locked as active baseline. `POST-R4-BASELINE-LOCK.md` written.
- ✅ This memo written.
- ✅ `WO-EX-SPANTAG-01_Spec.md` rewritten to two-pass.
- ⏳ CLAUDE.md changelog updated (same PR).
- ⏳ #63 should_pass drift audit — not blocking R5.5 start, but blocking R5.5 result credibility.

Once the first four are in and CLAUDE.md is updated, R4 is closed and R5.5 Phase 1 is the active work.

## 9. References

- `WO-EX-PROMPTSHRINK-01_Spec.md` — Disposition section, r4j flip audit.
- `POST-R4-BASELINE-LOCK.md` — the lock.
- `WO-EX-SPANTAG-01_Spec.md` — next execution spec.
- `docs/reports/master_loop01_r4i.json` / `.console.txt` — baseline metrics.
- `docs/reports/stubborn_pack_r4j_stability.console.txt` — 0/15 pass, 15/15 truncation.
- `docs/reports/loop01_research_synthesis.md` — Kiwi-LLaMA, UniversalNER, KORIE references behind SPANTAG.
- `docs/reports/WO-EX-CASE053-DISPOSITION.md` — #68 architectural deferral.
