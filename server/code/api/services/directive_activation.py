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

from typing import Dict, FrozenSet, List, NamedTuple

from .directive_predicates import PREDICATES as _PREDICATE_IMPLS
from .prompt_policy_vocab import (
    ALL_ROLES, DEGRADATIONS, DEGRADE_COSMETIC, DEGRADE_DURABLE_ON_SERVER,
    DEGRADE_NONE, DEGRADE_REBUILT_NEXT_TURN, DROPPABLE_DEGRADATIONS,
    ROLE_HELPER, ROLE_INTERVIEWER, ROLE_ONBOARDING, ROLES,
    SOURCE_DEVICE, SOURCE_PROFILE, SOURCE_RUNTIME, SOURCE_SERVER_DB,
    SOURCE_STATIC, SOURCES, TIER_ACCESSIBILITY, TIER_DISCIPLINE,
    TIER_IDENTITY, TIER_NARRATOR_CONTEXT, TIER_WORKFLOW, TIERS,
)

__all__ = [
    "DirectiveFamily", "UnknownFamilyError", "UnknownPredicateError",
    "ACTIVATION_PREDICATES", "REGISTRY", "family_for",
    "family_ids_in_render_order", "required_family_ids",
    "conditional_family_ids", "families_for_role",
]

#: The predicate ids a family may name. Sourced from the module that
#: IMPLEMENTS them, so a family cannot name a gate nobody evaluates --
#: the failure the first cut allowed, where activation was a string and
#: nothing ran it.
ACTIVATION_PREDICATES: FrozenSet[str] = frozenset(_PREDICATE_IMPLS)


class UnknownFamilyError(KeyError):
    """A directive family id with no registered policy."""


class UnknownPredicateError(ValueError):
    """A family naming an activation predicate that has no implementation."""


class DirectiveFamily(NamedTuple):
    """Declarative facts about one directive family.

    ── THE TWO WORDS DO DIFFERENT JOBS ─────────────────────────────────
        `activation`  decides whether the family is PRESENT this turn.
        `required`    decides whether the budget may REMOVE it once
                      present.

    Independent. A helper turn's guidance is conditional -- it appears
    only in the helper role -- and required once it appears, because a
    helper turn that silently loses it becomes an interview.

    ── ROLES ───────────────────────────────────────────────────────────
    `roles` is the branch. Helper and onboarding turns must not inherit
    interviewer-only directives; before this field they did, because the
    role blocks APPENDED rather than branching and execution fell
    through into the interview passes.
    """

    family_id: str
    owner: str
    capability: str
    activation: str
    #: Which conversations this family belongs to.
    roles: FrozenSet[str]
    source: str
    priority_tier: str
    required: bool
    #: A member of the closed degradation set. The forbidden rationale --
    #: that the narrator can be asked again -- is not a member and so
    #: cannot be expressed.
    degradation: str
    affects_evidence: bool
    render_order: int
    note: str = ""


def _f(family_id, owner, capability, activation, source, tier, required,
       order, roles=ALL_ROLES, degradation=DEGRADE_NONE,
       affects_evidence=False, note=""):
    return DirectiveFamily(
        family_id=family_id, owner=owner, capability=capability,
        activation=activation, roles=frozenset(roles), source=source,
        priority_tier=tier, required=required, degradation=degradation,
        affects_evidence=affects_evidence, render_order=order, note=note)


_INTERVIEW_ONLY = frozenset({ROLE_INTERVIEWER})

# ── THE REGISTRY ────────────────────────────────────────────────────────
# `render_order` reproduces today's composition order, so with every
# family active the rendered block is byte-for-byte what it was.
_FAMILIES: List[DirectiveFamily] = [
    _f("runtime_state", "lori-core", "the LORI_RUNTIME state header",
       "always", SOURCE_RUNTIME, TIER_IDENTITY, True, 5,
       note="Pass, era, mode, identity phase, role. Every downstream "
            "directive is read against it."),

    _f("device_time", "lori-core", "answering what day it is",
       "device_time_present", SOURCE_DEVICE, TIER_NARRATOR_CONTEXT, True, 8,
       note="Required when present. Losing it reproduces the live defect "
            "where Lori claimed she could not know the date while the "
            "date was in the prompt."),

    _f("narrator_location", "consent", "consented location context",
       "location_shared", SOURCE_RUNTIME, TIER_NARRATOR_CONTEXT, False, 12,
       degradation=DEGRADE_REBUILT_NEXT_TURN,
       note="Explicitly optional context by its own wording."),

    _f("interview_core", "lori-discipline", "the interview itself",
       "always", SOURCE_STATIC, TIER_DISCIPLINE, True, 10,
       note="Without it Lori reverts to a generic assistant."),

    _f("memoir_arc", "memoir", "memoir arc + meaning tags",
       "memoir_state_threads_or_draft", SOURCE_RUNTIME, TIER_WORKFLOW,
       False, 20, roles=_INTERVIEW_ONLY,
       degradation=DEGRADE_DURABLE_ON_SERVER,
       note="Arc state is persisted; the next turn restores the steer."),

    _f("speaker_name", "lori-core", "addressing the narrator by name",
       "speaker_name_known", SOURCE_PROFILE, TIER_NARRATOR_CONTEXT, True, 30,
       note="Losing it makes Lori address a named person as a stranger."),

    _f("session_style", "operator-session", "operator-selected session style",
       "session_style_non_default", SOURCE_RUNTIME, TIER_WORKFLOW, True, 40,
       roles=_INTERVIEW_ONLY,
       note="An operator chose a non-default style; silently reverting is "
            "a different session, not a shorter one."),

    _f("oral_history_posture", "lori-discipline",
       "the default oral-history posture -- the narrator leads",
       "session_style_default_oral", SOURCE_STATIC, TIER_DISCIPLINE, True, 42,
       roles=_INTERVIEW_ONLY,
       note="The load-bearing block for the DEFAULT style. It was absent "
            "from the first inventory, which would have made the default "
            "posture the one thing nobody had declared."),

    _f("media_hints", "photo-intake", "photo/media handling",
       "media_in_view", SOURCE_RUNTIME, TIER_WORKFLOW, True, 50,
       affects_evidence=True,
       note="NARROWED: in view this turn, not merely on file. A narrator "
            "with a large archive and nothing on screen is not doing a "
            "photo task."),

    _f("role_helper", "operator-roles", "helper role",
       "role_helper", SOURCE_RUNTIME, TIER_WORKFLOW, True, 60,
       roles=frozenset({ROLE_HELPER}),
       note="A helper turn that loses its guidance becomes an interview."),

    _f("role_onboarding", "operator-roles", "onboarding role",
       "role_onboarding", SOURCE_RUNTIME, TIER_WORKFLOW, True, 70,
       roles=frozenset({ROLE_ONBOARDING}), affects_evidence=True,
       note="Strands the narrator mid-onboarding if lost."),

    _f("story_mode", "lori-story", "story-mode override",
       "story_mode_active", SOURCE_RUNTIME, TIER_DISCIPLINE, True, 80,
       roles=_INTERVIEW_ONLY,
       note="SPLIT from the question hierarchy: they have different "
            "conditions -- story mode fires only at the story threshold."),

    _f("question_hierarchy", "lori-story", "the Layer 1-4 question ladder",
       "story_phase_active", SOURCE_RUNTIME, TIER_DISCIPLINE, True, 84,
       roles=_INTERVIEW_ONLY,
       note="Interview discipline under another name."),

    _f("thread_surfacing", "lori-threads", "open-thread continuity",
       "thread_surface_present", SOURCE_RUNTIME, TIER_WORKFLOW, False, 90,
       roles=_INTERVIEW_ONLY, degradation=DEGRADE_DURABLE_ON_SERVER,
       note="Safe to defer BECAUSE the thread is stored server-side."),

    _f("bio_anchored_ask", "bio-builder", "Bio Builder anchored ask",
       "bio_anchored_surface_present", SOURCE_RUNTIME, TIER_WORKFLOW, True,
       100, roles=_INTERVIEW_ONLY, affects_evidence=True,
       note="Without the anchor the reply is attributed to nothing."),

    _f("witness_receipt", "lori-witness", "witness-mode receipt",
       "witness_receipt_present", SOURCE_RUNTIME, TIER_WORKFLOW, True, 110,
       roles=_INTERVIEW_ONLY, affects_evidence=True,
       note="Witness mode is an evidence posture."),

    _f("era_explanation", "life-map", "Era Explainer",
       "era_definition_requested", SOURCE_RUNTIME, TIER_WORKFLOW, True, 120,
       roles=_INTERVIEW_ONLY,
       note="The narrator ASKED. Dropping it answers a question with "
            "silence."),

    _f("softened_response", "lori-safety", "softened response mode",
       "softened_state_active_and_not_parked", SOURCE_RUNTIME,
       TIER_ACCESSIBILITY, True, 130,
       note="Its parked check is load-bearing: runtime safety is PARKED "
            "and stays parked. When active, it is required."),

    _f("identity_mode", "lori-identity", "identity anchor collection",
       "identity_mode_active", SOURCE_RUNTIME, TIER_WORKFLOW, True, 140,
       roles=frozenset({ROLE_INTERVIEWER, ROLE_ONBOARDING}),
       affects_evidence=True,
       note="An identity turn that loses its instructions asks nothing "
            "and records nothing."),

    _f("profile_seed_walk", "profile-onboarding",
       "the ordered ten-topic new-narrator profile walk",
       "profile_walk_active", SOURCE_SERVER_DB, TIER_WORKFLOW, True, 150,
       roles=_INTERVIEW_ONLY, affects_evidence=True,
       note="PRESERVED. The only conversational filler for the nine "
            "profile_seed buckets, and a new Lorevox narrator may have no "
            "operator to seed them. Gated on INCOMPLETE ONBOARDING, never "
            "on narrator type."),

    _f("pass_2a", "life-map", "era walk, pass 2a", "pass_2a", SOURCE_RUNTIME,
       TIER_WORKFLOW, True, 160, roles=_INTERVIEW_ONLY),

    _f("pass_2b", "life-map", "era walk, pass 2b", "pass_2b", SOURCE_RUNTIME,
       TIER_WORKFLOW, True, 170, roles=_INTERVIEW_ONLY),

    _f("current_mode", "lori-modes", "recognition/grounding/light modes",
       "current_mode_set", SOURCE_RUNTIME, TIER_WORKFLOW, True, 180,
       roles=_INTERVIEW_ONLY,
       note="The mode was chosen for this narrator."),

    _f("cognitive_support", "wo-10c", "WO-10C cognitive support",
       "cognitive_support_mode", SOURCE_RUNTIME, TIER_ACCESSIBILITY, True,
       190,
       note="Accessibility, not workflow: it changes how a narrator is "
            "met, and is never traded for tokens."),

    _f("cognitive_variant", "wo-10c", "recognition/alongside variants",
       "cognitive_variant_set", SOURCE_RUNTIME, TIER_ACCESSIBILITY, True, 194,
       note="SPLIT from cognitive_support: a different condition governs "
            "the variant wording from the one that enables the mode."),

    _f("paired_interview", "operator-session", "paired interview",
       "paired_interview", SOURCE_RUNTIME, TIER_WORKFLOW, True, 200),

    _f("visual_affect", "facial-awareness", "affect-derived pacing",
       "visual_affect_fresh", SOURCE_RUNTIME, TIER_ACCESSIBILITY, False, 210,
       degradation=DEGRADE_COSMETIC,
       note="Requires baseline AND current reading AND freshness. Stale "
            "evidence produces nothing; the ban below still holds."),

    _f("no_visual_claims", "facial-awareness",
       "the ban on unevidenced visual claims", "always", SOURCE_STATIC,
       TIER_DISCIPLINE, True, 220,
       note="REQUIRED and unconditional. It must hold precisely when the "
            "affect family is ABSENT."),

    _f("fatigue", "wo-10c", "fatigue pacing", "fatigue_elevated",
       SOURCE_RUNTIME, TIER_ACCESSIBILITY, True, 230,
       note="A narrator-wellbeing signal, not a hint."),
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
                f"{fam.family_id}: activation {fam.activation!r} has no "
                f"implementation in directive_predicates")
        if fam.priority_tier not in TIERS:
            raise ValueError(f"{fam.family_id}: unknown tier")
        if fam.source not in SOURCES:
            raise ValueError(f"{fam.family_id}: unknown source")
        if fam.degradation not in DEGRADATIONS:
            raise ValueError(f"{fam.family_id}: unknown degradation")
        if not fam.roles or not (fam.roles <= ROLES):
            raise ValueError(f"{fam.family_id}: bad roles {sorted(fam.roles)}")
        if not fam.owner or not fam.capability:
            raise ValueError(f"{fam.family_id}: owner and capability required")
        # activation decides PRESENCE; required decides POST-ACTIVATION
        # protection. A conditional family may be required.
        if fam.required and fam.degradation != DEGRADE_NONE:
            raise ValueError(
                f"{fam.family_id}: a required family has no degradation; it "
                f"is kept or the turn refuses")
        if not fam.required and fam.degradation not in DROPPABLE_DEGRADATIONS:
            raise ValueError(
                f"{fam.family_id}: a droppable family must name how it "
                f"degrades, from the closed set")
        if not fam.required and fam.affects_evidence:
            raise ValueError(
                f"{fam.family_id}: a family whose loss can affect "
                f"persistence or attribution may not be droppable")
        orders.append(fam.render_order)
        reg[fam.family_id] = fam
    if len(orders) != len(set(orders)):
        raise ValueError("two directive families share a render_order")
    return reg


REGISTRY: Dict[str, DirectiveFamily] = _build(_FAMILIES)


def family_for(family_id: str) -> DirectiveFamily:
    try:
        return REGISTRY[family_id]
    except KeyError:
        raise UnknownFamilyError(
            f"{family_id!r} is not a registered directive family."
        ) from None


def family_ids_in_render_order() -> List[str]:
    return [f.family_id for f in sorted(_FAMILIES, key=lambda x: x.render_order)]


def families_for_role(role: str) -> List[str]:
    """The families that may appear in this conversation at all.

    The branch. A helper turn never even considers the interview passes.
    """
    return [f.family_id for f in sorted(_FAMILIES, key=lambda x: x.render_order)
            if role in f.roles]


def required_family_ids() -> List[str]:
    return [f.family_id for f in _FAMILIES if f.required]


def conditional_family_ids() -> List[str]:
    return [f.family_id for f in _FAMILIES if not f.required]
