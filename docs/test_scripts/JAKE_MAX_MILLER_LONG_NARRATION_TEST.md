# JAKE MAX MILLER long-narration test — Kent content, fresh narrator

**Created:** 2026-06-15
**Purpose:** Stress-test the new oral-history + Phase 1 stack on a fresh
narrator (no pre-loaded template, no profile_seed). Chapters drawn from
Kent James Horne's biographical material, rewritten as first-person
monologue so the operator can paste them sequentially without manual
authoring.

The test asks one structural question: **does new Lori let a narrator
tell three long chapters in sequence without re-asking the same
question, without grabbing onto stray nouns, and without making the
narrator stop to explain what "Early School Years" means?**

Compare against the May 11 2026 Kent transcript (old stack, pre-WO
sequence) where Lori:
- asked "What did handling meal tickets actually require you to do?"
  four times across one chapter
- crammed 5+ anchors into one compound question
- forced Kent to ask "What does Adolescence mean?" because the era
  labels surfaced without context
- triggered Kent's complaint "you are being vague and not asking about
  basic training rather the sensory parts of it"

If the new stack lets Jake tell all three chapters without those four
failure modes appearing, the WO sequence delivered what it promised.

---

## OPERATOR PROTOCOL

1. **Create a fresh narrator** named `Jake Max Miller`.
   - DOB: **1939-12-24** (matches Kent's, so the chapter content's
     historical era — WWII, postwar prairie, 1957 Army induction — fits)
   - Birthplace: leave blank or write "Stanley, North Dakota"
     (we want to see whether Lori echoes back the same place name
     Jake said, or substitutes the template default)
   - Do NOT touch any other fields. Specifically do not preload
     parents/spouse/children. The test is about how Lori behaves
     with a near-empty narrator.

2. **Enter Interview Mode.** Confirm session style is `oral_history`
   (default).

3. **Paste Chapter 1 verbatim.** Send it as one narrator turn — do NOT
   split it across multiple sends. The test is whether Lori treats
   a single chapter as a single chapter, not whether the chat UI
   handles paragraphs.

4. **Wait for Lori's response.** Score against the per-chapter checklist
   below. Don't reply yet — just observe.

5. **Then paste Chapter 2** as one turn. Wait. Score.

6. **Then paste Chapter 3** as one turn. Wait. Score.

7. **Bonus probe** — paste the short follow-up at the bottom. That
   exercises low-momentum / closing-marker mode and the thread bank's
   surfacing rules.

8. After all four turns: open the Shadow Review panel (extraction
   results) and the api.log for a sanity sweep. Pattern grep below.

---

## CHAPTER 1 — EARLIEST YEARS

> I was born on Christmas Eve, 1939, in Stanley, North Dakota. My
> father Ervin worked the land outside of town and my mother Leila —
> Leila Myrtle, Carkuff was her maiden name — kept the house and the
> garden and the canning and the kids. I had an older sister Sharon
> who was two when I came along, and three years later in 1942 our
> little sister Linda was born. So we were three: Sharon, me, Linda.
> The middle one. My father's people were Hornes who had come up to
> Ross, North Dakota in 1902 — my grandfather George Horne walked
> north from Ross looking for satisfactory land, filed his claim, and
> received title in June 1904. He died in 1914 when my father was
> only four years old. So my father grew up without his father. Then
> my grandmother Elizabeth married a man named William Mc Raith in
> 1916, and William died two years later in 1918. So my father lost
> two fathers before he was nine years old. I think about that
> sometimes when I think about how he raised me. He was a quiet man.
> He did not tell stories the way some men do. He worked. He came
> in for breakfast and went out again. The kitchen always had the
> coal stove going in winter — that is one of my earliest real
> memories, the smell of coal and the smell of bread baking and the
> sound of the wind coming across the prairie in those long
> Dakota winters. The wind in Stanley was not a sometimes thing. It
> was the air. I remember the train coming through Stanley too. You
> could hear it a long way off and then it would come right through
> the middle of town, and we would stop and watch it. My grandmother
> Elizabeth — the one who had been twice widowed — was still alive
> when I was little. She would come around with stories about her
> family. Her family was the Shong family, and she would tell us
> the name was originally Schong with a C, and they had dropped the
> C when they came to America. Her father John Michael Shong had
> come from Lorraine, France, near a city called Nancy, around 1848,
> and after he died in 1891 letters were still coming to him in
> French from his people back in France. She said her mother
> Christine was a Bolley from Hanover, Germany, and the Bolleys had
> come over in 1850 when Christine was eight. Catholic, both sides.
> When I was very small I did not know what any of that meant. I
> just knew that the old people came from someplace called France
> and someplace called Germany and that my grandmother kept a rosary.
> The war was on for most of those years. I do not remember the war
> the way an adult remembers a war — I was two when Pearl Harbor
> happened, six when it ended — but I remember rationing in the way
> a small child remembers things. Sugar was a thing my mother was
> careful with. Coffee was a thing the grown-ups talked about. My
> father was past the draft age and he was a farmer besides, so he
> was not called up. But the radio was always on for the news and
> the grown-ups would get quiet when it came on. I remember that.
> The radio meant be quiet.

---

## CHAPTER 2 — EARLY SCHOOL YEARS

> I started school in Stanley right around the end of the war. So my
> first-grade memory is mixed up with the memory of the war ending,
> which the grown-ups talked about more than the children did. My
> sister Sharon had already been in school for a couple of years by
> then so she had the routine down. I followed her. The schoolhouse
> in Stanley was a real building, brick and wood, not a one-room
> school the way the very early prairie schools had been, though my
> father had stories about going to one of those. The walk to school
> in winter was the test. North Dakota winter is not the kind of
> winter where you put on a coat and walk to the corner. It is the
> kind of winter where my mother would check our gloves and our
> scarves and our boots before we went out the door, and even then
> you could lose feeling in your face in five minutes if the wind
> was wrong. I remember her standing at the door with my muffler in
> her hands telling me to tuck it inside the coat, not on top of
> it. Tuck it in. Tuck it in. She said that every winter morning of
> my school years. The teachers in Stanley were strict in the way
> teachers were strict then, which meant you stood up when the
> teacher spoke to you, and you did your work, and you did not
> question why. Penmanship mattered. Arithmetic mattered. They were
> not telling us to express ourselves. They were telling us to do
> our work. Some of those teachers were the kind you remember the
> rest of your life because they cared. Some were the kind you
> remember because they did not. I had both. One of the women — I
> believe her name was Mrs. Pederson, but I would not swear to that
> — used to keep a small jar of lemon drops on her desk for the
> children who got their multiplication tables right the first time
> all the way through. That was the only candy I ever got at school
> and I worked for it. I do not remember whether I ever beat all of
> them, but I remember the lemon drops. The Catholic part of life
> was on Sunday and during Lent. My grandmother Elizabeth's people
> had been Catholic since France, and my father was raised Catholic,
> and so we went. Mass was in Latin then, the old way. I did not
> understand most of it but you learned to stand up and sit down and
> kneel at the right times. The hymns were the part that stayed with
> you. After Mass my grandmother would tell us things about her
> people — about her brother Charlie who ran a hotel in Penn,
> North Dakota, about her father John Michael who had served in the
> Civil War with the 28th Infantry from February 1865 to January
> 1866 in Kansas and Missouri, about how the family had ended up in
> Fall Creek, Wisconsin before some of them came west to North
> Dakota around 1902. I did not write any of that down when I was a
> child. Nobody told me to. I wish I had. By the time I was ten or
> eleven my father had me out with him doing real work — not just
> watching him work, which is what little boys do, but actually
> doing things. Carrying. Lifting. Holding what needed to be held
> while he worked. He did not give a lot of instructions because
> he expected you to watch and figure it out. He would say one
> thing once. If you missed it, he said it once more, and that was
> the second time, and there was not going to be a third time. So
> you learned to listen. I learned to listen on that farm before I
> ever learned to listen in the Army, and I think the Army part
> later was easier because of the farm part earlier.

---

## CHAPTER 3 — LATER YEARS

> I am eighty-six now. Christmas Eve is coming around again in a few
> months, and that is a strange thing — to keep having birthdays
> and to keep noticing that the people who were there at your
> earlier ones are not all there anymore. My father Ervin died in
> 1967. My mother Leila held on until 1985. My sister Sharon is
> still here, ninety this year, married to Ed Woodmansee all this
> time. My younger sister Linda is still here too. So three of us
> made it this far, which considering the family pattern — my
> father lost his father at four — is something I do not take for
> granted. Janice and I have been married since 1959. We met in
> Bismarck, actually, at the dentist's office, of all places. She
> was working there and I was a young man with the wrong tooth
> situation, and that was that. October 10, 1959. I was nineteen,
> she was twenty. Sixty-six years married now and we still talk
> every day about something that matters. Our three sons all turned
> out. Vincent, the oldest, was born in Germany at Landstuhl. Jason
> came after that. And Christopher — Chris, our youngest — was born
> on Christmas Eve 1962 in Williston. Christmas Eve, the same as
> mine. That fact has always struck me as one of the small symmetries
> a life can hand you. He grew up to be the kind of son who built
> things you could not have predicted. He is the one who built this
> system I am talking to right now. I will not pretend I understand
> all of it. The dog right now is Ivan. He is a golden retriever
> and he is the most generous animal I have ever known. He follows
> Janice from room to room, and when she sits down he lies down at
> her feet, and when she gets up he gets up. He is not a young dog
> anymore. We are not young either. But the three of us are still
> a household, and that is what matters at the end. People ask me
> what I learned. I will tell you the honest answer. I learned
> that you have to pay attention to people while they are still
> here. My father did not tell stories. He worked. And I admired
> him for that when I was a boy because that is what a son does.
> But I wish I had asked him more. I wish I had asked him about
> his father George who died in 1914, and about his stepfather
> William who died in 1918, and about what it was like to grow up
> a boy who had buried two fathers before he was nine. I never asked
> him. He never volunteered. And then he was gone in 1967 and the
> chance was over. I would say to anyone listening — and I am
> aware this is being recorded — ask them while they are here.
> Even if they will not answer the first time, ask them again
> later. The answers are not always in the asking. Sometimes the
> answer is that they trusted you enough to be silent in front of
> you. But you can only learn that by asking. The other thing I
> would say is that I did not realize until I was old how much of
> my life was set by the train ride west to Fort Ord in 1959, and
> by choosing the missile-system path over the three-month wait for
> Army Security Agency. Those two decisions, made by a boy who did
> not know what he was choosing, ran the rest of my life. They took
> me to Germany. They put me where I met the work and the timing
> that produced Vincent. They eventually came home to North Dakota
> and the photography work and then the University of North Dakota
> and the economics degrees. None of that was planned at eighteen.
> All of it followed from being too impatient to wait three months.
> So when young people ask me about choices, I tell them that even
> the small ones become large. You will not know it at the time. You
> will not know it for years. But you find out later that the choice
> you thought was about three months was about everything.

---

## BONUS PROBE — short follow-up turn

After Lori responds to Chapter 3, paste this short turn (≤20 words) as
a closing marker. This exercises the **thread bank surfacing logic** —
under the WO §3 design, a banked thread (Ivan, Linda, Christopher,
Sharon's husband Ed, etc.) becomes eligible to surface only after a
chapter ends with a closing marker AND momentum drops out of story
mode.

> Anyway, that's about it for what I wanted to say today.

If thread bank is firing and `HORNELORE_STORY_FIRST_PHASE_1=1`, Lori
should pick ONE banked anchor (not all of them) and gently return to
it with a chapter-natural question — something like:

> Earlier you mentioned your sister Linda. I keep thinking about her —
> what was she like growing up?

If the env flag is off (default), Lori just reflects warmly without
surfacing. Either is acceptable; the failure mode would be Lori cramming
multiple banked anchors into one question.

---

## PER-CHAPTER SCORING CHECKLIST

Use the same checklist for all three chapters. Score each line PASS /
FAIL / PARTIAL.

| Check | What good looks like | What failure looks like |
|---|---|---|
| **Reflection grounded** | Lori references at least one specific anchor from the chapter (Stanley, Ervin, the train, the lemon drops, Ivan, Christmas Eve, Landstuhl, the dentist's office) | Lori says "thank you for sharing" or talks abstractly about "your childhood" / "your service" |
| **One question max** | Exactly one `?` in Lori's response | Two or more `?`s, OR multi-clause compound ("You went from X to Y, then Z, and W — what was that like?") |
| **No questionnaire interrogation** | If Lori asks anything, it's Layer 1 ("What stands out…?") or Layer 2 ("What was X like?") | Lori pivots to "What was your mother's maiden name?" / "When exactly was that?" / "Was that 1959 or 1960?" |
| **No forbidden empathy openers** | Lori reflects with specifics | "That sounds difficult," "I can imagine," "Thank you for sharing," "I'm so sorry" — see `LORI_REFLECTION_GROUNDING` spec for the forbidden list |
| **No era-label menu** | Lori never asks "What era are you talking about?" or surfaces "Earliest Years" / "Adolescence" as a menu | Lori spits a list of life-stage labels at the narrator (the May 11 Kent transcript failure) |
| **No same-anchor loop** | If "meal tickets" or "Ivan" or "the train" appears in Chapter 1, Lori does not ask about it again in Chapters 2 or 3 unless the narrator re-raised it | Same anchor question reappears 2+ times across chapters |
| **Word budget honored** | Lori's response ≤ ~90 words (oral_history cap) | Response runs 120+ words OR is a compound paragraph with multiple sub-asks |
| **Translation/refusal absent** | Lori responds in plain English to plain English | "Let me say that in English" / "I cannot answer that" / silence (the May 11 Kent transcript opener) |

---

## BACKEND SANITY GREP

After all three chapters land, from a terminal:

```bash
cd /mnt/c/Users/chris/hornelore

# Confirm oral-history posture fired on every turn
grep -c "composer.*style=oral_history" .runtime/logs/api.log

# Should be ≥ 3 (one per chapter) plus any opener turn

# Confirm reflection-grounding validator ran (will only fire if
# HORNELORE_STORY_FIRST_PHASE_1=1)
grep "reflection_not_grounded\|question_layer_ineligible" .runtime/logs/api.log

# Confirm Tier 1 extraction caught Jake's anchors
grep "extract.*accepted=" .runtime/logs/api.log | tail -20

# Sanity check that the May 11 meal-tickets loop pattern is GONE
grep "meal tickets" .runtime/logs/api.log
# (should return only the literal text from Jake's chapter — Lori
# herself should NOT have written "meal tickets" in any output)
```

---

## EXPECTED EXTRACTION SHAPE

The Shadow Review panel should pick up at least the following from
across the three chapters, via the legacy `family_truth_rows` pipeline
(this is independent of Phase 1):

| Field | Expected value |
|---|---|
| `personal.dateOfBirth` | 1939-12-24 |
| `personal.placeOfBirth` | Stanley, North Dakota |
| `parents.firstName` (father) | Ervin |
| `parents.lastName` (father) | Horne |
| `parents.firstName` (mother) | Leila |
| `parents.middleName` (mother) | Myrtle |
| `parents.maidenName` (mother) | Carkuff |
| `siblings.firstName` ×2 | Sharon, Linda |
| `siblings.birthOrder` ×3 | 1 (Sharon), 2 (Jake), 3 (Linda) |
| `grandparents.firstName` (paternal-paternal) | George, Elizabeth |
| `grandparents.ancestry` | French / German / Catholic |
| `spouse.firstName` | Janice |
| `marriage.year` | 1959 |
| `children.firstName` ×3 | Vincent, Jason, Christopher |
| `military.branch` | Army |
| `military.locations` | Fort Ord, Germany, Landstuhl |
| `pets.name` | Ivan |
| `pets.species` | dog |
| `pets.breed` | golden retriever |

Anything beyond those is bonus. Missing 2-3 of those is acceptable
(extraction is probabilistic). Missing 8+ is a regression.

---

## WHAT TO REPORT BACK

After all three chapters + the bonus probe land:

1. Paste each of Lori's three responses verbatim
2. Per-chapter scoring (the checklist above)
3. Final api.log grep output
4. Any narrator-visible weirdness (UI glitch, wrong attribution, era
   confabulation, etc.)
5. Subjective read: did this feel like talking to a system that wanted
   to hear the chapter, or did it feel like the May 11 transcript with
   Kent?

The subjective read is the load-bearing judgment. Everything else is
diagnostic.
