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
        self.assertIn("REFUSED: response tracing is not available", self.src)
        self.assertIn("HORNELORE_RESPONSE_TRACE=1", self.src)

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
