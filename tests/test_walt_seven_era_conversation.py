"""Offline safeguards for the focused Walt browser acceptance script."""
from __future__ import annotations

import pathlib
import re
import subprocess
import unittest


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
