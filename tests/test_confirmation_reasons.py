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
