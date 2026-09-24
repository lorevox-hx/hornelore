#!/usr/bin/env python3
"""Mutation gate for Batch C-3 (Questionnaire V2 people and relationships).

Each mutation breaks one promise in a COPY of ui/js and runs
tests.test_qv2_people against it (env QV2_ROOT). A mutation that leaves the
suite green names a check that cannot fail.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python tests/mutate_qv2_people.py [name ...]
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SHELL, MODEL = "ui/js/questionnaire-v2.js", "ui/js/questionnaire-v2-model.js"

MUTATIONS = {
    "ui-duplicate-check-off": (SHELL, "    return saved.concat(pending).some(same);", "    return false;"),
    "ids-reminted-at-save": (SHELL, 'var ops = [{ op: "add", path: "people/" + e.personId, value: {} },',
                             'var ops = [{ op: "add", path: "people/" + newId("qv2p-"), value: {} },'),
    "child-direction-ignored": (SHELL, 'var v = { subjectPersonId: R.narratorIs === "other" ? personId : nid,\n'
                                       '              otherPersonId: R.narratorIs === "other" ? nid : personId, kind: R.kind };',
                                'var v = { subjectPersonId: personId, otherPersonId: nid, kind: R.kind };'),
    "rel-edit-claims-the-new-value": (SHELL, 'value: e.after, expectedPrevious: e.before }',
                                      'value: e.after, expectedPrevious: e.after }'),
    "half-filled-form-forgotten": (SHELL, "    return f && f[field] !== undefined ? f[field] : dflt;", "    return dflt;"),
    "role-preselected": (SHELL, 'options(roles, fv(k, "role", ""), "— choose —")', 'options(roles, fv(k, "role", roles[0][0]), null)'),
    "undo-leaves-the-person": (SHELL, '    if (e.kind === "newrel" && S.edits["newperson:" + e.personId] &&',
                               '    if (false && S.edits["newperson:" + e.personId] &&'),
    "count-stored-as-text": (SHELL, '      return { value: parseInt(value, 10) };', '      return { value: value };'),
    "provenance-ignored": (SHELL, "    var src = PROVENANCE[S.provenance] || PROVENANCE.operator;",
                           "    var src = PROVENANCE.operator;"),
    "approximate-date-given-a-value": (MODEL, '    return { text: t, value: null, precision: "unknown" };',
                                       '    return { text: t, value: t.replace(/[^0-9]/g, ""), precision: "year" };'),
    "names-block-hides-other-names": (SHELL, '    var saved = p ? p.names : [];', '    var saved = p ? p.names.slice(0, 1) : [];'),
    # ChatGPT's invariant list (review of 16a68e1)
    "assertion-id-minted-at-save": (SHELL, 'assertionOp(e.kindAssertionId || newId("qv2a-"), "relationship"',
                                    'assertionOp(newId("qv2a-"), "relationship"'),
    "inverse-row-generated": (SHELL, '        var out = [{ op: "add", path: "relationships/" + e.relId, value: e.value },',
                              '        var out = [{ op: "add", path: "relationships/" + e.relId, value: e.value },\n'
                              '                   { op: "add", path: "relationships/" + e.relId + "-inv", value: '
                              '{ subjectPersonId: e.value.otherPersonId, otherPersonId: e.value.subjectPersonId, kind: e.value.kind } },'),
    "relationship-left-out-of-the-patch": (SHELL, '        var out = [{ op: "add", path: "relationships/" + e.relId, value: e.value },',
                                           '        var out = [];'),
    "draft-of-A-lands-on-B": (SHELL, '      var raw = root.localStorage.getItem(DRAFT_PREFIX + pid);\n'
                              '      if (!raw) return null;\n'
                              '      var d = JSON.parse(raw);\n'
                              '      return d && d.v === DRAFT_VERSION && d.pid === pid ? d : null;',
                              '      for (var i = 0; i < root.localStorage.length; i++) {\n'
                              '        var k = root.localStorage.key(i);\n'
                              '        if (k.indexOf(DRAFT_PREFIX) === 0) return JSON.parse(root.localStorage.getItem(k));\n'
                              '      }\n'
                              '      return null;'),
    "rel-edit-without-expectedPrevious": (SHELL, 'value: e.after, expectedPrevious: e.before }', 'value: e.after }'),
    "full-name-split": (SHELL, 'value: { fullText: e.fullText, kind: "current" } }];',
                        'value: { fullText: e.fullText, kind: "current", givenParts: e.fullText.split(" ").slice(0, -1), '
                        'family: e.fullText.split(" ").slice(-1)[0] } }];'),
    "save-also-puts-the-graph": (SHELL, '    S.status = "saving"; S.conflict = null; S.refused = null; S.message = null;',
                                 '    root.fetch((root.LOREVOX_API || "http://localhost:8000") + "/api/graph/" + pid, { method: "PUT", body: "{}" });\n'
                                 '    S.status = "saving"; S.conflict = null; S.refused = null; S.message = null;'),
    # C-3 review repairs
    "family-late-answer-repaints": (SHELL, '      if (myGen !== _famGen) return;                                   // a newer Family request owns the screen\n',
                                    ''),
    "family-late-failure-repaints": (SHELL, '    }).catch(function (e) {\n      if (myGen !== _famGen) return;\n',
                                     '    }).catch(function (e) {\n'),
    "ui-missing-period-counts-as-a-match": (SHELL,
        '      return JSON.stringify(sortKeys(x.period || null)) === JSON.stringify(sortKeys(v.period || null));',
        '      return !(x.period && v.period && JSON.stringify(sortKeys(x.period)) !== JSON.stringify(sortKeys(v.period)));'),
}


def run(name):
    path, find, repl = MUTATIONS[name]
    tmp = Path(tempfile.mkdtemp())
    (tmp / "ui").mkdir()
    shutil.copytree(REPO / "ui" / "js", tmp / "ui" / "js")
    target = tmp / path
    src = target.read_text()
    if find not in src:
        return "ANCHOR MISSING"
    target.write_text(src.replace(find, repl, 1))
    env = dict(os.environ, QV2_ROOT=str(tmp), PYTHONPYCACHEPREFIX="/tmp/pyc",
               PYTHONPATH=str(REPO / "server" / "code"))
    r = subprocess.run([sys.executable, "-m", "unittest", "tests.test_qv2_people"], cwd=REPO, env=env,
                       capture_output=True, text=True, timeout=400)
    shutil.rmtree(tmp, ignore_errors=True)
    return "caught" if r.returncode != 0 else "SURVIVED"


if __name__ == "__main__":
    names = sys.argv[1:] or list(MUTATIONS)
    bad = 0
    for n in names:
        res = run(n)
        bad += res != "caught"
        print(f"  {'ok  ' if res == 'caught' else 'FAIL'} {n:40s} {res}", flush=True)
    print("every mutation caught" if not bad else f"{bad} mutation(s) not caught")
    sys.exit(1 if bad else 0)
