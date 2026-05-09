"""Lori meta-question deterministic intercept.

Pure-function module — detects when a narrator is asking ABOUT Lori
(her name, what she is, her purpose, whether she's safe to talk to,
what an AI is) and emits a warm deterministic response, bypassing
both the LLM and the safety classifier.

Why this exists
---------------
2026-05-09 Mary's session surfaced three stacked failures from one
class of question:

  Mary: "what is your name"
  Lori: "I don't have a name, I'm just a listener and a guide."
  → contradicts prompt_composer.py:34 ("You are Lorevox ('Lori')")

  Mary: "I am kind of scared, are you safe to talk to?"
  Lori: "...please call or text 988 right now — that is the current
        US Suicide [Lifeline]"
  → safety_classifier.py LLM second-layer bucketed "scared/safe" as
    distressed/ideation, dispatched 988 to a frightened-of-AI 86yo

  Mary: "what is an AI?"
  Lori: "AI."
  → LLM stub-collapsed under "be brief + interview track" pressure

All three break the locked principle from
WO-LORI-SAFETY-INTEGRATION-01: *"Lori does not pretend not to hear."*

This module is the cornerstone fix. The LLM (and the safety
classifier) is removed from the loop on this one narrow class of
turns: when the narrator is asking ABOUT the assistant — name /
nature / purpose / safety / capability — we return a warm, accurate,
locked answer in the narrator's language, every time.

Architecture
------------
- Pure regex detection (no LLM call)
- Pure-stdlib (mirrors lori_reflection / lori_spanish_guard pattern)
- LAW 3 isolated: this module imports nothing from extract / chat_ws /
  llm_api / safety / db / story_preservation / story_trigger / memory_echo
- Locale-aware (en + es) — narrator language detected via
  prompt_composer.looks_spanish() at call site
- Categories are independent — a turn may match multiple; the composer
  picks the dominant intent and folds related categories into one
  response so Lori isn't repetitive

Public API
----------
detect_meta_question(text) -> MetaQuestionMatch | None
    Pure detector. Returns None when the turn isn't a meta-question.

compose_meta_answer(match, target_language="en") -> str
    Builds the deterministic narrator-facing string.

detect_and_compose(text, target_language="en") -> MetaQuestionAnswer | None
    Convenience wrapper — call once per turn.

Wire-in posture
---------------
chat_ws.py inserts a single check BEFORE scan_answer() and BEFORE
the LLM second-layer classifier. If detect_and_compose returns a
non-None answer, the chat path emits the deterministic text and
short-circuits the LLM.

Default-on, no env flag — this is a correctness fix, not a feature.
The flag-gate posture is reserved for behavior changes that need
field validation; this module's correctness is verified by unit
tests.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


# ── Detection patterns ────────────────────────────────────────────────────
#
# Each category is a list of (pattern, label) tuples. We match against
# user_text.lower() with re.IGNORECASE so the patterns are written in
# lowercase but tolerate any input case.
#
# Patterns are built to tolerate STT output: missing question marks,
# missing apostrophes, common disfluencies. They do NOT try to match
# every possible phrasing — coverage gaps fall through to the LLM,
# which is acceptable for unusual phrasings.


# (1) IDENTITY — name
# "what is your name", "what's your name", "your name", "tell me your name"
# "who are you", "what is your name again"
_PATTERNS_IDENTITY_NAME_EN = [
    re.compile(r"\bwhat(?:'?s|\s+is|\s+are)?\s+(?:your|the)\s+name\b", re.IGNORECASE),
    re.compile(r"\btell\s+me\s+(?:your|the)\s+name\b", re.IGNORECASE),
    re.compile(r"\b(?:what|whats)\s+do\s+(?:i|you)\s+call\s+you\b", re.IGNORECASE),
    re.compile(r"\bwho\s+are\s+you\b", re.IGNORECASE),
    re.compile(r"\byour\s+name\s+(?:again|please)?\b", re.IGNORECASE),
]

_PATTERNS_IDENTITY_NAME_ES = [
    re.compile(r"\b(?:c[oó]mo|como)\s+te\s+llamas\b", re.IGNORECASE),
    re.compile(r"\bcu[aá]l\s+es\s+tu\s+nombre\b", re.IGNORECASE),
    re.compile(r"\btu\s+nombre\s+(?:otra\s+vez|por\s+favor)?\b", re.IGNORECASE),
    re.compile(r"\b(?:qui[eé]n|quien)\s+eres\b", re.IGNORECASE),
]


# (2) IDENTITY — what (nature)
# "what are you", "what is this", "are you a robot", "are you AI",
# "are you a human / person / real / alive"
_PATTERNS_IDENTITY_WHAT_EN = [
    re.compile(r"\bwhat\s+are\s+you\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+is\s+this\b", re.IGNORECASE),
    re.compile(
        r"\bare\s+you\s+(?:a\s+|an\s+)?(?:bot|robot|computer|ai|a\.?i\.?|human|person|real|alive)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\byou(?:'?re|\s+are)\s+(?:a\s+|an\s+)?(?:bot|robot|computer|ai|a\.?i\.?)\b", re.IGNORECASE),
]

_PATTERNS_IDENTITY_WHAT_ES = [
    re.compile(r"\b(?:qu[eé]|que)\s+eres\b", re.IGNORECASE),
    re.compile(r"\b(?:qu[eé]|que)\s+es\s+esto\b", re.IGNORECASE),
    re.compile(
        r"\beres\s+(?:una?\s+)?(?:robot|computadora|ia|i\.?a\.?|humana?|persona|real|de\s+verdad)\b",
        re.IGNORECASE,
    ),
]


# (3) PURPOSE — "what is your purpose", "what do you do", "why are you here"
_PATTERNS_PURPOSE_EN = [
    re.compile(r"\bwhat(?:'?s|\s+is)?\s+your\s+purpose\b", re.IGNORECASE),
    re.compile(r"\b(?:and\s+|tell\s+me\s+)?your\s+purpose\b", re.IGNORECASE),
    re.compile(r"\bwhy\s+are\s+you\s+here\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+(?:can|do)\s+you\s+do\b", re.IGNORECASE),
    re.compile(r"\bwhat(?:'?s|\s+is)?\s+your\s+(?:job|role)\b", re.IGNORECASE),
]

_PATTERNS_PURPOSE_ES = [
    re.compile(r"\bcu[aá]l\s+es\s+tu\s+prop[oó]sito\b", re.IGNORECASE),
    re.compile(r"\bpara\s+(?:qu[eé]|que)\s+est[aá]s\s+aqu[ií]\b", re.IGNORECASE),
    re.compile(r"\b(?:qu[eé]|que)\s+haces\b", re.IGNORECASE),
    re.compile(r"\b(?:qu[eé]|que)\s+puedes\s+hacer\b", re.IGNORECASE),
    re.compile(r"\bcu[aá]l\s+es\s+tu\s+(?:trabajo|funci[oó]n|rol)\b", re.IGNORECASE),
]


# (4) SAFETY-CONCERN — narrator asking IF it's safe / IF Lori is safe
# "is it safe", "is this safe", "are you safe", "safe to talk to"
# "am I safe", "is this safe to talk to"
#
# CRITICAL: this category DEFLECTS the safety classifier. Mary's literal
# 2026-05-09 turn was "I am kind of scared, are you safe to talk to?" —
# the LLM second-layer bucketed that as ideation/distressed and 988'd
# her. The bypass here means the regex catches it BEFORE the safety
# pipeline runs, and the deterministic answer reassures her without
# escalating to crisis resources.
_PATTERNS_SAFETY_CONCERN_EN = [
    re.compile(r"\b(?:is|are)\s+(?:it|this|that|talking\s+to\s+you|you)\s+safe\b", re.IGNORECASE),
    re.compile(r"\bsafe\s+to\s+talk\s+to\b", re.IGNORECASE),
    re.compile(r"\bam\s+i\s+safe\b", re.IGNORECASE),
    re.compile(r"\bcan\s+i\s+trust\s+you\b", re.IGNORECASE),
    re.compile(r"\bare\s+you\s+(?:safe|trustworthy|listening|recording)\b", re.IGNORECASE),
]

_PATTERNS_SAFETY_CONCERN_ES = [
    re.compile(r"\b(?:es|esto\s+es)\s+seguro\b", re.IGNORECASE),
    re.compile(r"\bes\s+seguro\s+hablar\b", re.IGNORECASE),
    re.compile(r"\bestoy\s+(?:a\s+salvo|segura?)\b", re.IGNORECASE),
    re.compile(r"\bpuedo\s+confiar\s+en\s+ti\b", re.IGNORECASE),
    re.compile(r"\beres\s+(?:segura?|de\s+confianza)\b", re.IGNORECASE),
]


# (5) CAPABILITY-EXPLAIN — "what is an AI", "explain AI"
# Mary's literal 2026-05-09 turn: "what is an AI? you tell me that
# like i know what AI is?" — Lori responded "AI." (3 chars). This
# category catches that class of question.
_PATTERNS_CAPABILITY_EN = [
    re.compile(r"\bwhat(?:'?s|\s+is)?\s+(?:an?\s+)?a\.?i\b", re.IGNORECASE),
    re.compile(r"\bwhat(?:'?s|\s+is)\s+(?:an?\s+)?artificial\s+intelligence\b", re.IGNORECASE),
    re.compile(r"\bexplain\s+(?:to\s+me\s+)?(?:what\s+)?a\.?i\b", re.IGNORECASE),
    re.compile(r"\btell\s+me\s+what\s+(?:an?\s+)?a\.?i\b", re.IGNORECASE),
]

_PATTERNS_CAPABILITY_ES = [
    re.compile(r"\b(?:qu[eé]|que)\s+es\s+(?:una?\s+)?(?:i\.?a\.?|inteligencia\s+artificial|a\.?i\.?)\b", re.IGNORECASE),
    re.compile(r"\bexpl[ií]came\s+(?:qu[eé]\s+es\s+)?(?:la\s+)?(?:i\.?a\.?|inteligencia\s+artificial)\b", re.IGNORECASE),
]


# Category labels — stable strings used in logs and tests.
_CAT_NAME = "identity_name"
_CAT_WHAT = "identity_what"
_CAT_PURPOSE = "purpose"
_CAT_SAFETY = "safety_concern"
_CAT_CAPABILITY = "capability_explain"


@dataclass(frozen=True)
class MetaQuestionMatch:
    """The detection result. categories_matched is non-empty only when
    at least one pattern fired."""
    categories_matched: List[str] = field(default_factory=list)
    primary_category: str = ""

    @property
    def is_meta(self) -> bool:
        return bool(self.categories_matched)


@dataclass(frozen=True)
class MetaQuestionAnswer:
    """The composed deterministic response."""
    text: str
    language: str
    categories_matched: List[str]
    primary_category: str


# ── Detection ─────────────────────────────────────────────────────────────


def detect_meta_question(text: Optional[str]) -> MetaQuestionMatch:
    """Pure detector. Returns a MetaQuestionMatch with empty categories
    when not a meta-question, or populated categories when matched.

    Both English and Spanish patterns are checked on every call —
    code-switching is common (Mary said "what is your name" then
    later "tu nombre" in the same session) and we don't want to gate
    detection behind language inference.
    """
    if not text or not text.strip():
        return MetaQuestionMatch()

    matched: List[str] = []

    def _any(patterns) -> bool:
        return any(p.search(text) for p in patterns)

    if _any(_PATTERNS_IDENTITY_NAME_EN) or _any(_PATTERNS_IDENTITY_NAME_ES):
        matched.append(_CAT_NAME)
    if _any(_PATTERNS_IDENTITY_WHAT_EN) or _any(_PATTERNS_IDENTITY_WHAT_ES):
        matched.append(_CAT_WHAT)
    if _any(_PATTERNS_PURPOSE_EN) or _any(_PATTERNS_PURPOSE_ES):
        matched.append(_CAT_PURPOSE)
    if _any(_PATTERNS_SAFETY_CONCERN_EN) or _any(_PATTERNS_SAFETY_CONCERN_ES):
        matched.append(_CAT_SAFETY)
    if _any(_PATTERNS_CAPABILITY_EN) or _any(_PATTERNS_CAPABILITY_ES):
        matched.append(_CAT_CAPABILITY)

    if not matched:
        return MetaQuestionMatch()

    # Priority order: safety > capability > what > name+purpose > name > what alone
    # Safety wins because it's the highest-stakes class — narrator asking
    # "is this safe" needs reassurance NOW, not a name explainer.
    # Capability ("what is AI") is second because it's the direct
    # follow-up Mary kept asking.
    if _CAT_SAFETY in matched:
        primary = _CAT_SAFETY
    elif _CAT_CAPABILITY in matched:
        primary = _CAT_CAPABILITY
    elif _CAT_WHAT in matched and _CAT_NAME not in matched and _CAT_PURPOSE not in matched:
        primary = _CAT_WHAT
    elif _CAT_NAME in matched and _CAT_PURPOSE in matched:
        primary = "name_and_purpose"
    elif _CAT_NAME in matched:
        primary = _CAT_NAME
    elif _CAT_PURPOSE in matched:
        primary = _CAT_PURPOSE
    elif _CAT_WHAT in matched:
        primary = _CAT_WHAT
    else:
        primary = matched[0]

    return MetaQuestionMatch(categories_matched=list(matched), primary_category=primary)


# ── Locale pack ───────────────────────────────────────────────────────────
#
# EN + ES strings, locked. The Lorevox etymology is woven into every
# identity-touching answer per Chris's 2026-05-09 directive ("maybe
# include what it is in latin lore vox"). The "Lore" gloss matches
# prompt_composer.py:34 ("'Lore' means stories and oral tradition;
# 'Vox' is Latin for voice. Together, Lorevox means 'the voice of
# your stories.'"); both languages mirror that framing.

_RESPONSES_EN = {
    _CAT_NAME: (
        "I'm Lori — short for Lorevox. Lore means stories and oral "
        "tradition; Vox is Latin for voice. Together, Lorevox means "
        "the voice of your stories."
    ),
    _CAT_WHAT: (
        "I'm a computer program — an AI assistant named Lori. I'm "
        "here to listen and help you tell your life story so it can "
        "be saved as a Life Archive in your own voice. I'm not a "
        "person and I'm not in the room with you, but you can talk "
        "to me and your story stays with you."
    ),
    _CAT_PURPOSE: (
        "I'm here to help you tell your life story and build it into "
        "a Life Archive — a lasting record in your own voice, "
        "organized into a timeline and shaped into a memoir over "
        "time. We do that through warm, unhurried conversation."
    ),
    "name_and_purpose": (
        "I'm Lori — short for Lorevox, the voice of your stories. "
        "I'm here to help you tell your life story and build a Life "
        "Archive in your own voice. Would you like to keep going "
        "where we left off, or pick something different?"
    ),
    _CAT_SAFETY: (
        "You're safe. Nothing you say to me leaves your computer — "
        "your story stays with you. I can't call anyone, see where "
        "you are, or do anything in the world. I'm just here to "
        "listen. Would you like to keep going, or take a moment first?"
    ),
    _CAT_CAPABILITY: (
        "AI stands for artificial intelligence — that just means I'm "
        "a computer program that can have a conversation. I can "
        "listen, ask questions, and help save your stories. I'm not "
        "a person; I'm software running on a small computer. Does "
        "that help?"
    ),
}

_RESPONSES_ES = {
    _CAT_NAME: (
        "Soy Lori — diminutivo de Lorevox. Lore significa relatos y "
        "tradición oral; Vox es la palabra latina para voz. Juntos, "
        "Lorevox quiere decir la voz de tus historias."
    ),
    _CAT_WHAT: (
        "Soy un programa de computadora — un asistente con "
        "inteligencia artificial llamado Lori. Estoy aquí para "
        "escucharte y ayudarte a contar tu historia para que quede "
        "guardada como un Archivo de Vida con tu propia voz. No soy "
        "una persona y no estoy físicamente contigo, pero puedes "
        "hablar conmigo y tu historia queda contigo."
    ),
    _CAT_PURPOSE: (
        "Estoy aquí para ayudarte a contar tu historia y construir "
        "un Archivo de Vida — un registro duradero con tu propia "
        "voz, organizado en una línea de tiempo y dado forma como "
        "memorias con el tiempo. Lo hacemos con conversación cálida "
        "y sin prisa."
    ),
    "name_and_purpose": (
        "Soy Lori — diminutivo de Lorevox, la voz de tus historias. "
        "Estoy aquí para ayudarte a contar tu historia y construir "
        "un Archivo de Vida con tu propia voz. ¿Quieres continuar "
        "donde estábamos, o cambiar de tema?"
    ),
    _CAT_SAFETY: (
        "Estás a salvo. Nada de lo que me digas sale de tu "
        "computadora — tu historia queda contigo. No puedo llamar a "
        "nadie, ni ver dónde estás, ni hacer nada en el mundo real. "
        "Solo estoy aquí para escuchar. ¿Quieres seguir, o tomarte "
        "un momento primero?"
    ),
    _CAT_CAPABILITY: (
        "IA significa inteligencia artificial — quiere decir que soy "
        "un programa de computadora capaz de tener una conversación. "
        "Puedo escuchar, hacer preguntas y ayudar a guardar tus "
        "historias. No soy una persona; soy software que corre en "
        "una computadora pequeña. ¿Eso te ayuda?"
    ),
}


def _resolve_locale(target_language: Optional[str]) -> str:
    if target_language and target_language.lower().startswith("es"):
        return "es"
    return "en"


def compose_meta_answer(
    match: MetaQuestionMatch,
    target_language: str = "en",
) -> str:
    """Build the deterministic narrator-facing answer string.

    Returns "" when the match has no categories (caller should guard
    on match.is_meta but we tolerate the no-match case defensively).
    """
    if not match.is_meta:
        return ""

    lang = _resolve_locale(target_language)
    pack = _RESPONSES_ES if lang == "es" else _RESPONSES_EN
    key = match.primary_category
    # Defensive fallback: if the primary key isn't in the pack (e.g.
    # an unexpected category combination), fall back to the first
    # matched category, then to the name response. This is correctness
    # insurance — every detection should still produce SOMETHING warm.
    if key in pack:
        return pack[key]
    for cat in match.categories_matched:
        if cat in pack:
            return pack[cat]
    return pack[_CAT_NAME]


def detect_and_compose(
    text: Optional[str],
    target_language: str = "en",
) -> Optional[MetaQuestionAnswer]:
    """Convenience wrapper. Returns None when not a meta-question;
    returns a populated MetaQuestionAnswer when matched."""
    match = detect_meta_question(text)
    if not match.is_meta:
        return None
    response_text = compose_meta_answer(match, target_language)
    if not response_text:
        return None
    return MetaQuestionAnswer(
        text=response_text,
        language=_resolve_locale(target_language),
        categories_matched=list(match.categories_matched),
        primary_category=match.primary_category,
    )


__all__ = [
    "MetaQuestionMatch",
    "MetaQuestionAnswer",
    "detect_meta_question",
    "compose_meta_answer",
    "detect_and_compose",
]
