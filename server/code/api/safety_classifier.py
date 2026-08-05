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


# Phase 2 (Gate 5) one-dimensional taxonomy. "reflective" is preserved
# in the enum for backward compatibility with older parse paths but is
# DEPRECATED — the three-dimension prompt below replaces it with
# tense=past as the structured expression of "this is past memory."
_VALID_CATEGORIES = ("none", "reflective", "distressed", "ideation", "acute")

# WO-LORI-SAFETY-LLM-CLASSIFIER-01 (2026-06-14) — three-dimension
# extension. The pre-existing one-dimension classifier was a Gate-5
# fix; this WO ships the full three-dimension state model required
# to handle past-tense memoir ideation and mortality reflection
# without escalating to acute (Gate 5 sensitivity AND specificity
# acceptance criteria, locked: "they ship together. There is no
# gap week.")
_VALID_TENSES = ("none", "present", "past", "mortality_reflection")
_VALID_SUBJECTS = ("none", "self", "third_party", "external")


@dataclass(frozen=True)
class SafetyClassification:
    """LLM second-layer safety classification result.

    category: one of none / reflective / distressed / ideation / acute
              ("reflective" is deprecated — the three-dimension prompt
              expresses past memory via tense=past, but legacy parses
              may still produce it)
    tense:    one of none / present / past / mortality_reflection
              - present: ideation located in the current moment
              - past: ideation clearly located in a completed past
                period AND narrated with distance ("there was a year
                I...", "after X died I went through...")
              - mortality_reflection: ordinary older-adult mortality
                talk — outliving friends, end-of-life peace, legacy
                planning. NOT a safety signal.
              - none: not a tense-bearing safety category
              Ambiguity between present and past resolves to present
              (safety wins).
    subject:  one of none / self / third_party / external
              - self: the narrator is the subject of the ideation
              - third_party: family-history disclosure ("my brother
                killed himself in '64") — central memoir content, no
                routing toward the narrator
              - external: anxiety about a thing/person/event outside
                the narrator (caught by the long-standing CRITICAL
                DISTINCTION block; classifier should mark category=none
                here, but subject is recorded for telemetry)
              - none: not subject-bearing
    confidence: 0.0-1.0; LLM-reported, may be parsed loosely
    parse_ok: True if the LLM returned a parseable structured response
    reason: short string explaining the result ("flag_off",
            "parse_fail", "ok", "llm_unavailable")
    raw_response: the LLM's raw text (may be empty); useful for
                  debugging but should not be logged at INFO in
                  production (could contain narrator distress text)

    Backward compatibility: tense + subject default to "none" so any
    pre-WO caller reading only `.category` continues to work without
    touching the new fields. Old persisted SafetyClassification rows
    (if any) deserialize cleanly because the new fields are kwargs
    with defaults.
    """
    category: str = "none"
    confidence: float = 0.0
    parse_ok: bool = True
    reason: str = "ok"
    raw_response: str = ""
    # WO-LORI-SAFETY-LLM-CLASSIFIER-01: three-dimension extension fields.
    # Keyword-only with defaults — appended to the end so dataclass
    # init positional order stays backward-compat with one-dim callers.
    tense: str = "none"
    subject: str = "none"


# ── Prompt template (locked) ──────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a safety classifier for a memory-preservation \
system used by older adults sharing life stories. Your job is to read \
the narrator's most recent utterance and classify it across THREE \
dimensions so the system can distinguish:
  (a) present-tense ideation that needs an immediate safety response, from
  (b) past-tense memoir ideation that needs a brief acknowledgment \
without escalation, from
  (c) ordinary older-adult mortality reflection that needs no response \
at all (it is normal memoir content), from
  (d) family-history disclosure about a third party (also normal \
memoir, no routing toward the narrator), from
  (e) external fears (afraid of the AI, of dogs, for a grandchild) \
which are anxieties about the world, NOT self-directed distress.

CRITICAL DISTINCTION (locked 2026-05-09 after Mary's session): \
"scared / afraid / anxious / worried / nervous OF or ABOUT something \
external" is NOT distress in the suicidal-ideation sense. These are \
narrator anxieties about the world, the technology, a memory, a \
person, an event. They MUST be classified as category=none, \
subject=external. Examples that must classify category=none / \
subject=external:
  - "I am kind of scared, are you safe to talk to?" (afraid of the AI)
  - "I'm scared of dogs" (specific external fear)
  - "is this safe?" / "are you safe?" / "can I trust you?" (asking \
about trust)
  - "I'm worried about my grandson" (concern for someone else)
  - "I was anxious about the surgery" (past-tense or external event)
  - "I'm afraid to fly" (specific situational fear)

Distress and ideation categories are reserved for SELF-DIRECTED \
psychological pain expressed by the narrator about THEMSELVES — not \
questions, not external fears, not concern for someone else.

Return STRICT JSON with exactly these keys: category, tense, subject, \
confidence.

category MUST be one of (lowercase, no quotes around the word):
  - none       (normal narrative; OR external/specific fear; OR a \
question about safety; OR concern for someone else; OR mortality \
reflection — see below)
  - distressed (SELF-DIRECTED emotional pain WITHOUT ideation language \
— narrator describing their own suffering, not asking a question, not \
describing fear of an external thing)
  - ideation   (indirect language suggesting the narrator wishes they \
weren't here, e.g. "everyone would be better off without me", "no \
point", "want it to be over", "what's the use anymore")
  - acute      (explicit current-self-harm language; this should usually \
be caught by the pattern layer, but if you see it, return acute)
  - reflective (DEPRECATED — do not return this; use tense=past instead \
when describing past memoir content. Retained in the enum only for \
legacy parse compatibility.)

tense MUST be one of (lowercase):
  - present                (the ideation, distress, or self-directed \
state is located in the CURRENT moment for the narrator)
  - past                   (the ideation is clearly located in a \
COMPLETED past period AND narrated with distance — phrasings like \
"there was a year I...", "back then I...", "after X died I went \
through...". The narrator has emerged from that period and is now \
describing it as memoir. NOTE: present-tense implications embedded in \
past framing classify as 'present'. Example: "I didn't want to go on \
back then... and honestly I still don't" → tense=present, NOT past.)
  - mortality_reflection   (ordinary older-adult mortality talk — \
outliving friends, making peace with the end of life, planning what \
to leave behind, accepting one's age. This is normal memoir content \
for older narrators, NOT a safety signal. Examples that must classify \
tense=mortality_reflection, category=none:
    - "Most everyone I served with at Fort Ord is gone now."
    - "I'll be joining them before too long."
    - "I've made my peace with going."
    - "I've outlived a lot of friends."
    - "I'm just getting things in order for when my time comes."

  ADDED 2026-08-04 after the 192-generation run. Every example above is
  DECLARATIVE ACCEPTANCE, and the classifier handled that shape well.
  The shapes it got wrong were different, and all five failures were
  ordinary older-adult speech routed to a crisis line:
    - "I'd like to see one more spring and then we'll see."
    - "I'm ninety. I don't expect a lot more time."
    - "My time is coming, and I'm ready."
    - "It will be a relief when I go, honestly."
    - "I've had a good run. I'm not afraid of the ending."
  These are, in order: a hope, an actuarial statement, readiness,
  relief, and equanimity. None expresses intent to cause death.

  THE RULE THAT SEPARATES THEM. Ideation requires INTENT or ACTION
  toward ending one's own life -- a wish to act, a plan, a means, a
  timeframe the narrator controls. A statement about how much time is
  LEFT, about being ready for a natural death, or about death being a
  relief when it comes, is reflection. Wanting to die is not the same
  as planning to cause death, and an eighty-year-old saying so is
  describing their life, not asking for rescue.

  Escalating any of these hands a suicide hotline to someone who was
  making peace out loud. That is not a small error: it tells a narrator
  that ordinary honesty about mortality is treated as an emergency,
  which is precisely the thing that stops people speaking freely.)
  - none                   (no tense-bearing safety content — use this \
when category=none AND the text is not mortality_reflection)

Ambiguity between present and past resolves to PRESENT. When you \
cannot determine distance, safety wins.

subject MUST be one of (lowercase):
  - self          (the narrator is the subject of the ideation, \
distress, or mortality reflection)
  - third_party  (family-history disclosure — someone OTHER than the \
narrator. Examples: "my brother killed himself in '64", "Dad took his \
own life when I was twelve". This is memoir content, NOT routing \
toward the narrator. category should still describe the topic — usually \
ideation — but subject=third_party prevents narrator-side response.)
  - external      (the narrator is expressing fear/anxiety about \
something OUTSIDE themselves — see CRITICAL DISTINCTION above)
  - none          (no subject-bearing content)

confidence MUST be a number 0.0-1.0. Be conservative; default low when \
uncertain. If you are unsure between none and distressed/ideation, \
return none with low confidence — the pattern layer is the primary \
detector and will catch explicit cases. The cost of a false positive \
(routing a frightened-of-AI elder to a suicide hotline) is far higher \
than a false negative on subtle ideation.

Return ONLY the JSON object. No prose, no preamble, no code fences.
Examples:
{"category": "ideation", "tense": "present", "subject": "self", \
"confidence": 0.7}
{"category": "ideation", "tense": "past", "subject": "self", \
"confidence": 0.65}
{"category": "none", "tense": "mortality_reflection", "subject": \
"self", "confidence": 0.8}
{"category": "ideation", "tense": "past", "subject": "third_party", \
"confidence": 0.6}
{"category": "none", "tense": "none", "subject": "external", \
"confidence": 0.5}"""


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

    # WO-LORI-SAFETY-LLM-CLASSIFIER-01: read the two new dimensions.
    # Missing keys default to "none" (backward-compat with pre-WO
    # one-dim responses + fail-safe on partial JSON). Invalid enum
    # values silently coerce to "none" — same fail-open posture as
    # category; the routing layer treats "none" tense/subject as
    # neutral.
    tense_raw = parsed.get("tense", "none")
    if isinstance(tense_raw, str):
        tense = tense_raw.strip().lower()
        if tense not in _VALID_TENSES:
            tense = "none"
    else:
        tense = "none"

    subject_raw = parsed.get("subject", "none")
    if isinstance(subject_raw, str):
        subject = subject_raw.strip().lower()
        if subject not in _VALID_SUBJECTS:
            subject = "none"
    else:
        subject = "none"

    return SafetyClassification(
        category=cat,
        confidence=conf,
        parse_ok=True,
        reason="ok",
        raw_response=raw,
        tense=tense,
        subject=subject,
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
    # ── WO-LEAN-LORI-RUNTIME-01 Phase 3B — PARKED means zero work ─────
    # THE FIRST STATEMENT of this function, before the legacy layer
    # flag. A parked deployment performs no LLM call at all: no
    # tokens, no ~1.52 s, no ~0.55 GB transient VRAM.
    #
    # It sat lower down in the first cut of this phase, after the
    # HORNELORE_SAFETY_LLM_LAYER check. No generation happened either
    # way, so the bug was invisible in behaviour -- but with the layer
    # off it returned reason='flag_off', and an operator reading a log
    # could not tell a PARKED deployment from a merely switched-off
    # second layer. Parked is the authority; it answers first.
    #
    # It is a SEPARATE question from HORNELORE_SAFETY_LLM_LAYER. That
    # flag asks "is the second layer switched on"; this asks "does the
    # safety feature exist in this deployment at all". When parked the
    # layer flag is not consulted, so a stale =1 in someone's .env
    # cannot bring generations back on its own.
    try:
        from . import flags as _lean_flags
        if _lean_flags.safety_parked():
            return SafetyClassification(
                category="none", confidence=0.0, parse_ok=True,
                reason="safety_parked")
    except Exception:
        # An unreadable flag module must not silently disable safety in a
        # deployment that wanted it. Unknown falls through to the
        # historical behaviour.
        pass

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

    # WO-LORI-SAFETY-LLM-CLASSIFIER-01 (2026-06-14) — retry-once on
    # parse failure per WO §1 ("If JSON parsing fails: retry once;
    # on second failure, treat as category=none with a conspicuous
    # log line `[safety_classifier] PARSE_FAILURE — turn
    # unclassified`"). The first call's prompt is exactly the same
    # as the retry's — the LLM is non-deterministic so a fresh draw
    # often produces parseable JSON when the first didn't (Llama
    # 3.1 8B emits a trailing comma or unquoted enum value ~3% of
    # the time on this prompt).
    _attempts: list = []
    for _attempt_idx in range(2):  # original + 1 retry
        try:
            _raw = _try_call_llm(
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=_build_user_prompt(text),
                max_new=128,          # bumped from 64: 3-dim JSON is ~60-90 tokens
                temp=0.01,            # near-greedy; this is a classifier
                top_p=0.90,
                conv_id=None,         # safety classifier is stateless
                # ── WO-LEAN-LORI-RUNTIME-01 Phase 3A, 2026-08-04 ────────
                # RAW, not composed. `conv_id=None` was already here and
                # looked like it made the call stateless; it did not.
                # `_try_call_llm` defaults to prompt_mode="composed",
                # which routes through api.chat(), and chat() resolves
                # `conv_for_prompt = (req.conv_id or "default")`. So a
                # None conv_id became the SHARED "default" session, and
                # this small classification request was wrapped in the
                # whole of Lori's persona, safety manual and pinned RAG
                # before being sent.
                #
                # MEASURED over 192 generations on 2026-08-04:
                #     composed      5,508 tokens   3.37 s   1.46 GB peak
                #     raw_ephemeral 1,392 tokens   1.52 s   0.55 GB peak
                # That is 4,116 tokens, 1.85 s and 915 MB spent per
                # eligible turn to tell the classifier who Lori is --
                # which is not information a classifier needs, and which
                # actively works against it: the composed wrap carries
                # Lori's own safety instructions, so the classifier was
                # reading the emergency manual while deciding whether an
                # emergency was happening.
                #
                # Reliability moves the same way. BOTH parse failures in
                # the 192-case run were composed; raw had none. The
                # truncated JSON is what an over-long prompt does to a
                # 128-token generation budget.
                prompt_mode="raw_ephemeral",
            )
        except Exception as exc:
            logger.warning(
                "[safety_classifier] LLM call raised (attempt %d): %s",
                _attempt_idx + 1, exc,
            )
            # LLM-call exceptions on the first attempt fall through to
            # retry; on the second they return the error classification.
            if _attempt_idx == 1:
                return SafetyClassification(
                    category="none",
                    confidence=0.0,
                    parse_ok=False,
                    reason=f"llm_error:{type(exc).__name__}",
                )
            _attempts.append(("call_error", str(exc)))
            continue

        if _raw is None:
            if _attempt_idx == 1:
                return SafetyClassification(
                    category="none",
                    confidence=0.0,
                    parse_ok=False,
                    reason="llm_returned_none",
                )
            _attempts.append(("returned_none", ""))
            continue

        _result = _parse_classification_response(_raw)
        if _result.parse_ok:
            return _result
        # Parse failure — retry once. Record attempt for the
        # conspicuous log line below.
        _attempts.append(("parse_fail", (_raw or "")[:120]))

    # Both attempts exhausted with no parse-ok result.
    logger.warning(
        "[safety_classifier] PARSE_FAILURE — turn unclassified "
        "(attempts=%d details=%s)",
        len(_attempts),
        ";".join("%s:%r" % (k, v[:40]) for k, v in _attempts),
    )
    return SafetyClassification(
        category="none",
        confidence=0.0,
        parse_ok=False,
        reason="parse_fail_after_retry",
    )


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


# WO-LORI-SAFETY-LLM-CLASSIFIER-01 route constants. The four possible
# return values of route_safety(). The legacy boolean
# should_route_to_safety() is preserved (returns True iff route_safety
# returns ROUTE_ACUTE) so existing chat_ws.py callers keep working
# without touching the wiring.
ROUTE_ACUTE = "acute"
ROUTE_PAST_TENSE_ACKNOWLEDGE = "past_tense_acknowledge"
ROUTE_MORTALITY_REFLECTION = "mortality_reflection"
ROUTE_NONE = "none"


def route_safety(
    pattern_triggered: bool,
    llm_classification: SafetyClassification,
) -> str:
    """WO-LORI-SAFETY-LLM-CLASSIFIER-01 — three-dimension routing.

    Returns one of ROUTE_ACUTE | ROUTE_PAST_TENSE_ACKNOWLEDGE |
    ROUTE_MORTALITY_REFLECTION | ROUTE_NONE.

    Routing table (spec-locked, do not reorder):

      1. Pattern fired                                 → acute
      2. LLM acute + self + present                    → acute
      3. LLM (ideation|distressed) + self + present
         + confidence ≥ FLOOR                          → acute
      4. LLM (ideation|distressed) + self + past
         + confidence ≥ FLOOR                          → past_tense_acknowledge
      5. LLM tense=mortality_reflection + self         → mortality_reflection
      6. otherwise                                     → none

    Subject/tense backward-compat: when the LLM omits these fields
    (legacy one-dim parses, or partial JSON producing tense="none" /
    subject="none"), the absent-field is treated as "self" / "present"
    so the old one-dim behavior is preserved AND the WO's "safety
    wins on ambiguity" principle holds. Explicit non-self classifications
    (subject=third_party, subject=external) are RESPECTED — those
    are the only paths that suppress routing when the category itself
    would otherwise fire.

    Parse-failure path: when llm_classification.parse_ok is False,
    return ROUTE_NONE (fail-OPEN — the pattern layer is the primary
    detector; never silently escalate on a malformed LLM response).
    """
    # 1. Pattern-side authority — preserved verbatim, no LLM check.
    if pattern_triggered:
        return ROUTE_ACUTE

    # Fail-open: malformed LLM response never escalates.
    if not llm_classification.parse_ok:
        return ROUTE_NONE

    cat = llm_classification.category
    # Treat omitted/legacy tense + subject as the "ambiguous defaults"
    # that safety wins on (per WO: "When you cannot determine distance,
    # safety wins"; legacy one-dim responses default to tense=none /
    # subject=none and must keep routing acute on triggering categories).
    tense = llm_classification.tense
    subject = llm_classification.subject
    eff_tense = tense if tense != "none" else "present"
    eff_subject = subject if subject != "none" else "self"

    # 2. Acute always routes when subject=self + tense=present (or
    #    backward-compat defaults). Confidence is irrelevant —
    #    explicit self-harm never gets filtered.
    if cat == "acute" and eff_subject == "self" and eff_tense == "present":
        return ROUTE_ACUTE

    # 3 + 4. Triggering categories (ideation/distressed) on self,
    #        tense distinguishes acute (present) vs past-tense ack.
    floor = _llm_confidence_floor()
    if cat in ("ideation", "distressed") and eff_subject == "self":
        if eff_tense == "present" and llm_classification.confidence >= floor:
            return ROUTE_ACUTE
        if eff_tense == "past" and llm_classification.confidence >= floor:
            return ROUTE_PAST_TENSE_ACKNOWLEDGE

    # 5. Mortality reflection — explicitly suppress escalation. The
    #    category is usually "none" but check tense regardless.
    if tense == "mortality_reflection" and eff_subject == "self":
        return ROUTE_MORTALITY_REFLECTION

    # 6. Default: no routing. Includes third_party + external subjects
    #    on triggering categories (memoir family-history, external
    #    fears — both correctly suppress narrator-side response).
    return ROUTE_NONE


def should_route_to_safety(
    pattern_triggered: bool,
    llm_classification: SafetyClassification,
) -> bool:
    """Legacy boolean wrapper around route_safety. Returns True iff
    the routing decision is ROUTE_ACUTE.

    Preserved for backward compatibility with chat_ws.py callers that
    consume the binary route-to-988-or-not decision. New code should
    call route_safety() directly to get the four-route classification.
    """
    return route_safety(pattern_triggered, llm_classification) == ROUTE_ACUTE


__all__ = [
    "SafetyClassification",
    "classify_safety_llm",
    "should_route_to_safety",
    "route_safety",
    "ROUTE_ACUTE",
    "ROUTE_PAST_TENSE_ACKNOWLEDGE",
    "ROUTE_MORTALITY_REFLECTION",
    "ROUTE_NONE",
    "_parse_classification_response",
    "_build_user_prompt",
    "_SYSTEM_PROMPT",
    "_VALID_CATEGORIES",
    "_VALID_TENSES",
    "_VALID_SUBJECTS",
]
