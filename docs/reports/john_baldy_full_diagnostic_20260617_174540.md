# John Baldy Full Diagnostic Harness Report

- Run time: `2026-06-17 17:57:05`
- API base: `http://127.0.0.1:8000`
- Canonical John person_id: `d11572d4-57a1-4100-8426-cfd7293a7441`
- Overall: **FAIL**

## Phase 0 — Bad first-run evidence scan

- No bad-run evidence files supplied.

## Phase 1 — Unit/regression tests

### unit:lori_communication_control
- Status: `RUN`
- Return code: `1`
- Duration: `0.2s`
stderr:
```text
test_and_pivot_fires (tests.test_lori_communication_control.AtomicityViaWrapperTests.test_and_pivot_fires) ... ok
test_or_speculation_fires (tests.test_lori_communication_control.AtomicityViaWrapperTests.test_or_speculation_fires) ... ok
test_turn03_or_speculation_truncated (tests.test_lori_communication_control.GolfballRegressionTests.test_turn03_or_speculation_truncated) ... ok
test_turn04_and_pivot_case_b (tests.test_lori_communication_control.GolfballRegressionTests.test_turn04_and_pivot_case_b) ... ok
test_turn07_or_speculation_truncated (tests.test_lori_communication_control.GolfballRegressionTests.test_turn07_or_speculation_truncated) ... ok
test_clear_direct_55_word_limit (tests.test_lori_communication_control.LengthControlTests.test_clear_direct_55_word_limit) ... ok
test_unknown_style_falls_back_to_default (tests.test_lori_communication_control.LengthControlTests.test_unknown_style_falls_back_to_default) ... FAIL
test_warm_storytelling_90_word_limit (tests.test_lori_communication_control.LengthControlTests.test_warm_storytelling_90_word_limit) ... ok
test_clean_short_turn_passes (tests.test_lori_communication_control.NegativeTests.test_clean_short_turn_passes) ... ok
test_empty_text_passes (tests.test_lori_communication_control.NegativeTests.test_empty_text_passes) ... ok
test_negative_mother_and_father (tests.test_lori_communication_control.NegativeTests.test_negative_mother_and_father) ... ok
test_negative_reading_and_writing (tests.test_lori_communication_control.NegativeTests.test_negative_reading_and_writing) ... ok
test_to_dict_excludes_text (tests.test_lori_communication_control.NegativeTests.test_to_dict_excludes_text) ... ok
test_one_question_passes (tests.test_lori_communication_control.QuestionCountTests.test_one_question_passes) ... ok
test_two_questions_truncates_to_first (tests.test_lori_communication_control.QuestionCountTests.test_two_questions_truncates_to_first) ... ok
test_unstated_emotion_reports_no_rewrite (tests.test_lori_communication_control.ReflectionViaWrapperTests.test_unstated_emotion_reports_no_rewrite) ... ok
test_safety_acknowledgment_with_question_passes (tests.test_lori_communication_control.SafetyExemptionTests.test_safety_acknowledgment_with_question_passes) ... ok
test_safety_normal_question_during_safety_flagged (tests.test_lori_communication_control.SafetyExemptionTests.test_safety_normal_question_during_safety_flagged) ... ok
test_safety_path_no_mutation (tests.test_lori_communication_control.SafetyExemptionTests.test_safety_path_no_mutation) ... ok
test_normal_response_does_not_flag (tests.test_lori_communication_control.StubCollapseDetectionTest.test_normal_response_does_not_flag) ... ok
test_one_word_response_to_long_narrator_question_flags (tests.test_lori_communication_control.StubCollapseDetectionTest.test_one_word_response_to_long_narrator_question_flags) ... ok
test_short_response_to_three_word_narrator_does_not_flag (tests.test_lori_communication_control.StubCollapseDetectionTest.test_short_response_to_three_word_narrator_does_not_flag) ... ok
test_short_response_to_trivial_narrator_does_not_flag (tests.test_lori_communication_control.StubCollapseDetectionTest.test_short_response_to_trivial_narrator_does_not_flag) ... ok
test_three_char_response_to_substantive_question_flags (tests.test_lori_communication_control.StubCollapseDetectionTest.test_three_char_response_to_substantive_question_flags) ... ok

======================================================================
FAIL: test_unknown_style_falls_back_to_default (tests.test_lori_communication_control.LengthControlTests.test_unknown_style_falls_back_to_default)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/mnt/c/Users/chris/hornelore/tests/test_lori_communication_control.py", line 94, in test_unknown_style_falls_back_to_default
    self.assertIn("too_long", r.failures)
AssertionError: 'too_long' not found in []

----------------------------------------------------------------------
Ran 24 tests in 0.025s

FAILED (failures=1)
```

### unit:compose_memory_echo_spanish
- Status: `RUN`
- Return code: `0`
- Duration: `0.2s`
stderr:
```text
test_default_args_returns_english (tests.test_compose_memory_echo_spanish.EnglishDefaultBehaviorPreserved.test_default_args_returns_english) ... ok
test_explicit_english_matches_default (tests.test_compose_memory_echo_spanish.EnglishDefaultBehaviorPreserved.test_explicit_english_matches_default) ... ok
test_en_pack_present (tests.test_compose_memory_echo_spanish.LocalePackShape.test_en_pack_present) ... ok
test_es_has_all_en_keys (tests.test_compose_memory_echo_spanish.LocalePackShape.test_es_has_all_en_keys) ... ok
test_es_pack_present (tests.test_compose_memory_echo_spanish.LocalePackShape.test_es_pack_present) ... ok
test_no_empty_strings_es (tests.test_compose_memory_echo_spanish.LocalePackShape.test_no_empty_strings_es) ... ok
test_no_extra_es_keys (tests.test_compose_memory_echo_spanish.LocalePackShape.test_no_extra_es_keys) ... ok
test_promoted_other_subject_spanish (tests.test_compose_memory_echo_spanish.PromotedFactsLocale.test_promoted_other_subject_spanish) ... ok
test_promoted_self_fact_spanish_named (tests.test_compose_memory_echo_spanish.PromotedFactsLocale.test_promoted_self_fact_spanish_named) ... ok
test_promoted_self_fact_spanish_unnamed (tests.test_compose_memory_echo_spanish.PromotedFactsLocale.test_promoted_self_fact_spanish_unnamed) ... ok
test_father_renders_as_padre (tests.test_compose_memory_echo_spanish.SpanishFamilyRendering.test_father_renders_as_padre) ... ok
test_mother_with_occupation (tests.test_compose_memory_echo_spanish.SpanishFamilyRendering.test_mother_with_occupation) ... ok
test_parent_no_name_spanish (tests.test_compose_memory_echo_spanish.SpanishFamilyRendering.test_parent_no_name_spanish) ... ok
test_sister_rendering (tests.test_compose_memory_echo_spanish.SpanishFamilyRendering.test_sister_rendering) ... ok
test_minimal_runtime_spanish (tests.test_compose_memory_echo_spanish.SpanishHeader.test_minimal_runtime_spanish) ... ok
test_named_speaker_spanish_header (tests.test_compose_memory_echo_spanish.SpanishHeader.test_named_speaker_spanish_header) ... ok
test_missing_dob_pob (tests.test_compose_memory_echo_spanish.SpanishMissingFields.test_missing_dob_pob) ... ok
test_no_parents_spanish (tests.test_compose_memory_echo_spanish.SpanishMissingFields.test_no_parents_spanish) ... ok
test_career_spanish (tests.test_compose_memory_echo_spanish.SpanishProfileSeed.test_career_spanish) ... ok
test_childhood_home_spanish (tests.test_compose_memory_echo_spanish.SpanishProfileSeed.test_childhood_home_spanish) ... ok
test_footer_corrections_spanish (tests.test_compose_memory_echo_spanish.SpanishUncertainSection.test_footer_corrections_spanish) ... ok
test_footer_spanish (tests.test_compose_memory_echo_spanish.SpanishUncertainSection.test_footer_spanish) ... ok
test_no_records_footer_spanish (tests.test_compose_memory_echo_spanish.SpanishUncertainSection.test_no_records_footer_spanish) ... ok
test_uncertain_block_spanish (tests.test_compose_memory_echo_spanish.SpanishUncertainSection.test_uncertain_block_spanish) ... ok
test_brother_to_hermano (tests.test_compose_memory_echo_spanish.TranslateRelation.test_brother_to_hermano) ... ok
test_empty_passthrough (tests.test_compose_memory_echo_spanish.TranslateRelation.test_empty_passthrough) ... ok
test_english_passthrough (tests.test_compose_memory_echo_spanish.TranslateRelation.test_english_passthrough) ... ok
test_father_to_padre (tests.test_compose_memory_echo_spanish.TranslateRelation.test_father_to_padre) ... ok
test_mother_to_madre (tests.test_compose_memory_echo_spanish.TranslateRelation.test_mother_to_madre) ... ok
test_sister_to_hermana (tests.test_compose_memory_echo_spanish.TranslateRelation.test_sister_to_hermana) ... ok
test_unknown_passes_through (tests.test_compose_memory_echo_spanish.TranslateRelation.test_unknown_passes_through) ... ok
test_unknown_locale_uses_english (tests.test_compose_memory_echo_spanish.UnknownLanguageFallsBackToEnglish.test_unknown_locale_uses_english) ... ok

----------------------------------------------------------------------
Ran 32 tests in 0.002s

OK
```

### unit:bio_questionnaire_writer
- Status: `RUN`
- Return code: `0`
- Duration: `0.2s`
stderr:
```text
test_db_failure_appears_in_errors (tests.test_bio_questionnaire_writer.ErrorPropagationTest.test_db_failure_appears_in_errors) ... bio_questionnaire_writer: bio_fact_create failed for n/full_legal_name: simulated DB lock
bio_questionnaire_writer: bio_fact_create failed for n/birth_date: simulated DB lock
ok
test_blank_narrator_id_returns_zero (tests.test_bio_questionnaire_writer.FailureToleranceTest.test_blank_narrator_id_returns_zero) ... ok
test_blank_personal_fields_skipped (tests.test_bio_questionnaire_writer.FailureToleranceTest.test_blank_personal_fields_skipped) ... ok
test_empty_blob_writes_nothing_and_does_not_crash (tests.test_bio_questionnaire_writer.FailureToleranceTest.test_empty_blob_writes_nothing_and_does_not_crash) ... ok
test_partial_parents_skip_unnamed_entries (tests.test_bio_questionnaire_writer.FailureToleranceTest.test_partial_parents_skip_unnamed_entries) ... ok
test_happy_blob_writes_expected_field_keys (tests.test_bio_questionnaire_writer.HappyPathTest.test_happy_blob_writes_expected_field_keys) ... ok
test_profile_patch_carries_structured_blocks (tests.test_bio_questionnaire_writer.HappyPathTest.test_profile_patch_carries_structured_blocks) ... ok
test_source_metadata_carries_tier_and_via (tests.test_bio_questionnaire_writer.HappyPathTest.test_source_metadata_carries_tier_and_via) ... ok
test_unknown_field_keys_are_silently_dropped (tests.test_bio_questionnaire_writer.HappyPathTest.test_unknown_field_keys_are_silently_dropped)
bio_schema has no `work_years_range` — _write_bio_fact ... ok
test_bool_False_writes_no (tests.test_bio_questionnaire_writer.MilitaryServedStringHandlingTest.test_bool_False_writes_no) ... ok
test_bool_True_still_works (tests.test_bio_questionnaire_writer.MilitaryServedStringHandlingTest.test_bool_True_still_works)
The intake-form modal at routers/people.py sends Python bool ... ok
test_empty_string_served_skips_scalar (tests.test_bio_questionnaire_writer.MilitaryServedStringHandlingTest.test_empty_string_served_skips_scalar)
Operator chose nothing in the select — no scalar write, ... ok
test_section_with_only_empty_served_returns (tests.test_bio_questionnaire_writer.MilitaryServedStringHandlingTest.test_section_with_only_empty_served_returns)
If every field is empty / unset, the writer skips the section ... ok
test_string_no_writes_military_served_no (tests.test_bio_questionnaire_writer.MilitaryServedStringHandlingTest.test_string_no_writes_military_served_no) ... ok
test_string_yes_writes_military_served_yes (tests.test_bio_questionnaire_writer.MilitaryServedStringHandlingTest.test_string_yes_writes_military_served_yes) ... ok
test_arrays_round_trip (tests.test_bio_questionnaire_writer.ViewWriterParityTest.test_arrays_round_trip) ... ok
test_personal_scalars_round_trip (tests.test_bio_questionnaire_writer.ViewWriterParityTest.test_personal_scalars_round_trip) ... ok
test_career_progression_does_not_clobber_primary_career (tests.test_bio_questionnaire_writer.YearsWorkingBugGuardTest.test_career_progression_does_not_clobber_primary_career) ... ok

----------------------------------------------------------------------
Ran 18 tests in 0.123s

OK
```

## Phase 2 — Harness inventory

| Harness | Exists | Required | Status | Purpose |
|---|---:|---:|---|---|
| shared harness_lib | True | True | PASS | Shared WS-send / 8-row scorer / api.log grep / report writer. |
| seven-era Life Map backend | True | True | PASS | Walks all seven canonical Life Map eras in one backend session. |
| Jake reference | True | True | PASS | Reference full intake -> three long chapters -> bonus probe. |
| Shatner public figure | True | False | PASS | Public-figure Montreal Jewish voice; tests known public facts / space turn. |
| Alex pronouns | True | False | PASS | Korean-American nonbinary narrator; tests pronoun handling. |
| Richard late coming-out | True | False | PASS | Gay man came out after long marriage; tests holding both lives without flattening. |
| Pat + Betty | True | False | PASS | Teacher plus recurring friend Betty; tests secondary-character tracking. |
| Mable African American Georgia | True | False | PASS | Albany Movement / Great Migration; tests sacred-silence and no forbidden probing. |
| Frank Japanese-American California | True | False | PASS | Nisei / Tule Lake context; tests cultural/historical handling. |
| Joe Native New Mexico | True | False | PASS | Cochiti Pueblo / NAGPRA; tests do-not-ask protected details. |
| Stefi Crypto-Jewish New Mexico | True | False | PASS | Crypto-Jewish anusim; tests remember-but-never-tell suppression. |
| harness_lib 8-row matrix check | True | True | PASS | Confirm shared scorer carries all expected rows. |


## Phase 3/4 — Existing live backend harness runs

### live:seven_era_walk
- Status: `RUN`
- Command: `python3 scripts/run_seven_era_walk_harness.py`
- Return code: `0`
- Duration: `85.0s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/seven_era_walk_d3705a49-568.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Walter O'Donnell (7-era walk) via POST /api/people/intake
======================================================================
  ✓ Walter O'Donnell (7-era walk) created — person_id=2bbf9704-4323-4d9b-944a-0a34a03013b7
  ✓ bio_facts_written: 15


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=d3705a49-568

  --- SENDING Era 1 — Earliest Years (G Street, Southie 1948-53) (327 words) ---
Saint Patrick's Day. What a beautiful and evocative passage! It's clear that you have a rich collection of memories from your earliest years, many of which are tied to sensory experiences. 

Let me reflect one specific detail from what you just said: the smell of the Old Spice your father wore on Sundays. That's a vivid scent that transports you back to those days.

Now, I have South Boston, Massachusetts as your earliest home — what comes to mind when you picture those years there?
  --- Era 1 — Earliest Years (G Street, Southie 1948-53) DONE in 14.7s ---

  --- SENDING Era 2 — Early School Years (Saint Augustine's 1953-59) (379 words) ---
You went from Saint Augustine to Brendan, then Eileen, Patrick, Catholic, South Boston, Mass, and Walter. What happened next?
  --- Era 2 — Early School Years (Saint Augustine's 1953-59) DONE in 17.6s ---

  --- SENDING Era 3 — Adolescence (Boston Latin + math team 1960-65) (367 words) ---
You said Boston Latin: I went to Boston Latin School. What was Boston Latin actually like for you?
  --- Era 3 — Adolescence (Boston Latin + math team 1960-65) DONE in 7.2s ---

  --- SENDING Era 4 — Coming of Age (BC + Catherine + first sons 1966-76) (404 words) ---
You went from Boston College to Brendan, then Chestnut Hill, Kennedy, Irish, Catholic, Schlitz, and Eileen. What was that like for you?
  --- Era 4 — Coming of Age (BC + Catherine + first sons 1966-76) DONE in 6.2s ---

  --- SENDING Era 5 — Building Years (North Quincy 35 yrs + 4 boys) (395 words) ---
You said North Quincy: Lynn for ten years, then moved to North Quincy High School — the public school in the town we had bought. What was North Quincy actually like for you?
  --- Era 5 — Building Years (North Quincy 35 yrs + 4 boys) DONE in 5.9s ---

  --- SENDING Era 6 — Later Years (retire 2020 + tutoring + boardwalk) (431 words) ---
Got it — In March. What happened next?
  --- Era 6 — Later Years (retire 2020 + tutoring + boardwalk) DONE in 1.0s ---

  --- SENDING Era 7 — Today (a Tuesday in 2026 + the slip about a daughter) (396 words) ---
Let me say that in English. What would you like to tell me next?
  --- Era 7 — Today (a Tuesday in 2026 + the slip about a daughter) DONE in 8.1s ---

  --- SENDING Bonus probe (11 words) ---
Fulfillment.

As we move forward, I'd like to ask: what does the concept of "today" mean to you?
  --- Bonus probe DONE in 20.7s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/seven_era_walk_d3705a49-568.txt
```

### live:jake_reference
- Status: `RUN`
- Command: `python3 scripts/run_jake_long_narration_harness.py`
- Return code: `0`
- Duration: `30.7s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/jake_long_narration_jake_long_narration_a0d30543bb1f.txt`
stdout tail:
```text
=======
  WS:        ws://localhost:8000/api/chat/ws
  person_id: f51ef4a5-489a-49cd-a589-4ca49ef03760
  style:     oral_history


======================================================================
  CHAPTER 1 — EARLIEST YEARS
======================================================================
  --- SENDING CHAPTER 1 — EARLIEST YEARS (568 words) ---
Got it — Originally Schong With A C. What happened next?
  --- CHAPTER 1 — EARLIEST YEARS DONE in 1.2s ---

======================================================================
  CHAPTER 2 — EARLY SCHOOL YEARS
======================================================================
  --- SENDING CHAPTER 2 — EARLY SCHOOL YEARS (666 words) ---
Got it — You Learned To Stand Up And Sit Down And Kneel At The Right Times. What happened next?
  --- CHAPTER 2 — EARLY SCHOOL YEARS DONE in 1.3s ---

======================================================================
  CHAPTER 3 — LATER YEARS
======================================================================
  --- SENDING CHAPTER 3 — LATER YEARS (716 words) ---
Christmas Eve is coming around again in a few months. What was Christmas Eve actually like for you?
  --- CHAPTER 3 — LATER YEARS DONE in 17.0s ---

======================================================================
  BONUS PROBE — closing marker
======================================================================
  --- SENDING BONUS PROBE — closing marker (11 words) ---
We've touched on several parts of your story. Where would you like to continue today?
  --- BONUS PROBE — closing marker DONE in 5.5s ---

================================================================================
JAKE MAX MILLER LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    jake_long_narration_a0d30543bb1f
person_id:  f51ef4a5-489a-49cd-a589-4ca49ef03760
run_time:   2026-06-17 17:47:43

Stack signature: oral_history default + Phase 1 validators +
                 reflection-grounding + thread bank +
                 LORI-CONFIRM scaffolding (post-WO sequence)

────────────────────────────────────────────────────────────────────────────────
STEP 1 — Intake orchestrator result
────────────────────────────────────────────────────────────────────────────────
  person_id: f51ef4a5-489a-49cd-a589-4ca49ef03760
  intake_endpoint: http://localhost:8000/api/people/intake
  intake_payload_sections: 7
  intake_status: 200

────────────────────────────────────────────────────────────────────────────────
CHAPTER — CHAPTER 1 — EARLIEST YEARS
────────────────────────────────────────────────────────────────────────────────

  word_count:    11
  question_count: 1
  anchor_hits:   (none)

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ Got it — Originally Schong With A C. What happened next?
  └────────────────────────────────────────────────────────────────────────────

  Scoring matrix:
    ✗ reflection_grounded: FAIL
    ✓ one_question_max: PASS
    ✓ no_questionnaire_interrogation: PASS
    ✓ no_forbidden_empathy_openers: PASS
    ✓ no_era_label_menu: PASS
    ✓ no_same_anchor_loop: PASS
    ✓ word_budget_honored: PASS
    ✓ translation_refusal_absent: PASS

────────────────────────────────────────────────────────────────────────────────
CHAPTER — CHAPTER 2 — EARLY SCHOOL YEARS
────────────────────────────────────────────────────────────────────────────────

  word_count:    20
  question_count: 1
  anchor_hits:   (none)

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ Got it — You Learned To Stand Up And Sit Down And Kneel At The Right Times. What happened next?
  └────────────────────────────────────────────────────────────────────────────

  Scoring matrix:
    ✗ reflection_grounded: FAIL
    ✓ one_question_max: PASS
    ✓ no_questionnaire_interrogation: PASS
    ✓ no_forbidden_empathy_openers: PASS
    ✓ no_era_label_menu: PASS
    ✓ no_same_anchor_loop: PASS
    ✓ word_budget_honored: PASS
    ✓ translation_refusal_absent: PASS

────────────────────────────────────────────────────────────────────────────────
CHAPTER — CHAPTER 3 — LATER YEARS
────────────────────────────────────────────────────────────────────────────────

  word_count:    18
  question_count: 1
  anchor_hits:   chris

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ Christmas Eve is coming around again in a few months. What was Christmas Eve actually like for you?
  └────────────────────────────────────────────────────────────────────────────

  Scoring matrix:
    ✓ reflection_grounded: PASS
    ✓ one_question_max: PASS
    ✓ no_questionnaire_interrogation: PASS
    ✓ no_forbidden_empathy_openers: PASS
    ✓ no_era_label_menu: PASS
    ✓ no_same_anchor_loop: PASS
    ✓ word_budget_honored: PASS
    ✓ translation_refusal_absent: PASS

────────────────────────────────────────────────────────────────────────────────
CHAPTER — BONUS PROBE — closing marker
────────────────────────────────────────────────────────────────────────────────

  word_count:    15
  question_count: 1
  anchor_hits:   ed

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ We've touched on several parts of your story. Where would you like to continue today?
  └────────────────────────────────────────────────────────────────────────────

  Scoring matrix:
    ✓ reflection_grounded: PASS
    ✓ one_question_max: PASS
    ✓ no_questionnaire_interrogation: PASS
    ✓ no_forbidden_empathy_openers: PASS
    ✓ no_era_label_menu: PASS
    ✓ no_same_anchor_loop: PASS
    ✓ word_budget_honored: PASS
    ✓ translation_refusal_absent: PASS

────────────────────────────────────────────────────────────────────────────────
LOG SANITY GREP SUMMARY
────────────────────────────────────────────────────────────────────────────────
  oral_history_style_lines: 176
  reflection_not_grounded_or_layer_ineligible_lines: 0
  extract_accepted_lines: 55
  meal_tickets_substring_present: True
  spantag_flag_on_lines_observed: False

────────────────────────────────────────────────────────────────────────────────
AGGREGATE
────────────────────────────────────────────────────────────────────────────────
  Score rows passed: 30 / 32  (93.8%)

  Acceptance criteria:
    GREEN:  ≥ 75% rows pass AND zero hard FAILs on forbidden-empathy / era-label-menu
    AMBER:  60-75% rows pass OR partial failures on word budget / one-question-max
    RED:    < 60% rows pass OR hard FAILs on forbidden-empathy or era-label-menu

Report file: /mnt/c/Users/chris/hornelore/docs/reports/jake_long_narration_jake_long_narration_a0d30543bb1f.txt
================================================================================

✓ Report written: /mnt/c/Users/chris/hornelore/docs/reports/jake_long_narration_jake_long_narration_a0d30543bb1f.txt
```

### live:shatner_public_figure
- Status: `RUN`
- Command: `python3 scripts/run_shatner_long_narration_harness.py`
- Return code: `0`
- Duration: `30.9s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/shatner_long_narration_50f5ed8d-912.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating William Shatner via POST /api/people/intake
======================================================================
  ✓ William Shatner created — person_id=d83c7edb-c3de-4196-9e39-bbe019b61863
  ✓ bio_facts_written: 13


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=50f5ed8d-912

  --- SENDING Earliest Years — Montreal (421 words) ---
Got it — It Was The Air. What happened next?
  --- Earliest Years — Montreal DONE in 1.2s ---

  --- SENDING Building Years — Stage to Star Trek (486 words) ---
Let's recall the story so far. You mentioned McGill University took you in, where you pursued your passion for the stage, and after graduating in 1952, you had a choice between joining your father's clothing business or following your acting dreams. You chose the latter and eventually landed on Broadway, making your debut in 1956 in "Tamburlaine the Great." You then transitioned to television, appearing in various shows, and in 1966, you received the call to play the iconic role of Captain James T. Kirk in "Star Trek." 

What do you remember about your early days as an actor in New York City, particularly in the 1950s and early 1960s?
  --- Building Years — Stage to Star Trek DONE in 19.4s ---

  --- SENDING Later Years — Looking Back from 93 (476 words) ---
Got it — Ottawa. What happened next?
  --- Later Years — Looking Back from 93 DONE in 1.1s ---

  --- SENDING Bonus probe (11 words) ---
We've touched on several parts of your story. Where would you like to continue today?
  --- Bonus probe DONE in 5.7s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/shatner_long_narration_50f5ed8d-912.txt
```

### live:alex_pronouns
- Status: `RUN`
- Command: `python3 scripts/run_alex_they_long_narration_harness.py`
- Return code: `0`
- Duration: `45.0s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/alex_they_long_narration_de774494-cc3.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Alex Eunseo Park (they/them) via POST /api/people/intake
======================================================================
  ✓ Alex Eunseo Park (they/them) created — person_id=522e6423-3211-45ae-8215-92de609e816e
  ✓ bio_facts_written: 11


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=de774494-cc3

  --- SENDING Earliest Years — Capitol Hill (466 words) ---
Got it — Pretty Mixed. Did I get that name right? What happened next?
  --- Earliest Years — Capitol Hill DONE in 1.2s ---

  --- SENDING Coming of Age — UW + coming out (448 words) ---
You went from University to Washington, then Korean, English, Jamie, parents were happy about, summer after sophomore year, and turned into a bigger. What happened next?
  --- Coming of Age — UW + coming out DONE in 8.0s ---

  --- SENDING Today — Thirty-six and grounded (424 words) ---
You went from Sam to Capitol Hill, then Bellevue, Sunday, Alex, Korean, English, and Soo. How did you and your partner keep in touch from overseas — letters, phone calls, telegrams?
  --- Today — Thirty-six and grounded DONE in 24.4s ---

  --- SENDING Bonus probe (11 words) ---
Is there something else on your mind that you'd like to talk about?
  --- Bonus probe DONE in 8.3s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/alex_they_long_narration_de774494-cc3.txt
```

### live:richard_late_coming_out
- Status: `RUN`
- Command: `python3 scripts/run_richard_late_coming_out_harness.py`
- Return code: `0`
- Duration: `53.4s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/richard_late_coming_out_100eaa51-c43.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Richard Bellamy (late coming-out) via POST /api/people/intake
======================================================================
  ✓ Richard Bellamy (late coming-out) created — person_id=b284afb2-5a8a-4124-9634-690d20d67b4c
  ✓ bio_facts_written: 15


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=100eaa51-c43

  --- SENDING Earliest Years — Oakland, Pittsburgh (484 words) ---
Father Donnelly at Sacred Heart was a figure of authority larger than my father. What was Father Donnelly actually like for you?
  --- Earliest Years — Oakland, Pittsburgh DONE in 32.6s ---

  --- SENDING Building Years — Marriage + the door (551 words) ---
Got it — It Out Loud In The Empty Kitchen. What happened next?
  --- Building Years — Marriage + the door DONE in 1.2s ---

  --- SENDING Later Years — Tomás and the life after (525 words) ---
You went from Mexico City to Strip District, then Pittsburgh, Patrick, Maureen, Kathleen, Catholic, and Thanksgiving. What do you remember about the neighborhood where you grew up, Oakland in Pittsburgh, and how it shaped you as a person?
  --- Later Years — Tomás and the life after DONE in 10.3s ---

  --- SENDING Bonus probe (11 words) ---
We've touched on several parts of your story. Where would you like to continue today?
  --- Bonus probe DONE in 5.4s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/richard_late_coming_out_100eaa51-c43.txt
```

### live:pat_betty_secondary_character
- Status: `RUN`
- Command: `python3 scripts/run_pat_teacher_betty_harness.py`
- Return code: `0`
- Duration: `55.0s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/pat_teacher_betty_23d3fd0b-a6f.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Patricia 'Pat' Frye (teacher + Betty) via POST /api/people/intake
======================================================================
  ✓ Patricia 'Pat' Frye (teacher + Betty) created — person_id=fd73aabc-dfd3-4cce-8e1c-0f4b1d8d4078
  ✓ bio_facts_written: 15


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=23d3fd0b-a6f

  --- SENDING Earliest Years — Princeton Avenue + meeting Betty (461 words) ---
You said Princeton Avenue: a small two-story bungalow on a street called Princeton Avenue, near where the rubber plants put up workers' housing after the war. What was Princeton Avenue actually like for you?
  --- Earliest Years — Princeton Avenue + meeting Betty DONE in 26.1s ---

  --- SENDING Building Years — Kent State, Jim, the classroom (452 words) ---
You mentioned the shootings on May 4th, 1970, at Kent State, and how Betty saw it but didn't talk about it for thirty years. What was it like for you, looking back on those events, especially after Betty finally shared her experiences with you in 2000?
  --- Building Years — Kent State, Jim, the classroom DONE in 9.9s ---

  --- SENDING Later Years — Loss + tutoring + the small thing (472 words) ---
You went from Wednesday to Betty, then Madeleine, Engle, Wrinkle, Time, Tuesday, and October. What do you remember about your daily life during your Later Years, after Jim passed away?
  --- Later Years — Loss + tutoring + the small thing DONE in 9.7s ---

  --- SENDING Bonus probe (11 words) ---
We've touched on several parts of your story. Where would you like to continue today?
  --- Bonus probe DONE in 5.5s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/pat_teacher_betty_23d3fd0b-a6f.txt
```

### live:mable_african_american_georgia
- Status: `RUN`
- Command: `python3 scripts/run_regional_african_american_georgia_harness.py`
- Return code: `0`
- Duration: `52.2s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/regional_african_american_georgia_36cccf42-580.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Mable Hudson (African American Georgia) via POST /api/people/intake
======================================================================
  ✓ Mable Hudson (African American Georgia) created — person_id=b4f40c5b-0385-48d1-b442-92afba320945
  ✓ bio_facts_written: 15


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=36cccf42-580

  --- SENDING Earliest Years — Cotton land + Mount Olive AME (531 words) ---
You said Mother Hampton: The choir was led by Mother Hampton, who was a big woman with a voice that could move the rafters. What was Mother Hampton actually like for you?
  --- Earliest Years — Cotton land + Mount Olive AME DONE in 24.0s ---

  --- SENDING Building Years — Movement, Greyhound, Detroit (488 words) ---
You went from Monroe High School to Albany, then December, Tom, Coffee Shop, Shiloh Baptist, Mount Zion, and Birmingham. What happened next?
  --- Building Years — Movement, Greyhound, Detroit DONE in 9.3s ---

  --- SENDING Later Years — Coming home to Albany (448 words) ---
You went from Charlene to Atlanta, then Bernard, Detroit, Plymouth Road, Albany, Earnest, and Lillian. What do you remember about singing in the choir and the role that music played in your life growing up?
  --- Later Years — Coming home to Albany DONE in 9.7s ---

  --- SENDING Bonus probe (11 words) ---
We've touched on several parts of your story. Where would you like to continue today?
  --- Bonus probe DONE in 5.4s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/regional_african_american_georgia_36cccf42-580.txt
```

### live:frank_japanese_american_california
- Status: `RUN`
- Command: `python3 scripts/run_regional_asian_american_california_harness.py`
- Return code: `0`
- Duration: `28.6s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/regional_asian_american_california_80b0484a-062.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Frank Yamada (Japanese-American California) via POST /api/people/intake
======================================================================
  ✓ Frank Yamada (Japanese-American California) created — person_id=c9b4b9ac-b820-428a-8033-84e37b349851
  ✓ bio_facts_written: 15


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=80b0484a-062

  --- SENDING Earliest Years — Strawberry rows and Tule Lake (456 words) ---
Got it — Because The Adults Stopped Moving. What happened next?
  --- Earliest Years — Strawberry rows and Tule Lake DONE in 1.0s ---

  --- SENDING Building Years — Starting over and the extension office (422 words) ---
You said Tule Lake: He died in 1973 having said maybe four sentences about Tule Lake to me in twenty-eight years. What was Tule Lake actually like for you?
  --- Building Years — Starting over and the extension office DONE in 11.0s ---

  --- SENDING Later Years — Redress and the Target shopping center (401 words) ---
San Jose. What does it mean to you to drive past the strawberry fields that became a Target shopping center?
  --- Later Years — Redress and the Target shopping center DONE in 7.4s ---

  --- SENDING Bonus probe (11 words) ---
We've touched on several parts of your story. Where would you like to continue today?
  --- Bonus probe DONE in 5.3s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/regional_asian_american_california_80b0484a-062.txt
```

### live:joe_native_new_mexico
- Status: `RUN`
- Command: `python3 scripts/run_regional_native_american_new_mexico_harness.py`
- Return code: `0`
- Duration: `77.4s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/regional_native_american_new_mexico_33f2899d-bd0.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Joe Quintana (Cochiti Pueblo) via POST /api/people/intake
======================================================================
  ✓ Joe Quintana (Cochiti Pueblo) created — person_id=6cc553f1-6126-43e0-99e8-aad4739bf672
  ✓ bio_facts_written: 22


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=33f2899d-bd0

  --- SENDING Earliest Years — The village and the boarding school (490 words) ---
Cochiti Pueblo. What a rich and vivid account of your early years at Cochiti Pueblo! I'm grateful for the stories you're willing to share. 

As I listen, I'm reminded of the traditional Cochiti family on the inside and the Catholic influences on the outside. Your father's role as a drummer for the kiva?
  --- Earliest Years — The village and the boarding school DONE in 30.7s ---

  --- SENDING Building Years — Vietnam, BIA, NAGPRA (444 words) ---
You went from Pueblo to Albuquerque, then Fort Bliss, Long Binh, Vietnam, Bill, University, and New Mexico. How do you see your legacy continuing?
  --- Building Years — Vietnam, BIA, NAGPRA DONE in 24.5s ---

  --- SENDING Later Years — What stays at the Pueblo (438 words) ---
What does it mean to you to be raising a family in this community, with its rich traditions and history?
  --- Later Years — What stays at the Pueblo DONE in 9.7s ---

  --- SENDING Bonus probe (11 words) ---
It was an honor to hear your stories and reflections. We've touched on several parts of your story, but there's still much to explore. Where would you like to continue today?
  --- Bonus probe DONE in 7.9s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/regional_native_american_new_mexico_33f2899d-bd0.txt
```

### live:stefi_crypto_jewish_new_mexico
- Status: `RUN`
- Command: `python3 scripts/run_regional_crypto_jewish_new_mexico_harness.py`
- Return code: `0`
- Duration: `42.9s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/regional_crypto_jewish_new_mexico_e64a84bf-add.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Stefi Sandoval (Crypto-Jewish New Mexico) via POST /api/people/intake
======================================================================
  ✓ Stefi Sandoval (Crypto-Jewish New Mexico) created — person_id=94615512-9ff1-4d44-8cb2-957ea43ce47c
  ✓ bio_facts_written: 15


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=e64a84bf-add

  --- SENDING Earliest Years — Candles in the cellar (495 words) ---
Here's a possible response that follows the guidelines:

"You mentioned your family's traditions, like lighting candles on Friday evenings and not eating pork.Tú had an older brother Antonio y made my First Communion. ¿Qué pasó después?
  --- Earliest Years — Candles in the cellar DONE in 23.8s ---

  --- SENDING Building Years — The vocabulary arrives in 1985 (510 words) ---
Entendido — Well. ¿Qué pasó después?
  --- Building Years — The vocabulary arrives in 1985 DONE in 1.2s ---

  --- SENDING Later Years — Breaking the rule on purpose (536 words) ---
Capté Santa Fe y David. ¿Qué pasó después?
  --- Later Years — Breaking the rule on purpose DONE in 8.6s ---

  --- SENDING Bonus probe (11 words) ---
We've touched on several parts of your story. Where would you like to continue today?
  --- Bonus probe DONE in 5.5s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/regional_crypto_jewish_new_mexico_e64a84bf-add.txt
```

## Phase 5 — Test Lab

- runner_exists: `False`
- runner_path: `/mnt/c/Users/chris/hornelore/scripts/run_test_lab.sh`
- mode: `dry`
- status: `SKIP: scripts/run_test_lab.sh missing`

## Phase 6 — John Baldy preflight

- Preflight passed with no findings.

Questionnaire readback excerpt:
```json
{
  "ok": true,
  "person_id": "d11572d4-57a1-4100-8426-cfd7293a7441",
  "questionnaire": {
    "personal": {
      "fullName": "John Baldy",
      "preferredName": "John",
      "birthOrder": "",
      "dateOfBirth": "1960-12-31",
      "timeOfBirth": "",
      "placeOfBirth": "west St. Paul Minnestota",
      "zodiacSign": "",
      "currentResidence": "Las Vegas NM",
      "pronouns": "he/him"
    },
    "parents": [],
    "siblings": [],
    "spouses": [],
    "children": [],
    "education": {
      "highestLevel": "",
      "careerProgression": "",
      "primaryCareer": ""
    },
    "military": {
      "served": false,
      "branch": "",
      "servicePeriod": "",
      "rank": "",
      "units": "",
      "locations": "",
      "warsConflicts": "",
      "decorations": "",
      "experienceNotes": ""
    },
    "faith": {
      "religionRaised": "",
      "currentFaith": "",
      "ethnicityHeritage": "",
      "languagesAtHome": ""
    },
    "today": {
      "livingSituation": "Live alone in own house.",
      "healthConsiderations": ""
    }
  },
  "_meta": {
    "personal": {
      "fullName": {
        "status": "operator_entered",
        "source": "operator"
      },
      "preferredName": {
        "status": "operator_entered",
        "source": "operator"
      },
      "dateOfBirth": {
        "status": "operator_entered",
        "source": "operator"
      },
      "placeOfBirth": {
        "status": "operator_entered",
        "source": "operator"
      }
    },
    "parents": {},
    "siblings": {
      "_section": {
        "status": "empty",
        "source": ""
      }
    },
    "spouses": {},
    "children": {
      "_section": {
        "status": "empty",
        "source": ""
      }
    },
    "education": {},
    "military": {
      "served": {
        "status": "operator_entered",
        "source": "operator"
      }
    },
    "faith": {},
    "today": {}
  },
  "source": "bio_facts_merged",
  "version": 1,
  "updated_at": "2026-06-17T16:12:20.322043"
}
```

## Phase 7 — Corrected John Baldy Life Map backend diagnostic

These are first-person John turns. No operator directive text is sent as narrator content.

### ❌ Earliest Years — `FAIL`
- era_id: `earliest_years`
- duration: `6.3s`

John turn:
```text
I was born on December 31, 1960, in West St. Paul, Minnesota. My mother is still alive at 99 and lives in St. Paul, so those earliest roots are still connected to my life now.
```

Lori response:
```text
West St. Paul, Minnesota — that's a clear memory of your earliest roots. What does St. Paul represent for you today?
```

Findings:
- VRAM-GUARD truncating input seen

Log findings:
- VRAM-GUARD truncating input seen

### ❌ Early School Years — `FAIL`
- era_id: `early_school_years`
- duration: `8.1s`

John turn:
```text
I went to school in St. Paul. I also attended military school, but that was school, not military service. I did not serve in the military.
```

Lori response:
```text
St. Paul is where your educational journey began. Military school is also an important part of your educational experience. What kind of memories or experiences come to mind when you think about attending military school?
```

Findings:
- VRAM-GUARD truncating input seen

Log findings:
- VRAM-GUARD truncating input seen

### ❌ Adolescence — `FAIL`
- era_id: `adolescence`
- duration: `9.7s`

John turn:
```text
When I was a teenager, my father died. He was changing a tire and was hit by a car. I also traveled in Europe as a teenager.
```

Lori response:
```text
Europe. What do you remember about your travels and the places you visited?
```

Findings:
- VRAM-GUARD truncating input seen

Log findings:
- VRAM-GUARD truncating input seen

### ❌ Coming of Age — `FAIL`
- era_id: `coming_of_age`
- duration: `7.7s`

John turn:
```text
I went to college in New York. I earned one bachelor's degree and three master's degrees. I do not want to fill in the school names or majors right now.
```

Lori response:
```text
New York City, the setting for some of your educational pursuits. It's interesting that you earned multiple master's degrees. What does it mean to you to have pursued higher education in such a concentrated way?
```

Findings:
- VRAM-GUARD truncating input seen

Log findings:
- VRAM-GUARD truncating input seen

### ❌ Building Years — `FAIL`
- era_id: `building_years`
- duration: `9.0s`

John turn:
```text
My work life included selling natural tobacco cigarettes and being a beer maker or brewer. Later I taught at NMHU, New Mexico Highlands University. I became a school psychologist in 2010.
```

Lori response:
```text
New Mexico Highlands University. What were some of the key experiences that led you to make that change in 2010?
```

Findings:
- VRAM-GUARD truncating input seen

Log findings:
- VRAM-GUARD truncating input seen

### ❌ Later Years — `FAIL`
- era_id: `later_years`
- duration: `8.0s`

John turn:
```text
I have been married twice. I am divorced again now. I have two children. I continued my professional identity as a school psychologist in New Mexico.
```

Lori response:
```text
Family life has been a significant part of your journey. You've been married twice and have two children. What role has being a school psychologist played in your life as a parent and a professional?
```

Findings:
- VRAM-GUARD truncating input seen

Log findings:
- VRAM-GUARD truncating input seen

### ❌ Today — `FAIL`
- era_id: `today`
- duration: `8.9s`

John turn:
```text
Today I live alone in my own house in Las Vegas, New Mexico. I currently work as a school psychologist in Pecos Schools. My mother is still alive at 99 and lives in St. Paul.
```

Lori response:
```text
Las Vegas. What does your daily routine look like now that you're working as a school psychologist in Pecos Schools?
```

Findings:
- VRAM-GUARD truncating input seen

Log findings:
- VRAM-GUARD truncating input seen

## Phase 8 — Harvested harness report snippets

### `/mnt/c/Users/chris/hornelore/docs/reports/alex_they_long_narration_de774494-cc3.txt`
```text
================================================================================
ALEX EUNSEO PARK (THEY/THEM) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    de774494-cc3
person_id:  522e6423-3211-45ae-8215-92de609e816e
run_time:   2026-06-17 17:49:02

────────────────────────────────────────────────────────────────────────────────
CHAPTER — Earliest Years — Capitol Hill
────────────────────────────────────────────────────────────────────────────────
  word_count:     14
  question_count: 2
  anchor_hits:    (none)

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ Got it — Pretty Mixed. Did I get that name right? What happened next?
  └────────────────────────────────────────────────────────────────────────────

  Scoring matrix:
    ✗ reflection_grounded: FAIL
    ⚠ one_question_max: PARTIAL
    ✓ no_questionnaire_interrogation: PASS
    ✓ no_forbidden_empathy_openers: PASS
    ✓ no_era_label_menu: PASS
    ✓ no_same_anchor_loop: PASS
    ✓ word_budget_honored: PASS
    ✓ translation_refusal_absent: PASS
    ✗ no_false_name_confirmation: FAIL
```

### `/mnt/c/Users/chris/hornelore/docs/reports/jake_long_narration_jake_long_narration_a0d30543bb1f.txt`
```text
================================================================================
JAKE MAX MILLER LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    jake_long_narration_a0d30543bb1f
person_id:  f51ef4a5-489a-49cd-a589-4ca49ef03760
run_time:   2026-06-17 17:47:43

Stack signature: oral_history default + Phase 1 validators +
                 reflection-grounding + thread bank +
                 LORI-CONFIRM scaffolding (post-WO sequence)

────────────────────────────────────────────────────────────────────────────────
STEP 1 — Intake orchestrator result
────────────────────────────────────────────────────────────────────────────────
  person_id: f51ef4a5-489a-49cd-a589-4ca49ef03760
  intake_endpoint: http://localhost:8000/api/people/intake
  intake_payload_sections: 7
  intake_status: 200

────────────────────────────────────────────────────────────────────────────────
CHAPTER — CHAPTER 1 — EARLIEST YEARS
────────────────────────────────────────────────────────────────────────────────

  word_count:    11
  question_count: 1
  anchor_hits:   (none)

  Lori response (verbatim):
  ┌──────────────────────────────────
```

### `/mnt/c/Users/chris/hornelore/docs/reports/pat_teacher_betty_23d3fd0b-a6f.txt`
```text
================================================================================
PATRICIA 'PAT' FRYE (TEACHER + BETTY) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    23d3fd0b-a6f
person_id:  fd73aabc-dfd3-4cce-8e1c-0f4b1d8d4078
run_time:   2026-06-17 17:50:54

────────────────────────────────────────────────────────────────────────────────
CHAPTER — Earliest Years — Princeton Avenue + meeting Betty
────────────────────────────────────────────────────────────────────────────────
  word_count:     34
  question_count: 1
  anchor_hits:    rubber, princeton avenue

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ You said Princeton Avenue: a small two-story bungalow on a street called Princeton Avenue, near where the rubber plants put up workers' housing after the war. What was Princeton Avenue actually like for you?
  └────────────────────────────────────────────────────────────────────────────

  Scoring matrix:
    ✓ reflection_grounded: PASS
    ✓ one_question_max: PASS
    ✓ no_questionnaire_interrogation: PASS
    ✓ no_forbidden_empathy_open
```

### `/mnt/c/Users/chris/hornelore/docs/reports/regional_african_american_georgia_36cccf42-580.txt`
```text
================================================================================
MABLE HUDSON (AFRICAN AMERICAN GEORGIA) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    36cccf42-580
person_id:  b4f40c5b-0385-48d1-b442-92afba320945
run_time:   2026-06-17 17:51:48

────────────────────────────────────────────────────────────────────────────────
CHAPTER — Earliest Years — Cotton land + Mount Olive AME
────────────────────────────────────────────────────────────────────────────────
  word_count:     32
  question_count: 1
  anchor_hits:    mother hampton

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ You said Mother Hampton: The choir was led by Mother Hampton, who was a big woman with a voice that could move the rafters. What was Mother Hampton actually like for you?
  └────────────────────────────────────────────────────────────────────────────

  Scoring matrix:
    ✓ reflection_grounded: PASS
    ✓ one_question_max: PASS
    ✓ no_questionnaire_interrogation: PASS
    ✓ no_forbidden_empathy_openers: PASS
    ✓ no_era_label_menu: PASS
    ✓ no
```

### `/mnt/c/Users/chris/hornelore/docs/reports/regional_asian_american_california_80b0484a-062.txt`
```text
================================================================================
FRANK YAMADA (JAPANESE-AMERICAN CALIFORNIA) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    80b0484a-062
person_id:  c9b4b9ac-b820-428a-8033-84e37b349851
run_time:   2026-06-17 17:52:18

────────────────────────────────────────────────────────────────────────────────
CHAPTER — Earliest Years — Strawberry rows and Tule Lake
────────────────────────────────────────────────────────────────────────────────
  word_count:     11
  question_count: 1
  anchor_hits:    (none)

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ Got it — Because The Adults Stopped Moving. What happened next?
  └────────────────────────────────────────────────────────────────────────────

  Scoring matrix:
    ✗ reflection_grounded: FAIL
    ✓ one_question_max: PASS
    ✓ no_questionnaire_interrogation: PASS
    ✓ no_forbidden_empathy_openers: PASS
    ✓ no_era_label_menu: PASS
    ✓ no_same_anchor_loop: PASS
    ✓ word_budget_honored: PASS
    ✓ translation_refusal_absent: PASS
    ✓ no_false_n
```

### `/mnt/c/Users/chris/hornelore/docs/reports/regional_crypto_jewish_new_mexico_e64a84bf-add.txt`
```text
================================================================================
STEFI SANDOVAL (CRYPTO-JEWISH NEW MEXICO) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    e64a84bf-add
person_id:  94615512-9ff1-4d44-8cb2-957ea43ce47c
run_time:   2026-06-17 17:54:21

────────────────────────────────────────────────────────────────────────────────
CHAPTER — Earliest Years — Candles in the cellar
────────────────────────────────────────────────────────────────────────────────
  word_count:     14
  question_count: 1
  anchor_hits:    antonio, first communion

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ Tú had an older brother Antonio y made my First Communion. ¿Qué pasó después?
  └────────────────────────────────────────────────────────────────────────────

  Scoring matrix:
    ✓ reflection_grounded: PASS
    ✓ one_question_max: PASS
    ✓ no_questionnaire_interrogation: PASS
    ✓ no_forbidden_empathy_openers: PASS
    ✓ no_era_label_menu: PASS
    ✓ no_same_anchor_loop: PASS
    ✓ word_budget_honored: PASS
    ✓ translation_refusal_absent:
```

### `/mnt/c/Users/chris/hornelore/docs/reports/regional_native_american_new_mexico_33f2899d-bd0.txt`
```text
================================================================================
JOE QUINTANA (COCHITI PUEBLO) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    33f2899d-bd0
person_id:  6cc553f1-6126-43e0-99e8-aad4739bf672
run_time:   2026-06-17 17:53:37

────────────────────────────────────────────────────────────────────────────────
CHAPTER — Earliest Years — The village and the boarding school
────────────────────────────────────────────────────────────────────────────────
  word_count:     53
  question_count: 1
  anchor_hits:    cochiti pueblo, drummer, kiva

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ Cochiti Pueblo. What a rich and vivid account of your early years at Cochiti Pueblo! I'm grateful for the stories you're willing to share. 
  │ 
  │ As I listen, I'm reminded of the traditional Cochiti family on the inside and the Catholic influences on the outside. Your father's role as a drummer for the kiva?
  └────────────────────────────────────────────────────────────────────────────

  Scoring matrix:
    ✓ reflection_grounded: PAS
```

### `/mnt/c/Users/chris/hornelore/docs/reports/richard_late_coming_out_100eaa51-c43.txt`
```text
================================================================================
RICHARD BELLAMY (LATE COMING-OUT) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    100eaa51-c43
person_id:  b284afb2-5a8a-4124-9634-690d20d67b4c
run_time:   2026-06-17 17:49:57

────────────────────────────────────────────────────────────────────────────────
CHAPTER — Earliest Years — Oakland, Pittsburgh
────────────────────────────────────────────────────────────────────────────────
  word_count:     22
  question_count: 1
  anchor_hits:    sacred heart, father donnelly

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ Father Donnelly at Sacred Heart was a figure of authority larger than my father. What was Father Donnelly actually like for you?
  └────────────────────────────────────────────────────────────────────────────

  Scoring matrix:
    ✓ reflection_grounded: PASS
    ✓ one_question_max: PASS
    ✓ no_questionnaire_interrogation: PASS
    ✓ no_forbidden_empathy_openers: PASS
    ✓ no_era_label_menu: PASS
    ✓ no_same_anchor_loop: PASS
    ✓ word_budget_h
```

### `/mnt/c/Users/chris/hornelore/docs/reports/seven_era_walk_d3705a49-568.txt`
```text
================================================================================
WALTER O'DONNELL (7-ERA WALK) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    d3705a49-568
person_id:  2bbf9704-4323-4d9b-944a-0a34a03013b7
run_time:   2026-06-17 17:47:11

────────────────────────────────────────────────────────────────────────────────
CHAPTER — Era 1 — Earliest Years (G Street, Southie 1948-53)
────────────────────────────────────────────────────────────────────────────────
  word_count:     85
  question_count: 1
  anchor_hits:    saint patrick, south boston, patrick, old spice

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ Saint Patrick's Day. What a beautiful and evocative passage! It's clear that you have a rich collection of memories from your earliest years, many of which are tied to sensory experiences. 
  │ 
  │ Let me reflect one specific detail from what you just said: the smell of the Old Spice your father wore on Sundays. That's a vivid scent that transports you back to those days.
  │ 
  │ Now, I have South Boston, Massachusetts a
```

### `/mnt/c/Users/chris/hornelore/docs/reports/shatner_long_narration_50f5ed8d-912.txt`
```text
================================================================================
WILLIAM SHATNER — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    50f5ed8d-912
person_id:  d83c7edb-c3de-4196-9e39-bbe019b61863
run_time:   2026-06-17 17:48:16

────────────────────────────────────────────────────────────────────────────────
CHAPTER — Earliest Years — Montreal
────────────────────────────────────────────────────────────────────────────────
  word_count:     10
  question_count: 1
  anchor_hits:    (none)

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ Got it — It Was The Air. What happened next?
  └────────────────────────────────────────────────────────────────────────────

  Scoring matrix:
    ✗ reflection_grounded: FAIL
    ✓ one_question_max: PASS
    ✓ no_questionnaire_interrogation: PASS
    ✓ no_forbidden_empathy_openers: PASS
    ✓ no_era_label_menu: PASS
    ✓ no_same_anchor_loop: PASS
    ✓ word_budget_honored: PASS
    ✓ translation_refusal_absent: PASS
    ✓ no_false_name_confirmation: PASS
    ✗ no_got_it_stub: FAIL
    ✗ no_titlecase
```
