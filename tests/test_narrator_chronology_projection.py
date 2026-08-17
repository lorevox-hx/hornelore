"""WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 commit 3 — ONE server chronology.

The Life Map's periods lived only in browser localStorage under
`lorevox.spine.<person_id>`. There was no server row to reconcile a second
browser against -- a sharper problem than the projection defect, not a milder
one: there a server row existed and was being clobbered, here there was nothing
to clobber.

Supervisor requirement (2026-08-16): do NOT build a second chronology engine.
`/api/chronology-accordion` already carries profile identity, promoted truth,
derived spine events, trips and historical context, so it is EXTENDED and the
Life Map consumes it. These tests pin that there is exactly one engine, that
the canonical taxonomy is unchanged (six historical eras PLUS the separate
`today` current-life bucket), and that the added lanes tell the truth about
their own status.

pytest is not installed in this repo. Run with:

    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_narrator_chronology_projection
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fastapi import FastAPI  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from api import db as _db  # noqa: E402
from api.lv_eras import LV_ERAS  # noqa: E402
from api.routers import chronology_accordion as ca  # noqa: E402

from tests.source_scan_helpers import strip_js_comments  # noqa: E402

_APP_JS = _REPO_ROOT / "ui" / "js" / "app.js"
_LIFEMAP_JS = _REPO_ROOT / "ui" / "js" / "life-map.js"
_API_JS = _REPO_ROOT / "ui" / "js" / "api.js"


class ExactlyOneChronologyEngine(unittest.TestCase):
    """Supervisor requirement: no second engine beside the accordion."""

    def test_the_standalone_service_does_not_exist(self):
        self.assertFalse(
            (_SERVER_CODE / "api" / "services" / "narrator_chronology.py").exists(),
            "a parallel chronology service is exactly what this commit must not add",
        )

    def test_no_separate_narrator_chronology_route(self):
        src = (_SERVER_CODE / "api" / "routers" / "narrator_state.py").read_text(encoding="utf-8")
        self.assertNotIn("/chronology", src)

    def test_the_browser_calls_the_accordion(self):
        app = strip_js_comments(_APP_JS.read_text(encoding="utf-8"))
        self.assertIn("API.CHRONOLOGY_ACCORDION", app)
        self.assertNotIn("NARRATOR_CHRONOLOGY(", app)

    def test_the_retired_endpoint_constant_is_gone(self):
        api = strip_js_comments(_API_JS.read_text(encoding="utf-8"))
        self.assertNotIn("NARRATOR_CHRONOLOGY:", api)


class CanonicalTaxonomyIsUnchanged(unittest.TestCase):
    """SIX historical eras PLUS the separate Today bucket. Today is not removed."""

    def test_six_historical_eras_then_today(self):
        periods = ca.build_scaffold_periods(1950, "Rivertown, Example")
        self.assertEqual(len(periods), 7)
        self.assertEqual(
            [p["era_id"] for p in periods],
            [
                "earliest_years",
                "early_school_years",
                "adolescence",
                "coming_of_age",
                "building_years",
                "later_years",
                "today",
            ],
        )

    def test_today_is_present_and_flagged_as_current_life(self):
        today = [p for p in ca.build_scaffold_periods(1950) if p["era_id"] == "today"][0]
        self.assertTrue(today["is_current_life"])
        self.assertIsNone(today["start_year"])
        self.assertIsNone(today["end_year"])

    def test_today_is_never_produced_by_year_arithmetic(self):
        # It is IN the taxonomy and OUT of the derivation. Both matter.
        periods = ca.build_scaffold_periods(1950)
        for year in (1950, 1963, 1999, 2026, 2100):
            with self.subTest(year=year):
                self.assertNotEqual(ca.year_to_era(year, periods), "today")

    def test_year_to_era_still_maps_the_historical_eras(self):
        periods = ca.build_scaffold_periods(1950)
        self.assertEqual(ca.year_to_era(1950, periods), "earliest_years")
        self.assertEqual(ca.year_to_era(1958, periods), "early_school_years")
        self.assertEqual(ca.year_to_era(2038, periods), "later_years")
        self.assertIsNone(ca.year_to_era(1888, periods))

    def test_boundaries_track_lv_eras_exactly(self):
        periods = {p["era_id"]: p for p in ca.build_scaffold_periods(1950)}
        for era in LV_ERAS:
            if era["era_id"] == "today" or era.get("ageStart") is None:
                continue
            p = periods[era["era_id"]]
            self.assertEqual(p["start_year"], 1950 + era["ageStart"])
            if era.get("ageEnd") is None:
                self.assertIsNone(p["end_year"])
            else:
                self.assertEqual(p["end_year"], 1950 + era["ageEnd"])

    def test_label_still_carries_the_era_id(self):
        # WO-CANONICAL-LIFE-SPINE-01 Step 3d contract.
        for p in ca.build_scaffold_periods(1950):
            self.assertEqual(p["label"], p["era_id"])

    def test_birthplace_lands_only_on_the_first_era(self):
        periods = ca.build_scaffold_periods(1950, "Rivertown, Example")
        self.assertEqual(periods[0]["places"], ["Rivertown, Example"])
        self.assertEqual(periods[0]["notes"], ["Born in Rivertown, Example"])
        for p in periods[1:]:
            self.assertEqual(p["places"], [])

    def test_missing_birthplace_leaves_places_empty(self):
        self.assertEqual(ca.build_scaffold_periods(1950, "")[0]["places"], [])


class _DbBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        tmp.close()
        self.db_path = Path(tmp.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()

        app = FastAPI()
        app.include_router(ca.router)
        self.client = TestClient(app, raise_server_exceptions=False)

        self.person_id = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO people (id, display_name, date_of_birth, place_of_birth, "
            "created_at, updated_at) VALUES (?, 'Test Narrator One', "
            "'1950-03-11', 'Rivertown, Example', '2026-08-16', '2026-08-16')",
            (self.person_id,),
        )
        con.commit()
        con.close()
        self._set_basics({"dob": "1950-03-11", "pob": "Rivertown, Example"})

    def tearDown(self):
        self.client.close()
        _db.DB_PATH = self._orig_db
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def _con(self):
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        return con

    def _set_basics(self, basics):
        _db.ensure_profile(self.person_id)
        con = self._con()
        con.execute(
            "UPDATE profiles SET profile_json=? WHERE person_id=?",
            (json.dumps({"basics": basics, "kinship": [], "pets": []}), self.person_id),
        )
        con.commit()
        con.close()

    def _get(self, pid=None):
        return self.client.get(
            f"/api/chronology-accordion?person_id={pid or self.person_id}"
        )


class UnifiedProjectionContract(_DbBase):
    def test_the_payload_carries_the_spine_the_browser_needs(self):
        body = self._get().json()
        self.assertTrue(body["seed_ready"])
        self.assertEqual(body["birth_date"], "1950-03-11")
        self.assertEqual(body["birth_place"], "Rivertown, Example")
        self.assertEqual(len(body["periods"]), 7)
        first = body["periods"][0]
        for key in ("era_id", "label", "start_year", "end_year",
                    "is_approximate", "is_current_life", "places", "notes",
                    "source", "status"):
            self.assertIn(key, first)

    def test_the_three_new_lanes_are_present(self):
        body = self._get().json()
        for key in ("timeline_events", "story_evidence", "trip_days"):
            self.assertIn(key, body)
            self.assertIsInstance(body[key], list)

    def test_sources_declare_authority_and_per_lane_status(self):
        s = self._get().json()["sources"]
        self.assertEqual(s["authority"], "server")
        for lane in ("periods", "timeline_events", "story_evidence", "trip_days"):
            self.assertIn("source", s[lane])
            self.assertIn("status", s[lane])

    def test_no_dob_is_a_state_and_today_still_appears(self):
        # Current life does not depend on a birth year.
        self._set_basics({})
        con = self._con()
        con.execute("UPDATE people SET date_of_birth='' WHERE id=?", (self.person_id,))
        con.commit()
        con.close()
        body = self._get().json()
        self.assertEqual(body["reason"], "no_dob")
        self.assertFalse(body["seed_ready"])
        self.assertEqual([p["era_id"] for p in body["periods"]], ["today"])
        self.assertEqual(body["sources"]["periods"]["status"], "unavailable_no_dob")

    def test_missing_person_is_404(self):
        self.assertEqual(self._get(str(uuid.uuid4())).status_code, 404)


class ConfirmedTimelineEventsLane(_DbBase):
    def _add_event(self, date="1963-06-01", title="Moved to Midland", status=None):
        eid = str(uuid.uuid4())
        con = self._con()
        con.execute(
            "INSERT INTO timeline_events(id,person_id,date,title,body,kind,created_at,meta_json"
            + (",status" if status else "") + ") VALUES(?,?,?,?,'','event','2026-08-16','{}'"
            + (",?" if status else "") + ")",
            (eid, self.person_id, date, title) + ((status,) if status else ()),
        )
        con.commit()
        con.close()
        return eid

    def test_events_appear_with_a_year(self):
        self._add_event()
        events = self._get().json()["timeline_events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["year"], 1963)
        self.assertEqual(events[0]["label"], "Moved to Midland")

    def test_status_is_reported_from_the_row(self):
        self._add_event(status="provisional")
        self.assertEqual(self._get().json()["timeline_events"][0]["status"], "provisional")

    def test_status_comes_from_the_column_not_from_an_assumption(self):
        # `timeline_events.status` carries a schema default of 'reviewed'.
        # It is reported verbatim rather than being relabelled to
        # something more flattering -- the point of the lane is that the
        # Life Map can see what the row actually claims.
        self._add_event()
        con = self._con()
        stored = con.execute(
            "SELECT status FROM timeline_events WHERE person_id=?", (self.person_id,)
        ).fetchone()["status"]
        con.close()
        self.assertEqual(self._get().json()["timeline_events"][0]["status"], stored)

    def test_a_null_status_falls_back_to_confirmed(self):
        self._add_event()
        con = self._con()
        con.execute("UPDATE timeline_events SET status=NULL WHERE person_id=?", (self.person_id,))
        con.commit()
        con.close()
        self.assertEqual(self._get().json()["timeline_events"][0]["status"], "confirmed")

    def test_an_undateable_event_is_dropped_rather_than_guessed(self):
        self._add_event(date="sometime")
        self.assertEqual(self._get().json()["timeline_events"], [])

    def test_another_narrators_events_are_not_included(self):
        other = str(uuid.uuid4())
        con = self._con()
        con.execute(
            "INSERT INTO people(id,display_name,created_at,updated_at) "
            "VALUES(?,'Test Narrator Two','2026-08-16','2026-08-16')", (other,))
        con.execute(
            "INSERT INTO timeline_events(id,person_id,date,title,body,kind,created_at,meta_json) "
            "VALUES(?,?,'1980-01-01','Theirs','','event','2026-08-16','{}')",
            (str(uuid.uuid4()), other),
        )
        con.commit()
        con.close()
        self.assertEqual(self._get().json()["timeline_events"], [])


class StoryEvidenceCarriesItsStatus(_DbBase):
    def _add_story(self, review="unreviewed", confidence="low", year_low=1958):
        sid = str(uuid.uuid4())
        con = self._con()
        con.execute(
            "INSERT INTO story_candidates(id,narrator_id,created_at,transcript,"
            "trigger_reason,estimated_year_low,confidence,review_status) "
            "VALUES(?,?,'2026-08-16','the barn burned down','manual',?,?,?)",
            (sid, self.person_id, year_low, confidence, review),
        )
        con.commit()
        con.close()
        return sid

    def test_promoted_reads_approved(self):
        self._add_story(review="promoted")
        self.assertEqual(self._get().json()["story_evidence"][0]["status"], "approved")

    def test_unreviewed_reads_provisional(self):
        self._add_story(review="unreviewed")
        self.assertEqual(self._get().json()["story_evidence"][0]["status"], "provisional")

    def test_discarded_is_excluded(self):
        self._add_story(review="discarded")
        self.assertEqual(self._get().json()["story_evidence"], [])

    def test_a_worked_out_year_is_labelled_derived_not_stated(self):
        # The difference between "they told us" and "we computed it from a
        # date of birth" must not be blurred.
        self._add_story(confidence="low")
        self.assertEqual(self._get().json()["story_evidence"][0]["placement"], "derived")

    def test_a_high_confidence_year_is_labelled_stated(self):
        self._add_story(confidence="high")
        self.assertEqual(self._get().json()["story_evidence"][0]["placement"], "stated")

    def test_the_excerpt_is_bounded(self):
        self.assertLessEqual(
            len(self._get_excerpt()), 280
        )

    def _get_excerpt(self):
        self._add_story()
        return self._get().json()["story_evidence"][0]["excerpt"]


class TripDaysNotJustATripHeading(_DbBase):
    def _add_trip_with_days(self, n=3):
        trip_id = str(uuid.uuid4())
        con = self._con()
        con.execute(
            "INSERT INTO trips(id,person_id,title,created_at,updated_at) "
            "VALUES(?,?,'France 2019','2026-08-16','2026-08-16')",
            (trip_id, self.person_id),
        )
        for i in range(n):
            con.execute(
                "INSERT INTO trip_days(id,trip_id,day_index,date,title,main_location) "
                "VALUES(?,?,?,?,?,?)",
                (str(uuid.uuid4()), trip_id, i + 1, f"2019-06-0{i + 1}",
                 f"Day {i + 1}", "Paris"),
            )
        con.commit()
        con.close()
        return trip_id

    def test_every_day_is_returned_not_one_trip_row(self):
        self._add_trip_with_days(3)
        days = self._get().json()["trip_days"]
        self.assertEqual(len(days), 3)
        self.assertEqual({d["year"] for d in days}, {2019})

    def test_a_day_carries_its_own_place_and_its_trip(self):
        self._add_trip_with_days(1)
        d = self._get().json()["trip_days"][0]
        self.assertEqual(d["trip_title"], "France 2019")
        self.assertEqual(d["main_location"], "Paris")
        self.assertEqual(d["day_index"], 1)

    def test_travels_is_flagged_as_a_shelf_not_an_era(self):
        self._add_trip_with_days(1)
        self.assertEqual(self._get().json()["trip_days"][0]["shelf"], "travels")

    def test_lane_counts_include_the_new_lanes(self):
        self._add_trip_with_days(2)
        counts = self._get().json()["lane_counts"]
        self.assertEqual(counts["trip_days"], 2)
        self.assertIn("timeline_events", counts)
        self.assertIn("story_evidence", counts)


class TheProjectionWritesNothing(_DbBase):
    """The authority contract this router already declared for itself."""

    def _snapshot(self):
        con = self._con()
        rows = {}
        for (name,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall():
            rows[name] = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        con.close()
        return rows

    def test_no_table_gains_or_loses_a_row(self):
        before = self._snapshot()
        for _ in range(3):
            self.assertEqual(self._get().status_code, 200)
        self.assertEqual(before, self._snapshot())

    def test_no_chronology_table_was_introduced(self):
        # The spine is derived, not stored. A table would be a second
        # thing to keep in sync with the profile.
        tables = self._snapshot()
        self.assertNotIn("narrator_chronology", tables)
        self.assertNotIn("eras", tables)

    def test_the_new_lanes_contain_no_write_verbs(self):
        src = (_SERVER_CODE / "api" / "routers" / "chronology_accordion.py").read_text(
            encoding="utf-8"
        )
        for fn in ("_collect_timeline_events", "_collect_story_evidence", "_collect_trip_days"):
            body = _extract_py_function(src, fn)
            for forbidden in ("INSERT ", "UPDATE ", "DELETE ", "commit("):
                with self.subTest(fn=fn, forbidden=forbidden):
                    self.assertNotIn(forbidden, body)


def _extract_py_function(src: str, name: str) -> str:
    m = re.search(r"^def " + re.escape(name) + r"\(", src, re.M)
    if not m:
        raise AssertionError(f"{name} not found")
    rest = src[m.start():]
    nxt = re.search(r"\n(?=def |# ─── )", rest[1:])
    return rest[: nxt.start() + 1] if nxt else rest


class BrowserConsumesTheOneProjection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = strip_js_comments(_APP_JS.read_text(encoding="utf-8"))
        cls.lifemap = strip_js_comments(_LIFEMAP_JS.read_text(encoding="utf-8"))

    def test_load_person_awaits_hydration(self):
        self.assertRegex(self.app, r"await\s+_hydrateChronologyFromServer\s*\(\s*pid")

    def test_server_periods_replace_the_cached_spine(self):
        self.assertRegex(self.app, r"periods:\s*j\.periods")
        self.assertIn("saveSpineLocal()", self.app)

    def test_the_whole_projection_is_kept_not_just_the_spine(self):
        self.assertRegex(self.app, r"state\.chronologyProjection\s*=\s*j")

    def test_request_is_cancelled_on_narrator_switch(self):
        self.assertIn("_chronoAbort", self.app)
        self.assertRegex(self.app, r"_chronoAbort\.abort\(\)")
        self.assertIn("AbortController", self.app)

    def test_rapid_clicks_are_deduplicated(self):
        self.assertIn("_chronoInFlight", self.app)

    def test_a_stale_response_is_dropped(self):
        self.assertRegex(self.app, r"gen\s*!==\s*_loadGeneration")

    def test_no_dob_does_not_claim_readiness(self):
        # `today` alone must not be mistaken for a derivable spine.
        self.assertRegex(self.app, r"filter\(p\s*=>\s*!p\.is_current_life\)")

    def test_one_shared_era_dispatcher_exists(self):
        self.assertIn("window.LorevoxEraDispatch", self.app)
        self.assertRegex(self.app, r"selectEra\s*:\s*selectEra")
        self.assertRegex(self.app, r"dispatchEraPrompt\s*:\s*dispatchEraPrompt")

    def test_today_does_not_promote_the_pass_engine(self):
        self.assertRegex(self.app, r'eraId\s*===\s*"today"')

    def test_the_era_prompt_is_deduplicated(self):
        self.assertRegex(self.app, r"duplicate era prompt suppressed")

    def test_life_map_routes_every_era_click_through_the_dispatcher(self):
        # The sequence used to be copy-pasted at four sites. If any of
        # them starts calling setPass directly again, this fails.
        self.assertNotIn("setPass(\"pass2a\")", self.lifemap)
        self.assertIn("LorevoxEraDispatch", self.lifemap)

    def test_life_map_prompts_go_through_the_shared_dispatcher(self):
        self.assertIn("_dispatchEraPrompt", self.lifemap)


if __name__ == "__main__":
    unittest.main()
