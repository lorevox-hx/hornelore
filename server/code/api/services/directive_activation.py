"""THE authoritative registry of interview directive families.

WO-LEAN-LORI-DIRECTIVE-ACTIVATION-01 (Lean Lori item 2), 2026-08-18.

── WHY THIS EXISTS ─────────────────────────────────────────────────────

Item 1 gave every prompt SECTION a declared policy. That left one
section, `directives_interview`, as a ~980-line monolith which is
`required=True` as a whole -- and which contains a great many
independent instruction families that have nothing to do with each
other: helper-role guidance, onboarding phases, questionnaire walks,
cognitive-support variants, visual-affect wording, fatigue pacing,
photo hints, pass-specific era prompts.

Because the section is required, all of it is protected from the budget.
Because it is one string, none of it is diagnosable. And because each
family is gated by an `if` buried a few hundred lines into the function,
nobody can answer "what is a ready narrator actually being told?"
without reading the whole thing.

**Making the whole section optional would be wrong** -- the interview
discipline inside it is what stops Lori reverting to a generic
assistant, and losing it is the behaviour every LORI bug fix undoes. The
answer is to separate the families, keep the protective core required,
and let each conditional family be present only when its condition is
genuinely active.

── WHAT THIS MODULE IS, AND IS NOT ─────────────────────────────────────

It is a PURE POLICY LAYER. It declares which families exist, who owns
them, which predicate activates them, where their content comes from,
how important they are, whether they may be dropped, and the order they
render in. It evaluates nothing and renders nothing.

It does NOT decide whether history or optional sections trim first. That
is item 3, and it is to be decided from measurement.

── FAILURE POSTURE ─────────────────────────────────────────────────────

An unknown family id or an unknown activation predicate raises at
import/boot. A silent default is how a section reached production ranked
below a per-turn hint; the same mistake in a directive family would mean
a narrator silently receiving, or silently missing, an instruction.
"""
from __future__ import annotations

from typing import Dict, List, NamedTuple

__all__ = [
    "DirectiveFamily",
    "UnknownFamilyError",
    "UnknownPredicateError",
    "ACTIVATION_PREDICATES",
    "REGISTRY",
    "family_for",
    "family_ids_in_render_order",
    "required_family_ids",
    "conditional_family_ids",
]

# ── activation predicates ───────────────────────────────────────────────
#
# The stable id of the CONDITION under which a family belongs in the
# prompt. Declared as a closed set so a family cannot name a predicate
# nobody implements, and so item 2's gating work has an inventory to
# work through rather than a grep.
#
# `always` is a real answer for the protective core, and naming it is
# the point: a family whose activation is `always` and should not be is
# exactly what this item goes looking for.
ACTIVATION_PREDICATES = frozenset({
    "always",
    "memoir_state_threads_or_draft",
    "speaker_name_known",
    "session_style_non_default",
    "media_present",
    "role_helper",
    "role_onboarding",
    "story_momentum_active",
    "thread_surface_present",
    "bio_anchored_surface_present",
    "witness_receipt_present",
    "era_definition_requested",
    "softened_state_active_and_not_parked",
    "identity_mode_active",
    "pass1_and_reference_narrator",
    "pass_2a",
    "pass_2b",
    "current_mode_set",
    "cognitive_support_mode",
    "paired_interview",
    "visual_affect_fresh",
    "fatigue_elevated",
})


class UnknownFamilyError(KeyError):
    """A directive family id with no registered policy."""


class UnknownPredicateError(ValueError):
    """A family naming an activation predicate that does not exist."""


class DirectiveFamily(NamedTuple):
    """Declarative facts about one directive family."""

    family_id: str
    owner: str
    activation: str
    source: str
    priority_tier: str
    #: Required families are never withheld and never dropped. They are
    #: the protective core: the interview discipline, and the rule that
    #: forbids claiming a visual observation without evidence.
    required: bool
    #: Ascending render order. Reproduces today's composition order so
    #: the active-state prompt stays byte-for-byte identical.
    render_order: int
    note: str = ""


def _f(family_id, owner, activation, source, tier, required, order, note=""):
    return DirectiveFamily(family_id=family_id, owner=owner,
                           activation=activation, source=source,
                           priority_tier=tier, required=required,
                           render_order=order, note=note)


# Tiers, reusing the section vocabulary so a diagnostic can group both.
TIER_DISCIPLINE = "discipline"
TIER_NARRATOR_CONTEXT = "narrator_context"
TIER_WORKFLOW = "workflow"
TIER_ACCESSIBILITY = "accessibility"

_TIERS = frozenset({TIER_DISCIPLINE, TIER_NARRATOR_CONTEXT, TIER_WORKFLOW,
                    TIER_ACCESSIBILITY})

# ── THE REGISTRY ────────────────────────────────────────────────────────
#
# `render_order` reproduces the order these families are appended today,
# so that with every family active the rendered directive block is
# byte-for-byte what it was. Intended activation changes belong in the
# gating commit, not here.
_FAMILIES: List[DirectiveFamily] = [
    _f("interview_core", "lori-discipline", "always", "static",
       TIER_DISCIPLINE, True, 10,
       "The interview discipline itself. Without it Lori reverts to a "
       "generic assistant, which is the behaviour every LORI bug fix "
       "undoes. Never withheld, never dropped."),

    _f("memoir_arc", "memoir", "memoir_state_threads_or_draft", "runtime71",
       TIER_WORKFLOW, False, 20,
       "Arc roles and meaning tags, only while a memoir is in threads or "
       "draft state."),

    _f("speaker_name", "lori-core", "speaker_name_known", "profile",
       TIER_NARRATOR_CONTEXT, False, 30,
       "How to address the narrator."),

    _f("session_style", "operator-session", "session_style_non_default",
       "runtime71", TIER_WORKFLOW, False, 40,
       "Style guidance for an operator-selected non-default session "
       "style. Oral history is the default and needs no override."),

    _f("media_hints", "photo-intake", "media_present", "runtime71",
       TIER_WORKFLOW, False, 50,
       "Photo and media handling hints. Absent when the narrator has no "
       "media in view."),

    _f("role_helper", "operator-roles", "role_helper", "runtime71",
       TIER_WORKFLOW, False, 60,
       "Guidance for the helper role only."),

    _f("role_onboarding", "operator-roles", "role_onboarding", "runtime71",
       TIER_WORKFLOW, False, 70,
       "Onboarding phase guidance only."),

    _f("story_momentum", "lori-story", "story_momentum_active", "runtime71",
       TIER_DISCIPLINE, False, 80,
       "Question hierarchy and story momentum."),

    _f("thread_surfacing", "lori-threads", "thread_surface_present",
       "runtime71", TIER_WORKFLOW, False, 90,
       "Surfacing an open thread, only when there is one."),

    _f("bio_anchored_ask", "bio-builder", "bio_anchored_surface_present",
       "runtime71", TIER_WORKFLOW, False, 100,
       "An anchored ask from the Bio Builder surface."),

    _f("witness_receipt", "lori-witness", "witness_receipt_present",
       "runtime71", TIER_WORKFLOW, False, 110,
       "Witness-mode receipt wording."),

    _f("era_explanation", "life-map", "era_definition_requested", "runtime71",
       TIER_WORKFLOW, False, 120,
       "The Era Explainer. Already gated on real narrator state -- the "
       "one family that was, which is why item 2 exists for the rest."),

    _f("softened_response", "lori-safety", "softened_state_active_and_not_parked",
       "runtime71", TIER_ACCESSIBILITY, False, 130,
       "Softened-mode wording. Its parked check is load-bearing: runtime "
       "safety is PARKED and must stay parked."),

    _f("identity_mode", "lori-identity", "identity_mode_active", "runtime71",
       TIER_WORKFLOW, False, 140,
       "Identity collection prompts. A live narrator with incomplete "
       "identity may still receive these -- what they must NOT receive "
       "is the ten-question questionnaire walk below."),

    _f("profile_seed_walk", "questionnaire", "pass1_and_reference_narrator",
       "runtime71+db", TIER_WORKFLOW, False, 150,
       "The hard-coded Pass 1 ten-question Profile Seed walk. RETIRED FOR "
       "LIVE NARRATORS by item 2 and preserved for reference narrators. "
       "Its activation predicate reads narrator_type from the SERVER "
       "database, never from the browser."),

    _f("pass_2a", "life-map", "pass_2a", "runtime71", TIER_WORKFLOW, False, 160,
       "Era-walk prompts for pass 2a."),

    _f("pass_2b", "life-map", "pass_2b", "runtime71", TIER_WORKFLOW, False, 170,
       "Era-walk prompts for pass 2b."),

    _f("current_mode", "lori-modes", "current_mode_set", "runtime71",
       TIER_WORKFLOW, False, 180,
       "Recognition / grounding / light mode variants."),

    _f("cognitive_support", "wo-10c", "cognitive_support_mode", "runtime71",
       TIER_ACCESSIBILITY, False, 190,
       "WO-10C cognitive support variants. Accessibility, not workflow: "
       "when active it changes how a narrator is met, not what task is "
       "being done."),

    _f("paired_interview", "operator-session", "paired_interview", "runtime71",
       TIER_WORKFLOW, False, 200,
       "Guidance for a paired interview."),

    _f("visual_affect", "facial-awareness", "visual_affect_fresh", "runtime71",
       TIER_ACCESSIBILITY, False, 210,
       "Affect-derived pacing guidance. Requires a baseline AND a current "
       "affect reading; stale or absent evidence must produce nothing."),

    _f("no_visual_claims", "facial-awareness", "always", "static",
       TIER_DISCIPLINE, True, 220,
       "The prohibition on claiming a visual observation without "
       "evidence. REQUIRED and unconditional: it is protective, it is "
       "the rule that stops 'I can see...', and it must hold precisely "
       "when the affect family above is ABSENT."),

    _f("fatigue", "wo-10c", "fatigue_elevated", "runtime71",
       TIER_ACCESSIBILITY, False, 230,
       "Pacing guidance at elevated fatigue only."),
]


def _build(families) -> Dict[str, DirectiveFamily]:
    """Validate at import so a bad registry fails the BOOT."""
    reg: Dict[str, DirectiveFamily] = {}
    orders = []
    for fam in families:
        if fam.family_id in reg:
            raise ValueError(f"duplicate directive family {fam.family_id!r}")
        if fam.activation not in ACTIVATION_PREDICATES:
            raise UnknownPredicateError(
                f"{fam.family_id}: unknown activation predicate "
                f"{fam.activation!r}")
        if fam.priority_tier not in _TIERS:
            raise ValueError(f"{fam.family_id}: unknown tier "
                             f"{fam.priority_tier!r}")
        if not fam.owner or not fam.source:
            raise ValueError(f"{fam.family_id}: owner and source required")
        # A required family that is conditional would be a contradiction:
        # "never withheld" and "only sometimes present" cannot both hold.
        if fam.required and fam.activation != "always":
            raise ValueError(
                f"{fam.family_id}: a required family cannot be conditional "
                f"(activation={fam.activation!r})")
        orders.append(fam.render_order)
        reg[fam.family_id] = fam
    if len(orders) != len(set(orders)):
        raise ValueError("two directive families share a render_order")
    return reg


REGISTRY: Dict[str, DirectiveFamily] = _build(_FAMILIES)


def family_for(family_id: str) -> DirectiveFamily:
    """The policy for a family id, or a loud failure."""
    try:
        return REGISTRY[family_id]
    except KeyError:
        raise UnknownFamilyError(
            f"{family_id!r} is not a registered directive family. Add it to "
            f"directive_activation.REGISTRY with an owner, an activation "
            f"predicate, a source, a tier, a drop policy and a render order."
        ) from None


def family_ids_in_render_order() -> List[str]:
    return [f.family_id for f in sorted(_FAMILIES, key=lambda x: x.render_order)]


def required_family_ids() -> List[str]:
    return [f.family_id for f in _FAMILIES if f.required]


def conditional_family_ids() -> List[str]:
    return [f.family_id for f in _FAMILIES if not f.required]
