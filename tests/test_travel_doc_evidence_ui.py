"""WO-TRAVEL-DOC-EVIDENCE-TOOLS-01 Phase 1/2 — Lab evidence UI (pattern).

Locks the operator evidence controls in travel-doc-lab.js: Run OCR +
Lookup public context buttons, the draft/approved/memoir badges, the
approval-ladder controls, and that OCR/lookup text is rendered via el()
(textContent), never innerHTML.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_JS = _REPO_ROOT / "ui" / "js" / "travel-doc-lab.js"
_CSS = _REPO_ROOT / "ui" / "css" / "travel-doc-lab.css"


def _strip(js: str) -> str:
    return re.sub(r"/\*[\s\S]*?\*/|//[^\n]*", "", js)


class EvidenceUiTest(unittest.TestCase):
    def setUp(self):
        self.src = _strip(_JS.read_text(encoding="utf-8"))

    def test_ocr_and_lookup_buttons_present(self):
        self.assertIn("Run OCR", self.src)
        self.assertIn("Lookup public context", self.src)

    def test_evidence_calls_sanctioned_endpoints(self):
        for path in ("/ocr", "/lookup-context", "/photo-context",
                     "/public-context"):
            self.assertIn(path, self.src, path)

    def test_approval_ladder_controls_present(self):
        for label in ("Approve for Lori", "Include in memoir",
                      "Reject / Hide"):
            self.assertIn(label, self.src, label)

    def test_badges_present(self):
        for badge in ("Draft", "Approved", "In memoir", "Rejected"):
            self.assertIn(badge, self.src, badge)

    def test_patch_wired_no_delete_in_lab(self):
        # Lab honours the never-DELETE posture: hide via PATCH rejected,
        # never a DELETE request (backend DELETE endpoints exist for the
        # API, but the lab does not call them).
        self.assertIn("photo-context/", self.src)
        self.assertIn('method: "PATCH"', self.src)
        self.assertNotIn('method: "DELETE"', self.src)

    def test_summary_rendered_via_textcontent_not_innerhtml(self):
        # result_summary must go through el() (textContent), never innerHTML.
        self.assertIn('el("div", "tdl-ev-summary", r.result_summary', self.src)

    def test_evidence_css_namespaced(self):
        css = _CSS.read_text(encoding="utf-8")
        self.assertIn(".tdl-ev-badge", css)
        self.assertIn(".tdl-evidence", css)


if __name__ == "__main__":
    unittest.main()
