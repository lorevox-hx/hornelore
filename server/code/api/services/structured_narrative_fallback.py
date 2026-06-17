"""Boris Phase 7 contract shim.

Re-exports `extract_safe_anchors` and `build_structured_narrative_fallback`
from the canonical `lori_structured_narrative_fallback` module so any of
the contract paths the test suite probes resolve. The implementation lives
in the lori_-prefixed module; both names point at the same code.
"""
from __future__ import annotations

from .lori_structured_narrative_fallback import (  # noqa: F401
    extract_safe_anchors,
    build_structured_narrative_fallback,
)

__all__ = [
    "extract_safe_anchors",
    "build_structured_narrative_fallback",
]
