"""BUG-NARRATOR-LABEL-COLLISION-01 — two narrators must never look alike.

LIVE (2026-07-14): the DB held two distinct people —
  e7fdb578 display_name="Christopher"
  a4b2f07a display_name="Christopher Todd Horne"
— and _horneloreNormalizeVisibleName() canonicalizes BOTH to the same warm
family label, so the narrator picker showed "Christopher Todd Horne" TWICE.

In a system whose entire job is attributing a life story to the right person,
two narrators that look identical in the picker is how a memory gets written
into the wrong person's history. The canonicalizer is still right to be warm;
it just may never collapse two identities into one label.

The first fix attempted a birth-year suffix — and the live data defeated it:
both Christophers share DOB 1962. A disambiguator that does not disambiguate
is worse than none, because it LOOKS resolved. Hence the id fallback, which is
unique by definition.

Runs the real function out of hornelore1.0.html under node.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_HTML = _REPO_ROOT / "ui" / "hornelore1.0.html"

_HARNESS = r"""
const fs = require('fs');
const s = fs.readFileSync(process.argv[1], 'utf8');
const i = s.indexOf('function _horneloreDisambiguateLabels');
const j = s.indexOf('function _horneloreFilterVisiblePeople');
if (i < 0 || j < 0) { console.log(JSON.stringify({error: 'fn not found'})); process.exit(0); }
eval(s.slice(i, j));
const people = JSON.parse(process.argv[2]);
const m = _horneloreDisambiguateLabels(people);
console.log(JSON.stringify([...m.values()]));
"""


def _labels(people):
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node not available")
    out = subprocess.run(
        [node, "-e", _HARNESS, str(_HTML), json.dumps(people)],
        capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise AssertionError(out.stderr[:400])
    return json.loads(out.stdout.strip())


class NarratorLabelCollisionTest(unittest.TestCase):
    LIVE = [
        {"id": "e7fdb578-1111", "display_name": "Christopher",
         "date_of_birth": "1962-12-24"},
        {"id": "a4b2f07a-2222", "display_name": "Christopher Todd Horne",
         "date_of_birth": "1962-12-24"},
        {"id": "d56900b5-3333", "display_name": "Melanie Zollner",
         "date_of_birth": "1972-12-20"},
        {"id": "93479171-4444", "display_name": "Janice",
         "date_of_birth": "1940-02-29"},
        {"id": "4aa0cc2b-5555", "display_name": "Kent",
         "date_of_birth": "1938-01-05"},
    ]

    def test_the_live_two_christophers_are_distinguishable(self):
        labels = _labels(self.LIVE)
        self.assertEqual(len(set(labels)), len(labels),
                         "two narrators render with the SAME label — an "
                         "operator cannot tell whose story they are recording")

    def test_shared_dob_does_not_defeat_disambiguation(self):
        # Both Christophers were born in 1962. The birth-year suffix collides,
        # so it must fall through to the id.
        labels = [x for x in _labels(self.LIVE) if x.startswith("Christopher")]
        self.assertEqual(len(labels), 2)
        self.assertTrue(all("#" in x for x in labels), labels)

    def test_distinct_dobs_prefer_the_human_suffix(self):
        # An id is the fallback, not the default — prefer something a person
        # can actually read.
        labels = _labels([
            {"id": "aaaa1111", "display_name": "Kent",
             "date_of_birth": "1938-01-05"},
            {"id": "bbbb2222", "display_name": "Kent James Horne",
             "date_of_birth": "1911-03-02"},
        ])
        self.assertEqual(len(set(labels)), 2)
        self.assertTrue(all("b. " in x for x in labels), labels)

    def test_uncontested_names_stay_warm(self):
        labels = _labels(self.LIVE)
        self.assertIn("Melanie Zollner", labels)
        self.assertIn("Kent James Horne", labels)     # still canonicalized
        self.assertIn("Janice Josephine (Zarr) Horne", labels)

    def test_single_narrator_keeps_the_family_name(self):
        self.assertEqual(
            _labels([{"id": "x", "display_name": "chris",
                      "date_of_birth": "1962-12-24"}]),
            ["Christopher Todd Horne"])

    def test_missing_dob_still_disambiguates(self):
        labels = _labels([{"id": "c1", "display_name": "Janice"},
                          {"id": "c2", "display_name": "janice horne"}])
        self.assertEqual(len(set(labels)), 2, labels)


if __name__ == "__main__":
    unittest.main()
