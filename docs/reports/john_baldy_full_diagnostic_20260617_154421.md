# John Baldy Full Diagnostic Harness Report

- Run time: `2026-06-17 15:55:40`
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
Ran 24 tests in 0.021s

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
Ran 18 tests in 0.103s

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
- Duration: `110.5s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/seven_era_walk_ee17ad07-f61.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Walter O'Donnell (7-era walk) via POST /api/people/intake
======================================================================
  ✓ Walter O'Donnell (7-era walk) created — person_id=6951d40e-bf5a-44e7-b7e6-e0a76250b9c3
  ✓ bio_facts_written: 15


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=ee17ad07-f61

  --- SENDING Era 1 — Earliest Years (G Street, Southie 1948-53) (327 words) ---
What a rich and vivid memory you have of your earliest years. The smells of South Boston in 1950 come alive in your description -.
  --- Era 1 — Earliest Years (G Street, Southie 1948-53) DONE in 32.9s ---

  --- SENDING Era 2 — Early School Years (Saint Augustine's 1953-59) (379 words) ---
You went from Saint Augustine to Brendan, then Eileen, Patrick, Catholic, South Boston, Mass, and Walter. That was the start of your journey with numbers?
  --- Era 2 — Early School Years (Saint Augustine's 1953-59) DONE in 13.2s ---

  --- SENDING Era 3 — Adolescence (Boston Latin + math team 1960-65) (367 words) ---
You said Boston Latin: I went to Boston Latin School. What was Boston Latin actually like for you?
  --- Era 3 — Adolescence (Boston Latin + math team 1960-65) DONE in 9.3s ---

  --- SENDING Era 4 — Coming of Age (BC + Catherine + first sons 1966-76) (404 words) ---
You went from Boston College to Brendan, then Chestnut Hill, Kennedy, Irish, Catholic, Schlitz, and Eileen. What happened next?
  --- Era 4 — Coming of Age (BC + Catherine + first sons 1966-76) DONE in 23.0s ---

  --- SENDING Era 5 — Building Years (North Quincy 35 yrs + 4 boys) (395 words) ---
You said North Quincy: Lynn for ten years, then moved to North Quincy High School — the public school in the town we had bought. What was North Quincy actually like for you?
  --- Era 5 — Building Years (North Quincy 35 yrs + 4 boys) DONE in 6.9s ---

  --- SENDING Era 6 — Later Years (retire 2020 + tutoring + boardwalk) (431 words) ---
Got it — In March. What happened next?
  --- Era 6 — Later Years (retire 2020 + tutoring + boardwalk) DONE in 0.9s ---

  --- SENDING Era 7 — Today (a Tuesday in 2026 + the slip about a daughter) (396 words) ---
Let me say that in English. What would you like to tell me next?
  --- Era 7 — Today (a Tuesday in 2026 + the slip about a daughter) DONE in 9.1s ---

  --- SENDING Bonus probe (11 words) ---
You've wrapped up nicely. What's left to say, then, is that I've reflected back on your words: 

"The earliest years and the school years and the math team and the marriage and the boys and the classroom and the retirement and the tutoring — they all turn into today, eventually. They become the days you are still living."

Would you like to explore this idea further, or perhaps ask a question about it?
  --- Bonus probe DONE in 12.1s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/seven_era_walk_ee17ad07-f61.txt
```

### live:jake_reference
- Status: `RUN`
- Command: `python3 scripts/run_jake_long_narration_harness.py`
- Return code: `0`
- Duration: `48.8s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/jake_long_narration_jake_long_narration_1744507584ae.txt`
stdout tail:
```text
=======
  WS:        ws://localhost:8000/api/chat/ws
  person_id: 2aece04c-655f-4029-911f-5fd26611fbc0
  style:     oral_history


======================================================================
  CHAPTER 1 — EARLIEST YEARS
======================================================================
  --- SENDING CHAPTER 1 — EARLIEST YEARS (568 words) ---
Got it — Originally Schong With A C. What happened next?
  --- CHAPTER 1 — EARLIEST YEARS DONE in 1.1s ---

======================================================================
  CHAPTER 2 — EARLY SCHOOL YEARS
======================================================================
  --- SENDING CHAPTER 2 — EARLY SCHOOL YEARS (666 words) ---
Got it — You Learned To Stand Up And Sit Down And Kneel At The Right Times. What happened next?
  --- CHAPTER 2 — EARLY SCHOOL YEARS DONE in 1.1s ---

======================================================================
  CHAPTER 3 — LATER YEARS
======================================================================
  --- SENDING CHAPTER 3 — LATER YEARS (716 words) ---
Christmas Eve is coming around again in a few months. What was Christmas Eve actually like for you?
  --- CHAPTER 3 — LATER YEARS DONE in 36.1s ---

======================================================================
  BONUS PROBE — closing marker
======================================================================
  --- SENDING BONUS PROBE — closing marker (11 words) ---
We've touched on several parts of your story. Where would you like to continue today?
  --- BONUS PROBE — closing marker DONE in 5.4s ---

================================================================================
JAKE MAX MILLER LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    jake_long_narration_1744507584ae
person_id:  2aece04c-655f-4029-911f-5fd26611fbc0
run_time:   2026-06-17 15:47:14

Stack signature: oral_history default + Phase 1 validators +
                 reflection-grounding + thread bank +
                 LORI-CONFIRM scaffolding (post-WO sequence)

────────────────────────────────────────────────────────────────────────────────
STEP 1 — Intake orchestrator result
────────────────────────────────────────────────────────────────────────────────
  person_id: 2aece04c-655f-4029-911f-5fd26611fbc0
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
  oral_history_style_lines: 130
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

Report file: /mnt/c/Users/chris/hornelore/docs/reports/jake_long_narration_jake_long_narration_1744507584ae.txt
================================================================================

✓ Report written: /mnt/c/Users/chris/hornelore/docs/reports/jake_long_narration_jake_long_narration_1744507584ae.txt
```

### live:shatner_public_figure
- Status: `RUN`
- Command: `python3 scripts/run_shatner_long_narration_harness.py`
- Return code: `0`
- Duration: `19.3s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/shatner_long_narration_11ac3d3f-562.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating William Shatner via POST /api/people/intake
======================================================================
  ✓ William Shatner created — person_id=f655737b-b2db-4bb2-83cf-a830f71917fa
  ✓ bio_facts_written: 13


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=11ac3d3f-562

  --- SENDING Earliest Years — Montreal (421 words) ---
Got it — It Was The Air. What happened next?
  --- Earliest Years — Montreal DONE in 1.2s ---

  --- SENDING Building Years — Stage to Star Trek (486 words) ---
You said New York: a number of other parts, and the New York theater world came up and saw me, and Broadway was the next step. What was New York actually like for you?
  --- Building Years — Stage to Star Trek DONE in 6.7s ---

  --- SENDING Later Years — Looking Back from 93 (476 words) ---
Got it — Ottawa. What happened next?
  --- Later Years — Looking Back from 93 DONE in 1.0s ---

  --- SENDING Bonus probe (11 words) ---
Is there a particular era or theme you'd like to revisit?
  --- Bonus probe DONE in 7.4s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/shatner_long_narration_11ac3d3f-562.txt
```

### live:alex_pronouns
- Status: `RUN`
- Command: `python3 scripts/run_alex_they_long_narration_harness.py`
- Return code: `1`
- Duration: `0.2s`
stdout tail:
```text
======================================================================
STEP 1 — Creating Alex Eunseo Park (they/them) via POST /api/people/intake
======================================================================
  ✗ INTAKE FAILED — HTTP 422
  Body: {
  "detail": [
    {
      "type": "int_parsing",
      "loc": [
        "body",
        "marriage",
        "spouses",
        0,
        "year_married"
      ],
      "msg": "Input should be a valid integer, unable to parse string as an integer",
      "input": ""
    }
  ]
}
```

### live:richard_late_coming_out
- Status: `RUN`
- Command: `python3 scripts/run_richard_late_coming_out_harness.py`
- Return code: `0`
- Duration: `53.4s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/richard_late_coming_out_4f174a88-852.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Richard Bellamy (late coming-out) via POST /api/people/intake
======================================================================
  ✓ Richard Bellamy (late coming-out) created — person_id=39789cb0-110d-4e58-82e2-c0793a690b70
  ✓ bio_facts_written: 15


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=4f174a88-852

  --- SENDING Earliest Years — Oakland, Pittsburgh (484 words) ---
Father Donnelly at Sacred Heart was a figure of authority larger than my father. What was Father Donnelly actually like for you?
  --- Earliest Years — Oakland, Pittsburgh DONE in 33.4s ---

  --- SENDING Building Years — Marriage + the door (551 words) ---
Got it — It Out Loud In The Empty Kitchen. What happened next?
  --- Building Years — Marriage + the door DONE in 1.0s ---

  --- SENDING Later Years — Tomás and the life after (525 words) ---
You went from Mexico City to Strip District, then Pittsburgh, Patrick, Maureen, Kathleen, Catholic, and Thanksgiving. What was it like to reconnect with your siblings and forge a deeper understanding with them after coming out?
  --- Later Years — Tomás and the life after DONE in 10.4s ---

  --- SENDING Bonus probe (11 words) ---
We've touched on several parts of your story. Where would you like to continue today?
  --- Bonus probe DONE in 5.3s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/richard_late_coming_out_4f174a88-852.txt
```

### live:pat_betty_secondary_character
- Status: `RUN`
- Command: `python3 scripts/run_pat_teacher_betty_harness.py`
- Return code: `0`
- Duration: `42.8s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/pat_teacher_betty_86590be7-178.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Patricia 'Pat' Frye (teacher + Betty) via POST /api/people/intake
======================================================================
  ✓ Patricia 'Pat' Frye (teacher + Betty) created — person_id=1f9b6611-4b62-4b64-8d2c-9d6255a55e25
  ✓ bio_facts_written: 15


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=86590be7-178

  --- SENDING Earliest Years — Princeton Avenue + meeting Betty (461 words) ---
Can you tell me about your dad Harold worked at Goodyear, and your mom Dorothy took care of you and your siblings in the two-story bungalow on Princeton Avenue. What do you remember about your daily life on that street, especially during the summers when your mom grew tomatoes and roses in the yard?
  --- Earliest Years — Princeton Avenue + meeting Betty DONE in 9.9s ---

  --- SENDING Building Years — Kent State, Jim, the classroom (452 words) ---
who was married to Don and had two children. What do you remember about your daily life as a teacher at Forrest Hill during the 1970s and 1980s? (We can come back to the rest in a moment.)
  --- Building Years — Kent State, Jim, the classroom DONE in 13.6s ---

  --- SENDING Later Years — Loss + tutoring + the small thing (472 words) ---
You went from Wednesday to Betty, then Madeleine, Engle, Wrinkle, Time, Tuesday, and October. What do you remember about where you were living during your Later Years, and how you filled your days after retiring from teaching at Forrest Hill?
  --- Later Years — Loss + tutoring + the small thing DONE in 10.6s ---

  --- SENDING Bonus probe (11 words) ---
We've touched on several parts of your story. Where would you like to continue today?
  --- Bonus probe DONE in 5.4s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/pat_teacher_betty_86590be7-178.txt
```

### live:mable_african_american_georgia
- Status: `RUN`
- Command: `python3 scripts/run_regional_african_american_georgia_harness.py`
- Return code: `0`
- Duration: `57.8s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/regional_african_american_georgia_fa1a3a10-652.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Mable Hudson (African American Georgia) via POST /api/people/intake
======================================================================
  ✓ Mable Hudson (African American Georgia) created — person_id=6a2a27b3-2c73-4fef-a7bf-6933daf80305
  ✓ bio_facts_written: 15


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=fa1a3a10-652

  --- SENDING Earliest Years — Cotton land + Mount Olive AME (531 words) ---
You said Mother Hampton: The choir was led by Mother Hampton, who was a big woman with a voice that could move the rafters. What was Mother Hampton actually like for you?
  --- Earliest Years — Cotton land + Mount Olive AME DONE in 30.5s ---

  --- SENDING Building Years — Movement, Greyhound, Detroit (488 words) ---
Can you tell me about your daddy Clarence worked at the Mr. Coleman place in Albany, Georgia, and your family had to move to Lincoln Heights when you were eleven. What was it like leaving the farm and moving to a house in Lincoln Heights with your mama's people?
  --- Building Years — Movement, Greyhound, Detroit DONE in 9.3s ---

  --- SENDING Later Years — Coming home to Albany (448 words) ---
You went from Charlene to Atlanta, then Bernard, Detroit, Plymouth Road, Albany, Earnest, and Lillian. What happened next?
  --- Later Years — Coming home to Albany DONE in 9.3s ---

  --- SENDING Bonus probe (11 words) ---
We've touched on several parts of your story. Where would you like to continue today?
  --- Bonus probe DONE in 5.3s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/regional_african_american_georgia_fa1a3a10-652.txt
```

### live:frank_japanese_american_california
- Status: `RUN`
- Command: `python3 scripts/run_regional_asian_american_california_harness.py`
- Return code: `0`
- Duration: `25.7s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/regional_asian_american_california_3c7c8651-eca.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Frank Yamada (Japanese-American California) via POST /api/people/intake
======================================================================
  ✓ Frank Yamada (Japanese-American California) created — person_id=b30ff4e6-fd74-44b7-96a5-c905932e56d0
  ✓ bio_facts_written: 15


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=3c7c8651-eca

  --- SENDING Earliest Years — Strawberry rows and Tule Lake (456 words) ---
Got it — Because The Adults Stopped Moving. What happened next?
  --- Earliest Years — Strawberry rows and Tule Lake DONE in 1.0s ---

  --- SENDING Building Years — Starting over and the extension office (422 words) ---
You said Tule Lake: He died in 1973 having said maybe four sentences about Tule Lake to me in twenty-eight years. What was Tule Lake actually like for you?
  --- Building Years — Starting over and the extension office DONE in 8.1s ---

  --- SENDING Later Years — Redress and the Target shopping center (401 words) ---
We've touched on several parts of your story. Where would you like to continue today?
  --- Later Years — Redress and the Target shopping center DONE in 5.4s ---

  --- SENDING Bonus probe (11 words) ---
Perhaps we could wrap up the conversation here?
  --- Bonus probe DONE in 7.9s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/regional_asian_american_california_3c7c8651-eca.txt
```

### live:joe_native_new_mexico
- Status: `RUN`
- Command: `python3 scripts/run_regional_native_american_new_mexico_harness.py`
- Return code: `0`
- Duration: `73.6s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/regional_native_american_new_mexico_4407895f-dd9.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Joe Quintana (Cochiti Pueblo) via POST /api/people/intake
======================================================================
  ✓ Joe Quintana (Cochiti Pueblo) created — person_id=b2833002-019c-408c-a3e3-af634f5d8e19
  ✓ bio_facts_written: 22


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=4407895f-dd9

  --- SENDING Earliest Years — The village and the boarding school (490 words) ---
Cochiti Pueblo. What a rich and vivid description of your childhood! It's clear that you have a deep connection to your Cochiti Pueblo roots and a strong sense of cultural heritage.

I'd like to take a moment to reflect on what you've shared so far. You mentioned that your father, Frank, was a drummer for the kiva?
  --- Earliest Years — The village and the boarding school DONE in 28.8s ---

  --- SENDING Building Years — Vietnam, BIA, NAGPRA (444 words) ---
You went from Pueblo to Albuquerque, then Fort Bliss, Long Binh, Vietnam, Bill, University, and New Mexico. What happened next?
  --- Building Years — Vietnam, BIA, NAGPRA DONE in 11.8s ---

  --- SENDING Later Years — What stays at the Pueblo (438 words) ---
Can you tell me more about what you mean by "keeping the things that need to be kept where they need to be kept"?
  --- Later Years — What stays at the Pueblo DONE in 23.5s ---

  --- SENDING Bonus probe (11 words) ---
We've touched on several parts of your story. Where would you like to continue today?
  --- Bonus probe DONE in 5.4s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/regional_native_american_new_mexico_4407895f-dd9.txt
```

### live:stefi_crypto_jewish_new_mexico
- Status: `RUN`
- Command: `python3 scripts/run_regional_crypto_jewish_new_mexico_harness.py`
- Return code: `0`
- Duration: `45.6s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/regional_crypto_jewish_new_mexico_c05bb4e8-41f.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Stefi Sandoval (Crypto-Jewish New Mexico) via POST /api/people/intake
======================================================================
  ✓ Stefi Sandoval (Crypto-Jewish New Mexico) created — person_id=51a99964-9fd4-4f87-9baa-a4171823ff82
  ✓ bio_facts_written: 15


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=c05bb4e8-41f

  --- SENDING Earliest Years — Candles in the cellar (495 words) ---
Let's create a response that follows the guidelines.Tú had an older brother Antonio y made my First Communion. ¿Qué pasó después?
  --- Earliest Years — Candles in the cellar DONE in 31.0s ---

  --- SENDING Building Years — The vocabulary arrives in 1985 (510 words) ---
Entendido — Well. ¿Qué pasó después?
  --- Building Years — The vocabulary arrives in 1985 DONE in 1.1s ---

  --- SENDING Later Years — Breaking the rule on purpose (536 words) ---
Capté Santa Fe y David. ¿Qué pasó después?
  --- Later Years — Breaking the rule on purpose DONE in 5.2s ---

  --- SENDING Bonus probe (11 words) ---
We've touched on several parts of your story. Where would you like to continue today?
  --- Bonus probe DONE in 5.1s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/regional_crypto_jewish_new_mexico_c05bb4e8-41f.txt
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
- duration: `6.9s`

John turn:
```text
I was born on December 31, 1960, in West St. Paul, Minnesota. My mother is still alive at 99 and lives in St. Paul, so those earliest roots are still connected to my life now.
```

Lori response:
```text
West St. Paul, Minnesota, and your mother still living in St. Paul — those early connections are still strong. What was it like growing up in West St. Paul?
```

Findings:
- VRAM-GUARD truncating input seen

Log findings:
- VRAM-GUARD truncating input seen

### ❌ Early School Years — `FAIL`
- era_id: `early_school_years`
- duration: `9.4s`

John turn:
```text
I went to school in St. Paul. I also attended military school, but that was school, not military service. I did not serve in the military.
```

Lori response:
```text
St. What was that experience like, attending a school with a military atmosphere, but not being part of the military itself?
```

Findings:
- VRAM-GUARD truncating input seen

Log findings:
- VRAM-GUARD truncating input seen

### ❌ Adolescence — `FAIL`
- era_id: `adolescence`
- duration: `5.4s`

John turn:
```text
When I was a teenager, my father died. He was changing a tire and was hit by a car. I also traveled in Europe as a teenager.
```

Lori response:
```text
Europe — what was that travel experience like for you as a teenager?
```

Findings:
- VRAM-GUARD truncating input seen

Log findings:
- VRAM-GUARD truncating input seen

### ❌ Coming of Age — `FAIL`
- era_id: `coming_of_age`
- duration: `7.6s`

John turn:
```text
I went to college in New York. I earned one bachelor's degree and three master's degrees. I do not want to fill in the school names or majors right now.
```

Lori response:
```text
College in New York, earning multiple degrees. That's quite an accomplishment. What does life in New York feel like for you now, after having spent time there for your education?
```

Findings:
- VRAM-GUARD truncating input seen

Log findings:
- VRAM-GUARD truncating input seen

### ❌ Building Years — `FAIL`
- era_id: `building_years`
- duration: `10.5s`

John turn:
```text
My work life included selling natural tobacco cigarettes and being a beer maker or brewer. Later I taught at NMHU, New Mexico Highlands University. I became a school psychologist in 2010.
```

Lori response:
```text
What motivated you to transition into being a school psychologist, compared to your earlier work?
```

Findings:
- VRAM-GUARD truncating input seen

Log findings:
- VRAM-GUARD truncating input seen

### ❌ Later Years — `FAIL`
- era_id: `later_years`
- duration: `8.2s`

John turn:
```text
I have been married twice. I am divorced again now. I have two children. I continued my professional identity as a school psychologist in New Mexico.
```

Lori response:
```text
New Mexico.
```

Findings:
- VRAM-GUARD truncating input seen

Log findings:
- VRAM-GUARD truncating input seen

### ❌ Today — `FAIL`
- era_id: `today`
- duration: `6.4s`

John turn:
```text
Today I live alone in my own house in Las Vegas, New Mexico. I currently work as a school psychologist in Pecos Schools. My mother is still alive at 99 and lives in St. Paul.
```

Lori response:
```text
Las Vegas, New Mexico, and Pecos Schools. What does life as a school psychologist in a rural area like Pecos mean to you?
```

Findings:
- VRAM-GUARD truncating input seen

Log findings:
- VRAM-GUARD truncating input seen

## Phase 8 — Harvested harness report snippets

### `/mnt/c/Users/chris/hornelore/docs/reports/jake_long_narration_jake_long_narration_1744507584ae.txt`
```text
================================================================================
JAKE MAX MILLER LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    jake_long_narration_1744507584ae
person_id:  2aece04c-655f-4029-911f-5fd26611fbc0
run_time:   2026-06-17 15:47:14

Stack signature: oral_history default + Phase 1 validators +
                 reflection-grounding + thread bank +
                 LORI-CONFIRM scaffolding (post-WO sequence)

────────────────────────────────────────────────────────────────────────────────
STEP 1 — Intake orchestrator result
────────────────────────────────────────────────────────────────────────────────
  person_id: 2aece04c-655f-4029-911f-5fd26611fbc0
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

### `/mnt/c/Users/chris/hornelore/docs/reports/pat_teacher_betty_86590be7-178.txt`
```text
================================================================================
PATRICIA 'PAT' FRYE (TEACHER + BETTY) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    86590be7-178
person_id:  1f9b6611-4b62-4b64-8d2c-9d6255a55e25
run_time:   2026-06-17 15:49:22

────────────────────────────────────────────────────────────────────────────────
CHAPTER — Earliest Years — Princeton Avenue + meeting Betty
────────────────────────────────────────────────────────────────────────────────
  word_count:     54
  question_count: 1
  anchor_hits:    harold, dorothy, goodyear, princeton avenue, roses, tomatoes

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ Can you tell me about your dad Harold worked at Goodyear, and your mom Dorothy took care of you and your siblings in the two-story bungalow on Princeton Avenue. What do you remember about your daily life on that street, especially during the summers when your mom grew tomatoes and roses in the yard?
  └────────────────────────────────────────────────────────────────────────────

  Scoring matrix:
    ✓
```

### `/mnt/c/Users/chris/hornelore/docs/reports/regional_african_american_georgia_fa1a3a10-652.txt`
```text
================================================================================
MABLE HUDSON (AFRICAN AMERICAN GEORGIA) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    fa1a3a10-652
person_id:  6a2a27b3-2c73-4fef-a7bf-6933daf80305
run_time:   2026-06-17 15:50:23

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

### `/mnt/c/Users/chris/hornelore/docs/reports/regional_asian_american_california_3c7c8651-eca.txt`
```text
================================================================================
FRANK YAMADA (JAPANESE-AMERICAN CALIFORNIA) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    3c7c8651-eca
person_id:  b30ff4e6-fd74-44b7-96a5-c905932e56d0
run_time:   2026-06-17 15:50:52

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

### `/mnt/c/Users/chris/hornelore/docs/reports/regional_crypto_jewish_new_mexico_c05bb4e8-41f.txt`
```text
================================================================================
STEFI SANDOVAL (CRYPTO-JEWISH NEW MEXICO) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    c05bb4e8-41f
person_id:  51a99964-9fd4-4f87-9baa-a4171823ff82
run_time:   2026-06-17 15:52:58

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

### `/mnt/c/Users/chris/hornelore/docs/reports/regional_native_american_new_mexico_4407895f-dd9.txt`
```text
================================================================================
JOE QUINTANA (COCHITI PUEBLO) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    4407895f-dd9
person_id:  b2833002-019c-408c-a3e3-af634f5d8e19
run_time:   2026-06-17 15:52:09

────────────────────────────────────────────────────────────────────────────────
CHAPTER — Earliest Years — The village and the boarding school
────────────────────────────────────────────────────────────────────────────────
  word_count:     57
  question_count: 1
  anchor_hits:    cochiti pueblo, frank, drummer, kiva

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ Cochiti Pueblo. What a rich and vivid description of your childhood! It's clear that you have a deep connection to your Cochiti Pueblo roots and a strong sense of cultural heritage.
  │ 
  │ I'd like to take a moment to reflect on what you've shared so far. You mentioned that your father, Frank, was a drummer for the kiva?
  └────────────────────────────────────────────────────────────────────────────

  Scoring matrix:
    ✓ refle
```

### `/mnt/c/Users/chris/hornelore/docs/reports/richard_late_coming_out_4f174a88-852.txt`
```text
================================================================================
RICHARD BELLAMY (LATE COMING-OUT) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    4f174a88-852
person_id:  39789cb0-110d-4e58-82e2-c0793a690b70
run_time:   2026-06-17 15:48:36

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

### `/mnt/c/Users/chris/hornelore/docs/reports/seven_era_walk_ee17ad07-f61.txt`
```text
================================================================================
WALTER O'DONNELL (7-ERA WALK) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    ee17ad07-f61
person_id:  6951d40e-bf5a-44e7-b7e6-e0a76250b9c3
run_time:   2026-06-17 15:46:22

────────────────────────────────────────────────────────────────────────────────
CHAPTER — Era 1 — Earliest Years (G Street, Southie 1948-53)
────────────────────────────────────────────────────────────────────────────────
  word_count:     25
  question_count: 0
  anchor_hits:    south boston

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ What a rich and vivid memory you have of your earliest years. The smells of South Boston in 1950 come alive in your description -.
  └────────────────────────────────────────────────────────────────────────────

  Scoring matrix:
    ✓ reflection_grounded: PASS
    ✓ one_question_max: PASS
    ✓ no_questionnaire_interrogation: PASS
    ✓ no_forbidden_empathy_openers: PASS
    ✓ no_era_label_menu: PASS
    ✓ no_same_anchor_loop: PASS
    ✓ word_budget_honore
```

### `/mnt/c/Users/chris/hornelore/docs/reports/shatner_long_narration_11ac3d3f-562.txt`
```text
================================================================================
WILLIAM SHATNER — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    11ac3d3f-562
person_id:  f655737b-b2db-4bb2-83cf-a830f71917fa
run_time:   2026-06-17 15:47:37

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
    ✓ no_titlecase
```
