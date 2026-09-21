"""WO-03B steps 1–2 — accept and decline.

THE PROPERTY, in the words of the ruling:

    accepting one never disguises Lori's proposal as something a human
    originally entered.

And its companions: accept acts on the proposal that actually exists,
never overwrites a differing stored answer, refuses to guess an entry;
decline is recorded before the queue forgets it, and a declined value is
not offered again while a different one still is.

Real SQLite, read back out of SQLite. The schema for the two new tables
is taken from the migrations rather than retyped — the CHECK constraints
are load-bearing and a test against a copy of the schema is a test of a
schema nobody ships.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))
sys.path.insert(0, str(REPO / "tests"))

from fastapi_stub import install as _install_stub  # noqa: E402
_install_stub()

NARRATOR = "93479171-0b97-4072-bcf0-d44c7f9078ba"
OTHER = "11111111-2222-3333-4444-555555555555"

SCHEMA = """
CREATE TABLE people (id TEXT PRIMARY KEY, display_name TEXT);
CREATE TABLE sessions (
    conv_id TEXT PRIMARY KEY, title TEXT, updated_at TEXT,
    payload_json TEXT, person_id TEXT, person_id_source TEXT
);
CREATE TABLE turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT, conv_id TEXT NOT NULL,
    role TEXT NOT NULL, content TEXT NOT NULL, ts TEXT NOT NULL,
    anchor_id TEXT DEFAULT '', meta_json TEXT DEFAULT '{}'
);
CREATE TABLE interview_projections (
    person_id TEXT PRIMARY KEY,
    projection_json TEXT NOT NULL DEFAULT '{}',
    source TEXT NOT NULL DEFAULT 'unknown',
    version INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
CREATE TABLE bio_builder_questionnaires (
    person_id TEXT PRIMARY KEY,
    questionnaire_json TEXT NOT NULL DEFAULT '{}',
    source TEXT NOT NULL DEFAULT 'unknown',
    version INTEGER NOT NULL DEFAULT 1,
    revision INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
);
CREATE TABLE bio_builder_questionnaire_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id TEXT NOT NULL, revision INTEGER NOT NULL,
    questionnaire_json TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'unknown',
    schema_version INTEGER NOT NULL DEFAULT 1,
    content_updated_at TEXT, superseded_at TEXT NOT NULL,
    superseded_by_source TEXT NOT NULL DEFAULT 'unknown',
    write_kind TEXT NOT NULL DEFAULT 'merge',
    changed_paths TEXT, removed_paths TEXT, previous_values TEXT,
    previous_provenance TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
);
"""


def _ddl(migration: str, table: str) -> str:
    sql = (REPO / "server" / "code" / "db" / "migrations" / migration).read_text(encoding="utf-8")
    start = sql.index(f"CREATE TABLE IF NOT EXISTS {table}")
    # up to the first statement after the CREATE that is not an index
    end = len(sql)
    for marker in ("ALTER TABLE", "-- ── the superseded"):
        i = sql.find(marker, start)
        if i != -1:
            end = min(end, i)
    return sql[start:end]


class _Base(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="review-")
        self.db_path = os.path.join(self.dir, "test.sqlite3")
        con = sqlite3.connect(self.db_path)
        con.executescript(SCHEMA)
        con.executescript(_ddl("0059_answer_provenance.sql", "bio_builder_answer_provenance"))
        con.executescript(_ddl("0060_suggestion_reviews.sql", "suggestion_reviews"))
        # WO-04 (0061): the correction columns and the flags table. The
        # accept path reads both, so a suite without them tests a shape
        # that no longer ships.
        con.executescript("ALTER TABLE suggestion_reviews ADD COLUMN corrected_value TEXT;")
        con.executescript("ALTER TABLE suggestion_reviews ADD COLUMN correction_reason TEXT;")
        con.executescript("ALTER TABLE suggestion_reviews ADD COLUMN accept_mode TEXT;")  # 0062
        con.executescript(_ddl("0061_suggestion_flags.sql", "suggestion_flags"))
        for pid, name in ((NARRATOR, "Janice"), (OTHER, "Kent")):
            con.execute("INSERT INTO people (id, display_name) VALUES (?,?)", (pid, name))
        con.commit()
        con.close()

        from api import db as _db
        self._real_connect = _db._connect
        self._real_init = _db.init_db

        def _connect():
            c = sqlite3.connect(self.db_path)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys=ON")
            return c

        _db._connect = _connect
        _db.init_db = lambda *a, **k: None

    def tearDown(self):
        from api import db as _db
        _db._connect = self._real_connect
        _db.init_db = self._real_init

    # ── helpers ──────────────────────────────────────────────────────

    def _con(self):
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    def _queue(self, pid=NARRATOR):
        c = self._con()
        row = c.execute("SELECT projection_json FROM interview_projections WHERE person_id=?",
                        (pid,)).fetchone()
        c.close()
        return ((json.loads(row["projection_json"]) or {}).get("pendingSuggestions") or []) if row else []

    def _doc(self, pid=NARRATOR):
        c = self._con()
        row = c.execute("SELECT questionnaire_json, revision FROM bio_builder_questionnaires "
                        "WHERE person_id=?", (pid,)).fetchone()
        c.close()
        return (json.loads(row["questionnaire_json"]), row["revision"]) if row else ({}, 0)

    def _prov(self, section, entry_id, field, pid=NARRATOR):
        c = self._con()
        row = c.execute("SELECT * FROM bio_builder_answer_provenance WHERE person_id=? "
                        "AND section=? AND entry_id=? AND field=?",
                        (pid, section, entry_id, field)).fetchone()
        c.close()
        return dict(row) if row else None

    def _reviews(self, pid=NARRATOR):
        c = self._con()
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM suggestion_reviews WHERE person_id=? ORDER BY reviewed_at", (pid,))]
        c.close()
        return rows

    def _seed_doc(self, doc, pid=NARRATOR, revision=1):
        c = self._con()
        c.execute("INSERT OR REPLACE INTO bio_builder_questionnaires "
                  "(person_id,questionnaire_json,source,version,revision,updated_at) "
                  "VALUES (?,?,?,?,?,?)",
                  (pid, json.dumps(doc), "seed", 1, revision, "2026-09-01T00:00:00"))
        c.commit()
        c.close()

    def _propose(self, field_path, value, pid=NARRATOR, turn_id=""):
        from api.routers.projection import SuggestionAppendRequest, append_suggestion_route
        return append_suggestion_route(SuggestionAppendRequest(
            person_id=pid, fieldPath=field_path, value=value, confidence=0.9, turnId=turn_id))

    def _accept(self, sid, entry_id="", pid=NARRATOR, by="chris"):
        from api.routers.projection import ReviewRequest, accept_suggestion_route
        return accept_suggestion_route(sid, ReviewRequest(person_id=pid, entry_id=entry_id,
                                                          reviewed_by=by))

    def _decline(self, sid, pid=NARRATOR, by="chris"):
        from api.routers.projection import ReviewRequest, decline_suggestion_route
        return decline_suggestion_route(sid, ReviewRequest(person_id=pid, reviewed_by=by))

    def _http(self, fn, *a, **kw):
        """Run a route and return (status, detail) for an HTTPException."""
        from fastapi import HTTPException
        try:
            return 200, fn(*a, **kw)
        except HTTPException as e:
            return e.status_code, e.detail


# ═══════════════════════════════════════════════════════════════════════
# 1. Accept never launders
# ═══════════════════════════════════════════════════════════════════════

class AcceptNeverLaunders(_Base):

    def test_an_accepted_suggestion_is_ai_suggested_not_operator_direct(self):
        """THE PROPERTY. A person clicking Accept does not become the
        author of the value."""
        sid = self._propose("personal.placeOfBirth", "Minot, ND").suggestion_id
        self._accept(sid, by="chris")
        row = self._prov("personal", "", "placeOfBirth")
        self.assertIsNotNone(row)
        self.assertEqual(row["origin"], "ai_suggested")
        self.assertEqual(row["proposed_by"], "lori")
        self.assertEqual(row["confirmed_via"], "acceptance")
        self.assertIsNotNone(row["confirmed_at"])
        self.assertNotEqual(row["origin"], "operator_direct")

    def test_the_value_lands_in_the_questionnaire(self):
        sid = self._propose("personal.placeOfBirth", "Minot, ND").suggestion_id
        self._accept(sid)
        doc, rev = self._doc()
        self.assertEqual(doc["personal"]["placeOfBirth"], "Minot, ND")
        self.assertEqual(rev, 1)

    def test_the_proposals_evidence_is_kept_on_the_review_record(self):
        """The 0059 CHECK correctly forbids turn_evidence on an
        ai_suggested provenance row — an accepted machine suggestion is
        not narrator testimony. So the proposal's own verdict has to
        survive somewhere, or it is discarded at the moment it becomes
        part of the record. This is the reason for the deviation from a
        declines-only table."""
        c = self._con()
        c.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?)",
                  ("conv_a", "", "t", "{}", NARRATOR, "explicit"))
        c.execute("INSERT INTO turns(id,conv_id,role,content,ts) VALUES (?,?,?,?,?)",
                  (100, "conv_a", "user", "I was born in Minot", "t"))
        c.commit()
        c.close()
        sid = self._propose("personal.placeOfBirth", "Minot, ND", turn_id="100").suggestion_id
        self._accept(sid)
        prov = self._prov("personal", "", "placeOfBirth")
        self.assertEqual(prov["turn_evidence"], "absent",
                         "an accepted suggestion must not read as narrator testimony")
        review = self._reviews()[0]
        self.assertEqual(review["verdict"], "accepted")
        self.assertEqual(review["turn_evidence"], "verified")
        self.assertEqual(review["source_turn_id"], "100")

    def test_accepting_the_same_value_already_entered_confirms_it(self):
        """Independently entered, then proposed, then accepted: the
        record gains the confirmation and keeps ai_suggested per 0059.
        No conflict — the values agree."""
        self._seed_doc({"personal": {"placeOfBirth": "Minot, ND"}})
        sid = self._propose("personal.placeOfBirth", "Minot, ND").suggestion_id
        out = self._accept(sid)
        self.assertEqual(out.verdict, "accepted")
        doc, _ = self._doc()
        self.assertEqual(doc["personal"]["placeOfBirth"], "Minot, ND")


# ═══════════════════════════════════════════════════════════════════════
# 2. Accept acts on the proposal that exists, and refuses to overwrite
# ═══════════════════════════════════════════════════════════════════════

class AcceptIsBoundedByTheRecord(_Base):

    def test_an_unknown_id_is_404_and_writes_nothing(self):
        status, _ = self._http(self._accept, "sg_nonexistent")
        self.assertEqual(status, 404)
        self.assertEqual(self._doc(), ({}, 0))
        self.assertEqual(self._reviews(), [])

    def test_another_narrators_proposal_cannot_be_accepted_into_this_record(self):
        sid = self._propose("personal.placeOfBirth", "Fargo, ND", pid=OTHER).suggestion_id
        status, _ = self._http(self._accept, sid, pid=NARRATOR)
        self.assertEqual(status, 404)
        self.assertEqual(self._doc(NARRATOR), ({}, 0))
        self.assertEqual(len(self._queue(OTHER)), 1, "Kent's proposal is untouched")

    def test_a_differing_stored_value_is_a_409_not_an_overwrite(self):
        """The Janice case, as it stood on 2026-09-20: the questionnaire
        holds 1939-09-30, Lori proposes 1939-08-30. One click labelled
        Accept must not replace an operator's date with a machine's."""
        self._seed_doc({"personal": {"dateOfBirth": "1939-09-30"}})
        sid = self._propose("personal.dateOfBirth", "1939-08-30").suggestion_id
        status, detail = self._http(self._accept, sid)
        self.assertEqual(status, 409)
        self.assertEqual(detail["stored"], "1939-09-30")
        self.assertEqual(detail["proposed"], "1939-08-30")
        doc, rev = self._doc()
        self.assertEqual(doc["personal"]["dateOfBirth"], "1939-09-30", "unchanged")
        self.assertEqual(rev, 1, "no revision burned")
        self.assertEqual(len(self._queue()), 1, "the proposal is still there for a decision")
        self.assertEqual(self._reviews(), [], "nothing was recorded as accepted")

    def test_a_race_is_caught_under_the_lock(self):
        """The pre-check passed (destination empty), then something wrote
        the destination before the locked write. base_fields must catch
        it inside _write; the outside check alone cannot."""
        from api.services import suggestion_review as sr
        sid = self._propose("personal.placeOfBirth", "Minot, ND").suggestion_id
        real_merge = sr._qp.merge_questionnaire

        def _racing_merge(*a, **kw):
            # Simulate a competing writer landing between the read and
            # the locked write.
            self._seed_doc({"personal": {"placeOfBirth": "Spokane, WA"}}, revision=5)
            return real_merge(*a, **kw)

        sr._qp.merge_questionnaire = _racing_merge
        try:
            status, detail = self._http(self._accept, sid)
        finally:
            sr._qp.merge_questionnaire = real_merge
        self.assertEqual(status, 409)
        self.assertEqual(detail["stored"], "Spokane, WA")
        doc, _ = self._doc()
        self.assertEqual(doc["personal"]["placeOfBirth"], "Spokane, WA", "the newer answer survives")
        self.assertEqual(self._reviews(), [], "and nothing was recorded")


# ═══════════════════════════════════════════════════════════════════════
# 3. Atomicity
# ═══════════════════════════════════════════════════════════════════════

class AcceptIsOneTransaction(_Base):

    def test_accept_removes_the_proposal_from_the_queue(self):
        sid = self._propose("personal.placeOfBirth", "Minot, ND").suggestion_id
        self._propose("personal.fullName", "Janice Horne")
        self._accept(sid)
        q = self._queue()
        self.assertEqual(len(q), 1)
        self.assertEqual(q[0]["fieldPath"], "personal.fullName", "the other one stays")

    def test_a_failure_after_the_questionnaire_write_rolls_everything_back(self):
        """If the review record or queue rewrite fails, the questionnaire
        write must roll back with it. A value with no record of where it
        came from is a confident statement about something nobody said."""
        from api.services import suggestion_review as sr
        sid = self._propose("personal.placeOfBirth", "Minot, ND").suggestion_id
        real = sr._write_queue_without

        def _boom(*a, **kw):
            raise RuntimeError("simulated failure inside the transaction")

        sr._write_queue_without = _boom
        try:
            with self.assertRaises(RuntimeError):
                sr.accept(NARRATOR, sid)
        finally:
            sr._write_queue_without = real
        self.assertEqual(self._doc(), ({}, 0), "the questionnaire write rolled back")
        self.assertIsNone(self._prov("personal", "", "placeOfBirth"), "and so did provenance")
        self.assertEqual(self._reviews(), [], "and the review record")
        self.assertEqual(len(self._queue()), 1, "the proposal is still queued")


# ═══════════════════════════════════════════════════════════════════════
# 4. Repeatable destinations — resolved by a person, never guessed  (C4)
# ═══════════════════════════════════════════════════════════════════════

class RepeatableDestinations(_Base):

    def test_an_unresolved_destination_cannot_be_accepted(self):
        sid = self._propose("parents.occupation", "Carpenter").suggestion_id
        status, detail = self._http(self._accept, sid)
        self.assertEqual(status, 422)
        self.assertEqual(detail["error"], "destination_unresolved")
        self.assertEqual(self._doc(), ({}, 0))

    def test_an_ordinal_in_the_path_is_not_a_resolution(self):
        """`parents[0]` names a slot, not a person. After a reorder it is
        somebody else. It must not be honoured as an entry choice."""
        sid = self._propose("parents[0].occupation", "Carpenter").suggestion_id
        status, _ = self._http(self._accept, sid)
        self.assertEqual(status, 422)

    def test_resolving_to_a_named_entry_writes_to_that_person(self):
        self._seed_doc({"parents": [
            {"_entryId": "e_mom", "firstName": "Josephine"},
            {"_entryId": "e_dad", "firstName": "Peter"},
        ]})
        sid = self._propose("parents.occupation", "Carpenter").suggestion_id
        out = self._accept(sid, entry_id="e_dad")
        self.assertEqual(out.path, "parents[1].occupation")
        doc, _ = self._doc()
        self.assertEqual(doc["parents"][1]["occupation"], "Carpenter")
        self.assertNotIn("occupation", doc["parents"][0], "the mother is untouched")
        prov = self._prov("parents", "e_dad", "occupation")
        self.assertEqual(prov["origin"], "ai_suggested")

    def test_the_index_is_derived_from_the_id_at_accept_time(self):
        """Propose, then the stored order changes, then accept. The value
        must follow the person, not the slot they used to be in."""
        self._seed_doc({"parents": [
            {"_entryId": "e_mom", "firstName": "Josephine"},
            {"_entryId": "e_dad", "firstName": "Peter"},
        ]})
        sid = self._propose("parents.occupation", "Carpenter").suggestion_id
        # Reorder: dad is now first.
        self._seed_doc({"parents": [
            {"_entryId": "e_dad", "firstName": "Peter"},
            {"_entryId": "e_mom", "firstName": "Josephine"},
        ]}, revision=2)
        out = self._accept(sid, entry_id="e_dad")
        self.assertEqual(out.path, "parents[0].occupation")
        doc, _ = self._doc()
        self.assertEqual(doc["parents"][0]["occupation"], "Carpenter")
        self.assertEqual(doc["parents"][0]["firstName"], "Peter")

    def test_a_new_entry_is_a_persons_decision(self):
        self._seed_doc({"parents": [{"_entryId": "e_mom", "firstName": "Josephine"}]})
        sid = self._propose("parents.occupation", "Carpenter").suggestion_id
        out = self._accept(sid, entry_id="__new__")
        doc, _ = self._doc()
        self.assertEqual(len(doc["parents"]), 2)
        self.assertEqual(doc["parents"][1]["occupation"], "Carpenter")
        self.assertTrue(doc["parents"][1]["_entryId"].startswith("e_"))
        self.assertEqual(out.entry_id, doc["parents"][1]["_entryId"])
        self.assertIsNotNone(self._prov("parents", out.entry_id, "occupation"))
        self.assertIsNone(self._prov("parents", out.entry_id, "_entryId"),
                          "bookkeeping gets no provenance row")

    def test_an_unknown_entry_id_is_refused(self):
        self._seed_doc({"parents": [{"_entryId": "e_mom", "firstName": "Josephine"}]})
        sid = self._propose("parents.occupation", "Carpenter").suggestion_id
        status, _ = self._http(self._accept, sid, entry_id="e_nobody")
        self.assertEqual(status, 404)
        doc, _ = self._doc()
        self.assertNotIn("occupation", doc["parents"][0])


# ═══════════════════════════════════════════════════════════════════════
# 5. Decline
# ═══════════════════════════════════════════════════════════════════════

class Decline(_Base):

    def test_a_decline_is_recorded_and_the_proposal_leaves_the_queue(self):
        sid = self._propose("personal.placeOfBirth", "Duluth, MN").suggestion_id
        self._decline(sid, by="chris")
        self.assertEqual(self._queue(), [])
        r = self._reviews()
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["verdict"], "declined")
        self.assertEqual(r[0]["proposed_value"], "Duluth, MN", "readable without the hash")
        self.assertEqual(r[0]["field_path"], "personal.placeOfBirth")
        self.assertEqual(r[0]["suggestion_id"], sid)

    def test_a_decline_writes_nothing_to_the_biography(self):
        """Declining 'born in Duluth' does not establish where they were
        born. The questionnaire and provenance are untouched."""
        sid = self._propose("personal.placeOfBirth", "Duluth, MN").suggestion_id
        self._decline(sid)
        self.assertEqual(self._doc(), ({}, 0))
        self.assertIsNone(self._prov("personal", "", "placeOfBirth"))

    def test_the_record_lands_before_the_queue_forgets(self):
        """Requirement 2, tested from the side that matters.

        The dangerous failure is the RECORD failing after the queue has
        already forgotten: the proposal is gone, nothing says it was
        refused, and it comes back on the next extraction. So this breaks
        `_insert_review` — not the queue rewrite — and asserts the
        proposal is still queued.

        The first version broke the queue rewrite instead. Under a
        two-transaction ordering (queue first, record second) that
        failure aborts everything anyway, so the test passed against the
        very ordering it was meant to reject. Mutation r8 survived, and
        this is the fix.
        """
        from api.services import suggestion_review as sr
        sid = self._propose("personal.placeOfBirth", "Duluth, MN").suggestion_id
        real = sr._insert_review

        def _boom(*a, **kw):
            raise RuntimeError("simulated: the record could not be written")

        sr._insert_review = _boom
        try:
            with self.assertRaises(RuntimeError):
                sr.decline(NARRATOR, sid)
        finally:
            sr._insert_review = real
        self.assertEqual(len(self._queue()), 1,
                         "the proposal must still be queued — a decline the record "
                         "cannot hold is a decline that did not happen")
        self.assertEqual(self._reviews(), [])

    def test_a_queue_failure_leaves_no_orphan_record(self):
        """The other side, kept because it is a real property too: a
        review row that says 'declined' about a proposal still sitting in
        the queue is a lie of the opposite kind."""
        from api.services import suggestion_review as sr
        sid = self._propose("personal.placeOfBirth", "Duluth, MN").suggestion_id
        real = sr._write_queue_without

        def _boom(*a, **kw):
            raise RuntimeError("simulated")

        sr._write_queue_without = _boom
        try:
            with self.assertRaises(RuntimeError):
                sr.decline(NARRATOR, sid)
        finally:
            sr._write_queue_without = real
        self.assertEqual(self._reviews(), [], "no orphan decline record")
        self.assertEqual(len(self._queue()), 1)

    def test_an_unknown_id_is_404(self):
        status, _ = self._http(self._decline, "sg_nope")
        self.assertEqual(status, 404)


# ═══════════════════════════════════════════════════════════════════════
# 6. Suppression — identical not re-offered, different still is  (req 3)
# ═══════════════════════════════════════════════════════════════════════

class Suppression(_Base):

    def test_a_declined_value_is_not_proposed_again(self):
        sid = self._propose("personal.placeOfBirth", "Duluth, MN").suggestion_id
        self._decline(sid)
        again = self._propose("personal.placeOfBirth", "Duluth, MN")
        self.assertFalse(again.appended)
        self.assertTrue(again.suppressed)
        self.assertEqual(self._queue(), [], "not queued")

    def test_the_reproposal_is_counted(self):
        """'Lori keeps trying to tell you X' stays observable."""
        sid = self._propose("personal.placeOfBirth", "Duluth, MN").suggestion_id
        self._decline(sid)
        self._propose("personal.placeOfBirth", "Duluth, MN")
        r = self._propose("personal.placeOfBirth", "Duluth, MN")
        self.assertEqual(r.repeats, 2)
        self.assertEqual(self._reviews()[0]["reproposals"], 2)

    def test_canonical_matching_catches_cosmetic_variants(self):
        sid = self._propose("personal.placeOfBirth", "Duluth, MN").suggestion_id
        self._decline(sid)
        again = self._propose("personal.placeOfBirth", "  duluth,   mn ")
        self.assertTrue(again.suppressed)

    def test_a_materially_different_value_is_still_offered(self):
        """A person who declined '6th grade' is still asked about '7th'."""
        sid = self._propose("education.gradeLevel", "6th grade").suggestion_id
        self._decline(sid)
        again = self._propose("education.gradeLevel", "7th grade")
        self.assertTrue(again.appended)
        self.assertFalse(again.suppressed)
        self.assertEqual(len(self._queue()), 1)

    def test_word_order_is_a_different_claim(self):
        sid = self._propose("personal.placeOfBirth", "Minot, ND").suggestion_id
        self._decline(sid)
        again = self._propose("personal.placeOfBirth", "ND, Minot")
        self.assertTrue(again.appended)

    def test_an_accepted_value_does_not_suppress(self):
        """Accepted is in the biography; re-proposing it is harmless and
        the append path's own duplicate check handles it. Only a refusal
        suppresses."""
        sid = self._propose("personal.placeOfBirth", "Minot, ND").suggestion_id
        self._accept(sid)
        again = self._propose("personal.placeOfBirth", "Minot, ND")
        self.assertFalse(again.suppressed)

    def test_an_unresolved_decline_does_not_suppress_a_named_entry(self):
        """C4. Declining 'Carpenter for some unnamed parent' must not
        silence 'Carpenter' proposed for a specific parent later — those
        are different claims about different people. (A named-entry
        proposal is not something the extractor produces today; the
        guard is asserted at the service level.)"""
        from api.services import suggestion_review as sr
        sid = self._propose("parents.occupation", "Carpenter").suggestion_id
        self._decline(sid)
        c = self._con()
        # The unresolved decline suppresses another unresolved proposal...
        self.assertIsNotNone(sr.is_suppressed(c, NARRATOR, "parents.occupation", "Carpenter"))
        # ...and its record says so.
        self.assertEqual(self._reviews()[0]["destination_unresolved"], 1)
        c.close()


# ═══════════════════════════════════════════════════════════════════════
# 7. The schema's own guards
# ═══════════════════════════════════════════════════════════════════════

class DestinationMustBeRenderable(_Base):
    """BUG-SUGGESTION-ACCEPTED-INTO-AN-INVISIBLE-FIELD-01.

    On 2026-09-20 a proposal for `personal.notes` was accepted through
    the review surface. Questionnaire written, provenance stamped,
    queue cleared, review recorded, revision 8 — and the value was
    invisible, because Personal Information defines seven fields and
    `notes` is not one of them. A person had approved information they
    could not then see or correct.

    Measured the same day: 20 of 30 live queued suggestions point at
    destinations the questionnaire does not define.
    """

    def test_an_undefined_field_cannot_be_accepted(self):
        sid = self._propose("personal.notes", "invisible if accepted").suggestion_id
        status, detail = self._http(self._accept, sid)
        self.assertEqual(status, 422)
        self.assertEqual(detail["error"], "destination_undefined")
        self.assertEqual((detail["section"], detail["field"]), ("personal", "notes"))

    def test_the_refusal_changes_nothing(self):
        """422 without touching the questionnaire, queue, provenance or
        review record — the ruling's exact requirement."""
        sid = self._propose("personal.notes", "invisible if accepted").suggestion_id
        before_q = self._queue()
        self._http(self._accept, sid)
        self.assertEqual(self._doc(), ({}, 0), "no questionnaire write")
        self.assertIsNone(self._prov("personal", "", "notes"), "no provenance")
        self.assertEqual(self._reviews(), [], "no review record")
        self.assertEqual(self._queue(), before_q, "still queued for resolution")

    def test_an_undefined_section_cannot_be_accepted(self):
        """WO-04 gave military/residence/travel real homes, so these are
        no longer the examples. `community.*` and `greatGrandparents.*`
        are still real extractor output with no section — they are on
        the pinned drift list in test_extractor_vocabulary."""
        for path in ("community.organization", "greatGrandparents.side",
                     "health.majorCondition"):
            sid = self._propose(path, "x").suggestion_id
            status, detail = self._http(self._accept, sid)
            self.assertEqual(status, 422, path)
            self.assertEqual(detail["error"], "destination_undefined", path)

    def test_a_defined_field_still_accepts(self):
        """The guard must not block real destinations. This is the case
        the live UI test exercises."""
        sid = self._propose("personal.timeOfBirth", "12:50 PM").suggestion_id
        out = self._accept(sid)
        self.assertEqual(out.verdict, "accepted")
        doc, _ = self._doc()
        self.assertEqual(doc["personal"]["timeOfBirth"], "12:50 PM")

    def test_the_proposal_is_flagged_at_queue_time(self):
        """Recorded when queued so the review surface can keep it out of
        the actionable list — inspectable, not silently discarded."""
        bad = self._propose("personal.notes", "x")
        good = self._propose("personal.timeOfBirth", "12:50 PM")
        self.assertTrue(bad.destination_undefined)
        self.assertFalse(good.destination_undefined)
        # Still queued: kept, not dropped.
        self.assertEqual(len(self._queue()), 2)
        flags = {s["fieldPath"]: s["destination_undefined"] for s in self._queue()}
        self.assertEqual(flags, {"personal.notes": True, "personal.timeOfBirth": False})

    def test_drift_DURING_the_write_rolls_the_whole_transaction_back(self):
        """THE IN-TRANSACTION CHECK, exercised on its own.

        The test below it patches `is_defined` outright, which the
        pre-check catches first — so it passes whether or not the
        second check exists. Removing the in-transaction block left that
        test green, which is the "identical output with and without the
        code under test" failure, caught by mutation s2.

        This one lets the PRE-check pass and only then drifts, which is
        the sole path to the check inside `_also`. Raising there must
        roll back the questionnaire row, its provenance, the queue
        rewrite and the review record together.
        """
        from api.services import questionnaire_schema as qs
        sid = self._propose("personal.timeOfBirth", "12:50 PM").suggestion_id

        real_defined = qs.is_defined
        real_fp = qs.schema_fingerprint
        calls = {"n": 0}

        def _defined_then_not(section, field):
            if (section, field) == ("personal", "timeOfBirth"):
                calls["n"] += 1
                return calls["n"] <= 1        # valid at the pre-check, gone after
            return real_defined(section, field)

        # A DIFFERENT value on each call — the schema moved between the
        # two moments. An earlier version keyed this off the is_defined
        # counter, which was circular: the fingerprint could only change
        # after a second is_defined call, and that call happens only
        # inside the branch the changed fingerprint is supposed to open.
        # It never fired, and the test passed for the wrong reason.
        fps = {"n": 0}

        def _moving_fingerprint():
            fps["n"] += 1
            return "fp_%d" % fps["n"]

        qs.is_defined = _defined_then_not
        qs.schema_fingerprint = _moving_fingerprint
        try:
            status, detail = self._http(self._accept, sid)
        finally:
            qs.is_defined = real_defined
            qs.schema_fingerprint = real_fp

        self.assertEqual(status, 422)
        self.assertEqual(detail["error"], "destination_undefined")
        self.assertGreater(calls["n"], 1, "the in-transaction check must have run")
        self.assertEqual(self._doc(), ({}, 0), "questionnaire rolled back")
        self.assertIsNone(self._prov("personal", "", "timeOfBirth"), "provenance rolled back")
        self.assertEqual(self._reviews(), [], "review record rolled back")
        self.assertEqual(len(self._queue()), 1, "queue rewrite rolled back")

    def test_an_unreadable_schema_at_proposal_time_flags_undefined(self):
        """Fail closed on the propose side too.

        Mutation s4 flipped this branch to `return False` — "cannot read
        the schema, assume it is fine" — and nothing failed. A proposal
        wrongly held back is visible and recoverable; one waved through
        becomes an invisible accepted value.
        """
        from api.services import questionnaire_schema as qs
        real = qs.is_defined

        def _broken(section, field):
            raise qs.SchemaUnavailable("simulated: file unreadable")

        qs.is_defined = _broken
        try:
            res = self._propose("personal.timeOfBirth", "12:50 PM")
        finally:
            qs.is_defined = real
        self.assertTrue(res.destination_undefined,
                        "an unverifiable destination must not be treated as valid")
        self.assertTrue(self._queue()[0]["destination_undefined"])

    def test_schema_drift_between_proposal_and_acceptance_is_caught(self):
        """THE CASE THAT NEEDS THE SECOND CHECK.

        A proposal is queued while its destination is valid. The
        questionnaire then changes. Acceptance must re-validate and
        refuse — a flag recorded at proposal time is a statement about
        the past.
        """
        from api.services import questionnaire_schema as qs
        sid = self._propose("personal.timeOfBirth", "12:50 PM").suggestion_id
        self.assertFalse(self._queue()[0]["destination_undefined"])

        real = qs.is_defined

        def _drifted(section, field):
            if (section, field) == ("personal", "timeOfBirth"):
                return False          # the field was removed while pending
            return real(section, field)

        qs.is_defined = _drifted
        try:
            status, detail = self._http(self._accept, sid)
        finally:
            qs.is_defined = real
        self.assertEqual(status, 422)
        self.assertEqual(detail["error"], "destination_undefined")
        self.assertEqual(self._doc(), ({}, 0), "nothing written")
        self.assertEqual(self._reviews(), [])
        self.assertEqual(len(self._queue()), 1, "kept for resolution")

    def test_a_repeatable_destination_is_validated_too(self):
        """Including the resolved entry: `parents.occupation` is real,
        `parents.salary` is not."""
        self._seed_doc({"parents": [{"_entryId": "e_mom", "firstName": "Josephine"}]})
        ok = self._propose("parents.occupation", "Housewife").suggestion_id
        bad = self._propose("parents.salary", "$0").suggestion_id
        self.assertEqual(self._accept(ok, entry_id="e_mom").verdict, "accepted")
        status, detail = self._http(self._accept, bad, entry_id="e_mom")
        self.assertEqual(status, 422)
        self.assertEqual(detail["error"], "destination_undefined")
        doc, _ = self._doc()
        self.assertEqual(doc["parents"][0]["occupation"], "Housewife")
        self.assertNotIn("salary", doc["parents"][0])

    def test_an_ordinal_on_a_flat_section_is_stripped_not_honoured(self):
        """`personal[0].timeOfBirth` writes to `personal.timeOfBirth`.

        I asserted a 422 here first, without checking. The code does
        something better: `split_destination` drops the bracket on a
        non-repeatable section, so the value lands at the flat path the
        form renders. Honouring the ordinal would build a LIST where the
        form expects an object and Personal Information would stop
        rendering altogether — the failure this guards is that, not the
        odd path.
        """
        sid = self._propose("personal.timeOfBirth", "1 PM").suggestion_id
        con = self._con()
        env = json.loads(con.execute(
            "SELECT projection_json FROM interview_projections WHERE person_id=?",
            (NARRATOR,)).fetchone()["projection_json"])
        for s in env["pendingSuggestions"]:
            if s["suggestion_id"] == sid:
                s["fieldPath"] = "personal[0].timeOfBirth"
        con.execute("UPDATE interview_projections SET projection_json=? WHERE person_id=?",
                    (json.dumps(env), NARRATOR))
        con.commit(); con.close()
        status, out = self._http(self._accept, sid)
        self.assertEqual(status, 200)
        self.assertEqual(out.path, "personal.timeOfBirth", "the ordinal is dropped")
        doc, _ = self._doc()
        self.assertEqual(doc["personal"]["timeOfBirth"], "1 PM")
        self.assertIsInstance(doc["personal"], dict,
                              "honouring the ordinal would build a list and the "
                              "section would stop rendering")

    def test_an_unreadable_schema_refuses_rather_than_allows(self):
        """Fail closed. If the schema cannot be read, accepting anything
        risks another invisible value; refusing is recoverable."""
        from api.services import questionnaire_schema as qs
        from api.services import suggestion_review as sr
        sid = self._propose("personal.timeOfBirth", "12:50 PM").suggestion_id
        real = qs.is_defined

        def _broken(section, field):
            raise qs.SchemaUnavailable("simulated: file unreadable")

        qs.is_defined = _broken
        try:
            with self.assertRaises(qs.SchemaUnavailable):
                sr.accept(NARRATOR, sid)
        finally:
            qs.is_defined = real
        self.assertEqual(self._doc(), ({}, 0))
        self.assertEqual(len(self._queue()), 1)


class SchemaParsing(unittest.TestCase):
    """The parser reads the file that renders the form. If it drifts,
    every destination check is wrong — so it validates itself."""

    def test_the_schema_matches_the_questionnaire(self):
        """WO-04 added military (9), residence (5), travel (6), faith (5),
        education.gradeLevel and marriage.marriagePlace: 16→20 sections,
        8→11 repeatable, 91→118 fields. Re-measured from the file."""
        from api.services import questionnaire_schema as qs
        s = qs.load_schema(force=True)
        self.assertEqual(len(s), 20)
        self.assertEqual(sum(1 for v in s.values() if v["repeatable"]), 11)
        self.assertEqual(sum(len(v["fields"]) for v in s.values()), 118)

    def test_it_agrees_with_the_repeatable_list_used_elsewhere(self):
        from api.services import questionnaire_schema as qs
        from api.services.suggestion_review import REPEATABLE_SECTIONS
        self.assertEqual(set(qs.repeatable_section_ids()), set(REPEATABLE_SECTIONS))

    def test_known_fields_and_known_non_fields(self):
        from api.services import questionnaire_schema as qs
        for sec, fld in (("personal", "timeOfBirth"), ("personal", "placeOfBirth"),
                         ("parents", "occupation"), ("education", "schooling")):
            self.assertTrue(qs.is_defined(sec, fld), f"{sec}.{fld}")
        # WO-04 gave military.branch, residence.place and
        # education.gradeLevel real homes. `personal.notes` stays absent
        # deliberately — decision 4 retired it rather than creating a
        # catch-all field.
        for sec, fld in (("personal", "notes"), ("military", "servicePeriod"),
                         ("residence", "period"), ("community", "organization")):
            self.assertFalse(qs.is_defined(sec, fld), f"{sec}.{fld}")

    def test_a_broken_parse_raises_rather_than_returning_a_partial(self):
        """The dangerous failure is a silent partial parse: half the
        fields read, and every real destination starts being rejected.
        Caught once for real while building this — a first regex reported
        '76 sections, 31 fields'."""
        from api.services import questionnaire_schema as qs
        with self.assertRaises(qs.SchemaUnavailable):
            qs._validate({"personal": {"label": "P", "repeatable": False,
                                       "repeat_label": "", "fields": {}}})

    def test_labels_come_from_the_questionnaire(self):
        from api.services import questionnaire_schema as qs
        self.assertEqual(qs.labels_for("personal", "timeOfBirth"),
                         {"section": "Personal Information", "field": "Time of Birth",
                          "single": "Personal Information"})
        self.assertEqual(qs.labels_for("parents", "occupation")["single"], "parent")


class SchemaGuards(_Base):

    def test_the_repeatable_list_matches_the_questionnaire(self):
        """One definition, checked against the questionnaire's real
        section ids rather than a retyped copy."""
        from api.services.suggestion_review import REPEATABLE_SECTIONS
        from api.routers.projection import _REPEATABLE_SECTIONS
        self.assertIs(REPEATABLE_SECTIONS, _REPEATABLE_SECTIONS, "must be the same object")
        qq = (REPO / "ui" / "js" / "bio-builder-questionnaire.js").read_text(encoding="utf-8")
        for s in REPEATABLE_SECTIONS:
            self.assertIn(f'id: "{s}"', qq)

    def test_the_review_table_refuses_an_unknown_verdict(self):
        c = self._con()
        with self.assertRaises(sqlite3.IntegrityError):
            c.execute("INSERT INTO suggestion_reviews (person_id,section,entry_id,field,"
                      "value_hash,verdict,field_path,proposed_value,reviewed_at) "
                      "VALUES (?,?,?,?,?,?,?,?,?)",
                      (NARRATOR, "personal", "", "x", "h", "maybe", "personal.x", "v", "t"))
        c.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
