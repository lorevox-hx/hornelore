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
    re.compile(r"\blet\s+me\s+(?:tell|finish|describe|explain)\b", re.IGNORECASE),
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
    sub_type: str = ""  # "stop_sensory" | "want_facts" | "being_vague" | "ask_x_not_y" | "structured" | ""
    factual_anchor: str = ""  # last factual anchor pulled from text
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

    # ── TYPE B: STRUCTURED NARRATIVE ──
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
        return WitnessDetection(
            detection_type="STRUCTURED_NARRATIVE",
            sub_type="structured",
            factual_anchor=_sanitize_anchor(_extract_factual_anchor(cleaned)),
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
    # STRUCTURED-NARRATIVE response — continuation invitation only.
    # Cap at ~12-15 words. Stay on the thread.
    "structured": (
        "Tell me more{anchor_clause}. What happened next?"
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
    "structured": (
        "Cuéntame más{anchor_clause}. ¿Qué pasó después?"
    ),
}


def _resolve_locale(target_language: Optional[str]) -> str:
    if target_language and target_language.lower().startswith("es"):
        return "es"
    return "en"


def _format_anchor_clause(anchor: str, lang: str) -> str:
    """Build the " about X" continuation clause from the anchor.
    Empty anchor → empty clause (template still reads naturally)."""
    if not anchor:
        return ""
    if lang == "es":
        return f" sobre {anchor}"
    return f" about {anchor}"


def compose_witness_response(
    detection: WitnessDetection,
    target_language: str = "en",
) -> str:
    """Build the deterministic narrator-facing answer string."""
    if not detection.is_witness_event:
        return ""

    lang = _resolve_locale(target_language)
    pack = _RESPONSES_ES if lang == "es" else _RESPONSES_EN
    template = pack.get(detection.sub_type) or pack.get("structured", "")
    anchor_clause = _format_anchor_clause(detection.factual_anchor, lang)
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


__all__ = [
    "WitnessDetection",
    "WitnessAnswer",
    "detect_witness_event",
    "compose_witness_response",
    "detect_and_compose",
]
