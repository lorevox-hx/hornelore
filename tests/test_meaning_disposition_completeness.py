"""Phase 5C — every supported reading names its destination.

WO-LORI-ARCHIVE-TO-MEMOIR-02 Block B.

    Every meaning Lori understands must reach a real field, an
    attributed review destination, or an EXPLICIT RECORDED REFUSAL.
    Nothing understood may silently disappear, and nothing may be
    forced into a false schema field to avoid a review item.

THIS FILE IS THE PROTECTION, not the mechanism. It enumerates the
AUTHORITATIVE interpreter's own table — every row, every component —
and refuses any component nobody has ruled on. A future session that
teaches the interpreter a new qualifier or a new state, and gives it
nowhere to go, fails HERE with the component named, instead of
discovering the loss months later the way `older` and `late wife` were
discovered.

WHY IT ENUMERATES RATHER THAN SAMPLES. Phase 5B's qualifier gap existed
for as long as it did because every test that touched it asserted a case
somebody had thought of. `_TABLE` is the shipped vocabulary; deriving the
cases from it means the test grows when the product does, and a row added
without a destination cannot slip past by not having a test written for
it.

THE FIELD SET IS THE SHIPPED ONE. `EXTRACTABLE_FIELDS` is imported from
the router rather than restated, so "there is no destination" is measured
against what production actually accepts. A hand-listed field set would
let this file agree with itself while disagreeing with the product —
the fixture supplying the property being proven.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server" / "code"))
# So the standard command works unchanged. `_run` below imports the
# kinship suite's helpers rather than building a second way to
# construct an item, and `PYTHONPATH=server/code` alone does not put
# the repository root on the path.
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATA_DIR", "/tmp/_md_completeness")

from api.routers import extract as ex                     # noqa: E402
from api.services import meaning_disposition as md        # noqa: E402
from api.services import relationship_interpreter as ri   # noqa: E402

FIELDS = set(ex.EXTRACTABLE_FIELDS)


def _declared_rows():
    """One `RelationshipReading` per row of the shipped vocabulary table.

    CONSTRUCTED DIRECTLY, AND THE NAME NOW SAYS SO. The first version of
    this helper was called `_readings` and claimed in its docstring to
    build them "through `interpret_phrase`, the production entry point".
    It did not — it constructed `RelationshipReading` from `ri._TABLE` —
    and a comment describing a production boundary the code does not
    cross is the repository's own recorded failure mode.

    Direct construction is the RIGHT tool for the job this helper has,
    which is enumerating the DECLARED vocabulary so no row can lack a
    disposition ruling. It is not, and must not be mistaken for,
    evidence that the interpreter produces those readings from real
    narrator wording. `ProducedByTheRealInterpreter` below does that,
    through `readings_in` and the shipped extraction path.
    """
    return [
        ri.RelationshipReading(group=group, relation=relation, state=state,
                               qualifier=qualifier, source_phrase=relation)
        for _pattern, group, relation, state, qualifier in ri._TABLE
    ]


class TheTableItselfIsNonEmpty(unittest.TestCase):
    """Guard the subject. An empty table passes everything below."""

    def test_the_interpreter_has_a_vocabulary(self):
        self.assertGreater(len(ri._TABLE), 20)

    def test_the_field_set_is_the_shipped_one(self):
        self.assertGreater(len(FIELDS), 100)
        self.assertIn("family.spouse.firstName", FIELDS)


class EveryComponentOfEveryReadingIsRuledOn(unittest.TestCase):
    """THE PHASE 5C GATE.

    Not "every component has a field" — several correctly have none.
    Every component has a DECISION: field, review, or recorded refusal.
    `undeclared` is the failure, and it is a different fact from a
    refusal: one says we decided nothing goes here, the other says
    nobody looked.
    """

    def test_no_component_is_undeclared(self):
        undeclared = []
        for reading in _declared_rows():
            for component in md.COMPONENTS:
                disposition, _dest = md.destination_for(
                    reading, component, FIELDS)
                if disposition == md.DISPOSITION_UNDECLARED:
                    undeclared.append(
                        f"{reading.group}.{reading.relation} "
                        f"state={reading.state!r} qual={reading.qualifier!r}"
                        f" -> {component}")
        self.assertEqual(
            undeclared, [],
            "these reading components have no ruling at all. Add them to "
            "the declared table in meaning_disposition, with a real "
            "destination or a deliberate refusal:\n  " +
            "\n  ".join(undeclared))

    def test_every_disposition_is_from_the_declared_vocabulary(self):
        for reading in _declared_rows():
            for component in md.COMPONENTS:
                disposition, _dest = md.destination_for(
                    reading, component, FIELDS)
                with self.subTest(component=component,
                                  relation=reading.relation):
                    self.assertIn(disposition,
                                  md.VALID_DISPOSITIONS |
                                  {md.DISPOSITION_UNDECLARED})

    def test_a_field_disposition_actually_names_something(self):
        """A destination of `None` alongside `field` would be a lie."""
        for reading in _declared_rows():
            for component in md.COMPONENTS:
                disposition, dest = md.destination_for(
                    reading, component, FIELDS)
                if disposition == md.DISPOSITION_FIELD:
                    with self.subTest(component=component,
                                      relation=reading.relation):
                        self.assertTrue(dest)

    def test_an_unknown_state_is_undeclared_not_silently_refused(self):
        """The trap this exists to spring.

        A new state added to the interpreter with no entry in the
        disposition table must NOT inherit "no destination" and look
        deliberate.
        """
        invented = ri.RelationshipReading(
            group=ri.GROUP_SPOUSE, relation="wife", state="estranged",
            source_phrase="estranged wife")
        disposition, _ = md.destination_for(invented, "state", FIELDS)
        self.assertEqual(md.DISPOSITION_UNDECLARED, disposition)

    def test_an_unknown_qualifier_is_undeclared_too(self):
        invented = ri.RelationshipReading(
            group=ri.GROUP_SIBLINGS, relation="brother", qualifier="eldest",
            source_phrase="eldest brother")
        disposition, _ = md.destination_for(invented, "qualifier", FIELDS)
        self.assertEqual(md.DISPOSITION_UNDECLARED, disposition)


class NothingIsInvented(unittest.TestCase):
    """The refusals must refuse the RIGHT thing.

    A disposition that quietly proposed `siblings.birthOrder` would be
    worse than the silence it replaced: it would look like a decision.
    """

    def test_older_never_proposes_birth_order(self):
        for phrase in ("My older brother Ray was a welder.",
                       "My younger sister Joan moved away."):
            with self.subTest(phrase=phrase):
                for rec in md.account_for_readings(phrase, FIELDS):
                    self.assertNotEqual("siblings.birthOrder",
                                        rec.get("would_need"))
                    self.assertNotEqual("siblings.birthOrder",
                                        rec.get("proposed_fieldPath"))

    def test_the_older_refusal_says_why_birth_order_is_wrong(self):
        """`would_need` is acted on by a human, so it has to warn."""
        recs = md.account_for_readings("My older brother Ray was a welder.",
                                       FIELDS)
        qualifier = [r for r in recs
                     if r["meaning"] == "relationship_qualifier"]
        self.assertEqual(1, len(qualifier))
        self.assertIn("NOT siblings.birthOrder", qualifier[0]["would_need"])

    def test_adult_is_not_answered_with_an_age_destination(self):
        recs = md.account_for_readings(
            "My adult daughter Nina lives in Boston.", FIELDS)
        qualifier = [r for r in recs
                     if r["meaning"] == "relationship_qualifier"]
        self.assertEqual(1, len(qualifier))
        self.assertIn("NOT an age", qualifier[0]["would_need"])

    def test_a_deceased_spouse_invents_no_date_year_or_cause(self):
        recs = md.account_for_readings("My late wife Susan taught school.",
                                       FIELDS)
        state = [r for r in recs if r["meaning"] == "relationship_state"]
        self.assertEqual(1, len(state))
        self.assertEqual("deceased", state[0]["value"])
        blob = " ".join(str(v) for v in state[0].values()).lower()
        for invented in ("deathdate", "death_date", "1987", "died on"):
            self.assertNotIn(invented, blob)

    def test_there_really_is_no_deceased_field_to_use_instead(self):
        """The refusal is only correct while this holds.

        If somebody adds a living/deceased destination, this fails and
        the disposition must become a FIELD rather than a refusal —
        which is the outcome we want, announced rather than assumed.
        """
        self.assertEqual(
            [], [f for f in FIELDS
                 if "deceased" in f.lower() or f.endswith(".livingState")],
            "a deceased destination now exists; route STATE_DECEASED to it")


class TheRecordIsActionable(unittest.TestCase):
    """A refusal a human cannot act on is a silence with extra steps."""

    def test_it_carries_the_narrators_own_words(self):
        recs = md.account_for_readings("My late wife Susan taught school.",
                                       FIELDS)
        self.assertTrue(recs)
        for rec in recs:
            self.assertTrue(rec["narrator_phrase"])
            self.assertTrue(rec["label"])
            self.assertTrue(rec["would_need"])
            self.assertTrue(rec["person"])
            self.assertTrue(rec["not_applied"])
            self.assertEqual(md.DISPOSITION_NO_DESTINATION,
                             rec["disposition"])

    def test_it_keeps_the_keys_the_existing_review_surface_reads(self):
        """Additive, not a reshape.

        `bug-panel-story-review.js:707` and the Phase 5B guards already
        read these; a Phase 5C record that dropped them would be
        invisible in the one place an operator looks.
        """
        rec = md.no_destination_record(
            meaning="relationship_qualifier", value="older",
            label="older brother", reason=md.REASON_QUALIFIER_HAS_NO_DESTINATION,
            narrator_phrase="older brother", would_need="something")
        for key in ("kind", "value", "label", "proposed_fieldPath",
                    "not_applied", "reasons", "reason", "narrator_phrase",
                    "would_need"):
            self.assertIn(key, rec)
        self.assertEqual([md.REASON_QUALIFIER_HAS_NO_DESTINATION],
                         rec["reasons"])

    def test_a_fully_placed_reading_produces_NO_record(self):
        """The discrimination. Without this the pass could emit on
        everything and every assertion above would still hold."""
        self.assertEqual(
            [], md.account_for_readings("My wife Mary is a nurse.", FIELDS))
        self.assertEqual(
            [], md.account_for_readings("My brother Ray was a welder.", FIELDS))

    def test_the_phase_5b_reason_string_is_unchanged(self):
        """`test_spouse_state_characterization` asserts it verbatim."""
        self.assertEqual("relationship_state_has_no_destination",
                         md.REASON_LANE_HAS_NO_DESTINATION)


class ItSurvivesToTheOperator(unittest.TestCase):
    """The production boundary: dispositions must reach the envelope.

    A record that never leaves the function is the same silence in a
    different costume, so this drives the shipped extraction path and
    reads `clarification_required` — the field that is persisted, served
    by `operator_story_review`, and rendered by the Bug Panel.
    """

    #: The SAME helpers `test_kinship_qualifier_binding` drives the
    #: shipped path with. Reused rather than reinvented: a second way to
    #: construct an item is a second thing that can drift away from the
    #: product, and the first draft of these tests proved it by getting
    #: `ExtractedItem`'s signature wrong.
    def _run(self, answer, items):
        from tests.test_kinship_qualifier_binding import item, run
        return run(answer, [item(fp, v) for fp, v in items])

    def _reasons(self, resp):
        return [c.get("reason") for c in (resp.clarification_required or [])]

    def test_a_qualifier_reaches_the_clarification_envelope(self):
        resp = self._run("My older brother Ray was a welder.",
                         [("siblings.firstName", "Ray")])
        self.assertIn(md.REASON_QUALIFIER_HAS_NO_DESTINATION,
                      self._reasons(resp))

    def test_a_deceased_spouse_reaches_it_too(self):
        resp = self._run("My late wife Susan taught school.",
                         [("family.spouse.firstName", "Susan")])
        self.assertIn(md.REASON_DECEASED_HAS_NO_DESTINATION,
                      self._reasons(resp))

    def test_the_record_that_arrives_carries_the_narrator_wording(self):
        resp = self._run("My late wife Susan taught school.",
                         [("family.spouse.firstName", "Susan")])
        rec = [c for c in resp.clarification_required
               if c.get("reason") == md.REASON_DECEASED_HAS_NO_DESTINATION]
        self.assertEqual(1, len(rec))
        self.assertEqual("late wife", rec[0]["narrator_phrase"])
        self.assertTrue(rec[0]["not_applied"])

    def test_an_ordinary_turn_adds_no_disposition(self):
        resp = self._run("My wife Mary is a nurse.",
                         [("family.spouse.firstName", "Mary")])
        reasons = self._reasons(resp)
        for reason in (md.REASON_QUALIFIER_HAS_NO_DESTINATION,
                       md.REASON_DECEASED_HAS_NO_DESTINATION):
            self.assertNotIn(reason, reasons)

    def test_the_qualifier_still_reaches_no_FIELD(self):
        """Recording it must not have wired it somewhere by accident."""
        resp = self._run("My older brother Ray was a welder.",
                         [("siblings.firstName", "Ray")])
        paths = [i.fieldPath for i in resp.items]
        self.assertNotIn("siblings.birthOrder", paths)
        self.assertIn("siblings.firstName", paths)


#: The eight no-destination families, as a narrator would actually say
#: them. Driven through the REAL producer, not constructed.
PRODUCTION_CASES = (
    ("older",       "My older brother Ray was a welder.",
     ("siblings.firstName", "Ray"),  md.REASON_QUALIFIER_HAS_NO_DESTINATION),
    ("younger",     "My younger sister Joan moved away.",
     ("siblings.firstName", "Joan"), md.REASON_QUALIFIER_HAS_NO_DESTINATION),
    ("adult",       "My adult daughter Nina lives in Boston.",
     ("family.children.firstName", "Nina"),
     md.REASON_QUALIFIER_HAS_NO_DESTINATION),
    ("grown",       "My grown son Peter took over the shop.",
     ("family.children.firstName", "Peter"),
     md.REASON_QUALIFIER_HAS_NO_DESTINATION),
    ("half",        "My half-sister Joan lived upstate.",
     ("siblings.firstName", "Joan"),  md.REASON_QUALIFIER_HAS_NO_DESTINATION),
    ("step",        "My step-brother Alan joined the navy.",
     ("siblings.firstName", "Alan"),  md.REASON_QUALIFIER_HAS_NO_DESTINATION),
    ("deceased",    "My late wife Susan taught school.",
     ("family.spouse.firstName", "Susan"),
     md.REASON_DECEASED_HAS_NO_DESTINATION),
    ("grandparent", "My grandmother Elsie kept bees.",
     ("grandparents.firstName", "Elsie"),
     md.REASON_RELATION_HAS_NO_DESTINATION),
    ("greatgrand",  "My great-grandmother Ada came over in 1901.",
     ("greatGrandparents.firstName", "Ada"),
     md.REASON_RELATION_HAS_NO_DESTINATION),
)


class ProducedByTheRealInterpreter(unittest.TestCase):
    """THE PRODUCTION BOUNDARY the enumeration above does not cross.

    `_declared_rows` proves every DECLARED vocabulary row has a ruling.
    It constructs its readings, so it cannot show that the interpreter
    produces them from what a narrator actually says — and a helper
    claiming otherwise is the failure this repository has paid for most
    often.

    So these drive the real phrase through `readings_in`, the shipped
    producer, and then through the shipped extraction path.
    """

    def _run(self, answer, item_pair):
        from tests.test_kinship_qualifier_binding import item, run
        return run(answer, [item(*item_pair)])

    def test_the_interpreter_really_reads_each_phrase(self):
        """Non-vacuity FIRST. If `readings_in` returns nothing, every
        assertion below would pass by finding nothing to place."""
        for name, answer, _item, _reason in PRODUCTION_CASES:
            with self.subTest(case=name):
                self.assertTrue(
                    ri.readings_in(answer),
                    f"the shipped interpreter reads nothing in {answer!r}")

    def test_each_family_reaches_the_envelope_from_a_real_phrase(self):
        for name, answer, item_pair, reason in PRODUCTION_CASES:
            with self.subTest(case=name):
                resp = self._run(answer, item_pair)
                reasons = [c.get("reason")
                           for c in (resp.clarification_required or [])]
                self.assertIn(reason, reasons,
                              f"{name}: {answer!r} produced {reasons}")

    def test_each_record_carries_the_phrase_the_narrator_used(self):
        for name, answer, item_pair, reason in PRODUCTION_CASES:
            with self.subTest(case=name):
                resp = self._run(answer, item_pair)
                recs = [c for c in (resp.clarification_required or [])
                        if c.get("reason") == reason]
                self.assertTrue(recs)
                for rec in recs:
                    self.assertTrue(rec["narrator_phrase"])
                    self.assertIn(rec["narrator_phrase"].split()[-1].lower(),
                                  answer.lower())

    def test_no_family_invents_a_field(self):
        for name, answer, item_pair, _reason in PRODUCTION_CASES:
            with self.subTest(case=name):
                resp = self._run(answer, item_pair)
                paths = [i.fieldPath for i in resp.items]
                for invented in ("siblings.birthOrder",
                                 "family.children.birthOrder",
                                 "personal.birthOrder",
                                 "grandparents.deathDate"):
                    self.assertNotIn(invented, paths)


class AnAccountingFailureIsItselfDurable(unittest.TestCase):
    """CORRECTION, found in review of the pushed Phase 5C.

    The pass used to catch its own exception, log
    "meaning with no destination went unrecorded", and continue. The
    narrator keeps their turn — correct — but a rotating gitignored log
    is not a record, and the result is exactly the silent loss this
    phase prohibits.

    `measurement_failed` is NOT `no_destination`. One says we looked and
    there is nowhere to put it; the other says we could not look.
    """

    def _run_with_broken_accounting(self):
        from unittest import mock
        from tests.test_kinship_qualifier_binding import item, run
        with mock.patch.object(md, "account_for_readings",
                               side_effect=RuntimeError("boom")):
            return run("My older brother Ray was a welder.",
                       [item("siblings.firstName", "Ray")])

    def test_the_turn_still_succeeds(self):
        resp = self._run_with_broken_accounting()
        self.assertEqual([("siblings.firstName", "Ray")],
                         [(i.fieldPath, i.value) for i in resp.items])

    def test_the_failure_is_recorded_not_swallowed(self):
        resp = self._run_with_broken_accounting()
        recs = [c for c in (resp.clarification_required or [])
                if c.get("reason") == md.REASON_ACCOUNTING_FAILED]
        self.assertEqual(1, len(recs), resp.clarification_required)
        rec = recs[0]
        self.assertEqual(md.DISPOSITION_MEASUREMENT_FAILED, rec["disposition"])
        self.assertEqual("unverified", rec["completeness"])
        self.assertEqual("RuntimeError", rec["error_class"])
        self.assertTrue(rec["not_applied"])

    def test_it_is_not_filed_as_a_refusal(self):
        """Filing it as `no_destination` would claim we looked."""
        resp = self._run_with_broken_accounting()
        for rec in (resp.clarification_required or []):
            if rec.get("reason") == md.REASON_ACCOUNTING_FAILED:
                self.assertNotEqual(md.DISPOSITION_NO_DESTINATION,
                                    rec["disposition"])

    def test_it_carries_no_narrator_text(self):
        """Not even the exception message, which can quote the input."""
        resp = self._run_with_broken_accounting()
        recs = [c for c in (resp.clarification_required or [])
                if c.get("reason") == md.REASON_ACCOUNTING_FAILED]
        blob = " ".join(str(v) for v in recs[0].values()).lower()
        for word in ("ray", "brother", "welder", "boom"):
            self.assertNotIn(word, blob)


class ItIsDurableOnTheCommittedTurn(unittest.TestCase):
    """A disposition-only turn must PERSIST and READ BACK.

    The earlier suite stopped at `ExtractFieldsResponse`. A record that
    reaches a response and not a row is gone the moment the frame is
    acknowledged — and this is the Phase 3 behaviour that
    `_store_result` persists a review-only result with ZERO executable
    items, exercised here rather than assumed.

    THE PERSISTED ROW IS NOT HAND-BUILT. It is written by the shipped
    store function and read back by the shipped accessor.
    """

    def setUp(self):
        import importlib
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._prev = {k: os.environ.get(k) for k in ("DATA_DIR", "DB_NAME")}
        os.environ["DATA_DIR"] = self._tmp.name
        os.environ["DB_NAME"] = "test_disposition_durability.sqlite3"
        from api import db as _db
        importlib.reload(_db)
        self.db = _db
        self.db.init_db()
        self.assertTrue(str(self.db.DB_PATH).startswith(self._tmp.name),
                        f"refusing to run against {self.db.DB_PATH}")
        self.addCleanup(self._restore)

    def _restore(self):
        import importlib
        for key, value in self._prev.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        from api import db as _db
        importlib.reload(_db)

    def test_a_disposition_only_result_persists_and_reads_back(self):
        from api.services import turn_extraction as te

        answer = "My older brother Ray was a welder."
        dispositions = md.account_for_readings(answer, FIELDS)
        self.assertTrue(dispositions, "fixture would prove nothing")

        person = self.db.create_person(display_name="Disposition Probe")
        # A REAL LEDGER ROW. `turn_extraction_results.ledger_id` is a
        # foreign key, and the first version of this test passed a
        # literal 1 and was refused with IntegrityError — the shipped
        # store rejecting a shape production never produces, which is
        # exactly why the row is not hand-built here.
        ledger_id = self.db.turn_extraction_claim(
            narrator_id=person["id"], turn_key="tk-disposition-only",
            turn_id="turn-1", session_id="sess-1", turn_mode="interview",
            source="test")
        self.assertIsNotNone(ledger_id)
        claim = te._Claim(
            ledger_id=ledger_id, started=0.0, narrator_id=person["id"],
            turn_id="turn-1", turn_key="tk-disposition-only",
            session_id="sess-1", turn_mode="interview", source="test",
            user_text=answer,
        )
        # ZERO executable items. This is the case Phase 3 opened the
        # store for and the case Phase 5C depends on.
        te._store_result(claim, [], dispositions, "test")

        rows = self.db.turn_extraction_results_pending(person["id"])
        self.assertEqual(1, len(rows), rows)
        row = rows[0]
        self.assertEqual(person["id"], row["narrator_id"])
        self.assertEqual("tk-disposition-only", row["turn_key"])

        stored = row["clarification_required"]
        self.assertTrue(stored, "the disposition did not survive the round trip")
        rec = stored[0]
        for key in ("reason", "narrator_phrase", "would_need", "not_applied",
                    "disposition", "meaning"):
            self.assertIn(key, rec)
        self.assertEqual(md.REASON_QUALIFIER_HAS_NO_DESTINATION, rec["reason"])
        self.assertEqual("older brother", rec["narrator_phrase"])
        self.assertEqual(md.DISPOSITION_NO_DESTINATION, rec["disposition"])
        self.assertTrue(rec["not_applied"])
        self.assertIn("NOT siblings.birthOrder", rec["would_need"])

    def test_an_empty_turn_still_writes_nothing(self):
        """The discrimination. `_store_result` must not have become a
        function that writes a row for every turn."""
        from api.services import turn_extraction as te
        person = self.db.create_person(display_name="Quiet Probe")
        ledger_id = self.db.turn_extraction_claim(
            narrator_id=person["id"], turn_key="tk-empty", turn_id="turn-2",
            session_id="sess-1", turn_mode="interview", source="test")
        claim = te._Claim(
            ledger_id=ledger_id, started=0.0, narrator_id=person["id"],
            turn_id="turn-2", turn_key="tk-empty", session_id="sess-1",
            turn_mode="interview", source="test", user_text="It was warm.")
        te._store_result(claim, [], [], "test")
        self.assertEqual(
            [], self.db.turn_extraction_results_pending(person["id"]))


class ItHasAnOrdinaryOperatorRoute(ItIsDurableOnTheCommittedTurn):
    """CORRECTION. "Operator-visible" was an overstatement.

    Traced in review: `interview.js:_handleReviewEntries` tries
    `HorneloreClarifyFragile` — **defined nowhere in the tree** — then
    `HorneloreShadowReview.showFragileClarifications`, and the module IS
    loaded while its exported API contains no such function. Both miss,
    and the chain ends at `TranscriptGuard.buildConfirmationPrompt`
    inside a `console.log`.

    The rows were durable the whole time. The only route serving them
    was the story-candidate DETAIL endpoint, and a turn whose only
    outcome is a disposition creates no candidate — so the record became
    unreachable the moment the live frame was acknowledged.

    A console log is not a review destination. These prove the real one,
    over the SAME table: no second store, no migration.
    """

    def _seed(self, answer="My older brother Ray was a welder."):
        from api.services import turn_extraction as te
        person = self.db.create_person(display_name="Route Probe")
        recs = md.account_for_readings(answer, FIELDS)
        self.assertTrue(recs, "fixture would prove nothing")
        ledger_id = self.db.turn_extraction_claim(
            narrator_id=person["id"], turn_key="tk-route", turn_id="t1",
            session_id="s1", turn_mode="interview", source="test")
        te._store_result(te._Claim(
            ledger_id=ledger_id, started=0.0, narrator_id=person["id"],
            turn_id="t1", turn_key="tk-route", session_id="s1",
            turn_mode="interview", source="test", user_text=answer), [],
            recs, "test")
        return person

    def test_the_accessor_finds_a_disposition_only_turn(self):
        person = self._seed()
        rows = self.db.turn_extraction_dispositions(person["id"])
        self.assertEqual(1, len(rows))
        self.assertEqual(0, rows[0]["item_count"],
                         "this is the zero-executable-item case")
        self.assertEqual("tk-route", rows[0]["turn_key"])
        self.assertTrue(rows[0]["dispositions"])

    def test_it_is_narrator_scoped(self):
        mine = self._seed()
        other = self.db.create_person(display_name="Someone Else")
        self.assertEqual([], self.db.turn_extraction_dispositions(other["id"]))
        self.assertEqual([], self.db.turn_extraction_dispositions(""))
        self.assertEqual(1, len(self.db.turn_extraction_dispositions(mine["id"])))

    def test_a_plain_result_is_not_listed(self):
        """The discrimination. Without it the route would return every
        extraction result and mean nothing."""
        from api.services import turn_extraction as te
        person = self.db.create_person(display_name="Plain Probe")
        ledger_id = self.db.turn_extraction_claim(
            narrator_id=person["id"], turn_key="tk-plain", turn_id="t9",
            session_id="s1", turn_mode="interview", source="test")
        te._store_result(te._Claim(
            ledger_id=ledger_id, started=0.0, narrator_id=person["id"],
            turn_id="t9", turn_key="tk-plain", session_id="s1",
            turn_mode="interview", source="test", user_text="x"),
            [{"fieldPath": "personal.firstName", "value": "Ray"}], [], "test")
        self.assertEqual([], self.db.turn_extraction_dispositions(person["id"]))

    def test_the_route_serves_it(self):
        import importlib
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:                     # pragma: no cover
            self.skipTest(f"fastapi unavailable: {exc}")
        person = self._seed()
        os.environ["HORNELORE_OPERATOR_STORY_REVIEW"] = "1"
        self.addCleanup(os.environ.pop, "HORNELORE_OPERATOR_STORY_REVIEW", None)
        from api.routers import operator_story_review as _osr
        importlib.reload(_osr)
        app = FastAPI()
        app.include_router(_osr.router)
        resp = TestClient(app).get(
            "/api/operator/meaning-dispositions"
            f"?narrator_id={person['id']}")
        self.assertEqual(200, resp.status_code, resp.text)
        body = resp.json()
        self.assertEqual(1, body["count"])
        self.assertIn(md.REASON_QUALIFIER_HAS_NO_DESTINATION,
                      body["counts_by_reason"])
        entry = body["items"][0]["dispositions"][0]
        self.assertEqual("older brother", entry["narrator_phrase"])
        self.assertIn("NOT siblings.birthOrder", entry["would_need"])
        self.assertTrue(entry["not_applied"])

    def test_the_route_is_404_when_the_feature_is_off(self):
        import importlib
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:                     # pragma: no cover
            self.skipTest(f"fastapi unavailable: {exc}")
        person = self._seed()
        os.environ["HORNELORE_OPERATOR_STORY_REVIEW"] = "0"
        self.addCleanup(os.environ.pop, "HORNELORE_OPERATOR_STORY_REVIEW", None)
        from api.routers import operator_story_review as _osr
        importlib.reload(_osr)
        app = FastAPI()
        app.include_router(_osr.router)
        resp = TestClient(app).get(
            "/api/operator/meaning-dispositions"
            f"?narrator_id={person['id']}")
        self.assertEqual(404, resp.status_code)

    def test_an_accounting_failure_is_surfaced_as_unverified(self):
        from api.services import turn_extraction as te
        person = self.db.create_person(display_name="Failed Probe")
        ledger_id = self.db.turn_extraction_claim(
            narrator_id=person["id"], turn_key="tk-failed", turn_id="t2",
            session_id="s1", turn_mode="interview", source="test")
        te._store_result(te._Claim(
            ledger_id=ledger_id, started=0.0, narrator_id=person["id"],
            turn_id="t2", turn_key="tk-failed", session_id="s1",
            turn_mode="interview", source="test", user_text="x"), [],
            [md.accounting_failed_record("RuntimeError")], "test")
        rows = self.db.turn_extraction_dispositions(person["id"])
        self.assertEqual(1, len(rows))
        self.assertEqual(md.DISPOSITION_MEASUREMENT_FAILED,
                         rows[0]["dispositions"][0]["disposition"])


class TheBrowserHandlerChainIsRecordedAsBROKEN(unittest.TestCase):
    """Measured, so the finding cannot quietly stop being true.

    If somebody later implements one of these handlers, this fails and
    the record above must be corrected rather than left describing a
    world that has moved on.
    """

    def _ui(self, name):
        return (ROOT / "ui" / "js" / name).read_text(
            encoding="utf-8", errors="replace")

    def test_HorneloreClarifyFragile_is_defined_nowhere(self):
        import re
        defined = []
        for path in (ROOT / "ui" / "js").glob("*.js"):
            text = path.read_text(encoding="utf-8", errors="replace")
            # `=(?!=)` because `=== "function"` in the CONSUMER also
            # contains an `=`, and the first version of this matched the
            # `typeof` check in interview.js and reported a definition
            # that does not exist. An assignment, not a comparison.
            if re.search(r"(window|global)\.HorneloreClarifyFragile\s*=(?!=)",
                         text):
                defined.append(path.name)
        self.assertEqual(
            [], defined,
            "HorneloreClarifyFragile now exists — the disposition route's "
            "docstrings say it does not. Correct them.")

    def test_shadow_review_exports_no_fragile_clarification_handler(self):
        text = self._ui("shadow-review.js")
        export = text[text.index("global.HorneloreShadowReview = {"):]
        self.assertNotIn(
            "showFragileClarifications", export.split("};")[0],
            "shadow-review now exports showFragileClarifications — the "
            "finding recorded in db.turn_extraction_dispositions is stale.")

    def test_the_fallback_really_is_a_console_log(self):
        text = self._ui("interview.js")
        chain = text[text.index("_handleReviewEntries"):]
        chain = chain[:chain.index("function applyCompletedTurnExtractionResult")]
        self.assertIn("buildConfirmationPrompt", chain)
        self.assertIn("console.log", chain)


if __name__ == "__main__":
    unittest.main()
