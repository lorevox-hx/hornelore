"""WO-TRAVEL-DOC-UI-LAB-03 — trip-day date-range reconcile tests.

Covers: reconcile-preview detects missing in-range dates and
out-of-range day cards after the trip's start/end dates change;
preview is strictly read-only; add_missing creates ONLY the missing
in-range days and never overwrites operator-edited rows;
mark_out_of_range stamps reconcile_status (migration 0029) while every
out-of-range day card — and all its content — is preserved; and
drop_empty_out_of_range removes out-of-range cards that hold nothing
while refusing, and reporting, the ones that hold something.

[This docstring said "NOTHING in the reconcile lane deletes trip_days
rows, and no test here permits it" until 2026-07-28. Chris's Phase A
review asked for the rest of the shrinking-date rule — "remove empty
out-of-range days; refuse and clearly list out-of-range days containing
work" — so the line moved. What replaced it is narrower and harder: a
day card that holds anything is never deleted, by any flag. The tests
that held the old line were rewritten in place to hold the new one, not
removed.]

Offline fastapi/pydantic stub pattern (same as tests/test_trip_days.py).
"""
from __future__ import annotations

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

# The generator guard at the foot of this file reads the emptiness
# definition out of the JS rather than restating it. Same try/except
# shape as tests/test_travel_doc_lab.py: direct execution of this file
# has no `tests` package on the path.
try:
    from tests import travel_doc_surfaces as _tds
except ImportError:  # direct execution: python tests/test_...py
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import travel_doc_surfaces as _tds

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
        # 2026-07-27 (WO-POST-LORI-CLEANUP-AND-UNBLOCK-01, incidental):
        # a bare `pass` here satisfies `class X(BaseModel)` but not
        # `X(id=..., label=...)`. Whichever sibling test loaded FIRST
        # won the sys.modules race, so a suite that passed alone failed
        # in a batch run -- a test env making tests lie. Matches the
        # stub tests/test_memoir_trip_story_lane.py already ships.
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
from api.services import trip_repository  # noqa: E402
from api.routers import trips  # noqa: E402


class _ReconcileReq:
    """TripDaysReconcileReq stand-in."""

    def __init__(self, add_missing=False, mark_out_of_range=False,
                 drop_empty_out_of_range=False):
        self.add_missing = add_missing
        self.mark_out_of_range = mark_out_of_range
        self.drop_empty_out_of_range = drop_empty_out_of_range


def _sql_source(fn) -> str:
    """Upper-cased source of ``fn`` with comment lines removed.

    Comments go because every source-inspection guard in this repo that
    was written against a bare word has eventually fired on a comment
    explaining that word. Docstrings stay: they are indented prose, they
    do not contain SQL statement forms, and stripping them would need a
    parser to do safely.
    """
    import inspect
    return "\n".join(
        line for line in inspect.getsource(fn).split("\n")
        if not line.lstrip().startswith("#")
    ).upper()


class _ReconcileCase(unittest.TestCase):
    def setUp(self):
        self._tmpdb = tempfile.NamedTemporaryFile(suffix=".sqlite3",
                                                  delete=False)
        self._tmpdb.close()
        self.db_path = Path(self._tmpdb.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()
        self._orig_trips_flag = os.environ.get("HORNELORE_TRIPS")
        os.environ["HORNELORE_TRIPS"] = "1"
        self._orig_sync = trips.trip_timeline_bridge.sync_trip_to_life_record
        trips.trip_timeline_bridge.sync_trip_to_life_record = \
            lambda *a, **k: None

        self.person_id = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO people (id, display_name, date_of_birth, "
            "created_at, updated_at) VALUES (?, 'Reconcile Test', "
            "'1962-12-24', '2026-07-10', '2026-07-10');",
            (self.person_id,),
        )
        con.commit()
        con.close()
        self.trip_id = trip_repository.trip_create(
            person_id=self.person_id, title="Reconcile Trip",
            start_date="2026-05-01", end_date="2026-05-05",
            summary="reconcile fixture")
        trips.generate_trip_days(self.trip_id)
        self.days = trip_repository.trip_days_list(self.trip_id)

    def tearDown(self):
        trips.trip_timeline_bridge.sync_trip_to_life_record = self._orig_sync
        _db.DB_PATH = self._orig_db
        if self._orig_trips_flag is None:
            os.environ.pop("HORNELORE_TRIPS", None)
        else:
            os.environ["HORNELORE_TRIPS"] = self._orig_trips_flag
        try:
            self.db_path.unlink()
        except OSError:
            pass

    # ── helpers ───────────────────────────────────────────────────────

    def _dump_days(self):
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in con.execute(
                "SELECT * FROM trip_days WHERE trip_id = ? ORDER BY id",
                (self.trip_id,)).fetchall()]
        finally:
            con.close()


class ReconcilePreviewTest(_ReconcileCase):
    def test_clean_trip_previews_empty_diff(self):
        pv = trips.reconcile_preview_trip_days(self.trip_id)
        self.assertEqual(pv["trip_id"], self.trip_id)
        self.assertEqual(pv["trip_start_date"], "2026-05-01")
        self.assertEqual(pv["trip_end_date"], "2026-05-05")
        self.assertEqual(pv["existing_days"], 5)
        self.assertEqual(pv["missing_dates"], [])
        self.assertEqual(pv["out_of_range_days"], [])
        self.assertEqual(pv["duplicate_or_invalid_days"], [])

    def test_detects_missing_dates_after_dates_widen(self):
        trip_repository.trip_update(self.trip_id, end_date="2026-05-07")
        pv = trips.reconcile_preview_trip_days(self.trip_id)
        self.assertEqual(pv["missing_dates"], ["2026-05-06", "2026-05-07"])
        self.assertEqual(pv["out_of_range_days"], [])

    def test_detects_out_of_range_after_dates_shrink(self):
        trip_repository.trip_update(self.trip_id,
                                    start_date="2026-05-02",
                                    end_date="2026-05-04")
        pv = trips.reconcile_preview_trip_days(self.trip_id)
        self.assertEqual(pv["missing_dates"], [])
        oor = sorted(d["date"] for d in pv["out_of_range_days"])
        self.assertEqual(oor, ["2026-05-01", "2026-05-05"])

    def test_preview_is_strictly_read_only(self):
        trip_repository.trip_update(self.trip_id,
                                    start_date="2026-05-02",
                                    end_date="2026-05-07")
        before = self._dump_days()
        trips.reconcile_preview_trip_days(self.trip_id)
        trip_repository.trip_days_reconcile_preview(self.trip_id)
        self.assertEqual(before, self._dump_days(),
                         "reconcile-preview must never write")

    def test_no_date_window_reports_nothing(self):
        bare = trip_repository.trip_create(
            person_id=self.person_id, title="No Dates")
        pv = trips.reconcile_preview_trip_days(bare)
        self.assertEqual(pv["missing_dates"], [])
        self.assertEqual(pv["out_of_range_days"], [])
        self.assertIsNone(pv["trip_start_date"])

    def test_detects_invalid_day_date(self):
        con = sqlite3.connect(str(self.db_path))
        try:
            con.execute("UPDATE trip_days SET date = 'not-a-date' "
                        "WHERE id = ?", (self.days[2]["id"],))
            con.commit()
        finally:
            con.close()
        pv = trips.reconcile_preview_trip_days(self.trip_id)
        bad = [d["id"] for d in pv["duplicate_or_invalid_days"]]
        self.assertEqual(bad, [self.days[2]["id"]])
        # The unreadable-date row is reported, not touched.
        self.assertEqual(len(self._dump_days()), 5)

    def test_unknown_trip_404(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.reconcile_preview_trip_days("no-such-trip")
        self.assertEqual(ctx.exception.status_code, 404)


class ReconcileApplyTest(_ReconcileCase):
    def test_add_missing_creates_only_missing(self):
        trip_repository.trip_update(self.trip_id, end_date="2026-05-07")
        out = trips.reconcile_trip_days(self.trip_id,
                                        _ReconcileReq(add_missing=True))
        self.assertEqual(out["added"], 2)
        self.assertEqual(out["preview"]["missing_dates"], [])
        dates = [d["date"] for d in out["days"]]
        self.assertIn("2026-05-06", dates)
        self.assertIn("2026-05-07", dates)
        self.assertEqual(len(dates), 7)

    def test_add_missing_never_overwrites_operator_edits(self):
        trip_repository.trip_day_update(self.days[0]["id"],
                                        title="Arrival — operator edit",
                                        morning_notes="museum first thing")
        trip_repository.trip_update(self.trip_id, end_date="2026-05-06")
        trips.reconcile_trip_days(self.trip_id,
                                  _ReconcileReq(add_missing=True))
        kept = trip_repository.trip_day_get(self.days[0]["id"])
        self.assertEqual(kept["title"], "Arrival — operator edit")
        self.assertEqual(kept["morning_notes"], "museum first thing")

    def test_mark_out_of_range_sets_status_preserves_content(self):
        # Give the soon-to-be-outside day real content.
        trip_repository.trip_day_update(self.days[0]["id"],
                                        title="Precious first day",
                                        evening_notes="beer hall dinner")
        trip_repository.location_note_create(
            trip_id=self.trip_id, note_text="day-one story",
            source_type="operator", trip_day_id=self.days[0]["id"])
        trip_repository.trip_update(self.trip_id, start_date="2026-05-02")
        out = trips.reconcile_trip_days(
            self.trip_id, _ReconcileReq(mark_out_of_range=True))
        self.assertEqual(out["marked_out_of_range"], 1)
        kept = trip_repository.trip_day_get(self.days[0]["id"])
        self.assertIsNotNone(kept, "out-of-range day card must be kept")
        self.assertEqual(kept["reconcile_status"],
                         "out_of_range_acknowledged")
        self.assertEqual(kept["title"], "Precious first day")
        self.assertEqual(kept["evening_notes"], "beer hall dinner")
        notes = [n for n in trip_repository.location_notes_list(self.trip_id)
                 if n.get("trip_day_id") == self.days[0]["id"]]
        self.assertEqual(len(notes), 1, "day content must survive marking")

    def test_reconcile_without_the_drop_flag_deletes_nothing(self):
        """Every caller written before 2026-07-28 behaves as it did.

        [This was test_reconcile_never_deletes_day_rows, and it asserted
        that no combination of flags could remove a row. That stopped
        being the rule when drop_empty_out_of_range landed. The half of
        it that still holds is the default, and that is what it tests
        now: add and mark, together, on a window that moved in both
        directions, and not one row goes missing.]
        """
        ids_before = {d["id"] for d in self.days}
        trip_repository.trip_update(self.trip_id,
                                    start_date="2026-05-03",
                                    end_date="2026-05-09")
        out = trips.reconcile_trip_days(self.trip_id, _ReconcileReq(
            add_missing=True, mark_out_of_range=True))
        ids_after = {d["id"]
                     for d in trip_repository.trip_days_list(self.trip_id)}
        self.assertTrue(ids_before.issubset(ids_after),
                        "reconcile must not delete rows unless asked to")
        self.assertEqual(len(ids_after), 9)  # 5 original + 4 added
        self.assertEqual(out["dropped_empty_out_of_range"], 0)
        self.assertEqual(out["dropped_days"], [])

    def test_acknowledged_day_reactivates_when_back_in_range(self):
        trip_repository.trip_update(self.trip_id, start_date="2026-05-02")
        trips.reconcile_trip_days(self.trip_id,
                                  _ReconcileReq(mark_out_of_range=True))
        self.assertEqual(
            trip_repository.trip_day_get(self.days[0]["id"])
            ["reconcile_status"], "out_of_range_acknowledged")
        # Dates widen back out — the day is in range again.
        trip_repository.trip_update(self.trip_id, start_date="2026-05-01")
        out = trips.reconcile_trip_days(
            self.trip_id, _ReconcileReq(mark_out_of_range=True))
        self.assertEqual(out["reactivated"], 1)
        self.assertEqual(
            trip_repository.trip_day_get(self.days[0]["id"])
            ["reconcile_status"], "active")

    def test_reconcile_noop_flags_change_nothing(self):
        trip_repository.trip_update(self.trip_id, end_date="2026-05-07")
        before = self._dump_days()
        out = trips.reconcile_trip_days(self.trip_id, _ReconcileReq())
        self.assertEqual(out["added"], 0)
        self.assertEqual(out["marked_out_of_range"], 0)
        self.assertEqual(before, self._dump_days())

    def test_unknown_trip_404(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.reconcile_trip_days("no-such-trip",
                                      _ReconcileReq(add_missing=True))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_the_preview_still_writes_nothing(self):
        """The read-only half of the lane did not move.

        [Until 2026-07-28 this and the test below were one test,
        test_repository_reconcile_lane_has_no_delete, and it asserted
        that neither function's source contained the WORD "DELETE".
        That guard fired the moment the preview's docstring explained
        why the display counts are the wrong number to make a delete
        decision with — a guard written against a word firing on the
        documentation of that word. It is asserted against SQL statement
        forms now, over source with the comments stripped, which is also
        a stronger claim: the old version would have passed a preview
        that quietly issued an UPDATE.]
        """
        body = _sql_source(trip_repository.trip_days_reconcile_preview)
        for stmt in ("DELETE FROM", "INSERT INTO", "UPDATE TRIP",
                     "COMMIT()", "BEGIN IMMEDIATE"):
            self.assertNotIn(stmt, body,
                             "reconcile-preview must never write (%s)" % stmt)

    def test_the_only_delete_is_one_row_under_the_write_lock(self):
        """The shape of the delete, not merely its absence.

        A count of one matters as much as the guards around it: a second
        DELETE statement added later would almost certainly be the bulk
        one this design refuses to have, and it would not trip a test
        that only looked for guards near the first.
        """
        import inspect
        body = inspect.getsource(trip_repository.trip_days_reconcile)
        self.assertEqual(body.count("DELETE FROM trip_days"), 1)
        # By id, one row at a time. Never by date, never by window.
        self.assertIn('DELETE FROM trip_days WHERE id = ?', body)
        d = body.index("DELETE FROM trip_days")
        # The emptiness decision and the lock both come first, in the
        # same transaction. Reading "empty" outside the write lock and
        # deleting inside it is the race this ordering exists to close.
        self.assertLess(body.index("BEGIN IMMEDIATE"), d)
        self.assertLess(body.index("_day_attachment_counts"), d)
        self.assertLess(body.index("_day_is_empty"), d)

    def test_emptiness_is_not_measured_by_the_displayed_counts(self):
        """trip_day_counts is the generous number and would never be 0.

        It counts photos matched by taken-date and notes inherited
        through the day's stop or region, and trip_days_generate
        auto-fills trip_region_id. Deciding emptiness with it would ship
        a feature that never finds an empty card on any trip that has
        region-scoped notes.
        """
        import inspect
        body = inspect.getsource(trip_repository._day_is_empty)
        self.assertNotIn("trip_day_counts", body)
        # trip_region_id is generated, so it is not evidence of a person.
        own = inspect.getsource(trip_repository.day_own_content)
        self.assertNotIn("trip_region_id", own)
        self.assertIn("trip_stop_id", own)


class ReconcileDropTest(_ReconcileCase):
    """Chris's correction 2, 2026-07-28:

        Implement the complete shrinking-date rule: remove empty
        out-of-range days; refuse and clearly list out-of-range days
        containing work.
    """

    def _shrink(self):
        trip_repository.trip_update(self.trip_id, start_date="2026-05-02",
                                    end_date="2026-05-04")

    def test_empty_out_of_range_days_are_removed(self):
        self._shrink()
        out = trips.reconcile_trip_days(
            self.trip_id, _ReconcileReq(drop_empty_out_of_range=True))
        self.assertEqual(out["dropped_empty_out_of_range"], 2)
        self.assertEqual(
            sorted(d["date"] for d in out["dropped_days"]),
            ["2026-05-01", "2026-05-05"])
        self.assertEqual(out["kept_out_of_range"], [])
        dates = sorted(d["date"]
                       for d in trip_repository.trip_days_list(self.trip_id))
        self.assertEqual(dates, ["2026-05-02", "2026-05-03", "2026-05-04"])

    def test_a_day_with_typed_text_is_refused_and_named(self):
        trip_repository.trip_day_update(self.days[0]["id"],
                                        morning_notes="the drive up")
        self._shrink()
        out = trips.reconcile_trip_days(
            self.trip_id, _ReconcileReq(drop_empty_out_of_range=True))
        self.assertEqual(out["dropped_empty_out_of_range"], 1)
        self.assertEqual([d["date"] for d in out["dropped_days"]],
                         ["2026-05-05"])
        self.assertEqual([k["date"] for k in out["kept_out_of_range"]], [])
        kept = trip_repository.trip_day_get(self.days[0]["id"])
        self.assertIsNotNone(kept, "a day with work must survive")
        self.assertEqual(kept["morning_notes"], "the drive up")

    def test_a_day_with_an_attached_note_is_refused(self):
        trip_repository.location_note_create(
            trip_id=self.trip_id, note_text="day-one story",
            source_type="operator", trip_day_id=self.days[0]["id"])
        self._shrink()
        out = trips.reconcile_trip_days(
            self.trip_id, _ReconcileReq(drop_empty_out_of_range=True))
        self.assertIsNotNone(
            trip_repository.trip_day_get(self.days[0]["id"]),
            "a day holding an attached note must survive")
        self.assertNotIn(self.days[0]["date"],
                         [d["date"] for d in out["dropped_days"]])

    def test_the_preview_says_what_each_out_of_range_day_holds(self):
        """This is the half that lets the surface write Chris's message.

        His example is "July 19 — 4 photos and 1 story note", which the
        browser can only say if the counts come back per day and per
        kind. A bare is_empty flag would have been enough for the drop
        and useless for the refusal.
        """
        trip_repository.trip_day_update(self.days[0]["id"],
                                        title="Arrival")
        trip_repository.location_note_create(
            trip_id=self.trip_id, note_text="day-one story",
            source_type="operator", trip_day_id=self.days[0]["id"])
        self._shrink()
        pv = trips.reconcile_preview_trip_days(self.trip_id)
        by_date = {d["date"]: d for d in pv["out_of_range_days"]}
        held = by_date["2026-05-01"]
        self.assertFalse(held["is_empty"])
        self.assertEqual(held["holds"]["notes"], 1)
        self.assertIn("title", held["holds"]["own"])
        bare = by_date["2026-05-05"]
        self.assertTrue(bare["is_empty"])
        self.assertEqual(bare["holds"]["notes"], 0)
        self.assertEqual(bare["holds"]["own"], [])

    def test_the_preview_still_writes_nothing_when_it_reports_holds(self):
        trip_repository.trip_day_update(self.days[0]["id"], title="Arrival")
        self._shrink()
        before = self._dump_days()
        trips.reconcile_preview_trip_days(self.trip_id)
        self.assertEqual(before, self._dump_days())

    def test_in_range_days_are_never_candidates(self):
        """The flag is about the window, not about emptiness.

        Four of this trip's five cards are bare, and three of them are
        inside the shortened window. A rule that removed empty cards
        rather than empty OUT-OF-RANGE cards would delete the trip.
        """
        self._shrink()
        trips.reconcile_trip_days(
            self.trip_id, _ReconcileReq(drop_empty_out_of_range=True))
        self.assertEqual(len(trip_repository.trip_days_list(self.trip_id)), 3)

    def test_add_and_drop_in_one_call_agree_about_the_window(self):
        """The drop re-previews after the add.

        Acting on the list computed before add_missing ran would decide
        against a set of rows that no longer describes the trip.
        """
        trip_repository.trip_update(self.trip_id, start_date="2026-05-03",
                                    end_date="2026-05-07")
        out = trips.reconcile_trip_days(self.trip_id, _ReconcileReq(
            add_missing=True, drop_empty_out_of_range=True))
        self.assertEqual(out["added"], 2)          # 05-06, 05-07
        self.assertEqual(out["dropped_empty_out_of_range"], 2)  # 05-01, 05-02
        dates = sorted(d["date"]
                       for d in trip_repository.trip_days_list(self.trip_id))
        self.assertEqual(dates, ["2026-05-03", "2026-05-04", "2026-05-05",
                                 "2026-05-06", "2026-05-07"])

    def test_dropping_nothing_is_not_an_error(self):
        out = trips.reconcile_trip_days(
            self.trip_id, _ReconcileReq(drop_empty_out_of_range=True))
        self.assertEqual(out["dropped_empty_out_of_range"], 0)
        self.assertEqual(len(trip_repository.trip_days_list(self.trip_id)), 5)

    def test_a_trip_with_no_dates_drops_nothing(self):
        """No window means nothing can honestly be called out of range.

        The dangerous reading is the opposite one: clear a trip's dates
        and every card is outside a window that does not exist.
        """
        trip_repository.trip_update(self.trip_id, clear_start_date=True,
                                    clear_end_date=True)
        out = trips.reconcile_trip_days(
            self.trip_id, _ReconcileReq(drop_empty_out_of_range=True))
        self.assertEqual(out["dropped_empty_out_of_range"], 0)
        self.assertEqual(len(trip_repository.trip_days_list(self.trip_id)), 5)


class DayGeneratorEmptinessGuardTest(unittest.TestCase):
    """The day generator must not write a field that reads as content.

    The drop half of the shrinking-date rule only removes a card that
    holds nothing, and "nothing" is defined in exactly one place: the
    DAY_OWN_TEXT_FIELDS / DAY_OWN_LIST_FIELDS lists in
    ui/js/travel-doc-lab.js. Every card the generator makes has to
    satisfy that definition on the day it is made. If it does not, the
    drop half quietly stops working -- every auto-generated card reports
    content, every shrink is refused, the operator is told their empty
    cards could not be removed, and NO TEST FAILS.

    Today the rule holds by omission: `title` is simply not in the
    INSERT's column list, so a generated day's title is NULL and
    dayOwnContent reads it as empty. Omission is a weak guarantee. It
    survives exactly until someone decides "Day 4" is a friendlier
    default than blank, adds one column here, and breaks a rule written
    down in a different language in a different file. This test is the
    executable form of that rule.

    The field names are READ OUT OF THE JS, never copied into this file.
    A copy would mean the next field added to the emptiness definition
    arrives with the guard already blind to it, which is precisely the
    failure this exists to prevent.
    """

    _REPO_PY = _SERVER_CODE / "api" / "services" / "trip_repository.py"

    @staticmethod
    def _js_field_list(js: str, name: str):
        head = "var " + name + " = ["
        i = js.index(head)
        body = js[i + len(head):js.index("]", i)]
        return [p.strip().strip('"') for p in body.split(",") if p.strip()]

    def _insert_statement(self) -> str:
        """The INSERT text from trip_days_generate, and only from there.

        Sliced to the enclosing function BEFORE searching. A whole-file
        index for a literal that can legitimately appear more than once
        lands on whichever copy happens to come first, which is a real
        bug this repo has shipped more than once.
        """
        src = self._REPO_PY.read_text(encoding="utf-8")
        i = src.index("def trip_days_generate(")
        nxt = src.find("\ndef ", i + 1)
        gen = src[i:] if nxt == -1 else src[i:nxt]
        k = gen.index('"""INSERT INTO trip_days')
        return gen[k + 3:gen.index('"""', k + 3)]

    def _columns_and_slots(self):
        stmt = self._insert_statement()
        cols = [c.strip() for c in
                stmt[stmt.index("(") + 1:stmt.index(")")].split(",")]
        vals = stmt[stmt.index("VALUES"):]
        slots = [s.strip() for s in
                 vals[vals.index("(") + 1:vals.rindex(")")].split(",")]
        self.assertEqual(len(cols), len(slots),
                         "column list and VALUES list are different lengths; "
                         "the positional check below would be meaningless")
        return cols, slots

    def test_the_generator_writes_no_field_that_makes_a_card_look_used(self):
        js = _tds.UNIFIED_JS.stripped()
        text_fields = self._js_field_list(js, "DAY_OWN_TEXT_FIELDS")
        list_fields = self._js_field_list(js, "DAY_OWN_LIST_FIELDS")
        # Sanity: if the lists ever stop parsing, everything below passes
        # vacuously, so prove they came back populated and recognisable.
        self.assertIn("title", text_fields)
        self.assertIn("places_visited_json", list_fields)

        cols, slots = self._columns_and_slots()

        # A text field must not be written at all. There is no "empty
        # string is fine" concession: dayOwnContent trims, so '' would
        # pass today, but a column that exists is a column someone fills.
        for f in text_fields:
            self.assertNotIn(
                f, cols,
                "the day generator populates " + f + ", which "
                "dayOwnContent counts as content. Every generated card "
                "would report as used and the shrinking-date rule would "
                "refuse to remove any of them.")

        # A list field may be written, but only as an empty JSON array.
        for i, name in enumerate(cols):
            if name in list_fields:
                self.assertEqual(
                    slots[i], "'[]'",
                    name + " is written with something other than an empty "
                    "array literal; dayOwnContent parses it and a non-empty "
                    "list counts as content.")

        # Nothing but bound parameters and empty-array literals. Catches a
        # default slipped in as a literal on a column not in either list
        # today but added to one tomorrow.
        for slot in slots:
            self.assertIn(slot, ("?", "'[]'"),
                          "unexpected literal in the generator's VALUES: "
                          + slot)

        # dayOwnContent counts a pinned stop as work, so the generator
        # must not pin one.
        self.assertNotIn("trip_stop_id", cols)

    def test_the_region_the_generator_stamps_is_deliberately_uncounted(self):
        """trip_region_id is written on creation and must stay uncounted.

        This is the one place the two halves genuinely touch. The
        generator DOES stamp a covering region on every card it makes, so
        the decision not to count a region as work is load-bearing today
        rather than hypothetically: add trip_region_id to dayOwnContent
        for perfectly good reasons and every generated card becomes
        non-empty at birth. The two facts are asserted together so
        whoever changes one is standing in front of the other.
        """
        stmt = self._insert_statement()
        self.assertIn("trip_region_id", stmt)
        js = _tds.UNIFIED_JS.stripped()
        i = js.index("function dayOwnContent(")
        own = js[i:js.index("\n  }", i)]
        self.assertNotIn("trip_region_id", own)
        self.assertIn("trip_stop_id", own)


if __name__ == "__main__":
    unittest.main()
