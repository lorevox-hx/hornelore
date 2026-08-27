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

# ── HOW TO REFUSE THE SKIP, 2026-08-26 ────────────────────────────────
#
# `OK (skipped=6)` is not a pass, and the route classes are the ONLY
# place Step 5 touches the live transport — so the run that matters is
# the one where they do not skip.
#
#     HORNELORE_REQUIRE_ROUTE_TESTS=1 PYTHONPATH=server/code \
#         python3 -m unittest tests.test_profile_seed_rest_read_authority
#
# With that set, an un-importable `api.api` FAILS instead of skipping.
# It exists so acceptance can be run as a gate rather than as a report
# someone has to read the skip count out of.
#
# Stubbing torch and transformers to remove the skip here was considered
# and rejected: `api.py` needs `AutoModelForCausalLM` and `PeftModel` at
# import, and a stub deep enough to satisfy that is a stub deep enough
# to make these tests pass for reasons unrelated to the routes.
_REQUIRE_ROUTES = os.environ.get("HORNELORE_REQUIRE_ROUTE_TESTS") == "1"
if _REQUIRE_ROUTES and not _HAS_API:                         # pragma: no cover
    raise ImportError(
        "HORNELORE_REQUIRE_ROUTE_TESTS=1 but api.api could not be "
        f"imported: {_API_IMPORT_ERROR}. Route behaviour is the only "
        "part of Step 5 that touches the live transport; a skipped run "
        "is not evidence about it.")

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
class OtherRestCallerTests(_Base):
    """The two NON-NARRATOR callers of these routes. Both unchanged.

    ── FOUND BY AUDIT, NOT BY THE SUITE, 2026-08-26 ────────────────────

    *(Step 5's boundary names warmup and translation as prompts that
    must be preserved byte-for-byte, and nothing tested either. Both
    turned out to be safe, but "safe by reasoning" is what this lane
    keeps having to retract — `services/translation.py` posts to
    `/api/chat` on loopback for every memoir translation, so a mistake
    here would have silently attached a narrator's onboarding questions
    to a translation prompt, or refused the translation with a 409.)*
    """

    def test_a_TRANSLATION_shaped_request_resolves_to_nothing(self):
        """`services/translation.py` sends no conv_id and no PROFILE_JSON.

        Its system prompt is the translator instruction, which carries
        no `PROFILE_JSON:` blob, so `extract_profile_json_from_ui_system`
        yields `None` and there is no claim to resolve.
        """
        translator_system = (
            "You are a precise translator working on a personal memoir. "
            "Your only job is to translate the narrator's text.")
        profile_obj, _base = _pc.extract_profile_json_from_ui_system(
            translator_system)
        self.assertIsNone(profile_obj,
                          "the translator prompt parsed as a profile claim")
        self.assertEqual({}, self.runtime(None, profile_obj))
        self.assertEqual(self.compose(None),
                         self.compose(self.runtime(None, profile_obj) or None))

    def test_a_WARMUP_shaped_request_resolves_to_nothing(self):
        """`scripts/warm_llm.py` falls back to `/api/chat/stream`.

        A warmup that could 503 on a locked database would turn a
        transient fault into a failed start, and cold boot already takes
        four minutes.
        """
        for conv in (None, "", "   "):
            with self.subTest(conv_id=conv):
                self.assertEqual({}, self.runtime(conv, None))

    def test_the_warmup_ROUTE_never_resolves_authority(self):
        """`/api/warmup` must not have acquired this behaviour at all.

        It documents itself as skipping prompt composition, profile
        lookup and DB writes; adding a narrator resolution to it would
        contradict that and put storage on the startup path.
        """
        import ast
        src = (_SERVER_CODE / "api" / "api.py").read_text(encoding="utf-8")
        warmup = next(n for n in ast.walk(ast.parse(src))
                      if isinstance(n, ast.FunctionDef)
                      and n.name == "warmup_endpoint")
        called = {getattr(n.func, "id", "") for n in ast.walk(warmup)
                  if isinstance(n, ast.Call)}
        self.assertNotIn("_profile_seed_runtime", called,
                         "/api/warmup now resolves narrator authority")


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

    def test_a_REAL_answer_over_REST_is_never_recorded(self):
        """The Option B limitation, with an answer actually persisted.

        ── THE FIRST VERSION PROVED THE WEAKER PROPERTY, 2026-08-27 ────

        *(It did two reads with different conv_ids and asserted the topic
        had not moved — which is just "reads do not advance", already
        covered by `test_the_read_does_NOT_advance_the_walk`, wearing the
        name of the sharper claim. No user turn, no assistant turn, no
        answer of any kind was ever written.)*

        Now the narrator ANSWERS, through the real turn writer
        (`db.add_turn`, the sibling of the committed-turn path), and the
        durable Profile Seed row is shown to be untouched — then a NEW
        conversation asks the same topic again.

        The CONTROL at the bottom is what makes this the sharper claim
        rather than the weaker one: applying the disposition through the
        real writer DOES move the walk. So the topic staying open is a
        statement about REST not recording, not about the walk being
        incapable of moving.
        """
        pid = self._person("Answering Narrator")
        first = self.runtime("c-answer-1", {"person_id": pid})
        asked = first[KEY]["topic_id"]

        # The narrator answers, for real, on the same conversation.
        _db.add_turn("c-answer-1", "assistant",
                     _ps.topic(asked).question, person_id=pid)
        _db.add_turn("c-answer-1", "user",
                     "We moved to Minot when I was four, so I grew up there.",
                     person_id=pid)
        turns = self._turn_count("c-answer-1")
        self.assertEqual(2, turns, "the answer was not persisted, so this "
                                   "test proves nothing about recording")

        # The durable row has not noticed.
        row = _ps.read_row(self._open(), pid)
        self.assertEqual(
            _ps.UNANSWERED,
            _ps._coerce_topic_state(row["topic_state_json"])[asked],
            "the topic moved without a disposition being applied")

        # A NEW conversation — a returning narrator's next session.
        second = self.runtime("c-answer-2-fresh", {"person_id": pid})
        self.assertEqual(
            asked, second[KEY]["topic_id"],
            "Lori asks the same topic again in a new session, after the "
            "narrator has already answered it — the re-interrogation "
            "Principle 8 forbids")

        # ── CONTROL: the walk CAN move, when something records it ─────
        #
        # The version comes from `profile_seed_resolve()`, not from the
        # row read above. *(Using the row's version raised
        # `VersionConflict: expected 1, current is 2` — because REST
        # never materializes, so the row still said 1, while the first
        # real writer reconciles `pending -> active` and lands on 2. A
        # neat demonstration of the same gap this test is about: the
        # read path had resolved that state repeatedly and written none
        # of it.)*
        current = _db.profile_seed_resolve(pid)
        applied = _db.profile_seed_apply(
            pid, expected_version=current["version"],
            action=_ps.ADDRESSED, topic_id=asked)
        self.assertNotEqual(
            asked, applied["active_topic_id"],
            "applying a disposition did not advance the walk, so the "
            "assertions above describe a broken walk rather than an "
            "unrecorded answer")
        third = self.runtime("c-answer-3", {"person_id": pid})
        self.assertNotEqual(asked, third[KEY]["topic_id"],
                            "the recorded answer did not reach composition")

    def _turn_count(self, conv_id):
        con = sqlite3.connect(str(self.db_path))
        try:
            return con.execute(
                "SELECT COUNT(*) FROM turns WHERE conv_id=?;",
                (conv_id,)).fetchone()[0]
        finally:
            con.close()

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
        """Race ANCHORLESS -> ANCHORED, which is the damaging direction.

        ── THE RACE WAS POINTED THE WRONG WAY, 2026-08-26 ─────────────

        *(This started anchored and DELETED the anchors between the two
        reads. Removing the transaction then produced an idle plan and
        `{}` — no contradiction to detect — and the test excused itself
        with `if not runtime: return`. So it passed with the snapshot
        gone, and S5 was caught only by the STRUCTURAL check noticing
        `BEGIN DEFERRED` was missing. A structural guard reported as
        behavioural proof, which is the pattern this lane keeps
        repeating.*

        *Measured in the correct direction, with the transaction
        removed: `identity_complete=True`, `speaker_name` present, `dob`
        and `pob` GONE. That is the self-contradicting runtime the
        requirement exists to prevent, and it is what this test must
        fail on.)*

        The narrator starts with a name only. The anchors ARRIVE between
        the identity read and the resolve. One snapshot means both reads
        see the world before that write: still pending, no runtime. Two
        reads mean the resolver sees anchors the facts never saw.
        """
        pid = self._person("Racing Narrator", anchors=False)

        original = _ps._person_and_basics
        fired = {"n": 0}

        def racing(con, person_id):
            """Complete the anchors after the identity read."""
            result = original(con, person_id)
            if fired["n"] == 0:
                fired["n"] = 1
                other = sqlite3.connect(str(self.db_path))
                try:
                    other.execute(
                        "UPDATE people SET date_of_birth='1936-11-08', "
                        "place_of_birth='Spokane, Washington' WHERE id=?;",
                        (pid,))
                    other.commit()
                finally:
                    other.close()
            return result

        _ps._person_and_basics = racing
        try:
            runtime = self.runtime("c1", {"person_id": pid})
        finally:
            _ps._person_and_basics = original

        self.assertEqual(1, fired["n"],
                         "the race never fired, so this test proves nothing")
        # NO early return. A coherent old snapshot is the ONLY acceptable
        # answer; anything else is two moments stitched together.
        self.assertEqual(
            {}, runtime,
            "the runtime was assembled from two different moments: the "
            "resolver saw anchors that the identity read did not, so the "
            "narrator is reported identity-complete with facts missing")

    def test_the_race_helper_actually_changes_the_row(self):
        """Non-vacuity for the race above.

        If the injected write silently failed, the test would pass by
        describing a race that never happened.
        """
        pid = self._person("Control Narrator", anchors=False)
        con = sqlite3.connect(str(self.db_path))
        try:
            con.execute("UPDATE people SET date_of_birth='1936-11-08', "
                        "place_of_birth='Spokane, Washington' WHERE id=?;",
                        (pid,))
            con.commit()
        finally:
            con.close()
        runtime = self.runtime("c1", {"person_id": pid})
        self.assertTrue(runtime, "completing the anchors did not start the "
                                 "walk, so the race's write is inert and the "
                                 "test above proves nothing")
        self.assertTrue(runtime["identity_complete"])
        self.assertIn("dob", runtime)
        self.assertIn("pob", runtime)

    def test_a_storage_fault_is_not_MASKED_by_the_rollback(self):
        """The fault the caller must see is the one they get.

        *(Unguarded, a `ROLLBACK` failing inside `finally` REPLACES the
        exception passing through it — so "database is locked" would
        reach the operator as a rollback error from a line where nothing
        went wrong. Storage faults are not absence, and they are also
        not to be overwritten by their own cleanup.)*
        """
        class Failing:
            """Raises on the resolve, then again on the ROLLBACK."""

            def __init__(self, real):
                self._real = real

            def execute(self, sql, *a):
                if sql.strip().upper().startswith("ROLLBACK"):
                    raise sqlite3.OperationalError("rollback failed too")
                return self._real.execute(sql, *a)

            def __getattr__(self, name):
                return getattr(self._real, name)

        real = sqlite3.connect(str(self.db_path))
        real.row_factory = sqlite3.Row
        self.addCleanup(real.close)

        original = _ps.resolve_effective

        def boom(con, person_id, *, now):
            raise sqlite3.OperationalError("database is locked")

        _ps.resolve_effective = boom
        try:
            with self.assertRaises(sqlite3.OperationalError) as caught:
                _rest.onboarding_runtime(
                    "c1", {"person_id": "p1"},
                    owner_lookup=lambda c: "p1",
                    connect=lambda: Failing(real))
        finally:
            _ps.resolve_effective = original

        self.assertIn("database is locked", str(caught.exception),
                      "the rollback's own failure replaced the storage fault "
                      "the caller needed to see")

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

    #: The EXACT mapping, stated once and asserted as a whole.
    #:
    #: An identity refusal tells the caller to re-select the narrator; a
    #: storage fault tells them to try again. Getting these the wrong way
    #: round sends the reader to fix the wrong thing.
    EXPECTED_STATUS = {
        "ContradictoryClaim": 409,
        "OwnerClaimMismatch": 409,
        "Error": 503,                 # `sqlite3.Error`
    }

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

    def test_the_helper_RETURNS_what_it_resolved(self):
        """A helper that resolves and then returns a constant is a
        silent no-op with a working refusal path.

        *(Found by mutation S9, which replaced `return runtime or None`
        with `return None` and SURVIVED. Every other guard still held:
        ownership still refused, the route still bound the value, the
        value still reached `runtime71=`. It was just always `None`, so
        no narrator would ever be asked anything and the whole step
        would be inert. The wiring test could not see it because it
        follows the NAME, and the route-behaviour tests that would have
        caught it are the ones that skip without the real stack.)*
        """
        import ast
        helper = next(n for n in ast.walk(ast.parse(self.source()))
                      if isinstance(n, ast.FunctionDef)
                      and n.name == "_profile_seed_runtime")
        # The success path — returns not inside an `except` — must
        # mention the name the resolution was bound to.
        handled = {id(n) for h in ast.walk(helper)
                   if isinstance(h, ast.ExceptHandler)
                   for n in ast.walk(h)}
        returns = [n for n in ast.walk(helper)
                   if isinstance(n, ast.Return) and id(n) not in handled]
        self.assertTrue(returns, "the helper has no success-path return")
        bound = {t.id for n in ast.walk(helper) if isinstance(n, ast.Assign)
                 for t in n.targets if isinstance(t, ast.Name)}
        self.assertTrue(bound, "the helper binds nothing, so it cannot be "
                               "returning what it resolved")
        for ret in returns:
            with self.subTest(line=ret.lineno):
                names = {n.id for n in ast.walk(ret)
                         if isinstance(n, ast.Name)}
                self.assertTrue(
                    names & bound,
                    f"the return at line {ret.lineno} does not reference the "
                    "resolved value — the helper discards what it computed")

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
        # ── AN EXACT MAPPING, NOT A MULTISET, 2026-08-26 ──────────────
        #
        # *(This compared `sorted(codes) == [409, 409, 503]`. A multiset
        # says how many of each code exist and NOTHING about which
        # exception raises which — so swapping `ContradictoryClaim` to
        # 503 and `sqlite3.Error` to 409 produced the same sorted list
        # and passed. A caller would have been told "Lori cannot reach
        # her notes" for a contradictory payload, and "reload and select
        # the narrator" for a locked database: both refusals still fire,
        # both are the wrong answer, and the test could not tell.)*
        actual = {}
        for handler in handlers:
            names = {n.attr for n in ast.walk(handler.type)
                     if isinstance(n, ast.Attribute)} or {
                n.id for n in ast.walk(handler.type) if isinstance(n, ast.Name)}
            codes = {kw.value.value for n in ast.walk(handler)
                     if isinstance(n, ast.Call)
                     for kw in n.keywords if kw.arg == "status_code"}
            self.assertEqual(1, len(codes),
                             f"handler for {sorted(names)} raises "
                             f"{sorted(codes)} — one refusal, one code")
            for name in names:
                actual[name] = codes.pop() if codes else None
                codes = {actual[name]}

        self.assertEqual(self.EXPECTED_STATUS, actual,
                         "the exception-to-status mapping is wrong: an "
                         "identity refusal and a storage fault mean "
                         "different things to the caller and must not be "
                         "interchangeable")


@unittest.skipUnless(_HAS_API, _API_SKIP_REASON)
class RouteBehaviourTests(_Base):
    """The ROUTES themselves refuse — `chat()` and `chat_stream()`.

    *(`RouteContractTests` calls `_profile_seed_runtime()` directly, so
    even with zero skips it never exercised a route. A helper that
    refuses correctly proves nothing about a route that might not call
    it, might call it after loading the model, or might swallow it. This
    class calls the route functions.)*

    `_load_model`, the composer and the generator are all replaced with
    tripwires: reaching any of them during a refusal is a failure, which
    is how "the refusal happens FIRST" is proven rather than asserted.
    """

    def setUp(self):
        super().setUp()
        import api.api as api_module
        self.api = api_module
        self.tripped = []
        self.exercised = set()

        def tripwire(name):
            def _fail(*a, **k):
                self.tripped.append(name)
                raise AssertionError(f"{name} was reached during a refusal")
            return _fail

        for name in ("_load_model", "compose_prompt_sections",
                     "_generate_text"):
            original = getattr(self.api, name)
            setattr(self.api, name, tripwire(name))
            self.addCleanup(setattr, self.api, name, original)

    def _req(self, profile_json, conv_id):
        """A request body carrying a PROFILE_JSON claim, as the browser sends.

        `conv_id` is REQUIRED and must be unique per route within a
        test — see `_assert_refused`.
        """
        import json as _json
        system = ("You are Lorevox.\nPROFILE_JSON:"
                  + _json.dumps(profile_json))
        return self.api._ChatReq(
            messages=[self.api.ChatTurn(role="system", content=system),
                      self.api.ChatTurn(role="user", content="Hello")],
            conv_id=conv_id)

    def _assert_refused(self, route, profile_json, *, status, error,
                        owner=None, fault=False):
        """Drive ONE route and assert it refused before doing any work.

        ── ONE CONV_ID PER ROUTE, 2026-08-27 ──────────────────────────

        *(This hard-coded `c-route` for both the session insert and the
        request. The `both routes` tests loop over `chat` and
        `chat_stream`, so the owner-mismatch case inserted the SAME
        `conv_id` twice inside one test and the second iteration died on
        `UNIQUE constraint failed: sessions.conv_id` BEFORE reaching
        `chat_stream()`. Reproduced directly. The test was named "both
        routes" and exercised one — and because the failure lands in
        setup rather than in an assertion, a reader seeing it go red on
        WSL would have gone looking for a route bug that was not
        there.)*
        """
        from fastapi import HTTPException
        conv_id = self._conv_for(route)
        if owner is not None:
            self._session(conv_id, owner)
        if fault:
            self._break_storage()
        with self.assertRaises(HTTPException) as caught:
            route(self._req(profile_json, conv_id))
        self.assertEqual(status, caught.exception.status_code)
        self.assertEqual(error, caught.exception.detail["error"])
        self.assertEqual([], self.tripped,
                         "the refusal happened AFTER the model, composer or "
                         "generator was reached")
        self.exercised.add(route.__name__)

    @staticmethod
    def _conv_for(route):
        """One conv_id per route. Sessions are keyed by conv_id, so two
        routes sharing one is a primary-key collision waiting for the
        second iteration."""
        return f"c-route-{route.__name__}"

    def _break_storage(self):
        """Patch ONCE per test, restore to the true original.

        *(Patching inside a loop captured the already-patched function as
        `original` on the second pass. LIFO cleanup happened to unwind it
        correctly, which is worse than being wrong: it worked by accident
        and would stop working the moment the order changed.)*
        """
        if getattr(self, "_storage_broken", False):
            return
        self._storage_broken = True
        original = _rest.onboarding_runtime
        _rest.onboarding_runtime = self._raise_locked
        self.addCleanup(setattr, _rest, "onboarding_runtime", original)

    def assertBothRoutesExercised(self):
        """A `both routes` test must actually enter both routes.

        Without this, anything that fails during setup on the second
        iteration leaves the first route tested, the second untouched,
        and the test name lying about it.
        """
        self.assertEqual({"chat", "chat_stream"}, self.exercised,
                         "this test claims to cover both REST routes but "
                         f"only entered {sorted(self.exercised)}")

    @staticmethod
    def _raise_locked(*a, **k):
        raise sqlite3.OperationalError("database is locked")

    # ── both routes, all three refusals ─────────────────────────────
    def test_a_contradictory_claim_is_refused_by_both_routes(self):
        for route in (self.api.chat, self.api.chat_stream):
            with self.subTest(route=route.__name__):
                self.tripped.clear()
                self._assert_refused(
                    route, {"person_id": "p-a", "personId": "p-b"},
                    status=409, error="CONTRADICTORY_NARRATOR_CLAIM")
        self.assertBothRoutesExercised()

    def test_an_owner_mismatch_is_refused_by_both_routes(self):
        """*(The owned session used to be inserted INSIDE the loop, on a
        conv_id shared by both routes, so the second iteration died on
        `UNIQUE constraint failed: sessions.conv_id` before
        `chat_stream()` was ever entered. One session, created once,
        before the loop.)*"""
        pid = self._person("Route Narrator")
        for route in (self.api.chat, self.api.chat_stream):
            conv_id = self._conv_for(route)
            self._session(conv_id, pid)
        for route in (self.api.chat, self.api.chat_stream):
            with self.subTest(route=route.__name__):
                self.tripped.clear()
                self._assert_refused(
                    route, {"person_id": "p-claim"},
                    status=409, error="SESSION_OWNER_MISMATCH")
        self.assertBothRoutesExercised()

    def test_a_storage_fault_is_refused_by_both_routes(self):
        for route in (self.api.chat, self.api.chat_stream):
            with self.subTest(route=route.__name__):
                self.tripped.clear()
                self._assert_refused(
                    route, {"person_id": "p-any"},
                    status=503, error="PROFILE_SEED_UNAVAILABLE", fault=True)
        self.assertBothRoutesExercised()

    def test_the_tripwires_ARE_reachable_on_a_non_refusing_turn(self):
        """Non-vacuity for every assertion above.

        If the tripwires could never fire — wrong attribute names, a
        route that returns before reaching them — then `self.tripped ==
        []` would be true for reasons having nothing to do with the
        refusal happening first.
        """
        pid = self._person("Ordinary Narrator")
        for route in (self.api.chat, self.api.chat_stream):
            conv_id = self._conv_for(route)
            self._session(conv_id, pid)
            with self.subTest(route=route.__name__):
                self.tripped.clear()
                with self.assertRaises(AssertionError) as caught:
                    route(self._req({"person_id": pid}, conv_id))
                self.assertIn("_load_model", str(caught.exception))
                self.assertEqual(["_load_model"], self.tripped,
                                 "the non-refusing turn did not reach the "
                                 "model, so the refusal tests' "
                                 "`tripped == []` proves nothing for this "
                                 "route")


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
