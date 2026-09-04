"""Phase 2 verifier — fixture-based behavioural tests.

WHY FIXTURES AND NOT THE LIVE DB
================================
The live database is outside the repository (`DATA_DIR=/mnt/c/hornelore_data`)
and is not present in a clone, so a test that reads it would skip in CI and on
any reviewer's machine — which is exactly how a verifier comes to prove
nothing. These tests build synthetic turns and candidates in memory and
exercise the verifier's real functions against them.

WHAT THEY GUARD
===============
The first version of `phase2_verify_ledger.py` reproduced only candidate
counts and closed with "the bottleneck is REVIEW". It labelled a turn with no
candidate `archived_only`, did not compute the 18/20 classifier split, and did
not check the extraction ledger. The command advertised as reproducing the
Phase 2 audit therefore proved yesterday's conclusion rather than the audit's
own findings. These tests make that regression impossible.
"""
from __future__ import annotations

import importlib.util
import re
import sqlite3
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "phase2_verify_ledger.py"


def _load():
    spec = importlib.util.spec_from_file_location("phase2_verify_ledger", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


V = _load()

# Candidate tuple shape the verifier reads, from its own SELECT:
#   0 id · 1 source_user_turn_row_id · 2 transcript · 3 word_count
#   4 review_status · 5 era_candidates · 6 placement_source · 7 trigger_reason
def cand(cid, turn, transcript, status="unreviewed", trigger="chain_detection"):
    return (cid, turn, transcript, len(transcript.split()), status,
            "[]", "unknown", trigger, "cohort-x")


# Three anchor dimensions fire -> the deterministic borderline path.
# VERIFIED against the shipped trigger, not assumed: an earlier version of this
# fixture named a place, a person AND a year and still scored only 2 -- a bare
# year is not a TIME anchor, relative time ("when I was little") is. A fixture
# whose properties are asserted rather than measured tests nothing.
ANCHOR_RICH = ("I was born in Akron, Ohio. My father Harold worked at "
               "Firestone when I was little.")
# Place + person only, no third dimension -> deterministic path cannot fire.
CHAIN_ONLY = ("I went to Kent State for my education degree. Kent State was "
              "about an hour from home and my father drove me there.")


class TerminalStatusTests(unittest.TestCase):
    """A turn with no candidate is measurement_failed, NOT archived_only."""

    def test_no_candidate_is_measurement_failed(self):
        turns = {1: CHAIN_ONLY}
        rows = V.structural_rows(turns, [])
        self.assertEqual("measurement_failed", rows[0]["terminal_status"])

    def test_archived_only_is_never_used_for_a_missing_candidate(self):
        """`archived_only` asserts we know no representation exists. We do
        not know that: the factual-chain decision is persisted nowhere."""
        rows = V.structural_rows({1: CHAIN_ONLY, 2: ANCHOR_RICH}, [])
        self.assertNotIn("archived_only", [r["terminal_status"] for r in rows])

    def test_a_candidate_is_provisional_until_promoted(self):
        turns = {1: CHAIN_ONLY}
        rows = V.structural_rows(turns, [cand("c1", 1, CHAIN_ONLY)])
        self.assertEqual("story_candidate_provisional", rows[0]["terminal_status"])

    def test_a_promoted_candidate_is_memoir_eligible(self):
        turns = {1: CHAIN_ONLY}
        rows = V.structural_rows(turns, [cand("c1", 1, CHAIN_ONLY, status="promoted")])
        self.assertEqual("memoir_eligible", rows[0]["terminal_status"])
        self.assertTrue(rows[0]["memoir_reachable"])


class ClassifierSplitTests(unittest.TestCase):
    """The 18/20 split, computed by the SHIPPED trigger."""

    def test_anchor_rich_turns_are_deterministic(self):
        s = V.classifier_split({1: ANCHOR_RICH}, [cand("c1", 1, ANCHOR_RICH)])
        self.assertEqual([1], s["deterministic"])
        self.assertEqual([], s["chain_captured"])
        self.assertEqual([], s["chain_silent"])

    def test_a_captured_turn_the_trigger_cannot_reproduce_is_chain_dependent(self):
        s = V.classifier_split({2: CHAIN_ONLY}, [cand("c2", 2, CHAIN_ONLY)])
        self.assertEqual([], s["deterministic"])
        self.assertEqual([2], s["chain_captured"])

    def test_an_uncaptured_turn_the_trigger_cannot_reproduce_is_chain_SILENT(self):
        """The three real misses. The chain classifier declined and left no
        record, so the turn is unexplained rather than explained."""
        s = V.classifier_split({3: CHAIN_ONLY}, [])
        self.assertEqual([3], s["chain_silent"])

    def test_the_three_buckets_partition_every_turn(self):
        turns = {1: ANCHOR_RICH, 2: CHAIN_ONLY, 3: CHAIN_ONLY}
        s = V.classifier_split(turns, [cand("c2", 2, CHAIN_ONLY)])
        total = len(s["deterministic"]) + len(s["chain_captured"]) + len(s["chain_silent"])
        self.assertEqual(len(turns), total, "every turn lands in exactly one bucket")
        self.assertEqual([1], s["deterministic"])
        self.assertEqual([2], s["chain_captured"])
        self.assertEqual([3], s["chain_silent"])


class ExtractionLedgerTests(unittest.TestCase):
    """Phase 2 measured ZERO cohort rows; the verifier must check that."""

    def _con(self, keys):
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE turn_extraction_ledger (turn_key TEXT)")
        con.executemany("INSERT INTO turn_extraction_ledger VALUES (?)",
                        [(k,) for k in keys])
        return con

    def test_zero_when_the_ledger_holds_only_other_turns(self):
        con = self._con(["turnrow:1923", "turnrow:2063"])
        self.assertEqual(0, V.extraction_ledger_rows(con, [1846, 1864, 1870]))

    def test_counts_rows_that_do_belong_to_the_cohort(self):
        con = self._con(["turnrow:1846", "turnrow:1923", "turnrow:1864"])
        self.assertEqual(2, V.extraction_ledger_rows(con, [1846, 1864, 1870]))

    def test_an_empty_ledger_is_zero_not_an_error(self):
        self.assertEqual(0, V.extraction_ledger_rows(self._con([]), [1846]))


class VerdictContentTests(unittest.TestCase):
    """The script must report today's findings, not yesterday's."""

    def setUp(self):
        self.src = SCRIPT.read_text(encoding="utf-8")

    def test_the_stale_bottleneck_verdict_is_gone(self):
        """It closed with 'The bottleneck is REVIEW', which both predates the
        audit's real findings and reads as a mandate to work the queue."""
        self.assertNotIn("The bottleneck is REVIEW", self.src)
        self.assertIn("NOT a mandate to work the", self.src)

    def test_it_reports_the_classifier_split(self):
        for needle in ("CAPTURE DECISION SPLIT", "deterministic (anchors>=3",
                       "chain-dependent (NOT reproducible)",
                       "chain fired, candidate created", "chain silent, NO candidate"):
            self.assertIn(needle, self.src)

    def test_it_reports_the_extraction_ledger_count(self):
        self.assertIn("EXTRACTION LEDGER rows for cohort turns", self.src)
        self.assertIn("Phase 2 measured ZERO", self.src)

    def test_it_reports_measurement_failed_rather_than_not_story(self):
        self.assertIn("measurement_failed, NOT not_story", self.src)
        self.assertIn("no evidence-backed reason exists, so none is invented", self.src)

    def test_it_still_corrects_the_eleven(self):
        self.assertIn("NOT 11/38", self.src)
        self.assertIn("PATCH actions in the API log", self.src)

    def test_no_trailing_whitespace(self):
        bad = [i + 1 for i, line in enumerate(self.src.split("\n"))
               if re.search(r"[ \t]+$", line)]
        self.assertEqual([], bad, f"trailing whitespace on lines {bad}")


class ReadOnlyTests(unittest.TestCase):
    """The verifier must never write."""

    def test_it_opens_the_database_read_only(self):
        src = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('f"file:{p}?mode=ro"', src)
        for w in ("INSERT", "UPDATE", "DELETE", "DROP", "commit()"):
            self.assertNotIn(w, src, f"{w} must not appear in a read-only verifier")

    def test_it_resolves_the_db_from_env_not_a_guess(self):
        src = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("DATA_DIR", src)
        self.assertIn("DB_NAME", src)


if __name__ == "__main__":
    unittest.main()
