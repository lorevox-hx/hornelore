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

    def test_a_failed_batch_stops_the_run_without_stopping_the_reload(self):
        """ADDED 2026-08-13.

        The behaviour is proved by executing the function --
        `node scripts/ui/run_photo_placement_safety.js`, which fails
        batch 2 of 120 and asserts 50 added / 2 requests / 1 reload.
        These are the structural properties that harness depends on, so
        that a rewrite which broke them fails here too rather than
        leaving the harness quietly measuring something else.
        """
        body = _fn("addPhotosToDay")
        # The per-batch failure handler: without it the rejection
        # propagates past the reload and the 50 that landed stay
        # invisible until the operator refreshes by hand.
        self.assertIn("failure = e", body)
        self.assertIn("unsent = unsent.concat(batch)", body)
        # The reload is chained off the completed run, not off a
        # success. `.then(` after the chain rather than inside it.
        self.assertIn("reloadDays(), reloadPhotoLinks()", body)
        # The tally reaches the operator.
        self.assertIn('"Added " + added.length + " of " + total', body)
        # And the caller is told what landed, so it can retain exactly
        # the selection that did not.
        self.assertIn("added: added", body)

    def test_the_picker_keeps_the_unadded_selection_after_a_partial_add(self):
        """RETARGETED 2026-08-13 after review.

        This pinned `if (!r.error) st.photoPickerDayId = null;`, which
        closes the drawer whenever no ERROR came back -- including a
        dirty-form refusal, where nothing was sent and every tick is
        still wanted. The condition now also requires that nothing is
        outstanding, which is the property the test was after.
        """
        body = _fn("renderPhotoPicker")
        self.assertIn("delete st.photoPickerChecked[id]", body)
        self.assertIn("if (!r.error && !(r.unsent || []).length)", body,
                      "the drawer must stay open when part of the "
                      "selection did not land")
        self.assertIn("if (r.blocked) { renderAll(); return; }", body,
                      "a refusal must not clear ticks or close the drawer")
        self.assertIn("if (!r || !Array.isArray(r.added))", body,
                      "an unrecognisable result must not be read as success")


class DirtyDayEditsAreProtectedFromPhotoControlsTest(unittest.TestCase):
    """ADDED 2026-08-13.

    Every day-inspector photo control ends in reloadDays() +
    renderAll(), which rebuilds the day form from the SAVED row and
    discards whatever the operator had typed. The Add photos drawer had
    carried `dayFormDirtyBlocks()` since it was written; Remove, Move
    and the direct "Add to this day" on a date suggestion had not.

    Behaviour is proved by
    `node scripts/ui/run_photo_placement_safety.js`, which drives each
    control with a dirty form and asserts zero requests; these tests
    pin the call sites so a removal is caught by the build as well.
    """

    def test_every_placement_control_checks_the_dirty_form_first(self):
        for name in ("addPhotosToDay", "unlinkDayPhoto",
                     "openPlacementMove", "movePlacement"):
            with self.subTest(fn=name):
                body = _fn(name)
                self.assertIn("dayFormDirtyBlocks()", body,
                              "%s can discard typed day edits" % name)

    def test_the_guard_is_the_first_thing_each_one_does(self):
        """Before the request, not after it.

        A guard below the api() call would block the repaint and leave
        the write already sent -- the worst of both.
        """
        for name, call in (("addPhotosToDay", "api("),
                           ("unlinkDayPhoto", "api("),
                           ("movePlacement", "api("),
                           ("openPlacementMove", "st.placementMove =")):
            with self.subTest(fn=name):
                body = _fn(name)
                self.assertLess(body.index("dayFormDirtyBlocks()"),
                                body.index(call),
                                "%s acts before it checks" % name)

    def test_blocking_returns_a_promise_where_the_caller_expects_one(self):
        """`addPhotosToDay(...).then(...)` is a live call site.

        Returning undefined from the guarded path would throw inside
        the picker's Add handler rather than block it quietly.

        CORRECTED 2026-08-13 after review. This asserted the literal
        `dayFormDirtyBlocks()) return Promise.resolve()` on all three,
        which was true of addPhotosToDay only while its blocked path
        resolved with NOTHING -- and the picker reads `r.added` off
        that. The blocked path now resolves with the same result object
        every other path answers, so the assertion is split: the two
        that need only a promise, and the one that needs the shape.
        """
        for name in ("unlinkDayPhoto", "movePlacement"):
            with self.subTest(fn=name):
                self.assertIn("dayFormDirtyBlocks()) return Promise.resolve()",
                              _fn(name))
        body = _fn("addPhotosToDay")
        self.assertIn("if (dayFormDirtyBlocks()) {", body)
        self.assertIn("return Promise.resolve(result({ unsent: ids, "
                      "blocked: true }));", body,
                      "the blocked path must answer the shape the picker "
                      "reads, and report the selection as outstanding")

    def test_every_exit_answers_the_same_result_shape(self):
        """ADDED 2026-08-13. Proved behaviourally by
        `node scripts/ui/run_photo_placement_safety.js`, which drives
        all six paths; pinned here so a rewrite that drops one is
        caught by the build too."""
        body = _fn("addPhotosToDay")
        self.assertIn("function result(o) {", body)
        self.assertIn("blocked: !!o.blocked", body)
        self.assertIn("reloadError: o.reloadError || null", body)
        # FOUR code exits, covering six outcomes: blocked, empty, the
        # chain's own return (success / partial / reload-failure all
        # share it, because only the MESSAGE differs between them), and
        # the outer catch.
        #
        # Counting exits is honest here; walking `return` statements is
        # not, because the batch reducer and the reload each `return`
        # inside a nested closure and neither is an exit of this
        # function. The behaviour is proved by driving all six outcomes
        # in run_photo_placement_safety.js; this fails the build only if
        # a rewrite starts answering something other than result().
        self.assertEqual(body.count("result({"), 4,
                         "an exit that does not go through result(), or a "
                         "new one nobody drove in the safety runner")
        self.assertNotIn("return Promise.resolve();", body,
                         "an exit answering nothing at all is what the "
                         "picker's `r.added` used to crash on")

    def test_a_failed_reload_does_not_erase_a_known_write(self):
        """ADDED 2026-08-13 after review.

        The reload used to sit inside the same chain as the writes, so
        the outer catch replaced "Added 50 of 120" with the refresh
        error -- telling the operator the add failed while 50
        photographs sat on the day.
        """
        body = _fn("addPhotosToDay")
        self.assertIn("var reloadError = null;", body)
        self.assertIn(".catch(function (e) { reloadError = e; });", body,
                      "the reload must fail on its own, not abort the run")
        self.assertIn("could not be refreshed", body)
        self.assertLess(body.index("var reloadError"),
                        body.index("could not be refreshed"))


class EveryItemIsReachableTest(unittest.TestCase):
    """Phase 3b. The truncating slices were a CORRECTNESS bug, not a
    load-shape one: every control lives on a row, so a photograph with
    no row could not be removed, moved, or seen, and nothing on screen
    said it was there."""

    def test_the_truncating_slices_are_gone(self):
        body = _fn("renderDayInspector") if "function renderDayInspector(" \
            in _js() else _js()
        for dead in ("dayLinks.slice(0, 12)", "dateLinks.slice(0, 8)"):
            self.assertNotIn(dead, body,
                             "%s truncates a list every control lives on"
                             % dead)

    def test_both_inspector_lists_are_windowed(self):
        src = _js()
        self.assertIn("dayLinks.slice(winA.start, winA.end)", src)
        self.assertIn("dateLinks.slice(winB.start, winB.end)", src)

    def test_the_picker_is_windowed(self):
        body = _fn("renderPhotoPicker")
        self.assertIn("pickable.slice(winP.start, winP.end)", body)
        self.assertNotIn("pickable.forEach(", body,
                         "the picker still mounts the whole trip library")

    def test_every_windowed_list_has_a_pager(self):
        """A window without a control is a slice with extra steps."""
        src = _js()
        self.assertEqual(src.count("photoPager("), 4,
                         "three call sites plus the definition; a list "
                         "gained a window without gaining its control")

    def test_the_pager_states_the_true_total(self):
        body = _fn("photoPager")
        self.assertIn('" of " + total', body)
        self.assertIn("Load more (", body)
        self.assertIn("Earlier", body)


class BoundedDomTest(unittest.TestCase):

    def test_the_constants_are_declared_once(self):
        src = _js()
        self.assertEqual(src.count("var PHOTO_PAGE_SIZE = "), 1)
        self.assertEqual(src.count("var PHOTO_WINDOW_MAX = "), 1)
        self.assertEqual(src.count("var PHOTO_WINDOW_MAX_SECTION = "), 1)

    def test_the_inspector_sections_share_the_drawer_budget(self):
        """Two lists are mounted at once in the inspector; one is
        mounted in the drawer. Halving the section bound is what makes
        the mounted total the same on either surface."""
        src = _js()
        page = int(re.search(r"var PHOTO_PAGE_SIZE = (\d+);", src).group(1))
        wide = int(re.search(r"var PHOTO_WINDOW_MAX = (\d+);", src).group(1))
        section = int(re.search(
            r"var PHOTO_WINDOW_MAX_SECTION = (\d+);", src).group(1))
        self.assertEqual(page, 50)
        self.assertLessEqual(section * 2, wide,
                             "the inspector can mount more than the drawer")
        self.assertLessEqual(wide, 200, "the bound drifted above ~200")

    def test_the_sections_use_the_section_bound_and_the_drawer_the_full_one(
            self):
        src = _js()
        self.assertIn('photoWindow(keyA, dayLinks.length, '
                      'PHOTO_WINDOW_MAX_SECTION)', src)
        self.assertIn('photoWindow(keyB, dateLinks.length, '
                      'PHOTO_WINDOW_MAX_SECTION)', src)
        self.assertIn('photoWindow(keyP, pickable.length, '
                      'PHOTO_WINDOW_MAX)', src)

    def test_start_is_derived_rather_than_stored(self):
        """The bug the arithmetic runner found: storing both edges let a
        shrunken list clamp to a one-item window. `start` is now
        max(0, end - wide), so the class cannot recur."""
        body = _fn("photoWindow")
        self.assertIn("start: Math.max(0, end - wide)", body)


class SelectionSurvivesARepaintTest(unittest.TestCase):
    """Load more repaints, and a repaint used to empty the selection —
    invisible while the grid was static, unmissable once it slides."""

    def test_the_checked_set_lives_in_state(self):
        src = _js()
        self.assertIn("photoPickerChecked", src)
        body = _fn("renderPhotoPicker")
        self.assertIn("var checked = st.photoPickerChecked;", body)
        self.assertNotIn("var checked = {};", body,
                         "selection is back in the render closure")

    def test_a_rendered_checkbox_reflects_the_stored_selection(self):
        body = _fn("renderPhotoPicker")
        self.assertIn("cb.checked = !!checked[l.id];", body)

    def test_the_footer_is_painted_from_the_stored_selection_on_render(self):
        """The checkbox is only half of it.

        paintAttach used to be reachable ONLY from a checkbox's change
        handler — fine while the grid never repainted mid-selection,
        because ticking was the only way to change the count. Load more
        repaints, so without a call at the end of the render the button
        reset to "Add selected to …" and disabled itself while the
        selection was still held in st: the footer contradicting the
        state it describes.
        """
        body = _fn("renderPhotoPicker")
        # Called at the end of the render, after the footer exists.
        self.assertIn("\n    paintAttach();\n", body)
        i = body.index("\n    paintAttach();\n")
        self.assertIn("foot.appendChild(attach);", body[:i],
                      "paintAttach runs before the button it paints exists")

    def test_it_is_cleared_when_the_picker_opens_and_closes(self):
        for fn in ("openPhotoPicker", "closePhotoPicker"):
            self.assertIn("st.photoPickerChecked = {};", _fn(fn),
                          "%s leaves a stale selection" % fn)

    def test_windows_and_selection_are_cleared_on_trip_switch(self):
        body = _fn("selectTrip")
        self.assertIn("st.photoWindows = {};", body)
        self.assertIn("st.photoPickerChecked = {};", body)


class ThumbnailsStayEagerTest(unittest.TestCase):
    """§8.1. Nested `overflow:auto` panels are their own scrollport, and
    native lazy loading evaluates against the document's — which is how
    four thumbnail sites shipped permanently blank once. Bounded eager
    batches are the sanctioned answer and the one taken here."""

    def test_every_nested_panel_asks_for_eager_thumbnails(self):
        """Scoped to the nested panels, NOT the whole file.

        The first version of this test banned lazy loading everywhere
        and failed on the trip gallery — which is the one surface that
        legitimately keeps the hint, because it scrolls with the
        DOCUMENT rather than inside an overflow:auto panel, and it is
        also the one that can hold every photograph on a trip. Banning
        it there would have traded a real defect for a real cost.
        """
        for fn in ("renderPhotoPicker", "renderPlacementMove"):
            body = _fn(fn)
            self.assertNotIn(", true)", body.replace("thumbImg(", "\x00"),
                             "%s asks for a lazy thumbnail inside a "
                             "nested scrollport" % fn)
        src = _js()
        self.assertIn("thumbImg(l.photo_id, l.caption, false)", src)

    def test_the_lazy_inventory_did_not_grow(self):
        """Exactly the two sites that were here before Phase 3: the trip
        gallery and the travel-document preview. Both scroll with the
        document rather than inside an overflow:auto panel, which is the
        condition under which native lazy loading works at all.

        Equality, not a ceiling. A third would almost certainly be a new
        nested panel, and that is the failure §8.1 exists to prevent —
        four thumbnail sites once shipped permanently blank for exactly
        this reason.
        """
        src = _js()
        lazy = re.findall(r"thumbImg\([^)]*,\s*true\)", src)
        self.assertEqual(len(lazy), 2,
                         "the lazy-thumbnail inventory moved: %r" % (lazy,))

    def test_lazy_remains_opt_in_at_the_single_decision_point(self):
        body = _fn("thumbImg")
        self.assertIn("lazy", body)


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
