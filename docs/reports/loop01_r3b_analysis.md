# LOOP-01 R3b Master Eval — Failure Analysis & R4 Patch Plan

Generated: 2026-04-19
Source: `master_loop01_r3b.json` (104 cases, live run, 2026-04-19T08:28:44)

## Top line

| Metric | R3b | Baseline (R2 v2) | Δ |
|---|---:|---:|---:|
| Overall pass | 50/104 (48.1%) | — | — |
| Contract v2 | 25/62 (40.3%) | 32/62 (51.6%) | **−7** |
| Contract v3 (truth-zone) | 28/62 (45.2%) | — | — |
| v2 avg score (contract) | 0.485 | — | — |
| must_not_write violations | 2/163 (1.2%) | — | — |
| must_extract recall | 91/177 (51.4%) | — | — |
| should_ignore leak | 12/68 (17.6%) | — | — |

**Headline: contract subset regressed 32 → 25 on v2 compat.** R3 Patches 1-4 did not move the core contract needle. Log-visible `negation-guard` fires (which were the R3 target) register only 2/54 in the scorer because most log-observed strips happened in style cases, not contract cases.

## Failure taxonomy (54 fails)

Raw categories (non-exclusive):
- `schema_gap` — 26
- `field_path_mismatch` — 25
- `llm_hallucination` — 11
- `noise_leakage` — 9
- `guard_false_positive` — 2

Re-clustered by root cause for R4 patch planning:

| Group | Cases | % of fails | Priority |
|---|---:|---:|---|
| A. Answer-dump (whole monologue → scalar value) | 13 | 24% | P0 |
| B. Zero-raw on parenthood/relationship | 4 | 7% | P0 |
| C. Pets → `.notes` sink | 6 | 11% | P1 |
| D. Narrator first-person birthOrder | 3 | 6% | P1 |
| E. Relation router safety (uncle/aunt/sibling) | 4–6 | ~10% | P0 (safety) |
| F. Contrast-affirmation guard FP | 2 eval, many log | — | P1 |
| G. `grandparents.ancestry` + `.birthPlace` schema | 3 | 6% | P1 |
| H. Write-time normalisation (birthOrder, dates, names) | 5–8 | 10–15% | P2 |
| I. Field aliases (education.*, parents.deathDate, residence vs travel) | 5–6 | 10% | P1 |
| J. Ancestor military routing | 2 | 4% | P2 |
| K. `family.marriagePlace` schema | 1 | 2% | P3 |

## Group details

### Group A — Answer-dump (scalar value = whole monologue)

**Cases (13):** 032, 065, 068, 070, 072, 075, 077, 080, 081, 082, 083, 084, 103

**Shape:** LLM returns a single-item array where the `value` is the narrator's entire paragraph (400–1000 chars) and the `fieldPath` is one scalar field like `grandparents.side='My grandfather Ervin was born Nov 12th 1909...'` or `family.marriageDate='Kent and I got married October 10, 1959. I was twenty...'`.

**Examples:**
- case_032 — `grandparents.side` = 224-char monologue (expected `'paternal'`)
- case_072 — `family.marriageDate` = 622-char paragraph (expected `'1959-10-10'`)
- case_081 — `grandparents.ancestry` = 1032-char research dump (expected `'French (Alsace-Lorraine), German'`)
- case_103 — `residence.place` = 510-char anecdote (expected `'Germany'`)

**Root cause:** prompt doesn't enforce that the `value` be the specific fact, not surrounding prose. The LLM falls back to "here is the relevant passage" when it can't cleanly extract.

**Fix (R4 Patch A):**
1. Prompt rule: "value MUST be the specific fact (a name, date, place, role), NOT the surrounding narrative prose."
2. Post-extraction guard in `extract.py`: if `fieldPath` is scalar AND `len(value) > 120` OR `value` contains 2+ sentence-ending punctuation → reject item. Log `answer_dump_reject` counter.
3. Keep permissive for narrative-typed fields (`memorableStory`, `notableLifeEvents`, `significantEvent`) — cap at ~400 chars instead.

### Group B — Zero-raw on content-rich input

**Cases (4):** 005, 012, 013, 023 — all score 0.00, all `raw_items=[]`.

- 005, 013 — parenthood subtopic; narrator describing their kids (Chris describing Gretchen; Kent describing Christopher's 1962 birth)
- 012, 023 — relationship_anchors

**Shape:** extractor returned empty array. Either LLM produced malformed JSON that fell through bracket_search to rules-only (zero rule hits), or prompt doesn't cover these subtopics and LLM emitted `[]`.

**Verification:** cross-check against api.log for JSON parse failures at these case IDs.

**Fix (R4 Patch B):** add few-shots for parenthood and relationship_anchors:
- "Our first son Christopher was born December 24, 1962 in Williston, North Dakota" →
  `family.children.firstName=Christopher`, `family.children.dateOfBirth=1962-12-24`, `family.children.placeOfBirth=Williston, North Dakota`

### Group C — Pets route to `.notes` instead of `.name`/`.species`

**Cases (6):** 010, 017, 025, 045, 046, 066 — all `childhood_pets`.

- 010, 017 — `'pets.notes'` twice instead of `pets.name='Ivan'` + `pets.species='dog'`
- 025 — `'personal.nameStory'` + `'pets.notes'` (also a relation confusion)
- 045, 046, 066 — partial: wrote name OR species but not both

**Root cause:** LLM defaults to `pets.notes` when schema offers both. Likely `pets.name`/`pets.species` are either absent from the prompt's field-enum or not cued strongly enough by few-shots.

**Fix (R4 Patch C):**
1. Verify `pets.name` and `pets.species` are present in the extractor's field-enum the prompt sees.
2. Add few-shot: "I had a dog named Ivan" → `pets.name=Ivan`, `pets.species=dog` (NOT `pets.notes='dog named Ivan'`).
3. Optional reject/remap: if extractor writes `pets.notes` matching `^([A-Z][a-z]+) (the )?(dog|cat|horse|bird|...)`, split into name+species.

### Group D — Narrator first-person birthOrder routes to siblings.birthOrder

**Cases (3):** 002, 014, 024

Narrator says "I was the youngest/middle/oldest" →
- Expected: `personal.birthOrder` = '2' / '3' / etc.
- Actual: `siblings.birthOrder = 'youngest'` (semantically correct but wrong entity)

Plus hallucination sub-pattern: case_014 flipped younger↔older, case_024 mislabelled middle as oldest.

**Fix (R4 Patch D):**
- Router rule: if `fieldPath=birthOrder` and input antecedent is first-person singular (`I`/`me`/`my`), route to `personal.birthOrder`, not `siblings.birthOrder`.
- Could be implemented as prompt rule or post-extraction alias.

### Group E — Relation router safety (mnw violations)

**Cases (2 mnw + 2+ non-mnw):** 008, 094 (+ 028, 035, 078)

- case_008 — narrator describes uncle James; extractor writes `family.children.firstName='James'`, `family.children.placeOfBirth='in a car on the way to Richardton Hospital'`. Both mnw violations.
- case_094 — narrator describes sibling; extractor writes `parents.firstName='Ervin'`, `parents.middleName='Leila'`, `parents.lastName='Horne'`. Mnw violations.
- case_028, case_035 — narrator's sister Verene written as `family.children.relation='sister'` (own child).
- case_078 — narrator's son Vincent correctly as `family.children`, but educational history got mis-routed to parents (`parents.occupation='went to Capitol Business College'` — that was narrator's *mom* attending a college, not narrator's parent's occupation).

**Fix (R4 Patch E):** hard router guards in extract.py:
- Reject `family.children.*` if source sentence contains `uncle|aunt|nephew|niece|cousin` cue without `my son|daughter|child` anchor.
- Reject `parents.*` if source sentence contains `brother|sister` cue without `my mother|father|mom|dad` anchor.
- Log to `relation_router_reject` counter for visibility.

This is **safety-critical** because mnw violations contaminate the knowledge graph.

### Group F — Contrast-affirmation negation-guard FP

**Cases (2 eval):** 008, 094. **Log cases (many):** community.role='one-on-one person', health.majorCondition='pretty healthy', health.milestone='tough', health.lifestyleChange='always outside, always working', health.majorCondition='healthy'.

**Pattern:** narrator says "not X, (but/more of a/just) Y" → Patch 4's `_apply_negation_guard` strips both X and Y. The Y is a legit affirmation that belongs in the graph.

**Fix (R4 Patch F):** extend `_apply_negation_guard` in `server/code/api/routers/extract.py`:
- Detect contrast-affirmation patterns:
  - `not X, (but |more of a |more like |just )Y`
  - `never X, but Y`
  - `I'm not X. I'm Y`
  - `don't X. Y`
- When detected, protect the affirmative clause's extractions; strip only the negated clause's extractions.
- Must NOT weaken R3 Patch 4's existing narrator-scope protection — this is additive.

### Group G — `grandparents.ancestry` schema/cueing gap

**Cases (3):** 031, 065, 081

Truth expects `grandparents.ancestry` = 'Germans from Russia' / 'French (Alsace-Lorraine), German'. Either field isn't in schema, or prompt doesn't cue it. Case_032 also missed `grandparents.birthPlace='North Dakota'`.

**Fix (R4 Patch G):**
1. Verify `grandparents.ancestry` and `grandparents.birthPlace` are in field-enum.
2. Few-shot: "My grandparents were Germans from Russia" → `grandparents.ancestry='Germans from Russia'`.

### Group H — Write-time normalisation (scorer partial-credit cases)

**Cases (~5–8):** 002, 037, 040, 047, 048, 059, 069, 079 — all show `status='partial'` (score 0.74–0.80) that fall under the 0.7 bar.

Examples:
- case_002 — `personal.birthOrder='3'` vs `'youngest'`
- case_079 — `siblings.firstName='Vincent'` vs `'Vincent Edward'`
- case_040 — `community.yearsActive='1997-2026'` vs `'almost twenty-nine years'`

**Shape:** extractor's value is semantically right but lexically different. Scorer marks partial.

**Fix (R4 Patch H) — two paths:**
- (a, recommended) Write-time normaliser: normalise `birthOrder` ('youngest'/'middle'/'oldest' → ordinal with sibling count); normalise dates to ISO when extractable; strip suffix middle names from firstName on first write.
- (b) Scorer equivalence sets — cosmetic, doesn't improve stored data quality.

Recommend (a) primary.

### Group I — Field-name aliases

**Cases (5–6):** 009, 015, 020, 027, 044, 078

Semantic-synonym misses where truth field and extractor field are both legitimate:
- `education.careerProgression` ↔ `education.earlyCareer` (009, 020)
- `education.schooling` ↔ `education.higherEducation` (027, 078)
- `parents.deathDate` ↔ `parents.notableLifeEvents` (015)
- `travel.destination=Germany` ↔ `residence.place=Germany` (044 — Kent relocated for work, not just visited)
- `personal.notes='Germans from Russia'` ↔ `earlyMemories.significantEvent` or `grandparents.ancestry` (028)

**Fix (R4 Patch I):** add bidirectional aliases to the router. Each alias should log which direction it fired so we can later decide whether to collapse.

### Group J — Ancestor military routing

**Cases (2):** 033, 034

Truth expects root `military.*` for narrator's great-great-grandfather's Civil War service. Extractor writes `greatGrandparents.militaryBranch`, `.militaryUnit`, `.militaryEvent` (R3 Patch 1 added these).

**Options:**
1. Add bidirectional alias `greatGrandparents.military* ↔ military.*` with subject-scope tag.
2. Update truth expectations to match the new nested schema.
3. Deprecate `greatGrandparents.military*` and route ancestor military to `military.*` with a `subject` field.

Recommend (1) for R4 — low risk, keeps both paths. Revisit schema design in V4.

### Group K — `family.marriagePlace` schema

**Case (1):** 061 — truth expects `family.marriagePlace="St. Mary's"`. Field may be missing from schema.

**Fix (R4 Patch K):** add `family.marriagePlace` to schema if missing; add few-shot.

## Cross-cutting observations

1. **Patch 4 (negation-guard narrator-scope) is working in the log** — visible cases of stripped legit values match contrast-affirmation, not broad over-reach. But it moved 0 cases in the contract scorer. The real damage is in style cases which the contract v2 scorer doesn't count.

2. **Three fails scored 0.53–0.57 with zero categories** (case_068, 079, 083) — these are "partial" cases just below the 0.7 bar. They're best fixed by normalisation (Group H), not prompt/router changes.

3. **2 must_not_write violations** — both are relation-router errors, not hallucinations. Group E is the highest-safety-priority patch.

4. **Zero-raw cluster (Group B) is pure alpha** — 4 cases of 0.00 score from empty extractor output. Any intervention there is pure upside. Verify in api.log whether these hit JSON parse failures (in which case R4-A's cap-length rule may help — LLM over-verbose on long prose → parse fails).

## R4 patch order (recommended)

| # | Patch | Reason |
|---|---|---|
| 1 | E — Relation router safety | Eliminates mnw violations (graph contamination) |
| 2 | A — Scalar value-length cap | 13 cases, biggest single lift |
| 3 | B — parenthood/relationship few-shots | 4 × 0.00-score cases, quick win |
| 4 | F — Contrast-affirmation guard exception | Correctness; fixes what R3 P4 partially addressed |
| 5 | I — Field aliases batch | 5–6 cases, mechanical |
| 6 | C — Pets few-shot + remap | 6 cases, isolated |
| 7 | D — Narrator birthOrder scoping | 3 cases |
| 8 | G — grandparents.ancestry coverage | 3 cases |
| 9 | H — Write-time normaliser | Partial-credit cases |
| 10 | J — Ancestor military alias | 2 cases |
| 11 | K — family.marriagePlace | 1 case |

Expected combined lift on contract v2: **+18 to +25 cases** (recovery of R2 baseline plus forward gain). Realistic conservative estimate: **recover to 30–35/62**.

## Eval hygiene notes

- `expected_extractor_results.should_pass` says 50/50, `actually_passed` = 24 → eval harness has a 26-case drift where cases predicted to pass didn't, and 26 predicted-fail cases did pass. Worth a harness-level audit after R4 lands.
- `v2_baseline.total_v2_rate` = 32.7% (34/104). That's a noisier metric than contract-subset v2; stick to contract v2 for R3/R4 comparison.
