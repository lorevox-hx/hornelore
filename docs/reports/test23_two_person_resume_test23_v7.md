# TEST-23 Two-Person Resume Canary — `test23_v7`

- started: 2026-05-05T20:03:27
- finished: 2026-05-05T20:37:06
- commit: `932a0d8` dirty=False
- base_url: http://localhost:8082/ui/hornelore1.0.html
- api_base: http://localhost:8000

## Topline: **RED**

- Mary Holts (messy): **RED**
- Marvin Mann (clean): **RED**

### Final failures
- Mary RED
- Marvin RED

## Mary Holts (TEST-23) (`mary`) — **RED**

- person_id: `c7c3f9b0-85d0-40ca-9df7-b7d4bb515c2c`

### Onboarding

| Step | Sent | Reply (excerpt) | Severity | Elapsed |
|---|---|---|---|---:|
| onboard_name | `mary Holts` | It's wonderful to meet you, mary! Knowing your date of birth will help me get a … | PASS | 29604ms |
| onboard_dob | `2/29 1940` | That's lovely, mary - February 29, 1940, a special birthday indeed! Now, I'd lov… | PASS | 23829ms |
| onboard_pob | `Minot ND` | Type away - whatever feels most comfortable for you. If you'd like, you can also… | PASS | 44380ms |
| onboard_pob_correction | `Actually it's Minot, North Dakota — not just ND` | Do you have any questions for me before we get started? | PASS | 14204ms |

**BB state after onboarding:**

- firstName: `None` (expected `'Mary'`)
- lastName: `None` (expected `'Holts'`)
- DOB: `None` (expected `'1940-02-29'`)
- POB: `None` (expected `'Minot, North Dakota'`)
- basics_complete: `True`

### Early inference probes (right after onboarding)

**early_age_guess:** sent=`How old do you think I am?` reply=`Do you have any questions for me before we get started?` severity=AMBER
  - text_elapsed=6521ms tts_wait=12850ms tts_done=True
  - age guess miss (expected=86)

**early_residence_guess:** sent=`Where do you think I live now?` reply=`Last time we were talking about how old you think I am. Shall we continue there?` severity=AMBER
  - text_elapsed=5697ms tts_wait=5967ms tts_done=True
  - residence: ambiguous response (review manually)

### Life Map walk

| Era | Click log | Era set | Reply (excerpt) | Anchored | Severity |
|---|---|---|---|---|---|
| Earliest Years (earliest_years) | ✓ | earliest_years | Being born during a storm can be a dramatic and memorable experience, … | ✓ | PASS |
| Early School Years (early_school_years) | ✓ | early_school_years | Walking to school with your brother through the snow must have been a … | ✓ | PASS |
| Adolescence (adolescence) | ✓ | adolescence | To keep private can be a valuable lesson. During your adolescence, wha… | ✓ | PASS |
| Coming of Age (coming_of_age) | ✓ | coming_of_age | Meeting your future partner at a county fair can be a charming and mem… | ✓ | PASS |
| Building Years (building_years) | ✓ | building_years | How they impacted your family's daily life? | ✗ | AMBER |
| Later Years (later_years) | ✓ | later_years | It sounds like the quietness of the house after your loss led you to f… | ✓ | PASS |

**Mid-stream extras (correction / ambiguity probes):**

- **Building Years** sent=`Actually we only had two kids, not three.`
  reply=`How they impacted your family's daily life?`
  handled_well=False

### Today cycles + factual interruption

**Today cycle 1:** sent=`These days I take things slower. I like sitting by the windo` reply=`It sounds like simplicity and quiet moments are bringing you peace these days. What do you appreciate most about your mo…` severity=PASS

**Today cycle 2:** sent=`I still think about everything that came before, but I try t` reply=`It's beautiful that you're acknowledging the past while focusing on the present. It sounds like mindfulness is helping y…` severity=PASS

**Today factual ('what day is it'):** reply=`It's beautiful that you're acknowledging the past while focusing on the present. It sounds like mindfulness is helping you navigate your thoughts. How do you typically handle the quiet moments when me` severity=PASS
  - text_elapsed=4476ms tts_wait=23132ms tts_done=True

### Late-stage age probe (after Life Map walk + Today)

sent=`How old do you think I am now?` reply=`Based on your birthdate, February 29, 1940, I believe you are currently 86 years old. Am I correct, mary?` severity=PASS
  - text_elapsed=7777ms tts_wait=10351ms tts_done=True
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
| early_inference | extract_attempts=2, extract_summary=1, fk_constraint=1, story_trigger=1, utterance_frame=1 |
| lifemap | extract_attempts=7, extract_summary=6, fk_constraint=12, story_trigger=7, utterance_frame=7 |
| today | extract_attempts=3, extract_summary=4, fk_constraint=4, story_trigger=3, utterance_frame=3 |
| late_age | extract_attempts=1, fk_constraint=1 |
| recall_pre | extract_attempts=1, extract_summary=1, fk_constraint=1, story_trigger=1, utterance_frame=1 |
| resume | (none) |

## Marvin Mann (TEST-23) (`marvin`) — **RED**

- person_id: `ad228e82-ff15-4452-b579-b087773df980`

### Onboarding

| Step | Sent | Reply (excerpt) | Severity | Elapsed |
|---|---|---|---|---:|
| onboard_name | `Marvin Mann` | Welcome, Marvin Mann. I'm so glad to be here to help you build your Life Archive… | PASS | 32808ms |
| onboard_dob | `December 6, 1949` | Marvin, you were born on December 6, 1949. I've got that down. Now, I'd love to … | PASS | 23624ms |
| onboard_pob | `Fargo, North Dakota` | Type away - whatever feels more natural to you. If you'd like, you can also see … | PASS | 40418ms |
| status_seed | `I am a widower now, I still think about my wife ev` | Marvin, I'm so sorry for your loss. It's beautiful that you still think about yo… | PASS | 25781ms |

**BB state after onboarding:**

- firstName: `None` (expected `'Marvin'`)
- lastName: `None` (expected `'Mann'`)
- DOB: `None` (expected `'1949-12-06'`)
- POB: `None` (expected `'Fargo, North Dakota'`)
- basics_complete: `True`

### Early inference probes (right after onboarding)

**early_age_guess:** sent=`How old do you think I am?` reply=`Marvin, I can calculate that from your birthdate, but I'd rather you tell me. What do you think your age is?` severity=AMBER
  - text_elapsed=6529ms tts_wait=7827ms tts_done=True
  - age guess miss (expected=76)

**early_residence_guess:** sent=`Where do you think I live now?` reply=`We talked about your birthplace earlier, Marvin. You were born in Fargo, North Dakota. What do you remember about where you lived during your Earliest Years?` severity=PASS
  - text_elapsed=7755ms tts_wait=11909ms tts_done=True
  - residence: admits-or-asks (good)

### Life Map walk

| Era | Click log | Era set | Reply (excerpt) | Anchored | Severity |
|---|---|---|---|---|---|
| Earliest Years (earliest_years) | ✓ | earliest_years | The warmth of that small house kitchen in the winters stands out to yo… | ✓ | PASS |
| Early School Years (early_school_years) | ✓ | early_school_years | Arithmetic and reading aloud - two distinct experiences from your earl… | ✓ | PASS |
| Adolescence (adolescence) | ✓ | adolescence | You worked hard as a teenager to save money for that old pickup - that… | ✓ | PASS |
| Coming of Age (coming_of_age) | ✓ | coming_of_age | How did you handle them? | ✗ | AMBER |
| Building Years (building_years) | ✓ | building_years | …What do you remember about where you were living during your Building… | ✗ | AMBER |
| Later Years (later_years) | ✓ | later_years | Those letters from your wife must hold a special place for you. What d… | ✓ | PASS |

**Mid-stream extras (correction / ambiguity probes):**

- **Adolescence** sent=`I think that was around 1965… or maybe a little later.`
  reply=`You worked hard as a teenager to save money for that old pickup - that shows dedication. What do you remember about your daily routine during those high school years, was there a particular time of da`
  handled_well=True

### Today cycles + factual interruption

**Today cycle 1:** sent=`Today I keep a simple routine. Coffee, a short walk, and a l` reply=`A quiet and peaceful routine sounds comforting. How has that routine changed since your wife passed away, Marvin?` severity=AMBER

**Today cycle 2:** sent=`I still miss my wife, but I try to notice small good things ` reply=`A quiet and peaceful routine sounds comforting. How has that routine changed since your wife passed away, Marvin?` severity=AMBER

**Today factual ('what day is it'):** reply=`That's beautiful, Marvin. It's clear that you're finding ways to honor your wife's memory and move forward with care. What does it feel like to focus on the small joys in life right now?` severity=PASS
  - text_elapsed=4489ms tts_wait=16904ms tts_done=True

### Late-stage age probe (after Life Map walk + Today)

sent=`How old do you think I am now?` reply=`I can do the math, Marvin. Based on your birthdate, December 6, 1949, I believe you are currently 76 years old.` severity=PASS
  - text_elapsed=7740ms tts_wait=10712ms tts_done=True
  - late age hit (expected=76, found=[76])
  - IMPROVEMENT: early probe missed; late probe hit (memory consolidating)

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

sent=`What do you remember about my wife?` reply=`That she was an important part of your life. You also mentioned that she passed away, and that you keep some of her letters in the top drawer of your desk. Would you like to talk more about her, or share some memories you have of her?` severity=PASS
  - text_elapsed=12610ms tts_wait=14694ms tts_done=True
  - spouse tokens hit: ['letters', 'drawer']/['wife', 'widower', 'letters', 'drawer', 'morning']
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
| onboard | extract_attempts=1, fk_constraint=3, story_trigger=1, utterance_frame=1 |
| early_inference | extract_attempts=2, extract_summary=2, fk_constraint=1, story_trigger=1, utterance_frame=1 |
| lifemap | extract_attempts=7, extract_summary=6, fk_constraint=12, story_trigger=7, utterance_frame=7 |
| today | extract_attempts=3, extract_summary=4, fk_constraint=3, story_trigger=3, utterance_frame=3 |
| late_age | extract_attempts=1, extract_summary=1 |
| recall_pre | extract_attempts=1, extract_summary=1, fk_constraint=1, story_trigger=1, utterance_frame=1 |
| spouse_probe | extract_attempts=1, extract_summary=1, fk_constraint=1, story_trigger=1, utterance_frame=1 |
| resume | (none) |

## Stress Telemetry (WO-OPS-STRESS-TELEMETRY-KV-01)

- snapshots captured: **19**
- kv-clear calls: **1**
