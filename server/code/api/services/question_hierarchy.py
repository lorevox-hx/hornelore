"""WO-LORI-STORY-FIRST-PHASE-1-01 (2026-06-14) — question hierarchy.

═══════════════════════════════════════════════════════════════════════
  WHAT THIS IS
═══════════════════════════════════════════════════════════════════════

The four-layer question ladder Lori's composition must respect. The
discipline is code-enforced: a question of Layer N can only fire when
the session state and momentum permit it. The locked rule:

    No Layer 3 or 4 unless Layer 1 or 2 has already succeeded in the
    current session.

Layers (1 → 4):

  1  OPEN_RECALL    "Tell me about X." / "What do you remember?"
  2  NARRATIVE      "Who was there?" / "What was the setting?"
  3  TIMELINE       "About how old were you?" / "Was this before X?"
  4  VERIFICATION   "Was that Spokane?" / "Did you mean...?"

═══════════════════════════════════════════════════════════════════════
  CLASSIFICATION STRATEGY
═══════════════════════════════════════════════════════════════════════

Phase 1 uses a deterministic lexical classifier as the primary path,
with an optional LLM fallback for ambiguous cases. The lexical
classifier covers the common question patterns reliably and is fast.
The LLM fallback only fires when:
  - LLM classifier is available (caller's choice)
  - Lexical classification is ambiguous (multiple layers match) or
    unknown (no layer pattern matched)
  - HORNELORE_STORY_FIRST_PHASE_1_LLM_CLASSIFY=1

Classification results are cached by normalized question fingerprint
so repeated patterns don't re-classify.

═══════════════════════════════════════════════════════════════════════
  ELIGIBILITY MODEL
═══════════════════════════════════════════════════════════════════════

`eligible_layers(session_state, momentum_mode) → Set[int]`:

  Layer 1: always
  Layer 2: eligible iff session_state.has_substantive_narrative_turn
  Layer 3: eligible iff Layer 2 eligible AND momentum_mode != "story"
            AND session_state.has_layer_2_succeeded
  Layer 4: eligible iff Layer 2 eligible AND
            session_state.has_layer_2_succeeded AND
            session_state.has_specific_ambiguity (caller flags this
            when a recent narrator turn left ambiguity in canonical
            truth that affects current composition — never preemptive)

═══════════════════════════════════════════════════════════════════════
  PUBLIC API
═══════════════════════════════════════════════════════════════════════

  classify_question_layer(question_text, allow_llm_fallback=False) → int
      Returns the layer (1, 2, 3, or 4) — defaults to 1 on truly
      unknown patterns (open-recall is the safe default).

  extract_questions(response_text) → List[str]
      Pull individual question strings from a Lori response.

  eligible_layers(session_state, momentum_mode) → Set[int]
      Compute which layers may fire this turn.

  enforce_question_hierarchy(response_text, session_state, momentum_mode,
                             allow_llm_fallback=False) → HierarchyResult
      Run the full check. Returns a dataclass with passed,
      classified_layers, violating_layers, and failure_reason.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


# Layer constants — exported for callers
QUESTION_LAYER_OPEN_RECALL = 1
QUESTION_LAYER_NARRATIVE = 2
QUESTION_LAYER_TIMELINE = 3
QUESTION_LAYER_VERIFICATION = 4


# ─────────────────────────────────────────────────────────────────────
# Lexical classifier patterns
# ─────────────────────────────────────────────────────────────────────

# Each pattern is (compiled_regex, layer). The classifier walks the
# patterns in order and returns the first match's layer. Multiple
# matches → layer with highest specificity wins (verification > timeline
# > narrative > open-recall) — we order the patterns deliberately so
# the first-match rule gives the right priority.

_LAYER_4_VERIFICATION_PATTERNS = (
    # Verification questions OPEN with the verb-demonstrative cue.
    # `\A\W*` allows leading punctuation/whitespace (em-dashes, etc.).
    # This anchoring distinguishes "Was that Spokane?" (Layer 4) from
    # "What year was that?" (Layer 3 — the "was that" appears mid-
    # question after a Layer 3 wh-marker). The negative lookahead
    # excludes "Was this before/after/during X?" — those are Layer 3
    # timeline questions even though they share the verb-demonstrative
    # opener (the Layer 3 patterns below specifically catch this form).
    re.compile(
        r"\A\W*(?:was|were|is|are)\s+(?:that|those|this|these)\b"
        r"(?!\s+(?:before|after|during))",
        re.IGNORECASE,
    ),
    re.compile(r"\bdid\s+you\s+mean\b", re.IGNORECASE),
    re.compile(r"\b(?:can|could)\s+(?:you\s+)?confirm\b", re.IGNORECASE),
    re.compile(r"\bjust\s+to\s+(?:be\s+)?(?:sure|clear)\b", re.IGNORECASE),
    re.compile(r"\bis\s+that\s+(?:right|correct)\b", re.IGNORECASE),
)

_LAYER_3_TIMELINE_PATTERNS = (
    re.compile(r"\bhow\s+old\s+were?\s+you\b", re.IGNORECASE),
    re.compile(r"\babout\s+how\s+old\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+year\b", re.IGNORECASE),
    re.compile(r"\bwhich\s+year\b", re.IGNORECASE),
    re.compile(r"\bwas\s+this\s+(?:before|after|during)\b", re.IGNORECASE),
    re.compile(r"\bbefore\s+or\s+after\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+decade\b", re.IGNORECASE),
    re.compile(r"\bwhen\s+(?:exactly|approximately)\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+age\b", re.IGNORECASE),
    re.compile(r"\bin\s+what\s+year\b", re.IGNORECASE),
)

_LAYER_2_NARRATIVE_PATTERNS = (
    re.compile(r"\bwho\s+(?:else\s+)?was\s+(?:there|with)\b", re.IGNORECASE),
    re.compile(r"\bwho\s+was\s+(?:there|with|in)\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+was\s+(?:the\s+)?(?:place|setting|room|house|scene)\s+like\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+happened\s+(?:next|then|after)\b", re.IGNORECASE),
    re.compile(r"\bhow\s+did\s+that\s+(?:feel|go|end|start)\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+did\s+(?:he|she|they|that|it)\s+(?:say|do|look)\b", re.IGNORECASE),
    re.compile(r"\bwhere\s+were\s+you\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+was\s+going\s+on\b", re.IGNORECASE),
)

_LAYER_1_OPEN_RECALL_PATTERNS = (
    re.compile(r"\btell\s+me\s+about\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+(?:do\s+you\s+)?remember\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+stands\s+out\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+comes\s+to\s+mind\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+(?:was|were)\s+(?:those|that|the)\s+(?:like|time|days|years)\b", re.IGNORECASE),
    re.compile(r"\bcould\s+you\s+(?:tell|share)\s+me\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+kind\s+of\b", re.IGNORECASE),
)


# In specificity order (high → low). First match wins → verification beats
# timeline beats narrative beats open recall, which is the right priority
# because the more specific pattern is the more reliable signal.
_LAYER_PATTERNS = (
    (4, _LAYER_4_VERIFICATION_PATTERNS),
    (3, _LAYER_3_TIMELINE_PATTERNS),
    (2, _LAYER_2_NARRATIVE_PATTERNS),
    (1, _LAYER_1_OPEN_RECALL_PATTERNS),
)


# ─────────────────────────────────────────────────────────────────────
# LLM classification prompt + cache
# ─────────────────────────────────────────────────────────────────────

_LLM_CLASSIFY_PROMPT = """\
Classify the following question into one of four layers:

LAYER 1 (Open Recall): broad invitation to talk about a period or topic.
Examples: "Tell me about your childhood." "What stands out from that time?"
"What do you remember?"

LAYER 2 (Narrative Probe): expands an active story. References people,
places, settings, or events the narrator has already mentioned.
Examples: "Who else was there?" "What was the place like?" "What happened next?"

LAYER 3 (Timeline Clarification): anchors chronology. Asks about age, sequence,
or temporal relationship.
Examples: "About how old were you?" "Was this before the war?" "What year was that?"

LAYER 4 (Verification): confirms a specific factual detail to resolve ambiguity.
Examples: "Was that Spokane, Washington?" "Did you mean your sister?"

Return only the layer number (1, 2, 3, or 4).
"""


# In-process cache. Cleared on stack restart — acceptable for a
# classifier cache. Key = sha1 hash of normalized question text.
_CLASSIFICATION_CACHE: Dict[str, int] = {}


def _normalize_question_text(text: str) -> str:
    """Lowercase, collapse whitespace, strip surrounding punctuation —
    so "What stands out?" and "What stands  out ?" hash to the same key."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.strip().lower()).strip("?.! ,;:")


def _cache_key(text: str) -> str:
    norm = _normalize_question_text(text)
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()


def _llm_classify_layer(question_text: str) -> Optional[int]:
    """Optional LLM fallback. Returns the layer or None on failure.

    Gated by HORNELORE_STORY_FIRST_PHASE_1_LLM_CLASSIFY=1. Default
    OFF — the lexical classifier handles common cases well enough
    for v1 and is faster.
    """
    if os.getenv(
        "HORNELORE_STORY_FIRST_PHASE_1_LLM_CLASSIFY", "0",
    ).strip().lower() not in ("1", "true", "yes", "on"):
        return None
    try:
        from ..llm_interview import _try_call_llm  # type: ignore
        raw = _try_call_llm(
            system_prompt=_LLM_CLASSIFY_PROMPT,
            user_prompt=f"Question: {question_text.strip()}\nLayer:",
            max_new=8, temp=0.01, top_p=0.90, conv_id=None,
        )
        if not raw:
            return None
        # Find the first digit 1-4 in the response.
        m = re.search(r"[1-4]", raw)
        if not m:
            return None
        return int(m.group(0))
    except Exception:
        return None


def classify_question_layer(
    question_text: str,
    allow_llm_fallback: bool = False,
) -> int:
    """Return the layer (1-4) for a single question.

    Walks the lexical patterns in specificity order; first match wins.
    Caches by normalized fingerprint so repeated patterns don't
    re-classify.

    When no lexical pattern matches AND `allow_llm_fallback=True`,
    falls through to the LLM classifier (also gated by the env flag
    HORNELORE_STORY_FIRST_PHASE_1_LLM_CLASSIFY=1). When the LLM is
    unavailable or returns nothing, defaults to Layer 1 (open recall
    is the safe default — it's always eligible).
    """
    if not question_text or not question_text.strip():
        return QUESTION_LAYER_OPEN_RECALL

    key = _cache_key(question_text)
    cached = _CLASSIFICATION_CACHE.get(key)
    if cached is not None:
        return cached

    # Walk patterns in specificity order — first match wins
    for layer, patterns in _LAYER_PATTERNS:
        for rx in patterns:
            if rx.search(question_text):
                _CLASSIFICATION_CACHE[key] = layer
                return layer

    # Lexical miss — optionally try LLM
    if allow_llm_fallback:
        llm_layer = _llm_classify_layer(question_text)
        if llm_layer in (1, 2, 3, 4):
            _CLASSIFICATION_CACHE[key] = llm_layer
            return llm_layer

    # Safe default: open-recall (always eligible, so a misclassified
    # question can't trigger a regeneration spuriously).
    _CLASSIFICATION_CACHE[key] = QUESTION_LAYER_OPEN_RECALL
    return QUESTION_LAYER_OPEN_RECALL


def reset_classification_cache() -> None:
    """Test / operator helper — clears the in-process cache."""
    _CLASSIFICATION_CACHE.clear()


# ─────────────────────────────────────────────────────────────────────
# Question extraction
# ─────────────────────────────────────────────────────────────────────


def extract_questions(response_text: str) -> List[str]:
    """Pull individual question strings from a multi-sentence response.

    Each returned string ends with '?'. A response with no '?' returns
    an empty list. Sentence boundaries are heuristic — split on
    sentence-ending punctuation, then keep the substrings that end
    with '?'.
    """
    if not response_text or "?" not in response_text:
        return []
    # Split on sentence-ending punctuation while keeping the
    # terminator. The pattern preserves '?' so we can identify
    # which fragments are questions.
    parts = re.split(r"(?<=[.!?])\s+", response_text.strip())
    return [p.strip() for p in parts if p.strip().endswith("?")]


# ─────────────────────────────────────────────────────────────────────
# Eligibility model
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SessionHierarchyState:
    """The piece of session state the eligibility computation needs.

    Caller (chat_ws) maintains this across turns; this module is
    stateless. All fields default to False / 0 — first turn of a
    session, before any narrator content has been composed against.
    """
    has_substantive_narrative_turn: bool = False
    has_layer_1_succeeded: bool = False
    has_layer_2_succeeded: bool = False
    has_specific_ambiguity: bool = False


def eligible_layers(
    session_state: Optional[SessionHierarchyState],
    momentum_mode: str = "normal",
) -> Set[int]:
    """Return the set of question layers eligible this turn.

    Layer 1 is always eligible. Higher layers gate on session state
    progression and momentum mode per the WO rules:

      Layer 2: eligible iff a substantive narrative turn has occurred
      Layer 3: eligible iff Layer 2 succeeded AND momentum != "story"
      Layer 4: eligible iff Layer 2 succeeded AND there is specific
               ambiguity in current composition (never preemptive)
    """
    eligible: Set[int] = {QUESTION_LAYER_OPEN_RECALL}
    state = session_state or SessionHierarchyState()

    if state.has_substantive_narrative_turn:
        eligible.add(QUESTION_LAYER_NARRATIVE)

    if state.has_layer_2_succeeded and momentum_mode != "story":
        eligible.add(QUESTION_LAYER_TIMELINE)

    if state.has_layer_2_succeeded and state.has_specific_ambiguity:
        eligible.add(QUESTION_LAYER_VERIFICATION)

    return eligible


# ─────────────────────────────────────────────────────────────────────
# Public enforcement entry
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class HierarchyResult:
    """Result of running question hierarchy enforcement on a response.

    passed:             True iff every question in the response is
                         currently eligible
    classified_layers:  per-question layer assignments (in order they
                         appear in the response)
    violating_layers:   layers that fired but are not eligible
    failure_reason:     empty when passed; otherwise "layer_N_not_eligible"
                         (joined by "+" for multiple violations)
    """
    passed: bool
    classified_layers: tuple
    violating_layers: tuple
    failure_reason: str


def enforce_question_hierarchy(
    response_text: str,
    session_state: Optional[SessionHierarchyState] = None,
    momentum_mode: str = "normal",
    allow_llm_fallback: bool = False,
) -> HierarchyResult:
    """Full hierarchy enforcement on a Lori response.

    Procedure:
      1. Extract questions from response
      2. Classify each into Layer 1-4
      3. Compute eligibility for this turn
      4. Pass iff every classified layer ∈ eligible

    When the response contains zero questions, the check passes
    vacuously — there's nothing to gate.
    """
    questions = extract_questions(response_text or "")
    if not questions:
        return HierarchyResult(
            passed=True,
            classified_layers=tuple(),
            violating_layers=tuple(),
            failure_reason="",
        )

    layers = tuple(
        classify_question_layer(q, allow_llm_fallback=allow_llm_fallback)
        for q in questions
    )
    eligible = eligible_layers(session_state, momentum_mode=momentum_mode)
    violating = tuple(sorted({L for L in layers if L not in eligible}))
    passed = not violating
    reason = "" if passed else "+".join(
        f"layer_{L}_not_eligible" for L in violating
    )
    return HierarchyResult(
        passed=passed,
        classified_layers=layers,
        violating_layers=violating,
        failure_reason=reason,
    )


__all__ = [
    "QUESTION_LAYER_OPEN_RECALL",
    "QUESTION_LAYER_NARRATIVE",
    "QUESTION_LAYER_TIMELINE",
    "QUESTION_LAYER_VERIFICATION",
    "SessionHierarchyState",
    "HierarchyResult",
    "classify_question_layer",
    "extract_questions",
    "eligible_layers",
    "enforce_question_hierarchy",
    "reset_classification_cache",
]
