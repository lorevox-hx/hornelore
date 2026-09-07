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


def _readings():
    """One representative reading per row of the shipped table.

    Built through `interpret_phrase`, the production entry point, so a
    row whose pattern stops matching its own canonical phrase fails here
    rather than being silently skipped.
    """
    out = []
    for pattern, group, relation, state, qualifier in ri._TABLE:
        out.append(ri.RelationshipReading(
            group=group, relation=relation, state=state,
            qualifier=qualifier, source_phrase=relation))
    return out


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
        for reading in _readings():
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
        for reading in _readings():
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
        for reading in _readings():
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


if __name__ == "__main__":
    unittest.main()
