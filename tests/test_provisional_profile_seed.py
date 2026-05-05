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

    def test_provisional_pending_suggestions_fill_empty_profile(self):
        """The Mary case: profile_json is empty, but pendingSuggestions
        from chat-extracted candidates have her identity. The bridge
        must surface those values."""
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

        self.assertEqual(seed.get("preferred_name"), "Mary")
        self.assertEqual(seed.get("full_name"), "Mary Holts")
        self.assertEqual(seed.get("childhood_home"), "Minot, North Dakota")
        # life_stage from 1940-02-29: 2026 - 1940 = 86 → "senior elder"
        self.assertEqual(seed.get("life_stage"), "senior elder")

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

    def test_partial_canonical_provisional_fills_gaps(self):
        """Canonical profile has fullName but no DOB/POB — provisional
        fills the missing ones. Mixed sources merge cleanly."""
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

        self.assertEqual(seed.get("full_name"), "Mary Holts")
        self.assertEqual(seed.get("childhood_home"), "Minot, North Dakota")
        self.assertEqual(seed.get("life_stage"), "senior elder")

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
        self.assertEqual(seed.get("life_stage"), "senior elder")

    # ── No person_id returns empty dict (existing behavior) ──────────

    def test_no_person_id_returns_empty(self):
        seed = _build_profile_seed(None)
        self.assertEqual(seed, {})
        seed = _build_profile_seed("")
        self.assertEqual(seed, {})


if __name__ == "__main__":
    unittest.main()
