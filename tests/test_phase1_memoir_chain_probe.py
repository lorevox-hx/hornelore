"""Phase 1 probe — offline behavioural guards.

The probe performs ONE authorized, unrepeatable live mutation: promoting
story candidate 447eee18. Every guard below exists because a mistake is
not undoable, so it must be proven before the probe is ever run.

The prior revision selected `.story-act-promote` with `.first()` while
validating the target through the API. Pat has two candidates and the
Bug Panel lists every narrator's unreviewed rows, so that click could
have promoted the CONTROL candidate and only noticed afterwards.
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


class _Base(unittest.TestCase):
    def setUp(self):
        self.raw = PROBE.read_text(encoding="utf-8")
        self.src = _code_only(self.raw)


class SyntaxAndSelfTest(_Base):
    def test_parses(self):
        r = subprocess.run(["node", "--check", str(PROBE)],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(0, r.returncode, r.stderr)

    def test_self_test_passes(self):
        r = subprocess.run(["node", str(PROBE), "--self-test"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertIn("SELF-TEST PASS", r.stdout)


class ExactRowSelectionTests(_Base):
    """1 — the row is located by narrator AND passage, never by position."""

    def test_no_first_promote_control(self):
        needle = ".story-act-promote" + '")' + ".fir" + "st()"
        self.assertNotIn(needle, self.src)

    def test_narrator_filter_is_applied_first(self):
        self.assertIn("filter.fill(PERSON)", self.src)

    def test_the_row_is_found_by_the_target_passage(self):
        self.assertIn("PASSAGE_HEAD", self.src)
        self.assertIn("2_row_located", self.src)

    def test_detail_is_opened_and_full_transcript_verified(self):
        self.assertIn("2b_detail_verified", self.src)
        self.assertIn("showsFullPassage", self.src)

    def test_it_refuses_unless_exactly_one_promote_control(self):
        self.assertIn("n !== 1", self.src)
        self.assertIn("refusing to guess", self.raw)

    def test_detail_verification_precedes_the_click(self):
        self.assertLess(self.src.index("2b_detail_verified"),
                        self.src.index("btn.click()"))


class PatchGuardTests(_Base):
    """2, 3 — a foreign PATCH cannot leave the browser."""

    def test_a_route_guard_is_installed(self):
        self.assertIn('page.route("**/api/operator/story-candidates/**"', self.src)
        # The guard must be a REAL named function, not a name that exists
        # only inside the assertion checking for it. That vacuous form was
        # caught here once already: the string appeared exactly once, in
        # the self-test that asserted its presence.
        self.assertIn("const refuseForeignPatch = async", self.src)
        self.assertGreaterEqual(self.src.count("refuseForeignPatch"), 2,
                                "the guard must be defined AND installed")

    def test_non_target_patches_are_aborted_and_recorded(self):
        self.assertIn('!req.url().includes(TARGET)', self.src)
        self.assertIn('route.abort("blockedbyclient")', self.src)
        self.assertIn("blockedPatches.push", self.src)

    def test_the_real_patch_is_observed_and_required(self):
        self.assertIn("waitForResponse", self.src)
        self.assertIn("targetedTarget", self.src)
        self.assertIn("R.blockedPatches.length", self.src)


class ResumeTests(_Base):
    """4, 5 — resume requires exactly promoted and carries provenance."""

    def test_resume_requires_status_exactly_promoted(self):
        self.assertIn('prior ? String(status) === "promoted"', self.src)

    def test_resume_never_accepts_unreviewed_or_in_review(self):
        i = self.src.index('prior ? String(status) === "promoted"')
        clause = self.src[i:i + 160]
        self.assertIn('["unreviewed", "in_review"].includes', clause)
        self.assertNotIn('"promoted"].includes', clause)

    def test_promotion_identity_and_time_are_carried_forward(self):
        self.assertIn("promotedCandidateId: p.promotedCandidateId", self.src)
        self.assertIn("promotedAt: p.promotedAt", self.src)
        self.assertIn("prior ? prior.promotedCandidateId : null", self.src)

    def test_a_resume_chain_is_recorded(self):
        self.assertIn("chain:", self.src)


class PreviewTests(_Base):
    """6, 7 — the real UI request is observed; no synthetic fetch."""

    def test_the_actual_ui_request_is_observed(self):
        self.assertIn("memoirRequest", self.src)
        self.assertIn('r.url().includes("/api/memoir/canonical")', self.src)

    def test_no_probe_generated_relative_fetch_is_used_as_evidence(self):
        self.assertNotIn('await fetch("/api/memoir/canonical', self.src)

    def test_preview_requires_exactly_one_occurrence(self):
        self.assertIn("panel.occurrences === 1", self.src)

    def test_export_is_not_attempted_when_preview_fails(self):
        i_guard = self.src.index("panel.occurrences !== 1")
        i_click = self.src.index("exportBtn.click()")
        self.assertLess(i_guard, i_click)
        self.assertIn("export is NOT attempted", self.raw)


class ExportTests(_Base):
    """8, 9 — a real download event, and the document is read."""

    def test_no_fixed_sleep_before_export(self):
        self.assertNotIn("waitForTimeout(8000)", self.src)

    def test_it_waits_for_a_real_download_event(self):
        self.assertIn('page.waitForEvent("download"', self.src)

    def test_the_docx_is_opened_and_counted(self):
        self.assertIn("function docxText", self.src)
        self.assertIn("word/document.xml", self.src)
        self.assertIn("occurrences: count(t, PASSAGE)", self.src)

    def test_all_three_surfaces_must_show_exactly_one(self):
        self.assertIn("8_agreement", self.src)
        self.assertIn("cOcc === 1 && pOcc === 1 && dOcc === 1", self.src)


class SubstitutionAndProvenanceTests(_Base):
    """10 — no false family fact may be substituted into the passage."""

    def test_forbidden_substitutions_are_defined_and_checked(self):
        self.assertIn("FORBIDDEN_SUBSTITUTIONS", self.src)
        self.assertIn("forbiddenSubstitutions", self.src)

    def test_it_guards_the_known_binding_defect(self):
        self.assertIn("father Jim", self.raw)
        self.assertIn("parents.deathDate", self.raw)

    def test_era_and_provenance_are_verified(self):
        self.assertIn("eraCorrect", self.src)
        self.assertIn("provenance:", self.src)


class ControlInFinallyTests(_Base):
    """11 — an earlier throw cannot skip the control check."""

    def test_control_verification_is_a_function_called_in_finally(self):
        self.assertIn("const verifyControl = async", self.src)
        fin = self.src[self.src.index("} finally {"):]
        self.assertIn("await verifyControl()", fin[:200])

    def test_it_records_whether_a_mutation_was_attempted(self):
        self.assertIn("checkedAfterAttemptedMutation", self.src)

    def test_it_compares_before_and_after_bytes(self):
        self.assertIn("JSON.stringify(ctlPre && ctlPre.body) === JSON.stringify(post.body)",
                      self.src)

    def test_the_control_is_never_patched(self):
        after = self.src[self.src.index("const CONTROL"):]
        self.assertNotIn("PATCH " + CONTROL, after)


class WithdrawnClaimTests(_Base):
    """12 — the over-broad networking claim is corrected in the file."""

    def test_the_claim_is_marked_withdrawn(self):
        self.assertIn("WITHDRAWN", self.raw)
        self.assertIn("Windows normally reaches WSL services", self.raw)

    def test_it_states_what_was_actually_observed(self):
        self.assertIn("isolated Claude browser session", self.raw)


if __name__ == "__main__":      # pragma: no cover
    unittest.main()
