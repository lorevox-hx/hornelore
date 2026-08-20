"""One canonical memoir read: preview, TXT and DOCX agree.

WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01, Commit B (2026-08-19).

The defect: three surfaces produced the narrator's memoir and none of
them agreed. The panel built its own view from `/api/facts/list`; the TXT
export serialised the panel; and the DOCX export took the browser's
payload and then, server-side and INVISIBLY, appended reviewed captured
stories and approved trip notes.

So the reviewed evidence -- the narrator's own words, the thing the whole
review pipeline exists to protect -- appeared in the DOCX and in neither
of the other two. An operator approved a story, saw no sign of it in the
preview, and exported a document containing it. The reverse is equally
possible and worse: prose the operator wrote incorporating a story, plus
the same story appended again underneath, because the visible prose
carried no source id.

Run with:

    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_memoir_canonical_contract
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
for _p in (str(_SERVER_CODE), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api import db as _db  # noqa: E402
from api.services import memoir_contract as _mc  # noqa: E402
from api.routers import memoir_export as _me  # noqa: E402
from tests.source_scan_helpers import strip_js_comments  # noqa: E402

_SHELL = _REPO_ROOT / "ui" / "hornelore1.0.html"
_PANEL = _REPO_ROOT / "ui" / "js" / "bug-panel-story-review.js"


def _read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


class _Base(unittest.TestCase):
    def setUp(self):
        fd = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        fd.close()
        self.db_path = Path(fd.name)
        self._orig = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()
        self.narrator = str(uuid.uuid4())
        self.conv = "conv-" + uuid.uuid4().hex[:8]
        con = sqlite3.connect(str(self.db_path))
        con.execute("INSERT INTO people (id, display_name, created_at, updated_at)"
                    " VALUES (?,?,?,?)",
                    (self.narrator, "N", "2026-08-19", "2026-08-19"))
        con.execute("INSERT INTO sessions (conv_id, updated_at) VALUES (?,?)",
                    (self.conv, "2026-08-19"))
        con.commit()
        con.close()

    def tearDown(self):
        _db.DB_PATH = self._orig
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def _story(self, text, *, language="en", placed=True, status="promoted"):
        cid = str(uuid.uuid4())
        _db.story_candidate_insert(
            cid, narrator_id=self.narrator, transcript=text,
            trigger_reason="manual", scene_anchor_count=1,
            session_id=self.conv, conversation_id=self.conv, turn_id=None,
            language=language)
        _db.story_candidate_review_apply(
            cid, narrator_id=self.narrator, expected_version=1,
            review_status=status, reviewed_by="test",
            era_candidates=["adolescence"] if placed else None,
            placement_source="operator_set" if placed else None)
        return cid


# ── The contract itself ─────────────────────────────────────────────────

class TheContractIsOneRead(_Base):

    def test_reviewed_stories_come_back_with_stable_source_ids(self):
        cid = self._story("The porch and the peas.")
        out = _mc.canonical_memoir(self.narrator)
        self.assertEqual(len(out.stories), 1)
        self.assertEqual(out.stories[0]["source_id"],
                         _mc.story_source_id(cid))
        self.assertEqual(out.stories[0]["era"], "adolescence")
        self.assertEqual(out.stories[0]["language"], "en")

    def test_the_export_delegates_rather_than_reimplements(self):
        """Equality alone was a tautology.

        Mutation testing: changing the contract's digest changed the
        export's too, because the export CALLS it -- so asserting they
        match proved nothing about whether they could drift. The property
        that matters is the delegation: one definition, so the preview
        and the DOCX cannot derive an id differently and leave a caller
        unable to tell one telling from two.
        """
        cid = self._story("Told once.")
        self.assertEqual(_mc.story_source_id(cid),
                         _me._story_source_digest(cid))
        src = _read(Path(_me.__file__))
        for fn, expect in (("_story_source_digest", "story_source_id"),
                           ("_trip_note_source_digest", "trip_note_source_id")):
            body = src[src.index("def " + fn + "("):]
            body = body[:body.index("\ndef ")]
            with self.subTest(fn=fn):
                self.assertIn("memoir_contract", body)
                self.assertIn(expect, body)
                self.assertNotIn("hashlib.sha256", body,
                                 "a second implementation is a second answer")

    def test_story_and_note_ids_are_namespaced_apart(self):
        same = "shared-id"
        self.assertNotEqual(_mc.story_source_id(same),
                            _mc.trip_note_source_id(same))

    def test_unreviewed_and_discarded_never_appear(self):
        self._story("Promoted.", status="promoted")
        self._story("Never reviewed.", status="unreviewed")
        self._story("Discarded.", status="discarded")
        texts = [s["text"] for s in _mc.canonical_memoir(self.narrator).stories]
        self.assertEqual(texts, ["Promoted."])

    def test_an_unplaced_story_carries_no_era(self):
        self._story("Nobody placed this.", placed=False)
        row = _mc.canonical_memoir(self.narrator).stories[0]
        self.assertEqual(row["placement"], "unplaced")
        self.assertIsNone(row["era"])

    def test_two_identical_tellings_are_two_sources(self):
        same = "We walked to the river."
        a, b = self._story(same), self._story(same)
        rows = _mc.canonical_memoir(self.narrator).stories
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({r["source_id"] for r in rows}), 2)

    def test_each_candidate_appears_exactly_once(self):
        self._story("Told once.")
        rows = _mc.canonical_memoir(self.narrator).stories
        self.assertEqual(len(rows), 1)


class LaneAvailabilityIsPartOfTheAnswer(_Base):

    def test_an_unreadable_story_lane_is_reported_not_hidden(self):
        from api.services import story_projection as _sp
        orig = _sp.memoir_projection
        _sp.memoir_projection = lambda nid: _sp.MemoirProjection(
            "unavailable", [])
        self.addCleanup(setattr, _sp, "memoir_projection", orig)
        out = _mc.canonical_memoir(self.narrator)
        self.assertEqual(out.lanes["captured_stories"], "unavailable")
        self.assertFalse(out.complete)

    def test_empty_is_distinct_from_unavailable(self):
        out = _mc.canonical_memoir(self.narrator)
        self.assertEqual(out.lanes["captured_stories"], "empty")
        self.assertTrue(out.complete)

    def test_the_caller_can_switch_a_lane_off_and_that_is_not_a_failure(self):
        """RENAMED AND REPOINTED 2026-08-19.

        Retired as `test_trips_off_is_not_attempted_and_does_not_spoil_
        completeness`, which popped `HORNELORE_TRIPS` and expected
        `not_attempted`. That is no longer what the flag means: it
        governs the trip UI, and an approved trip note is evidence an
        operator already reviewed and the database already holds.
        Reporting it `not_attempted` let a complete-looking export omit
        it silently. See `TripNotesAreNotHiddenByTheTripUiFlag` below.

        `not_attempted` still exists and still does not spoil
        completeness -- it is what a lane the CALLER switched off
        reports, which is a request, not a failure.
        """
        os.environ.pop("HORNELORE_TRIPS", None)
        out = _mc.canonical_memoir(self.narrator, include_trip_notes=False)
        self.assertEqual(out.lanes["trip_notes"], "not_attempted")
        self.assertTrue(out.complete,
                        "a lane the caller declined is a configuration "
                        "answer, not a failure")

    def test_the_status_vocabulary_is_shared(self):
        for v in ("read", "empty", "not_attempted", "partial", "unavailable"):
            self.assertIn(v, _mc.LANE_STATUSES)


class TripNotesAreNotHiddenByTheTripUiFlag(_Base):
    """`HORNELORE_TRIPS` governs the trip SCREENS, not whether approved
    trip notes already in the database belong in the memoir.

    THE DEFECT (2026-08-19). The lane returned `not_attempted` whenever
    the flag was off, and `not_attempted` does not spoil completeness --
    so an operator with the trip UI switched off got an export that
    reported itself complete while silently omitting evidence they had
    already reviewed and approved. Persisted evidence is never
    `not_attempted`.
    """

    def _trip_note(self, *, include_in_memoir=1):
        trip_id = str(uuid.uuid4())
        note_id = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO trips (id, person_id, title, created_at, updated_at)"
            " VALUES (?,?,?,?,?)",
            (trip_id, self.narrator, "Germany 1971", "2026-08-19", "2026-08-19"))
        con.execute(
            "INSERT INTO trip_location_notes (id, trip_id, note_text,"
            " include_in_memoir, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (note_id, trip_id, "We arrived in Munich after dark.",
             include_in_memoir, "2026-08-19", "2026-08-19"))
        con.commit()
        con.close()
        return note_id

    def test_an_approved_note_is_read_with_the_flag_off(self):
        os.environ.pop("HORNELORE_TRIPS", None)
        self._trip_note()
        out = _mc.canonical_memoir(self.narrator)
        self.assertEqual(out.lanes["trip_notes"], "read")
        self.assertEqual([n["text"] for n in out.trip_notes],
                         ["We arrived in Munich after dark."])

    def test_the_same_holds_with_the_flag_on(self):
        os.environ["HORNELORE_TRIPS"] = "1"
        self.addCleanup(os.environ.pop, "HORNELORE_TRIPS", None)
        self._trip_note()
        out = _mc.canonical_memoir(self.narrator)
        self.assertEqual(out.lanes["trip_notes"], "read")
        self.assertEqual(len(out.trip_notes), 1)

    def test_a_note_not_approved_for_the_memoir_is_still_excluded(self):
        # The flag is not the review gate; `include_in_memoir` is.
        os.environ.pop("HORNELORE_TRIPS", None)
        self._trip_note(include_in_memoir=0)
        out = _mc.canonical_memoir(self.narrator)
        self.assertEqual(out.trip_notes, [])
        self.assertEqual(out.lanes["trip_notes"], "empty")

    def test_a_schema_with_no_trip_tables_reports_empty(self):
        # Nothing is being omitted: there is nowhere for a note to be.
        con = sqlite3.connect(str(self.db_path))
        con.execute("DROP TABLE IF EXISTS trip_location_notes;")
        con.execute("DROP TABLE IF EXISTS trips;")
        con.commit()
        con.close()
        out = _mc.canonical_memoir(self.narrator)
        self.assertEqual(out.lanes["trip_notes"], "empty")
        self.assertTrue(out.complete)

    def _drop(self, table):
        con = sqlite3.connect(str(self.db_path))
        con.execute("DROP TABLE IF EXISTS %s;" % table)
        con.commit()
        con.close()

    def test_only_the_trips_table_present_reports_unavailable(self):
        """ADDED 2026-08-20. EXACTLY ONE of the two tables used to fall
        into the "no trip storage" arm and report `empty`, so a
        partially applied migration produced an export that called
        itself complete while the surviving table might hold real
        approved notes. One table present is a question this lane
        cannot answer, not an answer of "none".
        """
        self._drop("trip_location_notes")
        out = _mc.canonical_memoir(self.narrator)
        self.assertEqual(out.lanes["trip_notes"], "unavailable")
        self.assertFalse(out.complete)

    def test_only_the_notes_table_present_reports_unavailable(self):
        self._drop("trips")
        out = _mc.canonical_memoir(self.narrator)
        self.assertEqual(out.lanes["trip_notes"], "unavailable")
        self.assertFalse(out.complete)

    def test_a_present_but_unreadable_lane_reports_unavailable(self):
        self._trip_note()
        from api.services import trip_repository as _tr
        orig = _tr.trip_list
        _tr.trip_list = lambda pid: (_ for _ in ()).throw(RuntimeError("db gone"))
        self.addCleanup(setattr, _tr, "trip_list", orig)
        out = _mc.canonical_memoir(self.narrator)
        self.assertEqual(out.lanes["trip_notes"], "unavailable")
        self.assertFalse(out.complete,
                         "an outage on a lane that HAS evidence must refuse "
                         "a complete-looking export")

    def test_the_flag_is_not_consulted_at_all(self):
        import ast
        import inspect
        src = inspect.getsource(_mc._trip_notes)
        body = ast.get_source_segment(src, ast.parse(src).body[0]) or src
        tree = ast.parse(src)
        tree.body[0].body = [n for n in tree.body[0].body
                             if not (isinstance(n, ast.Expr)
                                     and isinstance(n.value, ast.Constant))]
        self.assertNotIn("HORNELORE_TRIPS", ast.unparse(tree),
                         "the docstring explains why the flag is not read; "
                         "the CODE must not read it")


# ── Every surface consumes it ───────────────────────────────────────────

class PreviewAndTxtReadTheSameContract(_Base):

    def setUp(self):
        super().setUp()
        self.js = strip_js_comments(_read(_SHELL))

    def test_the_panel_fetches_the_canonical_route(self):
        self.assertIn("/api/memoir/canonical?person_id=", self.js)
        self.assertIn("function _memoirLoadCanonical(", self.js)

    def test_one_function_feeds_both_the_panel_and_the_txt(self):
        """The preview and the file cannot drift if they are built by the
        same function -- which is the whole point of this commit."""
        # REPOINTED 2026-08-19. The renderer used to call
        # `_memoirCanonicalLines()` -- the flattened STRINGS -- and then
        # attach provenance by matching displayed text back to data,
        # which two identical tellings defeated. Both surfaces now come
        # from ONE builder, `_memoirCanonicalLinesRaw()`: the TXT export
        # takes the flattened form and the renderer takes the records.
        # Still one source; the renderer just no longer throws away the
        # provenance and then guess it back.
        self.assertIn("function _memoirCanonicalLinesRaw(", self.js)
        self.assertIn("function _memoirCanonicalLines(", self.js)
        txt = self.js[self.js.index("function _memoirBuildTxtContent("):]
        txt = txt[:txt.index("function _memoirDownloadTxt(")]
        self.assertIn("_memoirCanonicalLines()", txt)
        flat = self.js[self.js.index("function _memoirCanonicalLines("):]
        flat = flat[:flat.index("function _memoirRenderCanonical(")]
        self.assertIn("_memoirCanonicalRecords()", flat)
        render = self.js[self.js.index("function _memoirRenderCanonical("):]
        render = render[:render.index("function _memoirBuildTxtContent(")]
        self.assertIn("_memoirCanonicalRecords()", render)

    def test_an_unavailable_lane_is_stated_in_the_preview(self):
        # REPOINTED 2026-08-19: the builder is `_memoirCanonicalLinesRaw`.
        lines = self.js[self.js.index("function _memoirCanonicalLinesRaw("):]
        lines = lines[:lines.index("function _memoirRenderCanonical(")]
        self.assertIn("UNAVAILABLE", lines)
        self.assertIn("INCOMPLETE", lines)

    def test_the_docx_route_still_serves_the_same_evidence(self):
        src = _read(Path(_me.__file__))
        self.assertIn("def api_memoir_canonical", src)
        self.assertIn("canonical_memoir(person_id).as_dict()", src)


# ── The narrator-switch race ────────────────────────────────────────────

class DelayedNarratorAcannotRepaintB(_Base):

    def setUp(self):
        super().setUp()
        self.js = strip_js_comments(_read(_SHELL))
        i = self.js.index("async function _memoirLoadStoredFacts(")
        self.fn = self.js[i:i + 2600]

    def test_it_aborts_the_previous_request(self):
        self.assertIn("AbortController", self.fn)
        self.assertIn("_memoirFactsAbort.abort()", self.fn)

    def test_it_carries_a_generation(self):
        self.assertIn("++_memoirFactsGen", self.fn)
        self.assertIn("gen !== _memoirFactsGen", self.fn)

    def test_it_rechecks_the_narrator_before_painting(self):
        self.assertIn("_memoirActivePerson() !== personId", self.fn)

    def test_every_await_is_followed_by_a_staleness_check(self):
        """A guard before the first await and nowhere else would still
        let a response that arrived during the JSON parse repaint."""
        self.assertGreaterEqual(self.fn.count("if (stale()) return"), 2)

    def test_the_canonical_load_is_guarded_the_same_way(self):
        i = self.js.index("async function _memoirLoadCanonical(")
        fn = self.js[i:i + 2000]
        self.assertIn("AbortController", fn)
        self.assertIn("gen !== _memoirCanonicalGen", fn)
        self.assertIn("_memoirActivePerson() !== personId", fn)

    def test_the_canonical_paint_is_narrator_checked(self):
        """REPOINTED 2026-08-19. This pinned `if (!stale())` inside an
        inline `.then`, which became `_memoirLoadCanonicalAndRender`
        when the canonical load was lifted OUT of the facts branch --
        the fix for the defect where zero facts meant no evidence.

        The property is unchanged and is asserted in the helper. Its
        behaviour is proven by execution in
        `scripts/ui/run_memoir_canonical_lifecycle.js`, which a source
        assertion cannot do.
        """
        # REPOINTED AGAIN 2026-08-19: the ownership check moved one step
        # further out, into `_memoirPaintCanonicalIfCurrent()`, so that
        # the paint AND the state re-evaluation it now triggers are
        # guarded together. Same property, one place.
        i = self.js.index("function _memoirPaintCanonicalIfCurrent(")
        fn = self.js[i:i + 600]
        self.assertIn("_memoirCanonicalPerson !== personId", fn)
        self.assertIn("active !== personId", fn)
        self.assertIn("_memoirEvaluateState()", fn)

    def test_the_canonical_load_runs_independently_of_facts(self):
        """The defect a source scan could not see: the load sat inside
        the branch that runs only when `/api/facts/list` returned at
        least one fact, and the live database has zero facts."""
        # REPOINTED 2026-08-19. The canonical READ still starts before
        # and regardless of the facts request -- but it is now awaited
        # and PAINTED after the facts lane has settled, because every
        # facts branch clears the panel. Retired:
        #
        #     call = fn.index("_memoirLoadCanonicalAndRender(personId)")
        #     gate = fn.index("const gen = ++_memoirFactsGen")
        #     assertLess(call, gate)
        #
        # Both orderings are proven by execution in
        # `scripts/ui/run_memoir_canonical_lifecycle.js`; a source scan
        # cannot see which request wins a race.
        i = self.js.index("async function _memoirLoadStoredFacts(")
        fn = self.js[i:i + 1400]
        read = fn.index("const canonicalRead = _memoirLoadCanonical(personId)")
        lane = fn.index("_memoirLoadFactsLane(personId, content)")
        paint = fn.index("_memoirPaintCanonicalIfCurrent(personId)")
        self.assertLess(read, lane,
                        "the evidence request must start regardless of the "
                        "facts request")
        self.assertLess(lane, paint,
                        "and must be painted AFTER the facts lane settles, "
                        "because every facts branch clears the panel")
        self.assertIn("await canonicalRead", fn)


# ── Placement coherence ─────────────────────────────────────────────────

class PlacementIsAtomicAndCoherent(_Base):

    def setUp(self):
        super().setUp()
        self.js = strip_js_comments(_read(_PANEL))

    def test_choosing_an_era_records_operator_set(self):
        i = self.js.index("const eraSel = el('select'")
        window = self.js[i:i + 700]
        self.assertIn("edit.era_candidates = chosen;", window)
        self.assertIn("edit.placement_source = chosen ? 'operator_set' : 'unknown';",
                      window)

    def test_clearing_the_source_clears_the_era(self):
        i = self.js.index("const sourceSel = el('select'")
        window = self.js[i:i + 700]
        self.assertIn("edit.era_candidates = '';", window)

    def test_the_server_still_sends_exactly_one_era(self):
        self.assertIn("body.era_candidates = one ? [one] : [];", self.js)

    def test_clear_placement_still_clears_both(self):
        i = self.js.index("'Clear placement'")
        window = self.js[max(0, i - 900):i]
        self.assertIn("delete _edit(item.id).era_candidates;", window)
        self.assertIn("delete _edit(item.id).placement_source;", window)

    def test_the_server_refuses_an_era_it_does_not_know(self):
        from api.services import story_projection as _sp
        with self.assertRaises(_sp.PlacementRejected):
            _sp.canonical_eras(["buidling_years"])


if __name__ == "__main__":
    unittest.main()


# ── The DOCX consumes the contract, not a second read ───────────────────

class TheDocxCallsTheContractOnce(_Base):

    def test_the_route_no_longer_reads_the_lanes_itself(self):
        """Only the digest helpers delegated before; the route still ran
        `_captured_story_sections` and `_trip_story_sections`, so there
        were TWO executable interpretations of what the lanes contain.
        Ids agreeing did not make eligibility, placement or ordering
        agree, and no digest comparison would have noticed."""
        src = _read(Path(_me.__file__))
        route = src[src.index("def api_memoir_export_docx"):]
        route = route[:route.index("\n@router.get")]
        self.assertIn("canonical_memoir(", route)
        self.assertNotIn("_captured_story_sections(req.person_id)", route)
        self.assertNotIn("_trip_story_sections(req.person_id)", route)

    def test_the_adapter_only_reshapes(self):
        src = _read(Path(_me.__file__))
        fn = src[src.index("def _sections_from_canonical("):]
        fn = fn[:fn.index("\ndef ")]
        for forbidden in ("story_candidate_list_for_memoir", "trip_list(",
                          "location_notes_list(", "memoir_projection("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, fn,
                                 "the adapter must not perform its own read")

    def test_docx_and_the_endpoint_get_identical_ids_and_lanes(self):
        cid = self._story("Shared by both surfaces.")
        canon = _mc.canonical_memoir(self.narrator)
        sections = _me._sections_from_canonical(canon)
        self.assertEqual(sections[0].sources,
                         [s["source_id"] for s in canon.stories])
        self.assertEqual(sections[0].languages,
                         [s["language"] for s in canon.stories])
        self.assertEqual(canon.lanes["captured_stories"], "read")

    def test_an_unplaced_story_lands_in_more_stories(self):
        self._story("Nobody placed this.", placed=False)
        canon = _mc.canonical_memoir(self.narrator)
        ids = [s.id for s in _me._sections_from_canonical(canon)]
        self.assertEqual(ids, ["captured_stories_more"])


# ── Placement coherence, enforced server-side ───────────────────────────

class PlacementCannotBeIncoherent(_Base):

    def _fresh(self):
        cid = str(uuid.uuid4())
        _db.story_candidate_insert(
            cid, narrator_id=self.narrator, transcript="A story.",
            trigger_reason="manual", scene_anchor_count=1,
            session_id=self.conv, conversation_id=self.conv, turn_id=None)
        return cid

    def test_a_source_without_an_era_is_refused(self):
        """Directly through the API, not only through the panel. A rule
        the API does not enforce holds until somebody scripts against
        it."""
        cid = self._fresh()
        with self.assertRaises(ValueError) as ctx:
            _db.story_candidate_review_apply(
                cid, narrator_id=self.narrator, expected_version=1,
                placement_source="operator_set")
        self.assertIn("requires exactly one life era", str(ctx.exception))
        self.assertEqual(_db.story_candidate_get(cid)["placement_source"],
                         "unknown")

    def test_an_era_without_a_source_is_refused(self):
        cid = self._fresh()
        with self.assertRaises(ValueError):
            _db.story_candidate_review_apply(
                cid, narrator_id=self.narrator, expected_version=1,
                era_candidates=["adolescence"])
        self.assertEqual(_db.story_candidate_get(cid)["era_candidates"], [])

    def test_two_eras_are_refused(self):
        cid = self._fresh()
        with self.assertRaises(ValueError):
            _db.story_candidate_review_apply(
                cid, narrator_id=self.narrator, expected_version=1,
                era_candidates=["adolescence", "coming_of_age"],
                placement_source="operator_set")

    def test_the_final_state_is_judged_not_the_request(self):
        """A partial request that LEAVES an incoherent row is refused
        even though the request itself mentioned only one field."""
        cid = self._fresh()
        _db.story_candidate_review_apply(
            cid, narrator_id=self.narrator, expected_version=1,
            era_candidates=["adolescence"], placement_source="operator_set")
        with self.assertRaises(ValueError):
            _db.story_candidate_review_apply(
                cid, narrator_id=self.narrator, expected_version=2,
                placement_source="unknown")     # would orphan the era

    def test_a_coherent_placement_is_accepted(self):
        cid = self._fresh()
        out = _db.story_candidate_review_apply(
            cid, narrator_id=self.narrator, expected_version=1,
            era_candidates=["adolescence"], placement_source="operator_set")
        self.assertEqual(out["placement_source"], "operator_set")
        self.assertEqual(out["era_candidates"], ["adolescence"])

    def test_operator_set_is_not_offered_as_a_manual_choice(self):
        js = strip_js_comments(_read(_PANEL))
        i = js.index("const sourceSel = el('select'")
        window = js[i:i + 500]
        self.assertIn("'unknown', 'narrator_stated', 'dob_derived'", window)
        self.assertNotIn("'operator_set'", window)

    def test_the_review_refreshes_the_memoir(self):
        js = strip_js_comments(_read(_PANEL))
        i = js.index("function afterReviewApplied(")
        window = js[i:i + 900]
        self.assertIn("lvRefreshCanonicalMemoir", window)
