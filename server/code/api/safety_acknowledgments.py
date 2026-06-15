"""WO-LORI-SAFETY-LLM-CLASSIFIER-01 — past-tense acknowledgment bank.

═══════════════════════════════════════════════════════════════════════
  WHAT THIS IS
═══════════════════════════════════════════════════════════════════════

A deterministic phrase bank used by the past_tense_acknowledge route.
When the classifier identifies past-tense self-directed memoir ideation
("After Mom died in '78, there was a year I didn't want to go on"), Lori
emits a SHORT acknowledgment from this bank — no LLM, no follow-up
question — and the chapter continues at the narrator's pace.

The narrator-side principle: brief acknowledgment respects what was
shared without escalating a 48-year-old memory into a present-day
crisis dispatch. Lori bears witness; she does not interrogate the
chapter further or ask "how does that feel now?". The operator gets a
post-session flag for awareness.

═══════════════════════════════════════════════════════════════════════
  INVARIANTS (locked, tested)
═══════════════════════════════════════════════════════════════════════

1. The bank is small (4 phrases, cap at 6). Larger banks risk the
   acknowledgments themselves becoming a tell.
2. Selection is deterministic round-robin per session — no random
   choice, no LLM. Same session always produces phrases in the same
   order.
3. No two consecutive acknowledgments in the same session repeat
   verbatim. (Trivially satisfied by round-robin with bank size ≥ 2.)
4. ZERO LLM calls in this module. Code-level invariant. The past-
   tense path NEVER composes a follow-up question.

═══════════════════════════════════════════════════════════════════════
  STATE MODEL
═══════════════════════════════════════════════════════════════════════

State is per-conversation-id only. The caller (chat_ws.py) holds the
counter and passes it in; this module is a pure function plus a
constant phrase list. No global state, no DB writes, no I/O.

When a session reaches the end of the bank and wraps around (turn N+1
after N phrases used), the cycle restarts at index 0.
"""
from __future__ import annotations

from typing import Tuple


# WO-LORI-SAFETY-LLM-CLASSIFIER-01 spec §3 — the bank.
#
# Wordsmith principles applied:
#   - SHORT (≤ 6 words). Length communicates "I heard you, the
#     chapter continues" rather than "let's process this."
#   - PAST-DIRECTED ("a hard year", "got through it"). Acknowledges
#     the past without dragging it into the present.
#   - WITNESS, NOT INTERROGATOR. None of these phrases invite
#     elaboration. None ask a question.
#   - NO CLINICAL VOCABULARY ("trauma", "process", "feel").
#   - NO PROMISE OF SUPPORT ("I'm here for you"). That tonality
#     belongs on the acute path with the 988 frame.
PAST_TENSE_ACKNOWLEDGMENTS: Tuple[str, ...] = (
    "That sounds like a hard year.",
    "That's a heavy thing to carry.",
    "Thank you for telling me that.",
    "I'm glad you got through it.",
)


def select_past_tense_acknowledgment(
    session_acknowledgment_count: int,
) -> str:
    """Return the next acknowledgment for this session.

    Deterministic round-robin. `session_acknowledgment_count` is the
    number of past_tense_acknowledge routes that have already fired
    in this conversation (zero-indexed: the first call passes 0, the
    second passes 1, etc.). Caller persists the counter per session.

    Wraps cleanly at the end of the bank.

    Invariants:
      - Pure function. No I/O. No LLM call. No randomness.
      - Same input → same output (deterministic for testing).
      - Never returns the same phrase twice in a row within a single
        session, because round-robin over N≥2 phrases never repeats.
    """
    if not isinstance(session_acknowledgment_count, int) or \
            session_acknowledgment_count < 0:
        # Defensive: clamp negative or non-int input to 0 — produces
        # the first phrase. Better than raising and failing the
        # narrator turn.
        session_acknowledgment_count = 0
    idx = session_acknowledgment_count % len(PAST_TENSE_ACKNOWLEDGMENTS)
    return PAST_TENSE_ACKNOWLEDGMENTS[idx]


__all__ = [
    "PAST_TENSE_ACKNOWLEDGMENTS",
    "select_past_tense_acknowledgment",
]
