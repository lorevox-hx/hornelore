"""BUG-API-PROFILES-DROPS-INTAKE-KEYS-01 — projection tests.

The operator intake form (WO-OPERATOR-NEW-NARRATOR-INTAKE-FORM-01
Phase 2B) writes to `profile_json.personal.*` AND structured blocks
(parents, siblings, etc.). The /api/profiles read path runs through
`db.build_profile_from_promoted` which used to read only from
`profile_json.basics.*` + promoted-truth rows. Intake-created
narrators ended up with `{basics: {}, kinship: [], pets: []}` even
though their intake data was sitting in profile_json.

These tests pin the fix: intake-written personal.* projects into
basics.*, AND structured blocks (parents/siblings/spouses/children/
education/military/faith/today) pass through unchanged.
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


# Canonical intake-shaped profile_json (what the orchestrator writes).
INTAKE_PROFILE_JSON = {
    "personal": {
        "fullName": "Walter O'Donnell",
        "preferredName": "Walt",
        "dateOfBirth": "1948-03-17",
        "placeOfBirth": "South Boston, Massachusetts",
        "currentResidence": "Quincy, Massachusetts",
        "pronouns": "he/him",
        "faithRaised": "Roman Catholic",
        "currentFaith": "Roman Catholic",
        "culture": "Irish-American",
        "languagesAtHome": "English",
    },
    "parents": [
        {"relation": "Father", "firstName": "Patrick", "lastName": "O'Donnell"},
        {"relation": "Mother", "firstName": "Mary", "lastName": "O'Donnell",
         "maidenName": "Sullivan"},
    ],
    "siblings": [
        {"firstName": "Brendan", "lastName": "O'Donnell", "birthOrder": 1},
        {"firstName": "Eileen", "lastName": "O'Donnell", "birthOrder": 3},
    ],
    "spouses": [
        {"firstName": "Catherine", "lastName": "Murphy",
         "yearMarried": "1972", "status": "current"},
    ],
    "children": [
        {"firstName": "Sean", "lastName": "O'Donnell"},
        {"firstName": "Michael", "lastName": "O'Donnell"},
        {"firstName": "Brian", "lastName": "O'Donnell"},
        {"firstName": "Daniel", "lastName": "O'Donnell"},
    ],
    "education": {"highestLevel": "masters",
                  "careerProgression": "1970-2020"},
    "community": {"role": "High-school mathematics teacher"},
    "military": {"served": False},
    "today": {"livingSituation": "Lives in Quincy with wife Catherine"},
}


class IntakeProjectionTest(unittest.TestCase):
    """build_profile_from_promoted projects intake personal into basics
    and passes through structured blocks."""

    def test_intake_personal_projects_into_basics(self):
        from api import db
        with patch.object(db, "init_db", return_value=None), \
             patch.object(db, "get_profile",
                          return_value={"profile_json": INTAKE_PROFILE_JSON}), \
             patch.object(db, "ft_list_promoted", return_value=[]):
            result = db.build_profile_from_promoted("narrator-walt")
        basics = result["basics"]
        # The five identity scalars
        self.assertEqual(basics["fullname"], "Walter O'Donnell")
        self.assertEqual(basics["preferred"], "Walt")
        self.assertEqual(basics["dob"], "1948-03-17")
        self.assertEqual(basics["pob"], "South Boston, Massachusetts")
        # Extended fields
        self.assertEqual(basics["pronouns"], "he/him")
        self.assertEqual(basics["currentResidence"], "Quincy, Massachusetts")
        # Faith mirror
        self.assertEqual(basics["faithRaised"], "Roman Catholic")
        self.assertEqual(basics["culture"], "Irish-American")
        self.assertEqual(basics["language"], "English")

    def test_structured_blocks_pass_through(self):
        from api import db
        with patch.object(db, "init_db", return_value=None), \
             patch.object(db, "get_profile",
                          return_value={"profile_json": INTAKE_PROFILE_JSON}), \
             patch.object(db, "ft_list_promoted", return_value=[]):
            result = db.build_profile_from_promoted("narrator-walt")
        # parents / siblings / spouses / children all pass through
        self.assertEqual(len(result["parents"]), 2)
        self.assertEqual(result["parents"][0]["firstName"], "Patrick")
        self.assertEqual(len(result["siblings"]), 2)
        self.assertEqual(len(result["spouses"]), 1)
        self.assertEqual(result["spouses"][0]["firstName"], "Catherine")
        self.assertEqual(len(result["children"]), 4)
        # Education + military pass through too
        self.assertEqual(result["education"]["highestLevel"], "masters")
        self.assertFalse(result["military"]["served"])
        # Today block passes through
        self.assertIn("today", result)

    def test_legacy_basics_still_pass_through(self):
        """Narrators that have legacy basics + no personal block still
        get their basics returned unchanged."""
        from api import db
        legacy = {
            "profile_json": {
                "basics": {
                    "fullname": "Legacy Narrator",
                    "dob": "1950-01-01",
                    "culture": "set in legacy",
                },
                "kinship": [{"name": "Sib", "relation": "sibling"}],
                "pets": [{"name": "Spot"}],
            },
        }
        with patch.object(db, "init_db", return_value=None), \
             patch.object(db, "get_profile", return_value=legacy), \
             patch.object(db, "ft_list_promoted", return_value=[]):
            result = db.build_profile_from_promoted("legacy")
        self.assertEqual(result["basics"]["fullname"], "Legacy Narrator")
        self.assertEqual(result["basics"]["culture"], "set in legacy")
        self.assertEqual(len(result["kinship"]), 1)
        self.assertEqual(len(result["pets"]), 1)
        # No personal block → no structured passthrough
        self.assertNotIn("parents", result)

    def test_intake_does_not_overwrite_existing_basics(self):
        """When legacy basics has a value AND intake personal has a
        value for the same slot, legacy wins (it's already curated)."""
        from api import db
        merged = {
            "profile_json": {
                "basics": {"fullname": "Curated Name"},
                "personal": {"fullName": "Intake Name"},
            },
        }
        with patch.object(db, "init_db", return_value=None), \
             patch.object(db, "get_profile", return_value=merged), \
             patch.object(db, "ft_list_promoted", return_value=[]):
            result = db.build_profile_from_promoted("p")
        self.assertEqual(result["basics"]["fullname"], "Curated Name")

    def test_promoted_truth_still_wins_over_intake(self):
        """When promoted-truth has a value AND intake personal has a
        value for the same slot, promoted wins."""
        from api import db
        merged = {
            "profile_json": {
                "personal": {"fullName": "Intake Name"},
            },
        }
        promoted = [{
            "field": "personal.fullName", "value": "Promoted Name",
            "status": "confirmed", "qualification": "",
            "subject_name": "", "relationship": "self",
            "reviewer": "", "source_row_id": "", "updated_at": "",
        }]
        with patch.object(db, "init_db", return_value=None), \
             patch.object(db, "get_profile", return_value=merged), \
             patch.object(db, "ft_list_promoted", return_value=promoted):
            result = db.build_profile_from_promoted("p")
        self.assertEqual(result["basics"]["fullname"], "Promoted Name")

    def test_empty_profile_returns_empty_shape(self):
        from api import db
        with patch.object(db, "init_db", return_value=None), \
             patch.object(db, "get_profile", return_value={"profile_json": {}}), \
             patch.object(db, "ft_list_promoted", return_value=[]):
            result = db.build_profile_from_promoted("p")
        self.assertEqual(result["basics"], {})
        self.assertEqual(result["kinship"], [])
        self.assertEqual(result["pets"], [])
        # No intake keys → no structured passthrough
        for k in ("personal", "parents", "siblings"):
            self.assertNotIn(k, result)

    def test_get_profile_returns_none_does_not_crash(self):
        from api import db
        with patch.object(db, "init_db", return_value=None), \
             patch.object(db, "get_profile", return_value=None), \
             patch.object(db, "ft_list_promoted", return_value=[]):
            result = db.build_profile_from_promoted("nx")
        self.assertEqual(result["basics"], {})


if __name__ == "__main__":
    unittest.main()
