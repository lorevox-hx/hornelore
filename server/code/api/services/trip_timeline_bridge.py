"""Trip → life-record bridge — WO-TRIP-IMPORT-AND-CLUSTER-01 Phase B.

Makes a trip part of the narrator's canonical record instead of a silo:

1. ERA DERIVATION (parent-spec locked rule): the trip belongs to ONE
   era — the era the narrator was in when it started. Derived from
   people.date_of_birth + trips.start_date via lv_eras.era_id_from_age.
   Trips starting at/after age 76 land in later_years by the open-ended
   range; ``today`` is never derived (current-life is selected, not
   computed). Missing/fuzzy DOB → era_id None (recorded, not guessed).

2. TIMELINE PROJECTION: one timeline_events row per trip
   (kind="trip"), person-FK'd so it cascades with the narrator and
   flows into every surface that consumes timeline_events (timeline
   render, memoir timeline JSON) per locked principle 7 ("mechanical
   truth must visibly project"). Sync is delete-and-recreate keyed by
   trips.meta_json.timeline_event_id — idempotent, safe to call after
   any structural change.

3. BIO SUGGESTION: one trip_bio_suggestions row per trip
   (field_key="travel.trip", status="suggested"). Suggestions are the
   designed lane — they do NOT write bio_facts directly; promotion to
   narrator truth stays a review decision (locked principle 5:
   provisional persists, final truth waits for the operator).

Pure stdlib + db/lv_eras/trip_repository. Never raises to the caller —
a bridge failure must not break trip CRUD (log + return the error).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger("code.api.services.trip_timeline_bridge")


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    v = str(value).strip()[:10]
    try:
        return datetime.strptime(v, "%Y-%m-%d")
    except ValueError:
        return None


def _age_at(dob: Optional[str], on: Optional[str]) -> Optional[float]:
    d1, d2 = _parse_date(dob), _parse_date(on)
    if not d1 or not d2 or d2 < d1:
        return None
    return (d2 - d1).days / 365.25


def derive_trip_era(person_id: str, start_date: Optional[str]) -> Optional[str]:
    """Era the narrator was in when the trip started, or None when the
    DOB/date signal is missing or unparseable."""
    try:
        from .. import db as _db
        from ..lv_eras import era_id_from_age
        person = _db.get_person(person_id)
        if not person:
            return None
        age = _age_at(person.get("date_of_birth"), start_date)
        if age is None:
            return None
        return era_id_from_age(age)
    except Exception as exc:
        logger.warning("[trip-bridge] era derivation failed person=%s: %s",
                       person_id, exc)
        return None


def sync_trip_to_life_record(trip_id: str) -> Dict[str, Any]:
    """Idempotent sync: era into trips.meta_json, timeline event
    refreshed, bio suggestion upserted. Returns a summary dict; never
    raises."""
    result: Dict[str, Any] = {
        "trip_id": trip_id, "era_id": None,
        "timeline_event_id": None, "bio_suggestion": False,
    }
    try:
        from .. import db as _db
        from . import trip_repository as repo

        trip = repo.trip_get(trip_id)
        if not trip:
            result["error"] = "trip not found"
            return result
        person_id = str(trip.get("person_id") or "")
        tree = repo.trip_tree(trip_id) or {}
        n_regions = len(tree.get("regions", []))
        n_stops = 0

        def _count(s: Dict[str, Any]) -> int:
            return 1 + sum(_count(c) for c in s.get("children", []))

        for r in tree.get("regions", []):
            for s in r.get("stops", []):
                n_stops += _count(s)

        # 1) Era.
        era_id = derive_trip_era(person_id, trip.get("start_date"))
        result["era_id"] = era_id

        # 2) Timeline event (delete stale, write fresh).
        meta = trip.get("meta_json") or {}
        if not isinstance(meta, dict):
            meta = {}
        old_event_id = meta.get("timeline_event_id")
        if old_event_id:
            try:
                _db.delete_timeline_event(str(old_event_id))
            except Exception:
                pass
        date = trip.get("start_date") or trip.get("end_date")
        event_id = None
        if date:
            span = " to ".join(
                [d for d in (trip.get("start_date"), trip.get("end_date")) if d]
            )
            body_bits = [span]
            if n_regions or n_stops:
                body_bits.append(
                    f"{n_regions} region{'s' if n_regions != 1 else ''}, "
                    f"{n_stops} stop{'s' if n_stops != 1 else ''}"
                )
            event = _db.add_timeline_event(
                person_id=person_id,
                date=str(date),
                title=str(trip.get("title") or "Trip"),
                body=" · ".join(body_bits),
                kind="trip",
                meta={
                    "trip_id": trip_id,
                    "era_id": era_id,
                    "end_date": trip.get("end_date"),
                    "source": "trip_sync",
                },
            )
            event_id = event.get("id")
        result["timeline_event_id"] = event_id

        # Persist era + event link back onto the trip row.
        meta["era_id"] = era_id
        meta["timeline_event_id"] = event_id
        repo.trip_meta_update(trip_id, meta)

        # 3) Bio suggestion (one per trip; replace prior).
        try:
            repo.bio_suggestion_replace_for_trip(
                trip_id=trip_id,
                person_id=person_id,
                field_key="travel.trip",
                suggested_value=(
                    str(trip.get("title") or "Trip")
                    + (f" ({trip.get('start_date')}"
                       + (f" to {trip.get('end_date')}" if trip.get("end_date") else "")
                       + ")" if trip.get("start_date") else "")
                ),
            )
            result["bio_suggestion"] = True
        except Exception as exc:
            logger.warning("[trip-bridge] bio suggestion failed trip=%s: %s",
                           trip_id, exc)

        logger.info(
            "[trip-bridge] synced trip=%s era=%s event=%s regions=%d stops=%d",
            trip_id, era_id, event_id, n_regions, n_stops,
        )
        return result
    except Exception as exc:
        logger.warning("[trip-bridge] sync failed trip=%s: %s", trip_id, exc)
        result["error"] = str(exc)
        return result


def remove_trip_from_life_record(trip: Dict[str, Any]) -> None:
    """Called BEFORE trip deletion with the trip row — removes the
    timeline event so the life record doesn't keep a ghost. Bio
    suggestion rows cascade with the trip (FK). Never raises."""
    try:
        from .. import db as _db
        meta = trip.get("meta_json") or {}
        if isinstance(meta, dict) and meta.get("timeline_event_id"):
            _db.delete_timeline_event(str(meta["timeline_event_id"]))
            logger.info(
                "[trip-bridge] removed timeline event %s for deleted trip %s",
                meta["timeline_event_id"], trip.get("id"),
            )
    except Exception as exc:
        logger.warning("[trip-bridge] event removal failed: %s", exc)
