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
        self.assertEqual(ev["date"], {"text": "around 1939", "value": None, "precision": "unknown"},
                         "approximate words keep their words; no day is invented")
        self.assertEqual(rec["places"][0]["label"], "Minot, North Dakota")

    def test_an_exact_day_is_a_day(self):
        establish_narrator(NORA, full_name="Nora Whitfield", birth_date="1939-08-30")
        self.assertEqual(W.read_record(NORA)["events"][0]["date"],
                         {"text": "1939-08-30", "value": "1939-08-30", "precision": "day"})

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


if __name__ == "__main__":
    unittest.main()
