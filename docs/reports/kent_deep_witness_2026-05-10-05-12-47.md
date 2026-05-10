# Kent deep-witness harness — 2026-05-10-05-12-47

- conv_id: `deep_kent_a5d4a750f9b1`
- person_id: `4aa0cc2b-1f27-433a-9152-203bb1f69a55`
- WS: `ws://localhost:8000/api/chat/ws`
- tests: 10

## Topline
- PASS: 1
- AMBER: 1
- FAIL/HARD_FAIL: 8

**This harness is built to find failures, not confirm passes.**
Most tests will fail on the current Lori until the LLM-witness-receipt path lands.

## Per-test verdicts

### TEST-A floor-control: claimed-floor mode  →  **FAIL**  (score 3/12)

- words: 2  questions: 0
- facts: 0/0
- good_intents: []
- bad_intents: []
- score_notes: no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> I'm listening.

### TEST-B induction chapter (dense prose)  →  **AMBER**  (score 7/12)

- words: 36  questions: 1
- facts: 5/11
- good_intents: ['proper_noun_confirmation']
- bad_intents: []
- score_notes: facts:+2 (5/11), good_question:+2 (proper_noun_confirmation), no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> You went from Stanley to Fargo, then California, Fort Ord, beginning of the Army, dad took me down, right train, and induction process. Got it — you corrected to making. Did I get the spelling right?

### TEST-C Fort Ord / skills / Nike choice point  →  **FAIL**  (score 6/12)

- words: 83  questions: 1
- facts: 4/9
- good_intents: []
- bad_intents: []
- score_notes: facts:+1 (4/9), achievement:+2, no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> You qualified as an expert marksman with the M1 rifle. You were also considered for high school GED work, which showed your ability to handle technical tasks. You were then sent to Nike Ajax and Nike Hercules radar and computer work, which seemed like a good fit. Can you tell me more about what that training was like, where you were stationed, and what it meant to be a radar and computer operator? (We can come back to the rest in a moment.)

### TEST-D Germany + Janice logistics  →  **HARD_FAIL**  (score 6/12)

- words: 34  questions: 1
- facts: 5/11
- good_intents: []
- bad_intents: []
- hard_fails: ['too_short:34<35']
- score_notes: facts:+1 (5/11), family:+2, no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> You went from Nike to Detroit, then Michigan, Southridge Air Force Base, Germany, Janice, Bismarck, and first place I remember. You sounded a little unsure — was it Bismarck, or something close to that?

### TEST-E wedding / Janice identity / married life  →  **HARD_FAIL**  (score 8/12)

- words: 30  questions: 1
- facts: 3/10
- good_intents: ['proper_noun_confirmation']
- bad_intents: []
- hard_fails: ['too_short:30<35']
- score_notes: facts:+1 (3/10), family:+2, good_question:+2 (proper_noun_confirmation), no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> You went from Bismarck to Janice, then Cathedral, Holy Spirit, Leonard Duffy, Germany, wedding, and marriage ceremony. Got it — you corrected to going. Did I get the spelling right?

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

- words: 35  questions: 1
- facts: 7/15
- good_intents: ['proper_noun_confirmation']
- bad_intents: []
- score_notes: facts:+1 (7/15), family:+2, good_question:+2 (proper_noun_confirmation), spelling:+1, no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> You went from General Peter Schmick to Canadian, then American Army, Janice, Kaiserslautern, Vince, Lansdale Army Hospital, and Landstuhl Air Force Hospital. Got it — you corrected to Landstuhl. Did I get the spelling right?

### TEST-H correction-perspective repair (you are talking like you are me)  →  **FAIL**  (score 5/12)

- words: 14  questions: 0
- facts: 0/0
- good_intents: []
- bad_intents: []
- score_notes: family:+2, no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> Vince was born at Landstuhl Air Force Hospital while you were living near Kaiserslautern.

### TEST-COMMS-1959 communication-with-fiancée-from-overseas  →  **HARD_FAIL**  (score 6/12)

- words: 36  questions: 1
- facts: 3/6
- good_intents: []
- bad_intents: []
- hard_fails: ['missing_required_intent:communication_with_wife']
- score_notes: facts:+1 (3/6), family:+2, no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> You went from contacting Janice, to planning, to getting back to Bismarck, to getting married, and then bringing her back to Germany. What do you remember about where you were living in Germany at that time?

### TEST-COMBINED killer combined turn  →  **HARD_FAIL**  (score 6/12)

- words: 24  questions: 1
- facts: 0/19
- good_intents: ['proper_noun_confirmation']
- bad_intents: []
- hard_fails: ['too_short:24<55']
- score_notes: facts:+0 (0/19), good_question:+2 (proper_noun_confirmation), spelling:+1, no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> I want to come back to one detail you mentioned earlier. Got it — you corrected to just. Did I get the spelling right?
