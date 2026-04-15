"""WO-EX-01C — API-level integration test for /api/extract-fields.

Unit tests in test_extract_subject_filters.py prove the helper-function
logic. This test proves the ROUTER calls those helpers and the response
payload is actually clean where the user feels it — the HTTP endpoint.

Requirements:
  - fastapi (real package, not stub)
  - pydantic
  - starlette (transitive)
  - httpx   (TestClient dependency on starlette >=0.30)

Run with:
    cd server/code
    python -m unittest ../../tests/test_extract_api_subject_filters.py -v

Or via discovery:
    python -m unittest discover ../../tests -v

NOT runnable in minimal/offline environments — requires the real
FastAPI stack. Run it in the dev venv where the API itself runs.
"""
import os
import sys
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "server", "code"))

from api.routers import extract as extract_router  # noqa: E402


class ExtractApiSubjectFilterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = FastAPI()
        app.include_router(extract_router.router)
        cls.client = TestClient(app)

    @patch("api.routers.extract._extract_via_llm")
    def test_api_drops_west_fargo_birthplace_in_school_context(self, mock_llm):
        """Bug A regression at the HTTP layer.

        LLM is stubbed to return the exact misclassification Chris's live
        session produced. The router must filter it before responding.
        """
        mock_llm.return_value = (
            [
                {
                    "fieldPath": "personal.placeOfBirth",
                    "value": "West Fargo",
                    "confidence": 0.93,
                },
                {
                    "fieldPath": "education.schooling",
                    "value": "kindergarten in West Fargo",
                    "confidence": 0.71,
                },
            ],
            '[{"fieldPath":"personal.placeOfBirth","value":"West Fargo","confidence":0.93}]',
        )

        payload = {
            "person_id": "p_chris",
            "session_id": "sess_1",
            "answer": (
                "When I was in kindergarten we lived in West Fargo in a trailer court. "
                "My parents were going to school at NDSU. We'd ride the bus home from school."
            ),
            "current_section": "school_years",
            "current_phase": "elementary",
            "current_target_path": None,
            "profile_context": None,
        }

        resp = self.client.post("/api/extract-fields", json=payload)
        self.assertEqual(resp.status_code, 200, resp.text)

        body = resp.json()
        self.assertIn("items", body)

        field_paths = [item["fieldPath"] for item in body["items"]]
        self.assertNotIn("personal.placeOfBirth", field_paths)
        self.assertIn("education.schooling", field_paths)
        self.assertEqual(body["method"], "llm")

    @patch("api.routers.extract._extract_via_llm")
    def test_api_drops_child_dob_from_narrator_fields(self, mock_llm):
        """Bug B regression at the HTTP layer.

        Mirror test: 'my son was born April 10 2002' must not produce
        narrator DOB or placeOfBirth on the wire, even when the section
        is in a birth-safe slot like personal_information.
        """
        mock_llm.return_value = (
            [
                {
                    "fieldPath": "personal.dateOfBirth",
                    "value": "2002-04-10",
                    "confidence": 0.92,
                },
                {
                    "fieldPath": "personal.placeOfBirth",
                    "value": "April",
                    "confidence": 0.40,
                },
                {
                    "fieldPath": "education.schooling",
                    "value": "son graduated from West Las Vegas High School in 2022",
                    "confidence": 0.68,
                },
            ],
            '[{"fieldPath":"personal.dateOfBirth","value":"2002-04-10"}]',
        )

        payload = {
            "person_id": "p_chris",
            "session_id": "sess_1",
            "answer": (
                "In 2022 my youngest son Cole Harber La Plante Horne graduated from "
                "West Las Vegas High School, and he was born April 10 2002."
            ),
            "current_section": "personal_information",
            "current_phase": "post_school",
            "current_target_path": None,
            "profile_context": None,
        }

        resp = self.client.post("/api/extract-fields", json=payload)
        self.assertEqual(resp.status_code, 200, resp.text)

        body = resp.json()
        field_paths = [item["fieldPath"] for item in body["items"]]
        self.assertNotIn("personal.dateOfBirth", field_paths)
        self.assertNotIn("personal.placeOfBirth", field_paths)
        self.assertIn("education.schooling", field_paths)
        self.assertEqual(body["method"], "llm")

    @patch("api.routers.extract._extract_via_llm")
    def test_api_preserves_valid_narrator_birth_statement(self, mock_llm):
        """Protection against over-filtering. If the narrator really does
        say 'I was born in X', the endpoint must let the identity fields
        through on the wire."""
        mock_llm.return_value = (
            [
                {
                    "fieldPath": "personal.placeOfBirth",
                    "value": "Williston, North Dakota",
                    "confidence": 0.96,
                },
                {
                    "fieldPath": "personal.dateOfBirth",
                    "value": "1962-12-24",
                    "confidence": 0.97,
                },
            ],
            '[]',
        )

        payload = {
            "person_id": "p_chris",
            "session_id": "sess_1",
            "answer": "I was born in Williston, North Dakota on December 24, 1962.",
            "current_section": "personal_information",
            "current_phase": "pre_school",
            "current_target_path": None,
            "profile_context": None,
        }

        resp = self.client.post("/api/extract-fields", json=payload)
        self.assertEqual(resp.status_code, 200, resp.text)

        body = resp.json()
        field_paths = [item["fieldPath"] for item in body["items"]]
        self.assertIn("personal.placeOfBirth", field_paths)
        self.assertIn("personal.dateOfBirth", field_paths)


if __name__ == "__main__":
    unittest.main()
