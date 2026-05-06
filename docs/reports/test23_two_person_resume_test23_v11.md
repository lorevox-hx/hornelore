# TEST-23 Two-Person Resume Canary — `test23_v11`

- started: 2026-05-06T15:02:45
- finished: 2026-05-06T15:36:25
- commit: `62d249e` dirty=True
- base_url: http://localhost:8082/ui/hornelore1.0.html
- api_base: http://localhost:8000

## Topline: **RED**

- Mary Holts (messy): **RED**
- Marvin Mann (clean): **RED**

### Final failures
- Mary RED
- Marvin RED

## Mary Holts (TEST-23) (`mary`) — **RED**

- person_id: `6cd4a7c3-38d0-42aa-8764-cc6e1da53edf`

### Onboarding

| Step | Sent | Reply (excerpt) | Severity | Elapsed |
|---|---|---|---|---:|
| onboard_name | `mary Holts` | Mary, it's wonderful to meet you and start this conversation. Knowing your date … | PASS | 29558ms |
| onboard_dob | `2/29 1940` | So, you were born on February 29th, 1940 – what a unique birthday! I love that. … | PASS | 21279ms |
| onboard_pob | `Minot ND` | Type – whatever feels most natural for you. The camera is optional, and you can … | PASS | 45843ms |
| onboard_pob_correction | `Actually it's Minot, North Dakota — not just ND` | I heard that as a correction, but I'm not fully certain which field it changes y… | PASS | 15054ms |

**BB state after onboarding:**

- firstName: `None` (expected `'Mary'`)
- lastName: `None` (expected `'Holts'`)
- DOB: `None` (expected `'1940-02-29'`)
- POB: `None` (expected `'Minot, North Dakota'`)
- basics_complete: `True`

### Early inference probes (right after onboarding)

**early_age_guess:** sent=`How old do you think I am?` reply=`You were born on February 29, 1940, so you are 86 now.` severity=PASS
  - text_elapsed=1227ms tts_wait=6365ms tts_done=True
  - age guess hit (expected=86, found=[86])

**early_residence_guess:** sent=`Where do you think I live now?` reply=`Let's continue from where we left off. We were discussing your birthplace, Minot, North Dakota. Shall we go back to that conversation?` severity=PASS
  - text_elapsed=17666ms tts_wait=11113ms tts_done=True
  - residence: echoed POB with framing (acceptable)

### Life Map walk

| Era | Click log | Era set | Reply (excerpt) | Anchored | Severity |
|---|---|---|---|---|---|
| Earliest Years (earliest_years) | ✓ | earliest_years | Being born during a storm must have been quite an experience. What do … | ✓ | PASS |
| Early School Years (early_school_years) | ✓ | early_school_years | What the neighborhood was like? | ✓ | PASS |
| Adolescence (adolescence) | ✓ | adolescence | Was best kept private. How did you navigate those boundaries as a teen… | ✓ | PASS |
| Coming of Age (coming_of_age) | ✓ | coming_of_age | That's a lovely story. What was it about him that made him come back t… | ✗ | AMBER |
| Building Years (building_years) | ✓ | building_years | Those years were indeed filled with change and growth. What do you rem… | ✓ | PASS |
| Later Years (later_years) | ✓ | later_years | That must have been a difficult time for you. What do you remember abo… | ✓ | PASS |

**Mid-stream extras (correction / ambiguity probes):**

- **Building Years** sent=`Actually we only had two kids, not three.`
  reply=`I heard that as a correction, but I'm not fully certain which field it changes yet. You can say it one piece at a time — for example, 'I was born in ...' or 'My father's name was ...'.`
  handled_well=True

### Today cycles + factual interruption

**Today cycle 1:** sent=`These days I take things slower. I like sitting by the windo` reply=`Can you tell me about that sounds peaceful. Do you find that sitting by the window in the morning helps you feel more co…` severity=AMBER

**Today cycle 2:** sent=`I still think about everything that came before, but I try t` reply=`That sounds peaceful. Do you find that sitting by the window in the morning helps you feel more connected to the present…` severity=AMBER

**Today factual ('what day is it'):** reply=`Wednesday, May 6, 2026.` severity=PASS
  - text_elapsed=6171ms tts_wait=4160ms tts_done=True

### Late-stage age probe (after Life Map walk + Today)

sent=`How old do you think I am now?` reply=`You were born on February 29, 1940, so you are 86 now.` severity=PASS
  - text_elapsed=1237ms tts_wait=6430ms tts_done=True
  - late age hit (expected=86, found=[86])
  - consistent age across probes: {86}

### Pre-restart memory recall (Earliest Years anchor + 'what do you know about me')

- name recalled: True
- DOB/year recalled: True
- POB recalled: True
- era stories in readback: 2/7  (memory_echo readback content; NOT a measure of era-click navigation)
- cross-contamination: False
- onboarding restart: False
- severity: **AMBER**

Reply excerpt: `What I know about mary so far:

Identity
- Name: mary
- Date of birth: 1940-02-29
- Place of birth: Minot ND

Family
- Parents: (none on record yet)
- Siblings: (none on record yet)

Notes from our conversation
- Childhood home: Minot ND
- Education: walked to school
- Life stage: senior elder

What I'm less sure about
- Some parts are still blank, and that is completely fine. You can correct or a…`

### Post-restart memory recall (after browser context reopen)

- name recalled: False
- DOB/year recalled: False
- POB recalled: False
- era stories in readback: 0/7  (memory_echo readback content; NOT a measure of era-click navigation)
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
| early_inference | extract_attempts=2, extract_summary=2, fk_constraint=2, story_trigger=1, utterance_frame=1 |
| lifemap | extract_attempts=7, extract_summary=6, fk_constraint=12, story_trigger=7, utterance_frame=7 |
| today | extract_attempts=3, extract_summary=3, fk_constraint=4, story_trigger=3, utterance_frame=3 |
| late_age | extract_attempts=1 |
| recall_pre | extract_attempts=1, extract_summary=1, fk_constraint=2, story_trigger=1, utterance_frame=1 |
| resume | (none) |

## Marvin Mann (TEST-23) (`marvin`) — **RED**

- person_id: `db3a97d6-d181-499a-8fdc-3b7632347cc6`

### Onboarding

| Step | Sent | Reply (excerpt) | Severity | Elapsed |
|---|---|---|---|---:|
| onboard_name | `Marvin Mann` | It's lovely to meet you, Marvin Mann. Now, can you tell me your date of birth? T… | PASS | 31091ms |
| onboard_dob | `December 6, 1949` | Region that feels like home to you from your early years? | PASS | 18562ms |
| onboard_pob | `Fargo, North Dakota` | It's lovely that you were born in Fargo, North Dakota. Before we start, I want t… | PASS | 49880ms |
| status_seed | `I am a widower now, I still think about my wife ev` | That's beautiful, Marvin. It's clear she was a special person in your life. Take… | PASS | 16907ms |

**BB state after onboarding:**

- firstName: `None` (expected `'Marvin'`)
- lastName: `None` (expected `'Mann'`)
- DOB: `None` (expected `'1949-12-06'`)
- POB: `None` (expected `'Fargo, North Dakota'`)
- basics_complete: `True`

### Early inference probes (right after onboarding)

**early_age_guess:** sent=`How old do you think I am?` reply=`You were born on December 6, 1949, so you are 76 now.` severity=PASS
  - text_elapsed=2089ms tts_wait=6469ms tts_done=True
  - age guess hit (expected=76, found=[76])

**early_residence_guess:** sent=`Where do you think I live now?` reply=`Let's pick up where we left off earlier. We were just getting started on your story. Shall we continue from where we were?` severity=AMBER
  - text_elapsed=14866ms tts_wait=9274ms tts_done=True
  - residence: ambiguous response (review manually)

### Life Map walk

| Era | Click log | Era set | Reply (excerpt) | Anchored | Severity |
|---|---|---|---|---|---|
| Earliest Years (earliest_years) | ✓ | earliest_years | Can you tell me about that small house in Fargo sounds like a cozy pla… | ✓ | PASS |
| Early School Years (early_school_years) | ✓ | early_school_years | How did you feel about math classes back then? | ✗ | AMBER |
| Adolescence (adolescence) | ✓ | adolescence | Working after school was a big responsibility for you, and you had a g… | ✓ | PASS |
| Coming of Age (coming_of_age) | ✓ | coming_of_age | How did you balance independence with the responsibilities of working? | ✗ | AMBER |
| Building Years (building_years) | ✓ | building_years | Building a life together is a remarkable journey. What do you remember… | ✗ | AMBER |
| Later Years (later_years) | ✓ | later_years | Can you tell me about those letters must be a treasured keepsake for y… | ✓ | PASS |

**Mid-stream extras (correction / ambiguity probes):**

- **Adolescence** sent=`I think that was around 1965… or maybe a little later.`
  reply=`Working after school was a big responsibility for you, and you had a goal in mind with that pickup. What did you do with that money you earned?`
  handled_well=True

### Today cycles + factual interruption

**Today cycle 1:** sent=`Today I keep a simple routine. Coffee, a short walk, and a l` reply=`Can you tell me about that sounds like a peaceful rhythm. What does life look like for you these days - where are you, w…` severity=PASS

**Today cycle 2:** sent=`I still miss my wife, but I try to notice small good things ` reply=`That sounds like a peaceful rhythm. What does life look like for you these days - where are you, who do you see most, wh…` severity=PASS

**Today factual ('what day is it'):** reply=`It's Wednesday, May 6th, 2026.` severity=PASS
  - text_elapsed=7061ms tts_wait=4500ms tts_done=True

### Late-stage age probe (after Life Map walk + Today)

sent=`How old do you think I am now?` reply=`You were born on December 6, 1949, so you are 76 now.` severity=PASS
  - text_elapsed=1645ms tts_wait=6448ms tts_done=True
  - late age hit (expected=76, found=[76])
  - consistent age across probes: {76}

### Pre-restart memory recall (Earliest Years anchor + 'what do you know about me')

- name recalled: True
- DOB/year recalled: True
- POB recalled: True
- era stories in readback: 1/7  (memory_echo readback content; NOT a measure of era-click navigation)
- cross-contamination: False
- onboarding restart: False
- severity: **AMBER**

Reply excerpt: `What I know about Marvin Mann so far:

Identity
- Name: Marvin Mann
- Date of birth: 1949-12-06
- Place of birth: Fargo, North Dakota

Family
- Parents: (none on record yet)
- Siblings: (none on record yet)

Notes from our conversation
- Childhood home: Fargo, North Dakota
- Career: worked after school
- Life stage: elder / retirement years

What I'm less sure about
- Some parts are still blank, a…`

### Spouse memory probe (Marvin only — emotional anchoring + attribution)

sent=`What do you remember about my wife?` reply=`You've shared that you still think about your wife every morning, and that you kept some of her letters in the top drawer of your desk after she passed away. Those are poignant reminders of your love and connection. Is there anything specific that stands out to you about your wife, or any particular…` severity=PASS
  - text_elapsed=15613ms tts_wait=19136ms tts_done=True
  - spouse tokens hit: ['wife', 'letters', 'drawer', 'morning']/['wife', 'widower', 'letters', 'drawer', 'morning']
  - emotional anchoring intact (≥2 spouse tokens recalled)

### Post-restart memory recall (after browser context reopen)

- name recalled: False
- DOB/year recalled: False
- POB recalled: False
- era stories in readback: 0/7  (memory_echo readback content; NOT a measure of era-click navigation)
- cross-contamination: False
- onboarding restart: False
- severity: **RED**

Reply excerpt: ``

### Today after resume ('what day is it')

- reply: `It's Wednesday, May 6, 2026.`
- severity: **PASS**

### api.log signal counts per phase

| Phase | Signals |
|---|---|
| onboard | extract_attempts=1, fk_constraint=4, story_trigger=1, utterance_frame=1 |
| early_inference | extract_attempts=2, extract_summary=3, fk_constraint=1, story_trigger=1, utterance_frame=1 |
| lifemap | extract_attempts=7, extract_summary=6, fk_constraint=13, story_trigger=7, utterance_frame=7 |
| today | extract_attempts=3, extract_summary=3, fk_constraint=4, story_trigger=3, utterance_frame=3 |
| late_age | extract_attempts=1, fk_constraint=1 |
| recall_pre | extract_attempts=1, extract_summary=1, fk_constraint=2, story_trigger=1, utterance_frame=1 |
| spouse_probe | extract_attempts=1, extract_summary=1 |
| resume | extract_attempts=1, fk_constraint=2, story_trigger=1, utterance_frame=1 |

## Stress Telemetry (WO-OPS-STRESS-TELEMETRY-KV-01)

- snapshots captured: **18**
- kv-clear calls: **0**
