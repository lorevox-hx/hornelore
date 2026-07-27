"""WO-TRAVEL-DOC-EVIDENCE-REVIEW-QUEUE-01 Phase 3 -- promotion lock.

Phase 1 gave the review queue its read. This file locks the one write
that was missing: ``POST /api/import-provenance/candidates/{id}/promote``.

Why the route exists at all. Accepting a candidate has always required
the ``photo_id`` of a photos row that already exists, and nothing in the
import lane could produce one -- an ``import_candidate`` carries a
filename, a mime type, a byte count and maybe a hash, but never the
image. So 'accepted' was a state the queue could not reach. Promotion
reaches it, and it reaches nothing else: it materializes a photo and
stops. It does not decide, it does not approve, and it is a separate
request from the decision on purpose (WO-2 Decision 3, option B).

What is locked here:

  1. THE GATE, AGAIN. Flag off -> 404, on a multipart route too.

  2. BORN UNAPPROVED. The photos row promotion creates has
     narrator_ready = 0, needs_confirmation = 1,
     date_approved_for_lori = 0 and location_approved_for_lori = 0. This
     is the whole reason promotion is allowed to exist inside an intake
     lane: intake is not approval, and materializing bytes is not a
     claim that anyone has looked at them.

  3. PROMOTION DOES NOT DECIDE. The candidate is still 'pending' when
     promote returns, and the batch counters have not moved. The
     EXISTING decision route is what accepts, using the photo_id this
     route handed back. Two requests, in that order.

  4. NO BYTES, NO PHOTO. Promotion never invents an ``image_path``. With
     no file and no hash match the answer is 409, not a plausible path
     to a file that does not exist -- a photos row whose path resolves
     to nothing would flow into Lori's photo grounding as a real
     picture and nothing downstream would catch it.

  5. THE PERSON BOUNDARY. ``photos.file_hash`` is UNIQUE across the
     whole table, so the same bytes under another narrator is a refusal
     that names itself (409), not an IntegrityError 500.

  6. THE VOCABULARY COLLAPSE. A candidate's ``provider_metadata`` /
     ``operator`` provenance has no home in the photos vocabulary, so it
     collapses DOWNWARD to 'unknown' and the true value survives in
     ``photos.metadata_json.import_provenance``. Migration 0023's
     filename_guess doctrine is honored: a filename date never reaches
     ``date_value``.

  7. STILL NO DELETE. Promotion adds a row; nothing here removes one.

Fresh sqlite fixture, fresh DATA_DIR and fresh FastAPI app per test.
pytest is not installed in this repo; run with:

    python3 -m unittest tests.test_import_provenance_promote
"""
from __future__ import annotations

import ast
import json
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
from api.services import import_repository as repo  # noqa: E402

_ROUTER_PATH = _SERVER_CODE / "api" / "routers" / "import_provenance.py"

_FLAG = "HORNELORE_IMPORT_PROVENANCE"

# A 1x1 PNG. Real bytes, because store_photo_file hashes them and the
# thumbnailer will try to open them; a text blob would exercise only the
# failure path.
_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00"
    b"\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

# Different bytes, so a second promotion in the same test does not
# collide on the UNIQUE file_hash by accident.
_PNG2 = _PNG[:-4] + b"\x00\x00\x00\x00" + _PNG[-4:]


def _now() -> str:
    return "2026-07-27T00:00:00Z"


class _Base(unittest.TestCase):
    """Fresh database, fresh archive root, fresh app, flag ON."""

    flag_value = "1"

    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        tmp.close()
        self.db_path = Path(tmp.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()

        # DATA_DIR is read at call time by photo_intake.storage, and it
        # refuses to store anything without it. Point it at a temp tree
        # so a test run never writes into the real archive.
        self.data_dir = Path(tempfile.mkdtemp(prefix="promote_data_"))
        self._orig_data_dir = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = str(self.data_dir)

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

    def tearDown(self):
        self.client.close()
        _db.DB_PATH = self._orig_db
        if self._orig_flag is None:
            os.environ.pop(_FLAG, None)
        else:
            os.environ[_FLAG] = self._orig_flag
        if self._orig_data_dir is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self._orig_data_dir
        shutil.rmtree(self.data_dir, ignore_errors=True)
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

    def _insert_photo(self, narrator_id: str, file_hash=None,
                      deleted: bool = False) -> str:
        pid = str(uuid.uuid4())
        con = self._con()
        try:
            con.execute(
                "INSERT INTO photos (id, narrator_id, image_path, file_hash, "
                "deleted_at, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (pid, narrator_id, "/tmp/%s.jpg" % pid,
                 file_hash or uuid.uuid4().hex,
                 _now() if deleted else None, _now(), _now()),
            )
            con.commit()
        finally:
            con.close()
        return pid

    def _photo_row(self, photo_id: str) -> dict:
        con = self._con()
        try:
            row = con.execute(
                "SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone()
            return dict(row) if row else {}
        finally:
            con.close()

    def _photo_count(self) -> int:
        con = self._con()
        try:
            return int(con.execute(
                "SELECT COUNT(*) AS n FROM photos").fetchone()["n"])
        finally:
            con.close()

    # -- HTTP helpers ----------------------------------------------------

    def _open_batch(self, source: str = "local_upload", **over) -> str:
        body = {"person_id": self.person_id, "source": source}
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

    def _promote(self, candidate_id, data: bytes = None,
                 filename: str = "evidence.png",
                 content_type: str = "image/png", **form):
        url = "/api/import-provenance/candidates/%s/promote" % candidate_id
        if data is None:
            return self.client.post(url, data=form or None)
        return self.client.post(
            url,
            files={"file": (filename, data, content_type)},
            data=form or None,
        )

    def _candidate(self, candidate_id) -> dict:
        r = self.client.get(
            "/api/import-provenance/candidates/%s" % candidate_id)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["candidate"]

    def _decide(self, candidate_id, **body):
        return self.client.post(
            "/api/import-provenance/candidates/%s/decision" % candidate_id,
            json=body,
        )


# ======================================================================
#  1 -- THE GATE
# ======================================================================


class PromoteFlagGateTests(_Base):

    flag_value = None  # unset entirely: default OFF

    def test_promote_is_404_with_the_flag_off(self):
        r = self.client.post(
            "/api/import-provenance/candidates/whatever/promote")
        self.assertEqual(r.status_code, 404, r.text)

    def test_the_gate_answers_before_the_multipart_parser(self):
        # A body this route could never accept. With the flag off the
        # answer must still be the gate's 404 -- if a 422 comes back, the
        # surface has announced itself to an unauthorized caller.
        r = self.client.post(
            "/api/import-provenance/candidates/whatever/promote",
            json={"nonsense": True},
        )
        self.assertEqual(r.status_code, 404, r.text)


class PromoteUnknownCandidateTests(_Base):

    def test_unknown_candidate_is_404_even_with_a_file(self):
        r = self._promote("no-such-candidate", data=_PNG)
        self.assertEqual(r.status_code, 404, r.text)

    def test_unknown_candidate_writes_no_photo(self):
        before = self._photo_count()
        self._promote("no-such-candidate", data=_PNG)
        self.assertEqual(self._photo_count(), before)


# ======================================================================
#  2 -- BORN UNAPPROVED
# ======================================================================


class PromotedPhotoIsBornUnapprovedTests(_Base):

    def setUp(self):
        super().setUp()
        self.cid = self._new_candidate(filename="paris.png",
                                       mime_type="image/png")
        r = self._promote(self.cid, data=_PNG)
        self.assertEqual(r.status_code, 200, r.text)
        self.body = r.json()
        self.photo_id = self.body["photo_id"]

    def test_promote_reports_it_created_the_row(self):
        self.assertTrue(self.body["created"])
        self.assertIsNone(self.body["reused"])

    def test_photo_is_not_narrator_facing(self):
        self.assertEqual(int(self._photo_row(self.photo_id)["narrator_ready"]),
                         0)

    def test_photo_still_needs_confirmation(self):
        self.assertEqual(
            int(self._photo_row(self.photo_id)["needs_confirmation"]), 1)

    def test_photo_is_not_approved_for_lori_on_either_axis(self):
        row = self._photo_row(self.photo_id)
        self.assertEqual(int(row["date_approved_for_lori"]), 0)
        self.assertEqual(int(row["location_approved_for_lori"]), 0)

    def test_photo_is_not_in_a_memoir(self):
        # include_in_memoir is the other narrator-facing switch. Nothing
        # in this lane may set it, so it must be falsy however the column
        # spells its default.
        row = self._photo_row(self.photo_id)
        if "include_in_memoir" in row:
            self.assertFalse(bool(row["include_in_memoir"] or 0))

    def test_the_bytes_actually_landed_on_disk(self):
        # The point of refusing to invent an image_path is that the path
        # promotion DOES write resolves to a real file.
        path = Path(self._photo_row(self.photo_id)["image_path"])
        self.assertTrue(path.is_file(), path)
        self.assertEqual(path.read_bytes(), _PNG)

    def test_the_photo_belongs_to_the_candidates_person(self):
        self.assertEqual(self._photo_row(self.photo_id)["narrator_id"],
                         self.person_id)

    def test_promotion_writes_exactly_one_photo(self):
        self.assertEqual(self._photo_count(), 1)


# ======================================================================
#  3 -- PROMOTION DOES NOT DECIDE
# ======================================================================


class PromotionDoesNotDecideTests(_Base):

    def setUp(self):
        super().setUp()
        self.batch_id = self._open_batch()
        self.cid = self._new_candidate(self.batch_id, filename="a.png")
        r = self._promote(self.cid, data=_PNG)
        self.assertEqual(r.status_code, 200, r.text)
        self.photo_id = r.json()["photo_id"]

    def test_candidate_is_still_pending(self):
        self.assertEqual(self._candidate(self.cid)["state"], "pending")

    def test_candidate_now_carries_the_photo_id(self):
        self.assertEqual(self._candidate(self.cid)["photo_id"], self.photo_id)

    def test_no_reviewer_was_recorded(self):
        cand = self._candidate(self.cid)
        self.assertIsNone(cand["reviewed_by_user_id"])
        self.assertIsNone(cand["reviewed_at"])

    def test_batch_counters_did_not_move(self):
        r = self.client.get(
            "/api/import-provenance/batches/%s/counts" % self.batch_id)
        counts = r.json()["counts"]
        self.assertEqual(counts["pending"], 1)
        self.assertEqual(counts["accepted"], 0)

    def test_the_existing_decision_route_then_accepts_with_that_photo_id(self):
        # Build point 4, end to end. Two requests, and the second one is
        # the route that already shipped -- promotion did not grow a
        # decision, it just made one possible.
        r = self._decide(self.cid, state="accepted", photo_id=self.photo_id)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self._candidate(self.cid)["state"], "accepted")

    def test_accepting_does_not_touch_the_photos_row(self):
        before = self._photo_row(self.photo_id)
        self._decide(self.cid, state="accepted", photo_id=self.photo_id)
        after = self._photo_row(self.photo_id)
        self.assertEqual(int(after["narrator_ready"]), 0)
        self.assertEqual(int(after["needs_confirmation"]), 1)
        self.assertEqual(after["updated_at"], before["updated_at"])

    def test_rejecting_after_promoting_unlinks_but_keeps_the_photo(self):
        # A known and accepted consequence, locked so it cannot change
        # silently: candidate_decide writes photo_id unconditionally, and
        # a non-accepted decision must not carry one, so the link clears.
        # The photos row survives, unreferenced and still unapproved --
        # there is no DELETE in this lane and promotion did not add one.
        r = self._decide(self.cid, state="rejected")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNone(self._candidate(self.cid)["photo_id"])
        self.assertEqual(self._photo_count(), 1)
        self.assertEqual(int(self._photo_row(self.photo_id)["narrator_ready"]),
                         0)


class PromotionIsIdempotentTests(_Base):

    def test_second_promote_returns_the_same_photo_and_creates_nothing(self):
        cid = self._new_candidate(filename="a.png")
        first = self._promote(cid, data=_PNG).json()
        # No file the second time. "promote + accept" is two requests and
        # the second can fail; the retry must not demand the operator
        # find a file they already handed over.
        second = self._promote(cid)
        self.assertEqual(second.status_code, 200, second.text)
        body = second.json()
        self.assertEqual(body["photo_id"], first["photo_id"])
        self.assertFalse(body["created"])
        self.assertEqual(body["reused"], "candidate")
        self.assertEqual(self._photo_count(), 1)

    def test_re_promoting_with_bytes_also_creates_nothing(self):
        cid = self._new_candidate(filename="a.png")
        first = self._promote(cid, data=_PNG).json()
        second = self._promote(cid, data=_PNG2).json()
        # Already linked wins over supplied bytes: the candidate's photo
        # is the photo it was promoted into, whatever arrives later.
        self.assertEqual(second["photo_id"], first["photo_id"])
        self.assertEqual(second["reused"], "candidate")
        self.assertEqual(self._photo_count(), 1)


# ======================================================================
#  4 -- NO BYTES, NO PHOTO
# ======================================================================


class PromotionRefusesToInventAPhotoTests(_Base):

    def test_no_file_and_no_hash_is_409(self):
        cid = self._new_candidate(filename="a.png")
        r = self._promote(cid)
        self.assertEqual(r.status_code, 409, r.text)

    def test_that_refusal_writes_no_photo(self):
        cid = self._new_candidate(filename="a.png")
        self._promote(cid)
        self.assertEqual(self._photo_count(), 0)

    def test_that_refusal_leaves_the_candidate_untouched(self):
        cid = self._new_candidate(filename="a.png")
        self._promote(cid)
        cand = self._candidate(cid)
        self.assertEqual(cand["state"], "pending")
        self.assertIsNone(cand["photo_id"])

    def test_the_refusal_explains_what_a_candidate_does_not_carry(self):
        cid = self._new_candidate(filename="a.png")
        detail = self._promote(cid).json()["detail"]
        self.assertIn("never the image", detail)


class PromotableSourceTests(_Base):

    def test_promotion_is_defined_only_for_local_and_manual(self):
        self.assertEqual(repo.PROMOTABLE_SOURCES, ("local_upload", "manual"))

    def test_a_manual_batch_promotes(self):
        bid = self._open_batch(source="manual")
        cid = self._new_candidate(bid, filename="a.png")
        r = self._promote(cid, data=_PNG)
        self.assertEqual(r.status_code, 200, r.text)

    def test_a_takeout_batch_is_refused(self):
        bid = self._open_batch(source="google_takeout")
        cid = self._new_candidate(bid, filename="a.png")
        r = self._promote(cid, data=_PNG)
        self.assertEqual(r.status_code, 400, r.text)
        self.assertEqual(self._photo_count(), 0)

    def test_a_picker_batch_is_refused(self):
        bid = self._open_batch(source="google_photos_picker")
        cid = self._new_candidate(bid, filename="a.png")
        r = self._promote(cid, data=_PNG)
        self.assertEqual(r.status_code, 400, r.text)

    def test_a_csv_batch_is_refused(self):
        bid = self._open_batch(source="csv")
        cid = self._new_candidate(bid, filename="a.png")
        r = self._promote(cid, data=_PNG)
        self.assertEqual(r.status_code, 400, r.text)

    def test_the_refusal_says_why_a_provider_import_cannot_promote(self):
        bid = self._open_batch(source="google_takeout")
        cid = self._new_candidate(bid, filename="a.png")
        detail = self._promote(cid, data=_PNG).json()["detail"]
        self.assertIn("fetch its own bytes", detail)


class PromoteMimeTests(_Base):

    def test_a_non_image_upload_is_415(self):
        cid = self._new_candidate(filename="notes.txt")
        r = self._promote(cid, data=b"hello", filename="notes.txt",
                          content_type="text/plain")
        self.assertEqual(r.status_code, 415, r.text)
        self.assertEqual(self._photo_count(), 0)

    def test_the_allow_list_matches_the_photo_upload_route(self):
        # A file POST /api/photos would refuse must not get in through
        # this side door, so the two lists must be the same list.
        #
        # Read out of the source with ast rather than imported: importing
        # routers.photos would drag the whole photo lane -- and its own
        # flag gate -- into this test's import graph, which is exactly
        # the reason import_provenance restates the tuple instead of
        # importing it. Parsing the literal proves they agree without
        # coupling the two modules.
        photos_src = _SERVER_CODE / "api" / "routers" / "photos.py"
        self.assertTrue(photos_src.is_file(), photos_src)
        tree = ast.parse(photos_src.read_text(encoding="utf-8"))
        found = None
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "_ALLOWED_IMAGE_MIME_PREFIXES" in names:
                found = ast.literal_eval(node.value)
        self.assertIsNotNone(
            found, "photos.py no longer defines _ALLOWED_IMAGE_MIME_PREFIXES")
        self.assertEqual(set(ip._PROMOTE_MIME_PREFIXES), set(found))

    def test_jpeg_is_accepted(self):
        cid = self._new_candidate(filename="a.jpg")
        r = self._promote(cid, data=_PNG, filename="a.jpg",
                          content_type="image/jpeg")
        self.assertEqual(r.status_code, 200, r.text)


# ======================================================================
#  5 -- THE PERSON BOUNDARY AND THE UNIQUE HASH
# ======================================================================


class PromoteHashTests(_Base):

    def test_a_declared_hash_that_this_person_already_has_links_it(self):
        # The ordinary case once the operator has already uploaded the
        # image through the photo lane: no file needed, no second copy.
        h = uuid.uuid4().hex
        existing = self._insert_photo(self.person_id, file_hash=h)
        cid = self._new_candidate(filename="a.png", file_hash=h)
        r = self._promote(cid)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["photo_id"], existing)
        self.assertFalse(body["created"])
        self.assertEqual(body["reused"], "hash")
        self.assertEqual(self._photo_count(), 1)

    def test_linking_by_hash_leaves_the_candidate_pending(self):
        h = uuid.uuid4().hex
        self._insert_photo(self.person_id, file_hash=h)
        cid = self._new_candidate(filename="a.png", file_hash=h)
        self._promote(cid)
        self.assertEqual(self._candidate(cid)["state"], "pending")

    def test_a_declared_hash_owned_by_another_narrator_does_not_link(self):
        # find_photo_by_hash is person-scoped, so the other narrator's
        # photo is invisible here and the answer is "no bytes", not
        # "here is Kent's picture".
        h = uuid.uuid4().hex
        self._insert_photo(self.other_person_id, file_hash=h)
        cid = self._new_candidate(filename="a.png", file_hash=h)
        r = self._promote(cid)
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIn("never the image", r.json()["detail"])

    def test_a_soft_deleted_photo_of_this_person_does_not_link(self):
        h = uuid.uuid4().hex
        self._insert_photo(self.person_id, file_hash=h, deleted=True)
        cid = self._new_candidate(filename="a.png", file_hash=h)
        r = self._promote(cid)
        self.assertEqual(r.status_code, 409, r.text)

    def test_uploaded_bytes_this_person_already_has_link_instead_of_copy(self):
        cid1 = self._new_candidate(filename="a.png")
        first = self._promote(cid1, data=_PNG).json()
        cid2 = self._new_candidate(filename="same-again.png")
        second = self._promote(cid2, data=_PNG)
        self.assertEqual(second.status_code, 200, second.text)
        body = second.json()
        self.assertEqual(body["photo_id"], first["photo_id"])
        self.assertEqual(body["reused"], "hash")
        self.assertEqual(self._photo_count(), 1)

    def test_uploaded_bytes_owned_by_another_narrator_are_409_not_500(self):
        # photos.file_hash is UNIQUE across the WHOLE table. Left to the
        # INSERT this is an IntegrityError and a 500 that reads like a
        # server bug; it is a refusal, and it must name itself.
        other = self._new_candidate(
            self._open_batch_for(self.other_person_id), filename="kent.png")
        r = self._promote(other, data=_PNG)
        self.assertEqual(r.status_code, 200, r.text)

        mine = self._new_candidate(filename="mine.png")
        r = self._promote(mine, data=_PNG)
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIn("another", r.json()["detail"])
        self.assertEqual(self._photo_count(), 1)

    def test_uploaded_bytes_matching_own_soft_deleted_photo_are_409(self):
        cid1 = self._new_candidate(filename="a.png")
        photo_id = self._promote(cid1, data=_PNG).json()["photo_id"]
        con = self._con()
        try:
            con.execute("UPDATE photos SET deleted_at = ? WHERE id = ?",
                        (_now(), photo_id))
            con.commit()
        finally:
            con.close()

        cid2 = self._new_candidate(filename="again.png")
        r = self._promote(cid2, data=_PNG)
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIn("deleted", r.json()["detail"])
        self.assertEqual(self._photo_count(), 1)

    def _open_batch_for(self, person_id: str) -> str:
        r = self.client.post("/api/import-provenance/batches", json={
            "person_id": person_id, "source": "local_upload"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["batch"]["id"]


# ======================================================================
#  6 -- THE VOCABULARY COLLAPSE
# ======================================================================


class _PromotedRowBase(_Base):
    """Promote one candidate and hand back the photos row it produced."""

    def _promoted_row(self, **candidate_body) -> dict:
        cid = self._new_candidate(filename="a.png", **candidate_body)
        r = self._promote(cid, data=_PNG)
        self.assertEqual(r.status_code, 200, r.text)
        return self._photo_row(r.json()["photo_id"])


class PromoteDateDoctrineTests(_PromotedRowBase):

    def test_a_filename_date_never_reaches_date_value(self):
        # Migration 0023: a date parsed from a filename is low confidence,
        # display only, and NEVER auto-fills date_value.
        row = self._promoted_row(taken_at="2026-05-01T00:00:00Z",
                                 taken_at_source="filename_guess")
        self.assertIsNone(row["date_value"])
        self.assertEqual(row["taken_at_filename_guess"], "2026-05-01T00:00:00Z")
        self.assertEqual(row["date_source"], "filename_guess")

    def test_exif_is_the_only_source_that_earns_exact(self):
        row = self._promoted_row(taken_at="2026-05-01T00:00:00Z",
                                 taken_at_source="exif")
        self.assertEqual(row["date_value"], "2026-05-01T00:00:00Z")
        self.assertEqual(row["date_precision"], "exact")
        self.assertEqual(row["date_source"], "exif")

    def test_provider_metadata_keeps_the_date_but_not_the_precision(self):
        row = self._promoted_row(taken_at="2026-05-01T00:00:00Z",
                                 taken_at_source="provider_metadata")
        self.assertEqual(row["date_value"], "2026-05-01T00:00:00Z")
        self.assertEqual(row["date_precision"], "unknown")
        self.assertEqual(row["date_source"], "unknown")

    def test_operator_does_not_become_operator_confirmed(self):
        # At promotion time nothing has been confirmed by anyone: the
        # operator supplied a file, they did not review a date. And
        # date_source has no CHECK constraint, so this is the easy column
        # to lie in and the one worth locking.
        row = self._promoted_row(taken_at="2026-05-01T00:00:00Z",
                                 taken_at_source="operator")
        self.assertEqual(row["date_source"], "unknown")
        self.assertNotEqual(row["date_source"], "operator_confirmed")

    def test_no_date_at_all_leaves_every_date_column_empty(self):
        row = self._promoted_row()
        self.assertIsNone(row["date_value"])
        self.assertIsNone(row["taken_at_filename_guess"])
        self.assertEqual(row["date_precision"], "unknown")


class PromoteLocationDoctrineTests(_PromotedRowBase):

    def test_exif_gps_survives_verbatim(self):
        row = self._promoted_row(latitude=48.8584, longitude=2.2945,
                                 location_source="exif_gps")
        self.assertEqual(row["location_source"], "exif_gps")
        self.assertAlmostEqual(row["latitude"], 48.8584)
        self.assertAlmostEqual(row["longitude"], 2.2945)

    def test_provider_metadata_collapses_downward_to_unknown(self):
        # photos.location_source has a CHECK constraint and
        # 'provider_metadata' is not in it. Passing it through would be an
        # IntegrityError; asserting it as 'typed_address' would be a lie.
        row = self._promoted_row(latitude=48.8584, longitude=2.2945,
                                 location_source="provider_metadata")
        self.assertEqual(row["location_source"], "unknown")

    def test_operator_coordinates_collapse_downward_to_unknown(self):
        row = self._promoted_row(latitude=48.8584, longitude=2.2945,
                                 location_source="operator")
        self.assertEqual(row["location_source"], "unknown")

    def test_the_coordinates_survive_the_collapse(self):
        row = self._promoted_row(latitude=48.8584, longitude=2.2945,
                                 location_source="operator")
        self.assertAlmostEqual(row["latitude"], 48.8584)
        self.assertAlmostEqual(row["longitude"], 2.2945)

    def test_promotion_never_invents_a_location_label(self):
        # 0023 guards the operator-entered broad location_label; a
        # candidate has coordinates, not a place name, so manufacturing
        # one here would fabricate the very field approval exists for.
        row = self._promoted_row(latitude=48.8584, longitude=2.2945,
                                 location_source="exif_gps")
        self.assertIsNone(row["location_label"])


class PromoteProvenanceTrailTests(_Base):

    def setUp(self):
        super().setUp()
        self.batch_id = self._open_batch(label="July drop")
        self.cid = self._new_candidate(
            self.batch_id,
            filename="paris.png",
            external_id="ext-42",
            mime_type="image/png",
            byte_size=1234,
            taken_at="2026-05-01T00:00:00Z",
            taken_at_source="provider_metadata",
            latitude=48.8584,
            longitude=2.2945,
            location_source="operator",
            match_reason={"why": "same trip window"},
            match_confidence=0.8,
        )
        r = self._promote(self.cid, data=_PNG,
                          promoted_by_user_id="operator-1")
        self.assertEqual(r.status_code, 200, r.text)
        row = self._photo_row(r.json()["photo_id"])
        self.trail = json.loads(row["metadata_json"])["import_provenance"]

    def test_the_trail_names_the_candidate_and_the_batch(self):
        self.assertEqual(self.trail["candidate_id"], self.cid)
        self.assertEqual(self.trail["batch_id"], self.batch_id)
        self.assertEqual(self.trail["batch_source"], "local_upload")
        self.assertEqual(self.trail["batch_label"], "July drop")

    def test_the_collapsed_values_survive_in_the_trail(self):
        # The whole point of the collapse: photos.location_source says
        # 'unknown', and what the importer actually claimed is still
        # recoverable.
        self.assertEqual(self.trail["candidate_location_source"], "operator")
        self.assertEqual(self.trail["candidate_taken_at_source"],
                         "provider_metadata")

    def test_the_trail_keeps_the_match_reason(self):
        self.assertEqual(self.trail["match_reason"], {"why": "same trip window"})
        self.assertEqual(self.trail["match_confidence"], 0.8)

    def test_the_trail_records_who_promoted_and_when(self):
        self.assertEqual(self.trail["promoted_by_user_id"], "operator-1")
        self.assertTrue(self.trail["promoted_at"])

    def test_the_trail_keeps_the_source_side_identifiers(self):
        self.assertEqual(self.trail["external_id"], "ext-42")
        self.assertEqual(self.trail["filename"], "paris.png")
        self.assertEqual(self.trail["byte_size"], 1234)

    def test_the_trail_is_not_authority(self):
        # metadata_json is non-authoritative by contract (0001). Nothing
        # in it may name an approval, so a later reader cannot mistake
        # the trail for a decision.
        flat = json.dumps(self.trail)
        self.assertNotIn("narrator_ready", flat)
        self.assertNotIn("approved", flat)


# ======================================================================
#  7 -- TRIP PLACEMENT STAYS TRIP-GRANULARITY (Decision 1)
# ======================================================================


class PromoteStaysTripLevelTests(_Base):

    def test_promotion_does_not_move_the_candidate_off_its_trip(self):
        bid = self._open_batch(trip_id=self.trip_id)
        cid = self._new_candidate(bid, filename="a.png")
        self.assertEqual(self._candidate(cid)["trip_id"], self.trip_id)
        self._promote(cid, data=_PNG)
        self.assertEqual(self._candidate(cid)["trip_id"], self.trip_id)

    def test_promotion_invents_no_finer_placement_than_a_trip(self):
        # Decision 1, and there is no migration 0038. If a day / region /
        # stop column ever appears on a promoted photo, it came from
        # somewhere this slice did not authorize.
        bid = self._open_batch(trip_id=self.trip_id)
        cid = self._new_candidate(bid, filename="a.png")
        photo_id = self._promote(cid, data=_PNG).json()["photo_id"]
        row = self._photo_row(photo_id)
        for col in ("trip_day_id", "region_id", "stop_id"):
            self.assertNotIn(col, row)


# ======================================================================
#  8 -- STILL NO DELETE
# ======================================================================


class PromoteAddsNoDeleteTests(_Base):

    def test_the_router_still_declares_no_delete_method(self):
        methods = set()
        for route in ip.router.routes:
            methods |= set(getattr(route, "methods", None) or ())
        self.assertNotIn("DELETE", methods)

    def test_the_promote_route_source_contains_no_delete_statement(self):
        src = _ROUTER_PATH.read_text(encoding="utf-8").upper()
        self.assertNotIn("DELETE FROM", src)

    def test_the_repository_promotion_block_contains_no_delete_statement(self):
        src = (_SERVER_CODE / "api" / "services" / "import_repository.py"
               ).read_text(encoding="utf-8").upper()
        self.assertNotIn("DELETE FROM PHOTOS", src)
        self.assertNotIn("DELETE FROM IMPORT_CANDIDATE", src)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
