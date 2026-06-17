from __future__ import annotations

import unittest

from tests.boris_quality._helpers import require_callable


class EvidencePathNormalizationTests(unittest.TestCase):
    """Adjacent harness fix — Windows path to WSL path normalization."""

    def setUp(self):
        self.normalize = require_callable([
            ("scripts.run_john_baldy_full_diagnostic_harness", "normalize_evidence_path"),
            ("scripts.run_john_baldy_full_diagnostic_harness", "_normalize_evidence_path"),
        ])

    def test_converts_backslash_windows_path_to_wsl_path(self):
        raw = r"C:\Users\chris\AppData\Roaming\Claude\uploads\transcript_switch_mqif3.txt"
        got = str(self.normalize(raw))
        self.assertEqual(
            got,
            "/mnt/c/Users/chris/AppData/Roaming/Claude/uploads/transcript_switch_mqif3.txt",
        )

    def test_converts_forwardslash_windows_path_to_wsl_path(self):
        raw = "C:/Users/chris/AppData/Roaming/Claude/uploads/OPERATOR-LOG.md"
        got = str(self.normalize(raw))
        self.assertEqual(got, "/mnt/c/Users/chris/AppData/Roaming/Claude/uploads/OPERATOR-LOG.md")

    def test_leaves_wsl_path_unchanged(self):
        raw = "/mnt/c/Users/chris/hornelore/docs/reports/transcript_switch_mqif3.txt"
        got = str(self.normalize(raw))
        self.assertEqual(got, raw)

    def test_preserves_repo_relative_path(self):
        raw = "docs/reports/transcript_switch_mqif3.txt"
        got = str(self.normalize(raw))
        self.assertEqual(got, raw)


if __name__ == "__main__":
    unittest.main()
