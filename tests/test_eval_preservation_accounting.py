"""The evaluation must be able to tell a quarantine from a loss.

WO-LORI-ARCHIVE-TO-MEMOIR-02 Phase 3 (2026-09-04).

The evaluator read `data["items"]` and discarded `clarification_required`
entirely. An extraction that deliberately WITHHELD a fact for review therefore
looked exactly like one that lost it — opposite outcomes, identical report.

That distinction has already been decided the wrong way once: when the
reverted kinship guard cost five cases, nothing in the JSON could say whether
those five were suppressed or preserved.

PRESERVATION IS ACCOUNTING, NOT SCORING. `preserved_for_review` is not a pass
and must never touch `overall_score`, the v2/v3 subsets, or the pass flag —
the historical ladder has to stay comparable run to run.
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "archive" / "run_question_bank_extraction_eval.py"


def _load():
    spec = importlib.util.spec_from_file_location("qb_eval", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


E = _load()

CASE = {
    "id": "case_x", "narratorId": "n", "phase": "p", "subTopic": "s",
    "expectedBehavior": "extract_multiple",
    "truthZones": {"must_extract": [
        {"fieldPath": "parents.firstName", "value": "Otis"},
        {"fieldPath": "residence.place", "value": "Plymouth Road"},
    ]},
}

QUARANTINE = {
    "kind": "unbound_relationship", "value": "Otis",
    "label": "Otis's relationship to you",
    "proposed_fieldPath": "parents.firstName",
    "proposed_items": [
        {"fieldPath": "parents.firstName", "value": "Otis", "confidence": 0.9},
        {"fieldPath": "parents.birthDate", "value": "1922", "confidence": 0.7},
    ],
    "reasons": ["identity_conflict", "relationship_unstated"],
    "reason": "identity_conflict", "not_applied": True,
}


class Fates(unittest.TestCase):

    def test_a_quarantined_fact_is_preserved_not_missing(self):
        acc = E.preservation_accounting(
            CASE, [{"fieldPath": "residence.place", "value": "Plymouth Road"}],
            [QUARANTINE])
        self.assertEqual("preserved_for_review",
                         acc["fates"]["parents.firstName=Otis"])
        self.assertEqual("executed_correct",
                         acc["fates"]["residence.place=Plymouth Road"])
        self.assertEqual(1, acc["counts"]["preserved_for_review"])
        self.assertEqual(0, acc["counts"]["missing"])

    def test_the_same_shape_WITHOUT_the_quarantine_is_missing(self):
        """THE DISCRIMINATION. Identical executable items; the only difference
        is whether the withheld fact was preserved. If these two agreed, the
        accounting would be worthless."""
        acc = E.preservation_accounting(
            CASE, [{"fieldPath": "residence.place", "value": "Plymouth Road"}], [])
        self.assertEqual("missing", acc["fates"]["parents.firstName=Otis"])
        self.assertEqual(0, acc["counts"]["preserved_for_review"])
        self.assertEqual(1, acc["counts"]["missing"])

    def test_a_wrong_executable_value_is_not_preserved(self):
        acc = E.preservation_accounting(
            CASE, [{"fieldPath": "parents.firstName", "value": "Clarence"}], [])
        self.assertEqual("wrong_executable",
                         acc["fates"]["parents.firstName=Otis"])

    def test_an_executed_fact_outranks_a_review_entry_for_it(self):
        acc = E.preservation_accounting(
            CASE, [{"fieldPath": "parents.firstName", "value": "Otis"}],
            [QUARANTINE])
        self.assertEqual("executed_correct",
                         acc["fates"]["parents.firstName=Otis"])

    def test_an_entry_with_only_a_subject_still_counts(self):
        thin = dict(QUARANTINE)
        thin.pop("proposed_items")
        acc = E.preservation_accounting(CASE, [], [thin])
        self.assertEqual("preserved_for_review",
                         acc["fates"]["parents.firstName=Otis"])


class AccountingIsNotScoring(unittest.TestCase):

    def test_score_case_never_sees_clarifications(self):
        """score_case takes items only. If preservation ever reached it, a
        quarantine would inflate the historical ladder."""
        import inspect
        params = list(inspect.signature(E.score_case).parameters)
        self.assertEqual(["case", "extracted_items"], params)

    def test_the_reader_and_the_report_keep_them_separate(self):
        src = SCRIPT.read_text(encoding="utf-8")
        code = "\n".join(ln for ln in src.split("\n")
                         if not ln.lstrip().startswith("#"))
        self.assertIn('data.get("clarification_required", [])', code,
                      "the response's review entries are still discarded")
        self.assertIn('result["review_entries"]', code)
        self.assertIn('result["preservation"]', code)
        self.assertIn("not part of the score", src)
        # preservation must not be mixed into the score fields
        self.assertNotIn("preserved_for_review\"]", code.split("def score_case")[1]
                         .split("\ndef ")[0])


if __name__ == "__main__":
    unittest.main()
