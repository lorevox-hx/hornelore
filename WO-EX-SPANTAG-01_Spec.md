# WO-EX-SPANTAG-01 — Span-tag output format for citation grounding

**Author:** Claude (LOOP-01 R4 cleanup, research-synthesis pass)
**Status:** STUB / DEFERRED — do NOT execute before r4i lands AND #81 (WO-EX-PROMPTSHRINK-01) is signed off AND merged. Queued against R5.5, not R4.
**Depends on:** #81 landed (prompt real estate freed up, catalog shrink in place so the span-tag instructions have room to breathe).
**Blocks:** R5.5 citation-grounding WO (this is the primitive it consumes).
**Not this WO's job:** fixing entity-role binding (#68 / R6 Pillar 2), shrinking the catalog (#81), touching the span-tagger or field-classifier layers.

## Problem framing

R5.5 citation grounding needs a way to link every emitted extraction back to a source-text span in the narrator's reply. The current extractor emits `{fieldPath, value, confidence}` triples with no structural link to the source — the value is a standalone string that may or may not appear verbatim in the reply. Two downstream consequences:

1. **No provenance for the write.** We can't cheaply show the user which sentence a fact came from, and we can't cheaply verify that a fact is sourced from the reply at all (which is the R5.5 primitive).
2. **Boundary drift.** The LLM will frequently paraphrase or normalize values in-flight ("Christmas Eve, 1939" → "Christmas Eve of 1939"), which our Patch H write-time normalisation chases via regex + holiday map. Every paraphrase mode is a new normalizer entry.

Kiwi-LLaMA (Hu et al., JAMIA 2026) evaluates an alternative output contract: the model emits the *input text itself* with `<span class='entity_type'>value</span>` wrappers around extracted values. Their pilot-test claim: *"this structure improves extraction consistency and boundary recognition,"* and it *"mitigates LLaMA's known sensitivity to instruction design."* They use it as a fair-comparison artifact against BERT sequence-labeling, not as a grounding primitive — but for our purposes, it *is* a grounding primitive for free: the span's position in the emitted text gives source offsets, and a value that isn't in the reply literally cannot be wrapped.

## Scope

Single, well-contained change: the extractor's output contract and its downstream parser. Nothing else moves.

**In scope:**
- New output contract: LLM emits the narrator reply text with span-tag wrappers. Tag syntax follows Kiwi-LLaMA's shape: `<span class='fieldPath'>value</span>`.
- Parser that converts span-tagged output back into our existing `{fieldPath, value, confidence}` triples, preserving the original span offsets alongside for R5.5 to consume.
- Fallback: if parse fails, fall back to the current JSON contract (so this WO cannot regress failure modes — only add a new path).
- New log tag `[extract][spantag]` for parse success/fail and span-coverage stats.

**Out of scope:**
- Changing which fields get extracted. The scope of extraction is set by #81.
- Teaching the model to bind entities to roles. That's #68 / R6.
- Actually wiring the span offsets into the R5.5 citation-grounding pipeline. That's the R5.5 WO; this WO only *produces* the offsets.
- Removing the JSON contract. Keep both paths; span-tag is additive, JSON is the fallback.

## Goals (concrete)

1. **Produce source-offset provenance on ≥ 80% of emitted extractions** by r5j-spantag eval, measured as the fraction of written items whose value appears literally at the span offset in the narrator reply.
2. **No regression on r4j/#81 eval pass rate.** Span-tag path must match or beat the JSON path; if not, ship the fallback.
3. **Bound parse-failure rate.** When the model emits malformed span-tags, the parser must degrade to JSON-contract fallback in 100% of cases. No silent empty writes.

**Explicit non-goal:** We are NOT claiming span-tags will reduce hallucinations. The model can still tag the wrong span, tag the wrong type, or wrap a close paraphrase. The win is provenance + boundary consistency, not safety.

## Risks (with mitigations)

- **Llama may not reliably emit well-formed span tags.** Kiwi-LLaMA reports pilot-test improvement after fine-tuning, not zero-shot. Our prompt-only use may drift (extra whitespace, unclosed tags, nested tags, Unicode attribute quotes). Mitigation: strict regex parser with a relaxed fallback that accepts `<span class=…` (curly or straight quotes, any internal whitespace) before falling back entirely to JSON.
- **Sentence-level vs turn-level scope mismatch.** Kiwi-LLaMA operates sentence-by-sentence with each sentence an independent instance, and explicitly excludes cross-sentence relations. Hornelore's hard cases (`dense_truth`, `large chunks`) are multi-clause same-turn bindings that this setup does not address. Implication: span-tags are evidence-neutral for those cases — they neither help nor hurt. Don't count them as a win for the dense cluster in success metrics.
- **Throughput cost.** Span-tag output is strictly longer than JSON (it wraps the entire input text plus emits tags). On a single RTX 50-series at local inference, this may push us past the extraction turn budget for long narrator replies. Measure: token count p95 per reply, before/after. Gate: if p95 grows > 1.5×, ship with a length cutoff that falls back to JSON for long replies.
- **Scoring layer assumes JSON shape.** The master eval scorer and the `_apply_claims_validators` pipeline both consume the current `{fieldPath, value, confidence}` shape. Span-tag output must be converted to that shape *before* any validator or scorer sees it, so this WO has zero validator/scorer surface impact.

## Measurement plan

Captured in `docs/reports/WO-EX-SPANTAG-01_REPORT.md`:

1. **Output contract toggle per eval run** — run eval twice, once JSON (baseline), once span-tag (experimental). A/B.
2. **Parse success rate**: fraction of LLM outputs that produce a valid span-tag parse. Target ≥ 90% on r5j master.
3. **Source-offset coverage**: fraction of written items with a valid source offset. Target ≥ 80%.
4. **Topline delta**: pass rate, v2/v3 subsets, must_not_write, follow_up, dense_truth. All must be ≥ baseline for ship.
5. **Latency**: mean + p95 extraction inference time, before/after.

## Implementation plan

1. **Commit 1 — Additive prompt variant.** Add a second code path in `_build_extraction_prompt` behind a feature flag. New path returns a span-tag-style instruction. Existing JSON path untouched.
2. **Commit 2 — Parser.** Add `_parse_spantag_output()` that converts span-tagged reply text to `{fieldPath, value, confidence, sourceSpan: {start, end}}` triples. On any parse failure, return `None` so the caller falls back to JSON parsing.
3. **Commit 3 — Wire the toggle into the extraction pipeline.** Feature flag off by default. Off = JSON (current behavior). On = try span-tag, fall back to JSON if parse fails.
4. **Commit 4 — Eval run + WO report** with the A/B deltas. Decide ship / no-ship based on the measurement plan.

Each commit independently reversible. Feature flag lets Chris A/B at runtime without code changes.

## Related work (source citations)

- Hu et al., *Information extraction from clinical notes: are we ready to switch to large language models?*, JAMIA 2026 (doi:10.1093/jamia/ocaf213). Section 3 "Methods / Instruction Format" describes the `<span class='entity_type'>…</span>` contract and its rationale.
- `docs/reports/loop01_research_synthesis.md` — Hornelore research synthesis. Kiwi-LLaMA is the citation-grounding-primitive source; *Order Is Not Layout* and *Architectural Determinism* are the separately-tracked inspirations for R5.5 / R6.

## Open questions for Chris review

1. **Span class naming:** Kiwi-LLaMA uses flat type names (`problem`, `drug`). We have dotted paths (`family.children.firstName`). Do we (a) use the dotted path as the class name verbatim, (b) use a short alias system, or (c) use a compact enum (f0, f1, f2, …) with a per-prompt legend? (a) is simplest but eats tokens; (c) is densest but loses the self-describing property.
2. **Catalog-scoping interaction with #81.** If #81 lands first and we're sending only 15–40 field paths to the model, span-tag class name verbosity matters less. Confirms dependency ordering: #81 first, then this.
3. **Reply-as-template vs inline emission.** Kiwi-LLaMA has the model re-emit the entire input with tags. For long narrator replies this is expensive. Alternative: emit only the tagged spans + a character-offset attribute. Question: do we have enough tokens in our reply budget to re-emit the whole reply, or do we need the offset-only variant?
4. **Scoring path preservation.** Should the eval scorer see the `sourceSpan` field (new), or strip it so the existing pass/fail logic is byte-identical to the JSON path? Recommend strip-by-default with a `--with-source-spans` flag for the R5.5 readout.

## Revision history

- 2026-04-19: Initial stub. Deferred pending r4i + #81 signoff. ChatGPT pass corrected two overclaims from the initial Kiwi-LLaMA synthesis (span-tags are provenance, not hallucination cure; paper's sentence-level scope ≠ evidence for full Pillar 1).
