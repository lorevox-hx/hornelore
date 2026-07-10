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
        # WO-TRAVEL-DOC-LORI-MODAL-02: the modal owns its own chat WS —
        # a deliberate, sanctioned addition (surface=travel_doc_modal).
        allowed_prefixes = ("/api/trips", "/api/photos/", "/api/chat/ws")
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



class ReflowTest(unittest.TestCase):
    """WO-TRAVEL-DOC-LAYOUT-REFLOW-01 + WO-TRAVEL-DOC-EDITOR-ERGONOMICS-01.

    The right column pins to the viewport and the editor panel is a
    strict flex column: fixed head (+tabs), scrollable editor BODY, and a
    DEDICATED footer element as a real flex sibling — NO absolute
    positioning (Chris rejected the absolute-docked footer). edActions
    registers Save/Delete into that footer and renderEditor clears it on
    every render (stale-handler guard, same posture as Quick Save).
    """

    def _css(self) -> str:
        return (_REPO_ROOT / "ui" / "css" / "travel-documenter.css"
                ).read_text(encoding="utf-8")

    # ── viewport pin + independent body scroll (kept from REFLOW-01) ──

    def test_right_column_pinned_to_viewport(self):
        line = next((ln for ln in self._css().splitlines()
                     if ln.strip().startswith(".td-root .td-col-right")
                     and "calc(100vh" in ln), None)
        self.assertIsNotNone(line, "no viewport-pinned .td-col-right rule")
        self.assertIn("position: sticky", line)
        self.assertIn("flex-direction: column", line)
        self.assertIn("overflow: hidden", line)

    def test_narrow_viewport_unpins_height(self):
        # The <=1100px reset must undo the height pin, not just sticky —
        # otherwise phones get a clipped 100vh column.
        m = re.search(r"@media \(max-width: 1100px\)[^\n]*", self._css())
        self.assertIsNotNone(m)
        self.assertIn("height: auto", m.group(0))
        self.assertIn("overflow: visible", m.group(0))

    def test_editor_body_scrolls_independently(self):
        line = next((ln for ln in self._css().splitlines()
                     if ln.strip().startswith(".td-root .td-editor-body")
                     and "overflow-y: auto" in ln), None)
        self.assertIsNotNone(line, "no scrolling .td-editor-body rule")
        self.assertIn("flex: 1", line)
        self.assertIn("min-height: 0", line)

    def test_timeline_body_keeps_own_scroll(self):
        line = next((ln for ln in self._css().splitlines()
                     if ln.strip().startswith(".td-root .td-timeline-body")
                     and "flex: 1" in ln), None)
        self.assertIsNotNone(line, "no flexed .td-timeline-body rule")
        self.assertIn("overflow-y: auto", line)

    # ── dedicated footer (EDITOR-ERGONOMICS-01) ──

    def test_template_has_footer_sibling_after_editor_body(self):
        # The footer is a SIBLING after the scrollable body, inside the
        # editor panel section — not a child of the form.
        src = _JS.read_text(encoding="utf-8")
        m = re.search(
            r'data-td="editorPanel"[\s\S]*?'
            r'data-td="editorBody"[\s\S]*?'
            r'<div data-td="editorFooter" class="td-editor-footer"></div>'
            r'[\s\S]{0,80}?</section>',
            src)
        self.assertIsNotNone(
            m, "editorFooter sibling missing from editor panel template")

    def test_footer_css_is_normal_flex_row_no_absolute(self):
        css = self._css()
        line = next((ln for ln in css.splitlines()
                     if ln.strip().startswith(".td-root .td-editor-footer,")
                     ), None)
        self.assertIsNotNone(line, "no scoped .td-editor-footer rule")
        self.assertIn("body.td-standalone .td-editor-footer", line)
        self.assertIn("flex: 0 0 auto", line)
        self.assertIn("display: flex", line)
        self.assertIn("border-top", line)
        # Chris REJECTED the absolute-docked footer: no rule for either
        # the old actions row or the new footer may position:absolute.
        for ln in css.splitlines():
            if ".td-ed-actions" in ln or ".td-editor-footer" in ln:
                self.assertNotIn("position: absolute", ln,
                                 f"absolute positioning crept back: {ln[:70]}")

    def test_ed_actions_registers_into_footer(self):
        src = _stripped_js()
        m = re.search(
            r"function edActions\(parent, saveFn, deleteFn\) \{[\s\S]*?\n    \}",
            src)
        self.assertIsNotNone(m, "edActions not found")
        body = m.group(0)
        # Buttons go to the dedicated footer, never into the form.
        self.assertIn('$("editorFooter")', body)
        self.assertIn("footer.appendChild(save)", body)
        self.assertNotIn("parent.appendChild", body)

    def test_render_editor_clears_footer_every_render(self):
        src = _stripped_js()
        self.assertIn("function clearEditorFooter", src)
        m = re.search(r"function renderEditor\(\) \{[\s\S]*?\n    \}", src)
        self.assertIsNotNone(m, "renderEditor not found")
        body = m.group(0)
        # Cleared BEFORE the empty-state / non-edit-tab branches, so
        # switching trip/region/stop/tab never leaves stale handlers.
        # (The only thing allowed earlier is the null-DOM guard.)
        clear_at = body.index("clearEditorFooter();")
        empty_state = body.index("if (!st.selected")
        self.assertLess(clear_at, empty_state,
                        "footer must be cleared before the empty state")

    # ── Quick Save re-bind (kept exactly as REFLOW-01 built it) ──

    def test_quick_save_injected_with_rebind_guard(self):
        src = _stripped_js()
        self.assertIn("td-quick-save-btn", src)
        # Duplicate guard: existing node removed before a fresh bind, so
        # the button always carries the CURRENT form's saveFn.
        self.assertIn("function removeQuickSave", src)
        self.assertIn('querySelector(".td-quick-save-btn")', src)
        m = re.search(
            r"function edActions\(parent, saveFn, deleteFn\) \{[\s\S]*?\n    \}",
            src)
        self.assertIsNotNone(m, "edActions not found")
        self.assertIn("injectQuickSave(saveFn)", m.group(0))
        # Every editor render drops the stale button (non-edit tabs and
        # the empty state must not keep an orphaned Quick Save).
        m2 = re.search(r"function renderEditor\(\) \{[\s\S]*?\n    \}", src)
        self.assertIsNotNone(m2, "renderEditor not found")
        self.assertIn("removeQuickSave();", m2.group(0))

    # ── wide editor mode ──

    def test_wide_editor_toggle(self):
        src = _stripped_js()
        self.assertIn('data-td="wideToggle"', src)
        self.assertIn('"td-editor-wide"', src)
        # Module-variable memory only — no localStorage.
        self.assertIn("var wideEditor = false;", src)
        self.assertNotIn("localStorage", src.split("var wideEditor")[1][:600])
        # CSS widens the right column at desktop widths only.
        css = self._css()
        m = re.search(r"@media \(min-width: 1101px\)[^\n]*", css)
        self.assertIsNotNone(m, "wide-editor media rule missing")
        self.assertIn(".td-layout.td-editor-wide", m.group(0))
        self.assertIn("grid-template-columns", m.group(0))

    # ── workflow buttons ──

    def test_workflow_buttons_in_trip_toolbar(self):
        src = _JS.read_text(encoding="utf-8")
        self.assertIn('data-td="traveloguePreview"', src)
        self.assertIn('data-td="openPhotosTab"', src)
        stripped = _stripped_js()
        m = re.search(r'bind\("openPhotosTab", function \(\) \{[\s\S]*?\n    \}\);',
                      stripped)
        self.assertIsNotNone(m, "openPhotosTab bind missing")
        body = m.group(0)
        self.assertIn('st.editorTab = "photos"', body)
        self.assertIn("renderEditor()", body)


if __name__ == "__main__":
    unittest.main()
