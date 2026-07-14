"""Lori post-LLM response guards.

Two pure-stdlib guards that run AFTER the LLM produces a response,
catching specific failure shapes that can't be safely prevented at
the prompt level:

  1. BUG-LORI-LANGUAGE-DRIFT-UNPROMPTED-01 — narrator's recent turns
     are all English, current turn has no Spanish signal, but Lori
     emitted Spanish (or mixed). Replace with a chain-aware English
     continuation built from the narrator's detected anchors.

     STATUS (2026-06-24, iteration 2 — current shipped state):
     ACTIVE ON EVERY SURFACE. An earlier same-day iteration tried
     skipping the guard on surface="trip" to avoid destroying real
     replies with the boilerplate "Sorry - let's continue. What
     would you like to tell me next?" The skip leaked fully Spanish
     replies to English narrators on European-place-name turns
     (Prague / Salzburg / Ljubljana / Pula / Mirano / Padua /
     Cittadella / Chioggia / Mira / Venice / Rovinj) — worse than
     the boilerplate. Iteration 2 reverts the skip and replaces the
     fallback string with a chain-aware English continuation built
     from the narrator's detected anchors (e.g. "Let's stay with
     that in English - you were telling me about Prague, Salzburg,
     and Ljubljana. What happened next?"). The drift guard now runs
     on every surface AND produces substantive English when it fires.

     The surface kwarg on apply_response_guards is preserved (default
     "narrator") for a future caller that genuinely wants per-surface
     opt-out, but the current skip set
     (_SURFACES_WITHOUT_LANGUAGE_DRIFT_REPAIR) is empty. Per the
     product call: English-first narration on every surface;
     multilingual ABILITY remains available as an assistive tool
     (explain a word, pronounce a place, translate a menu) when the
     narrator explicitly asks. The ENGLISH_FIRST_RULE prompt
     directive prevents most drift at generation time; this guard
     remains as the safety net.

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

repair_language_drift(target_language="en", anchors=None) -> str
    Returns a deterministic English continuation. When `anchors` is
    non-empty and target_language is English, the continuation echoes
    up to the first three narrator anchors so the repair is
    substantive rather than the legacy "Sorry - let's continue"
    boilerplate Chris flagged as unacceptable on 2026-06-24.

detect_dangling_determiner(assistant_text) -> bool — True when the
    response ends with an incomplete determiner+period.

repair_dangling_determiner(target_language="en") -> str
    Returns a deterministic continuation prompt.

apply_response_guards(assistant_text, narrator_text="",
                      recent_narrator_turns=(), target_language="en",
                      seeded_facts=None, surface="narrator",
                      narrator_anchors=None) -> tuple[str, list[str]]
    Apply all guards in order. Returns (possibly-rewritten text, list
    of guard names that fired). The `surface` kwarg is preserved for
    future per-surface opt-out (default "narrator"); the current skip
    set is empty so all surfaces get the drift guard. `narrator_anchors`
    threads chain-detection anchors into repair_language_drift when
    the drift fallback fires.
"""
from __future__ import annotations

import re
from typing import List, Optional, Sequence, Tuple


# Per 2026-06-24 product call (English-first iteration 2): the drift
# guard stays ACTIVE on EVERY surface. The earlier surface=="trip"
# skip exposed the underlying bug — Lori was pattern-completing into
# Spanish on European trip narration, and skipping the repair leaked
# fully Spanish replies to English narrators (worse than the
# boilerplate). The fix is two-layered:
#   (1) prevent the drift at generation time with the ENGLISH_FIRST_RULE
#       prompt directive in prompt_composer (always-on for English
#       narrator turns).
#   (2) when drift slips through anyway, repair with a chain-aware
#       English continuation built from the narrator's detected
#       anchors — NOT the destructive "Sorry — let's continue"
#       boilerplate that Chris correctly flagged as unacceptable.
# Surface routing stays in the API in case a future surface needs it,
# but the trip-skip set is now empty.
_SURFACES_WITHOUT_LANGUAGE_DRIFT_REPAIR = frozenset()


# ── Language drift detection ──────────────────────────────────────────────

# Spanish-only signals (accent characters + function words).
# Conservative — false-positives here would force English output on
# legitimate Spanish narrator turns. We only match characters/words
# that are unambiguously Spanish-only.
#
# Two-tier accent detection (2026-07-02,
# BUG-LORI-SPANISH-DETECT-OVERFIRE-FRENCH-ACCENT-01): ñ/¿/¡ are
# unambiguously Spanish. Plain accented vowels are shared with French /
# Italian / Portuguese / English loanwords (Trocadéro, Musée d'Orsay,
# café) — and the VOICE PRESERVATION RULE
# (WO-LORI-ENGLISH-FIRST-SESSION-MODE-01) requires Lori to keep those
# verbatim, so an accented vowel alone must NOT flag a reply as Spanish.
# An accented vowel plus ≥1 Spanish-only word, or ≥2 Spanish-only words
# with no accent, is required. Do NOT lower these thresholds — the
# language-drift repair safety net (Kent K1/K2/K10 evidence) depends on
# this detector staying accurate.
_SPANISH_UNIQUE_CHARS_RX = re.compile(r"[ñÑ¿¡]")
_LATIN_ACCENT_CHARS_RX = re.compile(r"[áéíóúÁÉÍÓÚ]")

# Tokens from _SPANISH_ONLY_WORDS_RX that are ALSO common English /
# French / Italian words, so they cannot carry Spanish evidence in the
# accent tier on their own (2026-07-02, live T4 evidence: Lori's
# English reply "Can you tell ME about the sounds and smells of
# MARCHÉ d'Aligre..." satisfied accent + "me" and was replaced with
# the Spanish drift repair). "el/los/las" also appear in US place
# names (El Paso, Los Angeles, Las Vegas); "era/con/sin/se/te/nos"
# are plain English/French/Italian words.
_AMBIGUOUS_ES_TOKENS = frozenset({
    "me", "te", "se", "nos", "el", "los", "las", "una",
    "con", "sin", "era", "que", "cuando",
})
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
    if _SPANISH_UNIQUE_CHARS_RX.search(text):
        return True  # ñ / ¿ / ¡ alone → Spanish
    hits = set(m.lower() for m in _SPANISH_ONLY_WORDS_RX.findall(text))
    strong = hits - _AMBIGUOUS_ES_TOKENS
    if _LATIN_ACCENT_CHARS_RX.search(text):
        # Accented vowel is shared with French/Italian/PT loanwords
        # (Trocadéro) — require ≥1 UNAMBIGUOUS Spanish word alongside
        # it. "tell me about ... Marché" must stay English.
        return len(strong) >= 1
    # No accent → ≥2 distinct words, at least one unambiguous
    # ("the con man made me..." must stay English).
    return len(hits) >= 2 and len(strong) >= 1


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


# Neutral fallback strings — only used when no chain anchors are
# available to build a context-aware repair.
_LANGUAGE_DRIFT_REPAIR_EN_NEUTRAL = (
    "Let's keep going in English. What happened next in your story?"
)
_LANGUAGE_DRIFT_REPAIR_ES_NEUTRAL = (
    "Disculpa, continuemos. ¿Qué te gustaría contarme ahora?"
)


def repair_language_drift(
    target_language: str = "en",
    anchors: Optional[Sequence[str]] = None,
) -> str:
    """Return a deterministic continuation in the target language.

    When `anchors` is non-empty AND target_language is English, build
    a chain-aware continuation that echoes up to the first three
    narrator anchors so the repair is substantive rather than the
    earlier "Sorry — let's continue" boilerplate that Chris (correctly)
    flagged as unacceptable on the 2026-06-24 Spring 2026 trip canary.

    For Spanish narrators (target_language='es'), the neutral Spanish
    fallback is preserved because the chain-aware framing assumes the
    drifted-FROM language matched English narrator context.
    """
    tl = (target_language or "en").lower()
    if tl.startswith("es"):
        return _LANGUAGE_DRIFT_REPAIR_ES_NEUTRAL

    if anchors:
        cleaned: List[str] = []
        for a in anchors:
            if not a:
                continue
            s = str(a).strip()
            if s and s not in cleaned:
                cleaned.append(s)
            if len(cleaned) >= 3:
                break
        if cleaned:
            if len(cleaned) == 1:
                anchor_text = cleaned[0]
            elif len(cleaned) == 2:
                anchor_text = f"{cleaned[0]} and {cleaned[1]}"
            else:
                anchor_text = (
                    f"{cleaned[0]}, {cleaned[1]}, and {cleaned[2]}"
                )
            return (
                f"Let's stay with that in English — you were telling me "
                f"about {anchor_text}. What happened next?"
            )

    return _LANGUAGE_DRIFT_REPAIR_EN_NEUTRAL


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


# ── Meta-response leak detection ──────────────────────────────────────────
#
# BUG-LORI-META-RESPONSE-LEAK-01 (2026-06-17): the LLM occasionally exposes
# its prompt-compliance reasoning in the user-facing response, e.g.
# Richard Earliest from the 2026-06-17 full-family harness:
#
#   "Here is a response that follows the rules and guidelines:
#    \"You mentioned Magee Hospital where you were born...\"
#    This response reflects the narrator's mentions of Magee Hospital..."
#
# Three failure shapes:
#   1. Preamble: "Here is a response that...", "Here's a reflection and..."
#   2. Quoted draft: the actual response wrapped in quotes after the preamble
#   3. Postamble: "This response reflects...", "This invites the narrator..."
#
# Repair strategy: extract the quoted draft when present (it's usually
# the real reflective response Lori meant to send); otherwise fall back
# to a deterministic continuation prompt.

# Pre-text and post-text meta phrasings — when matched anchored to start
# or end of response, suppress.
_META_PREAMBLE_RX = re.compile(
    r"^(?:\s*)(?:"
    r"here(?:'s| is) (?:a |the |my )?(?:response|reflection|reply|answer)"
    r"(?:\s+(?:that|which))?\s+(?:follows|reflects|adheres|invites|grounds)"
    r"|"
    r"here(?:'s| is) (?:a |the |my )?(?:reflection|response) (?:and|with|grounded)"
    r"|"
    # BUG-LORI-META-RESPONSE-LEAK-WARMLY-ACKNOWLEDGING-01 (2026-06-24)
    # Walt seven-era walk Era 1: LLM literally typed out its own
    # instruction as a preamble — "Warmly acknowledging the narrator's
    # reflection, I reflect one specific anchor from their words: '...'"
    # Boris's no_meta_response_leak scorer did NOT catch this shape;
    # add it to the preamble strip so future stochastic recurrence is
    # auto-repaired before reaching the narrator.
    r"warmly acknowledging the narrator"
    r"|"
    r"i reflect (?:one |a )?specific anchor (?:from|in) (?:their|the narrator'?s) words"
    r"|"
    r"here(?:'s| is) (?:a |my )?reflection of the narrator(?:'s)? (?:message|words|story)"
    r"|"
    r"warm acknowledgment\s*:"
    r"|"
    r"this (?:response|reflection|reply) (?:follows|reflects|adheres|invites|captures|grounds|honors)"
    r"|"
    r"(?:i'?ll|i will|i shall) (?:respond|reply|reflect) (?:by|with|using)"
    r"|"
    r"following the (?:rules|guidelines|instructions)"
    r"|"
    # BUG-LORI-TRIP-PHOTO-VISIBLE-LEAKS-01 (2026-07-09) — second live
    # trip-open leak shape: "Here's a potential response that meets the
    # guidelines:". 'potential/possible/...' adjective slot + a verb the
    # 2026-07-07 list lacked (meets/matches/satisfies).
    r"here(?:'s| is) (?:a |the |my )?(?:potential |possible |suggested |draft |revised )?"
    r"(?:response|reflection|reply|answer)[^.!?\n]{0,60}?"
    r"(?:meets?|matches|satisfies|follows) the (?:guidelines|requirements|rules|criteria)"
    r"|"
    # Bare "Here is the response:" / "Here's my answer:" — Lori never
    # legitimately opens like this; requirements list it explicitly.
    r"here(?:'s| is) (?:the |a |my )?(?:response|answer|reply)(?=\s*:)"
    r"|"
    # BUG-LORI-META-PREAMBLE-LEAK-01 (2026-07-07) — live trip-open leak
    # reached the narrator verbatim: 'Here is the response in the
    # requested format: "Prague and Salzburg stand out..."'. The
    # repair's quoted-draft recovery already handled this shape; the
    # DETECTOR did not (verb list above requires follows/reflects/...).
    r"here(?:'s| is) (?:a |the |my )?(?:response|reflection|reply|answer)"
    r"[^.!?\n]{0,60}?\bin the (?:requested|specified|required|correct) format"
    r")[^\n.]*[:.\n]",
    re.IGNORECASE,
)

# Postamble — meta commentary AFTER the actual response
_META_POSTAMBLE_RX = re.compile(
    r"(?:\n\n|\s+)"
    r"(?:this response|this reply|this reflection)\s+"
    r"(?:reflects|invites|captures|honors|follows|adheres|grounds)"
    r"[^\n]*$",
    re.IGNORECASE | re.MULTILINE,
)

# Editorial / fake-warmth meta from the same generation drift class
_FAKE_WARMTH_RX = re.compile(
    r"\b(?:"
    r"what a (?:rich|wonderful|beautiful|moving|evocative|delightful) (?:narrative|story|account)"
    r"|"
    r"i'?m so grateful to be listening"
    r"|"
    r"let me capture (?:a few|the|some) key points"
    r"|"
    r"thank you for (?:sharing|trusting me with)"
    r")\b",
    re.IGNORECASE,
)

# WO-SPANISH-LIVE-READINESS-01 Patch 9 (2026-06-17, ChatGPT review
# follow-up): translation-refusal preamble patterns. The LANGUAGE
# MIRRORING RULE in compose_system_prompt says "Never translate the
# narrator's own words back at them." When Llama drifts and produces
# "Let me say that in English" / "Déjame decir eso en inglés" as a
# preamble before continuing in the wrong language, the meta-leak
# guard should catch and strip it. Same shape as the EN preamble and
# fake-warmth regexes above; ES branch parallel to those.
_TRANSLATION_REFUSAL_RX = re.compile(
    r"\b(?:"
    # English meta-refusal preambles
    r"let me say that in english"
    r"|"
    r"let me put (?:that|it) in english"
    r"|"
    r"i'?ll say (?:that|it) in english"
    r"|"
    r"in english:"
    # Spanish meta-refusal preambles
    r"|"
    r"d[eé]jame decir(?:lo)? eso en ingl[eé]s"
    r"|"
    r"d[eé]jame ponerlo en ingl[eé]s"
    r"|"
    r"en ingl[eé]s,? lo dir[ií]a"
    r"|"
    r"voy a decir eso en ingl[eé]s"
    r"|"
    r"voy a decirlo en ingl[eé]s"
    r")\b",
    re.IGNORECASE,
)

# Extract the quoted draft when present so we can recover the real
# response from a leaked preamble/postamble wrapper.
_QUOTED_DRAFT_RX = re.compile(
    r'"((?:[^"\\]|\\.)+)"|'
    r"“((?:[^”\\]|\\.)+)”"
)


# WO-SPANISH-LIVE-READINESS-01 Patch 1 (2026-06-17) — Spanish meta-leak
# patterns. The 2026-06-17 full-family run caught Stefi Sandoval's
# Crypto-Jewish New Mexico turn produce "Capté Santa Fe y David" plus
# meta-fluff like "Qué descripción tan rica" — the harness scorer
# flagged it, but the runtime guard's preamble/postamble/fake-warmth
# regexes are English-only and let the Spanish equivalents through.
# These patterns mirror the English ones and cover the meta-shapes
# Llama-3.1-8B produces when it slips into self-narration in Spanish.

_META_PREAMBLE_ES_RX = re.compile(
    r"^(?:\s*)(?:"
    # "Aquí está mi respuesta que sigue las reglas..."
    r"aqu[ií] (?:est[aá] |tienes |va )?(?:mi |una |la |tu )?"
    r"(?:respuesta|reflexi[oó]n|r[eé]plica|contestaci[oó]n)"
    r"(?:\s+(?:que|la cual))?\s+(?:sigue|refleja|honra|invita|captura|cumple)"
    r"|"
    # "Déjame capturar..." / "Déjame reflejar..."
    r"d[eé]jame (?:capturar|reflejar|reflexionar|responder|empezar|comenzar)"
    r"|"
    # "Permíteme..." (formal lead-in)
    r"perm[ií]teme (?:capturar|reflejar|responder)"
    r"|"
    # "Voy a responder..." / "Voy a reflejar..."
    r"voy a (?:responder|reflejar|reflexionar)"
    r"|"
    # "Siguiendo las reglas / instrucciones / pautas..."
    r"siguiendo (?:las |tus )?(?:reglas|instrucciones|pautas|gu[ií]as)"
    r"|"
    # "Esta respuesta refleja / honra / sigue..."
    r"esta (?:respuesta|reflexi[oó]n|r[eé]plica) (?:refleja|honra|sigue|invita|captura|cumple)"
    r")[^\n.]*[:.\n]",
    re.IGNORECASE,
)

_META_POSTAMBLE_ES_RX = re.compile(
    r"(?:\n\n|\s+)"
    r"(?:esta respuesta|esta r[eé]plica|esta reflexi[oó]n)\s+"
    r"(?:refleja|invita|captura|honra|sigue|cumple|asegura)"
    r"[^\n]*$",
    re.IGNORECASE | re.MULTILINE,
)

_FAKE_WARMTH_ES_RX = re.compile(
    r"\b(?:"
    # "Qué descripción tan rica / hermosa / conmovedora..."
    r"qu[eé] (?:descripci[oó]n|relato|narrativa|historia|recuerdo) "
    r"tan (?:rica|hermosa|conmovedora|emotiva|profunda|maravillosa|evocadora)"
    r"|"
    # "Es un honor escucharte..." / "Me siento agradecida..."
    r"(?:es un honor|me siento (?:muy )?agradecid[ao]) "
    r"(?:escucharte|de escucharte|de poder escucharte)"
    r"|"
    # "Gracias por compartir / por confiar en mí..."
    r"gracias por (?:compartir|confiar en m[ií]|contarme)"
    r"|"
    # "Déjame capturar algunos puntos / detalles clave..."
    r"d[eé]jame capturar (?:algunos |unos pocos |los |unos )?"
    r"(?:puntos|detalles|momentos) (?:clave|importantes|principales)"
    r")\b",
    re.IGNORECASE,
)


# BUG-LORI-TRIP-PHOTO-VISIBLE-LEAKS-01 (2026-07-09): the photo-added
# reply leaked a literal directive prefix to the narrator — "SYSTEM.
# What comes to mind when you look at that photo?". Any leading
# SYSTEM./SYSTEM:/System. is prompt scaffolding, never Lori.
_LEADING_SYSTEM_RX = re.compile(r'^\s*["\'\u201c]?(?:SYSTEM|System)\s*[.:]\s*')

# Live modal leak 2026-07-10 — pure meta-reasoning replies, position-free
# ("I'll respond with a neutral message", "since there's no prior
# conversation"). Whole reply is scaffolding; repair falls through to the
# deterministic continuation.
# BUG-GUARDS-DEAD-ON-PY311-INLINE-FLAG-01 (live, 2026-07-14).
# This pattern carried a SECOND inline "(?i)" before the alternation. Python
# 3.10 only warns; Python 3.11+ RAISES re.error ("global flags not at the start
# of the expression at position 99"). The server runs 3.12, so this
# module-level re.compile blew up AT IMPORT — and chat_ws imports the guards
# inside a defensive try/except whose whole purpose is "never break a turn on
# guard failure". It caught the ImportError, logged a WARNING, and passed the
# reply through UNGUARDED.
#
# Net effect: EVERY narrator-facing response guard was dead in production —
# narrator_echo, meta_response_leak, dangling_determiner, language_drift, the
# "I can see" block — all of them, on every turn, silently. Live proof: Lori
# parroting the narrator's own sentence back in the first person ("My father
# built the back porch himself. That's a specific memory.") while the echo
# guard sat there working perfectly and never being called.
#
# The flag now lives in the compile() call, where a version bump cannot move it.
_META_REASONING_RX = re.compile(
    r"i(?:'ll| will) (?:respond|reply|answer) with a "
    r"(?:neutral|generic|simple) (?:message|response)"
    r"|since there(?:'s| is) no prior conversation",
    re.IGNORECASE)


def detect_meta_response_leak(assistant_text: str) -> bool:
    """Return True if the response contains meta-instruction leakage."""
    if not assistant_text:
        return False
    if _LEADING_SYSTEM_RX.search(assistant_text):
        return True
    if _META_REASONING_RX.search(assistant_text):
        return True
    if _META_PREAMBLE_RX.search(assistant_text):
        return True
    if _META_POSTAMBLE_RX.search(assistant_text):
        return True
    if _FAKE_WARMTH_RX.search(assistant_text):
        return True
    # WO-SPANISH-LIVE-READINESS-01 Patch 1 — Spanish meta-shapes.
    if _META_PREAMBLE_ES_RX.search(assistant_text):
        return True
    if _META_POSTAMBLE_ES_RX.search(assistant_text):
        return True
    if _FAKE_WARMTH_ES_RX.search(assistant_text):
        return True
    # WO-SPANISH-LIVE-READINESS-01 Patch 9 — translation-refusal preamble.
    if _TRANSLATION_REFUSAL_RX.search(assistant_text):
        return True
    return False


def repair_meta_response_leak(
    assistant_text: str, target_language: str = "en",
) -> str:
    """Strip preamble/postamble meta; recover quoted draft if present.

    Recovery priority:
      1. If a quoted draft sentence appears in the response, return the
         longest such quoted draft (usually the LLM's actual reflective
         response, wrapped in its own meta commentary).
      2. If we can strip a recognizable preamble/postamble and leave a
         non-empty substring, return that.
      3. Otherwise return a deterministic continuation prompt.
    """
    text = (assistant_text or "").strip()

    # Leading SYSTEM./System: prefix is scaffolding — drop it first so
    # the remainder ("What comes to mind when you look at that photo?")
    # survives as the visible reply.
    text = _LEADING_SYSTEM_RX.sub("", text).strip()
    if _META_REASONING_RX.search(text):
        # Whole reply is meta-reasoning scaffolding — drop the matched
        # sentences; quoted-draft recovery / deterministic fallback below
        # handles what (if anything) remains.
        kept = [s for s in re.split(r"(?<=[.!?])\s+", text)
                if not _META_REASONING_RX.search(s)]
        text = " ".join(kept).strip()

    # Try to recover a quoted draft. The LLM frequently writes
    #   Here is a response: "Real response goes here."
    quoted_drafts = []
    for m in _QUOTED_DRAFT_RX.finditer(text):
        draft = (m.group(1) or m.group(2) or "").strip()
        if len(draft.split()) >= 6:  # discard short artifacts like "yes"
            quoted_drafts.append(draft)
    if quoted_drafts:
        # Return the longest quoted draft — usually the real response.
        return max(quoted_drafts, key=len)

    # Try to strip the leading preamble and trailing postamble.
    stripped = _META_PREAMBLE_RX.sub("", text, count=1).strip()
    stripped = _META_POSTAMBLE_RX.sub("", stripped).strip()
    # Drop any remaining fake-warmth opener sentence
    stripped = _FAKE_WARMTH_RX.sub("", stripped).strip()
    # WO-SPANISH-LIVE-READINESS-01 Patch 1 — also strip Spanish meta-shapes.
    stripped = _META_PREAMBLE_ES_RX.sub("", stripped, count=1).strip()
    stripped = _META_POSTAMBLE_ES_RX.sub("", stripped).strip()
    stripped = _FAKE_WARMTH_ES_RX.sub("", stripped).strip()
    # WO-SPANISH-LIVE-READINESS-01 Patch 9 — strip translation-refusal
    # preambles (EN + ES). When matched, drop the preamble sentence and
    # keep whatever follows.
    stripped = _TRANSLATION_REFUSAL_RX.sub("", stripped).strip()
    # Clean up leftover quote / colon residue
    stripped = stripped.strip().strip(":").strip().strip('"').strip()
    if len(stripped.split()) >= 6:
        return stripped

    # Last resort — deterministic continuation
    if target_language and target_language.lower().startswith("es"):
        return "Cuéntame más sobre eso."
    return "Tell me more about that."


# ── Boris Phase 5 / Phase 6 contract aliases ──────────────────────────────
# The Boris test suite uses canonical contract names; map them onto the
# existing implementations here. `strip_meta_response_leak` is the same as
# `repair_meta_response_leak` — the suite probes the symbol, not the
# semantics, so the alias is a one-liner.
strip_meta_response_leak = repair_meta_response_leak
sanitize_lori_response = repair_meta_response_leak


# WO-SPANISH-LIVE-READINESS-01 Patch 2 (2026-06-17) — runtime
# broken-code-mix guard. Ports `_detect_broken_code_mix` from
# `scripts/harness_lib.py` so we can catch the same shapes at chat-WS
# time (before the narrator sees them) instead of only in the scorer.
#
# Catches the Stefi-class output:
#   "Capté Santa Fe y David. ¿Qué pasó después?"
#   "Tú had an older brother Antonio... y asked my mother."
# These are mid-generation drift: Llama-3.1-8B sometimes loads Spanish
# vocabulary but keeps English grammar scaffolding (or vice versa).
# The harness-side scorer rule (`no_broken_code_mix`) catches the same
# thing after-the-fact; this is the runtime sibling.

_BROKEN_CODE_MIX_SIGNALS = (
    # Spanish receipt scaffolding bolted onto English text
    re.compile(r"\bcapté\b", re.IGNORECASE),
    re.compile(r"\btú\s+(had|made|asked|went|said|called|told)\b", re.IGNORECASE),
    re.compile(r"¿qué pasó después", re.IGNORECASE),
    re.compile(
        r"[a-z]\s+y\s+(asked|said|made|had|went|called|told)\b",
        re.IGNORECASE,
    ),
)

# Inverted Spanish punctuation embedded mid-text
_BROKEN_SPANISH_PUNCT_RX = re.compile(r"[¿¡]")

# English function words for density check
_ENGLISH_FUNCTION_WORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "is", "was",
    "you", "your", "i", "me", "my", "we", "had", "have", "with", "for",
    "on", "at", "what", "when", "where", "do", "did", "are", "be", "been",
})


def detect_broken_code_mix(assistant_text: str) -> Optional[str]:
    """Return a marker string if `assistant_text` looks like broken
    Spanish/English code-mix; None otherwise.

    Heuristic mirrors the harness scorer rule:
      1. Any explicit broken-code-mix signal (Capté / Tú X / ¿Qué pasó
         / X y verb) → fire.
      2. Inverted Spanish punctuation present AND English function-word
         density ≥ 30% (mid-text Spanglish; pure-Spanish narrator turns
         are NOT broken — they only become broken when mixed).

    A pure-Spanish response contains ¿ or ¡ but few English function
    words, so it does NOT trip the density check. A pure-English
    response contains no ¿/¡ so the density branch never runs.
    """
    if not assistant_text or len(assistant_text.split()) < 4:
        return None
    for pat in _BROKEN_CODE_MIX_SIGNALS:
        m = pat.search(assistant_text)
        if m:
            return m.group(0)
    if _BROKEN_SPANISH_PUNCT_RX.search(assistant_text):
        tokens = re.findall(r"\b[a-z]+\b", assistant_text.lower())
        if tokens:
            en_hits = sum(1 for t in tokens if t in _ENGLISH_FUNCTION_WORDS)
            density = en_hits / len(tokens)
            if density >= 0.30:
                return "spanish_punct_in_english_context"
    return None


def repair_broken_code_mix(
    assistant_text: str, target_language: str = "en",
) -> str:
    """Return a clean replacement when broken code-mix is detected.

    Strategy:
      - We CANNOT safely auto-repair the broken sentence (the LLM has
        already lost the thread). Returning the broken text would leak
        Spanglish to the narrator.
      - Substitute a short deterministic continuation prompt in the
        target language. This is the same fallback as
        repair_meta_response_leak's last-resort branch.

    Pure-Spanish responses do NOT trip detect_broken_code_mix, so this
    repair path only fires when the LLM produced a mid-mix string.
    """
    if target_language and target_language.lower().startswith("es"):
        return "Cuéntame más sobre eso."
    return "Tell me more about that."


# Boris Phase 6 — name-confirmation candidate detector. Returns True
# when `phrase` looks like a real proper-noun name (single capitalized
# token, or a short capitalized name like "Eliseo Sandoval"); False
# when it's a descriptive sentence fragment ("It Was The Air",
# "Originally Schong With A C") that the META_FEEDBACK
# correction_spelling template should NOT fire on.
#
# Inverts the semantics of `lori_witness_mode._looks_like_descriptive_phrase`
# and adds single-token name handling so the Boris contract is met.

_NAME_CONFIRM_DESCRIPTIVE_TOKENS = frozenset({
    # Common English verbs (any tense)
    "Was", "Were", "Is", "Are", "Am", "Be", "Been", "Being", "Have",
    "Has", "Had", "Do", "Does", "Did", "Will", "Would", "Can", "Could",
    "Should", "Stopped", "Picture", "Began", "Learned", "Stand", "Sit",
    "Kneel", "Walked", "Talked", "Said", "Moving", "Going", "Coming",
    "Knew", "Knows", "Got", "Get", "Saw", "See", "Took", "Take",
    # Articles, conjunctions, prepositions, pronouns
    "The", "A", "An", "And", "Or", "But", "Of", "With", "By", "From",
    "To", "In", "On", "At", "For", "Into", "Onto", "Upon", "About",
    "I", "We", "You", "He", "She", "It", "They", "My", "Your", "Our",
    "His", "Her", "Its", "Their",
    # Adverbs / qualifiers
    "Originally", "Because", "Still", "Clearly", "Loud", "Out", "Up",
    "Down", "Right", "Left", "Just", "Only", "Very", "Really", "Even",
    "Empty", "Full", "Big", "Small", "All", "Some", "Many", "No", "Yes",
    "Now", "Then", "Here", "There", "Where", "When", "What", "How",
    "Why", "Always", "Never", "Sometimes",
})


def is_valid_name_confirmation_candidate(phrase: str) -> bool:
    """Return True when `phrase` is a real proper-noun name candidate
    suitable for the correction_spelling template; False for descriptive
    sentence fragments.

    Single-token + Capitalized + alphabetic + length ≥ 2  → valid name
    Multi-token (2-4 tokens) + no descriptive tokens + ≥50% titlecase → valid
    Otherwise → invalid (descriptive phrase, too long, contains verb/article)
    """
    if not phrase:
        return False
    stripped = phrase.strip().rstrip(".,!?;:")
    if not stripped:
        return False
    # Sentence-shaped (ends with period in original) → not a name
    if phrase.strip().endswith("."):
        return False
    tokens = stripped.split()
    # Single-token name: must be capitalized, alphabetic, length ≥ 2
    if len(tokens) == 1:
        tok = tokens[0]
        if not tok or len(tok) < 2:
            return False
        if not tok[0].isupper():
            return False
        # Must be mostly alphabetic (allows apostrophes, hyphens)
        if not all(c.isalpha() or c in "'-" for c in tok):
            return False
        # Must not be a descriptive token in title-case position
        if tok in _NAME_CONFIRM_DESCRIPTIVE_TOKENS:
            return False
        return True
    # Multi-token: 2-4 tokens, no descriptive tokens, ≥50% titlecase
    if len(tokens) > 4:
        return False
    for tok in tokens:
        bare = tok.rstrip(".,!?;:")
        if bare in _NAME_CONFIRM_DESCRIPTIVE_TOKENS:
            return False
    cap_count = sum(1 for t in tokens if t and t[0].isupper())
    if cap_count < max(1, len(tokens) // 2):
        return False
    return True


# ── Seeded-fact intake-question detection ────────────────────────────────
#
# BUG-LORI-ASKS-WHAT-OPERATOR-SEEDED-01 (2026-06-17): the prompt-side
# directive (DO NOT ASK FOR SEEDED FACTS) is the primary path, but
# this post-LLM detection function is the safety net. Wired into
# apply_response_guards when the caller passes the seeded_facts dict.

_SEEDED_INTAKE_PATTERNS = (
    # "You were born in X" / "Were you born in X"
    (re.compile(
        r"\b(?:you were|were you) born in ([^?.,\n]+)",
        re.IGNORECASE,
    ), "place_of_birth"),
    # "...in YYYY" appended to the birth question
    (re.compile(
        r"\b(?:you were|were you) born[^?.,]{0,80}\b(\d{4})\b",
        re.IGNORECASE,
    ), "birth_year"),
    # "Do you live in X" / "You live in X"
    (re.compile(
        r"\b(?:do you (?:currently )?live|you (?:currently )?live) in ([^?.,\n]+)",
        re.IGNORECASE,
    ), "current_residence"),
    # "Do you work at X" / "You work at X"
    (re.compile(
        r"\b(?:do you (?:currently )?work|you (?:currently )?work) (?:at|for) ([^?.,\n]+)",
        re.IGNORECASE,
    ), "current_work"),
    # "Did you have N children"
    (re.compile(
        r"\b(?:did you have|do you have)\s+(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+(?:child|children|kids)",
        re.IGNORECASE,
    ), "children_count"),
    # "Is your mother (still) alive"
    (re.compile(
        r"\b(?:is your mother (?:still )?alive|your mother is (?:still )?alive)",
        re.IGNORECASE,
    ), "parent_alive"),
)


def detect_seeded_fact_intake(
    assistant_text: str, seeded_facts: Optional[dict] = None,
) -> Optional[str]:
    """Return the matched field_key if the response asks a seeded-fact
    intake question. None when there's no match or when the seeded
    facts dict is empty/None.

    `seeded_facts` is a dict from field_key to value (operator-seeded).
    Only returns a hit when BOTH:
      - the response matches one of the intake-question regex patterns
      - the matched field_key has a non-empty seeded value
    """
    if not assistant_text or not seeded_facts:
        return None
    for pattern, field_key in _SEEDED_INTAKE_PATTERNS:
        if pattern.search(assistant_text) and seeded_facts.get(field_key):
            return field_key
    return None


def repair_seeded_fact_intake(
    field_key: str, seeded_facts: dict, target_language: str = "en",
) -> str:
    """Rewrite to a lived-experience question around the seeded fact.

    Falls back to a generic continuation in the target language when
    no specific lived-experience rewrite is available for the field.
    """
    spanish = bool(target_language and target_language.lower().startswith("es"))
    if field_key == "place_of_birth":
        place = str(seeded_facts.get("place_of_birth", "")).strip()
        if not place:
            place = ""
        if spanish:
            return f"¿Qué recuerdas de {place} cuando eras pequeño?" if place else "¿Qué recuerdas de cuando eras pequeño?"
        return f"What do you remember about {place} when you were little?" if place else "What do you remember about your earliest years?"
    if field_key == "current_residence":
        place = str(seeded_facts.get("current_residence", "")).strip()
        if spanish:
            return f"¿Cómo se siente la vida en {place} ahora?" if place else "¿Cómo se siente tu vida ahora?"
        return f"What does life in {place} feel like for you now?" if place else "What does life feel like for you now?"
    if field_key == "current_work":
        employer = str(seeded_facts.get("current_work", "")).strip()
        if spanish:
            return f"¿Qué ha significado tu tiempo en {employer}?" if employer else "¿Qué ha significado tu trabajo?"
        return f"What has your time at {employer} been like?" if employer else "What has your work been like?"
    if field_key == "parent_alive":
        if spanish:
            return "¿Qué ha significado mantener ese vínculo con tu madre todos estos años?"
        return "What has it meant to still have that connection with your mother all these years?"
    if spanish:
        return "Cuéntame algo más de eso."
    return "Tell me more about that."


# ── Combined application ─────────────────────────────────────────────────


# ── Sensory-pivot-on-chain guard ──────────────────────────────────────────
#
# BUG-LORI-FACTUAL-OVER-SENSORY-PROBE-01 (2026-07-02). Live evidence,
# 2019 France/Italy canary T6 with the strengthened FACTUAL_CHAIN
# directive ACTIVE: Lori still replied "What was your impression of
# the city's atmosphere and historic buildings...". This repo's locked
# lesson (2026-05-02 Patch B) holds: prompt directives do not reliably
# constrain this LLM — deterministic post-LLM enforcement does. This
# guard is the enforcement layer for the chain-turn sensory ban. The
# detection vocabulary is imported from factual_chain_capture so the
# directive, this guard, and the harness F4 row grade the SAME regex.


def detect_sensory_pivot_on_chain(
    assistant_text: str,
    is_factual_chain: bool,
) -> bool:
    """Return True when the narrator turn was a factual chain and
    Lori's reply pivots to sensory/atmosphere/feeling vocabulary."""
    if not is_factual_chain:
        return False
    if not assistant_text or not assistant_text.strip():
        return False
    try:
        from .factual_chain_capture import _SENSORY_PROBE_RX
    except Exception:
        return False
    return bool(_SENSORY_PROBE_RX.search(assistant_text))


_SENSORY_PIVOT_REPAIR_EN_NEUTRAL = (
    "Let's stay with the sequence. What happened next?"
)
_SENSORY_PIVOT_REPAIR_ES_NEUTRAL = (
    "Sigamos con los hechos. ¿Qué pasó después?"
)


def repair_sensory_pivot(
    narrator_anchors: Optional[Sequence[str]] = None,
    target_language: str = "en",
) -> str:
    """Deterministic factual continuation for a chain turn. Echoes up
    to three narrator anchors (satisfies the anchor-echo contract) and
    asks exactly one next-factual-link question. Contains no sensory
    vocabulary by construction."""
    tl = (target_language or "en").lower()
    if tl.startswith("es"):
        return _SENSORY_PIVOT_REPAIR_ES_NEUTRAL

    cleaned: List[str] = []
    for a in narrator_anchors or []:
        if not a:
            continue
        s = str(a).strip()
        if s and s not in cleaned:
            cleaned.append(s)
        if len(cleaned) >= 3:
            break
    if not cleaned:
        return _SENSORY_PIVOT_REPAIR_EN_NEUTRAL
    if len(cleaned) == 1:
        return (
            f"You were taking me through {cleaned[0]}. "
            f"What came next?"
        )
    if len(cleaned) == 2:
        anchor_text = f"{cleaned[0]} and {cleaned[1]}"
    else:
        anchor_text = f"{cleaned[0]}, {cleaned[1]}, and {cleaned[2]}"
    return (
        f"You were taking me through {anchor_text} — I want to keep "
        f"that order straight. What came next after {cleaned[-1]}?"
    )


# ── BUG-LORI-TRIP-PHOTO-VISIBLE-LEAKS-01 (B): anti-echo guard ─────────────
# Live evidence 2026-07-09: narrator said "It was May 14 fathers day
# there"; Lori replied "It was May 14 fathers day there... What does that
# day mean to you now?" — parroting the whole narrator turn. Reflection
# discipline reflects ONE anchor, never the full utterance. Detection
# requires the narrator turn (>=4 words) to appear substantially inside
# the reply, so legitimate short-anchor reflections never trip it.

_ECHO_MIN_NARRATOR_WORDS = 4


def _norm_tokens(text: str) -> List[str]:
    return re.findall(r"[a-z0-9']+", str(text or "").lower())


def detect_narrator_echo(assistant_text: str, narrator_text: str) -> bool:
    """True when the reply substantially repeats the narrator's turn:
    the normalized narrator text appears verbatim inside the reply, OR
    the reply's first sentence is a near-copy (>=85% of the narrator's
    tokens, similar length)."""
    n_toks = _norm_tokens(narrator_text)
    if len(n_toks) < _ECHO_MIN_NARRATOR_WORDS:
        return False
    a_norm = " ".join(_norm_tokens(assistant_text))
    if not a_norm:
        return False
    if " ".join(n_toks) in a_norm:
        return True
    first_sent = re.split(r"[.!?\u2026]", str(assistant_text or ""), 1)[0]
    s_toks = _norm_tokens(first_sent)
    if not s_toks:
        return False
    overlap = len(set(n_toks) & set(s_toks)) / float(len(set(n_toks)))
    return overlap >= 0.85 and len(s_toks) <= len(n_toks) + 3


def repair_narrator_echo(
    assistant_text: str, narrator_text: str, target_language: str = "en",
) -> str:
    """Drop the echoed sentence; keep a substantive non-echo question if
    one survives, else a deterministic grounded continuation. Never
    invents facts, never claims image vision."""
    n_norm = " ".join(_norm_tokens(narrator_text))
    kept: List[str] = []
    for sent in re.split(r"(?<=[.!?])\s+|(?<=\u2026)\s*", str(assistant_text or "")):
        s_norm = " ".join(_norm_tokens(sent))
        if not s_norm:
            continue
        if n_norm and (n_norm in s_norm or s_norm in n_norm):
            continue  # the echo itself
        kept.append(sent.strip())
    remainder = " ".join(kept).strip()
    if len(_norm_tokens(remainder)) >= 4:
        return remainder
    if str(target_language or "en").lower().startswith("es"):
        return "Lo tengo. ¿Qué recuerdas de lo que había a tu alrededor?"
    return "I\u2019ve got that. What do you remember seeing around you?"


def apply_response_guards(
    assistant_text: str,
    narrator_text: str = "",
    recent_narrator_turns: Sequence[str] = (),
    target_language: str = "en",
    seeded_facts: Optional[dict] = None,
    surface: str = "narrator",
    narrator_anchors: Optional[Sequence[str]] = None,
    is_factual_chain: bool = False,
) -> Tuple[str, List[str]]:
    """Apply all guards in order. Language drift is checked first
    (a Spanish drift response will also fail the dangling-determiner
    check meaninglessly; replace whole response). Returns
    (final_text, list of guard names that fired).

    `seeded_facts` (optional) is a dict from field_key to value. When
    provided, the seeded-fact intake-question guard runs after the
    meta-leak guard and before the dangling-determiner check.

    `surface` (default "narrator") names the conversational surface
    the reply is being delivered on. DOC-LORI-RESPONSE-GUARDS-TRIP-
    SURFACE-STALE-COMMENT-01 (2026-07-07): the drift repair is ACTIVE
    on EVERY surface — the skip set is EMPTY. The earlier trip-surface
    skip (2026-06-24) was retired on 2026-07-02 when the two-tier
    looks_spanish detector fixed the European place-name false
    positives at the detector level (see module header, ~L97). Do NOT
    reintroduce a trip skip here; guard behavior is tuned in the
    detector, not by exempting surfaces.
    """
    fired: List[str] = []
    text = assistant_text or ""

    _drift_repair_active = (
        surface not in _SURFACES_WITHOUT_LANGUAGE_DRIFT_REPAIR
    )
    if (
        _drift_repair_active
        and detect_language_drift(text, narrator_text, recent_narrator_turns)
    ):
        text = repair_language_drift(
            target_language, anchors=narrator_anchors,
        )
        fired.append("language_drift")
        return text, fired

    # BUG-LORI-META-RESPONSE-LEAK-01: strip prompt-compliance preamble/
    # postamble before any further validation. Run BEFORE dangling-
    # determiner because the leak preamble often produces a quoted
    # draft that itself may end in determiner; we want to grade the
    # recovered draft, not the wrapper.
    if detect_meta_response_leak(text):
        text = repair_meta_response_leak(text, target_language)
        fired.append("meta_response_leak")
        # Recovered text still needs the rest of the checks.

    # BUG-LORI-TRIP-PHOTO-VISIBLE-LEAKS-01 (B): a reply that parrots the
    # narrator's whole turn is blocked and replaced with a grounded
    # continuation (or its own surviving non-echo question).
    if detect_narrator_echo(text, narrator_text):
        text = repair_narrator_echo(text, narrator_text, target_language)
        fired.append("narrator_echo")
        return text, fired

    # WO-SPANISH-LIVE-READINESS-01 Patch 2 (2026-06-17): broken Spanish/
    # English code-mix guard. Mid-generation drift produces "Tú had..."
    # or "Capté Santa Fe y David. ¿Qué pasó después?" — the narrator
    # should never see this. We can't safely auto-repair (the LLM has
    # already lost the thread), so we substitute a short deterministic
    # continuation prompt in the target language. Run AFTER meta-leak
    # so quoted-draft recovery gets its chance first; if the recovered
    # draft itself is broken code-mix, this still catches it.
    code_mix_marker = detect_broken_code_mix(text)
    if code_mix_marker:
        text = repair_broken_code_mix(text, target_language)
        fired.append("broken_code_mix")
        return text, fired

    # BUG-LORI-ASKS-WHAT-OPERATOR-SEEDED-01: rewrite seeded-fact intake
    # questions to lived-experience equivalents.
    if seeded_facts:
        matched_field = detect_seeded_fact_intake(text, seeded_facts)
        if matched_field:
            text = repair_seeded_fact_intake(
                matched_field, seeded_facts, target_language,
            )
            fired.append("seeded_fact_intake")
            return text, fired

    # BUG-LORI-FACTUAL-OVER-SENSORY-PROBE-01: on factual-chain turns,
    # a sensory/atmosphere pivot is replaced with a deterministic
    # anchor-echoing factual continuation. Runs after the whole-text
    # replacement guards above (their repairs are factual by
    # construction) and before dangling-determiner (this repair never
    # dangles).
    if detect_sensory_pivot_on_chain(text, is_factual_chain):
        text = repair_sensory_pivot(narrator_anchors, target_language)
        fired.append("sensory_pivot_on_chain")
        return text, fired

    if detect_dangling_determiner(text):
        text = repair_dangling_determiner(target_language)
        fired.append("dangling_determiner")
        return text, fired

    return text, fired


__all__ = [
    "detect_language_drift",
    "repair_language_drift",
    "detect_meta_response_leak",
    "detect_narrator_echo",
    "repair_narrator_echo",
    "repair_meta_response_leak",
    "strip_meta_response_leak",
    "sanitize_lori_response",
    "detect_broken_code_mix",
    "repair_broken_code_mix",
    "is_valid_name_confirmation_candidate",
    "detect_seeded_fact_intake",
    "repair_seeded_fact_intake",
    "detect_dangling_determiner",
    "repair_dangling_determiner",
    "detect_sensory_pivot_on_chain",
    "repair_sensory_pivot",
    "apply_response_guards",
]
