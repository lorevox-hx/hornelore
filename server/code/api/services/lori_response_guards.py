"""Lori post-LLM response guards.

Two pure-stdlib guards that run AFTER the LLM produces a response,
catching specific failure shapes that can't be safely prevented at
the prompt level:

  1. BUG-LORI-LANGUAGE-DRIFT-UNPROMPTED-01 — narrator's recent turns
     are all English, current turn has no Spanish signal, but Lori
     emitted Spanish (or mixed). Replace with English deterministic
     continuation.

  2. BUG-LORI-DANGLING-DETERMINER-01 — Lori's response ends with an
     incomplete determiner ("about the.", "for a.", "with an.").
     Replace with a safe continuation prompt.

Both guards are idempotent and safe-by-default: when the response
looks fine, the original passes through unchanged.

LAW 3: pure deterministic. No LLM. No DB. No IO. No third-party
framework. Only `re` from the stdlib.

Why post-LLM not pre-LLM
------------------------
Both failure shapes are LLM stochasticity / directive-pressure
artifacts that can't be reliably eliminated by prompt-engineering.
Mary's session line 47 ("Let's go back to what you were saying about
the.") shows the LLM emitting a sentence that ends with a determiner
because of token-level cap pressure or generation drift. Kent's line
23 (Spanish response to English narrator turn) shows the LANGUAGE
MIRRORING directive pattern-completing on "repeat that" → translate.
We can't fix the LLM's stochasticity; we can catch the failure shape
post-generation.

Public API
----------
detect_language_drift(assistant_text, narrator_text, recent_narrator_turns)
    -> bool — True when Lori response is Spanish but narrator context
    is English-only.

repair_language_drift(target_language="en") -> str
    Returns a deterministic English continuation prompt.

detect_dangling_determiner(assistant_text) -> bool — True when the
    response ends with an incomplete determiner+period.

repair_dangling_determiner(target_language="en") -> str
    Returns a deterministic continuation prompt.

apply_response_guards(assistant_text, narrator_text, recent_narrator_turns,
                      target_language="en") -> tuple[str, list[str]]
    Apply both guards in order. Returns (possibly-rewritten text,
    list of guard names that fired).
"""
from __future__ import annotations

import re
from typing import List, Sequence, Tuple


# ── Language drift detection ──────────────────────────────────────────────

# Spanish-only signals (accent characters + function words).
# Conservative — false-positives here would force English output on
# legitimate Spanish narrator turns. We only match characters/words
# that are unambiguously Spanish-only.
_SPANISH_ACCENT_CHARS_RX = re.compile(r"[áéíóúñÁÉÍÓÚÑ¿¡]")
_SPANISH_ONLY_WORDS_RX = re.compile(
    r"\b(?:que|el|los|las|una|unos|unas|para|con|por|sin|sobre|"
    # Greetings + common phrases
    r"hola|buenos|días|noches|tardes|gracias|favor|"
    # ser/estar conjugations (incl. imperfect "estaba", "iba", "era")
    r"está|estoy|estás|estamos|están|estaba|estabas|estábamos|estaban|"
    r"fue|fui|fuiste|fuimos|fueron|era|eras|éramos|eran|"
    r"iba|ibas|íbamos|iban|"
    # Common -ando/-iendo gerunds
    r"pensando|hablando|haciendo|viviendo|trabajando|estudiando|"
    # Common verbs
    r"hablaba|decía|recordaba|tenía|sabía|sabíamos|tenían|"
    r"recuerdo|recuerdas|recuerda|recuerdan|"
    r"quiero|quieres|quiere|queremos|"
    # Family / people
    r"hijos|hijas|esposo|esposa|abuela|abuelo|"
    # Q-words / connectors
    r"cuando|donde|cómo|qué|quién|"
    # Pronouns + reflexives
    r"mi|mis|tu|tus|nosotros|usted|ustedes|me|te|se|nos|"
    # Common nouns
    r"casa|familia|tiempo|cosa|cosas|años|día|días)\b",
    re.IGNORECASE,
)


def _looks_spanish(text: str) -> bool:
    """Return True if text contains Spanish-only signals."""
    if not text:
        return False
    if _SPANISH_ACCENT_CHARS_RX.search(text):
        return True
    # Need ≥2 distinct Spanish-only words to call it Spanish (single
    # word like "el" could be a name)
    matches = _SPANISH_ONLY_WORDS_RX.findall(text)
    return len(set(m.lower() for m in matches)) >= 2


def detect_language_drift(
    assistant_text: str,
    narrator_text: str,
    recent_narrator_turns: Sequence[str] = (),
) -> bool:
    """Return True if Lori's response is Spanish but narrator context
    is English-only.

    Conditions (ALL must hold):
      - Assistant text contains Spanish signals
      - Current narrator turn does NOT contain Spanish signals
      - Last 3 prior narrator turns also do NOT contain Spanish signals
        (or fewer than 3 turns of history exist — recency matters)

    The 3-turn lookback prevents false positives in cross-narrator
    sessions where Lori legitimately switches languages mid-session.
    Mid-session language switches by the narrator are valid; Lori
    reciprocating them is the LANGUAGE MIRRORING RULE.
    """
    if not assistant_text or not assistant_text.strip():
        return False
    if not _looks_spanish(assistant_text):
        return False  # Lori is in English — no drift
    # Lori is in Spanish. Check narrator context.
    if narrator_text and _looks_spanish(narrator_text):
        return False  # Narrator IS Spanish — Lori is correctly mirroring
    # Check recent narrator turns. If ANY recent turn is Spanish,
    # there's session-level Spanish context; not a drift.
    for prior in (recent_narrator_turns or [])[-3:]:
        if prior and _looks_spanish(prior):
            return False
    # Lori is Spanish, narrator and recent context are English-only.
    # That's drift.
    return True


_LANGUAGE_DRIFT_REPAIR_EN = (
    "Let me say that in English. What would you like to tell me next?"
)
_LANGUAGE_DRIFT_REPAIR_ES = (
    "Déjame decir eso en inglés. ¿Qué te gustaría contarme ahora?"
)


def repair_language_drift(target_language: str = "en") -> str:
    """Return a deterministic continuation in the target language.
    Default English (the most common case — narrator is English and
    Lori drifted to Spanish)."""
    if target_language and target_language.lower().startswith("es"):
        return _LANGUAGE_DRIFT_REPAIR_ES
    return _LANGUAGE_DRIFT_REPAIR_EN


# ── Dangling determiner detection ─────────────────────────────────────────

# Match the response ending with an incomplete determiner / preposition
# followed by an optional period. Mary's session line 47:
# "Let's go back to what you were saying about the." → matches.
#
# Conservative — only fires on EXACTLY these tokens at the end of the
# response. Doesn't fire on legitimate sentences ending in these
# words mid-sentence ("the table was set" — no trailing period plus
# nothing-else).
_DANGLING_DETERMINER_RX = re.compile(
    r"\b(?:the|a|an|to|of|with|about|for|in|on|at|by|from|into|onto|"
    r"upon)\.\s*$",
    re.IGNORECASE,
)


def detect_dangling_determiner(assistant_text: str) -> bool:
    """Return True if the response ends with a determiner + period
    pattern indicating an incomplete sentence."""
    if not assistant_text:
        return False
    text = assistant_text.rstrip()
    return bool(_DANGLING_DETERMINER_RX.search(text))


_DANGLING_REPAIR_EN = (
    "Let's stay with that. What happened next?"
)
_DANGLING_REPAIR_ES = (
    "Sigamos con eso. ¿Qué pasó después?"
)


def repair_dangling_determiner(target_language: str = "en") -> str:
    if target_language and target_language.lower().startswith("es"):
        return _DANGLING_REPAIR_ES
    return _DANGLING_REPAIR_EN


# ── Combined application ─────────────────────────────────────────────────


def apply_response_guards(
    assistant_text: str,
    narrator_text: str = "",
    recent_narrator_turns: Sequence[str] = (),
    target_language: str = "en",
) -> Tuple[str, List[str]]:
    """Apply both guards in order. Language drift is checked first
    (a Spanish drift response will also fail the dangling-determiner
    check meaninglessly; replace whole response). Returns
    (final_text, list of guard names that fired).
    """
    fired: List[str] = []
    text = assistant_text or ""

    if detect_language_drift(text, narrator_text, recent_narrator_turns):
        text = repair_language_drift(target_language)
        fired.append("language_drift")
        return text, fired

    if detect_dangling_determiner(text):
        text = repair_dangling_determiner(target_language)
        fired.append("dangling_determiner")
        return text, fired

    return text, fired


__all__ = [
    "detect_language_drift",
    "repair_language_drift",
    "detect_dangling_determiner",
    "repair_dangling_determiner",
    "apply_response_guards",
]
