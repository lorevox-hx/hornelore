# TEST-23 Two-Person Resume Canary — `test23_v5`

- started: 2026-05-05T07:23:28
- finished: 2026-05-05T07:56:20
- commit: `94bf76f` dirty=False
- base_url: http://localhost:8082/ui/hornelore1.0.html
- api_base: http://localhost:8000

## Topline: **RED**

- Mary Holts (messy): **RED**
- Marvin Mann (clean): **RED**

### Final failures
- Mary RED
- Marvin RED

## Mary Holts (TEST-23) (`mary`) — **RED**

- person_id: `3d59a9df-dcd0-47c7-a1d7-85d328777007`

### Onboarding

| Step | Sent | Reply (excerpt) | Severity | Elapsed |
|---|---|---|---|---:|
| onboard_name | `mary Holts` | …mary, it's wonderful to meet you and start this project together. Now, I'd love… | PASS | 28459ms |
| onboard_dob | `2/29 1940` | …That's a unique birthday, mary. February 29th, 1940. Now, I'd love to help plac… | PASS | 22891ms |
| onboard_pob | `Minot ND` | …You can turn it on or off at any time. Now, do you have any questions about our… | PASS | 39652ms |
| onboard_pob_correction | `Actually it's Minot, North Dakota — not just ND` | Minot, North Dakota, is where you were born. I'll make sure to use the full name… | PASS | 24618ms |

**BB state after onboarding:**

- firstName: `None` (expected `'Mary'`)
- lastName: `None` (expected `'Holts'`)
- DOB: `None` (expected `'1940-02-29'`)
- POB: `None` (expected `'Minot, North Dakota'`)
- basics_complete: `True`

### Early inference probes (right after onboarding)

**early_age_guess:** sent=`How old do you think I am?` reply=`Based on our conversation, I believe you were born in 1940, which would make you currently around 86 years old. Am I close?` severity=PASS
  - text_elapsed=8154ms tts_wait=10383ms tts_done=True
  - age guess hit (expected=86, found=[86])

**early_residence_guess:** sent=`Where do you think I live now?` reply=`We haven't discussed your current residence yet, mary. Let's start by exploring your earliest years. What do you remember about living in Minot, North Dakota, during that time?` severity=AMBER
  - text_elapsed=9000ms tts_wait=13875ms tts_done=True
  - residence: name dropped POB without 'born in' framing (ambiguous)

### Life Map walk

| Era | Click log | Era set | Reply (excerpt) | Anchored | Severity |
|---|---|---|---|---|---|
| Earliest Years (earliest_years) | ✓ | earliest_years | Being born during a storm must have been a memorable and perhaps inten… | ✓ | PASS |
| Early School Years (early_school_years) | ✓ | early_school_years | Walking to school with your brother through the snow must have made th… | ✓ | PASS |
| Adolescence (adolescence) | ✓ | adolescence | Learning that distinction at a young age can be a valuable lesson. Wha… | ✗ | AMBER |
| Coming of Age (coming_of_age) | ✓ | coming_of_age | It sounds like you formed a connection with your future husband at the… | ✓ | PASS |
| Building Years (building_years) | ✓ | building_years | How did you balance your own interests with being a mother and moving … | ✗ | AMBER |
| Later Years (later_years) | ✓ | later_years | Those must have been difficult and profound changes for you. How did b… | ✗ | AMBER |

**Mid-stream extras (correction / ambiguity probes):**

- **Building Years** sent=`Actually we only had two kids, not three.`
  reply=`How did you balance your own interests with being a mother and moving to new places?`
  handled_well=False

### Today cycles + factual interruption

**Today cycle 1:** sent=`These days I take things slower. I like sitting by the windo` reply=`It sounds like you've found a peaceful rhythm in your life these days. As you sit by the window in the morning, what do …` severity=PASS

**Today cycle 2:** sent=`I still think about everything that came before, but I try t` reply=`It can be both comforting and challenging to reflect on the past while also staying present. How do you balance those tw…` severity=AMBER

**Today factual ('what day is it'):** reply=`Today is Tuesday, May 5, 2026. Would you like to continue talking about your day or revisit something from earlier in our conversation?` severity=PASS
  - text_elapsed=6927ms tts_wait=11250ms tts_done=True

### Late-stage age probe (after Life Map walk + Today)

sent=`How old do you think I am now?` reply=`Today is Tuesday, May 5, 2026. Would you like to continue talking about your day or revisit something from earlier in our conversation?` severity=RED
  - text_elapsed=3253ms tts_wait=12220ms tts_done=True
  - late age miss (expected=86)
  - REGRESSION: early probe got age right; late probe missed

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
| onboard | extract_attempts=1, extract_summary=1, fk_constraint=4, story_trigger=1, utterance_frame=1 |
| early_inference | extract_attempts=2, extract_summary=2, fk_constraint=1, story_trigger=1, utterance_frame=1 |
| lifemap | extract_attempts=7, extract_summary=6, fk_constraint=13, story_trigger=7, utterance_frame=7 |
| today | extract_attempts=3, extract_summary=4, fk_constraint=4, story_trigger=3, utterance_frame=3 |
| late_age | extract_attempts=1, extract_summary=1, fk_constraint=1, story_trigger=1, utterance_frame=1 |
| recall_pre | extract_attempts=1, extract_summary=1, fk_constraint=2, story_trigger=1, utterance_frame=1 |
| resume | (none) |

## Marvin Mann (TEST-23) (`marvin`) — **RED**

- person_id: `5843e9d8-6c98-4d85-b28b-981aee6335fd`

### Onboarding

| Step | Sent | Reply (excerpt) | Severity | Elapsed |
|---|---|---|---|---:|
| onboard_name | `Marvin Mann` | …Nice to meet you, Marvin Mann! Now that we've got your name down, can you tell … | PASS | 29313ms |
| onboard_dob | `December 6, 1949` | …Marvin, great – December 6, 1949 is a wonderful starting point for your story. … | PASS | 23126ms |
| onboard_pob | `Fargo, North Dakota` | …Type - whichever feels more natural for you. I can also hear you just fine if y… | PASS | 45659ms |
| status_seed | `I am a widower now, I still think about my wife ev` | Marvin, that's beautiful. I can sense the love and affection you still hold for … | PASS | 25091ms |

**BB state after onboarding:**

- firstName: `None` (expected `'Marvin'`)
- lastName: `None` (expected `'Mann'`)
- DOB: `None` (expected `'1949-12-06'`)
- POB: `None` (expected `'Fargo, North Dakota'`)
- basics_complete: `True`

### Early inference probes (right after onboarding)

**early_age_guess:** sent=`How old do you think I am?` reply=`Well, let's see... since you were born in 1949, that makes you around 77 years young! Would you like to tell me a bit more about growing up in Fargo, where you were born?` severity=PASS
  - text_elapsed=8964ms tts_wait=13809ms tts_done=True
  - age guess hit (expected=76, found=[77])

**early_residence_guess:** sent=`Where do you think I live now?` reply=`Let's go back to where we were. Last time we were talking about your life in Fargo. Shall we continue there?` severity=AMBER
  - text_elapsed=6532ms tts_wait=8803ms tts_done=True
  - residence: name dropped POB without 'born in' framing (ambiguous)

### Life Map walk

| Era | Click log | Era set | Reply (excerpt) | Anchored | Severity |
|---|---|---|---|---|---|
| Earliest Years (earliest_years) | ✓ | earliest_years | Marvin, that's a lovely image – a warm kitchen in the winter sounds li… | ✓ | PASS |
| Early School Years (early_school_years) | ✓ | early_school_years | Marvin, arithmetic in school was something you enjoyed, but reading ou… | ✓ | PASS |
| Adolescence (adolescence) | ✓ | adolescence | Working after school and saving for a pickup truck - that shows initia… | ✓ | PASS |
| Coming of Age (coming_of_age) | ✓ | coming_of_age | How did you handle the new responsibilities? | ✗ | AMBER |
| Building Years (building_years) | ✓ | building_years | That sounds like a beautiful foundation for a life together. What do y… | ✓ | PASS |
| Later Years (later_years) | ✓ | later_years | How did you navigate that difficult time? | ✗ | AMBER |

**Mid-stream extras (correction / ambiguity probes):**

- **Adolescence** sent=`I think that was around 1965… or maybe a little later.`
  reply=`Working after school and saving for a pickup truck - that shows initiative and responsibility, Marvin. What do you remember about the daily routine or life as a teenager, balancing school and your par`
  handled_well=True

### Today cycles + factual interruption

**Today cycle 1:** sent=`Today I keep a simple routine. Coffee, a short walk, and a l` reply=`It sounds like you've found some comfort in those quiet moments. What does life look like for you these days - where are…` severity=PASS

**Today cycle 2:** sent=`I still miss my wife, but I try to notice small good things ` reply=`That's a beautiful approach, Marvin. What are some of those small good things that bring a smile to your face every day?` severity=AMBER

**Today factual ('what day is it'):** reply=`That's a beautiful approach, Marvin. What are some of those small good things that bring a smile to your face every day?` severity=PASS
  - text_elapsed=14309ms tts_wait=7234ms tts_done=True

### Late-stage age probe (after Life Map walk + Today)

sent=`How old do you think I am now?` reply=`Marvin, since we've discussed your birthdate earlier, I think you're around 77 years young! Would you like to talk more about what it's like being in your current life stage?` severity=PASS
  - text_elapsed=8985ms tts_wait=11984ms tts_done=True
  - late age hit (expected=76, found=[77])
  - consistent age across probes: {77}

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

sent=`What do you remember about my wife?` reply=`Marvin, you've shared that you still think about your wife every morning and that you keep some of her letters in the top drawer of your desk. She sounds like a very special person in your life. Would` severity=PASS
  - text_elapsed=10578ms tts_wait=19335ms tts_done=True
  - spouse tokens hit: ['wife', 'letters', 'drawer', 'morning']/['wife', 'widower', 'letters', 'drawer', 'morning']
  - emotional anchoring intact (≥2 spouse tokens recalled)

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

- reply: `Today's date is Tuesday, May 5, 2026. Now, let's get back to your story. You were saying...`
- severity: **PASS**

### api.log signal counts per phase

| Phase | Signals |
|---|---|
| onboard | extract_attempts=1, fk_constraint=4, story_trigger=1, utterance_frame=1 |
| early_inference | extract_attempts=2, extract_summary=2, fk_constraint=1, story_trigger=1, utterance_frame=1 |
| lifemap | extract_attempts=7, extract_summary=6, fk_constraint=13, story_trigger=7, utterance_frame=7 |
| today | extract_attempts=3, extract_summary=3, fk_constraint=4, story_trigger=3, utterance_frame=3 |
| late_age | extract_attempts=1, extract_summary=1 |
| recall_pre | extract_attempts=1, extract_summary=1, fk_constraint=2, story_trigger=1, utterance_frame=1 |
| spouse_probe | extract_attempts=1, extract_summary=1 |
| resume | extract_attempts=1, extract_summary=1, fk_constraint=2, story_trigger=1, utterance_frame=1 |

## Stress Telemetry (WO-OPS-STRESS-TELEMETRY-KV-01)

- snapshots captured: **19**
- kv-clear calls: **1**
