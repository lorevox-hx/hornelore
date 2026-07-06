"""WO-TRAVEL-DOCUMENTER-NATIVE-PANEL-01 — boundary gate.

The Travel Documenter is an OPERATOR tool for editing trips; the
Travels shelf is the narrator/Lori conversation surface. These tests
FAIL THE BUILD if the two ever mix state, or if the native panel
regresses to requiring pasted person_ids.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_JS = _REPO_ROOT / "ui" / "js" / "travel-documenter.js"
_APP = _REPO_ROOT / "ui" / "js" / "app.js"
_HTML = _REPO_ROOT / "ui" / "hornelore1.0.html"
_STANDALONE = _REPO_ROOT / "ui" / "travel-documenter.html"


def _stripped_js() -> str:
    js = _JS.read_text(encoding="utf-8")
    return re.sub(r"/\*[\s\S]*?\*/|//[^\n]*", "", js)


class BoundaryTest(unittest.TestCase):
    def test_module_never_touches_lori_or_travels_state(self):
        # Spec safety boundary 1-3: no trip-session scope writes, no
        # runtime71 consumption, no system-prompt dispatch. Checked on
        # comment-stripped source so docs can still explain the rule.
        src = _stripped_js()
        for banned in ("activeTripId", "travelsShelfOpen",
                       "activeTripStopId", "tripStyle", "runtime71",
                       "sendSystemPrompt", "wo9SendOrQueueSystemPrompt",
                       "state.session"):
            self.assertNotIn(banned, src,
                             f"travel-documenter must not reference {banned}")

    def test_mount_function_exported(self):
        src = _JS.read_text(encoding="utf-8")
        self.assertIn("window.lvTravelDocumenterMount", src)

    def test_native_panel_uses_selected_narrator_not_paste(self):
        # The native mount call in app.js must pass state.person_id;
        # the module must consume opts.person_id.
        app = _APP.read_text(encoding="utf-8")
        m = re.search(r'if \(tabName === "traveldoc"\) \{[\s\S]*?\n  \}', app)
        self.assertIsNotNone(m, "traveldoc mount block missing in app.js")
        block = m.group(0)
        self.assertIn("state.person_id", block)
        self.assertIn("lvTravelDocumenterMount", block)
        self.assertIn("Choose a narrator first", block)
        src = _stripped_js()
        self.assertIn("opts.person_id", src)

    def test_remount_on_narrator_change(self):
        app = _APP.read_text(encoding="utf-8")
        self.assertIn("_lvTravelDocMountedFor", app)

    def test_shell_tab_and_panel_wired(self):
        html = _HTML.read_text(encoding="utf-8")
        self.assertIn('data-tab="traveldoc"', html)
        self.assertIn('id="lvTravelDocTab"', html)
        self.assertIn('id="lvTravelDocHost"', html)
        self.assertIn("css/travel-documenter.css", html)
        self.assertIn("js/travel-documenter.js", html)
        # Interview-mode boundary: the shell tab strip (which carries
        # this tab) is hidden while interview mode is active.
        css = (_REPO_ROOT / "ui" / "css" / "lori80.css").read_text(
            encoding="utf-8")
        self.assertIn("body.lv-interview-mode-active #lvShellTabs", css)

    def test_standalone_is_thin_wrapper(self):
        html = _STANDALONE.read_text(encoding="utf-8")
        self.assertIn("lvTravelDocumenterMount", html)
        self.assertIn("standalone: true", html)
        # The old duplicated panel markup must be gone from the page —
        # single source of truth is the module template.
        self.assertNotIn('id="tdCreateTrip"', html)

    def test_stop_types_match_schema(self):
        # The prototype offered 'travel_day', which the DB CHECK
        # rejects. The module's list must be schema-legal.
        sql = (_REPO_ROOT / "server" / "code" / "db" / "migrations" /
               "0015_trip_tables.sql").read_text(encoding="utf-8")
        m = re.search(r"stop_type[\s\S]*?CHECK \(stop_type IN \(([\s\S]*?)\)\)", sql)
        self.assertIsNotNone(m)
        legal = set(re.findall(r"'(\w+)'", m.group(1)))
        src = _JS.read_text(encoding="utf-8")
        m2 = re.search(r"STOP_TYPES = \[([\s\S]*?)\]", src)
        self.assertIsNotNone(m2)
        offered = set(re.findall(r'"(\w+)"', m2.group(1)))
        self.assertTrue(offered.issubset(legal),
                        f"illegal stop types offered: {offered - legal}")

    def test_uses_existing_endpoints_only(self):
        src = _stripped_js()
        used = set(re.findall(r'"(/api/[a-z_/?=+-]*?)"', src))
        # Everything the module calls must be in the sanctioned list.
        allowed_prefixes = ("/api/trips", "/api/photos/")
        for u in used:
            self.assertTrue(any(u.startswith(p) for p in allowed_prefixes),
                            f"unsanctioned endpoint: {u}")


if __name__ == "__main__":
    unittest.main()
