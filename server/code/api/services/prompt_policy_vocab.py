"""Shared vocabulary for prompt-section and directive-family policy.

WO-LEAN-LORI-DIRECTIVE-ACTIVATION-01, 2026-08-18.

Two registries describe prompt material: `prompt_section_policy` for
system-prompt SECTIONS and `directive_activation` for the directive
FAMILIES inside the interview section. They had begun to declare their
own copies of the same vocabulary -- two `TIER_DISCIPLINE` constants,
two ideas of what a "source" is -- which is two authorities for one
concept and the beginning of the drift this lane exists to remove.

This module is the single vocabulary. Both registries import it.

── WHY THE DEGRADATION IS TYPED ────────────────────────────────────────

The first cut recorded degradation as an English sentence and then
BANNED a forbidden rationale by scanning that sentence for phrases. That
guard fired twice on prose that was arguing against the very rationale
it forbade -- once on a note that said a reviewed story "cannot be
re-asked", and once on the correction that quoted the retired claim in
order to withdraw it.

A scan over English cannot tell an assertion from a quotation. So the
degradation is now a TYPE drawn from a closed set, and the forbidden
justification is simply not a member of it. It cannot be expressed, so
it cannot be smuggled in, and no scanner is needed.
"""
from __future__ import annotations

from typing import FrozenSet

__all__ = [
    "TIER_IDENTITY", "TIER_DISCIPLINE", "TIER_REVIEWED_EVIDENCE",
    "TIER_NARRATOR_CONTEXT", "TIER_TURN_HINT", "TIER_WORKFLOW",
    "TIER_ACCESSIBILITY", "TIERS",
    "SOURCE_STATIC", "SOURCE_PROFILE", "SOURCE_RUNTIME",
    "SOURCE_REVIEWED_STORY", "SOURCE_TRANSPORT", "SOURCE_DEVICE",
    "SOURCE_SERVER_DB", "SOURCES",
    "DEGRADE_NONE", "DEGRADE_DURABLE_ON_SERVER", "DEGRADE_REBUILT_NEXT_TURN",
    "DEGRADE_COSMETIC", "DEGRADATIONS", "DROPPABLE_DEGRADATIONS",
    "ROLE_INTERVIEWER", "ROLE_HELPER", "ROLE_ONBOARDING", "ROLES", "ALL_ROLES",
]

# ── priority tier ───────────────────────────────────────────────────────
# What KIND of thing this is. Deliberately not the drop order: the tier
# says what it is, the order says which of two you lose first.
TIER_IDENTITY = "identity"                    # who Lori and the narrator are
TIER_DISCIPLINE = "discipline"                # how Lori is required to behave
TIER_REVIEWED_EVIDENCE = "reviewed_evidence"  # a human read it and decided
TIER_NARRATOR_CONTEXT = "narrator_context"    # durable context about this person
TIER_TURN_HINT = "turn_hint"                  # rebuilt next turn at no cost
TIER_WORKFLOW = "workflow"                    # an active operator/product task
TIER_ACCESSIBILITY = "accessibility"          # how this narrator is met

TIERS: FrozenSet[str] = frozenset({
    TIER_IDENTITY, TIER_DISCIPLINE, TIER_REVIEWED_EVIDENCE,
    TIER_NARRATOR_CONTEXT, TIER_TURN_HINT, TIER_WORKFLOW, TIER_ACCESSIBILITY,
})

# ── source ──────────────────────────────────────────────────────────────
# Where the content comes from. Answers "if this is wrong, where do I fix
# it", and -- for a droppable item -- "does the thing it came from still
# exist after we drop it".
SOURCE_STATIC = "static"                # literal text in the composer
SOURCE_PROFILE = "profile"              # profile / PROFILE_JSON
SOURCE_RUNTIME = "runtime71"            # per-turn runtime context
SOURCE_REVIEWED_STORY = "story_review"  # server-owned story projection
SOURCE_TRANSPORT = "transport"          # appended by a transport
SOURCE_DEVICE = "device"                # the narrator's own machine (clock)
SOURCE_SERVER_DB = "server_db"          # read from the database this turn

SOURCES: FrozenSet[str] = frozenset({
    SOURCE_STATIC, SOURCE_PROFILE, SOURCE_RUNTIME, SOURCE_REVIEWED_STORY,
    SOURCE_TRANSPORT, SOURCE_DEVICE, SOURCE_SERVER_DB,
})

# ── degradation ─────────────────────────────────────────────────────────
#
# THE CLOSED SET IS THE GUARD. "the narrator can be asked again" is not a
# member and cannot become one without someone adding it here, in the
# open, on purpose. Lorevox's premise is that an older narrator is not a
# recoverable storage device; making that unsayable in the type system is
# stronger than forbidding the sentence.
DEGRADE_NONE = "none"                            # required; kept or refuse
DEGRADE_DURABLE_ON_SERVER = "durable_on_server"  # source survives; reload later
DEGRADE_REBUILT_NEXT_TURN = "rebuilt_next_turn"  # regenerated at no cost
DEGRADE_COSMETIC = "cosmetic"                    # phrasing only; no capability

DEGRADATIONS: FrozenSet[str] = frozenset({
    DEGRADE_NONE, DEGRADE_DURABLE_ON_SERVER, DEGRADE_REBUILT_NEXT_TURN,
    DEGRADE_COSMETIC,
})

#: The degradations that may accompany a DROPPABLE item. `DEGRADE_NONE`
#: is reserved for required items, so a droppable item cannot decline to
#: say what losing it costs.
DROPPABLE_DEGRADATIONS: FrozenSet[str] = frozenset(
    DEGRADATIONS - {DEGRADE_NONE})

# ── assistant role ──────────────────────────────────────────────────────
# Which conversation this turn is. A helper turn is not a quieter
# interview: it is a different job, and it must not inherit
# interviewer-only instructions.
ROLE_INTERVIEWER = "interviewer"
ROLE_HELPER = "helper"
ROLE_ONBOARDING = "onboarding"

ROLES: FrozenSet[str] = frozenset({
    ROLE_INTERVIEWER, ROLE_HELPER, ROLE_ONBOARDING})

#: Convenience for families that belong to every role -- the protective
#: core and the runtime header.
ALL_ROLES: FrozenSet[str] = ROLES
