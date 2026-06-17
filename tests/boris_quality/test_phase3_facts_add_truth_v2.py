from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


class FactsAddTruthV2RoutingTests(unittest.TestCase):
    """Phase 3 — facts/add silent-data-loss contract tests.

    The important regression: proposal-shaped FE payloads must not die as a
    confusing 422 when HORNELORE_TRUTH_V2 is enabled. They must route through
    the new family-truth path or receive an explicit 410 migration response.
    """

    def _client(self):
        from server.code.api.routers import facts
        app = FastAPI()
        app.include_router(facts.router)
        return TestClient(app)

    @patch.dict(os.environ, {"HORNELORE_TRUTH_V2": "1"}, clear=False)
    def test_legacy_factadd_valid_shape_returns_explicit_410_under_truth_v2(self):
        client = self._client()
        response = client.post(
            "/api/facts/add",
            json={
                "person_id": "d11572d4-57a1-4100-8426-cfd7293a7441",
                "statement": "John Baldy was born in West St. Paul, Minnesota.",
                "fact_type": "birth",
                "status": "extracted",
                "confidence": 0.95,
            },
        )
        self.assertEqual(response.status_code, 410)
        self.assertIn("family-truth", response.text)

    @patch.dict(os.environ, {"HORNELORE_TRUTH_V2": "1"}, clear=False)
    def test_proposal_shaped_payload_returns_410_not_422_under_truth_v2(self):
        client = self._client()
        proposal_payload = {
            "subject_name": "John Baldy",
            "relationship": "self",
            "field": "personal.placeOfBirth",
            "source_says": "I was born in West St. Paul, Minnesota.",
            "status": "needs_verify",
            "confidence": 0.91,
            "narrative_role": "identity",
            "meaning_tags": ["place", "origin"],
            "provenance": {"conv_id": "boris_test", "turn": 1},
        }
        response = client.post("/api/facts/add", json=proposal_payload)
        self.assertEqual(
            response.status_code,
            410,
            "Under HORNELORE_TRUTH_V2, proposal-shaped legacy facts/add calls "
            "must receive an explicit 410 migration response, not Pydantic 422. "
            f"Body: {response.text}",
        )

    def test_factadd_request_rejects_proposal_shape_when_truth_v2_off(self):
        from pydantic import ValidationError
        from server.code.api.routers.facts import FactAddRequest

        with self.assertRaises(ValidationError):
            FactAddRequest(
                subject_name="John Baldy",
                relationship="self",
                field="personal.placeOfBirth",
                source_says="Born in West St. Paul",
                status="needs_verify",
            )


if __name__ == "__main__":
    unittest.main()
