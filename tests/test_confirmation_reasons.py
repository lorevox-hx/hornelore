"""Additive multi-reason confirmation — ordered, deduplicated, lossless.

WO-LORI-ARCHIVE-TO-MEMOIR-02 Phase 3 (2026-09-04).

`confirmation_reason` was a single string, so two guards doubting one item
erased each other's explanation. `confirmation_reasons` is added ALONGSIDE it;
the scalar is retained and holds the MOST SEVERE reason, so existing consumers
keep working unchanged while updated ones read the list and fall back.

Order is a DOCUMENTED PRECEDENCE, never append order. Append order would make
the API result depend on guard execution order: a refactor that reorders two
guards would flip the legacy scalar and churn the UI without changing a single
fact. The order is presentational — it selects the scalar and the render
sequence. It never decides write authority; anything needing confirmation is
already pinned to `suggest_only` before these run.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "server" / "code") not in sys.path:
    sys.path.insert(0, str(ROOT / "server" / "code"))

from api.routers import extract as EX  # noqa: E402

SEVERE, BIND, LOWCONF, FRAGILE = (
    "identity_conflict", "relationship_unstated", "low_confidence", "fragile_field")


def item(**kw):
    kw.setdefault("fieldPath", "parents.firstName")
    kw.setdefault("value", "Otis")
    kw.setdefault("writeMode", "suggest_only")
    kw.setdefault("confidence", 0.5)
    return EX.ExtractedItem(**kw)


class Precedence(unittest.TestCase):

    def test_the_documented_order_is_the_shipped_order(self):
        self.assertEqual((SEVERE, BIND, LOWCONF, FRAGILE),
                         EX.CONFIRMATION_REASON_PRECEDENCE)

    def test_order_is_independent_of_the_order_guards_fire(self):
        """THE POINT OF PRECEDENCE. Two guards, either sequence, one output."""
        a, b = item(), item()
        EX._add_confirmation_reason(a, FRAGILE)
        EX._add_confirmation_reason(a, SEVERE)
        EX._add_confirmation_reason(b, SEVERE)
        EX._add_confirmation_reason(b, FRAGILE)
        self.assertEqual(a.confirmation_reasons, b.confirmation_reasons)
        self.assertEqual(a.confirmation_reason, b.confirmation_reason)

    def test_unknown_tags_sort_after_known_ones_deterministically(self):
        it = item()
        for r in ("zz_future", LOWCONF, "aa_future", SEVERE):
            EX._add_confirmation_reason(it, r)
        self.assertEqual([SEVERE, LOWCONF, "aa_future", "zz_future"],
                         it.confirmation_reasons)
        self.assertEqual(SEVERE, it.confirmation_reason,
                         "a future tag must never take the scalar")

    def test_duplicates_are_collapsed(self):
        it = item()
        for _ in range(3):
            EX._add_confirmation_reason(it, LOWCONF)
        self.assertEqual([LOWCONF], it.confirmation_reasons)

    def test_nothing_is_erased_when_a_second_guard_fires(self):
        it = item()
        EX._add_confirmation_reason(it, LOWCONF)
        EX._add_confirmation_reason(it, BIND)
        self.assertEqual([BIND, LOWCONF], it.confirmation_reasons)
        self.assertEqual(BIND, it.confirmation_reason)

    def test_the_scalar_is_the_most_severe_not_the_first(self):
        it = item()
        EX._add_confirmation_reason(it, FRAGILE)
        self.assertEqual(FRAGILE, it.confirmation_reason)
        EX._add_confirmation_reason(it, SEVERE)
        self.assertEqual(SEVERE, it.confirmation_reason,
                         "least-severe scalar retained — older consumers would "
                         "see the mildest of two warnings")

    def test_one_helper_serves_items_and_envelope_entries(self):
        entry = {"fieldPath": "parents.firstName", "value": "Otis"}
        EX._add_confirmation_reason(entry, FRAGILE)
        EX._add_confirmation_reason(entry, LOWCONF)
        self.assertEqual([LOWCONF, FRAGILE], entry["reasons"])
        self.assertEqual(LOWCONF, entry["reason"],
                         "envelope keeps its legacy scalar key")


class LegacyScalarIsNeverLost(unittest.TestCase):
    """Gap found in review, 2026-09-04.

    The helper read only the list. An object carrying its single reason in the
    SCALAR -- one that predates the list, or whose scalar was set directly --
    lost it the moment a second guard fired. That is the same information loss
    the whole change exists to stop, reintroduced one layer down.
    """

    def test_a_scalar_only_item_keeps_its_reason(self):
        it = item()
        it.confirmation_reason = LOWCONF          # list left empty, as legacy
        EX._add_confirmation_reason(it, FRAGILE)
        self.assertEqual([LOWCONF, FRAGILE], it.confirmation_reasons)
        self.assertEqual(LOWCONF, it.confirmation_reason)

    def test_a_scalar_only_envelope_entry_keeps_its_reason(self):
        entry = {"fieldPath": "parents.firstName", "reason": LOWCONF}
        EX._add_confirmation_reason(entry, FRAGILE)
        self.assertEqual([LOWCONF, FRAGILE], entry["reasons"])
        self.assertEqual(LOWCONF, entry["reason"])

    def test_seeding_does_not_duplicate_when_scalar_matches(self):
        it = item()
        it.confirmation_reason = LOWCONF
        EX._add_confirmation_reason(it, LOWCONF)
        self.assertEqual([LOWCONF], it.confirmation_reasons)

    def test_an_unknown_tag_alone_may_hold_the_scalar(self):
        """The docstring once claimed unknown tags never reach the scalar.
        They cannot DISPLACE a known one, but with nothing else present the
        alternative is an empty scalar beside a populated list."""
        it = item()
        EX._add_confirmation_reason(it, "zz_future")
        self.assertEqual("zz_future", it.confirmation_reason)
        EX._add_confirmation_reason(it, FRAGILE)
        self.assertEqual(FRAGILE, it.confirmation_reason,
                         "a known tag must take the scalar back")


class EnvelopeMirrorsTheItem(unittest.TestCase):
    """Gap found in review: transcript safety built its envelope entry from
    the reason it had just added, so a reason another guard put on the item
    never reached the operator's clarification list."""

    def test_the_envelope_shows_every_reason_the_item_carries(self):
        """Through the REAL transcript-safety pass, with a reason already on
        the item — the shape a second guard produces.

        The first version of this test called _sync_confirmation_reasons on a
        hand-built dict, so mutating the production call back to
        `_add_confirmation_reason(_entry, reason)` left it green. A test that
        cannot fail when the product breaks is not a test; mutation checking is
        the only reason that was caught."""
        it = item(writeMode="candidate_only")
        EX._add_confirmation_reason(it, BIND)       # an earlier guard's verdict
        req = EX.ExtractFieldsRequest(
            person_id="p", answer="x", transcript_source="whisper",
            transcript_confidence=0.42, confirmation_required=True)

        items, clar = EX._apply_transcript_safety_layer([it], req)

        self.assertEqual([BIND, LOWCONF], items[0].confirmation_reasons)
        self.assertEqual(1, len(clar))
        self.assertEqual([BIND, LOWCONF], clar[0]["reasons"],
                         "the envelope dropped a reason the item carried")
        self.assertEqual(BIND, clar[0]["reason"],
                         "legacy scalar must be the most severe of BOTH")

    def test_sync_reorders_defensively(self):
        entry = {}
        EX._sync_confirmation_reasons(entry, [FRAGILE, SEVERE, LOWCONF])
        self.assertEqual([SEVERE, LOWCONF, FRAGILE], entry["reasons"])
        self.assertEqual(SEVERE, entry["reason"],
                         "an unordered caller must not choose the scalar")

    def test_sync_with_no_reasons_clears_both(self):
        entry = {"reasons": [FRAGILE], "reason": FRAGILE}
        EX._sync_confirmation_reasons(entry, [])
        self.assertEqual([], entry["reasons"])
        self.assertIsNone(entry["reason"])


class BackwardCompatibility(unittest.TestCase):
    """Exact, per the contract: single-reason output is unchanged."""

    def _resp(self, conf):
        req = EX.ExtractFieldsRequest(
            person_id="p", answer="My father Clarence Hudson worked there.",
            current_section="early_caregivers",
            current_target_path="parents.firstName",
            transcript_source="whisper", transcript_confidence=conf,
            confirmation_required=True)
        with mock.patch.object(EX, "_extract_via_llm", return_value=(
                [{"fieldPath": "parents.firstName", "value": "Clarence",
                  "confidence": 0.9}], "[stub]")):
            return EX.run_field_extraction(req)

    def test_low_confidence_still_emits_the_same_scalar(self):
        r = self._resp(0.42)
        it = [i for i in r.items if i.fieldPath == "parents.firstName"][0]
        self.assertEqual("low_confidence", it.confirmation_reason)
        self.assertEqual(["low_confidence"], it.confirmation_reasons)
        self.assertEqual("low_confidence", r.clarification_required[0]["reason"])
        self.assertEqual(["low_confidence"], r.clarification_required[0]["reasons"])

    def test_fragile_field_still_emits_the_same_scalar(self):
        r = self._resp(0.95)
        it = [i for i in r.items if i.fieldPath == "parents.firstName"][0]
        self.assertEqual("fragile_field", it.confirmation_reason)
        self.assertEqual(["fragile_field"], it.confirmation_reasons)
        self.assertEqual("fragile_field", r.clarification_required[0]["reason"])

    def test_the_list_survives_serialization_to_storage_and_the_socket(self):
        """turn_extraction and chat_ws persist and deliver via model_dump();
        a field the dump omits reaches neither the ledger nor the browser."""
        r = self._resp(0.42)
        dumped = [i.model_dump() for i in r.items]
        target = [d for d in dumped if d["fieldPath"] == "parents.firstName"][0]
        self.assertIn("confirmation_reasons", target)
        self.assertEqual(["low_confidence"], target["confirmation_reasons"])
        self.assertEqual("low_confidence", target["confirmation_reason"])

    def test_an_untouched_item_carries_an_empty_list_not_none(self):
        r = self._resp(0.42)
        clean = [i for i in r.items if i.fieldPath != "parents.firstName"]
        for i in clean:
            self.assertEqual([], i.confirmation_reasons)
            self.assertIsNone(i.confirmation_reason)

    def test_the_scalar_field_is_still_a_string(self):
        """Changing the scalar to a list would break every existing reader."""
        ann = EX.ExtractedItem.model_fields["confirmation_reason"].annotation
        self.assertIn("str", str(ann))
        self.assertNotIn("List", str(ann))


if __name__ == "__main__":
    unittest.main()
