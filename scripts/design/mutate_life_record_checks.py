#!/usr/bin/env python3
"""Mutation gate for the design validator — proves its checks can fail.

WHY. `validate_life_record_design.py` printing DESIGN COHERENT is worth
nothing on its own: a check that cannot fail passes for free, and this
project has shipped nine of those (docs/TESTING-DOCTRINE.md). So every
contract check gets a mutation that SHOULD break it. A mutation that
survives names an inert check.

The zero-count rule is the cautionary case. It shipped green for as long as
it existed, and it was wrong in both directions at once — it refused a
narrator who said "I had no siblings", and it let a genuinely list-derived
count straight through. No test objected, because nothing tried to break it.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPYCACHEPREFIX=/tmp/pyc python3 scripts/design/mutate_life_record_checks.py
"""

import importlib.util
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "validate_life_record_design.py")
# Since Batch B-3 (2026-09-23) the rules live ONCE, in the product; the
# validator imports them. A mutation's anchor may be in either file.
RULES_FILE = os.path.join(HERE, "..", "..", "server", "code", "api", "services",
                          "life_record", "rules.py")
_CODE = os.path.join(HERE, "..", "..", "server", "code")
if _CODE not in sys.path:
    sys.path.insert(0, _CODE)

# (description, find, replace, the check that must notice)
MUTATIONS = [
    ("reject on stale baseRevision instead of per path",
     'if rejected:\n        return {"conflict": rejected',
     'if rejected or base_revision != store["revision"]:\n'
     '        return {"conflict": rejected or [("*","stale revision")]',
     "write conflict is decided per path"),

    ("drop the cap on turn-scoped people",
     "for m in recent[:cap]:",
     "for m in recent[:]:",
     "required facts stay bounded"),

    ("emit the name without the life status",
     'line = f"{p[\'names\'][0][\'fullText\']} — {m[\'relation\']} — {st}"',
     'line = f"{p[\'names\'][0][\'fullText\']} — {m[\'relation\']}"',
     "required facts stay bounded"),

    ("let a place correction cascade into the trip label",
     'places["PL1"]["label"] = "Spokane, Washington, USA"     # a correction',
     'places["PL1"]["label"] = "Spokane, Washington, USA"\n'
     '    trip["stopLabel"] = places["PL1"]["label"]',
     "places and events cross the domain safely"),

    ("allow a referenced place to be hard-deleted",
     'if any(t["place_id"] == pid for t in trips):\n'
     '            return "refused: merge instead"',
     'if False:\n            return "refused: merge instead"',
     "places and events cross the domain safely"),

    ("export without computing the reference closure",
     'missing = {t["place_id"] for t in trips\n'
     '                   if t["place_id"] and t["place_id"] not in included_places}',
     'missing = set()',
     "places and events cross the domain safely"),

    ("let an unpromoted event carry a placement",
     '{"id": "E1", "type": "union", "date": D("1971", "1971", "year"),\n'
     '         "promoted": False}',
     '{"id": "E1", "type": "union", "date": D("1971", "1971", "year"),\n'
     '         "promoted": False, "era_candidates": ["young adult"]}',
     "review gate is not bypassed"),

    ("a producer names a concept the catalog lacks",
     '"extraction": {"person.birth.date", "person.death.date"},',
     '"extraction": {"person.birth.date", "parents.deathDate"},',
     "producers resolve against the catalog"),

    ("let restore accept an id ledger and remap",
     'if ledger is not None:\n'
     '            return {"refused": "restore does not take an id ledger"}',
     'if ledger is not None:\n'
     '            return {"ids": [ledger.get(p["id"], p["id"]) for p in package["people"]],\n'
     '                    "remapped": True}',
     "restore keeps ids"),

    # ── DOB / life-span scaffold ──────────────────────────────────────
    ("extend a deceased narrator with no death date to today",
     'end, kind = (death, "death_date") if death else (None, "deceased_date_unknown")',
     'end, kind = (death, "death_date") if death else '
     '({"text": today, "value": today, "precision": "day"}, "today_computed")',
     "DOB anchors the life span"),


    ("default a missing DOB so the scaffold always resolves",
     'return {"start": start, "end": end, "end_kind": kind,\n'
     '            "available": start is not None,',
     'start = start or {"text": "1900", "value": "1900", "precision": "year"}\n'
     '    return {"start": start, "end": end, "end_kind": kind,\n'
     '            "available": True,',
     "DOB anchors the life span"),


    ("subtract birth years instead of calling the shipped compute_age",
     'years = compute_age(date(by, bm, bd), wy, wm, wd)',
     'years = wy - by',
     "uncertainty propagates"),

    ("report a coarse date's age as one number rather than a pair",
     '"render": f"{lo} or {hi}" if lo != hi else str(hi)}',
     '"render": str(hi)}',
     "uncertainty propagates"),

    ("treat an approximate birth as precise",
     'return {"years": hi, "exact": False, "low": lo, "high": hi,\n'
     '                "render": f"about {hi}"}',
     'return {"years": hi, "exact": True, "render": str(hi)}',
     "uncertainty propagates"),

    ("give a living narrator's span a computed end the product does not have",
     'end, kind = None, "open"                 # the shipped behaviour, kept',
     'end, kind = {"text": today, "value": today, "precision": "day"}, "today_computed"',
     "DOB anchors the life span"),

    ("follow a birth pointer to any event type",
     'if ev.get("type") != expected_type:\n'
     '        return None, f"ref_is_{ev.get(\'type\')}_not_{expected_type}"',
     'pass',
     "DOB anchors the life span"),

    ("follow a birth pointer to another person's birth",
     'if person_id not in subjects:\n'
     '        return None, "subject_is_someone_else"',
     'pass',
     "DOB anchors the life span"),

    ("decide DOB acceptance by status name instead of a recorded decision",
     'accepted_id = event.get("acceptedAssertionId")\n'
     '    if accepted_id is not None:\n'
     '        return next((d for d in live if d.get("id") == accepted_id), None)',
     'chosen = next((d for d in live if d.get("status") in\n'
     '                   ("operator_entered", "narrator_corrected")), None)\n'
     '    if chosen is not None:\n'
     '        return chosen',
     "DOB conflicts and corrections"),

    ("guess a DOB when two live assertions are undecided",
     'return live[0] if len(live) == 1 else None',
     'return live[0]',
     "DOB conflicts and corrections"),

    ("derive a Life Map era from the narrator's age",
     'return ev.get("era_candidates") or "unplaced"',
     'return ev.get("era_candidates") or (["mid life"] if derived_age else "unplaced")',
     "calendar chronology is not narrative placement"),

    ("an entity loses its export/erase lane",
     'lanes = {"people", "places", "events", "relationships", "stories",\n'
     '             "animals", "biography"}',
     'lanes = {"people", "events", "relationships", "stories",\n'
     '             "animals", "biography"}',
     "every entity has an export/erase lane"),
]

# (description, find, replace, the RULE that must notice) — model rules are
# exercised through their MUST_FAIL fixtures, so these mutate the rule itself.
RULE_MUTATIONS = [
    ("conflict ignores context, so successive jobs become a dispute",
     'ctx = assertion.get("context") or assertion.get("period") or assertion.get("when")\n'
     '    return (list_key, json.dumps(ctx, sort_keys=True) if ctx else None)',
     'return (list_key, None)',
     "11 · two jobs in sequence"),

    ("the conflict rule reverts to demanding every member be `conflicted`",
     'if not (adjudicated or linked):',
     'if not all(a.get("status") == "conflicted" for a in live):',
     "12 · an accepted DOB beside a retained alternative"),

    ("the zero-count rule reverts to its 2026-09-22 defect",
     'if rc.get("derivedFrom"):\n'
     '            bad.append(f"reportedCounts.{concept}: derived from "\n'
     '                       f"{rc[\'derivedFrom\']!r} — a count is stated, not computed")',
     'if rc["value"] == 0:\n'
     '            bad.append(f"reportedCounts.{concept}: derived from an empty list")',
     "9 · an only child"),
]

# A rule made LAXER breaks no passing case — it lets a refusal through. These
# mutate a rule and assert the named MUST_FAIL fixture is no longer refused.
# Both were live defects on 2026-09-22, found by external review.
LAXNESS_MUTATIONS = [
    ("the provenance rule reverts to skipping value-without-source",
     'if is_assertion(node, parent_key) and "source" not in node:\n'
     '                bad.append(f"{path}: a value with no provenance")\n'
     '            elif is_assertion(node, parent_key) and "status" not in node:\n'
     '                bad.append(f"{path}: an assertion with no status")\n'
     '            elif is_assertion(node, parent_key) and not node.get("recordedAt"):\n'
     '                # Provenance is who said it AND when. Without the when, a\n'
     '                # later correction cannot be ordered against it.\n'
     '                bad.append(f"{path}: an assertion with no recordedAt")',
     'pass',
     "a value recorded with no provenance"),

    ("story references resolve for people only, as before",
     'for kind, universe in (("peopleRefs", ids),\n'
     '                               ("eventRefs", {e["id"] for e in b.get("events", [])}),\n'
     '                               ("placeRefs", {p["id"] for p in b.get("places", [])}),\n'
     '                               ("animalRefs", {a["id"] for a in b.get("animals", [])})):',
     'for kind, universe in (("peopleRefs", ids),):',
     "a story pointing at an event that does not exist"),

    # The first version of this mutation removed only the id guard and
    # SURVIVED — because `is not None` below defends the same hole a second
    # way. That is fine for the product and useless as a mutation. This one
    # reproduces the original bug exactly: None decision ∈ {None id}.
    ("a missing id counts as adjudicated (None in {None})",
     'if any(not a.get("id") for a in live):\n'
     '                        # Without ids nothing can be linked or accepted — and a\n'
     '                        # None id must not read as "matches the None decision".\n'
     '                        bad.append(f"{path}: competing accounts without ids "\n'
     '                                   "cannot be linked or adjudicated")\n'
     '                        continue\n'
     '                    ids = {a.get("id") for a in live}\n'
     '                    adjudicated = accepted is not None and accepted in ids',
     'ids = {a.get("id") for a in live}\n'
     '                    adjudicated = accepted in ids',
     "competing claims silently reduced to one"),

    ("a date assertion is classified by shape again, not by location",
     'if parent_key == "dateAssertions":\n'
     '            return True',
     'pass',
     "a date assertion with no provenance, hiding among dates"),

    ("recordedAt stops being required on an assertion",
     'bad.append(f"{path}: an assertion with no recordedAt")',
     'pass',
     "an assertion with no recordedAt"),

    # The first attempt at this mutation (`elif not candidates:` → `elif False:`)
    # SURVIVED, because the membership branch still caught it. The real defect
    # was the `candidates and` short-circuit, so that is what gets restored.
    ("the candidate check reverts to short-circuiting on an empty inventory",
     'elif not candidates:\n'
     '                # `candidates and ...` made an ABSENT inventory disable the\n'
     '                # check, so the least verifiable case was the one that passed.\n'
     '                # A captured story with no inventory to resolve against is\n'
     '                # unrestorable, which is a portability defect.\n'
     '                bad.append(f"story {s[\'id\']}: captured, but no candidate "\n'
     '                           "inventory exists to resolve it against")\n'
     '            elif s["candidateRef"] not in candidates:',
     'elif candidates and s["candidateRef"] not in candidates:',
     "a captured story with no resolvable candidate"),

    ("the required-facts ceiling goes back to being measured, not enforced",
     'if used + len(line) > ceiling:\n'
     '            dropped.append(m["person"])          # falls to retrieval, whole\n'
     '            continue',
     'pass',
     None),      # caught by a CONTRACT, not a refusal — see below
]


def _load(source_text, rules_text=None):
    """Load the validator; when `rules_text` is given, the validator imports
    THAT (mutated) copy of the product rules instead of the real one."""
    import api.services.life_record as _pkg
    real = sys.modules.get("api.services.life_record.rules")
    d = tempfile.mkdtemp()
    try:
        if rules_text is not None:
            rpath = os.path.join(d, "rules.py")
            with open(rpath, "w", encoding="utf-8") as fh:
                fh.write(rules_text)
            rspec = importlib.util.spec_from_file_location(
                "api.services.life_record.rules", rpath)
            rmod = importlib.util.module_from_spec(rspec)
            sys.modules["api.services.life_record.rules"] = rmod
            rspec.loader.exec_module(rmod)
            _pkg.rules = rmod
        path = os.path.join(d, "mutant.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(source_text)
        spec = importlib.util.spec_from_file_location("mutant", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        if rules_text is not None:
            if real is not None:
                sys.modules["api.services.life_record.rules"] = real
                _pkg.rules = real
            else:
                sys.modules.pop("api.services.life_record.rules", None)
                if hasattr(_pkg, "rules"):
                    delattr(_pkg, "rules")      # never leave the mutant reachable


def _mutant(src, rsrc, old, new):
    """The module with ONE mutation applied to whichever file holds it."""
    if old in src:
        return _load(src.replace(old, new, 1))
    return _load(src, rsrc.replace(old, new, 1))


def main():
    src = open(TARGET, encoding="utf-8").read()
    rsrc = open(RULES_FILE, encoding="utf-8").read()
    ok = True

    baseline = _load(src)
    if any(fn() for _, fn in baseline.CONTRACTS):
        print("  BASELINE IS RED — fix the validator before mutating it")
        return 1

    print("\nCONTRACT CHECKS\n" + "─" * 74)
    for name, old, new, expect in MUTATIONS:
        if old not in src and old not in rsrc:
            print(f"  STALE {name[:54]:<54} anchor not found")
            ok = False
            continue
        fired = [t for t, fn in _mutant(src, rsrc, old, new).CONTRACTS if fn()]
        hit = any(expect in t for t in fired)
        ok &= hit
        print(f"  {'ok  ' if hit else 'FAIL'} {name[:54]:<54} "
              f"{'caught' if hit else 'SURVIVED'}")

    print("\nMODEL RULES\n" + "─" * 74)
    for name, old, new, expect in RULE_MUTATIONS:
        if old not in src and old not in rsrc:
            print(f"  STALE {name[:54]:<54} anchor not found")
            ok = False
            continue
        m = _mutant(src, rsrc, old, new)
        broke = [t for t, bio in m.CASES.items() if m.run(bio)]
        hit = any(expect in t for t in broke)
        ok &= hit
        print(f"  {'ok  ' if hit else 'FAIL'} {name[:54]:<54} "
              f"{'caught' if hit else 'SURVIVED'}")

    print("\nRULES MADE LAXER — a refusal must stop being refused\n" + "─" * 74)
    for name, old, new, fixture in LAXNESS_MUTATIONS:
        if old not in src and old not in rsrc:
            print(f"  STALE {name[:54]:<54} anchor not found")
            ok = False
            continue
        m = _mutant(src, rsrc, old, new)
        if fixture is None:                       # a contract notices instead
            hit = any(fn() for _, fn in m.CONTRACTS)
        else:
            bio, rule = m.MUST_FAIL[fixture]
            hit = not any(r == rule for r, _ in m.run(bio))
        ok &= hit
        print(f"  {'ok  ' if hit else 'FAIL'} {name[:54]:<54} "
              f"{'caught' if hit else 'SURVIVED'}")

    print("\n" + "─" * 74)
    print("  every mutation caught" if ok else
          "  A MUTATION SURVIVED — that check is inert and proves nothing")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
