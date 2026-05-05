# TEST-23 Two-Person Resume Canary — `test23_v3`

- started: 2026-05-04T20:08:52
- finished: 2026-05-04T20:43:19
- commit: `7168cdc` dirty=False
- base_url: http://localhost:8082/ui/hornelore1.0.html
- api_base: http://localhost:8000

## Topline: **RED**

- Mary Holts (messy): **RED**
- Marvin Mann (clean): **RED**

### Final failures
- Mary RED
- Marvin RED

## Mary Holts (TEST-23) (`mary`) — **RED**

- person_id: `093b75bf-44b1-4033-a466-375a730816b4`

### Onboarding

| Step | Sent | Reply (excerpt) | Severity | Elapsed |
|---|---|---|---|---:|
| onboard_name | `mary Holts` | …It's so great to meet you, mary. Knowing your date of birth will help me place … | PASS | 28608ms |
| onboard_dob | `2/29 1940` | …That's a lovely birthday, mary. February 29th, 1940, is a unique day to celebra… | PASS | 27384ms |
| onboard_pob | `Minot ND` | …Minot, North Dakota, is a beautiful place to start your story, mary. Now, befor… | PASS | 44183ms |
| onboard_pob_correction | `Actually it's Minot, North Dakota — not just ND` | Are you ready to begin sharing your story? | PASS | 13216ms |

**BB state after onboarding:**

- firstName: `None` (expected `'Mary'`)
- lastName: `None` (expected `'Holts'`)
- DOB: `None` (expected `'1940-02-29'`)
- POB: `None` (expected `'Minot, North Dakota'`)
- basics_complete: `True`

### Early inference probes (right after onboarding)

**early_age_guess:** sent=`How old do you think I am?` reply=`Are you ready to begin sharing your story?` severity=AMBER
  - text_elapsed=7754ms tts_wait=11294ms tts_done=True
  - age guess miss (expected=86)

**early_residence_guess:** sent=`Where do you think I live now?` reply=`Last time we were talking about your childhood. Shall we continue there?` severity=AMBER
  - text_elapsed=6936ms tts_wait=5683ms tts_done=True
  - residence: ambiguous response (review manually)

### Life Map walk

| Era | Click log | Era set | Reply (excerpt) | Anchored | Severity |
|---|---|---|---|---|---|
| Earliest Years (earliest_years) | ✓ | earliest_years | Perhaps the house where you were born? | ✓ | PASS |
| Early School Years (early_school_years) | ✓ | early_school_years | That's a vivid image, mary. We walked to school, me and my brother, th… | ✓ | PASS |
| Adolescence (adolescence) | ✓ | adolescence | That's a wise observation, mary. I learned early on there were things … | ✓ | PASS |
| Coming of Age (coming_of_age) | ✓ | coming_of_age | That's a lovely start to a story, mary. Meeting someone at a county fa… | ✓ | PASS |
| Building Years (building_years) | ✓ | building_years | Having children and moving around for his work must have brought many … | ✓ | AMBER |
| Later Years (later_years) | ✓ | later_years | It's natural that the house might feel quieter after a loved one passe… | ✓ | PASS |

**Mid-stream extras (correction / ambiguity probes):**

- **Building Years** sent=`Actually we only had two kids, not three.`
  reply=`Having children and moving around for his work must have brought many changes to your life. We had kids and moved around a bit for his work. Those years went fast.`
  handled_well=False

### Today cycles + factual interruption

**Today cycle 1:** sent=`These days I take things slower. I like sitting by the windo` reply=`There's something lovely about taking time to appreciate the simple things, like sitting by the window in the morning. W…` severity=AMBER

**Today cycle 2:** sent=`I still think about everything that came before, but I try t` reply=`There's something lovely about taking time to appreciate the simple things, like sitting by the window in the morning. W…` severity=AMBER

**Today factual ('what day is it'):** reply=`It sounds like you're finding a way to balance looking back with living in the present. That's a beautiful approach, mary. How do you find that sitting by the window in the morning helps you with that` severity=PASS
  - text_elapsed=1224ms tts_wait=16703ms tts_done=True

### Late-stage age probe (after Life Map walk + Today)

sent=`How old do you think I am now?` reply=`It's Monday, May 4th, according to your device clock. Now, where were we?` severity=AMBER
  - text_elapsed=1626ms tts_wait=9130ms tts_done=True
  - late age miss (expected=86)

### Pre-restart memory recall (Earliest Years anchor + 'what do you know about me')

- name recalled: True
- DOB/year recalled: True
- POB recalled: True
- era facts recalled: 0/7
- cross-contamination: False
- onboarding restart: False
- severity: **AMBER**

Reply excerpt: `What I know about mary so far:

Identity
- Name: mary
- Date of birth: 1940-01-01
- Place of birth: Minot ND

Family
- Parents: (none on record yet)
- Siblings: (none on record yet)

Notes from our co`

### Post-restart memory recall (after browser context reopen)

- name recalled: False
- DOB/year recalled: False
- POB recalled: False
- era facts recalled: 0/7
- cross-contamination: False
- onboarding restart: False
- severity: **RED**

Reply excerpt: ``

### Today after resume ('what day is it')

- reply: ``
- severity: **RED**

### api.log signal counts per phase

| Phase | Signals |
|---|---|
| onboard | extract_attempts=1, fk_constraint=4, story_trigger=1, utterance_frame=1 |
| early_inference | extract_attempts=2, extract_summary=1, fk_constraint=2, story_trigger=1, utterance_frame=1 |
| lifemap | extract_attempts=7, extract_summary=6, fk_constraint=13, story_trigger=7, utterance_frame=7 |
| today | extract_attempts=3, extract_summary=2, fk_constraint=3, story_trigger=3, utterance_frame=3 |
| late_age | extract_attempts=1 |
| recall_pre | extract_attempts=1, extract_summary=1, fk_constraint=2, memory_echo=1, story_trigger=1, utterance_frame=1 |
| resume | (none) |

## Marvin Mann (TEST-23) (`marvin`) — **RED**

- person_id: `072d4b4a-c81e-4dca-aee1-311b976aa00f`

### Onboarding

| Step | Sent | Reply (excerpt) | Severity | Elapsed |
|---|---|---|---|---:|
| onboard_name | `Marvin Mann` | …Hello Marvin Mann, it's lovely to meet you. Now, to get started on building you… | PASS | 35312ms |
| onboard_dob | `December 6, 1949` | …A region that you remember fondly? | PASS | 14463ms |
| onboard_pob | `Fargo, North Dakota` | …Fargo, North Dakota, is a wonderful place to start your story. Now, before we g… | PASS | 46798ms |
| status_seed | `I am a widower now, I still think about my wife ev` | Losing a loved one is never easy, and it's clear that your wife meant a great de… | PASS | 20829ms |

**BB state after onboarding:**

- firstName: `None` (expected `'Marvin'`)
- lastName: `None` (expected `'Mann'`)
- DOB: `None` (expected `'1949-12-06'`)
- POB: `None` (expected `'Fargo, North Dakota'`)
- basics_complete: `True`

### Early inference probes (right after onboarding)

**early_age_guess:** sent=`How old do you think I am?` reply=`Based on the information you shared earlier, you were born on December 6, 1949. Would you like me to calculate your current age?` severity=AMBER
  - text_elapsed=13880ms tts_wait=10341ms tts_done=True
  - age guess miss (expected=76)

**early_residence_guess:** sent=`Where do you think I live now?` reply=`Based on the information you shared earlier, you were born on December 6, 1949. Would you like me to calculate your current age?` severity=AMBER
  - text_elapsed=5293ms tts_wait=13495ms tts_done=True
  - residence: ambiguous response (review manually)

### Life Map walk

| Era | Click log | Era set | Reply (excerpt) | Anchored | Severity |
|---|---|---|---|---|---|
| Earliest Years (earliest_years) | ✓ | earliest_years | That small house with a warm kitchen in the winter sounds like a cozy … | ✓ | PASS |
| Early School Years (early_school_years) | ✓ | early_school_years | Arithmetic was a subject that stood out to you. That small house with … | ✓ | PASS |
| Adolescence (adolescence) | ✓ | adolescence | Working after school and saving for a car as a teenager is a great way… | ✓ | PASS |
| Coming of Age (coming_of_age) | ✓ | coming_of_age | Leaving home for that first steady job marked a significant transition… | ✓ | PASS |
| Building Years (building_years) | ✓ | building_years | It sounds like you and your wife had a beautiful partnership and built… | ✓ | PASS |
| Later Years (later_years) | ✓ | later_years | How did you cope with the loss? | ✓ | PASS |

**Mid-stream extras (correction / ambiguity probes):**

- **Adolescence** sent=`I think that was around 1965… or maybe a little later.`
  reply=`Working after school and saving for a car as a teenager is a great way to develop responsibility and independence. What do you remember about your family's reaction to your decision to work and start `
  handled_well=True

### Today cycles + factual interruption

**Today cycle 1:** sent=`Today I keep a simple routine. Coffee, a short walk, and a l` reply=`` severity=RED

**Today cycle 2:** sent=`I still miss my wife, but I try to notice small good things ` reply=`It's beautiful that you're finding ways to honor your wife's memory and cultivate gratitude amidst your grief. What do y…` severity=AMBER

**Today factual ('what day is it'):** reply=`It's beautiful that you're finding ways to honor your wife's memory and cultivate gratitude amidst your grief. What do you think is the most important lesson or value that she taught you during your l` severity=PASS
  - text_elapsed=6535ms tts_wait=10961ms tts_done=True

### Late-stage age probe (after Life Map walk + Today)

sent=`How old do you think I am now?` reply=`Today is Monday, May 4, 2026. Shall we continue where we left off?` severity=AMBER
  - text_elapsed=3667ms tts_wait=16345ms tts_done=True
  - late age miss (expected=76)

### Pre-restart memory recall (Earliest Years anchor + 'what do you know about me')

- name recalled: False
- DOB/year recalled: False
- POB recalled: False
- era facts recalled: 0/7
- cross-contamination: False
- onboarding restart: False
- severity: **RED**

Reply excerpt: ``

### Spouse memory probe (Marvin only — emotional anchoring + attribution)

sent=`What do you remember about my wife?` reply=`You've mentioned your wife in our conversation before. She was a loving partner who built a life with you, and you miss her dearly. You also mentioned that she passed away, and that's been a difficult` severity=AMBER
  - text_elapsed=11814ms tts_wait=19420ms tts_done=True
  - spouse tokens hit: ['wife']/['wife', 'widower', 'letters', 'drawer', 'morning']
  - partial recall (1 spouse token)

### Post-restart memory recall (after browser context reopen)

- name recalled: True
- DOB/year recalled: False
- POB recalled: False
- era facts recalled: 0/7
- cross-contamination: False
- onboarding restart: False
- severity: **AMBER**

Reply excerpt: `Hello Marvin, nice to meet you! It's great to start our conversation today. Before we begin, I wanted to let you know that I'm here to listen and help you share your life story. Since you asked 'hello`

### Today after resume ('what day is it')

- reply: `It's Monday, May 4th, 2026. Let's get started on sharing your life story. Can you tell me a bit about where you live now?`
- severity: **PASS**

### api.log signal counts per phase

| Phase | Signals |
|---|---|
| onboard | extract_attempts=1, fk_constraint=4, story_trigger=1, utterance_frame=1 |
| early_inference | extract_attempts=2, extract_summary=3, fk_constraint=1, story_trigger=1, utterance_frame=1 |
| lifemap | extract_attempts=7, extract_summary=6, fk_constraint=13, story_trigger=7, utterance_frame=7 |
| today | extract_attempts=3, extract_summary=4, fk_constraint=4, story_trigger=3, utterance_frame=3 |
| late_age | extract_attempts=1, extract_summary=1, fk_constraint=1 |
| recall_pre | extract_attempts=1, extract_summary=1, fk_constraint=2, memory_echo=1, story_trigger=1, utterance_frame=1 |
| spouse_probe | extract_attempts=1, extract_summary=1 |
| resume | extract_attempts=2, extract_summary=2, fk_constraint=3, story_trigger=2, utterance_frame=2 |

## Stress Telemetry (WO-OPS-STRESS-TELEMETRY-KV-01)

- snapshots captured: **19**
- kv-clear calls: **1**
