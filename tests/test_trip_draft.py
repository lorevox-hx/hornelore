"""WO-TRAVEL-DOC-OPERATOR-DRAFT-ASSISTANT-01 — trip_draft functional tests.

Stubs the repository, travelogue builder, and LLM so we can assert the
assembly rules without a DB or a model:
  - scope resolution + cross-trip rejection,
  - approved-only anchors (draft-labeled excluded, counted),
  - MODSAVE sentinel skipped,
  - notes/sources scoping + include_* filters,
  - preview_only makes no LLM call,
  - no_material short-circuits,
  - draft returns text and NEVER persists.
"""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api.services import trip_draft  # noqa: E402

_TRIP = "trip-1"


class _FakeRepo:
    def __init__(self):
        self.regions = {
            "r1": {"id": "r1", "trip_id": _TRIP, "title": "Germany/Bavaria",
                   "summary": "MODSAVE-1783558649763"},   # sentinel summary
            "r2": {"id": "r2", "trip_id": _TRIP, "title": "Prague",
                   "summary": "Old town, five days."},
            "rX": {"id": "rX", "trip_id": "other-trip", "title": "Nope",
                   "summary": "x"},
        }
        self.stops = {
            "s1": {"id": "s1", "trip_id": _TRIP, "trip_region_id": "r2",
                   "location_name": "Charles Bridge", "notes": "at dawn"},
        }
        self.trips = {_TRIP: {"id": _TRIP, "title": "Spring 2026",
                              "summary": "Central Europe."}}
        self.notes = [
            {"id": "n1", "trip_region_id": "r2", "trip_stop_id": None,
             "source_type": "operator", "include_in_memoir": 1,
             "note_text": "The bridge was quiet before the crowds."},
            {"id": "n2", "trip_region_id": "r1", "trip_stop_id": None,
             "source_type": "lori", "include_in_memoir": 0,
             "note_text": "Beer hall the first night."},
            {"id": "n3", "trip_region_id": "r2", "trip_stop_id": "s1",
             "source_type": "operator", "include_in_memoir": 0,
             "note_text": "Statues along the parapet."},
        ]
        self.sources = [
            {"id": "src1", "trip_region_id": "r2", "trip_stop_id": None,
             "title": "Wikipedia", "summary": "Charles Bridge is a medieval "
             "bridge.", "pasted_text": "", "include_in_memoir": 1},
        ]

    def trip_tree(self, tid):
        if tid != _TRIP:
            return None
        return {"regions": [
            {"id": "r1", "stops": []},
            {"id": "r2", "stops": [{"id": "s1"}]},
        ]}

    def region_get(self, rid):
        return self.regions.get(rid)

    def stop_get(self, sid):
        return self.stops.get(sid)

    def trip_get(self, tid):
        return self.trips.get(tid)

    def location_notes_list(self, tid):
        return list(self.notes)

    def sources_list(self, tid):
        return list(self.sources)

    # Guard: if the draft path ever tries to persist, blow up loudly.
    def location_note_create(self, *a, **k):
        raise AssertionError("draft_section must NEVER persist")


def _fake_outline(trip_id):
    # Region r2 has one approved anchor and one draft anchor; r1 none.
    return {
        "blocks": [
            {"block_type": "region_chapter", "region_id": "r2", "stop_id": None,
             "prose_anchors": [
                 {"label": "approved place", "value": "Prague, Czechia"},
                 {"label": "photo context (draft)", "value": "a blurry sign"},
             ]},
            {"block_type": "discovery_tile", "region_id": "r2", "stop_id": "s1",
             "prose_anchors": [
                 {"label": "approved caption", "value": "Charles Bridge at dawn"},
             ]},
            {"block_type": "region_chapter", "region_id": "r1", "stop_id": None,
             "prose_anchors": []},
        ],
    }


class TripDraftTest(unittest.TestCase):
    def setUp(self):
        self._repo = trip_draft.trip_repository
        self._builder = trip_draft.travelogue_builder
        self._llm = trip_draft.llm_interview
        self.fake = _FakeRepo()
        trip_draft.trip_repository = self.fake
        trip_draft.travelogue_builder = types.SimpleNamespace(
            build_travelogue_outline=_fake_outline)
        self.llm_calls = []

        def _fake_draft(*, scope_title, instruction, evidence_text, max_new=None):
            self.llm_calls.append(
                {"scope": scope_title, "instruction": instruction,
                 "evidence": evidence_text})
            return "A warm paragraph about " + scope_title + "."
        trip_draft.llm_interview = types.SimpleNamespace(
            draft_travel_section=_fake_draft)

    def tearDown(self):
        trip_draft.trip_repository = self._repo
        trip_draft.travelogue_builder = self._builder
        trip_draft.llm_interview = self._llm

    # ── scope resolution ────────────────────────────────────────────────
    def test_cross_trip_scope_rejected(self):
        self.assertIsNone(trip_draft.draft_section(_TRIP, region_id="rX"))

    def test_unknown_scope_rejected(self):
        self.assertIsNone(trip_draft.draft_section(_TRIP, stop_id="nope"))

    # ── anchors: draft kept-but-flagged + sentinel skip ─────────────────
    def test_region_preview_keeps_draft_anchor_flagged(self):
        out = trip_draft.draft_section(_TRIP, region_id="r2", preview_only=True)
        ctx = out["context_preview"]
        by_label = {a["label"]: a for a in ctx["anchors"]}
        self.assertIn("approved place", by_label)
        self.assertIn("approved caption", by_label)   # from the stop tile in r2
        self.assertIn("photo context (draft)", by_label)   # kept, not excluded
        self.assertFalse(by_label["approved place"]["draft"])
        self.assertTrue(by_label["photo context (draft)"]["draft"])
        self.assertEqual(ctx["draft_anchor_count"], 1)
        self.assertEqual(self.llm_calls, [])          # preview makes no LLM call

    def test_sentinel_summary_excluded(self):
        out = trip_draft.draft_section(_TRIP, region_id="r1", preview_only=True)
        self.assertEqual(out["context_preview"]["summary"], "")  # MODSAVE dropped

    # ── notes/sources: promoted-by-default, unpromoted only if selected ──
    def test_region_default_only_promoted_notes(self):
        out = trip_draft.draft_section(_TRIP, region_id="r2", preview_only=True)
        ctx = out["context_preview"]
        # n1 is promoted (in); n3 is an unpromoted stop note (out by default)
        self.assertEqual({n["id"] for n in ctx["notes"]}, {"n1"})
        self.assertEqual(len(ctx["sources"]), 1)      # src1 is promoted

    def test_unpromoted_note_included_only_when_selected(self):
        out = trip_draft.draft_section(
            _TRIP, region_id="r2", include_note_ids=["n3"], preview_only=True)
        self.assertEqual({n["id"] for n in out["context_preview"]["notes"]},
                         {"n1", "n3"})               # promoted n1 + selected n3

    def test_stop_scope_unpromoted_absent_by_default(self):
        out = trip_draft.draft_section(_TRIP, stop_id="s1", preview_only=True)
        self.assertEqual(out["context_preview"]["notes"], [])   # n3 unpromoted
        out2 = trip_draft.draft_section(
            _TRIP, stop_id="s1", include_note_ids=["n3"], preview_only=True)
        self.assertEqual({n["id"] for n in out2["context_preview"]["notes"]},
                         {"n3"})

    # ── draft path ──────────────────────────────────────────────────────
    def test_draft_returns_text_and_calls_llm(self):
        out = trip_draft.draft_section(
            _TRIP, region_id="r2", instruction="Warm and short.")
        self.assertEqual(out["status"], "ok")
        self.assertTrue(out["draft"].startswith("A warm paragraph"))
        self.assertEqual(len(self.llm_calls), 1)
        # evidence actually carried the approved anchor + a note + a source
        ev = self.llm_calls[0]["evidence"]
        self.assertIn("Prague, Czechia", ev)
        self.assertIn("bridge was quiet", ev)
        self.assertIn("Wikipedia", ev)
        # draft evidence must be presented suggestively, not as fact (#5)
        self.assertIn("Approved evidence", ev)
        self.assertIn("Draft evidence", ev)
        self.assertIn("write suggestively", ev.lower())

    def test_no_material_short_circuits(self):
        # r1 has sentinel summary (dropped), no approved anchors, one lori note.
        # Remove its note to make it genuinely empty.
        self.fake.notes = [n for n in self.fake.notes if n["id"] != "n2"]
        out = trip_draft.draft_section(_TRIP, region_id="r1")
        self.assertEqual(out["status"], "no_material")
        self.assertIsNone(out["draft"])
        self.assertEqual(self.llm_calls, [])

    def test_never_persists(self):
        # The fake repo raises if location_note_create is called.
        trip_draft.draft_section(_TRIP, region_id="r2", instruction="x")
        # (no assertion needed — _FakeRepo.location_note_create would raise)


if __name__ == "__main__":
    unittest.main(verbosity=2)
