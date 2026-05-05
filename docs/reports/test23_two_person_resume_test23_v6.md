# TEST-23 Two-Person Resume Canary — `test23_v6`

- started: 2026-05-05T08:19:42
- finished: 2026-05-05T08:54:36
- commit: `1be89ec` dirty=False
- base_url: http://localhost:8082/ui/hornelore1.0.html
- api_base: http://localhost:8000

## Topline: **RED**

- Mary Holts (messy): **RED**
- Marvin Mann (clean): **RED**

### Final failures
- Mary RED
- Marvin RED

## Mary Holts (TEST-23) (`mary`) — **RED**

- person_id: `d1ecf805-1ce5-40a7-8870-8ae8980f3360`

### Onboarding

| Step | Sent | Reply (excerpt) | Severity | Elapsed |
|---|---|---|---|---:|
| onboard_name | `mary Holts` | mary, it's so great to meet you! Now, I'd love to get started on building your L… | PASS | 32828ms |
| onboard_dob | `2/29 1940` | February 29th, 1940 – a leap day baby! That's wonderful. Now, let's talk about w… | PASS | 21046ms |
| onboard_pob | `Minot ND` | If you prefer, you can type - whatever feels more natural for you. And if you'd … | PASS | 51382ms |
| onboard_pob_correction | `Actually it's Minot, North Dakota — not just ND` | Are you ready to begin building your Life Archive? | PASS | 13082ms |

**BB state after onboarding:**

- firstName: `None` (expected `'Mary'`)
- lastName: `None` (expected `'Holts'`)
- DOB: `None` (expected `'1940-02-29'`)
- POB: `None` (expected `'Minot, North Dakota'`)
- basics_complete: `True`

### Early inference probes (right after onboarding)

**early_age_guess:** sent=`How old do you think I am?` reply=`Based on the birthdate you provided earlier, I believe you were born in 1940, which would make you 86 years old today, May 5th. Shall we continue exploring your story?` severity=PASS
  - text_elapsed=7722ms tts_wait=12814ms tts_done=True
  - age guess hit (expected=86, found=[86])

**early_residence_guess:** sent=`Where do you think I live now?` reply=`Last time we were talking about your family. Shall we continue there?` severity=AMBER
  - text_elapsed=4885ms tts_wait=5643ms tts_done=True
  - residence: ambiguous response (review manually)

### Life Map walk

| Era | Click log | Era set | Reply (excerpt) | Anchored | Severity |
|---|---|---|---|---|---|
| Earliest Years (earliest_years) | ✓ | earliest_years | Being born during a storm must have made a strong impression on you, m… | ✓ | PASS |
| Early School Years (early_school_years) | ✓ | early_school_years | Walking to school through the snow with your brother must have been a … | ✓ | PASS |
| Adolescence (adolescence) | ✓ | adolescence | Learning about social nuances and knowing when to speak or keep quiet … | ✗ | AMBER |
| Coming of Age (coming_of_age) | ✓ | coming_of_age | Tell me more about what that was like - what drew you to him, and what… | ✗ | AMBER |
| Building Years (building_years) | ✓ | building_years | With your husband's work taking you to different places, I imagine it … | ✓ | AMBER |
| Later Years (later_years) | ✓ | later_years | It sounds like after your husband passed away, you found solace in bei… | ✓ | PASS |

**Mid-stream extras (correction / ambiguity probes):**

- **Building Years** sent=`Actually we only had two kids, not three.`
  reply=`With your husband's work taking you to different places, I imagine it was a busy but exciting time for your family. What do you remember about the places you lived and the sense of community you found`
  handled_well=False

### Today cycles + factual interruption

**Today cycle 1:** sent=`These days I take things slower. I like sitting by the windo` reply=`Sitting by the window in the morning sounds like a peaceful way to start the day. You mentioned taking things slower - w…` severity=PASS

**Today cycle 2:** sent=`I still think about everything that came before, but I try t` reply=`It can be bittersweet to reflect on the past while also living in the present. You're finding a way to acknowledge the m…` severity=PASS

**Today factual ('what day is it'):** reply=`Today's date is Wednesday, May 5th. Shall we continue there, mary?` severity=PASS
  - text_elapsed=6956ms tts_wait=6621ms tts_done=True

### Late-stage age probe (after Life Map walk + Today)

sent=`How old do you think I am now?` reply=`Today's date is Wednesday, May 5th. Shall we continue there, mary?` severity=RED
  - text_elapsed=6129ms tts_wait=27087ms tts_done=True
  - late age miss (expected=86)
  - REGRESSION: early probe got age right; late probe missed

### Pre-restart memory recall (Earliest Years anchor + 'what do you know about me')

- name recalled: True
- DOB/year recalled: True
- POB recalled: True
- era facts recalled: 2/7
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
| lifemap | extract_attempts=7, extract_summary=6, fk_constraint=12, story_trigger=7, utterance_frame=7 |
| today | extract_attempts=3, extract_summary=3, fk_constraint=3, story_trigger=3, utterance_frame=3 |
| late_age | extract_attempts=1, extract_summary=1, fk_constraint=1 |
| recall_pre | extract_attempts=1, extract_summary=1, fk_constraint=2, story_trigger=1, utterance_frame=1 |
| resume | (none) |

## Marvin Mann (TEST-23) (`marvin`) — **RED**

- person_id: `aa4992e8-1747-4e53-b405-d3260e737a56`

### Onboarding

| Step | Sent | Reply (excerpt) | Severity | Elapsed |
|---|---|---|---|---:|
| onboard_name | `Marvin Mann` | Hi Marvin Mann, it's so nice to meet you and start this conversation. Knowing yo… | PASS | 29203ms |
| onboard_dob | `December 6, 1949` | December 6, 1949 is a great starting point for your story, Marvin Mann. Now, I'm… | PASS | 22374ms |
| onboard_pob | `Fargo, North Dakota` | Fargo, North Dakota holds a special place in your early years, Marvin Mann. Now,… | PASS | 45982ms |
| status_seed | `I am a widower now, I still think about my wife ev` | Losing a loved one is never easy, Marvin Mann. Take your time, and when you're r… | PASS | 36756ms |

**BB state after onboarding:**

- firstName: `None` (expected `'Marvin'`)
- lastName: `None` (expected `'Mann'`)
- DOB: `None` (expected `'1949-12-06'`)
- POB: `None` (expected `'Fargo, North Dakota'`)
- basics_complete: `True`

### Early inference probes (right after onboarding)

**early_age_guess:** sent=`How old do you think I am?` reply=`Would you like to start fresh with a question or a topic that's on your mind?` severity=AMBER
  - text_elapsed=14313ms tts_wait=5078ms tts_done=True
  - age guess miss (expected=76)

**early_residence_guess:** sent=`Where do you think I live now?` reply=`Would you like to start fresh with a question or a topic that's on your mind?` severity=AMBER
  - text_elapsed=10220ms tts_wait=12955ms tts_done=True
  - residence: ambiguous response (review manually)

### Life Map walk

| Era | Click log | Era set | Reply (excerpt) | Anchored | Severity |
|---|---|---|---|---|---|
| Earliest Years (earliest_years) | ✓ | earliest_years | That small house with a cozy kitchen sounds like a comforting place, M… | ✓ | PASS |
| Early School Years (early_school_years) | ✓ | early_school_years | Arithmetic and shyness about reading out loud - those are distinct mem… | ✓ | PASS |
| Adolescence (adolescence) | ✓ | adolescence | Working after school and saving up for a special goal is a great accom… | ✓ | PASS |
| Coming of Age (coming_of_age) | ✓ | coming_of_age | Leaving home for your first job was a significant step, Marvin Mann. W… | ✓ | PASS |
| Building Years (building_years) | ✓ | building_years | Building a life together with your wife sounds like a beautiful journe… | ✓ | PASS |
| Later Years (later_years) | ✓ | later_years | Those letters must hold a lot of meaning for you, Marvin Mann. What do… | ✓ | PASS |

**Mid-stream extras (correction / ambiguity probes):**

- **Adolescence** sent=`I think that was around 1965… or maybe a little later.`
  reply=`Working after school and saving up for a special goal is a great accomplishment, Marvin Mann. What do you remember about where you were living during your adolescence?`
  handled_well=True

### Today cycles + factual interruption

**Today cycle 1:** sent=`Today I keep a simple routine. Coffee, a short walk, and a l` reply=`That simple routine sounds like a comforting pace, Marvin Mann. What does life look like for you these days - where are …` severity=PASS

**Today cycle 2:** sent=`I still miss my wife, but I try to notice small good things ` reply=`That simple routine sounds like a comforting pace, Marvin Mann. What does life look like for you these days - where are …` severity=PASS

**Today factual ('what day is it'):** reply=`That's a beautiful approach, Marvin Mann. It sounds like you're finding ways to honor your wife's memory and cultivate gratitude, even in the midst of missing her. What small good things have you noti` severity=PASS
  - text_elapsed=3239ms tts_wait=5894ms tts_done=True

### Late-stage age probe (after Life Map walk + Today)

sent=`How old do you think I am now?` reply=`Let me see... you were born in 1949, and today's date is May 5, 2026. I'd be happy to help you figure out your current age, Marvin Mann. Would you like me to calculate it for you?` severity=AMBER
  - text_elapsed=9759ms tts_wait=16177ms tts_done=True
  - late age miss (expected=76)

### Pre-restart memory recall (Earliest Years anchor + 'what do you know about me')

- name recalled: True
- DOB/year recalled: True
- POB recalled: True
- era facts recalled: 1/7
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

sent=`What do you remember about my wife?` reply=`I don't have any personal memories of your wife, Marvin Mann. However, from our conversation, I recall that you mentioned she passed away and that you still think about her every morning. You also shared that you kept some of her letters in the top drawer of your desk after she died. That's a poigna…` severity=PASS
  - text_elapsed=12966ms tts_wait=20744ms tts_done=True
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

- reply: ``
- severity: **RED**

### api.log signal counts per phase

| Phase | Signals |
|---|---|
| onboard | extract_attempts=1, fk_constraint=3, story_trigger=1, utterance_frame=1 |
| early_inference | extract_attempts=2, extract_summary=1, fk_constraint=2, story_trigger=1, utterance_frame=1 |
| lifemap | extract_attempts=7, extract_summary=6, fk_constraint=13, phase_g_disconnect=1, story_trigger=7, utterance_frame=7, ws_connected=1 |
| today | extract_attempts=3, extract_summary=3, fk_constraint=4, story_trigger=3, utterance_frame=3 |
| late_age | extract_attempts=1, extract_summary=1 |
| recall_pre | extract_attempts=1, extract_summary=1, fk_constraint=2, story_trigger=1, utterance_frame=1 |
| spouse_probe | extract_attempts=1, extract_summary=1, fk_constraint=1, story_trigger=1, utterance_frame=1 |
| resume | (none) |

## Stress Telemetry (WO-OPS-STRESS-TELEMETRY-KV-01)

- snapshots captured: **19**
- kv-clear calls: **1**
