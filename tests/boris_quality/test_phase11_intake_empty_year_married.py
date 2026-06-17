from __future__ import annotations

import unittest


class IntakeEmptyYearMarriedTests(unittest.TestCase):
    """Adjacent blocker — Alex intake 422 on year_married=''.

    This is a direct Pydantic-model regression test.
    """

    def test_intake_spouse_empty_year_married_coerces_to_none(self):
        from server.code.api.routers.people import IntakeSpouse

        spouse = IntakeSpouse(name="Jordan Lee", year_married="", status="divorced")
        self.assertIsNone(spouse.year_married)

    def test_full_intake_payload_accepts_empty_spouse_year(self):
        from server.code.api.routers.people import NarratorIntakePayload

        payload = NarratorIntakePayload(
            full_legal_name="Alex Kim",
            preferred_name="Alex",
            date_of_birth="1984-04-12",
            place_of_birth="Los Angeles, California",
            pronouns="they_them",
            current_residence="Portland, Oregon",
            consent_recording_agreement=True,
            consent_disclosure_reviewed=True,
            testing_only=True,
            marriage={
                "marital_status": "divorced",
                "number_of_marriages": 1,
                "spouses": [{"name": "Taylor Kim", "year_married": "", "status": "divorced"}],
            },
        )
        self.assertIsNotNone(payload.marriage)
        self.assertEqual(len(payload.marriage.spouses), 1)
        self.assertIsNone(payload.marriage.spouses[0].year_married)


if __name__ == "__main__":
    unittest.main()
