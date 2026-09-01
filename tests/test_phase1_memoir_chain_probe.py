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
    """Strip comments WITHOUT eating code.

    A naive ``/\*.*?\*/`` sub is wrong here: the glob
    ``"**/api/operator/story-candidates/**"`` contains ``/*``, so the
    regex matched from inside that string literal to the next ``*/`` and
    swallowed the middle of the file. Eleven assertions then failed
    against source that had been corrupted by the test helper — and in a
    different arrangement they would have passed falsely instead.

    Block comments in this file always begin a line, so only those are
    removed.
    """
    src = re.sub(r"(?ms)^[ \t]*/\*.*?\*/[ \t]*\n?", "", src)
    return re.sub(r"(?m)^\s*//[^\n]*$", "", src)


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
        """*(Was `showsFullPassage`, which searched the whole document
        body. The check is now row-scoped and compares the selected row's
        .story-transcript for equality with the complete passage.)*"""
        self.assertIn("2b_detail_verified", self.src)
        self.assertIn("transcriptEqualsTarget", self.src)
        self.assertNotIn("showsFullPassage", self.src)

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


class RequireIsInertTests(_Base):
    """A bare require() must not start a live probe run.

    The behavioural DOM test imports the selection functions from the
    probe. On the first attempt that import executed the probe's main
    body: it resolved Playwright, created an output directory and
    launched a browser against the live stack.
    """

    def test_side_effects_are_behind_a_direct_execution_guard(self):
        self.assertIn("if (require.main !== module) { return; }", self.src)

    def test_the_guard_precedes_every_side_effect(self):
        i_guard = self.src.index("require.main !== module")
        for effect in ("chromium.launch", "fs.mkdirSync", 'require("playwright")'):
            self.assertLess(i_guard, self.src.index(effect),
                            f"{effect} must sit behind the guard")

    def test_requiring_it_exports_the_contract_and_does_nothing_else(self):
        out = subprocess.run(
            ["node", "-e",
             "const m=require('./scripts/ui/phase1_memoir_chain_probe.js');"
             "console.log(Object.keys(m).sort().join(','))"],
            capture_output=True, text=True, timeout=60, cwd=str(ROOT))
        self.assertEqual(0, out.returncode, out.stderr)
        self.assertEqual("ACTIVE_OK,OPEN_DETAIL,SELECT_ROW,VERIFY_ROW",
                         out.stdout.strip())


class BehaviouralDomTests(unittest.TestCase):
    """The real DOM contract, exercised in a browser.

    Source-string assertions passed against code that could never work:
    the probe looked for getAttribute("onclick") while the shipped panel
    attaches handlers with addEventListener. Only a behavioural test sees
    that, so this runs the probe's own exported functions against a
    synthetic panel built the way the real one is built.
    """

    DOMTEST = ROOT / "scripts" / "ui" / "phase1_row_selection_domtest.js"

    def test_the_dom_test_exists_and_parses(self):
        self.assertTrue(self.DOMTEST.is_file())
        r = subprocess.run(["node", "--check", str(self.DOMTEST)],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(0, r.returncode, r.stderr)

    def test_it_covers_the_handler_mismatch_that_greps_missed(self):
        src = self.DOMTEST.read_text(encoding="utf-8")
        self.assertIn("addEventListener", src)
        self.assertIn("an onclick-attribute search would have found nothing", src)
        self.assertIn("a global first() would have promoted row-other", src)

    def test_it_runs_green_where_a_browser_is_available(self):
        r = subprocess.run(["node", str(self.DOMTEST)],
                           capture_output=True, text=True, timeout=180, cwd=str(ROOT))
        combined = r.stdout + r.stderr
        if "Executable doesn't exist" in combined or "playwright install" in combined:
            self.skipTest("no Playwright browser binary here — run this in WSL")
        self.assertEqual(0, r.returncode, combined[-1500:])
        self.assertIn("DOM TEST PASS", r.stdout)


class CanonicalStrictnessTests(_Base):
    def test_canonical_requires_the_complete_passage(self):
        self.assertIn('String(s.text || "").includes(PASSAGE)', self.src)
        self.assertNotIn('String(s.text || "").includes(PASSAGE_HEAD)', self.src)

    def test_era_and_source_id_gate_the_result(self):
        self.assertIn("canonHits.length === 1 && eraOK && srcOK", self.src)
        self.assertIn('hit.era === ERA', self.src)
        self.assertIn("String(hit.source_id || \"\").includes(TARGET)", self.src)


class SubstitutionScanTests(_Base):
    def test_the_full_panel_text_is_preserved(self):
        self.assertIn("fullText: t", self.src)

    def test_the_scan_is_case_insensitive_over_all_three_surfaces(self):
        self.assertIn("haystack.includes(lc(f))", self.src)
        self.assertIn("lc(panel.fullText)", self.src)
        self.assertIn("lc(R.docxFullText)", self.src)

    def test_it_no_longer_inspects_only_the_head(self):
        self.assertNotIn("(panel.head || \"\").includes(f)", self.src)


class PromotionProofTests(_Base):
    def test_proof_is_recorded_only_after_a_successful_target_patch(self):
        self.assertIn("R.observed.patch && R.observed.patch.targetedTarget"
                      " && R.observed.patch.status < 400", self.src)

    def test_it_is_saved_immediately(self):
        i = self.src.index("R.promotedAt = new Date().toISOString();")
        self.assertIn("save();", self.src[i:i + 120])

    def test_a_failed_patch_records_no_proof(self):
        self.assertIn("no promotion proof recorded", self.raw)


class FilterSubmissionTests(_Base):
    def test_the_filter_is_submitted_not_merely_filled(self):
        self.assertIn('filter.press("Enter")', self.src)

    def test_it_waits_for_the_refreshed_list(self):
        i = self.src.index('filter.press("Enter")')
        window = self.src[max(0, i - 400):i]
        self.assertIn("waitForResponse", window)

    def test_it_uses_the_real_filter_class(self):
        self.assertIn(".story-filter-input", self.src)


class RowScopedSelectionTests(_Base):
    def test_it_uses_the_real_dom_classes(self):
        for cls in (".story-row", ".story-preview-btn", ".story-detail",
                    ".story-transcript"):
            self.assertIn(cls, self.src)

    def test_no_onclick_search_is_used_to_open_a_story_row(self):
        """*(Was a blanket ban on getAttribute("onclick"). Too broad: the
        narrator Open button legitimately carries one —
        hornelore1.0.html:6435 renders onclick="lv80SwitchPerson('…')" —
        and that is the established switcher path the cohort proved across
        ten narrators. The ban belongs only to story-row opening, where
        handlers are addEventListener.)*"""
        opener = self.src[self.src.index("const OPEN_DETAIL"):
                          self.src.index("const VERIFY_ROW")]
        self.assertNotIn("onclick", opener)
        self.assertIn(".story-preview-btn", opener)
        # The one permitted use is the narrator Open button.
        self.assertEqual(1, self.src.count('getAttribute("onclick")'))
        i = self.src.index('getAttribute("onclick")')
        self.assertIn("Open", self.src[max(0, i - 220):i])

    def test_row_selection_requires_exactly_one_match(self):
        self.assertIn("matching.length === 1", self.src)

    def test_the_promote_click_is_scoped_to_the_row(self):
        self.assertIn('page.locator(".story-row", { hasText: PASSAGE_HEAD })', self.src)

    def test_the_transcript_must_equal_the_target(self):
        self.assertIn("transcriptEqualsTarget", self.src)
        self.assertIn("text === full.trim()", self.src)


class EvaluateSerialisationTests(_Base):
    """page.evaluate serialises the function it is GIVEN.

    Wrapping a shared helper in an arrow — evaluate(([h,f]) =>
    VERIFY_ROW(h,f), …) — sends the ARROW into the page, where
    VERIFY_ROW does not exist. The DOM test caught this as
    "VERIFY_ROW is not defined"; the probe carried the identical line
    and would have thrown live, immediately after promoting. Only a
    behavioural test could see it: node --check, the self-test and every
    source assertion passed.
    """

    def test_no_shared_helper_is_wrapped_in_an_arrow(self):
        for name in ("SELECT_ROW", "OPEN_DETAIL", "VERIFY_ROW"):
            self.assertNotIn(f"=> {name}(", self.src,
                             f"{name} must be passed to evaluate directly")

    def test_verify_row_takes_one_serialisable_argument(self):
        self.assertIn("const VERIFY_ROW = function (args)", self.src)
        self.assertIn("page.evaluate(VERIFY_ROW,", self.src)

    def test_all_three_helpers_are_passed_directly(self):
        for name in ("SELECT_ROW", "OPEN_DETAIL", "VERIFY_ROW"):
            self.assertIn(f"page.evaluate({name}", self.src)

    def test_the_dom_test_passes_them_directly_too(self):
        dom = (ROOT / "scripts" / "ui"
               / "phase1_row_selection_domtest.js").read_text(encoding="utf-8")
        for name in ("SELECT_ROW", "OPEN_DETAIL", "VERIFY_ROW"):
            self.assertNotIn(f"=> {name}(", dom)


class ActiveNarratorTests(_Base):
    """The Bug Panel filter is NOT the active narrator.

    The memoir panel and export read state.person_id. Filtering the panel
    to Pat while another narrator is active would promote Pat's candidate
    correctly and then preview someone else's memoir — and report that as
    Pat's preview failure. The state mutation was already protected; the
    evidence was not.
    """

    def test_pat_is_opened_through_the_real_switcher_first(self):
        self.assertIn("1b_narrator_active", self.src)
        i_open = self.src.index("openBtn.click()")
        i_panel = self.src.index("lv10dBugPanelBtn")
        self.assertLess(i_open, i_panel,
                        "Pat must be opened before the Bug Panel is used")

    def test_all_three_identity_conditions_are_required(self):
        self.assertIn("idOK && nameOK && lifecycleOK", self.src)
        self.assertIn("st.person_id === args.personId", self.src)
        self.assertIn("names.indexOf(args.displayName) > -1", self.src)
        self.assertIn('status === "ready"', self.src)

    def test_the_exact_display_name_is_pinned(self):
        self.assertIn("const DISPLAY_NAME", self.src)
        self.assertIn("\\u00b7 Pat", self.raw)

    def test_identity_is_reasserted_before_preview_and_export(self):
        self.assertIn("activeBeforePreview", self.src)
        self.assertIn("activeBeforeExport", self.src)

    def test_a_narrator_change_refuses_rather_than_reports(self):
        self.assertIn("REFUSED preview: active narrator is no longer Pat", self.raw)
        self.assertIn("REFUSED export: active narrator is no longer Pat", self.raw)

    def test_the_reassertion_precedes_each_action(self):
        self.assertLess(self.src.index("activeBeforePreview"),
                        self.src.index("lvNarratorCtxMemoir"))
        self.assertLess(self.src.index("activeBeforeExport"),
                        self.src.index("exportBtn.click()"))


class FilterStrictnessTests(_Base):
    def test_exactly_one_filter_input_is_required(self):
        self.assertIn("nFilters !== 1", self.src)

    def test_the_list_response_must_be_pats_and_successful(self):
        self.assertIn("listRes.status() < 400 && listRes.url().includes(PERSON)", self.src)

    def test_it_never_continues_silently(self):
        self.assertIn("review list for Pat was not observed to succeed", self.raw)
        self.assertNotIn("if (await filter.count()) {", self.src)


class ActiveNarratorBehaviouralTests(unittest.TestCase):
    DOMTEST = ROOT / "scripts" / "ui" / "phase1_row_selection_domtest.js"

    def test_the_dom_test_covers_a_foreign_active_narrator(self):
        src = self.DOMTEST.read_text(encoding="utf-8")
        self.assertIn("REFUSES when another narrator is active", src)
        self.assertIn("the Bug Panel still shows Pat's row", src)
        self.assertIn("REFUSES when the card shows a different name", src)
        self.assertIn("REFUSES when the open lifecycle has not reached ready", src)
        self.assertIn("REFUSES when no narrator is active at all", src)

    def test_it_runs_green_where_a_browser_is_available(self):
        r = subprocess.run(["node", str(self.DOMTEST)], capture_output=True,
                           text=True, timeout=180, cwd=str(ROOT))
        combined = r.stdout + r.stderr
        if "Executable doesn't exist" in combined or "playwright install" in combined:
            self.skipTest("no Playwright browser binary here — run this in WSL")
        self.assertEqual(0, r.returncode, combined[-1500:])
        self.assertIn("DOM TEST PASS", r.stdout)
