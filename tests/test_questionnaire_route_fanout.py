"""WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01 Phase 3 — route-level
tests for the PUT fan-out flag composition.

Validates that the env-flag matrix behaves as documented in .env.example:

  FANOUT=0 + LEGACY=1 (default): status quo, legacy blob only
  FANOUT=1 + LEGACY=1:           dual-write
  FANOUT=1 + LEGACY=0:           canonical-only
  FANOUT=0 + LEGACY=0:           writes go nowhere — acceptable
                                  current behavior; PUT route does
                                  not refuse (TODO in .env doc).

We exercise the put_questionnaire_route function directly with a
mocked payload + patched downstream services.

⚠ WHAT THIS FILE CANNOT SEE, AND WHY THAT MATTERED (2026-09-17)
───────────────────────────────────────────────────────────────
Every test here MOCKS the legacy writer. It can therefore prove

    "the route called the legacy writer"

and it can never prove

    "the writer preserved the narrator's existing data".

That gap is not hypothetical. On 2026-09-15 an ordinary Bio Builder save
deleted ten populated values from a real narrator's parents — birth dates,
birthplaces, and several hundred words of hand-typed family history — and
this suite stayed green throughout, because the destruction happened
inside the seam it replaces with a MagicMock.

These seven tests are still correct and still worth having: flag
composition IS what they are for. But data integrity is tested in
`tests/test_questionnaire_persistence_integrity.py`, which writes to a
real temporary SQLite file and reads the result back out of SQLite rather
than through the API. Do not add integrity assertions here — a test that
checks the API against the API cannot see this class of defect at all.

The patch target changed from `upsert_questionnaire` to
`_qp.merge_whole_document` when the route stopped calling the blind
whole-document replace (WO-QUESTIONNAIRE-PERSISTENCE-INTEGRITY-01).
"""
from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))


# ── Stub fastapi + pydantic (sandbox has no PyPI access) ─────────────
if "fastapi" not in sys.modules:
    fa = types.ModuleType("fastapi")
    class _APIRouter:
        def __init__(self, *a, **kw): pass
        def get(self, *a, **kw):
            def deco(fn): return fn
            return deco
        def put(self, *a, **kw):
            def deco(fn): return fn
            return deco
        def post(self, *a, **kw):
            def deco(fn): return fn
            return deco
    class _HTTPException(Exception):
        def __init__(self, status_code=500, detail=""):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail
    def _Query(default=None, **_kw): return default
    fa.APIRouter = _APIRouter
    fa.HTTPException = _HTTPException
    fa.Query = _Query
    sys.modules["fastapi"] = fa

if "pydantic" not in sys.modules:
    pd = types.ModuleType("pydantic")
    class _BaseModel:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)
            # Apply class-level defaults for any fields the caller
            # didn't pass — the route accesses some defaults (e.g.
            # version, source).
            for k in dir(type(self)):
                if k.startswith("_") or callable(getattr(type(self), k, None)):
                    continue
                if k not in self.__dict__:
                    setattr(self, k, getattr(type(self), k))
        class Config:
            populate_by_name = True
        def model_dump(self):
            return {k: v for k, v in self.__dict__.items()
                    if not k.startswith("_")}
    def _Field(default=None, default_factory=None, **_kw):
        if default_factory is not None:
            return default_factory()
        return default
    pd.BaseModel = _BaseModel
    pd.Field = _Field
    sys.modules["pydantic"] = pd


_DUMMY_BLOB = {
    "personal": {
        "fullName": "Test Narrator",
        "dateOfBirth": "1960-01-01",
        "placeOfBirth": "Anytown",
    },
}


def _fresh_payload():
    from api.routers.questionnaire import QuestionnairePutRequest
    return QuestionnairePutRequest(
        person_id="narrator-test",
        questionnaire=_DUMMY_BLOB,
        source="ui_save",
        version=1,
    )


class FanoutFlagOffLegacyOn(unittest.TestCase):
    """Default state — legacy blob writes, no fan-out."""

    def test_fanout_off_legacy_on(self):
        from api.routers import questionnaire as qroute
        with patch.dict(os.environ, {
            "HORNELORE_QUESTIONNAIRE_BIO_FACTS_WRITE": "0",
            "HORNELORE_QUESTIONNAIRE_LEGACY_BLOB_WRITE": "1",
        }), patch("api.routers.questionnaire._qp.merge_whole_document", return_value={
            "person_id": "narrator-test",
            "questionnaire": _DUMMY_BLOB,
            "source": "ui_save", "version": 1, "updated_at": "x",
        }) as mock_upsert, patch(
            "api.services.bio_questionnaire_writer.apply_questionnaire_writes",
            return_value={
                "bio_facts_written": 0, "bio_facts_errors": [],
                "profile_error": None, "profile_patch": {},
            },
        ) as mock_apply:
            resp = qroute.put_questionnaire_route(_fresh_payload())
        # Legacy blob write fired
        self.assertEqual(mock_upsert.call_count, 1)
        # Fan-out did NOT fire
        self.assertEqual(mock_apply.call_count, 0)
        self.assertEqual(resp.bio_facts_written, 0)
        self.assertTrue(resp.legacy_blob_written)


class NoOpIsReportedAsNoOp(unittest.TestCase):
    """BUG-QUESTIONNAIRE-NOOP-REPORTED-AS-WRITE-01 (2026-09-20).

    merge_whole_document has returned `write_applied: False` for an unchanged
    document since 6b0a877 ("a save that changes nothing is not a write").
    The router dropped it: QuestionnairePutResponse had no such field. So the
    browser's no-op detection, `j.write_applied === false`, could never fire
    against the real server, and an unchanged save rendered as green
    "Saved (revision N)".

    Found on the WO-01 live test — the operator saved Personal Information
    untouched, saw green, and the revision counter had not moved. The
    behavioural harness had passed because its server double returned the
    field the real route did not.
    """

    def _put(self, writer_result):
        from api.routers import questionnaire as qroute
        with patch.dict(os.environ, {
            "HORNELORE_QUESTIONNAIRE_BIO_FACTS_WRITE": "0",
            "HORNELORE_QUESTIONNAIRE_LEGACY_BLOB_WRITE": "1",
        }), patch("api.routers.questionnaire._qp.merge_whole_document",
                  return_value=writer_result):
            return qroute.put_questionnaire_route(_fresh_payload())

    def test_an_unchanged_save_says_so(self):
        resp = self._put({
            "person_id": "narrator-test", "questionnaire": _DUMMY_BLOB,
            "source": "ui_save", "version": 1, "updated_at": "x",
            "revision": 5, "write_applied": False, "ignored_blank_paths": [],
        })
        self.assertFalse(resp.write_applied,
                         "the writer said nothing changed; the route told the browser it had")
        self.assertEqual(resp.revision, 5)

    def test_a_real_write_says_so(self):
        resp = self._put({
            "person_id": "narrator-test", "questionnaire": _DUMMY_BLOB,
            "source": "ui_save", "version": 1, "updated_at": "x",
            "revision": 6, "write_applied": True, "ignored_blank_paths": [],
        })
        self.assertTrue(resp.write_applied)

    def test_a_writer_that_does_not_say_defaults_to_write(self):
        """Absence of the flag must not be read as a no-op — an older writer
        result that omits it is a write, and the banner should say saved."""
        resp = self._put({
            "person_id": "narrator-test", "questionnaire": _DUMMY_BLOB,
            "source": "ui_save", "version": 1, "updated_at": "x",
        })
        self.assertTrue(resp.write_applied)


class HarnessDoubleMayNotOutrunTheRoute(unittest.TestCase):
    """The behavioural harness's server double must not promise a response
    field the real route does not send.

    BUG-QUESTIONNAIRE-NOOP-REPORTED-AS-WRITE-01 was hidden by exactly that:
    the double returned `write_applied` from the day it was written, the real
    route did not, and sequence 3 ("an unchanged save says no changes")
    passed against a server that did not exist. A comment in the double now
    records this. A comment cannot fail. This can.

    Cross-language, deliberately mechanical: read the keys the double puts in
    its 200 PUT body, and require each to be a declared field on
    QuestionnairePutResponse.
    """

    def test_every_key_the_double_returns_is_a_real_response_field(self):
        import re
        from api.routers.questionnaire import QuestionnairePutResponse
        harness = (Path(__file__).resolve().parent / "harness" / "bio-builder-harness.js").read_text(encoding="utf8")
        # the success body: makeResponse(200, { ok: true, person_id: ..., revision: ..., write_applied: ... })
        m = re.search(r"applyMerge\([^)]*\);[\s\S]*?makeResponse\(200,\s*\{([\s\S]*?)\}\)\)", harness)
        self.assertIsNotNone(m, "could not find the double's successful PUT response body")
        keys = set(re.findall(r"(\w+)\s*:", m.group(1)))
        keys.discard("ok")
        # Annotations are what declare a field, with or without a default and
        # with or without real pydantic. `person_id: str` has no default, so
        # dir() alone missed it and this check failed against correct code.
        declared = set()
        for klass in QuestionnairePutResponse.__mro__:
            declared |= set(getattr(klass, "__annotations__", {}) or {})
        if hasattr(QuestionnairePutResponse, "model_fields"):
            declared |= set(QuestionnairePutResponse.model_fields)
        missing = sorted(keys - declared)
        self.assertEqual(missing, [],
                         f"the harness double returns {missing} but the real route does not "
                         "declare them — the double is lying about the server")

    def test_write_applied_is_declared_by_the_route(self):
        from api.routers.questionnaire import QuestionnairePutResponse
        self.assertTrue(hasattr(QuestionnairePutResponse, "write_applied") or
                        "write_applied" in getattr(QuestionnairePutResponse, "model_fields", {}))


class FanoutOnLegacyOn(unittest.TestCase):
    """Dual-write — both paths fire."""

    def test_fanout_on_legacy_on(self):
        from api.routers import questionnaire as qroute
        with patch.dict(os.environ, {
            "HORNELORE_QUESTIONNAIRE_BIO_FACTS_WRITE": "1",
            "HORNELORE_QUESTIONNAIRE_LEGACY_BLOB_WRITE": "1",
        }), patch("api.routers.questionnaire._qp.merge_whole_document", return_value={
            "person_id": "narrator-test",
            "questionnaire": _DUMMY_BLOB,
            "source": "ui_save", "version": 1, "updated_at": "x",
        }) as mock_upsert, patch(
            "api.services.bio_questionnaire_writer.apply_questionnaire_writes",
            return_value={
                "bio_facts_written": 3,
                "bio_facts_errors": [], "profile_error": None,
                "profile_patch": {"personal": {}},
            },
        ) as mock_apply:
            resp = qroute.put_questionnaire_route(_fresh_payload())
        self.assertEqual(mock_upsert.call_count, 1)
        self.assertEqual(mock_apply.call_count, 1)
        self.assertEqual(resp.bio_facts_written, 3)
        self.assertTrue(resp.legacy_blob_written)


class FanoutOnLegacyOff(unittest.TestCase):
    """Canonical-only — legacy blob skipped."""

    def test_fanout_on_legacy_off(self):
        from api.routers import questionnaire as qroute
        with patch.dict(os.environ, {
            "HORNELORE_QUESTIONNAIRE_BIO_FACTS_WRITE": "1",
            "HORNELORE_QUESTIONNAIRE_LEGACY_BLOB_WRITE": "0",
        }), patch("api.routers.questionnaire._qp.merge_whole_document") as mock_upsert, patch(
            "api.services.bio_questionnaire_writer.apply_questionnaire_writes",
            return_value={
                "bio_facts_written": 5, "bio_facts_errors": [],
                "profile_error": None, "profile_patch": {},
            },
        ) as mock_apply:
            resp = qroute.put_questionnaire_route(_fresh_payload())
        # Legacy blob NOT written
        self.assertEqual(mock_upsert.call_count, 0)
        # Fan-out fired
        self.assertEqual(mock_apply.call_count, 1)
        self.assertEqual(resp.bio_facts_written, 5)
        self.assertFalse(resp.legacy_blob_written)


class FanoutFailureFallback(unittest.TestCase):
    """When apply_questionnaire_writes raises, legacy blob write still
    runs + the error appears in the response. PUT must NOT 500."""

    def test_fanout_error_does_not_break_legacy_path(self):
        from api.routers import questionnaire as qroute
        with patch.dict(os.environ, {
            "HORNELORE_QUESTIONNAIRE_BIO_FACTS_WRITE": "1",
            "HORNELORE_QUESTIONNAIRE_LEGACY_BLOB_WRITE": "1",
        }), patch("api.routers.questionnaire._qp.merge_whole_document", return_value={
            "person_id": "narrator-test",
            "questionnaire": _DUMMY_BLOB,
            "source": "ui_save", "version": 1, "updated_at": "x",
        }) as mock_upsert, patch(
            "api.services.bio_questionnaire_writer.apply_questionnaire_writes",
            side_effect=Exception("boom"),
        ) as mock_apply:
            resp = qroute.put_questionnaire_route(_fresh_payload())
        # Legacy blob still wrote
        self.assertEqual(mock_upsert.call_count, 1)
        self.assertTrue(resp.legacy_blob_written)
        # Fan-out error surfaced
        self.assertEqual(len(resp.bio_facts_errors), 1)
        self.assertIn("boom", resp.bio_facts_errors[0]["error"])
        self.assertEqual(resp.bio_facts_errors[0]["stage"],
                         "apply_questionnaire_writes")


class BioFactsErrorsPropagated(unittest.TestCase):
    """External-review fix (2026-06-16): res['bio_facts_errors'] from
    the writer must surface in the PUT response. Previously the route
    only copied bio_facts_written + profile_error, leaving partial
    field-level write failures invisible to the operator UI."""

    def test_writer_errors_appear_in_response(self):
        from api.routers import questionnaire as qroute
        from api.routers.questionnaire import QuestionnairePutRequest
        with patch.dict(os.environ, {
            "HORNELORE_QUESTIONNAIRE_BIO_FACTS_WRITE": "1",
            "HORNELORE_QUESTIONNAIRE_LEGACY_BLOB_WRITE": "1",
        }), patch("api.routers.questionnaire._qp.merge_whole_document", return_value={
            "person_id": "n", "questionnaire": _DUMMY_BLOB,
            "source": "ui_save", "version": 1, "updated_at": "x",
        }), patch(
            "api.services.bio_questionnaire_writer.apply_questionnaire_writes",
            return_value={
                "bio_facts_written": 2,
                # Writer collected three per-field errors. The route
                # MUST surface these to the response — previously they
                # were silently dropped because the route only copied
                # bio_facts_written + profile_error.
                "bio_facts_errors": [
                    {"field_key": "primary_career", "error": "schema mismatch"},
                    {"field_key": "father_name",   "error": "value too long"},
                    {"field_key": "spouse_name",   "error": "DB lock"},
                ],
                "profile_error": None, "profile_patch": {},
            },
        ):
            payload = QuestionnairePutRequest(
                person_id="n", questionnaire=_DUMMY_BLOB,
            )
            resp = qroute.put_questionnaire_route(payload)
        self.assertEqual(len(resp.bio_facts_errors), 3)
        keys = [e["field_key"] for e in resp.bio_facts_errors]
        for k in ("primary_career", "father_name", "spouse_name"):
            self.assertIn(k, keys)


class DualFlagsDisabledRejected(unittest.TestCase):
    """Code-review issue #3: PUT must refuse when both write paths are
    off. Otherwise the operator UI shows 'saved' and the data drops."""

    def test_both_flags_off_returns_409(self):
        from fastapi import HTTPException
        from api.routers import questionnaire as qroute
        with patch.dict(os.environ, {
            "HORNELORE_QUESTIONNAIRE_BIO_FACTS_WRITE": "0",
            "HORNELORE_QUESTIONNAIRE_LEGACY_BLOB_WRITE": "0",
        }):
            with self.assertRaises(HTTPException) as cm:
                qroute.put_questionnaire_route(_fresh_payload())
        self.assertEqual(cm.exception.status_code, 409)
        self.assertIn("misconfigured", str(cm.exception.detail).lower())


class BlankNarratorIdRejected(unittest.TestCase):
    def test_blank_narrator_id_400(self):
        from fastapi import HTTPException
        from api.routers import questionnaire as qroute
        from api.routers.questionnaire import QuestionnairePutRequest
        payload = QuestionnairePutRequest(
            person_id="   ", questionnaire={},
        )
        with self.assertRaises(HTTPException) as cm:
            qroute.put_questionnaire_route(payload)
        self.assertEqual(cm.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
