# TEST-23 Two-Person Resume Canary — `test23_v8`

- started: 2026-05-06T07:47:17
- finished: 2026-05-06T08:19:12
- commit: `4fa3bbd` dirty=False
- base_url: http://localhost:8082/ui/hornelore1.0.html
- api_base: http://localhost:8000

## Topline: **RED**

- Mary Holts (messy): **RED**
- Marvin Mann (clean): **RED**

### Final failures
- Mary RED
- Marvin RED

## Mary Holts (TEST-23) (`mary`) — **RED**

- person_id: `365344d1-e66c-4027-9a00-28914e74b25a`

### Onboarding

| Step | Sent | Reply (excerpt) | Severity | Elapsed |
|---|---|---|---|---:|
| onboard_name | `mary Holts` | mary, it's lovely to meet you. To help me build your Life Archive, could you ple… | PASS | 33139ms |
| onboard_dob | `2/29 1940` | So you were born on February 29th, 1940 – what a unique birthday! Where did you … | PASS | 23313ms |
| onboard_pob | `Minot ND` | Type if that's easier for you - we'll adapt to what works best for you. Also, th… | PASS | 42336ms |
| onboard_pob_correction | `Actually it's Minot, North Dakota — not just ND` | You can turn it on or off whenever you like. Is there anything you'd like to kno… | PASS | 32916ms |

**BB state after onboarding:**

- firstName: `None` (expected `'Mary'`)
- lastName: `None` (expected `'Holts'`)
- DOB: `None` (expected `'1940-02-29'`)
- POB: `None` (expected `'Minot, North Dakota'`)
- basics_complete: `True`

### Early inference probes (right after onboarding)

**early_age_guess:** sent=`How old do you think I am?` reply=`Based on the birthdate you shared earlier, 1940-01-01, I believe you're likely in your 80s.` severity=AMBER
  - text_elapsed=7349ms tts_wait=7570ms tts_done=True
  - age guess miss (expected=86)

**early_residence_guess:** sent=`Where do you think I live now?` reply=`We hadn't discussed your current life yet, but since we were talking about your birthplace in Minot, North Dakota, shall we continue exploring your life story from where you grew up?` severity=PASS
  - text_elapsed=8569ms tts_wait=11648ms tts_done=True
  - residence: echoed POB with framing (acceptable)

### Life Map walk

| Era | Click log | Era set | Reply (excerpt) | Anchored | Severity |
|---|---|---|---|---|---|
| Earliest Years (earliest_years) | ✓ | earliest_years | Being born during a storm can be quite an eventful start to life. You … | ✓ | PASS |
| Early School Years (early_school_years) | ✓ | early_school_years | Walking to school through the snow with your brother sounds like a str… | ✓ | PASS |
| Adolescence (adolescence) | ✓ | adolescence | Learning that there were certain things you needed to be mindful of in… | ✓ | PASS |
| Coming of Age (coming_of_age) | ✓ | coming_of_age | The conversations you had together back then? | ✗ | AMBER |
| Building Years (building_years) | ✓ | building_years | With the kids growing up and moving to new places, I imagine there wer… | ✓ | AMBER |
| Later Years (later_years) | ✓ | later_years | It sounds like a significant change for you after losing your partner.… | ✗ | AMBER |

**Mid-stream extras (correction / ambiguity probes):**

- **Building Years** sent=`Actually we only had two kids, not three.`
  reply=`With the kids growing up and moving to new places, I imagine there were many adjustments and new experiences. What do you recall about the sense of community and connection you had with the people aro`
  handled_well=False

### Today cycles + factual interruption

**Today cycle 1:** sent=`These days I take things slower. I like sitting by the windo` reply=`Savoring the quiet moments by the window in the morning sounds peaceful. What do you find yourself looking forward to or…` severity=AMBER

**Today cycle 2:** sent=`I still think about everything that came before, but I try t` reply=`Savoring the quiet moments by the window in the morning sounds peaceful. What do you find yourself looking forward to or…` severity=AMBER

**Today factual ('what day is it'):** reply=`It's clear that you're reflecting on your life and its various chapters, but also trying to stay present and mindful. What does the present moment, like this quiet morning, bring to mind for you?` severity=PASS
  - text_elapsed=6942ms tts_wait=6587ms tts_done=True

### Late-stage age probe (after Life Map walk + Today)

sent=`How old do you think I am now?` reply=`Is there something else on your mind that you'd like to discuss?` severity=AMBER
  - text_elapsed=5725ms tts_wait=7002ms tts_done=True
  - late age miss (expected=86)

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
| onboard | extract_attempts=1, fk_constraint=3, story_trigger=1, utterance_frame=1 |
| early_inference | extract_attempts=2, extract_summary=2, fk_constraint=2, story_trigger=1, utterance_frame=1 |
| lifemap | extract_attempts=7, extract_summary=6, fk_constraint=13, story_trigger=7, utterance_frame=7 |
| today | extract_attempts=3, extract_summary=3, fk_constraint=3, story_trigger=3, utterance_frame=3 |
| late_age | extract_attempts=1 |
| recall_pre | extract_attempts=1, extract_summary=1, fk_constraint=2, story_trigger=1, utterance_frame=1 |
| resume | (none) |

## Marvin Mann (TEST-23) (`marvin`) — **RED**

- person_id: `72be3989-aad1-4fa2-baad-797af3c1c859`

### Onboarding

| Step | Sent | Reply (excerpt) | Severity | Elapsed |
|---|---|---|---|---:|
| onboard_name | `Marvin Mann` | Marvin, it's great to be talking with you! To get started, could you tell me you… | PASS | 30065ms |
| onboard_dob | `December 6, 1949` | So you were born on a winter day in December 1949. Where did you grow up, Marvin… | PASS | 14443ms |
| onboard_pob | `Fargo, North Dakota` | Type if that's easier for you. We can also have a video conversation, but you're… | PASS | 35865ms |
| status_seed | `I am a widower now, I still think about my wife ev` | It's beautiful that you still carry her in your thoughts every day. I can sense … | PASS | 18262ms |

**BB state after onboarding:**

- firstName: `None` (expected `'Marvin'`)
- lastName: `None` (expected `'Mann'`)
- DOB: `None` (expected `'1949-12-06'`)
- POB: `None` (expected `'Fargo, North Dakota'`)
- basics_complete: `True`

### Early inference probes (right after onboarding)

**early_age_guess:** sent=`How old do you think I am?` reply=`It's beautiful that you still carry her in your thoughts every day. I can sense the depth of feeling in your words. Shall we continue there?` severity=AMBER
  - text_elapsed=1226ms tts_wait=25144ms tts_done=True
  - age guess miss (expected=76)

**early_residence_guess:** sent=`Where do you think I live now?` reply=`If we're talking about the current time, I believe it's 2026, and you were born in 1949. That would make you around 77 years old. Would you like to talk about what it's like to be in your 70s?` severity=AMBER
  - text_elapsed=3258ms tts_wait=9406ms tts_done=True
  - residence: ambiguous response (review manually)

### Life Map walk

| Era | Click log | Era set | Reply (excerpt) | Anchored | Severity |
|---|---|---|---|---|---|
| Earliest Years (earliest_years) | ✓ | earliest_years | That small house with a warm kitchen sounds cozy. What was daily life … | ✓ | PASS |
| Early School Years (early_school_years) | ✓ | early_school_years | Arithmetic was a bright spot for you, but public speaking wasn't as ea… | ✓ | PASS |
| Adolescence (adolescence) | ✓ | adolescence | Working after school to save for a pickup truck - that's a great entre… | ✓ | PASS |
| Coming of Age (coming_of_age) | ✓ | coming_of_age | Leaving home for your first job was a big step. What was daily life li… | ✓ | PASS |
| Building Years (building_years) | ✓ | building_years | Building a life together with your wife - it sounds like a beautiful a… | ✓ | PASS |
| Later Years (later_years) | ✓ | later_years | Keeping your wife's letters close to you was a way to hold onto the me… | ✓ | PASS |

**Mid-stream extras (correction / ambiguity probes):**

- **Adolescence** sent=`I think that was around 1965… or maybe a little later.`
  reply=`Working after school to save for a pickup truck - that's a great entrepreneurial spirit. What do you think motivated you to start working and saving like that at a young age?`
  handled_well=True

### Today cycles + factual interruption

**Today cycle 1:** sent=`Today I keep a simple routine. Coffee, a short walk, and a l` reply=`That simple routine sounds comforting. What does life look like for you these days - where are you, who do you see most,…` severity=PASS

**Today cycle 2:** sent=`I still miss my wife, but I try to notice small good things ` reply=`That simple routine sounds comforting. What does life look like for you these days - where are you, who do you see most,…` severity=PASS

**Today factual ('what day is it'):** reply=`It's beautiful that you're finding ways to honor your wife's memory and cultivate gratitude in your daily life. What is one small good thing that stands out to you, something that brings a smile to yo` severity=PASS
  - text_elapsed=4897ms tts_wait=6885ms tts_done=True

### Late-stage age probe (after Life Map walk + Today)

sent=`How old do you think I am now?` reply=`Is there something else on your mind that you'd like to share?` severity=AMBER
  - text_elapsed=8158ms tts_wait=19712ms tts_done=True
  - late age miss (expected=76)

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

sent=`What do you remember about my wife?` reply=`You've shared that you still think about your wife every morning, and that she passed away. You also mentioned that you kept some of her letters in the top drawer of your desk. Those are the details I recall about her from our conversation.` severity=PASS
  - text_elapsed=9762ms tts_wait=14990ms tts_done=True
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

- reply: ``
- severity: **RED**

### api.log signal counts per phase

| Phase | Signals |
|---|---|
| onboard | extract_attempts=1, fk_constraint=4, story_trigger=1, utterance_frame=1 |
| early_inference | extract_attempts=2, extract_summary=2, fk_constraint=1, story_trigger=1, utterance_frame=1 |
| lifemap | extract_attempts=7, extract_summary=6, fk_constraint=13, story_trigger=7, utterance_frame=7 |
| today | extract_attempts=3, extract_summary=2, fk_constraint=3, story_trigger=3, utterance_frame=3 |
| late_age | extract_attempts=1, extract_summary=1 |
| recall_pre | extract_attempts=1, extract_summary=1, fk_constraint=2, story_trigger=1, utterance_frame=1 |
| spouse_probe | extract_attempts=1, extract_summary=1 |
| resume | phase_g_disconnect=1, ws_connected=1 |

## Stress Telemetry (WO-OPS-STRESS-TELEMETRY-KV-01)

- snapshots captured: **18**
- kv-clear calls: **0**
