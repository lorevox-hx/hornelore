# WO-QB-GENERATIONAL — Era-Anchored Generational Memory Questions

**Status:** Draft  
**Depends on:** WO-LIFE-SPINE-05 (question bank v3), WO-QB-MASTER-EVAL-01  
**Target narrators:** Baby Boomers (born 1946–1964), with framework extensible to Silent Generation  

---

## Problem

The current question bank (252 questions across 5 phases) is biographically thorough but generationally generic. It asks about career peaks, retirement, and family structure — universal life events that apply to anyone born in any decade. What it does not do is anchor the narrator's life to the shared cultural seismic events that defined their generation.

For the Horne family narrators (Janice, Kent, Christopher), these touchstones are the scaffolding of memory: where were you when man landed on the moon, did anyone in your family go to Vietnam, what was your first computer, what did COVID do to your daily life. These aren't extractable facts in the traditional schema sense — they're **memory triggers** that unlock stories the biographical questions never reach.

The current bank also underserves the **present-tense elder experience**: medications, memory changes, frustrations with aging, things they still want to do, stories they specifically want told. These are the questions that matter most to a memoir platform and the ones narrators are least likely to volunteer without a direct, warm invitation.

## Goals

1. Add a new sub-topic layer of **era-anchored touchstone questions** that Lori can weave into any phase where the narrator was alive and aware during the event.
2. Add a **late-life reflection** sub-topic covering health realities, cognitive changes, frustrations, and desired stories — the things a Boomer in their 60s–80s actually thinks about.
3. Key all touchstone questions to the narrator's **birth decade** so Lori never asks a 1948-born narrator about experiencing the Korean War as an adult (they were 5) or skips Vietnam (they were draft age).
4. Integrate with the existing `historical_events_1900_2026.json` seed file so the chronology accordion and the question composer share the same event vocabulary.
5. Ensure every touchstone question maps to at least one **extractable field** so responses feed the memoir, not just conversation.

## Design

### A. Touchstone Question Sets (by era band)

Each touchstone question is tied to a cultural event or shift. Lori selects from these when the narrator's age at the event falls within the "awareness window" (roughly age 8+ for passive awareness, age 14+ for active participation/opinion).

#### Childhood Awareness (narrator was 5–12 during event)

These are "what do you remember hearing about" questions — the narrator was a child, so framing is secondhand/environmental.

| Event cluster | Years | Sample question | Extract target |
|---|---|---|---|
| Korean War aftermath | 1950–1953 | "Did anyone in your family talk about Korea when you were small?" | `military.significantEvent` |
| Polio scare / Salk vaccine | 1952–1955 | "Do you remember getting the polio vaccine — or your parents' relief when it came?" | `health.milestone` |
| First TV in the house | 1950s | "Do you remember the first television set in your home — what show was on?" | `laterYears.significantEvent` |
| Sputnik / space race begins | 1957 | "When Sputnik went up, did anyone in your house talk about it?" | `laterYears.significantEvent` |

#### Adolescent Awareness (narrator was 13–18)

Active memory, emerging opinions, peer influence. "Where were you when" framing works here.

| Event cluster | Years | Sample question | Extract target |
|---|---|---|---|
| JFK assassination | 1963 | "Where were you when you heard President Kennedy had been shot?" | `laterYears.significantEvent` |
| Beatles / British Invasion | 1964 | "Did the Beatles matter to you — or was that someone else's thing?" | `hobbies.hobbies` |
| Vietnam draft begins | 1965–1969 | "When the draft numbers started, did it touch your family directly?" | `military.branch`, `military.significantEvent` |
| Moon landing | 1969 | "Where were you the night they landed on the moon — who were you watching with?" | `laterYears.significantEvent` |
| Woodstock / counterculture | 1969 | "Was the counterculture something you saw up close, or something on the news?" | `laterYears.significantEvent` |
| Civil rights movement | 1960s | "What do you remember about the civil rights movement as it was happening around you?" | `laterYears.significantEvent` |

#### Young Adult Awareness (narrator was 19–35)

Direct participation, career/family impact, strong opinions.

| Event cluster | Years | Sample question | Extract target |
|---|---|---|---|
| Vietnam War / Cambodia | 1965–1975 | "Did you serve, or did someone close to you? What was that like at home?" | `military.branch`, `military.yearsOfService`, `military.deploymentLocation` |
| Nixon / Watergate | 1972–1974 | "Do you remember watching the Watergate hearings — what did you think?" | `laterYears.significantEvent` |
| Oil crisis / gas lines | 1973 | "What did the gas shortage look like in your town — did it change how you drove?" | `laterYears.significantEvent` |
| First personal computer | 1977–1984 | "When did a computer first show up in your life — at work, at home, at a friend's?" | `laterYears.significantEvent` |
| MTV launches | 1981 | "Do you remember MTV starting up — did it change anything for you?" | `hobbies.hobbies` |
| Challenger disaster | 1986 | "Where were you when the Challenger went down?" | `laterYears.significantEvent` |
| Berlin Wall falls | 1989 | "When the Wall came down, what did you think — did it feel like the world changed?" | `laterYears.significantEvent` |

#### Midlife Awareness (narrator was 36–60)

Established perspective, parenting lens, economic impact.

| Event cluster | Years | Sample question | Extract target |
|---|---|---|---|
| First cell phone | 1990s | "When did you get your first cell phone — and what did you think of it?" | `laterYears.significantEvent` |
| Internet arrives | 1993–1998 | "When did the internet first come into your house — what did you use it for?" | `laterYears.significantEvent` |
| Oklahoma City bombing | 1995 | "Do you remember hearing about Oklahoma City — what went through your mind?" | `laterYears.significantEvent` |
| 9/11 | 2001 | "Where were you on September 11th — and what did the days after feel like?" | `laterYears.significantEvent` |
| Iraq War | 2003 | "Did the Iraq War touch your family, or was it something you watched from a distance?" | `military.significantEvent` |
| iPhone / smartphone era | 2007 | "When did you get your first smartphone — and how did it change your daily life?" | `laterYears.significantEvent` |
| Great Recession | 2008 | "Did the 2008 crash hit your family — a job, a house, retirement savings?" | `laterYears.significantEvent` |

#### Elder Awareness (narrator is 61+)

Witnessed as a grandparent/retiree, through the lens of legacy.

| Event cluster | Years | Sample question | Extract target |
|---|---|---|---|
| COVID-19 pandemic | 2020 | "What did COVID do to your daily life — and what did you miss the most?" | `health.lifestyleChange`, `laterYears.significantEvent` |
| COVID isolation | 2020–2021 | "Were you separated from family during COVID? How did you stay connected?" | `laterYears.significantEvent` |
| Generative AI | 2023 | "Have you heard about AI writing and talking — what do you make of it?" | `laterYears.significantEvent` |
| Artemis / return to Moon | 2025–2026 | "They're going back to the moon now — does that feel different from the first time?" | `laterYears.significantEvent` |

### B. Late-Life Reflection Sub-topic

A new sub-topic within `legacy_reflection` called **`present_life_realities`**. This is the "how are you right now" layer — the questions a memoir interviewer asks that a family member is too polite to.

```json
"present_life_realities": {
  "label": "Present life realities",
  "intent": "The narrator's current daily experience — health, cognition, frustrations, joys, and the stories they specifically want told before it's too late.",
  "extract_priority": [
    "health.majorCondition",
    "health.lifestyleChange",
    "laterYears.lifeLessons",
    "additionalNotes.unfinishedDreams"
  ],
  "questions": [
    "Do you take medications every day now — and is there one that changed your life for the better?",
    "Has your memory changed in a way you've noticed? What's the first thing that felt different?",
    "What frustrates you most about getting older — the thing nobody warned you about?",
    "Is there a story you've been carrying that you want on the record — one you haven't told yet?",
    "What part of your daily routine now would surprise your thirty-year-old self?",
    "Is there a place you can't get to anymore that you wish you could visit one more time?",
    "What do you want your grandchildren to understand about what it's like to be your age?",
    "If Lori could write down just one more story from your life, which one would you pick?"
  ],
  "follow_ups": [
    "When did that start?",
    "Who helps you with that?",
    "What do you do on a day when it's hard?",
    "Is there something that makes it better?",
    "What would you want written about that?"
  ],
  "sensory_prompts": [
    "What does your morning sound like now — is it quiet?",
    "What's the first thing you see when you wake up?",
    "Is there a smell in your house that would surprise a visitor?"
  ]
}
```

### C. New Extractable Fields (proposed)

The current schema routes most touchstone responses to `laterYears.significantEvent`, which becomes a catch-all. Proposed additions to `EXTRACTABLE_FIELDS`:

| Field path | Label | writeMode | Notes |
|---|---|---|---|
| `cultural.touchstoneMemory` | "Where-were-you memory tied to a historical event" | `suggest_only`, `repeatable: "cultural"` | Links to `historical_events` by event ID |
| `health.currentMedications` | "Current medications or treatments" | `suggest_only` | Sensitive — must_not_write guard if narrator declines |
| `health.cognitiveChange` | "Self-reported memory or cognitive change" | `suggest_only` | Sensitive — must_not_write guard if narrator declines |
| `laterYears.dailyRoutine` | "Current daily routine or lifestyle" | `suggest_only` | |
| `laterYears.desiredStory` | "Story the narrator specifically wants told" | `suggest_only`, `repeatable: "laterYears"` | High-priority for memoir arc |

### D. Integration with Question Composer

The touchstone questions are selected by the phase-aware composer using this logic:

1. Composer knows the narrator's `dateOfBirth` (from promoted truth).
2. For each touchstone event, compute `narrator_age_at_event = event.year - birth_year`.
3. Select the appropriate awareness band (childhood 5–12, adolescent 13–18, young adult 19–35, midlife 36–60, elder 61+).
4. Pick the question variant that matches the awareness band.
5. Touchstone questions are **interleaved** with biographical questions, not front-loaded. Suggested ratio: 1 touchstone question per 4–5 biographical questions, introduced after the narrator's basic identity is established (Phase 1 complete).

### E. Integration with Historical Events Seed

Each touchstone question entry should carry an `event_ref` field that maps to an `id` in `historical_events_1900_2026.json`. This allows:

- The chronology accordion UI to highlight events the narrator has responded to.
- The extraction pipeline to tag `cultural.touchstoneMemory` items with the event ID for timeline placement.
- Future filtering: "show me all the events this narrator actually remembers."

### F. Guard Considerations

- **Topic refusal**: Touchstone questions about war, trauma, and health are high-refusal-risk. The guard stack must treat "I don't want to talk about that" as a topic refusal (suppress the field), not a negation (don't extract "did not serve").
- **Sensitive health fields**: `health.currentMedications` and `health.cognitiveChange` must have must_not_write guards if the narrator declines or deflects. These are the most sensitive fields in the schema.
- **Vietnam/military special case**: If the narrator says "I didn't serve" that IS a factual negation and should NOT be extracted as `military.branch`. But if they say "my brother served," that's a different-subject extraction (brother, not narrator) and the subject filter must catch it.

## Implementation Steps

1. **Add `present_life_realities` sub-topic** to `question_bank.json` under `legacy_reflection` (8 questions, 5 follow-ups, 3 sensory prompts).
2. **Create `touchstone_questions.json`** — a new companion file with the era-banded touchstone question sets, each entry carrying `event_ref`, `awareness_band`, `age_range`, and `extract_priority`.
3. **Add new extractable fields** to `EXTRACTABLE_FIELDS` in `extract.py`: `cultural.touchstoneMemory`, `health.currentMedications`, `health.cognitiveChange`, `laterYears.dailyRoutine`, `laterYears.desiredStory`.
4. **Update the extraction prompt** with few-shot examples for touchstone responses (narrator says "I was 21 when they landed on the moon, watching with my dad in the living room" → extract `cultural.touchstoneMemory` with event_ref `apollo_lands_humans_moon_1969`).
5. **Wire the question composer** to select touchstone questions based on narrator birth year and current phase position.
6. **Add must_not_write guards** for `health.currentMedications` and `health.cognitiveChange` — these fire on topic refusal, not just negation.
7. **Write 10–15 eval cases** covering touchstone extraction, health-field sensitivity, and refusal handling.
8. **Update the chronology accordion** to highlight events with narrator responses.

## Eval Cases Needed

- Touchstone response → correct `cultural.touchstoneMemory` extraction with event_ref
- Touchstone response mentioning another person ("my brother went to Vietnam") → subject filter blocks narrator extraction
- Health disclosure ("I take blood pressure medication") → `health.currentMedications`
- Health refusal ("I'd rather not go into my health") → must_not_write fires, no health fields extracted
- Memory change acknowledgment ("my memory isn't what it was") → `health.cognitiveChange`
- Memory change refusal → must_not_write
- Desired story ("I want to tell about the time we drove to Alaska") → `laterYears.desiredStory`
- Multi-touchstone response covering two events in one turn

## Priority

High. The Horne narrators are Boomers in the legacy_reflection phase. Every interview session without these questions is a missed opportunity to capture the generational memories that make a memoir feel like a life, not a personnel file.

---

*WO-QB-GENERATIONAL — drafted 2026-04-18*
