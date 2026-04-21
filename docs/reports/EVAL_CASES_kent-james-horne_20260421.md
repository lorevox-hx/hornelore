# Eval Cases — kent-james-horne

Generated: 2026-04-21T04:14:15.355356Z

Total cases for this narrator: **33**

Use this as a fact-check pass. For each case, read `Lori asks`, `Narrator replies`, and `Expected fields`, then mark:

- **FACT** — narratorReply matches biobuilder canon
- **FICTION** — narratorReply contradicts canon or invents facts not in canon
- **PARTIAL** — some of the reply is canon-grounded, some is invented
- **CANON-GAP** — reply is plausible but canon is silent; needs canon entry

---

## Index

- **childhood_origins** (1)
    - [case_054 — mixed_narrator_family](#case-054--childhood_origins--mixed_narrator_family)
- **developmental_foundations** (9)
    - [case_011 — origin_point](#case-011--developmental_foundations--origin_point)
    - [case_014 — early_caregivers](#case-014--developmental_foundations--early_caregivers)
    - [case_017 — childhood_pets](#case-017--developmental_foundations--childhood_pets)
    - [case_033 — family_stories_and_lore](#case-033--developmental_foundations--family_stories_and_lore)
    - [case_068 — family_loss](#case-068--developmental_foundations--family_loss)
    - [case_077 — siblings_childhood](#case-077--developmental_foundations--siblings_childhood)
    - [case_080 — family_history](#case-080--developmental_foundations--family_history)
    - [case_083 — grandmother_story](#case-083--developmental_foundations--grandmother_story)
    - [case_090 — father_detail](#case-090--developmental_foundations--father_detail)
- **early_adulthood** (10)
    - [case_012 — relationship_anchors](#case-012--early_adulthood--relationship_anchors)
    - [case_013 — parenthood](#case-013--early_adulthood--parenthood)
    - [case_016 — professional_genesis](#case-016--early_adulthood--professional_genesis)
    - [case_044 — first_home](#case-044--early_adulthood--first_home)
    - [case_048 — parenthood](#case-048--early_adulthood--parenthood)
    - [case_050 — first_home](#case-050--early_adulthood--first_home)
    - [case_064 — marriage_story](#case-064--early_adulthood--marriage_story)
    - [case_071 — military_family](#case-071--early_adulthood--military_family)
    - [case_086 — career_family](#case-086--early_adulthood--career_family)
    - [case_103 — germany_years](#case-103--early_adulthood--germany_years)
- **later_adulthood** (1)
    - [case_062 — spouse_child_same_sentence](#case-062--later_adulthood--spouse_child_same_sentence)
- **legacy_reflection** (3)
    - [case_019 — reflection](#case-019--legacy_reflection--reflection)
    - [case_096 — health](#case-096--legacy_reflection--health)
    - [case_102 — travel](#case-102--legacy_reflection--travel)
- **midlife** (6)
    - [case_015 — parental_care](#case-015--midlife--parental_care)
    - [case_018 — middle_moves](#case-018--midlife--middle_moves)
    - [case_037 — health_and_body](#case-037--midlife--health_and_body)
    - [case_074 — family_traditions](#case-074--midlife--family_traditions)
    - [case_093 — spouse_detail](#case-093--midlife--spouse_detail)
    - [case_099 — faith](#case-099--midlife--faith)
- **transitional_adolescence** (3)
    - [case_020 — civic_entry_age_18](#case-020--transitional_adolescence--civic_entry_age_18)
    - [case_052 — first_job](#case-052--transitional_adolescence--first_job)
    - [case_059 — career_progression_vs_early](#case-059--transitional_adolescence--career_progression_vs_early)

---

### case_011 — developmental_foundations / origin_point

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> Do you know the hospital or the town where you were born?

**Narrator replies:**

> I was born in Stanley, North Dakota. Christmas Eve, 1939.

**Expected fields:**

- `personal.placeOfBirth` = "Stanley, North Dakota"
- `personal.dateOfBirth` = "1939-12-24"

**extractPriority:** `personal.dateOfBirth`, `personal.placeOfBirth`

**Forbidden fields:** `family.spouse.firstName`, `education.schooling`

**Truth zones:**

- **must_extract**
    - `personal.placeOfBirth = "Stanley, North Dakota"`
    - `personal.dateOfBirth = "1939-12-24"`
- **must_not_write**
    - `family.spouse.firstName`
    - `education.schooling`

_Scoring note: Clean single-fact: birth context. Kent shares Christmas Eve birthday with son Christopher — tests that extractor doesn't confuse the two when narrator is Kent._

---

### case_012 — early_adulthood / relationship_anchors

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> What year did you get married, and where was the ceremony?

**Narrator replies:**

> I married Janice Josephine Zarr on October 10th, 1959. I was nineteen and she was twenty.

**Expected fields:**

- `family.spouse.firstName` = "Janice"
- `family.marriageDate` = "1959-10-10"

**extractPriority:** `family.spouse`, `family.marriageDate`

**Forbidden fields:** `personal.dateOfBirth`, `education.earlyCareer`

**Truth zones:**

- **must_extract**
    - `family.spouse.firstName = "Janice"`
    - `family.marriageDate = "1959-10-10"`
- **must_not_write**
    - `personal.dateOfBirth`
    - `education.earlyCareer`

_Scoring note: Multi-fact: spouse name + marriage date. Removed maidenName expectation — LLM may route Zarr to lastName or maidenName unpredictably; testing the core spouse+date extraction._

---

### case_013 — early_adulthood / parenthood

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Tell me about your children — let's start with the oldest.

**Narrator replies:**

> Our first boy was Vincent Edward. He was born over in Germany while we were living there. Then Jason Richard came along, and our youngest was Christopher Todd, born December 24th, 1962 in Williston, North Dakota — same birthday as me.

**Expected fields:**

- `family.children.firstName` = "Christopher"
- `family.children.placeOfBirth` = "Williston, North Dakota"
- `family.children.dateOfBirth` = "1962-12-24"

**extractPriority:** `family.children`, `residence.place`

**Forbidden fields:** `family.spouse.firstName`, `parents.firstName`

**Truth zones:**

- **must_extract**
    - `family.children.firstName = "Christopher"`
    - `family.children.placeOfBirth = "Williston, North Dakota"`
    - `family.children.dateOfBirth = "1962-12-24"`
- **must_not_write**
    - `family.spouse.firstName`
    - `parents.firstName`

_Scoring note: Compound multi-fact: three children with partial dates/places. Known CLAIMS-01 gap. Tests entity coherence — Vincent's birthplace is Germany, Christopher's is Williston. Must not cross-contaminate._

---

### case_014 — developmental_foundations / early_caregivers

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Where did you fall in the sibling lineup — oldest, youngest, somewhere in between?

**Narrator replies:**

> I was the middle child. My older sister Sharon was born in 1937, I came along in '39, and then my little sister Linda in '42.

**Expected fields:**

- `personal.birthOrder` = "2"
- `siblings.firstName` = "Linda"
- `siblings.birthOrder` = "younger"

**extractPriority:** `parents.firstName`, `parents.relation`, `siblings.firstName`, `siblings.birthOrder`

**Forbidden fields:** `family.spouse.firstName`, `education.schooling`

**Truth zones:**

- **must_extract**
    - `personal.birthOrder = "2"`
    - `siblings.firstName = "Linda"`
    - `siblings.birthOrder = "younger"`
- **must_not_write**
    - `family.spouse.firstName`
    - `education.schooling`

_Scoring note: Compound multi-fact: two siblings + narrator birth order. Tests sibling repeatable grouping — Sharon and Linda must stay as separate entities with correct birth orders._

---

### case_015 — midlife / parental_care

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> What year did you have to say goodbye to your father?

**Narrator replies:**

> Dad died December 23rd, 1967. I was twenty-eight. The day before Christmas Eve — the day before my birthday.

**Expected fields:**

- `parents.notableLifeEvents` = "died December 23rd, 1967"

**extractPriority:** `parents.notableLifeEvents`

**Forbidden fields:** `personal.dateOfBirth`, `laterYears.retirement`

**Truth zones:**

- **must_extract**
    - `parents.notableLifeEvents = "died December 23rd, 1967"`
- **must_not_write**
    - `personal.dateOfBirth`
    - `laterYears.retirement`

_Scoring note: Clean single-fact: parent death date. Tests that narrator's age mention (28) and birthday reference don't cause extraction of personal.dateOfBirth — the subject guard should block narrator identity re-extraction from a parental context._

---

### case_016 — early_adulthood / professional_genesis

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> What kind of work did you do for a living?

**Narrator replies:**

> Construction and trades. That's what I did my whole life. Built things with my hands.

**Expected fields:**

- `education.earlyCareer` = "Construction and trades"

**extractPriority:** `education.earlyCareer`, `education.careerProgression`

**Forbidden fields:** `personal.dateOfBirth`, `family.marriageDate`

**Truth zones:**

- **must_extract**
    - `education.earlyCareer = "Construction and trades"`
- **must_not_write**
    - `personal.dateOfBirth`
    - `family.marriageDate`

_Scoring note: Clean single-fact: career from a short answer. Tests that a brief reply still triggers extraction._

---

### case_017 — developmental_foundations / childhood_pets

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> Was there an animal in your childhood that had its own personality you still remember?

**Narrator replies:**

> We had a Golden Retriever, Ivan. Good dog.

**Expected fields:**

- `pets.name` = "Ivan"
- `pets.species` = "dog"

**extractPriority:** `hobbies.hobbies`, `earlyMemories.significantEvent`

**Forbidden fields:** `family.children.firstName`, `education.schooling`

**Truth zones:**

- **must_extract**
    - `pets.name = "Ivan"`
    - `pets.species = "dog"`
- **must_not_write**
    - `family.children.firstName`
    - `education.schooling`

_Scoring note: Pet extraction: Golden Retriever named Ivan from terse reply. WO-SCHEMA-02 routes to pets.* fields._

---

### case_018 — midlife / middle_moves

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> What cities or towns did you call home during your midlife years?

**Narrator replies:**

> Well, we lived in Germany for a while when the boys were small — that's where Vincent was born. Then we moved around quite a bit. North Dakota of course, and other places.

**Expected fields:**

- `residence.place` = "Germany"

**extractPriority:** `residence.place`, `residence.period`

**Forbidden fields:** `personal.dateOfBirth`, `family.marriageDate`

**Truth zones:**

- **must_extract**
    - `residence.place = "Germany"`
- **must_not_write**
    - `personal.dateOfBirth`
    - `family.marriageDate`

_Scoring note: Multi-fact: multiple residences from a vague answer. Tests that extractor captures places even when dates are absent. Confidence should be 0.7 (implied, not precisely stated)._

---

### case_019 — legacy_reflection / reflection

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> What do you know now that no one could have told your younger self?

**Narrator replies:**

> That time goes faster than you think. You blink and your kids are grown and your parents are gone.

**Expected fields:**

- `laterYears.lifeLessons` = "Time goes faster than you think"

**extractPriority:** `laterYears.lifeLessons`, `hobbies.personalChallenges`

**Forbidden fields:** `personal.dateOfBirth`, `family.marriageDate`, `education.earlyCareer`

**Truth zones:**

- **must_extract**
    - `laterYears.lifeLessons = "Time goes faster than you think"`
- **must_not_write**
    - `personal.dateOfBirth`
    - `family.marriageDate`
    - `education.earlyCareer`

_Scoring note: Clean single-fact: reflective life lesson. Tests that philosophical/emotional content maps to laterYears.lifeLessons and not to children/parent fields despite mentioning both._

---

### case_020 — transitional_adolescence / civic_entry_age_18

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> When you turned eighteen, what was the first thing that made adulthood feel official?

**Narrator replies:**

> I don't really remember anything special about turning eighteen. I was already working construction by then.

**Expected fields:**

- `education.earlyCareer` = "Was already working construction by age eighteen"

**extractPriority:** `laterYears.significantEvent`, `education.earlyCareer`

**Forbidden fields:** `personal.dateOfBirth`, `laterYears.retirement`

**Truth zones:**

- **must_extract**
    - `education.earlyCareer = "Was already working construction by age eighteen"`
- **must_not_write**
    - `personal.dateOfBirth`
    - `laterYears.retirement`

_Scoring note: Clean single-fact from a dismissive reply. Tests that extractor still finds a career fact even when narrator says 'I don't really remember.' Confidence should be 0.7 (implied timeline, not precise)._

---

### case_033 — developmental_foundations / family_stories_and_lore

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> Did anyone in your family serve in the military?

**Narrator replies:**

> My great-grandfather John Michael Shong served in the Civil War. Company G of the 28th Infantry, from February 1865 to January 1866. He was stationed in Kansas and Missouri.

**Expected fields:**

- `military.branch` = "Army"
- `military.yearsOfService` = "1865-1866"
- `military.deploymentLocation` = "Kansas and Missouri"
- `military.significantEvent` = "Civil War service, Company G, 28th Infantry"

**extractPriority:** `military.branch`, `military.yearsOfService`, `military.significantEvent`

**Forbidden fields:** `personal.dateOfBirth`, `education.earlyCareer`

**Truth zones:**

- **must_extract**
    - `military.branch = "Army"`
    - `military.yearsOfService = "1865-1866"`
    - `military.deploymentLocation = "Kansas and Missouri"`
    - `military.significantEvent = "Civil War service, Company G, 28th Infantry"`
- **must_not_write**
    - `personal.dateOfBirth`
    - `education.earlyCareer`

_Scoring note: WO-SCHEMA-02 military: family military history from great-grandfather. Tests that branch is inferred as Army from 'Infantry' context. Note: this is family military, not narrator's own service — field should still capture it since it's narrator-reported family history._

---

### case_037 — midlife / health_and_body

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> Was there a time when your health changed how you lived your daily life?

**Narrator replies:**

> When I got older my knees gave out from all those years of construction. Concrete and roofing — that's hard on the body. I had to slow down a lot in my seventies.

**Expected fields:**

- `health.majorCondition` = "Knee problems from construction work"
- `health.lifestyleChange` = "Had to slow down in seventies"

**extractPriority:** `health.majorCondition`, `health.milestone`, `health.lifestyleChange`

**Forbidden fields:** `personal.dateOfBirth`, `education.earlyCareer`

**Truth zones:**

- **must_extract**
    - `health.majorCondition = "Knee problems from construction work"`
    - `health.lifestyleChange = "Had to slow down in seventies"`
- **must_not_write**
    - `personal.dateOfBirth`
    - `education.earlyCareer`

_Scoring note: WO-SCHEMA-02 health: occupational health impact. Tests that health.majorCondition and lifestyleChange extract from a narrative about aging and physical wear. Confidence should be 0.8 — narrator implies rather than states a diagnosis._

---

### case_044 — early_adulthood / first_home

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> Where was the first place you and Janice lived after getting married?

**Narrator replies:**

> We went to Germany. That's where our first boy Vincent was born. I was working construction over there. We came back to North Dakota after that.

**Expected fields:**

- `residence.place` = "Germany"
- `travel.destination` = "Germany"
- `travel.purpose` = "Work — construction"

**extractPriority:** `travel.destination`, `travel.purpose`, `residence.place`

**Forbidden fields:** `personal.dateOfBirth`, `family.marriageDate`

**Truth zones:**

- **must_extract**
    - `residence.place = "Germany"`
    - `travel.destination = "Germany"`
    - `travel.purpose = "Work — construction"`
- **must_not_write**
    - `personal.dateOfBirth`
    - `family.marriageDate`

_Scoring note: WO-SCHEMA-02 travel + residence overlap: Germany is both a residence and a travel/relocation event. Tests that extractor can produce both residence.place AND travel.destination for the same place when the context warrants both. Travel confidence should be lower (0.7) since it's more of a relocation than a trip._

---

### case_048 — early_adulthood / parenthood

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> Tell me about your children.

**Narrator replies:**

> We had three boys — Vincent, Jason, and Christopher. Vincent was the oldest. They all grew up in North Dakota.

**Expected fields:**

- `family.children.firstName` = "Vincent"
- `family.children.relation` = "son"

**extractPriority:** `family.children.firstName`, `family.children.relation`

**Forbidden fields:** `siblings.firstName`, `siblings.relation`

**Truth zones:**

- **must_extract**
    - `family.children.firstName = "Vincent"`
    - `family.children.relation = "son"`
- **must_not_write**
    - `siblings.firstName`
    - `siblings.relation`

_Scoring note: WO-EX-REROUTE-01 siblings NO-REROUTE: children in parenthood section. Even though answer says 'boys', rerouter must NOT misfire to siblings.* because section is parenthood, not sibling_dynamics. Tests cross-family damage prevention._

---

### case_050 — early_adulthood / first_home

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> Where was the first place you and Janice lived?

**Narrator replies:**

> We moved to Bismarck after we got married. Lived there about three years while I was working.

**Expected fields:**

- `residence.place` = "Bismarck"
- `residence.period` = "about three years"

**extractPriority:** `residence.place`, `residence.period`

**Forbidden fields:** `personal.placeOfBirth`

**Truth zones:**

- **must_extract**
    - `residence.place = "Bismarck"`
    - `residence.period = "about three years"`
- **must_not_write**
    - `personal.placeOfBirth`

_Scoring note: WO-EX-REROUTE-01 birthplace NO-REROUTE: residence.place in a residence section with no birth cues. Rerouter must NOT misfire to personal.placeOfBirth. Tests that 'moved to' is not confused with 'born in'._

---

### case_052 — transitional_adolescence / first_job

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> What was the first real job you ever had?

**Narrator replies:**

> I started working construction right out of school. That was my first real job.

**Expected fields:**

- `education.earlyCareer` = "working construction"

**extractPriority:** `education.earlyCareer`

**Forbidden fields:** `education.careerProgression`

**Truth zones:**

- **must_extract**
    - `education.earlyCareer = "working construction"`
- **must_not_write**
    - `education.careerProgression`

_Scoring note: WO-EX-REROUTE-01 career NO-REROUTE: first job with no duration markers. Rerouter must NOT misfire to education.careerProgression. Tests that 'first job' stays as earlyCareer._

---

### case_054 — childhood_origins / mixed_narrator_family

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Where were you born, and where were your parents from?

**Narrator replies:**

> I was born in Bismarck, North Dakota. My dad was from Stanley, and my mother grew up near Williston.

**Expected fields:**

- `personal.placeOfBirth` = "Bismarck"

**extractPriority:** `personal.placeOfBirth`, `parents.birthPlace`

**Forbidden fields:** `residence.place`

**Truth zones:**

- **must_extract**
    - `personal.placeOfBirth = "Bismarck"`
- **must_not_write**
    - `residence.place`

_Scoring note: WO-EX-TWOPASS-01: narrator birthplace vs family member origins in one answer. Tests that two-pass separates narrator personal fields from family-scoped fields and doesn't route birthplace to residence._

---

### case_059 — transitional_adolescence / career_progression_vs_early

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Tell me about the work you've done over your life.

**Narrator replies:**

> I started out as a welder's helper right out of school. Then I got on at the plant and worked my way up to foreman. I was there for thirty-two years until I retired.

**Expected fields:**

- `education.earlyCareer` = "welder's helper"
- `education.careerProgression` = "foreman"

**extractPriority:** `education.earlyCareer`, `education.careerProgression`

**Truth zones:**

- **must_extract**
    - `education.earlyCareer = "welder's helper"`
    - `education.careerProgression = "foreman"`

_Scoring note: WO-EX-TWOPASS-01: early career AND career progression in same answer with duration markers. Tests separation of first job from long-term career._

---

### case_062 — later_adulthood / spouse_child_same_sentence

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Can you tell me about your wife and children?

**Narrator replies:**

> My wife Dorothy and I had four children. Our boy Chris was the oldest, then came Vince, Jason, and Christine.

**Expected fields:**

- `family.spouse.firstName` = "Dorothy"
- `family.children.firstName` = "Chris"
- `family.children.relation` = "son"

**extractPriority:** `family.spouse.firstName`, `family.children.firstName`

**Forbidden fields:** `siblings.firstName`, `parents.firstName`

**Truth zones:**

- **must_extract**
    - `family.spouse.firstName = "Dorothy"`
    - `family.children.firstName = "Chris"`
    - `family.children.relation = "son"`
- **must_not_write**
    - `siblings.firstName`
    - `parents.firstName`

_Scoring note: WO-EX-TWOPASS-01: spouse and multiple children mentioned together. Tests role-based routing for spouse vs children when both appear. 'Our boy Chris' should route to family.children, not siblings._

---

### case_064 — early_adulthood / marriage_story

questionType: anchor  ·  caseType: mixed_narrative  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Tell me about how you and Janice met and got married.

**Narrator replies:**

> Janice was something else. She was a country girl, grew up milking cows and riding her horse Grey out in Dodge. Her dad Pete worked on the Garrison Dam for a while, so the family moved around quite a bit — Dodge, Glen Ulin, Strasburg. We got married October 10, 1959. I was only nineteen and she was twenty. We didn't have much but we had each other. The weather that day was beautiful, one of those perfect fall days in North Dakota where the sky just goes on forever. Her mother Josie made the best kuchen you ever tasted for the reception.

**Expected fields:**

- `family.marriageDate` = "1959-10-10"
- `family.spouse.firstName` = "Janice"

**extractPriority:** `family.marriageDate`, `family.spouse.firstName`

**Truth zones:**

- **must_extract**
    - `family.marriageDate = "1959-10-10"`
    - `family.spouse.firstName = "Janice"`
- **may_extract**
    - `family.spouse.maidenName = "Zarr"`
- **should_ignore**
    - `pets.name  _(Grey is Janice's childhood horse, mentioned in passing — not Kent's pet)_`
    - `residence.place  _(Dodge, Glen Ulin, Strasburg are Janice's childhood homes, not Kent's residences)_`
- **must_not_write**
    - `parents.firstName`

_Scoring note: Mixed narrative: marriage story with side detail about Janice's background, weather, food. Horse Grey and Janice's childhood towns are true but should not be extracted as Kent's data. Tests narrator-vs-family attribution._

---

### case_068 — developmental_foundations / family_loss

questionType: anchor  ·  caseType: mixed_narrative  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Were there any big losses in your family when you were growing up?

**Narrator replies:**

> My dad Ervin — he lost his own father George when he was only four years old. That was 1914. And then my grandmother Elizabeth, she remarried a man named William Mc Raith in 1916, but he died too, just two years later in 1918. So she was widowed twice by the time she was forty-one. She had a daughter Alice from that second marriage. Alice never married. My dad grew up in the Ross, North Dakota area. He married my mom Leila Myrtle Carkuff and they had us three kids — Sharon first in '37, me in '39, and Linda in '42. Then Dad died December 23, 1967. I was twenty-eight. The day before Christmas Eve, which is my birthday. That was hard.

**Expected fields:**

- `parents.notableLifeEvents` = "Father Ervin died December 23, 1967"

**extractPriority:** `parents.notableLifeEvents`

**Truth zones:**

- **must_extract**
    - `parents.notableLifeEvents = "Ervin died December 23, 1967"`
    - `parents.firstName = "Ervin"`
- **may_extract**
    - `parents.lastName = "Horne"`
    - `grandparents.firstName = "Elizabeth"`
    - `grandparents.memorableStory = "widowed twice"`
    - `siblings.firstName = "Sharon"`
- **should_ignore**
    - `personal.dateOfBirth  _(birthday context mentioned but not new data — already known)_`

_Scoring note: Mixed narrative: loss question opens up multi-generational family story. Father's death is the primary target, but grandparent widowing and sibling enumeration are truthful detail. Tests extraction depth vs restraint on a family-heavy answer._

---

### case_071 — early_adulthood / military_family

questionType: anchor  ·  caseType: mixed_narrative  ·  style: topical  ·  currentExtractorExpected: False

**Lori asks:**

> Was there any military service in your family?

**Narrator replies:**

> Well, going way back, my great-grandfather John Michael Shong served in the Civil War. Company G, 28th Infantry, from February 1865 to January 1866, down in Kansas and Missouri. He was French, came from Lorraine. But as for me personally, I didn't serve. I went into construction and trades. We did live in Germany for a while though — that's where our first boy Vincent was born. But that was for work, not military. Some people assume it was a military posting but it wasn't.

**Expected fields:**

_none_

**extractPriority:** `military.branch`

**Forbidden fields:** `military.branch`, `military.yearsOfService`, `military.rank`

**Truth zones:**

- **may_extract**
    - `grandparents.memorableStory = "great-grandfather served in Civil War"`
    - `family.children.firstName = "Vincent"`
    - `family.children.placeOfBirth = "Germany"`
- **should_ignore**
    - `education.earlyCareer  _(construction mentioned but already known)_`
- **must_not_write**
    - `military.branch`
    - `military.yearsOfService`
    - `military.deploymentLocation`

_Scoring note: Mixed narrative: military question but narrator explicitly says he didn't serve. Great-grandfather's Civil War service is true family history. Germany was residence, not deployment. Tests whether Lori correctly abstains from military extraction for Kent while optionally capturing ancestor service._

---

### case_074 — midlife / family_traditions

questionType: anchor  ·  caseType: mixed_narrative  ·  style: thematic  ·  currentExtractorExpected: False

**Lori asks:**

> What family traditions or routines were important to your family?

**Narrator replies:**

> The Shong side — my dad's mother's people — they were French, from Lorraine. And the Bolleys were German, from Hanover. So we had this mix. Christmas was always a big deal, especially since Chris and I share a birthday on Christmas Eve. Janice would cook for days. Her mother Josie taught her how to handle a knife in the kitchen — learned it at Mount Marty when she worked in the kitchen there. We'd have kuchen and all the German-Russian dishes. The whole family would come when they could. That was the thing about moving around so much for work — you really treasured the times everyone was together.

**Expected fields:**

_none_

**extractPriority:** `hobbies.hobbies`

**Truth zones:**

- **may_extract**
    - `hobbies.hobbies = "family holiday cooking traditions"`
    - `personal.culture = "French-German heritage, German-Russian food traditions"`
- **should_ignore**
    - `family.children.firstName  _(Chris mentioned but only as birthday context)_`
    - `family.spouse.firstName  _(Janice mentioned but already known)_`
- **must_not_write**
    - `parents.notableLifeEvents`

_Scoring note: Mixed narrative: thematic reflection on family traditions. Lots of true cultural detail but no hard facts to extract — mostly atmosphere and values. Tests whether Lori can recognize that a rich narrative answer may have limited extractable data._

---

### case_077 — developmental_foundations / siblings_childhood

questionType: anchor  ·  caseType: mixed_narrative  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Did you have brothers or sisters? What were they like?

**Narrator replies:**

> I had two sisters. Sharon was the oldest, born April 8, 1937. She married Ed Woodmansee. And then Linda was the youngest, born July 27, 1942. I was in the middle — the only boy. We grew up in North Dakota, kids of Ervin and Leila Horne. After Dad died in '67 we all kind of had to pull together. Mom Leila lived until 1985, she passed December 1st that year. We stayed close considering how much everybody moved around.

**Expected fields:**

- `siblings.firstName` = "Sharon"
- `siblings.relation` = "Sister"

**extractPriority:** `siblings.firstName`, `siblings.relation`

**Truth zones:**

- **must_extract**
    - `siblings.firstName = "Sharon, Linda"`
    - `siblings.relation = "Sister"`
- **may_extract**
    - `siblings.birthOrder = "older, younger"`
    - `siblings.lastName = "Woodmansee, Horne"`
- **should_ignore**
    - `parents.firstName  _(Ervin and Leila mentioned but as context)_`
    - `parents.notableLifeEvents  _(dad's death and mom's death mentioned in passing — already captured elsewhere)_`
    - `personal.birthOrder  _(Kent says 'I was in the middle' — true but low-value to extract here)_`

_Scoring note: Mixed narrative: both siblings with birth dates and marriage detail, plus parent death dates woven in. Tests compound sibling extraction while not duplicating parent data._

---

### case_080 — developmental_foundations / family_history

questionType: anchor  ·  caseType: dense_truth  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> What do you know about your grandparents on your father's side?

**Narrator replies:**

> Well my dad Ervin's parents were George Horne and Elizabeth Shong. George arrived in Ross, North Dakota in 1902. He walked north from Ross looking for good land, filed on a claim, and got the title June 16, 1904. He'd married Elizabeth — everybody called her Lizzie — on December 29, 1903 in Fall Creek, Wisconsin. They had six children: Margaret in 1904, then Phyllis in 1907 but she died as a baby, Ervin — my dad — in 1909, Isabel in 1910 who also died young, James in 1911, and Arthur in 1912. George died April 12, 1914. My dad was only four. Elizabeth married again — William Mc Raith — on May 1, 1916. But he died too, May 2, 1918. She had one daughter from that marriage, Alice, born September 23, 1917. Alice never married. Elizabeth lived until April 26, 1952.

**Expected fields:**

- `grandparents.firstName` = "George"
- `grandparents.memorableStory` = "arrived in Ross ND 1902, walked north to find land, died 1914"

**extractPriority:** `grandparents.firstName`, `grandparents.memorableStory`

**Truth zones:**

- **must_extract**
    - `grandparents.firstName = "George, Elizabeth"`
    - `grandparents.lastName = "Horne"`
    - `grandparents.maidenName = "Shong"`
    - `grandparents.memorableStory = "homesteaded Ross ND, married 1903, six children, George died 1914, Elizabeth remarried then widowed again"`
- **may_extract**
    - `grandparents.birthPlace = "Fall Creek, Wisconsin"`
- **should_ignore**
    - `parents.firstName  _(Ervin mentioned but as context for the grandparent story)_`
    - `parents.birthPlace  _(not directly stated here)_`
- **must_not_write**
    - `family.children.firstName`

_Scoring note: Dense truth: packed with dates, names, and events across two generations. Tests whether Lori can extract grandparent data comprehensively from a fact-dense family history, handling the homesteading narrative, two marriages, and child enumeration._

---

### case_083 — developmental_foundations / grandmother_story

questionType: followup  ·  caseType: dense_truth  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> You mentioned your grandmother Elizabeth — what else do you know about her family?

**Narrator replies:**

> Lizzie Shong was the youngest of eight children. Her dad John Michael and mom Christine had: Charlie, born 1864, married Tillie Welke, ran a hotel in Penn, North Dakota. Sarah, 1866, married Gustav Glenz. Little Maggie, 1868, died in infancy. Christie, 1869, married Henry Graichen, worked as a cook across the Midwest. Nicholas, 1871, married Adone Voechting. Henry — they called him Hank — 1873, married Lola Archer. Cora, 1875, also died in infancy. And then Lizzie, the youngest, 1877. Around the turn of the century she went to Penn to visit her brother Charlie and find work as a seamstress. That's where she met my grandfather George. The Shong name was originally Schong — they dropped the C when they came to America. Might have even been Le Shong once.

**Expected fields:**

- `grandparents.memorableStory` = "youngest of eight children of John Michael Shong and Christine Bolley"

**extractPriority:** `grandparents.memorableStory`

**Truth zones:**

- **must_extract**
    - `grandparents.memorableStory = "youngest of eight children, worked as seamstress in Penn ND, name originally Schong"`
    - `grandparents.maidenName = "Shong"`
- **may_extract**
    - `grandparents.ancestry = "French, German"`
- **must_not_write**
    - `siblings.firstName`
    - `family.children.firstName`

_Scoring note: Dense truth: exhaustive sibling enumeration for great-aunt/uncle generation. The sibling list is historically accurate but represents Elizabeth's siblings, not Kent's. Tests whether Lori focuses on grandmother's story without creating sibling entries for 19th century relatives._

---

### case_086 — early_adulthood / career_family

questionType: anchor  ·  caseType: dense_truth  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Tell me about your working life and how it shaped your family.

**Narrator replies:**

> I went into construction and trades pretty much right away. That meant we moved a lot — wherever the work was. We lived in Germany for a while, that's where our oldest boy Vincent was born. Then back to North Dakota and other places. Janice was a trooper through all of it, kept the boys on track even when we'd be packing up and moving to a new town every year or two. She'd been through it herself growing up — her dad Pete moved the family from Dodge to Glen Ulin to Strasburg for work. Three boys we raised — Vincent, Jason, and Christopher. Chris was born December 24, 1962 in Williston, same day as my birthday. By the time I was done working I'd built things all over. It was a good career, hard but good.

**Expected fields:**

- `education.earlyCareer` = "Construction and trades"

**extractPriority:** `education.earlyCareer`, `education.careerProgression`, `residence.place`

**Truth zones:**

- **must_extract**
    - `education.earlyCareer = "Construction and trades"`
- **may_extract**
    - `education.careerProgression = "long career in construction across multiple states"`
    - `residence.place = "Germany, North Dakota"`
    - `family.children.firstName = "Vincent, Jason, Christopher"`
    - `family.children.dateOfBirth = "1962-12-24"`
    - `family.children.placeOfBirth = "Germany, Williston ND"`
- **should_ignore**
    - `family.spouse.firstName  _(Janice mentioned but already established)_`
    - `personal.dateOfBirth  _(birthday mentioned but already known)_`

_Scoring note: Dense truth: career overview with family context, multiple children, and spouse detail woven in. Tests career extraction while handling the interleaved family narrative._

---

### case_090 — developmental_foundations / father_detail

questionType: followup  ·  caseType: follow_up  ·  style: thematic  ·  currentExtractorExpected: False

**Prior context:**

> Narrator previously stated father Ervin died December 23, 1967.

**Lori asks:**

> You mentioned your father Ervin passed away in 1967 — what was that like?

**Narrator replies:**

> It was December 23rd. The day before my birthday, Christmas Eve. I was twenty-eight. Mom was devastated. She kept going though — she lived another eighteen years, until 1985. Died December 1st that year. Dad and I had a complicated relationship, like a lot of fathers and sons of that generation. He grew up hard — lost his own father at four, then his stepfather died too. But he was a good man.

**Expected fields:**

_none_

**extractPriority:** `parents.notableLifeEvents`

**Truth zones:**

- **may_extract**
    - `parents.notableLifeEvents = "mother Leila died December 1, 1985"`
    - `earlyMemories.significantEvent = "father's death day before birthday"`
- **should_ignore**
    - `personal.dateOfBirth  _(birthday referenced but already known)_`
    - `parents.firstName  _(Ervin already captured)_`

_Scoring note: Follow-up: reflective elaboration on father's death. New fact: mother Leila's death date. Tests whether Lori captures the new parent fact while not re-extracting known data._

---

### case_093 — midlife / spouse_detail

questionType: followup  ·  caseType: follow_up  ·  style: thematic  ·  currentExtractorExpected: False

**Prior context:**

> Narrator previously stated spouse Janice Josephine Zarr, married October 10, 1959.

**Lori asks:**

> What else can you tell me about Janice?

**Narrator replies:**

> Janice is a strong woman. She grew up milking cows and riding horses in North Dakota. Her dad Pete worked all kinds of jobs — Garrison Dam, carpentry, steam boiler work. She went to Bismarck Junior College before we got married. She's always been independent. We raised three boys together and she kept that family running through every move and every job change.

**Expected fields:**

_none_

**extractPriority:** `family.spouse.firstName`

**Truth zones:**

- **may_extract**
    - `family.spouse.maidenName = "Zarr"`
    - `family.marriageNotes = "raised three boys through many moves"`
- **should_ignore**
    - `family.spouse.firstName  _(Janice already captured)_`
- **must_not_write**
    - `parents.firstName`
    - `parents.occupation`
    - `education.higherEducation`

_Scoring note: Follow-up: reflective praise of spouse. Pete's occupation and Janice's education are HER data, not Kent's — must not extract as Kent's parent/education fields. Tests attribution boundary._

---

### case_096 — legacy_reflection / health

questionType: anchor  ·  caseType: null_clarify  ·  style: topical  ·  currentExtractorExpected: True

**Lori asks:**

> Have you dealt with any major health issues over the years?

**Narrator replies:**

> Oh you know, the usual stuff that comes with getting old. But nothing I want to go into. We're all still here, that's what matters.

**Expected fields:**

_none_

**extractPriority:** `health.majorCondition`

**Forbidden fields:** `health.majorCondition`, `health.milestone`, `health.lifestyleChange`

**Truth zones:**

- **must_not_write**
    - `health.majorCondition`
    - `health.milestone`
    - `health.lifestyleChange`
    - `laterYears.significantEvent`

_Scoring note: Null/clarify: narrator deflects health question. 'The usual stuff' is NOT a health condition to extract. Tests whether Lori respects privacy boundaries and doesn't fabricate health data from a deflection._

---

### case_099 — midlife / faith

questionType: anchor  ·  caseType: null_clarify  ·  style: thematic  ·  currentExtractorExpected: False

**Lori asks:**

> Has faith been important in your life?

**Narrator replies:**

> I suppose so, in the background. The Shong family was Catholic — that goes way back to when they were in France. But I'm not a churchgoing man really. I believe in doing right by people. That's my faith, I guess.

**Expected fields:**

_none_

**extractPriority:** `faith.denomination`

**Truth zones:**

- **may_extract**
    - `faith.denomination = "Catholic (family heritage)"`
    - `faith.values = "doing right by people"`
- **should_ignore**
    - `faith.role  _(not a churchgoing man — no active role to extract)_`
    - `grandparents.ancestry  _(Shong Catholic heritage mentioned but as context)_`

_Scoring note: Null/clarify: ambiguous faith answer. Family heritage is Catholic but Kent doesn't actively practice. Tests nuanced extraction — denomination is technically true but low confidence, values statement is extractable but might be too thin._

---

### case_102 — legacy_reflection / travel

questionType: anchor  ·  caseType: null_clarify  ·  style: site_artifact  ·  currentExtractorExpected: False

**Lori asks:**

> What's the most meaningful place you've ever been?

**Narrator replies:**

> Germany, probably. Not because of the sightseeing — it was where we were living when Vince was born. That made it real. But you know, I'm a North Dakota boy at heart. Stanley, where I was born. Ross, where my grandmother's people homesteaded. Fall Creek, Wisconsin, where the Shongs started out in America. Those are the places that mean something to me, even if I haven't been to all of them.

**Expected fields:**

_none_

**extractPriority:** `travel.significantTrip`

**Truth zones:**

- **may_extract**
    - `travel.significantTrip = "Germany — where first son was born"`
- **should_ignore**
    - `travel.destination  _(Stanley, Ross, Fall Creek are ancestral places, not trips)_`
    - `residence.place  _(Germany already known as residence)_`
    - `personal.placeOfBirth  _(Stanley already captured)_`
    - `grandparents.birthPlace  _(Fall Creek mentioned but as reflection, not new data)_`

_Scoring note: Null/clarify (site/artifact style): reflective answer about meaningful places. Most mentioned places are already captured elsewhere. Tests whether Lori creates new travel entries for ancestral places the narrator hasn't actually traveled to._

---

### case_103 — early_adulthood / germany_years

questionType: anchor  ·  caseType: mixed_narrative  ·  style: site_artifact  ·  currentExtractorExpected: False

**Lori asks:**

> What was it like living in Germany?

**Narrator replies:**

> It was an adventure. I was working construction over there. Janice and I were young, just starting out. Our oldest, Vincent Edward, was born there. That was a big deal — having your first child in a foreign country. Janice handled it like she handled everything, just took it in stride. She'd grown up tough, milking cows in North Dakota. A German hospital wasn't going to throw her off. After Vincent we came back to the States and eventually the other two boys came along — Jason and then Chris in Williston.

**Expected fields:**

- `residence.place` = "Germany"

**extractPriority:** `residence.place`, `family.children.placeOfBirth`

**Truth zones:**

- **must_extract**
    - `residence.place = "Germany"`
    - `family.children.placeOfBirth = "Germany"`
- **may_extract**
    - `family.children.firstName = "Jason, Christopher"`
    - `family.children.placeOfBirth_2 = "Williston (Chris)"`
- **should_ignore**
    - `education.earlyCareer  _(construction already captured)_`
    - `family.spouse.firstName  _(Janice already known)_`

_Scoring note: Mixed narrative (site/artifact): Germany years with family life detail. Tests residence extraction for Germany plus child's birthplace, while not over-extracting already-known spouse/career data._

---
