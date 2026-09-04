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

from .measured_fixture import (
    FixtureMeasurementError, measured, story_trigger_measure,
)

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


# FIXTURES DECLARE; THE SHIPPED TRIGGER DECIDES.
#
# An earlier version of ANCHOR_RICH named a place, a person AND a year, and a
# comment above it asserted "three anchors". It scored two: a bare year is not
# a TIME anchor -- story_trigger.py:706 measures RELATIVE time phrasing
# (_matches_relative_time), not absolute dates. Every test that depended on the
# deterministic path was therefore exercising the chain-dependent path, and
# passing. A comment cannot fail; a measurement can. So these declarations are
# re-derived from the shipped code at import, and a mismatch raises here rather
# than surfacing as a confusing failure somewhere downstream.
#
# See tests/measured_fixture.py for the full statement of the failure class.
ANCHOR_RICH = measured(
    "I was born in Akron, Ohio. My father Harold worked at "
    "Firestone when I was little.",
    name="ANCHOR_RICH", measure=story_trigger_measure,
    anchors=3, trigger="borderline_scene_anchor",
    place_anchor=True, time_anchor=True, person_anchor=True,
)
# Place + person only, no third dimension -> the deterministic path cannot
# fire, so a candidate bound to this text can only have come from the chain.
CHAIN_ONLY = measured(
    "I went to Kent State for my education degree. Kent State was "
    "about an hour from home and my father drove me there.",
    name="CHAIN_ONLY", measure=story_trigger_measure,
    anchors=2, trigger=None,
    place_anchor=True, time_anchor=False, person_anchor=True,
)


class MeasuredFixtureTests(unittest.TestCase):
    """The guard that would have caught the 2026-09-04 fixture error.

    These test the GUARD, not the fixtures -- the fixtures already prove
    themselves at import. If `measured()` ever stopped raising, every
    fixture in this file would silently go back to asserting.
    """

    def test_a_wrong_declaration_raises_and_names_both_values(self):
        """Note the shape of this test: it MEASURES first, then asserts the
        error reports that measurement. The first draft hardcoded 'measured
        2' and failed -- the text scores 1, because it names no person. The
        guard caught its own author writing down an anchor count instead of
        taking one, which is the entire failure class in miniature."""
        text = "I was born in Akron, Ohio in 1946."
        actual = story_trigger_measure(text)["anchors"]
        wrong = actual + 1
        with self.assertRaises(FixtureMeasurementError) as ctx:
            measured(text, name="BARE_YEAR", measure=story_trigger_measure,
                     anchors=wrong)
        msg = str(ctx.exception)
        self.assertIn(f"declared {wrong}", msg)
        self.assertIn(f"measured {actual}", msg)
        self.assertIn("BARE_YEAR", msg)

    def test_the_exact_original_mistake_is_caught(self):
        """Place + person + a BARE YEAR is two anchors, not three. This is
        verbatim the assumption that produced the defect."""
        m = story_trigger_measure(
            "I was born in Akron, Ohio in 1946. My father Harold worked "
            "at Firestone.")
        self.assertEqual(2, m["anchors"])
        self.assertFalse(m["time_anchor"], "a bare year is not a time anchor")
        self.assertIsNone(m["trigger"])

    def test_a_correct_declaration_returns_the_text_unchanged(self):
        t = "I was born in Akron, Ohio. My father Harold worked at Firestone."
        self.assertEqual(t, measured(t, name="OK",
                                     measure=story_trigger_measure,
                                     time_anchor=False))

    def test_declaring_nothing_is_refused(self):
        with self.assertRaises(FixtureMeasurementError):
            measured("text", name="EMPTY", measure=story_trigger_measure)

    def test_declaring_a_property_the_measure_does_not_compute_is_refused(self):
        with self.assertRaises(FixtureMeasurementError) as ctx:
            measured("text", name="TYPO", measure=story_trigger_measure,
                     anchor_count=3)
        self.assertIn("anchor_count", str(ctx.exception))


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


class LogCorroborationTests(unittest.TestCase):
    """The log is a SECOND source. Agreement with the DB-derived split is
    the only evidence that re-running today's classifier reproduces the
    live run; disagreement would mean the classifier has drifted."""

    COHORT = "cohort-r20260831-040506-010cd6"
    LINE = ("2026-08-30 22:06:54,757 [code.api.routers.chat_ws] INFO: "
            "[story-trigger] conv={c}-20342881 narrator=2034 "
            "trigger={t} words={w} anchors={a} place={p} time={ti} person={pe}")

    def _log(self, lines):
        import tempfile
        fh = tempfile.NamedTemporaryFile("w", suffix=".log", delete=False,
                                         encoding="utf-8")
        fh.write("\n".join(lines) + "\n")
        fh.close()
        self.addCleanup(lambda: Path(fh.name).unlink(missing_ok=True))
        return fh.name

    def test_it_counts_triggers_and_isolates_the_misses(self):
        p = self._log([
            self.LINE.format(c=self.COHORT, t="borderline_scene_anchor",
                             w=238, a=3, p=True, ti=True, pe=True),
            self.LINE.format(c=self.COHORT, t="chain_detection",
                             w=230, a=2, p=True, ti=True, pe=False),
            self.LINE.format(c=self.COHORT, t="None",
                             w=236, a=2, p=True, ti=False, pe=True),
        ])
        got = V.log_capture_decisions(p, self.COHORT)
        self.assertEqual({"borderline_scene_anchor": 1, "chain_detection": 1,
                          "None": 1}, got["triggers"])
        self.assertEqual(1, len(got["misses"]))
        self.assertFalse(got["misses"][0]["time"])
        self.assertEqual(2, got["misses"][0]["anchors"])

    def test_another_cohorts_lines_are_not_counted(self):
        p = self._log([self.LINE.format(c="cohort-SOMETHING-ELSE", t="None",
                                        w=1, a=0, p=False, ti=False, pe=False)])
        self.assertEqual({}, V.log_capture_decisions(p, self.COHORT))

    def test_a_missing_log_is_empty_not_an_error(self):
        """The log rotates and is gitignored. A reviewer without it must
        still get every DB-derived number rather than a crash."""
        self.assertEqual({}, V.log_capture_decisions("/nonexistent/api.log",
                                                     self.COHORT))
        self.assertEqual({}, V.log_extraction_skips("/nonexistent/api.log",
                                                    self.COHORT))

    def test_extraction_skip_reasons_are_tallied(self):
        line = ("2026-08-30 22:05:22,503 INFO: [extract-turn] skipped "
                "conv={c}-2b2b5220 — client did not declare "
                "field_extraction_result=v1; it owns extraction on this turn")
        p = self._log([line.format(c=self.COHORT)] * 3)
        got = V.log_extraction_skips(p, self.COHORT)
        self.assertEqual(1, len(got))
        self.assertEqual(3, next(iter(got.values())))
        self.assertIn("field_extraction_result=v1", next(iter(got)))


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
                       "chain fired, candidate created",
                       "trigger declined, NO candidate"):
            self.assertIn(needle, self.src)

    def test_it_reports_the_extraction_ledger_count(self):
        self.assertIn("EXTRACTION LEDGER rows for cohort turns", self.src)
        self.assertIn("Phase 2 measured ZERO", self.src)

    def test_it_no_longer_claims_the_decision_is_persisted_nowhere(self):
        """CORRECTED 2026-09-04. chat_ws.py:1848 logs every capture decision
        with its full anchor breakdown, so 'nobody can say why it decided as
        it did' was false.

        Scoped to the PRINTED lines, not the whole source. The claim being
        retired is a claim the script MAKES; the docstring that explains the
        retirement has to be free to quote it. A first draft stripped only
        `#` comments and failed on the docstring -- an assertion that
        matched the correction rather than the defect, which is the same
        self-matching mistake this file has now made five times."""
        printed = "\n".join(line for line in self.src.split("\n")
                            if line.lstrip().startswith("print("))
        self.assertNotIn("persisted NOWHERE", printed)
        self.assertNotIn("nobody can say why", printed)
        self.assertIn("THE DEFECT IS DURABILITY OF THE DECISION", printed)

    def test_it_separates_the_harness_gap_from_a_product_defect(self):
        """Zero ledger rows had one cause: the cohort runner never declared
        the capability, so the server declined by protocol. Reporting that
        as an extraction defect would send Phase 3 after a working path."""
        self.assertIn("HARNESS gap, not a product defect", self.src)
        self.assertIn("field_extraction_result=v1", self.src)

    def test_it_names_the_shared_signature_of_the_misses(self):
        self.assertIn("no RELATIVE time phrasing", self.src)
        self.assertIn("story_trigger.py:706", self.src)

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
