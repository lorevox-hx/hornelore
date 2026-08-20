"""WO-MEMOIR-TRIP-STORY-LANE-01 — approved trip stories reach the memoir,
unapproved ones never do, and the two-surface rule stays intact.

BACKGROUND. WO-EXPORT-ARCHIVE-WRITER-BRIDGE-01 was opened on the premise
that the archive filesystem writer had stopped and Travel Doc turns
needed an archive.append_event() bridge. Diagnosis (2026-07-27) closed
that work order as no-defect: the writer is healthy, and travel_doc_modal
turns are excluded from the narrator's life-story archive DELIBERATELY --
the two-surface rule of 2026-07-09, locked by
tests/test_modal_archive_boundary.py after
BUG-MODAL-TURNS-ARCHIVED-AS-LIFE-STORY-01 put operator workspace chatter
into the Narrator Room as the narrator's own words.

The real gap was elsewhere: Travel Doc modal turns are captured to
trip_location_notes, but the narrator memoir DOCX had no lane for them,
and every one of the twelve live notes sat at include_in_memoir=0.

This lane closes that gap the sanctioned way -- a DB read gated on the
operator's explicit approval -- and this file exists so it never drifts
back into an archive write.
"""
from __future__ import annotations

import ast
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

# Offline stubs (fastapi/pydantic may be absent in the test env).
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
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)

    def _field(default=None, default_factory=None, **k):
        if default_factory is not None:
            return default_factory()
        return default

    pstub.BaseModel = _BaseModel
    pstub.Field = _field
    sys.modules["pydantic"] = pstub

from api.routers import memoir_export            # noqa: E402
from api.services import trip_repository         # noqa: E402

_PERSON = "person-under-test"
_MEMOIR_SRC = (_SERVER_CODE / "api" / "routers" / "memoir_export.py").read_text(
    encoding="utf-8")


def _note(text, approved, title=None, ord_=0):
    return {
        "id": f"note-{ord_}",
        "note_title": title,
        "note_text": text,
        "include_in_memoir": 1 if approved else 0,
        "source_surface": "travel_doc_modal",
        "hidden": 0,
        "ord": ord_,
    }


class _LaneCase(unittest.TestCase):
    """Stubs the repository so the lane's RULES are under test, not sqlite."""

    def setUp(self):
        # Trips are default-OFF; the lane only runs when they are enabled.
        self._env = mock.patch.dict(os.environ, {"HORNELORE_TRIPS": "1"})
        self._env.start()
        self.addCleanup(self._env.stop)
        self.notes_calls = []
        self.trips = []
        self.notes_by_trip = {}

        def _trip_list(person_id):
            return list(self.trips) if person_id == _PERSON else []

        def _notes_list(trip_id, **kw):
            self.notes_calls.append((trip_id, kw))
            val = self.notes_by_trip.get(trip_id, [])
            if isinstance(val, Exception):
                raise val
            return val

        for name, fn in (("trip_list", _trip_list),
                         ("location_notes_list", _notes_list)):
            p = mock.patch.object(trip_repository, name, fn)
            p.start()
            self.addCleanup(p.stop)

    def _trip(self, tid, title, start_date=None, created_at="2026-01-01T00:00:00Z"):
        self.trips.append({"id": tid, "title": title,
                           "start_date": start_date, "created_at": created_at})
        return tid

    def _sections(self):
        """Just the sections. See the note below for why there are two."""
        return memoir_export._trip_story_sections(_PERSON)[0]

    def _status(self):
        """read / empty / not_attempted / partial / unavailable."""
        return memoir_export._trip_story_sections(_PERSON)[1]


# REPOINTED 2026-08-19 (WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01).
# `_trip_story_sections` now returns `(sections, status)`. The status is
# the point: this lane used to swallow an unreadable trip list into `[]`
# and `continue` past a single unreadable trip, so an approved trip story
# could vanish from a memoir that looked complete. Tests unpack it; the
# two resilience tests that asserted `== []` on a failure now assert what
# the failure IS.


class ApprovalGateTest(_LaneCase):
    def test_approved_note_reaches_the_memoir(self):
        t = self._trip("trip-a", "Bismarck Trip")
        self.notes_by_trip[t] = [_note("I went to Bismarck for work.", True)]
        items = [i for s in self._sections() for i in s.items]
        self.assertIn("I went to Bismarck for work.", items)

    def test_unapproved_note_never_reaches_the_memoir(self):
        # The whole point of the gate: nothing is approved by silence.
        # All twelve live notes sat at include_in_memoir=0 on 2026-07-27.
        t = self._trip("trip-a", "Bismarck Trip")
        self.notes_by_trip[t] = [
            _note("tell me abnout this photo", False),
            _note("hi, i went to bismarck to do some work", False),
        ]
        self.assertEqual(self._sections(), [])

    def test_only_the_approved_half_of_a_mixed_trip_survives(self):
        t = self._trip("trip-a", "Bismarck Trip")
        self.notes_by_trip[t] = [
            _note("Operator scratch question.", False),
            _note("The bronze catfish outside the fishing museum.", True),
        ]
        items = [i for s in self._sections() for i in s.items]
        self.assertEqual(items, ["The bronze catfish outside the fishing museum."])

    def test_hidden_rows_are_left_to_the_repository_default(self):
        # location_notes_list already excludes hidden=1 unless asked.
        # This lane must never pass include_hidden=True.
        t = self._trip("trip-a", "Bismarck Trip")
        self.notes_by_trip[t] = [_note("Approved.", True)]
        self._sections()
        self.assertTrue(self.notes_calls)
        for _tid, kw in self.notes_calls:
            self.assertNotIn("include_hidden", kw)

    def test_blank_note_text_is_skipped(self):
        t = self._trip("trip-a", "Bismarck Trip")
        self.notes_by_trip[t] = [_note("   ", True), _note("", True)]
        self.assertEqual(self._sections(), [])

    def test_trip_with_no_approved_notes_produces_no_section(self):
        self._trip("trip-a", "Bismarck Trip")
        self._trip("trip-b", "Spring 2026 Central Europe")
        self.notes_by_trip["trip-a"] = [_note("unapproved", False)]
        self.notes_by_trip["trip-b"] = [_note("Approved one.", True)]
        sections = self._sections()
        self.assertEqual(len(sections), 1)
        self.assertIn("Spring 2026", sections[0].label)


class PresentationTest(_LaneCase):
    def test_section_is_clearly_sourced_as_travel_material(self):
        t = self._trip("trip-a", "Bismarck Trip")
        self.notes_by_trip[t] = [_note("Approved.", True)]
        s = self._sections()[0]
        self.assertEqual(s.id, "trip_stories_trip-a")
        self.assertIn("travels", s.label.lower())
        self.assertIn("Bismarck Trip", s.label)

    def test_note_title_is_carried_into_the_item(self):
        t = self._trip("trip-a", "Bismarck Trip")
        self.notes_by_trip[t] = [_note(
            "we were to fly on united airlines out of Santa Fe",
            True, title="What do you remember about day 1?")]
        item = self._sections()[0].items[0]
        self.assertTrue(item.startswith("What do you remember about day 1?"))
        self.assertIn("united airlines", item)

    def test_untitled_note_is_rendered_bare(self):
        t = self._trip("trip-a", "Bismarck Trip")
        self.notes_by_trip[t] = [_note("Just the text.", True)]
        self.assertEqual(self._sections()[0].items, ["Just the text."])

    def test_dated_trips_run_chronologically_and_undated_trail(self):
        self._trip("trip-late", "Later", start_date="2026-06-01")
        self._trip("trip-none", "Undated", created_at="2020-01-01T00:00:00Z")
        self._trip("trip-early", "Earlier", start_date="2026-01-01")
        for tid in ("trip-late", "trip-none", "trip-early"):
            self.notes_by_trip[tid] = [_note(f"note for {tid}", True)]
        labels = [s.label for s in self._sections()]
        self.assertEqual(
            labels,
            ["From your travels — Earlier",
             "From your travels — Later",
             "From your travels — Undated"])


class ResilienceTest(_LaneCase):
    def test_trips_flag_off_yields_nothing(self):
        t = self._trip("trip-a", "Bismarck Trip")
        self.notes_by_trip[t] = [_note("Approved.", True)]
        with mock.patch.dict(os.environ, {"HORNELORE_TRIPS": "0"}):
            self.assertEqual(self._sections(), [])

    def test_unreadable_repository_never_raises(self):
        # Memoir export must not fail because trip rows are unreadable.
        def _boom(person_id):
            raise RuntimeError("no such table: trips")
        with mock.patch.object(trip_repository, "trip_list", _boom):
            self.assertEqual(self._sections(), [])

    def test_unreadable_notes_skip_only_that_trip(self):
        self._trip("trip-bad", "Broken")
        self._trip("trip-ok", "Fine")
        self.notes_by_trip["trip-bad"] = RuntimeError("disk gone")
        self.notes_by_trip["trip-ok"] = [_note("Survives.", True)]
        sections = self._sections()
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].items, ["Survives."])

    def test_no_trips_yields_nothing(self):
        self.assertEqual(self._sections(), [])


class TwoSurfaceBoundaryTest(unittest.TestCase):
    """The rule this work order exists to respect, not to work around."""

    def test_the_lane_never_touches_the_archive_writer(self):
        self.assertNotIn(
            "append_event", _MEMOIR_SRC,
            "WO-MEMOIR-TRIP-STORY-LANE-01 is a DB read. If append_event "
            "appears here, someone has rebuilt the archive bridge that "
            "BUG-MODAL-TURNS-ARCHIVED-AS-LIFE-STORY-01 forbids.")

    def test_the_lane_reads_the_trip_repository_not_the_archive_store(self):
        # Inspect the EXECUTABLE body, not the prose: unparse the
        # function with its docstring removed, so the word "archive"
        # appearing in an explanatory comment can never mask a real
        # archive call (or vice versa).
        fn = next(
            n for n in ast.walk(ast.parse(_MEMOIR_SRC))
            if isinstance(n, ast.FunctionDef)
            and n.name == "_trip_story_sections")
        body = list(fn.body)
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            body = body[1:]
        code = "\n".join(ast.unparse(stmt) for stmt in body)
        self.assertIn("trip_repository", code)
        self.assertNotIn("archive", code.lower())

    def test_modal_turns_are_still_barred_from_the_life_story_archive(self):
        # Cross-check: this work order must not have loosened the gates
        # that test_modal_archive_boundary.py owns.
        chat_ws = (_SERVER_CODE / "api" / "routers" / "chat_ws.py").read_text(
            encoding="utf-8")
        self.assertIn("_skip_life_story_archive", chat_ws)
        self.assertIn('== "travel_doc_modal"', chat_ws)
        self.assertIn("_skip_modal_archive = (", chat_ws)


class RouteWiringTest(unittest.TestCase):
    def test_route_appends_trip_sections(self):
        """REPOINTED 2026-08-19. This pinned the append spelling:

            assertIn("list(req.sections) + _trip_sections", block)

        Both server lanes are now collected into `_server_sections` and
        appended once, after a provenance-alignment check, so the old
        literal no longer exists. The property -- the route reads this
        lane and appends what it returns -- is unchanged and is what is
        asserted now.
        """
        i = _MEMOIR_SRC.index("def api_memoir_export_docx")
        block = _MEMOIR_SRC[i:]
        # REPOINTED 2026-08-19: the route now makes ONE call to `canonical_memoir()` instead of running each lane read itself. Two executable interpretations of the lanes was the defect; the property -- this lane reaches the export -- is unchanged.
        self.assertIn("canonical_memoir(", block)
        self.assertIn("_sections_from_canonical(_canon)", block)
        self.assertIn("list(req.sections) + _server_sections", block)

    def test_the_lane_is_opt_outable_and_needs_a_person(self):
        i = _MEMOIR_SRC.index("def api_memoir_export_docx")
        block = _MEMOIR_SRC[i:]
        # REPOINTED 2026-08-19. Retired: `if req.person_id and
        # req.include_trip_stories:` -- the lane no longer has a branch of
        # its own. ONE `canonical_memoir()` call is the authority, so the
        # opt-out travels as an argument to it and the person requirement
        # is the gate on the whole read. Both properties still hold.
        self.assertIn("include_trip_notes=bool(req.include_trip_stories)",
                      block)
        self.assertIn("if req.person_id and (req.include_captured_stories "
                      "or req.include_trip_stories):", block)
        self.assertIn("include_trip_stories: bool = Field(default=True)",
                      _MEMOIR_SRC)

    def test_captured_story_lane_is_still_wired(self):
        # The trip lane is additive. It must not have displaced the
        # WO-MEMOIR-STORY-CANDIDATES-WIRE-01 harvest.
        self.assertIn("canonical_memoir(", _MEMOIR_SRC)  # REPOINTED 2026-08-19: the route now makes ONE call to `canonical_memoir()` instead of running each lane read itself. Two executable interpretations of the lanes was the defect; the property -- this lane reaches the export -- is unchanged.


class TripDocxUntouchedTest(unittest.TestCase):
    def test_trip_docx_still_renders_from_the_trip_memoir_preview(self):
        trips_src = (_SERVER_CODE / "api" / "routers" / "trips.py").read_text(
            encoding="utf-8")
        i = trips_src.index("def export_docx")
        block = trips_src[i:i + 1200]
        self.assertIn("trip_repository.trip_memoir_preview(trip_id)", block)
        self.assertIn("build_trip_docx", block)


if __name__ == "__main__":
    unittest.main()
