"""WO-TRIP-LANE-AUDIT-FIXPACK-01 — JS guards (H3, M5, M6).

Pattern-based locks on the front-end fixes (same convention as
tests/test_travel_doc_lab.py / test_travel_documenter_panel.py):
  H3 — travel-doc-lab.js resets loriPane on trip switch.
  M5 — travel-doc-lab.js guards destructive re-renders behind a
       dirty-discard confirmation (Save/Cancel stay unguarded).
  M6 — travel-documenter.js closes the modal Lori socket on destroy.

WO-TRAVEL-DOC-UNIFY-01 Phase 5: those two modules are no longer peers.
travel-doc-lab.js is the operator's only Travel Doc; travel-documenter.js
was retired from that path by Phase 4 and is reachable only through its
own standalone page. Both guards still hold and both are still required
-- M6 protects a socket that page can still open -- so this file names
its surfaces through tests/travel_doc_surfaces.py instead of repeating
their paths and its own copy of the comment stripper.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
import travel_doc_surfaces as _tds  # noqa: E402

# WO-TRAVEL-DOC-UNIFY-01 Phase 5: the paths and the string-aware comment
# stripper this file used to carry privately now live in
# tests/travel_doc_surfaces.py, which also records WHY the stripper
# cannot be a naive comment regex: Phase 3C added `files.accept =
# "image/*"` to the intake drawer, and the "/*" inside that literal
# opened a phantom block comment that swallowed several hundred lines of
# source, so the assertions covering them started passing and failing for
# reasons unrelated to the code they guard.


class H3LoriPaneResetTest(unittest.TestCase):
    def setUp(self):
        self.src = _tds.UNIFIED_JS.stripped()

    def test_loripane_has_reset_method(self):
        self.assertIn("reset: function ()", self.src)

    def test_reset_closes_socket_and_clears_anchors(self):
        # The reset body must drop socket + both anchors + transcript.
        m = re.search(r"reset:\s*function\s*\(\)\s*\{(.*?)\},",
                      self.src, re.S)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn(".ws.close()", body)
        self.assertIn("this.dayId = null", body)
        self.assertIn("this.photoLinkId = null", body)

    def test_selecttrip_calls_reset(self):
        self.assertIn("loriPane.reset();", self.src)


class M5DirtyGuardTest(unittest.TestCase):
    def setUp(self):
        self.src = _tds.UNIFIED_JS.stripped()

    def test_guard_function_defined(self):
        self.assertIn("function dayFormDirtyBlocks()", self.src)

    def test_open_functions_guard_at_definition(self):
        # The guard lives at each open* definition (centralized), not at
        # every call site, so opening a drawer/overlay while the day
        # inspector is dirty is blocked.
        for fn in ("openSourceDrawer", "openPhotoPicker", "openNoteDrawer",
                   "openLoriOverlay", "openLoriOverlayForPhoto"):
            m = re.search(
                r"function " + fn + r"\([^)]*\)\s*\{\s*"
                r"if \(dayFormDirtyBlocks\(\)\) return;", self.src)
            self.assertIsNotNone(m, fn + " definition is not guarded")

    def test_guard_uses_no_native_confirm(self):
        # Lab doctrine: no native confirm() dialogs anywhere in the guard.
        m = re.search(r"function dayFormDirtyBlocks\(\)\s*\{(.*?)\n  \}",
                      self.src, re.S)
        self.assertIsNotNone(m)
        self.assertNotIn("confirm(", m.group(1))

    def test_inspector_close_and_nav_are_guarded(self):
        self.assertIn(
            "if (dayFormDirtyBlocks()) return; st.selectedDayId = null; "
            "dayForm = null; renderAll();", self.src)
        self.assertIn(
            "if (idx > 0) { if (dayFormDirtyBlocks()) return;", self.src)
        self.assertIn(
            "if (idx < st.days.length - 1) { if (dayFormDirtyBlocks()) "
            "return;", self.src)

    def test_tab_switch_is_guarded(self):
        i = self.src.index("function setTab(tab) {")
        window = self.src[i:i + 160]
        self.assertIn("if (dayFormDirtyBlocks()) return;", window)

    def test_route_rail_selection_is_guarded(self):
        # The stop route-rail click must guard before mutating routeSel.
        j = self.src.index("st.routeSel = { kind:")
        window = self.src[max(0, j - 120):j]
        self.assertIn("if (dayFormDirtyBlocks()) return;", window)

    def test_cancel_stays_unguarded(self):
        # cancelDayEdits is the deliberate revert — it must NOT prompt.
        m = re.search(r"function cancelDayEdits\(\)\s*\{(.*?)\}",
                      self.src, re.S)
        self.assertIsNotNone(m)
        self.assertNotIn("dayFormDirtyBlocks", m.group(1))


class M6ModalSocketCloseTest(unittest.TestCase):
    def setUp(self):
        self.src = _tds.RETIRED_JS.stripped()

    def test_destroy_closes_modal_lori_socket(self):
        m = re.search(r"destroy:\s*function\s*\(\)\s*\{(.*?)\},",
                      self.src, re.S)
        self.assertIsNotNone(m)
        self.assertIn("modalLori.close()", m.group(1))


if __name__ == "__main__":
    unittest.main()
