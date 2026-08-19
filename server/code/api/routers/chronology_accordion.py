"""WO-CR-01 — Chronology Accordion Router

Read-only endpoint that merges three lanes into a decade/year accordion payload:
  Lane A: world events from historical_events_1900_2026.json (cached at startup)
  Lane B: verified personal anchors from promoted truth / profile / questionnaire
  Lane C: ghost prompt cues from static life-stage templates

Authority contract: this endpoint NEVER writes to facts, timeline, questionnaire,
archive, or any other truth table.  It only READS.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional

from fastapi import APIRouter, HTTPException, Query

from .. import db
from ..db import (
    ensure_profile,
    ft_list_promoted,
    get_person,
    get_profile,
    get_questionnaire,
)
from ..flags import truth_v2_enabled
from ..life_spine import derive_life_spine
from ..lv_eras import LV_ERAS, legacy_key_to_era_id
from ..services import story_projection

logger = logging.getLogger("chronology_accordion")

router = APIRouter(prefix="/api", tags=["chronology"])

# ─── ERA / AGE MAP ────────────────────────────────────────────────
# WO-CANONICAL-LIFE-SPINE-01 Step 4: TIMELINE_ORDER and ERA_AGE_MAP are
# now derived from the canonical lv_eras.LV_ERAS registry — same source
# the frontend reads from window.LorevoxEras.LV_ERAS, so the spine
# taxonomy lives in exactly one place. Today is filtered out of the
# age-derived scaffold (selected explicitly, never age-derived).
TIMELINE_ORDER = [
    e["era_id"] for e in LV_ERAS
    if e["era_id"] != "today" and e.get("ageStart") is not None
]

ERA_AGE_MAP = {
    e["era_id"]: {"start": e["ageStart"], "end": e["ageEnd"]}
    for e in LV_ERAS
    if e["era_id"] != "today" and e.get("ageStart") is not None
}

# ─── HISTORICAL SEED (loaded once, cached) ────────────────────────
_SEED_CACHE: Optional[List[Dict[str, Any]]] = None


def _seed_path() -> Path:
    """Resolve the historical events JSON file relative to the server dir."""
    return (
        Path(__file__).resolve().parents[3]  # routers → api → code → server
        / "data" / "historical" / "historical_events_1900_2026.json"
    )


def load_historical_seed() -> List[Dict[str, Any]]:
    """Load historical events from disk on first call, cache thereafter."""
    global _SEED_CACHE
    if _SEED_CACHE is not None:
        return _SEED_CACHE

    seed_file = _seed_path()
    if not seed_file.exists():
        logger.warning("Historical seed file not found: %s", seed_file)
        _SEED_CACHE = []
        return _SEED_CACHE

    with open(seed_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    events = data.get("events", [])
    _SEED_CACHE = events
    logger.info("Loaded %d historical events from seed file", len(events))
    return _SEED_CACHE


# ─── SCAFFOLD ─────────────────────────────────────────────────────

def build_scaffold_periods(
    birth_year: int,
    birth_place: str = "",
    include_today: bool = True,
) -> List[Dict[str, Any]]:
    """Build the canonical life-period spine from birth year.

    WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 commit 3 (2026-08-16).

    THIS IS THE ONLY CHRONOLOGY ENGINE. The Life Map used to compute its
    own periods in the browser (`app.js initTimelineSpine`) and persist
    them to localStorage under `lorevox.spine.<pid>`, so there was no
    server row to reconcile a second browser against. Rather than add a
    second server engine beside this one, the projection this endpoint
    already builds is extended and the browser consumes it.

    CANONICAL STRUCTURE, unchanged: SIX historical eras PLUS the separate
    `today` current-life bucket. Today is NOT removed and NOT folded into
    later_years -- it is a bucket the narrator/operator selects
    explicitly, never one that birth-year arithmetic produces, which is
    why it carries `start_year: None` and `is_current_life: True`.
    `year_to_era` skips it for exactly that reason.

    Each period now carries `era_id` alongside `label` (both hold the
    canonical era_id, per WO-CANONICAL-LIFE-SPINE-01 Step 3d) plus the
    places/notes/is_approximate keys the browser spine has always had, so
    a Life Map renderer can consume this payload directly.
    """
    place = (birth_place or "").strip()
    periods: List[Dict[str, Any]] = []
    for idx, label in enumerate(TIMELINE_ORDER):
        ages = ERA_AGE_MAP[label]
        periods.append({
            "era_id": label,
            "label": label,
            "start_year": birth_year + ages["start"],
            "end_year": (birth_year + ages["end"]) if ages["end"] is not None else None,
            "is_approximate": True,
            "is_current_life": False,
            "places": [place] if (idx == 0 and place) else [],
            "people": [],
            "notes": [f"Born in {place}"] if (idx == 0 and place) else [],
            "source": "derived",
            "status": "derived",
        })

    if include_today:
        today = _BY_ID_TODAY()
        if today:
            periods.append({
                "era_id": today["era_id"],
                "label": today["era_id"],
                "start_year": None,
                "end_year": None,
                "is_approximate": False,
                # The flag that keeps Today out of year->era math while
                # keeping it IN the canonical taxonomy.
                "is_current_life": True,
                "places": [],
                "people": [],
                "notes": [],
                "source": "canonical",
                "status": "current_life",
            })
    return periods


def _BY_ID_TODAY() -> Optional[Dict[str, Any]]:
    for era in LV_ERAS:
        if era.get("era_id") == "today":
            return era
    return None


# ─── UNIFIED PROJECTION LANES ─────────────────────────────────────
# WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 commit 3 (2026-08-16).
#
# Three lanes the Life Map needed and this payload did not carry:
# confirmed timeline events, story evidence WITH its review status, and
# trip DAYS rather than a single trip heading. They live here because
# the supervisor requirement is one projection contract, not a second
# engine beside this one.
#
# All three are READ-ONLY and all three FAIL SOFT: a missing table on an
# older database is not a defect, and a lane that fails must not take the
# rest of the chronology down with it. What it must not do is fail
# silently, so `_sources_block` reports the status of every lane.


class _LaneResult(NamedTuple):
    """One lane's rows AND whether the lane could be read at all.

    WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 Phase 2, Part A.

    THE DEFECT THIS TYPE EXISTS TO FIX. Until Phase 2 the three
    collectors below returned a bare list and swallowed every exception
    into `return []`, while `_sources_block` hardcoded `"status":
    "read"`. So a lane whose table was missing, whose database could not
    be opened, or whose query raised produced *exactly* the payload of a
    lane that was read successfully and found nothing:
    `{"status": "read", "count": 0}`.

    That is the one distinction `_sources_block`'s own docstring promises
    to make -- "this narrator has none" versus "this lane could not be
    read" -- and it was the one distinction the payload could not
    express. A renderer drawing an empty column from it would be
    reporting an outage as an answer.

    Failing soft is still right: a pre-0027 database legitimately has no
    `trip_days` table, and one lane must not take the chronology down.
    Failing soft SILENTLY is what changes here.
    """

    items: List[Dict[str, Any]]
    status: str  # "read" | "unavailable"


# Emitted when a lane raised. Distinct from "read" so a consumer can tell
# an outage from an empty narrator, and distinct from the periods lane's
# "unavailable_no_dob", which is a narrator STATE rather than a failure.
_LANE_UNAVAILABLE = "unavailable"
_LANE_READ = "read"


def _sources_block(
    dob_ok: bool,
    timeline_events: Optional[_LaneResult] = None,
    story_evidence: Optional[_LaneResult] = None,
    trip_days: Optional[_LaneResult] = None,
) -> Dict[str, Any]:
    """Truthful per-lane provenance, so a consumer never has to guess.

    `status` distinguishes "this narrator has none" from "this lane could
    not be read" -- the distinction the Life Map has to make before it
    renders an empty column as though it were an answer.

    Phase 2: each lane's status now comes FROM THE LANE. Passing `None`
    means the lane was never attempted (the no-DOB early return), which
    is a third state again and is reported as `not_attempted` rather than
    borrowing either of the other two.
    """

    def _lane(source: str, result: Optional[_LaneResult]) -> Dict[str, Any]:
        if result is None:
            return {"source": source, "status": "not_attempted", "count": 0}
        return {
            "source": source,
            "status": result.status,
            # A failed lane reports zero rows because it HAS zero rows in
            # hand -- the count is honest, and `status` is what says the
            # zero is not an answer about the narrator.
            "count": len(result.items),
        }

    return {
        "periods": {
            "source": "lv_eras + profile.dob",
            "status": "derived" if dob_ok else "unavailable_no_dob",
        },
        "timeline_events": _lane("timeline_events", timeline_events),
        "story_evidence": _lane("story_candidates", story_evidence),
        "trip_days": _lane("trips + trip_days", trip_days),
        "authority": "server",
    }


def _year_of(value: Any) -> Optional[int]:
    text = str(value or "").strip()
    if len(text) < 4 or not text[:4].isdigit():
        return None
    return int(text[:4])


def _lane_counts(*, world, personal, personal_derived, ghost,
                 timeline_events, story_evidence, trip_days) -> Dict[str, Any]:
    """Per-lane totals, with `null` where the count is not known.

    WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01 Commit 3 (2026-08-19).

    This block used to be seven `len()` calls. `_sources_block` already
    distinguished `read` / `unavailable` / `not_attempted`, but the counts
    beside it did not: a lane whose query raised produced
    `story_evidence: 0`, byte-identical to a narrator who has never told
    a story. Anything reading `lane_counts` alone -- and the browser's own
    diagnostic log did, with `?? 0` -- turned an outage into a fact about
    a person's life.

    `None` serialises to JSON `null`, which a renderer cannot mistake for
    zero the way it can mistake `0`. The three DOB-derived lanes are
    passed as plain lists (or None when they were never computed, which
    is the no-DOB case); the three independently-readable lanes are
    passed as `_LaneResult` so their status decides.
    """
    def _n(value):
        if value is None:
            return None
        if isinstance(value, _LaneResult):
            return len(value.items) if value.status == "read" else None
        return len(value)

    return {
        "world": _n(world),
        "personal": _n(personal),
        "personal_derived": _n(personal_derived),
        "ghost": _n(ghost),
        "timeline_events": _n(timeline_events),
        "story_evidence": _n(story_evidence),
        "trip_days": _n(trip_days),
    }


def _collect_timeline_events(person_id: str) -> _LaneResult:
    """Confirmed timeline events. Status is reported, never assumed."""
    try:
        con = db._connect()
    except Exception as exc:
        logger.info(
            "chronology: timeline_events lane unavailable for %s (no connection): %s",
            person_id, exc,
        )
        return _LaneResult([], _LANE_UNAVAILABLE)
    try:
        rows = con.execute(
            "SELECT id, date, title, body, kind, status, is_approximate, confidence "
            "FROM timeline_events WHERE person_id=? ORDER BY date;",
            (person_id,),
        ).fetchall()
    except Exception as exc:
        logger.info("chronology: timeline_events lane skipped for %s: %s", person_id, exc)
        return _LaneResult([], _LANE_UNAVAILABLE)
    finally:
        con.close()

    items: List[Dict[str, Any]] = []
    for r in rows:
        year = _year_of(r["date"])
        if year is None:
            continue
        items.append({
            "id": r["id"],
            "year": year,
            "date": r["date"],
            "label": r["title"] or "",
            "body": r["body"] or "",
            "kind": r["kind"] or "event",
            "lane": "personal",
            "source": "timeline_events",
            # An operator-entered event is confirmed unless the row says
            # otherwise. Reported from the column rather than inferred.
            "status": (r["status"] or "confirmed"),
            "is_approximate": bool(r["is_approximate"]) if r["is_approximate"] is not None else False,
        })
    return _LaneResult(items, _LANE_READ)


# WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 Phase 3, Commit A (2026-08-17).
#
# `_STORY_STATUS` and the stated/derived rule USED TO LIVE HERE. They were
# one of four separate interpretations of `review_status` in this
# repository, and the duplication is what Phase 3 removes: the canonical
# reading now lives in `services/story_projection.py` and this lane
# consumes it, so the Life Map, the memoir, Lori and the operator surface
# cannot disagree about whether a story is approved.
#
# The retired rule is quoted rather than deleted, because it is the reason
# the `placement_source` column exists:
#
#     placement = "stated" if year_low and r["confidence"] == "high" else "derived"
#
# That inferred PROVENANCE from CONFIDENCE. Confidence is set at capture
# time from the trigger heuristic and says nothing about who decided when
# a story happened -- and since nothing ever set it above "medium", the
# expression could only ever return "derived". Provenance is now recorded
# rather than guessed, and an unrecorded placement reports `unplaced`.


def _collect_story_evidence(person_id: str) -> _LaneResult:
    """Captured stories, carrying approved / provisional status.

    A thin adapter over the canonical projection. It maps the projection's
    lane status onto this module's `_LaneResult` and adds the two keys the
    accordion payload has always carried (`excerpt`, `extraction_status`);
    it makes no judgement of its own about any story.
    """
    projection = story_projection.project_stories(person_id)
    if projection.status != "read":
        return _LaneResult([], _LANE_UNAVAILABLE)

    items: List[Dict[str, Any]] = []
    for row in projection.items:
        items.append({
            "id": row["id"],
            "year": row.get("year"),
            "year_high": row.get("year_high"),
            "era_candidates": row.get("era_candidates") or [],
            "excerpt": row.get("excerpt") or "",
            "word_count": row.get("word_count"),
            "lane": "story",
            "source": "story_candidates",
            "status": row["status"],
            "review_status": row["review_status"],
            "extraction_status": row.get("extraction_status") or "pending",
            "placement": row["placement"],
            "placement_source": row.get("placement_source") or "unknown",
            "confidence": row.get("confidence") or "low",
        })
    return _LaneResult(items, _LANE_READ)


def _collect_trip_days(person_id: str) -> _LaneResult:
    """Trip DAYS, not merely a trip heading.

    A trip rendered as one row loses the thing the narrator actually
    remembers -- the individual days. Each day is returned with its own
    date and place so the chronology can place it.
    """
    try:
        con = db._connect()
    except Exception as exc:
        logger.info(
            "chronology: trip_days lane unavailable for %s (no connection): %s",
            person_id, exc,
        )
        return _LaneResult([], _LANE_UNAVAILABLE)
    try:
        rows = con.execute(
            "SELECT d.id AS day_id, d.trip_id, d.day_index, d.date, d.title, "
            "d.main_location, d.lodging_base, t.title AS trip_title "
            "FROM trip_days d JOIN trips t ON t.id = d.trip_id "
            "WHERE t.person_id=? ORDER BY d.date, d.day_index;",
            (person_id,),
        ).fetchall()
    except Exception as exc:
        # A pre-0027 database legitimately has no trip_days table.
        logger.info("chronology: trip_days lane skipped for %s: %s", person_id, exc)
        return _LaneResult([], _LANE_UNAVAILABLE)
    finally:
        con.close()

    items: List[Dict[str, Any]] = []
    for r in rows:
        year = _year_of(r["date"])
        if year is None:
            continue
        items.append({
            "id": r["day_id"],
            "trip_id": r["trip_id"],
            "trip_title": r["trip_title"] or "",
            "day_index": r["day_index"],
            "year": year,
            "date": r["date"],
            "label": r["title"] or r["main_location"] or "",
            "main_location": r["main_location"] or "",
            "lodging_base": r["lodging_base"] or "",
            "lane": "travels",
            "source": "trip_days",
            # Travels is a special shelf, not a life era. Flagged so a
            # renderer does not fold it into the era taxonomy.
            "shelf": "travels",
            "status": "confirmed",
        })
    return _LaneResult(items, _LANE_READ)


def year_to_era(year: int, periods: List[Dict[str, Any]]) -> Optional[str]:
    """Map a calendar year to an era label using the periods list.

    If year falls after the last period's start (later_years with
    end=None), it maps to later_years.  Years before birth return None.
    Returns canonical era_id strings after WO-CANONICAL-LIFE-SPINE-01
    Step 4 (was legacy keys before the migration).
    """
    for p in periods:
        # WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 commit 3: `today` is a
        # current-life bucket selected explicitly, never derived from
        # birth-year arithmetic (this matches era_id_from_age, which has
        # never returned it). It now appears in `periods` as part of the
        # canonical taxonomy, so it is skipped here rather than removed
        # there.
        if p.get("is_current_life") or p.get("start_year") is None:
            continue
        start = p["start_year"]
        end = p.get("end_year")
        if end is None:
            # later_years — open-ended
            if year >= start:
                return p["label"]
        else:
            if start <= year <= end:
                return p["label"]
    return None


# ─── LANE A: WORLD EVENTS ────────────────────────────────────────

def filter_world_events(
    events: List[Dict[str, Any]],
    birth_year: int,
) -> List[Dict[str, Any]]:
    """Filter historical events to the narrator's lifetime.

    Only includes events from birth_year onward.
    Returns ChronologyItem-shaped dicts.
    """
    items = []
    for ev in events:
        yr = ev.get("year", 0)
        if yr < birth_year:
            continue
        items.append({
            "year": yr,
            "label": ev.get("label", ""),
            "lane": "world",
            "category": ev.get("category", ""),
            "tags": ev.get("tags", []),
            "id": ev.get("id", ""),
            # CR-04 provenance: world items are context-only; Lori must
            # never rephrase them as personal biography.
            "source": "historical_json",
        })
    return items


# ─── LANE B: PERSONAL ANCHORS ────────────────────────────────────
# WO-CR-PACK-01 strict authority model.
#
# Source priority (highest → lowest):
#   1. profile basics            — dob / pob (identity captured during onboarding)
#   2. questionnaire fallback    — personal.dateOfBirth / personal.placeOfBirth ONLY
#   3. promoted truth            — primary for expanded anchors (marriages, jobs,
#                                  moves, retirement, etc.)
#
# CRITICAL: expansion beyond birth identity comes from PROMOTED TRUTH ONLY.
# Questionnaire fallback is intentionally restricted to the two canonical birth
# identity fields so unreviewed answers never leak into the sidebar as verified
# anchors.
#
# Dedup uses compound event-kind keys, not generic field names:
#   single-occurrence  : birth:self / death:self
#   multi-occurrence   : marriage:{spouse}:{year} / child:{name}:{year} /
#                        move:{place}:{year} / work_begin:{employer}:{year} ...
# This keeps repeatables from colliding while keeping one-per-narrator anchors
# stable across source layers.

# ── Promoted-truth field whitelist ───────────────────────────────
# Keys = family_truth_promoted.field values produced by extraction + review.
# Spec carries: event_kind (dedup family), label, date (bool), and
# cardinality ("single" one-per-narrator; "multi" repeatable per narrator).
_PROMOTED_ANCHOR_FIELDS: Dict[str, Dict[str, Any]] = {
    # single-occurrence identity anchors
    "date_of_birth":           {"event_kind": "birth",       "label": "Born",            "date": True,  "cardinality": "single"},
    "place_of_birth":          {"event_kind": "birth_place", "label": "Birthplace",      "date": False, "cardinality": "single"},
    "date_of_death":           {"event_kind": "death",       "label": "Died",            "date": True,  "cardinality": "single"},
    # education
    "date_of_graduation":      {"event_kind": "graduation",  "label": "Graduated",       "date": True,  "cardinality": "multi"},
    # military service
    "date_of_military_service":{"event_kind": "military",    "label": "Military service","date": True,  "cardinality": "single"},
    "date_of_enlistment":      {"event_kind": "military",    "label": "Enlisted",        "date": True,  "cardinality": "single"},
    "date_of_discharge":       {"event_kind": "discharge",   "label": "Discharged",      "date": True,  "cardinality": "single"},
    # work / career
    "date_of_first_job":       {"event_kind": "work_begin",  "label": "First job",       "date": True,  "cardinality": "single"},
    "date_of_retirement":      {"event_kind": "retirement",  "label": "Retired",         "date": True,  "cardinality": "single"},
    # relationships
    "date_of_marriage":        {"event_kind": "marriage",    "label": "Married",         "date": True,  "cardinality": "multi"},
    "date_of_divorce":         {"event_kind": "divorce",     "label": "Divorced",        "date": True,  "cardinality": "multi"},
    # moves / residence
    "date_of_move":            {"event_kind": "move",        "label": "Moved",           "date": True,  "cardinality": "multi"},
    "date_of_immigration":     {"event_kind": "immigration", "label": "Immigrated",      "date": True,  "cardinality": "single"},
    # children (narrator-as-parent)
    "date_of_first_child":     {"event_kind": "child",       "label": "First child",     "date": True,  "cardinality": "multi"},
}

# ── Profile basics whitelist (fallback when promoted is empty) ───
# basics.dob + basics.pob combine into a single enriched "Born" anchor.
_PROFILE_ANCHOR_KEYS: Dict[str, Dict[str, Any]] = {
    "dob":          {"event_kind": "birth", "label": "Born",       "date": True,  "cardinality": "single"},
    "pob":          {"event_kind": "birth", "label": "Birthplace", "date": False, "cardinality": "single"},
    # dateOfDeath is allowed at basics level only if a trusted basics slot
    # carries it (not currently populated; wired for forward-compat).
    "dateOfDeath":  {"event_kind": "death", "label": "Died",       "date": True,  "cardinality": "single"},
}

# ── Questionnaire fallback — STRICT identity subset only ─────────
# CR-02 contract: questionnaire fallback is limited to canonical birth
# identity fields. Expanded anchors (marriage/child/job/move/etc.) MUST
# come from promoted truth, not raw questionnaire answers.
_QUESTIONNAIRE_ANCHOR_KEYS: Dict[str, Dict[str, Any]] = {
    "personal.dateOfBirth":   {"event_kind": "birth", "label": "Born",       "date": True,  "cardinality": "single"},
    "personal.placeOfBirth":  {"event_kind": "birth", "label": "Birthplace", "date": False, "cardinality": "single"},
    # dateOfDeath accepted only because it's still a canonical identity
    # field. No other questionnaire keys are promoted to Lane B — that
    # path is reserved for promoted truth.
    "personal.dateOfDeath":   {"event_kind": "death", "label": "Died",       "date": True,  "cardinality": "single"},
}


def _dedup_key_single(event_kind: str) -> str:
    """One-per-narrator anchor (e.g. birth:self, death:self)."""
    return f"{event_kind}:self"


def _dedup_key_multi(event_kind: str, identity: str, year: Optional[int]) -> str:
    """Repeatable anchor keyed by (kind, identity, year).

    identity is a qualifier like spouse name, child name, place, employer —
    whatever makes this instance distinct. Unknown identities fall back to
    the empty string, which still differentiates via year.
    """
    ident = (identity or "").strip().lower()
    yr = str(year) if year is not None else ""
    return f"{event_kind}:{ident}:{yr}"


def _extract_year(value: Any) -> Optional[int]:
    """Try to extract a 4-digit year from a value string.

    Accepts ISO dates (1962-12-24), US-style (12/24/1962), and bare years (1962).
    Returns None if no plausible year (1850-2100) is found.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    # Normalize separators so we can split once.
    parts = s.replace("-", " ").replace("/", " ").replace(",", " ").split()
    for p in parts:
        if len(p) == 4 and p.isdigit():
            yr = int(p)
            if 1850 <= yr <= 2100:
                return yr
    return None


def _flatten(obj: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    """Flatten nested dict keys so 'personal.dateOfBirth' becomes a top-level lookup."""
    out: Dict[str, Any] = {}
    if not isinstance(obj, dict):
        return out
    for k, v in obj.items():
        kp = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten(v, kp))
        else:
            out[kp] = v
    return out


def _promoted_identity(spec: Dict[str, Any], row: Dict[str, Any]) -> str:
    """Derive the identity qualifier for a multi-cardinality promoted anchor.

    For marriage / child / move / work_begin / work_end, the subject_name
    on the promoted row is the natural identity (spouse name, child name,
    place, employer). For single-cardinality anchors, identity is unused.
    """
    return (row.get("subject_name") or "").strip()


def project_personal_anchors(
    basics: Dict[str, Any],
    questionnaire: Dict[str, Any],
    promoted_rows: List[Dict[str, Any]],
    narrator_display_name: str = "",
) -> List[Dict[str, Any]]:
    """Extract verified personal anchors — narrator (self) only.

    Source order (highest → lowest):
      1. profile basics          — trusted identity fields (dob, pob)
      2. questionnaire           — STRICT subset: personal.dateOfBirth /
                                   placeOfBirth / dateOfDeath only
      3. promoted truth          — expansion layer (marriage, jobs, moves,
                                   retirement, etc.) — self-subject only

    Dedup: compound event-kind keys
      single-occurrence : "{event_kind}:self"                — one per narrator
      multi-occurrence  : "{event_kind}:{identity}:{year}"   — per instance

    Returns ChronologyItem-shaped dicts with lane='personal' and a
    provenance tag source in {"profile","questionnaire","promoted_truth"}.
    """
    items: List[Dict[str, Any]] = []
    seen_dedup: set = set()
    # Track whether the single "birth" anchor has been claimed (prevents
    # double-counting birth across profile/questionnaire/promoted layers).
    birth_claimed = False

    def _claim(dedup_key: str) -> bool:
        """Claim a dedup slot. Returns True if newly claimed, False if already taken."""
        if dedup_key in seen_dedup:
            return False
        seen_dedup.add(dedup_key)
        return True

    # Normalize inputs
    basics = basics or {}
    dob = str(basics.get("dob") or "").strip()
    pob = str(basics.get("pob") or "").strip()
    name_lower = (narrator_display_name or "").strip().lower()

    # ── 1. Profile basics (identity captured during onboarding) ─
    # Enriched "Born" anchor combining dob + pob when both are present.
    if dob:
        yr = _extract_year(dob)
        if yr is not None:
            key = _dedup_key_single("birth")
            if _claim(key):
                if pob:
                    label = f"Born — {pob}"
                else:
                    label = "Born"
                items.append({
                    "year": yr,
                    "label": label,
                    "lane": "personal",
                    "event_kind": "birth",
                    "dedup_key": key,
                    "source": "profile",
                })
                birth_claimed = True

    # Profile-level dateOfDeath (forward-compat slot — not populated today).
    dod_basics = str(basics.get("dateOfDeath") or "").strip()
    if dod_basics:
        yr = _extract_year(dod_basics)
        if yr is not None:
            key = _dedup_key_single("death")
            if _claim(key):
                items.append({
                    "year": yr,
                    "label": "Died",
                    "lane": "personal",
                    "event_kind": "death",
                    "dedup_key": key,
                    "source": "profile",
                })

    # ── 2. Questionnaire fallback (strict identity subset) ──────
    q_obj = questionnaire.get("questionnaire", {}) if questionnaire else {}
    flat = _flatten(q_obj)
    for q_key, spec in _QUESTIONNAIRE_ANCHOR_KEYS.items():
        if not spec["date"]:
            continue  # place-only keys don't produce year-indexed anchors
        val = flat.get(q_key)
        if val is None or str(val).strip() == "":
            continue
        yr = _extract_year(val)
        if yr is None:
            continue
        event_kind = spec["event_kind"]
        key = _dedup_key_single(event_kind)
        if not _claim(key):
            continue  # already claimed by profile (or earlier questionnaire key)

        # If we're filling in the "Born" slot from questionnaire, try to
        # attach a place hint from flat["personal.placeOfBirth"] so the
        # label still reads "Born — {pob}".
        if event_kind == "birth":
            q_pob = str(flat.get("personal.placeOfBirth") or "").strip()
            label = f"Born — {q_pob}" if q_pob else "Born"
        else:
            label = spec["label"]

        items.append({
            "year": yr,
            "label": label,
            "lane": "personal",
            "event_kind": event_kind,
            "dedup_key": key,
            "source": "questionnaire",
        })

    # ── 3. Promoted truth (expansion layer) ─────────────────────
    # Self-filter: only accept rows where subject is the narrator.
    # Non-date promoted rows are skipped (year-indexed accordion).
    for row in promoted_rows or []:
        field = (row.get("field") or "").strip()
        spec = _PROMOTED_ANCHOR_FIELDS.get(field)
        if not spec:
            continue
        if not spec["date"]:
            # place_of_birth etc. — not an anchor on its own; handled via
            # enriched birth label when both dob and pob are available.
            continue

        subject = (row.get("subject_name") or "").strip().lower()
        relationship = (row.get("relationship") or "").strip().lower()
        cardinality = spec.get("cardinality", "single")

        # Narrator-self filter. `relationship` is the authoritative signal:
        # anything flagged spouse/parent/child/friend belongs to a different
        # subject's timeline, not the narrator's.
        if relationship and relationship not in ("self", "narrator", ""):
            continue

        # subject_name self-check applies ONLY to single-cardinality events
        # (birth, death, retirement, first_job, immigration, etc.) where
        # subject_name should be the narrator. For multi-cardinality events
        # (marriage, child, move, work_begin, divorce, graduation),
        # subject_name is the event identity qualifier (spouse name, child
        # name, place, employer) — not a different-person marker.
        if cardinality == "single":
            if subject and name_lower and subject != name_lower:
                continue

        value = (row.get("value") or "").strip()
        if not value:
            continue
        yr = _extract_year(value)
        if yr is None:
            continue

        event_kind = spec["event_kind"]

        if cardinality == "single":
            key = _dedup_key_single(event_kind)
            label = spec["label"]
        else:
            identity = _promoted_identity(spec, row)
            key = _dedup_key_multi(event_kind, identity, yr)
            # Enrich label with identity qualifier when present.
            if identity:
                label = f"{spec['label']} — {identity}"
            else:
                label = spec["label"]

        if not _claim(key):
            continue

        items.append({
            "year": yr,
            "label": label,
            "lane": "personal",
            "event_kind": event_kind,
            "dedup_key": key,
            "source": "promoted_truth",
        })

    return items


# ─── LANE C: GHOST PROMPTS ───────────────────────────────────────
# One ghost per life-stage band, placed at midpoint year.

# WO-CANONICAL-LIFE-SPINE-01 Step 4: keys migrated to canonical era_ids.
# Today bucket is intentionally absent from this map — Today ghost
# prompts are not tied to a specific calendar year (they would otherwise
# get placed at a midpoint that doesn't make sense for "right now"). If
# a future WO wants Today ghosts on the chronology, they'd anchor at
# current_year, not at era midpoint.
_GHOST_TEMPLATES = {
    "earliest_years":     "What's your earliest memory from childhood?",
    "early_school_years": "What was school like for you growing up?",
    "adolescence":        "What were your teenage years like?",
    "coming_of_age":      "What was life like when you were first on your own?",
    "building_years":     "What stands out about your building years?",
    "later_years":        "What has this chapter of life been like for you?",
}


def build_band_ghosts(
    birth_year: int,
    periods: List[Dict[str, Any]],
    personal_items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Generate ghost prompt items — one per life-stage band at midpoint year.

    Suppresses ghost for a band if that band already has >=2 personal anchors.
    """
    # Count personal items per era
    era_counts: Dict[str, int] = {}
    for item in personal_items:
        era = year_to_era(item.get("year", 0), periods)
        if era:
            era_counts[era] = era_counts.get(era, 0) + 1

    items = []
    current_year = 2026  # cap for later_years (open-ended period end)

    for p in periods:
        label = p["label"]
        if label not in _GHOST_TEMPLATES:
            continue
        # Suppress if band already has 2+ personal anchors
        if era_counts.get(label, 0) >= 2:
            continue

        start = p["start_year"]
        end = p.get("end_year")
        if end is None:
            end = min(birth_year + 90, current_year)
        midpoint = (start + end) // 2

        items.append({
            "year": midpoint,
            "label": _GHOST_TEMPLATES[label],
            "lane": "ghost",
            "era": label,
            # CR-04 provenance: ghost items shape question style only;
            # never asserted as known history about the narrator.
            "source": "life_stage_template",
        })

    # WO-CANONICAL-LIFE-SPINE-01 Step 5: append a Today ghost at
    # current_year. Today is the present-life bucket — anchored
    # explicitly to the calendar year, NEVER derived from birth-year
    # math (per the canonical-spine lock: today is selected, never
    # age-derived). Suppress if Today already has personal anchors
    # (same 2+ rule as historical bands). Today's prompt text is
    # forward-looking and present-tense, matching prompt_composer's
    # Pass 2A Today branch.
    if era_counts.get("today", 0) < 2:
        items.append({
            "year": current_year,
            "label": "What does life look like for you today — your routines, the people you see most, what's on your mind?",
            "lane": "ghost",
            "era": "today",
            "source": "life_stage_template",
        })

    return items


# ─── GROUP BY DECADE ──────────────────────────────────────────────

def group_by_decade(
    items: List[Dict[str, Any]],
    periods: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Group items into decade buckets, each containing year sub-groups.

    Returns:
      [
        {
          "decade": 1940,
          "decade_label": "1940s",
          "years": [
            {
              "year": 1940,
              "era": "earliest_years",
              "items": [ ... ]
            },
            ...
          ]
        },
        ...
      ]
    Sorted by decade ascending, years ascending within each decade.
    """
    # Collect items by decade → year
    decade_map: Dict[int, Dict[int, List[Dict[str, Any]]]] = {}
    for item in items:
        yr = item.get("year", 0)
        decade = (yr // 10) * 10
        if decade not in decade_map:
            decade_map[decade] = {}
        if yr not in decade_map[decade]:
            decade_map[decade][yr] = []
        decade_map[decade][yr].append(item)

    # Build sorted output.
    # CR-01B: Within each year, enforce lane priority so personal anchors
    # always appear above ghost prompts, and both above world context.
    # Without this sort, items render in Lane A+B+C concat order, which
    # pushes the narrator's own anchors below Cold War trivia.
    _LANE_PRIORITY = {"personal": 0, "ghost": 1, "world": 2}
    result = []
    for decade in sorted(decade_map.keys()):
        year_groups = []
        for yr in sorted(decade_map[decade].keys()):
            era = year_to_era(yr, periods)
            items_sorted = sorted(
                decade_map[decade][yr],
                key=lambda x: _LANE_PRIORITY.get(x.get("lane"), 9),
            )
            year_groups.append({
                "year": yr,
                "era": era,
                "items": items_sorted,
            })
        result.append({
            "decade": decade,
            "decade_label": f"{decade}s",
            "years": year_groups,
        })

    return result


# ─── MAIN BUILDER ─────────────────────────────────────────────────

def build_chronology_accordion_payload(
    person_id: str,
    profile: Dict[str, Any],
    questionnaire: Dict[str, Any],
    promoted_rows: List[Dict[str, Any]],
    narrator_display_name: str = "",
) -> Dict[str, Any]:
    """Build the full chronology accordion payload.

    Returns the complete JSON response shape for the frontend.
    """
    # Normalize incoming profile shape.  Accepts:
    #   {"basics": {...}}           → use the basics sub-dict
    #   {"dob": ..., "pob": ...}    → already a basics dict
    if isinstance(profile, dict) and "basics" in profile:
        basics = profile["basics"] or {}
    else:
        basics = profile or {}

    # Extract birth year
    dob = basics.get("dob", "")
    birth_year = None
    if dob:
        try:
            birth_year = int(str(dob).strip()[:4])
        except (ValueError, IndexError):
            pass

    if not birth_year:
        # A narrator who has not given a date of birth has no derivable
        # HISTORICAL chronology yet. That is a STATE, not a failure, and
        # the Life Map must be able to tell the difference. `today` still
        # appears: current life does not depend on a birth year.
        #
        # ── BUT THREE LANES DO NOT DEPEND ON DOB, 2026-08-19 ─────────
        #
        # This branch used to return `story_evidence: []`, `trip_days: []`
        # and `timeline_events: []` with `_sources_block(dob_ok=False)`,
        # so the lanes were never even queried. Captured stories, confirmed
        # timeline events and trip days are all readable without a birth
        # year -- only ERA DERIVATION needs one.
        #
        # The cost was borne by exactly the narrator least able to
        # afford it: someone brand new, who has told Lori several stories
        # and not yet given a date of birth, saw an empty Life Map that
        # was indistinguishable from having said nothing at all. Their
        # stories existed, were preserved, and were invisible.
        #
        # So the lanes are read and reported truthfully. What is withheld
        # is only what cannot be computed: decades stay empty, periods
        # stay at `today`, and every story is UNPLACED until an operator
        # supplies a canonical era. Unplaced is an honest state; absent
        # was not.
        no_dob_timeline = _collect_timeline_events(person_id)
        no_dob_stories = _collect_story_evidence(person_id)
        no_dob_trips = _collect_trip_days(person_id)
        return {
            "person_id": person_id,
            "decades": [],
            "periods": build_scaffold_periods(0, "", include_today=True)[-1:],
            "birth_year": None,
            "birth_date": dob or "",
            "birth_place": basics.get("pob", "") or "",
            "seed_ready": False,
            "reason": "no_dob",
            "error": "no_dob",
            "timeline_events": no_dob_timeline.items,
            "story_evidence": no_dob_stories.items,
            "trip_days": no_dob_trips.items,
            "sources": _sources_block(
                dob_ok=False,
                timeline_events=no_dob_timeline,
                story_evidence=no_dob_stories,
                trip_days=no_dob_trips,
            ),
            "lane_counts": _lane_counts(
                world=None, personal=None, personal_derived=None, ghost=None,
                timeline_events=no_dob_timeline,
                story_evidence=no_dob_stories,
                trip_days=no_dob_trips,
            ),
        }

    # Build periods (prefer spine if available, else scaffold).
    # WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 commit 3: birth place is
    # threaded through so the Life Map can render from this payload
    # instead of from its own browser-local spine.
    periods = build_scaffold_periods(birth_year, basics.get("pob", "") or "")

    # Load all three lanes
    seed = load_historical_seed()
    lane_a = filter_world_events(seed, birth_year)
    lane_b = project_personal_anchors(
        basics, questionnaire, promoted_rows,
        narrator_display_name=narrator_display_name,
    )

    # WO-LIFE-SPINE-01: derive school-years projection from DOB, add as
    # source='derived' Lane B entries. Dedup against existing Lane B items
    # (which carry source profile/questionnaire/promoted_truth) by event_kind
    # so a confirmed school_graduation never gets a ghost duplicate.
    #
    # Override propagation: any Lane B item whose event_kind matches a spine
    # entry counts as "confirmed" and shifts the spine offset accordingly.
    confirmed_for_spine: List[Dict[str, Any]] = [
        {
            "event_kind": item.get("event_kind"),
            "year": item.get("year"),
            "source": item.get("source"),
        }
        for item in lane_b
        if item.get("event_kind") and item.get("year") is not None
    ]
    # Pass the full profile to the spine so the family catalog can read
    # children. Other catalogs ignore facts. basics-only or full-profile
    # shapes are both accepted by the family catalog's _collect_children.
    spine_items = derive_life_spine(
        dob,
        confirmed_events=confirmed_for_spine,
        facts=profile if isinstance(profile, dict) else basics,
    )
    # Drop spine items whose event_kind already exists in Lane B (dedup).
    existing_kinds = {it.get("event_kind") for it in lane_b if it.get("event_kind")}
    spine_items = [it for it in spine_items if it.get("event_kind") not in existing_kinds]
    lane_b_with_spine = lane_b + spine_items

    # WO-TRIP-IMPORT-AND-CLUSTER-01 Phase B (2026-07-05): trips are
    # part of the life record — project each dated trip as a personal
    # anchor so the chronology accordion (and the era buckets it feeds)
    # show the journey alongside births, schools, and promoted truth.
    # Guarded import + failure tolerance: the accordion must render
    # even if the trip tables are absent (pre-0015 DB) or the trips
    # feature is off; trips data, once present, is canonical rows, so
    # it renders regardless of the HORNELORE_TRIPS API gate.
    # S8 (SECURITY/STABILITY-REVIEW-2026-08-12): this block used to
    # swallow every failure silently — `except Exception: trip_items = []`
    # with no log line — so a trips-schema problem, a missing migration or
    # a bad JSON column rendered as "this narrator has no trips", which is
    # indistinguishable from the truth. An operator debugging a missing
    # trip had nothing to look at. Failures are now logged and, where
    # possible, isolated to the trip that caused them.
    trip_items: List[Dict[str, Any]] = []
    try:
        from ..services import trip_repository as _trips_repo
        for _t in _trips_repo.trip_list(person_id):
            # S8: per-trip isolation. One malformed trip row used to take
            # the WHOLE lane down (and discard the trips already
            # collected); now it costs only itself.
            #
            # `_tid` is read INSIDE the try and defaulted here, because
            # the handler below must not touch the row again: a row that
            # raises on .get() would make the error log itself raise,
            # the exception would escape to the outer handler, and the
            # loop would stop — losing every trip after the bad one,
            # which is the failure this isolation exists to prevent.
            # (Caught by the regression test, not by reading the code.)
            _tid = None
            try:
                _tid = _t.get("id")
                _yr_src = _t.get("start_date") or _t.get("end_date") or ""
                try:
                    _yr = int(str(_yr_src)[:4])
                except (TypeError, ValueError):
                    continue
                # Photo strip (2026-07-05, per Chris): up to 6 memoir-
                # included photo links ride on the timeline item so the
                # accordion can render thumbnails; each carries what the
                # narrator lightbox needs (caption, date, stop name). The
                # FE composes /api/photos/{id}/thumb and /image URLs.
                _photos: List[Dict[str, Any]] = []
                try:
                    # Review fix 2026-07-05 (N+1): stop names come from the
                    # photo-links join (LEFT JOIN trip_stops) instead of a
                    # full trip_tree walk per trip — one query per trip.
                    for _link in _trips_repo.photo_links_with_photo_paths(
                            _t["id"], memoir_only=True):
                        # BUG-238 precedent: the narrator room shows ONLY
                        # curator-vetted photos (narrator_ready=1) — the
                        # accordion is narrator-visible, so unvetted intake
                        # photos must not leak here.
                        if not _link.get("photo_narrator_ready"):
                            continue
                        if len(_photos) >= 6:
                            break
                        _photos.append({
                            "photo_id": _link.get("photo_id"),
                            "caption": (
                                _link.get("narrator_caption")
                                or _link.get("caption")
                                or _link.get("photo_description")
                                or ""
                            ),
                            "taken_at": (
                                _link.get("taken_at")
                                or _link.get("photo_date_value")
                                or ""
                            ),
                            "stop_name": _link.get("stop_location_name") or "",
                        })
                except Exception as exc:
                    # S8: was silent. A broken photo strip now costs the
                    # thumbnails for THIS trip and says so; the trip
                    # itself still renders.
                    logger.warning(
                        "chronology: trip photo strip failed for trip=%s "
                        "person=%s: %s", _tid, person_id, exc,
                    )
                    _photos = []
                trip_items.append({
                    "year": _yr,
                    "label": f"Trip — {_t.get('title') or 'Journey'}",
                    "lane": "personal",
                    "event_kind": "trip",
                    "dedup_key": f"trip:{_t.get('id')}",
                    "source": "trip",
                    "photos": _photos,
                })
            except Exception as exc:
                logger.warning(
                    "chronology: skipping malformed trip row trip=%s "
                    "person=%s: %s", _tid or "<unreadable>", person_id, exc,
                )
                continue
    except ImportError as exc:
        # Expected on a checkout without the trips service — not a defect.
        logger.info(
            "chronology: trips lane unavailable (module not importable) "
            "for %s: %s", person_id, exc,
        )
    except Exception as exc:
        # S8: keep whatever was collected before the failure instead of
        # discarding it, and SAY that the lane is incomplete. A pre-0015
        # database legitimately has no trip tables; anything else is a
        # defect that used to render as "this narrator has no trips".
        _msg = str(exc).lower()
        if "no such table" in _msg or "no such column" in _msg:
            logger.info(
                "chronology: trips lane skipped for %s (schema not present: "
                "%s)", person_id, exc,
            )
        else:
            logger.warning(
                "chronology: trips lane FAILED for %s after %d item(s) — the "
                "accordion will render incomplete: %s",
                person_id, len(trip_items), exc, exc_info=True,
            )
    lane_b_with_spine = lane_b_with_spine + trip_items

    lane_c = build_band_ghosts(birth_year, periods, lane_b_with_spine)

    # Merge all items
    all_items = lane_a + lane_b_with_spine + lane_c

    # Group into decades
    decades = group_by_decade(all_items, periods)

    # WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 commit 3 — the unified
    # projection. These three lanes are added here rather than in a
    # parallel endpoint so there is ONE chronology contract for the Life
    # Map, the accordion, Lori grounding and (next phase) the Travel
    # Document to agree on.
    timeline_events_lane = _collect_timeline_events(person_id)
    story_evidence_lane = _collect_story_evidence(person_id)
    trip_days_lane = _collect_trip_days(person_id)
    timeline_events = timeline_events_lane.items
    story_evidence = story_evidence_lane.items
    trip_days = trip_days_lane.items

    return {
        "person_id": person_id,
        "birth_year": birth_year,
        "birth_date": dob or "",
        "birth_place": basics.get("pob", "") or "",
        "seed_ready": True,
        # Full period objects now (era_id, places, notes, is_approximate,
        # is_current_life, source, status) so a Life Map renderer can
        # consume this directly instead of deriving its own spine.
        "periods": periods,
        "decades": decades,
        "timeline_events": timeline_events,
        "story_evidence": story_evidence,
        "trip_days": trip_days,
        "sources": _sources_block(
            dob_ok=True,
            timeline_events=timeline_events_lane,
            story_evidence=story_evidence_lane,
            trip_days=trip_days_lane,
        ),
        "lane_counts": _lane_counts(
            world=lane_a,
            personal=lane_b_with_spine,
            personal_derived=spine_items,
            ghost=lane_c,
            timeline_events=timeline_events_lane,
            story_evidence=story_evidence_lane,
            trip_days=trip_days_lane,
        ),
    }


# ─── ENDPOINT ─────────────────────────────────────────────────────

@router.get("/chronology-accordion")
def api_chronology_accordion(
    person_id: str = Query(..., description="Narrator person_id"),
):
    """Read-only chronology accordion payload.

    Merges world events, personal anchors, and ghost prompts into
    a decade-grouped structure for the left-side accordion UI.
    """
    person = get_person(person_id)
    if not person:
        raise HTTPException(status_code=404, detail="person not found")

    ensure_profile(person_id)
    profile_row = get_profile(person_id)
    legacy_profile = profile_row.get("profile_json", {}) if profile_row else {}

    # Flag-gated promoted-truth profile build.  build_profile_from_promoted
    # returns {basics, kinship, pets}; legacy_profile also has that shape.
    profile_obj: Dict[str, Any] = legacy_profile or {}
    if truth_v2_enabled("profile"):
        try:
            profile_obj = db.build_profile_from_promoted(person_id)
        except Exception as exc:
            logger.warning(
                "chronology: build_profile_from_promoted failed for %s: %s",
                person_id, exc,
            )
            profile_obj = legacy_profile or {}

    promoted_rows = ft_list_promoted(person_id, limit=10_000)
    questionnaire = get_questionnaire(person_id)

    # Pull the narrator's display name for self-filtering promoted rows.
    narrator_name = (person.get("display_name") or "").strip()

    payload = build_chronology_accordion_payload(
        person_id=person_id,
        profile=profile_obj,
        questionnaire=questionnaire,
        promoted_rows=promoted_rows,
        narrator_display_name=narrator_name,
    )

    return payload
