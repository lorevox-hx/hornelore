"""WO-LORI-QUESTION-ATOMICITY-01 Layer 2 — deterministic atomicity filter.

LAW-3 isolation: this module imports zero extraction-stack code. Pure
functions only. Never calls an LLM. Never imports from
``api.routers.extract``, ``api.prompt_composer``, ``api.memory_echo``,
``api.routers.chat_ws``, or ``api.routers.llm_*``.

Architecture (per WO-LORI-QUESTION-ATOMICITY-01_Spec.md):

  * 6-category illegal-structure taxonomy:
      and_pivot / or_speculation / request_plus_inquiry / choice_framing
      / hidden_second_target / dual_retrieval_axis
  * Truncate-only enforcement — never rewrites or paraphrases
  * §5.1 truncation grammar guard — truncated output must end in '?',
    be valid imperative form, OR fall back to the original-text question
    clause if one exists. When in doubt, return original unchanged.

Public API:

    enforce_question_atomicity(text) -> tuple[str, list[str]]
        (possibly_truncated_text, list_of_failure_labels)

    classify_atomicity(text) -> list[str]
        list_of_failure_labels (no mutation; classification only)

Both functions return [] when text is empty or whitespace-only — the
caller decides how to handle missing assistant_text.
"""
from __future__ import annotations

import re
from typing import List, Tuple


# ──────────────────────────────────────────────────────────────────────────
# Regex inventory
# ──────────────────────────────────────────────────────────────────────────
#
# All patterns are case-insensitive. Each fires on its own dimension.
# Patterns that overlap (e.g. and_pivot vs hidden_second_target) both
# emit their labels — the truncation step uses the FIRST pivot it finds,
# but classification is exhaustive so the harness sees every signal.
#
# The patterns deliberately do NOT try to parse English — they look for
# specific surface forms that map to specific double-barreled structures.
# False positives are conservatively suppressed by requiring two distinct
# verb-bearing clauses on the and/or pivots (per §4.1 / §4.2 v1.1
# overfire guard).

# Verbs that indicate a clause has its own predicate. Used to validate
# that a "X, and Y" pivot has a real second clause (Y must contain a
# verb to count as a second predicate).
_VERB_TOKENS = (
    r"(?:was|were|is|are|am|been|being|"
    r"do|does|did|done|doing|"
    r"have|has|had|having|"
    r"can|could|will|would|shall|should|may|might|must|"
    r"go|goes|went|gone|going|"
    r"come|comes|came|coming|"
    r"see|sees|saw|seen|seeing|"
    r"feel|feels|felt|feeling|"
    r"think|thinks|thought|thinking|"
    r"know|knows|knew|known|knowing|"
    r"remember|remembers|remembered|remembering|"
    r"like|likes|liked|liking|"
    r"want|wants|wanted|wanting|"
    r"need|needs|needed|needing|"
    r"tell|tells|told|telling|"
    r"share|shares|shared|sharing|"
    r"talk|talks|talked|talking|"
    r"say|says|said|saying|"
    r"work|works|worked|working|"
    r"play|plays|played|playing|"
    r"live|lives|lived|living|"
    r"happen|happens|happened|happening|"
    r"affect|affects|affected|affecting|"
    r"change|changes|changed|changing|"
    r"shape|shapes|shaped|shaping|"
    r"drew|draws|drawn|drawing|"
    r"choose|chooses|chose|chosen|choosing|"
    r"move|moves|moved|moving|"
    r"matter|matters|mattered|mattering)"
)


# 4.1 and_pivot — TWO verb-bearing clauses joined by ", and"
# Pattern requires:
#   * first clause has a verb (a question stem like "What was..." satisfies)
#   * comma + and + (optional pronoun) + verb in second clause
#   * trailing '?'
# Conservative — bare "and how" without a verb-following structure is
# NOT enough; "X, and the kitchen smelled good" is NOT enough.
_AND_PIVOT_RX = re.compile(
    r"\b(what|when|where|who|why|how|which|did|do|does|were|was|is|are|can|could|would|will|tell|share)\b"
    r"[^?!.]*?"
    r",\s*and\s+"
    r"(?:you|he|she|it|they|i|we|"
    r"the|a|an|his|her|their|my|our|your|that|those|these|some|any|"
    r"what|how|why|when|where|who|did|do|does|is|are|was|were)?"
    r"\s*"
    r"[^?!.]*?"
    + _VERB_TOKENS +
    r"[^?!.]*?\?",
    re.IGNORECASE | re.DOTALL,
)


# 4.2 or_speculation — TWO verb-bearing clauses joined by ", or"
# Pattern requires the post-or clause to have its own verb (predicate),
# not just be a noun branch.
#
# CRITICAL overfire guard (v1.1): a yes/no question with "or X" branch
# where X reuses the SAME yes/no operator is NOT compound:
#   "Did your parents tell you why they chose to move ..., or was it a
#    bit of a mystery to you as a child?"  ← single yes/no, branch
# To distinguish, we require the second clause to contain a fresh
# predicate that's NOT just a yes/no aux of the first. Heuristic: the
# second clause must contain a wh-word or a content verb (not just
# is/was/were/are/am/be/been).
_OR_SPECULATION_RX = re.compile(
    r"\b(what|when|where|who|why|how|which|did|do|does|were|was|is|are|can|could|would|will|tell|share)\b"
    r"[^?!.]*?"
    r",\s*or\s+"
    # Post-or clause must contain a verb (any verb — be-verbs included
    # per 2026-04-30 review of golfball-v2-clean Turn 03 false-NEGATIVE
    # on "or were those nights a source of worry"). The two-predicate
    # rule still applies via the requirement that something verb-bearing
    # follows the comma.
    r"[^?!.]*?"
    r"\b(?:was|were|is|are|am|been|"
    r"do|does|did|have|has|had|"
    r"go|goes|went|come|comes|came|"
    r"see|sees|saw|feel|feels|felt|"
    r"think|thinks|thought|know|knows|knew|"
    r"remember|like|liked|want|wanted|need|needed|"
    r"tell|tells|told|share|shares|shared|"
    r"talk|talks|talked|say|says|said|"
    r"work|works|worked|play|plays|played|"
    r"live|lived|happen|happens|happened|"
    r"can|could|would|will|should|might|may|"
    r"affect|change|shape|matter|matters)\b"
    r"[^?!.]*?\?",
    re.IGNORECASE | re.DOTALL,
)


# 4.3 request_plus_inquiry — imperative followed by "and what/how/why"
# "Tell me more about Spokane and what happened next."
_REQUEST_PLUS_INQUIRY_RX = re.compile(
    r"\b(tell|share|describe|walk\s+me\s+through|talk\s+about|tell\s+me\s+about)\b"
    r"[^?!.]*?"
    r"\s+and\s+"
    r"(?:what|how|why|where|when|who|which|did|do|does|is|are|was|were)\b",
    re.IGNORECASE | re.DOTALL,
)


# 4.4 choice_framing — three or more comma-separated options before '?'
# "Did you feel proud, sad, or confused?"
# Conservative: needs at least 3 options (comma+comma OR comma+or-comma).
_CHOICE_FRAMING_RX = re.compile(
    r"(?:[A-Za-z][A-Za-z'\-]+)\s*,\s+"
    r"(?:[A-Za-z][A-Za-z'\-]+)\s*,\s+"
    r"(?:or\s+)?"
    r"(?:[A-Za-z][A-Za-z'\-]+)\s*\?",
    re.IGNORECASE,
)


# 4.5 hidden_second_target — two PROPER-NOUN tokens joined by "and"
# inside a single question. The classic case: two distinct place names
# ("Spokane and Montreal") or two named people that the narrator would
# need to retrieve from separate memory anchors.
#
# 2026-05-01 narrowing per WO-LORI-COMMUNICATION-CONTROL-01 negative
# tests: dropped the generic-relation branch (mom/dad/school/church/etc).
# Generic relation pairs like "mother and father" or "reading and
# writing" are conventionally single coordinated retrieval targets, not
# two separate memory anchors. The dual_retrieval_axis check still
# catches the real compound case (place + emotion / person + emotion /
# event + evaluation). This narrowing closes the false positive
# Chris's research-driven WO flagged in §8 negative tests.
_HIDDEN_SECOND_TARGET_PROPER_RX = re.compile(
    r"\b([A-Z][a-z]+)\s+and\s+([A-Z][a-z]+)\b"
    r"[^?!.]*?\?",
)


# 4.6 dual_retrieval_axis — single question, two retrieval systems
# "What do you remember about Spokane and how you felt?"
#
# Pattern: question contains a place/event/person token AND an affect
# token, joined by "and" or ", and". Conservative: only fires when the
# affect token comes AFTER the "and" (we don't want to trip on "Spokane
# and Montreal" — that's hidden_second_target's job).
_AFFECT_TOKENS = (
    r"(?:feel|feels|felt|feeling|"
    r"emotion|emotions|emotional|"
    r"mood|moods|"
    r"proud|scared|sad|happy|lonely|angry|"
    r"hurt|hurts|hurting|"
    r"anxious|relieved|confused|excited|"
    r"mean|means|meant|meaning|"
    r"affected|impacted|shaped|"
    r"difficult|painful|joyful|memorable|significant)"
)
_DUAL_RETRIEVAL_RX = re.compile(
    # Loose form: any text containing "and" then (any tokens) then an
    # affect token, all before the trailing '?'. The lazy ".*?" between
    # "and" and the affect anchor allows arbitrary intervening words
    # ("how you felt" / "what did it mean for the family" / "what did
    # it shape").
    r"[^?!.]*?"
    r"\band\s+"
    r"[^?!.]{0,80}?"
    r"\b" + _AFFECT_TOKENS + r"\b"
    r"[^?!.]*?\?",
    re.IGNORECASE | re.DOTALL,
)


# Question-stem regex used by the §5.1 truncation grammar guard to
# locate a complete question clause inside the original text when the
# naïve truncation produces a non-question artifact.
#
# CRITICAL: stem must be at clause boundary (start-of-string, after
# punctuation, or after a coordinator like "and"/"or"/"but"). Without
# this constraint, the regex matched modal verbs inside statements
# (e.g. "can" in "I can imagine that was thrilling, and what drew you"
# matched as a question stem, producing a wrong fallback clause).
_QUESTION_CLAUSE_RX = re.compile(
    r"(?:^|[.!?,;:]\s+|\s+(?:and|or|but)\s+)"
    r"(?P<clause>"
    r"\b(?:what|when|where|who|why|how|which|did|do|does|were|was|is|are|can|could|would|will)\b"
    r"[^?!.]*\?"
    r")",
    re.IGNORECASE,
)


# Imperative-form regex — "Tell me X." / "Share Y." / "Walk me through Z."
# Used by §5.1 to ACCEPT truncations that don't end in '?' but are valid
# request-form alternatives.
_IMPERATIVE_RX = re.compile(
    r"^\s*(tell\s+me|share|describe|walk\s+me\s+through|talk\s+about|"
    r"tell\s+me\s+about|let\s+me\s+know\s+about|"
    r"i'd\s+love\s+to\s+hear)\b",
    re.IGNORECASE,
)


# Pivot tokens used by truncation. The first pivot found in the text is
# where we cut. Order matters — we prefer ", and" / ", or" over bare
# " and " / " or " because the comma form is more reliable as a clause
# boundary.
_PIVOT_TOKENS = (
    ", and ", ", or ",
    " and what ", " and how ", " and why ", " and where ", " and when ",
    " and did ", " and do ", " and does ",
    " or was ", " or were ", " or did ", " or do ", " or does ",
    " or is ", " or are ", " or can ", " or could ",
)


# ──────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────

def classify_atomicity(text: str) -> List[str]:
    """Classification-only. Returns a list of failure labels, or []
    when the text is atomic.

    Multiple labels possible — and_pivot + dual_retrieval_axis can both
    fire on the same text. Order is fixed for reproducibility.
    """
    if not text or not text.strip():
        return []

    failures: List[str] = []

    if _AND_PIVOT_RX.search(text):
        failures.append("and_pivot")

    if _OR_SPECULATION_RX.search(text):
        failures.append("or_speculation")

    if _REQUEST_PLUS_INQUIRY_RX.search(text):
        failures.append("request_plus_inquiry")

    if _CHOICE_FRAMING_RX.search(text):
        failures.append("choice_framing")

    if _HIDDEN_SECOND_TARGET_PROPER_RX.search(text):
        failures.append("hidden_second_target")

    if _DUAL_RETRIEVAL_RX.search(text):
        failures.append("dual_retrieval_axis")

    return failures


def _find_first_pivot(text: str) -> int:
    """Return the lowercase index of the first pivot token in `text`,
    or -1 if none found. Used by the truncation step."""
    lower = text.lower()
    earliest = -1
    for tok in _PIVOT_TOKENS:
        idx = lower.find(tok)
        if idx != -1 and (earliest == -1 or idx < earliest):
            earliest = idx
    return earliest


def _attempt_truncation(text: str) -> str:
    """Truncate at the first pivot.

    Two cases — the discriminator is whether the pre-pivot clause
    starts with a question stem or an imperative stem:

      Case A (pre-pivot is the question/request):
          "What was Spokane like, and how did your dad's work affect you?"
          → "What was Spokane like?"  (keep pre-pivot, ensure '?')

          "Tell me about Spokane and what happened next."
          → "Tell me about Spokane."  (keep pre-pivot, ensure '.')

      Case B (pre-pivot is a statement, post-pivot is the question):
          "I can imagine that was thrilling, and what drew you to that role?"
          → "What drew you to that role?"  (keep post-pivot, capitalize)

    Without Case B handling, statement+question compounds got naïvely
    cut at the pivot and produced a statement — which the §5.1 grammar
    guard then misrouted via question_clause regex matching internal
    modal verbs. Case B fixes that at source.
    """
    pivot_idx = _find_first_pivot(text)
    if pivot_idx == -1:
        # No pivot found — split at first '?' if there are multiple
        # question marks (handles "What is X? And what is Y?").
        first_q = text.find("?")
        if first_q != -1 and first_q < len(text) - 1:
            return text[: first_q + 1].strip()
        return text

    pre_pivot = text[:pivot_idx].rstrip(" ,;:")

    # Discriminate Case A vs Case B
    is_question_lead = bool(re.match(
        r"^\s*(what|when|where|who|why|how|which|"
        r"did|do|does|were|was|is|are|am|"
        r"can|could|would|will|should|may|might)\b",
        pre_pivot, re.IGNORECASE,
    ))
    is_imperative_lead = bool(_IMPERATIVE_RX.match(pre_pivot))

    # Case A: pre-pivot is the question or request
    if is_question_lead:
        head = pre_pivot.rstrip(".,;: ")
        if not head.endswith("?"):
            head += "?"
        return head

    if is_imperative_lead:
        head = pre_pivot.rstrip(",;: ")
        if not head.endswith(".") and not head.endswith("?"):
            head += "."
        return head

    # Case B: pre-pivot is a statement → keep post-pivot
    lower = text.lower()
    post: str = ""
    for tok in _PIVOT_TOKENS:
        if lower[pivot_idx:pivot_idx + len(tok)] == tok:
            post = text[pivot_idx + len(tok):].strip()
            break

    if not post:
        return text

    # Capitalize and normalize
    if post[0].islower():
        post = post[0].upper() + post[1:]
    if not post.endswith("?") and not post.endswith("."):
        post += "?"

    return post


def _grammar_guard(truncated: str, original: str) -> Tuple[str, str]:
    """§5.1 truncation grammar guard.

    Decision tree:
      1. truncated ends with '?' → ACCEPT, status='truncated_clean'
      2. truncated is imperative-form → ACCEPT, status='truncated_imperative'
      3. original contains a complete question clause → fall back to that
         clause, status='truncated_to_original_question'
      4. otherwise → ABORT, return original, status='skip_grammar'

    Returns (final_text, status_label) so the caller can log.
    """
    if truncated and truncated.rstrip().endswith("?"):
        return truncated, "truncated_clean"

    if truncated and _IMPERATIVE_RX.match(truncated):
        return truncated, "truncated_imperative"

    # Step 3: try to find a question clause in the ORIGINAL text.
    m = _QUESTION_CLAUSE_RX.search(original)
    if m:
        clause = m.group("clause").strip()
        # Only accept if the recovered clause is reasonably complete
        # (>= 3 words) — avoid degenerate "Did?" type fallbacks.
        if len(clause.split()) >= 3:
            # Capitalize first letter if needed.
            if clause and clause[0].islower():
                clause = clause[0].upper() + clause[1:]
            return clause, "truncated_to_original_question"

    # Step 4: ABORT.
    return original, "skip_grammar"


def enforce_question_atomicity(text: str) -> Tuple[str, List[str]]:
    """Layer 2 deterministic filter.

    Returns:
        (possibly_truncated_text, list_of_failure_labels)

    Behavior:
        - Empty/whitespace text → returns (text, [])
        - No atomicity violations → returns (text, [])
        - One or more violations → attempts truncation; passes through
          §5.1 grammar guard before returning. If grammar guard ABORTS,
          returns (original_text, failure_labels) so the caller knows
          violations were detected even though no mutation happened.

    The caller can log failure_labels regardless of whether mutation
    occurred — they're the diagnostic signal for the harness.
    """
    if not text or not text.strip():
        return text, []

    failures = classify_atomicity(text)
    if not failures:
        return text, []

    # Attempt truncation
    truncated = _attempt_truncation(text)

    # Grammar guard
    final, _status = _grammar_guard(truncated, text)

    # Conservative: if final is too short (< 3 words), abort.
    # 3-word floor catches degenerate "Did?" / "What was?" truncations
    # while still allowing legitimate short questions like "How are
    # you?" or "What was Spokane like?". The §5.1 grammar guard's
    # "skip_grammar" branch handles the case where no usable truncation
    # exists — this length check only fires when truncation produced
    # something but it's near-meaningless.
    if final is not text and len(final.split()) < 3:
        return text, failures

    return final, failures


__all__ = [
    "enforce_question_atomicity",
    "classify_atomicity",
]
