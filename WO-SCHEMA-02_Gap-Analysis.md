# WO-SCHEMA-02 -- Life Map Coverage Expansion

**Status:** SPECCED -- ready for implementation  
**Created:** 2026-04-15  
**Updated:** 2026-04-16 (execution pack added)  
**Source:** Live audit of EXTRACTABLE_FIELDS vs 37-section interview roadmap

---

## Objective

Expand Hornelore's extraction schema so the life map is no longer only strong in identity / family / school / early career / residence, but can also capture the next major roadmap phases that narrators actually talk about.

Target outcome:

```
question_bank section
-> narrator answer
-> canonical field target exists
-> extractor accepts it
-> projection / review can hold it
```

This WO is about missing schema authority, not model replacement.

---

## Why This WO Exists

Current state from the audit:

The extractor is solid for: identity, parents/siblings/spouse/children, schooling/early career, residences, and a thin layer of memories/hobbies/later-years.

But when narrators move into uncovered life map phases, the system does one of three bad things:

1. Rejects the data (validation rejects invented paths)
2. Collapses it into catch-alls like `earlyMemories.significantEvent`
3. Accepts LLM-invented paths that have no canonical home and then drops them

That means the life map is not yet phase-complete.

---

## Hard Rules

```
1. Add canonical targets first. Do not solve schema gaps with aliases alone.
2. Add aliases only where repeated invented LLM paths are already seen in logs.
3. Do not expand narrative/phenomenology sections in this WO.
4. Do not redesign relationship modeling beyond what is needed for canonical capture.
5. Rerun extraction eval after schema changes and report the coverage delta.
```

---

## Current Coverage (Baseline)

### Well-Covered Sections (extraction fields exist)

| Interview Section | EXTRACTABLE_FIELDS | Notes |
|---|---|---|
| identity | `personal.*` (5 fields) | Solid |
| origins | `parents.*`, `earlyMemories.significantEvent` | Decent, missing grandparents |
| early_home / childhood | `earlyMemories.*` (2 fields) | Thin -- only firstMemory + significantEvent |
| school / school_life | `education.schooling` | Single field |
| education | `education.higherEducation` | Single field |
| first_job / career | `education.earlyCareer`, `education.careerProgression` | Covered |
| marriage | `family.spouse.*`, `family.marriage*` | Good (8 fields) |
| children | `family.children.*` (6 fields) | Good |
| hobbies | `hobbies.hobbies`, `hobbies.personalChallenges` | Decent |
| homes | `residence.*` (4 fields) | Good |
| lessons / legacy | `laterYears.*` (3 fields), `additionalNotes.unfinishedDreams` | Thin |

---

## In Scope -- Priority 1-7

### Priority 1 -- Grandparents

Questionnaire surface already exists; extractor has zero canonical targets today.

**Interview section:** origins  
**Questionnaire fields exist:** side, firstName, middleName, lastName, maidenName, birthDate, birthPlace, ancestry, culturalBackground, memorableStories  
**EXTRACTABLE_FIELDS:** ZERO  
**Impact:** When narrator says "My grandmother came from Russia" -- data has nowhere to go.

Add canonical fields:

```
grandparents.side              (maternal/paternal)     repeatable: grandparents   candidate_only
grandparents.firstName                                 repeatable: grandparents   candidate_only
grandparents.lastName                                  repeatable: grandparents   candidate_only
grandparents.maidenName                                repeatable: grandparents   candidate_only
grandparents.birthPlace                                repeatable: grandparents   candidate_only
grandparents.ancestry                                  repeatable: grandparents   candidate_only
grandparents.memorableStory                            repeatable: grandparents   suggest_only
```

### Priority 2 -- Military

**Interview section:** military  
**Questionnaire fields:** NONE  
**EXTRACTABLE_FIELDS:** ZERO  
**Impact:** Very common in narrator demographic. Currently dropped or aliased nowhere.

Add canonical fields:

```
military.branch                (Army, Navy, etc.)      suggest_only
military.yearsOfService        (e.g. "1965-1968")      suggest_only
military.rank                  (highest attained)       suggest_only
military.deploymentLocation                             repeatable: military   suggest_only
military.significantEvent                               repeatable: military   suggest_only
```

### Priority 3 -- Faith & Values

**Interview section:** faith  
**Questionnaire fields:** NONE  
**EXTRACTABLE_FIELDS:** ZERO  
**Impact:** Common topic for older narrators. Nowhere to land.

Add canonical fields:

```
faith.denomination             (Catholic, Lutheran)     suggest_only
faith.role                     (choir, deacon, etc.)    suggest_only
faith.significantMoment                                 suggest_only
faith.values                                            suggest_only
```

### Priority 4 -- Health

**Interview section:** challenges (partially)  
**Questionnaire fields:** healthMilestones, lifestyleChanges, wellnessTips  
**EXTRACTABLE_FIELDS:** ZERO  
**Impact:** Comes up constantly in later years discussions.

Add canonical fields:

```
health.majorCondition                                   repeatable: health   suggest_only
health.milestone                                        suggest_only
health.lifestyleChange                                  suggest_only
```

### Priority 5 -- Community & Civic Life

**Interview section:** community  
**Questionnaire fields:** education.communityInvolvement exists but not extractable  
**EXTRACTABLE_FIELDS:** ZERO  
**Impact:** Civic life matters to this generation. Currently aliased to laterYears.significantEvent.

Add canonical fields:

```
community.organization                                  repeatable: community   suggest_only
community.role                                          repeatable: community   suggest_only
community.yearsActive                                   repeatable: community   suggest_only
community.significantEvent                              suggest_only
```

### Priority 6 -- Pets

**Interview section:** pets  
**Questionnaire fields:** name, species, breed, birthDate, adoptionDate, notes  
**EXTRACTABLE_FIELDS:** ZERO  
**Impact:** Emotional anchor topic. Currently routed to hobbies.hobbies or dropped.

Add canonical fields:

```
pets.name                                               repeatable: pets   candidate_only
pets.species                                            repeatable: pets   candidate_only
pets.notes                                              repeatable: pets   suggest_only
```

### Priority 7 -- Travel

**Interview section:** travel  
**Questionnaire fields:** hobbies.travel exists but not extractable  
**EXTRACTABLE_FIELDS:** ZERO  

Add canonical fields:

```
travel.destination                                      repeatable: travel   suggest_only
travel.purpose                                          repeatable: travel   suggest_only
travel.significantTrip                                  suggest_only
```

---

## Out of Scope

Do not solve these in this WO:

- grief_rebuilding (narrative, emotional -- not entity-structured)
- caregiving (process/relationship, not discrete facts)
- migration (overlaps with residence + origins, needs careful dedup)
- blended_family (complex relationship modeling)
- identity_belonging (cultural/identity narrative)
- proud / achievement narrative
- teen identity blocks
- cars (could be hobbies.hobbies catch-all)
- technology (could be hobbies.hobbies or laterYears catch-all)
- world_events (contextual, not personal facts)
- 6 youth sections (specialized, likely need separate question bank)

Those stay for WO-PHENO-01 or later narrative-layer work. The gap analysis already marks these as harder-to-structure sections better handled outside strict extraction.

---

## Also Missing: Questionnaire Fields Without Extraction Targets

These exist in the questionnaire (bio-builder-questionnaire.js) but have no EXTRACTABLE_FIELDS entry:

- `education.communityInvolvement`
- `education.mentorship`
- `laterYears.adviceForFutureGenerations`
- `hobbies.worldEvents`
- `hobbies.travel`
- `health.healthMilestones`
- `health.lifestyleChanges`
- `health.wellnessTips`
- `technology.firstTechExperience`
- `technology.favoriteGadgets`
- `technology.culturalPractices`
- `additionalNotes.messagesForFutureGenerations`

---

## Required File Targets

Claude must inspect and patch the real repo paths, but the likely file targets are:

```
server/code/api/routers/extract.py
ui/js/projection-map.js
ui/js/bio-builder-questionnaire.js
data/prompts/question_bank.json        (only if examples / extract_priority need extension)
data/qa/question_bank_extraction_cases.json
scripts/run_question_bank_extraction_eval.py
docs/reports/WO-SCHEMA-02_REPORT.md
```

If actual paths differ, Claude must document the real patched paths in the report.

---

## Required Changes

### Phase 1 -- Canonical Schema Expansion

Add the new field families to `EXTRACTABLE_FIELDS`.

For each new field define:
- canonical field path
- repeatable vs single
- confidence / suggest_only behavior if applicable
- any section affinity hints already used by extractor

Do this before aliases.

### Phase 2 -- Alias Layer

Add aliases only for repeated LLM-invented paths that now have a canonical home.

Examples likely needed after schema expansion:

```
family.siblings.*          -> siblings.*
parents.sibling.*          -> grandparents.* or parents.notableLifeEvents (only if truly still needed)
education.workHistory      -> education.careerProgression
education.workStartYear    -> education.careerProgression
parents.ethnicity          -> grandparents.ancestry or faith/identity equivalent only if semantically justified
hobbies.travel             -> travel.destination / travel.significantTrip (careful)
```

Rule:
- prefer clean canonical mapping
- avoid lossy aliases unless there is no better home

Claude must include a short alias table in the report:
- alias added
- canonical target
- why it was needed

### Phase 3 -- Prompt / Extraction Guidance Update

Update the extraction prompt examples so the model sees the new field families and stops inventing unrelated paths.

Specifically add examples for:
- grandparents
- military
- faith
- health
- community
- pets
- travel

Keep examples short and canonical.

### Phase 4 -- Projection / Frontend Mapping

Add projection-map entries so accepted new fields are not dead-end extractions.

At minimum:
- canonical path registration
- protected / repeatable handling
- write mode
- label

Do not overbuild UI. Just ensure the fields can land somewhere valid.

### Phase 5 -- Eval Coverage Expansion

Add new eval cases for the new families.

Minimum additions:
- 2 grandparent cases
- 2 military cases
- 2 faith cases
- 2 health cases
- 2 community cases
- 2 pets cases
- 2 travel cases

These can be added to the existing question-bank extraction eval fixture using real narrator/template truth where available.

### Phase 6 -- Rerun Eval

Run full extraction eval again after schema patch.

Report:
- before / after total pass count
- before / after failure category counts
- which formerly dropped roadmap phases now have capturable schema targets

---

## Acceptance Criteria

This WO is only done if all are true:

```
[ ] Priority 1-7 field families added to canonical extraction schema
[ ] Projection-map entries exist for the new families
[ ] Alias layer added only where needed
[ ] Extraction prompt examples updated for the new families
[ ] New eval cases added for each new family
[ ] Full extraction eval rerun
[ ] Report includes before/after coverage numbers
```

---

## Success Metrics

```
Roadmap sections with extraction fields:
~11 / 37  ->  ~22 / 37

Questionnaire fields extractable:
~47 / 80+ -> ~70 / 80+

Life map phases that drop data:
~16      -> ~5-6
```

---

## Report Format (Mandatory)

```
WO-SCHEMA-02 REPORT

FILES EDITED
- ...

SCHEMA
- grandparents.* added: PASS / FAIL
- military.* added: PASS / FAIL
- faith.* added: PASS / FAIL
- health.* added: PASS / FAIL
- community.* added: PASS / FAIL
- pets.* added: PASS / FAIL
- travel.* added: PASS / FAIL

ALIASES
- aliases added: N
- lossy aliases added: N
- alias table included: PASS / FAIL

PROMPT / ROUTING
- extraction prompt examples updated: PASS / FAIL
- section-affinity hints updated: PASS / FAIL

PROJECTION
- projection-map entries added: PASS / FAIL

EVAL
- new cases added: N
- full eval rerun: PASS / FAIL
- before/after pass count:
- before/after failure categories:

COVERAGE DELTA
- roadmap sections with extraction fields: before -> after
- questionnaire fields extractable: before -> after
- dropped life-map phases: before -> after

NOTES
- any fields deferred to WO-PHENO-01
- any aliases intentionally left out
- next recommended WO
```

---

## Tight Patch Block for Claude

```
RULES FOR WO-SCHEMA-02
1. Add canonical field targets for uncovered life-map sections before adding aliases.
2. Cover Priority 1-7 only: grandparents, military, faith, health, community, pets, travel.
3. Do not solve narrative/identity-heavy sections in this WO; defer them to WO-PHENO-01.
4. Add aliases only for repeated LLM-invented paths that now have a canonical target.
5. Rerun the full extraction eval and report coverage delta against the baseline.
```

---

## Lower Priority Gaps (deferred to WO-PHENO-01 or later)

| Interview Section | Why it's harder |
|---|---|
| grief_rebuilding | Narrative, emotional -- not entity-structured |
| caregiving | Process/relationship, not discrete facts |
| migration | Overlaps with residence + origins, needs careful dedup |
| blended_family | Complex relationship modeling |
| identity_belonging | Cultural/identity narrative |
| proud | Achievement narrative |
| teen | Overlaps with earlyMemories + school |
| cars | Could be hobbies.hobbies catch-all |
| technology | Could be hobbies.hobbies or laterYears catch-all |
| world_events | Contextual, not personal facts |
| 6 youth sections | Specialized, likely need separate question bank |

---

## Sizing Estimate

- Priority 1 (grandparents): ~1 hour -- questionnaire surface already exists
- Priority 2-6 (military, faith, health, community, pets, travel): ~3-4 hours total
- Aliases + prompt updates: ~1 hour
- Eval cases: ~2 hours
- Total: 1-2 focused sessions
