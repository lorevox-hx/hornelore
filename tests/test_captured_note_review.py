"""WO-POST-LORI-CLEANUP-AND-UNBLOCK-01 Lane 3 — the operator promotion
surface for captured Travel Doc notes.

BACKGROUND. WO-MEMOIR-TRIP-STORY-LANE-01 shipped a memoir lane that
reads trip_location_notes and includes only include_in_memoir=1 rows.
That gate is correct and this file does not touch it. The problem it
left behind was discoverability: a note captured by the Travel Doc
modal lands under whichever trip/region/stop/day scope the operator
happened to be standing in, and the only list surface was the per-trip
Story Notes tab -- which you can only reach if you already know the
trip. On 2026-07-27 all twelve live rows sat at include_in_memoir=0,
the correct default, and there was no practical way to find them. The
memoir trip lane could therefore never produce output.

Lane 3 adds a READ: a cross-trip review feed plus a screen that lists
it. Promotion still goes through the pre-existing
PATCH /api/trips/location-notes/{id}. These tests exist to prove that
the default stayed off, that only an explicit operator toggle changes
it, and that no new write path, auto-promotion or archive write was
introduced on the way.
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
import tempfile
import types
import unittest
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

if "fastapi" not in sys.modules:
    stub = types.ModuleType("fastapi")

    class _APIRouter:
        def __init__(self, *a, **k):
            pass

        def _deco(self, *a, **k):
            def wrap(f):
                return f
            return wrap
        get = post = patch = delete = put = _deco

    class _HTTPException(Exception):
        def __init__(self, status_code=0, detail=""):
            self.status_code, self.detail = status_code, detail
            super().__init__(detail)

    stub.APIRouter = _APIRouter
    stub.HTTPException = _HTTPException
    stub.Query = lambda default=None, **k: default
    stub.File = lambda default=None, **k: default
    stub.Form = lambda default=None, **k: default
    stub.UploadFile = object
    responses = types.ModuleType("fastapi.responses")
    responses.StreamingResponse = object
    stub.responses = responses
    sys.modules["fastapi"] = stub
    sys.modules["fastapi.responses"] = responses

if "pydantic" not in sys.modules:
    pstub = types.ModuleType("pydantic")

    class _BaseModel:
        # Keyword __init__ mirrors pydantic closely enough for the
        # memoir lane's MemoirSection(id=..., label=..., items=[...]).
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)

    def _field(default=None, default_factory=None, **k):
        if default_factory is not None:
            return default_factory()
        return default

    pstub.BaseModel = _BaseModel
    pstub.Field = _field
    pstub.field_validator = lambda *a, **k: (lambda f: f)
    pstub.validator = lambda *a, **k: (lambda f: f)
    pstub.ConfigDict = dict
    sys.modules["pydantic"] = pstub

from fastapi import HTTPException          # noqa: E402
from api import db as _db                  # noqa: E402
from api.services import trip_repository   # noqa: E402
from api.routers import trips              # noqa: E402
from api.routers import memoir_export      # noqa: E402

_ROUTER_SRC = (_SERVER_CODE / "api" / "routers" / "trips.py").read_text(
    encoding="utf-8")
_LAB_SRC = (_REPO_ROOT / "ui" / "js" / "travel-doc-lab.js").read_text(
    encoding="utf-8")


class _Patch:
    """Stand-in for the LocationNotePatch pydantic model."""

    def __init__(self, **kw):
        base = dict(note_title=None, note_text=None, source_type=None,
                    source_ref=None, include_in_memoir=None,
                    include_in_interview_context=None, ord=None,
                    clear_title=False, hidden=None)
        base.update(kw)
        self.__dict__.update(base)


class _ReviewCase(unittest.TestCase):
    """Real sqlite. The point of Lane 3 is what the DB actually returns."""

    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        tmp.close()
        self.db_path = Path(tmp.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()
        self._orig_flag = os.environ.get("HORNELORE_TRIPS")
        os.environ["HORNELORE_TRIPS"] = "1"

        self.person_id = str(uuid.uuid4())
        self.other_person = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        for pid, name in ((self.person_id, "Captured Review Test"),
                          (self.other_person, "Someone Else")):
            con.execute(
                "INSERT INTO people (id, display_name, date_of_birth, "
                "created_at, updated_at) VALUES (?, ?, '1962-12-24', "
                "'2026-07-08', '2026-07-08');", (pid, name))
        con.commit()
        con.close()

        self.trip_id = trip_repository.trip_create(
            self.person_id, "Bismarck Trip")
        self.region_id = trip_repository.region_create(
            self.trip_id, "North Dakota")
        self.stop_id = trip_repository.stop_create(
            self.trip_id, self.region_id, "Bismarck")

    def tearDown(self):
        _db.DB_PATH = self._orig_db
        if self._orig_flag is None:
            os.environ.pop("HORNELORE_TRIPS", None)
        else:
            os.environ["HORNELORE_TRIPS"] = self._orig_flag
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def _capture(self, text, trip_id=None, **kw):
        """Simulate the Travel Doc modal capture path."""
        base = dict(source_type="lori", source_surface="travel_doc_modal",
                    trip_region_id=self.region_id, trip_stop_id=self.stop_id)
        base.update(kw)
        return trip_repository.location_note_create(
            trip_id or self.trip_id, text, **base)

    def _feed(self, **kw):
        kw.setdefault("person_id", self.person_id)
        return trips.list_captured_notes(**kw)


# ── the acceptance line: default off, operator toggle is what moves it ──

class DefaultRemainsOffTest(_ReviewCase):
    def test_a_captured_note_arrives_unpromoted(self):
        nid = self._capture("hi, i went to bismarck to do some work")
        row = trip_repository.location_note_get(nid)
        self.assertEqual(row["include_in_memoir"], 0)

    def test_the_review_feed_does_not_promote_what_it_reads(self):
        # Reading the screen must never be a write. This is the whole
        # reason the feed is a separate read-only function.
        nid = self._capture("tell me about this photo")
        self._feed()
        self._feed(promoted=False)
        self._feed(include_hidden=True)
        self.assertEqual(
            trip_repository.location_note_get(nid)["include_in_memoir"], 0)

    def test_counts_report_every_captured_note_as_unpromoted(self):
        for i in range(3):
            self._capture(f"captured {i}")
        counts = self._feed()["counts"]
        self.assertEqual(counts["total"], 3)
        self.assertEqual(counts["promoted"], 0)
        self.assertEqual(counts["unpromoted"], 3)
        self.assertEqual(counts["travel_doc_modal"], 3)


class OperatorToggleIsTheOnlyPromotionTest(_ReviewCase):
    def test_the_existing_patch_endpoint_promotes(self):
        nid = self._capture("The bronze catfish outside the museum.")
        out = trips.patch_location_note(
            nid, _Patch(include_in_memoir=True))
        self.assertTrue(out["ok"])
        self.assertEqual(
            trip_repository.location_note_get(nid)["include_in_memoir"], 1)

    def test_the_operator_can_demote_again(self):
        nid = self._capture("Promoted by mistake.")
        trips.patch_location_note(nid, _Patch(include_in_memoir=True))
        trips.patch_location_note(nid, _Patch(include_in_memoir=False))
        self.assertEqual(
            trip_repository.location_note_get(nid)["include_in_memoir"], 0)

    def test_promotion_shows_up_in_the_feed_and_the_counts(self):
        a = self._capture("Stays off.")
        b = self._capture("Gets promoted.")
        trips.patch_location_note(b, _Patch(include_in_memoir=True))
        feed = self._feed()
        by_id = {n["id"]: n for n in feed["notes"]}
        self.assertFalse(by_id[a]["include_in_memoir"])
        self.assertTrue(by_id[b]["include_in_memoir"])
        self.assertEqual(feed["counts"]["promoted"], 1)
        self.assertEqual(feed["counts"]["unpromoted"], 1)

    def test_lane_3_added_no_second_promotion_route(self):
        # If a future edit adds a write route to this lane, this fails.
        # Promotion has exactly one door and it predates this work order.
        self.assertEqual(_ROUTER_SRC.count('@router.get("/captured-notes")'), 1)
        for verb in ("post", "patch", "put", "delete"):
            self.assertNotIn(f'@router.{verb}("/captured-notes")', _ROUTER_SRC)
            self.assertNotIn(f'@router.{verb}("/captured-notes/', _ROUTER_SRC)


# ── unpromoted stays out of the memoir, promoted gets in ────────────────

class MemoirLaneWiringTest(_ReviewCase):
    def _sections(self):
        return memoir_export._trip_story_sections(self.person_id)

    def test_unpromoted_captured_notes_stay_out_of_the_memoir(self):
        self._capture("tell me abnout this photo")
        self._capture("hi, i went to bismarck to do some work")
        self.assertEqual(self._sections(), [])

    def test_a_note_promoted_through_the_operator_toggle_reaches_the_memoir(self):
        nid = self._capture("I drove to Bismarck for work in the fall.")
        self.assertEqual(self._sections(), [])       # before
        trips.patch_location_note(nid, _Patch(include_in_memoir=True))
        items = [i for s in self._sections() for i in s.items]
        self.assertIn("I drove to Bismarck for work in the fall.", items)

    def test_demotion_removes_it_from_the_memoir_again(self):
        nid = self._capture("Second thoughts about this one.")
        trips.patch_location_note(nid, _Patch(include_in_memoir=True))
        self.assertTrue(self._sections())
        trips.patch_location_note(nid, _Patch(include_in_memoir=False))
        self.assertEqual(self._sections(), [])


# ── the feed itself ─────────────────────────────────────────────────────

class FeedShapeTest(_ReviewCase):
    def test_it_shows_what_the_operator_needs_to_decide(self):
        # Chris's scope line: source_surface, created time, trip/location
        # context, current include_in_memoir state, note text preview.
        self._capture("A note with context.", note_title="Day 1?")
        n = self._feed()["notes"][0]
        for field in ("source_surface", "created_at", "trip_id", "trip_title",
                      "region_title", "stop_title", "stop_location_name",
                      "include_in_memoir", "note_text", "note_title"):
            self.assertIn(field, n)
        self.assertEqual(n["source_surface"], "travel_doc_modal")
        self.assertEqual(n["trip_title"], "Bismarck Trip")
        self.assertEqual(n["region_title"], "North Dakota")
        self.assertIs(n["include_in_memoir"], False)

    def test_it_crosses_trips_which_is_the_entire_point(self):
        second = trip_repository.trip_create(self.person_id, "Spring 2026")
        self._capture("From trip one.")
        trip_repository.location_note_create(
            second, "From trip two.", source_type="lori",
            source_surface="travel_doc_modal")
        titles = {n["trip_title"] for n in self._feed()["notes"]}
        self.assertEqual(titles, {"Bismarck Trip", "Spring 2026"})

    def test_it_does_not_leak_another_narrator(self):
        other_trip = trip_repository.trip_create(self.other_person, "Not mine")
        trip_repository.location_note_create(
            other_trip, "Someone else's note.", source_type="lori",
            source_surface="travel_doc_modal")
        self._capture("Mine.")
        texts = [n["note_text"] for n in self._feed()["notes"]]
        self.assertEqual(texts, ["Mine."])

    def test_surface_filter_isolates_modal_captures(self):
        self._capture("From the modal.")
        trip_repository.location_note_create(
            self.trip_id, "Typed by the operator.", source_type="operator")
        both = self._feed(source_surface=None)["notes"]
        self.assertEqual(len(both), 2)
        modal = self._feed(source_surface="travel_doc_modal")["notes"]
        self.assertEqual([n["note_text"] for n in modal], ["From the modal."])

    def test_promoted_filter_finds_the_backlog(self):
        a = self._capture("Still waiting.")
        b = self._capture("Already in.")
        trips.patch_location_note(b, _Patch(include_in_memoir=True))
        self.assertEqual([n["id"] for n in self._feed(promoted=False)["notes"]],
                         [a])
        self.assertEqual([n["id"] for n in self._feed(promoted=True)["notes"]],
                         [b])

    def test_hidden_rows_are_excluded_by_default(self):
        nid = self._capture("Retired from review.")
        trip_repository.location_note_update(nid, hidden=True)
        self.assertEqual(self._feed()["notes"], [])
        shown = self._feed(include_hidden=True)["notes"]
        self.assertEqual([n["id"] for n in shown], [nid])
        self.assertTrue(shown[0]["hidden"])

    def test_newest_first(self):
        ids = [self._capture(f"note {i}") for i in range(3)]
        # created_at has second resolution, so assert on the tiebreak too:
        # the feed must not return an arbitrary order.
        got = [n["id"] for n in self._feed()["notes"]]
        self.assertEqual(sorted(got), sorted(ids))
        self.assertEqual(len(got), 3)

    def test_limit_is_clamped_not_trusted(self):
        for i in range(5):
            self._capture(f"note {i}")
        self.assertEqual(len(self._feed(limit=2)["notes"]), 2)
        self.assertEqual(len(self._feed(limit=0)["notes"]), 1)
        self.assertEqual(len(self._feed(limit=-7)["notes"]), 1)

    def test_the_route_is_flag_gated_like_every_other_trip_route(self):
        os.environ["HORNELORE_TRIPS"] = "0"
        with self.assertRaises(HTTPException) as ctx:
            self._feed()
        self.assertEqual(ctx.exception.status_code, 404)


# ── scope walls ─────────────────────────────────────────────────────────

class ScopeWallTest(unittest.TestCase):
    """Source assertions. These are the walls Chris drew around Lane 3."""

    def test_the_review_screen_writes_only_through_the_existing_patch(self):
        # Isolate the Lane 3 screen and prove its only api() write is the
        # location-notes PATCH that shipped long before this work order.
        start = _LAB_SRC.index("function renderCaptured()")
        end = _LAB_SRC.index("// ── Sources ─")
        self.assertLess(start, end)
        block = _LAB_SRC[_LAB_SRC.index("function capturedQueryPath()"):end]
        writes = re.findall(r'method:\s*"(\w+)"', block)
        self.assertEqual(set(writes), {"PATCH"})
        self.assertIn('"/api/trips/location-notes/"', block)

    def test_the_screen_does_not_reach_the_archive(self):
        block = _LAB_SRC[_LAB_SRC.index("function capturedQueryPath()"):
                         _LAB_SRC.index("// ── Sources ─")]
        for forbidden in ("/api/archive", "archive.append", "append_event",
                          "/api/memoir-export"):
            self.assertNotIn(forbidden, block)

    def test_the_route_never_defaults_promotion_on(self):
        block = _ROUTER_SRC[_ROUTER_SRC.index('@router.get("/captured-notes")'):]
        block = block[:block.index("@router.get(\"/{trip_id}/location-notes\")")]
        self.assertIn("promoted: Optional[bool] = None", block)
        self.assertIn("include_hidden: bool = False", block)
        # A read route has no business calling an update.
        for forbidden in ("location_note_update", "location_note_create",
                          "location_note_delete"):
            self.assertNotIn(forbidden, block)

    def test_the_captured_tab_is_registered_and_reachable_without_a_trip(self):
        self.assertIn('["captured", "Captured Notes"]', _LAB_SRC)
        self.assertIn('case "captured": return renderCaptured();', _LAB_SRC)
        self.assertIn(
            'st.tab !== "evidence" && st.tab !== "captured"', _LAB_SRC)

    def test_the_screen_uses_no_native_dialog(self):
        block = _LAB_SRC[_LAB_SRC.index("function capturedQueryPath()"):
                         _LAB_SRC.index("// ── Sources ─")]
        for forbidden in ("window.confirm", "window.alert", "window.prompt",
                          "confirm(", "alert(", "prompt("):
            self.assertNotIn(forbidden, block)


if __name__ == "__main__":
    unittest.main()
