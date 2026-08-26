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

Measured against REAL storage, not asserted from prose and not fed
invented keys — see `_SeedBase` for what went wrong the first time.

`_build_profile_seed()` returns five keys: `age_years`,
`childhood_home`, `full_name`, `life_stage`, `preferred_name`. Only
**two of those correspond to walk topics** — `childhood_home` and
`life_stage` — and both are derived wrongly (gaps 5 and 6). The other
three are identity. So the seed does not answer "five of ten
questions"; it answers approximately none of them, which is the
finding.
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
from api.services import bio_schema as _bs  # noqa: E402

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
        KNOWN: {"evidence": {"bio_facts.childhood_home_address":
                     "Devils Lake, North Dakota"},
                "source": "operator_entered"},
        ADDRESSED: {"evidence": {"bio_facts.childhood_home_address":
                         "Devils Lake, North Dakota"},
                    "source": "onboarding",
                    "note": "grew up where born — answered, not absent"},
        DECLINED: {"source": "onboarding"},
        UNANSWERED: {},
    },
    "siblings": {
        KNOWN: {"evidence": {"bio_facts.sibling_count": 1},
                "source": "operator_entered"},
        ADDRESSED: {"evidence": {"bio_facts.sibling_count": 0},
                    "source": "onboarding",
                    "note": "an only child has ANSWERED — count 0, not absent"},
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
        KNOWN: {"evidence": {"education.highestLevel": "high school"},
                "source": "intake"},
        ADDRESSED: {"evidence": {"education.highestLevel": "none"},
                    "source": "onboarding"},
        DECLINED: {"source": "onboarding"},
        UNANSWERED: {},
    },
    "military": {
        KNOWN: {"evidence": {"bio_facts.military_served": "no"},
                "source": "operator_entered",
                "note": "the SAME fact as ADDRESSED below, different "
                        "provenance"},
        ADDRESSED: {"evidence": {"bio_facts.military_served": "no"},
                    "source": "onboarding",
                    "note": "non-service must SURVIVE the write"},
        DECLINED: {"source": "onboarding"},
        UNANSWERED: {},
    },
    "career": {
        KNOWN: {"evidence": {"career": "rural mail carrier"},
                "source": "provisional"},
        ADDRESSED: {"evidence": {"community.role": "homemaker"},
                    "source": "onboarding"},
        DECLINED: {"source": "onboarding"},
        UNANSWERED: {},
    },
    "partner": {
        KNOWN: {"evidence": {"bio_facts.spouse_name": "Merl"},
                "source": "operator_entered"},
        ADDRESSED: {"evidence": {"NO CANONICAL FIELD": "never married"},
                    "source": "onboarding",
                    "note": "bio_schema has spouse_name/marriage_year and "
                            "NO marital-status field; Phase 1 must add a "
                            "home for this answer"},
        DECLINED: {"source": "onboarding"},
        UNANSWERED: {},
    },
    "children": {
        KNOWN: {"evidence": {"bio_facts.children_count": 2},
                "source": "operator_entered"},
        ADDRESSED: {"evidence": {"bio_facts.children_count": 0},
                    "source": "onboarding"},
        DECLINED: {"source": "onboarding"},
        UNANSWERED: {},
    },
    "life_stage": {
        KNOWN: {"evidence": {"community.retirementStatus": "retired since 1998"},
                "source": "operator_entered"},
        ADDRESSED: {"evidence": {"community.retirementStatus": "still working"},
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
        """**CORRECTED 2026-08-26.** This compared `served=True` against
        `served=False` and called them "the same fact" — they are
        opposite facts, so it demonstrated nothing about provenance.

        The point is that ONE fact reaches the same protection by two
        routes: non-service already in the truth store is `known`;
        non-service said during onboarding is `addressed`. Same value,
        different source, and in neither case is the narrator asked
        again.
        """
        known = FIXTURES["military"][KNOWN]
        addressed = FIXTURES["military"][ADDRESSED]
        # THE SAME VALUE on both sides — that is the whole assertion.
        self.assertEqual(known["evidence"]["bio_facts.military_served"],
                         addressed["evidence"]["bio_facts.military_served"])
        self.assertEqual(known["evidence"], addressed["evidence"])
        # …arriving by different routes…
        self.assertEqual(known["source"], "operator_entered")
        self.assertEqual(addressed["source"], "onboarding")
        self.assertNotEqual(known["source"], addressed["source"])
        # …and both are final, so the question does not return.
        self.assertIn(KNOWN, FINAL)
        self.assertIn(ADDRESSED, FINAL)

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
    """Drives the REAL `_build_profile_seed()` against REAL truth stores.

    **CORRECTED 2026-08-26 after review.** The first version fed
    `profile_json` top-level keys I had invented — `childhood_home`,
    `life_stage`, `never_married`, `no_children`. The seed ignores keys
    it does not read, so every gap test passed **vacuously**: I was
    measuring my own fiction being discarded, not an adapter failing.
    That is precisely the failure this project keeps naming — a test
    that passes on the defect it was written for — and it took a
    reviewer to catch it.

    Every input below is now a shape the product actually writes:

      * `bio_facts` rows via `db.bio_fact_create()`, using field keys
        that exist in `bio_schema` (asserted below before use);
      * `profiles.profile_json` under the buckets
        `_build_profile_seed()`'s own docstring names — `personal.*`,
        `military.*`, `community.*`, `education.*`, `spouse`, `children`.
    """

    BIRTHPLACE = "Devils Lake, North Dakota"
    DOB = "1936-11-08"

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

        # ── THE bio_fields SEED GATE, and why it is reset here ────────
        # `bio_facts.field_key` carries a FOREIGN KEY to `bio_fields`,
        # and `db._BIO_SEED_LOADED` is a once-per-process flag guarding
        # the 83-row seed. So the FIRST database a process builds gets
        # the registry and every LATER one gets an empty `bio_fields` —
        # after which every `bio_fact_create()` fails with
        # "FOREIGN KEY constraint failed", pointing at `field_key`, not
        # at the narrator.
        #
        # This cost real time and the diagnosis was wrong at first: the
        # obvious reading of that error is a missing person row, and the
        # person row was fine. `PRAGMA foreign_key_list(bio_facts)`
        # named the real parent, and `SELECT COUNT(*) FROM bio_fields`
        # showed 83 on the first database and 0 on the second.
        #
        # Resetting the flag is the sanctioned path, not a workaround —
        # `db.py:62-70` documents it in those words: "Tests may reset it
        # ... to exercise the seed path under a fresh DB."
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

    def _narrator(self, profile_json=None, bio_facts=()):
        """A narrator with real intake anchors, optional profile and facts."""
        pid = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO people (id, display_name, date_of_birth,"
            " place_of_birth, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (pid, "Verlie Ostrander", self.DOB, self.BIRTHPLACE,
             "2026-08-26", "2026-08-26"))
        if profile_json is not None:
            con.execute(
                "INSERT INTO profiles (person_id, profile_json, updated_at)"
                " VALUES (?,?,?)", (pid, json.dumps(profile_json), "2026-08-26"))
        con.commit()
        con.close()
        for field_key, value in bio_facts:
            _db.bio_fact_create(narrator_id=pid, field_key=field_key,
                                value_json=json.dumps(value),
                                status="operator_entered", confidence=1.0)
        return pid

    def _seed(self, profile_json=None, bio_facts=()):
        return _pc._build_profile_seed(
            self._narrator(profile_json, bio_facts))


class TheFieldKeysUsedHereAreRealTests(_SeedBase):
    """Guard against the exact mistake this file made.

    If a test feeds a field key the schema does not define, it proves
    nothing — the write is a no-op and the seed was never going to read
    it. So the keys are checked against `bio_schema` FIRST.
    """

    REAL_KEYS = ("childhood_home_address", "childhood_homes", "sibling_count",
                 "children_count", "military_served", "spouse_name")

    def test_every_bio_fact_key_this_file_uses_exists(self):
        for key in self.REAL_KEYS:
            with self.subTest(field_key=key):
                self.assertIsNotNone(
                    _bs.get_field_by_key(key),
                    f"{key!r} is not a real bio_schema field; a test using "
                    f"it would prove nothing")

    def test_the_keys_i_previously_invented_do_not_exist(self):
        """Recorded so the error is legible, not just corrected."""
        for invented in ("childhood_home", "life_stage", "never_married",
                         "no_children"):
            with self.subTest(invented=invented):
                self.assertIsNone(
                    _bs.get_field_by_key(invented),
                    f"{invented!r} now exists as a schema field; the note "
                    f"about it being invented needs revisiting")


class TheSeedShapeTests(_SeedBase):

    def test_the_seed_returns_five_keys_of_which_two_map_to_topics(self):
        """**RENAMED AND CORRECTED.** This said "the seed answers five of
        the ten questions", which was wrong twice over: five is a count
        of KEYS, and only two of them correspond to walk topics —
        `childhood_home` and `life_stage` — both of which are derived
        incorrectly (gaps 5 and 6). The other three are identity, not
        onboarding answers.
        """
        seed = self._seed()
        self.assertEqual(
            sorted(seed), ["age_years", "childhood_home", "full_name",
                           "life_stage", "preferred_name"],
            "the seed's key set changed; every gap test below is now "
            "suspect and must be re-measured")
        topic_keys = {"childhood_home", "life_stage"}
        self.assertTrue(topic_keys <= set(seed))
        self.assertEqual(
            set(seed) - topic_keys - {"age_years"},
            {"full_name", "preferred_name"},
            "the non-topic keys are identity, not onboarding answers")

    def test_age_is_derived_from_the_date_of_birth(self):
        """**DATE-SENSITIVE ASSERTION REMOVED.** This read
        `age_years == 89`, which would have started failing after the
        synthetic narrator's next birthday with no code change at all —
        a test that breaks by the calendar teaches people to ignore it.
        The property is that the age is DERIVED, so it is computed the
        same way here.
        """
        import datetime as _dt
        seed = self._seed()
        born = _dt.date(1936, 11, 8)
        today = _dt.date.today()
        expected = today.year - born.year - (
            (today.month, today.day) < (born.month, born.day))
        self.assertEqual(seed.get("age_years"), expected)


class TheSixCompletionDataGapsTests(_SeedBase):
    """Each gap, driven against REAL storage shapes.

    Every input is something the product writes. Where a claimed gap
    turned out to be wrong on measurement, the correction is recorded
    rather than the test quietly reshaped.
    """

    # ── Gap 1 · education ────────────────────────────────────────────
    def test_gap_1_education_highestLevel_is_not_read(self):
        """Intake writes `education.highestLevel`; the seed reads
        `schooling` / `higherEducation`, so the value never arrives."""
        seed = self._seed({"education": {"highestLevel": "high school"}})
        self.assertNotIn("education", seed)
        self.assertNotIn("high school", json.dumps(seed))
        # …and the keys it DOES read work, which is what makes this a
        # naming mismatch rather than a dead bucket.
        reads = self._seed({"education": {"schooling": "high school"}})
        self.assertEqual(reads.get("education"), "high school")

    # ── Gap 2 · military ─────────────────────────────────────────────
    def test_gap_2_the_served_boolean_is_ignored_in_both_directions(self):
        """**CORRECTED FINDING.** I reported an asymmetry — that
        `served=True` survived while `served=False` was lost. Measured
        against the code, that was wrong: `_first_str()` accepts only
        strings, so the Boolean is never read AT ALL. `"Army"` survived
        in my earlier fixture because `branch` is a descriptive string,
        not because `True` was honoured.

        The real gap is broader than I claimed: no service Boolean
        reaches the seed in either direction, so "served", "did not
        serve" and "never asked" are all indistinguishable.
        """
        served = self._seed({"military": {"served": True}})
        not_served = self._seed({"military": {"served": False}})
        never_asked = self._seed({})
        self.assertIsNone(served.get("military"))
        self.assertIsNone(not_served.get("military"))
        self.assertEqual(served.get("military"), never_asked.get("military"))
        self.assertEqual(not_served.get("military"),
                         never_asked.get("military"))

    def test_gap_2b_only_a_descriptive_field_survives(self):
        """What DOES get through, so the repair target is precise."""
        seed = self._seed({"military": {"served": True, "branch": "Army"}})
        self.assertEqual(seed.get("military"), "Army")

    def test_gap_2c_the_real_bio_fact_does_not_reach_the_seed_either(self):
        """`military_served` is a real schema field that intake writes
        (`people.py` writes `"yes"`), and the seed does not read
        `bio_facts` at all."""
        self.assertIsNotNone(_bs.get_field_by_key("military_served"))
        seed = self._seed(bio_facts=[("military_served", "yes")])
        self.assertIsNone(seed.get("military"))

    # ── Gap 3 · partner ──────────────────────────────────────────────
    def test_gap_3_there_is_no_canonical_never_married_field(self):
        """**DOCUMENTED ABSENCE, not an invented key.** I previously
        passed `never_married` as though it were storage. It is not:
        `bio_schema` has `spouse_name`, `marriage_year`, `marriage_place`
        and no marital-status field. Intake accepts a `marital_status`
        input and folds it into `profile_json` as `marriage.status`,
        which the seed does not read.

        So an explicit "never married" has nowhere canonical to live —
        which is itself the gap Phase 1 must close.
        """
        self.assertIsNone(_bs.get_field_by_key("marital_status"))
        self.assertIsNotNone(_bs.get_field_by_key("spouse_name"))
        stated = self._seed({"marriage": {"status": "never married"}})
        self.assertIsNone(stated.get("partner"))
        self.assertEqual(stated.get("partner"), self._seed({}).get("partner"))

    # ── Gap 4 · children ─────────────────────────────────────────────
    def test_gap_4_a_zero_children_count_does_not_reach_the_seed(self):
        """`children_count` is a real field the intake fan-out writes."""
        self.assertIsNotNone(_bs.get_field_by_key("children_count"))
        explicit_none = self._seed(bio_facts=[("children_count", 0)])
        never_asked = self._seed({})
        self.assertIsNone(explicit_none.get("children"))
        self.assertEqual(explicit_none.get("children"),
                         never_asked.get("children"))

    def test_gap_4b_siblings_have_no_bucket_at_all(self):
        """`sibling_count` is real and written; the seed has no siblings
        bucket to receive it."""
        self.assertIsNotNone(_bs.get_field_by_key("sibling_count"))
        seed = self._seed(bio_facts=[("sibling_count", 0)])
        self.assertNotIn("siblings", seed)

    # ── Gap 5 · life stage ───────────────────────────────────────────
    def test_gap_5_the_real_retirement_path_does_not_reach_life_stage(self):
        """**REAL PROJECTION PATH.** `projection_writer` maps
        `education_work.retirement -> community.retirementStatus`. The
        seed derives `life_stage` from age alone and never consults it,
        so a narrator who has SAID they still work is still labelled by
        their age band.
        """
        retired = self._seed({"community": {"retirementStatus":
                                            "retired since 1998"}})
        still_working = self._seed({"community": {"retirementStatus":
                                                  "still working"}})
        never_asked = self._seed({})
        self.assertEqual(retired.get("life_stage"),
                         never_asked.get("life_stage"))
        self.assertEqual(still_working.get("life_stage"),
                         never_asked.get("life_stage"))
        for blob in (json.dumps(retired), json.dumps(still_working)):
            self.assertNotIn("retire", blob.lower())
            self.assertNotIn("working", blob.lower())

    # ── Gap 6 · childhood home ───────────────────────────────────────
    def test_gap_6_childhood_home_is_exactly_the_birthplace(self):
        """EXACT equality, not "the birthplace appears somewhere"."""
        self.assertEqual(self._seed().get("childhood_home"), self.BIRTHPLACE)

    def test_gap_6b_a_REAL_childhood_home_fact_is_still_overridden(self):
        """**THE CLAIM, NOW ACTUALLY PROVEN.**

        I previously asserted this using an invented top-level
        `childhood_home` key, which the seed never reads — so the test
        demonstrated nothing and I reported a "newly discovered defect"
        on the strength of it. Review caught that.

        Here the home is written to `bio_facts.childhood_home_address`,
        a real schema field, through the real `bio_fact_create()`. The
        seed STILL emits the birthplace: its `childhood_home` bucket is
        sourced entirely from `personal.placeOfBirth` / `basics.pob` /
        the people row, with no childhood-home input at any priority.
        The bucket is named for a question it never answers.
        """
        self.assertIsNotNone(_bs.get_field_by_key("childhood_home_address"))
        seed = self._seed(bio_facts=[("childhood_home_address",
                                      "Fargo, North Dakota")])
        self.assertEqual(
            seed.get("childhood_home"), self.BIRTHPLACE,
            "a real childhood-home fact now reaches the seed; gap 6 is "
            "closed and this test should become its contract")
        self.assertNotIn("Fargo", json.dumps(seed))

    def test_gap_6c_the_list_field_is_ignored_too(self):
        """`childhood_homes` is the list-shaped sibling field."""
        self.assertIsNotNone(_bs.get_field_by_key("childhood_homes"))
        seed = self._seed(bio_facts=[("childhood_homes",
                                      ["Fargo, North Dakota"])])
        self.assertEqual(seed.get("childhood_home"), self.BIRTHPLACE)
