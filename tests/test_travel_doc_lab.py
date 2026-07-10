"""WO-TRAVEL-DOC-UI-LAB-01 — boundary gate for the (removable) UI Lab.

The lab is an experimental, API-connected redesign surface. These tests
FAIL THE BUILD if it ever leaks into production state, loads the
production Travel Doc module, calls an unsanctioned endpoint, or drops
its tdl- namespace. The production panel (ui/js/travel-documenter.js)
cannot be guarded byte-for-byte from a test, so instead we lock the lab
side: the lab must not import or script-load the production module.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_JS = _REPO_ROOT / "ui" / "js" / "travel-doc-lab.js"
_CSS = _REPO_ROOT / "ui" / "css" / "travel-doc-lab.css"
_HTML = _REPO_ROOT / "ui" / "travel-doc-lab.html"


def _stripped_js() -> str:
    js = _JS.read_text(encoding="utf-8")
    return re.sub(r"/\*[\s\S]*?\*/|//[^\n]*", "", js)


def _stripped_css() -> str:
    css = _CSS.read_text(encoding="utf-8")
    return re.sub(r"/\*[\s\S]*?\*/", "", css)


def _stripped_html() -> str:
    html = _HTML.read_text(encoding="utf-8")
    return re.sub(r"<!--[\s\S]*?-->", "", html)


class LabFilesExistTest(unittest.TestCase):
    def test_all_three_lab_files_exist(self):
        for p in (_JS, _CSS, _HTML):
            self.assertTrue(p.exists(), f"missing lab file: {p}")

    def test_lab_files_carry_removable_marker(self):
        for p in (_JS, _CSS, _HTML):
            self.assertIn("REMOVABLE", p.read_text(encoding="utf-8"),
                          f"{p.name} must declare itself removable")


class BoundaryTest(unittest.TestCase):
    def test_lab_never_touches_narrator_or_shelf_state(self):
        # Same posture as the production panel gate, applied to the lab:
        # no narrator-session scope, no runtime71, no Travels shelf, no
        # system-prompt dispatch. Checked on comment-stripped source.
        src = _stripped_js()
        for banned in ("runtime71", "state.session", "travelsShelfOpen",
                       "activeTripId", "activeTripStopId", "tripStyle",
                       "sendSystemPrompt", "wo9SendOrQueueSystemPrompt",
                       "lvTravelsOpenTripById"):
            self.assertNotIn(banned, src,
                             f"travel-doc-lab must not reference {banned}")

    def test_lab_does_not_import_production_module(self):
        # Deep-linking to the standalone travel-documenter.html page is
        # sanctioned (existing flows); loading its JS/CSS is not.
        # Comment-stripped: the docs comments explaining the boundary
        # are allowed to NAME the production files; code may not.
        src = _stripped_js()
        self.assertNotIn("travel-documenter.js", src)
        self.assertNotIn("travel-documenter.css", src)
        self.assertNotIn("lvTravelDocumenterMount", src)
        self.assertNotIn("travel-documenter", _stripped_css())

    def test_endpoints_are_a_subset_of_the_sanctioned_api(self):
        src = _stripped_js()
        allowed = ("/api/trips", "/api/photos/", "/api/people",
                   "/api/chat/ws")
        for m in re.finditer(r'"(/api/[^"]*)"', src):
            path = m.group(1)
            self.assertTrue(
                any(path.startswith(a) for a in allowed),
                f"unsanctioned endpoint in travel-doc-lab.js: {path}")
        # And the sanctioned surfaces are actually exercised.
        for required in ("/api/trips", "/api/people", "/api/chat/ws"):
            self.assertIn('"' + required, src.replace("' ", '"'))

    def test_lori_pane_uses_modal_surface_and_day_scope(self):
        src = _stripped_js()
        self.assertIn("travel_doc_modal", src)
        self.assertIn("modal_scope", src)
        self.assertIn("active_trip_day_id", src)
        self.assertIn("turn_id", src)


class NamespaceTest(unittest.TestCase):
    def test_css_is_tdl_namespaced(self):
        css = _CSS.read_text(encoding="utf-8")
        # No production .td- classes may be reused (`.td-` followed by
        # anything but the lab's own l).
        self.assertIsNone(re.search(r"\.td-[^l]", css),
                          "lab CSS reuses a production .td- class")
        self.assertIn(".tdl-", css)

    def test_js_classes_are_tdl_namespaced(self):
        src = _stripped_js()
        self.assertIsNone(re.search(r"""["'][^"']*\btd-""", src),
                          "lab JS uses a non-tdl td- class string")
        self.assertIn("tdl-", src)


class HtmlPageTest(unittest.TestCase):
    def test_page_loads_only_lab_assets(self):
        html = _stripped_html()
        self.assertIn("css/travel-doc-lab.css", html)
        self.assertIn("js/travel-doc-lab.js", html)
        self.assertNotIn("travel-documenter.js", html)
        self.assertNotIn("travel-documenter.css", html)
        self.assertNotIn("app.js", html)
        self.assertNotIn("lori80.css", html)
        # Exactly one stylesheet + one script tag.
        self.assertEqual(len(re.findall(r"<link\b", html)), 1)
        self.assertEqual(len(re.findall(r"<script\b", html)), 1)

    def test_page_mounts_the_lab_root(self):
        html = _HTML.read_text(encoding="utf-8")
        self.assertIn('id="tdlRoot"', html)
        self.assertIn('class="tdl-body"', html)


if __name__ == "__main__":
    unittest.main()
