"""WO-LORI-SOFTENED-RESPONSE-01 — post-safety softened-mode prompt block.
WO-LORI-SOFTENED-MODE-PERSISTENCE-01 (2026-06-14) — three-state extension.

Pure-function module that builds the SOFTENED MODE / RECOVERING MODE
directives injected into Lori's system prompt for the N turns
following a safety trigger.

Architecture rationale (per WO §1 of the original WO):
    The 2026-05-01 golfball-comm-control-rerun Turn 07 demonstrated
    that chat_ws.py composes a normal interview prompt even while the
    DB has interview_softened=1 from Turn 06's acute trigger. The
    LLM produced a "Can you tell me more about... and..." compound
    question that the wrapper correctly flagged as
    normal_interview_question_during_safety. The fix is composer-side:
    read the softened state at turn-start and inject this directive
    so the LLM is told what shape its output should take.

WO-LORI-SOFTENED-MODE-PERSISTENCE-01 added the three-state machine
(normal → softened → softened_exiting → normal) and trigger-specific
per-state caps. This module now picks one of TWO directive blocks
based on the state machine:

    state="softened"          → _SOFTENED_DIRECTIVE       (no questions, 30-35w)
    state="softened_exiting"  → _RECOVERING_DIRECTIVE     (gentle re-engagement,
                                                            no resumption phrases,
                                                            50w)
    state="normal"            → empty (no injection)

LAW-3 isolation: this module imports zero extraction-stack code.
Pure functions only. Never calls an LLM. Composes a string from a
state dict; that's it.

Public API:

    build_softened_response_directive(state) -> str
        Returns the directive block to inject. Empty string when
        state["state"] is "normal" OR softened isn't active.

    is_softened_active(state) -> bool
        Convenience helper for boolean checks.

    SOFTENED_WORD_LIMIT — int, used by lori_communication_control to
        override the per-style word budget when softened (acute=30,
        past_tense=35, exiting=50).

    softened_word_limit(state) -> int
        Per-state + per-trigger word cap for the comm-control wrapper.

The state dict shape matches db.get_session_softened_state()'s return:
    {
        "interview_softened": bool,
        "softened_until_turn": int,
        "turn_count": int,
        "state": "normal" | "softened" | "softened_exiting",
        "trigger": "acute" | "past_tense_acknowledge" | "",
        "n_remaining": int,
    }
"""
from __future__ import annotations

from typing import Dict, Optional


# Tightened word budget for softened-mode turns (vs clear_direct 55).
# Presence-first responses should be short — long Lori answers in
# softened mode read as Lori-needs-something-from-the-narrator, which
# is exactly the wrong posture.
#
# Per-state defaults per WO-LORI-SOFTENED-MODE-PERSISTENCE-01 §6:
#   softened (acute)       = 30
#   softened (past-tense)  = 35
#   softened_exiting       = 50
# The legacy SOFTENED_WORD_LIMIT constant (35) is preserved for any
# caller that hasn't been updated to the per-state path; it matches
# the past-tense default.
SOFTENED_WORD_LIMIT = 35

_SOFTENED_WORD_LIMIT_ACUTE = 30
_SOFTENED_WORD_LIMIT_PAST_TENSE = 35
_SOFTENED_WORD_LIMIT_EXITING = 50


_SOFTENED_DIRECTIVE = """\
SOFTENED MODE — POST-SAFETY GROUND.

The previous turn surfaced distress. For this turn and the next few
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


_RECOVERING_DIRECTIVE = """\
RECOVERING MODE — ONE TURN OF TRANSITION.

The narrator shared something heavy a few turns back. The softened
window is ending, but the interview must NOT resume on Lori's
initiative — it resumes when the narrator resumes it.

For THIS turn ONLY (one-turn transition, then back to normal):

- Read where the narrator is from what they just said.
- If they are clearly back in chapter (telling a story, naming a
  person, describing a place), you may gently follow at their pace.
  Do NOT reference the heavy moment. Do NOT summarize what they
  shared back then.
- If they are still quiet or short, stay quiet with them. One short
  sentence is fine. A small reflection is fine.
- A question is NOT fine yet.
- FORBIDDEN phrases (these signal interview-resumption and undo the
  trust the narrator extended):
    "we can keep going"
    "where were we"
    "so, you were telling me about"
    "let's get back to"
    "shall we continue"
    "ready to pick up where we left off"
- Total length: 50 words or fewer.

This is a bridge turn. The next turn will be normal cadence, but it
follows the narrator's lead, not yours.\
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
    """Return the directive block matching the current softened state.

    Three-state machine per WO-LORI-SOFTENED-MODE-PERSISTENCE-01:
      state="softened"          → _SOFTENED_DIRECTIVE
      state="softened_exiting"  → _RECOVERING_DIRECTIVE
      state="normal" or absent  → "" (no injection)

    Backward compatibility: callers passing the old shape
    (interview_softened=True without state="...") get
    _SOFTENED_DIRECTIVE — same behavior as the v1 module.
    """
    if not is_softened_active(state):
        return ""
    if not state or not isinstance(state, dict):
        return _SOFTENED_DIRECTIVE
    explicit_state = (state.get("state") or "").strip().lower()
    if explicit_state == "softened_exiting":
        return _RECOVERING_DIRECTIVE
    # "softened", missing, or any unknown value falls through to the
    # safe default (the more restrictive block).
    return _SOFTENED_DIRECTIVE


def softened_word_limit(state: Optional[Dict]) -> int:
    """Per-state + per-trigger word cap for the comm-control wrapper.

    Caps per WO-LORI-SOFTENED-MODE-PERSISTENCE-01 §6:
      softened (acute)       = 30
      softened (past-tense)  = 35
      softened_exiting       = 50
      normal                 = caller's session-style default (this
                                function returns the legacy 35 as a
                                conservative fallback when state is
                                absent — callers normally short-circuit
                                back to their own per-style cap when
                                softened isn't active)
    """
    if not is_softened_active(state):
        return SOFTENED_WORD_LIMIT
    if not state or not isinstance(state, dict):
        return SOFTENED_WORD_LIMIT
    explicit_state = (state.get("state") or "").strip().lower()
    trigger = (state.get("trigger") or "").strip().lower()
    if explicit_state == "softened_exiting":
        return _SOFTENED_WORD_LIMIT_EXITING
    if trigger == "acute":
        return _SOFTENED_WORD_LIMIT_ACUTE
    if trigger == "past_tense_acknowledge":
        return _SOFTENED_WORD_LIMIT_PAST_TENSE
    # Unknown / legacy trigger value during softened state — use the
    # tighter acute cap as the safe default.
    return _SOFTENED_WORD_LIMIT_ACUTE


__all__ = [
    "SOFTENED_WORD_LIMIT",
    "is_softened_active",
    "turns_remaining",
    "build_softened_response_directive",
    "softened_word_limit",
]
