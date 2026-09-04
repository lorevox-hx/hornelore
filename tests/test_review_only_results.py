"""Review-only extraction results must travel end to end.

WO-LORI-ARCHIVE-TO-MEMOIR-02 Phase 3 (2026-09-04).

A turn can preserve MEANING without producing an executable item: the
extractor finds a name and cannot establish the relationship, so there is
something to review and nothing to apply. Three separate places treated that
as "found nothing" and dropped it silently:

  1. `_store_result`  -- `if not items: return`, so nothing was persisted.
  2. `extract_completed_turn` -- `if not items:` closed the ledger `noop`.
  3. the browser -- acknowledged and discarded a `succeeded` frame with
     `items=[]` before its handler ever ran.

For a quarantined relationship that is the worst available outcome: the whole
feature exists so uncertain meaning SURVIVES instead of being guessed at.

NO NEW STATUS AND NO MIGRATION. The durable distinction is the pair:

    succeeded, item_count > 0                    executable items
    succeeded, item_count == 0, review_count > 0 review-only, preserved
    noop,      both zero                         measured absent
    failed                                       measurement failed
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "server" / "code") not in sys.path:
    sys.path.insert(0, str(ROOT / "server" / "code"))

from api.services import turn_extraction as TE  # noqa: E402

# The shape the rebuilt kinship guard will emit. No executable fieldPath:
# `proposed_fieldPath` is diagnostic evidence, never a destination.
QUARANTINE = {
    "kind": "unbound_relationship",
    "value": "Otis",
    "label": "Otis's relationship to you",
    "proposed_fieldPath": "parents.firstName",
    "repeatableGroup": "parents_0",
    "reasons": ["identity_conflict", "relationship_unstated"],
    "reason": "identity_conflict",
    "not_applied": True,
}


class StoreAcceptsReviewOnly(unittest.TestCase):

    def _claim(self):
        # Field list read from the dataclass, not guessed.
        return TE._Claim(ledger_id=7, started=0.0, narrator_id="n1",
                         turn_id="t1", turn_key="turnrow:2", session_id="s1",
                         turn_mode="interview", source="chat_ws", user_text="x")

    def test_a_review_only_result_is_stored(self):
        with mock.patch("api.db.turn_extraction_result_store") as store:
            TE._store_result(self._claim(), [], [QUARANTINE], "llm")
        store.assert_called_once()
        kw = store.call_args.kwargs
        self.assertEqual([], kw["items"])
        self.assertEqual([QUARANTINE], kw["clarification_required"])
        self.assertEqual("succeeded", kw["status"],
                         "the row must be succeeded; noop would assert the "
                         "narrator's information was absent")

    def test_a_genuinely_empty_result_is_still_not_stored(self):
        with mock.patch("api.db.turn_extraction_result_store") as store:
            TE._store_result(self._claim(), [], [], "llm")
        store.assert_not_called()

    def test_items_only_is_unchanged(self):
        with mock.patch("api.db.turn_extraction_result_store") as store:
            TE._store_result(self._claim(), [{"fieldPath": "a.b", "value": "v"}],
                             [], "llm")
        store.assert_called_once()


class OutcomeCarriesReviewCount(unittest.TestCase):

    def test_review_count_defaults_to_zero_and_is_logged(self):
        out = TE.ExtractionOutcome(status="succeeded", turn_key="k")
        self.assertEqual(0, out.review_count)
        self.assertIn("review=0", out.as_log_fields())

    def test_the_four_way_distinction_is_expressible(self):
        exec_only = TE.ExtractionOutcome(status="succeeded", item_count=3)
        review_only = TE.ExtractionOutcome(status="succeeded", item_count=0,
                                           review_count=1)
        absent = TE.ExtractionOutcome(status="noop")
        failed = TE.ExtractionOutcome(status="failed")
        self.assertTrue(exec_only.item_count and not exec_only.review_count)
        self.assertTrue(not review_only.item_count and review_only.review_count,
                        "review-only must be distinguishable from measured absent")
        self.assertEqual(("noop", 0, 0),
                         (absent.status, absent.item_count, absent.review_count))
        self.assertFalse(failed.ok)
        self.assertTrue(review_only.ok)


class TraceDoesNotClaimAbsence(unittest.TestCase):
    """`measured_absent` asserts the narrator's information was not there.
    For a review-only turn it was there, and was deliberately withheld from
    automatic application. That is the opposite claim."""

    def _result_for(self, **kw):
        rt = mock.MagicMock()
        rt.RESULT_PERSISTED = "persisted"
        rt.RESULT_MEASURED_ABSENT = "measured_absent"
        rt.RESULT_MEASUREMENT_FAILED = "measurement_failed"
        with mock.patch.object(TE, "_rt", rt):
            TE._finalize_extraction_trace("turnrow:2", **kw)
        return rt.attach.call_args.args[2] if rt.attach.called else None

    def test_review_only_is_persisted_not_absent(self):
        self.assertEqual("persisted",
                         self._result_for(status="succeeded", item_count=0,
                                          review_count=1))

    def test_items_only_is_still_persisted(self):
        self.assertEqual("persisted",
                         self._result_for(status="succeeded", item_count=2))

    def test_a_true_noop_is_still_measured_absent(self):
        self.assertEqual("measured_absent",
                         self._result_for(status="noop", item_count=0,
                                          review_count=0))

    def test_failure_is_still_measurement_failed(self):
        self.assertEqual("measurement_failed",
                         self._result_for(status="failed", item_count=0,
                                          review_count=0))


class TheBranchThatDecides(unittest.TestCase):
    """`_complete_claim_inner` chooses noop vs succeeded. Driven END TO END,
    because testing `_store_result` and the trace separately left the decision
    itself uncovered — mutating `if not items and not _clar:` back to
    `if not items:` kept every other test in this file green.
    """

    class _Resp:
        def __init__(self, items, clar):
            self.items = items
            self.clarification_required = clar
            self.method = "llm"

    def _run(self, resp):
        import asyncio
        claim = TE._Claim(ledger_id=11, started=0.0, narrator_id="n1",
                          turn_id="t1", turn_key="turnrow:2", session_id="s1",
                          turn_mode="interview", source="chat_ws",
                          user_text="Otis died in 2005.")
        calls = {}
        with mock.patch.object(TE, "_call_extractor", return_value=resp), \
             mock.patch.object(TE, "_store_result") as store, \
             mock.patch.object(TE, "_finish_ledger") as fin, \
             mock.patch.object(TE, "_offer_result",
                               new=mock.AsyncMock(return_value=None)):
            out = asyncio.run(TE._complete_claim_inner(claim))
        calls["store"], calls["fin"] = store, fin
        return out, calls

    def test_review_only_is_succeeded_and_stored_not_a_noop(self):
        out, c = self._run(self._Resp([], [QUARANTINE]))
        self.assertEqual("succeeded", out.status,
                         "a preserved meaning was classified as 'found nothing'")
        self.assertEqual(0, out.item_count)
        self.assertEqual(1, out.review_count)
        c["store"].assert_called_once()
        self.assertEqual([], c["store"].call_args.args[1])
        self.assertEqual([QUARANTINE], c["store"].call_args.args[2])
        self.assertEqual("succeeded", c["fin"].call_args.args[1],
                         "the ledger must close succeeded, not noop")

    def test_a_genuine_empty_result_is_still_a_noop(self):
        out, c = self._run(self._Resp([], []))
        self.assertEqual("noop", out.status)
        self.assertEqual(0, out.review_count)
        c["store"].assert_not_called()
        self.assertEqual("noop", c["fin"].call_args.args[1])

    def test_items_plus_review_reports_both_counts(self):
        out, _ = self._run(self._Resp(
            [{"fieldPath": "personal.notes", "value": "v"}], [QUARANTINE]))
        self.assertEqual("succeeded", out.status)
        self.assertEqual(1, out.item_count)
        self.assertEqual(1, out.review_count)


class NoFamilyTruthWrite(unittest.TestCase):
    """The accepted boundary: this service never writes family truth, and a
    review carrier must not become the exception that does."""

    def test_the_service_still_calls_no_family_truth_writer(self):
        src = (ROOT / "server" / "code" / "api" / "services"
               / "turn_extraction.py").read_text(encoding="utf-8")
        code = "\n".join(ln for ln in src.split("\n")
                         if not ln.lstrip().startswith("#"))
        for forbidden in ("ft_add_note", "ft_add_row", "apply_correction"):
            self.assertNotIn(forbidden + "(", code)


if __name__ == "__main__":
    unittest.main()
