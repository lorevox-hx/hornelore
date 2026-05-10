"""Lori witness mode + meta-feedback deterministic intercept.

Pure-function module — detects when a narrator is either:
  (A) giving Lori meta-feedback that her behavior is wrong
      ("stop the sensory probes", "you are being vague", "I want
       facts not feelings", "let me tell my story")
  (B) delivering a multi-paragraph structured factual narrative
      (admissions test → train → exam → score → assignment) that
      should NOT be interrupted with sensory probes

Either condition switches the response posture into "witness mode":
emit a deterministic acknowledgment (for type A) and a continuation
invitation that follows the narrator's thread, with NO sensory probe,
NO feeling probe, NO topic shift.

Why this exists
---------------
Kent's session 2026-05-09 20:41-20:53 (`transcript_switch_moyt6.txt`)
exposed the structural bias of Lori's listener stack:

  Line 38: Kent answers about basic-training admissions with FIVE
  concrete factual events (admissions test, Stanley→Fargo train,
  physical+mental exams, top score, meal-ticket assignment for a
  trainload of recruits to the West Coast).

  Line 41: Lori responds with "What do you remember about the
  scenery or the trip itself?" — five facts ignored, sensory probe.

  Line 80: Kent gives explicit meta-feedback: "You are being vague
  and not asking about basic training rather the sensory parts of
  it. I want to tell my experience and you want to know how I
  felt."

  Line 82: Lori apologizes and proposes MORE sensory probes:
  "Let's focus on the sensory aspects of basic training. What do
  you remember about the sights, sounds, and smells?"

Kent walked. His narrator type — factually rich, chronologically
structured, professional-life arc (basic training → Germany →
marriage → second Germany deployment → child → missile operator →
photographer for a general → teacher → doctor) — wants the system
to keep recording, not extract feelings.

Architectural pattern (mirrors today's BUG-LORI-IDENTITY-META-
QUESTION-DETERMINISTIC-ROUTE-01):

  - Pure regex + heuristic detection, no LLM call
  - LAW 3 isolated: no extract / chat_ws / llm / safety / db
    imports
  - Locale-aware (en + es)
  - Wired into chat_ws.py AFTER the meta-question intercept and
    AFTER safety scan but BEFORE the LLM
  - When fires: deterministic answer, skip LLM, persist via
    existing turn-transaction path

The failure shape that walked Kent out — "Lori responded to my
correction by doing more of what I told her to stop" — vanishes
because the LLM is removed from the loop on this class of turn.

Public API
----------
detect_witness_event(text) -> WitnessDetection | None
    Pure detector. Returns None when the turn isn't a witness
    event. Otherwise returns a dataclass with detection_type
    (META_FEEDBACK / STRUCTURED_NARRATIVE) and any pulled anchors.

compose_witness_response(detection, target_language="en") -> str
    Builds the deterministic narrator-facing string.

detect_and_compose(text, target_language="en") -> WitnessAnswer | None
    Convenience wrapper.

Default-on, no env flag — correctness fix.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ── Detection: TYPE A — META-FEEDBACK ─────────────────────────────────────
#
# Narrator is correcting Lori's behavior. Kent's literal 2026-05-09
# turn is the canonical example: "You are being vague and not asking
# about basic training rather the sensory parts of it. I want to tell
# my experience and you want to know how I felt."
#
# Patterns split into specific categories so the composer can emit
# the right acknowledgment + continuation. Order doesn't matter for
# detection; for composer routing we pick the most specific match.

# A1. STOP SENSORY — "stop asking about sensory" / "you keep asking
#     about sights/sounds/smells" / "I don't want sensory questions"
_META_STOP_SENSORY_EN = [
    # "stop/don't asking about [the] sensory|sights|sounds|smells|how i felt|feelings|emotions"
    # — "about" is optional so "don't keep asking how I felt" matches
    re.compile(r"\b(?:stop|don'?t|quit)\s+(?:keep\s+)?(?:asking|talking)\s+(?:about\s+)?(?:the\s+)?(?:sensory|sights|sounds|smells|how\s+i\s+felt|how\s+i\s+feel|feelings|emotions)\b", re.IGNORECASE),
    re.compile(r"\byou\s+(?:are|keep|always)\s+(?:asking|talking)\s+(?:about\s+)?(?:the\s+)?(?:sensory|how\s+i\s+felt|how\s+i\s+feel|feelings|emotions)\b", re.IGNORECASE),
    re.compile(r"\bnot\s+(?:the\s+)?sensory\b", re.IGNORECASE),
    re.compile(r"\bsensory\s+parts?\s+of\s+it\b", re.IGNORECASE),
]

_META_STOP_SENSORY_ES = [
    re.compile(r"\b(?:deja|para|no)\s+(?:de\s+)?(?:preguntar|hablar)\s+(?:sobre|de)\s+(?:los\s+)?(?:sentidos|sensaciones|c[oó]mo\s+me\s+sent[ií])\b", re.IGNORECASE),
    re.compile(r"\bno\s+(?:los\s+)?(?:sentidos|sensaciones)\b", re.IGNORECASE),
]

# A2. WANT FACTS / NOT FEELINGS — "I want to tell my experience and
#     you want to know how I felt" / "facts not feelings" / "details
#     not emotions"
_META_WANT_FACTS_EN = [
    re.compile(r"\bi\s+want\s+(?:to\s+)?(?:tell|share|describe)\s+(?:my\s+)?(?:experience|story|story|life)\b", re.IGNORECASE),
    re.compile(r"\b(?:facts?|details?|specifics?)\s+not\s+(?:feelings?|emotions?|sensory|sights?\s+sounds?)\b", re.IGNORECASE),
    re.compile(r"\byou\s+want\s+to\s+know\s+how\s+i\s+felt\b", re.IGNORECASE),
    re.compile(r"\b(?:i'?m|i\s+am)\s+trying\s+to\s+(?:tell|describe)\b", re.IGNORECASE),
    # BUG-LORI-WANT-FACTS-FALSE-POSITIVE-01 (2026-05-10): "let me
    # tell" alone matches narrator's own framing ("Let me tell it
    # in order because one thing led to the next" — Kent's K-COMBINED
    # opener triggered want_facts deterministic ack). Tightened to
    # require finish/describe/explain (which signal "Lori, get out
    # of my way") OR tell paired with you-stop pattern. Bare "let me
    # tell" / "let me tell my story" no longer trigger.
    re.compile(r"\blet\s+me\s+(?:finish|describe|explain)\b", re.IGNORECASE),
    re.compile(r"\blet\s+me\s+tell\s+(?:you\s+)?(?:without|before)\s+(?:you\s+)?(?:interrupt|asking|stopping)", re.IGNORECASE),
]

_META_WANT_FACTS_ES = [
    re.compile(r"\bquiero\s+(?:contar|describir|compartir)\s+(?:mi\s+)?(?:experiencia|historia|vida)\b", re.IGNORECASE),
    re.compile(r"\b(?:hechos|detalles)\s+no\s+(?:sentimientos|emociones)\b", re.IGNORECASE),
    re.compile(r"\bd[eé]jame\s+(?:contar|terminar|describir|explicar)\b", re.IGNORECASE),
]

# A3. BEING VAGUE / NOT LISTENING — "you are being vague" / "you are
#     not listening" / "you skipped what I said"
_META_BEING_VAGUE_EN = [
    re.compile(r"\byou\s+(?:are|'?re)\s+being\s+(?:vague|too\s+general|generic|abstract)\b", re.IGNORECASE),
    re.compile(r"\byou\s+(?:are|'?re)\s+not\s+(?:listening|hearing|paying\s+attention)\b", re.IGNORECASE),
    re.compile(r"\byou\s+(?:skipped|ignored|missed)\s+(?:what\s+i\s+said|that)\b", re.IGNORECASE),
    re.compile(r"\bthat'?s?\s+not\s+(?:important|what\s+i\s+said|relevant)\b", re.IGNORECASE),
]

_META_BEING_VAGUE_ES = [
    re.compile(r"\beres\s+(?:muy\s+)?(?:vag[oa]|general|abstract[oa])\b", re.IGNORECASE),
    re.compile(r"\bno\s+(?:est[aá]s\s+)?escuchando\b", re.IGNORECASE),
    re.compile(r"\b(?:te\s+)?saltaste\s+lo\s+que\s+dije\b", re.IGNORECASE),
]

# A4. ASK ABOUT X NOT Y — "ask about basic training not the sensory
#     parts" / "ask about facts not feelings"
_META_ASK_ABOUT_X_NOT_Y_EN = [
    re.compile(r"\bask\s+about\s+\w+(?:\s+\w+){0,5}\s+not\s+(?:the\s+)?(?:sensory|sights|sounds|smells|feelings|emotions)\b", re.IGNORECASE),
    re.compile(r"\bnot\s+asking\s+about\s+\w+(?:\s+\w+){0,3}\s+rather\s+the\s+sensory\b", re.IGNORECASE),
]


# ── Detection: TYPE C — CORRECTION (NEW 2026-05-10) ───────────────────────
#
# BUG-LORI-CORRECTION-PERSPECTIVE-INVERSION-01 — Kent's K10 turn was
# "you have the name of the hospital wrong not Lansdale Army hospital
# but landstuhl air force hospital ramstein air force base". Lori
# responded by FIRST-PERSON ECHOING the correction as if she were
# Kent: "So while we were in Kaiserslautern our son Vince was born at
# Landstuhl Air Force Hospital, and we took care of all of the birth."
# Kent: "you are talking like you are me." Then Lori got confused
# about her role.
#
# The deterministic intercept extracts the correction (the AFTER value
# in "not X but Y" / "actually Y" / "the name is Y") and emits a
# strict second-person acknowledgment that NEVER uses "we" / "our" /
# "I" perspective markers. Like meta-feedback, this fires before the
# LLM, so the perspective-mimicry failure mode becomes structurally
# impossible.
_META_CORRECTION_EN = [
    # "you have/got the name of X wrong"
    re.compile(r"\byou\s+(?:have|got)\s+(?:the\s+)?(?:name\s+of\s+)?(?:the\s+)?\w+(?:\s+\w+){0,5}\s+wrong\b", re.IGNORECASE),
    # "not X but Y" / "not X, it was Y"
    re.compile(r"\bnot\s+\w+(?:\s+\w+){1,8}\s+but\s+(?:the\s+)?\w+", re.IGNORECASE),
    # "actually it was/is Y" / "actually, Y"
    re.compile(r"\bactually\s+(?:it\s+(?:was|is|'s)\s+)?[A-Z]?\w+", re.IGNORECASE),
    # "I meant Y" / "I said Y not"
    re.compile(r"\bi\s+(?:meant|said)\s+\w+", re.IGNORECASE),
    # "the [thing] was/is Y" — strong signal it's a correction
    re.compile(r"\bthe\s+(?:name|hospital|base|place|year|date|number|address)\s+(?:was|is|'s)\s+\w+", re.IGNORECASE),
    # "that's wrong" / "that is wrong" / "incorrect"
    re.compile(r"\b(?:that'?s|that\s+is|you\s+are|you'?re)\s+(?:wrong|incorrect|mistaken)\b", re.IGNORECASE),
]
_META_CORRECTION_ES = [
    re.compile(r"\bno\s+es\s+\w+(?:\s+\w+){0,5}\s+(?:es|sino)\s+\w+", re.IGNORECASE),
    re.compile(r"\bestá[s]?\s+equivocad[oa]s?\b", re.IGNORECASE),
    re.compile(r"\bquise\s+decir\b", re.IGNORECASE),
]


# Pattern to extract the CORRECTION (the AFTER value) from a correction
# turn. We look for "not X but Y" / "not X, Y" forms where Y is the
# correct value. Captures multi-word values up to 8 tokens.
_CORRECTION_AFTER_RX = (
    # "not [X] but/, [Y]" — stops at first terminator after Y
    re.compile(
        r"\bnot\s+[A-Za-z][A-Za-z\s]{2,40}?\s+(?:but|,)\s+([A-Za-z][A-Za-z\s]{2,80}?)(?:\.|,|;|$)",
        re.IGNORECASE,
    ),
    # "actually [Y]" / "actually it was [Y]"
    # Y stops at first " not " / punctuation / end
    re.compile(
        r"\bactually\s+(?:it\s+(?:was|is|'s)\s+)?([A-Za-z][A-Za-z\s]{2,40}?)(?:\s+not\s+|[\.\?!,;]|$)",
        re.IGNORECASE,
    ),
    # "I meant [Y]" / "I said [Y]" — Y stops at " not " / punct / end
    re.compile(
        r"\bi\s+(?:meant|said)\s+([A-Za-z][A-Za-z\s]{2,40}?)(?:\s+not\s+|[\.\?!,;]|$)",
        re.IGNORECASE,
    ),
    # "the [thing] was/is [Y]" — Y stops at " not " / punct / end
    re.compile(
        r"\bthe\s+(?:name|hospital|base|place)\s+(?:was|is|'s)\s+([A-Za-z][A-Za-z\s]{2,40}?)(?:\s+not\s+|[\.\?!,;]|$)",
        re.IGNORECASE,
    ),
)


def _extract_correction_value(text: str) -> str:
    """Extract the corrected (AFTER) value from a correction turn.

    For Kent's K10: "you have the name of the hospital wrong not
    Lansdale Army hospital but landstuhl air force hospital ramstein
    air force base" → returns "Landstuhl Air Force Hospital Ramstein
    Air Force Base".

    Returns "" if no clean AFTER value can be extracted (the composer
    falls back to a generic acknowledgment).

    Note: narrators often type corrected proper nouns in lowercase
    ("landstuhl air force hospital ramstein air force base"). We
    Title-Case BEFORE sanitizing so the standard sanitizer's
    proper-noun heuristic accepts longer multi-word place names
    instead of rejecting them as pronoun-heavy fragments.
    """
    if not text:
        return ""
    cleaned = re.sub(r"\[SYSTEM:.*?\]", " ", text or "", flags=re.DOTALL)
    for rx in _CORRECTION_AFTER_RX:
        m = rx.search(cleaned)
        if m:
            value = m.group(1).strip().rstrip(".,;:")
            if not value:
                continue
            # Title-case BEFORE sanitize so multi-word lowercase
            # corrections (Kent typed "landstuhl air force hospital
            # ramstein air force base") pass the proper-noun heuristic.
            value_titled = value.title()
            sanitized = _sanitize_anchor(value_titled)
            if sanitized:
                return sanitized
    return ""


# ── Detection: TYPE B — STRUCTURED NARRATIVE ──────────────────────────────
#
# Narrator delivered a multi-event chronological turn that should NOT
# be met with a sensory probe. Heuristic: word count ≥ 40 AND ≥ 2
# chronological connectors AND ≥ 2 distinct events/actions.
#
# We're conservative — false negatives (witness mode misses a real
# narrative) fall through to the LLM which will probably ask a sensory
# probe (the regression). False positives (witness mode fires on a
# non-narrative) emit a "tell me more" continuation which is a safe
# response in any context.

_CHRONOLOGICAL_CONNECTORS_EN = (
    r"\bthen\b",
    r"\band\s+then\b",
    r"\bafter\s+(?:that|i\s+\w+|the\s+\w+|going|getting)",
    r"\bafterwards?\b",
    r"\bbefore\s+(?:that|i\s+\w+)",
    r"\bnext\b",
    r"\bfirst\b",
    r"\blater\b",
    r"\beventually\b",
    r"\bfrom\s+there\b",
    r"\bwhen\s+i\s+(?:was|got|went|came|left|arrived|finished|started|enlisted)",
    r"\bduring\s+(?:that|the|my)",
    r"\bafter\s+the\b",
    r"\bonce\s+(?:i|we|that)",
    # Present-participle "going to/from/through" — Kent's idiom for
    # narrating a sequence ("going from Stanley to Fargo", "going
    # through the admissions test", "going to the West Coast"). Each
    # occurrence signals a chronological step in his telling.
    r"\bgoing\s+(?:from|to|through)\b",
    r"\bhaving\s+to\s+(?:go|do|take)\b",
    r"\bcame\s+back\b",
    r"\bcame\s+home\b",
    r"\bsent\s+(?:to|overseas|home)\b",
)

_CHRONOLOGICAL_CONNECTORS_ES = (
    r"\bdespu[eé]s\b",
    r"\bluego\b",
    r"\bantes\s+de\b",
    r"\bm[aá]s\s+tarde\b",
    r"\beventualmente\b",
    r"\bcuando\s+(?:yo|era|fui|ten[ií]a)",
    r"\bdurante\b",
    r"\bentonces\b",
)

# Action-verb shapes — narrator describing things they did/were.
# Each tuple element is its own pattern so _count_pattern_hits can
# count distinct shape categories. Designed to catch both past-tense
# ("I went / I served") AND present-participle / other narrator
# idioms ("having to go through", "going from X to Y").
#
# ChatGPT review 2026-05-09 caught the original bug: a single big
# regex collapsed all verb categories into 0-or-1 hit. Splitting
# into category-distinct patterns lets the heuristic count breadth
# of narrative shape, which is what we actually want.
_ACTION_VERBS_EN = (
    # Past-tense self-action ("I went", "I enlisted", "I served")
    r"\bi\s+(?:went|enlisted|served|joined|got|finished|started|trained|worked|moved|traveled|drove|flew|deployed|transferred|promoted|graduated|enrolled|attended|qualified|received|earned|arrived|departed|left|returned|came\s+back|came\s+home|married|had|raised|taught|studied|learned|practiced|built|made|wrote|read|saw|met|knew|remembered)\b",
    # "I + got + adjective/noun" ("I got the highest score", "I got
    # the job") — Kent's literal pattern at line 38
    r"\bi\s+got\s+(?:the\s+)?(?:highest|top|best|first|second|next)\b",
    # "Having to (go|do|take|get|complete) ..." — Kent's idiom for
    # narrating obligations
    r"\bhaving\s+to\s+(?:go|do|take|get|complete|pass|finish)\b",
    # "Going (from|to|through) ..." — sequence narration
    r"\bgoing\s+(?:from|to|through)\b",
    # "to be (qualified|assigned|chosen|put|in charge|placed)"
    r"\bto\s+be\s+(?:qualified|assigned|chosen|placed|put|made)\b",
    # "put (me|him|her) in charge of"
    r"\bput\s+(?:me|him|her|us)\s+in\s+charge\s+of\b",
    # Kent-specific factual nouns/phrases that signal military / job
    # / professional narrative content
    r"\b(?:admissions?\s+test|physical\s+exam|mental\s+exam|basic\s+training)\b",
    r"\b(?:meal\s+tickets?|trainload|train\s+load)\b",
    r"\bin\s+charge\s+of\s+(?:all\s+)?(?:the\s+)?\w+",
    # Generic milestone/event nouns
    r"\b(?:deployment|reassignment|promotion|enlistment|discharge|tour\s+of\s+duty|mission|assignment)\b",
    # Movement narrative ("sent to", "arrived at", "shipped out",
    # "transferred to")
    r"\b(?:sent|shipped|transferred|reassigned|deployed|stationed)\s+(?:to|in|at|overseas|home)\b",
)


@dataclass(frozen=True)
class WitnessDetection:
    """The detection result. detection_type is the primary label;
    sub_type is the META-FEEDBACK refinement when applicable."""
    detection_type: str = ""  # "META_FEEDBACK" | "STRUCTURED_NARRATIVE" | ""
    sub_type: str = ""  # "stop_sensory" | "want_facts" | "being_vague" | "ask_x_not_y" | "structured" | "correction" | ""
    factual_anchor: str = ""  # last factual anchor pulled from text (single)
    multi_anchors: tuple = ()  # ordered tuple of up to 3 anchors for
                                # multi-anchor composer (BUG-LORI-WITNESS
                                # -MULTI-ANCHOR-01, 2026-05-10)
    event_phrases: tuple = ()  # ordered tuple of up to 4 narrator-action
                                # event clauses for active-receipt
                                # composer (BUG-LORI-WITNESS-ACTIVE
                                # -RECEIPT-01, 2026-05-10)
    word_count: int = 0
    chronological_connector_count: int = 0
    action_verb_count: int = 0

    @property
    def is_witness_event(self) -> bool:
        return self.detection_type in ("META_FEEDBACK", "STRUCTURED_NARRATIVE")


@dataclass(frozen=True)
class WitnessAnswer:
    """The composed deterministic response."""
    text: str
    language: str
    detection_type: str
    sub_type: str
    factual_anchor: str


# ── Anchor extraction ─────────────────────────────────────────────────────


# Words we never want to treat as proper-noun anchors (sentence-start
# capitalization, common abbreviations, pronouns)
_NOT_AN_ANCHOR = frozenset({
    "I", "Im", "I'm", "Ive", "I've", "We", "We're",
    "The", "A", "An", "And", "Or", "But", "So", "If",
    "When", "Where", "Why", "How", "What", "Who",
    "Yes", "No", "Maybe", "Sure", "Okay", "OK",
    "Then", "Now", "Today", "Tomorrow", "Yesterday",
    "Tell", "Let", "Give", "Take", "Make",
    "USA", "U.S.", "US", "AI",
})

# Place + role + event nouns we'd LIKE to surface as anchors when
# capitalized — Stanley, Fargo, Germany, Army, Navy, etc.
_PROPER_NOUN_RX = re.compile(r"\b([A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]+){0,2})\b")

# "the X" / "my X" definite-noun phrase fallback
_DEFINITE_NOUN_RX = re.compile(
    r"\b(?:the|my|our|that|those|these|this)\s+([a-z][a-z]+(?:\s+[a-z]+){0,3})\b",
    re.IGNORECASE,
)


# Bad-anchor sanitizer — phrases or shapes that should never appear
# as a continuation anchor in a deterministic Lori response. ChatGPT
# review 2026-05-09 caught Kent's meta-feedback turn producing
# "my experience and you want" as the anchor — pronoun-heavy, clumsy.
_BAD_ANCHOR_TOKENS = (
    "you want", "you said", "you mentioned", "you asked", "you keep",
    "how i felt", "how i feel", "how she felt", "how he felt",
    "my experience", "the sensory", "sensory parts",
    "my feelings", "your feelings",
    "what i said", "what you said",
)


def _sanitize_anchor(anchor: str) -> str:
    """Reject anchors that are pronoun-heavy, contain meta-feedback
    vocabulary, or are too long. Returns "" when the anchor is bad
    (caller falls back to no-anchor template, which still reads
    naturally — "Tell me what happened next." vs. "Tell me what
    happened next about my experience and you want.")."""
    if not anchor:
        return ""
    a = anchor.strip()
    if not a:
        return ""
    a_lower = a.lower()
    # Reject any anchor containing meta-feedback / pronoun-heavy
    # vocabulary
    for bad in _BAD_ANCHOR_TOKENS:
        if bad in a_lower:
            return ""
    # Reject too-long anchors unless they look like proper-noun
    # phrases (capitalized chain). Heuristic: 5+ tokens AND not all
    # tokens capitalized → reject.
    tokens = a.split()
    if len(tokens) > 5:
        capitalized = sum(1 for t in tokens if t and t[0].isupper())
        if capitalized < len(tokens) - 1:
            return ""
    return a


# META-FEEDBACK topic capture — when narrator says "not asking about
# basic training rather the sensory parts", we want to pull "basic
# training" as the topic to follow, not the LAST proper noun in the
# turn. Same when narrator says "ask about X not Y" or "I want facts
# about Z".
_META_FEEDBACK_TOPIC_RX = (
    re.compile(
        r"not\s+asking\s+about\s+([a-zA-Z][a-zA-Z\s]{2,40}?)\s+rather",
        re.IGNORECASE,
    ),
    re.compile(
        r"ask(?:ing)?\s+about\s+([a-zA-Z][a-zA-Z\s]{2,40}?)\s+(?:not|rather)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:talk|tell)\s+(?:me\s+)?about\s+([a-zA-Z][a-zA-Z\s]{2,40}?)\s+(?:not|instead)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:want|tell)\s+(?:me\s+to\s+)?(?:tell|describe|share)\s+(?:my\s+)?(?:experience|story)\s+(?:about|in|of)\s+([a-zA-Z][a-zA-Z\s]{2,40}?)(?:\.|,|$)",
        re.IGNORECASE,
    ),
)


def _extract_meta_feedback_topic(text: str) -> str:
    """Pull the topic the narrator is asking Lori to focus ON (not
    the topic Lori is being told to skip). Used by composer for
    META_FEEDBACK responses to anchor the continuation invitation
    on what Kent ACTUALLY wants to talk about.

    For Kent's literal turn:
      "you are being vague and not asking about basic training rather
       the sensory parts of it"
    → topic = "basic training"
    """
    if not text:
        return ""
    cleaned = re.sub(r"\[SYSTEM:.*?\]", " ", text or "", flags=re.DOTALL)
    for rx in _META_FEEDBACK_TOPIC_RX:
        m = rx.search(cleaned)
        if m:
            topic = m.group(1).strip().rstrip(".,;:")
            sanitized = _sanitize_anchor(topic)
            if sanitized:
                return sanitized
    return ""


# BUG-LORI-WITNESS-ACTIVE-RECEIPT-01 (2026-05-10) — multi-event
# extractor for active-listening receipts. Pulls narrator-action
# clauses ("you went from Stanley to Fargo", "you scored expert on
# the M1") so the witness composer can produce a multi-fact sentence
# instead of a bare label list.
#
# Each event is a (verb_phrase, object_phrase) tuple. The composer
# joins 3-5 events into a single second-person sentence:
#   "You went from Stanley to Fargo, scored high on the induction
#   tests, and were put in charge of the meal tickets to the West
#   Coast. What happened on the train?"
#
# Detection is heuristic + tolerant. We extract verbs from a curated
# narrator-action list, pair each with a short following object/place
# phrase, and skip clauses that don't yield both a verb and a target.

# Narrator-action verbs (past tense, common in oral-history narrative)
_EVENT_VERBS = (
    "went", "got", "took", "drove", "drove", "rode", "flew", "sailed",
    "enlisted", "joined", "served", "trained", "moved", "transferred",
    "started", "finished", "arrived", "departed", "left", "returned",
    "deployed", "stationed", "assigned", "promoted", "graduated",
    "passed", "qualified", "received", "earned", "scored", "made",
    "selected", "picked", "chosen", "appointed",
    "became", "worked", "met", "married", "had", "raised",
    "taught", "studied", "learned", "practiced", "built", "wrote",
    "remembered", "told", "asked", "said", "decided", "chose",
    "saw", "knew", "ended", "came", "completed", "finished", "began",
    "shipped", "boarded", "landed", "rented", "bought", "sold",
    "spent", "lived", "stayed", "filed", "registered",
)
_EVENT_VERB_RX = re.compile(
    r"\bI\s+("
    + "|".join(re.escape(v) for v in _EVENT_VERBS)
    + r")\b",
    re.IGNORECASE,
)
# Also catch passive "they put me in charge of X" / "I was put in
# charge of X" / "got selected for X"
_PASSIVE_NARRATOR_RX = re.compile(
    r"\b(?:I\s+(?:was|got|had been)|they\s+(?:put|made|sent|chose|"
    r"selected|assigned|told|gave|let|let me))\s+"
    r"(\w+(?:\s+\w+){0,5})",
    re.IGNORECASE,
)


def _extract_event_phrases(text: str, max_n: int = 4) -> List[str]:
    """Extract narrator-action event phrases for active-receipt
    composition. Each phrase is short ('went to Fargo for induction',
    'scored expert on the M1', 'put in charge of meal tickets').

    Returns ordered list, deduped, truncated to max_n. Empty list if
    no clean events extractable.
    """
    if not text:
        return []
    cleaned = re.sub(r"\[SYSTEM:.*?\]", " ", text or "", flags=re.DOTALL)
    events: List[str] = []
    seen_lower: set = set()

    def _try_add(phrase: str) -> None:
        # Trim to 6-8 tokens for compactness
        toks = phrase.strip().split()
        if len(toks) > 8:
            toks = toks[:8]
        elif len(toks) < 2:
            return
        compact = " ".join(toks).rstrip(".,;:")
        # Reject if too generic / contains forbidden vocab
        compact_lower = compact.lower()
        for bad in ("you want", "how i felt", "the sensory"):
            if bad in compact_lower:
                return
        # Substring dedupe
        for existing in seen_lower:
            if compact_lower in existing or existing in compact_lower:
                return
        seen_lower.add(compact_lower)
        events.append(compact)

    # Pass 1: "I [verb] [next 4-7 tokens]"
    for m in _EVENT_VERB_RX.finditer(cleaned):
        verb = m.group(1).lower()
        # Take verb + next 5-7 tokens as the event phrase
        start = m.start()
        # Skip the "I " prefix; phrase begins at verb
        verb_start = m.start(1)
        # Pull 6 following tokens (or until punctuation)
        tail = cleaned[verb_start:verb_start + 80]
        # Stop at chronological connectors / punctuation
        tail_clipped = re.split(
            r"(?:\s+(?:and|then|after|but|so|when|while|because|until|"
            r"before|then|once|so)\s+|[\.\?!;])",
            tail, maxsplit=1
        )[0]
        _try_add(tail_clipped)
        if len(events) >= max_n:
            break

    return events[:max_n]


def _extract_top_anchors(text: str, max_n: int = 3) -> List[str]:
    """Pull the top-N most useful continuation anchors from a narrator
    turn, ordered by appearance position. Used by composer for STRUCTURED
    _NARRATIVE responses to reflect MULTIPLE concrete facts back ("Stanley
    to Fargo, the induction tests, and the meal-ticket assignment") so
    Lori demonstrates active listening, not just acknowledgment.

    BUG-LORI-WITNESS-MULTI-ANCHOR-01 (2026-05-10) — Kent's session
    showed that a single-anchor "Tell me more about West Coast" template
    feels dismissive after a 100-200 word narrative. Multi-anchor
    extraction lets the witness composer reflect substance without
    invoking the LLM.

    Selection logic:
      1. All proper-noun phrases in order of appearance (skip stopword
         starters, skip sentence-initial)
      2. Append definite-noun phrases ("the meal tickets", "the
         induction test") that aren't already covered by a proper noun
      3. Sanitize each via _sanitize_anchor
      4. Dedupe (case-insensitive substring containment)
      5. Return first max_n

    Empty input → empty list. No anchors found → empty list.
    """
    if not text or not text.strip():
        return []
    cleaned = re.sub(r"\[SYSTEM:.*?\]", " ", text or "", flags=re.DOTALL)

    found: List[str] = []
    seen_lower: set = set()

    def _try_add(candidate: str) -> None:
        s = _sanitize_anchor(candidate)
        if not s:
            return
        s_lower = s.lower()
        # Dedupe — skip if a previous anchor already contains this one
        # (or vice versa). "Fargo" subsumed by "Stanley to Fargo" etc.
        for existing in seen_lower:
            if s_lower in existing or existing in s_lower:
                return
        seen_lower.add(s_lower)
        found.append(s)

    # Pass 1: proper-noun phrases in narrative order
    for m in _PROPER_NOUN_RX.finditer(cleaned):
        token = m.group(1).strip()
        first_word = token.split()[0]
        if first_word in _NOT_AN_ANCHOR:
            continue
        start = m.start()
        if start == 0:
            continue
        prefix = cleaned[max(0, start - 2):start]
        if prefix in (". ", "! ", "? ", "\n\n"):
            continue
        _try_add(token)
        if len(found) >= max_n * 2:  # cap exploration; we'll trim below
            break

    # Pass 2: definite-noun phrases in narrative order
    if len(found) < max_n:
        for m in _DEFINITE_NOUN_RX.finditer(cleaned):
            phrase = m.group(0).strip()
            _try_add(phrase)
            if len(found) >= max_n * 2:
                break

    return found[:max_n]


def _extract_factual_anchor(text: str) -> str:
    """Pull the most useful continuation-anchor from the narrator's
    turn. Heuristic priority:
      1. Last capitalized proper noun that isn't a stopword
         (Stanley / Fargo / Germany / West Coast / Army)
      2. Last "the X" / "my X" definite phrase ("the meal tickets",
         "the admissions test", "my first deployment")
      3. Empty string → caller falls back to "what came next"

    Returns the raw anchor string for use in templates like
    "Tell me more about {anchor}." or "What happened after {anchor}?".
    """
    if not text or not text.strip():
        return ""

    # Strip "[SYSTEM: ...]" directive blocks if any
    cleaned = re.sub(r"\[SYSTEM:.*?\]", " ", text or "", flags=re.DOTALL)

    # Pull all proper-noun matches; iterate in reverse to find the
    # last one that isn't a stopword. Reject sentence-initial capitals
    # by checking the character preceding the match.
    proper_matches: List[Tuple[int, str]] = []
    for m in _PROPER_NOUN_RX.finditer(cleaned):
        token = m.group(1).strip()
        # Skip if first word is a stopword
        first_word = token.split()[0]
        if first_word in _NOT_AN_ANCHOR:
            continue
        # Skip sentence-initial position (word follows ". " / "! " /
        # "? " or appears at offset 0 in the cleaned text)
        start = m.start()
        if start == 0:
            continue
        prefix = cleaned[max(0, start - 2):start]
        if prefix in (". ", "! ", "? ", "\n\n"):
            continue
        proper_matches.append((start, token))

    if proper_matches:
        # Last proper-noun anchor wins
        return proper_matches[-1][1]

    # Fallback: last "the X" definite phrase
    definite_matches = list(_DEFINITE_NOUN_RX.finditer(cleaned))
    if definite_matches:
        last = definite_matches[-1]
        # Return the FULL phrase including determiner: "the meal tickets"
        return last.group(0).strip()

    return ""


# ── Detection ─────────────────────────────────────────────────────────────


def _matches_any(patterns, text: str) -> bool:
    return any(p.search(text) for p in patterns)


def _count_pattern_hits(patterns, text: str) -> int:
    """Count distinct chronological connectors / action verbs."""
    count = 0
    for p_str in patterns:
        try:
            if re.search(p_str, text, re.IGNORECASE):
                count += 1
        except re.error:
            continue
    return count


def detect_witness_event(text: Optional[str]) -> WitnessDetection:
    """Pure detector. Returns a populated WitnessDetection when the
    turn matches META_FEEDBACK or STRUCTURED_NARRATIVE; otherwise an
    empty detection.
    """
    if not text or not text.strip():
        return WitnessDetection()

    # Strip SYSTEM directives so they don't accidentally trigger
    # META_FEEDBACK on era-click prompt content.
    cleaned = re.sub(r"\[SYSTEM:.*?\]", " ", text or "", flags=re.DOTALL).strip()
    if not cleaned:
        return WitnessDetection()

    # ── TYPE A: META-FEEDBACK (priority over structured-narrative
    # because a meta-feedback turn may also contain narrative content
    # but the comprehending acknowledgment is what's needed) ──

    # For META-FEEDBACK, prefer the topic Kent is asking Lori to follow
    # (extracted from "not asking about X rather Y" → X) over a generic
    # last-proper-noun pull which gives garbage like "my experience and
    # you want" on Kent's literal turn. Falls back to the generic
    # extractor + sanitizer when no topic is captured.
    def _meta_anchor() -> str:
        topic = _extract_meta_feedback_topic(cleaned)
        if topic:
            return topic
        # Fallback to generic extraction with sanitizer
        return _sanitize_anchor(_extract_factual_anchor(cleaned))

    if _matches_any(_META_STOP_SENSORY_EN + _META_STOP_SENSORY_ES, cleaned):
        return WitnessDetection(
            detection_type="META_FEEDBACK",
            sub_type="stop_sensory",
            factual_anchor=_meta_anchor(),
        )
    if _matches_any(_META_ASK_ABOUT_X_NOT_Y_EN, cleaned):
        return WitnessDetection(
            detection_type="META_FEEDBACK",
            sub_type="ask_x_not_y",
            factual_anchor=_meta_anchor(),
        )
    if _matches_any(_META_WANT_FACTS_EN + _META_WANT_FACTS_ES, cleaned):
        return WitnessDetection(
            detection_type="META_FEEDBACK",
            sub_type="want_facts",
            factual_anchor=_meta_anchor(),
        )
    if _matches_any(_META_BEING_VAGUE_EN + _META_BEING_VAGUE_ES, cleaned):
        return WitnessDetection(
            detection_type="META_FEEDBACK",
            sub_type="being_vague",
            factual_anchor=_meta_anchor(),
        )

    # ── TYPE C: CORRECTION (BUG-LORI-CORRECTION-PERSPECTIVE-INVERSION-01)
    # Narrator is correcting a fact Lori got wrong. The composer emits
    # a strict second-person acknowledgment with the corrected value,
    # never first-person echoing. This fires AFTER meta-feedback
    # (meta-feedback handles "you are being vague" — broader behavior
    # critique) and BEFORE structured-narrative.
    if _matches_any(_META_CORRECTION_EN + _META_CORRECTION_ES, cleaned):
        corrected = _extract_correction_value(cleaned)
        return WitnessDetection(
            detection_type="META_FEEDBACK",
            sub_type="correction",
            # Use corrected value as the factual anchor when we got one;
            # otherwise fall back to a generic anchor extraction.
            factual_anchor=corrected or _sanitize_anchor(_extract_factual_anchor(cleaned)),
        )

    # ── TYPE B: STRUCTURED NARRATIVE ──
    # Pull multi-anchor list for richer composer response. Falls back
    # to single anchor (last meaningful proper noun) when narrator's
    # turn doesn't yield 2+ distinct anchors.
    structured_anchors = _extract_top_anchors(cleaned, max_n=3)

    word_count = len(cleaned.split())
    # 25-word floor. Below that we treat as a fragment/sentence — even
    # if it has chronological shape, the response should be a normal
    # turn not a witness-mode invitation. Kent's line 38 is ~80 words;
    # a tight chronological "I enlisted... Then I went..." can be ~25.
    if word_count < 25:
        return WitnessDetection()

    chrono_count = _count_pattern_hits(
        _CHRONOLOGICAL_CONNECTORS_EN + _CHRONOLOGICAL_CONNECTORS_ES,
        cleaned,
    )
    action_count = _count_pattern_hits(_ACTION_VERBS_EN, cleaned)

    # Trigger thresholds (recalibrated 2026-05-09 after ChatGPT
    # review caught the action-verb tuple-of-one bug). Each
    # _ACTION_VERBS_EN entry is now its own pattern category; the
    # count represents distinct narrative-shape categories present.
    # Kent's line 38 hits: ~6 action-verb categories + 2 chrono.
    #
    # Trigger when ANY of:
    #   - 2+ chronological connectors AND 1+ action category
    #   - 3+ action-verb categories alone (multiple narrative
    #     shapes signal real factual recounting)
    #   - Long turn (≥60 words) with 1+ chrono AND 1+ action
    #   - Total signals (chrono + action) ≥ 4
    total_signals = chrono_count + action_count
    is_structured = (
        (chrono_count >= 2 and action_count >= 1)
        or action_count >= 3
        or (word_count >= 60 and chrono_count >= 1 and action_count >= 1)
        or total_signals >= 4
    )
    if is_structured:
        # Multi-anchor extraction was pre-computed above; pull top
        # anchor for backward compat single-anchor template fallback.
        primary = structured_anchors[0] if structured_anchors else _sanitize_anchor(_extract_factual_anchor(cleaned))
        # Event-phrase extraction for active-receipt composer
        event_phrases = _extract_event_phrases(cleaned, max_n=4)
        return WitnessDetection(
            detection_type="STRUCTURED_NARRATIVE",
            sub_type="structured",
            factual_anchor=primary,
            multi_anchors=tuple(structured_anchors),
            event_phrases=tuple(event_phrases),
            word_count=word_count,
            chronological_connector_count=chrono_count,
            action_verb_count=action_count,
        )

    return WitnessDetection()


# ── Locale pack ───────────────────────────────────────────────────────────
#
# The composer locks witness-mode response shape: brief, comprehending
# (for meta-feedback) or thread-staying (for structured narrative).
# Cap at ~30 words. NO sensory probe. NO feeling probe. NO topic shift.

_RESPONSES_EN = {
    # META-FEEDBACK responses — comprehending acknowledgment + redirect
    # to a continuation invitation that follows the narrator's thread.
    "stop_sensory": (
        "Got it — I'll skip the sensory questions. "
        "Tell me what happened next{anchor_clause}."
    ),
    "ask_x_not_y": (
        "Got it — I'll stop the sensory questions and follow the facts. "
        "Tell me more{anchor_clause}."
    ),
    "want_facts": (
        "Understood — go ahead and tell me the experience the way you "
        "want to. I'll listen{anchor_clause}."
    ),
    "being_vague": (
        "You're right — I missed what you said. "
        "Please tell me again{anchor_clause}."
    ),
    # BUG-LORI-CORRECTION-PERSPECTIVE-INVERSION-01 (2026-05-10):
    # Strict second-person acknowledgment. NEVER uses "we" / "our" /
    # "I" perspective markers — that's the failure mode this template
    # is built to prevent. Format: "Got it — {corrected value}. What
    # happened next?" When anchor_clause is empty (no value extracted),
    # the template still reads naturally.
    "correction": (
        "Got it{anchor_clause}. What happened next?"
    ),
    # BUG-LORI-WITNESS-PROPER-NOUN-CONFIRM-01 (2026-05-10): when the
    # narrator corrects a proper noun (Kent's K10: "Landstuhl Air
    # Force Hospital Ramstein Air Force Base"), Lori should verify
    # accuracy like a careful oral historian — ask spelling
    # confirmation. Used when the corrected value contains 2+ tokens
    # (likely a multi-word place/institution name where exact spelling
    # matters for archive accuracy).
    "correction_spelling": (
        "Got it{anchor_clause}. Did I get that name right? "
        "What happened next?"
    ),
    # STRUCTURED-NARRATIVE response — continuation invitation only.
    # Cap at ~12-15 words. Stay on the thread.
    "structured": (
        "Tell me more{anchor_clause}. What happened next?"
    ),
    # BUG-LORI-WITNESS-MULTI-ANCHOR-01 (2026-05-10) — multi-anchor
    # template for STRUCTURED_NARRATIVE turns where Lori can reflect
    # MULTIPLE concrete facts the narrator just said. Demonstrates
    # active listening without invoking the LLM. Used when the
    # detector pulled 2+ anchors from the turn.
    #
    # Shape: "{Anchor list}. What happened next?"
    # Example: "Stanley to Fargo, the induction tests, and the meal-
    #          ticket assignment. What happened next?"
    "structured_multi": (
        "I caught {anchor_list}. What happened next?"
    ),
    # BUG-LORI-WITNESS-ACTIVE-RECEIPT-01 (2026-05-10) — active receipt
    # template using narrator-action event phrases. Used when the
    # detector pulled 2+ event clauses from the turn ("went from
    # Stanley to Fargo for induction", "scored expert on the M1",
    # "got put in charge of meal tickets"). Demonstrates Lori
    # followed the SEQUENCE, not just grabbed words.
    #
    # Shape: "You {event1}, {event2}, and {event3}. What happened next?"
    # Example: "You went from Stanley to Fargo for induction, scored
    #          expert on the M1, and got put in charge of meal tickets.
    #          What happened on the train?"
    "structured_receipt": (
        "You {event_list}. What happened next?"
    ),
}

_RESPONSES_ES = {
    "stop_sensory": (
        "Entendido — voy a dejar las preguntas sobre sensaciones. "
        "Cuéntame qué pasó después{anchor_clause}."
    ),
    "ask_x_not_y": (
        "Entendido — voy a parar las preguntas sensoriales y seguir los "
        "hechos. Cuéntame más{anchor_clause}."
    ),
    "want_facts": (
        "Entiendo — sigue contándome la experiencia como quieras "
        "contarla. Te escucho{anchor_clause}."
    ),
    "being_vague": (
        "Tienes razón — me perdí lo que dijiste. "
        "Por favor, cuéntame otra vez{anchor_clause}."
    ),
    "correction": (
        "Entendido{anchor_clause}. ¿Qué pasó después?"
    ),
    "correction_spelling": (
        "Entendido{anchor_clause}. ¿Capté bien el nombre? "
        "¿Qué pasó después?"
    ),
    "structured": (
        "Cuéntame más{anchor_clause}. ¿Qué pasó después?"
    ),
    "structured_multi": (
        "Capté {anchor_list}. ¿Qué pasó después?"
    ),
    "structured_receipt": (
        "Tú {event_list}. ¿Qué pasó después?"
    ),
}


def _resolve_locale(target_language: Optional[str]) -> str:
    if target_language and target_language.lower().startswith("es"):
        return "es"
    return "en"


def _format_anchor_clause(anchor: str, lang: str, sub_type: str = "") -> str:
    """Build the continuation clause from the anchor. Shape depends on
    sub_type:
      - "correction" / "correction_spelling": " — {anchor}" (em dash
        + value, second-person)
      - default: " about {anchor}" (continuation invitation)
    Empty anchor → empty clause (template still reads naturally)."""
    if not anchor:
        return ""
    if sub_type in ("correction", "correction_spelling"):
        return f" — {anchor}"
    if lang == "es":
        return f" sobre {anchor}"
    return f" about {anchor}"


def _events_quality_pass(events: List[str]) -> bool:
    """Quality gate for event-receipt composition. Returns True only
    when the extracted event phrases produce a clean response. Falls
    through to multi-anchor when the narrator's text was disfluent
    (Kent's K4/K5 verbatim had self-repeating phrases like "I had
    made I scored expert on the M1 rifle M1 rifle" that produced
    overlapping event extractions).

    Rejects if:
      - Total event tokens > 24 (response would exceed ~30 words)
      - Any pair of events overlaps >50% in token set
      - Any single event has >8 tokens (too long, likely noisy clip)
    """
    if not events:
        return False
    total_tokens = sum(len(e.split()) for e in events)
    if total_tokens > 24:
        return False
    for e in events:
        if len(e.split()) > 8:
            return False
    # Pairwise overlap check
    for i in range(len(events)):
        e1_tokens = set(events[i].lower().split())
        for j in range(i + 1, len(events)):
            e2_tokens = set(events[j].lower().split())
            if not e1_tokens or not e2_tokens:
                continue
            overlap = len(e1_tokens & e2_tokens)
            min_size = min(len(e1_tokens), len(e2_tokens))
            if min_size > 0 and overlap / min_size > 0.5:
                return False
    return True


def _format_multi_anchor_list(anchors: List[str], lang: str) -> str:
    """Build a comma-separated list of anchors with proper conjunction.
    "A, B, and C" or "A and B" or "A". Empty list returns "".

    Used by structured-narrative composer to demonstrate active
    listening — "Stanley to Fargo, the induction tests, and the
    meal-ticket assignment" instead of single-anchor "West Coast"."""
    if not anchors:
        return ""
    if len(anchors) == 1:
        return anchors[0]
    if len(anchors) == 2:
        joiner = " and " if lang == "en" else " y "
        return f"{anchors[0]}{joiner}{anchors[1]}"
    # 3+ anchors — Oxford-style "A, B, and C"
    body = ", ".join(anchors[:-1])
    final_joiner = ", and " if lang == "en" else ", y "
    return f"{body}{final_joiner}{anchors[-1]}"


def compose_witness_response(
    detection: WitnessDetection,
    target_language: str = "en",
) -> str:
    """Build the deterministic narrator-facing answer string."""
    if not detection.is_witness_event:
        return ""

    lang = _resolve_locale(target_language)
    pack = _RESPONSES_ES if lang == "es" else _RESPONSES_EN

    # BUG-LORI-WITNESS-ACTIVE-RECEIPT-01 (2026-05-10) — for STRUCTURED
    # _NARRATIVE turns, prefer multi-FACT receipt over multi-anchor
    # label list. Receipt demonstrates Lori followed the SEQUENCE of
    # narrator events (active listening), not just grabbed words.
    #
    # Composer ladder (most-engaged → least):
    #   1. event_phrases ≥ 2 → "structured_receipt" template
    #      "You went from Stanley to Fargo for induction, scored
    #       expert on the M1, and got put in charge of meal tickets.
    #       What happened next?"
    #   2. multi_anchors ≥ 2 → "structured_multi" template (label list
    #      with active intro: "I caught Stanley, Fargo, and the meal
    #      tickets. What happened next?")
    #   3. Single anchor → "structured" template (legacy fallback)
    if detection.detection_type == "STRUCTURED_NARRATIVE":
        events = list(detection.event_phrases or ())
        anchors = list(detection.multi_anchors or ())
        if len(events) >= 2 and _events_quality_pass(events):
            event_list = _format_multi_anchor_list(events, lang)
            receipt_template = pack.get("structured_receipt") or pack.get("structured", "")
            return receipt_template.format(event_list=event_list)
        if len(anchors) >= 2:
            multi_list = _format_multi_anchor_list(anchors, lang)
            multi_template = pack.get("structured_multi") or pack.get("structured", "")
            return multi_template.format(anchor_list=multi_list)
        # 0 or 1 anchor → fall through to single-anchor template

    # BUG-LORI-WITNESS-PROPER-NOUN-CONFIRM-01 — for correction turns
    # where the corrected value LOOKS LIKE a proper-noun multi-word
    # name (place / institution / person), use the spelling-confirm
    # template. Trigger requires:
    #   - 2+ tokens AND
    #   - 50%+ of tokens start with uppercase letters
    #
    # This prevents false-fire on "the year was" (which would be
    # extracted as a 2-token phrase but isn't a proper noun).
    sub_type = detection.sub_type
    if sub_type == "correction" and detection.factual_anchor:
        anchor_tokens = detection.factual_anchor.split()
        if len(anchor_tokens) >= 2:
            cap_count = sum(1 for t in anchor_tokens if t and t[0].isupper())
            if cap_count >= max(1, len(anchor_tokens) // 2):
                sub_type = "correction_spelling"

    template = pack.get(sub_type) or pack.get("structured", "")
    anchor_clause = _format_anchor_clause(
        detection.factual_anchor, lang, sub_type,
    )
    return template.format(anchor_clause=anchor_clause)


def detect_and_compose(
    text: Optional[str],
    target_language: str = "en",
) -> Optional[WitnessAnswer]:
    """Convenience wrapper. Returns None when not a witness event;
    returns a populated WitnessAnswer when matched."""
    detection = detect_witness_event(text)
    if not detection.is_witness_event:
        return None
    response_text = compose_witness_response(detection, target_language)
    if not response_text:
        return None
    return WitnessAnswer(
        text=response_text,
        language=_resolve_locale(target_language),
        detection_type=detection.detection_type,
        sub_type=detection.sub_type,
        factual_anchor=detection.factual_anchor,
    )


# ── BUG-LORI-WITNESS-LLM-RECEIPT-01 (2026-05-10) ─────────────────────────
#
# LLM-witness-receipt validator. Used by chat_ws.py AFTER the LLM
# composes a STRUCTURED_NARRATIVE response under the WITNESS RECEIPT
# directive injected by prompt_composer. If validation fails, chat_ws
# falls back to the deterministic compose_witness_response path.
#
# Failure modes the validator catches:
#   - Forbidden tokens (sights/sounds/smells/scenery/camaraderie/
#     "how did that feel"/etc.)
#   - First-person mimicry ("we were in Germany", "our son", "my wife")
#   - Length out of bounds (35-110 words for clean witness receipt)
#   - Multiple questions (witness mode = ONE question)
#   - Insufficient fact reflection (<3 narrator-named anchors echoed)
#
# All four checks must pass for the LLM output to be accepted. Any
# failure routes to the deterministic fallback so Kent never sees a
# sensory probe even when the LLM drifts under directive pressure.

# Forbidden tokens — case-insensitive substring match. These are the
# exact failure terms from Kent's earlier sessions plus the broader
# active-listening forbidden list (ChatGPT 2026-05-10 review).
_VALIDATOR_FORBIDDEN_TOKENS = (
    "scenery", "sights", "sounds", "smells", "sensory",
    "how did that feel", "how did you feel",
    "what did that feel like", "what was that like emotionally",
    "must have been", "must have felt",
    "camaraderie", "teamwork", "culture among",
    "sense of duty", "pivotal", "resilience",
)

# First-person mimicry — narrator's voice leaking into Lori's response.
# Kent's K10/K11 failure: Lori echoed "we were in Germany"/"our son".
_VALIDATOR_FIRST_PERSON = (
    "our son", "my son", "my wife", "our wife",
    "we were in germany", "we were in kaiserslautern",
    "we took care", "we got married", "we had to",
    "we were on", "we went through", "we had the",
    "i was assigned to germany", "i went to germany",
    "i contacted janice", "i contacted my fiancée",
    "while we were", "our oldest son",
    # Generic "we [past-action]" first-person plural narration —
    # Lori speaking AS Kent. Trim list to action verbs that are
    # almost always narrator-voice when used after "we".
    "we drilled", "we qualified", "we drove", "we sailed",
    "we landed", "we married", "we moved",
)


# Proper-noun extractor for fact-counting. Pulls capitalized words
# (names, places, military units) from narrator text. Used by
# validator to count how many narrator-named anchors Lori echoed.
_FACT_PROPER_NOUN_RX = re.compile(
    r"\b([A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]+){0,3})\b"
)
# Stopword list — capitalized words that aren't real anchors
_FACT_STOPWORDS = frozenset({
    "I", "Im", "Ive", "We", "The", "A", "An", "And", "Or", "But",
    "When", "Where", "Why", "How", "What", "Who", "Yes", "No",
    "Maybe", "Sure", "Okay", "OK", "Then", "Now", "Today",
    "Tomorrow", "Yesterday", "First", "Second", "Last", "Next",
    "Tell", "Let", "Give", "Take", "Make", "USA", "US", "AI",
    "Army", "Navy",  # too generic when standalone — only credit
                      # when combined ("Army Security Agency")
})


def _count_narrator_facts_echoed(narrator_text: str, lori_text: str) -> int:
    """Count distinct narrator-named anchors echoed in Lori's response.

    Strategy:
      1. Extract all capitalized proper-noun phrases from narrator text
         (skipping stopword starters and sentence-initial position)
      2. Plus key definite phrases ("the meal tickets", "the
         induction test")
      3. Count how many of those (case-insensitive substring match)
         appear in Lori's response

    This is the receipt-quality measure: did Lori reflect what the
    narrator actually said?
    """
    if not narrator_text or not lori_text:
        return 0

    # Strip SYSTEM directives
    cleaned = re.sub(r"\[SYSTEM:.*?\]", " ", narrator_text, flags=re.DOTALL)
    lori_lower = lori_text.lower()

    found_facts: set = set()

    # Pass 1: proper-noun phrases (skip sentence-start + stopwords)
    for m in _FACT_PROPER_NOUN_RX.finditer(cleaned):
        token = m.group(1).strip()
        first_word = token.split()[0]
        if first_word in _FACT_STOPWORDS:
            continue
        start = m.start()
        if start == 0:
            continue
        prefix = cleaned[max(0, start - 2):start]
        if prefix in (". ", "! ", "? ", "\n\n"):
            continue
        # Single significant token at minimum
        if token.lower() in lori_lower:
            found_facts.add(token.lower())

    # Pass 2: definite-noun phrases ("the meal tickets")
    for m in _DEFINITE_NOUN_RX.finditer(cleaned):
        phrase = m.group(0).strip().lower()
        # Strip "the" prefix for matching — Lori may rephrase
        bare = re.sub(r"^(?:the|my|our|that|these|those)\s+", "", phrase)
        if bare and bare in lori_lower:
            found_facts.add(bare)

    return len(found_facts)


def validate_witness_receipt(
    lori_text: str,
    narrator_text: str = "",
    *,
    min_words: int = 35,
    max_words: int = 110,
    max_questions: int = 1,
    min_facts: int = 3,
) -> tuple:
    """Validate an LLM-composed witness receipt response.

    Returns (is_valid: bool, failures: List[str]).

    On any failure, chat_ws.py routes the turn to the deterministic
    fallback (compose_witness_response on the existing detection).

    Failure labels:
      - "forbidden_token:<token>"
      - "first_person_mimicry:<phrase>"
      - "too_short:<n>"
      - "too_long:<n>"
      - "too_many_questions:<n>"
      - "too_few_facts:<n>/<min>"
    """
    failures: List[str] = []
    if not lori_text or not lori_text.strip():
        failures.append("empty_response")
        return False, failures

    text = lori_text
    text_lower = text.lower()

    for tok in _VALIDATOR_FORBIDDEN_TOKENS:
        if tok in text_lower:
            failures.append(f"forbidden_token:{tok}")
            break

    for phrase in _VALIDATOR_FIRST_PERSON:
        if phrase in text_lower:
            failures.append(f"first_person_mimicry:{phrase}")
            break

    word_count = len(text.split())
    if word_count < min_words:
        failures.append(f"too_short:{word_count}")
    elif word_count > max_words:
        failures.append(f"too_long:{word_count}")

    q_count = text.count("?")
    if q_count > max_questions:
        failures.append(f"too_many_questions:{q_count}")

    if narrator_text and min_facts > 0:
        facts = _count_narrator_facts_echoed(narrator_text, text)
        if facts < min_facts:
            failures.append(f"too_few_facts:{facts}/{min_facts}")

    return (len(failures) == 0), failures


__all__ = [
    "WitnessDetection",
    "WitnessAnswer",
    "detect_witness_event",
    "compose_witness_response",
    "detect_and_compose",
    "validate_witness_receipt",
]
