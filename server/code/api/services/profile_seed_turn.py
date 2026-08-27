"""Which question is open, and what the narrator just did about it.

WO-LORI-PROFILE-SEED-REACHABILITY-01, Phase 2 step 3 (2026-08-26).

── THE ONE THING THIS MODULE EXISTS TO PREVENT ───────────────────────

**Advancing a question nobody answered.**

The first Phase 2 design resolved the active topic, put it in Lori's
prompt, and then — in the same committed turn — marked it `addressed`.
The narrator had not spoken since before the question existed. Ten turns
later the walk would have reported itself complete having received zero
answers, and the narrator would have been asked ten questions and heard
none of them acknowledged.

The second design repaired that with ONE event type, re-stamped after a
response. That cannot distinguish *"Lori presented A"* from *"the
narrator answered A and Lori acknowledged it"*, so the acknowledgement
turn was composed as though A were still open — Lori would have asked A
again in the same breath she thanked the narrator for answering it.

Both were caught in review. What survives is two durable events and an
exact tuple.

── TWO EVENTS, AND THE TUPLE IS THE IDENTITY ─────────────────────────

    presented(topic, version)                    Lori asked
    response(topic, version, disposition)        Lori acknowledged

A response CONSUMES a presentation when the `(topic, version)` tuples
are **equal**. Not when the topics match.

That distinction is not pedantry, and the case it covers is ordinary:
Phase 1's `reconcile` bumps the version whenever effective stored state
changes, so an unrelated operator entry, a superseded row, or a pause
and resume all re-version a topic that is still active. Comparing topics
alone would let an answer to the OLD question consume the NEW
presentation and apply against it.

── WHY THE DISPOSITION IS ON THE ROW ─────────────────────────────────

So a retry after a crash applies what the narrator was actually told had
happened. Topic and version alone cannot reconstruct whether they
answered or declined; a recovery reading only a presentation would have
to re-derive the disposition from their words a second time, and could
reach a different answer.

── NO DEPENDENCIES, ON PURPOSE ───────────────────────────────────────

No FastAPI, no `api.db`, no connection. `recover()` takes the resolve
and apply functions as arguments. That keeps the whole state machine
testable without a database, and it is why the four mandatory mutations
below can be exercised behaviourally rather than by reading source.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, List, Mapping, Optional, Sequence, Tuple

from . import narrator_refusal as _refusal
from . import profile_seed as _seed

# ── Metadata keys written into the assistant row's `meta_json` ──────────
#
# Five scalars. Two topic ids from a fixed registry of ten, two integers
# and one of two words. NO NARRATOR PROSE, no question wording, no
# answer text — work-order decision 8 holds on the turn row exactly as
# it holds on the progress row.
PRESENTED_TOPIC = "profile_seed_presented_topic"
PRESENTED_VERSION = "profile_seed_presented_version"
RESPONSE_TOPIC = "profile_seed_response_topic"
RESPONSE_VERSION = "profile_seed_response_version"
RESPONSE_DISPOSITION = "profile_seed_response_disposition"

META_KEYS: Tuple[str, ...] = (
    PRESENTED_TOPIC, PRESENTED_VERSION,
    RESPONSE_TOPIC, RESPONSE_VERSION, RESPONSE_DISPOSITION,
)

# ── Classification outcomes ─────────────────────────────────────────────
ADDRESSED = _seed.ADDRESSED
DECLINED = _seed.DECLINED
#: Not a topic state. "The question stays open."
STATIONARY = "stationary"

CLASSIFICATIONS: Tuple[str, ...] = (ADDRESSED, DECLINED, STATIONARY)

# ── Turn plan actions ───────────────────────────────────────────────────
PRESENT = "present"          # ask A for the first time
RE_PRESENT = "re_present"    # ask A again after a deferral or a stale tuple
ACKNOWLEDGE = "acknowledge"  # respond to an answer; ask NOTHING
IDLE = "idle"                # onboarding is not active; render nothing

ACTIONS: Tuple[str, ...] = (PRESENT, RE_PRESENT, ACKNOWLEDGE, IDLE)


# ── Temporary deferral ──────────────────────────────────────────────────
#
# NARROW ON PURPOSE, and matched against the WHOLE utterance rather than
# searched for inside it.
#
# The ruling is that a deferral leaves the question open while everything
# else non-empty is `addressed`. A substring search would break that:
# "let me think — Devils Lake, North Dakota" contains a deferral and IS
# an answer, and treating it as stationary would re-ask a question the
# narrator had just answered.
#
# So the turn is normalised — lowercased, punctuation dropped, a small
# set of leading/trailing politeness fillers removed — and the residue
# must BE a deferral phrase, not merely contain one. No counting, no
# threshold: "is this the whole turn" is a different question from "is
# this answer long enough", and only the second one was ruled out.
_DEFERRAL_PHRASES = frozenset({
    "let me think",
    "let me think about that",
    "let me think on that",
    "give me a moment",
    "give me a minute",
    "give me a second",
    "just a moment",
    "just a minute",
    "one moment",
    "one minute",
    "hold on",
    "hang on",
    "i need a moment",
    "i need a minute",
    "id like a moment",
    "id like a minute",
    "come back to that",
    "come back to it",
    "can we come back to that",
    "can we come back to it",
    "lets come back to that",
    "lets come back to it",
    "ill come back to that",
    "ill come back to it",
})

#: Stripped from either end before the whole-utterance comparison.
_FILLERS = frozenset({
    "well", "oh", "um", "uh", "hmm", "mm", "okay", "ok", "so", "now",
    "please", "sorry", "yes", "no", "alright", "right", "and", "but",
})

#: Apostrophes are ELIDED, not turned into spaces, and the order matters.
#
# ── THE DEFECT THIS CLOSES, 2026-08-26 ──────────────────────────────────
#
# `_PUNCT` replaces punctuation with a SPACE, so "I'll come back to that"
# normalised to "i ll come back to that" and "Let's come back to it" to
# "let s come back to it" — neither of which matches the configured
# phrases `ill come back to that` and `lets come back to it`.
#
# So a narrator who said "I'll come back to that" — the single most
# natural way to ask for time — was classified `addressed`, and the
# topic was CLOSED. The one phrasing the deferral category exists to
# catch was the one it could not see, and the fixture phrases had been
# written apostrophe-free, which is why the tests agreed.
#
# Curly apostrophes are included because a phone keyboard and most word
# processors produce them by default, and a narrator dictating through
# STT may get either.
_APOSTROPHES = re.compile("['’‘ʼ´`]")
_PUNCT = re.compile(r"[^\w\s]+", re.UNICODE)
_WS = re.compile(r"\s+")


def _normalise(text: str) -> str:
    # Elide apostrophes FIRST so contractions collapse to one word;
    # then the general punctuation pass can safely use spaces.
    deapostrophised = _APOSTROPHES.sub("", (text or "").lower())
    lowered = _PUNCT.sub(" ", deapostrophised)
    words = [w for w in _WS.split(lowered) if w]
    while words and words[0] in _FILLERS:
        words.pop(0)
    while words and words[-1] in _FILLERS:
        words.pop()
    return " ".join(words)


def is_temporary_deferral(text: Optional[str]) -> bool:
    """Is this turn ONLY a request for time?

    Whole-utterance, so a deferral followed by an actual answer is an
    answer.
    """
    if not text or not text.strip():
        return False
    return _normalise(text) in _DEFERRAL_PHRASES


def classify_response(text: Optional[str]) -> str:
    """`addressed` | `declined` | `stationary`, per the Phase 2 rulings.

    Order matters. Refusal is checked first because "I'd rather not talk
    about that" must never be read as a deferral, and an empty turn is
    checked before anything else because it is not a response at all.

    **Everything else non-empty is `addressed`, and there is no
    word-count threshold.** "Devils Lake, North Dakota" is four words and
    completely answers the childhood-home question; thirty words of "oh
    goodness, that was such a long time ago" answers nothing. Grading
    answer quality is the operator review surface's job, later — it is
    not a reason to keep asking.

    **"I don't remember" is `addressed`.** It records no biographical
    fact and nothing about the recall difficulty reaches the progress
    row; it closes the topic so that an older narrator is not confronted
    with the same unreachable question every session. The ordinary
    committed conversation is still there if the memory surfaces later.
    """
    if not text or not text.strip():
        return STATIONARY
    if _refusal.is_topic_refusal(text):
        return DECLINED
    if is_temporary_deferral(text):
        return STATIONARY
    return ADDRESSED


# ── Events ──────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class TurnEvent:
    kind: str                      # "presented" | "response"
    topic_id: str
    version: int
    disposition: Optional[str] = None
    index: int = -1                # position in history, for ordering

    @property
    def tuple(self) -> Tuple[str, int]:
        return (self.topic_id, self.version)


PRESENTED = "presented"
RESPONSE = "response"


def _valid_version(raw: Any) -> Optional[int]:
    """A version is an integer >= 1. Booleans are not integers here.

    `isinstance(True, int)` is True in Python, and a `True` that reached
    a version field would compare equal to version 1 — silently
    consuming a real presentation.
    """
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw if raw >= 1 else None
    if isinstance(raw, str):
        try:
            value = int(raw.strip())
        except (TypeError, ValueError):
            return None
        return value if value >= 1 else None
    return None


def event_from_meta(meta: Any, index: int = -1) -> Optional[TurnEvent]:
    """One event from one row's `meta`, or `None`.

    MALFORMED METADATA IS IGNORED, NEVER GUESSED AT. An unknown topic id,
    a missing or non-integer version, a disposition outside the two a
    client may record, or a half-written pair all yield `None`.

    Ignoring is the safe direction here and it is worth saying why: a
    dropped event means the presentation stays outstanding and the
    question gets asked again, which costs the narrator one repeated
    question. A *guessed* event could mark a topic answered that nobody
    answered, which is the failure this whole module exists to prevent.
    """
    if not isinstance(meta, Mapping):
        return None

    r_topic = meta.get(RESPONSE_TOPIC)
    if r_topic is not None:
        version = _valid_version(meta.get(RESPONSE_VERSION))
        disposition = meta.get(RESPONSE_DISPOSITION)
        if (_seed.is_known_topic(r_topic) and version is not None
                and disposition in _seed.CLIENT_DISPOSITIONS):
            return TurnEvent(RESPONSE, r_topic, version, disposition, index)
        return None

    p_topic = meta.get(PRESENTED_TOPIC)
    if p_topic is not None:
        version = _valid_version(meta.get(PRESENTED_VERSION))
        if _seed.is_known_topic(p_topic) and version is not None:
            return TurnEvent(PRESENTED, p_topic, version, None, index)
        return None

    return None


def read_events(history: Optional[Iterable[Mapping[str, Any]]]) -> List[TurnEvent]:
    """Every well-formed event in `export_turns()` order."""
    out: List[TurnEvent] = []
    if not history:
        return out
    for index, row in enumerate(history):
        if not isinstance(row, Mapping):
            continue
        if (row.get("role") or "") != "assistant":
            continue
        event = event_from_meta(row.get("meta"), index)
        if event is not None:
            out.append(event)
    return out


def outstanding_presentation(
    history: Optional[Iterable[Mapping[str, Any]]],
) -> Optional[TurnEvent]:
    """The latest presentation no later response has consumed.

    Consumption requires the EXACT `(topic, version)` tuple. A response
    to `("siblings", 4)` does not consume a presentation of
    `("siblings", 5)` — the version moved, so it is a different
    question.

    ── CONSUMPTION IS TEMPORAL, NOT ONE-FOR-ONE ────────────────────────

    *(Corrected 2026-08-26. The first version `discard`ed the tuple after
    matching a single presentation, modelling "one response consumes one
    presentation". That is a COUNTING model, and the correct one is
    temporal. It broke on an ordinary history:*

        presented(A,7) · "let me think" · presented(A,7) · answer · response(A,7)

    *The reverse scan consumed the newer presentation, emptied the set,
    and then handed back the OLDER identical presentation as still
    outstanding — so a question the narrator had just answered would be
    re-presented, and re-presented again after every deferral. The
    deferral path made it reachable in normal conversation rather than
    only under a race.)*

    **A response consumes EVERY EARLIER presentation of its tuple.** The
    scan runs newest-first, so any presentation reached after a response
    for the same tuple is by construction earlier in time and is
    therefore answered. Nothing is discarded from `consumed`.

    A genuinely LATER presentation of the same tuple — Lori asking again
    after the response, because evidence has not moved and the topic is
    still open — is returned before the scan ever reaches that response,
    so it correctly stays outstanding.
    """
    events = read_events(history)
    consumed: set = set()
    for event in reversed(events):
        if event.kind == RESPONSE:
            consumed.add(event.tuple)
            continue
        if event.tuple in consumed:
            # Earlier than the response that answered it. Keep the tuple
            # in `consumed`: every still-earlier presentation of the same
            # question was answered by that same response.
            continue
        return event
    return None


def latest_response(
    history: Optional[Iterable[Mapping[str, Any]]],
) -> Optional[TurnEvent]:
    for event in reversed(read_events(history)):
        if event.kind == RESPONSE:
            return event
    return None


# ── The turn plan ───────────────────────────────────────────────────────
@dataclass(frozen=True)
class TurnPlan:
    action: str
    topic_id: Optional[str] = None
    version: Optional[int] = None
    disposition: Optional[str] = None
    #: True when THIS acknowledgement closes the last remaining topic.
    #:
    #: ── WHY THIS FIELD EXISTS, 2026-08-26 ───────────────────────────
    #:
    #: The presentation block used to carry "when they have answered,
    #: tell them warmly that you now have a sense of their story" on the
    #: turn that ASKED the final question. That instruction could never
    #: execute: it describes what to do on the NEXT turn, and by then
    #: the block is gone — the acknowledgement turn had no idea the walk
    #: had just finished. A promise Lori was structurally unable to keep.
    #:
    #: The flag moves the instruction to the turn that can act on it.
    completes_walk: bool = False

    @property
    def advances(self) -> bool:
        return self.action == ACKNOWLEDGE

    def presented_meta(self) -> dict:
        """Metadata for an assistant row that ASKS."""
        if self.action not in (PRESENT, RE_PRESENT):
            return {}
        return {PRESENTED_TOPIC: self.topic_id,
                PRESENTED_VERSION: int(self.version or 0)}

    def response_meta(self) -> dict:
        """Metadata for an assistant row that ACKNOWLEDGES.

        A stationary turn returns `{}` from BOTH — it produces a
        presentation, not a response, because a deferral is not an
        answer and the question stays open.
        """
        if self.action != ACKNOWLEDGE:
            return {}
        return {RESPONSE_TOPIC: self.topic_id,
                RESPONSE_VERSION: int(self.version or 0),
                RESPONSE_DISPOSITION: self.disposition}

    def turn_meta(self) -> dict:
        merged = dict(self.presented_meta())
        merged.update(self.response_meta())
        return merged


def plan_turn(
    *,
    state: Optional[Mapping[str, Any]],
    history: Optional[Iterable[Mapping[str, Any]]],
    narrator_text: Optional[str],
    eligible: bool = True,
) -> TurnPlan:
    """What this turn should do about Profile Seed. No side effects.

    `state` is a resolved-state dict (Phase 1 `as_dict()`), or `None` for
    a historical narrator. `eligible` is False for every turn that must
    not participate at all — deterministic modes, system directives,
    cancelled turns — and short-circuits to `IDLE` before anything else
    is considered.
    """
    if not eligible or not state:
        return TurnPlan(IDLE)
    if state.get("status") != _seed.STATUS_ACTIVE:
        return TurnPlan(IDLE)

    active = state.get("active_topic_id")
    version = _valid_version(state.get("version"))
    if not _seed.is_known_topic(active) or version is None:
        return TurnPlan(IDLE)

    outstanding = outstanding_presentation(history)

    if outstanding is None:
        # FIRST PRESENTATION. Ask, and advance NOTHING — the narrator has
        # not had a chance to answer a question that does not yet exist.
        return TurnPlan(PRESENT, active, version)

    if outstanding.tuple != (active, version):
        # STALE. Either the topic moved, or the SAME topic was
        # re-versioned underneath the question. Abandon the outstanding
        # presentation and ask the current question fresh; never apply a
        # disposition against a tuple that no longer exists.
        return TurnPlan(RE_PRESENT, active, version)

    outcome = classify_response(narrator_text)
    if outcome == STATIONARY:
        # A deferral is not an answer. Re-present, stamp a NEW
        # presentation at the current version, and write no response
        # event.
        return TurnPlan(RE_PRESENT, active, version)

    # ACKNOWLEDGE. Lori responds to what was said and asks NOTHING —
    # not A again, and not B, because until the post-commit apply
    # succeeds B is a prediction rather than a fact.
    #
    # `completes_walk` is NOT a prediction in the same sense. It says
    # only that the topic being closed right now is the last one still
    # unanswered, which this turn's own disposition settles. If the apply
    # later conflicts, recovery re-resolves and the next turn presents
    # whatever the server actually believes — and nothing false was said
    # to the narrator, because the block it drives asks no question and
    # claims no fact beyond "I have a sense of your story now".
    remaining = [t for t in (state.get("remaining_topics") or [])
                 if _seed.is_known_topic(t)]
    completes = remaining == [outstanding.topic_id]
    return TurnPlan(ACKNOWLEDGE, outstanding.topic_id, outstanding.version,
                    outcome, completes_walk=completes)


# ── Recovery ────────────────────────────────────────────────────────────
NOTHING_OWED = "nothing_owed"
RETRIED = "retried"
CONFLICT_RESOLVED = "conflict_resolved"

RECOVERY_OUTCOMES: Tuple[str, ...] = (NOTHING_OWED, RETRIED, CONFLICT_RESOLVED)


@dataclass(frozen=True)
class RecoveryOutcome:
    status: str
    state: Optional[Mapping[str, Any]]
    topic_id: Optional[str] = None
    version: Optional[int] = None
    disposition: Optional[str] = None


def recover(
    person_id: str,
    history: Optional[Iterable[Mapping[str, Any]]],
    *,
    resolve_fn: Callable[[str], Optional[Mapping[str, Any]]],
    apply_fn: Callable[..., Any],
) -> RecoveryOutcome:
    """Re-apply a committed response whose post-commit apply never landed.

    RUNS BEFORE COMPOSITION, EVERY TURN.

    Without this the machine does not retry — it REPEATS. The response
    event consumes the presentation, onboarding still holds the old
    tuple as active, the next reduction finds nothing outstanding, and
    the narrator is asked a question they already answered with their
    answer sitting committed one row above. That is repetition wearing
    retry's clothes, and it is why "costs one repeated question" was a
    false description of the failure rather than a small one.

    THREE OUTCOMES, and the error behaviour is as load-bearing as they
    are:

      * nothing owed — no response event, or the state has already moved
        past it. One resolve, which the turn was doing anyway.
      * retried — the tuples matched exactly, the apply succeeded, and
        the state is RESOLVED AGAIN so composition sees the new active
        topic rather than the one just closed.
      * conflict resolved — the apply raised `VersionConflict`, meaning
        the state moved for some other reason. The authoritative state
        is RE-RESOLVED and wins. The stored disposition is NEVER forced
        onto a tuple it no longer matches.

    **Any non-conflict storage error propagates.** The caller must refuse
    composition visibly rather than fall back, because "ask it again" is
    an onboarding decision and Phase 1's accepted rule is that a storage
    fault must never make one.
    """
    last = latest_response(history)
    if last is None:
        return RecoveryOutcome(NOTHING_OWED, resolve_fn(person_id))

    state = resolve_fn(person_id)
    if not state:
        # Historical narrator, or none. Nothing to recover onto.
        return RecoveryOutcome(NOTHING_OWED, state)

    current = (state.get("active_topic_id"), _valid_version(state.get("version")))
    if current != last.tuple:
        # Already applied on the original turn, or superseded since.
        return RecoveryOutcome(NOTHING_OWED, state)

    try:
        apply_fn(person_id, expected_version=last.version,
                 action=last.disposition, topic_id=last.topic_id)
    except _seed.VersionConflict:
        return RecoveryOutcome(CONFLICT_RESOLVED, resolve_fn(person_id),
                               last.topic_id, last.version, last.disposition)
    return RecoveryOutcome(RETRIED, resolve_fn(person_id),
                           last.topic_id, last.version, last.disposition)


__all__: Sequence[str] = (
    "PRESENTED_TOPIC", "PRESENTED_VERSION", "RESPONSE_TOPIC",
    "RESPONSE_VERSION", "RESPONSE_DISPOSITION", "META_KEYS",
    "ADDRESSED", "DECLINED", "STATIONARY", "CLASSIFICATIONS",
    "PRESENT", "RE_PRESENT", "ACKNOWLEDGE", "IDLE", "ACTIONS",
    "PRESENTED", "RESPONSE", "TurnEvent", "TurnPlan",
    "is_temporary_deferral", "classify_response", "event_from_meta",
    "read_events", "outstanding_presentation", "latest_response",
    "plan_turn", "RecoveryOutcome", "recover",
    "NOTHING_OWED", "RETRIED", "CONFLICT_RESOLVED", "RECOVERY_OUTCOMES",
)
