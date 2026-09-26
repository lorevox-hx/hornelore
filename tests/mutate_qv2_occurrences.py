#!/usr/bin/env python3
"""Mutation gate for Batch C-4F — homes/moves and unions/separations, the
intake's current residence, and the person-independence scenario.

Each mutation breaks one C-4F promise IN PLACE (tests/mutation_runner.py:
restore after every mutation, verified byte-identical at exit) and runs the
C-4F suites: the real editor against the real writer, then the database. A
missing anchor is NOT APPLIED, never counted as caught.

The stack must be DOWN — this edits product source in place.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python tests/mutate_qv2_occurrences.py [label-substring ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tests.mutation_runner import MutationRunner  # noqa: E402

SOURCES = {
    "shell": REPO / "ui" / "js" / "questionnaire-v2.js",
    "model": REPO / "ui" / "js" / "questionnaire-v2-model.js",
    "writer": REPO / "server" / "code" / "api" / "services" / "life_record" / "writer.py",
    "identity": REPO / "server" / "code" / "api" / "services" / "life_record" / "identity.py",
    "graph": REPO / "server" / "code" / "api" / "services" / "life_record" / "graph_projection.py",
    "rules": REPO / "server" / "code" / "api" / "services" / "life_record" / "rules.py",
    "captest": REPO / "tests" / "test_qv2_capabilities.py",        # the capability ORACLE
}
SUITES = ["tests.test_qv2_occurrences", "tests.test_life_record_identity",
          "tests.test_life_record_person_independence"]

_SAME_PAIR = ('Object.keys(S.view.events).filter(function (x) { var u = S.view.events[x]; '
              'return u.type === kind && (u.participants || []).some(function (p) { return p.personId === partnerId; }); })[0]')

MUTATIONS = [
    ("O1 a chosen place is resolved by its label instead of its id", "shell",
     '      var id = sel.slice("existing:".length);',
     '      var id = sel.slice("existing:".length); id = Object.keys(S.view.places).filter(function (x) '
     '{ return S.view.places[x].label === (S.view.places[id] || {}).label; })[0] || id;'),
    ("O2 a new place with a recorded name silently reuses that place", "shell",
     '      return { mode: "new", placeId: newId("qv2pl-"), label: label };',
     '      var _same = Object.keys(S.view.places).filter(function (x) { return S.view.places[x].label === label; })[0];'
     ' return _same ? { mode: "existing", placeId: _same } : { mode: "new", placeId: newId("qv2pl-"), label: label };'),
    ("O3 a home with no closed end is read as current", "model",
     '      return e.type === "move" && e.involvesNarrator && e.attributes && e.attributes.current === true;',
     '      return e.type === "move" && e.involvesNarrator && ((e.attributes && e.attributes.current === true) || '
     '!(e.date && e.date.state === "value" && /\\/\\d/.test(String((e.date.value || {}).value || ""))));'),
    ("O4 an impossible period bypasses the form's validation", "shell",
     "        if (date && date.refuse) { return err(date.refuse); }  // C-4F: never downgraded to words\n",
     ""),
    ("O5 one home's edit overwrites another's", "shell",
     '    var key = "occ:" + (eventId || "");', '    var key = "occ:" + kind;'),
    ("O6 a union is deduplicated by its pair of people", "shell",
     '    var id = eventId || newId("qv2e-");', '    var id = eventId || ' + _SAME_PAIR + ' || newId("qv2e-");'),
    ("O7 a separation rewrites the union it ends", "shell",
     "      if (e.current === true) v.attributes = { current: true };",
     "      if (e.current === true) v.attributes = { current: true };"
     ' if (e.occKind === "separation") Object.keys(S.view.events).forEach(function (x) { var u = S.view.events[x];'
     ' if (u.type === "union" && u.participants.some(function (p) { return p.personId === e.partnerId; })) {'
     ' var a = JSON.parse(JSON.stringify(u.raw)); a.attributes = { ended: true };'
     ' ops.push({ op: "set", path: "events/" + x, value: a, expectedPrevious: u.raw }); } });'),
    ("O8 a second union with the same pair is refused", "shell",
     '      if (!partnerId || !S.view.people[partnerId] || partnerId === nid) return err("choose who this is with.");',
     '      if (!partnerId || !S.view.people[partnerId] || partnerId === nid) return err("choose who this is with.");'
     ' if (kind === "union" && ' + _SAME_PAIR + ') return err("a union with this person is already recorded.");'),
    ("O9 a union date is written under the wrong concept", "shell",
     '    union:      { date: "event.union.date",', '    union:      { date: "event.separation.date",'),
    ("O10 the writer commits a change set that breaks a model rule (partial commit)", "writer",
     "            if violations:", "            if False:"),
    ("O11 an unchanged legacy period is re-parsed (and silently rewritten)", "shell",
     '      if (!(stored && String(stored.text || "").trim() === typed)) {\n        date = model().parseDateText(typed);',
     '      if (true) {\n        date = model().parseDateText(typed);'),
    ("O12 every new home is written as current, unasked", "shell",
     "      if (e.current === true) v.attributes = { current: true };",
     '      if (e.occKind === "move") v.attributes = { current: true };'),
    ("O13 editing a stored occurrence mints a new event (stranding its stories)", "shell",
     '    S.edits[key] = { kind: "occ", occKind: kind, topic: S.topic, eventId: id, isNew: !ev,',
     '    S.edits[key] = { kind: "occ", occKind: kind, topic: S.topic, eventId: ev ? newId("qv2e-") : id, isNew: true,'),
    ("O14 a corrected accepted period leaves the acceptance behind", "shell",
     "    if (edit.basis.accepted) {", "    if (false) {"),
    # (O15 retired in the C-4F review repair: Separation no longer OFFERS a Place — see O26)
    ("O16 the stated marriage count is computed from the unions", "model",
     '          marriages: field(p, "person.reported_count.marriages"),',
     '          marriages: { concept: "person.reported_count.marriages", state: "value", history: [], accepted: false,'
     ' value: (record.events || []).filter(function (e) { return e.type === "union"; }).length },'),
    ("O17 the intake's current residence is left legacy-only", "identity",
     "    if home:", "    if False:"),
    ("O18 the intake's residence is not marked current", "identity",
     '                                  "attributes": {"current": True}}})', "                                  }})"),
    ("O19 the graph projection turns parent_of into a gendered title", "graph",
     '            "relationship_type": r["kind"],',
     '            "relationship_type": {"parent_of": "father_of"}.get(r["kind"], r["kind"]),'),
    ("O20 a home said to be current may carry an ended period", "shell",
     '        return err("a current home cannot have a period that has ended — correct the period, or untick current.");',
     "        void 0;"),
    # ── C-4F review repair ──────────────────────────────────────────────
    ("O21 a stored union's participant cannot be corrected", "shell",
     "    if (ev && C.partner && can(C.partner)) {", "    if (false) {"),
    ("O22 a correction replaces EVERY other participant (collapses the occurrence)", "shell",
     "          return { person: e.swaps[x.person] || x.person, role: x.role }; });",
     "          return { person: x.person === S.view.narratorPersonId ? x.person : e.swaps[Object.keys(e.swaps)[0]], role: x.role }; });"),
    ("O23 a correction may name someone already in the occurrence", "shell",
     "        if (present.indexOf(nw) !== -1 || taken[nw])", "        if (taken[nw] && false)"),
    ("O24 the writer permits a derived relationship between non-participants", "rules",
     '    ("derived relationships match their event\'s people", rule_derived_relationship_matches_its_event),\n', ""),
    ("O25 the derived relationship is not updated in the same Save", "shell",
     '        ops.push({ op: "set", path: "relationships/" + d.relId, value: d.after, expectedPrevious: d.before });',
     "        void d;"),
    ("O26 the add form offers a Place for a Separation again", "shell",
     "    var sel = addable.length === 1 || addable.indexOf(chosen) === -1 ? addable[0] : chosen, Cs = OCC[sel];",
     '    var sel = addable.length === 1 || addable.indexOf(chosen) === -1 ? addable[0] : chosen, '
     'Cs = OCC[addable.indexOf("union") !== -1 ? "union" : sel];'),
    ("O27 a period typed “to present” saves on a home that is not current", "shell",
     '      if (date && !isNow && end === "..")', "      if (false)"),
    ("O28 unticking current keeps a stored “to present” period", "shell",
     "      if (current === false && !date && /\\/\\.\\.$/.test(storedV))", "      if (false)"),
    ("O29 a stored contradiction blocks an unrelated edit", "shell",
     "      if ((current === true || (date && isNow)) && end !== null", "      if (isNow && end !== null"),
    ("O30 [oracle] a participant SET is not recognised as a participant write", "captest",
     '                if (op == "add" and len(now) > 1) or (op == "set" and now != was):',
     '                if (op == "add" and len(now) > 1):', ["tests.test_qv2_capabilities"]),
    ("O31 [oracle] a separation's participants are classified as a date write", "captest",
     '                    concepts.add(f"event.{t}.participant")',
     '                    concepts.add("event.union.participant" if t == "union" else "event.separation.date")',
     ["tests.test_qv2_capabilities"]),
    ("O32 a new home's kind is left out of its first Save", "shell",
     '      ops.push(assertionOp(idOf(e, "homeTypeAssertionId"), "event", e.eventId, "event.residence.type", e.homeType, src));',
     "      void src;"),
    ("O33 the card shows only the first of several participants", "shell",
     "    return (ev.participants || []).filter(function (x) { return x.personId !== nid; })\n      .map(function (x) { return x.personId; });",
     "    return (ev.participants || []).filter(function (x) { return x.personId !== nid; })\n      .map(function (x) { return x.personId; }).slice(0, 1);"),
]


def main(labels):
    chosen = [m for m in MUTATIONS if not labels or any(l in m[0] for l in labels)]
    with MutationRunner(SOURCES) as mr:
        for m in chosen:
            label, key, old, new = m[:4]
            v = mr.check(label, key, old, new, m[4] if len(m) > 4 else SUITES, timeout=500)
            print(f"  {v:<14} {label}", flush=True)
        ok = mr.report()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
