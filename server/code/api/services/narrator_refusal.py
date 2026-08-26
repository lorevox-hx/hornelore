"""When the narrator says they would rather not. ONE definition.

WO-LORI-PROFILE-SEED-REACHABILITY-01, Phase 2 step 2 (2026-08-26).

── WHY THIS MODULE EXISTS ────────────────────────────────────────────

Two callers need to recognise the same sentence:

  * **extraction** — `WO-EX-GUARD-REFUSAL-01` strips every field from an
    answer in which the narrator refused the line of questioning, because
    a refusal is not a fact about their life;
  * **the Profile Seed walk** — an explicit refusal records `declined`,
    which is a FINAL topic state, so the question never returns.

These patterns lived as a local list inside
`routers.extract._apply_refusal_guard` and therefore could not be
imported. The obvious shortcut was to copy them into the Profile Seed
service. **That would have been the defect, not the fix.** Two lists
drift, and the day they diverge Lori strips a field from a sentence she
did not treat as a refusal in the conversation — or worse, tells the
narrator she has noted their wish not to discuss something while the
extractor writes it down anyway.

So: one module, no FastAPI import (the Profile Seed service must be able
to import it), and both callers go through it.

── THE PATTERNS ARE MOVED, NOT REWRITTEN ─────────────────────────────

All EIGHT are byte-identical to the list that was inside
`_apply_refusal_guard`, in the same order, with the same
`re.IGNORECASE`. Order is preserved because the first match wins and is
logged; reordering would change which pattern an operator sees in the
log for an ambiguous sentence.

`tests/test_narrator_refusal_characterization.py` landed BEFORE this
move, follows the patterns to whichever module holds them, and asserts
the count, the per-pattern behaviour and the negative controls. It is
the proof that this module is the old behaviour in a new place.

── WHAT IS DELIBERATELY NOT HERE ─────────────────────────────────────

`services.thread_bank.DECLINATION_PATTERNS` is NOT merged in and is not
changed. It serves a different purpose — deciding whether a narrator
took up a surfaced thread — and it mixes refusal with forgetting:
"can't recall", "nothing comes to mind" and "I don't remember much" sit
in the same tuple as "I'd rather not".

For that job the conflation is harmless. Here it would be the opposite
of harmless. Under the Phase 2 rulings, **forgetting resolves to
`addressed` and refusing resolves to `declined`** — so borrowing that
list would record an older narrator's memory loss as a refusal to
speak. That is the specific harm this module is written to avoid, and
the characterization suite asserts that none of the eight patterns
matches "I don't remember", "I can't recall" or "nothing comes to mind".

A temporary deferral — "let me think", "give me a moment", "come back to
that" — is likewise not a refusal. It leaves the question open, and it
is classified by the Profile Seed turn reducer, not here.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional, Pattern, Sequence, Tuple

#: The eight patterns, moved verbatim from
#: `routers.extract._apply_refusal_guard` on 2026-08-26. Order is
#: load-bearing: the first match wins and is what gets logged.
REFUSAL_PATTERNS: Tuple[Pattern[str], ...] = (
    # Direct privacy refusal — narrator says don't write / don't record
    re.compile(r"(?:not |don\'?t )(?:think )?(?:that\'?s )?something I (?:want|need) (?:written|recorded|put (?:down|in))", re.IGNORECASE),
    re.compile(r"not for (?:putting|writing) (?:in|down|into) (?:a book|the record|a record)", re.IGNORECASE),
    # Topic avoidance — narrator deflects the question
    re.compile(r"nothing I (?:want|need|care) to (?:go into|get into|talk about|discuss|share)", re.IGNORECASE),
    re.compile(r"(?:I\'?d |I would |I\'?d just )rather (?:not|leave it|skip|move on)", re.IGNORECASE),
    re.compile(r"(?:I\'?d |I would )prefer not to", re.IGNORECASE),
    re.compile(r"(?:let\'?s |can we )(?:skip|move on|not go there|leave) (?:that|this|it)", re.IGNORECASE),
    re.compile(r"I don\'?t (?:want|need|care) to (?:talk|go|get) (?:about |into )(?:that|this|it)", re.IGNORECASE),
    re.compile(r"rather not (?:get into|talk about|discuss|say|share|go there)", re.IGNORECASE),
)


def first_refusal_match(text: Optional[str]) -> Optional[Pattern[str]]:
    """The first pattern this text refuses by, or `None`.

    Returns the PATTERN rather than a bool so the extraction caller can
    keep logging which one fired — an operator reading
    `[extract][refusal-guard]` needs to know what was recognised, not
    only that something was.

    Matching is against the lowercased text, exactly as the original
    guard did. Every pattern also carries `re.IGNORECASE`, so the
    lowering is redundant and is kept anyway: it was there before, and
    a behaviour-preserving move is not the place to discover that a
    redundancy was load-bearing for some pattern nobody re-read.
    """
    if not text:
        return None
    lowered = text.lower()
    for pattern in REFUSAL_PATTERNS:
        if pattern.search(lowered):
            return pattern
    return None


def is_topic_refusal(text: Optional[str]) -> bool:
    """Did the narrator refuse this line of questioning?

    True means: extraction strips every field from this answer, and the
    Profile Seed walk records `declined` for the topic that was open.
    Both consequences follow from ONE decision, which is the point.
    """
    return first_refusal_match(text) is not None


__all__: Sequence[str] = (
    "REFUSAL_PATTERNS", "first_refusal_match", "is_topic_refusal",
)
