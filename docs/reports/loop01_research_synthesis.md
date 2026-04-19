# LOOP-01 Research Synthesis → Hornelore/Lorevox R5+

**Date:** 2026-04-19
**Scope:** All PDFs in `mnt/uploads/` as of 2026-04-19
**Goal:** Map each paper's contribution onto concrete R5+ decisions for the life-stories-to-rigid-schema extraction task.

Hornelore's R4 failure inventory (for reference):
- schema_gap: 29
- llm_hallucination: 14
- field_path_mismatch: 14
- noise_leakage: 12
- guard_false_positive: 4

---

## Part 1 — Your existing synthesis: confirmed, with nuance

### 1.1 Extraction vs other NLP tasks
Source: Pietrobon et al., *The Many Tongues of Meaning* (SSRN preprint).

Confirmed. Four-task taxonomy (classification, extraction, translation, summarization). We are in extraction, with classification as a side-effect of field dispatch. The paper specifically flags that extraction "supports alignment with common data models" and that precision/recall tradeoffs should be "guided by study aims, with safety-focused research often prioritizing sensitivity." For us, non-safety narrative extraction, the dual is: prioritize precision, because a false write contaminates the schema permanently. This matches our R4 tilt toward guard-heavy design.

### 1.2 Domain-Specific Adaptation
Source: Wind et al., *SteuerLLM* (FAU Erlangen + DATEV).

Confirmed. The block expansion strategy (insert trainable Transformer layers at regular depth intervals while freezing base parameters) is real and impactful — a 28B SteuerLLM beats 600B general-purpose models on legal reasoning. But this is a **pretraining-level** intervention trained on 6.1B domain tokens using 16 H100 nodes. It is not actionable in R5.

What IS actionable: the paper's thesis that **domain data + architectural adaptation beats parameter scale**. This directly justifies our continued investment in the few-shot library + schema curation + guard refinement over upgrading to a larger base model. Stay the course.

Deferred to V6+: if we ever decide to train a Hornelore-specific model, block expansion is a documented method. Not now.

### 1.3 Iterative Labeling (ReLabel)
Source: Tong Guo, *A Unified Framework for LLM-based ReLabel Method*.

Confirmed, with one mechanism not in your summary: the LLM correction step is **constrained to binary classification** — "the candidates are just 2 labels: the previously annotation and the one predicted by the trained model." This is cheap to implement and directly applicable to our open eval-harness audit (#63).

**Concrete steal for us:** the 24 `[GAP]` cases where `currentExtractorExpected=false` are stale from before the R2/R3/R4 improvements. Run an LLM-as-judge pass in ReLabel binary mode — for each GAP case, present {original expectation, current R4 extraction} and ask which is more correct given the narrator answer. Cases where the judge flips to "current" move to `currentExtractorExpected=true` without bulk manual review. This should also close some of the eval-harness drift that currently makes the `should_pass` prediction noisy.

### 1.4 Morphology-Aware Tokenization
Source: Držík & Kapusta, *Slovak Morphological Tokenizer (SKMT)* (Expert Systems With Applications).

Not applicable to English life stories. BPE is adequate for us. Relevant only if we ever localize to morphologically rich languages (Slovak, Czech, Polish, Turkish, Hungarian). The paper's finding — root morpheme preservation gives +12.49% on semantic similarity, +3.23% on QA — scales only for synthetic languages.

Skip until we have a non-English deployment.

### 1.5 Miniaturization Trend
Source: mentioned in several papers (SteuerLLM, SKMT intro, LMmeetnlp).

Descriptive, not prescriptive. Validates our choice to run locally on reasonable hardware. No action.

### 1.6 Context Engineering — Four-Layer Stack + CCM
Source: Mahaptra, *How Regulated Financial Institutions Will Tame Agentic AI Through Architectural Determinism* (Fiducia white paper, March 2026).

Critical caveat your summary didn't capture: **this is a banking/regulatory white paper with heavy SR 11-7, EU AI Act, NYDFS, and SEC translation sections.** The "Four-Layer Context Stack" and "Context Compliance Manifest" are proposed governance primitives for regulated agent deployment, not extraction-specific research. They are useful framings, but the paper's empirical content is limited.

Two portable insights:

**Deterministic Sandwich** (Ch. 3) — put deterministic checks BEFORE and AFTER the LLM. Our `_apply_claims_validators` is the "after" half. We have very little "before" — our prompt is mostly generic with few-shots, not field-scope-gated on detected cues. An upstream "field-scope filter" that restricts writable field paths based on regex cue detection on the narrator answer would reduce schema_gap (29 cases) by preventing the model from even attempting writes to irrelevant fields. This is a medium-effort R6 candidate.

**Context Compliance Manifest** (Ch. 2.3) — an audit record documenting what context was provided and why. Our per-case `raw_items` + `field_scores` outputs are already a partial CCM. Adding a "context trace" block (which few-shots fired, which cues matched, which schema subset was considered) would make our eval logs self-auditing and directly supports the eval-harness audit (#63).

---

## Part 2 — What your synthesis is missing

### 2.1 Self-Aware Language Models — directly addresses our 14 `llm_hallucination` failures
Source: Tiwari & Gupta (Microsoft CoreAI + UT Medical Branch), *Self-Aware Language Models: A Taxonomy and Evaluation of Epistemic Uncertainty and Hallucination Mitigation* (Research Square, Jan 2026).

Five-mechanism taxonomy for knowledge-gap awareness:
1. **Reflective prompting** — we have partial via prompt structure
2. **Uncertainty Quantification** — token/span/response-level confidence estimation. We have **zero** of this today.
3. **Selective Prediction / Abstention** — model opts out when uncertainty is high. Partial via our null_case category, but we rely on prompt-level instructions ("write null if unsure") rather than measured model confidence.
4. **Retrieval-based Verification** — external source confirmation. We have none.
5. **Confidence Calibration** — align confidence with factual correctness probability. We have none.

**Highest-leverage quick win:** have the extractor emit `{value, confidence}` per field write and threshold at validator time. A `confidence < 0.75` write is either dropped or demoted to `clarify_before_write`. This targets the 14 llm_hallucination cases directly, and is compatible with our current outlines-style constrained output.

**R6 candidate. One-sprint effort.**

### 2.2 Sensors/URT paper — the closest architectural cousin to Hornelore we've seen
Source: Huang et al., *Emergency Operation Scheme Generation for Urban Rail Transit Train Door Systems Using Retrieval-Augmented Large Language Models* (Sensors, March 2026).

Pipeline: unstructured maintenance narratives + dispatch logs + regulations → schema-compliant structured emergency operation schemes. This is the same architectural shape as Hornelore (unstructured narrator answers → schema-compliant extraction).

Their full-stack results on 776 real incidents:
- SchemaPass: 0.88
- RoleAcc: 0.91
- CiteCov: 0.73
- UsableAns: 0.83

Baseline comparisons:
- Pure LLM: UsableAns 0.15
- RAG-only: UsableAns 0.26
- Their full stack: UsableAns 0.83 (**3.2× over RAG-only**)

Their recipe vs our current state:
| Component | Huang et al. | Hornelore |
|---|---|---|
| Hybrid dense + BM25 retrieval | Yes | No |
| Cross-encoder reranker | Yes | No |
| Fine-tuned generator with structured objectives | Yes (schema + role + citation) | Partial (schema only, via validators) |
| Citation grounding | Yes | **No** |
| Multi-dimensional eval | Schema/Role/Cite/Usable | Single field_score |

**Most tractable steal:** citation grounding. Have the extractor emit `{value, startChar, endChar}` alongside each field write, pointing to the span in the narrator answer. Validator rejects writes whose cited span isn't actually in the answer, or isn't semantically consistent with the value. This addresses llm_hallucination (14) and field_path_mismatch (14) simultaneously — both buckets have the same root cause: the model writing something it didn't see or wasn't said.

This is a strong R5.5 candidate. The eval-harness addition is small (parse and validate char spans). The prompt addition is one paragraph. The validator addition is a substring check.

### 2.3 Thunder-NUBench — explains WHY Patch F regressed
Source: So et al. (SNU), *Thunder-NUBench: A Benchmark for LLMs' Sentence-Level Negation Understanding* (Findings of ACL 2026).

Formal typology of negation:
| Dimension | Types |
|---|---|
| Scope | Clausal (sentential) / Subclausal (constituent/local) |
| Form | Morphological / Syntactic |
| Target | Verbal / Non-verbal |

Key empirical finding: LLMs systematically conflate negation + its scope with non-negation, **especially for subclausal + non-verbal negation**. Performance degrades even on modern LLMs when negation is present.

Our three Patch F regressions are exactly subclausal:
- case_038 ("I don't have any big health stories to tell") — non-verbal, subclausal (negates object phrase)
- case_056 ("Never had any serious surgeries") — clausal-verbal with "never" + object
- case_100 ("I wasn't a joiner of things" + hedge clauses) — standard clausal, but preceded by "I suppose the church counted"

The narrowed Patch F (now requires denial+contrast within the SAME sentence, following Standard Negation's clausal-verbal definition) is in the right direction per the Thunder-NUBench taxonomy. **But the paper confirms subclausal cases are genuinely hard for LLMs** — expect residual false positives on hedging language like "I suppose X counted, but I wasn't really a Y." Plan for a small long tail even after Patch F narrowing lands.

### 2.4 Format Tax — prompt-level cost dominates
Source: Tam et al., *Let Me Speak Freely? A Study on the Impact of Format Restrictions on Performance of LLMs*.

Already covered in yesterday's DCCD review. Recap: the "prompt says produce JSON" costs more accuracy than the decoder-level grammar masking. Fix: 2-turn (reason freely, then format). **Most applicable to our R5 prompt shrink task.** When we shrink, bias the shrink to keep reasoning room and only add format directives at the tail.

### 2.5 DCCD — defer to V5+ for dense_truth specifically
Source: Reddy et al., *Draft-Conditioned Constrained Decoding for Structured Generation in LLMs* (Feb 2026).

Already covered. Recap: training-free two-stage draft-then-constrain. Gains concentrated at 1B-1.5B models. Useful as a V5+ option for dense_truth cases (currently 0/8) where projection tax MIGHT be a contributor; not a fit for our common case.

### 2.6 IPCD — too heavy, defer indefinitely
Source: Yodah (Quinnipiac), *Integer Programming-Constrained Decoding for Reducing Constraint-Based Hallucinations in LLMs*.

Mixed-integer linear programming at decoding time. 32-57% reduction in constraint violations on health risk prediction (stroke, diabetes). Adds massive latency — IPCD solves an MILP per token step for infeasible constraint regions. Our constraints are discrete (field path, field type) not numerical; IPCD's sweet spot is quantitative constraints like "sum of X must be between L and U." Not applicable.

### 2.7 Order-to-Space Bias (OINL) — warning for our few-shot library
Source: Zhang et al., *Order Is Not Layout: Order-to-Space Bias in Image Generation*.

Text-to-image paper but the general principle — **mention order spuriously determines downstream structure** — is a transferable warning. Their finding: with spatially neutral prompts, T2I models follow mention order to place the first-mentioned entity on the left ~70-90% of the time, even contradicting grounded cues.

Analog for us: if our few-shots consistently list one family role first (e.g., mother before father, or parents before siblings), the extraction model may default to writing that role first even when the narrator didn't mention it. **Quick audit for R5:** sample 10-15 random few-shots, check role-order consistency, and if skewed, add reverse-order variants. One-hour effort. Unlikely to be a huge fix but cheap.

### 2.8 LMmeetnlp — validates our paradigm choice
Source: Qin et al., *Large Language Models Meet NLP: a Survey* (Frontiers of Computer Science 2026).

Taxonomy: parameter-frozen (zero-shot, few-shot) vs parameter-tuning (full, LoRA/PET). The survey places IE in the few-shot bucket: "providing exemplars could help LLMs better understand the task and follow the problem-solving steps, especially in tasks requiring structured outputs and clear format adherence."

Our few-shot library IS the consensus direction for IE. No change; validation.

### 2.9 SourceData-NLP — QC framing + correction-count metric
Source: Abreu-Vicente et al., *Integrating Curation into Scientific Publishing to Train AI Models* (Bioinformatics 2026).

Two-step QC with author-in-the-loop. Their empirical distribution on 1258 manuscripts: 54.1% needed 0 corrections, 17.2% needed 1, 4.9% needed 6+. This is roughly the shape we'd see if we had human review of our eval cases.

**Portable idea:** add per-case **correction count** to our scorer — how many distinct guard fires, how many validator overrides, how many aliases invoked. Single-number case scores compress this. Breaking it out would let us see whether R5/R6 reduces the number of distinct interventions-per-case (a signal that the base model is behaving better) vs just papering over the same hallucinations with more guards (a signal that we're accumulating debt).

Low-effort R5 addition to the scorer.

### 2.10 Geometric Semantics — not actionable
Source: anonymous working draft, *Geometric Semantics for Legal Reasoning*.

Theoretical paper proposing quantum-inspired vector/tensor model for legal norms. Interesting framing (rules as vectors, standards as metric tensors) but no implementation, no benchmark, no NLP applicability. Skip.

### 2.11 Shysheya thesis — Chapter 5 (JoLT) marginally relevant
Source: Shysheya, *Advances in Few-Shot Learning for Image Classification and Tabular Data* (Cambridge PhD thesis, March 2025).

Most of the thesis is image classification / FiLM adapters. Chapter 5 (JoLT: Joint Probabilistic Predictions on Tabular Data Using LLMs) has a missing-data imputation prompt pattern that's tangentially relevant to our `null_case` / `clarify_before_write` categories. Not urgent — our null handling is adequate and this is a small bucket in our eval.

Defer.

---

## Part 3 — R5+ action map (revised)

Your current R5 plan (in-flight):
1. Patch F narrowing — **CODE DONE, awaiting eval**
2. D/H ordering fix — pending
3. Prompt shrink — pending

Research supports all three. With capacity, add:

**R5.5 — Citation grounding (from Sensors/URT)**
Have extractor emit `{value, startChar, endChar}` per field write. Validator: reject writes whose span isn't a substring of narrator answer. Directly targets llm_hallucination (14) + field_path_mismatch (14). Estimated cost: 1-2 days code + prompt paragraph + eval harness update.

**R5.6 — Correction-count metric + per-dimension eval breakout (from SourceData + Sensors)**
Scorer emits per-case {guard_fires, validator_overrides, aliases_invoked} in addition to field_score. Multi-dimensional dashboard: SchemaPass / FieldPathAcc / GuardNetValue / UsableAnswer (analog to Huang et al.'s SchemaPass/RoleAcc/CiteCov/UsableAns). Reduces eval-harness noise (#63).

**R5.7 — Few-shot order audit (from OINL)**
One-hour review of few-shot role order. Add reverse-order variants where skewed.

**R6 candidate — Selective abstention + confidence calibration (from Self-Aware LM)**
Emit `{value, confidence}` per field; threshold at validator time. Targets llm_hallucination (14) directly. One-sprint effort.

**R6 candidate — Upstream field-scope filter (from Architectural Determinism / Deterministic Sandwich)**
Regex cue detection pre-filters which field paths the model is allowed to write. Targets schema_gap (29) by preventing attempts against irrelevant schema subsets. Medium effort.

**R7+ — ReLabel binary judge for eval-harness drift (from ReLabel)**
For each `[GAP]` case, LLM-as-judge binary flip of `currentExtractorExpected` based on R4 extraction vs original expectation. Closes eval-harness drift without bulk manual review.

**Deferred / not applicable**
- SteuerLLM block expansion (pretraining-level)
- SKMT morphology (English only)
- IPCD (wrong constraint type)
- DCCD (V5+ dense_truth only, already covered)
- JoLT (small bucket)
- Geometric Semantics (theoretical)

---

## Appendix: "we tried two-pass and it failed" revisited

Prior two-pass failure (32/62 → 16/62, `extract_multiple` collapsed 16/35 → 4/35) was due to **span stripping between passes** — Pass 2B saw abstracted spans, not the original narrator text. This is not the same architecture as DCCD, where the draft is kept verbatim in Step-2 context.

If we ever retry two-pass, the DCCD architecture (full draft preserved in context, constrained decoding masks on top) is the correct reference. But research this cycle does not strongly justify retry; single-pass improvements (R5, R5.5, R6) are higher-ROI.

---

*Sources: all PDFs in `/mnt/uploads/` read 2026-04-19. Cross-references to `docs/reports/loop01_r4_eval_readout.md`.*
