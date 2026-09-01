"""Offline safeguards for the focused Walt browser acceptance script."""
from __future__ import annotations

import pathlib
import re
import subprocess
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ui" / "run_walt_seven_era_conversation.js"


class WaltSevenEraBrowserScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def test_javascript_parses(self):
        subprocess.run(["node", "--check", str(SCRIPT)], check=True)

    def test_self_test_is_offline_and_green(self):
        result = subprocess.run(
            ["node", str(SCRIPT), "--self-test"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SELF-TEST PASS", result.stdout)

    def test_all_seven_era_ids_are_literal_and_ordered(self):
        ids = re.findall(r'^\s+id: "([a-z_]+)",$', self.source, re.MULTILINE)
        self.assertEqual(ids[:7], [
            "earliest_years", "early_school_years", "adolescence",
            "coming_of_age", "building_years", "later_years", "today",
        ])

    def test_no_person_creation_or_deletion_request_exists(self):
        self.assertNotRegex(self.source, r'fetch\([^\n]+method:\s*["\'](?:POST|DELETE)["\']')
        self.assertNotIn("/api/intake", self.source)
        self.assertNotIn("/api/people/erase", self.source)

    def test_exact_uuid_comes_from_the_source_journal(self):
        self.assertIn('p.source === SOURCE', self.source)
        self.assertIn("UUID_RE.test", self.source)
        self.assertIn("expectedMarker", self.source)
        self.assertIn("actualDisplayName.startsWith(expectedMarker)", self.source)

    def test_real_ui_paths_are_used(self):
        for needle in (
            "#chatInput", "#lv80SendBtn", ".type(text",
            ".lv-interview-lifemap-era-btn", ".lv-interview-confirm-continue",
            "window.state?.session?.currentEra",
            "params?.runtime71?.current_era",
        ):
            self.assertIn(needle, self.source)

    def test_report_contains_complete_transcript_and_server_snapshots(self):
        self.assertIn("Complete test transcript", self.source)
        self.assertIn('path.join(outDir, "report.html")', self.source)
        self.assertIn('path.join(outDir, "report.json")', self.source)
        self.assertIn("beforeServer", self.source)
        self.assertIn("afterServer", self.source)
        self.assertIn("readRelevantLogDelta", self.source)
        self.assertIn("validatorFailures", self.source)


if __name__ == "__main__":
    unittest.main()

class IdentityIsVerifiedAgainstStateTests(unittest.TestCase):
    """The 2026-08-31 live failure, encoded.

    The run aborted with `opened narrator label does not identify Walt:
    Choose a narrator` while Walt WAS open. `id="lv80ActiveNarratorName"`
    is duplicated in the product and the label read resolved to the copy
    that never updates. Identity now comes from window.state.person_id.
    """

    @staticmethod
    def _code_only(src):
        """JS with comments stripped.

        *(The first version of this class asserted the old error string
        was absent from the raw file and failed on the COMMENT that
        explains why it was removed — the fourth time in this repo a
        guard has punished a file for documenting itself. The property
        is about CODE.)*
        """
        import re
        src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
        return re.sub(r"(?m)^\s*//[^\n]*", "", src)

    def setUp(self):
        self.raw = (_REPO_ROOT / "scripts" / "ui"
                    / "run_walt_seven_era_conversation.js").read_text(
                        encoding="utf-8")
        self.src = self._code_only(self.raw)

    def test_identity_is_taken_from_state_not_a_label(self):
        self.assertIn("identity.statePersonId !== narrator.person_id",
                      self.src)

    def test_the_label_substring_check_is_gone(self):
        self.assertNotIn(
            'opened narrator label does not identify Walt', self.src,
            "the label substring check reads a duplicated DOM id")
        # non-vacuity: the explanation must survive the stripper
        self.assertIn("duplicate DOM id in the product", self.raw)

    def test_the_check_is_an_exact_uuid_match_not_a_word(self):
        self.assertNotIn('.includes("Walt")', self.src)

    def test_the_duplicate_id_is_recorded_as_a_product_defect(self):
        self.assertIn("duplicateIdDefect", self.src)
        self.assertIn("Recorded, not repaired", self.src)

    def test_the_product_still_has_the_duplicate_id(self):
        """Non-vacuity: if this ever fails, the product was fixed and
        this guard can be revisited."""
        ui = (_REPO_ROOT / "ui" / "hornelore1.0.html").read_text(
            encoding="utf-8", errors="replace")
        self.assertGreater(ui.count('id="lv80ActiveNarratorName"'), 1)


class NarratorOpenRaceTests(unittest.TestCase):
    """The 20260831T142834Z failure: state set, card not yet repainted.

    `state.person_id` is assigned early in the open flow. The
    trainer-restore path then rewrites #lv80ActiveNarratorCard's
    innerHTML to a fresh card reading "Choose a narrator", and
    lv80UpdateActiveNarratorCard() repaints it afterwards. Waiting only
    on person_id samples inside that gap.
    """

    def setUp(self):
        raw = (_REPO_ROOT / "scripts" / "ui"
               / "run_walt_seven_era_conversation.js").read_text(
                   encoding="utf-8")
        self.raw = raw
        self.src = IdentityIsVerifiedAgainstStateTests._code_only(raw)

    def test_the_race_exists_in_the_product(self):
        """Non-vacuity. If this fails the product was fixed."""
        ui = (_REPO_ROOT / "ui" / "hornelore1.0.html").read_text(
            encoding="utf-8", errors="replace")
        self.assertIn(
            '\'<div class="lv80-narrator-name" id="lv80ActiveNarratorName">'
            'Choose a narrator</div>\'', ui,
            "the trainer-restore path no longer repaints the placeholder")

    def test_open_waits_for_a_terminal_openStatus(self):
        self.assertIn("narratorOpen", self.src)
        self.assertIn("openStatus", self.src)
        self.assertIn('st !== "loading"', self.src)
        self.assertIn('st !== "idle"', self.src)

    def test_open_waits_for_the_placeholder_to_be_repainted(self):
        self.assertIn('t !== "Choose a narrator"', self.src)
        self.assertIn('t !== "Loading…"', self.src)

    def test_the_visible_identity_assertion_is_preserved(self):
        self.assertIn("PRODUCT IDENTITY DEFECT", self.src)
        self.assertIn("identity.visibleName", self.src)

    def test_visible_name_is_checked_against_the_product_display_name(self):
        self.assertIn("actualDisplayName.includes(", self.src)


class TraceConsumptionTests(unittest.TestCase):
    def setUp(self):
        raw = (_REPO_ROOT / "scripts" / "ui"
               / "run_walt_seven_era_conversation.js").read_text(
                   encoding="utf-8")
        self.src = IdentityIsVerifiedAgainstStateTests._code_only(raw)

    def test_the_harness_refuses_without_tracing(self):
        """*(The message changed when preflight stopped accepting a
        stale directory: it now names what the API actually reported.)*"""
        self.assertIn("REFUSED: the API reports response tracing is NOT "
                      "enabled", self.src)
        self.assertIn("HORNELORE_RESPONSE_TRACE=1 ./scripts/start_all.sh",
                      self.src)

    def test_it_reads_trace_records_by_person_and_conversation(self):
        self.assertIn("tracesForRun", self.src)
        self.assertIn("r.narrator_id === personId", self.src)
        self.assertIn("r.conversation_id === conversationId", self.src)

    def test_the_report_shows_raw_versus_layers_versus_delivered(self):
        self.assertIn("Raw model output", self.src)
        self.assertIn("Control layers, in execution order", self.src)
        self.assertIn("Delivered to the narrator", self.src)

    def test_retention_counts_failed_separately_from_absent(self):
        self.assertIn("measurement_failed", self.src)
        self.assertIn("measured_absent", self.src)
        self.assertIn("genuinelyMeasured", self.src)

    def test_all_eight_retention_stages_are_accounted_for(self):
        for stage in ("durable_turns", "extraction", "bio_facts",
                      "chronology", "life_map", "rolling_summary",
                      "archive", "memoir_source"):
            self.assertIn(f'"{stage}"', self.src)

    def test_a_zero_turn_trace_is_reported_as_a_problem_not_a_pass(self):
        self.assertIn("recorded ZERO turns", self.src)


class PreflightAndCompletenessTests(unittest.TestCase):
    def setUp(self):
        raw = (_REPO_ROOT / "scripts" / "ui"
               / "run_walt_seven_era_conversation.js").read_text(
                   encoding="utf-8")
        self.src = IdentityIsVerifiedAgainstStateTests._code_only(raw)

    def test_preflight_requires_enabled_true_from_the_api(self):
        self.assertIn("traceHealth.body?.enabled !== true", self.src)

    def test_a_stale_directory_cannot_satisfy_preflight(self):
        self.assertNotIn("const dirExists = traceProbe.available", self.src)
        self.assertIn("An existing trace", self.src)

    def test_mechanical_pass_requires_trace_completeness(self):
        self.assertIn("report.traceCompleteness.complete", self.src)
        self.assertIn("&& report.traceCompleteness.complete", self.src)

    def test_completeness_counts_expected_traces_and_raw_text(self):
        """*(Asserted the hardcoded `1 + eras*2`. That was an ASSUMPTION
        about the product — if an era click produced two model turns the
        arithmetic would silently disagree with reality. Replaced by the
        turn manifest, which counts observed `done` events.)*"""
        self.assertIn("report.turnManifest.reduce(", self.src)
        self.assertIn("withRaw", self.src)
        self.assertIn("instrumentationFailures", self.src)

    def test_memoir_is_queried_at_the_api_origin(self):
        self.assertIn("${args.api}/api/memoir/canonical", self.src)
        self.assertIn("measurement_failed", self.src)

    def test_run_level_snapshots_are_not_called_per_turn(self):
        self.assertIn("NOT per-turn attribution", self.src)
        self.assertIn("perTurnAttribution", self.src)

    def test_archive_stays_not_measured_but_rolling_summary_does_not(self):
        """*(Asserted BOTH stay not_measured. Wrong for rolling summary:
        the 20260831T152542Z API log shows GET and POST on it after every
        turn, so it is live and was simply never read. Archive really is
        uninstrumented and stays.)*"""
        self.assertIn('archive: { result: "not_measured"', self.src)
        self.assertNotIn('rolling_summary: { result: "not_measured"',
                         self.src)
        self.assertIn("/api/transcript/rolling-summary?person_id=", self.src)

    def test_identity_waits_for_the_expected_display_name(self):
        self.assertIn("expectedDisplayName", self.src)
        self.assertIn("openExactNarrator(page, narrator.person_id, "
                      "actualDisplayName)", self.src)


class StartAllPropagatesTheFlagTests(unittest.TestCase):
    def test_start_all_exports_and_reports_the_flag(self):
        sh = (_REPO_ROOT / "scripts" / "start_all.sh").read_text(
            encoding="utf-8")
        self.assertIn('export HORNELORE_RESPONSE_TRACE="${HORNELORE_RESPONSE_TRACE:-0}"', sh)
        self.assertIn("Response trace: ENABLED", sh)
        self.assertIn("Response trace: off", sh)

    def test_the_default_is_off(self):
        sh = (_REPO_ROOT / "scripts" / "start_all.sh").read_text(
            encoding="utf-8")
        self.assertIn("RESPONSE_TRACE:-0}", sh,
                      "tracing must remain opt-in")


class TraceFinalizationOnTheLivePathTests(unittest.TestCase):
    """The 20260831T152542Z run lost all fifteen traces this way."""

    def setUp(self):
        self.src = (_REPO_ROOT / "server" / "code" / "api" / "services"
                    / "turn_extraction.py").read_text(encoding="utf-8")

    def test_the_finalizer_wraps_the_scheduled_path(self):
        """chat_ws calls schedule_completed_turn_extraction, which runs
        _complete_claim — NOT extract_completed_turn."""
        self.assertIn("async def _complete_claim(claim: _Claim)", self.src)
        self.assertIn("async def _complete_claim_inner(claim: _Claim)",
                      self.src)
        head = self.src[self.src.index("async def _complete_claim(claim"):
                        self.src.index("async def _complete_claim_inner")]
        self.assertIn("_finalize_extraction_trace", head)
        self.assertIn("except BaseException", head)

    def test_chat_ws_uses_the_scheduler_the_wrapper_now_covers(self):
        ws = (_REPO_ROOT / "server" / "code" / "api" / "routers"
              / "chat_ws.py").read_text(encoding="utf-8")
        self.assertIn("schedule_completed_turn_extraction", ws)


class TurnManifestTests(unittest.TestCase):
    def setUp(self):
        raw = (_REPO_ROOT / "scripts" / "ui"
               / "run_walt_seven_era_conversation.js").read_text(
                   encoding="utf-8")
        self.src = IdentityIsVerifiedAgainstStateTests._code_only(raw)

    def test_the_hardcoded_count_is_gone(self):
        self.assertNotIn("1 + (report.eras.length * 2)", self.src)

    def test_expected_traces_come_from_the_manifest(self):
        self.assertIn("report.turnManifest.reduce(", self.src)
        self.assertIn("doneEvents", self.src)

    def test_every_send_site_records_a_manifest_entry(self):
        for kind in ('"bio_probe"', '"era_prompt"', '"narrator_turn"'):
            self.assertIn(kind, self.src)

    def test_manifest_counts_observed_done_events(self):
        self.assertIn("doneEventsObserved", self.src)


class PartialRunEvidenceTests(unittest.TestCase):
    def setUp(self):
        raw = (_REPO_ROOT / "scripts" / "ui"
               / "run_walt_seven_era_conversation.js").read_text(
                   encoding="utf-8")
        self.src = IdentityIsVerifiedAgainstStateTests._code_only(raw)

    def test_the_trace_is_collected_on_the_failure_path(self):
        catch = self.src[self.src.index("} catch (error) {"):]
        self.assertIn("tracesForRun", catch)
        self.assertIn("report.responseTrace", catch)

    def test_a_partial_run_never_claims_completeness(self):
        catch = self.src[self.src.index("} catch (error) {"):]
        self.assertIn("complete: false", catch)
        self.assertIn("report.partial = true", catch)

    def test_the_output_dir_is_created_after_preflight(self):
        mk = self.src.index("fs.mkdirSync(shotDir")
        refuse = self.src.index("REFUSED: the API reports")
        self.assertGreater(mk, refuse,
                           "a refused run must not leave an empty "
                           "timestamped directory")


class RollingSummaryIsMeasuredTests(unittest.TestCase):
    def setUp(self):
        raw = (_REPO_ROOT / "scripts" / "ui"
               / "run_walt_seven_era_conversation.js").read_text(
                   encoding="utf-8")
        self.src = IdentityIsVerifiedAgainstStateTests._code_only(raw)

    def test_the_snapshot_reads_rolling_summary(self):
        self.assertIn("/api/transcript/rolling-summary?person_id=", self.src)

    def test_it_is_no_longer_hardcoded_not_measured(self):
        self.assertNotIn('rolling_summary: { result: "not_measured"', self.src)
        self.assertIn("beforeChars", self.src)
        self.assertIn("afterChars", self.src)

    def test_a_dead_endpoint_is_measurement_failed_not_absent(self):
        self.assertIn('result: "measurement_failed"', self.src)


class PostBudgetContextTests(unittest.TestCase):
    def test_the_trace_captures_the_real_model_context(self):
        ws = (_REPO_ROOT / "server" / "code" / "api" / "routers"
              / "chat_ws.py").read_text(encoding="utf-8")
        self.assertIn('"post_budget_messages"', ws)
        self.assertIn("_budget.messages", ws)
        self.assertIn("_budget.sections", ws)
