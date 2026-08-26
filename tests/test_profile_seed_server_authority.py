"""Phase 1: the server owns Profile Seed onboarding.

WO-LORI-PROFILE-SEED-REACHABILITY-01, Phase 1 (2026-08-26).

── HOW TO RUN THIS ───────────────────────────────────────────────────

    PYTHONPATH=server/code python3 -m unittest tests.test_profile_seed_server_authority

**NOT `.venv/bin/python`** — see `CLAUDE.md` under **Environment**.
`.venv` is Python 3.10.12 with NO fastapi, and the route-contract class
below imports the interview router. Under `.venv` those tests SKIP and
unittest still prints `OK`; a skip count is not a pass, and this header
exists so the next reader does not have to rediscover that.

── WHAT PHASE 1 IS AND IS NOT ────────────────────────────────────────

Phase 1 gives the walk a durable server owner. It does NOT make the
walk reachable — that is Phases 2 and 3, prompt and browser wiring. So
`tests/test_profile_seed_ordinary_intake_reachability.py` must still
report ONE EXPECTED FAILURE after this lands. A test in this file
asserts exactly that, because an unexpected success there during Phase
1 would mean something wired the composer early and nobody noticed.

── THE THREE CLAIMS THAT NEEDED REAL STORAGE ─────────────────────────

Phase 0 shipped a round of gap tests that passed vacuously: they fed
`_build_profile_seed()` invented `profile_json` keys the seed never
reads, and measured that fiction being discarded. The correction is
carried forward here as a rule with teeth:

  * every `bio_facts.field_key` in the registry is asserted to exist in
    `bio_schema` BEFORE it is used as evidence, so an invented key
    fails a named test rather than resolving to "unanswered" forever;
  * every evidence fixture is written through the real accessor
    (`bio_fact_create`, `update_profile_json`, the real projection
    row), never hand-assembled into a dict the resolver is then handed;
  * the absent case is asserted alongside every positive one, so a
    resolver that returned `known` unconditionally would fail.
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
from api.services import bio_schema as _bs  # noqa: E402
from api.services import profile_seed as _ps  # noqa: E402

try:  # route-level tests only
    from fastapi.testclient import TestClient  # noqa: F401
    _HAS_FASTAPI = True
except Exception:  # pragma: no cover
    _HAS_FASTAPI = False

_MIGRATION = "0051_profile_seed_onboarding.sql"


class _Base(unittest.TestCase):
    """One temp DATA_DIR and one temp database per test.

    `_BIO_SEED_LOADED` is reset before `init_db()` because it is a
    once-per-process gate: a suite that switches `DB_PATH` more than
    once otherwise gets an EMPTY `bio_fields` registry, after which
    every `bio_fact_create()` fails with "FOREIGN KEY constraint
    failed" — which reads like a missing person row and is not.
    `db.py:62-70` documents the reset; Phase 0 lost real time to it.
    """

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

    # ── helpers ─────────────────────────────────────────────────────
    def _con(self):
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        return con

    def _new_person(self, name="Verlie Ostrander", *, anchors=True,
                    narrator_type="live"):
        return _db.create_person(
            name,
            date_of_birth="1936-11-08" if anchors else "",
            place_of_birth="Devils Lake, North Dakota" if anchors else "",
            narrator_type=narrator_type,
        )["id"]

    def _historical_person(self, name="Historical Narrator"):
        """A person row with NO onboarding row — a pre-migration narrator."""
        pid = str(uuid.uuid4())
        con = self._con()
        con.execute(
            "INSERT INTO people (id, display_name, date_of_birth, "
            "place_of_birth, created_at, updated_at) VALUES (?,?,?,?,?,?);",
            (pid, name, "1930-01-01", "Somewhere", "2026-01-01", "2026-01-01"))
        con.commit()
        con.close()
        return pid

    def _row(self, person_id):
        con = self._con()
        row = con.execute(
            "SELECT * FROM profile_seed_onboarding WHERE person_id=?;",
            (person_id,)).fetchone()
        con.close()
        return row


# ── 1. Migration ────────────────────────────────────────────────────────
class MigrationTests(_Base):

    def test_migration_applies_and_is_recorded_as_0051(self):
        con = self._con()
        got = con.execute(
            "SELECT filename FROM schema_migrations WHERE filename=?;",
            (_MIGRATION,)).fetchone()
        con.close()
        self.assertIsNotNone(
            got, "migration 0051 did not record itself; the runner tracks by "
                 "filename and an unrecorded migration is re-applied forever")

    def test_the_table_exists_with_the_declared_columns(self):
        con = self._con()
        cols = {r["name"] for r in
                con.execute("PRAGMA table_info(profile_seed_onboarding);")}
        con.close()
        self.assertEqual(
            cols,
            {"person_id", "status", "topic_state_json", "active_topic_id",
             "version", "created_at", "updated_at", "completed_at"})

    def test_the_foreign_key_is_a_real_cascade(self):
        con = self._con()
        fks = list(con.execute(
            "PRAGMA foreign_key_list(profile_seed_onboarding);"))
        con.close()
        self.assertEqual(len(fks), 1, "expected exactly one FK, to people")
        self.assertEqual(fks[0]["table"], "people")
        self.assertEqual(
            fks[0]["on_delete"], "CASCADE",
            "without a real cascade this table would need to join the "
            "extended person-scoped delete list, which exists for tables "
            "the cascade cannot reach")

    def test_status_and_version_are_check_constrained(self):
        con = self._con()
        pid = str(uuid.uuid4())
        con.execute("INSERT INTO people (id, display_name, created_at, "
                    "updated_at) VALUES (?,?,?,?);", (pid, "x", "t", "t"))
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute(
                "INSERT INTO profile_seed_onboarding (person_id, status, "
                "topic_state_json, version, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?);", (pid, "banana", "{}", 1, "t", "t"))
        con.rollback()
        con.close()

    def test_topic_state_json_must_be_valid_json(self):
        con = self._con()
        pid = str(uuid.uuid4())
        con.execute("INSERT INTO people (id, display_name, created_at, "
                    "updated_at) VALUES (?,?,?,?);", (pid, "x", "t", "t"))
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute(
                "INSERT INTO profile_seed_onboarding (person_id, status, "
                "topic_state_json, version, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?);",
                (pid, "pending", "not json {", 1, "t", "t"))
        con.rollback()
        con.close()

    def test_pre_existing_people_receive_no_row(self):
        """The migration must not backfill.

        A narrator with no row is HISTORICAL, and that is a settled
        state rather than a gap to fill. Backfilling would mean every
        narrator who has been talking to Lori for months wakes up
        enrolled in a ten-question walk.
        """
        pid = self._historical_person()
        # Re-run init_db to prove a second boot does not backfill either.
        _db.init_db()
        self.assertIsNone(self._row(pid))
        self.assertIsNone(_db.profile_seed_resolve(pid))


# ── 2. Atomic enrollment ────────────────────────────────────────────────
class EnrollmentTests(_Base):

    def test_a_new_live_narrator_is_enrolled(self):
        pid = self._new_person(narrator_type="live")
        self.assertIsNotNone(self._row(pid))

    def test_a_new_reference_narrator_is_enrolled_identically(self):
        """Narrator type is neither an activation nor a completion
        predicate (work order decision 2)."""
        live = _db.profile_seed_resolve(self._new_person(narrator_type="live"))
        ref = _db.profile_seed_resolve(
            self._new_person("Reference Narrator", narrator_type="reference"))
        for key in ("status", "active_topic_id", "topic_state",
                    "remaining_topics", "known_topics"):
            self.assertEqual(live[key], ref[key],
                             f"{key} differed by narrator_type")

    def test_incomplete_identity_still_enrolls_but_stays_pending(self):
        """Enrollment and activation are different questions.

        The row exists from creation — that is what makes the narrator
        non-historical. The WALK waits for the anchors, which is correct
        behaviour and is pinned as such in Phase 0.
        """
        pid = self._new_person("No Anchors", anchors=False)
        self.assertIsNotNone(self._row(pid))
        state = _db.profile_seed_resolve(pid)
        self.assertEqual(state["status"], _ps.STATUS_PENDING)
        self.assertIsNone(state["active_topic_id"])
        self.assertFalse(state["identity_complete"])

    def test_forced_enrollment_failure_rolls_back_person_creation(self):
        """Both rows or neither.

        A person created without an onboarding row would be permanently
        and silently indistinguishable from a pre-migration narrator —
        excluded from the walk with nothing recording why. That is a
        worse outcome than a loud failure, so creation fails loudly.
        """
        original = _ps.enroll
        marker = "Rollback Fixture " + uuid.uuid4().hex[:6]

        def _boom(con, person_id, now):
            raise sqlite3.OperationalError("forced enrollment failure")

        _ps.enroll = _boom
        try:
            with self.assertRaises(sqlite3.OperationalError):
                _db.create_person(marker, date_of_birth="1936-11-08",
                                  place_of_birth="Devils Lake")
        finally:
            _ps.enroll = original

        con = self._con()
        left = con.execute(
            "SELECT COUNT(*) FROM people WHERE display_name=?;",
            (marker,)).fetchone()[0]
        con.close()
        self.assertEqual(
            left, 0,
            "the people row survived a failed enrollment — 'person created, "
            "onboarding best-effort' is exactly what work order 4.2 refuses")

    def test_enrollment_starts_pending_at_version_one(self):
        pid = self._new_person()
        row = self._row(pid)
        self.assertEqual(row["status"], _ps.STATUS_PENDING)
        self.assertEqual(row["version"], 1)
        self.assertIsNone(row["active_topic_id"])
        self.assertIsNone(row["completed_at"])
        self.assertEqual(json.loads(row["topic_state_json"]),
                         {t: _ps.UNANSWERED for t in _ps.TOPIC_IDS})


# ── 3. The registry is real ─────────────────────────────────────────────
class RegistryTests(_Base):

    def test_ten_topics_in_the_work_orders_order(self):
        self.assertEqual(
            _ps.TOPIC_IDS,
            ("childhood_home", "siblings", "parents_work", "heritage",
             "education", "military", "career", "partner", "children",
             "life_stage"))

    def test_every_bio_key_exists_in_bio_schema(self):
        """The anti-vacuity guard.

        An invented `field_key` cannot be written (`bio_facts.field_key`
        has a foreign key to `bio_fields`), so a resolver keyed on one
        would report "unanswered" forever while every test that fed it
        passed. Phase 0 shipped that mistake once; this test is what
        stops it recurring silently.
        """
        known = _bs.get_field_keys()
        for topic_def in _ps.TOPIC_REGISTRY:
            for key in topic_def.bio_keys:
                self.assertIn(
                    key, known,
                    f"{topic_def.topic_id} claims bio_facts key {key!r}, "
                    "which is not in the bio_schema seed")

    def test_marital_status_now_has_a_canonical_home(self):
        """Phase 0's finding, closed.

        `bio_schema` had `spouse_name`, `marriage_year` and
        `marriage_place` and nowhere to record that there was no
        marriage.
        """
        self.assertIn("marital_status", _bs.get_field_keys())
        self.assertIn("marital_status", _ps.topic("partner").bio_keys)

    def test_childhood_home_reads_no_birthplace_path(self):
        """A prohibition, asserted as one."""
        td = _ps.topic("childhood_home")
        haystack = " ".join(td.profile_paths + td.projection_paths
                            + td.bio_keys).lower()
        for banned in ("placeofbirth", "place_of_birth", "birth_place",
                       "pob", "birthplace"):
            self.assertNotIn(
                banned, haystack,
                "being born somewhere does not prove you grew up there")

    def test_life_stage_reads_no_date_of_birth_path(self):
        td = _ps.topic("life_stage")
        haystack = " ".join(td.profile_paths + td.projection_paths
                            + td.bio_keys).lower()
        for banned in ("dateofbirth", "date_of_birth", "dob", "age"):
            self.assertNotIn(
                banned, haystack,
                "an age band is arithmetic on a birthday, not an answer to "
                "'are you retired or still working'")


# ── 4. Presence, not truthiness ─────────────────────────────────────────
class PresenceTests(unittest.TestCase):

    def test_zero_and_false_are_evidence(self):
        self.assertTrue(_ps.has_value(0), "an only child answered 'none'")
        self.assertTrue(_ps.has_value(False), "'I did not serve' is an answer")
        self.assertTrue(_ps.has_value(0.0))

    def test_empty_string_list_and_none_are_not(self):
        for value in ("", "   ", [], {}, None):
            self.assertFalse(_ps.has_value(value), repr(value))

    def test_an_empty_list_cannot_stand_in_for_an_explicit_none(self):
        """§2.2's ambiguity, pinned.

        An empty `children` array cannot tell "no children" apart from
        an optional section nobody filled in, so it is not evidence
        either way. The explicit answer goes to `children_count = 0`.
        """
        self.assertFalse(_ps.has_value([]))
        self.assertTrue(_ps.has_value(0))


# ── 5. The ten evidence resolvers ───────────────────────────────────────
#: (topic_id, field_key, json value) — positive evidence, real keys only.
_POSITIVE_BIO = (
    ("childhood_home", "childhood_home_address", "Devils Lake, North Dakota"),
    ("siblings", "sibling_count", 2),
    ("parents_work", "father_occupation", "grain elevator operator"),
    ("heritage", "ethnicity_heritage", "Norwegian"),
    ("education", "highest_education_level", "High school"),
    ("military", "military_served", "yes"),
    ("career", "primary_career", "rural mail carrier"),
    ("partner", "marital_status", "married"),
    ("children", "children_count", 3),
    ("life_stage", "retirement_year", 2001),
)

#: Explicit negatives and zero counts — the answers §2.2 said the system
#: could not tell apart from silence.
_NEGATIVE_BIO = (
    ("siblings", "sibling_count", 0),
    ("children", "children_count", 0),
    ("partner", "marital_status", "never married"),
    ("military", "military_served", "no"),
    ("education", "highest_education_level", "none"),
)


class EvidenceResolverTests(_Base):

    def setUp(self):
        super().setUp()
        self.pid = self._new_person()

    def _known(self):
        return set(_db.profile_seed_resolve(self.pid)["known_topics"])

    def test_absent_evidence_leaves_all_ten_unanswered(self):
        """The control. Without it every positive case below could pass
        against a resolver that returned `known` unconditionally."""
        state = _db.profile_seed_resolve(self.pid)
        self.assertEqual(state["known_topics"], [])
        self.assertEqual(len(state["remaining_topics"]), 10)

    def test_each_topic_resolves_from_its_own_positive_evidence(self):
        for topic_id, field_key, value in _POSITIVE_BIO:
            with self.subTest(topic=topic_id):
                pid = self._new_person(f"Positive {topic_id}")
                self.assertNotIn(topic_id,
                                 _db.profile_seed_resolve(pid)["known_topics"])
                _db.bio_fact_create(
                    narrator_id=pid, field_key=field_key,
                    value_json=json.dumps(value), status="operator_entered")
                self.assertIn(
                    topic_id, _db.profile_seed_resolve(pid)["known_topics"],
                    f"{field_key}={value!r} did not answer {topic_id}")

    def test_zero_counts_and_explicit_negatives_resolve(self):
        for topic_id, field_key, value in _NEGATIVE_BIO:
            with self.subTest(topic=topic_id, value=value):
                pid = self._new_person(f"Negative {topic_id}")
                _db.bio_fact_create(
                    narrator_id=pid, field_key=field_key,
                    value_json=json.dumps(value), status="operator_entered")
                self.assertIn(
                    topic_id, _db.profile_seed_resolve(pid)["known_topics"],
                    f"an explicit {value!r} did not answer {topic_id} — this "
                    "is the failure that makes a question return forever")

    def test_a_false_boolean_in_profile_json_answers_military(self):
        """The Phase 0 finding, closed in the read direction.

        `_build_profile_seed._first_str()` accepts only strings, so
        `served` is invisible to it in BOTH directions. The resolver
        reads presence, so `False` lands.
        """
        self.assertNotIn("military", self._known())
        _db.update_profile_json(self.pid, {"military": {"served": False}},
                                merge=True, reason="test")
        self.assertIn("military", self._known())

    def test_a_true_boolean_in_profile_json_also_answers_military(self):
        _db.update_profile_json(self.pid, {"military": {"served": True}},
                                merge=True, reason="test")
        self.assertIn("military", self._known())

    def test_birthplace_alone_never_answers_childhood_home(self):
        """The narrator was created WITH a place of birth in setUp."""
        self.assertNotIn("childhood_home", self._known())
        _db.update_profile_json(
            self.pid,
            {"personal": {"placeOfBirth": "Devils Lake, North Dakota"},
             "basics": {"pob": "Devils Lake, North Dakota"}},
            merge=True, reason="test")
        self.assertNotIn(
            "childhood_home", self._known(),
            "birthplace satisfied childhood home — the bucket would be "
            "named for a question it never answers")

    def test_a_real_childhood_home_fact_does_answer_it(self):
        """The other half: the prohibition must not be a blanket refusal."""
        _db.bio_fact_create(
            narrator_id=self.pid, field_key="childhood_home_address",
            value_json=json.dumps("Devils Lake, North Dakota"),
            status="operator_entered")
        self.assertIn("childhood_home", self._known())

    def test_age_alone_never_answers_life_stage(self):
        """setUp's narrator was born in 1936 and is plainly elderly."""
        self.assertNotIn("life_stage", self._known())

    def test_retirement_status_answers_life_stage(self):
        _db.update_profile_json(
            self.pid, {"community": {"retirementStatus": "still working"}},
            merge=True, reason="test")
        self.assertIn(
            "life_stage", self._known(),
            "a narrator who says they still work at ninety is answered by "
            "that sentence, not by their birthday")

    def test_education_reads_the_field_intake_actually_writes(self):
        """`education.highestLevel` is what `POST /api/people/intake`
        writes; the seed reads `schooling`/`higherEducation` and so
        cannot see an operator-supplied answer."""
        _db.update_profile_json(
            self.pid, {"education": {"highestLevel": "High school"}},
            merge=True, reason="test")
        self.assertIn("education", self._known())

    def test_provisional_projection_values_are_evidence(self):
        """CLAUDE.md principle 5: provisional truth persists and Lori
        reads from it. A narrator should not be re-asked something they
        said last Tuesday because the review queue is long."""
        _db.upsert_projection(self.pid, {
            "fields": {"community.role": {"value": "rural mail carrier"}},
        }, source="test")
        self.assertIn("career", self._known())

    def test_pending_superseded_and_conflicted_facts_are_not_evidence(self):
        for status in ("anchored_asked_pending", "superseded", "conflicted",
                       "empty"):
            with self.subTest(status=status):
                pid = self._new_person(f"Status {status}")
                _db.bio_fact_create(
                    narrator_id=pid, field_key="primary_career",
                    value_json=json.dumps("mail carrier"), status=status)
                self.assertNotIn(
                    "career", _db.profile_seed_resolve(pid)["known_topics"],
                    f"a {status!r} row was treated as an answer")

    def test_parent_names_without_occupations_do_not_answer_parents_work(self):
        """The question is what they DID, not who they were."""
        _db.update_profile_json(
            self.pid, {"parents": [{"firstName": "Merl"},
                                   {"firstName": "Alma"}]},
            merge=True, reason="test")
        self.assertNotIn("parents_work", self._known())
        _db.update_profile_json(
            self.pid, {"parents": [{"firstName": "Merl",
                                    "occupation": "grain elevator"}]},
            merge=True, reason="test")
        self.assertIn("parents_work", self._known())


# ── 6. Reconciliation ───────────────────────────────────────────────────
class ReconciliationTests(_Base):

    def setUp(self):
        super().setUp()
        self.pid = self._new_person()

    def test_anchors_promote_pending_to_active(self):
        state = _db.profile_seed_resolve(self.pid)
        self.assertEqual(state["status"], _ps.STATUS_ACTIVE)
        self.assertEqual(state["active_topic_id"], "childhood_home")

    def test_the_active_topic_is_the_first_remaining_in_registry_order(self):
        _db.bio_fact_create(
            narrator_id=self.pid, field_key="childhood_home_address",
            value_json=json.dumps("Devils Lake"), status="operator_entered")
        self.assertEqual(
            _db.profile_seed_resolve(self.pid)["active_topic_id"], "siblings")

    def test_version_moves_only_when_effective_state_changes(self):
        first = _db.profile_seed_resolve(self.pid)["version"]
        second = _db.profile_seed_resolve(self.pid)["version"]
        self.assertEqual(
            first, second,
            "a resolve that discovered nothing new bumped the version, which "
            "would invalidate every client's in-flight write for no reason")
        _db.bio_fact_create(
            narrator_id=self.pid, field_key="sibling_count",
            value_json=json.dumps(0), status="operator_entered")
        self.assertGreater(_db.profile_seed_resolve(self.pid)["version"],
                           second)

    def test_stored_dispositions_survive_reconciliation(self):
        state = _db.profile_seed_resolve(self.pid)
        after = _db.profile_seed_apply(
            self.pid, expected_version=state["version"],
            action="declined", topic_id="childhood_home")
        self.assertEqual(after["topic_state"]["childhood_home"],
                         _ps.DECLINED)
        again = _db.profile_seed_resolve(self.pid)
        self.assertEqual(
            again["topic_state"]["childhood_home"], _ps.DECLINED,
            "a declined topic was recomputed away — 'I would rather not "
            "discuss that' is an answer and must not expire")

    def test_known_is_recomputed_and_does_not_fossilise(self):
        """Evidence removed is evidence gone.

        `known` is derived on every resolve precisely so that a
        corrected or superseded fact does not leave a permanent `known`
        marking a question answered when it no longer is.
        """
        _db.bio_fact_create(
            narrator_id=self.pid, field_key="sibling_count",
            value_json=json.dumps(2), status="operator_entered")
        self.assertIn("siblings",
                      _db.profile_seed_resolve(self.pid)["known_topics"])
        con = self._con()
        con.execute("UPDATE bio_facts SET status='superseded' "
                    "WHERE narrator_id=?;", (self.pid,))
        con.commit()
        con.close()
        self.assertNotIn("siblings",
                         _db.profile_seed_resolve(self.pid)["known_topics"])

    def test_completion_is_derived_and_terminal(self):
        state = _db.profile_seed_resolve(self.pid)
        for topic_id in _ps.TOPIC_IDS:
            state = _db.profile_seed_apply(
                self.pid, expected_version=state["version"],
                action="addressed", topic_id=topic_id)
        self.assertEqual(state["status"], _ps.STATUS_COMPLETED)
        self.assertIsNone(state["active_topic_id"])
        self.assertTrue(state["completed_at"])

        stamped = state["completed_at"]
        version = state["version"]
        again = _db.profile_seed_resolve(self.pid)
        self.assertEqual(again["status"], _ps.STATUS_COMPLETED)
        self.assertEqual(again["completed_at"], stamped,
                         "completed_at moved on a second resolve")
        self.assertEqual(again["version"], version,
                         "a terminal row bumped its version")

    #: One evidence-bearing bio fact per topic, so a walk can be
    #: completed ENTIRELY from `known` rather than from stored
    #: dispositions. That distinction is the whole point of the test
    #: below — see its docstring.
    _EVIDENCE_FOR_EVERY_TOPIC = (
        ("childhood_home_address", "Devils Lake, North Dakota"),
        ("sibling_count", 1),
        ("father_occupation", "grain elevator operator"),
        ("ethnicity_heritage", "Norwegian"),
        ("highest_education_level", "High school"),
        ("military_served", "no"),
        ("primary_career", "rural mail carrier"),
        ("marital_status", "married"),
        ("children_count", 2),
        ("retirement_year", 2001),
    )

    def test_a_completed_narrator_is_not_enrolled_again(self):
        """Completion survives its own evidence disappearing.

        *(An earlier version of this test completed the walk by marking
        all ten `addressed` and then deleted the bio facts. It passed
        against a mutation that removed the terminal short-circuit
        entirely — because `addressed` is durable, so deleting evidence
        changed nothing and the test was measuring the wrong guard. It
        is rewritten to complete the walk ENTIRELY FROM EVIDENCE, which
        is the case the short-circuit actually protects.)*

        `known` is recomputed on every resolve, deliberately. Without a
        terminal `completed`, a narrator who finished onboarding and
        then had a fact superseded during operator review would be
        walked back into the questionnaire — nine answers they had
        already given, plus one they thought they had.
        """
        for field_key, value in self._EVIDENCE_FOR_EVERY_TOPIC:
            _db.bio_fact_create(
                narrator_id=self.pid, field_key=field_key,
                value_json=json.dumps(value), status="operator_entered")

        state = _db.profile_seed_resolve(self.pid)
        self.assertEqual(
            state["status"], _ps.STATUS_COMPLETED,
            "the ten evidence fixtures did not complete the walk, so this "
            "test would prove nothing about a completed narrator")
        self.assertEqual(len(state["known_topics"]), 10)
        self.assertEqual(state["topic_state"],
                         {t: _ps.KNOWN for t in _ps.TOPIC_IDS},
                         "completion came from a stored disposition rather "
                         "than from evidence")

        con = self._con()
        con.execute("UPDATE bio_facts SET status='superseded' "
                    "WHERE narrator_id=?;", (self.pid,))
        con.commit()
        con.close()

        after = _db.profile_seed_resolve(self.pid)
        self.assertEqual(
            after["status"], _ps.STATUS_COMPLETED,
            "superseding the evidence re-opened a completed walk — the "
            "narrator would be asked all ten questions a second time")
        self.assertIsNone(after["active_topic_id"])
        self.assertEqual(after["remaining_topics"], [])
        self.assertEqual(after["completed_at"], state["completed_at"])

    def test_pause_and_resume(self):
        state = _db.profile_seed_resolve(self.pid)
        paused = _db.profile_seed_apply(
            self.pid, expected_version=state["version"], action="pause")
        self.assertEqual(paused["status"], _ps.STATUS_PAUSED)
        self.assertIsNone(paused["active_topic_id"],
                          "a paused walk still named an active topic")
        resumed = _db.profile_seed_apply(
            self.pid, expected_version=paused["version"], action="resume")
        self.assertEqual(resumed["status"], _ps.STATUS_ACTIVE)
        self.assertEqual(resumed["active_topic_id"], "childhood_home")

    def test_resolving_a_historical_narrator_never_enrolls_them(self):
        pid = self._historical_person()
        self.assertIsNone(_db.profile_seed_resolve(pid))
        self.assertIsNone(self._row(pid))

    def test_no_narrator_prose_enters_topic_state_json(self):
        state = _db.profile_seed_resolve(self.pid)
        _db.profile_seed_apply(
            self.pid, expected_version=state["version"],
            action="declined", topic_id="childhood_home")
        stored = json.loads(self._row(self.pid)["topic_state_json"])
        self.assertTrue(
            _ps.contains_no_prose(stored),
            "the progress row carried something that is not a canonical "
            "topic mapped to one of four states")
        self.assertEqual(set(stored), set(_ps.TOPIC_IDS))
        self.assertTrue(set(stored.values()) <= set(_ps.TOPIC_STATES))


# ── 7. Version conflicts and the evidence race ──────────────────────────
class ConcurrencyTests(_Base):

    def setUp(self):
        super().setUp()
        self.pid = self._new_person()
        self.state = _db.profile_seed_resolve(self.pid)

    def test_a_stale_write_returns_the_conflict_and_changes_nothing(self):
        _db.profile_seed_apply(
            self.pid, expected_version=self.state["version"],
            action="addressed", topic_id="childhood_home")
        before = json.loads(self._row(self.pid)["topic_state_json"])
        with self.assertRaises(_ps.VersionConflict) as ctx:
            _db.profile_seed_apply(
                self.pid, expected_version=self.state["version"],
                action="addressed", topic_id="siblings")
        self.assertEqual(
            json.loads(self._row(self.pid)["topic_state_json"]), before,
            "a rejected write still changed the row")
        self.assertEqual(ctx.exception.current.person_id, self.pid,
                         "the 409 did not carry the current state, so the "
                         "client cannot recover without a second round trip")

    def test_evidence_changing_between_get_and_patch_is_rejected_safely(self):
        """THE TRAP the work order names, exercised end to end.

        The client GETs while `childhood_home` is active. The operator
        then enters the childhood home in Bio Builder. The client
        PATCHes `childhood_home` as addressed, carrying a version that
        was correct when it was read.

        Testing `expected_version` against the progress row alone would
        accept that write: nothing the client could observe had changed.
        Re-resolving inside the write transaction materializes the
        operator's answer, moves the version, and the stale read is
        caught for what it is.
        """
        self.assertEqual(self.state["active_topic_id"], "childhood_home")
        _db.bio_fact_create(
            narrator_id=self.pid, field_key="childhood_home_address",
            value_json=json.dumps("Devils Lake"), status="operator_entered")
        with self.assertRaises(_ps.VersionConflict) as ctx:
            _db.profile_seed_apply(
                self.pid, expected_version=self.state["version"],
                action="addressed", topic_id="childhood_home")
        fresh = ctx.exception.current
        self.assertEqual(fresh.topic_state["childhood_home"], _ps.KNOWN)
        self.assertEqual(fresh.active_topic_id, "siblings")

    def test_a_topic_that_is_not_active_is_refused(self):
        with self.assertRaises(_ps.TopicNotActive):
            _db.profile_seed_apply(
                self.pid, expected_version=self.state["version"],
                action="addressed", topic_id="career")

    def test_an_unknown_topic_is_refused_before_any_lock(self):
        with self.assertRaises(_ps.UnknownTopic):
            _db.profile_seed_apply(
                self.pid, expected_version=self.state["version"],
                action="addressed", topic_id="favourite_colour")

    def test_a_client_cannot_declare_known_or_completed(self):
        """The illegal transitions, as a data-driven refusal.

        A client able to declare either could walk itself to the end of
        onboarding without answering anything.
        """
        for action in ("known", "completed", "unanswered", "pass2a", ""):
            with self.subTest(action=action):
                with self.assertRaises(ValueError):
                    _db.profile_seed_apply(
                        self.pid, expected_version=self.state["version"],
                        action=action, topic_id="childhood_home")

    def test_patching_a_historical_narrator_does_not_enroll_them(self):
        pid = self._historical_person()
        with self.assertRaises(_ps.NotEnrolled):
            _db.profile_seed_apply(pid, expected_version=1, action="pause")
        self.assertIsNone(self._row(pid))


# ── 8. Deletion ─────────────────────────────────────────────────────────
class DeletionTests(_Base):

    def test_the_inventory_reports_the_onboarding_row(self):
        pid = self._new_person()
        _db.profile_seed_resolve(pid)
        counts = _db.person_delete_inventory(pid)["counts"]
        self.assertEqual(counts.get("profile_seed_onboarding"), 1)

    def test_hard_delete_cascades_the_row_and_leaves_no_residue(self):
        pid = self._new_person()
        _db.profile_seed_resolve(pid)
        result = _db.hard_delete_person(pid, requested_by="test")
        self.assertTrue(result.get("erasure_complete"), result)
        con = self._con()
        left = con.execute(
            "SELECT COUNT(*) FROM profile_seed_onboarding WHERE person_id=?;",
            (pid,)).fetchone()[0]
        anywhere = con.execute(
            "SELECT COUNT(*) FROM profile_seed_onboarding;").fetchone()[0]
        con.close()
        self.assertEqual(left, 0)
        self.assertEqual(anywhere, 0, "a residue sweep found onboarding rows")

    def test_the_table_is_not_in_the_extended_list(self):
        """It has a working cascade; a second deletion path for one table
        is how the surviving one stops being tested."""
        names = {t for t, _ in _db._EXTENDED_PERSON_SCOPED_TABLES}
        self.assertNotIn("profile_seed_onboarding", names)

    def test_no_filesystem_erasure_target_was_added(self):
        from api.services import narrator_erasure as _erasure
        blob = json.dumps([
            getattr(_erasure, name, None) for name in
            ("FIXED_TARGETS", "SHARED_PURGE", "HISTORICAL_STORES")
        ], default=str).lower()
        self.assertNotIn("profile_seed", blob)
        self.assertNotIn("onboarding", blob)


# ── 9. Phase 0 stays honest ─────────────────────────────────────────────
@unittest.skipUnless(
    _HAS_FASTAPI,
    "the Phase 0 module imports chronology_accordion, which imports fastapi; "
    "under .venv this is an ERROR at import rather than a skip")
class PhaseZeroStillHoldsTests(unittest.TestCase):

    def test_the_ordinary_reachability_defect_is_still_expected_to_fail(self):
        """Phase 1 gives the walk an owner; it does not wire the prompt.

        If this starts failing, something made the walk reachable early
        — which is good news that must not arrive silently, because the
        browser promotion sites are still unchanged and the two would
        then disagree.
        """
        import tests.test_profile_seed_ordinary_intake_reachability as mod
        test = getattr(
            mod.OrdinaryIntakeReachabilityTests
            if hasattr(mod, "OrdinaryIntakeReachabilityTests")
            else mod, "test_the_ordinary_narrator_reaches_the_walk", None)
        found = False
        for name in dir(mod):
            obj = getattr(mod, name)
            if not isinstance(obj, type) or not issubclass(obj, unittest.TestCase):
                continue
            method = getattr(obj, "test_the_ordinary_narrator_reaches_the_walk",
                             None)
            if method is None:
                continue
            found = True
            self.assertTrue(
                getattr(method, "__unittest_expecting_failure__", False),
                "the ordinary-intake reachability test is no longer marked "
                "expectedFailure")
        self.assertTrue(
            found,
            "could not find test_the_ordinary_narrator_reaches_the_walk — "
            "Phase 0's defect record has been renamed or removed")


# ── 10. Route contract ──────────────────────────────────────────────────
@unittest.skipUnless(_HAS_FASTAPI,
                     "route tests need fastapi; .venv has none — a skip is "
                     "not a pass, report the count")
class RouteContractTests(_Base):

    def setUp(self):
        super().setUp()
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.routers import interview as _iv
        app = FastAPI()
        app.include_router(_iv.router)
        self.client = TestClient(app)
        self.pid = self._new_person()

    def test_get_returns_the_resolved_state(self):
        r = self.client.get("/api/interview/profile-seed",
                            params={"person_id": self.pid})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["enrolled"])
        self.assertEqual(body["active_topic_id"], "childhood_home")
        self.assertEqual(len(body["remaining_topics"]), 10)

    def test_get_on_a_historical_narrator_is_200_not_enrolled_and_writes_nothing(self):
        pid = self._historical_person()
        r = self.client.get("/api/interview/profile-seed",
                            params={"person_id": pid})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["enrolled"])
        self.assertIsNone(self._row(pid),
                          "a GET enrolled a historical narrator")

    def test_patch_records_a_disposition_and_advances(self):
        version = self.client.get(
            "/api/interview/profile-seed",
            params={"person_id": self.pid}).json()["version"]
        r = self.client.patch("/api/interview/profile-seed", json={
            "person_id": self.pid, "expected_version": version,
            "action": "addressed", "topic_id": "childhood_home"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["active_topic_id"], "siblings")

    def test_a_stale_patch_is_409_carrying_the_current_state(self):
        version = self.client.get(
            "/api/interview/profile-seed",
            params={"person_id": self.pid}).json()["version"]
        self.client.patch("/api/interview/profile-seed", json={
            "person_id": self.pid, "expected_version": version,
            "action": "addressed", "topic_id": "childhood_home"})
        r = self.client.patch("/api/interview/profile-seed", json={
            "person_id": self.pid, "expected_version": version,
            "action": "addressed", "topic_id": "siblings"})
        self.assertEqual(r.status_code, 409)
        detail = r.json()["detail"]
        self.assertEqual(detail["error"], "version_conflict")
        self.assertEqual(detail["current"]["active_topic_id"], "siblings")

    def test_an_unknown_topic_is_422(self):
        version = self.client.get(
            "/api/interview/profile-seed",
            params={"person_id": self.pid}).json()["version"]
        r = self.client.patch("/api/interview/profile-seed", json={
            "person_id": self.pid, "expected_version": version,
            "action": "addressed", "topic_id": "favourite_colour"})
        self.assertEqual(r.status_code, 422)

    def test_patching_a_historical_narrator_is_404_and_enrolls_nobody(self):
        pid = self._historical_person()
        r = self.client.patch("/api/interview/profile-seed", json={
            "person_id": pid, "expected_version": 1, "action": "pause"})
        self.assertEqual(r.status_code, 404)
        self.assertIsNone(self._row(pid))

    def test_the_identity_predicate_is_one_function(self):
        """The router alias and the service must be the same behaviour."""
        from api.routers import interview as _iv
        person = {"display_name": "Kent", "date_of_birth": "1940-01-01",
                  "place_of_birth": "Devils Lake"}
        self.assertTrue(_iv._identity_complete(person, {}))
        self.assertEqual(
            _iv._identity_complete(person, {}),
            _ps.identity_anchors_complete(person, {}))
        for missing in ("display_name", "date_of_birth", "place_of_birth"):
            partial = {k: v for k, v in person.items() if k != missing}
            with self.subTest(missing=missing):
                self.assertFalse(_iv._identity_complete(partial, {}))
                self.assertEqual(_iv._identity_complete(partial, {}),
                                 _ps.identity_anchors_complete(partial, {}))


# ── 11. The two bounded intake write-path corrections ───────────────────
@unittest.skipUnless(_HAS_FASTAPI, "intake route tests need fastapi")
class IntakeWritesTheAnswersTests(_Base):
    """Two answers the intake form collected and then threw away.

    Neither is a schema rewrite. Both are the minimum that makes the
    resolver's "explicit negative is evidence" rule reachable from the
    real product path rather than only from a test fixture.
    """

    def setUp(self):
        super().setUp()
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.routers import people as _people
        app = FastAPI()
        app.include_router(_people.router)
        self.client = TestClient(app)

    def _intake(self, **sections):
        payload = {
            "full_legal_name": "Verlie Mae Ostrander",
            "preferred_name": "Verlie",
            "date_of_birth": "1936-11-08",
            "place_of_birth": "Devils Lake, North Dakota",
            "pronouns": "she_her",
            "current_residence": "Devils Lake, North Dakota",
            "testing_only": True,
        }
        payload.update(sections)
        r = self.client.post("/api/people/intake", json=payload)
        self.assertIn(r.status_code, (200, 201), r.text)
        return r.json()["person"]["id"] if "person" in r.json() \
            else r.json()["id"]

    def _facts(self, pid, field_key):
        con = self._con()
        rows = con.execute(
            "SELECT value, status FROM bio_facts WHERE narrator_id=? "
            "AND field_key=?;", (pid, field_key)).fetchall()
        con.close()
        return [(json.loads(r["value"]), r["status"]) for r in rows]

    def test_an_unchecked_served_box_is_written_down(self):
        """"Did not serve" and "never asked" used to be identical.

        The block was `if mil and mil.served:` alone, so an operator who
        opened the military section and left the box unchecked produced
        exactly the same stored state as one who never opened it:
        nothing. Lori would go on asking a ninety-year-old about her
        service record because the system had no way to remember being
        told there wasn't one.
        """
        pid = self._intake(military={"served": False})
        self.assertEqual(self._facts(pid, "military_served"),
                         [("no", "operator_entered")])
        self.assertIn("military",
                      _db.profile_seed_resolve(pid)["known_topics"])

    def test_a_checked_served_box_still_works(self):
        pid = self._intake(military={"served": True, "branch": "Army"})
        self.assertEqual(self._facts(pid, "military_served"),
                         [("yes", "operator_entered")])
        self.assertIn("military",
                      _db.profile_seed_resolve(pid)["known_topics"])

    def test_an_absent_military_section_writes_nothing(self):
        """The mirror-image defect, refused.

        An untouched form is not an answer. Writing `served=False` for a
        section nobody opened would mark the topic answered on the
        strength of silence — the same error in the other direction.
        """
        pid = self._intake()
        self.assertEqual(self._facts(pid, "military_served"), [])
        self.assertNotIn("military",
                         _db.profile_seed_resolve(pid)["known_topics"])

    def test_never_married_now_has_somewhere_to_live(self):
        pid = self._intake(marriage={"marital_status": "never married"})
        self.assertEqual(self._facts(pid, "marital_status"),
                         [("never married", "operator_entered")])
        self.assertIn("partner",
                      _db.profile_seed_resolve(pid)["known_topics"])

    def test_intake_created_narrators_are_enrolled(self):
        pid = self._intake()
        state = _db.profile_seed_resolve(pid)
        self.assertTrue(state["enrolled"])
        self.assertEqual(state["status"], _ps.STATUS_ACTIVE)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
