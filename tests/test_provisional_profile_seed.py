"""Tests for WO-PROVISIONAL-TRUTH-01 Phase A — _build_profile_seed read bridge.

The bridge: when profiles.profile_json is empty (or missing a field), values
should fall back to interview_projections.projection_json — both fields
(applied writes) and pendingSuggestions (queued candidates).

Closes the Mary-loses-identity-after-restart class observed in TEST-23 v1+v2.

Per the audit at docs/reports/PROVISIONAL_TRUTH_ARCHITECTURE_AUDIT_2026-05-04.md,
the storage layer was already correct (projection_json persists across
restart); only the read path needed the bridge.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Test runs from repo root; expose the server-side package.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVER_CODE = _REPO_ROOT / "server" / "code"
sys.path.insert(0, str(_SERVER_CODE))

from api.prompt_composer import _build_profile_seed  # noqa: E402


class BuildProfileSeedProvisionalTests(unittest.TestCase):
    """Phase A acceptance: verify the merge order between canonical
    profile_json and provisional projection_json is correct, and that
    each bucket falls back appropriately when canonical is empty."""

    PID = "test-pid-mary-holts"

    def _make_profile_blob(self, profile_data):
        """Wrap the test data the way db.get_profile() returns."""
        return {"profile_json": {"profile": profile_data}}

    def _make_projection_blob(self, fields=None, pending=None):
        """Wrap the test data the way db.get_projection() returns."""
        return {
            "projection": {
                "fields": fields or {},
                "pendingSuggestions": pending or [],
            }
        }

    # ── Empty-empty: returns empty dict ──────────────────────────────

    def test_empty_profile_empty_projection_returns_empty(self):
        with patch("api.db.get_profile") as mp, \
             patch("api.db.get_projection") as gp:
            mp.return_value = self._make_profile_blob({})
            gp.return_value = self._make_projection_blob()
            seed = _build_profile_seed(self.PID)
        self.assertEqual(seed, {})

    # ── Canonical-only: profile values populate; projection ignored ──

    def test_canonical_profile_populates_buckets(self):
        with patch("api.db.get_profile") as mp, \
             patch("api.db.get_projection") as gp:
            mp.return_value = self._make_profile_blob({
                "personal": {
                    "fullName": "Christopher Todd Horne",
                    "preferredName": "Christopher",
                    "placeOfBirth": "Bismarck, ND",
                    "dateOfBirth": "1962-12-24",
                    "culture": "Germans from Russia",
                },
                "education": {
                    "schooling": "Bismarck High School",
                    "higherEducation": "University of North Dakota",
                    "careerProgression": "software engineer",
                },
            })
            gp.return_value = self._make_projection_blob()
            seed = _build_profile_seed(self.PID)

        self.assertEqual(seed.get("preferred_name"), "Christopher")
        self.assertEqual(seed.get("full_name"), "Christopher Todd Horne")
        self.assertEqual(seed.get("childhood_home"), "Bismarck, ND")
        self.assertEqual(seed.get("heritage"), "Germans from Russia")
        self.assertIn("Bismarck High School", seed.get("education", ""))
        self.assertEqual(seed.get("career"), "software engineer")
        # life_stage is age-derived: 2026 - 1962 = 64 → "later career"
        self.assertEqual(seed.get("life_stage"), "later career")

    # ── Provisional-only: projection fills empty profile ─────────────

    def test_pending_suggestions_do_not_fill_the_seed_buckets(self):
        """THE CONTRACT CHANGED, and this test changed with it.

        It used to assert the opposite — that pendingSuggestions fill
        `preferred_name`, `full_name`, `childhood_home` and the age
        derivation. That was the read-bridge's original design (the
        "Mary case"), and it was wrong in a way that took a live trace to
        see: a chat-extracted CANDIDATE, which nobody has confirmed,
        became a value every downstream bucket treats as established
        biography. Lori would then state it back as fact.

        Measured live 2026-09-20: Christopher carries 15 pending
        suggestions and Kent 14, including `education.schooling` =
        "induction physical and testing in Fargo" — a machine's reading
        of a sentence, not something either man said about his schooling.

        So suggestions now stay in their own map and fill nothing. The
        one consumer entitled to see them is the confirmation hint, which
        asks whether they are right rather than asserting them, and it
        reads them BY NAME from `seed["suggested"]`.
        """
        with patch("api.db.get_profile") as mp, \
             patch("api.db.get_projection") as gp:
            mp.return_value = self._make_profile_blob({})
            gp.return_value = self._make_projection_blob(
                pending=[
                    {"fieldPath": "personal.fullName", "value": "Mary Holts",
                     "confidence": 0.92},
                    {"fieldPath": "personal.preferredName", "value": "Mary",
                     "confidence": 0.85},
                    {"fieldPath": "personal.dateOfBirth", "value": "1940-02-29",
                     "confidence": 0.95},
                    {"fieldPath": "personal.placeOfBirth", "value": "Minot, North Dakota",
                     "confidence": 0.80},
                ],
            )
            seed = _build_profile_seed(self.PID)

        # Nothing unconfirmed reaches a bucket.
        self.assertIsNone(seed.get("preferred_name"))
        self.assertIsNone(seed.get("full_name"))
        self.assertIsNone(seed.get("childhood_home"))
        # Including the derivations. An age computed from an unconfirmed
        # birth date is an unconfirmed age wearing an arithmetic result's
        # clothes, and it reads as far more solid than its input.
        self.assertIsNone(seed.get("life_stage"))
        self.assertIsNone(seed.get("age_years"))

        # They are carried, not discarded — dropping them would only move
        # the problem somewhere they get silently re-added.
        self.assertEqual(seed["suggested"]["personal.preferredName"], "Mary")
        self.assertEqual(seed["suggested"]["personal.fullName"], "Mary Holts")
        self.assertEqual(seed["suggested"]["personal.placeOfBirth"],
                         "Minot, North Dakota")

    def test_provisional_fields_fill_empty_profile(self):
        """Same as pendingSuggestions but data lives in projection.fields
        instead. Both surfaces are read."""
        with patch("api.db.get_profile") as mp, \
             patch("api.db.get_projection") as gp:
            mp.return_value = self._make_profile_blob({})
            gp.return_value = self._make_projection_blob(
                fields={
                    "personal.fullName": {
                        "value": "Marvin Mann",
                        "source": "backend_extract",
                        "confidence": 0.94,
                    },
                    "personal.dateOfBirth": {
                        "value": "1949-12-06",
                        "source": "backend_extract",
                        "confidence": 0.93,
                    },
                    "personal.placeOfBirth": {
                        "value": "Fargo, North Dakota",
                        "source": "backend_extract",
                        "confidence": 0.91,
                    },
                },
            )
            seed = _build_profile_seed(self.PID)

        self.assertEqual(seed.get("full_name"), "Marvin Mann")
        self.assertEqual(seed.get("childhood_home"), "Fargo, North Dakota")
        # 2026 - 1949 = 77 → "elder / retirement years"
        self.assertEqual(seed.get("life_stage"), "elder / retirement years")

    # ── Canonical wins when both present ─────────────────────────────

    def test_canonical_wins_over_provisional(self):
        """If profile_json has a value AND pendingSuggestions has a
        different one, canonical wins. Provisional only fills gaps."""
        with patch("api.db.get_profile") as mp, \
             patch("api.db.get_projection") as gp:
            mp.return_value = self._make_profile_blob({
                "personal": {
                    "fullName": "Christopher Todd Horne",
                    "placeOfBirth": "Bismarck, ND",
                },
            })
            gp.return_value = self._make_projection_blob(
                pending=[
                    # These should be IGNORED — canonical wins
                    {"fieldPath": "personal.fullName", "value": "Wrong Name"},
                    {"fieldPath": "personal.placeOfBirth", "value": "Wrong City"},
                ],
            )
            seed = _build_profile_seed(self.PID)

        self.assertEqual(seed.get("full_name"), "Christopher Todd Horne")
        self.assertEqual(seed.get("childhood_home"), "Bismarck, ND")

    # ── Gap-filling: canonical has some, provisional fills rest ─────

    def test_canonical_stands_and_suggestions_do_not_fill_its_gaps(self):
        """A gap is not an invitation.

        This also used to assert the opposite. The appeal of gap-filling
        is obvious — the bucket is empty and something is available — but
        "empty" and "we have a guess" are different states, and the seed
        has no way to mark the second once it has written it into the
        first. An empty bucket makes Lori ask. A filled one makes her
        assert. Asking is the recoverable error.
        """
        with patch("api.db.get_profile") as mp, \
             patch("api.db.get_projection") as gp:
            mp.return_value = self._make_profile_blob({
                "personal": {
                    "fullName": "Mary Holts",  # canonical
                },
            })
            gp.return_value = self._make_projection_blob(
                pending=[
                    {"fieldPath": "personal.dateOfBirth", "value": "1940-02-29"},
                    {"fieldPath": "personal.placeOfBirth", "value": "Minot, North Dakota"},
                ],
            )
            seed = _build_profile_seed(self.PID)

        # The canonical value is unaffected — this change narrows what
        # suggestions can do, and touches nothing that was confirmed.
        self.assertEqual(seed.get("full_name"), "Mary Holts")
        self.assertIsNone(seed.get("childhood_home"))
        self.assertIsNone(seed.get("life_stage"))
        self.assertEqual(seed["suggested"]["personal.placeOfBirth"],
                         "Minot, North Dakota")

    # ── Fields take priority over pendingSuggestions ─────────────────

    def test_projection_fields_priority_over_pending_suggestions(self):
        """If both projection.fields[X] and pendingSuggestions[X] exist
        for the same path, fields wins (it's a more committed write)."""
        with patch("api.db.get_profile") as mp, \
             patch("api.db.get_projection") as gp:
            mp.return_value = self._make_profile_blob({})
            gp.return_value = self._make_projection_blob(
                fields={
                    "personal.fullName": {"value": "Name From Field"},
                },
                pending=[
                    {"fieldPath": "personal.fullName", "value": "Name From Suggestion"},
                ],
            )
            seed = _build_profile_seed(self.PID)

        self.assertEqual(seed.get("full_name"), "Name From Field")

    # ── Defensive: handles missing/malformed projection data ─────────

    def test_missing_projection_does_not_break_canonical(self):
        """When get_projection raises or returns garbage, canonical
        results still surface and we don't crash."""
        with patch("api.db.get_profile") as mp, \
             patch("api.db.get_projection", side_effect=RuntimeError("DB down")):
            mp.return_value = self._make_profile_blob({
                "personal": {"fullName": "Test User"},
            })
            seed = _build_profile_seed(self.PID)

        self.assertEqual(seed.get("full_name"), "Test User")

    def test_malformed_projection_skipped(self):
        """projection_json with non-dict fields or non-list pending
        suggestions gets ignored without crashing."""
        with patch("api.db.get_profile") as mp, \
             patch("api.db.get_projection") as gp:
            mp.return_value = self._make_profile_blob({})
            gp.return_value = {
                "projection": {
                    "fields": "not-a-dict",          # malformed
                    "pendingSuggestions": "not-a-list",  # malformed
                }
            }
            seed = _build_profile_seed(self.PID)
        self.assertEqual(seed, {})

    def test_empty_string_provisional_values_skipped(self):
        """Suggestions with empty string values are filtered out (don't
        accidentally fill buckets with empties)."""
        with patch("api.db.get_profile") as mp, \
             patch("api.db.get_projection") as gp:
            mp.return_value = self._make_profile_blob({})
            gp.return_value = self._make_projection_blob(
                pending=[
                    {"fieldPath": "personal.fullName", "value": ""},
                    {"fieldPath": "personal.placeOfBirth", "value": "   "},
                    # Only this one is real
                    {"fieldPath": "personal.dateOfBirth", "value": "1940-02-29"},
                ],
            )
            seed = _build_profile_seed(self.PID)
        self.assertNotIn("full_name", seed)
        self.assertNotIn("childhood_home", seed)
        # No bucket, and no age derived from an unconfirmed birth date.
        self.assertIsNone(seed.get("life_stage"))
        # A blank suggestion is not carried either: it is not a value
        # anyone could be asked to confirm.
        self.assertNotIn("personal.fullName", seed.get("suggested") or {})
        self.assertNotIn("personal.placeOfBirth", seed.get("suggested") or {})
        self.assertEqual((seed.get("suggested") or {}).get("personal.dateOfBirth"),
                         "1940-02-29")

    # ── WO-03A B6 — the confirmation hint gets its input back ────────

    def test_suggestions_are_returned_for_the_confirmation_hint(self):
        """The repair this work order owed.

        `suggested` was built and never returned — collected, then
        dropped on the floor. That was my own defect, introduced when I
        stopped merging suggestions into `provisional`. Removing the
        merge was right; leaving the map unreturned took away the input
        of the one consumer that legitimately needs it, so Lori went back
        to asking cold about things the narrator had already told her.
        """
        with patch("api.db.get_profile") as mp, \
             patch("api.db.get_projection") as gp:
            mp.return_value = self._make_profile_blob({})
            gp.return_value = self._make_projection_blob(
                pending=[{"fieldPath": "personal.placeOfBirth",
                          "value": "Minot, North Dakota"}],
            )
            seed = _build_profile_seed(self.PID)

        self.assertIn("suggested", seed)
        self.assertEqual(seed["suggested"]["personal.placeOfBirth"],
                         "Minot, North Dakota")
        # Under its own key, so a consumer has to ask for it by name and
        # no bucket resolution can acquire one by accident.
        self.assertIsNone(seed.get("childhood_home"))

    def test_no_suggestions_means_no_key_rather_than_an_empty_one(self):
        """An empty map would read as "we looked and there are none",
        which is a claim. Absence is the honest shape."""
        with patch("api.db.get_profile") as mp, \
             patch("api.db.get_projection") as gp:
            mp.return_value = self._make_profile_blob(
                {"personal": {"fullName": "Mary Holts"}})
            gp.return_value = self._make_projection_blob(pending=[])
            seed = _build_profile_seed(self.PID)
        self.assertNotIn("suggested", seed)

    # ── No person_id returns empty dict (existing behavior) ──────────

    def test_no_person_id_returns_empty(self):
        seed = _build_profile_seed(None)
        self.assertEqual(seed, {})
        seed = _build_profile_seed("")
        self.assertEqual(seed, {})


if __name__ == "__main__":
    unittest.main()
