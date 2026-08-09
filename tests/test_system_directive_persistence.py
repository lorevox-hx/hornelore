"""WO-SYSTEM-DIRECTIVE-PERSISTENCE-01 Phase 1 — authorship at the boundary.

Internal guidance the browser composes for Lori (`[SYSTEM: ...]`,
`[SYSTEM_QF: ...]`) travels in the user message slot, because in-band
guidance is how Lori is steered. It was then written to `turns` with
`role='user'`, so eighteen modules grew a defensive check on the text
prefix to undo it.

Measured read-only on the live database the day Phase 1 landed:
**120 of 794 user rows (15.1%) are directives, across 39 of 335
conversations**, the worst carrying ten apiece.

Option A, ruled by Chris 2026-08-09: record the classification in the
user row's `meta_json`; keep `role='user'` so the directive still
replays to the model.

WHAT THIS FILE HAS TO PROVE, in order of how badly it would hurt to be
wrong:

  1. a genuine narrator turn is byte-identical across EVERY column;
  2. what the model replays is byte-identical;
  3. the boundary does not re-sniff the text;
  4. a directive is recorded as one.

(1) and (2) come first because this work order is only worth doing if it
is invisible to the narrator and to Lori.
"""

from __future__ import annotations

import importlib
import inspect
import re
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from source_scan_helpers import strip_py_comments


def _fresh_db_module():
    """A real sqlite database in a temp dir, never the live one."""
    tmp = tempfile.mkdtemp(prefix="sysdir-")
    os.environ["DATA_DIR"] = tmp
    import api.db as db  # noqa: E402  (PYTHONPATH=server/code, per CLAUDE.md)
    importlib.reload(db)
    db.init_db()
    return db, tmp


class _Base(unittest.TestCase):
    def setUp(self):
        self.db, self.tmp = _fresh_db_module()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def rows(self, conv_id):
        con = sqlite3.connect(str(self.db.DB_PATH))
        con.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in con.execute(
                "SELECT * FROM turns WHERE conv_id=? ORDER BY id", (conv_id,))]
        finally:
            con.close()

    def user_row(self, conv_id):
        return [r for r in self.rows(conv_id) if r["role"] == "user"][0]


class NarratorTurnsAreUntouchedTest(_Base):
    """The property the whole work order is judged on."""

    NARRATOR = "My mother kept the ration book in the kitchen drawer."

    def test_default_call_writes_the_identical_bytes_it_always_did(self):
        self.db.persist_turn_transaction(
            conv_id="c1", user_message=self.NARRATOR,
            assistant_message="Tell me about that drawer.", model_name="m")
        # `"{}"` is what the hardcoded literal wrote before Phase 1. Not
        # `== {}` after parsing -- the stored BYTES have to match, or a
        # future differ or hash over this column reports a change that
        # never happened.
        self.assertEqual("{}", self.user_row("c1")["meta_json"])

    def test_a_narrator_row_is_identical_across_every_column(self):
        # Compare whole rows, not the field under test. A partial write
        # must not be able to hide in a column nobody thought to check.
        self.db.persist_turn_transaction(
            conv_id="a", user_message=self.NARRATOR,
            assistant_message="ok", model_name="m")
        self.db.persist_turn_transaction(
            conv_id="b", user_message=self.NARRATOR,
            assistant_message="ok", model_name="m",
            is_system_directive=False)
        a, b = self.user_row("a"), self.user_row("b")
        for k in a:
            if k in ("id", "conv_id", "ts"):
                continue
            self.assertEqual(a[k], b[k], f"column {k} differs")

    def test_a_narrator_who_types_the_prefix_keeps_their_words(self):
        """The BOUNDARY does not sniff. Scope corrected 2026-08-09.

        This docstring read "The case the prefix approach gets wrong,
        and this one does not." That overclaimed, and the overclaim is
        worth leaving visible: this test calls `persist_turn_transaction`
        directly WITHOUT the flag, so it proves only that the persistence
        boundary does not re-derive the answer from the text.

        It did NOT prove the pipeline was right. At the time it was
        written `chat_ws` still computed the flag as
        `user_text.lstrip().startswith("[SYSTEM")` one function upstream,
        so a narrator typing "[SYSTEM: ..." would have been flagged
        before reaching here -- the same wrong answer, now durable.
        Caught in supervisor review, fixed in Phase 1b, and pinned by
        `ProvenanceIsDeclaredNotSniffedTest` below.

        A test that proves a function does not do something its caller
        does anyway is a true statement and a misleading one.
        """
        typed = "[SYSTEM: that's what my father called the old switchboard.]"
        self.db.persist_turn_transaction(
            conv_id="c", user_message=typed, assistant_message="ok",
            model_name="m")  # caller did NOT set the flag
        row = self.user_row("c")
        self.assertEqual(typed, row["content"])
        self.assertEqual("{}", row["meta_json"],
                         "the boundary re-sniffed the text; it must not")


class WhatTheModelReplaysIsUnchangedTest(_Base):
    """Behaviour change wearing a storage change's clothes -- prevented."""

    DIRECTIVE = "[SYSTEM: The narrator just selected 'Today' on the Life Map.]"

    def test_role_stays_user_so_the_directive_still_reaches_lori(self):
        self.db.persist_turn_transaction(
            conv_id="c", user_message=self.DIRECTIVE, assistant_message="ok",
            model_name="m", is_system_directive=True)
        self.assertEqual("user", self.user_row("c")["role"])

    def test_role_and_content_are_identical_flagged_or_not(self):
        for conv, flag in (("on", True), ("off", False)):
            self.db.persist_turn_transaction(
                conv_id=conv, user_message=self.DIRECTIVE,
                assistant_message="ok", model_name="m",
                is_system_directive=flag)
        on, off = self.user_row("on"), self.user_row("off")
        self.assertEqual(off["role"], on["role"])
        self.assertEqual(off["content"], on["content"])
        # Only meta_json may differ. Everything a history builder selects
        # to replay to the model is byte-identical.
        self.assertNotEqual(off["meta_json"], on["meta_json"])

    def test_export_turns_still_yields_the_same_replayable_pair(self):
        self.db.persist_turn_transaction(
            conv_id="c", user_message=self.DIRECTIVE, assistant_message="ok",
            model_name="m", is_system_directive=True)
        got = [(t["role"], t["content"]) for t in self.db.export_turns("c")]
        self.assertEqual([("user", self.DIRECTIVE), ("assistant", "ok")], got)


class TheDirectiveIsRecordedTest(_Base):

    def test_flagged_row_carries_the_origin(self):
        self.db.persist_turn_transaction(
            conv_id="c", user_message="[SYSTEM: begin identity onboarding.]",
            assistant_message="ok", model_name="m", is_system_directive=True)
        meta = json.loads(self.user_row("c")["meta_json"])
        self.assertEqual(
            {"origin": self.db.TURN_ORIGIN_SYSTEM_DIRECTIVE}, meta)

    def test_the_assistant_row_is_never_marked(self):
        self.db.persist_turn_transaction(
            conv_id="c", user_message="[SYSTEM: x]", assistant_message="ok",
            model_name="m", is_system_directive=True)
        asst = [r for r in self.rows("c") if r["role"] == "assistant"][0]
        self.assertNotIn("origin", json.loads(asst["meta_json"]))


class TheParameterShapeIsDeliberateTest(unittest.TestCase):
    """Pinned because each choice prevents a specific regression."""

    def setUp(self):
        self.db, self.tmp = _fresh_db_module()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_it_is_keyword_only_and_defaults_false(self):
        p = inspect.signature(self.db.persist_turn_transaction).parameters
        self.assertIn("is_system_directive", p)
        self.assertEqual(inspect.Parameter.KEYWORD_ONLY,
                         p["is_system_directive"].kind)
        self.assertIs(False, p["is_system_directive"].default,
                      "default-false is what makes every pre-existing "
                      "call site behaviour-preserving without an edit")

    def test_it_is_a_flag_not_a_metadata_dict(self):
        """A dict invites a caller to attach the narrator's text.

        That is not hypothetical: it is how `PROFILE_JSON.last_user_text`
        came to duplicate the narrator's current message into the system
        prompt on every turn. A boolean cannot carry prose.
        """
        ann = inspect.signature(
            self.db.persist_turn_transaction).parameters[
                "is_system_directive"].annotation
        self.assertIn("bool", str(ann))


class TurnIsSystemDirectiveTest(_Base):
    """One helper, so eighteen modules stop each inventing the question."""

    def test_the_flag_wins(self):
        row = {"meta_json": json.dumps(
            {"origin": self.db.TURN_ORIGIN_SYSTEM_DIRECTIVE}),
            "content": "ordinary narrator words"}
        self.assertTrue(self.db.turn_is_system_directive(row))

    def test_an_explicit_other_origin_is_an_answer_not_a_fallthrough(self):
        row = {"meta_json": json.dumps({"origin": "narrator"}),
               "content": "[SYSTEM: looks like a directive]"}
        self.assertFalse(
            self.db.turn_is_system_directive(row),
            "a row that WAS classified must not be re-guessed from text")

    def test_legacy_rows_still_fall_back_to_the_prefix(self):
        # 120 such rows exist and no historical rewrite is authorised.
        for content in ("[SYSTEM: x]", "[SYSTEM_QF: x]", "  [SYSTEM: x]"):
            self.assertTrue(
                self.db.turn_is_system_directive(
                    {"meta_json": "{}", "content": content}), content)

    def test_ordinary_narrator_text_is_never_a_directive(self):
        for content in ("My mother kept the ration book.", "", "SYSTEM check",
                        "we talked about the system"):
            self.assertFalse(
                self.db.turn_is_system_directive(
                    {"meta_json": "{}", "content": content}), content)

    def test_unparseable_meta_degrades_to_the_legacy_behaviour(self):
        self.assertTrue(self.db.turn_is_system_directive(
            {"meta_json": "not json{", "content": "[SYSTEM: x]"}))
        self.assertFalse(self.db.turn_is_system_directive(
            {"meta_json": "not json{", "content": "ordinary words"}))

    def test_it_accepts_a_sqlite_row_as_well_as_a_dict(self):
        self.db.persist_turn_transaction(
            conv_id="c", user_message="[SYSTEM: x]", assistant_message="ok",
            model_name="m", is_system_directive=True)
        con = sqlite3.connect(str(self.db.DB_PATH))
        con.row_factory = sqlite3.Row
        try:
            row = con.execute(
                "SELECT * FROM turns WHERE conv_id='c' AND role='user'"
            ).fetchone()
        finally:
            con.close()
        self.assertTrue(self.db.turn_is_system_directive(row))


class CallSitesPassTheExistingClassificationTest(unittest.TestCase):
    """`chat_ws` must forward the decision, not make a second one.

    Source-asserted: the value is computed once at `chat_ws.py:1247` and
    carried in `params`. If a call site ever starts deriving it locally,
    the repository is back to guessing in more than one place.
    """

    _CHAT_WS = (Path(__file__).resolve().parent.parent
                / "server" / "code" / "api" / "routers" / "chat_ws.py")

    def setUp(self):
        self.src = self._CHAT_WS.read_text(encoding="utf-8")

    def test_every_persist_call_forwards_the_flag(self):
        calls = self.src.count("persist_turn_transaction(")
        forwards = self.src.count(
            'is_system_directive=bool(params.get("_is_system_directive"))')
        self.assertEqual(
            calls, forwards,
            f"{calls} persist_turn_transaction call sites but {forwards} "
            f"forward the classification. A turn persisted without it is "
            f"recorded as narrator speech.")

    def test_no_call_site_re_derives_it_from_the_text(self):
        for bad in ('is_system_directive=user_text',
                    'is_system_directive=(user_text',
                    'is_system_directive=_ut_lstrip'):
            self.assertNotIn(bad, self.src)


class ProvenanceIsDeclaredNotSniffedTest(unittest.TestCase):
    """Phase 1b — the correction that makes acceptance criterion 4 true.

    The work order said the classification "already exists, in the right
    place". It existed, but it was itself derived from the text prefix,
    so persisting it would have institutionalised the guess as durable
    metadata and failed the acceptance case it was written to satisfy.

    The sender knows. `sendSystemPrompt()` is a different function from
    `sendUserMessage()`, sends a differently-shaped frame, and carries a
    comment saying it emits directives. Both frames now say so on the
    wire, and the server believes the declaration over the text.
    """

    _ROOT = Path(__file__).resolve().parent.parent
    _WS = _ROOT / "server" / "code" / "api" / "routers" / "chat_ws.py"
    _APP = _ROOT / "ui" / "js" / "app.js"

    def setUp(self):
        # Comment-stripped, because this file's own retirement note
        # QUOTES the retired line -- `_is_system_directive =
        # _ut_lstrip.startswith("[SYSTEM")` -- and a raw scan finds the
        # quotation before the code. Fifth instance of that pattern in
        # this repository; `strip_py_comments` exists to end it.
        raw = self._WS.read_text(encoding="utf-8")
        # `strip_py_comments` re-joins tokens with single spaces, so exact
        # source spellings no longer match. Whitespace is removed from
        # BOTH the haystack and every needle (`_n`) rather than asserting
        # on a formatting-sensitive string -- which would fail the next
        # time somebody reflows a line.
        self.ws = re.sub(r"\s+", "", strip_py_comments(raw))
        self.app = re.sub(r"\s+", "", self._APP.read_text(encoding="utf-8"))
        self.app_raw = self._APP.read_text(encoding="utf-8")

    @staticmethod
    def _n(needle: str) -> str:
        return re.sub(r"\s+", "", needle)

    def test_the_server_reads_a_declared_kind(self):
        self.assertIn(self._n('params.get("message_kind")'), self.ws)
        self.assertIn(self._n('_declared_kind == "internal_directive"'), self.ws)

    def test_the_declaration_is_preferred_over_the_prefix(self):
        """Ordering is the property, so ordering is what is asserted.

        Both mechanisms exist on purpose. What must never invert is
        which one wins.
        """
        decl = self.ws.index(self._n('_declared_kind = str(params.get("message_kind")'))
        use = self.ws.index(self._n('_is_system_directive = (_declared_kind =='))
        prefix = self.ws.index(
            self._n('_is_system_directive = _ut_lstrip.startswith("[SYSTEM")'))
        self.assertLess(decl, use)
        self.assertLess(use, prefix,
                        "the prefix fallback must come AFTER the declared "
                        "kind, or the guess wins again")

    def test_the_prefix_survives_only_as_a_fallback(self):
        """Undeclared senders keep exactly the behaviour they had.

        As of the 2026-08-09 closeout there are NO undeclared senders
        left in the tree -- the two travel-doc modals were the last, and
        they now declare `narrator`. This sentence previously read "Two
        travel-doc modules still send `start_turn` without declaring",
        which was true when it was written and stopped being true within
        the hour.

        The fallback is kept anyway, for the 120 pre-Phase-1 rows and for
        any client that predates the declaration. What it must never
        become again is the primary classifier.
        """
        after = self.ws[self.ws.index(self._n('_declared_kind = str(')):]
        branch = after[:after.index(self._n('params["_is_system_directive"]'))]
        self.assertIn("else:", branch)
        self.assertEqual(
            1, branch.count(self._n('_ut_lstrip.startswith("[SYSTEM")')),
            "the prefix test should appear exactly once, in the else")

    def _resolve(self, *, user_text: str, params: dict) -> bool:
        """Run the SHIPPED resolver, not a copy of it.

        `chat_ws` needs fastapi, which the sandbox has not got, so the
        resolver's own source segment is extracted and executed against
        a controlled namespace. That is weaker than driving a real
        WebSocket and stronger than re-implementing the rule in the
        test -- a re-implementation would agree with itself forever.
        """
        raw = self._WS.read_text(encoding="utf-8")
        start = raw.index('        _ut_lstrip = (user_text or "").lstrip()')
        end = raw.index('        # BUG-TRIP-SYSTEM-DIRECTIVE', start)
        import textwrap
        src = textwrap.dedent(raw[start:end])
        ns: dict = {"user_text": user_text, "params": params}
        exec(compile(src, "<chat_ws-resolver>", "exec"), ns)
        return ns["_is_system_directive"]

    def test_pipeline_a_narrator_typing_the_prefix_stays_narrator(self):
        """Acceptance criterion 4, at the level it actually has to hold.

        This is the case the pushed implementation failed: the resolver
        derived the answer from the text, so a narrator's own words
        beginning "[SYSTEM:" were about to be recorded as machinery --
        permanently, in their memoir.
        """
        self.assertFalse(self._resolve(
            user_text="[SYSTEM: I saw this on the screen and wrote it down]",
            params={"message_kind": "narrator"}))

    def test_pipeline_a_declared_directive_is_one(self):
        self.assertTrue(self._resolve(
            user_text="[SYSTEM: The narrator just selected 'Today'.]",
            params={"message_kind": "internal_directive"}))

    def test_pipeline_provenance_owns_the_decision_not_the_text(self):
        """The strongest of the five, and the point of Phase 1b.

        A directive whose text does not begin "[SYSTEM" is still a
        directive. If this passes, the prefix is provably no longer the
        classifier -- which no amount of testing "[SYSTEM..." strings
        could establish.
        """
        self.assertTrue(self._resolve(
            user_text="Continue from the building years and ask one question.",
            params={"message_kind": "internal_directive"}))

    def test_pipeline_undeclared_senders_keep_the_old_behaviour(self):
        # The two travel-doc senders do not declare. They also emit no
        # directives -- verified: zero "[SYSTEM" strings in either file --
        # so the fallback is what they had and changes nothing for them.
        self.assertTrue(self._resolve(
            user_text="[SYSTEM: legacy client]", params={}))
        self.assertFalse(self._resolve(
            user_text="My mother kept the ration book.", params={}))

    def test_pipeline_an_unknown_declared_kind_is_not_a_directive(self):
        """Fail closed toward narrator speech.

        An unrecognised value means the sender declared something this
        server does not know. Treating that as a directive would let a
        typo erase a narrator's words; treating it as narrator speech
        costs, at worst, a directive appearing in a transcript -- which
        is the failure the readers already tolerate today.
        """
        self.assertFalse(self._resolve(
            user_text="[SYSTEM: x]", params={"message_kind": "narratorr"}))

    def test_the_declared_branch_is_actually_reachable(self):
        """Added after a surviving mutant, 2026-08-09.

        Mutation testing replaced `if _declared_kind:` with `if False:`
        and EVERY substring guard above stayed green -- the declaration
        was still read, the comparison string was still present, the
        ordering was unchanged. Only the branch was dead, so every turn
        fell through to the prefix and the fix silently did nothing.

        A guard that checks for the presence of text cannot see
        reachability. This one reads the branch condition from the AST,
        which can.
        """
        import ast as _ast
        tree = _ast.parse(self._WS.read_text(encoding="utf-8"))
        conditions = []
        for node in _ast.walk(tree):
            if not isinstance(node, _ast.If):
                continue
            names = {n.id for n in _ast.walk(node.test)
                     if isinstance(n, _ast.Name)}
            if "_declared_kind" in names:
                conditions.append(node.test)
        self.assertEqual(
            1, len(conditions),
            "expected exactly one branch on the declared kind")
        self.assertIsInstance(
            conditions[0], _ast.Name,
            "the branch condition must be the bare `_declared_kind`. A "
            "compound or constant test can disable the declaration while "
            "leaving every string these tests look for in place -- which "
            "is exactly the mutant that got through.")
        self.assertEqual("_declared_kind", conditions[0].id)

    def test_the_narrator_frame_declares_itself(self):
        self.assertIn(self._n('message_kind:"narrator"'), self.app)

    def test_the_directive_frame_declares_itself(self):
        self.assertIn(self._n('message_kind:"internal_directive"'), self.app)

    def test_every_start_turn_sender_in_the_tree_declares(self):
        """Closeout guard, 2026-08-09. Stronger than counting app.js.

        The first version of this test asserted "exactly two frames
        declare", which was true of `app.js` and blind to the rest of
        the tree. There are FOUR `start_turn` constructions:
        `app.js` twice, plus the two travel-doc modals -- and those two
        send text a HUMAN typed. Undeclared, a person typing
        "[SYSTEM: ..." into the Travel Doc modal would have been
        recorded as machinery, which is the same defect this work order
        exists to close, in a surface nobody had looked at.

        So the guard now enumerates senders rather than declarations: a
        NEW sender added without a `message_kind` fails here, which is
        the only version of this test that keeps working as the UI
        grows.
        """
        js = sorted((self._ROOT / "ui" / "js").glob("*.js"))
        senders, undeclared = [], []
        for path in js:
            lines = path.read_text(encoding="utf-8").split("\n")
            for i, line in enumerate(lines):
                if re.search(r'type:\s*"start_turn"', line):
                    window = "\n".join(lines[i:i + 20])
                    kind = re.search(r'message_kind:\s*"(\w+)"', window)
                    senders.append((path.name, i + 1,
                                    kind.group(1) if kind else None))
                    if not kind:
                        undeclared.append(f"{path.name}:{i + 1}")
        self.assertEqual(
            [], undeclared,
            f"start_turn sender(s) with no message_kind: {undeclared}. "
            f"An undeclared sender falls back to the [SYSTEM prefix, so a "
            f"human typing that prefix there loses their words.")
        self.assertEqual(
            4, len(senders),
            f"the number of start_turn senders changed: {senders}. That is "
            f"not a failure by itself -- classify the new one and update "
            f"this count deliberately.")
        self.assertEqual(
            1, sum(1 for _, _, k in senders if k == "internal_directive"),
            "exactly one sender should build internal directives; every "
            "other producer routes through sendSystemPrompt")

    def test_the_directive_text_itself_is_unchanged(self):
        """Provenance travels beside the message, never inside it.

        The moment a marker is added to the text, it is in the memoir,
        in the extractor and in the model's context -- which is the
        defect this whole work order exists to undo.
        """
        self.assertIn(self._n("message:instruction,params:{"), self.app)
        for smell in ('message:"[KIND', 'message:kind+', "instruction+'|"):
            self.assertNotIn(self._n(smell), self.app)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
