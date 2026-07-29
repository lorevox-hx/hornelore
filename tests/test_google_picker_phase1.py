"""WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01 Phase 1 -- lane lock.

Phase 1 is credentials, health and Picker session lifecycle. It creates
no candidates and downloads no bytes, and a large part of what this file
locks is that it STAYS that way.

What is locked here:

  1. THE DOUBLE GATE. Every route 404s unless BOTH HORNELORE_GOOGLE_PICKER
     and HORNELORE_IMPORT_PROVENANCE are on. Not 403, not 405 -- 404, so
     the surface does not announce itself. And the gate beats FastAPI's
     body validation: POST /sessions {} with the flag off is 404, not a
     422 that would name the required fields.

  2. CREDENTIALS NEVER COME BACK OUT. /health reports presence as
     booleans. The fake client secret and refresh token planted in the
     environment are asserted absent from every response body this suite
     produces, including error bodies. Import rule 3 says credentials
     live in the process environment; this is that rule, tested.

  3. A DEAD REFRESH TOKEN IS NAMED, NOT GUESSED AT. Google's
     `invalid_grant` maps to 503 with reason "refresh_token_expired",
     because in a Testing-status project that failure arrives every
     seven days and an operator should not have to diagnose it.

  4. UPSTREAM FAILURE LEAVES NO DEBRIS. Google is called before the
     batch is opened, so a failed session creates no batch. And when the
     batch open fails after Google succeeded, the picker session is
     released rather than orphaned.

  5. NO DELETE ON THE EVIDENCE LANE. DELETE /sessions/{batch_id} ends the
     session AT GOOGLE. The import_batch row survives it, and the router
     source contains no DELETE FROM.

  6. THE PHASE WALL HOLDS, WHEREVER IT CURRENTLY STANDS.
     2026-07-29: this bullet used to read "`google_photos_picker` is NOT
     in PROMOTABLE_SOURCES and no route in this lane creates a
     candidate." Both halves have been overtaken. Phase 2B wires this
     lane to candidate creation, and PROMOTABLE_SOURCES no longer
     exists: it was renamed UPLOAD_SOURCES, because the list never meant
     "may be promoted" -- it meant "may be promoted from a file the
     operator supplied". The picker is still off that list, and must
     stay off it. The wall now stands at: no byte download in the
     listing client, no route following `baseUrl`, and promotion gated
     on a verified staged copy rather than on a source name.

Nothing here touches the network: `requests` is replaced inside the two
service modules by a recording double.

pytest is not installed in this repo; run with:

    .venv/bin/python -u -m unittest tests.test_google_picker_phase1
"""
from __future__ import annotations

import ast
import json
import os
import sqlite3
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

# Import strategy: the picker router uses `from ...services.google_picker`,
# a three-dot relative import that only resolves under the production
# package layout (`python -m uvicorn code.api.main:app` with cwd=server).
# A naive `api.routers.google_picker` import makes `api` top-level and
# dies with "attempted relative import beyond top-level package", so we
# mirror production and import `code.api.routers.google_picker`. Every
# collaborator below is imported through the SAME `code.` root so the
# repo/db module objects are identical to the ones the router holds --
# importing `api.services.import_repository` here would mint a second,
# separate module and the DB_PATH rebind would not reach the router.
# Pattern copied from tests/test_photo_show_next_scope_failure.py.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
for _p in (str(_SERVER_CODE), str(_REPO_ROOT / "server"), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# The stdlib `code` module (InteractiveInterpreter) shadows the
# production `server/code` package if something imported it first (pdb
# does). Drop the module-shaped entry so the package wins.
if "code" in sys.modules and not hasattr(sys.modules["code"], "__path__"):
    del sys.modules["code"]

# Shared-process defense: sibling test modules install FAKE
# fastapi/pydantic stubs into sys.modules at import time and never
# remove them. The real packages ARE installed here and this lane needs
# them, so purge any stub (a bare ModuleType has no __path__) first.
for _stub_name in ("fastapi", "pydantic"):
    _stub = sys.modules.get(_stub_name)
    if _stub is not None and not hasattr(_stub, "__path__"):
        for _k in [k for k in list(sys.modules)
                   if k == _stub_name or k.startswith(_stub_name + ".")]:
            del sys.modules[_k]

# Second pollution shape: another test MUTATES the real fastapi/pydantic
# top-level attributes. Repair from the untouched submodules rather than
# reloading, which would mint new class objects.
_real_fa = sys.modules.get("fastapi")
if _real_fa is not None and hasattr(_real_fa, "__path__"):
    _api_router = getattr(_real_fa, "APIRouter", None)
    if not (isinstance(_api_router, type)
            and getattr(_api_router, "__module__", "").startswith("fastapi")):
        from fastapi.routing import APIRouter as _orig_api_router
        from fastapi.exceptions import HTTPException as _orig_http_exc
        from fastapi.params import Depends as _orig_depends_cls  # noqa: F401
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
from code.services.google_picker import oauth, picker_client  # noqa: E402

_ROUTER_PATH = _SERVER_CODE / "api" / "routers" / "google_picker.py"
_CLIENT_PATH = _SERVER_CODE / "services" / "google_picker" / "picker_client.py"

_PICKER_FLAG = "HORNELORE_GOOGLE_PICKER"
_PROV_FLAG = "HORNELORE_IMPORT_PROVENANCE"

# Not real credentials -- shapes. The point is that these strings are
# asserted never to appear in a response body.
_FAKE_CLIENT_ID = "111222333444-notarealclientid.apps.googleusercontent.com"
_FAKE_CLIENT_SECRET = "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hape"
_FAKE_REFRESH = "1//0eNotARealRefreshTokenJustTheShapeOfOne"
_FAKE_ACCESS = "ya29.A0ARrdaM_notARealAccessTokenJustTheShape"

_ALL_SECRETS = (_FAKE_CLIENT_SECRET, _FAKE_REFRESH, _FAKE_ACCESS)


def _now() -> str:
    return "2026-07-27T00:00:00Z"


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
    """Stands in for the `requests` module inside one service module.

    Records every call so a test can assert HOW MANY times Google was
    reached -- which is how the token cache and the release-on-failure
    path are proven.
    """

    class RequestException(Exception):
        pass

    def __init__(self):
        self.calls = []
        self.post_queue = []
        self.request_queue = []
        self.raise_on_next = None

    # oauth.py calls requests.post(...)
    def post(self, url, data=None, timeout=None, **kw):
        self.calls.append(("POST", url, data))
        if self.raise_on_next is not None:
            exc = self.raise_on_next
            self.raise_on_next = None
            raise exc
        if self.post_queue:
            return self.post_queue.pop(0)
        return _FakeResponse(200, {"access_token": _FAKE_ACCESS,
                                   "expires_in": 3600})

    # picker_client.py calls requests.request(...)
    def request(self, method, url, headers=None, json=None, timeout=None, **kw):
        self.calls.append((method, url, headers))
        if self.raise_on_next is not None:
            exc = self.raise_on_next
            self.raise_on_next = None
            raise exc
        if self.request_queue:
            return self.request_queue.pop(0)
        return _FakeResponse(200, {
            "id": "picker-session-abc123",
            "pickerUri": "https://photos.google.com/picker/session/abc123",
            "mediaItemsSet": False,
            "pollingConfig": {"pollInterval": "5s", "timeoutIn": "1800s"},
            "expireTime": "2026-07-27T01:00:00Z",
        })


# ---------------------------------------------------------------- base


class _Base(unittest.TestCase):
    picker_flag = "1"
    prov_flag = "1"
    set_credentials = True

    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        tmp.close()
        self.db_path = Path(tmp.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()

        self._orig_env = {}
        for key, val in ((_PICKER_FLAG, self.picker_flag),
                         (_PROV_FLAG, self.prov_flag),
                         (oauth.ENV_CLIENT_ID,
                          _FAKE_CLIENT_ID if self.set_credentials else None),
                         (oauth.ENV_CLIENT_SECRET,
                          _FAKE_CLIENT_SECRET if self.set_credentials else None),
                         (oauth.ENV_REFRESH_TOKEN,
                          _FAKE_REFRESH if self.set_credentials else None)):
            self._orig_env[key] = os.environ.get(key)
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

        # Network doubles. Each service module holds its own reference.
        self.auth_http = _FakeRequests()
        self.api_http = _FakeRequests()
        self._orig_oauth_requests = oauth.requests
        self._orig_client_requests = picker_client.requests
        oauth.requests = self.auth_http
        picker_client.requests = self.api_http
        oauth.reset_cache()

        app = FastAPI()
        app.include_router(gp.router)
        self.client = TestClient(app, raise_server_exceptions=False)

        self.person_id = self._insert_person("Christopher Todd Horne")
        self.other_person_id = self._insert_person("Kent James Horne")
        self.trip_id = self._insert_trip(self.person_id, "Europe 2026")
        self.other_trip_id = self._insert_trip(self.other_person_id, "Not His")

    def tearDown(self):
        self.client.close()
        oauth.requests = self._orig_oauth_requests
        picker_client.requests = self._orig_client_requests
        oauth.reset_cache()
        _db.DB_PATH = self._orig_db
        for key, val in self._orig_env.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        try:
            self.db_path.unlink()
        except OSError:
            pass

    # -- helpers ---------------------------------------------------------

    def _con(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON;")
        return con

    def _insert_person(self, name: str) -> str:
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

    def _insert_trip(self, person_id: str, title: str) -> str:
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

    def _batch_rows(self):
        con = self._con()
        try:
            return con.execute("SELECT * FROM import_batch").fetchall()
        finally:
            con.close()

    def _candidate_count(self) -> int:
        con = self._con()
        try:
            return con.execute(
                "SELECT COUNT(*) AS n FROM import_candidate").fetchone()["n"]
        finally:
            con.close()

    def _assert_no_secret_in(self, resp):
        """Rule 2, applied to one response. Checks the raw bytes, so a
        secret nested anywhere in the JSON is caught."""
        body = resp.text
        for secret in _ALL_SECRETS:
            self.assertNotIn(secret, body,
                             "a credential leaked into a response body")

    def _open_session(self, **over):
        payload = {"person_id": self.person_id}
        payload.update(over)
        return self.client.post("/api/google-picker/sessions", json=payload)


# ---------------------------------------------------------------- 1. gate


class TestGate(_Base):
    """Rule 1. Both flags, or nothing."""

    ROUTES = (
        ("GET", "/api/google-picker/health"),
        ("GET", "/api/google-picker/sessions/anything"),
        ("DELETE", "/api/google-picker/sessions/anything"),
    )

    def _assert_all_404(self):
        for method, path in self.ROUTES:
            r = self.client.request(method, path)
            self.assertEqual(r.status_code, 404,
                             "%s %s should 404 while the lane is off, got %d"
                             % (method, path, r.status_code))
        r = self._open_session()
        self.assertEqual(r.status_code, 404)

    def test_both_flags_on_is_the_only_open_state(self):
        r = self.client.get("/api/google-picker/health")
        self.assertEqual(r.status_code, 200)


class TestGateBothOff(TestGate):
    picker_flag = "0"
    prov_flag = "0"

    def test_both_flags_on_is_the_only_open_state(self):
        self._assert_all_404()


class TestGatePickerOnly(TestGate):
    picker_flag = "1"
    prov_flag = "0"

    def test_both_flags_on_is_the_only_open_state(self):
        # The picker lane writes import_batch rows through the provenance
        # repository. Running with provenance off would open batches no
        # route can read, so this combination is closed on purpose.
        self._assert_all_404()


class TestGateProvenanceOnly(TestGate):
    picker_flag = "0"
    prov_flag = "1"

    def test_both_flags_on_is_the_only_open_state(self):
        self._assert_all_404()


class TestGateBeatsBodyValidation(_Base):
    picker_flag = "0"

    def test_empty_body_is_404_not_422(self):
        """A gate that lived only in the handler would let FastAPI answer 422
        with the required field names while the lane was off -- announcing
        both that the route exists and what it wants. The dependency
        resolves before body validation, so 404 wins."""
        r = self.client.post("/api/google-picker/sessions", json={})
        self.assertEqual(r.status_code, 404, r.text)
        self.assertNotIn("person_id", r.text)

    def test_nothing_reached_google(self):
        self.client.post("/api/google-picker/sessions", json={})
        self.assertEqual(self.auth_http.calls, [])
        self.assertEqual(self.api_http.calls, [])


# ---------------------------------------------------------------- 2. health


class TestHealth(_Base):

    def test_reports_presence_as_booleans_only(self):
        r = self.client.get("/api/google-picker/health")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["credentials_complete"])
        present = body["credentials_present"]
        self.assertEqual(sorted(present), sorted(oauth.CREDENTIAL_ENV_KEYS))
        for key, val in present.items():
            self.assertIsInstance(val, bool,
                                  "%s must be a boolean, not %r" % (key, val))
        self._assert_no_secret_in(r)

    def test_health_does_not_mint_a_token(self):
        """Reporting configuration must not spend a round trip on Google,
        or a health check would fail whenever the network did."""
        self.client.get("/api/google-picker/health")
        self.assertEqual(self.auth_http.calls, [])

    def test_reports_the_flags_and_the_single_scope(self):
        body = self.client.get("/api/google-picker/health").json()
        self.assertTrue(body["flags"][_PICKER_FLAG])
        self.assertTrue(body["flags"][_PROV_FLAG])
        self.assertEqual(body["scope"], oauth.PICKER_SCOPE)
        self.assertIn("photospicker.mediaitems.readonly", body["scope"])
        # MOVED FORWARD in the 2B ingest commit. This asserted `phase == 1`.
        # An operator reads this number to decide whether the stack in
        # front of them can ingest, so holding it at 1 once the route
        # exists would not have been a wall holding -- it would have been
        # the health check lying. What must NOT move is the line above:
        # one read-only scope, no matter how many phases land.
        self.assertEqual(body["phase"], 2)
        self.assertTrue(body["ingest_available"])


class TestHealthNoCredentials(_Base):
    set_credentials = False

    def test_missing_credentials_are_reported_not_crashed(self):
        r = self.client.get("/api/google-picker/health")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertFalse(body["credentials_complete"])
        self.assertEqual(set(body["credentials_present"].values()), {False})

    def test_a_call_that_needs_a_token_is_503_and_names_what_is_missing(self):
        r = self._open_session()
        self.assertEqual(r.status_code, 503, r.text)
        detail = r.json()["detail"]
        self.assertEqual(detail["reason"], "credentials_missing")
        for key in oauth.CREDENTIAL_ENV_KEYS:
            self.assertIn(key, detail["detail"])
        self.assertEqual(self._batch_rows(), [],
                         "no batch may be opened without credentials")


# ---------------------------------------------------------------- 3. auth


class TestAuth(_Base):

    def test_token_is_cached_across_calls(self):
        self._open_session()
        self._open_session()
        posts = [c for c in self.auth_http.calls if c[0] == "POST"]
        self.assertEqual(len(posts), 1,
                         "the access token should be minted once and reused")

    def test_dead_refresh_token_is_named(self):
        self.auth_http.post_queue.append(
            _FakeResponse(400, {"error": "invalid_grant",
                                "error_description": "Token has been expired "
                                                     "or revoked."}))
        r = self._open_session()
        self.assertEqual(r.status_code, 503, r.text)
        detail = r.json()["detail"]
        self.assertEqual(detail["reason"], "refresh_token_expired")
        self.assertIn("7 days", detail["detail"])
        self._assert_no_secret_in(r)

    def test_a_refused_exchange_never_echoes_the_request(self):
        self.auth_http.post_queue.append(
            _FakeResponse(401, {"error": "invalid_client",
                                "error_description": "Unauthorized"}))
        r = self._open_session()
        self.assertEqual(r.status_code, 502, r.text)
        self._assert_no_secret_in(r)

    def test_a_non_json_token_body_is_not_pasted_into_the_error(self):
        self.auth_http.post_queue.append(_FakeResponse(500, _NO_JSON))
        r = self._open_session()
        self.assertEqual(r.status_code, 502, r.text)
        self.assertIn("withheld", r.json()["detail"]["detail"])
        self._assert_no_secret_in(r)

    def test_network_failure_is_502_not_500(self):
        self.auth_http.raise_on_next = oauth.requests.RequestException(
            "connection refused")
        r = self._open_session()
        self.assertEqual(r.status_code, 502, r.text)
        self.assertEqual(r.json()["detail"]["reason"], "network")

    def test_absurd_expires_in_is_treated_as_short(self):
        """Being wrong short costs one round trip. Being wrong long means
        calls fail holding a dead token."""
        oauth.reset_cache()
        self.auth_http.post_queue.append(
            _FakeResponse(200, {"access_token": _FAKE_ACCESS,
                                "expires_in": 999999}))
        oauth.get_access_token()
        state = oauth.cache_state()
        self.assertTrue(state["access_token_cached"])
        self.assertLessEqual(state["expires_in_seconds"], 600)


# ---------------------------------------------------------------- 4. create


class TestCreateSession(_Base):

    def test_opens_a_picker_batch_carrying_the_session_id(self):
        r = self._open_session(trip_id=self.trip_id, label="Europe pick")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["picker_uri"],
                         "https://photos.google.com/picker/session/abc123")
        self.assertFalse(body["media_items_set"])

        rows = self._batch_rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["id"], body["batch_id"])
        self.assertEqual(row["source"], "google_photos_picker")
        self.assertEqual(row["external_ref"], "picker-session-abc123")
        self.assertEqual(row["person_id"], self.person_id)
        self.assertEqual(row["trip_id"], self.trip_id)
        self.assertEqual(row["status"], "open")

    def test_creates_no_candidates(self):
        """Rule 6. Phase 1 opens a session; it does not intake anything."""
        self._open_session()
        self.assertEqual(self._candidate_count(), 0)

    def test_trip_binding_is_optional(self):
        r = self._open_session()
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNone(self._batch_rows()[0]["trip_id"])

    def test_another_persons_trip_is_refused_and_leaves_no_batch(self):
        r = self._open_session(trip_id=self.other_trip_id)
        self.assertIn(r.status_code, (400, 409), r.text)
        self.assertEqual(self._batch_rows(), [])

    def test_a_failed_batch_open_releases_the_google_session(self):
        """Rule 4. Google succeeded, the batch did not. The session is
        handed back rather than orphaned in the operator's account."""
        r = self._open_session(person_id=str(uuid.uuid4()))
        self.assertGreaterEqual(r.status_code, 400)
        self.assertEqual(self._batch_rows(), [])
        deletes = [c for c in self.api_http.calls if c[0] == "DELETE"]
        self.assertEqual(len(deletes), 1,
                         "the picker session should have been released")

    def test_upstream_failure_opens_no_batch(self):
        self.api_http.request_queue.append(
            _FakeResponse(403, {"error": {"status": "PERMISSION_DENIED",
                                          "message": "Photos Picker API has "
                                                     "not been used"}}))
        r = self._open_session()
        self.assertEqual(r.status_code, 502, r.text)
        self.assertEqual(self._batch_rows(), [],
                         "Google is called before the batch is opened, so an "
                         "upstream failure must leave no debris")
        self._assert_no_secret_in(r)

    def test_person_id_is_required(self):
        r = self.client.post("/api/google-picker/sessions", json={})
        self.assertEqual(r.status_code, 422, r.text)

    def test_bearer_header_is_sent_but_never_returned(self):
        r = self._open_session()
        self.assertEqual(r.status_code, 200)
        posts = [c for c in self.api_http.calls if c[0] == "POST"]
        self.assertEqual(posts[0][2]["Authorization"],
                         "Bearer %s" % _FAKE_ACCESS)
        self._assert_no_secret_in(r)


# ---------------------------------------------------------------- 5. poll


class TestPollSession(_Base):

    def setUp(self):
        super().setUp()
        self.batch_id = self._open_session(trip_id=self.trip_id).json()["batch_id"]

    def test_poll_reports_media_items_set(self):
        self.api_http.request_queue.append(_FakeResponse(200, {
            "id": "picker-session-abc123",
            "pickerUri": "https://photos.google.com/picker/session/abc123",
            "mediaItemsSet": True,
            "pollingConfig": {"pollInterval": "5s", "timeoutIn": "1800s"},
        }))
        r = self.client.get("/api/google-picker/sessions/%s" % self.batch_id)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["media_items_set"])
        self.assertEqual(body["trip_id"], self.trip_id)
        self.assertEqual(body["batch_status"], "open")

    def test_poll_offers_ingest_only_once_the_operator_has_finished_picking(
            self):
        """MOVED FORWARD in the 2B ingest commit (was
        `test_poll_says_ingest_does_not_exist_yet`).

        The old wall said the payload must not imply a next step that had
        not been built. The step is built, so the wall is PASSED -- and
        the property worth keeping is the honest half of it: the payload
        must never advertise a next step that would refuse. This
        `_Base` fixture polls a session whose `mediaItemsSet` is false,
        so ingest is not offered yet; `test_poll_reports_media_items_set`
        above covers the true case. If `ingest_available` ever stops
        agreeing with what the ingest route would actually accept, a UI
        built on it starts showing operators a button that answers 409."""
        body = self.client.get(
            "/api/google-picker/sessions/%s" % self.batch_id).json()
        self.assertEqual(body["phase"], 2)
        self.assertFalse(body["media_items_set"])
        self.assertFalse(body["ingest_available"],
                         "the operator has not finished picking; offering "
                         "ingest here would offer a 409")
        self.assertEqual(body["ingest_path"],
                         "/api/google-picker/sessions/%s/ingest"
                         % self.batch_id)

    def test_unknown_batch_is_404(self):
        r = self.client.get("/api/google-picker/sessions/%s" % uuid.uuid4())
        self.assertEqual(r.status_code, 404)

    def test_a_non_picker_batch_is_refused(self):
        other = repo.batch_create(person_id=self.person_id,
                                  source="local_upload")
        r = self.client.get("/api/google-picker/sessions/%s" % other)
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIn("local_upload", r.text)

    def test_upstream_404_maps_to_404(self):
        self.api_http.request_queue.append(
            _FakeResponse(404, {"error": {"status": "NOT_FOUND",
                                          "message": "Session not found"}}))
        r = self.client.get("/api/google-picker/sessions/%s" % self.batch_id)
        self.assertEqual(r.status_code, 404, r.text)


# ---------------------------------------------------------------- 6. delete


class TestDeleteSession(_Base):

    def setUp(self):
        super().setUp()
        self.batch_id = self._open_session(trip_id=self.trip_id).json()["batch_id"]

    def test_delete_releases_google_and_keeps_the_batch(self):
        """Rule 5. The one DELETE verb in this lane removes a session
        handle at Google and no row in this database."""
        self.api_http.request_queue.append(_FakeResponse(200, {}, content=b""))
        r = self.client.delete("/api/google-picker/sessions/%s" % self.batch_id)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["picker_session_released"])
        self.assertFalse(body["batch_deleted"])

        rows = self._batch_rows()
        self.assertEqual(len(rows), 1, "the import batch must survive")
        self.assertEqual(rows[0]["id"], self.batch_id)
        self.assertEqual(rows[0]["status"], "open")

    def test_already_gone_upstream_is_not_an_error(self):
        self.api_http.request_queue.append(
            _FakeResponse(404, {"error": {"status": "NOT_FOUND",
                                          "message": "Session not found"}}))
        r = self.client.delete("/api/google-picker/sessions/%s" % self.batch_id)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["already_gone"])
        self.assertEqual(len(self._batch_rows()), 1)

    def test_unknown_batch_is_404_and_reaches_no_upstream(self):
        before = len(self.api_http.calls)
        r = self.client.delete("/api/google-picker/sessions/%s" % uuid.uuid4())
        self.assertEqual(r.status_code, 404)
        self.assertEqual(len(self.api_http.calls), before)


# ---------------------------------------------------------------- 7. walls


class TestPhaseWalls(_Base):
    """Rule 6, as source-level assertions. These are the checks that will
    fail loudly if a later session reaches past the Phase 1 wall without
    doing the work the wall exists to force."""

    def test_the_picker_never_asks_the_operator_to_upload_the_file(self):
        """MOVED FORWARD 2026-07-29 (was
        `test_picker_source_is_not_promotable_yet`).

        The retired assertion read, verbatim:

            self.assertNotIn("google_photos_picker", repo.PROMOTABLE_SOURCES,
                             "google_photos_picker may only join
                             PROMOTABLE_SOURCES in Phase 3, after Phase 2
                             can stage real bytes")

        Its condition has been met. Phase 2B stages real bytes and
        hash-verifies them, so the thing the wall was waiting for has
        happened. But the list was NOT widened to let the picker in --
        it was renamed, because it never meant "may be promoted". It
        meant "may be promoted FROM AN UPLOADED FILE", and that is still
        false for the picker and must stay false: an operator must never
        be told to download their own Google photo and post it back.

        So the wall moves one step in, to the tighter claim: the list is
        about uploads, the picker is not on it, and the old name is
        gone rather than quietly still accepting the picker."""
        self.assertFalse(
            hasattr(repo, "PROMOTABLE_SOURCES"),
            "PROMOTABLE_SOURCES was renamed UPLOAD_SOURCES; a module still "
            "exporting the old name is one that never moved the wall")
        self.assertEqual(repo.UPLOAD_SOURCES, ("local_upload", "manual"))
        self.assertNotIn("google_photos_picker", repo.UPLOAD_SOURCES)
        self.assertIn("google_photos_picker", repo.IMPORT_SOURCES)

    def test_promotion_is_gated_on_a_verified_file_not_on_a_source_name(self):
        """The replacement precondition, asserted as structure.

        A source-name allowlist can be widened by one word and will then
        happily promote a candidate whose bytes are absent or wrong. The
        precondition that actually protects the archive is "a verified
        local copy of this candidate's picture is on disk", so the
        repository has to own three things: a way to find that copy, and
        two distinct, named refusals for the two ways it can be
        unusable. Their absence would mean the gate reverted to a list."""
        for name in ("staged_original_path", "StagedOriginalMissingError",
                     "StagedOriginalMismatchError"):
            self.assertTrue(hasattr(repo, name),
                            "promotion is gated on verified staged bytes; %r "
                            "is part of that gate" % name)

    def test_listing_exists_but_downloads_nothing(self):
        """Phase 2A added `list_media_items`. What it must NOT have
        grown is a byte fetch: `baseUrl` is only ever returned to a
        caller here, never followed. Following it is Phase 2B."""
        self.assertTrue(hasattr(picker_client, "list_media_items"),
                        "Phase 2A shipped media-item listing")
        src = _CLIENT_PATH.read_text(encoding="utf-8")
        for forbidden in ("=d\"", "stream=True", "iter_content",
                          "open(", "import shutil", "import tempfile",
                          "import os"):
            self.assertNotIn(forbidden, src,
                             "%r reads like a byte download; acquisition is "
                             "Phase 2B, not the listing client" % forbidden)

    def test_the_listing_is_wired_to_ingest_and_the_router_follows_no_url(self):
        """MOVED FORWARD in Phase 2B (was
        `test_no_route_is_wired_to_the_listing_yet`).

        The old wall said the router must not mention `list_media_items`
        at all, because 2A had to be reviewable with no caller. 2B is the
        session that wires it up, so that wall has been PASSED, not
        loosened -- and the wall moves to the next thing worth forcing.

        What is worth forcing now is WHO follows the download URL. The
        router may ask the listing for items, but `baseUrl` is a
        bearer-scoped URL: possession of it is possession of the
        photograph. Exactly one module is allowed to follow one, and that
        module is `acquire`, which knows to cap the read, verify the
        content and keep the URL out of every message it raises. If the
        router ever grows its own `requests.get` on an item URL, this
        fails."""
        src = _ROUTER_PATH.read_text(encoding="utf-8")
        self.assertIn("picker_client.list_media_items(", src,
                      "Phase 2B wires the listing into the ingest route")
        self.assertIn("acquire.download_original(", src,
                      "the route hands the item to acquire; it does not "
                      "fetch bytes itself")
        for forbidden in ("requests.get(", "requests.post(", "stream=True",
                          "iter_content", "urlopen("):
            self.assertNotIn(forbidden, src,
                             "%r means the router is following a download "
                             "URL itself; that belongs to acquire, which is "
                             "the only module allowed to hold a baseUrl"
                             % forbidden)

    def test_the_router_deletes_nothing_from_the_database(self):
        src = _ROUTER_PATH.read_text(encoding="utf-8")
        self.assertNotIn("DELETE FROM", src.upper())

    def test_the_router_creates_candidates_but_judges_none(self):
        """MOVED FORWARD in Phase 2B (was
        `test_the_router_creates_no_candidates`).

        Phase 1 had no way to produce bytes, so a candidate row would
        have been a claim with nothing behind it. 2B can stage verified
        bytes, so creating rows is now the job -- that wall is PASSED.

        The wall that replaces it is the one that still matters: creating
        a candidate is not judging one. Every row this route writes is
        born `pending` and waits for Lori in the existing evidence queue.
        No automated failure may become a terminal decision, and nothing
        here may promote into `photos`. Phase 3 opens that door.

        Asserted as an exact set of repository attributes rather than a
        blocklist, so a NEW repository call fails this test even if
        nobody thought to forbid it by name -- and so the deliberate
        prose mentions of `candidate_decide()` in the module docstrings,
        which are there to explain why it is NOT called, do not read as
        dependencies.

        MOVED FORWARD AGAIN on 2026-07-29, by exactly two names, and the
        move is recorded here rather than performed silently because an
        exact-set assertion whose set grows without explanation stops
        being an assertion.

        `candidate_restage` is the repair writer. Doctrine 1.14: a
        provider is not expected to return identical bytes on a later
        fetch, so when Hornelore's staged working copy is missing or no
        longer hashes to its row, the item is fetched again and the
        row's BYTE-DERIVED fields are re-stamped to describe the copy now
        on disk. It writes `file_hash`, `byte_size`, `mime_type`, the two
        date fields and the three location fields, and it writes nothing
        else -- not `state`, not `photo_id`, not `trip_id`, not
        `person_id`, not `external_id`, not a review field. It is
        therefore not a decision and not a promotion, and the wall this
        test defends is intact: the row it repairs is still `pending` and
        still waiting for Lori afterwards, which
        `TestReIngest.test_a_re_ingest_records_no_operator_decision`
        asserts from the other side.

        `CandidateAlreadyPromotedError` is caught, never raised here. It
        is the repository refusing to re-stamp a candidate that already
        points at a permanent archive photo -- doctrine 1.14's archive
        boundary -- and the router catches it only to report it under its
        own name rather than letting it blur into `repository_refused`.
        Catching an error is not reaching through a wall; it is being
        told about one.

        What did NOT enter the set, and must not: `candidate_decide`,
        `candidate_promote`, `candidate_set_trip`, `candidate_hide`.
        Phase 3 opens that door."""
        tree = ast.parse(_ROUTER_PATH.read_text(encoding="utf-8"))
        used = {node.attr for node in ast.walk(tree)
                if isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "repo"}
        self.assertEqual(
            used,
            # Errors the route catches and translates into HTTP, plus the
            # six calls it makes. `candidate_create` and `candidates_list`
            # arrived with the 2B ingest route; the batch calls are 1's;
            # `candidate_restage` and `CandidateAlreadyPromotedError`
            # arrived on 2026-07-29 with the repair path, for the reasons
            # in this test's docstring.
            {"BatchClosedError", "BatchNotFoundError",
             "CandidateAlreadyPromotedError", "CrossPersonError",
             "CrossTripError", "ExternalTokenError", "ImportRepositoryError",
             "IntakeIsNotApprovalError", "InvalidStateError",
             "batch_close", "batch_create", "batch_get",
             "candidate_create", "candidate_restage", "candidates_list"},
            "the router reached for a repository call it did not have "
            "before; if it is a decision or a promotion it belongs to "
            "Phase 3, and if it is something else it belongs in this set "
            "with a reason")

    def test_no_module_in_the_lane_reads_a_credential_into_a_response(self):
        """The credential env names may appear in oauth.py (it reads them)
        and in the router's health payload keys, but no module may
        interpolate os.environ into a returned body. Proxy check: the
        router never touches the credential env vars directly."""
        src = _ROUTER_PATH.read_text(encoding="utf-8")
        for key in oauth.CREDENTIAL_ENV_KEYS:
            self.assertNotIn(key, src,
                             "the router should ask oauth for presence, not "
                             "read %s itself" % key)


if __name__ == "__main__":
    unittest.main()
