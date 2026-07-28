"""WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01 Phase 2B -- byte acquisition.

Phase 2A read back WHAT the operator picked. This is the module that
fetches the actual bytes, identifies them, reads their EXIF, and puts
them where Phase 3 will look. It still opens no database handle and
creates no candidate -- that is the route's job, in the order spec 12.2
requires -- and this suite is written so that changing any of the
following quietly breaks something.

What is locked here:

  1. THE PROVIDER IS NOT TRUSTED ABOUT CONTENT. Bytes are identified by
     their own leading bytes. A declared `mimeType` is not an input to
     `sniff_image` at all, so no future bug fix can quietly promote it
     to one. Unrecognised bytes are REJECTED -- there is no `.jpg`
     fallback here, which is the specific thing spec 12.1 says this lane
     must not copy from `photo_intake/storage.py`.

  2. THE CAP IS ENFORCED DURING THE STREAM. A `Content-Length` over the
     cap is refused before a byte is read, but a LYING `Content-Length`
     is caught mid-stream too. A header is a promise, not a limit.

  3. FAILURE LEAVES NOTHING ON DISK. Every refusal path is asserted
     against an empty temp directory. A partial photo left behind would
     be indistinguishable from a staged one to anything using a glob.

  4. FAILURES CARRY `retryable`, AND IT IS A PROPERTY OF THE FAILURE.
     An expired download URL is retryable; bytes that are not an image
     never become one. Ingest never calls `candidate_decide()` (spec
     12.3), so this flag is the whole basis on which a re-run decides
     what to attempt again.

  5. NOTHING LEAKS. `base_url` is a bearer-scoped download URL and the
     access token is a credential. Neither may appear in any exception
     message or log line -- asserted against a real captured log stream.
     This includes transport failures, where `str(exc)` on a real
     `requests` error CONTAINS the full URL.

  6. DATE FALLS BACK; LOCATION DOES NOT. EXIF date missing -> the
     Picker's `createTime` is used and labelled `provider_metadata`.
     EXIF GPS missing -> null, null, `unknown`, always. Google Picker
     metadata is never a GPS source, and the schema does not enforce
     that, so this suite does.

  7. STAGING IS DERIVED, NEVER STORED, AND LEAVES EXACTLY ONE FILE.
     `DATA_DIR/import_staging/<batch_id>/<candidate_id>/original.<ext>`,
     with traversal-shaped ids refused and any stale `original.*`
     removed so Phase 3's "exactly one" holds after a re-ingest.

This suite does not need fastapi and does not touch the network:
`requests` is replaced inside `acquire` by a recording double, and the
real bytes it works on are written to a temp directory here.

pytest is not installed in this repo; run with:

    .venv/bin/python -u -m unittest tests.test_google_picker_phase2b_acquire
"""
from __future__ import annotations

import ast
import hashlib
import logging
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Same import strategy as tests/test_google_picker_phase1.py: mirror the
# production package root so `code.services...` resolves the way the
# running server resolves it.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
for _p in (str(_SERVER_CODE), str(_REPO_ROOT / "server"), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# The stdlib `code` module (InteractiveInterpreter) shadows the
# production `server/code` package if something imported it first.
if "code" in sys.modules and not hasattr(sys.modules["code"], "__path__"):
    del sys.modules["code"]

from code.services.google_picker import acquire as acq  # noqa: E402

_ACQ_PATH = _SERVER_CODE / "services" / "google_picker" / "acquire.py"

# Not real -- shapes. The point is that these strings are asserted never
# to appear in a log line or an exception message.
_FAKE_ACCESS = "ya29.A0ARrdaM_notARealAccessTokenJustTheShape"
_FAKE_BASE_URL = "https://lh3.googleusercontent.com/lr/NOT-A-REAL-BASE-URL-abc"

# The enum values `import_repository` accepts. Copied rather than
# imported: importing the repository would pull a database module into a
# suite that is deliberately DB-free. Source of truth is
# server/code/api/services/import_repository.py:96 and :100.
_TAKEN_AT_SOURCES = ("exif", "provider_metadata", "filename_guess",
                     "operator", "unknown")
_LOCATION_SOURCES = ("exif_gps", "provider_metadata", "typed_address",
                     "operator", "unknown")


# ---------------------------------------------------------------- byte fixtures

def _pad(prefix: bytes, size: int = 64) -> bytes:
    return prefix + b"\x00" * size


_JPEG = (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01"
         b"\x00\x00" + b"\x11" * 128 + b"\xff\xd9")
_PNG = _pad(b"\x89PNG\r\n\x1a\n")
_GIF87 = _pad(b"GIF87a")
_GIF89 = _pad(b"GIF89a")
_TIFF_LE = _pad(b"II*\x00")
_TIFF_BE = _pad(b"MM\x00*")
_WEBP = b"RIFF" + b"\x40\x00\x00\x00" + b"WEBP" + b"VP8 " + b"\x00" * 48
_HEIC = b"\x00\x00\x00\x18" + b"ftyp" + b"heic" + b"\x00" * 48
_MP4 = b"\x00\x00\x00\x18" + b"ftyp" + b"isom" + b"\x00" * 48
_AVI = b"RIFF" + b"\x40\x00\x00\x00" + b"AVI " + b"\x00" * 48
_TEXT = b"this is prose, not an image, and it never becomes one."


# ---------------------------------------------------------------- the doubles

class _Boom(Exception):
    """Stands in for requests.RequestException.

    Its message carries the full URL on purpose: that is exactly what a
    real transport error does, and it is what the leak assertions are
    checking has not been passed through.
    """


class _FakeResponse:
    def __init__(self, status_code=200, chunks=(), headers=None,
                 raise_at=None):
        self.status_code = status_code
        self.headers = dict(headers or {})
        self._chunks = list(chunks)
        self._raise_at = raise_at
        self.closed = False
        self.iterated = False

    def iter_content(self, chunk_size=None):
        self.iterated = True
        for index, chunk in enumerate(self._chunks):
            if self._raise_at is not None and index == self._raise_at:
                raise _Boom("HTTPSConnectionPool: failed for %s=d"
                            % _FAKE_BASE_URL)
            yield chunk

    def close(self):
        self.closed = True


class _FakeRequests:
    RequestException = _Boom

    def __init__(self):
        self.calls = []
        self.response = None
        self.raise_on_get = None

    def get(self, url, headers=None, stream=False, timeout=None):
        self.calls.append({"url": url, "headers": dict(headers or {}),
                           "stream": stream, "timeout": timeout})
        if self.raise_on_get is not None:
            raise self.raise_on_get
        return self.response


class _LogCatcher(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        try:
            self.lines.append(record.getMessage() % () if not record.args
                              else record.getMessage())
        except Exception:
            self.lines.append(str(record.msg))

    def blob(self):
        return "\n".join(self.lines)


# ------------------------------------------------------------------- the base

class _Base(unittest.TestCase):
    def setUp(self):
        self.http = _FakeRequests()
        self._real_requests = acq.requests
        acq.requests = self.http

        self.logs = _LogCatcher()
        self._logger = logging.getLogger("code.services.google_picker.acquire")
        self._old_level = self._logger.level
        self._logger.addHandler(self.logs)
        self._logger.setLevel(logging.DEBUG)

        # Captured HERE rather than in the swap helper on purpose. A
        # helper that re-captures on every call will, the second time it
        # is called inside one test, save the DOUBLE as the original and
        # restore that for the rest of the process -- which silently
        # turns the real-bytes tests below into more double tests.
        self._real_exif = acq.extract_exif

        self.tmp = tempfile.mkdtemp(prefix="picker-2b-test-")
        self._saved_env = {k: os.environ.get(k)
                           for k in (acq.MAX_BYTES_ENV, acq.DATA_DIR_ENV)}

    def tearDown(self):
        acq.extract_exif = self._real_exif
        acq.requests = self._real_requests
        self._logger.removeHandler(self.logs)
        self._logger.setLevel(self._old_level)
        shutil.rmtree(self.tmp, ignore_errors=True)
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    # -- helpers ----------------------------------------------------------

    def serve(self, chunks, status=200, headers=None, raise_at=None):
        self.http.response = _FakeResponse(status_code=status, chunks=chunks,
                                           headers=headers, raise_at=raise_at)
        return self.http.response

    def download(self, **kw):
        kw.setdefault("item_id", "m-1")
        kw.setdefault("tmp_dir", self.tmp)
        return acq.download_original(_FAKE_ACCESS, _FAKE_BASE_URL, **kw)

    def assertTempDirEmpty(self):
        self.assertEqual(sorted(os.listdir(self.tmp)), [],
                         "a refused download left bytes on disk")

    def assertNothingLeaked(self, *extra_texts):
        blob = self.logs.blob() + "\n" + "\n".join(str(t) for t in extra_texts)
        for secret, label in ((_FAKE_ACCESS, "the access token"),
                              (_FAKE_BASE_URL, "the download URL"),
                              ("Bearer", "an Authorization header")):
            self.assertNotIn(secret, blob,
                             "%s reached a log line or an error message"
                             % label)


# ------------------------------------------------------------------ sniffing

class TestSniff(_Base):
    def test_every_supported_signature_is_recognised(self):
        for raw, expected in ((_JPEG, ("image/jpeg", ".jpg")),
                              (_PNG, ("image/png", ".png")),
                              (_GIF87, ("image/gif", ".gif")),
                              (_GIF89, ("image/gif", ".gif")),
                              (_TIFF_LE, ("image/tiff", ".tif")),
                              (_TIFF_BE, ("image/tiff", ".tif")),
                              (_WEBP, ("image/webp", ".webp")),
                              (_HEIC, ("image/heic", ".heic"))):
            self.assertEqual(acq.sniff_image(raw), expected)

    def test_every_extension_it_can_return_is_stageable(self):
        """The sniffer and the staging whitelist cannot drift apart."""
        for raw in (_JPEG, _PNG, _GIF89, _TIFF_LE, _WEBP, _HEIC):
            _, ext = acq.sniff_image(raw)
            self.assertIn(ext, acq.VERIFIED_EXTENSIONS)

    def test_video_is_refused(self):
        """The Picker returns VIDEO items. This lane has no video
        evidence story, so a movie is unsupported content rather than a
        half-ingested photo."""
        self.assertIsNone(acq.sniff_image(_MP4))

    def test_a_riff_container_that_is_not_webp_is_refused(self):
        self.assertIsNone(acq.sniff_image(_AVI))

    def test_prose_is_refused(self):
        self.assertIsNone(acq.sniff_image(_TEXT))

    def test_too_few_bytes_is_refused_rather_than_guessed(self):
        self.assertIsNone(acq.sniff_image(b"\xff\xd8"))
        self.assertIsNone(acq.sniff_image(b""))

    def test_non_bytes_input_is_refused(self):
        self.assertIsNone(acq.sniff_image(None))
        self.assertIsNone(acq.sniff_image("\xff\xd8\xff a string"))

    def test_bytearray_is_accepted(self):
        self.assertEqual(acq.sniff_image(bytearray(_PNG)),
                         ("image/png", ".png"))


# ---------------------------------------------------------------------- cap

class TestMaxBytes(_Base):
    def test_unset_uses_the_default(self):
        os.environ.pop(acq.MAX_BYTES_ENV, None)
        self.assertEqual(acq.max_bytes(), acq.DEFAULT_MAX_BYTES)

    def test_a_valid_value_is_honoured(self):
        os.environ[acq.MAX_BYTES_ENV] = "1048576"
        self.assertEqual(acq.max_bytes(), 1048576)

    def test_it_is_read_per_call_not_cached_at_import(self):
        os.environ[acq.MAX_BYTES_ENV] = "1048576"
        self.assertEqual(acq.max_bytes(), 1048576)
        os.environ[acq.MAX_BYTES_ENV] = "2097152"
        self.assertEqual(acq.max_bytes(), 2097152)

    def test_garbage_falls_back_loudly_rather_than_taking_the_lane_down(self):
        os.environ[acq.MAX_BYTES_ENV] = "fifty megabytes please"
        self.assertEqual(acq.max_bytes(), acq.DEFAULT_MAX_BYTES)
        self.assertIn("not an integer", self.logs.blob())

    def test_out_of_range_values_fall_back(self):
        for raw in ("0", "-1", "12", str(64 * 1024 * 1024 * 1024)):
            os.environ[acq.MAX_BYTES_ENV] = raw
            self.assertEqual(acq.max_bytes(), acq.DEFAULT_MAX_BYTES)


# ---------------------------------------------------------------- downloading

class TestDownloadHappyPath(_Base):
    def test_it_returns_verified_facts_about_the_bytes(self):
        self.serve([_JPEG])
        out = self.download()
        self.addCleanup(lambda: acq._unlink(out["tmp_path"]))
        self.assertEqual(out["byte_size"], len(_JPEG))
        self.assertEqual(out["file_hash"], hashlib.sha256(_JPEG).hexdigest())
        self.assertEqual(out["verified_mime"], "image/jpeg")
        self.assertEqual(out["verified_ext"], ".jpg")
        self.assertTrue(os.path.isfile(out["tmp_path"]))
        self.assertEqual(Path(out["tmp_path"]).read_bytes(), _JPEG)

    def test_chunked_delivery_reassembles_exactly(self):
        self.serve([_JPEG[:5], _JPEG[5:20], _JPEG[20:]])
        out = self.download()
        self.addCleanup(lambda: acq._unlink(out["tmp_path"]))
        self.assertEqual(Path(out["tmp_path"]).read_bytes(), _JPEG)
        self.assertEqual(out["file_hash"], hashlib.sha256(_JPEG).hexdigest())

    def test_it_asks_for_the_original_not_the_display_copy(self):
        """Without the `=d` suffix Google serves a re-encode, which looks
        fine and has had its EXIF stripped -- the exact metadata this
        lane exists to read."""
        self.serve([_JPEG])
        out = self.download()
        self.addCleanup(lambda: acq._unlink(out["tmp_path"]))
        self.assertEqual(self.http.calls[0]["url"], _FAKE_BASE_URL + "=d")

    def test_it_sends_the_bearer_token_and_streams(self):
        self.serve([_JPEG])
        out = self.download()
        self.addCleanup(lambda: acq._unlink(out["tmp_path"]))
        call = self.http.calls[0]
        self.assertEqual(call["headers"]["Authorization"],
                         "Bearer " + _FAKE_ACCESS)
        self.assertIs(call["stream"], True)
        self.assertIsNotNone(call["timeout"])

    def test_the_response_is_closed(self):
        resp = self.serve([_JPEG])
        out = self.download()
        self.addCleanup(lambda: acq._unlink(out["tmp_path"]))
        self.assertTrue(resp.closed)

    def test_a_successful_download_logs_counts_not_urls(self):
        self.serve([_JPEG])
        out = self.download()
        self.addCleanup(lambda: acq._unlink(out["tmp_path"]))
        self.assertIn("downloaded item m-1", self.logs.blob())
        self.assertNothingLeaked()


class TestDownloadCap(_Base):
    def test_a_declared_oversize_is_refused_before_a_byte_is_read(self):
        resp = self.serve([_JPEG], headers={"Content-Length": "999999999"})
        with self.assertRaises(acq.AcquireError) as caught:
            self.download(cap=1024)
        self.assertEqual(caught.exception.reason, "too_large")
        self.assertFalse(caught.exception.retryable)
        self.assertFalse(resp.iterated, "it read the body anyway")
        self.assertTempDirEmpty()

    def test_a_lying_content_length_is_caught_mid_stream(self):
        self.serve([_JPEG, b"\x00" * 4096],
                   headers={"Content-Length": "10"})
        with self.assertRaises(acq.AcquireError) as caught:
            self.download(cap=1024)
        self.assertEqual(caught.exception.reason, "too_large")
        self.assertTempDirEmpty()

    def test_a_missing_content_length_is_not_a_free_pass(self):
        self.serve([b"\x00" * 2048 for _ in range(4)])
        with self.assertRaises(acq.AcquireError) as caught:
            self.download(cap=1024)
        self.assertEqual(caught.exception.reason, "too_large")
        self.assertTempDirEmpty()

    def test_an_unparseable_content_length_does_not_crash_the_download(self):
        self.serve([_JPEG], headers={"Content-Length": "about eight kay"})
        out = self.download()
        self.addCleanup(lambda: acq._unlink(out["tmp_path"]))
        self.assertEqual(out["byte_size"], len(_JPEG))

    def test_the_cap_defaults_to_the_environment(self):
        os.environ[acq.MAX_BYTES_ENV] = str(64 * 1024)
        self.serve([b"\x89PNG\r\n\x1a\n"] + [b"\x00" * 8192] * 16)
        with self.assertRaises(acq.AcquireError) as caught:
            self.download()
        self.assertEqual(caught.exception.reason, "too_large")
        self.assertIn(acq.MAX_BYTES_ENV, str(caught.exception))


class TestDownloadContentRefusal(_Base):
    def test_a_video_is_refused_and_leaves_nothing_behind(self):
        self.serve([_MP4])
        with self.assertRaises(acq.AcquireError) as caught:
            self.download()
        self.assertEqual(caught.exception.reason, "unsupported_content")
        self.assertFalse(caught.exception.retryable,
                         "a movie does not become a photo on retry")
        self.assertTempDirEmpty()

    def test_prose_is_refused_rather_than_saved_as_jpg(self):
        """`photo_intake/storage.py:_safe_ext` falls back to `.jpg` for
        anything it does not recognise. Spec 12.1 names that as the
        behaviour this lane must not copy."""
        self.serve([_TEXT])
        with self.assertRaises(acq.AcquireError) as caught:
            self.download()
        self.assertEqual(caught.exception.reason, "unsupported_content")
        self.assertNotIn(".jpg", str(caught.exception))
        self.assertTempDirEmpty()

    def test_a_body_too_short_to_identify_is_refused(self):
        self.serve([b"\xff\xd8"])
        with self.assertRaises(acq.AcquireError) as caught:
            self.download()
        self.assertEqual(caught.exception.reason, "unsupported_content")
        self.assertTempDirEmpty()

    def test_an_empty_body_is_retryable_not_a_content_verdict(self):
        self.serve([])
        with self.assertRaises(acq.AcquireError) as caught:
            self.download()
        self.assertEqual(caught.exception.reason, "empty_body")
        self.assertTrue(caught.exception.retryable)
        self.assertTempDirEmpty()

    def test_the_signature_is_read_across_chunk_boundaries(self):
        self.serve([_PNG[:3], _PNG[3:6], _PNG[6:]])
        out = self.download()
        self.addCleanup(lambda: acq._unlink(out["tmp_path"]))
        self.assertEqual(out["verified_mime"], "image/png")

    def test_a_declared_mime_type_cannot_rescue_bad_bytes(self):
        self.serve([_TEXT], headers={"Content-Type": "image/jpeg"})
        with self.assertRaises(acq.AcquireError) as caught:
            self.download()
        self.assertEqual(caught.exception.reason, "unsupported_content")


class TestDownloadUpstreamErrors(_Base):
    def _expect(self, status, reason, retryable):
        self.serve([_JPEG], status=status)
        with self.assertRaises(acq.AcquireError) as caught:
            self.download()
        self.assertEqual(caught.exception.reason, reason,
                         "HTTP %d mapped wrong" % status)
        self.assertEqual(caught.exception.retryable, retryable,
                         "HTTP %d retryability wrong" % status)
        self.assertEqual(caught.exception.status, status)
        return caught.exception

    def test_an_expired_download_url_is_retryable(self):
        """`baseUrl` is live for about an hour. A 401 or 403 here means
        the run outlived it, and re-listing the session mints new ones --
        so this is the single most important failure to get right."""
        for status in (401, 403):
            exc = self._expect(status, "base_url_expired", True)
            self.assertIn("re-list", str(exc))

    def test_a_missing_item_is_not_retryable(self):
        self._expect(404, "item_not_found", False)

    def test_rate_limiting_is_retryable(self):
        self._expect(429, "upstream_rate_limited", True)

    def test_server_errors_are_retryable(self):
        for status in (500, 502, 503):
            self._expect(status, "upstream_error", True)

    def test_other_client_errors_are_not_retryable(self):
        self._expect(400, "upstream_error", False)

    def test_no_upstream_failure_leaves_bytes_behind(self):
        for status in (400, 401, 403, 404, 429, 500, 503):
            self.serve([_JPEG], status=status)
            with self.assertRaises(acq.AcquireError):
                self.download()
            self.assertTempDirEmpty()

    def test_the_response_is_closed_even_when_it_fails(self):
        resp = self.serve([_JPEG], status=500)
        with self.assertRaises(acq.AcquireError):
            self.download()
        self.assertTrue(resp.closed)


class TestDownloadTransportErrors(_Base):
    def test_a_failure_to_connect_is_network_and_retryable(self):
        self.http.raise_on_get = _Boom(
            "HTTPSConnectionPool: max retries for %s=d" % _FAKE_BASE_URL)
        with self.assertRaises(acq.AcquireError) as caught:
            self.download()
        self.assertEqual(caught.exception.reason, "network")
        self.assertTrue(caught.exception.retryable)
        self.assertTempDirEmpty()

    def test_a_connect_failure_does_not_pass_the_url_through(self):
        """A real requests exception stringifies to a message containing
        the full URL. Only the class name may be reported."""
        self.http.raise_on_get = _Boom(
            "HTTPSConnectionPool: max retries for %s=d" % _FAKE_BASE_URL)
        with self.assertRaises(acq.AcquireError) as caught:
            self.download()
        self.assertIn("_Boom", str(caught.exception))
        self.assertNothingLeaked(str(caught.exception))

    def test_an_interrupted_stream_is_network_and_leaves_nothing(self):
        self.serve([_JPEG[:20], _JPEG[20:]], raise_at=1)
        with self.assertRaises(acq.AcquireError) as caught:
            self.download()
        self.assertEqual(caught.exception.reason, "network")
        self.assertTrue(caught.exception.retryable)
        self.assertTempDirEmpty()
        self.assertNothingLeaked(str(caught.exception))


class TestDownloadInputRefusal(_Base):
    def test_a_missing_token_is_refused_without_calling_google(self):
        with self.assertRaises(acq.AcquireError) as caught:
            acq.download_original("", _FAKE_BASE_URL, item_id="m-1",
                                  tmp_dir=self.tmp)
        self.assertEqual(caught.exception.reason, "invalid_request")
        self.assertFalse(caught.exception.retryable)
        self.assertEqual(self.http.calls, [])

    def test_a_missing_base_url_is_refused_without_calling_google(self):
        with self.assertRaises(acq.AcquireError) as caught:
            acq.download_original(_FAKE_ACCESS, "   ", item_id="m-1",
                                  tmp_dir=self.tmp)
        self.assertEqual(caught.exception.reason, "invalid_request")
        self.assertEqual(self.http.calls, [])


class TestFailureVocabulary(_Base):
    def test_every_reason_is_classified_exactly_once(self):
        """A new reason cannot be added without deciding, in data,
        whether re-running ingest can fix it."""
        overlap = set(acq.RETRYABLE_REASONS) & set(acq.PERMANENT_REASONS)
        self.assertEqual(overlap, set())

    def test_every_reason_the_module_can_raise_is_declared(self):
        tree = ast.parse(_ACQ_PATH.read_text(encoding="utf-8"))
        raised = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name != "AcquireError":
                continue
            for kw in node.keywords:
                if kw.arg == "reason" and isinstance(kw.value, ast.Constant):
                    raised.add(kw.value.value)
        self.assertTrue(raised, "no reasons found -- the scan broke")
        declared = set(acq.RETRYABLE_REASONS) | set(acq.PERMANENT_REASONS)
        self.assertEqual(raised - declared, set(),
                         "a failure reason is raised but not classified as "
                         "retryable or permanent")


# ------------------------------------------------------------------- metadata

class _FakeExif:
    """Stands in for photo_intake.exif.extract_exif.

    The branching this module owns is what these tests are for; the EXIF
    reader itself is Phase-2-of-another-work-order code with its own
    suite. One real-bytes test below proves the two are actually wired.
    """

    def __init__(self, captured_at=None, lat=None, lng=None,
                 present_unparseable=False, raw=None, boom=False):
        self.captured_at = captured_at
        self.lat = lat
        self.lng = lng
        self.present_unparseable = present_unparseable
        self.raw = raw or {}
        self.boom = boom

    def __call__(self, path):
        if self.boom:
            raise RuntimeError("Pillow said no")
        gps = {"latitude": self.lat, "longitude": self.lng,
               "source": "exif_gps" if self.lat is not None else "unknown"}
        if self.present_unparseable:
            gps["present_unparseable"] = True
        return {"captured_at": self.captured_at, "gps": gps,
                "raw_exif": self.raw}


class TestEvidenceMetadata(_Base):
    def use(self, **kw):
        # `_Base.tearDown` owns the restore; see the note there.
        acq.extract_exif = _FakeExif(**kw)

    def test_exif_date_and_gps_are_both_taken_from_the_file(self):
        self.use(captured_at="2026-04-11 09:15:00", lat=48.2082, lng=16.3738)
        out = acq.read_evidence_metadata("/tmp/whatever")
        self.assertEqual(out["taken_at"], "2026-04-11 09:15:00")
        self.assertEqual(out["taken_at_source"], "exif")
        self.assertAlmostEqual(out["latitude"], 48.2082)
        self.assertAlmostEqual(out["longitude"], 16.3738)
        self.assertEqual(out["location_source"], "exif_gps")

    def test_no_exif_date_falls_back_to_the_provider(self):
        self.use()
        out = acq.read_evidence_metadata(
            "/tmp/whatever", provider_create_time="2026-04-11T09:15:00Z")
        self.assertEqual(out["taken_at"], "2026-04-11 09:15:00")
        self.assertEqual(out["taken_at_source"], "provider_metadata")

    def test_exif_date_beats_the_provider_date(self):
        self.use(captured_at="2019-07-04 12:00:00")
        out = acq.read_evidence_metadata(
            "/tmp/whatever", provider_create_time="2026-04-11T09:15:00Z")
        self.assertEqual(out["taken_at"], "2019-07-04 12:00:00")
        self.assertEqual(out["taken_at_source"], "exif")

    def test_no_date_anywhere_is_unknown_not_a_guess(self):
        self.use()
        out = acq.read_evidence_metadata("/tmp/whatever")
        self.assertIsNone(out["taken_at"])
        self.assertEqual(out["taken_at_source"], "unknown")

    def test_picker_metadata_is_never_a_gps_source(self):
        """The rule that makes this suite necessary.
        `CANDIDATE_LOCATION_SOURCES` permits `provider_metadata`, so the
        schema would happily accept a Picker-derived location. Nothing
        but this stops it."""
        self.use(captured_at=None)
        out = acq.read_evidence_metadata(
            "/tmp/whatever", provider_create_time="2026-04-11T09:15:00Z")
        self.assertEqual(out["taken_at_source"], "provider_metadata")
        self.assertIsNone(out["latitude"])
        self.assertIsNone(out["longitude"])
        self.assertEqual(out["location_source"], "unknown")

    def test_the_date_falls_back_but_the_location_does_not(self):
        self.use(captured_at=None, lat=None, lng=None)
        out = acq.read_evidence_metadata(
            "/tmp/whatever", provider_create_time="2026-04-11T09:15:00Z")
        self.assertNotEqual(out["taken_at_source"], out["location_source"])
        self.assertEqual((out["taken_at_source"], out["location_source"]),
                         ("provider_metadata", "unknown"))

    def test_a_half_gps_fix_is_no_gps_fix(self):
        self.use(lat=48.2082, lng=None)
        out = acq.read_evidence_metadata("/tmp/whatever")
        self.assertIsNone(out["latitude"])
        self.assertEqual(out["location_source"], "unknown")

    def test_the_unparseable_gps_third_state_survives(self):
        """`photo_intake/exif.py:224-274` distinguishes 'no GPS tag' from
        'GPS tag present but unreadable'. There is no enum value and no
        candidate column for the second, so it has to leave this
        function intact or it is lost."""
        self.use(present_unparseable=True)
        out = acq.read_evidence_metadata("/tmp/whatever")
        self.assertTrue(out["gps_present_unparseable"])
        self.assertIsNone(out["latitude"])
        self.assertEqual(out["location_source"], "unknown")

    def test_absent_gps_is_distinguishable_from_unreadable_gps(self):
        self.use()
        out = acq.read_evidence_metadata("/tmp/whatever")
        self.assertFalse(out["gps_present_unparseable"])
        self.assertEqual(out["location_source"], "unknown")

    def test_unparseable_provider_times_are_dropped_not_truncated(self):
        self.use()
        for raw in ("", "   ", "yesterday", "2026-13-45T99:99:99Z",
                    "2026-04", None, 1744362900):
            out = acq.read_evidence_metadata("/tmp/whatever",
                                             provider_create_time=raw)
            self.assertIsNone(out["taken_at"], "accepted %r" % (raw,))
            self.assertEqual(out["taken_at_source"], "unknown")

    def test_fractional_and_offset_provider_times_normalise(self):
        self.use()
        for raw in ("2026-04-11T09:15:00.123456Z", "2026-04-11T09:15:00+02:00",
                    "2026-04-11 09:15:00"):
            out = acq.read_evidence_metadata("/tmp/whatever",
                                             provider_create_time=raw)
            self.assertEqual(out["taken_at"], "2026-04-11 09:15:00")

    def test_an_exif_reader_failure_is_not_an_ingest_failure(self):
        """A photo whose EXIF cannot be read is still evidence. It lands
        with unknown metadata rather than failing the item."""
        self.use(boom=True)
        out = acq.read_evidence_metadata("/tmp/whatever",
                                         provider_create_time="2026-04-11T09:15:00Z")
        self.assertEqual(out["taken_at_source"], "provider_metadata")
        self.assertEqual(out["location_source"], "unknown")
        self.assertIn("EXIF read failed", self.logs.blob())

    def test_every_source_it_returns_is_a_value_the_repository_accepts(self):
        for kwargs, provider in (({}, None),
                                 ({}, "2026-04-11T09:15:00Z"),
                                 ({"captured_at": "2026-04-11 09:15:00"}, None),
                                 ({"lat": 1.0, "lng": 2.0}, None),
                                 ({"present_unparseable": True}, None),
                                 ({"boom": True}, None)):
            self.use(**kwargs)
            out = acq.read_evidence_metadata("/tmp/x",
                                             provider_create_time=provider)
            self.assertIn(out["taken_at_source"], _TAKEN_AT_SOURCES)
            self.assertIn(out["location_source"], _LOCATION_SOURCES)

    def test_it_never_returns_a_location_source_of_provider_metadata(self):
        for kwargs in ({}, {"captured_at": "2026-04-11 09:15:00"},
                       {"present_unparseable": True}, {"boom": True}):
            self.use(**kwargs)
            out = acq.read_evidence_metadata(
                "/tmp/x", provider_create_time="2026-04-11T09:15:00Z")
            self.assertNotEqual(out["location_source"], "provider_metadata")


class TestEvidenceMetadataOnRealBytes(_Base):
    """One test that does NOT use the double, so the wiring is proven."""

    def setUp(self):
        super().setUp()
        # Without this, a double leaking out of an earlier test would
        # leave these tests passing while proving nothing at all.
        self.assertEqual(
            getattr(acq.extract_exif, "__name__", ""), "extract_exif",
            "a test double is still installed -- the real EXIF reader is "
            "not what these tests are exercising")

    def test_a_real_jpeg_with_no_exif_reads_as_unknown_without_raising(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is not installed in this interpreter")
        path = os.path.join(self.tmp, "plain.jpg")
        Image.new("RGB", (16, 16), (120, 40, 40)).save(path, "JPEG")
        out = acq.read_evidence_metadata(path)
        self.assertIsNone(out["taken_at"])
        self.assertEqual(out["taken_at_source"], "unknown")
        self.assertIsNone(out["latitude"])
        self.assertEqual(out["location_source"], "unknown")
        self.assertFalse(out["gps_present_unparseable"])

    def test_a_real_jpeg_with_an_exif_datetime_reads_as_exif(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is not installed in this interpreter")
        path = os.path.join(self.tmp, "dated.jpg")
        image = Image.new("RGB", (16, 16), (40, 120, 40))
        exif = image.getexif()
        exif[0x0132] = "2019:07:04 12:34:56"      # DateTime
        exif[0x010F] = "TestCam"                  # Make
        exif[0x0110] = "TestModel"                # Model
        image.save(path, "JPEG", exif=exif)
        out = acq.read_evidence_metadata(
            path, provider_create_time="2026-04-11T09:15:00Z")
        self.assertEqual(out["taken_at_source"], "exif",
                         "the real EXIF reader is not wired to real bytes")
        self.assertTrue(str(out["taken_at"]).startswith("2019-07-04"))

    def test_the_downloaded_temp_file_is_what_the_reader_reads(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is not installed in this interpreter")
        source = os.path.join(self.tmp, "source.jpg")
        Image.new("RGB", (24, 24), (10, 10, 200)).save(source, "JPEG")
        raw = Path(source).read_bytes()
        os.unlink(source)
        self.serve([raw])
        out = self.download()
        self.addCleanup(lambda: acq._unlink(out["tmp_path"]))
        self.assertEqual(out["verified_mime"], "image/jpeg")
        meta = acq.read_evidence_metadata(out["tmp_path"])
        self.assertEqual(meta["location_source"], "unknown")


# -------------------------------------------------------------------- staging

class TestStagingPath(_Base):
    def setUp(self):
        super().setUp()
        os.environ[acq.DATA_DIR_ENV] = self.tmp

    def test_the_layout_is_exactly_what_phase_three_will_look_for(self):
        path = acq.staging_dir_for("batch-1", "cand-2")
        self.assertEqual(
            path, Path(self.tmp) / "import_staging" / "batch-1" / "cand-2")

    def test_the_root_name_is_the_one_the_spec_names(self):
        self.assertEqual(acq.STAGING_ROOT, "import_staging")

    def test_an_unset_data_dir_is_refused_rather_than_defaulted(self):
        os.environ.pop(acq.DATA_DIR_ENV, None)
        with self.assertRaises(acq.AcquireError) as caught:
            acq.staging_dir_for("batch-1", "cand-2")
        self.assertEqual(caught.exception.reason, "data_dir_unset")
        self.assertFalse(caught.exception.retryable)

    def test_traversal_shaped_ids_are_refused(self):
        for bad in ("..", "../..", "a/../..", "a/b", "a\\b", ".hidden",
                    "-leading", "with space", "sem;colon", "x" * 200):
            with self.assertRaises(acq.AcquireError,
                                   msg="accepted %r" % bad) as caught:
                acq.staging_dir_for(bad, "cand-2")
            self.assertIn(caught.exception.reason,
                          ("unsafe_identifier", "invalid_request"))

    def test_a_bad_candidate_id_is_refused_too(self):
        with self.assertRaises(acq.AcquireError) as caught:
            acq.staging_dir_for("batch-1", "../escape")
        self.assertEqual(caught.exception.reason, "unsafe_identifier")

    def test_an_empty_id_names_the_field_not_the_value(self):
        with self.assertRaises(acq.AcquireError) as caught:
            acq.staging_dir_for("", "cand-2")
        self.assertEqual(caught.exception.reason, "invalid_request")
        self.assertIn("batch_id", str(caught.exception))

    def test_a_refused_value_is_withheld_from_the_message(self):
        with self.assertRaises(acq.AcquireError) as caught:
            acq.staging_dir_for("../../etc/passwd", "cand-2")
        self.assertNotIn("passwd", str(caught.exception))

    def test_a_real_uuid_is_accepted(self):
        path = acq.staging_dir_for("202718fb-314e-40d0-b748-c6525fcdaf68",
                                   "338dfc4b-15f4-438a-aeee-357a7d4c8810")
        self.assertTrue(str(path).endswith(
            "338dfc4b-15f4-438a-aeee-357a7d4c8810"))


class TestStageOriginal(_Base):
    def setUp(self):
        super().setUp()
        self.data_dir = os.path.join(self.tmp, "data")
        os.makedirs(self.data_dir, exist_ok=True)
        os.environ[acq.DATA_DIR_ENV] = self.data_dir
        self.work = os.path.join(self.tmp, "work")
        os.makedirs(self.work, exist_ok=True)

    def _temp_file(self, payload=_JPEG, name="incoming.part"):
        path = os.path.join(self.work, name)
        Path(path).write_bytes(payload)
        return path

    def test_it_moves_the_bytes_and_leaves_no_source(self):
        src = self._temp_file()
        target = acq.stage_original(src, "batch-1", "cand-2", ".jpg")
        self.assertFalse(os.path.exists(src), "the temp file survived")
        self.assertTrue(os.path.isfile(target))
        self.assertEqual(Path(target).read_bytes(), _JPEG)
        self.assertTrue(target.endswith(os.path.join(
            "import_staging", "batch-1", "cand-2", "original.jpg")))

    def test_it_creates_the_directory_tree(self):
        src = self._temp_file()
        acq.stage_original(src, "batch-9", "cand-9", ".jpg")
        self.assertTrue(os.path.isdir(os.path.join(
            self.data_dir, "import_staging", "batch-9", "cand-9")))

    def test_a_reingest_with_a_new_extension_leaves_exactly_one_original(self):
        """Phase 3 requires exactly one `original.*`. The same photo
        re-exported as PNG must not leave the JPEG beside it."""
        acq.stage_original(self._temp_file(), "batch-1", "cand-2", ".jpg")
        acq.stage_original(self._temp_file(_PNG, "second.part"),
                           "batch-1", "cand-2", ".png")
        staged = sorted(p.name for p in
                        acq.staging_dir_for("batch-1", "cand-2")
                        .glob("original.*"))
        self.assertEqual(staged, ["original.png"])

    def test_a_reingest_with_the_same_extension_overwrites_in_place(self):
        acq.stage_original(self._temp_file(), "batch-1", "cand-2", ".jpg")
        newer = _JPEG[:-2] + b"\x22\xff\xd9"
        acq.stage_original(self._temp_file(newer, "second.part"),
                           "batch-1", "cand-2", ".jpg")
        directory = acq.staging_dir_for("batch-1", "cand-2")
        staged = sorted(p.name for p in directory.glob("original.*"))
        self.assertEqual(staged, ["original.jpg"])
        self.assertEqual((directory / "original.jpg").read_bytes(), newer)

    def test_an_unverified_extension_is_refused(self):
        src = self._temp_file()
        for bad in (".mp4", ".exe", ".jpeg", "", ".JPG", None):
            with self.assertRaises(acq.AcquireError,
                                   msg="accepted %r" % (bad,)) as caught:
                acq.stage_original(src, "batch-1", "cand-2", bad)
            self.assertEqual(caught.exception.reason, "unsupported_content")
        self.assertTrue(os.path.exists(src), "a refusal consumed the source")

    def test_a_vanished_temp_file_is_a_retryable_staging_failure(self):
        with self.assertRaises(acq.AcquireError) as caught:
            acq.stage_original(os.path.join(self.work, "gone.part"),
                               "batch-1", "cand-2", ".jpg")
        self.assertEqual(caught.exception.reason, "staging_failed")
        self.assertTrue(caught.exception.retryable)

    def test_an_unsafe_id_is_refused_before_anything_is_written(self):
        src = self._temp_file()
        with self.assertRaises(acq.AcquireError):
            acq.stage_original(src, "../escape", "cand-2", ".jpg")
        self.assertTrue(os.path.exists(src))
        self.assertFalse(os.path.exists(
            os.path.join(self.data_dir, "import_staging")))

    def test_the_full_download_to_staging_round_trip(self):
        self.serve([_JPEG])
        out = self.download()
        target = acq.stage_original(out["tmp_path"], "batch-1", "cand-2",
                                    out["verified_ext"])
        self.assertEqual(Path(target).read_bytes(), _JPEG)
        self.assertEqual(
            hashlib.sha256(Path(target).read_bytes()).hexdigest(),
            out["file_hash"],
            "the hash recorded at download does not describe the staged file")
        self.assertNothingLeaked()


# ------------------------------------------------------------- the phase wall

class TestPhaseWall(_Base):
    def test_the_module_opens_no_database_and_creates_no_candidate(self):
        """Asserted as an exact import set, so a NEW collaborator fails
        this even if nobody thought to add it to a blocklist -- and so a
        prose mention of `candidate_create` in a docstring, which is
        there on purpose, does not read as a dependency."""
        tree = ast.parse(_ACQ_PATH.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add("." * node.level + (node.module or ""))
        self.assertEqual(
            imported,
            {"__future__", "logging", "os", "re", "shutil", "tempfile",
             "datetime", "pathlib", "typing", "requests",
             "..photo_intake.dedupe", "..photo_intake.exif",
             "..photo_intake.metadata_trust"},
            "the acquisition module grew a collaborator; the database and "
            "the route belong to the next step, not here")

    def test_it_reuses_the_one_hasher_rather_than_writing_a_second(self):
        """Spec 12.6: sha256_file lives in photo_intake/dedupe.py."""
        source = _ACQ_PATH.read_text(encoding="utf-8")
        self.assertIn("from ..photo_intake.dedupe import sha256_file", source)
        self.assertNotIn("hashlib", source)

    def test_no_route_is_wired_to_acquisition_yet(self):
        """A module with no caller is the point: it is reviewable on its
        own, and the ingest route is the next commit."""
        router = (_SERVER_CODE / "api" / "routers" / "google_picker.py"
                  ).read_text(encoding="utf-8")
        for name in ("acquire", "download_original", "list_media_items"):
            self.assertNotIn(name, router,
                             "the ingest route is the next step, not this one")

    def test_the_data_directory_is_read_from_configuration(self):
        """`C:\\hornelore_data` must never appear in product logic."""
        source = _ACQ_PATH.read_text(encoding="utf-8")
        self.assertNotIn("hornelore_data", source)
        self.assertIn('DATA_DIR_ENV = "DATA_DIR"', source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
