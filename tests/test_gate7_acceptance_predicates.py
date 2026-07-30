"""WO-TRUTH-PIPELINE-01 Phase 2 — the acceptance driver's own predicates.

WHY THIS FILE EXISTS. On 2026-07-30 the live Phase 2 run produced this:

    -- Test C -- forced extraction failure: FAIL
       raw_turn_saved=1  archive_event_created=2  extract_fields_called=1
       family_truth_written=0  projection_updated=0
       ! projection_unchanged: probe projection_updated=0; version delta 0

Every number in that failure is a passing value. The system under test
did exactly what Phase 2 requires; the ASSERTION was wrong. It read:

    counts.get("projection_updated", 0) == 0
    and rec["db_delta"].get("projection_version") is None

`_delta` in the acceptance script omits a key whose value is equal and
non-numeric on both sides, and returns an integer difference when both
sides are numeric. Before the disposable narrator owned an
`interview_projections` row, "unchanged" and "absent" were the same
state and the key was absent, so `is None` happened to be right. Once
Phase 1 Test D began writing a real projection for that same narrator,
"unchanged" started arriving as the integer 0, and `0 is None` is False.
The check inverted the moment its fixture got more realistic.

This file exists so that predicate is exercised by something other than
a ten-second live run against a GPU model. It tests the real function,
not a copy: `projection_is_unchanged` was extracted from inside `test_c`
precisely so it could be called here, and one test below reads the AST
to confirm `test_c` still calls it rather than re-inlining an
expression that could drift again.

WHY THE SCRIPT IS LOADED BY PATH. scripts/gate7_phase2_acceptance.py is
a runnable driver, not an importable package member, and `scripts/` has
no `__init__.py`. It is loaded through importlib from its path. Module
import is side-effect-free: it reads DATA_DIR and DB_NAME out of .env
and imports `requests`, but it opens no database, sends no request, and
writes no file until a function is called.
"""
from __future__ import annotations

import ast
import importlib.util
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "gate7_phase2_acceptance.py"


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "gate7_phase2_acceptance_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before exec so any dataclass or annotation resolution
    # inside the module can find its own module object.
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_SCRIPT_MODULE = _load_script()


class DeltaIsZeroTest(unittest.TestCase):
    """`_delta_is_zero` must read `_delta`'s three encodings correctly."""

    def setUp(self) -> None:
        self.fn = _SCRIPT_MODULE._delta_is_zero

    def test_an_absent_key_is_unchanged(self) -> None:
        # `_delta` drops keys whose values matched and were not ints.
        # For projection_version that is "no row before, no row now".
        self.assertTrue(self.fn({}, "projection_version"))
        self.assertTrue(self.fn({"turns": 2}, "projection_version"))

    def test_an_integer_zero_is_unchanged(self) -> None:
        # THE REGRESSION. This is the exact value that failed the live
        # run on 2026-07-30 while the detail line said "version delta 0".
        self.assertTrue(self.fn({"projection_version": 0},
                                "projection_version"))
        self.assertTrue(self.fn({"interview_projections": 0},
                                "interview_projections"))

    def test_any_nonzero_integer_is_changed(self) -> None:
        for value in (1, 2, -1):
            with self.subTest(value=value):
                self.assertFalse(
                    self.fn({"projection_version": value},
                            "projection_version"))

    def test_a_string_transition_is_changed_and_never_read_as_zero(self) -> None:
        # This is what `_delta` produces when a projection comes into
        # existence during the test: pre None, post 1. Test D in Phase 1
        # recorded exactly this string.
        self.assertFalse(
            self.fn({"projection_version": "None -> 1"},
                    "projection_version"))
        self.assertFalse(
            self.fn({"projection_updated_at": "'' -> '2026-07-30T13:31:54'"},
                    "projection_updated_at"))

    def test_a_boolean_is_not_accepted_as_a_numeric_zero(self) -> None:
        # bool is a subclass of int in Python, so False would otherwise
        # sneak through `isinstance(value, int) and value == 0`.
        self.assertFalse(self.fn({"projection_version": False},
                                 "projection_version"))
        self.assertFalse(self.fn({"projection_version": True},
                                 "projection_version"))

    def test_none_stored_under_the_key_is_not_a_zero(self) -> None:
        # A stored None means the measurement itself failed --- the
        # acceptance script keeps None and 0 distinct on purpose.
        self.assertFalse(self.fn({"projection_version": None},
                                 "projection_version"))


class ProjectionIsUnchangedTest(unittest.TestCase):
    """The predicate `test_c` actually asserts."""

    def setUp(self) -> None:
        self.fn = _SCRIPT_MODULE.projection_is_unchanged

    def _delta(self, **over):
        base = {
            "family_truth_notes": 0, "family_truth_rows": 0,
            "interview_projections": 0, "media_archive_items": 0,
            "people": 0, "photos": 0, "profiles": 0,
            "projection_version": 0, "story_candidates": 1,
            "turn_extraction_ledger": 1, "turns": 2,
        }
        base.update(over)
        return base

    def test_the_live_test_c_evidence_of_2026_07_30_passes(self) -> None:
        """The positive control, copied from the failing run's evidence.

        gate7_phase2_evidence_phase2.json, narrator
        harness-test-gate7p2-622fbd58. probe projection_updated=0,
        interview_projections delta 0, projection_version delta 0. The
        old predicate scored this FAIL.
        """
        counts = {
            "raw_turn_saved": 1, "archive_event_created": 2,
            "extract_fields_called": 1, "family_truth_written": 0,
            "projection_updated": 0,
        }
        self.assertTrue(self.fn(counts, self._delta()))

    def test_it_still_passes_when_the_narrator_never_had_a_projection(self) -> None:
        # The pre-fixture world: `_delta` omits the key entirely.
        delta = self._delta()
        delta.pop("projection_version")
        delta.pop("interview_projections")
        self.assertTrue(self.fn({"projection_updated": 0}, delta))

    def test_a_probe_stage_of_one_fails(self) -> None:
        self.assertFalse(self.fn({"projection_updated": 1}, self._delta()))

    def test_a_new_projection_row_fails(self) -> None:
        self.assertFalse(self.fn({"projection_updated": 0},
                                 self._delta(interview_projections=1)))

    def test_a_bumped_projection_version_fails(self) -> None:
        # Same row count, rewritten in place. This is the case the row
        # count alone cannot see.
        self.assertFalse(self.fn({"projection_updated": 0},
                                 self._delta(projection_version=1)))

    def test_a_projection_coming_into_existence_fails(self) -> None:
        # `_delta`'s string form, which truthiness would have scored as
        # "changed" by accident and `is None` as "unchanged" by accident.
        self.assertFalse(self.fn(
            {"projection_updated": 0},
            self._delta(projection_version="None -> 1",
                        interview_projections=1)))

    def test_a_missing_probe_stage_is_treated_as_zero(self) -> None:
        # An absent stage key means the probe did not record a
        # projection update; the two db measurements still have to hold.
        self.assertTrue(self.fn({}, self._delta()))
        self.assertFalse(self.fn({}, self._delta(projection_version=1)))


class PredicateWiringTest(unittest.TestCase):
    """`test_c` must call the predicate, not re-inline one.

    Read from the AST with docstrings and comments excluded, so the
    quoted retired expression in `_delta_is_zero`'s docstring cannot
    satisfy or break this test.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.tree = ast.parse(_SCRIPT.read_text(encoding="utf-8"))

    def _function(self, name: str) -> ast.FunctionDef:
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        self.fail(f"{name} is no longer defined in {_SCRIPT.name}")

    def _called_names(self, node: ast.AST) -> set:
        names = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                func = sub.func
                if isinstance(func, ast.Name):
                    names.add(func.id)
                elif isinstance(func, ast.Attribute):
                    names.add(func.attr)
        return names

    def test_test_c_asserts_through_the_named_predicate(self) -> None:
        called = self._called_names(self._function("test_c"))
        self.assertIn(
            "projection_is_unchanged", called,
            "test_c stopped calling projection_is_unchanged. An inlined "
            "expression is how the 2026-07-30 contradiction survived: it "
            "was evaluated only by a live run against a GPU model.")

    def test_the_predicate_compares_against_zero_explicitly(self) -> None:
        fn = self._function("projection_is_unchanged")
        compares = [n for n in ast.walk(fn) if isinstance(n, ast.Compare)]
        self.assertTrue(
            any(isinstance(c.comparators[0], ast.Constant)
                and c.comparators[0].value == 0
                and isinstance(c.ops[0], ast.Eq)
                for c in compares),
            "projection_is_unchanged must compare the probe stage to 0 "
            "with ==. Zero is the value this check REQUIRES, so any "
            "truthiness test inverts it.")

    def test_the_predicate_reads_all_three_measurements(self) -> None:
        fn = self._function("projection_is_unchanged")
        literals = {n.value for n in ast.walk(fn)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        # Drop the docstring; it is the first statement of the body.
        doc = ast.get_docstring(fn)
        literals.discard(doc)
        for key in ("projection_updated", "interview_projections",
                    "projection_version"):
            with self.subTest(key=key):
                self.assertIn(
                    key, literals,
                    f"{key} is no longer one of the three measurements. "
                    "The probe stage says whether the turn ASKED, the row "
                    "count says whether a projection APPEARED, and the "
                    "version says whether one was REWRITTEN in place. "
                    "Dropping any one of them leaves a way to change a "
                    "projection without this check noticing.")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
