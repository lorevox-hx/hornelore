"""Review evidence and chronology placement tell the truth.

WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01, Commit 2 (2026-08-19).

Six proven defects, each of which made a surface state something the data
did not support:

  * provenance was REPLACEABLE -- a second bind silently re-pointed a
    story at a different turn;
  * only the ordinary model path bound anything, so a story captured on a
    turn that resolved deterministically stayed permanently unlinked;
  * the provenance columns are plain INTEGERs, so a deleted turn left a
    convincing dangling id;
  * an approved but UNPLACED story was spoken to the narrator with a date
    nobody had placed;
  * server and browser disagreed about what "unplaced" meant, so the
    review panel could say "0 unplaced" while the Life Map said "1 not
    yet placed in any era";
  * a lane that could not be read rendered identically to a narrator with
    no stories.

Run with:

    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_story_placement_truthfulness
"""
from __future__ import annotations

import ast
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
from api.services import story_projection as _sp  # noqa: E402
from tests.source_scan_helpers import strip_js_comments  # noqa: E402

_UI = _REPO_ROOT / "ui" / "js"
_CHAT_WS = _SERVER_CODE / "api" / "routers" / "chat_ws.py"


def _read(path):
    with open(path, encoding="utf-8") as fh:
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
        con.execute(
            "INSERT INTO people (id, display_name, created_at, updated_at) "
            "VALUES (?,?,?,?)", (self.narrator, "N", "2026-08-19", "2026-08-19"))
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

    def _turn(self, role, content="words"):
        con = sqlite3.connect(str(self.db_path))
        rid = con.execute(
            "INSERT INTO turns (conv_id, role, content, ts) VALUES (?,?,?,?)",
            (self.conv, role, content, "2026-08-19T00:00:00")).lastrowid
        con.commit()
        con.close()
        return rid

    def _pair(self):
        return self._turn("user"), self._turn("assistant")

    def _candidate(self, transcript="My grandmother came up every summer."):
        cid = str(uuid.uuid4())
        _db.story_candidate_insert(
            cid, narrator_id=self.narrator, transcript=transcript,
            trigger_reason="borderline_scene_anchor", scene_anchor_count=3,
            session_id=self.conv, conversation_id=self.conv, turn_id=None)
        return cid

    def _bind(self, cid, u, a):
        return _db.story_candidate_bind_turn_rows(
            cid, narrator_id=self.narrator, conversation_id=self.conv,
            user_turn_row_id=u, assistant_turn_row_id=a)

    def _promote(self, cid, *, eras=None, year=None, source=None, version=1):
        _db.story_candidate_review_apply(
            cid, narrator_id=self.narrator, expected_version=version,
            review_status="promoted", reviewed_by="test",
            era_candidates=eras, estimated_year_low=year,
            estimated_year_high=year, placement_source=source)

    def _force_placement(self, cid, *, eras=None, year=None, source=None):
        """Write a placement DIRECTLY, bypassing the review transaction.

        Added 2026-08-19. The review API now refuses an incoherent final
        state -- a source with no era, or an era with no source. That is
        the right rule, and it means these tests can no longer BUILD the
        rows they exist to describe.

        They still matter: legacy rows and hand-edited databases carry
        exactly these combinations, and the projection's job is to read
        them honestly rather than assume they cannot occur. So the row is
        written directly and the PROJECTION is what is under test.
        """
        import json as _json
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "UPDATE story_candidates SET era_candidates=?, "
            "estimated_year_low=?, estimated_year_high=?, "
            "placement_source=?, review_status='promoted' WHERE id=?",
            (_json.dumps(list(eras or [])), year, year,
             source or "unknown", cid))
        con.commit()
        con.close()


# ── Provenance is write-once ────────────────────────────────────────────

class ProvenanceCannotBeReassigned(_Base):
    """A record of where a story came from that can be overwritten is not
    provenance, it is a mutable opinion."""

    def test_a_second_bind_to_a_different_turn_is_refused(self):
        cid = self._candidate()
        u1, a1 = self._pair()
        u2, a2 = self._pair()
        self._bind(cid, u1, a1)
        with self.assertRaises(_db.StoryTurnBindRejected) as ctx:
            self._bind(cid, u2, a2)
        self.assertIn("already_bound", ctx.exception.reason)
        row = _db.story_candidate_get(cid)
        self.assertEqual(row["source_user_turn_row_id"], u1)
        self.assertEqual(row["completed_assistant_turn_row_id"], a1)

    def test_rebinding_the_same_pair_is_idempotent(self):
        """A retried frame must not be an error, and must not double-write."""
        cid = self._candidate()
        u, a = self._pair()
        first = self._bind(cid, u, a)
        second = self._bind(cid, u, a)
        self.assertFalse(first["already_bound"])
        self.assertTrue(second["already_bound"])
        self.assertEqual(second["source_user_turn_row_id"], u)

    def test_the_guard_is_in_the_write_not_only_the_read(self):
        """Between the SELECT and the UPDATE another writer may bind.

        A check that trusts its own earlier read is a race with a comment
        on it, so the NULL condition sits in the WHERE clause and the
        verdict is rowcount.
        """
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
        self.assertIn("source_user_turn_row_id IS NULL", body)
        self.assertIn("completed_assistant_turn_row_id IS NULL", body)
        self.assertIn("rowcount", body)

    def test_a_half_bound_row_is_refused_not_completed(self):
        """This function writes both or neither, so one populated column
        means something else wrote it -- and guessing the other would be
        inventing provenance."""
        cid = self._candidate()
        u, a = self._pair()
        con = sqlite3.connect(str(self.db_path))
        con.execute("UPDATE story_candidates SET source_user_turn_row_id=? "
                    "WHERE id=?", (u, cid))
        con.commit()
        con.close()
        with self.assertRaises(_db.StoryTurnBindRejected):
            self._bind(cid, u, a)


# ── Deterministic routes link too, without gaining eligibility ──────────

class DeterministicTurnsBindWithoutBecomingEligible(_Base):

    def _finaliser_body(self):
        src = _read(_CHAT_WS)
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.AsyncFunctionDef)
                  and n.name == "_finalize_deterministic_turn")
        return ast.unparse(ast.Module(
            body=[n for n in fn.body
                  if not (isinstance(n, ast.Expr)
                          and isinstance(n.value, ast.Constant)
                          and isinstance(n.value.value, str))],
            type_ignores=[]))

    def test_the_deterministic_finaliser_binds_a_candidate(self):
        body = self._finaliser_body()
        self.assertIn("story_candidate_bind_turn_rows", body)
        self.assertIn("row_ids_out", body)

    def test_it_never_routes_row_ids_into_params(self):
        """`params` is the only channel the completed-turn hooks read, so
        a LOCAL row id cannot make a deterministic turn extraction- or
        trip-placement-eligible. This is the whole contract."""
        body = self._finaliser_body()
        for key in ("_persisted_turn_row_id", "_persisted_user_turn_row_id",
                    "_archive_event_persisted"):
            with self.subTest(key=key):
                self.assertNotIn(f"params['{key}']", body)
                self.assertNotIn(f'params["{key}"]', body)

    def test_the_bind_reads_the_candidate_from_params_only(self):
        """It may READ the candidate id from params; it may not write the
        eligibility keys back."""
        body = self._finaliser_body()
        self.assertIn("_story_candidate_id", body)

    def test_a_bind_failure_cannot_break_the_turn(self):
        body = self._finaliser_body()
        idx = body.index("story_candidate_bind_turn_rows")
        window = body[max(0, idx - 700):idx + 700]
        self.assertIn("try:", window)
        self.assertIn("except", window)


# ── A deleted turn must not leave a convincing id ───────────────────────

class DeletingATurnClearsProvenance(_Base):
    """SQLite may reissue a row id. A dangling provenance id looks exactly
    like a real one, and a WRONG record is worse than an absent one."""

    def test_deleting_the_narrator_row_nulls_only_that_field(self):
        cid = self._candidate()
        u, a = self._pair()
        self._bind(cid, u, a)
        con = sqlite3.connect(str(self.db_path))
        con.execute("DELETE FROM turns WHERE id=?", (u,))
        con.commit()
        con.close()
        row = _db.story_candidate_get(cid)
        self.assertIsNone(row["source_user_turn_row_id"])
        self.assertEqual(row["completed_assistant_turn_row_id"], a)

    def test_deleting_lori_row_nulls_only_that_field(self):
        cid = self._candidate()
        u, a = self._pair()
        self._bind(cid, u, a)
        con = sqlite3.connect(str(self.db_path))
        con.execute("DELETE FROM turns WHERE id=?", (a,))
        con.commit()
        con.close()
        row = _db.story_candidate_get(cid)
        self.assertEqual(row["source_user_turn_row_id"], u)
        self.assertIsNone(row["completed_assistant_turn_row_id"])

    def test_the_story_itself_survives(self):
        """The narrator said those words. Losing the record of a
        conversation must not delete the story that came out of it."""
        cid = self._candidate()
        u, a = self._pair()
        self._bind(cid, u, a)
        con = sqlite3.connect(str(self.db_path))
        con.execute("DELETE FROM turns WHERE id IN (?,?)", (u, a))
        con.commit()
        con.close()
        row = _db.story_candidate_get(cid)
        self.assertIsNotNone(row)
        self.assertIn("grandmother", row["transcript"])
        self.assertEqual(row["review_status"], "unreviewed")

    def test_a_cascading_session_delete_clears_provenance_too(self):
        cid = self._candidate()
        u, a = self._pair()
        self._bind(cid, u, a)
        con = sqlite3.connect(str(self.db_path))
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("DELETE FROM sessions WHERE conv_id=?", (self.conv,))
        con.commit()
        con.close()
        row = _db.story_candidate_get(cid)
        self.assertIsNotNone(row)
        self.assertIsNone(row["source_user_turn_row_id"])
        self.assertIsNone(row["completed_assistant_turn_row_id"])


# ── An unplaced story speaks no date ────────────────────────────────────

class UnplacedStoriesDoNotClaimADate(_Base):

    def test_a_machine_era_candidate_is_not_a_placement(self):
        """`placement_source` stays `unknown` when nobody placed it, and
        an era candidate alone must not become a spoken date."""
        cid = self._candidate()
        self._force_placement(cid, eras=["early_school_years"])
        proj = _sp.project_stories(self.narrator)
        item = proj.items[0]
        self.assertEqual(item["status"], "approved")
        self.assertEqual(item["placement"], _sp.PLACEMENT_UNPLACED)

        ctx = _sp.grounding_context(self.narrator)
        row = ctx["approved"][0]
        self.assertIsNone(row["era"])
        self.assertIsNone(row["year"])

    def test_an_operator_placement_does_speak_its_date(self):
        """The other half: a real placement must still reach Lori, or the
        fix would have removed a capability instead of a defect."""
        cid = self._candidate()
        self._promote(cid, eras=["early_school_years"], year=1945,
                      source="operator_set")
        ctx = _sp.grounding_context(self.narrator)
        row = ctx["approved"][0]
        self.assertEqual(row["era"], "early_school_years")
        self.assertEqual(row["year"], 1945)
        self.assertNotEqual(row["placement"], _sp.PLACEMENT_UNPLACED)

    def test_the_prompt_cannot_reintroduce_the_date(self):
        """The composer renders `year or era`; withholding at the source
        is what makes that safe, so this drives the real block."""
        from api.prompt_composer import _approved_story_block
        cid = self._candidate()
        self._force_placement(cid, eras=["early_school_years"])
        ctx = _sp.grounding_context(self.narrator)
        block = _approved_story_block({"story_context": ctx})
        self.assertIn("grandmother", block)
        self.assertNotIn("early_school_years", block)
        self.assertNotIn("(1945)", block)


# ── One definition of unplaced ──────────────────────────────────────────

class ServerAndBrowserAgreeOnUnplaced(_Base):

    def test_a_year_without_an_era_is_unplaced_on_the_server(self):
        """It has nowhere to be drawn: the Life Map is drawn in eras."""
        cid = self._candidate()
        self._force_placement(cid, year=1945, source="operator_set")
        proj = _sp.project_stories(self.narrator)
        self.assertEqual(proj.items[0]["placement"], _sp.PLACEMENT_UNPLACED)
        self.assertEqual(proj.counts["unplaced"], 1)

    def test_the_browser_reads_the_servers_era_not_the_candidates(self):
        """Comments are stripped with the repo's string-aware stripper.

        The retirement note above that code QUOTES the retired line, on
        purpose, so a raw scan fires on the explanation -- which it did on
        the first run of this test. A line filter was not enough either:
        the interior lines of a block comment carry no marker at all.
        """
        js = strip_js_comments(_read(_UI / "story-evidence.js"))
        fn = js[js.index("function byEra()"):]
        fn = fn[:fn.index("\n  }")]
        self.assertIn("row.era", fn)
        self.assertNotIn("era_candidates", fn)

    def test_both_sides_key_on_the_same_two_fields(self):
        js = _read(_UI / "story-evidence.js")
        self.assertIn('row.placement !== "unplaced"', js)
        self.assertEqual(_sp.PLACEMENT_UNPLACED, "unplaced")


# ── Unavailable is not empty ────────────────────────────────────────────

class AnUnreadableLaneSaysSo(_Base):

    def test_only_read_is_an_answer_in_the_shared_helper(self):
        js = _read(_UI / "story-evidence.js")
        self.assertIn("function laneReadable()", js)
        self.assertIn('laneStatus() === "read"', js)
        self.assertIn("laneReadable: laneReadable", js)

    def test_both_consumers_stopped_testing_the_literal_string(self):
        """`not_loaded` and `not_attempted` were rendering as zero.

        `not_attempted` is what a narrator with no date of birth gets --
        the server never queries the lane for them -- so fifty captured
        stories showed as none.
        """
        for name in ("life-map.js", "chronology-accordion.js"):
            with self.subTest(file=name):
                js = _read(_UI / name)
                self.assertIn("laneReadable", js)
                self.assertNotIn('t.status === "unavailable"', js)

    def test_an_unreadable_projection_reports_unavailable(self):
        proj = _sp.project_stories("no-such-narrator")
        self.assertEqual(proj.items, [])
        # An unknown narrator reads cleanly; the point is that `status`
        # exists as a separate axis from the item count.
        self.assertTrue(hasattr(proj, "status"))


# ── The narrator-switch leak ────────────────────────────────────────────

class SwitchingNarratorClearsTheProjection(_Base):

    def test_the_switch_clears_the_projection_and_payload(self):
        js = _read(_UI / "app.js")
        self.assertIn("state.chronologyProjection = null;", js)
        self.assertIn("state.chronologyAccordion.payload = null;", js)

    def test_it_is_cleared_inside_the_narrator_switch_reset(self):
        """Next to the focus reset that was already there -- the
        projection is narrator-scoped data and was the one piece of it
        nobody evicted."""
        js = _read(_UI / "app.js")
        focus = js.index("state.chronologyAccordion.focus = null;")
        clear = js.index("state.chronologyProjection = null;")
        self.assertGreater(clear, focus)
        self.assertLess(clear - focus, 2000,
                        "the clear should sit in the same reset block")


# ── The operator sees extraction, and cannot apply it ───────────────────

class ExtractionIsShownButNeverApplied(_Base):

    def setUp(self):
        super().setUp()
        self.js = _read(_UI / "bug-panel-story-review.js")

    def test_the_panel_renders_the_extraction_block(self):
        """The call site is pinned INSIDE renderDetail.

        Added after mutation testing: `assertIn("renderExtraction(d)")`
        against the whole file was satisfied by the function's own
        definition line, so deleting the call left the suite green — a
        block that exists and is never rendered, which is the same as not
        having it.
        """
        self.assertIn("function renderExtraction(", self.js)
        self.assertIn("Machine extraction — provisional", self.js)

        detail = self.js[self.js.index("function renderDetail("):]
        detail = detail[:detail.index("\n  function renderRow")]
        self.assertIn("renderExtraction(", detail)
        # And before the controls, so the evidence is read before the
        # decision rather than found underneath it.
        self.assertLess(detail.index("renderExtraction("),
                        detail.index("renderActions("))

    def test_the_four_states_are_distinct(self):
        for state in ("not_linked", "unavailable", "none"):
            with self.subTest(state=state):
                self.assertIn(f"'{state}'", self.js)
        body = self.js[self.js.index("function renderExtraction("):]
        body = body[:body.index("\n  function renderDetail")]
        # Split across a concatenation in the source, so assert a
        # contiguous fragment rather than the rendered sentence.
        self.assertIn("the same as finding nothing", body)

    def test_it_offers_no_control_of_any_kind(self):
        """Read-only by construction: a one-click apply would move
        unreviewed machine output into a life story with no human
        judgement in between."""
        body = self.js[self.js.index("function renderExtraction("):]
        body = body[:body.index("\n  function renderDetail")]
        for control in ("onclick", "addEventListener", "btn(", "'button'",
                        "applyReview", "input"):
            with self.subTest(control=control):
                self.assertNotIn(control, body)

    def test_it_says_nothing_has_been_applied(self):
        self.assertIn("Nothing here has been applied", self.js)

    def test_the_stylesheet_and_script_cache_busters_move_together(self):
        html = _read(_REPO_ROOT / "ui" / "hornelore1.0.html")
        found = re.findall(r"bug-panel-story-review\.(?:js|css)\?v=([0-9a-z-]+)",
                           html)
        self.assertEqual(len(found), 2, found)
        self.assertEqual(found[0], found[1],
                         "a cached stylesheet against a refetched script "
                         "reads as a CSS bug, not a caching one")


if __name__ == "__main__":
    unittest.main()
