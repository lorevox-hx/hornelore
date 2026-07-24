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


class _StubbedDraftCase(unittest.TestCase):
    """Shared stubbing harness. Subclasses may swap in a richer repo /
    outline (WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 extensions)
    WITHOUT inheriting each other's test methods."""

    repo_cls = _FakeRepo
    outline_fn = staticmethod(_fake_outline)

    def setUp(self):
        self._repo = trip_draft.trip_repository
        self._builder = trip_draft.travelogue_builder
        self._llm = trip_draft.llm_interview
        self.fake = self.repo_cls()
        trip_draft.trip_repository = self.fake
        trip_draft.travelogue_builder = types.SimpleNamespace(
            build_travelogue_outline=self.outline_fn)
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


class TripDraftTest(_StubbedDraftCase):

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


# ── WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 extensions ──────────────

class _NestedFakeRepo(_FakeRepo):
    """Adds nested (children) stops: r1 gains s2→s2c; new region r3 gains
    s3→s3c. Nested rows carry trip_region_id=None (stop-attached only) so
    region scope can ONLY reach them through the recursive tree walk."""

    def __init__(self):
        super().__init__()
        self.regions["r3"] = {"id": "r3", "trip_id": _TRIP, "title": "Vienna",
                              "summary": "Two days."}
        self.stops.update({
            "s2": {"id": "s2", "trip_id": _TRIP, "trip_region_id": "r1",
                   "location_name": "Zugspitze", "notes": ""},
            "s2c": {"id": "s2c", "trip_id": _TRIP, "trip_region_id": "r1",
                    "location_name": "Eibsee", "notes": ""},
            "s3c": {"id": "s3c", "trip_id": _TRIP, "trip_region_id": "r3",
                    "location_name": "Grinzing", "notes": ""},
        })
        self.notes += [
            {"id": "n4", "trip_region_id": None, "trip_stop_id": "s2c",
             "source_type": "operator", "include_in_memoir": 1,
             "note_text": "The lake below the cable car was glass-still."},
            {"id": "n5", "trip_region_id": None, "trip_stop_id": "s3c",
             "source_type": "operator", "include_in_memoir": 1,
             "note_text": "Heuriger tavern under the vines."},
        ]
        self.sources += [
            {"id": "src2", "trip_region_id": None, "trip_stop_id": "s2c",
             "title": "Funicular ticket", "summary": "Eibsee funicular "
             "ticket stub.", "pasted_text": "", "include_in_memoir": 0},
        ]

    def trip_tree(self, tid):
        if tid != _TRIP:
            return None
        return {"regions": [
            {"id": "r1", "stops": [
                {"id": "s2", "children": [{"id": "s2c", "children": []}]},
            ]},
            {"id": "r2", "stops": [{"id": "s1"}]},
            {"id": "r3", "stops": [
                {"id": "s3", "children": [{"id": "s3c"}]},
            ]},
        ]}


class NestedStopRegionScopeTest(_StubbedDraftCase):
    """Region scope must include evidence on NESTED child stops (recursive
    walk mirroring travelogue_builder._walk) while still excluding other
    regions' stops — nested or not."""

    repo_cls = _NestedFakeRepo

    def test_nested_child_promoted_note_in_region_scope(self):
        out = trip_draft.draft_section(_TRIP, region_id="r1", preview_only=True)
        ids = {n["id"] for n in out["context_preview"]["notes"]}
        self.assertIn("n4", ids)          # promoted note on nested s2c

    def test_nested_child_selected_source_in_region_scope(self):
        out = trip_draft.draft_section(
            _TRIP, region_id="r1", include_source_ids=["src2"],
            preview_only=True)
        ids = {s["id"] for s in out["context_preview"]["sources"]}
        self.assertIn("src2", ids)        # selected source on nested s2c

    def test_other_regions_nested_stop_evidence_excluded(self):
        out = trip_draft.draft_section(_TRIP, region_id="r1", preview_only=True)
        ctx = out["context_preview"]
        self.assertNotIn("n5", {n["id"] for n in ctx["notes"]})   # r3 nested
        out3 = trip_draft.draft_section(_TRIP, region_id="r3", preview_only=True)
        ids3 = {n["id"] for n in out3["context_preview"]["notes"]}
        self.assertIn("n5", ids3)
        self.assertNotIn("n4", ids3)


class _GroupedRepo(_FakeRepo):
    """Adds base/lodging/transit/memory_anchor stops (grouped block types
    that have no per-stop block in the builder outline)."""

    def __init__(self):
        super().__init__()
        for sid, sname in (("sb", "Pension Prague"), ("sl", "Hotel Munich"),
                           ("st", "Train platform"), ("sm", "Bells at dusk")):
            self.stops[sid] = {"id": sid, "trip_id": _TRIP,
                               "trip_region_id": "r2",
                               "location_name": sname, "notes": ""}

    def trip_tree(self, tid):
        if tid != _TRIP:
            return None
        return {"regions": [
            {"id": "r1", "stops": []},
            {"id": "r2", "stops": [{"id": "s1"}, {"id": "sb"}, {"id": "sl"},
                                   {"id": "st"}, {"id": "sm"}]},
        ]}


_GPS_VALUE = "coordinates recorded — not shown; reverse geocode available"


def _fake_outline_grouped(trip_id):
    """Builder outline with per-stop evidence entries: block["stops"] on the
    itinerary tile, block["memory_anchor_stops"] on the sensory coda —
    exactly the key names the production builder emits."""
    return {
        "blocks": [
            {"block_type": "itinerary_tile", "region_id": "r2",
             "prose_anchors": [
                 {"label": "base stop (operator)",
                  "value": "Pension Prague — 2026-05-01 to 2026-05-05"},
             ],
             "stops": [
                 {"stop_id": "sb", "prose_anchors": [
                     {"label": "base stop (operator)",
                      "value": "Pension Prague — 2026-05-01 to 2026-05-05"},
                     {"label": "approved caption",
                      "value": "Our little room under the roof"},
                     {"label": "GPS (private)", "value": _GPS_VALUE},
                 ]},
                 {"stop_id": "sl", "prose_anchors": [
                     {"label": "lodging stop (operator)",
                      "value": "Hotel Munich"},
                     {"label": "approved operator note",
                      "value": "Breakfast room overlooked the courtyard."},
                 ]},
                 {"stop_id": "st", "prose_anchors": [
                     {"label": "transit stop (operator)",
                      "value": "Train platform"},
                     {"label": "approved public context (public web context)",
                      "value": "The station hall dates to 1871."},
                 ]},
             ]},
            {"block_type": "sensory_coda", "region_id": None,
             "prose_anchors": [
                 {"label": "memory anchor (operator)",
                  "value": "Bells at dusk"},
             ],
             "memory_anchor_stops": [
                 {"stop_id": "sm", "prose_anchors": [
                     {"label": "memory anchor (operator)",
                      "value": "Bells at dusk"},
                     {"label": "narrator memory (promoted Lori capture)",
                      "value": "The bells echoed over the empty square."},
                 ]},
             ]},
        ],
    }


class GroupedStopScopeTest(_StubbedDraftCase):
    """Stop scope for base/lodging/transit/memory_anchor stops collects the
    builder's per-stop evidence entries; the "GPS (private)" placeholder
    never becomes evidence."""

    repo_cls = _GroupedRepo
    outline_fn = staticmethod(_fake_outline_grouped)

    def _anchors(self, stop_id):
        out = trip_draft.draft_section(_TRIP, stop_id=stop_id,
                                       preview_only=True)
        return out["context_preview"]["anchors"]

    def test_base_stop_scope_has_approved_photo_caption(self):
        values = [a["value"] for a in self._anchors("sb")]
        self.assertIn("Our little room under the roof", values)
        self.assertIn("Pension Prague — 2026-05-01 to 2026-05-05", values)

    def test_lodging_stop_scope_has_approved_operator_photo_context(self):
        values = [a["value"] for a in self._anchors("sl")]
        self.assertIn("Breakfast room overlooked the courtyard.", values)

    def test_transit_stop_scope_has_public_context(self):
        anchors = self._anchors("st")
        by_label = {a["label"]: a for a in anchors}
        self.assertIn("approved public context (public web context)", by_label)
        self.assertFalse(
            by_label["approved public context (public web context)"]["draft"])

    def test_memory_anchor_stop_scope_has_curated_anchors(self):
        values = [a["value"] for a in self._anchors("sm")]
        self.assertIn("The bells echoed over the empty square.", values)
        self.assertIn("Bells at dusk", values)

    def test_gps_placeholder_never_enters_evidence(self):
        labels = [a["label"] for a in self._anchors("sb")]
        self.assertNotIn("GPS (private)", labels)
        trip_draft.draft_section(_TRIP, stop_id="sb", instruction="x")
        self.assertEqual(len(self.llm_calls), 1)
        ev = self.llm_calls[0]["evidence"]
        self.assertNotIn("coordinates recorded", ev)
        self.assertNotIn("GPS (private)", ev)


class SentinelLineAwareTest(_StubbedDraftCase):
    """MODSAVE sentinel LINES are stripped from WITHIN values — a real
    summary sharing a value with a sentinel keeps the real text."""

    def test_sentinel_line_stripped_real_text_kept(self):
        self.fake.regions["r1"]["summary"] = \
            "Real operator summary.\nMODSAVE-12345"
        out = trip_draft.draft_section(_TRIP, region_id="r1",
                                       preview_only=True)
        self.assertEqual(out["context_preview"]["summary"],
                         "Real operator summary.")

    def test_sentinel_only_value_still_dropped(self):
        out = trip_draft.draft_section(_TRIP, region_id="r1",
                                       preview_only=True)
        self.assertEqual(out["context_preview"]["summary"], "")


class DraftSectionEndpointTest(_StubbedDraftCase):
    """/draft-section behavior (router fn, real llm_interview shim):
    preview makes no LLM call and no writes; draft makes exactly ONE
    raw-ephemeral LLM call with no conversation id and no writes; the raw
    drafting system prompt carries the transport/arrival prohibition; Keep
    stays outside the endpoint."""

    def setUp(self):
        super().setUp()
        import os
        from api import llm_interview as real_llm
        from api.routers import trips as trips_router
        self.trips = trips_router
        self._flag = os.environ.get("HORNELORE_TRIPS")
        os.environ["HORNELORE_TRIPS"] = "1"

        # Route through the REAL draft_travel_section, stubbing only the
        # chat boundary (_try_call_llm) so prompt_mode/conv_id are observable.
        self.try_calls = []

        def _fake_try(system_prompt, user_prompt, **kw):
            self.try_calls.append({"system": system_prompt,
                                   "user": user_prompt, **kw})
            return "A drafted paragraph."
        self._orig_try = real_llm._try_call_llm
        real_llm._try_call_llm = _fake_try
        trip_draft.llm_interview = real_llm
        self.real_llm = real_llm

    def tearDown(self):
        import os
        self.real_llm._try_call_llm = self._orig_try
        if self._flag is None:
            os.environ.pop("HORNELORE_TRIPS", None)
        else:
            os.environ["HORNELORE_TRIPS"] = self._flag
        super().tearDown()

    def _req(self, **kw):
        base = {"trip_region_id": None, "trip_stop_id": None,
                "instruction": None, "include_note_ids": None,
                "include_source_ids": None, "preview_only": False}
        base.update(kw)
        return types.SimpleNamespace(**base)

    def test_preview_no_llm_call_no_writes(self):
        before_notes = len(self.fake.notes)
        before_sources = len(self.fake.sources)
        out = self.trips.draft_section(
            _TRIP, self._req(trip_region_id="r2", preview_only=True))
        self.assertEqual(out["status"], "preview")
        self.assertIsNone(out["draft"])
        self.assertEqual(self.try_calls, [])
        self.assertEqual(len(self.fake.notes), before_notes)
        self.assertEqual(len(self.fake.sources), before_sources)

    def test_draft_one_raw_ephemeral_call_no_writes(self):
        before_notes = len(self.fake.notes)
        before_sources = len(self.fake.sources)
        out = self.trips.draft_section(
            _TRIP, self._req(trip_region_id="r2", instruction="Warm."))
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["draft"], "A drafted paragraph.")
        self.assertEqual(len(self.try_calls), 1)
        call = self.try_calls[0]
        self.assertEqual(call.get("prompt_mode"), "raw_ephemeral")
        self.assertFalse(call.get("conv_id"))          # no conversation id
        # note/source counts unchanged; _FakeRepo.location_note_create
        # would raise on any Keep attempt — Keep stays outside the endpoint
        self.assertEqual(len(self.fake.notes), before_notes)
        self.assertEqual(len(self.fake.sources), before_sources)

    def test_raw_system_prompt_carries_transport_prohibition(self):
        self.trips.draft_section(_TRIP, self._req(trip_region_id="r2"))
        system = self.try_calls[0]["system"]
        self.assertIn("no trains, stations, airports, flights, cars, buses, "
                      "or walking", system)
        self.assertIn("Do not invent weather", system)
        self.assertIn("write FEWER sentences", system)


if __name__ == "__main__":
    unittest.main(verbosity=2)
