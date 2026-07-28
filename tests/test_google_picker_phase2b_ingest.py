"""WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01 Phase 2B -- the ingest route.

Phase 2A read back WHAT the operator picked. The acquisition module
fetched and identified bytes with no database handle at all. This is the
route that joins them: it lists the selection, downloads each original,
creates a candidate ONLY after the bytes and the metadata are in hand,
and stages the file under the id the repository actually returned.

Everything here runs against the real router, the real repository and a
real sqlite database. Only the two network edges are doubled -- Google's
Picker API inside `picker_client`, and the byte download inside
`acquire` -- so the parts that could be got wrong quietly (the ORDER of
create-then-stage, the hash comparison on re-ingest, the GPS asymmetry,
the failure vocabulary) are exercised for real.

What is locked here:

  1. THE ORDER OF SPEC 12.2, PROVED BY OUTCOME. No candidate id is ever
     preallocated. The bytes land under the id `candidate_create()`
     returned, which is asserted by reading the row and then finding the
     file at the path derived from that row's id -- not from anything
     the route chose.

  2. RE-INGEST IS IDEMPOTENT, AND REPAIR IS NOT OVERWRITE. Running the
     same ingest twice creates nothing the second time. A missing staged
     original is restored. A staged original whose bytes no longer hash
     to the row is ALSO restored, because the row and Google agree and
     the disk is the lone dissenter. But bytes that disagree with the
     ROW's hash are refused outright: nothing is written, nothing is
     replaced, and the refusal is a per-item failure rather than a
     candidate state -- because a state would be `candidate_decide()`,
     which is one-way (spec 12.3).

  3. ONE FAILED ITEM DOES NOT STOP LATER ITEMS. Asserted with a failure
     deliberately placed in the MIDDLE of a selection, so a loop that
     aborts is visible as two missing photographs rather than one.

  4. A RETRYABLE FAILURE LEAVES THE BATCH OPEN. Spec 12.4: only a
     picking session that no longer exists closes a batch `failed`. A
     rate limit, a network blip or an expired token must not, because a
     retryable failure with the batch closed behind it is not retryable.

  5. DATE FALLS BACK; LOCATION NEVER DOES. EXIF GPS reaches
     latitude/longitude with `location_source='exif_gps'`. Provider
     metadata reaching those columns is asserted impossible, in the
     schema's teeth -- `CANDIDATE_LOCATION_SOURCES` permits
     `provider_metadata`, so only this rule stops it.

  6. NOTHING LEAKS. The access token and `baseUrl` never appear in a
     response body or a log line, asserted against captured streams
     including the failure paths, where a real `requests` exception
     stringifies to the full bearer-scoped download URL.

  7. NO TEMPORARY FILE SURVIVES. The incoming directory is asserted
     empty after every run, including runs that failed part-way.

  8. INTAKE IS NOT APPROVAL AND NOT PROMOTION. Every candidate is born
     `pending`, no `photos` row is written, `google_photos_picker` stays
     out of `PROMOTABLE_SOURCES`, and the router calls neither
     `candidate_decide` nor `candidate_promote`.

  9. THE NEW CANDIDATES ARE IN THE EXISTING QUEUE. Not a second review
     surface -- the same `candidates_list` read the Evidence Review
     Queue already uses.

pytest is not installed in this repo; run with:

    .venv/bin/python -W error::ResourceWarning -u -m unittest \
        tests.test_google_picker_phase2b_ingest
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

# Import strategy: the picker router uses `from ...services.google_picker`,
# a three-dot relative import that only resolves under the production
# package layout. Mirror production and import through the SAME `code.`
# root for every collaborator, so the module objects the router holds are
# the ones this file patches. Copied from
# tests/test_google_picker_phase1.py, including its two defences against
# sibling suites that install fake fastapi/pydantic modules.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
for _p in (str(_SERVER_CODE), str(_REPO_ROOT / "server"), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

if "code" in sys.modules and not hasattr(sys.modules["code"], "__path__"):
    del sys.modules["code"]

for _stub_name in ("fastapi", "pydantic"):
    _stub = sys.modules.get(_stub_name)
    if _stub is not None and not hasattr(_stub, "__path__"):
        for _k in [k for k in list(sys.modules)
                   if k == _stub_name or k.startswith(_stub_name + ".")]:
            del sys.modules[_k]

_real_fa = sys.modules.get("fastapi")
if _real_fa is not None and hasattr(_real_fa, "__path__"):
    _api_router = getattr(_real_fa, "APIRouter", None)
    if not (isinstance(_api_router, type)
            and getattr(_api_router, "__module__", "").startswith("fastapi")):
        from fastapi.routing import APIRouter as _orig_api_router
        from fastapi.exceptions import HTTPException as _orig_http_exc
        from fastapi.param_functions import Depends as _orig_depends
        _real_fa.APIRouter = _orig_api_router
        _real_fa.HTTPException = _orig_http_exc
        _real_fa.Depends = _orig_depends
_real_pd = sys.modules.get("pydantic")
if _real_pd is not None and hasattr(_real_pd, "__path__"):
    _base_model = getattr(_real_pd, "BaseModel", None)
    if not (isinstance(_base_model, type)
            and getattr(_base_model, "__module__", "").startswith("pydantic")):
        from pydantic.main import BaseModel as _orig_base_model
        from pydantic.fields import Field as _orig_pd_field
        _real_pd.BaseModel = _orig_base_model
        _real_pd.Field = _orig_pd_field

from fastapi import FastAPI  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from code.api import db as _db  # noqa: E402
from code.api.routers import google_picker as gp  # noqa: E402
from code.api.services import import_repository as repo  # noqa: E402
from code.services.google_picker import acquire as acq  # noqa: E402
from code.services.google_picker import oauth, picker_client  # noqa: E402

_ROUTER_PATH = _SERVER_CODE / "api" / "routers" / "google_picker.py"

_PICKER_FLAG = "HORNELORE_GOOGLE_PICKER"
_PROV_FLAG = "HORNELORE_IMPORT_PROVENANCE"

# Shapes, not credentials. Their whole job is to be asserted absent.
_FAKE_CLIENT_ID = "111222333444-notarealclientid.apps.googleusercontent.com"
_FAKE_CLIENT_SECRET = "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hape"
_FAKE_REFRESH = "1//0eNotARealRefreshTokenJustTheShapeOfOne"
_FAKE_ACCESS = "ya29.A0ARrdaM_notARealAccessTokenJustTheShape"
_BASE_URL_ROOT = "https://lh3.googleusercontent.com/lr/NOT-A-REAL-BASE-URL"

_ALL_SECRETS = (_FAKE_CLIENT_SECRET, _FAKE_REFRESH, _FAKE_ACCESS,
                _BASE_URL_ROOT)

_SESSION_ID = "picker-session-abc123"


def _now() -> str:
    return "2026-07-28T00:00:00Z"


# ------------------------------------------------------------ byte fixtures

def _jpeg(marker: bytes) -> bytes:
    """A minimally valid JPEG whose body varies, so two fixtures are the
    same FORMAT and different BYTES -- which is what the hash comparisons
    are actually about."""
    return (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01"
            b"\x00\x00" + marker * 32 + b"\xff\xd9")


_PHOTO_A = _jpeg(b"\xa1\xa2\xa3\xa4")
_PHOTO_B = _jpeg(b"\xb1\xb2\xb3\xb4")
_PHOTO_C = _jpeg(b"\xc1\xc2\xc3\xc4")
_PHOTO_REEXPORTED = _jpeg(b"\xd1\xd2\xd3\xd4")
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x77" * 64
_NOT_AN_IMAGE = b"this is prose, not an image, and it never becomes one."


# ------------------------------------------------------------- the doubles

class _Boom(Exception):
    """Stands in for requests.RequestException.

    Carries the full URL in its message on purpose: that is what a real
    transport error does, and it is the thing the leak assertions check
    was not passed through.
    """


class _JsonResponse:
    """A Picker API response. `picker_client` calls requests.request()."""

    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.content = b"{}"

    def json(self):
        return self._payload


class _ByteResponse:
    """A download response. `acquire` calls requests.get(stream=True)."""

    def __init__(self, status_code=200, body=b"", headers=None,
                 raise_mid_stream=False):
        self.status_code = status_code
        self.headers = dict(headers or {})
        self._body = body
        self._raise = raise_mid_stream
        self.closed = False

    def iter_content(self, chunk_size=None):
        if self._raise:
            yield self._body[:4]
            raise _Boom("HTTPSConnectionPool: read failed for %s-1=d"
                        % _BASE_URL_ROOT)
        size = chunk_size or 65536
        for start in range(0, len(self._body), size):
            yield self._body[start:start + size]

    def close(self):
        self.closed = True


class _FakePickerHttp:
    """Google's Picker API, dispatched by URL.

    One double for session-create, session-poll and media listing,
    because all three go through `picker_client.requests.request` and a
    test that wants to fail exactly one of them should say which by
    setting a field rather than by re-wiring the transport.
    """

    RequestException = _Boom

    def __init__(self):
        self.calls = []
        self.items = []
        self.media_items_set = True
        self.fail_poll = None          # (status, payload) or an exception
        self.fail_list = None
        self.pages = None              # [[raw...], [raw...]] for paging

    def request(self, method, url, headers=None, json=None, timeout=None, **kw):
        self.calls.append((method, url))

        if method == "POST" and url.endswith("/sessions"):
            return _JsonResponse(200, {
                "id": _SESSION_ID,
                "pickerUri": "https://photos.google.com/picker/s/abc123",
                "mediaItemsSet": False,
                "pollingConfig": {"pollInterval": "5s", "timeoutIn": "1800s"},
                "expireTime": "2026-07-28T01:00:00Z",
            })

        if "/mediaItems" in url:
            if isinstance(self.fail_list, Exception):
                raise self.fail_list
            if self.fail_list is not None:
                return _JsonResponse(*self.fail_list)
            return _JsonResponse(200, {"mediaItems": list(self.items)})

        # GET /sessions/{id} -- the poll.
        if isinstance(self.fail_poll, Exception):
            raise self.fail_poll
        if self.fail_poll is not None:
            return _JsonResponse(*self.fail_poll)
        return _JsonResponse(200, {
            "id": _SESSION_ID,
            "pickerUri": "https://photos.google.com/picker/s/abc123",
            "mediaItemsSet": self.media_items_set,
            "pollingConfig": {"pollInterval": "5s", "timeoutIn": "1800s"},
            "expireTime": "2026-07-28T01:00:00Z",
        })


class _FakeOauthHttp:
    RequestException = _Boom

    def __init__(self):
        self.calls = 0

    def post(self, url, data=None, timeout=None, **kw):
        self.calls += 1
        return _JsonResponse(200, {"access_token": _FAKE_ACCESS,
                                   "expires_in": 3600})


class _FakeDownloadHttp:
    """The byte edge. Keyed by item id, which is embedded in each
    fixture's baseUrl, so a selection of five photographs can have one
    failing item in the middle without re-wiring anything."""

    RequestException = _Boom

    def __init__(self):
        self.calls = []
        self.bodies = {}               # item_id -> bytes
        self.statuses = {}             # item_id -> http status
        self.raises = {}               # item_id -> exception to raise
        self.mid_stream = set()        # item_ids that die mid-download

    def _item_of(self, url):
        # `acquire` appends "=d" to the baseUrl; the id is the tail.
        return url[len(_BASE_URL_ROOT) + 1:].rsplit("=d", 1)[0]

    def get(self, url, headers=None, stream=False, timeout=None):
        item_id = self._item_of(url)
        self.calls.append(item_id)
        if item_id in self.raises:
            raise self.raises[item_id]
        status = self.statuses.get(item_id, 200)
        body = self.bodies.get(item_id, _PHOTO_A)
        return _ByteResponse(status_code=status, body=body,
                             raise_mid_stream=item_id in self.mid_stream)


class _LogCatcher(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        try:
            self.lines.append(record.getMessage())
        except Exception:
            self.lines.append(str(record.msg))

    def blob(self):
        return "\n".join(self.lines)


def _raw_item(item_id, *, mime="image/jpeg", media_type="PHOTO",
              filename=None, create_time=None, width=4032, height=3024):
    """A PickedMediaItem in Google's own shape, so `_normalize_media_item`
    does the real normalisation rather than the test doing it."""
    return {
        "id": item_id,
        "type": media_type,
        "createTime": create_time,
        "mediaFile": {
            "baseUrl": "%s-%s" % (_BASE_URL_ROOT, item_id),
            "mimeType": mime,
            "filename": filename or ("%s.jpg" % item_id),
            "mediaFileMetadata": {"width": width, "height": height},
        },
    }


# ---------------------------------------------------------------- the base

class _Base(unittest.TestCase):
    picker_flag = "1"
    prov_flag = "1"

    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        tmp.close()
        self.db_path = Path(tmp.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()

        self.data_dir = tempfile.mkdtemp(prefix="picker-ingest-data-")

        self._orig_env = {}
        for key, val in ((_PICKER_FLAG, self.picker_flag),
                         (_PROV_FLAG, self.prov_flag),
                         (acq.DATA_DIR_ENV, self.data_dir),
                         (acq.MAX_BYTES_ENV, None),
                         (oauth.ENV_CLIENT_ID, _FAKE_CLIENT_ID),
                         (oauth.ENV_CLIENT_SECRET, _FAKE_CLIENT_SECRET),
                         (oauth.ENV_REFRESH_TOKEN, _FAKE_REFRESH)):
            self._orig_env[key] = os.environ.get(key)
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

        self.picker_http = _FakePickerHttp()
        self.auth_http = _FakeOauthHttp()
        self.dl_http = _FakeDownloadHttp()
        self._orig_picker_requests = picker_client.requests
        self._orig_oauth_requests = oauth.requests
        self._orig_acq_requests = acq.requests
        picker_client.requests = self.picker_http
        oauth.requests = self.auth_http
        acq.requests = self.dl_http
        oauth.reset_cache()

        # Captured once, here, and never re-captured inside a helper: a
        # helper that re-captures would save the DOUBLE as the original
        # the second time it ran and silently fake the rest of the file.
        self._real_exif = acq.extract_exif

        self.logs = _LogCatcher()
        self._loggers = []
        for name in ("code.api.routers.google_picker",
                     "code.services.google_picker.acquire",
                     "code.services.google_picker.picker_client"):
            lg = logging.getLogger(name)
            self._loggers.append((lg, lg.level))
            lg.addHandler(self.logs)
            lg.setLevel(logging.DEBUG)

        app = FastAPI()
        app.include_router(gp.router)
        self.client = TestClient(app, raise_server_exceptions=False)

        self.person_id = self._insert_person("Christopher Todd Horne")
        self.other_person_id = self._insert_person("Kent James Horne")
        self.trip_id = self._insert_trip(self.person_id, "Europe 2026")

    def tearDown(self):
        self.client.close()
        acq.extract_exif = self._real_exif
        picker_client.requests = self._orig_picker_requests
        oauth.requests = self._orig_oauth_requests
        acq.requests = self._orig_acq_requests
        oauth.reset_cache()
        for lg, level in self._loggers:
            lg.removeHandler(self.logs)
            lg.setLevel(level)
        _db.DB_PATH = self._orig_db
        for key, val in self._orig_env.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        shutil.rmtree(self.data_dir, ignore_errors=True)
        try:
            self.db_path.unlink()
        except OSError:
            pass

    # -- fixture helpers -------------------------------------------------

    def _con(self):
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON;")
        return con

    def _insert_person(self, name):
        pid = str(uuid.uuid4())
        con = self._con()
        try:
            con.execute(
                "INSERT INTO people (id, display_name, created_at, updated_at) "
                "VALUES (?, ?, ?, ?)", (pid, name, _now(), _now()))
            con.commit()
        finally:
            con.close()
        return pid

    def _insert_trip(self, person_id, title):
        tid = str(uuid.uuid4())
        con = self._con()
        try:
            con.execute(
                "INSERT INTO trips (id, person_id, title, created_at, "
                "updated_at) VALUES (?, ?, ?, ?, ?)",
                (tid, person_id, title, _now(), _now()))
            con.commit()
        finally:
            con.close()
        return tid

    def open_batch(self, **over):
        """A real picker batch, opened through the real route, so
        `external_ref` holds a real picking session id."""
        payload = {"person_id": self.person_id}
        payload.update(over)
        resp = self.client.post("/api/google-picker/sessions", json=payload)
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()["batch_id"]

    def pick(self, *items):
        self.picker_http.items = list(items)

    def ingest(self, batch_id, body=None):
        return self.client.post(
            "/api/google-picker/sessions/%s/ingest" % batch_id,
            json=body if body is not None else {})

    # -- assertions ------------------------------------------------------

    def candidates(self, batch_id=None):
        con = self._con()
        try:
            if batch_id:
                rows = con.execute(
                    "SELECT * FROM import_candidate WHERE batch_id = ? "
                    "ORDER BY created_at, rowid", (batch_id,)).fetchall()
            else:
                rows = con.execute(
                    "SELECT * FROM import_candidate ORDER BY created_at, "
                    "rowid").fetchall()
            return [dict(r) for r in rows]
        finally:
            con.close()

    def photo_count(self):
        con = self._con()
        try:
            return con.execute(
                "SELECT COUNT(*) AS n FROM photos").fetchone()["n"]
        finally:
            con.close()

    def staged_path(self, batch_id, candidate_id):
        """Derived from the ROW's id, never from anything the route
        chose. This is what makes 'the bytes went under the id the
        repository returned' an assertion rather than a hope."""
        found = sorted(acq.staging_dir_for(batch_id, candidate_id)
                       .glob("original.*"))
        self.assertEqual(len(found), 1,
                         "expected exactly one staged original, found %r"
                         % [p.name for p in found])
        return found[0]

    def assertIncomingEmpty(self, batch_id):
        incoming = acq.incoming_dir_for(batch_id)
        left = sorted(p.name for p in incoming.glob("*")) \
            if incoming.exists() else []
        self.assertEqual(left, [],
                         "a temporary download survived the run: %r" % left)

    def assertNothingLeaked(self, *texts):
        blob = self.logs.blob() + "\n" + "\n".join(str(t) for t in texts)
        for secret in _ALL_SECRETS:
            self.assertNotIn(secret, blob,
                             "a credential or a download URL reached a "
                             "response body or a log line")
        self.assertNotIn("Bearer", blob)


# ------------------------------------------------------------------ 1. gate

class TestGate(_Base):
    picker_flag = "0"

    def test_ingest_is_not_found_when_the_picker_flag_is_off(self):
        """404, not 403 and not 405. A surface that is off does not
        announce that it exists."""
        resp = self.client.post(
            "/api/google-picker/sessions/anything/ingest", json={})
        self.assertEqual(resp.status_code, 404)


class TestGateProvenanceOff(_Base):
    prov_flag = "0"

    def test_ingest_is_not_found_when_the_provenance_lane_is_off(self):
        """Ingest writes into the provenance lane. If that lane is off,
        this route has nowhere to put a candidate and must not exist."""
        resp = self.client.post(
            "/api/google-picker/sessions/anything/ingest", json={})
        self.assertEqual(resp.status_code, 404)


# -------------------------------------------------------------- 2. the order

class TestHappyPath(_Base):
    def test_two_picked_photographs_become_two_pending_candidates(self):
        batch_id = self.open_batch(trip_id=self.trip_id)
        self.pick(_raw_item("m-1"), _raw_item("m-2"))
        self.dl_http.bodies = {"m-1": _PHOTO_A, "m-2": _PHOTO_B}

        resp = self.ingest(batch_id)
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()

        self.assertEqual(body["created"], 2)
        self.assertEqual(body["failed"], 0)
        self.assertEqual(body["picked"], 2)
        self.assertEqual(body["attempted"], 2)
        self.assertFalse(body["truncated"])
        self.assertEqual(body["remaining"], 0)
        self.assertEqual([r["outcome"] for r in body["results"]],
                         ["created", "created"])

        rows = self.candidates(batch_id)
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["state"], "pending")
            self.assertEqual(row["person_id"], self.person_id)
            self.assertEqual(row["trip_id"], self.trip_id)
            self.assertEqual(row["mime_type"], "image/jpeg")

    def test_the_bytes_land_under_the_id_the_repository_returned(self):
        """Spec 12.2. The path is derived from the ROW, so a route that
        preallocated an id and staged under it would fail here even if
        its own response looked right."""
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1"))
        self.dl_http.bodies = {"m-1": _PHOTO_A}
        self.ingest(batch_id)

        row = self.candidates(batch_id)[0]
        staged = self.staged_path(batch_id, row["id"])
        self.assertEqual(staged.name, "original.jpg")
        self.assertEqual(staged.read_bytes(), _PHOTO_A)
        self.assertEqual(acq.hash_file(staged), row["file_hash"])
        self.assertEqual(row["byte_size"], len(_PHOTO_A))

    def test_the_response_reports_the_candidate_id_it_actually_created(self):
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1"))
        body = self.ingest(batch_id).json()
        self.assertEqual(body["results"][0]["candidate_id"],
                         self.candidates(batch_id)[0]["id"])

    def test_the_verified_extension_wins_over_the_declared_mime_type(self):
        """Google says jpeg; the bytes are a PNG. The bytes win, and the
        disagreement is recorded rather than silently resolved."""
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1", mime="image/jpeg"))
        self.dl_http.bodies = {"m-1": _PNG}
        self.ingest(batch_id)

        row = self.candidates(batch_id)[0]
        self.assertEqual(row["mime_type"], "image/png")
        self.assertEqual(self.staged_path(batch_id, row["id"]).name,
                         "original.png")
        reason = json.loads(row["match_reason_json"])
        self.assertTrue(reason["provider_mime_disagreed"])
        self.assertEqual(reason["provider_mime_type"], "image/jpeg")
        self.assertEqual(reason["verified_mime"], "image/png")

    def test_no_temporary_file_survives_a_clean_run(self):
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1"), _raw_item("m-2"))
        self.ingest(batch_id)
        self.assertIncomingEmpty(batch_id)


# ------------------------------------------------------------ 3. idempotence

class TestReIngest(_Base):
    def _one_landed(self):
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1"))
        self.dl_http.bodies = {"m-1": _PHOTO_A}
        self.ingest(batch_id)
        row = self.candidates(batch_id)[0]
        return batch_id, row

    def test_running_the_same_ingest_twice_creates_no_duplicate(self):
        batch_id, first = self._one_landed()
        body = self.ingest(batch_id).json()

        self.assertEqual(body["created"], 0)
        self.assertEqual(body["unchanged"], 1)
        self.assertEqual(body["failed"], 0)
        rows = self.candidates(batch_id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], first["id"])
        self.assertEqual(rows[0]["file_hash"], first["file_hash"])

    def test_unchanged_means_the_staged_bytes_were_hashed_not_counted(self):
        """`unchanged` is a claim about bytes, not about a filename
        existing. The response says so explicitly."""
        batch_id, _ = self._one_landed()
        result = self.ingest(batch_id).json()["results"][0]
        self.assertEqual(result["outcome"], "unchanged")
        self.assertTrue(result["staged_verified"])

    def test_a_missing_staged_original_is_repaired(self):
        batch_id, row = self._one_landed()
        staged = self.staged_path(batch_id, row["id"])
        staged.unlink()

        body = self.ingest(batch_id).json()
        self.assertEqual(body["repaired"], 1)
        self.assertEqual(body["created"], 0)
        self.assertEqual(body["results"][0]["repaired_from"], "missing")

        restored = self.staged_path(batch_id, row["id"])
        self.assertEqual(restored.read_bytes(), _PHOTO_A)
        self.assertEqual(self.candidates(batch_id)[0]["file_hash"],
                         row["file_hash"])

    def test_a_staged_original_that_no_longer_matches_is_repaired(self):
        """The row and Google agree with each other and the disk is the
        lone dissenter, so the disk is the thing that gets corrected.
        Contrast the next test, where there is no such majority."""
        batch_id, row = self._one_landed()
        self.staged_path(batch_id, row["id"]).write_bytes(_PHOTO_B)

        body = self.ingest(batch_id).json()
        self.assertEqual(body["repaired"], 1)
        self.assertEqual(body["results"][0]["repaired_from"],
                         "hash_disagreement")
        self.assertEqual(self.staged_path(batch_id, row["id"]).read_bytes(),
                         _PHOTO_A)
        self.assertEqual(self.candidates(batch_id)[0]["file_hash"],
                         row["file_hash"])

    def test_different_bytes_under_the_same_item_id_are_refused(self):
        """The row keeps its hash, the staged file keeps its bytes, and
        the operator is told. Writing the new bytes under the old row
        would make the row lie; changing the row is not this lane's call
        to make automatically."""
        batch_id, row = self._one_landed()
        self.dl_http.bodies = {"m-1": _PHOTO_REEXPORTED}

        body = self.ingest(batch_id).json()
        self.assertEqual(body["failed"], 1)
        self.assertEqual(body["permanent_failures"], 1)
        self.assertEqual(body["created"], 0)
        self.assertEqual(body["repaired"], 0)

        result = body["results"][0]
        self.assertEqual(result["reason"], "hash_mismatch")
        self.assertFalse(result["retryable"])

        rows = self.candidates(batch_id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["file_hash"], row["file_hash"])
        self.assertEqual(self.staged_path(batch_id, row["id"]).read_bytes(),
                         _PHOTO_A)

    def test_a_refused_re_ingest_leaves_no_temporary_file(self):
        batch_id, _ = self._one_landed()
        self.dl_http.bodies = {"m-1": _PHOTO_REEXPORTED}
        self.ingest(batch_id)
        self.assertIncomingEmpty(batch_id)

    def test_a_hash_refusal_is_not_a_candidate_decision(self):
        """Spec 12.3. A refusal that wrote `state='error'` would be
        `candidate_decide()` -- one-way, with no undecide and no DELETE
        on this lane -- and would park an operator verdict no operator
        made."""
        batch_id, _ = self._one_landed()
        self.dl_http.bodies = {"m-1": _PHOTO_REEXPORTED}
        self.ingest(batch_id)
        self.assertEqual(self.candidates(batch_id)[0]["state"], "pending")

    def test_a_hidden_candidate_is_still_found_rather_than_duplicated(self):
        """A hidden row still owns (batch_id, external_id). Ingest must
        take the re-ingest branch, not try to create a second row behind
        the unique index."""
        batch_id, row = self._one_landed()
        repo.candidate_hide(row["id"], hidden=True)

        body = self.ingest(batch_id).json()
        self.assertEqual(body["created"], 0)
        self.assertEqual(len(self.candidates(batch_id)), 1)


# ------------------------------------------------------- 4. partial failure

class TestPartialFailure(_Base):
    def test_one_bad_item_in_the_middle_does_not_stop_the_rest(self):
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1"), _raw_item("m-2"), _raw_item("m-3"))
        self.dl_http.bodies = {"m-1": _PHOTO_A, "m-2": _NOT_AN_IMAGE,
                               "m-3": _PHOTO_C}

        body = self.ingest(batch_id).json()
        self.assertEqual(body["created"], 2)
        self.assertEqual(body["failed"], 1)
        self.assertEqual([r["outcome"] for r in body["results"]],
                         ["created", "failed", "created"])
        self.assertEqual(
            sorted(r["external_id"] for r in self.candidates(batch_id)),
            ["m-1", "m-3"])

    def test_an_unacquirable_item_produces_no_candidate_row_at_all(self):
        """Spec 12.3 again, from the other side: there is no such thing
        as an `error` candidate created by ingest."""
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1"))
        self.dl_http.bodies = {"m-1": _NOT_AN_IMAGE}
        self.ingest(batch_id)
        self.assertEqual(self.candidates(batch_id), [])

    def test_a_declared_video_is_refused_before_a_byte_is_fetched(self):
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1", media_type="VIDEO", mime="video/mp4"))
        body = self.ingest(batch_id).json()

        self.assertEqual(body["failed"], 1)
        result = body["results"][0]
        self.assertEqual(result["reason"], "unsupported_content")
        self.assertFalse(result["retryable"])
        self.assertEqual(self.candidates(batch_id), [])
        self.assertEqual(self.dl_http.calls, [],
                         "a video was downloaded before being refused")

    def test_a_retryable_and_a_permanent_failure_are_counted_apart(self):
        """The split is the whole basis on which a re-run decides what to
        attempt again, since ingest never records a decision."""
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1"), _raw_item("m-2"))
        self.dl_http.bodies = {"m-1": _NOT_AN_IMAGE}     # permanent
        self.dl_http.statuses = {"m-2": 401}             # base_url_expired
        body = self.ingest(batch_id).json()

        self.assertEqual(body["failed"], 2)
        self.assertEqual(body["permanent_failures"], 1)
        self.assertEqual(body["retryable_failures"], 1)
        by_id = {r["media_item_id"]: r for r in body["results"]}
        self.assertFalse(by_id["m-1"]["retryable"])
        self.assertTrue(by_id["m-2"]["retryable"])
        self.assertEqual(by_id["m-2"]["reason"], "base_url_expired")

    def test_a_partial_run_leaves_no_temporary_files(self):
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1"), _raw_item("m-2"), _raw_item("m-3"))
        self.dl_http.bodies = {"m-2": _NOT_AN_IMAGE}
        self.dl_http.mid_stream = {"m-3"}
        self.ingest(batch_id)
        self.assertIncomingEmpty(batch_id)

    def test_a_retryable_failure_leaves_the_batch_open(self):
        """Spec 12.4. A retryable failure with the batch closed behind it
        is not retryable: somebody would have to reopen the batch by hand
        before the retry the response invited could work."""
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1"))
        self.dl_http.statuses = {"m-1": 401}
        body = self.ingest(batch_id).json()

        self.assertEqual(body["batch_status"], "open")
        self.assertEqual(repo.batch_get(batch_id)["status"], "open")
        self.assertIsNone(repo.batch_get(batch_id)["failure_reason"])

    def test_the_retry_lands_the_item_that_failed_retryably(self):
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1"), _raw_item("m-2"))
        self.dl_http.statuses = {"m-2": 429}
        first = self.ingest(batch_id).json()
        self.assertEqual(first["created"], 1)

        self.dl_http.statuses = {}
        second = self.ingest(batch_id).json()
        self.assertEqual(second["created"], 1)
        self.assertEqual(second["unchanged"], 1,
                         "the item that already landed was re-downloaded and "
                         "re-created rather than recognised")
        self.assertEqual(len(self.candidates(batch_id)), 2)


# ------------------------------------------------------- 5. batch-level fail

class TestSessionUnusable(_Base):
    def test_a_vanished_picking_session_closes_the_batch_failed(self):
        batch_id = self.open_batch()
        self.picker_http.fail_poll = (404, {"error": {"message": "gone"}})
        resp = self.ingest(batch_id)

        self.assertEqual(resp.status_code, 404)
        batch = repo.batch_get(batch_id)
        self.assertEqual(batch["status"], "failed")
        self.assertIn("no longer available", batch["failure_reason"])

    def test_a_rate_limit_does_not_close_the_batch(self):
        batch_id = self.open_batch()
        self.picker_http.fail_list = (429, {"error": {"message": "slow down"}})
        resp = self.ingest(batch_id)

        self.assertEqual(resp.status_code, 503)
        self.assertEqual(repo.batch_get(batch_id)["status"], "open")

    def test_a_transport_failure_does_not_close_the_batch(self):
        """The listing call is to `photospicker.googleapis.com`, so the
        URL a real transport error stringifies is the API endpoint, not a
        `baseUrl`. That distinction is the whole point of the assertion
        below, so the fixture raises the URL that could actually appear
        rather than one that could not: a Picker API URL names a session
        the poll route already returns, while a `baseUrl` is
        bearer-scoped and is possession of the photograph. `picker_client`
        interpolates the transport exception into its detail, which is
        Phase 1 behaviour; what must stay true is that the token and the
        download URL are still not in it."""
        batch_id = self.open_batch()
        self.picker_http.fail_list = _Boom(
            "HTTPSConnectionPool(host='photospicker.googleapis.com', "
            "port=443): Max retries exceeded")
        resp = self.ingest(batch_id)

        self.assertEqual(resp.status_code, 502)
        self.assertEqual(repo.batch_get(batch_id)["status"], "open")
        self.assertNothingLeaked(resp.text)
        self.assertEqual(self.dl_http.calls, [],
                         "a listing that never returned must not have "
                         "produced a download")

    def test_candidates_that_already_landed_survive_the_batch_closing(self):
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1"))
        self.ingest(batch_id)
        self.assertEqual(len(self.candidates(batch_id)), 1)

        self.picker_http.fail_poll = (404, {"error": {"message": "gone"}})
        self.ingest(batch_id)
        self.assertEqual(len(self.candidates(batch_id)), 1)
        self.assertEqual(self.candidates(batch_id)[0]["state"], "pending")

    def test_a_closed_batch_is_refused_with_the_way_to_reopen_it(self):
        batch_id = self.open_batch()
        repo.batch_close(batch_id)
        resp = self.ingest(batch_id)

        self.assertEqual(resp.status_code, 409)
        self.assertIn("reopen", resp.text)
        self.assertEqual(self.dl_http.calls, [])

    def test_an_unfinished_selection_is_refused_before_any_download(self):
        """Ingesting a half-made selection would record it as the import,
        and the second run would then see every later photograph as new
        while the first batch already claimed to be complete."""
        batch_id = self.open_batch()
        self.picker_http.media_items_set = False
        resp = self.ingest(batch_id)

        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["detail"]["reason"],
                         "selection_incomplete")
        self.assertEqual(self.dl_http.calls, [])
        self.assertEqual(repo.batch_get(batch_id)["status"], "open")


# ----------------------------------------------------------- 6. the metadata

class TestEvidenceMetadata(_Base):
    def _with_exif(self, payload):
        acq.extract_exif = lambda path: dict(payload)

    def test_exif_gps_reaches_the_candidate(self):
        self._with_exif({"captured_at": "2026-06-01 10:00:00",
                         "gps": {"latitude": 41.9028, "longitude": 12.4964}})
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1"))
        self.ingest(batch_id)

        row = self.candidates(batch_id)[0]
        self.assertAlmostEqual(row["latitude"], 41.9028, places=4)
        self.assertAlmostEqual(row["longitude"], 12.4964, places=4)
        self.assertEqual(row["location_source"], "exif_gps")
        self.assertEqual(row["taken_at_source"], "exif")

    def test_provider_metadata_never_becomes_a_location_source(self):
        """`CANDIDATE_LOCATION_SOURCES` permits `provider_metadata`, so
        the schema does not stop this. This rule does."""
        self._with_exif({})
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1", create_time="2026-06-01T08:00:00Z"))
        self.ingest(batch_id)

        row = self.candidates(batch_id)[0]
        self.assertIsNone(row["latitude"])
        self.assertIsNone(row["longitude"])
        self.assertEqual(row["location_source"], "unknown")
        self.assertNotEqual(row["location_source"], "provider_metadata")

    def test_the_date_does_fall_back_to_the_provider(self):
        self._with_exif({})
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1", create_time="2026-06-01T08:00:00Z"))
        self.ingest(batch_id)

        row = self.candidates(batch_id)[0]
        self.assertEqual(row["taken_at_source"], "provider_metadata")
        self.assertTrue(row["taken_at"])

    def test_no_exif_and_no_provider_time_is_unknown_rather_than_now(self):
        self._with_exif({})
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1", create_time=None))
        self.ingest(batch_id)

        row = self.candidates(batch_id)[0]
        self.assertIsNone(row["taken_at"])
        self.assertEqual(row["taken_at_source"], "unknown")

    def test_an_unparseable_gps_tag_is_recorded_without_becoming_a_location(self):
        """Three states, two columns. The third has no home but
        `match_reason`, and dropping it would tell a reviewer 'no
        location' about a photograph that plainly has one."""
        self._with_exif({"gps": {"present_unparseable": True}})
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1"))
        self.ingest(batch_id)

        row = self.candidates(batch_id)[0]
        self.assertIsNone(row["latitude"])
        self.assertEqual(row["location_source"], "unknown")
        self.assertTrue(json.loads(row["match_reason_json"])
                        ["gps_present_unparseable"])

    def test_an_ordinary_photograph_does_not_carry_a_cleared_gps_claim(self):
        """Absence is the ordinary case. A `false` on every photograph
        would read as checked-and-cleared and bury the ones that mean
        something."""
        self._with_exif({})
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1"))
        self.ingest(batch_id)
        self.assertNotIn("gps_present_unparseable",
                         json.loads(self.candidates(batch_id)[0]
                                    ["match_reason_json"]))

    def test_an_exif_read_that_explodes_does_not_lose_the_photograph(self):
        def boom(path):
            raise ValueError("corrupt exif")
        acq.extract_exif = boom

        batch_id = self.open_batch()
        self.pick(_raw_item("m-1"))
        body = self.ingest(batch_id).json()
        self.assertEqual(body["created"], 1)
        self.assertEqual(self.candidates(batch_id)[0]["taken_at_source"],
                         "unknown")


# --------------------------------------------------------- 7. match_reason

class TestMatchReason(_Base):
    def test_it_carries_no_staging_path(self):
        """Spec 12.5. `match_reason` is effectively write-once -- the
        repository has no function that updates candidate metadata -- so
        a path recorded here could never be corrected after the file was
        repaired or moved."""
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1"))
        self.ingest(batch_id)

        row = self.candidates(batch_id)[0]
        blob = row["match_reason_json"]
        self.assertNotIn("import_staging", blob)
        self.assertNotIn("original.", blob)
        self.assertNotIn(str(self.data_dir), blob)
        self.assertNotIn(row["id"], blob)

    def test_it_carries_no_credential_and_no_download_url(self):
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1"))
        self.ingest(batch_id)
        blob = self.candidates(batch_id)[0]["match_reason_json"]
        for secret in _ALL_SECRETS:
            self.assertNotIn(secret, blob)

    def test_no_key_reads_as_a_credential_to_the_repository_scanner(self):
        """The repository would refuse these outright; the point of
        asserting it here is that the refusal would arrive as a failed
        item at run time, and this is cheaper to find."""
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1"))
        self.ingest(batch_id)
        reason = json.loads(self.candidates(batch_id)[0]["match_reason_json"])

        def walk(obj):
            if isinstance(obj, dict):
                for key, val in obj.items():
                    low = key.lower()
                    for hint in repo._SECRET_KEY_HINTS:
                        self.assertNotIn(hint, low)
                    walk(val)
            elif isinstance(obj, list):
                for val in obj:
                    walk(val)

        walk(reason)

    def test_it_names_the_lane_and_what_the_provider_claimed(self):
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1", width=4032, height=3024))
        self.ingest(batch_id)
        reason = json.loads(self.candidates(batch_id)[0]["match_reason_json"])

        self.assertEqual(reason["source"], "google_photos_picker")
        self.assertEqual(reason["provider_media_type"], "PHOTO")
        self.assertEqual(reason["provider_dimensions"],
                         {"width": 4032, "height": 3024})


# ------------------------------------------------------------- 8. no leaks

class TestNoLeak(_Base):
    def test_a_clean_run_leaks_nothing(self):
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1"), _raw_item("m-2"))
        resp = self.ingest(batch_id)
        self.assertNothingLeaked(resp.text)

    def test_a_transport_failure_mid_download_leaks_nothing(self):
        """A real `requests` exception stringifies to the full
        bearer-scoped download URL. The double does the same on purpose,
        so passing `str(exc)` through would be caught here."""
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1"))
        self.dl_http.raises = {"m-1": _Boom(
            "HTTPSConnectionPool: failed for %s-m-1=d" % _BASE_URL_ROOT)}
        resp = self.ingest(batch_id)

        self.assertEqual(resp.json()["failed"], 1)
        self.assertNothingLeaked(resp.text)

    def test_an_unexpected_error_is_reported_by_class_name_only(self):
        """No traceback and no message. A traceback logged on this path
        could carry the download URL, which is the one value in this lane
        that must never reach a log file."""
        def explode(path, **kw):
            raise RuntimeError("boom, and here is the url: %s" % _BASE_URL_ROOT)

        batch_id = self.open_batch()
        self.pick(_raw_item("m-1"))
        real = gp.acquire.read_evidence_metadata
        gp.acquire.read_evidence_metadata = explode
        try:
            resp = self.ingest(batch_id)
        finally:
            gp.acquire.read_evidence_metadata = real

        result = resp.json()["results"][0]
        self.assertEqual(result["reason"], "unexpected_error")
        self.assertTrue(result["retryable"])
        self.assertIn("RuntimeError", result["detail"])
        self.assertNothingLeaked(resp.text)
        self.assertIncomingEmpty(batch_id)


# -------------------------------------------------------------- 9. the cap

class TestMaxItems(_Base):
    def test_truncation_is_reported_in_three_fields_rather_than_hidden(self):
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1"), _raw_item("m-2"), _raw_item("m-3"))
        body = self.ingest(batch_id, {"max_items": 2}).json()

        self.assertEqual(body["picked"], 3)
        self.assertEqual(body["attempted"], 2)
        self.assertTrue(body["truncated"])
        self.assertEqual(body["remaining"], 1)
        self.assertEqual(body["created"], 2)
        self.assertEqual(len(self.candidates(batch_id)), 2)

    def test_no_body_at_all_ingests_the_whole_selection(self):
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1"), _raw_item("m-2"))
        resp = self.client.post(
            "/api/google-picker/sessions/%s/ingest" % batch_id)
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["created"], 2)

    def test_a_cap_of_zero_is_refused_rather_than_read_as_no_cap(self):
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1"))
        self.assertEqual(self.ingest(batch_id, {"max_items": 0}).status_code,
                         422)


# --------------------------------------------------------- 10. queue visible

class TestQueueVisibility(_Base):
    def test_new_candidates_are_in_the_existing_queue_read(self):
        """Not a second review surface. This is the same
        `candidates_list` the Evidence Review Queue already calls."""
        batch_id = self.open_batch(trip_id=self.trip_id)
        self.pick(_raw_item("m-1"), _raw_item("m-2"))
        body = self.ingest(batch_id).json()

        queued = repo.candidates_list(person_id=self.person_id)
        self.assertEqual(len(queued), 2)
        self.assertTrue(all(c["state"] == "pending" for c in queued))
        self.assertEqual(body["queue"]["candidates_in_batch"], 2)
        self.assertEqual(body["queue"]["pending_in_batch"], 2)
        self.assertIn("/api/import-provenance/queue", body["queue"]["path"])

    def test_the_queue_count_excludes_hidden_rows_like_the_queue_does(self):
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1"), _raw_item("m-2"))
        self.ingest(batch_id)
        repo.candidate_hide(self.candidates(batch_id)[0]["id"], hidden=True)

        body = self.ingest(batch_id).json()
        self.assertEqual(body["queue"]["candidates_in_batch"], 1)


# ------------------------------------------------------------- 11. the walls

class TestPhaseWalls(_Base):
    """Phase 2B ends here. These are the assertions that fail loudly if a
    later session reaches past the wall without doing the work the wall
    exists to force."""

    def test_ingest_creates_no_photos_row(self):
        batch_id = self.open_batch(trip_id=self.trip_id)
        self.pick(_raw_item("m-1"), _raw_item("m-2"))
        self.ingest(batch_id)
        self.assertEqual(self.photo_count(), 0,
                         "promotion is Phase 3; ingest mints no photos")

    def test_the_picker_source_is_still_not_promotable(self):
        self.assertNotIn("google_photos_picker", repo.PROMOTABLE_SOURCES)
        self.assertIn("google_photos_picker", repo.IMPORT_SOURCES)

    def test_the_router_records_no_operator_decision(self):
        src = _ROUTER_PATH.read_text(encoding="utf-8")
        for forbidden in ("repo.candidate_decide", "repo.candidate_promote",
                          "repo.candidate_accept"):
            self.assertNotIn(forbidden, src,
                             "an automated failure must never become a "
                             "terminal candidate decision")

    def test_the_router_deletes_nothing_and_alters_no_schema(self):
        src = _ROUTER_PATH.read_text(encoding="utf-8").upper()
        for forbidden in ("DELETE FROM", "CREATE TABLE", "ALTER TABLE",
                          "DROP TABLE"):
            self.assertNotIn(forbidden, src)

    def test_the_router_builds_no_user_interface(self):
        """2D is the operator UI, and it is a separate session. A route
        that started returning HTML would be that session happening by
        accident."""
        src = _ROUTER_PATH.read_text(encoding="utf-8")
        for forbidden in ("HTMLResponse", "TemplateResponse", "StaticFiles",
                          "<html", "<div"):
            self.assertNotIn(forbidden, src)

    def test_the_route_and_the_module_do_not_both_classify_a_reason(self):
        """One vocabulary behind the `reason` field. A reason classified
        in two places would resolve to whichever one the reader consulted
        and the two could disagree about whether to retry."""
        overlap = (set(gp._ROUTE_REASONS)
                   & (set(acq.RETRYABLE_REASONS) | set(acq.PERMANENT_REASONS)))
        self.assertEqual(overlap, set())

    def test_every_outcome_the_route_reports_is_declared(self):
        batch_id = self.open_batch()
        self.pick(_raw_item("m-1"), _raw_item("m-2"))
        self.dl_http.bodies = {"m-2": _NOT_AN_IMAGE}
        body = self.ingest(batch_id).json()
        for entry in body["results"]:
            self.assertIn(entry["outcome"], gp.INGEST_OUTCOMES)

    def test_only_a_vanished_session_is_treated_as_batch_fatal(self):
        """Held as data, and asserted small. Every reason added to this
        tuple closes batches, so it should be hard to grow by accident."""
        self.assertEqual(gp._SESSION_UNUSABLE, ("session_not_found",))


if __name__ == "__main__":
    unittest.main(verbosity=2)
