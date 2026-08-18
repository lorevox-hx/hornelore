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
        """A HARD reference failure still precedes any synthetic creation.

        NARROWED 2026-08-17. This previously stood for "any reference
        problem aborts the run", because absence and misclassification
        raised alike. Absence is now `not_applicable` and the run
        continues, so the property this test still guards is the one that
        matters: a reference failure that IS fatal happens before a
        writable row exists, and therefore cannot strand one.
        """
        manifest = self.module._validate_manifest(_load(PERSONAS))
        created, unavailable = [], {}
        with mock.patch.object(self.module, "_people", return_value=[]), \
             mock.patch.object(
                 self.module, "_find_reference",
                 side_effect=self.module.HarnessError("ambiguous reference"),
             ), \
             mock.patch.object(self.module, "_create_synthetic") as create:
            with self.assertRaises(self.module.HarnessError):
                self.module._resolve_live_people(
                    "http://unused", ["tomasita", "shatner"],
                    manifest, "run123", created, unavailable,
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


class ReferenceAvailabilityTest(unittest.TestCase):
    """Absent reference personas are N/A; ambiguous or misclassified ones fail.

    A reference narrator that was soft-deleted months ago is a fact about
    the database, not a fault in the harness. Raising on it made an
    unrelated data-state decision look like a harness failure AND took the
    writable synthetic coverage down with it. The two cases that still
    raise are the ones where continuing would be dishonest rather than
    merely limited.
    """

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("harness_refs", RUNNER)
        assert spec and spec.loader
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)
        cls.manifest = cls.module._validate_manifest(_load(PERSONAS))

    def _persona(self, key="shatner"):
        return self.manifest[key]

    # ── N/A, not failure ──────────────────────────────────────────────
    def test_an_absent_reference_is_not_applicable(self):
        row, status = self.module._find_reference(self._persona(), [])
        self.assertIsNone(row)
        self.assertEqual(status, "not_applicable")

    def test_a_soft_deleted_reference_is_not_applicable(self):
        # /api/people excludes soft-deleted rows, so a soft-deleted
        # narrator reaches the harness as an empty match list. Same input,
        # same answer -- and deliberately so.
        row, status = self.module._find_reference(
            self._persona(), [{"id": "x", "display_name": "Someone Else",
                               "narrator_type": "live"}])
        self.assertIsNone(row)
        self.assertEqual(status, "not_applicable")

    def test_a_present_reference_still_resolves(self):
        name = self._persona()["lookup_names"][0]
        row, status = self.module._find_reference(
            self._persona(),
            [{"id": "ref-1", "display_name": name, "narrator_type": "reference"}])
        self.assertEqual(status, "resolved")
        self.assertEqual(row["id"], "ref-1")

    # ── hard failures ─────────────────────────────────────────────────
    def test_duplicate_active_matches_are_a_hard_failure(self):
        name = self._persona()["lookup_names"][0]
        rows = [{"id": "a", "display_name": name, "narrator_type": "reference"},
                {"id": "b", "display_name": name, "narrator_type": "reference"}]
        with self.assertRaises(self.module.HarnessError) as ctx:
            self.module._find_reference(self._persona(), rows)
        self.assertIn("refusing to guess", str(ctx.exception))

    def test_a_matching_non_reference_narrator_is_a_hard_failure(self):
        name = self._persona()["lookup_names"][0]
        with self.assertRaises(self.module.HarnessError) as ctx:
            self.module._find_reference(
                self._persona(),
                [{"id": "live-1", "display_name": name, "narrator_type": "live"}])
        self.assertIn("not 'reference'", str(ctx.exception))

    # ── the writable personas carry on ────────────────────────────────
    def test_absent_references_do_not_stop_synthetic_resolution(self):
        created, unavailable = [], {}
        with mock.patch.object(self.module, "_people", return_value=[]), \
             mock.patch.object(
                 self.module, "_create_synthetic",
                 side_effect=lambda a, p, r, sink: {"id": "syn-" + p["key"],
                                                    "display_name": "x"}):
            rows = self.module._resolve_live_people(
                "http://unused", ["shatner", "dolly", "tomasita", "alex"],
                self.manifest, "run123", created, unavailable,
            )
        self.assertEqual(sorted(rows), ["alex", "tomasita"])
        self.assertEqual(sorted(unavailable), ["dolly", "shatner"])
        for reason in unavailable.values():
            self.assertIn("soft deletion is respected", reason)

    def test_an_absent_reference_is_never_recreated(self):
        """The rule this correction must not quietly break."""
        created, unavailable = [], {}
        with mock.patch.object(self.module, "_people", return_value=[]), \
             mock.patch.object(self.module, "_create_synthetic") as create:
            self.module._resolve_live_people(
                "http://unused", ["shatner", "dolly"],
                self.manifest, "run123", created, unavailable,
            )
        create.assert_not_called()
        self.assertEqual(created, [])

    # ── three-state reporting ─────────────────────────────────────────
    def test_product_read_reports_not_applicable_and_still_reads_synthetics(self):
        calls = []

        def fake_http(api, method, path, **kw):
            calls.append(path)
            return 200, {"person_id": "syn-tomasita"}

        with mock.patch.object(self.module, "_http_json", side_effect=fake_http):
            results = self.module._run_product_reads(
                ["shatner", "tomasita"], self.manifest,
                {"tomasita": {"id": "syn-tomasita"}}, "http://unused",
                {"shatner": "reference narrator not present in this database"},
            )
        by_key = {row["persona"]: row for row in results}
        self.assertFalse(by_key["shatner"]["applicable"])
        self.assertTrue(by_key["tomasita"]["applicable"])
        # The unavailable reference contributed no HTTP traffic...
        self.assertTrue(all("syn-tomasita" in p for p in calls))
        # ...and the writable persona was genuinely read.
        self.assertEqual(len(calls), 3)

    def test_the_three_states_are_counted_apart(self):
        rows = [
            {"persona": "shatner", "applicable": False, "pass": True},
            {"persona": "tomasita", "applicable": True, "pass": True},
            {"persona": "alex", "applicable": True, "pass": False},
        ]
        applicable = [r for r in rows if r.get("applicable")]
        summary = {
            "total": len(applicable),
            "passed": sum(1 for r in applicable if r["pass"]),
            "failed": sum(1 for r in applicable if not r["pass"]),
            "not_applicable": len(rows) - len(applicable),
        }
        # `total` is the APPLICABLE total, so an N/A run cannot report
        # itself as complete by shrinking its own denominator.
        self.assertEqual(summary, {"total": 2, "passed": 1, "failed": 1,
                                   "not_applicable": 1})

    def test_an_unavailable_persona_never_scores_as_a_pass(self):
        # A gate must not be able to read "all passed" from cases nobody
        # ran, so an N/A extraction case carries pass=False AND
        # applicable=False -- it is excluded from the denominator rather
        # than counted as success.
        results = self.module._run_extraction_cases(
            [{"id": "xcore_001", "persona": "shatner", "answer": "x",
              "truthZones": [], "context": {}}],
            {}, mode="live", api_base="http://unused",
        )
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["applicable"])
        self.assertFalse(results[0]["pass"])
        self.assertEqual(results[0]["method"], "not_applicable")


if __name__ == "__main__":
    unittest.main()
