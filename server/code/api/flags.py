"""WO-13 shared feature-flag helper.

One place to ask "is truth-v2 on for {consumer}?" so every router
reads the same env vars. Kept intentionally tiny.

Consumers:
  - 'facts_write'  → HORNELORE_TRUTH_V2
        Phase 4 legacy /api/facts/add write freeze. When on, the
        legacy write endpoint returns 410 Gone.
  - 'profile'      → HORNELORE_TRUTH_V2_PROFILE
        Phase 8 read seam. When on, GET /api/profiles/{id} returns
        a profile assembled from family_truth_promoted instead of
        the raw profiles.profile_json blob.

Default for every consumer is OFF.
"""

from __future__ import annotations

import os
from typing import Final

_TRUTHY: Final = ("1", "true", "yes", "on")


def _truthy(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in _TRUTHY


def truth_v2_enabled(consumer: str) -> bool:
    """Return True when the truth-v2 path is enabled for ``consumer``.

    Unknown consumers return False so adding a call site in advance of
    wiring its env var is safe.
    """
    if consumer == "facts_write":
        return _truthy(os.environ.get("HORNELORE_TRUTH_V2"))
    if consumer == "profile":
        return _truthy(os.environ.get("HORNELORE_TRUTH_V2_PROFILE"))
    return False
