"""WO-LORI-REFLECTION-01 — Memory Echo Before Question (validator only).

LAW-3 isolation: this module imports zero extraction-stack code. Pure
functions only. Never calls an LLM. Never mutates assistant_text — it
only classifies whether a turn's echo is grounded in narrator content.

Per the §6 architecture in WO-LORI-REFLECTION-01_Spec:
    atomicity is structure  → deterministic rewrite (truncate) is safe
    reflection is content   → deterministic rewrite is unsafe
                              (would invent narrator facts)
So this validator emits failure labels; chat_ws logs them; harness
records them. The composer-side Layer 1 directive does the real work.

Public API:

    validate_memory_echo(assistant_text, user_text)
        → (passed: bool, failure_labels: list[str])

Six failure labels (per §5 of the spec):
    missing_memory_echo
    echo_too_long
    echo_not_grounded
    echo_contains_archive_language
    echo_contains_diagnostic_language
    echo_contains_unstated_emotion
"""
from __future__ import annotations

import re
from typing import List, Set, Tuple


# Maximum word count for the echo span (text before the first question
# stem). 25 words per §3 of the spec.
ECHO_WORD_BUDGET = 25

# Question-stem regex used to split assistant_text into:
#   echo_span        — content before the first question stem
#   question_span    — the question itself
#
# BUG-LORI-REFLECTION-01 (2026-05-02): boundary widened from `[.!?]\s+`
# to `[.!?,]\s+` so a comma-led inversion ("..., did you find that...")
# is recognized as a question stem. Pre-patch, the comma blocked the
# stem detection, the whole turn was treated as echo span, and turns
# like turn_04 (golfball-comm-control-rerun 2026-05-01) tripped
# echo_too_long from the inflated word count.
_QUESTION_STEM_RX = re.compile(
    r"(?:^|[.!?,]\s+)"
    r"(?P<stem>"
    r"\b(?:what|when|where|who|why|how|which|"
    r"did|do|does|were|was|is|are|am|"
    r"can|could|would|will|should|may|might|"
    r"tell\s+me|share|describe|walk\s+me\s+through)\b"
    r"[^?]*\?"
    r")",
    re.IGNORECASE,
)


# §5.4 — archive / agenda / extraction language. If any of these appears
# in the echo span, we flag echo_contains_archive_language.
_ARCHIVE_TOKENS_RX = re.compile(
    r"\b(?:"
    r"archive|archives|archived|"
    r"record|records|recorded|"
    r"database|"
    r"field|fields|"
    r"extract|extracts|extracted|extraction|"
    r"candidate|candidates|"
    r"for\s+our\s+records|"
    r"saving\s+that|"
    r"noting\s+that|"
    r"captured|capturing|"
    r"profile|profiles|"
    r"timeline|life\s+map|memoir"
    r")\b",
    re.IGNORECASE,
)


# §5.5 — diagnostic / clinical / overreaching interpretation. These are
# the patterns that turn a memory echo into therapy talk.
_DIAGNOSTIC_TOKENS_RX = re.compile(
    r"\b(?:"
    r"must\s+have\s+been|"
    r"must\s+have\s+felt|"
    r"sounds\s+like\s+(?:that|it|you|something)|"
    r"shaped\s+you|shape\s+you|"
    r"traumatic|trauma|"
    r"resilient|resilience|"
    r"coping|coped|"
    r"processing|processed|"
    r"deeply\s+(?:affected|painful|meaningful|moving)|"
    r"clearly\s+(?:affected|impacted|shaped)|"
    r"that\s+is\s+a\s+sign\s+of"
    r")\b",
    re.IGNORECASE,
)


# §5.6 — unstated-emotion affect tokens. If any of these appears in the
# echo span AND was NOT in the narrator's last message, we flag
# echo_contains_unstated_emotion. The narrator-was-affect-aware check
# happens in validate_memory_echo (whitelist user_text tokens).
_AFFECT_TOKENS_RX = re.compile(
    r"\b(?:"
    r"scared|scary|scaring|"
    r"lonely|loneliness|"
    r"happy|happiness|"
    r"sad|sadness|"
    r"proud|pride|"
    r"angry|anger|"
    r"hurt|hurts|hurting|"
    r"confused|confusion|"
    r"anxious|anxiety|"
    r"relieved|relief|"
    r"excited|excitement|"
    r"thrilling|thrilled|"
    r"painful|"
    r"joyful|joy|"
    r"frightened|frightening|"
    r"worried|worrying|worry|"
    r"lonely|loneliness"
    r")\b",
    re.IGNORECASE,
)


# Tokens that signal speculation about narrator's experience that goes
# beyond the literal facts they provided. Used by §5.3 echo_not_grounded.
_SPECULATION_TOKENS_RX = re.compile(
    r"\b(?:"
    r"possibly\s+because|"
    r"perhaps\s+because|"
    r"maybe\s+because|"
    r"i\s+imagine|"
    r"i\s+can\s+imagine|"
    r"it\s+seems\s+like|seemed\s+like|"
    r"sounds\s+like\s+(?:you|that|it)|"
    r"suggests\s+(?:that|you)"
    r")\b",
    re.IGNORECASE,
)


def _split_echo_and_question(text: str) -> Tuple[str, str]:
    """Return (echo_span, question_span). echo_span is everything before
    the first question stem; question_span starts at the stem. If no
    question stem found, the whole text is treated as echo (no question)."""
    if not text:
        return "", ""
    m = _QUESTION_STEM_RX.search(text)
    if not m:
        return text.strip(), ""
    stem_start = m.start("stem")
    return text[:stem_start].strip(), text[stem_start:].strip()


# BUG-LORI-REFLECTION-01 (2026-05-02): kinship canon for the grounding
# overlap check. When a narrator says "dad" and Lori echoes "father",
# the pre-patch validator counted that as ungrounded because the raw
# tokens differ. This narrow lookup canonicalizes ordinary kinship
# variants to their formal form before set-overlap, so the validator
# stops penalising paraphrase that any reasonable reader would accept.
#
# Scope is intentionally narrow — kinship only, validator-side only.
# This is NOT an extractor truth rule; the extractor never reads
# this map. A broader oral-history language canon (places, life-stage
# topics, household roles) is parked as WO-LORI-LANGUAGE-CANON-01.
_KINSHIP_CANON: dict = {
    "dad": "father", "daddy": "father", "papa": "father", "pop": "father",
    "mom": "mother", "mommy": "mother", "mama": "mother", "ma": "mother",
    "grandma": "grandmother", "granny": "grandmother", "nana": "grandmother",
    "grandpa": "grandfather", "gramps": "grandfather",
    "sis": "sister", "bro": "brother",
}


def _stem(tok: str) -> str:
    """BUG-LORI-REFLECTION-01 (2026-05-02): minimal stemmer for the
    grounding overlap check. Strips the four most common English
    inflectional suffixes (-ing, -ed, -es, -s) only when stripping
    leaves a stem of at least 3 chars. Conservative on purpose — does
    not collapse derivational morphology (worker → work would collapse
    too aggressively; -er stays). Lets "worked"/"working" both match
    "work" without invoking nltk or a real stemmer dependency."""
    if not tok:
        return tok
    for suf in ("ing", "ed", "es", "s"):
        if len(tok) > len(suf) + 2 and tok.endswith(suf):
            return tok[: -len(suf)]
    return tok


def _content_tokens(text: str) -> Set[str]:
    """Lowercase content tokens (3+ letters, non-stopword) used for
    grounding comparison. Conservative — we keep numbers and proper
    nouns lowercased for matching.

    BUG-LORI-REFLECTION-01 (2026-05-02): now applies _KINSHIP_CANON
    + _stem() before set-build. Caller does set overlap downstream;
    canonicalising here means both sides of the comparison see the
    same form. Order matters — canon BEFORE stem so we don't stem
    "dad" → "da" before the lookup misses."""
    if not text:
        return set()
    raw = re.findall(r"\b[a-zA-Z][a-zA-Z'\-]+\b", text.lower())
    # Tiny stopword list — focus on words that aren't load-bearing
    # for grounding ("the", "a", "you", etc don't help us tell whether
    # an echo is grounded).
    stopwords = {
        "the", "a", "an", "and", "or", "but", "of", "to", "in", "on",
        "at", "by", "for", "with", "as", "is", "are", "was", "were",
        "be", "been", "being", "am", "do", "does", "did", "have", "has",
        "had", "i", "you", "he", "she", "it", "we", "they", "me", "him",
        "her", "us", "them", "my", "your", "his", "their", "our", "its",
        "this", "that", "these", "those", "what", "when", "where", "why",
        "how", "who", "which", "if", "then", "so", "can", "could",
        "would", "will", "shall", "should", "may", "might", "must",
        "not", "no", "yes", "from", "up", "down", "out", "into", "over",
        "very", "really", "quite", "just", "also", "too", "now", "here",
        "there", "more", "less", "some", "any", "all", "much", "many",
    }
    out: Set[str] = set()
    for t in raw:
        # BUG-LORI-REFLECTION-01 (2026-05-02): strip possessive "'s"
        # and any trailing apostrophe BEFORE downstream lookup. The
        # \w+ regex above keeps apostrophes in-token ("father's"),
        # which then defeated _KINSHIP_CANON lookup AND tricked _stem
        # into stripping the trailing s and leaving "father'". The
        # narrator's "dad" + Lori's "father's" should both canonicalize
        # to "father" so the grounding overlap counts the kinship match.
        if t.endswith("'s") or t.endswith("’s"):
            t = t[:-2]
        elif t.endswith("'") or t.endswith("’"):
            t = t[:-1]
        if len(t) < 3 or t in stopwords:
            continue
        # 1. Kinship canonicalization (lookup BEFORE stemming so "dad"
        #    maps cleanly without becoming "da" first).
        canonical = _KINSHIP_CANON.get(t, t)
        # 2. Conservative stem (worked → work, sisters → sister, etc.).
        out.add(_stem(canonical))
    return out


def validate_memory_echo(
    assistant_text: str,
    user_text: str,
) -> Tuple[bool, List[str]]:
    """Validate the memory-echo discipline on a single assistant turn.

    Returns (passed, failure_labels). passed == not failure_labels.

    Edge cases:
      * empty assistant_text  → returns (True, []) — caller decides if
        empty turns are a separate problem (they are, but not this
        validator's lane)
      * empty user_text       → returns (True, []) — first-turn / no-prior
        case where requiring a grounded echo doesn't make sense
      * narrator gave a single-word answer (e.g. "yes" / "no") →
        echo_not_grounded would over-fire because there's nothing to
        anchor on; we relax: if user_text has < 5 content tokens,
        we skip the grounding check (still run the other 5)
    """
    if not assistant_text or not assistant_text.strip():
        return True, []

    echo_span, question_span = _split_echo_and_question(assistant_text)

    failures: List[str] = []

    # §5.1 missing_memory_echo
    # An assistant turn that has a question but no echo span — the LLM
    # jumped straight to the question without acknowledging anything.
    # Accepted iff there's no user_text to echo (first turn) OR the
    # turn has no question at all (rare).
    if question_span and not echo_span:
        if user_text and user_text.strip():
            failures.append("missing_memory_echo")

    # §5.2 echo_too_long
    if echo_span:
        word_count = len(echo_span.split())
        if word_count > ECHO_WORD_BUDGET:
            failures.append("echo_too_long")

    # §5.4 echo_contains_archive_language
    if echo_span and _ARCHIVE_TOKENS_RX.search(echo_span):
        failures.append("echo_contains_archive_language")

    # §5.5 echo_contains_diagnostic_language
    if echo_span and _DIAGNOSTIC_TOKENS_RX.search(echo_span):
        failures.append("echo_contains_diagnostic_language")

    # §5.6 echo_contains_unstated_emotion
    # Affect token in echo that is NOT in user_text.
    if echo_span:
        echo_affects = set(m.group(0).lower() for m in _AFFECT_TOKENS_RX.finditer(echo_span))
        if echo_affects:
            user_lower = (user_text or "").lower()
            unstated = []
            for affect in echo_affects:
                # Whitelist: if the narrator used the same root token,
                # echoing it back is grounded ("I felt lonely" → "you
                # felt lonely" passes).
                root = re.sub(r"(s|ed|ing|ness)$", "", affect)
                if root in user_lower or affect in user_lower:
                    continue
                unstated.append(affect)
            if unstated:
                failures.append("echo_contains_unstated_emotion")

    # §5.3 echo_not_grounded
    # Two signals: speculation tokens, OR most content tokens in the
    # echo span don't appear in user_text. Skip if user_text is too
    # thin to anchor against (< 5 content tokens).
    if echo_span and user_text and user_text.strip():
        user_tokens = _content_tokens(user_text)
        if len(user_tokens) >= 5:
            if _SPECULATION_TOKENS_RX.search(echo_span):
                failures.append("echo_not_grounded")
            else:
                echo_tokens = _content_tokens(echo_span)
                if echo_tokens:
                    overlap = echo_tokens & user_tokens
                    overlap_ratio = len(overlap) / len(echo_tokens)
                    # Conservative threshold: if < 30% of echo's content
                    # tokens are in user_text, the echo is drifting from
                    # what the narrator said.
                    if overlap_ratio < 0.30:
                        failures.append("echo_not_grounded")

    return (not failures), failures


__all__ = [
    "validate_memory_echo",
    "ECHO_WORD_BUDGET",
]
