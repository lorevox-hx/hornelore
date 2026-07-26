"""WO-TRAVEL-DOC-IMPORT-PROVENANCE-FOUNDATION-01 Phase 3 -- repository lock.

Migration 0037 built the import landing zone and stated four rules.
tests/test_import_provenance_foundation_migration.py locks the half a
schema can hold. This file locks the other half -- the rules that need a
procedure, enforced in api/services/import_repository.py:

  1. INTAKE IS NOT APPROVAL. A candidate is born 'pending'. There is no
     argument anywhere in this module that can set narrator readiness or
     memoir inclusion. Acceptance requires a photos row that already
     exists and belongs to the same person, because acceptance records a
     promotion rather than asserting one.

  2. CANDIDATES CANNOT CROSS THE PERSON/TRIP BOUNDARY. person_id is
     copied from the batch and is not a parameter at all. Every place a
     foreign row could smuggle in a second person -- binding a trip,
     filing a candidate under a trip, accepting onto a photo -- refuses.

  3. NO RAW EXTERNAL TOKENS. Caller strings are scanned for the shapes a
     replayable credential actually takes, and match_reason keys are
     checked against a secret-ish name list, before any write opens.

  4. REVERSIBLE, NOT DESTRUCTIVE. There is no DELETE in the module. That
     is asserted against the source text, not just behaviour, so a
     future edit has to argue for it in review.

Plus the delegated one: match_reason_json round-trips. What the importer
put in is what the Evidence Review Queue gets back -- object for object,
never a summary.

Fresh sqlite fixture per test. pytest is not installed in this repo;
run with:  python3 -m unittest tests.test_import_repository
"""
from __future__ import annotations

import io
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
from api.services import import_repository as repo  # noqa: E402

_MODULE_PATH = (_SERVER_CODE / "api" / "services" / "import_repository.py")


def _now() -> str:
    return "2026-07-26T00:00:00Z"


class _Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        tmp.close()
        self.db_path = Path(tmp.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()

        self.person_id = self._insert_person("Christopher Todd Horne")
        self.other_person_id = self._insert_person("Kent James Horne")
        self.trip_id = self._insert_trip(self.person_id, "Europe 2026")
        self.other_trip_id = self._insert_trip(self.other_person_id, "Not His")

    def tearDown(self):
        _db.DB_PATH = self._orig_db
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

    def _open_batch(self, person_id=None, trip_id=None, source="local_upload"):
        return repo.batch_create(
            person_id=person_id or self.person_id, source=source,
            trip_id=trip_id,
        )


# ══════════════════════════════════════════════════════════════════════
#  RULE 1 -- INTAKE IS NOT APPROVAL
# ══════════════════════════════════════════════════════════════════════


class IntakeIsNotApprovalTests(_Base):

    def test_candidate_is_born_pending_with_no_photo(self):
        bid = self._open_batch()
        cid = repo.candidate_create(bid, external_id="ext-1")
        cand = repo.candidate_get(cid)
        self.assertEqual(cand["state"], "pending")
        self.assertIsNone(cand["photo_id"])
        self.assertIsNone(cand["reviewed_at"])
        self.assertIsNone(cand["reviewed_by_user_id"])

    def test_candidate_create_has_no_approval_parameters(self):
        """The signature is the enforcement. If somebody adds a
        narrator_ready or include_in_memoir kwarg, this fails."""
        import inspect
        params = set(inspect.signature(repo.candidate_create).parameters)
        self.assertNotIn("narrator_ready", params)
        self.assertNotIn("include_in_memoir", params)
        self.assertNotIn("state", params)
        # person_id is copied from the batch, never supplied (rule 2).
        self.assertNotIn("person_id", params)

    def test_accept_requires_a_photo_id(self):
        bid = self._open_batch()
        cid = repo.candidate_create(bid, external_id="ext-1")
        with self.assertRaises(repo.IntakeIsNotApprovalError):
            repo.candidate_decide(cid, "accepted")
        self.assertEqual(repo.candidate_get(cid)["state"], "pending")

    def test_accept_records_an_existing_photo(self):
        bid = self._open_batch()
        cid = repo.candidate_create(bid, external_id="ext-1")
        photo_id = self._insert_photo(self.person_id)
        self.assertTrue(
            repo.candidate_decide(cid, "accepted", photo_id=photo_id,
                                  reviewed_by_user_id="chris")
        )
        cand = repo.candidate_get(cid)
        self.assertEqual(cand["state"], "accepted")
        self.assertEqual(cand["photo_id"], photo_id)
        self.assertEqual(cand["reviewed_by_user_id"], "chris")
        self.assertIsNotNone(cand["reviewed_at"])

    def test_accept_does_not_touch_photo_approval_flags(self):
        """Acceptance is an intake record. It must not reach across and
        mark the photo narrator-ready."""
        bid = self._open_batch()
        cid = repo.candidate_create(bid, external_id="ext-1")
        photo_id = self._insert_photo(self.person_id)
        repo.candidate_decide(cid, "accepted", photo_id=photo_id)
        con = self._con()
        try:
            row = con.execute(
                "SELECT narrator_ready, needs_confirmation, "
                "date_approved_for_lori, location_approved_for_lori "
                "FROM photos WHERE id = ?", (photo_id,),
            ).fetchone()
        finally:
            con.close()
        self.assertEqual(row["narrator_ready"], 0)
        self.assertEqual(row["needs_confirmation"], 1)
        self.assertEqual(row["date_approved_for_lori"], 0)
        self.assertEqual(row["location_approved_for_lori"], 0)

    def test_rejected_candidate_cannot_carry_a_photo(self):
        bid = self._open_batch()
        cid = repo.candidate_create(bid, external_id="ext-1")
        photo_id = self._insert_photo(self.person_id)
        for state in ("rejected", "duplicate", "error"):
            with self.assertRaises(repo.InvalidStateError):
                repo.candidate_decide(cid, state, photo_id=photo_id)
        self.assertEqual(repo.candidate_get(cid)["state"], "pending")

    def test_pending_is_not_a_decision(self):
        bid = self._open_batch()
        cid = repo.candidate_create(bid, external_id="ext-1")
        repo.candidate_decide(cid, "rejected", reason="blurry")
        with self.assertRaises(repo.InvalidStateError):
            repo.candidate_decide(cid, "pending")
        self.assertEqual(repo.candidate_get(cid)["state"], "rejected")

    def test_unknown_state_is_refused(self):
        bid = self._open_batch()
        cid = repo.candidate_create(bid, external_id="ext-1")
        with self.assertRaises(repo.InvalidStateError):
            repo.candidate_decide(cid, "narrator_ready", photo_id=None)

    def test_runtime_guard_fires_if_an_approval_column_appears(self):
        """The migration test locks the schema at build time. This locks
        a live database that drifted -- a hand-run ALTER, a restored
        older file -- so nothing lands in a table that has quietly grown
        approval semantics."""
        bid = self._open_batch()
        con = self._con()
        try:
            con.execute("ALTER TABLE import_candidate "
                        "ADD COLUMN narrator_ready INTEGER NOT NULL DEFAULT 0")
            con.commit()
        finally:
            con.close()
        with self.assertRaises(repo.IntakeIsNotApprovalError):
            repo.candidate_create(bid, external_id="ext-drift")
        self.assertEqual(repo.candidates_list(batch_id=bid), [])


# ══════════════════════════════════════════════════════════════════════
#  RULE 2 -- THE PERSON / TRIP BOUNDARY
# ══════════════════════════════════════════════════════════════════════


class BoundaryTests(_Base):

    def test_candidate_person_is_copied_from_the_batch(self):
        bid = self._open_batch()
        cid = repo.candidate_create(bid, external_id="ext-1")
        self.assertEqual(repo.candidate_get(cid)["person_id"], self.person_id)

    def test_batch_cannot_be_created_on_another_persons_trip(self):
        with self.assertRaises(repo.CrossTripError):
            repo.batch_create(person_id=self.person_id, source="local_upload",
                              trip_id=self.other_trip_id)
        self.assertEqual(repo.batch_list(person_id=self.person_id), [])

    def test_batch_cannot_be_bound_to_another_persons_trip(self):
        bid = self._open_batch()
        with self.assertRaises(repo.CrossTripError):
            repo.batch_bind_trip(bid, self.other_trip_id)
        self.assertIsNone(repo.batch_get(bid)["trip_id"])

    def test_batch_bind_trip_accepts_the_owners_trip(self):
        bid = self._open_batch()
        self.assertTrue(repo.batch_bind_trip(bid, self.trip_id))
        self.assertEqual(repo.batch_get(bid)["trip_id"], self.trip_id)

    def test_candidate_cannot_claim_another_persons_trip(self):
        bid = self._open_batch()
        with self.assertRaises(repo.CrossTripError):
            repo.candidate_create(bid, external_id="ext-1",
                                  trip_id=self.other_trip_id)
        self.assertEqual(repo.candidates_list(batch_id=bid), [])

    def test_candidate_cannot_disagree_with_its_bound_batch(self):
        second_trip = self._insert_trip(self.person_id, "Bismarck")
        bid = self._open_batch(trip_id=self.trip_id)
        with self.assertRaises(repo.CrossTripError):
            repo.candidate_create(bid, external_id="ext-1",
                                  trip_id=second_trip)

    def test_candidate_inherits_the_batch_trip(self):
        bid = self._open_batch(trip_id=self.trip_id)
        cid = repo.candidate_create(bid, external_id="ext-1")
        self.assertEqual(repo.candidate_get(cid)["trip_id"], self.trip_id)

    def test_candidate_set_trip_refuses_another_persons_trip(self):
        bid = self._open_batch()
        cid = repo.candidate_create(bid, external_id="ext-1")
        with self.assertRaises(repo.CrossTripError):
            repo.candidate_set_trip(cid, self.other_trip_id)
        self.assertIsNone(repo.candidate_get(cid)["trip_id"])

    def test_accept_refuses_another_persons_photo(self):
        """The exact confusion the two Christopher rows produced: a photo
        addressable by one person id, a candidate by another."""
        bid = self._open_batch()
        cid = repo.candidate_create(bid, external_id="ext-1")
        foreign_photo = self._insert_photo(self.other_person_id)
        with self.assertRaises(repo.CrossPersonError):
            repo.candidate_decide(cid, "accepted", photo_id=foreign_photo)
        cand = repo.candidate_get(cid)
        self.assertEqual(cand["state"], "pending")
        self.assertIsNone(cand["photo_id"])

    def test_accept_refuses_a_photo_that_does_not_exist(self):
        bid = self._open_batch()
        cid = repo.candidate_create(bid, external_id="ext-1")
        with self.assertRaises(repo.CrossPersonError):
            repo.candidate_decide(cid, "accepted",
                                  photo_id="00000000-0000-0000-0000-0000000000ff")

    def test_batch_refuses_a_person_that_does_not_exist(self):
        with self.assertRaises(repo.CrossPersonError):
            repo.batch_create(person_id="nobody", source="manual")

    def test_list_by_person_never_leaks_across(self):
        mine = self._open_batch()
        theirs = repo.batch_create(person_id=self.other_person_id,
                                   source="manual")
        repo.candidate_create(mine, external_id="a")
        repo.candidate_create(theirs, external_id="b")
        mine_rows = repo.candidates_list(person_id=self.person_id)
        self.assertEqual(len(mine_rows), 1)
        self.assertEqual(mine_rows[0]["person_id"], self.person_id)


# ══════════════════════════════════════════════════════════════════════
#  RULE 3 -- NO RAW EXTERNAL TOKENS
# ══════════════════════════════════════════════════════════════════════


class NoTokenTests(_Base):

    OAUTH_ACCESS = "ya29.a0AfH6SMBx7Qw9ZzKlmnopQRSTUVwxyz1234567890"
    OAUTH_REFRESH = "1//0eXaMpLeReFrEsHtOkEn1234567890"
    JWT = ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
           "dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXk")

    def test_batch_external_ref_refuses_an_access_token(self):
        with self.assertRaises(repo.ExternalTokenError):
            repo.batch_create(person_id=self.person_id,
                              source="google_photos_picker",
                              external_ref=self.OAUTH_ACCESS)
        self.assertEqual(repo.batch_list(person_id=self.person_id), [])

    def test_batch_notes_refuses_a_bearer_header(self):
        with self.assertRaises(repo.ExternalTokenError):
            repo.batch_create(
                person_id=self.person_id, source="manual",
                notes="curl -H 'Authorization: Bearer abcdefghijklmnopqrst'",
            )

    def test_batch_label_refuses_a_credential_bearing_url(self):
        with self.assertRaises(repo.ExternalTokenError):
            repo.batch_create(
                person_id=self.person_id, source="google_takeout",
                label="https://example.test/albums?access_token=zzz",
            )

    def test_candidate_external_id_refuses_a_refresh_token(self):
        bid = self._open_batch()
        with self.assertRaises(repo.ExternalTokenError):
            repo.candidate_create(bid, external_id=self.OAUTH_REFRESH)
        self.assertEqual(repo.candidates_list(batch_id=bid), [])

    def test_candidate_filename_refuses_a_jwt(self):
        bid = self._open_batch()
        with self.assertRaises(repo.ExternalTokenError):
            repo.candidate_create(bid, external_id="ext-1",
                                  filename=self.JWT + ".jpg")

    def test_match_reason_refuses_a_secret_shaped_key(self):
        bid = self._open_batch()
        for key in ("access_token", "refreshToken", "api_key", "Cookie",
                    "client_secret", "password"):
            with self.assertRaises(repo.ExternalTokenError):
                repo.candidate_create(bid, external_id="ext-%s" % key,
                                      match_reason={key: "anything"})
        self.assertEqual(repo.candidates_list(batch_id=bid), [])

    def test_match_reason_refuses_a_nested_token_value(self):
        bid = self._open_batch()
        with self.assertRaises(repo.ExternalTokenError):
            repo.candidate_create(
                bid, external_id="ext-1",
                match_reason={"why": {"source": ["album", self.OAUTH_ACCESS]}},
            )

    def test_decision_reason_refuses_a_token(self):
        bid = self._open_batch()
        cid = repo.candidate_create(bid, external_id="ext-1")
        with self.assertRaises(repo.ExternalTokenError):
            repo.candidate_decide(cid, "rejected", reason=self.JWT)
        self.assertEqual(repo.candidate_get(cid)["state"], "pending")

    def test_opaque_provider_ids_still_pass(self):
        """The guard must not eat the thing external_ref exists for. A
        Google Photos media id and a Takeout archive name are long and
        random-looking and are not credentials."""
        bid = repo.batch_create(
            person_id=self.person_id, source="google_photos_picker",
            external_ref="AF1QipMv3nJ7dQ2xKcQ0d8Yb1RmZpLwT9NcXhVuEoAaB",
            label="takeout-20260517T093012Z-001.tgz",
        )
        cid = repo.candidate_create(
            bid,
            external_id="AF1QipPq8sT4wZ2vNhKcL0mBxYd7RtEuJgHiOaWcQzXy",
            file_hash="9f2b1c8ad4e7f60351bb9c2e77a10d4488ff3c21",
            filename="IMG_20260517_093012.jpg",
        )
        self.assertIsNotNone(repo.candidate_get(cid))


# ══════════════════════════════════════════════════════════════════════
#  MATCH REASON ROUND-TRIP
# ══════════════════════════════════════════════════════════════════════


class MatchReasonRoundTripTests(_Base):

    def test_nested_reason_comes_back_equal(self):
        reason = {
            "rule": "exif_time_within_trip_window",
            "confidence_inputs": {"delta_seconds": 412, "gps_km": 1.75},
            "trip_window": ["2026-05-17", "2026-05-19"],
            "signals": ["exif_datetime", "exif_gps", "album_name"],
            "album": {"name": "Praha", "index": 3, "primary": True},
            "ambiguous": False,
            "runner_up": None,
        }
        bid = self._open_batch()
        cid = repo.candidate_create(bid, external_id="ext-1",
                                    match_reason=reason, match_confidence=0.82)
        cand = repo.candidate_get(cid)
        self.assertEqual(cand["match_reason"], reason)
        self.assertAlmostEqual(cand["match_confidence"], 0.82)

    def test_unicode_survives_the_round_trip(self):
        reason = {"place": "Ceske Budejovice / České Budějovice",
                  "note": "album titled “Praha → Wien”"}
        bid = self._open_batch()
        cid = repo.candidate_create(bid, external_id="ext-1",
                                    match_reason=reason)
        self.assertEqual(repo.candidate_get(cid)["match_reason"], reason)

    def test_absent_reason_is_an_empty_object_not_null(self):
        bid = self._open_batch()
        cid = repo.candidate_create(bid, external_id="ext-1")
        cand = repo.candidate_get(cid)
        self.assertEqual(cand["match_reason"], {})
        self.assertEqual(cand["match_reason_json"], "{}")

    def test_reason_must_be_an_object_not_prose(self):
        bid = self._open_batch()
        with self.assertRaises(repo.InvalidStateError):
            repo.candidate_create(bid, external_id="ext-1",
                                  match_reason="it looked about right")

    def test_reason_survives_a_decision(self):
        reason = {"rule": "gps_within_stop_radius", "radius_km": 2}
        bid = self._open_batch()
        cid = repo.candidate_create(bid, external_id="ext-1",
                                    match_reason=reason)
        repo.candidate_decide(cid, "rejected", reason="operator says no")
        cand = repo.candidate_get(cid)
        self.assertEqual(cand["match_reason"], reason)
        self.assertEqual(cand["state_reason"], "operator says no")


# ══════════════════════════════════════════════════════════════════════
#  RULE 4 -- REVERSIBLE, NOT DESTRUCTIVE
# ══════════════════════════════════════════════════════════════════════


class ReversibilityTests(_Base):

    def test_module_contains_no_delete_or_drop(self):
        with io.open(str(_MODULE_PATH), encoding="utf-8") as fh:
            src = fh.read()
        upper = src.upper()
        self.assertNotIn("DELETE FROM", upper)
        self.assertNotIn("DROP TABLE", upper)

    def test_hiding_a_candidate_keeps_everything(self):
        reason = {"rule": "album_name"}
        bid = self._open_batch()
        cid = repo.candidate_create(bid, external_id="ext-1",
                                    match_reason=reason)
        repo.candidate_decide(cid, "rejected", reason="duplicate of ext-0")
        self.assertTrue(repo.candidate_hide(cid))

        self.assertEqual(repo.candidates_list(batch_id=bid), [])
        shown = repo.candidates_list(batch_id=bid, include_hidden=True)
        self.assertEqual(len(shown), 1)
        self.assertEqual(shown[0]["hidden"], 1)
        self.assertIsNotNone(shown[0]["hidden_at"])
        self.assertEqual(shown[0]["match_reason"], reason)
        self.assertEqual(shown[0]["state"], "rejected")
        self.assertEqual(shown[0]["state_reason"], "duplicate of ext-0")

        self.assertTrue(repo.candidate_hide(cid, hidden=False))
        back = repo.candidates_list(batch_id=bid)
        self.assertEqual(len(back), 1)
        self.assertEqual(back[0]["hidden"], 0)
        self.assertIsNone(back[0]["hidden_at"])
        self.assertEqual(back[0]["match_reason"], reason)

    def test_hiding_a_batch_is_reversible(self):
        bid = self._open_batch()
        repo.batch_hide(bid)
        self.assertEqual(repo.batch_list(person_id=self.person_id), [])
        self.assertEqual(
            len(repo.batch_list(person_id=self.person_id, include_hidden=True)),
            1,
        )
        repo.batch_hide(bid, hidden=False)
        self.assertEqual(len(repo.batch_list(person_id=self.person_id)), 1)

    def test_hidden_candidates_still_count(self):
        """Hiding retires a row from a view. It does not claim the import
        never happened, so the counters keep counting it."""
        bid = self._open_batch()
        cid = repo.candidate_create(bid, external_id="ext-1")
        repo.candidate_hide(cid)
        self.assertEqual(repo.batch_counts(bid)["total"], 1)
        self.assertEqual(repo.batch_get(bid)["candidate_count"], 1)


# ══════════════════════════════════════════════════════════════════════
#  BATCH LIFECYCLE, IDEMPOTENCY, COUNTERS
# ══════════════════════════════════════════════════════════════════════


class BatchLifecycleTests(_Base):

    def test_unknown_source_is_refused(self):
        with self.assertRaises(repo.InvalidStateError):
            repo.batch_create(person_id=self.person_id, source="dropbox")

    def test_every_documented_source_is_accepted(self):
        for src in repo.IMPORT_SOURCES:
            bid = repo.batch_create(person_id=self.person_id, source=src)
            self.assertEqual(repo.batch_get(bid)["source"], src)

    def test_closed_batch_refuses_new_candidates(self):
        bid = self._open_batch()
        repo.candidate_create(bid, external_id="ext-1")
        repo.batch_close(bid)
        self.assertEqual(repo.batch_get(bid)["status"], "closed")
        with self.assertRaises(repo.BatchClosedError):
            repo.candidate_create(bid, external_id="ext-2")
        self.assertEqual(len(repo.candidates_list(batch_id=bid)), 1)

    def test_failed_batch_keeps_what_landed(self):
        bid = self._open_batch()
        repo.candidate_create(bid, external_id="ext-1")
        repo.batch_close(bid, failed=True, failure_reason="picker timed out")
        batch = repo.batch_get(bid)
        self.assertEqual(batch["status"], "failed")
        self.assertEqual(batch["failure_reason"], "picker timed out")
        self.assertEqual(len(repo.candidates_list(batch_id=bid)), 1)

    def test_reopen_clears_failure_and_allows_the_retry(self):
        bid = self._open_batch()
        repo.batch_close(bid, failed=True, failure_reason="picker timed out")
        self.assertTrue(repo.batch_reopen(bid))
        batch = repo.batch_get(bid)
        self.assertEqual(batch["status"], "open")
        self.assertIsNone(batch["failure_reason"])
        self.assertIsNone(batch["closed_at"])
        repo.candidate_create(bid, external_id="ext-2")
        self.assertEqual(len(repo.candidates_list(batch_id=bid)), 1)

    def test_replaying_a_fetch_is_idempotent(self):
        """The UNIQUE (batch_id, external_id) index says re-running the
        same fetch must not duplicate. The repository honours it by
        returning the existing id rather than raising."""
        bid = self._open_batch()
        first = repo.candidate_create(bid, external_id="ext-1",
                                      match_reason={"rule": "exif"})
        second = repo.candidate_create(bid, external_id="ext-1",
                                       match_reason={"rule": "different"})
        self.assertEqual(first, second)
        rows = repo.candidates_list(batch_id=bid)
        self.assertEqual(len(rows), 1)
        # First write wins; a replay does not silently rewrite history.
        self.assertEqual(rows[0]["match_reason"], {"rule": "exif"})

    def test_same_external_id_in_a_different_batch_is_a_new_row(self):
        one = self._open_batch()
        two = self._open_batch()
        a = repo.candidate_create(one, external_id="ext-1")
        b = repo.candidate_create(two, external_id="ext-1")
        self.assertNotEqual(a, b)

    def test_counters_are_recomputed_not_incremented(self):
        bid = self._open_batch()
        cids = [repo.candidate_create(bid, external_id="ext-%d" % i)
                for i in range(4)]
        self.assertEqual(repo.batch_get(bid)["candidate_count"], 4)

        photo_id = self._insert_photo(self.person_id)
        repo.candidate_decide(cids[0], "accepted", photo_id=photo_id)
        repo.candidate_decide(cids[1], "rejected")
        repo.candidate_decide(cids[2], "duplicate")

        batch = repo.batch_get(bid)
        self.assertEqual(batch["candidate_count"], 4)
        self.assertEqual(batch["accepted_count"], 1)
        self.assertEqual(batch["rejected_count"], 2)

        # Replaying the same decision must not drift the counters.
        repo.candidate_decide(cids[1], "rejected", reason="again")
        batch = repo.batch_get(bid)
        self.assertEqual(batch["accepted_count"], 1)
        self.assertEqual(batch["rejected_count"], 2)

        counts = repo.batch_counts(bid)
        self.assertEqual(counts["total"], 4)
        self.assertEqual(counts["pending"], 1)
        self.assertEqual(counts["accepted"], 1)
        self.assertEqual(counts["rejected"], 1)
        self.assertEqual(counts["duplicate"], 1)
        self.assertEqual(counts["stored_candidate_count"], 4)

    def test_off_enum_metadata_sources_are_refused(self):
        bid = self._open_batch()
        with self.assertRaises(repo.InvalidStateError):
            repo.candidate_create(bid, external_id="a",
                                  taken_at_source="guessed")
        with self.assertRaises(repo.InvalidStateError):
            repo.candidate_create(bid, external_id="b",
                                  location_source="vibes")

    def test_missing_batch_and_candidate_are_named_errors(self):
        with self.assertRaises(repo.BatchNotFoundError):
            repo.candidate_create("no-such-batch", external_id="x")
        with self.assertRaises(repo.CandidateNotFoundError):
            repo.candidate_decide("no-such-candidate", "rejected")

    def test_person_hard_delete_cascades_the_landing_zone(self):
        """Migration 0037 gave both tables ON DELETE CASCADE from people.
        The repository never deletes, so the cascade is the only way rows
        leave -- worth asserting it actually reaches them."""
        bid = self._open_batch()
        repo.candidate_create(bid, external_id="ext-1")
        con = self._con()
        try:
            con.execute("DELETE FROM people WHERE id = ?", (self.person_id,))
            con.commit()
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM import_batch").fetchone()[0], 0)
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM import_candidate")
                   .fetchone()[0], 0)
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
