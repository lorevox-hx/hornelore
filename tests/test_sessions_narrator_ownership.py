"""WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 commit 2 -- sessions carry an owner.

Locks R2.1 (the column and its index), R2.4 (write-once ownership -- never
cleared, never overwritten), R2.5 (reads prefer the column and legacy JSON
still resolves) and R2.6 (nothing is destroyed, nothing is inferred).

The defect this pins, measured during the L2 partial run on 2026-08-16: every
`sessions` row had `payload_json` literally '{}' -- 56 of 56 -- so no session
could be attributed to any narrator, including the four created by the run
itself. Downstream, `get_narrator_state_snapshot`'s `user_turn_count` joined on
json_extract(payload_json,'$.active_person_id') and was therefore structurally
always 0, which made every returning narrator look brand new to the UI.

pytest is not installed in this repo. Run with:

    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_sessions_narrator_ownership
"""
from __future__ import annotations

import json
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

_MIGRATION = "0044_sessions_person_id.sql"


class _Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        tmp.close()
        self.db_path = Path(tmp.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()
        self.person_id = self._insert_person("Test Narrator One")
        self.other_id = self._insert_person("Test Narrator Two")

    def tearDown(self):
        _db.DB_PATH = self._orig_db
        try:
            self.db_path.unlink()
        except OSError:
            pass

    # -- helpers -----------------------------------------------------------
    def _con(self):
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        return con

    def _insert_person(self, name):
        pid = str(uuid.uuid4())
        con = self._con()
        con.execute(
            "INSERT INTO people (id, display_name, date_of_birth, created_at, updated_at) "
            "VALUES (?, ?, '1950-03-11', '2026-08-16', '2026-08-16')",
            (pid, name),
        )
        con.commit()
        con.close()
        return pid

    def _row(self, conv_id):
        con = self._con()
        row = con.execute("SELECT * FROM sessions WHERE conv_id=?", (conv_id,)).fetchone()
        con.close()
        return dict(row) if row else None


class SchemaLock(_Base):
    """R2.1/R2.2 -- the column exists, is nullable, and there is no FK."""

    def test_migration_is_recorded_as_applied(self):
        con = self._con()
        row = con.execute(
            "SELECT filename FROM schema_migrations WHERE filename=?", (_MIGRATION,)
        ).fetchone()
        con.close()
        self.assertIsNotNone(row, f"{_MIGRATION} did not apply")

    def test_person_id_column_exists_and_is_nullable(self):
        con = self._con()
        cols = {r["name"]: r for r in con.execute("PRAGMA table_info(sessions)")}
        con.close()
        self.assertIn("person_id", cols)
        self.assertEqual(cols["person_id"]["type"].upper(), "TEXT")
        self.assertEqual(
            cols["person_id"]["notnull"],
            0,
            "must stay nullable -- historical rows legitimately have no known owner",
        )

    def test_index_exists_with_house_name(self):
        con = self._con()
        names = {r["name"] for r in con.execute("PRAGMA index_list(sessions)")}
        con.close()
        self.assertIn("idx_sessions_person_updated", names)

    def test_no_foreign_key_was_added(self):
        # R2.2 -- deliberate. Adding one requires a table REBUILD, which
        # cascades into `turns`. If someone later adds it, this test should
        # fail loudly so the decision is made on purpose, not in passing.
        con = self._con()
        fks = list(con.execute("PRAGMA foreign_key_list(sessions)"))
        con.close()
        self.assertEqual(fks, [], "sessions FK is separately authorized work, not this commit")

    def test_payload_json_survives_untouched(self):
        # R2.6 -- nothing is destroyed.
        con = self._con()
        cols = {r["name"] for r in con.execute("PRAGMA table_info(sessions)")}
        con.close()
        self.assertIn("payload_json", cols)


class OwnershipIsWrittenOnce(_Base):
    """R2.4 -- never cleared by a NULL, never overwritten by a different id."""

    def test_ensure_session_records_the_owner(self):
        conv = "ws_" + uuid.uuid4().hex
        _db.ensure_session(conv, title="oral_history", person_id=self.person_id)
        self.assertEqual(self._row(conv)["person_id"], self.person_id)

    def test_omitting_person_id_records_null_not_a_guess(self):
        conv = "ws_" + uuid.uuid4().hex
        _db.ensure_session(conv, title="")
        self.assertIsNone(self._row(conv)["person_id"])

    def test_a_later_null_does_not_clear_an_existing_owner(self):
        conv = "ws_" + uuid.uuid4().hex
        _db.ensure_session(conv, person_id=self.person_id)
        _db.ensure_session(conv)  # e.g. a legacy caller that has no narrator
        self.assertEqual(self._row(conv)["person_id"], self.person_id)

    def test_a_different_owner_FAILS_rather_than_replacing(self):
        # Supervisor requirement (2026-08-16): "if a session is already
        # owned by narrator A, a later call for narrator B must fail --
        # not silently replace the owner." Keeping A quietly would also
        # have been a silent resolution; the contradiction IS the
        # information, so it is raised while the caller is on the stack.
        conv = "ws_" + uuid.uuid4().hex
        _db.ensure_session(conv, person_id=self.person_id)
        with self.assertRaises(_db.SessionOwnerConflict) as ctx:
            _db.ensure_session(conv, person_id=self.other_id)
        self.assertEqual(ctx.exception.stored_person_id, self.person_id)
        self.assertEqual(ctx.exception.incoming_person_id, self.other_id)
        # And the stored owner is untouched by the refusal.
        self.assertEqual(self._row(conv)["person_id"], self.person_id)

    def test_reasserting_the_same_owner_is_silent(self):
        conv = "ws_" + uuid.uuid4().hex
        _db.ensure_session(conv, person_id=self.person_id)
        _db.ensure_session(conv, person_id=self.person_id)
        self.assertEqual(self._row(conv)["person_id"], self.person_id)

    def test_upsert_session_also_refuses_a_reassignment(self):
        conv = "c_" + uuid.uuid4().hex
        _db.upsert_session(conv, "t", {"person_id": self.person_id})
        with self.assertRaises(_db.SessionOwnerConflict):
            _db.upsert_session(conv, "t", {"person_id": self.other_id})

    def test_add_turn_carries_the_owner(self):
        # The sibling writer to persist_turn_transaction. Left out, it
        # would have been a second way to mint an ownerless session.
        conv = "c_" + uuid.uuid4().hex
        _db.add_turn(conv, "user", "hello", person_id=self.person_id)
        self.assertEqual(self._row(conv)["person_id"], self.person_id)

    def test_add_turn_accepts_the_owner_from_meta(self):
        conv = "c_" + uuid.uuid4().hex
        _db.add_turn(conv, "user", "hello", meta={"person_id": self.person_id})
        self.assertEqual(self._row(conv)["person_id"], self.person_id)

    def test_blank_string_is_treated_as_absent(self):
        conv = "ws_" + uuid.uuid4().hex
        _db.ensure_session(conv, person_id="   ")
        self.assertIsNone(self._row(conv)["person_id"])

    def test_upsert_session_reads_either_legacy_payload_key(self):
        for key in ("active_person_id", "person_id"):
            with self.subTest(key=key):
                conv = "c_" + uuid.uuid4().hex
                _db.upsert_session(conv, "t", {key: self.person_id})
                self.assertEqual(self._row(conv)["person_id"], self.person_id)

    def test_upsert_session_does_not_clear_on_a_later_empty_payload(self):
        conv = "c_" + uuid.uuid4().hex
        _db.upsert_session(conv, "t", {"person_id": self.person_id})
        _db.upsert_session(conv, "t", {})
        self.assertEqual(self._row(conv)["person_id"], self.person_id)


class TurnPersistenceCarriesTheOwner(_Base):
    """R2.3 -- the live WebSocket path stops dropping the id it holds."""

    def test_persist_turn_transaction_records_the_narrator(self):
        conv = "ws_" + uuid.uuid4().hex
        _db.persist_turn_transaction(
            conv_id=conv,
            user_message="hi",
            assistant_message="Hello.",
            model_name="local-llm-ws",
            person_id=self.person_id,
        )
        self.assertEqual(self._row(conv)["person_id"], self.person_id)

    def test_without_a_narrator_it_records_null(self):
        conv = "ws_" + uuid.uuid4().hex
        _db.persist_turn_transaction(
            conv_id=conv, user_message="hi", assistant_message="Hello."
        )
        self.assertIsNone(self._row(conv)["person_id"])

    def test_turn_rows_are_unaffected(self):
        # R2.6/§4.3 -- `turns` is deliberately not touched by this commit.
        conv = "ws_" + uuid.uuid4().hex
        _db.persist_turn_transaction(
            conv_id=conv, user_message="hi", assistant_message="Hello.",
            person_id=self.person_id,
        )
        con = self._con()
        cols = {r["name"] for r in con.execute("PRAGMA table_info(turns)")}
        n = con.execute("SELECT COUNT(*) c FROM turns WHERE conv_id=?", (conv,)).fetchone()["c"]
        con.close()
        self.assertNotIn("person_id", cols)
        self.assertEqual(n, 2)


class UserTurnCountResolvesOwnership(_Base):
    """R2.5 -- the count that was structurally stuck at 0."""

    def _add_turn(self, conv, text="hi", role="user"):
        con = self._con()
        con.execute(
            "INSERT INTO turns(conv_id,role,content,ts,anchor_id,meta_json) "
            "VALUES(?,?,?,'2026-08-16T00:00:00','','{}')",
            (conv, role, text),
        )
        con.commit()
        con.close()

    def test_counts_through_the_column(self):
        conv = "ws_" + uuid.uuid4().hex
        _db.ensure_session(conv, person_id=self.person_id)
        self._add_turn(conv)
        self._add_turn(conv, "and another")
        snap = _db.get_narrator_state_snapshot(self.person_id)
        self.assertEqual(snap["user_turn_count"], 2)

    def test_counts_through_legacy_active_person_id(self):
        conv = "c_" + uuid.uuid4().hex
        con = self._con()
        con.execute(
            "INSERT INTO sessions(conv_id,title,updated_at,payload_json) VALUES(?,'','',?)",
            (conv, json.dumps({"active_person_id": self.person_id})),
        )
        con.commit()
        con.close()
        self._add_turn(conv)
        self.assertEqual(_db.get_narrator_state_snapshot(self.person_id)["user_turn_count"], 1)

    def test_counts_through_the_key_app_js_actually_writes(self):
        # The mismatch that made even the rare recorded owner uncountable:
        # app.js wrote `person_id`, the reader looked for `active_person_id`.
        conv = "c_" + uuid.uuid4().hex
        con = self._con()
        con.execute(
            "INSERT INTO sessions(conv_id,title,updated_at,payload_json) VALUES(?,'','',?)",
            (conv, json.dumps({"person_id": self.person_id})),
        )
        con.commit()
        con.close()
        self._add_turn(conv)
        self.assertEqual(_db.get_narrator_state_snapshot(self.person_id)["user_turn_count"], 1)

    def test_system_directive_rows_still_excluded(self):
        conv = "ws_" + uuid.uuid4().hex
        _db.ensure_session(conv, person_id=self.person_id)
        self._add_turn(conv, "[SYSTEM: seed]")
        self.assertEqual(_db.get_narrator_state_snapshot(self.person_id)["user_turn_count"], 0)

    def test_another_narrators_turns_are_not_counted(self):
        conv = "ws_" + uuid.uuid4().hex
        _db.ensure_session(conv, person_id=self.other_id)
        self._add_turn(conv)
        self.assertEqual(_db.get_narrator_state_snapshot(self.person_id)["user_turn_count"], 0)

    def test_unowned_sessions_are_counted_for_nobody(self):
        conv = "ws_" + uuid.uuid4().hex
        _db.ensure_session(conv)
        self._add_turn(conv)
        for pid in (self.person_id, self.other_id):
            self.assertEqual(_db.get_narrator_state_snapshot(pid)["user_turn_count"], 0)


class ReadersSurfaceTheOwner(_Base):
    def test_get_session_owner_reads_the_column(self):
        conv = "ws_" + uuid.uuid4().hex
        _db.ensure_session(conv, person_id=self.person_id)
        self.assertEqual(_db.get_session_owner(conv), self.person_id)

    def test_get_session_owner_is_none_when_unrecorded(self):
        conv = "ws_" + uuid.uuid4().hex
        _db.ensure_session(conv)
        self.assertIsNone(_db.get_session_owner(conv))

    def test_get_session_owner_is_none_for_a_missing_session(self):
        self.assertIsNone(_db.get_session_owner("nope_" + uuid.uuid4().hex))

    def test_an_ownerless_payload_is_returned_UNCHANGED(self):
        # REGRESSION GUARD. An earlier cut injected `person_id: None` into
        # every payload. prompt_composer serialises this dict into the
        # composed prompt's trailing PROFILE_JSON blob, so every legacy
        # session -- including the shared "default" one -- began emitting
        # `PROFILE_JSON: {"person_id": null}` into Lori's system prompt.
        # A read helper must not change what the composer says.
        conv = "ws_" + uuid.uuid4().hex
        _db.ensure_session(conv)
        payload = _db.get_session_payload(conv)
        self.assertNotIn("person_id", payload)
        self.assertNotIn("active_person_id", payload)
        self.assertEqual(
            {k for k in payload}, {"conv_id", "title", "updated_at"}
        )

    def test_an_owned_payload_surfaces_the_owner(self):
        conv = "ws_" + uuid.uuid4().hex
        _db.ensure_session(conv, person_id=self.person_id)
        self.assertEqual(_db.get_session_payload(conv)["person_id"], self.person_id)

    def test_get_session_payload_falls_back_to_legacy_json(self):
        conv = "c_" + uuid.uuid4().hex
        con = self._con()
        con.execute(
            "INSERT INTO sessions(conv_id,title,updated_at,payload_json) VALUES(?,'','',?)",
            (conv, json.dumps({"active_person_id": self.person_id})),
        )
        con.commit()
        con.close()
        self.assertEqual(_db.get_session_payload(conv)["person_id"], self.person_id)

    def test_list_sessions_includes_person_id(self):
        conv = "ws_" + uuid.uuid4().hex
        _db.ensure_session(conv, person_id=self.person_id)
        items = {i["conv_id"]: i for i in _db.list_sessions(limit=50)}
        self.assertIn(conv, items)
        self.assertEqual(items[conv]["person_id"], self.person_id)


class BackfillIsRecordedLinksOnly(_Base):
    """§4.4 -- no attribution by inference, and the shortfall is countable."""

    def test_archive_link_backfills_on_migration(self):
        # Rebuild a DB that already holds a pre-0044 session plus a
        # recorded archive link, then let init_db apply the migration.
        conv = "c_" + uuid.uuid4().hex
        con = self._con()
        con.execute("DELETE FROM schema_migrations WHERE filename=?", (_MIGRATION,))
        con.execute("ALTER TABLE sessions RENAME TO sessions_old")
        con.execute(
            "CREATE TABLE sessions (conv_id TEXT PRIMARY KEY, title TEXT DEFAULT '', "
            "updated_at TEXT, payload_json TEXT DEFAULT '{}')"
        )
        con.execute("DROP TABLE sessions_old")
        con.execute("DROP INDEX IF EXISTS idx_sessions_person_updated")
        con.execute(
            "INSERT INTO sessions(conv_id,title,updated_at,payload_json) VALUES(?,'','','{}')",
            (conv,),
        )
        con.execute(
            "INSERT INTO memory_archive_sessions(id,person_id,conv_id,archive_dir,created_at,updated_at) "
            "VALUES(?,?,?,'archive/x','2026-08-16','2026-08-16')",
            (str(uuid.uuid4()), self.person_id, conv),
        )
        con.commit()
        con.close()

        _db.init_db()
        self.assertEqual(self._row(conv)["person_id"], self.person_id)

    def test_ambiguous_archive_link_is_declined(self):
        conv = "c_" + uuid.uuid4().hex
        con = self._con()
        con.execute("DELETE FROM schema_migrations WHERE filename=?", (_MIGRATION,))
        con.execute("ALTER TABLE sessions RENAME TO sessions_old")
        con.execute(
            "CREATE TABLE sessions (conv_id TEXT PRIMARY KEY, title TEXT DEFAULT '', "
            "updated_at TEXT, payload_json TEXT DEFAULT '{}')"
        )
        con.execute("DROP TABLE sessions_old")
        con.execute("DROP INDEX IF EXISTS idx_sessions_person_updated")
        con.execute(
            "INSERT INTO sessions(conv_id,title,updated_at,payload_json) VALUES(?,'','','{}')",
            (conv,),
        )
        for pid in (self.person_id, self.other_id):
            con.execute(
                "INSERT INTO memory_archive_sessions(id,person_id,conv_id,archive_dir,created_at,updated_at) "
                "VALUES(?,?,?,'archive/x','2026-08-16','2026-08-16')",
                (str(uuid.uuid4()), pid, conv),
            )
        con.commit()
        con.close()

        _db.init_db()
        self.assertIsNone(
            self._row(conv)["person_id"],
            "two recorded owners is ambiguity, and ambiguity is left NULL rather than picked",
        )

    def test_unlinked_rows_stay_null(self):
        conv = "c_" + uuid.uuid4().hex
        con = self._con()
        con.execute(
            "INSERT INTO sessions(conv_id,title,updated_at,payload_json) VALUES(?,'','','{}')",
            (conv,),
        )
        con.commit()
        con.close()
        _db.init_db()
        self.assertIsNone(self._row(conv)["person_id"])

    def test_unowned_count_is_reportable(self):
        before = _db.count_sessions_without_owner()
        _db.ensure_session("ws_" + uuid.uuid4().hex)
        _db.ensure_session("ws_" + uuid.uuid4().hex, person_id=self.person_id)
        self.assertEqual(_db.count_sessions_without_owner(), before + 1)


class BothSessionSystemsAreReconciled(_Base):
    """Supervisor requirement: interview_sessions.id = sessions.conv_id."""

    def _pre_0044_session(self, conv):
        con = self._con()
        con.execute("DELETE FROM schema_migrations WHERE filename=?", (_MIGRATION,))
        con.execute("ALTER TABLE sessions RENAME TO sessions_old")
        con.execute(
            "CREATE TABLE sessions (conv_id TEXT PRIMARY KEY, title TEXT DEFAULT '', "
            "updated_at TEXT, payload_json TEXT DEFAULT '{}')"
        )
        con.execute("DROP TABLE sessions_old")
        con.execute("DROP INDEX IF EXISTS idx_sessions_person_updated")
        con.execute(
            "INSERT INTO sessions(conv_id,title,updated_at,payload_json) VALUES(?,'','','{}')",
            (conv,),
        )
        return con

    def _interview_session(self, con, conv, pid):
        con.execute(
            "INSERT INTO interview_plans(id,title,created_at) VALUES(?,'p','2026-08-16')",
            ("plan_" + conv,),
        )
        con.execute(
            "INSERT INTO interview_sessions(id,person_id,plan_id,started_at,updated_at) "
            "VALUES(?,?,?,'2026-08-16','2026-08-16')",
            (conv, pid, "plan_" + conv),
        )

    def test_interview_session_id_backfills_the_owner(self):
        # chat_ws already writes ensure_interview_session(conv_id, person_id)
        # for the SAME conv_id whose sessions row it leaves ownerless. The
        # narrator was being written down one table over, under the
        # identical key.
        conv = "ws_" + uuid.uuid4().hex
        con = self._pre_0044_session(conv)
        self._interview_session(con, conv, self.person_id)
        con.commit()
        con.close()
        _db.init_db()
        self.assertEqual(self._row(conv)["person_id"], self.person_id)

    def test_interview_link_outranks_a_weaker_source(self):
        conv = "ws_" + uuid.uuid4().hex
        con = self._pre_0044_session(conv)
        self._interview_session(con, conv, self.person_id)
        con.execute(
            "INSERT INTO memory_archive_sessions"
            "(id,person_id,conv_id,archive_dir,created_at,updated_at) "
            "VALUES(?,?,?,'archive/x','2026-08-16','2026-08-16')",
            (str(uuid.uuid4()), self.other_id, conv),
        )
        con.commit()
        con.close()
        _db.init_db()
        self.assertEqual(
            self._row(conv)["person_id"],
            self.person_id,
            "the strongest recorded link must win; passes must not overwrite each other",
        )

    def test_turn_metadata_backfills_when_nothing_stronger_exists(self):
        conv = "ws_" + uuid.uuid4().hex
        con = self._pre_0044_session(conv)
        con.execute(
            "INSERT INTO turns(conv_id,role,content,ts,anchor_id,meta_json) "
            "VALUES(?,'user','hi','2026-08-16','',?)",
            (conv, json.dumps({"person_id": self.person_id})),
        )
        con.commit()
        con.close()
        _db.init_db()
        self.assertEqual(self._row(conv)["person_id"], self.person_id)

    def test_conflicting_turn_metadata_is_declined(self):
        conv = "ws_" + uuid.uuid4().hex
        con = self._pre_0044_session(conv)
        for pid in (self.person_id, self.other_id):
            con.execute(
                "INSERT INTO turns(conv_id,role,content,ts,anchor_id,meta_json) "
                "VALUES(?,'user','hi','2026-08-16','',?)",
                (conv, json.dumps({"person_id": pid})),
            )
        con.commit()
        con.close()
        _db.init_db()
        self.assertIsNone(self._row(conv)["person_id"])


class DeletionPolicyIsEnforcedWhereDeletionHappens(_Base):
    """No SQLite FK, but the behaviour a cascade would have given."""

    def _owned_session_with_turns(self):
        conv = "ws_" + uuid.uuid4().hex
        _db.persist_turn_transaction(
            conv_id=conv, user_message="hi", assistant_message="Hello.",
            person_id=self.person_id,
        )
        return conv

    def test_inventory_counts_sessions_before_confirmation(self):
        self._owned_session_with_turns()
        inv = _db.person_delete_inventory(self.person_id)
        self.assertEqual(inv["counts"]["sessions"], 1)

    def test_hard_delete_removes_owned_sessions_and_their_turns(self):
        conv = self._owned_session_with_turns()
        _db.hard_delete_person(self.person_id)
        con = self._con()
        s = con.execute("SELECT COUNT(*) c FROM sessions WHERE conv_id=?", (conv,)).fetchone()["c"]
        t = con.execute("SELECT COUNT(*) c FROM turns WHERE conv_id=?", (conv,)).fetchone()["c"]
        con.close()
        self.assertEqual(s, 0)
        self.assertEqual(t, 0, "turns follow through the existing cascade off sessions(conv_id)")

    def test_hard_delete_leaves_another_narrators_sessions_alone(self):
        mine = self._owned_session_with_turns()
        theirs = "ws_" + uuid.uuid4().hex
        _db.ensure_session(theirs, person_id=self.other_id)
        _db.hard_delete_person(self.person_id)
        self.assertIsNone(self._row(mine))
        self.assertIsNotNone(self._row(theirs))

    def test_hard_delete_does_not_sweep_up_unowned_rows(self):
        # Deleting those would mean guessing they belonged to this
        # narrator, which is the thing this lane exists to stop.
        self._owned_session_with_turns()
        orphan = "ws_" + uuid.uuid4().hex
        _db.ensure_session(orphan)
        _db.hard_delete_person(self.person_id)
        self.assertIsNotNone(self._row(orphan))

    def test_residue_is_reported_as_numbers(self):
        self._owned_session_with_turns()
        orphan = "ws_" + uuid.uuid4().hex
        _db.ensure_session(orphan)
        r = _db.session_ownership_residue()
        self.assertEqual(r["sessions_owned"], 1)
        self.assertEqual(r["sessions_unowned"], 1)
        self.assertEqual(r["sessions_total"], 2)
        self.assertIn("turns_in_unowned_sessions", r)


class ListsAndExportsUseTheField(_Base):
    def test_list_can_scope_to_one_narrator(self):
        mine = "ws_" + uuid.uuid4().hex
        theirs = "ws_" + uuid.uuid4().hex
        _db.ensure_session(mine, person_id=self.person_id)
        _db.ensure_session(theirs, person_id=self.other_id)
        ids = {i["conv_id"] for i in _db.list_sessions(limit=50, person_id=self.person_id)}
        self.assertIn(mine, ids)
        self.assertNotIn(theirs, ids)

    def test_scoping_still_finds_legacy_json_rows(self):
        conv = "c_" + uuid.uuid4().hex
        con = self._con()
        con.execute(
            "INSERT INTO sessions(conv_id,title,updated_at,payload_json) VALUES(?,'','',?)",
            (conv, json.dumps({"active_person_id": self.person_id})),
        )
        con.commit()
        con.close()
        ids = {i["conv_id"] for i in _db.list_sessions(limit=50, person_id=self.person_id)}
        self.assertIn(conv, ids)

    def test_unfiltered_list_is_unchanged(self):
        conv = "ws_" + uuid.uuid4().hex
        _db.ensure_session(conv)
        ids = {i["conv_id"] for i in _db.list_sessions(limit=50)}
        self.assertIn(conv, ids)


if __name__ == "__main__":
    unittest.main()
