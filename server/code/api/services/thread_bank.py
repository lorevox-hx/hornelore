"""WO-LORI-STORY-FIRST-PHASE-1-01 (2026-06-14) — thread bank service.

═══════════════════════════════════════════════════════════════════════
  WHAT THIS IS
═══════════════════════════════════════════════════════════════════════

Persistent thread bank for unresolved story doors. When a narrator
mentions multiple anchors in one turn — "my grandmother, the train
ride, then Germany, the church choir" — Lori gently follows ONE and
silently banks the other three. Later in the session, when a
natural pause occurs, the oldest banked thread surfaces with a
warm template:

    "Earlier you mentioned your grandmother. I keep thinking about
    her. What was she like?"

Per WO §3 — the unsurfaced thread is preserved as story material and
returned to with narrative weight, not chronological control.

═══════════════════════════════════════════════════════════════════════
  ARCHITECTURE
═══════════════════════════════════════════════════════════════════════

DB-backed via `interview_threads` table (schema in db.py init_db()
and migration 0009). Pure-function module composes with:

  - lori_reflection.extract_concrete_anchor — proper-noun extraction
  - lori_reflection._KINSHIP_ANCHOR_RX       — kinship anchor pattern
  - story_momentum                            — surfacing-suppression signal
  - db.interview_thread_*                     — persistence

Surfacing logic — when Lori composes a turn:

  - If narrator turn is in story mode (momentum >= 0.6): NO surfacing.
    The chapter continues.
  - If narrator turn is short or ends a chapter (momentum < 0.4 OR
    contains closing markers): surfacing eligibility check.
    - Thread is `open`
    - Thread is older than current narrator turn by at least 3 turns
    - Thread has not been declined previously
    - Oldest eligible thread wins
  - Composition uses the template above; surfacing updates status to
    `surfaced` and writes `surfaced_at`.

After surfacing, the narrator's response on the NEXT turn determines
the thread's final state:

  - Substantive response (>= 30 words) → resolved
  - Declination matching one of CLOSING_MARKERS / DECLINATION_PATTERNS
    or response < 8 words → declined
  - Otherwise → stays surfaced (re-evaluable next turn)

═══════════════════════════════════════════════════════════════════════
  CATEGORIES (coarse heuristic)
═══════════════════════════════════════════════════════════════════════

  person       — kinship terms ("your father"), capitalized name-shape
                  (single-cap or cap-cap)
  place        — capitalized after "in"/"at"/"to"/"from"/"near", OR
                  state/country list match
  time_period  — contains year (1800-2099), decade word, or age phrase
  event        — definite-noun-phrase mentioning a verb-like noun
                  ("the train ride", "the wedding", "the funeral")
  object       — definite-noun-phrase otherwise ("the church choir",
                  "the radio")

Categories are advisory — used for operator review surface (future)
and telemetry. The thread bank's behavior does not branch on
category in v1.

═══════════════════════════════════════════════════════════════════════
  PUBLIC API
═══════════════════════════════════════════════════════════════════════

  extract_thread_candidates(narrator_text, source_turn_index) → List[ThreadCandidate]
      Pure extraction (no DB), returns dataclass list with anchor +
      excerpt + category.

  bank_new_threads(session_id, candidates) → List[str]
      Persist non-duplicate candidates. Returns list of inserted ids.

  select_surfacing_target(session_id, current_turn_index, momentum_mode,
                          narrator_text="") → Optional[ThreadRow]
      Pick the oldest eligible thread to surface this turn, or None
      when no thread should surface.

  build_surfacing_text(thread, open_question="What was that like?") → str
      Template builder.

  evaluate_response_to_surfaced_thread(narrator_text, thread) → str
      Classify the narrator's response as "resolved" / "declined" /
      "unclear". Caller decides whether to call interview_thread_set_status.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Set

from .. import db
from .lori_reflection import (
    _PROPER_NOUN_RX,
    _PROPER_NOUN_AT_START_RX,
    _PROPER_NOUN_BLOCKLIST,
    _KINSHIP_ANCHOR_RX,
    _KINSHIP_CANON,
    _trim_trailing_blocklist,
    _split_first_sentence,
)


# ─────────────────────────────────────────────────────────────────────
# Surfacing heuristics + vocab
# ─────────────────────────────────────────────────────────────────────

# WO §3 — closing markers that signal the chapter has ended and the
# narrator is open to a redirect. Substring match against lowercased
# narrator turn.
CLOSING_MARKERS = (
    "anyway",
    "that's about it",
    "that is about it",
    "i don't know what else",
    "i do not know what else",
    "where was i",
    "what was i saying",
    "i forgot what i was saying",
    "that's all i remember",
    "that is all i remember",
)


# Patterns that mark a narrator declining a surfaced thread. Matched
# against lowercased response text. Order matters — more-specific
# patterns first.
DECLINATION_PATTERNS = (
    "not much to say",
    "let's skip",
    "let us skip",
    "skip that",
    "i'd rather not",
    "i would rather not",
    "don't want to talk about that",
    "do not want to talk about that",
    "i don't remember much",
    "i don't really remember",
    "nothing comes to mind",
    "can't recall",
    "cannot recall",
    "let's move on",
    "let us move on",
)


# Per WO §3 substantive-response threshold.
_SUBSTANTIVE_WORD_COUNT = 30

# Per WO §3 surfacing age requirement — banked threads must be at
# least this many turns old before surfacing.
DEFAULT_SURFACING_MIN_AGE_TURNS = 3


# Definite-noun-phrase pattern — "the X", "the X Y" where X (and Y)
# are lowercase content words. Captures memoir anchors like "the
# train ride", "the church choir", "the old farmhouse".
#
# The regex over-captures by design (up to 3 tokens, greedy) and we
# trim non-noun trailing tokens in `_trim_dnp_tail` after extraction.
# This is more robust than a perfect regex because English NPs end at
# verbs, prepositions, conjunctions, and adverbs — easier to enumerate
# the stop tokens than to enumerate every legal NP shape.
_DEFINITE_NP_RX = re.compile(
    r"\bthe\s+([a-z][a-z'\-]+(?:\s+[a-z][a-z'\-]+){0,2})\b",
    re.IGNORECASE,
)


# Trailing tokens that signal the noun phrase has ended. When the
# greedy DNP regex captures these as part of the phrase, they get
# stripped. Covers copulas, common preps, conjunctions, and
# locative/temporal adverbs that typically follow an NP.
_DNP_TAIL_STOPWORDS = frozenset({
    # Copulas / state verbs
    "was", "were", "is", "are", "be", "been", "being",
    "seemed", "looked", "became", "got", "felt", "sounded",
    "had", "has", "have", "did", "do", "does",
    # Prepositions
    "in", "at", "on", "of", "to", "from", "by", "with",
    "for", "about", "into", "onto", "over", "under",
    "near", "behind", "before", "after", "during",
    "through", "around", "past", "across",
    # Conjunctions
    "and", "or", "but", "so", "if", "then", "because",
    # Locative / temporal adverbs that frequently follow an NP
    "back", "here", "there", "now", "later", "earlier",
    "again", "always", "never", "still",
    # Determiners that signal a new phrase starting
    "a", "an", "another",
})


def _trim_dnp_tail(phrase: str) -> str:
    """Trim trailing stopword tokens from a captured DNP. Returns the
    phrase minus any trailing tokens in `_DNP_TAIL_STOPWORDS`. The first
    token (the noun head) is always preserved even if it's in the
    stopword set — we only trim from the back end.
    """
    if not phrase:
        return ""
    tokens = phrase.split()
    while len(tokens) > 1 and tokens[-1].lower() in _DNP_TAIL_STOPWORDS:
        tokens.pop()
    return " ".join(tokens)


# Event-shape nouns to bias categorization. Coarse list.
_EVENT_NOUNS = frozenset({
    "ride", "trip", "journey", "voyage", "march", "walk", "drive",
    "wedding", "funeral", "ceremony", "service", "war", "battle",
    "fight", "argument", "accident", "fire", "flood", "storm",
    "birth", "death", "move", "graduation", "party", "dance",
    "concert", "performance", "game", "race", "election",
})


# Geographic-suffix list for place categorization.
_PLACE_SUFFIXES = (
    "ville", "burg", "town", "field", "ford", "port", "shire",
    "land", "stan", "wood", "wick",
)


# US state names + common country names — small list, coarse category
# hint. Not authoritative (operator can override; we use this only to
# classify the thread for the operator review surface).
_PLACE_NAMES = frozenset({
    # US states (subset; the rest are caught by the suffix heuristic
    # or the "in X" pattern)
    "alabama", "alaska", "arizona", "arkansas", "california",
    "colorado", "connecticut", "delaware", "florida", "georgia",
    "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas",
    "kentucky", "louisiana", "maine", "maryland", "massachusetts",
    "michigan", "minnesota", "mississippi", "missouri", "montana",
    "nebraska", "nevada", "ohio", "oklahoma", "oregon",
    "pennsylvania", "tennessee", "texas", "utah", "vermont",
    "virginia", "washington", "wisconsin", "wyoming",
    "north dakota", "south dakota", "new york", "new jersey",
    "new mexico", "new hampshire", "rhode island", "west virginia",
    # Common countries that appear in older-adult memoir
    "germany", "france", "england", "scotland", "ireland", "italy",
    "spain", "japan", "china", "korea", "vietnam", "canada",
    "mexico", "russia", "poland", "norway", "sweden",
})


# Year-shape regex (1800-2099 covers narrator memoir range).
_YEAR_RX = re.compile(r"\b(?:18|19|20)\d{2}\b")


# Age-phrase regex.
_AGE_RX = re.compile(
    r"\b(?:when\s+I\s+was|at\s+age|age|aged)\s+\w+|"
    r"\b\d{1,2}\s+years?\s+old\b",
    re.IGNORECASE,
)


# Decade words for time_period categorization.
_DECADE_WORDS = frozenset({
    "twenties", "thirties", "forties", "fifties", "sixties",
    "seventies", "eighties", "nineties", "childhood", "teenage",
    "teens",
})


# ─────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ThreadCandidate:
    """Extraction result — a single anchorable thread from a narrator
    turn. Pre-persistence; caller dedupes + writes via bank_new_threads."""
    anchor: str
    excerpt: str
    category: str  # 'person' | 'place' | 'event' | 'object' | 'time_period'
    source_turn_index: int


# ─────────────────────────────────────────────────────────────────────
# Extraction
# ─────────────────────────────────────────────────────────────────────


def _categorize_anchor(anchor: str, narrator_text: str) -> str:
    """Best-effort category heuristic. See module docstring §Categories."""
    if not anchor:
        return ""
    anchor_lower = anchor.lower()

    # time_period — anchor itself is a year, decade word, or age phrase
    if _YEAR_RX.search(anchor):
        return "time_period"
    if any(w in anchor_lower for w in _DECADE_WORDS):
        return "time_period"
    if _AGE_RX.search(anchor):
        return "time_period"

    # person — kinship surface form ("Your father") or kinship word
    kinship_singular = anchor.lower().replace("your ", "")
    if kinship_singular in _KINSHIP_CANON or anchor_lower.startswith("your "):
        return "person"

    # place — name in curated list or suffix match
    if anchor_lower in _PLACE_NAMES:
        return "place"
    if any(anchor_lower.endswith(suf) for suf in _PLACE_SUFFIXES):
        return "place"
    # place — proper-noun preceded by location preposition in source text
    for prep in ("in ", "at ", "to ", "from ", "near "):
        if (prep + anchor.lower()) in narrator_text.lower() or \
                (prep + anchor) in narrator_text:
            return "place"

    # event — definite-noun-phrase containing event-shape noun
    tokens = anchor_lower.split()
    if any(t in _EVENT_NOUNS for t in tokens):
        return "event"

    # If anchor starts with lowercase, it's a definite-noun-phrase
    # extraction — default to object
    if anchor and anchor[0].islower():
        return "object"

    # Otherwise — proper-noun without place/person/event signal.
    # Default to place (most common memoir anchor category).
    return "place"


def _extract_excerpt(narrator_text: str, anchor: str) -> str:
    """Return a 1-2 sentence excerpt containing `anchor`, capped at
    240 chars. Walks sentences in order; first containing match wins.
    Empty when not found."""
    if not narrator_text or not anchor:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", narrator_text.strip())
    anchor_lower = anchor.lower()
    for sentence in sentences:
        if anchor_lower in sentence.lower():
            return sentence.strip()[:240]
    # Fallback: return the first sentence (anchor may have been case-
    # normalized away from a literal match — better some excerpt than
    # none for the operator review surface).
    first, _ = _split_first_sentence(narrator_text)
    return first.strip()[:240]


def extract_thread_candidates(
    narrator_text: str,
    source_turn_index: int = 0,
) -> List[ThreadCandidate]:
    """Pure extraction (no DB). Returns up to 8 anchorable thread
    candidates from a single narrator turn, ordered by appearance.

    Extracts from three sources, deduped against each other:
      1. Proper-noun phrases (places, names) — via _PROPER_NOUN_RX
         + trailing-blocklist trim
      2. Kinship anchors ("my dad", "my grandmother") — via
         _KINSHIP_ANCHOR_RX with possessive flip
      3. Definite noun phrases ("the train ride", "the church
         choir") — via _DEFINITE_NP_RX

    Each candidate carries an excerpt + heuristic category. Caller
    persists via bank_new_threads (which also dedupes against
    existing OPEN threads in the same session).
    """
    if not narrator_text or not narrator_text.strip():
        return []

    seen_anchors_lower: Set[str] = set()
    candidates: List[ThreadCandidate] = []

    # 1. Proper-noun phrases (mid-sentence then sentence-start). Reuse
    #    the existing regex + trim pipeline from lori_reflection.
    propnoun_anchors: List[str] = []
    for m in _PROPER_NOUN_RX.finditer(narrator_text):
        phrase = _trim_trailing_blocklist(m.group(0).strip())
        if phrase:
            propnoun_anchors.append(phrase)
    for m in _PROPER_NOUN_AT_START_RX.finditer(narrator_text):
        phrase = _trim_trailing_blocklist(m.group("np").strip())
        if phrase:
            propnoun_anchors.append(phrase)
    for anchor in propnoun_anchors:
        key = anchor.lower()
        if key in seen_anchors_lower:
            continue
        # Reject single tokens that are entirely on the blocklist
        # (sentence-start "He", "My", etc. that slipped through the
        # regex's lookbehind).
        tokens = anchor.split()
        if all(t in _PROPER_NOUN_BLOCKLIST for t in tokens):
            continue
        seen_anchors_lower.add(key)
        candidates.append(ThreadCandidate(
            anchor=anchor,
            excerpt=_extract_excerpt(narrator_text, anchor),
            category=_categorize_anchor(anchor, narrator_text),
            source_turn_index=source_turn_index,
        ))

    # 2. Kinship anchors with possessive flip ("my dad" → "Your father")
    for m in _KINSHIP_ANCHOR_RX.finditer(narrator_text):
        noun = m.group("noun").lower()
        canonical = _KINSHIP_CANON.get(noun, noun)
        anchor = f"your {canonical}"
        key = anchor.lower()
        if key in seen_anchors_lower:
            continue
        seen_anchors_lower.add(key)
        candidates.append(ThreadCandidate(
            anchor=anchor,
            excerpt=_extract_excerpt(narrator_text, noun),
            category="person",
            source_turn_index=source_turn_index,
        ))

    # 3. Definite-noun-phrase anchors ("the train ride", etc.)
    for m in _DEFINITE_NP_RX.finditer(narrator_text):
        phrase_inner = _trim_dnp_tail(m.group(1).strip())
        if not phrase_inner:
            continue
        # Skip kinship terms (already captured above with possessive flip)
        first_word = phrase_inner.split()[0].lower()
        if first_word in _KINSHIP_CANON:
            continue
        # Build the bare-form anchor ("the train ride" → "the train ride")
        anchor = f"the {phrase_inner}".lower()
        if anchor in seen_anchors_lower:
            continue
        # Also dedupe against the inner phrase appearing as a
        # propnoun-extracted entity (rare but possible if the
        # narrator capitalized something mid-DNP).
        if phrase_inner.lower() in seen_anchors_lower:
            continue
        seen_anchors_lower.add(anchor)
        candidates.append(ThreadCandidate(
            anchor=anchor,
            excerpt=_extract_excerpt(narrator_text, phrase_inner),
            category=_categorize_anchor(anchor, narrator_text),
            source_turn_index=source_turn_index,
        ))

    # Cap at 8 — protects against pathological inputs that name 20+
    # anchors. Real chapters don't reasonably introduce more than
    # 8 distinct trackable threads in one turn.
    return candidates[:8]


# ─────────────────────────────────────────────────────────────────────
# Persistence
# ─────────────────────────────────────────────────────────────────────


def bank_new_threads(
    session_id: str,
    candidates: List[ThreadCandidate],
    tenant_id: str = "default",
) -> List[str]:
    """Persist non-duplicate candidates. Returns the list of new
    thread ids. Skips any candidate whose anchor already has an OPEN
    thread in this session (dedupe is per-session, case-insensitive
    via db.interview_thread_anchor_open_exists).
    """
    if not session_id or not candidates:
        return []
    new_ids: List[str] = []
    for c in candidates:
        if not c.anchor:
            continue
        try:
            if db.interview_thread_anchor_open_exists(session_id, c.anchor):
                continue
            new_id = db.interview_thread_create(
                session_id=session_id,
                thread_anchor=c.anchor,
                source_turn_index=int(c.source_turn_index),
                source_excerpt=c.excerpt or "",
                category=c.category or "",
                tenant_id=tenant_id or "default",
            )
            new_ids.append(new_id)
        except Exception:
            # Best-effort — never let thread bank breakage cascade into
            # the chat turn. The compose path runs regardless of bank
            # availability.
            continue
    return new_ids


# ─────────────────────────────────────────────────────────────────────
# Surfacing logic
# ─────────────────────────────────────────────────────────────────────


def _has_closing_marker(narrator_text: str) -> bool:
    if not narrator_text:
        return False
    low = narrator_text.lower()
    return any(m in low for m in CLOSING_MARKERS)


def select_surfacing_target(
    session_id: str,
    current_turn_index: int,
    momentum_mode: str = "normal",
    narrator_text: str = "",
    min_age_turns: int = DEFAULT_SURFACING_MIN_AGE_TURNS,
) -> Optional[Dict[str, Any]]:
    """Pick the thread (if any) Lori should surface this turn.

    Returns the thread row dict or None. Surfacing is suppressed when:
      - momentum_mode == "story" (don't interrupt a chapter)
      - the narrator turn has no closing marker AND momentum != "normal"
        (don't pre-empt an emerging chapter)
      - no open thread is old enough
      - all open threads have been declined

    When narrator_text contains a closing marker, surfacing eligibility
    relaxes — even in emerging mode, the narrator signaled they're done
    with the current thread.
    """
    if momentum_mode == "story":
        return None
    if not session_id:
        return None

    # Emerging mode without a closing marker → wait. The narrator may
    # be building toward a chapter we shouldn't deflect.
    if momentum_mode == "emerging" and not _has_closing_marker(narrator_text or ""):
        return None

    try:
        open_threads = db.interview_thread_list_for_session(
            session_id, status="open",
        )
    except Exception:
        return None

    # Filter by age. Oldest eligible wins (lowest source_turn_index).
    eligible: List[Dict[str, Any]] = []
    for t in open_threads:
        source_turn = int(t.get("source_turn_index") or 0)
        if (current_turn_index - source_turn) >= min_age_turns:
            eligible.append(t)
    if not eligible:
        return None
    eligible.sort(key=lambda t: int(t.get("source_turn_index") or 0))
    return eligible[0]


# Connecting phrase rotation. Round-robin per surfacing — caller
# bumps the counter. Five phrases is enough to avoid stale-feeling
# repeats across a session; "I keep thinking about" tracks the WO's
# example surfacing line.
_CONNECTING_PHRASES = (
    "I keep thinking about it.",
    "It stayed with me.",
    "I noticed that.",
    "I've been holding onto that one.",
    "I want to come back to it.",
)


def build_surfacing_text(
    thread: Dict[str, Any],
    open_question: str = "What was that like?",
    connecting_phrase_index: int = 0,
) -> str:
    """Build the surfacing turn per the WO template:

        "Earlier you mentioned {anchor}. {connecting_phrase} {open_question}"

    The connecting_phrase comes from a small bank, rotated per
    session (caller bumps the counter). The open_question defaults
    to a Layer 1 (open recall) question — caller may override with
    a context-specific phrasing.
    """
    if not thread or not thread.get("thread_anchor"):
        return ""
    anchor = str(thread.get("thread_anchor") or "").strip()
    idx = max(0, connecting_phrase_index) % len(_CONNECTING_PHRASES)
    connector = _CONNECTING_PHRASES[idx]
    question = (open_question or "What was that like?").strip()
    return f"Earlier you mentioned {anchor}. {connector} {question}"


# ─────────────────────────────────────────────────────────────────────
# Response evaluation
# ─────────────────────────────────────────────────────────────────────


def _is_declination(narrator_text: str) -> bool:
    if not narrator_text:
        return True  # silence after a surface = declination
    low = narrator_text.lower()
    return any(p in low for p in DECLINATION_PATTERNS)


def evaluate_response_to_surfaced_thread(
    narrator_text: str,
    thread: Optional[Dict[str, Any]] = None,  # reserved for future use
) -> str:
    """Classify the narrator's response to a previously-surfaced
    thread. Returns one of "resolved" / "declined" / "unclear".

    Caller decides what to do — typically calls db.interview_thread_
    set_status with the matching status + the appropriate timestamp.

    Heuristic:
      - declination phrase OR < 8 words OR empty → "declined"
      - >= 30 words → "resolved"
      - otherwise → "unclear" (caller leaves status as 'surfaced'
        and re-evaluates on the next turn)
    """
    txt = (narrator_text or "").strip()
    if not txt:
        return "declined"
    if _is_declination(txt):
        return "declined"
    wc = len(txt.split())
    if wc < 8:
        return "declined"
    if wc >= _SUBSTANTIVE_WORD_COUNT:
        return "resolved"
    return "unclear"


__all__ = [
    "ThreadCandidate",
    "CLOSING_MARKERS",
    "DECLINATION_PATTERNS",
    "DEFAULT_SURFACING_MIN_AGE_TURNS",
    "extract_thread_candidates",
    "bank_new_threads",
    "select_surfacing_target",
    "build_surfacing_text",
    "evaluate_response_to_surfaced_thread",
]
