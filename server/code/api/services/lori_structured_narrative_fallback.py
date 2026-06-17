"""Structured-narrative fallback composer.

Boris Phase 7 contract module. Two public functions:

    extract_safe_anchors(text) -> List[str]
        Returns a small filtered anchor list from narrator text.
        Drops calendar tokens (Wednesday, October, etc.), religious-
        residue (Catholic, Mass, Church), and common-noun residue
        (Time, School). Caps at 4 to keep the list human.

    build_structured_narrative_fallback(narrator_text, anchors) -> str
        Builds a clean continuation invitation. NEVER uses the
        "You went from X to Y, then Z, A, B, and C" template — the
        cascade dump that fired across 5 narrators in the 2026-06-17
        full-family run. Instead writes one human sentence anchored
        to ≤2 narrator-named anchors plus a single open question.

Pure stdlib, no LLM, no DB, no IO. Safe to import in tests; idempotent.
"""
from __future__ import annotations

import re
from typing import List, Optional

# Tokens that must NEVER appear in the formatted anchor list. Mirrors
# `lori_witness_mode._CASCADE_FILTER_TOKENS` plus the additional Time/
# Engle/Wrinkle class surfaced in the 2026-06-17 Pat Later cascade.
_CASCADE_FILTER_TOKENS = frozenset({
    # Calendar
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
    "sunday",
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
    # Religious / common-noun residue
    "catholic", "mass", "church", "school", "home", "family",
    "love", "life", "war", "joy", "time",
    # Joining / connector residue
    "then", "the", "and", "but", "so", "or", "when", "where", "while",
})

# Proper-noun-shaped tokens from narrator text. Multi-word phrases
# captured greedily: "Saint Augustine", "Cochiti Pueblo", "Mount Olive
# AME", "Boston Latin School", "Mexico City", "North Quincy".
_PROPER_NOUN_RX = re.compile(
    r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3})\b"
)


def extract_safe_anchors(text: str, *, max_n: int = 4) -> List[str]:
    """Pull a small filtered anchor list from narrator text.

    Returns up to `max_n` distinct proper-noun phrases, with calendar /
    religious-residue / common-noun tokens removed. Order preserved
    (earlier mentions ranked higher).

    Per Boris Phase 7 contract: the function operates on raw narrator
    text and returns the anchor list directly. No call site needs to
    pre-extract or pre-filter; this is the single chokepoint.
    """
    if not text:
        return []
    seen_lower: set = set()
    anchors: List[str] = []
    for m in _PROPER_NOUN_RX.finditer(text):
        candidate = m.group(1).strip()
        if not candidate:
            continue
        first_token = candidate.split()[0]
        if first_token.lower() in _CASCADE_FILTER_TOKENS:
            # Try to strip the leading filter token; if remainder is
            # non-empty and starts with a capital, keep that.
            if " " in candidate:
                tail = candidate.split(" ", 1)[1].strip()
                if tail and tail[0].isupper():
                    candidate = tail
                else:
                    continue
            else:
                continue
        # Drop if entire candidate is in the filter set
        if candidate.lower() in _CASCADE_FILTER_TOKENS:
            continue
        # Drop short / non-name fragments
        if len(candidate) < 3:
            continue
        # Dedupe case-insensitive
        key = candidate.lower()
        if key in seen_lower:
            continue
        seen_lower.add(key)
        anchors.append(candidate)
        if len(anchors) >= max_n:
            break
    return anchors


def _format_anchor_list(anchors: List[str]) -> str:
    """Render the cleaned anchor list as a human-readable phrase.

    Caps at 2 anchors so the output never reads as a list recital.
    Returns "" when the list is empty.
    """
    if not anchors:
        return ""
    if len(anchors) == 1:
        return anchors[0]
    return f"{anchors[0]} and {anchors[1]}"


def build_structured_narrative_fallback(
    *,
    narrator_text: str,
    anchors: Optional[List[str]] = None,
    open_question: str = "What stays with you most about that?",
) -> str:
    """Compose a clean structured-narrative continuation invitation.

    The fallback NEVER uses the "You went from X to Y, then Z, A, B, and
    C. What happened next?" template. Instead emits one human sentence
    anchored to ≤2 narrator-named anchors followed by one open question.

    When the caller has already extracted anchors, pass them via
    `anchors`. Otherwise the function re-runs `extract_safe_anchors`
    against `narrator_text` so any single call site can use it without
    pre-processing.
    """
    if anchors is None:
        anchors = extract_safe_anchors(narrator_text)
    cleaned_anchors = [a for a in anchors if a and a.strip()]
    # Filter cascade residue from any externally-supplied list too —
    # the contract is "this function will not emit cascade residue,"
    # regardless of where the input came from.
    filtered: List[str] = []
    seen: set = set()
    for raw in cleaned_anchors:
        candidate = raw.strip()
        if not candidate:
            continue
        first_token = candidate.split()[0]
        if first_token.lower() in _CASCADE_FILTER_TOKENS:
            if " " in candidate:
                tail = candidate.split(" ", 1)[1].strip()
                if not tail or not tail[0].isupper():
                    continue
                candidate = tail
            else:
                continue
        if candidate.lower() in _CASCADE_FILTER_TOKENS:
            continue
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        filtered.append(candidate)
        if len(filtered) >= 2:
            break
    anchor_phrase = _format_anchor_list(filtered)
    if anchor_phrase:
        return f"{anchor_phrase} — there's a lot held in that. {open_question}"
    # No usable anchors: emit the open question alone
    return open_question


__all__ = [
    "extract_safe_anchors",
    "build_structured_narrative_fallback",
]
