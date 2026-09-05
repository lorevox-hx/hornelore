"""Phase 5B item 1 — current vs former spouse, measured before changing it.

    PYTHONPATH=server/code .venv/bin/python -m unittest \\
        tests.test_spouse_state_characterization

`WO-LORI-ARCHIVE-TO-MEMOIR-02` Phase 5B.

── THESE TESTS ASSERT THE CURRENT BEHAVIOUR, NOT THE DESIRED ONE ─────

Every test here is a MEASUREMENT taken at the production boundary before
any Phase 5B code lands. When the fix lands, the tests marked
`CURRENT BEHAVIOUR` fail, and that failure is the signal to update them
deliberately alongside the implementation.

A suite that asserted the desired behaviour up front would be red for
the whole phase and get ignored, which is how a red test becomes
decoration.

── WHAT WAS MEASURED, 2026-09-05 ─────────────────────────────────────

The predicted hazard was that the spouse cue regex matches `wife` inside
`ex-wife`. **The reality is broader and worse: the spouse lane performs
no relationship-state check at all.** Whatever destination the extractor
proposes is accepted verbatim, so:

  * `My ex-wife Susan` proposed as `family.spouse.firstName` → Susan
    becomes the CURRENT spouse, unquarantined;
  * the same holds for `ex-husband`, `former wife` and `previous wife`;
  * and the fully CROSSED assignment survives — the current wife filed
    as a prior partner and the ex-wife as the current spouse, with no
    objection from any guard.

`family.priorPartners.*` exists and accepts values when proposed, so the
destination is not the missing piece. The missing piece is any
deterministic binding of *current* versus *former* from the narrator's
own words.

That is why Phase 5B is not "add a negative lookbehind to one regex".
A lookbehind would stop `ex-wife` reaching the spouse field and leave
the meaning with nowhere honest to go.
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

from api.routers import extract as EX  # noqa: E402

MIXED = "My wife Mary is a nurse. My ex-wife Susan was a teacher."


def item(fp, value, conf=0.9):
    return {"fieldPath": fp, "value": value, "confidence": conf}


def run(answer, items, profile=None):
    """Drive the SHIPPED extraction path with fixed model output.

    The model is not the property under test — binding is — so its
    output is held constant, exactly as `TheJimCase` does.
    """
    req = EX.ExtractFieldsRequest(person_id="N", answer=answer,
                                  current_section="family_life")
    with mock.patch("api.db.get_profile", return_value=profile), \
         mock.patch.object(EX, "_extract_via_llm",
                           return_value=(list(items), "[stub]")):
        return EX.run_field_extraction(req)


def paths(resp):
    return [(i.fieldPath, i.value) for i in resp.items]


class CurrentSpouseWorks(unittest.TestCase):
    """The positive control. Any fix must keep this passing."""

    def test_a_current_wife_reaches_the_spouse_field(self):
        r = run("My wife Mary worked as a teacher.",
                [item("family.spouse.firstName", "Mary")])
        self.assertEqual([("family.spouse.firstName", "Mary")], paths(r))

    def test_a_current_husband_reaches_the_spouse_field(self):
        r = run("My husband Frank drove a bus.",
                [item("family.spouse.firstName", "Frank")])
        self.assertEqual([("family.spouse.firstName", "Frank")], paths(r))

    def test_the_prior_partner_destination_accepts_values(self):
        """`family.priorPartners.*` is not the missing piece."""
        r = run("My ex-wife Susan worked as a teacher.",
                [item("family.priorPartners.firstName", "Susan")])
        self.assertEqual([("family.priorPartners.firstName", "Susan")], paths(r))


class FormerSpouseIsNotDistinguished(unittest.TestCase):
    """CURRENT BEHAVIOUR — every test here is expected to change.

    Each asserts that a former spouse currently reaches the CURRENT
    spouse field unchallenged. When Phase 5B lands, each should fail.
    """

    def test_ex_wife_becomes_the_current_spouse(self):
        r = run("My ex-wife Susan worked as a teacher.",
                [item("family.spouse.firstName", "Susan")])
        self.assertEqual(
            [("family.spouse.firstName", "Susan")], paths(r),
            "an ex-wife no longer reaches the current-spouse field — "
            "Phase 5B has landed; update this measurement deliberately")
        self.assertEqual([], list(r.clarification_required or []),
                         "nothing quarantined it either")

    def test_ex_husband_becomes_the_current_spouse(self):
        r = run("My ex-husband Frank drove a bus.",
                [item("family.spouse.firstName", "Frank")])
        self.assertEqual([("family.spouse.firstName", "Frank")], paths(r))

    def test_former_wife_becomes_the_current_spouse(self):
        """Unhyphenated wording, which a lookbehind on `ex-` would miss."""
        r = run("My former wife Susan worked as a teacher.",
                [item("family.spouse.firstName", "Susan")])
        self.assertEqual([("family.spouse.firstName", "Susan")], paths(r))

    def test_previous_wife_becomes_the_current_spouse(self):
        r = run("My previous wife Susan worked as a teacher.",
                [item("family.spouse.firstName", "Susan")])
        self.assertEqual([("family.spouse.firstName", "Susan")], paths(r))


class TheCrossedAssignmentSurvives(unittest.TestCase):
    """The decisive measurement, and the reason a regex fix is not enough.

    A mixed passage names both a current wife and an ex-wife. If the
    extractor swaps them, **nothing objects** — which proves the guard
    consults the proposal rather than the narrator's words.
    """

    def test_both_named_as_current_spouse_survives(self):
        r = run(MIXED, [item("family.spouse.firstName", "Mary"),
                        item("family.spouse.firstName", "Susan")])
        self.assertEqual(
            [("family.spouse.firstName", "Mary"),
             ("family.spouse.firstName", "Susan")], paths(r))

    def test_the_correct_separation_also_survives(self):
        """Correct input stays correct — the guard is not the problem."""
        r = run(MIXED, [item("family.spouse.firstName", "Mary"),
                        item("family.priorPartners.firstName", "Susan")])
        self.assertIn(("family.spouse.firstName", "Mary"), paths(r))
        self.assertIn(("family.priorPartners.firstName", "Susan"), paths(r))

    def test_the_FULLY_CROSSED_assignment_survives_unchallenged(self):
        """The current wife filed as prior, the ex-wife as current.

        This is the measurement that decides Phase 5B's shape. Nothing
        in the shipped path compares the destination against what the
        narrator actually said.
        """
        r = run(MIXED, [item("family.priorPartners.firstName", "Mary"),
                        item("family.spouse.firstName", "Susan")])
        got = paths(r)
        self.assertIn(("family.spouse.firstName", "Susan"), got,
                      "the ex-wife no longer lands as current spouse — "
                      "Phase 5B has landed; update this deliberately")
        self.assertIn(("family.priorPartners.firstName", "Mary"), got)


class PartnerIsNotRECOGNISEDToday(unittest.TestCase):
    """CURRENT BEHAVIOUR — and it contradicts the expectation.

    ── MEASURED 2026-09-05, AND IT WAS A SURPRISE ────────────────────

    The review expected `partner` to be *"probably test-only closure"* —
    the schema treats `family.spouse.*` as spouse-or-partner, the relation
    field accepts `partner`, the role mapper knows it, and the QA bank
    carries both partner cases. All true, and all upstream of the guard.

    At the production boundary **`partner` is quarantined
    `relationship_unstated`, exactly like `daddy`.** Sam does not reach
    the spouse lane, and no marriage is manufactured either — because
    nothing survives at all.

    So this is a THIRD instance of the same missing-vocabulary shape, not
    a coverage gap. It also means the schema/QA evidence the review cited
    is real but does not reach the binding decision, which is precisely
    the "cite the line that READS the value" rule: `family.spouse.relation`
    accepting `partner` says nothing about whether the guard binds it.
    """

    def test_partner_is_quarantined_not_bound(self):
        """CURRENT behaviour. Phase 5B is expected to change this."""
        r = run("My partner Sam and I have never married.",
                [item("family.spouse.firstName", "Sam")])
        self.assertEqual(
            [], paths(r),
            "partner now binds — Phase 5B has landed; update this "
            "measurement and check that no marriage was manufactured")
        self.assertIn("relationship_unstated",
                      [c.get("reason") for c in (r.clarification_required or [])])

    def test_the_same_holds_without_the_marriage_disclaimer(self):
        """The quarantine is about the word `partner`, not the sentence."""
        r = run("My partner Sam is a nurse.",
                [item("family.spouse.firstName", "Sam")])
        self.assertEqual([], paths(r))

    def test_wife_binds_in_the_identical_sentence_shape(self):
        """The discriminating control. Only the relationship word differs."""
        r = run("My wife Mary is a nurse.",
                [item("family.spouse.firstName", "Mary")])
        self.assertEqual([("family.spouse.firstName", "Mary")], paths(r))

    def test_no_marriage_is_manufactured_for_a_partner(self):
        """Holds today only because nothing survives.

        Kept because it must STILL hold once `partner` binds — that is
        the regression the ex-spouse work is most likely to cause.
        """
        r = run("My partner Sam and I have never married.",
                [item("family.spouse.firstName", "Sam")])
        self.assertFalse([p for p, _v in paths(r) if "marriage" in p.lower()],
                         "a marriage field appeared for an unmarried partner")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
