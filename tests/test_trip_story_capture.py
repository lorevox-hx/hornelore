"""WO-TRIP-LORI-ANSWER-CAPTURE-01 Step 1 — isolated capture service.

Reverse flow of trip_interview_context: a narrator's trip-scoped answer is
saved as a CANDIDATE trip_location_notes row (review-only, both promotion
flags OFF). No chat_ws wiring in Step 1.
"""
from __future__ import annotations

import ast
import os
import sqlite3
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api import db as _db  # noqa: E402
from api.services import trip_repository  # noqa: E402
from api.services import trip_story_capture as tsc  # noqa: E402


def _add_photo(con, pid, narrator_id, ready=1):
    con.execute(
        "INSERT INTO photos (id, narrator_id, image_path, file_hash, "
        "narrator_ready) VALUES (?, ?, ?, ?, ?)",
        (pid, narrator_id, "/tmp/" + pid + ".jpg", "hash-" + pid, ready),
    )


class _CaptureCase(unittest.TestCase):
    def setUp(self):
        self._tmpdb = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self._tmpdb.close()
        self.db_path = Path(self._tmpdb.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()
        self.person_id = str(uuid.uuid4())
        self.other_person = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        for pid in (self.person_id, self.other_person):
            con.execute(
                "INSERT INTO people (id, display_name, date_of_birth, "
                "created_at, updated_at) VALUES (?, 'P', '1962-12-24', "
                "'2026-07-08', '2026-07-08');", (pid,))
        con.commit()
        con.close()

        # Primary trip owned by person_id.
        self.trip_id = trip_repository.trip_create(
            self.person_id, "Spring 2026", start_date="2026-05-22",
            end_date="2026-06-13")
        self.region_id = trip_repository.region_create(self.trip_id, "Germany")
        self.stop_id = trip_repository.stop_create(
            self.trip_id, self.region_id, "Munich")

        # A second, DIFFERENT trip (also person_id) — for cross-trip scope tests.
        self.trip2_id = trip_repository.trip_create(self.person_id, "Italy 2025")
        self.region2_id = trip_repository.region_create(self.trip2_id, "Tuscany")
        self.stop2_id = trip_repository.stop_create(
            self.trip2_id, self.region2_id, "Florence")

        # A narrator-ready photo linked to the Munich stop on trip 1.
        con = sqlite3.connect(str(self.db_path))
        _add_photo(con, "p_munich", self.person_id, 1)
        con.commit()
        con.close()
        self.link_id = trip_repository.photo_link_upsert(
            self.trip_id, "p_munich", trip_region_id=self.region_id,
            trip_stop_id=self.stop_id, assignment_method="operator")

    def tearDown(self):
        _db.DB_PATH = self._orig_db
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def _notes(self, trip_id=None):
        return trip_repository.location_notes_list(trip_id or self.trip_id)

    # ── 1. captures a meaningful answer after a trip-scoped question ──────
    def test_captures_meaningful_trip_answer(self):
        r = tsc.capture_trip_story_answer(
            person_id=self.person_id, active_trip_id=self.trip_id,
            narrator_text="We were tired when we landed, but Munich felt "
                          "like the real start of the trip.",
            previous_lori_text="What do you remember about arriving in Munich?",
            turn_id="t-1")
        self.assertTrue(r["captured"])
        self.assertEqual(r["reason"], "meaningful_trip_answer")
        self.assertIsNotNone(r["note_id"])
        notes = self._notes()
        self.assertEqual(len(notes), 1)
        self.assertIn("real start of the trip", notes[0]["note_text"])

    # ── 2. no active trip ────────────────────────────────────────────────
    def test_no_active_trip(self):
        r = tsc.capture_trip_story_answer(
            person_id=self.person_id, active_trip_id=None,
            narrator_text="Munich was wonderful and full of life.",
            previous_prompt_kind="trip")
        self.assertFalse(r["captured"])
        self.assertEqual(r["reason"], "no_active_trip")

    # ── 3. trip not owned by person ──────────────────────────────────────
    def test_trip_not_owned(self):
        r = tsc.capture_trip_story_answer(
            person_id=self.other_person, active_trip_id=self.trip_id,
            narrator_text="Munich was wonderful and full of life.",
            previous_prompt_kind="trip", turn_id="t-x")
        self.assertFalse(r["captured"])
        self.assertEqual(r["reason"], "trip_not_owned")
        self.assertEqual(len(self._notes()), 0)

    # ── 4. trivial reply ─────────────────────────────────────────────────
    def test_trivial_reply_not_captured(self):
        for trivial in ("Yes.", "no", "okay", "I don't know", "maybe", "Sure!"):
            r = tsc.capture_trip_story_answer(
                person_id=self.person_id, active_trip_id=self.trip_id,
                narrator_text=trivial,
                previous_lori_text="What do you remember about Munich?",
                turn_id="t-" + trivial)
            self.assertFalse(r["captured"], trivial)
            self.assertEqual(r["reason"], "trivial_reply", trivial)
        self.assertEqual(len(self._notes()), 0)

    # ── 5. previous prompt not trip-scoped ───────────────────────────────
    def test_not_trip_scoped(self):
        r = tsc.capture_trip_story_answer(
            person_id=self.person_id, active_trip_id=self.trip_id,
            narrator_text="My favorite meal is my mother's roast chicken.",
            previous_lori_text="What is your favorite meal?",
            previous_prompt_kind="interview", turn_id="t-2")
        self.assertFalse(r["captured"])
        self.assertEqual(r["reason"], "not_trip_scoped")
        self.assertEqual(len(self._notes()), 0)

    # ── 6 + 7 + 8. flags OFF, source_type=lori ───────────────────────────
    def test_note_flags_off_and_source_lori(self):
        r = tsc.capture_trip_story_answer(
            person_id=self.person_id, active_trip_id=self.trip_id,
            narrator_text="The old town square in Munich was breathtaking.",
            previous_prompt_kind="trip", turn_id="t-3")
        self.assertTrue(r["captured"])
        row = trip_repository.location_note_get(r["note_id"])
        self.assertEqual(row["include_in_memoir"], 0)
        self.assertEqual(row["include_in_interview_context"], 0)
        self.assertEqual(row["source_type"], "lori")

    # ── 9. source_ref stores turn / conv id ──────────────────────────────
    def test_source_ref_turn_then_conv(self):
        r1 = tsc.capture_trip_story_answer(
            person_id=self.person_id, active_trip_id=self.trip_id,
            narrator_text="We walked along the river for hours that day.",
            previous_prompt_kind="trip", conv_id="c-9", turn_id="t-9")
        self.assertEqual(r1["source_ref"], "turn:t-9")   # turn wins
        r2 = tsc.capture_trip_story_answer(
            person_id=self.person_id, active_trip_id=self.trip_id,
            narrator_text="The cafe near the station served warm pretzels.",
            previous_prompt_kind="trip", conv_id="c-only")
        self.assertEqual(r2["source_ref"], "conv:c-only")  # falls back to conv

    # ── 10. photo-based answer → source_ref=photo_link:<id> ──────────────
    def test_photo_based_source_ref(self):
        r = tsc.capture_trip_story_answer(
            person_id=self.person_id, active_trip_id=self.trip_id,
            narrator_text="That was the train station after we landed.",
            previous_prompt_kind="photo", photo_link_id=self.link_id,
            turn_id="t-10")
        self.assertTrue(r["captured"])
        self.assertEqual(r["source_ref"], "photo_link:" + self.link_id)
        row = trip_repository.location_note_get(r["note_id"])
        self.assertEqual(row["source_ref"], "photo_link:" + self.link_id)
        # Photo carried its stop scope through.
        self.assertEqual(r["trip_stop_id"], self.stop_id)
        self.assertEqual(r["scope"], "stop")

    # ── 11. scope must belong to the trip ────────────────────────────────
    def test_scope_validation_cross_trip(self):
        # A stop from trip 2 must NOT attach to a note on trip 1.
        r = tsc.capture_trip_story_answer(
            person_id=self.person_id, active_trip_id=self.trip_id,
            narrator_text="The market that morning smelled of fresh bread.",
            previous_prompt_kind="trip",
            active_trip_stop_id=self.stop2_id,      # belongs to trip 2!
            active_trip_region_id=self.region2_id,  # belongs to trip 2!
            turn_id="t-11")
        self.assertTrue(r["captured"])
        self.assertIsNone(r["trip_stop_id"])    # invalid stop dropped
        self.assertIsNone(r["trip_region_id"])  # invalid region dropped
        self.assertEqual(r["scope"], "trip")    # fell back to trip level

    def test_scope_stop_region_trip_levels(self):
        # stop known → stop note
        r = tsc.capture_trip_story_answer(
            person_id=self.person_id, active_trip_id=self.trip_id,
            narrator_text="The bakery on the corner opened before dawn.",
            previous_prompt_kind="trip", active_trip_stop_id=self.stop_id,
            turn_id="ts")
        self.assertEqual(r["scope"], "stop")
        self.assertEqual(r["trip_stop_id"], self.stop_id)
        self.assertEqual(r["trip_region_id"], self.region_id)  # derived
        # only region known → region note
        r = tsc.capture_trip_story_answer(
            person_id=self.person_id, active_trip_id=self.trip_id,
            narrator_text="Bavaria in spring was greener than I expected.",
            previous_prompt_kind="trip", active_trip_region_id=self.region_id,
            turn_id="tr")
        self.assertEqual(r["scope"], "region")
        self.assertEqual(r["trip_region_id"], self.region_id)
        self.assertIsNone(r["trip_stop_id"])
        # neither → trip note
        r = tsc.capture_trip_story_answer(
            person_id=self.person_id, active_trip_id=self.trip_id,
            narrator_text="The whole journey changed how I see the world.",
            previous_prompt_kind="trip", turn_id="tt")
        self.assertEqual(r["scope"], "trip")
        self.assertIsNone(r["trip_stop_id"])
        self.assertIsNone(r["trip_region_id"])

    # ── 12. LAW-3 import isolation ───────────────────────────────────────
    def test_law3_isolation(self):
        p = _SERVER_CODE / "api" / "services" / "trip_story_capture.py"
        tree = ast.parse(p.read_text(encoding="utf-8"))
        forbidden = ("chat_ws", "prompt_composer", "extract", "memory_echo",
                     "llm_interview", "llm_api", "safety", "runtime71")
        mods = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods.append(node.module or "")
                mods += [(node.module or "") + "." + a.name for a in node.names]
        for m in mods:
            for bad in forbidden:
                self.assertNotIn(bad, m, "forbidden import: " + m)

    # ── 13. duplicate guard ──────────────────────────────────────────────
    def test_duplicate_guard_turn(self):
        args = dict(
            person_id=self.person_id, active_trip_id=self.trip_id,
            narrator_text="We took the slow train and it was worth every mile.",
            previous_prompt_kind="trip", turn_id="dup-1")
        r1 = tsc.capture_trip_story_answer(**args)
        r2 = tsc.capture_trip_story_answer(**args)  # same turn_id again
        self.assertTrue(r1["captured"])
        self.assertTrue(r2["captured"])          # captured=True but…
        self.assertEqual(r2["reason"], "duplicate")
        self.assertEqual(r2["note_id"], r1["note_id"])
        self.assertEqual(len(self._notes()), 1)  # no second row

    def test_duplicate_guard_photo(self):
        args = dict(
            person_id=self.person_id, active_trip_id=self.trip_id,
            narrator_text="That was the station café where we sat and waited.",
            previous_prompt_kind="photo", photo_link_id=self.link_id)
        r1 = tsc.capture_trip_story_answer(**args)
        r2 = tsc.capture_trip_story_answer(**args)
        self.assertEqual(r2["reason"], "duplicate")
        self.assertEqual(len(self._notes()), 1)

    def test_note_text_faithful_not_rewritten(self):
        original = "We   landed late,\n\nand Munich was quiet at that hour."
        r = tsc.capture_trip_story_answer(
            person_id=self.person_id, active_trip_id=self.trip_id,
            narrator_text=original, previous_prompt_kind="trip", turn_id="tf")
        row = trip_repository.location_note_get(r["note_id"])
        # whitespace collapsed but words preserved verbatim, not paraphrased
        self.assertIn("Munich was quiet at that hour", row["note_text"])
        self.assertIn("We landed late", row["note_text"])


    # ── hardening: conv_id-only must NOT over-dedupe (Chris review) ───────
    def test_conv_id_only_does_not_overdedupe(self):
        # Two DIFFERENT meaningful answers, same conversation, no turn_id.
        r1 = tsc.capture_trip_story_answer(
            person_id=self.person_id, active_trip_id=self.trip_id,
            narrator_text="The cathedral bells rang across the whole square.",
            previous_prompt_kind="trip", conv_id="c-shared")
        r2 = tsc.capture_trip_story_answer(
            person_id=self.person_id, active_trip_id=self.trip_id,
            narrator_text="Later we found a tiny bakery down a side street.",
            previous_prompt_kind="trip", conv_id="c-shared")
        self.assertTrue(r1["captured"])
        self.assertTrue(r2["captured"])
        self.assertEqual(r1["reason"], "meaningful_trip_answer")
        self.assertEqual(r2["reason"], "meaningful_trip_answer")  # NOT duplicate
        self.assertEqual(len(self._notes()), 2)
        # source_ref still records the conversation for traceability.
        self.assertEqual(r1["source_ref"], "conv:c-shared")

    # ── hardening: photo_link from another trip must not scope (Chris) ────
    def test_photo_link_from_other_trip_not_scoped(self):
        con = sqlite3.connect(str(self.db_path))
        _add_photo(con, "p_florence", self.person_id, 1)
        con.commit()
        con.close()
        other_link = trip_repository.photo_link_upsert(
            self.trip2_id, "p_florence", trip_region_id=self.region2_id,
            trip_stop_id=self.stop2_id, assignment_method="operator")
        # No other trip-scope signal: prompt_kind None, no place named.
        r = tsc.capture_trip_story_answer(
            person_id=self.person_id, active_trip_id=self.trip_id,
            narrator_text="It was a bright and unforgettable afternoon there.",
            previous_lori_text="Tell me more.",
            photo_link_id=other_link, turn_id="t-cross")
        self.assertFalse(r["captured"])
        self.assertEqual(r["reason"], "not_trip_scoped")
        self.assertEqual(len(self._notes()), 0)


if __name__ == "__main__":
    unittest.main()
