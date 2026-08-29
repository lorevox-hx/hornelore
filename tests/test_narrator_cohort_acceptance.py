"""The cohort runner's safety properties, pinned before it ever runs live.

    PYTHONPATH=server/code python3 -m unittest tests.test_narrator_cohort_acceptance

── WHY THESE TESTS COME FIRST ────────────────────────────────────────

This instrument creates narrators through the product intake endpoint
and sends them real model turns. Every property below is one that, if it
broke, would either touch data it must never touch or produce a report
that overstates what was proven.

The `--plan` default and the absence of any deletion path are the two
that matter most, and both are asserted over the SOURCE as well as by
behaviour — a deletion path could be added later without any test
noticing, unless a test is looking for it.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RUNNER = _REPO_ROOT / "scripts" / "run_narrator_cohort_acceptance.py"
for _p in (str(_REPO_ROOT), str(_REPO_ROOT / "server" / "code")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _load():
    """Import the runner by path.

    Registered in `sys.modules` BEFORE `exec_module`, because
    `@dataclass` resolves its own module through
    `sys.modules[cls.__module__]` and raises an opaque
    `AttributeError: 'NoneType' has no attribute '__dict__'` when the
    entry is missing.
    """
    spec = importlib.util.spec_from_file_location("cohort_runner", _RUNNER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cohort_runner"] = mod
    spec.loader.exec_module(mod)
    return mod


COHORT = _load()
SOURCE = _RUNNER.read_text(encoding="utf-8")


def _executable_source() -> str:
    """The runner's CODE, with docstrings removed.

    ── WHY NOT A RAW TEXT SCAN, 2026-08-29 ─────────────────────────────

    *(It was one, and it failed on the runner's own documentation: the
    module docstring explains WHY `--keep-run` and `runtime71` are
    excluded, and a substring search cannot tell an explanation from a
    call. Four tests failed while the code was correct.*

    *A guard that punishes a file for documenting itself teaches people
    to delete the documentation. The property is "no deletion path in
    the executable code", so the scan reads the AST and drops every
    docstring.)*
    """
    tree = ast.parse(SOURCE)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                # A body whose ONLY statement is the docstring becomes an
                # empty block, which `ast.unparse` emits as `def f():`
                # with nothing under it — and that will not re-parse.
                if len(body) == 1:
                    body[0] = ast.Pass()
                else:
                    body.pop(0)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


EXEC_SOURCE = _executable_source()


class SafetyRefusalTests(unittest.TestCase):
    """Who may receive a turn, and who may never."""

    def test_a_family_narrator_is_REFUSED(self):
        for person in (
            {"id": "x", "display_name": "Kent James Horne"},
            {"id": "y", "display_name": "Janice Josephine (Zarr) Horne",
             "testing_only": False},
            {"id": "z", "display_name": "Christopher Todd Horne",
             "narrator_type": "live"},
        ):
            with self.subTest(name=person["display_name"]):
                with self.assertRaises(COHORT.CohortRefusal):
                    COHORT.assert_synthetic(person)

    def test_a_testing_only_narrator_is_accepted(self):
        COHORT.assert_synthetic({"id": "a", "display_name": "ZZ COHORT r1 · Alex",
                                 "testing_only": True})

    def test_a_reference_narrator_is_accepted(self):
        COHORT.assert_synthetic({"id": "b", "display_name": "William Shatner",
                                 "narrator_type": "reference"})

    def test_an_unnamed_person_is_refused(self):
        with self.assertRaises(COHORT.CohortRefusal):
            COHORT.assert_synthetic({"id": "c", "display_name": "  "})

    def test_the_guard_is_not_vacuous(self):
        """It must reject something, or it is decoration."""
        with self.assertRaises(COHORT.CohortRefusal):
            COHORT.assert_synthetic({"id": "d", "display_name": "Somebody Real"})


class ExclusionTests(unittest.TestCase):
    """Jake and the writable Shatner fixture, with their reasons."""

    def test_jake_is_excluded_and_is_not_in_the_cohort(self):
        self.assertIn("run_jake_long_narration_harness", COHORT.EXCLUSIONS)
        self.assertNotIn("run_jake_long_narration_harness",
                         COHORT.COHORT_HARNESSES)
        reason = COHORT.EXCLUSIONS["run_jake_long_narration_harness"].lower()
        self.assertIn("kent", reason)
        self.assertIn("testing_only", reason)

    def test_jake_really_does_declare_testing_only_False(self):
        """The exclusion's stated evidence, verified against the file.

        An exclusion justified by a claim nobody checks is a rumour. If
        the fixture is ever corrected, this fails and the reason must be
        rewritten rather than left standing.
        """
        jake = (_REPO_ROOT / "scripts"
                / "run_jake_long_narration_harness.py").read_text(encoding="utf-8")
        self.assertIn('"testing_only": False', jake)

    def test_the_writable_shatner_harness_is_excluded(self):
        self.assertIn("run_shatner_long_narration_harness", COHORT.EXCLUSIONS)
        self.assertNotIn("run_shatner_long_narration_harness",
                         COHORT.COHORT_HARNESSES)

    def test_shatner_and_dolly_are_reference_only(self):
        self.assertIn("William Shatner", COHORT.REFERENCE_PERSONAS)
        self.assertIn("Dolly Parton", COHORT.REFERENCE_PERSONAS)
        for name in COHORT.REFERENCE_PERSONAS:
            self.assertNotIn(name, COHORT.COHORT_HARNESSES.values())

    def test_no_family_surname_appears_in_the_cohort(self):
        for label in COHORT.COHORT_HARNESSES.values():
            with self.subTest(label=label):
                self.assertNotIn("Horne", label)


class NoDeletionTests(unittest.TestCase):
    """The property that protects preserved evidence.

    ── A DELETION PATH IS A CALL, NOT A WORD, 2026-08-29 ───────────────

    *(This scanned raw source text and failed three times on the
    runner's own writing: the module docstring explains why `--keep-run`
    is excluded, and the EXCLUSIONS dict records "auto-deletes ... unless
    --keep-run" as a REASON. Both are the file documenting a prohibition,
    and a guard that cannot tell a prohibition from a violation forces
    you to delete the explanation to get green.*

    *So the scan walks the AST for deletion OPERATIONS — call targets,
    attribute names, and any HTTP method argument of "DELETE". String
    constants are excluded on purpose: they cannot delete anything.)*
    """

    DELETION_CALLS = {"hard_delete", "hard_delete_person", "erase_person",
                      "erase", "delete", "rmtree", "remove", "unlink",
                      "rmdir", "drop"}

    @staticmethod
    def _call_names(tree):
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                n = getattr(f, "id", None) or getattr(f, "attr", None)
                if n:
                    names.add(n)
        return names

    @staticmethod
    def _http_methods(tree):
        methods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "method" and isinstance(kw.value, ast.Constant):
                        methods.add(str(kw.value.value).upper())
        return methods

    def setUp(self):
        self.tree = ast.parse(SOURCE)

    def test_the_runner_calls_no_deletion_operation(self):
        called = self._call_names(self.tree)
        offenders = sorted(called & self.DELETION_CALLS)
        self.assertEqual(
            offenders, [],
            f"the cohort runner calls {offenders}. It must never delete: "
            "preserved narrators are evidence, and erasure needs Chris's "
            "explicit authorization through the product path.")

    def test_the_runner_issues_no_DELETE_request(self):
        self.assertNotIn("DELETE", self._http_methods(self.tree))

    def test_the_runner_has_no_keep_run_style_autocleanup_flag(self):
        """`--keep-run` implies deletion is the default. It must not exist
        as an ARGUMENT here — mentioning it as an exclusion reason is
        fine and is what the older harness did wrong."""
        added = set()
        for node in ast.walk(self.tree):
            if (isinstance(node, ast.Call)
                    and getattr(node.func, "attr", None) == "add_argument"):
                for a in node.args:
                    if isinstance(a, ast.Constant) and isinstance(a.value, str):
                        added.add(a.value)
        self.assertNotIn("--keep-run", added)
        self.assertNotIn("--cleanup", added)
        self.assertNotIn("--delete", added)

    def test_the_erasure_manifest_is_informational_only(self):
        """Asserted on the VALUE the runner writes, not on its source.

        The source wraps the sentence across string literals, so a
        substring search of the file finds quote characters in the
        middle of it — testing the formatting rather than the promise.
        """
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            led = COHORT.Ledger(Path(td), "r1")
            led.add_person("uuid-1", "ZZ COHORT r1 · Alex", "src")
            led.write_erasure_manifest()
            man = json.loads((Path(td) / "erasure-manifest.json").read_text())
        self.assertTrue(man["authorization_required"])
        self.assertIn("no deletion code path", man["how"])
        self.assertIn("authorization", man["how"].lower())

    def test_the_scan_CATCHES_a_real_deletion_and_ignores_a_mention(self):
        """Positive control, both directions."""
        real = ast.parse("def cleanup(pid):\n    hard_delete(pid)\n")
        self.assertIn("hard_delete", self._call_names(real))
        mention = ast.parse('REASON = "auto-deletes unless --keep-run"\n')
        self.assertEqual(self._call_names(mention) & self.DELETION_CALLS, set(),
                         "documenting a prohibition tripped the guard")
        req = ast.parse('urlopen(Request(u, method="DELETE"))\n')
        self.assertIn("DELETE", self._http_methods(req))


class PlanIsTheDefaultTests(unittest.TestCase):
    """A mistyped command inspects; it does not create.

    `main()` prints the plan, which is right for an operator and wrong
    for a test suite — an unreadable run is one people stop reading.
    Captured here rather than silenced in the runner.
    """

    def _run(self, argv):
        import contextlib, io
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = COHORT.main(argv)
        return rc, out.getvalue(), err.getvalue()

    def test_no_arguments_produces_a_plan_and_exits_zero(self):
        rc, out, _ = self._run([])
        self.assertEqual(rc, 0)
        self.assertIn("NONE", json.loads(out)["writes"])

    def test_quick_without_live_REFUSES(self):
        rc, _, err = self._run(["--quick"])
        self.assertEqual(rc, 2)
        self.assertIn("nothing was written", err)

    def test_full_without_live_REFUSES(self):
        self.assertEqual(self._run(["--full"])[0], 2)

    def test_live_lanes_are_not_enabled_in_this_commit(self):
        """The instrument lands before the run, deliberately."""
        rc, _, err = self._run(["--quick", "--live"])
        self.assertEqual(rc, 3)
        self.assertIn("not enabled", err)

    def test_plan_declares_that_it_writes_nothing(self):
        plan = COHORT.build_plan()
        self.assertIn("NONE", plan["writes"])


class FixtureReuseTests(unittest.TestCase):
    """Biographies are imported, never copied."""

    def test_no_persona_biography_is_embedded_in_the_runner(self):
        """The runner must stay a runner.

        A chapter is hundreds of words of narration. If one has been
        pasted in here, the fixture and the copy will drift and the run
        will score the copy.
        """
        longest = max((len(n.value) for n in ast.walk(ast.parse(EXEC_SOURCE))
                       if isinstance(n, ast.Constant)
                       and isinstance(n.value, str)), default=0)
        self.assertLess(
            longest, 1200,
            "a very long string literal appeared in the cohort runner — "
            "narration belongs in its harness fixture, not here")

    def test_every_cohort_harness_exists_and_builds_a_config(self):
        for stem in COHORT.COHORT_HARNESSES:
            with self.subTest(stem=stem):
                cfg, err = COHORT.load_harness_config(stem)
                self.assertIsNone(err, f"{stem}: {err}")
                self.assertTrue(getattr(cfg, "chapters", None),
                                f"{stem} declares no chapters")

    def test_every_cohort_narrator_is_testing_only(self):
        for stem in COHORT.COHORT_HARNESSES:
            with self.subTest(stem=stem):
                cfg, err = COHORT.load_harness_config(stem)
                self.assertIsNone(err)
                self.assertTrue(
                    COHORT.intake_is_testing_only(cfg),
                    f"{stem} would create a narrator that is not testing_only")

    def test_identity_drift_is_detected_but_decoration_is_not(self):
        same = COHORT._same_identity
        self.assertTrue(same("Alex Eunseo Park (they/them)", "Alex Eunseo Park"))
        self.assertTrue(same("Tomasita Reyes Cantú (Hispano)", "Tomasita Cantu"))
        self.assertFalse(same("Kent James Horne", "Alex Eunseo Park"))
        self.assertFalse(same("", "Alex Eunseo Park"))


class ReferenceAndDenominatorTests(unittest.TestCase):
    """A missing reference is not_applicable, and never shrinks the total."""

    def test_all_five_outcomes_are_counted(self):
        r = COHORT.LaneResult(lane="ui", persona="p")
        r.passed, r.failed, r.not_applicable, r.skipped, r.unverified = 3, 1, 2, 1, 1
        self.assertEqual(r.denominator, 8)

    def test_a_not_applicable_reference_still_counts(self):
        with_ref = COHORT.LaneResult(lane="extraction", persona="p")
        with_ref.passed, with_ref.not_applicable = 4, 2
        without = COHORT.LaneResult(lane="extraction", persona="p")
        without.passed = 4
        self.assertNotEqual(
            with_ref.denominator, without.denominator,
            "an absent reference vanished from the denominator, which is how "
            "a run reports 4/4 while testing six things")

    def test_the_plan_lists_references_even_when_absent(self):
        plan = COHORT.build_plan()
        for name in COHORT.REFERENCE_PERSONAS:
            self.assertIn(name, plan["reference_personas"])


class LedgerTests(unittest.TestCase):
    """A UUID is recorded before the narrator is used for anything."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_the_ledger_file_exists_before_any_person_is_added(self):
        COHORT.Ledger(self.dir, "r1")
        self.assertTrue((self.dir / "artifacts.json").exists(),
                        "a crash before the first flush would leave no "
                        "inventory at all")

    def test_a_person_is_flushed_to_disk_immediately(self):
        led = COHORT.Ledger(self.dir, "r1")
        led.add_person("uuid-1", "ZZ COHORT r1 · Alex", "alex_harness")
        on_disk = json.loads((self.dir / "artifacts.json").read_text())
        self.assertEqual(on_disk["people"][0]["person_id"], "uuid-1",
                         "the UUID was not on disk immediately after creation")

    def test_the_erasure_manifest_carries_ids_and_requires_authorization(self):
        led = COHORT.Ledger(self.dir, "r1")
        led.add_person("uuid-1", "ZZ COHORT r1 · Alex", "alex_harness")
        led.write_erasure_manifest()
        man = json.loads((self.dir / "erasure-manifest.json").read_text())
        self.assertEqual(man["person_ids"], ["uuid-1"])
        self.assertTrue(man["authorization_required"])

    def test_the_run_prefix_is_unmistakable_and_carries_the_run_id(self):
        p = COHORT.run_prefix("abc123")
        self.assertIn("abc123", p)
        self.assertTrue(p.startswith("ZZ "))


class ResumeTests(unittest.TestCase):
    """A resume repeats no completed model turn."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_a_completed_lane_is_not_repeated(self):
        cp = COHORT.Checkpoint(self.dir)
        self.assertFalse(cp.is_done("Alex", "conversation"))
        cp.mark("Alex", "conversation", {"passed": 3})
        self.assertTrue(cp.is_done("Alex", "conversation"))

    def test_the_checkpoint_survives_a_restart(self):
        COHORT.Checkpoint(self.dir).mark("Alex", "era", {"passed": 7})
        self.assertTrue(COHORT.Checkpoint(self.dir).is_done("Alex", "era"),
                        "a timeout would restart the whole cohort")

    def test_lanes_are_scoped_per_persona(self):
        cp = COHORT.Checkpoint(self.dir)
        cp.mark("Alex", "conversation", {})
        self.assertFalse(cp.is_done("John Baldy", "conversation"),
                         "one persona's completion marked another's done")


class ProfileSeedCompatibilityTests(unittest.TestCase):
    """Onboarding is paused through the server, never forged client-side."""

    def test_the_runner_never_forges_runtime_or_attestation(self):
        tree = ast.parse(SOURCE)
        # Assignment TARGETS and dict KEYS — the shapes a forgery takes.
        written = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for k in node.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        written.add(k.value)
            if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
                if isinstance(node.slice.value, str):
                    written.add(node.slice.value)
        for token in ("profile_seed_server_attested",
                      "profile_seed_onboarding", "runtime71"):
            with self.subTest(token=token):
                self.assertNotIn(
                    token, written,
                    f"the runner WRITES {token!r}. Onboarding must be paused "
                    "through the versioned product endpoint; forging client "
                    "runtime would test a state no narrator can reach.")

    def test_the_pause_requirement_is_documented_in_the_runner(self):
        self.assertIn("ENROLLS", SOURCE)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
