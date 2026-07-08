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


class ReviewFixesTest(unittest.TestCase):
    """Review 2026-07-06 — polish fixes locked in."""

    def test_css_fully_scoped(self):
        # Every .td-* component rule must be scoped under .td-root or
        # body.td-standalone; vars defined on BOTH roots.
        css = (_REPO_ROOT / "ui" / "css" / "travel-documenter.css"
               ).read_text(encoding="utf-8")
        self.assertIn(".td-root,\nbody.td-standalone {", css)
        for ln in css.splitlines():
            s = ln.strip()
            if s.startswith(".td-") and "{" in s and not s.startswith(".td-root"):
                self.fail(f"unscoped .td rule: {s[:60]}")
        # No bare element rules either.
        for bare in ("\nbody {", "\nbutton {", "\ninput, select"):
            self.assertNotIn(bare, css)

    def test_narrator_switch_remounts_travel_doc(self):
        html = _HTML.read_text(encoding="utf-8")
        m = re.search(r"async function lv80SwitchPerson[\s\S]{0,1200}", html)
        self.assertIsNotNone(m)
        block = m.group(0)
        self.assertIn("_lvTravelDocMountedFor = null", block)
        self.assertIn('lvShellShowTab("traveldoc")', block)

    def test_parent_dropdown_filters_by_region(self):
        src = _stripped_js()
        self.assertIn("rebuildParentOptions", src)
        self.assertIn("s.region_id !== selectedRegion", src)
        # Region change rebuilds the parent list. (WO-TRAVEL-DOC-LAYOUT-
        # REFLOW-01: the change handler is now an inline function that also
        # drops a stale insert context before rebuilding, so match the call
        # rather than the old bare-reference form.)
        self.assertIn('$("stopRegion")', src)
        self.assertIn('addEventListener("change", function', src)
        self.assertIn("rebuildParentOptions();", src)

    def test_upload_help_text_is_honest(self):
        # Uploads are narrator-ready operator additions, not "review
        # items" (needs_operator_review is only stamped for
        # travels_shelf uploads server-side).
        src = _JS.read_text(encoding="utf-8")
        self.assertIn("narrator-ready immediately", src)
        self.assertNotIn("as review items", src)


class StaleSelectLabelTest(unittest.TestCase):
    """BUG-TRAVEL-DOC-HIDDEN-SELECT-LABEL-STALE-01 (2026-07-06).

    Live proof: hidden lv80PersonSelect held a stale value during async
    narrator switch, so Travel Doc said "Documenting trips for Melanie
    Zollner" while state.person_id (and the mount) was Chris. The label
    must come from the active narrator card / state.profile.basics —
    NEVER from the hidden select's selectedOptions.
    """

    def _mount_block(self) -> str:
        app = _APP.read_text(encoding="utf-8")
        m = re.search(r'if \(tabName === "traveldoc"\) \{[\s\S]*?\n  \}', app)
        assert m is not None, "traveldoc mount block missing"
        return m.group(0)

    def test_mount_block_never_reads_hidden_select(self):
        block = self._mount_block()
        self.assertNotIn("selectedOptions", block)
        self.assertNotIn("lv80PersonSelect", block)

    def test_label_helper_reads_active_narrator_card(self):
        app = _APP.read_text(encoding="utf-8")
        m = re.search(
            r"function _lvCurrentNarratorDisplayLabel[\s\S]*?\n  \}", app)
        self.assertIsNotNone(m, "label helper missing")
        helper = m.group(0)
        self.assertIn("lv80ActiveNarratorName", helper)
        # state.profile.basics fallback, then pid — never the select.
        self.assertIn("state.profile.basics", helper)
        self.assertNotIn("lv80PersonSelect", helper)
        # Placeholder card text must not become the label.
        self.assertIn("loading|choose a narrator", helper)

    def test_mount_uses_the_helper(self):
        self.assertIn("_lvCurrentNarratorDisplayLabel(pid)",
                      self._mount_block())


if __name__ == "__main__":
    unittest.main()
