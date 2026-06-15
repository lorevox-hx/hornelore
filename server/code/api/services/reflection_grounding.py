"""WO-LORI-STORY-FIRST-PHASE-1-01 (2026-06-14) — reflection grounding validator.

═══════════════════════════════════════════════════════════════════════
  WHAT THIS IS
═══════════════════════════════════════════════════════════════════════

A composition-time validator that requires Lori's first 1-2 sentences
to ground in concrete content tokens from the most recent narrator
turn. The validator rejects generic empathy openers ("That sounds
difficult", "I can imagine") and returns a structured failure label
the regeneration loop in lori_communication_control consumes.

Per WO §1 — every normal Lori turn must begin with reflection of
narrator material before any continuation. The existing shallow check
("does the response contain any acknowledging phrase") is replaced by
this structural check (does the reflection ground in concrete
narrator content tokens).

═══════════════════════════════════════════════════════════════════════
  HOW GROUNDING IS DETECTED
═══════════════════════════════════════════════════════════════════════

Re-uses the existing token machinery in services.lori_reflection:

  - _content_tokens(text)      → set of content tokens (3+ chars, non-
                                  stopword, kinship-canonicalized, stemmed)
  - extract_concrete_anchor()  → most distinctive proper-noun phrase from
                                  narrator text (for the fallback template)
  - _split_first_sentence()    → sentence boundary

The check is lexical overlap with kinship canonicalization and
conservative stemming. The spec calls for embedding-based paraphrase
similarity; that's Phase 2+ work. Phase 1 ships with the lexical
approach because it's verifiable, fast, and good enough for the
common case (kinship/place/event re-mentions).

═══════════════════════════════════════════════════════════════════════
  FORBIDDEN GENERIC OPENERS
═══════════════════════════════════════════════════════════════════════

Bank of phrases that fail grounding regardless of token overlap.
These are the empathy stand-ins Lori produces when she doesn't know
what to say — exactly what reflection grounding is meant to catch.

  - "That sounds difficult."
  - "I can imagine."
  - "That must have been..."
  - "Thank you for sharing."
  - "I'm so sorry."
  - "That's so meaningful."

Detection is substring + leading-position. A response that opens with
"Mary, that sounds difficult" passes IF "Mary" was a narrator token
(grounding wins via content token) — but the validator still records
the forbidden phrase so the regeneration loop can flag it for a
follow-up prompt nudge.

═══════════════════════════════════════════════════════════════════════
  PUBLIC API
═══════════════════════════════════════════════════════════════════════

  check_reflection_grounding(lori_text, narrator_text) → GroundingResult
      Run the full check. Returns dataclass with passed, anchor_overlap,
      forbidden_phrase, and a structured failure_reason string.

  is_forbidden_empathy_opener(text) → bool
      Convenience: just the forbidden-phrase check.

  build_fallback_reflection(narrator_text, continuation) → str
      Deterministic fallback when regeneration exhausts. Uses
      extract_concrete_anchor() + a pause-token bank.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Set

from .lori_reflection import (
    _content_tokens,
    _split_first_sentence,
    extract_concrete_anchor,
)


# WO-LORI-STORY-FIRST-PHASE-1-01 §1 forbidden generic empathy openers.
# Compiled as a lowercase-matched set so we can also test substrings
# at sentence-start.
_FORBIDDEN_OPENERS = (
    "that sounds difficult",
    "that sounds hard",
    "that sounds heavy",
    "that sounds painful",
    "that sounds tough",
    "i can imagine",
    "i can't imagine",
    "i cannot imagine",
    "that must have been",
    "that must be",
    "thank you for sharing",
    "thank you for telling me",
    "i'm so sorry",
    "i am so sorry",
    "that's so meaningful",
    "that is so meaningful",
    "that's very meaningful",
    "what a meaningful",
    "that's beautiful",
    "that is beautiful",
    "how meaningful",
    "how lovely",
    "how wonderful",
)


# Deterministic fallback pause tokens — short, calm, never invent
# narrator content. Round-robin per session is the caller's
# responsibility (this module is stateless).
_FALLBACK_PAUSE_TOKENS = (
    "That stays with me.",
    "Mm.",
    "That's vivid.",
    "I'm listening.",
)


@dataclass(frozen=True)
class GroundingResult:
    """Reflection grounding check result.

    passed:              True iff the response has content-token overlap
                          AND no forbidden empathy opener
    anchor_overlap:      List of narrator tokens echoed in Lori's first
                          1-2 sentences (after canonicalization + stemming)
    forbidden_phrase:    The matched forbidden opener, or "" when none
    failure_reason:      Structured label for the regeneration loop:
                          "" (passed), "no_anchor_overlap",
                          "forbidden_empathy_opener", or both joined
                          by "+" when both fail
    """
    passed: bool
    anchor_overlap: tuple
    forbidden_phrase: str
    failure_reason: str


def extract_narrator_content_tokens(narrator_text: str) -> Set[str]:
    """Public wrapper around the private _content_tokens() helper.

    Used by callers that want to inspect the narrator token set
    directly (story_momentum and thread_bank both consume this).
    Stable across module reloads because the underlying helper is
    pure.
    """
    return _content_tokens(narrator_text or "")


def is_forbidden_empathy_opener(text: str) -> str:
    """Return the matched forbidden opener phrase, or empty string.

    Substring match against `_FORBIDDEN_OPENERS`, anchored to the
    first ~80 chars of `text` (lowercased) so a later forbidden
    phrase deep in a long response doesn't trigger. Reflection-
    grounding is about the OPENING; later sentences are out of
    scope.
    """
    if not text:
        return ""
    head = text.strip()[:120].lower()
    for phrase in _FORBIDDEN_OPENERS:
        if phrase in head:
            return phrase
    return ""


def check_reflection_grounding(
    lori_text: str,
    narrator_text: str,
) -> GroundingResult:
    """WO-LORI-STORY-FIRST-PHASE-1-01 §1 — reflection grounding check.

    Inputs:
      lori_text:     Lori's composed response (full text)
      narrator_text: the narrator's most recent turn (full text)

    Returns a GroundingResult. `passed` is True iff:
      1. Lori's first 1-2 sentences contain at least one content
         token from narrator_text (after canonicalization + stem),
         AND
      2. The opening (~120 chars) does NOT contain any phrase from
         _FORBIDDEN_OPENERS.

    When narrator_text is trivial (< 4 content tokens, e.g. "yes",
    "ok"), the grounding requirement is waived — Lori cannot ground
    in nothing. forbidden-phrase check still runs.

    Pure function; no LLM, no DB, no I/O.
    """
    n_tokens = _content_tokens(narrator_text or "")
    if len(n_tokens) < 4:
        # Trivial narrator: waive the anchor-overlap requirement, but
        # still check for forbidden empathy openers.
        forbidden = is_forbidden_empathy_opener(lori_text or "")
        passed = not forbidden
        return GroundingResult(
            passed=passed,
            anchor_overlap=tuple(),
            forbidden_phrase=forbidden,
            failure_reason="forbidden_empathy_opener" if forbidden else "",
        )

    # Extract Lori's first 1-2 sentences for the anchor check.
    first_sentence, rest = _split_first_sentence(lori_text or "")
    # If the first sentence is very short (< 4 words), include the
    # second sentence too — Lori may have opened with "Mm." and put
    # the actual reflection in sentence 2.
    if first_sentence and len(first_sentence.split()) < 4 and rest:
        second_sentence, _ = _split_first_sentence(rest)
        opening = (first_sentence + " " + second_sentence).strip()
    else:
        opening = first_sentence

    lori_tokens = _content_tokens(opening)
    overlap = n_tokens & lori_tokens

    forbidden = is_forbidden_empathy_opener(lori_text or "")
    has_anchor = len(overlap) >= 1
    passed = has_anchor and not forbidden

    failure_parts: List[str] = []
    if not has_anchor:
        failure_parts.append("no_anchor_overlap")
    if forbidden:
        failure_parts.append("forbidden_empathy_opener")

    return GroundingResult(
        passed=passed,
        anchor_overlap=tuple(sorted(overlap)),
        forbidden_phrase=forbidden,
        failure_reason="+".join(failure_parts),
    )


def build_fallback_reflection(
    narrator_text: str,
    pause_token_index: int = 0,
    continuation: str = "",
) -> str:
    """WO-LORI-STORY-FIRST-PHASE-1-01 §1 deterministic fallback.

    Used by the regeneration loop when 2 LLM regenerations both fail
    the grounding check. Builds a short, calm reflection that
    structurally cannot fail grounding — the anchor comes directly
    from the narrator text via extract_concrete_anchor(), and the
    pause token comes from a fixed bank.

    Output shape:
      "{anchor}. {pause_token} {continuation}"

    When extract_concrete_anchor returns None (truly trivial
    narrator), returns just "{pause_token} {continuation}". The
    continuation is included as-is when supplied; callers usually
    drop it because the regen budget is already exhausted.

    `pause_token_index` is for round-robin from the caller. Defaults
    to 0; caller bumps modulo bank length.
    """
    anchor = extract_concrete_anchor(narrator_text or "")
    pause_idx = max(0, pause_token_index) % len(_FALLBACK_PAUSE_TOKENS)
    pause = _FALLBACK_PAUSE_TOKENS[pause_idx]
    cont = (continuation or "").strip()
    if anchor:
        head = f"{anchor}. {pause}"
    else:
        head = pause
    if cont:
        return f"{head} {cont}".strip()
    return head


__all__ = [
    "GroundingResult",
    "check_reflection_grounding",
    "is_forbidden_empathy_opener",
    "build_fallback_reflection",
    "extract_narrator_content_tokens",
]
