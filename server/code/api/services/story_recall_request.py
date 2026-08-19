"""Detect an explicit request to recall what the NARRATOR already said.

WO-LORI-STORY-RECALL-ROUTING-01, 2026-08-19.

── THE DEFECT THIS FIXES ───────────────────────────────────────────────

Hornelore already has a deterministic `memory_echo` route. Its detector
is anchored on `about me`, `about my life|story|past`, or `who i am` --
so a SUBJECT-SPECIFIC question ("what have I already told you about my
grandmother?") does not match, falls through to the model, and depends
on whether the model happens to use a prompt paragraph on that turn.
Measured live: the approved story was in the prompt (`approved=1`), the
prompt fitted at 6,779/8,192 with nothing trimmed, and Lori answered
from an unrelated profile fact instead.

The server already holds the reviewed evidence. This routes the question
to it rather than hoping.

── WHY IT IS DELIBERATELY NARROW ───────────────────────────────────────

Ordinary conversation must stay model-driven: Lori listens, reflects and
asks. This fires ONLY when the narrator explicitly asks Lori to retrieve
something already recorded. Four conditions, all required:

  1. question form;
  2. short turn -- a long narrative that happens to contain the words is
     not a request;
  3. the NARRATOR is the teller: "I told you", "I said", "I mentioned".
     This is the clause that keeps "my grandmother told me..." out --
     there the grandmother is the teller and Lori is not being asked
     anything;
  4. an explicit `about <subject>`.

── ENGLISH ONLY, ON PURPOSE ────────────────────────────────────────────

Spanish handling is an established capability with its own guards. This
detector is English-specific, and the property is OVER-DETERMINED: the
telling construction, the recall verb and the `about` anchor are each
written in English, and each one independently rejects a Spanish
phrasing. Mutation testing established that -- adding Spanish verbs to
either verb pattern changes no outcome, because `about` still fails, and
the Spanish tests only go red when all three are translated at once.

(An earlier draft of this paragraph credited the telling construction
alone. That was a guess from reading the code, and it was wrong; three
conditions do the work, not one. Equivalent Spanish support would mean
translating all three deliberately, with its own tests.)

English-specific is not the same as English-word-only. A bilingual
narrator asking in English about a Spanish-named subject ("what have I
told you about mi abuela?") is asking an English question, and it is
answered.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, NamedTuple, Optional, Sequence

__all__ = ["StoryRecallRequest", "detect_story_recall", "subject_terms",
           "select_approved_story", "MAX_WORDS"]

#: Long turns are narration, not retrieval requests. Matches the existing
#: memory-echo detector's limit so the two behave alike.
MAX_WORDS = 30

# The narrator is the one who told/said/shared it. "my grandmother told
# me" fails this by construction: the verb needs a first-person subject.
_NARRATOR_TOLD = re.compile(
    r"\bi\s+(?:have\s+|already\s+|ever\s+)*"
    r"(?:told|said|mentioned|shared|described)\b"
    r"|\bhave\s+i\s+(?:ever\s+|already\s+)*"
    r"(?:told|said|mentioned|shared|described)\b"
    r"|\bdid\s+i\s+(?:ever\s+|already\s+)*"
    r"(?:tell|say|mention|share|describe)\b"
)

# "do you remember ... I told you" / "what do you remember about X" is
# only a recall request when paired with the narrator-as-teller clause
# above; this alone is not sufficient.
_RECALL_VERB = re.compile(
    r"\b(?:remember|recall|told|said|mentioned|shared|described|"
    r"tell|say|mention|share|describe)\b"
)

_QUESTION_OPENERS = (
    "what ", "do you ", "did i ", "have i ", "can you ", "could you ",
    "would you ", "tell me ", "anything ",
)

# `about <subject>` -- the subject runs to the end of ITS OWN sentence.
_ABOUT = re.compile(r"\babout\s+(.+?)\s*[?.!,;]*\s*$", re.I)

# Sentence split, used to take the LAST sentence of the turn.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

# Subject words that carry no selectivity. Dropped before matching so
# "about my grandmother" matches on "grandmother", not on "my".
_STOP = frozenset({
    "my", "our", "the", "a", "an", "his", "her", "their", "your", "that",
    "this", "those", "these", "of", "in", "on", "at", "to", "and", "or",
    "with", "from", "for", "any", "anything", "something", "some", "it",
    "me", "us", "you", "i", "we", "was", "were", "is", "are", "been",
    "had", "has", "have", "did", "do", "does", "when", "where", "what",
    "who", "why", "how", "ever", "already", "yet", "back", "then",
})

# ── HOW ENGLISH-ONLY IS ENFORCED, AND WHAT WAS REMOVED ─────────────────
#
# The first cut carried a Spanish word list (`¿ ¡ ñ`, plus `que / dije /
# contado / mi / abuela / sobre`) that rejected any turn containing one.
# Mutation testing showed it could not change a single outcome: the
# English telling construction, the English recall verb and the English
# `about` anchor each already reject every Spanish phrasing on their own.
#
# It was worse than merely redundant. "Lori, what have I told you about
# mi abuela?" is an ENGLISH question from a bilingual narrator, and the
# word list rejected it -- so an unreachable guard was buying nothing
# while creating a real false negative for exactly the narrators
# Lorevox's Spanish support exists to serve.
#
# So the guard is gone and the property is tested directly: Spanish
# phrasings do not match, a code-switched English question does.


class StoryRecallRequest(NamedTuple):
    """A detected request, and the subject it asks about."""

    matched: bool
    subject: str = ""
    terms: tuple = ()


def subject_terms(subject: str) -> List[str]:
    """Meaningful words from the subject phrase, lowercased.

    Selectivity matters: these decide WHICH approved story answers the
    question, and a match on "my" would select the first story every
    time.
    """
    words = re.findall(r"[a-z][a-z'\-]+", (subject or "").lower())
    return [w for w in words if w not in _STOP and len(w) > 2]


def detect_story_recall(text: Optional[str]) -> StoryRecallRequest:
    """True only for an explicit, short, subject-specific recall question.

    Never raises: a detector that throws would decide a narrator's turn
    by accident.
    """
    try:
        raw = (text or "").strip()
        if not raw:
            return StoryRecallRequest(False)
        low = raw.lower()

        # Length is judged on the WHOLE turn: a long monologue is
        # narration however it happens to end.
        if len(low.split()) > MAX_WORDS:
            return StoryRecallRequest(False)

        # ── ONLY THE LAST SENTENCE IS THE REQUEST ───────────────────────
        #
        # Added after a test caught the first cut matching:
        #
        #   "My grandmother told me about the river, and I asked her,
        #    what did I say about that? She only laughed at me."
        #
        # -- a narrator QUOTING a question they once asked someone else.
        # Every individual condition was satisfied somewhere in that
        # sentence, and the subject capture, anchored to end-of-string,
        # then swallowed the sentence after it.
        #
        # Reading only the final sentence fixes both halves at once: the
        # quoted-question case ends on "She only laughed at me" and
        # matches nothing, while an ordinary preamble ("Hello Lori. What
        # have I told you about my grandmother?") still works.
        raw = [s for s in _SENTENCE_SPLIT.split(raw) if s.strip()][-1].strip()
        low = raw.lower()

        is_question = ("?" in low) or low.startswith(_QUESTION_OPENERS)
        if not is_question:
            return StoryRecallRequest(False)

        # The narrator must be the teller. This is what separates
        # "have I told you about my grandmother?" from
        # "my grandmother told me about the river".
        if not _NARRATOR_TOLD.search(low):
            return StoryRecallRequest(False)
        if not _RECALL_VERB.search(low):
            return StoryRecallRequest(False)

        m = _ABOUT.search(raw)
        if not m:
            return StoryRecallRequest(False)
        subject = m.group(1).strip()
        terms = subject_terms(subject)
        if not terms:
            # "about me" and friends are the BROAD memory-echo case,
            # which already has its own detector and its own answer.
            # Claiming them here would change behaviour that works.
            return StoryRecallRequest(False)
        return StoryRecallRequest(True, subject, tuple(terms))
    except Exception:
        return StoryRecallRequest(False)


def _term_hits(text: str, terms: Sequence[str]) -> int:
    """How many distinct subject terms occur in this story, by word."""
    low = (text or "").lower()
    hits = 0
    for term in set(terms):
        if re.search(r"\b" + re.escape(term) + r"s?\b", low):
            hits += 1
    return hits


def select_approved_story(story_context: Optional[Dict[str, Any]],
                          terms: Sequence[str]) -> Optional[Dict[str, Any]]:
    """The best APPROVED story for these subject terms, or None.

    ── ONLY THE APPROVED LIST IS EVEN READ ─────────────────────────────

    `grounding_context` already drops discarded stories and never carries
    provisional TEXT -- only a count. This reads `approved` and nothing
    else, so provisional or discarded material cannot reach a narrator
    through this path even if the projection's guarantees were to change:
    there is no key here through which it could arrive.

    ── A MISS RETURNS None, AND THAT IS THE POINT ──────────────────────

    Returning the first story when nothing matches would answer a
    question about a grandmother with a story about a job, and the
    narrator would have no way to tell that Lori had not understood.
    Saying nothing matched is the honest answer and the caller renders
    it as one.
    """
    ctx = story_context if isinstance(story_context, dict) else {}
    if not ctx.get("available"):
        return None
    rows = ctx.get("approved") or []
    if not isinstance(rows, list) or not terms:
        return None

    best = None
    best_hits = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        hits = _term_hits(text, terms)
        # Strictly greater keeps the FIRST story on a tie. The projection
        # returns them in a stable order, so an unchanged question gets an
        # unchanged answer.
        if hits > best_hits:
            best, best_hits = row, hits
    return best
