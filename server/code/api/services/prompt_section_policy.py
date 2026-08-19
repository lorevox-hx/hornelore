"""THE authoritative policy registry for system-prompt sections.

WO-LEAN-LORI-RUNTIME-01 item 1 (prompt-section metadata), 2026-08-18.

── WHY THIS EXISTS ─────────────────────────────────────────────────────

Phase 4 of the Story Integration work order gave the section
classification its first production reader. Until then `required` and
`drop_order` were metadata nothing consumed, and the reason that went
unnoticed for a whole phase is instructive: the facts were scattered
across a dozen `parts.add()` calls inside a 1,200-line function, so
there was no single place to look at and ask "is anything reading
these?".

This module is that single place. Every section's POLICY is declared
here once, keyed by a stable section id, and the composer resolves it
rather than restating it. A section cannot acquire a drop order by
someone typing a number at a call site, and two sections cannot quietly
share one.

── THE TWO LAYERS, AND THE LINE BETWEEN THEM ───────────────────────────

**Layer 1 — DECLARATIVE policy (this module).** What a section IS, known
at composition time and true regardless of any particular turn: its
owner, the condition that activates it, what may be done to it, where
its content comes from, how important it is, and its position in the
drop ladder.

**Layer 2 — EVALUATED decision (`prompt_budget.SectionPlan`).** What
actually happened on ONE turn: the real post-template token count, the
keep/drop decision, and the redacted digest.

**Token counts and digests are deliberately NOT in layer 1.** Phase 0 of
Lean Lori established that the only honest token count is taken after
`_apply_chat_template`, where the template's own tokens are visible; a
builder-side estimate was wrong by a wide margin, and a wrong number
here would be worse than none because it is the number the compaction
work steers by. The tokenizer is not available at composition time and
this module does not pretend otherwise.

── WHAT `trim_policy` DOES NOT DECIDE ──────────────────────────────────

`trim_policy` says what MAY happen to a section: `never`, or
`drop_whole`. It does NOT say whether optional sections should be shed
before or after conversation history. That global ordering is a product
decision to be made from measurement (Lean Lori item 3), and encoding a
guess about it here would be exactly the kind of default-dressed-as-a-
decision that put `approved_stories` at drop_order 0.

── BEHAVIOUR NEUTRALITY ────────────────────────────────────────────────

Every `required` and `drop_order` below is transcribed from the call
site it replaces. This module adds vocabulary, not behaviour.
"""
from __future__ import annotations

from typing import Dict, List, NamedTuple, Optional

__all__ = [
    "SectionPolicy",
    "UnknownSectionError",
    "TRIM_NEVER",
    "TRIM_DROP_WHOLE",
    "TIER_IDENTITY",
    "TIER_DISCIPLINE",
    "TIER_REVIEWED_EVIDENCE",
    "TIER_NARRATOR_CONTEXT",
    "TIER_TURN_HINT",
    "SOURCE_STATIC",
    "SOURCE_PROFILE",
    "SOURCE_RUNTIME",
    "SOURCE_REVIEWED_STORY",
    "SOURCE_TRANSPORT",
    "REGISTRY",
    "policy_for",
    "known_section_ids",
]

# ── trim policy ─────────────────────────────────────────────────────────
# What MAY be done to a section. Not when, and not relative to history.
TRIM_NEVER = "never"            # must survive; refuse rather than lose it
TRIM_DROP_WHOLE = "drop_whole"  # removable, but only in its entirety

_TRIM_POLICIES = frozenset({TRIM_NEVER, TRIM_DROP_WHOLE})

# ── priority tier ───────────────────────────────────────────────────────
# Coarse editorial grouping, for diagnostics and for human argument about
# the ladder. Deliberately NOT the drop order: the tier says what KIND of
# thing this is, the order says which of two you lose first.
TIER_IDENTITY = "identity"                    # who Lori and the narrator are
TIER_DISCIPLINE = "discipline"                # how Lori is required to behave
TIER_REVIEWED_EVIDENCE = "reviewed_evidence"  # a human read it and decided
TIER_NARRATOR_CONTEXT = "narrator_context"    # durable context about this person
TIER_TURN_HINT = "turn_hint"                  # rebuilt next turn at no cost

_TIERS = frozenset({TIER_IDENTITY, TIER_DISCIPLINE, TIER_REVIEWED_EVIDENCE,
                    TIER_NARRATOR_CONTEXT, TIER_TURN_HINT})

# ── source ──────────────────────────────────────────────────────────────
# Where the section's CONTENT comes from. This is the field that answers
# "if this is wrong, where do I go and fix it".
SOURCE_STATIC = "static"                  # literal text in the composer
SOURCE_PROFILE = "profile"                # profile / PROFILE_JSON
SOURCE_RUNTIME = "runtime71"              # per-turn runtime context
SOURCE_REVIEWED_STORY = "story_review"    # server-owned story projection
SOURCE_TRANSPORT = "transport"            # appended by a transport, not the composer

_SOURCES = frozenset({SOURCE_STATIC, SOURCE_PROFILE, SOURCE_RUNTIME,
                      SOURCE_REVIEWED_STORY, SOURCE_TRANSPORT})


class UnknownSectionError(KeyError):
    """A section id with no registered policy.

    Raised rather than defaulted, on purpose. A silent default is how
    `approved_stories` reached production ranked below a per-turn hint:
    nobody chose 0, it was simply what an unspecified `drop_order` meant.
    """


class SectionPolicy(NamedTuple):
    """Declarative facts about a section. No per-turn values live here."""

    section_id: str
    owner: str
    #: Stable id for the condition under which this section appears at
    #: all. Lean Lori item 2 gates the directive families on these; today
    #: several are `always`, and naming that is the point -- an
    #: activation condition of "always" that should not be is exactly
    #: what item 2 goes looking for.
    activation: str
    trim_policy: str
    source: str
    priority_tier: str
    required: bool
    #: Ascending; the lowest-numbered droppable section goes first.
    #: Meaningless for required sections and pinned at 0 for them.
    drop_order: int
    note: str = ""


def _p(section_id, owner, activation, trim_policy, source, tier,
       required, drop_order, note=""):
    return SectionPolicy(section_id=section_id, owner=owner,
                         activation=activation, trim_policy=trim_policy,
                         source=source, priority_tier=tier,
                         required=required, drop_order=drop_order, note=note)


# ── THE REGISTRY ────────────────────────────────────────────────────────
#
# Ordered as the prompt is composed, so this reads like the prompt does.
# `required` and `drop_order` are transcribed verbatim from the call
# sites they replace; this table changes no behaviour.
_POLICIES: List[SectionPolicy] = [
    _p("system_head", "lori-core", "always", TRIM_NEVER, SOURCE_STATIC,
       TIER_IDENTITY, True, 0,
       "Lori's identity, purpose and the entire safety protocol. Losing it "
       "is the cemetery failure the front-slice used to cause."),

    _p("ui_context", "operator-profile", "profile_json_present",
       TRIM_DROP_WHOLE, SOURCE_PROFILE, TIER_NARRATOR_CONTEXT, False, 30,
       "PROFILE_JSON supplied by the UI. High value, dropped late."),

    _p("pinned_facts", "operator-profile", "pinned_facts_present",
       TRIM_DROP_WHOLE, SOURCE_PROFILE, TIER_NARRATOR_CONTEXT, False, 40,
       "Operator-pinned truth. Dropped LAST of the optional set, because "
       "it is the closest thing here to something a human chose."),

    _p("identity_facts", "lori-core", "runtime_present", TRIM_NEVER,
       SOURCE_RUNTIME, TIER_IDENTITY, True, 0,
       "Verified narrator facts (BUG-LG-01). Losing them does not make "
       "Lori quieter, it makes her invent."),

    _p("identity_grounding", "lori-core", "runtime_present", TRIM_NEVER,
       SOURCE_RUNTIME, TIER_IDENTITY, True, 0,
       "The anti-hallucination rules governing those facts. Dropping one "
       "without the other would be the worst of both."),

    _p("approved_stories", "story-review", "approved_story_present",
       TRIM_DROP_WHOLE, SOURCE_REVIEWED_STORY, TIER_REVIEWED_EVIDENCE,
       False, 25,
       "Stories a human REVIEWED and approved. Above the sections that "
       "rebuild themselves next turn because a reviewed story cannot be "
       "re-asked; below identity, because losing who the narrator is "
       "makes Lori invent, which is worse than her saying less."),

    _p("english_first", "lori-language", "narrator_is_english",
       TRIM_DROP_WHOLE, SOURCE_RUNTIME, TIER_TURN_HINT, False, 20,
       "Language steering. Real cost, but the deterministic guards catch "
       "drift after the fact, so it degrades rather than breaks."),

    _p("factual_chain", "lori-chain", "chain_directive_present",
       TRIM_DROP_WHOLE, SOURCE_RUNTIME, TIER_TURN_HINT, False, 10,
       "A per-turn hint; the next turn rebuilds it."),

    _p("trip_context", "travels-shelf", "trip_open_on_shelf",
       TRIM_DROP_WHOLE, SOURCE_TRANSPORT, TIER_NARRATOR_CONTEXT, False, 15,
       "Appended by chat_ws when a trip is open on the Travels shelf. The "
       "ONLY section a transport contributes -- registered here so the "
       "budget prices the message it actually sends, and so the trip "
       "scope stamp can follow the budget's decision."),

    _p("directives_bio_builder", "lori-discipline", "mode_bio_builder",
       TRIM_NEVER, SOURCE_RUNTIME, TIER_DISCIPLINE, True, 0,
       "Interview discipline for the Bio Builder task."),

    _p("directives_questionnaire", "lori-discipline", "mode_questionnaire",
       TRIM_NEVER, SOURCE_RUNTIME, TIER_DISCIPLINE, True, 0,
       "Interview discipline for the questionnaire task."),

    _p("directives_interview", "lori-discipline", "mode_interview",
       TRIM_NEVER, SOURCE_RUNTIME, TIER_DISCIPLINE, True, 0,
       "The standard interview discipline. Without it Lori reverts to a "
       "generic assistant, which is the behaviour every LORI bug fix "
       "undoes."),

    _p("memory_context", "lori-memory", "memory_block_present",
       TRIM_DROP_WHOLE, SOURCE_RUNTIME, TIER_TURN_HINT, False, 5,
       "Adaptive recall. Costs continuity, and the narrator can always be "
       "asked again -- which is precisely why a reviewed story outranks "
       "it."),
]


def _build_registry(policies) -> Dict[str, SectionPolicy]:
    """Validate at import, so a bad registry fails the BOOT.

    The standing lesson from INC-2026-07-09: a structural error must fail
    loudly at import rather than be caught per-call and leave the system
    running in a degraded state nobody notices.
    """
    reg: Dict[str, SectionPolicy] = {}
    for pol in policies:
        if pol.section_id in reg:
            raise ValueError(
                f"duplicate section id {pol.section_id!r} in the registry")
        if pol.trim_policy not in _TRIM_POLICIES:
            raise ValueError(
                f"{pol.section_id}: unknown trim_policy {pol.trim_policy!r}")
        if pol.priority_tier not in _TIERS:
            raise ValueError(
                f"{pol.section_id}: unknown priority_tier {pol.priority_tier!r}")
        if pol.source not in _SOURCES:
            raise ValueError(f"{pol.section_id}: unknown source {pol.source!r}")
        # required and trim_policy are two spellings of one fact; letting
        # them disagree would give two answers to "may this be dropped".
        if pol.required != (pol.trim_policy == TRIM_NEVER):
            raise ValueError(
                f"{pol.section_id}: required={pol.required} contradicts "
                f"trim_policy={pol.trim_policy!r}")
        if not pol.required and pol.drop_order <= 0:
            raise ValueError(
                f"{pol.section_id}: a droppable section needs a deliberate "
                f"drop_order, not the default 0")
        if pol.required and pol.drop_order != 0:
            raise ValueError(
                f"{pol.section_id}: drop_order is meaningless for a required "
                f"section and must be 0")
        if not pol.owner or not pol.activation:
            raise ValueError(f"{pol.section_id}: owner and activation required")
        reg[pol.section_id] = pol

    # Ties would make the drop sequence depend on composition order, which
    # is not where that decision should live.
    orders = [p.drop_order for p in policies if not p.required]
    if len(orders) != len(set(orders)):
        raise ValueError("two droppable sections share a drop_order")
    return reg


REGISTRY: Dict[str, SectionPolicy] = _build_registry(_POLICIES)


def policy_for(section_id: str) -> SectionPolicy:
    """The policy for a section id, or a loud failure.

    Never returns a default. An unregistered section is a section nobody
    made a decision about, and the budget must not guess on its behalf.
    """
    try:
        return REGISTRY[section_id]
    except KeyError:
        raise UnknownSectionError(
            f"{section_id!r} has no registered section policy. Add it to "
            f"prompt_section_policy.REGISTRY with an owner, an activation "
            f"condition, a trim policy, a source, a tier and -- if it is "
            f"droppable -- a deliberate drop order."
        ) from None


def known_section_ids() -> List[str]:
    """Registered ids, in composition order."""
    return [p.section_id for p in _POLICIES]
