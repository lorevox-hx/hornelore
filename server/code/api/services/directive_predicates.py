"""Executable activation predicates for directive families.

WO-LEAN-LORI-DIRECTIVE-ACTIVATION-01, 2026-08-18.

The first cut declared activation as a STRING NAME. A name is an
inventory, not a gate: it tells a reader which condition is meant and
lets nothing act on it, which is the same shape as the `drop_order` that
sat unread for a whole phase.

Each predicate here is a function of one `TurnState`. The registry names
them; this module evaluates them; the composer asks.

── WHAT A PREDICATE MAY AND MAY NOT DO ─────────────────────────────────

It reads state and returns a bool. It performs no I/O, mutates nothing,
and never raises: an exception in a gate would decide a narrator's
prompt by accident. `TurnState` is built once per turn by the caller,
which is the only place that touches runtime71 or the database.

── NARROWNESS IS THE POINT ─────────────────────────────────────────────

A capability's instructions belong in the prompt when the capability is
ACTIVE THIS TURN -- not when the narrator merely has data of that kind
on file. `media_present` is the worked example: a narrator with 400
archived photos and none in view this turn does not need photo-handling
instructions, and sending them on every turn is precisely the waste this
item removes. Stored data is not an active task.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, NamedTuple, Optional

logger = logging.getLogger("directive_predicates")

__all__ = ["TurnState", "PREDICATES", "predicate_for", "evaluate",
           "UnknownPredicateError", "build_turn_state"]


class UnknownPredicateError(KeyError):
    """A predicate id with no implementation."""


class TurnState(NamedTuple):
    """Everything the gates are allowed to see, resolved once per turn.

    Built by `build_turn_state` from runtime71 plus server-resolved
    facts. A predicate that needs something absent from here needs this
    record extended -- deliberately, in one place -- rather than reaching
    into runtime71 on its own.
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
    speaker_name: str
    # Device / consent context
    device_date: str
    device_time: str
    location_label: str
    # Task activity -- narrow, turn-scoped
    media_in_view: int
    memoir_state: str
    story_momentum: str
    thread_surface: str
    anchored_surface: str
    witness_block: bool
    era_definition_requested: bool
    softened_active: bool
    softened_parked: bool
    cognitive_support_mode: bool
    cognitive_mode: str
    paired: bool
    visual_baseline: bool
    visual_affect: str
    visual_fresh: bool
    fatigue_score: int
    # Profile onboarding -- the ten-topic walk
    profile_onboarding_complete: bool
    unanswered_profile_topics: tuple


def _s(d: Dict[str, Any], key: str, default: str = "") -> str:
    v = d.get(key)
    return (str(v).strip() if v is not None else default) or default


def build_turn_state(runtime71: Optional[Dict[str, Any]],
                     *,
                     unanswered_profile_topics=(),
                     profile_onboarding_complete: bool = False,
                     visual_fresh: bool = False) -> TurnState:
    """Resolve the gate inputs once, from runtime71 plus server facts.

    `unanswered_profile_topics` and `profile_onboarding_complete` are
    supplied by the caller because they are SERVER truth -- computed from
    the profile, not asserted by the browser. Narrator type is not an
    input at all: it does not decide whether the walk exists.
    """
    rt = runtime71 if isinstance(runtime71, dict) else {}
    try:
        fatigue = int(rt.get("fatigue_score") or 0)
    except Exception:
        fatigue = 0
    try:
        media = int(rt.get("media_count") or 0)
    except Exception:
        media = 0
    return TurnState(
        role=_s(rt, "assistant_role", "interviewer"),
        current_pass=_s(rt, "current_pass"),
        effective_pass=_s(rt, "effective_pass"),
        current_era=_s(rt, "current_era"),
        current_mode=_s(rt, "current_mode"),
        identity_mode=bool(rt.get("identity_mode")),
        identity_complete=bool(rt.get("identity_complete")),
        identity_phase=_s(rt, "identity_phase"),
        session_style=_s(rt, "session_style"),
        speaker_name=_s(rt, "speaker_name"),
        device_date=_s(rt, "device_date"),
        device_time=_s(rt, "device_time"),
        location_label=_s(rt, "location_label"),
        media_in_view=media,
        memoir_state=_s(rt, "memoir_state"),
        story_momentum=_s(rt, "story_first_momentum_mode"),
        thread_surface=_s(rt, "story_first_thread_surface_text"),
        anchored_surface=_s(rt, "bio_anchored_surface_text"),
        witness_block=bool(rt.get("witness_receipt_text")),
        era_definition_requested=bool(rt.get("era_definition_requested")),
        softened_active=bool(rt.get("softened_state")),
        softened_parked=bool(rt.get("safety_parked")),
        cognitive_support_mode=bool(rt.get("cognitive_support_mode")),
        cognitive_mode=_s(rt, "cognitive_mode"),
        paired=bool(rt.get("paired")),
        visual_baseline=bool(rt.get("visual_baseline")),
        visual_affect=_s(rt, "affect_state"),
        visual_fresh=bool(visual_fresh),
        fatigue_score=fatigue,
        profile_onboarding_complete=bool(profile_onboarding_complete),
        unanswered_profile_topics=tuple(unanswered_profile_topics or ()),
    )


# Session styles that are NOT the oral-history default.
_NON_ORAL_STYLES = frozenset({
    "questionnaire_first", "clear_direct", "warm_storytelling",
    "memory_exercise", "guided_trip_walk",
})


def _always(_s: TurnState) -> bool:
    return True


def _profile_walk_active(s: TurnState) -> bool:
    """The ten-topic new-narrator walk.

    PRESERVED, and gated on what is still unknown rather than on who the
    narrator is. Narrator type is deliberately absent from this function.

    Three conditions, all required:
      * identity is complete -- the walk builds on the anchors, it does
        not replace collecting them;
      * profile onboarding is not finished;
      * at least one meaningful topic is still unanswered.

    The caller computes the unanswered set, and it must not treat a
    birthplace as proof of a childhood home, nor an age-derived life
    stage as proof of retired-or-still-working.
    """
    return (s.identity_complete
            and not s.profile_onboarding_complete
            and bool(s.unanswered_profile_topics))


def _media_in_view(s: TurnState) -> bool:
    """Narrowed deliberately.

    Stored photographs are not an active photo task. This asks whether
    media is in view for THIS turn, so a narrator with a large archive
    and nothing on screen is not sent photo-handling instructions on
    every turn of an ordinary conversation.
    """
    return s.media_in_view > 0


def _visual_affect_fresh(s: TurnState) -> bool:
    """Requires a baseline AND a current reading AND freshness.

    Stale evidence must produce nothing: the no-visual-claims rule is
    what holds when this is absent, and it is unconditional.
    """
    return bool(s.visual_baseline and s.visual_affect and s.visual_fresh)


PREDICATES: Dict[str, Callable[[TurnState], bool]] = {
    "always": _always,
    "runtime_present": lambda s: True,
    "device_time_present": lambda s: bool(s.device_date or s.device_time),
    "location_shared": lambda s: bool(s.location_label),
    "memoir_state_threads_or_draft": lambda s: s.memoir_state in ("threads", "draft"),
    "speaker_name_known": lambda s: bool(s.speaker_name),
    "session_style_default_oral": lambda s: s.session_style not in _NON_ORAL_STYLES,
    "session_style_non_default": lambda s: s.session_style in _NON_ORAL_STYLES,
    "media_in_view": _media_in_view,
    "role_helper": lambda s: s.role == "helper",
    "role_onboarding": lambda s: s.role == "onboarding",
    "story_mode_active": lambda s: s.story_momentum == "story",
    "story_phase_active": lambda s: s.story_momentum in ("story", "emerging", "normal"),
    "thread_surface_present": lambda s: bool(s.thread_surface),
    "bio_anchored_surface_present": lambda s: bool(s.anchored_surface),
    "witness_receipt_present": lambda s: bool(s.witness_block),
    "era_definition_requested": lambda s: bool(s.era_definition_requested),
    "softened_state_active_and_not_parked":
        lambda s: bool(s.softened_active and not s.softened_parked),
    "identity_mode_active": lambda s: bool(s.identity_mode),
    "profile_walk_active": _profile_walk_active,
    "pass_2a": lambda s: s.current_pass == "pass2a",
    "pass_2b": lambda s: s.current_pass == "pass2b",
    "current_mode_set": lambda s: s.current_mode in ("recognition", "grounding", "light"),
    "cognitive_support_mode": lambda s: bool(s.cognitive_support_mode),
    "cognitive_variant_set": lambda s: s.cognitive_mode in ("recognition", "alongside"),
    "paired_interview": lambda s: bool(s.paired),
    "visual_affect_fresh": _visual_affect_fresh,
    "fatigue_elevated": lambda s: s.fatigue_score >= 50,
}


def predicate_for(predicate_id: str) -> Callable[[TurnState], bool]:
    try:
        return PREDICATES[predicate_id]
    except KeyError:
        raise UnknownPredicateError(
            f"{predicate_id!r} has no implementation. A named predicate "
            f"nobody evaluates is an inventory entry, not a gate -- add it "
            f"to directive_predicates.PREDICATES."
        ) from None


def evaluate(predicate_id: str, state: TurnState) -> bool:
    """Run a gate. Never raises; an unknown id or a failing predicate
    reports FALSE and logs, because a family included by accident is a
    narrator receiving an instruction nobody chose."""
    try:
        return bool(predicate_for(predicate_id)(state))
    except UnknownPredicateError:
        raise
    except Exception as exc:
        logger.warning("[directive-gate] %s failed, treating as inactive: %s",
                       predicate_id, exc)
        return False
