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
        # The route hands ONE projection to both consumers now; the
        # memoir_only filter lives inside it.
        i = _REPO_SVC.index("def photo_appendix_projection(")
        body = _REPO_SVC[i:_REPO_SVC.index("\ndef ", i + 10)]
        self.assertIn("memoir_only=True", body)

    def test_the_export_renders_the_same_preview_the_ui_shows(self):
        """One source of truth. If the export built its own view of the
        trip, the preview would stop being a preview."""
        i = _TRIPS.index("def export_docx(")
        body = _TRIPS[i:i + 1500]
        self.assertIn("trip_repository.trip_memoir_preview(trip_id, appendix=",
                      body)
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
        # `filter(` is allowed now: _docCounts filters the SERVER's own
        # values when summing the hidden lanes. What must never appear is
        # a read of the client's cached arrays.
        for derived in ("st.notes", "st.sources", "st.photoLinks",
                        ".length"):
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


class EveryExportedWordIsReviewableTest(unittest.TestCase):
    """An operator must not be able to export text they never saw.

    The preview need not reproduce Word's formatting, but every field
    the DOCX turns into words has to appear in "What is in the
    document". Four were missing after the first repair: a stop's own
    `notes`, a source's `pasted_text`/`link_url` fallback when it has no
    summary, theme `description`, and the trip/region date and base
    lines.
    """

    #: Fields `build_trip_docx` renders as prose, by the scope they sit
    #: on. Hand-written so the intent is readable, and pinned against the
    #: builder below so it cannot rot when the builder gains a field.
    EXPORTED_TEXT = {
        "preview": ["title", "date_range", "summary", "story_notes",
                    "sources", "part_one_journey_in_order",
                    "part_two_themes", "part_three_photo_appendix"],
        "note": ["note_title", "note_text"],
        "source": ["title", "filename", "source_type", "summary",
                   "pasted_text", "link_url"],
        "stop": ["title", "location_name", "date_start", "date_end",
                 "stop_type", "notes", "story_notes", "sources",
                 "day_trips"],
        "region": ["region", "date_range", "base_address", "summary",
                   "story_notes", "sources", "stops"],
        "theme": ["theme", "description", "stops"],
    }

    def setUp(self):
        self.js = _strip_js_comments(_JS)
        i = self.js.index("function renderTravelDocument(")
        self.body = self.js[i:self.js.index("function renderDraft()", i)]
        self.docx = (_SERVER / "api" / "services"
                     / "trip_memoir_docx.py").read_text(encoding="utf-8")

    def test_every_exported_text_field_is_previewed(self):
        for scope, fields in self.EXPORTED_TEXT.items():
            for f in fields:
                with self.subTest(scope=scope, field=f):
                    self.assertIn(f, self.body,
                                  f"{scope}.{f} is exported to the DOCX but "
                                  f"never rendered in the preview, so an "
                                  f"operator can export text they have not "
                                  f"reviewed")

    def test_the_field_list_still_matches_the_builder(self):
        """Non-vacuity, and rot protection. If the builder starts reading
        a field this list does not name, the list is stale and the test
        above is quietly weaker than it looks."""
        # Every `.get("x")` inside the builder, minus the photo-row and
        # bookkeeping reads, which are not prose the operator reviews.
        reads = set(re.findall(r'\.get\(\s*"(\w+)"', self.docx))
        # Not prose the operator reviews in Part I / II: photo-row
        # columns, and the appendix PROJECTION's own structure. The
        # appendix's text -- group labels, captions, dates and the
        # unavailable-file line -- is proved end to end against a real
        # opened .docx in tests/test_travel_document_docx_artifact.py,
        # which is a stronger instrument than a field-name list.
        photo_row_only = {
            "photo_image_path", "photo_description", "photo_date_value",
            "narrator_caption", "caption", "caption_approved_for_lori",
            "taken_at", "stop_location_name", "region_title",
            "trip_stop_id", "id", "assigned_photos", "unassigned_photos",
            "start", "end",
            # projection structure
            "groups", "photos", "label", "available", "image_path",
            "approved_by_stop", "approved",
        }
        named = {f for fields in self.EXPORTED_TEXT.values() for f in fields}
        unnamed = reads - photo_row_only - named
        self.assertEqual(set(), unnamed,
                         f"the builder reads fields this test does not "
                         f"track: {sorted(unnamed)}")

    def test_the_source_detail_fallback_matches_the_builder(self):
        """The exact chain, in the exact order. A source with pasted
        text and no summary exported a paragraph the preview did not
        show."""
        self.assertIn(
            's.get("summary") or s.get("pasted_text") or', self.docx)
        self.assertIn(
            "srow.summary || srow.pasted_text || srow.link_url", self.body)

    def test_a_title_only_note_is_previewed(self):
        """The DOCX prints a note's title and its body INDEPENDENTLY, so
        a note with a title and no body still reaches the document. The
        preview returned early when the body was empty and hid that title
        from review.

        Added after a surviving mutant: reinstating `if (title && body)`
        left the whole suite green, because nothing asserted the two are
        rendered independently.
        """
        i = self.js.index("function noteBlock(")
        body = self.js[i:self.js.index("\n    }", i)]
        self.assertIn("if (title) parent.appendChild", body)
        self.assertIn("if (body) parent.appendChild", body)
        self.assertNotIn("if (!t) return;", body)
        self.assertNotIn("title && body", body)
        # And the builder really does print them independently.
        i2 = self.docx.index("def _story_notes(")
        dbody = self.docx[i2:self.docx.index("\n    def ", i2)]
        self.assertIn("if t:", dbody)
        self.assertIn("if body:", dbody)

    def test_the_stop_notes_field_is_previewed(self):
        self.assertIn('stop.get("notes")', self.docx)
        self.assertIn("stop.notes", self.body)

    def test_theme_descriptions_are_previewed(self):
        self.assertIn('theme.get("description")', self.docx)
        self.assertIn("t.description", self.body)


class ThePhotoCountsAgreeWithTheDocumentTest(unittest.TestCase):
    """The document contradicted itself.

    Part III opened with "Photos assigned to stops: 4" and closed with
    "(1 photo embedded)". `assigned_photos` is the trip tree's tally of
    every link on a stop -- unapproved, hidden, and links whose
    photograph has been soft-deleted. The appendix embeds only
    memoir-approved, visible, undeleted photographs.
    """

    def setUp(self):
        self.docx = (_SERVER / "api" / "services"
                     / "trip_memoir_docx.py").read_text(encoding="utf-8")

    def test_the_appendix_counts_the_projection_it_was_given(self):
        self.assertIn("appendix_proj.get('approved', 0)", self.docx)
        self.assertIn("Approved photos in appendix", self.docx)

    def test_the_all_link_inventory_is_no_longer_printed(self):
        """It is a workspace number -- useful when deciding what to
        approve, meaningless to a reader holding the document.

        Scanned over comment-stripped source. The retirement comment in
        the builder QUOTES the retired line, which is exactly what this
        repository requires of a correction in place -- and a raw scan
        therefore fires on the explanation rather than on any code. Same
        trap as every other word-matching guard here.
        """
        code = re.sub(r"^\s*#.*$", "", self.docx, flags=re.M)
        self.assertNotIn("Photos assigned to stops", code)
        self.assertNotIn("awaiting assignment", code)
        # Positive half: something IS printed there.
        self.assertIn("Approved photos in appendix", code)

    def test_the_embedded_count_is_reported_after_file_access(self):
        """Approved and embedded are different numbers when a file is
        missing from disk, and the reader should not have to count
        pictures to notice."""
        i_emb = self.docx.index("photo{'s' if embedded != 1 else ''} embedded")
        i_loop = self.docx.index('if not ph.get("available")')
        self.assertLess(i_loop, i_emb)
        self.assertIn("not included", self.docx)

    def test_per_stop_counts_come_from_the_export_set(self):
        """`photo_count` counts every link on the stop, so a stop could
        read "· 3 photos" in a document containing one of them."""
        self.assertIn("_approved_by_stop", self.docx)
        self.assertIn('n_photos = _approved_by_stop.get(stop.get("id"), 0)',
                      self.docx)
        self.assertNotIn('n_photos = stop.get("photo_count")', self.docx)

    def test_the_two_tallies_share_one_source(self):
        """Part I's per-stop counts and Part III's appendix are two views
        of `photo_rows`, so they cannot drift apart."""
        # Both come out of ONE projection call now, which is a stronger
        # form of the same claim than two loops over the same list.
        self.assertEqual(1, self.docx.count("_proj_fn(rows="),
                         "the projection is built more than once")
        i = self.docx.index("_approved_by_stop: Dict[str, int] = appendix_proj")
        self.assertGreater(i, self.docx.index("appendix_proj = _proj_fn("))


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
        self.assertIn("photo_appendix_projection(trip_id)", body)
        self.assertIn('_counts["photos_in"] = _appendix["approved"]', body)
        # `embedded_photos` is RETIRED from the appendix: it held the
        # approved count under a name that promised an embedded one, and
        # #7 requires the three terms be kept apart.
        self.assertNotIn("embedded_photos", body)

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


class ThePhotoAppendixIsOneProjectionTest(unittest.TestCase):
    """P0/P1. The preview printed a number; the DOCX printed group
    headings, captions, dates and a missing-file line. The operator
    reviewed one and the family received the other.
    """

    def setUp(self):
        self.js = _strip_js_comments(_JS)
        self.docx = (_SERVER / "api" / "services"
                     / "trip_memoir_docx.py").read_text(encoding="utf-8")

    def test_there_is_one_projection_function(self):
        self.assertIn("def photo_appendix_projection(", _REPO_SVC)
        self.assertEqual(1, _REPO_SVC.count("def photo_appendix_projection("))

    def test_both_consumers_read_it(self):
        self.assertIn("photo_appendix_projection(trip_id)", _REPO_SVC)
        self.assertIn("photo_appendix_projection as _proj_fn", self.docx)

    def test_the_builder_no_longer_groups_by_display_text(self):
        """Two stops called "Hotel", or a stop and a region sharing a
        name, collapsed into one appendix section -- the photographs of
        two different places silently became one."""
        code = re.sub(r"^\s*#.*$", "", self.docx, flags=re.M)
        self.assertNotIn('row.get("stop_location_name")', code)
        self.assertNotIn("_groups[key]", code)

    def test_groups_are_keyed_by_scope_id(self):
        i = _REPO_SVC.index("def photo_appendix_projection(")
        body = _REPO_SVC[i:_REPO_SVC.index("\ndef ", i + 10)]
        self.assertIn('f"stop:{stop_id}"', body)
        self.assertIn('f"region:{region_id}"', body)

    def test_the_projection_never_carries_photo_description(self):
        """Read as an AST with the docstring dropped.

        The docstring explains, at length, why `photo_description` must
        never appear -- so a text scan fires on the explanation. Stripping
        `#` comments was not enough for the same reason it never is: the
        prose that documents a rule contains the word the rule forbids.
        """
        fn = next(n for n in ast.walk(ast.parse(_REPO_SVC))
                  if isinstance(n, ast.FunctionDef)
                  and n.name == "photo_appendix_projection")
        stmts = fn.body
        first = stmts[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            stmts = stmts[1:]
        code = "\n".join(ast.unparse(n) for n in stmts)
        self.assertNotIn("photo_description", code)
        # Positive half: it DOES read the caption fields it is allowed to.
        self.assertIn("_safe_photo_caption", code)

    def test_the_browser_copy_has_no_filesystem_path(self):
        """A path is not a thing to hand a browser; `photo_id` is what a
        thumbnail needs."""
        i = _REPO_SVC.index('"part_three_photo_appendix": (')
        block = _REPO_SVC[i:i + 2200]
        self.assertIn('if k != "image_path"', block)

    def test_the_preview_renders_the_appendix_not_a_number(self):
        i = self.js.index("function renderTravelDocument(")
        body = self.js[i:self.js.index("function renderDraft()", i)]
        for token in ("app.groups", "g.label", "ph.caption", "ph.taken_at",
                      "ph.available", "app.unavailable"):
            with self.subTest(token=token):
                self.assertIn(token, body, token)


class HiddenPhotosAreVisibleAndRestorableTest(unittest.TestCase):
    """P1. Hidden-approved photographs disappeared with no way to see or
    restore them: the hidden-approved counts covered notes and sources
    only, and the Photos reload never asked for hidden rows even though
    the API has always supported it."""

    def setUp(self):
        self.js = _strip_js_comments(_JS)

    def test_the_server_counts_hidden_approved_photos(self):
        self.assertIn('"photos_hidden_approved"', _REPO_SVC)
        # Counted by a dedicated helper that JOINS photos, because a
        # hidden link whose photograph has been soft-deleted cannot be
        # restored into the document and counting it would send the
        # operator looking for something that is gone.
        self.assertIn("def _hidden_approved_photo_count(", _REPO_SVC)
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


class UnknownIsNeverRenderedAsZeroTest(unittest.TestCase):
    """#5. A failed projection must stay unknown all the way to the
    screen. Turning -1 into 0 converts "we could not find out" into
    "there are none" -- the more confident and the more wrong."""

    def setUp(self):
        self.js = _strip_js_comments(_JS)

    def test_the_preview_reports_unknown_rather_than_an_empty_appendix(self):
        i = _REPO_SVC.index("def trip_memoir_preview(")
        body = _REPO_SVC[i:_REPO_SVC.index("\ndef ", i + 10)]
        self.assertIn("_appendix_unknown", body)
        self.assertIn('"unknown": True', body)
        self.assertIn("_appendix: Optional[Dict[str, Any]] = None", body)

    def test_every_lane_goes_to_minus_one_on_failure(self):
        i = _REPO_SVC.index("def trip_memoir_preview(")
        body = _REPO_SVC[i:_REPO_SVC.index("\ndef ", i + 10)]
        for lane in ("photos_in", "photos_out", "photos_hidden_approved"):
            with self.subTest(lane=lane):
                self.assertIn(f'_counts["{lane}"] = -1', body)

    def test_the_client_does_not_coerce_unknown_to_zero(self):
        i = self.js.index("function _docCounts(")
        body = self.js[i:self.js.index("\n  }", i)]
        self.assertIn("function n(v)", body)
        self.assertIn("return (typeof v === \"number\") ? v : -1;", body)

    def test_the_empty_state_needs_all_three_known_and_zero(self):
        """`photosIn <= 0` included -1, so an unknown photo count printed
        "Nothing is approved for the memoir yet"."""
        self.assertIn("c.notesIn === 0 && c.sourcesIn === 0 && c.photosIn === 0",
                      self.js)
        self.assertNotIn("c.photosIn <= 0", self.js)

    def test_an_unknown_appendix_prints_no_numbers(self):
        self.assertIn("if (app.unknown)", self.js)
        i = self.js.index("if (app.unknown)")
        block = self.js[i:i + 500]
        self.assertIn("unavailable", block)
        self.assertIn("unknown rather than zero", block)


class ApprovedAvailableAndEmbeddedAreDistinctTest(unittest.TestCase):
    """#7. Three different numbers. `approved` is what the operator
    ticked; `available` is what is on disk right now; `embedded` is
    knowable only after Word has accepted each image -- it can refuse a
    file that exists and is readable."""

    def setUp(self):
        self.js = _strip_js_comments(_JS)
        self.docx = (_SERVER / "api" / "services"
                     / "trip_memoir_docx.py").read_text(encoding="utf-8")

    def test_the_preview_promises_no_embedded_count(self):
        self.assertNotIn("will be embedded", self.js)
        self.assertNotIn("The rest will be embedded", self.js)

    def test_the_preview_says_approved_and_not_found(self):
        self.assertIn("approved. Captions are the narrator", self.js)
        self.assertIn("will not appear in the document", self.js)

    def test_the_document_reports_embedded_only_after_the_attempt(self):
        i_loop = self.docx.index("doc.add_picture(")
        i_report = self.docx.index("photo{'s' if embedded != 1 else ''} embedded")
        self.assertLess(i_loop, i_report)

    def test_a_word_refusal_counts_as_not_included(self):
        """The `except` around add_picture is why an embedded count taken
        any earlier would be a promise."""
        i = self.docx.index("doc.add_picture(")
        block = self.docx[i:i + 700]
        self.assertIn("except Exception as exc:", block)
        self.assertIn("skipped += 1", block)


class AnUnavailableOnlyGroupIsNotAnEmptyHeadingTest(unittest.TestCase):
    """#9. A section in a family memoir with a heading and nothing under
    it reads as a mistake or a deletion."""

    def setUp(self):
        self.docx = (_SERVER / "api" / "services"
                     / "trip_memoir_docx.py").read_text(encoding="utf-8")

    def test_the_builder_explains_an_empty_group(self):
        self.assertIn('usable = [ph for ph in photos if ph.get("available")]',
                      self.docx)
        # The sentence wraps across two source lines, so the assertion is
        # on the halves rather than on a string that only exists once the
        # f-strings are joined at runtime.
        self.assertIn("approved here could ", self.docx)
        self.assertIn("not be found on disk and are not shown", self.docx)

    def test_the_skipped_count_still_includes_them(self):
        i = self.docx.index("not be found on disk and are not shown")
        block = self.docx[i:i + 200]
        self.assertIn("skipped += n", block)


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


class TheExportReadsThePhotoTableOnceTest(unittest.TestCase):
    """#3. An export read the link table four times, and the counts
    printed in the document came from a different read than the appendix
    the operator reviewed."""

    def setUp(self):
        self.docx = (_SERVER / "api" / "services"
                     / "trip_memoir_docx.py").read_text(encoding="utf-8")

    def test_the_route_builds_one_projection_and_passes_it_to_both(self):
        i = _TRIPS.index("def export_docx(")
        body = _TRIPS[i:i + 1200]
        self.assertIn("appendix = trip_repository.photo_appendix_projection(trip_id)",
                      body)
        self.assertIn("trip_memoir_preview(trip_id, appendix=appendix)", body)
        self.assertIn("build_trip_docx(preview, appendix=appendix)", body)

    def test_the_route_no_longer_re_reads_the_rows(self):
        i = _TRIPS.index("def export_docx(")
        body = _TRIPS[i:i + 1200]
        self.assertNotIn("photo_links_with_photo_paths", body)

    def test_the_builder_uses_the_given_projection(self):
        self.assertIn("if appendix is not None:", self.docx)
        self.assertIn("appendix_proj = appendix", self.docx)

    def test_the_preview_accepts_a_prebuilt_projection(self):
        self.assertIn("appendix: Optional[Dict[str, Any]] = None", _REPO_SVC)
        self.assertIn("appendix if appendix is not None else", _REPO_SVC)


class PerStopApprovedCountsAreShownTest(unittest.TestCase):
    """#4. The DOCX printed a per-stop total in every Part I bullet and
    the preview did not, so the operator could not check it."""

    def setUp(self):
        self.js = _strip_js_comments(_JS)

    def test_the_browser_consumes_approved_by_stop(self):
        self.assertIn("approved_by_stop", self.js)
        i = self.js.index("function stopBlock(")
        body = self.js[i:self.js.index("\n    }", i)]
        self.assertIn("byStop[stop.id]", body)

    def test_it_is_labelled_approved_not_embedded(self):
        i = self.js.index("byStop[stop.id]")
        block = self.js[i:i + 300]
        self.assertIn("approved photo", block)
        self.assertNotIn("embedded", block)

    def test_a_stop_with_no_approved_photos_says_nothing(self):
        """A bare "· 0 approved photos" on every stop is noise."""
        i = self.js.index("var nStop = byStop[stop.id]")
        self.assertIn("if (nStop) {", self.js[i:i + 120])


class ApprovedIsNotInTheDocumentTest(unittest.TestCase):
    """`photos_in` is the APPROVED count. A file can be missing from disk
    or refused by Word, so "N photos in the document" promises an outcome
    the number cannot guarantee."""

    def setUp(self):
        self.js = _strip_js_comments(_JS)
        self.docx = (_SERVER / "api" / "services"
                     / "trip_memoir_docx.py").read_text(encoding="utf-8")

    def test_the_top_counts_say_approved_for_the_document(self):
        self.assertIn("approved for the document", self.js)
        i = self.js.index("function _docLine(")
        body = self.js[i:self.js.index("\n  }", i)]
        self.assertNotIn('" in the document"', body)

    def test_the_docx_per_stop_bullet_says_approved(self):
        self.assertIn("approved photo{'s' if n_photos != 1 else ''}",
                      self.docx)

    def test_only_the_foot_of_part_three_claims_embedded(self):
        """The one line that has actually tried every image.

        Counted as PARAGRAPHS the document emits, not as occurrences of
        the word: "embedded" also appears in the log line and in the
        comments explaining why the count cannot be taken earlier. My
        first cut counted the word and failed at 3 on its own prose.
        """
        # `add_paragraph(` and the f-string are on separate LINES, so a
        # per-line scan finds neither together. Comment-stripped source,
        # then count the emitted f-strings — the word also appears in the
        # log line and in the comments explaining why the count cannot be
        # taken earlier, and my first two cuts fired on that prose.
        code = re.sub(r"^\s*#.*$", "", self.docx, flags=re.M)
        emitting = re.findall(r'f"\([^"]*embedded', code)
        self.assertEqual(1, len(emitting),
                         f"{len(emitting)} paragraphs claim an embedded "
                         f"count: {emitting}")


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
