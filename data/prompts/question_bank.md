# Phase-Aware Question Bank — Review Copy (v2)

*Rendered from `data/prompts/question_bank.json` (version 2). Read-through for voice/quality before flipping `HORNELORE_PHASE_AWARE_QUESTIONS=1`. Edits you mark here get applied to the JSON source.*

## What changed from v1

- v2 — Full voice pass across all openers (sensory anchors, de-stacked 'and'
-      questions, one-at-a-time framing). Three pushback fixes applied:
-      (1) 'close your eyes' stage direction removed from earliest_memory,
-      (2) branch-specific 'yellow footprints' removed from post_education,
-      (3) partnership_midlife reworked to include the divorce/shift case.

-      Ten new sub-topics added to cover narrative dimensions missing from v1:
-        Phase 1: family_stories_and_lore, childhood_pets,
-                 childhood_fears_and_comforts, family_rituals_and_holidays
-        Phase 2: first_car_and_possessions
-        Phase 3: siblings_as_adults
-        Phase 4: pets_and_vehicles_family_years, holidays_and_traditions_built
-        Phase 5: objects_that_hold_meaning, present_fears_and_hopes

-      Total: 35 sub-topics (from 25), ~140 openers (from 99),
-      ~105 follow-ups (from 75). Spine anchors unchanged.

---

## Voice Guidelines

- Warm, invitational, one question at a time.
- Prefer specific over generic: 'what did the kitchen look like' beats 'tell me about the house'.
- Never stack questions (no 'where did you grow up AND what was your favorite food').
- Avoid leading ('wasn't that wonderful?'). Prefer open-ended ('what comes to mind?').
- Sensory anchors elicit recall: smells, sounds, textures, specific objects.
- Use 'moment' more than 'memory' — 'memory' feels like a test, 'moment' feels like a movie scene.
- Name specifics when you know them (from spine or promoted truth): 'when you started kindergarten in 1968…' is stronger than 'when you started kindergarten…'.
- Never ask a factual question Lori can already answer from promoted truth.

---

# Phase 1 — Developmental Foundations

**Age range:** 0–12
**Spine phases covered:** pre_school, elementary, middle
**Purpose:** Birth through elementary. Narrator as passenger; focus on environment and firsts.

**Voice notes:**
- Narrator was young — gentle framing, accept 'I don't remember' as valid.
- Parents and caregivers are the anchors here, not the narrator's own actions.
- Sensory prompts work best at this age (smells of home, first teacher's voice).

**Gating questions (operator, yes/no):**
- Do you have early memories of your home before school?
- Do you remember your kindergarten or first-grade teacher?

---

## 1.1 Origin point
**Intent:** Capture birth context and family lore around it.
**Spine anchor:** `birth`
**Extract priority:** `personal.dateOfBirth`, `personal.placeOfBirth`, `parents.firstName`, `parents.occupation`

**Questions:**
1. What is the story your parents told you about the day you were born?
2. When your family talked about the day you arrived, who did they say was the first person to come meet you?
3. Do you know the hospital or the town where you were born?
4. What season was it when you arrived — and what have you been told about the weather that day?

**Follow-ups:**
- Who told you that story — your mother, your father, a grandparent?
- Is there a photo from around that time you remember?
- What was happening in your parents' lives right before you arrived?

---

## 1.2 Earliest memory
**Intent:** Surface the first concrete scene the narrator can recall.
**Extract priority:** `earlyMemories.firstMemory`, `earlyMemories.significantEvent`

**Questions:**
1. What's the very first 'movie clip' of your life that you can see — not from a photograph, but from inside your own head?
2. When you think of being small, what scene comes to mind first?
3. What is the earliest moment you remember from being outside your own house?
4. What's an early moment you have that nobody else in your family seems to remember?

**Sensory prompts:**
- A smell from that age — what was it?
- A sound — something someone said, or a song on the radio?
- A texture — a blanket, a floor, a favorite toy?

**Follow-ups:**
- How old do you think you were?
- Who else was in the room?
- What time of year do you think it was?

---

## 1.3 Geographic anchor — first home you remember
**Intent:** Pin down the first clearly-remembered residence with address-level precision when possible.
**Extract priority:** `residence.place`, `residence.period`

**Questions:**
1. What was the street name or house number of the very first home you can picture?
2. Can you picture the first house or apartment you remember — what town was it in?
3. Where did you live when you were small enough that you couldn't go outside alone?
4. How long did your family stay in that first home, as far as you know?

**Follow-ups:**
- Who lived there with you?
- Where was your bedroom in that house — and did you share it with anyone?
- What was just outside the door — a yard, a street, a field, a playground?

---

## 1.4 Early caregivers and family structure
**Intent:** Map the people surrounding the narrator in the developmental window.
**Extract priority:** `parents.firstName`, `parents.relation`, `parents.occupation`, `siblings.firstName`, `siblings.birthOrder`

**Questions:**
1. Who were the people you saw every single day at the breakfast table when you were very small?
2. Was there a grandparent or other relative who was part of daily life in your home?
3. If you have siblings, where did you fall in the lineup — oldest, youngest, somewhere in between?
4. Who spent the most time with you before school started?

**Follow-ups:**
- What did your parents do for work?
- How did your parents meet, if you know the story?
- Was there a pet in the house in those years?

---

## 1.5 Entering school
**Intent:** Capture kindergarten and early-grade experiences.
**Spine anchor:** `school_kindergarten`
**Extract priority:** `education.schooling`, `earlyMemories.firstMemory`

**Questions:**
1. What was the name of your primary school, and can you tell me about the classroom or the teacher on your very first day?
2. Can you picture your kindergarten room — what was on the walls?
3. Who walked you to school on the first day, or how did you get there?
4. What do you remember about the teacher who ran your kindergarten class?

**Follow-ups:**
- Was the school in the same town you lived in?
- Do you remember one friend from that first classroom?
- What did you wear on your first day?

---

## 1.6 Family stories and lore
**Intent:** Capture the legendary births, tall tales, and recurring stories that circle back at family gatherings.
**Extract priority:** `earlyMemories.significantEvent`, `parents.notableLifeEvents`

**Questions:**
1. Is there a story in your family about an unusual birth — someone born in a car, in a hallway, during a storm?
2. Who is the most 'legendary' relative in your family — the one whose stories always come up at gatherings?
3. Is there a family story you've heard so many times you could tell it word-for-word?
4. What's one tall tale from your family that you've always suspected might actually be true?

**Follow-ups:**
- Who is the keeper of that story now?
- Does it get bigger each time it's told?
- Is there a version of that story that never gets told in front of the children?

---

## 1.7 Pets and animals of childhood
**Intent:** Capture the specific animals — with names and personalities — that populated the narrator's early world. Includes livestock and unusual pets.
**Extract priority:** `hobbies.hobbies`, `earlyMemories.significantEvent`

**Questions:**
1. Was there an animal in your childhood — a dog, a cat, a horse, a pig, a snake — that had its own personality you still remember?
2. What was the name of the family pet that felt most like yours?
3. Did you grow up around animals that weren't typical house pets — a horse, livestock, birds, something unusual?
4. Is there an animal from your childhood whose loss you still remember clearly?

**Follow-ups:**
- Where did that animal sleep?
- What's the one thing that animal did that nobody else's pet ever did?
- Who in the family was closest to it?

---

## 1.8 Fears, comforts, and the edges of the child's world
**Intent:** Surface the emotional textures of early life — what scared them, what soothed them, the invisible lines around their world.
**Extract priority:** `earlyMemories.significantEvent`, `hobbies.personalChallenges`

**Questions:**
1. What were you most afraid of as a small child — the dark, a storm, a particular room, an imagined creature?
2. When you were scared at night, who or what did you go to?
3. Was there something in your home or neighborhood that always made you feel safe?
4. Was there a specific place — a room, a corner of the yard, a particular chair — that was 'yours' when you needed to be alone?

**Follow-ups:**
- Did your parents know about that fear?
- Is there a comfort object whose texture you can still feel?
- Do you think any of those childhood fears followed you into adulthood?

---

## 1.9 Family rituals, holidays, and inherited culture
**Intent:** Capture the recurring traditions — religious, ethnic, cultural — that gave the child's year its shape.
**Extract priority:** `hobbies.hobbies`, `earlyMemories.significantEvent`

**Questions:**
1. How did your family mark Christmas, Hanukkah, or whichever holiday was central — were there traditions you only later realized came from a specific heritage?
2. Was there a food, a song, or a ritual in your home that only made sense once you knew where your family came from?
3. Did your family put up the Christmas tree on an early date, a late date, or an exact day — was that a negotiation every year?
4. What holiday meal do you remember most clearly from when you were small — the smells, the table, who was there?

**Follow-ups:**
- Who led that tradition — your mother, your grandmother, someone specific?
- Is that tradition still in your family, or did it fade?
- Did you carry any of it into the home you built as an adult?

---

# Phase 2 — Transitional Adolescence

**Age range:** 13–18
**Spine phases covered:** middle, high_school
**Purpose:** Middle school through high-school graduation. Shifts in autonomy, first legal milestones.

**Voice notes:**
- Narrator begins to be the subject of their own decisions — invite agency framing.
- Emotional stakes rise; some memories may be guarded. Pace matters.
- Legal milestones (license, first job, graduation) are anchors for dating other memories.

**Gating questions (operator, yes/no):**
- Did you change schools during your teenage years?
- Did you have a job before you finished high school?
- Did you get a driver's license as a teenager?

---

## 2.1 Pivot point — adolescent transitions
**Intent:** Identify the shift from childhood world to teenage world — a move, a new school, a family change.
**Extract priority:** `residence.place`, `education.schooling`, `laterYears.significantEvent`

**Questions:**
1. What was the biggest change in your life the year you turned thirteen?
2. When you moved from elementary to middle school, was there something else shifting at home at the same time?
3. Is there a year in your teens when things felt like they tipped — a move, a parent's job change, a new school?
4. What year do you think your childhood ended and your teenage years really began?

**Follow-ups:**
- How did you feel about that change at the time — not looking back now?
- Did your friend group change with it?
- Who in your family had the hardest time with that transition?

---

## 2.2 Autonomy milestones — license, first job, first money
**Intent:** Pin concrete legal/financial firsts. The driver's license is a spine anchor at age 16.
**Spine anchor:** `civic_drivers_license_age`
**Extract priority:** `education.earlyCareer`, `residence.period`

**Questions:**
1. Tell me about the day you finally got your driver's license — who taught you to drive?
2. What was your first part-time job — babysitting, paper route, store, farm? How old were you?
3. What's the first money you earned that felt like yours — and what did you spend it on?
4. Was there a first vehicle or bike of your own before you graduated high school?

**Follow-ups:**
- Where did you take the driving test?
- What was the name of the place that first employed you?
- Did that first job teach you something you still carry?

---

## 2.3 Family dynamics in the teenage years
**Intent:** Capture relationships with parents and siblings during the independence push.
**Extract priority:** `parents.notableLifeEvents`, `siblings.uniqueCharacteristics`

**Questions:**
1. In your teenage years, how would you describe your relationship with each of your parents?
2. Which of your siblings felt like your 'partner in crime' during your teenage years?
3. What was the one house rule you were most likely to break when you were sixteen?
4. Do you remember a specific argument or disagreement from your teenage years that stayed with you?

**Follow-ups:**
- How was that handled at the time?
- Do you see it differently now?
- Was there a family member who understood you then?

---

## 2.4 Adolescent friendships
**Intent:** Identify the people who mattered during the formative teenage years.
**Extract priority:** `hobbies.hobbies`

**Questions:**
1. If I walked into your high school cafeteria, who would you be sitting with?
2. Was there a group or crowd you were part of — a sports team, a band, a church youth group, a neighborhood crew?
3. Is there a friend from that time whose name still brings back a specific memory?
4. When you and your friends wanted to get away from the adults, where was your 'secret' spot?

**Follow-ups:**
- What did you do together that you couldn't have done alone?
- Who was the one everyone gathered around?
- Is there someone from that time you lost touch with and still think about?

---

## 2.5 The launch — graduation and what came next
**Intent:** Anchor HS graduation year and the first post-graduation decision.
**Spine anchor:** `school_graduation`
**Extract priority:** `education.higherEducation`, `education.earlyCareer`, `residence.place`

**Questions:**
1. Once the high school graduation ceremony was over, what was the very first 'adult' decision you had to make?
2. Do you remember your graduation day — who was sitting in the audience for you?
3. What did you think you would do with your life when you walked out of high school?
4. Was there a moment that summer when you realized childhood was actually over?

**Follow-ups:**
- Did you go on to college, the military, a job, or something else?
- Where did you live right after graduation?
- Who did you spend that first summer with?

---

## 2.6 First car and early possessions
**Intent:** Capture the vehicle or object that gave the narrator their first real independence.
**Extract priority:** `hobbies.hobbies`, `residence.place`

**Questions:**
1. What was your first car — the make, the model, the color, the condition?
2. How did you come to own it — did you buy it, was it a gift, did you inherit it from an older sibling?
3. What was the farthest trip you ever took in that first car?
4. What did you keep in the glove compartment or the trunk that you'd be embarrassed to admit now?

**Follow-ups:**
- What did it sound like when it started?
- Did you name it?
- What happened to that car in the end?

---

# Phase 3 — Early Adulthood & Establishing

**Age range:** 19–35
**Spine phases covered:** post_school
**Purpose:** The densest period for chronological precision — career starts, relocations, partnerships, parenthood.

**Voice notes:**
- Many parallel threads here — relationship, career, geography, children — ask one thread at a time.
- Specific dates matter (job start, marriage, first child); prioritize precision over narrative here.
- Emotional weight is high; some memories are proud, some painful. Invite both.

**Gating questions (operator, yes/no):**
- Did you go to college or technical school after high school?
- Did you serve in the military?
- Are you married or have you been married?
- Do you have children?

---

## 3.1 Post-education years
**Intent:** Capture college / trade / military / first independent living.
**Spine anchor:** `education_college_start`
**Extract priority:** `education.higherEducation`, `residence.place`

**Questions:**
1. In the first year after you finished high school, where did you lay your head at night?
2. If you went to college, what was the school and what did you study?
3. Where was the first place you lived as an adult — the first address that was yours, not your parents'?
4. If you served in the military, what was the date you first reported for duty?

**Follow-ups:**
- Who were your roommates or the people in your world then?
- What did you do for money?
- Is there a teacher, sergeant, or mentor from that time who shaped you?

---

## 3.2 Professional genesis — first real career
**Intent:** Pin down the first post-education job that felt like a career, with start/end dates.
**Extract priority:** `education.earlyCareer`, `education.careerProgression`

**Questions:**
1. What was the name of the first company that gave you a paycheck for 'real' professional work?
2. Who gave you that first real job — was there someone who took a chance on you?
3. What was the very first thing you did when you walked into the office or job site each morning?
4. What did you learn in that first career role that you still use today?

**Follow-ups:**
- What year did you start, and what year did you leave?
- How much did that first job pay?
- Why did you leave, and where did you go next?

---

## 3.3 Relationship anchors — how you met, when it became official
**Intent:** Capture marriage / long-term partnership dates and origins.
**Extract priority:** `family.spouse`, `family.marriage_date`

**Questions:**
1. Think back to the very first time you met your partner — where were you standing?
2. How did you and your partner first cross paths — a place, a day, a friend who introduced you?
3. What year did you get married, and where was the ceremony?
4. Before the one who became your long-term partner, was there someone else significant you dated seriously?

**Follow-ups:**
- On what date did you two officially start your life together under one roof?
- What made you know?
- Who was at the wedding?

---

## 3.4 Becoming a parent
**Intent:** Record each child's birth with date and location.
**Extract priority:** `family.children`, `residence.place`

**Questions:**
1. Let's start with your first child — what was the date they were born?
2. Take me back to the day your first child was born — where were you when labor started?
3. How did the family change when each child arrived — first one, second one, each in turn?
4. What did you name each of your children, and why those names?

**Follow-ups:**
- What hospital or city was each child born in?
- Who was the doctor or midwife?
- What was your life like in the year before each child arrived?

---

## 3.5 Who you were becoming
**Intent:** Broader narrative — what kind of adult was the narrator turning into.
**Extract priority:** `hobbies.hobbies`, `additionalNotes.unfinishedDreams`

**Questions:**
1. At age twenty-five, what did you think 'success' was going to look like for you?
2. Was there a version of your life you were chasing then that looks different from the one you ended up with?
3. What was a hobby you picked up in your twenties that you completely obsessed over for a while?
4. Who were your closest friends in that decade — people from work, neighbors, old friends carried forward?

**Follow-ups:**
- When did you first feel like an adult — not just legally, but inside?
- What belief did you have at 25 that you've revised since?
- Was there a mentor who mattered in that period?

---

## 3.6 Siblings as adults
**Intent:** Map how siblings' lives diverged, the marriages and struggles that shaped them, and the narrator's place in the sibling constellation.
**Extract priority:** `siblings.firstName`, `siblings.uniqueCharacteristics`, `family.children`

**Questions:**
1. How did each of your siblings' adult lives turn out — the marriages, the moves, the paths they chose?
2. Was there a sibling whose spouse you found hard to be around — too controlling, too distant, too different from the family?
3. Did any of your siblings live a life that surprised you — good or hard?
4. Is there a sibling you're closest to now, and one you've drifted from?

**Follow-ups:**
- When did you last see them?
- What would you want recorded about that sibling's life, even if they wouldn't write it themselves?
- Is there a family event that reset your relationship with one of them?

---

# Phase 4 — Mastery & Mid-Life

**Age range:** 36–60
**Spine phases covered:** post_school
**Purpose:** Sustained roles, civic contributions, peak professional years, parental care transitions.

**Voice notes:**
- Narrator is now the experienced adult; questions can assume agency.
- Parental care and grief may surface — allow space, don't rush.
- Career plateaus and pivots both matter; neither is more 'narrative' than the other.

**Gating questions (operator, yes/no):**
- Did you change careers at some point in your forties or fifties?
- Were you involved in caring for your parents in their later years?
- Did you move homes during your midlife years?

---

## 4.1 Career peaks — the long-held role
**Intent:** Identify the position that defined the narrator's working life, with its years.
**Extract priority:** `education.careerProgression`

**Questions:**
1. Which of your many jobs do you feel defined your professional life the most?
2. What job would you most want on the record — the one you'd be proud to have remembered?
3. Was there a moment when you realized you had become the experienced person others came to for answers?
4. Did you ever mentor or supervise others? Who stands out among them?

**Follow-ups:**
- What was the title you held the longest?
- What accomplishment from that role are you proudest of?
- Was there a project, a client, or a student you'd want named in the record?

---

## 4.2 Middle moves — the residential shifts of midlife
**Intent:** Capture the geographic changes between age 40 and 60 and what prompted them.
**Extract priority:** `residence.place`, `residence.period`

**Questions:**
1. Think of the house you lived in when you turned forty-five — what did the kitchen look like?
2. What cities or towns did you call home during your midlife years, in the order you lived in them?
3. Was there a house in your midlife that felt most like home?
4. What was the 'tipping point' that made you decide it was time to leave your last home and move to the next?

**Follow-ups:**
- What was the address of that favorite midlife home?
- Who lived there with you?
- What did you leave behind when you moved, and what did you take?

---

## 4.3 Partnerships in midlife
**Intent:** Marriage, divorce, remarriage, or sustained partnership through the midlife window.
**Extract priority:** `family.spouse`, `family.marriage_date`

**Questions:**
1. In the busy middle years of your life, was there one ritual you and a partner always made sure to keep — or a season when that partnership shifted?
2. If you were married through that period, what sustained it through the hard seasons?
3. What year did your life take a major turn because of a change in your relationship status?
4. Did a new relationship begin somewhere in midlife that became important?

**Follow-ups:**
- Who helped you through that time?
- What did you learn about yourself?
- What does that chapter look like to you now, with distance?

---

## 4.4 Your children growing up
**Intent:** Capture the narrator-as-parent through their kids' teenage and adult years.
**Extract priority:** `family.children`

**Questions:**
1. What was the hardest part about watching your children start to make their own mistakes?
2. What was one child's adolescence like from your perspective — the struggles and the milestones?
3. Is there a moment when you realized your children had grown up — that they were their own people?
4. What is a habit or phrase of yours that you now hear coming out of your children's mouths?

**Follow-ups:**
- When did each child leave home?
- Did any of them live through something you didn't, and how did you support them?
- What do they do now?

---

## 4.5 Caring for your parents
**Intent:** The role-reversal moment — when parents aged and the narrator stepped in.
**Extract priority:** `parents.notableLifeEvents`

**Questions:**
1. When did your role shift toward caring for your own parents?
2. Was there a specific event — a diagnosis, a fall, a move — when you realized your parents needed you?
3. Did you move your parents, visit more often, or bring them into your home?
4. What year did you have to say goodbye to your father? And your mother?

**Follow-ups:**
- Who else in the family helped?
- What's the last thing you remember them saying to you?
- How did that loss change your own sense of who you were?

---

## 4.6 Pets and vehicles of the family years
**Intent:** Capture the dogs, cats, horses, cars, and trucks that your own children grew up alongside.
**Extract priority:** `family.children`, `hobbies.hobbies`

**Questions:**
1. What was the family dog or cat your children grew up with — name, breed, the specific trait that made them family?
2. Was there a car — a station wagon, a pickup, a mini-van — that seems to appear in every family photo from that era?
3. Did you keep any animals your kids treated as their own — a horse they learned to ride, a rabbit, a chicken they named?
4. Was there a vehicle or boat in those years that made possible a trip your children still talk about?

**Follow-ups:**
- Who in the family was most attached to that animal or vehicle?
- What happened to it — sold, died, passed on?
- Do your kids still reference it now?

---

## 4.7 Holidays and traditions you built
**Intent:** The traditions the narrator carried forward from their own childhood and the new ones they created as a parent.
**Extract priority:** `family.children`, `hobbies.hobbies`

**Questions:**
1. Which holidays became the 'big ones' in the home you built with your own children?
2. Was there a tradition you carried over from your own childhood, even if you had to fight to keep it?
3. Is there a tradition you made up — something that didn't exist in your parents' home — that your kids now think has always been there?
4. What meal, song, or ritual did you make sure your children would remember?

**Follow-ups:**
- Who did it for the first time — you, your partner, a grandparent?
- Did your kids resist it at first?
- Is it still happening now, or did it fade as they grew up?

---

# Phase 5 — Legacy & Reflection

**Age range:** 61–200
**Spine phases covered:** post_school
**Purpose:** From professional identity to personal legacy. Retirement, archiving, reflection.

**Voice notes:**
- Narrator is the elder now — invite authority, perspective, summary.
- Reflection questions work well here; pure fact-gathering feels shallow.
- Grief and satisfaction often coexist in the same memory; don't force one tone.

**Gating questions (operator, yes/no):**
- Have you retired, or are you still working?
- Have you begun collecting family history or writing memories down?
- Do you have grandchildren?

---

## 5.1 The off-ramp — retirement
**Intent:** Anchor the last day of professional work and the early days of retirement.
**Spine anchor:** `civic_social_security_early`
**Extract priority:** `laterYears.retirement`

**Questions:**
1. Can you describe the feeling of walking out of your workplace on your very last day?
2. Was there a ceremony or a lunch, or did you just quietly close the door on that part of your life?
3. What did you think retirement would feel like, and what did it actually feel like?
4. What did you start doing in retirement that you'd never done before?

**Follow-ups:**
- Did you miss the work?
- What did you finally have time for?
- Did your daily rhythm change all at once, or slowly?

---

## 5.2 Ancestral archiving
**Intent:** The project the narrator takes on to preserve family memory — the reason they're here now.
**Extract priority:** `hobbies.hobbies`, `additionalNotes.unfinishedDreams`

**Questions:**
1. Was there a specific box of photos, a document, or a story someone told that made you realize 'I need to write this down'?
2. Is there a specific person — a grandchild, a relative, your younger self — you're doing this archiving for?
3. What stories are you most afraid will be lost if you don't tell them?
4. Have you been the keeper of the family's records, photos, or stories? For how long?

**Follow-ups:**
- Who else in the family cares about this project?
- What's the one thing you've always meant to write down?
- Is there a story you heard from your own grandparents that you'd want to pass forward?

---

## 5.3 Grandchildren and elders around you
**Intent:** The narrator's place in the family tree now — who's above, who's below.
**Extract priority:** `family.children`, `family.grandchildren`

**Questions:**
1. Think of your oldest grandchild — what is the first word that comes to mind when you describe their personality?
2. Is there a grandchild who reminds you of someone from an earlier generation?
3. Who is the person you look to now when you need 'elder' wisdom?
4. Has any grandchild asked you about your early life? What did they want to know?

**Follow-ups:**
- How often do you see them?
- What do you most hope they'll remember about you?
- Is there a family ritual they know that came from you?

---

## 5.4 What you want to be remembered for
**Intent:** Explicit statement of legacy — not to be promoted as truth, but to guide memoir arc.
**Extract priority:** `additionalNotes.unfinishedDreams`

**Questions:**
1. When your grandchildren tell their grandchildren about you, what do you hope they say?
2. If you could pick one project or achievement to represent your life's work, which one would it be?
3. Is there a piece of advice, a phrase, or a habit that you'd want carried down the family for a hundred years?
4. What is something you've created with your hands that you hope your great-grandchildren will still be using?

**Follow-ups:**
- Why that, and not something else?
- Who else understood that part of you?
- Is there still something you hope to do?

---

## 5.5 Looking back
**Intent:** Broad reflection — lessons, regrets, proud moments, things they've reconsidered.
**Extract priority:** `laterYears.lifeLessons`, `hobbies.personalChallenges`

**Questions:**
1. Is there a decision from your younger years that you would make exactly the same way if you had to do it over today?
2. What did you worry about at 25 that turned out not to matter?
3. What did you not worry about that you wish you had?
4. What do you know now that no one could have told your younger self — they'd have had to live it?

**Follow-ups:**
- What event in your life taught you that?
- When did you realize it?
- Is there a book, a song, or a place that captures it?

---

## 5.6 Objects that hold meaning
**Intent:** The specific physical items — cars, photos, tools, jewelry — the narrator would grab from a burning house.
**Extract priority:** `additionalNotes.unfinishedDreams`

**Questions:**
1. If your house were burning and everyone you loved was already safe, what single object would you run back for?
2. Is there a car, a tool, or a piece of furniture you've kept far longer than practical because of what it means?
3. Is there one photograph — one specific frame — you'd want in every child's and grandchild's home?
4. Is there an object from your own parents' or grandparents' home that has stayed with you?

**Follow-ups:**
- Who gave it to you, or how did it come to you?
- What would you want written on the back of it so it still means something in a hundred years?
- Is there someone specific you'd leave it to?

---

## 5.7 Present fears, present hopes
**Intent:** The emotional interior of the elder — what they carry now, what they let go, what they hope for.
**Extract priority:** `laterYears.lifeLessons`, `hobbies.personalChallenges`

**Questions:**
1. What do you worry about now that you couldn't have worried about at forty?
2. Is there a fear from earlier in your life that turned out not to be worth the energy you gave it?
3. What gives you peace on a hard day?
4. What do you hope to see happen before you're gone?

**Follow-ups:**
- Who do you talk to about those worries?
- What's something you've stopped worrying about this past year?
- Is there a moment you're quietly looking forward to?

---

# Review notes

When you find a question to change, mark it here or in the JSON directly. Common patterns to watch for:

- **Stacked questions** — any question with 'and' splitting two asks (fix: pick one, move the other to follow-ups).
- **Leading** — 'wasn't that…' / 'don't you think…' (fix: open-ended reframing).
- **Generic** — 'tell me about your childhood' (fix: pin to specific anchor — an address, a date, a specific object).
- **Presumes** — asks about spouse when narrator may never have married (fix: conditional phrasing, or move behind a gating question).
- **Wrong voice for Horne family** — anything that sounds like a therapist or journalist instead of a memoirist.

When you're ready, say the word and I'll apply your edits and bump `_version` to 3.
