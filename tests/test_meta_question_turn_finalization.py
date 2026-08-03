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

THE CORRECTION, 2026-08-03
--------------------------
The first cut of the repair did more than write the transcript: it
captured the persisted row ids into `params` and set
`_archive_event_persisted`. That was believed safe because the two
completed-turn hooks also gate on turn mode, and both eligibility sets
are frozenset({"interview"}).

They do gate on it -- and they read it from `params`, which never
receives the resolved mode. The dispatcher assigns "meta_question" to a
LOCAL variable; the only writes to params["turn_mode"] in chat_ws.py are
:5480 (whatever the browser sent, "interview" for an ordinary turn) and
:1247 / :2909, which both force "interview". A deterministic `return`
does not skip the hooks either -- it is a normal return from
`_generate_and_stream_body`, which is awaited at :481 with both hooks on
the two lines after it.

So both mode gates passed, and the ABSENCE of those flags was the only
thing holding the hooks out. Setting them fired an extraction generation
and a trip conversation link against Lori's own deterministic capability
answer. The flags are removed; the transcript writes stay.

The tests that asserted the flags were present are INVERTED rather than
deleted, with their retired assertions quoted. `EffectiveTurnModeSeamTest`
is new and asserts the seam as a chain, because the reason this was
missed is that a single test asserted the eligibility frozensets -- which
are correct, and which nothing on this path ever asks.

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

    def test_no_hook_plumbing_is_exposed_through_params(self):
        """INVERTED 2026-08-03. This test used to assert the opposite:

            def test_the_persisted_row_ids_are_captured_not_discarded:
                assertIn("row_ids_out", body)
                assertIn("_persisted_turn_row_id", body)
                assertIn("_persisted_user_turn_row_id", body)

        and a sibling asserted `_archive_event_persisted` was set after
        the append and inside the try. Those three flags are what the two
        completed-turn hooks read, and exposing them was believed safe
        because both hooks ALSO gate on turn mode and both eligibility
        sets are frozenset({"interview"}).

        They do -- and they read the mode from `params`, which never
        receives it. The dispatcher resolves the deterministic mode into
        a local variable; the only writes to params["turn_mode"] in
        chat_ws.py are :5480 (whatever the browser sent) and :1247/:2909
        (both forcing "interview"). So on a server-resolved meta_question
        turn both mode gates pass, and the ABSENCE of these flags was the
        only thing holding the hooks out. Setting them fired an
        extraction generation and a trip conversation link against Lori's
        own deterministic capability answer.

        The transcript repair never needed them. Removing the flags is
        the fix; repairing the mode handoff is separate work with five
        other branches on the same seam.
        """
        for banned in ("row_ids_out",
                       "_persisted_turn_row_id",
                       "_persisted_user_turn_row_id",
                       "_archive_event_persisted"):
            self.assertNotIn(
                banned, self.body,
                f"{banned} is set on the meta_question path again. It "
                "opens a completed-turn hook whose mode gate does not "
                "hold here -- see this test's docstring before "
                "reinstating it.")

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
    #
    # RETIRED 2026-08-03: test_the_archive_flag_is_set_after_the_append
    # _not_before and test_the_archive_flag_is_inside_the_try_block. Both
    # asserted the placement of `params["_archive_event_persisted"]`,
    # which is no longer set on this path at all. Their reasoning was
    # sound for a flag that SHOULD be set -- set it before the append and
    # a raising archive write leaves extraction running against an
    # incomplete archive -- and that reasoning still applies to the main
    # LLM path, where the flag lives and where its own tests cover it. It
    # stopped applying here when the flag was removed. The absence is now
    # asserted directly by
    # test_no_hook_plumbing_is_exposed_through_params.

    def test_the_archive_write_is_inside_a_try(self):
        """A failing archive write must not take the turn down with it.
        The narrator has already been answered by the time this runs."""
        tree = ast.parse(self.body)
        guarded = False
        for n in ast.walk(tree):
            if isinstance(n, ast.Try):
                if "archive_append_event" in "\n".join(
                        ast.unparse(b) for b in n.body):
                    guarded = True
        self.assertTrue(guarded,
                        "archive_append_event is called outside a try")

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
    """The eligibility SETS are correct. That is all this class proves.

    CORRECTED 2026-08-03. This docstring used to read:

        "Exposing `_persisted_turn_row_id` is what makes the trip link
         possible -- and the extraction hook keys on the same flag. So
         the repair could have quietly started extracting deterministic
         answers. It does not, and the reason is the eligibility set,
         which is checked here against the real module rather than
         recited."

    The last sentence was false. The repair DID start extracting
    deterministic answers, and the eligibility set was not the reason it
    would have been stopped, because the set is never asked about
    "meta_question" -- the hook asks about params["turn_mode"], which
    still says "interview". Checking a set against the real module
    instead of reciting it is better than reciting it and still proves
    nothing about the value that reaches it.

    This class is kept because the sets ARE a real invariant worth
    pinning. What it does not prove is covered by
    EffectiveTurnModeSeamTest below.
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
        """Cheapest gate first, before the ledger is touched at all.

        CORRECTED 2026-08-03. This docstring ended "-- so a meta_question
        turn cannot even take a claim." That conclusion does not follow
        from what the test measures. The ordering is real and worth
        pinning; what it protects against is a turn whose params ALREADY
        carry a non-interview mode. A server-resolved meta_question turn
        does not, so the gate passes and the turn can take a claim. See
        EffectiveTurnModeSeamTest.
        """
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


def _func_body(name: str) -> str:
    """The executable body of a top-level-or-nested def, no comments."""
    tree = ast.parse(_CHAT_WS.read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if (isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
                and n.name == name):
            return "\n".join(ast.unparse(b) for b in n.body)
    raise AssertionError(f"no function named {name!r} found")


class EffectiveTurnModeSeamTest(unittest.TestCase):
    """The seam the first repair walked into, asserted as a chain.

    Chris's required shape, 2026-08-03:

        incoming mode: interview
        server resolves: meta_question / memory_echo / witness / ...
        hook receives: <what params actually carries>
        result: zero trip links and zero extraction claims

    Each link is asserted separately, because the failure that produced
    this class was believing a conclusion that skipped one. A test that
    only asserted the eligibility frozensets passed happily while the
    live system created an extraction claim and a trip link for a
    deterministic answer.

    This is not a driven WebSocket. Driving one would need fastapi, a
    database, an archive and a fake socket, and would prove the same
    four facts less legibly and more fragilely. What it would add is
    coverage of the wiring BETWEEN these facts -- and that wiring is
    exactly what the AST assertions below read. When the effective-mode
    handoff is repaired, links 1-3 are expected to fail; retire them
    with the date and reason rather than deleting them, and only then
    reconsider link 4.
    """

    # -- link 1: the resolved mode is never written back --------------
    def test_the_dispatcher_never_writes_a_deterministic_mode_to_params(self):
        """Every assignment to params["turn_mode"] in the whole file.

        There are three, and all three assign "interview" -- one from
        the incoming browser message, two forcing it on safety paths.
        The dispatcher's own `turn_mode = "meta_question"` and friends
        are assignments to a LOCAL name and do not appear here.
        """
        tree = ast.parse(_CHAT_WS.read_text(encoding="utf-8"))
        assigned: list = []
        for n in ast.walk(tree):
            if not isinstance(n, ast.Assign):
                continue
            for tgt in n.targets:
                if (isinstance(tgt, ast.Subscript)
                        and isinstance(tgt.value, ast.Name)
                        and tgt.value.id == "params"):
                    key = ast.unparse(tgt.slice).strip("'\"")
                    if key == "turn_mode":
                        assigned.append(ast.unparse(n.value))

        self.assertTrue(assigned, "no params['turn_mode'] write found at "
                                  "all -- has the key been renamed?")
        for value in assigned:
            with self.subTest(value=value):
                self.assertIn(
                    "interview", value,
                    "a params['turn_mode'] write assigns something other "
                    "than 'interview'. If the dispatcher now writes the "
                    "resolved deterministic mode back, this seam is "
                    "FIXED -- retire links 1-3 of this class with the "
                    "date and reason, and revisit whether the "
                    "meta_question branch may expose hook plumbing "
                    "again.")

    # -- link 2: so the hooks read "interview" ------------------------
    def test_both_hooks_read_the_mode_from_params_not_from_the_local(self):
        """If they read the dispatcher's local, link 1 would not matter.
        They do not -- they run in the outer body, after the dispatcher
        function has returned, and `params` is the only thing that
        survives that boundary."""
        for hook in ("_run_completed_turn_extraction",
                     "_run_completed_turn_trip_link"):
            with self.subTest(hook=hook):
                body = _func_body(hook)
                self.assertIn("params.get('turn_mode')", body,
                              f"{hook} no longer reads turn_mode from "
                              "params -- re-derive this whole chain")

    def test_a_deterministic_branch_return_does_not_skip_the_hooks(self):
        """The dispatcher's `return` is a normal return from
        _generate_and_stream_body, and the hooks are awaited on the line
        after it. Nothing about returning early avoids them."""
        wrapper = None
        tree = ast.parse(_CHAT_WS.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)):
                src = "\n".join(ast.unparse(b) for b in n.body)
                if ("_generate_and_stream_body(" in src
                        and "_run_completed_turn_extraction(" in src):
                    wrapper = src
        self.assertIsNotNone(
            wrapper, "no caller awaits the body and then the hooks")
        i_body = wrapper.index("_generate_and_stream_body(")
        i_ext = wrapper.index("_run_completed_turn_extraction(")
        i_link = wrapper.index("_run_completed_turn_trip_link(")
        self.assertLess(i_body, i_ext)
        self.assertLess(i_ext, i_link)

    # -- link 3: therefore both mode gates PASS -----------------------
    def test_the_mode_gates_do_not_protect_a_resolved_deterministic_turn(self):
        """The uncomfortable one, and the reason this class exists.

        Both eligibility sets are frozenset({"interview"}) and both are
        correct. Asked about the value that actually arrives, both say
        yes. The set was never the protection on this path.
        """
        import sys
        p = str(_REPO / "server" / "code")
        if p not in sys.path:
            sys.path.insert(0, p)
        from api.services.turn_extraction import extraction_eligible
        from api.services.trip_placement import placement_eligible

        # what the browser sent, and what params still carries after the
        # server has decided the turn is a meta_question
        as_received = "interview"
        self.assertTrue(extraction_eligible(as_received))
        self.assertTrue(placement_eligible(as_received))

    # -- link 4: so the flags are the only protection, and are absent --
    def test_each_hook_requires_a_flag_the_branch_must_not_set(self):
        """Read from each hook's real body: the precondition that stops
        it, given that its mode gate has already passed."""
        ext = _func_body("_run_completed_turn_extraction")
        self.assertIn("_archive_event_persisted", ext)

        link = _func_body("_run_completed_turn_trip_link")
        self.assertIn("_persisted_turn_row_id", link)

    def test_the_meta_question_branch_sets_neither_flag(self):
        """The close of the chain. Duplicated deliberately from
        MetaQuestionFinalizationTest: there it reads as tidiness, here it
        is the single fact standing between a deterministic answer and an
        extraction generation."""
        body = _branch_body("meta_question")
        self.assertNotIn("_archive_event_persisted", body)
        self.assertNotIn("_persisted_turn_row_id", body)
        self.assertNotIn("_persisted_user_turn_row_id", body)
        self.assertNotIn("row_ids_out", body)

    def test_the_transcript_repair_itself_survived_the_removal(self):
        """Removing the flags must not have removed the thing the repair
        was for. One archive append, one rebuild, one persist."""
        calls = _calls(_branch_body("meta_question"))
        self.assertEqual(1, calls.count("archive_append_event"))
        self.assertEqual(1, calls.count("archive_rebuild_txt"))
        self.assertEqual(1, calls.count("persist_turn_transaction"))


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
