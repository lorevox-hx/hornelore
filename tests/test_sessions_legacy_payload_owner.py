"""WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 Phase 2, Part C.

Migration 0044 recovered session ownership from three RECORDED LINKS and
deliberately did not read `payload_json`, because at the time that column
was measured as '{}' on 56 of 56 recent rows. 0045 finishes the job for
the rows where it is NOT empty: one structured, unambiguous, existing
narrator id becomes the recorded owner, and everything else stays NULL.

These tests run THE SHIPPED MIGRATION TEXT, not a copy of its logic. The
`ALTER TABLE` line is stripped before re-execution (the column already
exists on a migrated database) and nothing else is touched, so a test
passing here is a statement about the file that will actually run.

The rules under test, each of which can only be got wrong in one
direction -- towards inventing ownership:

  * one valid payload owner is backfilled;
  * both payload fields agreeing is accepted;
  * disagreeing fields stay NULL;
  * a nonexistent person stays NULL;
  * a conflicting stronger source stays NULL;
  * an ambiguous stronger source stays NULL;
  * an existing explicit owner is NEVER changed;
  * re-running changes nothing;
  * residue accounting adds up.

pytest is not installed in this repo. Run with:

    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_sessions_legacy_payload_owner
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
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from api import db as _db  # noqa: E402

_MIGRATION = (
    _SERVER_CODE / "db" / "migrations" / "0045_sessions_legacy_payload_owner.sql"
)


class _Base(unittest.TestCase):
    def setUp(self):
        fd = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        fd.close()
        self.db_path = Path(fd.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        # init_db applies every migration, so the schema under test is the
        # real one and 0045 has already run once against an empty table.
        _db.init_db()

        self.alice = str(uuid.uuid4())
        self.bob = str(uuid.uuid4())
        con = self._con()
        for pid, name in ((self.alice, "Alice Example"), (self.bob, "Bob Example")):
            con.execute(
                "INSERT INTO people (id, display_name, created_at, updated_at) "
                "VALUES (?,?,?,?)",
                (pid, name, "2026-08-17", "2026-08-17"),
            )
        con.commit()
        con.close()

    def tearDown(self):
        _db.DB_PATH = self._orig_db
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def _con(self):
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        return con

    def _session(self, conv_id, payload, person_id=None, source=None):
        con = self._con()
        con.execute(
            "INSERT INTO sessions(conv_id,title,updated_at,payload_json,"
            "person_id,person_id_source) VALUES(?,?,?,?,?,?)",
            (conv_id, "", "2026-08-17T00:00:00Z",
             payload if isinstance(payload, str) else json.dumps(payload),
             person_id, source),
        )
        con.commit()
        con.close()

    def _turn(self, conv_id, person_id):
        con = self._con()
        con.execute(
            "INSERT INTO turns(conv_id, role, content, ts, meta_json) "
            "VALUES(?,?,?,?,?)",
            (conv_id, "user", "hello", "2026-08-17T00:00:00Z",
             json.dumps({"person_id": person_id})),
        )
        con.commit()
        con.close()

    def _run_migration(self):
        """Execute the SHIPPED 0045 body against the already-migrated DB."""
        sql = _MIGRATION.read_text(encoding="utf-8")
        stripped = "\n".join(
            line for line in sql.splitlines()
            if "ALTER TABLE sessions ADD COLUMN person_id_source" not in line
        )
        con = sqlite3.connect(str(self.db_path))
        con.executescript(stripped)
        con.commit()
        con.close()

    def _owner(self, conv_id):
        con = self._con()
        row = con.execute(
            "SELECT person_id, person_id_source FROM sessions WHERE conv_id=?;",
            (conv_id,),
        ).fetchone()
        con.close()
        return (row["person_id"], row["person_id_source"])


class BackfillAccepts(_Base):
    def test_one_valid_payload_owner_is_backfilled(self):
        self._session("s1", {"person_id": self.alice})
        self._run_migration()
        self.assertEqual(self._owner("s1"), (self.alice, "legacy_payload_json"))

    def test_the_other_historical_key_is_read_too(self):
        # app.js wrote `person_id` while the only reader looked for
        # `active_person_id`. Both are honoured or the mismatch keeps
        # costing attribution.
        self._session("s2", {"active_person_id": self.bob})
        self._run_migration()
        self.assertEqual(self._owner("s2"), (self.bob, "legacy_payload_json"))

    def test_both_fields_agreeing_is_accepted(self):
        self._session("s3", {"person_id": self.alice, "active_person_id": self.alice})
        self._run_migration()
        self.assertEqual(self._owner("s3"), (self.alice, "legacy_payload_json"))

    def test_a_stronger_source_that_agrees_does_not_block(self):
        self._session("s4", {"person_id": self.alice})
        self._turn("s4", self.alice)
        self._run_migration()
        self.assertEqual(self._owner("s4")[0], self.alice)


class BackfillDeclines(_Base):
    def test_disagreeing_fields_stay_null(self):
        # Two structured fields contradicting each other is INFORMATION.
        # Picking one would be a silent resolution of it.
        self._session("d1", {"person_id": self.alice, "active_person_id": self.bob})
        self._run_migration()
        self.assertEqual(self._owner("d1"), (None, None))

    def test_a_nonexistent_person_stays_null(self):
        self._session("d2", {"person_id": "not-a-real-narrator"})
        self._run_migration()
        self.assertEqual(self._owner("d2"), (None, None))

    def test_a_conflicting_stronger_source_stays_null(self):
        self._session("d3", {"person_id": self.alice})
        self._turn("d3", self.bob)
        self._run_migration()
        self.assertEqual(self._owner("d3"), (None, None))

    def test_an_ambiguous_stronger_source_stays_null(self):
        self._session("d4", {"person_id": self.alice})
        self._turn("d4", self.alice)
        self._turn("d4", self.bob)
        self._run_migration()
        self.assertEqual(self._owner("d4"), (None, None))

    def test_an_empty_payload_stays_null(self):
        self._session("d5", {})
        self._run_migration()
        self.assertEqual(self._owner("d5"), (None, None))

    def test_invalid_json_stays_null_and_does_not_raise(self):
        # json_extract on malformed JSON is a SQLite error, not a NULL.
        # The migration must not fall over on one bad historical row.
        self._session("d6", "this is not json")
        self._run_migration()
        self.assertEqual(self._owner("d6"), (None, None))

    def test_a_blank_id_stays_null(self):
        self._session("d7", {"person_id": "   "})
        self._run_migration()
        self.assertEqual(self._owner("d7"), (None, None))


class ExistingOwnershipIsUntouchable(_Base):
    def test_an_existing_explicit_owner_is_never_changed(self):
        self._session("x1", {"person_id": self.bob}, person_id=self.alice,
                      source="explicit")
        self._run_migration()
        self.assertEqual(self._owner("x1"), (self.alice, "explicit"))

    def test_an_owner_recorded_without_provenance_is_not_retro_stamped(self):
        # 0044's recoveries and pre-Phase-2 writes carry no source. Deciding
        # after the fact which one they were is the reconstruction this
        # lane forbids, so they stay NULL and are reported as unrecorded.
        self._session("x2", {"person_id": self.alice}, person_id=self.alice)
        self._run_migration()
        self.assertEqual(self._owner("x2"), (self.alice, None))

    def test_payload_json_is_never_rewritten(self):
        original = json.dumps({"person_id": self.alice, "extra": "keep me"})
        self._session("x3", original)
        self._run_migration()
        con = self._con()
        row = con.execute(
            "SELECT payload_json FROM sessions WHERE conv_id='x3';"
        ).fetchone()
        con.close()
        self.assertEqual(row["payload_json"], original)


class Idempotency(_Base):
    def test_rerunning_the_migration_changes_nothing(self):
        self._session("i1", {"person_id": self.alice})
        self._session("i2", {"person_id": self.alice, "active_person_id": self.bob})
        self._session("i3", {"person_id": "ghost"})
        self._run_migration()

        def snapshot():
            con = self._con()
            rows = con.execute(
                "SELECT conv_id, person_id, person_id_source, payload_json "
                "FROM sessions ORDER BY conv_id;"
            ).fetchall()
            con.close()
            return [tuple(r) for r in rows]

        before = snapshot()
        self._run_migration()
        self._run_migration()
        self.assertEqual(before, snapshot())


class WritePathRecordsProvenance(_Base):
    def test_ensure_session_stamps_explicit(self):
        _db.ensure_session("w1", title="t", person_id=self.alice)
        self.assertEqual(self._owner("w1"), (self.alice, "explicit"))

    def test_ensure_session_without_a_narrator_records_nothing(self):
        _db.ensure_session("w2", title="t")
        self.assertEqual(self._owner("w2"), (None, None))

    def test_a_later_ownerless_write_does_not_clear_the_owner_or_its_source(self):
        _db.ensure_session("w3", title="t", person_id=self.alice)
        _db.ensure_session("w3", title="t2")
        self.assertEqual(self._owner("w3"), (self.alice, "explicit"))

    def test_upsert_session_stamps_explicit_from_the_payload(self):
        _db.upsert_session("w4", "t", {"active_person_id": self.bob})
        self.assertEqual(self._owner("w4"), (self.bob, "explicit"))


class ResidueAccounting(_Base):
    def test_the_unowned_buckets_sum_to_the_unowned_total(self):
        self._session("r1", {"person_id": self.alice, "active_person_id": self.bob})
        self._session("r2", {"person_id": "ghost"})
        self._session("r3", {})
        self._session("r4", "not json")
        self._session("r5", {"person_id": self.alice})
        self._turn("r5", self.alice)
        self._turn("r5", self.bob)
        res = _db.session_ownership_residue()
        buckets = sum(
            res["unowned_" + name] for name in _db._RESIDUE_UNOWNED_BUCKETS
        )
        self.assertEqual(buckets, res["sessions_unowned"])

    def test_each_declined_row_lands_in_the_bucket_that_explains_it(self):
        self._session("b1", {"person_id": self.alice, "active_person_id": self.bob})
        self._session("b2", {"person_id": "ghost"})
        self._session("b3", {})
        self._session("b4", {"person_id": self.alice})
        self._turn("b4", self.bob)
        res = _db.session_ownership_residue()
        self.assertEqual(res["unowned_legacy_fields_disagree"], 1)
        self.assertEqual(res["unowned_legacy_id_invalid"], 1)
        self.assertEqual(res["unowned_stronger_source_ambiguous_or_conflicting"], 1)
        self.assertEqual(res["unowned_no_recorded_link"], 1)

    def test_owner_provenance_is_split_three_ways(self):
        self._session("p1", {"person_id": self.alice})           # -> recovered
        self._session("p2", {}, person_id=self.bob, source="explicit")
        self._session("p3", {}, person_id=self.alice)            # -> unrecorded
        self._run_migration()
        res = _db.session_ownership_residue()
        self.assertEqual(res["owner_recovered_legacy_payload"], 1)
        self.assertEqual(res["owner_explicit"], 1)
        self.assertEqual(res["owner_source_unrecorded"], 1)
        self.assertEqual(res["sessions_owned"], 3)

    def test_a_read_only_report_writes_nothing(self):
        self._session("q1", {"person_id": self.alice})
        before = self.db_path.read_bytes()
        _db.session_ownership_residue()
        _db.count_sessions_without_owner()
        self.assertEqual(before, self.db_path.read_bytes())


def _sql_without_comments(text: str) -> str:
    """Executable SQL only.

    This helper exists because the first cut of the test below did NOT
    have it, and failed immediately -- on the migration's own header,
    which explains in prose that ownership is *not* inferred from "a
    display name, not a title, not a timestamp". A guard written against
    a WORD fires on the documentation quoting that word, which is a bug
    this repository has now hit five times in five different lanes. The
    guard has to match what SQLite executes.
    """
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        if "--" in line:
            line = line.split("--", 1)[0]
        out.append(line)
    return "\n".join(out)


class MigrationTextRules(unittest.TestCase):
    """The file itself, because some rules are about what it must not do."""

    def setUp(self):
        self.sql = _MIGRATION.read_text(encoding="utf-8")
        self.body = _sql_without_comments(self.sql)

    def test_it_reads_only_the_two_structured_fields(self):
        self.assertIn("'$.person_id'", self.body)
        self.assertIn("'$.active_person_id'", self.body)
        # Every one of these is a way ownership could be GUESSED rather
        # than read: a name, a title, a fuzzy match, a timestamp ordering.
        for forbidden in ("display_name", "title", "LIKE", "ORDER BY updated_at"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.body)

    def test_the_comment_stripper_is_not_vacuous(self):
        # A stripper that returned "" would make every assertion above
        # pass. Positive control: the executable body still contains the
        # statements the migration is made of.
        self.assertIn("UPDATE sessions", self.body)
        self.assertIn("CREATE TEMP VIEW", self.body)
        # ...and the prose it dropped really did contain a banned word.
        # `title` is the one that actually fired when this guard was
        # first written without the stripper, in the header sentence
        # listing what ownership is NOT inferred from.
        self.assertIn("not a display name", self.sql)
        self.assertNotIn("not a display name", self.body)
        self.assertIn("title", self.sql)

    def test_it_never_writes_payload_json(self):
        self.assertNotIn("SET payload_json", self.body)

    def test_it_does_not_drop_or_rebuild_anything(self):
        for forbidden in ("DROP TABLE", "DELETE FROM", "ALTER TABLE sessions RENAME"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.body)

    def test_0044_is_not_edited(self):
        older = (_SERVER_CODE / "db" / "migrations" / "0044_sessions_person_id.sql")
        self.assertIn("ALTER TABLE sessions ADD COLUMN person_id TEXT;",
                      older.read_text(encoding="utf-8"))
        self.assertNotIn("person_id_source", older.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
