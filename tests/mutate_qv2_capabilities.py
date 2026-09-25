#!/usr/bin/env python3
"""Mutation gate for Batch C-4C — the V2 capability declaration, the catalog's
concept-level `questionnaire` property, and the event-date maps.

Each mutation breaks one C-4C promise IN PLACE (tests/mutation_runner.py:
restore after every mutation, verified byte-identical at exit), then runs:

    unittest tests.test_qv2_capabilities tests.test_life_record_writer.EventDatesC4C
    scripts/catalog/compile_concept_catalog.py --check

A mutation is CAUGHT when either fails. `--check` failing is itself the
invariant "the committed catalog equals a fresh compile" (and the compiler's
fail-closed refusals surface there too). A mutation whose anchor is missing is
reported NOT APPLIED — never counted as caught.

Two mutations edit the TEST's translation rules, not product code (marked
[oracle]): they prove the frozen expected set pins the structural translation,
so a translator that silently stops recognising a write cannot pass.

The stack must be DOWN — this edits product source in place.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python tests/mutate_qv2_capabilities.py [label-substring ...]
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tests.mutation_runner import MutationRunner  # noqa: E402

SOURCES = {
    "compiler": REPO / "scripts" / "catalog" / "compile_concept_catalog.py",
    "model": REPO / "ui" / "js" / "questionnaire-v2-model.js",
    "shell": REPO / "ui" / "js" / "questionnaire-v2.js",
    "store": REPO / "server" / "code" / "api" / "services" / "life_record" / "store.py",
    "oracle": REPO / "tests" / "test_qv2_capabilities.py",
}
SUITES = ["tests.test_qv2_capabilities", "tests.test_life_record_writer.EventDatesC4C"]

# (label, source, find, replace)
MUTATIONS = [
    ("1 compiler derives editability from the OLD questionnaire schema again", "compiler",
     "        in_v2 = cid in qv2_editable\n",
     '        in_v2 = any("questionnaire" in r["in"] for r in prows)\n'),
    ("2 compiler bypasses the V2 declaration", "compiler",
     "        in_v2 = cid in qv2_editable\n", "        in_v2 = False\n"),
    ("3 declaration drops person.pronouns", "model",
     '      "person.pronouns",\n', ""),
    ("4 declaration adds event.work.period before any editor exists", "model",
     '      "person.pronouns",\n', '      "person.pronouns",\n      "event.work.period",\n'),
    ("5 [oracle] relationship.period structural translation removed", "oracle",
     '            if (v or {}).get("period") != before:\n                concepts.add("relationship.period")\n',
     "            pass\n"),
    ("6 [oracle] name-alias structural translation removed", "oracle",
     '            if op == "add" and (v or {}).get("kind") == "also_known_as":\n'
     '                concepts.add("person.name.alias")\n',
     ""),
    ("6b editor stops offering the also-known-as name kind", "shell",
     'return k[0] !== "also_known_as" || can("person.name.alias");', 'return k[0] !== "also_known_as";'),
    ("7 capability begin marker removed", "model",
     "  /* QV2_CAPABILITIES_JSON_BEGIN */\n", ""),
    ("7b capability literal malformed (trailing comma)", "model",
     '      "relationship.qualifier.lineage_side"\n    ]',
     '      "relationship.qualifier.lineage_side",\n    ]'),
    ("8 an undefined concept is declared editable", "model",
     '      "person.pronouns",\n', '      "person.pronouns",\n      "person.shoe_size",\n'),
    ("9 work removed from EVENT_DATE_CONCEPT", "store",
     '    "work": "event.work.period",                # C-4C\n', ""),
    ("10 education removed from EVENT_DATE_CONCEPT", "store",
     '    "education": "event.education.period",      # C-4C\n', ""),
    ("11 separation removed from EVENT_DATE_CONCEPT", "store",
     '    "separation": "event.separation.date",      # C-4C\n', ""),
    ("12 activity mapping removed", "store",
     '    "activity": "event.activity.period",\n', ""),
    ("13 browser and server event-date maps diverge", "model",
     'work: "event.work.period",', 'work: "event.work.career",'),
    ("14 editor ignores the declaration (fail-closed gate removed)", "shell",
     "  function can(concept) { return model().isEditableConcept(concept); }",
     "  function can(concept) { return true; }"),
]


class Runner(MutationRunner):
    def run_suites(self, suites, timeout=300):
        env = {**os.environ, "PYTHONPATH": self.pythonpath, "PYTHONPYCACHEPREFIX": self.pycache}
        t = subprocess.run([sys.executable, "-m", "unittest", *suites], cwd=REPO, env=env,
                           capture_output=True, text=True, timeout=timeout)
        c = subprocess.run([sys.executable, "scripts/catalog/compile_concept_catalog.py", "--check"],
                           cwd=REPO, env=env, capture_output=True, text=True, timeout=timeout)
        return (t.stderr.count("FAIL:") + t.stderr.count("ERROR:") + (t.returncode != 0 and not
                (t.stderr.count("FAIL:") + t.stderr.count("ERROR:")))
                + (c.returncode != 0))


def main(labels):
    chosen = [m for m in MUTATIONS if not labels or any(l in m[0] for l in labels)]
    with Runner(SOURCES) as mr:
        for label, key, old, new in chosen:
            v = mr.check(label, key, old, new, SUITES, timeout=400)
            print(f"  {v:<14} {label}", flush=True)
        ok = mr.report()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
