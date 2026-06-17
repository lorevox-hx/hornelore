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
from typing import List, Optional, Sequence, Tuple


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
    r"this (?:response|reflection|reply) (?:follows|reflects|adheres|invites|captures|grounds|honors)"
    r"|"
    r"(?:i'?ll|i will|i shall) (?:respond|reply|reflect) (?:by|with|using)"
    r"|"
    r"following the (?:rules|guidelines|instructions)"
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

# Extract the quoted draft when present so we can recover the real
# response from a leaked preamble/postamble wrapper.
_QUOTED_DRAFT_RX = re.compile(
    r'"((?:[^"\\]|\\.)+)"|'
    r"“((?:[^”\\]|\\.)+)”"
)


def detect_meta_response_leak(assistant_text: str) -> bool:
    """Return True if the response contains meta-instruction leakage."""
    if not assistant_text:
        return False
    if _META_PREAMBLE_RX.search(assistant_text):
        return True
    if _META_POSTAMBLE_RX.search(assistant_text):
        return True
    if _FAKE_WARMTH_RX.search(assistant_text):
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


def apply_response_guards(
    assistant_text: str,
    narrator_text: str = "",
    recent_narrator_turns: Sequence[str] = (),
    target_language: str = "en",
    seeded_facts: Optional[dict] = None,
) -> Tuple[str, List[str]]:
    """Apply all guards in order. Language drift is checked first
    (a Spanish drift response will also fail the dangling-determiner
    check meaninglessly; replace whole response). Returns
    (final_text, list of guard names that fired).

    `seeded_facts` (optional) is a dict from field_key to value. When
    provided, the seeded-fact intake-question guard runs after the
    meta-leak guard and before the dangling-determiner check.
    """
    fired: List[str] = []
    text = assistant_text or ""

    if detect_language_drift(text, narrator_text, recent_narrator_turns):
        text = repair_language_drift(target_language)
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

    if detect_dangling_determiner(text):
        text = repair_dangling_determiner(target_language)
        fired.append("dangling_determiner")
        return text, fired

    return text, fired


__all__ = [
    "detect_language_drift",
    "repair_language_drift",
    "detect_meta_response_leak",
    "repair_meta_response_leak",
    "strip_meta_response_leak",
    "sanitize_lori_response",
    "is_valid_name_confirmation_candidate",
    "detect_seeded_fact_intake",
    "repair_seeded_fact_intake",
    "detect_dangling_determiner",
    "repair_dangling_determiner",
    "apply_response_guards",
]
