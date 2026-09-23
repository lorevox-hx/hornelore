# Concept decision appendix — GENERATED, do not edit by hand

Produced by `scripts/design/build_concept_catalog.py --markdown`. Regenerate rather than edit:

```bash
cd /mnt/c/Users/chris/hornelore
PYTHONPYCACHEPREFIX=/tmp/pyc python3 scripts/design/build_concept_catalog.py \
  --markdown docs/specs/CONCEPT-DECISION-APPENDIX.md
```

**Sources (measured):** `questionnaire_schema.load_schema [7b974b9c2f23]` · `extract.EXTRACTABLE_FIELDS` · `bio_schema.FieldDefinition` · `projection-map.FIELD_MAP`

**Two kinds of column.** *Measured* columns come from the shipped sources and are reproducible. *Proposed* columns (`concept`, `subject`, `disposition`, `purpose`) are one author's semantic judgement, written into the script so they can be reviewed and reversed. Approving them is a product decision.

## Totals (measured)

| | count |
|---|---:|
| questionnaire vocabulary | 118 |
| extraction vocabulary | 146 |
| asking (bio_schema) vocabulary | 84 |
| projection map vocabulary | 25 |
| extraction targets that hit a form field exactly | 69 |
| reachable only through a prefix alias | 8 |
| extraction targets with no destination | 69 |
| form fields extraction can never fill | 41 |
| of which broken at BOTH ends | 5 |

## B — broken at both ends (same fact, two spellings, reaching neither)

| id | concept | subject | extractor looks for | form offers |
|---|---|---|---|---|
| B01 | `person.birth.date` | child | `family.children.dateOfBirth` | `children.birthDate` |
| B02 | `person.birth.date` | spouse | `family.spouse.dateOfBirth` | `spouse.birthDate` |
| B03 | `person.birth.place` | child | `family.children.placeOfBirth` | `children.birthPlace` |
| B04 | `person.birth.place` | spouse | `family.spouse.placeOfBirth` | `spouse.birthPlace` |
| B05 | `story` | grandparent | `grandparents.memorableStory` | `grandparents.memorableStories` |

## A — prefix aliases (same fact, one path has an extra `family.`)

| id | extractor path | form path | extractor writeMode *(measured)* |
|---|---|---|---|
| A01 | `family.children.firstName` | `children.firstName` | candidate_only |
| A02 | `family.children.lastName` | `children.lastName` | candidate_only |
| A03 | `family.children.relation` | `children.relation` | candidate_only |
| A04 | `family.spouse.firstName` | `spouse.firstName` | prefill_if_blank |
| A05 | `family.spouse.lastName` | `spouse.lastName` | prefill_if_blank |
| A06 | `family.spouse.maidenName` | `spouse.maidenName` | prefill_if_blank |
| A07 | `family.spouse.middleName` | `spouse.middleName` | prefill_if_blank |
| A08 | `family.spouse.occupation` | `spouse.occupation` | prefill_if_blank |

## G — extraction targets with no destination, grouped by concept + subject

64 groups covering 69 paths. `?subject` means the section is not a questionnaire section at all.

| id | disposition *(proposed)* | concept *(proposed)* | subject *(proposed)* | original paths *(measured)* | extractor writeMode *(measured)* |
|---|---|---|---|---|---|
| G01 | define | `event` | narrator | `community.significantEvent`, `laterYears.significantEvent` | suggest_only |
| G02 | define | `person.birth.date` | child | `family.children.dateOfBirth` | candidate_only |
| G03 | define | `person.birth.date` | great-grandparent | `greatGrandparents.birthDate` | candidate_only |
| G04 | define | `person.birth.date` | sibling | `siblings.birthDate` | candidate_only |
| G05 | define | `person.birth.date` | spouse | `family.spouse.dateOfBirth` | prefill_if_blank |
| G06 | define | `person.birth.order` | child | `family.children.birthOrder` | candidate_only |
| G07 | define | `person.birth.place` | child | `family.children.placeOfBirth` | candidate_only |
| G08 | define | `person.birth.place` | great-grandparent | `greatGrandparents.birthPlace` | candidate_only |
| G09 | define | `person.birth.place` | sibling | `siblings.birthPlace` | candidate_only |
| G10 | define | `person.birth.place` | spouse | `family.spouse.placeOfBirth` | prefill_if_blank |
| G11 | define | `person.death.age` | parent | `parents.ageAtDeath` | candidate_only |
| G12 | define | `person.death.date` | grandparent | `grandparents.deathDate` | candidate_only |
| G13 | define | `person.death.date` | parent | `parents.deathDate` | candidate_only |
| G14 | define | `person.death.place` | parent | `parents.placeOfDeath` | candidate_only |
| G15 | define | `person.education` | parent | `parents.education` | suggest_only |
| G16 | define | `person.education` | spouse | `family.spouse.education` | suggest_only |
| G17 | define | `person.name.birth_family` | great-grandparent | `greatGrandparents.maidenName` | candidate_only |
| G18 | define | `person.name.family` | ?priorPartners | `family.priorPartners.lastName` | candidate_only |
| G19 | define | `person.name.family` | great-grandparent | `greatGrandparents.lastName` | candidate_only |
| G20 | define | `person.name.given` | ?grandchildren | `family.grandchildren.firstName` | candidate_only |
| G21 | define | `person.name.given` | ?priorPartners | `family.priorPartners.firstName` | candidate_only |
| G22 | define | `person.name.given` | great-grandparent | `greatGrandparents.firstName` | candidate_only |
| G23 | define | `person.name.preferred` | child | `family.children.preferredName` | candidate_only |
| G24 | define | `person.name.preferred` | parent | `parents.preferredName` | candidate_only |
| G25 | define | `person.name.preferred` | sibling | `siblings.preferredName` | candidate_only |
| G26 | define | `person.name.preferred` | spouse | `family.spouse.preferredName` | prefill_if_blank |
| G27 | define | `person.occupation` | grandparent | `grandparents.occupation` | candidate_only |
| G28 | define | `person.occupation` | sibling | `siblings.occupation` | candidate_only |
| G29 | define | `relationship.kind` | ?grandchildren | `family.grandchildren.relation` | candidate_only |
| G30 | define | `relationship.kind` | ?priorPartners | `family.priorPartners.relation` | candidate_only |
| G31 | define | `relationship.kind` | spouse | `family.spouse.relation` | prefill_if_blank |
| G32 | define | `story` | grandparent | `grandparents.memorableStory` | suggest_only |
| G33 | define | `story` | great-grandparent | `greatGrandparents.memorableStories` | suggest_only |
| G34 | define | `story` | narrator | `cultural.touchstoneMemory`, `laterYears.desiredStory` | suggest_only |
| G35 | NEEDS_CONCEPT | `?ageatmarriage` | spouse | `family.spouse.ageAtMarriage` | prefill_if_blank |
| G36 | NEEDS_CONCEPT | `?ancestry` | great-grandparent | `greatGrandparents.ancestry` | candidate_only |
| G37 | NEEDS_CONCEPT | `?childcount` | grandparent | `grandparents.childCount` | candidate_only |
| G38 | NEEDS_CONCEPT | `?cognitivechange` | narrator | `health.cognitiveChange` | suggest_only |
| G39 | NEEDS_CONCEPT | `?currentmedications` | narrator | `health.currentMedications` | suggest_only |
| G40 | NEEDS_CONCEPT | `?dailyroutine` | narrator | `laterYears.dailyRoutine` | suggest_only |
| G41 | NEEDS_CONCEPT | `?ethnicbackground` | parent | `parents.ethnicBackground` | suggest_only |
| G42 | NEEDS_CONCEPT | `?lifestylechange` | narrator | `health.lifestyleChange` | suggest_only |
| G43 | NEEDS_CONCEPT | `?majorcondition` | narrator | `health.majorCondition` | suggest_only |
| G44 | NEEDS_CONCEPT | `?marriagenotes` | family | `family.marriageNotes` | suggest_only |
| G45 | NEEDS_CONCEPT | `?meetingday` | narrator | `community.meetingDay` | suggest_only |
| G46 | NEEDS_CONCEPT | `?meetinglocation` | narrator | `community.meetingLocation` | suggest_only |
| G47 | NEEDS_CONCEPT | `?membercount` | narrator | `community.memberCount` | suggest_only |
| G48 | NEEDS_CONCEPT | `?milestone` | narrator | `health.milestone` | suggest_only |
| G49 | NEEDS_CONCEPT | `?militarybranch` | great-grandparent | `greatGrandparents.militaryBranch` | suggest_only |
| G50 | NEEDS_CONCEPT | `?militaryevent` | great-grandparent | `greatGrandparents.militaryEvent` | suggest_only |
| G51 | NEEDS_CONCEPT | `?militaryunit` | great-grandparent | `greatGrandparents.militaryUnit` | suggest_only |
| G52 | NEEDS_CONCEPT | `?namestory` | narrator | `personal.nameStory` | suggest_only |
| G53 | NEEDS_CONCEPT | `?organization` | narrator | `community.organization` | suggest_only |
| G54 | NEEDS_CONCEPT | `?period` | ?priorPartners | `family.priorPartners.period` | candidate_only |
| G55 | NEEDS_CONCEPT | `?readingability` | narrator | `education.readingAbility` | suggest_only |
| G56 | NEEDS_CONCEPT | `?role` | narrator | `community.role` | suggest_only |
| G57 | NEEDS_CONCEPT | `?side` | great-grandparent | `greatGrandparents.side` | candidate_only |
| G58 | NEEDS_CONCEPT | `?successor` | narrator | `community.successor` | suggest_only |
| G59 | NEEDS_CONCEPT | `?training` | narrator | `education.training` | suggest_only |
| G60 | NEEDS_CONCEPT | `?yearsactive` | narrator | `community.yearsActive` | suggest_only |
| G61 | RETIRE | `RETIRED` | ?grandchildren | `family.grandchildren.notes` | candidate_only |
| G62 | RETIRE | `RETIRED` | child | `family.children.notes` | suggest_only |
| G63 | RETIRE | `RETIRED` | narrator | `community.notes`, `education.notes`, `health.notes`, `hobbies.notes` | suggest_only |
| G64 | RETIRE | `RETIRED` | spouse | `family.spouse.notes` | suggest_only |

## Q — form fields extraction can never fill, grouped by purpose

| id | purpose *(proposed)* | count | fields *(measured)* |
|---|---|---:|---|
| Q01 | stories in field clothing | 9 | `children.narrative`, `earlyMemories.favoriteToy`, `familyTraditions.description`, `familyTraditions.occasion`, `grandparents.memorableStories`, `hobbies.worldEvents`, `siblings.memories`, `siblings.sharedExperiences`, `spouse.narrative` |
| Q02 | names and vitals of relatives | 8 | `children.birthDate`, `children.birthPlace`, `children.middleName`, `grandparents.middleName`, `siblings.maidenName`, `siblings.middleName`, `spouse.birthDate`, `spouse.birthPlace` |
| Q03 | marriage detail | 4 | `marriage.proposalStory`, `marriage.spouseReference`, `marriage.weddingDetails`, `spouse.relationshipType` |
| Q04 | technology & culture | 4 | `hobbies.travel`, `technology.culturalPractices`, `technology.favoriteGadgets`, `technology.firstTechExperience` |
| Q05 | health | 3 | `health.healthMilestones`, `health.lifestyleChanges`, `health.wellnessTips` |
| Q06 | pets | 3 | `pets.adoptionDate`, `pets.birthDate`, `pets.breed` |
| Q07 | derived / stale | 2 | `personal.timeOfBirth`, `personal.zodiacSign` |
| Q08 | education | 2 | `education.communityInvolvement`, `education.mentorship` |
| Q09 | legacy messages | 2 | `additionalNotes.messagesForFutureGenerations`, `laterYears.adviceForFutureGenerations` |
| Q10 | life status | 2 | `parents.deceased`, `spouse.deceased` |
| Q11 | heritage | 1 | `grandparents.culturalBackground` |
| Q12 | notes | 1 | `siblings.notes` |
| | **total** | **41** | must equal 41 |

