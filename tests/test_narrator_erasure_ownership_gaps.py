"""WO-LOREVOX-PORTABLE-NARRATOR-01 Phase 1, Step 1 — erasure gap tests.

Phase 0 found three places where narrator-owned rows are reachable by
export but not by erasure, plus one chain that is reachable and needs
proving. These tests pin the REQUIRED FINAL SEMANTICS through the real
production boundary, `db.hard_delete_person()`, with the normal
`PRAGMA foreign_keys=ON` the product uses:

    hard-delete of narrator A SUCCEEDS (no rollback, no plan refusal),
    A's rows in the lane are GONE,
    narrator B and B's rows are UNTOUCHED.

WHY "refused loudly" IS NOT AN ACCEPTABLE PASS. An FK declared without
ON DELETE (NO ACTION) makes the whole hard-delete roll back when a child
row exists. A test that accepted "rows gone OR delete refused" would be
GREEN at HEAD for exactly the two lanes whose defect IS that refusal —
and would prove nothing when the repair landed. So the assertion is
success-and-gone, and nothing else.

At HEAD (2026-09-10) the expectation, from Phase 0 evidence:

    interview_threads               RED  — 0009:56 FK to interview_sessions, no ON DELETE;
                                           nothing in hard-delete deletes threads
    trip_photo_day_placement_skips  RED  — no FK at all (0043); not in
                                           _EXTENDED_PERSON_SCOPED_TABLES
    media_archive_people (other-person tag)
                                    RED  — 0003:156 FK to media_archive_items, no ON DELETE;
                                           deleted only by its OWN person_id (db.py:5613),
                                           so a tag naming B on A's item is deleted by
                                           neither path and blocks the parent
    turns                           GREEN — turns.conv_id -> sessions ON DELETE CASCADE
                                           (db.py:595); sessions deleted by person_id.
                                           Preservation evidence, not a repair.

Fixtures supply ROWS. The property under test — what survives a
hard-delete — is produced by production code only. Setup uses raw SQL on
the same connection factory the product uses so the schema, FK settings
and constraints are the shipped ones; no fixture builds the schema by
hand and no test deletes a parent row directly.

Run:
    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python -m unittest \\
        tests.test_narrator_erasure_ownership_gaps
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_CODE = REPO_ROOT / "server" / "code"
if str(SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(SERVER_CODE))


def _uid() -> str:
    return str(uuid.uuid4())


class _DbCase(unittest.TestCase):
    """Own database per test, under a temp DATA_DIR. Same discipline as
    tests/test_people_testing_only_persistence.py: `db.py` binds DB_PATH
    at import, so the module is reloaded after the environment is set,
    and the case REFUSES to run unless DB_PATH is under the temp dir."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._prev = {k: os.environ.get(k) for k in ("DATA_DIR", "DB_NAME")}
        os.environ["DATA_DIR"] = self._tmp.name
        os.environ["DB_NAME"] = "test_erasure_gaps.sqlite3"
        from api import db as _db
        importlib.reload(_db)
        self.db = _db
        self.db.init_db()
        self.assertTrue(
            str(self.db.DB_PATH).startswith(self._tmp.name),
            f"REFUSING: DB_PATH is {self.db.DB_PATH}, not under the temp dir. "
            f"This suite hard-deletes narrators and must never see a real database.")
        self.addCleanup(self._restore)

    def _restore(self):
        for key, value in self._prev.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        from api import db as _db
        importlib.reload(_db)

    # ── helpers: rows in, via the product's own connection ─────────────

    def _con(self):
        return self.db._connect()

    def _person(self, name):
        return self.db.create_person(display_name=name)["id"]

    def _count(self, sql, *params) -> int:
        con = self._con()
        try:
            return con.execute(sql, params).fetchone()[0]
        finally:
            con.close()

    def _hard_delete_must_succeed(self, person_id):
        result = self.db.hard_delete_person(person_id, requested_by="phase1-gap-test")
        self.assertIsNotNone(result, "hard_delete_person returned None (person not found?)")
        self.assertNotIn(
            "error", result,
            f"hard-delete did NOT succeed: {result!r}. A rollback or a refused plan "
            f"is the defect, not an acceptable outcome.")
        self.assertEqual(
            self._count("SELECT COUNT(*) FROM people WHERE id=?", person_id), 0,
            "people row survived a successful hard-delete")
        return result


class InterviewThreadsGoWithTheNarrator(_DbCase):
    """GAP at HEAD. 0009:56 declares the FK without ON DELETE; hard-delete
    never names interview_threads; the cascade from people reaches
    interview_sessions and stops."""

    def test_hard_delete_succeeds_and_threads_are_gone(self):
        a = self._person("Narrator A")
        b = self._person("Narrator B")
        con = self._con()
        try:
            plan = _uid()
            con.execute("INSERT INTO interview_plans (id, title, created_at) VALUES (?, ?, ?)",
                        (plan, "gap-test plan", "2026-09-10T00:00:00Z"))
            sess_a, sess_b = _uid(), _uid()
            for pid, sid in ((a, sess_a), (b, sess_b)):
                con.execute(
                    "INSERT INTO interview_sessions (id, person_id, plan_id, started_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (sid, pid, plan, "2026-09-10T00:00:00Z", "2026-09-10T00:00:00Z"))
                con.execute(
                    "INSERT INTO interview_threads (id, session_id, thread_anchor, introduced_at) "
                    "VALUES (?, ?, ?, ?)",
                    (_uid(), sid, "the cemetery walk", "2026-09-10T00:00:00Z"))
            con.commit()
        finally:
            con.close()

        self._hard_delete_must_succeed(a)

        self.assertEqual(
            self._count("SELECT COUNT(*) FROM interview_sessions WHERE person_id=?", a), 0)
        self.assertEqual(
            self._count("SELECT COUNT(*) FROM interview_threads WHERE session_id=?", sess_a), 0,
            "A's interview_threads survived A's hard-delete")
        # B untouched.
        self.assertEqual(
            self._count("SELECT COUNT(*) FROM interview_sessions WHERE person_id=?", b), 1)
        self.assertEqual(
            self._count("SELECT COUNT(*) FROM interview_threads WHERE session_id=?", sess_b), 1)


class PlacementSkipsGoWithTheNarratorsTrips(_DbCase):
    """GAP at HEAD. Migration 0043 created the skip ledger with trip_id and
    no FK; it is in no deletion list; ownership is trips.person_id."""

    def test_hard_delete_succeeds_and_only_As_skips_are_gone(self):
        a = self._person("Narrator A")
        b = self._person("Narrator B")
        con = self._con()
        try:
            trip_a, trip_b = _uid(), _uid()
            con.execute("INSERT INTO trips (id, person_id, title) VALUES (?, ?, ?)",
                        (trip_a, a, "A's trip"))
            con.execute("INSERT INTO trips (id, person_id, title) VALUES (?, ?, ?)",
                        (trip_b, b, "B's trip"))
            for trip in (trip_a, trip_b):
                con.execute(
                    "INSERT INTO trip_photo_day_placement_skips "
                    "(id, photo_link_id, trip_id, reason, detected_at) VALUES (?, ?, ?, ?, ?)",
                    (_uid(), _uid(), trip, "legacy_day_missing", "2026-09-10T00:00:00Z"))
            con.commit()
        finally:
            con.close()

        self._hard_delete_must_succeed(a)

        self.assertEqual(self._count("SELECT COUNT(*) FROM trips WHERE person_id=?", a), 0)
        self.assertEqual(
            self._count("SELECT COUNT(*) FROM trip_photo_day_placement_skips WHERE trip_id=?", trip_a), 0,
            "A's placement-skip row survived A's hard-delete")
        self.assertEqual(self._count("SELECT COUNT(*) FROM trips WHERE person_id=?", b), 1)
        self.assertEqual(
            self._count("SELECT COUNT(*) FROM trip_photo_day_placement_skips WHERE trip_id=?", trip_b), 1,
            "B's placement-skip row was touched by A's hard-delete")


class OtherPersonTagGoesWithTheOwnedItem(_DbCase):
    """GAP at HEAD. A owns the archive item; the tag names B. The tag is
    deleted by neither its own person_id (B) nor by parent (links and
    family_lines are, people is not — db.py:5696-5705 vs :5613), and its
    NO ACTION FK blocks the parent delete."""

    def test_hard_delete_of_owner_succeeds_and_B_is_untouched(self):
        a = self._person("Narrator A")
        b = self._person("Narrator B")
        con = self._con()
        try:
            item = _uid()
            con.execute(
                "INSERT INTO media_archive_items "
                "(id, person_id, title, original_filename, mime_type, storage_path, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (item, a, "A's letter", "letter.pdf", "application/pdf",
                 "media/archive/people/%s/letter.pdf" % a,
                 "2026-09-10T00:00:00Z", "2026-09-10T00:00:00Z"))
            con.execute(
                "INSERT INTO media_archive_people "
                "(id, archive_item_id, person_id, person_label, role, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (_uid(), item, b, "Narrator B", "relative", "2026-09-10T00:00:00Z"))
            con.commit()
        finally:
            con.close()

        self._hard_delete_must_succeed(a)

        self.assertEqual(
            self._count("SELECT COUNT(*) FROM media_archive_items WHERE id=?", item), 0,
            "A's archive item survived A's hard-delete")
        self.assertEqual(
            self._count("SELECT COUNT(*) FROM media_archive_people WHERE archive_item_id=?", item), 0,
            "the tag on A's item survived A's hard-delete")
        # B is not deleted, not altered.
        self.assertEqual(self._count("SELECT COUNT(*) FROM people WHERE id=?", b), 1)
        self.assertEqual(
            self.db.get_person(b)["display_name"], "Narrator B")


class TurnsCascadeFromSessions(_DbCase):
    """VERIFY, expected GREEN at HEAD. turns.conv_id -> sessions(conv_id)
    ON DELETE CASCADE (db.py:595); sessions.person_id is deleted by
    _extended_person_scoped_delete. This is preservation evidence for
    the one column-only chain that already works."""

    def test_hard_delete_succeeds_and_turns_go_with_sessions(self):
        a = self._person("Narrator A")
        b = self._person("Narrator B")
        con = self._con()
        try:
            conv_a, conv_b = "conv-" + _uid(), "conv-" + _uid()
            for pid, conv in ((a, conv_a), (b, conv_b)):
                con.execute(
                    "INSERT INTO sessions (conv_id, title, updated_at, person_id) VALUES (?, ?, ?, ?)",
                    (conv, "t", "2026-09-10T00:00:00Z", pid))
                for role, text in (("user", "My brother Dennis walked me to school."),
                                   ("assistant", "What was that walk like?")):
                    con.execute(
                        "INSERT INTO turns (conv_id, role, content, ts) VALUES (?, ?, ?, ?)",
                        (conv, role, text, "2026-09-10T00:00:00Z"))
            con.commit()
        finally:
            con.close()

        self._hard_delete_must_succeed(a)

        self.assertEqual(self._count("SELECT COUNT(*) FROM sessions WHERE conv_id=?", conv_a), 0)
        self.assertEqual(
            self._count("SELECT COUNT(*) FROM turns WHERE conv_id=?", conv_a), 0,
            "A's turns survived the deletion of A's session")
        self.assertEqual(self._count("SELECT COUNT(*) FROM sessions WHERE conv_id=?", conv_b), 1)
        self.assertEqual(self._count("SELECT COUNT(*) FROM turns WHERE conv_id=?", conv_b), 2)


if __name__ == "__main__":
    unittest.main()
