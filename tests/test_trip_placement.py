"""WO-LIVE-TRIP-COMPANION-01 Vertical Slice 1 — the turn-to-trip link.

WHAT THIS FILE GUARDS. Two subsystems worked and were never joined.
Lori persisted turns, wrote archive events and (since Gate 7 Phase 2)
dispatched field extraction. The travel-document system held trips,
generated trip days and placed photographs. Nothing connected a
conversation to a day, and the only notion of "the trip Lori is working
on" was `state.session.activeTripId` in ui/js/travels-shelf.js —
forwarded to the server as `runtime71.active_trip_id`. That is a
browser fact. It does not survive a reload and it does not survive a
restart, so nothing built on it could pass the restart test this slice
has to pass.

The governing rule for the slice is:

    Link a completed turn to the trip and the day it happened on.
    Do NOT copy the turn into the trip.

Each test below maps to one requirement of the work order and names it
in its docstring, so a later reader can tell which requirement a
failure retires.

WHY THE TESTS ARE SHAPED THIS WAY. Every name that matters here
(ft_add_row, apply_correction, trip_turn_links, runtime71) also appears
in the prose of the files being checked — this file included. A
substring guard would pass on a comment while missing a real call, the
exact failure mode CLAUDE.md warns about. So the structural assertions
read the AST, and the behavioural assertions run the real service
against a real sqlite database.

The strongest assertion in the file is _assert_only_links_changed: it
snapshots the row count of EVERY table before linking and after, and
requires that `trip_turn_links` is the only one that moved. That covers
"no family-truth write caused by linking" and "no change to correction
projection behavior" without having to enumerate which tables carry
family truth — a list that would go stale.
"""
from __future__ import annotations

import ast
import os
import sqlite3
import sys
import tempfile
import types
import unittest
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

# ── offline fastapi/pydantic stubs (repo convention) ─────────────────────
if "fastapi" not in sys.modules:
    stub = types.ModuleType("fastapi")

    class _APIRouter:
        def __init__(self, *a, **k):
            pass

        def _deco(self, *a, **k):
            def wrap(f):
                return f
            return wrap
        get = post = patch = delete = put = _deco

    class _HTTPException(Exception):
        def __init__(self, status_code=0, detail=""):
            self.status_code, self.detail = status_code, detail
            super().__init__(detail)

    stub.APIRouter = _APIRouter
    stub.HTTPException = _HTTPException
    stub.Query = lambda default=None, **k: default
    stub.File = lambda default=None, **k: default
    stub.Form = lambda default=None, **k: default
    stub.UploadFile = object
    sys.modules["fastapi"] = stub

if "pydantic" not in sys.modules:
    pstub = types.ModuleType("pydantic")

    class _BaseModel:
        def __init__(self, **kw):
            for _k, _v in kw.items():
                setattr(self, _k, _v)

    pstub.BaseModel = _BaseModel

    def _field(default=None, default_factory=None, **k):
        if default_factory is not None:
            return default_factory()
        return default

    pstub.Field = _field
    pstub.field_validator = lambda *a, **k: (lambda f: f)
    pstub.validator = lambda *a, **k: (lambda f: f)
    pstub.ConfigDict = dict
    sys.modules["pydantic"] = pstub

from fastapi import HTTPException  # noqa: E402
from api import db as _db  # noqa: E402
from api.services import trip_placement, trip_repository  # noqa: E402
from api.routers import trips  # noqa: E402



def _executable_string_constants(tree):
    """Every string literal in ``tree`` except docstrings.

    WO-LIVE-TRIP-COMPANION-01 (2026-07-30): the first version of this
    file scanned every ast.Constant and failed on the module's own
    prose. A docstring that names `runtime71.active_trip_id` in order
    to say it is not the authority is evidence for the rule, not a
    violation of it. Only literals the interpreter would evaluate are
    returned.
    """
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef,
                             ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None) or []
            if body and isinstance(body[0], ast.Expr) \
                    and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in docstrings:
            out.append(node.value)
    return out


class _Body:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _PlacementCase(unittest.TestCase):

    # ── fixture ───────────────────────────────────────────────────────
    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        tmp.close()
        self.db_path = Path(tmp.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()

        self._orig_flag = os.environ.get("HORNELORE_TRIPS")
        os.environ["HORNELORE_TRIPS"] = "1"
        self._orig_force = os.environ.get("HORNELORE_TRIP_LINK_FORCE_FAILURE")
        os.environ.pop("HORNELORE_TRIP_LINK_FORCE_FAILURE", None)
        self._orig_sync = trips.trip_timeline_bridge.sync_trip_to_life_record
        trips.trip_timeline_bridge.sync_trip_to_life_record = \
            lambda *a, **k: None

        self.person_id = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO people (id, display_name, date_of_birth, "
            "created_at, updated_at) VALUES (?, 'Placement Test', "
            "'1951-04-02', '2026-07-30', '2026-07-30');",
            (self.person_id,),
        )
        con.commit()
        con.close()

        self.trip_id = trip_repository.trip_create(
            person_id=self.person_id, title="Bavaria 2026",
            start_date="2026-08-01", end_date="2026-08-03",
            summary="placement fixture")
        trip_repository.trip_days_generate(self.trip_id)
        self.days = trip_repository.trip_days_list(self.trip_id)
        self.assertGreaterEqual(len(self.days), 3)
        self.day_id = self.days[0]["id"]
        self.other_day_id = self.days[1]["id"]

    def tearDown(self):
        trips.trip_timeline_bridge.sync_trip_to_life_record = self._orig_sync
        _db.DB_PATH = self._orig_db
        for name, val in (("HORNELORE_TRIPS", self._orig_flag),
                          ("HORNELORE_TRIP_LINK_FORCE_FAILURE",
                           self._orig_force)):
            if val is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = val
        try:
            self.db_path.unlink()
        except OSError:
            pass

    # ── helpers ───────────────────────────────────────────────────────
    def _persist_turn(self, conv_id="conv-1", user="We walked the old town.",
                      assistant="What did you notice first?"):
        """One real committed turn pair. Returns (user_row, assistant_row)."""
        ids = {}
        arow = _db.persist_turn_transaction(
            conv_id=conv_id, user_message=user, assistant_message=assistant,
            model_name="test", meta={"ws": True}, row_ids_out=ids)
        return ids.get("user_row_id"), arow

    def _link(self, arow, urow=None, conv_id="conv-1", mode="interview"):
        return trip_placement.link_completed_turn(
            narrator_id=self.person_id,
            assistant_turn_row_id=arow,
            user_turn_row_id=urow,
            conv_id=conv_id,
            turn_id="t-" + str(arow),
            turn_mode=mode,
            source="chat_ws")

    def _table_counts(self):
        con = sqlite3.connect(str(self.db_path))
        try:
            names = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%';")]
            out = {}
            for n in names:
                out[n] = con.execute(
                    'SELECT COUNT(*) FROM "' + n + '";').fetchone()[0]
            return out
        finally:
            con.close()

    def _assert_only_links_changed(self, before, after):
        moved = {k: (before.get(k), after.get(k))
                 for k in set(before) | set(after)
                 if before.get(k) != after.get(k)}
        self.assertEqual(
            list(moved.keys()), ["trip_turn_links"],
            "linking a turn wrote to something other than the link "
            "table: " + repr(moved))

    def _start_trip(self, day_id=None):
        trip_repository.trip_live_state_set(self.trip_id, "active")
        if day_id:
            trip_repository.trip_selected_day_set(self.trip_id, day_id)

    # ── 1. schema ─────────────────────────────────────────────────────
    def test_migration_0039_applies(self):
        """VS1 requires explicit active-trip and selected-day state and a
        durable turn-to-trip/day link. All three are schema."""
        con = sqlite3.connect(str(self.db_path))
        try:
            cols = {r[1] for r in con.execute("PRAGMA table_info(trips);")}
            self.assertIn("live_state", cols)
            self.assertIn("active_trip_day_id", cols)
            # status must survive untouched: it means authoring progress,
            # not lived state, and widening it was the wrong fix.
            self.assertIn("status", cols)
            objs = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master;")}
            self.assertIn("trip_turn_links", objs)
            self.assertIn("ux_trip_turn_links_assistant_row", objs)
            self.assertIn("ux_trips_one_live_active_per_person", objs)
        finally:
            con.close()

    def test_link_table_stores_no_narrative_text(self):
        """'Do not duplicate the narrative text into the link table.'

        Enforced on the columns, not on a promise: no TEXT column may
        hold either side of the conversation after a link is made.
        """
        self._start_trip(self.day_id)
        urow, arow = self._persist_turn(
            user="UNIQUE-NARRATOR-SENTENCE", assistant="UNIQUE-LORI-SENTENCE")
        self.assertEqual(self._link(arow, urow).status, "linked")
        con = sqlite3.connect(str(self.db_path))
        try:
            row = con.execute(
                "SELECT * FROM trip_turn_links;").fetchone()
            blob = " ".join(str(v) for v in row)
            self.assertNotIn("UNIQUE-NARRATOR-SENTENCE", blob)
            self.assertNotIn("UNIQUE-LORI-SENTENCE", blob)
        finally:
            con.close()

    # ── 2. lifecycle ──────────────────────────────────────────────────
    def test_active_is_deliberate_not_inferred_from_today(self):
        """'Do not infer active only from today's date.'

        A trip that exists is not a trip anybody is on. Only the
        explicit start makes it active.
        """
        self.assertIsNone(trip_repository.trip_active_get(self.person_id))
        trip_repository.trip_live_state_set(self.trip_id, "active")
        active = trip_repository.trip_active_get(self.person_id)
        self.assertIsNotNone(active)
        self.assertEqual(active["id"], self.trip_id)

    def test_finish_and_reopen_round_trip(self):
        """Required actions: Start trip / Resume / Finish trip / Reopen."""
        trip_repository.trip_live_state_set(self.trip_id, "active")
        trip_repository.trip_selected_day_set(self.trip_id, self.day_id)
        trip_repository.trip_live_state_set(self.trip_id, "completed")
        self.assertIsNone(trip_repository.trip_active_get(self.person_id))
        # Finishing clears the selected day: a finished trip has no
        # "today", and leaving a stale day selected would silently
        # place the next conversation on it.
        trip = trip_repository.trip_get(self.trip_id)
        self.assertFalse(trip.get("active_trip_day_id"))
        trip_repository.trip_live_state_set(self.trip_id, "active")
        self.assertEqual(
            trip_repository.trip_active_get(self.person_id)["id"],
            self.trip_id)

    def test_one_active_trip_per_narrator(self):
        """Starting a second trip names the conflict; it does not
        silently finish the first. Which trip you are on is the
        operator's call, not a side effect."""
        trip_repository.trip_live_state_set(self.trip_id, "active")
        second = trip_repository.trip_create(
            person_id=self.person_id, title="Second Trip",
            start_date="2026-09-01", end_date="2026-09-02", summary="")
        with self.assertRaises(trip_repository.TripStateError) as ctx:
            trip_repository.trip_live_state_set(second, "active")
        self.assertEqual(ctx.exception.conflict.get("id"), self.trip_id)
        # The first trip is untouched.
        self.assertEqual(
            trip_repository.trip_active_get(self.person_id)["id"],
            self.trip_id)

    def test_selected_day_must_belong_to_the_trip(self):
        other_trip = trip_repository.trip_create(
            person_id=self.person_id, title="Elsewhere",
            start_date="2026-10-01", end_date="2026-10-02", summary="")
        trip_repository.trip_days_generate(other_trip)
        foreign_day = trip_repository.trip_days_list(other_trip)[0]["id"]
        # TripStateError, not ValueError: a day from another trip is a
        # refused lifecycle transition like any other, and the caller
        # needs the message, not just the type.
        with self.assertRaises(trip_repository.TripStateError):
            trip_repository.trip_selected_day_set(self.trip_id, foreign_day)
        # And the refusal changed nothing.
        self.assertIsNone(
            trip_repository.trip_get(self.trip_id).get("active_trip_day_id"))

    # ── 3. placement outcomes ─────────────────────────────────────────
    def test_no_active_trip_is_a_calm_noop(self):
        """'graceful handling when no trip or day is selected.'

        The overwhelming majority of family-interview turns land here.
        It must be a noop, not a failure and not an invented link.
        """
        urow, arow = self._persist_turn()
        before = self._table_counts()
        out = self._link(arow, urow)
        self.assertEqual(out.status, "noop")
        self.assertEqual(out.reason, "no_active_trip")
        self.assertTrue(out.ok)
        self.assertEqual(before, self._table_counts())

    def test_ineligible_turn_mode_is_a_noop(self):
        """Only interview turns go on the trip timeline in VS1.
        `correction` in particular must stay out — it has its own
        guarded projection path and this slice was told not to change
        correction behaviour."""
        self._start_trip(self.day_id)
        urow, arow = self._persist_turn()
        for mode in ("correction", "floor_hold", "meta_question", ""):
            out = self._link(arow, urow, mode=mode)
            self.assertEqual(out.status, "noop", mode)
            self.assertEqual(out.reason, "ineligible_turn_mode", mode)

    def test_no_committed_row_is_a_noop_not_a_guess(self):
        """Without a persisted assistant row there is no stable
        idempotency key and nothing for the timeline to read text back
        out of. The answer is noop, never a fabricated key."""
        self._start_trip(self.day_id)
        for bad in (None, 0, ""):
            out = self._link(bad, None)
            self.assertEqual(out.status, "noop")
            self.assertEqual(out.reason, "no_committed_turn_row")

    def test_active_trip_and_selected_day_links_confirmed(self):
        """The happy path: a day the operator chose IS an operator
        choice, so the placement is confirmed, not suggested."""
        self._start_trip(self.day_id)
        urow, arow = self._persist_turn()
        before = self._table_counts()
        out = self._link(arow, urow)
        self.assertEqual(out.status, "linked")
        self.assertEqual(out.trip_id, self.trip_id)
        self.assertEqual(out.trip_day_id, self.day_id)
        self.assertEqual(out.placement_source, "active_trip_day")
        self.assertEqual(out.placement_status, "confirmed")
        self._assert_only_links_changed(before, self._table_counts())

    def test_active_trip_without_a_day_still_keeps_the_conversation(self):
        """'A failure to link the trip should not lose the conversation.
        It should leave an observable reconciliation item.'"""
        trip_repository.trip_live_state_set(self.trip_id, "active")
        urow, arow = self._persist_turn()
        out = self._link(arow, urow)
        self.assertEqual(out.status, "needs_day")
        self.assertTrue(out.ok)
        self.assertEqual(out.trip_id, self.trip_id)
        self.assertEqual(out.trip_day_id, "")
        self.assertEqual(out.placement_status, "needs_day")
        # Observable: it appears in the reconciliation list.
        unplaced = trip_repository.trip_day_conversation_items(
            self.trip_id, None)
        self.assertEqual(len(unplaced), 1)
        self.assertEqual(unplaced[0]["link_id"], out.link_id)
        # And it is counted where the calendar can show it.
        counts = trip_repository.trip_turn_link_counts(self.trip_id)
        self.assertEqual(counts.get("unplaced"), 1)

    # ── 4. idempotency ────────────────────────────────────────────────
    def test_linking_the_same_turn_twice_is_idempotent(self):
        """'idempotency if the same completed turn is linked twice.'"""
        self._start_trip(self.day_id)
        urow, arow = self._persist_turn()
        first = self._link(arow, urow)
        self.assertEqual(first.status, "linked")
        after_first = self._table_counts()
        second = self._link(arow, urow)
        self.assertEqual(second.status, "duplicate")
        self.assertEqual(second.link_id, first.link_id)
        self.assertEqual(after_first, self._table_counts())
        self.assertEqual(
            len(trip_repository.trip_turn_links_list(self.trip_id)), 1)

    def test_a_replay_does_not_drag_a_moved_conversation_back(self):
        """A human moved it. A replayed turn must not overrule them."""
        self._start_trip(self.day_id)
        urow, arow = self._persist_turn()
        out = self._link(arow, urow)
        moved = trip_repository.trip_turn_link_move(
            out.link_id, self.other_day_id)
        self.assertEqual(moved["trip_day_id"], self.other_day_id)
        self.assertEqual(moved["placement_source"], "operator_selected")
        replay = self._link(arow, urow)
        self.assertEqual(replay.status, "duplicate")
        still = trip_repository.trip_turn_links_list(self.trip_id)[0]
        self.assertEqual(still["trip_day_id"], self.other_day_id)
        self.assertEqual(still["placement_source"], "operator_selected")

    def test_two_different_turns_are_two_links(self):
        """The key is the committed row, not the words. Two turns that
        say the same thing are two turns."""
        self._start_trip(self.day_id)
        u1, a1 = self._persist_turn(user="Same words.", assistant="Same.")
        u2, a2 = self._persist_turn(user="Same words.", assistant="Same.")
        self.assertEqual(self._link(a1, u1).status, "linked")
        self.assertEqual(self._link(a2, u2).status, "linked")
        self.assertEqual(
            len(trip_repository.trip_turn_links_list(self.trip_id)), 2)

    # ── 5. the timeline is a projection ───────────────────────────────
    def test_timeline_reads_text_out_of_turns_not_out_of_the_link(self):
        """'Do not add a second conversation store. Do not copy turn
        text into a trip table.'

        Proved by editing `turns` behind the link and watching the
        timeline follow. A stored copy could not do that.
        """
        self._start_trip(self.day_id)
        urow, arow = self._persist_turn(
            user="First version.", assistant="Lori's reply.")
        self._link(arow, urow)
        items = trip_repository.trip_day_conversation_items(
            self.trip_id, self.day_id)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["narrator_said"], "First version.")
        self.assertEqual(items[0]["lori_said"], "Lori's reply.")
        self.assertEqual(items[0]["kind"], "conversation")
        # Source navigation back to the conversation.
        self.assertEqual(items[0]["assistant_turn_row_id"], arow)
        self.assertEqual(items[0]["user_turn_row_id"], urow)
        self.assertTrue(items[0]["conv_id"])

        con = sqlite3.connect(str(self.db_path))
        con.execute("UPDATE turns SET content='Second version.' WHERE id=?;",
                    (urow,))
        con.commit()
        con.close()
        items = trip_repository.trip_day_conversation_items(
            self.trip_id, self.day_id)
        self.assertEqual(items[0]["narrator_said"], "Second version.")

    def test_timeline_is_ordered_and_scoped_to_its_day(self):
        self._start_trip(self.day_id)
        u1, a1 = self._persist_turn(user="Morning.", assistant="Go on.")
        self._link(a1, u1)
        trip_repository.trip_selected_day_set(self.trip_id, self.other_day_id)
        u2, a2 = self._persist_turn(user="Next day.", assistant="And then?")
        self._link(a2, u2)
        day1 = trip_repository.trip_day_conversation_items(
            self.trip_id, self.day_id)
        day2 = trip_repository.trip_day_conversation_items(
            self.trip_id, self.other_day_id)
        self.assertEqual([i["narrator_said"] for i in day1], ["Morning."])
        self.assertEqual([i["narrator_said"] for i in day2], ["Next day."])

    def test_calendar_counts_every_day_and_never_the_words(self):
        """The calendar shows that something happened on a day, never
        what was said."""
        self._start_trip(self.day_id)
        u1, a1 = self._persist_turn(user="SECRET-PHRASE", assistant="ok")
        self._link(a1, u1)
        resp = trips.trip_calendar(self.trip_id)
        self.assertTrue(resp["ok"])
        self.assertEqual(resp["live_state"], "active")
        self.assertEqual(resp["selected_day_id"], self.day_id)
        self.assertEqual(len(resp["days"]), len(self.days))
        by_id = {d["id"]: d for d in resp["days"]}
        self.assertEqual(by_id[self.day_id]["conversation_count"], 1)
        self.assertEqual(by_id[self.other_day_id]["conversation_count"], 0)
        self.assertNotIn("SECRET-PHRASE", repr(resp))

    # ── 6. the boundaries that must not move ──────────────────────────
    def test_linking_writes_nothing_but_the_link(self):
        """'no family-truth write caused by linking; no change to
        correction projection behavior.'

        Checked against every table in the database rather than a
        hand-kept list of family-truth tables, which would go stale.
        """
        self._start_trip(self.day_id)
        urow, arow = self._persist_turn()
        before = self._table_counts()
        self.assertEqual(self._link(arow, urow).status, "linked")
        self._assert_only_links_changed(before, self._table_counts())

    def test_placement_service_calls_no_truth_writer(self):
        """Structural, via AST — a substring check would pass on the
        docstring paragraph that names these very functions."""
        src = (_SERVER_CODE / "api" / "services"
               / "trip_placement.py").read_text(encoding="utf-8")
        called = set()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Name):
                    called.add(fn.id)
                elif isinstance(fn, ast.Attribute):
                    called.add(fn.attr)
        for forbidden in ("ft_add_note", "ft_add_row", "ft_upsert",
                          "apply_correction", "archive_append_event",
                          "extract_fields", "run_field_extraction"):
            self.assertNotIn(forbidden, called)

    def test_placement_never_learns_the_browsers_field_names(self):
        """`runtime71` dies on reload and on restart, and this module
        still never names it.

        AMENDED 2026-07-31, WO-TRIP-NARRATOR-BRIDGE-01. This test used
        to also forbid the string `active_trip_id`, and that clause has
        been dropped rather than worked around, because the module now
        legitimately reads that key off a `shelf_scope` argument the
        caller assembles. Dropping it costs something real, so the
        property it was standing in for is asserted directly in the
        three behavioural tests below: Priority 1 wins when it has an
        answer, a shelf id is re-read from the database before use, and
        a shelf trip belonging to someone else is refused.

        What survives verbatim is the part that still holds. The word
        `runtime71` must not appear in executable code here: the caller
        unwraps it, so this service has no opinion about what the
        browser calls things and cannot drift from it.

        Docstrings are excluded on purpose. The module explains this
        exact gap in its own prose, and a test that cannot tell an
        explanation from a read would forbid the module from saying
        why it exists.
        """
        src = (_SERVER_CODE / "api" / "services"
               / "trip_placement.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in _executable_string_constants(tree):
            self.assertNotIn("runtime71", node)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                self.assertNotEqual(node.attr, "runtime71")

    # ── 7. failure isolation ──────────────────────────────────────────
    def test_a_broken_link_never_costs_the_conversation(self):
        """'A failure to link the trip should not lose the
        conversation.' Proved with the harness-only seam rather than by
        corrupting production configuration."""
        self._start_trip(self.day_id)
        urow, arow = self._persist_turn(user="Still here.", assistant="Yes.")
        os.environ["HORNELORE_TRIP_LINK_FORCE_FAILURE"] = "raise"
        try:
            out = self._link(arow, urow)
        finally:
            os.environ.pop("HORNELORE_TRIP_LINK_FORCE_FAILURE", None)
        self.assertEqual(out.status, "failed")
        self.assertFalse(out.ok)
        self.assertEqual(out.error_class, "ForcedPlacementFailure")
        # The turn itself is untouched.
        con = sqlite3.connect(str(self.db_path))
        try:
            got = con.execute("SELECT content FROM turns WHERE id=?;",
                              (urow,)).fetchone()
        finally:
            con.close()
        self.assertEqual(got[0], "Still here.")
        self.assertEqual(
            trip_repository.trip_turn_links_list(self.trip_id), [])

    def test_outcome_log_fields_carry_no_narrative_text(self):
        self._start_trip(self.day_id)
        urow, arow = self._persist_turn(
            user="PRIVATE-NARRATIVE", assistant="PRIVATE-REPLY")
        line = self._link(arow, urow).as_log_fields()
        self.assertNotIn("PRIVATE-NARRATIVE", line)
        self.assertNotIn("PRIVATE-REPLY", line)
        self.assertIn("outcome=linked", line)
        self.assertIn("event=trip_link_linked", line)

    def test_an_unmigrated_database_degrades_to_no_active_trip(self):
        """An interview turn must not fail because the trip lane is
        unreadable."""
        con = sqlite3.connect(str(self.db_path))
        con.execute("DROP TABLE trip_turn_links;")
        con.commit()
        con.close()
        trip_repository.trip_live_state_set(self.trip_id, "active")
        trip_repository.trip_selected_day_set(self.trip_id, self.day_id)
        urow, arow = self._persist_turn()
        out = self._link(arow, urow)
        self.assertIn(out.status, ("failed", "noop"))
        self.assertFalse(out.linked)

    # ── 8. restart persistence, at the data layer ─────────────────────
    def test_the_link_and_the_active_trip_survive_a_reconnect(self):
        """The browser-state version of this could not survive a
        reload. This resolves from the database on every call, so a
        fresh connection sees the same answer.

        The live acceptance run proves the same property through an
        actual server restart; this is its unit-level guard.
        """
        self._start_trip(self.day_id)
        urow, arow = self._persist_turn()
        out = self._link(arow, urow)
        self.assertEqual(out.status, "linked")
        # Nothing cached: every accessor opens and closes its own
        # connection, so re-resolving is exactly what a restart does.
        resolved = trip_placement.resolve_placement(self.person_id)
        self.assertEqual(resolved["trip"]["id"], self.trip_id)
        self.assertEqual(resolved["day"]["id"], self.day_id)
        items = trip_repository.trip_day_conversation_items(
            self.trip_id, self.day_id)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["link_id"], out.link_id)

    # ── 9. the routes ─────────────────────────────────────────────────
    def test_routes_round_trip_the_workflow(self):
        """select trip -> mark active -> select day -> link -> calendar
        -> timeline, through the HTTP handlers."""
        self.assertTrue(
            trips.set_trip_live_state(
                self.trip_id, _Body(state="active"))["ok"])
        self.assertTrue(
            trips.set_trip_selected_day(
                self.trip_id, _Body(trip_day_id=self.day_id))["ok"])
        active = trips.get_active_trip(person_id=self.person_id)
        self.assertEqual(active["trip"]["id"], self.trip_id)
        self.assertEqual(active["day"]["id"], self.day_id)

        urow, arow = self._persist_turn(user="Route path.", assistant="Mm.")
        out = self._link(arow, urow)
        self.assertEqual(out.status, "linked")

        tl = trips.trip_day_timeline(self.trip_id, self.day_id)
        self.assertEqual(tl["count"], 1)
        self.assertEqual(tl["items"][0]["narrator_said"], "Route path.")

        moved = trips.move_trip_turn_link(
            out.link_id, _Body(trip_day_id=None))
        self.assertEqual(moved["link"]["placement_status"], "needs_day")
        self.assertEqual(
            trips.trip_unplaced_timeline(self.trip_id)["count"], 1)
        self.assertEqual(
            trips.trip_day_timeline(self.trip_id, self.day_id)["count"], 0)

    def test_route_rejects_an_unknown_live_state(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.set_trip_live_state(self.trip_id, _Body(state="on_holiday"))
        self.assertEqual(ctx.exception.status_code, 422)

    def test_route_reports_the_active_trip_conflict_as_409(self):
        trips.set_trip_live_state(self.trip_id, _Body(state="active"))
        second = trip_repository.trip_create(
            person_id=self.person_id, title="Second", start_date="2026-09-01",
            end_date="2026-09-02", summary="")
        with self.assertRaises(HTTPException) as ctx:
            trips.set_trip_live_state(second, _Body(state="active"))
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(
            ctx.exception.detail["conflict"]["id"], self.trip_id)

    def test_active_route_is_calm_when_nothing_is_running(self):
        resp = trips.get_active_trip(person_id=self.person_id)
        self.assertTrue(resp["ok"])
        self.assertIsNone(resp["trip"])
        self.assertEqual(resp["reason"], "no_active_trip")



class TravelsShelfPlacementCase(_PlacementCase):
    """WO-TRIP-NARRATOR-BRIDGE-01, Priority 2.

    THE GAP. A COMPLETED trip has live_state != 'active', so
    trip_active_get() returns None and link_completed_turn() answered
    noop/no_active_trip for every turn about it. That is not a bug in
    the placement rule -- the rule is correct for a live trip -- it is a
    scope the rule never had. A man opened the Bismarck trip on the
    Travels shelf and told the story of visiting his mother\u2019s parents\u2019
    gravesite, his elementary school, two middle schools, a high school
    and a junior college, with his wife Melanie. The turn persisted. The
    conversation was never lost. It was also never attached to anything,
    which from the operator\u2019s chair is the same as gone.

    THE DANGER IN FIXING IT is that the fix reaches for the browser. So
    these tests are mostly about what the shelf path REFUSES: it refuses
    to run by default, it refuses to outrank the database, it refuses an
    id it has not re-read, it refuses another person\u2019s trip, it refuses
    to invent a day, and it refuses to make a finished trip live again.
    """

    def setUp(self):
        super().setUp()
        self._orig_shelf = os.environ.get("HORNELORE_TRIP_SHELF_TURN_LINK")
        os.environ["HORNELORE_TRIP_SHELF_TURN_LINK"] = "1"

    def tearDown(self):
        if self._orig_shelf is None:
            os.environ.pop("HORNELORE_TRIP_SHELF_TURN_LINK", None)
        else:
            os.environ["HORNELORE_TRIP_SHELF_TURN_LINK"] = self._orig_shelf
        super().tearDown()

    def _link_shelf(self, arow, urow=None, trip_id=None, open_=True,
                    conv_id="conv-shelf", scope="__default__"):
        if scope == "__default__":
            scope = {"travels_shelf_open": open_,
                     "active_trip_id": trip_id or self.trip_id}
        return trip_placement.link_completed_turn(
            narrator_id=self.person_id,
            assistant_turn_row_id=arow,
            user_turn_row_id=urow,
            conv_id=conv_id,
            turn_id="t-" + str(arow),
            turn_mode="interview",
            source="chat_ws",
            shelf_scope=scope)

    # ── the gap itself ────────────────────────────────────────────────
    def test_a_completed_trip_on_the_shelf_now_receives_the_turn(self):
        # live_state is left completed on purpose. This is the case that
        # used to vanish.
        trip_repository.trip_live_state_set(self.trip_id, "completed")
        urow, arow = self._persist_turn(
            user="I visited my mom's parents' gravesite, and my old "
                 "elementary school, with my wife Melanie.",
            assistant="What did the school look like from outside?")
        out = self._link_shelf(arow, urow)
        self.assertEqual(out.status, "needs_day")
        self.assertEqual(out.trip_id, self.trip_id)
        self.assertEqual(out.placement_source, "travels_shelf_trip")
        self.assertEqual(out.placement_status, "needs_day")
        self.assertEqual(out.trip_day_id, "")

    def test_it_surfaces_in_the_operators_needs_a_day_list(self):
        """A link nobody can see is not a fix."""
        trip_repository.trip_live_state_set(self.trip_id, "completed")
        urow, arow = self._persist_turn(user="Melanie came with me.",
                                        assistant="Tell me about her.")
        self._link_shelf(arow, urow)
        items = trip_repository.trip_day_conversation_items(self.trip_id, None)
        self.assertEqual(len(items), 1)

    def test_the_source_word_survives_the_repository_whitelist(self):
        """trip_turn_link_claim silently rewrites an unrecognized source
        to 'active_trip_day'. If 'travels_shelf_trip' were missing from
        PLACEMENT_SOURCES the row would claim the narrator was live on
        the trip that day -- a forgery produced by a typo guard."""
        self.assertIn("travels_shelf_trip", trip_repository.PLACEMENT_SOURCES)
        trip_repository.trip_live_state_set(self.trip_id, "completed")
        urow, arow = self._persist_turn(user="a", assistant="b")
        self._link_shelf(arow, urow)
        con = sqlite3.connect(str(self.db_path))
        try:
            src = con.execute(
                "SELECT placement_source FROM trip_turn_links "
                "WHERE trip_id=?;", (self.trip_id,)).fetchone()[0]
        finally:
            con.close()
        self.assertEqual(src, "travels_shelf_trip")

    # ── everything it refuses ─────────────────────────────────────────
    def test_it_is_off_by_default(self):
        os.environ.pop("HORNELORE_TRIP_SHELF_TURN_LINK", None)
        trip_repository.trip_live_state_set(self.trip_id, "completed")
        urow, arow = self._persist_turn(user="a", assistant="b")
        out = self._link_shelf(arow, urow)
        self.assertEqual(out.status, "noop")
        self.assertEqual(out.reason, "no_active_trip")

    def test_the_database_outranks_the_shelf(self):
        """The accepted VS1 path is tried first on every turn. A stale
        browser payload naming another trip must not redirect a turn
        away from the trip the database says he is living in."""
        other = trip_repository.trip_create(
            person_id=self.person_id, title="Some other trip",
            start_date="2026-09-01", end_date="2026-09-02")
        self._start_trip(self.day_id)
        urow, arow = self._persist_turn(user="a", assistant="b")
        out = self._link_shelf(arow, urow, trip_id=other)
        self.assertEqual(out.status, "linked")
        self.assertEqual(out.trip_id, self.trip_id)
        self.assertEqual(out.trip_day_id, self.day_id)
        self.assertEqual(out.placement_source, "active_trip_day")

    def test_another_persons_trip_is_refused(self):
        """A well-formed id from the wrong journey. This is the check
        that makes the fallback safe to switch on at all."""
        stranger = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO people (id, display_name, date_of_birth, "
            "created_at, updated_at) VALUES (?, 'Someone Else', "
            "'1949-01-01', '2026-07-31', '2026-07-31');", (stranger,))
        con.commit()
        con.close()
        theirs = trip_repository.trip_create(
            person_id=stranger, title="Not his trip",
            start_date="2026-09-01", end_date="2026-09-02")
        urow, arow = self._persist_turn(user="a", assistant="b")
        out = self._link_shelf(arow, urow, trip_id=theirs)
        self.assertEqual(out.status, "noop")
        self.assertEqual(out.reason, "shelf_trip_not_owned")
        self.assertEqual(self._table_counts().get("trip_turn_links"), 0)

    def test_an_id_for_a_trip_that_does_not_exist_is_refused(self):
        urow, arow = self._persist_turn(user="a", assistant="b")
        out = self._link_shelf(arow, urow, trip_id=str(uuid.uuid4()))
        self.assertEqual(out.status, "noop")
        self.assertEqual(out.reason, "shelf_trip_missing")

    def test_a_closed_shelf_is_not_a_choice(self):
        """An active_trip_id left over in a stale payload is not a man
        opening a trip."""
        urow, arow = self._persist_turn(user="a", assistant="b")
        out = self._link_shelf(arow, urow, open_=False)
        self.assertEqual(out.status, "noop")
        self.assertEqual(out.reason, "shelf_closed")

    def test_a_malformed_scope_is_refused_not_repaired(self):
        """The 'str' object has no attribute 'get' family. A string is
        not half a scope, and inventing a trip id from one would file a
        conversation against a trip nobody chose."""
        for bad in ("trip", ["trip"], 7):
            urow, arow = self._persist_turn(
                user="a" + str(bad), assistant="b")
            out = self._link_shelf(arow, urow, scope=bad)
            self.assertEqual(out.status, "noop", repr(bad))
            self.assertEqual(out.reason, "malformed_shelf_scope", repr(bad))

    def test_it_never_infers_a_day(self):
        """Not from the trip's dates, not from stop order, not from the
        transcript, not from today. The trip has three generated days
        and the link gets none of them."""
        trip_repository.trip_live_state_set(self.trip_id, "completed")
        urow, arow = self._persist_turn(user="a", assistant="b")
        out = self._link_shelf(arow, urow)
        self.assertEqual(out.trip_day_id, "")
        con = sqlite3.connect(str(self.db_path))
        try:
            day = con.execute(
                "SELECT trip_day_id FROM trip_turn_links "
                "WHERE trip_id=?;", (self.trip_id,)).fetchone()[0]
        finally:
            con.close()
        self.assertIsNone(day)

    def test_it_does_not_make_a_finished_trip_live_again(self):
        """Opening a historical trip to talk about it is not resuming
        it. live_state is the operator's word."""
        trip_repository.trip_live_state_set(self.trip_id, "completed")
        urow, arow = self._persist_turn(user="a", assistant="b")
        self._link_shelf(arow, urow)
        self.assertEqual(
            trip_repository.trip_get(self.trip_id).get("live_state"),
            "completed")
        self.assertIsNone(trip_repository.trip_active_get(self.person_id))

    def test_a_replayed_turn_does_not_create_a_second_link(self):
        """Idempotency is keyed to the committed assistant row, so a
        reconnect that replays the same turn is a duplicate, and a
        duplicate never overwrites a placement an operator has moved."""
        trip_repository.trip_live_state_set(self.trip_id, "completed")
        urow, arow = self._persist_turn(user="a", assistant="b")
        first = self._link_shelf(arow, urow)
        second = self._link_shelf(arow, urow)
        self.assertEqual(first.status, "needs_day")
        self.assertEqual(second.status, "duplicate")
        self.assertEqual(self._table_counts().get("trip_turn_links"), 1)

    def test_the_shelf_path_writes_only_the_link_table(self):
        """Same guarantee as Priority 1: no family truth, no
        projection, nothing but trip_turn_links moves."""
        trip_repository.trip_live_state_set(self.trip_id, "completed")
        urow, arow = self._persist_turn(user="a", assistant="b")
        before = self._table_counts()
        self._link_shelf(arow, urow)
        self._assert_only_links_changed(before, self._table_counts())

    def test_an_ineligible_mode_is_still_ineligible_on_the_shelf(self):
        trip_repository.trip_live_state_set(self.trip_id, "completed")
        urow, arow = self._persist_turn(user="a", assistant="b")
        out = trip_placement.link_completed_turn(
            narrator_id=self.person_id, assistant_turn_row_id=arow,
            user_turn_row_id=urow, conv_id="c", turn_id="t",
            turn_mode="correction", source="chat_ws",
            shelf_scope={"travels_shelf_open": True,
                         "active_trip_id": self.trip_id})
        self.assertEqual(out.status, "noop")
        self.assertEqual(out.reason, "ineligible_turn_mode")


class SystemDirectiveIsNotNarratorSpeechCase(_PlacementCase):
    """BUG-TRIP-SYSTEM-DIRECTIVE-PLACED-AS-NARRATOR-TURN-01 (live).

    ui/js/session-loop.js feeds Lori in-band guidance by sending
    `[SYSTEM: ...]` as a USER-role WS payload. It carries
    turn_mode='interview', it persists an ordinary `turns` row, and
    every precondition placement had said yes to it.

    On 2026-07-31 that put three directives on the Bismarck Trip --
    740, 541 and 541 characters -- and because the timeline reads
    narrator text back out of `turns` by row id, the operator's own
    instructions were displayed as the narrator's words. Of the four
    conversations the acceptance run counted as "narrator interactions
    persisted", exactly one was a narrator.

    Nothing downstream could have caught it. The link table holds
    identifiers only, so every row was structurally perfect. The turn
    was simply never his.
    """

    def _link_directive(self, arow, urow=None, directive=True):
        return trip_placement.link_completed_turn(
            narrator_id=self.person_id,
            assistant_turn_row_id=arow,
            user_turn_row_id=urow,
            conv_id="conv-directive",
            turn_id="t-" + str(arow),
            turn_mode="interview",
            source="chat_ws",
            is_system_directive=directive)

    def test_a_system_directive_is_not_placed_on_a_live_trip(self):
        trip_repository.trip_live_state_set(self.trip_id, "active")
        urow, arow = self._persist_turn(
            user="[SYSTEM: The narrator has opened the Bismarck Trip. "
                 "Greet them warmly and ask one question about it.]",
            assistant="What stands out from that trip?")
        out = self._link_directive(arow, urow)
        self.assertEqual(out.status, "noop")
        self.assertEqual(out.reason, "system_directive")
        self.assertEqual(out.link_id, "")

    def test_it_writes_no_link_row_at_all(self):
        """A noop that still wrote would be the whole bug again."""
        trip_repository.trip_live_state_set(self.trip_id, "active")
        before = self._table_counts().get("trip_turn_links", 0)
        urow, arow = self._persist_turn(
            user="[SYSTEM: continue the interview]",
            assistant="Go on.")
        self._link_directive(arow, urow)
        self.assertEqual(self._table_counts().get("trip_turn_links", 0),
                         before)

    def test_the_same_turn_links_when_the_narrator_authored_it(self):
        """The non-vacuity control. Without this, a gate that refused
        everything would look identical to a gate that works."""
        trip_repository.trip_live_state_set(self.trip_id, "active")
        urow, arow = self._persist_turn(
            user="We drove out to the cemetery on the second morning.",
            assistant="What was the weather like?")
        out = self._link_directive(arow, urow, directive=False)
        self.assertIn(out.status, ("linked", "needs_day"))
        self.assertNotEqual(out.link_id, "")

    def test_the_refusal_outranks_the_shelf_fallback_too(self):
        """Priority 2 must not become a second door for a directive.
        The shelf path is reached only after the database says no, so a
        gate placed after it would have let every completed-trip
        directive straight through -- which is exactly the shape the
        live failure took."""
        os.environ["HORNELORE_TRIP_SHELF_TURN_LINK"] = "1"
        try:
            trip_repository.trip_live_state_set(self.trip_id, "completed")
            urow, arow = self._persist_turn(
                user="[SYSTEM: The narrator opened a trip from Travels.]",
                assistant="Tell me about it.")
            out = trip_placement.link_completed_turn(
                narrator_id=self.person_id,
                assistant_turn_row_id=arow,
                user_turn_row_id=urow,
                conv_id="conv-directive",
                turn_id="t-" + str(arow),
                turn_mode="interview",
                source="chat_ws",
                is_system_directive=True,
                shelf_scope={"travels_shelf_open": True,
                             "active_trip_id": self.trip_id})
            self.assertEqual(out.status, "noop")
            self.assertEqual(out.reason, "system_directive")
        finally:
            os.environ.pop("HORNELORE_TRIP_SHELF_TURN_LINK", None)

    def test_the_default_is_false_so_no_caller_is_silently_changed(self):
        """Every existing caller omits the argument. If it defaulted to
        True, placement would stop entirely and every suite above would
        fail -- but a reader deserves the guarantee stated once."""
        import inspect
        sig = inspect.signature(trip_placement.link_completed_turn)
        self.assertIs(sig.parameters["is_system_directive"].default, False)

    def test_the_service_is_not_given_the_text_to_judge(self):
        """It receives a boolean the boundary already computed. A
        service that sniffed transcripts would be a second place for
        'what counts as a directive' to drift from the first."""
        import inspect
        names = set(inspect.signature(
            trip_placement.link_completed_turn).parameters)
        for forbidden in ("user_text", "narrator_text", "message",
                          "transcript", "text"):
            self.assertNotIn(forbidden, names)


class _ChatWsHookCase(unittest.TestCase):
    """The hook is glue; these assertions are about where it sits."""

    def setUp(self):
        self.src = (_SERVER_CODE / "api" / "routers"
                    / "chat_ws.py").read_text(encoding="utf-8")
        self.tree = ast.parse(self.src)

    def _find(self, name):
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and node.name == name:
                return node
        return None

    def test_the_hook_exists_and_is_async(self):
        node = self._find("_run_completed_turn_trip_link")
        self.assertIsNotNone(node)
        self.assertIsInstance(node, ast.AsyncFunctionDef)

    def test_the_hook_runs_after_extraction_in_the_same_try(self):
        """Extraction is the older load-bearing path; a placement bug
        must not be able to delay or displace it."""
        # Locate the two awaits by source order.
        extract_at = self.src.find(
            "await _run_completed_turn_extraction(conv_id, user_text, "
            "params, ev)")
        link_at = self.src.find(
            "await _run_completed_turn_trip_link(conv_id, params, ev)")
        self.assertGreater(extract_at, 0)
        self.assertGreater(link_at, extract_at)

    def test_the_boundary_hands_the_service_the_directive_verdict(self):
        """BUG-TRIP-SYSTEM-DIRECTIVE-PLACED-AS-NARRATOR-TURN-01.

        The service gate is inert unless the boundary passes the flag,
        and the boundary is the only place that can: `user_text` is a
        sibling of `params` in the WS payload, so the hook -- which
        receives params alone -- cannot see the text at all. Two halves,
        both asserted, because either one alone silently does nothing.
        """
        # Half one: the verdict is recorded where it is computed.
        self.assertIn('params["_is_system_directive"] = _is_system_directive',
                      self.src)
        # Half two: the hook forwards it.
        node = self._find("_run_completed_turn_trip_link")
        self.assertIsNotNone(node)
        body = ast.get_source_segment(self.src, node) or ""
        self.assertIn("is_system_directive=", body)
        self.assertIn("_is_system_directive", body)

    def test_the_directive_test_is_the_one_the_capture_lane_uses(self):
        """One definition of 'this is a directive', not two drifting
        apart. The story-capture lane has refused these since 2026-04-30
        on the same test; placement now reads that same verdict rather
        than re-deriving it.

        NARROWED 2026-08-09 by WO-SYSTEM-DIRECTIVE-PERSISTENCE-01 Phase
        1b, and the property it protects is unchanged: there is still
        exactly ONE place where the question is answered, and placement
        still reads that answer rather than forming its own.

        What changed is the answer's SOURCE. It read:

            _is_system_directive = _ut_lstrip.startswith("[SYSTEM")

        and asserted that line appears exactly once. The prefix test is
        now the FALLBACK inside a branch that prefers `params
        ["message_kind"]`, because persisting a prefix-derived guess
        would have made it durable -- and a narrator who types
        "[SYSTEM: ..." must stay narrator speech.

        Two mechanical corrections came with it. The count is taken over
        COMMENT-STRIPPED source, because the retirement note above the
        new code quotes the retired line verbatim, per this repository's
        correct-in-place rule -- the sixth time in one day that a guard
        has fired on prose quoting the thing it guards. And the
        single-definition claim is now made about the ASSIGNMENT to
        `_is_system_directive`, which is the thing that must not
        proliferate, rather than about one particular right-hand side.
        """
        from source_scan_helpers import strip_py_comments
        code = strip_py_comments(self.src)
        # The declared kind is preferred; the prefix survives as fallback.
        self.assertIn('params . get ( "message_kind" )'.replace(" ", ""),
                      code.replace(" ", ""))
        self.assertIn('_ut_lstrip.startswith("[SYSTEM")'.replace(" ", ""),
                      code.replace(" ", ""))
        # Still answered in exactly one place: two assignments, both
        # inside the single if/else that resolves it, and nowhere else.
        self.assertEqual(
            2, code.replace(" ", "").count("_is_system_directive="),
            "the directive verdict is being formed in more than the one "
            "if/else that resolves it")

    def test_the_hook_is_not_given_the_narrator_text_to_sniff(self):
        """The hook takes (conv_id, params, ev). Adding user_text to it
        would let placement grow its own opinion about what a directive
        is -- the drift the test above exists to prevent."""
        node = self._find("_run_completed_turn_trip_link")
        args = [a.arg for a in node.args.args]
        self.assertEqual(args, ["conv_id", "params", "ev"])

    def test_the_hook_writes_no_truth_and_touches_no_projection(self):
        node = self._find("_run_completed_turn_trip_link")
        called = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                fn = sub.func
                if isinstance(fn, ast.Name):
                    called.add(fn.id)
                elif isinstance(fn, ast.Attribute):
                    called.add(fn.attr)
        for forbidden in ("ft_add_note", "ft_add_row", "apply_correction",
                          "archive_append_event", "persist_turn_transaction"):
            self.assertNotIn(forbidden, called)

    def test_the_hook_reads_runtime71_only_to_build_a_shelf_scope(self):
        """AMENDED 2026-07-31, WO-TRIP-NARRATOR-BRIDGE-01. The hook now
        does read runtime71, so the old blanket ban is gone. What
        replaces it is narrower and says the thing that actually
        matters: the browser value may become a `shelf_scope` argument
        and nothing else.

        In particular the hook must never hand `_link_turn` a trip_id
        or a trip_day_id. If it could, the browser would be choosing
        the trip directly and the database re-read on the other side
        would be decoration."""
        node = self._find("_run_completed_turn_trip_link")
        call = None
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) \
                    and sub.func.id == "_link_turn":
                call = sub
        self.assertIsNotNone(call, "the hook no longer calls _link_turn")
        kwargs = {k.arg for k in call.keywords}
        self.assertIn("shelf_scope", kwargs)
        for forbidden in ("trip_id", "trip_day_id", "placement_source",
                          "placement_status"):
            self.assertNotIn(forbidden, kwargs)

    def test_the_hook_guards_the_shape_of_runtime71_before_reading_it(self):
        """(x or {}).get() guards None and nothing else. A string
        runtime71 would raise 'str' object has no attribute 'get'
        inside a hook whose entire contract is that it cannot disturb
        a delivered turn."""
        src = ast.get_source_segment(
            self.src, self._find("_run_completed_turn_trip_link")) or ""
        self.assertIn("isinstance(_rt71_shelf, dict)", src)
        self.assertNotIn('(params.get("runtime71") or {}).get', src)

    def test_the_hook_cannot_swallow_cancellation(self):
        node = self._find("_run_completed_turn_trip_link")
        reraises = False
        for sub in ast.walk(node):
            if isinstance(sub, ast.ExceptHandler):
                t = sub.type
                name = getattr(getattr(t, "attr", None), "__str__", None)
                label = (t.attr if isinstance(t, ast.Attribute)
                         else getattr(t, "id", ""))
                del name
                if label == "CancelledError":
                    reraises = any(isinstance(s, ast.Raise)
                                   for s in ast.walk(sub))
        self.assertTrue(reraises)

    def test_the_user_row_id_is_captured_not_computed(self):
        """Deriving it as assistant_row_id - 1 would be right almost
        always and silently wrong the rest of the time — attributing one
        narrator's words to another narrator's turn."""
        self.assertIn("_persisted_user_turn_row_id", self.src)
        self.assertIn("row_ids_out=_persisted_row_ids", self.src)
        self.assertNotIn("_persisted_turn_row_id - 1", self.src)


class _ModalSurfaceEligibilityCase(unittest.TestCase):
    """The defect the first live acceptance run bought, 2026-07-30.

    Phase 1 of the live run passed eleven checks and failed the twelfth:
    a real interview turn completed through /api/chat/ws with the Travel
    Doc pane's exact payload, both turn rows committed with the right
    text, and no link row appeared. The API log named the cause on one
    line — the hook skipped because "required archive event not
    persisted for this turn".

    `_run_completed_turn_trip_link` had copied its precondition from
    `_run_completed_turn_extraction`, which requires
    `params["_archive_event_persisted"]`. That flag is only ever set
    inside the archive branch, and the archive branch is deliberately
    skipped when `surface == "travel_doc_modal"`
    (BUG-MODAL-TURNS-ARCHIVED-AS-LIFE-STORY-01 — modal talk is kept out
    of the narrator's life story on purpose). So the gate made every
    Travel Doc turn ineligible for the trip timeline: the one surface
    this slice exists to serve was the one surface it could never work
    on, and it failed as a silent skip on the happy path.

    These assertions exist so that a later reader who notices the two
    hooks disagree cannot "restore symmetry" without a red test.
    """

    def setUp(self):
        self.src = (_SERVER_CODE / "api" / "routers"
                    / "chat_ws.py").read_text(encoding="utf-8")
        self.tree = ast.parse(self.src)

    def _hook(self):
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and node.name == "_run_completed_turn_trip_link":
                return node
        return None

    @staticmethod
    def _param_keys_read(node):
        """Every literal key fetched off `params` inside the function."""
        keys = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) \
                    and isinstance(sub.func, ast.Attribute) \
                    and sub.func.attr == "get" \
                    and isinstance(sub.func.value, ast.Name) \
                    and sub.func.value.id == "params" \
                    and sub.args \
                    and isinstance(sub.args[0], ast.Constant):
                keys.add(sub.args[0].value)
            if isinstance(sub, ast.Subscript) \
                    and isinstance(sub.value, ast.Name) \
                    and sub.value.id == "params" \
                    and isinstance(sub.slice, ast.Constant):
                keys.add(sub.slice.value)
        return keys

    def test_placement_does_not_require_an_archive_event(self):
        node = self._hook()
        self.assertIsNotNone(node)
        self.assertNotIn(
            "_archive_event_persisted", self._param_keys_read(node),
            "placement gated on the memoir archive again. A "
            "travel_doc_modal turn never writes one, by design, so this "
            "makes every Travel Doc conversation ineligible for its own "
            "trip timeline.")

    def test_placement_requires_the_committed_row_instead(self):
        """What placement actually needs is that the words are on disk,
        because the timeline reads them back out of `turns` by row id."""
        node = self._hook()
        self.assertIn("_persisted_turn_row_id", self._param_keys_read(node))

    def test_extraction_keeps_its_own_archive_gate(self):
        """The fix corrects placement only. Extraction reads the memoir
        archive, so an incomplete archive would make it read a
        half-written turn — its gate is right and stays."""
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and node.name == "_run_completed_turn_extraction":
                self.assertIn("_archive_event_persisted",
                              self._param_keys_read(node))
                return
        self.fail("_run_completed_turn_extraction not found")

    def test_the_modal_archive_skip_is_still_there(self):
        """If this ever stops being true the comment above is stale, and
        the reader deserves to be told by a failure rather than by a
        surprise."""
        self.assertIn("travel_doc_modal", self.src)
        self.assertIn("_skip_modal_archive", self.src)


class _DayTimelineProjectionCase(_PlacementCase):
    """The second half of the same live run: the modal opened, and the
    day it opened on reported that nothing had been recorded, while the
    Trip Plan card two inches away showed one photograph and one story
    note.

    /timeline projected `trip_turn_links` and nothing else. A timeline
    that can only see the newest table is not a timeline; it is a view
    of the newest table. It is now a read projection over everything
    already fastened to the day, and it owns no storage.
    """

    def _add_photo(self, day_id, taken_at="2026-08-01T09:30:00",
                   caption="The old bridge", hidden=0):
        photo_id = str(uuid.uuid4())
        link_id = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        try:
            # The photos table has grown a long tail of NOT NULL columns
            # over the life of the project, and a fixture that names
            # them one at a time becomes a maintenance tax that fails
            # the next time one is added. Fill whatever the schema says
            # is required and nothing else.
            info = list(con.execute("PRAGMA table_info(photos);"))
            fields, values = [], []
            preset = {
                "id": photo_id,
                "person_id": self.person_id,
                "narrator_id": self.person_id,
                "description": "fixture photo",
                "filename": "fixture.jpg",
                "image_path": "/secret/staging/fixture.jpg",
                "storage_path": "/secret/staging/fixture.jpg",
            }
            for row in info:
                name, ctype, notnull, default = row[1], row[2], row[3], row[4]
                if name in preset:
                    fields.append(name)
                    values.append(preset[name])
                elif notnull and default is None:
                    fields.append(name)
                    values.append(
                        0 if str(ctype).upper().startswith(("INT", "REAL",
                                                            "NUM"))
                        else "2026-07-30")
            con.execute(
                "INSERT INTO photos (" + ", ".join(fields) + ") VALUES ("
                + ", ".join("?" * len(fields)) + ");", values)
            con.execute(
                "INSERT INTO trip_photo_links (id, trip_id, photo_id, "
                "trip_day_id, ord, taken_at, caption, hidden, created_at, "
                "updated_at) VALUES (?, ?, ?, ?, 0, ?, ?, ?, "
                "'2026-07-30', '2026-07-30');",
                (link_id, self.trip_id, photo_id, day_id, taken_at,
                 caption, hidden))
            con.commit()
        finally:
            con.close()
        return photo_id, link_id

    def _add_note(self, day_id, title="The market", text="Cherries.",
                  hidden=0):
        note_id = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        try:
            con.execute(
                "INSERT INTO trip_location_notes (id, trip_id, trip_day_id, "
                "note_title, note_text, source_type, ord, hidden, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, "
                "'operator', 0, ?, '2026-08-01T10:00:00', '2026-07-30');",
                (note_id, self.trip_id, day_id, title, text, hidden))
            con.commit()
        finally:
            con.close()
        return note_id

    def _add_source(self, day_id, title="Ticket stub", hidden=0):
        source_id = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        try:
            con.execute(
                "INSERT INTO trip_sources (id, trip_id, trip_day_id, "
                "source_type, title, storage_path, filename, summary, "
                "source_date, ord, hidden, created_at, updated_at) VALUES "
                "(?, ?, ?, 'ticket', ?, '/secret/staging/x.pdf', "
                "'x.pdf', 'One stub.', '2026-08-01', 0, ?, "
                "'2026-07-30', '2026-07-30');",
                (source_id, self.trip_id, day_id, title, hidden))
            con.commit()
        finally:
            con.close()
        return source_id

    def _kinds(self, day_id=None):
        items = trip_repository.trip_day_timeline_items(
            self.trip_id, day_id or self.day_id)
        return [i["kind"] for i in items]

    def test_a_day_with_a_photo_and_a_note_is_not_empty(self):
        """The exact live symptom."""
        self._add_photo(self.day_id)
        self._add_note(self.day_id)
        kinds = self._kinds()
        self.assertIn("photo", kinds)
        self.assertIn("note", kinds)

    def test_the_conversation_still_appears_beside_them(self):
        self._start_trip(self.day_id)
        urow, arow = self._persist_turn()
        self._link(arow, urow)
        self._add_photo(self.day_id)
        self._add_note(self.day_id)
        self._add_source(self.day_id)
        kinds = self._kinds()
        for k in ("conversation", "photo", "note", "source"):
            self.assertIn(k, kinds)

    def test_the_projection_is_scoped_to_its_own_day(self):
        self._add_photo(self.day_id)
        self._add_note(self.other_day_id)
        self.assertIn("photo", self._kinds(self.day_id))
        self.assertNotIn("note", self._kinds(self.day_id))
        self.assertIn("note", self._kinds(self.other_day_id))
        self.assertNotIn("photo", self._kinds(self.other_day_id))

    def test_hidden_rows_do_not_read_as_present_evidence(self):
        """Honest-counts governs display. A retired photograph is not
        something that happened on the day."""
        self._add_photo(self.day_id, hidden=1)
        self._add_note(self.day_id, hidden=1)
        self._add_source(self.day_id, hidden=1)
        kinds = self._kinds()
        for k in ("photo", "note", "source"):
            self.assertNotIn(k, kinds)

    def test_no_storage_path_or_coordinate_crosses_the_boundary(self):
        """Chris's rule: no staging paths, provider references or hashes
        in the normal UI; and raw lat/lon are never projected."""
        self._add_photo(self.day_id)
        self._add_source(self.day_id)
        blob = repr(trip_repository.trip_day_timeline_items(
            self.trip_id, self.day_id))
        for leak in ("storage_path", "/secret/staging", "latitude",
                     "longitude", "filename"):
            self.assertNotIn(leak, blob)

    def test_the_projection_writes_nothing(self):
        """A read projection that writes is not a read projection."""
        self._add_photo(self.day_id)
        self._add_note(self.day_id)
        before = self._table_counts()
        trip_repository.trip_day_timeline_items(self.trip_id, self.day_id)
        trip_repository.trip_day_item_counts(self.trip_id)
        self.assertEqual(before, self._table_counts())

    def test_the_day_card_own_text_is_on_the_timeline(self):
        """A day whose only content is the operator's own morning note
        must not report itself empty either."""
        trip_repository.trip_day_update(
            self.day_id, morning_notes="Rain until ten.")
        items = trip_repository.trip_day_timeline_items(
            self.trip_id, self.day_id)
        texts = [i.get("text") for i in items if i["kind"] == "day_text"]
        self.assertIn("Rain until ten.", texts)

    def test_the_calendar_counts_what_each_day_holds(self):
        """The rail said "1 conversation" or nothing at all, so a day
        with a photograph and a note rendered as empty next to a day
        card that showed both."""
        self._add_photo(self.day_id)
        self._add_note(self.day_id)
        self._add_note(self.day_id, title="Second note")
        self._add_source(self.other_day_id)
        counts = trip_repository.trip_day_item_counts(self.trip_id)
        self.assertEqual(counts[self.day_id]["photos"], 1)
        self.assertEqual(counts[self.day_id]["notes"], 2)
        self.assertEqual(counts[self.day_id]["sources"], 0)
        self.assertEqual(counts[self.other_day_id]["sources"], 1)

    def test_counts_and_items_agree_about_hidden_rows(self):
        self._add_photo(self.day_id, hidden=1)
        counts = trip_repository.trip_day_item_counts(self.trip_id)
        self.assertEqual(counts[self.day_id]["photos"], 0)

    def test_the_timeline_still_reads_the_words_out_of_turns(self):
        """Unchanged requirement, re-asserted here because the merge
        rewrote the function that used to own it."""
        self._start_trip(self.day_id)
        urow, arow = self._persist_turn(
            user="We took the funicular up.", assistant="Who was with you?")
        self._link(arow, urow)
        items = [i for i in trip_repository.trip_day_timeline_items(
            self.trip_id, self.day_id) if i["kind"] == "conversation"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["narrator_said"], "We took the funicular up.")
        self.assertEqual(items[0]["lori_said"], "Who was with you?")


class ClaimRefusalCase(_PlacementCase):
    """WO-TRIP-NARRATOR-BRIDGE-01 -- the bug underneath the bug.

    Adding 'travels_shelf_trip' to PLACEMENT_SOURCES in Python did not
    make it legal in the database: 0039 wrote the four accepted words
    into a CHECK constraint. Every shelf placement was refused, and
    trip_turn_link_claim reported the refusal as outcome='duplicate',
    because it treated sqlite3.IntegrityError as proof of the UNIQUE
    index firing. A CHECK raises the same class. PlacementOutcome.linked
    reads 'duplicate' as "a link row now exists for this turn", so a
    turn that was attached to nothing would have been logged as
    already-handled -- the same disappearance the work order exists to
    end, one layer further down and harder to see.

    Migration 0040 removes the reason the constraint fires. These tests
    guard the other half: that a refusal, whatever causes the next one,
    is never again mistaken for success.
    """

    def _links_sql(self):
        con = sqlite3.connect(str(self.db_path))
        try:
            return con.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' "
                "AND name='trip_turn_links';").fetchone()[0]
        finally:
            con.close()

    def test_migration_0040_made_the_shelf_word_legal_in_the_schema(self):
        sql = self._links_sql()
        self.assertIn("travels_shelf_trip", sql)
        # The four 0039 words are still accepted. Widening a vocabulary
        # is not replacing one, and a row already placed by the active
        # trip path must not become unreadable.
        for word in ("active_trip_day", "operator_selected",
                     "timestamp_suggested", "later_reconciled"):
            self.assertIn(word, sql)

    def test_the_rebuild_put_the_idempotency_index_back(self):
        """A rebuild drops the old table's indexes with it. If the
        UNIQUE index on assistant_turn_row_id did not come back, one
        turn could be placed twice and nothing anywhere would say so."""
        con = sqlite3.connect(str(self.db_path))
        try:
            idx = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND tbl_name='trip_turn_links';")}
        finally:
            con.close()
        self.assertIn("ux_trip_turn_links_assistant_row", idx)
        for name in ("idx_trip_turn_links_trip", "idx_trip_turn_links_day",
                     "idx_trip_turn_links_conv"):
            self.assertIn(name, idx)

    def test_the_rebuilt_table_still_refuses_a_word_nobody_defined(self):
        """The CHECK is widened, not removed. A source the vocabulary
        does not contain must still be impossible to store, or the
        column stops being a classification and becomes free text."""
        self._start_trip(self.day_id)
        urow, arow = self._persist_turn()
        con = sqlite3.connect(str(self.db_path))
        try:
            con.execute("PRAGMA foreign_keys=ON;")
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute(
                    "INSERT INTO trip_turn_links(id, trip_id, trip_day_id, "
                    "conv_id, user_turn_row_id, assistant_turn_row_id, "
                    "captured_at, placement_source, placement_status, "
                    "created_at, updated_at) "
                    "VALUES('x', ?, ?, '', ?, ?, '', 'vibes', "
                    "'confirmed', 'now', 'now');",
                    (self.trip_id, self.day_id, urow, arow))
        finally:
            con.close()

    def test_a_refused_row_is_reported_as_rejected_not_duplicate(self):
        """A foreign key that does not resolve raises the same
        exception class as the idempotency index. The claim has to ask
        the database which of the two happened rather than assume."""
        urow, arow = self._persist_turn()
        claim = trip_repository.trip_turn_link_claim(
            trip_id=self.trip_id,
            assistant_turn_row_id=arow,
            trip_day_id="no-such-day-id",
            user_turn_row_id=urow,
            conv_id="conv-1")
        self.assertEqual(claim["outcome"], "rejected")
        self.assertIsNone(claim["link"])
        con = sqlite3.connect(str(self.db_path))
        try:
            self.assertEqual(
                con.execute(
                    "SELECT COUNT(*) FROM trip_turn_links;").fetchone()[0], 0)
        finally:
            con.close()

    def test_a_real_second_run_is_still_a_duplicate(self):
        """The other half of the same question. Re-reading for the row
        must not turn genuine idempotency into a failure."""
        self._start_trip(self.day_id)
        urow, arow = self._persist_turn()
        self.assertEqual(self._link(arow, urow).status, "linked")
        again = trip_repository.trip_turn_link_claim(
            trip_id=self.trip_id,
            assistant_turn_row_id=arow,
            trip_day_id=self.other_day_id,
            user_turn_row_id=urow,
            conv_id="conv-1")
        self.assertEqual(again["outcome"], "duplicate")
        # And it did not drag the placement to the day the replay named.
        self.assertEqual(again["link"]["trip_day_id"], self.day_id)

    def test_placement_calls_a_refusal_a_failure(self):
        """'failed' rather than 'noop', because noop is documented as
        normal and most turns being noop is expected. A turn the
        database refused to place is not one of those."""
        self._start_trip(self.day_id)
        urow, arow = self._persist_turn()
        orig = trip_repository.trip_turn_link_claim
        trip_repository.trip_turn_link_claim = \
            lambda **kw: {"outcome": "rejected", "link": None}
        try:
            out = self._link(arow, urow)
        finally:
            trip_repository.trip_turn_link_claim = orig
        self.assertEqual(out.status, "failed")
        self.assertEqual(out.reason, "claim_rejected")
        self.assertEqual(out.error_class, "IntegrityError")
        # The two properties that would have carried the old lie.
        self.assertFalse(out.linked)
        self.assertFalse(out.ok)


if __name__ == "__main__":
    unittest.main()
