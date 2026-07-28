"""WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01 Phase 2A -- the listing client.

Phase 2A is one function: `picker_client.list_media_items`. It reads
back what the operator picked in Google's UI. It has no database, no
downloads, no staging, no route and no UI, and this suite is written so
that adding any of those quietly would break something.

What is locked here:

  1. PAGING RUNS TO EXHAUSTION OR RAISES. A short list is
     indistinguishable from "the operator picked fewer photos", so a
     listing that cannot finish must never return quietly. A repeated
     page token and an endless token chain both raise.

  2. THE RESPONSE IS VALIDATED, NOT TRUSTED. An item with no id, no
     mediaFile, no baseUrl or no mimeType is a defect, not a row to be
     patched up with defaults. Unknown fields are dropped rather than
     passed through.

  3. NOTHING LEAKS. `baseUrl` is a bearer-scoped download URL and the
     access token is a credential. Neither may appear in any exception
     message or any log line this module produces -- asserted against a
     real captured log stream, not by inspection.

  4. FAILURES ARE TYPED. Every failure is a PickerApiError carrying the
     same `reason` vocabulary Phase 1 established, so 2B's route can map
     them without inventing a second scheme.

  5. THE PHASE WALL. `base_url` is RETURNED (2B cannot download without
     it) and never followed here.

This suite does not need fastapi and does not touch the network:
`requests` is replaced inside picker_client by a recording double.

pytest is not installed in this repo; run with:

    .venv/bin/python -u -m unittest tests.test_google_picker_phase2a
"""
from __future__ import annotations

import ast
import logging
import sys
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

from code.services.google_picker import picker_client as pc  # noqa: E402

_CLIENT_PATH = _SERVER_CODE / "services" / "google_picker" / "picker_client.py"

# Not real -- shapes. The point is that these strings are asserted never
# to appear in a log line or an exception message.
_FAKE_ACCESS = "ya29.A0ARrdaM_notARealAccessTokenJustTheShape"
_FAKE_BASE_URL = "https://lh3.googleusercontent.com/lr/NOT-A-REAL-BASE-URL-abc"

_SESSION = "picker-session-abc123"


def _item(item_id, base_url=_FAKE_BASE_URL, mime="image/jpeg",
          filename="IMG_0001.JPG", create_time="2026-07-27T10:00:00Z",
          media_type="PHOTO", width=4032, height=3024, extra_file=None,
          extra_item=None):
    media_file = {
        "baseUrl": base_url,
        "mimeType": mime,
        "filename": filename,
        "mediaFileMetadata": {
            "width": width,
            "height": height,
            "cameraMake": "Apple",
            "cameraModel": "iPhone 15 Pro",
            "photoMetadata": {"focalLength": 6.86, "isoEquivalent": 50},
        },
    }
    if extra_file:
        media_file.update(extra_file)
    out = {
        "id": item_id,
        "createTime": create_time,
        "type": media_type,
        "mediaFile": media_file,
    }
    if extra_item:
        out.update(extra_item)
    return out


# ---------------------------------------------------------------- doubles


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b"{}"):
        self.status_code = status_code
        self._payload = payload
        self.content = content

    def json(self):
        if self._payload is _NO_JSON:
            raise ValueError("not json")
        return self._payload


_NO_JSON = object()


class _FakeRequests:
    """Stands in for `requests` inside picker_client, recording calls."""

    class RequestException(Exception):
        pass

    def __init__(self):
        self.calls = []          # (method, url, headers)
        self.request_queue = []
        self.factory = None      # callable(call_index) -> _FakeResponse
        self.raise_on_next = None

    def request(self, method, url, headers=None, json=None, timeout=None, **kw):
        self.calls.append((method, url, headers))
        if self.raise_on_next is not None:
            exc = self.raise_on_next
            self.raise_on_next = None
            raise exc
        if self.request_queue:
            return self.request_queue.pop(0)
        if self.factory is not None:
            return self.factory(len(self.calls) - 1)
        return _FakeResponse(200, {"mediaItems": []})


class _LogCatcher(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.lines = []

    def emit(self, record):
        try:
            self.lines.append(record.getMessage())
        except Exception:                                # pragma: no cover
            self.lines.append("<unformattable>")


# ---------------------------------------------------------------- base


class _Base(unittest.TestCase):
    def setUp(self):
        self.http = _FakeRequests()
        self._orig_requests = pc.requests
        pc.requests = self.http

        self.logs = _LogCatcher()
        pc.logger.addHandler(self.logs)
        self._orig_level = pc.logger.level
        pc.logger.setLevel(logging.DEBUG)

    def tearDown(self):
        pc.requests = self._orig_requests
        pc.logger.removeHandler(self.logs)
        pc.logger.setLevel(self._orig_level)

    def list(self, **kw):
        return pc.list_media_items(_FAKE_ACCESS, _SESSION, **kw)

    def assertNothingLeaked(self):
        blob = "\n".join(self.logs.lines)
        self.assertNotIn(_FAKE_ACCESS, blob, "an access token reached a log line")
        self.assertNotIn(_FAKE_BASE_URL, blob, "a baseUrl reached a log line")
        self.assertNotIn("Bearer", blob)


# ---------------------------------------------------------------- shape


class TestNormalization(_Base):

    def test_a_single_page_is_normalized_field_by_field(self):
        self.http.request_queue.append(
            _FakeResponse(200, {"mediaItems": [_item("m-1")]}))
        out = self.list()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0], {
            "media_item_id": "m-1",
            "create_time": "2026-07-27T10:00:00Z",
            "media_type": "PHOTO",
            "mime_type": "image/jpeg",
            "filename": "IMG_0001.JPG",
            "base_url": _FAKE_BASE_URL,
            "width": 4032,
            "height": 3024,
        })

    def test_provider_extras_are_dropped_not_passed_through(self):
        self.http.request_queue.append(_FakeResponse(200, {
            "mediaItems": [_item("m-1", extra_item={"somethingNew": "x"},
                                 extra_file={"alsoNew": "y"})]}))
        keys = set(self.list()[0])
        for absent in ("somethingNew", "alsoNew", "cameraMake", "cameraModel",
                       "photoMetadata", "camera_make", "photo_metadata"):
            self.assertNotIn(absent, keys)

    def test_there_is_no_location_or_byte_size_to_report(self):
        """Recorded as a test because it is the fact Phase 2B is built
        around: coordinates come from EXIF in the bytes and size comes
        from stat(), because the Picker response carries neither."""
        self.http.request_queue.append(
            _FakeResponse(200, {"mediaItems": [_item("m-1")]}))
        keys = set(self.list()[0])
        for absent in ("latitude", "longitude", "location", "byte_size",
                       "size_bytes", "bytes"):
            self.assertNotIn(absent, keys)

    def test_base_url_is_returned_because_2b_needs_it(self):
        self.http.request_queue.append(
            _FakeResponse(200, {"mediaItems": [_item("m-1")]}))
        self.assertEqual(self.list()[0]["base_url"], _FAKE_BASE_URL)

    def test_missing_type_falls_back_to_unspecified(self):
        self.http.request_queue.append(_FakeResponse(200, {
            "mediaItems": [_item("m-1", media_type=None)]}))
        self.assertEqual(self.list()[0]["media_type"], "TYPE_UNSPECIFIED")

    def test_video_type_is_reported_not_filtered(self):
        """2A reports what Google returned. Deciding that a VIDEO is
        unwanted is an ingest policy, and ingest is 2B."""
        self.http.request_queue.append(_FakeResponse(200, {
            "mediaItems": [_item("m-1", media_type="VIDEO",
                                 mime="video/mp4")]}))
        out = self.list()
        self.assertEqual(out[0]["media_type"], "VIDEO")
        self.assertEqual(out[0]["mime_type"], "video/mp4")

    def test_integer_fields_accept_googles_string_spelling(self):
        self.http.request_queue.append(_FakeResponse(200, {
            "mediaItems": [_item("m-1", width="4032", height="3024")]}))
        out = self.list()[0]
        self.assertEqual(out["width"], 4032)
        self.assertEqual(out["height"], 3024)

    def test_unusable_dimensions_become_none_not_zero(self):
        self.http.request_queue.append(_FakeResponse(200, {
            "mediaItems": [_item("m-1", width={"n": 1}, height="wide")]}))
        out = self.list()[0]
        self.assertIsNone(out["width"])
        self.assertIsNone(out["height"])

    def test_missing_filename_is_none(self):
        self.http.request_queue.append(_FakeResponse(200, {
            "mediaItems": [_item("m-1", filename=None)]}))
        self.assertIsNone(self.list()[0]["filename"])


# ---------------------------------------------------------------- refusal


class TestShapeRefusal(_Base):

    def _refuse(self, payload):
        self.http.request_queue.append(_FakeResponse(200, payload))
        with self.assertRaises(pc.PickerApiError) as ctx:
            self.list()
        return ctx.exception

    def test_item_with_no_id_is_refused(self):
        item = _item("m-1")
        del item["id"]
        err = self._refuse({"mediaItems": [item]})
        self.assertIn("no usable id", str(err))
        self.assertEqual(err.reason, "upstream_error")

    def test_blank_id_is_refused(self):
        err = self._refuse({"mediaItems": [_item("   ")]})
        self.assertIn("no usable id", str(err))

    def test_item_with_no_media_file_is_refused(self):
        item = _item("m-1")
        del item["mediaFile"]
        self.assertIn("no mediaFile", str(self._refuse({"mediaItems": [item]})))

    def test_item_with_no_base_url_is_refused(self):
        err = self._refuse({"mediaItems": [_item("m-1", base_url=None)]})
        self.assertIn("no baseUrl", str(err))

    def test_item_with_no_mime_type_is_refused(self):
        err = self._refuse({"mediaItems": [_item("m-1", mime=None)]})
        self.assertIn("no mimeType", str(err))

    def test_a_non_object_item_is_refused(self):
        err = self._refuse({"mediaItems": ["just a string"]})
        self.assertIn("not a JSON object", str(err))

    def test_media_items_that_is_not_a_list_is_refused(self):
        err = self._refuse({"mediaItems": {"m-1": "nope"}})
        self.assertIn("not a list", str(err))

    def test_the_complaint_names_the_position_across_pages(self):
        self.http.request_queue.append(_FakeResponse(200, {
            "mediaItems": [_item("m-1"), _item("m-2")],
            "nextPageToken": "tok-2"}))
        bad = _item("m-3")
        del bad["id"]
        self.http.request_queue.append(_FakeResponse(200, {"mediaItems": [bad]}))
        with self.assertRaises(pc.PickerApiError) as ctx:
            self.list()
        self.assertIn("position 2", str(ctx.exception))

    def test_a_shape_complaint_never_echoes_the_item(self):
        item = _item("m-1")
        del item["id"]
        err = self._refuse({"mediaItems": [item]})
        self.assertNotIn(_FAKE_BASE_URL, str(err))
        self.assertNotIn("IMG_0001", str(err))
        self.assertIn("withheld", str(err))
        self.assertNothingLeaked()


# ---------------------------------------------------------------- paging


class TestPaging(_Base):

    def test_the_query_carries_the_session_and_the_page_size(self):
        self.http.request_queue.append(_FakeResponse(200, {"mediaItems": []}))
        self.list()
        method, url, headers = self.http.calls[0]
        self.assertEqual(method, "GET")
        self.assertIn("/v1/mediaItems?sessionId=%s" % _SESSION, url)
        self.assertIn("pageSize=100", url)
        self.assertNotIn("pageToken", url)

    def test_page_size_is_clamped_at_both_ends(self):
        self.http.request_queue.append(_FakeResponse(200, {"mediaItems": []}))
        self.list(page_size=5000)
        self.assertIn("pageSize=100", self.http.calls[-1][1])
        self.http.request_queue.append(_FakeResponse(200, {"mediaItems": []}))
        self.list(page_size=0)
        self.assertIn("pageSize=1", self.http.calls[-1][1])

    def test_it_follows_the_token_to_exhaustion(self):
        self.http.request_queue.append(_FakeResponse(200, {
            "mediaItems": [_item("m-1"), _item("m-2")],
            "nextPageToken": "tok 2"}))
        self.http.request_queue.append(_FakeResponse(200, {
            "mediaItems": [_item("m-3")], "nextPageToken": "tok-3"}))
        self.http.request_queue.append(_FakeResponse(200, {
            "mediaItems": [_item("m-4")]}))
        out = self.list()
        self.assertEqual([i["media_item_id"] for i in out],
                         ["m-1", "m-2", "m-3", "m-4"])
        self.assertEqual(len(self.http.calls), 3)
        self.assertIn("pageToken=tok%202", self.http.calls[1][1])
        self.assertIn("pageToken=tok-3", self.http.calls[2][1])

    def test_an_empty_selection_is_an_empty_list_not_an_error(self):
        self.http.request_queue.append(_FakeResponse(200, {}))
        self.assertEqual(self.list(), [])

    def test_a_repeated_page_token_raises_instead_of_looping(self):
        def factory(_i):
            return _FakeResponse(200, {"mediaItems": [_item("m-%d" % _i)],
                                       "nextPageToken": "same-token"})
        self.http.factory = factory
        with self.assertRaises(pc.PickerApiError) as ctx:
            self.list()
        self.assertIn("did not advance", str(ctx.exception))
        self.assertEqual(len(self.http.calls), 2)

    def test_an_endless_token_chain_is_capped(self):
        def factory(i):
            return _FakeResponse(200, {"mediaItems": [_item("m-%d" % i)],
                                       "nextPageToken": "tok-%d" % i})
        self.http.factory = factory
        with self.assertRaises(pc.PickerApiError) as ctx:
            self.list()
        self.assertIn("did not terminate", str(ctx.exception))
        self.assertEqual(len(self.http.calls), pc._MAX_PAGES)

    def test_a_blank_next_token_ends_the_listing(self):
        self.http.request_queue.append(_FakeResponse(200, {
            "mediaItems": [_item("m-1")], "nextPageToken": "   "}))
        self.assertEqual(len(self.list()), 1)
        self.assertEqual(len(self.http.calls), 1)

    def test_a_duplicated_id_across_pages_is_kept_once(self):
        self.http.request_queue.append(_FakeResponse(200, {
            "mediaItems": [_item("m-1")], "nextPageToken": "tok-2"}))
        self.http.request_queue.append(_FakeResponse(200, {
            "mediaItems": [_item("m-1"), _item("m-2")]}))
        out = self.list()
        self.assertEqual([i["media_item_id"] for i in out], ["m-1", "m-2"])
        self.assertNothingLeaked()


# ---------------------------------------------------------------- errors


class TestErrors(_Base):

    def _upstream(self, status, payload=None):
        self.http.request_queue.append(_FakeResponse(
            status, payload if payload is not None
            else {"error": {"status": "X", "message": "y"}}))
        with self.assertRaises(pc.PickerApiError) as ctx:
            self.list()
        return ctx.exception

    def test_403_is_named_forbidden(self):
        self.assertEqual(self._upstream(403).reason, "upstream_forbidden")

    def test_404_is_a_missing_session(self):
        err = self._upstream(404)
        self.assertEqual(err.reason, "session_not_found")
        self.assertEqual(err.status, 404)

    def test_429_is_named_rate_limited(self):
        self.assertEqual(self._upstream(429).reason, "upstream_rate_limited")

    def test_500_is_a_generic_upstream_error(self):
        self.assertEqual(self._upstream(500).reason, "upstream_error")

    def test_a_transport_failure_is_typed_not_a_raw_exception(self):
        self.http.raise_on_next = pc.requests.RequestException("dns is down")
        with self.assertRaises(pc.PickerApiError) as ctx:
            self.list()
        self.assertEqual(ctx.exception.reason, "network")
        self.assertEqual(ctx.exception.status, 0)

    def test_a_non_json_body_is_not_pasted_into_the_error(self):
        self.http.request_queue.append(_FakeResponse(200, _NO_JSON,
                                                     content=b"<html>"))
        with self.assertRaises(pc.PickerApiError) as ctx:
            self.list()
        self.assertIn("withheld", str(ctx.exception))
        self.assertNotIn("<html>", str(ctx.exception))

    def test_an_empty_session_id_is_refused_before_reaching_google(self):
        with self.assertRaises(pc.PickerApiError) as ctx:
            pc.list_media_items(_FAKE_ACCESS, "   ")
        self.assertEqual(ctx.exception.reason, "invalid_request")
        self.assertEqual(self.http.calls, [])

    def test_no_error_message_carries_a_credential_or_a_base_url(self):
        for status in (400, 401, 403, 404, 429, 500, 503):
            self.http.request_queue.append(_FakeResponse(status, {
                "error": {"status": "S", "message": "m"}}))
            with self.assertRaises(pc.PickerApiError) as ctx:
                self.list()
            self.assertNotIn(_FAKE_ACCESS, str(ctx.exception))
            self.assertNotIn(_FAKE_BASE_URL, str(ctx.exception))
        self.assertNothingLeaked()


# ---------------------------------------------------------------- secrets


class TestNoLeak(_Base):

    def test_the_bearer_header_is_sent(self):
        self.http.request_queue.append(_FakeResponse(200, {"mediaItems": []}))
        self.list()
        headers = self.http.calls[0][2]
        self.assertEqual(headers["Authorization"], "Bearer %s" % _FAKE_ACCESS)

    def test_a_successful_listing_logs_counts_only(self):
        self.http.request_queue.append(_FakeResponse(200, {
            "mediaItems": [_item("m-1"), _item("m-1"), _item("m-2")]}))
        self.list()
        self.assertNothingLeaked()
        blob = "\n".join(self.logs.lines)
        self.assertIn("listed 2 picked media item(s)", blob)
        self.assertIn("1 duplicate media item id(s)", blob)
        self.assertNotIn("m-1", blob)

    def test_the_client_never_follows_a_base_url(self):
        """2A returns the download URL; 2B follows it. Every call this
        module makes goes to the Picker API host."""
        self.http.request_queue.append(_FakeResponse(200, {
            "mediaItems": [_item("m-1")]}))
        self.list()
        for _method, url, _headers in self.http.calls:
            self.assertTrue(url.startswith(pc.PICKER_BASE), url)

    def test_the_module_imports_no_database_or_storage_collaborator(self):
        """Asserted as an exact import set rather than a substring scan,
        so a prose mention of `import_repository` in a docstring does not
        read as a dependency -- and so a NEW collaborator fails this even
        if nobody thought to add it to a blocklist."""
        tree = ast.parse(_CLIENT_PATH.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add("." * node.level + (node.module or ""))
        self.assertEqual(
            imported,
            {"__future__", "logging", "typing", "urllib.parse", "requests"},
            "the listing client grew a collaborator; database, storage and "
            "photo_intake work belongs to Phase 2B")


if __name__ == "__main__":
    unittest.main()
