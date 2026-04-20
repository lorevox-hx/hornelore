# WO-EX-CASE053-DISPOSITION — case_053 defer-to-R5 memo

**Status:** deferred to R5 Pillar 2 (entity-binding / cardinality).
**Date:** 2026-04-19 (post-r4i).
**Related:** #68.

## Symptom

`case_053` (christopher-todd-horne, compound_family, extract_compound, tiny/clean):

Narrator reply: *"My dad's name was Kent, he was a welder. My mom Dorothy was a homemaker. I had two brothers, Vincent and Jason, and a sister named Christine."*

Expected fields (`extractPriority`-ordered):

| Path | Expected |
|---|---|
| `parents.firstName` | Kent |
| `parents.relation` | father |
| `parents.occupation` | welder |
| `siblings.firstName` | Vincent |

Actual extraction (r4i, method=`rules_fallback`):

| Path | Actual |
|---|---|
| `parents.firstName` | Dorothy |
| `parents.relation` | Mother |
| `parents.occupation` | homemaker |
| `siblings.firstName` | Christine |

Score 0.00, `llm_hallucination` category. `must_not_write` zones (`family.spouse.firstName`, `family.children.firstName`) correctly held — 0 violations.

## Why this is not an R4 tactical fix

Two overlapping architectural issues drive the miss:

1. **Scalar field vs multi-entity input.** `parents.firstName` and `siblings.firstName` are scalar paths in the current schema, but the narrator produced 2 parents and 3 siblings in a single reply. The extractor is forced to pick one, and currently picks the last-mentioned in each category (Dorothy for parents, Christine for siblings). The expected values are opinionated toward the first-mentioned / dominant entity (Kent, Vincent), but the schema has no way to express that prior. Fixing this cleanly requires either (a) making these paths list-typed (schema change + every downstream consumer), or (b) adding an ordinal prior to the router (fragile, leaks into unrelated cases).

2. **`rules_fallback` path bypasses the LLM entirely.** Method logged as `rules_fallback` — the LLM never saw this input. So no prompt-side patch (including #81 PROMPTSHRINK) will touch this case. The fix has to happen at the routing layer or at the rules extractor's dedup/ordinal logic.

Both are architectural R5 moves: cardinality promotion (schema-wide) + router-path reconsideration (Pillar 2 OTS entity-binding). Patching either inside R4 risks breaking the 34 cases where scalar `parents.firstName` is correct single-parent behavior.

## Empirical confirmation

- r4h: score 0.00, `llm_hallucination`, `parents.firstName=Dorothy`, `siblings.firstName=Christine`.
- r4i (post-Patch H): score 0.00, identical failure mode, identical extracted values. Patch H (write-time date normalisation) had no indirect effect — as expected, since the failure is in non-date scalar fields routed through `rules_fallback`.

Two live evals, same failure, same values, zero movement. Failure is stable and architectural, not noise.

## Disposition

- **Do not patch in R4.** No tactical patch under the R4 charter (prompt, schema aliases, write-time normalisation, turn-scope) can fix this without risking regression elsewhere.
- **Mark `currentExtractorExpected=false` stays false.** Already set correctly in the source case.
- **Deferred to R5 Pillar 2** (OTS entity-binding + cardinality promotion). Track under the follow-up that emerges from the post-R4 readout memo (#82).
- Re-measure after R5 Pillar 1 (citation-grounding) lands to check for indirect shift. If still unchanged, the fix is clearly in Pillar 2.

## Closeout

`#68` can be marked closed as "deferred with written disposition." Does not block R4 freeze. Surfaces in the #82 post-R4 memo as an explicit R5 inheritance.
