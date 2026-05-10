# Kent deep-witness harness — 2026-05-09-22-17-19

- conv_id: `deep_kent_6f2ea7090def`
- person_id: `4aa0cc2b-1f27-433a-9152-203bb1f69a55`
- WS: `ws://localhost:8000/api/chat/ws`
- tests: 10

## Topline
- PASS: 0
- AMBER: 1
- FAIL/HARD_FAIL: 9

**This harness is built to find failures, not confirm passes.**
Most tests will fail on the current Lori until the LLM-witness-receipt path lands.

## Per-test verdicts

### TEST-A floor-control: claimed-floor mode  →  **HARD_FAIL**  (score 3/12)

- words: 14  questions: 0
- facts: 0/0
- good_intents: []
- bad_intents: []
- hard_fails: ['too_long:14>12']
- score_notes: no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> It's great that you're taking the time to share your story with me, Kent.

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

### TEST-D Germany + Janice logistics  →  **FAIL**  (score 6/12)

- words: 39  questions: 1
- facts: 3/11
- good_intents: []
- bad_intents: []
- score_notes: facts:+1 (3/11), family:+2, no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> You were sent to Germany to work in the Nike systems, and that's where you decided to get married and live with your fiancée Janice. What do you remember about where you were living during your Coming of Age?

### TEST-E wedding / Janice identity / married life  →  **FAIL**  (score 5/12)

- words: 41  questions: 1
- facts: 2/10
- good_intents: []
- bad_intents: []
- score_notes: facts:+0 (2/10), family:+2, no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> Janice's family organized a wedding for you at the Cathedral of the Holy Spirit, which was a meaningful way to start your life together. What was daily life like for you and Janice after you returned to Germany with the Army?

### TEST-F Germany duty / CBR / courier / photographer  →  **FAIL**  (score 5/12)

- words: 37  questions: 1
- facts: 3/10
- good_intents: ['role_transition']
- bad_intents: []
- score_notes: facts:+0 (3/10), good_question:+2 (role_transition), no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> You moved from missile-site work to becoming a photographer for the 32nd Brigade after stopping at the 32nd Artillery Brigade office in Kaiserslautern. What do you remember about the work you did as a photographer in Kaiserslautern?

### TEST-G General Schmick + Vince + fragile names  →  **HARD_FAIL**  (score 5/12)

- words: 19  questions: 1
- facts: 4/15
- good_intents: []
- bad_intents: []
- hard_fails: ['too_short:19<35']
- score_notes: facts:+0 (4/15), family:+2, no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> Tú worked for was General Peter Schmick, a Canadian-born y moved into the photography work, Janice. ¿Qué pasó después?

### TEST-H correction-perspective repair (you are talking like you are me)  →  **AMBER**  (score 7/12)

- words: 16  questions: 1
- facts: 0/0
- good_intents: ['factual_continuation']
- bad_intents: []
- score_notes: family:+2, good_question:+2 (factual_continuation), no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> Would you like to continue where you left off, describing what happened after Vince was born?

### TEST-COMMS-1959 communication-with-fiancée-from-overseas  →  **HARD_FAIL**  (score 4/12)

- words: 21  questions: 1
- facts: 2/6
- good_intents: []
- bad_intents: []
- hard_fails: ['too_short:21<35', 'missing_required_intent:communication_with_wife']
- score_notes: facts:+1 (2/6), no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> You had been in Germany less than a year and had to make plans from overseas, get back. What happened next?

### TEST-COMBINED killer combined turn  →  **HARD_FAIL**  (score 5/12)

- words: 28  questions: 1
- facts: 2/19
- good_intents: []
- bad_intents: []
- hard_fails: ['too_short:28<55']
- score_notes: facts:+0 (2/19), achievement:+2, no_bad:+1, no_mimicry:+1, clear_tone:+1

**Lori said:**

> Tú left for the Army, went by train to Fargo for the induction, scored high enough that the Army put me, y had asked for. ¿Qué pasó después?
