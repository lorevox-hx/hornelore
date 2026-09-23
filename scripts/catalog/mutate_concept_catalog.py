#!/usr/bin/env python3
"""Mutation gate for the concept catalog — proves its tests and refusals can fail.

Each mutation breaks one rule in the loader, the compiler or the semantic
source, in a MINIMAL COPY of the tree (only what the suite reads — a full copy
filled the sandbox disk on the first attempt, 2026-09-22). A source mutation is
followed by a RECOMPILE, because that is what a developer would do: the catalog
must then either refuse to compile or fail a semantic test. A mutation that
does neither names an inert check.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPYCACHEPREFIX=/tmp/pyc python3 scripts/catalog/mutate_concept_catalog.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NEED_DIRS = ["server/code/api", "scripts/design", "scripts/catalog"]
NEED_FILES = ["docs/wo/WO-HORNELORE-INTEGRATED-LIFE-RECORD-01_DECISIONS.md",
              "docs/specs/CONCEPT-DECISION-APPENDIX.md",
              "ui/js/bio-builder-questionnaire.js", "ui/js/projection-map.js",
              "tests/test_concept_catalog.py", "tests/test_concept_migration_plan.py"]
LOADER = "server/code/api/services/concept_catalog.py"
COMPILER = "scripts/catalog/compile_concept_catalog.py"
SOURCE = "server/code/api/services/concept_catalog_source.py"
PLANNER = "server/code/api/services/concept_migration_plan.py"
EXTRACTOR = "server/code/api/routers/extract.py"
CATALOG_TESTS = "tests.test_concept_catalog"
PLAN_TESTS = "tests.test_concept_migration_plan"

# (file, description, find, replace, what must notice (regex), recompile?)
MUTATIONS = [
    (LOADER, "loader accepts eligible-with-no-scope",
     'elif ex.get("eligible") and not ex["scope"]:', 'elif False:', "no_scope", False),
    (LOADER, "loader lets a property default",
     'if prop not in c:\n                p.append', 'if False:\n                p.append',
     "missing_property", False),
    (LOADER, "loader allows asking for a derived concept",
     'if c.get("questionnaire") == "derived_readonly" and lori.get("askable") != "never":',
     'if False:', "derived_concept", False),
    (LOADER, "extraction scope ignores the section",
     '\\\n                    and r["section"] == section:', ':', "extraction_scope_offers_only", False),
    (COMPILER, "compiler drops the build gate",
     'if decisions.get(d, {}).get("state") != "approved":', 'if False:', "unapproved_decision", False),
    (COMPILER, "compiler stops reporting unbound paths",
     'problems.append(f"UNBOUND path `{p}` (field `{field}`)")', 'pass', "unbound_field", False),
    (COMPILER, "compiler forgets its typo guard",
     'problems.append(f"source names `{p}`, which no vocabulary contains")', 'pass',
     "concept_binding_of_a_nonexistent_path", False),
    (COMPILER, "compiler forgets the RETIRED typo guard",
     'problems.append(f"RETIRED `{p}` is in no vocabulary and no decision group — a typo?")',
     'pass', "retirement_of_a_nonexistent_path", False),
    (COMPILER, "compiler lets the extractor keep offering a retired path",
     'if "extraction" in vocab_of.get(p, ()):', 'if False:',
     "still_offered_to_the_extractor", False),
    (SOURCE, "age at death becomes a death date",
     '"ageAtDeath": "person.death.reported_age",', '"ageAtDeath": "person.death.date",',
     "COMPILE REFUSED|age_at_death", True),
    (SOURCE, "a D11 notes path is also retired outright",
     '"siblings.notes": "D1f",', '"siblings.notes": "D1f", "parents.notes": "D1d",',
     "COMPILE REFUSED", True),
    (SOURCE, "a D11 notes path returns to extraction",
     '"parents.notes": "D11", ', '', "COMPILE REFUSED|D11_notes|no_drift", True),
    (SOURCE, "great-grandparent service event becomes a story",
     '"greatGrandparents.militaryEvent": "event.service.occurrence",',
     '"greatGrandparents.militaryEvent": "story.service",',
     "COMPILE REFUSED|great_grandparent_service", True),
    (LOADER, "extraction scope offers extraction-retired paths",
     '\n                    or r["extraction_retired_by"]):', '):', "D11_notes|even_if_a_member", False),
    (LOADER, "loader stops requiring extraction_retired_by",
     'if not isinstance(xr, list):', 'if False:', "extraction_retired_by_must", False),
    (LOADER, "loader lets a dead path be retired from extraction",
     'elif xr and r.get("disposition") != "bind":', 'elif False:', "dead_path", False),
    # Was "compiler derives eligibility from retired-from-extraction paths"
    # (drop `and not r["extraction_retired_by"]`). A3 removed the D11 paths
    # from EXTRACTABLE_FIELDS, so extraction_member is already False for them
    # and that mutation became EQUIVALENT -- it survived because nothing it
    # could change was left, not because a check was inert. The live rule is
    # now producer agreement, and this mutation proves it can refuse.
    (EXTRACTOR, "extractor offers a D11-retired path again",
     '    "pets.birthDate":',
     '    "pets.notes": {"label": "x", "writeMode": "suggest_only", "repeatable": "pets"},\n    "pets.birthDate":',
     "COMPILE REFUSED", True),
    (EXTRACTOR, "extractor offers a D1d-retired path again",
     '    "pets.birthDate":',
     '    "health.notes": {"label": "x", "writeMode": "suggest_only"},\n    "pets.birthDate":',
     "COMPILE REFUSED", True),
    (COMPILER, "compiler drops the RETIRED/EXTRACTION_RETIRED conflict guard",
     'if p in src.RETIRED:\n            problems.append(f"`{p}` is in both',
     'if False:\n            problems.append(f"`{p}` is in both', "retired_outright_conflict", False),
    (COMPILER, "compiler lets a non-form path be extraction-retired",
     'elif "questionnaire" not in vocab_of.get(p, ()):', 'elif False:', "non_form_path", False),
    (SOURCE, "clinical medication un-retired",
     '"health.majorCondition": "D3", "health.currentMedications": "D3",',
     '"health.majorCondition": "D3",', "COMPILE REFUSED|no_clinical", True),
    (SOURCE, "life status loses its decided scope",
     '"person.life_status": ("D1f", ("parents", "spouse")),',
     '"person.life_status": ("D1f", ("parents",)),', "life_status", True),
    # ── Batch A5: the migration plan must never lose a value ────────────
    (PLANNER, "plan: a retired value is dropped instead of kept",
     'return _row(store, path, value, "retired_value_kept",',
     'return _row(store, path, None, "retired_value_kept",',
     "retired_path_keeps|no_nonempty_value", False),
    (PLANNER, "plan: an unmapped key is silently skipped",
     'return _row(store, path, value, "unmapped_value_kept",',
     'return _row(store, path, None, "empty",', "unknown_key|no_nonempty_value", False),
    (PLANNER, "plan: a blank deceased field counts as an answer",
     'return v is None or v == "" or v == [] or v == {}',
     'return v is None or v == [] or v == {}', "life_status", False),
    (PLANNER, "plan: entry ids are not carried",
     'eid = entry.get("_entryId")', 'eid = None', "entry_id", False),
    (PLANNER, "plan: derived fields migrated as ordinary facts",
     'if b["disposition"] == "derived":', 'if False:', "zodiac", False),
    (PLANNER, "plan: leaf count ignores list entries",
     'return sum(_count_leaves(v) if isinstance(v, dict) else 1 for v in doc)',
     'return len(doc)', "exactly_once", False),
]


def _minimal_tree():
    d = tempfile.mkdtemp(dir="/tmp")
    for nd in NEED_DIRS:
        shutil.copytree(os.path.join(ROOT, nd), os.path.join(d, nd),
                        ignore=shutil.ignore_patterns("__pycache__"))
    for nf in NEED_FILES:
        os.makedirs(os.path.dirname(os.path.join(d, nf)), exist_ok=True)
        shutil.copy(os.path.join(ROOT, nf), os.path.join(d, nf))
    os.makedirs(os.path.join(d, ".git"), exist_ok=True)
    with open(os.path.join(d, ".git", "HEAD"), "w") as fh:
        fh.write("0" * 40)
    return d


def _run(cwd, args):
    env = dict(os.environ, PYTHONPATH="server/code", PYTHONPYCACHEPREFIX="/tmp/pycm")
    r = subprocess.run([sys.executable] + args, cwd=cwd, capture_output=True, text=True, env=env)
    return r.returncode, r.stdout + r.stderr


def main():
    ok = True
    d = _minimal_tree()
    try:
        code, _ = _run(d, ["-m", "unittest", CATALOG_TESTS, PLAN_TESTS])
    finally:
        shutil.rmtree(d, ignore_errors=True)
    if code != 0:
        print("  BASELINE IS RED — fix the suite before mutating it")
        return 1

    for f, title, old, new, expect, recompile in MUTATIONS:
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
            txt = ""
            if recompile:
                _, txt = _run(d, [COMPILER])
            if "COMPILE REFUSED" not in txt:
                _, out = _run(d, ["-m", "unittest", CATALOG_TESTS, PLAN_TESTS])
                txt += out
        finally:
            shutil.rmtree(d, ignore_errors=True)
        failed = [ln for ln in txt.splitlines() if ln.startswith(("FAIL:", "ERROR:"))]
        refused = "COMPILE REFUSED" in txt
        hit = (refused and re.search(expect, "COMPILE REFUSED")) or \
            any(re.search(expect, ln) for ln in failed)
        ok &= bool(hit)
        how = "compile refused" if refused else f"{len(failed)} red"
        print(f"  {'ok  ' if hit else 'FAIL'} {title:<48} {'caught' if hit else 'SURVIVED'} ({how})")
    print("\n  every mutation caught" if ok else "\n  A MUTATION SURVIVED — that check is inert")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
