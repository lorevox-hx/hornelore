"""WO-LIFEMAP-TRAVELS-SHELF-AND-NARRATION-01 Phases 2+3 — narration
parser + provisional writes.

Fixture pack per the approved spec §5: Chris's Munich sentence
verbatim, Janice-style meandering narration, negation, uncertainty,
correction, duplicate-trip reference, deterministic Untitled-trip
birth, operator rows never moved, never-delete.
"""
from __future__ import annotations

import json
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
from api.services import trip_narration_capture as tnc  # noqa: E402
from api.services import trip_repository  # noqa: E402


class ParserTest(unittest.TestCase):
    def test_chris_munich_sentence_verbatim(self):
        p = tnc.parse_trip_narration(
            "I took a trip in May 2026 starting in Munich")
        self.assertEqual(p["start_place"], "Munich")
        self.assertEqual(p["month"], 5)
        self.assertEqual(p["year"], 2026)
        self.assertEqual(p["confidence"], "high")

    def test_route_with_nights(self):
        p = tnc.parse_trip_narration(
            "We started in Munich, then we drove to Prague for a while. "
            "We spent three nights in Prague, then on to Vienna.")
        self.assertEqual(p["start_place"], "Munich")
        places = [s["place"] for s in p["stops"]]
        self.assertIn("Prague", places)
        self.assertIn("Vienna", places)
        prague = next(s for s in p["stops"] if s["place"] == "Prague")
        self.assertEqual(prague["nights"], 3)

    def test_negation_suppresses_vienna(self):
        # Spec acceptance fixture, verbatim shape.
        p = tnc.parse_trip_narration(
            "I started in Munich, then Prague, but we never made it to Vienna.")
        self.assertEqual(p["start_place"], "Munich")
        places = [s["place"] for s in p["stops"]]
        self.assertNotIn("Vienna", places)
        self.assertIn("Vienna", p["suppressed"])

    def test_uncertainty_is_observation_only(self):
        p = tnc.parse_trip_narration("Maybe we stopped in Brno? I think it was Brno.")
        places = [s["place"] for s in p["stops"]]
        self.assertNotIn("Brno", places)
        self.assertTrue(p["observations"])
        self.assertIsNone(p["start_place"])

    def test_order_correction_parses(self):
        p = tnc.parse_trip_narration("No, Salzburg was before Vienna.")
        self.assertEqual(p["corrections"],
                         [{"first": "Salzburg", "second": "Vienna"}])

    def test_start_correction_needs_correction_marker(self):
        p1 = tnc.parse_trip_narration("No, we started in Munich.")
        self.assertEqual(p1["start_correction"], "Munich")
        p2 = tnc.parse_trip_narration("We started in Munich.")
        self.assertIsNone(p2["start_correction"])  # plain statement ≠ correction
        self.assertEqual(p2["start_place"], "Munich")

    def test_janice_style_meander_still_catches_places(self):
        p = tnc.parse_trip_narration(
            "Oh, that was such a time. We stayed in Bismarck with my "
            "sister — she had the little dog then — and later we visited "
            "Mandan for the fair. I remember the pie most of all.")
        places = [s["place"] for s in p["stops"]]
        self.assertIn("Bismarck", places)
        self.assertIn("Mandan", places)

    def test_no_places_no_confidence(self):
        p = tnc.parse_trip_narration("It was lovely weather that whole week.")
        self.assertEqual(p["confidence"], "none")

    def test_blocklist_rejects_pronouns_and_months(self):
        p = tnc.parse_trip_narration("Then we went to May and I stayed in We.")
        self.assertEqual([s["place"] for s in p["stops"]], [])

    def test_empty_and_garbage_safe(self):
        for bad in ("", "   ", None):
            p = tnc.parse_trip_narration(bad)  # type: ignore[arg-type]
            self.assertEqual(p["confidence"], "none")


class _WriteCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self._tmp.close()
        self.db_path = Path(self._tmp.name)
        self._orig = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()
        self.person_id = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO people (id, display_name, date_of_birth, created_at, "
            "updated_at) VALUES (?, 'Narration Test', '1962-12-24', "
            "'2026-07-05', '2026-07-05');", (self.person_id,))
        con.commit()
        con.close()

    def tearDown(self):
        _db.DB_PATH = self._orig
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def _stop_names(self, trip_id):
        tree = trip_repository.trip_tree(trip_id) or {}
        names = []
        for r in tree.get("regions", []):
            def _walk(s):
                names.append(s.get("location_name"))
                for c in s.get("children", []):
                    _walk(c)
            for s in r.get("stops", []):
                _walk(s)
        return names


class ProvisionalWriteTest(_WriteCase):
    def test_creates_untitled_trip_deterministically(self):
        p = tnc.parse_trip_narration(
            "I took a trip in May 2026 starting in Munich, then to Prague.")
        out = tnc.apply_trip_narration(p, person_id=self.person_id)
        self.assertTrue(out["applied"])
        self.assertTrue(out["created_trip"])
        trip = trip_repository.trip_get(out["trip_id"])
        self.assertEqual(trip["title"], "Untitled trip")  # Lori never titles
        self.assertEqual(trip["start_date"], "2026-05-01")
        meta = trip["meta_json"]
        self.assertEqual(meta.get("source"), "narration")
        self.assertEqual(meta.get("status"), "provisional")
        self.assertEqual(meta.get("created_from_surface"), "travels_shelf")
        names = self._stop_names(out["trip_id"])
        self.assertIn("Munich", names)
        self.assertIn("Prague", names)

    def test_active_trip_adds_stops_no_new_trip(self):
        trip_id = trip_repository.trip_create(
            person_id=self.person_id, title="Spring 2026",
            start_date="2026-05-22", end_date="2026-06-13")
        p = tnc.parse_trip_narration("We started in Munich, then on to Prague.")
        out = tnc.apply_trip_narration(p, person_id=self.person_id,
                                       active_trip_id=trip_id)
        self.assertTrue(out["applied"])
        self.assertFalse(out["created_trip"])
        self.assertEqual(sorted(out["stops_added"]), ["Munich", "Prague"])

    def test_duplicate_guard_blocks_second_trip(self):
        trip_repository.trip_create(
            person_id=self.person_id, title="Spring 2026 Central Europe",
            start_date="2026-05-22", end_date="2026-06-13")
        p = tnc.parse_trip_narration(
            "Our trip in 2026 started in Munich, then to Prague.")
        out = tnc.apply_trip_narration(p, person_id=self.person_id)
        self.assertFalse(out["created_trip"])
        self.assertIsNotNone(out["needs_disambiguation"])
        # Exactly one trip exists — no duplicate.
        self.assertEqual(len(trip_repository.trip_list(self.person_id)), 1)

    def test_existing_stops_never_duplicated_or_overwritten(self):
        trip_id = trip_repository.trip_create(
            person_id=self.person_id, title="T", start_date="2026-05-01")
        rid = trip_repository.region_create(trip_id, "Czechia")
        trip_repository.stop_create(trip_id, rid, "Prague")
        p = tnc.parse_trip_narration("We stayed in Prague, then on to Brno.")
        out = tnc.apply_trip_narration(p, person_id=self.person_id,
                                       active_trip_id=trip_id)
        self.assertEqual(out["stops_added"], ["Brno"])
        self.assertEqual(self._stop_names(trip_id).count("Prague"), 1)

    def test_reorder_touches_narration_rows_only(self):
        trip_id = trip_repository.trip_create(
            person_id=self.person_id, title="T", start_date="2026-05-01")
        # Narration adds Vienna then Salzburg (that order).
        p1 = tnc.parse_trip_narration("We went to Vienna, then on to Salzburg.")
        tnc.apply_trip_narration(p1, person_id=self.person_id,
                                 active_trip_id=trip_id)
        p2 = tnc.parse_trip_narration("No, Salzburg was before Vienna.")
        out = tnc.apply_trip_narration(p2, person_id=self.person_id,
                                       active_trip_id=trip_id)
        self.assertTrue(out["reordered"])
        names = self._stop_names(trip_id)
        self.assertLess(names.index("Salzburg"), names.index("Vienna"))

    def test_operator_rows_never_moved(self):
        trip_id = trip_repository.trip_create(
            person_id=self.person_id, title="T", start_date="2026-05-01")
        rid = trip_repository.region_create(trip_id, "R")
        trip_repository.stop_create(trip_id, rid, "Vienna")    # operator rows
        trip_repository.stop_create(trip_id, rid, "Salzburg")  # (no narration meta)
        p = tnc.parse_trip_narration("No, Salzburg was before Vienna.")
        out = tnc.apply_trip_narration(p, person_id=self.person_id,
                                       active_trip_id=trip_id)
        self.assertFalse(out["reordered"])
        names = self._stop_names(trip_id)
        self.assertLess(names.index("Vienna"), names.index("Salzburg"))  # unchanged

    def test_never_deletes_anything(self):
        trip_id = trip_repository.trip_create(
            person_id=self.person_id, title="T", start_date="2026-05-01")
        rid = trip_repository.region_create(trip_id, "R")
        trip_repository.stop_create(trip_id, rid, "Prague")
        # A narration turn full of negations must not remove rows.
        p = tnc.parse_trip_narration(
            "We never made it to Prague actually, we skipped Vienna too.")
        tnc.apply_trip_narration(p, person_id=self.person_id,
                                 active_trip_id=trip_id)
        self.assertIn("Prague", self._stop_names(trip_id))

    def test_apply_never_raises(self):
        out = tnc.apply_trip_narration(
            {"confidence": "high", "start_place": "X", "stops": [],
             "corrections": [], "start_correction": None, "year": None,
             "month": None},
            person_id=self.person_id, active_trip_id="no-such-trip")
        self.assertIsNotNone(out)  # summary returned, no exception


class ZeroTripHookRegressionTest(_WriteCase):
    """BUG-TRAVELS-ZERO-TRIP-NARRATION-HOOK-NEVER-CREATES-TRIP-01:
    zero trips + shelf open + the Munich sentence must create the
    Untitled trip WITHOUT an active_trip_id, and the chat_ws hook must
    accept the shelf-open scope."""

    def test_munich_sentence_creates_first_trip_without_active_id(self):
        p = tnc.parse_trip_narration(
            "I took a trip in May 2026 starting in Munich")
        out = tnc.apply_trip_narration(p, person_id=self.person_id,
                                       active_trip_id=None)
        self.assertTrue(out["created_trip"])
        trip = trip_repository.trip_get(out["trip_id"])
        self.assertEqual(trip["title"], "Untitled trip")
        self.assertIn("Munich", self._stop_names(out["trip_id"]))

    def test_chat_ws_hook_accepts_shelf_open_scope(self):
        src = (_SERVER_CODE / "api" / "routers" / "chat_ws.py").read_text(
            encoding="utf-8")
        # The gating condition must include the shelf-open flag, not
        # only active_trip_id (the bug: first trip could never be born).
        self.assertIn("travels_shelf_open", src)
        self.assertIn("_active_trip_id or _shelf_open", src)

    def test_shelf_open_flag_rides_runtime71(self):
        app = (_REPO_ROOT / "ui" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("travels_shelf_open:", app)

    def test_zero_trip_scope_flag_survives_poll_reset(self):
        # BUG-TRAVELS-ZERO-TRIP-SCOPE-FLAG-CLEARED-IMMEDIATELY-01:
        # _stopZeroTripPoll() clears travelsShelfOpen, so inside
        # _zeroTrips() it must run BEFORE the flag is set true —
        # otherwise the shelf scope is dead before the narrator's next
        # turn and the first trip can never be born.
        import re as _re
        js = (_REPO_ROOT / "ui" / "js" / "travels-shelf.js").read_text(
            encoding="utf-8")
        m = _re.search(r"function _zeroTrips\([\s\S]*?\n  \}", js)
        self.assertIsNotNone(m)
        body = m.group(0)
        stop_idx = body.find("_stopZeroTripPoll()")
        flag_idx = body.find("travelsShelfOpen = true")
        self.assertGreater(stop_idx, -1, "_zeroTrips must reset the poll")
        self.assertGreater(flag_idx, -1, "_zeroTrips must set shelf scope")
        self.assertLess(stop_idx, flag_idx,
                        "_stopZeroTripPoll() must run BEFORE the scope "
                        "flag is set (it clears travelsShelfOpen)")

    def test_date_confirm_not_dispatched_at_trip_open(self):
        # BUG-TRAVELS-OPEN-DISPATCHES-DATE-CONFIRM-TOO-SOON-01: one
        # deliberate prompt per gesture; the WO-9 queue holds a single
        # system prompt. The confirmation must live in the refresh
        # tick, not in _openTrip.
        import re as _re
        js = (_REPO_ROOT / "ui" / "js" / "travels-shelf.js").read_text(
            encoding="utf-8")
        js_nc = _re.sub(r"/\*[\s\S]*?\*/|//[^\n]*", "", js)
        m = _re.search(r"function _openTrip\([\s\S]*?\n  \}", js_nc)
        self.assertIsNotNone(m)
        self.assertNotIn("_maybeOfferDateConfirmation", m.group(0))
        m2 = _re.search(r"function _refetchAndPaint\([\s\S]*?\n  \}", js_nc)
        self.assertIsNotNone(m2)
        self.assertIn("_maybeOfferDateConfirmation", m2.group(0))


class IsolationTest(unittest.TestCase):
    """LAW 3-style: the parser module must not import runtime surfaces."""

    _FORBIDDEN = ("routers.extract", "prompt_composer", "memory_echo",
                  "routers.chat_ws", "llm_api", "routers.llm")

    def test_no_forbidden_imports(self):
        src = (_SERVER_CODE / "api" / "services" /
               "trip_narration_capture.py").read_text(encoding="utf-8")
        import ast as _ast
        tree = _ast.parse(src)
        for node in _ast.walk(tree):
            names = []
            if isinstance(node, _ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, _ast.ImportFrom):
                names = [node.module or ""]
            for n in names:
                for bad in self._FORBIDDEN:
                    self.assertNotIn(bad, n or "",
                                     f"forbidden import {n} in parser")


if __name__ == "__main__":
    unittest.main()
