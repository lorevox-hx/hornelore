# Kent deep-witness harness — 2026-05-10-05-35-48

- conv_id: `deep_kent_022a701e0751`
- person_id: `4aa0cc2b-1f27-433a-9152-203bb1f69a55`
- WS: `ws://localhost:8000/api/chat/ws`
- tests: 10

## Topline
- PASS: 1
- AMBER: 2
- FAIL/HARD_FAIL: 7

**This harness is built to find failures, not confirm passes.**
Most tests will fail on the current Lori until the LLM-witness-receipt path lands.

## Per-test verdicts

### TEST-A floor-control: claimed-floor mode  →  **FAIL**  (score 3/12)

- words: 3  questions: 0
- facts: 0/0
- good_intents: []
- bad_intents: []
- score_notes: no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> Take your time.

### TEST-B induction chapter (dense prose)  →  **AMBER**  (score 7/12)

- words: 43  questions: 1
- facts: 6/11
- good_intents: []
- bad_intents: []
- score_notes: facts:+2 (6/11), achievement:+2, no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> You went from Stanley to Fargo, then California, Fort Ord, beginning of the Army, dad took me down, right train, and induction process. What do you remember about the sense of responsibility you felt taking care of the meal tickets for the recruits?

### TEST-C Fort Ord / skills / Nike choice point  →  **HARD_FAIL**  (score 6/12)

- words: 31  questions: 1
- facts: 5/9
- good_intents: ['proper_noun_confirmation']
- bad_intents: []
- hard_fails: ['too_short:31<35']
- score_notes: facts:+1 (5/9), good_question:+2 (proper_noun_confirmation), no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> You went from Fort Ord to GED, then Nike Ajax, Nike Hercules, usual eight weeks of, time, Army taking a bunch, and system. Did I get Army Security Agency spelled right?

### TEST-D Germany + Janice logistics  →  **AMBER**  (score 8/12)

- words: 40  questions: 1
- facts: 4/11
- good_intents: ['communication_with_wife']
- bad_intents: []
- score_notes: facts:+1 (4/11), family:+2, good_question:+2 (communication_with_wife), no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> You were at Nike Ajax, Nike Hercules training around Detroit, then sent to Germany, and you remembered contacting your fiancée Janice while you were there. How did you and Janice communicate during that time, before she joined you in Germany?

### TEST-E wedding / Janice identity / married life  →  **FAIL**  (score 6/12)

- words: 42  questions: 1
- facts: 3/10
- good_intents: []
- bad_intents: []
- score_notes: facts:+1 (3/10), family:+2, no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> You came back to Bismarck, got married at the Cathedral of the Holy Spirit, and then prepared to move to Germany as a newlywed. What do you remember about the experience of adjusting to married life in Germany amidst your Army duties?

### TEST-F Germany duty / CBR / courier / photographer  →  **HARD_FAIL**  (score 9/12)

- words: 28  questions: 1
- facts: 5/10
- good_intents: ['proper_noun_confirmation']
- bad_intents: []
- hard_fails: ['too_short:28<35']
- score_notes: facts:+1 (5/10), family:+2, good_question:+2 (proper_noun_confirmation), spelling:+1, no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> You went from Germany to Nike Ajax, then Nike Hercules, Salamander, Johnny Johnson, Artillery Brigade, Kaiserslautern, and city name clear. Did I get 32nd Artillery Brigade spelled right?

### TEST-G General Schmick + Vince + fragile names  →  **PASS**  (score 9/12)

- words: 38  questions: 1
- facts: 7/15
- good_intents: ['proper_noun_confirmation']
- bad_intents: []
- score_notes: facts:+1 (7/15), family:+2, good_question:+2 (proper_noun_confirmation), spelling:+1, no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> You went from General Peter Schmick to Canadian, then American Army, Janice, Kaiserslautern, Vince, Lansdale Army Hospital, and Landstuhl Air Force Hospital. Got it — you corrected to Landstuhl Air Force Hospital. Did I get the spelling right?

### TEST-H correction-perspective repair (you are talking like you are me)  →  **FAIL**  (score 5/12)

- words: 27  questions: 1
- facts: 0/0
- good_intents: []
- bad_intents: []
- score_notes: family:+2, no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> Vince was born at Landstuhl Air Force Hospital, near Ramstein Air Force Base. How did your family adjust to life as a parent in a foreign country?

### TEST-COMMS-1959 communication-with-fiancée-from-overseas  →  **HARD_FAIL**  (score 9/12)

- words: 30  questions: 1
- facts: 4/6
- good_intents: ['communication_with_wife']
- bad_intents: []
- hard_fails: ['too_short:30<35']
- score_notes: facts:+2 (4/6), family:+2, good_question:+2 (communication_with_wife), no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> You went from Germany to Janice, then Bismarck, if we were going, and This was. How did you and Janice keep in touch from overseas — letters, phone calls, telegrams?

### TEST-COMBINED killer combined turn  →  **HARD_FAIL**  (score 7/12)

- words: 25  questions: 1
- facts: 6/19
- good_intents: ['proper_noun_confirmation']
- bad_intents: []
- hard_fails: ['too_short:25<55']
- score_notes: facts:+1 (6/19), good_question:+2 (proper_noun_confirmation), spelling:+1, no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> You went from Stanley to Fargo, then Fort Ord, California, GED, Nike Ajax, Nike Hercules, and Detroit. Did I get 32nd Artillery Brigade spelled right?
