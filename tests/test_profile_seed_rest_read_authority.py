"""Phase 2 Step 5: REST composes from server-authoritative state.

WO-LORI-PROFILE-SEED-REACHABILITY-01, Phase 2, Step 5 (2026-08-26).

── HOW TO RUN THIS ───────────────────────────────────────────────────

    PYTHONPATH=server/code python3 -m unittest tests.test_profile_seed_rest_read_authority

**NOT `.venv/bin/python`.** `.venv` is Python 3.10.12 with NO fastapi,
and the route class below imports `api.api`. There those tests SKIP and
unittest still prints `OK` — a skip count is not a pass. Read the skip
count before calling anything verified.

── WHAT STEP 5 IS, AND WHAT IT IS NOT ────────────────────────────────

It is the first transport to SUPPLY `profile_seed_onboarding`, for
prompt composition only. It never advances the walk and never writes a
turn event; that is Step 6 on the committed-turn path.

Real storage throughout, following the rule Phase 0 was corrected into:
a test that feeds the resolver invented keys it never reads measures
fiction being discarded. Every narrator here is created through
`db.create_person()` and every fact through the real writers.

── THE PROPERTY THAT MATTERS MOST ────────────────────────────────────

**Byte-identical.** For every narrator this step has nothing to say —
ownerless, historical, completed, anonymous — the composed prompt must
equal what the composer produced before Step 5 existed. Not "similar",
not "contains the same lines": equal. This lane has already shipped one
subset assertion that permitted fifteen thousand characters of unrelated
runtime content to arrive unnoticed.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
for _p in (str(_SERVER_CODE), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api import db as _db                                    # noqa: E402
from api import prompt_composer as _pc                       # noqa: E402
from api.services import profile_seed as _ps                 # noqa: E402
from api.services import profile_seed_rest as _rest          # noqa: E402

#: Can `api.api` be imported at all? It pulls in torch at module scope.
#:
#: The reason is captured and reported in the skip message rather than
#: guessed at, because an earlier guard in this lane named fastapi while
#: the real blocker was something else — and a skip whose stated reason
#: is wrong is worse than no skip, since it stops anyone investigating.
try:
    import api.api as _api_module                            # noqa: F401
    _HAS_API = True
    _API_IMPORT_ERROR = ""
except Exception as _exc:                                    # pragma: no cover
    _HAS_API = False
    _API_IMPORT_ERROR = f"{type(_exc).__name__}: {_exc}"

KEY = _pc.PROFILE_SEED_ONBOARDING_KEY


class _Base(unittest.TestCase):
    """One temp DATA_DIR and one temp database per test.

    `_BIO_SEED_LOADED` is reset before `init_db()` because it is a
    once-per-process gate — see `test_profile_seed_server_authority`,
    which lost real time to it.
    """

    def setUp(self):
        self.data_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.data_tmp.cleanup)
        self._orig_data_dir = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = str(Path(self.data_tmp.name).resolve())
        self.addCleanup(self._restore_data_dir)

        fd = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        fd.close()
        self.db_path = Path(fd.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db._BIO_SEED_LOADED = False
        _db.init_db()
        self.addCleanup(self._restore_db)

    def _restore_data_dir(self):
        if self._orig_data_dir is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self._orig_data_dir

    def _restore_db(self):
        _db.DB_PATH = self._orig_db
        try:
            self.db_path.unlink()
        except OSError:
            pass

    # ── fixtures, all through the real writers ──────────────────────
    def _person(self, name="Verlie Ostrander", *, anchors=True):
        return _db.create_person(
            name,
            date_of_birth="1936-11-08" if anchors else "",
            place_of_birth="Spokane, Washington" if anchors else "",
            narrator_type="live")["id"]

    def _session(self, conv_id, person_id=None):
        con = sqlite3.connect(str(self.db_path))
        try:
            con.execute(
                "INSERT INTO sessions (conv_id, payload_json, person_id) "
                "VALUES (?, ?, ?);",
                (conv_id, json.dumps({}), person_id))
            con.commit()
        finally:
            con.close()

    def runtime(self, conv_id=None, profile=None):
        return _rest.onboarding_runtime(conv_id, profile)

    def compose(self, runtime=None):
        return _pc.compose_system_prompt("conv-step5", runtime71=runtime)


# ── ownership ────────────────────────────────────────────────────────
class OwnershipTests(_Base):
    """The recorded owner wins; the payload is a claim, never authority."""

    def test_the_session_owner_beats_a_claim_that_agrees(self):
        pid = self._person()
        self._session("c1", pid)
        self.assertEqual(pid, _rest.resolve_rest_identity(
            "c1", {"person_id": pid}, owner_lookup=lambda c: pid))

    def test_the_owner_is_used_when_no_claim_is_made(self):
        self.assertEqual("p-owner", _rest.resolve_rest_identity(
            "c1", None, owner_lookup=lambda c: "p-owner"))

    def test_the_claim_is_used_ONLY_when_no_owner_is_recorded(self):
        """Truthful for every session row written before 0044.

        `None` from the lookup is "we never wrote it down", not "nobody
        owns this" — so the caller's claim is the only information there
        is, and using it is not a guess about identity.
        """
        self.assertEqual("p-claim", _rest.resolve_rest_identity(
            "c1", {"person_id": "p-claim"}, owner_lookup=lambda c: None))

    def test_a_MISMATCH_refuses_and_names_both(self):
        with self.assertRaises(_rest.OwnerClaimMismatch) as caught:
            _rest.resolve_rest_identity("c1", {"person_id": "p-claim"},
                                        owner_lookup=lambda c: "p-owner")
        self.assertEqual("p-owner", caught.exception.owner)
        self.assertEqual("p-claim", caught.exception.claimed)

    def test_a_mismatch_composes_NOTHING(self):
        """The refusal must happen before any state is read.

        A stale tab pointed at another narrator, or a caller asserting an
        identity that is not theirs — guessing between them would put one
        narrator's onboarding questions in front of another narrator.
        """
        with self.assertRaises(_rest.OwnerClaimMismatch):
            _rest.onboarding_runtime("c1", {"person_id": "p-claim"},
                                     owner_lookup=lambda c: "p-owner",
                                     connect=self._must_not_connect)

    def _must_not_connect(self):
        raise AssertionError("storage was opened before the ownership "
                             "refusal — the mismatch must be decided first")

    def test_a_non_string_claim_is_not_a_claim(self):
        """Coercing one would manufacture a claim nobody made."""
        for bad in ({"person_id": 7}, {"person_id": ""}, {"person_id": None},
                    {"person_id": {"id": "x"}}, {"person_id": ["x"]},
                    {}, None, "not a dict", 3):
            with self.subTest(profile=bad):
                self.assertIsNone(_rest.resolve_rest_identity(
                    "c1", bad, owner_lookup=lambda c: None))

    def test_a_storage_fault_in_the_owner_lookup_does_NOT_fall_back(self):
        """Otherwise a fault promotes an unverified claim to authority.

        That is the exact inversion this module exists to prevent, and
        it would be reached by the most ordinary failure there is.
        """
        def boom(conv_id):
            raise sqlite3.OperationalError("database is locked")

        with self.assertRaises(sqlite3.OperationalError):
            _rest.resolve_rest_identity("c1", {"person_id": "p-claim"},
                                        owner_lookup=boom)


# ── identity facts ───────────────────────────────────────────────────
class IdentityFactTests(_Base):
    """`identity_complete` and the three facts travel together."""

    def test_the_REAL_name_dob_and_birthplace_reach_the_prompt(self):
        """The binding Step 5 requirement.

        `identity_complete=True` alone produces a prompt that says
        identity is complete and then renders "KNOWN IDENTITY FACTS: -
        none yet". The Boolean and the facts are read from four separate
        runtime keys; sending one without the others is a runtime that
        contradicts itself.
        """
        pid = self._person("Marvin Horne")
        runtime = self.runtime("c1", {"person_id": pid})
        self.assertTrue(runtime["identity_complete"])
        self.assertEqual("Marvin Horne", runtime["speaker_name"])
        self.assertEqual("1936-11-08", runtime["dob"])
        self.assertEqual("Spokane, Washington", runtime["pob"])

        text = self.compose(runtime)
        self.assertIn("Marvin Horne", text)
        self.assertIn("1936-11-08", text)
        self.assertIn("Spokane, Washington", text)
        self.assertNotIn("KNOWN IDENTITY FACTS:\n- none yet", text)

    def test_identity_complete_is_the_SERVER_predicate_not_an_inference(self):
        """Step 4 briefly inferred this from a composer payload and it
        was withdrawn. It comes from `identity_anchors_complete()`."""
        anchored = self._person("Anchored Narrator")
        sparse = self._person("Sparse Narrator", anchors=False)
        self.assertTrue(self.runtime("c1", {"person_id": anchored})
                        ["identity_complete"])
        self.assertFalse(self.runtime("c2", {"person_id": sparse})
                         .get("identity_complete", False))

    def test_a_partially_known_narrator_states_only_what_is_known(self):
        """Empty anchors are OMITTED, not sent as empty strings.

        `_known_identity_facts_block` renders whichever keys are present;
        an empty string would still be a key, and the block would have to
        decide what to print for it.
        """
        pid = self._person("Half Known", anchors=False)
        runtime = self.runtime("c1", {"person_id": pid})
        self.assertEqual("Half Known", runtime.get("speaker_name"))
        self.assertNotIn("dob", runtime)
        self.assertNotIn("pob", runtime)


# ── byte stability ───────────────────────────────────────────────────
class ByteStabilityTests(_Base):
    """Everything Step 5 has nothing to say about is UNCHANGED."""

    def baseline(self):
        return self.compose(None)

    def test_an_anonymous_call_is_byte_identical(self):
        self.assertEqual({}, self.runtime(None, None))
        self.assertEqual(self.baseline(),
                         self.compose(self.runtime(None, None) or None))

    def test_an_unowned_session_with_no_claim_is_byte_identical(self):
        self._session("c1", None)
        self.assertEqual({}, self.runtime("c1", None))
        self.assertEqual(self.baseline(),
                         self.compose(self.runtime("c1", None) or None))

    def test_an_unknown_person_id_is_byte_identical(self):
        """A claim naming nobody resolves to nothing, and says nothing."""
        self.assertEqual({}, self.runtime("c1", {"person_id": "ghost"}))
        self.assertEqual(self.baseline(),
                         self.compose(self.runtime("c1", {"person_id": "ghost"})
                                      or None))

    def test_a_COMPLETED_walk_adds_no_onboarding_section(self):
        """`completed` is terminal — that is what stops a narrator being
        walked through onboarding a second time."""
        pid = self._person()
        con = sqlite3.connect(str(self.db_path))
        try:
            con.execute("UPDATE profile_seed_onboarding SET status=? "
                        "WHERE person_id=?;", (_ps.STATUS_COMPLETED, pid))
            con.commit()
        finally:
            con.close()
        runtime = self.runtime("c1", {"person_id": pid})
        self.assertNotIn(KEY, runtime,
                         "a completed walk supplied an onboarding plan")
        self.assertTrue(runtime["identity_complete"],
                        "completing the walk did not un-know the narrator")

    def test_a_historical_narrator_gets_facts_but_no_walk(self):
        """No onboarding row, and none will be created.

        Knowing who someone is was never conditional on enrolling them.
        """
        pid = self._person("Historical Narrator")
        con = sqlite3.connect(str(self.db_path))
        try:
            con.execute("DELETE FROM profile_seed_onboarding WHERE person_id=?;",
                        (pid,))
            con.commit()
        finally:
            con.close()
        runtime = self.runtime("c1", {"person_id": pid})
        self.assertNotIn(KEY, runtime)
        self.assertEqual("Historical Narrator", runtime["speaker_name"])
        self.assertIsNone(_ps.read_row(self._open(), pid),
                          "the read CREATED an onboarding row")

    def _open(self):
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        self.addCleanup(con.close)
        return con


# ── the walk actually becomes reachable ──────────────────────────────
class ReachabilityTests(_Base):
    """The point of the whole work order, measured on the REST path."""

    def test_an_ACTIVE_narrator_is_asked_ONE_canonical_question(self):
        pid = self._person()
        runtime = self.runtime("c1", {"person_id": pid})
        plan = runtime[KEY]
        self.assertEqual("present", plan["action"])
        self.assertTrue(_ps.is_known_topic(plan["topic_id"]))

        text = self.compose(runtime)
        asked = [t.topic_id for t in _ps.TOPIC_REGISTRY
                 if t.question in text]
        self.assertEqual([plan["topic_id"]], asked,
                         "the prompt asks something other than exactly the "
                         "one planned topic")

    def test_the_read_does_NOT_advance_the_walk(self):
        """Two reads in a row plan the same topic at the same version.

        REST composes; it does not record a presentation. Step 6 owns
        advancement, and a read that moved the walk would consume topics
        every time a page refreshed.
        """
        pid = self._person()
        before = _ps.read_row(self._open(), pid)
        first = self.runtime("c1", {"person_id": pid})
        second = self.runtime("c1", {"person_id": pid})
        after = _ps.read_row(self._open(), pid)
        self.assertEqual(first[KEY], second[KEY])
        self.assertEqual(before["version"], after["version"],
                         "a READ moved the version")
        self.assertEqual(before["active_topic_id"], after["active_topic_id"])

    def test_a_storage_fault_is_VISIBLE_not_an_empty_plan(self):
        """Never converted into "this narrator has nothing to do".

        That is indistinguishable from a historical narrator, and would
        silently retire the walk for someone mid-way through it.
        """
        def boom():
            raise sqlite3.OperationalError("database is locked")

        with self.assertRaises(sqlite3.OperationalError):
            _rest.onboarding_runtime("c1", {"person_id": "p1"},
                                     owner_lookup=lambda c: "p1",
                                     connect=boom)

    def _open(self):
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        self.addCleanup(con.close)
        return con


class RouteStructureTests(unittest.TestCase):
    """What can be proven from `api.py`'s SOURCE, with no import.

    `api.py` imports torch at module scope, and torch is not available
    to any interpreter reachable from the agent sandbox. The behavioural
    tests below therefore cannot run there.

    *(The first version guarded this whole class on fastapi, which was
    the wrong reason — fastapi IS present in the sandbox and torch is
    not, so the guard named a dependency that was not the blocker. This
    lane has already shipped one artificial skip that hid thirty-five
    tests. Everything provable from source is separated out here so it
    runs everywhere, and the genuinely un-runnable part says plainly
    what it needs.)*
    """

    def source(self):
        return (_SERVER_CODE / "api" / "api.py").read_text(encoding="utf-8")

    def test_both_routes_call_the_same_helper(self):
        """Two ownership checks would be one defect with a worse blast
        radius than the renderer/predicate split already was."""
        import ast
        calls = [n for n in ast.walk(ast.parse(self.source()))
                 if isinstance(n, ast.Call)
                 and getattr(n.func, "id", "") == "_profile_seed_runtime"]
        self.assertEqual(2, len(calls),
                         "expected exactly two call sites, one per route")
        wheres = sorted(kw.value.value for c in calls for kw in c.keywords
                        if kw.arg == "where")
        self.assertEqual(["rest-chat", "rest-stream"], wheres)

    def test_the_helper_refuses_rather_than_falling_back(self):
        """Structural cover for what the sandbox cannot execute.

        Weaker than the behavioural tests below and not a replacement
        for them — it proves the refusals exist and name the right
        status codes, not that they fire.
        """
        import ast
        tree = ast.parse(self.source())
        helper = next(n for n in ast.walk(tree)
                      if isinstance(n, ast.FunctionDef)
                      and n.name == "_profile_seed_runtime")
        handlers = [h for h in ast.walk(helper)
                    if isinstance(h, ast.ExceptHandler)]
        self.assertEqual(2, len(handlers),
                         "expected exactly two handlers: mismatch and "
                         "storage fault")
        for handler in handlers:
            with self.subTest(handler=ast.dump(handler.type)[:40]):
                raises = [n for n in ast.walk(handler)
                          if isinstance(n, ast.Raise)]
                self.assertTrue(raises, "a handler swallowed its exception "
                                        "instead of refusing")
        codes = sorted(kw.value.value for h in handlers
                       for n in ast.walk(h) if isinstance(n, ast.Call)
                       for kw in n.keywords if kw.arg == "status_code")
        self.assertEqual([409, 503], codes)


@unittest.skipUnless(_HAS_API, f"needs api.api, which imports torch "
                               f"({_API_IMPORT_ERROR})")
class RouteContractTests(_Base):
    """Both REST routes behave identically, because they share one helper."""

    def test_the_helper_maps_a_mismatch_to_409_and_a_fault_to_503(self):
        import api.api as _api
        from fastapi import HTTPException

        def mismatch(*a, **k):
            raise _rest.OwnerClaimMismatch("c1", "p-owner", "p-claim")

        def fault(*a, **k):
            raise sqlite3.OperationalError("database is locked")

        orig = _rest.onboarding_runtime
        try:
            _rest.onboarding_runtime = mismatch
            with self.assertRaises(HTTPException) as c:
                _api._profile_seed_runtime("c1", {}, where="rest-chat")
            self.assertEqual(409, c.exception.status_code)
            self.assertEqual("SESSION_OWNER_MISMATCH",
                             c.exception.detail["error"])

            _rest.onboarding_runtime = fault
            with self.assertRaises(HTTPException) as c:
                _api._profile_seed_runtime("c1", {}, where="rest-chat")
            self.assertEqual(503, c.exception.status_code)
        finally:
            _rest.onboarding_runtime = orig

    def test_an_empty_runtime_becomes_None_not_an_empty_dict(self):
        """`{}` and `None` must be the SAME instruction to the composer.

        Passing `{}` would be "a runtime that says nothing", which is
        close to but not the same as no runtime — and this lane has
        already been bitten once by close-but-not-equal.
        """
        import api.api as _api
        orig = _rest.onboarding_runtime
        try:
            _rest.onboarding_runtime = lambda *a, **k: {}
            self.assertIsNone(
                _api._profile_seed_runtime("c1", {}, where="rest-chat"))
        finally:
            _rest.onboarding_runtime = orig


if __name__ == "__main__":
    unittest.main()
