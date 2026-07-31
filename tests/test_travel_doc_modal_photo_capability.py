"""WO-TRIP-NARRATOR-BRIDGE-01 section 1D — the modal answers the photo
question with a number.

THE LIVE FAILURE. Asked "can you see any of the photos I added to my
trip?" in the Travel Doc modal, Lori replied:

    You added photos to your trip, but I'm a listener, not a viewer.
    I'm happy to chat with you, though! What would you like to talk
    about regarding those photos?

Not a false vision claim -- the honesty rule held. But two photographs
were sitting on the Bismarck Trip and she did not say so, and she closed
by asking him what he wanted to discuss. He asked a question whose
answer is a number and got a question back.

The cause was narrow: the modal's two patterns are about ONE photograph
("when was THIS taken", "tell me about THIS photo"), so the plural,
whole-trip form matched neither and fell through to the model.

THE FIX IS A WIRE, NOT A SECOND IMPLEMENTATION. The narrator side
already has a classifier and a composer for exactly this question. Two
surfaces answering it from two sets of rules is how one of them quietly
becomes wrong, and the divergence would present as Lori being honest in
the Narrator Room and vague in Travel Doc -- which nobody would think to
test for. So these tests assert the wiring and the shared identity, not
a reimplementation.

Offline sqlite fixture, same pattern as the day-capture ack tests.
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api import db as _db  # noqa: E402
from api.services import trip_repository  # noqa: E402
from api.services import travel_doc_lori_modal as modal  # noqa: E402
from api.services import trip_interview_context as tic  # noqa: E402

# The question exactly as Chris typed it.
THE_QUESTION = "can you see any of the photos I added to my trip?"

VISUAL_CLAIMS = ("i can see", "i see the", "the image shows",
                 "the photo shows", "the picture shows", "i looked at",
                 "i can view", "in the photo", "in the image")


def _add_photo(con, photo_id, person_id, ready=1, caption_ok=0):
    cols = {r[1] for r in con.execute("PRAGMA table_info(photos)")}
    values = {
        "id": photo_id,
        "narrator_id": person_id,
        "image_path": "/tmp/%s.jpg" % photo_id,
        "file_hash": "hash-" + photo_id,
        "narrator_ready": ready,
        "date_precision": "unknown",
        "caption_approved_for_lori": caption_ok,
        "created_at": "2026-07-14",
        "updated_at": "2026-07-14",
    }
    use = {k: v for k, v in values.items() if k in cols}
    con.execute(
        "INSERT INTO photos (%s) VALUES (%s)"
        % (", ".join(use), ", ".join("?" for _ in use)),
        tuple(use.values()))


class _ModalPhotoCase(unittest.TestCase):
    """Bismarck as it actually stands: two attached, both on days, none
    cleared for Lori."""

    attached = 2
    narrator_ready = 0

    def setUp(self):
        self._tmpdb = tempfile.NamedTemporaryFile(suffix=".sqlite3",
                                                  delete=False)
        self._tmpdb.close()
        self.db_path = Path(self._tmpdb.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()

        self.person_id = str(uuid.uuid4())
        self.other_person = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        for pid, nm in ((self.person_id, "Chris"),
                        (self.other_person, "Someone Else")):
            con.execute(
                "INSERT INTO people (id, display_name, date_of_birth, "
                "created_at, updated_at) VALUES (?, ?, '1962-12-24', "
                "'2026-07-14', '2026-07-14')", (pid, nm))
        con.commit()
        con.close()

        self.trip_id = trip_repository.trip_create(
            self.person_id, "Bismarck Trip",
            start_date="2026-07-14", end_date="2026-07-19")
        self.region_id = trip_repository.region_create(
            self.trip_id, "North Dakota")
        trip_repository.trip_days_generate(self.trip_id)
        self.days = trip_repository.trip_days_list(self.trip_id)

        con = sqlite3.connect(str(self.db_path))
        for i in range(self.attached):
            _add_photo(con, "p%d" % i, self.person_id,
                       ready=self.narrator_ready)
        con.commit()
        con.close()
        for i in range(self.attached):
            trip_repository.photo_link_upsert(
                self.trip_id, "p%d" % i, trip_region_id=self.region_id,
                assignment_method="operator")

    def _hide_one(self):
        """Reduce the attached count the way the product does. There is
        no DELETE on the evidence lane by doctrine, and hidden links are
        outside every inventory count, so this is the real path a photo
        leaves the trip by."""
        links = trip_repository.photo_links_list(self.trip_id)
        trip_repository.photo_link_update(links[0]["id"], hidden=True)

    def tearDown(self):
        _db.DB_PATH = self._orig_db
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def _scope(self):
        return modal.build_modal_scope(
            person_id=self.person_id,
            active_trip_id=self.trip_id,
            conv_id="tdlab_conv",
            selected_kind="trip")

    def _ask(self, text=THE_QUESTION, person=None):
        return modal.answer_modal_direct_question(
            person or self.person_id, self._scope(), text)


class TheQuestionIsAnsweredTest(_ModalPhotoCase):

    def test_the_exact_question_is_no_longer_handed_to_the_model(self):
        self.assertIsNotNone(self._ask(),
                             "returning None sends it to the LLM, which is "
                             "the live failure")

    def test_it_states_the_real_count(self):
        ans = (self._ask() or "").lower()
        self.assertTrue("two" in ans or "2" in ans, ans)

    def test_the_count_is_read_from_the_trip_not_hardcoded(self):
        """A composer that always says 'two' would pass the test above."""
        self._hide_one()
        ans = (self._ask() or "").lower()
        self.assertTrue("one" in ans or " 1 " in ans, ans)
        self.assertNotIn("two", ans)

    def test_it_makes_no_visual_claim(self):
        ans = (self._ask() or "").lower()
        for bad in VISUAL_CLAIMS:
            self.assertNotIn(bad, ans, bad)

    def test_it_says_it_does_not_inspect_the_pictures(self):
        ans = (self._ask() or "").lower()
        self.assertTrue(
            "look" in ans or "see" in ans,
            "the answer has to address the capability he asked about")

    def test_it_answers_before_it_asks(self):
        """The live reply led with a question. An answer that opens by
        asking what he wants to discuss has not answered."""
        ans = (self._ask() or "").strip()
        first = ans.split("?")[0]
        self.assertTrue(len(first) > 20, ans)
        self.assertFalse(ans.startswith("What"), ans)

    def test_zero_photos_says_so_rather_than_counting(self):
        for l in trip_repository.photo_links_list(self.trip_id):
            trip_repository.photo_link_update(l["id"], hidden=True)
        ans = (self._ask() or "").lower()
        self.assertIn("aren", ans)          # "there aren't any photos"
        for bad in VISUAL_CLAIMS:
            self.assertNotIn(bad, ans, bad)


class ItDoesNotEatTheRestOfTheModalTest(_ModalPhotoCase):
    """The classifier sits ahead of two existing patterns. If it were
    greedy it would take their turns, and those answers are more
    specific than this one."""

    def test_the_single_photo_date_question_is_untouched(self):
        self.assertFalse(
            tic.is_photo_capability_question("what date was this taken"))
        self.assertFalse(
            tic.is_photo_capability_question("when was that photo taken"))

    def test_the_single_photo_about_question_is_untouched(self):
        for q in ("tell me about this photo",
                  "can you tell me about that picture",
                  "what do you know about this photo"):
            self.assertFalse(tic.is_photo_capability_question(q), q)

    def test_ordinary_narration_about_photographs_is_not_intercepted(self):
        """The memoir is full of these. Swallowing one would discard a
        memory to answer a question nobody asked."""
        for s in ("I took photos of the gravesite that day.",
                  "Melanie showed me pictures of the school.",
                  "We have photographs of the whole trip somewhere.",
                  "The photos from that summer are in a box."):
            self.assertFalse(tic.is_photo_capability_question(s), s)
            self.assertIsNone(self._ask(s), s)


class ItAnswersFromOneSetOfRulesTest(_ModalPhotoCase):
    """Both surfaces, one classifier and one composer. Asserted by
    identity, not by comparing two outputs that could drift together."""

    def test_the_modal_calls_the_narrator_sides_functions(self):
        import ast
        src = (_SERVER_CODE / "api" / "services"
               / "travel_doc_lori_modal.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        node = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef)
                    and n.name == "answer_modal_direct_question")
        body = ast.get_source_segment(src, node) or ""
        self.assertIn("is_photo_capability_question", body)
        self.assertIn("compose_photo_capability_answer", body)

    def test_it_defines_no_rival_pattern_or_composer(self):
        src = (_SERVER_CODE / "api" / "services"
               / "travel_doc_lori_modal.py").read_text(encoding="utf-8")
        self.assertNotIn("_PHOTO_CAPABILITY_RX = ", src)
        self.assertNotIn("def compose_photo_capability_answer", src)
        self.assertNotIn("def is_photo_capability_question", src)

    def test_it_does_not_reach_the_shelf_coupled_entry_point(self):
        """The shelf-coupled entry point in trip_interview_context reads
        runtime71 and Travels-shelf state. The modal owns its own
        explicit scope and must not read the browser's.

        READS THE AST, NOT THE TEXT. The first version of this test
        scanned the raw source and failed -- on the comment that exists
        to explain the rule, and on the module docstring that has named
        runtime71 since the file was written. That is the fourth time in
        this repository that a guard written against a WORD has fired on
        the prose about the word. A guard has to match what the
        interpreter executes."""
        import ast
        src = (_SERVER_CODE / "api" / "services"
               / "travel_doc_lori_modal.py").read_text(encoding="utf-8")
        names = set()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Attribute):
                names.add(node.attr)
            elif isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.arg):
                names.add(node.arg)
            elif isinstance(node, ast.alias):
                names.add(node.name.split(".")[-1])
        self.assertNotIn("context_block_for_turn", names)
        self.assertNotIn("runtime71", names)
        # Non-vacuity: the walker really does see this module's names.
        self.assertIn("build_trip_interview_context", names)

    def test_both_surfaces_produce_the_same_answer_for_the_same_trip(self):
        ctx = tic.build_trip_interview_context(self.person_id, self.trip_id)
        self.assertEqual(self._ask(),
                         tic.compose_photo_capability_answer(ctx))


class ItStaysInsideTheOwnersTripTest(_ModalPhotoCase):

    def test_another_persons_question_gets_no_count(self):
        """build_modal_scope stamps the owner; a mismatched caller must
        not receive a count of somebody else's photographs."""
        self.assertIsNone(self._ask(person=self.other_person))

    def test_a_trip_that_is_not_his_yields_no_answer(self):
        other_trip = trip_repository.trip_create(
            self.other_person, "Not His Trip")
        scope = modal.build_modal_scope(
            person_id=self.person_id,
            active_trip_id=other_trip,
            conv_id="tdlab_conv",
            selected_kind="trip")
        self.assertIsNone(
            modal.answer_modal_direct_question(
                self.person_id, scope, THE_QUESTION))


class UnapprovedTextNeverLeaksTest(_ModalPhotoCase):
    """narrator_ready is not permission to speak a caption. Only a
    separately approved caption may be quoted."""

    def test_an_unapproved_caption_is_not_quoted(self):
        links = trip_repository.photo_links_list(self.trip_id)
        secret = "the headstone had her maiden name on it"
        trip_repository.photo_link_update(links[0]["id"], caption=secret)
        ans = (self._ask() or "").lower()
        self.assertNotIn("maiden name", ans)
        self.assertNotIn(secret, ans)


if __name__ == "__main__":
    unittest.main()
