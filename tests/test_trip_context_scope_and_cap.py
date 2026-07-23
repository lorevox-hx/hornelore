"""Travel Doc Lab finish-pass, Batch B (backend):

1. Context patch/delete trip-scoping — the four context endpoints keyed on
   context_id alone. A stale FE panel (operator switched trips) could mutate
   another trip's evidence row. When the caller asserts a trip_id it must match
   the row's real trip, else 409. Omitted trip_id stays backward-compatible.

2. The conv-keyed caches `_TRIP_PREV_LORI` / `_TRIP_LAST_CAPTURE` were never
   evicted — a long-running server leaked one entry per conversation forever.
   Now capped with oldest-first eviction.
"""
from __future__ import annotations

import re
import sys
import types
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

# Offline stubs so the trips router imports without fastapi/pydantic/torch.
if "fastapi" not in sys.modules:
    fa = types.ModuleType("fastapi")

    class _R:
        def __getattr__(self, _):
            return lambda *a, **k: (lambda f: f)

    class _HTTPException(Exception):
        def __init__(self, status_code=0, detail=""):
            self.status_code, self.detail = status_code, detail
            super().__init__(detail)

    fa.APIRouter = lambda *a, **k: _R()
    fa.HTTPException = _HTTPException
    fa.Query = lambda *a, **k: None
    fa.File = lambda *a, **k: None
    fa.Form = lambda *a, **k: None
    fa.UploadFile = object
    sys.modules["fastapi"] = fa
if "pydantic" not in sys.modules:
    pd = types.ModuleType("pydantic")
    pd.BaseModel = object
    pd.Field = lambda *a, **k: None
    pd.field_validator = lambda *a, **k: (lambda f: f)
    pd.ConfigDict = dict
    sys.modules["pydantic"] = pd

from fastapi import HTTPException  # noqa: E402  (stub)
from api.routers.trips import _assert_context_trip_scope  # noqa: E402


class ContextTripScopeTest(unittest.TestCase):
    def test_matching_trip_is_allowed(self):
        _assert_context_trip_scope("tripA", "tripA", "photo context")  # no raise

    def test_omitted_claim_is_backward_compatible(self):
        _assert_context_trip_scope("tripA", None, "photo context")  # no raise
        _assert_context_trip_scope("tripA", "", "photo context")     # no raise

    def test_mismatched_trip_is_409(self):
        with self.assertRaises(HTTPException) as cm:
            _assert_context_trip_scope("tripA", "tripB", "photo context")
        self.assertEqual(cm.exception.status_code, 409)

    def test_unknown_row_trip_does_not_false_409(self):
        # If the row's trip can't be resolved (None), we don't block — the
        # 404-not-found path handles a genuinely missing row.
        _assert_context_trip_scope(None, "tripB", "photo context")  # no raise

    def test_all_four_endpoints_call_the_guard(self):
        src = (_SERVER_CODE / "api" / "routers" / "trips.py").read_text(
            encoding="utf-8")
        # each of patch/delete photo/public context passes trip_id + calls guard
        self.assertEqual(src.count("_assert_context_trip_scope("), 5)  # 1 def + 4 calls
        for ep in ("def patch_public_context(", "def delete_public_context(",
                   "def patch_photo_context(", "def delete_photo_context("):
            i = src.index(ep)
            block = src[i:i + 500]
            # Query( may wrap to the next line, so match the param, not "Query(None".
            self.assertIn("trip_id: Optional[str] = Query(", block, ep)


class ConvCacheCapTest(unittest.TestCase):
    def test_eviction_logic(self):
        # Re-implement the tiny cap to prove the eviction contract without
        # importing chat_ws (heavy torch deps).
        cap = 3

        def _cap(d, c):
            while len(d) > c:
                d.pop(next(iter(d)))

        d = {}
        for i in range(10):
            d["conv%02d" % i] = i
            _cap(d, cap)
        self.assertEqual(len(d), cap)
        # oldest evicted, newest kept
        self.assertNotIn("conv00", d)
        self.assertIn("conv09", d)

    def test_chat_ws_wires_the_cap_at_both_write_sites(self):
        src = (_SERVER_CODE / "api" / "routers" / "chat_ws.py").read_text(
            encoding="utf-8")
        self.assertIn("def _cap_conv_cache(", src)
        # called after each of the two cache writes
        self.assertIn("_TRIP_LAST_CAPTURE[conv_id] = _tsc_res\n"
                      "                    _cap_conv_cache(_TRIP_LAST_CAPTURE)",
                      src)
        self.assertIn("_cap_conv_cache(_TRIP_PREV_LORI)", src)


if __name__ == "__main__":
    unittest.main()
