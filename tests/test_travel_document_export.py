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
        """The filtering above is correct and invisible. Without a
        visible excluded count, "the gravesite story is not approved
        yet" and "the export is broken" look identical from the outside.

        Asserts the COMPUTATION, not the key name. My first cut checked
        only that `notesOut` appeared in the source, and a mutant that
        kept the key and hard-coded it to 0 sailed straight through --
        which is the exact defect this test exists to catch, since a
        permanently-zero excluded count tells the operator that nothing
        is being held back when something is.
        """
        src = _strip_js_comments(_JS)
        i = src.index("function _docCounts(")
        body = src[i:src.index("\n  }", i)]
        for name, coll in (("notesOut", "notes"),
                           ("sourcesOut", "sources"),
                           ("photosOut", "links")):
            with self.subTest(count=name):
                self.assertIn(
                    f"{name}: {coll}.length - {coll}.filter(inMemoir).length",
                    body,
                    f"{name} is not derived from the unapproved rows")
        self.assertIn("not approved", src)


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
    """Pre-acceptance defect 2.

    `trip_memoir_preview` reads the note and source lists with the
    default `include_hidden=False`, so the export drops hidden rows
    server-side. But `st.notes` and `st.sources` carry hidden rows
    whenever "Show hidden" is on, and counting them as "in the document"
    told the operator a hidden-but-approved note would be in a file that
    will not contain it.
    """

    def setUp(self):
        self.src = _strip_js_comments(_JS)

    def test_the_counts_exclude_hidden_rows(self):
        i = self.src.index("function _docCounts(")
        body = self.src[i:self.src.index("\n  }", i)]
        for coll in ("st.notes", "st.sources", "st.photoLinks"):
            with self.subTest(collection=coll):
                self.assertIn(f"({coll} || []).filter(_visible)", body,
                              f"{coll} is counted without excluding hidden")
        self.assertIn("function _visible(r) { return !r.hidden; }", self.src)

    def test_hidden_but_approved_rows_are_reported_separately(self):
        """Not silently dropped. An operator looking at a hidden row with
        its In-memoir tick still set needs to know the hide is what keeps
        it out, rather than wondering why the tick does nothing."""
        i = self.src.index("function _docCounts(")
        body = self.src[i:self.src.index("\n  }", i)]
        self.assertIn("r.hidden && r.include_in_memoir", body)
        # The RETURNED value must be the computed one. A mutant that kept
        # the computation and returned a literal 0 survived the first
        # cut of this test -- the same shape that got past the notesOut
        # check -- and a permanently-zero hidden count is exactly the
        # silence this defect was about.
        self.assertIn("hiddenApproved: hiddenApproved,", body,
                      "the reported hidden count is not the computed one")
        self.assertIn("stay out of the document while", self.src)

    def test_the_backend_really_does_exclude_hidden(self):
        """Non-vacuity: if the export started including hidden rows, the
        UI counts above would become the wrong fix."""
        i = _REPO_SVC.index("def trip_memoir_preview(")
        body = _REPO_SVC[i:i + 4000]
        self.assertIn("location_notes_list(trip_id)", body)
        self.assertNotIn("include_hidden=True", body)


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
