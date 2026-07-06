"""Trip narration capture — WO-LIFEMAP-TRAVELS-SHELF-AND-NARRATION-01
Phases 2+3.

Deterministic per-turn parser: the narrator TALKS ("I took a trip in
May 2026 starting in Munich, then we drove to Prague for three
nights"), the SYSTEM extracts route structure. Lori never writes
structure (locked principle 6); prompt paragraphs never collect fields
(locked 2026-05-02 Patch B lesson) — this module is where the
structure work lives.

Hard rules from the approved spec (v2, §3.3):
  - create only OBVIOUS stops (high-confidence parse);
  - NEVER delete anything, ever;
  - never overwrite operator-entered fields;
  - never move/reorder operator rows — reorders touch narration rows
    (meta_json.source == "narration") only;
  - negation suppresses entirely ("we never made it to Vienna");
  - uncertainty ("maybe Brno?") emits an observation, no row;
  - no duplicate trip creation from ambiguous narration — on match
    with an existing trip, return needs_disambiguation instead;
  - narration-created trips are born deterministically:
    title="Untitled trip", provenance fields set, Lori never titles.

Gate (read by the chat_ws hook, not here):
  HORNELORE_TRIP_NARRATION = 0    -> hook off (default)
                             log  -> parse + [trip-narration] log only
                             1    -> parse + provisional writes

Pure stdlib + trip_repository/trip_timeline_bridge (lazy). LAW 3
isolation: no imports from extract / chat_ws / prompt_composer /
memory_echo / llm — enforced by tests/test_trip_narration_isolation.py.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("code.api.services.trip_narration_capture")

# ── Place-name capture ────────────────────────────────────────────────
# Proper-noun phrase: 1-3 capitalized tokens (allows "New York City",
# "Cesky Krumlov"). Deliberately capital-anchored — same trade-off as
# the utterance-frame place regex (STT-lowercase misses are a known,
# accepted gap; the alias layer can extend later).
_PLACE = r"([A-Z][\w''-]+(?:\s+[A-Z][\w''-]+){0,2})"

_START_RX = re.compile(
    r"\b(?:start(?:ed|ing)?(?:\s+(?:off|out))?\s+in|began\s+(?:the\s+trip\s+)?in|"
    r"flew\s+(?:in)?to|landed\s+in|arrived\s+in)\s+" + _PLACE)

_SEQ_RX = re.compile(
    r"\b(?:then\s+(?:we\s+)?(?:went|drove|traveled|travelled|moved|flew|headed|took\s+\w+)\s+(?:on\s+)?to|"
    r"then\s+(?:on\s+)?to|(?:went|drove|traveled|travelled|flew|headed)\s+(?:on\s+)?(?:down\s+|up\s+)?to|"
    r"stopped\s+(?:in|at)|stayed\s+(?:in|at)|visited|spent\s+time\s+in|"
    r"on\s+(?:the\s+way\s+)?to|continued\s+to|ended\s+(?:up\s+)?in|finished\s+in|"
    r"then)\s+" + _PLACE)

_NIGHTS_RX = re.compile(
    r"\b(?:(\d+)|(one|two|three|four|five|six|seven|eight|nine|ten))\s+"
    r"(?:nights?|days?)\s+in\s+" + _PLACE, re.IGNORECASE)

_MONTHS = ("january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december")
_MONTH_YEAR_RX = re.compile(
    r"\b(" + "|".join(m.capitalize() for m in _MONTHS) + r")\s*(?:of\s+)?(\d{4})\b")
_YEAR_RX = re.compile(r"\b(?:in|back\s+in|during)\s+((?:19|20)\d{2})\b")

_WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
             "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}

# Negation: places in these clauses are SUPPRESSED (no candidate, ever).
_NEGATION_RX = re.compile(
    r"\b(?:never\s+(?:made\s+it|got|went)\s+to|didn'?t\s+(?:go|get|make\s+it)\s+to|"
    r"couldn'?t\s+(?:visit|get\s+to|go\s+to)|skipped|missed|had\s+to\s+cancel)\b",
    re.IGNORECASE)

# Uncertainty: clause becomes an observation — no row mutation (REV 7).
_UNCERTAIN_RX = re.compile(
    r"\b(?:maybe|perhaps|possibly|i\s+think|might\s+have|may\s+have|"
    r"not\s+sure|somewhere\s+near|can'?t\s+remember\s+if|if\s+i\s+recall)\b",
    re.IGNORECASE)

# Corrections: "Salzburg was before Vienna", "no, we started in Munich".
_ORDER_CORRECTION_RX = re.compile(
    _PLACE + r"\s+(?:was|came)\s+(?:before|first,?\s+then)\s+" + _PLACE)
_START_CORRECTION_RX = re.compile(
    r"\b(?:no,?\s+)?(?:we|i)\s+(?:actually\s+)?started\s+in\s+" + _PLACE)

# Tokens that must never be treated as places (sentence-start captures).
_PLACE_BLOCKLIST = frozenset({
    "i", "we", "then", "the", "my", "our", "lori", "there", "that", "this",
    "it", "he", "she", "they", "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday", "spring", "summer", "fall", "autumn",
    "winter", "north", "south", "east", "west",
} | set(_MONTHS))


def _clauses(text: str) -> List[str]:
    # Sentence-ish splits; "but" splits too so negations stay scoped.
    parts = re.split(r"(?<=[.;!?])\s+|\s+but\s+", text or "")
    return [p.strip() for p in parts if p and p.strip()]


def _clean_place(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    place = raw.strip().rstrip(".,;:!?")
    if not place or place.split()[0].lower() in _PLACE_BLOCKLIST:
        return None
    return place


def parse_trip_narration(text: str) -> Dict[str, Any]:
    """Parse ONE narrator turn. Pure; no DB. Returns::

        {
          "start_place":  str|None,
          "stops":        [{"place": str, "nights": int|None}],   # in narration order
          "month":        1-12|None,
          "year":         int|None,
          "corrections":  [{"first": str, "second": str}],        # first BEFORE second
          "start_correction": str|None,                           # "no, we started in X"
          "observations": [str],   # uncertain clauses (verbatim, trimmed)
          "suppressed":   [str],   # negated place names
          "confidence":   "high"|"partial"|"none",
        }
    """
    out: Dict[str, Any] = {
        "start_place": None, "stops": [], "month": None, "year": None,
        "corrections": [], "start_correction": None,
        "observations": [], "suppressed": [], "confidence": "none",
    }
    if not text or not text.strip():
        return out

    # Trip-level date mentions (any clause; dates aren't negatable here).
    m = _MONTH_YEAR_RX.search(text)
    if m:
        out["month"] = _MONTHS.index(m.group(1).lower()) + 1
        out["year"] = int(m.group(2))
    else:
        y = _YEAR_RX.search(text)
        if y:
            out["year"] = int(y.group(1))

    seen: set = set()
    for clause in _clauses(text):
        negated = bool(_NEGATION_RX.search(clause))
        uncertain = bool(_UNCERTAIN_RX.search(clause))

        # Corrections parse even inside otherwise-plain clauses.
        for cm in _ORDER_CORRECTION_RX.finditer(clause):
            first, second = _clean_place(cm.group(1)), _clean_place(cm.group(2))
            if first and second:
                out["corrections"].append({"first": first, "second": second})
        sc = _START_CORRECTION_RX.search(clause)
        if sc and re.search(r"\bno\b|\bactually\b", clause, re.IGNORECASE):
            p = _clean_place(sc.group(1))
            if p:
                out["start_correction"] = p

        clause_places: List[Dict[str, Any]] = []
        sm = _START_RX.search(clause)
        if sm:
            p = _clean_place(sm.group(1))
            if p:
                clause_places.append({"place": p, "kind": "start", "nights": None})
        for qm in _SEQ_RX.finditer(clause):
            p = _clean_place(qm.group(1))
            if p:
                clause_places.append({"place": p, "kind": "stop", "nights": None})
        for nm in _NIGHTS_RX.finditer(clause):
            p = _clean_place(nm.group(3))
            if not p:
                continue
            nights = int(nm.group(1)) if nm.group(1) else _WORD_NUM.get(
                (nm.group(2) or "").lower())
            hit = next((c for c in clause_places
                        if c["place"].lower() == p.lower()), None)
            if hit:
                hit["nights"] = nights
            else:
                clause_places.append({"place": p, "kind": "stop", "nights": nights})

        if negated:
            out["suppressed"].extend(c["place"] for c in clause_places)
            # Negation verbs ("never made it to X") aren't travel verbs,
            # so the capture regexes may not have fired — record the
            # negated place from a generic "to PLACE" scan too.
            for gm in re.finditer(r"\bto\s+" + _PLACE, clause):
                p = _clean_place(gm.group(1))
                if p and p not in out["suppressed"]:
                    out["suppressed"].append(p)
            continue
        if uncertain:
            if clause_places or _UNCERTAIN_RX.search(clause):
                out["observations"].append(clause[:200])
            continue

        for c in clause_places:
            key = c["place"].lower()
            if key in seen:
                # Merge late-arriving detail ("We spent three nights in
                # Prague" after Prague was already captured).
                if c.get("nights") is not None:
                    for s in out["stops"]:
                        if s["place"].lower() == key and s["nights"] is None:
                            s["nights"] = c["nights"]
                continue
            seen.add(key)
            if c["kind"] == "start" and not out["start_place"]:
                out["start_place"] = c["place"]
            else:
                out["stops"].append({"place": c["place"], "nights": c["nights"]})

    n_signal = ((1 if out["start_place"] else 0) + len(out["stops"])
                + len(out["corrections"]) + (1 if out["start_correction"] else 0))
    if n_signal >= 2 or (n_signal >= 1 and out["year"]):
        out["confidence"] = "high"
    elif n_signal >= 1 or out["observations"] or out["year"]:
        out["confidence"] = "partial"
    return out


# ── Duplicate-trip protection (spec REV 5) ───────────────────────────

def find_matching_trip(parse: Dict[str, Any],
                       existing_trips: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Approximate-match narration against the narrator's existing trips.
    Match on: parsed year within the trip's date span OR title, or a
    parsed place token appearing in the trip title. On match, the
    caller must NOT create a new trip (disambiguation instead)."""
    places = {p.lower() for p in
              ([parse.get("start_place")] if parse.get("start_place") else [])
              + [s["place"] for s in parse.get("stops", [])]}
    year = parse.get("year")
    for trip in existing_trips or []:
        title = (trip.get("title") or "").lower()
        if year:
            if str(year) in title:
                return trip
            for key in ("start_date", "end_date"):
                if str(trip.get(key) or "").startswith(str(year)):
                    return trip
        for pl in places:
            if pl and pl in title:
                return trip
    return None


# ── Provisional writes (Phase 3 — conservative by contract) ──────────

_NARRATION_META = {"source": "narration", "status": "provisional"}


def _is_narration_row(row: Dict[str, Any]) -> bool:
    meta = row.get("meta_json") or {}
    if not isinstance(meta, dict):
        return False
    return meta.get("source") == "narration"


def apply_trip_narration(
    parse: Dict[str, Any],
    *,
    person_id: str,
    active_trip_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Consume a parse: provisional writes through trip_repository.

    Returns a summary dict (never raises to the caller):
      {applied: bool, trip_id, created_trip: bool, stops_added: [names],
       reordered: bool, needs_disambiguation: trip-title|None, error}
    """
    summary: Dict[str, Any] = {
        "applied": False, "trip_id": active_trip_id, "created_trip": False,
        "stops_added": [], "reordered": False,
        "needs_disambiguation": None, "error": None,
    }
    try:
        from . import trip_repository as repo
        from . import trip_timeline_bridge as bridge

        if parse.get("confidence") == "none":
            return summary

        # BUG-TRIP-NARRATION-ACTIVE-TRIP-OWNERSHIP-VALIDATION-01
        # (review 2026-07-05): never trust a frontend-supplied trip id
        # blindly — a stale/wrong active_trip_id in runtime71 must not
        # let narration write into another narrator's trip.
        if active_trip_id:
            _owned = repo.trip_get(active_trip_id)
            if not _owned or str(_owned.get("person_id")) != str(person_id):
                logger.warning(
                    "[trip-narration] ownership check failed: trip=%s does "
                    "not belong to narrator=%s — no writes",
                    active_trip_id, person_id)
                summary["error"] = "active trip not found for narrator"
                return summary

        trip_id = active_trip_id
        # ── no active trip: duplicate guard, then deterministic create ──
        if not trip_id:
            has_route = bool(parse.get("start_place") or parse.get("stops"))
            if not has_route:
                return summary  # nothing obvious enough to create from
            existing = repo.trip_list(person_id)
            match = find_matching_trip(parse, existing)
            if match:
                summary["needs_disambiguation"] = match.get("title") or "a trip"
                summary["trip_id"] = match.get("id")
                logger.info(
                    "[trip-narration] duplicate guard: narration matches trip "
                    "'%s' — NOT creating (disambiguation needed)",
                    summary["needs_disambiguation"])
                return summary
            # Deterministic birth (spec REV 4). Lori never titles it.
            start_date = None
            if parse.get("year") and parse.get("month"):
                start_date = f"{parse['year']:04d}-{parse['month']:02d}-01"
            trip_id = repo.trip_create(
                person_id=person_id, title="Untitled trip",
                start_date=start_date, end_date=None,
            )
            repo.trip_meta_merge(trip_id, {
                **_NARRATION_META,
                "created_from_surface": "travels_shelf",
            })
            summary["created_trip"] = True
            summary["trip_id"] = trip_id

        # ── find-or-create the narration region ─────────────────────
        tree = repo.trip_tree(trip_id) or {}
        regions = tree.get("regions", [])
        region_id = None
        existing_stop_names: Dict[str, Dict[str, Any]] = {}
        for r in regions:
            def _walk(s):
                existing_stop_names[(s.get("location_name") or "").lower()] = s
                for c in s.get("children", []):
                    _walk(c)
            for s in r.get("stops", []):
                _walk(s)
            rmeta = r.get("meta_json") or {}
            if isinstance(rmeta, dict) and rmeta.get("source") == "narration":
                region_id = r.get("id")
        if region_id is None:
            if len(regions) == 1 and not _is_narration_row(regions[0]):
                # Single operator region — add there rather than forking
                # the structure (operator can restructure in the Tab).
                region_id = regions[0]["id"]
            else:
                region_id = repo.region_create(trip_id, "Journey")
                _stamp_region_meta(region_id)

        # ── add stops (create-only-obvious; skip anything existing) ──
        ordered_places: List[Dict[str, Any]] = []
        if parse.get("start_place"):
            ordered_places.append({"place": parse["start_place"], "nights": None})
        ordered_places.extend(parse.get("stops", []))
        _max_ord = 0
        for r in regions:
            for s in r.get("stops", []):
                _max_ord = max(_max_ord, s.get("ord") or 0)
                for c in s.get("children", []):
                    _max_ord = max(_max_ord, c.get("ord") or 0)
        for sp in ordered_places:
            key = sp["place"].lower()
            if key in existing_stop_names:
                continue  # never duplicate, never overwrite
            _max_ord += 1
            stop_id = repo.stop_create(trip_id, region_id, sp["place"],
                                       ord_=_max_ord)
            # Stamp narration provenance on the stop row.
            _stamp_stop_meta(stop_id)
            existing_stop_names[key] = {"id": stop_id}
            summary["stops_added"].append(sp["place"])

        # ── corrections: reorder NARRATION rows only ─────────────────
        if parse.get("corrections") or parse.get("start_correction"):
            summary["reordered"] = _apply_order_corrections(
                repo, trip_id, parse, existing_stop_names)

        if summary["stops_added"] or summary["created_trip"] or summary["reordered"]:
            summary["applied"] = True
            try:
                bridge.sync_trip_to_life_record(trip_id)
            except Exception:
                pass
            logger.info(
                "[trip-narration] applied trip=%s created=%s stops_added=%s "
                "reordered=%s", trip_id, summary["created_trip"],
                summary["stops_added"], summary["reordered"])
        return summary
    except Exception as exc:  # narration must NEVER break the chat turn
        logger.warning("[trip-narration] apply failed: %s", exc)
        summary["error"] = str(exc)
        return summary


def _stamp_stop_meta(stop_id: str) -> None:
    """Write narration provenance into trip_stops.meta_json (direct,
    minimal UPDATE — repository has no stop-meta helper yet)."""
    try:
        import json
        import sqlite3
        from .. import db as _db
        con = sqlite3.connect(str(_db.DB_PATH))
        try:
            con.execute("PRAGMA busy_timeout = 5000;")
            con.execute(
                "UPDATE trip_stops SET meta_json = ? WHERE id = ?",
                (json.dumps(_NARRATION_META), stop_id))
            con.commit()
        finally:
            con.close()
    except Exception as exc:
        logger.info("[trip-narration] stop meta stamp skipped: %s", exc)


def _stamp_region_meta(region_id: str) -> None:
    try:
        import json
        import sqlite3
        from .. import db as _db
        con = sqlite3.connect(str(_db.DB_PATH))
        try:
            con.execute("PRAGMA busy_timeout = 5000;")
            con.execute(
                "UPDATE trip_regions SET meta_json = ? WHERE id = ?",
                (json.dumps(_NARRATION_META), region_id))
            con.commit()
        finally:
            con.close()
    except Exception as exc:
        logger.info("[trip-narration] region meta stamp skipped: %s", exc)


def _apply_order_corrections(repo, trip_id: str, parse: Dict[str, Any],
                             stop_index: Dict[str, Dict[str, Any]]) -> bool:
    """'Salzburg was before Vienna' → ord swap, NARRATION rows only.
    Operator rows are never moved (spec hard rule)."""
    changed = False
    tree = repo.trip_tree(trip_id) or {}
    rows: Dict[str, Dict[str, Any]] = {}
    for r in tree.get("regions", []):
        def _walk(s):
            rows[(s.get("location_name") or "").lower()] = s
            for c in s.get("children", []):
                _walk(c)
        for s in r.get("stops", []):
            _walk(s)

    for corr in parse.get("corrections", []):
        a = rows.get(corr["first"].lower())
        b = rows.get(corr["second"].lower())
        if not a or not b:
            continue
        if not (_is_narration_row(a) and _is_narration_row(b)):
            logger.info("[trip-narration] reorder skipped — operator row "
                        "involved (%s / %s)", corr["first"], corr["second"])
            continue
        ord_a, ord_b = a.get("ord") or 0, b.get("ord") or 0
        if ord_a > ord_b:  # first should come earlier
            try:
                repo.stop_update(a["id"], ord_=ord_b)
                repo.stop_update(b["id"], ord_=ord_a)
                changed = True
            except Exception as exc:
                logger.info("[trip-narration] reorder failed: %s", exc)

    sc = parse.get("start_correction")
    if sc:
        row = rows.get(sc.lower())
        if row and _is_narration_row(row):
            try:
                min_ord = min((r.get("ord") or 0) for r in rows.values()) - 1
                repo.stop_update(row["id"], ord_=min_ord)
                changed = True
            except Exception as exc:
                logger.info("[trip-narration] start reorder failed: %s", exc)
    return changed


__all__ = ["parse_trip_narration", "apply_trip_narration",
           "find_matching_trip"]
