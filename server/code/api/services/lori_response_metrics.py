"""WO-LORI-ACTIVE-LISTENING-01 Phase 3 — Lori-response eval metrics.

Pure-function module. Given a Lori turn (and optionally the prior
narrator turn), compute six measurable metrics:

  question_count                    Per Lori turn. Target ≤ 1 except
                                    in summary turns (memory-echo,
                                    correction). Counts '?' marks
                                    (excludes question marks inside
                                    quoted strings).
  nested_question_count             Number of compound / and-stacked /
                                    or-stacked question structures.
                                    Target = 0.
  word_count                        Total word count. Target ≤ 90 for
                                    ordinary turns, ≤ 55 by spec.
  direct_answer_first               Boolean. True if Lori's first
                                    sentence answers a direct
                                    question the narrator just asked.
                                    Required to be True if
                                    user_turn_had_direct_question.
  active_reflection_present         Boolean. True if the first 1-2
                                    sentences echo a specific anchor
                                    from the prior narrator turn
                                    (heuristic: shared 4+ char noun
                                    or phrase).
  menu_offer_count                  Count of "or we could / would you
                                    rather / which path / would you
                                    like to ... or ..." patterns.
                                    Target = 0.

Returned dict shape:
  {
    question_count: int,
    nested_question_count: int,
    word_count: int,
    direct_answer_first: bool,
    active_reflection_present: bool,
    asks_question_after_user_question: bool,
    menu_offer_count: int,
    user_turn_had_direct_question: bool,  # input echo, useful in reports
    pass_question_count: bool,            # ≤ 1
    pass_word_count: bool,                # ≤ 90
    pass_no_nested: bool,                 # nested == 0
    pass_no_menu_offer: bool,             # menu_offer == 0
    pass_direct_answer: bool,             # direct_answer satisfied
    pass_overall: bool,                   # all pass_* are True
  }

LAW: pure stdlib. No db, no LLM, no IO. Suitable for use inside any
eval harness without touching the runtime stack.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Set


# ── Patterns ──────────────────────────────────────────────────────────────
#
# COMPOUND_QUESTION_RX matches "?...and/or/also/plus/maybe/perhaps...?"
# (a question linked to another question via a connector). Also catches
# the common compound "What is X, AND how does Y?" structure where
# the connector sits inside a single ?-terminated sentence.
#
# Two variants:
#   _COMPOUND_TWO_QUESTIONS_RX  — two ?-marks linked by connector
#   _COMPOUND_AND_LINKED_RX     — single ?-mark with "X, and Y" structure
#                                 where Y starts with a wh-word
_COMPOUND_TWO_QUESTIONS_RX = re.compile(
    r"\?[^?]*\b(and|or|also|plus|maybe|perhaps)\b[^?]*\?",
    re.IGNORECASE,
)

# Compound single-? form: "What is X, and how is Y?" — connector
# joins a wh-clause to a wh-clause inside one question. Wh-stem is
# what / when / where / who / why / how / which / did.
_COMPOUND_AND_LINKED_RX = re.compile(
    r"\b(what|when|where|who|why|how|which|did|do|does|is|are|was|were)\b"
    r"[^.?!]{0,80}[,;]\s+(and|or|also|plus)\s+"
    r"\b(what|when|where|who|why|how|which|did|do|does|is|are|was|were)\b",
    re.IGNORECASE,
)

# Menu-offer patterns (per the spec — refined to avoid false positives
# on legitimate "would you like to" structures).
_MENU_OFFER_RX = re.compile(
    r"\b(would you like to .{0,80}\bor\b)|"
    r"\b(would you rather)\b|"
    r"\b(which path)\b|"
    r"\b(or we could)\b|"
    r"\b(or maybe we could)\b|"
    r"\b(or perhaps you'?d rather)\b",
    re.IGNORECASE,
)


# ── Helpers ───────────────────────────────────────────────────────────────

def _strip_quoted_questions(text: str) -> str:
    """Remove quoted ?-marks so they don't inflate question_count.
    Conservative: strips text inside "..." and '...' pairs."""
    # Double-quoted segments
    text = re.sub(r'"[^"]*"', '""', text)
    # Single-quoted segments (be careful with apostrophes — only fold
    # when the open-quote sits after whitespace or start)
    text = re.sub(r"(?:^|\s)'[^']*'", "''", text)
    return text


def _word_count(text: str) -> int:
    """Word count. Splits on whitespace; punctuation isn't a word."""
    if not text:
        return 0
    # Strip standalone punctuation tokens
    cleaned = re.sub(r"[^\w\s'-]", " ", text)
    tokens = [t for t in cleaned.split() if t]
    return len(tokens)


def _question_count(text: str) -> int:
    """Count '?' marks in text, excluding those inside quoted strings."""
    if not text:
        return 0
    return _strip_quoted_questions(text).count("?")


def _nested_question_count(text: str) -> int:
    """Count compound / nested question structures.

    Two patterns count toward nested:
      1. Two ?-marks linked by and/or/also/plus
      2. Single ?-mark with wh-clause , and/or wh-clause structure
    Returns the SUM of distinct compound matches.
    """
    if not text:
        return 0
    n = 0
    for m in _COMPOUND_TWO_QUESTIONS_RX.finditer(text):
        n += 1
    for m in _COMPOUND_AND_LINKED_RX.finditer(text):
        n += 1
    return n


def _menu_offer_count(text: str) -> int:
    """Count menu-offer patterns."""
    if not text:
        return 0
    return len(_MENU_OFFER_RX.findall(text))


def _user_turn_had_direct_question(user_text: Optional[str]) -> bool:
    """Heuristic: user_text contains a '?' OR starts with a wh-word
    followed by a verb-like structure."""
    if not user_text:
        return False
    if "?" in user_text:
        return True
    # Wh-word at start (case-insensitive) followed by content
    if re.match(
        r"^\s*(what|when|where|who|why|how|which|do|does|did|is|are|was|were|can|could|would|should)\b",
        user_text,
        re.IGNORECASE,
    ):
        return True
    return False


def _first_sentence(text: str) -> str:
    """Return Lori's first sentence (split on . ? !)."""
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)
    return parts[0] if parts else ""


def _looks_like_answer(first_sentence: str) -> bool:
    """Heuristic: does the first sentence look like an answer (not a
    question or a deflection)?

    True if: first sentence is declarative (no '?'), AND doesn't
    open with "Let me ask" / "I'd love to know" / similar deflection.
    """
    if not first_sentence:
        return False
    if "?" in first_sentence:
        return False
    deflection_starts = (
        "let me ask",
        "i'd love to know",
        "i would love to know",
        "tell me about",
        "could you tell me",
    )
    lower = first_sentence.strip().lower()
    for d in deflection_starts:
        if lower.startswith(d):
            return False
    return True


def _direct_answer_first(assistant_text: str, user_text: Optional[str]) -> bool:
    """If the user asked a direct question, the assistant's first
    sentence must look like an answer (declarative). If the user
    didn't ask a question, return True (no constraint applies)."""
    if not _user_turn_had_direct_question(user_text):
        return True
    return _looks_like_answer(_first_sentence(assistant_text))


def _content_words(text: str, min_len: int = 4) -> Set[str]:
    """Lowercased content words of length ≥ min_len, with common
    function words filtered out. Used by active_reflection heuristic."""
    if not text:
        return set()
    _STOPWORDS = {
        "this", "that", "with", "from", "have", "were", "they", "them",
        "than", "then", "what", "when", "where", "which", "would",
        "could", "should", "about", "after", "again", "into", "your",
        "yours", "their", "there", "here", "just", "some", "very",
        "much", "such", "more", "most", "many", "other", "another",
        "those", "these", "being", "been", "make", "made", "take",
        "took", "going", "still", "came", "come", "went", "know",
        "knew", "known", "feel", "felt", "tell", "told", "said",
        "say", "says", "looked", "looking", "thing", "things",
    }
    words = re.findall(r"[a-zA-Z][a-zA-Z'-]*", text.lower())
    return {w for w in words if len(w) >= min_len and w not in _STOPWORDS}


def _active_reflection_present(
    assistant_text: str, user_text: Optional[str]
) -> bool:
    """Heuristic: does Lori's first 1-2 sentences echo a specific
    anchor from the prior narrator turn?

    Implementation: take Lori's first 30 words. Compute the set of
    content words ≥ 4 chars in BOTH Lori's first 30 words and the
    user's text. If the intersection is non-empty, we count it as
    a reflection (Lori is echoing at least one specific narrator term).

    Spec floor: trivial responses (< 5 content words from the user)
    are exempt — Lori shouldn't echo "yes" or "I think so" because
    that sounds robotic. Returns True for trivial-user responses.
    """
    if not assistant_text or not user_text:
        return False if user_text else True
    user_content = _content_words(user_text)
    if len(user_content) < 5:
        # Trivial-response exception: don't require reflection on
        # short user replies like "yes", "no", "I think so"
        return True
    first_chunk = " ".join(assistant_text.split()[:30])
    lori_content = _content_words(first_chunk)
    return bool(user_content & lori_content)


def _asks_question_after_user_question(
    assistant_text: str, user_text: Optional[str]
) -> bool:
    """Did Lori ask a follow-up question? Allowed only if she
    answered the user's question first."""
    if not _user_turn_had_direct_question(user_text):
        # User didn't ask anything; this metric doesn't apply
        return False
    return _question_count(assistant_text) > 0


# ── Public scorer ─────────────────────────────────────────────────────────

def score_lori_turn(
    assistant_text: str,
    user_text: Optional[str] = None,
    *,
    word_cap: int = 90,
) -> Dict[str, Any]:
    """Score one Lori turn against the WO-LORI-ACTIVE-LISTENING-01
    behavior contract. Returns a dict with raw metrics + per-metric
    pass flags + an overall pass_overall.

    Args:
      assistant_text: Lori's full reply text
      user_text: the prior narrator turn (or None if not available)
      word_cap: pass threshold for word_count (default 90 per spec;
                Chris's locked target is ≤ 55 — the metric returns
                the actual count, the caller picks the cap)

    All metrics are computed from text alone — no DB, no LLM, no IO.
    """
    qc = _question_count(assistant_text)
    nqc = _nested_question_count(assistant_text)
    wc = _word_count(assistant_text)
    moc = _menu_offer_count(assistant_text)
    daf = _direct_answer_first(assistant_text, user_text)
    arp = _active_reflection_present(assistant_text, user_text)
    aqaq = _asks_question_after_user_question(assistant_text, user_text)
    user_q = _user_turn_had_direct_question(user_text)

    pass_question_count = qc <= 1
    pass_word_count = wc <= word_cap
    pass_no_nested = nqc == 0
    pass_no_menu_offer = moc == 0
    pass_direct_answer = daf  # True when no constraint OR answered first
    # asks_question_after_user_question is allowed only after answering;
    # so the failure mode is: user asked + assistant asked + didn't answer
    pass_asks_after_answer = (not aqaq) or pass_direct_answer

    pass_overall = (
        pass_question_count
        and pass_word_count
        and pass_no_nested
        and pass_no_menu_offer
        and pass_direct_answer
        and pass_asks_after_answer
    )

    return {
        "question_count": qc,
        "nested_question_count": nqc,
        "word_count": wc,
        "menu_offer_count": moc,
        "direct_answer_first": daf,
        "active_reflection_present": arp,
        "asks_question_after_user_question": aqaq,
        "user_turn_had_direct_question": user_q,
        "pass_question_count": pass_question_count,
        "pass_word_count": pass_word_count,
        "pass_no_nested": pass_no_nested,
        "pass_no_menu_offer": pass_no_menu_offer,
        "pass_direct_answer": pass_direct_answer,
        "pass_asks_after_answer": pass_asks_after_answer,
        "pass_overall": pass_overall,
    }


__all__ = [
    "score_lori_turn",
]
