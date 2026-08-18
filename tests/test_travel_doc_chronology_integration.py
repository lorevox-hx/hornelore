"""WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 Phase 2, Part A.

The Travel Document connects to the canonical chronology. It does not
replace it, and it is not replaced by it:

    detailed trip/day editing   trip_days + /api/trips/{id}/days
    person-wide chronology      /api/chronology-accordion
    narrator navigation         Life Map + Chronology Accordion
    travel memoir output        the visible timeline -> DOCX

These tests pin the SHAPE of that connection -- one fetch through the
module's api() choke point, a generation guard, a person_id check on the
response, a refresh at every day-moving write, a shell notification that
fires only after a successful refresh, and a pre-output gate.

The BEHAVIOUR of the reconciler -- matching by stable day id, treating an
undated day as a note rather than a disagreement, keeping Today off a
dateless trip -- is proved by executing the real functions in
`scripts/ui/run_chronology_connection_behaviour.js`. A source scan cannot
tell a working comparison from a broken one.

pytest is not installed in this repo. Run with:

    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_travel_doc_chronology_integration
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tests.source_scan_helpers import strip_js_comments  # noqa: E402

_TDL = _REPO_ROOT / "ui" / "js" / "travel-doc-lab.js"
_APP = _REPO_ROOT / "ui" / "js" / "app.js"
_CSS = _REPO_ROOT / "ui" / "css" / "travel-doc-lab.css"


def _src() -> str:
    return strip_js_comments(_TDL.read_text(encoding="utf-8"))


def _fn(src: str, name: str) -> str:
    """The body of one function, brace-matched."""
    start = src.find("function " + name + "(")
    if start < 0:
        raise AssertionError(name + " not found")
    depth = 0
    open_i = src.index("{", start)
    for i in range(open_i, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
    raise AssertionError("unterminated " + name)


class OneChronologyEngineStill(unittest.TestCase):
    """Phase 1 deleted the second engine. Phase 2 must not add a third."""

    def setUp(self):
        self.src = _src()

    def test_the_workspace_reads_the_accordion_and_nothing_else(self):
        self.assertIn("/api/chronology-accordion?person_id=", self.src)
        self.assertNotIn("/api/narrator/chronology", self.src)

    def test_it_computes_no_chronology_of_its_own(self):
        # Deriving eras here would be a second engine wearing a different
        # name. The projection decides; this file compares two lists.
        for forbidden in ("build_scaffold_periods", "derive_life_spine",
                          "era_id_from_age", "LV_ERAS"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.src)

    def test_travels_is_a_shelf_and_not_a_seventh_era(self):
        panel = _fn(self.src, "renderChronologyPanel")
        self.assertIn("Travels", panel)
        self.assertIn("not a life era", panel)
        # The historical-period list must exclude the current-life bucket.
        summary = _fn(self.src, "chronologySummary")
        self.assertIn("if (p.is_current_life) return;", summary)


class TheFetchGoesThroughTheChokePoint(unittest.TestCase):
    def setUp(self):
        self.src = _src()

    def test_there_is_still_exactly_one_fetch_in_the_file(self):
        # The mount's whole staleness argument rests on this count.
        self.assertEqual(len(re.findall(r"\bfetch\(", self.src)), 1)

    def test_the_chronology_load_uses_api(self):
        body = _fn(self.src, "loadChronology")
        self.assertIn('api("/api/chronology-accordion', body)
        self.assertNotIn("fetch(", body)
        self.assertNotIn("XMLHttpRequest", body)

    def test_a_stale_response_cannot_cross_a_generation(self):
        body = _fn(self.src, "loadChronology")
        self.assertIn("chronologyBumpGeneration()", body)
        # BOTH arms. This assertion originally counted one occurrence and
        # SURVIVED a mutation that deleted the guard from the success
        # arm, because the identical line in the catch arm still matched.
        # A resolve path and a reject path are two ways for a superseded
        # answer to land, and each needs its own guard.
        self.assertEqual(
            body.count("if (gen !== chronologyGeneration) return null;"), 2,
            "the success arm and the failure arm must each be guarded")
        # ...and in the success arm it must come FIRST, before any state
        # is written from a response that may be about a previous trip.
        then_arm = body[body.find(".then(function (out) {"):]
        i_guard = then_arm.find("if (gen !== chronologyGeneration)")
        i_write = then_arm.find("st.chronology")
        self.assertGreater(i_guard, -1)
        self.assertLess(i_guard, i_write)

    def test_a_response_about_another_narrator_is_discarded(self):
        body = _fn(self.src, "loadChronology")
        self.assertIn("pid !== st.personId", body)
        self.assertIn('String(out.person_id || "") !== String(pid)', body)

    def test_the_chronology_generation_is_its_own_counter(self):
        # Sharing paletteGeneration would let a photo action invalidate a
        # chronology read, and vice versa.
        self.assertIn("var chronologyGeneration = 0;", self.src)
        body = _fn(self.src, "loadChronology")
        self.assertNotIn("paletteGeneration", body)


class UnavailableIsNotEmpty(unittest.TestCase):
    def setUp(self):
        self.src = _src()

    def test_an_outage_keeps_the_previous_payload_and_flags_it_stale(self):
        body = _fn(self.src, "loadChronology")
        self.assertIn("st.chronologyStale = !!st.chronology;", body)

    def test_the_panel_renders_an_outage_as_an_outage(self):
        panel = _fn(self.src, "renderChronologyPanel")
        self.assertIn('sum.status === "unavailable"', panel)
        self.assertIn("could not be read", panel)

    def test_the_panel_shows_per_lane_provenance_and_status(self):
        panel = _fn(self.src, "renderChronologyPanel")
        self.assertIn("sum.sources", panel)
        for lane in ("timeline_events", "story_evidence", "trip_days"):
            with self.subTest(lane=lane):
                self.assertIn(lane, panel)
        self.assertIn("authority", panel)


class EveryDayMovingWriteRefreshes(unittest.TestCase):
    """A write that changes a day, its date, its label or its place moves
    the projection, so the projection is re-read."""

    def setUp(self):
        self.src = _src()

    def test_the_named_mutations_all_refresh(self):
        for fn in ("generateDays", "addMissingDays", "acknowledgeOutsideDays",
                   "saveDayEdits", "maybeAutoAddMissingDays",
                   "dropEmptyOutOfRangeDays", "afterTripDeleted"):
            with self.subTest(fn=fn):
                self.assertIn("refreshCanonicalChronology(", _fn(self.src, fn))

    def test_trip_create_and_trip_edit_refresh(self):
        # Both live inside the trip editor drawer's save handler rather
        # than in named functions, so they are checked by their
        # notifyTripUpdated neighbours.
        self.assertIn('notifyTripUpdated(out.trip_id, "trip_created");\n'
                      '            refreshCanonicalChronology("trip_created");',
                      self.src)
        self.assertIn('refreshCanonicalChronology("trip_saved");', self.src)

    def test_photo_only_writes_do_not_refresh(self):
        # Explicitly allowed by the work order: a photo placement changes
        # no chronology-bearing field, and refreshing on every thumbnail
        # action would be a fetch per click.
        for fn in ("unlinkDayPhoto", "addPhotosToDay", "removePhotosFromDay",
                   "setPhotoLinksHidden", "movePlacement"):
            with self.subTest(fn=fn):
                self.assertNotIn("refreshCanonicalChronology(", _fn(self.src, fn))


class TheShellIsToldOnlyWhenItIsTrue(unittest.TestCase):
    def setUp(self):
        self.src = _src()
        self.app = strip_js_comments(_APP.read_text(encoding="utf-8"))

    def test_the_event_fires_only_after_a_successful_refresh(self):
        body = _fn(self.src, "refreshCanonicalChronology")
        # The failure branch returns before the notify.
        i_fail = body.find("if (!out)")
        i_notify = body.find("notifyChronologyRefreshed(")
        self.assertGreater(i_fail, 0)
        self.assertGreater(i_notify, i_fail,
                           "the notification must sit after the failure return")
        self.assertIn("return false;", body[i_fail:i_notify])

    def test_a_failed_refresh_preserves_the_save_and_says_so(self):
        body = _fn(self.src, "refreshCanonicalChronology")
        self.assertIn("Your change was saved", body)
        self.assertIn("chronologySyncWarning", body)

    def test_the_event_carries_the_narrator(self):
        body = _fn(self.src, "notifyChronologyRefreshed")
        self.assertIn('"lorevox:chronology-refreshed"', body)
        self.assertIn("person_id: st.personId", body)

    def test_the_shell_accepts_it_only_for_its_active_narrator(self):
        body = _fn(self.app, "lvRefreshNarratorChronology")
        # The ENTRY guard, spelled out. This originally asserted only that
        # the comparison appeared somewhere in the function and SURVIVED a
        # mutation that removed it from the entry check — because the
        # second, post-await comparison inside the loop still matched.
        self.assertIn("if (!target || target !== state.person_id) {", body)
        # And the post-await one, which catches a switch that happened
        # while the fetch was in flight. Two different races, two checks.
        self.assertIn("if (target !== state.person_id) return false;", body)

    def test_the_shell_deduplicates_concurrent_refreshes(self):
        body = _fn(self.app, "lvRefreshNarratorChronology")
        self.assertIn("_chronoRefreshBusy", body)
        self.assertIn("_chronoRefreshQueued", body)

    def test_the_shell_updates_both_life_map_renderers(self):
        body = _fn(self.app, "lvRefreshNarratorChronology")
        self.assertIn("window.LorevoxLifeMap", body)
        self.assertIn("window.crInitAccordion", body)

    def test_the_shell_handler_sends_no_prompt_and_writes_no_projection(self):
        body = _fn(self.app, "lvRefreshNarratorChronology")
        for forbidden in ("sendSystemPrompt", "sendUserMessage", "LorevoxEraDispatch",
                          "PROJECTION", "PUT", "PATCH"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, body)

    def test_the_listener_is_registered(self):
        self.assertIn('window.addEventListener("lorevox:chronology-refreshed"',
                      self.app)


class ThePreOutputGate(unittest.TestCase):
    """visible editable timeline -> DOCX, and nothing else."""

    def setUp(self):
        self.src = _src()

    def test_a_dirty_day_form_blocks_output(self):
        body = _fn(self.src, "prepareForDocumentOutput")
        self.assertIn("dayFormDirtyBlocks()", body)
        # ...and it is checked BEFORE anything is reloaded, so a refusal
        # costs no request.
        self.assertLess(body.find("dayFormDirtyBlocks()"), body.find("reloadDays()"))

    def test_it_reloads_the_detailed_state_then_the_chronology(self):
        body = _fn(self.src, "prepareForDocumentOutput")
        self.assertLess(body.find("reloadDays()"),
                        body.find("refreshCanonicalChronology("))

    def test_it_invalidates_a_stale_lazy_preview(self):
        body = _fn(self.src, "prepareForDocumentOutput")
        self.assertIn("memoirPreviewToken += 1;", body)
        self.assertIn("st.memoirPreview = null;", body)

    def test_both_the_export_and_the_preview_go_through_it(self):
        self.assertIn('prepareForDocumentOutput("document_export")', self.src)
        self.assertIn('prepareForDocumentOutput("document_preview")', self.src)

    def test_the_export_cannot_bypass_the_gate(self):
        outer = _fn(self.src, "_exportTravelDocument")
        self.assertIn("prepareForDocumentOutput(", outer)
        self.assertNotIn("export-docx", outer,
                         "the outer function gates; the inner one downloads")
        self.assertIn("export-docx", _fn(self.src, "_exportTravelDocumentNow"))
        # ...and the gate must actually LEAD somewhere. This originally
        # checked only that the download was absent from the outer
        # function, and SURVIVED a mutation that deleted the call to the
        # inner one — a "gate" that refuses everything passes a test
        # written only in the negative.
        self.assertIn("if (!ok) return;", outer)
        self.assertIn("_exportTravelDocumentNow();", outer)
        self.assertLess(outer.find("if (!ok) return;"),
                        outer.find("_exportTravelDocumentNow();"))

    def test_exactly_once_day_rendering_is_still_the_projections_call(self):
        # The document renders the days the server projection gives it.
        # A client-side filter here would be a second definition of "a day
        # worth printing", living in a second language.
        self.assertIn("var tlDays = tl.days || [];", self.src)


class TripStateResetsCoverTheNewFields(unittest.TestCase):
    def setUp(self):
        self.src = _src()

    def test_both_trip_transitions_clear_the_reconciliation(self):
        for fn in ("selectTrip", "afterTripDeleted"):
            with self.subTest(fn=fn):
                body = _fn(self.src, fn)
                self.assertIn("st.chronologyReconcile = null;", body)
                self.assertIn('st.chronologySyncWarning = "";', body)

    def test_the_narrator_wide_payload_survives_a_trip_switch(self):
        # It describes every trip, so dropping it on a switch would mean
        # re-fetching the same answer for no reason.
        body = _fn(self.src, "selectTrip")
        self.assertNotIn("st.chronology = null;", body)


class CssPrefixDoesNotCollide(unittest.TestCase):
    def test_the_new_block_uses_its_own_prefix(self):
        css = _CSS.read_text(encoding="utf-8")
        self.assertIn(".tdl-chron {", css)

    def test_it_does_not_restyle_an_existing_block(self):
        css = _CSS.read_text(encoding="utf-8")
        new = [m for m in re.findall(r"^\.(tdl-[a-z0-9-]+)", css, re.M)
               if m.startswith("tdl-chron")]
        self.assertTrue(new)
        for cls in new:
            with self.subTest(cls=cls):
                # `tdl-cal-`, `tdl-tl-` and `tdl-doc-` are the calendar,
                # the trip timeline and the Travel Document.
                self.assertFalse(cls.startswith(("tdl-cal-", "tdl-tl-",
                                                 "tdl-doc-")))

    def test_no_new_colour_literals(self):
        # Structural only: every colour reuses an existing --tdl-*
        # variable, so the panel inherits the workspace theme instead of
        # introducing a second one.
        css = _CSS.read_text(encoding="utf-8")
        marker = "/* ── Chronology connection panel"
        i = css.find(marker)
        self.assertGreater(i, 0, "the Phase 2 CSS block is missing")
        block = _strip_css_comments(css[i:])
        self.assertIn(".tdl-chron", block, "comment stripper removed everything")
        for hexcolour in re.findall(r"#[0-9a-fA-F]{3,8}\b", block):
            self.fail("new colour literal " + hexcolour +
                      " — use an existing --tdl-* variable")


def _strip_css_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


if __name__ == "__main__":
    unittest.main()
