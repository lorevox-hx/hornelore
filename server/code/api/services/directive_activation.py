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
    `roles` is the branch, and it mirrors what the composer already does
    rather than proposing something new: helper and onboarding each build
    their own section and RETURN, so the entire interviewer tail --
    including the interview discipline and the visual-claims ban -- is
    reachable only on the interviewer path.

    (An earlier draft of this docstring claimed the role blocks
    "APPENDED rather than branching and execution fell through into the
    interview passes". That was wrong, and the composer's own comment
    said so: "They return early from the directive block so no pass/era/
    mode rules fire.")
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
_HELPER_ONLY = frozenset({ROLE_HELPER})
_ONBOARDING_ONLY = frozenset({ROLE_ONBOARDING})

# ── THE REGISTRY ────────────────────────────────────────────────────────
#
# CORRECTED 2026-08-18 against the composer's real branch structure. The
# first cut modelled helper and onboarding as APPENDING blocks that fell
# through into the interview material. They do not: both build their own
# section and RETURN, and the composer's own comment says so --
# "Helper and onboarding roles completely replace the interview
# directives. They return early from the directive block so no pass/era/
# mode rules fire."
#
# The real shape is three phases:
#
#   SHARED PRELUDE   every role. Runtime header, device time, location,
#                    memoir arc, speaker name, capabilities honesty,
#                    media, transparency.
#   ROLE-EXCLUSIVE   helper OR onboarding, each ending the assembly.
#   INTERVIEWER TAIL everything else -- and it is ALL interviewer-only,
#                    including the interview discipline itself and the
#                    ban on unevidenced visual claims.
#
# `render_order` follows the composer's line order, so with every family
# active the rendered block is byte-for-byte what it was.
_FAMILIES: List[DirectiveFamily] = [
    # ── shared prelude ──────────────────────────────────────────────
    _f("runtime_state", "lori-core", "the LORI_RUNTIME state header",
       "always", SOURCE_RUNTIME, TIER_IDENTITY, True, 10,
       note="Pass, era, mode, identity phase, role. Every directive "
            "below is read against it, and the transparency rule answers "
            "trust questions FROM it."),

    _f("device_time", "lori-core", "answering what day it is",
       "device_time_present", SOURCE_DEVICE, TIER_NARRATOR_CONTEXT, True, 20,
       note="Required when present. Losing it reproduces the live defect "
            "where Lori denied knowing the date while the date was in "
            "the prompt."),

    _f("narrator_location", "consent", "consented location context",
       "location_shared", SOURCE_RUNTIME, TIER_NARRATOR_CONTEXT, False, 30,
       degradation=DEGRADE_REBUILT_NEXT_TURN,
       note="Optional by its own wording -- 'do not bring it up unless "
            "relevant'."),

    _f("memoir_arc", "memoir", "memoir arc + meaning tags",
       "memoir_state_threads_or_draft", SOURCE_RUNTIME, TIER_WORKFLOW,
       False, 40, degradation=DEGRADE_DURABLE_ON_SERVER,
       note="Arc state is persisted; the next turn restores the steer."),

    _f("speaker_name", "lori-core", "addressing the narrator by name",
       "speaker_name_known", SOURCE_PROFILE, TIER_NARRATOR_CONTEXT, True, 50,
       note="Losing it makes Lori address a named person as a stranger."),

    _f("capabilities_honesty", "lori-trust",
       "honest answers about recording, camera and sensing",
       "style_directive_present", SOURCE_RUNTIME, TIER_DISCIPLINE, True, 60,
       note="MISMODELLED IN THE FIRST CUT as a non-default-style family. "
            "`_emitStyleDirective` ALWAYS returns the capabilities-honesty "
            "preamble (BUG-218) and appends a style suffix only when there "
            "is one -- so this is non-empty for oral history too. It is "
            "universal trust material, not style tuning."),

    _f("media_hints", "photo-intake", "photo-count context",
       "media_present", SOURCE_RUNTIME, TIER_NARRATOR_CONTEXT, True, 70,
       note="NOT an in-view signal. `media_count` is the narrator's TOTAL "
            "uploaded photo count; the first cut renamed the predicate "
            "'media_in_view', which would have claimed a turn-scoped "
            "signal the payload does not carry. Behaviour is preserved "
            "exactly; narrowing this needs a real in-view signal first."),

    _f("transparency_rule", "lori-trust",
       "never deny an active capability, never assert an inactive one",
       "always", SOURCE_STATIC, TIER_DISCIPLINE, True, 80,
       note="Universal by design and by its own comment -- 'must fire "
            "before role overrides so every role inherits it'. Prevents "
            "both false denial and false assertion about sensors."),

    # ── role-exclusive: each ENDS the assembly ──────────────────────
    _f("role_helper", "operator-roles", "helper role",
       "role_helper", SOURCE_RUNTIME, TIER_WORKFLOW, True, 100,
       roles=_HELPER_ONLY,
       note="Renders as the `directives_bio_builder` section -- a "
            "misnomer, recorded not renamed. A helper turn that loses "
            "this becomes an interview."),

    _f("role_onboarding", "operator-roles", "onboarding identity anchors",
       "role_onboarding", SOURCE_RUNTIME, TIER_WORKFLOW, True, 110,
       roles=_ONBOARDING_ONLY, affects_evidence=True,
       note="Renders as the `directives_questionnaire` section -- also a "
            "misnomer. Collects name/DOB/birthplace in strict sequence. "
            "Onboarding does NOT reach the later identity_mode block; it "
            "returns before it."),

    # ── interviewer tail: ALL of it is interviewer-only ─────────────
    _f("interview_core", "lori-discipline", "the interview discipline",
       "always", SOURCE_STATIC, TIER_DISCIPLINE, True, 200,
       roles=_INTERVIEW_ONLY,
       note="CORRECTED: interviewer-only, and it sits AFTER the shared "
            "prelude, not before it. The first cut had it universal at "
            "order 10. Helper and onboarding have already returned."),

    _f("oral_history_posture", "lori-discipline",
       "the default oral-history posture -- the narrator leads",
       "session_style_default_oral", SOURCE_STATIC, TIER_DISCIPLINE, True,
       210, roles=_INTERVIEW_ONLY,
       note="Fires for oral_history, empty, and any UNRECOGNISED style. "
            "The non-oral set is {warm_storytelling, companion, "
            "clear_direct, questionnaire_first, memory_exercise} -- read "
            "from the composer, after the first cut omitted `companion` "
            "and invented `guided_trip_walk`."),

    _f("story_mode", "lori-story", "story-mode override",
       "story_mode_active", SOURCE_RUNTIME, TIER_DISCIPLINE, True, 220,
       roles=_INTERVIEW_ONLY,
       note="Split from the question hierarchy: fires only at the story "
            "threshold, where the hierarchy fires across three modes."),

    _f("question_hierarchy", "lori-story", "the Layer 1-4 question ladder",
       "story_phase_active", SOURCE_RUNTIME, TIER_DISCIPLINE, True, 230,
       roles=_INTERVIEW_ONLY),

    _f("thread_surfacing", "lori-threads", "open-thread continuity",
       "thread_surface_present", SOURCE_RUNTIME, TIER_WORKFLOW, False, 240,
       roles=_INTERVIEW_ONLY, degradation=DEGRADE_DURABLE_ON_SERVER,
       note="Safe to defer BECAUSE the thread is stored server-side."),

    _f("bio_anchored_ask", "bio-builder", "Bio Builder anchored ask",
       "bio_anchored_surface_present", SOURCE_RUNTIME, TIER_WORKFLOW, True,
       250, roles=_INTERVIEW_ONLY, affects_evidence=True,
       note="Without the anchor the reply is attributed to nothing."),

    _f("witness_receipt", "lori-witness", "witness-mode receipt",
       "witness_receipt_present", SOURCE_RUNTIME, TIER_WORKFLOW, True, 260,
       roles=_INTERVIEW_ONLY, affects_evidence=True),

    _f("era_explanation", "life-map", "Era Explainer",
       "era_definition_requested", SOURCE_RUNTIME, TIER_WORKFLOW, True, 270,
       roles=_INTERVIEW_ONLY,
       note="The narrator ASKED. Dropping it answers a question with "
            "silence."),

    _f("softened_response", "lori-safety", "softened response mode",
       "softened_state_active_and_not_parked", SOURCE_RUNTIME,
       TIER_ACCESSIBILITY, True, 280, roles=_INTERVIEW_ONLY,
       note="Its parked check is load-bearing: runtime safety is PARKED "
            "and stays parked. Parking comes from the server flag, not "
            "the payload."),

    _f("identity_mode", "lori-identity", "identity anchor collection",
       "identity_mode_active", SOURCE_RUNTIME, TIER_WORKFLOW, True, 290,
       roles=_INTERVIEW_ONLY, affects_evidence=True,
       note="CORRECTED: interviewer-only. Onboarding returns before this "
            "block. `identity_mode` is COMPUTED by the composer as "
            "`(effective_pass == 'identity') or (not identity_complete)` "
            "-- it is not a runtime71 key, and reading it as one would "
            "have deactivated identity collection entirely."),

    _f("profile_seed_walk", "profile-onboarding",
       "the ordered ten-topic new-narrator profile walk",
       "profile_walk_pass1", SOURCE_RUNTIME, TIER_WORKFLOW, True, 300,
       roles=_INTERVIEW_ONLY, affects_evidence=True,
       note="PRESERVED, trigger UNCHANGED at current_pass == 'pass1'. "
            "The intended onboarding-completion gate has no production "
            "resolver and the browser promotes pass1 -> pass2a when "
            "chronology is ready, so its new-narrator reachability is a "
            "recorded DEBT rather than a claim. Never gated by narrator "
            "type; never auto-activated for historical incomplete "
            "profiles."),

    _f("pass_2a", "life-map", "era walk, pass 2a", "pass_2a", SOURCE_RUNTIME,
       TIER_WORKFLOW, True, 310, roles=_INTERVIEW_ONLY),

    _f("pass_2b", "life-map", "era walk, pass 2b", "pass_2b", SOURCE_RUNTIME,
       TIER_WORKFLOW, True, 320, roles=_INTERVIEW_ONLY),

    _f("current_mode", "lori-modes", "recognition/grounding/light modes",
       "current_mode_set", SOURCE_RUNTIME, TIER_WORKFLOW, True, 330,
       roles=_INTERVIEW_ONLY),

    _f("cognitive_support", "wo-10c", "WO-10C cognitive support",
       "cognitive_support_mode", SOURCE_RUNTIME, TIER_ACCESSIBILITY, True,
       340, roles=_INTERVIEW_ONLY,
       note="Accessibility, not workflow: it changes how a narrator is "
            "met, and is never traded for tokens."),

    _f("cognitive_variant", "wo-10c", "recognition/alongside variants",
       "cognitive_variant_set", SOURCE_RUNTIME, TIER_ACCESSIBILITY, True,
       350, roles=_INTERVIEW_ONLY),

    _f("paired_interview", "operator-session", "paired interview",
       "paired_interview", SOURCE_RUNTIME, TIER_WORKFLOW, True, 360,
       roles=_INTERVIEW_ONLY),

    _f("visual_affect", "facial-awareness", "affect-derived pacing",
       "visual_affect_present", SOURCE_RUNTIME, TIER_ACCESSIBILITY, False,
       370, roles=_INTERVIEW_ONLY, degradation=DEGRADE_COSMETIC,
       note="Composer condition is `v_baseline and v_affect`. There is no "
            "freshness signal in the payload; the first cut invented one."),

    _f("no_visual_claims", "facial-awareness",
       "the ban on unevidenced visual claims", "always", SOURCE_STATIC,
       TIER_DISCIPLINE, True, 380, roles=_INTERVIEW_ONLY,
       note="CORRECTED: interviewer-only in the current composer, not "
            "universal. It must still hold precisely when the affect "
            "family above is ABSENT, which is why it stays unconditional "
            "WITHIN that role."),

    _f("fatigue", "wo-10c", "fatigue pacing", "fatigue_elevated",
       SOURCE_RUNTIME, TIER_ACCESSIBILITY, True, 390,
       roles=_INTERVIEW_ONLY,
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


# ── THE EVALUATED ASSEMBLY ──────────────────────────────────────────────
#
# Role eligibility AND predicate evaluation, in one place, returning the
# families that are actually active for this turn in render order. This
# is what a consumer calls; without it the registry is an inventory and
# the predicates are unreferenced functions.


class ActiveFamily(NamedTuple):
    """A family that is active this turn, with its policy attached."""

    family_id: str
    policy: DirectiveFamily
    #: True when the budget may not remove it. Mirrors `policy.required`,
    #: surfaced here so a consumer need not reach back into the policy.
    required: bool


def active_families(state) -> List[ActiveFamily]:
    """The families active for this turn, in composer render order.

    Two gates, in order, and both must pass:

      1. ROLE eligibility -- a helper turn never even considers the
         interview passes, because the composer returns before them.
      2. The family's activation PREDICATE against the turn state.

    A family absent from this list is absent because its feature is
    inactive on this turn. It is never absent merely to save tokens.
    """
    from .directive_predicates import evaluate as _evaluate

    role = getattr(state, "role", "") or ROLE_INTERVIEWER
    out: List[ActiveFamily] = []
    for fid in families_for_role(role):
        fam = REGISTRY[fid]
        if _evaluate(fam.activation, state):
            out.append(ActiveFamily(fid, fam, fam.required))
    return out


def inactive_families(state) -> List[str]:
    """Role-eligible families whose condition did not fire.

    Reported separately from role-ineligible ones: "your feature is off"
    and "this conversation is not that kind of conversation" are
    different answers, and a diagnostic that merges them cannot explain
    why an instruction is missing.
    """
    from .directive_predicates import evaluate as _evaluate

    role = getattr(state, "role", "") or ROLE_INTERVIEWER
    return [fid for fid in families_for_role(role)
            if not _evaluate(REGISTRY[fid].activation, state)]
