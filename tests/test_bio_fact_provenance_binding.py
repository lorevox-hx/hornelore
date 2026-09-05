"""Phase 5A — bio-fact provenance comes from the committed turn.

    PYTHONPATH=server/code .venv/bin/python -m unittest \\
        tests.test_bio_fact_provenance_binding

`WO-LORI-ARCHIVE-TO-MEMOIR-02` Phase 5A.

── THE DEFECT THIS EXISTS TO PIN ─────────────────────────────────────

`run_field_extraction` routed bio facts with
`session_id=getattr(req, "conv_id", None)` and
`turn_id=getattr(req, "turn_id", None)`. **Neither `conv_id` nor
`turn_id` is a field on `ExtractFieldsRequest`** — verified by listing
`model_fields` — so production wrote `session_id: None, turn_id: None`
on every routed fact. Meanwhile `session_id` *is* a real field on that
model, sitting unused, because the caller asked for a name that does not
exist.

**And the suite could not see it.** `tests/test_bio_fact_router.py` calls
the router directly with `session_id="s1", turn_id="t1"` and asserts
those values persisted. The fixture supplied the exact property being
proven, and the production caller — which supplied neither — was never
exercised. Instance 9 in `docs/TESTING-DOCTRINE.md`, and the first one
found in the wild rather than by mutation.

── WHY THESE TESTS START WHERE THEY DO ───────────────────────────────

**A direct `route_extraction_to_bio_facts(session_id=..., turn_id=...)`
call is NOT evidence for production provenance** and must never again be
counted as such. Every test here enters at the completed-turn extraction
boundary, where a `_Claim` exists, and reads what the router actually
received.

The governing rule: **extraction may interpret meaning; it may not
decide which committed turn the meaning came from.**
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "server" / "code")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api.routers import extract as EX          # noqa: E402
from api.services import turn_extraction as TE  # noqa: E402

#: Wording the SHIPPED kinship guard accepts, so these tests exercise
#: PROVENANCE rather than lexical coverage.
#:
#: The first draft said "My daddy worked at the mill" and every routing
#: test failed with zero items: the guard does not recognise `daddy` as a
#: parent cue, so the item is quarantined `relationship_unstated` and
#: never reaches the router at all. That is a real Phase 5B gap, measured
#: at the production boundary and pinned in
#: `LexicalGapIsRealAndMeasured` below -- but it is not what this file is
#: for, and leaving it here would have made a provenance suite fail for a
#: vocabulary reason.
ACCEPTED_WORDING = "My father Walter worked at the mill."
DADDY_WORDING = "My daddy worked at the mill."


class TheRequestNeverCarriedProvenance(unittest.TestCase):
    """The premise, measured against the shipped model."""

    def test_the_request_model_has_no_conv_id_or_turn_id(self):
        f = (list(EX.ExtractFieldsRequest.model_fields)
             if hasattr(EX.ExtractFieldsRequest, "model_fields")
             else list(EX.ExtractFieldsRequest.__fields__))
        self.assertNotIn("conv_id", f)
        self.assertNotIn("turn_id", f)

    def test_but_session_id_is_a_real_field_that_was_being_ignored(self):
        """The sharpest part: the right id was there and unused."""
        f = (list(EX.ExtractFieldsRequest.model_fields)
             if hasattr(EX.ExtractFieldsRequest, "model_fields")
             else list(EX.ExtractFieldsRequest.__fields__))
        self.assertIn("session_id", f)

    def test_no_executable_line_reads_provenance_off_the_request(self):
        """Comments may quote the old code; executable lines may not."""
        import ast
        src = (ROOT / "server" / "code" / "api" / "routers"
               / "extract.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for n in ast.walk(tree):
            if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef,
                              ast.AsyncFunctionDef)):
                b = getattr(n, "body", None)
                if (b and isinstance(b[0], ast.Expr)
                        and isinstance(b[0].value, ast.Constant)
                        and isinstance(b[0].value.value, str)):
                    if len(b) == 1:
                        b[0] = ast.Pass()
                    else:
                        b.pop(0)
        ast.fix_missing_locations(tree)
        ex = ast.unparse(tree)
        self.assertNotIn("getattr(req, 'conv_id'", ex)
        self.assertNotIn("getattr(req, 'turn_id'", ex)


def _claim(**over):
    """A committed-turn claim, built from the SHIPPED dataclass."""
    base = dict(ledger_id=1, started=0.0, narrator_id="N-real",
                turn_id="turn-real", turn_key="turnrow:4242",
                session_id="conv-real", turn_mode="interview",
                source="ws", user_text=ACCEPTED_WORDING)
    base.update(over)
    return TE._Claim(**base)


class IdentityComesFromTheClaim(unittest.TestCase):
    """producer: _Claim -> consumer: route_extraction_to_bio_facts."""

    def test_the_helper_carries_all_four_ids_off_the_claim(self):
        ident = TE.claim_source_identity(_claim())
        self.assertEqual(ident, {
            "narrator_id": "N-real", "session_id": "conv-real",
            "turn_id": "turn-real", "turn_key": "turnrow:4242"})

    def test_the_router_receives_the_committed_turns_identity(self):
        """The production-boundary proof. Nothing is hand-supplied.

        `run_field_extraction` is driven with the identity the completed
        turn would hand it, and the router's ACTUAL kwargs are captured.
        """
        seen = {}

        def _fake_route(items, narrator_id, **kw):
            seen.update({"narrator_id": narrator_id, **kw})
            return mock.Mock(routed=1, conflicts=0, suppressed_by_authority=0,
                             unmapped=0, errors=0)

        req = EX.ExtractFieldsRequest(person_id="N-real",
                                      answer=ACCEPTED_WORDING)
        with mock.patch("api.services.bio_fact_router.routing_enabled",
                        return_value=True), \
             mock.patch("api.services.bio_fact_router."
                        "route_extraction_to_bio_facts", _fake_route), \
             mock.patch.object(EX, "_extract_via_llm",
                               return_value=([{"fieldPath": "parents.firstName",
                                               "value": "Walter",
                                               "confidence": 0.9}], "[stub]")):
            EX.run_field_extraction(
                req, source_identity=TE.claim_source_identity(_claim()))

        self.assertEqual(seen.get("session_id"), "conv-real")
        self.assertEqual(seen.get("turn_id"), "turn-real")
        self.assertEqual(seen.get("turn_key"), "turnrow:4242")
        self.assertEqual(seen.get("narrator_id"), "N-real")

    def test_none_of_those_ids_is_None(self):
        """The literal regression. Production used to send None, None."""
        seen = {}

        def _fake_route(items, narrator_id, **kw):
            seen.update(kw)
            return mock.Mock(routed=1, conflicts=0, suppressed_by_authority=0,
                             unmapped=0, errors=0)

        req = EX.ExtractFieldsRequest(person_id="N-real", answer=ACCEPTED_WORDING)
        with mock.patch("api.services.bio_fact_router.routing_enabled",
                        return_value=True), \
             mock.patch("api.services.bio_fact_router."
                        "route_extraction_to_bio_facts", _fake_route), \
             mock.patch.object(EX, "_extract_via_llm",
                               return_value=([{"fieldPath": "parents.firstName",
                                               "value": "Walter", "confidence": 0.9}],
                                             "[stub]")):
            EX.run_field_extraction(
                req, source_identity=TE.claim_source_identity(_claim()))
        for k in ("session_id", "turn_id", "turn_key"):
            with self.subTest(field=k):
                self.assertIsNotNone(seen.get(k))


class RequestSideIdentityCannotSubstitute(unittest.TestCase):
    """The negative control the work order requires."""

    def _route_with(self, source_identity, person_id="N-req", **req_kw):
        seen = {"called": False}

        def _fake_route(items, narrator_id, **kw):
            seen.update({"called": True, "narrator_id": narrator_id, **kw})
            return mock.Mock(routed=1, conflicts=0, suppressed_by_authority=0,
                            unmapped=0, errors=0)

        req = EX.ExtractFieldsRequest(person_id=person_id,
                                      answer=ACCEPTED_WORDING, **req_kw)
        with mock.patch("api.services.bio_fact_router.routing_enabled",
                        return_value=True), \
             mock.patch("api.services.bio_fact_router."
                        "route_extraction_to_bio_facts", _fake_route), \
             mock.patch.object(EX, "_extract_via_llm",
                               return_value=([{"fieldPath": "parents.firstName",
                                               "value": "Walter", "confidence": 0.9}],
                                             "[stub]")):
            EX.run_field_extraction(req, source_identity=source_identity)
        return seen

    def test_no_committed_turn_means_NO_ROUTING_AT_ALL(self):
        """Not routing with nulls. Not routing.

        A bio fact whose source turn is unknown is not worth writing, and
        writing it with `None` provenance is how the defect looked.

        ── WHY THE LOG IS ASSERTED TOO, 2026-09-05 ────────────────────

        *(This checked only `seen["called"] is False`, and a mutation
        that removed the guard entirely — routing unconditionally with
        `source_identity=None` — PASSED. The call raises `AttributeError`
        on `None.get`, the outer `except Exception` swallows it, and
        "never called" is indistinguishable from "called and crashed".
        The skip must be OBSERVED, not inferred from an absence.)*
        """
        with self.assertLogs("lorevox.extract", level="INFO") as logs:
            seen = self._route_with(None)
        self.assertFalse(seen["called"],
                         "routed a fact with no committed-turn identity")
        self.assertTrue(
            any("[bio_fact_router] SKIPPED" in m for m in logs.output),
            "the skip was not announced — routing may have crashed instead "
            f"of refusing. Log was: {logs.output}")

    def test_a_session_id_on_the_REQUEST_does_not_authorise_routing(self):
        """Even the real `session_id` field is not provenance.

        It says which conversation the caller claims to be in. It does
        not identify a committed turn, and the HTTP path can set it
        freely.
        """
        seen = self._route_with(None, session_id="conv-from-request")
        self.assertFalse(seen["called"])

    def test_the_claim_wins_over_a_conflicting_request(self):
        """Identity is the turn's fact, not the request's opinion.

        The narrator MATCHES here on purpose — a narrator mismatch is a
        refusal, tested separately below. What this isolates is that a
        `session_id` set on the request cannot displace the committed
        turn's own conversation id.
        """
        seen = self._route_with(
            TE.claim_source_identity(_claim(session_id="conv-real")),
            person_id="N-real",
            session_id="conv-from-request")
        self.assertTrue(seen["called"])
        self.assertEqual(seen["session_id"], "conv-real")

    def test_the_http_path_passes_no_identity(self):
        """`run_http_extraction` has no committed turn, and says so."""
        import inspect
        src = inspect.getsource(TE.run_http_extraction)
        self.assertIn("_call_extractor(req)", src)
        self.assertNotIn("source_identity=", src)


class ExtractionAndProvenanceMustNameTheSameNarrator(unittest.TestCase):
    """Phase 5B item 0 — the cross-narrator invariant.

    Provenance is authoritative, but extraction still runs against
    `req.person_id`. On the completed-turn path the two always agree,
    because both come from one `_Claim` — which is precisely why a
    disagreement means something upstream is wrong.

    **Refusing is the only safe answer.** Trusting `source_identity`
    would file narrator A's extracted facts under narrator B; trusting
    `req.person_id` would attach B's facts to A's committed turn. Both
    are silent cross-narrator corruption, and this repository's own
    Picker doctrine says destination is never inferred.
    """

    def _attempt(self, *, req_person, claim_narrator, turn_key="turnrow:1"):
        seen = {"called": False}

        def _fake_route(items, narrator_id, **kw):
            seen.update({"called": True, "narrator_id": narrator_id, **kw})
            return mock.Mock(routed=1, conflicts=0, suppressed_by_authority=0,
                             unmapped=0, errors=0)

        req = EX.ExtractFieldsRequest(person_id=req_person,
                                      answer=ACCEPTED_WORDING)
        ident = TE.claim_source_identity(
            _claim(narrator_id=claim_narrator, turn_key=turn_key))
        with mock.patch("api.services.bio_fact_router.routing_enabled",
                        return_value=True), \
             mock.patch("api.services.bio_fact_router."
                        "route_extraction_to_bio_facts", _fake_route), \
             mock.patch.object(EX, "_extract_via_llm",
                               return_value=([{"fieldPath": "parents.firstName",
                                               "value": "Walter",
                                               "confidence": 0.9}], "[stub]")):
            with self.assertLogs("lorevox.extract", level="INFO") as logs:
                resp = EX.run_field_extraction(req, source_identity=ident)
        return seen, resp, logs.output

    def test_matching_narrators_route_normally(self):
        """Positive control — without it, refusal proves nothing."""
        seen, _resp, _logs = self._attempt(req_person="N-1", claim_narrator="N-1")
        self.assertTrue(seen["called"])
        self.assertEqual(seen["narrator_id"], "N-1")

    def test_a_narrator_mismatch_REFUSES_to_route(self):
        seen, _resp, logs = self._attempt(req_person="N-1", claim_narrator="N-2")
        self.assertFalse(
            seen["called"],
            "routed a bio fact whose extraction ran for a different narrator")
        self.assertTrue(
            any("provenance-identity-mismatch" in m for m in logs),
            f"the mismatch was not announced. Log: {logs}")

    def test_the_mismatch_does_not_silently_pick_either_narrator(self):
        """Neither id wins. That is the whole point."""
        seen, _resp, _logs = self._attempt(req_person="N-1", claim_narrator="N-2")
        self.assertNotEqual(seen.get("narrator_id"), "N-1")
        self.assertNotEqual(seen.get("narrator_id"), "N-2")

    def test_the_extraction_result_survives_a_mismatch(self):
        """A refused side-write must not cost the narrator their result."""
        _seen, resp, _logs = self._attempt(req_person="N-1", claim_narrator="N-2")
        self.assertTrue(resp.items,
                        "the extraction result was lost to a routing refusal")

    def test_an_empty_turn_key_REFUSES_to_route(self):
        """`turn_key` is the only id that survives a replay.

        `turn_id` is the client's string and can legitimately be absent,
        so it cannot carry this requirement.
        """
        for empty in ("", "   "):
            with self.subTest(turn_key=repr(empty)):
                seen, _resp, logs = self._attempt(
                    req_person="N-1", claim_narrator="N-1", turn_key=empty)
                self.assertFalse(seen["called"])
                self.assertTrue(any("turn_key is missing" in m for m in logs))


class TheCompletedTurnPathHandsIdentityDown(unittest.TestCase):
    """The pass-through itself, exercised rather than assumed.

    ── WHY THIS CLASS EXISTS, 2026-09-05 ─────────────────────────────

    *(A mutation that deleted `claim_source_identity(claim)` from the
    completed-turn call site PASSED the whole suite. Every other test
    here calls `run_field_extraction` directly WITH an identity, so none
    of them touched the line that supplies it. The tests proved the
    consumer and skipped the producer.)*
    """

    def test_the_completed_turn_caller_passes_the_claims_identity(self):
        """Drive `_complete_claim_inner` and capture what it hands over."""
        import asyncio
        captured = {}

        def _spy(req, source_identity=None):
            captured["identity"] = source_identity
            return mock.Mock(items=[], clarification_required=[],
                             raw_output="", method="stub")

        claim = _claim()
        with mock.patch.object(TE, "_call_extractor", _spy), \
             mock.patch.object(TE, "_close_ledger", create=True,
                               side_effect=lambda *a, **k: None), \
             mock.patch.object(TE, "forced_failure_mode", return_value=""):
            try:
                asyncio.run(TE._complete_claim_inner(claim))
            except Exception:
                # The ledger close and outcome shaping are not under test;
                # what matters is what `_call_extractor` received.
                pass

        self.assertIsNotNone(
            captured.get("identity"),
            "the completed-turn path called the extractor with NO source "
            "identity — provenance would be null again")
        self.assertEqual(captured["identity"]["session_id"], "conv-real")
        self.assertEqual(captured["identity"]["turn_key"], "turnrow:4242")
        self.assertEqual(captured["identity"]["turn_id"], "turn-real")
        self.assertEqual(captured["identity"]["narrator_id"], "N-real")


class FailureIsolationIsPreserved(unittest.TestCase):
    """Routing must never cost the narrator their turn."""

    def test_a_router_explosion_does_not_break_extraction(self):
        req = EX.ExtractFieldsRequest(person_id="N-real", answer=ACCEPTED_WORDING)
        with mock.patch("api.services.bio_fact_router.routing_enabled",
                        return_value=True), \
             mock.patch("api.services.bio_fact_router."
                        "route_extraction_to_bio_facts",
                        side_effect=RuntimeError("router down")), \
             mock.patch.object(EX, "_extract_via_llm",
                               return_value=([{"fieldPath": "parents.firstName",
                                               "value": "Walter", "confidence": 0.9}],
                                             "[stub]")):
            resp = EX.run_field_extraction(
                req, source_identity=TE.claim_source_identity(_claim()))
        self.assertTrue(resp.items, "extraction lost its result to a router failure")


class LexicalGapWasMeasuredThenClosed(unittest.TestCase):
    """The `daddy` gap — found by accident, closed by Phase 5B.

    ── THE HISTORY IS THE POINT, 2026-09-05 ──────────────────────────

    The first draft of this file used *"My daddy worked at the mill"* as
    ordinary narrator wording, and every routing test failed with zero
    items. Not provenance, not the router: **the shipped kinship guard
    did not recognise `daddy`**, so the item was quarantined
    `relationship_unstated` and never reached routing.

    The vocabulary had `mama` and `papa` and no `daddy` — one word
    missing from one alternation, invisible to every test in the tree.
    Phase 5B replaced that alternation with a derived one from
    `services/relationship_interpreter`, so the asymmetry cannot recur
    without the central table disagreeing with itself.

    These now assert the CLOSED behaviour. The `father` control stays,
    because without it a passing `daddy` test proves only that something
    binds.
    """

    @staticmethod
    def _extract(answer, value):
        with mock.patch.object(
                EX, "_extract_via_llm",
                return_value=([{"fieldPath": "parents.firstName",
                                "value": value, "confidence": 0.9}], "[stub]")):
            return EX.run_field_extraction(
                EX.ExtractFieldsRequest(person_id="N", answer=answer))

    def test_father_binds(self):
        """The control. Without it the next test proves nothing."""
        r = self._extract("My father Walter worked at the mill.", "Walter")
        self.assertEqual([("parents.firstName", "Walter")],
                         [(i.fieldPath, i.value) for i in r.items])

    def test_daddy_now_binds_too(self):
        """Was quarantined `relationship_unstated`."""
        r = self._extract("My daddy Walter worked at the mill.", "Walter")
        self.assertEqual([("parents.firstName", "Walter")],
                         [(i.fieldPath, i.value) for i in r.items])
        self.assertNotIn(
            "relationship_unstated",
            [c.get("reason") for c in (r.clarification_required or [])])

    def test_mama_still_binds(self):
        """The half that always worked must not regress."""
        r = self._extract("My mama Betty kept the house.", "Betty")
        self.assertEqual([("parents.firstName", "Betty")],
                         [(i.fieldPath, i.value) for i in r.items])

    def test_daddy_and_mama_canonicalize_to_different_parents(self):
        """The asymmetry is gone, and the meanings stayed distinct.

        A central table makes it easy to fix `daddy` by mapping it to
        whatever `mama` maps to. That would bind and be wrong.
        """
        from api.services.relationship_interpreter import interpret_phrase
        self.assertEqual(interpret_phrase("my daddy").relation, "father")
        self.assertEqual(interpret_phrase("my mama").relation, "mother")

    def test_the_narrators_word_is_still_recoverable(self):
        """`daddy → father` must not lose `daddy`."""
        from api.services.relationship_interpreter import interpret_phrase
        reading = interpret_phrase("my daddy Walter")
        self.assertEqual(reading.source_phrase, "daddy")
        self.assertTrue(reading.normalized)

    def test_unchanged_language_claims_no_normalization(self):
        """`father → father` transformed nothing, and says so."""
        from api.services.relationship_interpreter import interpret_phrase
        self.assertFalse(interpret_phrase("my father Walter").normalized)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
