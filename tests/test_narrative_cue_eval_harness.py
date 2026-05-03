"""WO-NARRATIVE-CUE-LIBRARY-01 Phase 3 — smoke tests for the eval harness.

Two layers:
  1. Determinism / stability — running the same library twice produces
     byte-identical case records.
  2. Diff structure — running baseline vs candidate produces a diff with
     all required keys, and newly_failed / newly_passed bookkeeping is
     internally consistent.

These are smoke tests, not exhaustive coverage. The harness itself is
data-shaping code; the load-bearing logic is in
narrative_cue_detector.py (which has its own 19-test suite).
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = _REPO_ROOT / "scripts"
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# Import the harness as a module (it's a CLI but the helpers are importable).
import importlib.util
_HARNESS_PATH = _SCRIPTS / "run_narrative_cue_eval.py"
_spec = importlib.util.spec_from_file_location("run_narrative_cue_eval", _HARNESS_PATH)
_harness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_harness)  # type: ignore[union-attr]

from api.services.narrative_cue_detector import build_library_from_path  # noqa: E402

_DEFAULT_LIB = _REPO_ROOT / "data" / "lori" / "narrative_cue_library.v1.seed.json"
_CANDIDATE_LIB = _REPO_ROOT / "data" / "lori" / "narrative_cue_library.candidate_class_a_v1.json"
_EVAL_PACK = _REPO_ROOT / "data" / "qa" / "lori_narrative_cue_eval.json"


def _load_cases():
    with _EVAL_PACK.open(encoding="utf-8") as f:
        pack = json.load(f)
    return pack["cases"]


class HarnessStabilityTest(unittest.TestCase):
    """The detector is documented as deterministic. The harness must
    not break that contract — running the same library twice must
    produce byte-identical case records."""

    def test_two_runs_byte_stable(self):
        cases = _load_cases()
        lib = build_library_from_path(str(_DEFAULT_LIB))
        a = _harness._run_one(lib, str(_DEFAULT_LIB), cases, config_name="x")
        b = _harness._run_one(lib, str(_DEFAULT_LIB), cases, config_name="x")
        # config_name is intentionally identical here; records must match exactly
        self.assertEqual(
            json.dumps(a["records"], sort_keys=True),
            json.dumps(b["records"], sort_keys=True),
        )
        self.assertEqual(a["summary"], b["summary"])

    def test_stability_check_helper(self):
        cases = _load_cases()
        ok, msg = _harness._stability_check(str(_DEFAULT_LIB), cases)
        self.assertTrue(ok, msg)


class HarnessBaselineReportTest(unittest.TestCase):
    """The single-config report has all required fields and matches the
    detector's known 30/40 = 75% baseline."""

    def test_baseline_report_shape(self):
        cases = _load_cases()
        lib = build_library_from_path(str(_DEFAULT_LIB))
        report = _harness._run_one(lib, str(_DEFAULT_LIB), cases, config_name="baseline")
        for key in ("config_name", "library_path", "library_version",
                    "cue_type_count", "summary", "per_cue_type",
                    "miss_class_distribution", "records"):
            self.assertIn(key, report)
        self.assertGreaterEqual(report["cue_type_count"], 12)
        self.assertEqual(report["summary"]["total"], 40)
        # Detector calibration locked at 30 hits in PHASE2_CALIBRATION.md
        self.assertEqual(report["summary"]["hits"], 30)
        self.assertEqual(report["summary"]["pass_rate_pct"], 75.0)

    def test_records_have_miss_class_field(self):
        cases = _load_cases()
        lib = build_library_from_path(str(_DEFAULT_LIB))
        report = _harness._run_one(lib, str(_DEFAULT_LIB), cases, config_name="x")
        for r in report["records"]:
            self.assertIn(r["miss_class"], {"none", "class_a", "class_b", "class_c"})
            if r["ok"]:
                self.assertEqual(r["miss_class"], "none")
            else:
                self.assertNotEqual(r["miss_class"], "none")


class HarnessDiffTest(unittest.TestCase):
    """Baseline vs candidate diff has all required structure, and
    newly_passed + newly_failed counts reconcile with hit deltas."""

    def setUp(self):
        if not _CANDIDATE_LIB.is_file():
            self.skipTest(f"candidate library missing at {_CANDIDATE_LIB}")
        cases = _load_cases()
        self.base_lib = build_library_from_path(str(_DEFAULT_LIB))
        self.cand_lib = build_library_from_path(str(_CANDIDATE_LIB))
        self.baseline = _harness._run_one(self.base_lib, str(_DEFAULT_LIB), cases, "baseline")
        self.candidate = _harness._run_one(self.cand_lib, str(_CANDIDATE_LIB), cases, "candidate_class_a_v1")
        self.diff = _harness._build_diff(self.baseline, self.candidate)

    def test_diff_has_required_keys(self):
        for key in ("baseline", "candidate", "delta_pct", "newly_passed",
                    "newly_failed", "score_only_changes",
                    "per_cue_type_delta", "miss_class_delta", "verdict"):
            self.assertIn(key, self.diff)

    def test_hits_reconcile_with_diff(self):
        """candidate.hits should equal baseline.hits + len(newly_passed)
        - len(newly_failed)."""
        b_hits = self.baseline["summary"]["hits"]
        c_hits = self.candidate["summary"]["hits"]
        self.assertEqual(
            c_hits,
            b_hits + len(self.diff["newly_passed"]) - len(self.diff["newly_failed"]),
            "candidate hits don't reconcile with baseline + newly_passed - newly_failed",
        )

    def test_class_a_candidate_helps_class_a_misses(self):
        """The candidate was authored to expand triggers for the 3 Class A
        'no trigger fired' misses. At minimum, class_a misses should be
        reduced (delta <= 0)."""
        miss_delta = self.diff["miss_class_delta"]
        if "class_a" in miss_delta:
            self.assertLessEqual(
                miss_delta["class_a"]["delta"],
                0,
                f"Class A candidate should reduce Class A misses, got delta="
                f"{miss_delta['class_a']['delta']}",
            )

    def test_verdict_is_one_of_known_states(self):
        self.assertIn(
            self.diff["verdict"][:5],  # first 5 chars match GREEN or AMBER
            ("GREEN", "AMBER"),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
