"""WO-TRIP-PHOTO-PALETTE-01 P1 — batch Hide/Restore, and the two read fixes.

THE PROBLEM THIS LANE EXISTS FOR. The Palette lets an operator select
fifty photographs and hide them. `PATCH /photo-links/{id}` updates one
link and commits, so fifty of those are fifty transactions: a failure at
request thirty-one leaves thirty hidden and twenty not, with nothing
recording which, and the operator's only signal is a grid that
half-changed. `POST /{trip_id}/photo-links/visibility` is all-or-none.

THE THREE PROPERTIES THIS SUITE IS REALLY FOR:

1. **All or none.** A batch that names one foreign link changes nothing
   at all -- not the forty-nine that were legitimate either.

2. **Hiding is a posture, not an edit.** The route names three columns.
   After every call this suite re-reads placements, captions, all four
   approval flags and the photos row and asserts they are byte-identical,
   because "it only touches hidden" is exactly the kind of claim that
   quietly stops being true.

3. **The read fixes hold.** A soft-deleted photograph never enters the
   operator list, and the order is TOTAL -- `taken_at` and `ord` tie
   constantly, and a windowed grid over a nondeterministic order moves
   cards between renders for no reason the operator can see.

Run per-module:
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_trip_photo_visibility_batch
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

# Offline stub pattern, byte-compatible with tests.test_trip_photo_placement_api
# on purpose: whichever module wins the sys.modules race decides these
# classes for the whole process, and a stub that differs is how a suite
# passes alone and fails in a batch.
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


class _VisReq:
    def __init__(self, photo_link_ids=None, hidden=True):
        self.photo_link_ids = list(photo_link_ids or [])
        self.hidden = hidden


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
            " VALUES (?, 'Visibility Test', '2026-08-14', '2026-08-14')",
            (self.person_id,))
        self.trip_id = repo.trip_create(
            person_id=self.person_id, title="Visibility Trip",
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

    def _link(self, taken=None, trip_id=None, ord_=None):
        pid = self._photo(taken=taken)
        lid = repo.photo_link_upsert(
            trip_id=trip_id or self.trip_id, photo_id=pid, taken_at=taken,
            assignment_method="operator", cluster_confidence=1.0)
        if ord_ is not None:
            self._exec("UPDATE trip_photo_links SET ord=? WHERE id=?",
                       (ord_, lid))
        return lid

    def hidden_of(self, link_id):
        r = self.q("SELECT hidden, hidden_at FROM trip_photo_links"
                   " WHERE id=?", (link_id,))
        return (int(r[0]["hidden"] or 0), r[0]["hidden_at"])

    def link_row(self, link_id):
        return self.q("SELECT * FROM trip_photo_links WHERE id=?",
                      (link_id,))[0]

    def photo_rows(self):
        return self.q("SELECT * FROM photos ORDER BY id")

    def placements(self):
        return self.q("SELECT * FROM trip_photo_day_placements ORDER BY id")

    def call(self, ids, hidden=True):
        return trips.set_photo_links_visibility(
            self.trip_id, _VisReq(ids, hidden))


# ══════════════════════════════════════════════════════════════════════
# 1. Sizes: 0, 1, 49, 50, 51
# ══════════════════════════════════════════════════════════════════════

class BatchSizeTest(_Case):

    def test_zero_ids_is_422_and_writes_nothing(self):
        lid = self._link()
        with self.assertRaises(HTTPException) as cm:
            self.call([])
        self.assertEqual(422, cm.exception.status_code)
        self.assertEqual((0, None), self.hidden_of(lid))

    def test_one_id_hides_exactly_that_link(self):
        a, b = self._link(), self._link()
        out = self.call([a], hidden=True)
        self.assertEqual(1, out["requested"])
        self.assertEqual(1, out["updated"])
        self.assertEqual([], out["already_in_state"])
        self.assertEqual(1, self.hidden_of(a)[0])
        self.assertIsNotNone(self.hidden_of(a)[1],
                             "hiding must stamp hidden_at")
        self.assertEqual((0, None), self.hidden_of(b),
                         "a link not named must not move")

    def test_forty_nine_is_accepted(self):
        ids = [self._link() for _ in range(49)]
        out = self.call(ids, hidden=True)
        self.assertEqual(49, out["updated"])
        self.assertTrue(all(self.hidden_of(i)[0] == 1 for i in ids))

    def test_exactly_fifty_is_accepted(self):
        ids = [self._link() for _ in range(50)]
        out = self.call(ids, hidden=True)
        self.assertEqual(50, out["requested"])
        self.assertEqual(50, out["updated"])
        self.assertTrue(all(self.hidden_of(i)[0] == 1 for i in ids))

    def test_fifty_one_is_400_with_zero_writes(self):
        ids = [self._link() for _ in range(51)]
        with self.assertRaises(HTTPException) as cm:
            self.call(ids, hidden=True)
        self.assertEqual(400, cm.exception.status_code)
        self.assertIn("51", str(cm.exception.detail))
        self.assertIn("Nothing was written", str(cm.exception.detail))
        self.assertTrue(all(self.hidden_of(i) == (0, None) for i in ids),
                        "a refused batch must not have hidden anything")

    def test_the_cap_is_the_same_constant_the_placement_lane_uses(self):
        """Two ceilings that drift apart is two products. The Palette
        hides and places in the same session; if Hide took 50 and Add
        took 25 the operator would learn one number and be wrong half
        the time."""
        self.assertEqual(50, trips.PLACEMENT_BATCH_MAX)


# ══════════════════════════════════════════════════════════════════════
# 2. All or none
# ══════════════════════════════════════════════════════════════════════

class AllOrNoneTest(_Case):

    def test_a_foreign_link_rejects_the_whole_batch(self):
        other_trip = repo.trip_create(
            person_id=self.person_id, title="Other", start_date="2026-06-01",
            end_date="2026-06-02")
        mine = [self._link() for _ in range(3)]
        theirs = self._link(trip_id=other_trip)
        with self.assertRaises(HTTPException) as cm:
            self.call(mine + [theirs], hidden=True)
        self.assertEqual(400, cm.exception.status_code)
        for lid in mine:
            self.assertEqual((0, None), self.hidden_of(lid),
                             "the legitimate ids in a rejected batch must "
                             "not have been hidden")
        self.assertEqual((0, None), self.hidden_of(theirs))

    def test_a_nonexistent_link_rejects_the_whole_batch(self):
        mine = [self._link() for _ in range(3)]
        with self.assertRaises(HTTPException) as cm:
            self.call(mine + [str(uuid.uuid4())], hidden=True)
        self.assertEqual(400, cm.exception.status_code)
        for lid in mine:
            self.assertEqual((0, None), self.hidden_of(lid))

    def test_a_nonexistent_trip_writes_nothing(self):
        lid = self._link()
        with self.assertRaises(HTTPException) as cm:
            trips.set_photo_links_visibility(
                str(uuid.uuid4()), _VisReq([lid], True))
        self.assertEqual(400, cm.exception.status_code)
        self.assertEqual((0, None), self.hidden_of(lid))


# ══════════════════════════════════════════════════════════════════════
# 3. Idempotence
# ══════════════════════════════════════════════════════════════════════

class IdempotenceTest(_Case):

    def test_hiding_what_is_already_hidden_is_not_an_error(self):
        a = self._link()
        self.call([a], hidden=True)
        first_at = self.hidden_of(a)[1]
        out = self.call([a], hidden=True)
        self.assertEqual(1, out["requested"])
        self.assertEqual(0, out["updated"])
        self.assertEqual([a], out["already_in_state"])
        self.assertEqual(first_at, self.hidden_of(a)[1],
                         "a no-op must not re-stamp hidden_at; the operator "
                         "hid it once and that is when it happened")

    def test_a_mixed_batch_separates_changed_from_already(self):
        a, b = self._link(), self._link()
        self.call([a], hidden=True)
        out = self.call([a, b], hidden=True)
        self.assertEqual(2, out["requested"])
        self.assertEqual(1, out["updated"])
        self.assertEqual([a], out["already_in_state"])
        self.assertEqual([b], out["changed"])

    def test_restore_clears_hidden_at(self):
        a = self._link()
        self.call([a], hidden=True)
        self.assertIsNotNone(self.hidden_of(a)[1])
        out = self.call([a], hidden=False)
        self.assertEqual(1, out["updated"])
        self.assertEqual((0, None), self.hidden_of(a))

    def test_restoring_what_is_visible_is_idempotent(self):
        a = self._link()
        out = self.call([a], hidden=False)
        self.assertEqual(0, out["updated"])
        self.assertEqual([a], out["already_in_state"])

    def test_duplicate_ids_in_one_request_count_once(self):
        a = self._link()
        out = self.call([a, a, a], hidden=True)
        self.assertEqual(1, out["requested"])
        self.assertEqual(1, out["updated"])


# ══════════════════════════════════════════════════════════════════════
# 4. Hiding is a posture, not an edit
# ══════════════════════════════════════════════════════════════════════

class TouchesNothingElseTest(_Case):

    def test_placements_survive_hide_and_restore(self):
        a = self._link()
        trips.link_day_photos(
            self.trip_id, self.day1,
            type("R", (), {"photo_link_ids": [a], "photo_ids": []})())
        trips.link_day_photos(
            self.trip_id, self.day3,
            type("R", (), {"photo_link_ids": [a], "photo_ids": []})())
        before = self.placements()
        self.assertEqual(2, len(before))

        self.call([a], hidden=True)
        self.assertEqual(before, self.placements(),
                         "hiding must not move a placement")
        self.call([a], hidden=False)
        self.assertEqual(before, self.placements(),
                         "restoring must not move a placement")

    def test_caption_and_all_four_approval_flags_survive(self):
        a = self._link()
        repo.photo_link_update(
            a, caption="a caption the operator wrote",
            caption_approved_for_lori=True)
        before = self.link_row(a)
        self.call([a], hidden=True)
        after = self.link_row(a)
        for col in ("caption", "narrator_caption", "caption_approved_for_lori",
                    "operator_context_note",
                    "operator_context_approved_for_lori",
                    "include_in_memoir", "trip_region_id", "trip_stop_id",
                    "photo_id", "assignment_method", "cluster_confidence",
                    "taken_at", "ord"):
            self.assertEqual(before[col], after[col],
                             "%s must not change when hiding" % col)

    def test_the_photos_row_is_untouched(self):
        a = self._link()
        before = self.photo_rows()
        self.call([a], hidden=True)
        self.call([a], hidden=False)
        self.assertEqual(before, self.photo_rows(),
                         "hiding is not a delete and not an edit to the asset")

    def test_only_three_columns_ever_change(self):
        """Named individually rather than by count, so a future column
        added to this UPDATE fails here with its own name.

        A SUBSET rather than an equality, and the reason is a real
        failure of the first draft: `_now()` has whole-second precision,
        so a link created and hidden inside the same second has an
        `updated_at` that is unchanged as a STRING. Asserting equality
        made the test fail on a fast machine and pass on a slow one,
        which is worse than not testing it. What matters is that nothing
        OUTSIDE the three moves, and that hidden/hidden_at do.
        """
        a = self._link()
        before = self.link_row(a)
        self.call([a], hidden=True)
        after = self.link_row(a)
        moved = {k for k in before if before[k] != after[k]}
        self.assertTrue(
            moved <= {"hidden", "hidden_at", "updated_at"},
            "the visibility route moved a column outside its three: %r"
            % sorted(moved - {"hidden", "hidden_at", "updated_at"}))
        self.assertIn("hidden", moved)
        self.assertIn("hidden_at", moved)


# ══════════════════════════════════════════════════════════════════════
# 5. Soft-deleted photographs never enter the operator list
# ══════════════════════════════════════════════════════════════════════

class SoftDeletedExclusionTest(_Case):

    def test_a_soft_deleted_photo_is_absent_from_photo_links(self):
        keep, gone = self._link(), self._link()
        gone_photo = self.link_row(gone)["photo_id"]
        self._exec("UPDATE photos SET deleted_at='2026-08-14' WHERE id=?",
                   (gone_photo,))
        ids = [r["id"] for r in repo.photo_links_list(self.trip_id)]
        self.assertIn(keep, ids)
        self.assertNotIn(gone, ids,
                         "the operator list must not show a photograph the "
                         "narrator lane has already dropped")

    def test_the_link_row_still_exists_it_is_only_hidden_from_this_read(self):
        """The read excludes it; the row is NOT deleted. Deletion safety
        and any future undelete both depend on the membership surviving."""
        gone = self._link()
        photo = self.link_row(gone)["photo_id"]
        self._exec("UPDATE photos SET deleted_at='2026-08-14' WHERE id=?",
                   (photo,))
        self.assertEqual(1, len(self.q(
            "SELECT id FROM trip_photo_links WHERE id=?", (gone,))))

    def test_an_orphan_link_cannot_exist_because_the_fk_cascades(self):
        """CORRECTED after the first draft asserted the wrong thing.

        The draft claimed a link whose photos row is missing survives
        this read, on the reasoning that a LEFT JOIN yields NULL for a
        missing row and `deleted_at IS NULL` is therefore true of it.
        That reasoning about the SQL is correct and the scenario is
        UNREACHABLE: `trip_photo_links.photo_id` carries
        `REFERENCES photos(id) ON DELETE CASCADE`, so deleting the photo
        deletes the membership with it. There is no orphan to keep.

        The `IS NULL`-on-a-LEFT-JOIN behaviour still matters as the
        degradation path for a database predating that foreign key, so
        the query is not changed -- but the guarantee is the constraint,
        not the WHERE clause, and this test now says so.
        """
        orphan = self._link()
        photo = self.link_row(orphan)["photo_id"]
        self._exec("DELETE FROM photos WHERE id=?", (photo,))
        self.assertEqual([], self.q(
            "SELECT id FROM trip_photo_links WHERE id=?", (orphan,)),
            "the FK cascade should have removed the membership")
        self.assertNotIn(orphan,
                         [r["id"] for r in repo.photo_links_list(self.trip_id)])

    def test_hidden_and_soft_deleted_are_independent_exclusions(self):
        a = self._link()
        self.call([a], hidden=True)
        self.assertNotIn(a, [r["id"] for r in
                             repo.photo_links_list(self.trip_id)])
        self.assertIn(a, [r["id"] for r in repo.photo_links_list(
            self.trip_id, include_hidden=True)],
            "include_hidden surfaces a hidden link")

        photo = self.link_row(a)["photo_id"]
        self._exec("UPDATE photos SET deleted_at='2026-08-14' WHERE id=?",
                   (photo,))
        self.assertNotIn(a, [r["id"] for r in repo.photo_links_list(
            self.trip_id, include_hidden=True)],
            "include_hidden is an operator escape hatch for HIDDEN rows; it "
            "must not resurrect a soft-deleted photograph")


# ══════════════════════════════════════════════════════════════════════
# 6. Total order
# ══════════════════════════════════════════════════════════════════════

class StableOrderTest(_Case):

    def test_id_is_the_final_tiebreaker_when_taken_at_and_ord_tie(self):
        ids = [self._link(taken="2026-05-02T10:00:00Z", ord_=0)
               for _ in range(12)]
        first = [r["id"] for r in repo.photo_links_list(self.trip_id)]
        self.assertEqual(sorted(ids), first,
                         "with taken_at and ord tied, id decides, so the "
                         "order is total and repeatable")

    def test_the_order_is_identical_across_repeated_reads(self):
        """A SMOKE CHECK, weaker than its name suggests -- recorded
        rather than dressed up. Mutation-testing showed that removing the
        `l.id` tiebreaker leaves THIS test green, because SQLite returns
        the same order for the same query against unchanged data. It
        cannot tell "deterministic by contract" from "deterministic by
        luck". The guarantee is carried by the `sorted()` assertions in
        the neighbouring tests, which that mutation does kill.
        """
        for _ in range(12):
            self._link(taken="2026-05-02T10:00:00Z", ord_=0)
        runs = [[r["id"] for r in repo.photo_links_list(self.trip_id)]
                for _ in range(5)]
        self.assertEqual(1, len({tuple(r) for r in runs}),
                         "a windowed grid over a nondeterministic order "
                         "moves cards between renders")

    def test_undated_links_are_also_totally_ordered(self):
        ids = [self._link(taken=None) for _ in range(8)]
        got = [r["id"] for r in repo.photo_links_list(self.trip_id)]
        self.assertEqual(sorted(ids), got)

    def test_taken_at_still_wins_over_id(self):
        """The tiebreaker must not have become the sort key."""
        late = self._link(taken="2026-05-04T09:00:00Z")
        early = self._link(taken="2026-05-01T09:00:00Z")
        got = [r["id"] for r in repo.photo_links_list(self.trip_id)]
        self.assertEqual([early, late], got)

    def test_the_max_confidence_path_is_ordered_too(self):
        """Two query paths, one order. The filtered branch is the one a
        Palette 'Needs review' filter would use."""
        for _ in range(8):
            self._link(taken="2026-05-02T10:00:00Z", ord_=0)
        a = [r["id"] for r in repo.photo_links_list(
            self.trip_id, max_confidence=1.0)]
        b = [r["id"] for r in repo.photo_links_list(
            self.trip_id, max_confidence=1.0)]
        self.assertEqual(a, b)
        self.assertEqual(sorted(a), a)


# ══════════════════════════════════════════════════════════════════════
# 7. The route contract
# ══════════════════════════════════════════════════════════════════════

class RouteContractTest(_Case):

    def test_the_response_reports_requested_updated_and_already(self):
        a, b = self._link(), self._link()
        self.call([a], hidden=True)
        out = self.call([a, b], hidden=True)
        self.assertTrue(out["ok"])
        self.assertTrue(out["hidden"])
        self.assertEqual({"ok", "hidden", "requested", "updated",
                          "already_in_state", "changed"}, set(out))

    def test_the_flag_is_required_and_has_no_silent_default(self):
        """A missing `hidden` must not mean restore. The model declares
        it without a default so the framework refuses the request rather
        than the route guessing."""
        import inspect
        src = inspect.getsource(trips.TripPhotoVisibilityReq)
        self.assertIn("hidden: bool", src)
        self.assertNotIn("hidden: bool = ", src)

    def test_the_route_writes_no_placement_and_no_legacy_scalar(self):
        """The fossil column stays derived. One forgotten UPDATE here
        would put it back in play while every read derives from
        placements -- two answers to one question, with no error.

        Asserted against the AST with the docstring stripped, not
        against the raw source. The first draft scanned the text and
        failed on this route's own docstring, which uses the words
        `placement` and `trip_day_id` to explain what it does NOT do.
        That is the guard-writing rule this repository has now hit four
        times: a guard written against a WORD fires on the prose that
        quotes the word. Match executable code or nothing.
        """
        import ast as _ast
        import inspect
        tree = _ast.parse(inspect.getsource(trips.set_photo_links_visibility))
        fn = tree.body[0]
        if (fn.body and isinstance(fn.body[0], _ast.Expr)
                and isinstance(fn.body[0].value, _ast.Constant)
                and isinstance(fn.body[0].value.value, str)):
            fn.body = fn.body[1:]          # drop the docstring
        body = "\n".join(_ast.dump(n) for n in fn.body)
        self.assertNotIn("trip_day_id", body,
                         "the visibility route must never name the derived "
                         "compatibility scalar")
        self.assertNotIn("day_placement", body,
                         "the visibility route must not reach into the "
                         "placement lane")


# ══════════════════════════════════════════════════════════════════════
# 8. One thousand memberships
# ══════════════════════════════════════════════════════════════════════

class ScaleTest(_Case):
    """The condition attached to keeping the one-fetch read.

    P0 concluded that no paging endpoint is needed because the Palette
    windows client-side over a single fetch. That conclusion is only
    honest if the single fetch stays acceptable at a size no real trip
    has yet reached. If this suite starts failing, server paging stops
    being speculative architecture and becomes a measured requirement.
    """

    def _bulk(self, n):
        """Inserted directly rather than through photo_link_upsert: this
        is about the READ, and 1000 round trips through the write path
        would measure the fixture instead."""
        con = sqlite3.connect(str(self.db_path))
        try:
            con.execute("PRAGMA foreign_keys=ON")
            rows_p, rows_l = [], []
            for i in range(n):
                pid, lid = str(uuid.uuid4()), str(uuid.uuid4())
                rows_p.append((pid, self.person_id, "/tmp/%s.jpg" % pid,
                               "h-" + pid, "op"))
                # Deliberately ALL the same taken_at and ord, so the read
                # is leaning entirely on `id` to be deterministic.
                rows_l.append((lid, self.trip_id, pid, "2026-05-02T10:00:00Z",
                               0, "operator", 1.0))
            con.executemany(
                "INSERT INTO photos (id, narrator_id, image_path, file_hash,"
                " uploaded_by_user_id) VALUES (?,?,?,?,?)", rows_p)
            con.executemany(
                "INSERT INTO trip_photo_links (id, trip_id, photo_id,"
                " taken_at, ord, assignment_method, cluster_confidence)"
                " VALUES (?,?,?,?,?,?,?)", rows_l)
            con.commit()
        finally:
            con.close()
        return [r[0] for r in rows_l]

    def test_one_thousand_links_read_once_each_and_quickly(self):
        import time
        ids = self._bulk(1000)
        t0 = time.time()
        rows = repo.photo_links_list(self.trip_id)
        elapsed = time.time() - t0
        self.assertEqual(1000, len(rows))
        got = [r["id"] for r in rows]
        self.assertEqual(1000, len(set(got)),
                         "every membership must appear exactly once")
        self.assertEqual(sorted(ids), got,
                         "1000 identical taken_at/ord values must still "
                         "produce a total order")
        self.assertLess(elapsed, 5.0,
                        "the single-fetch model is the reason no paging "
                        "endpoint was built; %.2fs" % elapsed)

    def test_the_order_is_repeatable_at_one_thousand(self):
        self._bulk(1000)
        a = [r["id"] for r in repo.photo_links_list(self.trip_id)]
        b = [r["id"] for r in repo.photo_links_list(self.trip_id)]
        self.assertEqual(a, b)

    def test_placements_do_not_become_an_n_plus_one_at_scale(self):
        """Two queries, not 1001. Asserted by counting statements on the
        connection rather than by timing, which would be a proxy."""
        self._bulk(400)
        # sqlite3.Connection.execute is read-only and cannot be wrapped;
        # set_trace_callback is the supported hook and it sees every
        # statement the connection actually runs, including the PRAGMAs.
        counted = {"n": 0}
        real_connect = repo._connect

        def counting_connect():
            con = real_connect()
            con.set_trace_callback(
                lambda _sql: counted.__setitem__("n", counted["n"] + 1))
            return con

        repo._connect = counting_connect
        try:
            repo.photo_links_list(self.trip_id)
        finally:
            repo._connect = real_connect
        self.assertLess(counted["n"], 12,
                        "the read issued %d statements for 400 links; a "
                        "per-link placement query is the failure this "
                        "number exists to catch" % counted["n"])


if __name__ == "__main__":
    unittest.main()
