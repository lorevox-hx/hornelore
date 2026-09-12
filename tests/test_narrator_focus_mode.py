"""WO-LORI-NARRATOR-FOCUS-MODE-01 — structural pins for the narrator focus mode.

WHAT THESE TESTS ARE, STATED PLAINLY. They are STRUCTURAL PINS against the
shipped page and the shipped module. They are NOT acceptance evidence for the
mode's behaviour: CLAUDE.md is explicit that source-string assertions are never
acceptance by themselves, and this WO's acceptance is the live browser walk in
the spec (§Acceptance, eleven points, including the measured 697px composer
geometry and a real spoken turn). Nothing here may be quoted as "Focus Mode
works".

What they DO buy, and it is the specific thing this repository has been burned
by twice:

  * **Phantom selectors.** "A guard pinned to a phantom selector confirms the
    typo instead of catching it" (CLAUDE.md, UI harness hazards). Every id and
    class the module and the stylesheet reach for is asserted PRESENT in
    `hornelore1.0.html`. If someone renames `#crChatInner`, these fail here
    rather than at a narrator's session.
  * **Negative invariants that are genuinely decidable from source.** The mode
    must contain no transport, no state write, no persistence and no
    `turn_mode`. Absence is exactly the kind of claim a source read settles.
  * **The landed composer repair.** Focus mode must preserve
    `min-width: 0` + the wrap rules, never rebuild or undo them. Both sides
    are asserted: the shipped repair still exists, and the focus CSS does not
    contradict it.

Run:
    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_narrator_focus_mode
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
UI = REPO_ROOT / "ui"
PAGE = UI / "hornelore1.0.html"
JS = UI / "js" / "narrator-focus-mode.js"
CSS = UI / "css" / "narrator-focus-mode.css"

BODY_CLASS = "lv-narrator-focus"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _code(src: str) -> str:
    """Source with comments removed.

    The negative invariants below ("contains no fetch", "names no individual
    popover") are claims about CODE. A comment cannot fetch anything, and this
    module's header deliberately NAMES the transport it must not use, so
    checking the raw text would fail on its own documentation. Block comments
    go first, then any line that is only a line-comment — narrow on purpose, so
    a `//` inside a string is never mistaken for one."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    keep = [ln for ln in src.splitlines() if not ln.strip().startswith(("//", "*"))]
    return "\n".join(keep)


def _css_ids(css: str):
    """Every id selector in a stylesheet, excluding hex colours.

    `#e3ddd0` is a colour, not an element. Without this the selector-existence
    check would demand the page contain an element called `e3ddd0` — a test
    failing for a reason that has nothing to do with the product."""
    hex_like = re.compile(r"^[0-9a-fA-F]{3,8}$")
    return sorted({m for m in re.findall(r"#([A-Za-z][\w-]*)", css) if not hex_like.match(m)})


class _Sources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for p in (PAGE, JS, CSS):
            if not p.is_file():
                raise AssertionError(f"missing shipped file: {p}")
        cls.page = _read(PAGE)
        cls.js = _read(JS)
        cls.css = _read(CSS)


# ══════════════════════════════════════════════════════════════════════

class Mounted(_Sources):
    """The mode is actually wired into the page it claims to modify."""

    def test_stylesheet_and_module_are_linked(self):
        self.assertRegex(self.page, r'<link[^>]+href="css/narrator-focus-mode\.css')
        self.assertRegex(self.page, r'<script[^>]+src="js/narrator-focus-mode\.js')

    def test_entry_control_exists_and_calls_the_module(self):
        self.assertIn('id="lvNarratorFocusBtn"', self.page)
        self.assertIn("lvNarratorFocusEnter", self.page)
        self.assertIn('id="lvNarratorFocusStatus"', self.page)

    def test_entry_control_is_in_the_always_present_header_not_the_narrator_room(self):
        """Operator-side. It sits in the header control strip beside the Bug
        launcher (#205) because the operator needs it DURING a session, which
        is precisely when the Operator tab is not on screen. It must not be
        inside the narrator room, which is narrator surface."""
        header = self.page.split('<header id="lv80Header">', 1)[1].split("</header>", 1)[0]
        self.assertIn('id="lvNarratorFocusBtn"', header)
        room = self.page.split('<div id="lvNarratorRoom">', 1)[1].split("<!-- /lvNarratorRoom -->", 1)[0]
        self.assertNotIn("lvNarratorFocusBtn", room)

    def test_there_is_no_visible_exit_affordance(self):
        """The locked principles forbid a Return-to-Operator control in narrator
        flow. Exit is the documented chord and nothing else — no button, no
        label, anywhere in the module or its stylesheet."""
        for src in (self.js, self.css):
            low = src.lower()
            for forbidden in ("return to operator", "exit focus", "leave focus", "back to operator"):
                self.assertNotIn(forbidden, low, forbidden)
        self.assertNotIn("lvNarratorFocusExit", self.page,
                         "exit must not be wired to any on-screen control")


class SelectorsArePinnedAgainstTheShippedPage(_Sources):
    """Every selector the module and the stylesheet reach for must EXIST.

    This is the anti-phantom-selector guard. The values are read out of the two
    focus-mode files and checked against the page, so a selector added to them
    later is covered without editing this test."""

    #: ids the module addresses by name, and what each one is for.
    MODULE_IDS = {
        "lvNarratorFocusBtn": "the entry control (focus returns here on exit)",
        "lvNarratorFocusStatus": "the operator-facing refusal line",
        "crChatInner": "the conversation scroller — focus target on entry",
        "lvNarratorTab": "the narrator panel, tested for .lv-shell-panel-active",
    }

    def test_every_id_the_module_addresses_exists_in_the_page(self):
        for el_id, why in self.MODULE_IDS.items():
            self.assertIn(el_id, self.js, f"{el_id} should be referenced by the module ({why})")
            self.assertIn(f'id="{el_id}"', self.page, f'{el_id} ({why}) is not in the shipped page')

    def test_the_active_panel_class_the_module_tests_is_the_one_the_shell_sets(self):
        """`lv-shell-panel-active` is toggled by app.js:676. If the shell ever
        renames it, the readiness refusal would silently pass forever."""
        self.assertIn("lv-shell-panel-active", self.js)
        self.assertIn("lv-shell-panel-active", _read(UI / "js" / "app.js"))

    def test_the_readiness_authority_the_module_reads_is_the_shipped_one(self):
        """Focus mode consumes the readiness the page already computes — it does
        not invent a second answer or read the server itself."""
        self.assertIn("window.isLlmReady", self.js)
        self.assertIn("window.isLlmReady = isLlmReady", _read(UI / "js" / "app.js"))

    def test_every_id_the_stylesheet_hides_or_restyles_exists_in_the_page(self):
        ids = _css_ids(self.css)
        self.assertGreater(len(ids), 15, "the stylesheet should address the room's real furniture")
        missing = [i for i in ids if f'id="{i}"' not in self.page]
        self.assertEqual(missing, [], f"stylesheet targets absent from the shipped page: {missing}")

    def test_the_bubble_classes_the_stylesheet_restyles_are_the_ones_the_renderer_emits(self):
        """`appendBubble` (app.js) builds `div.bubble.bubble-<role>` containing
        `.bubble-speaker` + `.bubble-body`. Typography rules pinned to any other
        class name would style nothing."""
        app = _read(UI / "js" / "app.js")
        self.assertIn("`bubble bubble-${role}`", app)
        self.assertIn('label.className="bubble-speaker"', app)
        self.assertIn('body.className="bubble-body"', app)
        for cls in (".bubble-body", ".bubble-speaker", ".bubble-ai", ".bubble-user"):
            self.assertIn(cls, self.css)


class PresentationOnly(_Sources):
    """Invariants 1, 2 and 4 — decidable from source, and each one is a rule the
    WO fails if it is broken."""

    def test_module_has_no_transport_no_fetch_no_server_read(self):
        low = _code(self.js).lower()
        for forbidden in ("fetch(", "websocket", "xmlhttprequest", "/api/", "navigator.sendbeacon"):
            self.assertNotIn(forbidden, low, f"presentation-only mode must not contain {forbidden!r}")

    def test_module_proposes_no_turn_mode_and_touches_no_guard_surface(self):
        low = _code(self.js).lower()
        for forbidden in ("turn_mode", "turnmode", "guard_lab", "guardlab", "eligib"):
            self.assertNotIn(forbidden, low, forbidden)

    def test_module_never_persists_the_mode(self):
        """Invariant 4 and the anti-lockout property behind the chord-only exit:
        a reload must always restore the full operator UI."""
        low = _code(self.js).lower()
        for forbidden in ("localstorage", "sessionstorage", "indexeddb", "document.cookie"):
            self.assertNotIn(forbidden, low, forbidden)

    def test_module_never_reopens_or_reselects_the_narrator(self):
        """Invariant 3. Opening a narrator appends four `bio_facts` through
        `questionnaire_put` (BACKLOG §5, measured in Portable Narrator §36.1).
        A presentation toggle must not fire that path — nor switch tabs, which
        is what the neighbouring `lvEnterInterviewMode` does."""
        low = _code(self.js).lower()
        for forbidden in ("loadperson", "setnarrator", "lvshellshowtab", "startidentityonboarding",
                          "questionnaire_put", "person_id ="):
            self.assertNotIn(forbidden, low, forbidden)
        # state.person_id is READ for the refusal check, and only read.
        self.assertIn("state.person_id", self.js)

    def test_module_does_not_touch_the_mic_state_machine(self):
        """Invariant 5: the mic's classes are set by WO-MIC-UI-02A. Focus mode
        changes their clothes in CSS and must not add, remove or infer them."""
        low = _code(self.js).lower()
        for forbidden in ("mic-active", "mic-wait", "mic-blocked", "togglemic", "btnmic"):
            self.assertNotIn(forbidden, low, forbidden)

    def test_the_mode_is_not_preapplied_in_the_markup(self):
        self.assertNotRegex(self.page, r"<body[^>]*" + BODY_CLASS)


class TheModeIsFullyGated(_Sources):
    """Nothing in the stylesheet may reach outside the mode. A rule that is not
    gated on the body class changes the ordinary operator UI, which is the
    'no style bleed' acceptance point (§11) and the easiest way for this WO to
    do harm."""

    #: The documented exception: the refusal line is shown when the mode is
    #: REFUSED, i.e. exactly when the body class is absent.
    UNGATED_ALLOWED = (".lv-narrator-focus-status",)

    def _selector_blocks(self):
        css = re.sub(r"/\*.*?\*/", "", self.css, flags=re.S)
        for block in re.findall(r"([^{}]+)\{[^{}]*\}", css):
            sel = block.strip()
            if not sel or sel.startswith("@"):
                continue
            yield sel

    def test_every_rule_is_gated_on_the_body_class(self):
        ungated = []
        for sel in self._selector_blocks():
            parts = [p.strip() for p in sel.split(",") if p.strip()]
            for p in parts:
                if f"body.{BODY_CLASS}" in p:
                    continue
                if any(p.startswith(a) for a in self.UNGATED_ALLOWED):
                    continue
                ungated.append(p)
        self.assertEqual(ungated, [], f"selectors that escape the mode: {ungated}")

    def test_the_mode_class_is_the_documented_one_and_not_the_neighbouring_interview_mode(self):
        """`lv-interview-mode-active` (WO-INTERVIEW-MODE-01) is a DIFFERENT mode
        with real side effects — it switches tabs and can dispatch a Lori turn.
        Focus mode must never key off it, extend it, or be renamed into it."""
        self.assertIn(f"body.{BODY_CLASS}", self.css)
        # `_code` because BOTH files name that mode in their headers, on
        # purpose, to record why it was not reused. Documenting a hazard is
        # the opposite of depending on it; the claim under test is about code.
        self.assertNotIn("lv-interview-mode-active", _code(self.css))
        self.assertNotIn("lv-interview-mode-active", _code(self.js))


class GenericClosureAndRefusals(_Sources):
    """The most likely implementation miss in the whole WO, per the spec: a
    hand-written list of popovers instead of the generic selector."""

    def test_popover_closure_is_generic_and_uses_the_platform_state(self):
        self.assertIn("[popover]:popover-open", self.js)
        self.assertIn("hidePopover", self.js)
        # Never the false-negative check: top-layer elements are position:fixed,
        # so `offsetParent` is null for an OPEN popover (CLAUDE.md, UI harness
        # hazards) — it has reported a shut panel while 1,408 characters were
        # being read out of it.
        #
        # This asserts on PROPERTY ACCESS (dot or bracket form), not on the
        # word. The first version searched the whole file for the literal and
        # failed on the module's own comment WARNING against it — a test that
        # would have been "fixed" by deleting the warning, which is precisely
        # backwards. Documentation naming a hazard is not use of it.
        self.assertNotRegex(
            self.js,
            r"(?:\.\s*offsetParent\b|\[\s*['\"]offsetParent['\"]\s*\])",
            "offsetParent must never be READ here; keep the comment that says so",
        )

    def test_popover_closure_names_no_individual_popover(self):
        """A hand-written list goes stale the first time someone adds one."""
        low = _code(self.js).lower()
        for named in ("lv10dbugpanel", "memoirscrollpopover", "lifemap", "reviewqueue"):
            self.assertNotIn(named, low, f"closure must not name {named!r}")

    def test_open_dialogs_refuse_entry_and_are_never_closed(self):
        """A <dialog> may hold an unsaved edit (`memoirEditModal` is the real
        hazard). Entry is refused; the dialog is not touched."""
        self.assertIn('dialog[open]', self.js)
        self.assertNotIn(".close()", self.js)
        self.assertNotIn("closeDialog", self.js)

    def test_all_refusals_are_present(self):
        fn = self.js.split("function refusalReason()", 1)[1].split("\n  }", 1)[0]
        self.assertIn("dialog[open]", fn)
        self.assertIn("fc-active", fn)          # the capture overlay, a dialog in all but tag name
        self.assertIn("lv-shell-panel-active", fn)
        self.assertIn("state.person_id", fn)
        self.assertIn("isLlmReady", fn)

    def test_an_open_capture_overlay_refuses_entry_and_is_never_closed(self):
        """`#fcCanvas` is `role="dialog" aria-modal="true"` but NOT a native
        <dialog>, so the `dialog[open]` check cannot see it — and `#fcTextarea`
        can hold text the narrator typed and has not sent. Entry refuses on the
        shipped open-state class; the overlay is not closed, and FocusCanvas's
        own API is never called."""
        self.assertIn("fcCanvas", self.js)
        self.assertIn("fc-active", self.js)
        for forbidden in ("FocusCanvas.close", "FocusCanvas._", "fcCanvas.classList.remove",
                          "classList.add(\"fc-", "classList.remove(\"fc-"):
            self.assertNotIn(forbidden, _code(self.js), forbidden)

    def test_the_refusal_check_is_exported_for_the_harness(self):
        """The live walk asserts refusals by running the REAL check, never by
        reimplementing it in the harness."""
        self.assertIn("window.lvNarratorFocusRefusalReason = refusalReason", self.js)


class ExitChord(_Sources):
    def test_exit_is_a_multi_key_chord_not_a_single_key(self):
        """A single key is producible by a narrator; a three-modifier chord is
        not, and cannot be typed by accident into the composer."""
        self.assertIn("ctrlKey", self.js)
        self.assertIn("altKey", self.js)
        self.assertIn("shiftKey", self.js)
        self.assertIn("EXIT_CHORD_LABEL", self.js)

    def test_the_chord_listens_in_capture_phase_so_the_composer_cannot_swallow_it(self):
        self.assertIn('addEventListener("keydown", onKeyDown, true)', self.js)

    def test_the_chord_only_acts_while_the_mode_is_active(self):
        fn = self.js.split("function onKeyDown(e)", 1)[1].split("\n  }", 1)[0]
        self.assertIn("if (!isActive()) return;", fn)

    def test_the_chord_is_documented_operator_side(self):
        self.assertIn("Ctrl + Alt + Shift + F", self.js)


class ComposerRepairIsPreservedNotRebuilt(_Sources):
    """§'Composer narrow-width — regression VERIFICATION, not repair'.

    Both halves are asserted: the landed repair still exists in the shipped
    page, and focus mode does not contradict it. The MEASURED proof (697px:
    textarea ≥300px wide and ≥44px tall, Send fully inside the viewport with a
    ≥48px target, zero horizontal overflow) belongs to the live walk — a
    stylesheet read cannot produce a pixel."""

    def test_the_landed_repair_is_still_in_the_shipped_page(self):
        page = self.page
        self.assertIn("min-width: 0", page)
        self.assertIn(".lv-composer-row { flex-wrap: wrap; }", page)
        self.assertIn(".lv-composer-row > * { flex-shrink: 0; }", page)
        self.assertIn(".lv-composer-row > #chatInput", page)   # the ≤820px full-row rule

    def test_focus_mode_reasserts_min_width_zero_and_never_undoes_the_wrap(self):
        block = self.css.split(f"body.{BODY_CLASS} #chatInput {{", 1)[1].split("}", 1)[0]
        self.assertIn("min-width: 0", block)
        self.assertIn("flex: 1 1 auto", block)
        css = re.sub(r"/\*.*?\*/", "", self.css, flags=re.S)
        self.assertNotIn("flex-wrap: nowrap", css)
        # `(?<!-)` so `min-width` and `max-width` are not mistaken for a fixed
        # width: `min-width: 0` IS the repair, and `max-width` on the row is a
        # reading measure, not a size constraint on the textarea.
        self.assertNotRegex(css, r"lv-composer-row[^{]*\{[^}]*(?<!-)width:")
        self.assertNotRegex(css, r"#chatInput\s*\{[^}]*(?<!-)width:")

    def test_focus_mode_does_not_shrink_the_row_children(self):
        css = re.sub(r"/\*.*?\*/", "", self.css, flags=re.S)
        self.assertNotRegex(css, r"lv-composer-row\s*>\s*\*[^{]*\{[^}]*flex-shrink:\s*1")


class MicAndMotion(_Sources):
    """The mic keeps its states, its semantics and exactly one animation."""

    def test_listening_keeps_its_pulse_and_wait_is_made_static(self):
        css = re.sub(r"/\*.*?\*/", "", self.css, flags=re.S)
        # WAIT: the amber pulse is suppressed…
        self.assertRegex(css, r"#btnMic\.mic-wait\s*\{\s*animation:\s*none")
        # …and LISTENING's is not touched outside the reduced-motion block.
        outside_media = re.split(r"@media[^{]*\{", css)[0]
        self.assertNotIn("mic-active", outside_media)

    def test_reduced_motion_stops_even_the_kept_pulse(self):
        self.assertIn("prefers-reduced-motion", self.css)

    def test_the_parked_capture_overlay_is_removed_from_the_tab_order(self):
        """Acceptance case 2 is "no operator control reachable by click OR TAB
        TRAVERSAL". `#fcCanvas` parks below the viewport when closed and kept
        its controls focusable — `fcDoneBtn` was focusable at y≈1074 in a
        723px-tall viewport, measured live 2026-09-12. The first version of
        this suite passed that defect, because it only asked whether the
        controls I happened to name were hidden.

        `display: none` is the requirement, not `visibility` or `opacity`:
        only display removes an element from the tab order and the
        accessibility tree."""
        css = re.sub(r"/\*.*?\*/", "", self.css, flags=re.S)
        for root in ("#fcCanvas", "#fcScrim"):
            self.assertRegex(
                css, root + r"[^{}]*\{[^}]*display:\s*none",
                f"{root} must be display:none in focus mode, or its controls stay tab-reachable",
            )
        self.assertNotRegex(css, r"#fcCanvas[^{}]*\{[^}]*visibility:\s*hidden",
                            "visibility:hidden leaves the element in the tab order")

    def test_the_mic_is_the_sole_status_surface(self):
        """SOLE is the requirement, so BOTH of the room's other status
        indicators are hidden: `#lv80LoriDot` (pulsing dot) and `#lv80Thinking`
        ("Lori is thinking…"). The mic's WAIT state already says Lori owns the
        turn. `#lv80IdleCue` is deliberately NOT in this list — it is WO-10C's
        invitational re-entry, patience rather than status."""
        css = re.sub(r"/\*.*?\*/", "", self.css, flags=re.S)
        for hidden in ("#lv80LoriDot", "#lv80Thinking"):
            self.assertRegex(
                css, hidden + r"[^{}]*\{[^}]*display:\s*none",
                f"{hidden} must be hidden in focus mode",
            )
        self.assertNotRegex(css, r"#lv80IdleCue[^{}]*\{[^}]*display:\s*none",
                            "the take-your-time cue is patience, not status — keep it")

    def test_history_is_subordinated_by_size_never_by_contrast(self):
        """'Focus mode must not use low contrast or opacity to de-emphasise
        history' — a narrator must never work harder to reread their own words.
        The only opacity in the file RAISES the shipped speaker label from .55."""
        css = re.sub(r"/\*.*?\*/", "", self.css, flags=re.S)
        opacities = re.findall(r"opacity:\s*([\d.]+)", css)
        self.assertTrue(all(float(o) == 1 for o in opacities),
                        f"focus mode must not dim anything: {opacities}")

    def test_nothing_counts_or_hurries_the_narrator(self):
        """WO-10C's protected silence has a visual counterpart: nothing focus
        mode shows may count, tick or hurry. A tripwire, not a proof — the
        proof is a live silence in the acceptance walk."""
        low = (_code(self.css) + _code(self.js)).lower()
        for forbidden in ("countdown", "elapsed", "timer", "<progress"):
            self.assertNotIn(forbidden, low, forbidden)


if __name__ == "__main__":
    unittest.main()
