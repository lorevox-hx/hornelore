#!/usr/bin/env python3
"""Mutation gate for Batch C-4E — birth, death and places.

Each mutation breaks one C-4E promise IN PLACE (tests/mutation_runner.py:
restore after every mutation, verified byte-identical at exit) and runs
tests.test_qv2_vital (the real editor against the real writer, then the
database). A missing anchor is NOT APPLIED, never counted as caught.

The stack must be DOWN — this edits product source in place.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python tests/mutate_qv2_vital.py [label-substring ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tests.mutation_runner import MutationRunner  # noqa: E402

SOURCES = {
    "shell": REPO / "ui" / "js" / "questionnaire-v2.js",
    "rules": REPO / "server" / "code" / "api" / "services" / "life_record" / "rules.py",
    "writer": REPO / "server" / "code" / "api" / "services" / "life_record" / "writer.py",
}
SUITES = ["tests.test_qv2_vital"]

MUTATIONS = [
    ("V1 a death is saved without recording the person deceased", "shell",
     '      } else if (!(ls.state === "value" && ls.value === "deceased")) {',
     "      } else if (false) {"),
    ("V2 marking someone deceased invents a death event", "shell",
     '      case "answer": return answerOps(e, src);',
     '      case "answer": return answerOps(e, src).concat(e.concept === "person.life_status" && '
     'e.value === "deceased" ? [{ op: "add", path: "events/qv2e-inv-" + e.subjectId, value: { type: "death", '
     'participants: [{ person: e.subjectId, role: "subject" }] } }] : []);'),
    ("V3 the editor adds a second birth/death instead of extending the existing one", "shell",
     '                     eventId: cur.eventId || newId("qv2e-"), isNew: !cur.eventId,',
     '                     eventId: newId("qv2e-"), isNew: true,'),
    ("V4 the writer stops refusing a second birth/death event", "rules",
     '    ("one birth and one death per person", rule_one_birth_one_death_per_person),\n', ""),
    ("V5 a chosen place is resolved by its label instead of its id", "shell",
     '      var pid2 = sel.slice("existing:".length);',
     '      var pid2 = sel.slice("existing:".length); pid2 = Object.keys(S.view.places).filter(function (id) '
     '{ return S.view.places[id].label === (S.view.places[pid2] || {}).label; })[0] || pid2;'),
    ("V6 a new place with a recorded name silently reuses that place", "shell",
     '      place = { mode: "new", placeId: newId("qv2pl-"), label: label };',
     '      var _same = Object.keys(S.view.places).filter(function (id) { return S.view.places[id].label === label; })[0];'
     ' place = _same ? { mode: "existing", placeId: _same } : { mode: "new", placeId: newId("qv2pl-"), label: label };'),
    ("V7 the writer commits a change set that breaks a model rule (partial death)", "writer",
     "            if violations:", "            if False:"),
    ("V8 a death date is written under the birth-date concept", "shell",
     '    death: { date: "person.death.date",', '    death: { date: "person.birth.date",'),
    ("V9 an impossible date bypasses the form's validation", "shell",
     "        if (date && date.refuse) return err(date.refuse);", ""),
    ("V11 a correction leaves the explicit acceptance on the superseded assertion", "shell",
     "    if (edit.basis.accepted) {", "    if (false) {"),
    ("V10 an unchanged stored date is re-parsed (and silently rewritten)", "shell",
     '      if (!(stored && String(stored.text || "").trim() === typed)) {        // an unchanged date is not re-parsed',
     "      if (true) {"),
]


def main(labels):
    chosen = [m for m in MUTATIONS if not labels or any(l in m[0] for l in labels)]
    with MutationRunner(SOURCES) as mr:
        for label, key, old, new in chosen:
            v = mr.check(label, key, old, new, SUITES, timeout=400)
            print(f"  {v:<14} {label}", flush=True)
        ok = mr.report()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
