"""WO-03A — provenance and confirmation.

THE PROPERTY UNDER TEST, in the words that produced the work order:

    Lori must not be able to mark her own suggestions as human-confirmed
    merely by writing them into the questionnaire.

Everything here writes to a real temporary SQLite file and reads the
result back out of SQLite, never through the API. A test that checks the
API against the API cannot see the class of defect this table exists to
prevent — the lesson from
`tests/test_questionnaire_route_fanout.py`, which stayed green through a
save that destroyed ten populated values because the destruction happened
inside the seam it mocks.

The turn-verification tests build real `turns` and `sessions` rows in the
shape the live database actually has, including a system directive in the
user slot — live row 2634 — because that is the row that makes a naive
verifier record the prompt composer's own stage direction as testimony.
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

NARRATOR = "93479171-0b97-4072-bcf0-d44c7f9078ba"
OTHER = "11111111-2222-3333-4444-555555555555"

SCHEMA = """
CREATE TABLE people (id TEXT PRIMARY KEY, display_name TEXT);

CREATE TABLE sessions (
    conv_id TEXT PRIMARY KEY,
    title TEXT,
    updated_at TEXT,
    payload_json TEXT,
    person_id TEXT,
    person_id_source TEXT
);
CREATE TABLE turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conv_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    ts TEXT NOT NULL,
    anchor_id TEXT DEFAULT '',
    meta_json TEXT DEFAULT '{}'
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
    person_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    questionnaire_json TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'unknown',
    schema_version INTEGER NOT NULL DEFAULT 1,
    content_updated_at TEXT,
    superseded_at TEXT NOT NULL,
    superseded_by_source TEXT NOT NULL DEFAULT 'unknown',
    write_kind TEXT NOT NULL DEFAULT 'merge',
    changed_paths TEXT,
    removed_paths TEXT,
    previous_values TEXT,
    previous_provenance TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
);
"""


def _provenance_ddl() -> str:
    """The provenance table, taken from the migration rather than retyped.

    A test that declares its own copy of the schema is testing a schema
    nobody ships. The CHECK constraints in particular are load-bearing
    here — one of them is the only thing standing between an operator
    entry and a fabricated chat citation — so they must be the real ones.
    """
    sql = (REPO / "server" / "code" / "db" / "migrations"
           / "0059_answer_provenance.sql").read_text(encoding="utf-8")
    start = sql.index("CREATE TABLE IF NOT EXISTS bio_builder_answer_provenance")
    end = sql.index("ALTER TABLE bio_builder_questionnaire_revisions")
    return sql[start:end]


class _Base(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="prov-")
        self.db_path = os.path.join(self.dir, "test.sqlite3")
        con = sqlite3.connect(self.db_path)
        con.executescript(SCHEMA)
        con.executescript(_provenance_ddl())
        con.execute("INSERT INTO people (id, display_name) VALUES (?,?)",
                    (NARRATOR, "Janice"))
        con.execute("INSERT INTO people (id, display_name) VALUES (?,?)",
                    (OTHER, "Kent"))
        con.commit()
        con.close()

        from api import db as _db
        self._real_connect = _db._connect

        def _connect():
            c = sqlite3.connect(self.db_path)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys=ON")
            return c

        _db._connect = _connect

    def tearDown(self):
        from api import db as _db
        _db._connect = self._real_connect

    # ── helpers ──────────────────────────────────────────────────────

    def _con(self):
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    def _add_turn(self, turn_id, conv_id, role, content, owner, meta=None):
        c = self._con()
        c.execute(
            "INSERT OR IGNORE INTO sessions(conv_id,title,updated_at,payload_json,"
            "person_id,person_id_source) VALUES (?,?,?,?,?,?)",
            (conv_id, "", "2026-09-20T00:00:00", "{}", owner,
             "explicit" if owner else None),
        )
        c.execute(
            "INSERT INTO turns(id,conv_id,role,content,ts,anchor_id,meta_json) "
            "VALUES (?,?,?,?,?,?,?)",
            (turn_id, conv_id, role, content, "2026-09-20T00:00:00", "",
             json.dumps(meta or {})),
        )
        c.commit()
        c.close()

    def _prov(self, section, entry_id, field, person_id=NARRATOR):
        c = self._con()
        row = c.execute(
            "SELECT * FROM bio_builder_answer_provenance "
            "WHERE person_id=? AND section=? AND entry_id=? AND field=?",
            (person_id, section, entry_id, field),
        ).fetchone()
        c.close()
        return dict(row) if row else None

    def _prov_count(self, person_id=NARRATOR):
        c = self._con()
        n = c.execute(
            "SELECT COUNT(*) FROM bio_builder_answer_provenance WHERE person_id=?",
            (person_id,),
        ).fetchone()[0]
        c.close()
        return n

    def _stored(self, person_id=NARRATOR):
        c = self._con()
        row = c.execute(
            "SELECT questionnaire_json, revision FROM bio_builder_questionnaires "
            "WHERE person_id=?", (person_id,),
        ).fetchone()
        c.close()
        return (json.loads(row["questionnaire_json"]), row["revision"]) if row else (None, None)

    def _operator(self, sections, **kw):
        from api.services.answer_provenance import AnswerOrigin, ORIGIN_OPERATOR
        return AnswerOrigin(ORIGIN_OPERATOR, sections=sections, **kw)

    def _save(self, document, origin, person_id=NARRATOR):
        from api.services import questionnaire_persistence as qp
        return qp.merge_whole_document(
            person_id, document, source="ui_save", schema_version=1,
            provenance=origin,
        )


# ═══════════════════════════════════════════════════════════════════════
# 1. The classification comes from the route, not from the payload
# ═══════════════════════════════════════════════════════════════════════

class RouteDecidesOrigin(_Base):

    def test_legacy_put_writes_no_provenance_at_all(self):
        """The shared PUT has ~20 callers, two of them Lori's own writers.

        This is the single most important assertion in the file. If the
        legacy route ever starts stamping provenance, `_syncIdentityToBB`
        and `_syncPrefillIfBlank` acquire the authority of the person at
        the keyboard — which is exactly what revision 1 of the design
        proposed and review caught.
        """
        self._save({"personal": {"fullName": "Janice Horne"}}, None)
        doc, rev = self._stored()
        self.assertEqual(doc["personal"]["fullName"], "Janice Horne")
        self.assertEqual(rev, 1, "the answer must still be written")
        self.assertEqual(self._prov_count(), 0,
                         "the legacy PUT must classify nothing")

    def test_operator_route_stamps_operator_direct(self):
        self._save({"personal": {"fullName": "Janice Horne"}},
                   self._operator(["personal"], actor_id="chris"))
        row = self._prov("personal", "", "fullName")
        self.assertIsNotNone(row)
        self.assertEqual(row["origin"], "operator_direct")
        self.assertEqual(row["actor_id"], "chris")
        self.assertEqual(row["turn_evidence"], "absent")
        self.assertEqual(row["revision"], 1)

    def test_an_operator_entry_cannot_cite_a_chat_turn(self):
        """Constructing one is refused before any SQL runs.

        An operator entry carrying turn evidence would be claiming
        support from a conversation it had no part in. The CHECK in 0059
        refuses it at the database; AnswerOrigin refuses it at the
        caller, so the failure lands where the mistake was made.
        """
        from api.services.answer_provenance import AnswerOrigin, ORIGIN_OPERATOR
        with self.assertRaises(ValueError):
            AnswerOrigin(ORIGIN_OPERATOR, source_turn_id="7",
                         turn_evidence="verified", sections=["personal"])

    def test_the_database_refuses_it_too(self):
        """Belt and braces, and deliberately so: the Python guard protects
        this process, the CHECK protects the record from any process."""
        c = self._con()
        with self.assertRaises(sqlite3.IntegrityError):
            c.execute(
                "INSERT INTO bio_builder_answer_provenance "
                "(person_id,section,entry_id,field,origin,origin_at,"
                " turn_evidence) VALUES (?,?,?,?,?,?,?)",
                (NARRATOR, "personal", "", "fullName", "operator_direct",
                 "2026-09-20", "verified"),
            )
        c.close()


# ═══════════════════════════════════════════════════════════════════════
# 2. Scope — a whole-document save classifies only its own section
# ═══════════════════════════════════════════════════════════════════════

class SectionScope(_Base):

    def test_changes_outside_the_declared_section_are_not_classified(self):
        """The form saves one section and sends the whole document.

        A path that moved elsewhere in the same request moved for some
        other reason — a draft mirror, a prefill, an identity sync.
        Attributing it to the operator credits them with something they
        did not do.
        """
        self._save(
            {"personal": {"fullName": "Janice Horne"},
             "technology": {"culturalPractices": "Germans from Russia"}},
            self._operator(["personal"]),
        )
        self.assertIsNotNone(self._prov("personal", "", "fullName"))
        self.assertIsNone(
            self._prov("technology", "", "culturalPractices"),
            "a section the operator did not save must stay unclassified",
        )
        # ...and the ANSWER is written regardless. Scope limits the
        # claim, never the save.
        doc, _ = self._stored()
        self.assertEqual(doc["technology"]["culturalPractices"],
                         "Germans from Russia")


# ═══════════════════════════════════════════════════════════════════════
# 3. Entry identity — provenance survives a reorder
# ═══════════════════════════════════════════════════════════════════════

class EntryIdentity(_Base):

    def test_provenance_follows_the_person_not_the_slot(self):
        """The WO-02 payoff, and the reason this table is not keyed on paths.

        Two identified parents. The stored order changes. A correction
        made against the mother must still read as being about the
        mother.
        """
        self._save({"parents": [
            {"_entryId": "e_mom", "firstName": "Josephine", "occupation": "Housewife"},
            {"_entryId": "e_dad", "firstName": "Peter", "occupation": "Carpenter"},
        ]}, self._operator(["parents"], actor_id="chris"))

        mom = self._prov("parents", "e_mom", "occupation")
        self.assertEqual(mom["origin"], "operator_direct")

        # Reorder: dad is now parents[0]. Every flattened path renames.
        from api.services import questionnaire_persistence as qp
        qp.replace_questionnaire(NARRATOR, {"parents": [
            {"_entryId": "e_dad", "firstName": "Peter", "occupation": "Carpenter"},
            {"_entryId": "e_mom", "firstName": "Josephine", "occupation": "Housewife"},
        ]}, source="reorder")

        self.assertEqual(
            self._prov("parents", "e_mom", "occupation")["origin"],
            "operator_direct",
            "a reorder must not move an entry's provenance",
        )
        self.assertIsNotNone(self._prov("parents", "e_mom", "occupation"))

    def test_an_entry_without_an_id_is_not_classified(self):
        """Positional identity is what WO-02 removed. Falling back to the
        ordinal here would reintroduce it in the one table whose whole
        purpose is to survive a reorder.

        The answer is still saved — a pre-WO-02 entry gains an id on the
        next save and becomes classifiable then.
        """
        self._save({"parents": [{"firstName": "Josephine"}]},
                   self._operator(["parents"]))
        doc, _ = self._stored()
        self.assertEqual(doc["parents"][0]["firstName"], "Josephine")
        self.assertEqual(self._prov_count(), 0)

    def test_the_entry_id_itself_is_never_classified(self):
        """Recording that an operator "entered" an identifier the code
        minted would be the system attributing its own bookkeeping to a
        person."""
        self._save({"parents": [{"_entryId": "e_mom", "firstName": "Josephine"}]},
                   self._operator(["parents"]))
        self.assertIsNotNone(self._prov("parents", "e_mom", "firstName"))
        self.assertIsNone(self._prov("parents", "e_mom", "_entryId"))
        self.assertEqual(self._prov_count(), 1)


# ═══════════════════════════════════════════════════════════════════════
# 4. Turn verification
# ═══════════════════════════════════════════════════════════════════════

class TurnVerification(_Base):

    def _narrator(self, sections, turn_id, text=None, person_id=NARRATOR):
        from api.services.answer_provenance import (
            AnswerOrigin, ORIGIN_NARRATOR, verify_turn)
        c = self._con()
        try:
            evidence = verify_turn(c, person_id, turn_id)
        finally:
            c.close()
        return AnswerOrigin(
            ORIGIN_NARRATOR, actor_id=person_id,
            source_turn_id=(turn_id or None), turn_evidence=evidence,
            original_text=text, sections=sections,
        ), evidence

    def test_a_real_turn_by_this_narrator_verifies(self):
        self._add_turn(100, "conv_a", "user", "I was born in Spokane", NARRATOR)
        origin, ev = self._narrator(["personal"], "100", "I was born in Spokane")
        self.assertEqual(ev, "verified")
        self._save({"personal": {"placeOfBirth": "Spokane, Washington"}}, origin)
        row = self._prov("personal", "", "placeOfBirth")
        self.assertEqual(row["origin"], "narrator_direct")
        self.assertEqual(row["turn_evidence"], "verified")
        self.assertEqual(row["source_turn_id"], "100")
        self.assertEqual(row["original_text"], "I was born in Spokane")

    def test_a_system_directive_never_verifies(self):
        """Live row 2634, reproduced.

        Composed guidance travels in the user message slot. Without the
        directive clause the prompt composer's own stage direction
        becomes citable as something the narrator said.
        """
        self._add_turn(
            101, "conv_a", "user",
            "[SYSTEM: The narrator has been quiet for a while. Offer...]",
            NARRATOR, meta={"origin": "system_directive"},
        )
        origin, ev = self._narrator(["personal"], "101")
        self.assertEqual(ev, "unverified")

    def test_another_narrators_turn_never_verifies(self):
        self._add_turn(102, "conv_b", "user", "I was born in Fargo", OTHER)
        origin, ev = self._narrator(["personal"], "102")
        self.assertEqual(ev, "unverified")

    def test_an_assistant_turn_never_verifies(self):
        """An assistant row is Lori talking. Citing it as narrator
        testimony is the model quoting itself into the record."""
        self._add_turn(103, "conv_a", "assistant", "You were born in Spokane?",
                       NARRATOR)
        origin, ev = self._narrator(["personal"], "103")
        self.assertEqual(ev, "unverified")

    def test_an_ownerless_session_never_verifies(self):
        """1,468 of 1,487 live turns are in this state — pre-0045, or
        written through the REST chat path which still mints ownerless
        sessions. A citation to one of them must fail."""
        self._add_turn(104, "conv_c", "user", "I was born in Spokane", None)
        origin, ev = self._narrator(["personal"], "104")
        self.assertEqual(ev, "unverified")

    def test_no_citation_reads_absent_not_unverified(self):
        """'Nobody cited anything' and 'somebody cited something that did
        not check out' are different facts and the second is the one
        worth investigating."""
        origin, ev = self._narrator(["personal"], "")
        self.assertEqual(ev, "absent")

    def test_the_answer_is_saved_when_verification_fails(self):
        """A bookkeeping failure must not discard what the narrator said.

        What a failure changes is the CLAIM, not the answer.
        """
        origin, ev = self._narrator(["personal"], "999999", "I was born in Spokane")
        self.assertEqual(ev, "unverified")
        self._save({"personal": {"placeOfBirth": "Spokane, Washington"}}, origin)
        doc, rev = self._stored()
        self.assertEqual(doc["personal"]["placeOfBirth"], "Spokane, Washington")
        self.assertEqual(rev, 1)
        row = self._prov("personal", "", "placeOfBirth")
        self.assertEqual(row["turn_evidence"], "unverified")

    def test_a_failed_citation_is_retained_not_nulled(self):
        """Nulling it would erase the difference between 'no citation' and
        'a citation that did not check out'."""
        origin, _ = self._narrator(["personal"], "999999")
        self._save({"personal": {"placeOfBirth": "Spokane"}}, origin)
        row = self._prov("personal", "", "placeOfBirth")
        self.assertEqual(row["source_turn_id"], "999999")
        self.assertEqual(row["turn_evidence"], "unverified")

    def test_unverified_is_distinguishable_from_verified_in_one_column(self):
        """The distinction has to be readable without joining anything, or
        a consumer in a hurry will read the id and treat it as support."""
        self._add_turn(200, "conv_a", "user", "real", NARRATOR)
        good, _ = self._narrator(["personal"], "200")
        self._save({"personal": {"fullName": "Janice"}}, good)
        bad, _ = self._narrator(["earlyMemories"], "999999")
        self._save({"earlyMemories": {"firstMemory": "Milked cows"}}, bad)
        self.assertEqual(
            self._prov("personal", "", "fullName")["turn_evidence"], "verified")
        self.assertEqual(
            self._prov("earlyMemories", "", "firstMemory")["turn_evidence"],
            "unverified")


# ═══════════════════════════════════════════════════════════════════════
# 5. A no-op writes nothing — including no provenance
# ═══════════════════════════════════════════════════════════════════════

class NoOpChangesNothing(_Base):

    def test_an_unchanged_save_does_not_restamp_provenance(self):
        """Same reasoning that keeps a no-op from burning a revision: an
        answer nobody changed was not freshly entered, and recording a
        new origin_at for it would make the history lie about when the
        person said it."""
        self._save({"personal": {"fullName": "Janice Horne"}},
                   self._operator(["personal"], actor_id="chris"))
        first = self._prov("personal", "", "fullName")

        self._save({"personal": {"fullName": "Janice Horne"}},
                   self._operator(["personal"], actor_id="someone_else"))
        again = self._prov("personal", "", "fullName")

        self.assertEqual(again["origin_at"], first["origin_at"])
        self.assertEqual(again["actor_id"], "chris")
        _, rev = self._stored()
        self.assertEqual(rev, 1, "and the revision must not move either")


# ═══════════════════════════════════════════════════════════════════════
# 6. A correction preserves what it replaced
# ═══════════════════════════════════════════════════════════════════════

class CorrectionsPreserveHistory(_Base):

    def test_superseded_provenance_is_archived_with_the_superseded_value(self):
        """The archive row already carries what the value WAS. It now
        carries where that value CAME FROM, written in the same
        transaction, so the pair always describes the same moment."""
        self._add_turn(300, "conv_a", "user", "Spokane", NARRATOR)
        from api.services.answer_provenance import (
            AnswerOrigin, ORIGIN_NARRATOR, verify_turn)
        c = self._con()
        ev = verify_turn(c, NARRATOR, "300")
        c.close()
        self._save({"personal": {"placeOfBirth": "Spokane"}},
                   AnswerOrigin(ORIGIN_NARRATOR, actor_id=NARRATOR,
                                source_turn_id="300", turn_evidence=ev,
                                original_text="Spokane", sections=["personal"]))

        # An operator corrects it.
        self._save({"personal": {"placeOfBirth": "Spokane, Washington"}},
                   self._operator(["personal"], actor_id="chris"))

        con = self._con()
        row = con.execute(
            "SELECT previous_values, previous_provenance "
            "FROM bio_builder_questionnaire_revisions "
            "WHERE person_id=? ORDER BY id DESC LIMIT 1", (NARRATOR,),
        ).fetchone()
        con.close()
        prev_vals = json.loads(row["previous_values"])
        prev_prov = json.loads(row["previous_provenance"])
        self.assertEqual(prev_vals["personal.placeOfBirth"], "Spokane")
        archived = prev_prov["personal||placeOfBirth"]
        self.assertEqual(archived["origin"], "narrator_direct")
        self.assertEqual(archived["turn_evidence"], "verified")
        self.assertEqual(archived["source_turn_id"], "300")

        # And the CURRENT row names the correction.
        now = self._prov("personal", "", "placeOfBirth")
        self.assertEqual(now["origin"], "operator_direct")
        self.assertEqual(now["actor_id"], "chris")
        self.assertEqual(now["turn_evidence"], "absent")

    def test_a_write_with_no_prior_provenance_archives_an_empty_map(self):
        """'{}' rather than NULL: the column means "we looked and there
        was none", which is a different fact from "nobody ever looked"."""
        self._save({"personal": {"fullName": "Janice"}},
                   self._operator(["personal"]))
        self._save({"personal": {"preferredName": "Jan"}},
                   self._operator(["personal"]))
        con = self._con()
        row = con.execute(
            "SELECT previous_provenance FROM bio_builder_questionnaire_revisions "
            "WHERE person_id=? ORDER BY id DESC LIMIT 1", (NARRATOR,),
        ).fetchone()
        con.close()
        self.assertEqual(json.loads(row["previous_provenance"]), {})


# ═══════════════════════════════════════════════════════════════════════
# 7. Absence is a state
# ═══════════════════════════════════════════════════════════════════════

class AbsenceIsAState(_Base):

    def test_existing_answers_get_no_rows_and_keep_none(self):
        """Janice's 100 values, Kent's 86, Christopher's 130. Inventing
        provenance for them would be the system asserting something
        nobody told it — the exact failure this table exists to end."""
        con = self._con()
        con.execute(
            "INSERT INTO bio_builder_questionnaires "
            "(person_id,questionnaire_json,source,version,revision,updated_at) "
            "VALUES (?,?,?,?,?,?)",
            (NARRATOR, json.dumps({"personal": {"fullName": "Janice Horne"}}),
             "legacy", 1, 7, "2026-09-01T00:00:00"),
        )
        con.commit()
        con.close()

        from api.services.answer_provenance import load_provenance
        self.assertEqual(load_provenance(NARRATOR), {})

        # An unrelated legacy save does not invent any either.
        self._save({"personal": {"preferredName": "Jan"}}, None)
        self.assertEqual(load_provenance(NARRATOR), {})

    def test_load_provenance_returns_what_was_written(self):
        self._save({"parents": [{"_entryId": "e_mom", "firstName": "Josephine"}]},
                   self._operator(["parents"], actor_id="chris"))
        from api.services.answer_provenance import load_provenance
        got = load_provenance(NARRATOR)
        self.assertIn("parents|e_mom|firstName", got)
        self.assertEqual(got["parents|e_mom|firstName"]["origin"],
                         "operator_direct")


# ═══════════════════════════════════════════════════════════════════════
# 8. A deleted answer takes its provenance with it
# ═══════════════════════════════════════════════════════════════════════

class DeletionRemovesProvenance(_Base):

    def test_removing_a_value_removes_its_provenance(self):
        """Provenance that outlives the value it describes is worse than
        none: it is a confident statement about something that is not
        there."""
        self._save({"parents": [{"_entryId": "e_mom", "firstName": "Josephine",
                                 "occupation": "Housewife"}]},
                   self._operator(["parents"]))
        self.assertIsNotNone(self._prov("parents", "e_mom", "occupation"))

        from api.services import questionnaire_persistence as qp
        qp.merge_questionnaire(NARRATOR, {}, ["parents[0].occupation"],
                               source="delete")

        self.assertIsNone(self._prov("parents", "e_mom", "occupation"))
        self.assertIsNotNone(self._prov("parents", "e_mom", "firstName"),
                             "the sibling field is untouched")


if __name__ == "__main__":
    unittest.main(verbosity=2)
