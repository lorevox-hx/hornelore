"""The browser must be able to READ the download filename.

WHY THIS EXISTS
---------------
The live export on 2026-08-06 downloaded as `travel-document.docx` for
every trip, not `lorevox_trip_memoir_Bismarck_Trip.docx`.

Two tests already covered that filename and both passed:

  * a server-side test asserted the route emits `Content-Disposition`
    with both an ASCII `filename=` and an RFC 6266 `filename*=`;
  * a browser-side test fed the parsing regex a header string and
    asserted it extracted the right name.

Both were correct. Neither crossed an ORIGIN, and that is where the
header disappears. The interface is served from :8082 and the API
answers on :8000, so every response is cross-origin, and the Fetch
standard exposes only the CORS-safelisted response headers unless the
server names the others in `Access-Control-Expose-Headers`. The app
set `allow_headers` -- which governs the REQUEST direction -- and
nothing at all for responses.

Measured from the live page rather than assumed: `r.headers` enumerated
exactly `["content-length", "content-type"]`, and
`r.headers.get("server")` -- which uvicorn certainly sends -- returned
null. `Content-Disposition` was never visible, so the browser fell to
its hardcoded default.

So this test does the one thing the other two did not: it sends an
`Origin` header and asserts on what comes back. A header the browser
cannot read is a header that does not exist.

Run:
    PYTHONPYCACHEPREFIX=/tmp/pyc PYTHONPATH=server/code \\
        .venv/bin/python -m unittest tests.test_cors_content_disposition
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "server" / "code"))

try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import Response
    from fastapi.testclient import TestClient
    _READY, _WHY = True, ""
except Exception as exc:               # pragma: no cover - env dependent
    _READY, _WHY = False, str(exc)

BROWSER_ORIGIN = "http://127.0.0.1:8082"

#: Everything a browser can read on a cross-origin response WITHOUT the
#: server naming it. Anything outside this set needs to be exposed.
CORS_SAFELISTED = {
    "cache-control", "content-language", "content-length",
    "content-type", "expires", "last-modified", "pragma",
}


def _cors_kwargs_from_main():
    """The keyword arguments `main.py` actually passes to CORSMiddleware.

    Read from the AST rather than by importing `main`, which pulls in
    forty routers, a database and a model loader. The thing under test
    is one call's arguments, so parsing the call is both cheaper and a
    more direct measurement than booting the app to observe it.
    """
    import ast
    src = (_REPO / "server" / "code" / "api" / "main.py").read_text(
        encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = getattr(fn, "attr", None) or getattr(fn, "id", None)
        if name != "add_middleware":
            continue
        first = node.args[0] if node.args else None
        if getattr(first, "id", None) != "CORSMiddleware":
            continue
        out = {}
        for kw in node.keywords:
            try:
                out[kw.arg] = ast.literal_eval(kw.value)
            except Exception:
                out[kw.arg] = "<dynamic>"
        return out
    raise AssertionError("no CORSMiddleware registration found in main.py")


class MainAppCorsConfigTest(unittest.TestCase):
    """What the real application is configured to expose."""

    def setUp(self):
        if not _READY:                 # pragma: no cover
            self.skipTest(f"ENV-SKIP: {_WHY}")
        self.kwargs = _cors_kwargs_from_main()

    def test_content_disposition_is_exposed(self):
        exposed = self.kwargs.get("expose_headers") or []
        self.assertIn(
            "Content-Disposition",
            [str(h) for h in exposed],
            "the browser cannot read the download filename; every trip "
            "will download under the hardcoded fallback name")

    def test_expose_headers_is_not_confused_with_allow_headers(self):
        """`allow_headers` governs the REQUEST direction. It was set,
        which is why this looked configured while responses were not."""
        self.assertIn("allow_headers", self.kwargs)
        self.assertIn("expose_headers", self.kwargs)

    def test_content_disposition_is_not_safelisted(self):
        """Non-vacuity. If it were readable by default the test above
        would be guarding nothing."""
        self.assertNotIn("content-disposition", CORS_SAFELISTED)


class CrossOriginResponseTest(unittest.TestCase):
    """The wire, with an Origin header on the request.

    A miniature app carrying the same middleware arguments as `main.py`,
    so this exercises the real configuration through real Starlette CORS
    handling without booting the whole server.
    """

    @classmethod
    def setUpClass(cls):
        if not _READY:                 # pragma: no cover
            raise unittest.SkipTest(f"ENV-SKIP: {_WHY}")
        kwargs = _cors_kwargs_from_main()
        app = FastAPI()
        app.add_middleware(CORSMiddleware, **kwargs)

        @app.get("/download")
        def _download():
            return Response(
                content=b"PK",
                media_type=("application/vnd.openxmlformats-officedocument"
                            ".wordprocessingml.document"),
                headers={"Content-Disposition":
                         'attachment; filename="lorevox_trip_memoir_'
                         'Bismarck_Trip.docx"'},
            )

        cls.client = TestClient(app)

    def test_an_origin_request_is_told_it_may_read_the_header(self):
        r = self.client.get("/download", headers={"Origin": BROWSER_ORIGIN})
        self.assertEqual(200, r.status_code)
        exposed = r.headers.get("access-control-expose-headers", "")
        self.assertIn(
            "content-disposition",
            [h.strip().lower() for h in exposed.split(",")],
            f"header list was {exposed!r}")

    def test_the_filename_itself_still_arrives(self):
        r = self.client.get("/download", headers={"Origin": BROWSER_ORIGIN})
        self.assertIn("lorevox_trip_memoir_Bismarck_Trip.docx",
                      r.headers.get("content-disposition", ""))

    def test_the_response_is_allowed_cross_origin_at_all(self):
        r = self.client.get("/download", headers={"Origin": BROWSER_ORIGIN})
        self.assertIn("access-control-allow-origin", r.headers)

    def test_a_same_origin_request_is_unaffected(self):
        """No Origin header: the browser applies no CORS rules and the
        exposure list is irrelevant. Included so a future change that
        only ever tested the cross-origin path cannot break this one."""
        r = self.client.get("/download")
        self.assertEqual(200, r.status_code)
        self.assertIn("lorevox_trip_memoir_Bismarck_Trip.docx",
                      r.headers.get("content-disposition", ""))

    def test_without_the_exposure_the_browser_would_be_blind(self):
        """The negative control, and the reason this file exists.

        Builds the same app WITHOUT `expose_headers` and shows the
        response carries no exposure list -- which is precisely the
        state that shipped, and which two passing tests did not see.
        """
        app = FastAPI()
        app.add_middleware(CORSMiddleware, allow_origins=["*"],
                           allow_credentials=False, allow_methods=["*"],
                           allow_headers=["*"])

        @app.get("/download")
        def _download():
            return Response(content=b"PK", headers={
                "Content-Disposition": 'attachment; filename="x.docx"'})

        r = TestClient(app).get("/download",
                                headers={"Origin": BROWSER_ORIGIN})
        exposed = [h.strip().lower() for h
                   in r.headers.get("access-control-expose-headers",
                                    "").split(",") if h.strip()]
        self.assertNotIn("content-disposition", exposed)


class BrowserFallbackOrderTest(unittest.TestCase):
    """The browser's own parse, which had a second, separate defect."""

    def setUp(self):
        self.src = (_REPO / "ui" / "js" / "travel-doc-lab.js").read_text(
            encoding="utf-8")
        i = self.src.index("function _exportTravelDocument(")
        self.body = self.src[i:self.src.index("\n  }\n", i)]

    def test_the_name_starts_empty_so_every_source_is_consulted(self):
        """`var name = "travel-document.docx"` made `if (!name)` dead
        code: the ASCII `filename=` branch could never run, because the
        default was truthy. The hardcoded name has to be last."""
        star = self.body.index("filename\\*")
        default = self.body.index('"travel-document.docx"')
        self.assertGreater(
            default, star,
            "the hardcoded fallback is consulted before the header")

    def test_both_header_forms_are_read(self):
        self.assertIn("filename\\*", self.body)
        self.assertIn('filename="', self.body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
