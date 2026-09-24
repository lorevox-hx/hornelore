#!/usr/bin/env python3
"""Mutation gate for the Life Record writer (Batch B-5).

Every guarantee the one writer makes gets a mutation that SHOULD break it,
and the named acceptance test must go red. A mutation that survives names a
test that cannot fail (docs/TESTING-DOCTRINE.md). The mutant replaces the
shipped module's code in place, so the tests exercise it through the same
import path production uses, on real isolated SQLite.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python scripts/design/mutate_life_record_writer.py

Covers the writer (B-2/B-3) and the graph guard + projection (B-4).
"""
import io
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "server", "code"))
sys.path.insert(0, REPO)

import ast  # noqa: E402

from api import db as _dbmod  # noqa: E402
from api.services.life_record import graph_projection as _gp  # noqa: E402
from api.services.life_record import store as _store, writer as _writer  # noqa: E402

TESTS = ("tests.test_life_record_writer", "tests.test_life_record_graph")
W, S, G, D = _writer, _store, _gp, _dbmod
# db.py is mutated ONE FUNCTION AT A TIME: re-running the whole module would
# re-bind the exception classes other modules imported, and reset DB_PATH.
FUNCTION_LEVEL = {D}

# (description, module, find, replace, test that must go red)
MUTATIONS = [
    ("skip the per-path expectedPrevious comparison", W,
     'if not _same(cur, ch["expectedPrevious"]):', "if False:",
     "Concurrency.test_stale_same_path_write_is_rejected_and_writes_nothing"),
    ("reject on any stale baseRevision instead of per path", W,
     "            if refused:\n                con.execute(\"ROLLBACK\")",
     "            if base_revision is not None and base_revision != current_rev:\n"
     "                conflicts.append({'path': '*'})\n"
     "            if refused:\n                con.execute(\"ROLLBACK\")",
     "Concurrency.test_non_overlapping_concurrent_edits_both_succeed"),
    ("make expectedPrevious optional", W,
     'if "expectedPrevious" not in ch:', "if False:",
     "Concurrency.test_expected_previous_is_required"),
    ("commit what applied before the failure (not atomic)", W,
     "        except _Refuse as r:\n            con.execute(\"ROLLBACK\")",
     "        except _Refuse as r:\n            con.execute(\"COMMIT\")",
     "Atomicity.test_one_bad_change_writes_nothing_at_all"),
    ("stop running the model rules before commit", W,
     "violations = _rules.run(_store.assemble(con, narrator_id))", "violations = []",
     "Dates.test_a_birth_pointer_to_someone_elses_birth_is_refused"),
    ("re-adding an assertion id overwrites the old account", W,
     '        self.fresh("lr_assertions", id_, path)',
     '        self.con.execute("DELETE FROM lr_assertions WHERE id = ?", (id_,))',
     "ConflictAcceptCorrect.test_re_adding_an_assertion_id_does_not_overwrite_it"),
    ("drop the narrator-ownership check", W,
     "        if owner != self.nid:\n            raise", "        if False:\n            raise",
     "NarratorIsolation.test_an_assertion_about_another_narrators_person_is_refused"),
    ("drop the catalog check (fail open)", W,
     "if concept not in _catalog_concepts():", "if False:",
     "Atomicity.test_one_bad_change_writes_nothing_at_all"),
    ("let a date live off its event", W,
     'if stype != "event" or ev is None or _store.EVENT_DATE_CONCEPT.get(ev["type"]) != concept:',
     "if False:",
     "Dates.test_a_date_lives_only_on_its_event"),
    ("disclose former names by default", W,
     'cols["use"] = "historical_only"', "pass",
     "CreatePerson.test_a_former_name_is_the_same_person_and_not_for_casual_use"),
    ("copy the narrator's words into a captured story", W,
     'if coll == "stories" and v.get("origin") == "captured" and v.get("body") is not None:',
     "if False:",
     None),  # guarded twice: 0063's CHECK refuses a body on a captured story
    ("accept another narrator's story candidate", W,
     'if cand is None or cand["narrator_id"] != self.nid:', "if cand is None:",
     None),  # guarded twice: rules.py's story rule reads `_storyCandidates`
    ("BOTH layers accept another narrator's candidate",
     [(W, 'if cand is None or cand["narrator_id"] != self.nid:', "if cand is None:"),
      (S, '"SELECT id FROM story_candidates WHERE narrator_id = ?", (narrator_id,))]',
          '"SELECT id FROM story_candidates")]')],
     "StoriesKeepTheNarratorsWords.test_another_narrators_candidate_is_refused"),

    ("let a superseded assertion be accepted", W,
     'if a["status"] in ("rejected", "superseded"):', "if False:",
     "ConflictAcceptCorrect.test_a_superseded_account_cannot_be_accepted"),
    ("do not record previous values in the audit", W,
     'applied.append({"op": ch.get("op"), "path": path, "previous": prev,',
     'applied.append({"op": ch.get("op"), "path": path, "previous": None,',
     "RevisionAudit.test_every_write_is_audited_with_previous_values"),
    ("a read creates the record", S,
     "    if rec is None:\n        return bio",
     "    if rec is None:\n        con.execute('INSERT INTO lr_record(narrator_id, narrator_person_id,"
     " revision, schema_version, created_at, updated_at) VALUES (?,?,0,1,\"\",\"\")',"
     " (narrator_id, narrator_id)); con.commit()\n        return bio",
     "ReadWritesNothing.test_get_of_a_narrator_with_no_record_writes_nothing"),
    ("guess between two live accounts", S,
     "    return live[0] if len(live) == 1 else None", "    return live[0] if live else None",
     "ConflictAcceptCorrect.test_two_conflicting_dobs_coexist_and_nothing_is_chosen"),
    ("drop the superseded account from the assembly", S,
     "        by_subject.setdefault((r[\"subject_type\"], r[\"subject_id\"]), {})",
     "        if r['status'] == 'superseded': continue\n"
     "        by_subject.setdefault((r[\"subject_type\"], r[\"subject_id\"]), {})",
     "ConflictAcceptCorrect.test_a_later_correction_supersedes_and_keeps_history"),
    ("unknown life status reads as living", S,
     "        # Reported counts (",
     "        person.setdefault('lifeStatus', {'value': 'explicitly_living'})\n"
     "        # Reported counts (",
     "LifeStatus.test_living_deceased_and_unknown"),

    # ── B-4: the graph revision guard ──────────────────────────────────
    ("a full replacement ignores the revision", D,
     "if expected_revision is None or int(expected_revision) != current:", "if False:",
     "RevisionGuard.test_a_stale_full_replacement_is_refused_and_writes_nothing"),
    ("an incremental person write does not bump", D,
     "        graph_bump_revision(con, narrator_id)\n        con.commit()\n        return {\n"
     "            \"id\": pid,",
     "        con.commit()\n        return {\n            \"id\": pid,",
     "RevisionGuard.test_get_returns_a_revision_and_every_writer_bumps_it"),
    ("GET reports no revision", D,
     "        \"revision\": revision,", "        \"revision\": 0,",
     "RevisionGuard.test_revisions_are_per_narrator"),
    # ── B-4: projected rows are the record's, not the route's ─────────
    ("a projected row may be edited through the graph", D,
     "            diff = [k for k in content if str(p.get(k) or \"\") != str(s[k] or \"\")]",
     "            diff = []",
     "ProjectedRowsAreNotEditableHere.test_editing_a_projected_person_is_refused"),
    ("a projected row may be dropped through the graph", D,
     "    if missing:\n        raise GraphWriteRefused", "    if False:\n        raise GraphWriteRefused",
     "ProjectedRowsAreNotEditableHere.test_dropping_a_projected_row_is_refused"),
    ("the graph routes may write another narrator's row", D,
     "    if narrator_id is not None and row[\"narrator_id\"] != narrator_id:",
     "    if False:",
     "GraphNarratorIsolation.test_another_narrators_node_cannot_be_overwritten_or_linked"),
    ("the incremental routes may touch projected rows", D,
     "    if row[\"source\"] == GRAPH_PROJECTION_SOURCE:\n        raise",
     "    if False:\n        raise",
     None),  # guarded twice: projected ids carry the reserved `lr:` prefix
    ("drop the reserved lr: prefix guard", D,
     "    if str(row_id).startswith(GRAPH_PROJECTION_ID_PREFIX):",
     "    if False:",
     None),  # the source guard still refuses — reported
    ("BOTH layers let the routes touch projected rows", D,
     "    if str(row_id).startswith(GRAPH_PROJECTION_ID_PREFIX):\n"
     "        raise GraphWriteRefused(f\"{GRAPH_PROJECTION_ID_PREFIX!r} ids are minted only by the \"\n"
     "                                \"Life Record projection\")\n"
     "    row = con.execute(f\"SELECT narrator_id, source FROM {table} WHERE id=?\", (row_id,)).fetchone()\n"
     "    if row is None:\n        return None\n"
     "    if narrator_id is not None and row[\"narrator_id\"] != narrator_id:\n"
     "        raise GraphWriteRefused(f\"{row_id!r} belongs to another narrator\")\n"
     "    if row[\"source\"] == GRAPH_PROJECTION_SOURCE:\n        raise",
     "    row = con.execute(f\"SELECT narrator_id, source FROM {table} WHERE id=?\", (row_id,)).fetchone()\n"
     "    if row is None:\n        return None\n"
     "    if narrator_id is not None and row[\"narrator_id\"] != narrator_id:\n"
     "        raise GraphWriteRefused(f\"{row_id!r} belongs to another narrator\")\n"
     "    if False:\n        raise",
     "ProjectedRowsAreNotEditableHere.test_incremental_routes_cannot_touch_projected_rows"),
    # ── B-4: the graph is a projection of the record ──────────────────
    ("the writer stops re-projecting the graph", W,
     "            graph_rev = _graph.project_graph(con, _store.assemble(con, narrator_id))",
     "            graph_rev = None",
     "ProjectionAgreesWithTheRecord.test_the_projected_values_are_the_records_values"),
    ("the projection shows a former name", G,
     "    if pref is not None and pref.get(\"use\") not in _HIDDEN_USES:",
     "    for n in names:\n        return n\n    if pref is not None:",
     "ProjectionAgreesWithTheRecord.test_a_former_name_never_becomes_the_display_name"),
    ("the projection normalizes the date as said", G,
     "(birth.get(\"date\") or {}).get(\"text\")", "(birth.get(\"date\") or {}).get(\"value\")",
     "ProjectionAgreesWithTheRecord.test_the_projected_values_are_the_records_values"),
    ("the projection keeps rows the record removed", G,
     "        if r[\"id\"] not in want_r:\n            con.execute",
     "        if False:\n            con.execute",
     "ProjectionAgreesWithTheRecord.test_a_correction_and_a_removal_reach_the_graph"),
    ("the projection deletes and re-inserts persons", G,
     "    for p in rows[\"persons\"]:\n        con.execute(",
     "    for p in rows[\"persons\"]:\n        con.execute('DELETE FROM graph_persons WHERE id=?', (p['id'],))\n"
     "        con.execute(",
     "ProjectionAgreesWithTheRecord.test_a_ui_edge_to_a_projected_person_survives_reprojection"),
]


def _source(mod):
    with open(mod.__file__, encoding="utf-8") as f:
        return f.read()


def _run():
    suite = unittest.defaultTestLoader.loadTestsFromNames(TESTS)
    res = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    red = set()
    for t, _ in res.failures + res.errors:
        tid = t.id()
        for mod in TESTS:
            tid = tid.split(mod + ".")[-1]
        red.add(tid)
    return res.testsRun, red


def _function_holding(src, anchor):
    """(name, source) of the top-level def whose body holds `anchor`."""
    line = src[:src.index(anchor)].count("\n") + 1
    lines = src.splitlines(keepends=True)
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.lineno <= line <= node.end_lineno:
            start = min([node.lineno] + [d.lineno for d in node.decorator_list]) - 1
            return node.name, "".join(lines[start:node.end_lineno])
    raise LookupError(f"anchor is not inside a top-level function: {anchor[:40]!r}")


def _install(mod, original_src, find, repl, saved):
    if mod in FUNCTION_LEVEL:
        name, fsrc = _function_holding(original_src, find)
        saved.setdefault((mod, name), getattr(mod, name))
        exec(compile(fsrc.replace(find, repl), mod.__file__, "exec"), mod.__dict__)
    else:
        saved.setdefault((mod, None), True)
        return original_src.replace(find, repl)


def main():
    originals = {m: _source(m) for m in (W, S, G, D)}
    ran, red = _run()
    print(f"baseline: {ran} tests, {len(red)} red")
    if red:
        print("  BASELINE IS RED — fix the code before mutating it:", sorted(red))
        return 1
    ok = True
    print("─" * 78)
    for desc, *edits, must in MUTATIONS:
        # (desc, mod, find, repl, must) — or (desc, [(mod, find, repl), ...], must)
        # to break BOTH layers of a guard that is defended twice.
        edits = edits[0] if len(edits) == 1 else [tuple(edits)]
        if any(originals[m].count(f) != 1 for m, f, _ in edits):
            print(f"  STALE {desc[:60]:<60} anchor not unique")
            ok = False
            continue
        saved, whole = {}, {}
        try:
            for m, f, r in edits:
                out = _install(m, whole.get(m, originals[m]), f, r, saved)
                if out is not None:
                    whole[m] = out
            for m, src in whole.items():
                exec(compile(src, m.__file__, "exec"), m.__dict__)
            _, red = _run()
        finally:
            for (m, name), obj in saved.items():
                if name is None:
                    exec(compile(originals[m], m.__file__, "exec"), m.__dict__)
                else:
                    setattr(m, name, obj)
        if must is None:
            print(f"  info  {desc[:60]:<60} {len(red)} red (defence in depth)")
            continue
        hit = must in red
        ok &= hit
        print(f"  {'ok  ' if hit else 'FAIL'} {desc[:60]:<60} {len(red)} red")
    _, red = _run()
    if red:
        print("  RESTORE FAILED — shipped module not restored:", sorted(red))
        return 1
    print("─" * 78)
    print("  every mutation caught" if ok else "  A MUTATION SURVIVED — a test cannot fail")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
