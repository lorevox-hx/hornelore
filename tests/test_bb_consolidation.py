"""Batch C-2b — Bio Builder consolidation and authority cleanup.

Drives tests/bb_consolidation_harness.js: the real #bioBuilderPopover markup
from ui/hornelore1.0.html and the shipped scripts in page order, clicked
through in jsdom against a fake server that records EVERY request.

What it pins (each check is named in the harness):
  * five areas only — Questionnaire, Sources & Notes, Review, Family, Legacy;
    Life Threads, Reset Identity and the shell's Operator Intake tab are gone;
  * the header names the narrator from the Life Record, with its revision,
    never an id;
  * opening every area and review section writes nothing;
  * Sources & Notes and Family say DRAFT, Legacy says READ ONLY and has no
    control that could change anything;
  * Family Tree add-and-save sends no request (it used to PUT the earlier
    questionnaire) and keeps its draft in the browser;
  * Review actions that wrote the earlier system are HELD — Lori's Accept is
    absent, Conflicts Replace and Source-claims Correct change nothing and
    stay open, WO-13 Promote refuses and its button is disabled — and they
    stay held when life-record-authority.js is missing (fail closed);
  * a narrator switch creates no earlier-questionnaire draft and no write;
  * the stale authority phrases are gone.

Mutation-checked 2026-09-24 (each broke exactly the check it should):
authority opened; Family Tree back on the old persist; navigation writing the
old draft; conflict guard removed; shadow-review guard removed; Accept button
restored.

Skips (and says so) without node or jsdom.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")
HAVE_JSDOM = bool(NODE) and subprocess.run(
    [NODE, "-e", "require('jsdom')"], cwd=REPO, capture_output=True).returncode == 0


@unittest.skipUnless(HAVE_JSDOM, "node + jsdom are required — npm install")
class BioBuilderConsolidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = subprocess.run([NODE, str(REPO / "tests" / "bb_consolidation_harness.js")],
                             cwd=REPO, capture_output=True, text=True, timeout=180)
        if out.returncode != 0:
            raise AssertionError(out.stderr[-2000:])
        cls.result = json.loads(out.stdout)

    def test_harness_completed(self):
        self.assertNotIn("error", self.result, self.result.get("error"))
        self.assertGreaterEqual(len(self.result["checks"]), 23)

    def test_every_check_passes(self):
        failed = [c for c in self.result["checks"] if not c["ok"]]
        self.assertEqual(failed, [], "\n".join(f"{c['name']}: {c['why']}" for c in failed))


if __name__ == "__main__":
    unittest.main()
