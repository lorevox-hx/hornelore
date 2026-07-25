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

    def test_patch_wired_no_delete_on_evidence_lanes(self):
        # Evidence lanes are hide-only: rejecting a photo-context or
        # public-context row is a PATCH, never a DELETE.
        #
        # WO-TRAVEL-DOC-UNIFY-01 Phase 3A narrowed this from "the lab
        # issues no DELETE at all" to "the lab issues no DELETE except the
        # gated trip force-delete". The blanket form had to go — Phase 3A
        # deliberately ports that one destructive control — but dropping
        # the test outright would have retired the property it was really
        # protecting, which is that EVIDENCE is never destroyed from here.
        # So: assert every DELETE in the file targets /api/trips/ + a trip
        # id, and none of them targets an evidence sub-resource.
        self.assertIn("photo-context/", self.src)
        self.assertIn('method: "PATCH"', self.src)
        evidence_lanes = ("photo-context", "public-context", "location-notes",
                          "/sources", "photo-links")
        for m in re.finditer(r'method:\s*"DELETE"', self.src):
            # The api() call opens with the path argument, so the enclosing
            # call site is the ~200 chars before the method option.
            call = self.src[max(0, m.start() - 200):m.start()]
            self.assertIn('"/api/trips/" + encodeURIComponent(', call,
                          "a DELETE in the lab that is not a trip delete")
            for lane in evidence_lanes:
                self.assertNotIn(lane, call,
                                 f"DELETE aimed at the {lane} evidence lane")

    def test_summary_rendered_via_textcontent_not_innerhtml(self):
        # result_summary must go through el() (textContent), never innerHTML.
        self.assertIn('el("div", "tdl-ev-summary", r.result_summary', self.src)

    def test_evidence_css_namespaced(self):
        css = _CSS.read_text(encoding="utf-8")
        self.assertIn(".tdl-ev-badge", css)
        self.assertIn(".tdl-evidence", css)


if __name__ == "__main__":
    unittest.main()
