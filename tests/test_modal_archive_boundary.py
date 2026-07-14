"""BUG-MODAL-TURNS-ARCHIVED-AS-LIFE-STORY-01 — the two-surface rule, enforced.

LOCKED PRODUCT RULE (2026-07-09): there are two Lori surfaces.
  * Narrator Room / Life Map  -> the narrator's LIFE STORY
  * Travel Doc Lori Modal     -> TRIP BUILDING (captures to
                                 trip_location_notes,
                                 source_surface=travel_doc_modal)

LIVE (2026-07-14): chat_ws archived EVERY turn to the narrator's life-story
archive, gated on person_id and never on surface. Travel Doc modal turns
therefore landed in the Narrator Room transcript as things the NARRATOR said —
an operator's workspace question ("can you tell me about this photo?") rendered
as Christopher's own words, repeatedly.

Not cosmetic: peek_at_memoir / compose_memory_echo read archive sessions to
build "what you've shared so far", so operator workspace chatter becomes
narrator memory and Lori recites it back to them as their own life. This test
exists so that never regresses.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CHAT_WS = _REPO_ROOT / "server" / "code" / "api" / "routers" / "chat_ws.py"


class ModalArchiveBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.src = _CHAT_WS.read_text(encoding="utf-8")

    def test_chat_ws_parses(self):
        ast.parse(self.src)          # a NameError here would kill ALL archiving

    def test_user_turn_archive_is_surface_gated(self):
        # The ensure_session/append_event pair for the USER turn must not run
        # for a travel_doc_modal turn.
        i = self.src.index("# Memory Archive — ensure session exists")
        block = self.src[i:i + 2000]
        self.assertIn("_skip_life_story_archive", block)
        self.assertIn('== "travel_doc_modal"', block)
        self.assertIn("if person_id and not _skip_life_story_archive:", block)

    def test_assistant_turn_archive_is_surface_gated(self):
        i = self.src.index("# Memory Archive — log assistant reply")
        block = self.src[i:i + 1200]
        self.assertIn("travel_doc_modal", block)
        self.assertRegex(block, r"if person_id and not _skip_\w+:")

    def test_assistant_gate_does_not_depend_on_a_far_away_binding(self):
        # The user-turn gate is ~3k lines earlier. If an early return path
        # skipped it, inheriting the name would raise NameError and break the
        # archive for EVERY narrator. The assistant site must derive its own.
        i = self.src.index("# Memory Archive — log assistant reply")
        block = self.src[i:i + 1200]
        self.assertIn("_skip_modal_archive = (", block,
                      "assistant-side gate must be recomputed locally, not "
                      "inherited from a binding thousands of lines away")

    def test_the_modal_still_has_its_own_capture_path(self):
        # We removed life-story archiving for the modal — the trip-side capture
        # must still be wired, or modal turns would vanish entirely.
        self.assertIn("capture_modal_turn", self.src)


if __name__ == "__main__":
    unittest.main()
