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
import re
from typing import Any, Dict, List, NamedTuple, Optional, Sequence

from .. import db as _db
from ..lv_eras import LV_ERAS as _LV_ERAS, legacy_key_to_era_id as _legacy_key_to_era_id

logger = logging.getLogger("story_projection")

# The canonical taxonomy, read from lv_eras rather than restated: six
# historical eras PLUS the separate `today` current-life bucket. Restating
# it here would be a second definition of the spine.
_VALID_ERA_IDS = frozenset(e["era_id"] for e in _LV_ERAS)

__all__ = [
    "StoryProjection",
    "PlacementRejected",
    "canonical_eras",
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


class PlacementRejected(ValueError):
    """An operator placement that cannot be honoured as written.

    Added 2026-08-17 after review. The PATCH route accepted arbitrary
    `era_candidates`, so an operator typo — "buidling_years" — produced a
    story the SERVER considered placed and that appeared in NO Life Map
    era. Silently placed and invisible is the worst of the three possible
    outcomes: worse than unplaced, which at least shows up in the unplaced
    group and can be found and fixed.
    """


def canonical_eras(values: Optional[Sequence[str]]) -> List[str]:
    """Canonicalize operator-supplied eras, or refuse them.

    Accepts the six historical era_ids plus an explicit `today`, and the
    legacy keys `legacy_key_to_era_id` already knows how to translate.
    Anything else is REFUSED rather than dropped: dropping a typo silently
    would leave the operator believing they had placed a story.

    NEVER derives an era from a year. A year is not a position on the Life
    Map — the map is drawn in eras — and inferring one is the guess this
    whole lane exists to stop.
    """
    if values is None:
        return []
    out: List[str] = []
    for raw in values:
        text = str(raw or "").strip()
        if not text:
            continue
        era = text if text in _VALID_ERA_IDS else _legacy_key_to_era_id(text)
        if not era or era not in _VALID_ERA_IDS:
            raise PlacementRejected(
                f"{text!r} is not a life era. Valid: "
                + ", ".join(sorted(_VALID_ERA_IDS))
            )
        if era not in out:
            out.append(era)
    return out


def _placement_for(row: Dict[str, Any]) -> str:
    """Where this story's date came from, reported and never guessed.

    ── ONE DEFINITION OF UNPLACED, SERVER AND BROWSER ──────────────────

    Corrected 2026-08-19 (WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01
    Commit 2). This function used to accept a year OR an era:

        if not row.get("estimated_year_low") and not (row.get("era_candidates") or []):
            return PLACEMENT_UNPLACED

    while the browser required an era (`story-evidence.js`: a row is
    placed only when it has an era AND a non-unplaced placement). A
    year-only placement was therefore PLACED on the server and UNPLACED
    on the Life Map, so the review panel could say "0 unplaced" while the
    map said "1 not yet placed in any era" -- two readers, one column,
    two answers, which is the exact thing this module was created to end.

    The era is the one that survives, because it is the one that can be
    true. The Life Map is drawn in eras; a story with a year and no era
    has nowhere to be drawn, so calling it placed is a claim no surface
    can honour. The year is not lost -- it stays on the row as data, and
    `placement_source` still records who supplied it.
    """
    source = str(row.get("placement_source") or "unknown").strip()
    placement = _SOURCE_TO_PLACEMENT.get(source, PLACEMENT_UNPLACED)
    if placement == PLACEMENT_UNPLACED:
        return PLACEMENT_UNPLACED
    # A recorded provenance with nothing to show for it is still unplaced.
    # This catches a row whose placement was set and later cleared.
    if not _era_of(row):
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


_SENTENCE_END = re.compile(r"[.!?](?=\s|$)")


def _clip_to_boundary(text: str, max_chars: int) -> str:
    """Trim to the bound without leaving a sentence visibly unfinished.

    WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01 Commit 1 (2026-08-19).

    Observed live on 2026-08-19: an approved story was read back to the
    narrator ending `"...and about the little house her own mother"` --
    a hard slice at 240 characters, mid-sentence. The bound was doing its
    job; the CUT was the problem. Lori reciting a narrator's own words and
    stopping mid-breath reads as though the recording failed.

    The bound is unchanged and still absolute. Preference order:

      1. the last complete sentence that fits -- the best outcome, because
         nothing looks truncated at all;
      2. failing that, the last whole word, with an ellipsis, so the
         reader can SEE that more exists;
      3. never a raw mid-word slice.

    Rule 2 keeps the ellipsis inside `max_chars` rather than appending
    past it: a bound that the tidy-up quietly exceeds is not a bound.
    A very long first sentence therefore still shortens -- it just
    shortens honestly.
    """
    body = " ".join(str(text or "").split()).strip()
    try:
        limit = int(max_chars)
    except (TypeError, ValueError):
        return body
    if limit <= 0:
        return ""
    if len(body) <= limit:
        return body

    window = body[:limit]
    ends = [m.end() for m in _SENTENCE_END.finditer(window)]
    if ends:
        # A sentence that fits is not a truncation, so it gets no
        # ellipsis. Guard against a lone leading "." producing a stub.
        clipped = window[:ends[-1]].strip()
        if len(clipped) >= 40:
            return clipped

    ellipsis = "…"
    cut = window.rfind(" ")
    if cut <= 0:
        # One enormous unbroken token. Nothing safe to break on, so the
        # bound wins and the ellipsis says so.
        return window[:max(0, limit - 1)].rstrip() + ellipsis
    trimmed = window[:cut].rstrip(" ,;:-—")
    if len(trimmed) + 1 > limit:
        trimmed = trimmed[:limit - 1].rstrip()
    return trimmed + ellipsis


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
        # ── AN UNPLACED STORY CARRIES NO DATE INTO THE PROMPT ───────────
        #
        # Corrected 2026-08-19. `era` and `year` were forwarded verbatim
        # and `placement` was shipped beside them and read by nobody:
        # `_approved_story_block` renders `(year)` else `(era)`, and the
        # recall block does `year or era`. So a story whose placement was
        # never made -- a machine era candidate, a DOB-derived guess --
        # was spoken back to the narrator with a date as though an
        # operator had set it. TRUTH 2 of this module says unknown
        # placement is not called stated; the consumers could not honour
        # that because the payload made it optional to.
        #
        # Withholding here is the fix rather than patching each consumer,
        # because a consumer that has to remember is one that eventually
        # forgets. The story still reaches Lori in full; only the claim
        # about WHEN it happened is withheld, and only when nobody made
        # it.
        _placed = item.get("placement") != PLACEMENT_UNPLACED
        approved.append({
            "id": item["id"],
            "text": _clip_to_boundary(excerpt, max_chars),
            "era": item.get("era") if _placed else None,
            "year": item.get("year") if _placed else None,
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
