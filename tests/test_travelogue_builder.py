"""WO-TRAVEL-DOC-EVIDENCE-RICH-TRAVELOGUE-01 — travelogue outline builder,
public-context lane, reverse-geocode structure, and modal public-context
wording.

Locked doctrine under test: Travel Doc mode is EVIDENCE-RICH — all four
block types render from labeled evidence anchors with provenance; draft
evidence stays suggestive ("suggests"), approved evidence speaks plainly
("The approved Travel Doc context says…"); unpromoted sandbox notes NEVER
enter blocks (intake_review only, no auto-promotion); raw GPS and
upload/save/modified timestamps never reach the outline.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import types
import unittest
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

# ── offline fastapi/pydantic stubs (shared shape with test_trip_patch) ──
if "fastapi" not in sys.modules:
    stub = types.ModuleType("fastapi")

    class _APIRouter:
        def __init__(self, *a, **k):
            pass

        def _deco(self, *a, **k):
            def wrap(f):
                return f
            return wrap
        get = post = patch = delete = put = _deco

    class _HTTPException(Exception):
        def __init__(self, status_code=0, detail=""):
            self.status_code, self.detail = status_code, detail
            super().__init__(detail)

    stub.APIRouter = _APIRouter
    stub.HTTPException = _HTTPException
    stub.Query = lambda default=None, **k: default
    stub.File = lambda default=None, **k: default
    stub.Form = lambda default=None, **k: default
    stub.UploadFile = object
    sys.modules["fastapi"] = stub

if "pydantic" not in sys.modules:
    pstub = types.ModuleType("pydantic")

    class _BaseModel:
        pass

    pstub.BaseModel = _BaseModel
    pstub.Field = lambda default=None, **k: default
    pstub.field_validator = lambda *a, **k: (lambda f: f)
    pstub.validator = lambda *a, **k: (lambda f: f)
    pstub.ConfigDict = dict
    sys.modules["pydantic"] = pstub

from fastapi import HTTPException  # noqa: E402
from api import db as _db  # noqa: E402
from api.services import trip_repository  # noqa: E402
from api.services import travelogue_builder  # noqa: E402
from api.services import travel_doc_lori_modal as modal  # noqa: E402
from api.routers import trips  # noqa: E402


class _Req:
    """Plain request object for router fns (pydantic stub is attr-only)."""

    def __init__(self, **kw):
        self.result_summary = None
        self.source_type = "public_web_context"
        self.trip_region_id = None
        self.trip_stop_id = None
        self.photo_link_id = None
        self.query = None
        self.source_url = None
        self.confidence = "draft"
        self.notes = None
        self.approved_for_lori = None
        self.include_in_memoir = None
        self.__dict__.update(kw)


def _insert_photo(con, photo_id, person_id, **overrides):
    cols = {r[1] for r in con.execute("PRAGMA table_info(photos)")}
    values = {
        "id": photo_id,
        "narrator_id": person_id,
        "image_path": "/tmp/%s.jpg" % photo_id,
        "file_hash": "hash-%s" % photo_id,
        "narrator_ready": 1,
        "date_value": None,
        "date_precision": "unknown",
        "date_source": "unknown",
        "taken_at_filename_guess": None,
        "location_label": None,
        "date_approved_for_lori": 0,
        "location_approved_for_lori": 0,
        "latitude": None,
        "longitude": None,
    }
    values.update(overrides)
    used = [c for c in values if c in cols]
    con.execute(
        "INSERT INTO photos (" + ", ".join(used) + ") VALUES (" +
        ", ".join(["?"] * len(used)) + ")",
        [values[c] for c in used],
    )


class _TravelogueFixture(unittest.TestCase):
    """Two-region Spring 2026 trip with every stop type, two photos
    (EXIF vs filename-guess), promoted + unpromoted notes, and a second
    trip for cross-trip scope rejection."""

    def setUp(self):
        self._tmpdb = tempfile.NamedTemporaryFile(suffix=".sqlite3",
                                                  delete=False)
        self._tmpdb.close()
        self.db_path = Path(self._tmpdb.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()
        self._orig_trips_flag = os.environ.get("HORNELORE_TRIPS")
        os.environ["HORNELORE_TRIPS"] = "1"
        self._orig_geocode = os.environ.pop("HORNELORE_GEOCODE_CMD", None)

        self.person_id = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO people (id, display_name, date_of_birth, "
            "created_at, updated_at) VALUES (?, 'Travelogue Test', "
            "'1962-12-24', '2026-07-09', '2026-07-09');",
            (self.person_id,))
        con.commit()
        con.close()

        self.trip_id = trip_repository.trip_create(
            self.person_id, "Spring 2026 Central Europe",
            start_date="2026-05-22", end_date="2026-06-13",
            summary="Three weeks across Bavaria and Bohemia.")
        self.region_de = trip_repository.region_create(
            self.trip_id, "Germany", ord_=0, country_or_area="Germany",
            start_date="2026-05-22", end_date="2026-05-28",
            summary="First leg — flew into Munich.")
        self.region_cz = trip_repository.region_create(
            self.trip_id, "Czechia", ord_=1, country_or_area="Czechia")

        # Germany stops: base + transit + sight (+day_trip child) + meal
        # + memory_anchor. Czechia: lodging.
        self.stop_base = trip_repository.stop_create(
            self.trip_id, self.region_de, "Hotel Munich",
            stop_type="base", ord_=0,
            date_start="2026-05-22", date_end="2026-05-28")
        self.stop_transit = trip_repository.stop_create(
            self.trip_id, self.region_de, "Train to Prague",
            stop_type="transit", ord_=1, date_start="2026-05-28")
        self.stop_sight = trip_repository.stop_create(
            self.trip_id, self.region_de, "Marienplatz",
            stop_type="sight", ord_=2, date_start="2026-05-23",
            notes="Glockenspiel at noon")
        self.stop_daytrip = trip_repository.stop_create(
            self.trip_id, self.region_de, "Nymphenburg",
            stop_type="day_trip", ord_=0,
            parent_trip_stop_id=self.stop_sight)
        self.stop_meal = trip_repository.stop_create(
            self.trip_id, self.region_de, "Hofbrauhaus",
            stop_type="meal", ord_=3)
        self.stop_anchor = trip_repository.stop_create(
            self.trip_id, self.region_de, "Bells at dusk",
            stop_type="memory_anchor", ord_=4,
            notes="church bells across the square")
        self.stop_lodging = trip_repository.stop_create(
            self.trip_id, self.region_cz, "Pension Prague",
            stop_type="lodging", ord_=0)

        con = sqlite3.connect(str(self.db_path))
        _insert_photo(con, "p_exif", self.person_id,
                      date_value="2026-05-23", date_source="exif",
                      location_label="Munich area",
                      latitude=48.137154, longitude=11.576124)
        _insert_photo(con, "p_fname", self.person_id,
                      taken_at_filename_guess="2026-05-24",
                      date_source="filename_guess")
        con.commit()
        con.close()

        self.link_exif = trip_repository.photo_link_upsert(
            self.trip_id, "p_exif", trip_region_id=self.region_de,
            trip_stop_id=self.stop_sight, assignment_method="operator")
        trip_repository.photo_link_update(
            self.link_exif,
            caption="Outside the Glockenspiel",
            caption_approved_for_lori=True,
            operator_context_note="Street musicians were playing nearby.",
            operator_context_approved_for_lori=True)
        self.link_fname = trip_repository.photo_link_upsert(
            self.trip_id, "p_fname", trip_region_id=self.region_de,
            trip_stop_id=self.stop_sight, assignment_method="operator")
        trip_repository.photo_link_update(
            self.link_fname, caption="Second morning walk")  # unapproved

        # Notes: promoted stop / region / floating; unpromoted modal
        # sandbox; promoted modal capture linked to the EXIF photo.
        self.note_stop = trip_repository.location_note_create(
            self.trip_id, "The square was packed for the noon chimes.",
            trip_region_id=self.region_de, trip_stop_id=self.stop_sight,
            source_type="operator", include_in_memoir=True)
        self.note_region = trip_repository.location_note_create(
            self.trip_id, "Germany felt like the real start of the trip.",
            trip_region_id=self.region_de,
            source_type="operator", include_in_memoir=True)
        self.note_floating = trip_repository.location_note_create(
            self.trip_id, "What stayed with me was the evening light.",
            source_type="operator", include_in_memoir=True)
        self.note_sandbox = trip_repository.location_note_create(
            self.trip_id, "sandbox: the fish at the market was enormous",
            trip_region_id=self.region_de, trip_stop_id=self.stop_sight,
            source_type="lori", source_surface="travel_doc_modal",
            source_turn_ref="modal_turn:conv1:t1")
        self.note_modal_promoted = trip_repository.location_note_create(
            self.trip_id, "I remember men in lederhosen by the museum.",
            trip_region_id=self.region_de, trip_stop_id=self.stop_sight,
            source_type="lori", source_surface="travel_doc_modal",
            source_turn_ref="modal_turn:conv1:t2",
            photo_link_id=self.link_exif, include_in_memoir=True)

        # Second trip (same narrator) for cross-trip rejection.
        self.trip2_id = trip_repository.trip_create(
            self.person_id, "Italy 2025")
        self.region2_id = trip_repository.region_create(
            self.trip2_id, "Tuscany")
        self.stop2_id = trip_repository.stop_create(
            self.trip2_id, self.region2_id, "Florence")
        con = sqlite3.connect(str(self.db_path))
        _insert_photo(con, "p_other", self.person_id)
        con.commit()
        con.close()
        self.link_other_trip = trip_repository.photo_link_upsert(
            self.trip2_id, "p_other", trip_region_id=self.region2_id,
            trip_stop_id=self.stop2_id, assignment_method="operator")

    def tearDown(self):
        _db.DB_PATH = self._orig_db
        if self._orig_trips_flag is None:
            os.environ.pop("HORNELORE_TRIPS", None)
        else:
            os.environ["HORNELORE_TRIPS"] = self._orig_trips_flag
        if self._orig_geocode is not None:
            os.environ["HORNELORE_GEOCODE_CMD"] = self._orig_geocode
        else:
            os.environ.pop("HORNELORE_GEOCODE_CMD", None)
        try:
            self.db_path.unlink()
        except OSError:
            pass

    # ── helpers ─────────────────────────────────────────────────────────

    def _outline(self):
        out = travelogue_builder.build_travelogue_outline(self.trip_id)
        self.assertIsNotNone(out)
        return out

    def _blocks(self, kind=None, outline=None):
        blocks = (outline or self._outline())["blocks"]
        if kind:
            return [b for b in blocks if b["block_type"] == kind]
        return blocks

    def _discovery(self, title, outline=None):
        for b in self._blocks("discovery_tile", outline):
            if b.get("title") == title:
                return b
        self.fail("no discovery tile titled %r" % title)

    def _add_public(self, **kw):
        return trips.create_public_context(self.trip_id, _Req(**kw))


class BlockShapeTest(_TravelogueFixture):
    def test_outline_returns_all_four_block_types(self):
        kinds = {b["block_type"] for b in self._blocks()}
        self.assertEqual(
            kinds, {"region_chapter", "itinerary_tile", "discovery_tile",
                    "sensory_coda"})

    def test_regions_become_region_chapters_in_order(self):
        chapters = self._blocks("region_chapter")
        self.assertEqual([c["title"] for c in chapters],
                         ["Germany", "Czechia"])

    def test_base_lodging_transit_go_to_itinerary_tiles(self):
        tiles = self._blocks("itinerary_tile")
        names = [s["location_name"] for t in tiles for s in t["stops"]]
        self.assertIn("Hotel Munich", names)
        self.assertIn("Train to Prague", names)
        self.assertIn("Pension Prague", names)
        types_seen = {s["stop_type"] for t in tiles for s in t["stops"]}
        self.assertTrue(types_seen <= {"base", "lodging", "transit"},
                        types_seen)

    def test_sight_meal_day_trip_get_discovery_tiles(self):
        titles = {b["title"] for b in self._blocks("discovery_tile")}
        self.assertIn("Marienplatz", titles)
        self.assertIn("Hofbrauhaus", titles)
        self.assertIn("Nymphenburg", titles)  # child day_trip stop
        self.assertNotIn("Hotel Munich", titles)
        self.assertNotIn("Bells at dusk", titles)

    def test_memory_anchor_stops_in_sensory_coda(self):
        coda = self._blocks("sensory_coda")[0]
        names = [s["location_name"] for s in coda["memory_anchor_stops"]]
        self.assertIn("Bells at dusk", names)

    def test_floating_promoted_note_in_sensory_coda(self):
        coda = self._blocks("sensory_coda")[0]
        texts = [n["note_text"] for n in coda["floating_notes"]]
        self.assertIn("What stayed with me was the evening light.", texts)

    def test_overview_counts(self):
        ov = self._outline()["overview"]
        self.assertEqual(ov["title"], "Spring 2026 Central Europe")
        self.assertEqual(ov["region_count"], 2)
        self.assertEqual(ov["stop_count"], 7)
        self.assertEqual(ov["photo_count"], 2)
        self.assertEqual(ov["sandbox_note_count"], 1)
        self.assertGreater(ov["approved_evidence_count"], 0)
        self.assertGreater(ov["draft_evidence_count"], 0)


class PhotoEvidenceTest(_TravelogueFixture):
    def test_packet_carries_exif_filename_caption_context(self):
        tile = self._discovery("Marienplatz")
        pks = {p["photo_id"]: p for p in tile["photos"]}
        exif = pks["p_exif"]
        self.assertEqual(exif["draft_date"], "2026-05-23")
        self.assertEqual(exif["date_source"], "exif")
        self.assertEqual(exif["approved_caption"], "Outside the Glockenspiel")
        self.assertEqual(exif["approved_context"],
                         "Street musicians were playing nearby.")
        self.assertTrue(exif["raw_gps_available"])
        self.assertEqual(exif["thumbnail_path"], "/api/photos/p_exif/thumb")
        fname = pks["p_fname"]
        self.assertEqual(fname["filename_guess"], "2026-05-24")
        self.assertEqual(fname["draft_date"], "2026-05-24")
        self.assertEqual(fname["draft_context"], "Second morning walk")

    def test_draft_date_labeled_draft_and_flags_review(self):
        tile = self._discovery("Marienplatz")
        labels = {a["label"]: a["value"] for a in tile["prose_anchors"]}
        self.assertEqual(labels.get("EXIF date (draft)"), "2026-05-23")
        self.assertEqual(labels.get("filename date guess (draft)"),
                         "2026-05-24")
        self.assertTrue(tile["needs_review"])
        self.assertIn("draft", tile["provenance_badges"])
        self.assertIn("EXIF", tile["provenance_badges"])

    def test_approved_date_labeled_approved(self):
        con = sqlite3.connect(str(self.db_path))
        con.execute("UPDATE photos SET date_approved_for_lori=1 "
                    "WHERE id='p_exif'")
        con.commit()
        con.close()
        tile = self._discovery("Marienplatz")
        labels = {a["label"]: a["value"] for a in tile["prose_anchors"]}
        self.assertEqual(labels.get("approved taken date"), "2026-05-23")
        self.assertNotIn("EXIF date (draft)", labels)

    def test_no_raw_gps_or_upload_dates_in_outline_json(self):
        dumped = json.dumps(self._outline())
        self.assertNotIn("48.137", dumped)
        self.assertNotIn("11.576", dumped)
        self.assertNotIn('"latitude"', dumped)
        self.assertNotIn('"longitude"', dumped)
        self.assertNotIn("uploaded_at", dumped)

    def test_builder_source_never_reads_upload_save_modified_dates(self):
        src = (_SERVER_CODE / "api" / "services" /
               "travelogue_builder.py").read_text(encoding="utf-8")
        for forbidden in ("uploaded_at", "file_saved_at",
                          "file_modified_at", "upload_date"):
            self.assertNotIn(forbidden, src)
        # Taken dates come only from the reviewed photo date fields.
        self.assertIn("photo_date_source", src)
        # The builder must not touch link/photo row timestamps as dates.
        self.assertNotIn('l.get("created_at")', src)
        self.assertNotIn('link.get("created_at")', src)


class PublicContextTest(_TravelogueFixture):
    def test_trip_level_public_context_in_overview(self):
        self._add_public(
            result_summary="Pentecost Monday was a public holiday in "
                           "Bavaria that week.",
            source_type="calendar_context")
        ov = self._outline()["overview"]
        self.assertEqual(ov["public_context_count"], 1)
        self.assertIn("Pentecost Monday",
                      ov["public_context"][0]["result_summary"])
        self.assertEqual(ov["public_context"][0]["source_type"],
                         "calendar_context")

    def test_region_public_context_in_region_chapter(self):
        self._add_public(
            result_summary="Bavaria's beer gardens date to royal brewing "
                           "licenses.",
            source_type="place_context", trip_region_id=self.region_de)
        chapter = [c for c in self._blocks("region_chapter")
                   if c["title"] == "Germany"][0]
        self.assertEqual(len(chapter["public_context"]), 1)
        self.assertIn("beer gardens",
                      chapter["public_context"][0]["result_summary"])
        labels = [a["label"] for a in chapter["prose_anchors"]]
        self.assertTrue(any("public context (draft" in l for l in labels))
        self.assertTrue(chapter["needs_review"])

    def test_stop_food_context_in_discovery_tile(self):
        self._add_public(
            result_summary="Weisswurst is a Munich breakfast tradition.",
            source_type="food_context", trip_stop_id=self.stop_meal)
        tile = self._discovery("Hofbrauhaus")
        self.assertIn("Weisswurst",
                      tile["public_context"][0]["result_summary"])

    def test_photo_scoped_public_context_reaches_its_stop_tile(self):
        self._add_public(
            result_summary="The Glockenspiel plays daily at 11 and noon.",
            source_type="public_web_context",
            photo_link_id=self.link_exif)
        tile = self._discovery("Marienplatz")
        self.assertTrue(any("Glockenspiel plays" in
                            (p["result_summary"] or "")
                            for p in tile["public_context"]))

    def test_cross_trip_stop_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            self._add_public(result_summary="x",
                             trip_stop_id=self.stop2_id)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_cross_trip_region_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            self._add_public(result_summary="x",
                             trip_region_id=self.region2_id)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_cross_trip_photo_link_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            self._add_public(result_summary="x",
                             photo_link_id=self.link_other_trip)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_invalid_source_type_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            self._add_public(result_summary="x", source_type="cloud_llm")
        self.assertEqual(ctx.exception.status_code, 422)

    def test_patch_approves_and_edit_revokes(self):
        out = self._add_public(result_summary="Original summary.")
        cid = out["context_id"]
        trips.patch_public_context(cid, _Req(approved_for_lori=True))
        self.assertTrue(
            trip_repository.public_context_get(cid)["approved_for_lori"])
        # Editing the summary without re-approving revokes approval.
        trips.patch_public_context(cid, _Req(result_summary="Edited."))
        row = trip_repository.public_context_get(cid)
        self.assertEqual(row["result_summary"], "Edited.")
        self.assertFalse(row["approved_for_lori"])

    def test_delete_public_context(self):
        out = self._add_public(result_summary="temp")
        trips.delete_public_context(out["context_id"])
        self.assertIsNone(
            trip_repository.public_context_get(out["context_id"]))


class NotesRoutingTest(_TravelogueFixture):
    def test_sandbox_modal_capture_in_intake_review(self):
        intake = self._outline()["intake_review"]
        texts = [n["note_text"] for n in intake["notes"]]
        self.assertIn("sandbox: the fish at the market was enormous",
                      texts)
        badge = [n["badge"] for n in intake["notes"]
                 if n["note_text"].startswith("sandbox:")][0]
        self.assertEqual(badge, "Lori modal capture")

    def test_unpromoted_never_inside_main_blocks(self):
        dumped = json.dumps(self._blocks())
        self.assertNotIn("sandbox: the fish at the market", dumped)

    def test_promoted_notes_land_in_the_right_block(self):
        tile = self._discovery("Marienplatz")
        texts = [n["note_text"] for n in tile["notes"]]
        self.assertIn("The square was packed for the noon chimes.", texts)
        chapter = [c for c in self._blocks("region_chapter")
                   if c["title"] == "Germany"][0]
        rtexts = [n["note_text"] for n in chapter["notes"]]
        self.assertIn("Germany felt like the real start of the trip.",
                      rtexts)

    def test_photo_linked_promoted_capture_under_its_discovery_tile(self):
        tile = self._discovery("Marienplatz")
        entry = [n for n in tile["notes"]
                 if n["note_text"].startswith("I remember men in "
                                              "lederhosen")]
        self.assertEqual(len(entry), 1)
        self.assertEqual(entry[0]["photo_link_id"], self.link_exif)
        self.assertEqual(entry[0]["badge"], "Lori modal capture")

    def test_no_auto_promotion(self):
        # Building the outline must not flip any flags.
        self._outline()
        row = trip_repository.location_note_get(self.note_sandbox)
        self.assertEqual(row["include_in_memoir"], 0)
        self.assertEqual(row["include_in_interview_context"], 0)


class LlmPromptTest(_TravelogueFixture):
    def test_llm_prompt_carries_anchors_and_no_invention_rule(self):
        tile = self._discovery("Marienplatz")
        prompt = tile["llm_prompt"]
        self.assertIn("may NOT invent", prompt)
        self.assertIn("2026-05-23", prompt)
        self.assertIn("EXIF date (draft)", prompt)
        self.assertIn("never personal memory", prompt)
        self.assertNotIn("I can see the photo", prompt.replace(
            "Never say 'I can see'", ""))

    def test_every_block_has_prompt_and_review_flag(self):
        for b in self._blocks():
            self.assertIn("llm_prompt", b)
            self.assertIn("needs_review", b)
            self.assertIn("prose_anchors", b)
            self.assertIn("provenance_badges", b)
            self.assertIn("photo_link_ids", b)
            self.assertIn("note_ids", b)


class PreviewEndpointTest(_TravelogueFixture):
    def test_endpoint_returns_structured_json(self):
        out = trips.travelogue_preview(self.trip_id)
        self.assertEqual(out["trip_id"], self.trip_id)
        self.assertIn("overview", out)
        self.assertIn("blocks", out)
        self.assertIn("intake_review", out)

    def test_unknown_trip_404(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.travelogue_preview("no-such-trip")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_list_endpoint_filters(self):
        self._add_public(result_summary="stop row",
                         trip_stop_id=self.stop_meal)
        self._add_public(result_summary="trip row")
        out = trips.list_public_context(self.trip_id,
                                        stop_id=self.stop_meal)
        self.assertEqual(out["count"], 1)
        self.assertEqual(out["public_context"][0]["result_summary"],
                         "stop row")


class ReverseGeocodeTest(_TravelogueFixture):
    def test_no_provider_is_honest_and_stores_nothing(self):
        os.environ.pop("HORNELORE_GEOCODE_CMD", None)
        out = trips.reverse_geocode_photo_link(self.link_exif)
        self.assertEqual(out["status"], "no_provider")
        self.assertIn("no geocode provider configured", out["message"])
        self.assertEqual(
            trip_repository.public_context_list(self.trip_id), [])

    def test_no_gps_reported(self):
        out = trips.reverse_geocode_photo_link(self.link_fname)
        self.assertEqual(out["status"], "no_gps")

    def test_provider_command_stores_draft_reverse_geocode_row(self):
        os.environ["HORNELORE_GEOCODE_CMD"] = (
            'true {lat} {lng} && echo "Munich, Bavaria"')
        try:
            out = trips.reverse_geocode_photo_link(self.link_exif)
        finally:
            os.environ.pop("HORNELORE_GEOCODE_CMD", None)
        self.assertEqual(out["status"], "stored")
        self.assertEqual(out["result_summary"], "Munich, Bavaria")
        rows = trip_repository.public_context_list(self.trip_id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_type"], "reverse_geocode")
        self.assertEqual(rows[0]["result_summary"], "Munich, Bavaria")
        self.assertEqual(rows[0]["approved_for_lori"], 0)
        self.assertEqual(rows[0]["photo_link_id"], self.link_exif)
        self.assertEqual(rows[0]["trip_stop_id"], self.stop_sight)

    def test_unknown_link_404(self):
        with self.assertRaises(HTTPException) as ctx:
            trips.reverse_geocode_photo_link("no-such-link")
        self.assertEqual(ctx.exception.status_code, 404)


class ModalPublicContextWordingTest(_TravelogueFixture):
    def _scope(self):
        return modal.build_modal_scope(
            person_id=self.person_id,
            active_trip_id=self.trip_id,
            active_trip_region_id=self.region_de,
            active_trip_stop_id=self.stop_sight,
            active_photo_link_id=self.link_exif,
            selected_kind="photo")

    def test_approved_public_context_uses_approved_wording(self):
        out = self._add_public(
            result_summary="A local holiday brought lederhosen to the "
                           "streets that day.",
            photo_link_id=self.link_exif)
        trips.patch_public_context(out["context_id"],
                                   _Req(approved_for_lori=True))
        answer = modal.answer_modal_direct_question(
            self.person_id, self._scope(),
            "can you tell me about the photo")
        self.assertIn("The approved Travel Doc context says:", answer)
        self.assertIn("local holiday", answer)
        self.assertNotIn("I can see", answer)

    def test_draft_public_context_uses_suggests_wording(self):
        self._add_public(
            result_summary="the Viktualienmarkt fish stalls are a Munich "
                           "institution",
            photo_link_id=self.link_exif)
        answer = modal.answer_modal_direct_question(
            self.person_id, self._scope(),
            "can you tell me about the photo")
        self.assertIn("The public context suggests", answer)
        self.assertIn("Viktualienmarkt", answer)
        self.assertNotIn("The approved Travel Doc context says", answer)

    def test_no_public_context_keeps_legacy_answer_shape(self):
        answer = modal.answer_modal_direct_question(
            self.person_id, self._scope(),
            "can you tell me about the photo")
        self.assertIn("The approved photo context says:", answer)
        self.assertNotIn("Travel Doc context says", answer)
        self.assertNotIn("public context", answer.lower())


class UiStringsTest(unittest.TestCase):
    def test_no_kept_private_string_in_travel_documenter(self):
        js = (_REPO_ROOT / "ui" / "js" /
              "travel-documenter.js").read_text(encoding="utf-8")
        self.assertNotIn("kept private", js)

    def test_travelogue_preview_wired_in_ui(self):
        js = (_REPO_ROOT / "ui" / "js" /
              "travel-documenter.js").read_text(encoding="utf-8")
        self.assertIn('data-td="traveloguePreview"', js)
        self.assertIn("/travelogue-preview", js)
        self.assertIn("Reverse geocode", js)
        self.assertIn("/reverse-geocode", js)
        self.assertIn("EPHEMERA", js)


if __name__ == "__main__":
    unittest.main(verbosity=2)
