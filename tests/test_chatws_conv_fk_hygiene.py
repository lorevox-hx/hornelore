"""
BUG-CHATWS-CONV-FK-01
======================

Tests for the chat_ws conversation FK hygiene fix in
`db.ensure_interview_session`.

Before the patch, every chat_ws turn triggered:
    [chat_ws][softened] turn_count increment failed conv=...: FOREIGN KEY constraint failed

Root cause: interview_sessions FK's into interview_plans(id) via plan_id.
The default plan_id 'chat_ws' was never seeded by init_db() — only the
'default' plan row existed. INSERT INTO interview_sessions (plan_id='chat_ws')
fired the FK violation every turn.

Fix: lazy-seed the chat_ws plan row in ensure_interview_session before
inserting the session row. Both inserts are idempotent (INSERT OR IGNORE).
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "server"))
sys.path.insert(0, str(REPO_ROOT / "server" / "code"))


class _TmpDbContext:
    """Spin up a private DB for each test so we don't poison the live one."""
    def __init__(self):
        self._tmp = tempfile.mkdtemp(prefix="hornelore_test_")
        self._prev_data_dir = os.environ.get("DATA_DIR")
        self._prev_db_path = os.environ.get("HORNELORE_DB_PATH")
        os.environ["DATA_DIR"] = self._tmp
        os.environ["HORNELORE_DB_PATH"] = str(Path(self._tmp) / "test.sqlite3")

    def __enter__(self):
        # Force re-import so the new env vars take effect on first init_db()
        for mod_name in list(sys.modules.keys()):
            if mod_name.endswith(".db") or mod_name.endswith("api.db"):
                del sys.modules[mod_name]
        return self

    def __exit__(self, *a):
        if self._prev_data_dir is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self._prev_data_dir
        if self._prev_db_path is None:
            os.environ.pop("HORNELORE_DB_PATH", None)
        else:
            os.environ["HORNELORE_DB_PATH"] = self._prev_db_path
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)


class EnsureInterviewSessionFKHygieneTest(unittest.TestCase):
    """The session insert must not fail with FK constraint."""

    def _make_person(self, db, name="Test"):
        """Create a person row so the FK people(id) is satisfied."""
        pid = str(uuid.uuid4())
        return db.create_person(
            display_name=name,
            dob="",
            pob="",
            narrator_type="live",
            pronouns="they_them",
            current_residence="",
        )

    def test_lazy_seeds_chat_ws_plan_row(self):
        """ensure_interview_session must auto-seed its plan_id row."""
        with _TmpDbContext():
            from server.code.api import db
            db.init_db()
            person_id = self._make_person(db)
            session_id = f"chat_ws_test_{uuid.uuid4().hex[:8]}"

            # No exception expected — the lazy plan seed inside
            # ensure_interview_session creates the chat_ws plan row.
            db.ensure_interview_session(session_id, person_id)

            # Verify plan row exists
            con = sqlite3.connect(os.environ["HORNELORE_DB_PATH"])
            row = con.execute(
                "SELECT id FROM interview_plans WHERE id=?;", ("chat_ws",)
            ).fetchone()
            con.close()
            self.assertIsNotNone(row, "chat_ws plan row should have been lazy-seeded")

    def test_idempotent_multiple_calls(self):
        """Calling ensure_interview_session multiple times must not error."""
        with _TmpDbContext():
            from server.code.api import db
            db.init_db()
            person_id = self._make_person(db)
            session_id = f"chat_ws_test_{uuid.uuid4().hex[:8]}"

            for _ in range(5):
                db.ensure_interview_session(session_id, person_id)

            con = sqlite3.connect(os.environ["HORNELORE_DB_PATH"])
            row_count = con.execute(
                "SELECT COUNT(*) FROM interview_sessions WHERE id=?;",
                (session_id,),
            ).fetchone()[0]
            con.close()
            self.assertEqual(row_count, 1, "session insert must be idempotent")

    def test_increment_turn_succeeds_after_ensure(self):
        """The full chat_ws turn-start pattern: ensure → increment must work."""
        with _TmpDbContext():
            from server.code.api import db
            db.init_db()
            person_id = self._make_person(db)
            session_id = f"chat_ws_test_{uuid.uuid4().hex[:8]}"

            db.ensure_interview_session(session_id, person_id)
            count1 = db.increment_session_turn(session_id)
            count2 = db.increment_session_turn(session_id)

            self.assertEqual(count1, 1)
            self.assertEqual(count2, 2)


if __name__ == "__main__":
    unittest.main()
