"""WO-LORI-STORY-CAPTURE-01 Phase 1A Commit 2 — DOB + age-bucket arithmetic.

The product unlock from Chris's dialogue with Janice (2026-04-30):

    "When were you born — I can tell you what year you would have been
    in 6 and most people are in 1st grade then."
    "August 30, 1939."
    "Right before WW2 — that must have been a challenging time for
    your parents."

This module turns DOB + bucketed age phrase into approximate year range
WITHOUT asking the narrator to remember exact dates. Knowing Janice was
born 1939-08-30 and she said "I started school at 5 or 6" lands her
first-grade year at 1944–45 with no further pressure.

Pure functions, no I/O, no extraction-stack imports. The LAW 3
INFRASTRUCTURE gate is satisfied trivially.

Buckets are designed to match how elder narrators actually phrase
uncertainty ("very little", "before school", "in school", "older",
"teenager") and map back to the canonical 7-era spine declared in
WO-CANONICAL-LIFE-SPINE-01:

    earliest_years     → ages 0–4
    early_school_years → ages 5–11
    adolescence        → ages 12–17
    coming_of_age      → ages 18–25
    building_years     → ages 26–55
    later_years        → ages 56–84
    today              → ages 85+

Multi-era candidates are preserved as a list, NOT collapsed to a single
era. "Before school" can land in either earliest_years OR
early_school_years; the operator review queue resolves the ambiguity
(see WO §0.5 — the cover never overrides the windings).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional, Tuple


# ── Bucket → age range ────────────────────────────────────────────────────
# Tuples are inclusive (age_low, age_high). Designed to fail GRACEFULLY:
# unknown buckets return (None, None) instead of raising, so a stale
# bucket name written by an older client doesn't crash preservation.

_BUCKET_TO_AGE_RANGE: dict[str, Tuple[int, int]] = {
    "very_little":   (0, 4),
    "before_school": (3, 5),
    "preschool":     (3, 5),
    "early_school":  (5, 8),
    "in_school":     (5, 11),
    "grade_school":  (5, 11),
    "older":         (12, 17),
    "adolescent":    (12, 17),
    "teenager":      (13, 19),
    "young_adult":   (18, 25),
    "coming_of_age": (18, 25),
}


# ── Bucket → era_candidates (for the canonical 7-era spine) ───────────────
# When a bucket spans an era boundary, both candidates are recorded.
# Operator review resolves the ambiguity at HITL time.

_BUCKET_TO_ERA_CANDIDATES: dict[str, List[str]] = {
    "very_little":   ["earliest_years"],
    "before_school": ["earliest_years", "early_school_years"],
    "preschool":     ["earliest_years", "early_school_years"],
    "early_school":  ["early_school_years"],
    "in_school":     ["early_school_years"],
    "grade_school":  ["early_school_years"],
    "older":         ["adolescence"],
    "adolescent":    ["adolescence"],
    "teenager":      ["adolescence"],
    "young_adult":   ["coming_of_age"],
    "coming_of_age": ["coming_of_age"],
}


# ── Public API ────────────────────────────────────────────────────────────

def normalize_bucket(bucket: Optional[str]) -> Optional[str]:
    """Lowercase and strip a bucket label. Returns None for empty,
    None, or whitespace-only input. Does NOT validate against the
    known set — that's the caller's decision to make."""
    if not bucket:
        return None
    norm = bucket.strip().lower()
    return norm if norm else None


def is_known_bucket(bucket: Optional[str]) -> bool:
    """Cheap predicate: is this a bucket the arithmetic understands?"""
    norm = normalize_bucket(bucket)
    return bool(norm) and norm in _BUCKET_TO_AGE_RANGE


def bucket_to_era_candidates(bucket: Optional[str]) -> List[str]:
    """Return the era_id list for a bucket. Unknown buckets return [].

    Multi-era buckets ("before_school" → ["earliest_years",
    "early_school_years"]) are returned as-is — the schema preserves
    ambiguity; the operator queue resolves it."""
    norm = normalize_bucket(bucket)
    if not norm:
        return []
    return list(_BUCKET_TO_ERA_CANDIDATES.get(norm, []))


def estimate_year_from_age_bucket(
    narrator_dob: Optional[date],
    bucket: Optional[str],
) -> Tuple[Optional[int], Optional[int]]:
    """DOB + bucket → (year_low, year_high). Returns (None, None) if
    either input is missing or the bucket is unknown.

    Year arithmetic is birth_year + age_low/age_high. We do NOT factor
    in birth month vs. school-year cutoff; that's deliberate. The
    bucket is already approximate, and adding month-precision would
    suggest a precision the narrator's memory doesn't support.

    Examples:
        DOB 1939-08-30 + "in_school"   → (1944, 1950)
        DOB 1939-08-30 + "very_little" → (1939, 1943)
        DOB None + any                 → (None, None)
        any + None                     → (None, None)
        any + "made_up_bucket"         → (None, None)
    """
    if narrator_dob is None:
        return (None, None)
    if not isinstance(narrator_dob, date):
        return (None, None)

    norm = normalize_bucket(bucket)
    if not norm or norm not in _BUCKET_TO_AGE_RANGE:
        return (None, None)

    age_low, age_high = _BUCKET_TO_AGE_RANGE[norm]
    birth_year = narrator_dob.year
    return (birth_year + age_low, birth_year + age_high)


def parse_dob(dob_value: Optional[str]) -> Optional[date]:
    """Tolerant DOB parser. Accepts ISO-8601 (`1939-08-30`), ISO-8601
    with time (`1939-08-30T00:00:00`), or returns None if it can't
    parse. Used by callers that read DOB from narrator templates or
    profile_seed where format is loose."""
    if not dob_value or not isinstance(dob_value, str):
        return None
    s = dob_value.strip()
    if not s:
        return None

    # Try a few common shapes; keep the list small and explicit.
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue

    # Last-chance: a bare 4-digit year. Useful for narrators who only
    # remember "born around 1939" — we land them on Jan 1 of that year.
    try:
        if len(s) == 4 and s.isdigit():
            year = int(s)
            if 1850 <= year <= datetime.utcnow().year:
                return date(year, 1, 1)
    except ValueError:
        pass

    return None


def all_known_buckets() -> List[str]:
    """Return every bucket the arithmetic understands. Useful for
    composing the prompt that asks the bucket question and for
    operator-side validation."""
    return sorted(_BUCKET_TO_AGE_RANGE.keys())


__all__ = [
    "normalize_bucket",
    "is_known_bucket",
    "bucket_to_era_candidates",
    "estimate_year_from_age_bucket",
    "parse_dob",
    "all_known_buckets",
]
