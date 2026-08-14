"""WO-TRIP-PHOTO-PALETTE-01 P2 — the Palette pane.

WHAT THIS SUITE IS REALLY FOR, in the order the review put it:

1. **Two questions, kept apart.** "Not on a day" and "completely
   unplaced" are different facts about different axes. A photograph
   filed to a stop with no day is the first and not the second, and the
   card shows both. The old rule conflated them AND forgot
   `trip_region_id` entirely.

2. **One predicate for counts and cards.** The Photos tab carries two
   copies of its filter switch and they agree only because someone has
   kept them in step. A chip that disagrees with the grid it labels
   reads to an operator as lost data.

3. **Selection is state, not a closure.** `renderAll()` rebuilds every
   node in the module, so a selection held in a render closure is
   emptied by the next repaint -- which is every filter press and every
   Load more.

4. **Partial batches tell the truth.** Only confirmed successes leave
   the selection; the failed batch and everything after it stay ticked.

Source-shape assertions, deliberately: the behaviour that needs a real
DOM is proved by `scripts/ui/run_photo_palette_behaviour.js`, which
executes the shipped functions.

Run per-module:
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_trip_photo_palette_ui
"""
from __future__ import annotations

import re
import unittest

from tests import travel_doc_surfaces as _tds


def _js() -> str:
    return _tds.UNIFIED_JS.stripped()


def _raw() -> str:
    return _tds.UNIFIED_JS.path.read_text(encoding="utf-8")


def _fn(name: str) -> str:
    src = _js()
    start = src.index("function %s(" % name)
    depth = 0
    for j in range(src.index("{", start), len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
    raise AssertionError("unterminated function %s" % name)


class PredicatesAreSeparateQuestionsTest(unittest.TestCase):

    def test_all_five_helpers_exist(self):
        src = _js()
        for name in ("function linkHasNoDayPlacement(",
                     "function linkIsCompletelyUnplaced(",
                     "function linkIsOnDay(",
                     "function linkIsOnMultipleDays(",
                     "function linkMatchesPaletteFilter("):
            self.assertIn(name, src, "missing %s" % name)

    def test_not_on_a_day_asks_only_about_days(self):
        body = _fn("linkHasNoDayPlacement")
        self.assertIn("linkDayIds(l).length === 0", body)
        for axis in ("trip_stop_id", "trip_region_id", "trip_day_id"):
            self.assertNotIn(axis, body,
                             "Not on a day must not consult %s" % axis)

    def test_completely_unplaced_covers_all_three_axes(self):
        body = _fn("linkIsCompletelyUnplaced")
        self.assertIn("!l.trip_region_id", body)
        self.assertIn("!l.trip_stop_id", body)
        self.assertIn("linkHasNoDayPlacement(l)", body)

    def test_multiple_days_is_two_or_more(self):
        body = _fn("linkIsOnMultipleDays")
        self.assertIn("linkDayIds(l).length >= 2", body)

    def test_no_palette_predicate_reads_the_compatibility_scalar(self):
        """`trip_day_id` is null BY RULE for a photograph on several
        days. Any predicate that reads it calls the most deliberately
        placed photographs in the trip unplaced."""
        for name in ("linkHasNoDayPlacement", "linkIsCompletelyUnplaced",
                     "linkIsOnMultipleDays", "linkMatchesPaletteFilter"):
            self.assertNotIn("trip_day_id", _fn(name),
                             "%s reads the derived scalar" % name)

    def test_link_day_ids_is_still_the_single_source(self):
        body = _fn("linkDayIds")
        self.assertIn("trip_day_ids", body,
                      "the authoritative array is preferred")


class OnePredicateForCountsAndCardsTest(unittest.TestCase):

    def test_the_filter_dispatcher_handles_every_declared_filter(self):
        src = _js()
        block = src[src.index("var PALETTE_FILTERS"):]
        # to the array's CLOSING bracket, not the first one -- which is
        # the end of the first entry. The draft cut at `["all", "All"]`
        # and then cheerfully reported that every other filter was
        # undeclared.
        block = block[:block.index("];")]
        keys = re.findall(r'\["(\w+)",', block)
        self.assertEqual(["all", "noday", "day", "multi", "review", "hidden"],
                         keys)
        body = _fn("linkMatchesPaletteFilter")
        for k in keys:
            if k == "all":
                continue
            self.assertIn('"%s"' % k, body,
                          "%s is offered as a chip and not dispatched" % k)

    def test_the_chip_count_and_the_grid_call_the_same_function(self):
        """The whole point. If these ever diverge the operator sees a
        count that does not match the photographs under it."""
        # The two callers are in DIFFERENT functions -- the chip loop is
        # in the pane, the card list is in paletteLinks() -- so this
        # asserts one call each rather than two in one place. The draft
        # expected both inline and failed on the code being better
        # factored than the test assumed.
        pane = _fn("renderPalettePane")
        links = _fn("paletteLinks")
        self.assertEqual(1, pane.count("linkMatchesPaletteFilter("),
                         "the chip count must ask the shared predicate once")
        self.assertEqual(1, links.count("linkMatchesPaletteFilter("),
                         "the card list must ask the shared predicate once")
        self.assertIn("linkMatchesPaletteFilter(l, f[0], visibleDayId)", pane)
        self.assertIn("linkMatchesPaletteFilter(l, p.filter", links)
        self.assertIn("paletteLinks(cal)", pane,
                      "the grid must come from the shared list builder")

    def test_the_palette_never_writes_its_own_inline_filter_switch(self):
        pane = _fn("renderPalettePane")
        for leaked in ("linkIsUnplaced(", "l.hidden ===", "cluster_confidence"):
            self.assertNotIn(leaked, pane,
                             "the pane re-implements a predicate instead of "
                             "asking for one: %s" % leaked)


class SelectionSurvivesRepaintTest(unittest.TestCase):

    def test_selection_lives_in_state_not_in_a_closure(self):
        src = _js()
        self.assertIn("selected: {}", _fn("newPaletteState"))
        self.assertIn("st.tripCal.palette", _fn("paletteState"))

    def test_selection_is_keyed_by_photo_link_id(self):
        body = _fn("paletteToggleSelected")
        self.assertIn("p.selected[linkId]", body)

    def test_toggling_a_checkbox_does_not_repaint(self):
        """A repaint mid-tick rebuilds the input under the operator's
        finger and takes focus with it."""
        card = _fn("renderPaletteCard")
        i = card.index("cb.onchange")
        handler = card[i:i + 600]
        self.assertNotIn("renderAll()", handler,
                         "ticking a box must not repaint the grid")

    def test_the_out_of_filter_count_is_reported(self):
        """Twelve selected, filter changed, two shown -- without this
        line the other ten look lost."""
        # MOVED 2026-08-14. This asserted the call inside
        # renderPalettePane. It now lives in paletteRefreshBar, which is
        # strictly better: the pane runs once per render, the refresh
        # runs on every tick, so the out-of-filter count is now live
        # rather than one selection behind.
        self.assertIn("function paletteSelectedOutsideFilter(", _js())
        bar = _fn("paletteRefreshBar")
        self.assertIn("paletteSelectedOutsideFilter(", bar)
        self.assertIn("not shown by this filter", bar)

    def test_select_all_is_scoped_to_the_MOUNTED_WINDOW(self):
        """ADDED after mutation testing, which found nothing guarding
        this. Widening `mountedIds` from the window to the whole filtered
        list left every test green -- and with a thousand matches and
        fifty mounted, "Select all shown" would then reach nine hundred
        and fifty photographs the operator has never seen."""
        pane = _fn("renderPalettePane")
        self.assertIn("Select all shown", pane)
        self.assertIn("links.slice(win.start, win.end).map(", pane,
                      "Select all must take the MOUNTED window, not the "
                      "whole filtered list")
        i = pane.index("var mountedIds")
        self.assertIn("win.start", pane[i:i + 200])
        self.assertIn("mountedIds.forEach", pane,
                      "the handler must select the mounted ids")

    def test_timeline_move_uses_the_atomic_placement_endpoint(self):
        """ADDED after mutation testing. Reverting this to the day-link
        route left every test green, and that route ADDS a placement
        under the multi-day model -- so a control labelled "Move to Day N"
        left the photograph on both days while reporting a move."""
        body = _fn("moveTripPhotoLink")
        self.assertIn("/photos/placement-move", body)
        self.assertIn("from_day_id", body)
        self.assertIn("to_day_id", body)
        i = body.index("/photos/placement-move")
        guard = body[max(0, i - 400):i]
        self.assertIn("toDayId && fromDayId && toDayId !== fromDayId", guard,
                      "a move must name BOTH ends; one end is not a move")
        self.assertIn('"/photos/" + (toDayId ? "link" : "unlink")', body,
                      "taking a photograph off a day is still the unlink "
                      "route and must survive")


class BatchTruthfulnessTest(unittest.TestCase):

    def test_one_batch_runner_is_shared(self):
        src = _js()
        self.assertIn("function paletteBatchRun(", src)
        for caller in ("removePhotosFromDay", "setPhotoLinksHidden"):
            self.assertIn("paletteBatchRun(", _fn(caller),
                          "%s wrote its own runner" % caller)

    def test_the_runner_is_sequential_not_parallel(self):
        body = _fn("paletteBatchRun")
        self.assertIn("reduce(", body)
        self.assertNotIn("Promise.all(", body,
                         "concurrent batches interleave ord assignment")

    def test_the_runner_stops_at_the_first_failure(self):
        """The condition gained `|| state.cancelled` when batches learned
        to stop on a stale context, so this asserts the failure half by
        name rather than the whole expression."""
        body = _fn("paletteBatchRun")
        self.assertIn("state.failure || state.cancelled", body)
        self.assertIn("state.unsent = state.unsent.concat(batch)", body)

    def test_the_runner_checks_currency_BEFORE_sending(self):
        """Capturing the trip id stops a batch going to the wrong trip;
        it does nothing to stop it going at all. An operator who has left
        trip A must not have trip A changing underneath them."""
        body = _fn("paletteBatchRun")
        i = body.index('typeof isCurrent === "function"')
        j = body.index("return sendBatch(batch)")
        self.assertLess(i, j,
                        "currency must be checked before the request, not "
                        "after the response")
        self.assertIn("state.cancelled = true", body)

    def test_cancelled_is_not_reported_as_a_failure(self):
        """"You moved on" and "it broke" send the operator to different
        places; conflating them means retrying something never wrong."""
        body = _fn("paletteAfterBatch")
        self.assertIn("r.cancelled", body)
        self.assertIn("not sent because", body)

    def test_remove_chunks_at_the_same_ceiling_as_add(self):
        self.assertIn("PLACEMENT_BATCH_MAX", _fn("paletteBatchRun"))

    def test_every_batch_path_answers_the_same_five_keys(self):
        body = _fn("paletteResult")
        for key in ("done", "unsent", "error", "reloadError", "blocked"):
            self.assertIn(key, body)

    def test_a_reload_failure_is_not_a_write_failure(self):
        for name in ("removePhotosFromDay", "setPhotoLinksHidden"):
            body = _fn(name)
            self.assertIn("reloadError", body,
                          "%s conflates a failed refresh with a failed write"
                          % name)

    def test_only_confirmed_successes_leave_the_selection(self):
        body = _fn("paletteAfterBatch")
        self.assertIn("delete p.selected[id]", body)
        self.assertIn("landed", body)

    def test_remove_is_dirty_guarded_and_hide_is_not(self):
        """Remove reloads the day form and can discard typed day text.
        Hiding reloads the photo links only, so guarding it would refuse
        a safe action and teach the operator the guard is noise."""
        self.assertIn("dayFormDirtyBlocks()", _fn("removePhotosFromDay"))
        self.assertNotIn("dayFormDirtyBlocks()", _fn("setPhotoLinksHidden"))

    def test_hide_uses_the_atomic_endpoint(self):
        body = _fn("setPhotoLinksHidden")
        self.assertIn("/photo-links/visibility", body)
        self.assertIn("hidden: !!hidden", body)

    def test_there_is_no_bulk_move(self):
        """A photograph on three days has three occurrences behind one
        link id; a bulk move from a bare id is not expressible."""
        pane = _fn("renderPalettePane")
        self.assertNotIn("movePlacement(", pane)
        card = _fn("renderPaletteCard")
        self.assertIn("openPlacementMove(d, l)", card,
                      "Move stays contextual and names its source day")


class OneLinkLookupTest(unittest.TestCase):

    def test_palette_eligibility_never_reads_the_photos_tab_array(self):
        """`st.hiddenPhotoLinks` is empty unless the PHOTOS TAB toggle is
        on, so a hidden photograph could be on screen, on the day, and
        unremovable -- the same split authority the Palette's own pool
        was introduced to remove."""
        for name in ("paletteLinkIndex", "paletteRemovableIds"):
            self.assertNotIn("st.hiddenPhotoLinks", _fn(name),
                             "%s reads the Photos tab's array" % name)
        idx = _fn("paletteLinkIndex")
        self.assertIn("st.photoLinks", idx)
        self.assertIn("p.hidden", idx)

    def test_there_is_one_lookup_and_remove_uses_it(self):
        self.assertIn("paletteLinkIndex()", _fn("paletteRemovableIds"))
        self.assertIn("paletteLinkIndex()", _fn("paletteLinkById"))


class CaptionRouteTest(unittest.TestCase):

    def test_the_palette_does_not_route_through_the_photos_tab_filter(self):
        """`openLightbox` resolves selection through `filteredLinks()`,
        which is the Photos tab's list -- a Palette card excluded by that
        filter, or a hidden one, may not be in it at all."""
        card = _fn("renderPaletteCard")
        self.assertNotIn("openLightbox(", card)
        self.assertIn("openCaptionEditorForLink(l.id)", card)

    def test_the_opener_takes_a_link_id_not_a_timeline_item(self):
        """The Palette has a link and no row: its card may be for a
        photograph on no day at all, or hidden."""
        body = _fn("openCaptionEditorForLink")
        self.assertIn("paletteLinkById(linkId)", body)
        self.assertIn('kind: "photo"', body)

    def test_both_callers_end_at_one_shared_save(self):
        """Neither surface writes a caption itself."""
        body = _fn("timelineEditBody")
        self.assertIn('return { body: { caption: t("caption") } };', body)
        self.assertNotIn("caption_approved_for_lori", body,
                         "the shared save must never send approval")
        opener = _fn("openCaptionEditorForLink")
        self.assertNotIn("api(", opener,
                         "the opener must not carry its own write")


class GuardedReloadTest(unittest.TestCase):

    def test_the_guard_is_checked_at_the_assignment(self):
        """Guarding the reporter after an unguarded reload has already
        overwritten global state guards the wrong end of the chain."""
        for name, assign in (("reloadPhotoLinks", "st.photoLinks ="),
                             ("reloadDays", "st.days =")):
            body = _fn(name)
            i = body.index("reloadGuardIsCurrent(guard, tripId)")
            j = body.index(assign)
            self.assertLess(i, j,
                            "%s assigns before it checks the guard" % name)

    def test_the_guard_covers_trip_generation_and_modal(self):
        body = _fn("reloadGuardIsCurrent")
        self.assertIn("st.trip.id !== tripId", body)
        self.assertIn("guard.gen !== paletteGeneration", body)
        self.assertIn("guard.needsModal && !st.tripCal", body)
        self.assertIn("destroyed", body)

    def test_the_batch_reloads_carry_the_guard(self):
        for name in ("removePhotosFromDay", "setPhotoLinksHidden"):
            body = _fn(name)
            self.assertIn("reloadPhotoLinks(guard)", body,
                          "%s reloads unguarded" % name)


class ObsoleteCommentTest(unittest.TestCase):

    def test_the_retired_single_day_claim_is_gone(self):
        """It claimed one link has one day and that a photograph on two
        days is a claim it was taken twice -- retired by the placement
        model, and the corrected comment below it said the opposite."""
        src = _raw()
        for gone in ("A photograph moves by updating the ONE",
                     "a photograph on two days is a claim that it was"):
            self.assertNotIn(gone, src)
        self.assertIn("/photos/placement-move", _fn("moveTripPhotoLink"))


class StaleRequestTest(unittest.TestCase):

    def test_a_generation_identity_exists(self):
        src = _js()
        self.assertIn("var paletteGeneration", src)
        self.assertIn("function paletteBumpGeneration(", src)
        self.assertIn("function paletteGenerationIsCurrent(", src)

    def test_it_is_bumped_on_every_axis_that_changes_the_question(self):
        src = _js()
        self.assertGreaterEqual(
            src.count("paletteBumpGeneration()"), 4,
            "trip/day, mode, filter and close must each invalidate")
        self.assertIn("paletteBumpGeneration()", _fn("closeTripCalendar"))
        self.assertIn("paletteBumpGeneration()", _fn("renderCalModeStrip"))

    def test_currency_requires_a_live_mount_and_a_live_modal(self):
        body = _fn("paletteGenerationIsCurrent")
        self.assertIn("!destroyed", body)
        self.assertIn("st.tripCal", body)


class ModeNotModalTest(unittest.TestCase):

    def test_the_palette_is_a_mode_of_the_existing_modal(self):
        self.assertIn('mode: "timeline"', _js())
        strip = _fn("renderCalModeStrip")
        self.assertIn("Photo Palette", strip)
        self.assertIn("Timeline", strip)

    def test_there_is_no_second_scrim(self):
        pane = _fn("renderPalettePane")
        self.assertNotIn("tdl-drawer-scrim", pane)
        self.assertNotIn("tdl-cal-scrim", pane)

    def test_the_mode_switch_honours_the_dirty_guard(self):
        strip = _fn("renderCalModeStrip")
        self.assertIn("timelineEditDirtyBlocks()", strip)


class AccessibilityTest(unittest.TestCase):

    def test_selection_uses_a_native_checkbox(self):
        card = _fn("renderPaletteCard")
        self.assertIn('cb.type = "checkbox"', card)
        self.assertIn("aria-label", card)

    def test_no_aria_grid_without_keyboard_grid_behaviour(self):
        """The W3C grid pattern needs roving focus and arrow-key
        navigation, and this grid recycles its window so most rows are
        not in the DOM. A checkbox is already reachable and announced."""
        src = _js()
        self.assertNotIn('role", "grid"', src)
        self.assertNotIn('role="grid"', src)

    def test_there_is_one_polite_status_region(self):
        pane = _fn("renderPalettePane")
        self.assertIn('"aria-live", "polite"', pane)
        self.assertNotIn('"assertive"', pane,
                         "assertive talks over the operator for a count")

    def test_filter_chips_report_pressed_state(self):
        pane = _fn("renderPalettePane")
        self.assertIn('"aria-pressed"', pane)

    def test_focus_is_visible_in_the_grid(self):
        css = _tds.UNIFIED_CSS.stripped()
        self.assertIn(".tdl-palette-card :focus-visible", css)
        self.assertIn("outline", css)


class SafetyTest(unittest.TestCase):

    def test_the_palette_never_requests_an_original(self):
        pane = _fn("renderPalettePane")
        card = _fn("renderPaletteCard")
        for body in (pane, card):
            self.assertNotIn("fullImageUrl(", body,
                             "the grid must use thumbnails only")
        self.assertIn("thumbImg(", card)

    def test_the_card_exposes_no_path_provider_id_or_coordinate(self):
        card = _fn("renderPaletteCard")
        for leak in ("image_path", "external_id", "latitude", "longitude",
                     "file_hash", "thumbnail_path"):
            self.assertNotIn(leak, card)

    def test_caption_and_approval_are_separate_lines(self):
        card = _fn("renderPaletteCard")
        self.assertIn("No caption", card)
        self.assertIn("Not shared with Lori", card)

    def test_no_delete_control_exists(self):
        pane = _fn("renderPalettePane")
        card = _fn("renderPaletteCard")
        for body in (pane, card):
            self.assertNotIn('"DELETE"', body)
            self.assertNotIn("Delete", body)

    def test_a_stop_assigned_photograph_shows_both_facts(self):
        card = _fn("renderPaletteCard")
        self.assertIn("Not on a day", card)
        self.assertIn("Stop assigned", card)
        self.assertIn("Region assigned", card)
        self.assertIn("Not placed at all", card)


if __name__ == "__main__":
    unittest.main()
