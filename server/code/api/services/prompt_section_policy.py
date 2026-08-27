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

# ── vocabulary ──────────────────────────────────────────────────────────
#
# MIGRATED 2026-08-18. These tier and source constants were declared here
# AND in `directive_activation`, which is two authorities for one concept
# and the beginning of the drift this lane exists to remove. They are now
# re-exported from the shared module so every consumer keeps working
# while there is only one definition.
from .prompt_policy_vocab import (            # noqa: E402
    SOURCE_DEVICE, SOURCE_PROFILE, SOURCE_REVIEWED_STORY, SOURCE_RUNTIME,
    SOURCE_SERVER_DB, SOURCE_STATIC, SOURCE_TRANSPORT, SOURCES,
    TIER_ACCESSIBILITY, TIER_DISCIPLINE, TIER_IDENTITY,
    TIER_NARRATOR_CONTEXT, TIER_REVIEWED_EVIDENCE, TIER_TURN_HINT,
    TIER_WORKFLOW, TIERS,
)

#: Retained as the module's own name for the shared set, so existing
#: readers of `_TIERS` / `_SOURCES` are unaffected.
_TIERS = TIERS
_SOURCES = SOURCES


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

    _p("pinned_facts", "lori-discipline", "pinned_guidance_present",
       TRIM_DROP_WHOLE, SOURCE_STATIC, TIER_DISCIPLINE, False, 40,
       "MISNAMED, and the misnomer is recorded rather than corrected here. "
       "Verified 2026-08-18 against the composer: this section carries "
       "[ORAL_HISTORY_GUIDELINES] (the oral-history manifesto) and "
       "[GOLDEN_MOCK] (golden guidance). It does NOT carry "
       "narrator-specific operator-pinned facts, which is what its name "
       "and its previous rationale -- 'the closest thing here to something "
       "a human chose' -- both asserted. Its owner, source and tier are "
       "corrected to what it actually is: static discipline material, not "
       "narrator profile context. THE ID IS DELIBERATELY NOT RENAMED in "
       "this block: the id is stable and load-bearing across telemetry and "
       "tests, and item 3 must classify the contents before its priority "
       "is decided. Renaming it here would change a name without changing "
       "the decision that name is wrong about."),

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

    # WO-LORI-PROFILE-SEED-REACHABILITY-01 Phase 2 step 4 (2026-08-26).
    #
    # TRIM_NEVER, and the reason is a coupling rather than importance.
    # Step 6 stamps a `presented(topic, version)` event on the assistant
    # row for the turn that ASKS. If this section could be dropped by the
    # budget, the event would record a question Lori never asked — and
    # the reducer would then wait for an answer to it forever, or worse,
    # treat the narrator's next unrelated sentence as that answer.
    #
    # It is one short block naming ONE topic, so it is also cheap enough
    # that never dropping it costs almost nothing.
    _p("profile_seed_onboarding", "lori-onboarding",
       "profile_seed_onboarding_active", TRIM_NEVER, SOURCE_SERVER_DB,
       TIER_WORKFLOW, True, 0,
       "The ten-topic Profile Seed walk, rendered ONE topic at a time "
       "from the server-owned canonical registry. The legacy pass-1 "
       "ten-question block still EXISTS for historical narrators, who "
       "have no onboarding row and never will — but it is generated "
       "from that same registry, so there is one list and two "
       "renderings of it, not two lists. *(This note said the legacy block was REPLACED and that there was \"no second list\" while the composer still held a hard-coded copy of it. Both halves were false at the time.)*"),

    _p("memory_context", "lori-memory", "memory_block_present",
       TRIM_DROP_WHOLE, SOURCE_RUNTIME, TIER_NARRATOR_CONTEXT, False, 5,
       "Adaptive recall. ── RATIONALE CORRECTED 2026-08-18. This read "
       "'the narrator can always be asked again', which is contrary to "
       "Lorevox's purpose: an older narrator is not a recoverable storage "
       "device, and asking them to repeat themselves is a cost borne by "
       "the person this system exists to serve. The ONLY honest "
       "justification is durability: this block is RECONSTRUCTED each turn "
       "from the archive and rolling summary, which remain intact on the "
       "server, so dropping it costs continuity within one turn and loses "
       "nothing permanently. Its tier is narrator_context, not turn_hint -- "
       "it is about this person, not about this turn."),
]


# The harmful CLAIM, not the words. `approved_stories` legitimately says a
# reviewed story "cannot be re-asked" -- it invokes the idea in order to
# reject it -- so a bare substring ban would fire on the argument against
# the very rationale it exists to forbid. That is the guard-on-prose
# mistake this repository keeps making; the ban is on the assertion that
# the NARRATOR is the recovery mechanism.
_BANNED_RATIONALES = (
    "narrator can always be asked",
    "narrator can be asked again",
    "can always be asked again",
    "the narrator could be asked again",
    "ask the narrator again",
)


def _unquoted(text: str) -> str:
    """Text with single- and double-quoted spans removed.

    So that quoting a retired rationale in order to withdraw it does not
    read as asserting it.
    """
    import re
    return re.sub(r"'[^']*'|\"[^\"]*\"", " ", text)


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
        # Lorevox's purpose forbids one justification outright: an older
        # narrator is not a recoverable storage device. A section may be
        # droppable because its SOURCE is durable, never because the
        # person could be made to say it again.
        # Quoted spans are STRIPPED before the check. This file's own
        # correct-in-place rule requires quoting a retired claim when
        # withdrawing it, and `memory_context` does exactly that -- so a
        # naive scan fires on the withdrawal itself. A phrase inside
        # quotes is being reported; only unquoted text is asserted.
        low = _unquoted((pol.note or "").lower())
        for banned in _BANNED_RATIONALES:
            if banned in low:
                raise ValueError(
                    f"{pol.section_id}: a section may not be justified as "
                    f"droppable because the narrator could be asked again")
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
