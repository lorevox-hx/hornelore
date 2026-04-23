# WO-EX-SCHEMA-ANCESTOR-EXPAND-01 — Closeout report

**Status:** CLOSED complete (Lane 1 landed r5h; Lane 2 discovered-already-landed)
**Authored:** 2026-04-23
**Successor tags:** r5h (Lane 1 trial), r5i (Lane 1 full + #97 annotations)
**Task:** #144

---

## 1. Summary

Two-lane work order. Lane 1 (scorer-only `alt_defensible_paths` annotations for
ancestor-branch semantic-equivalence cases) landed across r5h and r5i as
specified — case_033 / case_039 / case_081 / case_087 annotated, r5i baseline
is 70/104 (v3=41/62, v2=35/62). Lane 2 (schema expansion adding
`greatGrandparents.*` identity fields) turned out to be **already landed as
part of task #36** (LOOP-01 R2, "Add greatGrandparents.* schema + router").
The Lane 2 spec's target field list is present in
`server/code/api/routers/extract.py` plus a thick alias table routing 20+
variant paths into the canonical keys. Net Lane 2 work: zero code change
required; closeout memo only.

## 2. Lane 1 — landed

Annotations committed to `data/qa/question_bank_extraction_cases.json`:

| case | truth-zone path | alt_defensible_paths added | r5h→r5i effect |
|---|---|---|---|
| case_081 | `grandparents.ancestry` | `greatGrandparents.ancestry` | 0.00 → 1.00 (flipped pass in r5h) |
| case_087 | `grandparents.ancestry` | `greatGrandparents.ancestry` | 0.00 → 0.50 (alt_defensible_path credited at fuzzy 0.8; memorableStory zone still missing, keeps case below v3 0.70) |
| case_033 | `military.significantEvent` | `greatGrandparents.militaryEvent`, `greatGrandparents.militaryUnit` | credited under #94 |
| case_033 | `military.branch` | `greatGrandparents.militaryBranch` + `alt_defensible_values=["Union", "United States Army", "Union Army", "US Army", "U.S. Army"]` | credited under #97 step-3 branch (`defensible_alt_value_credit`) |
| case_039 | `community.role` | `parents.occupation` | credited under #94 at fuzzy ~0.95 |

Scorer-drift audit on every flip: zero drift — truth-zone totals identical
r5g vs r5h vs r5i; only `hit` counts rose and `miss` counts fell.
must_not_write stayed 2 (case_035, case_093 — pre-existing carryover).

## 3. Lane 2 — already landed

The Lane 2 spec (`WO-EX-SCHEMA-ANCESTOR-EXPAND-01_Spec.md` §2.2) targeted:

| Target field | In extract.py? | Line | Notes |
|---|---|---|---|
| `greatGrandparents.firstName` | yes | L267 | writeMode=candidate_only, repeatable |
| `greatGrandparents.lastName` | yes | L268 | writeMode=candidate_only, repeatable |
| `greatGrandparents.relation` | equivalent | L266 | `greatGrandparents.side` (richer enum: maternal/paternal/grandfather's-father/etc.) |
| `greatGrandparents.ancestry` | yes | L272 | already credited case_081 in r5h |
| `greatGrandparents.placeOfBirth` | equivalent | L271 | `greatGrandparents.birthPlace` |
| `greatGrandparents.memorableStory` | equivalent | L273 | `greatGrandparents.memorableStories` (plural) |

Additional schema that the Lane 2 spec didn't list but is already present:
`greatGrandparents.maidenName` (L269), `greatGrandparents.birthDate` (L270),
plus `greatGrandparents.militaryBranch` / `militaryUnit` / `militaryEvent`
referenced throughout the extractor prompt text.

Router/alias side (also already present in extract.py at the alias block
around L3881–L3910) resolves 20+ variant paths into these canonical keys,
including `family.greatGrandparents.*`, `great-grandfather.*`,
`great-grandmother.*` prefixes.

**Task #119 landed the turnscope EXPAND** allowing greatGrandparents.* items
through the turn-scope filter when the target section points at grandparents
(r5g confirmed fires on case_028/033/035/044/069/087). The combination of
#36 (schema), #119 (filter), and Lane 1 (scorer annotations) is sufficient
for every failure mode Lane 2 was designed to address.

## 4. Why the spec still called for Lane 2

The Lane 2 spec was drafted after r5g's null result, when the
hallucination-prefix rollup showed `greatGrandparents` at 5 offenders
across 2 cases and the interpretation was "items die at schema validation."
Re-reading the r5g api.log trace post-#119 EXPAND showed the items were
in fact passing schema validation but the *scorer* was rejecting them
(wrong truth-zone path). Lane 1 fixed that. Lane 2's premise ("make the
path real so items survive validation") was already satisfied by #36 a
full development cycle earlier.

Lesson: when a turnscope patch EXPAND fires but items don't credit, the
next question is "scorer-side or extractor-side?" not "schema-side." The
schema-side fix had already landed months before.

## 5. What remains open

- case_087 hasn't crossed v3 0.70 despite the Lane 1 ancestry credit.
  Its bottleneck is `grandparents.memorableStory` — zone is missing
  (extracted=False) and has no alt annotation. An optional follow-up
  would add `alt_defensible_paths=["greatGrandparents.memorableStories"]`
  on that truth zone; the LLM does emit a memorableStories value on
  case_087 (r5i raw_items: `greatGrandparents.memorableStories='born in
  France, came to America around 1848, served in the C...'`). Not in
  Lane 1 scope; flagging as a follow-up annotation candidate.
- The `parents`/`family`/`siblings` hallucination cluster (28 offenders
  in r5h rollup) remains the dominant vector. That is a separate class
  (narrator-identity leak, family-prefix coercion, sibling mis-routing)
  and is WO-LORI-CONFIRM-01 territory.

## 6. Acceptance block (r5i reference)

- total pass count: 70/104
- v3 contract subset: 41/62
- v2 contract subset: 35/62
- must_not_write violations: 2 (case_035, case_093 — pre-existing)
- named affected cases: case_033 (0.00→0.33, scorer-side), case_039
  (0.00→0.50, scorer-side), case_081 (passing since r5h), case_087
  (0.00→0.50, scorer-side; below v3 0.70 threshold)
- pass↔fail flips vs r5h: 0 (r5i is r5h+#97 scorer extension + case_033/087
  annotations; #97 is additive and case_087 didn't cross threshold)
- scorer-drift audit on every flip: zero drift; only hit/miss shifts
- hallucination prefix rollup: greatGrandparents 5→5 (no change, expected
  — the extractor still emits the ancestor-path value, it just now gets
  scorer credit instead of being flagged as schema_gap)

## 7. Rollback

- Lane 1: revert the four annotations in
  `data/qa/question_bank_extraction_cases.json` (case_033, case_039,
  case_081, case_087). Revert also the #97 `alt_defensible_values`
  entries added at the same time.
- Lane 2: N/A — no code shipped under this WO.

## 8. Related

- Spec: `WO-EX-SCHEMA-ANCESTOR-EXPAND-01_Spec.md`
- Sibling WO (value-axis): `WO-EX-VALUE-ALT-CREDIT-01_Spec.md` (#97) —
  extended the scorer to credit `alt_defensible_values` on the alt path
  when expected-value fuzzy falls below 0.5. Landed in r5i alongside
  Lane 1 full annotation pass.
- Predecessor: task #119 (turnscope EXPAND for greatGrandparents subtree)
  and task #36 (greatGrandparents.* schema + router).
- Successor (separate cluster): WO-LORI-CONFIRM-01 for the
  parents/family/siblings hallucination vector.
