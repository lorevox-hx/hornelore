# TEST-23 Two-Person Resume Canary — `test23_v2`

- started: 2026-05-04T17:29:08
- finished: 2026-05-04T17:59:39
- commit: `da6756d` dirty=False
- base_url: http://localhost:8082/ui/hornelore1.0.html
- api_base: http://localhost:8000

## Topline: **RED**

- Mary Holts (messy): **RED**
- Marvin Mann (clean): **RED**

### Final failures
- Mary RED
- Marvin RED

## Mary Holts (TEST-23) (`mary`) — **RED**

- person_id: `ae4674ec-47d5-4272-8b6e-d095b01bce9a`

### Onboarding

| Step | Sent | Reply (excerpt) | Severity | Elapsed |
|---|---|---|---|---:|
| onboard_name | `mary Holts` | …mary, it's such a pleasure to meet you and start this project together. Now, I'… | PASS | 28773ms |
| onboard_dob | `2/29 1940` | …You were born on February 29th, 1940, what a unique birthday! Now, I'd love to … | PASS | 20555ms |
| onboard_pob | `Minot ND` | …Minot, North Dakota, is where you began your life journey. Before we start expl… | PASS | 42990ms |
| onboard_pob_correction | `Actually it's Minot, North Dakota — not just ND` | You can turn it on or off whenever you like. Now, do you have any questions abou… | PASS | 32726ms |

**BB state after onboarding:**

- firstName: `None` (expected `'Mary'`)
- lastName: `None` (expected `'Holts'`)
- DOB: `None` (expected `'1940-02-29'`)
- POB: `None` (expected `'Minot, North Dakota'`)
- basics_complete: `True`

### Early inference probes (right after onboarding)

**early_age_guess:** sent=`How old do you think I am?` reply=`Based on what you've shared so far, I believe you were born in 1940, which makes you 86 years young! Is that correct, mary?` severity=PASS
  - text_elapsed=6504ms tts_wait=10622ms tts_done=True
  - age guess hit (expected=86, found=[86])

**early_residence_guess:** sent=`Where do you think I live now?` reply=`We were just getting started on your life story, and now we've jumped ahead a bit. Why don't we go back to where we left off?` severity=AMBER
  - text_elapsed=8132ms tts_wait=8133ms tts_done=True
  - residence: ambiguous response (review manually)

### Life Map walk

| Era | Click log | Era set | Reply (excerpt) | Anchored | Severity |
|---|---|---|---|---|---|
| Earliest Years (earliest_years) | ✓ | earliest_years | Being born during a storm is a unique experience. A cold winter birth … | ✓ | PASS |
| Early School Years (early_school_years) | ✓ | early_school_years | Walking to school with your brother through the snow sounds like a bea… | ✓ | PASS |
| Adolescence (adolescence) | ✓ | adolescence | You learned early on that there were things you said in public and thi… | ✓ | PASS |
| Coming of Age (coming_of_age) | ✓ | coming_of_age | It sounds like a lovely start to a romance. What was it about your int… | ✓ | PASS |
| Building Years (building_years) | ✓ | building_years | How did you adapt to each new community? | ✗ | AMBER |
| Later Years (later_years) | ✓ | later_years | The quiet house must have been a big change for you. How did you find … | ✓ | PASS |

**Mid-stream extras (correction / ambiguity probes):**

- **Building Years** sent=`Actually we only had two kids, not three.`
  reply=`It's understandable to have a variation in memory. mary, would you like to revisit that part of your story or move forward?`
  handled_well=False

### Today cycles + factual interruption

**Today cycle 1:** sent=`These days I take things slower. I like sitting by the windo` reply=`` severity=RED

**Today cycle 2:** sent=`I still think about everything that came before, but I try t` reply=`It's clear that you're reflecting on your life and experiences. That can be a challenging but ultimately rewarding proce…` severity=AMBER

**Today factual ('what day is it'):** reply=`It's clear that you're reflecting on your life and experiences. That can be a challenging but ultimately rewarding process. Are you finding comfort in your daily routines and the simple pleasures of l` severity=PASS
  - text_elapsed=7307ms tts_wait=12413ms tts_done=True

### Late-stage age probe (after Life Map walk + Today)

sent=`How old do you think I am now?` reply=`According to your device, it's currently Monday, May 4, 2026. Shall we continue talking about your day and how you're enjoying the quiet moments by the window?` severity=RED
  - text_elapsed=2432ms tts_wait=10907ms tts_done=True
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
| onboard | extract_attempts=1, extract_summary=1, fk_constraint=3, story_trigger=1, utterance_frame=1 |
| early_inference | extract_attempts=2, extract_summary=2, fk_constraint=2, story_trigger=1, utterance_frame=1 |
| lifemap | extract_attempts=7, extract_summary=6, fk_constraint=12, story_trigger=7, utterance_frame=7 |
| today | extract_attempts=3, extract_summary=4, fk_constraint=3, story_trigger=3, utterance_frame=3 |
| late_age | extract_attempts=1, fk_constraint=1 |
| recall_pre | extract_attempts=1, extract_summary=1, fk_constraint=2, memory_echo=1, story_trigger=1, utterance_frame=1 |
| resume | (none) |

## Marvin Mann (TEST-23) (`marvin`) — **RED**

- person_id: `281398f2-6e19-457f-b30f-1650e20d84ec`

### Onboarding

| Step | Sent | Reply (excerpt) | Severity | Elapsed |
|---|---|---|---|---:|
| onboard_name | `Marvin Mann` | …Marvin Mann, I'm so glad we're starting this project together! Now, could you t… | PASS | 30664ms |
| onboard_dob | `December 6, 1949` | …Region comes to mind for you? | PASS | 9702ms |
| onboard_pob | `Fargo, North Dakota` | …Are you ready to begin building your Life Archive? | PASS | 22295ms |
| status_seed | `I am a widower now, I still think about my wife ev` | Marvin Mann, I'm so sorry to hear that you're a widower. That's a tender spot to… | PASS | 14206ms |

**BB state after onboarding:**

- firstName: `None` (expected `'Marvin'`)
- lastName: `None` (expected `'Mann'`)
- DOB: `None` (expected `'1949-12-06'`)
- POB: `None` (expected `'Fargo, North Dakota'`)
- basics_complete: `True`

### Early inference probes (right after onboarding)

**early_age_guess:** sent=`How old do you think I am?` reply=`Marvin Mann, I'm so sorry to hear that you're a widower. That's a tender spot to start our conversation.` severity=AMBER
  - text_elapsed=7744ms tts_wait=16482ms tts_done=True
  - age guess miss (expected=76)

**early_residence_guess:** sent=`Where do you think I live now?` reply=`I'd love to explore that with you. What do you remember about where you are living currently?` severity=AMBER
  - text_elapsed=4900ms tts_wait=6580ms tts_done=True
  - residence: ambiguous response (review manually)

### Life Map walk

| Era | Click log | Era set | Reply (excerpt) | Anchored | Severity |
|---|---|---|---|---|---|
| Earliest Years (earliest_years) | ✓ | earliest_years | That small house with the warm kitchen - that's a lovely image. What d… | ✓ | PASS |
| Early School Years (early_school_years) | ✓ | early_school_years | Arithmetic brought out a fondness in you, while reading out loud made … | ✓ | PASS |
| Adolescence (adolescence) | ✓ | adolescence | Working after school to save for that old pickup - that shows initiati… | ✓ | PASS |
| Coming of Age (coming_of_age) | ✓ | coming_of_age | Leaving home for your first steady job and learning about responsibili… | ✓ | PASS |
| Building Years (building_years) | ✓ | building_years | Starting a family - that's a wonderful foundation. What do you remembe… | ✗ | AMBER |
| Later Years (later_years) | ✓ | later_years | How her presence continued to shape your daily routines after she pass… | ✗ | AMBER |

**Mid-stream extras (correction / ambiguity probes):**

- **Adolescence** sent=`I think that was around 1965… or maybe a little later.`
  reply=`Working after school to save for that old pickup - that shows initiative. What do you remember about the daily routine of having a part-time job during your teenage years?`
  handled_well=True

### Today cycles + factual interruption

**Today cycle 1:** sent=`Today I keep a simple routine. Coffee, a short walk, and a l` reply=`` severity=RED

**Today cycle 2:** sent=`I still miss my wife, but I try to notice small good things ` reply=`Noticing the small good things each day - that's a beautiful way to honor your wife's memory. What role does gratitude p…` severity=AMBER

**Today factual ('what day is it'):** reply=`According to my device, today's date is Monday, May 4, 2026.` severity=PASS
  - text_elapsed=5692ms tts_wait=5910ms tts_done=True

### Late-stage age probe (after Life Map walk + Today)

sent=`How old do you think I am now?` reply=`Marvin Mann, since you were born in 1949, I believe you are currently 76 years old, given today's date of May 4, 2026.` severity=PASS
  - text_elapsed=7739ms tts_wait=11564ms tts_done=True
  - late age hit (expected=76, found=[76])
  - IMPROVEMENT: early probe missed; late probe hit (memory consolidating)

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

sent=`What do you remember about my wife?` reply=`Marvin Mann, I'm so glad you're willing to share more about your wife. From our previous conversations, I remember that she was a loving partner who played a significant role in your life, especially ` severity=AMBER
  - text_elapsed=14662ms tts_wait=22421ms tts_done=True
  - spouse tokens hit: ['wife']/['wife', 'widower', 'letters', 'drawer', 'morning']
  - partial recall (1 spouse token)

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

- reply: `Today's date is Monday, May 4, 2026. Would you like to share what's on your mind or what's been going on in your life lately? (We can come back to the rest in a moment.)`
- severity: **PASS**

### api.log signal counts per phase

| Phase | Signals |
|---|---|
| onboard | extract_attempts=1, fk_constraint=4, story_trigger=1, utterance_frame=1 |
| early_inference | extract_attempts=2, extract_summary=3, fk_constraint=2, story_trigger=2, utterance_frame=2 |
| lifemap | extract_attempts=7, extract_summary=6, fk_constraint=13, story_trigger=7, utterance_frame=7 |
| today | extract_attempts=3, extract_summary=4, fk_constraint=4, story_trigger=3, utterance_frame=3 |
| late_age | extract_attempts=1, extract_summary=1 |
| recall_pre | extract_attempts=1, extract_summary=1, fk_constraint=1, memory_echo=1, story_trigger=1, utterance_frame=1 |
| spouse_probe | extract_attempts=1, extract_summary=1 |
| resume | extract_attempts=2, extract_summary=2, fk_constraint=2, memory_echo=1, story_trigger=1, utterance_frame=1 |

## Stress Telemetry (WO-OPS-STRESS-TELEMETRY-KV-01)

- snapshots captured: **19**
- kv-clear calls: **1**
