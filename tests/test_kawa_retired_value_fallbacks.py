"""Retired Kawa state normalizes — seeded with the retired values, not defaults.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python -m unittest \
      tests.test_kawa_retired_value_fallbacks

WO-KAWA-REMOVAL-01, compatibility half.

WHY THIS TEST SEEDS RETIRED VALUES INSTEAD OF READING DEFAULTS.

Checking that `narratorView` now defaults to `"map"` proves almost
nothing: the narrators at risk are the ones whose PERSISTED session
already says `"river"`, and a default cannot reach them. So every case
here starts from a retired value and asserts where it lands.

THE FAILURE BEING PREVENTED IS SILENT. Before this change
`lvNarratorShowView` opened with:

    if (!["map", "photos", "memoir", "trips"].includes(view)) return;

A bare `return` — no throw, no fallback, nothing painted. The sole
caller reads `lvNarratorCurrentView() || "map"`, and that `||` does not
help, because `"river"` is TRUTHY: it survives the coalesce, fails the
membership test, and the function returns having rendered nothing. The
narrator gets an empty room and no error anywhere.

THREE FIELDS, THREE VOCABULARIES — and they must not be crossed:

    narratorView   river                             -> map
    kawaMode       hybrid, kawa_reflection           -> chronological
    memoirMode     chronology_river, river_organized -> chronology

`hybrid` is the one that hides. It reads like a neutral interview
setting and is not: `lori-kawa.js` paired it with `kawa_reflection`,
triggered Kawa follow-ups on it, and counted `hybridPromptsShown`. A
narrator left on `hybrid` would have kept receiving Kawa prompts after a
removal that looked complete. An earlier draft of the work order filed
`kawa_reflection` under memoir modes and omitted `hybrid` entirely; this
test exists partly so that class of mistake fails loudly.

The normalizers are read out of the SHIPPED `ui/js/state.js` through
Node rather than reimplemented here — a fixture may supply values, but
it may not supply the property being proven.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_JS = REPO_ROOT / "ui" / "js" / "state.js"

#: (field, seeded value, expected result). Every input is a value a real
#: persisted session could carry.
CASES = [
    # narrator view — the silent-blank-room case
    ("narratorView", "river", "map"),
    ("narratorView", "map", "map"),
    ("narratorView", "photos", "photos"),
    ("narratorView", "memoir", "memoir"),
    ("narratorView", "trips", "trips"),
    ("narratorView", "", "map"),
    ("narratorView", None, "map"),
    ("narratorView", "some_future_typo", "map"),
    # interview mode — `hybrid` is Kawa-specific and easy to miss
    ("kawaMode", "hybrid", "chronological"),
    ("kawaMode", "kawa_reflection", "chronological"),
    ("kawaMode", "chronological", "chronological"),
    ("kawaMode", None, "chronological"),
    # memoir mode
    ("memoirMode", "chronology_river", "chronology"),
    ("memoirMode", "river_organized", "chronology"),
    ("memoirMode", "chronology", "chronology"),
    ("memoirMode", "", "chronology"),
]

FIELD_FN = {
    "narratorView": "lvNormalizeNarratorView",
    "kawaMode": "lvNormalizeInterviewMode",
    "memoirMode": "lvNormalizeMemoirMode",
}

_PROBE = """
const fs = require("fs"), vm = require("vm");
const src = fs.readFileSync(process.argv[1], "utf8");
const ctx = { console, window: {} };
vm.createContext(ctx);
vm.runInContext(src, ctx);
const cases = JSON.parse(process.argv[2]);
const out = cases.map(([field, fn, value]) => {
  const f = ctx[fn];
  if (typeof f !== "function") return { field, value, error: "missing " + fn };
  return { field, value, got: f(value) };
});
process.stdout.write(JSON.stringify(out));
"""


def _node() -> str:
    exe = shutil.which("node")
    if not exe:
        raise unittest.SkipTest("node is not on PATH")
    return exe


class RetiredKawaValuesNormalize(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        node = _node()
        payload = json.dumps(
            [[f, FIELD_FN[f], v] for f, v, _ in CASES])
        proc = subprocess.run(
            [node, "-e", _PROBE, str(STATE_JS), payload],
            capture_output=True, text=True)
        if proc.returncode != 0:
            raise AssertionError(
                "could not evaluate the shipped ui/js/state.js:\n"
                + proc.stderr[-2000:])
        cls.results = json.loads(proc.stdout)

    def test_every_retired_value_normalizes_to_its_own_field_default(self):
        for (field, seeded, expected), got in zip(CASES, self.results):
            with self.subTest(field=field, seeded=seeded):
                self.assertNotIn("error", got, got.get("error"))
                self.assertEqual(
                    got["got"], expected,
                    f"{field}={seeded!r} normalized to {got['got']!r}, "
                    f"expected {expected!r}")

    def test_the_three_vocabularies_do_not_overlap(self):
        """A fallback must never map a value onto the wrong field.

        The work order's first draft put `kawa_reflection` under memoir
        modes. If the vocabularies shared values that error would have
        been invisible; they do not, so it is checkable.
        """
        node = _node()
        proc = subprocess.run(
            [node, "-e",
             'const fs=require("fs"),vm=require("vm");'
             'const ctx={console,window:{}};vm.createContext(ctx);'
             'vm.runInContext(fs.readFileSync(process.argv[1],"utf8"),ctx);'
             'process.stdout.write(JSON.stringify({'
             'views:ctx.window.LV_NARRATOR_VIEWS,'
             'interview:ctx.window.LV_INTERVIEW_MODES,'
             'memoir:ctx.window.LV_MEMOIR_MODES}));',
             str(STATE_JS)],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
        v = json.loads(proc.stdout)
        # `const` at module scope does NOT become a property of the vm
        # context object — only function declarations do. The vocabularies
        # are reachable through the window export, which is also how the
        # browser sees them.
        views, interview, memoir = (set(v["views"]), set(v["interview"]),
                                    set(v["memoir"]))
        self.assertTrue(views and interview and memoir,
                        "a vocabulary is empty; the test would pass vacuously")
        self.assertEqual(views & interview, set())
        self.assertEqual(views & memoir, set())
        self.assertEqual(interview & memoir, set())

    def test_no_retired_value_survives_as_accepted(self):
        """The retired names must not be in any accepted vocabulary."""
        node = _node()
        proc = subprocess.run(
            [node, "-e",
             'const fs=require("fs"),vm=require("vm");'
             'const ctx={console,window:{}};vm.createContext(ctx);'
             'vm.runInContext(fs.readFileSync(process.argv[1],"utf8"),ctx);'
             'process.stdout.write(JSON.stringify([].concat('
             'ctx.window.LV_NARRATOR_VIEWS,ctx.window.LV_INTERVIEW_MODES,'
             'ctx.window.LV_MEMOIR_MODES)));',
             str(STATE_JS)],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
        accepted = set(json.loads(proc.stdout))
        retired = {"river", "hybrid", "kawa_reflection",
                   "chronology_river", "river_organized"}
        self.assertEqual(
            accepted & retired, set(),
            "a retired Kawa value is still an ACCEPTED state value, so it "
            "would pass normalization untouched")

    def test_the_default_narrator_view_is_no_longer_river(self):
        """The other half — necessary, and on its own insufficient."""
        src = STATE_JS.read_text(encoding="utf-8")
        self.assertIn('narratorView: "map"', src)
        self.assertNotIn('narratorView: "river"', src)


if __name__ == "__main__":
    unittest.main()
