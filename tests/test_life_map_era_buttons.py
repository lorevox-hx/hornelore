"""Exactly seven era buttons, exactly one Today.

    PYTHONPATH=server/code python3 -m unittest tests.test_life_map_era_buttons

── THE DEFECT ────────────────────────────────────────────────────────

`_lvInterviewRenderLifeMap()` builds ordinary era buttons from the
hydrated `periods`, then ALWAYS appends a separate Today anchor. The
`defaultEraIds` branch filtered `today` out; the `periods` branch did
not. So any narrator whose spine contained a `today` period rendered
TWO controls carrying `data-era-id="today"`.

Two controls for one era is a product defect, not a selector problem:
`querySelector` and a plain Playwright locator both take the first, an
operator clicking the second addresses a different element than the
code does, and a seven-era walk cannot say which one the narrator used.

It blocked era 7 of run 20260831T152542Z after six eras had completed.
The harness was RIGHT to refuse, and must not be softened with
`.first()` or `.last()`.
"""
from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_APP = _REPO / "ui" / "js" / "app.js"

#: The canonical spine, hydrated — INCLUDING today, which is the case
#: that used to duplicate.
_HYDRATED_WITH_TODAY = [
    "earliest_years", "early_school_years", "adolescence",
    "coming_of_age", "building_years", "later_years", "today",
]

_SELECTION_JS = """
const _toEraId = v => v;
function eraIdsFor(periods, defaults) {
  const seen = new Set();
  return (periods.length
      ? periods.map(p => _toEraId(p.era_id || p.label)).filter(Boolean)
      : defaults)
    .filter(eid => eid !== "today")
    .filter(eid => { if (seen.has(eid)) return false; seen.add(eid); return true; });
}
const defaults = ["earliest_years","early_school_years","adolescence",
                  "coming_of_age","building_years","later_years"];
const periods = %s.map(id => ({era_id: id}));
const ids = eraIdsFor(periods, defaults);
console.log(JSON.stringify({
  ordinary: ids,
  ordinaryCount: ids.length,
  todayInOrdinary: ids.includes("today"),
  totalButtons: ids.length + 1,      // + the dedicated Today anchor
  unique: new Set(ids).size === ids.length,
}));
"""


def _run(period_ids):
    import json
    out = subprocess.run(
        ["node", "-e", _SELECTION_JS % json.dumps(period_ids)],
        capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise AssertionError(out.stderr)
    return json.loads(out.stdout)


class HydratedSpineIncludingTodayTests(unittest.TestCase):
    """The exact case that broke: `today` already in the spine."""

    def setUp(self):
        self.r = _run(_HYDRATED_WITH_TODAY)

    def test_exactly_seven_era_buttons_total(self):
        self.assertEqual(7, self.r["totalButtons"])

    def test_exactly_one_today_button(self):
        # today never comes from the ordinary loop, so the dedicated
        # anchor is the ONLY one.
        self.assertFalse(self.r["todayInOrdinary"])
        self.assertEqual(6, self.r["ordinaryCount"])

    def test_the_six_historical_eras_all_render(self):
        self.assertEqual(
            ["earliest_years", "early_school_years", "adolescence",
             "coming_of_age", "building_years", "later_years"],
            self.r["ordinary"])


class DeduplicationTests(unittest.TestCase):
    def test_a_repeated_era_renders_once(self):
        r = _run(_HYDRATED_WITH_TODAY + ["adolescence", "today", "today"])
        self.assertEqual(7, r["totalButtons"])
        self.assertTrue(r["unique"])
        self.assertFalse(r["todayInOrdinary"])

    def test_a_spine_that_is_only_today_still_renders_one_today(self):
        r = _run(["today"])
        self.assertEqual(0, r["ordinaryCount"])
        self.assertEqual(1, r["totalButtons"])


class FreshNarratorTests(unittest.TestCase):
    def test_an_empty_spine_falls_back_to_six_plus_today(self):
        r = _run([])
        self.assertEqual(7, r["totalButtons"])
        self.assertFalse(r["todayInOrdinary"])


class SourceGuardTests(unittest.TestCase):
    def setUp(self):
        self.src = _APP.read_text(encoding="utf-8", errors="replace")

    def test_both_branches_filter_today(self):
        """The defect was that only ONE branch filtered."""
        self.assertIn('.filter(eid => eid !== "today")', self.src)
        self.assertIn('.filter(e => e.era_id !== "today")', self.src)

    def test_the_ordinary_list_is_deduplicated(self):
        self.assertIn("_seenEra", self.src)

    def test_one_dedicated_today_anchor_remains(self):
        self.assertEqual(
            1, self.src.count("_lvInterviewConfirmEra('today')"),
            "the dedicated Today anchor must remain, and exactly once")


class HarnessMustNotBeSoftenedTests(unittest.TestCase):
    """A duplicate control is a product defect, not a selector problem."""

    def test_the_harness_still_demands_exactly_one(self):
        js = (_REPO / "scripts" / "ui"
              / "run_walt_seven_era_conversation.js").read_text(
                  encoding="utf-8")
        self.assertIn("expected one Life Map button for", js)
        code = re.sub(r"(?m)^\s*//[^\n]*", "",
                      re.sub(r"/\*.*?\*/", "", js, flags=re.S))
        for weakener in (".first()", ".last()", ".nth(0)"):
            self.assertNotIn(
                f'lv-interview-lifemap-era-btn"]{weakener}', code)


if __name__ == "__main__":      # pragma: no cover
    unittest.main()
