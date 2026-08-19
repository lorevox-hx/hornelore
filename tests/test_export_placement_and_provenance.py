"""Canonical placement and provenance survive every export mode.

WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01, completion commit (2026-08-19).

Four verified gaps, each of which would have made the live chain's Life
Map or DOCX evidence incomplete:

  * `_collect_story_evidence` dropped the canonical `era` before it
    reached the browser. The browser had just been taught to read
    `row.era` instead of interpreting `era_candidates` itself, so the key
    was absent and EVERY story -- including operator-placed ones --
    rendered as unplaced;
  * a successful `no_dob` response left a restored cached spine on
    screen, so historical periods kept drawing for a narrator the server
    had just said has none;
  * `_sources_block` still emitted `count: 0` for an unreadable lane, so
    a provenance line could read "unavailable · 0";
  * client-supplied `sources` were trusted, translation dropped them, and
    the draft builders ignored `req.sections` entirely -- so a draft
    export silently omitted every reviewed story.

Run with:

    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_export_placement_and_provenance
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
for _p in (str(_SERVER_CODE), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api import db as _db  # noqa: E402
from api.routers import chronology_accordion as _ca  # noqa: E402
from api.routers import memoir_export as _me  # noqa: E402
from tests.source_scan_helpers import strip_js_comments  # noqa: E402

_UI = _REPO_ROOT / "ui" / "js"


def _read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


class _Base(unittest.TestCase):
    def setUp(self):
        fd = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        fd.close()
        self.db_path = Path(fd.name)
        self._orig = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()
        self.narrator = str(uuid.uuid4())
        self.conv = "conv-" + uuid.uuid4().hex[:8]
        con = sqlite3.connect(str(self.db_path))
        con.execute("INSERT INTO people (id, display_name, created_at, updated_at)"
                    " VALUES (?,?,?,?)",
                    (self.narrator, "N", "2026-08-19", "2026-08-19"))
        con.execute("INSERT INTO sessions (conv_id, updated_at) VALUES (?,?)",
                    (self.conv, "2026-08-19"))
        con.commit()
        con.close()

    def tearDown(self):
        _db.DB_PATH = self._orig
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def _story(self, text):
        cid = str(uuid.uuid4())
        _db.story_candidate_insert(
            cid, narrator_id=self.narrator, transcript=text,
            trigger_reason="manual", scene_anchor_count=1,
            session_id=self.conv, conversation_id=self.conv, turn_id=None)
        return cid

    def _review(self, cid, status="promoted", *, eras=None, year=None,
                source=None):
        _db.story_candidate_review_apply(
            cid, narrator_id=self.narrator, expected_version=1,
            review_status=status, reviewed_by="test",
            era_candidates=eras, estimated_year_low=year,
            estimated_year_high=year, placement_source=source)


# ── Gap 1 · the canonical era reaches the browser ───────────────────────

class TheCanonicalEraReachesTheChronologyPayload(_Base):

    def test_an_operator_placed_story_carries_its_exact_era(self):
        cid = self._story("Placed by a human.")
        self._review(cid, eras=["coming_of_age"], year=1955,
                     source="operator_set")
        lane = _ca._collect_story_evidence(self.narrator)
        self.assertEqual(lane.status, "read")
        self.assertEqual(lane.items[0]["era"], "coming_of_age")
        self.assertNotEqual(lane.items[0]["placement"], "unplaced")

    def test_a_year_only_placement_stays_unplaced_with_no_era(self):
        cid = self._story("Sometime around then.")
        self._review(cid, year=1948, source="operator_set")
        row = _ca._collect_story_evidence(self.narrator).items[0]
        self.assertIsNone(row["era"])
        self.assertEqual(row["placement"], "unplaced")

    def test_an_unconfirmed_candidate_is_not_promoted_into_era(self):
        cid = self._story("A guessed placement.")
        self._review(cid, eras=["earliest_years"])
        row = _ca._collect_story_evidence(self.narrator).items[0]
        self.assertIsNone(row["era"])
        self.assertEqual(row["placement"], "unplaced")
        # The shortlist still travels for the operator surface; it is
        # simply no longer the placement.
        self.assertEqual(row["era_candidates"], ["earliest_years"])

    def test_the_browser_reads_era_and_never_the_shortlist(self):
        js = strip_js_comments(_read(_UI / "story-evidence.js"))
        fn = js[js.index("function byEra()"):]
        fn = fn[:fn.index("\n  }")]
        self.assertIn("row.era", fn)
        self.assertNotIn("era_candidates", fn)


# ── Gap 2 · a no-DOB answer is authoritative ────────────────────────────

class ANoDobAnswerReplacesTheCache(_Base):

    def setUp(self):
        super().setUp()
        self.js = _read(_UI / "app.js")
        i = self.js.index("const derived = (j.periods || []).filter")
        self.branch = self.js[i:i + 2200]

    def test_the_server_periods_replace_the_spine(self):
        self.assertIn("state.timeline.spine = {", self.branch)
        self.assertIn("periods:     j.periods || []", self.branch)

    def test_readiness_is_false(self):
        self.assertIn("state.timeline.seedReady = false;", self.branch)

    def test_the_projection_is_still_kept(self):
        """A narrator with no date of birth keeps their stories, events
        and trip days -- those lanes never needed one."""
        self.assertIn("state.chronologyProjection = j;", self.branch)

    def test_the_retired_reasoning_is_recorded(self):
        """The old branch kept the cache on purpose. The correction is
        that a SUCCESSFUL answer is not the same as a failed request, and
        the comment says so rather than leaving a silent reversal."""
        self.assertIn("do not overwrite a cached spine", self.branch)
        self.assertIn("authoritative", self.branch.lower())

    def test_a_no_dob_narrator_still_gets_their_stories_server_side(self):
        cid = self._story("Told before any birthday was given.")
        self._review(cid, source="operator_set")
        payload = _ca.build_chronology_accordion_payload(
            self.narrator, {}, {}, [])
        self.assertEqual(payload["reason"], "no_dob")
        self.assertEqual(len(payload["story_evidence"]), 1)
        self.assertEqual(payload["story_evidence"][0]["placement"], "unplaced")


# ── Gap 3 · an unknown count is null ────────────────────────────────────

class AnUnknownSourceCountIsNull(_Base):

    def test_unavailable_and_not_attempted_report_null(self):
        block = _ca._sources_block(
            dob_ok=True,
            timeline_events=_ca._LaneResult([], "unavailable"),
            story_evidence=None,
            trip_days=_ca._LaneResult([], "read"))
        self.assertIsNone(block["timeline_events"]["count"])
        self.assertEqual(block["timeline_events"]["status"], "unavailable")
        self.assertIsNone(block["story_evidence"]["count"])
        self.assertEqual(block["story_evidence"]["status"], "not_attempted")

    def test_a_read_and_empty_lane_reports_zero(self):
        """Zero is a fact about a person's life and still belongs here."""
        block = _ca._sources_block(
            dob_ok=True, trip_days=_ca._LaneResult([], "read"))
        self.assertEqual(block["trip_days"]["count"], 0)
        self.assertEqual(block["trip_days"]["status"], "read")

    def test_a_read_lane_with_rows_reports_them(self):
        block = _ca._sources_block(
            dob_ok=True, trip_days=_ca._LaneResult([{"a": 1}, {"b": 2}], "read"))
        self.assertEqual(block["trip_days"]["count"], 2)

    def test_the_consumer_omits_a_count_it_does_not_know(self):
        js = strip_js_comments(_read(_UI / "travel-doc-lab.js"))
        self.assertIn('typeof s.count === "number"', js)


# ── Gap 4 · provenance and draft rendering ──────────────────────────────

class ProvenanceIsServerOnly(_Base):

    def test_a_client_cannot_forge_a_source_digest(self):
        src = _read(Path(_me.__file__))
        i = src.index("_client_sections = [")
        window = src[i:i + 600]
        self.assertIn('update={"sources": []}', window)

    def test_only_reserved_sections_carry_digests(self):
        cid = self._story("Reviewed and placed.")
        self._review(cid, eras=["adolescence"], source="operator_set")
        sections, status = _me._captured_story_sections(self.narrator)
        self.assertEqual(status, "read")
        self.assertTrue(sections[0].id.startswith(
            _me._RESERVED_STORY_SECTION_PREFIX))
        self.assertEqual(len(sections[0].sources), len(sections[0].items))

    def test_translation_preserves_the_digests(self):
        section = _me.MemoirSection(
            id="captured_stories_adolescence", label="L",
            items=["Una historia."], sources=["abc123def456"])
        req = _me.MemoirExportRequest(
            narrator_name="N", memoir_state="draft", sections=[section])
        out = _me._translate_request_content(req, "es")
        self.assertEqual(out.sections[0].sources, ["abc123def456"])

    def test_the_mapping_is_positional_not_a_bare_list(self):
        """An unordered list proves sources were used; it cannot say
        which paragraph came from which candidate."""
        src = _read(Path(_me.__file__))
        i = src.index("def _stamp_source_provenance")
        window = src[i:i + 1800]
        self.assertIn('f"{sec_id}:{idx}={digest}"', window)
        self.assertIn("core_properties", window)

    def test_no_raw_id_reaches_visible_content(self):
        cid = self._story("Something said.")
        self._review(cid, eras=["adolescence"], source="operator_set")
        sections, _ = _me._captured_story_sections(self.narrator)
        blob = " ".join(sections[0].items) + " " + sections[0].label \
            + " " + sections[0].id
        self.assertNotIn(cid, blob)
        self.assertNotIn(self.narrator, blob)


class EveryExportModeCarriesTheStory(_Base):
    """English threads, English draft, Spanish draft and bilingual draft.

    The draft builders rendered `req.prose` and ignored `req.sections`,
    so the same narrator with the same reviewed stories got them in
    threads state and silently lost them in draft state.
    """

    def setUp(self):
        super().setUp()
        if not _me._DOCX_AVAILABLE:
            self.skipTest("python-docx not installed in this environment")
        cid = self._story("The porch, the peas, the evening cooling off.")
        self._review(cid, eras=["adolescence"], source="operator_set")
        sections, status = _me._captured_story_sections(self.narrator)
        self.assertEqual(status, "read")
        self.story_sections = sections
        self.req = _me.MemoirExportRequest(
            narrator_name="N",
            memoir_state="draft",
            prose="An operator wrote this paragraph.",
            sections=[_me.MemoirSection(
                id="operator_authored", label="Operator section",
                items=["An operator thread item."])] + sections,
        )

    def _text_of(self, blob):
        import io as _io
        from docx import Document as _D
        doc = _D(_io.BytesIO(blob))
        return "\n".join(p.text for p in doc.paragraphs), doc

    def test_english_draft_contains_the_story_once(self):
        text, _ = self._text_of(_me._build_draft_docx(self.req, render_lang="en"))
        self.assertEqual(text.count("The porch, the peas, the evening cooling off."), 1)
        self.assertIn("An operator wrote this paragraph.", text)

    def test_english_threads_contains_the_story_once(self):
        threads = self.req.model_copy(update={"memoir_state": "threads"})
        text, _ = self._text_of(_me._build_threads_docx(threads, render_lang="en"))
        self.assertEqual(text.count("The porch, the peas, the evening cooling off."), 1)

    def test_spanish_draft_contains_the_story_once(self):
        translated = _me._translate_request_content(self.req, "es")
        text, _ = self._text_of(
            _me._build_draft_docx(translated, render_lang="es"))
        # Translation is best-effort and falls back to the source text
        # when the service is unavailable, which is what happens here --
        # the point is that the story is PRESENT exactly once.
        self.assertEqual(text.count("The porch, the peas, the evening cooling off."), 1)

    def test_bilingual_draft_contains_the_story_once(self):
        translated = _me._translate_request_content(self.req, "es")
        text, _ = self._text_of(
            _me._build_draft_docx_bilingual(self.req, translated))
        self.assertEqual(text.count("The porch, the peas, the evening cooling off."), 1)

    def test_operator_prose_is_unchanged_by_the_addition(self):
        text, _ = self._text_of(_me._build_draft_docx(self.req, render_lang="en"))
        self.assertIn("An operator wrote this paragraph.", text)
        prose_at = text.index("An operator wrote this paragraph.")
        story_at = text.index("The porch, the peas, the evening cooling off.")
        self.assertLess(prose_at, story_at,
                        "the narrator's own words follow the operator's prose")

    def test_the_provenance_mapping_survives_into_the_draft_artifact(self):
        _, doc = self._text_of(_me._build_draft_docx(self.req, render_lang="en"))
        comments = doc.core_properties.comments or ""
        self.assertIn("lorevox-story-sources:", comments)
        self.assertIn(":0=", comments)
        self.assertIn(self.story_sections[0].id, comments)

    def test_unreviewed_material_is_absent_from_every_mode(self):
        self._story("Never reviewed at all.")
        sections, _ = _me._captured_story_sections(self.narrator)
        req = self.req.model_copy(update={"sections": sections})
        for name, blob in (
            ("draft", _me._build_draft_docx(req, render_lang="en")),
            ("threads", _me._build_threads_docx(
                req.model_copy(update={"memoir_state": "threads"}),
                render_lang="en")),
        ):
            with self.subTest(mode=name):
                text, _ = self._text_of(blob)
                self.assertNotIn("Never reviewed at all.", text)


if __name__ == "__main__":
    unittest.main()
