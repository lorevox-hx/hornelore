"""The Block C replay instrument must refuse an incomplete cohort.

WO-LORI-ARCHIVE-TO-MEMOIR-02, Phase 6, Block C.

WHY THIS FILE EXISTS. The first version of
`scripts/phase6_blockc_counterfactual_replay.py` read `narrator_input`
at the top level of each trace record. In the cohort-C trace that field
lives one level down, under `context`. Every one of the 38 turns was
therefore skipped, and the script printed a full report of clean zeroes
— 0 splits, 0 eligibility flips, 0 changed turns — and exited 0.

"Nothing was read" and "nothing changed" were byte-identical output.
That is precisely the class of false success B1 was built to eliminate
in the product, reproduced inside the instrument built to measure it.

These tests pin the refusal, not the report. They run the instrument's
real entry point against synthetic traces, so a future edit that
restores the silent-zero behaviour fails here rather than in a readout
somebody trusts.

Run with the repo root on the path:

    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=.:server/code .venv/bin/python -m unittest \\
        tests.test_phase6_blockc_replay_instrument
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(REPO_ROOT), str(REPO_ROOT / "server" / "code")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scripts.phase6_blockc_counterfactual_replay import (  # noqa: E402
    _classify,
    check_cohort_integrity,
    load_turns,
    main,
)


def _deterministic_record(trace_id, mode, delivered):
    """A non-generated route, shaped like cohort-C lines 11 and 26.

    Blank turn_key, no narrator_input, generation_attempted False, and
    no id-40/id-48 stage — measured from the real trace, not invented.
    """
    return {
        "trace_id": trace_id,
        "narrator_id": "f0442456-d1fa-4215-a448-c81894dcf44e",
        "conversation_id": "replay-test",
        "turn_key": "",
        "schema_version": 2,
        "delivered_text": delivered,
        "stages": [],
        "context": {
            "generation_attempted": False,
            "effective_turn_mode": mode,
            "requested_turn_mode": "interview",
        },
    }


def _record(turn_key, utterance, *, nested=True):
    """A trace record shaped like the real thing.

    `nested=True` mirrors the cohort-C schema (schema_version 2), where
    the per-turn payload sits under `context`.
    """
    payload = {
        "narrator_input": utterance,
        "turn_mode": "interview",
        "stages": [],
    }
    rec = {
        "trace_id": f"trace-{turn_key}",
        "narrator_id": "4ea5bb89-adb8-4065-a101-44f63f4b7c79",
        "conversation_id": "replay-test",
        "turn_key": turn_key,
        "schema_version": 2,
    }
    if nested:
        rec["context"] = payload
    else:
        rec.update(payload)
        rec["context"] = {}
    return rec


def _write_trace(tmpdir, records):
    path = Path(tmpdir) / "trace.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")
    return path


class LoaderRecoversTheRealSchemaTests(unittest.TestCase):
    """Pins the actual defect: the payload is under `context`."""

    def test_narrator_input_nested_under_context_is_recovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_trace(tmp, [
                _record("turnrow:2531",
                        "I was born on December 31, 1960, in West St. "
                        "Paul, Minnesota."),
                _record("turnrow:2532", "We moved to Bardstown in 1971."),
            ])
            turns, excluded, unexplained, malformed, total = load_turns(path)
        self.assertEqual(len(turns), 2)
        self.assertEqual((len(excluded), len(unexplained), malformed, total),
                         (0, 0, 0, 2))
        self.assertIn("West St. Paul", turns[0]["_replay_text"])
        self.assertEqual(turns[0]["_replay_turn_key"], "turnrow:2531")

    def test_a_flat_record_still_works(self):
        """Older or future traces may carry the field at top level."""
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_trace(tmp, [
                _record("turnrow:1", "We lived in Lowell.", nested=False),
            ])
            turns, _, _, _, _ = load_turns(path)
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0]["_replay_text"], "We lived in Lowell.")


class DeterministicRouteClassificationTests(unittest.TestCase):
    """The two cohort-C exclusions, and why they are not omissions."""

    def test_a_non_generated_route_with_no_authority_stage_is_not_applicable(self):
        verdict, reason = _classify(
            _deterministic_record("t11", "witness",
                                  "Got it — Princeton Avenue."))
        self.assertEqual(verdict, "not_applicable")
        self.assertIn("generation_attempted=False", reason)

    def test_a_non_generated_route_that_ran_id40_is_unexplained(self):
        """The load-bearing half of the exclusion rule.

        "It never generated" is not sufficient. If id 40 left a stage,
        that authority participated in the turn, and dropping it from a
        counterfactual ABOUT id 40 would hide the very thing being
        measured.
        """
        rec = _deterministic_record("t11", "witness", "Got it.")
        rec["stages"] = [{"stage": "chain_anchor_opener", "authority_id": 40,
                          "selected": True, "eligible": True, "fired": True}]
        verdict, reason = _classify(rec)
        self.assertEqual(verdict, "unexplained")
        self.assertIn("id 40", reason)

    def test_a_generated_turn_with_no_narrator_input_is_unexplained(self):
        rec = _deterministic_record("t99", "interview", "something")
        rec["context"]["generation_attempted"] = True
        verdict, _ = _classify(rec)
        self.assertEqual(verdict, "unexplained")


class IntegrityRefusesAnIncompleteCohortTests(unittest.TestCase):

    def _turns(self, n):
        return [
            {"_replay_turn_key": f"turnrow:{i}", "_replay_text": "x"}
            for i in range(n)
        ]

    def _excluded(self, n):
        return [
            {"line": 100 + i, "turn_key": "", "trace_id": f"t{i}",
             "mode": "witness", "reason": "deterministic route"}
            for i in range(n)
        ]

    def test_the_real_cohort_c_shape_passes(self):
        """38 records = 36 replayable + 2 deterministic exclusions."""
        result = check_cohort_integrity(
            self._turns(36), self._excluded(2), [], 0, 38, 38, 36)
        self.assertTrue(result["ok"], result["problems"])
        self.assertEqual(result["recovered"], 36)
        self.assertEqual(len(result["excluded"]), 2)

    def test_zero_recovered_is_refused(self):
        result = check_cohort_integrity(
            [], [], [], 0, 38, 38, 36)
        self.assertFalse(result["ok"])

    def test_a_partial_cohort_is_refused(self):
        """35 of 36 applicable is not a counterfactual, it is a subset."""
        result = check_cohort_integrity(
            self._turns(35), self._excluded(2), [], 0, 38, 38, 36)
        self.assertFalse(result["ok"])

    def test_an_unexplained_record_is_refused(self):
        """An omission without a measured production reason blocks."""
        unexplained = [{"line": 7, "turn_key": "", "trace_id": "t7",
                        "mode": "interview",
                        "reason": "no narrator_input and "
                                  "generation_attempted=True"}]
        result = check_cohort_integrity(
            self._turns(35), self._excluded(2), unexplained, 0, 38, 38, 35)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any("UNEXPLAINED" in p for p in result["problems"]))

    def test_a_record_falling_through_classification_is_refused(self):
        """36 + 1 + 0 + 0 != 38 — something was read and never bucketed."""
        result = check_cohort_integrity(
            self._turns(36), self._excluded(1), [], 0, 38, 38, 36)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any("fell through" in p for p in result["problems"]))

    def test_a_duplicate_turn_key_is_refused(self):
        """Same object, same record — but still not N distinct turns.

        Utterance and turn_key coming from one record removes the
        cross-source join problem. It does NOT prove the trace holds one
        unique record per intended turn, and this is the check that
        keeps those two claims separate.
        """
        turns = self._turns(2)
        turns[1]["_replay_turn_key"] = turns[0]["_replay_turn_key"]
        result = check_cohort_integrity(turns, [], [], 0, 2, 2, 2)
        self.assertFalse(result["ok"])

    def test_malformed_lines_are_refused(self):
        result = check_cohort_integrity(
            self._turns(36), self._excluded(2), [], 1, 39, 39, 36)
        self.assertFalse(result["ok"])

    def test_a_record_count_mismatch_is_refused(self):
        """Counted directly, not derived, so it can actually disagree."""
        result = check_cohort_integrity(
            self._turns(36), self._excluded(2), [], 0, 41, 38, 36)
        self.assertFalse(result["ok"])


class EntryPointRefusesAndWritesNothingTests(unittest.TestCase):
    """The regression that matters: exit code AND no report on disk."""

    def test_zero_recoverable_turns_exits_nonzero_and_writes_no_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Records carrying no narrator_input anywhere — the shape
            # that used to produce a clean zeroed report and exit 0.
            path = _write_trace(tmp, [
                {"trace_id": f"t{i}", "turn_key": f"turnrow:{i}",
                 "context": {"stages": []}}
                for i in range(38)
            ])
            out = Path(tmp) / "report.md"
            code = main([
                "--trace", str(path),
                "--out", str(out),
                "--expect-records", "38",
                "--expect-applicable", "38",
            ])
            self.assertNotEqual(
                code, 0,
                "a replay that recovered no narrator utterance reported "
                "success")
            self.assertFalse(
                out.exists(),
                "a refused replay still wrote a success-style report")

    def test_a_short_cohort_exits_nonzero_and_writes_no_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_trace(tmp, [
                _record(f"turnrow:{i}", f"Utterance {i} in Lowell.")
                for i in range(3)
            ])
            out = Path(tmp) / "report.md"
            code = main([
                "--trace", str(path),
                "--out", str(out),
                "--expect-records", "38",
                "--expect-applicable", "38",
            ])
            self.assertNotEqual(code, 0)
            self.assertFalse(out.exists())

    def test_a_complete_cohort_writes_a_report_and_exits_zero(self):
        """The positive control.

        Without this the refusal tests could pass on an instrument that
        refuses everything, which measures nothing just as thoroughly.
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_trace(tmp, [
                _record("turnrow:1",
                        "I was born in West St. Paul, Minnesota in 1960."),
                _record("turnrow:2",
                        "The Saint Patrick's Day parade in Lowell was the "
                        "big one every year."),
                _record("turnrow:3",
                        "We drove from Bardstown to Mexico City that "
                        "spring, then home."),
                # Mirrors the two real cohort-C exclusions.
                _deterministic_record(
                    "t-det-1", "witness",
                    "Got it — Princeton Avenue. What happened next?"),
            ])
            out = Path(tmp) / "report.md"
            code = main([
                "--trace", str(path),
                "--out", str(out),
                "--expect-records", "4",
                "--expect-applicable", "3",
            ])
            self.assertEqual(code, 0)
            self.assertTrue(out.exists())
            body = out.read_text(encoding="utf-8")
            self.assertIn("trace records accounted for | 4", body)
            self.assertIn("generated turns replayed | 3", body)
            self.assertIn("deterministic, not applicable | 1", body)
            # The exclusion is named and justified, never silent.
            self.assertIn("effective_turn_mode=witness", body)
            # And it must actually have measured something: the repair
            # merges "West St" + "Paul" on turn 1.
            self.assertIn("West St. Paul", body)

    def test_the_report_names_a_trace_outside_the_repo(self):
        """The positive control runs from /tmp, which is legitimate.

        `Path.relative_to(REPO_ROOT)` raised ValueError on any trace
        outside the repository, so the instrument crashed on its own
        test fixture. The display path falls back to absolute now —
        refusing to name the file would make the report lie about what
        it read.
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_trace(tmp, [
                _record("turnrow:1", "We lived in West St. Paul."),
            ])
            out = Path(tmp) / "report.md"
            code = main([
                "--trace", str(path),
                "--out", str(out),
                "--expect-records", "1",
                "--expect-applicable", "1",
            ])
            self.assertEqual(code, 0)
            self.assertIn(str(path), out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
