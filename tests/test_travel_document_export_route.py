"""WO-TRAVEL-DOC-CLOSEOUT-01 — the export route, EXECUTED.

WHY THIS SUITE EXISTS
---------------------
`export_docx()` shipped with `len(photo_rows)` in its logging line after
`photo_rows` had been retired in favour of the shared projection. The
document was built correctly and then the route raised `NameError` on
the last line before returning it, so every export died at the final
step.

463 tests were green. Not one of them called the function. The route
tests read its source and asserted which collaborators it names — which
is the right instrument for "does it pass the projection to both
consumers" and is blind, by construction, to a name that no longer
exists at runtime.

So this CALLS the route. Through the logging line, through the header
construction, through the StreamingResponse, and drains the body. An
undefined variable anywhere on that path is now a failure here rather
than a failure in front of Chris.

The database is not touched: `trip_repository` is stubbed at the two
functions the route calls, and python-docx does the rest for real.

Run:
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_travel_document_export_route
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "server" / "code"))

try:
    import fastapi                       # noqa: F401
    from docx import Document            # noqa: F401
    _READY = True
    _WHY = ""
except Exception as exc:                  # pragma: no cover - env dependent
    _READY, _WHY = False, str(exc)


def _png(path: Path) -> Path:
    path.write_bytes(bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753"
        "de0000000c4944415478da63f8ffff3f0005fe02fea735c9ab0000000049454e"
        "44ae426082"))
    return path


class ExportRouteExecutesTest(unittest.TestCase):
    """Calls export_docx() for real."""

    @classmethod
    def setUpClass(cls):
        if not _READY:                    # pragma: no cover
            raise unittest.SkipTest(f"ENV-SKIP: {_WHY}")
        os.environ["HORNELORE_TRIPS"] = "1"
        cls.tmp = tempfile.TemporaryDirectory()
        cls.png = _png(Path(cls.tmp.name) / "p.png")

        from api.routers import trips as trips_mod
        from api.services.trip_repository import photo_appendix_projection
        cls.trips = trips_mod
        cls._real = {
            "proj": trips_mod.trip_repository.photo_appendix_projection,
            "prev": trips_mod.trip_repository.trip_memoir_preview,
        }

        rows = [{
            "id": "l1", "photo_id": "p1", "trip_stop_id": "s1",
            "stop_location_name": "Bismarck",
            "narrator_caption": "Peter and Josie",
            "taken_at": "1962-06-01",
            "photo_image_path": str(cls.png),
        }]
        cls.projection = photo_appendix_projection(rows=rows)

        cls.captured = {}

        def fake_proj(trip_id=None, rows=None):
            cls.captured["proj_trip"] = trip_id
            return cls.projection

        def fake_preview(trip_id, appendix=None):
            cls.captured["preview_appendix_is_same_object"] = (
                appendix is cls.projection)
            return {
                "title": cls.TITLE,
                "date_range": {"start": "1962-05-30", "end": "1962-06-10"},
                "summary": "", "story_notes": [], "sources": [],
                "part_one_journey_in_order": [], "part_two_themes": [],
                "part_three_photo_appendix": {},
            }

        cls.fakes = {"proj": fake_proj, "preview": fake_preview}

    TITLE = "Bismarck 1962"

    @classmethod
    def tearDownClass(cls):
        if _READY:
            cls.trips.trip_repository.photo_appendix_projection = \
                cls._real["proj"]
            cls.trips.trip_repository.trip_memoir_preview = cls._real["prev"]
            cls.tmp.cleanup()

    def _call(self, title=None):
        if title is not None:
            type(self).TITLE = title
        self.trips.trip_repository.photo_appendix_projection = \
            self.fakes["proj"]
        self.trips.trip_repository.trip_memoir_preview = self.fakes["preview"]
        return self.trips.export_docx("T1")

    def _body(self, resp):
        chunks = []

        async def drain():
            async for c in resp.body_iterator:
                chunks.append(c if isinstance(c, bytes) else c.encode())
        asyncio.new_event_loop().run_until_complete(drain())
        return b"".join(chunks)

    # ── the bug ───────────────────────────────────────────────────────
    def test_the_route_returns_without_raising(self):
        """This is the whole point. `len(photo_rows)` raised NameError
        here, AFTER the document had been built."""
        resp = self._call()
        self.assertIsNotNone(resp)

    def test_the_response_body_is_a_real_document(self):
        body = self._body(self._call())
        self.assertGreater(len(body), 5000)
        self.assertEqual(b"PK", body[:2])

    def test_the_body_contains_the_approved_photo_caption(self):
        import io
        body = self._body(self._call())
        text = "\n".join(p.text for p in Document(io.BytesIO(body)).paragraphs)
        self.assertIn("Peter and Josie", text)
        self.assertIn("Approved photos in appendix: 1", text)

    def test_no_retired_variable_survives_on_the_response_path(self):
        """Executing the route is the only instrument that can see this.
        A source scan reads which names appear; it cannot tell which of
        them still exist."""
        import inspect, re
        src = inspect.getsource(self.trips.export_docx)
        # Comment-stripped. The retirement comment quotes the retired
        # name, as a correction in place is required to, so a raw scan
        # fires on the explanation rather than on code. The EXECUTION
        # tests above are the real guard; this one only stops the name
        # creeping back into a statement.
        code = re.sub(r"#.*$", "", src, flags=re.M)
        code = re.sub(r'"""[\s\S]*?"""', "", code)
        self.assertNotIn("photo_rows", code)

    # ── one projection, both consumers ────────────────────────────────
    def test_the_same_projection_object_reaches_the_preview(self):
        self._call()
        self.assertTrue(
            self.captured["preview_appendix_is_same_object"],
            "the preview was built from a different read than the document")

    def test_the_projection_is_built_once(self):
        calls = []
        orig = self.fakes["proj"]

        def counting(trip_id=None, rows=None):
            calls.append(trip_id)
            return orig(trip_id=trip_id, rows=rows)
        self.fakes["proj"] = counting
        try:
            self._call()
        finally:
            self.fakes["proj"] = orig
        self.assertEqual(1, len(calls),
                         f"the photo table was read {len(calls)} times")

    # ── headers, which the browser actually consumes ──────────────────
    def test_both_filename_forms_are_present(self):
        cd = self._call().headers["content-disposition"]
        self.assertIn('filename="lorevox_trip_memoir_Bismarck_1962.docx"', cd)
        self.assertIn("filename*=UTF-8''", cd)

    def test_a_non_latin_title_survives_in_filename_star(self):
        from urllib.parse import unquote
        import re
        cd = self._call(title="Königsberg").headers["content-disposition"]
        # The ASCII fallback is latin-1-safe...
        ascii_part = re.search(r'filename="([^"]+)"', cd).group(1)
        ascii_part.encode("latin-1")            # would raise if it were not
        # ...and the real name is in filename*, which is what the browser
        # now prefers.
        star = re.search(r"filename\*=UTF-8''([^;]+)", cd).group(1)
        self.assertEqual("lorevox_trip_memoir_Königsberg.docx",
                         unquote(star))
        type(self).TITLE = "Bismarck 1962"

    def test_a_long_title_keeps_its_extension(self):
        from urllib.parse import unquote
        import re
        cd = self._call(title="A" * 300).headers["content-disposition"]
        star = unquote(re.search(r"filename\*=UTF-8''([^;]+)", cd).group(1))
        self.assertTrue(star.endswith(".docx"), star[-20:])
        type(self).TITLE = "Bismarck 1962"

    def test_the_media_type_is_a_word_document(self):
        resp = self._call()
        self.assertIn("wordprocessingml", resp.media_type)


class ExportRouteRefusesCleanlyTest(unittest.TestCase):
    """A missing trip is a 404, not a traceback."""

    @classmethod
    def setUpClass(cls):
        if not _READY:                    # pragma: no cover
            raise unittest.SkipTest(f"ENV-SKIP: {_WHY}")
        os.environ["HORNELORE_TRIPS"] = "1"

    def test_an_unknown_trip_is_a_404(self):
        from fastapi import HTTPException
        from api.routers import trips as trips_mod
        real_p = trips_mod.trip_repository.photo_appendix_projection
        real_v = trips_mod.trip_repository.trip_memoir_preview
        trips_mod.trip_repository.photo_appendix_projection = \
            lambda *a, **k: {"groups": [], "approved": 0, "available": 0,
                             "unavailable": 0, "approved_by_stop": {}}
        trips_mod.trip_repository.trip_memoir_preview = lambda *a, **k: None
        try:
            with self.assertRaises(HTTPException) as ctx:
                trips_mod.export_docx("nope")
            self.assertEqual(404, ctx.exception.status_code)
        finally:
            trips_mod.trip_repository.photo_appendix_projection = real_p
            trips_mod.trip_repository.trip_memoir_preview = real_v


if __name__ == "__main__":
    unittest.main(verbosity=2)
