#!/usr/bin/env python3
"""Mutation gate for Batch C-4B (the Life Record date contract).

Each mutation breaks one promise of the contract in PRODUCT source and runs
tests.test_life_record_dates against it. Uses tests/mutation_runner.py, so the
source is restored after every mutation and verified byte-identical at the end
even if a run is interrupted. A mutation that leaves the suite green names a
check that cannot fail.

The stack must be DOWN while this runs — it edits product source in place.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python tests/mutate_life_record_dates.py [label ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tests.mutation_runner import MutationRunner  # noqa: E402

LR = REPO / "server" / "code" / "api" / "services" / "life_record"
SOURCES = {"dates": LR / "dates.py", "writer": LR / "writer.py", "rules": LR / "rules.py",
           "identity": LR / "identity.py",
           "people": REPO / "server" / "code" / "api" / "routers" / "people.py", "model": REPO / "ui" / "js" / "questionnaire-v2-model.js"}
SUITE = ["tests.test_life_record_dates"]

# (label, source, find, replace)
MUTATIONS = [
    # ── the server parser ──
    ("py: Feb 30 accepted (no calendar check)", "dates",
     "if not (1 <= mo <= 12) or not (1 <= d <= calendar.monthrange(y, mo)[1]):",
     "if not (1 <= mo <= 12) or not (1 <= d <= 31):"),
    ("py: approximation dropped from the value", "dates",
     'mark = "%" if (approx and uncertain) else "~" if approx else "?" if uncertain else ""',
     'mark = ""'),
    ("py: a decade gets precision unknown", "dates",
     'return (f"{m.group(1)}X", "year")', 'return (f"{m.group(1)}X", "unknown")'),
    ("py: a reversed range is accepted", "dates",
     "            return _REFUSE                              # a reversed range",
     "            pass"),
    ("py: a refusal is downgraded to text", "dates",
     '            return ("refuse", f"{text.strip()!r} is not a real date — correct it, or write it in words")',
     '            return ("text", None, "unknown")'),
    # ── the browser parser ──
    ("js: Feb 30 accepted (no calendar check)", "model",
     "if (mo < 1 || mo > 12 || d < 1 || d > monthDays(y, mo)) return REFUSE;",
     "if (mo < 1 || mo > 12 || d < 1 || d > 31) return REFUSE;"),
    ("js: approximation dropped from the value", "model",
     'var mark = approx && uncertain ? "%" : approx ? "~" : uncertain ? "?" : "";', 'var mark = "";'),
    ("js: slashed day/month/year normalised", "model",
     '    return null;\n  }\n\n  function qualifiedDate(s) {',
     '    if ((m = full("(\\\\d{1,2})/(\\\\d{1,2})/(\\\\d{4})", s))) return { v: m[3] + "-" + pad(+m[2], 2) + "-" + pad(+m[1], 2), p: "day", parts: [+m[3], +m[2], +m[1]] };\n'
     '    return null;\n  }\n\n  function qualifiedDate(s) {'),
    ("js: text rewritten (lower-cased) on the way out", "model",
     "      if (r) return { text: t, value: r.v, precision: r.p };",
     "      if (r) return { text: s, value: r.v, precision: r.p };"),
    # ── the writer ──
    ("writer: date assertions not checked", "writer",
     '        if vtype in ("date", "date_interval"):', '        if False:'),
    ("writer: a range accepted in a single-date concept", "writer",
     'why = _dates.check(v.get("value"), allow_interval=(vtype == "date_interval"))',
     'why = _dates.check(v.get("value"), allow_interval=True)'),
    ("writer: value checked, precision ignored", "dates",
     '    if obj.get("value") != want_value or obj.get("precision") != want_precision:',
     '    if obj.get("value") != want_value:'),
    ("writer: legacy precision words accepted on a new write", "dates",
     '    if obj.get("precision") not in PRECISIONS:',
     '    if obj.get("precision") not in PRECISIONS + LEGACY_VAGUE_PRECISIONS:'),
    ("writer: relationship periods not checked", "writer",
     '        if coll == "relationships":\n            _check_period(',
     '        if False:\n            _check_period('),
    ("writer: name periods not checked", "writer",
     '            _check_period(path, v.get("period"),\n                          (self.view(path) or {}).get("period") if op == "set" else None)\n            cols = {col',
     '            cols = {col'),
    ("writer: an UNCHANGED legacy endpoint is re-validated", "writer",
     '        if end in new and new[end] is not None and not _same(new[end], old.get(end)):',
     '        if end in new and new[end] is not None:'),
    ("writer: a NAME's unchanged legacy endpoint is re-validated", "writer",
     '            _check_period(path, v.get("period"),\n                          (self.view(path) or {}).get("period") if op == "set" else None)\n            cols = {col',
     '            _check_period(path, v.get("period"), None)\n            cols = {col'),
    ("writer: a period endpoint compared against the wrong end", "writer",
     'not _same(new[end], old.get(end)):', 'not _same(new[end], old.get("start")):'),
    # ── consumers ──
    ("rules: age reads approximation from precision only", "rules",
     'approximate = qb["approximate"] or qb["uncertain"] or qw["approximate"] or qw["uncertain"]',
     'approximate = (birth.get("precision") in ("approximate", "uncertain")\n'
     '                   or when.get("precision") in ("approximate", "uncertain"))'),
    ("rules: legacy precision words forgotten", "dates",
     '        "approximate": v.endswith("~") or v.endswith("%") or p == "approximate",',
     '        "approximate": v.endswith("~") or v.endswith("%"),'),
    ("identity: notRecorded is not reported", "identity",
     '    if dob_refused and out.get("ok"):', '    if False:'),
    ("identity: a bad DOB fails the whole creation", "identity",
     '        if r[0] == "refuse":\n            dob_refused = r[1]',
     '        if r[0] == "refuse":\n            return {"ok": False, "refused": [{"path": "", "reason": r[1]}]}'),
    ("route: the raw bad DOB is passed to the legacy people row again", "people",
     '            role=payload.role,\n            date_of_birth=_legacy_birth_date(payload.date_of_birth),',
     '            role=payload.role,\n            date_of_birth=payload.date_of_birth,'),
    ("route: a range is kept as a legacy birth date", "people",
     '    if r[0] == "refuse" or (r[1] and "/" in r[1]):', '    if r[0] == "refuse":'),
    ("route: the intake route passes the raw bad DOB to the legacy row", "people",
     '            role="",\n            date_of_birth=_legacy_birth_date(payload.date_of_birth),',
     '            role="",\n            date_of_birth=payload.date_of_birth,'),
    ("route: the intake profile mirror keeps the raw bad DOB", "people",
     '        "dateOfBirth": _legacy_birth_date(payload.date_of_birth),',
     '        "dateOfBirth": payload.date_of_birth,'),
    ("identity: a refused birth date is downgraded to words", "identity",
     '        if r[0] == "refuse":\n            dob_refused = r[1]',
     '        if r[0] == "refuse":\n            dob_value = {"text": dob, "value": None, "precision": "unknown"}'),
]


def main(labels):
    chosen = [m for m in MUTATIONS if not labels or any(l in m[0] for l in labels)]
    with MutationRunner(SOURCES) as mr:
        for label, key, old, new in chosen:
            v = mr.check(label, key, old, new, SUITE, timeout=300)
            print(f"  {v:<14} {label}", flush=True)
        ok = mr.report()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
