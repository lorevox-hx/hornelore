"""WO-LORI-SOFTENED-RESPONSE-01 — post-safety softened-mode prompt block.

Pure-function module that builds the SOFTENED MODE directive injected
into Lori's system prompt for the N turns following a safety trigger.

Architecture rationale (per WO §1):
    The 2026-05-01 golfball-comm-control-rerun Turn 07 demonstrated
    that chat_ws.py composes a normal interview prompt even while the
    DB has interview_softened=1 from Turn 06's acute trigger. The
    LLM produced a "Can you tell me more about... and..." compound
    question that the wrapper correctly flagged as
    normal_interview_question_during_safety. The fix is composer-side:
    read the softened state at turn-start and inject this directive
    so the LLM is told what shape its output should take.

LAW-3 isolation: this module imports zero extraction-stack code.
Pure functions only. Never calls an LLM. Composes a string from a
state dict; that's it.

Public API:

    build_softened_response_directive(state) -> str
        Returns the directive block to inject. Empty string when
        state["interview_softened"] is False (no-op when not in
        softened mode).

    is_softened_active(state) -> bool
        Convenience helper for boolean checks.

    SOFTENED_WORD_LIMIT — int, used by lori_communication_control to
        override the per-style word budget when softened. 35 words is
        tighter than clear_direct's 55; presence-first responses
        should not run long.

The state dict shape matches db.get_session_softened_state()'s return:
    {
        "interview_softened": bool,
        "softened_until_turn": int,
        "turn_count": int,
    }
"""
from __future__ import annotations

from typing import Dict, Optional


# Tightened word budget for softened-mode turns (vs clear_direct 55).
# Presence-first responses should be short — long Lori answers in
# softened mode read as Lori-needs-something-from-the-narrator, which
# is exactly the wrong posture.
SOFTENED_WORD_LIMIT = 35


_SOFTENED_DIRECTIVE = """\
SOFTENED MODE — POST-SAFETY GROUND.

The previous turn surfaced distress. For this turn and the next two
turns:

- Stay warm, present, and slow.
- Lead with what they just said. Reflect ONE concrete fragment they
  used, in their own words.
- You may add ONE gentle invitation. NEVER a question demand.
  Allowed: "I'm here whenever you want to keep going."
           "Take all the time you need."
           "We can stay with this."
           "There's no rush."
  Forbidden: "Can you tell me more about X?"
             "What was that like?"
             "How did you feel when Y?"
             "Tell me about Z."
- Do NOT ask new memory probes. Do NOT advance to a new topic. Do NOT
  request specifics.
- Do NOT cite 988 or other hotlines unless this turn is itself a
  fresh acute trigger. The acute path already fired in a previous
  turn; re-quoting is performative, not protective.
- Total length: 35 words or fewer.

The narrator chose to keep talking. That choice is already an act of
trust. Receive it; don't push.\
"""


def is_softened_active(state: Optional[Dict]) -> bool:
    """Return True if the session is currently in softened mode.

    Tolerant of None / missing keys / non-bool values — we don't want
    a malformed state dict to crash the prompt path.
    """
    if not state or not isinstance(state, dict):
        return False
    return bool(state.get("interview_softened", False))


def turns_remaining(state: Optional[Dict]) -> int:
    """How many softened turns remain (including the current one).

    Returns 0 when softened is not active. Used by the Bug Panel
    banner to show "N turns remaining". The math is:
        remaining = max(0, softened_until_turn - turn_count + 1)
    where +1 accounts for the current turn being one of the softened
    turns (turn_count was incremented at turn-start).
    """
    if not is_softened_active(state):
        return 0
    until = int(state.get("softened_until_turn", 0) or 0)
    count = int(state.get("turn_count", 0) or 0)
    return max(0, until - count + 1)


def build_softened_response_directive(state: Optional[Dict]) -> str:
    """Return the SOFTENED MODE directive block.

    Empty string when softened is not active — caller can blindly
    concatenate into the system prompt without conditional logic
    on the caller side.

    The block is invariant: same text every softened turn. The state
    dict is consulted only to gate whether the block is included at
    all. (Future v2 may inject "N turns remaining" into the block to
    nudge the LLM toward winding down toward the end of the window;
    v1 keeps it static for predictability.)
    """
    if not is_softened_active(state):
        return ""
    return _SOFTENED_DIRECTIVE


__all__ = [
    "SOFTENED_WORD_LIMIT",
    "is_softened_active",
    "turns_remaining",
    "build_softened_response_directive",
]
