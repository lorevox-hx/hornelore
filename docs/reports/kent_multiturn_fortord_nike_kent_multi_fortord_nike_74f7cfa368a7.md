# Kent multi-turn Fort Ord → memory echo → Nike test

- conv_id: `kent_multi_fortord_nike_74f7cfa368a7`
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
- final_words: 157
- question_count: 0
- forbidden_hits: []
- raw_meta_stream_hits: []
- bad_spelling_question_hits: []

**Lori final:**

> What I know about Kent so far:
> 
> Identity
> - Name: Kent
> - Date of birth: (not on record yet)
> - Place of birth: Stanley, North Dakota
> 
> Family
> - Parents: (none on record yet)
> - Siblings: (none on record yet)
> 
> Notes from our conversation
> - Childhood home: Stanley, North Dakota
> - Heritage: French (Alsace-Lorraine via Shong family), German (Bolley family), North Dakota
> - Career: Long career in construction and trades; built family life across multiple states including time in Germany
> - Life stage: senior elder
> 
> What I'm less sure about
> - Some parts are still blank, and that is completely fine. You can correct or add one thing at a time, whenever you'd like.
> - Anything you mention now I'll keep as a working draft until you confirm it. Confirmed facts come from your profile.
> 
> (Based on: profile, session notes.)
> 
> You can correct anything that is wrong, missing, or too vague. One correction at a time works best.

## Turn 3: TURN 3 — KENT NIKE MISSILE OPERATOR CHAPTER

- user_words: 521
- final_words: 38
- question_count: 1
- forbidden_hits: []
- raw_meta_stream_hits: []
- bad_spelling_question_hits: []

**Lori final:**

> You mentioned Southridge before. I should check that against Selfridge Air Force Base. What do you remember about the exact name of the base in Detroit, Michigan, where you trained for the Nike Ajax and Nike Hercules systems?

## Score

### TURN 1 Fort Ord: FAIL
- expected_hits: ['meal tickets']
- failures: ['too_short=26w (want ≥30)', "too_few_expected_terms=['meal tickets'] (want ≥3 of ['Fort Ord', 'meal tickets', 'M1', 'GED', 'Army Security Agency', 'Nike Ajax', 'Nike Hercules'])"]

### TURN 2 Memory echo: FAIL
- expected_hits: []
- failures: ["too_few_expected_terms=[] (want ≥3 of ['Fort Ord', 'meal tickets', 'M1', 'GED', 'Army Security Agency', 'Nike Ajax', 'Nike Hercules'])"]

### TURN 3 Nike: FAIL
- expected_hits: ['Nike Ajax', 'Nike Hercules']
- failures: ["too_few_expected_terms=['Nike Ajax', 'Nike Hercules'] (want ≥3 of ['Nike Ajax', 'Nike Hercules', 'radar', 'computer', 'operator', 'Germany', 'Janice'])"]

## Bank

- count: 4

- p2 `communication_with_partner_overseas` — How did you and Janice keep in touch from overseas — letters, phone calls, telegrams?
- p3 `career_choice_under_constraint` — How did the choice between waiting and pivoting actually feel at the time?
- p3 `role_pivot_courier_bridge` — How did the courier route end up turning into the next assignment?
- p3 `role_pivot_photography` — What kind of photography did the Brigade need you to do?