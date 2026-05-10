# Kent multi-turn Fort Ord → memory echo → Nike test

- conv_id: `kent_multi_fortord_nike_f61d815d1a99`
- person_id: `4aa0cc2b-1f27-433a-9152-203bb1f69a55`
- Fort Ord words: 2401
- Nike words: 521

## Turn 1: TURN 1 — KENT LONG FORT ORD MONOLOGUE

- user_words: 2401
- final_words: 26
- question_count: 1
- forbidden_hits: []
- raw_meta_stream_hits: []
- bad_spelling_question_hits: []

**Lori final:**

> You said meal tickets: had already been put in charge of meal tickets on the train. What did handling meal tickets actually require you to do?

## Turn 2: TURN 2 — KENT MEMORY-ECHO CHECK

- user_words: 8
- final_words: 14
- question_count: 1
- forbidden_hits: []
- raw_meta_stream_hits: []
- bad_spelling_question_hits: []

**Lori final:**

> What do you remember about where you were living during your Coming of Age?

## Turn 3: TURN 3 — KENT NIKE MISSILE OPERATOR CHAPTER

- user_words: 521
- final_words: 32
- question_count: 1
- forbidden_hits: []
- raw_meta_stream_hits: []
- bad_spelling_question_hits: []

**Lori final:**

> You went from Nike Ajax to Nike Hercules, then Detroit, Michigan, Southridge, Selfridge Air Force Base, Germany, and States. What happened when you arrived at Fort Ord and started your basic training?

## Score

### TURN 1 Fort Ord: FAIL
- expected_hits: ['meal tickets']
- failures: ['too_short=26w (want ≥30)', "too_few_expected_terms=['meal tickets'] (want ≥3 of ['Fort Ord', 'meal tickets', 'M1', 'GED', 'Army Security Agency', 'Nike Ajax', 'Nike Hercules'])"]

### TURN 2 Memory echo: FAIL
- expected_hits: []
- failures: ["too_few_expected_terms=[] (want ≥3 of ['Fort Ord', 'meal tickets', 'M1', 'GED', 'Army Security Agency', 'Nike Ajax', 'Nike Hercules'])"]

### TURN 3 Nike: PASS
- expected_hits: ['Nike Ajax', 'Nike Hercules', 'Germany']
- failures: NONE

## Bank

- count: 4

- p2 `communication_with_partner_overseas` — How did you and Janice keep in touch from overseas — letters, phone calls, telegrams?
- p3 `career_choice_under_constraint` — How did the choice between waiting and pivoting actually feel at the time?
- p3 `role_pivot_courier_bridge` — How did the courier route end up turning into the next assignment?
- p3 `role_pivot_photography` — What kind of photography did the Brigade need you to do?