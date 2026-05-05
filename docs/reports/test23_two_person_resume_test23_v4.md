# TEST-23 Two-Person Resume Canary — `test23_v4`

- started: 2026-05-04T21:17:41
- finished: 2026-05-04T21:50:58
- commit: `23a090e` dirty=False
- base_url: http://localhost:8082/ui/hornelore1.0.html
- api_base: http://localhost:8000

## Topline: **RED**

- Mary Holts (messy): **RED**
- Marvin Mann (clean): **RED**

### Final failures
- Mary RED
- Marvin RED

## Mary Holts (TEST-23) (`mary`) — **RED**

- person_id: `6d6af75c-b987-44b0-bba8-090d2cae5dd9`

### Onboarding

| Step | Sent | Reply (excerpt) | Severity | Elapsed |
|---|---|---|---|---:|
| onboard_name | `mary Holts` | …mary, it's wonderful to meet you and start this project together. Knowing your … | PASS | 28345ms |
| onboard_dob | `2/29 1940` | …That's lovely, mary – February 29th, 1940. That's a great starting point for us… | PASS | 22788ms |
| onboard_pob | `Minot ND` | …Type what you'd like to say – whatever feels more comfortable for you is perfec… | PASS | 42124ms |
| onboard_pob_correction | `Actually it's Minot, North Dakota — not just ND` | Are you ready to begin sharing your story? | PASS | 12243ms |

**BB state after onboarding:**

- firstName: `None` (expected `'Mary'`)
- lastName: `None` (expected `'Holts'`)
- DOB: `None` (expected `'1940-02-29'`)
- POB: `None` (expected `'Minot, North Dakota'`)
- basics_complete: `True`

### Early inference probes (right after onboarding)

**early_age_guess:** sent=`How old do you think I am?` reply=`Based on what you've shared so far, I believe you were born on February 29, 1940, which would make you currently 86 years old. Am I right, mary?` severity=PASS
  - text_elapsed=7717ms tts_wait=12172ms tts_done=True
  - age guess hit (expected=86, found=[86])

**early_residence_guess:** sent=`Where do you think I live now?` reply=`I have Minot, North Dakota, as your earliest home. What comes to mind when you picture those years there?` severity=AMBER
  - text_elapsed=6098ms tts_wait=7176ms tts_done=True
  - residence: name dropped POB without 'born in' framing (ambiguous)

### Life Map walk

| Era | Click log | Era set | Reply (excerpt) | Anchored | Severity |
|---|---|---|---|---|---|
| Earliest Years (earliest_years) | ✓ | earliest_years | A stormy birth, that's a vivid image! I have Minot, North Dakota, as y… | ✓ | PASS |
| Early School Years (early_school_years) | ✓ | early_school_years | Walking to school through the snow with your brother – that's a beauti… | ✓ | PASS |
| Adolescence (adolescence) | ✓ | adolescence | You learned early on that there were certain things to consider when s… | ✓ | PASS |
| Coming of Age (coming_of_age) | ✓ | coming_of_age | Meeting your husband at the county fair is a lovely start to a story –… | ✓ | PASS |
| Building Years (building_years) | ✓ | building_years | With children and moving around for your husband's work, those years m… | ✓ | AMBER |
| Later Years (later_years) | ✓ | later_years | The silence after his passing must have been difficult to adjust to. I… | ✗ | AMBER |

**Mid-stream extras (correction / ambiguity probes):**

- **Building Years** sent=`Actually we only had two kids, not three.`
  reply=`With children and moving around for your husband's work, those years must have been a whirlwind. What do you remember about the sense of community and connection you felt in the places you lived durin`
  handled_well=False

### Today cycles + factual interruption

**Today cycle 1:** sent=`These days I take things slower. I like sitting by the windo` reply=`It sounds like you've found a peaceful rhythm in your life lately, mary. Sitting by the window in the morning must be a …` severity=AMBER

**Today cycle 2:** sent=`I still think about everything that came before, but I try t` reply=`It sounds like you're navigating a delicate balance between reflecting on the past and being present in the present. How…` severity=AMBER

**Today factual ('what day is it'):** reply=`It sounds like you're navigating a delicate balance between reflecting on the past and being present in the present. How do you find the time to stay engaged with the world around you, even as you're ` severity=PASS
  - text_elapsed=3248ms tts_wait=11514ms tts_done=True

### Late-stage age probe (after Life Map walk + Today)

sent=`How old do you think I am now?` reply=`It's Monday, May 4th, 2026. Shall we continue where we left off, mary?` severity=RED
  - text_elapsed=6515ms tts_wait=12841ms tts_done=True
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
| onboard | extract_attempts=1, fk_constraint=3, story_trigger=1, utterance_frame=1 |
| early_inference | extract_attempts=2, extract_summary=1, fk_constraint=1, story_trigger=1, utterance_frame=1 |
| lifemap | extract_attempts=7, extract_summary=6, fk_constraint=12, story_trigger=7, utterance_frame=7 |
| today | extract_attempts=3, extract_summary=3, fk_constraint=4, story_trigger=3, utterance_frame=3 |
| late_age | extract_attempts=1, extract_summary=1 |
| recall_pre | extract_attempts=1, extract_summary=1, fk_constraint=2, story_trigger=1, utterance_frame=1 |
| resume | (none) |

## Marvin Mann (TEST-23) (`marvin`) — **RED**

- person_id: `5cf82c66-446c-4986-91ce-72dfab13c49b`

### Onboarding

| Step | Sent | Reply (excerpt) | Severity | Elapsed |
|---|---|---|---|---:|
| onboard_name | `Marvin Mann` | …Marvin Mann, nice to meet you. Knowing your date of birth will help me place yo… | PASS | 25414ms |
| onboard_dob | `December 6, 1949` | …You were born on December 6, 1949. That's a great starting point. Where were yo… | PASS | 18000ms |
| onboard_pob | `Fargo, North Dakota` | …Type — whatever feels more natural to you. I'll be speaking my responses aloud … | PASS | 40858ms |
| status_seed | `I am a widower now, I still think about my wife ev` | Marvin Mann, I'm so sorry for your loss. It's beautiful that you still have her … | PASS | 14655ms |

**BB state after onboarding:**

- firstName: `None` (expected `'Marvin'`)
- lastName: `None` (expected `'Mann'`)
- DOB: `None` (expected `'1949-12-06'`)
- POB: `None` (expected `'Fargo, North Dakota'`)
- basics_complete: `True`

### Early inference probes (right after onboarding)

**early_age_guess:** sent=`How old do you think I am?` reply=`Marvin Mann, I'm so sorry for your loss. It's beautiful that you still have her in your thoughts every morning.` severity=AMBER
  - text_elapsed=5307ms tts_wait=26823ms tts_done=True
  - age guess miss (expected=76)

**early_residence_guess:** sent=`Where do you think I live now?` reply=`Last time we were talking about your life, you shared that you're thinking about your wife every morning. Shall we continue exploring your story and see where it takes us?` severity=AMBER
  - text_elapsed=7337ms tts_wait=11567ms tts_done=True
  - residence: ambiguous response (review manually)

### Life Map walk

| Era | Click log | Era set | Reply (excerpt) | Anchored | Severity |
|---|---|---|---|---|---|
| Earliest Years (earliest_years) | ✓ | earliest_years | That small house in Fargo sounds cozy, especially with the warm kitche… | ✓ | PASS |
| Early School Years (early_school_years) | ✓ | early_school_years | Arithmetic was a highlight for you, and reading out loud was a bit cha… | ✓ | PASS |
| Adolescence (adolescence) | ✓ | adolescence | Working after school and saving up for an old pickup - that's a great … | ✓ | PASS |
| Coming of Age (coming_of_age) | ✓ | coming_of_age | Leaving home for your first steady job was a big step, and learning ab… | ✓ | PASS |
| Building Years (building_years) | ✓ | building_years | Building a life together, buying a house, raising children, and workin… | ✓ | PASS |
| Later Years (later_years) | ✓ | later_years | Those letters are a special reminder of your wife's love and presence … | ✓ | PASS |

**Mid-stream extras (correction / ambiguity probes):**

- **Adolescence** sent=`I think that was around 1965… or maybe a little later.`
  reply=`Working after school and saving up for an old pickup - that's a great memory. What do you remember about your daily routine during those after-school hours?`
  handled_well=True

### Today cycles + factual interruption

**Today cycle 1:** sent=`Today I keep a simple routine. Coffee, a short walk, and a l` reply=`What does a normal day feel like?` severity=AMBER

**Today cycle 2:** sent=`I still miss my wife, but I try to notice small good things ` reply=`What does a normal day feel like?` severity=AMBER

**Today factual ('what day is it'):** reply=`Marvin Mann, it's Monday, May 4th, 2026. Shall we continue exploring your story from where we left off?` severity=PASS
  - text_elapsed=11027ms tts_wait=9377ms tts_done=True

### Late-stage age probe (after Life Map walk + Today)

sent=`How old do you think I am now?` reply=`Marvin Mann, it's Monday, May 4th, 2026. Shall we continue exploring your story from where we left off?` severity=AMBER
  - text_elapsed=405ms tts_wait=17455ms tts_done=True
  - late age miss (expected=76)

### Pre-restart memory recall (Earliest Years anchor + 'what do you know about me')

- name recalled: True
- DOB/year recalled: True
- POB recalled: True
- era facts recalled: 0/7
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
- Siblings: (none on recor`

### Spouse memory probe (Marvin only — emotional anchoring + attribution)

sent=`What do you remember about my wife?` reply=`Marvin Mann, I've been listening to your story and I remember that you mentioned your wife earlier. She was a loving partner who passed away, leaving you with cherished memories and mementos, like the` severity=AMBER
  - text_elapsed=10174ms tts_wait=14983ms tts_done=True
  - spouse tokens hit: ['wife']/['wife', 'widower', 'letters', 'drawer', 'morning']
  - partial recall (1 spouse token)

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
| early_inference | extract_attempts=2, extract_summary=3, fk_constraint=1, story_trigger=1, utterance_frame=1 |
| lifemap | extract_attempts=7, extract_summary=6, fk_constraint=13, story_trigger=7, utterance_frame=7 |
| today | extract_attempts=3, extract_summary=4, fk_constraint=3, story_trigger=3, utterance_frame=3 |
| late_age | extract_attempts=1, extract_summary=1, fk_constraint=1 |
| recall_pre | extract_attempts=1, extract_summary=1, fk_constraint=1, story_trigger=1, utterance_frame=1 |
| spouse_probe | extract_attempts=1, extract_summary=1 |
| resume | (none) |

## Stress Telemetry (WO-OPS-STRESS-TELEMETRY-KV-01)

- snapshots captured: **19**
- kv-clear calls: **1**
