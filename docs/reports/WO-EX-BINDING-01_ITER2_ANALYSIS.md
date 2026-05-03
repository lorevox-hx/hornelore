# WO-EX-BINDING-01 Second Iteration — SPANTAG-on Bench Failure Analysis

**Date:** 2026-05-03 (afternoon, after `r5h-followup-guard-v1-spantag-on-bench`)
**Source data:** `docs/reports/master_loop01_r5h-followup-guard-v1-spantag-on-bench.{json,failure_pack.json}`
**Scope:** Identify next-iteration BINDING-01 patches grounded in fresh failure evidence; recommend disposition.

---

## Headline

The SPANTAG-on extraction-quality regression (3/10 = 30% on the eval slice) is NOT
caused by schema-invalid field paths. The LLM is emitting paths that ARE in the
schema; the eval cases just don't credit those paths in their truth zones. This
is **binding-vs-eval-zone mismatch**, not LLM-invents-a-fake-path.

This is a more nuanced problem than the prior BINDING-01 iteration's "drop the
invented namespace" pattern. Three paths forward; each warrants Chris + ChatGPT
triangulation before code lands.

**Disposition recommended: ANALYSIS COMPLETE, NO PATCH AUTHORED YET.** The
extractor lane stays default-OFF on SPANTAG. Next iteration is design discussion
about which of the three paths is the right shape.

---

## Initial misread, then the correction

Reading the failure_pack rollup at face value, four "hallucinated" paths popped:

```
case_082  offenders=2  siblings.relation, parents.relation
case_018  offenders=1  family.children.firstName
case_028  offenders=1  hobbies.hobbies
```

**First instinct:** add aliases / drops to extract.py's `_FIELD_ALIASES` to map
these to canonical paths.

**Then I checked extract.py.** All four are already in the schema:

| Path | Schema location |
|---|---|
| `siblings.relation` | L217: `{"label": "Sibling relationship (brother/sister)", ...}` |
| `parents.relation` | L205: `{"label": "Parent relationship (father/mother/step)", ...}` |
| `family.children.firstName` | L225: `{"label": "Child first name", ...}` |
| `hobbies.hobbies` | L197: `{"label": "Hobbies and interests", "writeMode": "suggest_only"}` |

So the model isn't inventing namespaces. It's emitting **valid schema paths
the eval cases don't expect** (= score 0 because none of the case's
`must_extract` zones match).

The label "invalid_field_path_hallucinations" in the failure_pack rollup is
misleading. These are field-path-vs-case-zone mismatches. Real hallucinations
(invented paths the schema rejects) are the cases the BINDING-01 PATCH 1-4
landed in 2026-04-27 already containment for.

---

## What's actually happening, per case

### case_082 — janice-josephine-horne, dense_truth, score 0.47

Narrator turn includes phrasing like "my sister Donna" — the LLM emits
`siblings.relation = "sister"` AND `siblings.firstName = "Donna"` (both
valid). The eval case's `must_extract` zone only credits `siblings.firstName`,
so the `.relation` emission counts as `noise_leakage` even though it's true.

**Real question:** is the eval case correct to penalize, or should the
`siblings.relation` emission be `may_extract` (informative-but-not-required)?

### case_018 — kent-james-horne, contract, score 0.00

`family.children.firstName` is the schema's canonical path for the narrator's
own children. The eval case might have expected `children.firstName` (without
the `family.` prefix). Without seeing the case JSON, this could be either:
- An eval-case path canonicalization gap (case expects unprefixed; schema
  says prefixed is canonical) → fix the case bank, not extract.py
- A genuine binding error if both prefixed and unprefixed are valid →
  needs an alias

### case_028 — janice-josephine-horne, contract, score 0.00

`hobbies.hobbies` is schema-valid (L197) but is the field path for "hobbies
and interests" (single-string narrative bucket) — distinct from the more
specific `hobbies.activity` style the eval case might expect. Same
canonicalization-vs-binding ambiguity as case_018.

### case_001 — christopher-todd-horne, contract, score 0.50

schema_gap, narrator=Chris. Without the per-case detail there's no way to
diagnose; the failure_pack rollup didn't surface offenders for this case
(only the 3 above).

### case_077 — kent-james-horne, mixed_narrative, score 0.50 [GAP]

Already-known gap (currentExtractorExpected=false). Not a regression target.

### case_087 — christopher-todd-horne, dense_truth, score 0.50 [GAP]

Already-known gap. Defensible_alt_credit failure means the LLM hit a path the
eval credited via the alt-defensible scorer mechanism — partial credit, not
full. Not a primary BINDING-01 target.

### case_033 — kent-james-horne, contract, score 0.25

schema_gap + defensible_value_alt_credit. The defensible_value_alt_credit
already credits `military.branch = "Union"` as a value-axis alternative for
`military.branch`. The schema_gap component needs separate look.

---

## Three paths forward

### Path A — Eval case bank canonicalization audit (lowest risk)

Hypothesis: the SPANTAG-on regression is partly an eval-side canonicalization
gap. The cases were authored against pre-SPANTAG extractor behavior; SPANTAG
Pass 2 emits the schema's canonical paths (`family.children.*`,
`hobbies.hobbies`) that the legacy SPANTAG-off path may have already mapped
internally before scoring.

**Action:** audit `data/qa/question_bank_extraction_cases.json` for cases
that expect non-canonical paths. Update their `must_extract` zones to accept
canonical AND legacy paths via the existing `alt_defensible_paths`
mechanism (same scorer policy already used for case_033 / case_087).

**Cost:** ~30 min of case-bank scrubbing, zero extract.py touch, zero risk
of regressing SPANTAG-OFF baseline (78/114).

**Expected delta on SPANTAG-on bench:** +1 to +3 cases (case_018 + case_028 +
maybe case_082), no regressions.

### Path B — Hospital-grade Pass 2 prompt tightening

Hypothesis: SPANTAG Pass 2 is too eager to emit valid-but-not-asked
metadata fields like `siblings.relation` when the question only needs
`siblings.firstName`. The Pass 2 controlled-prior block could carry a
"emit ONLY fields directly asked-for or strictly inferable" rule.

**Action:** add a NARROW-EMISSION RULE to the SPANTAG Pass 2 prompt
fewshots (extract.py around L644-680, where the existing `parents.relation`
and `siblings.relation` examples live). The rule would say "when the
narrator's text supports both the asked-for field AND a meta-field like
.relation, emit only the asked-for field; do not pile on metadata."

**Cost:** ~1 hr prompt edit + Chris-cycled SPANTAG-on bench cycle.

**Expected delta on SPANTAG-on bench:** +1 to +3 cases. Risk: new prompt
language might suppress LEGITIMATE `.relation` emissions on cases that DO
expect them. Needs careful eval matrix (Pass 2-on vs Pass 2-off for the 10
cases) before adopting.

### Path C — Defer until BINDING-01 has more failure data

The 10-case bench is a thin sample. Class C (case_001 schema_gap with no
visible offender) suggests the failure_pack rollup is missing detail for at
least some cases. A bigger bench (full 114-case master under SPANTAG-on)
would surface more patterns and let us A/B test prompt edits with more
signal.

**Cost:** ~10 min Chris-cycled (SPANTAG-on full master eval, ~5 min extract
+ ~5 min analysis). Higher risk of OOM tail per the 2026-04-27 rejection
context (case_044 + case_069 are the known long-prompt cases that hit OOM
last time).

**Expected delta on SPANTAG-on bench:** unknown. Better signal for the next
iteration design.

---

## Recommendation

**Sequence:** Path A first (lowest risk, fastest payoff) → Path B if Path A
doesn't close the regression → Path C only if Paths A+B together don't fix
the SPANTAG-on extraction regression.

Reasoning:
- Path A is pure eval-bank work, zero extract.py touch, zero
  SPANTAG-OFF baseline risk
- Path B requires Chris cycling and has the friendly-fire risk that the
  prompt-side BINDING-01 PATCH 1-4 already showed (the 2026-04-27 v3
  reject was -39 cases on the full master because broad prompt rules
  caused unintended behavior on non-target cases)
- Path C is a measurement step, useful but expensive

Note: the SPANTAG-OFF baseline (`r5h-followup-guard-v1` = 78/114) holds
regardless. SPANTAG default stays OFF until the next iteration shows
measured GREEN improvement on the full master pack.

---

## What this analysis does NOT do

- **No extract.py changes.** Recommendation is to triangulate Path A vs
  Path B before code lands.
- **No eval re-run.** Today's bench data is the input; cycling SPANTAG-on
  again is the next session's work.
- **No new BINDING-01 patch authoring.** Three paths identified; none
  authored. The author-vs-defer decision is Chris's call.
- **No SPANTAG default-on change.** `HORNELORE_SPANTAG=0` discipline lock
  stays.

---

## Pre-commit verification

Tree clean state requires `git status` from `/mnt/c/Users/chris/hornelore`
since sandbox can't run git. This is a docs-only artifact; no extract.py
touch, no test impact.
