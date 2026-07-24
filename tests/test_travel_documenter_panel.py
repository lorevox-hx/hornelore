"""WO-TRAVEL-DOCUMENTER-NATIVE-PANEL-01 — boundary gate.

The Travel Documenter is an OPERATOR tool for editing trips; the
Travels shelf is the narrator/Lori conversation surface. These tests
FAIL THE BUILD if the two ever mix state, or if the native panel
regresses to requiring pasted person_ids.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

try:
    from tests import source_scan_helpers as _ssh
except ImportError:  # direct execution: python tests/test_travel_documenter_panel.py
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import source_scan_helpers as _ssh

_REPO_ROOT = Path(__file__).resolve().parent.parent
_JS = _REPO_ROOT / "ui" / "js" / "travel-documenter.js"
_APP = _REPO_ROOT / "ui" / "js" / "app.js"
_HTML = _REPO_ROOT / "ui" / "hornelore1.0.html"
_STANDALONE = _REPO_ROOT / "ui" / "travel-documenter.html"


def _stripped_js() -> str:
    # WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 Phase 6.4: the old
    # re.sub(r"/\*[\s\S]*?\*/|//[^\n]*") stripper treated the "//" inside
    # string literals like "http://localhost:8000" (travel-documenter.js
    # ~line 68) as a line comment, blinding every banned-token scan from
    # there to end-of-line. The shared string-aware scanner (unit-tested
    # in tests/test_source_scan_helpers.py) removes real comments only;
    # string/template/regex contents stay visible to the scans below.
    js = _JS.read_text(encoding="utf-8")
    return _ssh.strip_js_comments(js)


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
        # Phase 6 review fix: the old r'"(/api/[a-z_/?=+-]*?)"' pattern
        # missed endpoints containing digits or uppercase — adopt the
        # lab gate's catch-all form so no endpoint spelling can hide.
        used = set(re.findall(r'"(/api/[^"]*)"', src))
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
        # Post-push review #2: dvh (mobile browser chrome safe) +
        # min-height: 0 + align-self: start on the pinned rule.
        line = next((ln for ln in self._css().splitlines()
                     if ln.strip().startswith(".td-root .td-col-right")
                     and "calc(100dvh" in ln), None)
        self.assertIsNotNone(line, "no viewport-pinned .td-col-right rule")
        self.assertIn("position: sticky", line)
        self.assertIn("flex-direction: column", line)
        self.assertIn("overflow: hidden", line)
        self.assertIn("min-height: 0", line)
        self.assertIn("align-self: start", line)
        self.assertNotIn("100vh", line.replace("100dvh", ""),
                         "vh crept back alongside dvh")

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


class PostPushReviewPunchListTest(unittest.TestCase):
    """Post-push review punch-list (2026-07-10) on top of 208678c."""

    def _css(self) -> str:
        return (_REPO_ROOT / "ui" / "css" / "travel-documenter.css"
                ).read_text(encoding="utf-8")

    def test_editor_tabs_are_sibling_before_editor_body(self):
        # Punch-list #1: the tab strip is a fixed sibling BETWEEN the
        # panel head and the scrollable editor body — never rendered
        # inside editorBody, where long forms scroll it away.
        src = _JS.read_text(encoding="utf-8")
        m = re.search(
            r'data-td="editorPanel"[\s\S]*?'
            r'<div data-td="editorTabs" class="td-ed-tabs"></div>[\s\S]*?'
            r'data-td="editorBody"',
            src)
        self.assertIsNotNone(
            m, "editorTabs strip missing between panel head and editorBody")
        stripped = _stripped_js()
        m2 = re.search(r"function renderEditor\(\) \{[\s\S]*?\n    \}",
                       stripped)
        self.assertIsNotNone(m2, "renderEditor not found")
        body = m2.group(0)
        # Tabs render into the dedicated strip, cleared every render;
        # the old tabs-in-body pattern must be gone.
        self.assertIn('$("editorTabs")', body)
        self.assertIn('tabsBar.innerHTML = ""', body)
        self.assertNotIn("body.appendChild(tabsBar)", body)
        self.assertNotIn('el("div", "td-ed-tabs")', body)
        # CSS: the strip is a fixed flex child (no scroll participation)
        # and hides itself when empty (no-selection state).
        css = self._css()
        line = next((ln for ln in css.splitlines()
                     if ln.strip().startswith(".td-root .td-ed-tabs,")), None)
        self.assertIsNotNone(line, "no scoped .td-ed-tabs rule")
        self.assertIn("flex: 0 0 auto", line)
        self.assertIn(".td-root .td-ed-tabs:empty", css)

    def test_modal_lori_notes_label_from_lori_modal(self):
        # Punch-list #3: story notes captured through the Travel Doc
        # Lori modal (source_surface=travel_doc_modal) are labeled
        # "from Lori modal"; plain lori notes keep "from Lori chat".
        src = _stripped_js()
        m = re.search(r"function renderNoteCard\(n\) \{[\s\S]*?\n    \}",
                      src)
        self.assertIsNotNone(m, "renderNoteCard not found")
        body = m.group(0)
        self.assertIn('n.source_surface === "travel_doc_modal"', body)
        self.assertIn('"from Lori modal"', body)
        self.assertIn('"from Lori chat"', body)
        # Branch shape: modal label only on the lori source type.
        self.assertIn('_srcType === "lori"', body)


class EvidenceLifecycleTest(unittest.TestCase):
    """WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01 — evidence lifecycle safety +
    destructive-trip controls.

    Note delete and source delete become immediate reversible hides
    (PATCH {hidden:true}) with an inline "Hidden — Restore" stub — no
    window.confirm, no DELETE. Trip delete becomes the impact-review
    flow: non-forced DELETE first; on 409 an IN-PANEL confirm block
    renders the evidence counts and arms only on an exact typed
    title/id match, then force-deletes with confirm_trip_id + reason.
    Region/stop deletes keep their native confirms (out of scope this
    WO) — the total window.confirm count drops from 5 to exactly 2."""

    def setUp(self):
        self.src = _stripped_js()
        self.raw = _JS.read_text(encoding="utf-8")

    def _fn(self, pattern: str) -> str:
        m = re.search(pattern, self.src)
        self.assertIsNotNone(m, f"function not found: {pattern}")
        return m.group(0)

    def test_note_hide_replaces_confirm_delete(self):
        body = self._fn(r"function renderNoteCard\(n\) \{[\s\S]*?\n    \}")
        self.assertNotIn("window.confirm", body)
        self.assertNotIn('method: "DELETE"', body)
        self.assertIn('method: "PATCH"', body)
        self.assertIn("JSON.stringify({ hidden: true })", body)
        self.assertIn("JSON.stringify({ hidden: false })", body)
        self.assertIn('"Hide"', body)
        self.assertIn("showHiddenStub(", body)

    def test_source_hide_replaces_confirm_delete(self):
        body = self._fn(r"function renderSourceCard\(s\) \{[\s\S]*?\n    \}")
        self.assertNotIn("window.confirm", body)
        self.assertNotIn('method: "DELETE"', body)
        self.assertIn('method: "PATCH"', body)
        self.assertIn("JSON.stringify({ hidden: true })", body)
        self.assertIn("JSON.stringify({ hidden: false })", body)
        self.assertIn('"Hide"', body)
        self.assertIn("showHiddenStub(", body)

    def test_hidden_restore_stub_is_inline_and_reversible(self):
        body = self._fn(r"function showHiddenStub\(card, labelText, "
                        r"restoreFn\) \{[\s\S]*?\n    \}")
        self.assertIn('"Hidden — "', body)
        self.assertIn('"Restore"', body)
        self.assertIn("td-hidden-stub", body)
        self.assertNotIn("window.confirm", body)

    def test_trip_delete_probes_then_opens_impact_review(self):
        body = self._fn(r"function deleteTrip\(trip\) \{[\s\S]*?\n    \}")
        self.assertNotIn("window.confirm", body)
        # Non-forced DELETE first; 409 + requires_force routes to the
        # in-panel review, everything else still surfaces as an error.
        self.assertIn('{ method: "DELETE" }', body)
        self.assertIn("e.status === 409", body)
        self.assertIn("requires_force", body)
        self.assertIn("openDeleteTripReview(", body)
        # WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01: the 409 impact ships inside
        # FastAPI's `detail` envelope — the flow MUST read e.body.detail
        # (reading the flat e.body.requires_force would silently never
        # open the review). Pin the nested read so it can't regress.
        self.assertIn("e.body.detail", body)
        self.assertNotIn("e.body.requires_force", body)

    def test_force_delete_sends_confirm_trip_id_force_and_reason(self):
        body = self._fn(r"function openDeleteTripReview\(trip, impact\) "
                        r"\{[\s\S]*?\n    \}")
        self.assertNotIn("window.confirm", body)
        self.assertNotIn("window.alert", body)
        self.assertIn("force: true", body)
        self.assertIn("confirm_trip_id: trip.id", body)
        self.assertIn('"operator cleanup"', body)
        # 422 / wrong-confirm failures render inline in the panel.
        self.assertIn("deleteTripError", body)
        # The 409 counts payload is rendered for review.
        self.assertIn("impact.counts", body)
        for key in ("regions", "stops", "days", "photo_links", "notes",
                    "sources", "story_links", "public_context",
                    "photo_context"):
            self.assertIn(f'"{key}"', body)

    def test_arm_requires_exact_title_or_id_match(self):
        body = self._fn(r"function openDeleteTripReview\(trip, impact\) "
                        r"\{[\s\S]*?\n    \}")
        # Trim-compare against the exact trip title, or the trip id —
        # the confirm button stays disabled otherwise.
        self.assertIn('typed === String(trip.title || "").trim()', body)
        self.assertIn("typed === String(trip.id)", body)
        self.assertIn("confirmBtn.disabled = !armed", body)

    def test_confirm_count_dropped_to_region_and_stop_only(self):
        # 5 → 2: only the (out-of-scope) region and stop deletes keep
        # window.confirm.
        self.assertEqual(self.src.count("window.confirm("), 2)
        self.assertIn("window.confirm",
                      self._fn(r"function deleteRegion\(region\) "
                               r"\{[\s\S]*?\n    \}"))
        self.assertIn("window.confirm",
                      self._fn(r"function deleteStop\(stop\) "
                               r"\{[\s\S]*?\n    \}"))

    def test_delete_trip_modal_hooks_and_css_present(self):
        for hook in ('data-td="modalDeleteTrip"',
                     'data-td="deleteTripSummary"',
                     'data-td="deleteTripCounts"',
                     'data-td="deleteTripConfirmInput"',
                     'data-td="deleteTripReason"',
                     'data-td="deleteTripError"',
                     'data-td="confirmDeleteTrip"',
                     'data-td="cancelDeleteTrip"',
                     'data-td="closeDeleteTrip"'):
            self.assertIn(hook, self.raw, hook)
        # Escape + backdrop close cover the new modal too (both lists
        # end with it, right before their .forEach).
        self.assertEqual(self.src.count('"modalDeleteTrip"].forEach'), 2)
        css = (_REPO_ROOT / "ui" / "css" / "travel-documenter.css"
               ).read_text(encoding="utf-8")
        for cls in (".td-hidden-stub", ".td-note-hidden",
                    ".td-delete-trip-counts", ".td-delete-trip-warning",
                    ".td-delete-trip-error"):
            self.assertIn(cls, css, cls)


if __name__ == "__main__":
    unittest.main()
