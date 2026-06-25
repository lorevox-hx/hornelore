"""Factual-chain capture — deterministic classifier.

WO-LORI-FACTUAL-CHAIN-CAPTURE-01 Phase 1.

When a narrator gives a chain of factual anchors (places, dates, events,
travel legs, institutions, outcomes), Lori must reflect the chain and
ask the next factual-link question rather than pivoting to sensory or
emotional probes. This module is the deterministic detection layer that
the composer / chat path consumes.

Pure stdlib. No LLM. No DB. No IO. Idempotent. Thread-safe.

LAW 3 isolation: this service must NOT import from any of:
    server.code.api.routers.*
    server.code.api.prompt_composer
    server.code.api.memory_echo
    server.code.api.routers.extract
    server.code.api.routers.chat_ws
    server.code.api.db
    server.code.api.services.story_preservation
    server.code.api.services.story_trigger

Allowed: sibling pure-function service modules (lori_structured_narrative_fallback).

Public API:
    detect_factual_chain(text) -> dict
    classify_factual_chain_cues(text) -> list[str]
    detect_meta_feedback_against_probe(text, last_assistant_text) -> dict
    build_factual_chain_followup_context(text, prior_turns) -> dict
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence


# ──────────────────────────────────────────────────────────────────────────
# Cue label vocabulary (locked per WO spec §Phase 1)
# ──────────────────────────────────────────────────────────────────────────

CUE_LABELS = (
    "multi_place_sequence",
    "date_place_action",
    "event_outcome_sequence",
    "institution_process_result",
    "travel_leg_sequence",
    "disruption_sequence",
    "job_school_military_sequence",
    "medical_sequence",
    "family_migration_sequence",
    "operator_trip_sequence",
)

PROBE_TYPE_SENSORY = "sensory"
PROBE_TYPE_ATMOSPHERE = "atmosphere"
PROBE_TYPE_CAMARADERIE = "camaraderie"

DEFAULT_BLOCKED_PROBE_TYPES = (
    PROBE_TYPE_SENSORY,
    PROBE_TYPE_ATMOSPHERE,
    PROBE_TYPE_CAMARADERIE,
)


# ──────────────────────────────────────────────────────────────────────────
# Regex patterns
# ──────────────────────────────────────────────────────────────────────────

# Proper-noun place (1-3 capitalized words). Mirrors the pattern in
# lori_structured_narrative_fallback._PROPER_NOUN_RX but kept local so
# this module remains independently auditable.
_PROPER_NOUN_RX = re.compile(
    r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2})\b"
)

# "from X to Y" — strong travel-leg signal, captures both endpoints.
_FROM_TO_RX = re.compile(
    r"\bfrom\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2})\s+to\s+"
    r"([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2})\b"
)

# Sequence connectors that link sentences/clauses into a chain.
_SEQUENCE_CONNECTOR_RX = re.compile(
    r"\b(?:then|and\s+then|after\s+that|afterwards?|next|"
    r"later|eventually|finally|first|second|third)\b",
    re.IGNORECASE,
)

# Travel verbs (broad set).
_TRAVEL_VERB_RX = re.compile(
    r"\b(?:went|flew|drove|took|sailed|traveled|walked|rode|"
    r"moved|came|returned|departed|arrived|left|crossed|"
    r"continued|headed|stayed|landed|boarded|disembarked|"
    r"shipped|transferred|connected|"
    r"(?:had|have|has)\s+to\s+(?:get|go|fly|drive|take)|"
    r"(?:got|get|going|gone|gotten|made\s+it)\s+(?:through|to|into)|"
    r"passed\s+through|cleared\s+(?:customs|immigration))\b",
    re.IGNORECASE,
)

# Disruption / travel-trouble markers.
_DISRUPTION_RX = re.compile(
    r"\b(?:delayed|cancelled|canceled|missed|rebooked|stuck|"
    r"stranded|tight\s+connection|disrupted|grounded|diverted|"
    r"rerouted|broke\s+down|breakdown)\b",
    re.IGNORECASE,
)

# Institution / process markers (military induction, school admissions,
# medical procedures, work onboarding).
_INSTITUTION_PROCESS_RX = re.compile(
    r"\b(?:enlisted|inducted|graduated|enrolled|admitted|"
    r"applied|interviewed|hired|fired|promoted|transferred|"
    r"passed\s+(?:the\s+)?(?:exam|test|admissions?|entrance|interview)|"
    r"took\s+(?:the\s+)?(?:exam|test|admissions?|entrance)|"
    r"physical\s+exam|mental\s+exam|admissions\s+test|"
    r"draft(?:ed)?|commissioned|discharged|diagnosed|"
    r"prescribed|operated\s+on|operation|surgery)\b",
    re.IGNORECASE,
)

# Outcome markers — paired with institution_process raises the
# institution_process_result signal.
_OUTCOME_RX = re.compile(
    r"\b(?:top\s+score|highest\s+score|honor\s+roll|honors?|"
    r"passed|failed|qualified|accepted|rejected|"
    r"got\s+(?:the\s+)?(?:job|offer|grade|score|position)|"
    r"won|lost|placed\s+first|placed\s+\w+\s+in)\b",
    re.IGNORECASE,
)

# Date / year markers (YYYY or month-name or "in 19XX/20XX").
_DATE_RX = re.compile(
    r"\b(?:"
    r"(?:19|20)\d{2}"  # 4-digit year
    r"|"
    r"(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)(?:\s+(?:19|20)\d{2})?"
    r"|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+(?:19|20)\d{2}"
    r")\b",
)

# Job / school / military lexicon.
_JOB_SCHOOL_MILITARY_RX = re.compile(
    r"\b(?:"
    r"army|navy|marines|air\s+force|coast\s+guard|"
    r"basic\s+training|boot\s+camp|deployment|deployed|"
    r"high\s+school|college|university|graduate\s+school|"
    r"first\s+job|new\s+job|career|company|firm|"
    r"served\s+(?:in|under|with)|tour\s+of\s+duty|"
    r"freshman|sophomore|junior|senior\s+year|"
    r"valedictorian|class\s+of\s+\d{2,4}|"
    r"started\s+(?:at|working)|worked\s+(?:at|for)"
    r")\b",
    re.IGNORECASE,
)

# Medical lexicon.
_MEDICAL_RX = re.compile(
    r"\b(?:"
    r"hospital|clinic|doctor|surgeon|surgery|operation|"
    r"diagnosis|diagnosed|biopsy|treatment|chemo|chemotherapy|"
    r"radiation|prescribed|medication|recovery|recovered|"
    r"emergency\s+room|er|icu|admitted\s+to|discharged\s+from"
    r")\b",
    re.IGNORECASE,
)

# Family migration lexicon.
_FAMILY_MIGRATION_RX = re.compile(
    r"\b(?:"
    r"emigrated|immigrated|migrated|came\s+over|came\s+to\s+america|"
    r"settled\s+in|moved\s+the\s+family|brought\s+(?:the\s+)?family|"
    r"ellis\s+island|passage|crossing|steerage|"
    r"left\s+the\s+old\s+country|first\s+generation|second\s+generation"
    r")\b",
    re.IGNORECASE,
)

# Sensory / emotional / atmosphere vocabulary — the class of probe that
# should NOT be Lori's next-question target while a factual chain is
# unresolved.
#
# Per WO §Phase 2 composer directive: "do not pivot to scenery, sounds,
# smells, atmosphere, or GENERALIZED FEELING." The "generalized feeling"
# leg of that directive was missing from the original regex — Lori's
# 2026-06-24 harness T6 turn ("Can you tell me about the emotions you
# felt?") slipped through F4 even though it's exactly the meta-feedback
# rejection class. Adding emotion / feeling / felt to the vocabulary
# closes that gap and also makes detect_meta_feedback_against_probe
# more sensitive when narrator pushes back against an emotion probe
# (e.g. "no, not the emotions — I want to tell you about the test").
_SENSORY_PROBE_RX = re.compile(
    r"\b(?:"
    r"scenery|sights|sounds|smells?|smelled|"
    r"atmosphere|ambien[cs]e|"
    r"camaraderie|"
    # Generalized-feeling / emotion vocabulary (WO Phase 2 directive)
    r"emotion|emotions|feeling|feelings|felt|"
    r"what\s+(?:did|do)\s+(?:it|that|they)\s+(?:feel|smell|sound|look)\s+like|"
    r"sense\s+of\s+(?:camaraderie|belonging|wonder)|"
    r"how\s+(?:did|do)\s+(?:it|that|they|you)\s+(?:feel|make\s+you\s+feel)"
    r")\b",
    re.IGNORECASE,
)

# Narrator meta-feedback against a sensory/emotional probe.
_META_AGAINST_SENSORY_RX = re.compile(
    r"\b(?:"
    r"not\s+(?:the\s+|asking\s+about\s+(?:the\s+)?)?(?:scenery|sights|sounds|smells?|atmosphere|feelings?|sensory|how\s+i\s+felt)"
    r"|"
    r"don'?t\s+ask\s+(?:about|me\s+about)\s+(?:scenery|feelings?|sensory|how)"
    r"|"
    r"stop\s+asking\s+(?:about|me\s+about)"
    r"|"
    r"i\s+(?:want|need)\s+to\s+(?:tell|talk\s+about)\s+(?:my|the)\s+(?:experience|facts|story|details)"
    r"|"
    r"(?:that'?s|that\s+is)\s+not\s+(?:what\s+i\s+mean(?:t)?|important)"
    r"|"
    r"i\s+(?:was|am)\s+talking\s+about\s+the"
    r"|"
    r"i\s+want\s+to\s+tell\s+my\s+experience"
    r"|"
    r"you\s+(?:are|keep)\s+asking\s+(?:about|the)\s+(?:sensory|feelings?|scenery)"
    r")\b",
    re.IGNORECASE,
)

# Proper-noun tokens that are NOT useful anchors (calendar / common
# noun residue / pronouns at sentence-start). Mirrors the filter in
# lori_structured_narrative_fallback but kept local.
_BAD_ANCHOR_TOKENS = frozenset({
    # Pronouns / sentence-start common-cap residue
    "i", "we", "they", "he", "she", "you", "it",
    "my", "our", "their", "his", "her", "your", "its",
    "this", "that", "these", "those", "the",
    # Calendar
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    # Generic
    "yes", "no", "ok", "okay", "well", "anyway", "still",
})


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────


def _empty_result() -> Dict[str, Any]:
    return {
        "is_factual_chain": False,
        "confidence": 0.0,
        "cue_labels": [],
        "anchors": [],
        "blocked_probe_types": [],
        "preferred_followup_type": "",
    }


def _dedupe_preserving_order(items: Sequence[str]) -> List[str]:
    seen: set = set()
    out: List[str] = []
    for item in items:
        if not item:
            continue
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out


def _filter_anchor(candidate: str) -> str:
    """Drop pronouns, calendar tokens, common-noun residue. Returns
    the cleaned candidate or "" if rejected."""
    if not candidate:
        return ""
    c = candidate.strip()
    if not c:
        return ""
    first_token = c.split()[0]
    if first_token.lower() in _BAD_ANCHOR_TOKENS:
        # Try stripping the leading filter token
        if " " in c:
            tail = c.split(" ", 1)[1].strip()
            if tail and tail[0].isupper():
                c = tail
            else:
                return ""
        else:
            return ""
    if c.lower() in _BAD_ANCHOR_TOKENS:
        return ""
    if len(c) < 3:
        return ""
    return c


def _extract_proper_noun_anchors(text: str, max_n: int = 12) -> List[str]:
    """Pull proper-noun phrases that pass the bad-token filter."""
    if not text:
        return []
    anchors: List[str] = []
    for m in _PROPER_NOUN_RX.finditer(text):
        candidate = _filter_anchor(m.group(1))
        if candidate:
            anchors.append(candidate)
        if len(anchors) >= max_n:
            break
    return _dedupe_preserving_order(anchors)


def _extract_event_phrase_anchors(text: str) -> List[str]:
    """Pull non-proper-noun event-phrase anchors (e.g. 'top score',
    'meal tickets', 'admissions test', 'tight connection', 'biopsy',
    'March 1965'). These aren't proper nouns but they're load-bearing
    in the factual chain — Kent's "top score" + "meal tickets" are the
    canonical travel/military examples; medical sequences add biopsy /
    surgery / diagnosis / dated months. Conservative: only fires for a
    small, locked vocabulary.
    """
    if not text:
        return []
    out: List[str] = []
    # Outcome phrases captured directly
    for m in _OUTCOME_RX.finditer(text):
        out.append(m.group(0).strip())
    # Common event-noun phrases (military / school / travel / medical)
    event_noun_rx = re.compile(
        r"\b(?:meal\s+tickets?|admissions?\s+test|entrance\s+exam|"
        r"physical\s+exam|mental\s+exam|tight\s+connection|"
        r"draft\s+number|first\s+job|basic\s+training|"
        r"boot\s+camp|tour\s+of\s+duty|class\s+of\s+\d{2,4}|"
        r"biopsy|surgery|operation|diagnosis|"
        r"chemotherapy|chemo|radiation|recovery|"
        r"emergency\s+room|er\s+visit|icu\s+stay)\b",
        re.IGNORECASE,
    )
    for m in event_noun_rx.finditer(text):
        out.append(m.group(0).strip())
    # Date-phrase anchors (year, month, month-year). These are
    # load-bearing chain anchors but get filtered out of the
    # proper-noun anchor pass by the calendar bad-token list.
    for m in _DATE_RX.finditer(text):
        out.append(m.group(0).strip())
    return _dedupe_preserving_order(out)


def _count_pattern(rx: re.Pattern, text: str) -> int:
    return len(rx.findall(text))


# ──────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────


def detect_factual_chain(text: str) -> Dict[str, Any]:
    """Detect whether the narrator turn is a factual chain.

    Returns a dict with the contract laid out in WO-LORI-FACTUAL-CHAIN-
    CAPTURE-01 Phase 1:

        is_factual_chain: bool
        confidence: float in [0.0, 1.0]
        cue_labels: List[str]      -- from CUE_LABELS vocabulary
        anchors: List[str]         -- proper nouns + event phrases
        blocked_probe_types: List[str]
        preferred_followup_type: str

    Pure-stdlib. Deterministic for a given input. Idempotent.
    """
    if not text or not text.strip():
        return _empty_result()

    cue_labels: List[str] = []
    anchors: List[str] = []
    score = 0.0

    # ── Travel-leg signals ───────────────────────────────────────
    from_to = _FROM_TO_RX.findall(text)
    if from_to:
        cue_labels.append("multi_place_sequence")
        cue_labels.append("travel_leg_sequence")
        for src, dst in from_to:
            s = _filter_anchor(src)
            d = _filter_anchor(dst)
            if s:
                anchors.append(s)
            if d:
                anchors.append(d)
        score += 0.45

    # Proper-noun anchors (places, names) — pulled regardless.
    proper_anchors = _extract_proper_noun_anchors(text, max_n=12)

    # Travel verbs + ≥2 proper-noun anchors → travel_leg_sequence
    travel_hits = _count_pattern(_TRAVEL_VERB_RX, text)
    if travel_hits >= 1 and len(proper_anchors) >= 2:
        if "travel_leg_sequence" not in cue_labels:
            cue_labels.append("travel_leg_sequence")
        score += 0.25

    # Multi-place sequence: ≥2 distinct proper nouns + ≥1 sequence connector
    sequence_hits = _count_pattern(_SEQUENCE_CONNECTOR_RX, text)
    if len(proper_anchors) >= 2 and sequence_hits >= 1:
        if "multi_place_sequence" not in cue_labels:
            cue_labels.append("multi_place_sequence")
        score += 0.20
        # Extra credit for a long sequence: ≥3 distinct places signals
        # a genuine route narration (Chris trip canary). Capped at +0.15.
        if len(proper_anchors) >= 3:
            score += 0.15

    # ── Institution / process / result ───────────────────────────
    has_institution_process = bool(_INSTITUTION_PROCESS_RX.search(text))
    has_outcome = bool(_OUTCOME_RX.search(text))
    proc_count = _count_pattern(_INSTITUTION_PROCESS_RX, text)
    if has_institution_process and has_outcome:
        cue_labels.append("institution_process_result")
        score += 0.30
    elif has_institution_process:
        cue_labels.append("institution_process_result")
        score += 0.15
        # Multi-step process (e.g. "admitted ... diagnosed ... surgery")
        # is itself chain evidence even without an outcome marker.
        if proc_count >= 2:
            score += 0.10

    # ── Date / place / action triplet ────────────────────────────
    has_date = bool(_DATE_RX.search(text))
    if has_date and len(proper_anchors) >= 1 and travel_hits >= 1:
        cue_labels.append("date_place_action")
        score += 0.20

    # ── Event / outcome sequence ─────────────────────────────────
    # ≥2 sequence connectors + outcome marker
    if sequence_hits >= 2 and has_outcome:
        cue_labels.append("event_outcome_sequence")
        score += 0.20

    # ── Disruption sequence ──────────────────────────────────────
    if _DISRUPTION_RX.search(text):
        cue_labels.append("disruption_sequence")
        score += 0.20
        # Paired-disruption bonus: a disruption with ≥2 distinct
        # proper-noun anchors is the Venice/Dulles class — Lori must
        # treat it as a chain, not a single-event memory.
        if len(proper_anchors) >= 2:
            score += 0.10

    # ── Job / school / military sequence ─────────────────────────
    if _JOB_SCHOOL_MILITARY_RX.search(text):
        cue_labels.append("job_school_military_sequence")
        score += 0.15

    # ── Medical sequence ─────────────────────────────────────────
    if _MEDICAL_RX.search(text):
        cue_labels.append("medical_sequence")
        score += 0.15
        # Multi-step medical chain (admitted + biopsy + diagnosed +
        # surgery class). Mayo Clinic canary depends on this bonus.
        med_count = _count_pattern(_MEDICAL_RX, text)
        if med_count >= 2:
            score += 0.15

    # ── Family migration sequence ────────────────────────────────
    if _FAMILY_MIGRATION_RX.search(text):
        cue_labels.append("family_migration_sequence")
        score += 0.15

    # Merge in event-phrase anchors (top score, meal tickets, etc.)
    event_anchors = _extract_event_phrase_anchors(text)
    merged_anchors = _dedupe_preserving_order(
        list(anchors) + list(proper_anchors) + list(event_anchors)
    )

    # Confidence cap
    confidence = min(1.0, score)

    # Decision: factual chain requires ≥0.50 score AND ≥2 distinct anchors
    is_factual_chain = (
        confidence >= 0.50
        and len(merged_anchors) >= 2
    )

    blocked_probe_types = (
        list(DEFAULT_BLOCKED_PROBE_TYPES) if is_factual_chain else []
    )
    preferred_followup_type = (
        "next_factual_link" if is_factual_chain else ""
    )

    # Dedupe cue_labels preserving order
    cue_labels = list(dict.fromkeys(cue_labels))

    return {
        "is_factual_chain": is_factual_chain,
        "confidence": round(confidence, 3),
        "cue_labels": cue_labels,
        "anchors": merged_anchors,
        "blocked_probe_types": blocked_probe_types,
        "preferred_followup_type": preferred_followup_type,
    }


def classify_factual_chain_cues(text: str) -> List[str]:
    """Return just the cue_labels for a turn. Cheap shorthand for
    callers that don't need the full detect dict."""
    return detect_factual_chain(text)["cue_labels"]


def detect_meta_feedback_against_probe(
    text: str,
    last_assistant_text: str,
) -> Dict[str, Any]:
    """Detect narrator pushback against the last assistant probe.

    Returns:
        {
            "is_meta_feedback": bool,
            "last_rejected_probe_type": str,    -- e.g. "sensory" or ""
            "reason": str,                      -- short label / matched phrase
            "turns_remaining": int,             -- how many turns the
                                                --   guard should suppress
                                                --   the rejected probe class
        }

    The narrator's text is the meta-feedback evidence. The last
    assistant text is the probe target — we inspect it for sensory
    vocabulary to determine which class was rejected.
    """
    if not text or not text.strip():
        return {
            "is_meta_feedback": False,
            "last_rejected_probe_type": "",
            "reason": "",
            "turns_remaining": 0,
        }

    m = _META_AGAINST_SENSORY_RX.search(text)
    if not m:
        return {
            "is_meta_feedback": False,
            "last_rejected_probe_type": "",
            "reason": "",
            "turns_remaining": 0,
        }

    matched = m.group(0).strip()

    # Determine which probe class was rejected by inspecting the
    # narrator's text (and optionally the last assistant probe).
    rejected_type = PROBE_TYPE_SENSORY  # default
    haystack = (text or "") + " " + (last_assistant_text or "")
    if _SENSORY_PROBE_RX.search(haystack):
        rejected_type = PROBE_TYPE_SENSORY

    return {
        "is_meta_feedback": True,
        "last_rejected_probe_type": rejected_type,
        "reason": f"narrator rejected probe: '{matched}'",
        "turns_remaining": 2,
    }


def build_factual_chain_followup_context(
    text: str,
    prior_turns: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build the directive payload for the composer / chat path.

    Combines `detect_factual_chain(text)` with meta-feedback state
    derived from the most recent assistant turn (when available in
    `prior_turns`). The returned dict is what the composer wiring
    (Phase 2/3) consumes to decide directive text and whether to
    suppress sensory probe classes.

    `prior_turns` shape: list of dicts with at least `role` and
    `content` keys, ordered oldest → newest. Optional. When omitted
    or empty, the meta-feedback branch returns inactive.
    """
    detection = detect_factual_chain(text)

    # Pull the last assistant turn from prior_turns if available
    last_assistant_text = ""
    if prior_turns:
        for t in reversed(list(prior_turns)):
            if isinstance(t, dict) and t.get("role") == "assistant":
                last_assistant_text = (t.get("content") or "").strip()
                break

    meta = detect_meta_feedback_against_probe(text, last_assistant_text)

    # Compose blocked probe types from both sources (factual chain
    # blocks ambient sensory, meta-feedback blocks the specific
    # rejected class for `turns_remaining`).
    blocked: List[str] = list(detection.get("blocked_probe_types") or [])
    if meta["is_meta_feedback"] and meta["last_rejected_probe_type"]:
        if meta["last_rejected_probe_type"] not in blocked:
            blocked.append(meta["last_rejected_probe_type"])

    # Compose a composer-facing directive string (Phase 2 sees this).
    directive_parts: List[str] = []
    if detection["is_factual_chain"]:
        directive_parts.append(
            "The narrator is giving a factual chain. Do not pivot to "
            "scenery, sounds, smells, atmosphere, or generalized feeling. "
            "Briefly reflect the known sequence and ask for the next "
            "factual link, missing place/date/person/action, or outcome. "
            "Ask one question only."
        )
    if meta["is_meta_feedback"]:
        directive_parts.append(
            f"The narrator rejected the previous "
            f"{meta['last_rejected_probe_type']} framing. Do not ask "
            f"another {meta['last_rejected_probe_type']} question. "
            f"Return to the factual sequence they were describing."
        )

    return {
        "is_factual_chain": detection["is_factual_chain"],
        "confidence": detection["confidence"],
        "cue_labels": detection["cue_labels"],
        "anchors": detection["anchors"],
        "blocked_probe_types": blocked,
        "preferred_followup_type": detection["preferred_followup_type"],
        "meta_feedback": meta,
        "composer_directive": " ".join(directive_parts),
    }


__all__ = [
    "CUE_LABELS",
    "PROBE_TYPE_SENSORY",
    "PROBE_TYPE_ATMOSPHERE",
    "PROBE_TYPE_CAMARADERIE",
    "DEFAULT_BLOCKED_PROBE_TYPES",
    "detect_factual_chain",
    "classify_factual_chain_cues",
    "detect_meta_feedback_against_probe",
    "build_factual_chain_followup_context",
]
