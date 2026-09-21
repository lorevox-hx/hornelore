"""The biography an operator types must reach Lori. WO-QUESTIONNAIRE-REACHES-LORI-01.

THE FINDING, in the work order's words:

    An operator saves `parents[1].occupation = "ore dock foreman"`. It is
    durably stored, versioned, audited and recoverable — and Lori cannot
    see it.

`prompt_composer` built her prompt from `profiles.profile_json`,
`interview_projections`, the `people` row, the runtime payload and
transcripts. It never read `bio_builder_questionnaires` — verified
2026-09-20, zero references.

WHY THE FIX IS A READ AND NOT THE FAN-OUT FLAG
-----------------------------------------------
The WO names a second break: `HORNELORE_QUESTIONNAIRE_BIO_FACTS_WRITE=1`
would not carry an occupation anyway, because `_apply_parents` writes
three keys and that is not one of them. And its carrier,
`db.update_profile_json`, merges at the TOP LEVEL, so a patch containing
`parents` replaces the whole array — the lossy-roundtrip shape, pointed
at a second table.

So the questionnaire is READ at compose time. Nothing is copied,
`update_profile_json` is not on the path, and there is no second version
of a fact to drift.

SYNTHETIC NARRATORS ONLY. No family record is read.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))
sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(REPO / "tests" / "harness"))

from fastapi_stub import install as _install_stub  # noqa: E402
_install_stub()

import synthetic_narrator as syn  # noqa: E402
from api import prompt_composer as pc  # noqa: E402
from api.services import questionnaire_for_lori as qfl  # noqa: E402


BERTIL = {
    "personal": {"fullName": "Alda Quillfeather", "placeOfBirth": "Marrow Bay"},
    "parents": [{
        "_entryId": "e-father", "relation": "father", "firstName": "Bertil",
        "occupation": "ore dock foreman", "birthPlace": "Marrow Bay",
    }, {
        "_entryId": "e-mother", "relation": "mother", "firstName": "Sigrid",
        "occupation": "schoolteacher",
    }],
}


class _Case(unittest.TestCase):

    def setUp(self):
        self.db = syn.build()
        self._restore = syn.use(self.db)

    def tearDown(self):
        self._restore()

    def _save(self, pid, doc, provenance=()):
        """What the Bio Builder save path leaves behind."""
        c = sqlite3.connect(self.db)
        c.execute("UPDATE bio_builder_questionnaires SET questionnaire_json=?, "
                  "revision=revision+1 WHERE person_id=?", (json.dumps(doc), pid))
        for section, entry_id, field, origin in provenance:
            c.execute("INSERT OR REPLACE INTO bio_builder_answer_provenance "
                      "(person_id, section, entry_id, field, origin, origin_at) "
                      "VALUES (?,?,?,?,?,?)",
                      (pid, section, entry_id, field, origin, "2026-09-20T00:00:00"))
        c.commit(); c.close()

    def _facts(self, pid):
        return qfl.load_facts(pid)

    def _seed(self, pid):
        return pc._build_profile_seed(pid) or {}


class TheOreDockForeman(_Case):
    """The work order's own example, end to end."""

    def test_the_occupation_reaches_the_seed(self):
        self._save(syn.ALDA, BERTIL,
                   [("parents", "e-father", "occupation", "operator_direct")])
        block = self._seed(syn.ALDA).get("biography_block") or ""
        self.assertIn("ore dock foreman", block,
                      "the fact the WO was written about still does not reach Lori")
        self.assertIn("Bertil", block, "and it is attached to the person it is about")

    def test_it_survives_a_reopen(self):
        """Save, read it back the way Bio Builder does, then compose."""
        self._save(syn.ALDA, BERTIL,
                   [("parents", "e-father", "occupation", "operator_direct")])
        c = sqlite3.connect(self.db)
        stored = json.loads(c.execute(
            "SELECT questionnaire_json FROM bio_builder_questionnaires "
            "WHERE person_id=?", (syn.ALDA,)).fetchone()[0])
        c.close()
        self.assertEqual(stored["parents"][0]["occupation"], "ore dock foreman")
        self.assertIn("ore dock foreman", self._seed(syn.ALDA).get("biography_block") or "")

    def test_a_second_parent_is_not_lost(self):
        """The lossy-roundtrip shape, checked at the read end: both
        entries must arrive, not just the first."""
        self._save(syn.ALDA, BERTIL)
        block = self._seed(syn.ALDA).get("biography_block") or ""
        self.assertIn("ore dock foreman", block)
        self.assertIn("schoolteacher", block)

    def test_entries_keep_their_own_identity(self):
        facts = self._facts(syn.ALDA) if self._save(syn.ALDA, BERTIL) is None else []
        ids = {f["entry_id"] for f in facts if f["section"] == "parents"}
        self.assertEqual(ids, {"e-father", "e-mother"},
                         "two parents collapsed into one entry")


class ProvenanceSurvivesTheHop(_Case):

    def test_an_accepted_suggestion_is_marked_as_one(self):
        self._save(syn.ALDA, BERTIL,
                   [("parents", "e-father", "occupation", "operator_direct"),
                    ("parents", "e-father", "birthPlace", "ai_suggested")])
        block = self._seed(syn.ALDA).get("biography_block") or ""
        # MIXED origins on one person must name WHICH field, or an
        # operator-typed occupation gets labelled machine-proposed.
        self.assertIn("Lori proposed, agreed: birthPlace", block)
        self.assertNotIn("[Lori proposed this; a person agreed]", block,
                         "a mixed-origin entry must not be blanket-labelled")

    def test_a_narrator_statement_is_marked_differently(self):
        self._save(syn.ALDA, BERTIL,
                   [("parents", "e-father", "occupation", "narrator_direct")])
        self.assertIn("the narrator said this",
                      self._seed(syn.ALDA).get("biography_block") or "")

    def test_unrecorded_origins_are_stated_once_not_per_line(self):
        """A marker on every line is a marker nobody reads."""
        self._save(syn.ALDA, BERTIL)          # no provenance at all
        block = self._seed(syn.ALDA).get("biography_block") or ""
        self.assertIn("before per-answer origins were recorded", block)
        self.assertNotIn("[origin not recorded]", block)


class FactsAreNotRecollections(_Case):
    """The rule the WO says must be stated wherever the fact is injected."""

    def setUp(self):
        super().setUp()
        self._save(syn.ALDA, BERTIL,
                   [("parents", "e-father", "occupation", "operator_direct")])
        self.block = self._seed(syn.ALDA).get("biography_block") or ""

    def test_it_forbids_narrating_a_fact_as_the_narrators_memory(self):
        self.assertIn("NEVER say or imply the narrator told you any of it",
                      self.block)

    def test_it_permits_asking_about_them(self):
        self.assertIn("You may ASK ABOUT them", self.block)
        self.assertIn("knowing a fact is not having heard the story", self.block)

    def test_it_says_a_fact_about_a_parent_is_not_a_fact_about_the_narrator(self):
        self.assertIn("A fact about a parent is not a fact about the narrator",
                      self.block)


class NarratorIsolation(_Case):
    """Every read is WHERE person_id = ?. Proven, not asserted."""

    def test_one_narrators_biography_never_appears_in_anothers(self):
        self._save(syn.ALDA, BERTIL,
                   [("parents", "e-father", "occupation", "operator_direct")])
        self._save(syn.BRENNIG, {"personal": {"fullName": "Brennig Oxhollow"},
                                 "parents": [{"_entryId": "b1", "relation": "father",
                                              "firstName": "Halvard",
                                              "occupation": "lighthouse keeper"}]})
        alda = self._seed(syn.ALDA).get("biography_block") or ""
        brennig = self._seed(syn.BRENNIG).get("biography_block") or ""
        self.assertIn("ore dock foreman", alda)
        self.assertNotIn("lighthouse keeper", alda)
        self.assertIn("lighthouse keeper", brennig)
        self.assertNotIn("ore dock foreman", brennig)

    def test_a_narrator_with_no_biography_gets_no_block(self):
        """The ordinary case for a new narrator. Absence, not an error.

        BRENNIG cannot serve here — the harness gives them an answer on
        purpose, so the isolation test has something to leak. A narrator
        with genuinely nothing is created for this."""
        c = sqlite3.connect(self.db)
        c.execute("INSERT INTO people (id, display_name) VALUES (?,?)",
                  ("p-synthetic-empty", "Nobody Yet"))
        c.commit(); c.close()
        seed = self._seed("p-synthetic-empty")
        self.assertNotIn("biography_block", seed)
        self.assertEqual(qfl.load_facts("p-synthetic-empty"), [])


class ItCannotBreakTheChatPath(_Case):

    def test_an_unreadable_questionnaire_does_not_raise(self):
        c = sqlite3.connect(self.db)
        c.execute("UPDATE bio_builder_questionnaires SET questionnaire_json=? "
                  "WHERE person_id=?", ("{not json", syn.ALDA))
        c.commit(); c.close()
        self.assertEqual(self._facts(syn.ALDA), [])
        self._seed(syn.ALDA)          # must not raise

    def test_missing_provenance_still_yields_the_biography(self):
        c = sqlite3.connect(self.db)
        c.execute("DROP TABLE bio_builder_answer_provenance")
        c.commit(); c.close()
        self._save(syn.ALDA, BERTIL)
        self.assertIn("ore dock foreman",
                      self._seed(syn.ALDA).get("biography_block") or "")


class WhenTwoRecordsDisagree(_Case):
    """The ruling: conflict is decided "using provenance and confirmation
    status, not store location alone", and neither value may be silently
    replaced."""

    def test_a_questionnaire_value_conflicting_with_a_narrator_statement(self):
        """The case the ruling asked for by name.

        The form says Marrow Bay. The narrator themselves said Ferrous
        Gate. Both must survive into the prompt, the narrator's own
        statement must be named as the better evidence, and neither may
        be asserted as settled."""
        self._save(syn.ALDA, BERTIL,
                   [("personal", "", "placeOfBirth", "operator_direct")])
        conflicts = qfl.find_conflicts(
            self._facts(syn.ALDA),
            {"personal.placeOfBirth": ("Ferrous Gate", "narrator_direct")})
        self.assertEqual(len(conflicts), 1)
        c = conflicts[0]
        self.assertEqual(c["questionnaire_value"], "Marrow Bay")
        self.assertEqual(c["other_value"], "Ferrous Gate")
        self.assertNotIn("better", c,
                         "provenance says WHO supplied a value, not which is "
                         "correct; there must be no evidence hierarchy")

        block = qfl.render_for_prompt(
            self._facts(syn.ALDA),
            competing={"personal.placeOfBirth": ("Ferrous Gate", "narrator_direct")})
        self.assertIn("TWO RECORDS DISAGREE", block)
        self.assertIn("Marrow Bay", block, "the form value was dropped")
        self.assertIn("Ferrous Gate", block, "the narrator's value was dropped")
        self.assertIn("ask which is right", block)
        self.assertIn("never quietly drop the other", block)
        self.assertIn("They do NOT say which is correct", block,
                      "the prompt must say plainly that origin is not truth")
        self.assertNotIn("better evidence", block)

    def test_a_value_with_no_competing_value_produces_no_conflict(self):
        """The other case the ruling named. An occupation nothing else
        claims is just a fact."""
        self._save(syn.ALDA, BERTIL,
                   [("parents", "e-father", "occupation", "operator_direct")])
        facts = self._facts(syn.ALDA)
        self.assertEqual(
            qfl.find_conflicts(facts, {"personal.placeOfBirth": ("Marrow Bay", "unknown")}),
            [], "an AGREEING value is not a conflict")
        self.assertEqual(qfl.find_conflicts(facts, {}), [])
        block = qfl.render_for_prompt(facts, competing={})
        self.assertNotIn("TWO RECORDS DISAGREE", block)
        self.assertIn("ore dock foreman", block)

    def test_whitespace_and_case_are_not_a_disagreement(self):
        self._save(syn.ALDA, BERTIL)
        self.assertEqual(
            qfl.find_conflicts(self._facts(syn.ALDA),
                               {"personal.placeOfBirth": ("  marrow   bay ", "unknown")}),
            [])

    def test_no_origin_pairing_produces_a_ranking(self):
        """Every combination renders the same way: both values, both
        origins, no tie-break. An earlier version ranked them."""
        self._save(syn.ALDA, BERTIL,
                   [("personal", "", "placeOfBirth", "operator_direct")])
        for other_origin in ("narrator_direct", "operator_direct",
                             "ai_suggested", "unknown"):
            with self.subTest(other=other_origin):
                block = qfl.render_for_prompt(
                    self._facts(syn.ALDA),
                    competing={"personal.placeOfBirth": ("Ferrous Gate", other_origin)})
                self.assertIn("Marrow Bay", block)
                self.assertIn("Ferrous Gate", block)
                for banned in ("better evidence", "outranks", "Neither outranks"):
                    self.assertNotIn(banned, block)

    def test_an_unreviewed_legacy_entry_stays_marked_origin_unknown(self):
        """In a MIXED biography an unmarked line would read as
        operator-entered. The ruling requires legacy entries to remain
        visibly origin-unknown."""
        self._save(syn.ALDA, BERTIL,
                   [("parents", "e-father", "occupation", "operator_direct")])
        block = self._seed(syn.ALDA).get("biography_block") or ""
        self.assertIn("origin not recorded", block,
                      "legacy entries lost their marking in a mixed biography")
        self.assertNotIn("ore dock foreman  [origin", block,
                         "and a recorded origin was not mislabelled")


class PendingSuggestionsStayOut(_Case):
    """"pending suggestions must never enter Lori's context as
    established facts"."""

    def test_the_queue_does_not_reach_the_biography_block(self):
        self._save(syn.ALDA, BERTIL)
        block = self._seed(syn.ALDA).get("biography_block") or ""
        # The harness queues `education.gradeLevel = 4th grade` and
        # `military.branch = Ferrous Gate battery` for ALDA.
        self.assertNotIn("4th grade", block)
        self.assertNotIn("Ferrous Gate battery", block)

    def test_they_remain_available_separately_for_review(self):
        """Excluded from the facts, not deleted. The review surface
        still needs them."""
        self._save(syn.ALDA, BERTIL)
        seed = self._seed(syn.ALDA)
        self.assertIn("suggested", seed)
        self.assertNotIn("4th grade", seed.get("biography_block") or "")


class TheWiringIsReal(unittest.TestCase):
    """Guards against the block existing and never being injected."""

    def setUp(self):
        self.src = (REPO / "server" / "code" / "api" / "prompt_composer.py").read_text(
            encoding="utf-8")

    def test_the_block_is_added_to_the_prompt_assembly(self):
        self.assertIn('parts.add("saved_biography"', self.src)

    def test_the_section_has_a_registered_policy(self):
        from api.services.prompt_section_policy import policy_for
        p = policy_for("saved_biography")
        self.assertFalse(p.required, "it must be droppable; losing it is recoverable")
        self.assertEqual(p.drop_order, 35,
                         "below ui_context (30), above pinned_facts (40)")
        # The rationale must not claim dropping it loses the data.
        pol = (REPO / "server" / "code" / "api" / "services"
               / "prompt_section_policy.py").read_text(encoding="utf-8")
        self.assertIn("Dropping a section does not delete anything", pol)
        self.assertIn("re-reads the stored questionnaire on the", pol)

    def test_the_stale_comment_was_corrected(self):
        """The WO called this out as 'the kind of note that persuades a
        future reader not to check'."""
        self.assertNotIn("folded into profile_json by\n         the questionnaire "
                         "endpoint already", self.src)
        self.assertIn("READ DIRECTLY, at the end of", self.src)

    def test_update_profile_json_is_not_on_this_path(self):
        from api.services import questionnaire_for_lori as m
        src = Path(m.__file__).read_text(encoding="utf-8")
        self.assertNotIn("update_profile_json", src.split('"""', 2)[2],
                         "the destructive top-level merge must stay off this path")



class TheBlockMustSURVIVETheBudget(_Case):
    """"would survive" is not a test result.

    The first compact version measured 1,533 tokens standalone and left
    62 tokens of headroom in the real prompt — which is another way of
    spelling "dropped again next week". These run the REAL budget
    function with the section sizes from the turn that actually failed
    (api.log, 2026-09-21 06:04:37):

        saved_biography:DROP:2605   directives_interview:keep:3918
        tokens=5766 limit=8192 dropped_sections=5
    """

    # Every section from that turn except the biography, at its real size.
    LOGGED = [("system_head", 1631), ("ui_context", 72), ("identity_facts", 35),
              ("identity_grounding", 138), ("approved_stories", 159),
              ("english_first", 107), ("directives_interview", 3918),
              ("memory_context", 233)]

    def _budget(self, bio, detail=""):
        from api.services.prompt_budget import fit_chat_messages_with_sections
        from api.prompt_composer import _PromptAssembly, _Section
        from api.services.prompt_section_policy import policy_for

        def mk(name, text):
            pol = policy_for(name)
            return _Section(name=name, text=text, required=pol.required,
                            drop_order=pol.drop_order)

        secs = [mk(n, "x" * (t * 4)) for n, t in self.LOGGED]
        secs.insert(4, mk("saved_biography", bio))
        if detail:
            secs.insert(5, mk("saved_biography_detail", detail))
        count = lambda m: sum(len(x.get("content") or "") // 4 for x in m)
        msgs = [{"role": "system", "content": _PromptAssembly.join(secs)},
                {"role": "user", "content": "what can you tell me about my mom"}]
        out = fit_chat_messages_with_sections(
            msgs, limit=8192, count_tokens=count, sections=secs,
            render_sections=_PromptAssembly.join)
        # `out.fits` IS NOT THE QUESTION, and prompt_budget.py says so
        # in its own comment: "a consumer that reads the boolean cannot
        # tell a turn where everything fitted from one where her
        # identity sections were dropped". It reports True after
        # shedding. Three tests here asserted it and would have passed
        # with the biography thrown away. The question is whether the
        # section SURVIVED.
        kept = {s.name for s in (out.sections or []) if s.kept}
        if not out.sections:
            kept = {s.name for s in secs}       # nothing was shed at all
        return kept, count(msgs), out

    def test_the_old_full_block_IS_dropped(self):
        """The control, and it earned its place: it is what showed that
        `out.fits` was the wrong assertion."""
        kept, total, out = self._budget("x" * (2605 * 4))
        self.assertNotIn("saved_biography", kept,
                         f"2,605 tokens survived in {total} — the budget moved")
        self.assertEqual(out.reason, "trimmed_sections")

    def test_the_compact_block_is_KEPT(self):
        self._save(syn.ALDA, BERTIL,
                   [("parents", "e-father", "occupation", "operator_direct")])
        bio = self._seed(syn.ALDA).get("biography_block") or ""
        kept, total, _out = self._budget(bio)
        self.assertIn("saved_biography", kept,
                      f"the compact biography was dropped ({total} tokens)")

    def test_it_survives_WITH_the_retrieved_detail_too(self):
        """The expensive turn: general biography AND a person's stories.

        BERTIL has no story fields, so it cannot exercise this — an
        earlier version used it, `detail_for` correctly returned nothing,
        the section was never added, and the failure looked like a budget
        problem. A fixture that carries stories is the point.
        """
        self._save(syn.ALDA, {"parents": [
            {"_entryId": "e-f", "relation": "Father", "firstName": "Bertil",
             "occupation": "ore dock foreman",
             "notableLifeEvents": "Worked the ore docks through two strikes and "
                                  "kept the union card in his wallet until he died."},
            {"_entryId": "e-m", "relation": "Mother", "firstName": "Sigrid",
             "occupation": "schoolteacher",
             "notableLifeEvents": "Taught at Marrow Bay for thirty years."}]},
                   [("parents", "e-f", "occupation", "operator_direct")])
        facts = self._facts(syn.ALDA)
        bio = qfl.render_for_prompt(facts)
        detail = qfl.detail_for(facts, "tell me about my father")
        self.assertTrue(detail, "the fixture must actually produce a retrieval")
        kept, total, _out = self._budget(bio, detail)
        self.assertIn("saved_biography", kept, f"biography dropped ({total} tokens)")
        self.assertIn("saved_biography_detail", kept,
                      "the answer to the question actually asked was dropped")

    def test_there_is_real_headroom_not_a_few_tokens(self):
        """62 tokens of slack is not a margin. One longer question, one
        extra history turn, and it is gone."""
        self._save(syn.ALDA, BERTIL)
        _kept, total, _o = self._budget(self._seed(syn.ALDA).get("biography_block") or "")
        self.assertGreater(8192 - total, 300,
                           f"only {8192 - total} tokens of headroom")


class TheLongStoriesStayReachable(_Case):
    """"Do not discard the longer stories from storage or make them
    permanently inaccessible to Lori."
    """

    RICH = {
        "parents": [{
            "_entryId": "e-m", "relation": "Mother", "firstName": "Sigrid",
            "occupation": "schoolteacher",
            "notableLifeEvents": "Taught at the Marrow Bay school for thirty "
                                 "years and kept every class photograph.",
        }, {
            "_entryId": "e-f", "relation": "Father", "firstName": "Bertil",
            "occupation": "ore dock foreman",
            "notableLifeEvents": "Worked the ore docks through two strikes.",
        }],
    }

    def test_stories_are_not_in_the_default_block(self):
        self._save(syn.ALDA, self.RICH)
        block = self._seed(syn.ALDA).get("biography_block") or ""
        self.assertNotIn("thirty years", block, "a long story rode along anyway")
        self.assertIn("schoolteacher", block, "but the facts must be there")

    def test_but_the_block_SAYS_they_exist(self):
        """Otherwise Lori asks for something already on record."""
        self._save(syn.ALDA, self.RICH)
        block = self._seed(syn.ALDA).get("biography_block") or ""
        self.assertIn("LONGER MATERIAL ON RECORD", block)
        self.assertIn("Mother Sigrid", block)

    def test_asking_about_mom_retrieves_her_story(self):
        self._save(syn.ALDA, self.RICH)
        d = qfl.detail_for(self._facts(syn.ALDA), "what can you tell me about my mom")
        self.assertIn("thirty years", d)
        self.assertNotIn("two strikes", d, "that is the father's, and unasked for")

    def test_asking_by_name_works_too(self):
        self._save(syn.ALDA, self.RICH)
        d = qfl.detail_for(self._facts(syn.ALDA), "tell me about Bertil")
        self.assertIn("two strikes", d)

    def test_a_turn_that_names_nobody_retrieves_nothing(self):
        """What keeps the default prompt small."""
        self._save(syn.ALDA, self.RICH)
        self.assertEqual(
            qfl.detail_for(self._facts(syn.ALDA), "what should we talk about"), "")

    def test_the_retrieval_carries_the_same_rule(self):
        self._save(syn.ALDA, self.RICH)
        d = qfl.detail_for(self._facts(syn.ALDA), "about my mom")
        self.assertIn("you did not HEAR it", d)
        self.assertIn("Do not say they told you", d)

    def test_nothing_was_deleted_from_storage(self):
        self._save(syn.ALDA, self.RICH)
        c = sqlite3.connect(self.db)
        stored = c.execute("SELECT questionnaire_json FROM bio_builder_questionnaires "
                           "WHERE person_id=?", (syn.ALDA,)).fetchone()[0]
        c.close()
        self.assertIn("thirty years", stored)


class EntriesWithoutAnEntryIdStayDistinct(_Case):
    """17 of 17 entries in a real record carry no `_entryId`.

    Grouping on the id alone merged a mother and a father into one
    person — "Kent James Horne (nee Zarr)", her maiden name on him.
    """

    NO_IDS = {"parents": [
        {"relation": "Mother", "firstName": "Janice", "maidenName": "Zarr",
         "occupation": "Homemaker"},
        {"relation": "Father", "firstName": "Kent", "occupation": "Construction"},
    ]}

    def test_two_parents_render_as_two_people(self):
        self._save(syn.ALDA, self.NO_IDS)
        block = self._seed(syn.ALDA).get("biography_block") or ""
        self.assertIn("Mother", block)
        self.assertIn("Father", block)
        self.assertEqual(block.count("Homemaker"), 1)

    def test_the_maiden_name_stays_on_the_right_person(self):
        self._save(syn.ALDA, self.NO_IDS)
        block = self._seed(syn.ALDA).get("biography_block") or ""
        for line in block.splitlines():
            if "Kent" in line:
                self.assertNotIn("Zarr", line,
                                 "the mother's maiden name landed on the father")
            if "Janice" in line:
                self.assertIn("Zarr", line)


# ── A GUARD, BECAUSE I MADE THIS MISTAKE TWICE ──────────────────────
#
# Both times I appended test classes AFTER `unittest.main()`. Python
# defines them, `main()` has already run, and they are never collected.
# The suite reports OK and asserts nothing. It cost eight dead tests in
# test_suggestion_identity.py on 2026-09-20 and five more here today.
#
# A count is the cheapest thing that notices.
class TheSuiteIsActuallyRunning(unittest.TestCase):

    def test_every_class_in_this_file_is_collected(self):
        import re
        src = Path(__file__).read_text(encoding="utf-8")
        declared = set(re.findall(r"^class (\w+)\(", src, re.M))
        loaded = {c.__name__ for c in globals().values()
                  if isinstance(c, type) and issubclass(c, unittest.TestCase)}
        missing = declared - loaded
        self.assertEqual(missing, set(),
                         f"declared but never collected: {sorted(missing)} — "
                         "almost certainly defined after unittest.main()")

    def test_the_main_block_is_the_last_thing_in_the_file(self):
        src = Path(__file__).read_text(encoding="utf-8").rstrip()
        self.assertTrue(src.endswith("unittest.main(verbosity=2)"),
                        "something was appended after unittest.main()")

class TheAntiConfabulationRuleIsAPrincipleNotABlocklist(unittest.TestCase):
    """Observed live on 2026-09-21, AFTER the list was tightened.

    Chris typed four words — "and my dad and siblings", plainly a
    request — and Lori replied "You have a vivid memory of your dad and
    siblings." Nothing on the forbidden list appears in that sentence.
    A blocklist of phrases cannot hold a rule about meaning.
    """

    def setUp(self):
        self.src = (REPO / "server" / "code" / "api" / "prompt_composer.py").read_text(
            encoding="utf-8")

    def test_the_rule_says_it_is_the_principle_not_the_list(self):
        self.assertIn("THE RULE IS THE PRINCIPLE, NOT THE LIST", self.src)

    def test_the_observed_evasion_is_quoted_verbatim(self):
        """Keep the real sentence. A paraphrase drifts; this one was
        said to a person about his own father."""
        self.assertIn("You have a vivid memory of your dad and siblings", self.src)

    def test_a_request_is_not_a_statement(self):
        self.assertIn("A REQUEST IS NOT A STATEMENT", self.src)

    def test_it_names_the_class_not_only_the_instance(self):
        for phrase in ("you clearly loved", "you remember X fondly",
                       "that was important to you"):
            self.assertIn(phrase, self.src,
                          "the rule must generalise past the one observed case")

    def test_having_a_fact_is_still_distinguished_from_being_told_it(self):
        """The earlier repair must survive this one."""
        self.assertIn("HAVING A FACT IS NOT THE SAME AS HAVING BEEN TOLD IT",
                      self.src)

if __name__ == "__main__":
    unittest.main(verbosity=2)