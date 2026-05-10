# Kent deep-witness harness — 2026-05-09-21-24-56

- conv_id: `deep_kent_1e3973d74596`
- person_id: `4aa0cc2b-1f27-433a-9152-203bb1f69a55`
- WS: `ws://localhost:8000/api/chat/ws`
- tests: 10

## Topline
- PASS: 0
- AMBER: 0
- FAIL/HARD_FAIL: 10

**This harness is built to find failures, not confirm passes.**
Most tests will fail on the current Lori until the LLM-witness-receipt path lands.

## Per-test verdicts

### TEST-A floor-control: claimed-floor mode  →  **HARD_FAIL**  (score 3/12)

- words: 13  questions: 0
- facts: 0/0
- good_intents: []
- bad_intents: []
- hard_fails: ['too_long:13>12']
- score_notes: no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> You're taking your time to gather your thoughts, and I'm here to listen.

### TEST-B induction chapter (dense prose)  →  **HARD_FAIL**  (score 4/12)

- words: 9  questions: 1
- facts: 2/11
- good_intents: []
- bad_intents: []
- hard_fails: ['too_short:9<35']
- score_notes: facts:+1 (2/11), no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> I caught Army, Stanley, and Fargo. What happened next?

### TEST-C Fort Ord / skills / Nike choice point  →  **HARD_FAIL**  (score 5/12)

- words: 26  questions: 1
- facts: 2/9
- good_intents: []
- bad_intents: []
- hard_fails: ['too_short:26<35']
- score_notes: facts:+0 (2/9), achievement:+2, no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> You qualified expert with the M1 rifle, had enlisted hoping for Army Security Agency work, asked what else was available, and chose it. What happened next?

### TEST-D Germany + Janice logistics  →  **HARD_FAIL**  (score 3/12)

- words: 8  questions: 1
- facts: 1/11
- good_intents: []
- bad_intents: []
- hard_fails: ['too_short:8<35']
- score_notes: facts:+0 (1/11), no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> Capté Nike, Detroit, y Michigan. ¿Qué pasó después?

### TEST-E wedding / Janice identity / married life  →  **HARD_FAIL**  (score 5/12)

- words: 16  questions: 1
- facts: 2/10
- good_intents: []
- bad_intents: []
- hard_fails: ['too_short:16<35']
- score_notes: facts:+0 (2/10), family:+2, no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> You came back to Bismarck, Janice's family had put and went back overseas. What happened next?

### TEST-F Germany duty / CBR / courier / photographer  →  **HARD_FAIL**  (score 3/12)

- words: 26  questions: 1
- facts: 2/10
- good_intents: []
- bad_intents: []
- hard_fails: ['too_short:26<35']
- score_notes: facts:+0 (2/10), no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> You had the city name clear, got about one day of training on the, and asked whether they had any openings for photographers. What happened next?

### TEST-G General Schmick + Vince + fragile names  →  **HARD_FAIL**  (score 5/12)

- words: 19  questions: 1
- facts: 4/15
- good_intents: []
- bad_intents: []
- hard_fails: ['too_short:19<35']
- score_notes: facts:+0 (4/15), family:+2, no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> Tú worked for was General Peter Schmick, a Canadian-born y moved into the photography work, Janice. ¿Qué pasó después?

### TEST-H correction-perspective repair (you are talking like you are me)  →  **FAIL**  (score 5/12)

- words: 27  questions: 1
- facts: 0/0
- good_intents: []
- bad_intents: []
- score_notes: family:+2, no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> I'll stay out of the way. Vince was born in Landstuhl Air Force Hospital, connected with Ramstein Air Force Base. What do you remember about that time?

### TEST-COMMS-1959 communication-with-fiancée-from-overseas  →  **HARD_FAIL**  (score 4/12)

- words: 21  questions: 1
- facts: 2/6
- good_intents: []
- bad_intents: []
- hard_fails: ['too_short:21<35', 'missing_required_intent:communication_with_wife']
- score_notes: facts:+1 (2/6), no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> Tú had been in Germany less than a year y had to make plans from overseas, get back. ¿Qué pasó después?

### TEST-COMBINED killer combined turn  →  **HARD_FAIL**  (score 3/12)

- words: 13  questions: 0
- facts: 1/19
- good_intents: []
- bad_intents: []
- hard_fails: ['too_short:13<55']
- score_notes: facts:+0 (1/19), no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> Entiendo — sigue contándome la experiencia como quieras contarla. Te escucho sobre Germany.
