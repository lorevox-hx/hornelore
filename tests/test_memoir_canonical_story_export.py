"""The memoir exports canonical reviewed stories, with provenance.

WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01, Commit 3 (2026-08-19).

Two legitimate content classes reach the DOCX and must not be confused:
operator-authored sections and prose from the editing surface, which are
INTENDED and are not rejected here; and server-authoritative captured
story evidence, which is review-gated.

The defects this closes:

  * `_captured_story_sections` read `era_candidates[0]` itself -- a
    second, independent reading of placement that disagreed with the
    canonical one, so a machine guess became a chapter heading in a
    document a family keeps;
  * an unreadable story lane produced a memoir missing every approved
    story, logged at WARNING and otherwise indistinguishable from a
    complete one;
  * a client could send a section wearing a reserved `captured_stories`
    id and have it appear as reviewed narrator evidence;
  * nothing exported carried any provenance at all.

Also folded in from the Commit 2 review: bind atomicity, narrator-switch
spine clearing, DOB-independent story reads, and unavailable-never-zero.

Run with:

    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_memoir_canonical_story_export
"""
from __future__ import annotations

import ast
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
from api.services import story_projection as _sp  # noqa: E402
from api.routers import memoir_export as _me  # noqa: E402
from tests.source_scan_helpers import strip_js_comments  # noqa: E402

_UI = _REPO_ROOT / "ui" / "js"


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

    def _story(self, text):
        cid = str(uuid.uuid4())
        _db.story_candidate_insert(
            cid, narrator_id=self.narrator, transcript=text,
            trigger_reason="manual", scene_anchor_count=1,
            session_id=self.conv, conversation_id=self.conv, turn_id=None)
        return cid

    def _review(self, cid, status, *, eras=None, year=None, source=None,
                version=1):
        _db.story_candidate_review_apply(
            cid, narrator_id=self.narrator, expected_version=version,
            review_status=status, reviewed_by="test",
            era_candidates=eras, estimated_year_low=year,
            estimated_year_high=year, placement_source=source)

    def _harvest(self):
        return _me._captured_story_sections(self.narrator)


# ── Eligibility ─────────────────────────────────────────────────────────

class OnlyReviewedStoriesExport(_Base):

    def test_promoted_and_memoir_only_both_export_once(self):
        a = self._story("The promoted one.")
        b = self._story("The memoir-only one.")
        self._review(a, "promoted", eras=["adolescence"], source="operator_set")
        self._review(b, "memoir_only", eras=["adolescence"], source="operator_set")
        sections, status = self._harvest()
        self.assertEqual(status, "read")
        texts = [i for s in sections for i in s.items]
        self.assertEqual(sorted(texts),
                         ["The memoir-only one.", "The promoted one."])

    def test_unreviewed_in_review_and_discarded_never_export(self):
        keep = self._story("Reviewed and kept.")
        self._review(keep, "promoted", eras=["adolescence"], source="operator_set")
        self._story("Never reviewed.")
        mid = self._story("Still in review.")
        self._review(mid, "in_review")
        gone = self._story("Discarded outright.")
        self._review(gone, "discarded")

        sections, _ = self._harvest()
        texts = " ".join(i for s in sections for i in s.items)
        self.assertIn("Reviewed and kept.", texts)
        for banned in ("Never reviewed.", "Still in review.",
                       "Discarded outright."):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, texts)

    def test_the_projection_enforces_eligibility_itself(self):
        """Added after mutation testing.

        Deleting the projection's `memoir_eligible` check left the suite
        green, because `story_candidate_list_for_memoir` filters in SQL
        too and the two gates hide each other. Defence in depth is right,
        but an untested layer is not a layer -- so this drives the
        projection with a transcript source that returns EVERYTHING and
        proves the projection still refuses the ineligible.
        """
        keep = self._story("Promoted.")
        drop = self._story("Never reviewed.")
        self._review(keep, "promoted", eras=["adolescence"],
                     source="operator_set")

        original = _db.story_candidate_list_for_memoir
        _db.story_candidate_list_for_memoir = lambda nid: [
            dict(r) for r in (_db.story_candidate_get(keep),
                              _db.story_candidate_get(drop))
        ]
        self.addCleanup(setattr, _db, "story_candidate_list_for_memoir",
                        original)

        out = _sp.memoir_projection(self.narrator)
        texts = [i["transcript"] for i in out.items]
        self.assertIn("Promoted.", texts)
        self.assertNotIn("Never reviewed.", texts)

    def test_each_candidate_appears_exactly_once(self):
        cid = self._story("Told once.")
        self._review(cid, "promoted", eras=["adolescence"], source="operator_set")
        sections, _ = self._harvest()
        texts = [i for s in sections for i in s.items]
        self.assertEqual(texts.count("Told once."), 1)

    def test_two_identical_tellings_remain_two_sources(self):
        """Deliberately NOT deduplicated by text.

        Two tellings of the same memory are two things the narrator said;
        collapsing them would be the system choosing which of a person's
        own words to discard.
        """
        same = "We walked to the river every Sunday."
        a, b = self._story(same), self._story(same)
        self._review(a, "promoted", eras=["adolescence"], source="operator_set")
        self._review(b, "promoted", eras=["adolescence"], source="operator_set")
        sections, _ = self._harvest()
        texts = [i for s in sections for i in s.items]
        self.assertEqual(texts.count(same), 2)
        digests = [d for s in sections for d in s.sources]
        self.assertEqual(len(set(digests)), 2,
                         "two candidates are two sources, even word-for-word")


# ── Placement ───────────────────────────────────────────────────────────

class PlacementComesFromTheCanonicalService(_Base):

    def test_a_year_only_candidate_exports_as_unplaced(self):
        cid = self._story("Sometime around then.")
        self._review(cid, "promoted", year=1948, source="operator_set")
        sections, _ = self._harvest()
        self.assertEqual([s.id for s in sections], ["captured_stories_more"])
        self.assertIn("More stories", sections[0].label)

    def test_an_unconfirmed_era_candidate_is_not_a_chapter_heading(self):
        """The retired behaviour, and the reason this lane was rewritten.

        `era_candidates[0]` with `placement_source` still `unknown` is a
        machine guess. It used to file the story under that era anyway.
        """
        cid = self._story("A guessed placement.")
        self._review(cid, "promoted", eras=["earliest_years"])
        sections, _ = self._harvest()
        self.assertEqual([s.id for s in sections], ["captured_stories_more"])

    def test_a_real_operator_placement_gets_its_era_section(self):
        cid = self._story("Placed by a human.")
        self._review(cid, "promoted", eras=["coming_of_age"], year=1955,
                     source="operator_set")
        sections, _ = self._harvest()
        self.assertEqual([s.id for s in sections],
                         ["captured_stories_coming_of_age"])

    def test_the_harvest_no_longer_reads_era_candidates_itself(self):
        src = _read(Path(_me.__file__))
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef)
                  and n.name == "_captured_story_sections")
        body = ast.unparse(ast.Module(
            body=[n for n in fn.body
                  if not (isinstance(n, ast.Expr)
                          and isinstance(n.value, ast.Constant)
                          and isinstance(n.value.value, str))],
            type_ignores=[]))
        self.assertIn("memoir_projection", body)
        self.assertNotIn("era_candidates", body)
        self.assertNotIn("story_candidate_list_for_memoir", body)


# ── An unreadable lane refuses rather than looks complete ───────────────

class AnUnreadableStoryLaneRefusesTheExport(_Base):

    def test_the_harvest_reports_its_status(self):
        cid = self._story("Kept.")
        self._review(cid, "promoted", eras=["adolescence"], source="operator_set")
        _, status = self._harvest()
        self.assertEqual(status, "read")

    def test_an_unreadable_story_projection_is_carried_through(self):
        """Added after mutation testing.

        Every other test here patches `memoir_projection` itself, so
        making IT report "read" on an unreadable `project_stories` went
        unnoticed. This drives the real seam: the underlying projection
        fails, and the memoir lane must inherit that verdict rather than
        return an empty list that reads as "this narrator has no stories".
        """
        original = _sp.project_stories
        _sp.project_stories = lambda nid: _sp.StoryProjection(
            status="unavailable", items=[], counts={})
        self.addCleanup(setattr, _sp, "project_stories", original)

        out = _sp.memoir_projection(self.narrator)
        self.assertFalse(out.available)
        self.assertEqual(out.status, "unavailable")
        self.assertEqual(out.items, [])

    def test_a_failed_projection_is_reported_not_swallowed(self):
        original = _sp.memoir_projection
        _sp.memoir_projection = lambda nid: _sp.MemoirProjection("unavailable", [])
        self.addCleanup(setattr, _sp, "memoir_projection", original)
        sections, status = self._harvest()
        self.assertEqual(sections, [])
        self.assertNotEqual(status, "read")

    def test_a_raising_projection_is_reported_not_swallowed(self):
        def _boom(nid):
            raise RuntimeError("db gone")
        original = _sp.memoir_projection
        _sp.memoir_projection = _boom
        self.addCleanup(setattr, _sp, "memoir_projection", original)
        _, status = self._harvest()
        self.assertEqual(status, "unavailable")

    def test_the_route_refuses_rather_than_export_a_gap(self):
        """A family cannot tell that a chapter is absent; they simply
        never see it. So the export refuses instead."""
        src = _read(Path(_me.__file__))
        i = src.index("_story_sections, _story_status = _captured_story_sections")
        window = src[i:i + 1400]
        self.assertIn('_story_status != "read"', window)
        self.assertIn("503", window)


# ── The reserved namespace ──────────────────────────────────────────────

class ClientSectionsCannotSpoofCapturedStories(_Base):

    def test_the_reserved_prefix_is_stripped_from_client_sections(self):
        src = _read(Path(_me.__file__))
        self.assertIn("_RESERVED_STORY_SECTION_PREFIX", src)
        i = src.index("_client_sections = [")
        window = src[i:i + 500]
        self.assertIn("startswith(", window)
        self.assertIn("_RESERVED_STORY_SECTION_PREFIX", window)

    def test_operator_authored_sections_are_still_welcome(self):
        """Client prose is the editing surface doing its job. Only the
        reserved namespace is defended, not client content in general."""
        src = _read(Path(_me.__file__))
        i = src.index("_client_sections = [")
        window = src[i:i + 500]
        self.assertIn("req.sections", window)
        # The filter keeps everything that is NOT reserved.
        self.assertIn("not str(", window)


# ── Provenance survives into the artifact ───────────────────────────────

class ProvenanceTravelsWithTheDocument(_Base):

    def test_each_item_carries_a_digest(self):
        cid = self._story("Something said.")
        self._review(cid, "promoted", eras=["adolescence"], source="operator_set")
        sections, _ = self._harvest()
        self.assertEqual(len(sections[0].sources), len(sections[0].items))
        self.assertTrue(all(d for d in sections[0].sources))

    def test_the_digest_is_stable_and_hides_the_id(self):
        cid = str(uuid.uuid4())
        d1 = _me._story_source_digest(cid)
        d2 = _me._story_source_digest(cid)
        self.assertEqual(d1, d2)
        self.assertNotIn(cid, d1)
        self.assertNotEqual(d1, _me._story_source_digest(str(uuid.uuid4())))

    def test_the_stamp_is_metadata_not_a_visible_page(self):
        src = _read(Path(_me.__file__))
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef)
                  and n.name == "_stamp_source_provenance")
        body = ast.unparse(ast.Module(
            body=[n for n in fn.body
                  if not (isinstance(n, ast.Expr)
                          and isinstance(n.value, ast.Constant)
                          and isinstance(n.value.value, str))],
            type_ignores=[]))
        self.assertIn("core_properties", body)
        for visible in ("add_paragraph", "add_heading", "add_run"):
            with self.subTest(visible=visible):
                self.assertNotIn(visible, body)

    def test_every_builder_stamps(self):
        src = _read(Path(_me.__file__))
        self.assertEqual(src.count("_stamp_source_provenance(doc, req)"), 4)


# ── Folded-in Commit 2 integrity ────────────────────────────────────────

class BindIsOneTransaction(_Base):

    def test_validation_and_write_share_the_lock(self):
        """A turn deleted between validation and the write has already
        fired migration 0048's clearing trigger, so the bind would leave
        ids the trigger will never come back for."""
        src = _read(Path(_db.__file__))
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef)
                  and n.name == "story_candidate_bind_turn_rows")
        body = ast.unparse(ast.Module(
            body=[n for n in fn.body
                  if not (isinstance(n, ast.Expr)
                          and isinstance(n.value, ast.Constant)
                          and isinstance(n.value.value, str))],
            type_ignores=[]))
        begin = body.index("BEGIN IMMEDIATE")
        self.assertLess(begin, body.index("FROM story_candidates"))
        self.assertLess(begin, body.index("FROM turns"))
        self.assertLess(begin, body.index("UPDATE story_candidates"))

    def test_every_refusal_releases_the_lock(self):
        src = _read(Path(_db.__file__))
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef)
                  and n.name == "story_candidate_bind_turn_rows")
        handlers = [h for h in ast.walk(fn) if isinstance(h, ast.ExceptHandler)]
        broad = [h for h in handlers
                 if isinstance(h.type, ast.Name) and h.type.id == "Exception"]
        self.assertTrue(broad, "a refusal raised inside the transaction must "
                               "roll back, not only sqlite3.Error")

    def test_a_refusal_leaves_the_database_writable(self):
        """Added after mutation testing.

        Narrowing the handler back to `sqlite3.Error` survived every
        source assertion, because nothing actually triggered a refusal
        inside the open transaction and then tried to write again. A
        refusal that keeps the write lock is a deadlock, not a refusal.
        """
        cid = self._story("A story.")
        con = sqlite3.connect(str(self.db_path))
        u = con.execute("INSERT INTO turns (conv_id, role, content, ts) "
                        "VALUES (?,?,?,?)",
                        (self.conv, "user", "x", "t")).lastrowid
        a = con.execute("INSERT INTO turns (conv_id, role, content, ts) "
                        "VALUES (?,?,?,?)",
                        (self.conv, "assistant", "y", "t")).lastrowid
        con.commit()
        con.close()

        # Swapped roles: refused deep inside the transaction.
        with self.assertRaises(_db.StoryTurnBindRejected):
            _db.story_candidate_bind_turn_rows(
                cid, narrator_id=self.narrator, conversation_id=self.conv,
                user_turn_row_id=a, assistant_turn_row_id=u)

        # The very next write must succeed. Under a leaked lock this
        # blocks until busy_timeout and then raises "database is locked".
        follow_up = self._story("Written after the refusal.")
        self.assertIsNotNone(_db.story_candidate_get(follow_up))
        # And the correct bind still works afterwards.
        _db.story_candidate_bind_turn_rows(
            cid, narrator_id=self.narrator, conversation_id=self.conv,
            user_turn_row_id=u, assistant_turn_row_id=a)
        self.assertEqual(
            _db.story_candidate_get(cid)["source_user_turn_row_id"], u)

    def test_a_deleted_turn_cannot_leave_dangling_provenance(self):
        cid = self._story("A story.")
        con = sqlite3.connect(str(self.db_path))
        u = con.execute("INSERT INTO turns (conv_id, role, content, ts) "
                        "VALUES (?,?,?,?)",
                        (self.conv, "user", "x", "t")).lastrowid
        a = con.execute("INSERT INTO turns (conv_id, role, content, ts) "
                        "VALUES (?,?,?,?)",
                        (self.conv, "assistant", "y", "t")).lastrowid
        con.commit()
        con.close()
        _db.story_candidate_bind_turn_rows(
            cid, narrator_id=self.narrator, conversation_id=self.conv,
            user_turn_row_id=u, assistant_turn_row_id=a)
        con = sqlite3.connect(str(self.db_path))
        con.execute("DELETE FROM turns WHERE id IN (?,?)", (u, a))
        con.commit()
        con.close()
        row = _db.story_candidate_get(cid)
        self.assertIsNone(row["source_user_turn_row_id"])
        self.assertIsNone(row["completed_assistant_turn_row_id"])
        self.assertIsNotNone(row, "the story survives its turn")


class NoDobNarratorsStillSeeTheirStories(_Base):

    def test_the_no_dob_branch_reads_the_independent_lanes(self):
        from api.routers import chronology_accordion as _ca
        src = _read(Path(_ca.__file__))
        i = src.index('"reason": "no_dob"')
        window = src[max(0, i - 2500):i + 900]
        for lane in ("_collect_story_evidence", "_collect_timeline_events",
                     "_collect_trip_days"):
            with self.subTest(lane=lane):
                self.assertIn(lane, window)

    def test_a_no_dob_narrator_still_exposes_unplaced_stories(self):
        from api.routers import chronology_accordion as _ca
        cid = self._story("Told before any birthday was given.")
        self._review(cid, "promoted", source="operator_set")
        payload = _ca.build_chronology_accordion_payload(
            self.narrator, {}, {}, [])
        self.assertEqual(payload.get("reason"), "no_dob")
        self.assertEqual(len(payload.get("story_evidence") or []), 1)
        self.assertEqual(payload["story_evidence"][0]["placement"], "unplaced")

    def test_no_historical_era_is_derived_without_a_dob(self):
        from api.routers import chronology_accordion as _ca
        payload = _ca.build_chronology_accordion_payload(
            self.narrator, {}, {}, [])
        self.assertEqual(payload.get("decades"), [])
        self.assertIsNone(payload.get("birth_year"))


class AnUnavailableLaneIsNeverZero(_Base):

    def test_lane_counts_use_null_for_an_unreadable_lane(self):
        from api.routers import chronology_accordion as _ca
        counts = _ca._lane_counts(
            world=[], personal=[], personal_derived=[], ghost=[],
            timeline_events=_ca._LaneResult([], "unavailable"),
            story_evidence=_ca._LaneResult([], "unavailable"),
            trip_days=_ca._LaneResult([], "read"))
        self.assertIsNone(counts["story_evidence"])
        self.assertIsNone(counts["timeline_events"])
        self.assertEqual(counts["trip_days"], 0,
                         "a lane that WAS read and found nothing is zero")

    def test_the_browser_log_stopped_defaulting_to_zero(self):
        js = _read(_UI / "app.js")
        self.assertIn("function _laneCount(", js)
        self.assertNotIn("lane_counts?.story_evidence ?? 0", js)

    def test_the_travel_document_says_unavailable_instead_of_zero(self):
        """The flag must be DERIVED from the lane status.

        Added after mutation testing: `out.storiesReadable = true` left
        the name in place and satisfied a bare substring check, so the
        panel would have gone back to counting an unread lane while the
        test stayed green.
        """
        js = strip_js_comments(_read(_UI / "travel-doc-lab.js"))
        self.assertIn('(storyLane.status || "read") === "read"', js)
        self.assertIn("out.storiesReadable =", js)
        self.assertNotIn("out.storiesReadable = true", js)
        self.assertIn("unavailable — the reviewed-story lane could not be read",
                      js)


class NarratorSwitchClearsTheSpine(_Base):

    def test_the_spine_and_seed_flag_are_cleared(self):
        js = _read(_UI / "app.js")
        self.assertIn("state.timeline.spine = null;", js)
        self.assertIn("state.timeline.seedReady = false;", js)

    def test_they_are_cleared_in_the_same_switch_block(self):
        js = _read(_UI / "app.js")
        proj = js.index("state.chronologyProjection = null;")
        spine = js.index("state.timeline.spine = null;")
        self.assertLess(abs(spine - proj), 1500)


if __name__ == "__main__":
    unittest.main()
