"""WO-LORI-ARCHIVE-TO-MEMOIR-02 Phase 1 probe — offline guards.

The probe performs ONE authorized live mutation: promoting story
candidate 447eee18. These tests exist because that mutation is not
freely repeatable — the candidate can only be promoted once — so the
probe's guards must be verified before it is ever run.
"""
from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "scripts" / "ui" / "phase1_memoir_chain_probe.js"

TARGET = "447eee18-9ea5-4961-bf3d-157773d3cd44"
CONTROL = "5a56f942-001b-453b-8e4d-01fb82062013"


def _code_only(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?m)^\s*//[^\n]*", "", src)


class ProbeShapeTests(unittest.TestCase):
    def setUp(self):
        self.raw = PROBE.read_text(encoding="utf-8")
        self.src = _code_only(self.raw)

    def test_it_parses_and_self_tests(self):
        for args in (["--check"], ["--self-test"]):
            flag = ["node", "--check", str(PROBE)] if args == ["--check"] \
                else ["node", str(PROBE), "--self-test"]
            out = subprocess.run(flag, capture_output=True, text=True, timeout=60)
            self.assertEqual(0, out.returncode, out.stderr)

    def test_exactly_one_candidate_is_targeted(self):
        self.assertEqual(TARGET, re.search(
            r'const TARGET\s*=\s*"([^"]+)"', self.src).group(1))
        self.assertEqual(CONTROL, re.search(
            r'const CONTROL\s*=\s*"([^"]+)"', self.src).group(1))

    def test_promotion_uses_the_real_ui_control(self):
        self.assertIn('page.locator(".story-act-promote")', self.src)

    def test_it_never_promotes_twice(self):
        self.assertIn("NOT re-promoting", self.raw)
        self.assertIn("promotedThisRun", self.src)


class RefusalTests(unittest.TestCase):
    """A refusal is a result. The probe must stop, not adapt."""

    def setUp(self):
        self.src = _code_only(PROBE.read_text(encoding="utf-8"))

    def test_all_seven_preconditions_are_checked(self):
        for name in ("candidate readable", "candidate id matches",
                     "narrator is Pat", "status is promotable",
                     "era recorded", "passage matches", "control readable"):
            self.assertIn(name, self.src)

    def test_a_failed_precondition_stops_before_promotion(self):
        # Anchor on the actual click, not the locator string — that also
        # appears inside the self-test's own source assertions near the top
        # of the file, which made this test pass for the wrong reason.
        i_check = self.src.index("REFUSED before promotion")
        i_click = self.src.index("await promoteBtn.click()")
        self.assertLess(i_check, i_click,
                        "the refusal must be evaluated before the promote click")

    def test_provisional_is_required_unless_resuming(self):
        self.assertIn('priorProof\n        ? ["unreviewed", "in_review", "promoted"]',
                      self.src)
        self.assertIn(': ["unreviewed", "in_review"].includes(String(status))', self.src)


class ResumeGuardTests(unittest.TestCase):
    def setUp(self):
        self.src = _code_only(PROBE.read_text(encoding="utf-8"))

    def test_resume_requires_a_report_proving_this_probe_promoted_it(self):
        self.assertIn("prior.promotedCandidateId === TARGET", self.src)
        self.assertIn('l3.result === "PASS"', self.src)

    def test_resume_refuses_an_unproven_report(self):
        self.assertIn("does not prove this probe promoted", self.src)
        self.assertIn("process.exit(2)", self.src)

    def test_the_promotion_is_journaled_for_a_later_resume(self):
        self.assertIn("R.promotedCandidateId = TARGET", self.src)
        self.assertIn("R.promotedAt =", self.src)


class AcceptancePathTests(unittest.TestCase):
    """Preview and export are accepted through the UI only."""

    def setUp(self):
        self.raw = PROBE.read_text(encoding="utf-8")
        self.src = _code_only(self.raw)

    def test_export_acceptance_is_the_ui_control(self):
        self.assertIn('acceptancePath: "UI control #memoirExportDocxBtn"', self.src)
        self.assertIn("memoirExportDocxBtn", self.src)

    def test_a_direct_post_cannot_satisfy_the_export_gate(self):
        self.assertIn("diagnosisOnly_directPOST", self.src)
        block = self.src[self.src.index('step("6_export"'):]
        self.assertIn('result: downloads.length ? "PASS" : "FAIL"', block[:400])
        self.assertNotIn('direct.status === 200 ? "PARTIAL"', self.src)

    def test_preview_is_measured_in_the_real_panel(self):
        self.assertIn("memoirScrollPopover", self.src)
        self.assertIn("neverSubstituted", self.src)

    def test_preview_records_url_and_status(self):
        self.assertIn("requestedUrl", self.src)
        self.assertIn("requestedStatus", self.src)


class VerdictShapeTests(unittest.TestCase):
    def setUp(self):
        self.src = _code_only(PROBE.read_text(encoding="utf-8"))

    def test_the_five_required_verdict_lines_exist(self):
        for k in ("promotion:", "canonical_api:", "preview:", "export:",
                  "control_unchanged:"):
            self.assertIn(k, self.src)

    def test_wrong_origin_preview_is_named_as_such(self):
        self.assertIn('"failed — wrong API origin"', self.src)
        self.assertIn("requestedStatus === 404", self.src)

    def test_export_reports_not_reached_when_preview_failed(self):
        self.assertIn('"not reached through accepted UI path"', self.src)

    def test_the_exit_gate_names_the_failing_link(self):
        self.assertIn("Phase 1: failed at ${firstBad", self.src)


class ControlCandidateTests(unittest.TestCase):
    def test_the_control_is_compared_before_and_after(self):
        src = _code_only(PROBE.read_text(encoding="utf-8"))
        self.assertIn("JSON.stringify(ctlPre.body) === JSON.stringify(ctlPost.body)", src)
        self.assertIn("7_control_unchanged", src)

    def test_the_control_is_never_clicked_or_patched(self):
        src = _code_only(PROBE.read_text(encoding="utf-8"))
        after = src[src.index("const CONTROL"):]
        self.assertNotIn("PATCH", after)


if __name__ == "__main__":      # pragma: no cover
    unittest.main()
