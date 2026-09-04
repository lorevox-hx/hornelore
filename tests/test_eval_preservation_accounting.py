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

BANK = ROOT / "data" / "qa" / "question_bank_extraction_cases.json"
GEN = ROOT / "data" / "qa" / "question_bank_generational_cases.json"


def load_cases(path: Path):
    import json
    d = json.loads(path.read_text(encoding="utf-8"))
    return d["cases"] if isinstance(d, dict) and "cases" in d else d


def by_id(cases, cid):
    for c in cases:
        if c.get("id") == cid:
            return c
    raise AssertionError(f"{cid} not in the bank")


# THE REAL CASES, not a fixture. The first version of this file invented
# `truthZones: {"must_extract": [...]}` — a shape no bank uses — so all seven
# tests passed while the helper returned empty fates for all 114 live cases.
# That is the same failure this Phase 3 work exists to eliminate: a property
# supplied instead of measured. Every test below loads from data/qa/.
CASES = load_cases(BANK)
GEN_CASES = load_cases(GEN)
CASE = by_id(CASES, "case_001")


def quarantine_for(field_path, value):
    return {
        "kind": "unbound_relationship", "value": value,
        "label": f"{value}'s relationship to you",
        "proposed_fieldPath": field_path,
        "proposed_items": [{"fieldPath": field_path, "value": value,
                            "confidence": 0.9}],
        "reasons": ["identity_conflict", "relationship_unstated"],
        "reason": "identity_conflict", "not_applied": True,
    }

class TheRealBankShapes(unittest.TestCase):
    """Three shapes exist in the tree. The helper must read all three."""

    def test_case_001_is_fieldPath_keyed_and_yields_facts(self):
        tz = CASE["truthZones"]
        self.assertIsInstance(tz.get("personal.placeOfBirth"), dict,
                              "case_001 is fieldPath-keyed, not a list")
        facts = E.expected_must_extract(CASE)
        self.assertEqual(2, len(facts))
        self.assertIn({"fieldPath": "personal.placeOfBirth",
                       "expected": "Williston, North Dakota"}, facts)

    def test_generational_cases_use_top_level_arrays(self):
        g = GEN_CASES[0]
        self.assertIsNone(g.get("truthZones"))
        self.assertTrue(g.get("must_extract"))
        self.assertEqual(len(g["must_extract"]), len(E.expected_must_extract(g)))

    def test_a_real_multi_case_is_read(self):
        """case_203 puts hobbies.hobbies in must_extract AND should_ignore.

        The assertion names the fact INSIDE the _multi record. An earlier
        version only checked that expected_must_extract() returned something,
        which the case's other field satisfied on its own — so a mutation
        ignoring _multi entirely passed.
        """
        c = by_id(GEN_CASES, "case_203")
        tz = E.normalize_truth_zones(c)
        self.assertIn("_multi", tz.get("hobbies.hobbies", {}),
                      "no _multi record built for case_203")
        facts = E.expected_must_extract(c)
        self.assertIn({"fieldPath": "hobbies.hobbies",
                       "expected": "going to drive-in movies"}, facts,
                      "the must_extract half of the _multi record was lost")

    def test_a_multi_fact_accounts_end_to_end(self):
        c = by_id(GEN_CASES, "case_203")
        acc = E.preservation_accounting(
            c, [], [quarantine_for("hobbies.hobbies",
                                   "going to drive-in movies")])
        self.assertEqual(
            "preserved_for_review",
            acc["fates"]["hobbies.hobbies=going to drive-in movies"])

    def test_the_whole_bank_yields_facts(self):
        total = sum(len(E.expected_must_extract(c)) for c in CASES)
        self.assertGreater(total, 100,
                           "the live bank produced almost no expected facts — "
                           "the helper is reading a shape the bank does not use")

    def test_score_case_and_the_accounting_share_one_reader(self):
        src = SCRIPT.read_text(encoding="utf-8")
        body = src.split("def score_case")[1].split("\ndef ")[0]
        self.assertIn("normalize_truth_zones(case)", body,
                      "score_case must not keep a private copy of the reader")


class Fates(unittest.TestCase):
    """Driven by real case_001: placeOfBirth + dateOfBirth, both must_extract."""

    FACT = {"fieldPath": "personal.placeOfBirth",
            "expected": "Williston, North Dakota"}
    OTHER = {"fieldPath": "personal.dateOfBirth", "expected": "1962-12-24"}

    def _key(self, f):
        return f"{f['fieldPath']}={f['expected']}"

    def test_empty_output_is_missing(self):
        acc = E.preservation_accounting(CASE, [], [])
        self.assertEqual(2, acc["counts"]["missing"])
        self.assertEqual("missing", acc["fates"][self._key(self.FACT)])

    def test_an_executable_item_is_executed_correct(self):
        acc = E.preservation_accounting(
            CASE, [{"fieldPath": self.FACT["fieldPath"],
                    "value": self.FACT["expected"]}], [])
        self.assertEqual("executed_correct", acc["fates"][self._key(self.FACT)])
        self.assertEqual(1, acc["counts"]["executed_correct"])

    def test_the_same_fact_in_proposed_items_is_preserved(self):
        acc = E.preservation_accounting(
            CASE, [], [quarantine_for(self.FACT["fieldPath"],
                                      self.FACT["expected"])])
        self.assertEqual("preserved_for_review",
                         acc["fates"][self._key(self.FACT)])
        self.assertEqual(1, acc["counts"]["preserved_for_review"])

    def test_preserved_and_missing_are_distinguishable(self):
        """THE DISCRIMINATION. Identical executable output (none); the only
        difference is whether the withheld fact was preserved."""
        q = E.preservation_accounting(
            CASE, [], [quarantine_for(self.FACT["fieldPath"],
                                      self.FACT["expected"])])["counts"]
        n = E.preservation_accounting(CASE, [], [])["counts"]
        self.assertNotEqual(q, n)
        self.assertEqual(1, q["preserved_for_review"])
        self.assertEqual(0, n["preserved_for_review"])

    def test_a_wrong_executable_value_is_not_preserved(self):
        acc = E.preservation_accounting(
            CASE, [{"fieldPath": self.FACT["fieldPath"], "value": "Fargo"}], [])
        self.assertEqual("wrong_executable", acc["fates"][self._key(self.FACT)])

    def test_an_executed_fact_outranks_a_review_entry_for_it(self):
        acc = E.preservation_accounting(
            CASE, [{"fieldPath": self.FACT["fieldPath"],
                    "value": self.FACT["expected"]}],
            [quarantine_for(self.FACT["fieldPath"], self.FACT["expected"])])
        self.assertEqual("executed_correct", acc["fates"][self._key(self.FACT)])

    def test_an_entry_with_only_a_subject_still_counts(self):
        thin = quarantine_for(self.FACT["fieldPath"], self.FACT["expected"])
        thin.pop("proposed_items")
        acc = E.preservation_accounting(CASE, [], [thin])
        self.assertEqual("preserved_for_review",
                         acc["fates"][self._key(self.FACT)])

    def test_a_real_generational_case_accounts_too(self):
        g = GEN_CASES[0]
        facts = E.expected_must_extract(g)
        acc = E.preservation_accounting(
            g, [{"fieldPath": facts[0]["fieldPath"],
                 "value": facts[0]["expected"]}], [])
        self.assertEqual(1, acc["counts"]["executed_correct"])
        self.assertEqual(len(facts) - 1, acc["counts"]["missing"])


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


class SurfaceFormMustNotReadAsLoss(unittest.TestCase):
    """"December 23rd" and "December 23" are the same day.

    WO-LORI-ARCHIVE-TO-MEMOIR-02 Phase 3 (2026-09-04), rule 4.

    The fate classifier compared normalized strings with containment while the
    SCORER resolved dates, role aliases and token overlap. So on
    r5j-phase3-v1 the guard preserved case_015's fact -- the extractor
    proposed "died December 23, 1967" against an expected "died December 23rd,
    1967" -- and the table reported it `missing`.

    That is the one confusion this accounting exists to prevent, and every
    such mismatch understates preserved_for_review while overstating missing.
    The fix reuses score_field_match(), the scorer's single value-equivalence
    entry point, rather than growing a second implementation that can drift.

    Driven by the REAL case_015 and the value the live extractor really
    produced, not by an invented pair.
    """

    CASE_ID = "case_015"
    LIVE_VALUE = "died December 23, 1967"      # what the extractor emitted
    PATH = "parents.notableLifeEvents"

    def setUp(self):
        cases = load_cases(BANK)
        self.case = next((c for c in cases
                          if (c.get("id") or c.get("caseId")) == self.CASE_ID),
                         None)
        if self.case is None:                  # pragma: no cover
            self.skipTest(f"{self.CASE_ID} not in the bank")

    def test_the_fixture_really_does_differ_in_surface_form(self):
        """Precondition, measured. If the bank were edited to say "23", this
        test would stop discriminating and would say so instead of passing."""
        expected = {e["fieldPath"]: e["expected"]
                    for e in E.expected_must_extract(self.case)}
        self.assertIn(self.PATH, expected)
        self.assertNotEqual(expected[self.PATH], self.LIVE_VALUE,
                            "the two forms are now identical — this test no "
                            "longer proves normalization happens")
        self.assertIn("23rd", expected[self.PATH])

    def test_a_quarantined_fact_reads_as_preserved_not_missing(self):
        """THE MUTATION: revert to containment and this returns `missing`."""
        clar = [{
            "kind": "unbound_relationship",
            "value": "",
            "proposed_fieldPath": self.PATH,
            "proposed_items": [{"fieldPath": self.PATH,
                                "value": self.LIVE_VALUE,
                                "confidence": 0.9,
                                "grounding": "spoken"}],
            "reasons": ["relationship_unstated"],
        }]
        pres = E.preservation_accounting(self.case, [], clar)
        fates = list(pres["fates"].values())
        self.assertIn("preserved_for_review", fates,
                      f"a preserved fact was reported as {fates}")
        self.assertEqual(0, pres["counts"]["missing"], pres["fates"])

    def test_an_unrelated_value_is_still_missing(self):
        """Normalization must not turn every quarantine into a match."""
        clar = [{
            "kind": "unbound_relationship",
            "value": "",
            "proposed_fieldPath": self.PATH,
            "proposed_items": [{"fieldPath": self.PATH,
                                "value": "moved to Akron for the tyre works",
                                "confidence": 0.9}],
            "reasons": ["relationship_unstated"],
        }]
        pres = E.preservation_accounting(self.case, [], clar)
        self.assertEqual(0, pres["counts"]["preserved_for_review"],
                         pres["fates"])
