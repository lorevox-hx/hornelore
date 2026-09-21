"""WO-04 protection layer — a flagged suggestion cannot be accepted unchanged.

THE ACCEPTANCE CRITERION FOR WO-04, in the reviewer's words:

    expanding the biography must not make an old extraction mistake
    easier to turn into a permanent family record.

Adding a `military` section flips WO-03B's destination guard for Kent's
queued `military.branch = "Nike Ajax Nike Hercules missile site"`. It
goes from "cannot be added" to one entry-pick and one click from his
family's permanent record. These tests are what stops that, and they
test the WRITE, not the interface — hiding an Accept button is
presentation; the endpoint is what writes the biography.

Real SQLite, read back from SQLite.
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

SCHEMA = """
CREATE TABLE people (id TEXT PRIMARY KEY, display_name TEXT);
CREATE TABLE sessions (conv_id TEXT PRIMARY KEY, title TEXT, updated_at TEXT,
    payload_json TEXT, person_id TEXT, person_id_source TEXT);
CREATE TABLE turns (id INTEGER PRIMARY KEY AUTOINCREMENT, conv_id TEXT NOT NULL,
    role TEXT NOT NULL, content TEXT NOT NULL, ts TEXT NOT NULL,
    anchor_id TEXT DEFAULT '', meta_json TEXT DEFAULT '{}');
CREATE TABLE interview_projections (person_id TEXT PRIMARY KEY,
    projection_json TEXT NOT NULL DEFAULT '{}', source TEXT NOT NULL DEFAULT 'unknown',
    version INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL);
CREATE TABLE bio_builder_questionnaires (person_id TEXT PRIMARY KEY,
    questionnaire_json TEXT NOT NULL DEFAULT '{}', source TEXT NOT NULL DEFAULT 'unknown',
    version INTEGER NOT NULL DEFAULT 1, revision INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL, FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE);
CREATE TABLE bio_builder_questionnaire_revisions (id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id TEXT NOT NULL, revision INTEGER NOT NULL, questionnaire_json TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'unknown', schema_version INTEGER NOT NULL DEFAULT 1,
    content_updated_at TEXT, superseded_at TEXT NOT NULL,
    superseded_by_source TEXT NOT NULL DEFAULT 'unknown', write_kind TEXT NOT NULL DEFAULT 'merge',
    changed_paths TEXT, removed_paths TEXT, previous_values TEXT,
    previous_provenance TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE);
"""


def _ddl(migration: str, first_stmt: str, stop_at=None) -> str:
    sql = (REPO / "server" / "code" / "db" / "migrations" / migration).read_text(encoding="utf-8")
    start = sql.index(first_stmt)
    end = len(sql)
    for marker in (stop_at or []):
        i = sql.find(marker, start)
        if i != -1:
            end = min(end, i)
    return sql[start:end]


class _Base(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="flags-")
        self.db_path = os.path.join(self.dir, "test.sqlite3")
        con = sqlite3.connect(self.db_path)
        con.executescript(SCHEMA)
        con.executescript(_ddl("0059_answer_provenance.sql",
                               "CREATE TABLE IF NOT EXISTS bio_builder_answer_provenance",
                               ["ALTER TABLE"]))
        # 0060 + the 0061 ALTERs it gains.
        con.executescript(_ddl("0060_suggestion_reviews.sql",
                               "CREATE TABLE IF NOT EXISTS suggestion_reviews"))
        con.executescript("ALTER TABLE suggestion_reviews ADD COLUMN corrected_value TEXT;")
        con.executescript("ALTER TABLE suggestion_reviews ADD COLUMN correction_reason TEXT;")
        con.executescript(_ddl("0061_suggestion_flags.sql",
                               "CREATE TABLE IF NOT EXISTS suggestion_flags",
                               ["ALTER TABLE"]))
        con.execute("INSERT INTO people (id, display_name) VALUES (?,?)", (NARRATOR, "Kent"))
        con.commit()
        con.close()

        from api import db as _db
        self._real_connect, self._real_init = _db._connect, _db.init_db

        def _connect():
            c = sqlite3.connect(self.db_path)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys=ON")
            return c

        _db._connect = _connect
        _db.init_db = lambda *a, **k: None

    def tearDown(self):
        from api import db as _db
        _db._connect, _db.init_db = self._real_connect, self._real_init

    # ── helpers ──────────────────────────────────────────────────────

    def _con(self):
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    def _seed_queue(self, entries):
        c = self._con()
        c.execute("INSERT OR REPLACE INTO interview_projections"
                  "(person_id,projection_json,source,version,updated_at) VALUES (?,?,?,?,?)",
                  (NARRATOR, json.dumps({"fields": {}, "pendingSuggestions": entries}),
                   "seed", 1, "t"))
        c.commit(); c.close()

    def _legacy(self, field_path, value, sid=None):
        """A row in the pre-WO-03B shape: NO `destination_undefined` key."""
        e = {"fieldPath": field_path, "value": value, "confidence": 0.9,
             "turnId": "turn-1", "ts": 1777339161106}
        if sid:
            e["suggestion_id"] = sid
        return e

    def _modern(self, field_path, value, sid="sg_modern", undefined=False):
        return {"suggestion_id": sid, "fieldPath": field_path, "value": value,
                "confidence": 0.9, "origin": "extraction", "source_turn_id": None,
                "turn_evidence": "absent", "ts": "2026-09-20T00:00:00",
                "repeats": 1, "destination_undefined": undefined,
                "destination_unresolved": False}

    def _doc(self):
        c = self._con()
        row = c.execute("SELECT questionnaire_json, revision FROM bio_builder_questionnaires "
                        "WHERE person_id=?", (NARRATOR,)).fetchone()
        c.close()
        return (json.loads(row["questionnaire_json"]), row["revision"]) if row else ({}, 0)

    def _queue(self):
        c = self._con()
        row = c.execute("SELECT projection_json FROM interview_projections WHERE person_id=?",
                        (NARRATOR,)).fetchone()
        c.close()
        return ((json.loads(row["projection_json"]) or {}).get("pendingSuggestions") or []) if row else []

    def _flags(self):
        c = self._con()
        rows = [dict(r) for r in c.execute("SELECT * FROM suggestion_flags WHERE person_id=?", (NARRATOR,))]
        c.close()
        return rows

    def _reviews(self):
        c = self._con()
        rows = [dict(r) for r in c.execute("SELECT * FROM suggestion_reviews WHERE person_id=?", (NARRATOR,))]
        c.close()
        return rows

    def _prov(self, section, field, entry_id=""):
        c = self._con()
        r = c.execute("SELECT * FROM bio_builder_answer_provenance WHERE person_id=? "
                      "AND section=? AND entry_id=? AND field=?",
                      (NARRATOR, section, entry_id, field)).fetchone()
        c.close()
        return dict(r) if r else None

    def _all_prov(self):
        """Every provenance row. Needed for repeatable sections, where the
        entry id is minted at accept time and is not known in advance."""
        c = self._con()
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM bio_builder_answer_provenance WHERE person_id=?", (NARRATOR,))]
        c.close()
        return rows

    def _accept(self, sid, **kw):
        from api.routers.projection import ReviewRequest, accept_suggestion_route
        body = {"person_id": NARRATOR}
        body.update(kw)
        return accept_suggestion_route(sid, ReviewRequest(**body))

    def _http(self, fn, *a, **kw):
        from fastapi import HTTPException
        try:
            return 200, fn(*a, **kw)
        except HTTPException as e:
            return e.status_code, e.detail

    def _stub_schema(self, defined):
        """No-op, kept so the test bodies read as written.

        These tests were first drafted to run BEFORE WO-04's sections
        existed, stubbing the schema to simulate them. The sections are
        real now, so stubbing would test a fiction — and the first
        version of this stub forced `is_repeatable` to False, which put
        it at odds with `REPEATABLE_SECTIONS` and made `accept` refuse
        every military proposal for the wrong reason ("shaped the other
        way"). Testing against the real schema is both simpler and what
        actually ships.
        """
        return None

    def _entry_kw(self, field_path):
        """Repeatable destinations need a person to choose an entry.
        `__new__` is the "add it as a new one" choice the review surface
        offers; the flag guard still runs after the destination is
        resolved, which is the point."""
        from api.services.suggestion_review import split_destination
        _sec, _fld, repeatable = split_destination(field_path)
        return {"entry_id": "__new__"} if repeatable else {}


# ═══════════════════════════════════════════════════════════════════════
# 1. The structural guard — needs no flag, cannot be missed
# ═══════════════════════════════════════════════════════════════════════

class LegacyRowsAimedAtNewSections(_Base):
    """Layer 2. A classifier that did not run, or ran incompletely, must
    not leave a hole."""

    def test_kents_missile_site_cannot_be_accepted_once_military_exists(self):
        """THE CASE THE WHOLE WORK ORDER IS FOR.

        `military.branch = "Nike Ajax Nike Hercules missile site"` —
        queued before a military section existed, no flag recorded, and
        the destination now exists. It must still be refused.
        """
        self._stub_schema(None)
        self._seed_queue([self._legacy("military.branch",
                                       "Nike Ajax Nike Hercules missile site",
                                       sid="sg_kent_branch")])
        status, detail = self._http(self._accept, "sg_kent_branch", entry_id="__new__")
        self.assertEqual(status, 422)
        self.assertEqual(detail["error"], "suggestion_flagged")
        self.assertEqual(detail["reason"], "queued_before_home")
        self.assertEqual(self._doc(), ({}, 0), "nothing written")
        self.assertEqual(self._reviews(), [], "no review record")
        self.assertEqual(len(self._queue()), 1, "still queued")

    def test_it_holds_with_no_flag_row_at_all(self):
        """The guard is structural. Prove the flags table is empty when
        it fires, or this is just testing layer 1 twice."""
        self._stub_schema(None)
        self._seed_queue([self._legacy("military.branch", "x", sid="sg_a")])
        self.assertEqual(self._flags(), [])
        status, _ = self._http(self._accept, "sg_a", entry_id="__new__")
        self.assertEqual(status, 422)
        self.assertEqual(self._flags(), [], "still no flag — the guard needed none")

    def test_all_four_new_sections_are_covered(self):
        self._stub_schema(None)
        for path in ("military.branch", "residence.place",
                     "travel.destination", "faith.denomination"):
            self._seed_queue([self._legacy(path, "x", sid="sg_" + path)])
            status, detail = self._http(self._accept, "sg_" + path, **self._entry_kw(path))
            self.assertEqual(status, 422, path)
            self.assertEqual(detail["reason"], "queued_before_home", path)

    def test_a_legacy_row_NOT_aimed_at_a_new_section_is_unaffected(self):
        """The guard is narrow on purpose. `education.schooling` was
        always acceptable; blocking it would be a regression dressed as
        caution."""
        self._stub_schema(None)
        self._seed_queue([self._legacy("education.schooling",
                                       "Bismarck High School", sid="sg_school")])
        status, out = self._http(self._accept, "sg_school")
        self.assertEqual(status, 200)
        doc, _ = self._doc()
        self.assertEqual(doc["education"]["schooling"], "Bismarck High School")

    def test_a_modern_row_aimed_at_a_new_section_is_unaffected(self):
        """A proposal queued AFTER the section exists had its destination
        checked at queue time. It is ordinary."""
        self._stub_schema(None)
        self._seed_queue([self._modern("military.branch", "Army", sid="sg_new")])
        status, out = self._http(self._accept, "sg_new", entry_id="__new__")
        self.assertEqual(status, 200)
        doc, _ = self._doc()
        self.assertEqual(doc["military"][0]["branch"], "Army",
                         "a repeatable section stores a LIST of postings")


# ═══════════════════════════════════════════════════════════════════════
# 2. Recorded flags
# ═══════════════════════════════════════════════════════════════════════

class RecordedFlagsBlock(_Base):

    def _flag(self, entry, reason, note=""):
        from api.services import suggestion_flags as f
        c = self._con()
        c.execute("BEGIN")
        f.record_flag(c, NARRATOR, entry, reason, source_note=note)
        c.commit(); c.close()

    def test_a_flagged_modern_suggestion_is_refused(self):
        self._stub_schema(None)
        e = self._modern("education.gradeLevel", "took tests and medical exams", sid="sg_ed")
        self._seed_queue([e])
        self._flag(e, "misclassified_section", note="Kent's military induction")
        status, detail = self._http(self._accept, "sg_ed")
        self.assertEqual(status, 422)
        self.assertEqual(detail["reason"], "misclassified_section")
        self.assertIn("source_note", detail)
        self.assertEqual(self._doc(), ({}, 0))

    def test_each_reason_gives_a_different_explanation(self):
        from api.services import suggestion_flags as f
        seen = set()
        for i, reason in enumerate(f.REASONS):
            self._stub_schema(None)
            e = self._modern("education.gradeLevel", f"v{i}", sid=f"sg_{i}")
            self._seed_queue([e])
            self._flag(e, reason)
            status, detail = self._http(self._accept, f"sg_{i}")
            self.assertEqual(status, 422, reason)
            seen.add(detail["detail"])
        self.assertEqual(len(seen), len(f.REASONS),
                         "each reason must explain itself differently")

    def test_identity_by_suggestion_id_survives_a_value_edit(self):
        """A flag found by id still applies when the queued value has
        been edited — the canonical-tuple fallback would miss it."""
        from api.services import suggestion_flags as f
        self._stub_schema(None)
        e = self._modern("education.gradeLevel", "original", sid="sg_id")
        self._seed_queue([e])
        self._flag(e, "value_not_a_field")
        edited = dict(e); edited["value"] = "edited since"
        self._seed_queue([edited])
        c = self._con()
        self.assertIsNotNone(f.flag_for(c, NARRATOR, edited),
                             "the id must find it even though the hash changed")
        c.close()

    def test_identity_by_canonical_tuple_for_legacy_rows(self):
        """The 29 fossils have no id. The documented fallback."""
        from api.services import suggestion_flags as f
        e = self._legacy("residence.period", "mostly")
        self._flag(e, "value_not_a_field")
        c = self._con()
        row = f.flag_for(c, NARRATOR, e)
        c.close()
        self.assertIsNotNone(row)
        self.assertIsNone(row["suggestion_id"], "recorded without an id")

    def test_a_disposed_flag_no_longer_blocks(self):
        from api.services import suggestion_flags as f
        self._stub_schema(None)
        e = self._modern("education.gradeLevel", "v", sid="sg_d")
        self._seed_queue([e])
        self._flag(e, "value_not_a_field")
        c = self._con(); c.execute("BEGIN")
        f.mark_disposed(c, NARRATOR, e, "corrected")
        c.commit(); c.close()
        status, _ = self._http(self._accept, "sg_d")
        self.assertEqual(status, 200)


# ═══════════════════════════════════════════════════════════════════════
# 3. "Accept anyway" is not a shortcut  (requirement 3)
# ═══════════════════════════════════════════════════════════════════════

class ConfirmationIsNotEnough(_Base):

    def setUp(self):
        super().setUp()
        self._stub_schema(None)
        self.entry = self._legacy("military.branch",
                                  "Nike Ajax Nike Hercules missile site",
                                  sid="sg_branch")
        self._seed_queue([self.entry])

    def test_accepting_with_no_correction_is_refused(self):
        status, detail = self._http(self._accept, "sg_branch", entry_id="__new__")
        self.assertEqual(status, 422)
        self.assertIn("corrected_value", detail["remedy"])

    def test_a_correction_identical_to_the_proposal_is_refused(self):
        """The obvious evasion: pass the same value back as a
        'correction'. That is a confirmation wearing a correction's
        clothes."""
        status, detail = self._http(
            self._accept, "sg_branch",
            corrected_value="Nike Ajax Nike Hercules missile site", entry_id="__new__")
        self.assertEqual(status, 422)
        self.assertIn("same as what was proposed", detail["detail"])
        self.assertEqual(self._doc(), ({}, 0))

    def test_a_cosmetic_correction_is_refused(self):
        """Canonical comparison, so whitespace and case do not count as
        a correction either."""
        status, _ = self._http(
            self._accept, "sg_branch",
            corrected_value="  nike ajax   NIKE hercules missile site ", entry_id="__new__")
        self.assertEqual(status, 422)

    def test_a_real_correction_is_accepted_and_records_both_values(self):
        status, out = self._http(self._accept, "sg_branch", entry_id="__new__",
                                 corrected_value="Army",
                                 correction_reason="the proposal named an installation",
                                 reviewed_by="chris")
        self.assertEqual(status, 200)
        doc, _ = self._doc()
        self.assertEqual(doc["military"][0]["branch"], "Army", "the person's value landed")
        r = self._reviews()[0]
        self.assertEqual(r["proposed_value"], "Nike Ajax Nike Hercules missile site",
                         "the ORIGINAL proposal is preserved")
        self.assertEqual(r["corrected_value"], "Army")
        self.assertEqual(r["correction_reason"], "the proposal named an installation")

    def test_a_corrected_acceptance_is_the_persons_entry_not_a_confirmation(self):
        """The person rejected Lori's value and typed their own, so the
        answer is theirs: operator_direct, proposed_by=lori, and NO
        confirmed_via — nothing of Lori's was confirmed."""
        self._http(self._accept, "sg_branch", entry_id="__new__", corrected_value="Army", reviewed_by="chris")
        p = [r for r in self._all_prov() if r["field"]=="branch"][0]
        self.assertEqual(p["origin"], "operator_direct")
        self.assertEqual(p["proposed_by"], "lori")
        self.assertIsNone(p["confirmed_via"])

    def test_the_flag_is_marked_disposed_in_the_same_transaction(self):
        self._http(self._accept, "sg_branch", entry_id="__new__", corrected_value="Army")
        # The structural guard leaves no flag row, so this asserts the
        # recorded-flag path instead.
        from api.services import suggestion_flags as f
        c = self._con(); c.execute("BEGIN")
        e2 = self._modern("military.rank", "v", sid="sg_rank")
        self._seed_queue([e2])
        f.record_flag(c, NARRATOR, e2, "value_not_a_field")
        c.commit(); c.close()
        self._stub_schema(None)
        self._http(self._accept, "sg_rank", entry_id="__new__", corrected_value="Sergeant")
        rows = [r for r in self._flags() if r["field"] == "rank"]
        self.assertEqual(rows[0]["disposition"], "corrected")
        self.assertIsNotNone(rows[0]["disposed_at"])


# ═══════════════════════════════════════════════════════════════════════
# 4. The protection is in the WRITE, not the interface
# ═══════════════════════════════════════════════════════════════════════

class EnforcedServerSide(_Base):

    def test_the_service_refuses_even_when_called_directly(self):
        """Bypassing the route entirely — the UI is not in the path."""
        from api.services import suggestion_review as sr
        from api.services import suggestion_flags as f
        self._stub_schema(None)
        self._seed_queue([self._legacy("military.branch", "missile site", sid="sg_x")])
        with self.assertRaises(f.SuggestionFlagged):
            sr.accept(NARRATOR, "sg_x", entry_id="__new__")
        self.assertEqual(self._doc(), ({}, 0))

    def test_a_flag_recorded_mid_flight_still_blocks(self):
        """The in-transaction re-check. A flag written between the
        pre-check and the locked write must still stop it — otherwise
        two operators reviewing one queue can race a flagged value in."""
        from api.services import suggestion_review as sr
        from api.services import suggestion_flags as f
        self._stub_schema(None)
        e = self._modern("education.gradeLevel", "v", sid="sg_race")
        self._seed_queue([e])

        real = f.requires_correction
        calls = {"n": 0}

        def _clean_then_flagged(con, pid, s):
            calls["n"] += 1
            if calls["n"] <= 1:
                return None                      # pre-check sees nothing
            return f.SuggestionFlagged("value_not_a_field", "flagged mid-flight")

        f.requires_correction = _clean_then_flagged
        try:
            with self.assertRaises(f.SuggestionFlagged):
                sr.accept(NARRATOR, "sg_race")
        finally:
            f.requires_correction = real

        self.assertGreater(calls["n"], 1, "the in-transaction check must have run")
        self.assertEqual(self._doc(), ({}, 0), "questionnaire rolled back")
        self.assertEqual(self._reviews(), [], "review record rolled back")
        self.assertEqual(len(self._queue()), 1, "queue rewrite rolled back")

    def test_decline_is_never_blocked_by_a_flag(self):
        """Refusing a flagged proposal is exactly what should stay easy."""
        from api.routers.projection import ReviewRequest, decline_suggestion_route
        self._stub_schema(None)
        self._seed_queue([self._legacy("military.branch", "missile site", sid="sg_dec")])
        out = decline_suggestion_route("sg_dec", ReviewRequest(person_id=NARRATOR))
        self.assertEqual(out.verdict, "declined")
        self.assertEqual(self._queue(), [])


# ═══════════════════════════════════════════════════════════════════════
# 5. The guarded sections are the ones WO-04 creates
# ═══════════════════════════════════════════════════════════════════════

class GuardScope(unittest.TestCase):

    def test_the_guarded_set_is_exactly_the_new_sections(self):
        from api.services.suggestion_flags import SECTIONS_ADDED_BY_WO04
        self.assertEqual(SECTIONS_ADDED_BY_WO04,
                         {"military", "residence", "travel", "faith"})

    def test_none_of_them_existed_before_this_work(self):
        """If one of these was already a section, the structural guard
        would be blocking proposals that were always acceptable."""
        import subprocess
        js = (REPO / "ui" / "js" / "bio-builder-questionnaire.js").read_text(encoding="utf-8")
        head = js[:js.index("var SECTIONS = [")]
        del head, subprocess
        # Asserted against git history is not possible here; asserted
        # against the reconciliation's measurement instead: these four
        # were the undefined destinations, which is why they are the set.
        from api.services.suggestion_flags import SECTIONS_ADDED_BY_WO04
        for s in SECTIONS_ADDED_BY_WO04:
            self.assertNotIn(f'id: "{s}"', js[:js.index("var SECTIONS = [")],
                             "a section must not be declared before SECTIONS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
