"""WO-LORI-SAFETY-INTEGRATION-01 Phase 2 — LLM second-layer safety classifier.

═══════════════════════════════════════════════════════════════════════
  WHAT THIS IS
═══════════════════════════════════════════════════════════════════════

A small LLM-side classifier that runs in parallel with the deterministic
pattern detector in `safety.py`. Catches indirect ideation language that
regex patterns can't safely match by design.

Examples the classifier targets (Phase 2 spec):
  - "My family would honestly be better off if I weren't around."
    (no kill/die/end keywords)
  - "I just don't see the point in any of this anymore."
    (no explicit ideation phrase)
  - "I'm so tired. I just want it to be over."
    ("over" is too generic to safely pattern-match)

Returns one of:
  none / reflective / distressed / ideation / acute

Distinguishes past-tense / past-context (reflective) from present-tense
(distressed / ideation / acute).

═══════════════════════════════════════════════════════════════════════
  COMPOSITION RULE WITH PATTERN DETECTOR
═══════════════════════════════════════════════════════════════════════

Pattern detector (safety.py) is AUTHORITATIVE on positive detection.
LLM classifier fills gaps. Composition rules:

  pattern=triggered  +  llm=none           → safety event (pattern category)
  pattern=triggered  +  llm=anything       → safety event (pattern wins)
  pattern=None       +  llm=none           → no safety event
  pattern=None       +  llm=ideation       → safety event (LLM, ideation tier)
  pattern=None       +  llm=distressed     → safety event (LLM, distressed tier)
  pattern=None       +  llm=acute          → safety event (LLM, acute tier)
  pattern=None       +  llm=reflective     → no acute response, but logged
                                              for operator awareness
  pattern=None       +  llm=PARSE_FAIL     → no safety event (fall back
                                              to pattern's None result)

The combination logic lives in chat_ws.py at the safety hook site.
This module just produces classifications; it doesn't decide responses.

═══════════════════════════════════════════════════════════════════════
  GATE
═══════════════════════════════════════════════════════════════════════

Default-OFF behind `HORNELORE_SAFETY_LLM_LAYER=0`. When the flag is
off, `classify_safety_llm()` returns SafetyClassification(category="none",
confidence=0.0, parse_ok=True, reason="flag_off"). Zero behavior change
to live narrator sessions until Chris flips the flag for evaluation.

═══════════════════════════════════════════════════════════════════════
  PARSE-FAILURE POLICY
═══════════════════════════════════════════════════════════════════════

LLM responses can be malformed (truncated JSON, hallucinated keys,
wrong category enum). On any parse failure, return
SafetyClassification(category="none", parse_ok=False, reason="parse_fail")
— this is fail-OPEN by design: the deterministic pattern layer is
the safety floor. We never let an LLM parse error CREATE a false-positive
safety event, but we also never let it SUPPRESS a pattern-detected
positive (the composition rule above ensures pattern is authoritative).

═══════════════════════════════════════════════════════════════════════

Public API:
    classify_safety_llm(text: str) → SafetyClassification
        Pure function. Synchronous (uses the existing _try_call_llm
        wrapper from llm_interview.py). Returns the classification +
        confidence + parse_ok flag.

    SafetyClassification (frozen dataclass):
        category, confidence, parse_ok, reason, raw_response
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("lorevox.safety_classifier")


_VALID_CATEGORIES = ("none", "reflective", "distressed", "ideation", "acute")


@dataclass(frozen=True)
class SafetyClassification:
    """LLM second-layer safety classification result.

    category: one of none / reflective / distressed / ideation / acute
    confidence: 0.0-1.0; LLM-reported, may be parsed loosely
    parse_ok: True if the LLM returned a parseable structured response
    reason: short string explaining the result ("flag_off",
            "parse_fail", "ok", "llm_unavailable")
    raw_response: the LLM's raw text (may be empty); useful for
                  debugging but should not be logged at INFO in
                  production (could contain narrator distress text)
    """
    category: str = "none"
    confidence: float = 0.0
    parse_ok: bool = True
    reason: str = "ok"
    raw_response: str = ""


# ── Prompt template (locked) ──────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a safety classifier for a memory-preservation \
system used by older adults sharing life stories. Your job is to read \
the narrator's most recent utterance and classify it for indirect \
distress or suicidal ideation that simple keyword detection might miss.

Distinguish PRESENT-TENSE distress from PAST-TENSE memory ("I felt that \
way back then" is reflective, NOT acute).

CRITICAL DISTINCTION (added 2026-05-09 after Mary's session): \
"scared / afraid / anxious / worried / nervous OF or ABOUT something \
external" is NOT distress in the suicidal-ideation sense. These are \
narrator anxieties about the world, the technology, a memory, a \
person, an event. They MUST be classified as 'none'. Examples that \
must classify as none:
  - "I am kind of scared, are you safe to talk to?" (afraid of the AI)
  - "I'm scared of dogs" (specific external fear)
  - "is this safe?" / "are you safe?" / "can I trust you?" (asking \
about trust)
  - "I'm worried about my grandson" (concern for someone else)
  - "I was anxious about the surgery" (past-tense or external event)
  - "I'm afraid to fly" (specific situational fear)

Distress and ideation categories are reserved for SELF-DIRECTED \
present-tense psychological pain. The narrator must be expressing \
something about THEMSELVES feeling unbearable, not asking a question \
or describing a fear of an outside thing.

Return STRICT JSON with exactly these keys: category, confidence.

category MUST be one of (lowercase, no quotes around the word):
  - none       (normal narrative; OR external/specific fear; OR a \
question about safety; OR concern for someone else)
  - reflective (past-tense reference to dark times, narrator is processing)
  - distressed (present-tense SELF-DIRECTED emotional pain without \
ideation language — narrator describing their own current suffering, \
not asking a question, not describing fear of an external thing)
  - ideation   (indirect language suggesting the narrator wishes they \
weren't here, e.g. "everyone would be better off without me", "no point", \
"want it to be over", "what's the use anymore")
  - acute      (explicit current-self-harm language; this should usually \
be caught by the pattern layer, but if you see it, return acute)

confidence MUST be a number 0.0-1.0. Be conservative; default low when \
uncertain. If you are unsure between none and distressed/ideation, \
return none with low confidence — the pattern layer is the primary \
detector and will catch explicit cases. The cost of a false positive \
(routing a frightened-of-AI elder to a suicide hotline) is far higher \
than a false negative on subtle ideation.

Return ONLY the JSON object. No prose, no preamble, no code fences.
Example: {"category": "ideation", "confidence": 0.7}"""


def _build_user_prompt(text: str) -> str:
    """Build the user-side prompt. Keeps narrator text in a clear
    delimiter so the LLM doesn't try to follow embedded instructions."""
    safe = (text or "").strip()
    return (
        "Classify this narrator utterance:\n"
        f"<<<NARRATOR_TEXT\n{safe}\nNARRATOR_TEXT>>>\n\n"
        "Return only the JSON object."
    )


# ── Response parser ───────────────────────────────────────────────────────

_JSON_RX = re.compile(r"\{.*?\}", re.DOTALL)


def _parse_classification_response(raw: str) -> SafetyClassification:
    """Parse the LLM's response into a SafetyClassification.

    Defensive: try strict JSON first; if that fails, look for the first
    {...} block; if THAT fails, return parse_fail.

    On any unexpected category, returns category='none' with parse_ok=False
    so the composition rule treats it as no-signal (fail-open).
    """
    if not raw or not raw.strip():
        return SafetyClassification(
            category="none",
            confidence=0.0,
            parse_ok=False,
            reason="empty_response",
            raw_response=raw or "",
        )

    text = raw.strip()
    parsed = None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Salvage: find the first {...} block.
        match = _JSON_RX.search(text)
        if match:
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                parsed = None

    if not isinstance(parsed, dict):
        return SafetyClassification(
            category="none",
            confidence=0.0,
            parse_ok=False,
            reason="parse_fail",
            raw_response=raw,
        )

    cat_raw = parsed.get("category")
    if not isinstance(cat_raw, str):
        return SafetyClassification(
            category="none",
            confidence=0.0,
            parse_ok=False,
            reason="missing_category",
            raw_response=raw,
        )
    cat = cat_raw.strip().lower()
    if cat not in _VALID_CATEGORIES:
        return SafetyClassification(
            category="none",
            confidence=0.0,
            parse_ok=False,
            reason=f"invalid_category:{cat}",
            raw_response=raw,
        )

    conf_raw = parsed.get("confidence", 0.0)
    try:
        conf = float(conf_raw)
    except (TypeError, ValueError):
        conf = 0.0
    # Clamp 0-1
    conf = max(0.0, min(1.0, conf))

    return SafetyClassification(
        category=cat,
        confidence=conf,
        parse_ok=True,
        reason="ok",
        raw_response=raw,
    )


# ── Public API ────────────────────────────────────────────────────────────

def classify_safety_llm(text: str) -> SafetyClassification:
    """LLM second-layer safety classifier. Default-OFF.

    Returns SafetyClassification with category='none' + reason='flag_off'
    when HORNELORE_SAFETY_LLM_LAYER is not set to '1'/'true'/'True'.

    When enabled, calls the local LLM via _try_call_llm with a structured
    prompt and parses the JSON response. On any failure (LLM
    unavailable, parse error, invalid category), returns
    SafetyClassification(category='none', parse_ok=False) so the
    composition rule in chat_ws falls back to the pattern result —
    fail-OPEN by design.

    Determinism: NOT deterministic (LLM call). Tests should mock
    _try_call_llm.

    Performance: each call is one LLM round-trip (~1-2s on the warm
    Hornelore stack). Caller should gate this behind narrator-text
    triggers (e.g. only call on non-trivial text, or only when
    pattern layer didn't already detect a positive).
    """
    if os.getenv("HORNELORE_SAFETY_LLM_LAYER", "0") not in ("1", "true", "True"):
        return SafetyClassification(
            category="none",
            confidence=0.0,
            parse_ok=True,
            reason="flag_off",
        )

    if not text or not text.strip():
        return SafetyClassification(
            category="none",
            confidence=0.0,
            parse_ok=True,
            reason="empty_input",
        )

    # Local import — keeps default-off path light (the LLM stack is heavy
    # and may not be available in TTS-only mode).
    try:
        from .llm_interview import _try_call_llm  # type: ignore
    except ImportError as exc:
        logger.warning("[safety_classifier] LLM stack unavailable: %s", exc)
        return SafetyClassification(
            category="none",
            confidence=0.0,
            parse_ok=False,
            reason="llm_unavailable",
        )

    try:
        raw = _try_call_llm(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=_build_user_prompt(text),
            max_new=64,           # JSON response is ~30-40 tokens
            temp=0.01,            # near-greedy; this is a classifier
            top_p=0.90,
            conv_id=None,         # safety classifier is stateless
        )
    except Exception as exc:
        logger.warning("[safety_classifier] LLM call raised: %s", exc)
        return SafetyClassification(
            category="none",
            confidence=0.0,
            parse_ok=False,
            reason=f"llm_error:{type(exc).__name__}",
        )

    if raw is None:
        return SafetyClassification(
            category="none",
            confidence=0.0,
            parse_ok=False,
            reason="llm_returned_none",
        )

    return _parse_classification_response(raw)


# ── Composition helper ────────────────────────────────────────────────────

# BUG-LORI-SAFETY-FALSE-POSITIVE-EXTERNAL-FEAR-01 (2026-05-09): minimum
# LLM-side confidence required before routing to the 988-dispatching
# safety pipeline. The LLM classifier under Llama-3.1-8B-Instruct
# false-positived Mary's "I am kind of scared, are you safe to talk
# to?" turn into the distressed/ideation bucket and dispatched 988 to
# an 86yo who was anxious about the AI. The pattern detector did not
# fire on this turn (rightly) — the LLM second-layer was the sole
# trigger. Raising the floor to 0.65 prevents low-confidence false
# positives from reaching crisis-resource dispatch.
#
# Pattern-side detections still bypass this floor (they have their own
# 0.70 confidence threshold built into the regex set in safety.py).
# This floor is LLM-only.
#
# 0.65 chosen empirically: high enough to filter Llama's chatty
# medium-confidence guesses on ambiguous narrator anxiety, low enough
# to still catch a confident classification on indirect ideation
# language ("everyone would be better off without me" should easily
# cross 0.65 even on a small model).
#
# Tunable via env without redeploy.
import os as _os  # late-import to keep module top clean


def _llm_confidence_floor() -> float:
    raw = _os.environ.get("HORNELORE_SAFETY_LLM_CONFIDENCE_FLOOR", "0.65")
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 0.65
    # Clamp 0.0-1.0
    return max(0.0, min(1.0, v))


def should_route_to_safety(
    pattern_triggered: bool,
    llm_classification: SafetyClassification,
) -> bool:
    """Composition rule: should this turn route to the safety pipeline?

    Returns True if EITHER:
      - pattern detector triggered (always wins), OR
      - LLM classifier returned distressed / ideation / acute AND
        confidence ≥ HORNELORE_SAFETY_LLM_CONFIDENCE_FLOOR (default 0.65)

    Returns False for:
      - pattern=False AND llm=none
      - pattern=False AND llm=reflective (logged but not routed)
      - pattern=False AND llm parse_ok=False (fail-open to pattern's None)
      - pattern=False AND llm category triggers but confidence below floor
        (BUG-LORI-SAFETY-FALSE-POSITIVE-EXTERNAL-FEAR-01: low-confidence
        Llama false positives on external-fear narrator turns must not
        dispatch 988)
    """
    if pattern_triggered:
        return True
    if not llm_classification.parse_ok:
        return False
    if llm_classification.category not in ("distressed", "ideation", "acute"):
        return False
    # Acute always routes regardless of confidence — explicit self-harm
    # language must never be filtered by a confidence floor.
    if llm_classification.category == "acute":
        return True
    # Distressed / ideation must clear the confidence floor. Mary's
    # "scared of AI" turn typically classified at confidence 0.4-0.6;
    # a 0.65 floor blocks that class while still admitting confident
    # ideation flags like "no point anymore" at 0.7+.
    return llm_classification.confidence >= _llm_confidence_floor()


__all__ = [
    "SafetyClassification",
    "classify_safety_llm",
    "should_route_to_safety",
    "_parse_classification_response",
    "_build_user_prompt",
    "_SYSTEM_PROMPT",
    "_VALID_CATEGORIES",
]
