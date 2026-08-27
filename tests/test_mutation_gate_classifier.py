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
import sys
import unittest
from pathlib import Path

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

    def test_a_zero_exit_with_a_FAILED_summary_still_counts_failures(self):
        """Exit code is not the authority; the summary is."""
        self.assertEqual(gate.CAUGHT, self.verdict(0, summary(failures=2)))


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


if __name__ == "__main__":
    unittest.main()
