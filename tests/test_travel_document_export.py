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
    from source_scan_helpers import strip_js_comments
    return strip_js_comments(src)


sys.path.insert(0, str(_REPO / "tests"))


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
        the panel."""
        i = self.src.index("function _exportTravelDocument(")
        body = self.src[i:self.src.index("\n  function ", i + 10)]
        self.assertIn("d.error", body)
        # The anchor is built only after a successful response.
        self.assertLess(body.index('"/export-docx"'),
                        body.index('createElement("a")'))

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
        i = _CSS.index("Travel Document tab (WO-TRAVEL-DOC-CLOSEOUT-01)")
        block = _CSS[i:]
        # #fffdf7 is the existing card background, already used by
        # .tdl-doc-section; anything else would be a new colour.
        literals = set(re.findall(r"#[0-9a-fA-F]{3,8}\b", block))
        self.assertLessEqual(literals, {"#fffdf7"},
                             f"new colour literals: {sorted(literals)}")


class ApprovalDecidesWhatIsInTheDocumentTest(unittest.TestCase):
    """Half two, and the half that matters for trust.

    Read from source because these are ROUTING facts -- which rows the
    preview and the DOCX are built from. The behavioural half runs
    against the real database in the combined acceptance.
    """

    def test_story_notes_are_filtered_on_include_in_memoir(self):
        i = _REPO_SVC.index("def trip_memoir_preview(")
        body = _REPO_SVC[i:i + 4000]
        self.assertIn('if not _n.get("include_in_memoir"):', body)

    def test_sources_are_filtered_on_include_in_memoir(self):
        i = _REPO_SVC.index("def trip_memoir_preview(")
        body = _REPO_SVC[i:i + 4000]
        self.assertIn('if not _s.get("include_in_memoir"):', body)

    def test_the_photo_appendix_asks_for_memoir_photos_only(self):
        i = _TRIPS.index("def export_docx(")
        body = _TRIPS[i:i + 1500]
        self.assertIn("memoir_only=True", body)

    def test_the_export_renders_the_same_preview_the_ui_shows(self):
        """One source of truth. If the export built its own view of the
        trip, the preview would stop being a preview."""
        i = _TRIPS.index("def export_docx(")
        body = _TRIPS[i:i + 1500]
        self.assertIn("trip_repository.trip_memoir_preview(trip_id)", body)
        self.assertIn("build_trip_docx(preview", body)

    def test_the_ui_reads_the_same_preview_route(self):
        self.assertIn('"/memoir-preview"', _strip_js_comments(_JS))

    def test_the_operator_can_see_what_is_being_left_out(self):
        """The filtering is correct and invisible. Without a visible
        excluded count, "the gravesite story is not approved yet" and
        "the export is broken" look identical from the outside.

        REWRITTEN 2026-08-05. The retired version asserted the BROWSER
        computed these from its cached arrays:

            self.assertIn(f"{name}: {coll}.length - {coll}.filter(inMemoir).length", body)

        That derivation WAS the bug. The browser got four things wrong at
        once -- hidden rows, unapproved photos, soft-deleted photos and
        staleness -- because membership is decided server-side, beside
        the walk that builds the document.
        """
        for key in ("notes_in", "notes_out", "sources_in", "sources_out",
                    "photos_in", "photos_out"):
            with self.subTest(key=key):
                self.assertIn(f'"{key}"', _REPO_SVC,
                              f"the server does not report {key}")
        self.assertIn('"export_summary": _counts', _REPO_SVC)
        src = _strip_js_comments(_JS)
        self.assertIn("st.memoirPreview.export_summary", src)
        self.assertIn("not approved", src)

    def test_the_browser_no_longer_derives_membership(self):
        """The seam that mattered. A client that can still compute its
        own answer will drift from the document again."""
        src = _strip_js_comments(_JS)
        i = src.index("function _docCounts(")
        body = src[i:src.index("\n  }", i)]
        for derived in ("st.notes", "st.sources", "st.photoLinks",
                        "filter(", ".length"):
            with self.subTest(token=derived):
                self.assertNotIn(derived, body,
                                 "_docCounts is deriving counts again "
                                 "instead of reading the server's")

    def test_an_uncountable_photo_lane_reads_as_unknown_not_zero(self):
        """-1 is the sentinel. Printing 0 would tell the operator the
        document has no photographs when the truth is that the server
        could not find out."""
        self.assertIn('_counts["photos_in"] = -1', _REPO_SVC)
        src = _strip_js_comments(_JS)
        self.assertIn("count unavailable", src)
        self.assertIn("inCount < 0", src)


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
                      "p.part_three_photo_appendix",
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
        self.src = (_SERVER / "api" / "services"
                    / "trip_memoir_docx.py").read_text(encoding="utf-8")

    def _caption(self, row):
        ns = {}
        i = self.src.index("def _safe_caption(")
        exec(compile(self.src[i:self.src.index("\ndef ", i + 10)],
                     "<docx>", "exec"), ns)
        return ns["_safe_caption"](row)

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

    def test_the_builder_has_no_other_caption_path(self):
        self.assertNotIn('row.get("photo_description")',
                         self.src[self.src.index("def build_trip_docx("):])
        self.assertIn("_safe_caption(row)", self.src)


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


class HiddenRowsAreNotInTheDocumentTest(unittest.TestCase):
    """Pre-acceptance defect 2, fixed on the server.

    REWRITTEN 2026-08-05: these asserted a browser-side `_visible`
    filter. That filter is gone with the rest of the client-side
    derivation; membership is counted beside the walk that decides it.
    """

    def test_the_content_walks_exclude_hidden(self):
        i = _REPO_SVC.index("def trip_memoir_preview(")
        body = _REPO_SVC[i:i + 7000]
        self.assertIn("for _n in location_notes_list(trip_id):", body)
        self.assertIn("for _s in sources_list(trip_id):", body)

    def test_hidden_but_approved_rows_are_counted_and_reported(self):
        """Reported separately, not silently dropped: an operator looking
        at a hidden row whose In-memoir tick is still set needs to know
        the hide is what keeps it out.

        This is the ONE legitimate `include_hidden=True` here -- it
        counts what is being excluded and feeds no content.
        """
        i = _REPO_SVC.index("def trip_memoir_preview(")
        body = _REPO_SVC[i:i + 7000]
        self.assertIn("location_notes_list(trip_id, include_hidden=True)", body)
        self.assertIn("sources_list(trip_id, include_hidden=True)", body)
        self.assertIn('_counts["notes_hidden_approved"] += 1', body)
        src = _strip_js_comments(_JS)
        self.assertIn("notes_hidden_approved", src)
        self.assertIn("stay out of the document while", src)

    def test_the_hidden_walk_feeds_no_content(self):
        """Non-vacuity for the line above. If that walk ever appended to
        a note or source list, hidden rows would be IN the document."""
        i = _REPO_SVC.index(
            "for _hn in location_notes_list(trip_id, include_hidden=True):")
        block = _REPO_SVC[i:i + 500]
        for forbidden in ("_notes_trip.append", "_notes_stop.setdefault",
                          "_notes_region.setdefault", "_src_trip.append"):
            with self.subTest(token=forbidden):
                self.assertNotIn(forbidden, block)

    def test_photo_counts_are_the_embedded_ones(self):
        """The appendix embeds only memoir-approved photos, so the count
        beside it must be those. `assigned_photos` said 4 while the DOCX
        embedded 1, which reads as a broken export rather than as three
        unapproved photographs. Counted through the SAME call the
        exporter makes, so it inherits the hidden-link and
        soft-deleted-photo exclusions the browser count got wrong.
        """
        # Sliced to the function's real end rather than a fixed byte
        # window: my first cut used 8000 and the assertion it wanted sits
        # at 8041, so the test failed on its own window rather than on
        # the code. Fixed windows are the recurring bug in this repo's
        # guards, and a function boundary is what was meant all along.
        i = _REPO_SVC.index("def trip_memoir_preview(")
        body = _REPO_SVC[i:_REPO_SVC.index("\ndef ", i + 10)]
        self.assertIn("photo_links_with_photo_paths(trip_id, memoir_only=True)",
                      body)
        self.assertIn('"embedded_photos": _counts["photos_in"]', body)

    def test_the_export_query_still_excludes_deleted_and_hidden(self):
        """Non-vacuity: the counts are only right because this is."""
        i = _REPO_SVC.index("def photo_links_with_photo_paths(")
        body = _REPO_SVC[i:i + 1800]
        self.assertIn("p.deleted_at IS NULL", body)
        self.assertIn("l.hidden = 0", body)
        self.assertIn("l.include_in_memoir = 1", body)


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
