"""The Guard Lab panel, tested by RENDERING the shipped module.

WO-LORI-BASELINE-RESET-AND-GUARD-LAB-01 Continuation A, section R.

`tests/test_operator_guard_lab_api.py` proves the SERVER tells the truth
about 43 authorities. That is one consumer short of the property that
matters, which is whether the operator sees it — and this repository has
paid for that gap twice already. `lvStoryReviewRenderExtraction` had to
be exported because a source-string assertion could not tell whether the
values reached the screen, and `disabled: undefined` left every review
button permanently dead while the buttons, their labels and their
handlers all read correctly in the source. Only pressing one revealed it.

So the behaviour lives in `scripts/ui/guard_lab_panel_domtest.js`, which
loads the SHIPPED `ui/js/bug-panel-guard-lab.js` in a Node VM with a
small real DOM, renders it, and clicks its buttons.

THE PAYLOAD IS NOT A FIXTURE. This wrapper calls the real route first
and hands the Node harness that response. A hand-built payload would
supply the very shape under test, and the two halves could then agree
with each other while disagreeing with the product.

WHY NODE AND NOT PLAYWRIGHT. The Playwright DOM tests here skip wherever
no browser binary is installed, and `OK (skipped=N)` has already been
mistaken for a pass in this lane.
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
SCRIPT = ROOT / "scripts" / "ui" / "guard_lab_panel_domtest.js"
MODULE = ROOT / "ui" / "js" / "bug-panel-guard-lab.js"

sys.path.insert(0, str(ROOT / "server" / "code"))

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    _READY, _WHY = True, ""
except Exception as exc:               # pragma: no cover - env dependent
    _READY, _WHY = False, str(exc)


class PresenceTests(unittest.TestCase):
    """Checked separately from execution: a missing file must FAIL.

    Only a missing interpreter is a legitimate skip. A guard whose
    subject has been deleted should go red, not quiet.
    """

    def test_the_shipped_module_and_its_harness_exist(self):
        self.assertTrue(MODULE.exists(), f"{MODULE} is missing")
        self.assertTrue(SCRIPT.exists(), f"{SCRIPT} is missing")

    def test_the_module_is_mounted_in_the_shipped_ui(self):
        """A panel nobody loads is not a panel.

        Both halves are required and they fail differently: without the
        script tag the module never runs, and without the mount div it
        runs and renders into nothing.
        """
        html = (ROOT / "ui" / "hornelore1.0.html").read_text(
            encoding="utf-8", errors="replace")
        self.assertIn('id="lv10dBpGuardLab"', html)
        self.assertIn("js/bug-panel-guard-lab.js", html)


@unittest.skipUnless(_READY, f"fastapi unavailable: {_WHY}")
class PanelRendersTheServerTruthTests(unittest.TestCase):

    def _real_state_payload(self) -> dict:
        """A live response from the real route, in a temp database."""
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
        os.environ["DB_NAME"] = "test_guard_lab_panel.sqlite3"
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
        client = TestClient(app)
        resp = client.get("/api/operator/guard-lab/state")
        self.assertEqual(200, resp.status_code, resp.text)
        return resp.json()

    def test_the_operator_sees_what_the_server_resolved(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not on PATH — run scripts/ui/"
                          "guard_lab_panel_domtest.js where it is")
        payload = self._real_state_payload()

        # Guard the harness's own subject. If the response ever stopped
        # carrying protected rows or switchable rows, the checks below
        # would pass vacuously against an empty list.
        self.assertTrue([a for a in payload["authorities"] if a["switchable"]])
        self.assertTrue([a for a in payload["authorities"] if not a["switchable"]])

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
