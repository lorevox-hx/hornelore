"""Phase 6 baseline integrity — the ten-turn set is MEASURED, not assumed.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python -m unittest \
      tests.test_phase6_baseline_turnset

WHAT THESE PIN
==============

The Phase 6 capture claims "this report is the intended ten-turn
baseline". Before this suite, that claim rested on the runbook: run the
turns correctly and the report is correct. An interrupted or retried
session would leave 11 or 15 traced turns behind, and the renderer would
have drawn every one of them into a report indistinguishable from a
clean run — the contamination invisible exactly when it mattered.

`_sequence_problems` turns that into a refusal, and these tests fail if
any arm of it stops refusing.

THE FIXTURE DOES NOT SUPPLY THE PROPERTY BEING PROVEN
=====================================================

`_narrator_input` claims to read where the runtime records the narrator's
words. A hand-built `{"context": {"narrator_input": ...}}` would prove
only that this file and that reader agree with each other.

So `_traced()` below builds its records by calling the SHIPPED trace
module — `lori_response_trace.begin()` then `note("narrator_input", ...)`,
which is the same call `chat_ws.py:97` makes — and reads the record the
store actually produced. If `note` ever stops writing into `context`, or
the key is renamed, these tests fail at the fixture with the real shape
in the message, rather than passing against a shape nothing produces.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "server" / "code"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from api.services import lori_response_trace as rt        # noqa: E402
import phase6_conversation_capture as cap                 # noqa: E402


class _TracingOn(unittest.TestCase):
    """Tracing is opt-in; an unarmed fixture gets `None` from `begin`."""

    def setUp(self):
        self._prev = os.environ.get("HORNELORE_RESPONSE_TRACE")
        os.environ["HORNELORE_RESPONSE_TRACE"] = "1"
        rt._traces.clear()
        rt._parked.clear()
        rt._parked_keys.clear()
        self.addCleanup(self._restore)

    def _restore(self):
        if self._prev is None:
            os.environ.pop("HORNELORE_RESPONSE_TRACE", None)
        else:
            os.environ["HORNELORE_RESPONSE_TRACE"] = self._prev
        rt._traces.clear()
        rt._parked.clear()
        rt._parked_keys.clear()

    def _traced(self, texts):
        """Records built by the SHIPPED store. See the module docstring."""
        records = []
        for text in texts:
            trace_id = rt.begin(narrator_id="ada", conversation_id="c1")
            self.assertIsNotNone(
                trace_id, "begin() returned None — tracing is not armed, "
                          "so this fixture would prove nothing")
            rt.note("narrator_input", text, trace_id=trace_id)
            records.append(dict(rt._traces[trace_id]))
        return records


class TurnSetFile(unittest.TestCase):
    """The authoritative list, and the scoring split Chris asked for."""

    def setUp(self):
        self.data = json.loads(cap.TURN_SET.read_text(encoding="utf-8"))
        self.turns = self.data["turns"]

    def test_the_set_is_exactly_ten_turns(self):
        self.assertEqual(len(self.turns), 10)

    def test_indexes_are_one_through_ten_in_order(self):
        self.assertEqual([t["index"] for t in self.turns],
                         list(range(1, 11)))

    def test_exactly_one_turn_requests_the_correction_route(self):
        corrections = [t for t in self.turns
                       if t["expected_requested_route"] == "correction"]
        self.assertEqual(
            [t["index"] for t in corrections], [6],
            "turn 6 is the only turn the BROWSER should route as a "
            "correction")

    def test_the_set_declares_no_static_aggregate_membership(self):
        """Membership follows generation evidence, never a prediction.

        Run 1 declared turn 6 outside the aggregate because the browser
        routes it as a correction. It generated anyway — the server
        returns an unparseable correction to the ordinary pipeline
        (chat_ws.py:5031) — so the declaration described an assumption
        rather than the run. The field is gone; the capture reads
        `generation_attempted` from each trace instead.
        """
        for turn in self.turns:
            self.assertNotIn(
                "in_quality_aggregate", turn,
                "aggregate membership must be measured, not declared")

    def test_every_turn_carries_a_category_and_nonempty_text(self):
        for turn in self.turns:
            self.assertTrue(str(turn.get("category") or "").strip())
            self.assertTrue(str(turn.get("text") or "").strip())

    def test_no_turn_text_is_repeated(self):
        texts = [t["text"] for t in self.turns]
        self.assertEqual(len(set(texts)), len(texts))


class SequenceEnforcement(_TracingOn):
    """Every arm of the refusal, driven through the shipped trace store."""

    def setUp(self):
        super().setUp()
        self.turns = json.loads(
            cap.TURN_SET.read_text(encoding="utf-8"))["turns"]
        self.texts = [t["text"] for t in self.turns]

    def test_the_intended_run_is_accepted(self):
        problems = cap._sequence_problems(self._traced(self.texts),
                                          self.turns)
        self.assertEqual(problems, [], f"a clean run was refused: {problems}")

    def test_a_short_run_is_refused(self):
        problems = cap._sequence_problems(self._traced(self.texts[:9]),
                                          self.turns)
        self.assertTrue(any("found 9" in p for p in problems), problems)

    def test_an_extra_turn_is_refused(self):
        extra = self.texts + ["And that's about all I remember today."]
        problems = cap._sequence_problems(self._traced(extra), self.turns)
        self.assertTrue(any("found 11" in p for p in problems), problems)

    def test_a_retried_turn_is_refused_as_contamination(self):
        """The failure this exists for: a resend leaves both attempts."""
        retried = self.texts[:3] + [self.texts[2]] + self.texts[3:]
        problems = cap._sequence_problems(self._traced(retried), self.turns)
        self.assertTrue(any("sent 2 times" in p for p in problems), problems)

    def test_reordering_is_refused_and_named_as_reordering(self):
        swapped = list(self.texts)
        swapped[3], swapped[6] = swapped[6], swapped[3]
        problems = cap._sequence_problems(self._traced(swapped), self.turns)
        self.assertTrue(any("OUT OF ORDER" in p for p in problems), problems)

    def test_a_foreign_turn_is_refused(self):
        foreign = list(self.texts)
        foreign[4] = "Tell me about the weather."
        problems = cap._sequence_problems(self._traced(foreign), self.turns)
        self.assertTrue(
            any("not a baseline turn" in p for p in problems), problems)

    def test_whitespace_around_a_turn_does_not_refuse(self):
        """A trailing newline from the composer is not contamination."""
        padded = ["  " + t + "\n" for t in self.texts]
        self.assertEqual(
            cap._sequence_problems(self._traced(padded), self.turns), [])


class SystemDirectivesAreNotNarratorTurns(_TracingOn):
    """An idle session appends system turns. They are not contamination.

    Phase 6 run 1: the silence/re-entry directive fired two minutes after
    turn 10 and the capture refused an otherwise perfect baseline. The
    discriminator it needed was already in the trace — the extraction
    stage records `is_system_directive` because it deliberately skips
    these turns.
    """

    def setUp(self):
        super().setUp()
        self.turns = json.loads(
            cap.TURN_SET.read_text(encoding="utf-8"))["turns"]
        self.texts = [t["text"] for t in self.turns]

    def _with_extraction(self, rec, is_directive):
        """Attach the storage shape the SHIPPED extraction stage writes."""
        rec["storage"] = {"extraction": {"detail": {
            "is_system_directive": is_directive,
            "method": "system_directive" if is_directive else "llm",
        }}}
        return rec

    def test_a_system_directive_does_not_contaminate_a_valid_baseline(self):
        recs = self._traced(self.texts)
        for r in recs:
            self._with_extraction(r, False)
        directive = self._traced([
            "[SYSTEM: The narrator has been quiet for a while. Offer a "
            "gentle, warm invitation to continue their life story.]"])[0]
        self._with_extraction(directive, True)
        everything = recs + [directive]

        narrator_turns = [r for r in everything
                          if not cap.is_system_directive(r)]
        self.assertEqual(len(narrator_turns), 10)
        self.assertEqual(
            cap._sequence_problems(narrator_turns, self.turns), [],
            "a valid ten-turn baseline was refused because a system "
            "directive fired while the session sat idle")

    def test_an_eleventh_NARRATOR_turn_still_refuses(self):
        """The real contamination case must keep failing."""
        extra = self.texts + ["And one more thing I forgot to mention."]
        recs = [self._with_extraction(r, False) for r in self._traced(extra)]
        narrator_turns = [r for r in recs if not cap.is_system_directive(r)]
        self.assertEqual(len(narrator_turns), 11)
        problems = cap._sequence_problems(narrator_turns, self.turns)
        self.assertTrue(any("found 11" in p for p in problems), problems)

    def test_the_product_decision_outranks_the_text_prefix(self):
        """`is_system_directive` is read; the prefix is only a fallback."""
        rec = self._traced(["[SYSTEM: looks like a directive]"])[0]
        self._with_extraction(rec, False)
        self.assertFalse(
            cap.is_system_directive(rec),
            "the shipped extraction decision must win over a text sniff")
        bare = self._traced(["[SYSTEM: no extraction stage attached]"])[0]
        self.assertTrue(cap.is_system_directive(bare))


class PreflightAgreesWithTheSameFile(unittest.TestCase):
    """The JS consumer is EXECUTED, not grepped.

    A source-string assertion that the preflight mentions the JSON path
    is not evidence that it reads it — the doctrine file is explicit that
    source-string assertions are never acceptance evidence by themselves.
    Running it proves the three consumers share one list.
    """

    def test_the_shipped_router_preflight_passes_on_this_set(self):
        script = REPO_ROOT / "scripts" / "ui" / "phase6_turn_route_preflight.js"
        try:
            proc = subprocess.run(["node", str(script)], cwd=str(REPO_ROOT),
                                  capture_output=True, text=True, timeout=120)
        except FileNotFoundError:
            self.skipTest("node is not available on this interpreter's host")
        self.assertEqual(
            proc.returncode, 0,
            f"the route preflight refused the committed turn set:\n"
            f"{proc.stdout}\n{proc.stderr}")
        self.assertIn("nine requested as interview", proc.stdout)


class WritesOnlyToTheServersDatabase(unittest.TestCase):
    """The failure that produced a passing run about the wrong world.

    On its first live run the creation script wrote Ada into a database
    nothing serves. `api.db` resolves `DATA_DIR` at import (db.py:58),
    defaulting to a repo-relative `data/`; the server runs with `.env`
    loaded. With neither variable exported, `init_db()` CREATED a second
    empty database and populated it — and then every check passed: ten
    topics answered, `plan_turn` IDLE, `PASS`. The product returned 404
    for that narrator.

    So the guard is not "warn if the path looks odd". It is: a database
    that does not exist yet is proof of pointing at the wrong world, and
    the script must refuse WITHOUT creating it.
    """

    SCRIPT = REPO_ROOT / "scripts" / "phase6_populated_narrator.py"

    def test_create_refuses_and_creates_nothing_when_the_db_is_absent(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ)
            env["DATA_DIR"] = tmp
            env["DB_NAME"] = "nonexistent.sqlite3"
            env["PYTHONPATH"] = str(REPO_ROOT / "server" / "code")
            proc = subprocess.run(
                [sys.executable, str(self.SCRIPT), "--create"],
                cwd=str(REPO_ROOT), env=env, capture_output=True,
                text=True, timeout=180)

            self.assertEqual(
                proc.returncode, 2,
                f"expected the refusal exit code.\n{proc.stdout}\n{proc.stderr}")
            self.assertIn("REFUSING", proc.stderr)
            # The property that matters: nothing was created.
            self.assertFalse(
                (Path(tmp) / "db" / "nonexistent.sqlite3").exists(),
                "the script CREATED a database it had just refused to use — "
                "which is the original bug, not a fix for it")

    def test_the_resolved_database_path_is_printed(self):
        """A destination that is never shown is a destination nobody checks."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ)
            env["DATA_DIR"] = tmp
            env["DB_NAME"] = "nonexistent.sqlite3"
            env["PYTHONPATH"] = str(REPO_ROOT / "server" / "code")
            proc = subprocess.run(
                [sys.executable, str(self.SCRIPT), "--create"],
                cwd=str(REPO_ROOT), env=env, capture_output=True,
                text=True, timeout=180)
        self.assertIn("Database:", proc.stdout)
        self.assertIn("nonexistent.sqlite3", proc.stdout)

    def test_dotenv_supplies_the_keys_but_the_environment_wins(self):
        """Precedence matches the server: an exported value is not clobbered."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_phase6_narrator_for_test", self.SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        dotenv = REPO_ROOT / ".env"
        if not dotenv.is_file():
            self.skipTest("no .env on this host")
        declared = {}
        for line in dotenv.read_text(encoding="utf-8",
                                     errors="replace").splitlines():
            for key in ("DATA_DIR", "DB_NAME"):
                if line.strip().startswith(f"{key}="):
                    declared[key] = line.strip().split("=", 1)[1].strip()
        if "DATA_DIR" not in declared:
            self.skipTest(".env declares no DATA_DIR")

        prev = {k: os.environ.get(k) for k in ("DATA_DIR", "DB_NAME")}
        try:
            os.environ.pop("DATA_DIR", None)
            os.environ["DB_NAME"] = "already-exported.sqlite3"
            module._load_env()
            self.assertEqual(os.environ["DATA_DIR"], declared["DATA_DIR"],
                             "the .env value should fill an unset key")
            self.assertEqual(os.environ["DB_NAME"], "already-exported.sqlite3",
                             "an exported value must win, as it does for "
                             "the server")
        finally:
            for key, value in prev.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
