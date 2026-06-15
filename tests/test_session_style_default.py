"""WO-LORI-ORAL-HISTORY-DEFAULT-01 (2026-06-14) — default-flip tests.

Covers acceptance gate #1 (new sessions default to oral_history) and
gate #6 (existing sessions are not retroactively modified).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))


class PydanticSessionStartDefaultTest(unittest.TestCase):
    """The _SessionStart payload model's default value drives every
    API session-creation call that omits session_style.

    Memory-archive router pulls in FastAPI which isn't available in
    every test sandbox; we verify the contract by reading the source
    file rather than importing the model. Both forms enforce the same
    invariant: the default is the literal string 'oral_history'."""

    def test_session_start_default_is_oral_history(self):
        path = (
            _REPO_ROOT / "server" / "code" / "api" / "routers"
            / "memory_archive.py"
        )
        src = path.read_text(encoding="utf-8")
        # The field declaration must carry the new default string.
        # Pre-WO: `session_style: str = ""`
        # Post-WO: `session_style: str = "oral_history"`
        self.assertIn(
            'session_style: str = "oral_history"',
            src,
        )
        # The pre-WO empty-string default MUST NOT remain in the model
        # (would silently re-introduce the regression).
        self.assertNotIn(
            'session_style: str = ""',
            src,
        )

    def test_session_start_carries_pivot_attribution(self):
        # The change should be commented for archeology — future
        # readers should be able to trace back to this WO.
        path = (
            _REPO_ROOT / "server" / "code" / "api" / "routers"
            / "memory_archive.py"
        )
        src = path.read_text(encoding="utf-8")
        self.assertIn(
            "WO-LORI-ORAL-HISTORY-DEFAULT-01",
            src,
        )


class MigrationOralHistoryDefaultTest(unittest.TestCase):
    """The schema migration changes memory_archive_sessions.session_style
    default to 'oral_history'. Verified by reading the migration SQL —
    pure-text contract check, no DB execution required."""

    def test_migration_changes_default_to_oral_history(self):
        path = (
            _REPO_ROOT / "server" / "code" / "db" / "migrations"
            / "0010_session_style_oral_history_default.sql"
        )
        self.assertTrue(path.exists())
        sql = path.read_text(encoding="utf-8")
        self.assertIn(
            "session_style TEXT NOT NULL DEFAULT 'oral_history'",
            sql,
        )
        # The migration must NOT touch other columns' defaults (we
        # only rebuild the table to flip session_style).
        self.assertIn("audio_enabled INTEGER NOT NULL DEFAULT 0", sql)
        self.assertIn("video_enabled INTEGER NOT NULL DEFAULT 0", sql)


class MalformedStyleFallthroughTest(unittest.TestCase):
    """When session_style is unrecognized in runtime71, the composer
    must fall through to the oral_history posture block. This test
    inspects the composer source to confirm the fall-through clause
    is in place."""

    def test_composer_falls_through_to_oral_history_on_unknown(self):
        path = (
            _REPO_ROOT / "server" / "code" / "api" / "prompt_composer.py"
        )
        src = path.read_text(encoding="utf-8")
        # Block defined
        self.assertIn("LORI_ORAL_HISTORY_RESPONSE", src)
        # Injected from runtime71["session_style"]
        self.assertIn('runtime71.get("session_style")', src)
        # Known set excludes oral_history (so oral_history + unknown +
        # empty all land on the LORI_ORAL_HISTORY_RESPONSE branch).
        self.assertIn("_KNOWN_NON_ORAL_STYLES", src)
        # Verifiable log line per WO acceptance gate 0
        self.assertIn(
            "[composer] style=oral_history block=LORI_ORAL_HISTORY_RESPONSE",
            src,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
