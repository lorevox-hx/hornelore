"""WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01 Phase 2 — the Section 6 API.

The routes the browser calls, driven as the browser calls them, against
a real sqlite database built by the real migration chain. Repository
primitives are covered in tests.test_trip_photo_day_placements; this
suite exists because a correct primitive behind a route that validates
in the wrong ORDER, caps the wrong number, or reports the wrong thing is
still a broken product.

THE THREE PROPERTIES THIS SUITE IS REALLY FOR:

1. **A rejected batch writes nothing.** The 51-item refusal has to
   happen before the membership upserts, not after. A 400 that has
   already created trip links is a request the operator was told failed
   and which changed their trip anyway.

2. **Remove takes one occurrence.** The whole product ruling collapses
   if taking a photograph off Day 1 also takes it off Day 3, or worse,
   detaches it from the trip.

3. **Nothing writes the legacy column.** Asserted after every mutating
   route, because a single forgotten UPDATE would put the fossil back
   in play while every read derives its value from placements -- two
   answers to one question, with no error anywhere.

Run per-module:
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_trip_photo_placement_api
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
for _p in (str(_SERVER_CODE), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Offline stub pattern, identical to tests/test_trip_days.py. Kept
# byte-for-byte compatible with the sibling suites on purpose: whichever
# module wins the sys.modules race decides these classes for the whole
# process, and a stub that differs is how a suite passes alone and fails
# in a batch (see the note in test_trip_days.py).
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
from api.services import trip_repository as repo  # noqa: E402
from api.routers import trips  # noqa: E402


class _LinkReq:
    def __init__(self, photo_link_ids=None, photo_ids=None):
        self.photo_link_ids = list(photo_link_ids or [])
        self.photo_ids = list(photo_ids or [])


class _MoveReq:
    def __init__(self, photo_link_id, from_day_id, to_day_id):
        self.photo_link_id = photo_link_id
        self.from_day_id = from_day_id
        self.to_day_id = to_day_id


class _Case(unittest.TestCase):

    def setUp(self):
        self._tmpdb = tempfile.NamedTemporaryFile(suffix=".sqlite3",
                                                  delete=False)
        self._tmpdb.close()
        self.db_path = Path(self._tmpdb.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()
        self._orig_flag = os.environ.get("HORNELORE_TRIPS")
        os.environ["HORNELORE_TRIPS"] = "1"
        self._orig_sync = trips.trip_timeline_bridge.sync_trip_to_life_record
        trips.trip_timeline_bridge.sync_trip_to_life_record = \
            lambda *a, **k: None

        self.person_id = str(uuid.uuid4())
        self._exec(
            "INSERT INTO people (id, display_name, created_at, updated_at)"
            " VALUES (?, 'Placement Test', '2026-08-13', '2026-08-13')",
            (self.person_id,))
        self.trip_id = repo.trip_create(
            person_id=self.person_id, title="Placement Trip",
            start_date="2026-05-01", end_date="2026-05-05")
        repo.trip_days_generate(self.trip_id)
        self.days = repo.trip_days_list(self.trip_id)
        self.day1, self.day2, self.day3 = [d["id"] for d in self.days[:3]]

    def tearDown(self):
        trips.trip_timeline_bridge.sync_trip_to_life_record = self._orig_sync
        _db.DB_PATH = self._orig_db
        if self._orig_flag is None:
            os.environ.pop("HORNELORE_TRIPS", None)
        else:
            os.environ["HORNELORE_TRIPS"] = self._orig_flag
        try:
            self.db_path.unlink()
        except OSError:
            pass

    # ── fixture helpers ───────────────────────────────────────────────

    def _exec(self, sql, args=()):
        con = sqlite3.connect(str(self.db_path))
        try:
            con.execute("PRAGMA foreign_keys=ON")
            con.execute(sql, args)
            con.commit()
        finally:
            con.close()

    def q(self, sql, args=()):
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in con.execute(sql, args).fetchall()]
        finally:
            con.close()

    def _photo(self, taken=None, person=None):
        pid = str(uuid.uuid4())
        self._exec(
            "INSERT INTO photos (id, narrator_id, image_path, file_hash,"
            " uploaded_by_user_id, date_value) VALUES (?,?,?,?,?,?)",
            (pid, person or self.person_id, "/tmp/%s.jpg" % pid,
             "hash-" + pid, "op", taken))
        return pid

    def _link(self, taken=None, trip_id=None):
        pid = self._photo(taken=taken)
        return repo.photo_link_upsert(
            trip_id=trip_id or self.trip_id, photo_id=pid, taken_at=taken,
            assignment_method="operator", cluster_confidence=1.0)

    def placements(self, day_id=None):
        if day_id:
            return self.q("SELECT * FROM trip_photo_day_placements"
                          " WHERE trip_day_id=? ORDER BY ord", (day_id,))
        return self.q("SELECT * FROM trip_photo_day_placements ORDER BY id")

    def days_of(self, link_id):
        return sorted(r["trip_day_id"] for r in self.q(
            "SELECT trip_day_id FROM trip_photo_day_placements"
            " WHERE photo_link_id=?", (link_id,)))

    def scalars(self):
        return self.q("SELECT id, trip_day_id FROM trip_photo_links"
                      " ORDER BY id")

    def link_rows(self):
        return self.q("SELECT * FROM trip_photo_links ORDER BY id")


class AddRouteTest(_Case):

    def test_zero_one_and_many_placements_serialize_correctly(self):
        lid = self._link()
        rows = {r["id"]: r for r in repo.photo_links_list(self.trip_id)}
        self.assertIsNone(rows[lid]["trip_day_id"])
        self.assertEqual(rows[lid]["trip_day_ids"], [])
        self.assertEqual(rows[lid]["day_placements"], [])

        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        rows = {r["id"]: r for r in repo.photo_links_list(self.trip_id)}
        self.assertEqual(rows[lid]["trip_day_id"], self.day1)
        self.assertEqual(rows[lid]["trip_day_ids"], [self.day1])

        trips.link_day_photos(self.trip_id, self.day3, _LinkReq([lid]))
        rows = {r["id"]: r for r in repo.photo_links_list(self.trip_id)}
        self.assertIsNone(rows[lid]["trip_day_id"],
                          "several days must not elect an arbitrary one")
        self.assertEqual(sorted(rows[lid]["trip_day_ids"]),
                         sorted([self.day1, self.day3]))
        self.assertEqual(len(rows[lid]["day_placements"]), 2)

    def test_day_placements_carry_the_fields_the_ui_needs(self):
        lid = self._link()
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        p = repo.photo_links_list(self.trip_id)[0]["day_placements"][0]
        for key in ("id", "trip_day_id", "ord", "placement_method",
                    "placement_note", "day_index", "day_date"):
            self.assertIn(key, p, "missing %s" % key)
        self.assertEqual(p["placement_method"], "operator")

    def test_adding_twice_is_idempotent_and_reports_it(self):
        lid = self._link()
        first = trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        second = trips.link_day_photos(self.trip_id, self.day1,
                                       _LinkReq([lid]))
        self.assertEqual(first["updated"], 1)
        self.assertEqual(second["updated"], 0,
                         "a repeat must not claim to have done the work")
        self.assertEqual(second["already_present"], [lid])
        self.assertEqual(len(self.placements(self.day1)), 1)

    def test_add_many_orders_by_request_order(self):
        a, b, c = self._link(), self._link(), self._link()
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([c, a, b]))
        rows = self.placements(self.day1)
        self.assertEqual([r["photo_link_id"] for r in rows], [c, a, b])
        self.assertEqual([r["ord"] for r in rows], [0, 1, 2])

    def test_the_route_never_writes_the_legacy_column(self):
        lid = self._link()
        before = self.scalars()
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        trips.link_day_photos(self.trip_id, self.day2, _LinkReq([lid]))
        self.assertEqual(self.scalars(), before)

    def test_a_hand_written_scalar_is_not_served_as_authority(self):
        """Review caution, 2026-08-13. Nothing in the product creates a
        populated scalar with no placement -- 0043 backfilled every live
        one and no code writes the column now -- but manual SQL, an old
        script or a restored malformed backup can, for as long as the
        column exists. The rule is that such a value is ignored, not
        that it is promoted back into a placement.

        The sibling assertion on photo_link_get lives in
        tests.test_trip_photo_day_placements; this one covers the LIST
        read, which needs the real photos table.
        """
        lid = self._link()
        self._exec("UPDATE trip_photo_links SET trip_day_id=? WHERE id=?",
                   (self.day2, lid))
        row = {r["id"]: r for r in repo.photo_links_list(self.trip_id)}[lid]
        self.assertIsNone(row["trip_day_id"], "the fossil was served")
        self.assertEqual(row["trip_day_ids"], [])
        self.assertEqual(row["day_placements"], [])
        self.assertEqual(self.days_of(lid), [],
                         "reading resurrected it as a placement")
        self.assertEqual(
            repo.trip_day_counts(self.trip_id)[self.day2]["photos"], 0,
            "a stray scalar counted as a placement on the day card")


class BatchLimitTest(_Case):
    """§6.1. Fifty is a transport limit; fifty-one is a refusal."""

    def _links(self, n):
        return [self._link() for _ in range(n)]

    def test_exactly_fifty_is_accepted(self):
        ids = self._links(50)
        out = trips.link_day_photos(self.trip_id, self.day1, _LinkReq(ids))
        self.assertEqual(out["updated"], 50)
        self.assertEqual(len(self.placements(self.day1)), 50)

    def test_fifty_one_is_refused_with_400(self):
        ids = self._links(51)
        with self.assertRaises(HTTPException) as ctx:
            trips.link_day_photos(self.trip_id, self.day1, _LinkReq(ids))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_a_refused_batch_writes_absolutely_nothing(self):
        """Not truncated to fifty, not partially applied."""
        ids = self._links(51)
        before_placements = self.placements()
        before_links = self.link_rows()
        with self.assertRaises(HTTPException):
            trips.link_day_photos(self.trip_id, self.day1, _LinkReq(ids))
        self.assertEqual(self.placements(), before_placements)
        self.assertEqual(self.link_rows(), before_links)

    def test_the_cap_counts_photo_ids_too_and_refuses_before_upserting(self):
        """The ordering that matters. photo_ids CREATE trip links, so a
        cap checked after that loop would leave new links behind on a
        request that then returned 400 -- a rejected call that changed
        the trip."""
        photo_ids = [self._photo() for _ in range(51)]
        before_links = self.link_rows()
        with self.assertRaises(HTTPException) as ctx:
            trips.link_day_photos(self.trip_id, self.day1,
                                  _LinkReq(photo_ids=photo_ids))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(self.link_rows(), before_links,
                         "the refusal created trip memberships anyway")

    def test_the_cap_is_the_sum_of_both_id_lists(self):
        ids = self._links(26)
        photo_ids = [self._photo() for _ in range(25)]
        before_links = self.link_rows()
        with self.assertRaises(HTTPException):
            trips.link_day_photos(self.trip_id, self.day1,
                                  _LinkReq(ids, photo_ids))
        self.assertEqual(self.link_rows(), before_links)


class RemoveRouteTest(_Case):

    def test_removing_one_day_leaves_the_other(self):
        lid = self._link()
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        trips.link_day_photos(self.trip_id, self.day3, _LinkReq([lid]))
        trips.unlink_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        self.assertEqual(self.days_of(lid), [self.day3])

    def test_removing_preserves_everything_that_is_not_the_placement(self):
        """§6.2 in full: membership, photo row, original, thumbnail,
        caption, approval, shared context."""
        lid = self._link()
        repo.photo_link_update(link_id=lid, caption="a caption",
                               caption_approved_for_lori=True)
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        link_before = self.link_rows()
        photos_before = self.q("SELECT * FROM photos ORDER BY id")

        trips.unlink_day_photos(self.trip_id, self.day1, _LinkReq([lid]))

        self.assertEqual(self.link_rows(), link_before,
                         "the trip membership row changed")
        self.assertEqual(self.q("SELECT * FROM photos ORDER BY id"),
                         photos_before, "the photo row changed")
        self.assertEqual(self.days_of(lid), [])

    def test_removing_something_that_is_not_there_is_not_an_error(self):
        lid = self._link()
        out = trips.unlink_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        self.assertTrue(out["ok"])
        self.assertEqual(out["removed"], 0)
        self.assertEqual(out["not_present"], [lid])

    def test_remove_reports_the_day_it_operated_on(self):
        """It used to return trip_day_id=None, meaning 'this photograph
        now has no day' -- a claim it can no longer make."""
        lid = self._link()
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        trips.link_day_photos(self.trip_id, self.day3, _LinkReq([lid]))
        out = trips.unlink_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        self.assertEqual(out["trip_day_id"], self.day1)

    def test_the_route_never_writes_the_legacy_column(self):
        lid = self._link()
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        before = self.scalars()
        trips.unlink_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        self.assertEqual(self.scalars(), before)


class MoveRouteTest(_Case):

    def test_move_changes_one_occurrence(self):
        lid = self._link()
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        trips.link_day_photos(self.trip_id, self.day3, _LinkReq([lid]))
        out = trips.move_photo_placement(
            self.trip_id, _MoveReq(lid, self.day1, self.day2))
        self.assertTrue(out["moved"])
        self.assertEqual(self.days_of(lid), sorted([self.day2, self.day3]))

    def test_moving_from_a_day_it_is_not_on_is_409_with_no_writes(self):
        lid = self._link()
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        before = self.placements()
        with self.assertRaises(HTTPException) as ctx:
            trips.move_photo_placement(
                self.trip_id, _MoveReq(lid, self.day3, self.day2))
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(self.placements(), before,
                         "a refused move added the destination anyway")

    def test_moving_to_the_same_day_is_refused(self):
        lid = self._link()
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        with self.assertRaises(HTTPException) as ctx:
            trips.move_photo_placement(
                self.trip_id, _MoveReq(lid, self.day1, self.day1))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_a_day_from_another_trip_is_refused(self):
        other = repo.trip_create(person_id=self.person_id, title="Other",
                                 start_date="2026-06-01", end_date="2026-06-02")
        repo.trip_days_generate(other)
        other_day = repo.trip_days_list(other)[0]["id"]
        lid = self._link()
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        before = self.placements()
        with self.assertRaises(HTTPException) as ctx:
            trips.move_photo_placement(
                self.trip_id, _MoveReq(lid, self.day1, other_day))
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(self.placements(), before)

    def test_moving_onto_a_day_it_already_occupies_removes_the_source(self):
        lid = self._link()
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        trips.link_day_photos(self.trip_id, self.day2, _LinkReq([lid]))
        out = trips.move_photo_placement(
            self.trip_id, _MoveReq(lid, self.day1, self.day2))
        self.assertTrue(out["destination_existed"])
        self.assertEqual(self.days_of(lid), [self.day2])


class CrossTripAndOwnershipTest(_Case):

    def test_a_link_from_another_trip_is_refused_with_no_writes(self):
        other = repo.trip_create(person_id=self.person_id, title="Other",
                                 start_date="2026-06-01", end_date="2026-06-02")
        foreign = self._link(trip_id=other)
        before = self.placements()
        with self.assertRaises(HTTPException) as ctx:
            trips.link_day_photos(self.trip_id, self.day1, _LinkReq([foreign]))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(self.placements(), before)

    def test_a_day_from_another_trip_is_refused_with_no_writes(self):
        other = repo.trip_create(person_id=self.person_id, title="Other",
                                 start_date="2026-06-01", end_date="2026-06-02")
        repo.trip_days_generate(other)
        other_day = repo.trip_days_list(other)[0]["id"]
        lid = self._link()
        before = self.placements()
        with self.assertRaises(HTTPException):
            trips.link_day_photos(self.trip_id, other_day, _LinkReq([lid]))
        self.assertEqual(self.placements(), before)

    def test_another_narrators_photo_is_refused(self):
        stranger = str(uuid.uuid4())
        self._exec(
            "INSERT INTO people (id, display_name, created_at, updated_at)"
            " VALUES (?, 'Stranger', '2026-08-13', '2026-08-13')", (stranger,))
        pid = self._photo(person=stranger)
        before = self.link_rows()
        with self.assertRaises(HTTPException) as ctx:
            trips.link_day_photos(self.trip_id, self.day1,
                                  _LinkReq(photo_ids=[pid]))
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(self.link_rows(), before)


class CountsAreExplicitTest(_Case):
    """§7. Two numbers that used to be one."""

    def test_placements_count_and_date_matches_suggest(self):
        placed = self._link(taken="2026-05-01T09:00:00Z")
        matching = self._link(taken="2026-05-01T10:00:00Z")
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([placed]))
        counts = repo.trip_day_counts(self.trip_id)[self.day1]
        self.assertEqual(counts["photos"], 1)
        self.assertEqual(counts["photo_suggestions"], 1)
        self.assertNotIn(placed, [matching])       # readability guard

    def test_a_photo_placed_here_is_not_suggested_here(self):
        lid = self._link(taken="2026-05-01T09:00:00Z")
        self.assertEqual(
            repo.trip_day_counts(self.trip_id)[self.day1]["photo_suggestions"],
            1)
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        self.assertEqual(
            repo.trip_day_counts(self.trip_id)[self.day1]["photo_suggestions"],
            0, "suggesting something already done is noise")

    def test_a_photo_placed_elsewhere_is_still_suggested_here(self):
        """The narrower exclusion the work order specifies: exclude
        photos already on THIS day, not photos placed anywhere."""
        lid = self._link(taken="2026-05-03T09:00:00Z")
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        counts = repo.trip_day_counts(self.trip_id)
        self.assertEqual(counts[self.day1]["photos"], 1)
        self.assertEqual(counts[self.day3]["photo_suggestions"], 1)

    def test_one_photo_on_two_days_counts_once_on_each(self):
        lid = self._link()
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        trips.link_day_photos(self.trip_id, self.day3, _LinkReq([lid]))
        counts = repo.trip_day_counts(self.trip_id)
        self.assertEqual(counts[self.day1]["photos"], 1)
        self.assertEqual(counts[self.day3]["photos"], 1)

    def test_a_hidden_link_is_out_of_display_counts(self):
        lid = self._link()
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        self._exec("UPDATE trip_photo_links SET hidden=1 WHERE id=?", (lid,))
        self.assertEqual(
            repo.trip_day_counts(self.trip_id)[self.day1]["photos"], 0)

    def test_a_hidden_links_placement_still_protects_its_day(self):
        """Display counts and deletion safety answer different
        questions, and this is the pair where they diverge."""
        lid = self._link()
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        self._exec("UPDATE trip_photo_links SET hidden=1 WHERE id=?", (lid,))
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        try:
            attached = repo._day_attachment_counts(con, self.trip_id)
        finally:
            con.close()
        self.assertEqual(attached.get(self.day1, {}).get("photos"), 1)
        self.assertFalse(repo._day_is_empty({"id": self.day1}, attached))

    def test_a_soft_deleted_photo_is_out_of_display_counts(self):
        lid = self._link()
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        self._exec("UPDATE photos SET deleted_at='2026-08-13'"
                   " WHERE id=(SELECT photo_id FROM trip_photo_links"
                   " WHERE id=?)", (lid,))
        self.assertEqual(
            repo.trip_day_counts(self.trip_id)[self.day1]["photos"], 0)

    def test_the_inventory_counts_a_multi_day_photo_as_placed_once(self):
        lid = self._link()
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        trips.link_day_photos(self.trip_id, self.day3, _LinkReq([lid]))
        inv = repo.trip_photo_inventory(self.trip_id)
        self.assertEqual(inv["attached"], 1)
        self.assertEqual(inv["on_a_day"], 1,
                         "the trip link counts once however many days")


class HonestFailureTest(_Case):
    """§7 closing rule: locks, I/O failures, missing tables and
    malformed queries surface. They are never translated into zero,
    because zero attachments is what licenses a day deletion."""

    def test_a_broken_counts_query_raises_rather_than_reporting_zero(self):
        self._exec("DROP TABLE trip_photo_day_placements")
        with self.assertRaises(sqlite3.Error):
            repo.trip_day_counts(self.trip_id)

    def test_a_broken_attachment_tally_raises(self):
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        try:
            con.execute("DROP TABLE trip_photo_links")
            with self.assertRaises(sqlite3.OperationalError):
                repo._day_attachment_counts(con, self.trip_id)
        finally:
            con.close()


class ScaleTest(_Case):
    """§11. No schema or product cap on one day; only a batch limit."""

    def test_a_thousand_placements_on_one_day(self):
        ids = [self._link() for _ in range(1000)]
        for chunk in range(0, 1000, 50):
            trips.link_day_photos(self.trip_id, self.day1,
                                  _LinkReq(ids[chunk:chunk + 50]))
        self.assertEqual(
            repo.trip_day_counts(self.trip_id)[self.day1]["photos"], 1000)
        rows = self.placements(self.day1)
        self.assertEqual(len(rows), 1000)
        self.assertEqual([r["ord"] for r in rows], list(range(1000)),
                         "order must be dense and monotonic across batches")


if __name__ == "__main__":
    unittest.main()
