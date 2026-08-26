"""Ten topics, four dispositions, and the gaps between them.

WO-LORI-PROFILE-SEED-REACHABILITY-01, Phase 0 (2026-08-26).

**THIS PHASE CHANGES NO BEHAVIOUR.** These fixtures are the shapes a
completion resolver will have to read. They exist now so that Phase 1
builds against evidence rather than against a guess, and so the six
completion-data defects the work order names are executable rather than
prose in a table.

── WHY THE NEGATIVES ARE THE POINT ───────────────────────────────────

A narrator who says *"I was an only child"* has ANSWERED the siblings
question. So has one who says *"I never served."* If the system stores
those as empty, they are indistinguishable from never having been asked,
and the walk asks again — and again. That is not an onboarding flow, it
is an interrogation, and it is exactly the failure mode this project's
own principle 8 forbids: **Lori must not interrogate the narrator for
facts the system already has.**

So every topic here carries all four dispositions:

  * `KNOWN`      — structured truth already answers it; do not ask.
  * `NEGATIVE`   — the narrator answered, and the answer is "none/no".
  * `DECLINED`   — the narrator would rather not say. Also final.
  * `UNANSWERED` — genuinely not yet asked. The ONLY askable state.

`NEGATIVE` and `DECLINED` are not absences. Storing them as absences is
the defect.

── THE SIX GAPS, AS FIXTURES ─────────────────────────────────────────

Each gap below is a case where the ten questions and
`_build_profile_seed()` disagree about what counts as answered. Phase 0
asserts the disagreement EXISTS, against the real function, so nobody
later has to take the table's word for it.

Run with:

    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_profile_seed_topic_fixtures
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

# ── Dispositions ────────────────────────────────────────────────────────
KNOWN = "known"
NEGATIVE = "negative"
DECLINED = "declined"
UNANSWERED = "unanswered"

DISPOSITIONS = (KNOWN, NEGATIVE, DECLINED, UNANSWERED)

#: Only one of the four is askable. Stated as data so Phase 1 cannot
#: quietly widen it.
ASKABLE = {UNANSWERED}

# ── The ten topics, in the composer's order ─────────────────────────────
TOPICS = (
    "childhood_home",
    "siblings",
    "parents_work",
    "heritage",
    "education",
    "military",
    "career",
    "partner",
    "children",
    "life_stage",
)

#: One evidence shape per topic per disposition. Prose is deliberately
#: minimal: **progress rows store no narrator speech** (work order
#: decision 8), so these carry the SHAPE, not the biography.
FIXTURES = {
    "childhood_home": {
        KNOWN: {"childhood_home": "Devils Lake, North Dakota",
                "_source": "operator_entered"},
        NEGATIVE: {"childhood_home": None, "moved_in_childhood": False,
                   "_disposition": NEGATIVE,
                   "_note": "grew up where they were born — an ANSWER"},
        DECLINED: {"_disposition": DECLINED},
        UNANSWERED: {},
    },
    "siblings": {
        KNOWN: {"siblings": [{"name": "Arden", "relation": "brother"}]},
        NEGATIVE: {"siblings": [], "only_child": True, "_disposition": NEGATIVE,
                   "_note": "an only child has ANSWERED the question"},
        DECLINED: {"_disposition": DECLINED},
        UNANSWERED: {},
    },
    "parents_work": {
        KNOWN: {"parents": [{"relation": "father", "occupation": "grain elevator"}]},
        NEGATIVE: {"parents": [], "_disposition": NEGATIVE},
        DECLINED: {"_disposition": DECLINED},
        UNANSWERED: {},
    },
    "heritage": {
        KNOWN: {"heritage": "Norwegian on both sides"},
        NEGATIVE: {"heritage": None, "heritage_unknown": True,
                   "_disposition": NEGATIVE,
                   "_note": "'we never knew' is an answer, not a silence"},
        DECLINED: {"_disposition": DECLINED},
        UNANSWERED: {},
    },
    "education": {
        # THE FIELD-NAMING GAP: intake writes `education.highestLevel`;
        # the seed reads `schooling` / `higherEducation`.
        KNOWN: {"education": {"highestLevel": "high school"}},
        NEGATIVE: {"education": {"highestLevel": "none"},
                   "_disposition": NEGATIVE},
        DECLINED: {"_disposition": DECLINED},
        UNANSWERED: {},
    },
    "military": {
        KNOWN: {"military": {"served": True, "branch": "Army"}},
        # THE OMITTED-FALSE GAP: `served=false` is dropped from
        # profile_json, so "did not serve" reads as "not asked".
        NEGATIVE: {"military": {"served": False}, "_disposition": NEGATIVE,
                   "_note": "served=False must SURVIVE the write"},
        DECLINED: {"_disposition": DECLINED},
        UNANSWERED: {},
    },
    "career": {
        KNOWN: {"career": "rural mail carrier, thirty-one years"},
        NEGATIVE: {"career": None, "never_worked_outside_home": True,
                   "_disposition": NEGATIVE},
        DECLINED: {"_disposition": DECLINED},
        UNANSWERED: {},
    },
    "partner": {
        KNOWN: {"spouse": {"name": "Merl", "status": "married"}},
        # THE EMPTY-ARRAY GAP: [] cannot distinguish "never married"
        # from "not asked".
        NEGATIVE: {"spouse": None, "never_married": True,
                   "_disposition": NEGATIVE},
        DECLINED: {"_disposition": DECLINED},
        UNANSWERED: {},
    },
    "children": {
        KNOWN: {"children": [{"name": "Dale"}]},
        NEGATIVE: {"children": [], "no_children": True,
                   "_disposition": NEGATIVE},
        DECLINED: {"_disposition": DECLINED},
        UNANSWERED: {},
    },
    "life_stage": {
        # THE DERIVED-GUESS GAP: the seed derives an age band; the
        # question asks retired-or-working, which an age cannot answer.
        KNOWN: {"life_stage": {"retired": True, "since": 1998}},
        NEGATIVE: {"life_stage": {"retired": False, "still_working": True},
                   "_disposition": NEGATIVE,
                   "_note": "'still working' is an ANSWER, not a non-answer"},
        DECLINED: {"_disposition": DECLINED},
        UNANSWERED: {},
    },
}


class TheFixtureSetIsCompleteTests(unittest.TestCase):
    """Structural checks on the fixtures themselves.

    A fixture set with a hole in it produces a resolver with the same
    hole, so the set is checked before it is used.
    """

    def test_all_ten_topics_are_covered(self):
        self.assertEqual(tuple(FIXTURES), TOPICS)
        self.assertEqual(len(TOPICS), 10)

    def test_every_topic_has_all_four_dispositions(self):
        for topic in TOPICS:
            with self.subTest(topic=topic):
                self.assertEqual(set(FIXTURES[topic]), set(DISPOSITIONS))

    def test_only_unanswered_is_askable(self):
        """The rule that stops the walk becoming an interrogation."""
        self.assertEqual(ASKABLE, {UNANSWERED})
        for d in (KNOWN, NEGATIVE, DECLINED):
            self.assertNotIn(d, ASKABLE)

    def test_unanswered_is_the_only_empty_shape(self):
        """A negative answer must carry evidence.

        If `NEGATIVE` were also `{}` the whole distinction would be
        notional, and the resolver would have nothing to read.
        """
        for topic in TOPICS:
            with self.subTest(topic=topic):
                self.assertEqual(FIXTURES[topic][UNANSWERED], {},
                                 "unanswered is the absence of evidence")
                self.assertNotEqual(FIXTURES[topic][NEGATIVE], {},
                                    "a negative answer that stores nothing is "
                                    "indistinguishable from never asking")
                self.assertNotEqual(FIXTURES[topic][DECLINED], {})

    def test_no_fixture_carries_narrator_prose(self):
        """Work-order decision 8: progress rows store no narrator speech.

        The fixtures model onboarding STATE. Biography stays in the
        truth stores it already lives in.
        """
        for topic in TOPICS:
            for disp in (NEGATIVE, DECLINED):
                blob = json.dumps(FIXTURES[topic][disp])
                with self.subTest(topic=topic, disposition=disp):
                    self.assertLess(
                        len(blob), 240,
                        "a progress fixture is carrying prose-sized content")


class _SeedBase(unittest.TestCase):
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

        self.pid = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO people (id, display_name, date_of_birth, place_of_birth,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (self.pid, "Verlie Ostrander", "1936-11-08",
             "Devils Lake, North Dakota", "2026-08-26", "2026-08-26"))
        con.commit()
        con.close()

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

    def _seed(self):
        return _pc._build_profile_seed(self.pid)


class TheSeedCannotAnswerTheTenQuestionsTests(_SeedBase):
    """The gaps, measured against the REAL `_build_profile_seed()`.

    The work order states these in a table. Phase 0's job is to make
    them executable, so that Phase 1 designs a resolver against what the
    function actually returns rather than against a description of it.
    """

    def test_the_seed_has_no_siblings_bucket(self):
        """The walk asks about siblings; the seed cannot record it."""
        seed = self._seed()
        self.assertNotIn("siblings", seed,
                         "if a siblings bucket now exists, the work order's "
                         "gap table is out of date — update it before "
                         "building on it")

    def test_the_seed_cannot_distinguish_none_from_unasked(self):
        """The core of the negative-answer defect.

        A narrator with no siblings and a narrator who was never asked
        produce the same seed. Nothing downstream can tell them apart,
        which is why the same question could return forever.
        """
        seed = self._seed()
        for bucket in ("children", "spouse", "military"):
            with self.subTest(bucket=bucket):
                value = seed.get(bucket)
                self.assertIn(
                    value, (None, "", [], {}, "(not on record yet)"),
                    "an unanswered topic should read as empty here; if it "
                    "does not, the disposition model has changed")

    def test_childhood_home_is_derived_from_birthplace(self):
        """Being born somewhere does not prove growing up there.

        The seed populates childhood home from the birthplace, so a
        narrator who moved at two years old is recorded as having grown
        up where they were born — a derived guess presented as truth,
        which principle 7 (mechanical truth must visibly project) and
        decision 6 (a derived guess may not satisfy a topic) both
        forbid.
        """
        seed = self._seed()
        birthplace = "Devils Lake, North Dakota"
        derived = [k for k, v in seed.items()
                   if isinstance(v, str) and birthplace in v]
        self.assertTrue(
            derived,
            "the birthplace no longer propagates into the seed; if that is "
            "deliberate, the gap table needs correcting")

    def test_the_seed_is_a_dict_of_buckets_not_a_completion_record(self):
        """The structural point behind all six gaps.

        `_build_profile_seed()` answers "what do we know about this
        narrator" — it was never designed to answer "which questions has
        this narrator been asked". Those are different questions, and
        the second one has no owner today. That absence, not any one
        bucket, is what Phase 1 builds.
        """
        seed = self._seed()
        self.assertIsInstance(seed, dict)
        for marker in ("asked", "disposition", "topics", "onboarding",
                       "completed"):
            self.assertNotIn(
                marker, seed,
                f"the seed now carries {marker!r}; a completion record may "
                f"have appeared and this test should become its contract")
