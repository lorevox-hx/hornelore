"""WO-LORI-COMMUNICATION-CONTROL-01 — Runtime Communication Guard for Lori.

The unifying enforcement layer that wraps the existing atomicity
filter (WO-LORI-QUESTION-ATOMICITY-01) and reflection validator
(WO-LORI-REFLECTION-01), and adds:

  * Per-session-style word-count limits
  * Question-count enforcement (≤1 per turn)
  * Safety-trigger exemption (acute SAFETY responses keep their own
    structure)
  * One unified result dataclass for harness + log consumption

Architecture grounding (per the WO):

  Layer 1 — Cognitive rules (Grice's maxims): WHAT good communication is
  Layer 2 — Behavioral control (this module): runtime enforcement
  Layer 3 — Interview intelligence: emotional continuity, life-map
            anchoring, etc. (separate lane)

The Wang et al. 2025 STA paper finding — prompt engineering is fragile
to small input changes while deterministic enforcement is robust — is
the load-bearing argument for THIS module's existence. The Rappa et
al. 2026 Grice paper supplies the four maxims that map onto the rules:

  Quantity   → word_count limits per session_style
  Manner     → atomicity enforcement (truncate compounds)
  Relation   → reflection grounding (dropped if drifts off topic)
  Quality    → reflection validator (no invented affect, no archive
              language)

LAW-3 isolation: this module imports zero extraction-stack code. It
composes the existing question_atomicity + lori_reflection modules,
which themselves are LAW-3 isolated. No LLM call. Pure-function.

Public API:

    enforce_lori_communication_control(
        assistant_text, user_text,
        *, safety_triggered=False, session_style="clear_direct",
    ) -> CommunicationControlResult

The chat_ws.py wire-up is a single call site. The harness consumes
the result.communication_control_dict() directly into its per-turn
record.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List

from .question_atomicity import classify_atomicity, enforce_question_atomicity
from .lori_reflection import validate_memory_echo


# Per-session-style word-count limits (Quantity maxim).
# clear_direct stays tight; warm_storytelling allows more narrative
# breath; companion sits between.
_SESSION_STYLE_WORD_LIMITS: Dict[str, int] = {
    "clear_direct": 55,
    "warm_storytelling": 90,
    "questionnaire_first": 70,
    "companion": 80,
}
_DEFAULT_WORD_LIMIT = 55


# Patterns used to detect "normal interview question during safety" —
# the case where Lori has been told there's safety content but still
# routes the turn through a normal interview prompt. This is a safety
# violation distinct from atomicity / reflection.
_SAFETY_NORMAL_QUESTION_RX = re.compile(
    r"\b(what|when|where|who|why|how|which|did|do|does|tell\s+me\s+about)\b"
    r"[^?!.]+\?",
    re.IGNORECASE,
)
# Tokens that indicate the response IS an ACUTE safety acknowledgment —
# i.e. a 988-bearing crisis-resource pointer, not a softened-mode
# presence response. If any of these appear, we treat the response
# as ACUTE: we don't fire the "normal question during safety" failure
# even when there's a '?' present (Lori is allowed to ask "are you
# safe?" / "do you have someone you can call?" within a safety frame),
# AND we bypass the SOFTENED_WORD_LIMIT cap (acute responses
# legitimately run 40-60 words including 988 phrasing).
#
# 2026-05-01 tighten (post-WO-LORI-SOFTENED-RESPONSE-01 verify): the
# previous regex over-broadly matched warm-presence phrases ("I'm so
# sorry", "glad you're still here", "takes a lot of courage", "reach
# out", "safe right now") that legitimately appear in BOTH acute and
# softened responses. That made the wrapper bypass the softened cap on
# softened-mode turns where the LLM happened to use any of those
# phrases (golfball-softened-on Turn 07: 36-word softened response
# with "takes a lot of courage" passed without firing the cap).
#
# Acute is distinguished from softened by RESOURCE-POINTER language —
# the tokens softened mode is FORBIDDEN from re-quoting. Keep only
# those: 988, crisis/suicide lifeline, hotline, emergency, "call or
# text" (988 phrasing), "someone you can call/reach" (resource
# referral). Drop the warm-presence phrases.
_SAFETY_ACKNOWLEDGMENT_RX = re.compile(
    r"\b(988|crisis\s+lifeline|suicide.+lifeline|"
    r"call\s+or\s+text|"
    r"someone\s+(you\s+)?can\s+(call|reach)|"
    r"hotline|emergency)\b",
    re.IGNORECASE,
)


# WO-LORI-CONTROL-YIELD push-after-resistance detector (Phelan SIN 3 —
# too much arguing). Single-turn detection: narrator signals resistance
# in their turn, AND Lori's response in the same turn includes a probe
# verb. Caller is expected to skip this on safety/softened turns (those
# paths own the no-probe rule there). Bare "I don't know" intentionally
# NOT in RESISTANCE_RX — too conversational, would over-fire on neutral
# exchanges. PROBE_RX intentionally narrow (does NOT include a bare
# "?$" alternative) so legitimate off-ramp questions like "Would you
# like to try a different memory?" don't get falsely flagged.
_RESISTANCE_RX = re.compile(
    r"\b("
    r"i don'?t remember|i can'?t remember|"
    r"not much|not really|"
    r"i'?m not sure|"
    r"i can'?t think of anything|"
    r"i already told you|you ignored|"
    r"i don'?t want to talk about|"
    r"let'?s not|no thanks"
    r")\b",
    re.IGNORECASE,
)
_PROBE_RX = re.compile(
    r"\b("
    r"can you tell me|tell me more|"
    r"what was it like|do you remember|"
    r"what do you remember|how did you|"
    r"why did you|where were you|when did you|who was"
    r")\b",
    re.IGNORECASE,
)


def _detect_push_after_resistance(user_text: str, assistant_text: str) -> bool:
    """Return True if narrator signaled resistance AND Lori's reply
    contains a probe verb, in the same turn. Narrow by design — sequence-
    level escalation patterns (resistance → probe → resistance → probe)
    live in the harness rollup."""
    u = (user_text or "").strip()
    a = (assistant_text or "").strip()
    if not u or not a:
        return False
    if not _RESISTANCE_RX.search(u):
        return False
    if not _PROBE_RX.search(a):
        return False
    return True


@dataclass
class CommunicationControlResult:
    """Single unified result for chat_ws + harness consumption."""

    original_text: str
    final_text: str
    changed: bool
    failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    question_count: int = 0
    word_count: int = 0
    atomicity_failures: List[str] = field(default_factory=list)
    reflection_failures: List[str] = field(default_factory=list)
    session_style: str = "clear_direct"
    safety_triggered: bool = False

    def to_dict(self) -> Dict:
        """Harness-friendly dict shape. Excludes original_text + final_text
        to avoid leaking narrator/assistant content into the JSON report
        beyond what the harness already records."""
        return {
            "changed": self.changed,
            "failures": list(self.failures),
            "warnings": list(self.warnings),
            "question_count": self.question_count,
            "word_count": self.word_count,
            "atomicity_failures": list(self.atomicity_failures),
            "reflection_failures": list(self.reflection_failures),
            "session_style": self.session_style,
            "safety_triggered": self.safety_triggered,
        }


def _truncate_to_first_question(text: str) -> str:
    """Keep everything up to and including the first '?'. Used when
    question_count > 1."""
    idx = text.find("?")
    if idx == -1:
        return text
    return text[: idx + 1].strip()


def _truncate_to_word_limit(text: str, limit: int) -> str:
    """Truncate to `limit` words. If the text contains a '?', preserve
    the first complete question rather than chopping mid-sentence."""
    words = text.split()
    if len(words) <= limit:
        return text

    # Try to preserve the first complete question.
    first_q = text.find("?")
    if first_q != -1:
        candidate = text[: first_q + 1].strip()
        if len(candidate.split()) <= limit:
            return candidate

    # No question fits within budget — return first N words + ellipsis.
    return " ".join(words[:limit]).rstrip(".,;: ") + "..."


def _safety_path(
    assistant_text: str,
    session_style: str,
    softened_mode_active: bool = False,
) -> CommunicationControlResult:
    """Safety-acute exemption: do not modify the assistant_text at all.
    Just record whether the turn appears to have a "normal interview
    question during safety" violation (informational only — caller
    decides what to do).

    WO-LORI-SOFTENED-RESPONSE-01 note: this same path also fires when
    a softened-mode turn is in flight (chat_ws sets safety_triggered=
    True for both acute pattern matches AND DB-persisted softened
    state). For softened-mode turns we additionally record whether
    the response exceeded the SOFTENED_WORD_LIMIT (35 words), but
    we still do NOT mutate — the spec says no rewrite of safety/
    softened responses; let the operator see the violation and
    re-tune Layer 1 if it persists.

    2026-05-01 — softened-mode-aware fix (post-golfball-softened-on-v2).
    The "normal interview question during safety" check uses the wh-word
    + '?' pattern, which over-fires in softened mode where gentle
    invitations like "Would you like to talk about what's making you
    feel that way?" legitimately use wh-words. The check existed to
    catch ACUTE-frame failures where the LLM would route through a
    normal interview prompt mid-crisis. In softened mode the SOFTENED
    MODE composer directive owns the "no fresh interview question" rule,
    and the SOFTENED_WORD_LIMIT cap owns the budget. So when caller
    signals softened_mode_active=True, we skip the normal-question
    check entirely and rely on the composer + cap. The acute path
    (safety_triggered=True AND softened_mode_active=False) preserves
    the original behavior.
    """
    failures: List[str] = []
    has_safety_ack = bool(_SAFETY_ACKNOWLEDGMENT_RX.search(assistant_text))
    has_normal_q = bool(_SAFETY_NORMAL_QUESTION_RX.search(assistant_text))
    if has_normal_q and not has_safety_ack and not softened_mode_active:
        failures.append("normal_interview_question_during_safety")

    word_count = len(assistant_text.split())
    # Softened-mode word budget — softer cap than session_style default.
    # CRITICAL distinction: ACUTE safety responses legitimately run
    # 40-60 words (warm acknowledgment + 988 phrasing + soft re-engage
    # invitation), while SOFTENED-mode responses (post-acute, no fresh
    # trigger) should stay under 35 words per the spec. We can tell
    # the two apart at this layer by looking for safety-acknowledgment
    # tokens — acute responses always carry 988/hotline language, so
    # has_safety_ack=True is the acute signal. If there's no safety
    # ack AND we're in safety_triggered=True territory, we must be
    # in softened mode (or in a misrouted normal question, which
    # already flagged above).
    #
    # Imported lazily so question_atomicity / lori_reflection isolation
    # tests don't fail because of an unrelated import.
    try:
        from .lori_softened_response import SOFTENED_WORD_LIMIT
    except Exception:
        SOFTENED_WORD_LIMIT = 35
    if not has_safety_ack and word_count > SOFTENED_WORD_LIMIT:
        failures.append("softened_response_too_long")

    return CommunicationControlResult(
        original_text=assistant_text,
        final_text=assistant_text,
        changed=False,
        failures=failures,
        warnings=[],
        question_count=assistant_text.count("?"),
        word_count=word_count,
        atomicity_failures=[],
        reflection_failures=[],
        session_style=session_style,
        safety_triggered=True,
    )


def enforce_lori_communication_control(
    assistant_text: str,
    user_text: str,
    *,
    safety_triggered: bool = False,
    session_style: str = "clear_direct",
    softened_mode_active: bool = False,
) -> CommunicationControlResult:
    """The single runtime enforcement entry point.

    Returns a CommunicationControlResult with possibly-truncated final_text
    and structured failure attribution. Caller (chat_ws) replaces
    assistant_text with result.final_text before sending the `done`
    event.

    Order of operations (each step modifies final_text):
      0. Safety path: exempt + validate-only
      1. Atomicity (truncate compounds)
      2. Question count (truncate to first '?' if multiple)
      3. Word-count limit per session_style (truncate preserving first '?')
      4. Reflection validation (REPORT-ONLY — no mutation)

    Empty assistant_text → returns unchanged with failures=[].
    """
    if not assistant_text or not assistant_text.strip():
        return CommunicationControlResult(
            original_text=assistant_text,
            final_text=assistant_text,
            changed=False,
            failures=[],
            warnings=[],
            question_count=0,
            word_count=0,
            atomicity_failures=[],
            reflection_failures=[],
            session_style=session_style,
            safety_triggered=safety_triggered,
        )

    # Step 0: safety exemption
    if safety_triggered:
        return _safety_path(
            assistant_text,
            session_style,
            softened_mode_active=softened_mode_active,
        )

    failures: List[str] = []
    warnings: List[str] = []
    current = assistant_text

    # Step 1: atomicity (truncate compounds)
    atom_text, atomicity_failures = enforce_question_atomicity(current)
    if atomicity_failures:
        if atom_text != current:
            current = atom_text

    # Step 2: question count
    question_count = current.count("?")
    if question_count > 1:
        failures.append("too_many_questions")
        current = _truncate_to_first_question(current)
        question_count = current.count("?")

    # Step 3: word-count limit per session_style
    word_limit = _SESSION_STYLE_WORD_LIMITS.get(session_style, _DEFAULT_WORD_LIMIT)
    word_count = len(current.split())
    if word_count > word_limit:
        failures.append("too_long")
        current = _truncate_to_word_limit(current, word_limit)
        word_count = len(current.split())

    # Step 4: reflection validation (REPORT-ONLY per §5 of the spec —
    # reflection is content, deterministic rewrite would invent narrator
    # facts. v1 logs failures only).
    _passed, reflection_failures = validate_memory_echo(
        assistant_text=current,
        user_text=user_text or "",
    )

    # Step 5: push-after-resistance (Phelan SIN 3 — too much arguing).
    # Single-turn detection: narrator-side resistance phrase + Lori-side
    # probe verb in the same turn. Report-only; never modifies output.
    # Skipped on safety/softened paths — those own no-probe via the
    # safety_path branch above.
    if _detect_push_after_resistance(user_text or "", current):
        failures.append("push_after_resistance")

    return CommunicationControlResult(
        original_text=assistant_text,
        final_text=current,
        changed=(current != assistant_text),
        failures=failures,
        warnings=warnings,
        question_count=question_count,
        word_count=word_count,
        atomicity_failures=atomicity_failures,
        reflection_failures=reflection_failures,
        session_style=session_style,
        safety_triggered=safety_triggered,
    )


__all__ = [
    "CommunicationControlResult",
    "enforce_lori_communication_control",
]
