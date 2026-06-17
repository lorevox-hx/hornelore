from __future__ import annotations

import re
import unittest
from pathlib import Path

from tests.boris_quality._helpers import get_source


class ChatWsForeignKeyLifecycleTests(unittest.TestCase):
    """Phase 4 — chat_ws FK hygiene tests.

    These are source-level contract tests because the full WS path loads the
    model and is too heavy for unit tests. They lock the lifecycle invariant:
    a session row must exist before turn_count increment, softened-state write,
    or safety segment persistence.
    """

    def test_chat_ws_imports_lifecycle_primitives(self):
        source = get_source("server.code.api.routers.chat_ws")
        self.assertIn("ensure_interview_session", source)
        self.assertIn("increment_session_turn", source)
        self.assertIn("save_segment_flag", source)

    def test_generate_path_attempts_ensure_before_increment(self):
        source = get_source("server.code.api.routers.chat_ws")
        ensure_positions = [m.start() for m in re.finditer(r"\bensure_interview_session\s*\(", source)]
        increment_positions = [m.start() for m in re.finditer(r"\bincrement_session_turn\s*\(", source)]

        self.assertTrue(ensure_positions, "chat_ws must call ensure_interview_session() before turn writes.")
        self.assertTrue(increment_positions, "chat_ws must call increment_session_turn().")
        self.assertLess(
            min(ensure_positions),
            min(increment_positions),
            "ensure_interview_session() must occur before the first increment_session_turn() call "
            "so synthetic harness conv_ids do not FK-fail."
        )

    def test_fk_failure_log_is_not_the_normal_path(self):
        source = get_source("server.code.api.routers.chat_ws")
        self.assertNotIn(
            "FOREIGN KEY constraint failed",
            source,
            "Do not hard-code or normalize FK failure as an expected path. Fix lifecycle instead.",
        )

    def test_softened_write_is_not_allowed_to_hide_persistent_fk_failure(self):
        source = get_source("server.code.api.routers.chat_ws")
        self.assertIn("[chat_ws][softened]", source)
        self.assertRegex(
            source,
            r"ensure_interview_session",
            "Before softened mode can persist safely, chat_ws must ensure/create the session row.",
        )


if __name__ == "__main__":
    unittest.main()
