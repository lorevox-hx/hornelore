#!/usr/bin/env python3
"""Mutation gate for A2 + A3 — proves the new vocabulary tests can fail.

Each mutation reverts ONE A2/A3 subchange in a minimal copy of the tree and
runs the focused suites. A mutation that turns nothing red names a subchange
nothing is guarding. Shape follows scripts/catalog/mutate_concept_catalog.py.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPYCACHEPREFIX=/tmp/pyc .venv/bin/python scripts/eval/mutate_a3_vocabulary.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NEED_DIRS = ["server/code/api", "server/code/db"]
NEED_FILES = ["ui/js/bio-builder-questionnaire.js", "tests/fastapi_stub.py", "tests/test_extract_a3_vocabulary.py",
              "tests/test_extract_schema_coverage.py", "tests/test_suggestion_review.py",
              "tests/test_extract_date_uncertainty_guard.py"]
SUITES = ["tests.test_extract_a3_vocabulary", "tests.test_extract_schema_coverage",
          "tests.test_suggestion_review", "tests.test_extract_date_uncertainty_guard"]
EXTRACT = "server/code/api/routers/extract.py"
REVIEW = "server/code/api/services/suggestion_review.py"

# (file, subchange, find, replace, test-name regex that must go red)
MUTATIONS = [
    (REVIEW, "A2 split_destination stops translating decided aliases",
     'field_path = _decided_alias(field_path or "")', 'field_path = field_path or ""',
     "A2DecidedAliases"),
    (EXTRACT, "A2 spouse loses its repeatable group",
     '"Spouse / partner first name", "writeMode": "prefill_if_blank", "repeatable": "spouse"}',
     '"Spouse / partner first name", "writeMode": "prefill_if_blank"}',
     "spouse"),
    (EXTRACT, "D12 family.marriageDate no longer redirected",
     '    "family.marriageDate": "marriage.marriageDate",\n', '',
     "marriage|Marriage"),
    (EXTRACT, "D12 redirected duplicates not folded",
     'return _fold_redirected_duplicates(valid)', 'return valid',
     "Marriage|fold|duplicate"),
    (EXTRACT, "D12 bare marriageDate alias lost",
     '"marriageDate": "marriage.marriageDate", "marriage_date": "marriage.marriageDate",',
     '', "marriage"),
    (EXTRACT, "D13 pets.dateOfBirth no longer redirected",
     '    "pets.dateOfBirth": "pets.birthDate",\n', '', "Pet|pet"),
    (EXTRACT, "D1f child middle name removed",
     '    "family.children.middleName":', '    "family.children.middleNameX":',
     "Middle|middle"),
    (EXTRACT, "D11 a pets.notes bucket returns to extraction",
     '    "family.children.middleName":',
     '    "pets.notes": {"label": "x", "writeMode": "suggest_only", "repeatable": "pets"},\n'
     '    "family.children.middleName":',
     "Retired|retired"),
    (EXTRACT, "D3 health.majorCondition returns to extraction",
     '    "family.children.middleName":',
     '    "health.majorCondition": {"label": "x", "writeMode": "suggest_only"},\n'
     '    "family.children.middleName":',
     "Retired|retired"),
    (EXTRACT, "ancestor-military duplication restored",
     '    # ── 6. Touchstone duplicate: laterYears.significantEvent → ADD cultural.touchstoneMemory ─',
     '    rerouted.extend([{"fieldPath": "military.branch", "value": it["value"], "confidence": 0.8}\n'
     '                     for it in list(rerouted)\n'
     '                     if it.get("fieldPath") == "greatGrandparents.militaryBranch"])\n'
     '    # ── 6. Touchstone duplicate: laterYears.significantEvent → ADD cultural.touchstoneMemory ─',
     "narrator_military|Ancestor"),
    (EXTRACT, "relative catch-all returns",
     '            "parents.schooling":                  "parents.education",',
     '            "parents.schooling":                  "parents.education",\n'
     '            "family.relative":                    "parents.notableLifeEvents",',
     "rejected_not_rewritten|RelativeCatchAlls"),
    # D1c's mutation moved to scripts/eval/mutate_b3_binding.py when B3(e)
    # reintroduced `ageAtDeath` behind the binding guard.
    # ── B2 repair: hedged or conflicting dates go to review ──────────────
    # The seam mutation is caught only by the ProductionBoundary class, which
    # needs real pydantic: run this gate in .venv, or it SURVIVES by skip.
    (EXTRACT, "B2 date-uncertainty guard not called at the seam",
     '    final_items, _date_entries, clarifications = _apply_date_uncertainty_guard(\n'
     '        final_items, answer=answer, clarifications=clarifications)',
     '    _date_entries = []', "ProductionBoundary|case_061_as_the_model"),
    (EXTRACT, "B2 conflicting values not detected",
     'if len({_norm_fact_value(m.value) for m in members}) > 1:',
     'if len({_norm_fact_value(m.value) for m in members}) > 99:',
     "conflict|case_061"),
    (EXTRACT, "B2 conflict ignores the entity (fieldPath only)",
     'slot = (it.fieldPath, getattr(it, "repeatableGroup", None))',
     'slot = (it.fieldPath, None)', "different_entities"),
    (EXTRACT, "B2 narrator hedge ignored",
     'if any(_NARRATOR_HEDGE_RX.search(s)', 'if False and any(_NARRATOR_HEDGE_RX.search(s)',
     "hedged_date|normalized_date|case_061"),
    (EXTRACT, "B2 'around 1964' no longer true as stated",
     '            continue                      # "around 1964" is true as stated',
     '            pass', "own_approximation|around_1964"),
    (EXTRACT, "B2 'I think about' read as doubt",
     'r"\\b(?:i\\s+think(?!\\s+(?:about|of)\\b)|', 'r"\\b(?:i\\s+think|',
     "thinking_about"),
    (EXTRACT, "B2 held date dropped instead of preserved",
     '        entries.append(entry)\n        logger.info(\n            "[extract][date-uncertainty]',
     '        logger.info(\n            "[extract][date-uncertainty]',
     "case_061|hedged_date|conflict"),
]


def _minimal_tree():
    d = tempfile.mkdtemp(prefix="a3mut-")
    ign = shutil.ignore_patterns("__pycache__", "*.pyc")
    for sub in NEED_DIRS:
        shutil.copytree(os.path.join(ROOT, sub), os.path.join(d, sub), ignore=ign)
    for f in NEED_FILES:
        os.makedirs(os.path.dirname(os.path.join(d, f)), exist_ok=True)
        shutil.copy2(os.path.join(ROOT, f), os.path.join(d, f))
    open(os.path.join(d, "tests", "__init__.py"), "a").close()
    return d


def _run(d):
    env = dict(os.environ, PYTHONPATH=os.path.join(d, "server", "code"),
               PYTHONPYCACHEPREFIX=os.path.join(d, ".pyc"))
    p = subprocess.run([sys.executable, "-m", "unittest", *SUITES], cwd=d, env=env,
                       capture_output=True, text=True, timeout=300)
    return p.returncode, p.stdout + p.stderr


def main():
    d = _minimal_tree()
    try:
        code, out = _run(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    if code != 0:
        print(out[-3000:])
        print("  BASELINE IS RED — fix the suite before mutating it")
        return 1
    ran = re.search(r"Ran (\d+) tests", out)
    skipped = re.search(r"skipped=(\d+)", out)
    print(f"  baseline green: {ran.group(1) if ran else '?'} tests, "
          f"{skipped.group(1) if skipped else 0} skipped, interpreter {sys.executable}")

    ok = True
    for f, title, old, new, expect in MUTATIONS:
        with open(os.path.join(ROOT, f), encoding="utf-8") as fh:
            src = fh.read()
        if old not in src:
            print(f"  STALE {title}: anchor not found")
            ok = False
            continue
        d = _minimal_tree()
        try:
            with open(os.path.join(d, f), "w", encoding="utf-8") as fh:
                fh.write(src.replace(old, new, 1))
            _, txt = _run(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)
        failed = [ln for ln in txt.splitlines() if ln.startswith(("FAIL:", "ERROR:"))]
        hit = any(re.search(expect, ln) for ln in failed)
        ok &= hit
        print(f"  {'ok  ' if hit else 'FAIL'} {title:<58} "
              f"{'caught' if hit else 'SURVIVED'} ({len(failed)} red)")
        if not hit and failed:
            for ln in failed[:4]:
                print(f"         red but not the named test: {ln}")
    print("\n  every mutation caught" if ok else "\n  A MUTATION SURVIVED — that subchange is unguarded")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
