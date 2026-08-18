"""ONE canonical projection of reviewed story evidence.

WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 Phase 3, Commit A (2026-08-17).

Five surfaces need to know what a narrator's captured stories amount to:

    Chronology Accordion    which stories sit in which decade
    Life Map                approved vs provisional, and where they place
    Lori grounding          what may be spoken of as established
    memoir eligibility      what may reach a family-facing artifact
    operator review         what the reviewer is looking at

Before this module each of them interpreted `review_status` for itself.
`chronology_accordion` had `_STORY_STATUS`; `db.story_candidate_list_for_memoir`
had `IN ('promoted','memoir_only')`; the operator surface had a hard-wired
`unreviewed` filter; Lori had nothing at all. Four readings of one column,
which is four chances to disagree about whether a story is approved -- and
the one that matters most, Lori's, did not exist, so no captured story had
ever reached her prompt.

This is the single interpretation. Every consumer reads from here.

── THE FIVE TRUTHS, and what each one prevents ──────────────────────────

1. **Provisional is never called approved.** A story the narrator told and
   nobody reviewed is evidence that something was said, not a fact about
   their life. `approved` requires an explicit human decision.

2. **Unknown placement is not called stated.** Where a date came from is
   recorded (`placement_source`), never inferred. The rule this replaces
   guessed `stated` from `confidence == "high"`, and confidence is set at
   capture time by the trigger heuristic -- it says nothing about who
   decided when the story happened.

3. **Unplaced stories are not forced into Today.** A story with no era and
   no year is UNPLACED. Today is the current-life bucket, not a bin for
   things that failed to sort; putting them there would assert a placement
   nobody made.

4. **Discarded stories disappear.** Not dimmed, not filtered client-side --
   absent from every projection this module produces.

5. **A lane failure reports unavailable, not an empty narrator.** Same rule
   the chronology lanes earned in Phase 2: an outage must never render as
   "this narrator has no stories".

── WHAT THIS MODULE MAY NOT DO ─────────────────────────────────────────

It is a READ projection. It writes nothing, and it never reaches into the
extraction stack -- the LAW 3 boundary that `story_preservation` documents
applies to anything handling this data. It imports `db` and nothing else
from the project.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, NamedTuple, Optional, Sequence

from .. import db as _db

logger = logging.getLogger("story_projection")

__all__ = [
    "StoryProjection",
    "APPROVED",
    "PROVISIONAL",
    "PLACEMENT_STATED",
    "PLACEMENT_OPERATOR",
    "PLACEMENT_DERIVED",
    "PLACEMENT_UNPLACED",
    "project_stories",
    "grounding_context",
]

# Outward status vocabulary. Deliberately NOT the same words as the
# database column: `review_status` records what an operator did,
# `status` records what a consumer may claim.
APPROVED = "approved"
PROVISIONAL = "provisional"

_REVIEW_TO_STATUS = {
    "promoted": APPROVED,
    "memoir_only": APPROVED,
    "in_review": PROVISIONAL,
    "unreviewed": PROVISIONAL,
    # `discarded` is absent on purpose -- it maps to exclusion, not to a
    # status, and a consumer must never receive a discarded row to filter.
}

# Only `promoted` carries extracted facts forward. `memoir_only` is the
# operator saying "this belongs in the memoir as the narrator told it, but
# do not promote what the extractor made of it" -- the distinction is the
# whole reason the two statuses exist.
_FACTS_ELIGIBLE = set(_db.STORY_FACTS_ELIGIBLE)
_MEMOIR_ELIGIBLE = set(_db.STORY_MEMOIR_ELIGIBLE)

PLACEMENT_STATED = "stated"
PLACEMENT_OPERATOR = "operator_set"
PLACEMENT_DERIVED = "derived"
PLACEMENT_UNPLACED = "unplaced"

_SOURCE_TO_PLACEMENT = {
    "narrator_stated": PLACEMENT_STATED,
    "operator_set": PLACEMENT_OPERATOR,
    "dob_derived": PLACEMENT_DERIVED,
    "unknown": PLACEMENT_UNPLACED,
}


class StoryProjection(NamedTuple):
    """Canonical story evidence, plus whether the lane could be read.

    `status` mirrors the chronology lane vocabulary: "read" when the
    narrator's stories were successfully loaded (even if there are none),
    "unavailable" when they could not be.
    """

    items: List[Dict[str, Any]]
    status: str
    counts: Dict[str, int]


def _placement_for(row: Dict[str, Any]) -> str:
    """Where this story's date came from, reported and never guessed."""
    source = str(row.get("placement_source") or "unknown").strip()
    placement = _SOURCE_TO_PLACEMENT.get(source, PLACEMENT_UNPLACED)
    if placement == PLACEMENT_UNPLACED:
        return PLACEMENT_UNPLACED
    # A recorded provenance with nothing to show for it is still unplaced.
    # This catches a row whose placement was set and later cleared.
    if not row.get("estimated_year_low") and not (row.get("era_candidates") or []):
        return PLACEMENT_UNPLACED
    return placement


def _era_of(row: Dict[str, Any]) -> Optional[str]:
    eras = row.get("era_candidates") or []
    if isinstance(eras, str):
        return None
    for era in eras:
        text = str(era or "").strip()
        if text:
            # TRUTH 3. `today` is the current-life bucket and a captured
            # story is a memory; a story is only placed there if a human
            # explicitly said so, which reaches us as an era candidate
            # rather than as a fallback.
            return text
    return None


def project_stories(narrator_id: str) -> StoryProjection:
    """Every non-discarded story for one narrator, canonically shaped."""
    counts = {
        "approved": 0,
        "provisional": 0,
        "discarded": 0,
        "unplaced": 0,
        "memoir_eligible": 0,
        "facts_eligible": 0,
    }
    if not (narrator_id or "").strip():
        return StoryProjection([], "read", counts)

    try:
        rows = _db.story_candidate_list_for_review(narrator_id, limit=500)
    except Exception as exc:
        # TRUTH 5. An outage is an outage.
        logger.info("story projection unavailable for %s: %s", narrator_id, exc)
        return StoryProjection([], "unavailable", counts)

    items: List[Dict[str, Any]] = []
    for row in rows:
        review = str(row.get("review_status") or "unreviewed").strip()
        if review == "discarded":
            # TRUTH 4.
            counts["discarded"] += 1
            continue
        status = _REVIEW_TO_STATUS.get(review, PROVISIONAL)
        placement = _placement_for(row)
        era = _era_of(row)
        if placement == PLACEMENT_UNPLACED:
            counts["unplaced"] += 1
        counts[status] += 1
        if review in _MEMOIR_ELIGIBLE:
            counts["memoir_eligible"] += 1
        if review in _FACTS_ELIGIBLE:
            counts["facts_eligible"] += 1

        items.append({
            "id": row.get("id"),
            "narrator_id": row.get("narrator_id"),
            "status": status,
            "review_status": review,
            "review_version": int(row.get("review_version") or 1),
            "placement": placement,
            "placement_source": str(row.get("placement_source") or "unknown"),
            "era": era,
            "era_candidates": row.get("era_candidates") or [],
            "year": row.get("estimated_year_low"),
            "year_high": row.get("estimated_year_high"),
            "confidence": row.get("confidence") or "low",
            # Carried so the chronology payload keeps the key it has
            # always had. It describes what the EXTRACTOR managed, and is
            # deliberately never an input to `status` -- extraction cannot
            # approve a story.
            "extraction_status": row.get("extraction_status") or "pending",
            "word_count": row.get("word_count"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "excerpt": str(row.get("transcript") or "")[:280],
            "memoir_eligible": review in _MEMOIR_ELIGIBLE,
            "facts_eligible": review in _FACTS_ELIGIBLE,
            "lane": "story",
            "source": "story_candidates",
        })
    return StoryProjection(items, "read", counts)


def grounding_context(
    narrator_id: str,
    *,
    max_stories: int = 6,
    max_chars: int = 240,
    exclude_text: str = "",
) -> Dict[str, Any]:
    """Bounded, server-owned story context for Lori's prompt.

    Four rules, each of which is a way this could do harm:

    * **Only APPROVED stories are offered as established material.** A
      provisional story is something the narrator said once and nobody
      confirmed; stating it back as fact is the confabulation this system
      exists to avoid.
    * **Provisional stories are counted, never quoted.** The composer is
      told how many are waiting so it can decline to invent, but it never
      receives their text and so cannot assert them.
    * **Discarded stories never appear** -- `project_stories` has already
      dropped them.
    * **The current turn is not fed back as history.** A story captured
      from the turn being composed would otherwise reach the prompt as
      established narrator material within the same breath.

    Bounded by construction: at most `max_stories`, each truncated to
    `max_chars`. The token window is LOCKED, so this may not grow without
    a decision that is not this work order's to make.
    """
    projection = project_stories(narrator_id)
    if projection.status != "read":
        return {
            "available": False,
            "status": projection.status,
            "approved": [],
            "approved_count": 0,
            "provisional_count": 0,
        }

    current = " ".join(str(exclude_text or "").split()).strip().casefold()
    approved: List[Dict[str, Any]] = []
    for item in projection.items:
        if item["status"] != APPROVED:
            continue
        excerpt = " ".join(str(item.get("excerpt") or "").split()).strip()
        if not excerpt:
            continue
        if current and (excerpt.casefold() in current or current in excerpt.casefold()):
            # The turn being composed right now is not history.
            continue
        approved.append({
            "id": item["id"],
            "text": excerpt[:max_chars],
            "era": item.get("era"),
            "year": item.get("year"),
            "placement": item.get("placement"),
        })
        if len(approved) >= max_stories:
            break

    return {
        "available": True,
        "status": projection.status,
        "approved": approved,
        "approved_count": projection.counts["approved"],
        # Reported so the composer knows material exists without being
        # able to speak it.
        "provisional_count": projection.counts["provisional"],
    }
