"""Batch C-2R2 — a new narrator exists in the Life Record from creation.

Real SQLite migrated by init_db; the people row is inserted the way
create_person leaves it (no Life Record), then establish_narrator — the
function both creation routes call — writes through the one writer. The
route-level test (FastAPI) skips, and says so, where FastAPI is absent.
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
from api.services.life_record import writer as W  # noqa: E402
from api.services.life_record.identity import establish_narrator  # noqa: E402
from tests.test_life_record_writer import NORA, _Db  # noqa: E402

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routers import people as _people_router
    _HAVE_FASTAPI = True
except Exception:  # pragma: no cover
    _HAVE_FASTAPI = False


class EstablishNarrator(_Db):
    def test_a_name_only_narrator_exists_in_the_record(self):
        self.assertEqual(W.read_record(NORA)["revision"], 0, "precondition: nothing in the record")
        r = establish_narrator(NORA, full_name="Nora Whitfield")
        self.assertTrue(r["ok"], r)
        rec = W.read_record(NORA)
        me = rec["people"][0]
        self.assertEqual((rec["revision"], me["id"], [n["fullText"] for n in me["names"]], me["preferredNameRef"]),
                         (1, NORA, ["Nora Whitfield"], f"{NORA}-name"))
        self.assertEqual(rec["events"], [], "no birth was invented")
        self.assertNotIn("person.pronouns", me, "blank stays blank")

    def test_full_identity_is_written_as_given_and_nothing_more(self):
        r = establish_narrator(NORA, full_name="Nora Ann Whitfield", preferred_name="Nan",
                               pronouns="she/her", birth_date="around 1939", birth_place="Minot, North Dakota")
        self.assertTrue(r["ok"], r)
        rec = W.read_record(NORA)
        me = rec["people"][0]
        self.assertEqual({n["fullText"] for n in me["names"]}, {"Nora Ann Whitfield", "Nan"})
        self.assertEqual([n for n in me["names"] if n["id"] == me["preferredNameRef"]][0]["fullText"], "Nan")
        self.assertNotIn("givenParts", me["names"][0], "the name was not split")
        self.assertEqual([a["value"] for a in me["person.pronouns"]], ["she/her"])
        self.assertEqual(me["person.pronouns"][0]["assertedBy"], "operator", "never labelled the narrator's")
        ev = rec["events"][0]
        self.assertEqual(ev["date"], {"text": "around 1939", "value": "1939~", "precision": "year"},
                         "approximate words keep their words; no day is invented")
        self.assertEqual(rec["places"][0]["label"], "Minot, North Dakota")

    def test_an_exact_day_is_a_day(self):
        establish_narrator(NORA, full_name="Nora Whitfield", birth_date="1939-08-30")
        self.assertEqual(W.read_record(NORA)["events"][0]["date"],
                         {"text": "1939-08-30", "value": "1939-08-30", "precision": "day"})

    # C-4F — the intake's REQUIRED "currently lives in" is canonical, not legacy-only
    def test_the_current_residence_is_one_place_and_one_current_home(self):
        r = establish_narrator(NORA, full_name="Nora Whitfield", current_residence="Las Vegas, NM")
        self.assertTrue(r["ok"], r)
        rec = W.read_record(NORA)
        self.assertEqual([p["label"] for p in rec["places"]], ["Las Vegas, NM"], "the text as typed, one place")
        homes = [e for e in rec["events"] if e["type"] == "move"]
        self.assertEqual(len(homes), 1)
        h = homes[0]
        self.assertEqual((h["place"], h["participants"], h.get("attributes")),
                         (rec["places"][0]["id"], [{"person": NORA, "role": "resident"}], {"current": True}),
                         "explicitly current")
        self.assertNotIn("date", h, "no start date is invented; no end is inferred")
        self.assertNotIn("dateAssertions", h)

    def test_a_multi_level_residence_stays_one_place_and_one_home(self):
        label = "412 Elm Street, South Side, Chicago, Illinois"
        establish_narrator(NORA, full_name="Nora Whitfield", current_residence=label)
        rec = W.read_record(NORA)
        self.assertEqual([(p["label"], p.get("parts")) for p in rec["places"]], [(label, None)],
                         "never split into street / neighbourhood / city — parts are supplied, not guessed")
        self.assertEqual(len([e for e in rec["events"] if e["type"] == "move"]), 1)

    def test_no_residence_no_home(self):
        establish_narrator(NORA, full_name="Nora Whitfield", current_residence="   ")
        self.assertEqual(W.read_record(NORA)["events"], [])

    def test_no_name_no_write(self):
        self.assertFalse(establish_narrator(NORA, full_name="  ")["ok"])
        self.assertEqual(W.read_record(NORA)["revision"], 0)


@unittest.skipUnless(_HAVE_FASTAPI, "fastapi is not importable under this interpreter")
class CreateRouteEstablishes(_Db):
    def test_create_fictional_narrator_route_writes_the_life_record(self):
        app = FastAPI()
        app.include_router(_people_router.router)
        c = TestClient(app)
        r = c.post("/api/people", json={"display_name": "Probe Fictional", "role": "",
                                        "narrator_type": "live", "testing_only": True})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["life_record"]["ok"], body)
        rec = W.read_record(body["person_id"])
        self.assertEqual([n["fullText"] for n in rec["people"][0]["names"]], ["Probe Fictional"])

    def test_the_intake_route_establishes_the_current_residence_in_the_record(self):
        app = FastAPI()
        app.include_router(_people_router.router)
        r = TestClient(app).post("/api/people/intake", json={
            "full_legal_name": "Probe Fictional", "preferred_name": "Probe",
            "date_of_birth": "1939", "place_of_birth": "Minot", "pronouns": "she_her",
            "current_residence": "Las Vegas, NM", "testing_only": True})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["life_record"]["ok"], body)
        rec = W.read_record(body["person_id"])
        homes = [e for e in rec["events"] if e["type"] == "move"]
        self.assertEqual(len(homes), 1, rec["events"])
        place = {p["id"]: p["label"] for p in rec["places"]}[homes[0]["place"]]
        self.assertEqual((place, homes[0].get("attributes")), ("Las Vegas, NM", {"current": True}))
        self.assertNotIn("date", homes[0])


if __name__ == "__main__":
    unittest.main()
