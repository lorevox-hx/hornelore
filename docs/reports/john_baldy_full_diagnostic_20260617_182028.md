# John Baldy Full Diagnostic Harness Report

- Run time: `2026-06-17 18:32:41`
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
Ran 24 tests in 0.024s

FAILED (failures=1)
```

### unit:compose_memory_echo_spanish
- Status: `RUN`
- Return code: `0`
- Duration: `0.3s`
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
Ran 18 tests in 0.120s

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
- Duration: `87.2s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/seven_era_walk_1fa6eef6-ba0.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Walter O'Donnell (7-era walk) via POST /api/people/intake
======================================================================
  ✓ Walter O'Donnell (7-era walk) created — person_id=afb40e6e-ce08-4d8c-ae45-13c256bfa87e
  ✓ bio_facts_written: 15


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=1fa6eef6-ba0

  --- SENDING Era 1 — Earliest Years (G Street, Southie 1948-53) (327 words) ---
You have a strong sense of early childhood, which is beautiful. Let's explore that further. What do you remember about the kitchen where your mother held you and stirred something at the stove?
  --- Era 1 — Earliest Years (G Street, Southie 1948-53) DONE in 8.5s ---

  --- SENDING Era 2 — Early School Years (Saint Augustine's 1953-59) (379 words) ---
You went from Saint Augustine to Brendan, then Eileen, Patrick, Catholic, South Boston, Mass, and Walter. How that experience made you feel?
  --- Era 2 — Early School Years (Saint Augustine's 1953-59) DONE in 11.2s ---

  --- SENDING Era 3 — Adolescence (Boston Latin + math team 1960-65) (367 words) ---
You said Boston Latin: I went to Boston Latin School. What was Boston Latin actually like for you?
  --- Era 3 — Adolescence (Boston Latin + math team 1960-65) DONE in 10.6s ---

  --- SENDING Era 4 — Coming of Age (BC + Catherine + first sons 1966-76) (404 words) ---
where you excelled in math and joined the math team. You then attended Boston College on a Jesuit scholarship, majoring in mathematics. After graduating, you began teaching at a Catholic high school in Lynn and met your future wife, Catherine. They got married and had four children together. Would you like to continue exploring this chapter of your life or move on to another era? (We can come back to the rest in a moment.)
  --- Era 4 — Coming of Age (BC + Catherine + first sons 1966-76) DONE in 21.3s ---

  --- SENDING Era 5 — Building Years (North Quincy 35 yrs + 4 boys) (395 words) ---
You said North Quincy: Lynn for ten years, then moved to North Quincy High School — the public school in the town we had bought. What was North Quincy actually like for you?
  --- Era 5 — Building Years (North Quincy 35 yrs + 4 boys) DONE in 11.6s ---

  --- SENDING Era 6 — Later Years (retire 2020 + tutoring + boardwalk) (431 words) ---
Got it — In March. What happened next?
  --- Era 6 — Later Years (retire 2020 + tutoring + boardwalk) DONE in 1.1s ---

  --- SENDING Era 7 — Today (a Tuesday in 2026 + the slip about a daughter) (396 words) ---
Let me say that in English. What would you like to tell me next?
  --- Era 7 — Today (a Tuesday in 2026 + the slip about a daughter) DONE in 11.6s ---

  --- SENDING Bonus probe (11 words) ---
Is there anything else you'd like to talk about?
  --- Bonus probe DONE in 7.4s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/seven_era_walk_1fa6eef6-ba0.txt
```

### live:jake_reference
- Status: `RUN`
- Command: `python3 scripts/run_jake_long_narration_harness.py`
- Return code: `0`
- Duration: `40.7s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/jake_long_narration_jake_long_narration_e7c34070ddb5.txt`
stdout tail:
```text
6-9e53-4f6e-be30-9badee2eddb9
  style:     oral_history


======================================================================
  CHAPTER 1 — EARLIEST YEARS
======================================================================
  --- SENDING CHAPTER 1 — EARLIEST YEARS (568 words) ---
Got it — Originally Schong With A C. What happened next?
  --- CHAPTER 1 — EARLIEST YEARS DONE in 1.3s ---

======================================================================
  CHAPTER 2 — EARLY SCHOOL YEARS
======================================================================
  --- SENDING CHAPTER 2 — EARLY SCHOOL YEARS (666 words) ---
Got it — You Learned To Stand Up And Sit Down And Kneel At The Right Times. What happened next?
  --- CHAPTER 2 — EARLY SCHOOL YEARS DONE in 1.2s ---

======================================================================
  CHAPTER 3 — LATER YEARS
======================================================================
  --- SENDING CHAPTER 3 — LATER YEARS (716 words) ---
Christmas Eve is coming around again in a few months. What was Christmas Eve actually like for you?
  --- CHAPTER 3 — LATER YEARS DONE in 13.8s ---

======================================================================
  BONUS PROBE — closing marker
======================================================================
  --- SENDING BONUS PROBE — closing marker (11 words) ---
Your reflections on your father's legacy and the importance of asking questions while people are still here?
  --- BONUS PROBE — closing marker DONE in 18.3s ---

================================================================================
JAKE MAX MILLER LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    jake_long_narration_e7c34070ddb5
person_id:  1f348686-9e53-4f6e-be30-9badee2eddb9
run_time:   2026-06-17 18:22:54

Stack signature: oral_history default + Phase 1 validators +
                 reflection-grounding + thread bank +
                 LORI-CONFIRM scaffolding (post-WO sequence)

────────────────────────────────────────────────────────────────────────────────
STEP 1 — Intake orchestrator result
────────────────────────────────────────────────────────────────────────────────
  person_id: 1f348686-9e53-4f6e-be30-9badee2eddb9
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

  word_count:    22
  question_count: 1
  anchor_hits:   (none)

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ Can you tell me about your reflections on your father's legacy and the importance of asking questions while people are still here?
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
LOG SANITY GREP SUMMARY
────────────────────────────────────────────────────────────────────────────────
  oral_history_style_lines: 225
  reflection_not_grounded_or_layer_ineligible_lines: 0
  extract_accepted_lines: 55
  meal_tickets_substring_present: True
  spantag_flag_on_lines_observed: False

────────────────────────────────────────────────────────────────────────────────
AGGREGATE
────────────────────────────────────────────────────────────────────────────────
  Score rows passed: 29 / 32  (90.6%)

  Acceptance criteria:
    GREEN:  ≥ 75% rows pass AND zero hard FAILs on forbidden-empathy / era-label-menu
    AMBER:  60-75% rows pass OR partial failures on word budget / one-question-max
    RED:    < 60% rows pass OR hard FAILs on forbidden-empathy or era-label-menu

Report file: /mnt/c/Users/chris/hornelore/docs/reports/jake_long_narration_jake_long_narration_e7c34070ddb5.txt
================================================================================

✓ Report written: /mnt/c/Users/chris/hornelore/docs/reports/jake_long_narration_jake_long_narration_e7c34070ddb5.txt
```

### live:shatner_public_figure
- Status: `RUN`
- Command: `python3 scripts/run_shatner_long_narration_harness.py`
- Return code: `0`
- Duration: `42.7s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/shatner_long_narration_95910ea8-3a3.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating William Shatner via POST /api/people/intake
======================================================================
  ✓ William Shatner created — person_id=dcb9d001-54d7-411c-9109-1df952405525
  ✓ bio_facts_written: 13


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=95910ea8-3a3

  --- SENDING Earliest Years — Montreal (421 words) ---
Got it — It Was The Air. What happened next?
  --- Earliest Years — Montreal DONE in 1.3s ---

  --- SENDING Building Years — Stage to Star Trek (486 words) ---
You said New York: a number of other parts, and the New York theater world came up and saw me, and Broadway was the next step. What was New York actually like for you?
  --- Building Years — Stage to Star Trek DONE in 31.5s ---

  --- SENDING Later Years — Looking Back from 93 (476 words) ---
Got it — Ottawa. What happened next?
  --- Later Years — Looking Back from 93 DONE in 1.0s ---

  --- SENDING Bonus probe (11 words) ---
We've touched on several parts of your story. Where would you like to continue today?
  --- Bonus probe DONE in 5.5s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/shatner_long_narration_95910ea8-3a3.txt
```

### live:alex_pronouns
- Status: `RUN`
- Command: `python3 scripts/run_alex_they_long_narration_harness.py`
- Return code: `0`
- Duration: `40.9s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/alex_they_long_narration_7277f00c-f61.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Alex Eunseo Park (they/them) via POST /api/people/intake
======================================================================
  ✓ Alex Eunseo Park (they/them) created — person_id=006c3a56-6891-4528-8101-8b78e3a3f07d
  ✓ bio_facts_written: 11


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=7277f00c-f61

  --- SENDING Earliest Years — Capitol Hill (466 words) ---
Got it — Pretty Mixed. Did I get that name right? What happened next?
  --- Earliest Years — Capitol Hill DONE in 1.2s ---

  --- SENDING Coming of Age — UW + coming out (448 words) ---
You went from University to Washington, then Korean, English, Jamie, parents were happy about, summer after sophomore year, and turned into a bigger. What was it like for you, learning to navigate your identity as nonbinary, especially when sharing it with your loved ones, including your parents?
  --- Coming of Age — UW + coming out DONE in 7.5s ---

  --- SENDING Today — Thirty-six and grounded (424 words) ---
You went from Sam to Capitol Hill, then Bellevue, Sunday, Alex, Korean, English, and Soo. How did you and your partner keep in touch from overseas — letters, phone calls, telegrams?
  --- Today — Thirty-six and grounded DONE in 23.4s ---

  --- SENDING Bonus probe (11 words) ---
We've touched on several parts of your story. Where would you like to continue today?
  --- Bonus probe DONE in 5.6s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/alex_they_long_narration_7277f00c-f61.txt
```

### live:richard_late_coming_out
- Status: `RUN`
- Command: `python3 scripts/run_richard_late_coming_out_harness.py`
- Return code: `0`
- Duration: `44.6s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/richard_late_coming_out_ab61f289-73e.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Richard Bellamy (late coming-out) via POST /api/people/intake
======================================================================
  ✓ Richard Bellamy (late coming-out) created — person_id=fdc5a4e3-a245-438f-8549-ea2a08bec26b
  ✓ bio_facts_written: 15


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=ab61f289-73e

  --- SENDING Earliest Years — Oakland, Pittsburgh (484 words) ---
Father Donnelly at Sacred Heart was a figure of authority larger than my father. What was Father Donnelly actually like for you?
  --- Earliest Years — Oakland, Pittsburgh DONE in 23.4s ---

  --- SENDING Building Years — Marriage + the door (551 words) ---
Got it — It Out Loud In The Empty Kitchen. What happened next?
  --- Building Years — Marriage + the door DONE in 1.3s ---

  --- SENDING Later Years — Tomás and the life after (525 words) ---
You went from Mexico City to Strip District, then Pittsburgh, Patrick, Maureen, Kathleen, Catholic, and Thanksgiving. Where would you like to continue today?
  --- Later Years — Tomás and the life after DONE in 5.7s ---

  --- SENDING Bonus probe (11 words) ---
It sounds like you've shared a lot of your story today. Before we wrap up, is there anything else you'd like to talk about or any particular aspect of your life that you'd like to revisit?
  --- Bonus probe DONE in 10.6s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/richard_late_coming_out_ab61f289-73e.txt
```

### live:pat_betty_secondary_character
- Status: `RUN`
- Command: `python3 scripts/run_pat_teacher_betty_harness.py`
- Return code: `0`
- Duration: `63.3s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/pat_teacher_betty_508be32a-284.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Patricia 'Pat' Frye (teacher + Betty) via POST /api/people/intake
======================================================================
  ✓ Patricia 'Pat' Frye (teacher + Betty) created — person_id=94b44a19-4bb8-4f05-9e46-49d794006d92
  ✓ bio_facts_written: 15


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=508be32a-284

  --- SENDING Earliest Years — Princeton Avenue + meeting Betty (461 words) ---
Princeton Avenue. What a delightful and intimate glimpse into your life! Here's a reflection on what you just shared, followed by a question:

You described your earliest years in Akron, Ohio, where your family lived in a small bungalow on Princeton Avenue. You remembered your mother's garden, the roses, and the smell of crayons at school. You also spoke fondly of your third-grade teacher, Miss McCullough, whom you admired and looked up to.

Now, let's explore this period further:

What do you remember about your daily life and routines during your Earliest Years, when you were around three or four years old, living in Akron?
  --- Earliest Years — Princeton Avenue + meeting Betty DONE in 18.1s ---

  --- SENDING Building Years — Kent State, Jim, the classroom (452 words) ---
Kent State. which occurred after you had graduated, but which affected your friend Betty deeply. You noted that the event was not publicly discussed in your community for thirty years. Betty only shared her experience with you on the thirtieth anniversary in 2000.

Now, let's explore this period further:

What do you remember about your relationships with your friends and classmates during your college years, particularly in the context of the Kent State shootings, which were so impactful on Betty?
  --- Building Years — Kent State, Jim, the classroom DONE in 17.6s ---

  --- SENDING Later Years — Loss + tutoring + the small thing (472 words) ---
You went from Wednesday to Betty, then Madeleine, Engle, Wrinkle, Time, Tuesday, and October. What happened next?
  --- Later Years — Loss + tutoring + the small thing DONE in 18.3s ---

  --- SENDING Bonus probe (11 words) ---
We've touched on several parts of your story. Where would you like to continue today?
  --- Bonus probe DONE in 5.4s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/pat_teacher_betty_508be32a-284.txt
```

### live:mable_african_american_georgia
- Status: `RUN`
- Command: `python3 scripts/run_regional_african_american_georgia_harness.py`
- Return code: `0`
- Duration: `62.7s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/regional_african_american_georgia_5ca87bfe-0f6.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Mable Hudson (African American Georgia) via POST /api/people/intake
======================================================================
  ✓ Mable Hudson (African American Georgia) created — person_id=d8980415-ed0a-470c-ad27-70092e69e37b
  ✓ bio_facts_written: 15


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=5ca87bfe-0f6

  --- SENDING Earliest Years — Cotton land + Mount Olive AME (531 words) ---
You said Mother Hampton: The choir was led by Mother Hampton, who was a big woman with a voice that could move the rafters. What was Mother Hampton actually like for you?
  --- Earliest Years — Cotton land + Mount Olive AME DONE in 32.1s ---

  --- SENDING Building Years — Movement, Greyhound, Detroit (488 words) ---
You said Mount Zion: You slipped out at night to the mass meetings at Shiloh Baptist or Mount Zion. What do you remember about the community at Mount Zion, the people you met, or the songs you sang there?
  --- Building Years — Movement, Greyhound, Detroit DONE in 8.7s ---

  --- SENDING Later Years — Coming home to Albany (448 words) ---
You went from Charlene to Atlanta, then Bernard, Detroit, Plymouth Road, Albany, Earnest, and Lillian. How did that experience shape your understanding of home and community?
  --- Later Years — Coming home to Albany DONE in 9.0s ---

  --- SENDING Bonus probe (11 words) ---
How has life been treating you in this current chapter?
  --- Bonus probe DONE in 9.1s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/regional_african_american_georgia_5ca87bfe-0f6.txt
```

### live:frank_japanese_american_california
- Status: `RUN`
- Command: `python3 scripts/run_regional_asian_american_california_harness.py`
- Return code: `0`
- Duration: `26.2s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/regional_asian_american_california_61e1c01c-1e6.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Frank Yamada (Japanese-American California) via POST /api/people/intake
======================================================================
  ✓ Frank Yamada (Japanese-American California) created — person_id=3f446851-9bfc-4116-bcdd-50ccce52e1c5
  ✓ bio_facts_written: 15


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=61e1c01c-1e6

  --- SENDING Earliest Years — Strawberry rows and Tule Lake (456 words) ---
Got it — Because The Adults Stopped Moving. What happened next?
  --- Earliest Years — Strawberry rows and Tule Lake DONE in 1.1s ---

  --- SENDING Building Years — Starting over and the extension office (422 words) ---
Can you tell me about your father, Kenji, was quiet about his experiences, especially the time at Tule Lake, but you found ways to build a fulfilling life in Stockton. What do you remember about your time at Stockton High School, particularly with Mr. Howell's encouragement to attend college?
  --- Building Years — Starting over and the extension office DONE in 10.0s ---

  --- SENDING Later Years — Redress and the Target shopping center (401 words) ---
San Jose. What do you remember about Mitsuko, particularly the conversations that you're choosing not to share with your grandchildren?
  --- Later Years — Redress and the Target shopping center DONE in 5.9s ---

  --- SENDING Bonus probe (11 words) ---
We've touched on several parts of your story. Where would you like to continue today?
  --- Bonus probe DONE in 5.5s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/regional_asian_american_california_61e1c01c-1e6.txt
```

### live:joe_native_new_mexico
- Status: `RUN`
- Command: `python3 scripts/run_regional_native_american_new_mexico_harness.py`
- Return code: `0`
- Duration: `57.9s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/regional_native_american_new_mexico_12291895-154.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Joe Quintana (Cochiti Pueblo) via POST /api/people/intake
======================================================================
  ✓ Joe Quintana (Cochiti Pueblo) created — person_id=2921f476-a58a-432d-a85c-262e78f532a2
  ✓ bio_facts_written: 22


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=12291895-154

  --- SENDING Earliest Years — The village and the boarding school (490 words) ---
What comes to mind when you think about the summers you spent back in Cochiti Pueblo as a child?"

This response acknowledges the narrator's sharing and invites them to continue, allowing them to pick up where they left off and share more about their experiences. The question is open-ended and encourages the narrator to reflect on their memories of the village.
  --- Earliest Years — The village and the boarding school DONE in 15.9s ---

  --- SENDING Building Years — Vietnam, BIA, NAGPRA (444 words) ---
You went from Pueblo to Albuquerque, then Fort Bliss, Long Binh, Vietnam, Bill, University, and New Mexico. What happened next?
  --- Building Years — Vietnam, BIA, NAGPRA DONE in 22.3s ---

  --- SENDING Later Years — What stays at the Pueblo (438 words) ---
You mentioned the importance of holding certain stories, songs, and names within the village and the kiva, rather than sharing them more broadly. What role do you think storytelling and memory-keeping play in preserving the cultural heritage of Cochiti Pueblo?
  --- Later Years — What stays at the Pueblo DONE in 9.3s ---

  --- SENDING Bonus probe (11 words) ---
"We've touched on several parts of your story. Where would you like to continue today?"
  --- Bonus probe DONE in 5.4s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/regional_native_american_new_mexico_12291895-154.txt
```

### live:stefi_crypto_jewish_new_mexico
- Status: `RUN`
- Command: `python3 scripts/run_regional_crypto_jewish_new_mexico_harness.py`
- Return code: `0`
- Duration: `46.2s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/regional_crypto_jewish_new_mexico_7cefa1de-8fe.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Stefi Sandoval (Crypto-Jewish New Mexico) via POST /api/people/intake
======================================================================
  ✓ Stefi Sandoval (Crypto-Jewish New Mexico) created — person_id=d35b022c-6744-4cce-8372-e32d945b80ad
  ✓ bio_facts_written: 15


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=7cefa1de-8fe

  --- SENDING Earliest Years — Candles in the cellar (495 words) ---
Here is a response that follows the guidelines:

You've shared about your family's traditions and practices in Las Vegas, New Mexico.Tú had an older brother Antonio y made my First Communion. ¿Qué pasó después?
  --- Earliest Years — Candles in the cellar DONE in 26.1s ---

  --- SENDING Building Years — The vocabulary arrives in 1985 (510 words) ---
Entendido — Well. ¿Qué pasó después?
  --- Building Years — The vocabulary arrives in 1985 DONE in 1.3s ---

  --- SENDING Later Years — Breaking the rule on purpose (536 words) ---
Capté Santa Fe y David. ¿Qué pasó después?
  --- Later Years — Breaking the rule on purpose DONE in 9.7s ---

  --- SENDING Bonus probe (11 words) ---
We've touched on several parts of your story. Where would you like to continue today?
  --- Bonus probe DONE in 5.4s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/regional_crypto_jewish_new_mexico_7cefa1de-8fe.txt
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
- duration: `8.3s`

John turn:
```text
I was born on December 31, 1960, in West St. Paul, Minnesota. My mother is still alive at 99 and lives in St. Paul, so those earliest roots are still connected to my life now.
```

Lori response:
```text
West St. Paul and St. Paul — those Twin Cities roots have been a part of your life story for almost six decades. What do you remember about your earliest years growing up in West St. Paul?
```

Findings:
- VRAM-GUARD truncating input seen

Log findings:
- VRAM-GUARD truncating input seen

### ❌ Early School Years — `FAIL`
- era_id: `early_school_years`
- duration: `8.5s`

John turn:
```text
I went to school in St. Paul. I also attended military school, but that was school, not military service. I did not serve in the military.
```

Lori response:
```text
St. Paul and military school — two distinct chapters in your education. Military school sounds like a unique experience. What does it mean to you that you attended military school as a student, rather than as a service member?
```

Findings:
- VRAM-GUARD truncating input seen

Log findings:
- VRAM-GUARD truncating input seen

### ❌ Adolescence — `FAIL`
- era_id: `adolescence`
- duration: `10.3s`

John turn:
```text
When I was a teenager, my father died. He was changing a tire and was hit by a car. I also traveled in Europe as a teenager.
```

Lori response:
```text
Traveling abroad as a teenager can be a transformative experience. What do you remember about those travels in Europe, and how did they shape your perspective on the world? (We can come back to the rest in a moment.)
```

Findings:
- VRAM-GUARD truncating input seen

Log findings:
- VRAM-GUARD truncating input seen

### ❌ Coming of Age — `FAIL`
- era_id: `coming_of_age`
- duration: `10.0s`

John turn:
```text
I went to college in New York. I earned one bachelor's degree and three master's degrees. I do not want to fill in the school names or majors right now.
```

Lori response:
```text
New York. How has it impacted your life since?
```

Findings:
- VRAM-GUARD truncating input seen

Log findings:
- VRAM-GUARD truncating input seen

### ❌ Building Years — `FAIL`
- era_id: `building_years`
- duration: `9.1s`

John turn:
```text
My work life included selling natural tobacco cigarettes and being a beer maker or brewer. Later I taught at NMHU, New Mexico Highlands University. I became a school psychologist in 2010.
```

Lori response:
```text
What drew you to become a school psychologist in 2010?
```

Findings:
- VRAM-GUARD truncating input seen

Log findings:
- VRAM-GUARD truncating input seen

### ❌ Later Years — `FAIL`
- era_id: `later_years`
- duration: `6.2s`

John turn:
```text
I have been married twice. I am divorced again now. I have two children. I continued my professional identity as a school psychologist in New Mexico.
```

Lori response:
```text
As a school psychologist, how has working with students and families in New Mexico impacted your perspective on education and community development?
```

Findings:
- VRAM-GUARD truncating input seen

Log findings:
- VRAM-GUARD truncating input seen

### ❌ Today — `FAIL`
- era_id: `today`
- duration: `11.8s`

John turn:
```text
Today I live alone in my own house in Las Vegas, New Mexico. I currently work as a school psychologist in Pecos Schools. My mother is still alive at 99 and lives in St. Paul.
```

Lori response:
```text
Las Vegas. What does life in Las Vegas feel like for you now?
```

Findings:
- VRAM-GUARD truncating input seen

Log findings:
- VRAM-GUARD truncating input seen

## Phase 8 — Harvested harness report snippets

### `/mnt/c/Users/chris/hornelore/docs/reports/alex_they_long_narration_7277f00c-f61.txt`
```text
================================================================================
ALEX EUNSEO PARK (THEY/THEM) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    7277f00c-f61
person_id:  006c3a56-6891-4528-8101-8b78e3a3f07d
run_time:   2026-06-17 18:24:25

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

### `/mnt/c/Users/chris/hornelore/docs/reports/jake_long_narration_jake_long_narration_e7c34070ddb5.txt`
```text
================================================================================
JAKE MAX MILLER LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    jake_long_narration_e7c34070ddb5
person_id:  1f348686-9e53-4f6e-be30-9badee2eddb9
run_time:   2026-06-17 18:22:54

Stack signature: oral_history default + Phase 1 validators +
                 reflection-grounding + thread bank +
                 LORI-CONFIRM scaffolding (post-WO sequence)

────────────────────────────────────────────────────────────────────────────────
STEP 1 — Intake orchestrator result
────────────────────────────────────────────────────────────────────────────────
  person_id: 1f348686-9e53-4f6e-be30-9badee2eddb9
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

### `/mnt/c/Users/chris/hornelore/docs/reports/pat_teacher_betty_508be32a-284.txt`
```text
================================================================================
PATRICIA 'PAT' FRYE (TEACHER + BETTY) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    508be32a-284
person_id:  94b44a19-4bb8-4f05-9e46-49d794006d92
run_time:   2026-06-17 18:26:21

────────────────────────────────────────────────────────────────────────────────
CHAPTER — Earliest Years — Princeton Avenue + meeting Betty
────────────────────────────────────────────────────────────────────────────────
  word_count:     105
  question_count: 1
  anchor_hits:    akron, princeton avenue, roses, miss mccullough

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ Princeton Avenue. What a delightful and intimate glimpse into your life! Here's a reflection on what you just shared, followed by a question:
  │ 
  │ You described your earliest years in Akron, Ohio, where your family lived in a small bungalow on Princeton Avenue. You remembered your mother's garden, the roses, and the smell of crayons at school. You also spoke fondly of your third-grade teacher, Miss McCullough,
```

### `/mnt/c/Users/chris/hornelore/docs/reports/regional_african_american_georgia_5ca87bfe-0f6.txt`
```text
================================================================================
MABLE HUDSON (AFRICAN AMERICAN GEORGIA) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    5ca87bfe-0f6
person_id:  d8980415-ed0a-470c-ad27-70092e69e37b
run_time:   2026-06-17 18:27:28

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

### `/mnt/c/Users/chris/hornelore/docs/reports/regional_asian_american_california_61e1c01c-1e6.txt`
```text
================================================================================
FRANK YAMADA (JAPANESE-AMERICAN CALIFORNIA) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    61e1c01c-1e6
person_id:  3f446851-9bfc-4116-bcdd-50ccce52e1c5
run_time:   2026-06-17 18:27:58

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

### `/mnt/c/Users/chris/hornelore/docs/reports/regional_crypto_jewish_new_mexico_7cefa1de-8fe.txt`
```text
================================================================================
STEFI SANDOVAL (CRYPTO-JEWISH NEW MEXICO) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    7cefa1de-8fe
person_id:  d35b022c-6744-4cce-8372-e32d945b80ad
run_time:   2026-06-17 18:29:50

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

### `/mnt/c/Users/chris/hornelore/docs/reports/regional_native_american_new_mexico_12291895-154.txt`
```text
================================================================================
JOE QUINTANA (COCHITI PUEBLO) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    12291895-154
person_id:  2921f476-a58a-432d-a85c-262e78f532a2
run_time:   2026-06-17 18:29:00

────────────────────────────────────────────────────────────────────────────────
CHAPTER — Earliest Years — The village and the boarding school
────────────────────────────────────────────────────────────────────────────────
  word_count:     61
  question_count: 1
  anchor_hits:    cochiti pueblo

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ What comes to mind when you think about the summers you spent back in Cochiti Pueblo as a child?"
  │ 
  │ This response acknowledges the narrator's sharing and invites them to continue, allowing them to pick up where they left off and share more about their experiences. The question is open-ended and encourages the narrator to reflect on their memories of the village.
  └────────────────────────────────────────────────────────────────────────────

  Sc
```

### `/mnt/c/Users/chris/hornelore/docs/reports/richard_late_coming_out_ab61f289-73e.txt`
```text
================================================================================
RICHARD BELLAMY (LATE COMING-OUT) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    ab61f289-73e
person_id:  fdc5a4e3-a245-438f-8549-ea2a08bec26b
run_time:   2026-06-17 18:25:14

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

### `/mnt/c/Users/chris/hornelore/docs/reports/seven_era_walk_1fa6eef6-ba0.txt`
```text
================================================================================
WALTER O'DONNELL (7-ERA WALK) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    1fa6eef6-ba0
person_id:  afb40e6e-ce08-4d8c-ae45-13c256bfa87e
run_time:   2026-06-17 18:22:09

────────────────────────────────────────────────────────────────────────────────
CHAPTER — Era 1 — Earliest Years (G Street, Southie 1948-53)
────────────────────────────────────────────────────────────────────────────────
  word_count:     33
  question_count: 1
  anchor_hits:    (none)

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ You have a strong sense of early childhood, which is beautiful. Let's explore that further. What do you remember about the kitchen where your mother held you and stirred something at the stove?
  └────────────────────────────────────────────────────────────────────────────

  Scoring matrix:
    ✗ reflection_grounded: FAIL
    ✓ one_question_max: PASS
    ✓ no_questionnaire_interrogation: PASS
    ✓ no_forbidden_empathy_openers: PASS
    ✓ no_era_label_menu: PASS
```

### `/mnt/c/Users/chris/hornelore/docs/reports/shatner_long_narration_95910ea8-3a3.txt`
```text
================================================================================
WILLIAM SHATNER — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    95910ea8-3a3
person_id:  dcb9d001-54d7-411c-9109-1df952405525
run_time:   2026-06-17 18:23:40

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
