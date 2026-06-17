# John Baldy Full Diagnostic Harness Report

- Run time: `2026-06-17 15:44:20`
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
Ran 24 tests in 0.022s

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
Ran 18 tests in 0.107s

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

## Phase 5 — Test Lab

- runner_exists: `False`
- runner_path: `/mnt/c/Users/chris/hornelore/scripts/run_test_lab.sh`
- mode: `check`
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
- duration: `8.0s`

John turn:
```text
I was born on December 31, 1960, in West St. Paul, Minnesota. My mother is still alive at 99 and lives in St. Paul, so those earliest roots are still connected to my life now.
```

Lori response:
```text
West St. Paul and St. Paul — those roots in Minnesota are still strong. What do you remember about your early years in Minnesota, particularly around the winter holidays when you were a baby?
```

Findings:
- VRAM-GUARD truncating input seen

Log findings:
- VRAM-GUARD truncating input seen

### ❌ Early School Years — `FAIL`
- era_id: `early_school_years`
- duration: `7.8s`

John turn:
```text
I went to school in St. Paul. I also attended military school, but that was school, not military service. I did not serve in the military.
```

Lori response:
```text
St. Paul again, where you went to school. What does "military school" bring to mind for you, aside from the distinction you made about not serving in the military?
```

Findings:
- VRAM-GUARD truncating input seen

Log findings:
- VRAM-GUARD truncating input seen

### ❌ Adolescence — `FAIL`
- era_id: `adolescence`
- duration: `10.6s`

John turn:
```text
When I was a teenager, my father died. He was changing a tire and was hit by a car. I also traveled in Europe as a teenager.
```

Lori response:
```text
Europe. What are some memories that have stayed with you from that trip?
```

Findings:
- VRAM-GUARD truncating input seen

Log findings:
- VRAM-GUARD truncating input seen

### ❌ Coming of Age — `FAIL`
- era_id: `coming_of_age`
- duration: `7.8s`

John turn:
```text
I went to college in New York. I earned one bachelor's degree and three master's degrees. I do not want to fill in the school names or majors right now.
```

Lori response:
```text
New York. What do you remember about your time in New York during that period?
```

Findings:
- VRAM-GUARD truncating input seen

Log findings:
- VRAM-GUARD truncating input seen

### ❌ Building Years — `FAIL`
- era_id: `building_years`
- duration: `7.7s`

John turn:
```text
My work life included selling natural tobacco cigarettes and being a beer maker or brewer. Later I taught at NMHU, New Mexico Highlands University. I became a school psychologist in 2010.
```

Lori response:
```text
NMHU, that's where you taught. What does it mean to you that you transitioned to becoming a school psychologist in 2010, and what motivated you to take on that role? (We can come back to the rest in a moment.)
```

Findings:
- VRAM-GUARD truncating input seen

Log findings:
- VRAM-GUARD truncating input seen

### ❌ Later Years — `FAIL`
- era_id: `later_years`
- duration: `5.4s`

John turn:
```text
I have been married twice. I am divorced again now. I have two children. I continued my professional identity as a school psychologist in New Mexico.
```

Lori response:
```text
We've touched on several parts of your story. Where would you like to continue today?
```

Findings:
- VRAM-GUARD truncating input seen

Log findings:
- VRAM-GUARD truncating input seen

### ❌ Today — `FAIL`
- era_id: `today`
- duration: `8.6s`

John turn:
```text
Today I live alone in my own house in Las Vegas, New Mexico. I currently work as a school psychologist in Pecos Schools. My mother is still alive at 99 and lives in St. Paul.
```

Lori response:
```text
Las Vegas, New Mexico, and your work in Pecos Schools. Your mother's longevity and connection to her hometown in Minnesota are remarkable. What does life in Las Vegas feel like for you now?
```

Findings:
- VRAM-GUARD truncating input seen

Log findings:
- VRAM-GUARD truncating input seen

## Phase 8 — Harvested harness report snippets

- No new harness reports detected.
