"""The smallest usable Google Photos workflow, locked end to end.

    Google Photos -> import -> Evidence Queue -> approve
                  -> attach to trip/day -> photo on the day card

Written 2026-07-29, when the Phase 1/2B wall was moved forward. The wall
said `google_photos_picker` may not promote. Its reason was sound and is
quoted in full where it was retired (`import_repository.candidate_promote`,
`routers/google_picker.py`, and the three moved-forward wall tests): a
provider source added to a promotion allowlist WITHOUT a byte fetch would
turn promotion into a way to mint `photos` rows for pictures that do not
exist on this machine.

Phase 2B built the fetch. So the wall did not come down -- it moved to
the thing it was actually protecting. Promotion's precondition is no
longer "the source's name is on a list". It is:

    A VERIFIED LOCAL SOURCE FILE IS AVAILABLE TO PROMOTION.

That is strictly stronger than the allowlist ever was. A `local_upload`
batch passed the old check by name alone; a picker batch passes this one
only by producing bytes that hash to the digest the candidate recorded at
acquisition time.

The ten behaviours this file locks, in Chris's numbering:

  1. A Picker candidate with a valid staged original promotes with no
     multipart upload.
  2. The staged file is hash-verified before promotion.
  3. Missing or corrupt staged bytes refuse, changing no candidate, no
     photo and no link row.
  4. A promoted candidate is idempotent -- reported as already promoted,
     never duplicated.
  5. Provider identity stays in `external_id`; no provider session handle
     appears in any response.
  6. A promoted photo links to an existing `trip_day_id`.
  7. Repeating the placement creates no second link.
  8. A day outside the candidate's trip is refused.
  9. The queue tells the browser a Picker candidate needs no file chooser
     -- as a fact about the candidate, not a list of source names -- and
     the drawer obeys that fact.
 10. The day the operator chose then reports the photo.

Both routers are mounted on ONE app on purpose. Promotion and placement
are two requests in the real workflow, and the thing worth proving is
that the photo_id handed back by the first is accepted by the second.

Fresh sqlite, fresh DATA_DIR, fresh app per test. pytest is not installed
in this repo; run with:

    .venv/bin/python -u -m unittest tests.test_picker_promote_to_day
"""
from __future__ import annotations

import hashlib
import os
import shutil
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
from api.routers import trips as trips_router  # noqa: E402
from api.services import import_repository as repo  # noqa: E402

_UI_PATH = _REPO_ROOT / "ui" / "js" / "travel-doc-lab.js"

_PROV_FLAG = "HORNELORE_IMPORT_PROVENANCE"
_TRIPS_FLAG = "HORNELORE_TRIPS"

# A real 1x1 PNG: store_photo_file hashes it and the thumbnailer opens
# it, so a text blob would exercise only the failure path.
_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00"
    b"\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
_PNG_SHA = hashlib.sha256(_PNG).hexdigest()

# The shape of a Google media item id. Kept here as a literal so the
# "provider identity survives" assertions are checking a real value and
# not a placeholder that could never have leaked.
_EXTERNAL_ID = "AMLNta_test_media_item_0001"

# What must never come back out of any response on this lane. The picker
# session handle is the dangerous one: it is bearer-equivalent for the
# life of the session.
_PICKER_SESSION_HANDLE = "356905de-6cc2-4ee4-9a3e-4620d8a5d9d9"
_FORBIDDEN = ("ya29.", "GOCSPX", "client_secret", "access_" + "token",
              "refresh_" + "token", "Bearer ", "baseUrl", "base_url",
              "googleusercontent", "googleapis.com", _PICKER_SESSION_HANDLE)


def _now() -> str:
    return "2026-07-29T00:00:00Z"


class _Base(unittest.TestCase):
    """Fresh DB, fresh archive + staging root, both flags on."""

    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        tmp.close()
        self.db_path = Path(tmp.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()

        # DATA_DIR is read at call time, and it roots BOTH the archive
        # and the import staging tree. One temp root keeps a test run
        # from ever touching the real one.
        self.data_dir = Path(tempfile.mkdtemp(prefix="pk_promote_"))
        self._orig_data_dir = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = str(self.data_dir)

        self._orig_flags = {k: os.environ.get(k)
                            for k in (_PROV_FLAG, _TRIPS_FLAG)}
        os.environ[_PROV_FLAG] = "1"
        os.environ[_TRIPS_FLAG] = "1"

        app = FastAPI()
        app.include_router(ip.router)
        app.include_router(trips_router.router)
        self.client = TestClient(app, raise_server_exceptions=False)

        self.person_id = self._insert_person("Christopher Todd Horne")
        self.other_person_id = self._insert_person("Kent James Horne")
        self.trip_id, self.day_ids = self._new_trip("Bismarck Trip")

    def tearDown(self):
        self.client.close()
        _db.DB_PATH = self._orig_db
        for key, val in self._orig_flags.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        if self._orig_data_dir is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self._orig_data_dir
        shutil.rmtree(self.data_dir, ignore_errors=True)
        try:
            self.db_path.unlink()
        except OSError:
            pass

    # -- fixture -------------------------------------------------------

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
                "INSERT INTO people (id, display_name, created_at, updated_at)"
                " VALUES (?, ?, ?, ?)", (pid, name, _now(), _now()))
            con.commit()
        finally:
            con.close()
        return pid

    def _new_trip(self, title: str, person_id=None):
        """Create a trip through the real route so its days are the days
        the auto-generator makes -- the same rows the operator picks from
        in the drawer."""
        r = self.client.post("/api/trips", json={
            "person_id": person_id or self.person_id,
            "title": title,
            "start_date": "2026-07-14",
            "end_date": "2026-07-16",
        })
        self.assertEqual(r.status_code, 200, r.text)
        trip_id = r.json()["trip_id"]
        d = self.client.get("/api/trips/%s/days" % trip_id)
        self.assertEqual(d.status_code, 200, d.text)
        day_ids = [row["id"] for row in d.json()["days"]]
        self.assertTrue(day_ids, d.text)
        return trip_id, day_ids

    # -- the picker lane, without the network --------------------------

    def _picker_batch(self, source: str = "google_photos_picker") -> str:
        r = self.client.post("/api/import-provenance/batches", json={
            "person_id": self.person_id, "source": source,
            "trip_id": self.trip_id,
        })
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["batch"]["id"]

    def _candidate(self, batch_id: str, **over) -> str:
        body = {
            "external_id": _EXTERNAL_ID,
            "file_hash": _PNG_SHA,
            "filename": "PXL_20260715_010002448.jpg",
            "mime_type": "image/png",
            "byte_size": len(_PNG),
            "taken_at": "2026-07-15T01:00:02Z",
            "taken_at_source": "exif",
            "trip_id": self.trip_id,
        }
        body.update(over)
        r = self.client.post(
            "/api/import-provenance/batches/%s/candidates" % batch_id,
            json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["candidate"]["id"]

    def _stage(self, batch_id: str, candidate_id: str,
               data: bytes = _PNG, ext: str = "png") -> Path:
        """Write the file the acquisition lane would have written.

        Deliberately built by hand rather than by calling the acquire
        service: this file is about what promotion does with a staged
        original, and a test that had to run a download first would fail
        for reasons that have nothing to do with promotion."""
        d = (self.data_dir / "import_staging" / batch_id / candidate_id)
        d.mkdir(parents=True, exist_ok=True)
        p = d / ("original.%s" % ext)
        p.write_bytes(data)
        return p

    def _staged_candidate(self, **over):
        batch_id = self._picker_batch()
        cid = self._candidate(batch_id, **over)
        path = self._stage(batch_id, cid)
        return batch_id, cid, path

    # -- HTTP ----------------------------------------------------------

    def _promote(self, candidate_id, data: bytes = None):
        url = "/api/import-provenance/candidates/%s/promote" % candidate_id
        if data is None:
            return self.client.post(url)
        return self.client.post(
            url, files={"file": ("evidence.png", data, "image/png")})

    def _decide(self, candidate_id, **body):
        return self.client.post(
            "/api/import-provenance/candidates/%s/decision" % candidate_id,
            json=body)

    def _cand_row(self, candidate_id) -> dict:
        r = self.client.get(
            "/api/import-provenance/candidates/%s" % candidate_id)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["candidate"]

    def _link_day(self, day_id, photo_ids=None, photo_link_ids=None,
                  trip_id=None):
        return self.client.post(
            "/api/trips/%s/days/%s/photos/link"
            % (trip_id or self.trip_id, day_id),
            json={"photo_ids": photo_ids or [],
                  "photo_link_ids": photo_link_ids or []})

    def _links(self, trip_id=None):
        r = self.client.get("/api/trips/%s/photo-links"
                            % (trip_id or self.trip_id))
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["photo_links"]

    def _counts(self):
        con = self._con()
        try:
            def n(table):
                return int(con.execute(
                    "SELECT COUNT(*) AS n FROM %s" % table).fetchone()["n"])
            return {"photos": n("photos"),
                    "trip_photo_links": n("trip_photo_links"),
                    "import_candidate": n("import_candidate")}
        finally:
            con.close()


# ======================================================================
#  1, 2, 5 -- PROMOTION FROM VERIFIED STAGED BYTES
# ======================================================================


class PromotesWithoutAnUploadTests(_Base):

    def test_a_staged_picker_candidate_promotes_with_no_file(self):
        """Behaviour 1. The request carries no multipart body at all --
        this is the exact shape the drawer sends once it stops asking
        for a file."""
        _b, cid, _p = self._staged_candidate()
        r = self._promote(cid)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["created"], body)
        self.assertTrue(body["photo_id"])

    def test_the_archive_row_exists_and_is_readable(self):
        _b, cid, _p = self._staged_candidate()
        photo_id = self._promote(cid).json()["photo_id"]
        con = self._con()
        try:
            row = con.execute("SELECT * FROM photos WHERE id = ?",
                              (photo_id,)).fetchone()
        finally:
            con.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["narrator_id"], self.person_id)
        self.assertEqual(row["file_hash"], _PNG_SHA)
        stored = Path(row["image_path"])
        if not stored.is_absolute():
            stored = self.data_dir / stored
        self.assertTrue(stored.is_file(),
                        "promotion must not write a path to nothing: %s"
                        % row["image_path"])

    def test_promotion_leaves_the_staged_original_where_it_was(self):
        """Doctrine 1.14: staging is not the archive.

        `store_photo_file` MOVES what it is handed. If promotion handed
        it the staged original directly, the archive would eat the file
        the candidate's recorded fingerprint describes, and every later
        re-verification of this candidate would report corruption. So
        the archive is fed a throwaway duplicate, and this asserts it."""
        _b, cid, path = self._staged_candidate()
        self.assertEqual(self._promote(cid).status_code, 200)
        self.assertTrue(path.is_file(),
                        "the archive consumed the import lane's own copy")
        self.assertEqual(path.read_bytes(), _PNG)

    def test_the_promoted_photo_is_born_unapproved(self):
        """Intake is not approval. Materializing bytes is not a claim
        that any human has looked at them, and this is the whole reason
        promotion is allowed to live inside an intake lane at all."""
        _b, cid, _p = self._staged_candidate()
        photo_id = self._promote(cid).json()["photo_id"]
        con = self._con()
        try:
            row = con.execute("SELECT * FROM photos WHERE id = ?",
                              (photo_id,)).fetchone()
        finally:
            con.close()
        self.assertEqual(int(row["narrator_ready"] or 0), 0)
        self.assertEqual(int(row["needs_confirmation"] or 0), 1)
        self.assertEqual(int(row["date_approved_for_lori"] or 0), 0)
        self.assertEqual(int(row["location_approved_for_lori"] or 0), 0)

    def test_an_uploaded_file_is_still_refused_for_a_picker_batch(self):
        """The rule that survived the wall move, and the reason the list
        was renamed rather than widened: Chris, 2026-07-29 -- "The
        operator must not download the Google photo and manually upload
        it back into Hornelore."

        Refused even though the staged copy is right there and would
        have worked. Silently promoting the staged bytes instead would
        be technically correct and would still teach the operator to do
        the wrong thing."""
        _b, cid, _p = self._staged_candidate()
        before = self._counts()
        r = self._promote(cid, data=_PNG)
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn("no need to supply the file again", r.json()["detail"])
        self.assertEqual(self._counts(), before)


class StagedBytesAreVerifiedTests(_Base):

    def test_bytes_that_do_not_match_the_recorded_digest_refuse(self):
        """Behaviour 2. The staged file is present and readable; it is
        simply not the picture this candidate describes."""
        _b, cid, path = self._staged_candidate()
        path.write_bytes(_PNG + b"tampered")
        r = self._promote(cid)
        self.assertEqual(r.status_code, 409, r.text)

    def test_a_mismatch_writes_nothing_at_all(self):
        """Behaviour 3, on the corrupt half. Counted across all three
        tables, because "refuses safely" means the refusal is invisible
        everywhere, not just in `photos`."""
        _b, cid, path = self._staged_candidate()
        before = self._counts()
        path.write_bytes(b"not a picture")
        self.assertEqual(self._promote(cid).status_code, 409)
        self.assertEqual(self._counts(), before)
        cand = self._cand_row(cid)
        self.assertEqual(cand["state"], "pending")
        self.assertIsNone(cand["photo_id"])

    def test_a_missing_staged_original_refuses_and_writes_nothing(self):
        """Behaviour 3, on the missing half. Distinct from the mismatch
        because the operator's fix is the same but the diagnosis is
        not -- and a lane that answered "corrupt" for a file that was
        never written would send someone looking for a disk fault."""
        _b, cid, path = self._staged_candidate()
        before = self._counts()
        path.unlink()
        r = self._promote(cid)
        self.assertEqual(r.status_code, 409, r.text)
        self.assertEqual(self._counts(), before)
        self.assertEqual(self._cand_row(cid)["state"], "pending")

    def test_the_two_refusals_are_separately_named(self):
        """They are different facts and a caller must be able to tell
        them apart without parsing prose."""
        self.assertTrue(issubclass(repo.StagedOriginalMissingError, Exception))
        self.assertTrue(issubclass(repo.StagedOriginalMismatchError, Exception))
        self.assertIsNot(repo.StagedOriginalMissingError,
                         repo.StagedOriginalMismatchError)

    def test_a_refusal_never_names_the_staging_path(self):
        """Chris, 2026-07-29: "Do not expose staging paths, provider
        references, hashes, or repository terminology in the normal
        UI." The detail string IS normal UI -- the drawer prints it."""
        _b, cid, path = self._staged_candidate()
        path.unlink()
        detail = self._promote(cid).json()["detail"]
        for leak in ("import_staging", str(self.data_dir), _PNG_SHA,
                     "original.png"):
            self.assertNotIn(leak, detail, detail)


class IdempotentPromotionTests(_Base):

    def test_promoting_twice_returns_the_same_photo(self):
        """Behaviour 4. 'Promote + accept' is two requests and the
        second can fail, so the operator's retry has to be free."""
        _b, cid, _p = self._staged_candidate()
        first = self._promote(cid).json()
        second = self._promote(cid)
        self.assertEqual(second.status_code, 200, second.text)
        body = second.json()
        self.assertEqual(body["photo_id"], first["photo_id"])
        self.assertFalse(body["created"])
        self.assertEqual(body["reused"], "candidate")

    def test_promoting_twice_creates_one_photo(self):
        _b, cid, _p = self._staged_candidate()
        self._promote(cid)
        after_first = self._counts()
        self._promote(cid)
        self.assertEqual(self._counts(), after_first)

    def test_a_promoted_candidate_can_still_be_accepted(self):
        _b, cid, _p = self._staged_candidate()
        photo_id = self._promote(cid).json()["photo_id"]
        r = self._decide(cid, state="accepted", photo_id=photo_id)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self._cand_row(cid)["state"], "accepted")

    def test_promotion_after_acceptance_still_answers_with_the_photo(self):
        """The retry that matters most: the accept landed, the browser
        lost the response, the operator clicks again."""
        _b, cid, _p = self._staged_candidate()
        photo_id = self._promote(cid).json()["photo_id"]
        self._decide(cid, state="accepted", photo_id=photo_id)
        before = self._counts()
        again = self._promote(cid)
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(again.json()["photo_id"], photo_id)
        self.assertEqual(self._counts(), before)


class ProviderIdentitySurvivesTests(_Base):

    def test_external_id_is_unchanged_by_promotion(self):
        """Behaviour 5. `external_id` is the logical Google item; the
        staged hash verifies OUR copy of it. Promotion touches neither."""
        _b, cid, _p = self._staged_candidate()
        before = self._cand_row(cid)
        self._promote(cid)
        after = self._cand_row(cid)
        self.assertEqual(after["external_id"], _EXTERNAL_ID)
        self.assertEqual(after["external_id"], before["external_id"])
        self.assertEqual(after["file_hash"], before["file_hash"])

    def test_no_provider_handle_appears_in_the_promote_response(self):
        _b, cid, _p = self._staged_candidate()
        blob = self._promote(cid).text
        for bad in _FORBIDDEN:
            self.assertNotIn(bad, blob, "leaked %r" % bad)

    def test_no_provider_handle_appears_in_the_queue_response(self):
        _b, cid, _p = self._staged_candidate()
        self._promote(cid)
        r = self.client.get("/api/import-provenance/queue",
                            params={"person_id": self.person_id})
        self.assertEqual(r.status_code, 200, r.text)
        for bad in _FORBIDDEN:
            self.assertNotIn(bad, r.text, "leaked %r" % bad)

    def test_promotion_does_not_move_the_candidates_review_fields(self):
        _b, cid, _p = self._staged_candidate()
        before = self._cand_row(cid)
        self._promote(cid)
        after = self._cand_row(cid)
        for key in ("state", "match_reason", "match_confidence", "trip_id",
                    "taken_at", "taken_at_source", "filename", "byte_size"):
            self.assertEqual(after.get(key), before.get(key),
                             "promotion moved %r" % key)


# ======================================================================
#  6, 7, 8, 10 -- PLACEMENT ON A DAY
# ======================================================================


class DayPlacementTests(_Base):

    def _promoted(self):
        _b, cid, _p = self._staged_candidate()
        photo_id = self._promote(cid).json()["photo_id"]
        self._decide(cid, state="accepted", photo_id=photo_id)
        return cid, photo_id

    def test_a_promoted_photo_links_to_an_existing_day(self):
        """Behaviour 6. The operator has no photo_link_id to send -- the
        photo has never been on this trip -- so the only thing they can
        name is the photo, which is why the attach route learned
        `photo_ids`."""
        _cid, photo_id = self._promoted()
        r = self._link_day(self.day_ids[1], photo_ids=[photo_id])
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["trip_day_id"], self.day_ids[1])
        self.assertEqual(len(body["created_link_ids"]), 1)

    def test_the_day_then_reports_the_photo(self):
        """Behaviour 10, at the layer the day card reads. The card draws
        from the trip's photo links filtered by `trip_day_id`; if the
        row is not here with that day on it, nothing renders."""
        _cid, photo_id = self._promoted()
        self._link_day(self.day_ids[1], photo_ids=[photo_id])
        on_day = [l for l in self._links()
                  if l.get("trip_day_id") == self.day_ids[1]]
        self.assertEqual(len(on_day), 1, self._links())
        self.assertEqual(on_day[0]["photo_id"], photo_id)

    def test_the_placement_is_recorded_as_the_operators(self):
        """Not a cluster guess. A later re-cluster must not move a photo
        the operator filed by hand, and `assignment_method` is what
        stops it."""
        _cid, photo_id = self._promoted()
        self._link_day(self.day_ids[1], photo_ids=[photo_id])
        link = [l for l in self._links() if l["photo_id"] == photo_id][0]
        self.assertEqual(link["assignment_method"], "operator")

    def test_repeating_the_placement_creates_no_second_link(self):
        """Behaviour 7. UNIQUE(trip_id, photo_id) plus an upsert that
        treats operator truth as already-correct."""
        _cid, photo_id = self._promoted()
        self._link_day(self.day_ids[1], photo_ids=[photo_id])
        after_first = self._counts()
        r = self._link_day(self.day_ids[1], photo_ids=[photo_id])
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self._counts(), after_first)
        self.assertEqual(len([l for l in self._links()
                              if l["photo_id"] == photo_id]), 1)

    def test_placing_the_same_photo_on_a_second_day_adds_it(self):
        """REWRITTEN 2026-08-13, WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01.

        This was ``test_moving_the_same_photo_to_another_day_moves_it``
        and it asserted the defect: 'a photo filed on the wrong day
        should be re-filed, not duplicated'. That was a true reading of
        the OLD data model, where one nullable column could hold one
        day, so placing a second day necessarily erased the first --
        and the interface said 'Move to this day' because the storage
        left it no other option.

        The product ruling reverses it: a photograph taken on one day
        can belong to the story of several, and the route is now an
        ADD. The half of the old test that is still true and still
        worth guarding is kept and asserted first: the photograph
        joins the trip exactly ONCE however many days it sits on. One
        asset, one membership, many placements.

        Correcting a wrong day is no longer a side effect of placing a
        right one; it is the move operation, which names the day it is
        moving FROM. That is tested where it belongs, against the move
        route.
        """
        _cid, photo_id = self._promoted()
        self._link_day(self.day_ids[0], photo_ids=[photo_id])
        self._link_day(self.day_ids[2], photo_ids=[photo_id])
        rows = [l for l in self._links() if l["photo_id"] == photo_id]
        self.assertEqual(len(rows), 1, "trip membership must stay singular")
        self.assertEqual(sorted(rows[0]["trip_day_ids"]),
                         sorted([self.day_ids[0], self.day_ids[2]]),
                         "the photograph is on both days it was placed on")
        self.assertIsNone(
            rows[0]["trip_day_id"],
            "the compatibility scalar must not pick one of several days")

    def test_a_day_from_another_trip_is_refused(self):
        """Behaviour 8. Asserted through the route the browser calls,
        because a repository-level check the router never reaches would
        prove nothing about the workflow."""
        other_trip, other_days = self._new_trip("Somewhere Else")
        _cid, photo_id = self._promoted()
        before = self._counts()
        r = self._link_day(other_days[0], photo_ids=[photo_id])
        self.assertGreaterEqual(r.status_code, 400, r.text)
        self.assertLess(r.status_code, 500, r.text)
        self.assertEqual(self._counts(), before)

    def test_a_photo_of_another_narrator_is_refused(self):
        """The person boundary, at the placement step. Nothing in this
        workflow should be able to file one narrator's picture onto
        another narrator's trip."""
        con = self._con()
        stranger = str(uuid.uuid4())
        try:
            con.execute(
                "INSERT INTO photos (id, narrator_id, image_path, file_hash, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (stranger, self.other_person_id, "/tmp/x.jpg",
                 uuid.uuid4().hex, _now(), _now()))
            con.commit()
        finally:
            con.close()
        before = self._counts()
        r = self._link_day(self.day_ids[0], photo_ids=[stranger])
        self.assertEqual(r.status_code, 409, r.text)
        self.assertEqual(self._counts(), before)

    def test_an_unknown_photo_is_404_and_writes_nothing(self):
        before = self._counts()
        r = self._link_day(self.day_ids[0], photo_ids=[str(uuid.uuid4())])
        self.assertEqual(r.status_code, 404, r.text)
        self.assertEqual(self._counts(), before)

    def test_an_empty_request_is_refused_rather_than_silently_ok(self):
        r = self._link_day(self.day_ids[0])
        self.assertEqual(r.status_code, 422, r.text)

    def test_detaching_by_photo_id_is_refused(self):
        """Attaching may name a photo because there is no link yet.
        Detaching always has one, and accepting a photo id there would
        make "remove this from the day" ambiguous the moment a photo is
        on a trip twice."""
        _cid, photo_id = self._promoted()
        self._link_day(self.day_ids[0], photo_ids=[photo_id])
        r = self.client.post(
            "/api/trips/%s/days/%s/photos/unlink"
            % (self.trip_id, self.day_ids[0]),
            json={"photo_ids": [photo_id]})
        self.assertEqual(r.status_code, 422, r.text)


# ======================================================================
#  9 -- THE QUEUE TELLS THE BROWSER WHAT IT NEEDS
# ======================================================================


class NoFileChooserForPickerTests(_Base):

    def _queue(self, **params):
        params.setdefault("person_id", self.person_id)
        r = self.client.get("/api/import-provenance/queue", params=params)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def _row(self, candidate_id):
        for c in self._queue()["candidates"]:
            if c["id"] == candidate_id:
                return c
        self.fail("candidate %s not in the queue" % candidate_id)

    def test_a_staged_picker_candidate_asks_for_no_file(self):
        """Behaviour 9. The flag is a fact about THIS CANDIDATE -- "is
        there already a file here" -- and never a source name. A browser
        holding a list of source names goes stale the day a fourth lane
        is added; this one cannot."""
        _b, cid, _p = self._staged_candidate()
        self.assertFalse(self._row(cid)["promotion_needs_upload"])

    def test_a_picker_candidate_with_nothing_staged_still_asks(self):
        batch_id = self._picker_batch()
        cid = self._candidate(batch_id)          # deliberately not staged
        self.assertTrue(self._row(cid)["promotion_needs_upload"])

    def test_a_manual_candidate_asks_for_a_file(self):
        batch_id = self._picker_batch(source="manual")
        cid = self._candidate(batch_id)
        self.assertTrue(self._row(cid)["promotion_needs_upload"])

    def test_an_already_promoted_candidate_asks_for_nothing(self):
        _b, cid, _p = self._staged_candidate()
        self._promote(cid)
        self.assertFalse(self._row(cid)["promotion_needs_upload"])

    def test_the_flag_costs_no_hash(self):
        """It decides which control to draw, on every page load, for
        every row. Verifying here would mean a full read of every
        original every time -- and a staged copy that is present but
        wrong is not something an upload fixes: promotion refuses it by
        name. So a corrupt staged file still reports "no upload needed",
        and that is correct."""
        _b, cid, path = self._staged_candidate()
        path.write_bytes(b"corrupt")
        self.assertFalse(self._row(cid)["promotion_needs_upload"])

    def test_the_drawer_gates_its_file_input_on_the_flag(self):
        """The browser half, read out of the source.

        A UI test cannot be run here, but the thing worth locking is not
        pixels -- it is that the drawer decides from the server's fact
        rather than from a hardcoded source name. That is a grep."""
        self.assertTrue(_UI_PATH.is_file(), _UI_PATH)
        src = _UI_PATH.read_text(encoding="utf-8")
        self.assertIn("promotion_needs_upload", src,
                      "the promote drawer must ask the server whether a file "
                      "is needed")
        # The failure this guards against: a drawer that re-derives the
        # answer from the lane's name.
        for forbidden in ('c.source === "google_photos_picker"',
                          "c.source === 'google_photos_picker'"):
            self.assertNotIn(forbidden, src,
                             "%s re-implements the server's decision in the "
                             "browser" % forbidden)


# ======================================================================
#  THE WHOLE WORKFLOW, ONCE, IN ORDER
# ======================================================================


class EndToEndWorkflowTests(_Base):
    """The shape of the live acceptance run, as a test.

    Chris's run is the verification; this is what makes a regression in
    it fail in the suite rather than in his browser."""

    def test_import_to_photo_on_a_day(self):
        batch_id = self._picker_batch()
        cids = []
        for i in range(3):
            data = _PNG + (b"\x00" * (i + 1))     # distinct bytes per item
            cid = self._candidate(
                batch_id,
                external_id="%s-%d" % (_EXTERNAL_ID, i),
                file_hash=hashlib.sha256(data).hexdigest(),
                filename="PXL_2026071%d.jpg" % i,
                byte_size=len(data))
            self._stage(batch_id, cid, data=data)
            cids.append(cid)

        before = self._counts()
        self.assertEqual(before["photos"], 0)
        self.assertEqual(before["trip_photo_links"], 0)
        self.assertEqual(before["import_candidate"], 3)

        # -- one candidate, all the way through ------------------------
        target = cids[0]
        photo_id = self._promote(target).json()["photo_id"]
        self.assertEqual(
            self._decide(target, state="accepted",
                         photo_id=photo_id).status_code, 200)
        self.assertEqual(
            self._link_day(self.day_ids[1],
                           photo_ids=[photo_id]).status_code, 200)

        after = self._counts()
        self.assertEqual(after["photos"], 1)
        self.assertEqual(after["trip_photo_links"], 1)
        self.assertEqual(after["import_candidate"], 3)

        rows = self._links()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["trip_day_id"], self.day_ids[1])
        self.assertEqual(rows[0]["photo_id"], photo_id)

        # -- the other two are untouched -------------------------------
        for cid in cids[1:]:
            row = self._cand_row(cid)
            self.assertEqual(row["state"], "pending")
            self.assertIsNone(row["photo_id"])

        # -- a repeated submission adds nothing ------------------------
        self._promote(target)
        self._link_day(self.day_ids[1], photo_ids=[photo_id])
        self.assertEqual(self._counts(), after)

        # -- and it is a workflow, not a one-row special case ----------
        second = cids[1]
        photo2 = self._promote(second).json()["photo_id"]
        self.assertNotEqual(photo2, photo_id)
        self._decide(second, state="accepted", photo_id=photo2)
        self.assertEqual(
            self._link_day(self.day_ids[2],
                           photo_ids=[photo2]).status_code, 200)

        final = self._counts()
        self.assertEqual(final["photos"], 2)
        self.assertEqual(final["trip_photo_links"], 2)
        self.assertEqual(final["import_candidate"], 3)
        by_day = dict((l["photo_id"], l["trip_day_id"])
                      for l in self._links())
        self.assertEqual(by_day[photo_id], self.day_ids[1])
        self.assertEqual(by_day[photo2], self.day_ids[2])
        self.assertEqual(self._cand_row(cids[2])["state"], "pending")


if __name__ == "__main__":
    unittest.main()
