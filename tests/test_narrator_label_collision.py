"""BUG-NARRATOR-LABEL-COLLISION-01 — two narrators must never look alike.

LIVE (2026-07-14): the DB held two distinct people —
  e7fdb578 display_name="Christopher"
  a4b2f07a display_name="Christopher Todd Horne"
— and _horneloreNormalizeVisibleName() canonicalized BOTH onto the same warm
family label, so the narrator picker showed "Christopher Todd Horne" TWICE.

In a system whose entire job is attributing a life story to the right person,
two narrators that look identical in the picker is how a memory gets written
into the wrong person's history.

The first fix attempted a birth-year suffix — and the live data defeated it:
both Christophers share DOB 1962. A disambiguator that does not disambiguate
is worse than none, because it LOOKS resolved. Hence the id fallback, which is
unique by definition.

REWRITTEN for Phase 7 (WO-LOREVOX-CLEAN-DATA-WORLD-01), and the reason matters
more than the rewrite. The canonicalizer is GONE: it was part of the Horne
family lock, and a narrator's own name is not a spelling mistake to be
corrected. That removes the way this collision was MANUFACTURED — but not the
collision. Two narrators may simply share a display name, and sequential
package restore into one Lorevox root makes that likelier, not rarer: a root
holding one "Mary" can be restored into from a package holding another.

So the fixtures below now carry GENUINE collisions (same display_name, no
canonicalizer involved) rather than Horne aliases, and
`test_the_family_canonicalizer_is_gone` fails if anyone reintroduces the
name-rewriting that caused the original bug — the same shape as
tests/test_kawa_product_path_removed.py.

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
    payload = json.loads(out.stdout.strip())
    if isinstance(payload, dict) and payload.get("error"):
        raise AssertionError(
            "harness could not locate the disambiguator in hornelore1.0.html: "
            + payload["error"])
    return payload


class NarratorLabelCollisionTest(unittest.TestCase):
    # A genuine collision: two distinct people, one display name, no alias
    # table and no canonicalizer in sight. This is the shape that survives the
    # family-lock removal, and the shape sequential restore can produce.
    COLLIDING = [
        {"id": "e7fdb578-1111", "display_name": "Christopher Todd Horne",
         "date_of_birth": "1962-12-24"},
        {"id": "a4b2f07a-2222", "display_name": "Christopher Todd Horne",
         "date_of_birth": "1962-12-24"},
        {"id": "d56900b5-3333", "display_name": "Melanie Zollner",
         "date_of_birth": "1972-12-20"},
    ]

    def test_colliding_narrators_are_distinguishable(self):
        labels = _labels(self.COLLIDING)
        self.assertEqual(len(set(labels)), len(labels),
                         "two narrators render with the SAME label — an "
                         "operator cannot tell whose story they are recording")

    def test_shared_dob_does_not_defeat_disambiguation(self):
        # Both Christophers were born in 1962. The birth-year suffix collides,
        # so it must fall through to the id.
        labels = [x for x in _labels(self.COLLIDING)
                  if x.startswith("Christopher")]
        self.assertEqual(len(labels), 2)
        self.assertTrue(all("#" in x for x in labels), labels)

    def test_distinct_dobs_prefer_the_human_suffix(self):
        # An id is the fallback, not the default — prefer something a person
        # can actually read.
        labels = _labels([
            {"id": "aaaa1111", "display_name": "Kent James Horne",
             "date_of_birth": "1938-01-05"},
            {"id": "bbbb2222", "display_name": "Kent James Horne",
             "date_of_birth": "1911-03-02"},
        ])
        self.assertEqual(len(set(labels)), 2)
        self.assertTrue(all("b. " in x for x in labels), labels)

    def test_uncontested_names_are_left_alone(self):
        labels = _labels(self.COLLIDING)
        self.assertIn("Melanie Zollner", labels)

    def test_the_family_canonicalizer_is_gone(self):
        # Phase 7 regression gate. Each of these names was rewritten onto a
        # Horne family label by _horneloreNormalizeVisibleName(), which is what
        # collapsed two real people onto one label in the live bug above. A
        # narrator is shown the name their record carries.
        for raw in ("chris", "Christopher", "kent", "Janice", "janice horne"):
            with self.subTest(display_name=raw):
                self.assertEqual(
                    _labels([{"id": "x", "display_name": raw,
                              "date_of_birth": "1962-12-24"}]),
                    [raw],
                    "the Horne name canonicalizer has returned — it rewrites a "
                    "narrator's own name and manufactures label collisions")

    def test_missing_dob_still_disambiguates(self):
        labels = _labels([{"id": "c1", "display_name": "Janice Horne"},
                          {"id": "c2", "display_name": "Janice Horne"}])
        self.assertEqual(len(set(labels)), 2, labels)

    def test_blank_named_narrator_is_still_identifiable(self):
        # A restored or half-created narrator can carry no display name at all.
        # Two of them must not both render as a bare "Unknown".
        labels = _labels([{"id": "n1", "display_name": ""},
                          {"id": "n2"}])
        self.assertEqual(len(set(labels)), 2, labels)


if __name__ == "__main__":
    unittest.main()
