# Eval Cases — janice-josephine-horne

Generated: 2026-04-21T04:14:15.365328Z

Total cases for this narrator: **33**

Use this as a fact-check pass. For each case, read `Lori asks`, `Narrator replies`, and `Expected fields`, then mark:

- **FACT** — narratorReply matches biobuilder canon
- **FICTION** — narratorReply contradicts canon or invents facts not in canon
- **PARTIAL** — some of the reply is canon-grounded, some is invented
- **CANON-GAP** — reply is plausible but canon is silent; needs canon entry

---

## Index

- **childhood_origins** (1)
    - [case_058 — birthplace_vs_residence](#case-058--childhood_origins--birthplace_vs_residence)
- **developmental_foundations** (20)
    - [case_021 — origin_point](#case-021--developmental_foundations--origin_point)
    - [case_022 — educational_entry](#case-022--developmental_foundations--educational_entry)
    - [case_024 — early_caregivers](#case-024--developmental_foundations--early_caregivers)
    - [case_025 — childhood_pets](#case-025--developmental_foundations--childhood_pets)
    - [case_026 — educational_entry](#case-026--developmental_foundations--educational_entry)
    - [case_028 — family_rituals_and_holidays](#case-028--developmental_foundations--family_rituals_and_holidays)
    - [case_029 — childhood_fears_and_comforts](#case-029--developmental_foundations--childhood_fears_and_comforts)
    - [case_031 — family_stories_and_lore](#case-031--developmental_foundations--family_stories_and_lore)
    - [case_035 — family_rituals_and_holidays](#case-035--developmental_foundations--family_rituals_and_holidays)
    - [case_039 — community_belonging](#case-039--developmental_foundations--community_belonging)
    - [case_041 — childhood_pets](#case-041--developmental_foundations--childhood_pets)
    - [case_046 — childhood_pets](#case-046--developmental_foundations--childhood_pets)
    - [case_049 — origin_point](#case-049--developmental_foundations--origin_point)
    - [case_063 — childhood_home](#case-063--developmental_foundations--childhood_home)
    - [case_066 — childhood_pets](#case-066--developmental_foundations--childhood_pets)
    - [case_075 — mother_stories](#case-075--developmental_foundations--mother_stories)
    - [case_082 — childhood_moves](#case-082--developmental_foundations--childhood_moves)
    - [case_085 — father_story](#case-085--developmental_foundations--father_story)
    - [case_088 — childhood_pets](#case-088--developmental_foundations--childhood_pets)
    - [case_094 — sibling_detail](#case-094--developmental_foundations--sibling_detail)
- **early_adulthood** (6)
    - [case_023 — relationship_anchors](#case-023--early_adulthood--relationship_anchors)
    - [case_027 — post_education](#case-027--early_adulthood--post_education)
    - [case_030 — parenthood](#case-030--early_adulthood--parenthood)
    - [case_072 — marriage_children](#case-072--early_adulthood--marriage_children)
    - [case_078 — higher_education](#case-078--early_adulthood--higher_education)
    - [case_091 — marriage_detail](#case-091--early_adulthood--marriage_detail)
- **later_adulthood** (1)
    - [case_056 — negated_health](#case-056--later_adulthood--negated_health)
- **legacy_reflection** (1)
    - [case_097 — regrets](#case-097--legacy_reflection--regrets)
- **middle_adulthood** (1)
    - [case_061 — uncertain_date](#case-061--middle_adulthood--uncertain_date)
- **midlife** (2)
    - [case_038 — health_and_body](#case-038--midlife--health_and_body)
    - [case_100 — community](#case-100--midlife--community)
- **transitional_adolescence** (1)
    - [case_069 — school_experience](#case-069--transitional_adolescence--school_experience)

---

### case_021 — developmental_foundations / origin_point

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> What is the story your parents told you about the day you were born?

**Narrator replies:**

> I was born in Spokane, Washington on August 30th, 1939. My dad Pete was working at an aluminum factory out there. That's why we were in Washington — for his job.

**Expected fields:**

- `personal.placeOfBirth` = "Spokane, Washington"
- `personal.dateOfBirth` = "1939-08-30"
- `parents.firstName` = "Peter"
- `parents.occupation` = "Aluminum factory worker"

**extractPriority:** `personal.dateOfBirth`, `personal.placeOfBirth`, `parents.firstName`, `parents.occupation`

**Forbidden fields:** `family.spouse.firstName`, `education.schooling`

**Truth zones:**

- **must_extract**
    - `personal.placeOfBirth = "Spokane, Washington"`
    - `personal.dateOfBirth = "1939-08-30"`
    - `parents.firstName = "Peter"`
    - `parents.occupation = "Aluminum factory worker"`
- **must_not_write**
    - `family.spouse.firstName`
    - `education.schooling`

_Scoring note: Multi-fact: birth context + parent occupation from a narrative answer. Tests that 'Pete' extracts as parent name (template has 'Peter' — evaluator should accept 'Pete' as equivalent via preferred/nick name)._

---

### case_022 — developmental_foundations / educational_entry

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> What was the name of your primary school?

**Narrator replies:**

> I started school in Dodge, North Dakota. I was there for first and second grade. I could read big books already — the teacher used to have me read out loud to the whole class. I sat alone and I thought it was a punishment, but I think it was because I was ahead.

**Expected fields:**

- `education.schooling` = "Dodge, North Dakota"

**extractPriority:** `education.schooling`, `earlyMemories.firstMemory`

**Forbidden fields:** `family.marriageDate`, `parents.occupation`

**Truth zones:**

- **must_extract**
    - `education.schooling = "Dodge, North Dakota"`
- **must_not_write**
    - `family.marriageDate`
    - `parents.occupation`

_Scoring note: Multi-fact: school entry with both education and early memory. Tests dual extraction from a rich narrative reply._

---

### case_023 — early_adulthood / relationship_anchors

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> What year did you get married?

**Narrator replies:**

> I married Kent Horne on October 10th, 1959. I was twenty and he was nineteen.

**Expected fields:**

- `family.spouse.firstName` = "Kent"
- `family.spouse.lastName` = "Horne"
- `family.marriageDate` = "1959-10-10"

**extractPriority:** `family.spouse`, `family.marriageDate`

**Forbidden fields:** `personal.dateOfBirth`, `education.schooling`

**Truth zones:**

- **must_extract**
    - `family.spouse.firstName = "Kent"`
    - `family.spouse.lastName = "Horne"`
    - `family.marriageDate = "1959-10-10"`
- **must_not_write**
    - `personal.dateOfBirth`
    - `education.schooling`

_Scoring note: Multi-fact: spouse + marriage date. Verified working in live smoke test. This is the mirror of case_012 (Kent's perspective) — same marriage, different narrator._

---

### case_024 — developmental_foundations / early_caregivers

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Where did you fall in the sibling lineup?

**Narrator replies:**

> I was the middle child. My older sister Verene Marie — she married a Schnieder — she was the oldest. Then me. Then my little brother James Peter, who we called Jim. He was born in a car on the way to Richardton Hospital, can you believe that?

**Expected fields:**

- `personal.birthOrder` = "2"
- `siblings.firstName` = "James"
- `siblings.birthOrder` = "younger"

**extractPriority:** `siblings.firstName`, `siblings.birthOrder`

**Forbidden fields:** `family.spouse.firstName`, `education.higherEducation`

**Truth zones:**

- **must_extract**
    - `personal.birthOrder = "2"`
    - `siblings.firstName = "James"`
    - `siblings.birthOrder = "younger"`
- **must_not_write**
    - `family.spouse.firstName`
    - `education.higherEducation`

_Scoring note: Compound multi-fact: two siblings + narrator birth order + family lore (born in car). Tests repeatable sibling grouping. currentExtractorExpected=false for compound entity grouping._

---

### case_025 — developmental_foundations / childhood_pets

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> Was there an animal in your childhood that felt most like yours?

**Narrator replies:**

> Oh, my horse Grey. I loved that horse. I liked to be outside — my sister Verene hated it, but I was always out with Grey. And we had a dog named Spot, he was the last dog I had as a kid. Uncle Johnny got Spot when he rented a farm.

**Expected fields:**

- `pets.name` = "Grey"
- `pets.species` = "horse"

**extractPriority:** `hobbies.hobbies`, `earlyMemories.significantEvent`

**Forbidden fields:** `family.marriageDate`, `education.higherEducation`

**Truth zones:**

- **must_extract**
    - `pets.name = "Grey"`
    - `pets.species = "horse"`
- **must_not_write**
    - `family.marriageDate`
    - `education.higherEducation`

_Scoring note: Multi-fact: two pets (Grey horse, Spot dog) plus sibling contrast. WO-SCHEMA-02 routes to pets.* fields. Primary expected extraction is Grey the horse._

---

### case_026 — developmental_foundations / educational_entry

questionType: followup  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> Did you stay at one school or did you move around?

**Narrator replies:**

> Oh, I moved a lot. Dodge for first and second grade, then Sacred Hearts in Glen Ulin for third, fourth, and fifth. Then we moved to Strasburg for sixth grade — that's where Lawrence Welk was from, you know. The teacher there was a nun who was a real nut.

**Expected fields:**

- `education.schooling` = "Dodge"

**extractPriority:** `education.schooling`, `residence.place`

**Forbidden fields:** `family.marriageDate`, `personal.dateOfBirth`

**Truth zones:**

- **must_extract**
    - `education.schooling = "Dodge"`
- **must_not_write**
    - `family.marriageDate`
    - `personal.dateOfBirth`

_Scoring note: Clean single-fact (composite education string): three schools in sequence. Tests that a rich education narrative collapses into one education.schooling value rather than three separate items._

---

### case_027 — early_adulthood / post_education

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> Did you go to college after high school?

**Narrator replies:**

> Yes, I started at Bismarck Junior College. I studied Speech and History. Those credits transferred to UND.

**Expected fields:**

- `education.higherEducation` = "Bismarck Junior College, Speech and History; credits transferred to UND"

**extractPriority:** `education.higherEducation`, `residence.place`

**Forbidden fields:** `education.earlyCareer`, `family.marriageDate`

**Truth zones:**

- **must_extract**
    - `education.higherEducation = "Bismarck Junior College, Speech and History; credits transferred to UND"`
- **must_not_write**
    - `education.earlyCareer`
    - `family.marriageDate`

_Scoring note: Clean single-fact: higher education extraction. Tests education.higherEducation from a concise factual answer with school name, subjects, and transfer._

---

### case_028 — developmental_foundations / family_rituals_and_holidays

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> Was there a food, a song, or a ritual in your home that only made sense once you knew where your family came from?

**Narrator replies:**

> We were Germans from Russia. Both sides — the Zarrs and the Schaafs. My grandmother Josie's family, the Schaafs, came from Ukraine. My grandfather Mathias hated the Russians. That whole culture came through in the food and the way things were done.

**Expected fields:**

- `earlyMemories.significantEvent` = "Germans from Russia"

**extractPriority:** `hobbies.hobbies`, `earlyMemories.significantEvent`

**Forbidden fields:** `personal.dateOfBirth`, `education.schooling`, `family.marriageDate`

**Truth zones:**

- **must_extract**
    - `earlyMemories.significantEvent = "Germans from Russia"`
- **must_not_write**
    - `personal.dateOfBirth`
    - `education.schooling`
    - `family.marriageDate`

_Scoring note: Clean single-fact: cultural heritage from family rituals prompt. Tests that cultural context maps to earlyMemories or hobbies, not to invented culture.* fields._

---

### case_029 — developmental_foundations / childhood_fears_and_comforts

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> What were you most afraid of as a small child?

**Narrator replies:**

> I hated men. My uncle August was mean to me. I was afraid of him. But I wasn't afraid of much else — I liked being outside, I liked the animals, I was tough.

**Expected fields:**

- `earlyMemories.significantEvent` = "uncle August was mean"

**extractPriority:** `earlyMemories.significantEvent`, `hobbies.personalChallenges`

**Forbidden fields:** `personal.dateOfBirth`, `family.marriageDate`, `education.schooling`

**Truth zones:**

- **must_extract**
    - `earlyMemories.significantEvent = "uncle August was mean"`
- **must_not_write**
    - `personal.dateOfBirth`
    - `family.marriageDate`
    - `education.schooling`

_Scoring note: Clean single-fact: emotionally sensitive childhood memory. Tests extraction of personal/emotional content into earlyMemories. The 'hated men' detail is real template truth._

---

### case_030 — early_adulthood / parenthood

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Tell me about your children — let's start with the oldest.

**Narrator replies:**

> Our oldest is Vincent Edward — he was born over in Germany. Then Jason Richard. And the baby was Christopher Todd, born December 24th, 1962 in Williston, North Dakota. Same birthday as his father Kent — both Christmas Eve babies.

**Expected fields:**

- `family.children.firstName` = "Christopher"
- `family.children.placeOfBirth` = "Williston, North Dakota"
- `family.children.dateOfBirth` = "1962-12-24"

**extractPriority:** `family.children`, `residence.place`

**Forbidden fields:** `family.spouse.firstName`, `personal.dateOfBirth`

**Truth zones:**

- **must_extract**
    - `family.children.firstName = "Christopher"`
    - `family.children.placeOfBirth = "Williston, North Dakota"`
    - `family.children.dateOfBirth = "1962-12-24"`
- **must_not_write**
    - `family.spouse.firstName`
    - `personal.dateOfBirth`

_Scoring note: Compound multi-fact: three children from Janice's perspective (mirrors case_013 from Kent's). Known CLAIMS-01 gap. Also tests forbidden field: 'same birthday as his father Kent' must NOT re-extract Kent's DOB into personal.dateOfBirth (narrator is Janice, not Kent)._

---

### case_031 — developmental_foundations / family_stories_and_lore

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> Did you know any of your grandparents? What do you remember about them?

**Narrator replies:**

> My grandmother on my mother's side was Josie — Josephine Schaaf. She was fifty years old when she had my mother, which embarrassed her. And my grandfather Mathias Schaaf hated the Russians. His family came from Ukraine — we were Germans from Russia.

**Expected fields:**

- `grandparents.side` = "maternal"
- `grandparents.firstName` = "Josephine"
- `grandparents.lastName` = "Schaaf"
- `grandparents.ancestry` = "Germans from Russia"

**extractPriority:** `grandparents.side`, `grandparents.firstName`, `grandparents.lastName`, `grandparents.ancestry`, `grandparents.memorableStory`

**Forbidden fields:** `personal.dateOfBirth`, `family.spouse.firstName`

**Truth zones:**

- **must_extract**
    - `grandparents.side = "maternal"`
    - `grandparents.firstName = "Josephine"`
    - `grandparents.lastName = "Schaaf"`
    - `grandparents.ancestry = "Germans from Russia"`
- **must_not_write**
    - `personal.dateOfBirth`
    - `family.spouse.firstName`

_Scoring note: WO-SCHEMA-02 grandparents: compound multi-fact with two grandparents from one answer. Tests repeatable grandparents grouping — Josephine and Mathias must stay as separate entities. Also tests ancestry extraction for Germans from Russia heritage._

---

### case_035 — developmental_foundations / family_rituals_and_holidays

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> What role did church or faith play in your family growing up?

**Narrator replies:**

> We were Catholic. My sister Verene's confirmation name was Gertrude. My mother Josie went to Mount Marty in Yankton for high school — that was a Catholic school run by nuns. The faith was a big part of everything.

**Expected fields:**

- `faith.denomination` = "Catholic"
- `faith.significantMoment` = "Mother Josie attended Mount Marty Catholic school in Yankton"

**extractPriority:** `faith.denomination`, `faith.role`, `faith.significantMoment`

**Forbidden fields:** `personal.dateOfBirth`, `education.schooling`

**Truth zones:**

- **must_extract**
    - `faith.denomination = "Catholic"`
    - `faith.significantMoment = "Mother Josie attended Mount Marty Catholic school in Yankton"`
- **must_not_write**
    - `personal.dateOfBirth`
    - `education.schooling`

_Scoring note: WO-SCHEMA-02 faith: denomination and family faith history. Tests that faith.denomination extracts cleanly and that mother's school routes to faith.significantMoment (not education.schooling, which belongs to narrator)._

---

### case_038 — midlife / health_and_body

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> Was there a health scare or a recovery that changed how you saw things?

**Narrator replies:**

> I've been pretty healthy my whole life, honestly. I was tough. I was always outside, always working. I don't have any big health stories to tell.

**Expected fields:**

_none_

**extractPriority:** `health.majorCondition`, `health.milestone`

**Forbidden fields:** `health.majorCondition`, `health.milestone`, `health.lifestyleChange`

**Truth zones:**

- **must_not_write**
    - `health.majorCondition`
    - `health.milestone`
    - `health.lifestyleChange`

_Scoring note: WO-SCHEMA-02 health: null case — narrator explicitly says no health events. Tests that extractor produces ZERO health fields. All health fields are forbidden here. The 'tough' and 'always outside' details should not invent a health entry._

---

### case_039 — developmental_foundations / community_belonging

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> Was your family involved in any organizations or community groups?

**Narrator replies:**

> My father Pete worked on the Garrison Dam as a foreman of a finishing crew for cement forms. And the Gustins — my mother's side — Arno Gustin was one of the founders of the College of Mary. Uncle Al Gustin was an agricultural reporter.

**Expected fields:**

- `community.organization` = "Garrison Dam project"
- `community.role` = "Foreman of finishing crew for cement forms"

**extractPriority:** `community.organization`, `community.role`, `community.significantEvent`

**Forbidden fields:** `education.earlyCareer`, `personal.dateOfBirth`

**Truth zones:**

- **must_extract**
    - `community.organization = "Garrison Dam project"`
    - `community.role = "Foreman of finishing crew for cement forms"`
- **must_not_write**
    - `education.earlyCareer`
    - `personal.dateOfBirth`

_Scoring note: WO-SCHEMA-02 community: family civic contributions. Tests community.organization and role extraction from family narrative. Also tests that College of Mary founding routes to significantEvent as family lore rather than education._

---

### case_041 — developmental_foundations / childhood_pets

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> Tell me about your animals growing up — which ones do you still remember?

**Narrator replies:**

> Oh, my horse Grey. I loved that horse more than anything. I was always outside with Grey. And then later we had a dog named Spot — Uncle Johnny got Spot when he rented a farm. Spot was the last dog I had as a kid.

**Expected fields:**

- `pets.name` = "Spot"
- `pets.species` = "dog"

**extractPriority:** `pets.name`, `pets.species`, `pets.notes`

**Forbidden fields:** `hobbies.hobbies`, `personal.dateOfBirth`

**Truth zones:**

- **must_extract**
    - `pets.name = "Spot"`
    - `pets.species = "dog"`
- **must_not_write**
    - `hobbies.hobbies`
    - `personal.dateOfBirth`

_Scoring note: WO-SCHEMA-02 pets: two pets from one answer. Tests repeatable pets grouping — Grey (horse) and Spot (dog) must stay as separate entities. Also tests that pets route to pets.* fields rather than hobbies.hobbies (which is now forbidden for pet data). This is a SCHEMA-02 migration test._

---

### case_046 — developmental_foundations / childhood_pets

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> Were there animals around the house when you were growing up?

**Narrator replies:**

> Oh, we always had cats. Barn cats mostly. And my dad had a horse named Dusty that he used for ranch work.

**Expected fields:**

- `pets.species` = "cat"
- `pets.name` = "Dusty"
- `pets.notes` = "horse, used for ranch work"

**extractPriority:** `pets.name`, `pets.species`, `pets.notes`

**Forbidden fields:** `hobbies.hobbies`

**Truth zones:**

- **must_extract**
    - `pets.species = "cat"`
    - `pets.name = "Dusty"`
    - `pets.notes = "horse, used for ranch work"`
- **must_not_write**
    - `hobbies.hobbies`

_Scoring note: WO-EX-REROUTE-01 pets rerouter: multiple pet species with named animal. Tests compound pet extraction and that horse routes to pets.*, not hobbies.*._

---

### case_049 — developmental_foundations / origin_point

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: True

**Lori asks:**

> Where were you born?

**Narrator replies:**

> I was born in Spokane, Washington, on August 30th, 1939. My dad Pete worked at an aluminum factory there.

**Expected fields:**

- `personal.placeOfBirth` = "Spokane, Washington"
- `personal.dateOfBirth` = "1939-08-30"

**extractPriority:** `personal.placeOfBirth`, `personal.dateOfBirth`

**Forbidden fields:** `residence.place`

**Truth zones:**

- **must_extract**
    - `personal.placeOfBirth = "Spokane, Washington"`
    - `personal.dateOfBirth = "1939-08-30"`
- **must_not_write**
    - `residence.place`

_Scoring note: WO-EX-REROUTE-01 birthplace rerouter: 'I was born in' is unambiguous birth cue. If LLM routes to residence.place, rerouter should fix it. Tests that forbiddenFields residence.place is not produced._

---

### case_056 — later_adulthood / negated_health

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Have you had any significant health challenges?

**Narrator replies:**

> I've been pretty healthy my whole life, knock on wood. Never had any serious surgeries or anything like that.

**Expected fields:**

_none_

**Forbidden fields:** `health.majorCondition`, `health.milestone`, `health.lifestyleChange`

**Truth zones:**

- **must_not_write**
    - `health.majorCondition`
    - `health.milestone`
    - `health.lifestyleChange`

_Scoring note: WO-EX-TWOPASS-01: negated health. Pass 1 should flag 'negated' on both health references. Tests denial detection for hedged language._

---

### case_058 — childhood_origins / birthplace_vs_residence

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Where were you born and where did you grow up?

**Narrator replies:**

> I was born in Fargo but we moved to West Fargo when I was about five. That's where I really grew up.

**Expected fields:**

- `personal.placeOfBirth` = "Fargo"
- `residence.place` = "West Fargo"

**extractPriority:** `personal.placeOfBirth`, `residence.place`

**Truth zones:**

- **must_extract**
    - `personal.placeOfBirth = "Fargo"`
    - `residence.place = "West Fargo"`

_Scoring note: WO-EX-TWOPASS-01: birthplace AND residence in same answer. Tests that two-pass correctly separates 'born in X' from 'moved to Y'. Both should extract, to different fields._

---

### case_061 — middle_adulthood / uncertain_date

questionType: anchor  ·  caseType: contract  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> When and where did you get married?

**Narrator replies:**

> We got married at St. Mary's church. I think it was 1956, maybe 1957. I'm not sure of the exact year anymore.

**Expected fields:**

- `family.marriagePlace` = "St. Mary's"

**extractPriority:** `family.marriageDate`, `family.marriagePlace`

**Truth zones:**

- **must_extract**
    - `family.marriagePlace = "St. Mary's"`

_Scoring note: WO-EX-TWOPASS-01: uncertain date with hedging language. Pass 1 should flag 'uncertain'. Tests that uncertain spans get lower confidence, not dropped._

---

### case_063 — developmental_foundations / childhood_home

questionType: anchor  ·  caseType: mixed_narrative  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> What do you remember about where you grew up?

**Narrator replies:**

> Well, we lived in Dodge first — that's where I started school, first and second grade. I could read big books even then, and the teacher had me read aloud to the class. I sat alone which I thought was punishment at the time, but looking back I think she just didn't know what to do with me. I loved being outside. My sister Verene was the opposite, she hated it. I used to milk the cows and I actually liked doing it. Then we moved to Glen Ulin where I went to Sacred Hearts for third, fourth, and fifth grade. The roads were dirt and in the spring they'd turn to mud something awful.

**Expected fields:**

- `residence.place` = "Dodge, ND"
- `education.schooling` = "Sacred Hearts school in Glen Ulin"

**extractPriority:** `residence.place`, `earlyMemories.firstMemory`

**Truth zones:**

- **must_extract**
    - `residence.place = "Dodge, ND"`
    - `education.schooling = "Sacred Hearts school in Glen Ulin"`
- **may_extract**
    - `siblings.firstName = "Verene"`
    - `earlyMemories.firstMemory = "milking cows, reading aloud to class"`
- **should_ignore**
    - `residence.notes  _(dirt roads and mud — color detail, not a fact to extract)_`
- **must_not_write**
    - `parents.firstName`

_Scoring note: Mixed narrative: childhood memories with residence facts, school facts, sibling mention, and scene-setting detail about roads. Tests whether Lori extracts the residence and school while ignoring atmospheric detail._

---

### case_066 — developmental_foundations / childhood_pets

questionType: anchor  ·  caseType: mixed_narrative  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Did you have any animals or pets when you were growing up?

**Narrator replies:**

> Oh yes. I had a horse named Grey — I loved that horse. I was a real country girl, always outside. My sister Verene wouldn't go near the barn but I was out there every day. We also had Spot, he was our last dog when I was a kid. Uncle Johnny got Spot when he rented a farm. Johnny was the youngest of my dad's siblings — there was Tillie who was the oldest sister, then my dad Peter, then Steven, Joe, August, and Johnny at the end. I hated Uncle August, he was mean to me. But Johnny was always good to us kids.

**Expected fields:**

- `pets.name` = "Grey"
- `pets.species` = "Horse"

**extractPriority:** `pets.name`, `pets.species`

**Truth zones:**

- **must_extract**
    - `pets.name = "Grey"`
    - `pets.species = "Horse"`
- **may_extract**
    - `pets.notes = "childhood horse"`
    - `siblings.firstName = "Verene"`
- **should_ignore**
    - `parents.firstName  _(Peter mentioned as 'my dad' in passing within uncle list)_`
- **must_not_write**
    - `parents.notableLifeEvents`

_Scoring note: Mixed narrative: pet question answered with horse Grey, dog Spot, then tangent into uncle list and childhood feelings. Tests whether Lori extracts the pet data and optionally sibling, while ignoring the uncle enumeration which is parent-sibling data not narrator data._

---

### case_069 — transitional_adolescence / school_experience

questionType: anchor  ·  caseType: mixed_narrative  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Tell me about your school years — what stands out?

**Narrator replies:**

> I went to so many schools. Started in Dodge for first and second grade — I could already read big books, and the teacher had me read aloud to the whole class. Then we moved to Glen Ulin and I went to Sacred Hearts for third, fourth, and fifth grade. Sixth grade was in Strasburg — that's where Lawrence Welk was from, you know. His wife was a nurse at the local hospital. My teacher there was a nun, I called her 'a nut.' She falsely accused me over some note that a classmate had written. And there was this boy Johnny Baumgartner who was the class clown, she made him wear a dunce hat. After that I started college at Bismarck Junior College studying Speech and History. Those credits eventually transferred to UND.

**Expected fields:**

- `education.schooling` = "Dodge for first and second grade; Sacred Hearts in Glen Ulin for third through fifth; Strasburg for sixth grade"
- `education.higherEducation` = "Bismarck Junior College, Speech and History, credits transferred to UND"

**extractPriority:** `education.schooling`

**Truth zones:**

- **must_extract**
    - `education.schooling = "Dodge, Sacred Hearts in Glen Ulin, Strasburg"`
    - `education.higherEducation = "Bismarck Junior College, Speech and History"`
- **may_extract**
    - `residence.place = "Dodge, Glen Ulin, Strasburg"`
- **should_ignore**
    - `education.earlyCareer  _(no career info here despite education topic)_`
- **must_not_write**
    - `laterYears.lifeLessons`

_Scoring note: Mixed narrative: school history with colorful detail (Lawrence Welk, dunce hat, nun teacher). Multiple schools and college. Tests whether Lori captures the full education arc while ignoring anecdotal color._

---

### case_072 — early_adulthood / marriage_children

questionType: anchor  ·  caseType: mixed_narrative  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> How did you and Kent start your family?

**Narrator replies:**

> Kent and I got married October 10, 1959. I was twenty, he was nineteen — so I was the older one! We moved around quite a bit for his construction work. Our first boy Vincent was born in Germany, can you believe that? Then Jason came along, he's the family-oriented one. And Christopher — Chris — he was born December 24, 1962 in Williston, North Dakota. Christmas Eve, same as his dad's birthday. Kent's always said that was the best birthday present he ever got. We raised those three boys through all kinds of moves and adventures. I made sure they got a good education even when we were living in the middle of nowhere.

**Expected fields:**

- `family.marriageDate` = "1959-10-10"
- `family.children.firstName` = "Vincent"

**extractPriority:** `family.marriageDate`, `family.children.firstName`

**Truth zones:**

- **must_extract**
    - `family.marriageDate = "1959-10-10"`
    - `family.children.firstName = "Vincent, Jason, Christopher"`
    - `family.children.dateOfBirth = "1962-12-24"`
- **may_extract**
    - `family.children.placeOfBirth = "Germany, Williston ND"`
- **should_ignore**
    - `family.spouse.firstName  _(Kent already known as spouse)_`
    - `family.spouse.dateOfBirth  _(birthday reference is Kent's, not new data)_`
- **must_not_write**
    - `personal.dateOfBirth`

_Scoring note: Mixed narrative: marriage date and three children with birth details, mixed with anecdotal detail about moves and Kent's birthday. Tests compound child extraction plus marriage date, while not extracting Kent's birthday as new spouse data._

---

### case_075 — developmental_foundations / mother_stories

questionType: anchor  ·  caseType: mixed_narrative  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Tell me about your mother — what kind of person was she?

**Narrator replies:**

> My mother was Josephine — everyone called her Josie. She was a gifted musician. During the silent movie era she played the organ at movie theaters to make money. She had two years of college at Capitol Business College in Bismarck. Her mom had sent her there and she worked as a housekeeper for the owners of the school to help pay for it. She didn't like the accounting part at all. Her mom Anna was fifty years old when she had Josie, which embarrassed her. When Josie was in seventh grade her parents sent her by train by herself to Mount Marty. She went back to Glen Ulin for eighth grade at Sacred Heart, then went to Mount Marty high school for three years in Yankton, South Dakota. She hated boarding school. She told us kids she would never send us. She worked in the kitchen there and learned to cook — she was an expert with the knife and could dice an onion like nobody's business.

**Expected fields:**

- `parents.firstName` = "Josephine"
- `parents.occupation` = "Housewife"

**extractPriority:** `parents.firstName`, `parents.occupation`

**Truth zones:**

- **must_extract**
    - `parents.firstName = "Josephine"`
    - `parents.notableLifeEvents = "played organ at silent movie theaters, attended Capitol Business College, boarding school at Mount Marty"`
- **may_extract**
    - `parents.maidenName = "Schaaf"`
    - `grandparents.firstName = "Anna"`
- **must_not_write**
    - `education.schooling`
    - `education.higherEducation`

_Scoring note: Mixed narrative: rich mother biography with many true facts. The education details are Josie's, not Janice's — tests whether Lori assigns them to parents.notableLifeEvents rather than education.schooling for the narrator. WO-QB-ALT-VALUES-01 (#97): alt_defensible_values added for parents.notableLifeEvents — the primary expected string is a long comma-joined conjunction; the extractor is permitted to emit any ONE of the adjudicated phrasings for a must_extract credit (≥0.5 fuzzy match). Value-axis-only scorer relaxation; primary path is unchanged._

---

### case_078 — early_adulthood / higher_education

questionType: anchor  ·  caseType: mixed_narrative  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Did you go on to any further education after high school?

**Narrator replies:**

> I started at Bismarck Junior College studying Speech and History. I liked it, especially the Speech part. Those credits transferred to UND — that's the University of North Dakota. But then Kent and I got married in '59 and things went a different direction. My mother Josie had gone to Capitol Business College but hated the business side of it, and I think that stuck with me — I wanted to study things I actually cared about, not just what would get me a job. Kent was already in construction by then. We started our family soon after the wedding. Vincent was born in Germany when we were over there for Kent's work.

**Expected fields:**

- `education.higherEducation` = "Bismarck Junior College, Speech and History, credits transferred to UND"

**extractPriority:** `education.higherEducation`

**Truth zones:**

- **must_extract**
    - `education.higherEducation = "Bismarck Junior College, Speech and History, credits transferred to UND"`
- **may_extract**
    - `family.marriageDate = "1959"`
- **should_ignore**
    - `family.children.firstName  _(Vincent mentioned in passing)_`
    - `family.spouse.firstName  _(Kent mentioned in context)_`
    - `parents.notableLifeEvents  _(Josie's college mentioned for comparison, not new extraction)_`

_Scoring note: Mixed narrative: education answer with marriage and family tangent. Mother's education mentioned as contrast. Tests whether Lori extracts Janice's education while not extracting Josie's education details as Janice's._

---

### case_082 — developmental_foundations / childhood_moves

questionType: anchor  ·  caseType: dense_truth  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Did your family move around a lot when you were young?

**Narrator replies:**

> All the time. I was born in Spokane, Washington because my dad Pete was working at an aluminum factory out there. Then we moved back to Dodge, North Dakota — that's where Dad's family was from. I went to first and second grade there. After that we moved to Glen Ulin where I went to Sacred Hearts for third, fourth, and fifth grade. My sister Verene was there too but she was always inside. Then we moved to Strasburg for sixth grade — Lawrence Welk was from there, his wife was a nurse at the hospital. After that there was Bismarck where I started college. And then after Kent and I got married we lived in Germany for a while where Vincent was born, then all over. My dad had worked on the Garrison Dam too — he was a foreman of a finishing crew for the cement forms. So moving was just what our family did.

**Expected fields:**

- `residence.place` = "Spokane, Washington"
- `personal.placeOfBirth` = "Spokane, Washington"

**extractPriority:** `residence.place`, `residence.period`

**Truth zones:**

- **must_extract**
    - `personal.placeOfBirth = "Spokane, Washington"`
    - `residence.place = "Dodge ND, Glen Ulin ND, Strasburg ND, Bismarck ND, Germany"`
- **may_extract**
    - `education.schooling = "first/second grade Dodge, Sacred Hearts Glen Ulin, sixth grade Strasburg"`
    - `parents.occupation = "aluminum factory worker, Garrison Dam foreman"`
    - `parents.firstName = "Peter"`
- **should_ignore**
    - `siblings.firstName  _(Verene mentioned in passing)_`
    - `family.children.firstName  _(Vincent mentioned but as married-life context)_`
    - `family.spouse.firstName  _(Kent mentioned but as context)_`

_Scoring note: Dense truth: chronological residence history with education, parent occupation, and family details woven throughout. Many extractable facts across multiple field families. Tests comprehensive extraction from a natural life-story answer._

---

### case_085 — developmental_foundations / father_story

questionType: anchor  ·  caseType: dense_truth  ·  style: life_history  ·  currentExtractorExpected: False

**Lori asks:**

> Tell me about your father — what do you remember about him?

**Narrator replies:**

> My dad Pete — Peter Zarr — he was born at home in Dodge, North Dakota. Delivered by Mrs. Steve Dodenheffer. He was a hard worker all his life. Had a steam boiler operator license, did carpentry, worked on the Garrison Dam as a foreman of a finishing crew for cement forms. When I was born he was working at an aluminum factory out in Washington state — that's why I was born in Spokane. He lost his birth certificate when the state Capitol of North Dakota burned down, that always bothered him. His siblings — there was a whole bunch of them. Tillie Dodenheffer was the oldest sister, then my dad Peter, then Steven, Joe, August, and Johnny was the youngest. They were all from Dodge. Good people, Germans from Russia stock.

**Expected fields:**

- `parents.firstName` = "Peter"
- `parents.lastName` = "Zarr"
- `parents.occupation` = "Steam boiler operator, carpenter"

**extractPriority:** `parents.firstName`, `parents.occupation`, `parents.notableLifeEvents`

**Truth zones:**

- **must_extract**
    - `parents.firstName = "Peter"`
    - `parents.lastName = "Zarr"`
    - `parents.occupation = "Steam boiler operator, carpenter, Garrison Dam foreman"`
    - `parents.birthPlace = "Dodge, ND"`
    - `parents.notableLifeEvents = "born at home, worked on Garrison Dam, lost birth certificate when Capitol burned"`
- **may_extract**
    - `personal.placeOfBirth = "Spokane, Washington"`
- **must_not_write**
    - `siblings.firstName`
    - `grandparents.firstName`

_Scoring note: Dense truth: detailed father biography with occupation list, birth story, sibling enumeration. Pete's siblings should NOT create sibling entries — they are parent's siblings. Tests parent extraction depth and correct attribution._

---

### case_088 — developmental_foundations / childhood_pets

questionType: followup  ·  caseType: follow_up  ·  style: life_history  ·  currentExtractorExpected: False

**Prior context:**

> Narrator previously mentioned having a horse named Grey and a dog named Spot.

**Lori asks:**

> You mentioned your horse Grey earlier — what was that like?

**Narrator replies:**

> Grey was everything to me. I'd ride out every morning before chores. My sister wouldn't come near the barn but I loved it. That was in Dodge when we lived there. I was a real outdoors girl — milking cows, riding Grey, just being outside. Verene was the exact opposite.

**Expected fields:**

- `pets.notes` = "childhood horse, rode every morning before chores"

**extractPriority:** `pets.notes`

**Truth zones:**

- **must_extract**
    - `pets.notes = "rode every morning before chores in Dodge"`
- **should_ignore**
    - `pets.name  _(Grey already captured — should not overwrite or duplicate)_`
    - `pets.species  _(Horse already captured)_`
    - `siblings.firstName  _(Verene mentioned in passing, already captured)_`
    - `residence.place  _(Dodge already captured as residence)_`

_Scoring note: Follow-up: enriches existing pet entry with notes. Grey, Horse, Verene, and Dodge are all previously captured — this answer should add notes without duplicating existing data. Tests non-overwrite and enrichment behavior. WO-QB-ALT-VALUES-01 (#97): alt_defensible_values added for pets.notes — the primary expected string pins 'in Dodge' which a riding-centric extraction would not include; the adjudicated alts accept any phrasing that captures the core 'rode every morning before chores' idea. Value-axis-only scorer relaxation._

---

### case_091 — early_adulthood / marriage_detail

questionType: followup  ·  caseType: follow_up  ·  style: life_history  ·  currentExtractorExpected: False

**Prior context:**

> Narrator previously stated marriage date October 10, 1959.

**Lori asks:**

> You mentioned marrying Kent in 1959 — do you remember the wedding?

**Narrator replies:**

> We got married on October 10th. I was twenty and Kent was nineteen — I was older! It was a small affair, we didn't have a lot of money. But it was a beautiful fall day. After that we just started our life together. We didn't have much but we had each other.

**Expected fields:**

_none_

**extractPriority:** `family.marriagePlace`

**Truth zones:**

- **may_extract**
    - `family.marriageNotes = "small wedding, beautiful fall day"`
- **should_ignore**
    - `family.marriageDate  _(October 10 already captured — do not re-extract)_`
    - `family.spouse.firstName  _(Kent already captured)_`
- **must_not_write**
    - `personal.dateOfBirth`

_Scoring note: Follow-up: wedding elaboration. No new hard facts beyond optional marriage notes. Tests restraint — marriage date and spouse name are already known._

---

### case_094 — developmental_foundations / sibling_detail

questionType: followup  ·  caseType: follow_up  ·  style: life_history  ·  currentExtractorExpected: False

**Prior context:**

> Narrator previously mentioned siblings Verene Marie (older sister) and James Peter (younger brother).

**Lori asks:**

> Tell me more about your brother James.

**Narrator replies:**

> James Peter Zarr — he was the youngest. He was born on June 29th, which is the same day as Kent's parents' wedding anniversary. Ervin and Leila Horne's anniversary. And get this — James was born in a car on the way to Richardton Hospital! Mom and Dad didn't make it in time.

**Expected fields:**

_none_

**extractPriority:** `siblings.firstName`

**Truth zones:**

- **may_extract**
    - `siblings.uniqueCharacteristics = "born in a car on the way to Richardton Hospital"`
- **should_ignore**
    - `siblings.firstName  _(James already captured)_`
    - `siblings.birthOrder  _(youngest already captured)_`
- **must_not_write**
    - `parents.firstName`
    - `family.marriageDate`

_Scoring note: Follow-up: enriches existing sibling entry with birth story. Kent's parents' anniversary is cross-family detail that should not be extracted. Tests enrichment of existing entry and cross-family attribution._

---

### case_097 — legacy_reflection / regrets

questionType: anchor  ·  caseType: null_clarify  ·  style: thematic  ·  currentExtractorExpected: True

**Lori asks:**

> Looking back, is there anything you wish you'd done differently?

**Narrator replies:**

> I don't know... maybe. But I don't think that's something I want written down. Some things are just for thinking about, not for putting in a book.

**Expected fields:**

_none_

**extractPriority:** `additionalNotes.unfinishedDreams`

**Forbidden fields:** `additionalNotes.unfinishedDreams`, `laterYears.lifeLessons`

**Truth zones:**

- **must_not_write**
    - `additionalNotes.unfinishedDreams`
    - `laterYears.lifeLessons`
    - `hobbies.personalChallenges`

_Scoring note: Null/clarify: narrator explicitly says she doesn't want this recorded. Tests whether Lori respects the narrator's stated wish not to have information written down._

---

### case_100 — midlife / community

questionType: anchor  ·  caseType: null_clarify  ·  style: topical  ·  currentExtractorExpected: True

**Lori asks:**

> Were you involved in any community groups or organizations?

**Narrator replies:**

> Not really, no. I was busy with the boys and keeping house wherever Kent's job took us. I mean, I suppose the church counted, but I wasn't a joiner of things. I was more of a one-on-one person. If a neighbor needed help I was there, but I didn't sign up for committees.

**Expected fields:**

_none_

**extractPriority:** `community.organization`

**Forbidden fields:** `community.organization`, `community.role`

**Truth zones:**

- **should_ignore**
    - `faith.denomination  _(church mentioned but vaguely, not enough for denomination extraction)_`
    - `hobbies.hobbies  _(helping neighbors is character, not a hobby to extract)_`
- **must_not_write**
    - `community.organization`
    - `community.role`

_Scoring note: Null/clarify: explicit non-answer to community question. 'Not really, no' and 'wasn't a joiner' are clear signals to abstain. Tests whether Lori fabricates community involvement from vague church reference._

---
