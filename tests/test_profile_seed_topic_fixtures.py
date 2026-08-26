"""Ten topics, four states, and the six gaps between the seed and the walk.

WO-LORI-PROFILE-SEED-REACHABILITY-01, Phase 0 (2026-08-26).

**THIS PHASE CHANGES NO BEHAVIOUR.** These fixtures are the shapes a
completion resolver will read, and the six gaps below are exercised
against the real `_build_profile_seed()` so Phase 1 designs against
measurement rather than against a table.

── HOW TO RUN THIS ───────────────────────────────────────────────────

    PYTHONPATH=server/code python3 -m unittest tests.test_profile_seed_topic_fixtures

**NOT `.venv/bin/python`** — see `CLAUDE.md` under **Environment**:
`.venv` has no fastapi, and this file's import chain reaches the app.

── THE STATE CONTRACT IS THE WORK ORDER'S, NOT MINE ──────────────────

    unanswered | known | addressed | declined

The first version of this file invented a fifth state, `negative`, and
that was a design decision smuggled in as a fixture. It is corrected
here, and the correction matters more than the word:

**AN EXPLICIT NEGATIVE IS EVIDENCE, NOT A STATE.** "I never served" does
not need its own bucket — it needs to be *stored*, after which it
resolves like any other evidence:

  * `military.served = False` already in structured truth  → **known**
    (nobody has to ask; the truth store answers it);
  * "I never served" said during onboarding                → **addressed**
    (the topic was put to the narrator and they answered);
  * either way the truth store keeps the explicit `False`.

The distinction that actually protects the narrator is between *answered*
and *never asked* — and today the system cannot make it, because
`served=False` is dropped on the way to the seed. That is gap 2 below,
and it is why the same question could return forever. Principle 8:
**Lori must not interrogate the narrator for facts the system already
has.**

`declined` is final in the same way. "I would rather not discuss that"
is an answer.

── THE SIX GAPS ──────────────────────────────────────────────────────

Measured, not asserted from prose. `_build_profile_seed()` returns five
keys — `age_years`, `childhood_home`, `full_name`, `life_stage`,
`preferred_name` — and the walk asks ten questions. Each test below
names one consequence.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
for _p in (str(_SERVER_CODE), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api import db as _db  # noqa: E402
from api import prompt_composer as _pc  # noqa: E402

# ── The work order's four states ────────────────────────────────────────
UNANSWERED = "unanswered"
KNOWN = "known"
ADDRESSED = "addressed"
DECLINED = "declined"

TOPIC_STATES = (UNANSWERED, KNOWN, ADDRESSED, DECLINED)

#: Only one of the four is askable. Data, so Phase 1 cannot widen it
#: without editing something a reviewer will see.
ASKABLE = {UNANSWERED}

#: Final states — asking again after any of these is interrogation.
FINAL = {KNOWN, ADDRESSED, DECLINED}

TOPICS = (
    "childhood_home", "siblings", "parents_work", "heritage", "education",
    "military", "career", "partner", "children", "life_stage",
)

#: Evidence shapes per topic per state. `known` is structured truth that
#: already answers the topic; `addressed` is the narrator having answered
#: it during onboarding, INCLUDING an explicit negative; `declined` is a
#: refusal; `unanswered` is the absence of all three.
#:
#: Progress rows store no narrator prose (work-order decision 8) — these
#: carry SHAPE and disposition, not biography.
FIXTURES = {
    "childhood_home": {
        KNOWN: {"evidence": {"childhood_home": "Devils Lake, North Dakota"},
                "source": "operator_entered"},
        ADDRESSED: {"evidence": {"moved_in_childhood": False},
                    "source": "onboarding",
                    "note": "grew up where born — answered, not absent"},
        DECLINED: {"source": "onboarding"},
        UNANSWERED: {},
    },
    "siblings": {
        KNOWN: {"evidence": {"siblings": [{"relation": "brother"}]},
                "source": "operator_entered"},
        ADDRESSED: {"evidence": {"siblings": [], "only_child": True},
                    "source": "onboarding",
                    "note": "an only child has ANSWERED"},
        DECLINED: {"source": "onboarding"},
        UNANSWERED: {},
    },
    "parents_work": {
        KNOWN: {"evidence": {"parents": [{"relation": "father",
                                          "occupation": "grain elevator"}]},
                "source": "operator_entered"},
        ADDRESSED: {"evidence": {"parents_work_unknown": True},
                    "source": "onboarding"},
        DECLINED: {"source": "onboarding"},
        UNANSWERED: {},
    },
    "heritage": {
        KNOWN: {"evidence": {"heritage": "Norwegian"},
                "source": "provisional"},
        ADDRESSED: {"evidence": {"heritage_unknown": True},
                    "source": "onboarding",
                    "note": "'we never knew' is an answer"},
        DECLINED: {"source": "onboarding"},
        UNANSWERED: {},
    },
    "education": {
        KNOWN: {"evidence": {"education": {"highestLevel": "high school"}},
                "source": "intake"},
        ADDRESSED: {"evidence": {"education": {"highestLevel": "none"}},
                    "source": "onboarding"},
        DECLINED: {"source": "onboarding"},
        UNANSWERED: {},
    },
    "military": {
        KNOWN: {"evidence": {"military": {"served": True, "branch": "Army"}},
                "source": "operator_entered"},
        ADDRESSED: {"evidence": {"military": {"served": False}},
                    "source": "onboarding",
                    "note": "served=False must SURVIVE the write"},
        DECLINED: {"source": "onboarding"},
        UNANSWERED: {},
    },
    "career": {
        KNOWN: {"evidence": {"career": "rural mail carrier"},
                "source": "provisional"},
        ADDRESSED: {"evidence": {"never_worked_outside_home": True},
                    "source": "onboarding"},
        DECLINED: {"source": "onboarding"},
        UNANSWERED: {},
    },
    "partner": {
        KNOWN: {"evidence": {"spouse": {"status": "married"}},
                "source": "operator_entered"},
        ADDRESSED: {"evidence": {"spouse": None, "never_married": True},
                    "source": "onboarding"},
        DECLINED: {"source": "onboarding"},
        UNANSWERED: {},
    },
    "children": {
        KNOWN: {"evidence": {"children": [{"relation": "son"}]},
                "source": "operator_entered"},
        ADDRESSED: {"evidence": {"children": [], "no_children": True},
                    "source": "onboarding"},
        DECLINED: {"source": "onboarding"},
        UNANSWERED: {},
    },
    "life_stage": {
        KNOWN: {"evidence": {"life_stage": {"retired": True, "since": 1998}},
                "source": "operator_entered"},
        ADDRESSED: {"evidence": {"life_stage": {"retired": False,
                                                "still_working": True}},
                    "source": "onboarding",
                    "note": "'still working' is an ANSWER"},
        DECLINED: {"source": "onboarding"},
        UNANSWERED: {},
    },
}


class TheStateContractMatchesTheWorkOrderTests(unittest.TestCase):

    def test_the_four_states_are_the_specified_four(self):
        """`negative` was mine and is gone.

        The spec names `unanswered | known | addressed | declined`.
        Inventing a fifth persisted state in a fixture file is a design
        change wearing test clothes.
        """
        self.assertEqual(TOPIC_STATES,
                         ("unanswered", "known", "addressed", "declined"))
        self.assertNotIn("negative", TOPIC_STATES)

    def test_only_unanswered_is_askable(self):
        self.assertEqual(ASKABLE, {UNANSWERED})

    def test_the_other_three_are_final(self):
        """Asking again after any of these is interrogation."""
        self.assertEqual(FINAL, {KNOWN, ADDRESSED, DECLINED})
        self.assertEqual(ASKABLE & FINAL, set())
        self.assertEqual(ASKABLE | FINAL, set(TOPIC_STATES))

    def test_all_ten_topics_carry_all_four_states(self):
        self.assertEqual(tuple(FIXTURES), TOPICS)
        self.assertEqual(len(TOPICS), 10)
        for topic in TOPICS:
            with self.subTest(topic=topic):
                self.assertEqual(set(FIXTURES[topic]), set(TOPIC_STATES))

    def test_an_explicit_negative_is_evidence_under_addressed(self):
        """The correction, stated as an assertion.

        Every negative answer lives under `addressed` and carries
        evidence. None of them is a separate state, and none is empty.
        """
        for topic in ("siblings", "military", "partner", "children",
                      "life_stage"):
            with self.subTest(topic=topic):
                shape = FIXTURES[topic][ADDRESSED]
                self.assertIn("evidence", shape,
                              "a negative answer must store evidence, or it "
                              "is indistinguishable from never asking")
                self.assertEqual(shape["source"], "onboarding")

    def test_the_same_fact_can_arrive_as_known_or_addressed(self):
        """Military is the clearest case, so it is asserted directly.

        `served=False` from the truth store is `known`; the same fact
        said during onboarding is `addressed`. Different provenance,
        same protection: nobody asks again.
        """
        known = FIXTURES["military"][KNOWN]
        addressed = FIXTURES["military"][ADDRESSED]
        self.assertIs(known["evidence"]["military"]["served"], True)
        self.assertIs(addressed["evidence"]["military"]["served"], False)
        self.assertNotEqual(known["source"], addressed["source"])
        for shape in (known, addressed):
            self.assertIn("evidence", shape)

    def test_unanswered_is_the_only_empty_shape(self):
        for topic in TOPICS:
            with self.subTest(topic=topic):
                self.assertEqual(FIXTURES[topic][UNANSWERED], {})
                for state in (KNOWN, ADDRESSED, DECLINED):
                    self.assertNotEqual(FIXTURES[topic][state], {})

    def test_no_fixture_carries_narrator_prose(self):
        """Work-order decision 8: progress rows store no narrator speech."""
        for topic in TOPICS:
            for state in (KNOWN, ADDRESSED, DECLINED):
                with self.subTest(topic=topic, state=state):
                    self.assertLess(len(json.dumps(FIXTURES[topic][state])), 200)


class _SeedBase(unittest.TestCase):
    """Drives the REAL `_build_profile_seed()` against a real database."""

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

    BIRTHPLACE = "Devils Lake, North Dakota"

    def _seed_from(self, profile_json: dict) -> dict:
        """Create a narrator with `profile_json` and return their seed."""
        pid = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO people (id, display_name, date_of_birth,"
            " place_of_birth, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (pid, "Verlie Ostrander", "1936-11-08", self.BIRTHPLACE,
             "2026-08-26", "2026-08-26"))
        con.execute(
            "INSERT INTO profiles (person_id, profile_json, updated_at)"
            " VALUES (?,?,?)", (pid, json.dumps(profile_json), "2026-08-26"))
        con.commit()
        con.close()
        return _pc._build_profile_seed(pid)


class TheSixCompletionDataGapsTests(_SeedBase):
    """Each of the six gaps, driven against product code.

    The work order tabulates these. Phase 0's job is to make them
    executable, so Phase 1 corrects a measured adapter rather than a
    described one — and so that when an adapter IS corrected, the test
    here fails and has to be re-pointed deliberately.
    """

    def test_gap_0_the_seed_answers_five_of_the_ten_questions(self):
        """The shape of the whole problem, in one assertion."""
        seed = self._seed_from({})
        self.assertEqual(
            sorted(seed), ["age_years", "childhood_home", "full_name",
                           "life_stage", "preferred_name"],
            "the seed's key set changed; every gap test below is now "
            "suspect and must be re-measured")

    def test_gap_1_education_highestLevel_is_not_read(self):
        """Intake writes `education.highestLevel`; the seed reads
        `schooling` / `higherEducation`, so the value never arrives."""
        seed = self._seed_from({"education": {"highestLevel": "high school"}})
        education_ish = {k: v for k, v in seed.items()
                         if "educ" in k.lower() or "school" in k.lower()}
        self.assertEqual(
            education_ish, {},
            "education evidence now reaches the seed; gap 1 is closed and "
            "this test should become its contract")
        self.assertNotIn("high school", json.dumps(seed))

    def test_gap_2_military_served_false_is_lost(self):
        """THE CENTRAL GAP. `served=False` and never-asked are identical
        in the seed, so the question can return forever."""
        did_not_serve = self._seed_from({"military": {"served": False}})
        never_asked = self._seed_from({})
        self.assertEqual(
            did_not_serve.get("military"), never_asked.get("military"),
            "an explicit non-service is now distinguishable from silence; "
            "gap 2 is closed")
        # …while an affirmative DOES survive, which is what makes the
        # asymmetry a defect rather than a uniform omission.
        served = self._seed_from({"military": {"served": True,
                                               "branch": "Army"}})
        self.assertEqual(served.get("military"), "Army")

    def test_gap_3_explicit_no_partner_is_indistinguishable(self):
        explicit_none = self._seed_from({"spouse": None,
                                         "never_married": True})
        never_asked = self._seed_from({})
        self.assertEqual(explicit_none.get("spouse"),
                         never_asked.get("spouse"))
        self.assertNotIn("spouse", explicit_none,
                         "a partner bucket now exists; gap 3 is closed")

    def test_gap_4_explicit_no_children_is_indistinguishable(self):
        explicit_none = self._seed_from({"children": [], "no_children": True})
        never_asked = self._seed_from({})
        self.assertEqual(explicit_none.get("children"),
                         never_asked.get("children"))
        self.assertNotIn("children", explicit_none,
                         "a children bucket now exists; gap 4 is closed")

    def test_gap_5_life_stage_is_an_age_band_not_a_working_status(self):
        """The seed derives a life stage from age. The walk asks whether
        the narrator is retired or still working. An age cannot answer
        that — a ninety-year-old may still be working."""
        seed = self._seed_from({})
        self.assertEqual(seed.get("age_years"), 89)
        self.assertEqual(seed.get("life_stage"), "senior elder")
        blob = json.dumps(seed).lower()
        for proof in ("retired", "working", "still_working"):
            self.assertNotIn(
                proof, blob,
                "the seed now carries a working-status answer; gap 5 is "
                "closed and the derived band is no longer standing in for it")

    def test_gap_5b_a_stated_working_status_still_does_not_reach_the_seed(self):
        """Even when the narrator HAS answered, the seed keeps the band."""
        seed = self._seed_from({"life_stage": {"retired": False,
                                               "still_working": True}})
        self.assertEqual(seed.get("life_stage"), "senior elder")

    def test_gap_6_childhood_home_is_exactly_the_birthplace(self):
        """EXACT equality, not "the birthplace appears somewhere".

        The earlier version searched the seed for the birthplace string,
        which would also have passed if it appeared in an unrelated
        field. Being born somewhere does not prove growing up there, and
        the work order's decision 6 forbids a derived guess from
        satisfying a topic.
        """
        seed = self._seed_from({})
        self.assertEqual(
            seed.get("childhood_home"), self.BIRTHPLACE,
            "childhood_home is no longer copied verbatim from the "
            "birthplace; gap 6 is closed")

    def test_gap_6b_a_stated_childhood_home_is_still_overridden(self):
        """The narrator moved. The seed still says they did not.

        This is the gap at its worst: not merely a guess where nothing
        is known, but a guess that survives a contradicting fact.
        """
        seed = self._seed_from({"childhood_home": "Fargo, North Dakota"})
        self.assertEqual(
            seed.get("childhood_home"), self.BIRTHPLACE,
            "a stated childhood home now wins over the birthplace; gap 6 "
            "is closed and this test should become its contract")
