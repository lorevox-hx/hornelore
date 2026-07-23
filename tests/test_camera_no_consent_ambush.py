"""BUG-CAM-CONSENT-AMBUSH-ON-OPEN-01 — no camera-consent modal on narrator open.

permCamOn and emotionAware both DEFAULT ON ("family defaults"). The narrator-
load auto-start therefore called startEmotionEngine -> FacialConsent.request ->
the consent MODAL popped the instant a narrator was opened, with no user
gesture. Proven live 2026-07: opening "Amelia" (no consent record) fired the
overlay straight out of lv80SwitchPerson.

An older narrator opening their own session must not be ambushed by a camera-
consent dialog. A consent prompt has to come from a DELIBERATE action (clicking
the Cam toggle), never from merely opening a narrator.

Fix: the auto-start now additionally requires FacialConsent.isGranted() — it is
a convenience for the ALREADY-consented (friction-free return), and is never
the thing that first asks. This is a source-shape guard: the inline handler in
hornelore1.0.html isn't unit-testable in isolation, so we assert the gate is
present and wired into the auto-start condition.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_HTML = (_REPO_ROOT / "ui" / "hornelore1.0.html").read_text(encoding="utf-8")


class CameraConsentAmbushGuardTest(unittest.TestCase):
    def _autostart_block(self):
        # The WO-CAM-FIX auto-start condition + its body.
        i = _HTML.index("BUG-CAM-CONSENT-AMBUSH-ON-OPEN-01")
        j = _HTML.index("startEmotionEngine();", i)
        return _HTML[i:j + 40]

    def test_autostart_requires_stored_consent(self):
        block = self._autostart_block()
        # The isGranted() gate must be part of the condition that guards
        # startEmotionEngine on narrator open.
        self.assertIn("FacialConsent.isGranted()", block)
        self.assertIn("_fcGrantedForAutostart", block)
        self.assertRegex(
            block,
            r"if\s*\([^)]*!cameraActive[^)]*_fcGrantedForAutostart",
            "the narrator-open auto-start must require granted consent, so it "
            "cannot pop the consent modal on open")

    def test_deliberate_toggle_path_still_requests_consent(self):
        # The Cam toggle -> startEmotionEngine -> FacialConsent.request path is
        # the SANCTIONED way to ask. It must remain intact (this is what lets
        # the operator turn the camera on deliberately).
        self.assertIn("const granted = await FacialConsent.request();",
                      (_REPO_ROOT / "ui" / "js" / "emotion-ui.js")
                      .read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
