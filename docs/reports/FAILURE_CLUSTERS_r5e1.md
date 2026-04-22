# LOOP-01 R5.5 — Failure-Cluster Packs (r5e1 baseline, 45 failing)

**Author:** Claude (overnight run, 2026-04-21 → 22)
**Source:** `docs/reports/FAILING_CASES_r5e1_RUNDOWN.md` (45 cases, joined from `master_loop01_r5e1.json` and `question_bank_extraction_cases.json`).
**Baseline:** r5e1 — 59 pass / 45 fail / 104 total · v3=38/62 · v2=32/62 · mnw=2 (case_035, case_093).
**Purpose:** group the 45 failures into mechanism-homogeneous packs so each next WO has a concrete target set to measure against. Feeds SPANTAG target-pack definition, WO-LORI-CONFIRM-01 pilot scope confirmation, and future truncation-lane scoping.

---

## Rollup — four packs + residuals

| Pack | Cases | N | Shared mechanism | Proposed lane |
|---|---|---:|---|---|
| **1 — Birth-order / sibling arithmetic** | 002, 014, 024, 047 (core) · 048, 070 (adjacent scalar-list consolidation) | 4 + 2 | Narrator uses relational language (`"middle child"`, `"oldest"`, `"youngest of three"`); LLM drops derived integer on `personal.birthOrder` or emits wrong canonical form on `siblings.birthOrder`. List-consolidation on `siblings.firstName` / `family.children.firstName` when multiple names appear. | WO-LORI-CONFIRM-01 (4-field pilot covers this directly). SPANTAG Pass 1 `quantity_or_ordinal` tag can help bind. |
| **2 — Ownership / attribution** | 028, 035, 039, 068, 093 (core) · 033, 043, 044 (soft) | 5 + 3 | Writes about someone else's life event or trait land on narrator-owned fields, or vice versa. The r5e2 ATTRIBUTION-BOUNDARY rule was designed for this class but friendly-fired; proper fix is elicitation-side. | WO-LORI-CONFIRM-01 future extension (faith / spouse-detail follow-ups). SPANTAG Pass 2 subject-beats-section rule partially addresses. |
| **3 — Pets salience** | 025, 042, 045, 046, 066 | 5 | Narrator mentions pet naturally inside surrounding family-life prose (`"I had a horse named Grey — I loved that horse. My sister Verene..."`) and the extractor routes to the surrounding subject (siblings, hobbies) instead of pets. Also `pets.species` granularity drift (`'dog'` when `'Golden Retriever'` is named). | WO-LORI-CONFIRM-01 follow-on (parked as out-of-pilot). Short micro-flow: *"What was the animal? Name? Species?"* |
| **4 — Silent output / fallback drop** | 005, 023, 045, 046, 064, 065, 072, 077, 080, 081, 084, 086, 104 | 13 | Extractor raw emits literally nothing (`(none)` in rundown top-6) on turns that have explicit, well-named scalar answers. Parse-failure and `method=fallback` paths both route here. Largest single cluster by volume (29% of the failures). | TRUNCATION-LANE / WO-EX-TRUNCATION-LANE-01 (#96). SPANTAG explicitly declines this sub-pack as a primary target. Possible dense-input parse-bug intersection. |

**Coverage:** 4 packs cover 6+8+5+13 = **32 cases** (with overlaps for cases 045/046 in Pack 3 ∩ Pack 4). Unique coverage = 30. Residuals (mechanism not dominantly one of the four): 15 cases, inventoried in §5.

---

## Pack 1 — Birth-order / sibling arithmetic

**Core cases (4):** case_002, case_014, case_024, case_047.
**Adjacent (2):** case_048 (children list consolidation), case_070 (children list consolidation + relation drop).

### Shared mechanism

Narrator uses relational / ordinal language that the LLM parses narratively but does not convert to the expected canonical scalar forms:

| Narrator says | Scorer expects | LLM emits |
|---|---|---|
| "I was the youngest of three boys" | `personal.birthOrder = 3` | MISSING |
| "My older sister Sharon ... I came along in '39" | `siblings.birthOrder = older` | `siblings.birthOrder = first` |
| "middle child ... oldest sister Verene, then me, then my little brother James" | `siblings.birthOrder = younger` (for James) | `siblings.birthOrder = third` |
| "two older brothers — Vincent and Jason" | `siblings.firstName = Vincent` + per-sibling record | `siblings.firstName = Vincent, Jason` (consolidated into one value) |

Three sub-mechanisms interlocked:

1. **Arithmetic derivation.** "Middle of three" → `personal.birthOrder = 2` is arithmetic the 8B model reliably refuses to perform in the extraction contract. It names the ordinal ("middle") but doesn't count to the index.
2. **Canonical form drift.** The scorer's birth-order canon is `{older, younger, same_age, unknown}` for `siblings.birthOrder` — a two-token axis relative to the narrator. The LLM emits `{oldest, youngest, first, second, third, middle}` — absolute ordinal labels. These are semantically close but token-axis-incompatible.
3. **List consolidation.** `"Vincent and Jason"` gets emitted as a single `siblings.firstName = "Vincent, Jason"` string instead of two rows. Scorer then partially matches (0.8), and relation / birthOrder can't be attached to the right entity. Same pattern on `family.children.firstName` in cases 048 / 070.

### Case-by-case highlights

- **case_002** — "It was my mom Janice and my dad Kent, and my two older brothers Vincent and Jason. I was the youngest of three boys." → `siblings.birthOrder='youngest'` (wrong axis); `personal.birthOrder=3` missing; `parents.relation='mother'` missing (names harvested without roles).
- **case_014** — "My older sister Sharon was born in 1937, I came along in '39, and then my little sister Linda in '42." → `siblings.birthOrder='first'` (sibling-self labeling instead of sibling-relative-to-narrator); `personal.birthOrder=2` missing.
- **case_024** — "middle child ... Verene Marie ... she was the oldest. Then me. Then my little brother James Peter." → `siblings.birthOrder='third'` on James; `siblings.firstName='James Peter'` (partial 0.8, scorer wants `'James'`); `personal.birthOrder=2` missing.
- **case_047** — "I had two older brothers — Vincent and Jason. Vincent was the oldest, then Jason, then me." → `siblings.firstName='Vincent, Jason'` (consolidated); `siblings.birthOrder='oldest, second, third'` (consolidated); `siblings.relation='brother'` missing.
- **case_048** — "three boys — Vincent, Jason, and Christopher. Vincent was the oldest." → `family.children.firstName='Vincent, Jason, Christopher'` (consolidated); `family.children.relation='son'` missing.
- **case_070** — same family-children consolidation pattern; `family.children.relation='son'` missing with `family.children.firstName='Vincent Edward'` (partial 0.8, first-name-only expected).

### Proposed fix path (by lane)

**Extractor lane (weak):** a prompt rule to prefer per-sibling row emission and two-axis birth-order canonical form (`older`/`younger`) could land a modest lift, but prior prompt-rule experiments (Phase 3 DATE-RANGE PREFERENCE) show prompt-level rules only narrow, don't close, this class. Arithmetic derivation (`middle of three → 2`) is not reachable via prompt rules.

**Interview-engine lane (strong):** this cluster is exactly the intended target of WO-LORI-CONFIRM-01's **4-field pilot**. All four pilot fields appear in this cluster:
- `personal.birthOrder` (arithmetic) → confirmation micro-flow: *"How many children were in your family? What number were you?"*
- `siblings.birthOrder` per-sibling → *"Was [NAME] older or younger than you?"*
- `parents.relation` (role tag missing in 002) → *"And [NAME] — was that your mother or your father?"*

**SPANTAG lane (partial):** Pass 1's `quantity_or_ordinal` tag can separate the narrator ordinal from sibling ordinals as evidence. Pass 2's subject-beats-section rule doesn't directly address birth-order, but cleaner evidence capture may help Pass 2 emit per-sibling rows instead of consolidated lists. Does NOT address arithmetic derivation.

### Gate criteria for "Pack 1 fixed"

Three clean passes across the 4 core cases in a multi-turn eval lane with confirm-pass active. Specifically:

- `personal.birthOrder` hits exact integer on 002 / 014 / 024 after confirmation.
- `siblings.birthOrder` emits `{older, younger}` canonical form on 002 / 014 / 024 / 047 (per-sibling).
- `siblings.firstName` emits one row per sibling on 047 (and adjacent 048 / 070 on the children axis).

If SPANTAG lands default-on first and does not move these four cases, Pack 1 becomes the WO-LORI-CONFIRM-01 pilot-validation target list.

### Risks / notes

- Birth-order arithmetic is robust even in humans when the narrator is counting mid-sentence. Confirmation is the cleanest resolution. Attempting further prompt-side fixes risks the same pattern as r5e2 ATTRIBUTION-BOUNDARY — safety gains offset by friendly-fire on neighboring clean cases.
- **case_079** (`"Vince" vs "Vincent"` partial 0.8, v2_pass=True) is NOT in this pack — it's a name-normalization issue, not arithmetic. Keep distinct.

---

## Pack 2 — Ownership / attribution

**Core cases (5):** case_028, case_035, case_039, case_068, case_093.
**Soft members (3):** case_033 (case-card error, kept for completeness), case_043, case_044.

### Shared mechanism

Writes about someone else's life event or characteristic land on narrator-owned fields, or vice versa. Two directions:

- **Narrator-leak:** content about the narrator's parent / spouse / grandparent lands on `education.schooling` / `education.higherEducation` / `military.*` / `faith.*` — fields schema-owned by the narrator. This is the must_not_write violator class.
- **Parent-leak:** content about the narrator's self-in-context lands on `parents.*` / `grandparents.*` when it should be `community.*` / narrator-owned.

This is the same class the r5e2 ATTRIBUTION-BOUNDARY rule was designed to address — it did clear mnw 2→0 on r5e2 but friendly-fired on 7 clean passes (including case_075 which was the rule's target class), delta -3, rejected. Proper fix is elicitation-side with section-scoped follow-ups, not a prompt rule.

### Case-by-case highlights

- **case_028** — "We were Germans from Russia ... My grandmother Josie's family, the Schaafs, came from Ukraine." → target = `earlyMemories.significantEvent = "Germans from Russia"`; emitted `parents.firstName=Mathias`, `parents.lastName=Schaaf/Zarr`, `grandparents.side=maternal` etc. Content is ancestral, narrator was asked about a family ritual. Attribution pushed everything to parent/grandparent scalars; the section-level `earlyMemories` framing got lost entirely.
- **case_035** — "What role did church or faith play in your family growing up?" → narrator: "My mother Josie went to Mount Marty in Yankton for high school." → emitted `education.schooling='Mount Marty in Yankton for high school'` (narrator-owned). **mnw VIOLATED** on `education.schooling`. Mother's schooling → narrator's `education.schooling` slot. Classic narrator-leak. One of the two live mnw offenders on r5e1.
- **case_039** — "My father Pete worked on the Garrison Dam as a foreman of a finishing crew." → target = `community.organization='Garrison Dam project'` + `community.role='Foreman...'`. Model emitted `parents.firstName=Pete`, `parents.occupation='foreman of a finishing crew...'`. Section was `community_belonging`. Parent-occupation path won over community-org path even though the section was explicitly `community`.
- **case_068** — parent-death story (Father Ervin died December 23, 1967); emitted `parents.notableLifeEvents=<entire reply>` as a single prose blob. v2_pass=True at 0.75, but scorer's value-match loose enough to credit. Adjacent to noise-leak class (Pack 4+) but mechanism is actually "the scalar-narrative boundary got chosen as 'narrative' and the narrative included everything".
- **case_093** — "She went to Bismarck Junior College before we got married." (on spouse Janice) → emitted `education.higherEducation='Bismarck Junior College'` (narrator-owned). **mnw VIOLATED** on `education.higherEducation`. Spouse's schooling → narrator's `education.higherEducation` slot. Second of the two live mnw offenders. Mechanism identical to case_035.

### Soft members

- **case_033** — `military.*` expected for narrator, content describes great-grandfather John Michael Shong's Civil War service. Model correctly routed to `greatGrandparents.militaryBranch/Unit/Event`. **This is a case-card error** (truth zones require narrator military, but content is ancestor military). The r4 Patch J alias (`greatGrandparents.military* ↔ military.*`) was intentionally NOT made bidirectional because emitting ancestor military on narrator fields is the mnw-violator shape. Phase 1 SECTION-EFFECT adjudication has not been applied to this case; it may belong in `case-card-error` bucket separate from model failure.
- **case_043** — `travel.purpose='family vacation'` emitted; scorer expected `'Ancestry connection'`. Model picked the obvious meta-purpose over the narrator's cited reason. Marginal attribution failure; probably not a Pack 2 target.
- **case_044** — residence.place=Germany missing; travel.purpose missing. Expected residence + travel. Got education.earlyCareer=construction worker + travel.destination + family.children.*. Residence slot and travel.purpose got drowned by the child-birth frame. Adjacent to attribution but dominated by field-path-mismatch.

### Proposed fix path (by lane)

**Extractor lane (observed ceiling):** r5e2 attempted an ATTRIBUTION-BOUNDARY fewshot rule targeted exactly at cases 035 / 093 and adjacent (`case_005` spouse-detail, `case_075` mother_stories). It worked on the named targets (case_093 .70 → .90, case_005 .00 → 1.00) but friendly-fired 7 clean cases including case_075 itself. Net -3 vs r5e1. Three-agent convergence REJECTED. The prompt-rule ceiling on this class is below the collateral-damage floor.

**Interview-engine lane (designed target):** WO-LORI-CONFIRM-01 parks this class for future extension — the 4-field pilot doesn't cover faith/education-schooling by design, but the same section-boundary dispatcher + confirmation bank pattern extends naturally. Specifically:
- Faith turns: *"That school you mentioned — was that your school, or your mother's school?"*
- Spouse-detail turns: *"When you say 'before we got married' — is that Janice going to college, or is that you?"*

**SPANTAG lane (partial):** Pass 2's subject-beats-section rule is designed for this. When Pass 1 tags identify a non-narrator subject cleanly (`person=Josie`, `relation_cue=mother`), Pass 2 should route to parent-scoped fields, not narrator-scoped. However, cases 035 and 093 have the narrator-owned field as the SECTION target (`education.*`), so the section pressure is exactly the attribution direction. Pass 2's controlled-prior framing should weigh subject over section here — this IS a designed mechanism test.

### Gate criteria for "Pack 2 fixed"

- `mnw` violations on case_035 and case_093 go to zero while their positive extractions (Catholic denomination, Bismarck mention) remain.
- case_028 gets `earlyMemories.significantEvent` written (at least fuzzy-match).
- case_039 emits `community.organization` / `community.role` alongside (not instead of) `parents.firstName`.
- No friendly-fire on case_075 (mother_stories) or case_005 (marriage_story).

### Risks / notes

- **The r5e2 cautionary tale.** Any future prompt-rule attempt at this class must measure friendly-fire on the explicit watch list: case_003, case_018, case_022, case_034, case_067, case_075, case_088 (the seven regressions on r5e2).
- **SPANTAG expectations are modest.** Pass 2 might flip 035 and 093 cleanly. It will not address case_028 or case_068 (those are not subject-section-disagreement cases).

---

## Pack 3 — Pets salience

**Cases (5):** case_025, case_042, case_045, case_046, case_066.

### Shared mechanism

The narrator mentions a pet naturally inside surrounding family-life prose. The extractor routes to the surrounding subject (siblings / hobbies / family) instead of `pets.*`, or emits `pets.name` without `pets.species` (or vice versa), or drops both entirely.

All 5 cases are in the `childhood_pets` sub-topic under `developmental_foundations`, `school_years` era.

Three sub-mechanisms:

1. **Surrounding-subject wins.** "I had a horse named Grey — I loved that horse. My sister Verene wouldn't go near the barn..." → extractor picks up `siblings.firstName=Verene` and drops pet scalars.
2. **Granularity drift.** "Golden Retriever named Ivan" → emits `pets.species='dog'` (too coarse) when scorer wants `'Golden Retriever'`.
3. **Silent output.** "Buster ... Best dog I ever had" → zero emissions (top-6 is `(none)`).

### Case-by-case

- **case_025** — horse Grey + dog Spot + uncle Johnny mention. Emitted siblings + `hobbies.hobbies=<prose dump>`. Zero pet scalars.
- **case_042** — Golden Retriever Ivan. `pets.name=Ivan` ✓ but `pets.species='dog'` wrong (scorer wants 'Golden Retriever').
- **case_045** — Buster the yellow lab. **Silent output.** Also in Pack 4.
- **case_046** — barn cats + horse Dusty. **Silent output.** Also in Pack 4.
- **case_066** — horse Grey in a long prose turn about family moves. Emitted siblings + parent scalars; zero pet scalars.

### Proposed fix path (by lane)

**Extractor lane:** the `pets.name` / `pets.species` routing was already targeted by R4 Patch C. It fixed the `.notes` sink problem (model was emitting everything as `pets.notes`) but the current failure mode is different — the pet mention isn't landing in `pets.*` at all when surrounded by other-subject prose. Additional prompt rule could try to force pet-mention elevation, but this is the exact pattern (narrow prompt rule against a surrounding-prose class) that r5e2 showed ships collateral damage.

**Interview-engine lane (parked):** WO-LORI-CONFIRM-01 explicitly parks pets as out-of-pilot. The natural confirm micro-flow is: *"You mentioned [ANIMAL] — what was its name? What species was it? Was it yours or the family's?"* — three short questions that land all three scalars deterministically.

**SPANTAG lane:** weak fit. Pass 1 could tag the pet mention as `object` with a species token, but the binding from `{person=narrator, object=horse, pet_name=Grey}` to `{pets.name=Grey, pets.species=horse}` is exactly the schema-binding Pass 2 is supposed to do — and the section/target prior IS `pets.*`, so the section pressure is already correct. The failure isn't section-vs-subject; it's that the LLM is picking the surrounding-subject in competition.

### Gate criteria for "Pack 3 fixed"

- 5/5 cases land `pets.name` + `pets.species` on a confirmation-pass lane (multi-turn eval).
- `pets.species` granularity hits breed-level when breed is named ('Golden Retriever', not 'dog').
- No regression on siblings / hobbies emissions (the surrounding-subject writes that currently dominate).

### Risks / notes

- This pack is the cleanest case for a micro-flow — three deterministic questions resolve all ambiguity. Strongest argument for the confirm-pass extension.
- The `pets.species` scorer currently accepts breed-level (`'Golden Retriever'` credits). If it didn't, Pack 3 would shrink by 1 (case_042).

---

## Pack 4 — Silent output / fallback drop

**Cases (13):** case_005, case_023, case_045, case_046, case_064, case_065, case_072, case_077, case_080, case_081, case_084, case_086, case_104.

### Shared mechanism

Extractor top-6 raw emission is literally `(none)`. The turn produced zero accepted items, either via:

- **method=fallback / rules-fallback** (LLM parse failure or LLM returned empty → rule-based emitter fallback emits nothing when it has no rule match).
- **VRAM-GUARD truncation** cutting input mid-reply before the model can parse the section that carries the expected fields.
- **Post-extract guard drop** (R4-A answer-dump length cap, CLAIMS-02 validator drop, TURNSCOPE cross-branch filter) where the guards eat every candidate extraction.

Partition by type:

| Sub-type | Cases | Dominant mechanism |
|---|---|---|
| Dense genealogy (truncation-starved) | 065, 080, 081, 084, 086 | Large-chunk reply; VRAM-GUARD truncates; rules-fallback empty. Matches SPANTAG spec's 7-case "truncation-starved" sub-pack. |
| Explicit-answer drops | 005, 023, 064, 072 | Narrator gives a crisp, scalar-able answer ("Kent Horne on October 10th, 1959. I was twenty and he was nineteen.") and the extractor still emits nothing. No truncation pressure. |
| Pet silent | 045, 046 | Also in Pack 3. Short replies. Silent output on well-scoped question. |
| Sibling silent | 077 | Well-structured sibling-listing reply. Silent output. |
| Legacy-reflection silent | 104 | `laterYears.lifeLessons` on a late-era reflection turn. Silent. |

### The scariest sub-sub-class: explicit-answer drops (cases 005, 023, 064, 072)

These four are the **most anomalous** in the rundown:

- **case_005:** "I have four kids. My oldest is Vincent Edward, then Gretchen Jo who was born October 4th, 1991 in Austin, Texas. Then Amelia Fay, born August 5th, 1994, and my youngest is Cole Harber, born April 10th, 2002." — crisp, unambiguous, four dated children named. **Zero emissions.**
- **case_023:** "I married Kent Horne on October 10th, 1959. I was twenty and he was nineteen." — scalar-perfect. **Zero emissions.**
- **case_064:** long marriage-story turn with "October 10, 1959" as the explicit date. **Zero emissions.**
- **case_072:** marriage-children turn with "October 10, 1959 ... born December 24, 1962 in Williston, North Dakota." **Zero emissions.**

These cases are not truncation-starved (replies are within budget). They are not subject-section mismatch (targets are `family.spouse.*` / `family.marriageDate` / `family.children.*` and content matches). They are not guard-drops (no guard log signature). Something is killing the extraction before emission — the likeliest candidate is a parse-failure class the rundown didn't tag (the console shows `method=llm` but the raw output isn't surviving the parser).

**Action item flagged for investigation in the TRUNCATION-LANE / TRUNC-01 WO:** a targeted `api.log` scan of these four cases specifically, looking for `[extract-parse] Could not parse ANY JSON from LLM output` or `[extract] LLM extraction returned no items` log lines. If those are present, the parser is the suspect; if absent, the LLM itself is returning degenerate output (possibly repetition suppression firing, possibly a template-level pathology).

### Case-by-case (by sub-type)

**Dense genealogy (5):**
- case_065 — "His grandmother was Elizabeth Shong — everybody called her Lizzie. She was the youngest of eight kids..." — full Shong genealogy. Silent.
- case_080 — George Horne + Elizabeth Shong + Ross ND 1902 homestead + six children enumeration. Silent.
- case_081 — John Michael Shong born Nancy Lorraine 1829, Nicholas-as-father, four siblings, Schong name origin. Silent.
- case_084 — Gretchen/Amelia/Cole enumeration with dates. Silent.
- case_086 — career-family blend: construction, Germany, Vincent, Janice, Chris born Williston 1962. Silent.

**Explicit-answer drops (4):** 005, 023, 064, 072 (detailed above).

**Pet silent (2):** 045, 046 (also in Pack 3).

**Sibling silent (1):** 077 — "I had two sisters. Sharon was the oldest, born April 8, 1937 ... Linda was the youngest, born July 27, 1942."

**Legacy-reflection silent (1):** 104 — "Family is everything. That sounds simple but it's the truth."

### Proposed fix path (by lane)

**Extractor lane:** this cluster is what the TRUNCATION-LANE WO (#96, `WO-EX-TRUNCATION-LANE-01_Spec.md`, already drafted) is scoped for. The specific explicit-answer-drops sub-sub-class (005 / 023 / 064 / 072) is an **escalation of that WO's scope** — those four cases should be on the TRUNCATION-LANE target pack for diagnosis even though they aren't truncation-dominated.

**Interview-engine lane:** WO-LORI-CONFIRM-01 helps only if confirmation surfaces the missing fields (e.g., marriage-date confirmation on 023/064/072). Confirm-pass is reactive to staged `suggest_only` writes; it doesn't help when the extractor emits nothing to stage. NOT a fix for Pack 4.

**SPANTAG lane:** **explicitly declined.** SPANTAG spec §4 (Goal #4 primary sub-pack) lists the 7 truncation-starved stubborn cases as NOT SPANTAG targets; the "truncation_rate" metric is informational, not a ship gate. Pack 4's dense-genealogy sub-type overlaps heavily with that SPANTAG non-target sub-pack. The explicit-answer-drops sub-type is a new finding — may or may not overlap with SPANTAG's Pass 1 parse success metric once Pass 1 lands.

### Gate criteria for "Pack 4 fixed"

Two-phase:

**Phase A — diagnose.** For each of the 13 cases, identify the drop mechanism precisely: parse failure / LLM empty / VRAM-GUARD truncation / post-extract guard. Audit log trace per case. Output: one-line mechanism per case.

**Phase B — triage.** Based on Phase A:
- Parse failures → parser-hardening fix (bracket search, tolerant JSON, fallback path shape).
- LLM-empty → few-shot starvation or prompt-level issue; probably NOT fixable without a different lever (re-enable PROMPTSHRINK for Pass 2 / model swap).
- Truncation → input-budget lever (chunking, staged pipeline, Pass 1 span contract that doesn't re-echo).
- Guard drops → targeted guard-relaxation with careful mnw audit.

### Risks / notes

- This is the **single largest lever** in the 45-case failure list. 13 cases silent = 13/45 = 29% of failures.
- Critical: 045/046 are double-counted in Pack 3. De-duplicated unique contribution = 11 cases.
- The explicit-answer-drops sub-sub-class is the most puzzling — these turns have all the structural hallmarks of clean wins. Investigation candidate #1 for TRUNCATION-LANE / SPANTAG Pass 1 parse success.

---

## 5. Unclustered residuals (15 cases)

Cases from the 45-case rundown that don't dominantly fit any of the four packs. One-line mechanism per case.

| Case | Era / section | Mechanism |
|---|---|---|
| case_058 | early_childhood / birthplace_vs_residence | `residence.place` missing; model emitted `personal.placeOfBirth=Fargo` AND `personal.placeOfBirth=West Fargo` (both), never routed second to residence. Field-path-mismatch. |
| case_027 | early_adulthood / post_education | `education.higherEducation='Bismarck Junior College, Speech, History'` — extractor dropped "credits transferred to UND" tail. Normalization / value-shape. |
| case_037 | midlife / health_and_body | `health.majorCondition='knees gave out due to construction-related injuries'` (semantically correct, scorer wanted `'Knee problems from construction work'`). Scorer fuzzy-match tight. |
| case_049 | school_years / origin_point | `personal.dateOfBirth` missing despite Phase 2 narrator-identity-priority rule. Possible rule not firing or target-scoping. Noted in WO-EX-NARRATIVE-FIELD-01 report as remaining carryover. |
| case_059 | adolescence / career_progression_vs_early | `education.earlyCareer` = whole narrator reply as prose blob (R4-A answer-dump didn't drop it). `education.careerProgression='foreman'` missing. Noise-leak + schema-gap. |
| case_061 | midlife / uncertain_date | `family.marriagePlace="St. Mary's"` missing, model emitted `family.marriageDate=1956` + `=1957`. Marriage-place slot dropped entirely. |
| case_069 | adolescence / school_experience | `education.schooling` + `education.higherEducation` missing. Model emitted `personal.fullName='her'` (small hallucination). Silent-adjacent + tiny-hallucination. |
| case_078 | early_adulthood / higher_education | `education.higherEducation='Bismarck Junior College, Speech and History, credits transferred to UND'` missing. Model emitted `family.children.*` + `parents.firstName=Josie` from context bleed. Noise-leak / narrator-field drop. |
| case_079 | school_years / siblings | `siblings.firstName='Vince'` (partial 0.8) vs expected `'Vincent'`. Name-normalization. v2_pass=True (not a hard fail). |
| case_082 | school_years / childhood_moves | `residence.place`=<full reply prose>, `personal.placeOfBirth=Spokane, Washington` missing. Stubborn-pack member; SECTION-EFFECT-01 adjudication = dual_answer_defensible. Noise-leak + must-extract drop. |
| case_083 | school_years / grandmother_story | `grandparents.memorableStory`=<full reply prose> (partial 0.74). v2_pass=True. Noise-leak on a v2 pass. |
| case_085 | school_years / father_story | `parents.firstName=Peter` hit, `parents.lastName` + `parents.occupation` missing. Truncation-partial. Stubborn-pack member. |
| case_087 | school_years / shong_family | `grandparents.memorableStory` emitted (prose), `grandparents.ancestry='French (Alsace-Lorraine)'` missing. Ancestry-scalar drop. Stubborn-pack member. |
| case_103 | early_adulthood / germany_years | `residence.place`=<full reply prose>. Noise-leak parallel to case_082 / case_068. |
| case_020 | adolescence / civic_entry_age_18 | `education.earlyCareer='Was already working construction by age eighteen'` missing. Model emitted `laterYears.significantEvent='turning eighteen'` and `laterYears.significantEvent='already working construction'`. Era-mismatch (adolescence → laterYears) field-path-mismatch. |

**Observation:** many residuals cluster secondarily around two themes:

- **Noise-leak / prose-as-value** (case_059, case_068, case_082, case_083, case_103) — scalar fields receive entire paragraph as value; R4-A answer-dump guard has a `>500 chars` threshold that most of these slide under. Could be a Pack 5 if we promoted.
- **Normalization drift** (case_027, case_037, case_070, case_079) — value is semantically correct but scorer's fuzzy-match rejected. Scorer-policy work (`alt_defensible_values`, #97) addresses.

These secondary themes are not promoted to full packs tonight because (a) they don't have a single dominant fix lane, and (b) the four packs Chris named are enough load-bearing weight for the next WO cycle.

---

## 6. Cross-pack overlap map

```
Pack 1 (Birth-order) ∩ Pack 4 (Silent) = {case_077}            [sibling-list silent]
Pack 3 (Pets)        ∩ Pack 4 (Silent) = {case_045, case_046}  [pet silent]
Pack 2 (Attribution) ∩ Pack 4 (Silent) = ∅
Pack 1 ∩ Pack 2 = ∅
Pack 1 ∩ Pack 3 = ∅
Pack 2 ∩ Pack 3 = ∅
```

Three overlaps total (045, 046, 077), all between a semantic pack and the fallback-drop pack. Meaning: **when a pet or sibling question hits the fallback drop, it's still pack-3 or pack-1 content — the drop is a Pack 4 mechanism layered on top.**

---

## 7. Pack → next-WO mapping

| Pack | Next WO most relevant | Role |
|---|---|---|
| Pack 1 | WO-LORI-CONFIRM-01 | 4-field pilot covers this directly; this pack is the pilot's validation target list. |
| Pack 2 | WO-LORI-CONFIRM-01 (future extension) | ATTRIBUTION-BOUNDARY prompt rule rejected on r5e2; elicitation-side is the remaining lever. SPANTAG Pass 2 subject-beats-section partial assist. |
| Pack 3 | WO-LORI-CONFIRM-01 (parked as out-of-pilot) | Cleanest case for micro-flow; strongest argument for pets extension. |
| Pack 4 | WO-EX-TRUNCATION-LANE-01 (#96) | Dense genealogy sub-type is the explicit target. Explicit-answer-drops sub-sub-class needs investigation. |
| Residuals (noise-leak) | Future prompt-rule narrowing or scorer alt_defensible_values | Not a primary lane. |
| Residuals (normalization) | #97 alt_defensible_values scorer policy | Scorer-side. |

---

## 8. Target-pack recommendations for open WOs

**WO-EX-SPANTAG-01 target pack (from this clustering):**
- Primary: Pack 2 core (028, 035, 039, 068, 093) — subject-beats-section rule's natural test cases, plus mnw pair.
- Secondary: Pack 3 (025, 042, 045, 046, 066) — pets.* routing under section-pressure, informative.
- Explicitly excluded: Pack 4 (all 13 silent-output cases).
- Keep existing SPANTAG primary sub-pack (008, 009, 018, 082) from SECTION-EFFECT adjudication — overlap is minimal, those are dual-answer-defensible, not in any of the four r5e1 failure packs.

**WO-LORI-CONFIRM-01 pilot-validation target list:**
- Pack 1 core (002, 014, 024, 047).
- Pack 2 mnw offenders (035, 093) — target for future extension, not v1 pilot.
- Pack 3 (parked) — future extension candidate.

**WO-EX-TRUNCATION-LANE-01 target pack:**
- Pack 4 all 13 cases.
- Escalation focus: explicit-answer-drops sub-sub-class (005, 023, 064, 072).
- Overlap with stubborn-pack truncation-starved 7: case_065, case_080, case_081, case_084, case_086 already in stubborn-15; case_077, case_104 are new additions.

---

## 9. Changelog

- 2026-04-21 → 22 (overnight): Initial draft. 45 r5e1-failing cases clustered into 4 packs + 15 residuals. Overlap map + next-WO mapping included. Feeds SPANTAG target-pack definition and WO-LORI-CONFIRM-01 pilot validation.
