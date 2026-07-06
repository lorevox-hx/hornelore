"""WO-LIFEMAP-TRAVELS-SHELF-AND-NARRATION-01 — shelf isolation gate.

HARD RULE from the approved spec (§3.1 + stop conditions): Travels is
a SHELF, never an era. These tests FAIL THE BUILD if "travels" ever
enters the canonical era registry (py or js side), if era age
derivation changes shape, or if the shelf markup migrates into the
era-button class (which would let era consumers pick it up).

Also guards the directive discipline (§3.4): no calendar-date-recall
phrasing in any travels-shelf Lori directive.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api import lv_eras  # noqa: E402

_CANONICAL_ERA_IDS = [
    "earliest_years", "early_school_years", "adolescence",
    "coming_of_age", "building_years", "later_years", "today",
]


class EraRegistryIsolationTest(unittest.TestCase):
    def test_python_registry_has_exactly_seven_eras_no_travels(self):
        ids = [e["era_id"] for e in lv_eras.LV_ERAS]
        self.assertEqual(ids, _CANONICAL_ERA_IDS)
        self.assertNotIn("travels", ids)
        self.assertNotIn("travelogues", ids)

    def test_era_id_from_age_never_returns_travels(self):
        for age in (0, 4, 9, 15, 21, 40, 70, 90, 105):
            self.assertIn(lv_eras.era_id_from_age(age), _CANONICAL_ERA_IDS)

    def test_js_registry_has_no_travels_era(self):
        js = (_REPO_ROOT / "ui" / "js" / "lv-eras.js").read_text(encoding="utf-8")
        # Any era_id-shaped mention of travels in the JS registry fails.
        self.assertNotRegex(js, re.compile(r"era_id[\"']?\s*[:=]\s*[\"']travel",
                                           re.IGNORECASE))

    def test_shelf_button_is_not_an_era_button(self):
        app = (_REPO_ROOT / "ui" / "js" / "app.js").read_text(encoding="utf-8")
        m = re.search(
            r"lv-interview-lifemap-travels-btn.*?</button>", app, re.DOTALL)
        self.assertIsNotNone(m, "Travels shelf button missing from Life Map render")
        block = m.group(0)
        # Must NOT carry the era button class or a data-era-id attribute —
        # both would let era consumers (harnesses, selectors) pick it up.
        self.assertNotIn("lv-interview-lifemap-era-btn", block)
        self.assertNotIn("data-era-id", block)

    def test_memoir_section_builder_untouched_by_travels(self):
        html = (_REPO_ROOT / "ui" / "hornelore1.0.html").read_text(encoding="utf-8")
        m = re.search(r"function lv80BuildMemoirSections[\s\S]{0,4000}?\n\}", html)
        if m:  # builder present — must not consume travels as a section era
            self.assertNotIn("travels", m.group(0).lower())


class DirectiveDisciplineTest(unittest.TestCase):
    """§3.4: Lori never asks the narrator to recall calendar dates.
    String-level gate on every directive in travels-shelf.js."""

    _BANNED = [
        r"what\s+date", r"what\s+day\b", r"what\s+year",
        r"when\s+exactly", r"when\s+did\s+you\s+leave",
        r"which\s+year", r"what\s+month",
    ]

    def test_no_calendar_date_recall_in_directives(self):
        js = (_REPO_ROOT / "ui" / "js" / "travels-shelf.js").read_text(encoding="utf-8")
        directives = re.findall(r"\[SYSTEM:.*?\]", js, re.DOTALL)
        self.assertGreaterEqual(len(directives), 3)  # zero-trip, open, photo
        for d in directives:
            for pat in self._BANNED:
                self.assertNotRegex(d, re.compile(pat, re.IGNORECASE),
                                    f"banned date-recall phrasing in: {d[:80]}")

    def test_every_directive_carries_the_date_ban(self):
        js = (_REPO_ROOT / "ui" / "js" / "travels-shelf.js").read_text(encoding="utf-8")
        directives = re.findall(r"\[SYSTEM:.*?\]", js, re.DOTALL)
        for d in directives:
            self.assertIn("calendar dates", d,
                          "directive missing the explicit date-recall ban")

    def test_panel_never_renders_operator_vocabulary(self):
        # §3.6 REV 2: narrator panel shows human labels only. Gate the
        # renderer source for operator vocabulary in any string that
        # could reach the DOM.
        js = (_REPO_ROOT / "ui" / "js" / "travels-shelf.js").read_text(encoding="utf-8")
        for term in ("cluster_confidence", "assignment_method",
                     "metadata_trust", "needs_review", "review queue"):
            # Terms may appear in comments; strip comments first.
            stripped = re.sub(r"/\*[\s\S]*?\*/|//[^\n]*", "", js)
            self.assertNotIn(term, stripped,
                             f"operator vocabulary '{term}' in panel code")


if __name__ == "__main__":
    unittest.main()
