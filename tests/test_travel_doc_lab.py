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


class UsabilityReviewTest(unittest.TestCase):
    """WO-TRAVEL-DOC-UI-LAB-02 — Chris's 2026-07-10 laptop review fixes.

    Locks the ten-item verdict: save without hunting, add photos to THAT
    day in-lab, Lori stays scoped to the day with an obvious way back,
    and no crowded horizontal layout on laptop widths.
    """

    def test_sticky_save_with_top_action_row_and_dirty_badge(self):
        src = _stripped_js()
        # Save Day exists at BOTH ends of the inspector (top action row
        # + sticky footer) and dirty-state gates it.
        self.assertIn("tdl-ins-actions", src)
        self.assertIn("tdl-inspector-footer", src)
        self.assertIn("Unsaved changes", src)
        self.assertIn("Save Day", src)
        self.assertIn("Cancel", src)
        self.assertIn('"Escape"', src)
        css = _stripped_css()
        self.assertIn(".tdl-dirty-badge", css)
        self.assertIn(".tdl-inspector-footer", css)
        self.assertIn("sticky", css)

    def test_no_navigation_away_from_the_lab(self):
        # The old "+ Photos" / "+ Add note" buttons deep-linked to the
        # production Travel Documenter page via window.open — gone. The
        # only remaining production reference is the sanctioned <a> link
        # on the Current tab.
        src = _stripped_js()
        self.assertNotIn("window.open", src)

    def test_in_lab_day_photo_picker(self):
        src = _stripped_js()
        self.assertIn("tdl-photo-picker", src)
        self.assertIn("/photos/link", src)
        self.assertIn("/photos/unlink", src)
        self.assertIn("photo_link_ids", src)
        self.assertIn("Attach photos", src)
        self.assertIn("Attach existing trip photos", src)
        self.assertIn("Unlink", src)
        # Day attachment is first-class in the link rows.
        self.assertIn("trip_day_id", src)

    def test_photo_picker_attach_vs_move_is_explicit(self):
        # 2026-07-10 review fix 3: links already attached to ANOTHER day
        # are never silently reassigned. Per-row labels split Attach vs
        # Move, the confirm button carries both counts, and a one-line
        # inline notice replaces any native confirm() dialog.
        src = _stripped_js()
        self.assertIn("Move to this day", src)
        self.assertIn('"Attach"', src)
        self.assertIn("Attach \" + c.attach + \" · Move \" + c.move", src)
        self.assertIn("will move from other days.", src)
        self.assertIn("on Day ", src)
        self.assertIn("tdl-move-notice", src)
        self.assertNotIn("confirm(", src.replace("paintAttach(", ""))
        css = _stripped_css()
        self.assertIn(".tdl-move-notice", css)
        self.assertIn(".tdl-picker-action", css)

    def test_gps_wording_uses_two_surface_doctrine(self):
        # 2026-07-10 review fix 2: Travel Doc is the evidence-rich
        # operator surface. "(private)" GPS phrasing is narrator-room
        # language and is banned here.
        src = _stripped_js()
        self.assertNotIn("GPS on file (private)", src)
        self.assertIn("GPS found — available for Travel Doc context", src)

    def test_in_lab_day_note_drawer(self):
        src = _stripped_js()
        self.assertIn("tdl-note-drawer", src)
        self.assertIn("Add note", src)
        self.assertIn("/location-notes", src)

    def test_lori_opens_as_in_context_drawer_with_back_control(self):
        src = _stripped_js()
        self.assertIn("tdl-lori-overlay", src)
        self.assertIn("Back to Trip Plan", src)
        # Day chip + scope line stay visible in the overlay.
        self.assertIn("active_trip_day_id", src)
        self.assertIn("Unanchor day", src)

    def test_photo_lori_opens_overlay_drawer_not_tab(self):
        # 2026-07-10 review fix 1: "Talk with Lori about this photo"
        # opens the SAME in-context overlay drawer the day cards use.
        # The photo action must never tab-navigate to the Lori tab.
        src = _stripped_js()
        self.assertNotIn('setTab("lori")', src)
        self.assertIn("openLoriOverlayForPhoto", src)
        # Context-aware back label: photos return to Photos, day cards
        # return to Trip Plan.
        self.assertIn("Back to Photos", src)
        self.assertIn("loriReturnTab", src)
        # Photo chip stays visible in the overlay.
        self.assertIn("Unanchor photo", src)
        self.assertIn("active_photo_link_id", src)

    def test_day_card_actions_are_full_labels_in_one_order(self):
        src = _stripped_js()
        # One consistent action row builder used everywhere.
        self.assertIn("dayActionRow", src)
        for label in ("Talk with Lori", "Attach photos", "Add note",
                      "Edit day"):
            self.assertIn(label, src)
        # Order locked: Talk with Lori, then Attach photos, then Add
        # note, then Edit day, inside the shared builder.
        i = src.index("function dayActionRow")
        block = src[i:i + 700]
        pos = [block.index("Talk with Lori"), block.index("Attach photos"),
               block.index("Add note"), block.index("Edit day")]
        self.assertEqual(pos, sorted(pos), "day action order drifted")

    def test_compact_laptop_layout_rules(self):
        css = _stripped_css()
        self.assertIn("@media (max-width: 1500px)", css)
        # The workspace column must be minmax(0, 1fr) so 1280-1500px
        # widths never horizontal-scroll.
        self.assertIn("minmax(0, 1fr)", css)
        self.assertNotIn("minmax(520px", css)
        self.assertNotIn("minmax(460px", css)
        # Left rail collapse + inspector drawer + drawer chrome exist.
        self.assertIn(".tdl-rail-collapsed", css)
        self.assertIn(".tdl-drawer", css)
        js = _stripped_js()
        self.assertIn("railCollapsed", js)

    def test_inspector_sections_are_collapsible(self):
        src = _stripped_js()
        self.assertIn("tdl-ins-sec", src)
        for section in ("Overview", "Notes", "Photos", "Sources",
                        "Lori captures"):
            self.assertIn(section, src)
        # Overview is the only default-open section.
        self.assertIn('insSection("overview", "Overview", true)', src)


class Lab03Test(unittest.TestCase):
    """WO-TRAVEL-DOC-UI-LAB-03 — the two formerly-deferred gaps are now
    REQUIRED behavior: true day-scoped sources and the date-range
    reconcile flow, plus the lab-only evaluation checklist. These
    assertions also lock the never-delete posture (no DELETE calls
    anywhere in the lab) and preserve the round-2 fixes untouched."""

    def test_day_scoped_sources_ui(self):
        src = _stripped_js()
        # Attach-source drawer, day-scoped by construction.
        self.assertIn("Attach source to Day", src)
        self.assertIn("＋ Attach source", src)
        self.assertIn("Save source to this day", src)
        # Day inspector splits day-attached sources from the scope
        # fallback, and unlinking clears trip_day_id ONLY.
        self.assertIn("Attached to this day", src)
        self.assertIn("From linked stop/region", src)
        self.assertIn("Unlink from day", src)
        self.assertIn("clear_day", src)
        # Flags-honest display state.
        self.assertIn("In memoir OFF", src)

    def test_source_attach_vs_move_is_explicit(self):
        # Same Attach-vs-Move doctrine as the photo picker: sources on
        # another day are never silently reassigned. "Move to this day"
        # now appears for BOTH pickers (photos + sources), the source
        # move gets its own inline notice, and there is still no native
        # confirm() dialog anywhere in the lab.
        src = _stripped_js()
        self.assertGreaterEqual(src.count("Move to this day"), 2)
        self.assertIn("source(s) will move from other days.", src)
        cleaned = src.replace("paintAttach(", "").replace(
            "paintAttachSources(", "")
        self.assertNotIn("confirm(", cleaned)

    def test_sources_tab_day_badge_and_filters(self):
        src = _stripped_js()
        self.assertIn("sourceFilter", src)
        for label in ("Day-scoped", "Unattached", "In memoir"):
            self.assertIn(label, src)
        self.assertIn("tdl-badge-day", src)

    def test_reconcile_banners_and_generate_relabel(self):
        src = _stripped_js()
        self.assertIn("Generate / reconcile day cards", src)
        self.assertIn("not yet in the calendar.", src)
        self.assertIn("Add missing days", src)
        self.assertIn("outside the current trip dates", src)
        self.assertIn("kept to protect your notes", src)
        self.assertIn("Review outside-date days", src)
        # The UI reads the read-only preview endpoint and refreshes it
        # after generation.
        self.assertIn("/days/reconcile-preview", src)
        self.assertIn("reloadReconcile", src)

    def test_out_of_range_day_cards_visible_never_hidden(self):
        src = _stripped_js()
        self.assertIn("Outside current trip dates", src)
        # Chip renders inside the day card body — cards are never
        # filtered out of the Trip Plan list.
        self.assertIn("tdl-chip-outside", src)
        css = _stripped_css()
        self.assertIn(".tdl-chip-outside", css)
        self.assertIn(".tdl-reconcile-banner", css)

    def test_reconcile_drawer_reviews_without_deleting(self):
        src = _stripped_js()
        self.assertIn("tdl-reconcile-drawer", src)
        self.assertIn("Missing days (", src)
        self.assertIn("Outside-date day cards (", src)
        # Per-day content indicators in the review drawer.
        self.assertIn("Lori captures", src)
        self.assertIn("Mark outside-date days as reviewed (kept)", src)
        # NEVER-DELETE lock: the lab issues no DELETE request at all —
        # unlink flows are PATCH clear_day / photos-unlink only.
        self.assertNotIn('"DELETE"', src)
        self.assertNotIn("'DELETE'", src)

    def test_lab_only_evaluation_checklist(self):
        src = _stripped_js()
        self.assertIn("Lab-only evaluation checklist", src)
        self.assertIn("removable lab, not production", src)
        for label in ("Day cards generated / reconciled",
                      "Photos attached to days",
                      "Sources attached to days",
                      "Lori day captures present",
                      "Travelogue preview available"):
            self.assertIn(label, src)
        css = _stripped_css()
        self.assertIn(".tdl-eval-panel", css)

    def test_round_2_fixes_preserved(self):
        # WO-TRAVEL-DOC-UI-LAB-03 must not regress the round-2 review
        # fixes: photo-Lori overlay, GPS two-surface doctrine wording,
        # explicit Attach vs Move for photos, "Attach photos" naming.
        src = _stripped_js()
        self.assertIn("openLoriOverlayForPhoto", src)
        self.assertIn("GPS found — available for Travel Doc context", src)
        self.assertNotIn("GPS on file (private)", src)
        self.assertIn("Attach \" + c.attach + \" · Move \" + c.move", src)
        self.assertIn("Attach photos", src)
        self.assertNotIn("Add photos", src)


class FinishPassTest(unittest.TestCase):
    """2026-07-23 Travel Doc Lab finish-pass: no native prompts, preview matches
    the backend spoken trim, evidence text is editable, and evidence actions
    refresh the day/public-context counts."""

    def setUp(self):
        self.src = _stripped_js()   # comments removed — mentions don't count

    # ── Lab doctrine: no native dialogs ──────────────────────────────────
    def test_no_window_prompt_in_the_lab(self):
        self.assertNotIn("window.prompt(", self.src)
        self.assertNotIn("prompt(", self.src.replace("window.prompt(", ""))

    def test_no_native_confirm_or_alert(self):
        self.assertNotIn("window.confirm(", self.src)
        self.assertNotIn("window.alert(", self.src)

    def test_in_panel_editor_replaces_the_prompt(self):
        self.assertIn("openEvidenceEditor(", self.src)
        self.assertIn("renderEvidenceEditor(", self.src)
        # the two operator-entry lanes now open the editor
        self.assertIn('mode: "draft_observation"', self.src)
        self.assertIn('mode: "place_from_context"', self.src)

    # ── preview matches the backend spoken trim ──────────────────────────
    def test_spoken_trim_helper_present(self):
        self.assertIn("function spokenContextTrim(", self.src)
        # 160-char budget mirrors _SPOKEN_CONTEXT_CHARS on the backend
        self.assertIn("SPOKEN_CONTEXT_CHARS = 160", self.src)

    def test_preview_trims_place_vision_observation_but_not_ocr(self):
        i = self.src.index("function evLoriWording(")
        block = self.src[i:i + 1600]
        # OCR branch speaks the untrimmed value (stripDot), like the backend
        self.assertIn("the OCR draft appears to read '\" + stripDot", block)
        # place / vision / observation branches speak the trimmed value
        self.assertIn("the place context suggests \" + spoken", block)
        self.assertIn("the draft image context suggests \"\n           + spoken",
                      block)
        self.assertIn("the draft photo observation suggests \"\n           + spoken",
                      block)

    # ── evidence text editing (edit revokes approval, clears memoir) ──────
    def test_edit_row_patches_result_summary(self):
        self.assertIn('"Edit text"', self.src)
        self.assertIn("result_summary: t", self.src)
        # the drawer for edit warns it revokes approval
        self.assertIn("revokes approval", self.src)

    # ── refresh the counts after evidence changes ────────────────────────
    def test_refresh_after_evidence_reloads_days_and_public_context(self):
        self.assertIn("function refreshAfterEvidence(", self.src)
        i = self.src.index("function refreshAfterEvidence(")
        block = self.src[i:i + 400]
        self.assertIn("reloadDays()", block)
        self.assertIn("reloadPublicContext()", block)
        # and the evidence actions call it
        self.assertIn(".then(refreshAfterEvidence)", self.src)
        self.assertIn("refreshAfterEvidence();", self.src)


class DocumenterDoubleSendGuardTest(unittest.TestCase):
    """travel-documenter.js modal double-send guard (parity with the 2026-05-07
    chat-path _loriIsBusy fix) — a second click while Lori is generating must
    not fire the turn twice."""

    def setUp(self):
        p = _REPO_ROOT / "ui" / "js" / "travel-documenter.js"
        self.src = re.sub(r"/\*[\s\S]*?\*/|//[^\n]*", "",
                          p.read_text(encoding="utf-8"))

    def test_send_is_guarded_and_cleared(self):
        i = self.src.index("_send: function ()")
        block = self.src[i:i + 400]
        self.assertIn("if (this._busy) return;", block)
        self.assertIn("this._busy = true;", block)
        # cleared on done, on connection failure, and by a failsafe timer
        self.assertIn("self._busy = false;", self.src)
        self.assertIn("_busyTimer", self.src)


if __name__ == "__main__":
    unittest.main()
