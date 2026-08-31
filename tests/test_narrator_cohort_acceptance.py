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
import re
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
    """Who may receive a turn, and who may never.

    ── `assert_synthetic` WAS REMOVED, AND SO WERE ITS TESTS ──────────

    *(Five tests here asserted that a person whose row lacks
    `testing_only: True` is refused. They passed against hand-written
    dicts and described a product row that does not exist: `testing_only`
    is not a column, `create_person` takes no such argument, and intake
    writes `narrator_type="live"`. The guard would therefore have refused
    the cohort's own narrators the moment it met a real one.*

    *Tests that pass only because their fixtures are more convenient than
    the product are worse than no tests — they report a guard as working
    when it cannot work. Replaced by `DurableAuthorityTests`, which
    asserts the journal-based authority AND checks the product source for
    the facts the old tests assumed.)*
    """

    def test_the_removed_guard_has_not_come_back(self):
        self.assertFalse(
            hasattr(COHORT, "assert_synthetic"),
            "assert_synthetic is back. Its premise — that a field on the "
            "product row proves synthetic status — is false; use "
            "Ledger.require_journaled.")

    def test_the_journal_refuses_a_family_narrator_by_absence(self):
        """Kent is refused because this run did not create him."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            ledger = COHORT.Ledger(Path(tmp), "r-safety")
            with self.assertRaises(COHORT.CohortRefusal):
                ledger.require_journaled("4aa0cc2b-1f27-433a-9152-203bb1f69a55")

    def test_the_journal_guard_is_not_vacuous(self):
        """It must accept something too, or it refuses everything."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            ledger = COHORT.Ledger(Path(tmp), "r-safety")
            ledger.add_person("aaaa-bbbb", "ZZ COHORT r-safety · Alex", "h1")
            self.assertTrue(ledger.is_journaled("aaaa-bbbb"))
            self.assertFalse(ledger.is_journaled("cccc-dddd"))


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

    def test_full_with_live_is_STILL_closed(self):
        """Quick is wired; the full cohort is not.

        ── SUPERSEDES `test_live_lanes_are_not_enabled_in_this_commit` ──

        *(That test asserted `--quick --live` exits 3 with "not enabled".
        Once the quick run was wired, it did the one thing a test in this
        suite must never do: it called `main(["--quick", "--live"])`, which
        is no longer a refusal but a real run — and it went to the network,
        failing with `Connection refused` only because no stack was up. On
        a developer's machine with the stack running, that test would have
        CREATED NARRATORS.*

        *So the gate it was guarding is re-asserted here against `--full`,
        which is still closed, and the quick path is exercised only through
        `LiveRun` with an injected fake transport. A test must never be one
        running stack away from writing to the product.)*
        """
        rc, _, err = self._run(["--full", "--live"])
        self.assertEqual(rc, 3)
        self.assertIn("--full is not open yet", err)

    def test_no_test_in_this_suite_invokes_a_live_quick_run(self):
        """A guard against re-introducing exactly that mistake."""
        source = Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            args = [a for a in node.args
                    if isinstance(a, (ast.List, ast.Tuple))]
            for arg in args:
                values = [e.value for e in arg.elts
                          if isinstance(e, ast.Constant)
                          and isinstance(e.value, str)]
                if "--live" in values and "--quick" in values:
                    self.fail(
                        "a test passes --quick --live to main(); with a stack "
                        "running that CREATES NARRATORS. Exercise the quick "
                        "path through LiveRun with a fake transport instead.")

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


# ── The browser half ──────────────────────────────────────────────────
#
# Ported from the Codex cohort harness on 2026-08-29. The UI, traveldoc,
# isolation and persistence lanes are all worthless without this file, and
# "the 36 Python tests passed" was true while it was missing — which is
# precisely the shape of a green suite that proves less than it appears to.
class BrowserHelperTests(unittest.TestCase):
    HELPER = _REPO_ROOT / "scripts" / "ui" / "run_narrator_cohort_surfaces.js"

    def test_the_browser_helper_exists(self):
        self.assertTrue(
            self.HELPER.is_file(),
            f"{self.HELPER} is missing. The UI lane has no browser half, so "
            "a passing Python suite would describe an untested surface.")

    def test_the_browser_helper_parses(self):
        """Parsed by node itself, not by a regex that hopes."""
        import shutil
        import subprocess
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not on PATH in this environment")
        proc = subprocess.run(
            [node, "--check", str(self.HELPER)],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(
            proc.returncode, 0,
            f"node --check failed:\n{proc.stderr.strip()}")

    def test_the_runner_knows_where_the_helper_is(self):
        self.assertEqual(COHORT.BROWSER_HELPER.resolve(), self.HELPER.resolve())

    def test_a_missing_helper_becomes_a_reported_problem(self):
        """Absence must be LOUD.

        The plan reports the helper's presence, so a lane that cannot run
        is visible in the report rather than merely absent from it.
        """
        plan = COHORT.build_plan()
        self.assertIn("browser_helper", plan)
        self.assertTrue(plan["browser_helper"]["present"])

    @staticmethod
    def _executable_js() -> str:
        """The helper's CODE, with comments removed.

        ── WHY NOT A RAW TEXT SCAN, 2026-08-29 ─────────────────────────

        *(It was one, and it failed the same way the Python scan did: the
        helper's header comment says it "never clicks coordinates", and a
        substring search cannot tell a promise from a violation. The file
        was correct and the test was wrong.*

        *This is the JavaScript half of the rule already recorded for
        `_executable_source`: the property is "no positional selection in
        the executable code", so the scan drops comments and looks for
        real APIs rather than for English words.)*
        """
        src = BrowserHelperTests.HELPER.read_text(encoding="utf-8")
        src = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)   # block comments
        src = re.sub(r"(?m)^\s*//.*$", "", src)                # line comments
        return src

    def test_the_helper_selects_by_exact_uuid_and_never_by_position(self):
        src = self._executable_js()
        self.assertIn("lv80ConfirmNarratorSwitch", src)
        # An exact 36-character UUID, not a loose prefix match.
        self.assertIn("{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", src)
        # Real positional/pixel APIs, not the English word for them.
        for forbidden in ("mouse.click(", "page.mouse", "boundingBox()",
                          ".nth(", ".first()", ".last()", "elementAt("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(
                    forbidden, src,
                    f"{forbidden!r} resolves a narrator by position or pixel; "
                    "the contract is exact-UUID semantic selection only.")

    def test_the_positional_scan_can_actually_fail(self):
        """Positive control: the scan must not be vacuous.

        A guard that cannot fail proves nothing, so the same check is run
        against source that genuinely does the forbidden thing.
        """
        planted = 'await page.mouse.click(10, 20);\n'
        self.assertIn("page.mouse", planted)
        # ...and the real file does not contain it.
        self.assertNotIn("page.mouse", self._executable_js())

    def test_the_helper_refuses_destructive_actions(self):
        src = self.HELPER.read_text(encoding="utf-8")
        self.assertIn("DESTRUCTIVE", src)
        self.assertIn("REFUSED", src)
        for verb in ("lv80DeleteNarrator", "deleteNarrator", "confirmDelete"):
            with self.subTest(verb=verb):
                self.assertNotIn(verb, src)

    def test_the_helper_cannot_pass_having_walked_no_tab(self):
        """every() over an empty array is true.

        The staged original derived its verdict that way, so a selector
        drift that collected zero tabs would have reported a PASSING ui
        lane having tested nothing. The count is asserted first.
        """
        src = self.HELPER.read_text(encoding="utf-8")
        self.assertIn("nonVacuity", src)
        self.assertIn("MIN_SHELL_TABS", src)
        self.assertIn("tabsClicked", src)

    def test_the_helper_classifies_travel_document_state(self):
        src = self.HELPER.read_text(encoding="utf-8")
        for state in ("populated", "empty", "unavailable", "unknown"):
            with self.subTest(state=state):
                self.assertIn(state, src)
        # `unknown` must not be treated as success.
        self.assertIn('classification !== "unknown"', src)


# ── Ported safeguards ─────────────────────────────────────────────────
class PortedSafeguardTests(unittest.TestCase):

    def test_resume_cannot_broaden_a_quick_run_into_a_full_one(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            cp = COHORT.Checkpoint(Path(tmp))
            cp.set_selection(personas=["Alex", "Walt"], lanes=["ui"],
                             mode="quick")
            # The same selection is fine — that is what a resume is.
            cp.set_selection(personas=["Walt", "Alex"], lanes=["ui"],
                             mode="quick")
            # Widening it is not.
            with self.assertRaises(COHORT.CohortRefusal):
                cp.set_selection(personas=["Alex", "Walt"], lanes=["ui"],
                                 mode="full")
            with self.assertRaises(COHORT.CohortRefusal):
                cp.set_selection(
                    personas=["Alex", "Walt", "John"], lanes=["ui"],
                    mode="quick")

    def test_the_frozen_selection_survives_a_restart(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            COHORT.Checkpoint(Path(tmp)).set_selection(
                personas=["Alex"], lanes=["ui"], mode="quick")
            reopened = COHORT.Checkpoint(Path(tmp))
            self.assertEqual(reopened.selection["mode"], "quick")
            with self.assertRaises(COHORT.CohortRefusal):
                reopened.set_selection(personas=["Alex"], lanes=["ui"],
                                       mode="full")

    def test_containment_reads_the_database_read_only(self):
        """Profile Seed GET is a writing read, so containment cannot use it."""
        self.assertIn("mode=ro", SOURCE)
        snap = COHORT.containment_snapshot(
            [], db_path=Path("/nonexistent/does-not-exist.db"),
            people_rows=["a", "b"])
        self.assertTrue(snap["db_opened_read_only"])
        self.assertEqual(snap["onboarding_probe_errors"], 1)
        # It must state its own limits rather than implying proof it lacks.
        self.assertIn("does_not_prove", snap)

    def test_containment_hashes_only_the_non_run_narrators(self):
        snap = COHORT.containment_snapshot(
            ["b"], db_path=Path("/nonexistent.db"), people_rows=["a", "b", "c"])
        self.assertEqual(snap["count"], 3)
        self.assertEqual(snap["non_run_count"], 2)

    def test_reference_extraction_is_not_applicable_not_skipped(self):
        """The denominator keeps the case; the reason is recorded."""
        self.assertEqual(COHORT.REFERENCE_EXTRACTION_DISPOSITION,
                         "not_applicable")
        self.assertIn("extract-fields", COHORT.REFERENCE_EXTRACTION_REASON)
        self.assertIn("persist", COHORT.REFERENCE_EXTRACTION_REASON)

    def test_the_deletion_inventory_is_a_read_and_nothing_deletes(self):
        path = COHORT.delete_inventory_path("abc-123")
        self.assertEqual(path, "/api/people/abc-123/delete-inventory")
        plan = COHORT.build_plan()
        self.assertEqual(plan["deletion"]["call_sites"], 0)

    def test_denominators_count_every_status_including_the_awkward_ones(self):
        counts = COHORT.summarize_tasks([
            {"status": "pass"}, {"status": "fail"},
            {"status": "not_applicable"}, {"status": "skipped"},
            {"status": "unverified"},
        ])
        self.assertEqual(counts["passed"], 1)
        self.assertEqual(counts["failed"], 1)
        self.assertEqual(counts["not_applicable"], 1)
        self.assertEqual(counts["skipped"], 1)
        self.assertEqual(counts["unverified"], 1)
        self.assertEqual(counts["total"], 5)

    def test_an_unknown_status_is_refused_rather_than_dropped(self):
        with self.assertRaises(COHORT.CohortRefusal):
            COHORT.summarize_tasks([{"status": "mostly_fine"}])

    def test_live_is_still_required_after_the_port(self):
        """The staged harness had no --live gate. Ours keeps it."""
        import contextlib
        import io
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = COHORT.main(["--quick"])
        self.assertEqual(rc, 2, "--quick without --live must refuse")
        self.assertIn("REFUSED", err.getvalue())
        self.assertIn("--live is required", err.getvalue())


# ── The wired live run, exercised offline ─────────────────────────────
class FakeTransport:
    """Every side effect the live run can have, recorded instead of done.

    The point is not to simulate the product. It is to make the ORDER of
    the real run observable without a stack, a model or a browser — and
    to let an interruption be injected at an exact step, which is the
    only way to test that a resume repeats no model turn.
    """

    #: What `GET /api/people/{id}` REALLY returns for an intake-created
    #: narrator: `narrator_type="live"` and NO `testing_only` field.
    #:
    #: This fake used to return `testing_only: True`, which is not a
    #: column in any migration and not a parameter `create_person`
    #: accepts. The kinder fake hid a real refusal — the run would have
    #: created its first narrator and then rejected it. A fake that is
    #: more generous than the product tests something that does not
    #: exist.
    def __init__(self, *, fail_on_turn=None, display_name=None,
                 marker="ZZ COHORT r-test · ", store=None):
        self.calls = []
        self.turns = []
        self.conv_ids = set()
        self.fail_on_turn = fail_on_turn
        self.marker = marker
        self.display_name = display_name
        self._n = 0
        # `store` is the stand-in for the database: pass the SAME dict to
        # a second transport to model a resume, where the rows created by
        # the interrupted attempt are still there to be read back.
        self.created = {} if store is None else store

    def list_people(self):
        self.calls.append("list_people")
        return ["existing-1", "existing-2"]

    def post(self, path, payload):
        self.calls.append(("POST", path))
        assert payload.get("testing_only") is True, \
            "intake must always REQUEST testing_only (a consent behaviour)"
        self._n += 1
        pid = f"11111111-2222-3333-4444-00000000000{self._n}"
        # Record what the product would actually store: the marked
        # display name, narrator_type=live, and NO testing_only field.
        self.created[pid] = {
            "id": pid,
            "display_name": self.display_name or payload.get("preferred_name"),
            "narrator_type": "live",
        }
        return 200, {"person_id": pid}

    def get(self, path):
        self.calls.append(("GET", path))
        if path.startswith("/api/people/") and "delete-inventory" in path:
            return 200, {"photos": 0, "conversations": 1}
        if path.startswith("/api/people/"):
            pid = path.rsplit("/", 1)[-1]
            row = self.created.get(pid) or {
                "id": pid,
                "display_name": self.display_name or f"{self.marker}Someone",
                "narrator_type": "live",
            }
            return 200, {"person": row}
        if path.startswith("/api/interview/profile-seed"):
            return 200, {"enrolled": True, "version": 3, "status": "active",
                         "active_topic_id": "childhood_home",
                         "presentation_epoch": 2,
                         "remaining_topics": ["childhood_home"]}
        if path.startswith("/api/facts/list"):
            return 200, {"facts": [{"field_key": "childhood_home_address"}]}
        return 404, {}

    def patch(self, path, payload):
        self.calls.append(("PATCH", path, payload.get("action")))
        return 200, {"status": "paused", "version": payload["expected_version"] + 1}

    def model_turn(self, *, person_id, text, era, speaker_name, conv_id):
        self.turns.append((person_id, era))
        self.conv_ids.add(conv_id)
        if self.fail_on_turn is not None and len(self.turns) == self.fail_on_turn:
            raise KeyboardInterrupt("simulated interruption mid-run")
        # Mirrors the real transport's envelope. A fake that returned
        # only `text` could not exercise the capture under test.
        reply = f"Lori reflects on {era}."
        return {"text": reply, "chars": len(reply), "event_count": 3,
                "era": era, "era_sent": era,
                "done_event": {"type": "done", "turn_id": f"t-{len(self.turns)}"},
                "ws_errors": []}

    def browser(self, *, person_id, expected_name, ui_url, output, screenshots):
        self.calls.append(("browser", person_id))
        # Mirrors the real transport, which records the string it waited
        # on. Without it this fake could not tell the fixture label from
        # the marked display name — the exact defect under test.
        return {"ok": True, "tabs": [{"tab": "narrator"}],
                "expected_name_used": expected_name,
                "nonVacuity": {"ok": True, "tabsCollected": 6}}


def _two_personas():
    """Two personas whose intake payloads look like REAL ones.

    They previously carried `{"a": 1}`, which has no `preferred_name` for
    the cohort marker to stamp — so the fixtures could not exercise the
    marker check at all. A fixture that omits the field under test is
    another way of testing nothing.
    """
    return [
        {"harness": "h1", "label": "Alex",
         "intake_payload": {"preferred_name": "Alex",
                            "full_legal_name": "Alex Eunseo Park",
                            "date_of_birth": "1962-04-02",
                            "place_of_birth": "Seoul",
                            "pronouns": "they_them",
                            "current_residence": "Portland"},
         "chapters": [type("C", (), {"narrator_text": "t1",
                                     "runtime71_era": "childhood"})(),
                      type("C", (), {"narrator_text": "t2",
                                     "runtime71_era": "today"})()]},
        {"harness": "run_seven_era_walk_harness", "label": "Walt",
         "intake_payload": {"preferred_name": "Walter",
                            "full_legal_name": "Walter O'Donnell",
                            "date_of_birth": "1948-01-11",
                            "place_of_birth": "Boston",
                            "pronouns": "he_him",
                            "current_residence": "Quincy"},
         "chapters": [type("C", (), {"narrator_text": "t3",
                                     "runtime71_era": "building_years"})()]},
    ]


class LiveOrchestrationTests(unittest.TestCase):

    def _run(self, tmp, transport, personas=None, run_id="ZZ-COHORT-test"):
        return COHORT.LiveRun(
            personas=personas or _two_personas(),
            lanes=list(COHORT.LANES), mode="quick",
            out_dir=Path(tmp), transport=transport,
            ui_url="http://localhost:8082/ui/x.html",
            db_path=Path("/nonexistent/none.db"), run_id=run_id)

    def test_the_quick_run_executes_the_declared_order(self):
        """The mocked end-to-end run, asserted step by step."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(tmp, FakeTransport())
            run.execute()
            per_persona = ["create_intake", "journal_uuid", "verify_identity",
                           "profile_seed_resolve", "profile_seed_pause",
                           "model_turns", "era_evidence", "browser_traversal",
                           "delete_inventory_read"]
            expected = (["freeze_selection", "containment_baseline"]
                        + per_persona * 2
                        + ["containment_after", "emit_reports"])
            self.assertEqual(run.trace, expected)

    def test_every_step_in_the_trace_is_a_declared_step(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(tmp, FakeTransport())
            run.execute()
            for step in run.trace:
                self.assertIn(step, COHORT.ORCHESTRATION)

    def test_the_uuid_is_journalled_before_any_later_request(self):
        """A narrator that exists but is not on disk is an orphan."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(tmp, FakeTransport())
            run.execute()
            self.assertLess(run.trace.index("journal_uuid"),
                            run.trace.index("verify_identity"))
            artifacts = json.loads(
                (Path(tmp) / "artifacts.json").read_text(encoding="utf-8"))
            self.assertEqual(len(artifacts["people"]), 2)

    def test_profile_seed_is_paused_through_the_versioned_endpoint(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            t = FakeTransport()
            self._run(tmp, t).execute()
            patches = [c for c in t.calls if c[0] == "PATCH"]
            self.assertEqual(len(patches), 2)
            for call in patches:
                self.assertEqual(call[1], "/api/interview/profile-seed")
                self.assertEqual(call[2], "pause")

    def test_the_pause_precedes_narration_and_traversal(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(tmp, FakeTransport())
            run.execute()
            first_pause = run.trace.index("profile_seed_pause")
            self.assertLess(first_pause, run.trace.index("model_turns"))
            self.assertLess(first_pause, run.trace.index("browser_traversal"))

    def test_model_turns_run_sequentially_in_chapter_order(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            t = FakeTransport()
            self._run(tmp, t).execute()
            self.assertEqual([era for _pid, era in t.turns],
                             ["childhood", "today", "building_years"])

    def test_the_era_lane_reuses_conversation_evidence(self):
        """Seven-era material is never asked twice."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            t = FakeTransport()
            run = self._run(tmp, t)
            report = run.execute()
            walt = next(p for p in report["personas"] if p["persona"] == "Walt")
            self.assertTrue(walt["era"]["reused_from_conversation_lane"])
            # Three chapters total across both personas — no extra era turns.
            self.assertEqual(len(t.turns), 3)

    def test_the_delete_inventory_is_read_and_nothing_is_deleted(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            t = FakeTransport()
            report = self._run(tmp, t).execute()
            reads = [c for c in t.calls
                     if c[0] == "GET" and "delete-inventory" in c[1]]
            self.assertEqual(len(reads), 2)
            self.assertFalse(report["deletion"]["performed"])
            for row in report["personas"]:
                self.assertFalse(row["delete_inventory"]["deleted"])

    def test_the_transport_has_no_deletion_method_at_all(self):
        """The strongest form of "it never deletes"."""
        for name in dir(COHORT.Transport):
            with self.subTest(name=name):
                self.assertNotIn("delete", name.lower().replace(
                    "delete_inventory", ""))

    def test_all_six_artifacts_are_emitted(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self._run(tmp, FakeTransport()).execute()
            for artifact in ("report.json", "report.html", "artifacts.json",
                             "erasure-manifest.json", "checkpoint.json",
                             "containment-before.json"):
                with self.subTest(artifact=artifact):
                    self.assertTrue((Path(tmp) / artifact).is_file(), artifact)

    def test_the_erasure_manifest_authorizes_nothing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self._run(tmp, FakeTransport()).execute()
            manifest = json.loads(
                (Path(tmp) / "erasure-manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["authorization_required"])
            self.assertEqual(len(manifest["person_ids"]), 2)

    def test_the_report_states_what_containment_does_not_prove(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            report = self._run(tmp, FakeTransport()).execute()
            self.assertIn("does_not_prove", report["containment"]["before"])
            html = (Path(tmp) / "report.html").read_text(encoding="utf-8")
            self.assertIn("do <em>not</em> prove", html)

    def test_the_reference_block_is_policy_and_says_so(self):
        """It is not a lane result, and must not read like one.

        ── RENAMED AND STRENGTHENED, 2026-08-30 ───────────────────────

        *(This asserted `reference_personas["extraction"] ==
        "not_applicable"`, sitting beside real per-persona results, which
        reads as a reference lane that ran and returned a disposition.
        No reference persona is opened, read, traversed or extracted from
        anywhere in this runner — there is no reference lane at all. The
        test now pins the honest shape: an explicit `executed: False`,
        with the disposition kept as the standing policy it always was.)*
        """
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            report = self._run(tmp, FakeTransport()).execute()
            block = report["reference_personas"]
            self.assertIs(block["executed"], False)
            self.assertIs(block["policy_only"], True)
            self.assertEqual(block["extraction_policy"], "not_applicable")
            # The old key must not come back: it is the one that made a
            # policy look like a measurement.
            self.assertNotIn("extraction", block)

    def test_unrun_lanes_are_named_in_the_report(self):
        """Coverage is stated, never inferred from an absent complaint."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            report = self._run(tmp, FakeTransport()).execute()
            missing = report["lanes"]["not_implemented"]
            self.assertIn("behavior", missing)
            self.assertIn("extraction", missing)
            for lane in ("behavior", "extraction"):
                self.assertNotIn(lane, report["lanes"]["executed"])
                self.assertNotIn(lane, COHORT.LANES)
            html = (Path(tmp) / "report.html").read_text(encoding="utf-8")
            self.assertIn("Not implemented by this runner", html)

    def test_the_browser_waits_on_the_marked_name_not_the_fixture_label(self):
        """The picker shows `ZZ COHORT <run> · Alex`, never the fixture name.

        The live run's browser lane was handed `persona["label"]` and
        waited 60s for an active-narrator label that could never contain
        it. The row read back in `verify_identity` is the authority.
        """
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            transport = FakeTransport()
            report = self._run(tmp, transport).execute()
            for row in report["personas"]:
                self.assertTrue(
                    row["display_name"].startswith("ZZ COHORT"),
                    f"unmarked display name: {row['display_name']!r}")
                self.assertEqual(row["browser"]["expected_name_used"],
                                 row["display_name"])
                self.assertNotEqual(row["browser"]["expected_name_used"],
                                    row["persona"])

    def test_only_lane_actually_removes_work(self):
        """It was recorded in the frozen selection and then ignored."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(tmp, FakeTransport())
            run.lanes = ["inventory"]
            report = run.execute()
            self.assertNotIn("model_turns", report["orchestration"])
            self.assertNotIn("browser_traversal", report["orchestration"])
            self.assertIn("delete_inventory_read", report["orchestration"])
            for row in report["personas"]:
                self.assertIs(row["conversation"]["executed"], False)
                self.assertIs(row["browser"]["executed"], False)


class DurableAuthorityTests(unittest.TestCase):
    """What actually authorizes touching a narrator.

    ── testing_only IS NOT A CLASSIFICATION, 2026-08-30 ────────────────

    *(The runner claimed `testing_only` "keeps them out of family truth".
    It does no such thing. It is not a column in any migration,
    `create_person` accepts no such parameter, and the intake route uses
    it only to skip consent attestations before writing a row that is
    `narrator_type="live"` — the same as a family narrator's — plus
    profile and bio-fact data.*

    *The claim was also load-bearing in code: `create_narrator` called
    `assert_synthetic` on the row it read back, so the run would have
    created its first narrator and then refused it. The mocked transport
    returned `testing_only: True` and hid that.*

    *The durable authority is the artifact journal.)*
    """

    def _run(self, tmp, transport, run_id="r-test"):
        return COHORT.LiveRun(
            personas=_two_personas(), lanes=list(COHORT.LANES),
            mode="quick", out_dir=Path(tmp), transport=transport,
            ui_url="http://x", db_path=Path("/nonexistent/none.db"),
            run_id=run_id)

    def test_the_product_row_is_live_and_carries_no_testing_only_field(self):
        """Asserted against the product, not against the fake."""
        people = (_REPO_ROOT / "server" / "code" / "api" / "routers"
                  / "people.py").read_text(encoding="utf-8")
        # Intake hard-codes the durable classification.
        self.assertIn('narrator_type="live"', people)
        # `testing_only` is not a column anywhere in the schema.
        migrations = _REPO_ROOT / "server" / "code" / "db" / "migrations"
        for sql in migrations.glob("*.sql"):
            with self.subTest(migration=sql.name):
                self.assertNotIn("testing_only",
                                 sql.read_text(encoding="utf-8"))
        # And `create_person` takes no such parameter.
        db_src = (_REPO_ROOT / "server" / "code" / "api"
                  / "db.py").read_text(encoding="utf-8")
        signature = db_src.split("def create_person(", 1)[1].split(")", 1)[0]
        self.assertNotIn("testing_only", signature)

    def test_the_run_accepts_a_row_with_no_testing_only_field(self):
        """The regression the kind fake concealed."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            t = FakeTransport()
            report = self._run(tmp, t).execute()
            self.assertEqual(len(report["personas"]), 2)
            for row in t.created.values():
                self.assertNotIn("testing_only", row)
                self.assertEqual(row["narrator_type"], "live")

    def test_a_journaled_uuid_is_accepted_on_resume(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(tmp, FakeTransport())
            run.execute()
            pid = run.results[0]["person_id"]
            # A genuinely fresh run object over the same directory, which
            # is what a resume actually is.
            resumed = self._run(tmp, FakeTransport())
            self.assertTrue(resumed.ledger.is_journaled(pid))
            self.assertEqual(resumed.ledger.require_journaled(pid)["person_id"],
                             pid)

    def test_a_resume_does_not_truncate_the_artifact_journal(self):
        """The journal is what makes erasure possible later.

        `Ledger.__init__` wrote its empty structure unconditionally, so
        constructing a resumed run DESTROYED the record of everything the
        interrupted attempt had created — the narrators would then be
        refused as unjournaled and dropped from the erasure manifest,
        becoming orphans with no inventory.
        """
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(tmp, FakeTransport())
            run.execute()
            before = json.loads(
                (Path(tmp) / "artifacts.json").read_text(encoding="utf-8"))
            self.assertEqual(len(before["people"]), 2)

            resumed = self._run(tmp, FakeTransport())
            after = json.loads(
                (Path(tmp) / "artifacts.json").read_text(encoding="utf-8"))
            self.assertEqual(len(after["people"]), 2,
                             "constructing a resumed run truncated the journal")
            self.assertEqual([p["person_id"] for p in before["people"]],
                             [p["person_id"] for p in after["people"]])
            self.assertIn("resumed_at", resumed.ledger.data)

    def test_a_resume_reuses_the_narrator_instead_of_creating_a_second(self):
        """The duplicate-narrator defect, pinned.

        A resume ran `create_narrator` unconditionally, so intake was
        POSTed again and the journal went from two narrators to four.
        The turn checkpoint is keyed by persona, so the new duplicates
        were told their turns were done and got NONE — two empty orphans,
        while the report described the first pair's turns.
        """
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = {}
            first = FakeTransport(fail_on_turn=3, store=db)
            run1 = self._run(tmp, first, run_id="r-dup")
            with self.assertRaises(KeyboardInterrupt):
                run1.execute()
            journaled = [p["person_id"] for p in
                         json.loads((Path(tmp) / "artifacts.json")
                                    .read_text(encoding="utf-8"))["people"]]
            self.assertEqual(len(journaled), 2)

            second = FakeTransport(store=db)
            self._run(tmp, second, run_id="r-dup").execute()
            after = [p["person_id"] for p in
                     json.loads((Path(tmp) / "artifacts.json")
                                .read_text(encoding="utf-8"))["people"]]
            self.assertEqual(after, journaled,
                             "a resume created duplicate narrators")
            # No second intake POST for an already-journaled persona.
            self.assertEqual([c for c in second.calls if c[0] == "POST"], [])

    def test_the_erasure_manifest_survives_a_resume(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self._run(tmp, FakeTransport()).execute()
            self._run(tmp, FakeTransport()).ledger.write_erasure_manifest()
            manifest = json.loads(
                (Path(tmp) / "erasure-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["person_ids"]), 2,
                             "a resume lost narrators from the erasure manifest")

    def test_an_unjournaled_uuid_is_REFUSED_even_when_marked(self):
        """A name beginning ZZ COHORT authorizes nothing."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(tmp, FakeTransport())
            stranger = "99999999-8888-7777-6666-555555555555"
            with self.assertRaises(COHORT.CohortRefusal):
                run.ledger.require_journaled(stranger)
            # Even with a perfectly marked display name on the product row.
            marked = FakeTransport(
                display_name="ZZ COHORT r-test · Somebody Real")
            with self.assertRaises(COHORT.CohortRefusal):
                self._run(tmp, marked).verify_identity(stranger)

    def test_no_resume_path_searches_by_display_name(self):
        """Authority is the UUID. Names are for humans and repeat."""
        tree = ast.parse(SOURCE)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            src = ast.unparse(node)
            if "display_name" in src and "person_id" not in src:
                self.fail(f"a display_name comparison selects a narrator: {src}")
        # And no lookup helper keys off a name.
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "attr", "") or getattr(
                    node.func, "id", "")
                if name in {"require_journaled", "is_journaled"}:
                    arg = ast.unparse(node.args[0]) if node.args else ""
                    self.assertNotIn("display_name", arg)

    def test_the_marker_is_recorded_as_an_affordance_not_authorization(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(tmp, FakeTransport())
            run.execute()
            checks = run.ledger.data["identity_checks"]
            self.assertEqual(len(checks), 2)
            for check in checks:
                self.assertTrue(check["marker_present"])
                self.assertEqual(check["narrator_type"], "live")
                self.assertFalse(check["row_has_testing_only_field"])
                self.assertIn("journal", check["authority"])

    def test_an_unmarked_narrator_is_refused(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            plain = FakeTransport(display_name="Alex")
            with self.assertRaises(COHORT.CohortRefusal):
                self._run(tmp, plain).execute()

    def test_the_manifest_records_testing_only_as_a_REQUEST(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self._run(tmp, FakeTransport()).execute()
            artifacts = json.loads(
                (Path(tmp) / "artifacts.json").read_text(encoding="utf-8"))
            for person in artifacts["people"]:
                self.assertTrue(person["testing_only_requested"])
                # Never restated as a durable classification.
                self.assertNotIn("testing_only", set(person) - {
                    "testing_only_requested"})

    def test_the_runner_no_longer_claims_testing_only_proves_anything(self):
        lowered = SOURCE.lower()
        for claim in ("testing_only is what keeps",
                      "keeps it out of family truth",
                      "refuses anything not testing-only"):
            with self.subTest(claim=claim):
                self.assertNotIn(claim.lower(), lowered)


class InterruptedResumeTests(unittest.TestCase):
    """A resume must repeat no completed model turn."""

    def test_a_resumed_run_does_not_repeat_completed_turns(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            # First attempt: interrupted during the THIRD turn.
            db = {}
            first = FakeTransport(fail_on_turn=3, store=db)
            run1 = COHORT.LiveRun(
                personas=_two_personas(), lanes=list(COHORT.LANES),
                mode="quick", out_dir=Path(tmp), transport=first,
                ui_url="http://x", db_path=Path("/nonexistent/none.db"),
                run_id="ZZ-COHORT-resume")
            with self.assertRaises(KeyboardInterrupt):
                run1.execute()
            self.assertEqual(len(first.turns), 3)   # third raised

            # Resume: a fresh transport over the SAME database and the
            # same output directory.
            second = FakeTransport(store=db)
            run2 = COHORT.LiveRun(
                personas=_two_personas(), lanes=list(COHORT.LANES),
                mode="quick", out_dir=Path(tmp), transport=second,
                ui_url="http://x", db_path=Path("/nonexistent/none.db"),
                run_id="ZZ-COHORT-resume")
            run2.execute()

            # Alex's two turns completed and were checkpointed, so the
            # resume must not re-ask them. Only Walt's remains.
            self.assertEqual(
                [era for _pid, era in second.turns], ["building_years"],
                "a resume re-asked a completed turn")

    def test_the_containment_baseline_is_never_replaced_on_resume(self):
        """Re-taking it would hide the run's own narrators in the delta."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = {}
            first = FakeTransport(fail_on_turn=1, store=db)
            run1 = COHORT.LiveRun(
                personas=_two_personas(), lanes=list(COHORT.LANES),
                mode="quick", out_dir=Path(tmp), transport=first,
                ui_url="http://x", db_path=Path("/nonexistent/none.db"),
                run_id="ZZ-COHORT-base")
            with self.assertRaises(KeyboardInterrupt):
                run1.execute()
            original = (Path(tmp) / "containment-before.json").read_text(
                encoding="utf-8")

            run2 = COHORT.LiveRun(
                personas=_two_personas(), lanes=list(COHORT.LANES),
                mode="quick", out_dir=Path(tmp), transport=FakeTransport(store=db),
                ui_url="http://x", db_path=Path("/nonexistent/none.db"),
                run_id="ZZ-COHORT-base")
            run2.execute()
            self.assertEqual(
                original,
                (Path(tmp) / "containment-before.json").read_text(
                    encoding="utf-8"),
                "the baseline was replaced during a resume")

    def test_an_interruption_leaves_a_resumable_checkpoint(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            run = COHORT.LiveRun(
                personas=_two_personas(), lanes=list(COHORT.LANES),
                mode="quick", out_dir=Path(tmp),
                transport=FakeTransport(fail_on_turn=2),
                ui_url="http://x", db_path=Path("/nonexistent/none.db"),
                run_id="ZZ-COHORT-cp")
            with self.assertRaises(KeyboardInterrupt):
                run.execute()
            saved = json.loads(
                (Path(tmp) / "checkpoint.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["selection"]["mode"], "quick")
            self.assertIn("Alex::turn0", saved["tasks"])


class CohortMembershipTests(unittest.TestCase):
    """Twelve writable narrators, plus two read-only references."""

    def test_the_cohort_is_twelve_writable_narrators(self):
        self.assertEqual(len(COHORT.load_personas()), 12)

    def test_mara_and_elena_are_members_not_merely_templates(self):
        labels = {p["label"] for p in COHORT.load_personas()}
        self.assertIn("Mara Vale", labels)
        self.assertIn("Elena March", labels)
        plan = COHORT.build_plan()
        self.assertIn("Mara Vale", {p["label"] for p in plan["personas"]})
        self.assertEqual(len(plan["personas"]), 12)

    def test_the_templates_supply_intake_payloads_without_being_edited(self):
        before = {name: path.read_bytes()
                  for name, path in COHORT.QA_TEMPLATES.items()}
        personas = COHORT.load_personas()
        mara = next(p for p in personas if p["label"] == "Mara Vale")
        self.assertTrue(mara["intake_payload"]["testing_only"])
        self.assertEqual(mara["intake_payload"]["date_of_birth"], "1941-03-12")
        for name, path in COHORT.QA_TEMPLATES.items():
            with self.subTest(name=name):
                self.assertEqual(before[name], path.read_bytes(),
                                 "a quarantined template was modified")

    def test_harness_supplied_fields_are_labelled_not_passed_off_as_fixture(self):
        """Invented values must be distinguishable from fixture truth."""
        mara = next(p for p in COHORT.load_personas()
                    if p["label"] == "Mara Vale")
        self.assertEqual(sorted(mara["harness_supplied_fields"]),
                         ["current_residence", "pronouns"])

    def test_quick_is_alex_and_walt_by_name_not_the_first_two(self):
        quick = COHORT.load_personas(quick=True)
        self.assertEqual(len(quick), 2)
        self.assertEqual({p["harness"] for p in quick},
                         set(COHORT.QUICK_HARNESSES))
        # Specifically NOT John Baldy, which is what personas[:2] gave.
        self.assertNotIn("run_john_baldy_seven_era_harness",
                         {p["harness"] for p in quick})

    def test_created_narrators_carry_the_cohort_marker(self):
        """Otherwise the cohort creates a narrator called plain "Alex".

        The fixtures carry ordinary human names because they are written
        to read like people. Making them identifiable as test data in the
        picker is the runner's job, and it was passing the fixture's
        payload through unchanged.
        """
        marked = COHORT.mark_intake_payload(
            {"preferred_name": "Alex", "full_legal_name": "Alex Eunseo Park"},
            "r20260829-120000-abc123")
        self.assertTrue(marked["preferred_name"].startswith("ZZ COHORT"))
        self.assertTrue(marked["full_legal_name"].startswith("ZZ COHORT"))
        self.assertIn("Alex", marked["preferred_name"])
        self.assertTrue(marked["testing_only"])

    def test_the_marker_is_not_applied_twice_on_resume(self):
        once = COHORT.mark_intake_payload({"preferred_name": "Alex"}, "r1")
        twice = COHORT.mark_intake_payload(once, "r1")
        self.assertEqual(once["preferred_name"], twice["preferred_name"])

    def test_the_live_run_marks_every_narrator_it_creates(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            t = FakeTransport()
            COHORT.LiveRun(
                personas=_two_personas(), lanes=list(COHORT.LANES),
                mode="quick", out_dir=Path(tmp), transport=t,
                ui_url="http://x", db_path=Path("/nonexistent/none.db"),
                run_id="r-test").execute()
            # FakeTransport.post asserts testing_only; assert the marker here.
            self.assertEqual(len([c for c in t.calls
                                  if c[0] == "POST"]), 2)

    def test_the_run_id_is_filesystem_safe(self):
        """`run_prefix` produced `ZZ COHORT 1d66d482 · ` as a DIRECTORY.

        Spaces, a non-ASCII middot and a trailing separator, in a path
        that has to survive a shell, a `--resume` argument and a Windows
        checkout.
        """
        run_id = COHORT.new_run_id()
        self.assertNotIn(" ", run_id)
        self.assertNotIn("·", run_id)
        self.assertTrue(run_id.isascii())
        self.assertRegex(run_id, r"^r\d{8}-\d{6}-[0-9a-f]{6}$")

    def test_run_prefix_is_still_a_display_name_not_a_path(self):
        """It keeps its spaces on purpose — it is what humans read."""
        self.assertIn(" ", COHORT.run_prefix("abc"))
        self.assertTrue(COHORT.run_prefix("abc").startswith("ZZ COHORT"))

    def test_full_is_still_closed(self):
        import contextlib
        import io
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(err):
            rc = COHORT.main(["--full", "--live"])
        self.assertEqual(rc, 3)
        self.assertIn("--full is not open yet", err.getvalue())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class TurnEvidenceTests(unittest.TestCase):
    """The record must be reviewable by a human, not a character count.

    ── WHY THIS SUITE EXISTS, 2026-08-30 ─────────────────────────────

    `run_turns` stored `{"index", "era", "chars"}`. Lori's response was
    fetched over the WebSocket and discarded, so the report could not
    answer whether she recognised the era, repeated herself, or answered
    at all. Running the cohort on that record would have produced the
    vacuous pass this instrument is supposed to prevent.
    """

    def _run(self, tmp, transport, **kw):
        return COHORT.LiveRun(
            personas=_two_personas(), lanes=list(COHORT.LANES), mode="quick",
            out_dir=Path(tmp), transport=transport,
            ui_url="http://localhost:8082/ui/x.html", run_id="r-evidence", **kw)

    def test_the_full_narrator_and_lori_text_are_kept(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            report = self._run(tmp, FakeTransport()).execute()
            turns = report["personas"][0]["conversation"]["turns"]
            self.assertTrue(turns)
            for t in turns:
                with self.subTest(index=t.get("index")):
                    self.assertTrue(t.get("narrator_text"),
                                    "the narrator's words were not kept")
                    self.assertTrue(t.get("lori_text"),
                                    "Lori's response was not kept")

    def test_ids_and_eras_are_recorded_per_turn(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            report = self._run(tmp, FakeTransport()).execute()
            t = report["personas"][0]["conversation"]["turns"][0]
            for key in ("person_id", "conversation_id", "era_requested",
                        "era_sent", "done_event"):
                self.assertIn(key, t)

    def test_profile_seed_state_is_captured_either_side_of_the_turn(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            report = self._run(tmp, FakeTransport()).execute()
            t = report["personas"][0]["conversation"]["turns"][0]
            for side in ("profile_seed_before", "profile_seed_after"):
                seed = t[side]
                self.assertEqual("childhood_home", seed["active_topic_id"])
                self.assertEqual(2, seed["presentation_epoch"])

    def test_extracted_facts_are_captured_before_and_after(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            report = self._run(tmp, FakeTransport()).execute()
            t = report["personas"][0]["conversation"]["turns"][0]
            self.assertEqual(1, t["facts_before"]["count"])
            self.assertEqual(1, t["facts_after"]["count"])

    def test_the_hardcoded_pass_is_labelled_as_the_instrument_s_own(self):
        """Not dressed up as a browser reading.

        `harness_lib._send_turn_and_capture` hardcodes pass2a, so this
        path cannot observe pass reconciliation. Saying so is the honest
        record; reporting it as `currentPass` would be a fiction.
        """
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            report = self._run(tmp, FakeTransport()).execute()
            t = report["personas"][0]["conversation"]["turns"][0]
            self.assertIn("hardcoded", t["runtime_pass_sent"])

    def test_the_ledger_keeps_ids_and_NOT_narrator_prose(self):
        """The journal is accounting. Speech belongs in the report."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self._run(tmp, FakeTransport()).execute()
            journal = json.loads(
                (Path(tmp) / "artifacts.json").read_text(encoding="utf-8"))
            for row in journal["turns"]:
                self.assertNotIn("narrator_text", row)
                self.assertNotIn("lori_text", row)
                self.assertIn("conversation_id", row)

    def test_the_html_report_shows_the_exchanges_grouped_by_era(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self._run(tmp, FakeTransport()).execute()
            html = (Path(tmp) / "report.html").read_text(encoding="utf-8")
            self.assertIn("Narrator", html)
            self.assertIn("Lori", html)
            self.assertIn("Lori reflects on", html)   # the actual response
            self.assertIn("not scored", html)         # no invented judgement


class ReplayModeTests(unittest.TestCase):
    """Re-measure existing narrators. Create nobody, rewrite nothing."""

    def _source_ledger(self, tmp):
        src = Path(tmp) / "source"
        src.mkdir()
        led = COHORT.Ledger(src, "r-source")
        led.add_person("11111111-2222-3333-4444-000000000001",
                       "ZZ COHORT r-source · Alex", "h1")
        led.add_person("11111111-2222-3333-4444-000000000002",
                       "ZZ COHORT r-source · Walt",
                       "run_seven_era_walk_harness")
        return src, led

    def test_a_replay_creates_no_person(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            src, led = self._source_ledger(tmp)
            transport = FakeTransport(marker="ZZ COHORT r-source · ")
            run = COHORT.LiveRun(
                personas=_two_personas(), lanes=list(COHORT.LANES),
                mode="replay", out_dir=Path(tmp) / "replay",
                transport=transport, ui_url="http://x/y.html",
                run_id="replay-r-new", replay_of="r-source",
                source_ledger=led)
            run.execute()
            posts = [c for c in transport.calls
                     if isinstance(c, tuple) and c[0] == "POST"
                     and "intake" in str(c[1])]
            self.assertEqual([], posts, "a replay performed intake")

    def test_a_replay_reuses_the_journaled_uuids(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            src, led = self._source_ledger(tmp)
            run = COHORT.LiveRun(
                personas=_two_personas(), lanes=list(COHORT.LANES),
                mode="replay", out_dir=Path(tmp) / "replay",
                transport=FakeTransport(marker="ZZ COHORT r-source · "), ui_url="http://x/y.html",
                run_id="replay-r-new", replay_of="r-source",
                source_ledger=led)
            report = run.execute()
            ids = {p["person_id"] for p in report["personas"]}
            self.assertEqual(
                {"11111111-2222-3333-4444-000000000001",
                 "11111111-2222-3333-4444-000000000002"}, ids)

    def test_a_replay_takes_a_NEW_conversation(self):
        """The journaled thread holds defect evidence and must not grow."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            src, led = self._source_ledger(tmp)
            transport = FakeTransport(marker="ZZ COHORT r-source · ")
            run = COHORT.LiveRun(
                personas=_two_personas(), lanes=list(COHORT.LANES),
                mode="replay", out_dir=Path(tmp) / "replay",
                transport=transport, ui_url="http://x/y.html",
                run_id="replay-r-new", replay_of="r-source",
                source_ledger=led)
            run.execute()
            for conv in transport.conv_ids:
                with self.subTest(conv=conv):
                    self.assertTrue(conv.startswith("replay-"), conv)
                    self.assertNotIn("r-source", conv)

    def test_a_replay_does_not_write_to_the_source_journal(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            src, led = self._source_ledger(tmp)
            before = (src / "artifacts.json").read_text(encoding="utf-8")
            run = COHORT.LiveRun(
                personas=_two_personas(), lanes=list(COHORT.LANES),
                mode="replay", out_dir=Path(tmp) / "replay",
                transport=FakeTransport(marker="ZZ COHORT r-source · "), ui_url="http://x/y.html",
                run_id="replay-r-new", replay_of="r-source",
                source_ledger=led)
            run.execute()
            self.assertEqual(
                before, (src / "artifacts.json").read_text(encoding="utf-8"),
                "the source journal was modified by a replay")

    def test_a_replay_refuses_rather_than_creating_an_unjournaled_persona(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "empty"; src.mkdir()
            led = COHORT.Ledger(src, "r-empty")     # journals nobody
            run = COHORT.LiveRun(
                personas=_two_personas(), lanes=list(COHORT.LANES),
                mode="replay", out_dir=Path(tmp) / "replay",
                transport=FakeTransport(marker="ZZ COHORT r-source · "), ui_url="http://x/y.html",
                run_id="replay-r-new", replay_of="r-empty",
                source_ledger=led)
            with self.assertRaises(COHORT.CohortRefusal):
                run.execute()
