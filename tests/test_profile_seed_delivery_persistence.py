"""The finalized question, and its metadata, survive the real storage path.

    PYTHONPATH=server/code python3 -m unittest tests.test_profile_seed_delivery_persistence

── WHAT THIS ADDS THAT THE DELIVERY SUITE COULD NOT ──────────────────

`test_profile_seed_presentation_delivery` proves `finalize_presentation`
builds the right string and that `delivers_question` gates the stamp. Its
router checks are SOURCE ASSERTIONS — they read `chat_ws.py` and confirm
the call is wired in the right order.

A source assertion proves the call exists. It does not prove the bytes
survive. The existing persistence suites do not close that gap either:
they write `"Lori says…"` and never touch `finalize_presentation`.

So this file runs the real thing end to end:

    finalize_presentation  ->  persist_turn_transaction  ->  export_turns

on a real SQLite database, and asserts what comes back out. No mock, no
fake writer, and no second persistence path — `persist_turn_transaction`
is the same function `chat_ws` calls.

── THE NEGATIVE HALF IS THE POINT ────────────────────────────────────

Proving the assistant row carries the question is half of it. The other
half is that the NARRATOR's row carries neither the question nor any
presentation metadata. A narrator row holding Lori's canonical question
would put words in the narrator's mouth in the memoir source; a narrator
row holding `presented(...)` would let the reducer read the narrator as
having asked themselves a question. Both are asserted.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
for _p in (str(_SERVER_CODE), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api import db as _db                                    # noqa: E402
from api.services import profile_seed as _seed               # noqa: E402
from api.services import profile_seed_turn as _turn          # noqa: E402

A = _seed.TOPIC_IDS[0]      # childhood_home
B = _seed.TOPIC_IDS[1]      # siblings

#: The generic prose that shipped the defect: Lori's own question, with
#: no mention of the topic the server had selected.
GENERIC = ("We've touched on several parts of your story. "
           "Where would you like to continue today?")

NARRATOR_TEXT = "I'd like to continue where we left off."


class _Base(unittest.TestCase):
    """One temp DATA_DIR and database per test.

    `_BIO_SEED_LOADED` is a once-per-process gate; a suite that moves
    `DB_PATH` more than once otherwise gets an empty `bio_fields`
    registry and every person write fails with a foreign-key error that
    reads like a missing person. Same reset the Step 6 suite documents.
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

        self.person_id = _db.create_person(
            "ZZ Delivery Probe",
            date_of_birth="1948-01-11",
            place_of_birth="Boston, Massachusetts",
        )["id"]
        self.conv_id = f"delivery-persist-{self.person_id[:8]}"

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

    # ── the real round trip ──────────────────────────────────────────
    def _deliver_and_persist(self, plan, model_text=GENERIC,
                             narrator_text=NARRATOR_TEXT):
        """Exactly what `chat_ws` does, in the same order, for real.

        The finalizer rewrites `final_text`; the SAME string is what is
        persisted, because that is the guarantee the placement of the
        gate exists to provide. `turn_meta()` is the same accessor the
        router merges into `meta`.
        """
        final_text = _turn.finalize_presentation(model_text, plan)
        self.assertTrue(final_text, "the finalizer produced nothing")
        stamp = _turn.delivers_question(final_text, plan)
        meta: Dict[str, Any] = {"ws": True, "cancelled": False}
        if stamp:
            meta.update(plan.turn_meta())
        _db.persist_turn_transaction(
            self.conv_id, narrator_text, final_text,
            model_name="test", meta=meta, person_id=self.person_id)
        return final_text, stamp

    def _rows(self) -> List[Dict[str, Any]]:
        return _db.export_turns(self.conv_id)

    def _assistant(self) -> Dict[str, Any]:
        rows = [r for r in self._rows() if r["role"] == "assistant"]
        self.assertEqual(1, len(rows), "expected exactly one assistant row")
        return rows[0]

    def _narrator(self) -> Dict[str, Any]:
        rows = [r for r in self._rows()
                if r["role"] in ("user", "narrator")]
        self.assertEqual(1, len(rows), "expected exactly one narrator row")
        return rows[0]


class AssistantRowTests(_Base):
    """The row Lori spoke: exact text AND matching metadata."""

    def setUp(self):
        super().setUp()
        self.plan = _turn.TurnPlan(_turn.PRESENT, A, 7, epoch=2)
        self.final_text, self.stamped = self._deliver_and_persist(self.plan)

    def test_the_stamp_was_permitted(self):
        """Non-vacuity. If the gate refused, nothing below means anything."""
        self.assertTrue(self.stamped)

    def test_the_exact_canonical_question_survives_storage(self):
        row = self._assistant()
        self.assertIn(_seed.topic(A).narrator_question, row["content"])

    def test_the_stored_text_is_byte_identical_to_what_was_delivered(self):
        """Emitted and durable are ONE string, not two similar ones."""
        self.assertEqual(self.final_text, self._assistant()["content"])

    def test_the_model_question_did_not_survive(self):
        row = self._assistant()
        self.assertNotIn("Where would you like to continue today?",
                         row["content"])
        self.assertEqual(1, row["content"].count("?"),
                         f"more than one question reached storage: {row['content']!r}")

    def test_the_presentation_metadata_survives_and_matches(self):
        meta = self._assistant()["meta"]
        self.assertEqual(A, meta.get(_turn.PRESENTED_TOPIC))
        self.assertEqual(2, meta.get(_turn.PRESENTED_EPOCH))
        self.assertEqual(7, meta.get(_turn.PRESENTED_VERSION))

    def test_the_stored_row_reduces_to_the_event_it_claims(self):
        """The reducer's own reader, on the row that came OUT of storage.

        Asserting the keys is not the same as asserting the machine can
        use them — a stored row that `event_from_meta` rejects would be
        an event nobody can correlate against.
        """
        event = _turn.event_from_meta(self._assistant()["meta"])
        self.assertIsNotNone(event, "the persisted row produced no event")
        self.assertEqual(_turn.PRESENTED, event.kind)
        self.assertEqual((A, 2), event.tuple)
        self.assertFalse(event.is_legacy)

    def test_the_outstanding_presentation_is_found_from_stored_rows(self):
        """End to end: storage -> export -> reduction."""
        outstanding = _turn.outstanding_presentation(self._rows())
        self.assertIsNotNone(outstanding)
        self.assertEqual((A, 2), outstanding.tuple)


class NarratorRowTests(_Base):
    """The row the NARRATOR spoke must carry neither."""

    def setUp(self):
        super().setUp()
        self.plan = _turn.TurnPlan(_turn.PRESENT, A, 7, epoch=2)
        self._deliver_and_persist(self.plan)

    def test_the_narrator_row_does_not_contain_the_canonical_question(self):
        """Lori's words must never be stored as the narrator's.

        The memoir source is rebuilt from these rows. A canonical
        question sitting on the narrator's row is Lori's sentence
        attributed to the person whose life story this is.
        """
        row = self._narrator()
        self.assertEqual(NARRATOR_TEXT, row["content"])
        self.assertNotIn(_seed.topic(A).narrator_question, row["content"])

    def test_the_narrator_row_carries_no_presentation_metadata(self):
        meta = self._narrator()["meta"] or {}
        for key in _turn.META_KEYS:
            self.assertNotIn(key, meta,
                             f"narrator row carries {key}")

    def test_the_narrator_row_produces_no_turn_event(self):
        self.assertIsNone(_turn.event_from_meta(self._narrator()["meta"]))


class RefusedDeliveryTests(_Base):
    """A turn that could not deliver stamps nothing — through storage."""

    def test_an_unknown_topic_persists_no_presentation_metadata(self):
        plan = _turn.TurnPlan(_turn.PRESENT, "favourite_colour", 7, epoch=2)
        self.assertEqual("", _turn.finalize_presentation(GENERIC, plan))
        # chat_ws drops the planned meta and persists the model text.
        _db.persist_turn_transaction(
            self.conv_id, NARRATOR_TEXT, GENERIC,
            model_name="test", meta={"ws": True, "cancelled": False},
            person_id=self.person_id)
        meta = self._assistant()["meta"] or {}
        for key in _turn.META_KEYS:
            self.assertNotIn(key, meta)
        self.assertIsNone(_turn.outstanding_presentation(self._rows()),
                          "a turn that asked nothing left a question open")

    def test_a_cancelled_turn_persists_no_presentation_metadata(self):
        """Cancellation is observed at the merge, not in the finalizer."""
        plan = _turn.TurnPlan(_turn.PRESENT, A, 7, epoch=2)
        final_text = _turn.finalize_presentation(GENERIC, plan)
        _db.persist_turn_transaction(
            self.conv_id, NARRATOR_TEXT, final_text,
            model_name="test",
            meta={"ws": True, "cancelled": True},   # cancelled -> {} merged
            person_id=self.person_id)
        meta = self._assistant()["meta"] or {}
        for key in _turn.META_KEYS:
            self.assertNotIn(key, meta)
        self.assertIsNone(_turn.outstanding_presentation(self._rows()))


class RePresentPersistenceTests(_Base):
    """RE_PRESENT stores the fixed lead-in and the same canonical question."""

    def test_re_present_round_trips(self):
        plan = _turn.TurnPlan(_turn.RE_PRESENT, B, 9, epoch=4)
        final_text, stamped = self._deliver_and_persist(plan)
        self.assertTrue(stamped)
        row = self._assistant()
        self.assertEqual(final_text, row["content"])
        self.assertTrue(row["content"].startswith(_turn.RE_PRESENT_LEAD_IN))
        self.assertIn(_seed.topic(B).narrator_question, row["content"])
        self.assertEqual(1, row["content"].count("?"))
        event = _turn.event_from_meta(row["meta"])
        self.assertEqual((B, 4), event.tuple)


if __name__ == "__main__":      # pragma: no cover
    unittest.main()
