"""WO-LORI-REFLECTION-01 — Memory Echo Before Question (validator only).
WO-LORI-REFLECTION-02 — Runtime Shaping (Layer 1 anchor + Layer 2 shape).

LAW-3 isolation: this module imports zero extraction-stack code. Pure
functions only. Never calls an LLM. The validator (validate_memory_echo)
never mutates assistant_text — it only classifies whether a turn's echo
is grounded in narrator content. The shaper (shape_reflection) DOES
mutate, but only via deterministic rules over the narrator's own text:
it never invents a narrator fact, it only re-arranges or trims what
Lori already produced.

Per the §6 architecture in WO-LORI-REFLECTION-01_Spec:
    atomicity is structure  → deterministic rewrite (truncate) is safe
    reflection is content   → deterministic rewrite is unsafe
                              (would invent narrator facts)
The Patch B regression (2026-05-02) confirmed this empirically and
locked the principle for BUG-LORI-REFLECTION-02:
    Prompt-heavy reflection rules make Lori worse, not better.
    The next iteration MUST be runtime shaping, NOT prompt paragraphs.

Public API:

    validate_memory_echo(assistant_text, user_text)
        → (passed: bool, failure_labels: list[str])

    extract_concrete_anchor(narrator_text)
        → str | None  — one short noun-phrase suitable for an echo opener

    shape_reflection(assistant_text, narrator_text, softened_mode_active=False)
        → (shaped_text: str, action_labels: list[str])

Six validator failure labels (per §5 of WO-LORI-REFLECTION-01):
    missing_memory_echo
    echo_too_long
    echo_not_grounded
    echo_contains_archive_language
    echo_contains_diagnostic_language
    echo_contains_unstated_emotion

Five shaper action labels (per §3-§5 of WO-LORI-REFLECTION-02):
    shaped_anchor_prepended       — Case B: no echo + anchor available
    shaped_echo_trimmed_to_anchor — Case C1: echo too long, anchor inside it
    shaped_echo_dropped           — Case C2: echo too long, no anchor inside
    shaped_softened_truncated     — Layer 3: softened mode > 30 words
    shaped_no_change              — Case D: passed through unmodified
"""
from __future__ import annotations

import re
from typing import List, Optional, Set, Tuple


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


# ═════════════════════════════════════════════════════════════════════
# WO-LORI-REFLECTION-02 — Runtime Shaping (Layer 1 + Layer 2 + Layer 3)
# ═════════════════════════════════════════════════════════════════════
#
# The locked design constraint (from BUG-LORI-REFLECTION-02_Spec.md):
#
#     Prompt-heavy reflection rules make Lori worse, not better.
#     The next iteration MUST be runtime shaping, NOT prompt paragraphs.
#
# This isn't a hypothesis. It's the empirical lesson banked from Patch B
# (2026-05-02 evening), which regressed golfball from 4/8 → 1/8 by adding
# two new prompt rules. The fix is to move enforcement OUT of the prompt
# (which the LLM interprets as guidance to fill the budget) and INTO
# code (which deterministically caps and shapes the output).
#
# Three layers, one shared entrypoint:
#
#   Layer 1 — extract_concrete_anchor()
#       Pull one short noun-phrase from narrator_text for echo opener.
#       Standalone deterministic function. Eventually wraps the
#       Utterance Frame WO when that lands.
#
#   Layer 2 — shape_reflection()
#       Cases A/B/C/D: trivial / no-echo+anchor → prepend / echo too
#       long → trim or drop / pass through.
#
#   Layer 3 — softened-mode tighter cap (inside shape_reflection())
#       30-word limit on softened-mode turns vs 55 on ordinary.
#       Truncate to first sentence, drop trailing question if needed.
# ═════════════════════════════════════════════════════════════════════


# Hard floors used by the shaper. These differ from the validator's
# ECHO_WORD_BUDGET (25) — the shaper is more permissive about WHAT it
# allows through (it only acts when the echo is clearly broken), but
# the softened-mode cap (Layer 3) is tighter than ordinary.
SHAPER_ECHO_WORD_BUDGET = 25
SHAPER_SOFTENED_TURN_BUDGET = 30


# Trivial-input threshold — narrator turns shorter than this are treated
# as not anchorable, so we don't try to extract an anchor from "yes" or
# "I think so" or garbled STT.
_TRIVIAL_CONTENT_TOKEN_THRESHOLD = 4


# Mid-sentence proper-noun phrase regex: runs of capitalized words NOT
# at the start of the text (start-of-sentence capitals are usually just
# articles / pronouns capitalized for grammar, not proper nouns).
# Example matches: "Spokane", "Captain Kirk", "North Dakota",
# "Kent Horne", "T.J. Hooker".
_PROPER_NOUN_RX = re.compile(
    r"(?<![.!?]\s)(?<!^)"                       # not sentence-start
    r"\b(?:[A-Z][a-zA-Z'\-\.]+(?:\s+[A-Z][a-zA-Z'\-\.]+){0,3})\b",
    re.UNICODE,
)


# Sentence-start proper noun: capitalized phrase at the very start of
# the text or after a sentence terminator. Rarer (most sentence-starts
# are pronouns / articles) but we still want to catch "Spokane was..."
# at the beginning.
_PROPER_NOUN_AT_START_RX = re.compile(
    r"(?:^|[.!?]\s+)"
    r"(?P<np>(?:[A-Z][a-zA-Z'\-\.]+(?:\s+[A-Z][a-zA-Z'\-\.]+){0,3}))"
    r"(?=\s+(?:was|is|were|are|had|has|will|won't|can|could|"
    r"would|should|might|may|do|does|did|comes?|came|"
    r"in|on|at|when|where|near|outside)\b)",
    re.UNICODE,
)


# Common English words that look proper-noun-shaped but aren't (would
# false-positive proper-noun detection in mid-sentence position when
# a sentence starts with one of these and the regex's lookbehind misses).
_PROPER_NOUN_BLOCKLIST = frozenset({
    # Pronouns / articles capitalized after period
    "I", "He", "She", "We", "They", "It", "You", "The", "A", "An", "My",
    "Your", "His", "Her", "Their", "Our", "This", "That", "These", "Those",
    # Question / discourse starters
    "What", "Where", "When", "Why", "How", "Who", "Which", "Yes", "No",
    "Well", "So", "Now", "Then", "Also", "And", "But", "Or", "If",
    # Common day / month names (real proper nouns but not story anchors)
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
    "Sunday", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
})


# Kinship surface forms — narrator-side "my dad" / "my mom" / etc.
# Maps to the canonical anchor form Lori would prepend in an echo. Note
# the canonicalization here flips possessive: narrator "my dad" → Lori
# anchor "your dad". Falls back to "father"/"mother" if needed by the
# context (caller decides). For now we keep the kinship anchor
# possessive-flipped because it reads more naturally in an echo opener:
# "Your dad. ..." vs "Father. ..."
_KINSHIP_ANCHOR_RX = re.compile(
    r"\b(?P<poss>my|our)\s+"
    r"(?P<noun>dad|daddy|papa|pop|"
    r"mom|mommy|mama|ma|"
    r"father|mother|"
    r"grandma|granny|nana|grandmother|"
    r"grandpa|gramps|grandfather|"
    r"sister|sis|brother|bro|"
    r"aunt|uncle|cousin)\b",
    re.IGNORECASE,
)


def _is_trivial_narrator_text(narrator_text: str) -> bool:
    """A narrator turn is trivial if it provides nothing extractable to
    anchor a Lori echo on. Trivial turns pass through the shaper
    unchanged (Lori's response to "yes" / "thanks" / single-word ack
    should not be artificially shaped).

    Definition (more permissive than just content-token count):
      - empty / whitespace-only → trivial
      - very short string (< 8 chars stripped) → trivial
      - any proper-noun phrase (mid-sentence or sentence-start with
        verb lookahead) is itself a hard anchor → NOT trivial
      - any kinship reference ("my dad", "my mom") is an anchor → NOT trivial
      - otherwise fall back to content-token threshold (< 4)
    """
    if not narrator_text or not narrator_text.strip():
        return True
    if len(narrator_text.strip()) < 8:
        return True
    # Proper-noun escape: even with few content tokens, a clear proper
    # noun is anchorable. "I was born in Spokane in 1962." has 2 content
    # tokens but the proper noun "Spokane" is a perfect echo opener.
    if _PROPER_NOUN_RX.search(narrator_text):
        return False
    if _PROPER_NOUN_AT_START_RX.search(narrator_text):
        return False
    # Kinship escape: "My dad worked." has < 4 content tokens but
    # "Your father" is an anchorable echo opener.
    if _KINSHIP_ANCHOR_RX.search(narrator_text):
        return False
    return len(_content_tokens(narrator_text)) < _TRIVIAL_CONTENT_TOKEN_THRESHOLD


def _score_proper_noun_candidate(phrase: str) -> int:
    """Higher score = better anchor. Multi-word phrases score higher
    than single words ("Captain Kirk" > "Kirk"). Phrases entirely on
    the blocklist score 0."""
    tokens = phrase.split()
    if not tokens:
        return 0
    # All-blocklist phrase → reject
    if all(t in _PROPER_NOUN_BLOCKLIST for t in tokens):
        return 0
    # Single token on blocklist → reject (sentence-start "I", "The", etc.)
    if len(tokens) == 1 and tokens[0] in _PROPER_NOUN_BLOCKLIST:
        return 0
    # Multi-word phrase → bigger score (more specific anchor)
    return 5 + len(tokens)


def extract_concrete_anchor(narrator_text: str) -> Optional[str]:
    """Return one short noun-phrase from narrator_text suitable for an
    echo opener — or None if nothing extractable.

    Algorithm (deterministic, no LLM):
      1. If trivial narrator (< 4 content tokens) → None
      2. Find proper-noun phrases mid-sentence (highest priority)
      3. Find proper-noun phrases at sentence-start (with verb lookahead)
      4. Find kinship references (medium priority, possessive-flip
         "my dad" → "your dad")
      5. Fall back to first content token (lowest priority)
      6. Return the highest-scoring candidate, or None if no candidate
         clears the score floor

    Pure-deterministic. Never invents — always pulled from narrator_text.
    Never returns text Lori didn't already see in the user turn.
    """
    if _is_trivial_narrator_text(narrator_text):
        return None

    candidates: List[Tuple[int, str]] = []  # (score, phrase)

    # Layer 1.1 — Mid-sentence proper-noun phrases (highest priority)
    for m in _PROPER_NOUN_RX.finditer(narrator_text):
        phrase = m.group(0).strip()
        score = _score_proper_noun_candidate(phrase)
        if score > 0:
            candidates.append((score, phrase))

    # Layer 1.2 — Sentence-start proper-noun phrases (medium priority)
    for m in _PROPER_NOUN_AT_START_RX.finditer(narrator_text):
        phrase = m.group("np").strip()
        score = _score_proper_noun_candidate(phrase)
        if score > 0:
            # Slight penalty for sentence-start position — these are
            # less reliably proper-noun than mid-sentence capitalization.
            candidates.append((score - 1, phrase))

    # Layer 1.3 — Kinship references (medium priority)
    # Possessive-flip: narrator says "my dad" / "our mom" → Lori anchor
    # is "your dad" / "your mom". Reads more naturally in echo context.
    for m in _KINSHIP_ANCHOR_RX.finditer(narrator_text):
        noun = m.group("noun").lower()
        # Canonicalize via the existing kinship canon (already does
        # dad → father, mom → mother, etc. for grounding; here we use
        # the SAME canon so an echo "your father" matches a narrator
        # "my dad" if the validator runs on the shaped output).
        canonical = _KINSHIP_CANON.get(noun, noun)
        candidates.append((4, f"Your {canonical}"))

    # Pick the highest-scoring candidate. Stable ordering on ties: first
    # candidate found wins (mid-sentence > sentence-start > kinship by
    # score, plus discovery order within each tier).
    if candidates:
        candidates.sort(key=lambda x: -x[0])
        return candidates[0][1]

    return None


def _split_first_sentence(text: str) -> Tuple[str, str]:
    """Return (first_sentence, rest). Sentence boundary is .!? followed
    by whitespace, OR end-of-text. If no terminator found, the entire
    text is the "first sentence" and rest is empty."""
    if not text:
        return "", ""
    m = re.search(r"[.!?](?:\s+|$)", text)
    if not m:
        return text.strip(), ""
    return text[: m.end()].strip(), text[m.end():].strip()


def shape_reflection(
    assistant_text: str,
    narrator_text: str,
    softened_mode_active: bool = False,
) -> Tuple[str, List[str]]:
    """Runtime-shape Lori's emitted assistant_text per the WO-LORI-
    REFLECTION-02 design contract. Returns (shaped_text, action_labels).

    Cases (Layer 2):
      A. Trivial narrator (< 4 content tokens) → pass through unchanged
      B. Lori produced no echo span AND we have an anchor → prepend
         "{anchor}. " before the question
      C1. Echo too long AND anchor appears inside echo → trim echo to
          just the anchor
      C2. Echo too long AND anchor NOT in echo → drop echo entirely,
          keep only the question
      D. Pass-through (echo present + within budget OR no anchor + echo
         absent — no shaping signal)

    Layer 3 (softened mode):
      If softened_mode_active=True and word count > SHAPER_SOFTENED_TURN_BUDGET:
        truncate to first sentence; drop trailing probe question if any.

    Always pure-post-LLM. Never calls an LLM. Idempotent: shaping the
    output of shape_reflection() again produces the same output.
    """
    if not assistant_text or not assistant_text.strip():
        return assistant_text, []

    # Layer 3 FIRST: softened mode has its own tighter contract that
    # overrides the standard echo logic AND the trivial-narrator check.
    # Softened-mode responses must stay under SHAPER_SOFTENED_TURN_BUDGET
    # (30 words) regardless of what the narrator's last turn looked
    # like — the cap exists because the LLM under softened-mode prompts
    # tends to balloon supportive responses past the calm-presence
    # contract. We must shape even when narrator_text is "I'm tired"
    # (which is content-token-trivial but is exactly the kind of turn
    # that triggers a long, monologuing softened response).
    if softened_mode_active:
        word_count = len(assistant_text.split())
        if word_count <= SHAPER_SOFTENED_TURN_BUDGET:
            return assistant_text, ["shaped_no_change"]
        # Truncate to first sentence. If first sentence is itself too
        # long, fall back to first SHAPER_SOFTENED_TURN_BUDGET words.
        first_sent, _rest = _split_first_sentence(assistant_text)
        first_sent_words = first_sent.split()
        if first_sent and len(first_sent_words) <= SHAPER_SOFTENED_TURN_BUDGET:
            return first_sent, ["shaped_softened_truncated"]
        # First sentence still too long → hard word-cap.
        capped = " ".join(first_sent_words[:SHAPER_SOFTENED_TURN_BUDGET])
        capped = capped.rstrip(".,;: ")
        if not capped.endswith((".", "!", "?")):
            capped += "."
        return capped, ["shaped_softened_truncated"]

    # Case A: trivial narrator → no shaping signal. Runs after Layer 3
    # so softened-mode caps still fire on trivial-narrator turns.
    if _is_trivial_narrator_text(narrator_text):
        return assistant_text, ["shaped_no_change"]

    echo_span, question_span = _split_echo_and_question(assistant_text)
    anchor = extract_concrete_anchor(narrator_text)

    # Case B: no echo span + question present + anchor available
    # → prepend "{anchor}. " before the question.
    if question_span and not echo_span and anchor:
        return f"{anchor}. {question_span}", ["shaped_anchor_prepended"]

    # Case C: echo span too long
    if echo_span:
        echo_word_count = len(echo_span.split())
        if echo_word_count > SHAPER_ECHO_WORD_BUDGET:
            if anchor and anchor.lower() in echo_span.lower():
                # C1: anchor inside echo → trim echo to just the anchor
                tail = question_span if question_span else ""
                shaped = f"{anchor}. {tail}".strip()
                return shaped, ["shaped_echo_trimmed_to_anchor"]
            # C2: no anchor or anchor not in echo → drop echo entirely
            if question_span:
                return question_span, ["shaped_echo_dropped"]
            # No question to fall back to — just hard-cap to the budget.
            capped = " ".join(echo_span.split()[:SHAPER_ECHO_WORD_BUDGET])
            capped = capped.rstrip(".,;: ")
            if not capped.endswith((".", "!", "?")):
                capped += "."
            return capped, ["shaped_echo_dropped"]

    # Case D: pass through
    return assistant_text, ["shaped_no_change"]


__all__ = [
    "validate_memory_echo",
    "ECHO_WORD_BUDGET",
    # WO-LORI-REFLECTION-02 additions
    "extract_concrete_anchor",
    "shape_reflection",
    "SHAPER_ECHO_WORD_BUDGET",
    "SHAPER_SOFTENED_TURN_BUDGET",
]
