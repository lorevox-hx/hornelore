"""WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 Phase 3, Commit A.

Server-authoritative story review, and ONE canonical story projection.

Before Phase 3 the write primitive existed (`story_candidate_update_review`)
with zero production callers, no version check, no narrator check and no
row-existence check -- a bad id silently updated nothing, and two operators
silently overwrote each other. Four separate modules each interpreted
`review_status` for themselves, and the one interpretation that mattered
most, Lori's, did not exist at all.

pytest is not installed in this repo. Run with:

    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_story_review_authority
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
from api.services import story_projection  # noqa: E402

_MIGRATION = _SERVER_CODE / "db" / "migrations" / "0046_story_review_authority.sql"


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
        con = sqlite3.connect(str(self.db_path))
        for pid, name in ((self.narrator, "Story Narrator"), (self.other, "Other Narrator")):
            con.execute(
                "INSERT INTO people (id, display_name, created_at, updated_at) "
                "VALUES (?,?,?,?)", (pid, name, "2026-08-17", "2026-08-17"))
        con.commit()
        con.close()

    def tearDown(self):
        _db.DB_PATH = self._orig
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def _story(self, narrator=None, transcript="I remember the kitchen table.",
               **kw):
        cid = str(uuid.uuid4())
        _db.story_candidate_insert(
            cid, narrator or self.narrator, transcript,
            trigger_reason=kw.pop("trigger_reason", "full_threshold"),
            **kw,
        )
        return cid

    def _row(self, cid):
        return _db.story_candidate_get(cid)


class MigrationShape(_Base):
    def test_the_three_columns_exist_with_honest_defaults(self):
        cid = self._story()
        row = self._row(cid)
        self.assertEqual(row["placement_source"], "unknown")
        self.assertEqual(row["review_version"], 1)

    def test_placement_source_is_never_inferred_from_confidence(self):
        # THE RULE. A high-confidence capture is not a stated placement:
        # confidence is set by the trigger heuristic and says nothing
        # about who decided when the story happened.
        cid = self._story(confidence="high")
        self.assertEqual(self._row(cid)["placement_source"], "unknown")

    def test_the_migration_text_does_not_read_confidence(self):
        body = "\n".join(
            line.split("--", 1)[0] for line in
            _MIGRATION.read_text(encoding="utf-8").splitlines()
            if not line.strip().startswith("--")
        )
        self.assertIn("UPDATE story_candidates", body)   # stripper not vacuous
        self.assertNotIn("confidence", body)
        self.assertNotIn("estimated_year_low", body)


class AtomicReviewContract(_Base):
    def test_a_review_applies_and_bumps_the_version(self):
        cid = self._story()
        out = _db.story_candidate_review_apply(
            cid, self.narrator, 1, review_status="promoted", reviewed_by="op")
        self.assertEqual(out["review_status"], "promoted")
        self.assertEqual(out["review_version"], 2)
        self.assertTrue(out["reviewed_at"])
        self.assertTrue(out["updated_at"])

    def test_a_stale_version_is_refused_and_writes_nothing(self):
        cid = self._story()
        _db.story_candidate_review_apply(cid, self.narrator, 1, review_status="in_review")
        before = self._row(cid)
        with self.assertRaises(_db.StoryReviewConflict) as ctx:
            _db.story_candidate_review_apply(
                cid, self.narrator, 1, review_status="discarded")
        self.assertEqual(ctx.exception.expected, 1)
        self.assertEqual(ctx.exception.actual, 2)
        self.assertEqual(self._row(cid), before)

    def test_the_conflict_carries_the_current_record(self):
        # So the UI can show what changed WITHOUT discarding the edit the
        # operator just typed.
        cid = self._story()
        _db.story_candidate_review_apply(cid, self.narrator, 1, review_notes="first")
        with self.assertRaises(_db.StoryReviewConflict) as ctx:
            _db.story_candidate_review_apply(cid, self.narrator, 1, review_notes="second")
        self.assertEqual(ctx.exception.current["review_notes"], "first")

    def test_another_narrators_candidate_is_never_touched(self):
        cid = self._story(narrator=self.other)
        before = self._row(cid)
        with self.assertRaises(_db.StoryCandidateNotFound):
            _db.story_candidate_review_apply(
                cid, self.narrator, 1, review_status="promoted")
        self.assertEqual(self._row(cid), before)

    def test_an_unknown_candidate_is_not_found(self):
        with self.assertRaises(_db.StoryCandidateNotFound):
            _db.story_candidate_review_apply(
                str(uuid.uuid4()), self.narrator, 1, review_status="promoted")

    def test_the_preserved_transcript_is_never_edited(self):
        text = "The kitchen table had a burn mark from my father's cigarette."
        cid = self._story(transcript=text)
        for status in ("in_review", "promoted", "memoir_only", "discarded"):
            _db.story_candidate_review_apply(
                cid, self.narrator, self._row(cid)["review_version"],
                review_status=status, review_notes="x" * 50)
        self.assertEqual(self._row(cid)["transcript"], text)

    def test_review_cannot_touch_extraction(self):
        cid = self._story()
        _db.story_candidate_update_extraction(
            cid, extraction_status="complete", extracted_fields={"a": "b"})
        _db.story_candidate_review_apply(
            cid, self.narrator, 1, review_status="promoted")
        row = self._row(cid)
        self.assertEqual(row["extraction_status"], "complete")
        self.assertEqual(row["extracted_fields"], {"a": "b"})

    def test_extraction_cannot_approve_a_story(self):
        # The other direction, and the one that matters: approval is a
        # human act. Extraction writes its own columns and moves nothing
        # about review.
        cid = self._story()
        _db.story_candidate_update_extraction(cid, extraction_status="complete")
        row = self._row(cid)
        self.assertEqual(row["review_status"], "unreviewed")
        self.assertEqual(row["review_version"], 1)

    def test_omitted_fields_are_left_alone(self):
        # The accessor this replaces wrote review_notes unconditionally,
        # so a status change silently erased the reviewer's notes.
        cid = self._story()
        _db.story_candidate_review_apply(
            cid, self.narrator, 1, review_notes="keep me", reviewed_by="op")
        _db.story_candidate_review_apply(
            cid, self.narrator, 2, review_status="promoted")
        row = self._row(cid)
        self.assertEqual(row["review_notes"], "keep me")
        self.assertEqual(row["reviewed_by"], "op")

    def test_a_year_range_can_be_taken_back_off(self):
        """REPOINTED 2026-08-19. The final placement state is now
        validated inside the review transaction, so a `placement_source`
        with no era -- and an era with no source -- are both refused
        however the request is shaped. These tests built exactly those
        states, which was legitimate under the old permissive model and
        is the incoherence the rule now prevents.

        Each keeps the property it was really about, expressed as a
        coherent placement.
        """
        cid = self._story()
        _db.story_candidate_review_apply(
            cid, self.narrator, 1, estimated_year_low=1962,
            estimated_year_high=1964, placement_source="operator_set",
            era_candidates=["coming_of_age"])
        # Clearing the years alone keeps the placement coherent: the era
        # and its source both survive.
        _db.story_candidate_review_apply(
            cid, self.narrator, 2, clear_year_range=True)
        row = self._row(cid)
        self.assertIsNone(row["estimated_year_low"])
        self.assertIsNone(row["estimated_year_high"])
        self.assertEqual(row["placement_source"], "operator_set")

    def test_invalid_values_are_refused(self):
        cid = self._story()
        for kw in ({"review_status": "approved"},        # not a db status
                   {"placement_source": "guessed"},
                   {"confidence": "certain"}):
            with self.subTest(kw=kw):
                with self.assertRaises(ValueError):
                    _db.story_candidate_review_apply(cid, self.narrator, 1, **kw)

    def test_the_stale_write_is_refused_by_two_independent_guards(self):
        # Structural, and it exists because a mutation SURVIVED: deleting
        # the compare in the SELECT still refused the write, because the
        # UPDATE's own `AND review_version=?` matched no row and the
        # rowcount check caught it. Defence in depth worked -- but a
        # behavioural test alone could not tell me which guard was doing
        # the work, so a later edit could remove one and look fine.
        import inspect
        src = inspect.getsource(_db.story_candidate_review_apply)
        self.assertIn("if current_version != expected:", src)
        self.assertIn("AND review_version=?", src)
        self.assertIn("if cur.rowcount != 1:", src)
        # And the write lock is taken before the read, or the compare
        # could be interleaved by a second writer.
        self.assertLess(src.index("BEGIN IMMEDIATE"), src.index("SELECT * FROM story_candidates"))

    def test_the_version_moves_even_for_a_note_only_edit(self):
        # Otherwise a second operator's stale save would be accepted
        # because nothing they could observe had changed.
        cid = self._story()
        _db.story_candidate_review_apply(cid, self.narrator, 1, review_notes="n")
        self.assertEqual(self._row(cid)["review_version"], 2)


class CanonicalPlacementValidation(_Base):
    """Added 2026-08-17 after review.

    The PATCH route accepted arbitrary eras, reversed year ranges and
    misspelled era ids. An operator typo produced a story the SERVER
    treated as PLACED and that appeared in NO Life Map era -- silently
    placed and invisible, which is worse than unplaced, because unplaced at
    least shows up in the unplaced group where somebody can fix it.
    """

    def test_the_canonical_eras_are_the_six_plus_today(self):
        from api.lv_eras import LV_ERAS
        ids = [e["era_id"] for e in LV_ERAS]
        self.assertEqual(len(ids), 7)
        self.assertIn("today", ids)
        self.assertEqual(story_projection.canonical_eras(ids), ids)

    def test_a_misspelled_era_is_refused_not_dropped(self):
        # Dropping it silently would leave the operator believing they had
        # placed the story.
        with self.assertRaises(story_projection.PlacementRejected):
            story_projection.canonical_eras(["buidling_years"])

    def test_a_year_is_never_accepted_as_an_era(self):
        with self.assertRaises(story_projection.PlacementRejected):
            story_projection.canonical_eras(["1962"])

    def test_legacy_era_keys_still_canonicalize(self):
        self.assertEqual(story_projection.canonical_eras(["midlife"]),
                         ["building_years"])

    def test_duplicates_collapse(self):
        self.assertEqual(
            story_projection.canonical_eras(["adolescence", "adolescence"]),
            ["adolescence"])

    def test_clearing_a_placement_takes_the_era_back_off(self):
        cid = self._story()
        _db.story_candidate_review_apply(
            cid, self.narrator, 1, era_candidates=["building_years"],
            estimated_year_low=1962, estimated_year_high=1964,
            placement_source="operator_set")
        placed = story_projection.project_stories(self.narrator).items[0]
        self.assertEqual(placed["placement"], "operator_set")

        _db.story_candidate_review_apply(
            cid, self.narrator, 2, clear_eras=True, clear_year_range=True,
            placement_source="unknown")
        row = self._row(cid)
        self.assertEqual(row["era_candidates"], [])
        self.assertIsNone(row["estimated_year_low"])
        self.assertEqual(row["placement_source"], "unknown")
        cleared = story_projection.project_stories(self.narrator).items[0]
        self.assertEqual(cleared["placement"], "unplaced")
        self.assertIsNone(cleared["era"])


class ListingAndCounts(_Base):
    def test_a_reviewed_story_does_not_vanish_from_the_operator(self):
        # The Phase 1B accessor filtered to `unreviewed`, so acting on a
        # candidate removed it from the only list that could show it.
        cid = self._story()
        _db.story_candidate_review_apply(cid, self.narrator, 1, review_status="promoted")
        self.assertEqual(_db.story_candidate_list_unreviewed(narrator_id=self.narrator), [])
        rows = _db.story_candidate_list_for_review(self.narrator)
        self.assertEqual([r["id"] for r in rows], [cid])

    def test_status_filtering(self):
        a, b = self._story(), self._story()
        _db.story_candidate_review_apply(a, self.narrator, 1, review_status="promoted")
        promoted = _db.story_candidate_list_for_review(
            self.narrator, statuses=["promoted"])
        self.assertEqual([r["id"] for r in promoted], [a])
        unrev = _db.story_candidate_list_for_review(
            self.narrator, statuses=["unreviewed"])
        self.assertEqual([r["id"] for r in unrev], [b])

    def test_counts_include_every_status_even_at_zero(self):
        self._story()
        counts = _db.story_candidate_status_counts(self.narrator)
        self.assertEqual(counts["unreviewed"], 1)
        for status in ("in_review", "promoted", "discarded", "memoir_only"):
            self.assertIn(status, counts)
            self.assertEqual(counts[status], 0)

    def test_listing_is_narrator_scoped(self):
        self._story(narrator=self.other)
        self.assertEqual(_db.story_candidate_list_for_review(self.narrator), [])


class TheFiveTruths(_Base):
    """The projection's contract, stated as the five things it must never do."""

    def test_provisional_is_never_called_approved(self):
        self._story()
        p = story_projection.project_stories(self.narrator)
        self.assertEqual(p.items[0]["status"], "provisional")
        self.assertEqual(p.counts["approved"], 0)
        self.assertEqual(p.counts["provisional"], 1)

    def test_only_a_human_decision_produces_approved(self):
        cid = self._story()
        _db.story_candidate_review_apply(cid, self.narrator, 1, review_status="promoted")
        p = story_projection.project_stories(self.narrator)
        self.assertEqual(p.items[0]["status"], "approved")

    def test_memoir_only_is_approved_but_carries_no_facts(self):
        cid = self._story()
        _db.story_candidate_review_apply(cid, self.narrator, 1, review_status="memoir_only")
        item = story_projection.project_stories(self.narrator).items[0]
        self.assertEqual(item["status"], "approved")
        self.assertTrue(item["memoir_eligible"])
        self.assertFalse(item["facts_eligible"])

    def test_unknown_placement_is_not_called_stated(self):
        self._story()
        self.assertEqual(
            story_projection.project_stories(self.narrator).items[0]["placement"],
            "unplaced")

    def test_high_confidence_alone_never_produces_a_placement(self):
        # THE RULE, at the projection rather than only at the column.
        # This test was ADDED after a mutation survived: making
        # `confidence == "high"` yield `narrator_stated` passed the whole
        # suite, because every other story here is captured at the default
        # confidence and the migration-level test only read the column.
        # Confidence is set by the capture heuristic; it is not provenance.
        cid = self._story(confidence="high", estimated_year_low=1962)
        item = story_projection.project_stories(self.narrator).items[0]
        self.assertEqual(item["confidence"], "high")
        self.assertEqual(item["placement_source"], "unknown")
        self.assertEqual(item["placement"], "unplaced")
        self.assertEqual(self._row(cid)["placement_source"], "unknown")

    def test_placement_is_reported_from_its_recorded_source(self):
        """NARROWED 2026-08-19 (WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01
        Commit 2). This test asserted:

            _db.story_candidate_review_apply(
                cid, self.narrator, 1, placement_source="narrator_stated",
                estimated_year_low=1962)
            assertEqual(items[0]["placement"], "stated")

        -- a YEAR with no era counting as placed. That was the server's
        definition and the browser's was different: `story-evidence.js`
        files a story under an era or under UNPLACED, so a year-only row
        was `stated` in the review panel's count and `unplaced` on the
        Life Map. One column, two readers, two answers.

        The era is the definition that survives, because it is the one a
        surface can honour: the Life Map is drawn in eras and a year alone
        has nowhere to go. Deriving an era from the year is the
        derivation this lane exists to stop.

        Nothing is lost that was true. `placement_source` still reports
        who supplied it and the year is still on the row -- so this test
        now asserts BOTH halves: the source is reported faithfully, and a
        year without an era is honestly unplaced.
        """
        cid = self._story()
        # A source with no era is now REFUSED outright rather than
        # accepted and reported unplaced -- the state cannot be created,
        # so it cannot be misread. Both halves are asserted.
        with self.assertRaises(ValueError):
            _db.story_candidate_review_apply(
                cid, self.narrator, 1, placement_source="narrator_stated",
                estimated_year_low=1962)
        _db.story_candidate_review_apply(
            cid, self.narrator, 1, placement_source="narrator_stated",
            estimated_year_low=1962, era_candidates=["coming_of_age"])
        item = story_projection.project_stories(self.narrator).items[0]
        self.assertEqual(item["placement_source"], "narrator_stated")
        self.assertEqual(item["year"], 1962)
        self.assertEqual(item["placement"], "stated")

    def test_a_recorded_source_with_an_era_is_reported_as_placed(self):
        """The other half, so the narrowing above did not simply make
        `placement` always read `unplaced`."""
        cid = self._story()
        _db.story_candidate_review_apply(
            cid, self.narrator, 1, placement_source="narrator_stated",
            estimated_year_low=1962, era_candidates=["coming_of_age"])
        item = story_projection.project_stories(self.narrator).items[0]
        self.assertEqual(item["placement"], "stated")
        self.assertEqual(item["era"], "coming_of_age")

    def test_a_recorded_source_with_nothing_to_show_is_still_unplaced(self):
        cid = self._story()
        _db.story_candidate_review_apply(
            cid, self.narrator, 1, placement_source="operator_set",
            estimated_year_low=1962, era_candidates=["coming_of_age"])
        # Clearing the placement removes BOTH the era and the source, so
        # the story returns to genuinely unplaced.
        _db.story_candidate_review_apply(
            cid, self.narrator, 2, clear_eras=True,
            placement_source="unknown")
        self.assertEqual(
            story_projection.project_stories(self.narrator).items[0]["placement"],
            "unplaced")

    def test_unplaced_stories_are_not_forced_into_today(self):
        self._story()
        item = story_projection.project_stories(self.narrator).items[0]
        self.assertIsNone(item["era"])
        self.assertNotEqual(item["era"], "today")
        self.assertEqual(item["placement"], "unplaced")

    def test_discarded_stories_disappear(self):
        keep, drop = self._story(), self._story()
        _db.story_candidate_review_apply(drop, self.narrator, 1, review_status="discarded")
        p = story_projection.project_stories(self.narrator)
        self.assertEqual([i["id"] for i in p.items], [keep])
        self.assertEqual(p.counts["discarded"], 1)

    def test_a_lane_failure_reports_unavailable_not_an_empty_narrator(self):
        con = sqlite3.connect(str(self.db_path))
        con.execute("DROP TABLE story_candidates;")
        con.commit()
        con.close()
        p = story_projection.project_stories(self.narrator)
        self.assertEqual(p.status, "unavailable")
        self.assertEqual(p.items, [])

    def test_a_read_lane_with_no_stories_is_read_not_unavailable(self):
        p = story_projection.project_stories(self.narrator)
        self.assertEqual(p.status, "read")
        self.assertEqual(p.items, [])


class LoriGrounding(_Base):
    def test_only_approved_stories_are_offered_as_established(self):
        approved = self._story(transcript="We moved to Bismarck in the spring.")
        self._story(transcript="There was a dog called Rusty.")
        _db.story_candidate_review_apply(approved, self.narrator, 1, review_status="promoted")
        ctx = story_projection.grounding_context(self.narrator)
        self.assertEqual(len(ctx["approved"]), 1)
        self.assertIn("Bismarck", ctx["approved"][0]["text"])

    def test_provisional_stories_are_counted_but_never_quoted(self):
        self._story(transcript="Something unconfirmed about my aunt.")
        ctx = story_projection.grounding_context(self.narrator)
        self.assertEqual(ctx["approved"], [])
        self.assertEqual(ctx["provisional_count"], 1)
        blob = repr(ctx)
        self.assertNotIn("unconfirmed", blob)

    def test_discarded_stories_never_enter_the_prompt(self):
        cid = self._story(transcript="Retracted account of the fire.")
        _db.story_candidate_review_apply(cid, self.narrator, 1, review_status="discarded")
        ctx = story_projection.grounding_context(self.narrator)
        self.assertNotIn("Retracted", repr(ctx))
        self.assertEqual(ctx["approved"], [])

    def test_the_current_turn_is_not_fed_back_as_history(self):
        text = "I remember the kitchen table."
        cid = self._story(transcript=text)
        _db.story_candidate_review_apply(cid, self.narrator, 1, review_status="promoted")
        ctx = story_projection.grounding_context(self.narrator, exclude_text=text)
        self.assertEqual(ctx["approved"], [])

    def test_grounding_is_bounded(self):
        for i in range(12):
            cid = self._story(transcript=f"Story number {i} " + ("x" * 400))
            _db.story_candidate_review_apply(cid, self.narrator, 1, review_status="promoted")
        ctx = story_projection.grounding_context(self.narrator, max_stories=6, max_chars=100)
        self.assertEqual(len(ctx["approved"]), 6)
        for row in ctx["approved"]:
            self.assertLessEqual(len(row["text"]), 100)

    def test_story_context_cannot_leak_across_narrators(self):
        mine = self._story(transcript="My own story about the river.")
        theirs = self._story(narrator=self.other, transcript="Their story about a barn.")
        _db.story_candidate_review_apply(mine, self.narrator, 1, review_status="promoted")
        _db.story_candidate_review_apply(theirs, self.other, 1, review_status="promoted")
        ctx = story_projection.grounding_context(self.narrator)
        self.assertNotIn("barn", repr(ctx))
        self.assertIn("river", repr(ctx))

    def test_an_unavailable_lane_grounds_nothing(self):
        con = sqlite3.connect(str(self.db_path))
        con.execute("DROP TABLE story_candidates;")
        con.commit()
        con.close()
        ctx = story_projection.grounding_context(self.narrator)
        self.assertFalse(ctx["available"])
        self.assertEqual(ctx["approved"], [])


class OneInterpretationOnly(unittest.TestCase):
    """The duplicated status readings are gone."""

    def test_the_chronology_lane_no_longer_interprets_review_status(self):
        src = (_SERVER_CODE / "api" / "routers" / "chronology_accordion.py").read_text(
            encoding="utf-8")
        body = "\n".join(
            line for line in src.splitlines() if not line.strip().startswith("#"))
        self.assertNotIn("_STORY_STATUS = {", body)
        self.assertNotIn('"promoted": "approved"', body)
        self.assertIn("story_projection.project_stories", body)

    def test_the_projection_never_writes(self):
        src = (_SERVER_CODE / "api" / "services" / "story_projection.py").read_text(
            encoding="utf-8")
        body = "\n".join(
            line for line in src.splitlines() if not line.strip().startswith("#"))
        for forbidden in ("INSERT ", "UPDATE ", "DELETE ", "commit(",
                          "review_apply", "update_review"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, body)

    def test_the_projection_stays_out_of_the_extraction_stack(self):
        src = (_SERVER_CODE / "api" / "services" / "story_projection.py").read_text(
            encoding="utf-8")
        for forbidden in ("routers.extract", "prompt_composer", "llm_api",
                          "chat_ws"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, src)


if __name__ == "__main__":
    unittest.main()
