# Question-bank tagging audit — r5e1 baseline

**Author:** Claude (overnight 2026-04-21→22)
**Parent ref:** Chris's decision-packet tag vocabulary (2026-04-21 evening)
**Scope:** All 104 cases in `data/qa/question_bank_extraction_cases.json`, joined with `docs/reports/master_loop01_r5e1.json`.
**Task:** #139 (stretch from original overnight list, #134 original number).
**Status:** First-pass audit complete. Tagging is rule-based from expectedFields + truthZones + narratorReply heuristics; not LLM-classified. The audit is for roadmap targeting, not ground-truth labeling.

---

## TL;DR

- `silent_output_risk` is the most operationally urgent class: 26 cases carry it, and only 3 pass (12% pass rate). 23 of the 45 r5e1 failures carry this tag. This is the rules_fallback_rate symptom made visible per-case.
- `birth_order_confirm` is the cleanest confirm-pass target: 4 cases, 0 pass. Every birth-order case in the corpus fails.
- LORI pilot scope (`confirm_eligible`) covers only 6 of 104 cases in its current narrow form. Scope is deliberately narrow per the parent spec — the audit confirms it's narrow, which is the intended tradeoff.
- `kinship_skeleton` is the highest-leverage LORI Feature A target: 25 cases, 40% pass. Skeleton pre-population would remove the name/relation extraction burden from every one of them.
- `date_range_confirm` has only 1 case in the whole corpus and 0 failures. The LORI date-range bank is corpus-underserved — consider authoring corpus cases before shipping that bank.
- Scalar-harvest cases fail at 1.5× the narrative-only rate (60% vs 46%), matching the "scalar confirmation problem" framing in the decision packet.

---

## Tag vocabulary (from decision packet)

Applied exactly as Chris specified:

| Tag | Meaning (tagging rule) |
|---|---|
| `scalar_harvest` | Any expected field whose leaf is a scalar type: firstName, lastName, birthOrder, relation, denomination, species, name, branch, count, dateOfBirth, placeOfBirth, yearsOfService, deploymentLocation, ancestry, maidenName, middleName, marriageDate, marriagePlace |
| `kinship_skeleton` | Any expected field in the skeleton block's deterministic write set (parents.firstName/relation/maidenName, siblings.firstName/relation/birthOrder, personal.birthOrder, family.spouse.firstName, family.children.*) |
| `confirm_eligible` | Any expected field in the LORI 4-field pilot (personal.birthOrder, siblings.birthOrder, parents.relation, *.yearsActive/dateRange/servicePeriod) |
| `narrative_only` | All expected fields have a narrative tail (notableLifeEvents, memorableStory, significantEvent, significantMoment, notes, uniqueCharacteristics, lifeLessons, earlyMemories, higherEducation, majorCondition, lifestyleChange, earlyCareer, careerProgression, destination, purpose, schooling, organization, role) |
| `thematic_evidence` | Expected field is one of: faith.significantMoment, community.organization, community.role, earlyMemories.significantEvent, travel.purpose, travel.destination |
| `high_ownership_risk` | forbidden includes narrator-scope fields (education.schooling, education.higherEducation, personal.dateOfBirth, family.marriageDate, parents.firstName, parents.occupation) AND narrator reply mentions family relatives + schooling/life-event cues |
| `silent_output_risk` | Extractor emitted 0 non-missing field values against ≥1 expected field (per r5e1 field_scores) |
| `dense_truth_risk` | Total (expected ∪ must_not_write) paths ≥ 5 |
| `date_range_confirm` | Any expected field ending in .yearsActive, .dateRange, or .servicePeriod |
| `birth_order_confirm` | Expected field is personal.birthOrder or siblings.birthOrder |

Notes on the tagging rules: `silent_output_risk` is measured against r5e1 output, not the corpus static — it's an extractor-behavior tag, not an intent tag. If the extractor changes, silent_output_risk tags would shift. The other 9 tags are intent/corpus-static.

---

## Tag frequency

|  Tag                 | All 104 | Failing 45 | Pass rate on tagged |
|---|---:|---:|---:|
| `scalar_harvest`     |   53  |   32  | 40% |
| `silent_output_risk` |   26  |   23  | 12% |
| `kinship_skeleton`   |   25  |   15  | 40% |
| `narrative_only`     |   24  |   11  | 54% |
| `dense_truth_risk`   |   21  |   10  | 52% |
| `high_ownership_risk`|   11  |    5  | 55% |
| `thematic_evidence`  |    7  |    5  | 29% |
| `confirm_eligible`   |    6  |    4  | 33% |
| `birth_order_confirm`|    4  |    4  | 0%  |
| `date_range_confirm` |    1  |    0  | 100% |

Corpus-wide pass rate baseline for reference: 59/104 = 57%.

## Interpretation

### Emergency: `silent_output_risk` (26 cases, 12% pass)

By far the sharpest signal. Three-quarters of cases with silent-output also fail overall. This is the rules_fallback_rate from the decision packet rendered per-case. Cross-tag:

- `silent_output_risk × scalar_harvest`: 16 cases — scalar extractions that go silent is its own class (cases like 045/046 for pets, 077/080/081 for family history, 083 for grandparents).
- `silent_output_risk × narrative_only`: 9 cases — prose extractions that go silent.

**Recommendation:** lift this class to its own WO. It's probably closer to extractor-parse or fallback-path behavior than to the LORI confirm-pass lane. Stops being "we'll fix it with SPANTAG" hand-waving. Candidate WO name: `WO-EX-SILENT-OUTPUT-01` — instrument which parse failure / max-tokens / prompt collapse mode is responsible, fix the dominant one.

### Sharpest confirm-pass signal: `birth_order_confirm` (4 cases, 0% pass)

Perfect targeting signal. Every case with this tag fails in r5e1. These are cases 002, 014, 024, 047 — all four are the LORI Feature B birthOrder bank's primary targets. Each is in the 15-case multi-turn pilot pack (`docs/drafts/multiturn_cases_r5e1_pilot.json`, mt_case_001–004).

### LORI scope confirms narrow: `confirm_eligible` (6 cases, 33% pass)

Only 6 corpus cases hit the 4 pilot fields directly. The LORI spec's "deliberately narrow" framing is honest — it's not that confirm-pass would fix a huge chunk of the corpus, it's that it targets a specific failure class that extractor-only work can't easily solve. The leverage comes from Feature A (skeleton), not Feature B (confirm).

### Highest-leverage LORI target: `kinship_skeleton` (25 cases, 40% pass)

Cases where the expected data lives in the skeleton-deterministic set. The skeleton block's writes would pre-populate parents.firstName, parents.relation, siblings.firstName, siblings.relation, siblings.birthOrder, personal.birthOrder. That's 15 of 25 currently failing (and 10 of 25 currently passing with some noise). If the skeleton writes canon authoritatively and canon-collision Rule 3 is live, every one of these 25 cases gets cleaner extraction — and the 15 failing ones likely flip.

`kinship_skeleton × scalar_harvest` is the biggest co-occurrence at 25 — the full set. Every kinship_skeleton case is scalar_harvest, which is logically consistent with the tag definitions.

### Date-range corpus gap: `date_range_confirm` (1 case, 0 failing)

The corpus has one case touching yearsActive/dateRange/servicePeriod fields, and it passes. The LORI dateRange bank has no baseline targets. Either the corpus needs to exercise the date-range class (add 3–5 cases with duration-phrase → explicit-range patterns), or the dateRange bank can be descoped from v1 pilot and deferred to v1.5.

**Recommendation:** add 3 date-range cases to the corpus in the next corpus expansion pass (task #111 covers corpus expansion in progress). Patterns to author:
- "twenty-five years at Boeing" → `*.yearsActive = 1997-2022`
- "served about a decade in the Navy" → `military.servicePeriod = 1968-1978`
- "we lived in Fargo for twelve years" → `residence.dateRange = 1985-1997`

If these cases are authored and land as stubborn in baseline, the dateRange bank has a target. If they pass baseline, the bank can be retired from v1 scope.

### Ownership/attribution class: `high_ownership_risk` (11 cases, 45% fail)

Close to the r5e2 ATTRIBUTION-BOUNDARY rule's target. The 5 failing cases: 002 (forbidden education.schooling), 014 (forbidden education.schooling), 024 (forbidden education.higherEducation), 035 (mnw violated on education.schooling for parent Josie), 093 (mnw risk on parents.firstName=Pete). LORI Feature A (skeleton) addresses this indirectly — if `parents.firstName=Leila,Ervin` is already in canon, the narrative pass write of `parents.firstName=Pete` (Janice's father, from Kent's faith turn) would be caught by canon-collision Rule 3 (narrative_drift_vs_skeleton, severity=warn) and blocked.

This is a **second-order benefit** of LORI Feature A that isn't called out in the parent spec. Worth documenting: skeleton canon is an implicit attribution-boundary guard. Adding to LORI prep pack §4 as a bonus outcome.

### Narrator skew

| Narrator | silent_output_risk | kinship_skeleton | narrative_only |
|---|---:|---:|---:|
| christopher-todd-horne | 9 | 10 | 7 |
| janice-josephine-horne | 10 | 7 | 9 |
| kent-james-horne | 7 | 8 | 8 |

Janice has the highest silent_output concentration. Kent has the lowest. Christopher has the most kinship_skeleton coverage — makes sense, his canon has 2 parents + 2 siblings explicitly called out in early developmental cases.

**LORI pilot ordering:** start Feature A dogfooding with christopher-todd-horne (cleanest canon, densest skeleton coverage). Move to kent second. Janice third, because her silent_output rate is a confounder.

---

## Top untagged classes (failing cases with only 1 tag)

Looking for failing cases that don't cluster well — these are the weirdos that may need their own WO scoping.

```
case_031 (school_years, early_caregivers)  [silent_output_risk, kinship_skeleton, scalar_harvest]
case_027 (early_adulthood, post_education) [narrative_only, silent_output_risk]  
case_037 (midlife, health_and_body)        [narrative_only, silent_output_risk]  
case_043 (midlife, travel_and_world)       [narrative_only, thematic_evidence, silent_output_risk]
case_059 (adolescence, career_progression) [narrative_only, silent_output_risk]
case_083 (school_years, grandmother_story) [narrative_only, kinship_skeleton, silent_output_risk]
```

Pattern: almost every sparsely-tagged case carries `silent_output_risk`. Reinforces the recommendation above to stand up a silent-output WO.

---

## Cross-tag matrix (top 10 co-occurrences, all 104)

|  Tag A                 |  Tag B                 | Count |
|---|---|---:|
| `kinship_skeleton`     | `scalar_harvest`       |  25 |
| `dense_truth_risk`     | `scalar_harvest`       |  19 |
| `scalar_harvest`       | `silent_output_risk`   |  16 |
| `dense_truth_risk`     | `kinship_skeleton`     |  15 |
| `narrative_only`       | `silent_output_risk`   |   9 |
| `confirm_eligible`     | `dense_truth_risk`     |   6 |
| `kinship_skeleton`     | `silent_output_risk`   |   6 |
| `high_ownership_risk`  | `scalar_harvest`       |   6 |
| `confirm_eligible`     | `kinship_skeleton`     |   5 |
| `confirm_eligible`     | `scalar_harvest`       |   5 |

Readings:

- **LORI Feature A footprint:** `kinship_skeleton × scalar_harvest` at 25 — literally the entire kinship_skeleton set is scalar_harvest. Feature A deterministic writes cover this whole surface.
- **Silent output is a symptom, not a class:** `silent_output_risk` co-occurs with every other major tag. It's an orthogonal behavior axis, not a scope tag. Suggests silent-output should be tracked as a *metric* (like dense_metrics) rather than used for WO scoping.
- **LORI Feature B footprint:** `confirm_eligible × kinship_skeleton` at 5 + `confirm_eligible × scalar_harvest` at 5 = overlap is almost complete. Feature B fires on a subset of Feature A's surface.
- **Dense cases are brittle:** `dense_truth_risk × scalar_harvest` at 19, `dense_truth_risk × silent_output_risk` at 4. Dense cases with many paths fail in the silent-output mode often.

---

## Recommendations

1. **Promote silent_output_risk to a dedicated WO.** Current status: it's a diagnostic tag. Recommendation: stand up `WO-EX-SILENT-OUTPUT-01` with a 26-case pack (the tagged set) and diagnostics that distinguish parse-failure / max-new truncation / prompt collapse / rules_fallback fallthrough / extractor return-empty. The current failure_categories histogram mixes these. Grep `.runtime/logs/api.log` for `rules_fallback_dispatched`, `json_parse_failed`, `max_new_truncated`, and see which dominates on the 26 silent cases.
2. **Add 3 date-range corpus cases** to give the LORI dateRange bank something to evaluate against. Patterns in §Date-range corpus gap above.
3. **Start LORI pilot dogfooding with christopher-todd-horne.** Cleanest skeleton coverage, lowest silent_output confounding.
4. **Update LORI prep pack** (`WO-LORI-CONFIRM-01_PREP_PACK.md` §4) to explicitly note canon-collision Rule 3 as an implicit attribution-boundary guard. Current prep pack treats it only as drift telemetry.
5. **Tag the full corpus in-tree.** This audit is static. If tags are added to each case record in `question_bank_extraction_cases.json`, future eval reports can auto-bucket and the dense_metrics block (task #33) can grow a tag-axis. Proposal: add an optional `tags: ["scalar_harvest", "kinship_skeleton"]` field per case, authored initially from this audit. Non-breaking (ignored by the scorer). Light touch, persistent value.
6. **Do NOT use tag rates for go/no-go on LORI.** Confirm-pass fires on 4 staged fields, not on tags. The tagging here is roadmap-level; the pilot's acceptance gates (prep pack §9) are case-level. Keep the two surfaces separate.

---

## Output files

- Full per-case tagging JSON: `/tmp/tag_audit_results.json` (transient). Propose promoting to `docs/reports/question_bank_tagging_audit.json` on morning signoff.
- This report: `docs/reports/question_bank_tagging_audit.md`.

## Limitations

- Tagging is rule-based from expectedFields + truthZones + narratorReply keyword heuristics. A semantic classifier would produce different tags on some edge cases (especially `thematic_evidence` and `high_ownership_risk`, which rely on reply-content cues that are easy to miss).
- `silent_output_risk` is computed against r5e1 output specifically. If the extractor changes, this tag's distribution will shift. Recommend re-running the audit after each floor change.
- No tag captures "truncation-starved" as a distinct class — that's `#96` lane territory and requires VRAM-GUARD flag analysis, which isn't in the question bank static data.
- `date_range_confirm` has 1 case total; the finding may not survive a bigger corpus. Treat as tentative until corpus expansion (#111) lands.
