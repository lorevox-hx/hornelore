"""Retrieval has to CHOOSE when the biography is substantial.

WHY A SECOND BIOGRAPHY SUITE
============================
`test_questionnaire_reaches_lori` establishes that saved answers reach
the prompt. This establishes that the RIGHT ones do, on a record big
enough that choosing wrongly is possible.

The distinction is not academic. Every assertion below reproduces a
failure that a live session showed and the small-record fixture could
not:

    "and my dad and siblings"          -> the father, and no siblings
    "tell me about my brothers and
     sisters"                          -> nothing at all
    "her notable life events"          -> an occupation
    "what can you tell me about my
     mom?"                             -> nothing (before punctuation
                                          handling)

The causes turned out to be small and specific, which is the point of
having a fixture that can show them:

  * `siblings` is PLURAL and the relation map held only `sibling`. Two
    separate captures were read as Lori declining to address them. She
    was never given them.
  * a flat result list spent the whole character cap on whichever
    subject came first — the father, whose entry is long — so the second
    subject in a two-part question was silently absent even once it
    matched.
  * naming a field ("notable life events") was not read at all, so the
    cap could be filled with unrelated stories while the requested field
    sat on record untouched.

THE FIXTURE IS FICTIONAL AND SHARED
===================================
`tests/harness/rich_narrator.py` holds it, and
`scripts/make_rich_synthetic_narrator.py` imports the same module to
write it into a live database through the product's routes. One
definition: two copies of a fixture stay equal until the first change.

No real narrator's record is read, written or referenced here.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))
sys.path.insert(0, str(REPO / "tests"))

from api.services import questionnaire_for_lori as qfl   # noqa: E402
from harness.rich_narrator import QUESTIONNAIRE          # noqa: E402

PID = "p-rich-fixture"


def _facts():
    """`load_facts` against an in-memory copy of the fixture.

    The real reader, the real shape, no live database. `load_facts` is
    `WHERE person_id = ?` throughout, so a single-narrator database
    exercises the same path a full one does.
    """
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE bio_builder_questionnaires "
                "(person_id TEXT, questionnaire_json TEXT, revision INT,"
                " updated_at TEXT)")
    con.execute("CREATE TABLE bio_builder_answer_provenance "
                "(person_id TEXT, section TEXT, entry_id TEXT, field TEXT,"
                " origin TEXT)")
    con.execute("INSERT INTO bio_builder_questionnaires VALUES (?,?,?,?)",
                (PID, json.dumps(QUESTIONNAIRE), 1, "2026-09-21"))
    con.commit()
    return qfl.load_facts(PID, con=con)


def _fields(detail: str):
    """The fields the block offered, in the order it offered them."""
    return [m.group(1) for m in re.finditer(r"^  .+ — (\w+):$",
                                            detail or "", re.M)]


class TheFixtureIsActuallyRich(unittest.TestCase):
    """A fixture too small to create pressure proves nothing.

    Pinned because the previous round's conclusion rested on a
    1,444-byte record whose turns had 650-900 tokens of headroom, while
    the failure being investigated had five.
    """

    def test_it_is_substantially_larger_than_the_small_fixture(self):
        self.assertGreater(len(json.dumps(QUESTIONNAIRE)), 5000)

    def test_it_has_enough_entries_to_choose_wrongly(self):
        entries = sum(len(v) if isinstance(v, list) else 1
                      for v in QUESTIONNAIRE.values())
        self.assertGreaterEqual(entries, 18)

    def test_siblings_are_populated(self):
        self.assertGreaterEqual(len(QUESTIONNAIRE.get("siblings") or []), 4)

    def test_it_carries_long_prose_not_just_short_facts(self):
        long_fields = [v for sec in QUESTIONNAIRE.values()
                       if isinstance(sec, list)
                       for e in sec for v in e.values()
                       if isinstance(v, str) and len(v) > 200]
        self.assertGreaterEqual(len(long_fields), 3)

    def test_it_carries_no_life_map_material(self):
        """Measured: Life Map contributes no prompt section.

        Including it would simulate budget pressure that does not exist.
        """
        blob = json.dumps(QUESTIONNAIRE).lower()
        for token in ("life_map", "lifemap", "life map"):
            with self.subTest(token=token):
                self.assertNotIn(token, blob)


class ATwoPartQuestionGetsBothParts(unittest.TestCase):

    def setUp(self):
        self.facts = _facts()

    def test_dad_and_siblings_returns_the_father(self):
        d = qfl.detail_for(self.facts, "and my dad and siblings")
        self.assertIn("Emrys", d)

    def test_dad_and_siblings_also_returns_every_sibling(self):
        """The live failure, twice, in two captures."""
        d = qfl.detail_for(self.facts, "and my dad and siblings")
        for name in ("Tamsin", "Rhodri", "Gwenllian", "Caradog"):
            with self.subTest(sibling=name):
                self.assertIn(name, d)

    def test_the_plural_alone_is_enough(self):
        """`siblings` must not need `sibling` to have been said."""
        d = qfl.detail_for(self.facts, "tell me about my siblings")
        self.assertIn("Tamsin", d)

    def test_brothers_and_sisters_means_the_same_shelf(self):
        d = qfl.detail_for(self.facts, "tell me about my brothers and sisters")
        for name in ("Tamsin", "Rhodri", "Gwenllian", "Caradog"):
            with self.subTest(sibling=name):
                self.assertIn(name, d)

    def test_parents_returns_both_parents(self):
        d = qfl.detail_for(self.facts, "what about my parents")
        self.assertIn("Marguerite", d)
        self.assertIn("Emrys", d)

    def test_no_subject_is_crowded_out_by_the_cap(self):
        """Round-robin, not first-come.

        The father's entry is long. Filling the cap in fact order spends
        it on him and drops the siblings without saying so.
        """
        d = qfl.detail_for(self.facts, "and my dad and siblings")
        self.assertLessEqual(len(d), 2400)
        present = sum(1 for n in ("Emrys", "Tamsin", "Rhodri",
                                  "Gwenllian", "Caradog") if n in d)
        self.assertEqual(present, 5)


class TheRequestedFieldComesFirst(unittest.TestCase):

    def setUp(self):
        self.facts = _facts()

    def test_notable_life_events_leads_when_asked_for(self):
        d = qfl.detail_for(self.facts,
                           "can you tell me about her notable life events",
                           recent_text="What can you tell me about my mom?")
        fields = _fields(d)
        self.assertTrue(fields, "nothing retrieved at all")
        self.assertEqual(fields[0], "notableLifeEvents")

    def test_the_events_themselves_are_present_not_just_the_occupation(self):
        """The live answer was 'she was a schoolteacher'."""
        d = qfl.detail_for(self.facts,
                           "can you tell me about her notable life events",
                           recent_text="What can you tell me about my mom?")
        self.assertIn("Culvert Row School", d)

    def test_a_story_request_retrieves_stories(self):
        d = qfl.detail_for(self.facts, "tell me a story about my grandmother")
        self.assertIn("memorableStories", _fields(d))

    def test_an_unqualified_question_still_returns_the_person(self):
        d = qfl.detail_for(self.facts, "What can you tell me about my mom?")
        self.assertIn("Marguerite", d)


class PronounsCarryTheSubjectForward(unittest.TestCase):

    def setUp(self):
        self.facts = _facts()

    def test_her_resolves_against_the_preceding_turn(self):
        d = qfl.detail_for(self.facts, "what about her school years",
                           recent_text="tell me about my mom")
        self.assertIn("Marguerite", d)

    def test_a_pronoun_with_no_context_retrieves_nothing(self):
        """Not a guess. Silence is the honest result.

        Returning a confident answer about the wrong relative is worse
        than returning none, and `recent_text` is the only thing that
        makes the pronoun resolvable.
        """
        d = qfl.detail_for(self.facts, "what about her school years",
                           recent_text="")
        self.assertEqual(d, "")

    def test_a_turn_naming_nobody_retrieves_nothing(self):
        """What keeps the default prompt small."""
        self.assertEqual(
            qfl.detail_for(self.facts, "that sounds lovely"), "")


class CollectionGuardTests(unittest.TestCase):

    def test_every_test_class_is_collected(self):
        import inspect
        mod = sys.modules[__name__]
        defined = {n for n, o in inspect.getmembers(mod, inspect.isclass)
                   if issubclass(o, unittest.TestCase)
                   and o.__module__ == __name__}
        loaded = unittest.defaultTestLoader.loadTestsFromModule(mod)
        seen = set()

        def walk(suite):
            for t in suite:
                if isinstance(t, unittest.TestSuite):
                    walk(t)
                else:
                    seen.add(type(t).__name__)
        walk(loaded)
        self.assertEqual(defined - seen, set())

    def test_nothing_follows_unittest_main(self):
        src = Path(__file__).read_text(encoding="utf-8")
        self.assertNotIn("\nclass ", src[src.rindex("unittest.main("):])


if __name__ == "__main__":
    unittest.main(verbosity=2)
