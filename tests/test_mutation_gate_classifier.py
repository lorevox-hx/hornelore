"""The mutation runner's verdict, tested against synthetic summaries.

── WHY THIS MODULE EXISTS ─────────────────────────────────────────────

The gate is the instrument that decides whether the Profile Seed tests
are worth anything. Nothing was testing the gate.

The cost of that showed up twice, the same way both times: a mutation
that broke the module outright was scored as evidence that the tests
work. First a `SyntaxError`, which produced a narrow rule naming syntax
errors specifically. Then `C16`, written against `TRIM_ALLOWED` — a
constant that does not exist — which raised `NameError`, errored every
test in three suites, exited non-zero, and was reported CAUGHT having
tested nothing at all.

The property that matters is not "which exception was it". It is
**whether any assertion failed**. An assertion failure means a test
looked at behaviour and disagreed with it. An error means the test never
reached the behaviour.

These run against captured unittest output rather than real subprocesses
so the awkward cases — errors-only, no summary, mixed — can be stated
exactly, including the ones that are tedious to reproduce on demand.
"""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts"))

import run_mutation_gate as gate  # noqa: E402


def summary(failures=0, errors=0, ok=False, extra=""):
    """A realistic unittest tail."""
    body = "----------------------------------------------------------------------\n"
    if ok:
        return f"{extra}\nRan 12 tests in 0.4s\n\n{body}OK\n"
    bits = []
    if failures:
        bits.append(f"failures={failures}")
    if errors:
        bits.append(f"errors={errors}")
    detail = f" ({', '.join(bits)})" if bits else ""
    return f"{extra}\nRan 12 tests in 0.4s\n\n{body}FAILED{detail}\n"


class ClassifierTests(unittest.TestCase):
    def verdict(self, code, output):
        return gate.classify_result(code, output)[0]

    def test_a_green_run_is_MISSED(self):
        self.assertEqual(gate.MISSED, self.verdict(0, summary(ok=True)))

    def test_one_assertion_failure_is_CAUGHT(self):
        self.assertEqual(gate.CAUGHT, self.verdict(1, summary(failures=1)))

    def test_failures_mixed_with_errors_are_CAUGHT(self):
        """C13 and C14 legitimately look like this.

        Their mutations reintroduce a claim AND make malformed-metadata
        cases raise, so a real assertion failure arrives beside genuine
        errors. Refusing mixed results would throw away true evidence.
        """
        status, tail = gate.classify_result(1, summary(failures=11, errors=1))
        self.assertEqual(gate.CAUGHT, status)
        self.assertIn("failures=11", tail)
        self.assertIn("errors=1", tail)

    def test_errors_only_is_BROKEN(self):
        status, tail = gate.classify_result(1, summary(errors=8))
        self.assertEqual(gate.BROKEN, status)
        self.assertIn("no assertion failed", tail)

    def test_the_EXACT_NameError_case_is_BROKEN(self):
        """C16 against `TRIM_ALLOWED`, as it actually happened.

        This is the regression that motivated the rule. Under the old
        classifier it returned CAUGHT — a non-zero exit with no
        SyntaxError — and would have been reported as proof that the
        preservation tests defend the policy.
        """
        traceback = (
            "ERROR: test_lori_can_never_lose_her_identity_or_her_discipline\n"
            "Traceback (most recent call last):\n"
            '  File "prompt_section_policy.py", line 237, in <module>\n'
            "    TIER_WORKFLOW, False, 35,\n"
            "NameError: name 'TRIM_ALLOWED' is not defined\n")
        status, tail = gate.classify_result(1, summary(errors=71,
                                                       extra=traceback))
        self.assertEqual(gate.BROKEN, status)
        self.assertIn("NameError", tail)

    def test_the_REAL_TRIM_ALLOWED_output_shape_is_BROKEN(self):
        """The same defect, in the shape it actually produced.

        Re-running C16-with-`TRIM_ALLOWED` against the live tree shows
        it is worse than the synthetic case above: the policy module
        fails at IMPORT, so unittest never prints a summary line at all.
        Exit was 1, there was no SyntaxError, and the old classifier
        returned CAUGHT. Two different BROKEN branches — an errors-only
        summary and no summary whatsoever — reach the same verdict, and
        both need a test or the next one is a surprise.
        """
        real = ("Traceback (most recent call last):\n"
                '  File "/usr/lib/python3.10/unittest/loader.py", line 154\n'
                "    module = __import__(module_name)\n"
                '  File ".../prompt_section_policy.py", line 236\n'
                "    \"profile_seed_onboarding_active\", TRIM_ALLOWED,\n"
                "NameError: name 'TRIM_ALLOWED' is not defined\n")
        status, tail = gate.classify_result(1, real)
        self.assertEqual(gate.BROKEN, status)
        self.assertIn("no recognizable unittest summary", tail)

    def test_import_and_attribute_failures_are_BROKEN(self):
        for marker in ("ImportError: cannot import name 'x'",
                       "ModuleNotFoundError: No module named 'x'",
                       "AttributeError: 'NoneType' object has no attribute 'y'",
                       "SyntaxError: invalid syntax",
                       "IndentationError: unexpected indent"):
            with self.subTest(marker=marker):
                status, tail = gate.classify_result(
                    1, summary(errors=4, extra=marker))
                self.assertEqual(gate.BROKEN, status)
                self.assertIn(marker.split(":")[0], tail)

    def test_a_run_with_no_summary_is_BROKEN(self):
        """A crashed or killed run has no verdict to read."""
        for output in ("", "Killed\n", "Traceback (most recent call last):\n",
                       None):
            with self.subTest(output=output):
                status, tail = gate.classify_result(1, output)
                self.assertEqual(gate.BROKEN, status)
                self.assertIn("no recognizable unittest summary", tail)

    def test_an_errors_only_run_without_a_known_marker_is_still_BROKEN(self):
        """The rule is about assertions, not about naming exceptions.

        The marker list makes the REPORT specific. It must never be what
        decides the verdict, or the next unfamiliar exception walks
        through exactly as NameError did.
        """
        status, tail = gate.classify_result(
            1, summary(errors=3, extra="ZeroDivisionError: division by zero"))
        self.assertEqual(gate.BROKEN, status)
        self.assertIn("no assertion failed", tail)

    # ── the exit code and the summary are TWO observations of one run ──
    def test_a_zero_exit_with_a_FAILED_summary_is_BROKEN(self):
        """*(This asserted CAUGHT, with the docstring "exit code is not
        the authority; the summary is". That was backwards. They are two
        independent observations of one run, and when they disagree the
        run is inconsistent — a harness fault, a killed process, a
        wrapper eating the status. Neither reading is trustworthy, and
        preferring whichever suits the verdict is how an instrument
        starts agreeing with whatever it is pointed at.)*"""
        status, tail = gate.classify_result(0, summary(failures=2))
        self.assertEqual(gate.BROKEN, status)
        self.assertIn("disagree", tail)

    def test_a_nonzero_exit_with_an_OK_summary_is_BROKEN(self):
        status, tail = gate.classify_result(1, summary(ok=True))
        self.assertEqual(gate.BROKEN, status)
        self.assertIn("disagree", tail)

    # ── the LAST summary is the verdict, not the first ────────────────
    def test_noise_beginning_with_FAILED_does_not_become_the_verdict(self):
        """A surviving mutation must not be scored as caught.

        Tests print to stderr. A captured message, a logged line, or a
        subprocess of the suite's own can start with "FAILED", and
        `.search()` took the FIRST match as the verdict while the real
        summary below it said OK.
        """
        noisy = ("FAILED (failures=9)\n"
                 "some captured output from the test itself\n"
                 + summary(ok=True))
        self.assertEqual(gate.MISSED, self.verdict(0, noisy))

    def test_noise_beginning_with_OK_does_not_hide_a_real_failure(self):
        """The same defect in the other direction."""
        noisy = "OK, here is some captured output\n" + summary(failures=1)
        self.assertEqual(gate.CAUGHT, self.verdict(1, noisy))

    def test_the_last_summary_wins_even_after_several(self):
        stacked = (summary(failures=3) + summary(ok=True)
                   + summary(failures=1))
        status, tail = gate.classify_result(1, stacked)
        self.assertEqual(gate.CAUGHT, status)
        self.assertIn("failures=1", tail)

    def test_noise_cannot_rescue_an_inconsistent_run(self):
        """Agreement is checked against the FINAL summary, not the noise."""
        noisy = "FAILED (failures=9)\n" + summary(ok=True)
        self.assertEqual(gate.BROKEN, self.verdict(1, noisy))


class DuplicateIdGuardTests(unittest.TestCase):
    """`_assert_unique_ids()` was added after a real defect. Now tested.

    *(It was added because Step 5 introduced `S1`/`S2` as `R1`/`R2`,
    which were already the Step 1 refusal mutations — and nothing
    noticed, because ids are how mutations are selected and reported, so
    `--only R1` silently meant two unrelated things. Adding the guard
    without covering it repeated the shape of the original problem: a
    protection nobody has seen work.)*
    """

    def make(self, *ids):
        return tuple(
            gate.Mutation(i, f"what {i}", "target.py", "old", "new", "tests")
            for i in ids)

    def test_duplicate_ids_REFUSE(self):
        original = gate.MUTATIONS
        try:
            gate.MUTATIONS = self.make("A1", "A2", "A1")
            with self.assertRaises(SystemExit) as caught:
                gate._assert_unique_ids()
            self.assertIn("A1", str(caught.exception))
        finally:
            gate.MUTATIONS = original

    def test_unique_ids_PASS(self):
        """Positive control. A guard that refused everything, or nothing,
        would pass the test above."""
        original = gate.MUTATIONS
        try:
            gate.MUTATIONS = self.make("A1", "A2", "A3")
            gate._assert_unique_ids()          # must not raise
        finally:
            gate.MUTATIONS = original

    def test_the_REAL_mutation_list_has_no_duplicates(self):
        """The condition the guard exists to maintain, checked directly
        rather than only through the guard."""
        ids = [m.id for m in gate.MUTATIONS]
        self.assertEqual(sorted(set(ids)), sorted(ids),
                         "the checked-in mutation list has duplicate ids")

    def test_the_refusal_names_BOTH_colliding_mutations(self):
        """A duplicate-id error that names only the id sends the reader
        looking for one of two identical strings."""
        original = gate.MUTATIONS
        try:
            gate.MUTATIONS = self.make("A1", "A1")
            with self.assertRaises(SystemExit) as caught:
                gate._assert_unique_ids()
            message = str(caught.exception)
            self.assertEqual(2, message.count("what A1"),
                             "the refusal did not describe both mutations")
        finally:
            gate.MUTATIONS = original


class AmbiguousAnchorTests(unittest.TestCase):
    """`run_one()` refuses an anchor that matches more than one place.

    *(Added with the guard, not after it. `str.replace(old, new, 1)`
    takes the FIRST occurrence, so an ambiguous anchor mutates whichever
    site comes first and leaves the rest intact — a HALF mutation
    reported as a whole one. Caught writing S9, whose original anchor
    appeared once per REST route: it would have mutated `/api/chat` only
    and reported CAUGHT while `/api/chat/stream` was untouched.)*
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.target = Path(self.tmp.name) / "target.py"
        self.rel = str(self.target)

    def _mutation(self, old, new="REPLACED"):
        return gate.Mutation("X1", "what", self.rel, old, new,
                             "tests.does_not_matter")

    def _run(self, old):
        original = self.target.read_text(encoding="utf-8")
        status, tail = gate.run_one(self._mutation(old), dict(os.environ))
        return status, tail, self.target.read_text(encoding="utf-8"), original

    def test_ZERO_matches_is_BROKEN_and_leaves_the_file_alone(self):
        self.target.write_text("alpha = 1\n", encoding="utf-8")
        status, tail, after, before = self._run("nonexistent anchor")
        self.assertEqual(gate.BROKEN, status)
        self.assertIn("anchor not found", tail)
        self.assertEqual(before, after, "the target was modified")

    def test_MULTIPLE_matches_is_BROKEN_and_leaves_the_file_alone(self):
        """The defect the guard exists for. The file must be untouched —
        a half-mutated target left on disk is worse than no run."""
        self.target.write_text("x = 1\nsame = 2\ny = 3\nsame = 4\n",
                               encoding="utf-8")
        status, tail, after, before = self._run("same")
        self.assertEqual(gate.BROKEN, status)
        self.assertIn("matches 2 places", tail)
        self.assertEqual(before, after,
                         "an ambiguous anchor still edited the target")

    def test_EXACTLY_ONE_match_PASSES_the_anchor_check(self):
        """Positive control: a guard refusing everything would satisfy
        both tests above forever.

        The verdict here is still BROKEN, because the fixture names a
        test module that does not exist so the run reaches no summary —
        but it must be broken for THAT reason, not for an anchor one.
        Asserting on the reason is the only thing that distinguishes
        "the anchor was accepted" from "the anchor was refused".
        """
        self.target.write_text("keep = 0\nunique_line = 1\n",
                               encoding="utf-8")
        status, tail, after, before = self._run("unique_line = 1")
        self.assertNotIn("anchor", tail.lower(),
                         "a UNIQUE anchor was refused by the anchor check")
        self.assertEqual(before, after,
                         "run_one did not restore the target afterwards")


class ClassifierIsNotVacuousTests(unittest.TestCase):
    """The synthetic summaries must resemble real unittest output.

    Without this, `summary()` could drift into a shape the classifier
    never sees in practice and every test above would keep passing.
    """

    def test_the_fixture_matches_what_unittest_actually_prints(self):
        import io
        class Tiny(unittest.TestCase):
            def test_fails(self):
                self.assertEqual(1, 2)
            def test_errors(self):
                raise ValueError("boom")

        buf = io.StringIO()
        suite = unittest.TestLoader().loadTestsFromTestCase(Tiny)
        unittest.TextTestRunner(stream=buf, verbosity=0).run(suite)
        real = buf.getvalue()

        status, tail = gate.classify_result(1, real)
        self.assertEqual(gate.CAUGHT, status)
        self.assertIn("failures=1", tail)
        self.assertIn("errors=1", tail)

    def test_a_real_all_green_run_is_MISSED(self):
        import io
        class Fine(unittest.TestCase):
            def test_ok(self):
                pass

        buf = io.StringIO()
        suite = unittest.TestLoader().loadTestsFromTestCase(Fine)
        unittest.TextTestRunner(stream=buf, verbosity=0).run(suite)
        self.assertEqual(gate.MISSED,
                         gate.classify_result(0, buf.getvalue())[0])


class TimeoutIsBrokenNotCaughtTests(unittest.TestCase):
    """A killed child is not evidence, and must not end the run.

    ── WHY, 2026-09-05 ──────────────────────────────────────────────

    `_run_tests` ran with `timeout=900` and no handler. A timeout
    therefore escaped `run_one` — the `finally` still restored the source
    and cleared the journal, that guarantee was already sound — but the
    exception then left `main()` with a traceback and NO verdict for any
    remaining mutation. An hour of gate became zero classified results.

    And it must never be CAUGHT. A child that was killed produced no
    assertion failure and no summary, so "the tests did not finish" is
    not "the tests objected" — crediting it would silently retire a real
    test the first time a suite got slow. That is the same reasoning the
    classifier already applies to errors-only runs.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.target = Path(self.tmp.name) / "target.py"
        self.target.write_text("keep = 0\nunique_line = 1\n", encoding="utf-8")
        self.mutation = gate.Mutation(
            "TO1", "what", str(self.target),
            "unique_line = 1", "unique_line = 2", "tests.irrelevant")

    def _timing_out(self, *_a, **_kw):
        raise subprocess.TimeoutExpired(cmd=["python", "-m", "unittest"],
                                        timeout=900)

    def test_a_timeout_is_classified_BROKEN(self):
        with mock.patch.object(gate, "_run_tests", self._timing_out):
            status, detail = gate.run_one(self.mutation, dict(os.environ))
        self.assertEqual(gate.BROKEN, status)
        self.assertIn("timeout", detail.lower())

    def test_a_timeout_is_NEVER_classified_CAUGHT(self):
        """Stated separately because it is the dangerous direction.

        BROKEN costs a re-run. CAUGHT is a false green that removes a
        test from the gate's protection without anyone deciding to.
        """
        with mock.patch.object(gate, "_run_tests", self._timing_out):
            status, _ = gate.run_one(self.mutation, dict(os.environ))
        self.assertNotEqual(gate.CAUGHT, status)

    def test_the_source_is_restored_after_a_timeout(self):
        before = self.target.read_text(encoding="utf-8")
        with mock.patch.object(gate, "_run_tests", self._timing_out):
            gate.run_one(self.mutation, dict(os.environ))
        self.assertEqual(before, self.target.read_text(encoding="utf-8"),
                         "a timeout left the mutation on disk")

    def test_the_journal_is_cleared_after_a_timeout(self):
        with mock.patch.object(gate, "_run_tests", self._timing_out):
            gate.run_one(self.mutation, dict(os.environ))
        self.assertFalse(
            gate.JOURNAL.exists(),
            "a surviving journal refuses every later run, so a timeout "
            "would block the gate until someone deleted it by hand")

    def test_the_production_timeout_is_injected_not_hardcoded(self):
        """`CHILD_TIMEOUT_S` must actually reach `subprocess.run`.

        Proven by reading the kwarg rather than by waiting: a test that
        lowered the production constant to make itself fast would change
        the very value it claims to verify.
        """
        seen = {}

        def _fake_run(*_a, **kw):
            seen.update(kw)
            return subprocess.CompletedProcess([], 0, "", "OK\n")

        with mock.patch.object(gate.subprocess, "run", _fake_run):
            with mock.patch.object(gate, "CHILD_TIMEOUT_S", 1234):
                gate._run_tests("tests.irrelevant", dict(os.environ))
        self.assertEqual(1234, seen.get("timeout"))

    def test_an_explicit_timeout_argument_overrides_the_constant(self):
        seen = {}

        def _fake_run(*_a, **kw):
            seen.update(kw)
            return subprocess.CompletedProcess([], 0, "", "OK\n")

        with mock.patch.object(gate.subprocess, "run", _fake_run):
            gate._run_tests("tests.irrelevant", dict(os.environ), timeout=7)
        self.assertEqual(7, seen.get("timeout"))


class RunnerProgressAndPolicyTests(unittest.TestCase):
    """The runner says what it is doing, and finishes what it started.

    A gate of this size that prints nothing for an hour is not usable as
    an acceptance gate: a legitimately slow suite and a hang look
    identical from outside. A full run was killed by hand on 2026-09-05
    in that belief — `test_profile_seed_ws_step6` takes ~31s, of which
    only 9 are CPU, and nothing said so.
    """

    def _drive(self, verdicts):
        """Run `main()` over fake mutations, returning (stdout, exit).

        `verdicts` maps mutation id to the status `run_one` should
        report, so a BROKEN or MISSED can be staged without needing a
        product defect to produce one.
        """
        muts = tuple(
            gate.Mutation(mid, f"what {mid}", "irrelevant.py", "a", "b",
                          f"tests.suite_for_{mid}")
            for mid in verdicts)
        order = []

        def _fake_run_one(mutation, _env, timeout=None):
            order.append(("ran", mutation.id, buf.getvalue()))
            return verdicts[mutation.id], "detail"

        buf = io.StringIO()
        with mock.patch.object(gate, "MUTATIONS", muts), \
             mock.patch.object(gate, "_baseline_green", lambda *_a: True), \
             mock.patch.object(gate, "_unclean_paths", lambda: []), \
             mock.patch.object(gate, "_journal_check", lambda: 0), \
             mock.patch.object(gate, "run_one", _fake_run_one), \
             mock.patch.object(sys, "argv", ["run_mutation_gate.py"]), \
             contextlib.redirect_stdout(buf):
            code = gate.main()
        return buf.getvalue(), code, order

    def test_the_progress_line_is_printed_BEFORE_the_child_runs(self):
        """Ordering is the whole point.

        A progress line printed after the child would appear at the same
        moment as the verdict and tell a watcher nothing during the wait
        that prompted it.
        """
        _out, _code, order = self._drive({"A1": gate.CAUGHT})
        _tag, _mid, stdout_at_call = order[0]
        self.assertIn("RUNNING A1", stdout_at_call,
                      "the child started before its progress line was "
                      "printed, so the line cannot announce a wait")

    def test_the_progress_line_names_the_suite_and_the_position(self):
        out, _code, _order = self._drive({"A1": gate.CAUGHT,
                                          "A2": gate.CAUGHT})
        self.assertIn("RUNNING A1 ", out)
        self.assertIn("[1/2]", out)
        self.assertIn("[2/2]", out)
        self.assertIn("tests.suite_for_A1", out)

    def test_every_verdict_reports_an_elapsed_time(self):
        out, _code, _order = self._drive({"A1": gate.CAUGHT})
        self.assertRegex(out, r"CAUGHT.*A1.*\d+\.\d+s")

    def test_a_BROKEN_result_does_NOT_stop_the_remaining_mutations(self):
        """THE DOCUMENTED POLICY: continue.

        Stopping at the first bad result would discard the
        classification of every mutation after it — an hour of gate
        reduced to one line — and there is nothing to protect by
        stopping, because `run_one` restores the source per mutation in
        a `finally` rather than at the end.
        """
        out, code, order = self._drive({"A1": gate.BROKEN,
                                        "A2": gate.CAUGHT,
                                        "A3": gate.MISSED})
        self.assertEqual(["A1", "A2", "A3"], [m for _t, m, _s in order],
                         "the run stopped early after a bad result")
        self.assertEqual(1, code, "a run with MISSED/BROKEN must exit 1")
        self.assertIn("NOT AN ACCEPTING RUN", out)

    def test_MISSED_and_BROKEN_are_named_separately_in_the_summary(self):
        """They mean opposite things and used to look identical.

        The summary reported only the caught count, so both showed as
        "one short" and a reader had to scroll back through eighty lines
        to find out which. MISSED is a missing test; BROKEN is a
        measurement that never happened.
        """
        out, _code, _order = self._drive({"A1": gate.BROKEN,
                                          "A2": gate.MISSED,
                                          "A3": gate.CAUGHT})
        # A1 is the BROKEN one and A2 the MISSED one. Naming them exactly
        # matters: an alternation that accepted either id would pass even
        # if the summary put every bad result in one bucket, which is the
        # confusion this test exists to prevent.
        self.assertRegex(out, r"MISSED\s+1: A2\b")
        self.assertRegex(out, r"BROKEN\s+1: A1\b")
        self.assertNotIn("A3", out.split("caught behaviourally")[-1],
                         "the CAUGHT mutation was listed in a failure bucket")
        self.assertIn("1/3 caught", out)

    def test_an_all_caught_run_exits_zero_and_says_nothing_alarming(self):
        """The positive control.

        Without it, a runner that printed NOT AN ACCEPTING RUN
        unconditionally would satisfy every test above.
        """
        out, code, _order = self._drive({"A1": gate.CAUGHT,
                                         "A2": gate.CAUGHT})
        self.assertEqual(0, code)
        self.assertNotIn("NOT AN ACCEPTING RUN", out)
        self.assertIn("2/2 caught", out)
        self.assertIn("elapsed", out)


if __name__ == "__main__":
    unittest.main()
