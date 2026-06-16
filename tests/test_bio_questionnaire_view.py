"""WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01 Phase 1 — read-aggregation tests.

Exercises the new bio_questionnaire_view service in isolation by
patching the three db.* accessors it consults (get_person, get_profile,
bio_fact_list_by_narrator).

Avoids the temp-sqlite fixture used by test_bio_facts_crud.py since the
view layer is pure aggregation — there's nothing DB-engine-specific to
verify here. Patch the three reader functions, hand the view canned
shapes, assert the projection.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))


# Canonical person + profile + facts shapes used across tests.

PERSON_ROW = {
    "id": "narrator-jake",
    "display_name": "Jake Max Miller",
    "role": "narrator",
    "date_of_birth": "1955-04-12",
    "place_of_birth": "Bismarck, North Dakota",
    "narrator_type": "live",
    "pronouns": "he/him",
    "pronouns_other": "",
    "current_residence": "Fargo, North Dakota",
    "created_at": "2026-06-15T10:00:00Z",
    "updated_at": "2026-06-15T10:00:00Z",
}


PROFILE = {
    "person_id": "narrator-jake",
    "updated_at": "2026-06-15T10:30:00Z",
    "profile_json": {
        "personal": {
            "fullName": "Jake Max Miller",
            "preferredName": "Jake",
            "dateOfBirth": "1955-04-12",
            "placeOfBirth": "Bismarck, North Dakota",
            "currentResidence": "Fargo, North Dakota",
            "pronouns": "he/him",
            "faithRaised": "Lutheran",
            "currentFaith": "Lutheran",
            "culture": "German-Russian heritage",
            "languagesAtHome": "English, some German",
        },
        "parents": [
            {
                "relation": "Father", "firstName": "Henry",
                "middleName": "", "lastName": "Miller",
                "dateOfBirth": "1925-03-10",
            },
            {
                "relation": "Mother", "firstName": "Mae",
                "middleName": "", "lastName": "Miller",
                "maidenName": "Schwartz",
                "dateOfBirth": "1928-09-22",
            },
        ],
        "siblings": [
            {
                "firstName": "Walter", "middleName": "",
                "lastName": "Miller", "birthOrder": 1,
                "dateOfBirth": "1953-01-15",
            },
        ],
        "spouses": [
            {
                "firstName": "Dorothy", "middleName": "",
                "lastName": "Miller", "yearMarried": "1977",
                "status": "Married",
            },
        ],
        "children": [
            {
                "firstName": "Anna", "middleName": "",
                "lastName": "Miller", "dateOfBirth": "1980-06-05",
            },
        ],
        "education": {
            "highestLevel": "Bachelor's",
            "careerProgression": "30 years",
        },
        "community": {"role": "Mechanical engineer"},
        "military": {
            "served": True,
            "branch": "Army",
            "servicePeriod": "1974-1976",
            "rank": "Specialist",
            "locations": "Fort Lewis",
        },
        "today": {
            "livingSituation": "Lives at home with spouse",
            "healthConsiderations": "Hearing aid",
        },
    },
}


# bio_facts rows — these populate the per-field {status, source} meta
# the FE renders as status badges. Multiple rows per (narrator, field)
# allowed: the view picks the highest-priority row.
FACTS_ROWS = [
    {
        "id": "f1", "field_key": "birth_date", "value": "1955-04-12",
        "status": "operator_entered",
        "source": '{"tier": 4, "kind": "operator"}',
        "confidence": 1.0,
        "created_at": "2026-06-15T10:00:00Z",
        "last_updated": "2026-06-15T10:00:00Z",
    },
    {
        "id": "f2", "field_key": "birth_place",
        "value": "Bismarck, North Dakota",
        "status": "operator_entered",
        "source": '{"tier": 4, "kind": "operator"}',
        "confidence": 1.0,
        "created_at": "2026-06-15T10:00:00Z",
        "last_updated": "2026-06-15T10:00:00Z",
    },
    {
        "id": "f3", "field_key": "father_name", "value": "Henry Miller",
        "status": "operator_entered",
        "source": '{"tier": 4, "kind": "operator"}',
        "confidence": 1.0,
        "created_at": "2026-06-15T10:00:00Z",
        "last_updated": "2026-06-15T10:00:00Z",
    },
    {
        "id": "f4", "field_key": "mother_name", "value": "Mae Miller",
        "status": "operator_entered",
        "source": '{"tier": 4, "kind": "operator"}',
        "confidence": 1.0,
        "created_at": "2026-06-15T10:00:00Z",
        "last_updated": "2026-06-15T10:00:00Z",
    },
    {
        "id": "f5", "field_key": "mother_maiden_name", "value": "Schwartz",
        "status": "approved",
        "source": '{"tier": 4, "kind": "operator"}',
        "confidence": 1.0,
        "created_at": "2026-06-15T10:00:00Z",
        "last_updated": "2026-06-15T10:00:00Z",
    },
    {
        "id": "f6", "field_key": "sibling_count", "value": "1",
        "status": "operator_entered",
        "source": '{"tier": 4, "kind": "operator"}',
        "confidence": 1.0,
        "created_at": "2026-06-15T10:00:00Z",
        "last_updated": "2026-06-15T10:00:00Z",
    },
    {
        "id": "f7", "field_key": "spouse_name", "value": "Dorothy Miller",
        "status": "operator_entered",
        "source": '{"tier": 4, "kind": "operator"}',
        "confidence": 1.0,
        "created_at": "2026-06-15T10:00:00Z",
        "last_updated": "2026-06-15T10:00:00Z",
    },
    {
        "id": "f8", "field_key": "marriage_year", "value": "1977",
        "status": "operator_entered",
        "source": '{"tier": 4, "kind": "operator"}',
        "confidence": 1.0,
        "created_at": "2026-06-15T10:00:00Z",
        "last_updated": "2026-06-15T10:00:00Z",
    },
    {
        "id": "f9", "field_key": "children_count", "value": "1",
        "status": "operator_entered",
        "source": '{"tier": 4, "kind": "operator"}',
        "confidence": 1.0,
        "created_at": "2026-06-15T10:00:00Z",
        "last_updated": "2026-06-15T10:00:00Z",
    },
    {
        "id": "f10", "field_key": "highest_education_level",
        "value": "Bachelor's",
        "status": "operator_entered",
        "source": '{"tier": 4, "kind": "operator"}',
        "confidence": 1.0,
        "created_at": "2026-06-15T10:00:00Z",
        "last_updated": "2026-06-15T10:00:00Z",
    },
    {
        "id": "f11", "field_key": "primary_career",
        "value": "Mechanical engineer",
        "status": "operator_entered",
        "source": '{"tier": 4, "kind": "operator"}',
        "confidence": 1.0,
        "created_at": "2026-06-15T10:00:00Z",
        "last_updated": "2026-06-15T10:00:00Z",
    },
    {
        "id": "f12", "field_key": "military_branch", "value": "Army",
        "status": "operator_entered",
        "source": '{"tier": 4, "kind": "operator"}',
        "confidence": 1.0,
        "created_at": "2026-06-15T10:00:00Z",
        "last_updated": "2026-06-15T10:00:00Z",
    },
    {
        "id": "f13", "field_key": "religion_raised", "value": "Lutheran",
        "status": "operator_entered",
        "source": '{"tier": 4, "kind": "operator"}',
        "confidence": 1.0,
        "created_at": "2026-06-15T10:00:00Z",
        "last_updated": "2026-06-15T10:00:00Z",
    },
]


def _patches(person=PERSON_ROW, profile=PROFILE, facts=FACTS_ROWS):
    """Helper: build the three patch context-managers for a test."""
    from api import db
    return (
        patch.object(db, "get_person", return_value=person),
        patch.object(db, "get_profile", return_value=profile),
        patch.object(db, "bio_fact_list_by_narrator", return_value=facts),
    )


# ─────────────────────────────────────────────────────────────────────
# Section shape tests
# ─────────────────────────────────────────────────────────────────────


class HappyPathShapeTest(unittest.TestCase):
    """View renders all 9 sections + meta when all sources are populated."""

    def test_returns_well_shaped_view(self):
        from api.services.bio_questionnaire_view import build_questionnaire_view
        p1, p2, p3 = _patches()
        with p1, p2, p3:
            view = build_questionnaire_view("narrator-jake")
        self.assertIsNotNone(view)
        self.assertEqual(view["person_id"], "narrator-jake")
        self.assertEqual(view["source"], "bio_facts_merged")
        self.assertEqual(view["version"], 1)
        # 9 sections in questionnaire and _meta
        for k in (
            "personal", "parents", "siblings", "spouses", "children",
            "education", "military", "faith", "today",
        ):
            self.assertIn(k, view["questionnaire"])
            self.assertIn(k, view["_meta"])

    def test_personal_section_fields(self):
        from api.services.bio_questionnaire_view import build_questionnaire_view
        p1, p2, p3 = _patches()
        with p1, p2, p3:
            view = build_questionnaire_view("narrator-jake")
        p = view["questionnaire"]["personal"]
        self.assertEqual(p["fullName"], "Jake Max Miller")
        self.assertEqual(p["preferredName"], "Jake")
        self.assertEqual(p["dateOfBirth"], "1955-04-12")
        self.assertEqual(p["placeOfBirth"], "Bismarck, North Dakota")
        self.assertEqual(p["currentResidence"], "Fargo, North Dakota")
        self.assertEqual(p["pronouns"], "he/him")
        self.assertEqual(p["faithRaised"], "Lutheran")
        self.assertEqual(p["currentFaith"], "Lutheran")
        self.assertEqual(p["culture"], "German-Russian heritage")
        self.assertEqual(p["languagesAtHome"], "English, some German")

    def test_parents_section_array(self):
        from api.services.bio_questionnaire_view import build_questionnaire_view
        p1, p2, p3 = _patches()
        with p1, p2, p3:
            view = build_questionnaire_view("narrator-jake")
        parents = view["questionnaire"]["parents"]
        self.assertEqual(len(parents), 2)
        self.assertEqual(parents[0]["relation"], "Father")
        self.assertEqual(parents[0]["firstName"], "Henry")
        self.assertEqual(parents[0]["lastName"], "Miller")
        self.assertEqual(parents[1]["maidenName"], "Schwartz")

    def test_siblings_section_array(self):
        from api.services.bio_questionnaire_view import build_questionnaire_view
        p1, p2, p3 = _patches()
        with p1, p2, p3:
            view = build_questionnaire_view("narrator-jake")
        sibs = view["questionnaire"]["siblings"]
        self.assertEqual(len(sibs), 1)
        self.assertEqual(sibs[0]["firstName"], "Walter")

    def test_spouses_section_array(self):
        from api.services.bio_questionnaire_view import build_questionnaire_view
        p1, p2, p3 = _patches()
        with p1, p2, p3:
            view = build_questionnaire_view("narrator-jake")
        sp = view["questionnaire"]["spouses"]
        self.assertEqual(len(sp), 1)
        self.assertEqual(sp[0]["firstName"], "Dorothy")
        self.assertEqual(sp[0]["yearMarried"], "1977")
        self.assertEqual(sp[0]["status"], "Married")

    def test_children_section_array(self):
        from api.services.bio_questionnaire_view import build_questionnaire_view
        p1, p2, p3 = _patches()
        with p1, p2, p3:
            view = build_questionnaire_view("narrator-jake")
        kids = view["questionnaire"]["children"]
        self.assertEqual(len(kids), 1)
        self.assertEqual(kids[0]["firstName"], "Anna")
        self.assertEqual(kids[0]["dateOfBirth"], "1980-06-05")

    def test_education_section(self):
        from api.services.bio_questionnaire_view import build_questionnaire_view
        p1, p2, p3 = _patches()
        with p1, p2, p3:
            view = build_questionnaire_view("narrator-jake")
        edu = view["questionnaire"]["education"]
        self.assertEqual(edu["highestLevel"], "Bachelor's")
        self.assertEqual(edu["careerProgression"], "30 years")
        self.assertEqual(edu["primaryCareer"], "Mechanical engineer")

    def test_military_section(self):
        from api.services.bio_questionnaire_view import build_questionnaire_view
        p1, p2, p3 = _patches()
        with p1, p2, p3:
            view = build_questionnaire_view("narrator-jake")
        mil = view["questionnaire"]["military"]
        self.assertTrue(mil["served"])
        self.assertEqual(mil["branch"], "Army")
        self.assertEqual(mil["servicePeriod"], "1974-1976")
        self.assertEqual(mil["locations"], "Fort Lewis")

    def test_faith_section(self):
        from api.services.bio_questionnaire_view import build_questionnaire_view
        p1, p2, p3 = _patches()
        with p1, p2, p3:
            view = build_questionnaire_view("narrator-jake")
        faith = view["questionnaire"]["faith"]
        self.assertEqual(faith["religionRaised"], "Lutheran")
        self.assertEqual(faith["currentFaith"], "Lutheran")
        self.assertEqual(faith["ethnicityHeritage"], "German-Russian heritage")
        self.assertEqual(faith["languagesAtHome"], "English, some German")

    def test_today_section(self):
        from api.services.bio_questionnaire_view import build_questionnaire_view
        p1, p2, p3 = _patches()
        with p1, p2, p3:
            view = build_questionnaire_view("narrator-jake")
        today = view["questionnaire"]["today"]
        self.assertEqual(today["livingSituation"], "Lives at home with spouse")
        self.assertEqual(today["healthConsiderations"], "Hearing aid")


# ─────────────────────────────────────────────────────────────────────
# Meta status-badge mapping
# ─────────────────────────────────────────────────────────────────────


class MetaStatusMappingTest(unittest.TestCase):
    """Per-field _meta entries carry {status, source} pulled from
    bio_facts via the field_key → questionnaire-slot map."""

    def test_personal_meta_carries_status_and_source(self):
        from api.services.bio_questionnaire_view import build_questionnaire_view
        p1, p2, p3 = _patches()
        with p1, p2, p3:
            view = build_questionnaire_view("narrator-jake")
        pm = view["_meta"]["personal"]
        self.assertEqual(pm["dateOfBirth"]["status"], "operator_entered")
        self.assertEqual(pm["dateOfBirth"]["source"], "operator")
        self.assertEqual(pm["placeOfBirth"]["status"], "operator_entered")
        self.assertEqual(pm["faithRaised"]["status"], "operator_entered")

    def test_parents_meta_carries_named_keys(self):
        from api.services.bio_questionnaire_view import build_questionnaire_view
        p1, p2, p3 = _patches()
        with p1, p2, p3:
            view = build_questionnaire_view("narrator-jake")
        pm = view["_meta"]["parents"]
        self.assertEqual(pm["father_name"]["status"], "operator_entered")
        self.assertEqual(pm["mother_name"]["status"], "operator_entered")
        # mother_maiden_name was 'approved' — confirm winner is approved
        self.assertEqual(pm["mother_maiden_name"]["status"], "approved")

    def test_siblings_meta_carries_section_count(self):
        from api.services.bio_questionnaire_view import build_questionnaire_view
        p1, p2, p3 = _patches()
        with p1, p2, p3:
            view = build_questionnaire_view("narrator-jake")
        sm = view["_meta"]["siblings"]
        self.assertEqual(sm["_section"]["status"], "operator_entered")

    def test_education_meta_carries_primary_career(self):
        from api.services.bio_questionnaire_view import build_questionnaire_view
        p1, p2, p3 = _patches()
        with p1, p2, p3:
            view = build_questionnaire_view("narrator-jake")
        em = view["_meta"]["education"]
        self.assertEqual(em["primaryCareer"]["status"], "operator_entered")
        self.assertEqual(em["highestLevel"]["status"], "operator_entered")


# ─────────────────────────────────────────────────────────────────────
# Status precedence (multiple rows per field_key)
# ─────────────────────────────────────────────────────────────────────


class StatusPrecedenceTest(unittest.TestCase):
    """When bio_facts has multiple rows for the same field_key, the
    highest-priority status wins. Tie-break by last_updated DESC."""

    def test_approved_beats_operator_entered(self):
        from api.services.bio_questionnaire_view import build_questionnaire_view
        # Two father_name rows: operator-entered (older) + approved (newer)
        facts = [
            {
                "id": "old", "field_key": "father_name", "value": "Henry",
                "status": "operator_entered",
                "source": '{"tier": 4, "kind": "operator"}',
                "confidence": 1.0,
                "created_at": "2026-06-15T08:00:00Z",
                "last_updated": "2026-06-15T08:00:00Z",
            },
            {
                "id": "new", "field_key": "father_name", "value": "Henry",
                "status": "approved",
                "source": '{"tier": 4, "kind": "operator"}',
                "confidence": 1.0,
                "created_at": "2026-06-15T09:00:00Z",
                "last_updated": "2026-06-15T09:00:00Z",
            },
        ]
        p1, p2, p3 = _patches(facts=facts)
        with p1, p2, p3:
            view = build_questionnaire_view("narrator-jake")
        # approved is higher priority than operator_entered
        self.assertEqual(
            view["_meta"]["parents"]["father_name"]["status"], "approved",
        )

    def test_conflicted_does_not_beat_approved(self):
        from api.services.bio_questionnaire_view import build_questionnaire_view
        facts = [
            {
                "id": "ok", "field_key": "father_name", "value": "Henry",
                "status": "approved",
                "source": '{"tier": 4, "kind": "operator"}',
                "confidence": 1.0,
                "created_at": "2026-06-15T08:00:00Z",
                "last_updated": "2026-06-15T08:00:00Z",
            },
            {
                "id": "conf", "field_key": "father_name", "value": "Hank",
                "status": "conflicted",
                "source": '{"tier": 1, "kind": "extractor"}',
                "confidence": 0.6,
                "created_at": "2026-06-15T09:00:00Z",
                "last_updated": "2026-06-15T09:00:00Z",  # newer but lower prio
            },
        ]
        p1, p2, p3 = _patches(facts=facts)
        with p1, p2, p3:
            view = build_questionnaire_view("narrator-jake")
        # approved must win despite conflicted being newer
        self.assertEqual(
            view["_meta"]["parents"]["father_name"]["status"], "approved",
        )


# ─────────────────────────────────────────────────────────────────────
# Empty / partial narrator (no bio_facts, sparse profile_json)
# ─────────────────────────────────────────────────────────────────────


class EmptyNarratorTest(unittest.TestCase):
    """View renders well-shaped empty sections, not None / 500."""

    def test_empty_facts_empty_profile_returns_blank_view(self):
        from api.services.bio_questionnaire_view import build_questionnaire_view
        person = dict(PERSON_ROW)
        empty_profile = {
            "person_id": "narrator-jake",
            "updated_at": "",
            "profile_json": {},
        }
        p1, p2, p3 = _patches(person=person, profile=empty_profile, facts=[])
        with p1, p2, p3:
            view = build_questionnaire_view("narrator-jake")
        # Sections present but empty/default-shaped
        self.assertEqual(view["questionnaire"]["parents"], [])
        self.assertEqual(view["questionnaire"]["siblings"], [])
        self.assertEqual(view["questionnaire"]["spouses"], [])
        self.assertEqual(view["questionnaire"]["children"], [])
        # personal pulls DOB/POB from people row scalars
        p = view["questionnaire"]["personal"]
        self.assertEqual(p["dateOfBirth"], "1955-04-12")
        self.assertEqual(p["placeOfBirth"], "Bismarck, North Dakota")
        self.assertEqual(p["fullName"], "Jake Max Miller")  # display_name
        # Meta is empty-but-present for sections without facts
        self.assertEqual(view["_meta"]["education"], {})

    def test_no_person_row_returns_none(self):
        from api.services.bio_questionnaire_view import build_questionnaire_view
        p1, p2, p3 = _patches(person=None, profile=None, facts=[])
        with p1, p2, p3:
            view = build_questionnaire_view("narrator-jake")
        self.assertIsNone(view)

    def test_blank_narrator_id_returns_none(self):
        from api.services.bio_questionnaire_view import build_questionnaire_view
        self.assertIsNone(build_questionnaire_view(""))

    def test_get_profile_failure_does_not_crash(self):
        """When get_profile raises, the view still returns a shape
        backed by people row + bio_facts only."""
        from api import db
        from api.services.bio_questionnaire_view import build_questionnaire_view
        with patch.object(db, "get_person", return_value=PERSON_ROW), \
             patch.object(db, "get_profile", side_effect=Exception("DB down")), \
             patch.object(db, "bio_fact_list_by_narrator", return_value=[]):
            view = build_questionnaire_view("narrator-jake")
        self.assertIsNotNone(view)
        # personal still has people-row scalars
        self.assertEqual(
            view["questionnaire"]["personal"]["dateOfBirth"], "1955-04-12",
        )

    def test_bio_fact_read_failure_does_not_crash(self):
        from api import db
        from api.services.bio_questionnaire_view import build_questionnaire_view
        with patch.object(db, "get_person", return_value=PERSON_ROW), \
             patch.object(db, "get_profile", return_value=PROFILE), \
             patch.object(db, "bio_fact_list_by_narrator",
                          side_effect=Exception("table missing")):
            view = build_questionnaire_view("narrator-jake")
        self.assertIsNotNone(view)
        # Sections still render from profile_json
        self.assertEqual(
            view["questionnaire"]["personal"]["fullName"], "Jake Max Miller",
        )
        # Meta is empty since bio_facts failed
        self.assertEqual(view["_meta"]["personal"], {})


# ─────────────────────────────────────────────────────────────────────
# Source-label extraction (kind / tier fallback)
# ─────────────────────────────────────────────────────────────────────


class SourceLabelTest(unittest.TestCase):
    def test_kind_key_wins(self):
        from api.services.bio_questionnaire_view import build_questionnaire_view
        facts = [{
            "id": "f", "field_key": "primary_career", "value": "Engineer",
            "status": "operator_entered",
            "source": '{"tier": 4, "kind": "operator"}',
            "confidence": 1.0,
            "created_at": "x", "last_updated": "x",
        }]
        p1, p2, p3 = _patches(facts=facts)
        with p1, p2, p3:
            view = build_questionnaire_view("narrator-jake")
        self.assertEqual(
            view["_meta"]["education"]["primaryCareer"]["source"], "operator",
        )

    def test_tier_fallback_when_no_kind(self):
        from api.services.bio_questionnaire_view import build_questionnaire_view
        facts = [{
            "id": "f", "field_key": "primary_career", "value": "Engineer",
            "status": "extracted_needs_verify",
            "source": '{"tier": 1}',
            "confidence": 0.7,
            "created_at": "x", "last_updated": "x",
        }]
        p1, p2, p3 = _patches(facts=facts)
        with p1, p2, p3:
            view = build_questionnaire_view("narrator-jake")
        self.assertEqual(
            view["_meta"]["education"]["primaryCareer"]["source"], "extractor",
        )

    def test_empty_source_blob(self):
        from api.services.bio_questionnaire_view import build_questionnaire_view
        facts = [{
            "id": "f", "field_key": "primary_career", "value": "Engineer",
            "status": "operator_entered", "source": "",
            "confidence": 1.0,
            "created_at": "x", "last_updated": "x",
        }]
        p1, p2, p3 = _patches(facts=facts)
        with p1, p2, p3:
            view = build_questionnaire_view("narrator-jake")
        self.assertEqual(
            view["_meta"]["education"]["primaryCareer"]["source"], "",
        )


# ─────────────────────────────────────────────────────────────────────
# Spouse legacy-shape fallback
# ─────────────────────────────────────────────────────────────────────


class SpouseLegacyShapeTest(unittest.TestCase):
    """When profile_json carries a single `spouse` dict (legacy) AND
    not `spouses` array, the view should still render one spouse row."""

    def test_single_spouse_legacy_fallback(self):
        from api.services.bio_questionnaire_view import build_questionnaire_view
        profile = {
            "person_id": "narrator-jake",
            "updated_at": "x",
            "profile_json": {
                "spouse": {
                    "firstName": "Helen", "lastName": "Miller",
                    "yearMarried": "1980",
                },
                # no `spouses` key at all
            },
        }
        p1, p2, p3 = _patches(profile=profile, facts=[])
        with p1, p2, p3:
            view = build_questionnaire_view("narrator-jake")
        sp = view["questionnaire"]["spouses"]
        self.assertEqual(len(sp), 1)
        self.assertEqual(sp[0]["firstName"], "Helen")


if __name__ == "__main__":
    unittest.main()
