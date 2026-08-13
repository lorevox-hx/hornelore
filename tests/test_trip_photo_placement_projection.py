"""WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01 Phase 2 — §6.5 rulings.

The timeline projection and the document built from it. One projection
feeds both the on-screen preview and the DOCX (rule 9), so these tests
assert the projection and then assert the rendered document, and the
second is not redundant with the first: a correct projection rendered by
a builder that de-duplicates by photo id would still print the
photograph once.

THE THREE RULINGS UNDER TEST

1. **"Needs a day" means ZERO PLACEMENTS.** It used to mean
   ``trip_day_id IS NULL``. Under many-to-many that is not merely
   outdated, it is inverted: a photograph on Day 1 and Day 3 serializes
   its compatibility scalar as null BY RULE, so the old query would have
   printed it under "Needs a day" in the same document that already
   printed it under both days. The operator would see one photograph
   three times, described as unplaced.

2. **A multi-day photograph renders once under each explicit day.**
   This deliberately changes the WO-TRAVEL-DOC-CLOSEOUT-01 observation
   that four photographs embedded exactly once each -- that was a
   property of one-day data, not an enforced invariant.

3. **A one-day photograph's output is unchanged**, which is what makes
   ruling 2 safe to land.

Run per-module:
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_trip_photo_placement_projection
"""
from __future__ import annotations

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
for _p in (str(_SERVER_CODE), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

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
        def __init__(self, **kw):
            for _k, _v in kw.items():
                setattr(self, _k, _v)

    pstub.BaseModel = _BaseModel

    def _field(default=None, default_factory=None, **k):
        if default_factory is not None:
            return default_factory()
        return default

    pstub.Field = _field
    pstub.field_validator = lambda *a, **k: (lambda f: f)
    pstub.validator = lambda *a, **k: (lambda f: f)
    pstub.ConfigDict = dict
    sys.modules["pydantic"] = pstub

from api import db as _db  # noqa: E402
from api.services import trip_repository as repo  # noqa: E402
from api.routers import trips  # noqa: E402


class _LinkReq:
    def __init__(self, photo_link_ids=None, photo_ids=None):
        self.photo_link_ids = list(photo_link_ids or [])
        self.photo_ids = list(photo_ids or [])


class _Case(unittest.TestCase):

    def setUp(self):
        self._tmpdb = tempfile.NamedTemporaryFile(suffix=".sqlite3",
                                                  delete=False)
        self._tmpdb.close()
        self.db_path = Path(self._tmpdb.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()
        self._orig_flag = os.environ.get("HORNELORE_TRIPS")
        os.environ["HORNELORE_TRIPS"] = "1"
        self._orig_sync = trips.trip_timeline_bridge.sync_trip_to_life_record
        trips.trip_timeline_bridge.sync_trip_to_life_record = \
            lambda *a, **k: None

        self.person_id = str(uuid.uuid4())
        self._exec(
            "INSERT INTO people (id, display_name, created_at, updated_at)"
            " VALUES (?, 'Projection Test', '2026-08-13', '2026-08-13')",
            (self.person_id,))
        self.trip_id = repo.trip_create(
            person_id=self.person_id, title="Projection Trip",
            start_date="2026-05-01", end_date="2026-05-04")
        repo.trip_days_generate(self.trip_id)
        self.days = repo.trip_days_list(self.trip_id)
        self.day1, self.day2, self.day3 = [d["id"] for d in self.days[:3]]

    def tearDown(self):
        trips.trip_timeline_bridge.sync_trip_to_life_record = self._orig_sync
        _db.DB_PATH = self._orig_db
        if self._orig_flag is None:
            os.environ.pop("HORNELORE_TRIPS", None)
        else:
            os.environ["HORNELORE_TRIPS"] = self._orig_flag
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def _exec(self, sql, args=()):
        con = sqlite3.connect(str(self.db_path))
        try:
            con.execute("PRAGMA foreign_keys=ON")
            con.execute(sql, args)
            con.commit()
        finally:
            con.close()

    def _link(self, caption=None, taken=None):
        pid = str(uuid.uuid4())
        self._exec(
            "INSERT INTO photos (id, narrator_id, image_path, file_hash,"
            " uploaded_by_user_id) VALUES (?,?,?,?,?)",
            (pid, self.person_id, "/tmp/%s.jpg" % pid, "h-" + pid, "op"))
        lid = repo.photo_link_upsert(
            trip_id=self.trip_id, photo_id=pid, taken_at=taken,
            assignment_method="operator", cluster_confidence=1.0)
        if caption:
            repo.photo_link_update(link_id=lid, caption=caption)
        return lid

    # ── projection helpers ────────────────────────────────────────────

    def projection(self):
        return repo.trip_timeline_projection(self.trip_id)

    def photos_on(self, proj, day_id):
        for day in proj["days"]:
            if day["id"] == day_id:
                return [i for i in day["items"] if i.get("kind") == "photo"]
        return []

    def unplaced_photos(self, proj):
        return [i for i in proj["unplaced"]["items"]
                if i.get("kind") == "photo"]


class NeedsADayMeansZeroPlacementsTest(_Case):

    def test_a_photo_with_no_placement_is_unplaced(self):
        lid = self._link()
        self.assertEqual([i["link_id"] for i in
                          self.unplaced_photos(self.projection())], [lid])

    def test_a_photo_on_one_day_is_not_unplaced(self):
        lid = self._link()
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        proj = self.projection()
        self.assertEqual(self.unplaced_photos(proj), [])
        self.assertEqual([i["link_id"] for i in
                          self.photos_on(proj, self.day1)], [lid])

    def test_a_photo_on_TWO_days_is_not_unplaced(self):
        """The inversion. Its compatibility scalar is null by rule, so
        the old ``trip_day_id IS NULL`` query would have called it
        unplaced while also printing it under both days."""
        lid = self._link()
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        trips.link_day_photos(self.trip_id, self.day3, _LinkReq([lid]))
        proj = self.projection()
        self.assertIsNone(repo.photo_link_get(lid)["trip_day_id"],
                          "fixture precondition: the scalar IS null here")
        self.assertEqual(self.unplaced_photos(proj), [],
                         "a photograph on two days was called unplaced")

    def test_removing_the_last_placement_returns_it_to_needs_a_day(self):
        lid = self._link()
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        trips.unlink_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        self.assertEqual([i["link_id"] for i in
                          self.unplaced_photos(self.projection())], [lid])

    def test_removing_one_of_two_placements_does_not(self):
        lid = self._link()
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        trips.link_day_photos(self.trip_id, self.day3, _LinkReq([lid]))
        trips.unlink_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        proj = self.projection()
        self.assertEqual(self.unplaced_photos(proj), [])
        self.assertEqual(self.photos_on(proj, self.day1), [])
        self.assertEqual(len(self.photos_on(proj, self.day3)), 1)


class OneOccurrencePerExplicitDayTest(_Case):

    def test_day1_and_day3_each_show_it_once_and_day2_not_at_all(self):
        lid = self._link(caption="the harbour")
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        trips.link_day_photos(self.trip_id, self.day3, _LinkReq([lid]))
        proj = self.projection()
        self.assertEqual(len(self.photos_on(proj, self.day1)), 1)
        self.assertEqual(len(self.photos_on(proj, self.day3)), 1)
        self.assertEqual(self.photos_on(proj, self.day2), [])
        self.assertEqual(self.unplaced_photos(proj), [])

    def test_each_occurrence_carries_its_own_placement_id(self):
        """Without it the interface cannot say WHICH occurrence to
        remove: the two share one link id."""
        lid = self._link()
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        trips.link_day_photos(self.trip_id, self.day3, _LinkReq([lid]))
        proj = self.projection()
        a = self.photos_on(proj, self.day1)[0]
        b = self.photos_on(proj, self.day3)[0]
        self.assertEqual(a["link_id"], b["link_id"])
        self.assertTrue(a["placement_id"])
        self.assertNotEqual(a["placement_id"], b["placement_id"])

    def test_the_shared_caption_is_identical_on_both_days(self):
        """One asset, one caption. A caption edited on 'the Day 3 copy'
        must not be able to diverge, because there is no copy."""
        lid = self._link(caption="the harbour at dusk")
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        trips.link_day_photos(self.trip_id, self.day3, _LinkReq([lid]))
        proj = self.projection()
        a = self.photos_on(proj, self.day1)[0]
        b = self.photos_on(proj, self.day3)[0]
        self.assertEqual(a["caption"], "the harbour at dusk")
        self.assertEqual(a["caption"], b["caption"])
        self.assertEqual(a["caption_source"], b["caption_source"])

    def test_placement_ord_decides_between_photos_the_clock_cannot(self):
        """Ordering follows the placement's ord. The day timeline still
        merges kinds chronologically, so this is asserted where the
        claim is actually true: photographs whose timestamps tie or are
        absent -- which is every photograph the operator ordered by
        hand."""
        first, second = self._link(), self._link()
        trips.link_day_photos(self.trip_id, self.day1,
                              _LinkReq([second, first]))
        proj = self.projection()
        self.assertEqual([i["link_id"] for i in
                          self.photos_on(proj, self.day1)], [second, first])

        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        try:
            ids = [p["id"] for p in repo.placements_for_day(con, self.day1)]
            repo.placement_reorder(con, self.day1, list(reversed(ids)))
            con.commit()
        finally:
            con.close()
        proj = self.projection()
        self.assertEqual([i["link_id"] for i in
                          self.photos_on(proj, self.day1)], [first, second],
                         "reordering the placements did not reorder the day")

    def test_one_day_photographs_are_unchanged(self):
        """Ruling 3, and the reason ruling 2 is safe to land."""
        a = self._link(caption="one")
        b = self._link(caption="two")
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([a]))
        trips.link_day_photos(self.trip_id, self.day2, _LinkReq([b]))
        proj = self.projection()
        self.assertEqual([i["link_id"] for i in
                          self.photos_on(proj, self.day1)], [a])
        self.assertEqual([i["link_id"] for i in
                          self.photos_on(proj, self.day2)], [b])
        self.assertEqual(self.photos_on(proj, self.day3), [])
        self.assertEqual(self.unplaced_photos(proj), [])

    def test_a_soft_deleted_photo_reaches_no_day_and_no_unplaced(self):
        lid = self._link()
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        self._exec("UPDATE photos SET deleted_at='2026-08-13' WHERE id="
                   "(SELECT photo_id FROM trip_photo_links WHERE id=?)",
                   (lid,))
        proj = self.projection()
        self.assertEqual(self.photos_on(proj, self.day1), [])
        self.assertEqual(self.unplaced_photos(proj), [])

    def test_a_hidden_link_reaches_no_day_and_no_unplaced(self):
        lid = self._link()
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        self._exec("UPDATE trip_photo_links SET hidden=1 WHERE id=?", (lid,))
        proj = self.projection()
        self.assertEqual(self.photos_on(proj, self.day1), [])
        self.assertEqual(self.unplaced_photos(proj), [])


class TheDocumentRendersWhatTheProjectionSaysTest(_Case):
    """The projection is not the document. A builder that keyed on
    photo id would collapse two occurrences back into one and every
    assertion above would still pass."""

    def _docx_bytes(self):
        try:
            from api.services import trip_memoir_docx
        except Exception as exc:                      # pragma: no cover
            self.skipTest("python-docx unavailable: %s" % exc)
        preview = repo.trip_memoir_preview(self.trip_id)
        return trip_memoir_docx.build_trip_docx(preview)

    def _docx_text(self):
        import io
        import zipfile
        import re as _re
        data = self._docx_bytes()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
        return _re.sub(r"<[^>]+>", " ", xml)

    def _docx_image_count(self):
        import io
        import zipfile
        data = self._docx_bytes()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
        # Each embedded picture is one <pic:pic> element regardless of
        # how many times the same media part is referenced, so this
        # counts OCCURRENCES rather than stored files -- which is the
        # distinction the ruling is about.
        return xml.count("<pic:pic")

    def _real_image(self, lid):
        """Give this link a real PNG so the builder embeds something.

        BUILT, not pasted from a hex literal. The first version of this
        helper used a hand-copied byte string that was subtly corrupt;
        python-docx refused it, the builder logged 'photo embed failed'
        and carried on, and the embed count came back 0 -- a test
        failure that looked like a product defect and was not. A file
        assembled from real chunks either is a PNG or raises here.
        """
        import struct
        import zlib

        def _chunk(kind, payload):
            body = kind + payload
            return (struct.pack(">I", len(payload)) + body
                    + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))

        png = (b"\x89PNG\r\n\x1a\n"
               + _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
               + _chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff"))
               + _chunk(b"IEND", b""))
        path = Path(tempfile.mkdtemp(prefix="hl-docx-")) / "p.png"
        path.write_bytes(png)
        self._exec("UPDATE photos SET image_path=? WHERE id="
                   "(SELECT photo_id FROM trip_photo_links WHERE id=?)",
                   (str(path), lid))

    def test_a_two_day_photo_is_embedded_twice(self):
        lid = self._link(caption="the harbour at dusk")
        self._real_image(lid)
        repo.photo_link_update(link_id=lid, include_in_memoir=True)
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        trips.link_day_photos(self.trip_id, self.day3, _LinkReq([lid]))
        self.assertEqual(
            self._docx_image_count(), 2,
            "the document collapsed two placements of one photograph "
            "into a single occurrence")

    def test_a_one_day_photo_is_embedded_once(self):
        lid = self._link(caption="only once")
        self._real_image(lid)
        repo.photo_link_update(link_id=lid, include_in_memoir=True)
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        self.assertEqual(self._docx_image_count(), 1)

    def test_a_multi_day_photo_never_appears_under_needs_a_day(self):
        lid = self._link(caption="unmistakable caption text")
        self._real_image(lid)
        repo.photo_link_update(link_id=lid, include_in_memoir=True)
        trips.link_day_photos(self.trip_id, self.day1, _LinkReq([lid]))
        trips.link_day_photos(self.trip_id, self.day3, _LinkReq([lid]))
        text = self._docx_text()
        needs = text.find("Needs a day")
        if needs >= 0:
            self.assertNotIn("unmistakable caption text", text[needs:],
                             "a placed photograph printed under Needs a day")

    def test_an_unplaced_photo_still_reaches_needs_a_day(self):
        """Non-vacuity for the test above: if nothing ever landed under
        that heading, its assertion would be free."""
        lid = self._link(caption="genuinely unplaced caption")
        self._real_image(lid)
        repo.photo_link_update(link_id=lid, include_in_memoir=True)
        text = self._docx_text()
        self.assertIn("genuinely unplaced caption", text)


if __name__ == "__main__":
    unittest.main()
