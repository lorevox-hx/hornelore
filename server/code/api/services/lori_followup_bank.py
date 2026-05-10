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
    flow straight into db.followup_bank_add() without translation.

    Priority field carries the OLD numeric priority (1-6) for backward
    compat with existing DB rows. New code should also consult the
    `tier` field for the BANK_PRIORITY_REBUILD 2026-05-10 model:

      Tier S — sacred / sensitive (zero questions, never auto-flush)
      Tier 1A — story-weighted named particular (immediate)
      Tier 1B — record-critical self-correction (immediate)
      Tier 1C — fragile-name + uncertainty marker (immediate)
      Tier 2D — concrete action / mechanism (immediate when no Tier 1)
      Tier 3A-D — logistics / mechanism (bank, immediate only when cued)
      Tier 4A-B — relationship / role (bank only)
      Tier 5 — sensory / daily-life texture (bank only)
      Tier 6 — medical / family (bank only, careful)
      Tier 7 — reflection (only if narrator opens it)
      Tier N — mechanical record cleanup (bank only, lowest urgency)
    """
    intent: str
    question_en: str
    triggering_anchor: str
    why_it_matters: str
    priority: int  # 1=fragile-name, 2=communication/logistics,
                    # 3=role-transition, 4=relationship,
                    # 5=daily-life, 6=emotional-reflection
    # Tier model (BANK_PRIORITY_REBUILD 2026-05-10). Default empty
    # for backward-compat with existing detectors that haven't been
    # migrated yet. Selector falls back to numeric priority when
    # tier is empty.
    tier: str = ""
    story_weight: int = 0  # for Tier 1A scoring; 0 when not applicable


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

# BUG: re.IGNORECASE on `[A-Z]` makes it match lowercase letters too.
# 2026-05-10 Kent harness replay polluted the bank with corrections
# captured from common English phrases like "I was not thinking" /
# "what else was available" / "It was just the Army". The trigger
# words ("not"/"was"/"actually"/"I mean") are case-insensitive
# (handled via [Nn]ot etc) but the captured proper-noun group MUST
# be uppercase-start — a real correction names a proper noun.
#
# Additional defense: the captured value must be either multi-word
# OR a known TIER A fragile name OR ≥7 characters. Common short
# words like "Nike" / "just" / "going" / "Army" don't pass.
_SELF_CORRECTION_PATTERNS = (
    # "It was not Foo Bar. It was Baz Qux." — strictest form, both
    # captures must be multi-word or strong proper-noun shape.
    re.compile(
        r"\b[Ii]t was not\s+([A-Z][\w\-]{2,}(?:\s+[A-Z][\w\-]{2,})+)\b"
        r".*?\b[Ii]t was\s+([A-Z][\w\-]{2,}(?:\s+[A-Z][\w\-]{2,})+)\b"
    ),
    # "I mean Foo Bar" / "I meant Foo Bar" — multi-word capture only
    re.compile(
        r"\b[Ii] meant?\s+([A-Z][\w\-]{2,}(?:\s+[A-Z][\w\-]{2,})+)\b"
    ),
    # "actually, it was Foo Bar" — multi-word capture only
    re.compile(
        r"\b[Aa]ctually,?\s+it was\s+([A-Z][\w\-]{2,}(?:\s+[A-Z][\w\-]{2,})+)\b"
    ),
    # "not Foo, was Bar" — KEEP single-word but only when both are
    # uppercase-start AND ≥7 chars (rules out "not Nike, was Detroit"
    # noise but allows "not Lansdale, was Landstuhl"). Note: NO
    # IGNORECASE flag — [A-Z] must match uppercase-only here.
    re.compile(
        r"\bnot\s+([A-Z][a-z\-]{6,})\b[^.!?]*?\bwas\s+([A-Z][a-z\-]{6,})\b"
    ),
)

# Common-English-word blocklist for self-correction captures. If the
# captured value is one of these, drop the door — we've matched a
# false positive against narrator's prose, not a real proper-noun
# correction.
_SELF_CORRECTION_VALUE_BLOCKLIST = frozenset({
    "just", "making", "going", "thinking", "saying", "telling",
    "right", "wrong", "really", "actually", "almost", "nearly",
    "before", "after", "during", "while", "since", "until",
    "first", "next", "later", "earlier", "always", "never",
    "something", "anything", "everything", "nothing",
    "someone", "anyone", "everyone", "nobody",
    "today", "tomorrow", "yesterday", "tonight",
    "army", "navy", "marines", "force",  # too generic alone
    "german", "english", "french", "spanish",
})

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

# TIER A — TRULY-fragile names where memoir is damaged by misspelling.
# Per Chris's 2026-05-10 review (after the 2,400-word Fort Ord
# monologue exposed over-broad spelling-confirms): TIER A is
# reserved for foreign-language place names with non-English
# orthography that Kent could plausibly drift on. Clear English
# institutional names (Army Security Agency, Nike Ajax, Nike
# Hercules, 32nd Brigade) are NOT TIER A — they're unambiguous
# acronyms/proper nouns Kent says with confidence; spell-checking
# them mid-chapter feels mechanical and misses the story.
_FRAGILE_NAMES_TIER_A = frozenset({
    # German place names with non-English orthography
    "landstuhl", "ramstein", "kaiserslautern",
    "hochspeyer", "wiesbaden",
    # German cultural landmark
    "salamander",
    # Person name with German spelling — easy to drift
    "schmick",
    # Hospital + base names where Kent already corrected (Lansdale
    # → Landstuhl); locking the corrected spelling matters
    "lansdale army hospital", "landstuhl air force hospital",
    "ramstein air force base",
    # Janice's chapter — Norwegian/foreign equivalents
    "trondheim",
})

# TIER B — conditionally-fragile names. Common American + clear
# institutional names that do NOT need confirmation in normal use.
# Only fire when narrator signals uncertainty or self-corrects.
#
# Per Chris's 2026-05-10 review: "Army Security Agency / Nike Ajax /
# Nike Hercules / Fort Ord / Fargo / Stanley / Bismarck / GED /
# M1 rifle" should NOT be priority-1 immediate spelling questions.
# They bank as factual anchors but never dominate Lori's immediate
# response to a chapter. Spelling-confirm reserves for genuinely
# uncertain or foreign names.
_FRAGILE_NAMES_TIER_B = frozenset({
    # Common American place names
    "stanley", "fargo", "bismarck", "fort ord",
    "minot", "spokane", "norway", "oslo",
    # Well-known European city
    "frankfurt",
    # Common American surname
    "duffy",
    # Clear English institutional names — Kent says these with
    # confidence; bank only with explicit uncertainty marker
    "army security agency",
    "nike ajax", "nike hercules",
    "32nd artillery brigade", "32nd brigade",
    # Common American base name
    "selfridge",
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

    # (1) Self-correction — strict gate: captured value must look
    # like a real proper-noun correction, not narrator's prose.
    for rx in _SELF_CORRECTION_PATTERNS:
        m = rx.search(narrator_text)
        if not m:
            continue
        try:
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
        # Reject common-English-word false positives
        if corrected.lower() in _SELF_CORRECTION_VALUE_BLOCKLIST:
            continue
        # Final sanity: the corrected value must EITHER be multi-word
        # (Title Case multiple tokens) OR be a known TIER A fragile
        # name OR start with uppercase + ≥7 chars (likely proper noun).
        # Single short uppercase words like "Nike" / "Army" / "Janice"
        # are too ambiguous to fire a correction door without context.
        is_multiword = len(corrected.split()) >= 2
        is_tier_a = corrected.lower() in _FRAGILE_NAMES_TIER_A
        is_long_propnoun = (
            len(corrected) >= 7
            and corrected[0].isupper()
            and corrected.replace("-", "").isalpha()
        )
        if not (is_multiword or is_tier_a or is_long_propnoun):
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

    # (3) TIER B names — only fire when uncertainty marker present
    # AND the name appears near the marker. Cap at ONE door per
    # turn — Chris's 2026-05-10 review caught the prior version
    # firing 7 redundant `_uncertain` doors when one "I wish I"
    # marker appeared in a long monologue. The narrator's
    # uncertainty was about ONE name, not all named places.
    if _has_uncertainty_marker(narrator_text):
        # Find the position of the first uncertainty marker in text
        first_marker_pos = len(narrator_text)
        for rx in _UNCERTAINTY_PATTERNS:
            m = rx.search(narrator_text)
            if m and m.start() < first_marker_pos:
                first_marker_pos = m.start()
        # Find the closest TIER B name to the marker (within 200
        # chars on either side). The narrator's uncertainty is
        # almost always about something they just said or are
        # about to say — not a name 1000 chars away.
        best_fragile = None
        best_distance = 10**9
        best_canonical = ""
        WINDOW = 200
        for fragile in _FRAGILE_NAMES_TIER_B:
            for m in re.finditer(
                rf"\b({re.escape(fragile)})\b",
                narrator_text,
                re.IGNORECASE,
            ):
                dist = abs(m.start() - first_marker_pos)
                if dist > WINDOW:
                    continue
                if dist < best_distance:
                    best_distance = dist
                    best_fragile = fragile
                    best_canonical = m.group(1)
        if best_fragile:
            doors.append(Door(
                intent=f"fragile_name_confirm_{best_fragile.replace(' ', '_')}_uncertain",
                question_en=(
                    f"You sounded a little unsure — was it "
                    f"{best_canonical}, or something close to that?"
                ),
                triggering_anchor=best_canonical,
                why_it_matters=(
                    f"Narrator signaled uncertainty near "
                    f"'{best_canonical}'. Confirming now while "
                    f"context is fresh prevents the memoir locking "
                    f"in a wrong spelling."
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


# ── BANK_PRIORITY_REBUILD 2026-05-10 — Tier model + story-weight ─────────
#
# Per the signed-off synthesis at docs/reports/BANK_PRIORITY_REBUILD_
# 2026-05-10.md: the bank prioritizes story doors (oral-history follow-
# ups), not spellings. Tier 1A is the story-weighted named particular
# the narrator just emphasized. Tier N is mechanical record cleanup.
# The Kent / adult-competence overlay demotes sensory to bank-only.

# Story-weighted anchor candidate scoring per synthesis §3 Tier 1A.
# A "named particular" is an object/person/decision the narrator
# repeated, developed, or emphasized. The anchor with highest story-
# weight wins Tier 1A.

_NARRATOR_EMPHASIS_PHRASES = (
    "that mattered to me", "still stands out", "i want it preserved",
    "i want the name right", "i want it right",
    "that was when", "that was the",
    "i remember that", "i'll never forget",
    "the most important", "the biggest",
    "first army", "first time",
    "that counted", "it counted",
    "i did well", "i scored",
)

# Object-of-responsibility anchor patterns. These are story-weighted
# anchors specific to adult-competence narratives (Kent's meal
# tickets, Janice's family arrangements, etc.). Add patterns here as
# new narrators surface them. Each is a (regex, anchor_label) pair.
_RESPONSIBILITY_ANCHOR_PATTERNS = (
    # Kent — meal tickets episode
    (re.compile(r"\bmeal[\s-]ticket(?:s|s?)\b", re.IGNORECASE), "meal tickets"),
    # Kent — M1 expert qualification
    (re.compile(r"\bM[\s-]?1\s+(?:rifle|expert|qualif)", re.IGNORECASE), "M1 expert qualification"),
    # Kent — courier route
    (re.compile(r"\bcourier\s+(?:route|run|job)\b", re.IGNORECASE), "courier route"),
    # Kent — photography work
    (re.compile(r"\bphotograph(?:y|er)\s+(?:work|job|assignment)\b", re.IGNORECASE), "photography work"),
    # Generic — "I was put in charge of X"
    (re.compile(r"\bin charge of\s+([a-z][a-z\s]{3,30})\b", re.IGNORECASE), None),
    # Generic — "responsible for X"
    (re.compile(r"\bresponsible for\s+([a-z][a-z\s]{3,30})\b", re.IGNORECASE), None),
)


def _score_story_weight(anchor_text: str, narrator_text: str) -> int:
    """Story-weight scoring per synthesis §3 Tier 1A.

    repetition_count ×3 if anchor appears ≥3 times
                     ×2 if 2 times
                     ×1 if once
    development_depth +2 if 2+ sentences develop the anchor
                      +1 if 1 sentence develops it
    narrator_emphasis +2 if "that mattered to me" / "still stands
                         out" / "first time" / etc. within ±100 chars
    sentence_neighborhood +1 if anchor has ≥3 sentences in semantic
                          neighborhood (not just listed)
    """
    if not anchor_text or not narrator_text:
        return 0
    anchor_lower = anchor_text.lower()
    text_lower = narrator_text.lower()

    # Repetition
    rep = text_lower.count(anchor_lower)
    if rep == 0:
        return 0
    if rep >= 3:
        weight_rep = 3
    elif rep == 2:
        weight_rep = 2
    else:
        weight_rep = 1

    # Development depth — count sentences that contain the anchor
    sentences = re.split(r'[.!?]+\s+', narrator_text)
    dev_count = sum(1 for s in sentences if anchor_lower in s.lower())
    if dev_count >= 2:
        weight_dev = 2
    elif dev_count == 1:
        weight_dev = 1
    else:
        weight_dev = 0

    # Narrator emphasis — within ±100 chars of any anchor occurrence
    weight_emph = 0
    for m in re.finditer(re.escape(anchor_lower), text_lower):
        window_start = max(0, m.start() - 100)
        window_end = min(len(text_lower), m.end() + 100)
        window = text_lower[window_start:window_end]
        if any(p in window for p in _NARRATOR_EMPHASIS_PHRASES):
            weight_emph = 2
            break

    # Sentence neighborhood — sentences within 2-sentence window
    # before or after each anchor occurrence
    weight_neigh = 0
    for i, s in enumerate(sentences):
        if anchor_lower not in s.lower():
            continue
        # Count sentences ±2 around this one that contain the anchor
        # OR develop a related token
        nearby = sentences[max(0, i-2):min(len(sentences), i+3)]
        if len(nearby) >= 3:
            weight_neigh = 1
            break

    return weight_rep + weight_dev + weight_emph + weight_neigh


def _detect_story_weighted_tier_1a_doors(narrator_text: str) -> List[Door]:
    """Story-weighted named-particular detector (Tier 1A).

    Walks the narrator text for named-particular candidates (objects-
    of-responsibility from `_RESPONSIBILITY_ANCHOR_PATTERNS`, plus
    multi-word proper-noun phrases that recur 2+ times). Scores each
    via `_score_story_weight()`. Returns the highest-scoring anchor
    as a Tier 1A door.

    The cue type is `work_survival` for responsibility/role anchors,
    `object_keepsake` for narrator-named objects. The question_en
    follows the "seek the particular" rule: invite the narrator to
    say more about THIS specific named anchor.
    """
    doors: List[Door] = []
    if not narrator_text:
        return doors

    candidates: List[Tuple[str, int]] = []  # (anchor_label, score)
    seen: set = set()

    # Pass 1 — explicit responsibility patterns
    for rx, fixed_label in _RESPONSIBILITY_ANCHOR_PATTERNS:
        for m in rx.finditer(narrator_text):
            label = fixed_label
            if label is None:
                # Generic capture group
                try:
                    captured = m.group(1).strip()
                except (IndexError, re.error):
                    captured = ""
                if not captured or len(captured) < 4:
                    continue
                label = captured
            label_key = label.lower()
            if label_key in seen:
                continue
            seen.add(label_key)
            score = _score_story_weight(label, narrator_text)
            if score >= 2:  # minimum threshold for Tier 1A
                candidates.append((label, score))

    # Pass 2 — narrator-named multi-word proper-noun phrases that
    # recur 2+ times. These are the "named particular" anchors per
    # Voice Library §10A row 1.
    propnoun_rx = re.compile(
        r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){1,3})\b"
    )
    propnoun_counts: Dict[str, int] = {}
    for m in propnoun_rx.finditer(narrator_text):
        token = m.group(1).strip()
        # Skip generic / well-known institutional names — those are
        # Tier N, not Tier 1A. Per Chris's locked rule.
        if token.lower() in _FRAGILE_NAMES_TIER_B:
            continue
        if token.lower() in (
            "army security agency", "nike ajax", "nike hercules",
            "32nd brigade", "32nd artillery brigade",
        ):
            continue
        propnoun_counts[token] = propnoun_counts.get(token, 0) + 1
    for token, count in propnoun_counts.items():
        if count < 2:
            continue  # singletons aren't story-weighted
        token_key = token.lower()
        if token_key in seen:
            continue
        score = _score_story_weight(token, narrator_text)
        if score >= 2:
            candidates.append((token, score))
            seen.add(token_key)

    if not candidates:
        return doors

    # Pick the highest-scoring anchor
    candidates.sort(key=lambda p: -p[1])
    best_anchor, best_score = candidates[0]

    # Compose a "seek the particular" question — invite narrator to
    # say more about THIS specific anchor. The wording follows
    # Alshenqeeti's "always seek the particular" rule + Voice Library
    # §10A "What was that anchor like?" shape.
    door = Door(
        intent="story_weighted_named_particular",
        question_en=(
            f"You came back to {best_anchor} more than once — what "
            f"did it actually look like, day to day?"
        ),
        triggering_anchor=best_anchor,
        why_it_matters=(
            f"The narrator emphasized '{best_anchor}' (story-weight "
            f"score {best_score}). Per Voice Library §10A, the named "
            f"particular the narrator returned to is the strongest "
            f"anchor for an active-listening response."
        ),
        priority=1,
        tier="1A",
        story_weight=best_score,
    )
    doors.append(door)
    return doors


def _is_sensory_door(door: Door) -> bool:
    """True when the door is asking about sensory texture (smell /
    sound / sight / taste / atmosphere). Per Chris's 2026-05-10 lock,
    these bank but do NOT auto-immediate under adult_competence
    overlay."""
    import re
    intent_lower = (door.intent or "").lower()
    q_lower = (door.question_en or "").lower()
    if "daily_life_off_duty" in intent_lower:
        return True
    if "sensory" in intent_lower:
        return True
    # Literal substring patterns (fast path) — these are unambiguously
    # sensory regardless of object. Excludes bare "look like" / "feel
    # like" since they're overloaded ("what did the schedule look like"
    # is logistical, not sensory).
    sensory_q_patterns = (
        "what did it smell", "what was the smell",
        "what did it sound", "what did it look like",
        "what was the atmosphere", "what did it feel like",
        "what was that like", "what was it like in",
        "smell like", "sound like", "taste like",
    )
    if any(p in q_lower for p in sensory_q_patterns):
        return True
    # Flexible regex for "what did <X> feel/smell/sound/look/taste like"
    # — fires when narrator's anchor is wrapped in the sensory shape
    # but the literal substring above didn't match (e.g., "what did the
    # courier route feel like during long days").
    sensory_regex_patterns = (
        r"\bwhat\s+did\s+(?:the\s+|a\s+|that\s+|those\s+|these\s+)?\w+(?:\s+\w+){0,3}\s+(?:feel|smell|sound|taste)\s+like\b",
        r"\bwhat\s+was\s+(?:the\s+|that\s+|it\s+)?\s*atmosphere\b",
        r"\bwhat\s+(?:did|was|were)\s+the\s+\w+(?:\s+\w+){0,4}\s+(?:smell|sound|sight)\b",
    )
    for pat in sensory_regex_patterns:
        if re.search(pat, q_lower):
            return True
    return False


def _is_tier_n_spelling_confirm(door: Door) -> bool:
    """True when the door is a Tier-N institutional spelling-confirm
    that should NEVER auto-immediate. Per Chris's locked rule."""
    intent_lower = (door.intent or "").lower()
    # Clear institutional names that should never spelling-confirm
    tier_n_anchors = (
        "army_security_agency", "nike_ajax", "nike_hercules",
        "32nd_brigade", "32nd_artillery_brigade",
        "fort_ord", "stanley", "fargo", "bismarck",
    )
    if any(t in intent_lower for t in tier_n_anchors):
        # Only Tier N if NOT a self-correction (self-corrections still
        # get immediate per Tier 1B)
        if "correction" not in intent_lower:
            return True
    return False


# ── Public API ──────────────────────────────────────────────────────────────


def detect_doors(narrator_text: str, history: Optional[List[Dict]] = None) -> List[Door]:
    """Return all doors opened by the narrator turn, in priority order
    (1 first). The caller picks the immediate door (priority 1-3) and
    banks the rest. Priority 4-6 always bank, never immediate.

    BANK_PRIORITY_REBUILD 2026-05-10: now includes Tier 1A story-
    weighted named-particular detector that fires BEFORE the legacy
    fragile-name detectors. The Tier 1A door (when present) becomes
    the immediate-ask candidate — beating spelling-confirms.

    history is currently unused but reserved for future "have we
    already asked this in a prior turn?" deduplication. v1 relies on
    the DB-level (session_id, intent, triggering_anchor) dedupe.
    """
    if not narrator_text or not narrator_text.strip():
        return []

    doors: List[Door] = []
    # Story-weighted Tier 1A — runs FIRST so it dominates selection
    doors.extend(_detect_story_weighted_tier_1a_doors(narrator_text))
    # Legacy detectors — produce doors with numeric priority
    doors.extend(_detect_fragile_name_doors(narrator_text))
    doors.extend(_detect_communication_logistics_doors(narrator_text))
    doors.extend(_detect_role_transition_doors(narrator_text))
    doors.extend(_detect_relationship_doors(narrator_text))
    doors.extend(_detect_daily_life_doors(narrator_text))
    doors.extend(_detect_medical_family_doors(narrator_text))

    # Sort by priority (lower = more urgent), then by intent for
    # deterministic ordering across runs. Tier 1A doors have
    # priority=1 so they sort with other priority-1 doors but win
    # alphabetically (intent="story_weighted_named_particular"
    # — actually that sorts AFTER "fragile_name_*", let the selector
    # apply story_weight tie-break).
    doors.sort(key=lambda d: (d.priority, d.intent))
    return doors


def select_immediate_and_bank(
    doors: List[Door],
    *,
    narrator_voice_overlay: str = "default",
) -> Tuple[Optional[Door], List[Door]]:
    """BANK_PRIORITY_REBUILD 2026-05-10 selector with Kent overlay.

    Selection rules:

      1. Priority 1-3 doors MAY be immediate.
      2. Priority 4-6 doors NEVER immediate. Always bank.
      3. Tier 1A story-weighted named particular WINS within priority 1
         (sorts above other priority-1 doors via story_weight).
      4. Tier-N institutional spelling-confirm doors NEVER immediate.
         They downgrade to bank even if they hit priority 1.
      5. Under `adult_competence` overlay (Kent), Tier 5 sensory doors
         are excluded from immediate consideration. They bank only.
      6. Under `shield_protected` overlay, sensitive doors return
         (None, ...) — no immediate question, only bank/operator review.

    Per Chris's 2026-05-10 locked rule for Kent: sensory questions are
    bank-only unless Kent himself dwells on a sensory anchor (caller's
    responsibility to detect — this selector trusts the overlay).

    Returns (immediate_door, doors_to_bank). immediate_door is None
    when only priority 4-6 doors are open OR all priority 1-3 doors
    are filtered out by overlay rules.
    """
    if not doors:
        return (None, [])

    # Sort: priority asc, then story_weight desc (Tier 1A wins ties),
    # then intent asc for deterministic order
    sorted_doors = sorted(
        doors,
        key=lambda d: (d.priority, -d.story_weight, d.intent),
    )

    # Filter immediate-eligible doors:
    #   - priority ≤ 3
    #   - NOT a Tier-N institutional spelling-confirm
    #   - NOT a sensory door under adult_competence overlay
    immediate_eligible = []
    for d in sorted_doors:
        if d.priority > 3:
            continue
        if _is_tier_n_spelling_confirm(d):
            continue
        if narrator_voice_overlay == "adult_competence" and _is_sensory_door(d):
            continue
        immediate_eligible.append(d)

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

    # ── PROTECT THE NARRATOR'S MONOLOGUE ──────────────────────────
    # Per Chris's 2026-05-10 floor-control rule: Kent should be able
    # to talk uninterrupted for 10-30 minutes. The bank-flush MUST
    # NEVER fire mid-chapter. Hard gate: any narrator turn with
    # ≥40 words is a chapter, not a "what else?" cue. Skip flush.
    word_count = len(narrator_text.split())
    if word_count >= 40:
        return (False, "")

    # (b) explicit narrator cue — must be in the LAST sentence of
    # the narrator turn, not embedded in narrative prose. Plus the
    # last sentence must be SHORT (≤8 words) — a cue-word inside a
    # 25-word last sentence is rhetoric, not a flush request.
    parts = re.split(r'[.!?]\s+', narrator_text.rstrip())
    last_sentence = parts[-1] if parts else narrator_text
    last_sentence_words = len(last_sentence.split())
    if last_sentence_words <= 8 and any(
        rx.search(last_sentence) for rx in _FLUSH_CUE_PATTERNS
    ):
        return (True, "narrator_cued")

    # (a) short narrator answer + no new door
    if word_count < 8 and not current_turn_doors:
        return (True, f"short_answer_no_door:{word_count}w")

    return (False, "")


# ── Bank-flush composer ────────────────────────────────────────────────────


_BANK_FLUSH_PHRASE = "I want to come back to one detail you mentioned earlier."

# Defense-in-depth: even if the door detector mis-fires and writes a
# malformed fragile-name-correction door to the bank, the bank-flush
# composer refuses to surface it to the narrator. A "Got it — you
# corrected to just" question never reaches Kent.
#
# Patterns to reject (case-insensitive substring on the question_en):
_BANK_FLUSH_MALFORMED_PATTERNS = (
    "corrected to just",
    "corrected to going",
    "corrected to making",
    "corrected to thinking",
    "corrected to saying",
    "corrected to telling",
    "corrected to right",
    "corrected to wrong",
    "corrected to actually",
    "corrected to nothing",
    "corrected to something",
    "corrected to one ",
    "corrected to two ",
    "corrected to three ",
    "corrected to first",
    "corrected to next",
    "corrected to today",
    "corrected to tomorrow",
)


def is_bank_question_malformed(question_en: str) -> bool:
    """True when a banked question contains junk-correction shape
    that should never surface to the narrator. Use as a filter
    before flushing — if True, skip this banked entry and try the
    next."""
    if not question_en:
        return True
    q_lower = question_en.lower()
    for pat in _BANK_FLUSH_MALFORMED_PATTERNS:
        if pat in q_lower:
            return True
    return False


def compose_bank_flush_response(banked_question_text: str) -> str:
    """Fixed phrase + the banked question. The phrase is locked because
    it's a recognizable rhythm cue for the narrator — they should feel
    Lori is circling back, not interrogating fresh.

    Returns "" when the banked question is malformed (junk correction
    captured by a regex false-positive). The caller should then pick
    the next banked question OR skip the flush entirely for this turn.
    """
    if not banked_question_text:
        return ""
    if is_bank_question_malformed(banked_question_text):
        return ""
    return f"{_BANK_FLUSH_PHRASE} {banked_question_text}"


__all__ = [
    "Door",
    "detect_doors",
    "select_immediate_and_bank",
    "should_flush_bank",
    "compose_bank_flush_response",
]
