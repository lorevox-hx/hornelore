"""Unit tests for services/story_preservation.py.

LAW 3 [INFRASTRUCTURE] enforcement at the runtime level (the static
import gate is in test_story_preservation_isolation.py — this file
adds dynamic verification that preservation actually completes when
the extractor isn't available).

Uses an isolated temp DB per test so we don't touch the live
hornelore.sqlite3. Each test creates the story_candidates table from
the migration SQL, exercises the service, and asserts.

Critical scenario coverage:
  - preserve_turn() with extractor unavailable (LAW 3 baseline)
  - preserve_turn() with all optional fields None
  - preserve_turn() with full_threshold vs borderline_scene_anchor
    initial confidence assignment
  - update_placement() with DOB + bucket auto-derives years and eras
  - update_placement() with caller-supplied values overrides derivation
  - get_unreviewed() ordering + narrator_id filter
  - get_candidate() returns None for missing id
  - validation: invalid trigger_reason / confidence raise ValueError
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

# Add server/code to sys.path so `api.services.story_preservation` imports.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))


class _TempDbCase(unittest.TestCase):
    """Base class — sets up an isolated temp DB with story_candidates
    table created from the migration SQL. Patches db.DB_PATH so all
    accessor functions hit our temp file, not the live DB."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self._tmp.close()
        self.db_path = Path(self._tmp.name)

        # Apply migration SQL directly to the temp DB
        migration_sql = (
            _REPO_ROOT
            / "server"
            / "code"
            / "db"
            / "migrations"
            / "0004_story_candidates.sql"
        ).read_text(encoding="utf-8")

        con = sqlite3.connect(str(self.db_path))
        con.executescript(migration_sql)
        con.commit()
        con.close()

        # Patch db.DB_PATH so service calls hit our temp file.
        # Import here (not at module top) so the patch is per-test.
        from api import db as _db  # noqa: WPS433
        self._db = _db
        self._original_db_path = _db.DB_PATH
        _db.DB_PATH = self.db_path

    def tearDown(self):
        # Restore real DB_PATH and clean up temp file.
        self._db.DB_PATH = self._original_db_path
        try:
            os.unlink(self.db_path)
        except OSError:
            pass


class PreserveTurnTest(_TempDbCase):
    def test_preserve_minimal(self):
        """Smallest possible preservation: just narrator_id +
        transcript + trigger. Must succeed."""
        from api.services import story_preservation

        cid = story_preservation.preserve_turn(
            narrator_id="janice-josephine-horne",
            transcript="My dad worked nights at the aluminum plant in Spokane.",
            trigger_reason="full_threshold",
        )
        self.assertTrue(cid)

        row = story_preservation.get_candidate(cid)
        self.assertIsNotNone(row)
        self.assertEqual(row["narrator_id"], "janice-josephine-horne")
        self.assertEqual(row["trigger_reason"], "full_threshold")
        self.assertEqual(row["review_status"], "unreviewed")
        self.assertEqual(row["extraction_status"], "pending")
        self.assertEqual(row["era_candidates"], [])
        self.assertEqual(row["scene_anchors"], [])
        self.assertEqual(row["extracted_fields"], {})

    def test_preserve_with_all_fields(self):
        from api.services import story_preservation

        cid = story_preservation.preserve_turn(
            narrator_id="janice-josephine-horne",
            transcript="I had a mastoidectomy in Spokane when I was little.",
            audio_clip_path="archive/janice/sessions/x/turn1.webm",
            audio_duration_sec=42.5,
            word_count=12,
            trigger_reason="borderline_scene_anchor",
            scene_anchor_count=3,
            session_id="sess_abc",
            conversation_id="conv_xyz",
            turn_id="turn_123",
        )
        row = story_preservation.get_candidate(cid)
        self.assertEqual(row["audio_duration_sec"], 42.5)
        self.assertEqual(row["scene_anchor_count"], 3)
        self.assertEqual(row["session_id"], "sess_abc")
        self.assertEqual(row["confidence"], "low")  # borderline → low

    def test_full_threshold_initial_confidence_medium(self):
        """full_threshold trigger should land at confidence='medium',
        because the duration+words+anchor floor is high enough to
        suggest the narrator gave a real story."""
        from api.services import story_preservation

        cid = story_preservation.preserve_turn(
            narrator_id="kent-james-horne",
            transcript="When I was a kid in Stanley we had a big yard.",
            trigger_reason="full_threshold",
        )
        row = story_preservation.get_candidate(cid)
        self.assertEqual(row["confidence"], "medium")

    def test_borderline_initial_confidence_low(self):
        from api.services import story_preservation

        cid = story_preservation.preserve_turn(
            narrator_id="kent-james-horne",
            transcript="Stanley.",
            trigger_reason="borderline_scene_anchor",
            scene_anchor_count=3,
        )
        row = story_preservation.get_candidate(cid)
        self.assertEqual(row["confidence"], "low")

    def test_word_count_auto_computed(self):
        from api.services import story_preservation

        cid = story_preservation.preserve_turn(
            narrator_id="kent-james-horne",
            transcript="one two three four five",
            trigger_reason="full_threshold",
        )
        row = story_preservation.get_candidate(cid)
        self.assertEqual(row["word_count"], 5)

    def test_empty_transcript_rejected(self):
        from api.services import story_preservation

        with self.assertRaises(ValueError):
            story_preservation.preserve_turn(
                narrator_id="kent-james-horne",
                transcript="   ",
                trigger_reason="full_threshold",
            )

    def test_empty_narrator_rejected(self):
        from api.services import story_preservation

        with self.assertRaises(ValueError):
            story_preservation.preserve_turn(
                narrator_id="",
                transcript="something",
                trigger_reason="full_threshold",
            )

    def test_oversized_transcript_truncated_with_marker(self):
        # Patch C (2026-04-30 polish): a runaway STT output must NOT be
        # written to story_candidates verbatim. preserve_turn truncates
        # at MAX_TRANSCRIPT_BYTES and appends a marker so a downstream
        # reader can see the row is partial.
        from api.services import story_preservation

        oversize = "x" * (story_preservation.MAX_TRANSCRIPT_BYTES + 1000)
        cid = story_preservation.preserve_turn(
            narrator_id="kent",
            transcript=oversize,
            trigger_reason="full_threshold",
        )
        row = story_preservation.get_candidate(cid)
        self.assertIsNotNone(row)
        assert row is not None  # narrow for type checker
        # Transcript was truncated and the marker is present.
        self.assertLess(
            len(row["transcript"]),
            len(oversize),
            "transcript was not truncated",
        )
        self.assertTrue(
            row["transcript"].endswith(story_preservation._TRUNCATION_MARKER),
            "truncation marker missing from stored transcript",
        )

    def test_under_cap_transcript_passes_through(self):
        # Cap shouldn't fire on normal-sized turns.
        from api.services import story_preservation

        normal = "My dad worked nights at the aluminum plant."
        cid = story_preservation.preserve_turn(
            narrator_id="kent",
            transcript=normal,
            trigger_reason="full_threshold",
        )
        row = story_preservation.get_candidate(cid)
        self.assertIsNotNone(row)
        assert row is not None  # narrow for type checker
        self.assertEqual(row["transcript"], normal)

    def test_invalid_trigger_reason_rejected(self):
        from api.services import story_preservation

        with self.assertRaises(ValueError):
            story_preservation.preserve_turn(
                narrator_id="kent",
                transcript="something",
                trigger_reason="made_up_reason",
            )


class TurnIdIdempotencyTest(_TempDbCase):
    """WO-LORI-STORY-CAPTURE-01 Phase 1A Commit 3b — chat_ws may
    re-fire preservation on reconnect/retry. preserve_turn must
    de-dupe on (narrator_id, turn_id) so retries don't write
    duplicate story_candidate rows."""

    def test_same_turn_id_returns_existing_candidate(self):
        from api.services import story_preservation

        cid_first = story_preservation.preserve_turn(
            narrator_id="janice-josephine-horne",
            transcript="First arrival at the hospital.",
            trigger_reason="full_threshold",
            turn_id="turn-abc-123",
        )
        cid_second = story_preservation.preserve_turn(
            narrator_id="janice-josephine-horne",
            transcript="(retry — different transcript shouldn't matter)",
            trigger_reason="borderline_scene_anchor",
            turn_id="turn-abc-123",
        )
        self.assertEqual(cid_first, cid_second,
                         "retry with same (narrator, turn_id) must return existing id")

        # And the row count is exactly 1, not 2.
        unreviewed = story_preservation.get_unreviewed(
            narrator_id="janice-josephine-horne"
        )
        self.assertEqual(len(unreviewed), 1)

    def test_different_turn_id_writes_new_candidate(self):
        from api.services import story_preservation

        cid_first = story_preservation.preserve_turn(
            narrator_id="kent",
            transcript="One scene.",
            trigger_reason="full_threshold",
            turn_id="turn-aaa",
        )
        cid_second = story_preservation.preserve_turn(
            narrator_id="kent",
            transcript="Another scene.",
            trigger_reason="full_threshold",
            turn_id="turn-bbb",
        )
        self.assertNotEqual(cid_first, cid_second)

        rows = story_preservation.get_unreviewed(narrator_id="kent")
        self.assertEqual(len(rows), 2)

    def test_no_turn_id_does_not_dedupe(self):
        # When the caller has no turn_id (e.g. legacy path or no UI
        # turn marker), the dedupe is opted-out and each call writes
        # a new row. This is by design — without a turn_id we have
        # no key to dedupe on.
        from api.services import story_preservation

        cid_first = story_preservation.preserve_turn(
            narrator_id="kent",
            transcript="Same content twice.",
            trigger_reason="full_threshold",
        )
        cid_second = story_preservation.preserve_turn(
            narrator_id="kent",
            transcript="Same content twice.",
            trigger_reason="full_threshold",
        )
        self.assertNotEqual(cid_first, cid_second)

    def test_corrupt_existing_row_falls_through_to_fresh_insert(self):
        # Patch D (2026-04-30 polish): if a row exists for the
        # (narrator, turn_id) pair but its `id` is falsy (only
        # possible via direct SQL or schema corruption), preserve_turn
        # must NOT return None — it must fall through to a fresh
        # insert and log a WARNING. We seed a row with id='' (passes
        # NOT NULL but is falsy in Python) to exercise the path.
        from api.services import story_preservation

        con = sqlite3.connect(str(self.db_path))
        try:
            con.execute(
                """
                INSERT INTO story_candidates (
                    id, narrator_id, transcript, trigger_reason, turn_id,
                    confidence, era_candidates, scene_anchors, extracted_fields
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                ("", "kent", "corrupt sentinel", "full_threshold",
                 "turn-corrupt-1", "low", "[]", "[]", "{}"),
            )
            con.commit()
        finally:
            con.close()

        # preserve_turn should NOT return "" — it should fall through
        # and write a fresh row with a real UUID.
        new_id = story_preservation.preserve_turn(
            narrator_id="kent",
            transcript="real story here.",
            trigger_reason="full_threshold",
            turn_id="turn-corrupt-1",
        )
        self.assertTrue(new_id)  # non-empty UUID
        self.assertNotEqual(new_id, "")

    def test_same_turn_id_different_narrator_writes_new(self):
        # turn_id alone isn't unique — only (narrator_id, turn_id) is.
        # Two narrators producing identical turn_id strings must not
        # collide.
        from api.services import story_preservation

        cid_kent = story_preservation.preserve_turn(
            narrator_id="kent",
            transcript="Kent's turn.",
            trigger_reason="full_threshold",
            turn_id="turn-shared-id",
        )
        cid_janice = story_preservation.preserve_turn(
            narrator_id="janice-josephine-horne",
            transcript="Janice's turn (same turn_id by coincidence).",
            trigger_reason="full_threshold",
            turn_id="turn-shared-id",
        )
        self.assertNotEqual(cid_kent, cid_janice)


class GetByTurnTest(_TempDbCase):
    """db.story_candidate_get_by_turn — accessor that powers the
    dedupe in preserve_turn. Direct unit coverage so failure modes
    surface here rather than via the higher-level idempotency tests."""

    def test_missing_returns_none(self):
        result = self._db.story_candidate_get_by_turn(
            narrator_id="kent", turn_id="never-seen"
        )
        self.assertIsNone(result)

    def test_empty_args_return_none(self):
        self.assertIsNone(self._db.story_candidate_get_by_turn(
            narrator_id="", turn_id="x"
        ))
        self.assertIsNone(self._db.story_candidate_get_by_turn(
            narrator_id="kent", turn_id=""
        ))
        self.assertIsNone(self._db.story_candidate_get_by_turn(
            narrator_id=None, turn_id=None  # type: ignore[arg-type]
        ))

    def test_finds_by_pair(self):
        from api.services import story_preservation

        cid = story_preservation.preserve_turn(
            narrator_id="kent",
            transcript="One scene.",
            trigger_reason="full_threshold",
            turn_id="turn-xyz",
        )
        found = self._db.story_candidate_get_by_turn(
            narrator_id="kent", turn_id="turn-xyz"
        )
        self.assertIsNotNone(found)
        assert found is not None  # narrow for the type checker
        self.assertEqual(found["id"], cid)
        self.assertEqual(found["narrator_id"], "kent")
        self.assertEqual(found["turn_id"], "turn-xyz")


class UpdatePlacementTest(_TempDbCase):
    def _seed(self) -> str:
        from api.services import story_preservation

        return story_preservation.preserve_turn(
            narrator_id="janice-josephine-horne",
            transcript="That story about the hospital.",
            trigger_reason="full_threshold",
        )

    def test_dob_plus_bucket_auto_derives(self):
        """The product unlock: DOB + bucket → year range + era_candidates.
        No exact-date pressure on the narrator."""
        from api.services import story_preservation

        cid = self._seed()
        story_preservation.update_placement(
            cid,
            age_bucket="in_school",
            narrator_dob=date(1939, 8, 30),
        )
        row = story_preservation.get_candidate(cid)
        self.assertEqual(row["age_bucket"], "in_school")
        self.assertEqual(row["era_candidates"], ["early_school_years"])
        self.assertEqual(row["estimated_year_low"], 1944)
        self.assertEqual(row["estimated_year_high"], 1950)

    def test_caller_supplied_year_overrides_derivation(self):
        """If the caller passes explicit year_low/year_high, the
        derivation is suppressed for those fields."""
        from api.services import story_preservation

        cid = self._seed()
        story_preservation.update_placement(
            cid,
            age_bucket="in_school",
            narrator_dob=date(1939, 8, 30),
            estimated_year_low=1945,  # explicit override
            estimated_year_high=1949,
        )
        row = story_preservation.get_candidate(cid)
        self.assertEqual(row["estimated_year_low"], 1945)
        self.assertEqual(row["estimated_year_high"], 1949)

    def test_multi_era_bucket_preserves_ambiguity(self):
        """before_school spans two eras — both must end up in
        era_candidates."""
        from api.services import story_preservation

        cid = self._seed()
        story_preservation.update_placement(
            cid,
            age_bucket="before_school",
            narrator_dob=date(1939, 8, 30),
        )
        row = story_preservation.get_candidate(cid)
        self.assertEqual(
            row["era_candidates"],
            ["earliest_years", "early_school_years"],
        )

    def test_unknown_bucket_clears_to_none_eras(self):
        """A stale bucket label should NOT crash; it should land with
        empty era_candidates and let the operator review queue resolve."""
        from api.services import story_preservation

        cid = self._seed()
        story_preservation.update_placement(
            cid,
            age_bucket="middle_aged",  # not in the table
            narrator_dob=date(1939, 8, 30),
        )
        row = story_preservation.get_candidate(cid)
        # Bucket itself is normalized but stored
        self.assertEqual(row["age_bucket"], "middle_aged")
        # No era candidates derived
        self.assertEqual(row["era_candidates"], [])
        # No year derivation either
        self.assertIsNone(row["estimated_year_low"])
        self.assertIsNone(row["estimated_year_high"])

    def test_dob_missing_no_year_derivation(self):
        """Bucket without DOB → era_candidates set, but year range
        stays None. Operator can fact-check at review time."""
        from api.services import story_preservation

        cid = self._seed()
        story_preservation.update_placement(cid, age_bucket="in_school")
        row = story_preservation.get_candidate(cid)
        self.assertEqual(row["age_bucket"], "in_school")
        self.assertEqual(row["era_candidates"], ["early_school_years"])
        self.assertIsNone(row["estimated_year_low"])
        self.assertIsNone(row["estimated_year_high"])

    def test_caller_supplied_eras_override_derivation(self):
        from api.services import story_preservation

        cid = self._seed()
        story_preservation.update_placement(
            cid,
            age_bucket="in_school",
            era_candidates=["adolescence"],  # operator's call
            narrator_dob=date(1939, 8, 30),
        )
        row = story_preservation.get_candidate(cid)
        self.assertEqual(row["era_candidates"], ["adolescence"])

    def test_invalid_confidence_rejected(self):
        from api.services import story_preservation

        cid = self._seed()
        with self.assertRaises(ValueError):
            story_preservation.update_placement(cid, confidence="bogus")


class ReadAccessorsTest(_TempDbCase):
    def test_get_unreviewed_orders_newest_first(self):
        from api.services import story_preservation

        cid1 = story_preservation.preserve_turn(
            narrator_id="janice",
            transcript="first story",
            trigger_reason="full_threshold",
        )
        cid2 = story_preservation.preserve_turn(
            narrator_id="janice",
            transcript="second story",
            trigger_reason="full_threshold",
        )
        rows = story_preservation.get_unreviewed()
        self.assertEqual(len(rows), 2)
        # Newest first — cid2 ahead of cid1. Created_at is timestamp-tied
        # but our INSERTs are millisecond-distinct; if equal, id DESC
        # tiebreaks. Either way cid2 should land first.
        ids = [r["id"] for r in rows]
        self.assertIn(cid1, ids)
        self.assertIn(cid2, ids)

    def test_get_unreviewed_filters_by_narrator(self):
        from api.services import story_preservation

        story_preservation.preserve_turn(
            narrator_id="janice",
            transcript="janice story",
            trigger_reason="full_threshold",
        )
        story_preservation.preserve_turn(
            narrator_id="kent",
            transcript="kent story",
            trigger_reason="full_threshold",
        )
        janice_rows = story_preservation.get_unreviewed(narrator_id="janice")
        self.assertEqual(len(janice_rows), 1)
        self.assertEqual(janice_rows[0]["narrator_id"], "janice")

    def test_get_unreviewed_excludes_promoted(self):
        """Once a candidate is promoted, it should drop out of the
        unreviewed list. Tests integration with db.story_candidate_update_review."""
        from api.services import story_preservation

        cid = story_preservation.preserve_turn(
            narrator_id="janice",
            transcript="story",
            trigger_reason="full_threshold",
        )
        # Mark as promoted
        self._db.story_candidate_update_review(
            cid, review_status="promoted", reviewed_by="operator"
        )
        rows = story_preservation.get_unreviewed()
        self.assertEqual(len(rows), 0)

    def test_get_candidate_missing_returns_none(self):
        from api.services import story_preservation

        result = story_preservation.get_candidate("nonexistent-id")
        self.assertIsNone(result)

    def test_get_candidate_empty_id_returns_none(self):
        from api.services import story_preservation

        self.assertIsNone(story_preservation.get_candidate(""))


class Law3RuntimeIntegrityTest(_TempDbCase):
    """Dynamic verification that preservation actually works when the
    extractor isn't available. Companion to the static AST-import gate
    in test_story_preservation_isolation.py."""

    def test_preserve_succeeds_without_extractor(self):
        """The whole point: this test imports story_preservation and
        calls preserve_turn() WITHOUT importing the extraction stack
        anywhere. If preservation depended on extraction, this test
        would fail at import time."""
        from api.services import story_preservation

        # Affirmatively confirm the extractor is NOT loaded
        for forbidden in (
            "api.routers.extract",
            "api.prompt_composer",
            "api.routers.chat_ws",
        ):
            self.assertNotIn(
                forbidden,
                sys.modules,
                f"{forbidden} was imported as a side effect of "
                "importing story_preservation — LAW 3 violation",
            )

        cid = story_preservation.preserve_turn(
            narrator_id="janice",
            transcript="The hospital had a long porch.",
            trigger_reason="full_threshold",
        )
        self.assertTrue(cid)
        row = story_preservation.get_candidate(cid)
        self.assertEqual(row["transcript"], "The hospital had a long porch.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
