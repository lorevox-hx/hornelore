# TEST-23 Two-Person Resume Canary — `test23_v10`

- started: 2026-05-06T13:48:20
- finished: 2026-05-06T14:14:06
- commit: `bbd7971` dirty=False
- base_url: http://localhost:8082/ui/hornelore1.0.html
- api_base: http://localhost:8000

## Topline: **RED**

- Mary Holts (messy): **RED**
- Marvin Mann (clean): **RED**

### Final failures
- Mary RED
- Marvin RED

## Mary Holts (TEST-23) (`mary`) — **RED**

- person_id: `c813874b-95da-43b2-a738-7ff289340603`

### Onboarding

| Step | Sent | Reply (excerpt) | Severity | Elapsed |
|---|---|---|---|---:|
| onboard_name | `mary Holts` | It's lovely to meet you, mary. Knowing when you were born will really help me pl… | PASS | 26188ms |
| onboard_dob | `2/29 1940` | February 29, 1940 - that's a unique birthday! Where were you born, mary? | PASS | 15720ms |
| onboard_pob | `Minot ND` | Chat error: Chat backend error: cannot access local variable '_seed_age_years' w… | PASS | 14646ms |
| onboard_pob_correction | `Actually it's Minot, North Dakota — not just ND` | I heard that as a correction, but I'm not fully certain which field it changes y… | PASS | 15376ms |

**BB state after onboarding:**

- firstName: `None` (expected `'Mary'`)
- lastName: `None` (expected `'Holts'`)
- DOB: `None` (expected `'1940-02-29'`)
- POB: `None` (expected `'Minot, North Dakota'`)
- basics_complete: `True`

### Early inference probes (right after onboarding)

**early_age_guess:** sent=`How old do you think I am?` reply=`Chat error: Chat backend error: cannot access local variable '_seed_age_years' where it is not associated with a value. Try again.` severity=AMBER
  - text_elapsed=1638ms tts_wait=9955ms tts_done=True
  - age guess miss (expected=86)

**early_residence_guess:** sent=`Where do you think I live now?` reply=`Chat error: Chat backend error: cannot access local variable '_seed_age_years' where it is not associated with a value. Try again.` severity=AMBER
  - text_elapsed=2472ms tts_wait=9985ms tts_done=True
  - residence: ambiguous response (review manually)

### Life Map walk

| Era | Click log | Era set | Reply (excerpt) | Anchored | Severity |
|---|---|---|---|---|---|
| Earliest Years (earliest_years) | ✓ | earliest_years | Chat error: Chat backend error: cannot access local variable '_seed_ag… | ✗ | AMBER |
| Early School Years (early_school_years) | ✓ | early_school_years | Chat error: Chat backend error: cannot access local variable '_seed_ag… | ✗ | AMBER |
| Adolescence (adolescence) | ✓ | adolescence | Chat error: Chat backend error: cannot access local variable '_seed_ag… | ✗ | AMBER |
| Coming of Age (coming_of_age) | ✓ | coming_of_age | Chat error: Chat backend error: cannot access local variable '_seed_ag… | ✗ | AMBER |
| Building Years (building_years) | ✓ | building_years | Chat error: Chat backend error: cannot access local variable '_seed_ag… | ✗ | AMBER |
| Later Years (later_years) | ✓ | later_years | Chat error: Chat backend error: cannot access local variable '_seed_ag… | ✗ | AMBER |

**Mid-stream extras (correction / ambiguity probes):**

- **Building Years** sent=`Actually we only had two kids, not three.`
  reply=`I heard that as a correction, but I'm not fully certain which field it changes yet. You can say it one piece at a time — for example, 'I was born in ...' or 'My father's name was ...'.`
  handled_well=True

### Today cycles + factual interruption

**Today cycle 1:** sent=`These days I take things slower. I like sitting by the windo` reply=`Chat error: Chat backend error: cannot access local variable '_seed_age_years' where it is not associated with a value. …` severity=AMBER

**Today cycle 2:** sent=`I still think about everything that came before, but I try t` reply=`Chat error: Chat backend error: cannot access local variable '_seed_age_years' where it is not associated with a value. …` severity=AMBER

**Today factual ('what day is it'):** reply=`Chat error: Chat backend error: cannot access local variable '_seed_age_years' where it is not associated with a value. Try again.` severity=PASS
  - text_elapsed=7321ms tts_wait=9396ms tts_done=True

### Late-stage age probe (after Life Map walk + Today)

sent=`How old do you think I am now?` reply=`Chat error: Chat backend error: cannot access local variable '_seed_age_years' where it is not associated with a value. Try again.` severity=AMBER
  - text_elapsed=3266ms tts_wait=12878ms tts_done=True
  - late age miss (expected=86)

### Pre-restart memory recall (Earliest Years anchor + 'what do you know about me')

- name recalled: False
- DOB/year recalled: False
- POB recalled: False
- era stories in readback: 0/7  (memory_echo readback content; NOT a measure of era-click navigation)
- cross-contamination: False
- onboarding restart: False
- severity: **RED**

Reply excerpt: `Chat error: Chat backend error: cannot access local variable '_seed_age_years' where it is not associated with a value. Try again.`

### Post-restart memory recall (after browser context reopen)

- name recalled: True
- DOB/year recalled: True
- POB recalled: True
- era stories in readback: 1/7  (memory_echo readback content; NOT a measure of era-click navigation)
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
- Life stage: senior elder

What I'm less sure about
- Some parts are still blank, and that is completely fine. You can correct or add one thing at a time, whenev…`

### Today after resume ('what day is it')

- reply: ``
- severity: **RED**

### api.log signal counts per phase

| Phase | Signals |
|---|---|
| onboard | extract_attempts=1, fk_constraint=3, story_trigger=1, utterance_frame=1 |
| early_inference | extract_attempts=2, extract_summary=1, fk_constraint=1, story_trigger=1, utterance_frame=1 |
| lifemap | extract_attempts=6, extract_summary=1, fk_constraint=13, story_trigger=7, utterance_frame=7 |
| today | extract_summary=2, fk_constraint=4, story_trigger=3, utterance_frame=3 |
| late_age | fk_constraint=1 |
| recall_pre | extract_attempts=1, fk_constraint=2, story_trigger=1, utterance_frame=1 |
| resume | extract_attempts=1, extract_summary=2, fk_constraint=1, story_trigger=1, utterance_frame=1 |

## Marvin Mann (TEST-23) (`marvin`) — **RED**

- person_id: `3e0ec01d-97ed-4b94-8d8b-3aa35124f35a`

### Onboarding

| Step | Sent | Reply (excerpt) | Severity | Elapsed |
|---|---|---|---|---:|
| onboard_name | `Marvin Mann` | Chat error: Chat backend error: cannot access local variable '_seed_age_years' w… | PASS | 11808ms |
| onboard_dob | `December 6, 1949` | Chat error: Chat backend error: cannot access local variable '_seed_age_years' w… | PASS | 11820ms |
| onboard_pob | `Fargo, North Dakota` | Chat error: Chat backend error: cannot access local variable '_seed_age_years' w… | PASS | 11791ms |
| status_seed | `I am a widower now, I still think about my wife ev` | Chat error: Chat backend error: cannot access local variable '_seed_age_years' w… | PASS | 11367ms |

**BB state after onboarding:**

- firstName: `None` (expected `'Marvin'`)
- lastName: `None` (expected `'Mann'`)
- DOB: `None` (expected `'1949-12-06'`)
- POB: `None` (expected `'Fargo, North Dakota'`)
- basics_complete: `False`

### Early inference probes (right after onboarding)

**early_age_guess:** sent=`How old do you think I am?` reply=`Chat error: Chat backend error: cannot access local variable '_seed_age_years' where it is not associated with a value. Try again.` severity=AMBER
  - text_elapsed=1250ms tts_wait=9458ms tts_done=True
  - age guess miss (expected=76)

**early_residence_guess:** sent=`Where do you think I live now?` reply=`Chat error: Chat backend error: cannot access local variable '_seed_age_years' where it is not associated with a value. Try again.` severity=AMBER
  - text_elapsed=1634ms tts_wait=9441ms tts_done=True
  - residence: ambiguous response (review manually)

### Life Map walk

| Era | Click log | Era set | Reply (excerpt) | Anchored | Severity |
|---|---|---|---|---|---|
| Earliest Years (earliest_years) | ✓ | earliest_years | Chat error: Chat backend error: cannot access local variable '_seed_ag… | ✗ | AMBER |
| Early School Years (early_school_years) | ✓ | early_school_years | Chat error: Chat backend error: cannot access local variable '_seed_ag… | ✗ | AMBER |
| Adolescence (adolescence) | ✓ | adolescence | Chat error: Chat backend error: cannot access local variable '_seed_ag… | ✗ | AMBER |
| Coming of Age (coming_of_age) | ✓ | coming_of_age | Chat error: Chat backend error: cannot access local variable '_seed_ag… | ✗ | AMBER |
| Building Years (building_years) | ✓ | building_years | Chat error: Chat backend error: cannot access local variable '_seed_ag… | ✗ | AMBER |
| Later Years (later_years) | ✓ | later_years | Chat error: Chat backend error: cannot access local variable '_seed_ag… | ✗ | AMBER |

**Mid-stream extras (correction / ambiguity probes):**

- **Adolescence** sent=`I think that was around 1965… or maybe a little later.`
  reply=`Chat error: Chat backend error: cannot access local variable '_seed_age_years' where it is not associated with a value. Try again.`
  handled_well=True

### Today cycles + factual interruption

**Today cycle 1:** sent=`Today I keep a simple routine. Coffee, a short walk, and a l` reply=`Chat error: Chat backend error: cannot access local variable '_seed_age_years' where it is not associated with a value. …` severity=AMBER

**Today cycle 2:** sent=`I still miss my wife, but I try to notice small good things ` reply=`Chat error: Chat backend error: cannot access local variable '_seed_age_years' where it is not associated with a value. …` severity=AMBER

**Today factual ('what day is it'):** reply=`Chat error: Chat backend error: cannot access local variable '_seed_age_years' where it is not associated with a value. Try again.` severity=PASS
  - text_elapsed=4901ms tts_wait=10409ms tts_done=True

### Late-stage age probe (after Life Map walk + Today)

sent=`How old do you think I am now?` reply=`Chat error: Chat backend error: cannot access local variable '_seed_age_years' where it is not associated with a value. Try again.` severity=AMBER
  - text_elapsed=4092ms tts_wait=13259ms tts_done=True
  - late age miss (expected=76)

### Pre-restart memory recall (Earliest Years anchor + 'what do you know about me')

- name recalled: False
- DOB/year recalled: False
- POB recalled: False
- era stories in readback: 0/7  (memory_echo readback content; NOT a measure of era-click navigation)
- cross-contamination: False
- onboarding restart: False
- severity: **RED**

Reply excerpt: `Chat error: Chat backend error: cannot access local variable '_seed_age_years' where it is not associated with a value. Try again.`

### Spouse memory probe (Marvin only — emotional anchoring + attribution)

sent=`What do you remember about my wife?` reply=`Chat error: Chat backend error: cannot access local variable '_seed_age_years' where it is not associated with a value. Try again.` severity=RED
  - text_elapsed=7729ms tts_wait=9748ms tts_done=True
  - spouse tokens hit: []/['wife', 'widower', 'letters', 'drawer', 'morning']
  - FAILED emotional anchoring (0 spouse tokens recalled)

### Post-restart memory recall (after browser context reopen)

- name recalled: False
- DOB/year recalled: False
- POB recalled: False
- era stories in readback: 0/7  (memory_echo readback content; NOT a measure of era-click navigation)
- cross-contamination: False
- onboarding restart: False
- severity: **RED**

Reply excerpt: `What I know about you so far:

Identity
- Name: (not on record yet)
- Date of birth: (not on record yet)
- Place of birth: (not on record yet)

Family
- Parents: (none on record yet)
- Siblings: (none on record yet)

What I'm less sure about
- Some parts are still blank, and that is completely fine. You can correct or add one thing at a time, whenever you'd like.
- Anything you mention now I'll ke…`

### Today after resume ('what day is it')

- reply: `Chat error: Chat backend error: cannot access local variable '_seed_age_years' where it is not associated with a value. Try again.`
- severity: **PASS**

### api.log signal counts per phase

| Phase | Signals |
|---|---|
| onboard | extract_attempts=4, extract_summary=3, fk_constraint=3, story_trigger=3, utterance_frame=3 |
| early_inference | extract_attempts=2, extract_summary=2, fk_constraint=2, story_trigger=2, utterance_frame=2 |
| lifemap | extract_attempts=6, extract_summary=1, fk_constraint=13, story_trigger=7, utterance_frame=7 |
| today | extract_attempts=1, extract_summary=2, fk_constraint=4, story_trigger=3, utterance_frame=3 |
| late_age | extract_attempts=1, fk_constraint=1 |
| recall_pre | fk_constraint=2, story_trigger=1, utterance_frame=1 |
| spouse_probe | extract_attempts=1, fk_constraint=1 |
| resume | extract_attempts=1, fk_constraint=3, story_trigger=2, utterance_frame=2 |

## Stress Telemetry (WO-OPS-STRESS-TELEMETRY-KV-01)

- snapshots captured: **18**
- kv-clear calls: **0**
