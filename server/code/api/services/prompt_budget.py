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

import hashlib
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "BudgetOutcome",
    "SectionPlan",
    "fit_chat_messages",
    "fit_chat_messages_with_sections",
    "history_segments",
    "section_digest",
]

Message = Dict[str, str]


def section_digest(text: str) -> str:
    """A short, non-reversible fingerprint of a section's content.

    Telemetry has to be able to say *which* text was kept or dropped
    across two turns without ever carrying narrator words into a log. A
    truncated SHA-256 answers "is this the same section content as last
    turn" and answers nothing else.
    """
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class SectionPlan:
    """The EVALUATED half: what the budget decided about one section, on
    one turn.

    Lean Lori item 1 draws the line here deliberately. The DECLARATIVE
    half -- owner, activation condition, trim policy, source, priority
    tier -- lives in `prompt_section_policy` and is true of the section
    regardless of any turn. The three fields that can only be known once
    the real tokenizer has seen the real template live here: `tokens`,
    `kept`, and `digest`.

    Phase 0 of Lean Lori established that a builder-side token estimate
    is wrong by a wide margin, so a token count must never be invented
    at composition time. This record is the only place one is honest.
    """

    name: str
    required: bool
    drop_order: int
    #: Real post-template token cost, measured by difference.
    tokens: int
    #: Non-reversible fingerprint. See `section_digest`.
    digest: str
    kept: bool
    #: The declared policy this section resolved to, when available.
    #: Carried so a diagnostic can report owner and tier without a second
    #: lookup, and deliberately NOT re-derived here.
    policy: Optional[object] = None

    @property
    def owner(self) -> str:
        return getattr(self.policy, "owner", "") or "unregistered"

    @property
    def priority_tier(self) -> str:
        return getattr(self.policy, "priority_tier", "") or "unregistered"

    @property
    def trim_policy(self) -> str:
        return getattr(self.policy, "trim_policy", "") or (
            "never" if self.required else "drop_whole")

    def as_log_field(self) -> str:
        return (f"{self.name}:{'keep' if self.kept else 'DROP'}"
                f":{self.tokens}:{self.digest}")


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
    #: Phase 4. Empty for the history-only entry point, which cannot see
    #: sections and therefore may not claim to have judged any.
    sections: List[SectionPlan] = field(default_factory=list)

    @property
    def dropped_sections(self) -> List[str]:
        return [s.name for s in self.sections if not s.kept]

    @property
    def kept_sections(self) -> List[str]:
        return [s.name for s in self.sections if s.kept]

    def as_log_fields(self) -> str:
        base = (f"reason={self.reason} tokens={self.tokens} limit={self.limit} "
                f"kept_turns={self.kept_turns} dropped_turns={self.dropped_turns}")
        if not self.sections:
            return base
        # Section identifiers, token counts, decisions and digests. NEVER
        # section text -- the digest exists precisely so the text does not
        # have to travel.
        return (base
                + f" dropped_sections={len(self.dropped_sections)}"
                + " sections=" + ",".join(s.as_log_field() for s in self.sections))


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


# ── Phase 4: section-aware budgeting ────────────────────────────────────
#
# WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 Phase 4, 2026-08-18.
#
# `fit_chat_messages` above can drop conversation turns and nothing else.
# When the mandatory content -- system prompt plus the current narrator
# turn -- exceeds the window on its own, it refuses, because there was no
# safe subset to discard: the prompt was one opaque string.
#
# The composer has always CLASSIFIED that string into named sections with
# a required flag and a drop order, and nothing in production ever read
# the classification. This is the reader.
#
# ── THE ORDER IS THE DESIGN, AND IT IS DELIBERATELY CONSERVATIVE ────────
#
# History is exhausted FIRST, exactly as today. Section removal is a rung
# BELOW that, so it engages only in the situations that currently raise
# `ChatPromptTooLarge`. The consequence is worth stating plainly:
#
#   **No prompt that fits today changes at all.** Every currently-working
#   turn keeps byte-identical content. What changes is that some turns
#   that currently REFUSE now degrade gracefully instead, by shedding the
#   optional sections the composer already ranked as losable.
#
# Dropping sections before history would be the opposite trade -- it would
# alter working turns to save failing ones -- and no measurement supports
# it. If a future measurement does, this is the one place to change it.
#
# Sections go in ASCENDING drop_order, lowest first, which is the ladder
# the composer documents. Ties keep composition order, which the sort is
# stable enough to preserve.
#
# Required sections and the complete current narrator turn are never
# touched. If they alone do not fit, this refuses exactly as before: a
# reply generated from a prompt with Lori's identity or the narrator's
# actual words cut out of it is worse than an error somebody can read.


def _plan(sections, kept_names, tokens_by_name) -> List[SectionPlan]:
    return [
        SectionPlan(
            name=s.name,
            required=bool(s.required),
            drop_order=int(s.drop_order),
            tokens=int(tokens_by_name.get(s.name, 0)),
            digest=section_digest(s.text),
            kept=s.name in kept_names,
            policy=getattr(s, "policy", None),
        )
        for s in sections
    ]


def fit_chat_messages_with_sections(
    messages: Sequence[Message],
    *,
    limit: int,
    count_tokens: Callable[[List[Message]], int],
    sections: Optional[Sequence] = None,
    render_sections: Optional[Callable[[Sequence], str]] = None,
) -> BudgetOutcome:
    """Fit history first; then, only if still over, shed optional sections.

    `sections` are the composer's classified `_Section` records for the
    system message. `render_sections` turns a subset back into the system
    string, and MUST be the composer's own renderer -- a second joiner
    here would be a second definition of what the prompt says.

    With no sections supplied this is `fit_chat_messages`, unchanged.
    """
    outcome = fit_chat_messages(messages, limit=limit, count_tokens=count_tokens)
    if outcome.fits or not sections or render_sections is None:
        return outcome

    # History is gone and it still does not fit. Now, and only now, the
    # classification earns its keep.
    msgs = [dict(m) for m in outcome.messages]
    if not msgs or (msgs[0].get("role") or "").strip().lower() != "system":
        # No system message to shed sections from; nothing further to try.
        return outcome

    ordered = list(sections)
    droppable = sorted(
        [s for s in ordered if not s.required],
        key=lambda s: int(s.drop_order),
    )

    # Per-section token cost, measured by difference through the REAL
    # template rather than estimated. An estimate here would be the same
    # mistake the front-slice made.
    def with_sections(keep_names) -> List[Message]:
        kept = [s for s in ordered if s.name in keep_names]
        out = [dict(m) for m in msgs]
        out[0] = dict(out[0], content=render_sections(kept))
        return out

    all_names = {s.name for s in ordered}
    tokens_by_name: Dict[str, int] = {}
    full_tokens = count_tokens(with_sections(all_names))
    for s in ordered:
        without = count_tokens(with_sections(all_names - {s.name}))
        tokens_by_name[s.name] = max(0, full_tokens - without)

    keep_names = set(all_names)
    for s in droppable:
        candidate = keep_names - {s.name}
        msgs_try = with_sections(candidate)
        n = count_tokens(msgs_try)
        keep_names = candidate
        if n <= limit:
            return BudgetOutcome(
                msgs_try, True, n, limit,
                outcome.dropped_turns, outcome.kept_turns,
                "trimmed_sections",
                _plan(ordered, keep_names, tokens_by_name),
            )

    # Every optional section is gone and the required ones plus the
    # narrator's current words still do not fit. Refuse, and report what
    # was left so an operator can see WHAT did not fit.
    minimal = with_sections(keep_names)
    return BudgetOutcome(
        minimal, False, count_tokens(minimal), limit,
        outcome.dropped_turns, outcome.kept_turns,
        "mandatory_too_large",
        _plan(ordered, keep_names, tokens_by_name),
    )
