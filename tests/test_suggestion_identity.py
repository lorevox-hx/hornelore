"""Identity for the pre-cutover queue entries. WO-04 addendum.

The live queue has NO duplicate proposals — verified: no repeated
(narrator, fieldPath, value), and no narrator with the same fieldPath
twice. So the live data cannot exercise the case that matters most.

That is exactly why these exist. Identity must not depend on the queue
staying free of duplicates, because `_write_queue_without` removes EVERY
entry matching an id:

    env["pendingSuggestions"] = [
        s for s in pending
        if not (isinstance(s, dict) and s.get("suggestion_id") == suggestion_id)
    ]

so two entries sharing an id means one decline silently deletes two
proposals — and the person is never told.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "tests"))

from fastapi_stub import install as _install_stub  # noqa: E402
_install_stub()

import backfill_suggestion_ids as bf  # noqa: E402

PID = "p-kent"
OTHER = "p-chris"


def _fossil(path, value, ts=1777339161106, turn="turn-1777339141496"):
    """The exact five-key shape every pre-cutover entry has."""
    return {"fieldPath": path, "value": value, "confidence": 0.9,
            "turnId": turn, "ts": ts}


class DerivedIdentity(unittest.TestCase):

    def test_two_identical_proposals_get_different_ids(self):
        """THE CASE THE LIVE DATA CANNOT SHOW.

        Someone queued the same thing twice. They are two proposals, not
        one, and a person declining the first must not lose the second.
        """
        e = _fossil("military.rank", "Sergeant")
        a = bf.derive_id(PID, 3, dict(e))
        b = bf.derive_id(PID, 7, dict(e))
        self.assertNotEqual(a, b, "position is part of identity")

    def test_hashing_content_alone_would_have_collapsed_them(self):
        """Names what the index is buying. If this ever passes without
        the index, the guarantee above is gone."""
        e = _fossil("military.rank", "Sergeant")
        same_index = (bf.derive_id(PID, 3, dict(e)), bf.derive_id(PID, 3, dict(e)))
        self.assertEqual(*same_index, "same position, same entry -> same id")

    def test_the_same_entry_derives_the_same_id_every_time(self):
        e = _fossil("education.schooling", "high school")
        self.assertEqual(bf.derive_id(PID, 0, e), bf.derive_id(PID, 0, dict(e)))

    def test_two_narrators_with_the_same_entry_get_different_ids(self):
        e = _fossil("education.schooling", "high school")
        self.assertNotEqual(bf.derive_id(PID, 0, e), bf.derive_id(OTHER, 0, e))

    def test_the_value_and_timestamp_both_matter(self):
        base = _fossil("personal.fullName", "A")
        self.assertNotEqual(bf.derive_id(PID, 0, base),
                            bf.derive_id(PID, 0, _fossil("personal.fullName", "B")))
        self.assertNotEqual(bf.derive_id(PID, 0, base),
                            bf.derive_id(PID, 0, _fossil("personal.fullName", "A", ts=1)))

    def test_it_is_shaped_exactly_like_a_minted_id(self):
        """`sg_` + 16 hex, same as `routers/projection.py`:

            sid = "sg_" + uuid.uuid4().hex[:16]

        Nothing downstream should be able to tell a backfilled id from a
        minted one — a two-class identity invites code that branches on
        which kind it is.
        """
        sid = bf.derive_id(PID, 0, _fossil("personal.fullName", "A"))
        self.assertRegex(sid, r"^sg_[0-9a-f]{16}$")

    def test_a_none_value_does_not_crash_or_collide_with_empty_string(self):
        a = bf.derive_id(PID, 0, {"fieldPath": "x.y", "value": None, "ts": 1})
        b = bf.derive_id(PID, 0, {"fieldPath": "x.y", "value": "", "ts": 1})
        self.assertRegex(a, r"^sg_[0-9a-f]{16}$")
        self.assertEqual(a, b, "None and '' are the same absent value here, "
                               "and the tuple still distinguishes by position")

    def test_the_separator_cannot_be_forged_from_a_value(self):
        """A field separator a value can contain lets two different
        tuples hash the same. \\x1f is not typeable into a form."""
        self.assertNotEqual(
            bf.derive_id(PID, 0, _fossil("a.b", "x")),
            bf.derive_id(PID, 0, _fossil("a", "b\x1fx")))


class _DbCase(unittest.TestCase):

    def setUp(self):
        from api import db as _db
        sys.path.insert(0, str(REPO / "tests"))
        from test_suggestion_flags import SCHEMA, _ddl  # reuse the built schema
        self.dir = tempfile.mkdtemp(prefix="ident-")
        self.db = os.path.join(self.dir, "t.sqlite3")
        con = sqlite3.connect(self.db)
        con.executescript(SCHEMA)
        con.executescript(_ddl("0059_answer_provenance.sql",
                               "CREATE TABLE IF NOT EXISTS bio_builder_answer_provenance",
                               ["ALTER TABLE"]))
        con.executescript(_ddl("0060_suggestion_reviews.sql",
                               "CREATE TABLE IF NOT EXISTS suggestion_reviews"))
        con.executescript("ALTER TABLE suggestion_reviews ADD COLUMN corrected_value TEXT;")
        con.executescript("ALTER TABLE suggestion_reviews ADD COLUMN correction_reason TEXT;")
        con.executescript("ALTER TABLE suggestion_reviews ADD COLUMN accept_mode TEXT;")
        con.executescript(_ddl("0061_suggestion_flags.sql",
                               "CREATE TABLE IF NOT EXISTS suggestion_flags",
                               ["ALTER TABLE"]))
        for pid, nm in ((PID, "Kent"), (OTHER, "Chris")):
            con.execute("INSERT INTO people (id, display_name) VALUES (?,?)", (pid, nm))
        con.commit(); con.close()

        self._real = _db._connect, _db.init_db

        def _c():
            c = sqlite3.connect(self.db); c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys=ON"); return c

        _db._connect = _c
        _db.init_db = lambda *a, **k: None
        bf.DB = self.db

    def tearDown(self):
        from api import db as _db
        _db._connect, _db.init_db = self._real

    def _con(self):
        c = sqlite3.connect(self.db); c.row_factory = sqlite3.Row; return c

    def _seed(self, pid, entries):
        c = self._con()
        c.execute("INSERT OR REPLACE INTO interview_projections"
                  "(person_id,projection_json,source,version,updated_at) VALUES (?,?,?,?,?)",
                  (pid, json.dumps({"fields": {}, "pendingSuggestions": entries}),
                   "seed", 1, "t"))
        c.commit(); c.close()

    def _queue(self, pid):
        c = self._con()
        r = c.execute("SELECT projection_json FROM interview_projections WHERE person_id=?",
                      (pid,)).fetchone()
        c.close()
        return (json.loads(r["projection_json"]) or {}).get("pendingSuggestions") or []

    def _run(self):
        c = self._con()
        plan = bf._plan(c)
        bf._apply(c, plan, "test")
        ok = True
        c.close()
        return plan


class TheOperation(_DbCase):

    def test_duplicate_entries_both_get_ids_and_they_differ(self):
        e = _fossil("military.rank", "Sergeant")
        self._seed(PID, [dict(e), dict(e)])
        self._run()
        q = self._queue(PID)
        self.assertEqual(len(q), 2, "both entries survive")
        self.assertNotEqual(q[0]["suggestion_id"], q[1]["suggestion_id"])
        self.assertEqual(q[0]["value"], q[1]["value"], "still the same proposal, twice")

    def test_declining_one_duplicate_leaves_the_other(self):
        """The consequence, end to end. This is what a shared id would
        have broken, and the breakage would have been silent."""
        from api.services import suggestion_review as sr
        e = _fossil("education.schooling", "high school")
        self._seed(PID, [dict(e), dict(e)])
        self._run()
        first = self._queue(PID)[0]["suggestion_id"]
        sr.decline(PID, first)
        left = self._queue(PID)
        self.assertEqual(len(left), 1, "exactly one proposal was declined")
        self.assertNotEqual(left[0]["suggestion_id"], first)

    def test_destination_undefined_is_never_written(self):
        """The sharpest edge. `_is_unchecked_legacy` is

            return "destination_undefined" not in suggestion

        so writing that key would delete the legacy guard for every row
        it touched."""
        self._seed(PID, [_fossil("personal.fullName", "kind of scared")])
        self._run()
        self.assertNotIn("destination_undefined", self._queue(PID)[0])

    def test_the_entry_still_reads_as_legacy_afterwards(self):
        from api.services import suggestion_flags as f
        self._seed(PID, [_fossil("personal.fullName", "kind of scared")])
        self._run()
        s = self._queue(PID)[0]
        self.assertTrue(f._is_unchecked_legacy(s))
        c = self._con()
        req = f.requires_review(c, PID, s)
        c.close()
        self.assertIsNotNone(req, "it is addressable AND still requires review")
        self.assertEqual(req.requirement, f.REQUIRE_ACKNOWLEDGE)

    def test_the_five_original_keys_are_untouched(self):
        e = _fossil("education.schooling", "high school")
        self._seed(PID, [dict(e)])
        self._run()
        got = self._queue(PID)[0]
        for k, v in e.items():
            self.assertEqual(got[k], v, f"{k} was altered")

    def test_array_order_is_preserved(self):
        """`prompt_composer` builds `suggested[fieldPath] = value` in
        array order, so last-wins. Reordering changes what Lori offers."""
        paths = ["a.b", "c.d", "e.f", "g.h"]
        self._seed(PID, [_fossil(p, p.upper(), ts=i) for i, p in enumerate(paths)])
        self._run()
        self.assertEqual([s["fieldPath"] for s in self._queue(PID)], paths)

    def test_repeatable_sections_get_destination_unresolved(self):
        """Without it the review surface stops drawing the entry picker
        and the operator hits a 422 with no control to answer it."""
        self._seed(PID, [_fossil("military.branch", "Army"),
                         _fossil("education.schooling", "high school")])
        self._run()
        q = {s["fieldPath"]: s for s in self._queue(PID)}
        self.assertIs(q["military.branch"]["destination_unresolved"], True)
        self.assertNotIn("destination_unresolved", q["education.schooling"],
                         "a flat section is not made unresolved")

    def test_turn_evidence_is_the_verdict_verify_turn_actually_returned(self):
        """The surface reads `s.turn_evidence || (sid ? 'absent' : 'pre-cutover')`.

        Leaving the key absent would make every backfilled row claim "No
        conversation was cited. This is something Lori worked out" —
        false, since all 29 cite one. Hardcoding "absent" would make the
        same false claim while looking like a measurement.

        So this asserts the recorded value IS what `verify_turn`
        returned, for each of the three verdicts. An earlier version
        only checked the value was in the vocabulary, which "absent"
        satisfies — a mutation that hardcoded it survived.
        """
        import api.services.answer_provenance as ap
        real = ap.verify_turn
        try:
            for verdict in ("verified", "unverified", "absent"):
                ap.verify_turn = lambda con, pid, tid, _v=verdict: _v
                self._seed(PID, [_fossil("education.schooling", "high school")])
                self._run()
                self.assertEqual(self._queue(PID)[0]["turn_evidence"], verdict,
                                 f"recorded something other than the {verdict} verdict")
        finally:
            ap.verify_turn = real

    def test_a_turn_evidence_already_present_is_not_overwritten(self):
        e = dict(_fossil("education.schooling", "x"), turn_evidence="verified")
        self._seed(PID, [e])
        self._run()
        self.assertEqual(self._queue(PID)[0]["turn_evidence"], "verified")

    def test_an_entry_that_already_has_an_id_is_left_alone(self):
        keep = dict(_fossil("education.schooling", "x"), suggestion_id="sg_already")
        self._seed(PID, [keep])
        plan = self._run()
        self.assertEqual(plan, [], "nothing planned")
        self.assertEqual(self._queue(PID)[0]["suggestion_id"], "sg_already")

    def test_running_twice_is_a_no_op(self):
        self._seed(PID, [_fossil("a.b", "v1"), _fossil("c.d", "v2")])
        self._run()
        first = json.dumps(self._queue(PID), sort_keys=True)
        self.assertEqual(self._run(), [], "second run plans nothing")
        self.assertEqual(json.dumps(self._queue(PID), sort_keys=True), first)

    def test_a_collision_refuses_the_whole_operation(self):
        """Including against an id recorded in another table. One
        collision must stop everything, not skip one row."""
        e = _fossil("education.schooling", "high school")
        clash = bf.derive_id(PID, 0, e)
        self._seed(PID, [dict(e), _fossil("a.b", "other")])
        c = self._con()
        c.execute("INSERT INTO suggestion_flags (person_id,section,entry_id,field,"
                  "value_hash,suggestion_id,field_path,proposed_value,reason,flagged_at) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (PID, "zz", "", "zz", "hash-x", clash, "zz.zz", "v",
                   "queued_before_home", "t"))
        c.commit()
        with self.assertRaises(SystemExit):
            bf._plan(c)
        c.close()
        self.assertNotIn("suggestion_id", self._queue(PID)[0], "nothing was written")

    def test_ids_are_unique_across_narrators(self):
        e = _fossil("education.schooling", "high school")
        self._seed(PID, [dict(e)])
        self._seed(OTHER, [dict(e)])
        self._run()
        self.assertNotEqual(self._queue(PID)[0]["suggestion_id"],
                            self._queue(OTHER)[0]["suggestion_id"])

    def test_the_version_is_bumped_so_a_stale_client_conflicts(self):
        self._seed(PID, [_fossil("a.b", "v")])
        c = self._con()
        before = c.execute("SELECT version FROM interview_projections WHERE person_id=?",
                           (PID,)).fetchone()[0]
        c.close()
        self._run()
        c = self._con()
        after = c.execute("SELECT version FROM interview_projections WHERE person_id=?",
                          (PID,)).fetchone()[0]
        c.close()
        self.assertGreater(after, before)

    def test_no_questionnaire_answer_or_review_is_written(self):
        self._seed(PID, [_fossil("education.schooling", "high school")])
        self._run()
        c = self._con()
        self.assertEqual(
            c.execute("SELECT COUNT(*) FROM bio_builder_questionnaires").fetchone()[0], 0)
        self.assertEqual(
            c.execute("SELECT COUNT(*) FROM suggestion_reviews").fetchone()[0], 0)
        self.assertEqual(
            c.execute("SELECT COUNT(*) FROM bio_builder_answer_provenance").fetchone()[0], 0)
        c.close()


class TheOtherProducer(_DbCase):
    """`projection_writer.apply_correction`, the second source of id-less
    entries — and the one that was still running.

    A one-time backfill repairs the thirty fossils. It does nothing about
    a producer that makes another one the same afternoon, and every
    entry this path made was permanently stuck: `find_suggestion` matches
    on the id, so a deferred correction could be neither accepted nor
    declined, only accumulated.
    """

    def _operator_field(self, path, value):
        """A field the operator typed, which the model must not overwrite."""
        c = self._con()
        c.execute("INSERT OR REPLACE INTO interview_projections"
                  "(person_id,projection_json,source,version,updated_at) VALUES (?,?,?,?,?)",
                  (PID, json.dumps({
                      "fields": {path: {"value": value, "locked": True,
                                        "source": "human_edit"}},
                      "pendingSuggestions": []}), "seed", 1, "t"))
        c.commit(); c.close()

    # `apply_correction` takes PARSER keys and maps them to projection
    # paths through `_PARSER_TO_PROJECTION`. Five keys map; anything else
    # is skipped as `no_canonical_mapping`, which is how the first draft
    # of these tests silently exercised nothing at all.
    PARSER = {
        "personal.placeOfBirth":     "identity.place_of_birth",      # flat, defined
        "parents.father.firstName":  "family.parents.father.name",   # REPEATABLE
        "community.retirementStatus": "education_work.retirement",   # NOT defined
    }

    def _defer(self, path, old, new, turn="turn-9"):
        from api.services import projection_writer as pw
        self._operator_field(path, old)
        out = pw.apply_correction(PID, {self.PARSER[path]: new}, source_turn_id=turn)
        self.assertFalse(out.get("skipped"),
                         f"the parser key for {path} did not map: {out.get('skipped')}")
        return out, self._queue(PID)

    def test_a_deferred_correction_is_still_not_applied(self):
        """The protection this path exists for, unchanged. Assert it
        FIRST — everything else here is worthless if the repair loosened
        the thing it was repairing."""
        out, q = self._defer("personal.placeOfBirth", "Williston", "Bismarck")
        c = self._con()
        r = c.execute("SELECT projection_json FROM interview_projections WHERE person_id=?",
                      (PID,)).fetchone()
        c.close()
        fields = (json.loads(r["projection_json"]) or {}).get("fields") or {}
        self.assertEqual(fields["personal.placeOfBirth"]["value"], "Williston",
                         "the operator's value was overwritten")
        self.assertTrue(fields["personal.placeOfBirth"].get("locked"), "lock survived")
        self.assertEqual(len(out.get("deferred") or []), 1, "reported as deferred")
        self.assertEqual(len(q), 1, "and queued for a person to decide")

    def test_the_deferred_suggestion_now_has_an_id(self):
        _out, q = self._defer("personal.placeOfBirth", "Williston", "Bismarck")
        self.assertRegex(q[0].get("suggestion_id") or "", r"^sg_[0-9a-f]{16}$")

    def test_it_is_reachable_and_declinable(self):
        """The whole point. Before the repair this raised
        SuggestionNotFound and the entry could never leave the queue."""
        from api.services import suggestion_review as sr
        _out, q = self._defer("personal.placeOfBirth", "Williston", "Bismarck")
        sid = q[0]["suggestion_id"]
        c = self._con()
        self.assertIsNotNone(sr.find_suggestion(c, PID, sid))
        c.close()
        sr.decline(PID, sid)
        self.assertEqual(self._queue(PID), [], "it could actually be refused")

    def test_it_is_not_labelled_legacy(self):
        """`_is_unchecked_legacy` keys on the ABSENCE of
        `destination_undefined`. A proposal created today by code that
        checks destinations must not read as predating that code."""
        from api.services import suggestion_flags as f
        _out, q = self._defer("personal.placeOfBirth", "Williston", "Bismarck")
        self.assertIn("destination_undefined", q[0])
        self.assertFalse(f._is_unchecked_legacy(q[0]))

    def test_the_destination_is_actually_checked(self):
        _out, q = self._defer("personal.placeOfBirth", "Williston", "Bismarck")
        self.assertIs(q[0]["destination_undefined"], False, "a real field")
        _out2, q2 = self._defer("community.retirementStatus", "x", "y")
        self.assertIs(q2[0]["destination_undefined"], True,
                      "community.retirementStatus is not a questionnaire field; "
                      "saying otherwise would let a value land where no form "
                      "can show it")

    def test_a_repeatable_destination_gets_unresolved(self):
        _out, q = self._defer("parents.father.firstName", "John", "Jonathan")
        self.assertIs(q[0].get("destination_unresolved"), True)

    def test_turn_evidence_is_measured_here_too(self):
        _out, q = self._defer("personal.placeOfBirth", "Williston", "Bismarck")
        self.assertIn(q[0].get("turn_evidence"), ("verified", "unverified", "absent"))
        self.assertNotEqual(q[0].get("turn_evidence"), "verified",
                            "turn-9 does not resolve to this narrator")

    def test_an_unreadable_schema_fails_CLOSED(self):
        """If we cannot check the destination we must not claim it is
        fine. `False` would be the one answer that is definitely wrong."""
        from api.services import projection_writer as pw
        from api.services import questionnaire_schema as qs
        real = qs.is_defined
        qs.is_defined = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("unreadable"))
        try:
            _out, q = self._defer("personal.placeOfBirth", "Williston", "Bismarck")
        finally:
            qs.is_defined = real
        self.assertIs(q[0]["destination_undefined"], True)

    def test_superseding_an_earlier_proposal_is_logged_not_silent(self):
        """Newest-wins is the existing semantics and is left alone. But a
        superseded entry may carry a flag, a decline history, or an id a
        person has already seen."""
        import logging
        self._operator_field("personal.placeOfBirth", "Williston")
        from api.services import projection_writer as pw
        pw.apply_correction(PID, {"identity.place_of_birth": "Bismarck"}, source_turn_id="t1")
        first = self._queue(PID)[0]["suggestion_id"]
        with self.assertLogs("api.services.projection_writer", level="INFO") as cm:
            pw.apply_correction(PID, {"identity.place_of_birth": "Fargo"}, source_turn_id="t2")
        q = self._queue(PID)
        self.assertEqual(len(q), 1, "newest wins, as before")
        self.assertNotEqual(q[0]["suggestion_id"], first)
        self.assertTrue(any("superseded" in m and first in m for m in cm.output),
                        "the dropped id must appear in the log")


class NoProducerCanMakeAnIdlessEntry(_DbCase):
    """The durable guarantee, stated once.

    There are exactly two things that put an entry in the queue. This
    asserts the property they must share, so a third producer added later
    fails here rather than quietly rebuilding the problem.
    """

    def test_both_producers_mint_an_id(self):
        from api.services import projection_writer as pw

        # Producer 1: the append route's entry shape.
        e1 = pw._server_owned_suggestion("personal.fullName", "A Name", "t",
                                         person_id=PID, source_turn_id=None)
        # Producer 2: the deferred-correction path, end to end.
        c = self._con()
        c.execute("INSERT OR REPLACE INTO interview_projections"
                  "(person_id,projection_json,source,version,updated_at) VALUES (?,?,?,?,?)",
                  (PID, json.dumps({"fields": {"personal.placeOfBirth": {
                      "value": "Williston", "locked": True, "source": "human_edit"}},
                      "pendingSuggestions": []}), "seed", 1, "t"))
        c.commit(); c.close()
        pw.apply_correction(PID, {"identity.place_of_birth": "Bismarck"},
                            source_turn_id="turn-9")
        e2 = self._queue(PID)[0]

        for name, e in (("_server_owned_suggestion", e1), ("apply_correction", e2)):
            with self.subTest(producer=name):
                self.assertRegex(e.get("suggestion_id") or "", r"^sg_[0-9a-f]{16}$")
                self.assertIn("destination_undefined", e,
                              "must not read as legacy — it was checked today")
                self.assertIn("turn_evidence", e)

    def test_the_route_and_the_writer_agree_on_the_id_shape(self):
        """Both are `sg_` + 16 hex. A two-class identity invites code
        that branches on which kind it is looking at."""
        src = (REPO / "server" / "code" / "api" / "routers" / "projection.py").read_text(
            encoding="utf-8")
        self.assertIn('sid = "sg_" + uuid.uuid4().hex[:16]', src)
        from api.services import projection_writer as pw
        e = pw._server_owned_suggestion("a.b", "v", "t")
        self.assertRegex(e["suggestion_id"], r"^sg_[0-9a-f]{16}$")


if __name__ == "__main__":
    unittest.main(verbosity=2)
