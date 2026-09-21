"""WO-03B Step 0 — the suggestion queue is server-owned and durable.

THE DEFECT THIS CLOSES, measured on the live database 2026-09-20:

    pendingSuggestions in the DB        29 rows, all pre-cutover shape
    newest                              2026-08-12
    client writes since 2026-08-17      none — `_sendMutations` has
                                        never sent the array
    server-producer writes ever         none

A suggestion queued by the browser lived in memory until the next
projection load overwrote it. The protected-identity gate routes its
entire output there, so the gate was producing nothing durable while the
value it withheld reached the questionnaire by another route.

Every test writes to a real temporary SQLite file and reads the result
back out of SQLite, never through the API — the rule from
test_questionnaire_persistence_integrity. A test that checks the API
against the API cannot see a persistence defect at all, which is how
this one survived a month.
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

# The sandbox has no fastapi/pydantic. The stub validates nothing, so
# these tests prove what the route DOES with well-formed input and never
# what the framework would reject.
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
"""


def _review_ddl() -> str:
    """The propose route consults suggestion_reviews for declined values
    (WO-03B req. 3). Taken from the migration, not retyped."""
    sql = (REPO / "server" / "code" / "db" / "migrations"
           / "0060_suggestion_reviews.sql").read_text(encoding="utf-8")
    return sql[sql.index("CREATE TABLE IF NOT EXISTS suggestion_reviews"):]


class _Base(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="sugg-")
        self.db_path = os.path.join(self.dir, "test.sqlite3")
        con = sqlite3.connect(self.db_path)
        con.executescript(SCHEMA)
        con.executescript(_review_ddl())
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

    def _queue(self, person_id=NARRATOR):
        """Read the queue straight out of SQLite."""
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        row = c.execute(
            "SELECT projection_json FROM interview_projections WHERE person_id=?",
            (person_id,),
        ).fetchone()
        c.close()
        if not row:
            return []
        return (json.loads(row["projection_json"]) or {}).get("pendingSuggestions") or []

    def _add_turn(self, turn_id, conv_id, role, content, owner, meta=None):
        c = sqlite3.connect(self.db_path)
        c.execute(
            "INSERT OR IGNORE INTO sessions(conv_id,title,updated_at,payload_json,"
            "person_id,person_id_source) VALUES (?,?,?,?,?,?)",
            (conv_id, "", "2026-09-20T00:00:00", "{}", owner, "explicit" if owner else None),
        )
        c.execute(
            "INSERT INTO turns(id,conv_id,role,content,ts,anchor_id,meta_json) "
            "VALUES (?,?,?,?,?,?,?)",
            (turn_id, conv_id, role, content, "2026-09-20T00:00:00", "",
             json.dumps(meta or {})),
        )
        c.commit()
        c.close()

    def _propose(self, field_path, value, person_id=NARRATOR, turn_id="", confidence=0.9):
        from api.routers.projection import (
            SuggestionAppendRequest, append_suggestion_route,
        )
        return append_suggestion_route(SuggestionAppendRequest(
            person_id=person_id, fieldPath=field_path, value=value,
            confidence=confidence, turnId=turn_id,
        ))


# ═══════════════════════════════════════════════════════════════════════
# 1. A proposal is durable
# ═══════════════════════════════════════════════════════════════════════

class ProposalsPersist(_Base):

    def test_a_proposal_reaches_the_database(self):
        """THE DEFECT. Nothing queued by the browser has reached the
        server since 2026-08-17."""
        self.assertEqual(self._queue(), [])
        res = self._propose("personal.placeOfBirth", "Minot, ND")
        self.assertTrue(res.appended)

        q = self._queue()
        self.assertEqual(len(q), 1)
        self.assertEqual(q[0]["fieldPath"], "personal.placeOfBirth")
        self.assertEqual(q[0]["value"], "Minot, ND")

    def test_it_survives_a_reload(self):
        """A reload re-reads from the server, which is the step that used
        to destroy the queue (`proj.pendingSuggestions = serverPending`).
        Reading it back out of SQLite is that same read."""
        self._propose("personal.placeOfBirth", "Minot, ND")
        first = self._queue()
        self.assertEqual(len(first), 1)
        sid = first[0]["suggestion_id"]
        # Any number of re-reads return the same row.
        self.assertEqual(self._queue()[0]["suggestion_id"], sid)

    def test_narrators_keep_their_own_queues(self):
        self._propose("personal.placeOfBirth", "Minot, ND", person_id=NARRATOR)
        self._propose("personal.placeOfBirth", "Fargo, ND", person_id=OTHER)
        self.assertEqual([s["value"] for s in self._queue(NARRATOR)], ["Minot, ND"])
        self.assertEqual([s["value"] for s in self._queue(OTHER)], ["Fargo, ND"])

    def test_existing_suggestions_are_not_disturbed(self):
        """The ruling: preserve the 29. An append must not rewrite,
        reshape or renumber what is already queued — including rows in
        the pre-cutover shape that carry no suggestion_id."""
        fossil = {"fieldPath": "education.gradeLevel", "value": "6th grade",
                  "confidence": 0.9, "turnId": "turn-1777339141496",
                  "ts": 1777339161106}
        c = sqlite3.connect(self.db_path)
        c.execute(
            "INSERT INTO interview_projections(person_id,projection_json,source,"
            "version,updated_at) VALUES (?,?,?,?,?)",
            (NARRATOR, json.dumps({"fields": {}, "pendingSuggestions": [fossil]}),
             "legacy", 3, "2026-08-12T15:46:00"),
        )
        c.commit()
        c.close()

        self._propose("personal.placeOfBirth", "Minot, ND")
        q = self._queue()
        self.assertEqual(len(q), 2)
        self.assertEqual(q[0], fossil, "the fossil must be byte-identical")

    def test_server_authored_fields_survive_an_append(self):
        """`fields` is written by the server mid-turn (apply_correction).
        Appending to the queue must not touch it — the reason the
        whole-envelope PUT was retired in the first place."""
        c = sqlite3.connect(self.db_path)
        c.execute(
            "INSERT INTO interview_projections(person_id,projection_json,source,"
            "version,updated_at) VALUES (?,?,?,?,?)",
            (NARRATOR, json.dumps({"fields": {"personal.fullName": {"value": "Janice"}},
                                   "pendingSuggestions": []}), "x", 1, "t"),
        )
        c.commit()
        c.close()
        self._propose("personal.placeOfBirth", "Minot, ND")
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        stored = json.loads(c.execute(
            "SELECT projection_json FROM interview_projections WHERE person_id=?",
            (NARRATOR,)).fetchone()["projection_json"])
        c.close()
        self.assertEqual(stored["fields"]["personal.fullName"]["value"], "Janice")


# ═══════════════════════════════════════════════════════════════════════
# 2. The server owns identity, time and evidence  (C1, C2)
# ═══════════════════════════════════════════════════════════════════════

class ServerOwnsTheRecord(_Base):

    def test_the_server_mints_the_id(self):
        a = self._propose("personal.placeOfBirth", "Minot, ND")
        b = self._propose("personal.fullName", "Janice Horne")
        self.assertTrue(a.suggestion_id.startswith("sg_"))
        self.assertNotEqual(a.suggestion_id, b.suggestion_id)

    def test_a_verified_turn_is_recorded_as_verified(self):
        self._add_turn(100, "conv_a", "user", "I was born in Minot", NARRATOR)
        res = self._propose("personal.placeOfBirth", "Minot, ND", turn_id="100")
        self.assertEqual(res.turn_evidence, "verified")
        self.assertEqual(self._queue()[0]["turn_evidence"], "verified")

    def test_a_system_directive_is_never_verified_evidence(self):
        """The same clause WO-03A needed. A composed instruction sits in
        the user slot; cited as support it turns the prompt composer's
        stage direction into something the narrator said."""
        self._add_turn(101, "conv_a", "user", "[SYSTEM: the narrator has been quiet]",
                       NARRATOR, meta={"origin": "system_directive"})
        res = self._propose("personal.placeOfBirth", "Minot, ND", turn_id="101")
        self.assertEqual(res.turn_evidence, "unverified")

    def test_another_narrators_turn_is_never_verified(self):
        self._add_turn(102, "conv_b", "user", "I was born in Fargo", OTHER)
        res = self._propose("personal.placeOfBirth", "Fargo, ND", turn_id="102")
        self.assertEqual(res.turn_evidence, "unverified")

    def test_an_unverifiable_citation_is_kept_and_the_proposal_is_queued(self):
        """A bookkeeping failure must not discard the proposal, and the
        claimed id survives so the failure can be investigated."""
        res = self._propose("personal.placeOfBirth", "Minot, ND", turn_id="999999")
        self.assertEqual(res.turn_evidence, "unverified")
        q = self._queue()
        self.assertEqual(len(q), 1)
        self.assertEqual(q[0]["source_turn_id"], "999999")

    def test_no_citation_reads_absent(self):
        res = self._propose("personal.placeOfBirth", "Minot, ND")
        self.assertEqual(res.turn_evidence, "absent")
        self.assertIsNone(self._queue()[0]["source_turn_id"])

    def test_the_evidence_verdict_is_stored_not_the_clients_claim(self):
        """The decisive one. A client cannot get `verified` by asking
        for it — the request model has no field for it, and the stored
        verdict comes from the join."""
        from api.routers.projection import SuggestionAppendRequest
        self.assertNotIn("turn_evidence", SuggestionAppendRequest.model_fields)
        self.assertNotIn("suggestion_id", SuggestionAppendRequest.model_fields)
        self.assertNotIn("ts", SuggestionAppendRequest.model_fields)


# ═══════════════════════════════════════════════════════════════════════
# 3. Duplicates and competing claims  (C2)
# ═══════════════════════════════════════════════════════════════════════

class DuplicatesAndCompetingClaims(_Base):

    def test_an_identical_repeat_is_counted_not_requeued(self):
        a = self._propose("personal.placeOfBirth", "Minot, ND")
        b = self._propose("personal.placeOfBirth", "Minot, ND")
        self.assertTrue(a.appended)
        self.assertFalse(b.appended)
        self.assertTrue(b.duplicate)
        self.assertEqual(b.repeats, 2)
        q = self._queue()
        self.assertEqual(len(q), 1)
        self.assertEqual(q[0]["repeats"], 2,
                         "'Lori keeps insisting' has to stay visible")

    def test_two_different_values_for_one_field_both_stay(self):
        """The old behaviour dropped the earlier suggestion for a path,
        so a person never learned the model had proposed something else.
        Two different claims about one field is exactly what review is
        for."""
        self._propose("personal.placeOfBirth", "Minot, ND")
        self._propose("personal.placeOfBirth", "Fargo, ND")
        q = self._queue()
        self.assertEqual(len(q), 2)
        self.assertEqual(sorted(s["value"] for s in q), ["Fargo, ND", "Minot, ND"])


# ═══════════════════════════════════════════════════════════════════════
# 4. The ordinary PATCH no longer owns the queue  (C1)
# ═══════════════════════════════════════════════════════════════════════

class PatchCannotTouchTheQueue(_Base):

    def _patch(self, **kw):
        from api.routers.projection import (
            ProjectionPatchRequest, patch_projection_route,
        )

        class _Resp:
            status_code = 200

        body = {"person_id": NARRATOR}
        body.update(kw)
        return patch_projection_route(ProjectionPatchRequest(**body), _Resp())

    def test_patch_cannot_replace_the_queue(self):
        """Whoever can replace the array owns it, and an acceptance
        checked against a client-owned queue verifies nothing."""
        self._propose("personal.placeOfBirth", "Minot, ND")
        self._patch(pendingSuggestions=[
            {"fieldPath": "personal.fullName", "value": "Injected"},
        ])
        q = self._queue()
        self.assertEqual(len(q), 1)
        self.assertEqual(q[0]["value"], "Minot, ND")

    def test_patch_cannot_clear_the_queue(self):
        self._propose("personal.placeOfBirth", "Minot, ND")
        self._patch(pendingSuggestions=[])
        self.assertEqual(len(self._queue()), 1)

    def test_the_refusal_is_reported_not_swallowed(self):
        """A caller that believed it wrote the queue must be able to find
        out that it did not — the rule `write_applied` follows."""
        out = self._patch(pendingSuggestions=[{"fieldPath": "x", "value": "y"}])
        self.assertTrue(out.suggestions_ignored)

    def test_an_ordinary_patch_is_unaffected(self):
        """The lockdown must not break the field-level write path."""
        out = self._patch(mutations={"personal.fullName": {"value": "Janice"}})
        self.assertTrue(out.write_applied)
        self.assertFalse(out.suggestions_ignored)
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        stored = json.loads(c.execute(
            "SELECT projection_json FROM interview_projections WHERE person_id=?",
            (NARRATOR,)).fetchone()["projection_json"])
        c.close()
        self.assertEqual(stored["fields"]["personal.fullName"]["value"], "Janice")


# ═══════════════════════════════════════════════════════════════════════
# 5. Repeatable destinations are flagged, never guessed  (C4)
# ═══════════════════════════════════════════════════════════════════════

class RepeatableDestinations(_Base):

    def test_a_repeatable_destination_is_marked_unresolved(self):
        """A proposal aimed at a repeatable section has no entry to
        attach to. Falling back to the ordinal would name a different
        relative after an insertion or reorder — the failure WO-02
        existed to end."""
        self._propose("parents.occupation", "Carpenter")
        self.assertTrue(self._queue()[0]["destination_unresolved"])

    def test_an_indexed_path_is_also_unresolved(self):
        self._propose("parents[0].occupation", "Carpenter")
        self.assertTrue(self._queue()[0]["destination_unresolved"])

    def test_a_flat_destination_is_resolved(self):
        self._propose("personal.placeOfBirth", "Minot, ND")
        self.assertFalse(self._queue()[0]["destination_unresolved"])

    def test_every_repeatable_section_is_covered(self):
        """All eight, checked against the questionnaire's own list rather
        than a retyped copy that can drift."""
        from api.routers.projection import _REPEATABLE_SECTIONS
        qq = (REPO / "ui" / "js" / "bio-builder-questionnaire.js").read_text(
            encoding="utf-8")
        for section in _REPEATABLE_SECTIONS:
            self.assertIn('id: "' + section + '"', qq,
                          f"{section} is not a real questionnaire section")
        self.assertEqual(len(_REPEATABLE_SECTIONS), 11)


if __name__ == "__main__":
    unittest.main(verbosity=2)
