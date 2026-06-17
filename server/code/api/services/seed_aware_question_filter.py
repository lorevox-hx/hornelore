"""Seed-aware question filter.

Boris Phase 8 contract module. Catches Lori asking the narrator to
confirm bio facts the operator already entered (CLAUDE.md design
principle 8: "If the operator seeded it, Lori knows it. If Lori knows
it, she does not ask for it as intake.").

Public functions:

    classify_seeded_fact_question(question, profile) -> Optional[str]
        Returns the field_key when `question` is an intake-shaped
        question targeting a value present in `profile`. Returns None
        when the question is fine (lived-experience shape) or when the
        targeted field has no seeded value.

    should_block_seeded_fact_question(question, profile) -> bool
        Boolean alias: True when the question should be blocked, False
        when it should be allowed through.

    rewrite_seeded_fact_question(question, profile) -> str
        Rewrites an intake-shaped question to a lived-experience
        question that uses the seeded value as context. Falls back to a
        generic open question when no rewrite is available.

Profile shape — supports the nested fixture format used by
`tests/boris_quality/fixtures/boris_quality_cases.py`:

    {
      "personal": {
        "preferredName": "Mable",
        "dateOfBirth": "1942-01-01",
        "placeOfBirth": "Albany, Georgia",
        "currentResidence": "Detroit, Michigan",
        "pronouns": "she/her"
      },
      "family": {
        "mother": {"alive": True, "age": 99, "residence": "St. Paul"},
        "children": [{"count": 2}]
      },
      "education_work": {
        "primary_career": "school psychologist",
        "current_work": "Pecos Schools",
        "career_start_year": 2010
      }
    }

Pure stdlib, no LLM, no DB, no IO.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


# ── Intake-question patterns ──────────────────────────────────────────────
#
# Each entry maps a regex (the question shape) to the profile lookup path
# that would carry a matching seeded value. The path is a list of dict
# keys; the resolver walks it and returns the leaf value (or None when
# any segment is missing).
_INTAKE_PATTERNS: Tuple[Tuple[re.Pattern, List[str]], ...] = (
    # Mable: "You were born in Albany, Georgia, in 1942?"
    (
        re.compile(
            r"\b(?:you were|were you) born in [^?.,]+",
            re.IGNORECASE,
        ),
        ["personal", "placeOfBirth"],
    ),
    (
        re.compile(
            r"\b(?:you were|were you) born[^?.,]{0,80}\b\d{4}\b",
            re.IGNORECASE,
        ),
        ["personal", "dateOfBirth"],
    ),
    # John: "Do you live in Las Vegas, New Mexico?"
    (
        re.compile(
            r"\b(?:do you (?:currently )?live|you (?:currently )?live) in [^?.,]+",
            re.IGNORECASE,
        ),
        ["personal", "currentResidence"],
    ),
    # John: "Do you work at Pecos Schools?"
    (
        re.compile(
            r"\b(?:do you (?:currently )?work|you (?:currently )?work) (?:at|for) [^?.,]+",
            re.IGNORECASE,
        ),
        ["education_work", "current_work"],
    ),
    # John: "Did you become a school psychologist in 2010?"
    (
        re.compile(
            r"\b(?:did you become a|did you start (?:working|as) a)\s+[A-Za-z ]+\s+in\s+\d{4}",
            re.IGNORECASE,
        ),
        ["education_work", "career_start_year"],
    ),
    # John: "Is your mother alive?" / "Is your mother still alive?"
    (
        re.compile(
            r"\bis your (?:mother|mom) (?:still )?alive\b",
            re.IGNORECASE,
        ),
        ["family", "mother", "alive"],
    ),
    # John: "Does your mother live in St. Paul?"
    (
        re.compile(
            r"\bdoes your (?:mother|mom) live in [^?.,]+",
            re.IGNORECASE,
        ),
        ["family", "mother", "residence"],
    ),
    # Children count
    (
        re.compile(
            r"\b(?:did you have|do you have)\s+(?:one|two|three|four|five|six|seven|\d+)\s+(?:child|children|kids)",
            re.IGNORECASE,
        ),
        ["family", "children"],
    ),
)


def _lookup_seeded_value(profile: Dict[str, Any], path: List[str]) -> Optional[Any]:
    """Walk the nested profile dict by path; return None on any miss."""
    if not isinstance(profile, dict):
        return None
    cursor: Any = profile
    for segment in path:
        if isinstance(cursor, dict):
            cursor = cursor.get(segment)
        elif isinstance(cursor, list):
            # children path may resolve to a list; return non-empty list
            return cursor if cursor else None
        else:
            return None
        if cursor is None:
            return None
    return cursor


def classify_seeded_fact_question(
    question: str, profile: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Return the field-key string when `question` is an intake-shaped
    question targeting a seeded value in `profile`; None otherwise.

    `field_key` is the dot-joined profile path (e.g. "personal.placeOfBirth")
    so the caller can attribute the block to a specific seeded value.
    """
    if not question:
        return None
    if not isinstance(profile, dict):
        return None
    for pattern, path in _INTAKE_PATTERNS:
        if not pattern.search(question):
            continue
        seeded_value = _lookup_seeded_value(profile, path)
        if seeded_value is None or seeded_value is False:
            continue
        # Empty string / empty list = not seeded
        if isinstance(seeded_value, (str, list)) and not seeded_value:
            continue
        return ".".join(path)
    return None


def should_block_seeded_fact_question(
    question: str, profile: Optional[Dict[str, Any]] = None,
) -> bool:
    """True when `question` should be blocked (intake-shaped + seeded)."""
    return classify_seeded_fact_question(question, profile) is not None


def _rewrite_with_anchor(field_key: str, seeded_value: Any) -> Optional[str]:
    """Return a lived-experience rewrite when one is available for the
    given field_key + seeded value pair."""
    value_str = str(seeded_value).strip() if seeded_value is not None else ""
    if field_key == "personal.placeOfBirth":
        if value_str:
            return f"What do you remember about {value_str} when you were little?"
        return "What do you remember about your earliest years?"
    if field_key == "personal.dateOfBirth":
        return "What do you remember about your earliest years?"
    if field_key == "personal.currentResidence":
        if value_str:
            return f"What does life in {value_str} feel like for you now?"
        return "What does life feel like for you now?"
    if field_key == "education_work.current_work":
        if value_str:
            return f"What has your time at {value_str} meant to you?"
        return "What has your work meant to you?"
    if field_key == "education_work.career_start_year":
        return "What drew you toward that work in the first place?"
    if field_key == "family.mother.alive":
        return "What has it meant to still have that connection with your mother all these years?"
    if field_key == "family.mother.residence":
        if value_str:
            return f"What does it mean that your mother is still in {value_str}?"
        return "What does that mother-and-place connection mean to you?"
    if field_key == "family.children":
        return "What has being a parent to them meant in your life?"
    return None


def rewrite_seeded_fact_question(
    question: str, profile: Optional[Dict[str, Any]] = None,
) -> str:
    """Rewrite an intake-shaped question to a lived-experience question
    that uses the seeded value as context. Falls back to a generic open
    question when no specific rewrite is available.

    Pass-through: if the question is NOT intake-shaped (or no seeded
    value matches), the original question is returned unchanged.
    """
    if not question:
        return question
    field_key = classify_seeded_fact_question(question, profile)
    if not field_key:
        return question
    path = field_key.split(".")
    seeded_value = _lookup_seeded_value(profile, path) if isinstance(profile, dict) else None
    rewrite = _rewrite_with_anchor(field_key, seeded_value)
    if rewrite:
        return rewrite
    return "Tell me more about that part of your life."


# Boris also probes a combined "rewrite or block" entry point
rewrite_or_block_seeded_fact_question = rewrite_seeded_fact_question


__all__ = [
    "classify_seeded_fact_question",
    "should_block_seeded_fact_question",
    "rewrite_seeded_fact_question",
    "rewrite_or_block_seeded_fact_question",
]
