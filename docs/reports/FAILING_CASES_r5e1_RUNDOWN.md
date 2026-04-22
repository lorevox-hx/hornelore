# LOOP-01 R5.5 — Failed Cases Rundown (r5e1 baseline, 45/104 failing)

**Generated from:** `docs/reports/master_loop01_r5e1.json` joined with `data/qa/question_bank_extraction_cases.json`.

**Baseline:** 59 pass / 45 fail / 104 total — v3=38/62, v2=32/62, mnw=2.

**Per case, this rundown shows:** question (Lori prompt) · response (narrator reply) · life-map stage (era / pass / mode) · failure categories · the specific fields / paths that hurt · what the extractor actually emitted (raw top-6).

## Failure-category histogram

| count | category |
|---:|---|
| 28 | schema_gap |
| 11 | field_path_mismatch |
|  8 | llm_hallucination |
|  4 | noise_leakage |
|  2 | guard_false_positive |

## Era histogram (all 45 fails)

school_years 24 · early_adulthood 10 · midlife 6 · adolescence 3 · early_childhood 1 · later_life 1. All 45 are `pass1` / `open`.

---

## 1. `case_058` — childhood_origins / birthplace_vs_residence

**Life-map:** era=`early_childhood` · pass=`pass1` · mode=`open`  
**Score:** overall=0.5 · v2_pass=False · categories=['field_path_mismatch']

**Q (Lori):** Where were you born and where did you grow up?

**A (Narrator):** I was born in Fargo but we moved to West Fargo when I was about five. That's where I really grew up.

**Expected fields:**
- `personal.placeOfBirth` = `Fargo`
- `residence.place` = `West Fargo`

**Issue detail:**

```
  - residence.place  [missing, score=0.0]  expected='West Fargo'  actual=MISSING
```

**Extractor raw (top 6):** personal.placeOfBirth=Fargo | personal.placeOfBirth=West Fargo | residence.period=about five years old

---

## 2. `case_002` — developmental_foundations / early_caregivers

**Life-map:** era=`school_years` · pass=`pass1` · mode=`open`  
**Score:** overall=0.4 · v2_pass=False · categories=['schema_gap', 'llm_hallucination']

**Q (Lori):** Who were the people you saw every single day at the breakfast table when you were very small?

**A (Narrator):** It was my mom Janice and my dad Kent, and my two older brothers Vincent and Jason. I was the youngest of three boys.

**Expected fields:**
- `parents.firstName` = `Janice`
- `parents.relation` = `mother`
- `siblings.firstName` = `Vincent`
- `siblings.birthOrder` = `older`
- `personal.birthOrder` = `3`

**Forbidden (must_not_write):** `family.spouse.firstName`, `education.schooling`

**Issue detail:**

```
  - parents.relation  [missing, score=0.0]  expected='mother'  actual=MISSING
  - siblings.birthOrder  [wrong, score=0.0]  expected='older'  actual='youngest'
  - personal.birthOrder  [missing, score=0.0]  expected='3'  actual=MISSING
```

**Extractor raw (top 6):** parents.firstName=Janice | parents.firstName=Kent | siblings.firstName=Vincent | siblings.firstName=Jason | siblings.birthOrder=youngest

---

## 3. `case_014` — developmental_foundations / early_caregivers

**Life-map:** era=`school_years` · pass=`pass1` · mode=`open`  
**Score:** overall=0.333 · v2_pass=False · categories=['llm_hallucination', 'field_path_mismatch']

**Q (Lori):** Where did you fall in the sibling lineup — oldest, youngest, somewhere in between?

**A (Narrator):** I was the middle child. My older sister Sharon was born in 1937, I came along in '39, and then my little sister Linda in '42.

**Expected fields:**
- `personal.birthOrder` = `2`
- `siblings.firstName` = `Linda`
- `siblings.birthOrder` = `younger`

**Forbidden (must_not_write):** `family.spouse.firstName`, `education.schooling`

**Issue detail:**

```
  - personal.birthOrder  [missing, score=0.0]  expected='2'  actual=MISSING
  - siblings.birthOrder  [wrong, score=0.0]  expected='younger'  actual='first'
```

**Extractor raw (top 6):** siblings.firstName=Sharon | siblings.uniqueCharacteristics=1937 | siblings.birthOrder=first | siblings.uniqueCharacteristics=1939 | siblings.firstName=Linda | siblings.uniqueCharacteristics=1942

---

## 4. `case_024` — developmental_foundations / early_caregivers

**Life-map:** era=`school_years` · pass=`pass1` · mode=`open`  
**Score:** overall=0.333 · v2_pass=False · categories=['schema_gap', 'llm_hallucination']

**Q (Lori):** Where did you fall in the sibling lineup?

**A (Narrator):** I was the middle child. My older sister Verene Marie — she married a Schnieder — she was the oldest. Then me. Then my little brother James Peter, who we called Jim. He was born in a car on the way to Richardton Hospital, can you believe that?

**Expected fields:**
- `personal.birthOrder` = `2`
- `siblings.firstName` = `James`
- `siblings.birthOrder` = `younger`

**Forbidden (must_not_write):** `family.spouse.firstName`, `education.higherEducation`

**Issue detail:**

```
  - personal.birthOrder  [missing, score=0.0]  expected='2'  actual=MISSING
  - siblings.firstName  [partial, score=0.8]  expected='James'  actual='James Peter'
  - siblings.birthOrder  [wrong, score=0.0]  expected='younger'  actual='third'
```

**Extractor raw (top 6):** siblings.firstName=Verene Marie | siblings.firstName=James Peter | siblings.birthOrder=third | siblings.birthOrder=second | siblings.birthOrder=first | siblings.uniqueCharacteristics=born in a car on the way to Richardton Hospital

---

## 5. `case_025` — developmental_foundations / childhood_pets

**Life-map:** era=`school_years` · pass=`pass1` · mode=`open`  
**Score:** overall=0.0 · v2_pass=False · categories=['field_path_mismatch']

**Q (Lori):** Was there an animal in your childhood that felt most like yours?

**A (Narrator):** Oh, my horse Grey. I loved that horse. I liked to be outside — my sister Verene hated it, but I was always out with Grey. And we had a dog named Spot, he was the last dog I had as a kid. Uncle Johnny got Spot when he rented a farm.

**Expected fields:**
- `pets.name` = `Grey`
- `pets.species` = `horse`

**Forbidden (must_not_write):** `family.marriageDate`, `education.higherEducation`

**Issue detail:**

```
  - pets.name  [missing, score=0.0]  expected='Grey'  actual=MISSING
  - pets.species  [missing, score=0.0]  expected='horse'  actual=MISSING
```

**Extractor raw (top 6):** siblings.relation=Sister | siblings.firstName=Verene | hobbies.hobbies=Oh, my horse Grey. I loved that horse. I liked to be outside — my sis…

---

## 6. `case_028` — developmental_foundations / family_rituals_and_holidays

**Life-map:** era=`school_years` · pass=`pass1` · mode=`open`  
**Score:** overall=0.0 · v2_pass=False · categories=['schema_gap']

**Q (Lori):** Was there a food, a song, or a ritual in your home that only made sense once you knew where your family came from?

**A (Narrator):** We were Germans from Russia. Both sides — the Zarrs and the Schaafs. My grandmother Josie's family, the Schaafs, came from Ukraine. My grandfather Mathias hated the Russians. That whole culture came through in the food and the way things were done.

**Expected fields:**
- `earlyMemories.significantEvent` = `Germans from Russia`

**Forbidden (must_not_write):** `personal.dateOfBirth`, `education.schooling`, `family.marriageDate`

**Issue detail:**

```
  - earlyMemories.significantEvent  [missing, score=0.0]  expected='Germans from Russia'  actual=MISSING
```

**Extractor raw (top 6):** parents.firstName=Mathias | parents.lastName=Schaaf/Zarr | parents.notes=hated Russians, came from Ukraine | grandparents.side=maternal | grandparents.firstName=Josie | grandparents.lastName=Schaaf | …(+2 more)

---

## 7. `case_033` — developmental_foundations / family_stories_and_lore

**Life-map:** era=`school_years` · pass=`pass1` · mode=`open`  
**Score:** overall=0.0 · v2_pass=False · categories=['schema_gap', 'field_path_mismatch']

**Q (Lori):** Did anyone in your family serve in the military?

**A (Narrator):** My great-grandfather John Michael Shong served in the Civil War. Company G of the 28th Infantry, from February 1865 to January 1866. He was stationed in Kansas and Missouri.

**Expected fields:**
- `military.branch` = `Army`
- `military.yearsOfService` = `1865-1866`
- `military.deploymentLocation` = `Kansas and Missouri`
- `military.significantEvent` = `Civil War service, Company G, 28th Infantry`

**Forbidden (must_not_write):** `personal.dateOfBirth`, `education.earlyCareer`

**Issue detail:**

```
  - military.branch  [missing, score=0.0]  expected='Army'  actual=MISSING
  - military.yearsOfService  [missing, score=0.0]  expected='1865-1866'  actual=MISSING
  - military.deploymentLocation  [missing, score=0.0]  expected='Kansas and Missouri'  actual=MISSING
  - military.significantEvent  [missing, score=0.0]  expected='Civil War service, Company G, 28th Infantry'  actual=MISSING
```

**Extractor raw (top 6):** greatGrandparents.firstName=John Michael | greatGrandparents.lastName=Shong | greatGrandparents.militaryBranch=Union | greatGrandparents.militaryUnit=Company G, 28th Infantry | greatGrandparents.militaryEvent=Civil War service from February 1865 to January 1866

---

## 8. `case_035` — developmental_foundations / family_rituals_and_holidays

**Life-map:** era=`school_years` · pass=`pass1` · mode=`open`  
**Score:** overall=0.3 · v2_pass=False · categories=['guard_false_positive', 'field_path_mismatch']

**Q (Lori):** What role did church or faith play in your family growing up?

**A (Narrator):** We were Catholic. My sister Verene's confirmation name was Gertrude. My mother Josie went to Mount Marty in Yankton for high school — that was a Catholic school run by nuns. The faith was a big part of everything.

**Expected fields:**
- `faith.denomination` = `Catholic`
- `faith.significantMoment` = `Mother Josie attended Mount Marty Catholic school in Yankton`

**Forbidden (must_not_write):** `personal.dateOfBirth`, `education.schooling`

**Issue detail:**

```
  - faith.significantMoment  [missing, score=0.0]  expected='Mother Josie attended Mount Marty Catholic school in Yankton'  actual=MISSING
  - FORBIDDEN writes: ['education.schooling']
  - must_not_write VIOLATED: ['education.schooling']
```

**Extractor raw (top 6):** faith.denomination=Catholic | education.schooling=Mount Marty in Yankton for high school | family.children.relation=sister | family.children.firstName=Verene | parents.relation=mother | parents.firstName=Josie

---

## 9. `case_039` — developmental_foundations / community_belonging

**Life-map:** era=`school_years` · pass=`pass1` · mode=`open`  
**Score:** overall=0.0 · v2_pass=False · categories=['schema_gap', 'field_path_mismatch']

**Q (Lori):** Was your family involved in any organizations or community groups?

**A (Narrator):** My father Pete worked on the Garrison Dam as a foreman of a finishing crew for cement forms. And the Gustins — my mother's side — Arno Gustin was one of the founders of the College of Mary. Uncle Al Gustin was an agricultural reporter.

**Expected fields:**
- `community.organization` = `Garrison Dam project`
- `community.role` = `Foreman of finishing crew for cement forms`

**Forbidden (must_not_write):** `education.earlyCareer`, `personal.dateOfBirth`

**Issue detail:**

```
  - community.organization  [missing, score=0.0]  expected='Garrison Dam project'  actual=MISSING
  - community.role  [missing, score=0.0]  expected='Foreman of finishing crew for cement forms'  actual=MISSING
```

**Extractor raw (top 6):** parents.firstName=Pete | parents.occupation=foreman of a finishing crew for cement forms | parents.relation=father | parents.notableLifeEvents=Gustins

---

## 10. `case_042` — developmental_foundations / childhood_pets

**Life-map:** era=`school_years` · pass=`pass1` · mode=`open`  
**Score:** overall=0.5 · v2_pass=False · categories=['llm_hallucination']

**Q (Lori):** What was the name of the family pet that felt most like yours?

**A (Narrator):** We had a Golden Retriever named Ivan. He was the family dog when I was growing up. Born around 1964 I think.

**Expected fields:**
- `pets.name` = `Ivan`
- `pets.species` = `Golden Retriever`

**Forbidden (must_not_write):** `hobbies.hobbies`, `family.children.firstName`

**Issue detail:**

```
  - pets.species  [wrong, score=0.0]  expected='Golden Retriever'  actual='dog'
```

**Extractor raw (top 6):** pets.name=Ivan | pets.species=dog | pets.notes=family dog when narrator was growing up; born around 1964

---

## 11. `case_045` — developmental_foundations / childhood_pets

**Life-map:** era=`school_years` · pass=`pass1` · mode=`open`  
**Score:** overall=0.0 · v2_pass=False · categories=['schema_gap']

**Q (Lori):** Did you have any pets growing up?

**A (Narrator):** We had a big old yellow lab named Buster. He followed us everywhere. Best dog I ever had.

**Expected fields:**
- `pets.name` = `Buster`
- `pets.species` = `dog`

**Forbidden (must_not_write):** `hobbies.hobbies`

**Issue detail:**

```
  - pets.name  [missing, score=0.0]  expected='Buster'  actual=MISSING
  - pets.species  [missing, score=0.0]  expected='dog'  actual=MISSING
```

**Extractor raw (top 6):** (none)

---

## 12. `case_046` — developmental_foundations / childhood_pets

**Life-map:** era=`school_years` · pass=`pass1` · mode=`open`  
**Score:** overall=0.0 · v2_pass=False · categories=['schema_gap']

**Q (Lori):** Were there animals around the house when you were growing up?

**A (Narrator):** Oh, we always had cats. Barn cats mostly. And my dad had a horse named Dusty that he used for ranch work.

**Expected fields:**
- `pets.species` = `cat`
- `pets.name` = `Dusty`
- `pets.notes` = `horse, used for ranch work`

**Forbidden (must_not_write):** `hobbies.hobbies`

**Issue detail:**

```
  - pets.species  [missing, score=0.0]  expected='cat'  actual=MISSING
  - pets.name  [missing, score=0.0]  expected='Dusty'  actual=MISSING
  - pets.notes  [missing, score=0.0]  expected='horse, used for ranch work'  actual=MISSING
```

**Extractor raw (top 6):** (none)

---

## 13. `case_047` — developmental_foundations / sibling_dynamics

**Life-map:** era=`school_years` · pass=`pass1` · mode=`open`  
**Score:** overall=0.667 · v2_pass=False · categories=['schema_gap']

**Q (Lori):** Tell me about your brothers and sisters.

**A (Narrator):** I had two older brothers — Vincent and Jason. Vincent was the oldest, then Jason, then me. We were all pretty close growing up.

**Expected fields:**
- `siblings.firstName` = `Vincent`
- `siblings.relation` = `brother`
- `siblings.birthOrder` = `oldest`

**Forbidden (must_not_write):** `family.children.firstName`, `family.children.relation`

**Issue detail:**

```
  - siblings.firstName  [partial, score=0.8]  expected='Vincent'  actual='Vincent, Jason'
  - siblings.relation  [missing, score=0.0]  expected='brother'  actual=MISSING
  - siblings.birthOrder  [partial, score=0.8]  expected='oldest'  actual='oldest, second, third'
```

**Extractor raw (top 6):** siblings.firstName=Vincent, Jason | siblings.birthOrder=oldest, second, third | siblings.uniqueCharacteristics=pretty close growing up

---

## 14. `case_049` — developmental_foundations / origin_point

**Life-map:** era=`school_years` · pass=`pass1` · mode=`open`  
**Score:** overall=0.5 · v2_pass=False · categories=['schema_gap']

**Q (Lori):** Where were you born?

**A (Narrator):** I was born in Spokane, Washington, on August 30th, 1939. My dad Pete worked at an aluminum factory there.

**Expected fields:**
- `personal.placeOfBirth` = `Spokane, Washington`
- `personal.dateOfBirth` = `1939-08-30`

**Forbidden (must_not_write):** `residence.place`

**Issue detail:**

```
  - personal.dateOfBirth  [missing, score=0.0]  expected='1939-08-30'  actual=MISSING
```

**Extractor raw (top 6):** personal.placeOfBirth=Spokane, Washington | parents.firstName=Pete | parents.occupation=aluminum factory worker

---

## 15. `case_065` — developmental_foundations / family_origins

**Life-map:** era=`school_years` · pass=`pass1` · mode=`open`  
**Score:** overall=0.0 · v2_pass=False · categories=['schema_gap']

**Q (Lori):** What do you know about your family's heritage — where your grandparents came from?

**A (Narrator):** On my dad's side, it goes way back. His grandmother was Elizabeth Shong — everybody called her Lizzie. She was the youngest of eight kids. Her father John Michael Shong was born near Nancy in Lorraine, France, came to America around 1848. He served in the Civil War, Company G of the 28th Infantry. Owned 200 acres east of Fall Creek, Wisconsin. Her mother Christine Bolley was from Hanover, Germany, came over in 1850.…

**Expected fields:**
- `grandparents.firstName` = `Elizabeth`
- `grandparents.ancestry` = `French (Alsace-Lorraine), German`

**Issue detail:**

```
  - grandparents.firstName  [missing, score=0.0]  expected='Elizabeth'  actual=MISSING
  - grandparents.ancestry  [missing, score=0.0]  expected='French (Alsace-Lorraine), German'  actual=MISSING
```

**Extractor raw (top 6):** (none)

---

## 16. `case_066` — developmental_foundations / childhood_pets

**Life-map:** era=`school_years` · pass=`pass1` · mode=`open`  
**Score:** overall=0.0 · v2_pass=False · categories=['schema_gap', 'noise_leakage']

**Q (Lori):** Did you have any animals or pets when you were growing up?

**A (Narrator):** Oh yes. I had a horse named Grey — I loved that horse. I was a real country girl, always outside. My sister Verene wouldn't go near the barn but I was out there every day. We also had Spot, he was our last dog when I was a kid. Uncle Johnny got Spot when he rented a farm. Johnny was the youngest of my dad's siblings — there was Tillie who was the oldest sister, then my dad Peter, then Steven, Joe, August, and Johnny…

**Expected fields:**
- `pets.name` = `Grey`
- `pets.species` = `Horse`

**Issue detail:**

```
  - pets.name  [missing, score=0.0]  expected='Grey'  actual=MISSING
  - pets.species  [missing, score=0.0]  expected='Horse'  actual=MISSING
```

**Extractor raw (top 6):** siblings.relation=Sister | siblings.firstName=Verene | parents.relation=Father | parents.firstName=Peter

---

## 17. `case_068` — developmental_foundations / family_loss

**Life-map:** era=`school_years` · pass=`pass1` · mode=`open`  
**Score:** overall=0.525 · v2_pass=True · categories=[]

**Q (Lori):** Were there any big losses in your family when you were growing up?

**A (Narrator):** My dad Ervin — he lost his own father George when he was only four years old. That was 1914. And then my grandmother Elizabeth, she remarried a man named William Mc Raith in 1916, but he died too, just two years later in 1918. So she was widowed twice by the time she was forty-one. She had a daughter Alice from that second marriage. Alice never married. My dad grew up in the Ross, North Dakota area. He married my mo…

**Expected fields:**
- `parents.notableLifeEvents` = `Father Ervin died December 23, 1967`

**Issue detail:**

```
  - parents.notableLifeEvents  [partial, score=0.75]  expected='Father Ervin died December 23, 1967'  actual="My dad Ervin — he lost his own father George when he was only four years old. That was 1914. And then my grandmother Elizabeth, she remarried a man named William Mc Raith in 1916, but he died too, just two years later in 1918. So she was widowed twice by the time she was forty-one. She had a daughter Alice from that second marriage. Alice never married. My dad grew up in the Ross, North Dakota area. He married my mom Leila Myrtle Carkuff and they had us three kids — Sharon first in '37, me in '39, and Linda in '42. Then Dad died December 23, 1967. I was twenty-eight. The day before Christmas Eve, which is my birthday. That was hard."
```

**Extractor raw (top 6):** parents.relation=Mother | parents.firstName=Leila | parents.lastName=Myrtle Carkuff | parents.notableLifeEvents=My dad Ervin — he lost his own father George when he was only four ye…

---

## 18. `case_077` — developmental_foundations / siblings_childhood

**Life-map:** era=`school_years` · pass=`pass1` · mode=`open`  
**Score:** overall=0.0 · v2_pass=False · categories=['schema_gap']

**Q (Lori):** Did you have brothers or sisters? What were they like?

**A (Narrator):** I had two sisters. Sharon was the oldest, born April 8, 1937. She married Ed Woodmansee. And then Linda was the youngest, born July 27, 1942. I was in the middle — the only boy. We grew up in North Dakota, kids of Ervin and Leila Horne. After Dad died in '67 we all kind of had to pull together. Mom Leila lived until 1985, she passed December 1st that year. We stayed close considering how much everybody moved around.

**Expected fields:**
- `siblings.firstName` = `Sharon`
- `siblings.relation` = `Sister`

**Issue detail:**

```
  - siblings.firstName  [missing, score=0.0]  expected='Sharon'  actual=MISSING
  - siblings.relation  [missing, score=0.0]  expected='Sister'  actual=MISSING
```

**Extractor raw (top 6):** (none)

---

## 19. `case_079` — developmental_foundations / siblings

**Life-map:** era=`school_years` · pass=`pass1` · mode=`open`  
**Score:** overall=0.567 · v2_pass=True · categories=[]

**Q (Lori):** Tell me about your brothers.

**A (Narrator):** I've got two older brothers. Vince — Vincent Edward — he's the oldest. He was born in Germany when Mom and Dad were living over there for Dad's construction work. Then Jason, Jason Richard Horne, he's the middle one. Family-oriented guy. I'm the youngest, born in Williston. We all grew up together moving around with Dad's construction jobs. Mom kept us grounded through all those moves.

**Expected fields:**
- `siblings.firstName` = `Vincent`

**Issue detail:**

```
  - siblings.firstName  [partial, score=0.8]  expected='Vincent'  actual='Vince'
```

**Extractor raw (top 6):** personal.birthOrder=youngest | siblings.firstName=Vince | siblings.firstName=Jason | siblings.firstName=Self | siblings.birthOrder=oldest | siblings.birthOrder=middle | …(+3 more)

---

## 20. `case_080` — developmental_foundations / family_history

**Life-map:** era=`school_years` · pass=`pass1` · mode=`open`  
**Score:** overall=0.0 · v2_pass=False · categories=['schema_gap']

**Q (Lori):** What do you know about your grandparents on your father's side?

**A (Narrator):** Well my dad Ervin's parents were George Horne and Elizabeth Shong. George arrived in Ross, North Dakota in 1902. He walked north from Ross looking for good land, filed on a claim, and got the title June 16, 1904. He'd married Elizabeth — everybody called her Lizzie — on December 29, 1903 in Fall Creek, Wisconsin. They had six children: Margaret in 1904, then Phyllis in 1907 but she died as a baby, Ervin — my dad — i…

**Expected fields:**
- `grandparents.firstName` = `George`
- `grandparents.memorableStory` = `arrived in Ross ND 1902, walked north to find land, died 1914`

**Issue detail:**

```
  - grandparents.firstName  [missing, score=0.0]  expected='George'  actual=MISSING
  - grandparents.memorableStory  [missing, score=0.0]  expected='arrived in Ross ND 1902, walked north to find land, died 1914'  actual=MISSING
```

**Extractor raw (top 6):** (none)

---

## 21. `case_081` — developmental_foundations / great_grandparents

**Life-map:** era=`school_years` · pass=`pass1` · mode=`open`  
**Score:** overall=0.0 · v2_pass=False · categories=['schema_gap']

**Q (Lori):** Do you know anything about the generations before your grandparents?

**A (Narrator):** Oh yeah, I've done a lot of research on this. My great-grandmother Elizabeth's father was John Michael Shong — born October 11, 1829 near Nancy in Lorraine, France. He came to America around 1848 at about nineteen. His father's name was thought to be Nicholas, a railroad worker. John Michael had two sisters Mary and Margaret and a brother Peter, who all stayed in France. The name was originally Schong but the C got…

**Expected fields:**
- `grandparents.ancestry` = `French (Alsace-Lorraine), German`

**Issue detail:**

```
  - grandparents.ancestry  [missing, score=0.0]  expected='French (Alsace-Lorraine), German'  actual=MISSING
```

**Extractor raw (top 6):** (none)

---

## 22. `case_082` — developmental_foundations / childhood_moves

**Life-map:** era=`school_years` · pass=`pass1` · mode=`open`  
**Score:** overall=0.467 · v2_pass=False · categories=['noise_leakage', 'field_path_mismatch']

**Q (Lori):** Did your family move around a lot when you were young?

**A (Narrator):** All the time. I was born in Spokane, Washington because my dad Pete was working at an aluminum factory out there. Then we moved back to Dodge, North Dakota — that's where Dad's family was from. I went to first and second grade there. After that we moved to Glen Ulin where I went to Sacred Hearts for third, fourth, and fifth grade. My sister Verene was there too but she was always inside. Then we moved to Strasburg f…

**Expected fields:**
- `residence.place` = `Spokane, Washington`
- `personal.placeOfBirth` = `Spokane, Washington`

**Issue detail:**

```
  - residence.place  [partial, score=0.8]  expected='Spokane, Washington'  actual="All the time. I was born in Spokane, Washington because my dad Pete was working at an aluminum factory out there. Then we moved back to Dodge, North Dakota — that's where Dad's family was from. I went to first and second grade there. After that we moved to Glen Ulin where I went to Sacred Hearts for third, fourth, and fifth grade. My sister Verene was there too but she was always inside. Then we moved to Strasburg for sixth grade — Lawrence Welk was from there, his wife was a nurse at the hospital. After that there was Bismarck where I started college. And then after Kent and I got married we lived in Germany for a while where Vincent was born, then all over. My dad had worked on the Garrison Dam too — he was a foreman of a finishing crew for the cement forms. So moving was just what our family did."
  - personal.placeOfBirth  [missing, score=0.0]  expected='Spokane, Washington'  actual=MISSING
```

**Extractor raw (top 6):** siblings.relation=Sister | siblings.firstName=Verene | parents.relation=Father | parents.firstName=Pete | parents.occupation=working at an aluminum factory out there | residence.place=All the time. I was born in Spokane, Washington because my dad Pete w…

---

## 23. `case_083` — developmental_foundations / grandmother_story

**Life-map:** era=`school_years` · pass=`pass1` · mode=`open`  
**Score:** overall=0.5 · v2_pass=True · categories=[]

**Q (Lori):** You mentioned your grandmother Elizabeth — what else do you know about her family?

**A (Narrator):** Lizzie Shong was the youngest of eight children. Her dad John Michael and mom Christine had: Charlie, born 1864, married Tillie Welke, ran a hotel in Penn, North Dakota. Sarah, 1866, married Gustav Glenz. Little Maggie, 1868, died in infancy. Christie, 1869, married Henry Graichen, worked as a cook across the Midwest. Nicholas, 1871, married Adone Voechting. Henry — they called him Hank — 1873, married Lola Archer.…

**Expected fields:**
- `grandparents.memorableStory` = `youngest of eight children of John Michael Shong and Christine Bolley`

**Issue detail:**

```
  - grandparents.memorableStory  [partial, score=0.74]  expected='youngest of eight children of John Michael Shong and Christine Bolley'  actual="Lizzie Shong was the youngest of eight children. Her dad John Michael and mom Christine had: Charlie, born 1864, married Tillie Welke, ran a hotel in Penn, North Dakota. Sarah, 1866, married Gustav Glenz. Little Maggie, 1868, died in infancy. Christie, 1869, married Henry Graichen, worked as a cook across the Midwest. Nicholas, 1871, married Adone Voechting. Henry — they called him Hank — 1873, married Lola Archer. Cora, 1875, also died in infancy. And then Lizzie, the youngest, 1877. Around the turn of the century she went to Penn to visit her brother Charlie and find work as a seamstress. That's where she met my grandfather George. The Shong name was originally Schong — they dropped the C when they came to America. Might have even been Le Shong once."
```

**Extractor raw (top 6):** grandparents.memorableStory=Lizzie Shong was the youngest of eight children. Her dad John Michael…

---

## 24. `case_085` — developmental_foundations / father_story

**Life-map:** era=`school_years` · pass=`pass1` · mode=`open`  
**Score:** overall=0.2 · v2_pass=False · categories=['schema_gap']

**Q (Lori):** Tell me about your father — what do you remember about him?

**A (Narrator):** My dad Pete — Peter Zarr — he was born at home in Dodge, North Dakota. Delivered by Mrs. Steve Dodenheffer. He was a hard worker all his life. Had a steam boiler operator license, did carpentry, worked on the Garrison Dam as a foreman of a finishing crew for cement forms. When I was born he was working at an aluminum factory out in Washington state — that's why I was born in Spokane. He lost his birth certificate wh…

**Expected fields:**
- `parents.firstName` = `Peter`
- `parents.lastName` = `Zarr`
- `parents.occupation` = `Steam boiler operator, carpenter`

**Issue detail:**

```
  - parents.lastName  [missing, score=0.0]  expected='Zarr'  actual=MISSING
  - parents.occupation  [missing, score=0.0]  expected='Steam boiler operator, carpenter'  actual=MISSING
```

**Extractor raw (top 6):** parents.relation=Father | parents.firstName=Peter

---

## 25. `case_087` — developmental_foundations / shong_family

**Life-map:** era=`school_years` · pass=`pass1` · mode=`open`  
**Score:** overall=0.5 · v2_pass=False · categories=['schema_gap']

**Q (Lori):** You've mentioned the Shong family — can you tell me more about that side?

**A (Narrator):** The Shongs go back to Lorraine, France. John Michael Shong was born October 11, 1829 near Nancy. He came to America around 1848. His father was supposedly Nicholas, a railroad worker. John Michael had two sisters — Mary and Margaret — and a brother Peter who all stayed in France. He settled in Fall Creek, Wisconsin around 1859. Served in the Civil War with Company G of the 28th Infantry. By 1871 he had 200 acres. He…

**Expected fields:**
- `grandparents.ancestry` = `French (Alsace-Lorraine)`

**Issue detail:**

```
  - grandparents.ancestry  [missing, score=0.0]  expected='French (Alsace-Lorraine)'  actual=MISSING
```

**Extractor raw (top 6):** grandparents.memorableStory=The Shongs go back to Lorraine, France. John Michael Shong was born O…

---

## 26. `case_020` — transitional_adolescence / civic_entry_age_18

**Life-map:** era=`adolescence` · pass=`pass1` · mode=`open`  
**Score:** overall=0.0 · v2_pass=False · categories=['field_path_mismatch']

**Q (Lori):** When you turned eighteen, what was the first thing that made adulthood feel official?

**A (Narrator):** I don't really remember anything special about turning eighteen. I was already working construction by then.

**Expected fields:**
- `education.earlyCareer` = `Was already working construction by age eighteen`

**Forbidden (must_not_write):** `personal.dateOfBirth`, `laterYears.retirement`

**Issue detail:**

```
  - education.earlyCareer  [missing, score=0.0]  expected='Was already working construction by age eighteen'  actual=MISSING
```

**Extractor raw (top 6):** laterYears.significantEvent=turning eighteen | laterYears.significantEvent=already working construction

---

## 27. `case_059` — transitional_adolescence / career_progression_vs_early

**Life-map:** era=`adolescence` · pass=`pass1` · mode=`open`  
**Score:** overall=0.5 · v2_pass=False · categories=['field_path_mismatch']

**Q (Lori):** Tell me about the work you've done over your life.

**A (Narrator):** I started out as a welder's helper right out of school. Then I got on at the plant and worked my way up to foreman. I was there for thirty-two years until I retired.

**Expected fields:**
- `education.earlyCareer` = `welder's helper`
- `education.careerProgression` = `foreman`

**Issue detail:**

```
  - education.earlyCareer  [partial, score=0.8]  expected="welder's helper"  actual="I started out as a welder's helper right out of school. Then I got on at the plant and worked my way up to foreman. I was there for thirty-two years until I retired."
  - education.careerProgression  [missing, score=0.0]  expected='foreman'  actual=MISSING
```

**Extractor raw (top 6):** education.earlyCareer=I started out as a welder's helper right out of school. Then I got on…

---

## 28. `case_069` — transitional_adolescence / school_experience

**Life-map:** era=`adolescence` · pass=`pass1` · mode=`open`  
**Score:** overall=0.0 · v2_pass=False · categories=['schema_gap']

**Q (Lori):** Tell me about your school years — what stands out?

**A (Narrator):** I went to so many schools. Started in Dodge for first and second grade — I could already read big books, and the teacher had me read aloud to the whole class. Then we moved to Glen Ulin and I went to Sacred Hearts for third, fourth, and fifth grade. Sixth grade was in Strasburg — that's where Lawrence Welk was from, you know. His wife was a nurse at the local hospital. My teacher there was a nun, I called her 'a nut…

**Expected fields:**
- `education.schooling` = `Dodge for first and second grade; Sacred Hearts in Glen Ulin for third through fifth; Strasburg for sixth grade`
- `education.higherEducation` = `Bismarck Junior College, Speech and History, credits transferred to UND`

**Issue detail:**

```
  - education.schooling  [missing, score=0.0]  expected='Dodge for first and second grade; Sacred Hearts in Glen Ulin for third through fifth; Strasburg for sixth grade'  actual=MISSING
  - education.higherEducation  [missing, score=0.0]  expected='Bismarck Junior College, Speech and History, credits transferred to UND'  actual=MISSING
```

**Extractor raw (top 6):** personal.fullName=her

---

## 29. `case_005` — early_adulthood / parenthood

**Life-map:** era=`early_adulthood` · pass=`pass1` · mode=`open`  
**Score:** overall=0.0 · v2_pass=False · categories=['schema_gap']

**Q (Lori):** Tell me the names of each of your children.

**A (Narrator):** I have four kids. My oldest is Vincent Edward, then Gretchen Jo who was born October 4th, 1991 in Austin, Texas. Then Amelia Fay, born August 5th, 1994, and my youngest is Cole Harber, born April 10th, 2002.

**Expected fields:**
- `family.children.firstName` = `Gretchen`
- `family.children.dateOfBirth` = `1991-10-04`
- `family.children.placeOfBirth` = `Austin, Texas`

**Forbidden (must_not_write):** `family.spouse.firstName`, `parents.firstName`

**Issue detail:**

```
  - family.children.firstName  [missing, score=0.0]  expected='Gretchen'  actual=MISSING
  - family.children.dateOfBirth  [missing, score=0.0]  expected='1991-10-04'  actual=MISSING
  - family.children.placeOfBirth  [missing, score=0.0]  expected='Austin, Texas'  actual=MISSING
```

**Extractor raw (top 6):** (none)

---

## 30. `case_023` — early_adulthood / relationship_anchors

**Life-map:** era=`early_adulthood` · pass=`pass1` · mode=`open`  
**Score:** overall=0.0 · v2_pass=False · categories=['schema_gap']

**Q (Lori):** What year did you get married?

**A (Narrator):** I married Kent Horne on October 10th, 1959. I was twenty and he was nineteen.

**Expected fields:**
- `family.spouse.firstName` = `Kent`
- `family.spouse.lastName` = `Horne`
- `family.marriageDate` = `1959-10-10`

**Forbidden (must_not_write):** `personal.dateOfBirth`, `education.schooling`

**Issue detail:**

```
  - family.spouse.firstName  [missing, score=0.0]  expected='Kent'  actual=MISSING
  - family.spouse.lastName  [missing, score=0.0]  expected='Horne'  actual=MISSING
  - family.marriageDate  [missing, score=0.0]  expected='1959-10-10'  actual=MISSING
```

**Extractor raw (top 6):** (none)

---

## 31. `case_027` — early_adulthood / post_education

**Life-map:** era=`early_adulthood` · pass=`pass1` · mode=`open`  
**Score:** overall=0.0 · v2_pass=False · categories=['llm_hallucination']

**Q (Lori):** Did you go to college after high school?

**A (Narrator):** Yes, I started at Bismarck Junior College. I studied Speech and History. Those credits transferred to UND.

**Expected fields:**
- `education.higherEducation` = `Bismarck Junior College, Speech and History; credits transferred to UND`

**Forbidden (must_not_write):** `education.earlyCareer`, `family.marriageDate`

**Issue detail:**

```
  - education.higherEducation  [wrong, score=0.0]  expected='Bismarck Junior College, Speech and History; credits transferred to UND'  actual='Bismarck Junior College, Speech, History'
```

**Extractor raw (top 6):** education.higherEducation=Bismarck Junior College, Speech, History | education.higherEducation=credits transferred to University of North Dakota (UND)

---

## 32. `case_044` — early_adulthood / first_home

**Life-map:** era=`early_adulthood` · pass=`pass1` · mode=`open`  
**Score:** overall=0.333 · v2_pass=False · categories=['schema_gap', 'field_path_mismatch']

**Q (Lori):** Where was the first place you and Janice lived after getting married?

**A (Narrator):** We went to Germany. That's where our first boy Vincent was born. I was working construction over there. We came back to North Dakota after that.

**Expected fields:**
- `residence.place` = `Germany`
- `travel.destination` = `Germany`
- `travel.purpose` = `Work — construction`

**Forbidden (must_not_write):** `personal.dateOfBirth`, `family.marriageDate`

**Issue detail:**

```
  - residence.place  [missing, score=0.0]  expected='Germany'  actual=MISSING
  - travel.purpose  [missing, score=0.0]  expected='Work — construction'  actual=MISSING
```

**Extractor raw (top 6):** education.earlyCareer=construction worker | travel.destination=Germany | family.children.relation=son | family.children.firstName=Vincent | family.children.placeOfBirth=Germany

---

## 33. `case_048` — early_adulthood / parenthood

**Life-map:** era=`early_adulthood` · pass=`pass1` · mode=`open`  
**Score:** overall=0.5 · v2_pass=False · categories=['field_path_mismatch']

**Q (Lori):** Tell me about your children.

**A (Narrator):** We had three boys — Vincent, Jason, and Christopher. Vincent was the oldest. They all grew up in North Dakota.

**Expected fields:**
- `family.children.firstName` = `Vincent`
- `family.children.relation` = `son`

**Forbidden (must_not_write):** `siblings.firstName`, `siblings.relation`

**Issue detail:**

```
  - family.children.firstName  [partial, score=0.8]  expected='Vincent'  actual='Vincent, Jason, Christopher'
  - family.children.relation  [missing, score=0.0]  expected='son'  actual=MISSING
```

**Extractor raw (top 6):** family.children.firstName=Vincent, Jason, Christopher | family.children.birthOrder=oldest | family.children.placeOfBirth=North Dakota

---

## 34. `case_064` — early_adulthood / marriage_story

**Life-map:** era=`early_adulthood` · pass=`pass1` · mode=`open`  
**Score:** overall=0.0 · v2_pass=False · categories=['schema_gap']

**Q (Lori):** Tell me about how you and Janice met and got married.

**A (Narrator):** Janice was something else. She was a country girl, grew up milking cows and riding her horse Grey out in Dodge. Her dad Pete worked on the Garrison Dam for a while, so the family moved around quite a bit — Dodge, Glen Ulin, Strasburg. We got married October 10, 1959. I was only nineteen and she was twenty. We didn't have much but we had each other. The weather that day was beautiful, one of those perfect fall days i…

**Expected fields:**
- `family.marriageDate` = `1959-10-10`
- `family.spouse.firstName` = `Janice`

**Issue detail:**

```
  - family.marriageDate  [missing, score=0.0]  expected='1959-10-10'  actual=MISSING
  - family.spouse.firstName  [missing, score=0.0]  expected='Janice'  actual=MISSING
```

**Extractor raw (top 6):** (none)

---

## 35. `case_072` — early_adulthood / marriage_children

**Life-map:** era=`early_adulthood` · pass=`pass1` · mode=`open`  
**Score:** overall=0.0 · v2_pass=False · categories=['schema_gap']

**Q (Lori):** How did you and Kent start your family?

**A (Narrator):** Kent and I got married October 10, 1959. I was twenty, he was nineteen — so I was the older one! We moved around quite a bit for his construction work. Our first boy Vincent was born in Germany, can you believe that? Then Jason came along, he's the family-oriented one. And Christopher — Chris — he was born December 24, 1962 in Williston, North Dakota. Christmas Eve, same as his dad's birthday. Kent's always said tha…

**Expected fields:**
- `family.marriageDate` = `1959-10-10`
- `family.children.firstName` = `Vincent`

**Issue detail:**

```
  - family.marriageDate  [missing, score=0.0]  expected='1959-10-10'  actual=MISSING
  - family.children.firstName  [missing, score=0.0]  expected='Vincent'  actual=MISSING
```

**Extractor raw (top 6):** (none)

---

## 36. `case_078` — early_adulthood / higher_education

**Life-map:** era=`early_adulthood` · pass=`pass1` · mode=`open`  
**Score:** overall=0.0 · v2_pass=False · categories=['schema_gap', 'noise_leakage']

**Q (Lori):** Did you go on to any further education after high school?

**A (Narrator):** I started at Bismarck Junior College studying Speech and History. I liked it, especially the Speech part. Those credits transferred to UND — that's the University of North Dakota. But then Kent and I got married in '59 and things went a different direction. My mother Josie had gone to Capitol Business College but hated the business side of it, and I think that stuck with me — I wanted to study things I actually care…

**Expected fields:**
- `education.higherEducation` = `Bismarck Junior College, Speech and History, credits transferred to UND`

**Issue detail:**

```
  - education.higherEducation  [missing, score=0.0]  expected='Bismarck Junior College, Speech and History, credits transferred to UND'  actual=MISSING
```

**Extractor raw (top 6):** family.children.relation=son | family.children.firstName=Vincent | parents.firstName=Josie

---

## 37. `case_086` — early_adulthood / career_family

**Life-map:** era=`early_adulthood` · pass=`pass1` · mode=`open`  
**Score:** overall=0.0 · v2_pass=False · categories=['schema_gap']

**Q (Lori):** Tell me about your working life and how it shaped your family.

**A (Narrator):** I went into construction and trades pretty much right away. That meant we moved a lot — wherever the work was. We lived in Germany for a while, that's where our oldest boy Vincent was born. Then back to North Dakota and other places. Janice was a trooper through all of it, kept the boys on track even when we'd be packing up and moving to a new town every year or two. She'd been through it herself growing up — her da…

**Expected fields:**
- `education.earlyCareer` = `Construction and trades`

**Issue detail:**

```
  - education.earlyCareer  [missing, score=0.0]  expected='Construction and trades'  actual=MISSING
```

**Extractor raw (top 6):** (none)

---

## 38. `case_103` — early_adulthood / germany_years

**Life-map:** era=`early_adulthood` · pass=`pass1` · mode=`open`  
**Score:** overall=0.0 · v2_pass=False · categories=['llm_hallucination']

**Q (Lori):** What was it like living in Germany?

**A (Narrator):** It was an adventure. I was working construction over there. Janice and I were young, just starting out. Our oldest, Vincent Edward, was born there. That was a big deal — having your first child in a foreign country. Janice handled it like she handled everything, just took it in stride. She'd grown up tough, milking cows in North Dakota. A German hospital wasn't going to throw her off. After Vincent we came back to t…

**Expected fields:**
- `residence.place` = `Germany`

**Issue detail:**

```
  - residence.place  [wrong, score=0.0]  expected='Germany'  actual="It was an adventure. I was working construction over there. Janice and I were young, just starting out. Our oldest, Vincent Edward, was born there. That was a big deal — having your first child in a foreign country. Janice handled it like she handled everything, just took it in stride. She'd grown up tough, milking cows in North Dakota. A German hospital wasn't going to throw her off. After Vincent we came back to the States and eventually the other two boys came along — Jason and then Chris in Williston."
```

**Extractor raw (top 6):** residence.place=It was an adventure. I was working construction over there. Janice an…

---

## 39. `case_037` — midlife / health_and_body

**Life-map:** era=`midlife` · pass=`pass1` · mode=`open`  
**Score:** overall=0.5 · v2_pass=False · categories=['llm_hallucination']

**Q (Lori):** Was there a time when your health changed how you lived your daily life?

**A (Narrator):** When I got older my knees gave out from all those years of construction. Concrete and roofing — that's hard on the body. I had to slow down a lot in my seventies.

**Expected fields:**
- `health.majorCondition` = `Knee problems from construction work`
- `health.lifestyleChange` = `Had to slow down in seventies`

**Forbidden (must_not_write):** `personal.dateOfBirth`, `education.earlyCareer`

**Issue detail:**

```
  - health.majorCondition  [wrong, score=0.0]  expected='Knee problems from construction work'  actual='knees gave out due to construction-related injuries'
  - health.lifestyleChange  [partial, score=0.9]  expected='Had to slow down in seventies'  actual='had to slow down a lot in my seventies'
```

**Extractor raw (top 6):** health.lifestyleChange=had to slow down a lot in my seventies | health.majorCondition=knees gave out due to construction-related injuries

---

## 40. `case_043` — midlife / travel_and_world

**Life-map:** era=`midlife` · pass=`pass1` · mode=`open`  
**Score:** overall=0.5 · v2_pass=False · categories=['llm_hallucination']

**Q (Lori):** What was the most memorable trip you ever took?

**A (Narrator):** Hawaii was special. We went there as a family. And I've been to France — that's where the Shong family came from originally. John Michael Shong was from near Nancy in Lorraine.

**Expected fields:**
- `travel.destination` = `France`
- `travel.purpose` = `Ancestry connection`

**Forbidden (must_not_write):** `residence.place`, `personal.dateOfBirth`

**Issue detail:**

```
  - travel.purpose  [wrong, score=0.0]  expected='Ancestry connection'  actual='family vacation'
```

**Extractor raw (top 6):** travel.destination=Hawaii | travel.purpose=family vacation | travel.destination=France | greatGrandparents.firstName=John Michael | greatGrandparents.birthPlace=near Nancy in Lorraine

---

## 41. `case_061` — middle_adulthood / uncertain_date

**Life-map:** era=`midlife` · pass=`pass1` · mode=`open`  
**Score:** overall=0.0 · v2_pass=False · categories=['schema_gap']

**Q (Lori):** When and where did you get married?

**A (Narrator):** We got married at St. Mary's church. I think it was 1956, maybe 1957. I'm not sure of the exact year anymore.

**Expected fields:**
- `family.marriagePlace` = `St. Mary's`

**Issue detail:**

```
  - family.marriagePlace  [missing, score=0.0]  expected="St. Mary's"  actual=MISSING
```

**Extractor raw (top 6):** family.marriageDate=1956 | family.marriageDate=1957

---

## 42. `case_070` — midlife / family_life

**Life-map:** era=`midlife` · pass=`pass1` · mode=`open`  
**Score:** overall=0.533 · v2_pass=False · categories=['schema_gap']

**Q (Lori):** Tell me about your kids — how many do you have?

**A (Narrator):** I've got four kids. Well, Vince — Vincent Edward — he's the oldest, he was actually born over in Germany when we were living there. Then there's Gretchen Jo, she was born October 4, 1991. She's in Austin, Texas now. Amelia Fay came along in '94, August 5th. She's got her MSW, she's been all over — New Mexico, Colorado, Hawaii — working in social services. And Cole, the youngest, Cole Harber Horne, born April 10, 200…

**Expected fields:**
- `family.children.firstName` = `Vincent`
- `family.children.relation` = `son`

**Issue detail:**

```
  - family.children.firstName  [partial, score=0.8]  expected='Vincent'  actual='Vincent Edward'
  - family.children.relation  [missing, score=0.0]  expected='son'  actual=MISSING
```

**Extractor raw (top 6):** family.marriageDate=2010-12-22 | family.children.firstName=Vincent Edward | family.children.firstName=Gretchen Jo | family.children.dateOfBirth=1991-10-04 | family.children.firstName=Amelia Fay | family.children.dateOfBirth=1994-08-05 | …(+2 more)

---

## 43. `case_084` — midlife / children_detailed

**Life-map:** era=`midlife` · pass=`pass1` · mode=`open`  
**Score:** overall=0.0 · v2_pass=False · categories=['schema_gap']

**Q (Lori):** Can you tell me a bit more about each of your kids — what they're doing now?

**A (Narrator):** Sure. Gretchen Jo was born October 4, 1991. She's been through a lot — went through some major life challenges in 2024, been going to ACA meetings. She lives in Austin, Texas now. Then Amelia Fay, born August 5, 1994. She's got her MSW, master's in social work. She's lived everywhere — New Mexico, Colorado, Hawaii — she works in social services. And Cole Harber Horne, born April 10, 2002, he's the baby. He's in medi…

**Expected fields:**
- `family.children.firstName` = `Gretchen`
- `family.children.dateOfBirth` = `1991-10-04`

**Issue detail:**

```
  - family.children.firstName  [missing, score=0.0]  expected='Gretchen'  actual=MISSING
  - family.children.dateOfBirth  [missing, score=0.0]  expected='1991-10-04'  actual=MISSING
```

**Extractor raw (top 6):** (none)

---

## 44. `case_093` — midlife / spouse_detail

**Life-map:** era=`midlife` · pass=`pass1` · mode=`open`  
**Score:** overall=0.7 · v2_pass=False · categories=['guard_false_positive', 'noise_leakage']

**Q (Lori):** What else can you tell me about Janice?

**A (Narrator):** Janice is a strong woman. She grew up milking cows and riding horses in North Dakota. Her dad Pete worked all kinds of jobs — Garrison Dam, carpentry, steam boiler work. She went to Bismarck Junior College before we got married. She's always been independent. We raised three boys together and she kept that family running through every move and every job change.

**Issue detail:**

```
  - must_not_write VIOLATED: ['education.higherEducation']
```

**Extractor raw (top 6):** family.spouse.firstName=Janice | family.spouse.notes=strong woman, grew up milking cows and riding horses in North Dakota,… | education.higherEducation=Bismarck Junior College

---

## 45. `case_104` — legacy_reflection / life_lessons

**Life-map:** era=`later_life` · pass=`pass1` · mode=`open`  
**Score:** overall=0.0 · v2_pass=False · categories=['schema_gap']

**Q (Lori):** What are the most important things life has taught you?

**A (Narrator):** Family is everything. That sounds simple but it's the truth. My parents moved us all over the country for Dad's construction work, but Mom kept that family together through every single move. She had studied Speech and History at Bismarck Junior College — she was educated, she was smart, but she chose to put the family first. Dad worked with his hands his whole life and never complained. I look at my own kids now —…

**Expected fields:**
- `laterYears.lifeLessons` = `Family is everything — show up and be there`

**Issue detail:**

```
  - laterYears.lifeLessons  [missing, score=0.0]  expected='Family is everything — show up and be there'  actual=MISSING
```

**Extractor raw (top 6):** (none)

---
