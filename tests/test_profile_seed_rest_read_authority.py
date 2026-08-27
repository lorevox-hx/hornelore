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

#: Can `api.api` be imported at all? It pulls in heavy dependencies at
#: module scope, and which one is missing DEPENDS ON THE ENVIRONMENT.
#:
#: *(This named torch, because torch was what the agent sandbox was
#: missing. In a review clone the import failed on fastapi FIRST, so the
#: decorator read "needs api.api, which imports torch
#: (ModuleNotFoundError: No module named 'fastapi')" — a skip reason
#: contradicting itself in one line. An earlier guard in this lane named
#: fastapi while the real blocker was torch, which is the same mistake
#: with the names swapped. Hard-coding ANY dependency here is guessing;
#: the captured exception is the only thing that is true everywhere.)*
try:
    import api.api as _api_module                            # noqa: F401
    _HAS_API = True
    _API_IMPORT_ERROR = ""
except Exception as _exc:                                    # pragma: no cover
    _HAS_API = False
    _API_IMPORT_ERROR = f"{type(_exc).__name__}: {_exc}"

_API_SKIP_REASON = (f"needs api.api, which could not be imported here "
                    f"({_API_IMPORT_ERROR}). Route behaviour must be run "
                    f"on the real stack before Step 5 is accepted.")

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
        # The anchorless narrator is held at `pending`, so no runtime is
        # supplied at all — which is a STRONGER guarantee than
        # `identity_complete=False`, and the reason this asserts on the
        # whole runtime rather than the one key.
        self.assertEqual({}, self.runtime("c2", {"person_id": sparse}))

    def test_a_partially_known_narrator_states_only_what_is_known(self):
        """Empty anchors are OMITTED, not sent as empty strings.

        `_known_identity_facts_block` renders whichever keys are present;
        an empty string would still be a key, and the block would have
        to decide what to print for it.

        Exercised through `_identity_facts` directly, because a narrator
        missing an anchor is held at `pending` and supplies no runtime
        at all — the composed-prompt route cannot reach this.
        """
        facts = _rest._identity_facts(
            {"display_name": "Half Known", "date_of_birth": "",
             "place_of_birth": None}, {})
        self.assertEqual({"speaker_name": "Half Known"}, facts)

    def test_identity_facts_travel_ONLY_with_an_active_walk(self):
        """The Step 5 boundary, as a property rather than three cases.

        *(I first supplied facts to any narrator who had them. That is
        defensible on its own merits and was not Step 5's call to make:
        supplying ANY runtime dict makes the composer emit its whole
        runtime block, so historical and completed prompts grew by
        17,760 characters — measured — against a boundary that preserves
        them byte-for-byte.)*
        """
        # `pending` is deliberately NOT in this list, and the reason is
        # worth stating: writing `status='pending'` onto an ANCHORED
        # narrator does not produce a pending narrator. The resolver
        # recomputes status from the identity anchors, so the row
        # promotes straight back to `active` — the stored status is not
        # authoritative on its own. A real pending narrator is one whose
        # anchors are missing, covered by
        # `test_a_PENDING_narrator_is_byte_identical`.
        #
        # *(This test asserted it anyway and failed, which is the fixture
        # being unrealistic rather than the code being wrong — but a
        # fixture that cannot occur would have been a permanent false
        # alarm for whoever met it next.)*
        for status in (_ps.STATUS_PAUSED, _ps.STATUS_COMPLETED):
            with self.subTest(status=status):
                pid = self._person(f"Narrator {status}")
                self._set_status(pid, status)
                self.assertEqual({}, self.runtime("c1", {"person_id": pid}))

    def test_forcing_pending_on_an_anchored_narrator_RESOLVES_BACK(self):
        """The behaviour the list above had to work around, pinned.

        Left as a test rather than a comment because it is the reason
        the list is short, and a future reader adding `pending` back
        should meet this instead of a puzzling failure.
        """
        pid = self._person("Anchored Narrator")
        self._set_status(pid, _ps.STATUS_PENDING)
        self.assertIn(KEY, self.runtime("c1", {"person_id": pid}),
                      "the resolver stopped recomputing status from the "
                      "anchors — the comment above is now wrong")

    def _set_status(self, pid, status):
        con = sqlite3.connect(str(self.db_path))
        try:
            con.execute("UPDATE profile_seed_onboarding SET status=? "
                        "WHERE person_id=?;", (status, pid))
            con.commit()
        finally:
            con.close()


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

    def test_a_COMPLETED_walk_is_byte_identical_with_a_KNOWN_narrator(self):
        """A POPULATED identity, not an empty fixture.

        *(The first version asserted only that no onboarding key was
        supplied, and separately that `identity_complete` was True — so
        it PASSED while the prompt grew by 17,760 characters. A narrator
        with no name would have hidden the defect entirely; this one has
        a name, a DOB and a birthplace, which is the case that exposes
        it.)*
        """
        pid = self._person("Completed Narrator")
        self._set_status(pid, _ps.STATUS_COMPLETED)
        runtime = self.runtime("c1", {"person_id": pid})
        self.assertEqual({}, runtime,
                         "a completed walk supplied runtime state")
        self.assertEqual(self.baseline(), self.compose(runtime or None))

    def test_a_HISTORICAL_narrator_is_byte_identical_with_a_KNOWN_identity(self):
        """No onboarding row, and none is created.

        Supplying this narrator's facts would be a defensible prompt
        change on its own merits — and it is not Step 5's to make, whose
        boundary preserves historical prompts byte-for-byte. Supplying
        ANY runtime dict makes the composer emit its whole runtime
        block, so "just the three facts" is never just three facts.
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
        self.assertEqual({}, runtime)
        self.assertEqual(self.baseline(), self.compose(runtime or None))
        self.assertIsNone(_ps.read_row(self._open(), pid),
                          "the read CREATED an onboarding row")

    def test_a_PENDING_narrator_is_byte_identical(self):
        """Anchors incomplete, so the walk must not begin — Phase 0
        pinned that as correct, not part of the reachability defect."""
        pid = self._person("Anchorless Narrator", anchors=False)
        runtime = self.runtime("c1", {"person_id": pid})
        self.assertEqual({}, runtime)
        self.assertEqual(self.baseline(), self.compose(runtime or None))

    def test_the_preserved_cases_are_measured_against_a_POPULATED_narrator(self):
        """Non-vacuity for the three tests above.

        Each asserts equality against a baseline. If the fixtures were
        empty, or the composer ignored runtime entirely, they would pass
        for the wrong reason forever. An ACTIVE narrator built the same
        way must CHANGE the prompt.
        """
        pid = self._person("Active Narrator")
        runtime = self.runtime("c1", {"person_id": pid})
        self.assertTrue(runtime, "the active fixture supplied nothing, so the "
                                 "byte-equality tests above prove nothing")
        self.assertNotEqual(self.baseline(), self.compose(runtime))

    def _set_status(self, pid, status):
        con = sqlite3.connect(str(self.db_path))
        try:
            con.execute("UPDATE profile_seed_onboarding SET status=? "
                        "WHERE person_id=?;", (status, pid))
            con.commit()
        finally:
            con.close()

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


class ClaimScopeTests(_Base):
    """`person_id` is the claim. Aliases are read only to catch conflicts."""

    def test_only_the_specified_key_satisfies_a_claim(self):
        """*(`personId` and `active_person_id` used to satisfy it on
        their own, widening an identity boundary the transport map
        scopes to one key.)*"""
        for alias in ("personId", "active_person_id"):
            with self.subTest(alias=alias):
                self.assertIsNone(_rest.resolve_rest_identity(
                    "c1", {alias: "p-alias"}, owner_lookup=lambda c: None),
                    f"{alias} satisfied a claim by itself")

    def test_a_CONTRADICTORY_payload_is_refused_not_silently_resolved(self):
        """First-match was a coin toss deciding whose childhood is asked about."""
        for payload in ({"person_id": "p-a", "personId": "p-b"},
                        {"person_id": "p-a", "active_person_id": "p-b"},
                        {"personId": "p-a", "active_person_id": "p-b"}):
            with self.subTest(payload=payload):
                with self.assertRaises(_rest.ContradictoryClaim):
                    _rest.resolve_rest_identity("c1", payload,
                                                owner_lookup=lambda c: None)

    def test_a_contradiction_composes_NOTHING(self):
        """Refused before storage is opened, like an owner mismatch.

        Same property, and it needs its own test: the two refusals are
        raised from different helpers, so covering one says nothing
        about the other.
        """
        def must_not_connect():
            raise AssertionError("storage was opened before the "
                                 "contradictory-claim refusal")

        with self.assertRaises(_rest.ContradictoryClaim):
            _rest.onboarding_runtime("c1", {"person_id": "p-a",
                                            "personId": "p-b"},
                                     owner_lookup=lambda c: None,
                                     connect=must_not_connect)

    def test_agreeing_aliases_are_not_a_contradiction(self):
        """Redundant is not conflicting — refusing here would break
        callers who send both keys with the same value."""
        self.assertEqual("p-a", _rest.resolve_rest_identity(
            "c1", {"person_id": "p-a", "personId": "p-a",
                   "active_person_id": "p-a"},
            owner_lookup=lambda c: None))


class SnapshotConsistencyTests(_Base):
    """Identity facts and effective state come from ONE snapshot.

    *(They were two independent reads of `people`. Review reproduced a
    concurrent update between them and got `identity_complete=True` with
    a name but no DOB and no birthplace — the self-contradicting runtime
    the requirement exists to prevent, assembled from two moments that
    never both existed.)*
    """

    def test_a_write_BETWEEN_the_two_reads_cannot_split_the_runtime(self):
        pid = self._person("Snapshot Narrator")

        original = _ps._person_and_basics
        state = {"n": 0}

        def racing(con, person_id):
            """Erase the anchors after the identity read, before resolve."""
            result = original(con, person_id)
            if state["n"] == 0:
                state["n"] = 1
                other = sqlite3.connect(str(self.db_path))
                try:
                    other.execute(
                        "UPDATE people SET date_of_birth='', "
                        "place_of_birth='' WHERE id=?;", (pid,))
                    other.commit()
                finally:
                    other.close()
            return result

        _ps._person_and_basics = racing
        try:
            runtime = self.runtime("c1", {"person_id": pid})
        finally:
            _ps._person_and_basics = original

        self.assertEqual(1, state["n"], "the race never fired, so this "
                                        "test proves nothing")
        if not runtime:
            return   # resolved consistently as pending — also coherent
        self.assertTrue(runtime["identity_complete"])
        for key in ("speaker_name", "dob", "pob"):
            self.assertIn(key, runtime,
                          f"identity_complete is True but {key} is missing — "
                          "the runtime was assembled from two different "
                          "moments")

    def test_the_read_opens_a_transaction_and_rolls_it_back(self):
        """Structural: the snapshot is a transaction, and it never commits.

        *(First written against every string in the module and it FAILED
        — on "committed-turn path" in the docstring. Guard-on-prose, the
        eighth time in this lane. It reads SQL passed to `execute()`
        now, which is the only place a COMMIT could actually be.)*
        """
        import ast
        src = (_SERVER_CODE / "api" / "services"
               / "profile_seed_rest.py").read_text(encoding="utf-8")
        sql = []
        for node in ast.walk(ast.parse(src)):
            if (isinstance(node, ast.Call)
                    and getattr(node.func, "attr", "") == "execute"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                sql.append(node.args[0].value)
        self.assertTrue(sql, "no execute() calls found, so this proves "
                             "nothing about the transaction")
        self.assertIn("BEGIN DEFERRED;", sql)
        self.assertIn("ROLLBACK;", sql)
        for statement in sql:
            with self.subTest(sql=statement):
                self.assertNotIn("COMMIT", statement.upper(),
                                 "the read path commits")


class PersonIdTests(_Base):
    """`person_id` reaches the runtime, because a layer depends on it."""

    def test_the_resolved_person_id_is_supplied(self):
        """Without it the composer's person-dependent memory layer is
        skipped, so the narrator is named in the prompt and has no
        memory attached to them."""
        pid = self._person("Named Narrator")
        runtime = self.runtime("c1", {"person_id": pid})
        self.assertEqual(pid, runtime["person_id"])

    def test_the_supplied_id_is_the_RESOLVED_one_not_the_claim(self):
        """An unowned session's claim resolves to itself; an owned one
        resolves to the owner. Supplying the claim would re-introduce
        the payload as authority one key later."""
        pid = self._person("Owned Narrator")
        self._session("c-owned", pid)
        runtime = _rest.onboarding_runtime("c-owned", None,
                                           owner_lookup=lambda c: pid)
        self.assertEqual(pid, runtime["person_id"])

    def test_the_composer_ACTS_on_the_person_id(self):
        """Non-vacuity: prove the key is not merely present.

        A key nothing reads would pass the assertions above forever.
        """
        pid = self._person("Memory Narrator")
        runtime = self.runtime("c1", {"person_id": pid})
        with_id = self.compose(runtime)
        without = self.compose({k: v for k, v in runtime.items()
                                if k != "person_id"})
        self.assertNotEqual(with_id, without,
                            "removing person_id changed nothing, so the "
                            "composer is not reading it and this "
                            "requirement is unmet")


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

    def test_each_route_PASSES_the_resolved_runtime_to_the_composer(self):
        """Discarding the result must fail this.

        *(The first version only COUNTED two `_profile_seed_runtime`
        calls. A route that called the helper and then threw the value
        away — or passed `runtime71=None` beside it — would have passed,
        which is precisely the defect worth catching: the ownership
        refusal would still fire, and the onboarding state would never
        reach the prompt.)*

        This follows the value: the helper's result must be bound to a
        name, and that same name must be what `runtime71=` receives in
        the same function.
        """
        import ast
        tree = ast.parse(self.source())
        routes = {}
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef):
                continue
            bound = {t.id for node in ast.walk(fn)
                     if isinstance(node, ast.Assign)
                     and isinstance(node.value, ast.Call)
                     and getattr(node.value.func, "id", "") == "_profile_seed_runtime"
                     for t in node.targets if isinstance(t, ast.Name)}
            if not bound:
                continue
            passed = {kw.value.id for node in ast.walk(fn)
                      if isinstance(node, ast.Call)
                      and getattr(node.func, "id", "") == "compose_prompt_sections"
                      for kw in node.keywords
                      if kw.arg == "runtime71" and isinstance(kw.value, ast.Name)}
            routes[fn.name] = (bound, passed)

        self.assertEqual({"chat", "chat_stream"}, set(routes),
                         "expected exactly the two REST chat routes to "
                         "resolve onboarding state")
        for name, (bound, passed) in routes.items():
            with self.subTest(route=name):
                self.assertTrue(
                    bound & passed,
                    f"{name}() calls _profile_seed_runtime but the value it "
                    "binds is not what reaches compose_prompt_sections' "
                    "runtime71 — the result is being discarded")

    def test_authority_is_resolved_BEFORE_the_model_loads(self):
        """Otherwise a model-loading failure masks the 409 or 503.

        Line order inside each route, because that IS the property: a
        refusal that runs after several gigabytes of weights cannot be
        guaranteed to run at all.
        """
        import ast
        tree = ast.parse(self.source())
        for fn in ast.walk(tree):
            if not (isinstance(fn, ast.FunctionDef)
                    and fn.name in ("chat", "chat_stream")):
                continue
            resolve = min((n.lineno for n in ast.walk(fn)
                           if isinstance(n, ast.Call)
                           and getattr(n.func, "id", "") == "_profile_seed_runtime"),
                          default=None)
            load = min((n.lineno for n in ast.walk(fn)
                        if isinstance(n, ast.Call)
                        and getattr(n.func, "id", "") == "_load_model"),
                       default=None)
            with self.subTest(route=fn.name):
                self.assertIsNotNone(resolve, "no authority resolution")
                self.assertIsNotNone(load, "no model load — has this route "
                                           "changed shape?")
                self.assertLess(resolve, load,
                                f"{fn.name}() loads the model before "
                                "resolving who the turn is for")

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

        # ── DERIVED, NOT COUNTED, 2026-08-26 ───────────────────────────
        #
        # *(This asserted "exactly two handlers". That is a count, and a
        # count cannot tell you WHICH exceptions are handled — so when
        # `ContradictoryClaim` was added to the service and never wired
        # into the route, a contradictory payload escaped as an
        # unhandled 500 and this test PASSED. Worse, the assertion would
        # have BLOCKED the fix: adding the third handler makes a
        # hard-coded 2 fail. A test that both hides a defect and
        # obstructs its repair is worse than no test.)*
        #
        # Every refusal the SERVICE defines must have a handler here.
        # New refusals arrive from the service, so the requirement is
        # read from there rather than restated.
        refusals = {name for name in _rest.__all__
                    if isinstance(getattr(_rest, name, None), type)
                    and issubclass(getattr(_rest, name), Exception)}
        self.assertTrue(refusals, "no refusal classes exported, so this "
                                  "check proves nothing")
        handled = {n.attr for h in handlers if h.type is not None
                   for n in ast.walk(h.type) if isinstance(n, ast.Attribute)}
        missing = refusals - handled
        self.assertEqual(set(), missing,
                         f"the service defines {sorted(missing)} but the "
                         "route helper does not handle it — it would escape "
                         "as an unhandled 500")
        for handler in handlers:
            with self.subTest(handler=ast.dump(handler.type)[:40]):
                raises = [n for n in ast.walk(handler)
                          if isinstance(n, ast.Raise)]
                self.assertTrue(raises, "a handler swallowed its exception "
                                        "instead of refusing")
        codes = sorted(kw.value.value for h in handlers
                       for n in ast.walk(h) if isinstance(n, ast.Call)
                       for kw in n.keywords if kw.arg == "status_code")
        # One 409 per identity refusal the service defines, plus one 503
        # for the storage fault. `sqlite3.Error` is not ours, so it is
        # not in `refusals` and is counted separately.
        self.assertEqual([409] * len(refusals) + [503], sorted(codes),
                         "every identity refusal must be a 409 and the "
                         "storage fault a 503")


@unittest.skipUnless(_HAS_API, _API_SKIP_REASON)
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
