"""Browser authority enforcement — runs the shipped-module Node test.

WO-LORI-ARCHIVE-TO-MEMOIR-02 Phase 3 (2026-09-04).

The behaviour lives in `scripts/ui/projection_authority_domtest.js`, which
loads the SHIPPED `ui/js/projection-sync.js` in a Node VM context with a
minimal window/state harness. This wrapper exists so the check runs with the
rest of the suite instead of depending on somebody remembering to invoke a
loose script.

WHY IT IS NOT A PLAYWRIGHT TEST. The Playwright DOM tests in this repo skip
wherever no browser binary is installed, and `OK (skipped=N)` has already been
mistaken for a pass in this lane. This one needs only Node, so it produces
evidence in the sandbox and in WSL alike.

THE GUARD WAS MUTATION-CHECKED, 2026-09-04. Three independent mutations of the
product each turned it red, and the tree was restored afterwards:

  * `_syncToBioBuilder` re-deriving the mode unconditionally  -> 3/16 failed
  * `interview.js` dropping `writeMode` from the call          -> 1/16 failed
  * the reduction permitting elevation                         -> 2/16 failed
"""
from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ui" / "projection_authority_domtest.js"


class ProjectionAuthorityTests(unittest.TestCase):

    def test_the_script_is_present(self):
        """Checked separately from execution: a missing file must fail, not
        skip. Only a missing INTERPRETER is a legitimate skip."""
        self.assertTrue(SCRIPT.exists(), f"{SCRIPT} is missing")

    def test_server_downgrade_binds_the_browser(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not on PATH — run scripts/ui/"
                          "projection_authority_domtest.js where it is")
        proc = subprocess.run([node, str(SCRIPT)], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(0, proc.returncode,
                         "\n" + (proc.stdout or "") + (proc.stderr or ""))
        self.assertIn("checks passed", proc.stdout)


if __name__ == "__main__":
    unittest.main()
