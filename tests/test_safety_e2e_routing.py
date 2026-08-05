"""C1b — end-to-end WebSocket safety-routing integration test.

The existing safety tests are all UNIT-level: the classifier parser
(test_safety_classifier), the route_safety composition table
(test_safety_classifier_three_dim), the prompt block presence
(test_safety_response_block), and the chat_ws import contract
(test_safety_import_contract). Each piece is proven alone.

What was NEVER proven — and what protects Kent and Janice — is the COMPOSED
chain producing the right side effects against a real DB, and (just as
important) NOT escalating on the four look-alike cases:

    indirect ideation turn
      -> pattern scan (safety.scan_answer)          # misses indirect by design
      -> LLM classifier (safety_classifier)         # fills the gap
      -> route_safety                               # ROUTE_ACUTE
      -> synthesized SafetyResult                   # _llm_cat_map, as chat_ws does
      -> segment flag written to DB
      -> softened mode written to DB
      -> operator-visible safety event written to DB
      -> crisis resources include 988

This test drives the REAL functions in the REAL order chat_ws uses, against a
REAL temp SQLite DB. Only the LLM round-trip is mocked (non-deterministic, and
the heavy stack is not available in the test env). It runs in a SUBPROCESS so it
can set HORNELORE_SAFETY_LLM_LAYER=1 and inject a fake api.llm_interview without
leaking either into the parent test process (the sys.modules-pollution class
this suite has been bitten by).

Two negative-space guarantees are the safety-critical half:
  * external fear ("I am kind of scared, are you safe to talk to?") — Mary's
    2026-05-09 case that 988'd an 86-year-old — must NOT escalate.
  * mortality reflection, third-party family history, and LLM parse failure
    must NOT escalate either.

A companion source-wiring class asserts the chat_ws handler actually contains
the routing side-effect calls, so the handler glue is pinned even without a
live WebSocket.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
_CHAT_WS = _SERVER_CODE / "api" / "routers" / "chat_ws.py"


# ── The subprocess driver ──────────────────────────────────────────────────
# Reproduces the chat_ws safety hook EXACTLY (scan -> classify -> route ->
# synth -> DB side effects), using the real functions + a real temp DB. The
# _llm_cat_map mirrors chat_ws.py verbatim; if chat_ws changes it, the live
# smoke (flag-on) is the backstop, and this stays the composition proof.
_E2E_SUBPROCESS = r'''
import os, sys, json, tempfile, sqlite3, types
from pathlib import Path

SERVER_CODE = sys.argv[1]
sys.path.insert(0, SERVER_CODE)

# Safety LLM layer ON for this process only.
os.environ["HORNELORE_SAFETY_LLM_LAYER"] = "1"
os.environ["HORNELORE_SAFETY_LLM_CONFIDENCE_FLOOR"] = "0.65"

# ── temp DB with the three tables the safety hook writes ──
tmpdir = tempfile.mkdtemp(prefix="safety_e2e_")
db_file = Path(tmpdir) / "test.sqlite3"
con = sqlite3.connect(str(db_file))
con.executescript("""
-- FK constraints deliberately omitted: _connect() sets PRAGMA
-- foreign_keys=ON, and there are no people/plan parent rows in this minimal
-- fixture. The columns are what the safety writes touch — that is the scope.
CREATE TABLE IF NOT EXISTS interview_plans (
    id TEXT PRIMARY KEY, title TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS interview_sessions (
    id TEXT PRIMARY KEY, person_id TEXT, plan_id TEXT,
    started_at TEXT, updated_at TEXT, active_question_id TEXT,
    interview_softened INTEGER DEFAULT 0, softened_until_turn INTEGER DEFAULT 0,
    turn_count INTEGER DEFAULT 0, softened_trigger TEXT DEFAULT '',
    softened_initial_n INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS segment_flags (
    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, question_id TEXT,
    section_id TEXT, sensitive INTEGER NOT NULL DEFAULT 0,
    sensitive_category TEXT DEFAULT '', excluded_from_memoir INTEGER NOT NULL DEFAULT 1,
    private INTEGER NOT NULL DEFAULT 1, deleted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS safety_events (
    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, person_id TEXT,
    category TEXT NOT NULL DEFAULT '', matched_phrase TEXT, turn_excerpt TEXT,
    created_at TEXT NOT NULL, acknowledged_at TEXT, acknowledged_by TEXT
);
""")
con.commit()
con.close()

# Point the db accessors at the temp file.
import api.db as db
db.DB_PATH = db_file

# ── Fake the LLM round-trip. classify_safety_llm does
#    `from .llm_interview import _try_call_llm`, so we inject api.llm_interview.
#    Each test sets FAKE_LLM_JSON to the string the model "returns".
import api  # ensure the package exists before we inject a submodule
_fake = types.ModuleType("api.llm_interview")
# ── WO-LEAN-LORI-RUNTIME-01 Phase 3B, 2026-08-04 ──────────────────────
# The safety feature is PARKED by default in Lean Lori, so these tests
# opt back into the ACTIVE state. That is the point of parking rather
# than deleting: the feature and its whole test surface are preserved
# and still exercised, the way Companion mode is, and reactivation is a
# setting rather than an archaeology exercise.
#
# Setting it per-module rather than per-test is deliberate: a suite that
# exists to prove the safety feature works should be entirely in the
# state where the feature exists. The PARKED behaviour has its own
# suite, tests/test_safety_parked.py.
def setUpModule():  # noqa: N802
    import os
    global _SAVED_SAFETY_STATE
    _SAVED_SAFETY_STATE = os.environ.get("HORNELORE_SAFETY_STATE")
    os.environ["HORNELORE_SAFETY_STATE"] = "active"


def tearDownModule():  # noqa: N802
    import os
    if _SAVED_SAFETY_STATE is None:
        os.environ.pop("HORNELORE_SAFETY_STATE", None)
    else:
        os.environ["HORNELORE_SAFETY_STATE"] = _SAVED_SAFETY_STATE


def _try_call_llm(system_prompt=None, user_prompt=None, **kw):
    return globals().get("FAKE_LLM_JSON", None)
_fake._try_call_llm = _try_call_llm
sys.modules["api.llm_interview"] = _fake

from api.safety import (
    scan_answer, build_segment_flags, get_resources_for_category, SafetyResult,
)
from api.safety_classifier import (
    classify_safety_llm, route_safety, ROUTE_ACUTE,
)

# _llm_cat_map — verbatim from chat_ws.py safety hook.
_LLM_CAT_MAP = {
    "acute": "suicidal_ideation",
    "ideation": "suicidal_ideation_indirect",
    "distressed": "cognitive_distress",
}

def run_hook(conv_id, person_id, text, fake_llm_json):
    """Reproduce the chat_ws safety hook for one turn. Returns a dict of what
    happened, and writes real rows to the temp DB when it escalates."""
    globals()["FAKE_LLM_JSON"] = fake_llm_json

    # 1. pattern layer
    pattern = scan_answer(text)
    safety_result = pattern

    route = None
    if not (safety_result and safety_result.triggered):
        # 2 + 3. LLM classifier -> route
        classification = classify_safety_llm(text)
        route = route_safety(False, classification)
        if route == ROUTE_ACUTE:
            # 4. synthesize SafetyResult (chat_ws _llm_cat_map)
            safety_result = SafetyResult(
                triggered=True,
                category=_LLM_CAT_MAP.get(classification.category,
                                          "cognitive_distress"),
                confidence=classification.confidence,
            )
    else:
        route = ROUTE_ACUTE  # pattern authority

    escalated = bool(safety_result and safety_result.triggered)
    out = {"escalated": escalated, "route": route,
           "category": safety_result.category if escalated else None}

    if escalated:
        # 5. segment flag
        db.ensure_interview_session(conv_id, person_id)
        flags = build_segment_flags(safety_result)
        db.save_segment_flag(
            session_id=conv_id, question_id=None, section_id=None,
            sensitive=flags.sensitive,
            sensitive_category=flags.sensitive_category or "",
            excluded_from_memoir=flags.excluded_from_memoir,
            private=flags.private,
        )
        # 6. softened mode
        db.set_session_softened(conv_id, current_turn=1,
                                softened_turns=5, trigger="acute")
        # 7. operator-visible safety event
        db.save_safety_event(
            session_id=conv_id, person_id=person_id,
            category=safety_result.category,
            matched_phrase=safety_result.matched_phrase,
            turn_excerpt=text[:200],
        )

    # read the DB side effects back
    out["segment_flags"] = [
        f for f in (db.get_segment_flags(conv_id) or []) if f.get("sensitive")
    ]
    out["softened"] = db.get_session_softened_state(conv_id).get(
        "interview_softened", False)
    # Read safety_events directly (list_safety_events filters by person_id and
    # calls init_db, which needs the migrations runner — out of scope here).
    _c = sqlite3.connect(str(db_file))
    out["safety_events"] = _c.execute(
        "SELECT id, category FROM safety_events WHERE session_id=?",
        (conv_id,)).fetchall()
    _c.close()
    out["resources_988"] = any(
        r.get("contact") == "988"
        for r in get_resources_for_category(out["category"])
    ) if escalated else False
    return out


checks = []
def ck(name, ok):
    checks.append((name, bool(ok)))

# ═══ POSITIVE: indirect ideation escalates through the whole chain ═══
r = run_hook("c_pos", "p1",
             "I just don't see the point in any of this anymore.",
             '{"category":"ideation","tense":"present","subject":"self","confidence":0.8}')
ck("indirect_pattern_missed_but_escalated", r["escalated"] and r["route"] == "acute")
ck("indirect_category_indirect", r["category"] == "suicidal_ideation_indirect")
ck("indirect_segment_flag_written", len(r["segment_flags"]) == 1)
ck("indirect_segment_flag_sensitive",
   r["segment_flags"] and r["segment_flags"][0].get("sensitive") == 1)
ck("indirect_softened_written", r["softened"] is True or r["softened"] == 1)
ck("indirect_safety_event_written", len(r["safety_events"]) >= 1)
ck("indirect_resources_include_988", r["resources_988"] is True)

# ═══ NEGATIVE #1: external fear (Mary) must NOT escalate ═══
r = run_hook("c_ext", "p2",
             "I am kind of scared, are you safe to talk to?",
             '{"category":"none","tense":"none","subject":"external","confidence":0.5}')
ck("external_fear_no_escalation", not r["escalated"])
ck("external_fear_no_segment_flag", len(r["segment_flags"]) == 0)
ck("external_fear_no_softened", not r["softened"])
ck("external_fear_no_safety_event", len(r["safety_events"]) == 0)

# ═══ NEGATIVE #2: mortality reflection must NOT escalate ═══
r = run_hook("c_mort", "p3",
             "I've outlived a lot of friends.",
             '{"category":"none","tense":"mortality_reflection","subject":"self","confidence":0.8}')
ck("mortality_no_escalation", not r["escalated"])
ck("mortality_no_segment_flag", len(r["segment_flags"]) == 0)

# ═══ NEGATIVE #3: third-party family history must NOT escalate ═══
r = run_hook("c_third", "p4",
             "My brother killed himself in '64.",
             '{"category":"ideation","tense":"past","subject":"third_party","confidence":0.7}')
ck("third_party_no_escalation", not r["escalated"])
ck("third_party_no_segment_flag", len(r["segment_flags"]) == 0)

# ═══ NEGATIVE #4: LLM parse failure fails OPEN (no escalation) ═══
r = run_hook("c_parse", "p5",
             "Something ambiguous the model garbles.",
             'not json at all { broken')
ck("parse_fail_no_escalation", not r["escalated"])
ck("parse_fail_no_segment_flag", len(r["segment_flags"]) == 0)

# ═══ PATTERN PATH: explicit acute escalates WITHOUT the LLM ═══
r = run_hook("c_pat", "p6",
             "I want to kill myself.",
             '{"category":"none","tense":"none","subject":"none","confidence":0.0}')
ck("pattern_acute_escalated", r["escalated"] and r["route"] == "acute")
ck("pattern_acute_category", r["category"] == "suicidal_ideation")
ck("pattern_acute_segment_flag", len(r["segment_flags"]) == 1)
ck("pattern_acute_988", r["resources_988"] is True)

for name, ok in checks:
    print(("ok   " if ok else "FAIL ") + name)
sys.exit(0 if all(ok for _, ok in checks) else 1)
'''


# ── WO-LEAN-LORI-RUNTIME-01 Phase 3B, corrected 2026-08-04 ────────────
# THIS MODULE ALREADY CONTAINED A `setUpModule` OPTING INTO THE ACTIVE
# STATE, AND IT WAS DEAD CODE.
#
# It sits at line ~122, which is INSIDE the `_E2E_SUBPROCESS` triple-
# quoted string — the source text handed to the child interpreter, where
# unittest never runs and nothing calls it. So the parent never set the
# variable, the child inherited a parked environment, and every one of
# the eleven routing checks failed.
#
# It went unnoticed because this suite could not run at all in the
# sandbox until pydantic was installed, so it reported ENV-SKIP rather
# than a failure. It would have failed on Chris's .venv, which has
# pydantic. That is the lesson worth keeping: a suite that cannot run is
# not a suite that passes, and an ENV-SKIP hides a red just as well as a
# green does.
#
# The dead copy is deliberately left where it is rather than deleted: it
# is inside a string that reproduces a module's setup, and removing lines
# from that string risks changing what the child does for a reason
# unrelated to this fix.
_SAVED_SAFETY_STATE = None


def setUpModule():  # noqa: N802
    """Opt into ACTIVE safety for the parent AND the child.

    `subprocess.run` inherits `os.environ`, so setting it here is what
    actually reaches the child interpreter that drives the chain.
    """
    import os
    global _SAVED_SAFETY_STATE
    _SAVED_SAFETY_STATE = os.environ.get("HORNELORE_SAFETY_STATE")
    os.environ["HORNELORE_SAFETY_STATE"] = "active"


def tearDownModule():  # noqa: N802
    import os
    if _SAVED_SAFETY_STATE is None:
        os.environ.pop("HORNELORE_SAFETY_STATE", None)
    else:
        os.environ["HORNELORE_SAFETY_STATE"] = _SAVED_SAFETY_STATE


class SafetyEndToEndRoutingTest(unittest.TestCase):
    """Drives the real safety chain against a real temp DB, in a subprocess."""

    def test_the_active_opt_in_actually_reaches_this_process(self):
        """Non-vacuity guard for the correction above.

        The previous opt-in was syntactically perfect and had no effect
        because of where it lived. This fails loudly if that happens
        again, instead of the eleven downstream checks failing for a
        reason nobody can see from their names.
        """
        import os
        self.assertEqual("active", os.environ.get("HORNELORE_SAFETY_STATE"),
                         "setUpModule did not run in the parent process — "
                         "check it is at module level and not inside the "
                         "_E2E_SUBPROCESS string")

    def test_full_chain_and_no_false_escalation(self):
        out = subprocess.run(
            [sys.executable, "-c", _E2E_SUBPROCESS, str(_SERVER_CODE)],
            capture_output=True, text=True, timeout=120)
        checks = [l for l in out.stdout.splitlines()
                  if l.startswith(("ok ", "FAIL"))]
        self.assertTrue(
            checks,
            "subprocess produced no checks — setup failed:\n"
            + out.stdout + "\n" + out.stderr)
        fails = [l for l in checks if l.startswith("FAIL")]
        self.assertEqual(
            out.returncode, 0,
            "safety routing chain broke:\n" + "\n".join(fails)
            + "\n\n(full output)\n" + out.stdout + "\n" + out.stderr)


class ChatWsSafetyHookWiringTest(unittest.TestCase):
    """The handler glue: chat_ws must actually contain the routing side-effect
    calls in its safety hook. Pins the wiring even without a live WebSocket, so
    a future edit that drops (say) the save_safety_event call fails the build."""

    @classmethod
    def setUpClass(cls):
        cls.src = _CHAT_WS.read_text(encoding="utf-8")

    def test_pattern_scan_is_called(self):
        self.assertIn("scan_answer(user_text)", self.src)

    def test_llm_classifier_and_route_are_called(self):
        self.assertIn("classify_safety_llm", self.src)
        self.assertIn("route_safety", self.src)

    def test_segment_flag_is_written_on_trigger(self):
        self.assertIn("build_segment_flags(_safety_result)", self.src)
        self.assertIn("save_segment_flag(", self.src)

    def test_softened_mode_is_written_on_trigger(self):
        self.assertIn("_softened_write(", self.src)

    def test_operator_signal_is_emitted(self):
        # DB-side operator event + narrator-invisible UI signal.
        self.assertIn("_safety_notify_operator(", self.src)
        self.assertIn('"safety_triggered"', self.src)

    def test_crisis_resources_are_attached(self):
        self.assertIn("get_resources_for_category(_safety_result.category)",
                      self.src)

    def test_external_fear_is_diverted_before_safety_scan(self):
        # Mary's "are you safe to talk to?" must be caught by the deterministic
        # meta-question intercept BEFORE the LLM safety classifier runs.
        self.assertIn("_is_meta_question", self.src)
        self.assertIn("not _is_meta_question", self.src)


if __name__ == "__main__":
    unittest.main()
