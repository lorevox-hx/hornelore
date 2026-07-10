"""WO-TRAVEL-DOC-EVIDENCE-RICH-TRAVELOGUE-01 §0 — doctrine tests 1-6.
The Travel Doc Evidence + Web Context Rule must live in README + CLAUDE.md:
local LLM/API may use web/public context; cloud outsourcing of private
memoir archives is forbidden."""
from __future__ import annotations
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


class DoctrineTest(unittest.TestCase):
    def _readme(self):
        return (_ROOT / "README.md").read_text(encoding="utf-8")

    def _claude(self):
        return (_ROOT / "CLAUDE.md").read_text(encoding="utf-8")

    def test_readme_has_rule(self):
        self.assertIn("Travel Doc Evidence + Web Context Rule", self._readme())

    def test_claude_has_rule(self):
        self.assertIn("Travel Doc Evidence + Web Context Rule", self._claude())

    def test_readme_allows_local_web_context(self):
        t = self._readme()
        self.assertIn('The rule is not "no web."', t)
        self.assertIn("may use web and", t)

    def test_claude_allows_local_web_context(self):
        t = self._claude()
        self.assertIn('The rule is not "no web."', t)

    def test_readme_forbids_cloud_memoir_outsourcing(self):
        self.assertIn("outsource private narrator memory",
                      self._readme())

    def test_claude_forbids_cloud_memoir_outsourcing(self):
        self.assertIn("outsource private narrator memory",
                      self._claude())


if __name__ == "__main__":
    unittest.main()
