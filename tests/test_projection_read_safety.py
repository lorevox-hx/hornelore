"""An unreviewed suggestion is not a fact, and a model may not overrule a person.

BUG-LORI-SUGGESTION-READS-AS-FACT-01
BUG-PROJECTION-CORRECTION-OVERRIDES-OPERATOR-01

WHAT WAS WRONG

  `pendingSuggestions` is the queue for UNTRUSTED writes to protected identity
  paths. projection-sync.js:238-247 diverts a model-inferred value there
  INSTEAD of writing it to the record, precisely so a guess does not become
  biography before a person confirms it.

  Two independent readers then flattened that queue into the same namespace as
  operator-typed values:

      prompt_composer.py:1150-1159    setdefault into `provisional`
      profile_seed.py:592-599         setdefault into the topic value map

  So a model's unconfirmed guess about a narrator's birthplace reached Lori's
  prompt indistinguishable from something the operator typed, and Lori would
  state it back to the narrator as something she knew about them. The second
  reader decides which interview topics count as answered, so a guess could
  also stop her ever asking.

  Separately, `projection_writer.apply_correction` assigned a fresh field dict
  over whatever was there — no `history`, no `locked`. A model-detected
  correction could overwrite a value the operator had typed from a document,
  and erase the audit trail on the way past.

WHAT THESE TESTS ASSERT

  Behaviour, by calling the real functions. Not source patterns.

Run:  python3 -m pytest tests/test_projection_read_safety.py -q
      (or: python3 tests/test_projection_read_safety.py)
"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "server" / "code"))

PID = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


def _field(value, source, locked=False, history=None, **extra):
    e = {"value": value, "source": source, "locked": locked,
         "confidence": 1.0 if source == "human_edit" else 0.6,
         "turnId": None, "ts": 1757000000000, "history": history or []}
    e.update(extra)
    return e


class ProvenanceTierTests(unittest.TestCase):
    """The tier vocabulary from WO-BIOGRAPHY-READ-CONTRACT-01."""

    def setUp(self):
        from code.api import prompt_composer
        self.pc = prompt_composer

    def test_operator_entry_is_the_top_tier(self):
        p = self.pc._projection_provenance(_field("Superior", "human_edit", locked=True))
        self.assertEqual(p["tier"], "operator_entered")
        self.assertEqual(p["tier_rank"], 1)
        self.assertTrue(p["locked"])

    def test_narrator_statement_outranks_a_model_guess(self):
        said = self.pc._projection_provenance(_field("Superior", "interview"))
        guessed = self.pc._projection_provenance(_field("Duluth", "backend_extract"))
        self.assertLess(said["tier_rank"], guessed["tier_rank"])
        self.assertEqual(said["tier"], "narrator_stated")
        self.assertEqual(guessed["tier"], "model_inferred")

    def test_an_unknown_source_is_not_trusted(self):
        """`source` is client-asserted; the server stores it opaquely
        (db.py:7074). An unrecognised value is not evidence of authority."""
        p = self.pc._projection_provenance(_field("Superior", "something_invented"))
        self.assertEqual(p["tier"], "model_inferred")
        self.assertGreater(p["tier_rank"], 1)

    def test_seeded_values_never_outrank_their_own_source(self):
        p = self.pc._projection_provenance(_field("Superior", "profile_hydrate"))
        self.assertEqual(p["tier"], "seeded")
        self.assertEqual(p["tier_rank"], 5)


class SuggestionIsNotAFactTests(unittest.TestCase):
    """The prompt composer's read boundary."""

    def setUp(self):
        from code.api import prompt_composer
        self.pc = prompt_composer
        self._real_get_projection = None

    def _seed_projection(self, fields, suggestions):
        """Patch db.get_projection for the duration of one test."""
        from code.api import db as _db
        self._real_get_projection = _db.get_projection
        blob = {"projection": {"fields": fields, "pendingSuggestions": suggestions}}
        _db.get_projection = lambda pid: blob if pid == PID else {}

    def tearDown(self):
        if self._real_get_projection is not None:
            from code.api import db as _db
            _db.get_projection = self._real_get_projection

    def test_a_pending_suggestion_does_not_reach_the_seed(self):
        """THE DEFECT. A model guessed the narrator's birthplace. Nobody
        confirmed it. It must not arrive as something Lori knows."""
        self._seed_projection(
            fields={"personal.fullName": _field("Thorvald Lindqvist", "human_edit", locked=True)},
            suggestions=[{"fieldPath": "personal.placeOfBirth",
                          "value": "Duluth, Minnesota", "confidence": 0.7}],
        )
        seed = self.pc._build_profile_seed(PID)
        blob = json.dumps(seed)
        self.assertNotIn("Duluth", blob,
                         "an unreviewed model suggestion reached the profile seed")

    def test_a_committed_operator_field_still_reaches_the_seed(self):
        """The fix must not silence real answers."""
        self._seed_projection(
            fields={"personal.fullName": _field("Thorvald Lindqvist", "human_edit", locked=True)},
            suggestions=[],
        )
        seed = self.pc._build_profile_seed(PID)
        self.assertIn("Thorvald", json.dumps(seed))

    def test_a_suggestion_cannot_fill_a_gap_left_by_a_field(self):
        """The old code used setdefault, so a suggestion filled any path no
        committed field had claimed. That is the exact path a guess took."""
        self._seed_projection(
            fields={},
            suggestions=[{"fieldPath": "personal.fullName", "value": "Ingeborg Falk"}],
        )
        seed = self.pc._build_profile_seed(PID)
        self.assertNotIn("Ingeborg", json.dumps(seed))


class TopicAnsweredTests(unittest.TestCase):
    """The second reader — profile_seed._load_projection_values."""

    def test_suggestions_do_not_mark_a_topic_answered(self):
        from code.api.services import profile_seed as ps
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE interview_projections "
                    "(person_id TEXT PRIMARY KEY, projection_json TEXT)")
        con.execute(
            "INSERT INTO interview_projections VALUES (?,?)",
            (PID, json.dumps({
                "fields": {"personal.fullName": _field("Thorvald", "human_edit", locked=True)},
                "pendingSuggestions": [
                    {"fieldPath": "personal.placeOfBirth", "value": "Duluth"}],
            })),
        )
        vals = ps._load_projection_values(con, PID)
        self.assertIn("personal.fullName", vals)
        self.assertNotIn("personal.placeOfBirth", vals,
                         "an unreviewed guess marked a subject as covered, which "
                         "would stop Lori ever asking about it")

    def test_real_types_are_still_preserved(self):
        """A projected 0 or False is an answer; this reader keeps types on
        purpose and the repair must not change that."""
        from code.api.services import profile_seed as ps
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE interview_projections "
                    "(person_id TEXT PRIMARY KEY, projection_json TEXT)")
        con.execute(
            "INSERT INTO interview_projections VALUES (?,?)",
            (PID, json.dumps({"fields": {
                "family.childrenCount": _field(0, "human_edit", locked=True),
                "personal.living": _field(False, "interview"),
            }, "pendingSuggestions": []})),
        )
        vals = ps._load_projection_values(con, PID)
        self.assertEqual(vals["family.childrenCount"], 0)
        self.assertIs(vals["personal.living"], False)


class CorrectionMayNotOverruleOperatorTests(unittest.TestCase):
    """projection_writer.apply_correction against an operator-entered field."""

    def _run_correction(self, stored_fields, parsed):
        from code.api.services import projection_writer as pw
        from code.api import db as _db

        captured = {}
        real_get = _db.get_projection
        real_merge = _db.merge_projection_fields

        _db.get_projection = lambda pid: {
            "projection": {"fields": json.loads(json.dumps(stored_fields)),
                           "pendingSuggestions": []},
            "version": 3,
        }

        def fake_merge(person_id, **kw):
            captured.update(kw)
            captured["person_id"] = person_id
            return {"write_applied": True, "version": 4}

        _db.merge_projection_fields = fake_merge
        try:
            summary = pw.apply_correction(PID, parsed, source_turn_id="t_1")
        finally:
            _db.get_projection = real_get
            _db.merge_projection_fields = real_merge
        return summary, captured

    def test_a_correction_does_not_overwrite_an_operator_entered_value(self):
        stored = {"personal.placeOfBirth":
                  _field("Superior, Wisconsin", "human_edit", locked=True)}
        summary, captured = self._run_correction(
            stored, {"identity.place_of_birth": "Duluth, Minnesota"})

        self.assertEqual(summary["applied"], [],
                         "a model overwrote a value the operator typed")
        self.assertTrue(summary["deferred"], "the proposal was dropped entirely")
        self.assertEqual(summary["deferred"][0]["field_path"], "personal.placeOfBirth")

        muts = captured.get("mutations") or {}
        self.assertNotIn("personal.placeOfBirth", muts,
                         "the operator's field was sent as a mutation anyway")

    def test_the_proposal_is_queued_for_review_rather_than_lost(self):
        stored = {"personal.placeOfBirth":
                  _field("Superior, Wisconsin", "human_edit", locked=True)}
        _summary, captured = self._run_correction(
            stored, {"identity.place_of_birth": "Duluth, Minnesota"})

        pending = captured.get("pending_suggestions")
        self.assertIsNotNone(pending, "nothing was persisted for review")
        paths = [s.get("fieldPath") for s in pending]
        self.assertIn("personal.placeOfBirth", paths)
        entry = next(s for s in pending if s["fieldPath"] == "personal.placeOfBirth")
        self.assertEqual(entry["value"], "Duluth, Minnesota")
        self.assertEqual(entry["supersedes"], "Superior, Wisconsin",
                         "a reviewer must see what the change would replace")

    def test_an_unlocked_field_is_still_corrected(self):
        """The guard must not freeze the record. A model-inferred value has
        no operator authority behind it and may be corrected."""
        stored = {"personal.placeOfBirth": _field("Dulut", "backend_extract")}
        summary, captured = self._run_correction(
            stored, {"identity.place_of_birth": "Duluth, Minnesota"})
        self.assertTrue(summary["applied"])
        self.assertIn("personal.placeOfBirth", captured.get("mutations") or {})

    def test_history_survives_a_correction(self):
        stored = {"personal.placeOfBirth": _field(
            "Dulut", "backend_extract",
            history=[{"value": "Dlth", "source": "interview", "ts": 1}])}
        _summary, captured = self._run_correction(
            stored, {"identity.place_of_birth": "Duluth, Minnesota"})
        new = (captured.get("mutations") or {})["personal.placeOfBirth"]
        vals = [h.get("value") for h in new.get("history") or []]
        self.assertIn("Dlth", vals, "prior history was erased by the correction")
        self.assertIn("Dulut", vals, "the replaced value was not recorded")

    def test_the_lock_flag_survives_a_correction(self):
        """A correction used to build a fresh dict with no `locked`, so a
        field silently lost its operator-authority flag in passing."""
        stored = {"personal.placeOfBirth": _field("Dulut", "backend_extract", locked=False)}
        _summary, captured = self._run_correction(
            stored, {"identity.place_of_birth": "Duluth, Minnesota"})
        new = (captured.get("mutations") or {})["personal.placeOfBirth"]
        self.assertIn("locked", new)

    def test_the_browser_key_spelling_is_written_too(self):
        """This writer used turn_id/applied_at while the browser gates read
        turnId/ts, so a corrected field was invisible to every client-side
        check (lock, confidence, trust)."""
        stored = {"personal.placeOfBirth": _field("Dulut", "backend_extract")}
        _summary, captured = self._run_correction(
            stored, {"identity.place_of_birth": "Duluth, Minnesota"})
        new = (captured.get("mutations") or {})["personal.placeOfBirth"]
        self.assertIn("turnId", new)
        self.assertIn("ts", new)


if __name__ == "__main__":
    unittest.main(verbosity=2)
