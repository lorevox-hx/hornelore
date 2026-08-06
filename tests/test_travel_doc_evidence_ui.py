"""WO-TRAVEL-DOC-EVIDENCE-TOOLS-01 Phase 1/2 — Lab evidence UI (pattern).

Locks the operator evidence controls in travel-doc-lab.js: Run OCR +
Lookup public context buttons, the draft/approved/memoir badges, the
approval-ladder controls, and that OCR/lookup text is rendered via el()
(textContent), never innerHTML.

WO-TRAVEL-DOC-UNIFY-01 Phase 5: "Lab" in the title above is history, not
the current boundary. Phase 4 made travel-doc-lab.js the operator's only
Travel Doc, so these are the operator evidence controls, full stop. The
paths and the comment stripper come from tests/travel_doc_surfaces.py.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
import travel_doc_surfaces as _tds  # noqa: E402

# WO-TRAVEL-DOC-UNIFY-01 Phase 5: paths and the string-aware comment
# stripper come from tests/travel_doc_surfaces.py now, which records why
# a naive comment regex cannot be used on this module.
_CSS = _tds.UNIFIED_CSS.path


class EvidenceUiTest(unittest.TestCase):
    def setUp(self):
        self.src = _tds.UNIFIED_JS.stripped()

    def test_ocr_and_lookup_buttons_present(self):
        self.assertIn("Run OCR", self.src)
        self.assertIn("Lookup public context", self.src)

    def test_evidence_calls_sanctioned_endpoints(self):
        for path in ("/ocr", "/lookup-context", "/photo-context",
                     "/public-context"):
            self.assertIn(path, self.src, path)

    def test_approval_ladder_controls_present(self):
        """NARROWED 2026-08-05 (WO-TRAVEL-DOC-CLOSEOUT-01). Retired:

            for label in ("Approve for Lori", "Include in memoir",
                          "Reject / Hide"):

        The "Include in memoir" control on evidence rows was a NO-OP:
        `build_trip_docx` has never read photo-context or public-context
        rows, so the tick promised an outcome that could not happen.
        Chris's decision was to retire the control rather than build the
        promise, because these rows are OCR text, vision descriptions,
        draft observations and web context -- working evidence, not
        memoir content.

        "Approve for Lori" stays and is asserted below, because it IS
        consumed: approved photo context reaches Lori's prompt
        (WO-TRIP-PHOTO-CONTEXT-ENRICHMENT Ph5). It is deliberately NOT
        renamed, since a rename would be a second promise about a
        boundary rather than a description of what the control does.
        """
        for label in ("Approve for Lori", "Reject / Hide"):
            self.assertIn(label, self.src, label)

    def test_the_retired_memoir_control_stays_retired(self):
        """An absence worth asserting: without this, the control can come
        back and be a no-op again."""
        stripped = re.sub(r"^\s*//.*$", "", self.src, flags=re.M)
        self.assertNotIn("Include in memoir", stripped,
                         "the no-op memoir control is back on evidence rows")
        self.assertNotIn("Remove from memoir", stripped)

    def test_badges_present(self):
        # "In memoir" remains as a BADGE on sources, which is a real
        # state that does reach the document; only the evidence-row
        # control was retired.
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
        #
        # WO-TRAVEL-DOC-UNIFY-01 Phase 3B widened it once more: region and
        # stop deletion are now ported too, so the sanctioned set is the
        # trip GRAPH (trip / region / stop) rather than the trip row
        # alone. The evidence exclusion below is untouched — that is the
        # property this test has always really been about.
        evidence_lanes = ("photo-context", "public-context", "location-notes",
                          "/sources", "photo-links")
        sanctioned = ('"/api/trips/" + encodeURIComponent(',
                      '"/api/trips/regions/" + encodeURIComponent(',
                      '"/api/trips/stops/" + encodeURIComponent(')
        for m in re.finditer(r'method:\s*"DELETE"', self.src):
            # The api() call opens with the path argument, so the enclosing
            # call site is the ~220 chars before the method option.
            call = self.src[max(0, m.start() - 220):m.start()]
            self.assertTrue(any(p in call for p in sanctioned),
                            "a DELETE in the lab outside the trip graph")
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
