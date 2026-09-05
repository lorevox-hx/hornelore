"""Group-local kinship guard — the rebuild of the reverted add4753.

WO-LORI-ARCHIVE-TO-MEMOIR-02 Phase 3 (2026-09-04).

THE CASE, in the narrator's own words. Mable Hudson: "Otis died in 2005. Heart
attack at sixty-three." The extractor filed `parents.firstName=Otis` at 0.9
plus three more `parents_0` fields. Otis was her HUSBAND, and her stored
profile already said so. Tomasita/Domingo is the identical shape.

EVERY TEST HERE GOES THROUGH `run_field_extraction`. The first attempt shipped
19 passing tests that called the guard helper directly and handed it a
`repeatableGroup` key production does not have at that stage; the guard's
decisions were then overwritten downstream and reached no caller. Asserting on
the final `ExtractFieldsResponse` is the only way that failure is visible.

QUARANTINE, NOT DOWNGRADE. A lower-confidence `parents.firstName=Otis` is still
an approvable claim that Otis was Mable's father. The group leaves `items`
entirely and becomes one neutral review entry carrying every proposed field as
evidence.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "server" / "code") not in sys.path:
    sys.path.insert(0, str(ROOT / "server" / "code"))

from api.routers import extract as EX  # noqa: E402

MABLE = ("Otis died in 2005. Heart attack at sixty-three. The kids were grown "
         "— Charlene was in Atlanta with her family, Bernard in Detroit still.")
MABLE_PROFILE = {"profile_json": {
    "spouses": [{"firstName": "Otis", "lastName": "Bell"}],
    "parents": [{"firstName": "Clarence"}, {"firstName": "Ida"}]}}


def item(fp, value, conf=0.9):
    return {"fieldPath": fp, "value": value, "confidence": conf}


def run(answer, items, profile=None, target=None, force_rules=False):
    """Drive the SHIPPED pipeline. force_rules exercises the fallback tail."""
    req = EX.ExtractFieldsRequest(
        person_id="narrator-1", answer=answer,
        current_section="family_life", current_target_path=target)
    llm = ([], "[stub]") if force_rules else (list(items), "[stub]")
    ctx = [mock.patch("api.db.get_profile", return_value=profile),
           mock.patch.object(EX, "_extract_via_llm", return_value=llm)]
    if force_rules:
        ctx.append(mock.patch.object(EX, "_extract_via_rules",
                                     return_value=list(items)))
    with ctx[0], ctx[1]:
        if force_rules:
            with ctx[2]:
                return EX.run_field_extraction(req)
        return EX.run_field_extraction(req)


def paths(resp):
    return [i.fieldPath for i in resp.items]


def entries(resp):
    return [c for c in resp.clarification_required
            if c.get("kind") == "unbound_relationship"]


class TheOtisCase(unittest.TestCase):

    ITEMS = [item("parents.firstName", "Otis"),
             item("parents.birthDate", "1922", 0.7),
             item("parents.deathDate", "2005"),
             item("parents.notableLifeEvents", "died 2005", 0.8),
             item("residence.place", "Plymouth Road")]

    def test_no_executable_parents_item_survives(self):
        r = run(MABLE, self.ITEMS, MABLE_PROFILE)
        self.assertFalse([p for p in paths(r) if p.startswith("parents.")],
                         "a false parent fact reached the caller")

    def test_the_WHOLE_group_is_quarantined_not_just_firstName(self):
        """The reverted guard downgraded firstName and left the dates at full
        authority under the same doubt."""
        r = run(MABLE, self.ITEMS, MABLE_PROFILE)
        e = entries(r)
        self.assertEqual(1, len(e))
        got = {(p["fieldPath"], p["value"]) for p in e[0]["proposed_items"]}
        self.assertEqual(
            {("parents.firstName", "Otis"), ("parents.birthDate", "1922"),
             ("parents.deathDate", "2005"),
             ("parents.notableLifeEvents", "died 2005")}, got)

    def test_the_safe_item_in_the_same_answer_survives(self):
        r = run(MABLE, self.ITEMS, MABLE_PROFILE)
        self.assertIn("residence.place", paths(r),
                      "no collateral loss — Plymouth Road is not in doubt")

    def test_both_reasons_are_recorded_in_precedence_order(self):
        r = run(MABLE, self.ITEMS, MABLE_PROFILE)
        e = entries(r)[0]
        self.assertEqual(["identity_conflict", "relationship_unstated"],
                         e["reasons"])
        self.assertEqual("identity_conflict", e["reason"])

    def test_the_entry_is_neutral_and_not_applied(self):
        r = run(MABLE, self.ITEMS, MABLE_PROFILE)
        e = entries(r)[0]
        self.assertTrue(e["not_applied"])
        self.assertIn("relationship to you", e["label"])
        self.assertNotIn("father", e["label"].lower(),
                         "the label must not assert the error it is asking about")
        self.assertNotIn("fieldPath", e,
                         "a quarantine entry must carry NO executable fieldPath")
        self.assertEqual("parents.firstName", e["proposed_fieldPath"])

    def test_the_same_shape_on_the_rules_fallback_path(self):
        r = run(MABLE, self.ITEMS, MABLE_PROFILE, force_rules=True)
        self.assertEqual("rules_fallback", r.method)
        self.assertFalse([p for p in paths(r) if p.startswith("parents.")])
        self.assertEqual(1, len(entries(r)))


class LocalEvidenceDecides(unittest.TestCase):

    def test_stated_relationship_in_the_same_sentence_is_supported(self):
        r = run("My father Clarence Hudson worked at the plant for thirty years.",
                [item("parents.firstName", "Clarence"),
                 item("parents.lastName", "Hudson")], MABLE_PROFILE)
        self.assertEqual(["parents.firstName", "parents.lastName"], paths(r))
        self.assertEqual([], entries(r))

    def test_evidence_does_not_leak_across_sentences(self):
        """THE DEFECT THAT SANK THE FIRST ATTEMPT. One 'my father' anywhere
        licensed every parents.* item in the whole answer."""
        r = run("My father Clarence worked at the plant. Otis died in 2005.",
                [item("parents.firstName", "Clarence"),
                 item("parents.firstName", "Otis")], MABLE_PROFILE)
        vals = [i.value for i in r.items if i.fieldPath == "parents.firstName"]
        self.assertIn("Clarence", vals)
        self.assertNotIn("Otis", vals,
                         "a relationship stated about Clarence licensed Otis")
        self.assertEqual(1, len(entries(r)))

    def test_a_mixed_spouse_and_parent_answer_keeps_the_valid_group(self):
        r = run("My father Clarence worked at the plant. I married Otis in 1965.",
                [item("parents.firstName", "Clarence"),
                 item("family.spouse.firstName", "Otis")], MABLE_PROFILE)
        self.assertIn("parents.firstName", paths(r))
        self.assertIn("family.spouse.firstName", paths(r),
                      "'I married Otis' states the spouse relationship locally")
        self.assertEqual([], entries(r))

    def test_narrators_say_dad_without_my(self):
        """The first attempt reused conflict-cue regexes requiring the literal
        word 'my', so 'Dad was Kent Horne' read as unstated."""
        r = run("Dad was Kent Horne, born in Stanley.",
                [item("parents.firstName", "Kent")], None)
        self.assertEqual(["parents.firstName"], paths(r))


class NameEqualityAloneNeverRefuses(unittest.TestCase):

    JOHN_PROFILE = {"profile_json": {"spouses": [{"firstName": "John"}]}}

    def test_father_John_survives_a_spouse_named_John(self):
        """Explicit local wording outranks a same-first-name collision: a
        narrator who says 'my father John' has told us which John."""
        r = run("My father John was a machinist at the yard.",
                [item("parents.firstName", "John")], self.JOHN_PROFILE)
        self.assertEqual(["parents.firstName"], paths(r))
        self.assertEqual([], entries(r))

    def test_the_collision_only_adds_a_reason_to_an_already_unsupported_group(self):
        r = run("John died in 2005.", [item("parents.firstName", "John")],
                self.JOHN_PROFILE)
        e = entries(r)
        self.assertEqual(1, len(e))
        self.assertIn("identity_conflict", e[0]["reasons"])

    def test_an_unsupported_group_with_no_collision_is_only_unstated(self):
        r = run("Otis died in 2005.", [item("parents.firstName", "Otis")], None)
        self.assertEqual(["relationship_unstated"], entries(r)[0]["reasons"])

    def test_a_profile_outage_does_not_lose_the_local_check(self):
        with mock.patch("api.db.get_profile", side_effect=RuntimeError("db")):
            with mock.patch.object(EX, "_extract_via_llm",
                                   return_value=([item("parents.firstName", "Otis")],
                                                 "[stub]")):
                r = EX.run_field_extraction(EX.ExtractFieldsRequest(
                    person_id="n", answer="Otis died in 2005."))
        self.assertEqual([], [p for p in paths(r) if p.startswith("parents.")])
        self.assertEqual(["relationship_unstated"], entries(r)[0]["reasons"])


class EvidenceIsBoundToTheEntity(unittest.TestCase):
    """Gaps found in review of d58c42d. A sentence-wide test still leaked, and
    an unlocatable subject fell back to the WHOLE ANSWER."""

    def test_a_cue_about_harold_does_not_authorise_otis(self):
        """"My father Harold worked at Firestone and Otis died in 2005."
        Parent language sits in Otis's sentence. Sentence-wide passed both."""
        r = run("My father Harold worked at Firestone and Otis died in 2005.",
                [item("parents.firstName", "Harold"),
                 item("parents.firstName", "Otis")], None)
        vals = [i.value for i in r.items if i.fieldPath == "parents.firstName"]
        self.assertEqual(["Harold"], vals)
        self.assertEqual(["Otis's relationship to you"],
                         [e["label"] for e in entries(r)])

    def test_an_intervening_person_blocks_a_singular_cue(self):
        """"My father Harold knew Otis." — five tokens, so a fixed ±4 window
        puts 'father' inside Otis's span whatever its size. Shrinking the
        window is not the fix; it would break the ordinary valid forms in
        OrdinaryFormsAreNotQuarantined. A SINGULAR cue describes one person,
        and another named person standing between the cue and this name is
        what breaks the association."""
        r = run("My father Harold knew Otis.",
                [item("parents.firstName", "Harold"),
                 item("parents.firstName", "Otis")], None)
        vals = [i.value for i in r.items if i.fieldPath == "parents.firstName"]
        self.assertEqual(["Harold"], vals)
        self.assertEqual(["Otis's relationship to you"],
                         [e["label"] for e in entries(r)])

    def test_a_plural_cue_still_reaches_past_an_intervening_name(self):
        """The barrier must not break lists: a PLURAL cue opens a set, and
        Charlene standing before Bernard makes him part of it, not cut off
        from it."""
        r = run("We had two children, Charlene and Bernard.",
                [item("family.children.firstName", "Charlene"),
                 item("family.children.firstName", "Bernard")], None)
        self.assertEqual(["family.children.firstName"] * 2, paths(r))
        self.assertEqual([], entries(r))

    def test_a_name_before_the_plural_cue_is_not_in_its_list(self):
        """A plural cue opens a set; only names AFTER it are in that set.

        The fixture puts the name and a SAME-ROLE plural cue in one sentence,
        name first, and places the cue outside the singular window. An earlier
        version used 'Otis died. We had two children...' where Otis is a
        parents item and the children cue never applied to his role — so the
        position rule was never exercised and a mutation removing it passed.
        """
        r = run("Ida was born in Akron and my parents moved there in 1930.",
                [item("parents.firstName", "Ida")], None)
        self.assertEqual([], paths(r),
                         "'Ida' preceded the cue and was swept into its set")
        self.assertEqual(["Ida's relationship to you"],
                         [e["label"] for e in entries(r)])

    def test_a_name_after_the_same_plural_cue_IS_in_its_list(self):
        """The control for the test above: reverse the order and it executes,
        so the rule is about position rather than about that sentence."""
        r = run("My parents moved to Akron in 1930 and Ida was born there.",
                [item("parents.firstName", "Ida")], None)
        self.assertEqual(["parents.firstName"], paths(r))
        self.assertEqual([], entries(r))

    # ── NAMELESS GROUPS ────────────────────────────────────────────────
    # CHANGED 2026-09-04, deliberately. This block used to hold a single test
    # asserting that a group with no firstName ALWAYS quarantines, on the
    # fixture "My father Harold worked at Firestone. He died in 2005."
    #
    # That rule was too strong and it cost six live cases -- 015, 105, 106,
    # 109, 113 and 214 -- whose narrators stated the relationship as plainly
    # as it can be stated: "My dad was born in Stanley." There is no name in
    # that sentence to build a window around, so `stated` could never become
    # true and the plainest form in the corpus was quarantined.
    #
    # The property the old test defended is REAL and is still defended: a
    # nameless group must not borrow evidence from across the answer. What
    # replaced the blanket refusal is locality -- the value's own sentence
    # must carry the cue, or inherit it from the sentence immediately before
    # via an unambiguous pronoun. The five refusals below are the teeth.
    #
    # The old fixture now executes, and that is CORRECT: "My father Harold
    # worked at Firestone. He died in 2005." does state the father's death
    # year. Keeping it as a refusal was asserting that a true, plainly-stated
    # fact should be withheld.

    def test_a_pronoun_inherits_the_previous_sentences_relationship(self):
        """The case_113 shape: 'Dad's last name was Horne. He was born in
        Stanley.'"""
        r = run("My father Harold worked at Firestone. He died in 2005.",
                [item("parents.deathDate", "2005")], None)
        # The R4-I rerouter mirrors a parent death date into the narrative
        # field, so production emits BOTH. Asserting only the date would be
        # asserting a shape this test invented rather than the one shipped.
        self.assertEqual(["parents.deathDate", "parents.notableLifeEvents"],
                         sorted(paths(r)))
        self.assertEqual([], entries(r))

    def test_a_nameless_group_refuses_when_another_person_is_named(self):
        """No pronoun, and somebody else is the subject of that sentence."""
        r = run("My father Harold worked at Firestone. Otis died in 2005.",
                [item("parents.deathDate", "2005")], None)
        self.assertEqual([], paths(r))
        self.assertEqual(1, len(entries(r)))

    def test_a_nameless_group_refuses_with_no_cue_anywhere(self):
        r = run("We moved to Akron. The year was 2005.",
                [item("parents.deathDate", "2005")], None)
        self.assertEqual([], paths(r))
        self.assertEqual(1, len(entries(r)))

    def test_a_pronoun_is_refused_when_it_is_ambiguous(self):
        """Another PROPOSED person across the pair makes 'he' unsafe."""
        r = run("My father Harold worked at Firestone. "
                "He and Otis died in 2005.",
                [item("parents.deathDate", "2005"),
                 item("parents.firstName", "Otis")], None)
        self.assertEqual([], paths(r))

    def test_a_value_that_cannot_be_located_is_refused(self):
        """1931 appears nowhere in the answer, so nothing grounds it."""
        r = run("My father was a hard man.",
                [item("parents.deathDate", "1931")], None)
        self.assertEqual([], paths(r))
        self.assertEqual(1, len(entries(r)))

    def test_a_modifier_between_the_count_and_the_noun_still_opens_a_list(self):
        """"my two OLDER brothers Vincent and Jason" — case_002, 047, 079."""
        r = run("It was my mom Janice and my dad Kent, and my two older "
                "brothers Vincent and Jason.",
                [item("siblings.firstName", "Vincent"),
                 item("siblings.firstName", "Jason")], None)
        self.assertEqual([], entries(r))
        self.assertEqual(2, len([p for p in paths(r)
                                 if p == "siblings.firstName"]))

    def test_a_firstName_holding_the_whole_list_is_split(self):
        """The model sometimes emits one field carrying every name."""
        r = run("We had three boys — Vincent, Jason, and Christopher.",
                [item("family.children.firstName",
                      "Vincent, Jason, Christopher")], None)
        self.assertEqual([], entries(r),
                         "a joined firstName matched nobody in the roster")

    def test_an_alias_does_not_consume_a_place_in_the_count(self):
        """"Vince — Vincent Edward —" is ONE brother, not two.

        Counting both closed a list of two before the second brother.
        """
        a = ("I've got two brothers. Vince — Vincent Edward — is the oldest, "
             "then Jason.")
        scope = {n.lower() for n in EX._plural_cue_scope(
            a, "siblings", ["Vince", "Vincent", "Jason"])}
        self.assertIn("jason", scope, scope)
        self.assertIn("vincent", scope, "the alias must still be IN scope")

    def test_without_a_count_the_list_stops_at_a_sentence_naming_nobody(self):
        """THE BOUND that keeps this from becoming answer-wide.

        No count, so the list is contiguous only: a sentence that names none
        of the roster ends it, and a name after that sentence is NOT in scope.
        Deleting this break leaves a cue authorising the rest of the answer,
        which is the permission the guard exists to withdraw.
        """
        a = ("My brothers were a lot older. Vince was the oldest. "
             "The winter of 1958 was terrible. Then Jason.")
        scope = {n.lower() for n in EX._plural_cue_scope(
            a, "siblings", ["Vince", "Jason"])}
        self.assertIn("vince", scope, scope)
        self.assertNotIn("jason", scope,
                         "an intervening sentence naming nobody must end an "
                         "uncounted list — otherwise the cue is answer-wide")

    def test_a_possessive_side_qualifier_is_transparent_to_the_window(self):
        """"My grandmother on my mother's side was Josie" — case_031.

        'grandmother' sits seven tokens from 'Josie' and 'mother' stands
        between them, so a plain ±4 window with barriers missed the cue and
        then blamed the wrong person. The qualifier says WHICH grandmother.
        """
        r = run("My grandmother on my mother's side was Josie.",
                [item("grandparents.firstName", "Josie")], None)
        self.assertIn("grandparents.firstName", paths(r))
        self.assertEqual([], entries(r))

    def test_transparency_does_not_disarm_a_real_intervening_person(self):
        """The qualifier is transparent; a PERSON is still a barrier.

        Ida reaches 'grandmother' through the qualifier. Josie stands on the
        far side of Ida and does not, which is the barrier still working.
        """
        r = run("My grandmother on my mother's side was Ida, and her friend "
                "Josie visited often.",
                [item("grandparents.firstName", "Ida"),
                 item("grandparents.firstName", "Josie")], None)
        self.assertEqual([("grandparents.firstName", "Ida")],
                         [(i.fieldPath, i.value) for i in r.items])
        self.assertEqual(["Josie"], [e["value"] for e in entries(r)])

    def test_a_competing_role_cue_still_closes_the_list(self):
        """The bound that keeps this from becoming answer-wide."""
        a = ("I've got two older brothers. Vince was the oldest. "
             "Mom and Dad were living in Germany then. Then Jason.")
        scope = {n.lower() for n in EX._plural_cue_scope(
            a, "siblings", ["Vince", "Jason"])}
        self.assertNotIn("jason", scope,
                         "a parents cue must end a list of siblings")

    # ── "we got married" resolved by the next sentence (case_091) ───────
    def _spouse(self, answer, items):
        return run(answer, items, None)

    def test_the_sentence_after_we_got_married_names_the_spouse(self):
        """case_091, live: 'We got married on October 10th. I was twenty and
        Kent was nineteen.'"""
        r = self._spouse(
            "We got married on October 10th. I was twenty and Kent was "
            "nineteen — I was older! It was a small affair.",
            [item("family.spouse.firstName", "Kent")])
        self.assertIn("family.spouse.firstName", paths(r))
        self.assertEqual([], entries(r))

    def test_two_candidates_in_that_sentence_refuse(self):
        """The function must not choose between people."""
        r = self._spouse(
            "We got married in 1959. Kent and Harold were both there.",
            [item("family.spouse.firstName", "Kent"),
             item("family.spouse.firstName", "Harold")])
        self.assertEqual([], paths(r))

    def test_they_got_married_resolves_nothing(self):
        """Third-person marriage says nothing about the narrator's spouse."""
        r = self._spouse(
            "They got married in 1959. Kent was nineteen.",
            [item("family.spouse.firstName", "Kent")])
        self.assertEqual([], paths(r))

    def test_an_explicit_different_role_wins(self):
        """'My brother Kent' assigns Kent a role, and it is not spouse."""
        r = self._spouse(
            "We got married in 1959. My brother Kent was nineteen.",
            [item("family.spouse.firstName", "Kent")])
        self.assertEqual([], paths(r))

    def test_the_continuation_reaches_only_the_next_sentence(self):
        r = self._spouse(
            "We got married in 1959. It was a small affair. "
            "Kent was nineteen.",
            [item("family.spouse.firstName", "Kent")])
        self.assertEqual([], paths(r))

    def test_a_paragraph_break_ends_the_continuation(self):
        r = self._spouse(
            "We got married in 1959.\n\nKent was nineteen.",
            [item("family.spouse.firstName", "Kent")])
        self.assertEqual([], paths(r))

    def test_an_ambiguous_year_quarantines_rather_than_guessing(self):
        """A year is the weakest locator in the corpus.

        "My father died in 1967. We sold the farm in 1967." puts the value in
        two sentences saying different things, and accepting the first
        supporting one is choosing an answer at random.
        """
        r = run("My father died in 1967. We sold the farm in 1967.",
                [item("parents.deathDate", "1967")], None)
        self.assertEqual([], paths(r))
        self.assertEqual(1, len(entries(r)))

    def test_an_unambiguous_repeat_still_executes(self):
        """Ambiguity is DISAGREEMENT, not repetition. Both sentences are
        about a parent, so there is nothing to choose between."""
        r = run("My father died in 1967. My mother was widowed in 1967.",
                [item("parents.deathDate", "1967")], None)
        self.assertIn("parents.deathDate", paths(r))
        self.assertEqual([], entries(r))

    def test_the_pronoun_reaches_exactly_one_sentence_back(self):
        """Two sentences is borrowing, not continuation."""
        r = run("My father Harold worked at Firestone. It was a long job. "
                "He died in 2005.",
                [item("parents.deathDate", "2005")], None)
        self.assertEqual([], paths(r))
        self.assertEqual(1, len(entries(r)))

    def test_a_name_the_narrator_never_said_is_quarantined(self):
        """A hallucinated firstName previously borrowed any parent wording
        elsewhere in the answer."""
        r = run("Otis died in 2005. My father Harold worked at Firestone.",
                [item("parents.firstName", "Ida")], None)
        self.assertEqual([], paths(r))
        self.assertEqual(["Ida's relationship to you"],
                         [e["label"] for e in entries(r)])

    def test_matching_is_token_bounded_not_substring(self):
        """'Ida' must not find itself inside 'Idaho'.

        The fixture is chosen so the two behaviours DIFFER. An earlier version
        used "We moved to Idaho in 1961." with no cue present — substring and
        token matching both quarantined it, so the test could not tell them
        apart and a substring mutation passed. Here the spurious 'Idaho' match
        sits four tokens from 'father', so substring matching would EXECUTE
        parents.firstName=Ida — a name the narrator never said."""
        r = run("My father was born in Idaho.",
                [item("parents.firstName", "Ida")], None)
        self.assertEqual([], paths(r),
                         "'Ida' was located inside 'Idaho' and borrowed the "
                         "parent cue beside it")
        self.assertEqual(1, len(entries(r)))

    def test_a_repeated_name_is_supported_by_ANY_occurrence(self):
        """Using only the first occurrence would quarantine a relationship the
        narrator stated later in the same turn."""
        r = run("Otis was at the plant. My husband Otis died in 2005.",
                [item("family.spouse.firstName", "Otis")], None)
        self.assertEqual(["family.spouse.firstName"], paths(r))
        self.assertEqual([], entries(r))


class OrdinaryFormsAreNotQuarantined(unittest.TestCase):
    """False quarantine costs a narrator a fact. These are the shapes people
    actually use, and all of them must execute."""

    CASES = [
        ("We had two children, Charlene and Bernard.",
         [("family.children.firstName", "Charlene"),
          ("family.children.firstName", "Bernard")]),
        ("Charlene is my daughter.", [("family.children.firstName", "Charlene")]),
        ("Otis died. The kids were grown — Charlene was in Atlanta.",
         [("family.children.firstName", "Charlene")]),
        ("Dad was Kent Horne, born in Stanley.",
         [("parents.firstName", "Kent")]),
        ("I married Otis in 1965.", [("family.spouse.firstName", "Otis")]),
        ("My brother Vince was born in Germany.",
         [("siblings.firstName", "Vince")]),
    ]

    def test_no_false_quarantine(self):
        for answer, fields in self.CASES:
            with self.subTest(answer=answer):
                r = run(answer, [item(fp, v) for fp, v in fields], None)
                self.assertEqual([fp for fp, _ in fields], paths(r))
                self.assertEqual([], entries(r))


class ReasonsCompose(unittest.TestCase):

    def test_a_low_confidence_otis_carries_all_three_reasons(self):
        """Gap found in review: kinship ran BEFORE transcript safety and
        removed the group, so low_confidence vanished with it. The operator
        was told the relationship was unknown but not that the audio was
        unclear — a separate reason to distrust the value itself."""
        req = EX.ExtractFieldsRequest(
            person_id="n", answer="Otis died in 2005.",
            transcript_source="whisper", transcript_confidence=0.42,
            confirmation_required=True)
        with mock.patch("api.db.get_profile", return_value=MABLE_PROFILE), \
             mock.patch.object(EX, "_extract_via_llm",
                               return_value=([item("parents.firstName", "Otis")],
                                             "[s]")):
            r = EX.run_field_extraction(req)
        e = entries(r)
        self.assertEqual(1, len(e))
        self.assertEqual(["identity_conflict", "relationship_unstated",
                          "low_confidence"], e[0]["reasons"])

    def test_the_superseded_transcript_entry_is_not_shown_twice(self):
        req = EX.ExtractFieldsRequest(
            person_id="n", answer="Otis died in 2005.",
            transcript_source="whisper", transcript_confidence=0.42,
            confirmation_required=True)
        with mock.patch("api.db.get_profile", return_value=MABLE_PROFILE), \
             mock.patch.object(EX, "_extract_via_llm",
                               return_value=([item("parents.firstName", "Otis")],
                                             "[s]")):
            r = EX.run_field_extraction(req)
        self.assertEqual(1, len(r.clarification_required),
                         "one value must not raise two prompts, one of them "
                         "naming a field that is no longer executable")
    """A kinship quarantine and a transcript-safety downgrade can both apply
    to one turn; neither may erase the other's explanation."""

    def test_transcript_safety_reasons_are_retained_alongside(self):
        req = EX.ExtractFieldsRequest(
            person_id="n",
            answer="My father Clarence worked there. Otis died in 2005.",
            transcript_source="whisper", transcript_confidence=0.42,
            confirmation_required=True)
        items = [item("parents.firstName", "Clarence"),
                 item("parents.firstName", "Otis")]
        with mock.patch("api.db.get_profile", return_value=MABLE_PROFILE), \
             mock.patch.object(EX, "_extract_via_llm", return_value=(items, "[s]")):
            r = EX.run_field_extraction(req)
        kinds = {c.get("kind") for c in r.clarification_required}
        self.assertIn("unbound_relationship", kinds)
        self.assertTrue(
            any(c.get("kind") != "unbound_relationship"
                for c in r.clarification_required),
            "the transcript-safety clarification for Clarence was lost")
        clarence = [i for i in r.items if i.value == "Clarence"][0]
        self.assertIn("low_confidence", clarence.confirmation_reasons)


PAT_PROFILE = {"profile_json": {
    "spouses": [{"firstName": "Jim", "lastName": "Whitmore"}],
    "parents": [{"firstName": "Walter"}, {"firstName": "Dorothy"}]}}


class TheJimCase(unittest.TestCase):
    """Pat's husband, the third spouse fixture — and the last one covered.

    ── WHY THIS CLASS EXISTS, 2026-09-05 ──────────────────────────────

    `WO-LORI-ARCHIVE-TO-MEMOIR-02` Phase 3 lists three spouse fixtures and
    its exit gate says all three bind correctly. Measured against the
    suite: **`Otis` appeared in five test files and `Domingo` in two.
    `Jim` appeared in NONE.** Two of three were demonstrated and the
    third was asserted, so that box stayed unchecked at acceptance.

    The wording is Pat's own, from
    `scripts/run_pat_teacher_betty_harness.py`: *"I met James Whitmore —
    Jim — the summer after I graduated... We were married in 1970."*
    That is the Otis shape exactly — a husband named in a passage dense
    with other people, where a sentence-wide reading can hand him to
    `parents.*`.

    These run the SHIPPED `run_field_extraction`, like every other test
    in this file. The LLM is stubbed so the INPUT is fixed; the binding
    decision under test is production's.
    """

    def test_jim_does_not_enter_parents_from_a_marriage_sentence(self):
        """The plain case: marriage language, no parent language at all."""
        r = run("I met James Whitmore — Jim — the summer after I graduated. "
                "We were married in 1970.",
                [item("parents.firstName", "Jim")], PAT_PROFILE)
        vals = [i.value for i in r.items if i.fieldPath == "parents.firstName"]
        self.assertEqual([], vals, "Pat's husband was filed as her parent")

    def test_a_parent_cue_elsewhere_does_not_authorise_jim(self):
        """The Otis failure, in Pat's words.

        Parent language sits in the same passage as the husband's name. A
        sentence-wide reading passes both; local evidence must not.
        """
        r = run("My father Walter worked at the rubber plant and Jim died in 2018.",
                [item("parents.firstName", "Walter"),
                 item("parents.firstName", "Jim")], PAT_PROFILE)
        vals = [i.value for i in r.items if i.fieldPath == "parents.firstName"]
        self.assertEqual(["Walter"], vals)
        self.assertEqual(["Jim's relationship to you"],
                         [e["label"] for e in entries(r)])

    def test_jim_binds_as_the_spouse_he_is(self):
        """Positive control. A guard that only ever refuses proves nothing.

        The same name, in the same passage, reaching the spouse field
        when the narrator's language says husband.
        """
        r = run("My husband Jim and I were married in 1970.",
                [item("family.spouse.firstName", "Jim")], PAT_PROFILE)
        vals = [i.value for i in r.items
                if i.fieldPath == "family.spouse.firstName"]
        self.assertEqual(["Jim"], vals)
        self.assertEqual([], entries(r))

    def test_the_fixture_wording_is_the_narrators_own(self):
        """Measured against the shipped harness, not transcribed by hand.

        A fixture that quotes a passage which has since changed is
        testing a sentence nobody says any more.
        """
        harness = (ROOT / "scripts"
                   / "run_pat_teacher_betty_harness.py").read_text(encoding="utf-8")
        self.assertIn("I met James Whitmore — Jim —", harness)
        self.assertIn("We were married in 1970", harness)


if __name__ == "__main__":
    unittest.main()
