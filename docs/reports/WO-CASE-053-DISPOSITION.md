# WO-CASE-053-DISPOSITION — defer to R5 Pillar 2

**Task:** #68 — case_053 wrong-entity regression
**Disposition:** **DEFER** to R5 Pillar 2 (entity-role binding / OTS bias). Do NOT tactically patch in R4.
**Author:** Claude (LOOP-01 R4 cleanup)
**Date:** 2026-04-19

## The case

**narratorReply** (abridged): *"My dad's name was Kent, he was a welder. My mom Dorothy was a homemaker."*
**Expected:** `parents.firstName = "Kent"` (single-extract, dad-first mention).
**Actual (r4f / r4g):** `parents.firstName = "Dorothy"`.
**Actual (r4h):** same wrong pick, plus `siblings.firstName = "Christine"` newly emitted (likely a side-effect of a different narrator turn surfacing in the same run).

Score: 0.00 across r4f / r4g / r4h.

## Why this is not an R4 tactical fix

The surface symptom ("picked the wrong person") could be papered over in three ways. Each is rejected.

### Rejected fix 1 — positional heuristic

"If `extractPriority[0] = parents.firstName` and the narrator reply contains both `'dad'` and `'mom'`, prefer the name adjacent to `'dad'`."

Rejected because:
- Requires a rules-layer patch that only fires on this exact phrasing. Any narrator who says *"my mom Dorothy and my dad Kent"* (word-order reversed) defeats it.
- The real question ("which named entity does field X refer to in this sentence?") is semantic, not positional.
- Adds a special-case branch to the rules extractor which is already under pressure for #81 prompt-shrink.

### Rejected fix 2 — add a "parent name" few-shot

"Drop in a training example where `my dad Kent, my mom Dorothy` → `parents.firstName=Kent`."

Rejected because:
- A single few-shot can flip the bias in one direction on one phrasing, but the extractor's attention is already loaded; we don't know which existing few-shot it displaces in context.
- The `dense_truth 0/8` and `large chunks 0/4` cliffs are partially caused by prompt-catalog overload. Adding more few-shots directly works against the #81 spec.
- Papers over the root cause without addressing the general problem.

### Rejected fix 3 — second-pass LLM verifier

"Re-prompt the LLM asking 'who is the dad?' and use the answer to override the extraction."

Rejected because:
- Doubles inference latency on every turn.
- Pushes the architectural problem down the road — we'd still want the single-pass extractor to get this right eventually.
- Introduces a new failure mode (verifier disagreement resolution).

## What this actually is

Order-to-Space Bias (OTS), documented in `docs/reports/loop01_research_synthesis.md` citing *Order Is Not Layout* and *Architectural Determinism*. The extractor binds the first surfaced entity of a matching type to the first target field, independent of the relational anchor ("dad" / "mom") in the sentence. The synthesis identifies this as architectural debt addressable only by Pillar 1 (Draft/Project/Bind split) or Pillar 2 (entity-binding with explicit role attachments).

Evidence this is an architectural bias, not a one-case glitch:
- case_053 fails on this exact mechanism across r4f, r4g, r4h — three independent runs, same wrong pick.
- r4h shifted other extractions (`siblings.firstName='Christine'` newly emitted) without shifting this one, indicating the bias is stable against local perturbation.
- Similar symptoms appear in case_068 (`schema_gap` but same narrator-confusion pattern) and case_088 (`noise_leakage` + `llm_hallucination` on a relation extraction). These are clustered in the same failure family.

## Deferral plan

1. **No R4 code change** on case_053 or the parent-entity routing. Leave the raw failure as evidence for R5.
2. **Re-check after #67 lands** (r4i eval). If case_053 indirectly shifts (score > 0, or different wrong-pick), log the delta — it tells us which other R4 patches are touching the same code path.
3. **Surface in the post-R4 memo** (#82) as one of the three canonical R5 Pillar 2 cases alongside case_068 and case_088. These become the reference suite for validating the Draft/Project/Bind implementation when it lands.
4. **Don't re-litigate.** When any agent (Claude, Gemini, or ChatGPT) proposes a tactical patch for this, point at this memo.

## If case_053 does flip to passing before R5

Two possibilities:

- **Benign:** another patch downstream of #67 / #81 shifted the rules-layer routing such that the `dad`/`mom` co-occurrence now disambiguates. Good. Verify with a tighter adversarial case (word-order reversed) before counting the win.
- **Concerning:** LLM stochasticity gave us a lucky pass on one run. Verify by re-running; if the result is variable across 3+ runs, the underlying bias is still there and the pass is noise.

Either way, R5 Pillar 2 still needs to land — this case passing doesn't close the architectural debt. Update this memo's status block only, don't delete.

## Status

**Open / Deferred-to-R5.** Referenced from `CLAUDE.md` current-phase block as explicitly NOT in R4 scope.
