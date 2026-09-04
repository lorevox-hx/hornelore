"""Phase 1 probe — offline contract guards.

Written after a full review found ten mismatches between the probe and
the pushed product contracts. Four would have made the run fail or,
worse, LIE:

  * ``narrator_id`` is ``Query(..., min_length=1)`` on the candidate
    detail route — omitting it returns 422, so preflight could never pass.
  * That route returns ``{"item": shaped, "fetched_at": _now_iso()}``;
    reading fields off the wrapper yields undefined, and comparing whole
    responses would always report the control changed.
  * ``story_source_id`` is ``sha256("story:"+id)[:12]`` — the raw UUID is
    deliberately absent from anything a family reads, so searching for it
    could never match.
  * ``#lvNarratorCtxMemoir`` is a ``<div>``. Clicking it does nothing, so
    the probe would have found no passage in a popover that never opened
    and reported "preview failed — wrong API origin": the predicted
    answer, for entirely the wrong reason.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "scripts" / "ui" / "phase1_memoir_chain_probe.js"
DOMTEST = ROOT / "scripts" / "ui" / "phase1_row_selection_domtest.js"

TARGET = "447eee18-9ea5-4961-bf3d-157773d3cd44"
CONTROL = "5a56f942-001b-453b-8e4d-01fb82062013"
PERSON = "62e94e93-0e44-4fb0-bf19-4bfe847e163c"


def _code_only(src: str) -> str:
    """Strip comments without eating code.

    A naive ``/\\*.*?\\*/`` sub matched the ``/*`` inside the glob
    ``"**/api/operator/story-candidates/**"`` and swallowed the middle of
    the file. Block comments here always begin a line.
    """
    src = re.sub(r"(?ms)^[ \t]*/\*.*?\*/[ \t]*\n?", "", src)
    return re.sub(r"(?m)^\s*//[^\n]*$", "", src)


class _Base(unittest.TestCase):
    def setUp(self):
        self.raw = PROBE.read_text(encoding="utf-8")
        self.src = _code_only(self.raw)


class SyntaxTests(_Base):
    def test_both_scripts_parse(self):
        for f in (PROBE, DOMTEST):
            r = subprocess.run(["node", "--check", str(f)],
                               capture_output=True, text=True, timeout=60)
            self.assertEqual(0, r.returncode, r.stderr)

    def test_self_test_passes(self):
        r = subprocess.run(["node", str(PROBE), "--self-test"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertIn("SELF-TEST PASS", r.stdout)


class ApiEnvelopeTests(_Base):
    """The real candidate-detail contract."""

    def test_narrator_id_is_supplied_on_candidate_reads(self):
        self.assertIn("?narrator_id=${PERSON}", self.src)

    def test_the_envelope_is_unwrapped(self):
        self.assertIn("env.item", self.src)
        self.assertIn("env.fetched_at", self.src)

    def test_the_server_really_requires_narrator_id(self):
        route = (ROOT / "server" / "code" / "api" / "routers"
                 / "operator_story_review.py").read_text(encoding="utf-8")
        self.assertIn("narrator_id: str = Query(..., min_length=1)", route)
        self.assertIn('return {"item": shaped, "fetched_at": _now_iso()}', route)


class SourceDigestTests(_Base):
    def test_the_digest_is_computed_not_guessed(self):
        self.assertIn('crypto.createHash("sha256")', self.src)
        self.assertIn('"story:" + TARGET', self.src)

    def test_it_equals_the_servers_value(self):
        expected = hashlib.sha256(("story:" + TARGET).encode()).hexdigest()[:12]
        self.assertEqual("5d57a43ce780", expected)
        r = subprocess.run(["node", "-e",
                            "console.log(require('./scripts/ui/"
                            "phase1_memoir_chain_probe.js').SOURCE_ID)"],
                           capture_output=True, text=True, timeout=60, cwd=str(ROOT))
        self.assertEqual(expected, r.stdout.strip())

    def test_the_raw_uuid_is_never_sought_in_source_id(self):
        self.assertNotIn('source_id || "").includes(TARGET)', self.src)

    def test_the_server_hashes_it_deliberately(self):
        mc = (ROOT / "server" / "code" / "api" / "services"
              / "memoir_contract.py").read_text(encoding="utf-8")
        self.assertIn("must not appear in a document a", mc)


class ControlComparisonTests(_Base):
    def test_only_item_is_compared(self):
        self.assertIn("JSON.stringify(ctlPreItem) === JSON.stringify(post.item)", self.src)

    def test_fetched_at_is_excluded_by_design(self):
        self.assertIn("fetched_at excluded by design", self.raw)

    def test_the_control_is_verified_in_finally(self):
        fin = self.src[self.src.index("} finally {"):]
        self.assertIn("await verifyControl()", fin[:200])


class ProvenanceTests(_Base):
    def test_conversation_session_and_both_turn_rows_are_required(self):
        for f in ("conversation_id", "session_id", "source_user_turn_row_id",
                  "completed_assistant_turn_row_id"):
            self.assertIn(f, self.src)
        self.assertIn("source user turn row recorded", self.src)
        self.assertIn("completed assistant turn row recorded", self.src)

    def test_the_target_must_arrive_unplaced(self):
        """REVERSED 2026-09-01, and the reversal is the finding.

        This test used to require ``placement is building_years`` as a
        PRECONDITION. Run 20260901T212134Z refused on exactly that check
        and was right to: the candidate's ``era_candidates`` was ``[]``
        and its ``placement_source`` ``unknown``. The conversation's
        runtime era was ``building_years``; the STORY's placement was
        nothing. Capture declines to turn the first into the second, and
        the probe now tests the operator workflow that does.
        """
        self.assertNotIn("placement is building_years", self.src,
                         "the old precondition asserted a placement capture never makes")
        self.assertIn("target is unplaced", self.src)
        self.assertIn("UNPLACED_OK(it)", self.src)

    def test_immutable_fields_are_compared_before_and_after(self):
        self.assertIn("immutableSame", self.src)
        self.assertIn("immutable provenance changed during placement", self.raw)
        self.assertIn("immutable provenance changed during promotion", self.raw)


class PatchExactnessTests(_Base):
    def test_the_guard_matches_the_pathname_candidate_not_a_substring(self):
        self.assertIn("new URL(req.url()).pathname.split", self.src)
        self.assertIn("seg !== TARGET", self.src)

    def test_both_patch_bodies_are_verified_by_predicate(self):
        """The hand-rolled per-field flags became two predicates, so the
        SAME rule the offline tests exercise is the one the run applies."""
        self.assertIn("PLACEMENT_PATCH_OK({ sent", self.src)
        self.assertIn("PROMOTION_PATCH_OK({ sent", self.src)
        self.assertIn("UNRELATED_KEYS(sent, PLACEMENT_ALLOWED)", self.src)
        self.assertIn("UNRELATED_KEYS(sent, PROMOTION_ALLOWED)", self.src)

    def test_the_response_item_must_identify_target_pat_and_promoted(self):
        self.assertIn("resItem.id === TARGET", self.src)
        self.assertIn("resItem.narrator_id === PERSON", self.src)
        self.assertIn('resItem.review_status === "promoted"', self.src)

    def test_a_version_conflict_banner_refuses_the_link(self):
        self.assertIn(".story-conflict", self.src)
        self.assertIn("version-conflicted", self.raw)


class CanonicalContractTests(_Base):
    def test_every_required_canonical_field_gates_the_result(self):
        for cond in ("cb.person_id === PERSON", "cb.complete === true",
                     'captured_stories === "read"', "hits.length === 1",
                     "hit.era === ERA", "hit.source_id === SOURCE_ID",
                     'hit.review_status === "promoted"',
                     'hit.lane === "captured_story"'):
            self.assertIn(cond, self.src)


class TwoStageMemoirTests(_Base):
    def test_the_ctx_block_div_is_not_clicked(self):
        self.assertIn(".lv-narrator-ctx-cta", self.src)
        self.assertNotIn('getElementById("lvNarratorCtxMemoir").click()', self.src)

    def test_both_stages_exist_and_gate_the_result(self):
        self.assertIn("OPEN_MEMOIR_STAGE1", self.src)
        self.assertIn("OPEN_MEMOIR_STAGE2", self.src)
        self.assertIn("s1.found && s2.found && panel.visible", self.src)

    def test_it_does_not_expect_the_popover_to_issue_a_request(self):
        self.assertIn("NOT from opening the popover", self.raw)
        self.assertIn("canonicalSeen", self.src)

    def test_the_ctx_block_really_is_a_div(self):
        ui = (ROOT / "ui" / "hornelore1.0.html").read_text(
            encoding="utf-8", errors="replace")
        self.assertIn('<div id="lvNarratorCtxMemoir"', ui)
        self.assertIn('class="lv-narrator-ctx-cta"', ui)


class ExportOwnershipTests(_Base):
    def test_the_export_post_body_is_observed_and_required(self):
        self.assertIn("bodyPersonIsPat", self.src)
        self.assertIn("sent.person_id === PERSON", self.src)
        self.assertIn("exportPost && exportPost.bodyPersonIsPat", self.src)

    def test_export_waits_for_a_real_download(self):
        self.assertIn('page.waitForEvent("download"', self.src)
        self.assertNotIn("waitForTimeout(8000)", self.src)

    def test_export_is_skipped_when_preview_fails(self):
        self.assertLess(self.src.index("if (!previewOK)"),
                        self.src.index("btn.click()", self.src.index("if (!previewOK)")))


class ActiveNarratorTests(_Base):
    def test_all_three_conditions_are_required(self):
        self.assertIn("idOK && nameOK && lifecycleOK", self.src)
        self.assertIn('status === "ready"', self.src)

    def test_identity_is_reasserted_before_each_stage(self):
        for name in ("reassert", "beforePreview", "beforeExport"):
            self.assertIn(name, self.src)

    def test_pat_is_opened_before_the_bug_panel(self):
        """Re-anchored on the REAL opener.

        This asserted ordering against ``lv10dBugPanelBtn`` — an id that
        exists nowhere in the product. The test passed because the string
        was present in the PROBE, and the probe's own selector was the
        thing that was wrong: it matched nothing live, so the Bug Panel
        never opened. A guard pinned to a phantom selector confirms the
        typo instead of catching it.
        """
        self.assertLess(self.src.index("openBtn.click()"),
                        self.src.index('page.locator("#lv10dBugBtn")'))


class ExitCodeTests(_Base):
    def test_a_failed_or_refused_chain_exits_non_zero(self):
        self.assertIn("process.exitCode", self.src)
        self.assertIn("!R.refusals.length && !R.error) ? 0 : 1", self.src)

    def test_only_a_complete_pass_returns_zero(self):
        self.assertIn("(!bad && complete", self.src)


class ResumeTests(_Base):
    def test_resume_requires_the_named_links_and_the_control_pass(self):
        """UPDATED for the two-mutation workflow. There is no longer one
        prior link to trust but two, and they are checked separately so a
        run that placed and stopped can resume at promotion."""
        self.assertIn('L["3a_placed"]', self.src)
        self.assertIn('pass("3a_verify_placement")', self.src)
        self.assertIn('pass("3b_promoted")', self.src)
        self.assertIn('pass("7_control_unchanged")', self.src)

    def test_resume_requires_the_state_its_mode_claims(self):
        self.assertIn('status is promoted, as the prior report recorded', self.src)
        self.assertIn('still holds', self.src)

    def test_resume_carries_provenance_and_never_patches(self):
        self.assertIn("immutable: p.immutableBefore", self.src)
        self.assertIn("NOT re-promoting", self.raw)
        self.assertIn("NOT re-placing", self.raw)


class PreservedBehaviourTests(_Base):
    """What the review confirmed correct must survive the rewrite."""

    def test_row_selection_helpers_survive(self):
        for f in ("SELECT_ROW", "OPEN_DETAIL", "VERIFY_ROW"):
            self.assertIn(f"const {f} = function", self.src)

    def test_no_helper_is_arrow_wrapped_for_evaluate(self):
        for f in ("SELECT_ROW", "OPEN_DETAIL", "VERIFY_ROW", "ACTIVE_OK",
                  "PANEL_STATE"):
            self.assertNotIn(f"=> {f}(", self.src)

    def test_require_stays_inert(self):
        self.assertIn("if (require.main !== module) { return; }", self.src)
        out = subprocess.run(
            ["node", "-e", "const m=require('./scripts/ui/"
             "phase1_memoir_chain_probe.js');console.log(typeof m.SELECT_ROW)"],
            capture_output=True, text=True, timeout=60, cwd=str(ROOT))
        self.assertEqual("function", out.stdout.strip())


class BehaviouralDomTests(unittest.TestCase):
    def test_it_covers_the_contract_not_just_selection(self):
        src = DOMTEST.read_text(encoding="utf-8")
        for probe in ("source digest matches", "raw candidate UUID is NOT",
                      "changing fetched_at", "immutable provenance covers",
                      "memoir opening is two-stage", "COMPLETE passage",
                      "failed chain exits non-zero",
                      "REFUSES when another narrator is active"):
            self.assertIn(probe, src)

    def test_it_runs_green_where_a_browser_is_available(self):
        r = subprocess.run(["node", str(DOMTEST)], capture_output=True,
                           text=True, timeout=180, cwd=str(ROOT))
        combined = r.stdout + r.stderr
        if "Executable doesn't exist" in combined or "playwright install" in combined:
            self.skipTest("no Playwright browser binary here — run this in WSL")
        self.assertEqual(0, r.returncode, combined[-1500:])
        self.assertIn("DOM TEST PASS", r.stdout)

    def test_the_placement_workflow_runs_green_where_a_browser_exists(self):
        """The placement test drives the SHIPPED panel module, so it needs
        a real browser. It skips here for the same reason the row test
        does — and a skip is reported as a skip, never as a pass."""
        placement = ROOT / "scripts" / "ui" / "phase1_placement_workflow_domtest.js"
        r = subprocess.run(["node", str(placement)], capture_output=True,
                           text=True, timeout=240, cwd=str(ROOT))
        combined = r.stdout + r.stderr
        if "Executable doesn't exist" in combined or "playwright install" in combined:
            self.skipTest("no Playwright browser binary here — run this in WSL")
        self.assertEqual(0, r.returncode, combined[-2000:])
        self.assertIn("ALL PASS", r.stdout)


if __name__ == "__main__":      # pragma: no cover
    unittest.main()


class ResumeAndVerdictPredicateTests(unittest.TestCase):
    """The three resume/verdict rules, EXERCISED rather than grepped.

    A source assertion for these would match its own text, which has
    produced three vacuous guards in this file's history. Each rule is a
    pure exported function here, so the test runs it and checks answers.

    What they prevent:
      * a resumed run accepting a candidate whose provenance changed —
        `prior.immutable` was loaded and never compared;
      * a resumed run passing without proving it mutated nothing —
        skipping the Promote click is not the same as zero PATCHes;
      * a canonical 404 from :8000 being mislabelled "wrong API origin",
        which would hide a real canonical failure behind a known UI bug.
    """

    @classmethod
    def setUpClass(cls):
        js = (
            'const P = require("./scripts/ui/phase1_memoir_chain_probe.js");'
            'const IMM = { id: "c", narrator_id: "pat", conversation_id: "conv1",'
            '  session_id: "s1", source_user_turn_row_id: 2094,'
            '  completed_assistant_turn_row_id: 2095 };'
            'console.log(JSON.stringify({'
            '  same: P.RESUME_PROVENANCE_OK(IMM, JSON.parse(JSON.stringify(IMM))),'
            '  changedRow: P.RESUME_PROVENANCE_OK(IMM,'
            '    Object.assign({}, IMM, { source_user_turn_row_id: 9999 })),'
            '  changedConv: P.RESUME_PROVENANCE_OK(IMM,'
            '    Object.assign({}, IMM, { conversation_id: "other" })),'
            '  noPrior: P.RESUME_PROVENANCE_OK(null, IMM),'
            '  undefPrior: P.RESUME_PROVENANCE_OK(undefined, IMM),'
            '  clean: P.RESUMED_WITHOUT_MUTATION(0, false),'
            '  onePatch: P.RESUMED_WITHOUT_MUTATION(1, false),'
            '  attempted: P.RESUMED_WITHOUT_MUTATION(0, true),'
            '  both: P.RESUMED_WITHOUT_MUTATION(2, true),'
            '  vPass: P.PREVIEW_VERDICT("PASS", false),'
            '  vWrongOrigin: P.PREVIEW_VERDICT("FAIL", true),'
            '  vApi404: P.PREVIEW_VERDICT("FAIL", false),'
            '  vUndef: P.PREVIEW_VERDICT("FAIL", undefined),'
            '  vNotReached: P.PREVIEW_VERDICT("not_reached", false)}));'
        )
        r = subprocess.run(["node", "-e", js], capture_output=True, text=True,
                           timeout=60, cwd=str(ROOT))
        assert r.returncode == 0, r.stderr
        import json as _json
        cls.res = _json.loads(r.stdout)

    # ── 1. resumed provenance must match ─────────────────────────────
    def test_identical_provenance_is_accepted(self):
        self.assertTrue(self.res["same"])

    def test_a_changed_source_turn_row_is_refused(self):
        self.assertFalse(self.res["changedRow"])

    def test_a_changed_conversation_is_refused(self):
        self.assertFalse(self.res["changedConv"])

    def test_a_prior_report_without_provenance_is_refused(self):
        self.assertFalse(self.res["noPrior"])
        self.assertFalse(self.res["undefPrior"])

    # ── 2. a resumed run must prove zero mutation ────────────────────
    def test_zero_patches_and_no_attempt_is_clean(self):
        self.assertTrue(self.res["clean"])

    def test_a_single_patch_fails_the_resume(self):
        self.assertFalse(self.res["onePatch"])

    def test_an_attempted_promotion_fails_the_resume(self):
        self.assertFalse(self.res["attempted"])
        self.assertFalse(self.res["both"])

    # ── 3. wrong-origin classification is strict ────────────────────
    def test_a_passing_preview_reports_passed(self):
        self.assertEqual("passed", self.res["vPass"])

    def test_only_a_non_api_origin_404_is_called_wrong_origin(self):
        self.assertEqual("failed — wrong API origin", self.res["vWrongOrigin"])

    def test_an_api_origin_404_is_a_plain_failure(self):
        self.assertEqual("failed", self.res["vApi404"],
                         "a 404 from :8000 is a real canonical failure")

    def test_an_unmeasured_origin_is_not_assumed_wrong(self):
        self.assertEqual("failed", self.res["vUndef"])

    def test_a_preview_never_reached_is_not_wrong_origin(self):
        """CHANGED 2026-09-01. This used to assert "failed", which is how
        run 20260901T212134Z came to print `preview: failed` for a preview
        it had refused to attempt. A step that never ran is not a failed
        step, and reporting it as one overstates the damage."""
        self.assertEqual("not reached", self.res["vNotReached"])


class ResumeWiringTests(_Base):
    """The predicates must be wired into the flow, not merely exported."""

    def test_the_probe_calls_each_predicate(self):
        """Definition uses `const NAME = function (…)`, so `NAME(` marks a
        CALL. Both forms are required: exported-but-unused would leave the
        rule provable in isolation and absent from the run."""
        for fn in ("RESUME_PROVENANCE_OK", "RESUMED_WITHOUT_MUTATION",
                   "PREVIEW_VERDICT"):
            self.assertIn(f"const {fn} = function", self.src,
                          f"{fn} must be defined")
            self.assertIn(f"{fn}(", self.src, f"{fn} must be called")

    def test_resume_provenance_is_a_precondition(self):
        self.assertIn("resumed provenance identical to the prior report", self.src)

    def test_link_three_records_the_resume_mutation_evidence(self):
        for f in ("resumedWithoutMutation", "patchesObservedThisRun",
                  "promotionAttemptedThisRun"):
            self.assertIn(f, self.src)

    def test_the_verdict_uses_the_recorded_strict_result(self):
        self.assertIn("R.observed.previewWrongOrigin", self.src)


def _node(expr: str) -> str:
    """Evaluate an expression against the probe's real exports.

    EXERCISED, NOT GREPPED. A predicate can be present, exported and
    wrong; the only test that catches that is one that runs it.
    """
    r = subprocess.run(
        ["node", "-e",
         "const P=require('./scripts/ui/phase1_memoir_chain_probe.js');"
         f"console.log(JSON.stringify({expr}));"],
        capture_output=True, text=True, timeout=60, cwd=str(ROOT))
    if r.returncode != 0:
        raise AssertionError(r.stderr.strip())
    return r.stdout.strip()


class PlacementIsNotRuntimeEraTests(_Base):
    """The distinction the whole phase turns on.

    The conversation Pat spoke in carried era `building_years`. Her story
    candidate carried no era at all. Treating the first as the second is
    how a story gets filed into a memoir chapter on the strength of which
    screen the narrator happened to be looking at.
    """

    def test_capture_writes_no_placement(self):
        cap = (ROOT / "server" / "code" / "api" / "services"
               / "story_preservation.py").read_text(encoding="utf-8")
        self.assertIn("era_candidates=[]", cap,
                      "capture is expected to record NO placement")

    def test_only_an_operator_set_placement_counts(self):
        self.assertEqual("true", _node(
            'P.PLACEMENT_STATE_OK({era_candidates:["building_years"],'
            'placement_source:"operator_set"},"building_years")'))
        self.assertEqual("false", _node(
            'P.PLACEMENT_STATE_OK({era_candidates:["building_years"],'
            'placement_source:"unknown"},"building_years")'),
            "an era nobody confirmed is not a placement")

    def test_two_eras_is_not_a_placement(self):
        self.assertEqual("false", _node(
            'P.PLACEMENT_STATE_OK({era_candidates:["building_years","today"],'
            'placement_source:"operator_set"},"building_years")'))

    def test_the_unplaced_shape_is_the_one_the_live_read_returned(self):
        self.assertEqual("true", _node(
            'P.UNPLACED_OK({era_candidates:[],placement_source:"unknown",'
            'estimated_year_low:null,estimated_year_high:null})'))
        self.assertEqual("false", _node(
            'P.UNPLACED_OK({era_candidates:["building_years"],'
            'placement_source:"operator_set"})'))


class MutationBodyContractTests(_Base):
    """Neither PATCH may carry the other's field, or an unasked edit."""

    def test_placement_body_accepted(self):
        self.assertEqual("true", _node(
            'P.PLACEMENT_PATCH_OK({sent:{narrator_id:P.PERSON,review_version:1,'
            'era_candidates:["building_years"],placement_source:"operator_set"},'
            'era:P.ERA,person:P.PERSON,version:1})'))

    def test_placement_body_must_not_restatus(self):
        self.assertEqual("false", _node(
            'P.PLACEMENT_PATCH_OK({sent:{narrator_id:P.PERSON,review_version:1,'
            'era_candidates:["building_years"],placement_source:"operator_set",'
            'review_status:"promoted"},era:P.ERA,person:P.PERSON,version:1})'))

    def test_promotion_body_must_not_carry_placement(self):
        self.assertEqual("false", _node(
            'P.PROMOTION_PATCH_OK({sent:{narrator_id:P.PERSON,review_version:2,'
            'review_status:"promoted",era_candidates:["today"]},'
            'person:P.PERSON,version:2})'))

    def test_promotion_at_the_stale_version_is_rejected(self):
        """The defect this phase would otherwise have shipped: the panel
        sends the version it OBSERVED, so promoting without refetching
        after placement sends 1 when the server holds 2."""
        self.assertEqual("false", _node(
            'P.PROMOTION_PATCH_OK({sent:{narrator_id:P.PERSON,review_version:1,'
            'review_status:"promoted"},person:P.PERSON,version:2})'))
        self.assertEqual("true", _node(
            'P.PROMOTION_PATCH_OK({sent:{narrator_id:P.PERSON,review_version:2,'
            'review_status:"promoted"},person:P.PERSON,version:2})'))

    def test_unrelated_keys_are_named(self):
        self.assertEqual('["review_notes"]', _node(
            'P.UNRELATED_KEYS({narrator_id:"x",review_version:1,'
            'era_candidates:[],placement_source:"unknown",review_notes:"hi"},'
            'P.PLACEMENT_ALLOWED)'))

    def test_version_must_advance(self):
        self.assertEqual("true", _node("P.VERSION_ADVANCED(1,2)"))
        self.assertEqual("false", _node("P.VERSION_ADVANCED(2,2)"))
        self.assertEqual("false", _node("P.VERSION_ADVANCED(2,1)"))


class ResumeStateMachineTests(_Base):
    """Three states, three budgets, and no inference from the database."""

    def test_the_three_modes(self):
        self.assertEqual('"full"', _node("P.RESUME_MODE(null)"))
        self.assertEqual('"placed"', _node(
            "P.RESUME_MODE({placementProven:true,promotionProven:false})"))
        self.assertEqual('"promoted"', _node(
            "P.RESUME_MODE({placementProven:true,promotionProven:true})"))

    def test_an_unusable_prior_is_refused_not_guessed(self):
        self.assertEqual("null", _node(
            "P.RESUME_MODE({placementProven:false,promotionProven:false})"))
        self.assertEqual("-1", _node("P.PATCH_BUDGET(null)"))

    def test_the_budgets(self):
        self.assertEqual("2", _node('P.PATCH_BUDGET("full")'))
        self.assertEqual("1", _node('P.PATCH_BUDGET("placed")'))
        self.assertEqual("0", _node('P.PATCH_BUDGET("promoted")'),
                         "a fully resumed run must be allowed to mutate nothing")

    def test_a_mutation_is_proven_by_the_named_report_never_by_the_row(self):
        self.assertIn("NEVER BY", self.raw)
        self.assertIn('pass("3b_promoted") && p.promotedCandidateId === TARGET', self.src)

    def test_placement_resume_requires_the_verification_not_just_the_patch(self):
        """`3a_placed` records that a conforming PATCH returned 200.
        `3a_verify_placement` is the step that re-reads the row and proves
        the placement landed. Trusting the first alone would let a run
        whose verification FAILED authorise a resume that then skips
        placement entirely — the same mistake one level up."""
        self.assertIn('pass("3a_verify_placement")', self.src)
        self.assertIn("placementLinkOK && pass(\"3a_verify_placement\")", self.src)
        self.assertIn("placementShapeOK", self.src)
        self.assertIn("provenanceRecorded", self.src)

    def test_a_carried_forward_placement_still_counts(self):
        """A resumed run records `carried_forward`, not PASS, and re-proves
        the placement from the live row every time — so a chain of resumes
        must not demand a mutation nobody was allowed to repeat."""
        self.assertIn('placedLink === "carried_forward"', self.src)

    def test_an_attempted_but_unproven_placement_refuses_the_resume(self):
        self.assertIn("a placement was attempted but is not PROVEN", self.raw)

    def test_promotion_without_placement_is_an_unusable_prior(self):
        self.assertIn("claims promotion without placement", self.raw)

    def test_the_budget_is_enforced_before_the_request_leaves(self):
        self.assertIn("patchesAllowed", self.src)
        self.assertIn("over budget", self.src)
        self.assertIn('route.abort("blockedbyclient")', self.src)

    def test_the_ledger_checks_count_and_order(self):
        self.assertIn("expectedKinds", self.src)
        self.assertIn("placement>promotion", self.src)
        self.assertIn("budgetHeld", self.src)


class PreviewVerdictTests(_Base):
    """A step that never ran is not a failed step."""

    def test_not_reached_is_not_failed(self):
        self.assertEqual('"not reached"', _node('P.PREVIEW_VERDICT("not_reached")'))
        self.assertEqual('"not reached"', _node("P.PREVIEW_VERDICT(undefined)"))

    def test_a_real_failure_still_reads_as_failed(self):
        self.assertEqual('"failed"', _node('P.PREVIEW_VERDICT("FAIL",false)'))
        self.assertEqual('"failed — wrong API origin"',
                         _node('P.PREVIEW_VERDICT("FAIL",true)'))
        self.assertEqual('"passed"', _node('P.PREVIEW_VERDICT("PASS")'))


class PlacementWorkflowDomTestTests(unittest.TestCase):
    """The DOM test must drive the REAL panel, not an imitation of it."""

    def setUp(self):
        self.path = ROOT / "scripts" / "ui" / "phase1_placement_workflow_domtest.js"
        self.src = self.path.read_text(encoding="utf-8")

    def test_it_exists_and_parses(self):
        r = subprocess.run(["node", "--check", str(self.path)],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(0, r.returncode, r.stderr)

    def test_it_injects_the_shipped_panel_module(self):
        self.assertIn("bug-panel-story-review.js", self.src)
        self.assertIn("addScriptTag", self.src)
        self.assertIn("PANEL_SRC", self.src)

    def test_it_uses_selectOption_not_a_hand_dispatched_event(self):
        self.assertIn("selectOption", self.src)
        self.assertNotIn('dispatchEvent(new Event("change"))', self.src)

    def test_it_proves_the_409_case_that_is_actually_reachable(self):
        """The panel FORECLOSES the "forgot to refresh" stale promote:
        applyReview's success path nulls `_state.detail` and `_state.openId`
        and refetches, so no action survives a save. The reachable 409 is a
        second operator moving the version while the row is open, and that
        is what must be proven — along with the conflict banner the live
        probe checks for."""
        code = _code_only(self.src)
        self.assertIn("a version moved underneath", code)
        self.assertIn(".story-conflict", code)
        self.assertIn("review_version = 9", code,
                      "the version must move in the MOCK SERVER's store")
        self.assertIn("a successful save closes the detail", code)

    def test_the_panel_really_closes_the_detail_on_success(self):
        """The claim above is load-bearing, so it is pinned to the panel."""
        panel = (ROOT / "ui" / "js" / "bug-panel-story-review.js").read_text(
            encoding="utf-8")
        self.assertIn("_state.detail = null;", panel)
        self.assertIn("_state.openId = null;", panel)
        self.assertIn("return afterReviewApplied(pid);", panel)

    def test_confidence_is_a_string_bucket_not_a_float(self):
        """The fixture guessed a float because "confidence" sounds like
        one. The server types it ``Optional[str]`` and the live read
        returned ``"low"``; the panel renders it as a text child, so a
        number makes renderRow throw for every row and the panel presents
        as empty. A fixture whose types drift from the server tests
        nothing but itself."""
        # Checked against CODE ONLY. The comment above the fixture quotes
        # the wrong value in order to explain it, so a raw-source
        # assertion matches its own documentation and fails — the
        # self-matching-assertion trap, hit here for the fourth time.
        code = _code_only(self.src)
        self.assertIn('confidence: "low"', code)
        self.assertNotIn("confidence: 0.", code)
        route = (ROOT / "server" / "code" / "api" / "routers"
                 / "operator_story_review.py").read_text(encoding="utf-8")
        self.assertIn("confidence: Optional[str] = None", route)

    def test_the_mocked_list_shape_matches_the_server_exactly(self):
        """The list route returns ``_shape_for_operator``'s keys; the
        detail route returns a richer body. Serving one fat shape to both
        hides a panel that depends on a field the list never sends, so the
        mock's key set is pinned to the server's and drift fails here."""
        src = (ROOT / "server" / "code" / "api" / "routers"
               / "operator_story_review.py").read_text(encoding="utf-8")
        blk = src[src.index("def _shape_for_operator"):]
        blk = blk[blk.index("return {"):blk.index("\n    }")]
        server_keys = sorted(re.findall(r'"([a-z_]+)":', blk))
        lk = self.src[self.src.index("const LIST_KEYS = ["):]
        lk = lk[:lk.index("];")]
        test_keys = sorted(re.findall(r'"([a-z_]+)"', lk))
        self.assertEqual(server_keys, test_keys)

    def test_it_fails_fast_instead_of_cascading_timeouts(self):
        """One root cause presented as nine failures because each missing
        control waited out a 30s default. A zero-row render now aborts
        with diagnostics."""
        code = _code_only(self.src)
        self.assertIn("page.setDefaultTimeout(", code)
        self.assertIn("hardFail", code)
        self.assertIn("diagnose", code)

    def test_it_never_manufactures_a_pass(self):
        code = _code_only(self.src)
        for forbidden in ("createElement('div'", 'createElement("div"',
                          "_state.collapsed =", "_state.items ="):
            self.assertNotIn(forbidden, code,
                             "the test must not build the DOM it wants to see")

    def test_render_exceptions_are_surfaced_not_swallowed(self):
        """render() is called from a .then(), so a throw inside renderRow
        rejects a promise nobody awaits and the only visible symptom is an
        empty panel."""
        self.assertIn('page.on("pageerror"', self.src)
        self.assertIn("the panel rendered without throwing", self.src)

    def test_it_expands_the_collapsed_section(self):
        """Asserted against CODE, not prose: a comment's wording is not a
        contract, and matching one is how this guard broke when the file
        was rewritten and the sentence changed case."""
        code = _code_only(self.src)
        self.assertIn("#lv10dBpStoryReview .story-section-header", code)
        self.assertIn("header.click()", code)

    def test_the_probe_expands_the_section_before_reading_controls(self):
        probe = PROBE.read_text(encoding="utf-8")
        self.assertIn("2a0_section_expanded", probe)
        self.assertIn("#lv10dBpStoryReview .story-section-header", probe)
        self.assertNotIn("_state.collapsed = false", probe,
                         "expansion must go through the operator's own gesture")


class RefetchRaceTests(_Base):
    """Defect found in review of pushed 619636f.

    The fresh-run refetch pressed Enter and only THEN started waiting,
    swallowed the timeout into ``None``, and never read the body. Three
    faults in three lines: the response could complete before the listener
    existed; a failure became a silent ``null``; and nothing checked what
    came back. The probe could promote from a panel still holding the
    pre-placement version and call the chain proven.
    """

    @property
    def _refetch_block(self) -> str:
        """The refetch step ONLY.

        An earlier version of these tests anchored on ``if (MODE ===
        "full") {``, whose FIRST occurrence is the preconditions block ~250
        lines earlier. The slice therefore swallowed the placement step and
        flagged its ``catch(() => null)`` and sleeps — both of which are
        legitimate there, being armed inside a Promise.all and explicitly
        checked. A test that reads the wrong region reports the wrong file.
        """
        blk = self.src[self.src.index("const refetchFail"):]
        # rindex, not index: the refetchFail helper ITSELF emits a
        # step("3b_row_refetched", …) refusal, so slicing at the first
        # occurrence cut the block down to the helper and left the tests
        # inspecting four lines of error handling. The step that closes
        # the block is the LAST one.
        return blk[:blk.rindex('step("3b_row_refetched"')]

    def test_the_wait_is_armed_inside_the_same_promise_all_as_the_trigger(self):
        blk = self._refetch_block
        self.assertIn("await Promise.all([", blk)
        armed = blk.index("await Promise.all([")
        pressed = blk.index('filters.first().press("Enter")')
        self.assertLess(armed, pressed,
                        "the listener must exist before the gesture that fires it")

    def test_no_refetch_failure_is_swallowed(self):
        blk = self._refetch_block
        self.assertNotIn("catch(() => null)", blk,
                         "a swallowed timeout let the run continue unproven")
        self.assertIn("refetchFail", blk)

    def test_both_reads_must_carry_the_verified_version(self):
        self.assertIn("the refreshed list carries the wrong review version", self.raw)
        self.assertIn("the reopened detail carries the wrong review version", self.raw)
        self.assertIn("listRow.review_version !== versionAfterPlacement", self.src)
        self.assertIn("detItem.review_version !== versionAfterPlacement", self.src)

    def test_the_detail_must_be_the_target_and_show_the_placement(self):
        self.assertIn("the reopened detail is a different candidate", self.raw)
        self.assertIn("PLACEMENT_STATE_OK(detItem, ERA)", self.src)

    def test_the_promotion_carries_that_verified_version(self):
        self.assertIn("PROMOTION_PATCH_OK({ sent, person: PERSON,"
                      " version: versionAfterPlacement })", self.src)

    def test_the_promote_control_is_awaited_not_slept_for(self):
        blk = self._refetch_block
        self.assertIn('waitFor({ state: "visible"', blk)
        self.assertNotIn("waitForTimeout(", blk,
                         "the refetch step must be event-driven end to end")

    def test_the_era_selection_is_polled_not_slept_for(self):
        self.assertIn("the era control did not retain the choice", self.raw)
        self.assertIn("seen !== ERA", self.src)


class HeaderAccuracyTests(_Base):
    """A file header that understates what a script may change is the last
    place a stale sentence should live."""

    def test_it_states_exactly_two_authorized_mutations(self):
        head = self.raw[:self.raw.index('"use strict"')]
        self.assertIn("EXACTLY TWO AUTHORIZED MUTATIONS", head)
        self.assertIn("PLACEMENT", head)
        self.assertIn("PROMOTION", head)
        # NOT a NotIn on "ONE authorized mutation": the header quotes that
        # phrase in the note recording its own correction, so a naive
        # negative matches the documentation of the fix. Self-matching
        # assertion, fifth time. Assert the claim is made ONCE, as history.
        self.assertEqual(1, head.count("ONE authorized mutation"))
        self.assertIn('said "ONE authorized mutation', head)

    def test_the_chain_in_the_header_includes_placement(self):
        head = self.raw[:self.raw.index('"use strict"')]
        self.assertIn("operator PLACEMENT -> operator promotion", head)


class BugPanelOpenerTests(_Base):
    """Defect found by the first authorized live run, 20260901T232656Z.

    The probe never opened the Bug Panel. It looked for
    ``#lv10dBugPanelBtn`` — one word off from the real ``#lv10dBugBtn`` —
    then fell back to ``[onclick*="BugPanel"],[id*="ugPanel"]``. The panel
    is a NATIVE POPOVER opened by ``popovertarget``, so there is no onclick
    to match, and the id fallback matched ``lv10dBugPanel``: the popover
    DIV itself, whose click does nothing. ``if (el) el.click()`` then
    swallowed the miss, and the run died 30s later inside a section header
    that was present and invisible.

    Same family as ``#lvNarratorCtxMemoir``: an element that RESOLVES is
    not a control that WORKS. Nothing was mutated — 0 PATCHes, control
    PASS, exit 1.
    """

    def test_the_opener_is_the_header_button_not_a_guessed_id(self):
        self.assertIn('page.locator("#lv10dBugBtn")', self.src)
        # the attribute selector is used to RECORD what exists, not to choose
        self.assertIn('[popovertarget="lv10dBugPanel"]\').count()', self.src)

    def test_the_guessed_id_and_the_div_fallback_are_gone(self):
        code = _code_only(self.src)
        self.assertNotIn("lv10dBugPanelBtn", code)
        self.assertNotIn('[id*="ugPanel"]', code)
        self.assertNotIn("if (el) el.click()", code,
                         "a missed control must refuse, not silently do nothing")

    def test_the_opener_must_be_unique_and_opening_must_be_proven(self):
        self.assertIn("2a0_bug_panel_open", self.src)
        self.assertIn("the header Bug Panel launcher is not usable", self.raw)
        self.assertIn("Bug Panel did not open", self.raw)
        self.assertIn('waitFor({ state: "visible"', self.src)

    def test_the_panel_really_is_a_native_popover(self):
        html = (ROOT / "ui" / "hornelore1.0.html").read_text(encoding="utf-8")
        self.assertIn('<div id="lv10dBugPanel" popover>', html)
        self.assertIn('popovertarget="lv10dBugPanel"', html)
        self.assertIn('id="lv10dBugBtn"', html)

    def test_the_open_step_is_in_the_required_order(self):
        self.assertIn('"2a0_bug_panel_open",', self.src)
        order_blk = self.src[self.src.index("const order = ["):]
        order_blk = order_blk[:order_blk.index("]")]
        self.assertLess(order_blk.index("2a0_bug_panel_open"),
                        order_blk.index("2a0_section_expanded"),
                        "the panel must open before its section can expand")


class SelectorsExistInTheProductTests(_Base):
    """Every id the probe addresses must exist in the shipped UI.

    THE GUARD THAT WOULD HAVE CAUGHT ``#lv10dBugPanelBtn``. That id exists
    nowhere in the product; the probe waited 30s on an invisible header
    because the panel it addressed had never opened. A selector typo is
    invisible to every other offline test — the string is syntactically
    fine, the file parses, the self-test passes — and only a live run or
    this check can see it.

    ids created at runtime by JS are searched for in ui/js/ too, so this
    stays honest about elements the HTML never contains.
    """

    def _haystack(self) -> str:
        parts = [(ROOT / "ui" / "hornelore1.0.html").read_text(encoding="utf-8")]
        for f in sorted((ROOT / "ui" / "js").glob("*.js")):
            parts.append(f.read_text(encoding="utf-8"))
        return "\n".join(parts)

    def test_every_hash_id_the_probe_uses_exists(self):
        hay = self._haystack()
        ids = sorted(set(re.findall(r'["\'`]#([A-Za-z][\w-]+)', self.src)))
        self.assertTrue(ids, "the probe should address some ids")
        missing = [i for i in ids if i not in hay]
        self.assertEqual([], missing,
                         f"probe addresses ids absent from the shipped UI: {missing}")

    def test_the_probe_targets_the_session_time_opener(self):
        """TWO openers exist: the always-visible header button #205, and
        "Open Full Bug Panel" in the operator launcher — a surface that is
        not on screen during a Narrator Session. A bare
        [popovertarget="lv10dBugPanel"] matches both, so requiring
        uniqueness on it would refuse against a correct product."""
        html = (ROOT / "ui" / "hornelore1.0.html").read_text(encoding="utf-8")
        self.assertEqual(2, html.count('popovertarget="lv10dBugPanel"'),
                         "both openers are expected to exist")
        self.assertEqual(1, html.count('id="lv10dBugBtn"'),
                         "the header opener must be unique")
        self.assertIn('page.locator("#lv10dBugBtn")', self.src)
        self.assertIn("await bugBtn.isVisible()", self.src)

    def test_the_phantom_id_is_gone_from_code(self):
        code = _code_only(self.src)
        hay = self._haystack()
        self.assertNotIn("lv10dBugPanelBtn", code)
        self.assertNotIn("lv10dBugPanelBtn", hay,
                         "if the product ever gains this id, revisit the opener")


class BugPanelLauncherContractTests(_Base):
    """The launcher path, pinned against the shipped page.

    Run 20260901T232656Z refused with zero mutations because the probe's
    launcher selector matched nothing. No offline test could see it: the
    file parsed, the self-test was green, the string was syntactically
    perfect. These guards close that gap.
    """

    LAUNCHER = ROOT / "scripts" / "ui" / "phase1_bugpanel_launcher_domtest.js"

    def setUp(self):
        super().setUp()
        self.html = (ROOT / "ui" / "hornelore1.0.html").read_text(encoding="utf-8")
        self.dom = self.LAUNCHER.read_text(encoding="utf-8")

    def test_the_launcher_test_exists_and_parses(self):
        r = subprocess.run(["node", "--check", str(self.LAUNCHER)],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(0, r.returncode, r.stderr)

    def test_it_extracts_the_markup_rather_than_inventing_it(self):
        """Writing a plausible button would test the author's idea of the
        launcher — precisely the thing that was wrong."""
        self.assertIn("hornelore1.0.html", self.dom)
        self.assertIn("extractLauncher", self.dom)
        self.assertIn("extractPopoverOpenTag", self.dom)
        # Assert what is MOUNTED, not whether the string "<button" occurs
        # anywhere: the extractor legitimately searches for "<button" and
        # the assertion messages name it. A crude negative flagged both.
        mounted = self.dom[self.dom.index("await page.setContent("):]
        mounted = mounted[:mounted.index("`);")]
        self.assertIn("${launcherHTML}", mounted)
        self.assertIn("${popoverTag}", mounted)
        self.assertNotIn("<button", mounted,
                         "the mounted page must carry the SHIPPED launcher, not a copy")

    def test_the_probe_requires_visible_and_enabled(self):
        self.assertIn("await bugBtn.isVisible()", self.src)
        self.assertIn("await bugBtn.isEnabled()", self.src)
        self.assertIn("the header Bug Panel launcher is not usable", self.raw)

    def test_the_probe_gates_on_popover_open_not_a_side_effect(self):
        self.assertIn('matches(":popover-open")', self.src)
        self.assertIn("never matched :popover-open", self.raw)

    def test_the_probe_refuses_a_hidden_section_header(self):
        self.assertIn("the story-review section header is hidden", self.raw)
        self.assertIn("story-review section header is not visible", self.raw)
        self.assertIn("the story-review controls never appeared", self.raw)

    def test_two_separate_evidence_links_are_recorded(self):
        self.assertIn('step("2a0_bug_panel_open"', self.src)
        self.assertIn('step("2a0_section_expanded"', self.src)
        order_blk = self.src[self.src.index("const order = ["):]
        order_blk = order_blk[:order_blk.index("]")]
        self.assertIn("2a0_bug_panel_open", order_blk)
        self.assertIn("2a0_section_expanded", order_blk)

    def test_the_shipped_launcher_contract_holds(self):
        self.assertEqual(1, self.html.count('id="lv10dBugBtn"'))
        self.assertEqual(2, self.html.count('popovertarget="lv10dBugPanel"'))
        self.assertIn('<div id="lv10dBugPanel" popover>', self.html)
        self.assertNotIn("lv10dBugPanelBtn", self.html)

    def test_it_runs_green_where_a_browser_is_available(self):
        r = subprocess.run(["node", str(self.LAUNCHER)], capture_output=True,
                           text=True, timeout=180, cwd=str(ROOT))
        combined = r.stdout + r.stderr
        if "Executable doesn't exist" in combined or "playwright install" in combined:
            self.skipTest("no Playwright browser binary here — run this in WSL")
        self.assertEqual(0, r.returncode, combined[-2000:])
        self.assertIn("ALL PASS", r.stdout)


class WrongOriginDiagnosticTests(_Base):
    """The probe's own requests must not dilute its own diagnostic.

    Run 20260904T123556Z reported a bare ``preview: failed`` while the same
    report recorded three UI-issued 404s against :8082. The predicate
    averaged over EVERY canonical request for Pat, including the probe's own
    step-4 :8000 check, which correctly returns 200 — so ``every()`` was
    false and the wrong-origin label was suppressed. The guard written to
    prevent that mislabelling was defeated by the instrument beside it.
    """

    def test_only_ui_issued_requests_are_considered(self):
        self.assertIn("const uiCanonical = patCanonical.filter", self.src)
        self.assertIn('!c.origin.includes("8000")', self.src)
        self.assertIn("uiCanonical.every((c) => c.status === 404)", self.src)

    def test_the_probe_records_the_split(self):
        for f in ("uiIssued", "probeIssued", "uiAll404"):
            self.assertIn(f, self.src)

    def test_an_api_origin_404_is_still_a_real_failure(self):
        self.assertIn("A 404 from :8000 remains a real canonical", self.raw)

    def test_the_relative_fetch_defect_is_FIXED(self):
        """INVERTED 2026-09-04, and the inversion is the point.

        This asserted the bare relative fetch EXISTED, because it was the
        defect the preview step reported. Its own message said: "if this ever
        becomes absolute, the wrong-origin branch should stop firing." It
        became absolute, and this test failed on the same commit that fixed
        it — which is a guard doing its job, not a regression.

        The wrong-origin branch stays in the probe: it is still the correct
        label for any future UI-issued canonical read that misses the API
        origin. What must not survive is the defect itself.
        """
        html = (ROOT / "ui" / "hornelore1.0.html").read_text(encoding="utf-8")
        self.assertNotIn('fetch("/api/memoir/canonical?person_id="', html,
                         "the relative canonical fetch is the BUG-224 class "
                         "defect; it must not come back")
        self.assertIn('fetch(_O + "/api/memoir/canonical?person_id="', html)


class MemoirCanonicalOriginTests(unittest.TestCase):
    """The canonical fetch must use the configured API origin.

    Phase 1 live run ``20260904T123556Z`` proved the chain to canonical and
    then failed at preview: ``hornelore1.0.html`` fetched
    ``/api/memoir/canonical`` with a BARE RELATIVE URL, which resolves
    against the UI static server on :8082. That server does not proxy
    ``/api/*``, so three canonical reads 404'd and the memoir popover never
    opened — while the identical query against the API origin returned 200
    in the same run.

    This is the same defect as BUG-224 (fixed 2026-05-01 in the Bug Panel
    modules), missed in the page's own inline script.
    """

    def setUp(self):
        self.html = (ROOT / "ui" / "hornelore1.0.html").read_text(encoding="utf-8")

    def test_no_bare_api_fetch_survives_in_the_page(self):
        """THE GUARD THAT WOULD HAVE CAUGHT IT. A relative /api fetch is
        invisible to every other offline test: the file parses, the string
        is well-formed, and only a live run sees the 404."""
        bare = re.findall(r'fetch\(\s*"(/api/[^"]*)"', self.html)
        self.assertEqual([], bare,
                         f"bare relative /api fetches resolve to the UI server: {bare}")

    def test_the_canonical_fetch_composes_with_the_origin(self):
        self.assertIn('fetch(_O + "/api/memoir/canonical?person_id="', self.html)

    def test_the_origin_follows_the_documented_bug224_pattern(self):
        self.assertIn('const _O = (typeof ORIGIN !== "undefined" && ORIGIN) '
                      '|| "http://localhost:8000";', self.html)
        api = (ROOT / "ui" / "js" / "api.js").read_text(encoding="utf-8")
        self.assertIn('const ORIGIN   = window.LOREVOX_API || "http://localhost:8000";', api,
                      "ORIGIN must remain the single configured source")

    def test_api_js_loads_before_the_inline_script_uses_ORIGIN(self):
        load_at = self.html.index('src="js/api.js"')
        use_at = self.html.index('fetch(_O + "/api/memoir/canonical')
        self.assertLess(load_at, use_at, "ORIGIN must be defined before it is read")

    def test_the_shipped_expression_really_targets_the_configured_origin(self):
        """EXERCISED, not grepped: the expression is lifted verbatim out of
        the shipped page and evaluated with ORIGIN set to a sentinel."""
        m = re.search(r'(const _O = \(typeof ORIGIN[^\n]*\n)\s*'
                      r'const r = await fetch\((_O \+ "/api/memoir/canonical\?person_id="\)?)',
                      self.html)
        self.assertIsNotNone(m, "could not lift the shipped expression")
        js = (
            'const ORIGIN = "http://sentinel.invalid:9999";\n'
            + m.group(1)
            + 'const personId = "abc-123";\n'
            'const url = _O + "/api/memoir/canonical?person_id=" '
            '+ encodeURIComponent(personId);\n'
            'if (!url.startsWith("http://sentinel.invalid:9999/api/memoir/canonical")) {\n'
            '  console.error("WRONG ORIGIN: " + url); process.exit(1);\n'
            '}\n'
            'console.log("OK " + url);\n'
        )
        r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=60)
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("sentinel.invalid:9999", r.stdout)


class ResumeVersionExpectationTests(_Base):
    """The version a resumed run expects depends on how far the prior got.

    Resume ``20260904T125120Z`` refused because the check compared the live
    row against ``placementAfter.review_version`` (v2) in BOTH modes. After a
    full run the promotion has bumped it again, so the row was at v3. Nothing
    was mutated and the control passed — but the refusal was the probe's
    arithmetic, not the product's state, and ``promoted`` mode had never been
    exercised before that run.
    """

    def test_the_expected_version_is_derived_per_mode(self):
        self.assertIn('(p.mutations || []).filter((m) => m.kind === "promotion")', self.src)
        self.assertIn("promotionProven", self.src)
        self.assertIn("_promoMut.versionTransition.to", self.src)
        self.assertIn("p.placementAfter.review_version", self.src)

    def test_an_underivable_version_refuses_the_resume(self):
        self.assertIn("cannot determine the version the prior run left", self.raw)

    def test_the_precondition_uses_the_derived_value(self):
        self.assertIn("versionBefore === prior.expectedVersion", self.src)
        self.assertNotIn("versionBefore === prior.placement.review_version", self.src)

    def test_the_label_names_which_mutation_set_the_version(self):
        self.assertIn("the prior run's promotion left", self.src)
        self.assertIn("the prior run's placement left", self.src)

    def test_the_real_report_yields_v3_for_promoted_mode(self):
        """Exercised against the ACTUAL prior report, not a synthetic one."""
        rep = (ROOT / ".runtime" / "eval" / "phase1-memoir-chain"
               / "20260904T123556Z" / "report.json")
        if not rep.exists():
            self.skipTest("prior run evidence not present (.runtime is gitignored)")
        import json
        r = json.loads(rep.read_text(encoding="utf-8"))
        promo = [m for m in r.get("mutations", []) if m["kind"] == "promotion"][-1]
        self.assertEqual(3, promo["versionTransition"]["to"])
        self.assertEqual(2, r["placementAfter"]["review_version"],
                         "placement left v2; promotion left v3 — the distinction "
                         "this class exists to preserve")


class PopoverVisibilityTests(_Base):
    """`offsetParent` cannot decide whether a native popover is open.

    Resume ``20260904T125523Z`` reported ``popoverVisible=false`` while the
    same call read ``occurrences=1`` and 1408 characters out of the panel:
    the passage was on screen and the test said the panel was shut.
    ``#memoirScrollPopover`` is ``<div popover="auto">``; native popovers
    render in the top layer, which the UA stylesheet positions ``fixed``,
    and ``offsetParent`` is ``null`` for every fixed element.

    CLAUDE.md already carried this rule from the Bug Panel — *gate on
    ``:popover-open``, not on a side effect*. It was applied there and not
    here, which is why the same class of defect surfaced twice.
    """

    def test_offsetparent_decides_nothing_in_the_probe(self):
        self.assertNotIn("offsetParent", self.src,
                         "a fixed-position element always reports null")

    def test_the_platform_open_state_is_the_ONLY_basis(self):
        self.assertIn('el.matches(":popover-open")', self.src)
        self.assertIn("visible: open", self.src)

    def test_there_is_NO_fallback_basis(self):
        """A first fix here kept a bounding-box backstop for engines without
        ``:popover-open``. That is itself inference from a side effect — the
        exact mistake the rule forbids — and a closed element can occupy a
        box, so the fallback could only ever mask a real failure. The
        launcher test asserts the selector is supported before anything
        depends on it. One instrument, and it is the platform's own answer."""
        for gone in ("renderedBox", "visibilityBasis", "boxed",
                     "getBoundingClientRect"):
            self.assertNotIn(gone, self.src,
                             f"{gone} reintroduces a second visibility basis")

    def test_the_memoir_panel_really_is_a_native_popover(self):
        html = (ROOT / "ui" / "hornelore1.0.html").read_text(encoding="utf-8")
        self.assertIn('<div id="memoirScrollPopover" popover="auto"', html,
                      "if this stops being a popover, the visibility basis "
                      "must be revisited")

    def test_the_run_that_exposed_it_is_recorded(self):
        self.assertIn("20260904T125523Z", self.raw)


class MemoirPopoverDomTestTests(unittest.TestCase):
    """The memoir popover gets its OWN proof, not an inherited assumption."""

    PATH = ROOT / "scripts" / "ui" / "phase1_memoir_popover_domtest.js"

    def setUp(self):
        self.src = self.PATH.read_text(encoding="utf-8")

    def test_it_exists_and_parses(self):
        r = subprocess.run(["node", "--check", str(self.PATH)],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(0, r.returncode, r.stderr)

    def test_it_extracts_shipped_markup_rather_than_inventing_it(self):
        self.assertIn("extractPopoverOpenTag", self.src)
        self.assertIn("extractPeekButton", self.src)
        mounted = self.src[self.src.index("await page.setContent("):]
        mounted = mounted[:mounted.index("`);")]
        self.assertIn("${popoverTag}", mounted)
        self.assertIn("${peekButton}", mounted)
        self.assertNotIn("popover=", mounted,
                         "the mounted page must carry the SHIPPED tag, not a copy")

    def test_it_exercises_the_probe_s_own_PANEL_STATE(self):
        self.assertIn("const { PANEL_STATE } = P;", self.src)
        self.assertIn("page.evaluate(PANEL_STATE, PASSAGE)", self.src)

    def test_it_proves_all_five_required_facts(self):
        for fact in ("the shipped control OPENS it and it matches :popover-open",
                     "THE TRAP: offsetParent is null on the OPEN popover",
                     "offsetParent is not the verdict anywhere in the probe",
                     "closing it makes :popover-open false",
                     "the passage must appear exactly once"):
            self.assertIn(fact, self.src)

    def test_it_records_that_text_presence_is_not_openness(self):
        self.assertIn("occurrences cannot be used as an openness signal either",
                      self.src)

    def test_it_runs_green_where_a_browser_is_available(self):
        r = subprocess.run(["node", str(self.PATH)], capture_output=True,
                           text=True, timeout=180, cwd=str(ROOT))
        combined = r.stdout + r.stderr
        if "Executable doesn't exist" in combined or "playwright install" in combined:
            self.skipTest("no Playwright browser binary here — run this in WSL")
        self.assertEqual(0, r.returncode, combined[-2000:])
        self.assertIn("ALL PASS", r.stdout)
