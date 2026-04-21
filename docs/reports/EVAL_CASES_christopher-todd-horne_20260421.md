# Eval Cases — christopher-todd-horne

Generated: 2026-04-21T04:14:15.375123Z

Total cases for this narrator: **38**

Use this as a fact-check pass. For each case, read `Lori asks`, `Narrator replies`, and `Expected fields`, then mark:

- **FACT** — narratorReply matches biobuilder canon
- **FICTION** — narratorReply contradicts canon or invents facts not in canon
- **PARTIAL** — some of the reply is canon-grounded, some is invented
- **CANON-GAP** — reply is plausible but canon is silent; needs canon entry

---

## Index

- **childhood_origins** (2)
    - [case_053 — compound_family](#case-053--childhood_origins--compound_family)
    - [case_057 — pet_in_hobby_language](#case-057--childhood_origins--pet_in_hobby_language)
- **developmental_foundations** (15)
    - [case_001 — origin_point](#case-001--developmental_foundations--origin_point)
    - [case_002 — early_caregivers](#case-002--developmental_foundations--early_caregivers)
    - [case_008 — family_stories_and_lore](#case-008--developmental_foundations--family_stories_and_lore)
    - [case_010 — childhood_pets](#case-010--developmental_foundations--childhood_pets)
    - [case_032 — family_stories_and_lore](#case-032--developmental_foundations--family_stories_and_lore)
    - [case_042 — childhood_pets](#case-042--developmental_foundations--childhood_pets)
    - [case_045 — childhood_pets](#case-045--developmental_foundations--childhood_pets)
    - [case_047 — sibling_dynamics](#case-047--developmental_foundations--sibling_dynamics)
    - [case_065 — family_origins](#case-065--developmental_foundations--family_origins)
    - [case_073 — grandparent_stories](#case-073--developmental_foundations--grandparent_stories)
    - [case_079 — siblings](#case-079--developmental_foundations--siblings)
    - [case_081 — great_grandparents](#case-081--developmental_foundations--great_grandparents)
    - [case_087 — shong_family](#case-087--developmental_foundations--shong_family)
    - [case_089 — birthplace_detail](#case-089--developmental_foundations--birthplace_detail)
    - [case_095 — birthplace_clarify](#case-095--developmental_foundations--birthplace_clarify)
- **early_adulthood** (6)
    - [case_004 — relationship_anchors](#case-004--early_adulthood--relationship_anchors)
    - [case_005 — parenthood](#case-005--early_adulthood--parenthood)
    - [case_009 — professional_genesis](#case-009--early_adulthood--professional_genesis)
    - [case_034 — professional_genesis](#case-034--early_adulthood--professional_genesis)
    - [case_067 — career_start](#case-067--early_adulthood--career_start)
    - [case_098 — military](#case-098--early_adulthood--military)
- **legacy_reflection** (6)
    - [case_006 — the_off_ramp](#case-006--legacy_reflection--the_off_ramp)
    - [case_007 — legacy_projects](#case-007--legacy_reflection--legacy_projects)
    - [case_036 — reflection](#case-036--legacy_reflection--reflection)
    - [case_051 — the_off_ramp](#case-051--legacy_reflection--the_off_ramp)
    - [case_101 — uncertain_date](#case-101--legacy_reflection--uncertain_date)
    - [case_104 — life_lessons](#case-104--legacy_reflection--life_lessons)
- **middle_adulthood** (2)
    - [case_055 — negated_military](#case-055--middle_adulthood--negated_military)
    - [case_060 — ambiguous_family_role](#case-060--middle_adulthood--ambiguous_family_role)
- **midlife** (6)
    - [case_040 — community_belonging](#case-040--midlife--community_belonging)
    - [case_043 — travel_and_world](#case-043--midlife--travel_and_world)
    - [case_070 — family_life](#case-070--midlife--family_life)
    - [case_076 — spouse_meeting](#case-076--midlife--spouse_meeting)
    - [case_084 — children_detailed](#case-084--midlife--children_detailed)
    - [case_092 — child_detail](#case-092--midlife--child_detail)
- **transitional_adolescence** (1)
    - [case_003 — the_launch](#case-003--transitional_adolescence--the_launch)

---

### case_001 — developmental_foundations / origin_point

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> Do you know the hospital or the town where you were born?

**Narrator replies:**

> I was born in Williston, North Dakota, on Christmas Eve, December 24th, 1962.

**Expected fields:**

- `personal.placeOfBirth` = "Williston, North Dakota"
- `personal.dateOfBirth` = "1962-12-24"

**extractPriority:** `personal.dateOfBirth`, `personal.placeOfBirth`

**Forbidden fields:** `parents.firstName`, `family.spouse.firstName`

**Truth zones:**

- **must_extract**
    - `personal.placeOfBirth = "Williston, North Dakota"`
    - `personal.dateOfBirth = "1962-12-24"`
- **must_not_write**
    - `parents.firstName`
    - `family.spouse.firstName`

_Scoring note: Clean single-fact: birth context with two identity fields from one sentence. Both fields are in extract_priority for origin_point. Verifies date formatting (YYYY-MM-DD)._

---

### case_002 — developmental_foundations / early_caregivers

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Who were the people you saw every single day at the breakfast table when you were very small?

**Narrator replies:**

> It was my mom Janice and my dad Kent, and my two older brothers Vincent and Jason. I was the youngest of three boys.

**Expected fields:**

- `parents.firstName` = "Janice"
- `parents.relation` = "mother"
- `siblings.firstName` = "Vincent"
- `siblings.birthOrder` = "older"
- `personal.birthOrder` = "3"

**extractPriority:** `parents.firstName`, `parents.relation`, `parents.occupation`, `siblings.firstName`, `siblings.birthOrder`

**Forbidden fields:** `family.spouse.firstName`, `education.schooling`

**Truth zones:**

- **must_extract**
    - `parents.firstName = "Janice"`
    - `parents.relation = "mother"`
    - `siblings.firstName = "Vincent"`
    - `siblings.birthOrder = "older"`
    - `personal.birthOrder = "3"`
- **must_not_write**
    - `family.spouse.firstName`
    - `education.schooling`

_Scoring note: Compound multi-fact: four family members plus narrator birth order from one reply. Tests repeatable group association (two parents, two siblings). currentExtractorExpected=false because compound entity grouping is a CLAIMS-01 gap._

---

### case_003 — transitional_adolescence / the_launch

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> What month and year did you graduate from high school?

**Narrator replies:**

> I graduated from Bismarck High School in 1981.

**Expected fields:**

- `education.schooling` = "Graduated from Bismarck High School, 1981"

**extractPriority:** `education.higherEducation`, `education.earlyCareer`, `residence.place`

**Forbidden fields:** `personal.dateOfBirth`, `family.marriageDate`

**Truth zones:**

- **must_extract**
    - `education.schooling = "Graduated from Bismarck High School, 1981"`
- **must_not_write**
    - `personal.dateOfBirth`
    - `family.marriageDate`

_Scoring note: Clean single-fact: high school graduation with school name and year. Tests education.schooling extraction from a concise factual reply._

---

### case_004 — early_adulthood / relationship_anchors

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> What year did you get married, and where was the ceremony?

**Narrator replies:**

> I married Melanie Zollner on December 22nd, 2010.

**Expected fields:**

- `family.spouse.firstName` = "Melanie"
- `family.spouse.lastName` = "Zollner"
- `family.marriageDate` = "2010-12-22"

**extractPriority:** `family.spouse`, `family.marriageDate`

**Forbidden fields:** `parents.firstName`, `personal.dateOfBirth`

**Truth zones:**

- **must_extract**
    - `family.spouse.firstName = "Melanie"`
    - `family.spouse.lastName = "Zollner"`
    - `family.marriageDate = "2010-12-22"`
- **must_not_write**
    - `parents.firstName`
    - `personal.dateOfBirth`

_Scoring note: Clean multi-fact: spouse name + marriage date from one sentence. Verified working in live smoke test (SCHEMA-01 fields). Tests spouse entity extraction and date formatting._

---

### case_005 — early_adulthood / parenthood

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Tell me the names of each of your children.

**Narrator replies:**

> I have four kids. My oldest is Vincent Edward, then Gretchen Jo who was born October 4th, 1991 in Austin, Texas. Then Amelia Fay, born August 5th, 1994, and my youngest is Cole Harber, born April 10th, 2002.

**Expected fields:**

- `family.children.firstName` = "Gretchen"
- `family.children.dateOfBirth` = "1991-10-04"
- `family.children.placeOfBirth` = "Austin, Texas"

**extractPriority:** `family.children`, `residence.place`

**Forbidden fields:** `family.spouse.firstName`, `parents.firstName`

**Truth zones:**

- **must_extract**
    - `family.children.firstName = "Gretchen"`
    - `family.children.dateOfBirth = "1991-10-04"`
    - `family.children.placeOfBirth = "Austin, Texas"`
- **must_not_write**
    - `family.spouse.firstName`
    - `parents.firstName`

_Scoring note: Compound multi-fact: four children with names, dates, place. Known CLAIMS-01 gap — compound children extraction returns 0 items in live smoke test. Tests repeatable group entity coherence across 4 entities._

---

### case_006 — legacy_reflection / the_off_ramp

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> What date or at least what month and year was that last day of work?

**Narrator replies:**

> I retired on January 1st, 2026. I'd been the OT at West Las Vegas Schools since 1997, so that was almost 29 years.

**Expected fields:**

- `laterYears.retirement` = "January 1st, 2026"
- `education.careerProgression` = "West Las Vegas Schools since 1997"

**extractPriority:** `laterYears.retirement`

**Forbidden fields:** `personal.dateOfBirth`, `family.marriageDate`

**Truth zones:**

- **must_extract**
    - `laterYears.retirement = "January 1st, 2026"`
    - `education.careerProgression = "West Las Vegas Schools since 1997"`
- **must_not_write**
    - `personal.dateOfBirth`
    - `family.marriageDate`

_Scoring note: Clean multi-fact: retirement date + career context from legacy phase reply. Tests laterYears.retirement and career extraction coexisting._

---

### case_007 — legacy_reflection / legacy_projects

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> If you could pick one project or achievement to represent your life's work, which one would it be?

**Narrator replies:**

> Building Lorevox. It's the thing I want to last — a system that captures family stories before they disappear.

**Expected fields:**

- `additionalNotes.unfinishedDreams` = "Building Lorevox"

**extractPriority:** `additionalNotes.unfinishedDreams`

**Forbidden fields:** `education.earlyCareer`, `personal.fullName`

**Truth zones:**

- **must_extract**
    - `additionalNotes.unfinishedDreams = "Building Lorevox"`
- **must_not_write**
    - `education.earlyCareer`
    - `personal.fullName`

_Scoring note: Clean single-fact: narrative-style legacy answer → additionalNotes.unfinishedDreams. Tests that free-form reflective text maps to the correct suggest_only field._

---

### case_008 — developmental_foundations / family_stories_and_lore

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> Is there a story in your family about an unusual birth — someone born in a car, in a hallway, during a storm?

**Narrator replies:**

> Yeah, my mom's brother James was born in a car on the way to Richardton Hospital. Uncle Jim — James Peter Zarr — he was the youngest of the three kids.

**Expected fields:**

- `parents.notableLifeEvents` = "born in a car"

**extractPriority:** `earlyMemories.significantEvent`, `parents.notableLifeEvents`

**Forbidden fields:** `personal.dateOfBirth`, `family.children.firstName`

**Truth zones:**

- **must_extract**
    - `parents.notableLifeEvents = "born in a car"`
- **must_not_write**
    - `personal.dateOfBirth`
    - `family.children.firstName`

_Scoring note: Family lore about a relative's unusual birth. LLM extracts as parents.sibling.* which aliases to parents.notableLifeEvents. Value should capture the 'born in a car' detail._

---

### case_009 — early_adulthood / professional_genesis

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> What was the name of the first company that gave you a paycheck for 'real' professional work?

**Narrator replies:**

> Well, my real career started when I became an occupational therapist. I trained in OT and that's what I did my whole career.

**Expected fields:**

- `education.earlyCareer` = "occupational therapist"

**extractPriority:** `education.earlyCareer`, `education.careerProgression`

**Forbidden fields:** `laterYears.retirement`, `family.marriageDate`

**Truth zones:**

- **must_extract**
    - `education.earlyCareer = "occupational therapist"`
- **must_not_write**
    - `laterYears.retirement`
    - `family.marriageDate`

_Scoring note: Clean single-fact: early career extraction. Tests that career answer maps to education.earlyCareer. Expected value is the role fragment the LLM extracts, not a composed sentence._

---

### case_010 — developmental_foundations / childhood_pets

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> What was the name of the family pet that felt most like yours?

**Narrator replies:**

> We had a Golden Retriever named Ivan. He was the family dog when I was growing up.

**Expected fields:**

- `pets.name` = "Ivan"
- `pets.species` = "dog"

**extractPriority:** `hobbies.hobbies`, `earlyMemories.significantEvent`

**Forbidden fields:** `family.children.firstName`, `personal.placeOfBirth`

**Truth zones:**

- **must_extract**
    - `pets.name = "Ivan"`
    - `pets.species = "dog"`
- **must_not_write**
    - `family.children.firstName`
    - `personal.placeOfBirth`

_Scoring note: Pet extraction: Golden Retriever named Ivan. WO-SCHEMA-02 routes to pets.* fields. Tests structured pet extraction from terse reply._

---

### case_032 — developmental_foundations / family_stories_and_lore

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> What do you know about your father's parents — your grandparents on that side?

**Narrator replies:**

> My grandfather Ervin was born November 12th, 1909. His father George died when Ervin was only four, April 12th, 1914. George had come to Ross, North Dakota in 1902 — walked north from Ross looking for land and filed a claim.

**Expected fields:**

- `grandparents.side` = "paternal"
- `grandparents.firstName` = "Ervin"
- `grandparents.birthPlace` = "North Dakota"

**extractPriority:** `grandparents.side`, `grandparents.firstName`, `grandparents.lastName`, `grandparents.birthPlace`, `grandparents.memorableStory`

**Forbidden fields:** `personal.dateOfBirth`, `parents.firstName`

**Truth zones:**

- **must_extract**
    - `grandparents.side = "paternal"`
    - `grandparents.firstName = "Ervin"`
    - `grandparents.birthPlace = "North Dakota"`
- **must_not_write**
    - `personal.dateOfBirth`
    - `parents.firstName`

_Scoring note: WO-SCHEMA-02 grandparents: paternal grandparent with family lore spanning generations. Tests that great-grandparent George data routes to grandparents.memorableStory (not a separate entity) and that Ervin is correctly tagged as paternal._

---

### case_034 — early_adulthood / professional_genesis

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> Did you ever serve in the military, or was that something you considered?

**Narrator replies:**

> No, I never served. But my great-great-grandfather John Michael Shong fought in the Civil War — Company G of the 28th Infantry. He was in Kansas and Missouri from 1865 to 1866.

**Expected fields:**

- `military.significantEvent` = "Family history: great-great-grandfather John Michael Shong served in Civil War"

**extractPriority:** `military.branch`, `military.yearsOfService`

**Forbidden fields:** `military.branch`, `military.rank`

**Truth zones:**

- **must_extract**
    - `military.significantEvent = "Family history: great-great-grandfather John Michael Shong served in Civil War"`
- **must_not_write**
    - `military.branch`
    - `military.rank`

_Scoring note: WO-SCHEMA-02 military: narrator explicitly says 'I never served' but shares family military. Tests forbidden field guard — military.branch should NOT be extracted for narrator since narrator did not serve. The family military detail routes to significantEvent as family lore._

---

### case_036 — legacy_reflection / reflection

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> What values or beliefs guided you through the hardest times?

**Narrator replies:**

> Family loyalty, definitely. And faith — we're Catholic. The Shong family was Catholic going back to France. I think the belief that you show up and do the work no matter what — that's what got passed down.

**Expected fields:**

- `faith.denomination` = "Catholic"
- `faith.values` = "Family loyalty; showing up and doing the work"

**extractPriority:** `faith.values`, `faith.denomination`

**Forbidden fields:** `personal.dateOfBirth`, `education.earlyCareer`

**Truth zones:**

- **must_extract**
    - `faith.denomination = "Catholic"`
    - `faith.values = "Family loyalty; showing up and doing the work"`
- **must_not_write**
    - `personal.dateOfBirth`
    - `education.earlyCareer`

_Scoring note: WO-SCHEMA-02 faith: values extraction from reflective answer. Tests that faith.values captures the narrator's articulated core values and that denomination extracts alongside them._

---

### case_040 — midlife / community_belonging

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> Were you part of any groups, clubs, or organizations during your working years?

**Narrator replies:**

> I was the OT at West Las Vegas Schools from 1997 to 2026. That was basically my whole professional community. Almost twenty-nine years with those kids and teachers.

**Expected fields:**

- `community.organization` = "West Las Vegas Schools"
- `community.role` = "Occupational therapist"
- `community.yearsActive` = "1997-2026"

**extractPriority:** `community.organization`, `community.role`, `community.yearsActive`

**Forbidden fields:** `laterYears.retirement`, `personal.dateOfBirth`

**Truth zones:**

- **must_extract**
    - `community.organization = "West Las Vegas Schools"`
    - `community.role = "Occupational therapist"`
    - `community.yearsActive = "1997-2026"`
- **must_not_write**
    - `laterYears.retirement`
    - `personal.dateOfBirth`

_Scoring note: WO-SCHEMA-02 community: professional community. Tests that a work-as-community answer routes to community fields rather than education.careerProgression. Both are valid but community should be preferred when the prompt specifically asks about organizations._

---

### case_042 — developmental_foundations / childhood_pets

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> What was the name of the family pet that felt most like yours?

**Narrator replies:**

> We had a Golden Retriever named Ivan. He was the family dog when I was growing up. Born around 1964 I think.

**Expected fields:**

- `pets.name` = "Ivan"
- `pets.species` = "Golden Retriever"

**extractPriority:** `pets.name`, `pets.species`, `pets.notes`

**Forbidden fields:** `hobbies.hobbies`, `family.children.firstName`

**Truth zones:**

- **must_extract**
    - `pets.name = "Ivan"`
    - `pets.species = "Golden Retriever"`
- **must_not_write**
    - `hobbies.hobbies`
    - `family.children.firstName`

_Scoring note: WO-SCHEMA-02 pets: single pet with species detail. Tests that pet data now routes to pets.name and pets.species rather than hobbies.hobbies. Mirror of case_010 but targeting SCHEMA-02 fields. If extractor still routes to hobbies.hobbies, this case fails — that's the signal to update prompt hints._

---

### case_043 — midlife / travel_and_world

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> What was the most memorable trip you ever took?

**Narrator replies:**

> Hawaii was special. We went there as a family. And I've been to France — that's where the Shong family came from originally. John Michael Shong was from near Nancy in Lorraine.

**Expected fields:**

- `travel.destination` = "France"
- `travel.purpose` = "Ancestry connection"

**extractPriority:** `travel.destination`, `travel.purpose`, `travel.significantTrip`

**Forbidden fields:** `residence.place`, `personal.dateOfBirth`

**Truth zones:**

- **must_extract**
    - `travel.destination = "France"`
    - `travel.purpose = "Ancestry connection"`
- **must_not_write**
    - `residence.place`
    - `personal.dateOfBirth`

_Scoring note: WO-SCHEMA-02 travel: two destinations with different purposes. Tests repeatable travel grouping and that travel.significantTrip captures the most meaningful trip. Also tests that France routes to travel.destination, NOT residence.place (narrator visited, did not live there)._

---

### case_045 — developmental_foundations / childhood_pets

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> Did you have any pets growing up?

**Narrator replies:**

> We had a big old yellow lab named Buster. He followed us everywhere. Best dog I ever had.

**Expected fields:**

- `pets.name` = "Buster"
- `pets.species` = "dog"

**extractPriority:** `pets.name`, `pets.species`, `pets.notes`

**Forbidden fields:** `hobbies.hobbies`

**Truth zones:**

- **must_extract**
    - `pets.name = "Buster"`
    - `pets.species = "dog"`
- **must_not_write**
    - `hobbies.hobbies`

_Scoring note: WO-EX-REROUTE-01 pets rerouter: pet in pets section. If LLM routes to hobbies.hobbies, rerouter should catch it. Tests that forbiddenFields hobbies.hobbies is not produced._

---

### case_047 — developmental_foundations / sibling_dynamics

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> Tell me about your brothers and sisters.

**Narrator replies:**

> I had two older brothers — Vincent and Jason. Vincent was the oldest, then Jason, then me. We were all pretty close growing up.

**Expected fields:**

- `siblings.firstName` = "Vincent"
- `siblings.relation` = "brother"
- `siblings.birthOrder` = "oldest"

**extractPriority:** `siblings.firstName`, `siblings.relation`, `siblings.birthOrder`

**Forbidden fields:** `family.children.firstName`, `family.children.relation`

**Truth zones:**

- **must_extract**
    - `siblings.firstName = "Vincent"`
    - `siblings.relation = "brother"`
    - `siblings.birthOrder = "oldest"`
- **must_not_write**
    - `family.children.firstName`
    - `family.children.relation`

_Scoring note: WO-EX-REROUTE-01 siblings rerouter: brothers in sibling section. If LLM misroutes to family.children.*, rerouter should fix it. Tests that forbiddenFields family.children.* are not produced._

---

### case_051 — legacy_reflection / the_off_ramp

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> Tell me about your career and how it ended.

**Narrator replies:**

> I worked as an OT at West Las Vegas Schools since 1997. Almost 29 years. I retired on January 1st, 2026.

**Expected fields:**

- `education.careerProgression` = "OT at West Las Vegas Schools since 1997"
- `laterYears.retirement` = "January 1st, 2026"

**extractPriority:** `laterYears.retirement`, `education.careerProgression`

**Truth zones:**

- **must_extract**
    - `education.careerProgression = "OT at West Las Vegas Schools since 1997"`
    - `laterYears.retirement = "January 1st, 2026"`

_Scoring note: WO-EX-REROUTE-01 career rerouter: 'since 1997' and 'almost 29 years' are long-duration markers. If LLM routes to education.earlyCareer, rerouter should fix it to education.careerProgression._

---

### case_053 — childhood_origins / compound_family

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Can you tell me about your parents and siblings?

**Narrator replies:**

> My dad's name was Kent, he was a welder. My mom Dorothy was a homemaker. I had two brothers, Vincent and Jason, and a sister named Christine.

**Expected fields:**

- `parents.firstName` = "Kent"
- `parents.relation` = "father"
- `parents.occupation` = "welder"
- `siblings.firstName` = "Vincent"

**extractPriority:** `parents.firstName`, `siblings.firstName`

**Forbidden fields:** `family.children.firstName`, `family.spouse.firstName`

**Truth zones:**

- **must_extract**
    - `parents.firstName = "Kent"`
    - `parents.relation = "father"`
    - `parents.occupation = "welder"`
    - `siblings.firstName = "Vincent"`
- **must_not_write**
    - `family.children.firstName`
    - `family.spouse.firstName`

_Scoring note: WO-EX-TWOPASS-01: compound family description with parents AND siblings in one answer. Tests that two-pass correctly routes siblings vs children vs parents._

---

### case_055 — middle_adulthood / negated_military

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Did you ever serve in the military?

**Narrator replies:**

> No, I never served. I registered for the draft but my number never came up.

**Expected fields:**

_none_

**Forbidden fields:** `military.branch`, `military.rank`, `military.yearsOfService`, `military.deploymentLocation`

**Truth zones:**

- **must_not_write**
    - `military.branch`
    - `military.rank`
    - `military.yearsOfService`
    - `military.deploymentLocation`

_Scoring note: WO-EX-TWOPASS-01: negated military. Pass 1 should flag 'negated', pass 2 should skip entirely. Tests that denied experiences produce no extraction._

---

### case_057 — childhood_origins / pet_in_hobby_language

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> What were some of your favorite activities or hobbies growing up?

**Narrator replies:**

> Well we always had animals around. We had a dog named Buster, a yellow lab, and there were barn cats everywhere. I liked playing with them more than anything.

**Expected fields:**

- `pets.name` = "Buster"
- `pets.species` = "dog"

**extractPriority:** `pets.name`, `pets.species`

**Forbidden fields:** `hobbies.hobbies`

**Truth zones:**

- **must_extract**
    - `pets.name = "Buster"`
    - `pets.species = "dog"`
- **must_not_write**
    - `hobbies.hobbies`

_Scoring note: WO-EX-TWOPASS-01: pets embedded in hobby/activity question context. Pass 1 should tag as 'pet' type, not 'event'. Tests that pet spans route to pets.* not hobbies.*._

---

### case_060 — middle_adulthood / ambiguous_family_role

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Tell me about your wife and kids.

**Narrator replies:**

> I married my wife Sarah in 1985. We had three kids — our oldest son Michael, then our daughter Emily, and our youngest Jake.

**Expected fields:**

- `family.spouse.firstName` = "Sarah"
- `family.marriageDate` = "1985"
- `family.children.firstName` = "Michael"

**extractPriority:** `family.spouse.firstName`, `family.children.firstName`

**Forbidden fields:** `siblings.firstName`, `parents.firstName`

**Truth zones:**

- **must_extract**
    - `family.spouse.firstName = "Sarah"`
    - `family.marriageDate = "1985"`
    - `family.children.firstName = "Michael"`
- **must_not_write**
    - `siblings.firstName`
    - `parents.firstName`

_Scoring note: WO-EX-TWOPASS-01: spouse + marriage + multiple children in one answer. Tests that two-pass correctly routes spouse vs children and doesn't confuse with siblings or parents._

---

### case_065 — developmental_foundations / family_origins

questionType: anchor  ·  caseType: mixed_narrative  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> What do you know about your family's heritage — where your grandparents came from?

**Narrator replies:**

> On my dad's side, it goes way back. His grandmother was Elizabeth Shong — everybody called her Lizzie. She was the youngest of eight kids. Her father John Michael Shong was born near Nancy in Lorraine, France, came to America around 1848. He served in the Civil War, Company G of the 28th Infantry. Owned 200 acres east of Fall Creek, Wisconsin. Her mother Christine Bolley was from Hanover, Germany, came over in 1850. So you've got French and German blood there. On my mom's side, it's Germans from Russia — the Zarr family from Dodge, North Dakota, and the Schaafs from Glen Ulin. My grandma Josie's family came from Ukraine originally, part of that whole Germans from Russia migration. Grandpa Pete was a tough guy, worked on the Garrison Dam.

**Expected fields:**

- `grandparents.firstName` = "Elizabeth"
- `grandparents.ancestry` = "French (Alsace-Lorraine), German"

**extractPriority:** `grandparents.ancestry`, `grandparents.firstName`

**Truth zones:**

- **must_extract**
    - `grandparents.firstName = "Elizabeth"`
    - `grandparents.ancestry = "French (Alsace-Lorraine), German"`
- **may_extract**
    - `grandparents.lastName = "Horne"`
    - `grandparents.maidenName = "Shong"`
    - `grandparents.birthPlace = "Fall Creek, Wisconsin"`
- **should_ignore**
    - `personal.culture  _(heritage summary mentioned but not a direct personal.culture extraction moment)_`
    - `parents.occupation  _(Garrison Dam is grandpa Pete's job, mentioned in passing)_`

_Scoring note: Mixed narrative: dense family heritage story spanning great-grandparents, grandparents, and cultural background. Many true facts but only grandparent data should be primary extraction targets. Tests coverage and attribution depth._

---

### case_067 — early_adulthood / career_start

questionType: anchor  ·  caseType: mixed_narrative  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> What was your first real job or career after school?

**Narrator replies:**

> Well after Bismarck High I kind of bounced around for a bit. I'd always been interested in helping people though. Eventually I got into occupational therapy. But you know, growing up, my dad Kent was in construction and trades his whole life. He could build anything. I think watching him work with his hands gave me an appreciation for physical rehabilitation — understanding how the body moves and how to help people recover function. My mom Janice had studied Speech and History at Bismarck Junior College before she had us kids, so education was valued in our house even though we weren't a wealthy family by any stretch.

**Expected fields:**

- `education.earlyCareer` = "Occupational therapy"

**extractPriority:** `education.earlyCareer`

**Truth zones:**

- **must_extract**
    - `education.earlyCareer = "Occupational therapy"`
- **may_extract**
    - `education.schooling = "Bismarck High School"`
- **should_ignore**
    - `parents.occupation  _(Kent's construction career is true but this is Chris's interview, not Kent's)_`
    - `parents.firstName  _(Kent and Janice mentioned but as context, not new parent data to extract here)_`

_Scoring note: Mixed narrative: career question answered with personal career plus family context about parents. Tests whether Lori extracts Chris's OT career while ignoring Kent's construction career and Janice's college, which are true but belong to their narrator profiles._

---

### case_070 — midlife / family_life

questionType: anchor  ·  caseType: mixed_narrative  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Tell me about your kids — how many do you have?

**Narrator replies:**

> I've got four kids. Well, Vince — Vincent Edward — he's the oldest, he was actually born over in Germany when we were living there. Then there's Gretchen Jo, she was born October 4, 1991. She's in Austin, Texas now. Amelia Fay came along in '94, August 5th. She's got her MSW, she's been all over — New Mexico, Colorado, Hawaii — working in social services. And Cole, the youngest, Cole Harber Horne, born April 10, 2002. He works in medical billing now and studies computer science. Smart kid, into AI and cybersecurity. My wife Melanie — we got married December 22, 2010 — she's a college professor. We do a lot of family dinners, try to get everyone together when we can.

**Expected fields:**

- `family.children.firstName` = "Vincent"
- `family.children.relation` = "son"

**extractPriority:** `family.children.firstName`, `family.children.relation`

**Truth zones:**

- **must_extract**
    - `family.children.firstName = "Vincent, Gretchen, Amelia, Cole"`
    - `family.children.dateOfBirth = "1991-10-04, 1994-08-05, 2002-04-10"`
- **may_extract**
    - `family.children.lastName = "Horne"`
    - `family.spouse.firstName = "Melanie"`
    - `family.marriageDate = "2010-12-22"`
- **should_ignore**
    - `residence.place  _(Austin TX is Gretchen's residence, not Chris's)_`
- **must_not_write**
    - `education.careerProgression`

_Scoring note: Mixed narrative: all four children named with details, plus spouse and marriage date woven in. Austin TX and other locations are children's residences. Tests compound extraction of 4 children plus optional spouse data, while not misattributing children's locations as narrator residences._

---

### case_073 — developmental_foundations / grandparent_stories

questionType: anchor  ·  caseType: mixed_narrative  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Do you remember any stories about your grandparents?

**Narrator replies:**

> My grandpa Pete — my mom's dad — he was born at home, delivered by Mrs. Steve Dodenheffer. He had this thing about his birth certificate getting lost when the state Capitol of North Dakota burned down. He was a steam boiler operator, had his license, and also did carpentry. Worked on the Garrison Dam as a foreman of a finishing crew for cement forms. Tough man. His wife Josie — my grandma — she was something special. She played the organ at silent movie theaters to make money. Can you imagine? She went to Capitol Business College in Bismarck but hated the accounting part. She was the youngest in her family, and her older brother was Mike Schaaf.

**Expected fields:**

- `grandparents.firstName` = "Peter"

**extractPriority:** `grandparents.memorableStory`

**Truth zones:**

- **must_extract**
    - `grandparents.firstName = "Peter"`
    - `grandparents.memorableStory = "born at home, worked on Garrison Dam, steam boiler operator"`
- **may_extract**
    - `grandparents.lastName = "Zarr"`
    - `grandparents.birthPlace = "Dodge, ND"`
- **should_ignore**
    - `parents.firstName  _('my mom's dad' references parent but not new parent data)_`
- **must_not_write**
    - `education.higherEducation`

_Scoring note: Mixed narrative: rich grandparent stories with occupational detail and color. Both maternal grandparents described. Tests extraction of grandparent facts from a story-heavy answer without over-extracting._

---

### case_076 — midlife / spouse_meeting

questionType: anchor  ·  caseType: mixed_narrative  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> How did you and Melanie meet?

**Narrator replies:**

> Melanie and I got married December 22, 2010. She's a college professor, really smart woman. Her last name was Zollner before we married. We have a family-centered life — big on family dinners, getting everyone together whenever we can. My parents had that same kind of family culture, you know? Germans from Russia on my mom's side through the Zarr and Schaaf families. Food was always the center of everything. Melanie fits right into that tradition even though she came from a different background.

**Expected fields:**

- `family.spouse.firstName` = "Melanie"
- `family.marriageDate` = "2010-12-22"

**extractPriority:** `family.spouse.firstName`, `family.marriageDate`

**Truth zones:**

- **must_extract**
    - `family.spouse.firstName = "Melanie"`
    - `family.marriageDate = "2010-12-22"`
- **may_extract**
    - `family.spouse.lastName = "Zollner"`
    - `family.marriageNotes = "family-centered life"`
- **should_ignore**
    - `personal.culture  _(heritage mentioned for context, not new data)_`
- **must_not_write**
    - `parents.firstName`

_Scoring note: Mixed narrative: spouse meeting with cultural context. Tests clean spouse + marriage extraction while ignoring heritage tangent._

---

### case_079 — developmental_foundations / siblings

questionType: anchor  ·  caseType: mixed_narrative  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Tell me about your brothers.

**Narrator replies:**

> I've got two older brothers. Vince — Vincent Edward — he's the oldest. He was born in Germany when Mom and Dad were living over there for Dad's construction work. Then Jason, Jason Richard Horne, he's the middle one. Family-oriented guy. I'm the youngest, born in Williston. We all grew up together moving around with Dad's construction jobs. Mom kept us grounded through all those moves.

**Expected fields:**

- `siblings.firstName` = "Vincent"

**extractPriority:** `siblings.firstName`

**Truth zones:**

- **must_extract**
    - `siblings.firstName = "Vincent, Jason"`
    - `siblings.relation = "Brother"`
- **may_extract**
    - `siblings.lastName = "Horne"`
    - `siblings.birthOrder = "older"`
    - `siblings.uniqueCharacteristics = "born in Germany, family-oriented"`
- **should_ignore**
    - `personal.placeOfBirth  _(Williston already known)_`
    - `parents.occupation  _(construction mentioned but as context)_`

_Scoring note: Mixed narrative: two brothers described with some detail. Tests compound sibling extraction with optional character detail._

---

### case_081 — developmental_foundations / great_grandparents

questionType: anchor  ·  caseType: dense_truth  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Do you know anything about the generations before your grandparents?

**Narrator replies:**

> Oh yeah, I've done a lot of research on this. My great-grandmother Elizabeth's father was John Michael Shong — born October 11, 1829 near Nancy in Lorraine, France. He came to America around 1848 at about nineteen. His father's name was thought to be Nicholas, a railroad worker. John Michael had two sisters Mary and Margaret and a brother Peter, who all stayed in France. The name was originally Schong but the C got dropped in America. He settled at Fall Creek, Wisconsin around 1859, before the railroad came through. Served in the Civil War — Company G, 28th Infantry, February 1865 to January 1866, in Kansas and Missouri. By 1871 he owned 200 acres east of Fall Creek. He married Christine Bolley on August 7, 1863. He definitely claimed to be French, and after he died in 1891 letters still came from his people in France. His wife Christine was born July 18, 1842 in Germany — Hanover — came to America with her family in 1850. Her parents were Carl and Mrs. Bolley. Carl Bolley died December 13, 1873 in Weston, Wisconsin.

**Expected fields:**

- `grandparents.ancestry` = "French (Alsace-Lorraine), German"

**extractPriority:** `grandparents.ancestry`

**Truth zones:**

- **must_extract**
    - `grandparents.ancestry = "French (Alsace-Lorraine), German (Hanover)"`
- **may_extract**
    - `grandparents.memorableStory = "Civil War service, French immigrant, name originally Schong"`
    - `personal.culture = "French and German heritage"`
- **must_not_write**
    - `military.branch`
    - `military.yearsOfService`
    - `education.schooling`

_Scoring note: Dense truth: very long, fact-packed great-grandparent history. Immigration, Civil War, naming changes, property, marriage. Tests whether Lori can extract ancestry and memorable stories without falsely attributing Civil War service as narrator's military service._

---

### case_084 — midlife / children_detailed

questionType: followup  ·  caseType: dense_truth  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Can you tell me a bit more about each of your kids — what they're doing now?

**Narrator replies:**

> Sure. Gretchen Jo was born October 4, 1991. She's been through a lot — went through some major life challenges in 2024, been going to ACA meetings. She lives in Austin, Texas now. Then Amelia Fay, born August 5, 1994. She's got her MSW, master's in social work. She's lived everywhere — New Mexico, Colorado, Hawaii — she works in social services. And Cole Harber Horne, born April 10, 2002, he's the baby. He's in medical billing right now but also studying computer science. Really into AI and cybersecurity and accounting. And then Vince of course, the oldest, born in Germany. All four of them are different but they're all good people. Melanie and I try to do family dinners whenever everyone's in the same state.

**Expected fields:**

- `family.children.firstName` = "Gretchen"
- `family.children.dateOfBirth` = "1991-10-04"

**extractPriority:** `family.children.firstName`, `family.children.dateOfBirth`

**Truth zones:**

- **must_extract**
    - `family.children.firstName = "Gretchen, Amelia, Cole, Vincent"`
    - `family.children.dateOfBirth = "1991-10-04, 1994-08-05, 2002-04-10"`
- **may_extract**
    - `family.children.lastName = "Horne"`
    - `family.children.placeOfBirth = "Germany (Vincent)"`
- **should_ignore**
    - `family.spouse.firstName  _(Melanie mentioned but as context)_`
- **must_not_write**
    - `residence.place`
    - `education.higherEducation`

_Scoring note: Dense truth: four children with dates, occupations, locations, personal challenges. Austin TX, NM, CO, HI are children's locations, not narrator's. Tests compound extraction of multiple children while maintaining narrator attribution boundaries._

---

### case_087 — developmental_foundations / shong_family

questionType: followup  ·  caseType: dense_truth  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> You've mentioned the Shong family — can you tell me more about that side?

**Narrator replies:**

> The Shongs go back to Lorraine, France. John Michael Shong was born October 11, 1829 near Nancy. He came to America around 1848. His father was supposedly Nicholas, a railroad worker. John Michael had two sisters — Mary and Margaret — and a brother Peter who all stayed in France. He settled in Fall Creek, Wisconsin around 1859. Served in the Civil War with Company G of the 28th Infantry. By 1871 he had 200 acres. He married Christine Bolley — she was born July 18, 1842 in Hanover, Germany, came over in 1850 with her family. Her parents were Carl and Mrs. Bolley from Hanover. They married August 7, 1863 at Fall Creek. Had eight kids. His daughter Lizzie — Elizabeth — was my dad's grandmother. She went to Penn, North Dakota around 1900 to visit her brother Charlie who ran a hotel there, and to work as a seamstress. She met George Horne and married him December 29, 1903. The Shong name was originally Schong. He definitely claimed to be French. After he died in 1891 letters still came from his people in France.

**Expected fields:**

- `grandparents.ancestry` = "French (Alsace-Lorraine)"

**extractPriority:** `grandparents.memorableStory`, `grandparents.ancestry`

**Truth zones:**

- **must_extract**
    - `grandparents.ancestry = "French (Alsace-Lorraine), German (Hanover)"`
    - `grandparents.memorableStory = "Shong family from Lorraine France, name originally Schong, Civil War service"`
- **may_extract**
    - `grandparents.firstName = "Elizabeth"`
    - `grandparents.maidenName = "Shong"`
- **should_ignore**
    - `personal.culture  _(cultural heritage mentioned but as family history, not personal profile update)_`
- **must_not_write**
    - `military.branch`

_Scoring note: Dense truth: very detailed Shong family genealogy. Civil War reference must NOT create military entry for Chris. Tests genealogical narrative handling — lots of valid data but most belongs in grandparent memorable stories, not as standalone field extractions._

---

### case_089 — developmental_foundations / birthplace_detail

questionType: followup  ·  caseType: follow_up  ·  style: life_history  ·  currentExtractorExpected: False

**Prior context:**

> Narrator stated birthplace as Williston, North Dakota, DOB 1962-12-24.

**Lori asks:**

> You mentioned being born in Williston, North Dakota — what was it like growing up there?

**Narrator replies:**

> Well we didn't stay in Williston that long, actually. Dad's construction work moved us around. But North Dakota in general — it was rural, wide open. Family-centered. We had our dog Ivan, a golden retriever. Just a good, simple childhood. My brothers and I were always outside.

**Expected fields:**

_none_

**extractPriority:** `residence.notes`

**Truth zones:**

- **may_extract**
    - `pets.name = "Ivan"`
    - `pets.species = "Dog"`
    - `earlyMemories.firstMemory = "rural North Dakota, family-centered, always outside"`
- **should_ignore**
    - `personal.placeOfBirth  _(Williston already captured — should not re-extract)_`
    - `residence.place  _(general ND reference, too vague for new residence entry)_`
    - `parents.occupation  _(construction mentioned but already known)_`

_Scoring note: Follow-up: short answer that enriches childhood picture but has limited new extractable facts. Pet Ivan is new if not previously captured. Tests restraint — should not re-extract birthplace._

---

### case_092 — midlife / child_detail

questionType: followup  ·  caseType: follow_up  ·  style: topical  ·  currentExtractorExpected: False

**Prior context:**

> Narrator previously listed children: Vincent, Gretchen (DOB 1991-10-04), Amelia, Cole.

**Lori asks:**

> You mentioned Gretchen went through some challenges — can you share more?

**Narrator replies:**

> Gretchen's had a tough road. In 2024 she went through some major life challenges. She's been going to ACA meetings — Adult Children of Alcoholics — and it's really helped her. She's living in Austin, Texas now. She's strong though, like her grandma Janice.

**Expected fields:**

_none_

**extractPriority:** `family.children.firstName`

**Truth zones:**

- **should_ignore**
    - `family.children.firstName  _(Gretchen already captured)_`
    - `family.children.dateOfBirth  _(already captured)_`
- **must_not_write**
    - `residence.place`
    - `health.majorCondition`

_Scoring note: Follow-up: personal detail about existing child. Austin TX is Gretchen's city not Chris's. ACA meetings are sensitive personal info. Tests restraint — should not create new child entry or residence for narrator._

---

### case_095 — developmental_foundations / birthplace_clarify

questionType: followup  ·  caseType: follow_up  ·  style: life_history  ·  currentExtractorExpected: False

**Prior context:**

> Narrator stated birthplace Williston, North Dakota.

**Lori asks:**

> Was Williston where your family was living, or did your mom just go to the hospital there?

**Narrator replies:**

> No, we were living in Williston at the time. But we didn't stay long — Dad's construction work moved us around. I was only there for the first year or two. After that we were in other parts of North Dakota and wherever the jobs took us.

**Expected fields:**

_none_

**extractPriority:** `personal.placeOfBirth`, `residence.place`

**Truth zones:**

- **may_extract**
    - `residence.place = "Williston, North Dakota"`
    - `residence.period = "first year or two"`
- **should_ignore**
    - `personal.placeOfBirth  _(already captured)_`
    - `parents.occupation  _(construction already known)_`

_Scoring note: Follow-up: clarification that confirms Williston as both birthplace and early residence. May extract as residence entry. Tests whether Lori handles the distinction between birthplace (already captured) and residence (new entry)._

---

### case_098 — early_adulthood / military

questionType: anchor  ·  caseType: null_clarify  ·  style: topical  ·  currentExtractorExpected: True

**Lori asks:**

> Did you ever serve in the military?

**Narrator replies:**

> No, I never did. My great-great-grandfather John Michael Shong served in the Civil War, and my brother Vince was born in Germany when we were over there, but that was for Dad's construction job, not military.

**Expected fields:**

_none_

**extractPriority:** `military.branch`

**Forbidden fields:** `military.branch`, `military.yearsOfService`, `military.rank`, `military.deploymentLocation`

**Truth zones:**

- **may_extract**
    - `grandparents.memorableStory = "great-great-grandfather in Civil War"`
- **must_not_write**
    - `military.branch`
    - `military.yearsOfService`
    - `military.rank`
    - `military.deploymentLocation`

_Scoring note: Null/clarify: explicit denial of military service. Civil War reference is ancestor data. Germany was not a deployment. Tests abstention on the primary field while optionally capturing ancestor detail._

---

### case_101 — legacy_reflection / uncertain_date

questionType: followup  ·  caseType: null_clarify  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Do you know when your family lived in Germany?

**Narrator replies:**

> I'm not exactly sure of the dates. I think it was before I was born — Vince was born there, so it must have been before '62. But I couldn't tell you the exact years. You'd have to ask my mom or dad.

**Expected fields:**

_none_

**extractPriority:** `residence.period`

**Truth zones:**

- **may_extract**
    - `residence.place = "Germany"`
- **should_ignore**
    - `residence.period  _(narrator explicitly uncertain — 'not exactly sure,' 'couldn't tell you')_`
    - `family.children.placeOfBirth  _(Vince born in Germany already known context)_`

_Scoring note: Null/clarify: narrator is explicitly uncertain about dates. 'I'm not exactly sure' and 'you'd have to ask' are hedging signals. Tests whether Lori handles uncertainty appropriately — may note Germany as residence but should not fabricate dates._

---

### case_104 — legacy_reflection / life_lessons

questionType: anchor  ·  caseType: mixed_narrative  ·  style: thematic  ·  currentExtractorExpected: False

**Lori asks:**

> What are the most important things life has taught you?

**Narrator replies:**

> Family is everything. That sounds simple but it's the truth. My parents moved us all over the country for Dad's construction work, but Mom kept that family together through every single move. She had studied Speech and History at Bismarck Junior College — she was educated, she was smart, but she chose to put the family first. Dad worked with his hands his whole life and never complained. I look at my own kids now — Gretchen dealing with her challenges, Amelia out there doing social work, Cole studying cybersecurity — and I think the best thing I can do is be there. Like my parents were for us. That's the lesson. Show up.

**Expected fields:**

- `laterYears.lifeLessons` = "Family is everything — show up and be there"

**extractPriority:** `laterYears.lifeLessons`

**Truth zones:**

- **must_extract**
    - `laterYears.lifeLessons = "Family is everything, show up and be there"`
- **should_ignore**
    - `parents.occupation  _(construction mentioned reflectively, not new data)_`
    - `parents.firstName  _(referenced in reflection, not extraction targets)_`
    - `family.children.firstName  _(kids mentioned reflectively)_`
- **must_not_write**
    - `education.higherEducation`

_Scoring note: Mixed narrative (thematic): reflective answer with family references throughout. Only the life lesson itself should be extracted. Tests whether Lori can extract the reflection while ignoring the many true-but-already-known facts mentioned for context._

---
