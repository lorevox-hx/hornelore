"""WO-TRAVEL-DOC-EVIDENCE-REVIEW-QUEUE-01 Phase 1 -- queue read lock.

`tests/test_import_provenance_routes.py` locks the Phase 4 verification
surface. This file locks the one route WO-2 Phase 1 adds on top of it:
``GET /api/import-provenance/queue``, the read an Evidence Review Queue
screen is built on.

The queue read is a different kind of risk from the routes it sits
beside. Those routes write, so their failure mode is a bad write. This
one only reads, so its failure modes are quieter and worse: showing a
reviewer another person's evidence, serving rows out of a batch the
operator already retired, reporting a queue depth that is really just
the page size, or summarizing a match reason that was supposed to be
shown verbatim. A wrong write gets noticed. A wrong queue gets trusted.

What is locked here:

  1. THE GATE, AGAIN, FOR THIS ROUTE. 404 when the flag is off, even
     with `person_id` missing -- a 422 naming the parameter would prove
     the route exists.

  2. PERSON IS REQUIRED AND IS NEVER INFERRED. No person_id is a 422.
     An unknown person is a 409, not an empty queue: "this person has
     nothing" and "there is no such person" are different facts.

  3. THE BOUNDARY. A trip or batch belonging to someone else is 409,
     and one person's queue never contains another person's candidate.

  4. BOTH KINDS OF HIDDEN. A hidden candidate is out. A visible
     candidate inside a hidden batch is also out -- otherwise hiding a
     batch would be a lie. `include_hidden=true` brings both back and
     says which kind each one is.

  5. COUNTS DESCRIBE THE QUEUE, NOT THE PAGE. `state_counts` is
     computed over the whole filtered set and ignores the `state`
     filter, so a reviewer looking at `pending` still sees what is
     behind it. `total` does honor the filter. `queue_depth` is
     pending, and nothing else.

  6. ORDER IS INSERTION ORDER. `created_at` has whole-second precision
     and a real import lands inside one second, so the rowid tiebreak
     is what actually makes this a queue.

  7. IT IS A READ. `match_reason` comes back byte-identical to what
     went in, no join alias leaks into the payload, and nothing in the
     database changes because someone looked at it.

  8. INTAKE IS STILL NOT APPROVAL. Looking at a candidate does not
     promote it, and the queue materializes no photo.

Fresh sqlite fixture and a fresh FastAPI app per test. pytest is not
installed in this repo; run with:

    python3 -m unittest tests.test_import_provenance_queue
"""
from __future__ import annotations

import json
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

from fastapi import FastAPI  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from api import db as _db  # noqa: E402
from api.routers import import_provenance as ip  # noqa: E402
from api.services import import_repository as repo  # noqa: E402

_FLAG = "HORNELORE_IMPORT_PROVENANCE"
_QUEUE = "/api/import-provenance/queue"

# A shape from _TOKEN_PATTERNS. Not a real credential -- the pattern is
# the point, and the test asserts the queue can never serve one.
_FAKE_TOKEN = "ya29.A0ARrdaM_thisIsNotARealTokenJustTheShape"


def _fixed_now() -> str:
    return "2026-07-26T00:00:00Z"


class _Base(unittest.TestCase):
    """Fresh database, fresh app, flag ON.

    Deliberately a copy of the routes-test fixture rather than an import
    of it. `python3 -m unittest discover` contaminates across modules in
    this repo, so each test module stands on its own and is run by name.
    """

    flag_value = "1"

    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        tmp.close()
        self.db_path = Path(tmp.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()

        self._orig_flag = os.environ.get(_FLAG)
        if self.flag_value is None:
            os.environ.pop(_FLAG, None)
        else:
            os.environ[_FLAG] = self.flag_value

        app = FastAPI()
        app.include_router(ip.router)
        self.client = TestClient(app, raise_server_exceptions=False)

        self.person_id = self._insert_person("Christopher Todd Horne")
        self.other_person_id = self._insert_person("Kent James Horne")
        self.trip_id = self._insert_trip(self.person_id, "Europe 2026")
        self.other_trip_id = self._insert_trip(self.other_person_id, "Not His")

    def tearDown(self):
        self.client.close()
        _db.DB_PATH = self._orig_db
        if self._orig_flag is None:
            os.environ.pop(_FLAG, None)
        else:
            os.environ[_FLAG] = self._orig_flag
        try:
            self.db_path.unlink()
        except OSError:
            pass

    # -- fixture helpers -------------------------------------------------

    def _con(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON;")
        return con

    def _insert_person(self, name: str) -> str:
        pid = str(uuid.uuid4())
        con = self._con()
        try:
            con.execute(
                "INSERT INTO people (id, display_name, created_at, updated_at) "
                "VALUES (?, ?, ?, ?)", (pid, name, _fixed_now(), _fixed_now()),
            )
            con.commit()
        finally:
            con.close()
        return pid

    def _insert_trip(self, person_id: str, title: str,
                     start_date: str = "2026-05-01",
                     end_date: str = "2026-05-20") -> str:
        tid = str(uuid.uuid4())
        con = self._con()
        try:
            con.execute(
                "INSERT INTO trips (id, person_id, title, start_date, "
                "end_date, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (tid, person_id, title, start_date, end_date,
                 _fixed_now(), _fixed_now()),
            )
            con.commit()
        finally:
            con.close()
        return tid

    def _insert_photo(self, narrator_id: str) -> str:
        pid = str(uuid.uuid4())
        con = self._con()
        try:
            con.execute(
                "INSERT INTO photos (id, narrator_id, image_path, file_hash, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (pid, narrator_id, "/tmp/%s.jpg" % pid, uuid.uuid4().hex,
                 _fixed_now(), _fixed_now()),
            )
            con.commit()
        finally:
            con.close()
        return pid

    # -- HTTP helpers ----------------------------------------------------

    def _open_batch(self, person_id=None, **over) -> str:
        body = {"person_id": person_id or self.person_id,
                "source": "local_upload"}
        body.update(over)
        r = self.client.post("/api/import-provenance/batches", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["batch"]["id"]

    def _new_candidate(self, batch_id=None, **body) -> str:
        bid = batch_id or self._open_batch()
        r = self.client.post(
            "/api/import-provenance/batches/%s/candidates" % bid, json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["candidate"]["id"]

    def _decide(self, candidate_id, **body):
        return self.client.post(
            "/api/import-provenance/candidates/%s/decision" % candidate_id,
            json=body)

    def _hide_candidate(self, candidate_id, hidden=True):
        r = self.client.patch(
            "/api/import-provenance/candidates/%s/hidden" % candidate_id,
            json={"hidden": hidden})
        self.assertEqual(r.status_code, 200, r.text)

    def _hide_batch(self, batch_id, hidden=True):
        r = self.client.patch(
            "/api/import-provenance/batches/%s/hidden" % batch_id,
            json={"hidden": hidden})
        self.assertEqual(r.status_code, 200, r.text)

    def _queue(self, **params):
        params.setdefault("person_id", self.person_id)
        return self.client.get(_QUEUE, params=params)

    def _ok_queue(self, **params) -> dict:
        r = self._queue(**params)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["ok"])
        return body

    def _ids(self, body) -> list:
        return [c["id"] for c in body["candidates"]]


# ======================================================================
#  1 -- THE GATE
# ======================================================================


class QueueGateTests(_Base):

    flag_value = None  # unset entirely: default OFF

    def test_queue_404s_when_the_flag_is_off(self):
        r = self.client.get(_QUEUE, params={"person_id": "whoever"})
        self.assertEqual(r.status_code, 404)

    def test_queue_404s_before_it_validates_a_missing_person_id(self):
        """422 would name the parameter, which announces the route.

        FastAPI validates query parameters before it calls the handler,
        so a gate that lived only inside the handler would answer 422
        here and hand a prober the shape of the endpoint. The gate is a
        router dependency, which is solved first, so 404 wins.
        """
        r = self.client.get(_QUEUE)
        self.assertEqual(r.status_code, 404, r.text)

    def test_queue_404s_with_junk_query_parameters(self):
        for params in ({"person_id": ""}, {"limit": "banana"},
                       {"offset": "-5"}, {"state": "nonsense"}):
            with self.subTest(params=params):
                r = self.client.get(_QUEUE, params=params)
                self.assertEqual(r.status_code, 404, r.text)


# ======================================================================
#  2 -- PERSON IS REQUIRED AND IS NEVER INFERRED
# ======================================================================


class QueuePersonTests(_Base):

    def test_missing_person_id_is_a_422_not_a_default(self):
        r = self.client.get(_QUEUE)
        self.assertEqual(r.status_code, 422, r.text)

    def test_empty_person_id_is_a_422(self):
        r = self.client.get(_QUEUE, params={"person_id": ""})
        self.assertEqual(r.status_code, 422, r.text)

    def test_unknown_person_is_409_not_an_empty_queue(self):
        """An empty list would read as 'this person has nothing'."""
        r = self.client.get(_QUEUE, params={"person_id": str(uuid.uuid4())})
        self.assertEqual(r.status_code, 409, r.text)

    def test_a_real_person_with_no_imports_is_an_empty_queue(self):
        body = self._ok_queue()
        self.assertEqual(body["candidates"], [])
        self.assertEqual(body["total"], 0)
        self.assertEqual(body["returned"], 0)
        self.assertEqual(body["queue_depth"], 0)
        self.assertEqual(
            body["state_counts"],
            {"pending": 0, "accepted": 0, "rejected": 0,
             "duplicate": 0, "error": 0},
        )

    def test_person_id_is_echoed_back_so_a_screen_can_prove_whose_queue(self):
        body = self._ok_queue()
        self.assertEqual(body["person_id"], self.person_id)


# ======================================================================
#  3 -- THE BOUNDARY
# ======================================================================


class QueueBoundaryTests(_Base):

    def test_another_persons_trip_is_409(self):
        r = self._queue(trip_id=self.other_trip_id)
        self.assertEqual(r.status_code, 409, r.text)

    def test_an_unknown_trip_is_409(self):
        r = self._queue(trip_id=str(uuid.uuid4()))
        self.assertEqual(r.status_code, 409, r.text)

    def test_another_persons_batch_is_409(self):
        other_batch = self._open_batch(person_id=self.other_person_id)
        r = self._queue(batch_id=other_batch)
        self.assertEqual(r.status_code, 409, r.text)

    def test_an_unknown_batch_is_404(self):
        """404 and not 409: there is nothing there to be refused."""
        r = self._queue(batch_id=str(uuid.uuid4()))
        self.assertEqual(r.status_code, 404, r.text)

    def test_one_persons_queue_never_contains_anothers_candidates(self):
        mine = self._new_candidate(filename="mine.jpg")
        theirs_batch = self._open_batch(person_id=self.other_person_id)
        theirs = self._new_candidate(theirs_batch, filename="theirs.jpg")

        body = self._ok_queue()
        self.assertEqual(self._ids(body), [mine])
        self.assertNotIn(theirs, self._ids(body))
        self.assertEqual(body["total"], 1)

        other = self._ok_queue(person_id=self.other_person_id)
        self.assertEqual(self._ids(other), [theirs])

    def test_an_unknown_state_filter_is_400(self):
        r = self._queue(state="skipped")
        self.assertEqual(r.status_code, 400, r.text)

    def test_changed_and_skipped_are_not_states_this_queue_knows(self):
        """Recorded WO-2 design vocabulary, not 0037 behavior.

        `changed` and `skipped` are carried-forward design inputs. Until
        a migration makes them real, the queue must refuse them rather
        than quietly returning an empty page that looks like a state
        with nothing in it.
        """
        for word in ("changed", "skipped"):
            with self.subTest(word=word):
                r = self._queue(state=word)
                self.assertEqual(r.status_code, 400, r.text)

    def test_a_negative_limit_or_offset_is_422(self):
        for params in ({"limit": -1}, {"offset": -1}):
            with self.subTest(params=params):
                r = self._queue(**params)
                self.assertEqual(r.status_code, 422, r.text)


# ======================================================================
#  4 -- BOTH KINDS OF HIDDEN
# ======================================================================


class QueueHiddenTests(_Base):

    def setUp(self):
        super().setUp()
        self.batch_a = self._open_batch(label="A")
        self.batch_b = self._open_batch(label="B")
        self.visible = self._new_candidate(self.batch_a, filename="visible.jpg")
        self.hidden_cand = self._new_candidate(self.batch_a,
                                               filename="hidden.jpg")
        self.in_hidden_batch = self._new_candidate(self.batch_b,
                                                   filename="in-hidden.jpg")
        self._hide_candidate(self.hidden_cand)
        self._hide_batch(self.batch_b)

    def test_a_hidden_candidate_is_out_of_the_queue(self):
        self.assertNotIn(self.hidden_cand, self._ids(self._ok_queue()))

    def test_a_visible_candidate_in_a_hidden_batch_is_also_out(self):
        """Otherwise hiding a batch would not actually retire anything."""
        con = self._con()
        try:
            row = con.execute(
                "SELECT hidden FROM import_candidate WHERE id = ?",
                (self.in_hidden_batch,)).fetchone()
        finally:
            con.close()
        self.assertEqual(row["hidden"], 0,
                         "fixture assumption: the candidate itself is visible")
        self.assertNotIn(self.in_hidden_batch, self._ids(self._ok_queue()))

    def test_only_the_visible_candidate_survives_the_default_queue(self):
        body = self._ok_queue()
        self.assertEqual(self._ids(body), [self.visible])
        self.assertEqual(body["total"], 1)

    def test_include_hidden_restores_both_kinds(self):
        ids = self._ids(self._ok_queue(include_hidden=True))
        self.assertEqual(
            set(ids),
            {self.visible, self.hidden_cand, self.in_hidden_batch})

    def test_include_hidden_says_which_kind_of_hidden_each_row_is(self):
        body = self._ok_queue(include_hidden=True)
        by_id = {c["id"]: c for c in body["candidates"]}
        self.assertEqual(by_id[self.visible]["hidden"], 0)
        self.assertEqual(by_id[self.visible]["batch"]["hidden"], 0)
        self.assertEqual(by_id[self.hidden_cand]["hidden"], 1)
        self.assertEqual(by_id[self.hidden_cand]["batch"]["hidden"], 0)
        self.assertEqual(by_id[self.in_hidden_batch]["hidden"], 0)
        self.assertEqual(by_id[self.in_hidden_batch]["batch"]["hidden"], 1)

    def test_hidden_rows_are_out_of_the_counts_too(self):
        """A queue depth that counted retired material would be a lie."""
        self.assertEqual(self._ok_queue()["state_counts"]["pending"], 1)
        self.assertEqual(
            self._ok_queue(include_hidden=True)["state_counts"]["pending"], 3)

    def test_unhiding_puts_a_candidate_back(self):
        self._hide_candidate(self.hidden_cand, hidden=False)
        self.assertIn(self.hidden_cand, self._ids(self._ok_queue()))

    def test_reopening_a_batch_is_not_the_same_as_unhiding_it(self):
        """Retirement and lifecycle are different axes.

        A closed batch's candidates stay in the queue -- closing means no
        more material is coming, not that what arrived stops mattering.
        """
        r = self.client.post(
            "/api/import-provenance/batches/%s/close" % self.batch_a, json={})
        self.assertEqual(r.status_code, 200, r.text)
        body = self._ok_queue()
        self.assertEqual(self._ids(body), [self.visible])
        self.assertEqual(body["candidates"][0]["batch"]["status"], "closed")


# ======================================================================
#  5 -- COUNTS DESCRIBE THE QUEUE, NOT THE PAGE
# ======================================================================


class QueueCountsTests(_Base):

    def setUp(self):
        super().setUp()
        self.batch = self._open_batch(label="mixed")
        self.pending = [self._new_candidate(self.batch, filename="p%d.jpg" % i)
                        for i in range(3)]
        self.rejected = self._new_candidate(self.batch, filename="r.jpg")
        self.duplicate = self._new_candidate(self.batch, filename="d.jpg")
        self.errored = self._new_candidate(self.batch, filename="e.jpg")
        for cid, state in ((self.rejected, "rejected"),
                           (self.duplicate, "duplicate"),
                           (self.errored, "error")):
            r = self._decide(cid, state=state, reason="fixture")
            self.assertEqual(r.status_code, 200, r.text)

    def test_state_counts_cover_every_state_including_the_empty_ones(self):
        counts = self._ok_queue()["state_counts"]
        self.assertEqual(
            counts,
            {"pending": 3, "accepted": 0, "rejected": 1,
             "duplicate": 1, "error": 1},
        )

    def test_state_counts_ignore_the_state_filter(self):
        """The whole point: filtering the view must not shrink the map."""
        counts = self._ok_queue(state="pending")["state_counts"]
        self.assertEqual(counts["pending"], 3)
        self.assertEqual(counts["rejected"], 1)
        self.assertEqual(counts["duplicate"], 1)
        self.assertEqual(counts["error"], 1)

    def test_state_counts_ignore_the_page_size(self):
        """`limit=1` must not report a one-candidate queue."""
        body = self._ok_queue(limit=1)
        self.assertEqual(body["returned"], 1)
        self.assertEqual(body["state_counts"]["pending"], 3)
        self.assertEqual(body["total"], 6)

    def test_total_does_honor_the_state_filter(self):
        body = self._ok_queue(state="pending")
        self.assertEqual(body["total"], 3)
        self.assertEqual(body["returned"], 3)

    def test_queue_depth_is_pending_and_only_pending(self):
        self.assertEqual(self._ok_queue()["queue_depth"], 3)
        self.assertEqual(self._ok_queue(state="rejected")["queue_depth"], 3)

    def test_the_filters_are_echoed_back_so_a_screen_can_show_its_state(self):
        body = self._ok_queue(state="pending", limit=2, offset=1)
        self.assertEqual(
            body["filters"],
            {"batch_id": None, "trip_id": None, "state": "pending",
             "include_hidden": False, "limit": 2, "offset": 1},
        )

    def test_counts_are_scoped_to_the_batch_filter(self):
        other = self._open_batch(label="other")
        self._new_candidate(other, filename="elsewhere.jpg")
        self.assertEqual(self._ok_queue()["state_counts"]["pending"], 4)
        self.assertEqual(
            self._ok_queue(batch_id=self.batch)["state_counts"]["pending"], 3)


# ======================================================================
#  6 -- ORDER IS INSERTION ORDER
# ======================================================================


class QueueOrderTests(_Base):

    def test_oldest_first_with_a_rowid_tiebreak(self):
        """`created_at` is whole-second, so rowid is what makes this work.

        Twenty candidates land inside the same second. Ordering by
        created_at alone leaves sqlite free to return them in any order,
        which in practice means uuid order -- a shuffled review queue.
        """
        batch = self._open_batch()
        expected = [self._new_candidate(batch, filename="f%02d.jpg" % i)
                    for i in range(20)]
        body = self._ok_queue(limit=50)
        self.assertEqual(self._ids(body), expected)

    def test_the_order_survives_paging(self):
        batch = self._open_batch()
        expected = [self._new_candidate(batch, filename="f%02d.jpg" % i)
                    for i in range(10)]
        seen = []
        for off in range(0, 10, 3):
            seen.extend(self._ids(self._ok_queue(limit=3, offset=off)))
        self.assertEqual(seen, expected)

    def test_offset_works_without_a_limit(self):
        """SQLite refuses OFFSET without LIMIT; the read must handle it."""
        batch = self._open_batch()
        expected = [self._new_candidate(batch, filename="f%d.jpg" % i)
                    for i in range(5)]
        body = self._ok_queue(offset=2)
        self.assertEqual(self._ids(body), expected[2:])
        self.assertEqual(body["total"], 5)
        self.assertEqual(body["returned"], 3)

    def test_an_offset_past_the_end_is_an_empty_page_not_an_error(self):
        batch = self._open_batch()
        self._new_candidate(batch, filename="only.jpg")
        body = self._ok_queue(offset=99)
        self.assertEqual(body["candidates"], [])
        self.assertEqual(body["returned"], 0)
        self.assertEqual(body["total"], 1,
                         "total describes the queue, not the page")

    def test_limit_zero_returns_the_counts_and_no_rows(self):
        """The cheapest way for a screen to ask 'how deep is the queue'."""
        batch = self._open_batch()
        for i in range(4):
            self._new_candidate(batch, filename="f%d.jpg" % i)
        body = self._ok_queue(limit=0)
        self.assertEqual(body["candidates"], [])
        self.assertEqual(body["total"], 4)
        self.assertEqual(body["queue_depth"], 4)


# ======================================================================
#  7 -- IT IS A READ
# ======================================================================


class QueueShapeTests(_Base):

    def test_each_candidate_carries_its_batch_inline(self):
        batch = self._open_batch(label="Takeout 2019", source="google_takeout",
                                 external_ref="takeout-2019-q3")
        self._new_candidate(batch, filename="a.jpg")
        row = self._ok_queue()["candidates"][0]
        self.assertEqual(row["batch"]["id"], batch)
        self.assertEqual(row["batch"]["label"], "Takeout 2019")
        self.assertEqual(row["batch"]["source"], "google_takeout")
        self.assertEqual(row["batch"]["status"], "open")
        self.assertEqual(row["batch"]["external_ref"], "takeout-2019-q3")
        self.assertEqual(row["batch"]["candidate_count"], 1)

    def test_an_unfiled_candidate_has_trip_none_not_a_dict_of_nulls(self):
        self._new_candidate(filename="unfiled.jpg")
        row = self._ok_queue()["candidates"][0]
        self.assertIsNone(row["trip"])
        self.assertIsNone(row["trip_id"])

    def test_a_filed_candidate_carries_its_trip_and_its_date_window(self):
        """The reviewer's first question is whether the date fits."""
        batch = self._open_batch(trip_id=self.trip_id)
        self._new_candidate(batch, filename="filed.jpg",
                            taken_at="2026-05-04T10:00:00Z",
                            taken_at_source="exif")
        row = self._ok_queue()["candidates"][0]
        self.assertEqual(row["trip"]["id"], self.trip_id)
        self.assertEqual(row["trip"]["title"], "Europe 2026")
        self.assertEqual(row["trip"]["start_date"], "2026-05-01")
        self.assertEqual(row["trip"]["end_date"], "2026-05-20")
        self.assertEqual(row["trip"]["status"], "draft")

    def test_no_join_alias_leaks_into_the_payload(self):
        """`_b_id` / `_t_id` are plumbing and must not reach a client."""
        batch = self._open_batch(trip_id=self.trip_id)
        self._new_candidate(batch, filename="a.jpg")
        row = self._ok_queue()["candidates"][0]
        leaked = [k for k in row if k.startswith(("_b_", "_t_"))]
        self.assertEqual(leaked, [], "join aliases leaked: %r" % leaked)

    def test_the_candidates_own_id_is_not_shadowed_by_the_batchs(self):
        """`import_candidate` and `import_batch` both have `id`."""
        batch = self._open_batch()
        cid = self._new_candidate(batch, filename="a.jpg")
        row = self._ok_queue()["candidates"][0]
        self.assertEqual(row["id"], cid)
        self.assertEqual(row["batch_id"], batch)
        self.assertEqual(row["batch"]["id"], batch)
        self.assertNotEqual(row["id"], row["batch"]["id"])

    def test_the_candidates_own_person_id_is_not_shadowed_either(self):
        self._new_candidate(filename="a.jpg")
        row = self._ok_queue()["candidates"][0]
        self.assertEqual(row["person_id"], self.person_id)

    def test_match_reason_round_trips_verbatim(self):
        """0037 made this JSON so the queue could show it, not summarize it."""
        reason = {
            "rule": "exif_gps_inside_region",
            "region": "Tuscany",
            "distance_km": 3.4,
            "evidence": ["exif_gps", "taken_at"],
            "nested": {"confidence_inputs": [0.8, 0.91], "manual": False},
        }
        self._new_candidate(filename="a.jpg", match_reason=reason,
                            match_confidence=0.87)
        row = self._ok_queue()["candidates"][0]
        self.assertEqual(row["match_reason"], reason)
        self.assertEqual(json.loads(row["match_reason_json"]), reason)
        self.assertEqual(row["match_confidence"], 0.87)

    def test_a_queue_read_changes_nothing_in_the_database(self):
        batch = self._open_batch()
        for i in range(3):
            self._new_candidate(batch, filename="f%d.jpg" % i)

        def snapshot():
            con = self._con()
            try:
                return (
                    [dict(r) for r in con.execute(
                        "SELECT * FROM import_candidate ORDER BY rowid")],
                    [dict(r) for r in con.execute(
                        "SELECT * FROM import_batch ORDER BY rowid")],
                )
            finally:
                con.close()

        before = snapshot()
        for params in ({}, {"state": "pending"}, {"include_hidden": True},
                       {"limit": 1, "offset": 1}, {"batch_id": batch}):
            self._ok_queue(**params)
        self.assertEqual(snapshot(), before)

    def test_looking_at_a_candidate_does_not_promote_it(self):
        cid = self._new_candidate(filename="a.jpg")
        self._ok_queue()
        r = self.client.get("/api/import-provenance/candidates/%s" % cid)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["candidate"]["state"], "pending")
        self.assertIsNone(r.json()["candidate"]["photo_id"])

    def test_the_queue_materializes_no_photo(self):
        """Intake is not approval, and neither is being looked at."""
        self._new_candidate(filename="a.jpg")
        con = self._con()
        try:
            before = con.execute("SELECT COUNT(*) AS n FROM photos"
                                 ).fetchone()["n"]
        finally:
            con.close()
        self._ok_queue()
        con = self._con()
        try:
            after = con.execute("SELECT COUNT(*) AS n FROM photos"
                                ).fetchone()["n"]
        finally:
            con.close()
        self.assertEqual(before, after)

    def test_an_accepted_candidate_shows_the_photo_it_was_promoted_into(self):
        photo_id = self._insert_photo(self.person_id)
        cid = self._new_candidate(filename="a.jpg")
        r = self._decide(cid, state="accepted", photo_id=photo_id)
        self.assertEqual(r.status_code, 200, r.text)
        body = self._ok_queue(state="accepted")
        self.assertEqual(self._ids(body), [cid])
        self.assertEqual(body["candidates"][0]["photo_id"], photo_id)

    def test_the_queue_cannot_serve_a_token_because_intake_refuses_one(self):
        """Rule 3 holds upstream; this is the regression guard on the read."""
        bid = self._open_batch()
        r = self.client.post(
            "/api/import-provenance/batches/%s/candidates" % bid,
            json={"filename": "a.jpg",
                  "match_reason": {"note": _FAKE_TOKEN}})
        self.assertEqual(r.status_code, 400, r.text)
        self.assertNotIn(_FAKE_TOKEN, r.text)
        page = self._queue()
        self.assertEqual(page.status_code, 200, page.text)
        self.assertNotIn("ya29.", page.text)


# ======================================================================
#  8 -- THE REPOSITORY FUNCTION ON ITS OWN
# ======================================================================


class QueueRepositoryTests(_Base):
    """The route is one caller. These lock the read itself, so a second
    caller cannot be added that skips the boundary by not going through
    HTTP."""

    def test_person_id_is_required_at_the_repository_too(self):
        for bad in (None, "", "   "):
            with self.subTest(bad=bad):
                with self.assertRaises(repo.InvalidStateError):
                    repo.queue_read(bad)

    def test_an_unknown_person_raises_rather_than_returning_empty(self):
        with self.assertRaises(repo.CrossPersonError):
            repo.queue_read(str(uuid.uuid4()))

    def test_an_unknown_state_raises(self):
        with self.assertRaises(repo.InvalidStateError):
            repo.queue_read(self.person_id, state="skipped")

    def test_a_cross_person_batch_raises(self):
        other = self._open_batch(person_id=self.other_person_id)
        with self.assertRaises(repo.CrossPersonError):
            repo.queue_read(self.person_id, batch_id=other)

    def test_a_cross_person_trip_raises(self):
        with self.assertRaises(repo.CrossTripError):
            repo.queue_read(self.person_id, trip_id=self.other_trip_id)

    def test_a_negative_limit_or_offset_raises(self):
        with self.assertRaises(repo.InvalidStateError):
            repo.queue_read(self.person_id, limit=-1)
        with self.assertRaises(repo.InvalidStateError):
            repo.queue_read(self.person_id, offset=-1)

    def test_it_agrees_with_candidates_list_on_which_rows_are_visible(self):
        """The queue adds context; it must not add or drop rows.

        Compared against `candidates_list` with hidden batches excluded
        by hand, which is the only difference between the two reads.
        """
        batch = self._open_batch()
        ids = [self._new_candidate(batch, filename="f%d.jpg" % i)
               for i in range(4)]
        raw = [c["id"] for c in repo.candidates_list(person_id=self.person_id)]
        queued = [c["id"] for c in
                  repo.queue_read(self.person_id)["candidates"]]
        self.assertEqual(raw, ids)
        self.assertEqual(queued, ids)

    def test_the_read_opens_and_closes_its_own_connection(self):
        """No connection is left behind for a later write to trip over."""
        self._new_candidate(filename="a.jpg")
        for _ in range(25):
            repo.queue_read(self.person_id)
        self.assertEqual(repo.queue_read(self.person_id)["total"], 1)


if __name__ == "__main__":
    unittest.main()
