"""WO-TRIP-LANE-AUDIT-FIXPACK-01 — JS guards (H3, M5, M6).

Pattern-based locks on the front-end fixes (same convention as
tests/test_travel_doc_lab.py / test_travel_documenter_panel.py):
  H3 — travel-doc-lab.js resets loriPane on trip switch.
  M5 — travel-doc-lab.js guards destructive re-renders behind a
       dirty-discard confirmation (Save/Cancel stay unguarded).
  M6 — travel-documenter.js closes the modal Lori socket on destroy.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
import source_scan_helpers as _ssh  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent
_LAB = _REPO_ROOT / "ui" / "js" / "travel-doc-lab.js"
_DOC = _REPO_ROOT / "ui" / "js" / "travel-documenter.js"


def _strip(js: str) -> str:
    # WO-TRAVEL-DOC-UNIFY-01 Phase 3C: this used to be
    # re.sub(r"/\*[\s\S]*?\*/|//[^\n]*"), which cannot tell a comment
    # from a string literal that merely looks like one. Phase 3C added
    # `files.accept = "image/*"` to the intake drawer, and the "/*" inside
    # that string opened a phantom block comment that swallowed everything
    # down to the next real "*/" — several hundred lines of source went
    # invisible, and the assertions covering them started passing or
    # failing for reasons that had nothing to do with the code they were
    # guarding. The shared string-aware scanner removes real comments
    # only; string, template and regex contents stay visible.
    return _ssh.strip_js_comments(js)


class H3LoriPaneResetTest(unittest.TestCase):
    def setUp(self):
        self.src = _strip(_LAB.read_text(encoding="utf-8"))

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
        self.src = _strip(_LAB.read_text(encoding="utf-8"))

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
        self.src = _strip(_DOC.read_text(encoding="utf-8"))

    def test_destroy_closes_modal_lori_socket(self):
        m = re.search(r"destroy:\s*function\s*\(\)\s*\{(.*?)\},",
                      self.src, re.S)
        self.assertIsNotNone(m)
        self.assertIn("modalLori.close()", m.group(1))


if __name__ == "__main__":
    unittest.main()
