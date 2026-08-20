"""ONE canonical memoir read. What the operator sees is what exports.

WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01, Commit B (2026-08-19).

── THE DEFECT THIS EXISTS TO END ───────────────────────────────────────

Three surfaces produced the narrator's memoir and none of them agreed:

  * the memoir PANEL built its own view from `/api/facts/list` and the
    in-browser threads/draft state;
  * the TXT export serialised whatever the panel happened to be showing;
  * the DOCX export took the browser's payload and then, server-side and
    invisibly, APPENDED reviewed captured stories and approved trip notes.

So the reviewed evidence -- the narrator's own words, the part the whole
review pipeline exists to protect -- appeared in the DOCX and in neither
of the other two. An operator approved a story, looked at the preview,
saw no sign of it, and exported a document containing it. The reverse is
worse and equally possible: prose the operator wrote INCORPORATING a
story, plus the same story appended again underneath, because the visible
prose carried no source id and nothing could tell they were the same
telling.

This module is the single read. Every surface consumes it, so "what the
operator sees is what will be exported" becomes a property of the system
rather than a habit of whoever last edited a renderer.

── WHAT IT IS NOT ──────────────────────────────────────────────────────

It is a READ. It writes nothing, promotes nothing and places nothing.
Eligibility, placement, era and language all come from
`story_projection`, which is already the one interpretation of review
state; this module composes lanes and never re-decides them.

Operator-authored prose is NOT evidence and is not returned here. It
belongs to the editing surface and stays there -- the point of this
contract is that the operator can see the evidence their document will
contain, not that the server takes over authorship.

── LANE AVAILABILITY IS PART OF THE ANSWER ─────────────────────────────

Each lane reports `read` / `empty` / `not_attempted` / `partial` /
`unavailable`. A caller that cannot read a lane must be able to say so:
rendering an unreadable lane as zero is how a memoir comes to look
complete while missing a chapter, and the person who would notice is the
one who will never see it.
"""
from __future__ import annotations

import hashlib
import logging
import os
from typing import Any, Dict, List, NamedTuple, Optional

logger = logging.getLogger("memoir_contract")

__all__ = ["CanonicalMemoir", "canonical_memoir", "story_source_id",
           "trip_note_source_id", "LANE_STATUSES"]

#: The shared vocabulary. `empty` is separate from `read` so a caller can
#: say which happened without also counting rows.
LANE_STATUSES = ("read", "empty", "not_attempted", "partial", "unavailable")


def story_source_id(candidate_id: str) -> str:
    """Stable, non-identifying id for one captured story.

    A raw narrator or candidate UUID must not appear in a document a
    family reads, and a memoir with no provenance cannot be traced back
    to the turn it came from. A digest is stable across reads, reveals
    nothing on its face, and is what makes "exactly once" enforceable
    across preview, TXT and DOCX.
    """
    return hashlib.sha256(
        f"story:{candidate_id}".encode("utf-8")).hexdigest()[:12]


def trip_note_source_id(note_id: str) -> str:
    """The same, for one approved trip note.

    Namespaced apart from stories so a note and a candidate that happened
    to share an id can never collide.
    """
    return hashlib.sha256(
        f"tripnote:{note_id}".encode("utf-8")).hexdigest()[:12]


class CanonicalMemoir(NamedTuple):
    """Every reviewed item a narrator's memoir may contain, once each."""

    person_id: str
    stories: List[Dict[str, Any]]
    trip_notes: List[Dict[str, Any]]
    lanes: Dict[str, str]

    @property
    def complete(self) -> bool:
        """True when no requested lane is partial or unavailable.

        `not_attempted` does not spoil completeness: it means a feature
        is switched off for this deployment, which is a configuration
        answer rather than a failure. An export may proceed; a caller
        that wants to say so has the per-lane status.
        """
        return not any(v in ("partial", "unavailable")
                       for v in self.lanes.values())

    def as_dict(self) -> Dict[str, Any]:
        return {
            "person_id": self.person_id,
            "stories": self.stories,
            "trip_notes": self.trip_notes,
            "lanes": self.lanes,
            "complete": self.complete,
        }


def _stories(person_id: str) -> (List[Dict[str, Any]], str):
    try:
        from . import story_projection as _sp
        projection = _sp.memoir_projection(person_id)
    except Exception as exc:
        logger.warning("[memoir-contract] story lane failed: %s", exc)
        return [], "unavailable"
    if not projection.available:
        return [], projection.status

    out: List[Dict[str, Any]] = []
    seen: set = set()
    for row in projection.items:
        cid = row.get("id")
        # Exactly once BY ID. Deliberately not deduplicated by text: two
        # tellings of one memory are two things the narrator said, and
        # collapsing them would be the system choosing which of a
        # person's own words to discard.
        if not cid or cid in seen:
            continue
        seen.add(cid)
        out.append({
            "source_id": story_source_id(cid),
            "text": row.get("transcript") or "",
            "era": row.get("era"),
            "year": row.get("year"),
            "placement": row.get("placement"),
            "language": row.get("language") or "en",
            "review_status": row.get("review_status"),
            "lane": "captured_story",
        })
    return out, ("read" if out else "empty")


def _trip_notes(person_id: str) -> (List[Dict[str, Any]], str):
    if os.getenv("HORNELORE_TRIPS", "0").strip().lower() not in (
        "1", "true", "yes", "on",
    ):
        return [], "not_attempted"
    try:
        from . import trip_repository as _tr
        trips = _tr.trip_list(person_id)
    except Exception as exc:
        logger.warning("[memoir-contract] trip list unreadable: %s", exc)
        return [], "unavailable"
    if not trips:
        return [], "empty"

    def _order(t: Dict[str, Any]):
        start = (t.get("start_date") or "").strip()
        return (0, start) if start else (1, (t.get("created_at") or ""))

    out: List[Dict[str, Any]] = []
    seen: set = set()
    unreadable = 0
    for trip in sorted(trips, key=_order):
        trip_id = trip.get("id")
        if not trip_id:
            continue
        try:
            notes = _tr.location_notes_list(trip_id)
        except Exception as exc:
            # PARTIAL, not skipped. A single unreadable trip used to be
            # `continue`d past, producing a memoir that looked complete.
            logger.warning("[memoir-contract] trip %s unreadable: %s",
                           trip_id, exc)
            unreadable += 1
            continue
        for n in notes:
            if not n.get("include_in_memoir"):
                continue
            note_id = n.get("id")
            text = (n.get("note_text") or "").strip()
            if not note_id or not text or note_id in seen:
                continue
            seen.add(note_id)
            out.append({
                "source_id": trip_note_source_id(note_id),
                "text": text,
                "title": (n.get("note_title") or "").strip(),
                "trip_id": trip_id,
                "trip_title": (trip.get("title") or "").strip(),
                # `target_language` is the column that exists; see the
                # note in memoir_export._trip_story_sections for why it
                # is read as the note's own language.
                "language": str(n.get("target_language") or "").strip().lower() or "en",
                "lane": "trip_note",
            })
    if unreadable:
        return out, "partial"
    return out, ("read" if out else "empty")


def canonical_memoir(person_id: str, *,
                     include_stories: bool = True,
                     include_trip_notes: bool = True) -> CanonicalMemoir:
    """The one reviewed-evidence read every memoir surface consumes."""
    lanes: Dict[str, str] = {}
    stories: List[Dict[str, Any]] = []
    trips: List[Dict[str, Any]] = []

    if include_stories:
        stories, lanes["captured_stories"] = _stories(person_id)
    else:
        lanes["captured_stories"] = "not_attempted"

    if include_trip_notes:
        trips, lanes["trip_notes"] = _trip_notes(person_id)
    else:
        lanes["trip_notes"] = "not_attempted"

    return CanonicalMemoir(person_id=person_id, stories=stories,
                           trip_notes=trips, lanes=lanes)
