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

WO-LIFE-SPINE-05 / WO-EX-VALIDATE-01 additions:
  - age_validator_enabled()         → HORNELORE_AGE_VALIDATOR
        Runtime age-math plausibility gate in /api/extract-fields.
        When on, extractor annotates items with plausibility_flag and
        drops items marked 'impossible'. Default OFF for pre-test safety.
  - phase_aware_questions_enabled() → HORNELORE_PHASE_AWARE_QUESTIONS
        Interview router uses data/prompts/question_bank.json to pick
        phase-appropriate questions instead of strict sequential DB
        ordering. Default OFF so tomorrow's test sees unchanged flow.
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


def age_validator_enabled() -> bool:
    """WO-EX-VALIDATE-01. When True, /api/extract-fields runs each item
    through life_spine.validator.validate_fact() and drops any item
    flagged 'impossible'. Default OFF."""
    return _truthy(os.environ.get("HORNELORE_AGE_VALIDATOR"))


def phase_aware_questions_enabled() -> bool:
    """WO-LIFE-SPINE-05. When True, interview router uses the phase-aware
    composer (question_bank.json) to pick the next question when a
    narrator DOB is available. Falls back to sequential DB ordering when
    composer returns None. Default OFF."""
    return _truthy(os.environ.get("HORNELORE_PHASE_AWARE_QUESTIONS"))


def claims_validators_enabled() -> bool:
    """WO-EX-CLAIMS-02. When True, /api/extract-fields runs three
    post-extraction validators: value-shape rejection, relation allowlist,
    and confidence floor. Default ON — these are safe guardrails that only
    drop clearly-bad items."""
    return _truthy(os.environ.get("HORNELORE_CLAIMS_VALIDATORS", "1"))
