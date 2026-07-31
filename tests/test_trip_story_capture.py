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



class _CaptureForTurnCase(_CaptureCase):
    """Step 2 gate (capture_for_turn) — flag + shelf + delegation + non-fatal."""

    def setUp(self):
        super().setUp()
        # Test-isolation fix (2026-07-10): restore the process's original
        # flag instead of popping it (popping leaked flag_off into the
        # Mark Twain gate when both suites share one unittest process).
        self._orig_capture_flag = os.environ.get(tsc._FLAG)

    def tearDown(self):
        if self._orig_capture_flag is None:
            os.environ.pop(tsc._FLAG, None)
        else:
            os.environ[tsc._FLAG] = self._orig_capture_flag
        super().tearDown()

    def _rt(self, **kw):
        base = {"active_trip_id": self.trip_id, "travels_shelf_open": True}
        base.update(kw)
        return base

    # 1. flag OFF → never captures (byte-stable default)
    def test_flag_off_no_capture(self):
        os.environ.pop(tsc._FLAG, None)
        r = tsc.capture_for_turn(
            self.person_id, self._rt(), "A long meaningful trip answer here.",
            previous_prompt_kind="trip", turn_id="t-1")
        self.assertFalse(r["captured"])
        self.assertEqual(r["reason"], "flag_off")
        self.assertEqual(len(self._notes()), 0)

    # 2. flag on, no active trip → no note
    def test_flag_on_no_active_trip(self):
        os.environ[tsc._FLAG] = "1"
        r = tsc.capture_for_turn(
            self.person_id, self._rt(active_trip_id=None),
            "A long meaningful trip answer here.",
            previous_prompt_kind="trip", turn_id="t-2")
        self.assertFalse(r["captured"])
        self.assertEqual(r["reason"], "no_active_trip")

    # 3. flag on, shelf closed → no note
    def test_flag_on_shelf_closed(self):
        os.environ[tsc._FLAG] = "1"
        r = tsc.capture_for_turn(
            self.person_id, self._rt(travels_shelf_open=False),
            "A long meaningful trip answer here.",
            previous_prompt_kind="trip", turn_id="t-3")
        self.assertFalse(r["captured"])
        self.assertEqual(r["reason"], "shelf_closed")

    # 4. wrong owner → no note
    def test_flag_on_wrong_owner(self):
        os.environ[tsc._FLAG] = "1"
        r = tsc.capture_for_turn(
            self.other_person, self._rt(), "A long meaningful trip answer here.",
            previous_prompt_kind="trip", turn_id="t-4")
        self.assertFalse(r["captured"])
        self.assertEqual(r["reason"], "trip_not_owned")
        self.assertEqual(len(self._notes()), 0)

    # 5. previous turn not trip-scoped → no note
    def test_flag_on_not_trip_scoped(self):
        os.environ[tsc._FLAG] = "1"
        r = tsc.capture_for_turn(
            self.person_id, self._rt(), "A long meaningful answer with no scope.",
            previous_prompt_kind=None, turn_id="t-5")
        self.assertFalse(r["captured"])
        self.assertEqual(r["reason"], "not_trip_scoped")

    # 6. trivial reply → no note
    def test_flag_on_trivial(self):
        os.environ[tsc._FLAG] = "1"
        r = tsc.capture_for_turn(
            self.person_id, self._rt(), "Yes.",
            previous_prompt_kind="trip", turn_id="t-6")
        self.assertFalse(r["captured"])
        self.assertEqual(r["reason"], "trivial_reply")

    # 7 + 8 + 9. meaningful → one source_type=lori note, both flags 0
    def test_flag_on_meaningful_creates_note(self):
        os.environ[tsc._FLAG] = "1"
        r = tsc.capture_for_turn(
            self.person_id, self._rt(),
            "The little square in Munich stayed with me for years.",
            previous_prompt_kind="trip", turn_id="t-7")
        self.assertTrue(r["captured"])
        self.assertEqual(r["reason"], "meaningful_trip_answer")
        row = trip_repository.location_note_get(r["note_id"])
        self.assertEqual(row["source_type"], "lori")
        self.assertEqual(row["include_in_memoir"], 0)
        self.assertEqual(row["include_in_interview_context"], 0)

    # 10 + 11. dedupe same turn only; two turn_ids → two notes
    def test_dedupe_same_turn_two_turns_two_notes(self):
        os.environ[tsc._FLAG] = "1"
        a = dict(previous_prompt_kind="trip")
        r1 = tsc.capture_for_turn(self.person_id, self._rt(),
            "We wandered the old streets until the light faded.", turn_id="tt", **a)
        r1b = tsc.capture_for_turn(self.person_id, self._rt(),
            "We wandered the old streets until the light faded.", turn_id="tt", **a)
        self.assertEqual(r1b["reason"], "duplicate")
        r2 = tsc.capture_for_turn(self.person_id, self._rt(),
            "The next morning we found a market by the river.", turn_id="tu", **a)
        self.assertTrue(r2["captured"])
        self.assertEqual(r2["reason"], "meaningful_trip_answer")
        self.assertEqual(len(self._notes()), 2)

    # 12. photo answer via runtime → source_ref photo_link only when valid
    def test_photo_scope_via_runtime(self):
        os.environ[tsc._FLAG] = "1"
        rt = self._rt(active_photo_link_id=self.link_id)
        r = tsc.capture_for_turn(
            self.person_id, rt, "That was the station right after we arrived.",
            previous_prompt_kind="photo", turn_id="tp")
        self.assertTrue(r["captured"])
        self.assertEqual(r["source_ref"], "photo_link:" + self.link_id)
        self.assertEqual(r["scope"], "stop")

    # 13. non-fatal: an internal error returns error result, never raises
    def test_capture_for_turn_non_fatal_on_error(self):
        os.environ[tsc._FLAG] = "1"
        orig = trip_repository.trip_get
        def _boom(*a, **k):
            raise RuntimeError("simulated repo failure")
        trip_repository.trip_get = _boom
        try:
            r = tsc.capture_for_turn(
                self.person_id, self._rt(),
                "A meaningful trip answer that should not crash the turn.",
                previous_prompt_kind="trip", turn_id="t-err")
        finally:
            trip_repository.trip_get = orig
        self.assertFalse(r["captured"])
        self.assertEqual(r["reason"], "error")

    # 15. chat_ws wiring imports only the isolated service, never UI
    def test_chat_ws_wiring_no_ui_import(self):
        p = _SERVER_CODE / "api" / "routers" / "chat_ws.py"
        src = p.read_text(encoding="utf-8")
        self.assertIn("from ..services import trip_story_capture", src)
        for line in src.splitlines():
            st = line.strip()
            self.assertFalse(st.startswith("import ui"), st)
            self.assertFalse(st.startswith("from ui "), st)
            self.assertFalse(st.startswith("from ui."), st)



    # ── B. skip direct questions / info requests / meta-comments ──────────
    def test_skips_direct_questions_and_meta(self):
        for q in (
            "what can you tell me about the weather story that i was told "
            "do you know of anything",
            "i asked you a question about it.",
            "do you know anything about that weather system?",
            "can you explain that?",
            "why was it raining?",
            "what is that called?",
            "no, that's not what I asked",
        ):
            r = tsc.capture_trip_story_answer(
                person_id=self.person_id, active_trip_id=self.trip_id,
                narrator_text=q, previous_prompt_kind="trip",
                turn_id="q-" + q[:8])
            self.assertFalse(r["captured"], q)
            self.assertEqual(r["reason"], "direct_question_or_command", q)
        self.assertEqual(len(self._notes()), 0)

    def test_still_captures_real_narrative(self):
        goods = (
            "It was cold and rainy in Regensburg, and someone told us it was "
            "a regional pattern.",
            "The weather became part of the memory because we were always "
            "looking for warm food.",
        )
        for i, good in enumerate(goods):
            r = tsc.capture_trip_story_answer(
                person_id=self.person_id, active_trip_id=self.trip_id,
                narrator_text=good, previous_prompt_kind="trip",
                turn_id="g-" + str(i))
            self.assertTrue(r["captured"], good)
            self.assertEqual(r["reason"], "meaningful_trip_answer", good)
        self.assertEqual(len(self._notes()), 2)

    # ── A. note title comes from the prior Lori question ─────────────────
    def test_note_title_from_prior_lori_question(self):
        r = tsc.capture_trip_story_answer(
            person_id=self.person_id, active_trip_id=self.trip_id,
            narrator_text="Munich felt like the true start of the whole trip.",
            previous_lori_text="What do you remember about arriving in Munich?",
            previous_prompt_kind="trip", turn_id="title-1")
        self.assertTrue(r["captured"])
        row = trip_repository.location_note_get(r["note_id"])
        self.assertTrue(row["note_title"])
        self.assertIn("Munich", row["note_title"])

    # ── B. the day on a captured candidate note ─────────────────────────
    #
    # WO-TRIP-NARRATOR-BRIDGE-01 section D: "trip_day_id = durable
    # selected day when valid, otherwise NULL". Before that work order
    # the chat path passed no day at all, so a narrator answer given
    # while the operator had a day selected on a LIVE trip still landed
    # unplaced. The tests below fix both halves: the day is attached
    # when the database knows it, and it is NULL -- not guessed -- when
    # it does not.

    def _days(self):
        trip_repository.trip_days_generate(self.trip_id)
        return trip_repository.trip_days_list(self.trip_id)

    def _days2(self):
        """Day cards on the OTHER trip. The shared fixture builds Italy
        without dates, and day cards are generated from the date span,
        so the dates go on here rather than in setUp: giving every test
        in the file a dated second trip would change fixtures these
        tests do not own."""
        trip_repository.trip_update(
            self.trip2_id, start_date="2025-09-04", end_date="2025-09-06")
        trip_repository.trip_days_generate(self.trip2_id)
        return trip_repository.trip_days_list(self.trip2_id)

    def _capture_story(self, rt=None, turn_id="day-1"):
        os.environ[tsc._FLAG] = "1"
        return tsc.capture_for_turn(
            self.person_id, rt if rt is not None else self._rt(),
            "We walked out to the gravesite in the morning and then drove "
            "past the old school, just the outside of it.",
            previous_prompt_kind="trip", turn_id=turn_id)

    def test_a_live_trip_puts_the_candidate_on_the_selected_day(self):
        day_id = self._days()[0]["id"]
        trip_repository.trip_live_state_set(self.trip_id, "active")
        trip_repository.trip_selected_day_set(self.trip_id, day_id)
        r = self._capture_story()
        self.assertTrue(r["captured"])
        self.assertEqual(
            trip_repository.location_note_get(r["note_id"])["trip_day_id"],
            day_id)

    def test_a_completed_trip_on_the_shelf_leaves_the_day_null(self):
        """The live Bismarck shape. He opened a finished trip and told a
        story from his chair; there is no day the software knows. The
        story is still captured -- NULL is the day, not the verdict."""
        day_id = self._days()[0]["id"]
        trip_repository.trip_live_state_set(self.trip_id, "active")
        trip_repository.trip_selected_day_set(self.trip_id, day_id)
        trip_repository.trip_live_state_set(self.trip_id, "completed")
        r = self._capture_story(turn_id="day-2")
        self.assertTrue(r["captured"])
        self.assertIsNone(
            trip_repository.location_note_get(r["note_id"])["trip_day_id"])

    def test_the_day_is_never_taken_from_the_browser(self):
        """runtime71 says which trip is open on the shelf. It does not
        get to say which day a moment happened on: that value dies on a
        reload, and a wrong one puts a manufactured fact in front of an
        operator who cannot tell it from a human's choice."""
        day_id = self._days()[0]["id"]
        trip_repository.trip_live_state_set(self.trip_id, "completed")
        r = self._capture_story(
            rt=self._rt(active_trip_day_id=day_id), turn_id="day-3")
        self.assertTrue(r["captured"])
        self.assertIsNone(
            trip_repository.location_note_get(r["note_id"])["trip_day_id"])

    def test_a_selected_day_that_belongs_elsewhere_is_dropped(self):
        """A day re-parented or deleted out from under the selection.
        The story keeps its trip and loses its day, rather than being
        filed on a day from another journey."""
        foreign = self._days2()[0]["id"]
        trip_repository.trip_live_state_set(self.trip_id, "active")
        con = sqlite3.connect(str(self.db_path))
        try:
            con.execute("UPDATE trips SET active_trip_day_id=? WHERE id=?;",
                        (foreign, self.trip_id))
            con.commit()
        finally:
            con.close()
        r = self._capture_story(turn_id="day-4")
        self.assertTrue(r["captured"])
        row = trip_repository.location_note_get(r["note_id"])
        self.assertEqual(row["trip_id"], self.trip_id)
        self.assertIsNone(row["trip_day_id"])

    def test_a_day_from_a_different_live_trip_is_not_borrowed(self):
        """He is live on one trip and has another open on the shelf.
        The day belongs to the trip he is living in, so the shelf trip's
        note gets none."""
        self._days2()
        day_id = self._days()[0]["id"]
        trip_repository.trip_live_state_set(self.trip_id, "active")
        trip_repository.trip_selected_day_set(self.trip_id, day_id)
        r = self._capture_story(
            rt=self._rt(active_trip_id=self.trip2_id), turn_id="day-5")
        self.assertTrue(r["captured"])
        row = trip_repository.location_note_get(r["note_id"])
        self.assertEqual(row["trip_id"], self.trip2_id)
        self.assertIsNone(row["trip_day_id"])

    def test_the_candidate_is_still_review_only_with_a_day_on_it(self):
        """A day is a placement, not a promotion. Section D's other
        columns do not move because one of them got filled in."""
        day_id = self._days()[0]["id"]
        trip_repository.trip_live_state_set(self.trip_id, "active")
        trip_repository.trip_selected_day_set(self.trip_id, day_id)
        r = self._capture_story(turn_id="day-6")
        row = trip_repository.location_note_get(r["note_id"])
        self.assertEqual(row["source_type"], "lori")
        self.assertEqual(int(row["include_in_memoir"] or 0), 0)
        self.assertEqual(int(row["include_in_interview_context"] or 0), 0)
        self.assertEqual(int(row["hidden"] or 0), 0)

    def test_a_replayed_turn_does_not_write_a_second_candidate(self):
        """Section D: written once. The dedupe key is the committed
        turn id, so a reconnect that replays the same turn finds the
        note that is already there."""
        day_id = self._days()[0]["id"]
        trip_repository.trip_live_state_set(self.trip_id, "active")
        trip_repository.trip_selected_day_set(self.trip_id, day_id)
        first = self._capture_story(turn_id="day-7")
        again = self._capture_story(turn_id="day-7")
        self.assertTrue(again["captured"])
        self.assertEqual(again["reason"], "duplicate")
        self.assertEqual(again["note_id"], first["note_id"])
        self.assertEqual(len(self._notes()), 1)


class ModalCaptureTest(_CaptureCase):
    """WO-TRAVEL-DOC-LORI-MODAL-01 — backend capture slice. Modal turns
    are trip-scoped by construction, stamp source_surface, preserve
    photo_link refs, and keep both promotion flags OFF."""

    def setUp(self):
        super().setUp()
        # Test-isolation fix (2026-07-10): RESTORE the process's original
        # flag value in tearDown instead of popping it — popping broke the
        # Mark Twain gate when both suites run in one unittest process
        # with HORNELORE_TRIP_STORY_CAPTURE=1 exported.
        self._orig_capture_flag = os.environ.get(
            "HORNELORE_TRIP_STORY_CAPTURE")
        os.environ["HORNELORE_TRIP_STORY_CAPTURE"] = "1"

    def tearDown(self):
        if self._orig_capture_flag is None:
            os.environ.pop("HORNELORE_TRIP_STORY_CAPTURE", None)
        else:
            os.environ["HORNELORE_TRIP_STORY_CAPTURE"] =                 self._orig_capture_flag
        super().tearDown()

    def _note(self, note_id):
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        r = con.execute("SELECT * FROM trip_location_notes WHERE id=?",
                        (note_id,)).fetchone()
        con.close()
        return dict(r) if r else None

    def test_modal_answer_creates_candidate_with_provenance(self):
        res = tsc.capture_modal_turn(
            self.person_id, {"active_trip_id": self.trip_id},
            "We spent the whole morning at the natural history museum",
            previous_lori_text="What do you remember about that day?",
            conv_id="convA", turn_id="t1")
        self.assertTrue(res["captured"], res)
        n = self._note(res["note_id"])
        self.assertEqual(n["source_type"], "lori")
        self.assertEqual(n["source_surface"], "travel_doc_modal")
        self.assertEqual(n["source_ref"], "modal_turn:convA:t1")
        self.assertEqual(n["include_in_memoir"], 0)
        self.assertEqual(n["include_in_interview_context"], 0)

    def test_photo_scoped_modal_answer_preserves_photo_link(self):
        res = tsc.capture_modal_turn(
            self.person_id,
            {"active_trip_id": self.trip_id,
             "active_trip_stop_id": self.stop_id,
             "active_photo_link_id": self.link_id},
            "A bunch of men in lederhosen outside the beer hall",
            conv_id="convA", turn_id="t2")
        self.assertTrue(res["captured"], res)
        n = self._note(res["note_id"])
        self.assertIn("modal_turn:convA:t2", n["source_ref"])
        self.assertIn("photo_link:" + self.link_id, n["source_ref"])
        self.assertEqual(n["trip_stop_id"], self.stop_id)

    def test_modal_needs_no_shelf_and_no_trip_scope_evidence(self):
        # No previous_lori_text, no shelf — modal is scoped by surface.
        res = tsc.capture_modal_turn(
            self.person_id, {"active_trip_id": self.trip_id},
            "The pretzels were bigger than my head at that market",
            conv_id="c", turn_id="t3")
        self.assertTrue(res["captured"], res)

    def test_foreign_trip_rejected(self):
        res = tsc.capture_modal_turn(
            self.other_person, {"active_trip_id": self.trip_id},
            "Trying to write into someone else's trip",
            conv_id="c", turn_id="t4")
        self.assertFalse(res["captured"])
        self.assertEqual(res["reason"], "trip_not_owned")

    def test_trivial_and_questions_still_skipped(self):
        r1 = tsc.capture_modal_turn(
            self.person_id, {"active_trip_id": self.trip_id},
            "yes", conv_id="c", turn_id="t5")
        self.assertFalse(r1["captured"])
        r2 = tsc.capture_modal_turn(
            self.person_id, {"active_trip_id": self.trip_id},
            "what date was that taken", conv_id="c", turn_id="t6")
        self.assertFalse(r2["captured"])

    def test_flag_off_captures_nothing(self):
        os.environ.pop("HORNELORE_TRIP_STORY_CAPTURE", None)
        res = tsc.capture_modal_turn(
            self.person_id, {"active_trip_id": self.trip_id},
            "A full story about the museum morning in Munich",
            conv_id="c", turn_id="t7")
        self.assertFalse(res["captured"])
        self.assertEqual(res["reason"], "flag_off")

    def test_modal_turn_dedupe(self):
        kw = dict(conv_id="convD", turn_id="t8")
        a = tsc.capture_modal_turn(
            self.person_id, {"active_trip_id": self.trip_id},
            "The drive through the Alps took all afternoon", **kw)
        b = tsc.capture_modal_turn(
            self.person_id, {"active_trip_id": self.trip_id},
            "The drive through the Alps took all afternoon", **kw)
        self.assertTrue(a["captured"] and b["captured"])
        self.assertEqual(b["reason"], "duplicate")
        self.assertEqual(a["note_id"], b["note_id"])

    def test_shelf_path_unchanged_no_surface_stamp(self):
        # Legacy shelf capture writes source_surface NULL.
        res = tsc.capture_trip_story_answer(
            person_id=self.person_id, active_trip_id=self.trip_id,
            narrator_text="We started in Munich then drove east",
            previous_lori_text="Tell me about your trip to Munich",
            previous_prompt_kind="trip_open", turn_id="t9")
        self.assertTrue(res["captured"], res)
        n = self._note(res["note_id"])
        self.assertIsNone(n["source_surface"])

class ModalScopeShapeTest(_CaptureCase):
    """WO-LIVE-TRIP-COMPANION-02 step 2 --- the modal scope is an OBJECT,
    and when it is not, that fact has to be legible.

    THE DEFECT. `scripts/vs1_trip_companion_acceptance.py` sent the
    STRING "trip" as `modal_scope` for three acceptance runs while its
    own docstring claimed to copy the pane's payload field for field.
    The server called `.get()` on it, AttributeError came back, the
    blanket non-fatal except swallowed it, and the operator log printed
    `captured=False reason=error`. Three runs carried that line. Nobody
    could tell from it that the scope had never been built --- `error`
    names no thing that happened, so it could not be acted on, and the
    acceptance run went green while the modal capture path had in fact
    never executed once.

    WHAT THESE TESTS PIN. Two separate promises. First, a wrong-SHAPE
    scope is a NAMED no-op (`malformed_scope`) and never an `error`,
    because a caller sending the wrong type is a caller bug that should
    say so in one word. Second, when something genuinely does raise, the
    result reports the exception CLASS and never `str(exc)` --- these
    results are snapshotted onto operator surfaces, and an exception
    raised while handling a narrator turn can carry that turn's words in
    its message. The privacy test below builds an exception whose text is
    a sentence a narrator might really say, and proves it does not come
    back out.

    A `None` scope is NOT malformed. That is an ordinary trip-level turn
    and has its own downstream gates; conflating the two would turn a
    supported call into a reported fault.
    """

    def setUp(self):
        super().setUp()
        self._orig_capture_flag = os.environ.get(
            "HORNELORE_TRIP_STORY_CAPTURE")
        os.environ["HORNELORE_TRIP_STORY_CAPTURE"] = "1"

    def tearDown(self):
        if self._orig_capture_flag is None:
            os.environ.pop("HORNELORE_TRIP_STORY_CAPTURE", None)
        else:
            os.environ["HORNELORE_TRIP_STORY_CAPTURE"] = \
                self._orig_capture_flag
        super().tearDown()

    # ── the shape gate ───────────────────────────────────────────────────
    def test_a_string_scope_is_a_named_no_op_not_an_error(self):
        # The exact payload the harness sent for three runs.
        res = tsc.capture_modal_turn(
            self.person_id, "trip",
            "We walked the whole riverfront before supper",
            conv_id="convS", turn_id="s1")
        self.assertFalse(res["captured"])
        self.assertEqual(res["reason"], "malformed_scope")
        self.assertNotEqual(res["reason"], "error")
        # The type is named so the caller can find its own bug.
        self.assertEqual(res["error"], "str")

    def test_other_wrong_shapes_are_named_the_same_way(self):
        for bad in ("trip", 7, ["active_trip_id"], True):
            with self.subTest(bad=bad):
                res = tsc.capture_modal_turn(
                    self.person_id, bad,
                    "A long enough answer about the afternoon in Bismarck",
                    conv_id="convS", turn_id="s2")
                self.assertFalse(res["captured"])
                self.assertEqual(res["reason"], "malformed_scope")

    def test_a_wrong_shape_writes_nothing(self):
        before = len(trip_repository.location_notes_list(self.trip_id))
        tsc.capture_modal_turn(
            self.person_id, "trip",
            "The bridge looked completely different in the evening light",
            conv_id="convS", turn_id="s3")
        after = len(trip_repository.location_notes_list(self.trip_id))
        self.assertEqual(before, after)

    def test_absent_scope_is_not_malformed(self):
        # None is a supported call, not a fault. It has no trip, so it
        # stops at the ordinary downstream gate --- but it must not be
        # reported as a shape problem.
        res = tsc.capture_modal_turn(
            self.person_id, None,
            "A perfectly ordinary sentence about the trip",
            conv_id="convS", turn_id="s4")
        self.assertFalse(res["captured"])
        self.assertNotEqual(res["reason"], "malformed_scope")

    def test_an_empty_dict_is_a_real_scope(self):
        res = tsc.capture_modal_turn(
            self.person_id, {},
            "Another perfectly ordinary sentence about the trip",
            conv_id="convS", turn_id="s5")
        self.assertNotEqual(res["reason"], "malformed_scope")

    def test_a_real_scope_still_captures(self):
        # The gate must not have cost us the working path.
        res = tsc.capture_modal_turn(
            self.person_id, {"active_trip_id": self.trip_id},
            "We stopped at the overlook and stayed longer than we meant to",
            conv_id="convS", turn_id="s6")
        self.assertTrue(res["captured"], res)

    def test_the_shape_gate_runs_after_the_flag_gate(self):
        # Flag off means capture does nothing at all, including any
        # opinion about the caller's argument shapes.
        os.environ.pop("HORNELORE_TRIP_STORY_CAPTURE", None)
        res = tsc.capture_modal_turn(
            self.person_id, "trip", "Anything at all",
            conv_id="convS", turn_id="s7")
        self.assertEqual(res["reason"], "flag_off")

    # ── the privacy of the failure report ────────────────────────────────
    def test_a_real_failure_reports_the_class_and_not_the_message(self):
        secret = "Dad cried when we found the farmhouse still standing"

        class TripCaptureExploded(RuntimeError):
            pass

        def boom(**kwargs):
            raise TripCaptureExploded(secret)

        orig = tsc.capture_trip_story_answer
        tsc.capture_trip_story_answer = boom
        try:
            res = tsc.capture_modal_turn(
                self.person_id, {"active_trip_id": self.trip_id},
                secret, conv_id="convS", turn_id="s8")
        finally:
            tsc.capture_trip_story_answer = orig
        self.assertFalse(res["captured"])
        self.assertEqual(res["reason"], "error")
        self.assertEqual(res["error"], "TripCaptureExploded")
        # Nothing anywhere in the result may quote the narrator.
        self.assertNotIn(secret, repr(res))

    def test_the_non_fatal_contract_holds_for_the_shelf_path_too(self):
        secret = "Mom kept the ticket stub in her wallet for thirty years"

        class ShelfCaptureExploded(RuntimeError):
            pass

        def boom(**kwargs):
            raise ShelfCaptureExploded(secret)

        orig = tsc.capture_trip_story_answer
        tsc.capture_trip_story_answer = boom
        try:
            res = tsc._capture_for_turn_impl(
                self.person_id,
                {"travels_shelf_open": True, "active_trip_id": self.trip_id},
                secret, conv_id="convS", turn_id="s9")
        finally:
            tsc.capture_trip_story_answer = orig
        self.assertEqual(res["reason"], "error")
        self.assertEqual(res["error"], "ShelfCaptureExploded")
        self.assertNotIn(secret, repr(res))

    def test_no_except_clause_in_this_module_reports_str_of_the_exception(self):
        # Belt and braces against the next person restoring `str(exc)`
        # because it reads as more helpful. It is more helpful; it is
        # also the narrator's words on an operator screen.
        #
        # Read the CODE, not the file: the comment above each except
        # block says "the CLASS, never str(exc)", and a plain substring
        # scan would match the warning instead of the thing it warns
        # about. Every `except ... as exc` in this module is checked for
        # what it actually passes on.
        tree = ast.parse((_SERVER_CODE / "api" / "services"
                          / "trip_story_capture.py").read_text(encoding="utf-8"))
        handlers = [h for h in ast.walk(tree)
                    if isinstance(h, ast.ExceptHandler) and h.name]
        self.assertGreaterEqual(len(handlers), 2, "the non-fatal blocks")
        classy = 0
        for h in handlers:
            bound = h.name
            for node in ast.walk(h):
                # str(exc) / repr(exc) / f-strings over the exception.
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id in ("str", "repr")
                        and any(isinstance(a, ast.Name) and a.id == bound
                                for a in node.args)):
                    self.fail("%s(%s) reports the exception message" % (
                        node.func.id, bound))
                if isinstance(node, ast.JoinedStr):
                    for a in ast.walk(node):
                        if isinstance(a, ast.Name) and a.id == bound:
                            self.fail("f-string reports the exception message")
                if (isinstance(node, ast.Attribute)
                        and node.attr == "__name__"):
                    classy += 1
        self.assertGreaterEqual(classy, 2,
                                "each non-fatal block reports the class")


class ModalScopeBoundaryNormalizationTest(unittest.TestCase):
    """WO-LIVE-TRIP-COMPANION-02 step 2 --- ONE normalization, at the
    boundary where the value arrives.

    Chris's instruction was specific: "Normalize the modal-direct-answer
    result at its producing boundary. Do not scatter `.get()` guards
    throughout consumers." A guard in each consumer would have made the
    crash stop and left the design worse: every future consumer would
    have to remember, and the one that forgot would fail in production
    rather than in review. So `chat_ws` reads the raw `modal_scope` key
    in exactly one place.

    These tests read the source rather than importing it --- `chat_ws`
    imports fastapi, which is not installed in the test environment, and
    the property being pinned is structural anyway: WHERE the read
    happens, not what it returns for a given input. They read the CODE
    and not the comments: the helper's own comment quotes the key it
    exists to protect, and a naive substring scan counts that quotation
    as a second read.
    """

    @classmethod
    def setUpClass(cls):
        path = _SERVER_CODE / "api" / "routers" / "chat_ws.py"
        cls.src = path.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.src)
        cls.fn = None
        for node in ast.walk(cls.tree):
            if (isinstance(node, ast.FunctionDef)
                    and node.name == "_normalized_modal_scope"):
                cls.fn = node

    def _helper_source(self) -> str:
        self.assertIsNotNone(self.fn, "boundary helper not found")
        seg = ast.get_source_segment(self.src, self.fn)
        self.assertTrue(seg)
        return seg

    def test_the_boundary_helper_exists(self):
        self.assertIsNotNone(self.fn, "boundary helper not found")

    def test_the_raw_key_is_read_in_exactly_one_place(self):
        # Every subscript or .get() of "modal_scope" anywhere in chat_ws,
        # located by line so a failure names where the stray read is.
        reads = []
        for node in ast.walk(self.tree):
            key = None
            if (isinstance(node, ast.Subscript)
                    and isinstance(node.slice, ast.Constant)):
                key = node.slice.value
            elif (isinstance(node, ast.Call)
                  and isinstance(node.func, ast.Attribute)
                  and node.func.attr == "get"
                  and node.args
                  and isinstance(node.args[0], ast.Constant)):
                key = node.args[0].value
            if key == "modal_scope":
                reads.append(node.lineno)
        self.assertEqual(
            len(reads), 1,
            "modal_scope must be read once, at the boundary. Lines: "
            + repr(reads))
        self.assertGreaterEqual(reads[0], self.fn.lineno)
        self.assertLessEqual(reads[0], self.fn.end_lineno)

    def test_every_consumer_goes_through_the_helper(self):
        calls = [n for n in ast.walk(self.tree)
                 if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name)
                 and n.func.id == "_normalized_modal_scope"]
        self.assertGreaterEqual(
            len(calls), 2,
            "both consumers (story capture and the direct-answer branch) "
            "must go through the boundary helper")

    def test_the_helper_does_not_repair_or_guess(self):
        # A string is not half a scope. Inventing an active_trip_id from
        # one would file a conversation against a trip nobody chose.
        body = self._helper_source()
        self.assertIn("isinstance(raw, dict)", body)
        self.assertIn("return None", body)

    def test_the_helper_logs_the_type_and_never_the_value(self):
        # The scope object carries person and trip identifiers and sits
        # next to narrative text, so the log line gets the TYPE and the
        # reason and never the object. Read it with `ast` rather than by
        # scanning text: the logging call is multi-line and an argument
        # on a continuation line is exactly the one a text scan misses.
        self.assertIsNotNone(self.fn, "boundary helper not found")
        logged, sanctioned = [], 0
        for node in ast.walk(self.fn):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if not (isinstance(f, ast.Attribute)
                    and isinstance(f.value, ast.Name)
                    and f.value.id == "logger"):
                continue
            for arg in node.args:
                # `type(raw).__name__` is the one sanctioned mention.
                if (isinstance(arg, ast.Attribute)
                        and arg.attr == "__name__"
                        and isinstance(arg.value, ast.Call)
                        and isinstance(arg.value.func, ast.Name)
                        and arg.value.func.id == "type"):
                    sanctioned += 1
                    continue
                logged.extend(
                    n.id for n in ast.walk(arg) if isinstance(n, ast.Name))
        self.assertEqual(sanctioned, 1, "the type is what gets logged")
        self.assertNotIn("raw", logged,
                         "the scope object itself must never be logged")


if __name__ == "__main__":
    unittest.main()
