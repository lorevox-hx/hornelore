"""BUG-FACIAL-CONSENT-DECLINE-NOT-PERSISTED-01.

Consent was written to localStorage ONLY on grant. A DECLINE set an in-memory
flag and stored nothing — so a narrator who said "no, I don't want the camera"
was asked again on the very next page load. And the next.

Observed live 2026-07-14: the consent card appeared, Chris declined, and
localStorage held no consent record at all afterwards.

For an older narrator, being repeatedly asked to switch on a camera they have
already refused is exactly the pressure this consent flow exists to prevent.
No means no, and it has to survive a reload.

Storage is now tri-state, so "declined" and "never asked" stop being the same
thing:
    'true'  -> granted   (auto-grant, do not re-ask)
    'false' -> DECLINED  (do not re-ask; only revokeStored() re-opens it)
    absent  -> never asked (ask once)

The legacy-migration guard is load-bearing: its old condition (`!_storedConsent`)
is ALSO true for a narrator who declined, so migrating on it would overwrite
their "no" with a legacy "yes" inherited from somebody else.

Runs the real ui/js/facial-consent.js under node against a localStorage shim.
"""
from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_HARNESS = _REPO_ROOT / "tests" / "js" / "facial_consent_decline.test.js"


class FacialConsentDeclineTest(unittest.TestCase):
    def test_decline_persists_and_survives_reload(self):
        node = shutil.which("node")
        if not node:
            raise unittest.SkipTest("node not available")
        out = subprocess.run(
            [node, str(_HARNESS)], cwd=str(_REPO_ROOT),
            capture_output=True, text=True, timeout=60)
        checks = [l for l in out.stdout.splitlines()
                  if l.startswith("  ok") or l.startswith("  FAIL")]
        failures = [l for l in checks if l.startswith("  FAIL")]
        self.assertTrue(checks, "harness produced no assertions:\n" + out.stdout)
        self.assertEqual(
            out.returncode, 0,
            "a narrator's refusal of the camera is not being respected:\n"
            + "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
