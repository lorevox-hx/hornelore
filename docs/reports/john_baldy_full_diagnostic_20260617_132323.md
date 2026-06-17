# John Baldy Full Diagnostic Harness Report

- Run time: `2026-06-17 13:36:21`
- API base: `http://127.0.0.1:8000`
- Canonical John person_id: `d11572d4-57a1-4100-8426-cfd7293a7441`
- Overall: **FAIL**

## Phase 0 — Bad first-run evidence scan

### C:UserschrisAppDataRoamingClaudelocal-agent-mode-sessions5d56ce72-7894-46f8-b0b4-4b9074b7aa8a352c8999-4713-49f8-988e-09c24bd90653local_506ab8b7-a4d7-43b4-b3a2-fc6f9a3fbbccuploadstranscript_switch_mqif3.txt
- Status: `MISSING_OR_UNREADABLE`
- [Errno 2] No such file or directory: 'C:UserschrisAppDataRoamingClaudelocal-agent-mode-sessions5d56ce72-7894-46f8-b0b4-4b9074b7aa8a352c8999-4713-49f8-988e-09c24bd90653local_506ab8b7-a4d7-43b4-b3a2-fc6f9a3fbbccuploadstranscript_switch_mqif3.txt'

### C:UserschrisAppDataRoamingClaudelocal-agent-mode-sessions5d56ce72-7894-46f8-b0b4-4b9074b7aa8a352c8999-4713-49f8-988e-09c24bd90653local_506ab8b7-a4d7-43b4-b3a2-fc6f9a3fbbccuploadsOPERATOR-LOG-2026-06-17-18-54-54.md
- Status: `MISSING_OR_UNREADABLE`
- [Errno 2] No such file or directory: 'C:UserschrisAppDataRoamingClaudelocal-agent-mode-sessions5d56ce72-7894-46f8-b0b4-4b9074b7aa8a352c8999-4713-49f8-988e-09c24bd90653local_506ab8b7-a4d7-43b4-b3a2-fc6f9a3fbbccuploadsOPERATOR-LOG-2026-06-17-18-54-54.md'

## Phase 1 — Unit/regression tests

### unit:lori_communication_control
- Status: `RUN`
- Return code: `1`
- Duration: `0.3s`
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
Ran 24 tests in 0.031s

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
Ran 32 tests in 0.003s

OK
```

### unit:bio_questionnaire_writer
- Status: `RUN`
- Return code: `0`
- Duration: `0.3s`
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
Ran 18 tests in 0.163s

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
- Duration: `95.9s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/seven_era_walk_2f9448fc-492.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Walter O'Donnell (7-era walk) via POST /api/people/intake
======================================================================
  ✓ Walter O'Donnell (7-era walk) created — person_id=3faf4b5c-39ce-4c9c-b00e-7298c7ba6d7d
  ✓ bio_facts_written: 15


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=2f9448fc-492

  --- SENDING Era 1 — Earliest Years (G Street, Southie 1948-53) (327 words) ---
Esa sensación de calidez en la cocina con tu madre mientras removía algo en la estufa está tan viva en mi memoria. ¿Qué recuerdas sobre.
  --- Era 1 — Earliest Years (G Street, Southie 1948-53) DONE in 11.2s ---

  --- SENDING Era 2 — Early School Years (Saint Augustine's 1953-59) (379 words) ---
You went from Saint Augustine to Brendan, then Eileen, Patrick, Catholic, South Boston, Mass, and Walter. What happened next?
  --- Era 2 — Early School Years (Saint Augustine's 1953-59) DONE in 26.0s ---

  --- SENDING Era 3 — Adolescence (Boston Latin + math team 1960-65) (367 words) ---
You said Boston Latin: I went to Boston Latin School. You kept coming back to Boston Latin — what was that actually like for you?
  --- Era 3 — Adolescence (Boston Latin + math team 1960-65) DONE in 12.4s ---

  --- SENDING Era 4 — Coming of Age (BC + Catherine + first sons 1966-76) (404 words) ---
You went from Boston College to Brendan, then Chestnut Hill, Kennedy, Irish, Catholic, Schlitz, and Eileen. What happened next?
  --- Era 4 — Coming of Age (BC + Catherine + first sons 1966-76) DONE in 9.3s ---

  --- SENDING Era 5 — Building Years (North Quincy 35 yrs + 4 boys) (395 words) ---
You said North Quincy: Lynn for ten years, then moved to North Quincy High School — the public school in the town we had bought. You kept coming back to North Quincy — what was that actually like for you?
  --- Era 5 — Building Years (North Quincy 35 yrs + 4 boys) DONE in 10.5s ---

  --- SENDING Era 6 — Later Years (retire 2020 + tutoring + boardwalk) (431 words) ---
Got it — In March. Did I get that name right? What happened next?
  --- Era 6 — Later Years (retire 2020 + tutoring + boardwalk) DONE in 1.5s ---

  --- SENDING Era 7 — Today (a Tuesday in 2026 + the slip about a daughter) (396 words) ---
Let me say that in English. What would you like to tell me next?
  --- Era 7 — Today (a Tuesday in 2026 + the slip about a daughter) DONE in 10.5s ---

  --- SENDING Bonus probe (11 words) ---
That's all for now. Thank you for sharing your story with me. Would you like to continue talking or is there something else I can help you with?
  --- Bonus probe DONE in 9.4s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/seven_era_walk_2f9448fc-492.txt
```

### live:jake_reference
- Status: `RUN`
- Command: `python3 scripts/run_jake_long_narration_harness.py`
- Return code: `0`
- Duration: `33.4s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/jake_long_narration_jake_long_narration_a7a09ab02c98.txt`
stdout tail:
```text
==========================
  CHAPTER 1 — EARLIEST YEARS
======================================================================
  --- SENDING CHAPTER 1 — EARLIEST YEARS (568 words) ---
Got it — Originally Schong With A C. Did I get that name right? What happened next?
  --- CHAPTER 1 — EARLIEST YEARS DONE in 1.9s ---

======================================================================
  CHAPTER 2 — EARLY SCHOOL YEARS
======================================================================
  --- SENDING CHAPTER 2 — EARLY SCHOOL YEARS (666 words) ---
Got it — You Learned To Stand Up And Sit Down And Kneel At The Right Times. Did I get that name right? What happened next?
  --- CHAPTER 2 — EARLY SCHOOL YEARS DONE in 1.9s ---

======================================================================
  CHAPTER 3 — LATER YEARS
======================================================================
  --- SENDING CHAPTER 3 — LATER YEARS (716 words) ---
Christmas Eve is coming around again in a few months. You kept coming back to Christmas Eve — what was that actually like for you?
  --- CHAPTER 3 — LATER YEARS DONE in 13.3s ---

======================================================================
  BONUS PROBE — closing marker
======================================================================
  --- SENDING BONUS PROBE — closing marker (11 words) ---
We've touched on several parts of your story. Where would you like to continue today?
  --- BONUS PROBE — closing marker DONE in 8.5s ---

================================================================================
JAKE MAX MILLER LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    jake_long_narration_a7a09ab02c98
person_id:  9aeea5f6-4a1a-4bf1-901c-4b986ea2a002
run_time:   2026-06-17 13:25:55

Stack signature: oral_history default + Phase 1 validators +
                 reflection-grounding + thread bank +
                 LORI-CONFIRM scaffolding (post-WO sequence)

────────────────────────────────────────────────────────────────────────────────
STEP 1 — Intake orchestrator result
────────────────────────────────────────────────────────────────────────────────
  person_id: 9aeea5f6-4a1a-4bf1-901c-4b986ea2a002
  intake_endpoint: http://localhost:8000/api/people/intake
  intake_payload_sections: 7
  intake_status: 200

────────────────────────────────────────────────────────────────────────────────
CHAPTER — CHAPTER 1 — EARLIEST YEARS
────────────────────────────────────────────────────────────────────────────────

  word_count:    17
  question_count: 2
  anchor_hits:   (none)

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ Got it — Originally Schong With A C. Did I get that name right? What happened next?
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

────────────────────────────────────────────────────────────────────────────────
CHAPTER — CHAPTER 2 — EARLY SCHOOL YEARS
────────────────────────────────────────────────────────────────────────────────

  word_count:    26
  question_count: 2
  anchor_hits:   (none)

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ Got it — You Learned To Stand Up And Sit Down And Kneel At The Right Times. Did I get that name right? What happened next?
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

────────────────────────────────────────────────────────────────────────────────
CHAPTER — CHAPTER 3 — LATER YEARS
────────────────────────────────────────────────────────────────────────────────

  word_count:    25
  question_count: 1
  anchor_hits:   chris

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ Christmas Eve is coming around again in a few months. You kept coming back to Christmas Eve — what was that actually like for you?
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
  oral_history_style_lines: 84
  reflection_not_grounded_or_layer_ineligible_lines: 0
  extract_accepted_lines: 55
  meal_tickets_substring_present: True
  spantag_flag_on_lines_observed: False

────────────────────────────────────────────────────────────────────────────────
AGGREGATE
────────────────────────────────────────────────────────────────────────────────
  Score rows passed: 28 / 32  (87.5%)

  Acceptance criteria:
    GREEN:  ≥ 75% rows pass AND zero hard FAILs on forbidden-empathy / era-label-menu
    AMBER:  60-75% rows pass OR partial failures on word budget / one-question-max
    RED:    < 60% rows pass OR hard FAILs on forbidden-empathy or era-label-menu

Report file: /mnt/c/Users/chris/hornelore/docs/reports/jake_long_narration_jake_long_narration_a7a09ab02c98.txt
================================================================================

✓ Report written: /mnt/c/Users/chris/hornelore/docs/reports/jake_long_narration_jake_long_narration_a7a09ab02c98.txt
```

### live:shatner_public_figure
- Status: `RUN`
- Command: `python3 scripts/run_shatner_long_narration_harness.py`
- Return code: `0`
- Duration: `39.3s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/shatner_long_narration_30bdd953-9e3.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating William Shatner via POST /api/people/intake
======================================================================
  ✓ William Shatner created — person_id=d5e6f0cb-649e-4106-8100-a1aef5775ad4
  ✓ bio_facts_written: 13


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=30bdd953-9e3

  --- SENDING Earliest Years — Montreal (421 words) ---
Got it — It Was The Air. Did I get that name right? What happened next?
  --- Earliest Years — Montreal DONE in 1.6s ---

  --- SENDING Building Years — Stage to Star Trek (486 words) ---
You graduated from McGill in 1952 and made a choice between your father's clothing business and the Canadian National Repertory Theatre. You chose the theatre, which led to your work in Shakespeare productions, Broadway, and eventually, television. And then, in 1966, Gene Roddenberry offered you the role of Captain James T. Kirk in the science-fiction pilot that would become Star Trek. What do you remember about the early days of working in television and film, before your time on Star Trek?
  --- Building Years — Stage to Star Trek DONE in 23.1s ---

  --- SENDING Later Years — Looking Back from 93 (476 words) ---
Got it — Ottawa. What happened next?
  --- Later Years — Looking Back from 93 DONE in 1.3s ---

  --- SENDING Bonus probe (11 words) ---
It was a pleasure listening to your story. Would you like to continue where we left off or is there something else you'd like to talk about? (We can come back to the rest in a moment.)
  --- Bonus probe DONE in 8.6s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/shatner_long_narration_30bdd953-9e3.txt
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
- Duration: `52.8s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/richard_late_coming_out_d9d9bf39-94a.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Richard Bellamy (late coming-out) via POST /api/people/intake
======================================================================
  ✓ Richard Bellamy (late coming-out) created — person_id=2bbe794c-96ac-4267-ba5d-0e182fe16d67
  ✓ bio_facts_written: 15


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=d9d9bf39-94a

  --- SENDING Earliest Years — Oakland, Pittsburgh (484 words) ---
Here is a response that follows the rules and guidelines:

"You mentioned Magee Hospital where you were born, your parents, and the Catholic Church, where you attended Mass and served as an altar boy. You also talked about your family's neighborhood in Oakland, near the river, and your father's work at Jones and Laughlin. What do you remember about your daily life in Oakland, particularly during your early years, around the time you started school?"

This response reflects the narrator's mentions of Magee Hospital, the Catholic Church, and Oakland, and asks a follow-up question that invites the narrator to share more about their daily life during this period.
  --- Earliest Years — Oakland, Pittsburgh DONE in 21.4s ---

  --- SENDING Building Years — Marriage + the door (551 words) ---
Got it — It Out Loud In The Empty Kitchen. Did I get that name right? What happened next?
  --- Building Years — Marriage + the door DONE in 1.4s ---

  --- SENDING Later Years — Tomás and the life after (525 words) ---
You went from Mexico City to Strip District, then Pittsburgh, Patrick, Maureen, Kathleen, Catholic, and Thanksgiving. What do you remember about your relationship with your mother, particularly towards the end of her life, and how did you navigate the changes in your life after coming out?
  --- Later Years — Tomás and the life after DONE in 17.1s ---

  --- SENDING Bonus probe (11 words) ---
Is there something specific you'd like to reflect on or explore further?
  --- Bonus probe DONE in 8.2s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/richard_late_coming_out_d9d9bf39-94a.txt
```

### live:pat_betty_secondary_character
- Status: `RUN`
- Command: `python3 scripts/run_pat_teacher_betty_harness.py`
- Return code: `0`
- Duration: `81.7s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/pat_teacher_betty_ae482602-601.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Patricia 'Pat' Frye (teacher + Betty) via POST /api/people/intake
======================================================================
  ✓ Patricia 'Pat' Frye (teacher + Betty) created — person_id=2b9968e8-0728-469a-9327-f67b16e409be
  ✓ bio_facts_written: 15


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=ae482602-601

  --- SENDING Earliest Years — Princeton Avenue + meeting Betty (461 words) ---
Princeton Avenue. What a delightful start to our conversation! You mentioned several key figures in your life, including your parents, brother, sister, and friends. Your fondness for rules and routines shines through, especially in your description of elementary school and your affection for Miss McCullough, who inspired you to become a teacher. It's lovely to hear how your relationships with others have played a significant role in shaping your experiences.

Let's touch on the era of your Earliest Years. You've already mentioned that you were born in Akron, Ohio, and that your father Harold worked at Goodyear. What comes to mind when you picture your earliest home on Princeton Avenue?
  --- Earliest Years — Princeton Avenue + meeting Betty DONE in 21.5s ---

  --- SENDING Building Years — Kent State, Jim, the classroom (452 words) ---
Kent State. How Betty carried that wound in silence for thirty years.

As we explore the Building Years, I'd like to invite you to reflect on your life during this period. You've mentioned your time at Kent State, your marriage to Jim, and the birth of your children. What do you remember about where you were living and what daily life felt like during the 1970s, as you were establishing your family and career as a teacher? (We can come back to the rest in a moment.)
  --- Building Years — Kent State, Jim, the classroom DONE in 25.2s ---

  --- SENDING Later Years — Loss + tutoring + the small thing (472 words) ---
You went from Wednesday to Betty, then Madeleine, Engle, Wrinkle, Time, Tuesday, and October. What do you remember about your daily routine and sense of purpose during this time?
  --- Later Years — Loss + tutoring + the small thing DONE in 16.9s ---

  --- SENDING Bonus probe (11 words) ---
Where would you like to continue next, or perhaps revisit a particular theme that resonates with you?"
  --- Bonus probe DONE in 13.3s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/pat_teacher_betty_ae482602-601.txt
```

### live:mable_african_american_georgia
- Status: `RUN`
- Command: `python3 scripts/run_regional_african_american_georgia_harness.py`
- Return code: `0`
- Duration: `82.5s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/regional_african_american_georgia_c2138a9a-b8d.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Mable Hudson (African American Georgia) via POST /api/people/intake
======================================================================
  ✓ Mable Hudson (African American Georgia) created — person_id=29a7808f-7e28-4216-b5f9-daf6dd04a7f3
  ✓ bio_facts_written: 15


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=c2138a9a-b8d

  --- SENDING Earliest Years — Cotton land + Mount Olive AME (531 words) ---
Mount Olive AME. What a rich and evocative narrative! I'm so grateful to be listening to your story. Let me capture a few key points from your early years.

You were born in Albany, Georgia, in 1942?
  --- Earliest Years — Cotton land + Mount Olive AME DONE in 38.0s ---

  --- SENDING Building Years — Movement, Greyhound, Detroit (488 words) ---
Can you tell me about your account of the Albany Movement and its impact on you and your community is powerful. What do you remember about the mass meetings at Shiloh Baptist or Mount Zion, where you would often attend and participate in the singing and marching?
  --- Building Years — Movement, Greyhound, Detroit DONE in 10.1s ---

  --- SENDING Later Years — Coming home to Albany (448 words) ---
You went from Charlene to Atlanta, then Bernard, Detroit, Plymouth Road, Albany, Earnest, and Lillian. What do you remember about coming back to Albany and settling into your childhood home again?
  --- Later Years — Coming home to Albany DONE in 17.5s ---

  --- SENDING Bonus probe (11 words) ---
It was a pleasure listening to your story. Thank you for sharing your experiences and reflections with me. If you'd like to continue another time.
  --- Bonus probe DONE in 12.4s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/regional_african_american_georgia_c2138a9a-b8d.txt
```

### live:frank_japanese_american_california
- Status: `RUN`
- Command: `python3 scripts/run_regional_asian_american_california_harness.py`
- Return code: `0`
- Duration: `36.8s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/regional_asian_american_california_6f95ef03-06c.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Frank Yamada (Japanese-American California) via POST /api/people/intake
======================================================================
  ✓ Frank Yamada (Japanese-American California) created — person_id=a594aeff-3432-4943-b0ec-20247d37c88b
  ✓ bio_facts_written: 15


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=6f95ef03-06c

  --- SENDING Earliest Years — Strawberry rows and Tule Lake (456 words) ---
Got it — Because The Adults Stopped Moving. Did I get that name right? What happened next?
  --- Earliest Years — Strawberry rows and Tule Lake DONE in 1.2s ---

  --- SENDING Building Years — Starting over and the extension office (422 words) ---
You said Tule Lake: He died in 1973 having said maybe four sentences about Tule Lake to me in twenty-eight years. You kept coming back to Tule Lake — what was that actually like for you?
  --- Building Years — Starting over and the extension office DONE in 6.5s ---

  --- SENDING Later Years — Redress and the Target shopping center (401 words) ---
It's okay that they're private. Can you tell me more about what it means to you to "drive past" the strawberry fields and the Target shopping center, and how that experience relates to your memories and sense of place? (We can come back to the rest in a moment.)
  --- Later Years — Redress and the Target shopping center DONE in 18.6s ---

  --- SENDING Bonus probe (11 words) ---
We've touched on several parts of your story. Where would you like to continue today?
  --- Bonus probe DONE in 5.8s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/regional_asian_american_california_6f95ef03-06c.txt
```

### live:joe_native_new_mexico
- Status: `RUN`
- Command: `python3 scripts/run_regional_native_american_new_mexico_harness.py`
- Return code: `0`
- Duration: `67.5s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/regional_native_american_new_mexico_25f8e1c8-35c.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Joe Quintana (Cochiti Pueblo) via POST /api/people/intake
======================================================================
  ✓ Joe Quintana (Cochiti Pueblo) created — person_id=17158844-63a3-4f24-9346-8278cad8c4e6
  ✓ bio_facts_written: 22


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=25f8e1c8-35c

  --- SENDING Earliest Years — The village and the boarding school (490 words) ---
You went from Cochiti Pueblo to August, then Frank, Elena, Andrew, Mary, Catholic, and Mass. What happened next?
  --- Earliest Years — The village and the boarding school DONE in 29.3s ---

  --- SENDING Building Years — Vietnam, BIA, NAGPRA (444 words) ---
You went from Fort Bliss to Long Binh, Vietnam, serving as a combat engineer for two years. Then you came home in 1970. What do you remember about the transition from military life back to civilian life when you returned to the Pueblo in 1970?
  --- Building Years — Vietnam, BIA, NAGPRA DONE in 11.6s ---

  --- SENDING Later Years — What stays at the Pueblo (438 words) ---
What do you remember about your own experiences with the St. Catherine boarding school, and how did it shape your understanding of what gets preserved and shared? (We can come back to the rest in a moment.)
  --- Later Years — What stays at the Pueblo DONE in 14.7s ---

  --- SENDING Bonus probe (11 words) ---
"We've touched on several parts of your story. Where would you like to continue today?"
  --- Bonus probe DONE in 6.1s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/regional_native_american_new_mexico_25f8e1c8-35c.txt
```

### live:stefi_crypto_jewish_new_mexico
- Status: `RUN`
- Command: `python3 scripts/run_regional_crypto_jewish_new_mexico_harness.py`
- Return code: `0`
- Duration: `51.7s`
- New reports:
  - `/mnt/c/Users/chris/hornelore/docs/reports/regional_crypto_jewish_new_mexico_45304e10-c03.txt`
stdout tail:
```text
======================================================================
STEP 1 — Creating Stefi Sandoval (Crypto-Jewish New Mexico) via POST /api/people/intake
======================================================================
  ✓ Stefi Sandoval (Crypto-Jewish New Mexico) created — person_id=e719e69e-b1c0-4538-b009-b637f0dbf403
  ✓ bio_facts_written: 15


Opening chat WS: ws://localhost:8000/api/chat/ws  conv_id=45304e10-c03

  --- SENDING Earliest Years — Candles in the cellar (495 words) ---
Here's a reflection and a question, grounded in the narrator's words:

"It sounds like you grew up in a very specific cultural and spiritual tradition, marked by certain customs and practices like lighting candles, saying prayers, and observing dietary restrictions. You mentioned that your mother's family has a long history in New Mexico, and that there were certain ways of doing things that had been passed down through generations.

You also talked about the importance of maintaining certain boundaries and traditions, like not eating pork or having ham at Easter. And you described how you learned about these practices by osmosis, without necessarily understanding the reasoning behind them.

What do you remember about the sense of community and belonging you felt as part of this tradition?"Tú had an older brother Antonio, made my First Communion, asked her why she lit candles down there, y asked my mother. ¿Qué pasó después?
  --- Earliest Years — Candles in the cellar DONE in 24.1s ---

  --- SENDING Building Years — The vocabulary arrives in 1985 (510 words) ---
Entendido — Well. ¿Qué pasó después?
  --- Building Years — The vocabulary arrives in 1985 DONE in 1.5s ---

  --- SENDING Later Years — Breaking the rule on purpose (536 words) ---
Capté Santa Fe, David, y Albuquerque. ¿Qué pasó después?
  --- Later Years — Breaking the rule on purpose DONE in 15.5s ---

  --- SENDING Bonus probe (11 words) ---
We've touched on several parts of your story. Where would you like to continue today?
  --- Bonus probe DONE in 6.0s ---

Report written: /mnt/c/Users/chris/hornelore/docs/reports/regional_crypto_jewish_new_mexico_45304e10-c03.txt
```

## Phase 5 — Test Lab

- runner_exists: `False`
- runner_path: `/mnt/c/Users/chris/hornelore/scripts/run_test_lab.sh`
- mode: `dry`
- status: `SKIP: scripts/run_test_lab.sh missing`

## Phase 6 — John Baldy preflight

- WARNING: fake John from bad harness exists in people list: 5de235a9-a2f6-4d2a-b3c1-0731db5d0b20

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

### ✅ Earliest Years — `PASS`
- era_id: `earliest_years`
- duration: `11.8s`

John turn:
```text
I was born on December 31, 1960, in West St. Paul, Minnesota. My mother is still alive at 99 and lives in St. Paul, so those earliest roots are still connected to my life now.
```

Lori response:
```text
West St.
```

Log findings:
- FK constraint warning seen

### ✅ Early School Years — `PASS`
- era_id: `early_school_years`
- duration: `9.7s`

John turn:
```text
I went to school in St. Paul. I also attended military school, but that was school, not military service. I did not serve in the military.
```

Lori response:
```text
St.
```

Log findings:
- FK constraint warning seen

### ⚠️ Adolescence — `WARN`
- era_id: `adolescence`
- duration: `9.4s`

John turn:
```text
When I was a teenager, my father died. He was changing a tire and was hit by a car. I also traveled in Europe as a teenager.
```

Lori response:
```text
Let me say that in English. What would you like to tell me next?
```

Findings:
- Spanish/English correction artifact

Log findings:
- FK constraint warning seen

### ✅ Coming of Age — `PASS`
- era_id: `coming_of_age`
- duration: `8.2s`

John turn:
```text
I went to college in New York. I earned one bachelor's degree and three master's degrees. I do not want to fill in the school names or majors right now.
```

Lori response:
```text
New York and those master's degrees, John - that's a remarkable achievement. What does a graduate program stand out to you, looking back on those experiences?
```

Log findings:
- FK constraint warning seen

### ✅ Building Years — `PASS`
- era_id: `building_years`
- duration: `11.0s`

John turn:
```text
My work life included selling natural tobacco cigarettes and being a beer maker or brewer. Later I taught at NMHU, New Mexico Highlands University. I became a school psychologist in 2010.
```

Lori response:
```text
What was going on in your mind or heart as you made that decision to become a school psychologist?
```

Log findings:
- FK constraint warning seen

### ✅ Later Years — `PASS`
- era_id: `later_years`
- duration: `8.3s`

John turn:
```text
I have been married twice. I am divorced again now. I have two children. I continued my professional identity as a school psychologist in New Mexico.
```

Lori response:
```text
You were starting your career as a school psychologist in New Mexico?
```

Log findings:
- FK constraint warning seen

### ❌ Today — `FAIL`
- era_id: `today`
- duration: `8.0s`

John turn:
```text
Today I live alone in my own house in Las Vegas, New Mexico. I currently work as a school psychologist in Pecos Schools. My mother is still alive at 99 and lives in St. Paul.
```

Lori response:
```text
Let me say that in English. What would you like to tell me next?
```

Findings:
- Spanish/English correction artifact
- VRAM-GUARD truncating input seen

Log findings:
- VRAM-GUARD truncating input seen
- FK constraint warning seen

## Phase 8 — Harvested harness report snippets

### `/mnt/c/Users/chris/hornelore/docs/reports/jake_long_narration_jake_long_narration_a7a09ab02c98.txt`
```text
================================================================================
JAKE MAX MILLER LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    jake_long_narration_a7a09ab02c98
person_id:  9aeea5f6-4a1a-4bf1-901c-4b986ea2a002
run_time:   2026-06-17 13:25:55

Stack signature: oral_history default + Phase 1 validators +
                 reflection-grounding + thread bank +
                 LORI-CONFIRM scaffolding (post-WO sequence)

────────────────────────────────────────────────────────────────────────────────
STEP 1 — Intake orchestrator result
────────────────────────────────────────────────────────────────────────────────
  person_id: 9aeea5f6-4a1a-4bf1-901c-4b986ea2a002
  intake_endpoint: http://localhost:8000/api/people/intake
  intake_payload_sections: 7
  intake_status: 200

────────────────────────────────────────────────────────────────────────────────
CHAPTER — CHAPTER 1 — EARLIEST YEARS
────────────────────────────────────────────────────────────────────────────────

  word_count:    17
  question_count: 2
  anchor_hits:   (none)

  Lori response (verbatim):
  ┌──────────────────────────────────
```

### `/mnt/c/Users/chris/hornelore/docs/reports/pat_teacher_betty_ae482602-601.txt`
```text
================================================================================
PATRICIA 'PAT' FRYE (TEACHER + BETTY) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    ae482602-601
person_id:  2b9968e8-0728-469a-9327-f67b16e409be
run_time:   2026-06-17 13:29:10

────────────────────────────────────────────────────────────────────────────────
CHAPTER — Earliest Years — Princeton Avenue + meeting Betty
────────────────────────────────────────────────────────────────────────────────
  word_count:     110
  question_count: 1
  anchor_hits:    akron, harold, goodyear, princeton avenue, miss mccullough

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ Princeton Avenue. What a delightful start to our conversation! You mentioned several key figures in your life, including your parents, brother, sister, and friends. Your fondness for rules and routines shines through, especially in your description of elementary school and your affection for Miss McCullough, who inspired you to become a teacher. It's lovely to hear how your relationships with others have
```

### `/mnt/c/Users/chris/hornelore/docs/reports/regional_african_american_georgia_c2138a9a-b8d.txt`
```text
================================================================================
MABLE HUDSON (AFRICAN AMERICAN GEORGIA) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    c2138a9a-b8d
person_id:  29a7808f-7e28-4216-b5f9-daf6dd04a7f3
run_time:   2026-06-17 13:30:37

────────────────────────────────────────────────────────────────────────────────
CHAPTER — Earliest Years — Cotton land + Mount Olive AME
────────────────────────────────────────────────────────────────────────────────
  word_count:     37
  question_count: 1
  anchor_hits:    albany, 1942, mount olive, ame

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ Mount Olive AME. What a rich and evocative narrative! I'm so grateful to be listening to your story. Let me capture a few key points from your early years.
  │ 
  │ You were born in Albany, Georgia, in 1942?
  └────────────────────────────────────────────────────────────────────────────

  Scoring matrix:
    ✓ reflection_grounded: PASS
    ✓ one_question_max: PASS
    ✓ no_questionnaire_interrogation: PASS
    ✓ no_forbidden_empathy
```

### `/mnt/c/Users/chris/hornelore/docs/reports/regional_asian_american_california_6f95ef03-06c.txt`
```text
================================================================================
FRANK YAMADA (JAPANESE-AMERICAN CALIFORNIA) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    6f95ef03-06c
person_id:  a594aeff-3432-4943-b0ec-20247d37c88b
run_time:   2026-06-17 13:31:18

────────────────────────────────────────────────────────────────────────────────
CHAPTER — Earliest Years — Strawberry rows and Tule Lake
────────────────────────────────────────────────────────────────────────────────
  word_count:     17
  question_count: 2
  anchor_hits:    (none)

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ Got it — Because The Adults Stopped Moving. Did I get that name right? What happened next?
  └────────────────────────────────────────────────────────────────────────────

  Scoring matrix:
    ✗ reflection_grounded: FAIL
    ⚠ one_question_max: PARTIAL
    ✓ no_questionnaire_interrogation: PASS
    ✓ no_forbidden_empathy_openers: PASS
    ✓ no_era_label_menu: PASS
    ✓ no_same_anchor_loop: PASS
    ✓ word_budget_honored: PASS
    ✓ translation_refusal
```

### `/mnt/c/Users/chris/hornelore/docs/reports/regional_crypto_jewish_new_mexico_45304e10-c03.txt`
```text
================================================================================
STEFI SANDOVAL (CRYPTO-JEWISH NEW MEXICO) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    45304e10-c03
person_id:  e719e69e-b1c0-4538-b009-b637f0dbf403
run_time:   2026-06-17 13:33:26

────────────────────────────────────────────────────────────────────────────────
CHAPTER — Earliest Years — Candles in the cellar
────────────────────────────────────────────────────────────────────────────────
  word_count:     25
  question_count: 1
  anchor_hits:    antonio, first communion

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ Tú had an older brother Antonio, made my First Communion, asked her why she lit candles down there, y asked my mother. ¿Qué pasó después?
  └────────────────────────────────────────────────────────────────────────────

  Scoring matrix:
    ✓ reflection_grounded: PASS
    ✓ one_question_max: PASS
    ✓ no_questionnaire_interrogation: PASS
    ✓ no_forbidden_empathy_openers: PASS
    ✓ no_era_label_menu: PASS
    ✓ no_same_anchor_loop: PASS
    ✓
```

### `/mnt/c/Users/chris/hornelore/docs/reports/regional_native_american_new_mexico_25f8e1c8-35c.txt`
```text
================================================================================
JOE QUINTANA (COCHITI PUEBLO) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    25f8e1c8-35c
person_id:  17158844-63a3-4f24-9346-8278cad8c4e6
run_time:   2026-06-17 13:32:30

────────────────────────────────────────────────────────────────────────────────
CHAPTER — Earliest Years — The village and the boarding school
────────────────────────────────────────────────────────────────────────────────
  word_count:     18
  question_count: 1
  anchor_hits:    cochiti pueblo, frank, elena, andrew, mary

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ You went from Cochiti Pueblo to August, then Frank, Elena, Andrew, Mary, Catholic, and Mass. What happened next?
  └────────────────────────────────────────────────────────────────────────────

  Scoring matrix:
    ✓ reflection_grounded: PASS
    ✓ one_question_max: PASS
    ✓ no_questionnaire_interrogation: PASS
    ✓ no_forbidden_empathy_openers: PASS
    ✓ no_era_label_menu: PASS
    ✓ no_same_anchor_loop: PASS
    ✓ word
```

### `/mnt/c/Users/chris/hornelore/docs/reports/richard_late_coming_out_d9d9bf39-94a.txt`
```text
================================================================================
RICHARD BELLAMY (LATE COMING-OUT) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    d9d9bf39-94a
person_id:  2bbe794c-96ac-4267-ba5d-0e182fe16d67
run_time:   2026-06-17 13:27:43

────────────────────────────────────────────────────────────────────────────────
CHAPTER — Earliest Years — Oakland, Pittsburgh
────────────────────────────────────────────────────────────────────────────────
  word_count:     108
  question_count: 1
  anchor_hits:    oakland, jones and laughlin, magee

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ Here is a response that follows the rules and guidelines:
  │ 
  │ "You mentioned Magee Hospital where you were born, your parents, and the Catholic Church, where you attended Mass and served as an altar boy. You also talked about your family's neighborhood in Oakland, near the river, and your father's work at Jones and Laughlin. What do you remember about your daily life in Oakland, particularly during your early years, around the time you sta
```

### `/mnt/c/Users/chris/hornelore/docs/reports/seven_era_walk_2f9448fc-492.txt`
```text
================================================================================
WALTER O'DONNELL (7-ERA WALK) — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    2f9448fc-492
person_id:  3faf4b5c-39ce-4c9c-b00e-7298c7ba6d7d
run_time:   2026-06-17 13:25:17

────────────────────────────────────────────────────────────────────────────────
CHAPTER — Era 1 — Earliest Years (G Street, Southie 1948-53)
────────────────────────────────────────────────────────────────────────────────
  word_count:     14
  question_count: 1
  anchor_hits:    (none)

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ Let me say that in English. What would you like to tell me next?
  └────────────────────────────────────────────────────────────────────────────

  Scoring matrix:
    ✗ reflection_grounded: FAIL
    ✓ one_question_max: PASS
    ✓ no_questionnaire_interrogation: PASS
    ✓ no_forbidden_empathy_openers: PASS
    ✓ no_era_label_menu: PASS
    ✓ no_same_anchor_loop: PASS
    ✓ word_budget_honored: PASS
    ✗ translation_refusal_absent: FAIL

────────────────────────
```

### `/mnt/c/Users/chris/hornelore/docs/reports/shatner_long_narration_30bdd953-9e3.txt`
```text
================================================================================
WILLIAM SHATNER — LONG-NARRATION HARNESS REPORT
================================================================================
conv_id:    30bdd953-9e3
person_id:  d5e6f0cb-649e-4106-8100-a1aef5775ad4
run_time:   2026-06-17 13:26:40

────────────────────────────────────────────────────────────────────────────────
CHAPTER — Earliest Years — Montreal
────────────────────────────────────────────────────────────────────────────────
  word_count:     16
  question_count: 2
  anchor_hits:    (none)

  Lori response (verbatim):
  ┌────────────────────────────────────────────────────────────────────────────
  │ Got it — It Was The Air. Did I get that name right? What happened next?
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

─────────────────────────────────────────────────────
```
