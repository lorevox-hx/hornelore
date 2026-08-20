"""Server evidence survives draft and bilingual export.

WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01, export completion (2026-08-19).

Three defects, all in the same family: the draft and bilingual builders
were written when `sections` was purely the threads view of the same
content, and stopped being right once the SERVER began appending
review-gated evidence as sections.

  * the draft builders rendered `req.prose` and ignored `req.sections`,
    so a draft export silently omitted every reviewed story;
  * the first repair rendered only `captured_stories*`, so approved
    Travel Document stories were still lost;
  * the bilingual draft rendered evidence in the source language only,
    while every surrounding paragraph appeared in both -- and a bilingual
    memoir exists precisely so a Spanish-reading grandchild can read the
    narrator speaking;
  * `trip_stories*` was not a reserved namespace, so a client could send
    a section wearing it and have it appear as operator-approved travel
    evidence.

TRANSLATION IS STUBBED WITH A DISTINCT SPANISH STRING. Relying on the
offline connection-failure fallback would have made every "the Spanish
text is present" assertion pass on the ENGLISH text, which is the shape
of test that proves nothing.

Run with:

    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_memoir_draft_and_bilingual_evidence
"""
from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
for _p in (str(_SERVER_CODE), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api.routers import memoir_export as _me  # noqa: E402

_STORY = "The porch, the peas, the evening cooling off."
_TRIP = "We arrived in Munich after dark."
_PROSE = "An operator wrote this paragraph."

#: What the stub returns. Deliberately unmistakable: if an assertion for
#: Spanish content ever passes on English text, this string is what makes
#: the difference visible.
_ES = {
    _STORY: "El porche, los guisantes, la tarde refrescando.",
    _TRIP: "Llegamos a Múnich despues del anochecer.",
    _PROSE: "Un operador escribio este parrafo.",
}


class _Base(unittest.TestCase):
    def setUp(self):
        if not _me._DOCX_AVAILABLE:
            self.skipTest("python-docx not installed in this environment")

        # Stub the translation SERVICE, not the export helper, so the real
        # `_translate_request_content` runs -- including its handling of
        # labels, items, prose and `sources`.
        from api.services import translation as _translation
        self._orig = _translation.translate_text

        def _fake(text, source_lang="en", target_lang="es",
                  narrator_name=None):
            return _ES.get(text, "ES::" + text)

        _translation.translate_text = _fake
        self.addCleanup(setattr, _translation, "translate_text", self._orig)

        self.captured = _me.MemoirSection(
            id="captured_stories_adolescence",
            label="In their own words — Adolescence",
            items=[_STORY], sources=["deadbeef1234"])
        self.trip = _me.MemoirSection(
            id="trip_stories_abc123",
            label="From your travels — Germany 1971",
            items=[_TRIP])
        self.operator = _me.MemoirSection(
            id="operator_authored", label="Operator section",
            items=["An operator thread item."])
        self.req = _me.MemoirExportRequest(
            narrator_name="N", memoir_state="draft", prose=_PROSE,
            sections=[self.operator, self.captured, self.trip])

    def _text(self, blob):
        from docx import Document as _D
        doc = _D(io.BytesIO(blob))
        return "\n".join(p.text for p in doc.paragraphs), doc


# ── Both lanes reach the draft ──────────────────────────────────────────

class DraftCarriesBothEvidenceLanes(_Base):

    def test_english_draft_has_the_captured_story_and_the_trip_story(self):
        text, _ = self._text(_me._build_draft_docx(self.req, render_lang="en"))
        self.assertEqual(text.count(_STORY), 1)
        self.assertEqual(text.count(_TRIP), 1)

    def test_operator_prose_is_untouched_and_comes_first(self):
        text, _ = self._text(_me._build_draft_docx(self.req, render_lang="en"))
        self.assertIn(_PROSE, text)
        self.assertLess(text.index(_PROSE), text.index(_STORY))

    def test_the_helper_matches_both_reserved_namespaces(self):
        found = {s.id for s in _me._server_evidence_sections_of(self.req)}
        self.assertEqual(found, {"captured_stories_adolescence",
                                 "trip_stories_abc123"})
        self.assertNotIn("operator_authored", found)

    def test_threads_still_carries_both(self):
        threads = self.req.model_copy(update={"memoir_state": "threads"})
        text, _ = self._text(_me._build_threads_docx(threads, render_lang="en"))
        self.assertEqual(text.count(_STORY), 1)
        self.assertEqual(text.count(_TRIP), 1)


# ── Spanish draft renders the TRANSLATED evidence ───────────────────────

class SpanishDraftRendersTranslatedEvidence(_Base):

    def test_the_spanish_draft_contains_the_spanish_story(self):
        translated = _me._translate_request_content(self.req, "es")
        text, _ = self._text(
            _me._build_draft_docx(translated, render_lang="es"))
        self.assertIn(_ES[_STORY], text)
        self.assertIn(_ES[_TRIP], text)

    def test_it_does_not_also_carry_the_english(self):
        """A Spanish-only export is Spanish-only."""
        translated = _me._translate_request_content(self.req, "es")
        text, _ = self._text(
            _me._build_draft_docx(translated, render_lang="es"))
        self.assertNotIn(_STORY, text)
        self.assertNotIn(_TRIP, text)

    def test_each_appears_exactly_once(self):
        translated = _me._translate_request_content(self.req, "es")
        text, _ = self._text(
            _me._build_draft_docx(translated, render_lang="es"))
        self.assertEqual(text.count(_ES[_STORY]), 1)
        self.assertEqual(text.count(_ES[_TRIP]), 1)

    def test_provenance_survives_translation_into_the_artifact(self):
        translated = _me._translate_request_content(self.req, "es")
        _, doc = self._text(
            _me._build_draft_docx(translated, render_lang="es"))
        comments = doc.core_properties.comments or ""
        self.assertIn("captured_stories_adolescence:0=deadbeef1234", comments)


# ── Bilingual draft renders each item once per language ─────────────────

class BilingualDraftRendersBothLanguages(_Base):

    def _render(self):
        translated = _me._translate_request_content(self.req, "es")
        return self._text(_me._build_draft_docx_bilingual(self.req, translated))

    def test_the_story_appears_in_both_languages(self):
        text, _ = self._render()
        self.assertIn(_STORY, text)
        self.assertIn(_ES[_STORY], text)

    def test_the_trip_story_appears_in_both_languages(self):
        text, _ = self._render()
        self.assertIn(_TRIP, text)
        self.assertIn(_ES[_TRIP], text)

    def test_neither_language_is_duplicated(self):
        text, _ = self._render()
        for line in (_STORY, _ES[_STORY], _TRIP, _ES[_TRIP]):
            with self.subTest(line=line[:30]):
                self.assertEqual(text.count(line), 1)

    def test_the_translation_follows_its_own_source_line(self):
        """Pairing is by section id and item index. Getting this wrong
        attaches one story's translation to another's text, which reads
        as the narrator having said something they did not."""
        text, _ = self._render()
        self.assertLess(text.index(_STORY), text.index(_ES[_STORY]))
        self.assertLess(text.index(_ES[_STORY]), text.index(_TRIP))

    def test_an_untranslated_item_is_not_printed_twice(self):
        """When the service is unavailable it passes source text through.
        Printing the same sentence twice is worse than printing it once.
        """
        from api.services import translation as _translation
        _translation.translate_text = lambda text, **kw: text
        translated = _me._translate_request_content(self.req, "es")
        text, _ = self._text(
            _me._build_draft_docx_bilingual(self.req, translated))
        self.assertEqual(text.count(_STORY), 1)

    def test_a_shorter_translated_section_does_not_shift_the_pairing(self):
        translated = _me._translate_request_content(self.req, "es")
        short = [s.model_copy(update={"items": []})
                 if s.id == "captured_stories_adolescence" else s
                 for s in translated.sections]
        translated = translated.model_copy(update={"sections": short})
        text, _ = self._text(
            _me._build_draft_docx_bilingual(self.req, translated))
        self.assertIn(_STORY, text)
        self.assertNotIn(_ES[_STORY], text)
        # The trip story keeps its own translation regardless.
        self.assertIn(_ES[_TRIP], text)


# ── The reserved namespace covers both lanes ────────────────────────────

class BothNamespacesAreServerOwned(_Base):

    def test_the_prefix_tuple_names_both(self):
        self.assertEqual(_me._RESERVED_SECTION_PREFIXES,
                         ("captured_stories", "trip_stories"))

    def test_a_client_section_in_either_namespace_is_recognised(self):
        for sid in ("captured_stories_today", "trip_stories_xyz"):
            with self.subTest(sid=sid):
                self.assertTrue(_me._is_server_evidence_section(
                    _me.MemoirSection(id=sid, label="L", items=["x"])))

    def test_an_operator_section_is_not(self):
        self.assertFalse(_me._is_server_evidence_section(self.operator))

    def test_the_route_strips_both_namespaces_from_client_input(self):
        src = Path(_me.__file__).read_text(encoding="utf-8")
        i = src.index("_client_sections = [")
        window = src[i:i + 400]
        self.assertIn("_is_server_evidence_section(s)", window)

    def test_no_provenance_is_invented_for_trip_notes(self):
        """Trip notes have no stable candidate id to digest, so they carry
        no `sources` -- an invented digest would look exactly like a real
        one and could never afterwards be told apart."""
        self.assertEqual(self.trip.sources, [])
        translated = _me._translate_request_content(self.req, "es")
        tgt = {s.id: s for s in translated.sections}
        self.assertEqual(tgt["trip_stories_abc123"].sources, [])


if __name__ == "__main__":
    unittest.main()


# ── Commit A · export integrity ─────────────────────────────────────────

class SanitisationIsUnconditional(_Base):
    """A defence you can switch off by asking for less is not a defence.

    The strip used to sit inside `if person_id and include_captured_stories`,
    so omitting the narrator -- or setting `include_captured_stories=false`
    -- let a caller send sections wearing a reserved id with forged
    `sources`, which the artifact would present as reviewed evidence with
    server provenance.
    """

    def test_the_strip_is_not_nested_under_the_harvest_flags(self):
        src = Path(_me.__file__).read_text(encoding="utf-8")
        route = src[src.index("def api_memoir_export_docx"):]
        # Anchored on the COLON: the strip block's own comment quotes the
        # gate it used to sit inside, and the first cut of this test
        # matched that explanation instead of the statement.
        #
        # REPOINTED 2026-08-19. Retired gate spelling:
        #     "if req.person_id and req.include_captured_stories:"
        # The two lane reads collapsed into ONE `canonical_memoir()` call,
        # so the harvest now sits behind a single combined gate. The
        # property under test -- the strip runs BEFORE and OUTSIDE any
        # harvest gate -- is unchanged.
        strip_at = route.index("_client_sections = [")
        gate_at = route.index(
            "if req.person_id and (req.include_captured_stories "
            "or req.include_trip_stories):")
        self.assertLess(strip_at, gate_at,
                        "sanitisation must run before, and outside, the "
                        "harvest gates")

    def test_client_languages_are_discarded_too(self):
        src = Path(_me.__file__).read_text(encoding="utf-8")
        i = src.index("_client_sections = [")
        self.assertIn('"languages": []', src[i:i + 300])


class AuthoritativeLanesRefuseRatherThanLookComplete(_Base):

    def test_the_trip_lane_reports_its_own_status(self):
        src = Path(_me.__file__).read_text(encoding="utf-8")
        fn = src[src.index("def _trip_story_sections("):]
        fn = fn[:fn.index("\ndef ")]
        for verdict in ('"not_attempted"', '"unavailable"', '"partial"',
                        '"read"'):
            with self.subTest(verdict=verdict):
                self.assertIn(verdict, fn)

    def test_a_partial_trip_read_refuses_the_export(self):
        """REPOINTED 2026-08-19. Retired:

            i = route.index("_trip_status")
            assertIn('_trip_status in ("partial", "unavailable")', window)

        There is no per-lane status variable in the route any more. It
        makes ONE `canonical_memoir()` call and refuses on ANY lane
        reporting `partial` or `unavailable`, which covers the trip lane
        and the story lane by the same rule rather than by two named
        checks that could drift apart.
        """
        src = Path(_me.__file__).read_text(encoding="utf-8")
        route = src[src.index("def api_memoir_export_docx"):]
        i = route.index("_lane_status = dict(_canon.lanes)")
        window = route[i:i + 900]
        self.assertIn('v in ("partial", "unavailable")', window)
        self.assertIn("503", window)
        # …and the trip lane really is one of the lanes being judged.
        # This suite has no database, so the lane's PRESENCE in the
        # contract output is proven behaviourally in
        # `test_memoir_canonical_contract`; asserted here only that the
        # route's rule reads every lane rather than a named subset.
        self.assertIn("for k, v in _lane_status.items()", window)

    def test_provenance_alignment_is_checked_not_assumed(self):
        src = Path(_me.__file__).read_text(encoding="utf-8")
        route = src[src.index("def api_memoir_export_docx"):]
        self.assertIn("len(sec.sources) != len(sec.items)", route)

    def test_a_failed_stamp_refuses_rather_than_ships_unstamped(self):
        src = Path(_me.__file__).read_text(encoding="utf-8")
        fn = src[src.index("def _stamp_source_provenance("):]
        fn = fn[:fn.index("\ndef ")]
        self.assertIn("raise HTTPException", fn)
        self.assertNotIn("best effort", fn)


class TripNotesCarryTheirOwnProvenance(_Base):

    def test_a_note_digest_is_stable_and_namespaced_apart(self):
        a = _me._trip_note_source_digest("note-1")
        self.assertEqual(a, _me._trip_note_source_digest("note-1"))
        self.assertNotEqual(a, _me._story_source_digest("note-1"),
                            "a note and a candidate with the same id must "
                            "not collide")


class RequestedTranslationIsNotFaked(_Base):

    def _req_with_english_story(self):
        sec = _me.MemoirSection(
            id="captured_stories_adolescence", label="L",
            items=[_STORY], sources=["d1"], languages=["en"])
        return _me.MemoirExportRequest(
            narrator_name="N", memoir_state="draft", sections=[sec])

    def test_untranslated_evidence_refuses_a_spanish_export(self):
        from fastapi import HTTPException
        from api.services import translation as _t
        _t.translate_text = lambda text, **kw: text     # service down
        req = self._req_with_english_story()
        translated = _me._translate_request_content(req, "es")
        with self.assertRaises(HTTPException) as ctx:
            _me._assert_translation_covered(req, translated, "es")
        self.assertEqual(ctx.exception.status_code, 503)

    def test_a_real_translation_passes(self):
        req = self._req_with_english_story()
        translated = _me._translate_request_content(req, "es")
        _me._assert_translation_covered(req, translated, "es")

    def test_an_item_already_in_spanish_is_not_flagged(self):
        """Per-item language is why this works: a Spanish story returned
        unchanged is correct, not a failed translation."""
        from api.services import translation as _t
        _t.translate_text = lambda text, **kw: text
        sec = _me.MemoirSection(
            id="captured_stories_today", label="L",
            items=["Ya esta en espanol."], sources=["d1"], languages=["es"])
        req = _me.MemoirExportRequest(narrator_name="N", sections=[sec])
        translated = _me._translate_request_content(req, "es")
        _me._assert_translation_covered(req, translated, "es")

    def test_english_exports_are_never_checked(self):
        req = self._req_with_english_story()
        _me._assert_translation_covered(req, req, "en")
