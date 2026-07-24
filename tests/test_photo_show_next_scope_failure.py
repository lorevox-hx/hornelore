"""WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 §3.4 — COMMIT 3 tests.

photos.show_next trip-scope FAIL CLOSED. A failure reading the trip's
allowed photo IDs for a trip-scoped session used to reset
`allowed_ids = None`, which select_next_photo treats as "no allowlist"
— silently widening a trip-scoped elicitation session to the narrator's
WHOLE photo pool. Now the trip-scoped path either honors its scope or
refuses with a classified 500; narrator-wide selection is preserved
ONLY when no trip scope was requested.

Import strategy: the photos router uses `from ...services...` relative
imports that only resolve under the production package layout
(`python -m uvicorn code.api.main:app` with cwd=server). Naive
`api.routers.photos` import fails with "relative import beyond
top-level package", so we mirror production: put `server` on sys.path
and import `code.api.routers.photos`. The router's collaborators
(photo_repo / select_next_photo / trip_repository) are then
monkeypatched on the imported module objects — the routing/fail-closed
logic under test is the REAL production function.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(_REPO_ROOT / "server" / "code"),
           str(_REPO_ROOT / "server"),
           str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# The stdlib `code` module (InteractiveInterpreter) shadows the
# production `server/code` package if something imported it first (pdb
# does). Drop the module-shaped entry so the package wins.
if "code" in sys.modules and not hasattr(sys.modules["code"], "__path__"):
    del sys.modules["code"]

# Shared-process defense: several sibling test modules install FAKE
# fastapi/pydantic stubs into sys.modules at import time (offline
# pattern) and never remove them. The real packages ARE installed in
# this environment and photos.py needs them (fastapi.responses etc.),
# so purge any stub (a bare ModuleType has no __path__; the real ones
# are packages) before importing the router.
for _stub_name in ("fastapi", "pydantic"):
    _stub = sys.modules.get(_stub_name)
    if _stub is not None and not hasattr(_stub, "__path__"):
        for _k in [k for k in list(sys.modules)
                   if k == _stub_name or k.startswith(_stub_name + ".")]:
            del sys.modules[_k]

# Second pollution shape (pre-existing, seen in full-discover runs):
# tests/test_extract_vague_temporal_guard.py MUTATES whatever
# fastapi/pydantic module is already in sys.modules — including the
# REAL packages (fastapi.APIRouter becomes a two-verb stub with no
# .patch; pydantic.BaseModel becomes `object`). Repair by restoring the
# clobbered top-level attributes from the UNTOUCHED submodules — a full
# package reload would mint new class objects and break identity with
# fastapi's cached pydantic references.
_real_fa = sys.modules.get("fastapi")
if _real_fa is not None and hasattr(_real_fa, "__path__"):
    _api_router = getattr(_real_fa, "APIRouter", None)
    if not (isinstance(_api_router, type)
            and getattr(_api_router, "__module__", "").startswith("fastapi")):
        from fastapi.routing import APIRouter as _orig_api_router
        from fastapi.exceptions import HTTPException as _orig_http_exc
        from fastapi.param_functions import Query as _orig_query
        _real_fa.APIRouter = _orig_api_router
        _real_fa.HTTPException = _orig_http_exc
        _real_fa.Query = _orig_query
_real_pd = sys.modules.get("pydantic")
if _real_pd is not None and hasattr(_real_pd, "__path__"):
    _base_model = getattr(_real_pd, "BaseModel", None)
    if not (isinstance(_base_model, type)
            and getattr(_base_model, "__module__", "").startswith("pydantic")):
        from pydantic.main import BaseModel as _orig_base_model
        from pydantic.fields import Field as _orig_pd_field
        _real_pd.BaseModel = _orig_base_model
        _real_pd.Field = _orig_pd_field
        try:
            from pydantic.functional_validators import (
                field_validator as _orig_field_validator,
            )
            _real_pd.field_validator = _orig_field_validator
        except Exception:
            pass
        try:
            from pydantic.config import ConfigDict as _orig_config_dict
            _real_pd.ConfigDict = _orig_config_dict
        except Exception:
            pass

from fastapi import HTTPException  # noqa: E402  (real fastapi)

from code.api.routers import photos as photos_router  # noqa: E402
from code.api.services import trip_repository as trip_repo_mod  # noqa: E402

# The photo surface is flag-gated per request; enable for these tests.
os.environ["HORNELORE_PHOTO_ENABLED"] = "1"


class _RepoStub:
    """Minimal photo_repo stand-in for show_next's collaborators."""

    def __init__(self, session_row):
        self.session_row = session_row
        self.recorded_shows = []

    def get_photo_session(self, sid):
        return dict(self.session_row)

    def get_photo(self, pid, deleted=False):
        return {"id": pid, "people": [], "location_label": None,
                "date_value": None}

    def record_photo_show(self, photo_session_id, photo_id, prompt_text):
        self.recorded_shows.append(photo_id)
        return {"id": "show-1"}


class _Patched:
    """Patch photos_router.photo_repo / select_next_photo and
    trip_repository.photo_links_list / stop_get; restore on exit."""

    def __init__(self, repo_stub, selector, links_fn=None, stop_fn=None):
        self.repo_stub = repo_stub
        self.selector = selector
        self.links_fn = links_fn
        self.stop_fn = stop_fn

    def __enter__(self):
        self._orig = (photos_router.photo_repo,
                      photos_router.select_next_photo,
                      trip_repo_mod.photo_links_list,
                      trip_repo_mod.stop_get)
        photos_router.photo_repo = self.repo_stub
        photos_router.select_next_photo = self.selector
        if self.links_fn is not None:
            trip_repo_mod.photo_links_list = self.links_fn
        if self.stop_fn is not None:
            trip_repo_mod.stop_get = self.stop_fn
        return self

    def __exit__(self, *exc):
        (photos_router.photo_repo,
         photos_router.select_next_photo,
         trip_repo_mod.photo_links_list,
         trip_repo_mod.stop_get) = self._orig
        return False


class _SelectorSpy:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def __call__(self, narrator_id=None, repository=None, photo_ids=None):
        self.calls.append({"narrator_id": narrator_id,
                           "photo_ids": photo_ids})
        return self.result


_TRIP_SESSION = {"id": "sess-trip", "narrator_id": "narr-1",
                 "trip_id": "trip-1", "trip_stop_id": None,
                 "ended_at": None}
_UNSCOPED_SESSION = {"id": "sess-plain", "narrator_id": "narr-1",
                     "trip_id": None, "trip_stop_id": None,
                     "ended_at": None}


class TripScopeFailureFailsClosedTest(unittest.TestCase):
    def test_sqlite_failure_never_widens_to_whole_pool(self):
        repo = _RepoStub(_TRIP_SESSION)
        selector = _SelectorSpy({"id": "leaked-photo"})

        def _boom(trip_id):
            raise sqlite3.OperationalError("database is locked")

        with _Patched(repo, selector, links_fn=_boom):
            with self.assertRaises(HTTPException) as cm:
                photos_router.show_next("sess-trip")
        # Classified 500, never a silent whole-pool widening.
        self.assertEqual(cm.exception.status_code, 500)
        detail = str(cm.exception.detail)
        self.assertIn("fail closed", detail)
        self.assertIn("database is locked", detail)
        # sqlite failures carry a sqlite classification prefix.
        self.assertRegex(detail, r"SQLITE_|sqlite3\.")
        # The selector was NEVER consulted — no photo left the scope.
        self.assertEqual(selector.calls, [])
        self.assertEqual(repo.recorded_shows, [])

    def test_stop_lookup_failure_also_fails_closed(self):
        repo = _RepoStub(_TRIP_SESSION)
        selector = _SelectorSpy({"id": "leaked-photo"})

        def _links_ok(trip_id):
            return [{"photo_id": "p1", "trip_stop_id": "stop-1"}]

        def _stop_boom(sid):
            raise ValueError("corrupt stop row")

        with _Patched(repo, selector, links_fn=_links_ok,
                      stop_fn=_stop_boom):
            with self.assertRaises(HTTPException) as cm:
                photos_router.show_next("sess-trip")
        self.assertEqual(cm.exception.status_code, 500)
        self.assertIn("ValueError", str(cm.exception.detail))
        self.assertEqual(selector.calls, [])

    def test_healthy_trip_scope_passes_allowlist(self):
        repo = _RepoStub(_TRIP_SESSION)
        selector = _SelectorSpy({"id": "p1"})

        def _links_ok(trip_id):
            return [{"photo_id": "p1", "trip_stop_id": "stop-1"},
                    {"photo_id": "p2", "trip_stop_id": None}]

        def _stop_ok(sid):
            return {"location_name": "Prague"}

        with _Patched(repo, selector, links_fn=_links_ok, stop_fn=_stop_ok):
            out = photos_router.show_next("sess-trip")
        self.assertEqual(selector.calls[0]["photo_ids"], ["p1", "p2"])
        self.assertEqual(out["photo"]["id"], "p1")


class UnscopedSessionKeepsBehaviorTest(unittest.TestCase):
    def test_unscoped_session_still_selects_narrator_wide(self):
        repo = _RepoStub(_UNSCOPED_SESSION)
        selector = _SelectorSpy({"id": "p9"})

        def _boom(trip_id):  # must not even be consulted
            raise AssertionError("trip scope read on an unscoped session")

        with _Patched(repo, selector, links_fn=_boom):
            out = photos_router.show_next("sess-plain")
        # Narrator-wide selection preserved ONLY here: photo_ids=None.
        self.assertEqual(selector.calls[0]["photo_ids"], None)
        self.assertEqual(out["photo"]["id"], "p9")
        self.assertEqual(repo.recorded_shows, ["p9"])

    def test_unscoped_session_none_pick_keeps_empty_shape(self):
        repo = _RepoStub(_UNSCOPED_SESSION)
        selector = _SelectorSpy(None)
        with _Patched(repo, selector):
            out = photos_router.show_next("sess-plain")
        self.assertEqual(out, {"photo": None, "show_id": None,
                               "prompt_text": None})


class SourceContractTest(unittest.TestCase):
    """The widening reset must be gone from the source."""

    def test_no_allowed_ids_none_reset_in_the_except_path(self):
        src = (_REPO_ROOT / "server" / "code" / "api" / "routers" /
               "photos.py").read_text(encoding="utf-8")
        i = src.index("def show_next")
        body = src[i:i + 6000]
        self.assertNotIn(
            "allowed_ids = None\n", body.split("except Exception", 1)[1]
            .split("picked = select_next_photo", 1)[0],
            "the except path resets allowed_ids to None again — that IS "
            "the whole-pool widening this WO removed")
        self.assertIn("FAIL CLOSED", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
