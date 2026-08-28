"""The narrator operating the conversation, rather than telling something.

WO-LORI-PROFILE-SEED-REACHABILITY-01, pre-Step-6 correction checkpoint
(2026-08-27).

── WHY THIS MODULE EXISTS, AND WHY IT IS NOT A NEW PHRASE LIST ────────

The vocabulary below is not new. It was written for
WO-TRIP-NARRATOR-BRIDGE-01 §1C and lived privately in
`trip_story_capture.py` as `_COMMAND_CORE` / `_is_conversation_command`,
after "say that again" was saved as a Bismarck travel note on 2026-07-31
— a 14-character "memory" that was really the spoken equivalent of
pressing a button.

Profile Seed needs the same judgement for a different reason: a turn that
operates the conversation must never be read as an ANSWER to an
onboarding question. The review that found this was explicit that the
answer is not a second list:

    "Reuse or extract the existing conversation-control detector; do not
     create another phrase list."

So the list MOVED here, whole, and `trip_story_capture` now imports it.
There is one canonical owner. A phrase added for Profile Seed is
automatically honoured by trip capture and vice versa, which is the
property a copied list cannot have — two lists agree on the day they are
written and never again.

── THE WHOLE DESIGN IS THE ANCHORING ──────────────────────────────────

Every one of these words appears inside real narration — "we had to GO
BACK to the hotel", "she would SAY THAT AGAIN every Christmas", "we
STOPPED at the school and CONTINUED to the cemetery". A substring match
would eat all three.

So the pattern must match the ENTIRE normalised turn, with nothing before
it and nothing after it but politeness. A turn that is a command says
only the command; a turn that is a memory says more. The six-word ceiling
is a second wall, not the first one: if a future edit loosens an
alternative so that it can match a long sentence, the ceiling stops that
edit from swallowing a memory.

── TWO INTENTS, BECAUSE THE WALK MUST RESPOND DIFFERENTLY ─────────────

Both intents are STATIONARY — neither is an answer, and neither may ever
advance a topic. They differ only in what Lori does next:

  `CONTROL_REPEAT`   "repeat that", "say it again", "louder", "slower"
                     The narrator is asking for the question BACK. The
                     walk re-presents it.

  `CONTROL_HOLD`     "pause", "stop", "help", "change narrator",
                     "never mind", "go on"
                     The narrator is doing something else with the
                     conversation. The walk asks NOTHING this turn and
                     holds where it is.

The split is deliberately lopsided: REPEAT is enumerated explicitly and
everything else that is a control falls to HOLD, because HOLD is the
conservative outcome. Mis-filing a control as HOLD costs one turn without
a question. Mis-filing it as REPEAT asks a narrator who said "stop" the
onboarding question again.

── STDLIB ONLY, ON PURPOSE ────────────────────────────────────────────

`trip_story_capture` carries a LAW 3 isolation gate: trip data layer and
stdlib, nothing else. This module imports `re` and nothing from the
project, so importing it cannot widen that lane's dependency surface.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

#: The narrator is asking for the last question back.
CONTROL_REPEAT = "control_repeat"
#: The narrator is operating the conversation some other way.
CONTROL_HOLD = "control_hold"

CONTROL_INTENTS: Tuple[str, ...] = (CONTROL_REPEAT, CONTROL_HOLD)

# ── The vocabulary ─────────────────────────────────────────────────────
#
# `_REPEAT_CORE` and `_HOLD_CORE` together are, verbatim, the
# `_COMMAND_CORE` that lived in `trip_story_capture.py` — split by intent
# and extended by exactly two families, each named in the 2026-08-27
# review because the classifier got them wrong:
#
#   help              — "help" as a whole turn is a request for
#                       assistance with the conversation, not an answer
#                       to "where did you grow up".
#   narrator control  — "change narrator" is the narrator operating the
#                       session. It was classified `addressed`, which
#                       would have closed a topic nobody spoke to.
#
# They are added HERE, to the one canonical vocabulary, rather than in a
# Profile-Seed-only list — which is the whole point of this module.
_REPEAT_CORE = (
    r"say (?:that|it) again|say again|"
    r"repeat(?:\s+(?:that|it|again))*|"
    r"read (?:that|it) (?:again|back)|"
    r"say that one more time|"
    r"what was that|come again|"
    r"louder|speak up|slower|slow down|speak (?:slower|slowly|up)"
)

_HOLD_CORE = (
    r"go back|back up|"
    r"pause|"
    r"stop(?:\s+(?:talking|that|it))?|"
    r"continue|go on|keep going|carry on|"
    r"wait|hold on|hang on|(?:just )?a (?:second|moment|minute)|"
    r"never ?mind|forget it|"
    r"start over|"
    r"help|help me|"
    r"(?:change|switch|different|new) narrators?"
)

#: Kept as a single name so a reader can still see the whole vocabulary
#: in one place, exactly as `_COMMAND_CORE` did.
_COMMAND_CORE = _REPEAT_CORE + r"|" + _HOLD_CORE

_PREFIX = (r"^(?:hey\s+)?(?:lori\s+)?"
           r"(?:please\s+|can you\s+|could you\s+|would you\s+|will you\s+)?")
_SUFFIX = r"(?:\s+please)?(?:\s+lori)?$"

_CONVERSATION_COMMAND_RX = re.compile(
    _PREFIX + r"(?:" + _COMMAND_CORE + r")" + _SUFFIX, re.I)
_REPEAT_RX = re.compile(_PREFIX + r"(?:" + _REPEAT_CORE + r")" + _SUFFIX, re.I)

# A control is short by nature. This is a second wall, not the first one:
# if a future edit loosens an alternative above so that it can match a
# long sentence, this stops that edit from swallowing a memory.
MAX_COMMAND_WORDS = 6


def normalize(text: Optional[str]) -> str:
    """Lowercase, drop punctuation, collapse whitespace, keep apostrophes.

    Byte-identical to `trip_story_capture._normalize`, which is now a
    thin alias for this function. Moving it rather than copying it is
    what keeps the two callers from drifting.
    """
    s = str(text or "").lower()
    s = s.replace("’", "'")
    s = re.sub(r"[^\w\s']", " ", s)     # drop punctuation but keep apostrophes
    s = re.sub(r"\s+", " ", s).strip()
    return s


def is_conversation_command(narrator_text: Optional[str]) -> bool:
    """True when the WHOLE turn is the narrator operating the conversation.

    Deliberately conservative in one direction only. A missed command
    costs the operator one junk row they can hide; a false positive
    silently discards a memory, and nothing downstream would ever show
    that it had happened.
    """
    norm = normalize(narrator_text).replace("'", "")
    if not norm:
        return False
    if len(norm.split()) > MAX_COMMAND_WORDS:
        return False
    return bool(_CONVERSATION_COMMAND_RX.match(norm))


def control_intent(narrator_text: Optional[str]) -> Optional[str]:
    """`CONTROL_REPEAT`, `CONTROL_HOLD`, or `None` for an ordinary turn.

    `None` means "this is not a control" — NOT "this is an answer". What
    an ordinary turn means is the caller's decision; this module only
    reports whether the narrator was operating the conversation.
    """
    if not is_conversation_command(narrator_text):
        return None
    norm = normalize(narrator_text).replace("'", "")
    return CONTROL_REPEAT if _REPEAT_RX.match(norm) else CONTROL_HOLD


__all__ = (
    "CONTROL_REPEAT", "CONTROL_HOLD", "CONTROL_INTENTS",
    "MAX_COMMAND_WORDS", "normalize", "is_conversation_command",
    "control_intent",
)
