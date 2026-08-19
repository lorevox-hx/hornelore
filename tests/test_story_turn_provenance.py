"""A preserved story knows which committed turn it came from.

WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01, Commit 1 (2026-08-19).

── THE GAP THIS CLOSES, MEASURED ───────────────────────────────────────

Before this commit, `story_candidates.turn_id` held the CLIENT's turn id
and was annotated `-- existing transcript turn FK`. It is not one: the
`turns` table has no `turn_id` column, only an autoincrement `id`. On the
live database: 22 of 75 candidates had it NULL or empty, and 0 of 75
joined to anything.

Meanwhile `turn_extraction_results` already held real extraction output,
narrator-scoped and keyed on `turnrow:<turns.id>`. The two halves were
never connected: the 6 sessions holding extraction results contained 0
story candidates, and 0 candidates joined a result by any key. In 75
captures and 7 extractions they had never met.

── WHAT THESE TESTS PROTECT ────────────────────────────────────────────

Linking is PROVENANCE. The dangerous failure is not an absent link -- an
unlinked story is merely unlinked -- it is a WRONG one: attaching one
narrator's evidence to another, or letting a link quietly promote
unreviewed machine output into a life story. So most of what follows
tests refusals.

Run with:

    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_story_turn_provenance
"""
from __future__ import annotations

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
from api.services.story_projection import _clip_to_boundary  # noqa: E402


class _Base(unittest.TestCase):
    def setUp(self):
        fd = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        fd.close()
        self.db_path = Path(fd.name)
        self._orig = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()
        self.narrator = str(uuid.uuid4())
        self.other = str(uuid.uuid4())
        self.conv = "conv-" + uuid.uuid4().hex[:8]
        con = sqlite3.connect(str(self.db_path))
        for pid, name in ((self.narrator, "Story Narrator"),
                          (self.other, "Other Narrator")):
            con.execute(
                "INSERT INTO people (id, display_name, created_at, updated_at) "
                "VALUES (?,?,?,?)", (pid, name, "2026-08-19", "2026-08-19"))
        con.execute(
            "INSERT INTO sessions (conv_id, updated_at) VALUES (?,?)",
            (self.conv, "2026-08-19"))
        con.commit()
        con.close()

    def tearDown(self):
        _db.DB_PATH = self._orig
        try:
            self.db_path.unlink()
        except OSError:
            pass

    # ── fixtures ────────────────────────────────────────────────────────
    def _turn(self, role, content="words", conv=None):
        con = sqlite3.connect(str(self.db_path))
        cur = con.execute(
            "INSERT INTO turns (conv_id, role, content, ts) VALUES (?,?,?,?)",
            (conv or self.conv, role, content, "2026-08-19T00:00:00"))
        rid = cur.lastrowid
        con.commit()
        con.close()
        return rid

    def _completed_turn(self, conv=None):
        """The two rows one completed turn commits, narrator's first."""
        return (self._turn("user", "My grandmother came up every summer", conv),
                self._turn("assistant", "What do you remember of her?", conv))

    def _candidate(self, narrator=None, conv=None):
        cid = str(uuid.uuid4())
        _db.story_candidate_insert(
            cid,
            narrator_id=narrator or self.narrator,
            transcript="My grandmother came up from Corpus Christi every summer.",
            trigger_reason="borderline_scene_anchor",
            scene_anchor_count=3,
            session_id=conv or self.conv,
            conversation_id=conv or self.conv,
            turn_id=None,
        )
        return cid

    def _bind(self, cid, user_row, asst_row, narrator=None, conv=None):
        return _db.story_candidate_bind_turn_rows(
            cid,
            narrator_id=narrator or self.narrator,
            conversation_id=conv or self.conv,
            user_turn_row_id=user_row,
            assistant_turn_row_id=asst_row,
        )

    def _row(self, cid):
        return _db.story_candidate_get(cid)


# ── The link itself ─────────────────────────────────────────────────────

class TurnProvenanceIsRecorded(_Base):

    def test_both_committed_rows_are_stored(self):
        cid = self._candidate()
        user_row, asst_row = self._completed_turn()
        out = self._bind(cid, user_row, asst_row)

        self.assertEqual(out["source_user_turn_row_id"], user_row)
        self.assertEqual(out["completed_assistant_turn_row_id"], asst_row)
        row = self._row(cid)
        self.assertEqual(row["source_user_turn_row_id"], user_row)
        self.assertEqual(row["completed_assistant_turn_row_id"], asst_row)

    def test_the_two_identities_are_kept_apart(self):
        """The story came from the narrator's row; extraction keys on Lori's.

        Storing one and deriving the other -- even as "the other one, minus
        one" -- would be right today and wrong the first time a floor-buffer
        turn, a retry or any future writer lands between them.
        """
        cid = self._candidate()
        # A floor-buffer turn commits BETWEEN this pair, so the two rows of
        # the real completed turn are not adjacent.
        user_row = self._turn("user", "the narrator's words")
        self._turn("assistant", "I'm listening.")          # floor buffer
        self._turn("user", "a buffered fragment")          # floor buffer
        asst_row = self._turn("assistant", "the completed reply")

        self._bind(cid, user_row, asst_row)
        row = self._row(cid)
        self.assertEqual(row["source_user_turn_row_id"], user_row)
        self.assertEqual(row["completed_assistant_turn_row_id"], asst_row)
        self.assertNotEqual(
            row["completed_assistant_turn_row_id"] - 1,
            row["source_user_turn_row_id"],
            "adjacency is an artefact of insert order, never a contract")

    def test_the_client_turn_id_is_not_the_durable_link(self):
        """It may be absent, and it cannot join `turns` at all."""
        cid = self._candidate()
        self.assertIsNone(self._row(cid)["turn_id"])
        user_row, asst_row = self._completed_turn()
        self._bind(cid, user_row, asst_row)
        self.assertIsNotNone(self._row(cid)["source_user_turn_row_id"])

        con = sqlite3.connect(str(self.db_path))
        cols = {r[1] for r in con.execute("PRAGMA table_info(turns)")}
        con.close()
        self.assertNotIn("turn_id", cols)

    def test_many_candidates_may_share_one_turn(self):
        """No uniqueness constraint: one answer can carry several stories.

        A constraint here would start REFUSING captures, and preservation
        may never refuse.
        """
        user_row, asst_row = self._completed_turn()
        first, second = self._candidate(), self._candidate()
        self._bind(first, user_row, asst_row)
        self._bind(second, user_row, asst_row)
        for cid in (first, second):
            self.assertEqual(
                self._row(cid)["completed_assistant_turn_row_id"], asst_row)


# ── Refusals: the half that protects narrators ──────────────────────────

class TheBindRefusesRatherThanGuess(_Base):

    def _rejects(self, reason_fragment, **kw):
        with self.assertRaises(_db.StoryTurnBindRejected) as ctx:
            self._bind(**kw)
        self.assertIn(reason_fragment, ctx.exception.reason)
        return ctx.exception

    def test_another_narrators_candidate_is_refused(self):
        """The failure worth making impossible: one narrator's evidence
        attached to another's life."""
        cid = self._candidate(narrator=self.other)
        user_row, asst_row = self._completed_turn()
        self._rejects("narrator_mismatch",
                      cid=cid, user_row=user_row, asst_row=asst_row)
        row = self._row(cid)
        self.assertIsNone(row["source_user_turn_row_id"])
        self.assertIsNone(row["completed_assistant_turn_row_id"])

    def test_a_turn_from_another_conversation_is_refused(self):
        other_conv = "conv-" + uuid.uuid4().hex[:8]
        con = sqlite3.connect(str(self.db_path))
        con.execute("INSERT INTO sessions (conv_id, updated_at) VALUES (?,?)",
                    (other_conv, "2026-08-19"))
        con.commit()
        con.close()
        cid = self._candidate()
        user_row, asst_row = self._completed_turn(conv=other_conv)
        self._rejects("conversation_mismatch",
                      cid=cid, user_row=user_row, asst_row=asst_row)

    def test_a_candidate_from_another_conversation_is_refused(self):
        other_conv = "conv-" + uuid.uuid4().hex[:8]
        cid = self._candidate(conv=other_conv)
        user_row, asst_row = self._completed_turn()
        self._rejects("candidate_conversation_mismatch",
                      cid=cid, user_row=user_row, asst_row=asst_row)

    def test_swapped_roles_are_refused(self):
        """Otherwise the story claims to come from Lori's sentence.

        This is silent and permanent: both ids are real, both rows exist,
        both are in the right conversation. Only the roles disagree.
        """
        cid = self._candidate()
        user_row, asst_row = self._completed_turn()
        self._rejects("unexpected_role",
                      cid=cid, user_row=asst_row, asst_row=user_row)
        self.assertIsNone(self._row(cid)["source_user_turn_row_id"])

    def test_identical_row_ids_are_refused(self):
        cid = self._candidate()
        user_row, _ = self._completed_turn()
        self._rejects("turn_rows_identical",
                      cid=cid, user_row=user_row, asst_row=user_row)

    def test_a_missing_turn_row_is_refused(self):
        cid = self._candidate()
        user_row, asst_row = self._completed_turn()
        self._rejects("not_found",
                      cid=cid, user_row=user_row, asst_row=asst_row + 9999)

    def test_an_unknown_candidate_is_refused(self):
        user_row, asst_row = self._completed_turn()
        self._rejects("candidate_not_found",
                      cid=str(uuid.uuid4()), user_row=user_row, asst_row=asst_row)

    def test_missing_or_junk_ids_are_refused(self):
        cid = self._candidate()
        user_row, asst_row = self._completed_turn()
        for bad in (None, "", "abc", 0, -1):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(_db.StoryTurnBindRejected):
                    self._bind(cid, bad, asst_row)

    def test_a_refusal_writes_nothing_at_all(self):
        """Compared whole-row, so a partial write cannot hide."""
        cid = self._candidate()
        before = dict(self._row(cid))
        user_row, asst_row = self._completed_turn()
        with self.assertRaises(_db.StoryTurnBindRejected):
            self._bind(cid, asst_row, user_row)  # swapped
        self.assertEqual(dict(self._row(cid)), before)


# ── Linking must not become approving ───────────────────────────────────

class LinkingIsProvenanceNotApproval(_Base):

    def test_review_and_placement_are_untouched_by_a_bind(self):
        """Knowing where a story came from says nothing about its truth."""
        cid = self._candidate()
        before = dict(self._row(cid))
        user_row, asst_row = self._completed_turn()
        self._bind(cid, user_row, asst_row)
        after = dict(self._row(cid))

        for field in ("review_status", "placement_source", "era_candidates",
                      "estimated_year_low", "estimated_year_high",
                      "confidence", "extracted_fields", "extraction_status",
                      "reviewed_by", "reviewed_at", "review_version"):
            with self.subTest(field=field):
                self.assertEqual(after[field], before[field])
        self.assertEqual(after["review_status"], "unreviewed")

    def test_a_linked_story_is_still_not_memoir_eligible(self):
        cid = self._candidate()
        user_row, asst_row = self._completed_turn()
        self._bind(cid, user_row, asst_row)
        self.assertEqual(_db.story_candidate_list_for_memoir(self.narrator), [])

    def test_the_writer_touches_only_the_two_provenance_columns(self):
        """Source-level, because the regression is a one-line addition."""
        import ast
        src = Path(_db.__file__).read_text(encoding="utf-8")
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef)
                  and n.name == "story_candidate_bind_turn_rows")
        body = ast.unparse(ast.Module(
            body=[n for n in fn.body
                  if not (isinstance(n, ast.Expr)
                          and isinstance(n.value, ast.Constant)
                          and isinstance(n.value.value, str))],
            type_ignores=[]))
        self.assertIn("UPDATE story_candidates", body)
        for forbidden in ("review_status", "placement_source", "era_candidates",
                          "extracted_fields", "extraction_status", "confidence"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, body)


# ── The extraction join ─────────────────────────────────────────────────

class ExtractionResultIsJoinedNotMerged(_Base):

    def _store_result(self, asst_row, narrator=None, items=None):
        return _db.turn_extraction_result_store(
            narrator_id=narrator or self.narrator,
            turn_key=_db.turn_extraction_key_for_row(asst_row),
            turn_id="client-" + uuid.uuid4().hex[:6],
            session_id=self.conv,
            status="succeeded",
            method="llm",
            items=items if items is not None else [
                {"fieldPath": "grandparents.firstName", "value": "Elena"}],
            clarification_required=[],
            ledger_id=None,
        )

    def test_the_result_is_found_through_the_assistant_row(self):
        cid = self._candidate()
        user_row, asst_row = self._completed_turn()
        self._bind(cid, user_row, asst_row)
        self._store_result(asst_row)

        got = _db.story_candidate_extraction_result(self._row(cid))
        self.assertIsNotNone(got)
        self.assertEqual(got["items"][0]["value"], "Elena")

    def test_it_is_not_found_through_the_user_row(self):
        """The join key is Lori's row. Using the narrator's would silently
        find nothing, or worse, find a neighbouring turn's evidence."""
        cid = self._candidate()
        user_row, asst_row = self._completed_turn()
        self._bind(cid, user_row, asst_row)
        self._store_result(user_row)   # stored against the WRONG row
        self.assertIsNone(_db.story_candidate_extraction_result(self._row(cid)))

    def test_another_narrators_result_is_never_returned(self):
        cid = self._candidate()
        user_row, asst_row = self._completed_turn()
        self._bind(cid, user_row, asst_row)
        self._store_result(asst_row, narrator=self.other)
        self.assertIsNone(_db.story_candidate_extraction_result(self._row(cid)))

    def test_an_unlinked_story_looks_up_nothing(self):
        cid = self._candidate()
        self.assertIsNone(_db.story_candidate_extraction_result(self._row(cid)))

    def test_a_linked_story_with_no_extraction_returns_none(self):
        """Missing-result is a normal outcome, not an error."""
        cid = self._candidate()
        user_row, asst_row = self._completed_turn()
        self._bind(cid, user_row, asst_row)
        self.assertIsNone(_db.story_candidate_extraction_result(self._row(cid)))

    def test_the_join_copies_nothing_into_the_candidate(self):
        """Extraction output stays evidence. Merging it here would put
        unreviewed machine output into a life story."""
        cid = self._candidate()
        user_row, asst_row = self._completed_turn()
        self._bind(cid, user_row, asst_row)
        self._store_result(asst_row)
        before = dict(self._row(cid))
        _db.story_candidate_extraction_result(self._row(cid))
        after = dict(self._row(cid))
        self.assertEqual(after, before)
        self.assertEqual(after["extracted_fields"], {})
        self.assertEqual(after["extraction_status"], "pending")
        self.assertEqual(after["review_status"], "unreviewed")


# ── Deletion residue ────────────────────────────────────────────────────

class DeletingANarratorLeavesNoProvenance(_Base):

    def test_hard_delete_removes_the_linked_story_and_its_evidence(self):
        cid = self._candidate()
        user_row, asst_row = self._completed_turn()
        self._bind(cid, user_row, asst_row)
        _db.turn_extraction_result_store(
            narrator_id=self.narrator,
            turn_key=_db.turn_extraction_key_for_row(asst_row),
            turn_id="c1", session_id=self.conv, status="succeeded",
            method="llm", items=[{"fieldPath": "x", "value": "y"}],
            clarification_required=[], ledger_id=None)

        _db.hard_delete_person(self.narrator)

        con = sqlite3.connect(str(self.db_path))
        try:
            left = con.execute(
                "SELECT COUNT(*) FROM story_candidates WHERE narrator_id=?",
                (self.narrator,)).fetchone()[0]
            results = con.execute(
                "SELECT COUNT(*) FROM turn_extraction_results WHERE narrator_id=?",
                (self.narrator,)).fetchone()[0]
        finally:
            con.close()
        self.assertEqual(left, 0)
        self.assertEqual(results, 0)

    def test_the_other_narrator_is_untouched(self):
        mine = self._candidate()
        theirs = self._candidate(narrator=self.other)
        user_row, asst_row = self._completed_turn()
        self._bind(mine, user_row, asst_row)
        _db.hard_delete_person(self.narrator)
        self.assertIsNotNone(_db.story_candidate_get(theirs))


# ── The clipped excerpt ─────────────────────────────────────────────────

class ExcerptsEndCleanly(_Base):
    """Observed live 2026-08-19: an approved story was read back to the
    narrator ending "...and about the little house her own mother" -- a
    hard slice at 240 characters. The bound was right; the cut was not."""

    LIVE = ("My grandmother Elena came up from Corpus Christi every summer "
            "after the war, and she would sit with me on the front porch "
            "shelling peas while the evening cooled off. She told me about "
            "the crossing, and about the little house her own mother kept, "
            "and she always smelled faintly of rosewater.")

    def test_the_live_excerpt_now_ends_on_a_sentence(self):
        out = _clip_to_boundary(self.LIVE, 240)
        self.assertTrue(out.endswith("cooled off."), out[-40:])
        self.assertNotIn("…", out, "a complete sentence is not a truncation")

    def test_the_character_bound_is_never_exceeded(self):
        for limit in (20, 40, 80, 120, 240, 1000):
            with self.subTest(limit=limit):
                self.assertLessEqual(len(_clip_to_boundary(self.LIVE, limit)),
                                     limit)

    def test_a_word_is_never_cut_in_half(self):
        for limit in range(30, 260, 7):
            out = _clip_to_boundary(self.LIVE, limit)
            if not out.endswith("…"):
                continue
            tail = out[:-1].rstrip()
            with self.subTest(limit=limit):
                # Whatever survives must be a prefix of the original ending
                # at a word break. Trailing punctuation is deliberately
                # stripped before the ellipsis ("porch, …" reads worse than
                # "porch…"), so the next original character may be that
                # punctuation rather than a space.
                self.assertTrue(
                    self.LIVE.startswith(tail),
                    f"{tail[-30:]!r} is not a clean prefix")
                nxt = self.LIVE[len(tail):len(tail) + 1]
                self.assertIn(nxt, (" ", "", ",", ";", ":", "-", "—"),
                              f"cut mid-word at {limit}")

    def test_a_truncation_says_so(self):
        out = _clip_to_boundary(self.LIVE, 120)
        self.assertTrue(out.endswith("…"))

    def test_short_text_is_returned_whole_and_unmarked(self):
        self.assertEqual(_clip_to_boundary("Short one.", 240), "Short one.")

    def test_one_enormous_token_still_respects_the_bound(self):
        out = _clip_to_boundary("a" * 300, 240)
        self.assertEqual(len(out), 240)
        self.assertTrue(out.endswith("…"))

    def test_empty_and_degenerate_inputs(self):
        self.assertEqual(_clip_to_boundary("", 240), "")
        self.assertEqual(_clip_to_boundary("anything", 0), "")

    def test_the_grounding_context_actually_uses_the_boundary_clip(self):
        """Added after mutation testing.

        Every test above exercised `_clip_to_boundary` directly, so
        reverting `grounding_context` to a raw `excerpt[:max_chars]` left
        the suite GREEN -- the helper was proven correct and proven
        unused, which is the same as untested. This drives the real
        production read.
        """
        from api.services import story_projection as _sp

        cid = self._candidate()
        con = sqlite3.connect(str(self.db_path))
        con.execute("UPDATE story_candidates SET transcript=? WHERE id=?",
                    (self.LIVE, cid))
        con.commit()
        con.close()
        _db.story_candidate_review_apply(
            cid, narrator_id=self.narrator, expected_version=1,
            review_status="promoted", reviewed_by="test")

        ctx = _sp.grounding_context(self.narrator, max_chars=240)
        self.assertTrue(ctx["available"])
        text = ctx["approved"][0]["text"]
        self.assertLessEqual(len(text), 240)
        self.assertTrue(text.endswith("cooled off."),
                        f"grounding_context cut mid-sentence: {text[-40:]!r}")


if __name__ == "__main__":
    unittest.main()
