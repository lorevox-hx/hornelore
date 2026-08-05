"""WO-LEAN-LORI-RUNTIME-01 Phase 4A — fit the chat prompt without cutting Lori.

THE DEFECT THIS REPLACES
------------------------
Three sites did the same thing::

    inputs = {k: v[:, -MAX_CHAT_PROMPT_TOKENS:] for k, v in inputs.items()}

That keeps the LAST N tokens, so what it discards is the FRONT -- which is
exactly where the system prompt lives. `api.py:365` says so in its own
comment: "NOTE it cuts the FRONT, where a system prompt lives."

Measured over 630 real chat turns in `api.log`: 382 (60.6%) exceeded the
8,192-token window, median 9,383, worst 12,656. On every one of those
turns Lori's identity, purpose and interview discipline were removed
before she answered, and nothing told anyone. That is the cemetery
answer: she was not ignoring her instructions, she was never shown them.

WHAT REPLACES IT
----------------
Drop the OLDEST CONVERSATION, at turn boundaries, and never the system
message or the narrator's current words.

Three properties, in the order they matter:

1. **The system message is untouchable.** It is not trimmed, not
   summarised, not partially sliced. Losing half of Lori's identity is
   worse than losing an old exchange, because a half-instruction still
   reads as an instruction.

2. **The narrator's current message is untouchable.** Answering a turn
   you cannot see is worse than answering with less history.

3. **History is dropped at turn boundaries, oldest first.** Never
   mid-message. A half-sentence from 20 turns ago is not context, it is
   noise that reads as context -- and a model handed the second half of a
   question will answer the question it can see.

WHY BOUNDARIES AND NOT TOKENS
-----------------------------
A user turn and the assistant reply it produced are dropped TOGETHER.
Dropping only the reply leaves a question that was never answered;
dropping only the question leaves an answer to nothing. Both give the
model a false picture of what has already been said, and the second one
is worse -- Lori can re-ask something she has already been told, which is
precisely the failure this system exists to avoid with older narrators.

WHEN IT STILL DOES NOT FIT
--------------------------
If the system message and the current turn alone exceed the window, this
reports `mandatory_too_large` and the CALLER refuses the turn. It does
not slice. The extraction lane already works this way -- `api.py:352`
refuses rather than truncating, on the grounds that "there is no safe
subset of an extraction prompt to discard" -- and the same reasoning
holds here: an honest error an operator can see beats a reply generated
from a prompt that was quietly mutilated.

This is expected to be rare. A parked system prompt is ~2,400 tokens
against an 8,192 window, so a refusal needs a single narrator message of
roughly 5,700 tokens -- about 20,000 characters in one turn.

MEASUREMENT
-----------
Token counting is injected, not imported. The only honest count is taken
AFTER the chat template is applied, because the template adds its own
tokens, and this module has no business loading a tokenizer to find that
out. Callers pass `count_tokens(messages) -> int` that renders and
counts exactly the way their own generation path does; anything else
would measure a prompt nobody sends.

NOT IN THIS PHASE
-----------------
Dropping optional SYSTEM sections (memory context, factual chain,
English-first, UI context, pinned facts) when even a minimal history
does not fit. Those are classified and ordered already in
`prompt_composer._PromptAssembly`, and dropping them needs the assembly
to survive as far as this function -- a wider change. History trimming
alone removes the failure that was actually happening in production, and
a phase that fixes the live defect is worth more than a phase that fixes
it more elegantly later.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Sequence

__all__ = ["BudgetOutcome", "fit_chat_messages", "history_segments"]

Message = Dict[str, str]


@dataclass(frozen=True)
class BudgetOutcome:
    """What the budget decided, in terms an operator log can carry."""

    messages: List[Message]
    fits: bool
    tokens: int
    limit: int
    #: conversation turns removed from the OLD end (a user turn plus the
    #: assistant reply it produced counts as one).
    dropped_turns: int
    kept_turns: int
    #: "fits" | "trimmed" | "mandatory_too_large"
    reason: str

    def as_log_fields(self) -> str:
        return (f"reason={self.reason} tokens={self.tokens} limit={self.limit} "
                f"kept_turns={self.kept_turns} dropped_turns={self.dropped_turns}")


def history_segments(history: Sequence[Message]) -> List[List[Message]]:
    """Group history into conversation turns.

    A turn starts at a `user` message and runs to just before the next
    one, so the assistant reply travels with the question that produced
    it. Anything before the first `user` message becomes a leading
    segment of its own rather than being silently attached to the first
    real turn -- it is usually a resumed assistant greeting, and gluing
    it to an unrelated question would misreport what gets dropped.
    """
    segments: List[List[Message]] = []
    current: List[Message] = []
    for m in history:
        role = (m.get("role") or "").strip().lower()
        if role == "user" and current:
            segments.append(current)
            current = []
        current.append(m)
    if current:
        segments.append(current)
    return segments


def fit_chat_messages(
    messages: Sequence[Message],
    *,
    limit: int,
    count_tokens: Callable[[List[Message]], int],
) -> BudgetOutcome:
    """Return the largest suffix of history that fits under ``limit``.

    ``messages`` is the shape all three chat paths already build:
    ``[system] + history + [current user turn]``.

    The system message and the final message are mandatory and are never
    modified. History is dropped oldest-first at turn boundaries.
    """
    msgs = [dict(m) for m in messages]
    if not msgs:
        return BudgetOutcome([], True, count_tokens([]), limit, 0, 0, "fits")

    head: List[Message] = []
    if (msgs[0].get("role") or "").strip().lower() == "system":
        head = [msgs[0]]
        msgs = msgs[1:]

    # The current narrator turn is the last message. If history is empty
    # this is also the only message, and `tail` simply takes it.
    tail: List[Message] = [msgs[-1]] if msgs else []
    history = msgs[:-1] if msgs else []

    segments = history_segments(history)
    total_turns = len(segments)

    def build(keep: int) -> List[Message]:
        kept = segments[total_turns - keep:] if keep else []
        out: List[Message] = list(head)
        for seg in kept:
            out.extend(seg)
        out.extend(tail)
        return out

    full = build(total_turns)
    tokens = count_tokens(full)
    if tokens <= limit:
        return BudgetOutcome(full, True, tokens, limit, 0, total_turns, "fits")

    # Binary search for the largest number of NEWEST turns that fits.
    # Monotonic by construction -- adding an older turn only adds tokens --
    # so this is exact, and it costs about log2(n) template renders rather
    # than n. On a long session that is the difference between five
    # renders and forty, on the turn the narrator is waiting for.
    lo, hi, best = 0, total_turns, -1
    best_msgs: List[Message] = []
    best_tokens = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = build(mid)
        n = count_tokens(candidate)
        if n <= limit:
            best, best_msgs, best_tokens = mid, candidate, n
            lo = mid + 1
        else:
            hi = mid - 1

    if best < 0:
        # Not even the system message plus the current turn fits. Report
        # it; the caller refuses. Returning the minimum here rather than
        # an empty list so an operator can see WHAT did not fit.
        minimal = build(0)
        return BudgetOutcome(minimal, False, count_tokens(minimal), limit,
                             total_turns, 0, "mandatory_too_large")

    return BudgetOutcome(best_msgs, True, best_tokens, limit,
                         total_turns - best, best, "trimmed")
