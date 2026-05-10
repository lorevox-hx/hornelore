"""WO-LORI-WITNESS-FOLLOWUP-BANK-01 (2026-05-10) — patience layer.

Each narrator turn opens new doors. Lori cannot ask all of them in one
response — that's interruption, not interview. This service implements
Chris's locked principle:

    Immediate Lori response:
      Receive the chapter.
      Reflect the main chain.
      Open ONE door only if it is clearly the next door.
      Bank the rest.

    Later Lori response:
      Return to one banked question at a natural pause.

Architecture:

  - detect_doors(narrator_text, history) → ordered list of Doors
    A "door" is a follow-up question the narrator's text invites,
    paired with the anchor that opened it and the rationale for why
    it matters in oral-history terms.

  - select_immediate_and_bank(doors) → (immediate_door, doors_to_bank)
    Picks the highest-urgency door for THIS turn (priority 1-3 only).
    Priority 4-6 doors NEVER ask immediately — relationship and
    daily-life doors always bank, per Chris's locked rule.

  - should_flush_bank(narrator_text, current_turn_doors, ...) → bool
    Conservative triggers ONLY (no per-turn metronome):
      • narrator answer was short AND opened no new door
      • narrator says "what else / where were we / what next"
      • floor-released SYSTEM directive
      • operator click "Ask banked follow-up" (SYSTEM directive)
      • chapter-summary mode active

  - select_banked_question_to_flush(session_id) → BankedQuestion | None
    Lowest priority number wins (priority 1 = most urgent fragile
    name); ties broken by most-recently-banked first (the door
    narrator most-recently opened is freshest in their working
    memory).

  - compose_bank_flush_response(banked) → str
    Fixed phrase: "I want to come back to one detail you mentioned
    earlier. <question>"

LAW: this is a pure-stdlib service. NO LLM call. NO direct DB write
within detect/select. The chat_ws.py caller handles persistence via
db.followup_bank_add() / db.followup_bank_mark_asked().

The architecture is intentionally separable from witness mode — the
bank works for ANY structured narrative (Janice's later-years stories
will use the same bank logic, different intent patterns).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ── Door dataclass ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Door:
    """A follow-up question the narrator's turn just invited.

    Attributes mirror the BankedQuestion DB schema so this struct can
    flow straight into db.followup_bank_add() without translation."""
    intent: str
    question_en: str
    triggering_anchor: str
    why_it_matters: str
    priority: int  # 1=fragile-name, 2=communication/logistics,
                    # 3=role-transition, 4=relationship,
                    # 5=daily-life, 6=emotional-reflection


# ── Door detectors ──────────────────────────────────────────────────────────
#
# Each detector returns 0 or more Doors. Priority 1 detectors run first;
# the selector picks the lowest priority number for the immediate ask.
# Detectors are deliberately conservative — false-positives mean Lori
# asks a less relevant question, but false-negatives mean a banked door
# never opens. Lean toward false-positives to keep doors discoverable.


# Priority 1: fragile-name confirms.
#
# Per Chris's 2026-05-10 review refinement:
#
#   "Fragile-name confirmation fires immediately only when:
#     - narrator self-corrects: 'not X, it was Y'
#     - narrator says 'I may not have that right' / 'something like' /
#       'I think it was' / 'the way it comes back to me'
#     - foreign/uncommon name appears (Landstuhl, Ramstein, Schmick)
#     - hospital/base/unit/person name is record-critical
#     - STT confidence or text shape looks garbled
#
#    Do not confirm ordinary known places every time."
#
# Two-tier fragile-name handling:
#
#   TIER A — ALWAYS fragile (foreign/uncommon, record-critical names).
#   These fire immediate confirmation on first appearance because the
#   memoir record is at risk if the spelling drifts later. German
#   military place names + person names with rank + hospital names.
#
#   TIER B — CONDITIONALLY fragile (common American places, well-known
#   bases). These DO NOT fire immediate confirmation in normal use.
#   They only fire when the narrator volunteers uncertainty or a
#   self-correction. For Kent, "Stanley" and "Fargo" are common
#   American names he says with confidence; we follow his story
#   instead of breaking rhythm to spell-check what he already knows.
#
# When in doubt: do NOT make Lori interrupt for spelling. Let the
# narrator keep the floor.

_SELF_CORRECTION_PATTERNS = (
    re.compile(r"\bnot\s+([A-Z][\w\-]{3,})\b.*?\bwas\s+([A-Z][\w\-]{3,})\b", re.IGNORECASE),
    re.compile(r"\bit was not\s+([A-Z][\w\-]{2,}(?:\s+[A-Z][\w\-]{2,})?)\b.*?\bit was\s+([A-Z][\w\-]{2,}(?:\s+[A-Z][\w\-]{2,})?)\b", re.IGNORECASE),
    re.compile(r"\bI mean[t]?\s+([A-Z][\w\-]{2,}(?:\s+[A-Z][\w\-]{2,})?)\b", re.IGNORECASE),
    re.compile(r"\bactually,?\s+it was\s+([A-Z][\w\-]{2,}(?:\s+[A-Z][\w\-]{2,})?)\b", re.IGNORECASE),
)

# Uncertainty markers — narrator signals they aren't sure. When ANY
# of these appear in the same turn as a TIER B name, we treat the
# name as fragile-for-this-turn.
_UNCERTAINTY_PATTERNS = (
    # "I may not have that right" / "I may not have that name right" /
    # "I may not be saying that exactly" — allow up to 2 intervening
    # tokens between "have/be saying" and "right/exactly".
    re.compile(
        r"\bI may not (?:have|be saying)\s+(?:that|it|the|this)"
        r"(?:\s+\w+){0,3}\s+(?:right|exactly|correct|correctly)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bI(?:'m|\s+am)\s+not (?:sure|certain)\b", re.IGNORECASE),
    re.compile(r"\bsomething like\b", re.IGNORECASE),
    re.compile(r"\bI think it (?:was|might have been)\b", re.IGNORECASE),
    re.compile(r"\bthe way it comes back to me\b", re.IGNORECASE),
    re.compile(r"\bif I(?:'m|\s+am)?\s+remember(?:ing)?\s+(?:right|correctly)\b", re.IGNORECASE),
    re.compile(r"\bI wish I had (?:the|that) (?:name|city)\s+(?:clear|right)\b", re.IGNORECASE),
    re.compile(r"\b(?:might be|could be|may be)\s+(?:wrong|off|misremembering)\b", re.IGNORECASE),
    re.compile(r"\b(?:I am|I'm) not saying (?:it|that)\s+(?:right|exactly)\b", re.IGNORECASE),
)

# TIER A — ALWAYS-fragile names. Foreign-language places, rank-
# titled persons, record-critical hospital/base/unit names.
_FRAGILE_NAMES_TIER_A = frozenset({
    # German military / Kent's chapter — foreign-language places
    "landstuhl", "ramstein", "kaiserslautern", "frankfurt",
    "hochspeyer", "wiesbaden", "selfridge",
    # German cultural / business landmark names
    "salamander",
    # Person names with German/uncommon spelling
    "schmick",
    # Hospital + base names where misspelling damages the memoir
    "lansdale army hospital", "landstuhl air force hospital",
    "ramstein air force base",
    # Unit names — small typos cascade in memoir
    "32nd artillery brigade", "32nd brigade",
    "army security agency",
    "nike ajax", "nike hercules",
    # Janice's chapter — Norwegian/foreign equivalents
    "oslo", "trondheim",
})

# TIER B — conditionally-fragile names. Common American places that
# do NOT need confirmation in normal use. Only fire when narrator
# signals uncertainty or self-corrects.
_FRAGILE_NAMES_TIER_B = frozenset({
    "stanley", "fargo", "bismarck", "fort ord",
    "minot", "spokane", "norway",
    "duffy",  # common American surname; foreign-equivalent confirmation only on self-correct
})


def _has_uncertainty_marker(narrator_text: str) -> bool:
    return any(rx.search(narrator_text) for rx in _UNCERTAINTY_PATTERNS)


def _detect_fragile_name_doors(narrator_text: str) -> List[Door]:
    """Priority 1 doors. Three trigger paths:

    (1) Self-correction: "not X, was Y" / "actually, it was Y" / "I
        meant Y" — always fires regardless of name tier.

    (2) TIER A names — always-fragile foreign/record-critical names.
        Fire on first appearance.

    (3) TIER B names + uncertainty marker — common American names
        only fire when the narrator volunteers uncertainty or a
        self-correction. Without the marker, common names DO NOT
        get confirmation.

    Per Chris's locked rule: "Do not confirm ordinary known places
    every time." For Kent, Stanley and Fargo are common American
    names he says with confidence; only Landstuhl / Ramstein /
    Schmick / Kaiserslautern / 32nd Brigade get the immediate
    confirmation door.
    """
    doors: List[Door] = []
    if not narrator_text:
        return doors

    text_lower = narrator_text.lower()

    # (1) Self-correction — always fires.
    for rx in _SELF_CORRECTION_PATTERNS:
        m = rx.search(narrator_text)
        if not m:
            continue
        try:
            # Different patterns expose the corrected value at
            # different group positions. Walk groups looking for
            # a non-None value.
            corrected = ""
            for gi in range(m.lastindex or 0, 0, -1):
                cand = m.group(gi)
                if cand and len(cand.strip()) >= 3:
                    corrected = cand.strip()
                    break
        except (IndexError, re.error):
            corrected = m.group(0)
        if not corrected or len(corrected) < 3:
            continue
        doors.append(Door(
            intent="fragile_name_confirm_correction",
            question_en=f"Got it — you corrected to {corrected}. Did I get the spelling right?",
            triggering_anchor=corrected,
            why_it_matters=(
                "Narrator volunteered a self-correction. The memoir "
                "record needs the corrected spelling locked while the "
                "narrator can confirm it."
            ),
            priority=1,
        ))
        break  # one self-correction door per turn

    # (2) TIER A names — always-fragile.
    for fragile in _FRAGILE_NAMES_TIER_A:
        if fragile in text_lower:
            m = re.search(rf"\b({re.escape(fragile)})\b", narrator_text, re.IGNORECASE)
            canonical = m.group(1) if m else fragile.title()
            doors.append(Door(
                intent=f"fragile_name_confirm_{fragile.replace(' ', '_')}",
                question_en=f"Did I get {canonical} spelled right?",
                triggering_anchor=canonical,
                why_it_matters=(
                    f"'{canonical}' is a foreign-language or rare "
                    f"proper noun the memoir needs spelled "
                    f"correctly. Confirming now while the narrator "
                    f"is in-context locks the record."
                ),
                priority=1,
            ))

    # (3) TIER B names — only fire when uncertainty marker present.
    if _has_uncertainty_marker(narrator_text):
        for fragile in _FRAGILE_NAMES_TIER_B:
            if fragile in text_lower:
                m = re.search(rf"\b({re.escape(fragile)})\b", narrator_text, re.IGNORECASE)
                canonical = m.group(1) if m else fragile.title()
                doors.append(Door(
                    intent=f"fragile_name_confirm_{fragile.replace(' ', '_')}_uncertain",
                    question_en=f"You sounded a little unsure — was it {canonical}, or something close to that?",
                    triggering_anchor=canonical,
                    why_it_matters=(
                        f"Narrator signaled uncertainty about "
                        f"{canonical}. Confirming now while context "
                        f"is fresh prevents the memoir locking in a "
                        f"wrong spelling."
                    ),
                    priority=1,
                ))

    return doors


# Priority 2: communication / logistics.
# Triggers: era-cued courtship logistics, travel/paperwork mechanics,
# pre-text-era communication. When the narrator literally cues the
# question (e.g. "1959, not like today where you text someone"), the
# door is asked IMMEDIATELY (selector sees priority 2 with cue and
# promotes). Otherwise it banks.

_COMMUNICATION_CUE_PATTERNS = (
    re.compile(r"\bnot like today\b", re.IGNORECASE),
    re.compile(r"\bbefore (?:texting|cell phones|email|the internet)\b", re.IGNORECASE),
    re.compile(r"\bwhere you (?:just )?(?:text|email|call)\b", re.IGNORECASE),
    re.compile(r"\bin (?:those days|that era|the (?:fifties|sixties|seventies))\b", re.IGNORECASE),
)


def _detect_communication_logistics_doors(narrator_text: str) -> List[Door]:
    """Priority 2 doors. Communication / travel / paperwork logistics."""
    doors: List[Door] = []
    if not narrator_text:
        return doors

    text_lower = narrator_text.lower()

    # 1959-era communication cue (Kent TEST-COMMS load-bearing)
    has_overseas_signal = any(
        sig in text_lower for sig in (
            "overseas", "germany", "korea", "vietnam", "okinawa",
            "abroad", "europe",
        )
    )
    has_partner_signal = any(
        sig in text_lower for sig in (
            "fiancée", "fiancee", "girlfriend", "boyfriend", "wife",
            "husband", "janice", "mary", "marvin", "kent", "spouse",
        )
    )
    has_contact_verb = any(
        sig in text_lower for sig in (
            "contacted", "wrote", "called", "letter", "letters",
            "phone", "telegram", "telegrams",
        )
    )
    has_year_or_cue = (
        any(yr in narrator_text for yr in (
            "1955", "1956", "1957", "1958", "1959",
            "1960", "1961", "1962", "1963", "1964", "1965",
            "1966", "1967", "1968", "1969", "1970",
        ))
        or any(rx.search(narrator_text) for rx in _COMMUNICATION_CUE_PATTERNS)
    )

    if has_overseas_signal and has_partner_signal and (has_contact_verb or has_year_or_cue):
        # Find partner name for the question
        partner_name = "your partner"
        for cand in ("Janice", "Mary", "Marvin", "Kent"):
            if cand.lower() in text_lower:
                partner_name = cand
                break
        cued = any(rx.search(narrator_text) for rx in _COMMUNICATION_CUE_PATTERNS)
        priority = 2 if cued else 2  # always 2; the cue is what makes selector ask immediately
        doors.append(Door(
            intent="communication_with_partner_overseas",
            question_en=(
                f"How did you and {partner_name} keep in touch from "
                "overseas — letters, phone calls, telegrams?"
            ),
            triggering_anchor=f"{partner_name} overseas communication",
            why_it_matters=(
                f"Pre-text-era courtship logistics with {partner_name} "
                "is core to a 1950s-60s memoir. Letters, phone calls, "
                "telegrams across an ocean are a story most narrators "
                "have rich detail on."
            ),
            priority=2,
        ))

    # Spouse travel after wedding (Kent TEST-E follow-up)
    has_wedding = any(s in text_lower for s in ("wedding", "married", "ceremony"))
    has_return = any(s in text_lower for s in (
        "back to germany", "back overseas", "bring her back",
        "bring him back", "travel back", "returned to",
    ))
    if has_wedding and has_return:
        partner_name = "your spouse"
        for cand in ("Janice", "Mary"):
            if cand.lower() in text_lower:
                partner_name = cand
                break
        doors.append(Door(
            intent="spouse_travel_paperwork",
            question_en=(
                f"How did {partner_name} travel to Germany after the "
                "wedding — military transport, or commercial flight?"
            ),
            triggering_anchor=f"{partner_name} travel to Germany",
            why_it_matters=(
                "How a military spouse joined the active-duty partner "
                "overseas is a logistics chain — Army rules, "
                "paperwork, transport — that the narrator owns and "
                "few outside sources can recover."
            ),
            priority=2,
        ))

    return doors


# Priority 3: role transition mechanism.
# Triggers: narrator describes a job-to-job pivot AND identifies the
# bridge moment. Asked immediately because the mechanism IS the story.

_ROLE_TRANSITION_PATTERNS = (
    re.compile(
        r"\b(?:became|moved into|asked if (?:they had|there were)|"
        r"they (?:offered|opened up)|that (?:opened|led) (?:up )?(?:to|into))\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:replaced|substituted for|filled in for|took over for)\s+\w+",
        re.IGNORECASE,
    ),
)


def _detect_role_transition_doors(narrator_text: str) -> List[Door]:
    """Priority 3 doors. Two sub-detectors:

    (A) Role-pivot mechanism — gated by transition-pattern regex.
        Fires on photography / courier when the narrator describes the
        pivot ("became" / "moved into" / "asked if" / "replaced X").

    (B) Career choice under constraint — NOT gated by transition
        regex. Fires when the narrator describes a Plan-A-blocked /
        Plan-B-chosen calculus regardless of how they phrased the
        pivot itself ("originally enlisted hoping for X but had to
        wait" / "I asked what else was available").
    """
    doors: List[Door] = []
    if not narrator_text:
        return doors

    text_lower = narrator_text.lower()

    # (A) Role-pivot mechanism — gated by transition pattern
    if any(rx.search(narrator_text) for rx in _ROLE_TRANSITION_PATTERNS):
        if "photography" in text_lower or "photographer" in text_lower:
            doors.append(Door(
                intent="role_pivot_photography",
                question_en="What kind of photography did the Brigade need you to do?",
                triggering_anchor="photography role pivot",
                why_it_matters=(
                    "The day-to-day work of an Army photographer is "
                    "the specific texture of a role pivot. What got "
                    "photographed, for whom, and why."
                ),
                priority=3,
            ))
        if "courier" in text_lower:
            doors.append(Door(
                intent="role_pivot_courier_bridge",
                question_en=(
                    "How did the courier route end up turning into "
                    "the next assignment?"
                ),
                triggering_anchor="courier route transition",
                why_it_matters=(
                    "A temporary substitution that became a permanent "
                    "career pivot is the bridge moment of the chapter."
                ),
                priority=3,
            ))

    # (B) Career choice under constraint — independent of transition
    # pattern. Fires on Plan-A-blocked / Plan-B-chosen narratives.
    has_constraint_signal = (
        "originally" in text_lower
        or "had hoped" in text_lower
        or "have to wait" in text_lower
        or "had to wait" in text_lower
        or "asked what else" in text_lower
    )
    has_career_options = any(s in text_lower for s in (
        "army security agency", "asa", "nike",
        "ajax", "hercules", "missile",
    ))
    if has_constraint_signal and has_career_options:
        doors.append(Door(
            intent="career_choice_under_constraint",
            question_en=(
                "How did the choice between waiting and pivoting "
                "actually feel at the time?"
            ),
            triggering_anchor="ASA-vs-Nike career choice",
            why_it_matters=(
                "Pivot-under-constraint decisions shape the next "
                "decades. The narrator's calculus at the moment is "
                "information memoir summaries lose."
            ),
            priority=3,
        ))

    return doors


# Priority 4: relationship / personality.
# Trigger: rank-vs-role asymmetry (private + general / sergeant +
# colonel) OR explicit "worked for X" pattern. NEVER asked immediately.
# Always banks. Per Chris's example: "private working as photographer
# for a General" → bank, not immediate.

_RANK_TERMS = (
    "private", "specialist", "corporal", "sergeant", "lieutenant",
    "captain", "major", "colonel", "general", "admiral",
)


def _detect_relationship_doors(narrator_text: str) -> List[Door]:
    doors: List[Door] = []
    if not narrator_text:
        return doors

    text_lower = narrator_text.lower()

    # Rank asymmetry: low rank + high rank in same turn
    low_ranks = {"private", "specialist", "corporal"}
    high_ranks = {"general", "admiral", "colonel"}
    has_low = any(r in text_lower for r in low_ranks)
    has_high = any(r in text_lower for r in high_ranks)
    if has_low and has_high:
        # Find the high-rank named person if possible
        m = re.search(
            r"\b(?:General|Admiral|Colonel)\s+([A-Z][\w\-]+(?:\s+[A-Z][\w\-]+)*)",
            narrator_text,
        )
        named = m.group(0) if m else "the General"
        doors.append(Door(
            intent="rank_asymmetry_relationship",
            question_en=(
                f"Working for {named} as a private — was it strictly "
                "yes-sir / no-sir, or did he know you more personally "
                "through your skill?"
            ),
            triggering_anchor=named,
            why_it_matters=(
                "Working relationships across rank reveal personality "
                "and trust dynamics that job titles don't capture. "
                "A private trusted with photography for a General is "
                "specifically a story of skill recognition, not "
                "chain-of-command."
            ),
            priority=4,
        ))

    # Worked-for boss
    m = re.search(
        r"\b(?:I )?worked for\s+([A-Z][\w\-]+(?:\s+[A-Z][\w\-]+)*)",
        narrator_text,
    )
    if m:
        boss = m.group(1)
        doors.append(Door(
            intent="working_relationship_boss",
            question_en=(
                f"What was {boss} like as a person to work with day "
                "to day?"
            ),
            triggering_anchor=f"worked for {boss}",
            why_it_matters=(
                f"How {boss} treated subordinates is the human texture "
                "of the working life — promotion, trust, friction, "
                "loyalty."
            ),
            priority=4,
        ))

    return doors


# Priority 5: daily life / off-duty texture. Always banks.

def _detect_daily_life_doors(narrator_text: str) -> List[Door]:
    doors: List[Door] = []
    if not narrator_text:
        return doors

    # Living-arrangement regex doubles as the gate AND the place
    # extractor. Matches:
    #   "we were living up around X"
    #   "we lived in X"
    #   "Janice and I were living near X"
    #   "I was stationed at X"
    #   "we were stationed near X"
    living_rx = re.compile(
        r"\b(?:were |was |been )?(?:living|lived|stationed)\s+"
        r"(?:up\s+|out\s+|down\s+)?"
        r"(?:around|in|at|near)\s+"
        r"([A-Z][\w\-]+(?:\s+[A-Z][\w\-]+){0,2})",
        re.IGNORECASE,
    )
    m = living_rx.search(narrator_text)
    if not m:
        return doors

    place = m.group(1)
    if not place:
        return doors

    doors.append(Door(
        intent="daily_life_off_duty",
        question_en=(
            f"What was off-duty life like for the two of you in {place}?"
        ),
        triggering_anchor=f"living in {place}",
        why_it_matters=(
            f"Daily life — meals, neighbors, weekend routines — in "
            f"{place} grounds the larger arc in lived experience and "
            f"is rich for the memoir's texture."
        ),
        priority=5,
    ))
    return doors


# Priority 6: medical / family event details (high-care context).
# Trigger: premature / CP / cerebral palsy / hospital + family member.
# Per Chris's note about Vince premature with CP: this is a banked
# door, asked carefully later, not jammed into the same turn as
# fragile-name confirmation.

def _detect_medical_family_doors(narrator_text: str) -> List[Door]:
    doors: List[Door] = []
    if not narrator_text:
        return doors

    text_lower = narrator_text.lower()

    medical_signals = (
        "premature", "preemie", "cerebral palsy", " cp ", "cp,",
        "medical needs", "incubator", "intensive care", "icu",
        "specialist",
    )
    has_medical = any(s in text_lower for s in medical_signals)

    family_signals = (
        " son ", " daughter ", " child ", " baby ", " our ",
        "vince", "child was born", "born premature",
    )
    has_family = any(s in text_lower for s in family_signals)

    if has_medical and has_family:
        doors.append(Door(
            intent="medical_family_care",
            question_en=(
                "What was the medical care like in those first months "
                "— were the doctors there able to help?"
            ),
            triggering_anchor="premature/medical needs",
            why_it_matters=(
                "Family medical events shape decades of life. Asked "
                "with care, not jammed into a fragile-name "
                "confirmation turn. The narrator owns this story and "
                "we receive it on their pace."
            ),
            priority=6,
        ))

    return doors


# ── Public API ──────────────────────────────────────────────────────────────


def detect_doors(narrator_text: str, history: Optional[List[Dict]] = None) -> List[Door]:
    """Return all doors opened by the narrator turn, in priority order
    (1 first). The caller picks the immediate door (priority 1-3) and
    banks the rest. Priority 4-6 always bank, never immediate.

    history is currently unused but reserved for future "have we
    already asked this in a prior turn?" deduplication. v1 relies on
    the DB-level (session_id, intent, triggering_anchor) dedupe.
    """
    if not narrator_text or not narrator_text.strip():
        return []

    doors: List[Door] = []
    doors.extend(_detect_fragile_name_doors(narrator_text))
    doors.extend(_detect_communication_logistics_doors(narrator_text))
    doors.extend(_detect_role_transition_doors(narrator_text))
    doors.extend(_detect_relationship_doors(narrator_text))
    doors.extend(_detect_daily_life_doors(narrator_text))
    doors.extend(_detect_medical_family_doors(narrator_text))

    # Sort by priority (lower = more urgent), then by intent for
    # deterministic ordering across runs.
    doors.sort(key=lambda d: (d.priority, d.intent))
    return doors


def select_immediate_and_bank(
    doors: List[Door],
) -> Tuple[Optional[Door], List[Door]]:
    """Per Chris's locked rule:
       - Priority 1-3 doors MAY be immediate.
       - Priority 4-6 doors NEVER immediate. Always bank.
       - Of the immediate-eligible doors, pick the lowest priority
         number (most urgent). Ties broken by the order detect_doors
         returned (intent name asc within same priority).

    Returns (immediate_door, doors_to_bank). immediate_door is None
    when only priority 4-6 doors are open OR no doors at all.
    doors_to_bank is everything except the immediate_door.
    """
    if not doors:
        return (None, [])
    # Sort defensively by priority ascending (lower = more urgent),
    # then by intent for deterministic ties. detect_doors() already
    # sorts but callers may pass raw doors directly.
    sorted_doors = sorted(doors, key=lambda d: (d.priority, d.intent))
    immediate_eligible = [d for d in sorted_doors if d.priority <= 3]
    if not immediate_eligible:
        return (None, list(sorted_doors))
    immediate = immediate_eligible[0]
    bank = [d for d in sorted_doors if d is not immediate]
    return (immediate, bank)


# ── Bank-flush triggers ────────────────────────────────────────────────────
#
# Conservative per Chris's locked list. Bank-flush fires ONLY when:
#   (a) narrator gave a short answer AND opened no new door, OR
#   (b) narrator says "what else / where were we / what next", OR
#   (c) floor-released SYSTEM directive arrives, OR
#   (d) operator click "Ask banked follow-up" SYSTEM directive arrives, OR
#   (e) chapter-summary mode active in runtime71.
#
# NOT a per-Nth-turn metronome. Mechanical pacing makes Lori feel
# robotic; the bank only flushes when the narrator's own rhythm opens
# space for it.


_FLUSH_CUE_PATTERNS = (
    re.compile(r"\bwhat (?:else|next|now|should i|would you like)\b", re.IGNORECASE),
    re.compile(r"\bwhere were we\b", re.IGNORECASE),
    re.compile(r"\banything else\b", re.IGNORECASE),
    re.compile(r"\bi(?:'m|am)\s+done with that\b", re.IGNORECASE),
    re.compile(r"\bthat[''']?s all (?:i (?:can )?remember|i('ve| have) got)\b", re.IGNORECASE),
    re.compile(r"\bthat was the (?:end|whole) of (?:that|it)\b", re.IGNORECASE),
)

_OPERATOR_BANK_FLUSH_DIRECTIVE = "[SYSTEM:ASK_BANKED_FOLLOWUP]"
_FLOOR_RELEASED_DIRECTIVE_SIGNALS = (
    "floor released",
    "narrator paused",
    "narrator silent for",
)


def should_flush_bank(
    narrator_text: str,
    current_turn_doors: List[Door],
    is_system_directive: bool = False,
    runtime71: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """Conservative flush trigger evaluation. Returns (should_flush, reason).

    reason is a short label for the api.log marker — operator can
    grep for `[bank-flush] reason=...` to understand which trigger
    fired.
    """
    if not narrator_text:
        return (False, "")

    # (d) operator-click directive
    if is_system_directive and _OPERATOR_BANK_FLUSH_DIRECTIVE.lower() in narrator_text.lower():
        return (True, "operator_click")

    # (c) floor-released directive
    if is_system_directive:
        text_lower = narrator_text.lower()
        if any(sig in text_lower for sig in _FLOOR_RELEASED_DIRECTIVE_SIGNALS):
            return (True, "floor_released")

    # (e) chapter-summary mode
    if runtime71 and runtime71.get("turn_mode") == "chapter_summary":
        return (True, "chapter_summary_mode")

    # Skip remaining checks for SYSTEM directives — they don't reflect
    # narrator content, just operator/UI signaling.
    if is_system_directive:
        return (False, "")

    # (b) explicit narrator cue — check FIRST so a short cue like
    # "what else?" wins the narrator_cued reason rather than getting
    # bucketed as short_answer_no_door.
    if any(rx.search(narrator_text) for rx in _FLUSH_CUE_PATTERNS):
        return (True, "narrator_cued")

    # (a) short narrator answer + no new door
    word_count = len(narrator_text.split())
    if word_count < 8 and not current_turn_doors:
        return (True, f"short_answer_no_door:{word_count}w")

    return (False, "")


# ── Bank-flush composer ────────────────────────────────────────────────────


_BANK_FLUSH_PHRASE = "I want to come back to one detail you mentioned earlier."


def compose_bank_flush_response(banked_question_text: str) -> str:
    """Fixed phrase + the banked question. The phrase is locked because
    it's a recognizable rhythm cue for the narrator — they should feel
    Lori is circling back, not interrogating fresh.

    Per Chris's note:
        "I want to come back to one detail you mentioned earlier.
         When you contacted Janice from Germany in 1959, how did the
         two of you communicate — letters, phone calls, or telegrams?"
    """
    if not banked_question_text:
        return ""
    return f"{_BANK_FLUSH_PHRASE} {banked_question_text}"


__all__ = [
    "Door",
    "detect_doors",
    "select_immediate_and_bank",
    "should_flush_bank",
    "compose_bank_flush_response",
]
