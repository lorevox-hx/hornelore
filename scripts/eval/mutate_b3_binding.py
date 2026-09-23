#!/usr/bin/env python3
"""Mutation gate for B3 / A4 — subject binding. Each mutation reverts ONE rule.

Reuses the A3 gate's machinery (minimal tree, runner, report), with B3's own
mutation list and suites. Run in .venv: the seam mutations are caught only by
the ProductionBoundary classes, which skip without real pydantic.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPYCACHEPREFIX=/tmp/pyc .venv/bin/python scripts/eval/mutate_b3_binding.py
"""
import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("a3gate", os.path.join(_HERE, "mutate_a3_vocabulary.py"))
g = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(g)

E = g.EXTRACT
g.NEED_FILES = ["ui/js/bio-builder-questionnaire.js", "tests/fastapi_stub.py",
                "data/qa/question_bank_extraction_cases.json",
                "tests/test_extract_subject_binding.py", "tests/test_extract_eval_trace.py",
                "tests/test_extract_date_uncertainty_guard.py", "tests/test_extract_a3_vocabulary.py"]
g.SUITES = ["tests.test_extract_subject_binding", "tests.test_extract_eval_trace",
            "tests.test_extract_date_uncertainty_guard", "tests.test_extract_a3_vocabulary"]

g.MUTATIONS = [
    # (a) armed evaluation trace
    (E, "B3a trace written when NOT armed",
     "    if not _eval_trace_enabled():\n        return\n    try:\n        import hashlib",
     "    if False:\n        return\n    try:\n        import hashlib", "off_by_default"),
    (E, "B3a trace keeps only a prefix",
     '"raw": raw_output or "",', '"raw": (raw_output or "")[:500],', "full_output"),
    (E, "B3a trace not called in run_field_extraction",
     "    _write_eval_trace(req, answer, raw_output)\n", "", "armed_extraction_is_traced"),
    # (b) evidence span
    (E, "B3b R4-H forgets what was said",
     '                nd["normalized_from"] = raw', "                pass", "keeps_what_was_said|case_070"),
    (E, "B3b grouper ignores the spoken date",
     "                    val_pos = _spoken_date_position(answer_lower, item)",
     "                    val_pos = -1", "case_070|elided"),
    # (c) span subject
    (E, "B3c subject-binding guard not called at the seam",
     "    final_items, _bind_entries, clarifications = _apply_subject_binding_guard(\n"
     "        final_items, answer=answer, clarifications=clarifications)",
     "    _bind_entries = []", "grandfathers_death"),
    (E, "B3c said-once rule removed (first occurrence only)",
     "        if claimed in roles:\n            continue", "        if False:\n            continue",
     "said_once"),
    (E, "B3c possessive 's chain removed",
     "    for m in _POSSESSIVE_KIN_RX.finditer(answer):", "    for m in []:", "moms_dad"),
    (E, "B3c the model's name outranks the narrator's kin phrase",
     '                   for e in kin_ends):\n                continue\n',
     '                   for e in kin_ends):\n                pass\n', "his_own_father|grandfathers_death"),
    (E, "B3c wrong subject dropped instead of preserved",
     '        entries.append(entry)\n        logger.info("[extract][subject-binding]',
     '        logger.info("[extract][subject-binding]', "his_own_father|first_person"),
    # (d) predicate
    (E, "B3d predicate guard not called at the seam",
     "    final_items, _pred_entries, clarifications = _apply_predicate_binding_guard(\n"
     "        final_items, answer=answer, clarifications=clarifications)",
     "    _pred_entries = []", "ross_is_held"),
    (E, "B3d any sentence may lend its wording",
     "    if idx > 0 and _POINTS_BACK_RX.match(answer[a:b]):", "    if idx > 0:",
     "does_not_borrow"),
    (E, "B3d a date located by its year only",
     "    if iso and 1 <= int(iso.group(1)) <= 12:", "    if False:", "any_part_said"),
    (E, "B3d narrator's own fields swept in",
     'if rx is None or _bound_role_of(fp) in (None, "narrator"):',
     "if rx is None or _bound_role_of(fp) is None:", "narrators_own_fields"),
    # (e) age at death
    (E, "B3e first-person age accepted",
     '        if any(g and g[0] == "narrator" for _p, g in governed):', "        if False:",
     "narrators_age|narrator_age_leak|no_narrator_age"),
    (E, "B3e age guard not called at the seam",
     "    final_items, _age_entries, clarifications = _apply_age_at_death_guard(\n"
     "        final_items, answer=answer, clarifications=clarifications)",
     "    _age_entries = []", "no_narrator_age"),
    (E, "B3e death wording not required",
     "            if _predicate_stated(answer, p, _DEATH_WORDING_RX):", "            if True:",
     "no_death_wording"),
    (E, "B3e the other parent's age accepted",
     "            if rel and own_rel and own_rel != rel:", "            if False:",
     "other_parents_age"),
    (E, "B3 final: places located verbatim only",
     "            hits = _place_word_positions(answer, val)", "            hits = []",
     "case_065|great_grandfathers_birthplace"),
    (E, "B3e ages said in words not found",
     "        for text in (val, _number_words(int(val))):", "        for text in (val,):",
     "said_in_words"),
]

if __name__ == "__main__":
    sys.exit(g.main())
