"""Small, stable truth-zone scorer for active extraction harnesses.

The retired master evaluator grew scoring, GPU diagnostics, report rendering,
historical experiment partitions, and live HTTP execution in one module.  This
module keeps only the durable contract: compare extractor items with
``must_extract``, ``may_extract``, ``should_ignore``, and ``must_not_write``
truth zones.

The value matcher intentionally preserves the retired scorer's normalization,
date handling, role aliases, fuzzy thresholds, bonuses, and penalties.  A
representative parity test protects that claim.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional

TRUTH_ZONES = ("must_extract", "may_extract", "should_ignore", "must_not_write")

_MONTH_NAMES = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}

_ROLE_ALIASES = {
    "ot": "occupational therapist",
    "pt": "physical therapist",
    "rn": "registered nurse",
    "lpn": "licensed practical nurse",
    "np": "nurse practitioner",
    "slp": "speech language pathologist",
}


def normalize_value(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).lower().strip().split())


def _normalize_date(value: Any) -> Optional[str]:
    text = str(value or "").strip().lower()
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", text)
    if match:
        return text
    match = re.match(r"^(\w+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})$", text)
    if match and match.group(1) in _MONTH_NAMES:
        return f"{match.group(3)}-{_MONTH_NAMES[match.group(1)]}-{match.group(2).zfill(2)}"
    match = re.match(r"^(\d{1,2})\s+(\w+)\s+(\d{4})$", text)
    if match and match.group(2) in _MONTH_NAMES:
        return f"{match.group(3)}-{_MONTH_NAMES[match.group(2)]}-{match.group(1).zfill(2)}"
    return None


def score_field_match(expected: Any, actual: Any) -> float:
    """Return the retired scorer's 0..1 fuzzy value score."""
    exp = normalize_value(expected)
    got = normalize_value(actual)
    if not exp or not got:
        return 0.0
    if exp == got:
        return 1.0
    if _ROLE_ALIASES.get(exp) == got or _ROLE_ALIASES.get(got) == exp:
        return 1.0
    exp_date = _normalize_date(expected)
    got_date = _normalize_date(actual)
    if exp_date and got_date:
        if exp_date == got_date:
            return 1.0
        return 0.5 if exp_date[:4] == got_date[:4] else 0.0
    if exp in got or got in exp:
        return 0.8
    exp_tokens = set(exp.split())
    got_tokens = set(got.split())
    if exp_tokens and exp_tokens.issubset(got_tokens):
        return 0.9
    overlap = len(exp_tokens & got_tokens)
    if exp_tokens:
        ratio = overlap / len(exp_tokens)
        if ratio >= 0.5:
            return round(0.5 + ratio * 0.3, 2)
    return 0.0


def _zone_entries(case: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Normalize dict-style and list-style case contracts."""
    entries: List[Dict[str, Any]] = []
    truth_zones = case.get("truthZones") or {}
    if truth_zones:
        for field_path, raw in truth_zones.items():
            raw_entries = raw.get("_multi", []) if isinstance(raw, dict) and "_multi" in raw else [raw]
            for item in raw_entries:
                if not isinstance(item, dict):
                    continue
                entries.append({"fieldPath": field_path, **item})
        return entries

    for zone in TRUTH_ZONES:
        for raw in case.get(zone, []) or []:
            if not isinstance(raw, dict) or not raw.get("fieldPath"):
                continue
            item = dict(raw)
            item["zone"] = zone
            if "value" in item and "expected" not in item:
                item["expected"] = item["value"]
            entries.append(item)
    return entries


def _extracted_map(items: Iterable[Mapping[str, Any]]) -> Dict[str, List[Any]]:
    result: MutableMapping[str, List[Any]] = defaultdict(list)
    for item in items:
        path = str(item.get("fieldPath") or "").strip()
        if path:
            result[path].append(item.get("value", ""))
    return dict(result)


def _best_value_score(values: Iterable[Any], expected: Any) -> float:
    return max((score_field_match(expected, value) for value in values), default=0.0)


def _score_must_extract(entry: Mapping[str, Any], extracted: Mapping[str, List[Any]]) -> Dict[str, Any]:
    path = str(entry.get("fieldPath") or "")
    expected = entry.get("expected", "")
    alt_paths = list(entry.get("alt_defensible_paths") or [])
    alt_values = list(entry.get("alt_defensible_values") or [])

    if path in extracted:
        if not expected:
            return {"hit": True, "winning_path": path, "winning_via": "primary", "score": 1.0}
        best = _best_value_score(extracted[path], expected)
        if best >= 0.5:
            return {"hit": True, "winning_path": path, "winning_via": "primary", "score": best}
        for alternate in alt_values:
            best = _best_value_score(extracted[path], alternate)
            if best >= 0.5:
                return {"hit": True, "winning_path": path, "winning_via": "alt_defensible_value", "score": best}

    for alt_path in alt_paths:
        if alt_path not in extracted:
            continue
        if expected:
            best = _best_value_score(extracted[alt_path], expected)
            if best >= 0.5:
                return {"hit": True, "winning_path": alt_path, "winning_via": "alt_defensible_path", "score": best}
        for alternate in alt_values:
            best = _best_value_score(extracted[alt_path], alternate)
            if best >= 0.5:
                return {"hit": True, "winning_path": alt_path, "winning_via": "alt_defensible_path_and_value", "score": best}

    return {"hit": False, "winning_path": None, "winning_via": None, "score": 0.0}


def score_case(case: Mapping[str, Any], extracted_items: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    """Score one extraction case without importing the runtime extractor."""
    items = [dict(item) for item in extracted_items]
    extracted = _extracted_map(items)
    entries = _zone_entries(case)
    totals: Dict[str, Dict[str, int]] = {
        "must_extract": {"total": 0, "hit": 0, "miss": 0},
        "may_extract": {"total": 0, "hit": 0, "miss": 0},
        "should_ignore": {"total": 0, "hit": 0, "miss": 0, "leaked": 0},
        "must_not_write": {"total": 0, "hit": 0, "miss": 0, "violated": 0},
    }
    details: List[Dict[str, Any]] = []

    for entry in entries:
        zone = str(entry.get("zone") or "must_extract")
        path = str(entry.get("fieldPath") or "")
        if zone not in totals or not path:
            continue
        totals[zone]["total"] += 1
        present = path in extracted
        detail = {"fieldPath": path, "zone": zone, "present": present}
        if zone == "must_extract":
            outcome = _score_must_extract(entry, extracted)
            key = "hit" if outcome["hit"] else "miss"
            totals[zone][key] += 1
            detail.update(outcome)
        elif zone == "may_extract":
            totals[zone]["hit" if present else "miss"] += 1
            detail["hit"] = present
        elif zone == "should_ignore":
            totals[zone]["leaked" if present else "hit"] += 1
            detail["leaked"] = present
        else:
            totals[zone]["violated" if present else "hit"] += 1
            detail["violated"] = present
        details.append(detail)

    must = totals["must_extract"]
    recall = must["hit"] / must["total"] if must["total"] else 1.0
    may = totals["may_extract"]
    may_bonus = 0.1 * (may["hit"] / may["total"]) if may["total"] else 0.0
    ignore_penalty = 0.1 * totals["should_ignore"]["leaked"]
    no_write_penalty = 0.2 * totals["must_not_write"]["violated"]
    overall = max(0.0, min(1.0, recall + may_bonus - ignore_penalty - no_write_penalty))

    failures: List[str] = []
    if must["miss"]:
        failures.append("missing_required")
    if totals["should_ignore"]["leaked"]:
        failures.append("noise_leakage")
    if totals["must_not_write"]["violated"]:
        failures.append("must_not_write_violation")
    passed = overall >= 0.7 and totals["must_not_write"]["violated"] == 0
    return {
        "case_id": case.get("id") or case.get("case_id") or "",
        "pass": passed,
        "overall_score": round(overall, 3),
        "truth_zone_scores": totals,
        "truth_zone_details": details,
        "failure_categories": failures,
        "extracted_count": len(items),
    }


def summarize(case_results: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    results = list(case_results)
    passed = sum(1 for result in results if result.get("pass"))
    zones = {
        "must_extract": {"total": 0, "hit": 0, "miss": 0},
        "may_extract": {"total": 0, "hit": 0, "miss": 0},
        "should_ignore": {"total": 0, "hit": 0, "leaked": 0},
        "must_not_write": {"total": 0, "hit": 0, "violated": 0},
    }
    failure_counts: MutableMapping[str, int] = defaultdict(int)
    for result in results:
        for zone, aggregate in zones.items():
            source = (result.get("truth_zone_scores") or {}).get(zone) or {}
            for key in aggregate:
                aggregate[key] += int(source.get(key, 0))
        for category in result.get("failure_categories") or []:
            failure_counts[str(category)] += 1
    must = zones["must_extract"]
    return {
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": round(passed / len(results), 3) if results else 0.0,
        "must_extract_recall": round(must["hit"] / must["total"], 3) if must["total"] else 1.0,
        "should_ignore_leak_rate": round(
            zones["should_ignore"]["leaked"] / zones["should_ignore"]["total"], 3
        ) if zones["should_ignore"]["total"] else 0.0,
        "must_not_write_violation_rate": round(
            zones["must_not_write"]["violated"] / zones["must_not_write"]["total"], 3
        ) if zones["must_not_write"]["total"] else 0.0,
        "truth_zones": zones,
        "failure_categories": dict(sorted(failure_counts.items())),
    }
