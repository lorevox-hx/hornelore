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
        self.assertLess(self.src.index("openBtn.click()"),
                        self.src.index("lv10dBugPanelBtn"))


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
        self.assertIn('pass("3a_placed")', self.src)
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
        self.assertIn('pass("3a_placed") && p.placedCandidateId === TARGET', self.src)
        self.assertIn('pass("3b_promoted") && p.promotedCandidateId === TARGET', self.src)

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

    def test_it_proves_the_stale_version_case(self):
        self.assertIn("stale version", self.src.lower())
        self.assertIn("409", self.src)
