"""Offline contract tests for the four-persona product harness."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.harness.extraction_scoring import score_case, summarize

PERSONAS = ROOT / "data" / "qa" / "narrator_product_personas_v1.json"
CORE = ROOT / "data" / "qa" / "extraction_core_v1.json"
CHALLENGE = ROOT / "data" / "qa" / "extraction_challenge_v1.json"
RUNNER = ROOT / "scripts" / "run_narrator_product_harness.py"
OLD_RUNNER = ROOT / "scripts" / "archive" / "run_question_bank_extraction_eval.py"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class PersonaManifestTest(unittest.TestCase):
    def test_locked_four_persona_capability_split(self):
        rows = {row["key"]: row for row in _load(PERSONAS)["personas"]}
        self.assertEqual(set(rows), {"shatner", "dolly", "tomasita", "alex"})
        for key in ("shatner", "dolly"):
            self.assertEqual(rows[key]["kind"], "reference")
            self.assertIn("product_mutation", rows[key]["forbidden_capabilities"])
            self.assertNotIn("intake", rows[key])
        for key in ("tomasita", "alex"):
            self.assertEqual(rows[key]["kind"], "synthetic_writable")
            self.assertIs(rows[key]["intake"]["testing_only"], True)
            self.assertFalse(rows[key]["intake"]["consent_recording_agreement"])

    def test_manifest_and_public_case_packs_contain_no_family_identifiers(self):
        text = "\n".join(
            path.read_text(encoding="utf-8") for path in (PERSONAS, CORE, CHALLENGE)
        ).casefold()
        forbidden = (
            "christopher todd horne",
            "kent james horne",
            "janice josephine horne",
            "a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2",
            "93479171-0b97-4072-bcf0-d44c7f9078ba",
            "4aa0cc2b-1f27-433a-9152-203bb1f69a55",
        )
        for value in forbidden:
            self.assertNotIn(value, text)


class CasePackTest(unittest.TestCase):
    def test_core_is_balanced_and_all_mock_contracts_pass(self):
        document = _load(CORE)
        self.assertIs(document["gate"], True)
        self.assertEqual(len(document["cases"]), 32)
        self.assertEqual(
            Counter(case["persona"] for case in document["cases"]),
            Counter({"shatner": 8, "dolly": 8, "tomasita": 8, "alex": 8}),
        )
        results = [score_case(case, case["mockItems"]) for case in document["cases"]]
        failures = [result["case_id"] for result in results if not result["pass"]]
        self.assertEqual(failures, [])
        summary = summarize(results)
        self.assertEqual(summary["passed"], 32)
        self.assertEqual(summary["must_not_write_violation_rate"], 0.0)
        self.assertGreater(summary["truth_zones"]["must_not_write"]["total"], 20)

    def test_challenge_is_balanced_non_gate_and_mock_ideal_passes(self):
        document = _load(CHALLENGE)
        self.assertIs(document["gate"], False)
        self.assertEqual(len(document["cases"]), 16)
        self.assertEqual(
            Counter(case["persona"] for case in document["cases"]),
            Counter({"shatner": 4, "dolly": 4, "tomasita": 4, "alex": 4}),
        )
        results = [score_case(case, case["mockItems"]) for case in document["cases"]]
        self.assertTrue(all(result["pass"] for result in results))
        clusters = {case["cluster"] for case in document["cases"]}
        self.assertGreaterEqual(len(clusters), 12)

    def test_case_ids_are_unique_across_active_packs(self):
        ids = [case["id"] for path in (CORE, CHALLENGE) for case in _load(path)["cases"]]
        self.assertEqual(len(ids), len(set(ids)))


class ScorerParityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        archive_dir = str(OLD_RUNNER.parent)
        sys.path.insert(0, archive_dir)
        spec = importlib.util.spec_from_file_location("retired_extraction_eval", OLD_RUNNER)
        assert spec and spec.loader
        cls.old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.old)
        sys.path.remove(archive_dir)

    def _assert_parity(self, case, items):
        old = self.old.score_case(case, items)
        new = score_case(case, items)
        self.assertEqual(new["pass"], old["pass"])
        self.assertEqual(new["overall_score"], old["overall_score"])
        self.assertEqual(new["truth_zone_scores"], old["truth_zone_scores"])

    def test_representative_subset_matches_retired_scorer(self):
        core = {case["id"]: case for case in _load(CORE)["cases"]}
        scenarios = [
            (core["xcore_001"], core["xcore_001"]["mockItems"]),
            (core["xcore_001"], core["xcore_001"]["mockItems"][:1]),
            (core["xcore_003"], core["xcore_003"]["mockItems"] + [
                {"fieldPath": "travel.destination", "value": "Ottawa"}
            ]),
            (core["xcore_007"], [{"fieldPath": "military.branch", "value": "Army"}]),
            (core["xcore_014"], core["xcore_014"]["mockItems"]),
            (core["xcore_020"], core["xcore_020"]["mockItems"]),
            (core["xcore_028"], core["xcore_028"]["mockItems"] + [
                {"fieldPath": "family.marriageDate", "value": "2020"}
            ]),
            (core["xcore_032"], []),
        ]
        for case, items in scenarios:
            with self.subTest(case=case["id"], items=len(items)):
                self._assert_parity(case, items)

    def test_alt_path_and_multi_zone_match_retired_scorer(self):
        alt_case = {
            "id": "parity_alt",
            "truthZones": {
                "education.earlyCareer": {
                    "zone": "must_extract",
                    "expected": "school teacher",
                    "alt_defensible_paths": ["education.careerProgression"],
                }
            },
        }
        self._assert_parity(
            alt_case,
            [{"fieldPath": "education.careerProgression", "value": "school teacher"}],
        )
        multi_case = {
            "id": "parity_multi",
            "truthZones": {
                "hobbies.hobbies": {
                    "_multi": [
                        {"zone": "must_extract", "expected": "gardening"},
                        {"zone": "should_ignore"},
                    ]
                }
            },
        }
        self._assert_parity(
            multi_case,
            [{"fieldPath": "hobbies.hobbies", "value": "gardening"}],
        )


class RunnerOfflineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("active_product_harness", RUNNER)
        assert spec and spec.loader
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_plan_is_read_only_and_lists_capability_classes(self):
        result = subprocess.run(
            [sys.executable, str(RUNNER), "--scenario", "plan"],
            cwd=ROOT, text=True, capture_output=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("reference", result.stdout)
        self.assertIn("synthetic_writable", result.stdout)

    def test_offline_core_run_writes_a_machine_readable_report(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "report.json"
            result = subprocess.run(
                [
                    sys.executable, str(RUNNER),
                    "--scenario", "extraction-core",
                    "--mode", "offline",
                    "--max-cases", "4",
                    "--output", str(output),
                ],
                cwd=ROOT, text=True, capture_output=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = _load(output)
            self.assertEqual(report["summary"]["total"], 4)
            self.assertEqual(report["summary"]["passed"], 4)
            self.assertEqual(report["synthetic_rows_created"], [])

    def test_cleanup_refuses_any_non_harness_name_before_network(self):
        with self.assertRaises(self.module.HarnessError):
            self.module._delete_exact_synthetic(
                "http://127.0.0.1:1",
                {"id": "family-id", "display_name": "A real narrator"},
            )

    def test_references_resolve_before_any_synthetic_creation(self):
        manifest = self.module._validate_manifest(_load(PERSONAS))
        created = []
        with mock.patch.object(self.module, "_people", return_value=[]), \
             mock.patch.object(
                 self.module, "_find_reference",
                 side_effect=self.module.HarnessError("missing reference"),
             ), \
             mock.patch.object(self.module, "_create_synthetic") as create:
            with self.assertRaises(self.module.HarnessError):
                self.module._resolve_live_people(
                    "http://unused", ["tomasita", "shatner"],
                    manifest, "run123", created,
                )
        create.assert_not_called()
        self.assertEqual(created, [])

    def test_created_uuid_is_accounted_before_post_create_verification(self):
        manifest = self.module._validate_manifest(_load(PERSONAS))
        created = []
        with mock.patch.object(
            self.module,
            "_http_json",
            side_effect=[
                (200, {"person_id": "exact-new-uuid"}),
                self.module.HarnessError("verification transport failed"),
            ],
        ):
            with self.assertRaises(self.module.HarnessError):
                self.module._create_synthetic(
                    "http://unused", manifest["tomasita"], "run123", created,
                )
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]["id"], "exact-new-uuid")
        self.assertTrue(created[0]["display_name"].startswith("HARNESS PRODUCT DELME "))


if __name__ == "__main__":
    unittest.main()
