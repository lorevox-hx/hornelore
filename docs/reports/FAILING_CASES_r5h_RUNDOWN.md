# r5h Failing Cases Rundown

**Baseline:** r5h (70/104, v3=41/62, v2=35/62, mnw=2) — ADOPTED 2026-04-22
**Comparison reference:** r5f (69/104), r5g (69/104 null)
**Successor doc to:** `FAILING_CASES_r5e1_RUNDOWN.md` (2026-04-21)
**Authored:** 2026-04-22, doc-only API-down session

---

## Topline

34 failed cases across 3 narrators.

| narrator | failed count |
|---|---|
| christopher-todd-horne | 11 |
| janice-josephine-horne | 12 |
| kent-james-horne | 11 |

Must-not-write violations (2, carried from r5e1 / r5f): **case_035** (faith turn, `education.schooling` narrator-leak), **case_093** (spouse-detail follow-up, `education.higherEducation` narrator-leak). Both tracked under WO-LORI-CONFIRM-01.

## Failure-category tally

| category | count |
|---|---|
| schema_gap | 14 |
| llm_hallucination | 13 |
| field_path_mismatch | 9 |
| noise_leakage | 3 |
| guard_false_positive | 2 |
| defensible_alt_credit | 1 |

Many cases carry multiple categories. `schema_gap` dominates — exactly the cluster WO-SCHEMA-ANCESTOR-EXPAND-01 (#144) targets.

## Score-bucket distribution (fails only)

| bucket | count |
|---|---|
| 0.00 | 10 |
| 0.25–0.49 | 6 |
| 0.50–0.69 | 17 |
| 0.70+ | 1 |

17 of 34 fails sit in the 0.50–0.69 band — these are the "one truth-zone miss away from passing" cases, the highest-leverage target for scorer-annotation lanes (#144 Lane 1, #97).

## Invalid-fieldpath hallucination rollup

| prefix | offender count (visible in report) |
|---|---|
| parents | 11 |
| family | 10 |
| siblings | 7 |
| greatGrandparents | 5 |
| education | 5 |
| grandparents | 4 |
| laterYears | 2 |
| residence | 1 |

**Shift from r5f:** The greatGrandparents cluster dropped (r5f top: case_028 8 + case_033 5 + case_035 4 = 17 in the ancestor class). The parents/family/siblings cluster is now dominant. This is partly a narrator-identity leak issue (parents.firstName emitted when narrator describes own early life) and partly a family-prefix coercion (LLM emits family.children.* when narrator describes their own adult family).

## 34 failing cases

### christopher-todd-horne (11 failed)

| case | score | phase | subTopic | categories |
|---|---|---|---|---|
| case_002 | 0.40 | developmental_foundations | early_caregivers | schema_gap, llm_hallucination |
| case_042 | 0.50 | developmental_foundations | childhood_pets | llm_hallucination |
| case_043 | 0.50 | midlife | travel_and_world | llm_hallucination |
| case_045 | 0.50 | developmental_foundations | childhood_pets | llm_hallucination |
| case_047 | 0.67 | developmental_foundations | sibling_dynamics | schema_gap |
| case_065 | 0.60 | developmental_foundations | family_origins | llm_hallucination |
| case_070 | 0.53 | midlife | family_life | schema_gap |
| case_079 | 0.57 | developmental_foundations | siblings | (none — passed v3?) |
| case_084 | 0.50 | midlife | children_detailed | (none) |
| case_087 | 0.50 | developmental_foundations | shong_family | defensible_alt_credit |
| case_104 | 0.00 | legacy_reflection | life_lessons | noise_leakage, llm_hallucination |

Pattern: childhood_pets sink (case_042, 045 Christopher — same phenomenon in janice-case_046/066), sibling_dynamics non-numeric (case_047 schema_gap for `siblings.uniqueCharacteristics`), shong_family ancestry-drift (case_087 → #97 target).

### janice-josephine-horne (12 failed)

| case | score | phase | subTopic | categories |
|---|---|---|---|---|
| case_024 | 0.33 | developmental_foundations | early_caregivers | schema_gap, llm_hallucination |
| case_027 | 0.00 | early_adulthood | post_education | llm_hallucination |
| case_028 | 0.00 | developmental_foundations | family_rituals_and_holidays | schema_gap |
| case_035 | 0.30 | developmental_foundations | family_rituals_and_holidays | field_path_mismatch, guard_false_positive (**mnw**) |
| case_039 | 0.00 | developmental_foundations | community_belonging | schema_gap, field_path_mismatch |
| case_046 | 0.33 | developmental_foundations | childhood_pets | llm_hallucination |
| case_049 | 0.50 | developmental_foundations | origin_point | schema_gap |
| case_058 | 0.50 | childhood_origins | birthplace_vs_residence | field_path_mismatch |
| case_061 | 0.00 | middle_adulthood | uncertain_date | schema_gap |
| case_066 | 0.50 | developmental_foundations | childhood_pets | schema_gap |
| case_069 | 0.00 | transitional_adolescence | school_experience | schema_gap, llm_hallucination |
| case_078 | 0.00 | early_adulthood | higher_education | noise_leakage, schema_gap |

Pattern: **family_rituals_and_holidays cluster** (case_028 "Germans from Russia" → parents.notes drift; case_035 faith narrator-leak mnw; case_039 Garrison Dam community-role → parents.occupation drift). case_069 school-years narrative → `education.gradeLevel` three times instead of aggregate `education.schooling` — schema mismatch. Janice has the deepest failure pile (12 vs 11); community/family_ritual axis is her weak spot.

### kent-james-horne (11 failed)

| case | score | phase | subTopic | categories |
|---|---|---|---|---|
| case_014 | 0.33 | developmental_foundations | early_caregivers | field_path_mismatch, llm_hallucination |
| case_020 | 0.00 | transitional_adolescence | civic_entry_age_18 | field_path_mismatch |
| case_033 | 0.00 | developmental_foundations | family_stories_and_lore | schema_gap, field_path_mismatch |
| case_037 | 0.50 | midlife | health_and_body | llm_hallucination |
| case_044 | 0.33 | early_adulthood | first_home | schema_gap, field_path_mismatch |
| case_048 | 0.50 | early_adulthood | parenthood | field_path_mismatch |
| case_059 | 0.50 | transitional_adolescence | career_progression_vs_early | field_path_mismatch |
| case_068 | 0.00 | developmental_foundations | family_loss | llm_hallucination |
| case_080 | 0.60 | developmental_foundations | family_history | schema_gap |
| case_083 | 0.50 | developmental_foundations | grandmother_story | (none) |
| case_093 | 0.70 | midlife | spouse_detail | noise_leakage, guard_false_positive (**mnw**) |

Pattern: Kent has four 0.00 cases (20, 33, 44, 68). case_033 is the flagship WO-SCHEMA-ANCESTOR-EXPAND-01 Lane 1 target (Civil War great-grandfather → military.* not emitted, greatGrandparents.military* emitted). case_044 first_home → family.children.* drift instead of residence/travel. case_020 civic_entry_age_18 → laterYears.significantEvent emitted instead of childhood/adolescent life-event.

## Cluster map to active sequence

| cluster | cases | planned fix |
|---|---|---|
| greatGrandparents path-drift (Mode A) | case_033, case_039, case_081 (already flipped in r5h) | #144 Lane 1 (scorer annotations) |
| greatGrandparents path-missing (Mode B) | case_087 value-drift, remainder | #144 Lane 2 (schema expansion) + #97 |
| Value-axis drift (path matched, value compressed) | case_087 | #97 WO-EX-VALUE-ALT-CREDIT-01 |
| parents/family/siblings narrator-identity leak | case_028, case_039, case_049 | SPANTAG (#90) + LORI-CONFIRM |
| childhood_pets sink | case_042, 045, 046, 066 | separate audit (no WO open) |
| education.gradeLevel vs schooling aggregate | case_069 | separate audit (prompt-side, likely SPANTAG) |
| mnw offenders | case_035, case_093 | WO-LORI-CONFIRM-01 |
| 0.00 floor cases (no clear alt path) | case_020, case_027, case_061, case_068, case_078, case_104 | deep-dive needed; likely mixed LLM-hallucination + section-misbinding |

## Stochasticity notes

Three cases known to jitter across r5f/r5g/r5h from LLM sampling variance (not patch-attributable):

- case_046: 0.333 → 0.667 (r5f→r5g) → 0.333 (r5g→r5h)
- case_068: 0.53 (r5e1) → 0.00 (r5f) — once noted, carried through r5g/r5h
- case_087: 0.50 (r5f) → 0.00 (r5g) → 0.50 (r5h)

Any future flip on these without a code or annotation change is noise.

## Recommended next actions

1. **#144 Lane 1** (scorer annotations for case_033, case_039, case_081-already-done) → r5i eval
2. **#97** (value-alt-credit, case_087) → r5k eval
3. **#144 Lane 2** (schema expansion) conditional on Lane 1 clean
4. Deep-dive audit of the 0.00 floor cases (case_020, 027, 061, 068, 078, 104) — mixed bag, likely section-misbinding + LLM-hallucination. No WO yet.
