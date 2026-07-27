"""BUG-LV80-TOGGLE-REFERENCEERROR-01 (WO-POST-LORI-CLEANUP-AND-UNBLOCK-01
Lane 2) — the header narrator card's inline onclick can never throw
"lv80ToggleNarratorSwitcher is not defined" again.

WHAT WAS ACTUALLY WRONG. Nothing was renamed and nothing was removed.
The handler is declared, exactly once, inside the classic inline
<script> that begins around line 5532 of hornelore1.0.html -- roughly
3,600 lines into a ~105 KB block, with ~60 external scripts still
loading behind it. The card itself paints at line 2928, near the top of
<body>. Cold boot on this stack is about four minutes, and the file's
own BUG-NARRATOR-SWITCHER-EMPTY-ON-COLD-BOOT-01 banner records that
operators click this exact chip during that window. A click landing
before the inline block finishes evaluating hits an undeclared
identifier and throws.

THE FIX HAS TWO HALVES, and both are asserted here:

  1. The inline handler is feature-tested rather than a bare call, so
     an early click warns on the console instead of throwing.
  2. The globals are mirrored onto window explicitly, following the
     same convention the WO-10C silence-ladder constants already use in
     this file, so the binding is intentional rather than an accident
     of sloppy-mode top-level function declarations.

The control is NOT retired. Narrator switching still works exactly as
it did; this file also pins the behaviour that made the toggle correct
in the first place (the CHRIS RULE against awaiting the API inside it).
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_HTML = _REPO_ROOT / "ui" / "hornelore1.0.html"
_SRC = _HTML.read_text(encoding="utf-8")

_CARD_RE = re.compile(r'<div id="lv80ActiveNarratorCard"[^>]*>')


class InlineHandlerTest(unittest.TestCase):
    def setUp(self):
        cards = _CARD_RE.findall(_SRC)
        self.assertEqual(len(cards), 1,
                         "expected exactly one lv80ActiveNarratorCard")
        self.card = cards[0]

    def test_the_card_still_has_a_click_handler(self):
        # The control is active. If a future edit retires it, that is a
        # product decision and this test should be deleted deliberately,
        # not silently satisfied by an unclickable card.
        self.assertIn("onclick=", self.card)

    def test_the_handler_is_not_a_bare_call(self):
        # This is the regression. `onclick="lv80ToggleNarratorSwitcher()"`
        # throws a ReferenceError when clicked before the inline script
        # block has evaluated.
        self.assertNotIn('onclick="lv80ToggleNarratorSwitcher()"', _SRC)

    def test_the_handler_feature_tests_before_calling(self):
        self.assertIn("window.lv80ToggleNarratorSwitcher ?", self.card)
        self.assertIn("window.lv80ToggleNarratorSwitcher()", self.card)

    def test_an_early_click_degrades_to_a_console_warning(self):
        self.assertIn("console.warn", self.card)
        # No native dialog on the operator path.
        for forbidden in ("alert(", "confirm(", "prompt("):
            self.assertNotIn(forbidden, self.card)


class WindowMirrorTest(unittest.TestCase):
    def test_the_toggle_is_defined_exactly_once(self):
        self.assertEqual(
            _SRC.count("function lv80ToggleNarratorSwitcher("), 1)

    def test_the_toggle_is_mirrored_onto_window(self):
        self.assertIn(
            "window.lv80ToggleNarratorSwitcher = lv80ToggleNarratorSwitcher;",
            _SRC)

    def test_the_open_variant_is_mirrored_too(self):
        # lv80OpenNarratorSwitcher is reached from other call sites for
        # the same popover; leaving one mirrored and one not is how this
        # comes back.
        self.assertIn("function lv80OpenNarratorSwitcher(", _SRC)
        self.assertRegex(
            _SRC,
            r"window\.lv80OpenNarratorSwitcher\s*=\s*lv80OpenNarratorSwitcher;")

    def test_the_mirror_comes_after_the_declarations(self):
        decl = _SRC.index("function lv80ToggleNarratorSwitcher(")
        mirror = _SRC.index(
            "window.lv80ToggleNarratorSwitcher = lv80ToggleNarratorSwitcher;")
        self.assertLess(decl, mirror)


class SwitcherBehaviourPreservedTest(unittest.TestCase):
    """Lane 2's scope wall: fix the ReferenceError, rewrite no UI."""

    def setUp(self):
        start = _SRC.index("function lv80ToggleNarratorSwitcher(")
        self.body = _SRC[start:_SRC.index(
            "function lv80OpenNarratorSwitcher(", start)]

    def test_it_still_toggles_the_popover(self):
        self.assertIn('getElementById("lv80NarratorSwitcher")', self.body)
        self.assertIn("hidePopover()", self.body)
        self.assertIn("showPopover()", self.body)

    def test_it_still_refuses_to_switch_during_trainer_mode(self):
        # WO-11E: the card is cosmetic while trainer mode is active.
        self.assertIn("trainerNarrators", self.body)

    def test_it_still_honours_the_no_await_rule(self):
        # BUG-NARRATOR-SWITCHER-EMPTY-ON-COLD-BOOT-01, CHRIS RULE:
        # never await on the API inside the switcher toggle.
        self.assertNotIn("await", self.body)
        self.assertIn("_lv80RenderOrKickRefresh()", self.body)


if __name__ == "__main__":
    unittest.main()
