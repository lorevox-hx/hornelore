"""Executable activation predicates for directive families.

WO-LEAN-LORI-DIRECTIVE-ACTIVATION-01, 2026-08-18.

── WHY THIS MODULE DOES NOT PARSE runtime71 ────────────────────────────

The first cut built `TurnState` by inferring key names from predicate
names. Eleven of them were wrong: device time, location, memoir state
and visual signals live in NESTED sub-objects (`device_context`,
`location_context`, `memoir_context`, `visual_signals`); `identity_mode`
is not sent at all but COMPUTED by the composer as
`(effective_pass == "identity") or (not identity_complete)`; safety
parking comes from a server flag rather than the payload; and several
defaults differ from the composer's.

Wiring that in would have suppressed live capabilities -- most seriously
identity collection, which would have activated never.

So this module does not read `runtime71`. `TurnState` is built FROM THE
COMPOSER'S ALREADY-NORMALISED LOCALS, at the point where they have been
derived once and correctly. One derivation, one shape; the gates cannot
drift from the values the prompt is actually built from. Same principle
as one renderer and one joiner.

── WHAT A PREDICATE MAY DO ─────────────────────────────────────────────

Read state, return a bool. No I/O, no mutation, never fatal: an
exception in a gate would decide a narrator's prompt by accident.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, NamedTuple, Optional

logger = logging.getLogger("directive_predicates")

__all__ = ["TurnState", "PREDICATES", "predicate_for", "evaluate",
           "UnknownPredicateError", "state_from_composer",
           "NON_ORAL_STYLES"]


class UnknownPredicateError(KeyError):
    """A predicate id with no implementation."""


#: Verbatim from the composer's `_KNOWN_NON_ORAL_STYLES`. `companion` was
#: missing from the first cut and `guided_trip_walk` was invented; both
#: errors came from writing the set from memory instead of reading it.
NON_ORAL_STYLES = frozenset({
    "warm_storytelling", "companion", "clear_direct",
    "questionnaire_first", "memory_exercise",
})


class TurnState(NamedTuple):
    """The gate inputs, taken from the composer's derived locals.

    Every field is the composer's own variable, already normalised --
    era canonicalised, defaults applied, nested contexts unwrapped,
    `identity_mode` computed. Nothing here re-derives anything.
    """

    role: str
    current_pass: str
    effective_pass: str
    current_era: str
    current_mode: str
    identity_mode: bool
    identity_complete: bool
    identity_phase: str
    session_style: str
    style_directive: str
    speaker_name: str
    device_date: str
    device_time: str
    location_label: str
    media_count: int
    memoir_state: str
    story_momentum: str
    thread_surface: str
    anchored_surface: str
    witness_block: bool
    era_definition_requested: bool
    softened_state: bool
    softened_parked: bool
    cognitive_support_mode: bool
    cognitive_mode: str
    paired: bool
    visual_baseline: bool
    visual_affect: str
    visual_gaze: Any
    fatigue_score: int


def state_from_composer(*, assistant_role, current_pass, effective_pass,
                        current_era, current_mode, identity_mode,
                        identity_complete, identity_phase, session_style,
                        style_directive, speaker_name, device_date,
                        device_time, location_label, media_count,
                        memoir_state, story_momentum, thread_surface,
                        anchored_surface, witness_block,
                        era_definition_requested, softened_state,
                        softened_parked, cognitive_support_mode,
                        cognitive_mode, paired, visual_baseline,
                        visual_affect, visual_gaze, fatigue_score
                        ) -> TurnState:
    """Build the gate state from values the composer has already derived.

    Keyword-only and exhaustive on purpose: adding a gate input must be a
    deliberate edit at the one call site, not a quiet `.get()` somewhere
    that reintroduces the shape drift this replaces.
    """
    def _s(v):
        return (str(v).strip() if v is not None else "")

    def _i(v):
        try:
            return int(v or 0)
        except Exception:
            return 0

    return TurnState(
        role=_s(assistant_role) or "interviewer",
        current_pass=_s(current_pass),
        effective_pass=_s(effective_pass),
        current_era=_s(current_era),
        current_mode=_s(current_mode),
        identity_mode=bool(identity_mode),
        identity_complete=bool(identity_complete),
        identity_phase=_s(identity_phase),
        session_style=_s(session_style).lower(),
        style_directive=_s(style_directive),
        speaker_name=_s(speaker_name),
        device_date=_s(device_date),
        device_time=_s(device_time),
        location_label=_s(location_label),
        media_count=_i(media_count),
        memoir_state=_s(memoir_state),
        story_momentum=_s(story_momentum),
        thread_surface=_s(thread_surface),
        anchored_surface=_s(anchored_surface),
        witness_block=bool(witness_block),
        era_definition_requested=bool(era_definition_requested),
        softened_state=bool(softened_state),
        softened_parked=bool(softened_parked),
        cognitive_support_mode=bool(cognitive_support_mode),
        cognitive_mode=_s(cognitive_mode),
        paired=bool(paired),
        visual_baseline=bool(visual_baseline),
        visual_affect=_s(visual_affect),
        visual_gaze=visual_gaze,
        fatigue_score=_i(fatigue_score),
    )


def _profile_walk_pass1(s: TurnState) -> bool:
    """The ten-topic new-narrator walk. PRESERVED, trigger UNCHANGED.

    ── REACHABILITY DEBT, RECORDED RATHER THAN PAPERED OVER ────────────
    The intended gate is "onboarding incomplete AND topics remain". No
    production caller computes either value: there is no server-owned
    profile-completion resolver, and the browser promotes `pass1 ->
    pass2a` as soon as chronology is ready. So an intended gate would
    have been a gate on values nobody supplies.

    Two wrong answers were available. Gating by narrator type is wrong --
    the walk is about what is still unknown, not about who the narrator
    is. Auto-activating on any incomplete profile is also wrong -- it
    would start a ten-topic questionnaire for every historical narrator
    whose profile has a gap, which is interrogation, not onboarding.

    So the EXISTING trigger is preserved exactly: `current_pass ==
    "pass1"`. Behaviour is unchanged, no narrator gains or loses the
    walk, and the debt is that its new-narrator reachability is not
    proven here. Resolving it needs a real completion resolver and a
    decision about the pass1 -> pass2a promotion, which is product work,
    not a predicate.
    """
    return s.current_pass == "pass1"


def _visual_affect_present(s: TurnState) -> bool:
    """Exactly the composer's condition: `v_baseline and v_affect`.

    Not "freshness" -- there is no freshness signal in the payload, and
    inventing one would be a claim the data does not support.
    """
    return bool(s.visual_baseline and s.visual_affect)


PREDICATES: Dict[str, Callable[[TurnState], bool]] = {
    "always": lambda s: True,
    "device_time_present": lambda s: bool(s.device_date or s.device_time),
    "location_shared": lambda s: bool(s.location_label),
    "memoir_state_threads_or_draft":
        lambda s: s.memoir_state in ("threads", "draft"),
    "speaker_name_known": lambda s: bool(s.speaker_name),
    #: The capabilities-honesty preamble is ALWAYS emitted (BUG-218), so
    #: this is non-empty even for oral history. Gating on the emitted
    #: directive rather than on a list of style names is what the
    #: composer actually does.
    "style_directive_present": lambda s: bool(s.style_directive),
    "media_present": lambda s: s.media_count > 0,
    "role_helper": lambda s: s.role == "helper",
    "role_onboarding": lambda s: s.role == "onboarding",
    "role_interviewer": lambda s: s.role == "interviewer",
    "session_style_default_oral":
        lambda s: s.session_style not in NON_ORAL_STYLES,
    "story_mode_active": lambda s: s.story_momentum == "story",
    "story_phase_active":
        lambda s: s.story_momentum in ("story", "emerging", "normal"),
    "thread_surface_present": lambda s: bool(s.thread_surface),
    "bio_anchored_surface_present": lambda s: bool(s.anchored_surface),
    "witness_receipt_present": lambda s: bool(s.witness_block),
    "era_definition_requested": lambda s: bool(s.era_definition_requested),
    "softened_state_active_and_not_parked":
        lambda s: bool(s.softened_state and not s.softened_parked),
    "identity_mode_active": lambda s: bool(s.identity_mode),
    "profile_walk_pass1": _profile_walk_pass1,
    "pass_2a": lambda s: s.current_pass == "pass2a",
    "pass_2b": lambda s: s.current_pass == "pass2b",
    "current_mode_set":
        lambda s: s.current_mode in ("recognition", "grounding", "light"),
    "cognitive_support_mode": lambda s: bool(s.cognitive_support_mode),
    "cognitive_variant_set":
        lambda s: s.cognitive_mode in ("recognition", "alongside"),
    "paired_interview": lambda s: bool(s.paired),
    "visual_affect_present": _visual_affect_present,
    "fatigue_elevated": lambda s: s.fatigue_score >= 50,
}


def predicate_for(predicate_id: str) -> Callable[[TurnState], bool]:
    try:
        return PREDICATES[predicate_id]
    except KeyError:
        raise UnknownPredicateError(
            f"{predicate_id!r} has no implementation. A named predicate "
            f"nobody evaluates is an inventory entry, not a gate."
        ) from None


def evaluate(predicate_id: str, state: TurnState) -> bool:
    """Run a gate. Never fatal; a failing gate reports INACTIVE and logs,
    because a family included by accident is a narrator receiving an
    instruction nobody chose."""
    try:
        return bool(predicate_for(predicate_id)(state))
    except UnknownPredicateError:
        raise
    except Exception as exc:
        logger.warning("[directive-gate] %s failed, treating as inactive: %s",
                       predicate_id, exc)
        return False
