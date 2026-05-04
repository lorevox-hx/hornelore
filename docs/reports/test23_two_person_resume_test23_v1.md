# TEST-23 Two-Person Resume Canary — `test23_v1`

- started: 2026-05-04T16:40:56
- finished: 2026-05-04T17:07:21
- commit: `772ffac` dirty=True
- base_url: http://localhost:8082/ui/hornelore1.0.html
- api_base: http://localhost:8000

## Topline: **RED**

- Mary Holts (messy): **RED**
- Marvin Mann (clean): **RED**

### Final failures
- Mary RED
- Marvin RED

## Mary Holts (TEST-23) (`mary`) — **RED**

- person_id: `1c823edd-cf9d-4c26-ab56-1c43d1be5a1c`

### Onboarding

| Step | Sent | Reply (excerpt) | Severity | Elapsed |
|---|---|---|---|---:|
| onboard_name | `mary Holts` | …mary, I'm so glad you're here! Now that I know your name, the next piece I'd lo… | PASS | 12551ms |
| onboard_dob | `2/29 1940` | …mary, February 29, 1940 is a unique birthday – I'll make sure to keep that in m… | PASS | 10484ms |
| onboard_pob | `Minot ND` | …Type away - whichever feels more comfortable for you. You can also feel free to… | PASS | 26657ms |
| onboard_pob_correction | `Actually it's Minot, North Dakota — not just ND` | Are you ready to begin sharing your story with me? | PASS | 11411ms |

**BB state after onboarding:**

- firstName: `None` (expected `'Mary'`)
- lastName: `None` (expected `'Holts'`)
- DOB: `None` (expected `'1940-02-29'`)
- POB: `None` (expected `'Minot, North Dakota'`)
- basics_complete: `True`

### Early inference probes (right after onboarding)

**early_age_guess:** sent=`How old do you think I am?` reply=`Are you ready to begin sharing your story with me?` severity=AMBER
  - age guess miss (expected=86)

**early_residence_guess:** sent=`Where do you think I live now?` reply=`You're curious about where I think you live now?` severity=AMBER
  - residence: ambiguous response (review manually)

### Life Map walk

| Era | Click log | Era set | Reply (excerpt) | Anchored | Severity |
|---|---|---|---|---|---|
| Earliest Years (earliest_years) | ✓ | earliest_years | Being born during a storm must have made a vivid impression on you - w… | ✓ | PASS |
| Early School Years (early_school_years) | ✓ | early_school_years |  | ✗ | RED |
| Adolescence (adolescence) | ✓ | adolescence | That lesson about public and private conversation has stuck with you a… | ✓ | PASS |
| Coming of Age (coming_of_age) | ✓ | coming_of_age |  | ✗ | RED |
| Building Years (building_years) | ✓ | building_years | Those years with your family on the move sound like a dynamic time. Wh… | ✗ | AMBER |
| Later Years (later_years) | ✓ | later_years |  | ✗ | RED |

**Mid-stream extras (correction / ambiguity probes):**

- **Building Years** sent=`Actually we only had two kids, not three.`
  reply=`I'll make sure to update my understanding of your family. So, with your two children, what was daily life like for you during those building years, as you navigated parenting and moving around?`
  handled_well=True

### Today cycles + factual interruption

**Today cycle 1:** sent=`These days I take things slower. I like sitting by the windo` reply=`Taking things slower and enjoying the quiet morning moments by the window sounds like a beautiful way to cultivate peace…` severity=PASS

**Today cycle 2:** sent=`I still think about everything that came before, but I try t` reply=`Taking things slower and enjoying the quiet morning moments by the window sounds like a beautiful way to cultivate peace…` severity=PASS

**Today factual ('what day is it'):** reply=`Taking things slower and enjoying the quiet morning moments by the window sounds like a beautiful way to cultivate peace in your life now. What does life look like for you these days - where are you, ` severity=PASS

### Late-stage age probe (after Life Map walk + Today)

sent=`How old do you think I am now?` reply=`Taking things slower and enjoying the quiet morning moments by the window sounds like a beautiful way to cultivate peace in your life now. What does life look like for you these days - where are you, ` severity=AMBER
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

- reply: `Today's date is Monday, May 4th, 2026. Now, shall we continue exploring your life story?`
- severity: **PASS**

### api.log signal counts per phase

| Phase | Signals |
|---|---|
| onboard | extract_attempts=1, fk_constraint=4, story_trigger=1, utterance_frame=1 |
| early_inference | extract_attempts=1, extract_summary=1, fk_constraint=1, story_trigger=1, utterance_frame=1 |
| lifemap | extract_attempts=7, extract_summary=5, fk_constraint=13, story_trigger=7, utterance_frame=7 |
| today | extract_attempts=1, fk_constraint=3, story_trigger=3, utterance_frame=3 |
| late_age | fk_constraint=1 |
| recall_pre | extract_attempts=1, extract_summary=1, fk_constraint=2, memory_echo=1, story_trigger=1, utterance_frame=1 |
| resume | extract_attempts=1, fk_constraint=2, story_trigger=1, utterance_frame=1 |

## Marvin Mann (TEST-23) (`marvin`) — **RED**

- person_id: `8e6a963c-a211-4aef-9f74-470565146ab6`

### Onboarding

| Step | Sent | Reply (excerpt) | Severity | Elapsed |
|---|---|---|---|---:|
| onboard_name | `Marvin Mann` | …Hello Marvin, it's so great to meet you! I'm glad you're here to share your sto… | PASS | 14593ms |
| onboard_dob | `December 6, 1949` | …A particular region that feels like home to you? | PASS | 13232ms |
| onboard_pob | `Fargo, North Dakota` | …If you do choose to use it, I'll be able to see your expression and adjust our … | PASS | 24294ms |
| status_seed | `I am a widower now, I still think about my wife ev` | You're still thinking about your wife every morning, Marvin. That must be very d… | PASS | 8582ms |

**BB state after onboarding:**

- firstName: `None` (expected `'Marvin'`)
- lastName: `None` (expected `'Mann'`)
- DOB: `None` (expected `'1949-12-06'`)
- POB: `None` (expected `'Fargo, North Dakota'`)
- basics_complete: `True`

### Early inference probes (right after onboarding)

**early_age_guess:** sent=`How old do you think I am?` reply=`You're still thinking about your wife every morning, Marvin. That must be very difficult for you. What was your life like in Fargo, North Dakota, where you grew up?` severity=AMBER
  - age guess miss (expected=76)

**early_residence_guess:** sent=`Where do you think I live now?` reply=`You're still thinking about your wife every morning, Marvin. That must be very difficult for you. What was your life like in Fargo, North Dakota, where you grew up?` severity=AMBER
  - residence: name dropped POB without 'born in' framing (ambiguous)

### Life Map walk

| Era | Click log | Era set | Reply (excerpt) | Anchored | Severity |
|---|---|---|---|---|---|
| Earliest Years (earliest_years) | ✓ | earliest_years |  | ✗ | RED |
| Early School Years (early_school_years) | ✓ | early_school_years | Were there any particular teachers or friends who stood out to you? | ✗ | AMBER |
| Adolescence (adolescence) | ✓ | adolescence |  | ✗ | RED |
| Coming of Age (coming_of_age) | ✓ | coming_of_age |  | ✗ | RED |
| Building Years (building_years) | ✓ | building_years | You and your wife built a life together, buying a house, raising child… | ✓ | PASS |
| Later Years (later_years) | ✓ | later_years |  | ✗ | RED |

**Mid-stream extras (correction / ambiguity probes):**

- **Adolescence** sent=`I think that was around 1965… or maybe a little later.`
  reply=`So that was around 1965, or maybe a bit later. Last time we were talking about your education. Shall we continue there?`
  handled_well=True

### Today cycles + factual interruption

**Today cycle 1:** sent=`Today I keep a simple routine. Coffee, a short walk, and a l` reply=`You're maintaining a quiet routine these days, Marvin. It sounds peaceful. What does a typical day look like for you now…` severity=PASS

**Today cycle 2:** sent=`I still miss my wife, but I try to notice small good things ` reply=`You're maintaining a quiet routine these days, Marvin. It sounds peaceful. What does a typical day look like for you now…` severity=PASS

**Today factual ('what day is it'):** reply=`You're maintaining a quiet routine these days, Marvin. It sounds peaceful. What does a typical day look like for you now, beyond just those quiet moments?` severity=PASS

### Late-stage age probe (after Life Map walk + Today)

sent=`How old do you think I am now?` reply=`You're maintaining a quiet routine these days, Marvin. It sounds peaceful. What does a typical day look like for you now, beyond just those quiet moments?` severity=AMBER
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

sent=`What do you remember about my wife?` reply=`What I know about Marvin Mann so far:

Identity
- Name: Marvin Mann
- Date of birth: 1949-12-06
- Place of birth: Fargo, North Dakota

Family
- Parents: (none on record yet)
- Siblings: (none on recor` severity=RED
  - spouse tokens hit: []/['wife', 'widower', 'letters', 'drawer', 'morning']
  - FAILED emotional anchoring (0 spouse tokens recalled)

### Post-restart memory recall (after browser context reopen)

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

### Today after resume ('what day is it')

- reply: ``
- severity: **RED**

### api.log signal counts per phase

| Phase | Signals |
|---|---|
| onboard | extract_attempts=1, fk_constraint=4, story_trigger=1, utterance_frame=1 |
| early_inference | fk_constraint=1, story_trigger=1, utterance_frame=1 |
| lifemap | extract_attempts=7, extract_summary=8, fk_constraint=12, story_trigger=7, utterance_frame=7 |
| today | extract_attempts=1, fk_constraint=4, story_trigger=3, utterance_frame=3 |
| late_age | fk_constraint=1 |
| recall_pre | extract_attempts=1, fk_constraint=1, memory_echo=1, story_trigger=1, utterance_frame=1 |
| spouse_probe | fk_constraint=1, story_trigger=1, utterance_frame=1 |
| resume | extract_attempts=2, extract_summary=2, fk_constraint=2, memory_echo=1, story_trigger=1, utterance_frame=1 |

## Stress Telemetry (WO-OPS-STRESS-TELEMETRY-KV-01)

- snapshots captured: **19**
- kv-clear calls: **1**
