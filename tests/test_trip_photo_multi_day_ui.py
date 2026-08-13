"""WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01 Phase 3 — the operator surface.

Phase 2 made trip_photo_day_placements authoritative and turned the
day-photo route into an ADD. It deliberately did not touch the
interface, so the shipped product spent one commit saying "Move to this
day" over a route that added, and calling a photograph on two days
"Unplaced" because the compatibility scalar is null by rule when there
are several. This suite guards the surface that closes both.

WHY THESE ARE SOURCE SCANS. This module has no DOM harness; the two
liveness scripts under scripts/ui/ drive a real browser and are the
right instrument for mount/teardown. What is asserted here is a
different kind of claim — "no code path answers the where-is-this-photo
question by reading the single scalar" — which is a property of the
TEXT, holds for paths no test has exercised yet, and would be missed by
any fixture that happens not to build a two-day photograph.

The one rule this file must not break, learned four times in this
repository: a guard written against a WORD fires on prose that quotes
the word. Every scan below runs over comment-stripped source, and the
production comments deliberately quote the retired labels.

Run per-module:
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_trip_photo_multi_day_ui
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tests import travel_doc_surfaces as _tds  # noqa: E402

_JS_PATH = _tds.UNIFIED_JS.path


def _js() -> str:
    return _tds.UNIFIED_JS.stripped()


def _raw() -> str:
    return _JS_PATH.read_text(encoding="utf-8")


def _fn(name: str) -> str:
    """The body of one top-level function, comment-stripped."""
    src = _js()
    start = src.index("function " + name + "(")
    depth = 0
    i = src.index("{", start)
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
    raise AssertionError("unterminated function %s" % name)


class OneDefinitionOfWhereAPhotographIsTest(unittest.TestCase):
    """`linkDayIds` is the single answer, and everything asks it."""

    def test_the_helpers_exist(self):
        src = _js()
        for name in ("function linkDayIds(", "function linkIsOnDay(",
                     "function dayListText("):
            self.assertIn(name, src, "missing %s" % name)

    def test_unplaced_means_no_stop_and_zero_placements(self):
        body = _fn("linkIsUnplaced")
        self.assertIn("!l.trip_stop_id", body)
        self.assertIn("linkDayIds(l).length", body)
        self.assertNotIn("l.trip_day_id", body,
                         "unplaced still consults the compatibility scalar, "
                         "which is null for a photograph on several days")

    def test_the_day_photo_list_reads_the_placement_set(self):
        body = _fn("dayLinkedPhotoLinks")
        self.assertIn("linkIsOnDay(", body)
        self.assertNotIn("l.trip_day_id === day.id", body)

    def test_suggestions_exclude_only_this_day(self):
        """§7's narrower rule: a photograph placed on Day 1 whose taken
        date is Day 3 is still the right suggestion for Day 3. The old
        client rule excluded anything placed ANYWHERE."""
        body = _fn("dateMatchedPhotoLinks")
        self.assertIn("!linkIsOnDay(l, day.id)", body)
        self.assertNotIn("!l.trip_day_id", body)

    def test_only_linkDayIds_may_read_the_compatibility_scalar(self):
        """The whole point, as one assertion.

        Anything else reading `l.trip_day_id` is a path that answers
        "which day is this photograph on" with a value that is null
        whenever the answer is 'several' — which is silent, and wrong in
        the direction of losing the operator's most deliberate work.
        """
        src = _js()
        offenders = []
        for m in re.finditer(r"\b(l|link|sel)\.trip_day_id\b", src):
            line_no = src[:m.start()].count("\n") + 1
            line = src.split("\n")[line_no - 1].strip()
            # linkDayIds is the sanctioned reader and the only one.
            if "Array.isArray(l.trip_day_ids)" in line:
                continue
            if line.startswith("return l.trip_day_id ? [l.trip_day_id] : [];"):
                continue
            offenders.append("%d: %s" % (line_no, line[:100]))
        self.assertEqual(offenders, [],
                         "photo-day scalar read outside linkDayIds: %r"
                         % (offenders,))


class TheLabelMatchesWhatTheRouteDoesTest(unittest.TestCase):
    """The defect Phase 3 exists to close: the button said Move, the
    route added, and nothing on screen mentioned the second day."""

    def test_the_photo_picker_says_add(self):
        body = _fn("renderPhotoPicker")
        self.assertIn('"Add"', body)
        self.assertIn("Add to this day too", body)
        self.assertIn("Add selected to ", body)

    def test_the_photo_picker_no_longer_promises_a_move(self):
        body = _fn("renderPhotoPicker")
        self.assertNotIn("Move to this day", body)
        self.assertNotIn("photo(s) will move from other days.", body)
        self.assertNotIn('"Attach"', body)

    def test_a_photo_already_on_a_day_is_still_offered(self):
        """It is addable, not filtered out and not disabled: being on
        Day 1 is not a reason it cannot also belong to Day 3."""
        body = _fn("renderPhotoPicker")
        self.assertIn("!linkIsOnDay(l, day.id)", body,
                      "the picker must exclude only THIS day's photos")

    def test_the_notice_states_the_consequence_rather_than_warning(self):
        body = _fn("renderPhotoPicker")
        self.assertIn("are already on another day and will be on", body)

    def test_the_source_picker_is_deliberately_unchanged(self):
        """A trip_source still has one `trip_day_id`, so for sources the
        move doctrine is still correct. The two pickers differ on
        purpose; asserting it here stops a later pass from unifying
        them in the wrong direction."""
        src = _js()
        self.assertIn("Move to this day", src)
        self.assertIn("source(s) will move from other days.", src)


class TheDayInspectorShowsBothSurfacesTest(unittest.TestCase):
    """§8: On this day, and Photo library / suggestions."""

    def test_the_two_headings(self):
        src = _js()
        self.assertIn('"On this day"', src)
        self.assertIn('"Taken on this date"', src)

    def test_remove_and_move_are_distinct_actions(self):
        src = _js()
        self.assertIn("Remove from this day", src)
        self.assertIn('"Move…"', src)
        self.assertIn("function openPlacementMove(", src)
        self.assertIn("function movePlacement(", src)

    def test_a_placement_row_names_the_other_days(self):
        """"Remove from this day" is only readable as the narrow act it
        is if the operator can see the photograph is also elsewhere."""
        src = _js()
        self.assertIn("also on ", src)
        self.assertIn("dayListText(others)", src)

    def test_a_suggestion_row_can_be_added_directly(self):
        src = _js()
        self.assertIn('"Add to this day"', src)
        self.assertIn("addPhotosToDay(day, [l.id])", src)


class MoveNamesBothEndsTest(unittest.TestCase):

    def test_the_move_state_carries_the_source_day(self):
        src = _js()
        self.assertIn("placementMove", src)
        body = _fn("openPlacementMove")
        self.assertIn("fromDayId", body)
        self.assertIn("linkId", body)

    def test_the_request_sends_all_three_ids(self):
        body = _fn("movePlacement")
        for field in ("photo_link_id", "from_day_id", "to_day_id"):
            self.assertIn(field, body)
        self.assertIn("/photos/placement-move", body)

    def test_the_drawer_says_which_day_it_moves_from(self):
        body = _fn("renderPlacementMove")
        self.assertIn('"from " + dayChipText(fromDay)', body)
        self.assertIn("Only the ", body)

    def test_moving_onto_a_day_it_already_occupies_is_labelled(self):
        body = _fn("renderPlacementMove")
        self.assertIn("already here", body)
        self.assertIn("Move here (removes the other)", body)

    def test_the_move_drawer_is_cleared_on_trip_switch(self):
        """A drawer left open across a trip switch would be offering
        Trip A's days for Trip B's photograph."""
        src = _js()
        self.assertIn("st.placementMove = null;", src)


class BatchingRespectsTheServerLimitTest(unittest.TestCase):

    def test_a_large_selection_is_batched_not_refused(self):
        body = _fn("addPhotosToDay")
        self.assertIn("PLACEMENT_BATCH_MAX", body)
        self.assertIn("splice(0, PLACEMENT_BATCH_MAX)", body)
        # And the batches are what gets SENT. A mutation replacing
        # `batches.reduce(` with `[ids].reduce(` left both strings above
        # present — the splice still ran, its result was just thrown
        # away — so this test passed on code that posted all 51 in one
        # call. Asserting the collection the loop actually walks is the
        # difference between checking that batching was computed and
        # checking that it was used.
        self.assertIn("batches.reduce(", body)

    def test_the_limit_matches_the_servers(self):
        src = _js()
        self.assertIn("var PLACEMENT_BATCH_MAX = 50;", src)
        server = (_REPO_ROOT / "server" / "code" / "api" / "routers"
                  / "trips.py").read_text(encoding="utf-8")
        self.assertIn("PLACEMENT_BATCH_MAX = 50", server,
                      "the client and server batch limits have drifted")

    def test_batches_are_sequential_so_order_survives(self):
        """Each call assigns ord after the day's current maximum, so
        concurrent batches would interleave the operator's order."""
        body = _fn("addPhotosToDay")
        self.assertIn("reduce(", body)
        self.assertNotIn("Promise.all(batches", body)

    def test_the_picker_sends_through_the_batching_path(self):
        body = _fn("renderPhotoPicker")
        self.assertIn("addPhotosToDay(day, ids)", body)


class NoNativeDialogsTest(unittest.TestCase):
    """Every destructive or reassigning act added by Phase 3 stays
    in-panel. The lab's standing rule, and this is the phase most
    likely to reach for a confirm()."""

    def test_no_native_dialog_is_introduced(self):
        src = _js()
        cleaned = src.replace("paintAttach(", "").replace(
            "paintAttachSources(", "")
        for banned in ("window.confirm(", "window.prompt(", "window.alert(",
                       "confirm(", "prompt(", "alert("):
            self.assertNotIn(banned, cleaned, "native dialog: %s" % banned)


class TheRetiredFrontendStaysOutOfItTest(unittest.TestCase):
    """§8.2. The Phase 0 map found `travel-documenter.js` has ZERO
    photo-day placement code, so there is no legacy page writing the
    scalar authority and nothing to port or lock down. Verified here
    rather than assumed, because §8.2 asks for one or the other and
    'neither, because the hazard does not exist' is only an acceptable
    answer if it is checked."""

    def test_the_retired_module_has_no_photo_day_code(self):
        doc = _tds.RETIRED_JS.stripped()
        self.assertNotIn("trip_day_id", doc)
        self.assertNotIn("photos/link", doc)
        self.assertNotIn("photos/unlink", doc)
        self.assertNotIn("placement-move", doc)

    def test_it_is_still_served_and_still_unmounted(self):
        """Deleting it is a different work order. What matters here is
        that it cannot write placement."""
        self.assertTrue(_tds.RETIRED_JS.path.exists())
        self.assertFalse(_tds.RETIRED_JS.on_operator_path)


class OperatorGuaranteesFromTheEarlierPhaseSurviveTest(unittest.TestCase):
    """§10 Phase 3: the landed `5d1a4fa` behaviours must not be reset or
    bypassed by multi-day photo rendering."""

    def test_the_saved_chip_is_still_stamped_only_after_success(self):
        src = _js()
        self.assertIn("st.daySavedAt = new Date().toLocaleTimeString(", src)
        # Still inside the .then, after the PATCH and the reload.
        i = src.index("st.daySavedAt = new Date()")
        before = src[:i]
        self.assertIn('{ method: "PATCH", body: body_ }', before)
        self.assertIn("return reloadDays();", before)

    def test_the_inspector_scroll_position_is_still_preserved(self):
        src = _js()
        self.assertIn("st.insScroll", src)

    def test_no_teardown_unsafe_timer_was_added(self):
        """setTimeout/setInterval each need a destroyed guard or a
        stored handle cleared in destroy(). Phase 3 adds neither, and
        this asserts the count did not move."""
        src = _js()
        self.assertEqual(src.count("setInterval("), 0)
        # Exactly the three that were here before Phase 3: the picker
        # poll, the export URL revoke, and Lori's send-retry ladder.
        # Equality, not a ceiling — the number is the inventory, and a
        # ceiling would let a fourth appear the moment one was removed.
        self.assertEqual(
            src.count("setTimeout("), 3,
            "the timer count moved; a new timer needs a destroyed guard "
            "or a stored handle cleared in destroy(). See the timer "
            "inventory in tests/test_travel_doc_lab.py.")


if __name__ == "__main__":
    unittest.main()
