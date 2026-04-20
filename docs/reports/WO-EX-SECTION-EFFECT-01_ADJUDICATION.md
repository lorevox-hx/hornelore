# WO-EX-SECTION-EFFECT-01 — Phase 1 Adjudication

**Author:** Claude
**Date:** 2026-04-20
**Source eval:** `docs/reports/stubborn_pack_r4j_run1.json` (r4j, `HORNELORE_PROMPTSHRINK=1`, stubborn-15 pack, method per case recorded below)
**Pack:** the 15 frozen stubborn cases (case_008, 009, 017, 018, 053, 075, 080, 081, 082, 083, 084, 085, 086, 087, 088)

## 1. What this is

Phase 1 of WO-EX-SECTION-EFFECT-01. One-shot adjudication of whether each stubborn-pack case has a genuinely-single expected emission path, a defensible dual-path story, or is failing for some other reason (truncation, entity-bind, scorer-drift).

**Purpose:** produce `alt_defensible_paths` labels so (a) SPANTAG's Pass 2 dual-path emission can be scored against adjudicated truth, and (b) we can cleanly separate section-conditioned schema coercion from the other failure modes polluting the stubborn frontier.

**Classification taxonomy** (used in the table):

- `subject_only_defensible` — expected path is the only reasonable read; model went wrong for non-section reasons (entity-bind, intra-schema miss, coverage).
- `dual_answer_defensible` — narrator content legitimately supports **more than one** schema path. Today's scorer penalises any path that isn't the case author's pick; SPANTAG's first-class dual-path output needs both to be recognised.
- `section_only_misapplied` — model committed to a section-driven path with no subject support. (None observed in this pack; kept in the taxonomy for Phase 3 and scorer policy.)
- `truncation_starved` — r4j produced zero-or-near-zero items, method often `fallback`, dense or large chunk. Failure mode is output-budget or input-context pressure, not shape. SPANTAG alone won't fix.
- `scorer_drift_suspect` — model emission is semantically correct but truth value or scorer fuzzy-match penalised it. Flag for scorer-policy review under this same WO (`alt_defensible_paths` generalises to `alt_defensible_values` in the scorer).
- `wrong_entity_bind` — compound-family or multi-entity disambiguation failure. Architectural (#68), not section-effect.
- `context_unavailable` — model was penalised for re-emitting content already captured in an earlier turn; the "already-captured" context isn't threaded to the extractor. Systemic, not per-case.

## 2. Adjudication table

| Case | Reply (trimmed) | active_section | active_target_path | expected_primary | r4j_emitted (primary) | classification | alt_defensible_paths | Notes |
|---|---|---|---|---|---|---|---|---|
| case_008 | "mom's brother James was born in a car on the way to Richardton… Uncle Jim — James Peter Zarr" | developmental_foundations / family_stories_and_lore | _earlyMemories.significantEvent_ (inferred; Phase 2 TBD) | `parents.notableLifeEvents` = "born in a car" | `earlyMemories.significantEvent` = full reply | **dual_answer_defensible** | `["earlyMemories.significantEvent"]` | Case's own `extractPriority` lists BOTH paths. "Uncle's birth-in-a-car" is simultaneously (a) a family-lore early-memory item from narrator's childhood framing, (b) a parent-side notable life event (mom's brother). Section-context pushed the early-memory bind; content also supports the parent-side bind. Secondary issue = verbatim-reply value (noise leak), separate from the path bind. |
| case_009 | "my real career started when I became an occupational therapist. I trained in OT and that's what I did my whole career." | early_adulthood / professional_genesis | _education.careerProgression_ (inferred) | `education.earlyCareer` = "occupational therapist" | `education.careerProgression` = "occupational therapist"; `education.training` = "trained in OT" | **dual_answer_defensible** | `["education.careerProgression"]` | The distinction `earlyCareer` vs `careerProgression` is a schema-internal subtlety. Narrator said "real career started when I became" — earlyCareer is the author's pick, but careerProgression is defensible, especially under the `career_progression`-adjacent section. `education.training` is noise (may_extract at best). Model found the entity cleanly; it picked an adjacent schema path. |
| case_017 | "We had a Golden Retriever, Ivan. Good dog." | developmental_foundations / childhood_pets | _pets.*_ (inferred — note `extractPriority` says hobbies/earlyMemories instead) | `pets.name` = "Ivan", `pets.species` = "dog" | `pets.notes` = "Golden Retriever"; `pets.notes` = "Ivan" | **subject_only_defensible** | — | Not section-effect. Case's `extractPriority` mis-points (hobbies/earlyMemories) but the subTopic/`childhood_pets` section correctly pushed model to `pets.*`. Failure is intra-schema: model chose `pets.notes` for everything instead of `pets.name` + `pets.species`. Shape-error within correct section. Interesting datapoint: section-routing worked; finer-grained within-catalog binding failed. |
| case_018 | "we lived in Germany for a while when the boys were small — that's where Vincent was born. Then we moved around…" | midlife / middle_moves | _residence.place_ (inferred) | `residence.place` = "Germany" | `family.children.relation` = "son"; `family.children.firstName` = "Vincent" | **dual_answer_defensible** | `["family.children.firstName", "family.children.placeOfBirth"]` | Narrator content legitimately supports two binds: residence (Germany) and child birth-event (Vincent born in Germany). Section (middle_moves) should have pushed to residence; model followed the `was born` relation_cue to `family.children` instead. Interesting counter-example to case_008: here subject beat section. Scorer should credit either path on its own. |
| case_053 | "My dad's name was Kent, he was a welder. My mom Dorothy was a homemaker. I had two brothers, Vincent and Jason, and a sister named Christine." | childhood_origins / compound_family | _parents.*_ (inferred) | `parents.firstName` = "Kent", `parents.occupation` = "welder", `siblings.firstName` = "Vincent" | `parents.firstName` = "Dorothy"; `parents.occupation` = "homemaker"; `siblings.firstName` = "Christine" | **wrong_entity_bind** | — | The #68 case. Compound-family disambiguation: model bound the second-mentioned parent (Dorothy) into the `parents.firstName` slot and the last-mentioned sibling (Christine) into the `siblings.firstName` slot, overwriting the first-mentioned. Architectural — deferred to R6 Pillar 2 (OTS / entity-role binding) per `WO-EX-CASE053-DISPOSITION.md`. Not a section-effect target; SPANTAG may help if Pass 1's relation_cue inventory disambiguates, but closing it is out of scope for this WO. |
| case_075 | "My mother was Josephine — everyone called her Josie. She was a gifted musician… played the organ at movie theaters… two years of college… worked as a housekeeper… kitchen work…" | developmental_foundations / mother_stories | _parents.*_ (inferred) | `parents.occupation` = "Housewife" | `parents.occupation` = "musician"; plus `parents.firstName`=Josephine (hit), preferredName=Josie, education, and Anna | **scorer_drift_suspect** | — | **"Housewife" is not grounded in the reply.** The reply describes musician, organist, housekeeper, college student, kitchen worker — never housewife. Model's "musician" is arguably the best-supported occupation span. This is either a truth-authoring miss or an overly narrow scorer fuzzy-match. Flag for scorer-policy review: Phase 1 output should add `alt_defensible_values` capability generalising `alt_defensible_paths`. Separately: `parents.firstName`=Anna emission is a wrong_entity_bind (grandmother, not parent). |
| case_080 | Dense genealogy: George Horne, Elizabeth Shong, homestead, six children, dates, remarriage. | developmental_foundations / family_history | _grandparents.*_ | `grandparents.firstName` = "George"; `grandparents.memorableStory` = homestead-and-death story | (empty — method=`fallback`, extracted_count=0) | **truncation_starved** | — | Dense-truth medium chunk, 0 items emitted. Not section-effect; SPANTAG Pass 2 alone won't fix unless Pass 1 span-extraction succeeds on the dense input. Candidate for KORIE-style staged pipeline if SPANTAG doesn't move it. |
| case_081 | Dense genealogy: Lorraine France origin, John Michael Shong, Civil War, Christine Bolley, migration. | developmental_foundations / great_grandparents | _grandparents.*_ | `grandparents.ancestry` = "French (Alsace-Lorraine), German" | (empty — method=`fallback`, extracted_count=0) | **truncation_starved** | — | Same pattern as 080. Large chunk, 0 items. |
| case_082 | "I was born in Spokane, Washington because my dad Pete was working at an aluminum factory… moved back to Dodge… Glen Ulin… Strasburg… Bismarck… Germany…" | developmental_foundations / childhood_moves | _residence.*_ (inferred) | `residence.place` = "Spokane, Washington"; also `personal.placeOfBirth` = "Spokane, Washington" (must_extract) | `parents.firstName`=Pete; `parents.occupation`="working at an aluminum factory out there"; `residence.place` = full reply verbatim (noise leak) | **dual_answer_defensible** | `["personal.placeOfBirth"]` on `residence.place`; **and** `residence.place` itself expects a multi-value (Dodge, Glen Ulin, Strasburg, Bismarck, Germany) that the expected value truncates to "Spokane, Washington" | Section = childhood_moves pushed toward residence, but the narrator's Spokane is actually birthplace, not residence. Truth zone correctly has both `personal.placeOfBirth` and `residence.place` as must_extract; the `expectedFields` single-pick is tighter than the truth zone. Model's noise-leaked residence.place value is a different problem (write-time normalisation). SPANTAG should help: Pass 1 can tag `Spokane, Washington` once as a place, and Pass 2's dual-path output can bind it to both `personal.placeOfBirth` and `residence.place` (if both sit in scope). |
| case_083 | Dense Shong-family history: eight siblings, dates, migrations, surname-change note. | developmental_foundations / grandmother_story | _grandparents.*_ | `grandparents.memorableStory` = "youngest of eight children… seamstress in Penn ND… Schong→Shong" | (empty — method=`fallback`, extracted_count=0) | **truncation_starved** | — | Medium dense chunk, 0 items. |
| case_084 | "Gretchen Jo was born October 4, 1991… Amelia Fay August 5, 1994… Cole Harber Horne April 10, 2002…" | midlife / children_detailed | _family.children.*_ | `family.children.firstName` = "Gretchen"; `family.children.dateOfBirth` = "1991-10-04" | (empty — method=`fallback`, extracted_count=0) | **truncation_starved** | — | Multi-child compound content, 0 items emitted. Note: expected is only the FIRST child; truth zone correctly expands to all four. Even so, model didn't emit anything. |
| case_085 | "Pete — Peter Zarr — born at home in Dodge… steam boiler operator license… carpentry… Garrison Dam foreman… birth certificate burned with Capitol…" | developmental_foundations / father_story | _parents.*_ | `parents.firstName`=Peter, `parents.lastName`=Zarr, `parents.occupation`="Steam boiler operator, carpenter" | `parents.firstName`=Peter only | **truncation_starved** (partial recall) | — | Model got the first-name hit then stopped. 2 items emitted, rest of the parent-role content (lastName, occupation, notable life events, birthPlace) missing. Partial-recall variant of truncation. |
| case_086 | "construction and trades… we moved a lot… Germany… Vincent born… Janice kept the boys on track… three boys — Vincent, Jason, Christopher. Chris born December 24, 1962…" | early_adulthood / career_family | _education.*_ and _family.*_ (mixed section) | `education.earlyCareer` = "Construction and trades" | (empty — method=`fallback`, extracted_count=0) | **truncation_starved** | — | Long mixed-section reply (career + residence + children + family context). 0 items emitted. |
| case_087 | Dense Shong ancestral history: France/Lorraine, Civil War, Germany/Hanover, Lizzie→George marriage, surname change. | developmental_foundations / shong_family | _grandparents.*_ | `grandparents.ancestry` = "French (Alsace-Lorraine)" | (empty — method=`fallback`, extracted_count=0) | **truncation_starved** | — | Large chunk, 0 items. |
| case_088 | "Grey was everything to me. I'd ride out every morning before chores… That was in Dodge… I was a real outdoors girl — milking cows, riding Grey… Verene was the exact opposite." | developmental_foundations / childhood_pets (follow_up) | _pets.*_ | `pets.notes` = "childhood horse, rode every morning before chores" | `pets.name`=Grey, `pets.species`=horse, `pets.notes`="narrator's favorite horse, rode every morning, loved being outdoors", `residence.place`=Dodge | **scorer_drift_suspect** + **context_unavailable** | alt_defensible_values on `pets.notes` should include "rode every morning, loved being outdoors" | (a) Model's `pets.notes` is semantically equivalent to expected; scorer's fuzzy match too tight. (b) Model re-emitted `pets.name`=Grey and `pets.species`=horse which the truth zone marks as should_ignore with note "already captured earlier". The extractor has no context signal that those were captured on a prior turn — systemic. (c) `residence.place`=Dodge is also flagged already-captured → same context-unavailable mechanism. |

## 3. Rollup

**Classification tally across the 15:**

| Classification | Cases | Count |
|---|---|---|
| truncation_starved | 080, 081, 083, 084, 085, 086, 087 | **7** |
| dual_answer_defensible | 008, 009, 018, 082 | **4** |
| scorer_drift_suspect | 075, 088 | **2** |
| subject_only_defensible | 017 | **1** |
| wrong_entity_bind | 053 | **1** |
| section_only_misapplied | — | 0 |

**Read of the pack:**

- **The stubborn frontier is mostly not section-effect.** 7 of 15 are truncation-starved and will not move on SPANTAG's path-binding design alone. They need Pass 1 to succeed on dense input first, and possibly output-budget or staged-pipeline work (KORIE lane) beyond that.
- **4 of 15 (008, 009, 018, 082) are clean dual-answer-defensible cases.** These are SPANTAG's proper target pack — the ones where Pass 2's first-class dual-path output, with `alt_defensible_paths` in the scorer, should flip scoring from 0.0 to passing without any model change. This is the measurable section-effect SPANTAG is designed to fix.
- **2 of 15 (075, 088) are scorer-drift-suspect.** These need scorer-policy work (`alt_defensible_values` on top of `alt_defensible_paths`), not model work. Flag for Phase 2 bundled with scorer updates.
- **2 of 15 (017 bind-within-section, 053 compound-entity) are architectural.** 017 is an intra-catalog bind error (section routing worked, within-section schema choice failed) — SPANTAG Pass 2 may or may not help depending on how strongly the `pets.name`/`pets.species` distinction is carried in Pass 2's prompt. 053 is explicitly deferred to R6 Pillar 2 (#68).

**Implication for SPANTAG expectations:**

- Realistic SPANTAG topline lift from the section-effect mechanism alone = **+4 stubborn flips at best** (008, 009, 018, 082), gating on scorer adopting `alt_defensible_paths`.
- A scorer-policy update bundled with Phase 2 gives **+2 more** (075, 088) without model work.
- The remaining **7 truncation-starved cases and 2 architectural** will not move on SPANTAG Phase 1 alone. The KORIE conditional-trigger bar in CLAUDE.md ("≥20% topline lift or ≥3 stubborn flips") is achievable within SPANTAG's designed scope; pushing beyond needs a different lever.

**Implication for eval attribution:**

When SPANTAG lands, the pre-flip-vs-post-flip delta on the stubborn pack will mix `scorer adopts alt_defensible_paths` (label change, no model change) with `SPANTAG binds differently` (model change). Phase 2 scorer updates must land **before** SPANTAG's first eval so the delta is attributable to SPANTAG alone. Otherwise we cannot distinguish "SPANTAG fixed the bind" from "scorer now accepts the bind it was already producing".

## 4. Phase 1 patch to the cases file

`data/qa/question_bank_extraction_cases.json` is patched in the same commit as this report. Per-case changes:

- **case_008** — add `alt_defensible_paths` on `parents.notableLifeEvents` truth zone entry: `["earlyMemories.significantEvent"]`.
- **case_009** — add `alt_defensible_paths` on `education.earlyCareer` truth zone entry: `["education.careerProgression"]`.
- **case_018** — add `alt_defensible_paths` on `residence.place` truth zone entry: `["family.children.firstName", "family.children.placeOfBirth"]`.
- **case_082** — add `alt_defensible_paths` on `residence.place` truth zone entry: `["personal.placeOfBirth"]`.
- **case_075, case_088** — do NOT add `alt_defensible_paths`; these need `alt_defensible_values` support (future field) on the value-match axis, not the path axis. Log their disposition in the notes column of this report only.
- **case_017, case_053, case_080, case_081, case_083, case_084, case_085, case_086, case_087** — no adjudication patch. Failure modes are not section-effect.

Scorer behavior required for `alt_defensible_paths` (Phase 2 task, not landed here):

- On a `must_extract` truth zone: if an emitted field path matches any entry in `alt_defensible_paths` AND the value matches expected (exact or fuzzy per existing scoring), credit the zone as hit. Do not penalise for emitting the primary path or any defensible path.
- On a `must_not_write` truth zone: `alt_defensible_paths` does not apply.
- Report the winning path in the per-field score so audits can see which of {primary, defensible-alt} flipped.

## 5. Open questions for Phase 2 / Phase 3

1. **Case_008 active target path.** The case's `extractPriority` lists both paths in order [earlyMemories first, parents second]. Was the runtime `current_target_path` the first item of extract_priority, or is there a different derivation? Need interview-runtime code-path trace to confirm what the extractor actually saw on r4j for this case. (Phase 2 instrumentation.)
2. **Case_018 subject-beat-section.** Why did model pick `family.children` over `residence` here when it picked section over subject on case_008? Two candidate mechanisms: (a) `was born` is a stronger relation_cue than `brother was born in a car`; (b) `middle_moves` subTopic's target_path differs from `family_stories_and_lore` target_path in a way that changes the bind pressure. Causal matrix (Phase 3) should vary these.
3. **Dense-chunk floor for case_080 / 081 / 083 / 084 / 086 / 087.** All six produced 0 items under `fallback` method. Confirm on r4i and r4h whether this is r4j-specific (PROMPTSHRINK few-shot starvation on dense content) or baseline behavior. If baseline, SPANTAG's Pass 1 must be validated on dense input before Phase 2 eval.
4. **Case_053 (#68) cross-reference.** Already deferred, but should be noted in SPANTAG's measurement section so its topline inclusion is not claimed as a SPANTAG target.
5. **Case_017 inside-catalog drift.** `pets.name` vs `pets.notes` is a within-scope bind error. Does SPANTAG's Pass 2 input include the full catalog scope for the active section, or only a narrowed slice? If narrowed, ensure Pass 2 sees both paths.

## 6. References

- `WO-EX-SECTION-EFFECT-01_Spec.md` — this WO.
- `WO-EX-SPANTAG-01_Spec.md` — consumer of this adjudication; Pass 2 dual-path emission scored against `alt_defensible_paths`.
- `docs/reports/stubborn_pack_r4j_run1.json` — source emissions for r4j.
- `docs/reports/master_loop01_r4i.json` — locked baseline for cross-reference on dense-chunk behavior.
- `docs/reports/WO-EX-CASE053-DISPOSITION.md` — case_053 architectural deferral.
- `data/qa/question_bank_extraction_cases.json` — patched in the same commit with `alt_defensible_paths` entries on the four flagged cases.

## 7. Revision history

- 2026-04-20: Phase 1 adjudication written. 4 dual-answer-defensible, 7 truncation-starved, 2 scorer-drift-suspect, 1 subject-only intra-catalog bind, 1 wrong-entity-bind (#68). Zero pure section-only misapplications in this pack.
