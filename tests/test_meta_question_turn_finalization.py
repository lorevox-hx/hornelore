"""BUG-DETERMINISTIC-TURN-ARCHIVE-MISSING-01 — the meta_question repair.

THE LIVE EVIDENCE THIS EXISTS FOR
---------------------------------
2026-08-01, Bismarck Trip, narrator a4b2f07a. Chris asked:

    how many pictures can you see from this trip

Lori answered correctly IN THE BROWSER:

    There are three photos attached to Bismarck Trip, two of them
    placed on a day. [...] I don't look at the images themselves.

and the exported transcript (`transcript_switch_msaiq.txt`) jumps from
his question at 15:22:42 straight to his NEXT message at 15:24:25. The
answer is absent.

The deterministic `meta_question` branch -- which the trip
photo-capability answer and the trip-direct answer both take -- called
`persist_turn_transaction` and returned. It never wrote the assistant
archive event, never rebuilt the transcript, and never exposed the
persisted row ids. The USER archive event IS written unconditionally
~1,500 lines earlier, so the export showed the question and no answer,
which reads like an unanswered turn rather than a missing write. That
asymmetry is why it survived so long.

WHY THESE TESTS ARE SHAPED THE WAY THEY ARE
-------------------------------------------
The requirement is "exactly once", and the failure mode a careless fix
produces is TWO -- two archive events, two turn rows, two trip links.
So almost every assertion here is a COUNT, not a presence check. A
presence check passes just as happily on a duplicate.

They read the AST of the real branch rather than driving a WebSocket,
because the properties under test are structural: which calls the branch
makes, how many times, and in what order relative to its own `return`.
A substring scan would fire on the long comment block that explains the
bug, which names every one of these symbols -- that is the guard-writing
trap this repository has hit repeatedly, so the executable body is
unparsed from the AST with docstrings stripped.

Run:
    PYTHONPATH=server/code .venv/bin/python -m unittest \\
        tests.test_meta_question_turn_finalization
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_CHAT_WS = _REPO / "server" / "code" / "api" / "routers" / "chat_ws.py"


def _branch_body(mode: str) -> str:
    """The executable body of `if turn_mode == "<mode>":`, no comments.

    Unparsed from the AST, so the explanatory comment above the code --
    which mentions archive_append_event, _persisted_turn_row_id and the
    rest by name -- cannot satisfy an assertion about the code.
    """
    tree = ast.parse(_CHAT_WS.read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, ast.If):
            t = ast.unparse(n.test)
            if "turn_mode ==" in t and f"'{mode}'" in t.replace('"', "'"):
                return "\n".join(ast.unparse(b) for b in n.body)
    raise AssertionError(f"no `if turn_mode == {mode!r}` branch found")


def _calls(body: str) -> list:
    out = []
    for n in ast.walk(ast.parse(body)):
        if isinstance(n, ast.Call):
            f = n.func
            out.append(f.attr if isinstance(f, ast.Attribute)
                       else getattr(f, "id", ""))
    return out


class MetaQuestionFinalizationTest(unittest.TestCase):
    """The repair, asserted as counts."""

    @classmethod
    def setUpClass(cls):
        cls.body = _branch_body("meta_question")
        cls.calls = _calls(cls.body)

    # -- persist exactly once -----------------------------------------
    def test_the_turn_is_persisted_exactly_once(self):
        """Not 'is persisted' -- ONCE. A second call would write a
        duplicate user AND assistant row for one exchange."""
        self.assertEqual(1, self.calls.count("persist_turn_transaction"))

    def test_the_persisted_row_ids_are_captured_not_discarded(self):
        """The whole defect in one line. The call was already here; its
        return value was thrown away, so every downstream hook that keys
        on the committed row saw nothing."""
        self.assertIn("row_ids_out", self.body)
        self.assertIn("_persisted_turn_row_id", self.body)
        self.assertIn("_persisted_user_turn_row_id", self.body)

    # -- archive exactly once -----------------------------------------
    def test_the_assistant_archive_event_is_written_exactly_once(self):
        self.assertEqual(1, self.calls.count("archive_append_event"))

    def test_the_transcript_is_rebuilt_exactly_once(self):
        """Without this the export keeps the stale file and the answer
        stays missing even though the event landed."""
        self.assertEqual(1, self.calls.count("archive_rebuild_txt"))

    def test_the_USER_archive_event_is_NOT_written_here(self):
        """It is already written unconditionally at chat_ws.py:1888,
        before the dispatcher. Writing it again here is the most likely
        way this repair would produce a duplicate, so it is asserted
        rather than assumed: exactly one append, and its role is
        'assistant'."""
        roles = []
        for n in ast.walk(ast.parse(self.body)):
            # `archive_append_event` is imported by name, so its Call node
            # carries ast.Name -- not ast.Attribute. The first cut of this
            # test read only `.attr` and therefore found ZERO appends and
            # asserted an empty list against ["assistant"]. A walker that
            # matches one call shape and silently ignores the other is the
            # same class of blindness this suite exists to catch.
            _fn = n.func if isinstance(n, ast.Call) else None
            _nm = (getattr(_fn, "attr", None) or getattr(_fn, "id", None)
                   if _fn is not None else None)
            if _nm == "archive_append_event":
                for kw in n.keywords:
                    if kw.arg == "role":
                        roles.append(ast.literal_eval(kw.value))
        self.assertEqual(["assistant"], roles)

    # -- ordering is the safety property ------------------------------
    def test_the_archive_flag_is_set_after_the_append_not_before(self):
        """`_archive_event_persisted` gates completed-turn extraction.
        Setting it before the append would let extraction run against a
        turn whose archive write then raised -- the exact fail-open the
        main path's comment warns about."""
        i_append = self.body.index("archive_append_event")
        i_flag = self.body.index("_archive_event_persisted")
        self.assertLess(i_append, i_flag)

    def test_the_archive_flag_is_inside_the_try_block(self):
        """Outside it, a raising archive write would still mark the
        archive as persisted."""
        tree = ast.parse(self.body)
        inside = False
        for n in ast.walk(tree):
            if isinstance(n, ast.Try):
                if "_archive_event_persisted" in "\n".join(
                        ast.unparse(b) for b in n.body):
                    inside = True
        self.assertTrue(inside,
                        "_archive_event_persisted is set outside a try")

    def test_the_answer_is_sent_after_the_writes(self):
        """The narrator's answer must not be delivered by a turn that
        then fails to record itself."""
        i_persist = self.body.index("persist_turn_transaction")
        i_send = self.body.index("_ws_send")
        self.assertLess(i_persist, i_send)

    # -- the browser contract is unchanged ----------------------------
    def test_the_browser_frames_are_unchanged(self):
        """The repair is bookkeeping. What the narrator sees must be
        byte-identical: one token frame, one done frame, same fields."""
        self.assertEqual(2, self.calls.count("_ws_send"))
        for needle in ("'type': 'token'", "'delta': assistant_text",
                       "'type': 'done'", "'final_text': assistant_text",
                       "'turn_mode': 'meta_question'",
                       "meta_question_category"):
            self.assertIn(needle, self.body, needle)

    def test_the_modal_surface_is_still_excluded_from_life_story(self):
        """BUG-MODAL-TURNS-ARCHIVED-AS-LIFE-STORY-01. A Travel Doc modal
        reply must not enter the narrator's life story, and the gate is
        RECOMPUTED here rather than inherited -- the user-turn gate is
        ~1,500 lines up and an early return could leave it unbound."""
        self.assertIn("travel_doc_modal", self.body)
        self.assertIn("surface", self.body)

    # -- what must NOT have been added --------------------------------
    def test_the_branch_does_not_call_the_downstream_hooks_itself(self):
        """The trip link and extraction hooks run in the OUTER body after
        this function returns, reading the two params flags. Calling them
        here as well is how this repair would create a SECOND trip link
        for one conversation."""
        for banned in ("_run_completed_turn_trip_link",
                       "_run_completed_turn_extraction",
                       "schedule_completed_turn_extraction",
                       "record_completed_turn"):
            self.assertNotIn(banned, self.calls, banned)

    def test_no_family_truth_or_projection_write_was_added(self):
        for banned in ("ft_add_note", "ft_add_row", "apply_correction",
                       "story_candidate_insert", "preserve_turn"):
            self.assertNotIn(banned, self.calls, banned)


class ExtractionRemainsIneligibleTest(unittest.TestCase):
    """Chris's explicit requirement: PROVE meta_question is refused,
    do not assume it.

    Exposing `_persisted_turn_row_id` is what makes the trip link
    possible -- and the extraction hook keys on the same flag. So the
    repair could have quietly started extracting deterministic answers.
    It does not, and the reason is the eligibility set, which is checked
    here against the real module rather than recited.
    """

    def test_only_interview_turns_are_extraction_eligible(self):
        import sys
        p = str(_REPO / "server" / "code")
        if p not in sys.path:
            sys.path.insert(0, p)
        from api.services.turn_extraction import (
            extraction_eligible, EXTRACTION_ELIGIBLE_TURN_MODES)

        self.assertTrue(extraction_eligible("interview"))
        for mode in ("meta_question", "witness", "memory_echo",
                     "age_recall", "correction", "floor_hold"):
            with self.subTest(mode=mode):
                self.assertFalse(
                    extraction_eligible(mode),
                    f"{mode} became extraction-eligible; a deterministic "
                    "answer would be mined as if the narrator had said it")
        self.assertEqual(frozenset({"interview"}),
                         EXTRACTION_ELIGIBLE_TURN_MODES)

    def test_the_extraction_hook_gates_on_turn_mode_first(self):
        """Cheapest gate first, before the ledger is touched at all --
        so a meta_question turn cannot even take a claim."""
        # Read the hook's REAL body from the AST rather than slicing a
        # fixed number of characters. Two earlier cuts of this test got
        # this wrong in two different ways: one matched the IMPORT of
        # _schedule_extraction (six lines above the gate) instead of its
        # call, and one used a 3000-character window when the call sits
        # at offset 5527. A window is a guess about size; the AST is the
        # structure itself.
        tree = ast.parse(_CHAT_WS.read_text(encoding="utf-8"))
        hook = None
        for n in ast.walk(tree):
            if (isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
                    and n.name == "_run_completed_turn_extraction"):
                hook = n
        self.assertIsNotNone(hook, "extraction hook not found")

        body = "\n".join(ast.unparse(b) for b in hook.body)
        i_eligible = body.index("_eligible(turn_mode)")
        i_call = body.index("_schedule_extraction(")
        self.assertLess(
            i_eligible, i_call,
            "extraction is scheduled before turn_mode is checked")


class TheOtherFiveAreDeliberatelyUntouchedTest(unittest.TestCase):
    """Scope, pinned.

    Chris: "Do not refactor the other five deterministic branches during
    WO1E." They have the identical gap and it is recorded as
    WO-DETERMINISTIC-TURN-FINALIZATION-01. This test does NOT assert
    they stay broken forever -- it asserts that THIS commit did not
    quietly widen, so the next reader can tell a scoped repair from a
    silent refactor.

    When the follow-up work order lands, this test is expected to fail
    and should be retired with its reason quoted, not deleted.
    """

    def test_the_other_five_still_lack_the_finalisation(self):
        for mode in ("floor_hold", "witness", "memory_echo",
                     "age_recall", "correction"):
            with self.subTest(mode=mode):
                body = _branch_body(mode)
                calls = _calls(body)
                self.assertEqual(
                    0, calls.count("archive_append_event"),
                    f"{mode} gained the archive write -- if that is "
                    "WO-DETERMINISTIC-TURN-FINALIZATION-01 landing, "
                    "retire this test with the date and reason")


if __name__ == "__main__":
    unittest.main(verbosity=2)
