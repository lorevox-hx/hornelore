"""WO-LORI-STORY-CAPTURE-01 Phase 1A Commit 3a — story trigger detection.

Post-turn classifier. Decides whether a narrator turn merits creating a
story_candidate row. Pure functions, no I/O, zero extraction-stack
imports — sits cleanly under the LAW 3 INFRASTRUCTURE gate.

Two trigger paths (per WO §3.3):
  * full_threshold        — long story with at least one scene anchor
                            (duration ≥ 30s AND words ≥ 60 AND ≥1 anchor)
  * borderline_scene_anchor — short turn rescued by HIGH anchor density
                            (anchors ≥ 3) — catches Janice's actual
                            mastoidectomy turn (~25s/50w but rich in
                            place + relative-time + person-relation
                            references)

Returns None when neither path fires. Caller decides what to do then
(default: skip story_candidate creation, let extraction run as normal).

Thresholds are env-tunable so an operator can dial them per narrator
without a code change. Defaults match the WO spec.
"""
from __future__ import annotations

import os
import re
from typing import List, Optional


# ── Thresholds (env-tunable) ──────────────────────────────────────────────

def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# Recomputed per call so tests / live operators can re-tune at runtime
# without re-importing the module.
def _min_duration_sec() -> float:
    return _env_float("STORY_TRIGGER_MIN_DURATION_SEC", 30.0)


def _min_words() -> int:
    return _env_int("STORY_TRIGGER_MIN_WORDS", 60)


def _borderline_anchor_count() -> int:
    return _env_int("STORY_TRIGGER_BORDERLINE_ANCHOR_COUNT", 3)


# ── Scene-anchor detection ────────────────────────────────────────────────
#
# Conservative bigram detection, NOT loose keyword presence. Janice
# saying "I was very little" is not a scene anchor; "in Spokane" is.
# The dimensions:
#   1. PLACE — explicit place noun OR matches proper-noun place pattern
#   2. RELATIVE_TIME — phrasing that anchors the memory in time
#   3. PERSON_RELATION — family/role reference ("my dad", "my mom",
#      "my grandmother", etc.)
#
# Each dimension that fires contributes 1 to the anchor count. Total
# range is 0–3 per turn.

# Place words split into two tiers to keep bare-reference false positives
# out (a 2026-04-30 reviewer caught "School was hard" / "Kitchen was tidy"
# firing as place anchors against the docstring's stated intent — bug was
# real, fixed before 3b banks):
#
# Tier 1 (BARE): institutional / industrial nouns whose bare mention is
# overwhelmingly locational. "Hospital was crowded" reads as place.
#
# Tier 2 (PREP_REQUIRED): common nouns that ALSO denote places. These
# only count as place anchors when preceded by a place preposition
# ("in the kitchen", "at school", "to the barn"). "Kitchen was tidy"
# is a state predicate about an object and does NOT fire.
_PLACE_NOUNS_BARE = {
    "hospital", "church", "factory", "fairgrounds",
}

# `plant` and `mill` were originally Tier 1 but a 2026-04-30 reviewer
# caught them overfiring on bare predicate uses ("The plant died.",
# "They mill around.") because both nouns also act as common nouns
# ("a houseplant") and as verbs ("mill around"). Demoted to Tier 2 —
# they only count as place anchors with a place preposition
# ("at the plant", "to the mill", "near the aluminum plant").
_PLACE_NOUNS_PREP_REQUIRED = {
    "plant", "mill",
    "farm", "ranch", "shop", "store",
    "kitchen", "yard", "porch",
    "river", "lake", "park",
    "neighborhood", "town", "village", "city", "county",
    "school", "library", "barn", "garage", "alley",
}

# Word-boundary match (the previous substring approach matched "plant"
# inside "implant" and "mill" inside "million" — silently correct on
# the canonical Janice text but a real risk elsewhere).
_PLACE_NOUN_BARE_RE = re.compile(
    r"\b(?:" + "|".join(sorted(_PLACE_NOUNS_BARE)) + r")\b",
    re.IGNORECASE,
)

# Tier 2 must be preceded by a place preposition. Optional determiner
# (the / a / my / etc.) followed by 0–2 lowercase adjective tokens
# before the noun ("at the aluminum plant", "in the small white
# kitchen"). The adjective slot is bounded at 2 to keep "at home with
# my plant" from sneaking in via greedy consumption.
_PLACE_NOUN_PREP_RE = re.compile(
    r"\b(?:in|at|to|from|near|outside|inside|behind|by|around|through|"
    r"over|across|beside|past|toward|towards)\s+"
    r"(?:(?:the|a|an|my|our|her|his|their)\s+)?"
    r"(?:[a-z]+\s+){0,2}"
    r"(?:" + "|".join(sorted(_PLACE_NOUNS_PREP_REQUIRED)) + r")\b",
    re.IGNORECASE,
)

# Relative-time phrasing — these are the elder-narrator markers that
# place a memory without forcing precision. Multi-word patterns must
# match as bigrams or trigrams; single tokens like "remember" are too
# loose and would fire on every other turn.
_RELATIVE_TIME_PATTERNS = (
    re.compile(r"\bwhen i was\b", re.IGNORECASE),
    re.compile(r"\bwhen we were\b", re.IGNORECASE),
    re.compile(r"\bback then\b", re.IGNORECASE),
    re.compile(r"\bin those days\b", re.IGNORECASE),
    re.compile(r"\bgrowing up\b", re.IGNORECASE),
    re.compile(r"\bbefore (?:the |my )?(?:war|school|kids|that|then)\b", re.IGNORECASE),
    re.compile(r"\bafter (?:the |my )?(?:war|wedding|funeral|service)\b", re.IGNORECASE),
    re.compile(r"\b(?:as|when) a (?:child|kid|girl|boy|teenager)\b", re.IGNORECASE),
    re.compile(r"\bone (?:summer|winter|spring|fall|day|night|morning|evening)\b", re.IGNORECASE),
    re.compile(r"\b(?:in|during) (?:the |my )?(?:summer|winter|spring|fall|war|childhood)\b", re.IGNORECASE),
)

# Person-relation phrasing — narrators referencing the people who
# populated the scene. "my dad", "my mother", "my grandmother". Bare
# pronouns and common names don't fire.
_PERSON_RELATION_PATTERNS = (
    re.compile(r"\bmy (?:dad|father|papa|pop)\b", re.IGNORECASE),
    re.compile(r"\bmy (?:mom|mother|mama|ma)\b", re.IGNORECASE),
    re.compile(r"\bmy (?:brother|sister|sibling)s?\b", re.IGNORECASE),
    re.compile(r"\bmy (?:grandmother|grandma|granny|nana)\b", re.IGNORECASE),
    re.compile(r"\bmy (?:grandfather|grandpa|granddad|papa)\b", re.IGNORECASE),
    re.compile(r"\bmy (?:aunt|uncle|cousin)s?\b", re.IGNORECASE),
    re.compile(r"\bmy (?:husband|wife|spouse)\b", re.IGNORECASE),
    re.compile(r"\bmy (?:son|daughter|kids?|children)\b", re.IGNORECASE),
)

# Proper-noun place pattern: capitalized word(s) that look like a place
# name. Conservative — must be either after a place preposition (in/at/from)
# OR a multi-word capitalized run ("Grand Forks", "North Dakota").
_PROPER_NOUN_PLACE_AFTER_PREP = re.compile(
    r"\b(?:in|at|from|to|near|outside) ([A-Z][a-zA-Z]+(?:[ \-][A-Z][a-zA-Z]+)*)",
)
_PROPER_NOUN_MULTI_WORD = re.compile(
    r"\b([A-Z][a-zA-Z]+)\s+([A-Z][a-zA-Z]+)\b",
)


def _matches_place(text: str) -> bool:
    """Does this text contain a place reference?

    Order matters for clarity, not correctness — any single hit fires:
      1. Tier 1 institutional / industrial noun (bare mention OK)
      2. Tier 2 common-noun place word PRECEDED by a place preposition
      3. Proper noun after a place preposition ("in Spokane")
      4. Multi-word capitalized run ("Grand Forks", "North Dakota")
    """
    if _PLACE_NOUN_BARE_RE.search(text):
        return True
    if _PLACE_NOUN_PREP_RE.search(text):
        return True
    if _PROPER_NOUN_PLACE_AFTER_PREP.search(text):
        return True
    if _PROPER_NOUN_MULTI_WORD.search(text):
        return True
    return False


def _matches_relative_time(text: str) -> bool:
    """Does this text contain time-anchoring phrasing?"""
    return any(pat.search(text) for pat in _RELATIVE_TIME_PATTERNS)


def _matches_person_relation(text: str) -> bool:
    """Does this text reference a family/role person?"""
    return any(pat.search(text) for pat in _PERSON_RELATION_PATTERNS)


def count_scene_anchors(text: str) -> int:
    """Return 0..3 — the number of anchor dimensions present.

    Each dimension contributes at most 1. A turn that mentions
    "Spokane" three times still has anchor_count=1 from the place
    axis. The point is *dimensional richness*, not raw frequency.
    """
    if not text:
        return 0
    score = 0
    if _matches_place(text):
        score += 1
    if _matches_relative_time(text):
        score += 1
    if _matches_person_relation(text):
        score += 1
    return score


def has_scene_anchor(text: str) -> bool:
    """Is there at least one anchor dimension? Cheap predicate."""
    return count_scene_anchors(text) >= 1


# ── Trigger classification ────────────────────────────────────────────────

def classify_story_candidate(
    *,
    audio_duration_sec: Optional[float],
    transcript: str,
) -> Optional[str]:
    """Returns trigger_reason string if the turn should produce a
    story_candidate, else None.

    Inputs are kwargs (no positional confusion) and minimal — just the
    audio duration and the transcript text. Word count is computed
    from the transcript here so callers don't have to pre-compute and
    risk drift between the trigger threshold and the persisted
    word_count.

    Two trigger paths:
        full_threshold (medium confidence)
            duration ≥ MIN_DURATION_SEC
            AND words ≥ MIN_WORDS
            AND scene_anchor_count ≥ 1

        borderline_scene_anchor (low confidence)
            scene_anchor_count ≥ BORDERLINE_ANCHOR_COUNT (default 3)

    The borderline path catches Janice's actual mastoidectomy story,
    which is below the duration/word floor but rich in anchors.
    """
    if not transcript or not transcript.strip():
        return None

    word_count = len(transcript.split())
    anchors = count_scene_anchors(transcript)

    duration = audio_duration_sec if isinstance(audio_duration_sec, (int, float)) else 0.0

    # Primary path: substantial story with at least one anchor.
    if (
        duration >= _min_duration_sec()
        and word_count >= _min_words()
        and anchors >= 1
    ):
        return "full_threshold"

    # Borderline path: short but anchor-rich. The threshold is the
    # MAX dimensions (3) by default — all three axes must fire.
    if anchors >= _borderline_anchor_count():
        return "borderline_scene_anchor"

    return None


def trigger_diagnostic(
    *,
    audio_duration_sec: Optional[float],
    transcript: str,
) -> dict:
    """Same inputs as classify_story_candidate, but returns the
    underlying numbers so logs and operator review can show WHY a
    turn was (or wasn't) classified.

    Useful in the chat_ws turn handler for emitting a
    [story-trigger] log marker per turn — operator can see the
    threshold proximity and tune env vars accordingly.
    """
    word_count = len(transcript.split()) if transcript else 0
    anchors = count_scene_anchors(transcript or "")
    duration = audio_duration_sec if isinstance(audio_duration_sec, (int, float)) else 0.0

    trigger = classify_story_candidate(
        audio_duration_sec=audio_duration_sec,
        transcript=transcript,
    )

    return {
        "trigger": trigger,
        "duration_sec": duration,
        "word_count": word_count,
        "anchor_count": anchors,
        "place_anchor": _matches_place(transcript or ""),
        "time_anchor": _matches_relative_time(transcript or ""),
        "person_anchor": _matches_person_relation(transcript or ""),
        "thresholds": {
            "min_duration_sec": _min_duration_sec(),
            "min_words": _min_words(),
            "borderline_anchor_count": _borderline_anchor_count(),
        },
    }


__all__ = [
    "count_scene_anchors",
    "has_scene_anchor",
    "classify_story_candidate",
    "trigger_diagnostic",
]
