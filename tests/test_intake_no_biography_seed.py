"""Batch C-3 — narrator creation is not a second biography seed.

POST /api/people/intake used to fan a rich payload (family, marriage,
children, work, service, faith, today) into profile_json and bio_facts, and
only then write identity to the Life Record. For a REAL narrator it now
refuses those sections (422, naming them) and writes nothing; identity and
consent create the narrator, and the Life Record holds the identity.

testing_only narrators (the Lori harnesses) keep the earlier seeding until
Batch D moves Lori onto the Life Record — pinned here so that exception is a
decision, not an accident.

Route tests: they SKIP without fastapi (sandbox python3). Run under .venv.
"""
from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))
sys.path.insert(0, str(REPO))

from api import db as _db  # noqa: E402
from tests.test_life_record_writer import _Db  # noqa: E402

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    HAVE_FASTAPI = True
except ImportError:  # sandbox python3
    HAVE_FASTAPI = False

IDENTITY = {
    "full_legal_name": "Solveig Ingrid Haugen", "preferred_name": "Solveig",
    "date_of_birth": "1941-03-02", "place_of_birth": "Tromsø, Norway", "pronouns": "she_her",
    "current_residence": "Duluth, Minnesota",
    "consent_recording_agreement": True, "consent_disclosure_reviewed": True,
}


@unittest.skipUnless(HAVE_FASTAPI, "fastapi is required — run under .venv")
class IntakeIsIdentityAndConsent(_Db):
    def setUp(self):
        super().setUp()
        from api.routers import people as _people
        app = FastAPI()
        app.include_router(_people.router)
        self.client = TestClient(app)

    def count(self, sql, *a):
        con = sqlite3.connect(str(_db.DB_PATH))
        try:
            return con.execute(sql, a).fetchone()[0]
        finally:
            con.close()

    def test_a_real_narrator_with_biography_sections_is_refused_and_nothing_is_written(self):
        before = self.count("SELECT count(*) FROM people")
        r = self.client.post("/api/people/intake", json=dict(
            IDENTITY, family_of_origin={"father_name": "Arne Haugen"},
            children=[{"name": "Kari"}], military={"served": False}))
        self.assertEqual(r.status_code, 422, r.text)
        self.assertEqual(sorted(r.json()["detail"]["sections"]), ["children", "family_of_origin", "military"])
        self.assertEqual(self.count("SELECT count(*) FROM people"), before, "no narrator half-created")
        self.assertEqual(self.count("SELECT count(*) FROM bio_facts"), 0)

    def test_identity_and_consent_create_the_narrator_and_their_life_record_only(self):
        r = self.client.post("/api/people/intake", json=dict(IDENTITY))
        self.assertEqual(r.status_code, 200, r.text)
        pid = r.json()["person_id"]
        self.assertEqual(self.count("SELECT count(*) FROM bio_facts WHERE narrator_id=?", pid), 0)
        self.assertEqual(self.count("SELECT count(*) FROM lr_names WHERE narrator_id=? AND full_text=?",
                                    pid, "Solveig Ingrid Haugen"), 1)
        # identity only — no family, marriage, children or service in the profile
        prof = _db.get_profile(pid) or {}
        blob = prof.get("profile_json", prof) if isinstance(prof, dict) else {}
        for k in ("parents", "siblings", "spouses", "spouse", "children", "military", "education", "today"):
            self.assertNotIn(k, blob or {}, k)

    def test_a_stated_zero_is_an_answer_and_is_refused(self):
        # C-3 review: `and v` treated 0 as empty, so "married 0 times" slipped
        # through the guard. Zero is a stated answer, not a blank.
        before = self.count("SELECT count(*) FROM people")
        r = self.client.post("/api/people/intake", json=dict(IDENTITY, marriage={"number_of_marriages": 0}))
        self.assertEqual(r.status_code, 422, r.text)
        self.assertEqual(r.json()["detail"]["sections"], ["marriage"])
        self.assertEqual(self.count("SELECT count(*) FROM people"), before, "no narrator created")

    def test_empty_sections_are_not_answers_and_do_not_refuse(self):
        r = self.client.post("/api/people/intake", json=dict(
            IDENTITY, family_of_origin={"father_name": "", "siblings": []}, children=[], faith={}))
        self.assertEqual(r.status_code, 200, r.text)

    def test_a_testing_only_narrator_keeps_the_harness_seeding_until_batch_d(self):
        r = self.client.post("/api/people/intake", json=dict(
            IDENTITY, testing_only=True, military={"served": False}))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.count("SELECT count(*) FROM bio_facts WHERE narrator_id=? AND field_key='military_served'",
                                    r.json()["person_id"]), 1)


if __name__ == "__main__":
    unittest.main()
