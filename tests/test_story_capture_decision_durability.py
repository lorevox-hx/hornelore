"""Phase 4 — the capture decision is durable, on the source turn.

    PYTHONPATH=server/code .venv/bin/python -m unittest \\
        tests.test_story_capture_decision_durability

WO-LORI-STORY-CAPTURE-DECISION-DURABILITY-01.

── WHAT THESE TESTS ARE FOR ──────────────────────────────────────────

The capture decision was already computed for every evaluated turn and
already logged in full. It lived in `.runtime/logs/api.log`, which is
gitignored and rotates — so the record for a DECLINED turn, the one case
with no `story_candidates` row to carry it, survived only until the log
aged out. That is what Phase 4 makes durable, and it changes nothing
about which narration is captured.

── THE BOUNDARY RULE, APPLIED ────────────────────────────────────────

`docs/TESTING-DOCTRINE.md`: **a fixture may supply values, but not the
property being proven.** Here that means:

  * the decision object is built by the SHIPPED builder from a SHIPPED
    `trigger_diagnostic()` result — never hand-written;
  * persistence is proven by calling the REAL `persist_turn_transaction`
    against a REAL sqlite file and reading `turns.meta_json` back;
  * "no narrator text in the record" is checked against a transcript the
    test actually passed through the producer, not a constructed dict.

A test that builds its own decision dict and asserts the dict has the
fields it just typed proves nothing, and that is the exact failure this
repository has now recorded eight times.
"""
from __future__ import annotations

import ast
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(_REPO_ROOT), str(_REPO_ROOT / "server" / "code")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api.services import story_trigger as ST  # noqa: E402

_CHAT_WS = _REPO_ROOT / "server" / "code" / "api" / "routers" / "chat_ws.py"
_DB_PY = _REPO_ROOT / "server" / "code" / "api" / "db.py"

#: A transcript that the SHIPPED trigger actually nominates. Its
#: properties are measured at import (below), never asserted in a
#: comment — if the classifier changes, this fails here with the real
#: numbers rather than silently exercising the declined path.
NOMINATING_TEXT = (
    "I was born in Las Vegas, New Mexico, and my father Eliseo was a sheep "
    "rancher in San Miguel County when I was a girl. My mother Adela kept the "
    "house on Hot Springs Road, and years later we walked to Mass at Our Lady "
    "of Sorrows together."
)
DECLINING_TEXT = "Yes."


def _diag(text: str, duration: float = 42.0) -> dict:
    return ST.trigger_diagnostic(audio_duration_sec=duration, transcript=text)


class MeasuredFixtureTests(unittest.TestCase):
    """The fixtures must actually have the properties they are used for."""

    def test_the_nominating_text_really_nominates(self):
        d = _diag(NOMINATING_TEXT)
        self.assertIsNotNone(
            d["trigger"],
            f"the nominating fixture no longer triggers: anchors="
            f"{d['anchor_count']} words={d['word_count']}")

    def test_the_declining_text_really_declines(self):
        d = _diag(DECLINING_TEXT, duration=1.0)
        self.assertIsNone(
            d["trigger"],
            f"the declining fixture now triggers: {d['trigger']}")


class BuilderTests(unittest.TestCase):
    """producer: trigger_diagnostic -> build_story_capture_decision."""

    def test_nominated_carries_the_triggers_own_reason_and_candidate(self):
        d = _diag(NOMINATING_TEXT)
        rec = ST.build_story_capture_decision(
            outcome="nominated", diagnostic=d,
            trigger_reason=d["trigger"], candidate_id="cand-1")
        self.assertEqual(rec["outcome"], "nominated")
        self.assertEqual(rec["reason"], d["trigger"])
        self.assertEqual(rec["candidate_id"], "cand-1")
        self.assertEqual(rec["schema_version"], "story_capture_decision/v1")

    def test_declined_uses_the_approved_reason_and_no_candidate(self):
        rec = ST.build_story_capture_decision(
            outcome="declined", diagnostic=_diag(DECLINING_TEXT, 1.0))
        self.assertEqual(rec["reason"], "below_all_capture_paths")
        self.assertIsNone(rec["candidate_id"])

    def test_declined_is_never_called_not_story(self):
        """A decline is a statement about the classifier, not the story."""
        rec = ST.build_story_capture_decision(
            outcome="declined", diagnostic=_diag(DECLINING_TEXT, 1.0))
        self.assertNotIn("not_story", json.dumps(rec))

    def test_measurement_failed_carries_a_class_name_only(self):
        rec = ST.build_story_capture_decision(
            outcome="measurement_failed", diagnostic=None,
            trigger_reason="preservation_failed",
            error_class=type(ValueError("Eliseo was a sheep rancher")).__name__)
        self.assertEqual(rec["error_class"], "ValueError")
        self.assertNotIn("Eliseo", json.dumps(rec))

    def test_a_nominated_record_without_a_candidate_is_REFUSED(self):
        with self.assertRaises(ST.StoryCaptureDecisionError):
            ST.build_story_capture_decision(
                outcome="nominated", diagnostic=_diag(NOMINATING_TEXT),
                trigger_reason="full_threshold")

    def test_a_declined_record_naming_a_candidate_is_REFUSED(self):
        with self.assertRaises(ST.StoryCaptureDecisionError):
            ST.build_story_capture_decision(
                outcome="declined", diagnostic=_diag(DECLINING_TEXT, 1.0),
                candidate_id="cand-9")

    def test_an_unapproved_outcome_is_REFUSED(self):
        for bad in ("not_story", "skipped", "captured", ""):
            with self.subTest(outcome=bad):
                with self.assertRaises(ST.StoryCaptureDecisionError):
                    ST.build_story_capture_decision(
                        outcome=bad, diagnostic=_diag(DECLINING_TEXT, 1.0))

    def test_an_unapproved_failure_reason_is_REFUSED(self):
        with self.assertRaises(ST.StoryCaptureDecisionError):
            ST.build_story_capture_decision(
                outcome="measurement_failed", diagnostic=None,
                trigger_reason="something_went_wrong", error_class="ValueError")

    def test_the_record_copies_measurements_and_never_recomputes(self):
        """Consuming the diagnostic is the point; recomputing invites drift."""
        d = _diag(NOMINATING_TEXT)
        rec = ST.build_story_capture_decision(
            outcome="nominated", diagnostic=d,
            trigger_reason=d["trigger"], candidate_id="c")
        for field in ("word_count", "anchor_count", "place_anchor",
                      "time_anchor", "person_anchor"):
            with self.subTest(field=field):
                self.assertEqual(rec["diagnostic"][field], d[field])

    def test_chain_is_factual_stays_three_valued(self):
        """None means the chain classifier did not run — not False."""
        rec = ST.build_story_capture_decision(
            outcome="declined", diagnostic=_diag(DECLINING_TEXT, 1.0))
        self.assertIsNone(rec["diagnostic"]["chain_is_factual"])
        rec2 = ST.build_story_capture_decision(
            outcome="declined",
            diagnostic={**_diag(DECLINING_TEXT, 1.0), "chain_is_factual": False})
        self.assertIs(rec2["diagnostic"]["chain_is_factual"], False)

    def test_unknown_diagnostic_fields_are_not_carried_through(self):
        """A record that silently widens is a privacy question unasked."""
        rec = ST.build_story_capture_decision(
            outcome="declined",
            diagnostic={**_diag(DECLINING_TEXT, 1.0),
                        "transcript": NOMINATING_TEXT,
                        "raw_response": "Lori said something"})
        self.assertNotIn("transcript", rec["diagnostic"])
        self.assertNotIn("raw_response", rec["diagnostic"])
        self.assertNotIn("Eliseo", json.dumps(rec))


class PersistenceBoundaryTests(unittest.TestCase):
    """consumer: persist_turn_transaction -> real turns.meta_json."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmp.name
        os.environ["DB_NAME"] = "phase4.sqlite3"
        for mod in [m for m in list(sys.modules) if m.startswith("api.db")]:
            del sys.modules[mod]
        import importlib
        import api.db as _db
        self.db = importlib.reload(_db)
        self.db.init_db()

    def tearDown(self):
        self._tmp.cleanup()

    def _rows(self, conv):
        con = self.db._connect()
        try:
            return con.execute(
                "SELECT role, content, meta_json FROM turns WHERE conv_id=? "
                "ORDER BY id;", (conv,)).fetchall()
        finally:
            con.close()

    def _meta(self, conv, role):
        for r, _content, meta in self._rows(conv):
            if r == role:
                return json.loads(meta or "{}")
        return None

    def test_a_declined_decision_persists_on_the_user_row(self):
        conv = "p4-declined"
        rec = ST.build_story_capture_decision(
            outcome="declined", diagnostic=_diag(DECLINING_TEXT, 1.0))
        self.db.persist_turn_transaction(
            conv, DECLINING_TEXT, "Go on.", model_name="m",
            story_capture_decision=rec)
        stored = self._meta(conv, "user")["story_capture_decision"]
        self.assertEqual(stored["outcome"], "declined")
        self.assertIsNone(stored["candidate_id"])
        self.assertEqual(stored["reason"], "below_all_capture_paths")

    def test_the_decision_is_absent_from_the_assistant_row(self):
        conv = "p4-assistant-clean"
        rec = ST.build_story_capture_decision(
            outcome="declined", diagnostic=_diag(DECLINING_TEXT, 1.0))
        self.db.persist_turn_transaction(
            conv, DECLINING_TEXT, "Go on.", model_name="m",
            story_capture_decision=rec)
        self.assertNotIn("story_capture_decision", self._meta(conv, "assistant"))

    def test_a_nominated_decision_persists_with_its_candidate(self):
        conv = "p4-nominated"
        d = _diag(NOMINATING_TEXT)
        rec = ST.build_story_capture_decision(
            outcome="nominated", diagnostic=d,
            trigger_reason=d["trigger"], candidate_id="cand-77")
        self.db.persist_turn_transaction(
            conv, NOMINATING_TEXT, "Tell me more.", model_name="m",
            story_capture_decision=rec)
        stored = self._meta(conv, "user")["story_capture_decision"]
        self.assertEqual(stored["outcome"], "nominated")
        self.assertEqual(stored["candidate_id"], "cand-77")

    def test_measurement_failed_persists_as_itself_not_as_a_decline(self):
        conv = "p4-failed"
        rec = ST.build_story_capture_decision(
            outcome="measurement_failed", diagnostic=None,
            trigger_reason="preservation_failed", error_class="RuntimeError")
        self.db.persist_turn_transaction(
            conv, NOMINATING_TEXT, "Go on.", model_name="m",
            story_capture_decision=rec)
        stored = self._meta(conv, "user")["story_capture_decision"]
        self.assertEqual(stored["outcome"], "measurement_failed")
        self.assertEqual(stored["error_class"], "RuntimeError")

    def test_no_narrator_or_assistant_prose_reaches_the_record(self):
        """Checked against text that really went through the producer."""
        conv = "p4-no-prose"
        d = _diag(NOMINATING_TEXT)
        rec = ST.build_story_capture_decision(
            outcome="nominated", diagnostic=d,
            trigger_reason=d["trigger"], candidate_id="c")
        self.db.persist_turn_transaction(
            conv, NOMINATING_TEXT, "Tell me more about Eliseo.",
            model_name="m", story_capture_decision=rec)
        blob = json.dumps(self._meta(conv, "user")["story_capture_decision"])
        for fragment in ("Las Vegas", "Eliseo", "Adela", "Hot Springs",
                         "Tell me more"):
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, blob)

    def test_a_legacy_caller_omitting_the_argument_is_unchanged(self):
        conv = "p4-legacy"
        self.db.persist_turn_transaction(conv, "plain", "reply", model_name="m")
        self.assertEqual(self._meta(conv, "user"), {})

    def test_the_system_directive_origin_survives_alongside_the_decision(self):
        conv = "p4-both"
        rec = ST.build_story_capture_decision(
            outcome="declined", diagnostic=_diag(DECLINING_TEXT, 1.0))
        self.db.persist_turn_transaction(
            conv, DECLINING_TEXT, "ok", model_name="m",
            is_system_directive=True, story_capture_decision=rec)
        meta = self._meta(conv, "user")
        self.assertIn("origin", meta)
        self.assertIn("story_capture_decision", meta)

    def test_a_malformed_decision_is_REFUSED_before_the_turn_is_written(self):
        """The turn matters more than its diagnostic.

        Validation happens before `BEGIN`, so a bad record cannot roll
        back the narrator's own row.
        """
        conv = "p4-malformed"
        with self.assertRaises(ST.StoryCaptureDecisionError):
            self.db.persist_turn_transaction(
                conv, "hello", "hi", model_name="m",
                story_capture_decision={"outcome": "declined"})
        self.assertEqual(self._rows(conv), [],
                         "a refused decision must not leave a half-written turn")

    def test_erasure_of_the_turn_removes_the_decision_with_it(self):
        """Inherited deletion is the whole reason this lives on the turn."""
        conv = "p4-erase"
        rec = ST.build_story_capture_decision(
            outcome="declined", diagnostic=_diag(DECLINING_TEXT, 1.0))
        self.db.persist_turn_transaction(
            conv, DECLINING_TEXT, "ok", model_name="m",
            story_capture_decision=rec)
        self.assertIsNotNone(self._meta(conv, "user").get("story_capture_decision"))
        con = self.db._connect()
        try:
            con.execute("DELETE FROM turns WHERE conv_id=?;", (conv,))
            con.commit()
        finally:
            con.close()
        self.assertEqual(self._rows(conv), [])


class WiringTests(unittest.TestCase):
    """Both completion paths hand the record to the writer."""

    @staticmethod
    def _executable(path: Path) -> str:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
                body = getattr(node, "body", None)
                if (body and isinstance(body[0], ast.Expr)
                        and isinstance(body[0].value, ast.Constant)
                        and isinstance(body[0].value.value, str)):
                    if len(body) == 1:
                        body[0] = ast.Pass()
                    else:
                        body.pop(0)
        ast.fix_missing_locations(tree)
        return ast.unparse(tree)

    def setUp(self):
        self.src = self._executable(_CHAT_WS)

    def test_exactly_two_writers_receive_the_decision(self):
        self.assertEqual(
            self.src.count("story_capture_decision=_capture_decision_from(params)"),
            2, "both the ordinary and deterministic completion paths must pass it")

    def test_persist_turn_transaction_call_sites_that_pass_it(self):
        """One is the deterministic finaliser, one the model path."""
        tree = ast.parse(_CHAT_WS.read_text(encoding="utf-8"))
        passing = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", "") or getattr(node.func, "attr", "")
                if name == "persist_turn_transaction":
                    if any(k.arg == "story_capture_decision" for k in node.keywords):
                        passing += 1
        self.assertEqual(passing, 2)

    def test_the_decision_is_built_in_exactly_one_place(self):
        """Two callers, one builder — or they drift."""
        tree = ast.parse(_CHAT_WS.read_text(encoding="utf-8"))
        builders = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                    and (getattr(n.func, "id", "")
                         or getattr(n.func, "attr", "")) == "build_story_capture_decision"]
        self.assertEqual(len(builders), 1)

    def test_all_three_outcomes_are_emitted_somewhere(self):
        for outcome in ("nominated", "declined", "measurement_failed"):
            with self.subTest(outcome=outcome):
                self.assertIn(f"outcome='{outcome}'", self.src)

    def test_recording_never_breaks_the_turn(self):
        """LAW 3 applies to the recorder too."""
        tree = ast.parse(_CHAT_WS.read_text(encoding="utf-8"))
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef)
                  and n.name == "_record_capture_decision")
        self.assertTrue(
            any(isinstance(h, ast.ExceptHandler) for h in ast.walk(fn)),
            "_record_capture_decision must swallow its own failures")

    def test_no_decision_is_written_when_there_is_no_narrator(self):
        """The one branch that deliberately records nothing.

        A trigger fired but `person_id` is missing, so no candidate can
        exist. That fits none of the three outcomes — it is not a
        decline (the trigger fired), not a nomination (no candidate) and
        not a failure (nothing raised). The vocabulary is closed, so the
        branch stays silent and says why. Pinned here so the silence is
        a decision rather than an oversight.
        """
        self.assertIn("PHASE 4 WRITES NOTHING HERE, DELIBERATELY",
                      _CHAT_WS.read_text(encoding="utf-8"))


class ScopeTests(unittest.TestCase):
    """Phase 4 changes observability, not capture."""

    def test_no_threshold_default_changed(self):
        """The stored thresholds describe the decision, not tune it."""
        self.assertEqual(ST._min_duration_sec(), 30.0)
        self.assertEqual(ST._min_words(), 60)
        self.assertEqual(ST._borderline_anchor_count(), 3)
        self.assertEqual(ST._rich_short_min_words(), 15)
        self.assertEqual(ST._rich_short_min_duration_sec(), 10.0)

    def test_the_classifier_still_returns_the_same_four_paths(self):
        src = (_REPO_ROOT / "server" / "code" / "api" / "services"
               / "story_trigger.py").read_text(encoding="utf-8")
        for path in ("full_threshold", "borderline_scene_anchor",
                     "rich_short_narrative", "chain_detection"):
            with self.subTest(path=path):
                self.assertIn(f'return "{path}"', src)

    def test_no_migration_was_added(self):
        """Turn metadata was chosen specifically to avoid one."""
        migrations = _REPO_ROOT / "server" / "code" / "db" / "migrations"
        for sql in migrations.glob("*.sql"):
            with self.subTest(migration=sql.name):
                self.assertNotIn("story_capture_decision",
                                 sql.read_text(encoding="utf-8"))

    def test_the_writer_only_ever_touches_the_user_row(self):
        src = _DB_PY.read_text(encoding="utf-8")
        i = src.index("_capture_decision_for_row is not None")
        window = src[i:i + 400]
        self.assertIn("user_meta[", window)
        self.assertNotIn("assistant_meta", window)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
