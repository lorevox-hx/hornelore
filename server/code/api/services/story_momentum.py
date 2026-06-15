"""WO-LORI-STORY-FIRST-PHASE-1-01 (2026-06-14) — story momentum scorer.

═══════════════════════════════════════════════════════════════════════
  WHAT THIS IS
═══════════════════════════════════════════════════════════════════════

A composition-time signal that tells the composer whether the narrator
is in a story chapter (long, dense, anchored, sensory, sequenced) or
in a short factual exchange. The signal is consumed by:

  - question_hierarchy : suppress Layer 3-4 questions when in story mode
  - thread_bank        : do NOT surface banked threads when in story mode
  - prompt_composer    : pick the story-mode prompt block variant

The model is intentionally CHEAP and DETERMINISTIC. No LLM, no I/O.
Phase 2+ may replace this with an LLM-derived momentum signal; Phase 1
ships with the rule-based version because it is verifiable, fast,
and good enough for the story-vs-not-story distinction the question
hierarchy needs.

═══════════════════════════════════════════════════════════════════════
  SIGNALS (per WO §2)
═══════════════════════════════════════════════════════════════════════

  word_count           — narrator turn length (raw token count)
  named_entity_count   — capitalized non-stop-word tokens (proxy for
                          places, people, events)
  temporal_marker_count — "when", "then", "after", "before", "during",
                          years, ages, dates
  sensory_token_count  — vocabulary list of sensory verbs/adjectives
                          (~150 curated tokens)
  sequence_marker_count — "first", "next", "then", "later", "finally",
                          numeric ordinals
  dialogue_present     — quoted speech or "she said" / "he told me"
                          patterns (bool)
  uninterrupted_run    — number of consecutive narrator turns >= 50
                          words in the current session. CALLER provides
                          this (chat_ws walks the session history).

═══════════════════════════════════════════════════════════════════════
  COMPOSITE SCORE
═══════════════════════════════════════════════════════════════════════

Weighted sum, normalized to [0.0, 1.0]:

    momentum = 0.25 * norm(word_count, 0, 300)
             + 0.15 * norm(named_entity_count, 0, 5)
             + 0.10 * norm(temporal_marker_count, 0, 3)
             + 0.15 * norm(sensory_token_count, 0, 4)
             + 0.10 * norm(sequence_marker_count, 0, 3)
             + 0.10 * (1.0 if dialogue_present else 0.0)
             + 0.15 * norm(uninterrupted_run, 0, 4)

Weights sum to 1.0 → composite is always in [0.0, 1.0] by construction.

═══════════════════════════════════════════════════════════════════════
  THRESHOLDS (env-tunable)
═══════════════════════════════════════════════════════════════════════

  momentum >= HORNELORE_MOMENTUM_STORY      (default 0.60) → story mode
  momentum >= HORNELORE_MOMENTUM_EMERGING   (default 0.40) → emerging
  otherwise                                                  → normal

═══════════════════════════════════════════════════════════════════════
  PUBLIC API
═══════════════════════════════════════════════════════════════════════

  score_story_momentum(narrator_text, uninterrupted_run=0) → MomentumScore
      Compute all signals + composite + mode label for one turn.

  mode_for_score(score) → str
      "story" / "emerging" / "normal" — env-tunable thresholds.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional, Set


# ─────────────────────────────────────────────────────────────────────
# Vocabulary lists (curated, small, easy to audit)
# ─────────────────────────────────────────────────────────────────────

# Common English stop-words for the named-entity heuristic. A
# capitalized token that's also a stop-word (e.g., sentence-start
# "I", "The") is not a named entity.
_NE_STOPWORDS = frozenset({
    "I", "A", "An", "The", "And", "Or", "But", "So", "If", "Then",
    "Now", "Here", "There", "This", "That", "These", "Those",
    "He", "She", "It", "We", "They", "You", "My", "Your", "His",
    "Her", "Their", "Our", "Its",
    "Yes", "No", "Well", "Okay", "Ok",
    "What", "When", "Where", "Why", "How", "Who", "Which",
    "Mr", "Mrs", "Ms", "Dr",  # titles alone aren't entities
})


_TEMPORAL_MARKERS = frozenset({
    # Conjunctions and prepositions of time
    "when", "then", "after", "before", "during", "while", "until",
    "since", "once", "whenever", "later", "earlier",
    # Time-of-day / week / year terms (common ones)
    "morning", "afternoon", "evening", "night", "midnight", "noon",
    "monday", "tuesday", "wednesday", "thursday", "friday",
    "saturday", "sunday", "weekend", "weekday",
    "january", "february", "march", "april", "june", "july",
    "august", "september", "october", "november", "december",
    # May is also a modal verb; intentionally omitted to avoid
    # over-matching ("I may not remember" shouldn't count).
    # Stages of life
    "childhood", "teenage", "teens", "twenties", "thirties",
    "forties", "fifties", "sixties", "seventies", "eighties",
    "nineties",
})


# Year-style four-digit number 1800-2099 (covers narrator memoir range).
_YEAR_RX = re.compile(r"\b(?:18|19|20)\d{2}\b")

# Age phrasings ("when I was 9", "at 12 years old", "age twelve")
_AGE_RX = re.compile(
    r"\b(?:when\s+I\s+was|at\s+age|age|aged)\s+\w+|"
    r"\b\d{1,2}\s+years?\s+old\b",
    re.IGNORECASE,
)


# Curated sensory vocabulary. Conservative — only tokens that
# unambiguously signal sensory recall in a memoir context. Verbs of
# perception, adjectives describing physical sensation, weather terms.
_SENSORY_TOKENS = frozenset({
    # Sight
    "saw", "seen", "watched", "looked", "looking", "stared", "glimpsed",
    "bright", "dark", "shiny", "dim", "glowing", "shadow", "shadows",
    "color", "colors", "red", "blue", "green", "yellow", "black",
    "white", "grey", "gray", "brown", "orange", "purple",
    # Hearing
    "heard", "hearing", "listened", "listening", "sounded", "sounds",
    "loud", "quiet", "silent", "noise", "noises", "song", "songs",
    "voice", "voices", "music", "humming", "whistle", "whistling",
    "rang", "ringing", "buzz", "clang", "echo", "echoed",
    # Smell
    "smelled", "smell", "smelling", "scent", "scents", "fragrance",
    "stink", "stunk", "aroma",
    # Taste
    "tasted", "tasting", "sweet", "bitter", "sour", "salty", "spicy",
    "delicious", "bland",
    # Touch / temperature
    "felt", "feeling", "touched", "touching", "warm", "cold", "hot",
    "cool", "chilly", "freezing", "rough", "smooth", "soft", "hard",
    "sharp", "heavy", "light",
    # Weather (frequent sensory anchor in memoir)
    "rain", "raining", "rained", "snow", "snowing", "snowed", "wind",
    "windy", "storm", "stormy", "sunny", "cloudy", "foggy", "humid",
    # Movement / physical action vocabulary that paints scenes
    "walked", "ran", "running", "climbed", "climbing", "rode", "riding",
    "drove", "driving", "flew", "flying", "swam", "swimming",
})


_SEQUENCE_MARKERS = frozenset({
    "first", "second", "third", "fourth", "fifth", "sixth", "seventh",
    "eighth", "ninth", "tenth",
    "next", "then", "afterwards", "after", "later", "finally",
    "eventually", "subsequently", "before", "lastly",
    "initially", "originally", "ultimately",
})


# Dialogue patterns — quoted speech OR reporting verbs that signal
# remembered conversation. The reporting-verb form ("she said", "he
# told me") is the most common memoir signal.
_DIALOGUE_RX = re.compile(
    r"[\"“”].+?[\"“”]"          # double-quoted
    r"|[‘’].+?[‘’]"             # single-quoted (smart quotes)
    r"|\b(?:said|told|asked|replied|answered|whispered|shouted|"
    r"yelled|called|cried|exclaimed|murmured)\b",
    re.IGNORECASE,
)


# ─────────────────────────────────────────────────────────────────────
# Threshold helpers
# ─────────────────────────────────────────────────────────────────────

MODE_STORY = "story"
MODE_EMERGING = "emerging"
MODE_NORMAL = "normal"

_DEFAULT_STORY_THRESHOLD = 0.60
_DEFAULT_EMERGING_THRESHOLD = 0.40


def _read_threshold(env_name: str, default: float) -> float:
    """Read an env-tunable threshold, clamped to [0.0, 1.0]."""
    raw = os.getenv(env_name, "")
    if not raw:
        return default
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, v))


def _story_threshold() -> float:
    return _read_threshold("HORNELORE_MOMENTUM_STORY", _DEFAULT_STORY_THRESHOLD)


def _emerging_threshold() -> float:
    return _read_threshold("HORNELORE_MOMENTUM_EMERGING", _DEFAULT_EMERGING_THRESHOLD)


def mode_for_score(score: float) -> str:
    """Return the mode label for a composite momentum score."""
    if score >= _story_threshold():
        return MODE_STORY
    if score >= _emerging_threshold():
        return MODE_EMERGING
    return MODE_NORMAL


# ─────────────────────────────────────────────────────────────────────
# Signal computation
# ─────────────────────────────────────────────────────────────────────


def _normalize(value: float, lo: float, hi: float) -> float:
    """Linear normalization to [0.0, 1.0] with clamping at both ends."""
    if hi <= lo:
        return 0.0
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def _count_named_entities(text: str) -> int:
    """Capitalized non-stop-word tokens excluding sentence-start.

    Heuristic: walk the tokens, keep capitalized ones that are not in
    `_NE_STOPWORDS` AND are not the very first token of a sentence
    (where capitalization is grammatical, not entity-signaling).

    Counts each capitalized run once (a multi-word entity like
    "Captain Kirk" counts as one). This matches the spec's framing
    of named_entity_count as a coarse proxy.
    """
    if not text:
        return 0
    # Split into sentences first so we can skip the first token per
    # sentence. Cheap split — no need for full sentence tokenization.
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    count = 0
    for sent in sentences:
        tokens = sent.split()
        in_entity = False
        for i, raw in enumerate(tokens):
            # Strip surrounding punctuation for the capitalization
            # check but keep the original to detect contractions.
            tok = raw.strip(".,;:!?\"'()[]")
            if not tok:
                in_entity = False
                continue
            is_cap = tok[0].isupper()
            is_stopword = tok in _NE_STOPWORDS
            is_first = i == 0
            if is_cap and not is_stopword and not is_first:
                if not in_entity:
                    count += 1
                    in_entity = True
            else:
                in_entity = False
    return count


def _count_temporal_markers(text: str) -> int:
    """Conjunctions / time-words + year-pattern + age-pattern hits."""
    if not text:
        return 0
    lower = text.lower()
    # Word-token markers
    tokens = re.findall(r"\b[a-z]+\b", lower)
    word_hits = sum(1 for t in tokens if t in _TEMPORAL_MARKERS)
    # Year patterns
    year_hits = len(_YEAR_RX.findall(text))
    # Age patterns
    age_hits = len(_AGE_RX.findall(text))
    return word_hits + year_hits + age_hits


def _count_sensory_tokens(text: str) -> int:
    if not text:
        return 0
    tokens = re.findall(r"\b[a-z]+\b", text.lower())
    return sum(1 for t in tokens if t in _SENSORY_TOKENS)


def _count_sequence_markers(text: str) -> int:
    if not text:
        return 0
    tokens = re.findall(r"\b[a-z]+\b", text.lower())
    return sum(1 for t in tokens if t in _SEQUENCE_MARKERS)


def _has_dialogue(text: str) -> bool:
    if not text:
        return False
    return bool(_DIALOGUE_RX.search(text))


def _word_count(text: str) -> int:
    return len((text or "").split())


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MomentumScore:
    """Story-momentum signal pack for one narrator turn.

    All counts are raw; composite is the normalized weighted sum;
    mode is the threshold-derived label.

    The dataclass is frozen for safe sharing across the request
    pipeline (chat_ws hands it to the prompt composer and the
    question-hierarchy validator).
    """
    word_count: int
    named_entity_count: int
    temporal_marker_count: int
    sensory_token_count: int
    sequence_marker_count: int
    dialogue_present: bool
    uninterrupted_run: int
    composite: float
    mode: str


def score_story_momentum(
    narrator_text: str,
    uninterrupted_run: int = 0,
) -> MomentumScore:
    """Compute the full momentum signal pack for one narrator turn.

    `uninterrupted_run` is the count of CONSECUTIVE prior narrator
    turns (this session) that had >= 50 words. Caller (chat_ws)
    computes this by walking the session history; the module is
    stateless. Pass 0 when there's no history.

    Returns a MomentumScore. Composite is always in [0.0, 1.0].
    Mode is "story" / "emerging" / "normal" per the env-tunable
    thresholds.
    """
    wc = _word_count(narrator_text)
    nec = _count_named_entities(narrator_text or "")
    tmc = _count_temporal_markers(narrator_text or "")
    stc = _count_sensory_tokens(narrator_text or "")
    smc = _count_sequence_markers(narrator_text or "")
    dlg = _has_dialogue(narrator_text or "")
    run = max(0, int(uninterrupted_run or 0))

    composite = (
        0.25 * _normalize(wc, 0, 300)
        + 0.15 * _normalize(nec, 0, 5)
        + 0.10 * _normalize(tmc, 0, 3)
        + 0.15 * _normalize(stc, 0, 4)
        + 0.10 * _normalize(smc, 0, 3)
        + 0.10 * (1.0 if dlg else 0.0)
        + 0.15 * _normalize(run, 0, 4)
    )
    # Defensive clamp — weights sum to 1.0 so composite is bounded by
    # construction, but float arithmetic can drift on edge inputs.
    composite = max(0.0, min(1.0, composite))

    return MomentumScore(
        word_count=wc,
        named_entity_count=nec,
        temporal_marker_count=tmc,
        sensory_token_count=stc,
        sequence_marker_count=smc,
        dialogue_present=dlg,
        uninterrupted_run=run,
        composite=composite,
        mode=mode_for_score(composite),
    )


__all__ = [
    "MomentumScore",
    "score_story_momentum",
    "mode_for_score",
    "MODE_STORY",
    "MODE_EMERGING",
    "MODE_NORMAL",
]
