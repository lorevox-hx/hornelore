"""Qualified kinship wording binds, and the qualifier's fate is measured.

`WO-LORI-ARCHIVE-TO-MEMOIR-02` Phase 5B item 6.

── WHAT THIS IS FOR ──────────────────────────────────────────────────

Phase 5B added qualifier rows to the interpreter table — `adult
daughter`, `grown son`, `older brother`, `younger sister`, the `half-`
and `step-` forms — and every one of them was added by reading the
shape of the neighbouring rows. That is exactly how `late wife` got in,
and how `daddy` stayed out for months: **a vocabulary entry nobody sent
through `run_field_extraction` is a guess with a regex around it.**

So each qualified form is driven through the shipped extraction path
here, beside a PLAIN-RELATION control that differs only in the
qualifying word. Two things can go wrong and the pair separates them:

  * the qualified form fails to bind → the qualifier BROKE binding, and
    the plain control still passing is what proves it;
  * both fail → binding is broken for that relation generally, and the
    qualifier is innocent.

Without the control a qualified-form failure looks like a qualifier bug
either way, which is the discrimination the doctrine asks for.

── AND WHAT HAPPENS TO THE QUALIFIER ITSELF ──────────────────────────

Measured, not assumed: the qualifier is read by the interpreter and is
NOT carried onto the extracted item. `TheQualifierIsReadButNotCarried`
records that as current behaviour with the destination question left
open — `siblings.birthOrder` exists but `older` is not a birth order,
and inventing `birthOrder="1"` from the word `older` would manufacture
a fact the narrator never stated. That is the same review disposition
Phase 5C generalizes, and it is deliberately not decided here.
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


def item(fp, value, conf=0.9):
    return {"fieldPath": fp, "value": value, "confidence": conf}


def run(answer, items, profile=None):
    """Drive the SHIPPED extraction path with fixed model output."""
    req = EX.ExtractFieldsRequest(person_id="N", answer=answer,
                                  current_section="family_life")
    with mock.patch("api.db.get_profile", return_value=profile), \
         mock.patch.object(EX, "_extract_via_llm",
                           return_value=(list(items), "[stub]")):
        return EX.run_field_extraction(req)


def paths(resp):
    return [(i.fieldPath, i.value) for i in resp.items]


class AdultChildWordingBinds(unittest.TestCase):
    """`adult daughter` and `grown son` reach the children lane."""

    def test_an_adult_daughter_binds(self):
        r = run("My adult daughter Nina is a vet.",
                [item("family.children.firstName", "Nina")])
        self.assertEqual([("family.children.firstName", "Nina")], paths(r))

    def test_a_plain_daughter_binds_in_the_same_sentence_shape(self):
        """The control. Only the word `adult` differs."""
        r = run("My daughter Nina is a vet.",
                [item("family.children.firstName", "Nina")])
        self.assertEqual([("family.children.firstName", "Nina")], paths(r))

    def test_a_grown_son_binds(self):
        r = run("My grown son Peter runs a garage.",
                [item("family.children.firstName", "Peter")])
        self.assertEqual([("family.children.firstName", "Peter")], paths(r))

    def test_a_plain_son_binds_in_the_same_sentence_shape(self):
        r = run("My son Peter runs a garage.",
                [item("family.children.firstName", "Peter")])
        self.assertEqual([("family.children.firstName", "Peter")], paths(r))

    def test_an_adult_child_binds(self):
        r = run("My adult child Alex teaches piano.",
                [item("family.children.firstName", "Alex")])
        self.assertEqual([("family.children.firstName", "Alex")], paths(r))

    def test_no_age_is_invented_from_the_word_adult(self):
        """`adult` is a description, not a date of birth.

        The one thing a children-lane qualifier must never do is produce
        a numeric fact. Nothing in the response may carry a birth date
        the narrator did not state.
        """
        r = run("My adult daughter Nina is a vet.",
                [item("family.children.firstName", "Nina")])
        self.assertFalse(
            [p for p, _v in paths(r) if "dateOfBirth" in p or "age" in p.lower()],
            "an age or birth date was invented from the word `adult`")


class SiblingQualifiersBind(unittest.TestCase):
    """Ordering and half/step wording reach the siblings lane."""

    def test_an_older_brother_binds(self):
        r = run("My older brother Ray was a welder.",
                [item("siblings.firstName", "Ray")])
        self.assertEqual([("siblings.firstName", "Ray")], paths(r))

    def test_a_plain_brother_binds_in_the_same_sentence_shape(self):
        r = run("My brother Ray was a welder.",
                [item("siblings.firstName", "Ray")])
        self.assertEqual([("siblings.firstName", "Ray")], paths(r))

    def test_a_younger_sister_binds(self):
        r = run("My younger sister Joan was a nurse.",
                [item("siblings.firstName", "Joan")])
        self.assertEqual([("siblings.firstName", "Joan")], paths(r))

    def test_a_plain_sister_binds_in_the_same_sentence_shape(self):
        r = run("My sister Joan was a nurse.",
                [item("siblings.firstName", "Joan")])
        self.assertEqual([("siblings.firstName", "Joan")], paths(r))

    def test_a_half_sister_binds(self):
        r = run("My half-sister Joan was a nurse.",
                [item("siblings.firstName", "Joan")])
        self.assertEqual([("siblings.firstName", "Joan")], paths(r))

    def test_a_step_brother_binds(self):
        r = run("My stepbrother Ray was a welder.",
                [item("siblings.firstName", "Ray")])
        self.assertEqual([("siblings.firstName", "Ray")], paths(r))

    def test_a_little_brother_binds(self):
        """`little brother` is an ordering word, not a child."""
        r = run("My little brother Ray was a welder.",
                [item("siblings.firstName", "Ray")])
        self.assertEqual([("siblings.firstName", "Ray")], paths(r))

    def test_a_little_brother_does_not_become_a_child(self):
        r = run("My little brother Ray was a welder.",
                [item("siblings.firstName", "Ray")])
        self.assertFalse([p for p, _v in paths(r)
                          if p.startswith("family.children.")],
                         "a sibling was filed as a child")


class TheQualifierIsReadCorrectly(unittest.TestCase):
    """The interpreter's own reading. Cheap, and it localizes a failure."""

    def _read(self, phrase):
        from api.services.relationship_interpreter import interpret_phrase
        return interpret_phrase(phrase)

    def test_adult_daughter(self):
        r = self._read("my adult daughter Nina")
        self.assertEqual(("family.children", "daughter", "adult"),
                         (r.group, r.relation, r.qualifier))

    def test_grown_son_normalizes_to_the_same_qualifier(self):
        """Two wordings, one meaning. `grown` is not a third category."""
        r = self._read("my grown son Peter")
        self.assertEqual(("family.children", "son", "adult"),
                         (r.group, r.relation, r.qualifier))
        self.assertEqual("grown son", r.source_phrase,
                         "the narrator's own wording was not preserved")

    def test_older_brother(self):
        r = self._read("my older brother Ray")
        self.assertEqual(("siblings", "brother", "older"),
                         (r.group, r.relation, r.qualifier))

    def test_younger_sister(self):
        r = self._read("my younger sister Joan")
        self.assertEqual(("siblings", "sister", "younger"),
                         (r.group, r.relation, r.qualifier))

    def test_a_plain_relation_carries_no_qualifier(self):
        """The discriminating control — an empty qualifier is a claim too."""
        self.assertEqual("", self._read("my brother Ray").qualifier)
        self.assertEqual("", self._read("my daughter Nina").qualifier)

    def test_the_qualifier_never_replaces_the_relation(self):
        """`older brother` is a brother. `adult daughter` is a daughter."""
        for phrase, relation in (("my older brother Ray", "brother"),
                                 ("my younger sister Joan", "sister"),
                                 ("my adult daughter Nina", "daughter"),
                                 ("my grown son Peter", "son"),
                                 ("my half-sister Joan", "sister")):
            with self.subTest(phrase=phrase):
                self.assertEqual(relation, self._read(phrase).relation)


class TheQualifierIsReadButNotCarried(unittest.TestCase):
    """CURRENT BEHAVIOUR, measured 2026-09-05 — recorded, not endorsed.

    The interpreter reads `older` / `adult` correctly and the extracted
    item does not carry it anywhere. `siblings.birthOrder` exists, and
    `older` is not a birth order: deriving `birthOrder="1"` from the
    word would manufacture a fact about a family the narrator never
    stated, in a system whose whole Phase 5B is about not doing that.

    So the qualifier's destination is a Phase 5C question — the same
    "meaning with no schema destination" boundary that produced the
    `relationship_state_has_no_destination` review disposition — and
    this test exists so that a future session designing that
    destination has to come here and change a measurement rather than
    discover the gap again.
    """

    def test_no_birth_order_is_invented_from_older(self):
        r = run("My older brother Ray was a welder.",
                [item("siblings.firstName", "Ray")])
        self.assertFalse([p for p, _v in paths(r) if p.endswith(".birthOrder")],
                         "a birthOrder was manufactured from the word `older`")

    def test_the_qualifier_reaches_no_field_today(self):
        """If this fails, a destination was wired — update the record."""
        r = run("My older brother Ray was a welder.",
                [item("siblings.firstName", "Ray")])
        self.assertEqual([("siblings.firstName", "Ray")], paths(r))

    def test_the_interpreter_still_knows_it(self):
        """Non-vacuity: the value exists upstream, it is simply unused."""
        from api.services.relationship_interpreter import readings_in
        found = readings_in("My older brother Ray was a welder.")
        self.assertEqual(["older"], [f.qualifier for f in found])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
