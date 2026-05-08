"""BUG-ML-LORI-SPANISH-PERSPECTIVE-01 — post-LLM Spanish output guards.

Two repair passes for Lori's Spanish output:

  1. PERSPECTIVE GUARD — when the narrator says "mi abuela" / "mi mamá"
     / "mi papá" etc. and Lori reflects with "Mi abuela" / "Mi mamá"
     / "Mi papá" (claiming the narrator's family as her own), rewrite
     to "Tu abuela" / "Tu mamá" / "Tu papá".  Quote-safe: text inside
     Spanish quotation marks (« », " ", '' '') is preserved verbatim
     because that's an explicit narrator quote, not Lori's own
     reflection.

  2. FRAGMENT GUARD — Spanish sentences that end on a connector word
     ("su", "que", "cuando", "después de que", etc.) are dangling
     fragments. Live evidence 2026-05-07: "después de que su." mid-
     stream truncation. Repair by trimming the trailing connector
     and ending the sentence cleanly with a period.

Architectural posture matches the existing era-fragment-repair guard
in chat_ws.py:
  - Pure post-LLM repair (no LLM re-call)
  - Idempotent (running twice produces the same result as once)
  - Quote-safe (preserves narrator quotes verbatim)
  - English passthrough (no-op when input lacks Spanish indicators)
  - Failure is non-fatal (returns the input unchanged on any error)

Public surface:

    apply_spanish_guards(lori_text, narrator_text=None) ->
        (repaired_text, list[str] of changes_applied)

The narrator_text arg is optional context; when provided, the
perspective guard cross-references narrator's "mi X" usage to
ensure Lori's "Mi X" is mirroring the narrator's relation rather
than referring to her own (which she shouldn't have anyway, but
the cross-reference adds defense in depth).
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple


# ── Spanish detection ────────────────────────────────────────────────────────

# Lightweight: Spanish-specific characters or common function words.
# Doesn't try to be a full language detector — the guards are no-ops
# on text that doesn't look Spanish, so a few false-negatives just
# mean the guard doesn't fire on a Spanish text without these markers
# (acceptable trade-off vs. firing on English text and breaking it).
_SPANISH_CHARS_RX = re.compile(r"[áéíóúñ¿¡]", re.IGNORECASE)

# Function-word list extended for the no-accent fallback path.
# Whisper output sometimes drops accents AND markers like ¿/¡, so a
# short Spanish reflection (e.g. "Las tardes con tu abuela cuando")
# might have zero accents but still be unambiguously Spanish.
# Coverage focused on: articles, pronouns, prepositions, common
# verbs, common adverbs/connectors. "no" / "se" / "no" are excluded
# because they're high-overlap with English and would produce false
# positives.
_SPANISH_FUNCTION_WORDS = (
    # articles
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    # prepositions
    "de", "del", "al", "en", "con", "para", "por", "hacia", "desde",
    "sin", "sobre", "entre", "según",
    # conjunctions
    "y", "o", "u", "pero", "porque", "aunque", "cuando", "mientras",
    # pronouns / possessives / demonstratives
    "tu", "tus", "su", "sus", "mi", "mis",
    "yo", "tú", "él", "ella", "nosotros", "ellos", "ellas",
    "este", "esta", "estos", "estas", "ese", "esa", "esos", "esas",
    "aquel", "aquella", "aquellos", "aquellas", "eso", "esto", "aquello",
    # common verb forms
    "es", "son", "fue", "era", "eran", "hay", "había", "está", "estaba",
    "tiene", "tuvo", "ser", "estar",
    # common adverbs / Q-words
    "que", "qué", "como", "cómo", "donde", "dónde", "cuando", "cuándo",
    "porque", "muy", "más", "menos", "también", "ya",
)
_SPANISH_FUNCTION_RX = re.compile(
    r"\b(?:" + "|".join(_SPANISH_FUNCTION_WORDS) + r")\b",
    re.IGNORECASE,
)


def looks_spanish(text: str) -> bool:
    """Heuristic Spanish detection. Used to gate the guards so they
    don't accidentally fire on English text containing the bigram
    'mi mom' or similar.

    A response is considered Spanish if EITHER:
      - contains any of á/é/í/ó/ú/ñ/¿/¡  (definitive — accent path)
      - contains ≥2 distinct Spanish function words AND no obvious
        English-only signals  (heuristic — no-accent path covers
        Whisper-degraded output)

    Threshold lowered from 3 to 2 (2026-05-07): real Lori reflections
    are often short ("Las tardes con tu abuela cuando.") and only hit
    2-3 Spanish function words even on unambiguously Spanish text.
    """
    if not text:
        return False
    if _SPANISH_CHARS_RX.search(text):
        return True
    fn_word_hits = set(m.group(0).lower() for m in _SPANISH_FUNCTION_RX.finditer(text))
    return len(fn_word_hits) >= 2


# ── Quote span detection (skip-region for repair guards) ─────────────────────

# Match Spanish quotation styles + plain double/single quotes.
# Uses non-greedy capture so consecutive quoted spans don't merge.
_QUOTE_SPAN_RX = re.compile(
    r"«[^»]*»|"          # «...»  (Spanish typographic)
    r"“[^”]*”|"  # "..."  (curly double)
    r"‘[^’]*’|"  # '...'  (curly single)
    r'"[^"]*"|'          # "..."  (ASCII double)
    r"'[^']*'"           # '...'  (ASCII single)
)


def _quote_span_indices(text: str) -> List[Tuple[int, int]]:
    """Return list of (start, end) tuples for spans inside quotation
    marks. The repair guards skip any match whose start position falls
    inside one of these spans — that's narrator-quoted content that
    must stay verbatim per the SPANISH PERSPECTIVE RULE exception.
    """
    return [(m.start(), m.end()) for m in _QUOTE_SPAN_RX.finditer(text)]


def _index_in_quote(idx: int, spans: List[Tuple[int, int]]) -> bool:
    return any(s <= idx < e for s, e in spans)


# ── Perspective guard ───────────────────────────────────────────────────────

# Spanish kinship / relation nouns Lori might appropriate.  Sorted
# longest-first so the regex prefers "abuelita" over "abuela" when
# both could match.  Diminutive + possessive variants accepted.
_REL_NOUNS_ES = (
    # grandparents
    "abuelita", "abuelito", "abuela", "abuelo",
    # parents
    "mamita", "mamá", "mama", "madre", "mami",
    "papito", "papá", "papa", "padre", "papi",
    # siblings
    "hermana", "hermano", "hermanita", "hermanito",
    # extended
    "tía", "tia", "tío", "tio", "prima", "primo",
    "sobrina", "sobrino", "madrina", "padrino", "comadre", "compadre",
    # spouse
    "esposa", "esposo", "marido", "mujer", "pareja",
    # children
    "hija", "hijo", "hijita", "hijito", "niña", "nina", "niño", "nino",
    "chamaca", "chamaco",
)
_REL_GROUP = "|".join(sorted(_REL_NOUNS_ES, key=len, reverse=True))

# Capture form: "Mi abuela" at sentence start OR after period/exclam.
# The capital M is required — lowercase "mi" inside narrator quotes
# is already inside a quote span and gets skipped at the next layer.
# Singular form first; plural form ("Mis hermanos") handled in a
# separate pass to keep the rewrite rule simple.
_PERSPECTIVE_SINGULAR_RX = re.compile(
    r"(?<![\wÁÉÍÓÚÑáéíóúñ])M[iI]\s+(" + _REL_GROUP + r")\b"
)

# Plural form: "Mis hermanos", "Mis padres", "Mis hijos"
_REL_NOUNS_ES_PLURAL = (
    "hermanos", "hermanas", "padres", "tíos", "tios", "tías", "tias",
    "primos", "primas", "sobrinos", "sobrinas", "hijos", "hijas",
    "niños", "ninos", "niñas", "ninas", "abuelos", "abuelas",
    "padrinos", "madrinas", "compadres", "comadres",
)
_REL_PLURAL_GROUP = "|".join(sorted(_REL_NOUNS_ES_PLURAL, key=len, reverse=True))
_PERSPECTIVE_PLURAL_RX = re.compile(
    r"(?<![\wÁÉÍÓÚÑáéíóúñ])M[iI][sS]\s+(" + _REL_PLURAL_GROUP + r")\b"
)


def _narrator_used_relation(narrator_text: Optional[str], relation: str) -> bool:
    """Did the narrator use 'mi <relation>' (case-insensitive) in
    their recent text? Used as a defense-in-depth check — if Lori
    says "Mi abuela" but the narrator never mentioned an abuela, we
    don't want to flip Lori's reference (which she shouldn't have
    in the first place, but the cross-check guards against false-
    positive rewrites).
    """
    if not narrator_text:
        # Without narrator context, default to repairing aggressively.
        # Lori has no business saying "Mi abuela" in interview mode
        # regardless of narrator content.
        return True
    rel_lower = relation.lower()
    # Find "mi <relation>" or "mis <plural-of-relation>" in narrator text
    pattern = re.compile(
        r"\bm[iI][sS]?\s+" + re.escape(rel_lower) + r"\b",
        re.IGNORECASE,
    )
    return bool(pattern.search(narrator_text))


def repair_spanish_perspective(
    lori_text: str,
    narrator_text: Optional[str] = None,
) -> Tuple[str, List[str]]:
    """Rewrite "Mi <relation>" → "Tu <relation>" in Spanish reflections.
    Quote-safe: matches inside quotation spans are preserved.

    Returns (repaired_text, list_of_changes_applied).
    """
    if not lori_text or not looks_spanish(lori_text):
        return (lori_text or "", [])

    spans = _quote_span_indices(lori_text)
    changes: List[str] = []

    def _replace_singular(m: re.Match) -> str:
        if _index_in_quote(m.start(), spans):
            return m.group(0)  # quote-safe — preserve narrator's verbatim quote
        relation = m.group(1)
        if not _narrator_used_relation(narrator_text, relation):
            return m.group(0)
        # Preserve the M case the model used (Mi vs MI) → Tu vs TU
        original = m.group(0)
        first_char = original[0]
        if first_char == "M":
            replacement = "Tu " + relation
        elif first_char == "m":
            replacement = "tu " + relation
        else:
            replacement = "Tu " + relation
        changes.append(f"perspective_singular:{original.strip()}→{replacement.strip()}")
        return replacement

    def _replace_plural(m: re.Match) -> str:
        if _index_in_quote(m.start(), spans):
            return m.group(0)
        relation = m.group(1)
        if not _narrator_used_relation(narrator_text, relation):
            return m.group(0)
        original = m.group(0)
        first_two = original[:2]
        if first_two[0] == "M":
            replacement = ("Tus " if first_two[1] in "iI" else "TUS ") + relation
        else:
            replacement = "tus " + relation
        changes.append(f"perspective_plural:{original.strip()}→{replacement.strip()}")
        return replacement

    repaired = _PERSPECTIVE_SINGULAR_RX.sub(_replace_singular, lori_text)
    # After span indices have been computed against ORIGINAL text, we
    # need to recompute spans for the plural pass since the singular
    # pass may have changed string length. Recompute against the
    # singular-pass result.
    if changes:
        spans = _quote_span_indices(repaired)
    repaired = _PERSPECTIVE_PLURAL_RX.sub(_replace_plural, repaired)
    return (repaired, changes)


# ── Fragment guard ──────────────────────────────────────────────────────────

# Connector words / phrases that demand a following clause. A Spanish
# sentence ending on one of these is an incomplete fragment.
# Ordered longest-first so multi-word connectors are matched before
# their leading single-word components.
_FRAGMENT_CONNECTORS = (
    "después de que",
    "antes de que",
    "a pesar de que",
    "en cuanto a",
    "a través de",
    "de que",
    "por que",
    "porque",
    "cuando",
    "mientras",
    "donde",
    "que",
    "su",
    "sus",
    "el",
    "la",
    "los",
    "las",
    "un",
    "una",
    "de",
    "del",
    "al",
    "en",
    "y",
    "o",
    "pero",
)
_FRAGMENT_CONNECTORS_GROUP = "|".join(
    re.escape(c) for c in sorted(_FRAGMENT_CONNECTORS, key=len, reverse=True)
)

# Match a sentence-ending fragment: (start of sentence or end of prior
# sentence) ... (connector) (whitespace)? (period | end-of-string).
# We anchor on sentence end-points so we only catch the LAST sentence.
_FRAGMENT_TAIL_RX = re.compile(
    r"\b(" + _FRAGMENT_CONNECTORS_GROUP + r")\s*\.?\s*$",
    re.IGNORECASE,
)


def repair_spanish_fragment(lori_text: str) -> Tuple[str, List[str]]:
    """Detect and repair Spanish dangling-fragment endings.

    The repair: trim the trailing connector + any trailing punctuation
    and end the sentence cleanly with a period. We do NOT attempt to
    complete the fragment because we'd be inventing narrator content.
    Truncation is the conservative repair.

    Quote-safe: if the trailing fragment is inside quotation marks,
    leave it alone (narrator quote preservation).

    Returns (repaired_text, list_of_changes_applied).
    """
    if not lori_text or not looks_spanish(lori_text):
        return (lori_text or "", [])

    text = lori_text.rstrip()
    if not text:
        return (lori_text, [])

    # If the LAST character is part of a quote span at end-of-string,
    # skip — that's likely a narrator quote that legitimately ends
    # mid-thought.
    spans = _quote_span_indices(text)
    if spans and spans[-1][1] == len(text):
        return (lori_text, [])

    # If the last sentence ends with "?" or "!", it's a question or
    # exclamation — never a "dangling connector" issue.
    if text[-1] in "?!»":
        return (lori_text, [])

    m = _FRAGMENT_TAIL_RX.search(text)
    if not m:
        return (lori_text, [])

    # Extract the chunk before the fragment.
    pre_fragment = text[: m.start()].rstrip()

    # If trimming would leave nothing or nothing meaningful, skip.
    if len(pre_fragment) < 8:
        return (lori_text, [])

    # If the pre-fragment text already ends with punctuation, keep it
    # as-is (the fragment was the only remnant). Otherwise add a period.
    if pre_fragment[-1] in ".!?":
        repaired = pre_fragment
    else:
        repaired = pre_fragment + "."

    # Preserve trailing whitespace pattern from original
    trailing_ws = lori_text[len(text):]
    repaired_with_ws = repaired + trailing_ws

    return (
        repaired_with_ws,
        [f"fragment_trim:{m.group(0).strip()!r}→removed"],
    )


# ── Public entry point ──────────────────────────────────────────────────────


def apply_spanish_guards(
    lori_text: str,
    narrator_text: Optional[str] = None,
) -> Tuple[str, List[str]]:
    """Run perspective + fragment guards in sequence.

    Idempotent: running twice on the same input produces the same
    output as running once. Failure is non-fatal — returns the input
    unchanged with an error tag in the changes list.

    Returns (repaired_text, list_of_changes_applied).
    """
    if not lori_text:
        return ("", [])
    try:
        all_changes: List[str] = []
        repaired, changes_p = repair_spanish_perspective(lori_text, narrator_text)
        all_changes.extend(changes_p)
        repaired, changes_f = repair_spanish_fragment(repaired)
        all_changes.extend(changes_f)
        return (repaired, all_changes)
    except Exception as exc:
        return (lori_text, [f"error:{exc!r}"])


__all__ = [
    "looks_spanish",
    "repair_spanish_perspective",
    "repair_spanish_fragment",
    "apply_spanish_guards",
]
