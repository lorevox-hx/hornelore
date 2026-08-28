"""`expected_version` is an integer, and nothing else is converted into one.

WO-LORI-PROFILE-SEED-REACHABILITY-01 — pre-Step-6 correction checkpoint,
2026-08-27.

── HOW TO RUN THIS ───────────────────────────────────────────────────

    PYTHONPATH=server/code python3 -m unittest \\
        tests.test_profile_seed_expected_version_strict

The accessor tests run everywhere. The ROUTE tests need the real route
stack — **`pydantic` AND `fastapi`** — and are skipped, with the reason
named, where a dependency is genuinely absent.

    generic interpreter, no fastapi   ->  green, 5 explicit route skips
    `.venv-gpu` (the serving venv)    ->  22/22 green, ZERO skips

*(Corrected 2026-08-28. This guard checked `pydantic` alone while the
paragraph above it promised skips for unavailable route dependencies.
Measured on an ordinary interpreter with pydantic present and fastapi
absent: 13 tests ran and EIGHT ERRORED with `ModuleNotFoundError: No
module named 'fastapi'`, and `run_mutation_gate.py --only P11` then
refused its red baseline. `api.routers.interview` imports fastapi one
line above pydantic; a guard naming one of the two was covering for the
other with prose.)*

── THE DEFECT, REPRODUCED BEFORE IT WAS CLOSED ───────────────────────

Phase 1 says the onboarding version is an integer and that a PATCH must
carry the exact version the caller read. Two layers disagreed:

  * `ProfileSeedPatchRequest.expected_version: int` — Pydantic COERCES,
    so `{"expected_version": true}` arrived as `1`;
  * `db.profile_seed_apply()` — `expected = int(expected_version)`,
    which is a converter wearing a validator's clothes. `int()` accepts
    `True`, `"1"`, `1.0` and anything with `__int__`.

Measured against a temporary database: **a narrator at version 1
accepted `expected_version=True` and advanced to version 2.**

That is not a typing nicety. `expected_version` exists to answer one
question — "is the state you decided against still the state I have?" —
and it answers it by EQUALITY. `True == 1` is true in Python, so a
caller that sent a Boolean got a match it had not earned. `1.0` matches
by the same accident, and `int(1.9)` is `1`, so a client with an
arithmetic bug would silently address a version it never read.

── THE TWO LAYERS ARE BOTH REQUIRED, AND THIS IS NOT BELT-AND-BRACES ──

The request model cannot be the only check: `db.profile_seed_apply` has
callers that never pass through it — every test in this repository, and
the Step 6 WebSocket path, which will call the accessor directly. A rule
that lives only in a request model does not exist for them.

The accessor cannot be the only check either. Refusing at the accessor
produces a `ValueError`, and the route's job is to turn a malformed
request into a 422 the client can read.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from typing import Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
for _p in (str(_SERVER_CODE), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api import db as _db  # noqa: E402
from api.services import profile_seed as _ps  # noqa: E402

#: Every value that `int()` would have accepted and that is NOT an int.
#: `Decimal` is included because it is the ordinary way a JSON number
#: reaches Python through a financial or spreadsheet client, and it has
#: `__int__` — so it would have passed the old check silently.
try:
    from decimal import Decimal
    _DECIMAL_ONE = Decimal("1")
except Exception:  # pragma: no cover
    _DECIMAL_ONE = None


class _StrictBase(unittest.TestCase):
    """One temp DATA_DIR and one temp database per test.

    Mirrors `tests/test_profile_seed_server_authority._Base`, including
    the `_BIO_SEED_LOADED` reset — a once-per-process gate that leaves
    `bio_fields` empty for the second suite to switch `DB_PATH`, after
    which evidence writes fail with a foreign-key error that reads like
    a missing person row and is not.
    """

    def setUp(self):
        self.data_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.data_tmp.cleanup)
        self._orig_data_dir = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = str(Path(self.data_tmp.name).resolve())
        self.addCleanup(self._restore_data_dir)

        fd = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        fd.close()
        self.db_path = Path(fd.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db._BIO_SEED_LOADED = False
        _db.init_db()
        self.addCleanup(self._restore_db)

    def _restore_data_dir(self):
        if self._orig_data_dir is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self._orig_data_dir

    def _restore_db(self):
        _db.DB_PATH = self._orig_db
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def _new_person(self, name="Verlie Ostrander", *, anchors=False):
        """A narrator AT VERSION 1 by default, and that is load-bearing.

        `create_person` with a DOB and a birthplace supplies two pieces
        of evidence, `reconcile` materializes them, and the narrator is
        at version 2 before any test touches them. That is a fine
        fixture for most things and a BAD one here: `int(True)` is `1`,
        so at version 2 a Boolean would fail the version comparison and
        come back as a `VersionConflict` — the refusal test would pass
        for the wrong reason, and the mutation that removes the type
        check would still look caught.

        At version 1 the coerced value MATCHES. So a missing type check
        does not conflict; it succeeds, moves the narrator to version 2,
        and every test below fails by assertion. This is the exact
        fixture the 2026-08-27 review used to reproduce the defect: "a
        pending narrator at version 1 accepted expected_version=True and
        moved to version 2".
        """
        return _db.create_person(
            name,
            date_of_birth="1936-11-08" if anchors else "",
            place_of_birth="Devils Lake, North Dakota" if anchors else "",
            narrator_type="live",
        )["id"]

    def assertRefusedAsTypeError(self, person_id, value, action="pause"):
        """The refusal must be a TYPE refusal, not a version conflict.

        Written as an explicit try/except rather than `assertRaises`
        because the two failure modes have to be told apart, and
        `assertRaises` cannot: a `VersionConflict` escaping it is an
        ERROR, and an error says the test never reached the behaviour it
        was measuring. Here every wrong outcome is an assertion.
        """
        before = self._version(person_id)
        try:
            _db.profile_seed_apply(person_id, expected_version=value,
                                   action=action)
        except ValueError:
            self.assertEqual(
                self._version(person_id), before,
                f"{value!r} was refused but something was still written")
            return
        except _ps.ProfileSeedError as exc:
            self.fail(
                f"{value!r} reached the version COMPARISON and came back as "
                f"{type(exc).__name__}. A non-integer must be refused as a "
                "contract violation before any comparison — a value that had "
                "to be converted was not the value the caller read.")
        self.fail(
            f"{value!r} was ACCEPTED. It is now version "
            f"{self._version(person_id)} (was {before}).")

    def _stored_version(self, person_id):
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT version FROM profile_seed_onboarding WHERE person_id=?;",
            (person_id,)).fetchone()
        con.close()
        return None if row is None else row["version"]

    def _version(self, person_id):
        """The EFFECTIVE version, which is the one `expected_version` is
        compared against.

        Not the stored column. `profile_seed_apply` reconciles BEFORE it
        compares (Phase 1, step 2 of its contract), so evidence that
        arrived since the last write — for an ordinary intake narrator,
        the DOB and birthplace supplied at creation — moves the version
        during the call. A test reading the raw column would be asserting
        against a number the accessor never compares.
        """
        state = _db.profile_seed_resolve(person_id)
        return None if state is None else state["version"]


class AccessorStrictnessTests(_StrictBase):
    """`db.profile_seed_apply` refuses, and refuses BEFORE writing."""

    def test_the_reported_defect_no_longer_reproduces(self):
        """The exact sequence from the 2026-08-27 review.

        A narrator at version 1, `expected_version=True`, `pause` — which
        needs no topic and so isolates the version check from every other
        guard. Before the correction this returned a new state at version
        2. It must now refuse, and the stored version must not move.
        """
        pid = self._new_person()
        before = self._version(pid)
        self.assertEqual(
            before, 1,
            "fixture assumption broken: this reproduction needs a narrator "
            "at version 1, where int(True) would MATCH")
        self.assertEqual(_db.profile_seed_resolve(pid)["status"],
                         _ps.STATUS_PENDING)

        self.assertRefusedAsTypeError(pid, True)

        self.assertEqual(
            self._version(pid), 1,
            "a Boolean expected_version advanced the version — the exact "
            "defect this test exists to close")
        self.assertEqual(
            _db.profile_seed_resolve(pid)["status"], _ps.STATUS_PENDING,
            "a Boolean expected_version paused the narrator")

    def test_the_refusal_names_the_field(self):
        pid = self._new_person()
        try:
            _db.profile_seed_apply(pid, expected_version=True, action="pause")
        except ValueError as exc:
            self.assertIn("expected_version", str(exc))
            self.assertIn("bool", str(exc))
            return
        except _ps.ProfileSeedError as exc:
            self.fail(f"refused as {type(exc).__name__}, not as a type error")
        self.fail("a Boolean expected_version was accepted")

    def test_False_is_refused_too(self):
        """`False` is `0`, which no version can equal, so this one would
        have failed with a conflict rather than a false match. It is
        still refused HERE, at the type, because a client sending
        Booleans has a bug the version comparison cannot describe — and
        `assertRefusedAsTypeError` fails rather than errors when it comes
        back as a conflict, which is exactly this case."""
        pid = self._new_person()
        self.assertRefusedAsTypeError(pid, False)

    def test_floats_strings_and_other_convertibles_are_refused(self):
        """Every value `int()` would have accepted, at a version where
        the conversion would have MATCHED.

        `"one"`, `None`, `[1]` and `{"v": 1}` are here for completeness:
        `int()` refused those too, so they are the cases the old code
        got right. The first four are the cases it got wrong.
        """
        pid = self._new_person()
        self.assertEqual(self._version(pid), 1)
        rejected = [1.0, 1.9, "1", " 1 ", "one", None, [1], {"v": 1}]
        if _DECIMAL_ONE is not None:
            rejected.append(_DECIMAL_ONE)
        for value in rejected:
            with self.subTest(value=repr(value)):
                self.assertRefusedAsTypeError(pid, value)

    def test_a_REAL_int_still_works(self):
        """The guard must not be vacuous. If this test can be deleted
        without the others failing, the accessor is simply broken.

        Run against an ANCHORED narrator too, so the positive control
        covers a version the fixture did not choose."""
        for anchors in (False, True):
            with self.subTest(anchors=anchors):
                pid = self._new_person(f"Positive {anchors}", anchors=anchors)
                before = self._version(pid)
                state = _db.profile_seed_apply(pid, expected_version=before,
                                               action="pause")
                self.assertGreater(
                    self._version(pid), before,
                    "a correctly typed expected_version wrote nothing")
                if anchors:
                    # Only an ACTIVE walk can be paused. A pending
                    # narrator has no anchors yet, so the pause is
                    # recorded and the status stays `pending` — which is
                    # Phase 1 behaviour and not this test's subject.
                    self.assertEqual(state["status"], _ps.STATUS_PAUSED)

    def test_a_WRONG_int_still_conflicts_rather_than_being_refused(self):
        """Range is not a type error, and the distinction matters.

        `0` and `-5` are well-typed claims that are simply wrong. They
        must reach the version comparison and come back as
        `VersionConflict` CARRYING THE FRESH STATE — which tells the
        client what the version actually is. A 422 would tell them less.
        """
        pid = self._new_person()
        before = self._version(pid)
        for wrong in (0, -5, before + 97):
            with self.subTest(expected_version=wrong):
                with self.assertRaises(_ps.VersionConflict):
                    _db.profile_seed_apply(pid, expected_version=wrong,
                                           action="pause")
                self.assertEqual(self._version(pid), before)

    def test_the_refusal_happens_before_any_lock_is_taken(self):
        """A malformed version is a client bug, not a concurrency event.

        Proved by refusing for a person who does not exist at all: if the
        type check ran after the person lookup, this would raise
        `PersonNotFound` instead.
        """
        ghost = str(uuid.uuid4())
        try:
            _db.profile_seed_apply(ghost, expected_version=True,
                                   action="pause")
        except ValueError:
            return
        except _ps.ProfileSeedError as exc:
            self.fail(
                f"refused as {type(exc).__name__} — the type check now runs "
                "after the person lookup, so a malformed version takes a "
                "write lock before it is refused")
        self.fail("a Boolean expected_version was accepted for a ghost id")

    def test_the_message_names_the_field_and_the_type_it_got(self):
        """An error a client can act on without reading this source."""
        pid = self._new_person()
        try:
            _db.profile_seed_apply(pid, expected_version="1", action="pause")
        except ValueError as exc:
            self.assertIn("expected_version", str(exc))
            self.assertIn("str", str(exc))
            return
        except _ps.ProfileSeedError as exc:
            self.fail(f"refused as {type(exc).__name__}, not as a type error")
        self.fail("a numeric string expected_version was accepted")


# ── THE ROUTE STACK IS pydantic AND fastapi, 2026-08-28 ───────────────
#
# *(This checked `pydantic` ALONE and asserted in its own docstring that
# unavailable route dependencies would produce skips. That was false and
# measured false: on an ordinary interpreter with pydantic installed and
# fastapi absent, the suite ran 13 tests and produced EIGHT ERRORS —
# `ModuleNotFoundError: No module named 'fastapi'`, raised inside
# `_model()` — and `run_mutation_gate.py --only P11` then refused its
# red baseline, which is the gate working correctly against a broken
# instrument.*
#
# *`api.routers.interview` imports `fastapi` at line 7 and `pydantic` at
# line 8. A guard that names one of the two is not a guard on the route
# stack; it is a guard on half of it, with a docstring covering for the
# other half.)*
#
# THE DEPENDENCY LIST IS EXPLICIT, and that is the second half of the
# correction. "Skip when the router will not import" is the wrong rule:
# it converts a REAL defect — a syntax error in the router, a bad
# relative import, a circular import introduced by Step 6 — into a
# silent skip, and this file would then report OK while measuring
# nothing. Only a ModuleNotFoundError naming one of the modules below is
# a skip. Every other import failure propagates and is a collection
# ERROR, loudly.
_ROUTE_DEPENDENCIES: Tuple[str, ...] = ("pydantic", "fastapi")


def _dependency_unavailable(name: str) -> Optional[str]:
    """Import ONE route dependency. Missing -> a reason; else it RAISES.

    ── THE SWEEP WAS STILL BROAD, 2026-08-28 ──────────────────────────

    *(The router-import step below was narrowed to `ModuleNotFoundError`
    and the sweep above it was left catching bare `ImportError` — the
    same defect the narrowing was for, one call earlier. Reproduced with
    a circular-import-style fastapi failure:*

        RESULT RETURNED: fastapi is not installed
        (cannot import name 'X' from partially initialized module 'fastapi')

    *A partially initialized module is INSTALLED. Reporting it as absent
    turns a real defect — the likeliest being a circular import
    introduced by Step 6 — into a skip, and the suite then reports `OK`
    having measured nothing.)*

    Two conditions, both required, before this is called a skip:

      1. the failure is a `ModuleNotFoundError`, not any other
         `ImportError` — `ModuleNotFoundError` is a SUBCLASS, so
         catching the parent catches circular imports too;
      2. **the module that is missing IS the one being imported.**
         `import fastapi` failing because `starlette` is absent is a
         BROKEN INSTALL, not an absent dependency, and it is not this
         suite's business to paper over it.
    """
    import importlib
    try:
        module = importlib.import_module(name)
    except ModuleNotFoundError as exc:
        missing = (exc.name or "").split(".")[0]
        if missing == name:
            return f"{name} is not installed ({exc})"
        raise
    if getattr(module, "__file__", None) is None:
        return f"the offline {name} stub is installed, and it validates nothing"
    return None


def _router_import_unavailable() -> Optional[str]:
    """Import the router. Missing dependency -> a reason; else it RAISES.

    Separated from the dependency sweep below so it is DIRECTLY
    testable. Folded into one function it was unreachable on the very
    interpreter whose behaviour matters most — the one without fastapi
    returns at the sweep and never reaches this import, so a test of
    this rule could not observe it there.
    """
    import importlib
    try:
        importlib.import_module("api.routers.interview")
    except ModuleNotFoundError as exc:
        missing = (exc.name or "").split(".")[0]
        if missing in _ROUTE_DEPENDENCIES:
            return f"route dependency {missing!r} is not installed ({exc})"
        raise
    return None


def _route_stack_unavailable() -> Optional[str]:
    """`None` when the route tests can run, else WHY they cannot.

    Three distinct unavailabilities, each reported rather than swallowed:

      * a dependency is genuinely not installed;
      * a dependency is present as one of the OFFLINE STUBS that ~30
        modules under `tests/` install. The pydantic stub's `BaseModel`
        is `class _BaseModel: pass` — it validates nothing, so a
        "passing" strictness test against it would be measuring a class
        that accepts everything. That is worse than a skip, because it
        reports OK;
      * the router itself cannot be imported FOR A MISSING DEPENDENCY —
        the same environment fact, reached one import deeper.

    Anything else raises. See `_router_import_unavailable`.
    """
    for name in _ROUTE_DEPENDENCIES:
        reason = _dependency_unavailable(name)
        if reason is not None:
            return reason

    import pydantic
    if not hasattr(pydantic, "StrictInt"):
        return "pydantic has no StrictInt"

    return _router_import_unavailable()


_ROUTE_SKIP_REASON = _route_stack_unavailable()


class RouteGuardTests(unittest.TestCase):
    """The guard itself, on every interpreter — INCLUDING the ones that
    skip the route tests.

    A skip guard is the one piece of a suite that nothing else checks:
    when it is wrong in the permissive direction the suite errors, and
    when it is wrong in the other direction the suite reports OK having
    measured nothing. Both were live here.
    """

    def test_the_reason_is_None_or_NAMES_a_dependency(self):
        """A skip must say which dependency, not merely that it skipped."""
        if _ROUTE_SKIP_REASON is None:
            return
        self.assertTrue(
            any(dep in _ROUTE_SKIP_REASON for dep in _ROUTE_DEPENDENCIES),
            f"the route tests skip for a reason that names no dependency: "
            f"{_ROUTE_SKIP_REASON!r}")

    def test_fastapi_is_part_of_the_route_stack(self):
        """The defect, as a named test.

        `api.routers.interview` imports fastapi at line 7. A guard that
        omits it lets the suite ERROR where it promised to skip.
        """
        self.assertIn("fastapi", _ROUTE_DEPENDENCIES)
        self.assertIn("pydantic", _ROUTE_DEPENDENCIES)
        source = (_SERVER_CODE / "api" / "routers"
                  / "interview.py").read_text(encoding="utf-8")
        for dep in _ROUTE_DEPENDENCIES:
            with self.subTest(dep=dep):
                self.assertIn(f"from {dep} import", source)

    def test_a_NON_dependency_import_failure_is_NOT_swallowed(self):
        """"The router would not import" must never be a blanket skip.

        A syntax error in the router, a bad relative import, or a
        circular import introduced by Step 6 are DEFECTS. If those
        skipped, this file would report OK while measuring nothing —
        which is the failure mode the whole checkpoint is about.
        """
        import importlib
        real = importlib.import_module

        def fake(name, *a, **k):
            if name == "api.routers.interview":
                raise ModuleNotFoundError("No module named 'not_a_dependency'",
                                          name="not_a_dependency")
            return real(name, *a, **k)

        importlib.import_module = fake
        try:
            with self.assertRaises(ModuleNotFoundError):
                _router_import_unavailable()
        finally:
            importlib.import_module = real

    def test_a_MISSING_DEPENDENCY_import_failure_IS_a_skip(self):
        """The other half, so the guard is not merely strict."""
        import importlib
        real = importlib.import_module

        def fake(name, *a, **k):
            if name == "api.routers.interview":
                raise ModuleNotFoundError("No module named 'fastapi'",
                                          name="fastapi")
            return real(name, *a, **k)

        importlib.import_module = fake
        try:
            reason = _router_import_unavailable()
        finally:
            importlib.import_module = real
        self.assertIsNotNone(reason)
        self.assertIn("fastapi", reason)

    # ── Controls for the OUTER DEPENDENCY SWEEP ────────────────────────
    #
    # The router-import step was narrowed first and the sweep above it
    # was left catching bare `ImportError`, so the same defect survived
    # one call earlier and nothing tested that call at all. These four
    # drive `_dependency_unavailable` directly.

    def _patched_import(self, raiser):
        """Run `_dependency_unavailable('fastapi')` with a scripted import."""
        import importlib
        real = importlib.import_module

        def fake(name, *a, **k):
            if name == "fastapi":
                raise raiser
            return real(name, *a, **k)

        importlib.import_module = fake
        try:
            return _dependency_unavailable("fastapi")
        finally:
            importlib.import_module = real

    def test_the_sweep_reraises_an_ARBITRARY_ImportError(self):
        """A partially initialized module is INSTALLED.

        The reproduction that reopened this: a circular-import fastapi
        failure came back as `fastapi is not installed`. `ImportError`
        is the parent of `ModuleNotFoundError`, so catching the parent
        catches circular imports — the likeliest way Step 6 breaks this
        route — and calls them an environment fact.
        """
        with self.assertRaises(ImportError) as caught:
            self._patched_import(ImportError(
                "cannot import name 'X' from partially initialized module "
                "'fastapi' (most likely due to a circular import)"))
        self.assertIn("circular", str(caught.exception))

    def test_the_sweep_reraises_a_NESTED_missing_module(self):
        """`import fastapi` failing on a MISSING `starlette` is a broken
        install, not an absent dependency. The missing root must BE the
        module being imported, or this suite is covering for a
        half-installed environment it did not diagnose."""
        with self.assertRaises(ModuleNotFoundError):
            self._patched_import(ModuleNotFoundError(
                "No module named 'starlette'", name="starlette"))

    def test_the_sweep_treats_a_GENUINELY_ABSENT_dependency_as_a_skip(self):
        """The other half, so the guard is not merely strict."""
        reason = self._patched_import(ModuleNotFoundError(
            "No module named 'fastapi'", name="fastapi"))
        self.assertIsNotNone(reason)
        self.assertIn("fastapi", reason)
        self.assertIn("not installed", reason)

    def test_the_sweep_rejects_an_OFFLINE_STUB_as_unavailable(self):
        """A stub that validates nothing must not count as present.

        ~30 modules under `tests/` install one. A "passing" strictness
        test against `class _BaseModel: pass` would be measuring a class
        that accepts everything — worse than a skip, because it reports
        OK.
        """
        import importlib
        import types
        real = importlib.import_module
        stub = types.ModuleType("fastapi")   # no __file__

        def fake(name, *a, **k):
            return stub if name == "fastapi" else real(name, *a, **k)

        importlib.import_module = fake
        try:
            reason = _dependency_unavailable("fastapi")
        finally:
            importlib.import_module = real
        self.assertIsNotNone(reason)
        self.assertIn("stub", reason)

    def test_a_NON_ModuleNotFound_router_failure_is_NOT_swallowed(self):
        """A syntax error is not a missing dependency.

        `ModuleNotFoundError` is a subclass of `ImportError`; a broader
        `except ImportError` here would turn a circular import — the
        most likely way Step 6 breaks this router — into a silent skip.
        """
        import importlib
        real = importlib.import_module

        def fake(name, *a, **k):
            if name == "api.routers.interview":
                raise ImportError("cannot import name 'X' (circular)")
            return real(name, *a, **k)

        importlib.import_module = fake
        try:
            with self.assertRaises(ImportError):
                _router_import_unavailable()
        finally:
            importlib.import_module = real


@unittest.skipUnless(
    _ROUTE_SKIP_REASON is None,
    f"the route stack is unavailable: {_ROUTE_SKIP_REASON}")
class RouteStrictnessTests(unittest.TestCase):
    """The request model refuses the same three types the accessor does.

    SKIPPED ONLY for an explicitly named missing dependency. On any
    interpreter that has the real `fastapi` + `pydantic` route stack —
    `.venv-gpu` — these run, and the suite reports 22/22 with ZERO
    skips.
    """

    def _model(self):
        from api.routers.interview import ProfileSeedPatchRequest
        return ProfileSeedPatchRequest

    def test_the_field_carries_pydantic_STRICT_metadata(self):
        """Asserted on the DECLARATION as well as on behaviour.

        Behaviour alone would keep passing if someone replaced
        `StrictInt` with a hand-rolled validator that happened to agree
        today. `StrictInt` is `Annotated[int, Strict(strict=True)]`, so
        the annotation itself is a plain `int` and the strictness lives
        in the field metadata — which is what is checked here.
        """
        model = self._model()
        field = model.model_fields["expected_version"]
        self.assertIs(field.annotation, int)
        strict_markers = [m for m in (getattr(field, "metadata", None) or [])
                          if getattr(m, "strict", False) is True]
        self.assertTrue(
            strict_markers,
            "expected_version carries no pydantic Strict marker; it will "
            f"coerce. metadata={getattr(field, 'metadata', None)!r}")

    def test_the_source_declares_StrictInt_by_name(self):
        """The metadata check above proves the effect. This proves the
        SPELLING, so a reader of the router sees the contract without
        having to introspect a model — and so that a future edit to
        `int` is caught by a test that names what it wants."""
        source = (_SERVER_CODE / "api" / "routers" / "interview.py").read_text(
            encoding="utf-8")
        self.assertIn("expected_version: StrictInt", source)
        self.assertNotIn("expected_version: int", source)

    def test_true_is_refused_by_the_request_model(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            self._model()(person_id="p1", expected_version=True,
                          action="pause")

    def test_floats_and_numeric_strings_are_refused(self):
        from pydantic import ValidationError
        for value in (1.0, 1.9, "1", "one", None):
            with self.subTest(value=repr(value)):
                with self.assertRaises(ValidationError):
                    self._model()(person_id="p1", expected_version=value,
                                  action="pause")

    def test_a_real_int_is_accepted_and_kept_as_an_int(self):
        model = self._model()(person_id="p1", expected_version=7,
                              action="pause")
        self.assertEqual(model.expected_version, 7)
        self.assertIsInstance(model.expected_version, int)
        self.assertNotIsInstance(model.expected_version, bool)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
