"""The Lori Configuration card, tested by RENDERING the shipped module.

WO-LORI-ARCHIVE-TO-MEMOIR-02 Block A.

`tests/test_operator_guard_lab_api.py` proves the server decides
eligibility from the durable people row and names the configuration.
That is one consumer short of the property the card exists for: whether
the OPERATOR sees that verdict, and — the part that matters — whether
the card ever computes one of its own.

Two of the checks in the Node harness are deliberately adversarial. One
feeds a payload where the narrator IS testing-only and IS in the
eligible list while the server says `can_receive_experiment: false`; a
card doing its own list lookup would contradict the server and go red.
The other labels a payload `Lean` while its rows show everything
running; a card computing the label from the rows would print
`Defaults`.

The payload is a real `GET /state` response, taken here and handed to
the harness. A hand-built one would supply the shape under test.
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ui" / "operator_guard_lab_card_domtest.js"
MODULE = ROOT / "ui" / "js" / "operator-guard-lab-card.js"

sys.path.insert(0, str(ROOT / "server" / "code"))

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    _READY, _WHY = True, ""
except Exception as exc:               # pragma: no cover - env dependent
    _READY, _WHY = False, str(exc)


class PresenceTests(unittest.TestCase):

    def test_the_module_and_harness_exist(self):
        self.assertTrue(MODULE.exists(), f"{MODULE} is missing")
        self.assertTrue(SCRIPT.exists(), f"{SCRIPT} is missing")

    def test_the_card_is_mounted_on_the_OPERATOR_tab(self):
        """Both halves, and the right tab.

        Without the script tag the module never runs; without the mount
        it runs and renders into nothing. And the card belongs beside
        the other session controls — an operator preparing a session is
        who needs it.
        """
        html = (ROOT / "ui" / "hornelore1.0.html").read_text(
            encoding="utf-8", errors="replace")
        self.assertIn('id="lvOperatorGuardLabCard"', html)
        self.assertIn("js/operator-guard-lab-card.js", html)
        self.assertIn("css/operator-guard-lab-card.css", html)

        # It must sit in the Operator tab's own section markup, not in
        # the Bug Panel and not in the narrator surface.
        mount_at = html.index('id="lvOperatorGuardLabCard"')
        panel_at = html.index('id="lv10dBugPanel"')
        self.assertLess(
            mount_at, panel_at,
            "the card must be in the Operator tab, above the Bug Panel "
            "markup — it is operator session chrome, not a diagnostic")

    def test_the_bug_panel_guard_lab_is_still_mounted(self):
        """The 43-row table was moved nowhere. It stays where it was."""
        html = (ROOT / "ui" / "hornelore1.0.html").read_text(
            encoding="utf-8", errors="replace")
        self.assertIn('id="lv10dBpGuardLab"', html)
        self.assertIn("js/bug-panel-guard-lab.js", html)


@unittest.skipUnless(_READY, f"fastapi unavailable: {_WHY}")
class CardRendersTheServerVerdictTests(unittest.TestCase):

    def _real_state_payload(self) -> dict:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        prev = {k: os.environ.get(k)
                for k in ("DATA_DIR", "DB_NAME", "HORNELORE_OPERATOR_GUARD_LAB")}

        def _restore():
            for key, value in prev.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            from api import db as _db
            importlib.reload(_db)
            from api.routers import operator_guard_lab as _r
            importlib.reload(_r)

        os.environ["DATA_DIR"] = tmp.name
        os.environ["DB_NAME"] = "test_guard_lab_card.sqlite3"
        os.environ["HORNELORE_OPERATOR_GUARD_LAB"] = "1"

        from api import db as _db
        importlib.reload(_db)
        _db.init_db()
        self.assertTrue(str(_db.DB_PATH).startswith(tmp.name),
                        f"refusing to run against {_db.DB_PATH}")
        from api.routers import operator_guard_lab as _router
        importlib.reload(_router)
        self.addCleanup(_restore)

        app = FastAPI()
        app.include_router(_router.router)
        resp = TestClient(app).get("/api/operator/guard-lab/state")
        self.assertEqual(200, resp.status_code, resp.text)
        return resp.json()

    def test_the_operator_sees_the_servers_verdict(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not on PATH — run scripts/ui/"
                          "operator_guard_lab_card_domtest.js where it is")
        payload = self._real_state_payload()

        # Guard the harness's own subject: these keys are what the card
        # renders, and their absence would let checks pass vacuously.
        for key in ("configuration", "current_narrator", "gate", "counts",
                    "revision", "authorities"):
            self.assertIn(key, payload)
        self.assertTrue(payload["authorities"])

        with tempfile.NamedTemporaryFile(
                "w", suffix=".json", delete=False, encoding="utf-8") as fh:
            json.dump(payload, fh)
            state_path = fh.name
        self.addCleanup(lambda: os.unlink(state_path))

        proc = subprocess.run([node, str(SCRIPT), state_path], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(0, proc.returncode,
                         "\n" + (proc.stdout or "") + (proc.stderr or ""))
        self.assertIn("checks passed", proc.stdout)


if __name__ == "__main__":
    unittest.main()
