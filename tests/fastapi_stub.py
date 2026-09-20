"""Minimal fastapi + pydantic stand-ins, for route tests in a sandbox
with no PyPI access.

WHY A SHARED MODULE RATHER THAN A COPY PER TEST
-----------------------------------------------
`test_questionnaire_route_fanout.py` carries its own inline copy of this
block. Two stubs for one framework is the same hazard as two
"is there anything here" walks or two duplicate detectors: they drift,
and the drift shows up as a test that passes against behaviour the real
framework would not produce. That has cost real time on this project
already.

This module is the one place to fix a fidelity gap. The inline copy in
the fanout test is left alone for now because that suite is green and
migrating it is a change with no benefit to the work in hand — recorded
here so the duplication is deliberate and visible rather than forgotten.

WHAT THIS IS NOT. It validates nothing. Real pydantic coerces types,
rejects unknown fields depending on config, and enforces annotations;
this accepts whatever it is handed. So a test using it can prove what a
route DOES with well-formed input and can never prove what the framework
rejects. Anything that turns on validation needs the real stack.
"""

from __future__ import annotations

import sys
import types


def install() -> None:
    """Idempotent. Registers the stubs only if the real thing is absent."""

    if "fastapi" not in sys.modules:
        fa = types.ModuleType("fastapi")

        class _APIRouter:
            def __init__(self, *a, **kw):
                pass

            def _deco(self, *a, **kw):
                def deco(fn):
                    return fn
                return deco

            get = patch = put = post = delete = _deco

        class _HTTPException(Exception):
            def __init__(self, status_code=500, detail=""):
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail

        def _Query(default=None, **_kw):
            return default

        class _Response:
            def __init__(self, *a, **kw):
                self.status_code = 200

        fa.APIRouter = _APIRouter
        fa.HTTPException = _HTTPException
        fa.Query = _Query
        fa.Response = _Response
        sys.modules["fastapi"] = fa

    if "pydantic" not in sys.modules:
        pd = types.ModuleType("pydantic")

        class _BaseModel:
            def __init__(self, **kw):
                for k, v in kw.items():
                    setattr(self, k, v)
                # Class-level defaults for anything the caller omitted;
                # routes read several of them directly.
                for klass in reversed(type(self).__mro__):
                    for k, v in vars(klass).items():
                        if k.startswith("_") or callable(v) or isinstance(v, (classmethod, staticmethod, property)):
                            continue
                        if k not in self.__dict__:
                            setattr(self, k, v)
                # Annotated-but-undefaulted fields still have to exist,
                # or a route reading one gets AttributeError where the
                # real framework would have required it at construction.
                for k in self.__class__._field_names():
                    if k not in self.__dict__:
                        setattr(self, k, None)

            @classmethod
            def _field_names(cls):
                out = []
                for klass in reversed(cls.__mro__):
                    for k in getattr(klass, "__annotations__", {}):
                        if not k.startswith("_") and k not in out:
                            out.append(k)
                return out

            class _Fields(dict):
                pass

            @classmethod
            def _model_fields(cls):
                # Enough of pydantic's `model_fields` for a test to ask
                # "does this request model have a field called X" —
                # which is how a route proves a client CANNOT supply
                # something the server is supposed to decide.
                return _BaseModel._Fields({k: None for k in cls._field_names()})

            class Config:
                populate_by_name = True

            def model_dump(self):
                return {k: v for k, v in self.__dict__.items()
                        if not k.startswith("_")}

        class _Meta(type):
            @property
            def model_fields(cls):
                return cls._model_fields()

        # Rebuild with the metaclass so `Model.model_fields` works as a
        # class attribute, the way real pydantic exposes it.
        _BaseModel = _Meta("BaseModel", (_BaseModel,), {})

        def _Field(default=None, default_factory=None, **_kw):
            if default_factory is not None:
                return default_factory()
            return default

        pd.BaseModel = _BaseModel
        pd.Field = _Field
        sys.modules["pydantic"] = pd
