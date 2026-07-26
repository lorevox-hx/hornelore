"""WO-TRAVEL-DOC-IMPORT-PROVENANCE-FOUNDATION-01 Phase 2 -- migration lock.

Locks migration 0037_import_provenance_foundation.sql. Same shape as
tests/test_c1_trips_person_id_fk_migration.py, which locks 0034.

Two things are being locked, and they are locked for different reasons.

FK HARDENING
    photos.narrator_id had no REFERENCES since 0001, so a photo could
    name a person id that does not exist and nothing would complain.
    trip_photo_links.photo_id had no REFERENCES since 0015, so a trip
    could link a photo that had been deleted. The failure mode is not
    a crash -- _photos_for_narrator() returns an EMPTY LIST for an
    unknown narrator id, so clustering silently shows nothing and
    looks like "this trip has no photos yet". Silent wrong answers are
    worse than errors, which is why these need schema teeth and not
    just an app-level check.

INTAKE IS NOT APPROVAL
    import_candidate must NOT grow a narrator_ready column or an
    include_in_memoir column. The absence is the enforcement. If
    somebody adds one, these tests fail and the reviewer has to argue
    for it in the open rather than sliding approval semantics into the
    intake table. The Epic rule is that import is intake: creating a
    candidate does not mean narrator-ready and does not mean memoir
    inclusion.

Fresh sqlite fixture per test.
"""
from __future__ import annotations

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

MIGRATION = "0037_import_provenance_foundation.sql"


def _now() -> str:
    return "2026-07-26T00:00:00"


class _FreshDBBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        tmp.close()
        self.db_path = Path(tmp.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()

        self.person_id = str(uuid.uuid4())
        con = self._con()
        try:
            con.execute(
                "INSERT INTO people (id, display_name, date_of_birth, "
                "created_at, updated_at) VALUES (?, 'Chris', '1962-12-24', ?, ?)",
                (self.person_id, _now(), _now()),
            )
            con.commit()
        finally:
            con.close()

    def tearDown(self):
        _db.DB_PATH = self._orig_db
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def _con(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.db_path))
        con.execute("PRAGMA foreign_keys = ON;")
        return con

    def _insert_photo(self, con, narrator_id, photo_id=None):
        photo_id = photo_id or str(uuid.uuid4())
        con.execute(
            "INSERT INTO photos (id, narrator_id, image_path, file_hash, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (photo_id, narrator_id, f"/tmp/{photo_id}.jpg",
             uuid.uuid4().hex, _now(), _now()),
        )
        return photo_id

    def _insert_trip(self, con, person_id, trip_id=None):
        trip_id = trip_id or str(uuid.uuid4())
        con.execute(
            "INSERT INTO trips (id, person_id, title, created_at, updated_at) "
            "VALUES (?, ?, 'A Trip', ?, ?)",
            (trip_id, person_id, _now(), _now()),
        )
        return trip_id

    def _insert_link(self, con, trip_id, photo_id):
        link_id = str(uuid.uuid4())
        con.execute(
            "INSERT INTO trip_photo_links (id, trip_id, photo_id, created_at, "
            "updated_at) VALUES (?, ?, ?, ?, ?)",
            (link_id, trip_id, photo_id, _now(), _now()),
        )
        return link_id

    def _insert_batch(self, con, person_id=None, batch_id=None, source="local_upload"):
        batch_id = batch_id or str(uuid.uuid4())
        con.execute(
            "INSERT INTO import_batch (id, person_id, source, created_at, "
            "updated_at) VALUES (?, ?, ?, ?, ?)",
            (batch_id, person_id or self.person_id, source, _now(), _now()),
        )
        return batch_id

    def _insert_candidate(self, con, batch_id, person_id=None,
                          candidate_id=None, external_id=None, **extra):
        candidate_id = candidate_id or str(uuid.uuid4())
        cols = ["id", "batch_id", "person_id", "external_id",
                "created_at", "updated_at"]
        vals = [candidate_id, batch_id, person_id or self.person_id,
                external_id or uuid.uuid4().hex, _now(), _now()]
        for k, v in extra.items():
            cols.append(k)
            vals.append(v)
        con.execute(
            f"INSERT INTO {'import_candidate'} ({', '.join(cols)}) "
            f"VALUES ({', '.join('?' * len(vals))})",
            vals,
        )
        return candidate_id


# -- migration lands clean --------------------------------------------

class MigrationLandsCleanTest(_FreshDBBase):
    def test_migration_recorded_in_schema_migrations(self):
        con = self._con()
        try:
            rows = con.execute(
                "SELECT filename FROM schema_migrations WHERE filename = ?;",
                (MIGRATION,),
            ).fetchall()
            self.assertEqual(len(rows), 1, f"{MIGRATION} should be recorded once")
        finally:
            con.close()

    def test_foreign_key_check_returns_zero_rows(self):
        con = self._con()
        try:
            violations = con.execute("PRAGMA foreign_key_check;").fetchall()
            self.assertEqual(violations, [], f"got {violations!r}")
        finally:
            con.close()

    def test_integrity_check_ok(self):
        con = self._con()
        try:
            self.assertEqual(
                con.execute("PRAGMA integrity_check;").fetchone()[0], "ok")
        finally:
            con.close()


# -- FK A: photos.narrator_id -> people(id) ---------------------------

class PhotosNarratorFkTest(_FreshDBBase):
    def test_photos_narrator_id_has_cascade_fk_to_people(self):
        con = self._con()
        try:
            fks = con.execute("PRAGMA foreign_key_list(photos);").fetchall()
            matching = [r for r in fks
                        if r[2] == "people" and r[3] == "narrator_id"]
            self.assertEqual(len(matching), 1,
                             f"exactly one FK expected; got {fks!r}")
            self.assertEqual(matching[0][6], "CASCADE")
        finally:
            con.close()

    def test_photo_with_unknown_narrator_is_rejected(self):
        """The silent-empty-list bug, made loud."""
        con = self._con()
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                self._insert_photo(con, str(uuid.uuid4()))
        finally:
            con.close()

    def test_deleting_person_cascades_their_photos(self):
        con = self._con()
        try:
            self._insert_photo(con, self.person_id)
            self._insert_photo(con, self.person_id)
            con.commit()
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM photos;").fetchone()[0], 2)
            con.execute("DELETE FROM people WHERE id = ?;", (self.person_id,))
            con.commit()
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM photos;").fetchone()[0], 0)
        finally:
            con.close()

    def test_photos_indexes_survive_the_rebuild(self):
        """The migration DROPs photos, which drops its indexes. If it
        forgets to recreate them, every narrator-scoped photo query
        degrades to a table scan and nothing fails loudly."""
        con = self._con()
        try:
            names = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND tbl_name='photos';")}
            for expected in ("idx_photos_narrator_id",
                             "idx_photos_narrator_ready",
                             "idx_photos_date",
                             "idx_photos_uploaded_by",
                             "idx_photos_deleted_at"):
                self.assertIn(expected, names)
        finally:
            con.close()

    def test_file_hash_uniqueness_survives_the_rebuild(self):
        con = self._con()
        try:
            shared = uuid.uuid4().hex
            for i in range(2):
                stmt = (
                    "INSERT INTO photos (id, narrator_id, image_path, "
                    "file_hash, created_at, updated_at) VALUES (?,?,?,?,?,?)")
                args = (str(uuid.uuid4()), self.person_id, f"/tmp/{i}.jpg",
                        shared, _now(), _now())
                if i == 0:
                    con.execute(stmt, args)
                else:
                    with self.assertRaises(sqlite3.IntegrityError):
                        con.execute(stmt, args)
        finally:
            con.close()


# -- FK B: trip_photo_links.photo_id -> photos(id) --------------------

class TripPhotoLinkFkTest(_FreshDBBase):
    def test_photo_id_has_cascade_fk_to_photos(self):
        con = self._con()
        try:
            fks = con.execute(
                "PRAGMA foreign_key_list(trip_photo_links);").fetchall()
            matching = [r for r in fks
                        if r[2] == "photos" and r[3] == "photo_id"]
            self.assertEqual(len(matching), 1,
                             f"exactly one FK expected; got {fks!r}")
            self.assertEqual(matching[0][6], "CASCADE")
        finally:
            con.close()

    def test_pre_existing_trip_fk_survives_the_rebuild(self):
        con = self._con()
        try:
            fks = con.execute(
                "PRAGMA foreign_key_list(trip_photo_links);").fetchall()
            trip_fk = [r for r in fks if r[2] == "trips" and r[3] == "trip_id"]
            self.assertEqual(len(trip_fk), 1, f"got {fks!r}")
            self.assertEqual(trip_fk[0][6], "CASCADE")
            self.assertEqual(
                {r[2] for r in fks},
                {"trips", "trip_regions", "trip_stops", "trip_days", "photos"},
            )
        finally:
            con.close()

    def test_link_to_unknown_photo_is_rejected(self):
        con = self._con()
        try:
            trip_id = self._insert_trip(con, self.person_id)
            with self.assertRaises(sqlite3.IntegrityError):
                self._insert_link(con, trip_id, str(uuid.uuid4()))
        finally:
            con.close()

    def test_deleting_a_person_now_reaches_the_trip_links(self):
        """people -> photos -> trip_photo_links. Before 0037 the chain
        stopped at photos and left the links stranded, which is exactly
        the orphan class the Phase 1.1 sweep had to look for by hand."""
        con = self._con()
        try:
            trip_id = self._insert_trip(con, self.person_id)
            photo_id = self._insert_photo(con, self.person_id)
            self._insert_link(con, trip_id, photo_id)
            con.commit()
            self.assertEqual(
                con.execute(
                    "SELECT COUNT(*) FROM trip_photo_links;").fetchone()[0], 1)
            con.execute("DELETE FROM people WHERE id = ?;", (self.person_id,))
            con.commit()
            self.assertEqual(
                con.execute(
                    "SELECT COUNT(*) FROM trip_photo_links;").fetchone()[0], 0)
            self.assertEqual(
                con.execute("PRAGMA foreign_key_check;").fetchall(), [])
        finally:
            con.close()

    def test_trip_photo_link_indexes_survive_the_rebuild(self):
        con = self._con()
        try:
            names = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND tbl_name='trip_photo_links';")}
            for expected in ("idx_trip_photo_links_trip_id",
                             "idx_trip_photo_links_stop_id",
                             "idx_trip_photo_links_confidence",
                             "idx_trip_photo_links_trip_photo",
                             "idx_trip_photo_links_day",
                             "idx_trip_photo_links_hidden"):
                self.assertIn(expected, names)
        finally:
            con.close()

    def test_trip_photo_uniqueness_survives_the_rebuild(self):
        con = self._con()
        try:
            trip_id = self._insert_trip(con, self.person_id)
            photo_id = self._insert_photo(con, self.person_id)
            self._insert_link(con, trip_id, photo_id)
            with self.assertRaises(sqlite3.IntegrityError):
                self._insert_link(con, trip_id, photo_id)
        finally:
            con.close()


# -- import_batch ------------------------------------------------------

class ImportBatchTest(_FreshDBBase):
    def test_batch_requires_a_real_person(self):
        con = self._con()
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                self._insert_batch(con, person_id=str(uuid.uuid4()))
        finally:
            con.close()

    def test_unknown_source_is_rejected(self):
        con = self._con()
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                self._insert_batch(con, source="dropbox")
        finally:
            con.close()

    def test_every_declared_source_is_accepted(self):
        con = self._con()
        try:
            for src in ("google_photos_picker", "google_takeout",
                        "local_upload", "csv", "manual"):
                self._insert_batch(con, source=src)
            con.commit()
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM import_batch;").fetchone()[0], 5)
        finally:
            con.close()

    def test_status_defaults_to_open_and_rejects_unknown(self):
        con = self._con()
        try:
            bid = self._insert_batch(con)
            con.commit()
            self.assertEqual(
                con.execute("SELECT status FROM import_batch WHERE id=?;",
                            (bid,)).fetchone()[0], "open")
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("UPDATE import_batch SET status='archived' WHERE id=?;",
                            (bid,))
        finally:
            con.close()

    def test_hidden_defaults_to_zero_and_is_reversible(self):
        con = self._con()
        try:
            bid = self._insert_batch(con)
            con.commit()
            self.assertEqual(
                con.execute("SELECT hidden, hidden_at FROM import_batch "
                            "WHERE id=?;", (bid,)).fetchone(), (0, None))
            con.execute("UPDATE import_batch SET hidden=1, hidden_at=? "
                        "WHERE id=?;", (_now(), bid))
            con.execute("UPDATE import_batch SET hidden=0, hidden_at=NULL "
                        "WHERE id=?;", (bid,))
            con.commit()
            self.assertEqual(
                con.execute("SELECT hidden, hidden_at FROM import_batch "
                            "WHERE id=?;", (bid,)).fetchone(), (0, None))
        finally:
            con.close()

    def test_deleting_the_person_removes_their_batches(self):
        con = self._con()
        try:
            self._insert_batch(con)
            con.commit()
            con.execute("DELETE FROM people WHERE id=?;", (self.person_id,))
            con.commit()
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM import_batch;").fetchone()[0], 0)
        finally:
            con.close()

    def test_batch_carries_no_token_columns(self):
        con = self._con()
        try:
            cols = {r[1].lower() for r in con.execute(
                "PRAGMA table_info(import_batch);")}
            for banned in ("access_token", "refresh_token", "token",
                           "authorization", "credentials", "cookie",
                           "client_secret", "api_key", "password"):
                self.assertNotIn(banned, cols,
                                 f"import_batch must never store {banned!r}")
        finally:
            con.close()


# -- import_candidate --------------------------------------------------

class ImportCandidateTest(_FreshDBBase):
    def test_candidate_requires_a_real_batch(self):
        con = self._con()
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                self._insert_candidate(con, batch_id=str(uuid.uuid4()))
        finally:
            con.close()

    def test_candidate_requires_a_real_person(self):
        con = self._con()
        try:
            bid = self._insert_batch(con)
            with self.assertRaises(sqlite3.IntegrityError):
                self._insert_candidate(con, bid, person_id=str(uuid.uuid4()))
        finally:
            con.close()

    def test_state_defaults_to_pending_and_rejects_unknown(self):
        con = self._con()
        try:
            bid = self._insert_batch(con)
            cid = self._insert_candidate(con, bid)
            con.commit()
            self.assertEqual(
                con.execute("SELECT state FROM import_candidate WHERE id=?;",
                            (cid,)).fetchone()[0], "pending")
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("UPDATE import_candidate SET state='approved' "
                            "WHERE id=?;", (cid,))
        finally:
            con.close()

    def test_declared_states_are_accepted(self):
        con = self._con()
        try:
            bid = self._insert_batch(con)
            cid = self._insert_candidate(con, bid)
            for st in ("pending", "accepted", "rejected", "duplicate", "error"):
                con.execute("UPDATE import_candidate SET state=? WHERE id=?;",
                            (st, cid))
            con.commit()
        finally:
            con.close()

    def test_same_external_id_cannot_land_twice_in_one_batch(self):
        """Re-running a fetch is idempotent, not duplicative."""
        con = self._con()
        try:
            bid = self._insert_batch(con)
            self._insert_candidate(con, bid, external_id="google:abc123")
            with self.assertRaises(sqlite3.IntegrityError):
                self._insert_candidate(con, bid, external_id="google:abc123")
        finally:
            con.close()

    def test_same_external_id_may_land_in_a_different_batch(self):
        con = self._con()
        try:
            b1 = self._insert_batch(con)
            b2 = self._insert_batch(con)
            self._insert_candidate(con, b1, external_id="google:abc123")
            self._insert_candidate(con, b2, external_id="google:abc123")
            con.commit()
            self.assertEqual(
                con.execute(
                    "SELECT COUNT(*) FROM import_candidate;").fetchone()[0], 2)
        finally:
            con.close()

    def test_deleting_a_batch_cascades_its_candidates(self):
        con = self._con()
        try:
            bid = self._insert_batch(con)
            self._insert_candidate(con, bid)
            self._insert_candidate(con, bid)
            con.commit()
            con.execute("DELETE FROM import_batch WHERE id=?;", (bid,))
            con.commit()
            self.assertEqual(
                con.execute(
                    "SELECT COUNT(*) FROM import_candidate;").fetchone()[0], 0)
        finally:
            con.close()

    def test_photo_id_is_set_null_not_cascade(self):
        """A candidate is the record that an import happened. If the
        photo it produced is later deleted, the candidate and its match
        reasons must survive -- otherwise the provenance trail is the
        first thing lost."""
        con = self._con()
        try:
            bid = self._insert_batch(con)
            photo_id = self._insert_photo(con, self.person_id)
            cid = self._insert_candidate(con, bid, photo_id=photo_id,
                                         state="accepted")
            con.commit()
            con.execute("DELETE FROM photos WHERE id=?;", (photo_id,))
            con.commit()
            row = con.execute(
                "SELECT photo_id, state FROM import_candidate WHERE id=?;",
                (cid,)).fetchone()
            self.assertIsNotNone(row, "candidate must survive the photo")
            self.assertIsNone(row[0], "photo_id must be nulled, not cascaded")
            self.assertEqual(row[1], "accepted")
        finally:
            con.close()

    def test_match_reason_json_round_trips_unchanged(self):
        con = self._con()
        try:
            bid = self._insert_batch(con)
            payload = ('{"rules":["exif_time_in_trip_window",'
                       '"gps_within_25km_of_stop"],"stop_id":"s-1"}')
            cid = self._insert_candidate(con, bid, match_reason_json=payload)
            con.commit()
            self.assertEqual(
                con.execute("SELECT match_reason_json FROM import_candidate "
                            "WHERE id=?;", (cid,)).fetchone()[0], payload)
        finally:
            con.close()

    def test_match_reason_json_defaults_to_empty_object(self):
        con = self._con()
        try:
            bid = self._insert_batch(con)
            cid = self._insert_candidate(con, bid)
            con.commit()
            self.assertEqual(
                con.execute("SELECT match_reason_json FROM import_candidate "
                            "WHERE id=?;", (cid,)).fetchone()[0], "{}")
        finally:
            con.close()

    def test_unknown_taken_at_source_is_rejected(self):
        con = self._con()
        try:
            bid = self._insert_batch(con)
            with self.assertRaises(sqlite3.IntegrityError):
                self._insert_candidate(con, bid, taken_at_source="astrology")
        finally:
            con.close()

    def test_unknown_location_source_is_rejected(self):
        con = self._con()
        try:
            bid = self._insert_batch(con)
            with self.assertRaises(sqlite3.IntegrityError):
                self._insert_candidate(con, bid, location_source="vibes")
        finally:
            con.close()


# -- the scope wall ----------------------------------------------------

class IntakeIsNotApprovalTest(_FreshDBBase):
    """These four tests exist to fail loudly if someone widens intake
    into approval. Deleting one of them is the change that needs the
    argument, not a column addition that quietly slips through."""

    def test_candidate_has_no_narrator_ready_column(self):
        con = self._con()
        try:
            cols = {r[1] for r in con.execute(
                "PRAGMA table_info(import_candidate);")}
            self.assertNotIn(
                "narrator_ready", cols,
                "creating a candidate does not mean narrator-ready; "
                "narrator_ready belongs on photos, after operator acceptance")
        finally:
            con.close()

    def test_candidate_has_no_memoir_inclusion_column(self):
        con = self._con()
        try:
            cols = {r[1] for r in con.execute(
                "PRAGMA table_info(import_candidate);")}
            self.assertNotIn(
                "include_in_memoir", cols,
                "creating a candidate does not mean memoir inclusion; "
                "include_in_memoir belongs on trip_photo_links")
        finally:
            con.close()

    def test_candidate_carries_no_token_columns(self):
        con = self._con()
        try:
            cols = {r[1].lower() for r in con.execute(
                "PRAGMA table_info(import_candidate);")}
            for banned in ("access_token", "refresh_token", "token",
                           "authorization", "credentials", "cookie",
                           "client_secret", "api_key", "password"):
                self.assertNotIn(banned, cols,
                                 f"import_candidate must never store {banned!r}")
        finally:
            con.close()

    def test_accepted_state_does_not_touch_photo_flags(self):
        """Marking a candidate accepted is an intake transition. It must
        not, on its own, make anything narrator-ready."""
        con = self._con()
        try:
            bid = self._insert_batch(con)
            photo_id = self._insert_photo(con, self.person_id)
            cid = self._insert_candidate(con, bid, photo_id=photo_id)
            con.commit()
            con.execute("UPDATE import_candidate SET state='accepted' "
                        "WHERE id=?;", (cid,))
            con.commit()
            ready, needs = con.execute(
                "SELECT narrator_ready, needs_confirmation FROM photos "
                "WHERE id=?;", (photo_id,)).fetchone()
            self.assertEqual(ready, 0)
            self.assertEqual(needs, 1)
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
