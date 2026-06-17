# Boris Test Matrix

| Test file | Bug(s) covered | Type |
|---|---|---|
| test_phase1_safety_false_positive.py | child_abuse false-positive | direct unit |
| test_phase2_scorer_quality_rows.py | scorer too lenient | direct scorer unit |
| test_phase3_facts_add_truth_v2.py | facts/add 422 | route contract |
| test_phase4_chat_ws_fk_lifecycle.py | chat_ws FK | static + source contract |
| test_phase5_meta_response_guard.py | meta-response leak | direct guard + scorer |
| test_phase6_phrase_as_name_confirmation.py | phrase-as-name confirm | direct detector + scorer |
| test_phase7_anchor_cascade_dump.py | anchor-cascade dump | direct fallback + scorer |
| test_phase8_seed_aware_question_filter.py | asks-what-seeded | direct filter + scorer |
| test_phase9_spanish_lang_contract.py | Spanish misfire/code-mix | direct lang + scorer |
| test_phase11_intake_empty_year_married.py | Alex intake 422 | direct Pydantic model |
| test_phase12_evidence_path_normalization.py | Windows→WSL paths | direct harness helper |
| test_full_family_report_regression_patterns.py | second-run failure patterns | report/scorer regression |
