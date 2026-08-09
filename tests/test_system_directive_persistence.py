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
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path


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
        """The case the prefix approach gets wrong, and this one does not.

        Nothing stops a narrator beginning a sentence with "[SYSTEM:".
        Under prefix-sniffing their words are erased from their own
        memoir forever. Here the caller did not classify it as a
        directive, so it is not recorded as one -- and this is exactly
        why the boundary must not look at the text.
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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
