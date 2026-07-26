"""WO-TRAVEL-DOC-IMPORT-PROVENANCE-FOUNDATION-01 Phase 4 -- route lock.

Phase 3 proved the rules hold in the repository. This file proves they
still hold when the caller is HTTP, which is a different question: a
route can forget a check, widen a body, invent a person_id field, or turn
a deliberate refusal into a 500 that reads like a server bug.

What is locked here:

  1. THE GATE. Every route 404s unless HORNELORE_IMPORT_PROVENANCE is on.
     Not 403, not 405 -- 404, so the surface does not announce itself.

  2. INTAKE IS NOT APPROVAL, THROUGH HTTP. A candidate posted over the
     wire is born 'pending'. Posting person_id, state, narrator_ready or
     include_in_memoir in the body changes nothing, because the route
     model has no such fields. Accepting requires a photo that already
     exists and already belongs to the candidate's person, and the accept
     does not write to the photos row at all.

  3. THE PERSON / TRIP / PHOTO BOUNDARY, AT THE ROUTE. A cross-person
     trip or photo is refused with 409 before the repository is called,
     so the HTTP surface has its own opinion rather than forwarding and
     hoping.

  4. A REFUSAL IS NOT A CRASH. Every ImportRepositoryError subclass maps
     to a specific 4xx. A pasted OAuth token comes back 400 with a
     message that names the field and never echoes the value.

  5. NO DELETE. The router declares no DELETE method and contains no
     DELETE FROM. Retirement is `hidden`, and it is reversible.

Fresh sqlite fixture and a fresh FastAPI app per test. pytest is not
installed in this repo; run with:

    python3 -m unittest tests.test_import_provenance_routes
"""
from __future__ import annotations

import io
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

_ROUTER_PATH = _SERVER_CODE / "api" / "routers" / "import_provenance.py"
_MAIN_PATH = _SERVER_CODE / "api" / "main.py"

_FLAG = "HORNELORE_IMPORT_PROVENANCE"

# A shape from _TOKEN_PATTERNS. Not a real credential -- it is the
# pattern that matters, and the test asserts it never comes back out.
_FAKE_TOKEN = "ya29.A0ARrdaM_thisIsNotARealTokenJustTheShape"


def _now() -> str:
    return "2026-07-26T00:00:00Z"


class _Base(unittest.TestCase):
    """Fresh database, fresh app, flag ON. Subclasses that want the flag
    off say so themselves."""

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
                "VALUES (?, ?, ?, ?)", (pid, name, _now(), _now()),
            )
            con.commit()
        finally:
            con.close()
        return pid

    def _insert_trip(self, person_id: str, title: str) -> str:
        tid = str(uuid.uuid4())
        con = self._con()
        try:
            con.execute(
                "INSERT INTO trips (id, person_id, title, created_at, "
                "updated_at) VALUES (?, ?, ?, ?, ?)",
                (tid, person_id, title, _now(), _now()),
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
                 _now(), _now()),
            )
            con.commit()
        finally:
            con.close()
        return pid

    def _photo_row(self, photo_id: str) -> dict:
        con = self._con()
        try:
            return dict(con.execute(
                "SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone())
        finally:
            con.close()

    # -- HTTP helpers ----------------------------------------------------

    def _post_batch(self, **over):
        body = {"person_id": self.person_id, "source": "local_upload"}
        body.update(over)
        return self.client.post("/api/import-provenance/batches", json=body)

    def _open_batch(self, **over) -> str:
        r = self._post_batch(**over)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["batch"]["id"]

    def _post_candidate(self, batch_id, **body):
        return self.client.post(
            "/api/import-provenance/batches/%s/candidates" % batch_id,
            json=body,
        )

    def _new_candidate(self, batch_id=None, **body) -> str:
        bid = batch_id or self._open_batch()
        r = self._post_candidate(bid, **body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["candidate"]["id"]

    def _decide(self, candidate_id, **body):
        return self.client.post(
            "/api/import-provenance/candidates/%s/decision" % candidate_id,
            json=body,
        )


# ======================================================================
#  1 -- THE GATE
# ======================================================================


class FlagGateTests(_Base):

    flag_value = None  # unset entirely: default OFF

    # Every route, so adding one without a gate call is caught here and
    # not in production.
    def _all_routes(self):
        return [
            ("post", "/api/import-provenance/batches", {"person_id": "p",
                                                        "source": "csv"}),
            ("get", "/api/import-provenance/batches", None),
            ("get", "/api/import-provenance/batches/b1", None),
            ("get", "/api/import-provenance/batches/b1/counts", None),
            ("patch", "/api/import-provenance/batches/b1/trip", {"trip_id": None}),
            ("post", "/api/import-provenance/batches/b1/close", {}),
            ("post", "/api/import-provenance/batches/b1/reopen", None),
            ("patch", "/api/import-provenance/batches/b1/hidden", {"hidden": True}),
            ("post", "/api/import-provenance/batches/b1/candidates", {}),
            ("get", "/api/import-provenance/candidates", None),
            ("get", "/api/import-provenance/candidates/c1", None),
            ("patch", "/api/import-provenance/candidates/c1/trip", {"trip_id": None}),
            ("post", "/api/import-provenance/candidates/c1/decision",
             {"state": "rejected"}),
            ("patch", "/api/import-provenance/candidates/c1/hidden", {"hidden": True}),
            ("get", "/api/import-provenance/enums", None),
        ]

    def test_every_route_404s_when_the_flag_is_off(self):
        for method, path, body in self._all_routes():
            with self.subTest(route="%s %s" % (method.upper(), path)):
                fn = getattr(self.client, method)
                r = fn(path) if body is None else fn(path, json=body)
                self.assertEqual(r.status_code, 404, "%s %s -> %s"
                                 % (method, path, r.status_code))

    def test_route_count_is_the_count_the_gate_test_covers(self):
        """If someone adds a route, the gate list above must grow too."""
        paths = {r.path for r in ip.router.routes}
        covered = {p for _m, p, _b in self._all_routes()}
        # The gate list uses literal ids where the route uses {batch_id};
        # compare the template shapes instead.
        templated = {
            p.replace("/b1", "/{batch_id}").replace("/c1", "/{candidate_id}")
            for p in covered
        }
        self.assertEqual(paths, templated)

    def test_off_switch_accepts_the_usual_falsey_spellings(self):
        for raw in ("0", "", "no", "off", "false", "  "):
            with self.subTest(raw=raw):
                os.environ[_FLAG] = raw
                r = self.client.get("/api/import-provenance/enums")
                self.assertEqual(r.status_code, 404)

    def test_on_switch_accepts_the_usual_truthy_spellings(self):
        for raw in ("1", "true", "TRUE", "yes", "on", " on "):
            with self.subTest(raw=raw):
                os.environ[_FLAG] = raw
                r = self.client.get("/api/import-provenance/enums")
                self.assertEqual(r.status_code, 200, raw)


# ======================================================================
#  2 -- BATCHES
# ======================================================================


class BatchRouteTests(_Base):

    def test_create_batch_returns_an_open_batch_for_that_person(self):
        r = self._post_batch(label="July picker run")
        self.assertEqual(r.status_code, 200, r.text)
        batch = r.json()["batch"]
        self.assertEqual(batch["person_id"], self.person_id)
        self.assertEqual(batch["status"], "open")
        self.assertEqual(batch["source"], "local_upload")
        self.assertEqual(batch["label"], "July picker run")
        self.assertIsNone(batch["trip_id"])
        self.assertEqual(batch["candidate_count"], 0)

    def test_unknown_source_is_400_and_lists_the_known_ones(self):
        r = self._post_batch(source="dropbox")
        self.assertEqual(r.status_code, 400)
        self.assertIn("google_photos_picker", r.json()["detail"])

    def test_blank_person_id_is_400(self):
        r = self._post_batch(person_id="   ")
        self.assertEqual(r.status_code, 400)
        self.assertIn("person_id", r.json()["detail"])

    def test_unknown_person_is_409_not_500(self):
        r = self._post_batch(person_id=str(uuid.uuid4()))
        self.assertEqual(r.status_code, 409)

    def test_another_persons_trip_is_refused_and_nothing_lands(self):
        r = self._post_batch(trip_id=self.other_trip_id)
        self.assertEqual(r.status_code, 409)
        self.assertIn("another person", r.json()["detail"])
        listed = self.client.get(
            "/api/import-provenance/batches",
            params={"person_id": self.person_id}).json()
        self.assertEqual(listed["count"], 0)

    def test_nonexistent_trip_is_409_at_the_route(self):
        r = self._post_batch(trip_id=str(uuid.uuid4()))
        self.assertEqual(r.status_code, 409)
        self.assertIn("no trip", r.json()["detail"])

    def test_get_unknown_batch_is_404(self):
        r = self.client.get("/api/import-provenance/batches/%s"
                            % uuid.uuid4())
        self.assertEqual(r.status_code, 404)

    def test_list_filters_by_person_and_status(self):
        mine = self._open_batch()
        theirs = self._open_batch(person_id=self.other_person_id)
        self.client.post("/api/import-provenance/batches/%s/close" % theirs,
                         json={})

        r = self.client.get("/api/import-provenance/batches",
                            params={"person_id": self.person_id})
        self.assertEqual([b["id"] for b in r.json()["batches"]], [mine])

        r = self.client.get("/api/import-provenance/batches",
                            params={"status": "closed"})
        self.assertEqual([b["id"] for b in r.json()["batches"]], [theirs])

    def test_list_with_an_unknown_status_is_400(self):
        r = self.client.get("/api/import-provenance/batches",
                            params={"status": "finished"})
        self.assertEqual(r.status_code, 400)

    def test_bind_trip_then_unbind(self):
        bid = self._open_batch()
        r = self.client.patch(
            "/api/import-provenance/batches/%s/trip" % bid,
            json={"trip_id": self.trip_id})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["batch"]["trip_id"], self.trip_id)

        r = self.client.patch(
            "/api/import-provenance/batches/%s/trip" % bid,
            json={"trip_id": None})
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()["batch"]["trip_id"])

    def test_bind_another_persons_trip_is_409(self):
        bid = self._open_batch()
        r = self.client.patch(
            "/api/import-provenance/batches/%s/trip" % bid,
            json={"trip_id": self.other_trip_id})
        self.assertEqual(r.status_code, 409)
        self.assertIsNone(repo.batch_get(bid)["trip_id"])

    def test_close_then_reopen(self):
        bid = self._open_batch()
        r = self.client.post("/api/import-provenance/batches/%s/close" % bid,
                             json={"failed": True,
                                   "failure_reason": "picker timed out"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["batch"]["status"], "failed")
        self.assertEqual(r.json()["batch"]["failure_reason"],
                         "picker timed out")

        r = self.client.post("/api/import-provenance/batches/%s/reopen" % bid)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["batch"]["status"], "open")
        self.assertIsNone(r.json()["batch"]["failure_reason"])

    def test_a_closed_batch_refuses_new_candidates_with_409(self):
        bid = self._open_batch()
        self.client.post("/api/import-provenance/batches/%s/close" % bid,
                         json={})
        r = self._post_candidate(bid, external_id="late")
        self.assertEqual(r.status_code, 409)

    def test_hidden_is_reversible_and_hides_from_the_default_list(self):
        bid = self._open_batch()
        self.client.patch("/api/import-provenance/batches/%s/hidden" % bid,
                          json={"hidden": True})
        default = self.client.get("/api/import-provenance/batches").json()
        self.assertEqual(default["count"], 0)

        shown = self.client.get("/api/import-provenance/batches",
                                params={"include_hidden": "true"}).json()
        self.assertEqual([b["id"] for b in shown["batches"]], [bid])

        self.client.patch("/api/import-provenance/batches/%s/hidden" % bid,
                          json={"hidden": False})
        back = self.client.get("/api/import-provenance/batches").json()
        self.assertEqual([b["id"] for b in back["batches"]], [bid])

    def test_counts_endpoint_reports_live_and_stored_together(self):
        bid = self._open_batch()
        self._new_candidate(bid, external_id="a")
        self._new_candidate(bid, external_id="b")
        r = self.client.get("/api/import-provenance/batches/%s/counts" % bid)
        self.assertEqual(r.status_code, 200, r.text)
        counts = r.json()["counts"]
        self.assertEqual(counts["total"], 2)
        self.assertEqual(counts["pending"], 2)
        self.assertEqual(counts["accepted"], 0)

    def test_counts_on_an_unknown_batch_is_404(self):
        r = self.client.get("/api/import-provenance/batches/%s/counts"
                            % uuid.uuid4())
        self.assertEqual(r.status_code, 404)


# ======================================================================
#  3 -- CANDIDATES AND THE BOUNDARY
# ======================================================================


class CandidateRouteTests(_Base):

    def test_candidate_is_born_pending_with_the_batchs_person(self):
        bid = self._open_batch()
        r = self._post_candidate(bid, external_id="ext-1",
                                 filename="IMG_0001.JPG")
        self.assertEqual(r.status_code, 200, r.text)
        cand = r.json()["candidate"]
        self.assertEqual(cand["state"], "pending")
        self.assertEqual(cand["person_id"], self.person_id)
        self.assertEqual(cand["batch_id"], bid)
        self.assertIsNone(cand["photo_id"])
        self.assertIsNone(cand["reviewed_at"])

    def test_the_body_cannot_assert_person_state_or_approval(self):
        """The route model has no person_id, no state, no narrator_ready
        and no include_in_memoir. Posting them is not an error -- it is
        simply nothing, which is the point."""
        bid = self._open_batch()
        r = self._post_candidate(
            bid,
            external_id="smuggle",
            person_id=self.other_person_id,
            state="accepted",
            narrator_ready=1,
            include_in_memoir=True,
            photo_id=self._insert_photo(self.other_person_id),
        )
        self.assertEqual(r.status_code, 200, r.text)
        cand = r.json()["candidate"]
        self.assertEqual(cand["person_id"], self.person_id)
        self.assertEqual(cand["state"], "pending")
        self.assertIsNone(cand["photo_id"])
        self.assertNotIn("narrator_ready", cand)
        self.assertNotIn("include_in_memoir", cand)

    def test_candidate_on_an_unknown_batch_is_404(self):
        r = self._post_candidate(str(uuid.uuid4()), external_id="x")
        self.assertEqual(r.status_code, 404)

    def test_candidate_cannot_claim_another_persons_trip(self):
        bid = self._open_batch()
        r = self._post_candidate(bid, external_id="x",
                                 trip_id=self.other_trip_id)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(repo.candidates_list(batch_id=bid), [])

    def test_off_enum_taken_at_source_is_400(self):
        bid = self._open_batch()
        r = self._post_candidate(bid, external_id="x",
                                 taken_at_source="astrology")
        self.assertEqual(r.status_code, 400)
        self.assertIn("taken_at_source", r.json()["detail"])

    def test_off_enum_location_source_is_400(self):
        bid = self._open_batch()
        r = self._post_candidate(bid, external_id="x",
                                 location_source="vibes")
        self.assertEqual(r.status_code, 400)
        self.assertIn("location_source", r.json()["detail"])

    def test_posting_the_same_external_id_twice_returns_the_same_row(self):
        bid = self._open_batch()
        first = self._new_candidate(bid, external_id="dup-1")
        second = self._new_candidate(bid, external_id="dup-1")
        self.assertEqual(first, second)
        self.assertEqual(len(repo.candidates_list(batch_id=bid)), 1)

    def test_match_reason_round_trips_as_an_object(self):
        reason = {
            "rule": "exif_time_within_trip",
            "trip_window": {"start": "2026-06-01", "end": "2026-06-14"},
            "signals": ["exif_datetime", "gps_in_bbox"],
            "score": 0.82,
        }
        bid = self._open_batch()
        r = self._post_candidate(bid, external_id="mr-1",
                                 match_reason=reason, match_confidence=0.82)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["candidate"]["match_reason"], reason)

        got = self.client.get("/api/import-provenance/candidates",
                              params={"batch_id": bid}).json()
        self.assertEqual(got["candidates"][0]["match_reason"], reason)

    def test_list_orders_oldest_first_within_the_same_second(self):
        """created_at is whole seconds, so a batch that lands together
        would sort by uuid if the tiebreak were the id. The queue must
        come back in the order the operator's material arrived."""
        bid = self._open_batch()
        ids = [self._new_candidate(bid, external_id="ord-%02d" % i)
               for i in range(10)]
        r = self.client.get("/api/import-provenance/candidates",
                            params={"batch_id": bid})
        self.assertEqual([c["id"] for c in r.json()["candidates"]], ids)

    def test_list_filters_by_trip_person_state_and_limit(self):
        bound = self._open_batch(trip_id=self.trip_id)
        on_trip = self._new_candidate(bound, external_id="a")
        loose = self._new_candidate(self._open_batch(), external_id="b")

        r = self.client.get("/api/import-provenance/candidates",
                            params={"trip_id": self.trip_id})
        self.assertEqual([c["id"] for c in r.json()["candidates"]], [on_trip])

        r = self.client.get("/api/import-provenance/candidates",
                            params={"person_id": self.person_id,
                                    "state": "pending"})
        self.assertEqual(sorted(c["id"] for c in r.json()["candidates"]),
                         sorted([on_trip, loose]))

        r = self.client.get("/api/import-provenance/candidates",
                            params={"person_id": self.person_id, "limit": 1})
        self.assertEqual(r.json()["count"], 1)

    def test_a_candidate_inherits_the_trip_its_batch_is_bound_to(self):
        """The operator bound the batch to a trip; every item that lands
        in it is filed there without the caller restating it."""
        bid = self._open_batch(trip_id=self.trip_id)
        cid = self._new_candidate(bid, external_id="inherit")
        self.assertEqual(
            self.client.get("/api/import-provenance/candidates/%s" % cid)
                .json()["candidate"]["trip_id"], self.trip_id)

    def test_listing_a_person_against_someone_elses_trip_is_409(self):
        """Not an empty list. 'This person has nothing on that trip' and
        'that trip is not theirs' are different facts."""
        r = self.client.get("/api/import-provenance/candidates",
                            params={"person_id": self.person_id,
                                    "trip_id": self.other_trip_id})
        self.assertEqual(r.status_code, 409)

    def test_listing_an_unknown_state_is_400(self):
        r = self.client.get("/api/import-provenance/candidates",
                            params={"state": "needs_review"})
        self.assertEqual(r.status_code, 400)

    def test_get_unknown_candidate_is_404(self):
        r = self.client.get("/api/import-provenance/candidates/%s"
                            % uuid.uuid4())
        self.assertEqual(r.status_code, 404)

    def test_set_candidate_trip_then_unfile(self):
        cid = self._new_candidate(external_id="f-1")
        r = self.client.patch(
            "/api/import-provenance/candidates/%s/trip" % cid,
            json={"trip_id": self.trip_id})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["candidate"]["trip_id"], self.trip_id)

        r = self.client.patch(
            "/api/import-provenance/candidates/%s/trip" % cid,
            json={"trip_id": None})
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()["candidate"]["trip_id"])

    def test_set_candidate_trip_across_people_is_409(self):
        cid = self._new_candidate(external_id="f-2")
        r = self.client.patch(
            "/api/import-provenance/candidates/%s/trip" % cid,
            json={"trip_id": self.other_trip_id})
        self.assertEqual(r.status_code, 409)
        self.assertIsNone(repo.candidate_get(cid)["trip_id"])

    def test_candidate_cannot_disagree_with_its_bound_batch(self):
        other_trip_same_person = self._insert_trip(self.person_id, "Japan 2027")
        bid = self._open_batch(trip_id=self.trip_id)
        cid = self._new_candidate(bid, external_id="f-3")
        r = self.client.patch(
            "/api/import-provenance/candidates/%s/trip" % cid,
            json={"trip_id": other_trip_same_person})
        self.assertEqual(r.status_code, 409)

    def test_hidden_candidate_leaves_the_default_queue_and_can_come_back(self):
        bid = self._open_batch()
        cid = self._new_candidate(bid, external_id="h-1")
        self.client.patch(
            "/api/import-provenance/candidates/%s/hidden" % cid,
            json={"hidden": True})
        self.assertEqual(
            self.client.get("/api/import-provenance/candidates",
                            params={"batch_id": bid}).json()["count"], 0)
        shown = self.client.get(
            "/api/import-provenance/candidates",
            params={"batch_id": bid, "include_hidden": "true"}).json()
        self.assertEqual([c["id"] for c in shown["candidates"]], [cid])

        self.client.patch(
            "/api/import-provenance/candidates/%s/hidden" % cid,
            json={"hidden": False})
        self.assertEqual(
            self.client.get("/api/import-provenance/candidates",
                            params={"batch_id": bid}).json()["count"], 1)

    def test_hiding_an_unknown_candidate_is_404(self):
        r = self.client.patch(
            "/api/import-provenance/candidates/%s/hidden" % uuid.uuid4(),
            json={"hidden": True})
        self.assertEqual(r.status_code, 404)


# ======================================================================
#  4 -- DECISIONS: INTAKE IS NOT APPROVAL, OVER HTTP
# ======================================================================


class DecisionRouteTests(_Base):

    def test_accept_without_a_photo_is_409(self):
        cid = self._new_candidate(external_id="d-1")
        r = self._decide(cid, state="accepted")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(repo.candidate_get(cid)["state"], "pending")

    def test_accept_onto_another_persons_photo_is_409(self):
        cid = self._new_candidate(external_id="d-2")
        r = self._decide(cid, state="accepted",
                         photo_id=self._insert_photo(self.other_person_id))
        self.assertEqual(r.status_code, 409)
        self.assertIn("another narrator", r.json()["detail"])
        self.assertEqual(repo.candidate_get(cid)["state"], "pending")

    def test_accept_onto_a_photo_that_does_not_exist_is_409(self):
        cid = self._new_candidate(external_id="d-3")
        r = self._decide(cid, state="accepted", photo_id=str(uuid.uuid4()))
        self.assertEqual(r.status_code, 409)

    def test_accept_onto_an_owned_photo_records_the_decision(self):
        cid = self._new_candidate(external_id="d-4")
        photo_id = self._insert_photo(self.person_id)
        r = self._decide(cid, state="accepted", photo_id=photo_id,
                         state_reason="operator confirmed the day",
                         reviewed_by_user_id="chris")
        self.assertEqual(r.status_code, 200, r.text)
        cand = r.json()["candidate"]
        self.assertEqual(cand["state"], "accepted")
        self.assertEqual(cand["photo_id"], photo_id)
        self.assertEqual(cand["state_reason"], "operator confirmed the day")
        self.assertEqual(cand["reviewed_by_user_id"], "chris")
        self.assertIsNotNone(cand["reviewed_at"])

    def test_accepting_does_not_write_to_the_photos_row(self):
        """Acceptance records a promotion that happened somewhere else.
        It does not perform one, so the photo must come out byte-for-byte
        the way it went in -- including whatever approval columns the
        photos table happens to carry."""
        cid = self._new_candidate(external_id="d-5")
        photo_id = self._insert_photo(self.person_id)
        before = self._photo_row(photo_id)
        r = self._decide(cid, state="accepted", photo_id=photo_id)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self._photo_row(photo_id), before)

    def test_a_rejection_cannot_carry_a_photo(self):
        cid = self._new_candidate(external_id="d-6")
        r = self._decide(cid, state="rejected",
                         photo_id=self._insert_photo(self.person_id))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(repo.candidate_get(cid)["state"], "pending")

    def test_rejection_duplicate_and_error_are_recorded_with_a_reason(self):
        for state in ("rejected", "duplicate", "error"):
            with self.subTest(state=state):
                cid = self._new_candidate(external_id="d-%s" % state)
                r = self._decide(cid, state=state,
                                 state_reason="because %s" % state)
                self.assertEqual(r.status_code, 200, r.text)
                cand = r.json()["candidate"]
                self.assertEqual(cand["state"], state)
                self.assertEqual(cand["state_reason"], "because %s" % state)
                self.assertIsNone(cand["photo_id"])

    def test_pending_is_not_a_decision(self):
        cid = self._new_candidate(external_id="d-7")
        r = self._decide(cid, state="pending")
        self.assertEqual(r.status_code, 400)
        self.assertIn("not a decision", r.json()["detail"])

    def test_epic_plan_states_that_0037_never_shipped_are_400(self):
        """The plan drafted needs_review / changed / skipped. 0037 has
        none of them. The route refuses rather than guessing a mapping;
        naming them is a WO-2 decision, not a Phase 4 one."""
        cid = self._new_candidate(external_id="d-8")
        for state in ("needs_review", "changed", "skipped", "hidden"):
            with self.subTest(state=state):
                r = self._decide(cid, state=state)
                self.assertEqual(r.status_code, 400)

    def test_deciding_an_unknown_candidate_is_404(self):
        r = self._decide(str(uuid.uuid4()), state="rejected")
        self.assertEqual(r.status_code, 404)

    def test_a_decision_updates_the_batch_counters(self):
        bid = self._open_batch()
        c1 = self._new_candidate(bid, external_id="c-1")
        self._new_candidate(bid, external_id="c-2")
        self._decide(c1, state="rejected", state_reason="blurry")
        counts = self.client.get(
            "/api/import-provenance/batches/%s/counts" % bid).json()["counts"]
        self.assertEqual(counts["total"], 2)
        self.assertEqual(counts["pending"], 1)
        self.assertEqual(counts["rejected"], 1)
        self.assertEqual(counts["stored_candidate_count"], 2)


# ======================================================================
#  5 -- A REFUSAL IS NOT A CRASH
# ======================================================================


class TokenRefusalRouteTests(_Base):

    def _assert_refused_without_echoing(self, response):
        self.assertEqual(response.status_code, 400,
                         "a refused credential must not surface as %s"
                         % response.status_code)
        self.assertNotIn(_FAKE_TOKEN, response.text)

    def test_a_token_in_external_ref_is_400(self):
        self._assert_refused_without_echoing(
            self._post_batch(external_ref=_FAKE_TOKEN))

    def test_a_token_in_label_is_400(self):
        self._assert_refused_without_echoing(
            self._post_batch(label="picker run " + _FAKE_TOKEN))

    def test_a_token_in_notes_is_400(self):
        self._assert_refused_without_echoing(
            self._post_batch(notes=_FAKE_TOKEN))

    def test_a_token_in_a_candidate_external_id_is_400(self):
        bid = self._open_batch()
        self._assert_refused_without_echoing(
            self._post_candidate(bid, external_id=_FAKE_TOKEN))

    def test_a_secret_key_in_match_reason_is_400(self):
        bid = self._open_batch()
        r = self._post_candidate(
            bid, external_id="mr-secret",
            match_reason={"rule": "exif", "access_token": _FAKE_TOKEN})
        self._assert_refused_without_echoing(r)
        self.assertIn("access_token", r.json()["detail"])

    def test_a_secret_key_nested_in_match_reason_is_400(self):
        bid = self._open_batch()
        self._assert_refused_without_echoing(self._post_candidate(
            bid, external_id="mr-nested",
            match_reason={"provider": {"headers": {"authorization": "x"}}}))

    def test_a_token_in_a_failure_reason_is_400(self):
        bid = self._open_batch()
        self._assert_refused_without_echoing(self.client.post(
            "/api/import-provenance/batches/%s/close" % bid,
            json={"failed": True, "failure_reason": _FAKE_TOKEN}))

    def test_a_token_in_a_state_reason_is_400(self):
        cid = self._new_candidate(external_id="t-1")
        self._assert_refused_without_echoing(
            self._decide(cid, state="rejected", state_reason=_FAKE_TOKEN))
        self.assertEqual(repo.candidate_get(cid)["state"], "pending")

    def test_the_refusal_names_the_field_so_the_operator_can_fix_it(self):
        r = self._post_batch(external_ref=_FAKE_TOKEN)
        self.assertIn("external_ref", r.json()["detail"])

    def test_every_repository_error_has_a_deliberate_status(self):
        """No refusal falls through to 500 by accident."""
        for kind in (repo.BatchNotFoundError, repo.CandidateNotFoundError,
                     repo.CrossPersonError, repo.CrossTripError,
                     repo.IntakeIsNotApprovalError, repo.BatchClosedError,
                     repo.ExternalTokenError, repo.InvalidStateError):
            with self.subTest(error=kind.__name__):
                self.assertLess(ip._status_for(kind("x")), 500)
        # The base class is the drifted-database case, and that IS a 500.
        self.assertEqual(ip._status_for(repo.ImportRepositoryError("x")), 500)


# ======================================================================
#  6 -- NO DELETE, AND THE ROUTER IS ACTUALLY WIRED UP
# ======================================================================


class NoDeleteAndWiringTests(_Base):

    def test_the_router_declares_no_delete_method(self):
        for route in ip.router.routes:
            with self.subTest(path=route.path):
                self.assertNotIn("DELETE", getattr(route, "methods", set()) or set())

    def test_the_router_source_contains_no_delete_statement(self):
        with io.open(_ROUTER_PATH, "r", encoding="utf-8") as fh:
            src = fh.read()
        upper = src.upper()
        self.assertNotIn("@ROUTER.DELETE", upper)
        self.assertNotIn("DELETE FROM", upper)
        self.assertNotIn("DROP TABLE", upper)

    def test_the_router_is_registered_in_main(self):
        with io.open(_MAIN_PATH, "r", encoding="utf-8") as fh:
            main_src = fh.read()
        self.assertIn("import_provenance,", main_src)
        self.assertIn("app.include_router(import_provenance.router)", main_src)

    def test_every_route_lives_under_the_one_prefix(self):
        for route in ip.router.routes:
            with self.subTest(path=route.path):
                self.assertTrue(route.path.startswith("/api/import-provenance"))

    def test_enums_are_read_from_the_repository_not_restated(self):
        r = self.client.get("/api/import-provenance/enums")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["import_sources"], list(repo.IMPORT_SOURCES))
        self.assertEqual(body["batch_statuses"], list(repo.BATCH_STATUSES))
        self.assertEqual(body["candidate_states"], list(repo.CANDIDATE_STATES))
        self.assertEqual(body["decidable_states"], list(repo.DECIDABLE_STATES))
        self.assertNotIn("pending", body["decidable_states"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
