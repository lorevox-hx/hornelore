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
    # PRESERVED WALK, corrected 2026-08-18. This read
    # "pass1_and_reference_narrator", which encoded the withdrawn
    # "retire for live narrators" decision. Narrator type does NOT
    # decide whether the ten-topic walk exists. The walk is active when:
    #   identity complete
    #   AND profile onboarding incomplete
    #   AND at least one meaningful topic remains unanswered
    # Birthplace does not prove childhood home, and an age-derived life
    # stage does not prove retired-or-still-working.
    "profile_walk_active",
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
    """Declarative facts about one directive family.

    ── THE TWO WORDS DO DIFFERENT JOBS, corrected 2026-08-18 ───────────
    This module first conflated them, and the conflation was the whole
    error: it enforced that a required family could not be conditional.

        `activation`  decides whether the family is PRESENT this turn.
        `required`    decides whether the budget may REMOVE it once it
                      is present.

    Those are independent. A helper turn's helper guidance is
    conditional -- it appears only in the helper role -- and it is also
    required once it appears, because a helper turn that silently loses
    its guidance does not become a shorter helper turn, it becomes an
    interview. Most of the families below are exactly that shape.

    A family may be absent because its feature is inactive. It may NOT
    be absent merely because fewer tokens would be convenient.
    """

    family_id: str
    owner: str
    #: What PRODUCT CAPABILITY this family supports. Recorded so a
    #: reviewer can ask "what breaks if this is missing" without reading
    #: the composer.
    capability: str
    activation: str
    source: str
    priority_tier: str
    #: True = the budget may not remove it once activated. If it cannot
    #: fit, the turn refuses honestly rather than running the feature
    #: without its instructions.
    required: bool
    #: For droppable families: the EXACT safe degradation, named so it is
    #: observable. Empty for required families.
    degradation: str
    #: True if dropping this family could affect persistence, attribution
    #: or evidence capture. Such a family must never be silently dropped.
    affects_evidence: bool
    #: Ascending render order. Reproduces today's composition order so
    #: the active-state prompt stays byte-for-byte identical.
    render_order: int
    note: str = ""


def _f(family_id, owner, capability, activation, source, tier, required,
       order, degradation="", affects_evidence=False, note=""):
    return DirectiveFamily(family_id=family_id, owner=owner,
                           capability=capability, activation=activation,
                           source=source, priority_tier=tier,
                           required=required, degradation=degradation,
                           affects_evidence=affects_evidence,
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
    _f("interview_core", "lori-discipline", "the interview itself",
       "always", "static", TIER_DISCIPLINE, True, 10,
       note="The interview discipline. Without it Lori reverts to a generic "
            "assistant, which is the behaviour every LORI bug fix undoes."),

    _f("memoir_arc", "memoir", "memoir arc + meaning tags",
       "memoir_state_threads_or_draft", "runtime71", TIER_WORKFLOW, False, 20,
       degradation="Lori stops steering toward under-covered arc roles; the "
                   "arc state itself is persisted and the next turn restores it.",
       note="Only while a memoir is in threads or draft state."),

    _f("speaker_name", "lori-core", "addressing the narrator by name",
       "speaker_name_known", "profile", TIER_NARRATOR_CONTEXT, True, 30,
       note="Required once known. Losing it does not shorten the turn, it "
            "makes Lori address a named person as a stranger."),

    _f("session_style", "operator-session", "operator-selected session style",
       "session_style_non_default", "runtime71", TIER_WORKFLOW, True, 40,
       note="Required once activated: an operator chose a non-default style, "
            "and silently reverting to oral history is not a shorter version "
            "of that style, it is a different session."),

    _f("media_hints", "photo-intake", "photo/media handling",
       "media_present", "runtime71", TIER_WORKFLOW, True, 50,
       affects_evidence=True,
       note="Required when media is in view: these hints govern how a photo "
            "is described and attributed, so losing them can affect what is "
            "captured against that photo."),

    _f("role_helper", "operator-roles", "helper role",
       "role_helper", "runtime71", TIER_WORKFLOW, True, 60,
       note="A helper turn that loses its guidance becomes an interview."),

    _f("role_onboarding", "operator-roles", "onboarding role",
       "role_onboarding", "runtime71", TIER_WORKFLOW, True, 70,
       note="An onboarding turn that loses its phase guidance strands the "
            "narrator mid-onboarding."),

    _f("story_momentum", "lori-story", "question hierarchy + story momentum",
       "story_momentum_active", "runtime71", TIER_DISCIPLINE, True, 80,
       note="This is interview discipline under another name."),

    _f("thread_surfacing", "lori-threads", "open-thread continuity",
       "thread_surface_present", "runtime71", TIER_WORKFLOW, False, 90,
       degradation="The thread is not surfaced this turn. It remains stored "
                   "server-side and surfaces on a later turn.",
       note="Safe to defer BECAUSE the thread is durable, not because the "
            "narrator could raise it again."),

    _f("bio_anchored_ask", "bio-builder", "Bio Builder anchored ask",
       "bio_anchored_surface_present", "runtime71", TIER_WORKFLOW, True, 100,
       affects_evidence=True,
       note="The operator surface is waiting on this specific answer; losing "
            "the anchor means the reply is attributed to nothing."),

    _f("witness_receipt", "lori-witness", "witness-mode receipt",
       "witness_receipt_present", "runtime71", TIER_WORKFLOW, True, 110,
       affects_evidence=True,
       note="Witness mode is an evidence posture. Running it without its "
            "receipt wording changes what the narrator is told was recorded."),

    _f("era_explanation", "life-map", "Era Explainer",
       "era_definition_requested", "runtime71", TIER_WORKFLOW, True, 120,
       note="The narrator ASKED what an era means. Dropping the answer to "
            "save tokens answers a direct question with silence."),

    _f("softened_response", "lori-safety", "softened response mode",
       "softened_state_active_and_not_parked", "runtime71",
       TIER_ACCESSIBILITY, True, 130,
       note="Its parked check is load-bearing: runtime safety is PARKED and "
            "must stay parked. When it IS active, it is required."),

    _f("identity_mode", "lori-identity", "identity collection",
       "identity_mode_active", "runtime71", TIER_WORKFLOW, True, 140,
       affects_evidence=True,
       note="An identity turn that loses its instructions asks nothing and "
            "records nothing."),

    _f("profile_seed_walk", "profile-onboarding",
       "the ordered ten-topic new-narrator profile walk",
       "profile_walk_active", "runtime71+db", TIER_WORKFLOW, True, 150,
       affects_evidence=True,
       note="PRESERVED. The 'retire for live narrators' decision was wrong "
            "and is withdrawn: this walk is the ONLY conversational filler "
            "for the nine profile_seed buckets, and a new Lorevox narrator "
            "may have no operator to seed them. Its activation is now "
            "profile_walk_active -- identity complete AND onboarding "
            "incomplete AND at least one meaningful topic unanswered. "
            "NARRATOR TYPE DOES NOT DECIDE WHETHER THE WALK EXISTS."),

    _f("pass_2a", "life-map", "era walk, pass 2a",
       "pass_2a", "runtime71", TIER_WORKFLOW, True, 160),

    _f("pass_2b", "life-map", "era walk, pass 2b",
       "pass_2b", "runtime71", TIER_WORKFLOW, True, 170),

    _f("current_mode", "lori-modes", "recognition/grounding/light modes",
       "current_mode_set", "runtime71", TIER_WORKFLOW, True, 180,
       note="The mode was chosen for this narrator; silently ignoring it is "
            "not a lighter version of it."),

    _f("cognitive_support", "wo-10c", "WO-10C cognitive support",
       "cognitive_support_mode", "runtime71", TIER_ACCESSIBILITY, True, 190,
       note="Accessibility, not workflow. When active it changes how a "
            "narrator is met, and it must never be traded for tokens."),

    _f("paired_interview", "operator-session", "paired interview",
       "paired_interview", "runtime71", TIER_WORKFLOW, True, 200),

    _f("visual_affect", "facial-awareness", "affect-derived pacing",
       "visual_affect_fresh", "runtime71", TIER_ACCESSIBILITY, False, 210,
       degradation="Pacing guidance is omitted and Lori proceeds at her "
                   "default pace. The no_visual_claims rule below still "
                   "forbids asserting anything she cannot evidence.",
       note="Requires a baseline AND a current reading; stale or absent "
            "evidence must produce nothing."),

    _f("no_visual_claims", "facial-awareness",
       "the ban on unevidenced visual claims",
       "always", "static", TIER_DISCIPLINE, True, 220,
       note="REQUIRED and unconditional. It must hold precisely when the "
            "affect family above is ABSENT, which is why it cannot share "
            "that family's condition."),

    _f("fatigue", "wo-10c", "fatigue pacing", "fatigue_elevated", "runtime71",
       TIER_ACCESSIBILITY, True, 230,
       note="Elevated fatigue is a narrator-wellbeing signal, not a hint."),
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
        # CORRECTED 2026-08-18. This rejected a required family that was
        # also conditional:
        #     if fam.required and fam.activation != "always": raise
        # That conflated the two words and was the whole error. A helper
        # turn's guidance is conditional AND required: it appears only in
        # the helper role, and a helper turn that silently loses it does
        # not become shorter, it becomes an interview.
        #
        # What IS a contradiction is a droppable family with no named
        # degradation, or a droppable family whose loss could affect
        # evidence. Both are now rejected.
        if not fam.required and not fam.degradation:
            raise ValueError(
                f"{fam.family_id}: a droppable family must name its safe "
                f"degradation, so the loss is observable rather than silent")
        if not fam.required and fam.affects_evidence:
            raise ValueError(
                f"{fam.family_id}: a family whose loss can affect persistence, "
                f"attribution or evidence capture may not be droppable")
        if fam.required and fam.degradation:
            raise ValueError(
                f"{fam.family_id}: a required family has no degradation; it "
                f"is kept or the turn refuses")
        if not fam.capability:
            raise ValueError(f"{fam.family_id}: no capability recorded")
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
