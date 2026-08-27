"""The Bug Panel's narrator label reads a key that exists.

BUG-BUGPANEL-NARRATOR-ALWAYS-UNNAMED-01 (2026-08-27).

── WHY THIS FILE EXISTS ──────────────────────────────────────────────

`_narratorLabel()` in `ui/js/bug-panel-preflight.js` read
`state.session.narratorName || .preferredName || .fullName`. **None of
those three keys exist on `state.session`.** Enumerated against a live
session, it holds `currentPass, identityPhase, assistantRole,
identityCapture, profileSeed, onboarding, sessionStyle, priorUserTurns,
currentEra, loop, turnMode, confusionTurnCount, currentMode,
lastTurnMode, pendingCorrection`.

So the label rendered `(unnamed)` for **every narrator, always**, while
the header two inches above showed the name and the server held
`display_name` plus both other anchors.

The fix was one line and was accepted on live observation alone. That is
not enough for a UI reader that is the operator's own diagnostic
surface, so the behaviour is pinned here.

── HOW THIS TESTS JAVASCRIPT WITHOUT A BROWSER ───────────────────────

`_narratorLabel()` is a pure function of one global. Rather than stand
up a DOM, the function body is extracted from the source and evaluated
in Node with a synthetic `state`. That keeps the test honest about WHAT
it covers — the key-resolution logic, which is where the bug was — and
honest about what it does not: rendering, mounting, and the 2-second
refresh loop are not exercised here.

Skips when `node` is unavailable, and says so.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SOURCE = _REPO_ROOT / "ui" / "js" / "bug-panel-preflight.js"

_NODE = shutil.which("node")


@unittest.skipUnless(_NODE, "needs node to evaluate the JS under test")
class NarratorLabelTests(unittest.TestCase):
    """One case per state the operator can actually be looking at."""

    @classmethod
    def setUpClass(cls):
        source = _SOURCE.read_text(encoding="utf-8")
        match = re.search(
            r"function _narratorLabel\(\) \{.*?\n  \}", source, re.S)
        if not match:
            raise AssertionError(
                "_narratorLabel() not found in bug-panel-preflight.js — the "
                "function was renamed or reshaped, and this test is now "
                "measuring nothing")
        cls.fn = match.group(0)

    def label_for(self, session):
        """Evaluate the real function body against a synthetic `state`."""
        script = (
            "var state = " + json.dumps({"session": session}) + ";\n"
            + self.fn + "\n"
            + "process.stdout.write(String(_narratorLabel()));\n"
        )
        out = subprocess.run([_NODE, "-e", script], capture_output=True,
                             text=True, timeout=30)
        self.assertEqual("", out.stderr.strip(), out.stderr)
        return out.stdout

    # ── the case that was broken ────────────────────────────────────
    def test_a_NAMED_narrator_renders_the_name(self):
        """The live shape, verified against a running session:
        identityCapture = {name, dob, birthplace}."""
        self.assertEqual("Del", self.label_for({
            "identityCapture": {"name": "Del", "dob": "1950-03-04",
                                "birthplace": "Fargo, North Dakota"},
            "currentPass": "pass2a", "identityPhase": "complete"}))

    def test_the_OLD_keys_still_work_if_anything_populates_them(self):
        """They were kept in the chain deliberately. If some other
        surface ever sets them the label should not regress."""
        for key in ("narratorName", "preferredName", "fullName"):
            with self.subTest(key=key):
                self.assertEqual("Verlie", self.label_for({key: "Verlie"}))

    # ── the states that must NOT invent a name ──────────────────────
    def test_a_BLANK_narrator_is_unnamed(self):
        for session in ({}, {"identityCapture": {}},
                        {"identityCapture": {"name": ""}},
                        {"identityCapture": {"dob": "1950-03-04"}}):
            with self.subTest(session=session):
                self.assertEqual("(unnamed)", self.label_for(session))

    def test_a_RESET_session_is_unnamed_not_stale(self):
        """Reset Identity clears narrator-scoped state in one operation.

        A label that kept the previous narrator's name after a reset
        would be worse than "(unnamed)": it would name the wrong person
        on the surface an operator uses to check who is loaded.
        """
        self.assertEqual("(unnamed)", self.label_for(
            {"currentPass": "pass1", "identityPhase": "unknown",
             "identityCapture": {}}))

    def test_a_NARRATOR_SWITCH_shows_the_new_narrator(self):
        """Switching is the case the operator is most likely to be
        checking, and the one where a stale name is most expensive."""
        before = self.label_for({"identityCapture": {"name": "Del"}})
        after = self.label_for({"identityCapture": {"name": "Kent"}})
        self.assertEqual("Del", before)
        self.assertEqual("Kent", after)

    def test_TRAINER_MODE_identity_is_preserved_not_blanked(self):
        """Trainer mode intentionally retains identity state, so the
        label must keep reporting it rather than treating the mode as a
        reason to go quiet."""
        self.assertEqual("Marvin", self.label_for({
            "identityCapture": {"name": "Marvin"},
            "assistantRole": "trainer", "sessionStyle": "oral_history"}))

    # ── non-vacuity ─────────────────────────────────────────────────
    def test_the_harness_can_actually_fail(self):
        """If the extracted function were a stub returning a constant,
        every assertion above would pass for the wrong reason."""
        self.assertNotEqual(self.label_for({"identityCapture": {"name": "A"}}),
                            self.label_for({"identityCapture": {"name": "B"}}))

    def test_the_source_no_longer_reads_ONLY_the_missing_keys(self):
        """Structural backstop: `identityCapture` must be consulted.

        Guards the specific regression — someone "simplifying" the chain
        back to the three keys that do not exist.
        """
        self.assertIn("identityCapture", self.fn,
                      "the label no longer reads identityCapture, which is "
                      "the only key that actually holds the name")


if __name__ == "__main__":
    unittest.main()
