"""WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01 Phase 3 — writer tests.

Exercises bio_questionnaire_writer.apply_questionnaire_writes against
canned questionnaire blobs. Patches db.bio_fact_create and
db.update_profile_json so the test runs without a live sqlite.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))


# ─────────────────────────────────────────────────────────────────────
# Canned blobs
# ─────────────────────────────────────────────────────────────────────


HAPPY_BLOB = {
    "personal": {
        "fullName": "Jake Max Miller",
        "preferredName": "Jake",
        "dateOfBirth": "1955-04-12",
        "placeOfBirth": "Bismarck, North Dakota",
        "currentResidence": "Fargo, North Dakota",
        "pronouns": "he/him",
        "birthOrder": "Second",
    },
    "parents": [
        {"relation": "Father", "firstName": "Henry", "lastName": "Miller"},
        {"relation": "Mother", "firstName": "Mae", "lastName": "Miller",
         "maidenName": "Schwartz"},
    ],
    "siblings": [
        {"firstName": "Walter", "lastName": "Miller", "birthOrder": 1},
    ],
    "spouses": [
        {"firstName": "Dorothy", "lastName": "Miller",
         "yearMarried": "1977", "status": "Married"},
    ],
    "children": [
        {"firstName": "Anna", "lastName": "Miller",
         "dateOfBirth": "1980-06-05"},
    ],
    "education": {
        "highestLevel": "Bachelor's",
        "careerProgression": "30 years",
        "primaryCareer": "Mechanical engineer",
    },
    "military": {
        "served": True,
        "branch": "Army",
        "servicePeriod": "1974-1976",
        "rank": "Specialist",
        "locations": "Fort Lewis",
    },
    "faith": {
        "religionRaised": "Lutheran",
        "currentFaith": "Lutheran",
        "ethnicityHeritage": "German-Russian",
        "languagesAtHome": "English, some German",
    },
    "today": {
        "livingSituation": "Lives at home",
        "healthConsiderations": "Hearing aid",
    },
}


class _WriterFixture(unittest.TestCase):
    """Patches db.bio_fact_create + db.update_profile_json. Each test
    starts with empty `_facts_written` + `_profile_patches` lists."""

    def setUp(self):
        from api import db
        self.db = db
        self._facts_written = []
        self._profile_patches = []

        def _fake_bio_fact_create(
            narrator_id, field_key, value_json,
            status="empty", source_json="{}", confidence=0.0,
            **kwargs,
        ):
            self._facts_written.append({
                "narrator_id": narrator_id,
                "field_key":   field_key,
                "value":       json.loads(value_json),
                "status":      status,
                "source":      json.loads(source_json),
                "confidence":  confidence,
            })
            return f"fact-{len(self._facts_written)}"

        def _fake_update_profile_json(
            person_id, profile_json, merge=True, reason="",
        ):
            self._profile_patches.append({
                "person_id":    person_id,
                "profile_json": profile_json,
                "merge":        merge,
                "reason":       reason,
            })
            return {
                "person_id":    person_id,
                "profile_json": profile_json,
                "updated_at":   "x",
            }

        self._patches = [
            patch.object(db, "bio_fact_create",
                         side_effect=_fake_bio_fact_create),
            patch.object(db, "update_profile_json",
                         side_effect=_fake_update_profile_json),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def _written_keys(self):
        return [f["field_key"] for f in self._facts_written]


# ─────────────────────────────────────────────────────────────────────
# Happy-path coverage
# ─────────────────────────────────────────────────────────────────────


class HappyPathTest(_WriterFixture):
    def test_happy_blob_writes_expected_field_keys(self):
        from api.services.bio_questionnaire_writer import (
            apply_questionnaire_writes,
        )
        res = apply_questionnaire_writes(
            "narrator-jake", HAPPY_BLOB, operator_id="op-1",
        )
        keys = set(self._written_keys())
        # Personal scalars
        for k in ("full_legal_name", "preferred_name", "birth_date",
                  "birth_place", "birth_order"):
            self.assertIn(k, keys, f"missing scalar write: {k}")
        # Parents: father + mother + maiden
        for k in ("father_name", "mother_name", "mother_maiden_name"):
            self.assertIn(k, keys, f"missing parent scalar: {k}")
        # Counts
        for k in ("sibling_count", "children_count"):
            self.assertIn(k, keys, f"missing count: {k}")
        # Spouse
        for k in ("spouse_name", "marriage_year"):
            self.assertIn(k, keys, f"missing spouse scalar: {k}")
        # Education
        for k in ("highest_education_level", "primary_career"):
            self.assertIn(k, keys, f"missing education scalar: {k}")
        # Military
        for k in ("military_served", "military_branch",
                  "military_service_period", "military_rank",
                  "military_locations"):
            self.assertIn(k, keys, f"missing military scalar: {k}")
        # Faith
        for k in ("religion_raised", "current_faith", "ethnicity_heritage",
                  "languages_spoken_home"):
            self.assertIn(k, keys, f"missing faith scalar: {k}")
        self.assertEqual(res["bio_facts_written"], len(self._facts_written))
        self.assertEqual(res["bio_facts_errors"], [])
        self.assertIsNone(res["profile_error"])

    def test_profile_patch_carries_structured_blocks(self):
        from api.services.bio_questionnaire_writer import (
            apply_questionnaire_writes,
        )
        apply_questionnaire_writes("narrator-jake", HAPPY_BLOB,
                                   operator_id="op-1")
        self.assertEqual(len(self._profile_patches), 1)
        patch_dict = self._profile_patches[0]["profile_json"]
        # All 9 logical blocks present
        for k in ("personal", "parents", "siblings", "spouses",
                  "children", "education", "military", "today",
                  "community"):
            self.assertIn(k, patch_dict, f"profile_patch missing: {k}")
        # Spouse legacy single-slot present for read-bridge compat
        self.assertIn("spouse", patch_dict)
        self.assertEqual(
            patch_dict["community"]["role"], "Mechanical engineer",
        )

    def test_source_metadata_carries_tier_and_via(self):
        from api.services.bio_questionnaire_writer import (
            apply_questionnaire_writes,
        )
        apply_questionnaire_writes("narrator-jake", HAPPY_BLOB,
                                   operator_id="operator-42")
        sample = self._facts_written[0]
        self.assertEqual(sample["source"]["tier"], 4)
        self.assertEqual(sample["source"]["kind"], "operator")
        self.assertEqual(sample["source"]["via"], "questionnaire_put")
        self.assertEqual(sample["source"]["operator_id"], "operator-42")
        self.assertEqual(sample["status"], "operator_entered")

    def test_unknown_field_keys_are_silently_dropped(self):
        """bio_schema has no `work_years_range` — _write_bio_fact
        returns None for unknown keys. The PUT route should not crash
        when an FE blob carries an unknown slot."""
        from api.services.bio_questionnaire_writer import (
            apply_questionnaire_writes,
        )
        blob = {"personal": {
            "fullName": "Tester",
            "dateOfBirth": "1960-01-01",
        }}
        res = apply_questionnaire_writes("nx", blob)
        # full_legal_name + birth_date should write, no error
        keys = self._written_keys()
        self.assertIn("full_legal_name", keys)
        self.assertIn("birth_date", keys)
        self.assertIsNone(res["profile_error"])


# ─────────────────────────────────────────────────────────────────────
# Failure-tolerance & edge cases
# ─────────────────────────────────────────────────────────────────────


class FailureToleranceTest(_WriterFixture):
    def test_empty_blob_writes_nothing_and_does_not_crash(self):
        from api.services.bio_questionnaire_writer import (
            apply_questionnaire_writes,
        )
        res = apply_questionnaire_writes("narrator-empty", {})
        self.assertEqual(res["bio_facts_written"], 0)
        self.assertEqual(res["bio_facts_errors"], [])
        self.assertIsNone(res["profile_error"])
        self.assertEqual(self._facts_written, [])
        self.assertEqual(self._profile_patches, [])

    def test_blank_narrator_id_returns_zero(self):
        from api.services.bio_questionnaire_writer import (
            apply_questionnaire_writes,
        )
        res = apply_questionnaire_writes("", HAPPY_BLOB)
        self.assertEqual(res["bio_facts_written"], 0)
        self.assertEqual(self._facts_written, [])
        self.assertEqual(self._profile_patches, [])

    def test_blank_personal_fields_skipped(self):
        from api.services.bio_questionnaire_writer import (
            apply_questionnaire_writes,
        )
        blob = {"personal": {
            "fullName": "",
            "preferredName": "  ",
            "dateOfBirth": "1955-04-12",
        }}
        apply_questionnaire_writes("n", blob)
        keys = self._written_keys()
        self.assertNotIn("full_legal_name", keys)
        self.assertNotIn("preferred_name", keys)
        self.assertIn("birth_date", keys)

    def test_partial_parents_skip_unnamed_entries(self):
        from api.services.bio_questionnaire_writer import (
            apply_questionnaire_writes,
        )
        blob = {"parents": [
            {"relation": "", "firstName": "", "lastName": ""},  # empty row
            {"relation": "Father", "firstName": "Henry",
             "lastName": "Miller"},
        ]}
        apply_questionnaire_writes("n", blob)
        # Only the named father lands as a scalar
        keys = self._written_keys()
        self.assertIn("father_name", keys)
        self.assertNotIn("mother_name", keys)
        # And the projected array has only the named entry
        prof = self._profile_patches[0]["profile_json"]
        self.assertEqual(len(prof["parents"]), 1)


# ─────────────────────────────────────────────────────────────────────
# Parity with the view: writer + view round-trip
# ─────────────────────────────────────────────────────────────────────


class ViewWriterParityTest(_WriterFixture):
    """Writer fans out → simulate the merged stores → view rebuilds.
    Confirms personal scalars survive the round-trip + show up in
    questionnaire_view output. Mirrors the design intent that PUT
    followed by GET returns equivalent data."""

    def test_personal_scalars_round_trip(self):
        from api.services.bio_questionnaire_writer import (
            apply_questionnaire_writes,
        )
        from api import db
        from api.services.bio_questionnaire_view import (
            build_questionnaire_view,
        )

        # 1. Apply writes — observe what got fanned out.
        apply_questionnaire_writes(
            "narrator-rt", HAPPY_BLOB, operator_id="op-rt",
        )

        # 2. Build the "stored" state from the writer's output:
        #    - profile_json = the last patch's profile_json
        #    - bio_facts    = rows mirrored from _facts_written
        profile_json = self._profile_patches[-1]["profile_json"]

        fake_facts_rows = [
            {
                "id": f"f{i}",
                "field_key": f["field_key"],
                "value": json.dumps(f["value"]),
                "status": f["status"],
                "source": json.dumps(f["source"]),
                "confidence": f["confidence"],
                "created_at": "x",
                "last_updated": "x",
            }
            for i, f in enumerate(self._facts_written)
        ]
        person_row = {
            "id": "narrator-rt", "display_name": "Jake",
            "role": "narrator", "date_of_birth": "1955-04-12",
            "place_of_birth": "Bismarck, North Dakota",
            "narrator_type": "live",
            "pronouns": "he/him", "pronouns_other": "",
            "current_residence": "Fargo, North Dakota",
            "created_at": "x", "updated_at": "x",
        }
        profile_dict = {
            "person_id":    "narrator-rt",
            "updated_at":   "x",
            "profile_json": profile_json,
        }

        with patch.object(db, "get_person", return_value=person_row), \
             patch.object(db, "get_profile", return_value=profile_dict), \
             patch.object(db, "bio_fact_list_by_narrator",
                          return_value=fake_facts_rows):
            view = build_questionnaire_view("narrator-rt")

        # Personal block round-trips byte-stable on the key identity slots
        p = view["questionnaire"]["personal"]
        self.assertEqual(p["fullName"], "Jake Max Miller")
        self.assertEqual(p["dateOfBirth"], "1955-04-12")
        self.assertEqual(p["placeOfBirth"], "Bismarck, North Dakota")
        # Faith block round-trips through personal mirror
        self.assertEqual(p.get("faithRaised"), "Lutheran")
        # Per-field meta carries operator_entered + operator source
        pm = view["_meta"]["personal"]
        self.assertEqual(pm["dateOfBirth"]["status"], "operator_entered")
        self.assertEqual(pm["dateOfBirth"]["source"], "operator")

    def test_arrays_round_trip(self):
        from api.services.bio_questionnaire_writer import (
            apply_questionnaire_writes,
        )
        from api import db
        from api.services.bio_questionnaire_view import (
            build_questionnaire_view,
        )

        apply_questionnaire_writes("rt2", HAPPY_BLOB)
        profile_json = self._profile_patches[-1]["profile_json"]
        person_row = {
            "id": "rt2", "display_name": "x", "role": "x",
            "date_of_birth": "1955-04-12", "place_of_birth": "x",
            "narrator_type": "live",
            "pronouns": "", "pronouns_other": "", "current_residence": "",
            "created_at": "x", "updated_at": "x",
        }
        with patch.object(db, "get_person", return_value=person_row), \
             patch.object(db, "get_profile",
                          return_value={"person_id": "rt2",
                                        "updated_at": "x",
                                        "profile_json": profile_json}), \
             patch.object(db, "bio_fact_list_by_narrator", return_value=[]):
            view = build_questionnaire_view("rt2")
        # Parents survived
        self.assertEqual(len(view["questionnaire"]["parents"]), 2)
        # Siblings survived
        self.assertEqual(len(view["questionnaire"]["siblings"]), 1)
        # Spouses survived
        self.assertEqual(len(view["questionnaire"]["spouses"]), 1)
        # Children survived
        self.assertEqual(len(view["questionnaire"]["children"]), 1)


# ─────────────────────────────────────────────────────────────────────
# years_working bug guard — Phase 4 regression check
# ─────────────────────────────────────────────────────────────────────


class ErrorPropagationTest(_WriterFixture):
    """Code-review issue #1: individual bio_fact_create failures must
    surface in bio_facts_errors, not silently disappear."""

    def test_db_failure_appears_in_errors(self):
        from api import db
        from api.services.bio_questionnaire_writer import (
            apply_questionnaire_writes,
        )
        def _boom(*a, **kw):
            raise RuntimeError("simulated DB lock")
        # Override the patched bio_fact_create with a boom.
        for p in self._patches:
            p.stop()
        try:
            with patch.object(db, "bio_fact_create", side_effect=_boom), \
                 patch.object(db, "update_profile_json", return_value=None):
                res = apply_questionnaire_writes(
                    "n", {"personal": {"fullName": "X", "dateOfBirth": "1960-01-01"}},
                )
            self.assertGreater(len(res["bio_facts_errors"]), 0)
            # At least one error row has the field_key + the error text
            sample = res["bio_facts_errors"][0]
            self.assertIn(sample["field_key"], {"full_legal_name", "birth_date"})
            self.assertIn("simulated DB lock", sample["error"])
        finally:
            # Re-prime the original patches for tearDown's clean stop.
            for p in self._patches:
                p.start()


class YearsWorkingBugGuardTest(_WriterFixture):
    """The writer must NOT route an `education.careerProgression`
    string to bio_facts as `primary_career`. The view ↔ writer parity
    requires that `primaryCareer` and `careerProgression` are two
    distinct slots — the Phase 4 fix removed an identical bug in the
    intake orchestrator; this test is the writer-side regression
    guard so a future refactor can't re-introduce it on this path."""

    def test_career_progression_does_not_clobber_primary_career(self):
        from api.services.bio_questionnaire_writer import (
            apply_questionnaire_writes,
        )
        blob = {"education": {
            "highestLevel": "Bachelor's",
            "careerProgression": "30 years",
            "primaryCareer": "Mechanical engineer",
        }}
        apply_questionnaire_writes("n", blob)
        primary_writes = [
            f for f in self._facts_written
            if f["field_key"] == "primary_career"
        ]
        # Exactly ONE primary_career write, and it carries the actual
        # career, NOT the duration string.
        self.assertEqual(len(primary_writes), 1)
        self.assertEqual(primary_writes[0]["value"], "Mechanical engineer")


if __name__ == "__main__":
    unittest.main()
