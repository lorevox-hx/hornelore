# TEST-23 Two-Person Resume Canary — `test23_v9`

- started: 2026-05-06T11:19:02
- finished: 2026-05-06T11:53:19
- commit: `996531d` dirty=True
- base_url: http://localhost:8082/ui/hornelore1.0.html
- api_base: http://localhost:8000

## Topline: **RED**

- Mary Holts (messy): **RED**
- Marvin Mann (clean): **RED**

### Final failures
- Mary RED
- Marvin RED

## Mary Holts (TEST-23) (`mary`) — **RED**

- person_id: `b6e3264d-1e57-4c94-85e2-454edea4932e`

### Onboarding

| Step | Sent | Reply (excerpt) | Severity | Elapsed |
|---|---|---|---|---:|
| onboard_name | `mary Holts` | Hello mary, it's such a pleasure to meet you. Knowing your date of birth will he… | PASS | 31235ms |
| onboard_dob | `2/29 1940` | So lovely to have your birthdate, mary! February 29th, 1940 – that's a unique st… | PASS | 30235ms |
| onboard_pob | `Minot ND` | If you're more comfortable typing, that's perfectly fine too - I'll respond just… | PASS | 54101ms |
| onboard_pob_correction | `Actually it's Minot, North Dakota — not just ND` | I heard that as a correction, but I'm not fully certain which field it changes y… | PASS | 14848ms |

**BB state after onboarding:**

- firstName: `None` (expected `'Mary'`)
- lastName: `None` (expected `'Holts'`)
- DOB: `None` (expected `'1940-02-29'`)
- POB: `None` (expected `'Minot, North Dakota'`)
- basics_complete: `True`

### Early inference probes (right after onboarding)

**early_age_guess:** sent=`How old do you think I am?` reply=`I heard that as a correction, but I'm not fully certain which field it changes yet. You can say it one piece at a time — for example, 'I was born in ...' or 'My father's name was ...'.` severity=AMBER
  - text_elapsed=5307ms tts_wait=14776ms tts_done=True
  - age guess miss (expected=86)

**early_residence_guess:** sent=`Where do you think I live now?` reply=`Last time we were talking about your birthplace. Shall we continue there?` severity=AMBER
  - text_elapsed=5313ms tts_wait=5698ms tts_done=True
  - residence: ambiguous response (review manually)

### Life Map walk

| Era | Click log | Era set | Reply (excerpt) | Anchored | Severity |
|---|---|---|---|---|---|
| Earliest Years (earliest_years) | ✓ | earliest_years | Being born during a storm, especially in a cold winter, can be quite v… | ✓ | PASS |
| Early School Years (early_school_years) | ✓ | early_school_years | Walking to school through the snow with your brother must have been a … | ✓ | PASS |
| Adolescence (adolescence) | ✓ | adolescence | You learned early on there were things you said in public and things y… | ✓ | PASS |
| Coming of Age (coming_of_age) | ✓ | coming_of_age | It sounds like you had a strong connection with him right from the sta… | ✗ | AMBER |
| Building Years (building_years) | ✓ | building_years | Those early years of raising a family and navigating your husband's ca… | ✗ | AMBER |
| Later Years (later_years) | ✓ | later_years | It sounds like losing him had a profound impact on your daily routine … | ✓ | PASS |

**Mid-stream extras (correction / ambiguity probes):**

- **Building Years** sent=`Actually we only had two kids, not three.`
  reply=`I heard that as a correction, but I'm not fully certain which field it changes yet. You can say it one piece at a time — for example, 'I was born in ...' or 'My father's name was ...'.`
  handled_well=True

### Today cycles + factual interruption

**Today cycle 1:** sent=`These days I take things slower. I like sitting by the windo` reply=`Taking things slower and enjoying the morning light by the window sounds like a peaceful way to start the day. What do y…` severity=PASS

**Today cycle 2:** sent=`I still think about everything that came before, but I try t` reply=`Taking things slower and enjoying the morning light by the window sounds like a peaceful way to start the day. What do y…` severity=PASS

**Today factual ('what day is it'):** reply=`It's beautiful how you're finding a way to balance nostalgia with being present in the moment. Can you tell me more about what it means to you to "stay in the day"?` severity=PASS
  - text_elapsed=10259ms tts_wait=12901ms tts_done=True

### Late-stage age probe (after Life Map walk + Today)

sent=`How old do you think I am now?` reply=`Based on what you shared earlier, I believe you were born on February 29, 1940. Since leap year birthdays only occur every 4 years, I would calculate your current age as 86 years old, but since 2026 i…` severity=PASS
  - text_elapsed=16408ms tts_wait=25211ms tts_done=True
  - late age hit (expected=86, found=[86])
  - IMPROVEMENT: early probe missed; late probe hit (memory consolidating)

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
| early_inference | extract_attempts=2, extract_summary=1, fk_constraint=2, story_trigger=2, utterance_frame=2 |
| lifemap | extract_attempts=7, extract_summary=6, fk_constraint=13, story_trigger=7, utterance_frame=7 |
| today | extract_attempts=3, extract_summary=4, fk_constraint=4, story_trigger=3, utterance_frame=3 |
| late_age | extract_attempts=1, extract_summary=1, fk_constraint=1, story_trigger=1, utterance_frame=1 |
| recall_pre | extract_attempts=1, extract_summary=1, fk_constraint=2, story_trigger=1, utterance_frame=1 |
| resume | (none) |

## Marvin Mann (TEST-23) (`marvin`) — **RED**

- person_id: `8a6526a5-6d11-43b5-9da6-04e9c74ad7b8`

### Onboarding

| Step | Sent | Reply (excerpt) | Severity | Elapsed |
|---|---|---|---|---:|
| onboard_name | `Marvin Mann` | It's wonderful to meet you, Marvin Mann. Now, can you tell me your date of birth… | PASS | 32597ms |
| onboard_dob | `December 6, 1949` | Region that feels like home to you? | PASS | 14339ms |
| onboard_pob | `Fargo, North Dakota` | It's lovely that you were born in Fargo, North Dakota. Now, before we start, I w… | PASS | 46222ms |
| status_seed | `I am a widower now, I still think about my wife ev` | It's beautiful that her memory stays with you every day. I'm so sorry for your l… | PASS | 28313ms |

**BB state after onboarding:**

- firstName: `None` (expected `'Marvin'`)
- lastName: `None` (expected `'Mann'`)
- DOB: `None` (expected `'1949-12-06'`)
- POB: `None` (expected `'Fargo, North Dakota'`)
- basics_complete: `True`

### Early inference probes (right after onboarding)

**early_age_guess:** sent=`How old do you think I am?` reply=`If I recall correctly, you were born on December 6, 1949. That would make you 76 years old, right?` severity=PASS
  - text_elapsed=7360ms tts_wait=10401ms tts_done=True
  - age guess hit (expected=76, found=[76])

**early_residence_guess:** sent=`Where do you think I live now?` reply=`Last time we were talking about your late wife and your memories of her. Shall we continue there?` severity=AMBER
  - text_elapsed=6137ms tts_wait=7547ms tts_done=True
  - residence: ambiguous response (review manually)

### Life Map walk

| Era | Click log | Era set | Reply (excerpt) | Anchored | Severity |
|---|---|---|---|---|---|
| Earliest Years (earliest_years) | ✓ | earliest_years | That small house with a cozy kitchen sounds like a comforting place. W… | ✓ | PASS |
| Early School Years (early_school_years) | ✓ | early_school_years | Arithmetic and shyness about reading out loud - that's an interesting … | ✓ | PASS |
| Adolescence (adolescence) | ✓ | adolescence | Working after school to save for a pickup truck sounds like a goal-dri… | ✓ | PASS |
| Coming of Age (coming_of_age) | ✓ | coming_of_age | Taking on your first steady job and learning about responsibility firs… | ✓ | PASS |
| Building Years (building_years) | ✓ | building_years | Building a life together with your wife, buying a house, raising child… | ✓ | PASS |
| Later Years (later_years) | ✓ | later_years | Those letters must hold a special place in your heart. Keeping them cl… | ✓ | PASS |

**Mid-stream extras (correction / ambiguity probes):**

- **Adolescence** sent=`I think that was around 1965… or maybe a little later.`
  reply=`Working after school to save for a pickup truck sounds like a goal-driven endeavor. What do you remember about the freedom of having your own vehicle, even if it was an old one?`
  handled_well=True

### Today cycles + factual interruption

**Today cycle 1:** sent=`Today I keep a simple routine. Coffee, a short walk, and a l` reply=`How have they helped you cope with the loss of your wife?` severity=AMBER

**Today cycle 2:** sent=`I still miss my wife, but I try to notice small good things ` reply=`How have they helped you cope with the loss of your wife?` severity=AMBER

**Today factual ('what day is it'):** reply=`That's a beautiful approach. What's been a recent source of joy or comfort for you, something that's helped you appreciate the small things in life?` severity=PASS
  - text_elapsed=413ms tts_wait=23508ms tts_done=True

### Late-stage age probe (after Life Map walk + Today)

sent=`How old do you think I am now?` reply=`If I recall correctly, you were born on December 6, 1949. That would make you 76 years old, right?` severity=PASS
  - text_elapsed=8180ms tts_wait=10409ms tts_done=True
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

sent=`What do you remember about my wife?` reply=`You've shared that you still think about your wife every morning, and you mentioned her in the context of your daily routine and the life you built together. You also talked about keeping her letters in a special place as a reminder of her love and presence in your life. Is there something specific …` severity=PASS
  - text_elapsed=15532ms tts_wait=19495ms tts_done=True
  - spouse tokens hit: ['wife', 'letters', 'morning']/['wife', 'widower', 'letters', 'drawer', 'morning']
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

- reply: ``
- severity: **RED**

### api.log signal counts per phase

| Phase | Signals |
|---|---|
| onboard | extract_attempts=1, fk_constraint=4, story_trigger=1, utterance_frame=1 |
| early_inference | extract_attempts=2, extract_summary=1, fk_constraint=2, story_trigger=1, utterance_frame=1 |
| lifemap | extract_attempts=7, extract_summary=6, fk_constraint=12, story_trigger=7, utterance_frame=7 |
| today | extract_attempts=3, extract_summary=3, fk_constraint=4, story_trigger=3, utterance_frame=3 |
| late_age | extract_attempts=1, fk_constraint=1, story_trigger=1, utterance_frame=1 |
| recall_pre | extract_attempts=1, extract_summary=1, fk_constraint=2, story_trigger=1, utterance_frame=1 |
| spouse_probe | extract_attempts=1, extract_summary=1 |
| resume | (none) |

## Stress Telemetry (WO-OPS-STRESS-TELEMETRY-KV-01)

- snapshots captured: **18**
- kv-clear calls: **0**
