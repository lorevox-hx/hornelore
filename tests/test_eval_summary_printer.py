"""The evaluator's console printer is a production boundary.

WO-LORI-ARCHIVE-TO-MEMOIR-02 Phase 3 (2026-09-04).

WHY THIS FILE EXISTS. `tests/test_eval_preservation_accounting.py` proves that
`preservation_accounting()` CREATES the right counts. Nothing proved that
anything could READ them. The r5j-phase3-v1 run made the gap visible: the
preservation block in `print_summary()` iterated a bare name `results`, which
exists only in the CALLER's scope, so the summary died with

    WARNING: print_summary crashed: name 'results' is not defined

after the score had printed and before Layer 1. The 114-case run itself was
fine -- the JSON is pre-written to disk precisely so a printer fault cannot
destroy an expensive run -- but the operator was shown a truncated console and
had to be told the console "may be partial".

This is the tenth instance of the lane's recurring defect and it is recorded as
such in docs/TESTING-DOCTRINE.md: a test covered the producer, no test crossed
the boundary to the consumer, and the suite had no opinion.

WHAT THIS TEST MAY NOT DO. It may not hand-build a `report` dict. The property
being proven is that the printer reads the report PRODUCTION builds, so the
report must come from `generate_report()` and the per-case fields must come
from `score_case()` and `preservation_accounting()` -- the same three functions
the live runner calls. A hand-built dict would prove only that the printer can
read a dict this test wrote, which is the failure mode the doctrine names.
"""

import importlib.util
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts" / "archive" / "run_question_bank_extraction_eval.py"
CASES = REPO_ROOT / "data" / "qa" / "question_bank_extraction_cases.json"


def _load_runner():
    """Import the eval runner by path -- it is a script, not a package."""
    spec = importlib.util.spec_from_file_location("_qb_eval_runner", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class EvalSummaryPrinterTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not RUNNER.exists():          # pragma: no cover - environment guard
            raise unittest.SkipTest(f"runner not present at {RUNNER}")
        if not CASES.exists():           # pragma: no cover - environment guard
            raise unittest.SkipTest(f"case bank not present at {CASES}")
        cls.ev = _load_runner()
        cls.cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]

    # ------------------------------------------------------------------
    # helpers -- every field comes from a production function
    # ------------------------------------------------------------------
    def _base_result(self, case, extracted_items):
        """The case_results entry as the LIVE runner assembles it.

        These are the keys the live path sets at
        run_question_bank_extraction_eval.py:1367-1380, copied because
        generate_report() reads several of them unguarded --
        `r["expectedBehavior"]` at :1754 is a hard subscript. Guessing this
        shape instead of reading it is the exact defect this file exists to
        stop repeating.
        """
        result = self.ev.score_case(case, extracted_items)
        result["case_id"] = case["id"]
        result["narratorId"] = case.get("narratorId")
        result["phase"] = case["phase"]
        result["subTopic"] = case["subTopic"]
        result["expectedBehavior"] = case["expectedBehavior"]
        result["currentExtractorExpected"] = case.get(
            "currentExtractorExpected", True)
        result["caseType"] = case.get("caseType", "contract")
        result["oralHistoryStyle"] = case.get("oralHistoryStyle",
                                              "life_history")
        result["style_bucket"] = case.get("style_bucket", "life_history")
        result["chunk_size"] = case.get("chunk_size", "small")
        result["noise_profile"] = case.get("noise_profile", "clean")
        result["case_mode"] = case.get("case_mode", "contract")
        result["sequence_group"] = case.get("sequence_group")
        result["mode"] = "unit"
        result["method"] = "llm"
        result["elapsed_ms"] = 0
        result["extracted_count"] = len(extracted_items)
        result["current_era"] = case.get("currentEra") or "earliest_years"
        result["current_pass"] = case.get("currentPass") or "pass1"
        result["current_mode"] = case.get("currentMode") or "open"
        result["stubborn_partition"] = self.ev._stubborn_partition_for(
            case["id"])
        return result

    def _result_for(self, case, extracted_items, clarifications):
        """A full entry, including the Phase 3 preservation fields."""
        result = self._base_result(case, extracted_items)
        review = [c for c in clarifications
                  if c.get("kind") == "unbound_relationship"]
        result["review_entries"] = review
        result["review_count"] = len(review)
        pres = self.ev.preservation_accounting(case, extracted_items,
                                               clarifications)
        result["preservation"] = pres["counts"]
        result["preservation_fates"] = pres["fates"]
        result["executable_count"] = len(extracted_items)
        return result, pres

    def _quarantined_case(self):
        """A real case whose expected facts are withheld, not extracted.

        case_105 is 'My dad was born in Stanley.' -- one expected fact,
        parents.birthPlace. Feeding NO items and one quarantine reproduces
        exactly what the guard did to it live on r5j-phase3-v1.
        """
        case = next(c for c in self.cases if c["id"] == "case_105")
        clar = [{
            "kind": "unbound_relationship",
            "value": "",
            "label": "a parents detail we could not place",
            "proposed_fieldPath": "parents.birthPlace",
            "proposed_items": [{"fieldPath": "parents.birthPlace",
                                "value": "Stanley", "confidence": 0.9,
                                "grounding": "spoken"}],
            "confirmation_reasons": ["relationship_unstated"],
        }]
        return case, [], clar

    # ------------------------------------------------------------------
    def test_printer_runs_and_reads_preservation_from_the_report(self):
        """print_summary must render the counts, from report['case_results'].

        THE MUTATION THIS CATCHES: restoring `for _r in results` raises
        NameError inside print_summary, the assertions below never see the
        block, and this test fails. That is the whole point -- the printer is
        exercised, not merely imported.
        """
        case, items, clar = self._quarantined_case()
        result, pres = self._result_for(case, items, clar)

        # PRODUCTION builds the report. This test does not.
        report = self.ev.generate_report([result], mode="unit")
        self.assertIn("case_results", report)

        buf = io.StringIO()
        with redirect_stdout(buf):
            self.ev.print_summary(report)
        out = buf.getvalue()

        self.assertIn("PRESERVATION ACCOUNTING", out,
                      "the preservation block did not render at all -- the "
                      "printer either crashed or never reached it")

        # The numbers must be the ones preservation_accounting produced, not
        # zeros and not a count this test supplied.
        self.assertGreaterEqual(pres["counts"]["preserved_for_review"], 1,
                                "fixture precondition: the live guard withheld "
                                "case_105, so this must be a quarantine")
        self.assertIn(
            f"preserved_for_review:   {pres['counts']['preserved_for_review']}",
            out,
            f"printed block did not carry the produced count; got:\n{out}")
        self.assertIn("withheld ON PURPOSE, not lost", out)
        self.assertIn("cases with review entries: 1", out)

    def test_printer_reaches_layer_1_after_the_block(self):
        """The crash truncated the console mid-report; prove it no longer does.

        Asserting only that the block prints would still pass if the printer
        died on the next line. Layer 1 is what the operator lost.
        """
        case, items, clar = self._quarantined_case()
        result, _ = self._result_for(case, items, clar)
        report = self.ev.generate_report([result], mode="unit")

        buf = io.StringIO()
        with redirect_stdout(buf):
            self.ev.print_summary(report)
        out = buf.getvalue()

        self.assertIn("LAYER 1: CONTRACT / REGRESSION", out)
        i_block = out.index("PRESERVATION ACCOUNTING")
        i_layer = out.index("LAYER 1: CONTRACT / REGRESSION")
        self.assertLess(i_layer, i_block + len(out),
                        "Layer 1 must still be reached")

    def test_printer_survives_a_report_with_no_preservation_data(self):
        """Older reports have no preservation keys. The printer predates them.

        docs/reports/ holds runs from before this accounting existed, and an
        operator re-printing one must not get a crash for a missing key.
        """
        case = next(c for c in self.cases if c["id"] == "case_001")
        result = self._base_result(case, [
            {"fieldPath": "personal.placeOfBirth",
             "value": "Williston, North Dakota", "confidence": 0.95},
            {"fieldPath": "personal.dateOfBirth",
             "value": "1962-12-24", "confidence": 0.95},
        ])
        # deliberately NO preservation / review_count keys
        report = self.ev.generate_report([result], mode="unit")

        buf = io.StringIO()
        with redirect_stdout(buf):
            self.ev.print_summary(report)
        out = buf.getvalue()
        self.assertIn("LAYER 1: CONTRACT / REGRESSION", out)


class ReviewEntryFidelityTest(unittest.TestCase):
    """The evaluator's copy of a quarantine must not lose grounding.

    THE BOUNDARY: the SERVER builds the clarification envelope (extract.py
    _apply_kinship_binding_guard, which annotates every proposed value
    spoken/derived/unsupported) and the EVALUATOR copies it into the report.
    Nothing tested the copy, and the copy listed three keys. Measured on
    r5j-phase3-v1 and r5j-phase3-generational: 171 preserved values in the
    reports, ZERO with a grounding label.

    So this test does not hand-build an envelope -- that would prove only that
    the copier can copy a dict this file wrote. It runs the SHIPPED extraction
    pipeline, takes the envelope the guard actually produces, and copies that.
    """

    ANSWER = ("Otis died in 2005. Heart attack at sixty-three. The kids were "
              "grown — Charlene was in Atlanta with her family, Bernard in "
              "Detroit still.")
    PROFILE = {"profile_json": {
        "spouses": [{"firstName": "Otis", "lastName": "Bell"}],
        "parents": [{"firstName": "Clarence"}, {"firstName": "Ida"}]}}
    ITEMS = [
        {"fieldPath": "parents.firstName", "value": "Otis", "confidence": 0.9},
        # 1922 is the fabricated one: no narrator said it. It is the reason
        # grounding exists and the reason it must reach the report.
        {"fieldPath": "parents.birthDate", "value": "1922", "confidence": 0.7},
        {"fieldPath": "parents.deathDate", "value": "2005", "confidence": 0.9},
    ]

    @classmethod
    def setUpClass(cls):
        import sys
        server = str(REPO_ROOT / "server" / "code")
        if server not in sys.path:
            sys.path.insert(0, server)
        try:
            from api.routers import extract as EX
        except Exception as exc:      # pragma: no cover - environment guard
            raise unittest.SkipTest(f"extract router unavailable: {exc}")
        cls.EX = EX
        cls.ev = _load_runner()

    def _live_envelope(self):
        """The clarification envelope the SHIPPED guard produces."""
        from unittest import mock
        EX = self.EX
        req = EX.ExtractFieldsRequest(
            person_id="narrator-1", answer=self.ANSWER,
            current_section="family_life", current_target_path=None)
        with mock.patch("api.db.get_profile", return_value=self.PROFILE), \
             mock.patch.object(EX, "_extract_via_llm",
                               return_value=(list(self.ITEMS), "[stub]")):
            resp = EX.run_field_extraction(req)
        return [c for c in resp.clarification_required
                if c.get("kind") == "unbound_relationship"]

    def test_the_server_actually_annotates_grounding(self):
        """Fixture precondition, measured -- not asserted in a comment.

        If the server stopped emitting grounding, the fidelity test below
        would pass vacuously. This fails first and says so.
        """
        env = self._live_envelope()
        self.assertTrue(env, "the guard produced no quarantine to copy")
        vals = {p["fieldPath"]: p.get("grounding")
                for p in env[0]["proposed_items"]}
        self.assertEqual("unsupported", vals.get("parents.birthDate"),
                         f"1922 was never spoken; got {vals}")
        self.assertEqual("spoken", vals.get("parents.deathDate"),
                         f"2005 is in the answer; got {vals}")

    def test_grounding_survives_the_report_copy(self):
        """THE MUTATION: drop the two `if p.get(...)` copies and this fails."""
        env = self._live_envelope()
        copied = self.ev.compact_review_entries(env)

        self.assertEqual(len(env), len(copied))
        got = {p["fieldPath"]: p.get("grounding")
               for p in copied[0]["proposed_items"]}
        self.assertEqual("unsupported", got.get("parents.birthDate"),
                         "the fabricated value reached the report with no "
                         f"grounding label; got {got}")
        self.assertEqual("spoken", got.get("parents.deathDate"), got)

        # And the detail that justifies the verdict travels with it.
        detail = next(p.get("grounding_detail")
                      for p in copied[0]["proposed_items"]
                      if p["fieldPath"] == "parents.birthDate")
        self.assertIsInstance(detail, dict)
        self.assertEqual(1922, detail.get("year"))

    def test_long_values_are_still_truncated(self):
        """Truncation is why this copy exists; grounding must not undo it."""
        entries = self.ev.compact_review_entries([{
            "kind": "unbound_relationship",
            "proposed_items": [{"fieldPath": "parents.notableLifeEvents",
                                "value": "x" * 400, "confidence": 0.8,
                                "grounding": "spoken"}],
        }])
        v = entries[0]["proposed_items"][0]["value"]
        self.assertEqual(101, len(v))
        self.assertTrue(v.endswith("…"))
        self.assertEqual("spoken", entries[0]["proposed_items"][0]["grounding"])

    def test_an_envelope_without_grounding_keeps_its_old_shape(self):
        """Pre-Phase-3 reports must not gain null keys."""
        entries = self.ev.compact_review_entries([{
            "kind": "unbound_relationship",
            "proposed_items": [{"fieldPath": "parents.firstName",
                                "value": "Otis", "confidence": 0.9}],
        }])
        self.assertNotIn("grounding", entries[0]["proposed_items"][0])
        self.assertNotIn("grounding_detail", entries[0]["proposed_items"][0])


if __name__ == "__main__":       # pragma: no cover
    unittest.main()
