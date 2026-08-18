"""WO-TRAVEL-DOC-CLOSEOUT-01 — the finished travel document.

WHAT WAS MISSING
----------------
The backend has had `GET /api/trips/{trip_id}/export-docx` and a
deterministic Part I/II/III renderer for weeks. The unified Travel Doc
workspace called neither. An operator could gather every photograph,
note and source and had no way to produce the document they were for.

This suite covers the two halves of closing that:

  1. the workspace has an export control, wired to the EXISTING route
     and building no document of its own;
  2. approval decides what is in it -- approved trip notes, approved
     sources and memoir-approved photos reach the preview and the DOCX,
     and unapproved ones do not.

WHAT IS DELIBERATELY NOT HERE
-----------------------------
Narrator-wide `story_candidates`. They are narrator-scoped, not
trip-scoped, and the only way to attach them to a trip today would be
loose text matching -- which would put one trip's stories into another
trip's document and be very hard to notice. That integration needs an
explicit source-turn/trip binding and is tracked separately; it must not
block producing the document through the trip-note path, which is
already correct.

Run:
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_travel_document_export
"""
from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SERVER = _REPO / "server" / "code"
sys.path.insert(0, str(_SERVER))

_JS = (_REPO / "ui" / "js" / "travel-doc-lab.js").read_text(encoding="utf-8")
_CSS = (_REPO / "ui" / "css" / "travel-doc-lab.css").read_text(encoding="utf-8")
_TRIPS = (_SERVER / "api" / "routers" / "trips.py").read_text(encoding="utf-8")
_REPO_SVC = (_SERVER / "api" / "services" / "trip_repository.py").read_text(
    encoding="utf-8")


def _strip_js_comments(src: str) -> str:
    """String-aware comment stripper.

    The naive regex version broke on `files.accept = "image/*"` in this
    very module on 2026-07-25 -- the `/*` inside a string literal opened
    a phantom block comment that swallowed hundreds of lines. The repo
    already learned this once; reuse the shared helper.
    """
    from tests.source_scan_helpers import strip_js_comments
    return strip_js_comments(src)


sys.path.insert(0, str(_REPO / "tests"))


# ══════════════════════════════════════════════════════════════════════
# RETIRED 2026-08-06 — the approval gate and the photo appendix
# ══════════════════════════════════════════════════════════════════════
#
# Ten classes were removed from this file, not loosened and not left
# failing. Every one of them guarded a real property of a design that
# no longer exists:
#
#   ApprovalDecidesWhatIsInTheDocumentTest
#   ApprovedIsNotInTheDocumentTest
#   HiddenRowsAreNotInTheDocumentTest
#   ThePhotoCountsAgreeWithTheDocumentTest
#   ThePhotoAppendixIsOneProjectionTest
#   TheExportReadsThePhotoTableOnceTest
#   ApprovedAvailableAndEmbeddedAreDistinctTest
#   AnUnavailableOnlyGroupIsNotAnEmptyHeadingTest
#   UnknownIsNeverRenderedAsZeroTest
#   EveryExportedWordIsReviewableTest
#   PerStopApprovedCountsAreShownTest
#
# The product rule changed: the visible trip timeline is the editable
# source of truth and this document is a Word snapshot of it, so
# `include_in_memoir` decides nothing about the normal export and the
# Part III appendix is gone.
#
# The claims that SURVIVE the change moved rather than vanished:
#
#   * hidden material staying out of the document ->
#       test_travel_document_day_lane.OnlyTheFourExclusionsTest
#   * one shared projection for preview and document ->
#       test_travel_document_day_lane.OneProjectionTest
#   * every exported word being visible to the operator first --
#     which under the old rule meant "previewed before approval" and
#     now means "the preview and the document render the SAME
#     projection" ->
#       test_travel_document_day_lane.OneProjectionTest
#   * captions, and machine text never posing as Chris's own words ->
#       test_travel_document_day_lane.MachineCaptionTest
#
# What has NO successor, stated plainly rather than left to be found:
# the appendix's arithmetic, `approved` vs `available` vs `embedded` as
# three separate numbers. Nothing left counts them -- approval no
# longer decides membership and each photograph is embedded where it is
# mentioned, so "approved but not embedded" is not a state this
# document can be in.


class TheWorkspaceCanExportTest(unittest.TestCase):
    """Half one: the control exists and is wired to the real route."""

    def setUp(self):
        self.src = _strip_js_comments(_JS)

    def test_there_is_an_export_control(self):
        self.assertIn("Export Travel Document", self.src)

    def test_it_calls_the_existing_route(self):
        self.assertIn('"/export-docx"', self.src)

    def test_it_builds_no_second_document(self):
        """The one rule Chris set on this work: use the existing
        exporter. A client-side assembler would drift from the DOCX the
        moment either changed, and the operator would have two documents
        that disagree with no way to tell which is right.

        The tokens are DOCX-BUILDER names, not the word "docx". My first
        cut forbade the bare substring and failed on `travel-document.docx`
        -- the default download filename -- and forbade `Document(`, which
        matched unrelated code elsewhere in a 9,000-line module. A guard
        that fires on the route's own name is not measuring what it
        claims to.
        """
        for forbidden in ("new Document(", "docx.Document", "new Paragraph(",
                          "JSZip", "PizZip", "docxtemplater", "officegen"):
            with self.subTest(token=forbidden):
                self.assertNotIn(forbidden, self.src,
                                 f"{forbidden!r} suggests a second exporter")

    def test_docx_appears_only_as_the_route_and_the_filename(self):
        """The positive half. Without it the test above would pass on a
        build that had stopped exporting altogether."""
        contexts = [self.src[max(0, m.start() - 30):m.start() + 10]
                    for m in re.finditer(r"docx", self.src)]
        self.assertTrue(contexts, "nothing references docx at all any more")
        for c in contexts:
            with self.subTest(context=c):
                self.assertTrue("export-docx" in c or ".docx" in c,
                                f"unexpected docx reference: {c!r}")

    def test_the_download_goes_through_the_single_fetch_choke_point(self):
        """This module's async safety rests on one `fetch` with one set
        of destroyed guards. The first cut of this feature added a second
        fetch for the binary body and `test_the_only_fetch_is_guarded_on_
        every_arm` caught it immediately -- so the raw branch lives
        inside api() instead."""
        self.assertEqual(1, len(re.findall(r"\bfetch\(", self.src)),
                         "a second fetch() appeared")
        self.assertIn("if (opts.raw) return r;", self.src)
        self.assertIn("{ raw: true }", self.src)

    def test_a_failed_export_is_a_message_not_a_saved_file(self):
        """A plain <a download> would save a 503 error page to disk AS
        the document, and the operator would open a Word file containing
        an error. The response is fetched first so a failure surfaces on
        the panel.

        NARROWED 2026-08-17 by WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01
        Phase 2 Part A. This read `_exportTravelDocument` and asserted
        `d.error` in it. That function is now the pre-output GATE --
        dirty-form refusal, day reload, chronology refresh, stale-preview
        invalidation -- and the download it guards moved to
        `_exportTravelDocumentNow`. The assertion is unchanged in
        substance and re-pointed at the function that now downloads; the
        gate itself is covered by
        tests/test_travel_doc_chronology_integration.py."""
        i = self.src.index("function _exportTravelDocumentNow(")
        body = self.src[i:self.src.index("\n  function ", i + 10)]
        self.assertIn("d.error", body)
        # The anchor is built only after a successful response.
        self.assertLess(body.index('"/export-docx"'),
                        body.index('createElement("a")'))

    def test_the_download_is_reachable_only_through_the_gate(self):
        """Phase 2 Part A: the split must not become a bypass."""
        outer = self.src[self.src.index("function _exportTravelDocument("):]
        outer = outer[: outer.index("\n  function ", 10)]
        self.assertIn("prepareForDocumentOutput(", outer)
        self.assertIn("_exportTravelDocumentNow();", outer)
        # And nothing else calls the downloader.
        self.assertEqual(1, self.src.count("_exportTravelDocumentNow();"))

    def test_no_native_dialog_is_used(self):
        """Standing doctrine for every Travel Doc surface.

        Anchored on a FUNCTION, not on the section comment. `self.src` is
        comment-stripped -- it has to be, because the prose above this
        block explains the very calls it forbids -- so a comment marker
        can never be found in it. My first cut looked for the banner and
        raised ValueError.
        """
        i = self.src.index("function docExportRevokeNow(")
        block = self.src[i:self.src.index("function renderDraft()", i)]
        for native in ("window.confirm", "window.prompt", "window.alert",
                       "confirm(", "prompt(", "alert("):
            with self.subTest(call=native):
                self.assertNotIn(native, block)

    def test_the_object_url_is_revoked_and_the_timer_is_clearable(self):
        """A blob URL held open pins a multi-megabyte buffer. The handle
        is stored so destroy() can clear the pending revoke and free it
        at once."""
        self.assertIn("docExportRevokeTimer = setTimeout(", self.src)
        self.assertIn("clearTimeout(docExportRevokeTimer)", self.src)
        self.assertIn("revokeObjectURL", self.src)

    def test_a_second_click_cannot_start_a_second_download(self):
        i = self.src.index("function _exportTravelDocument(")
        body = self.src[i:i + 500]
        self.assertIn("if (d.busy) return;", body)

    def test_the_new_css_adds_no_colour_literal(self):
        """Structural only; every colour reuses an existing --tdl-*
        variable so this block cannot drift from the palette."""
        # BOUNDED AT BOTH ENDS — corrected 2026-08-14.
        #
        # This read `block = _CSS[i:]`, i.e. from the Travel Document
        # marker to END OF FILE. That was correct only while this block
        # was last in the stylesheet. WO-TRIP-PHOTO-PALETTE-01 P2 later
        # appended the Photo Palette section, so the scan silently grew
        # to cover somebody else's CSS and began failing on #fff and
        # #efe8dc -- literals that belong to the Palette, not here.
        #
        # An unbounded slice is the same defect this repository has now
        # hit three times (the fixed-width window in
        # test_travel_documenter_panel, the naive comment stripper, this).
        # The END MARKER IS ASSERTED rather than defaulted to end-of-file:
        # if the Palette block is renamed or removed, this fails loudly
        # instead of quietly re-widening to swallow whatever comes next.
        start = _CSS.index("Travel Document tab (WO-TRAVEL-DOC-CLOSEOUT-01)")
        END = "WO-TRIP-PHOTO-PALETTE-01 P2"
        self.assertIn(END, _CSS[start:],
                      "the end marker this scan is bounded by is gone; "
                      "re-bound it deliberately rather than scanning to EOF")
        block = _CSS[start:_CSS.index(END, start)]
        # #fffdf7 is the existing card background, already used by
        # .tdl-doc-section; anything else would be a new colour.
        literals = set(re.findall(r"#[0-9a-fA-F]{3,8}\b", block))
        self.assertLessEqual(literals, {"#fffdf7"},
                             f"new colour literals: {sorted(literals)}")


class ThePreviewReadsTheKeysTheBackendEmitsTest(unittest.TestCase):
    """THE BUG THAT MADE THE PREVIEW LOOK EMPTY.

    The backend returns `part_one_journey_in_order` and
    `part_two_themes`. The first cut of the renderer read `part_one` and
    `part_two`, which do not exist — so `undefined || []` produced a
    silent empty list, every region rendered as nothing, and the preview
    appeared blank while the exported DOCX was full.

    Nothing failed loudly, and nothing in the first test suite caught it:
    it asserted the ROUTE was called, not that the response was read. A
    route-called test and a keys-match test are different tests, and only
    one of them would have found this.
    """

    def setUp(self):
        self.src = _strip_js_comments(_JS)
        i = self.src.index("function renderTravelDocument(")
        self.body = self.src[i:self.src.index("function renderDraft()", i)]

    def _emitted_keys(self):
        """Top-level keys the preview route actually returns."""
        i = _REPO_SVC.index("def trip_memoir_preview(")
        fn = _REPO_SVC[i:_REPO_SVC.index("\ndef ", i + 10)]
        ret = fn[fn.rindex("    return {"):]
        return set(re.findall(r'^\s{8}"(\w+)":', ret, re.M))

    def test_the_renderer_reads_only_keys_the_backend_emits(self):
        emitted = self._emitted_keys()
        self.assertIn("part_one_journey_in_order", emitted)
        self.assertIn("part_two_themes", emitted)
        read = set(re.findall(r"\bp\.(\w+)", self.body))
        unknown = read - emitted
        self.assertEqual(set(), unknown,
                         f"the preview reads keys the backend never "
                         f"returns: {sorted(unknown)}")

    def test_the_retired_key_names_are_gone(self):
        self.assertNotIn("p.part_one ", self.body)
        self.assertNotIn("p.part_two ", self.body)

    def test_every_category_the_docx_contains_is_previewed(self):
        """Trip-level notes and sources, regions, nested stops, themes
        and the photo appendix. A preview that stopped at the top level
        would under-report a real trip -- `_stop_line` recurses into
        `day_trips` and the DOCX walks them."""
        for token in ("p.story_notes", "p.sources",
                      "p.part_one_journey_in_order", "p.part_two_themes",
                      # [Held "p.part_three_photo_appendix" and
                      # "p.part_one_days". The appendix is retired and
                      # the approved-day lane was replaced by the
                      # timeline snapshot.]
                      "p.part_one_timeline",
                      "stop.day_trips", "region.stops"):
            with self.subTest(token=token):
                self.assertIn(token, self.body, token)

    def test_nested_day_trips_recurse(self):
        self.assertIn("stopBlock(child, (depth || 0) + 1)", self.body)


class OnlyNarratorSafeCaptionsAreExportedTest(unittest.TestCase):
    """P0. Unapproved operator or generated text was reaching a family
    document.

    The caption chain was `narrator_caption or caption or
    photo_description`, with no `caption_approved_for_lori` check. The
    rule already existed in `_NARRATOR_PHOTO_LINK_COLS` -- narrator
    caption first, operator caption only when approved, else nothing --
    but that constant guards the narrator READ, and the export query is
    a `SELECT l.*`, so the raw column and the photo's own description
    arrived unfiltered.

    `photo_description` is operator- or machine-written text nobody
    approved for a narrator to hear. Printed under a photograph in a
    memoir it is indistinguishable, to the reader, from something the
    narrator said.
    """

    def setUp(self):
        # MOVED 2026-08-05: the rule now lives beside the appendix
        # grouping, in trip_repository, so the preview and the DOCX apply
        # ONE implementation. A second copy in the builder would drift,
        # and the direction it drifts in is unapproved text reaching a
        # family document.
        self.src = _REPO_SVC
        self.docx_src = (_SERVER / "api" / "services"
                         / "trip_memoir_docx.py").read_text(encoding="utf-8")

    def _caption(self, row):
        ns = {}
        i = self.src.index("def _safe_photo_caption(")
        exec(compile(self.src[i:self.src.index("\ndef ", i + 10)],
                     "<repo>", "exec"), ns)
        return ns["_safe_photo_caption"](row)

    def test_the_narrator_caption_always_wins(self):
        self.assertEqual("Peter and Josie", self._caption({
            "narrator_caption": "Peter and Josie",
            "caption": "operator text", "caption_approved_for_lori": 1,
            "photo_description": "a headstone"}))

    def test_an_approved_operator_caption_is_used(self):
        self.assertEqual("Bismarck cemetery", self._caption({
            "narrator_caption": "", "caption": "Bismarck cemetery",
            "caption_approved_for_lori": 1}))

    def test_an_unapproved_operator_caption_is_dropped(self):
        self.assertEqual("", self._caption({
            "narrator_caption": "", "caption": "Bismarck cemetery",
            "caption_approved_for_lori": 0}))

    def test_the_photo_description_is_never_used(self):
        """The fall-through that made this a leak rather than a gap."""
        self.assertEqual("", self._caption({
            "photo_description": "grave marker, granite, weathered"}))
        self.assertEqual("", self._caption({
            "narrator_caption": "", "caption": "",
            "caption_approved_for_lori": 1,
            "photo_description": "grave marker, granite, weathered"}))

    def test_no_caption_is_the_right_answer_when_nothing_is_approved(self):
        """A photograph with a date and no words is honest; a photograph
        with words nobody sanctioned is not."""
        self.assertEqual("", self._caption({}))

    def test_the_builder_has_no_caption_rule_of_its_own(self):
        """[Asserted the builder names `_safe_photo_caption`, the
        repository helper the appendix used. Retired 2026-08-06: the
        appendix is gone and captions are chosen once, with their
        provenance, inside `_day_photo_items` -- which both the live
        timeline and the document read. The surviving claim is the same
        one: the BUILDER must not choose a caption itself.]"""
        docx_src = (_SERVER / "api" / "services"
                    / "trip_memoir_docx.py").read_text(encoding="utf-8")
        code = re.sub(r"#.*$", "", docx_src, flags=re.M)
        code = re.sub(r'"""[\s\S]*?"""', "", code)
        for banned in ("narrator_caption", "photo_description",
                       "caption_approved_for_lori"):
            self.assertNotIn(banned, code, banned)
        return

    def _retired_test_the_builder_has_no_caption_rule_of_its_own(self):
        """One implementation. The builder reads the projection's
        caption; it does not choose one."""
        code = re.sub(r"^\s*#.*$", "", self.docx_src, flags=re.M)
        self.assertNotIn("photo_description", code)
        self.assertNotIn("def _safe_caption", code)
        self.assertIn('ph.get("caption")', code)


class TheApprovalControlsExistWhereTheTabSaysTest(unittest.TestCase):
    """P0. The Travel Document tab told the operator to tick "In memoir"
    on the Sources and Photos tabs, and neither tab had the control --
    Sources showed it as a read-only badge, Photos showed the approval
    flags read-only. New sources and photographs could not be approved
    into the document through the interface at all.
    """

    def setUp(self):
        self.src = _strip_js_comments(_JS)

    def test_sources_can_be_ticked_into_the_memoir(self):
        self.assertIn('"/api/trips/sources/" + encodeURIComponent(s.id)',
                      self.src)
        i = self.src.index('"/api/trips/sources/" + encodeURIComponent(s.id)')
        block = self.src[i - 400:i + 300]
        self.assertIn("include_in_memoir: srcCb.checked", block)
        self.assertIn("reloadSources()", block)

    def test_photo_links_can_be_ticked_into_the_memoir(self):
        self.assertIn('"/api/trips/photo-links/" + encodeURIComponent(sel.id)',
                      self.src)
        i = self.src.index('"/api/trips/photo-links/" + encodeURIComponent(sel.id)')
        block = self.src[i - 400:i + 300]
        self.assertIn("include_in_memoir: memCb.checked", block)
        self.assertIn("reloadPhotoLinks()", block)

    def test_the_lori_approval_flags_stay_read_only(self):
        """Those govern what LORI may say, which is a different decision
        from what goes in the family document. Ticking one must not tick
        the other."""
        for flag in ("caption_approved_for_lori",
                     "operator_context_approved_for_lori"):
            with self.subTest(flag=flag):
                self.assertNotIn(f"body: {{ {flag}", self.src)

    def test_a_failed_tick_reverts_the_checkbox(self):
        """Otherwise the box shows approved while the server does not."""
        self.assertIn("srcCb.checked = !srcCb.checked;", self.src)
        self.assertIn("memCb.checked = !memCb.checked;", self.src)


class ThePreviewCannotGoStaleTest(unittest.TestCase):
    """Pre-acceptance defect 1.

    The preview was cached on the first visit and never invalidated, so
    approving the gravesite note moved the COUNTS (which read live `st`)
    while the rendered preview stayed as it was. The tab could show
    "3 story notes in the document" above a preview containing two, and
    the exported DOCX matched neither.
    """

    def setUp(self):
        self.src = _strip_js_comments(_JS)

    def test_there_is_one_invalidation_seam(self):
        self.assertIn("function invalidateMemoirPreview(", self.src)
        self.assertIn("st.memoirPreview = null;", self.src)

    def test_every_eligibility_reload_invalidates(self):
        """The seam is inside the RELOADS, not at each approval call
        site. Seven writes can change eligibility today and all of them
        end in a reload; a seam at the reload is inherited by the write
        somebody adds next month, which is exactly what a list of call
        sites is not."""
        for fn in ("reloadNotes", "reloadSources", "reloadPhotoLinks",
                   "reloadCaptured"):
            with self.subTest(reload=fn):
                i = self.src.index("function " + fn + "(")
                body = self.src[i:self.src.index("\n  }", i)]
                self.assertIn("invalidateMemoirPreview", body,
                              f"{fn} can change what is in the document "
                              f"without invalidating the preview")

    def test_a_whole_trip_refresh_drops_the_cache(self):
        i = self.src.index("st.photoLinks = outs[2].photo_links")
        self.assertIn("st.memoirPreview = null", self.src[i - 200:i])

    def test_it_refetches_only_while_the_tab_is_open(self):
        """On any other tab, dropping the cache is enough — the
        tab-switch handler fetches when it finds nothing cached. A
        background refetch would be a request for a surface nobody is
        looking at."""
        i = self.src.index("function invalidateMemoirPreview(")
        body = self.src[i:self.src.index("\n  }\n", i)]
        self.assertIn('st.tab !== "document"', body)
        self.assertIn("return Promise.resolve();", body)

    def test_a_late_preview_cannot_land_on_a_different_trip(self):
        """The operator can switch trips while the refetch is in flight."""
        i = self.src.index("function invalidateMemoirPreview(")
        body = self.src[i:self.src.index("\n  }\n", i)]
        self.assertIn("st.trip.id !== tripId", body)

    def test_the_refetch_is_guarded_on_a_destroyed_mount(self):
        i = self.src.index("function invalidateMemoirPreview(")
        body = self.src[i:self.src.index("\n  }\n", i)]
        self.assertGreaterEqual(body.count("destroyed"), 2)


class SequentialExportsCleanUpTest(unittest.TestCase):
    """Pre-acceptance defect 3.

    Two exports inside the same minute overwrote both module vars, so
    the first blob URL was left with no timer pointing at it and no way
    to reach it — leaked for the life of the page, holding a
    multi-megabyte buffer.
    """

    def setUp(self):
        self.src = _strip_js_comments(_JS)

    def test_the_previous_url_is_revoked_before_the_new_one_is_stored(self):
        i = self.src.index("docExportRevokeUrl = href;")
        before = self.src[i - 400:i]
        self.assertIn("docExportRevokeNow();", before,
                      "a second export takes ownership without retiring "
                      "the first blob's cleanup")

    def test_the_helper_clears_both_the_timer_and_the_url(self):
        i = self.src.index("function docExportRevokeNow(")
        body = self.src[i:self.src.index("\n  }", i)]
        self.assertIn("clearTimeout(docExportRevokeTimer)", body)
        self.assertIn("revokeObjectURL(docExportRevokeUrl)", body)
        self.assertIn("docExportRevokeTimer = null", body)
        self.assertIn("docExportRevokeUrl = null", body)

    def test_destroy_still_runs_the_same_cleanup(self):
        self.assertIn("docExportRevokeNow()", _destroy_body(self.src))


def _destroy_body(src: str) -> str:
    i = src.index("destroy: function () {")
    return src[i:src.index("\n    }", i)]


class HiddenPhotosAreVisibleAndRestorableTest(unittest.TestCase):
    """P1. Hidden-approved photographs disappeared with no way to see or
    restore them: the hidden-approved counts covered notes and sources
    only, and the Photos reload never asked for hidden rows even though
    the API has always supported it."""

    def setUp(self):
        self.js = _strip_js_comments(_JS)

    def test_the_server_counts_hidden_photos(self):
        self.assertIn('"photos_hidden"', _REPO_SVC)
        # Counted by a dedicated helper that JOINS photos, because a
        # hidden link whose photograph has been soft-deleted cannot be
        # restored into the document and counting it would send the
        # operator looking for something that is gone.
        self.assertIn("def _hidden_photo_count(", _REPO_SVC)
        self.assertIn("p.deleted_at IS NULL", _REPO_SVC)

    def test_the_photos_reload_can_ask_for_hidden(self):
        i = self.js.index("function reloadPhotoLinks(")
        body = self.js[i:self.js.index("\n  }", i)]
        self.assertIn("st.showHiddenPhotos", body)
        self.assertIn("include_hidden=1", body)

    def test_the_photos_tab_has_show_hidden_and_restore(self):
        self.assertIn("st.showHiddenPhotos = !st.showHiddenPhotos", self.js)
        self.assertIn("setPhotoLinkHidden(sel.id, false)", self.js)
        self.assertIn("setPhotoLinkHidden(sel.id, true)", self.js)

    def test_restoring_is_a_patch_never_a_delete(self):
        i = self.js.index("function setPhotoLinkHidden(")
        body = self.js[i:self.js.index("\n  }", i)]
        self.assertIn('method: "PATCH"', body)
        self.assertNotIn("DELETE", body)


class ThePreviewCannotBeOverwrittenByAnOlderResponseTest(unittest.TestCase):
    """P1. The trip guard rejects a response for a DIFFERENT trip, and
    that is not enough: two refreshes of the SAME trip can complete out
    of order, so an older preview can land second and reappear under
    counts that have already moved."""

    def setUp(self):
        self.js = _strip_js_comments(_JS)

    def test_there_is_a_monotonic_token(self):
        self.assertIn("var memoirPreviewToken = 0;", self.js)
        self.assertIn("memoirPreviewToken += 1;", self.js)

    def test_both_fetch_sites_take_a_token(self):
        """The invalidation refetch and the tab-switch fetch can be in
        flight together, so guarding only one leaves the race open."""
        # FIVE sites now, not two: the two fetches plus trip-select,
        # trip-delete and the whole-bundle refresh. Every cache
        # invalidation must supersede an in-flight request, including the
        # ones that make no request of their own.
        self.assertEqual(5, self.js.count("memoirPreviewToken += 1;"))

    def test_a_superseded_response_does_not_write(self):
        for guard in ("if (token !== memoirPreviewToken) return;",
                      "if (_docToken !== memoirPreviewToken) return;"):
            with self.subTest(guard=guard):
                self.assertIn(guard, self.js)


class ExportFilenamesSurviveNonLatinTitlesTest(unittest.TestCase):
    """P2. `c.isalnum()` is True for 'é', 'Ж' and '京'. Those reached a
    bare `filename="..."` header, which is latin-1 only, so a trip called
    "Königsberg" or "京都 2019" could fail at the header rather than at
    the document -- and the family whose trip it is are exactly the
    people who would hit it."""

    def test_the_ascii_fallback_is_ascii(self):
        self.assertIn("c.isalnum() and c.isascii()", _TRIPS)

    def test_a_utf8_filename_star_is_also_sent(self):
        self.assertIn("filename*=UTF-8''", _TRIPS)
        self.assertIn("from urllib.parse import quote", _TRIPS)

    def test_the_header_carries_both_forms(self):
        i = _TRIPS.index("Content-Disposition")
        block = _TRIPS[i:i + 300]
        self.assertIn('filename="{filename}"', block)
        self.assertIn("filename*=UTF-8", block)

    def test_the_ascii_form_never_empties_out(self):
        """A title of only non-Latin characters must still produce a
        usable name rather than `lorevox_trip_memoir_.docx`."""
        self.assertIn('.strip("_") or "trip"', _TRIPS)


class HiddenPhotosAreIsolatedFromEveryOtherConsumerTest(unittest.TestCase):
    """#2. `st.photoLinks` has ~14 consumers -- day counts, route badges,
    the header total, day-linked photos, the filter rail, and the day
    photo PICKER -- and none of them filter on `hidden`. Merging hidden
    rows into it made the picker offer a hidden photograph as
    attachable, which writes a trip_day_id onto a link that can never
    appear on that day.
    """

    def setUp(self):
        self.js = _strip_js_comments(_JS)

    def test_the_visible_reload_never_asks_for_hidden(self):
        i = self.js.index("function reloadPhotoLinks(")
        body = self.js[i:self.js.index("\n  }", i)]
        first = body[:body.index("st.photoLinks = out.photo_links")]
        self.assertNotIn("include_hidden", first,
                         "the visible list is being polluted with hidden rows")

    def test_hidden_rows_land_in_their_own_array(self):
        self.assertIn("st.hiddenPhotoLinks", self.js)
        i = self.js.index("function reloadPhotoLinks(")
        body = self.js[i:self.js.index("function photoLinksForReview(", i)]
        self.assertIn("include_hidden=1", body)
        self.assertIn("st.hiddenPhotoLinks =", body)

    def test_only_the_review_surface_combines_them(self):
        self.assertIn("function photoLinksForReview(", self.js)
        # The DEFINITION matches this pattern too, so consumers are
        # total minus one. My first cut asserted 2 and failed at 3 for
        # exactly that reason.
        uses = re.findall(r"photoLinksForReview\(\)", self.js)
        self.assertEqual(3, len(uses),
                         f"photoLinksForReview() appears {len(uses)} times "
                         f"(1 definition + 2 consumers); only the review "
                         f"gallery and its filter rail may see hidden rows")

    def test_the_day_picker_never_sees_hidden_rows(self):
        """The one that would write bad data: attaching a hidden photo to
        a day, where it can never appear."""
        # `var pickable = ` occurs twice -- the SOURCES picker comes
        # first in the file. My first cut anchored on the bare string and
        # asserted the photo rule against the sources picker, which is a
        # test that could never fail for the right reason.
        i = self.js.index("var pickable = st.photoLinks.filter")
        self.assertNotIn("photoLinksForReview", self.js[i:i + 200])

    def test_the_bundle_load_also_stays_visible_only(self):
        i = self.js.index('api("/api/trips/" + t + "/photo-links")')
        self.assertNotIn("include_hidden", self.js[i:i + 80])

    def test_hidden_is_cleared_when_the_toggle_is_off(self):
        """Otherwise a stale hidden array outlives the toggle and the
        gallery keeps showing rows the operator stopped asking for."""
        i = self.js.index("function reloadPhotoLinks(")
        body = self.js[i:self.js.index("function photoLinksForReview(", i)]
        self.assertIn("if (!st.showHiddenPhotos) { st.hiddenPhotoLinks = [];",
                      body)


class TheBrowserReadsTheUtf8FilenameTest(unittest.TestCase):
    """#8. The server emits both forms and the browser read only the
    ASCII one, so "Königsberg" downloaded as "K_nigsberg".

    I previously reported this as working on the strength of a test that
    asserted the SERVER header. That test was correct and was not
    measuring what the operator experiences.
    """

    def setUp(self):
        self.js = _strip_js_comments(_JS)

    def test_filename_star_is_preferred(self):
        i = self.js.index("var star =")
        j = self.js.index('var hit = /filename="', i)
        self.assertLess(i, j, "the ASCII form is read first")
        self.assertIn("decodeURIComponent(star[3].trim())", self.js)

    def test_the_regex_accepts_the_rfc_shape(self):
        """`filename*=UTF-8''<encoded>`, with an optional language tag
        between the apostrophes."""
        m = re.search(r"var star = (/.+?/i)\.exec", self.js)
        self.assertIsNotNone(m, "the filename* regex is gone")
        self.assertIn("filename", m.group(1))
        self.assertIn("[^']*", m.group(1))

    def test_a_malformed_encoding_falls_back_rather_than_failing(self):
        i = self.js.index("decodeURIComponent(star[3].trim())")
        block = self.js[i:i + 300]
        self.assertIn("catch", block)
        self.assertIn('name = "";', block)

    def test_the_server_truncates_the_title_not_the_extension(self):
        """Slicing the assembled filename at 120 characters cuts `.docx`
        off a long title, and the operator saves a file Word will not
        open by double-click."""
        self.assertIn("raw_title[:80]", _TRIPS)
        self.assertNotIn('.docx"[:120]', _TRIPS)


class TheBundleRefreshesHiddenPhotosTest(unittest.TestCase):
    """A whole-trip refresh reloaded the visible photos and left
    `hiddenPhotoLinks` alone, so with Show hidden active the review
    gallery kept rows from the previous trip state after a cross-tab
    save."""

    def setUp(self):
        self.js = _strip_js_comments(_JS)
        # Anchored on the hidden-photo block itself. `include_hidden=1`
        # also appears in the bundle's NOTES and SOURCES calls, so a
        # slice of the whole function found the wrong occurrence and the
        # ordering assertion below compared two unrelated offsets.
        i = self.js.index("function loadTripBundle(")
        self.body = self.js[i:self.js.index("function refreshTripsPreserving", i)]
        j = self.body.index("st.hiddenPhotoLinks = [];")
        self.hidden_block = self.body[j:]

    def test_the_bundle_clears_the_stale_hidden_snapshot(self):
        self.assertIn("st.hiddenPhotoLinks = [];", self.body)

    def test_it_clears_before_it_refetches(self):
        """A failed refetch must leave an empty list, not a stale one."""
        self.assertIn("include_hidden=1", self.hidden_block,
                      "the refetch does not follow the clear")

    def test_it_refetches_when_show_hidden_is_active(self):
        """Clearing alone would be a different bug: the hidden rows
        vanish from the gallery until the operator toggles twice."""
        self.assertIn("if (st.showHiddenPhotos && st.trip",
                      self.hidden_block)
        self.assertIn("photo-links?include_hidden=1", self.hidden_block)

    def test_the_refetch_is_guarded_by_trip_and_mount(self):
        i = self.hidden_block.index("photo-links?include_hidden=1")
        block = self.hidden_block[i:i + 400]
        self.assertIn("if (destroyed || !st.trip || st.trip.id !== tripId)",
                      block)

    def test_a_failed_refetch_leaves_it_empty(self):
        i = self.hidden_block.index("photo-links?include_hidden=1")
        block = self.hidden_block[i:i + 500]
        self.assertIn("catch", block)


class NarratorStoriesAreNotSweptInTest(unittest.TestCase):
    """Chris's explicit boundary, pinned so it cannot erode quietly.

    `story_candidates` are narrator-scoped. Correlating them to a trip by
    text would put one trip's stories into another trip's document, and
    that is exactly the kind of error nobody notices until a finished
    memoir is in someone's hands.
    """

    def test_the_export_route_does_not_read_story_candidates(self):
        i = _TRIPS.index("def export_docx(")
        body = _TRIPS[i:i + 1500]
        self.assertNotIn("story_candidate", body)

    def test_the_preview_does_not_read_story_candidates(self):
        i = _REPO_SVC.index("def trip_memoir_preview(")
        body = _REPO_SVC[i:i + 4000]
        self.assertNotIn("story_candidate", body)

    def test_the_document_tab_does_not_reach_for_them_either(self):
        src = _strip_js_comments(_JS)
        i = src.index("function renderTravelDocument(")
        body = src[i:src.index("function renderDraft()", i)]
        self.assertNotIn("story_candidate", body)
        self.assertNotIn("story-candidates", body)


class TheRouteSurfaceIsUnchangedTest(unittest.TestCase):
    """This work order adds no endpoint. It wires an existing one."""

    def test_no_new_export_route_was_added(self):
        routes = re.findall(r'@router\.\w+\("([^"]+)"', _TRIPS)
        exports = [r for r in routes if "export" in r or "docx" in r]
        self.assertEqual(["/{trip_id}/export-docx"], exports,
                         f"export routes drifted: {exports}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
