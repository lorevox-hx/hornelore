#!/usr/bin/env python3
"""WO-QB-MASTER-EVAL-01 — Unified regression + oral-history stress eval.

Dual-mode runner:
  --mode offline   Use mockLlmOutput from the fixture. Tests guards, routing,
                   field-path validation, and scoring logic without a loaded model.

  --mode live      POST to the real /api/extract-fields endpoint with the local
                   LLM loaded. Tests end-to-end extraction quality.

One command, one master report.  Backward compatible with v2 cases.

Usage:
  python scripts/run_question_bank_extraction_eval.py --mode offline
  python scripts/run_question_bank_extraction_eval.py --mode live --api http://localhost:8000

Output:
  Writes a JSON report to docs/reports/question_bank_extraction_eval_report.json
  Prints a summary table to stdout.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# WO-EX-FAILURE-PACK-01 (#141): cluster-JSON sidecar companion. Additive only;
# the master report JSON remains byte-identical.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from failure_pack import build_failure_pack, render_failure_pack_console  # noqa: E402

# ── Paths ───────────────────────────────────────────────────────────────────
# 2026-04-25: script moved from scripts/ to scripts/archive/ — REPO_ROOT
# needs three .parent calls now (file → archive/ → scripts/ → repo root).
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CASES_PATH = REPO_ROOT / "data" / "qa" / "question_bank_extraction_cases.json"
REPORT_DIR = REPO_ROOT / "docs" / "reports"

# ── Failure category enum ───────────────────────────────────────────────────
FAILURE_CATEGORIES = [
    "schema_gap",              # field exists in template but no EXTRACTABLE_FIELDS path covers it
    "guard_false_positive",    # guard stack drops a valid extraction
    "llm_output_shape",        # LLM returns unparseable or malformed JSON
    "llm_hallucination",       # LLM invents a fact not in the narrator reply
    "field_path_mismatch",     # LLM uses wrong fieldPath for a correct value
    "missing_alias",           # LLM uses an alias not in FIELD_ALIASES
    "noise_leakage",           # should_ignore field was wrongly extracted
    "attribution_error",       # family/narrator attribution wrong (style check)
]


# ── Stubborn-pack partition (WO-EX-SPANTAG-01 §Stubborn-pack partition) ─────
# Keeps the eval harness self-aware of which cases fall into which sub-pack
# so reports surface movement per partition without hand-counting. Primary
# is the SECTION-EFFECT-adjudicated dual_answer_defensible quartet (first
# SPANTAG target); secondary is one guard_false_positive retag candidate;
# truncation_starved is the VRAM-GUARD-dominated long tail; out_of_scope is
# the R6-deferred wrong-entity / alt-value set.
STUBBORN_PACK_PARTITION: Dict[str, set] = {
    "primary":            {"case_008", "case_009", "case_018", "case_082"},
    "secondary":          {"case_017"},
    "truncation_starved": {"case_080", "case_081", "case_083", "case_084",
                           "case_085", "case_086", "case_087"},
    "out_of_scope":       {"case_075", "case_088", "case_053"},
}


def _stubborn_partition_for(case_id: str) -> Optional[str]:
    """Return the stubborn-pack partition key for a case, or None if not in the pack."""
    for name, ids in STUBBORN_PACK_PARTITION.items():
        if case_id in ids:
            return name
    return None


def _confidence_stats(items: List[dict]) -> Dict[str, Any]:
    """Per-case confidence summary: count / min / max / avg + low-count flag.

    Accepts the raw extracted-items list (live) or the mockLlmOutput list
    (offline) — both expose `confidence` on each item. Missing / non-numeric
    confidence values are skipped so cases with no confidence survive cleanly.
    """
    confs: List[float] = []
    for it in items or []:
        c = it.get("confidence")
        if isinstance(c, (int, float)):
            confs.append(float(c))
    if not confs:
        return {"count": 0, "min": None, "max": None, "avg": None, "lt_0_5": 0, "ge_0_9": 0}
    return {
        "count": len(confs),
        "min":   round(min(confs), 3),
        "max":   round(max(confs), 3),
        "avg":   round(sum(confs) / len(confs), 3),
        "lt_0_5": sum(1 for c in confs if c <  0.5),
        "ge_0_9": sum(1 for c in confs if c >= 0.9),
    }


# ── WO-EX-DISCIPLINE-01 (#142) — run-report discipline header ───────────────
# Captures the system state at run time (git SHA, flag state, api endpoint,
# warmup classification, scorer/case-bank file hashes) so that when a master
# eval produces movement, the reader can attribute the delta to a specific
# code state without reconstructing it from memory or timestamp correlation.
# Harness-side only; zero scoring impact. Output: first ~20 lines of the
# .console.txt, plus a top-level "run_metadata" key on the JSON report.

_DISCIPLINE_FLAG_NAMES = (
    "HORNELORE_NARRATIVE",
    "HORNELORE_ATTRIB_BOUNDARY",
    "HORNELORE_PROMPTSHRINK",
    "HORNELORE_SILENT_DEBUG",
    "HORNELORE_SPANTAG",
    "HORNELORE_INTAKE_MINIMAL",
)


def _capture_discipline_header(
    api_base: str,
    mode: str,
    cases_path: Path,
    output_path: Optional[Path],
) -> tuple[Dict[str, Any], str]:
    """Build the discipline-header dict + its rendered console text.

    Called BEFORE the eval loop runs so the warmup-probe classification and
    api.log freshness reflect the pre-run state of the stack. Never raises —
    every sub-capture catches its own exceptions and records a graceful
    'unavailable' string so a partial environment still produces a header.
    """
    import datetime as _dt
    import hashlib as _hashlib
    import subprocess as _sp

    header: Dict[str, Any] = {}

    # eval_tag — derived from master_loop01_<tag>.json convention
    eval_tag: Optional[str] = None
    if output_path is not None:
        stem = output_path.stem
        if stem.startswith("master_loop01_"):
            eval_tag = stem[len("master_loop01_"):]
    header["eval_tag"] = eval_tag
    header["started_at"] = _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    header["mode"] = mode

    # Git state — best-effort; may be unreachable from sandbox mounts.
    for key, cmd in (
        ("git_sha",    ["git", "rev-parse", "--short=7", "HEAD"]),
        ("branch",     ["git", "rev-parse", "--abbrev-ref", "HEAD"]),
    ):
        try:
            out = _sp.check_output(
                cmd, cwd=str(REPO_ROOT),
                stderr=_sp.DEVNULL, timeout=5,
            ).decode().strip()
            header[key] = out or "unavailable"
        except Exception:
            header[key] = "unavailable"
    try:
        status = _sp.check_output(
            ["git", "status", "--porcelain"],
            cwd=str(REPO_ROOT), stderr=_sp.DEVNULL, timeout=5,
        ).decode()
        header["git_dirty"] = bool(status.strip())
    except Exception:
        header["git_dirty"] = None

    # Flag state — exact runtime env-var values at harness spawn.
    header["flags"] = {
        name: os.environ.get(name, "0") for name in _DISCIPLINE_FLAG_NAMES
    }

    # API endpoint + live-only probes.
    header["api_endpoint"] = api_base if mode == "live" else "(offline mode)"
    header["api_model"] = "(offline mode)" if mode != "live" else None
    header["api_model_hash"] = "(offline mode)" if mode != "live" else None
    header["api_uptime_seconds"] = None
    header["api_log_last_line_age_seconds"] = None
    header["warmup_probe"] = {"classification": "skipped_offline"}

    if mode == "live":
        try:
            import requests as _req  # noqa: F401
            _have_requests = True
        except ImportError:
            _have_requests = False

        # /status or /health — optional. Not all builds expose them; if absent
        # we record 'unavailable' and proceed rather than failing the header.
        if _have_requests:
            import requests as _req
            for path in ("/status", "/health"):
                try:
                    r = _req.get(
                        f"{api_base.rstrip('/')}{path}",
                        timeout=5,
                    )
                    if r.status_code == 200:
                        try:
                            j = r.json()
                        except Exception:
                            j = None
                        if isinstance(j, dict):
                            if "model" in j and j["model"]:
                                header["api_model"] = str(j["model"])
                            if "uptime_seconds" in j:
                                header["api_uptime_seconds"] = j["uptime_seconds"]
                            elif "uptime" in j:
                                header["api_uptime_seconds"] = j["uptime"]
                        break
                except Exception:
                    continue

        if header["api_model"]:
            header["api_model_hash"] = _hashlib.sha256(
                str(header["api_model"]).encode("utf-8")
            ).hexdigest()[:12]
        else:
            header["api_model"] = "unavailable — /status endpoint not exposed"
            header["api_model_hash"] = "unavailable"

        # api.log freshness — mtime of the last-written line, approximated
        # by file mtime. Cheap, covers the "was the stack idle?" question.
        api_log_path = REPO_ROOT / ".runtime" / "logs" / "api.log"
        try:
            if api_log_path.exists():
                header["api_log_last_line_age_seconds"] = round(
                    time.time() - os.path.getmtime(api_log_path), 1
                )
        except Exception:
            header["api_log_last_line_age_seconds"] = None

        # Warmup probe — one trivial /api/extract-fields call. RTT classifies
        # the stack per CLAUDE.md cold-boot rule. Uses a janice person_id
        # because janice is the most-populated narrator in the case bank and
        # the extractor will always have a schema view for her.
        if _have_requests:
            import requests as _req
            probe_payload = {
                "person_id":           "93479171-0b97-4072-bcf0-d44c7f9078ba",
                "session_id":          "discipline_warmup",
                "answer":              "My name is Janice.",
                "current_section":     "personal_identity",
                "current_target_path": "personal.firstName",
                "current_phase":       "childhood_origins",
                "current_era":         "early_childhood",
                "current_pass":        "pass1",
                "current_mode":        "open",
            }
            try:
                _t0 = time.time()
                _r = _req.post(
                    f"{api_base.rstrip('/')}/api/extract-fields",
                    json=probe_payload, timeout=120,
                )
                _rtt_ms = round((time.time() - _t0) * 1000)
                header["warmup_probe"] = {
                    "post_extract_roundtrip_ms": _rtt_ms,
                    "http_status": _r.status_code,
                    "classification": (
                        "hot"     if _rtt_ms <  30_000
                        else "warming" if _rtt_ms <  90_000
                        else "cold"
                    ),
                }
            except Exception as e:
                header["warmup_probe"] = {
                    "post_extract_roundtrip_ms": None,
                    "http_status": None,
                    "classification": "unreachable",
                    "error": f"{type(e).__name__}: {e}",
                }
        else:
            header["warmup_probe"] = {
                "classification": "unreachable",
                "error": "requests package not installed",
            }

    # Scorer + case-bank hashes — detect scorer or fixture drift across runs
    # that would otherwise masquerade as extractor movement.
    try:
        header["scorer_version"] = _hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest()[:12]
    except Exception:
        header["scorer_version"] = "unavailable"
    try:
        header["case_bank_version"] = _hashlib.sha256(
            cases_path.read_bytes()
        ).hexdigest()[:12]
    except Exception:
        header["case_bank_version"] = "unavailable"

    # Render a ~20-line console-friendly representation.
    lines: List[str] = []
    lines.append(f"[discipline] eval_tag={header['eval_tag']}")
    lines.append(f"[discipline] started_at={header['started_at']}")
    lines.append(f"[discipline] mode={header['mode']}")
    lines.append(
        f"[discipline] git_sha={header['git_sha']} "
        f"git_dirty={header['git_dirty']} "
        f"branch={header['branch']}"
    )
    lines.append("[discipline] flags:")
    for name in _DISCIPLINE_FLAG_NAMES:
        v = header["flags"][name]
        suffix = " (default)" if v == "0" else ""
        lines.append(f"  {name}={v}{suffix}")
    lines.append(f"[discipline] api_endpoint={header['api_endpoint']}")
    lines.append(
        f"[discipline] api_model={header['api_model']}  "
        f"api_model_hash={header['api_model_hash']}"
    )
    if header["api_uptime_seconds"] is not None:
        lines.append(
            f"[discipline] api_uptime_seconds={header['api_uptime_seconds']}"
        )
    if header["api_log_last_line_age_seconds"] is not None:
        lines.append(
            f"[discipline] api_log_last_line_age_seconds="
            f"{header['api_log_last_line_age_seconds']}"
        )
    wp = header["warmup_probe"]
    lines.append("[discipline] warmup_probe:")
    if wp.get("post_extract_roundtrip_ms") is not None:
        lines.append(
            f"  post_extract_roundtrip_ms={wp['post_extract_roundtrip_ms']}"
        )
    lines.append(f"  classification: {wp.get('classification', 'unknown')}")
    if wp.get("error"):
        lines.append(f"  error: {wp['error']}")
    lines.append(f"[discipline] scorer_version={header['scorer_version']}")
    lines.append(f"[discipline] case_bank_version={header['case_bank_version']}")

    rendered = "\n".join(lines) + "\n"
    return header, rendered


# ── Scoring ─────────────────────────────────────────────────────────────────

def normalize_value(v: str) -> str:
    """Lowercase, strip whitespace, collapse spaces for fuzzy matching."""
    if not v:
        return ""
    return " ".join(v.lower().strip().split())


# ── Date normalization ──────────────────────────────────────────────────────
_MONTH_NAMES = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}

def _normalize_date(v: str) -> Optional[str]:
    """Try to normalize a date string to YYYY-MM-DD. Returns None if not a date."""
    v = v.strip().lower()
    # Already YYYY-MM-DD?
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', v)
    if m:
        return v
    # "Month DDth, YYYY" or "Month DD, YYYY" variants
    m = re.match(r'^(\w+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})$', v)
    if m:
        month_str, day, year = m.group(1), m.group(2), m.group(3)
        mm = _MONTH_NAMES.get(month_str)
        if mm:
            return f"{year}-{mm}-{day.zfill(2)}"
    # "DD Month YYYY"
    m = re.match(r'^(\d{1,2})\s+(\w+)\s+(\d{4})$', v)
    if m:
        day, month_str, year = m.group(1), m.group(2), m.group(3)
        mm = _MONTH_NAMES.get(month_str)
        if mm:
            return f"{year}-{mm}-{day.zfill(2)}"
    return None


# ── Role / occupation abbreviation aliases (WO-EX-NARRATIVE-FIELD-01 Phase 3)
# Bidirectional alias map for unambiguous professional-role initialisms. When
# either side of a comparison (expected or actual) is a known abbreviation and
# the other is its canonical expansion, treat them as an exact match. Scoped
# narrowly to healthcare/therapy roles where abbreviations are standard and
# collision with common English words is zero. Widen only when a corpus case
# surfaces need. See case_040 (OT ↔ Occupational therapist).
_ROLE_ALIASES = {
    "ot":  "occupational therapist",
    "pt":  "physical therapist",
    "rn":  "registered nurse",
    "lpn": "licensed practical nurse",
    "np":  "nurse practitioner",
    "slp": "speech language pathologist",
}


def _role_alias_match(e: str, a: str) -> bool:
    """Return True if normalized values e, a are alias-equivalent.

    Bidirectional: accepts "OT" ↔ "Occupational therapist" in either order.
    """
    if _ROLE_ALIASES.get(e) == a:
        return True
    if _ROLE_ALIASES.get(a) == e:
        return True
    return False


def score_field_match(expected_val: str, actual_val: str) -> float:
    """Score a single field match. Returns 0.0-1.0."""
    e = normalize_value(expected_val)
    a = normalize_value(actual_val)
    if not e or not a:
        return 0.0
    if e == a:
        return 1.0

    # Role abbreviation alias (Phase 3 scorer relax): OT ↔ Occupational therapist
    if _role_alias_match(e, a):
        return 1.0

    # Date-aware comparison: normalize both to YYYY-MM-DD before comparing
    e_date = _normalize_date(expected_val)
    a_date = _normalize_date(actual_val)
    if e_date and a_date:
        if e_date == a_date:
            return 1.0
        # Same year but different day/month
        if e_date[:4] == a_date[:4]:
            return 0.5
        return 0.0

    # Substring containment (either direction)
    if e in a or a in e:
        return 0.8
    # Check if all key tokens from expected appear in actual
    e_tokens = set(e.split())
    a_tokens = set(a.split())
    if e_tokens and e_tokens.issubset(a_tokens):
        return 0.9
    overlap = len(e_tokens & a_tokens)
    if e_tokens:
        ratio = overlap / len(e_tokens)
        if ratio >= 0.5:
            return round(0.5 + ratio * 0.3, 2)
    return 0.0


def score_case(case: dict, extracted_items: List[dict]) -> dict:
    """Score a single evaluation case against extracted items.

    Returns a dict with:
      - field_scores: {fieldPath: {expected, actual, score}}
      - forbidden_violations: [fieldPath, ...]
      - overall_score: float 0.0-1.0
      - failure_categories: [str, ...]
      - pass: bool (overall_score >= 0.7 and no forbidden violations)
      - truth_zone_scores: {zone: {total, hit, miss}} (v3)
    """
    expected_fields = case.get("expectedFields", {})
    forbidden_fields = case.get("forbiddenFields", [])
    expected_behavior = case.get("expectedBehavior", "extract_single")
    truth_zones = case.get("truthZones", {})

    # WO-QB-GENERATIONAL-01: build truthZones from array-style keys if not present.
    # Generational cases use must_extract/may_extract/should_ignore/must_not_write
    # arrays instead of a truthZones dict.
    #
    # WO-QB-GENERATIONAL-01B fix: the same fieldPath can appear in multiple zones
    # (e.g. case_203 has hobbies.hobbies in both must_extract and should_ignore
    # with different values). Use a list of zone entries per fieldPath so later
    # zones don't overwrite earlier ones.
    if not truth_zones:
        _tz_list: Dict[str, list] = {}  # fieldPath -> [zone_entry, ...]
        for entry in case.get("must_extract", []):
            fp = entry.get("fieldPath", "")
            if fp:
                _tz_list.setdefault(fp, []).append({"zone": "must_extract", "expected": entry.get("value", "")})
        for entry in case.get("may_extract", []):
            fp = entry.get("fieldPath", "")
            if fp:
                _tz_list.setdefault(fp, []).append({"zone": "may_extract", "expected": entry.get("value", "")})
        for entry in case.get("should_ignore", []):
            fp = entry.get("fieldPath", "")
            if fp:
                _tz_list.setdefault(fp, []).append({"zone": "should_ignore"})
        for entry in case.get("must_not_write", []):
            fp = entry.get("fieldPath", "")
            if fp:
                _tz_list.setdefault(fp, []).append({"zone": "must_not_write"})
        # Flatten: if a fieldPath has only one entry, store it directly (backward compat).
        # If it has multiple entries, store as a list under a "_multi" wrapper.
        for fp, entries in _tz_list.items():
            if len(entries) == 1:
                truth_zones[fp] = entries[0]
            else:
                truth_zones[fp] = {"_multi": entries}

    # Build a lookup from extracted items: fieldPath -> list of values
    extracted_map: Dict[str, List[str]] = {}
    for item in extracted_items:
        fp = item.get("fieldPath", "")
        val = item.get("value", "")
        if fp not in extracted_map:
            extracted_map[fp] = []
        extracted_map[fp].append(val)

    # Score each expected field (backward compat)
    field_scores = {}
    for fp, exp_val in expected_fields.items():
        actual_vals = extracted_map.get(fp, [])
        if not actual_vals:
            field_scores[fp] = {
                "expected": exp_val,
                "actual": None,
                "score": 0.0,
                "status": "missing"
            }
        else:
            # Find best match among extracted values for this fieldPath
            best_score = 0.0
            best_val = actual_vals[0]
            for av in actual_vals:
                s = score_field_match(exp_val, av)
                if s > best_score:
                    best_score = s
                    best_val = av
            field_scores[fp] = {
                "expected": exp_val,
                "actual": best_val,
                "score": best_score,
                "status": "exact" if best_score == 1.0 else "partial" if best_score > 0 else "wrong"
            }

    # Check forbidden fields (backward compat)
    forbidden_violations = []
    for fp in forbidden_fields:
        if fp in extracted_map:
            forbidden_violations.append(fp)

    # ── Truth zone scoring (v3) ────────────────────────────────────────────
    tz_scores: Dict[str, Dict[str, int]] = {
        "must_extract": {"total": 0, "hit": 0, "miss": 0},
        "may_extract": {"total": 0, "hit": 0, "miss": 0},
        "should_ignore": {"total": 0, "hit": 0, "miss": 0, "leaked": 0},
        "must_not_write": {"total": 0, "hit": 0, "miss": 0, "violated": 0},
    }
    tz_details: Dict[str, dict] = {}

    # WO-QB-GENERATIONAL-01B: score each zone entry, handling _multi wrappers
    # where the same fieldPath appears in multiple zones.
    def _score_one_tz_entry(fp: str, tz_entry: dict, idx_suffix: str = ""):
        zone = tz_entry.get("zone", "must_extract")
        expected_val = tz_entry.get("expected", "")
        # WO-EX-SECTION-EFFECT-01 Phase 2 scorer policy: alt_defensible_paths
        # lets a must_extract zone be credited when the primary path isn't
        # emitted but an adjudicated-defensible alternative path is. Applies
        # only to must_extract zones (see WO-EX-SECTION-EFFECT-01_Spec.md §Scope).
        alt_paths = tz_entry.get("alt_defensible_paths") or []
        # WO-QB-ALT-VALUES-01 (#97): value-axis sibling of alt_defensible_paths.
        # Credits a must_extract zone when the emission lands on the PRIMARY
        # path but the value is a defensible rephrasing of the expected
        # string — e.g. "rode every morning before chores" vs. the adjudicated
        # "rode every morning before chores in Dodge". Scoped to case_075 and
        # case_088 for the first cut (out_of_scope stubborn set) so we don't
        # globally loosen the value-match bar. Applies only to must_extract.
        alt_values = tz_entry.get("alt_defensible_values") or []
        was_extracted = fp in extracted_map
        detail_key = f"{fp}{idx_suffix}"

        if zone == "must_extract":
            tz_scores["must_extract"]["total"] += 1

            # 1. Try the primary path (existing behavior).
            primary_hit = False
            primary_best = 0.0
            if was_extracted and expected_val:
                primary_best = max(
                    (score_field_match(expected_val, v) for v in extracted_map[fp]),
                    default=0.0,
                )
                primary_hit = primary_best >= 0.5
            elif was_extracted:
                # No expected value declared — any emission to the primary path counts.
                primary_hit = True

            # 2. WO-QB-ALT-VALUES-01 (#97). If primary-path value missed,
            # try alt_defensible_values against the primary path's extracted
            # values. Winning_via="alt_defensible_value" marks this credit.
            value_alt_hit = False
            winning_value_alt = None
            winning_value_alt_score = 0.0
            if not primary_hit and was_extracted and alt_values:
                for av_expected in alt_values:
                    if not av_expected:
                        continue
                    best = max(
                        (score_field_match(av_expected, v) for v in extracted_map[fp]),
                        default=0.0,
                    )
                    if best >= 0.5 and best > winning_value_alt_score:
                        value_alt_hit = True
                        winning_value_alt_score = best
                        winning_value_alt = av_expected

            # 3. If primary + value-alt both missed, consult alt_defensible_paths.
            alt_hit = False
            winning_alt_path = None
            winning_alt_score = 0.0
            if not primary_hit and not value_alt_hit and alt_paths and expected_val:
                for ap in alt_paths:
                    if ap in extracted_map:
                        ab = max(
                            (score_field_match(expected_val, v) for v in extracted_map[ap]),
                            default=0.0,
                        )
                        if ab >= 0.5 and ab > winning_alt_score:
                            alt_hit = True
                            winning_alt_score = ab
                            winning_alt_path = ap

            # 4. WO-EX-VALUE-ALT-CREDIT-01 (#97) step-3 NEW branch: if alt path
            # matched at all (but value fuzzy <0.5 vs expected), re-check the
            # alt-path values against alt_defensible_values. This closes the
            # value-drift-on-alt-path class — e.g. case_087 LLM emits
            # greatGrandparents.ancestry='French' when expected is
            # 'French (Alsace-Lorraine), German (Hanover)'. The path alt fires
            # only on the primary expected value under step 3; step 4 is the
            # second-chance scorer for a pre-curated alt-value set on the same
            # alt path. Strictly additive: cases without alt_defensible_values
            # are unaffected. Gate remains ≥0.5.
            alt_value_hit = False
            winning_alt_value_path = None
            winning_alt_value_score = 0.0
            winning_alt_value = None
            if (not primary_hit and not value_alt_hit and not alt_hit
                    and alt_paths and alt_values):
                for ap in alt_paths:
                    if ap not in extracted_map:
                        continue
                    for av_expected in alt_values:
                        if not av_expected:
                            continue
                        ab = max(
                            (score_field_match(av_expected, v)
                             for v in extracted_map[ap]),
                            default=0.0,
                        )
                        if ab >= 0.5 and ab > winning_alt_value_score:
                            alt_value_hit = True
                            winning_alt_value_score = ab
                            winning_alt_value_path = ap
                            winning_alt_value = av_expected

            if primary_hit:
                tz_scores["must_extract"]["hit"] += 1
                tz_details[detail_key] = {
                    "zone": zone,
                    "extracted": True,
                    "winning_path": fp,
                    "winning_via": "primary",
                    "winning_score": round(primary_best, 3),
                }
            elif value_alt_hit:
                tz_scores["must_extract"]["hit"] += 1
                tz_details[detail_key] = {
                    "zone": zone,
                    "extracted": True,
                    "winning_path": fp,
                    "winning_via": "alt_defensible_value",
                    "winning_score": round(winning_value_alt_score, 3),
                    "matched_alt_value": winning_value_alt,
                    "alt_defensible_values": list(alt_values),
                }
            elif alt_hit:
                tz_scores["must_extract"]["hit"] += 1
                tz_details[detail_key] = {
                    "zone": zone,
                    "extracted": True,
                    "winning_path": winning_alt_path,
                    "winning_via": "alt_defensible_path",
                    "winning_score": round(winning_alt_score, 3),
                    "alt_defensible_paths": list(alt_paths),
                }
            elif alt_value_hit:
                # WO-EX-VALUE-ALT-CREDIT-01 (#97) step-3: alt path + alt value.
                tz_scores["must_extract"]["hit"] += 1
                tz_details[detail_key] = {
                    "zone": zone,
                    "extracted": True,
                    "winning_path": winning_alt_value_path,
                    "winning_via": "alt_defensible_path_and_value",
                    "winning_score": round(winning_alt_value_score, 3),
                    "matched_alt_value": winning_alt_value,
                    "alt_defensible_paths": list(alt_paths),
                    "alt_defensible_values": list(alt_values),
                }
            else:
                tz_details[detail_key] = {
                    "zone": zone,
                    "extracted": was_extracted,
                    "winning_path": None,
                    "winning_via": None,
                    **({"alt_defensible_paths": list(alt_paths)} if alt_paths else {}),
                    **({"alt_defensible_values": list(alt_values)} if alt_values else {}),
                }
                tz_scores["must_extract"]["miss"] += 1

        elif zone == "may_extract":
            tz_scores["may_extract"]["total"] += 1
            if was_extracted:
                tz_scores["may_extract"]["hit"] += 1
            else:
                tz_scores["may_extract"]["miss"] += 1
            tz_details[detail_key] = {"zone": zone, "extracted": was_extracted}

        elif zone == "should_ignore":
            tz_scores["should_ignore"]["total"] += 1
            if was_extracted:
                tz_scores["should_ignore"]["leaked"] += 1
            else:
                tz_scores["should_ignore"]["hit"] += 1
            tz_details[detail_key] = {"zone": zone, "extracted": was_extracted, "leaked": was_extracted}

        elif zone == "must_not_write":
            tz_scores["must_not_write"]["total"] += 1
            if was_extracted:
                tz_scores["must_not_write"]["violated"] += 1
            else:
                tz_scores["must_not_write"]["hit"] += 1
            tz_details[detail_key] = {"zone": zone, "extracted": was_extracted, "violated": was_extracted}

    for fp, tz in truth_zones.items():
        if "_multi" in tz:
            # Same fieldPath in multiple zones — score each independently
            for i, entry in enumerate(tz["_multi"]):
                _score_one_tz_entry(fp, entry, f"[{i}]")
        else:
            _score_one_tz_entry(fp, tz)

    # ── Overall score (uses truth zones when available, falls back to v2) ──
    if truth_zones:
        # must_extract recall (primary)
        must_total = tz_scores["must_extract"]["total"]
        must_hit = tz_scores["must_extract"]["hit"]
        must_recall = must_hit / must_total if must_total else 1.0

        # may_extract bonus (secondary — adds up to 0.1)
        may_total = tz_scores["may_extract"]["total"]
        may_hit = tz_scores["may_extract"]["hit"]
        may_bonus = 0.1 * (may_hit / may_total) if may_total else 0.0

        # should_ignore penalty (0.1 per leak)
        ignore_leaked = tz_scores["should_ignore"]["leaked"]
        ignore_penalty = 0.1 * ignore_leaked

        # must_not_write penalty (0.2 per violation)
        mnw_violated = tz_scores["must_not_write"]["violated"]
        mnw_penalty = 0.2 * mnw_violated

        overall_score = max(0.0, min(1.0, must_recall + may_bonus - ignore_penalty - mnw_penalty))

    # Always compute v2-compatible score for baseline comparison
    if field_scores:
        v2_avg = sum(fs["score"] for fs in field_scores.values()) / len(field_scores)
    else:
        v2_avg = 0.0
    v2_penalty = 0.2 * len(forbidden_violations)
    v2_score = max(0.0, v2_avg - v2_penalty)
    v2_pass = v2_score >= 0.7 and len(forbidden_violations) == 0

    if not truth_zones:
        # v2 fallback (no truth zones)
        overall_score = v2_score

    # Classify failures
    # WO-EX-SECTION-EFFECT-01 Phase 2: if a primary path is "missing" in v2
    # field_scores but the emission landed on an alt_defensible_path for that
    # same must_extract truth zone, do NOT tag field_path_mismatch — the emission
    # is defensible by adjudication, not a mismatch. Tag 'defensible_alt_credit'
    # instead so the audit shows what happened.
    #
    # WO-QB-ALT-VALUES-01 (#97): mirror of the above on the value axis. If the
    # primary path IS emitted but its value misses the strict 0.7 match while
    # matching an adjudicated alt_defensible_values entry ≥ 0.5, do NOT tag
    # llm_hallucination — it's a defensible rephrase. Tag 'defensible_value_alt_credit'.
    def _alt_paths_for(fp_primary: str) -> set:
        tz = truth_zones.get(fp_primary)
        if not tz:
            return set()
        if "_multi" in tz:
            out: set = set()
            for e in tz["_multi"]:
                if e.get("zone") == "must_extract":
                    out.update(e.get("alt_defensible_paths") or [])
            return out
        if tz.get("zone") == "must_extract":
            return set(tz.get("alt_defensible_paths") or [])
        return set()

    def _alt_values_for(fp_primary: str) -> list:
        tz = truth_zones.get(fp_primary)
        if not tz:
            return []
        if "_multi" in tz:
            out: list = []
            for e in tz["_multi"]:
                if e.get("zone") == "must_extract":
                    out.extend(e.get("alt_defensible_values") or [])
            return out
        if tz.get("zone") == "must_extract":
            return list(tz.get("alt_defensible_values") or [])
        return []

    failure_categories = []
    for fp, fs in field_scores.items():
        if fs["status"] == "missing":
            alt_set = _alt_paths_for(fp)
            alt_vals_for_fp = _alt_values_for(fp)
            # Was it extracted under a different path?
            found_alt_defensible = False
            found_elsewhere = False
            for efp, vals in extracted_map.items():
                if efp != fp:
                    for v in vals:
                        if score_field_match(fs["expected"], v) >= 0.7:
                            if efp in alt_set:
                                found_alt_defensible = True
                            else:
                                found_elsewhere = True
                            break
                    if found_alt_defensible or found_elsewhere:
                        break
            # WO-EX-VALUE-ALT-CREDIT-01 (#97) step-3 classifier: if none of the
            # ≥0.7 checks fired but an alt path carries a value that fuzzy-
            # matches any alt_defensible_values entry ≥0.5, tag defensible_
            # alt_value_credit rather than schema_gap. Matches the scorer's
            # step-3 crediting so the classifier mirrors the truth-zone hit.
            found_alt_value_defensible = False
            if (not found_alt_defensible and not found_elsewhere
                    and alt_set and alt_vals_for_fp):
                for efp in alt_set:
                    if efp in extracted_map:
                        for av_expected in alt_vals_for_fp:
                            if not av_expected:
                                continue
                            for v in extracted_map[efp]:
                                if score_field_match(av_expected, v) >= 0.5:
                                    found_alt_value_defensible = True
                                    break
                            if found_alt_value_defensible:
                                break
                    if found_alt_value_defensible:
                        break
            if found_alt_defensible:
                failure_categories.append("defensible_alt_credit")
            elif found_alt_value_defensible:
                failure_categories.append("defensible_alt_value_credit")
            elif found_elsewhere:
                failure_categories.append("field_path_mismatch")
            else:
                failure_categories.append("schema_gap")
        elif fs["status"] == "wrong":
            # WO-QB-ALT-VALUES-01: before tagging llm_hallucination, check whether
            # the emitted value on the primary path matches any alt_defensible_value
            # at the 0.5 threshold. If so, the tag is defensible_value_alt_credit
            # (and the truth-zone scorer above has already credited the zone hit).
            alt_vals = _alt_values_for(fp)
            rescued = False
            if alt_vals and fs.get("actual"):
                for av in alt_vals:
                    if av and score_field_match(av, fs["actual"]) >= 0.5:
                        rescued = True
                        break
            if rescued:
                failure_categories.append("defensible_value_alt_credit")
            else:
                failure_categories.append("llm_hallucination")

    if forbidden_violations:
        failure_categories.append("guard_false_positive")

    # Add truth-zone-specific failure categories
    if tz_scores["should_ignore"]["leaked"] > 0:
        failure_categories.append("noise_leakage")
    if tz_scores["must_not_write"]["violated"] > 0 and "guard_false_positive" not in failure_categories:
        failure_categories.append("guard_false_positive")

    passed = overall_score >= 0.7 and len(forbidden_violations) == 0 and tz_scores["must_not_write"]["violated"] == 0

    return {
        "field_scores": field_scores,
        "forbidden_violations": forbidden_violations,
        "overall_score": round(overall_score, 3),
        "v2_score": round(v2_score, 3),
        "v2_pass": v2_pass,
        "failure_categories": list(set(failure_categories)),
        "pass": passed,
        "truth_zone_scores": tz_scores,
        "truth_zone_details": tz_details,
    }


# ── Offline mode ────────────────────────────────────────────────────────────

def run_offline(cases: List[dict]) -> List[dict]:
    """Run cases using mockLlmOutput — no LLM, no server required.

    Validates that the mock output scores correctly against expectations.
    This tests the scoring harness and fixture quality.
    """
    results = []
    for case in cases:
        mock_items = case.get("mockLlmOutput", [])
        result = score_case(case, mock_items)
        result["case_id"] = case["id"]
        result["narratorId"] = case["narratorId"]
        result["phase"] = case["phase"]
        result["subTopic"] = case["subTopic"]
        result["expectedBehavior"] = case["expectedBehavior"]
        result["currentExtractorExpected"] = case.get("currentExtractorExpected", True)
        result["caseType"] = case.get("caseType", "contract")
        result["oralHistoryStyle"] = case.get("oralHistoryStyle", "life_history")
        result["style_bucket"] = case.get("style_bucket", "life_history")
        result["chunk_size"] = case.get("chunk_size", "small")
        result["noise_profile"] = case.get("noise_profile", "clean")
        result["case_mode"] = case.get("case_mode", "contract")
        result["sequence_group"] = case.get("sequence_group")
        result["mode"] = "offline"
        result["extracted_count"] = len(mock_items)
        # WO-QB-EVAL-EXPAND-01 — life-map + diagnostic axes. Offline mode
        # synthesizes stage context the same way run_live does so the by_era /
        # by_pass / by_mode / by_era_x_pass axes stay populated across both
        # modes. method is stamped "offline_mock" so method_distribution is
        # honest rather than empty.
        result["current_era"]  = case.get("currentEra")  or _phase_to_era(case.get("phase", ""))
        result["current_pass"] = case.get("currentPass") or "pass1"
        result["current_mode"] = case.get("currentMode") or "open"
        result["method"]       = "offline_mock"
        result["confidence_stats"] = _confidence_stats(mock_items)
        result["stubborn_partition"] = _stubborn_partition_for(case["id"])
        # WO-EX-DENSE-DIAG-01 — pipe diagnostic metadata through for dense_metrics
        if "_diagFamily" in case:
            result["_diagFamily"] = case["_diagFamily"]
            result["_diagSubclass"] = case.get("_diagSubclass", "")
        if "_cardinality_assertion" in case:
            result["_cardinality_assertion"] = case["_cardinality_assertion"]
        if "_length_assertion" in case:
            result["_length_assertion"] = case["_length_assertion"]
        results.append(result)
    return results


# ── Live mode ───────────────────────────────────────────────────────────────

def run_live(cases: List[dict], api_base: str) -> List[dict]:
    """Run cases by POSTing to the real extraction endpoint."""
    try:
        import requests
    except ImportError:
        print("ERROR: 'requests' package required for live mode. pip install requests")
        sys.exit(1)

    # Map narrator IDs to person_ids (from the live database)
    NARRATOR_PERSON_IDS = {
        "janice-josephine-horne": "93479171-0b97-4072-bcf0-d44c7f9078ba",
        "kent-james-horne": "4aa0cc2b-1f27-433a-9152-203bb1f69a55",
        "christopher-todd-horne": "a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2",
    }

    endpoint = f"{api_base.rstrip('/')}/api/extract-fields"
    results = []

    for case in cases:
        person_id = NARRATOR_PERSON_IDS.get(case["narratorId"])
        if not person_id:
            print(f"  SKIP {case['id']}: no person_id for {case['narratorId']}")
            continue

        # Support both master-eval keys (narratorReply, extractPriority)
        # and generational-pack keys (answer, extract_priority)
        narrator_reply = case.get("narratorReply") or case.get("answer", "")
        extract_prio = case.get("extractPriority") or case.get("extract_priority")

        # WO-EX-SECTION-EFFECT-01 Phase 2 (#93): synthesize life-map stage
        # context so the payload round-trips era/pass/mode. Era is derived
        # from the case's phase via _phase_to_era. Pass/mode default to
        # pass1/open (state.js defaults) unless the case file overrides.
        # Cases may opt in by setting top-level "currentPass" / "currentMode"
        # — no current case does, but the pass-through is ready for Phase 3.
        _case_era  = case.get("currentEra")  or _phase_to_era(case.get("phase", ""))
        _case_pass = case.get("currentPass") or "pass1"
        _case_mode = case.get("currentMode") or "open"

        payload = {
            "person_id": person_id,
            "session_id": f"eval_{case['id']}",
            "answer": narrator_reply,
            "current_section": case.get("subTopic"),
            "current_target_path": extract_prio[0] if extract_prio else None,
            # WO-EX-TURNSCOPE-01 r4h follow-up: pass the FULL extractPriority
            # list so the turn-scope filter unions branch roots across all
            # declared targets. Without this, compound-extract cases like
            # case_060 (spouse + children) lose the non-[0] branches.
            "current_target_paths": list(extract_prio) if extract_prio else None,
            "current_phase": _phase_to_spine_phase(case.get("phase", "")),
            # WO-EX-SECTION-EFFECT-01 Phase 2 (#93).
            "current_era":  _case_era,
            "current_pass": _case_pass,
            "current_mode": _case_mode,
        }

        try:
            t0 = time.time()
            # WO-EX-CLAIMS-01: compound answers (multiple children, etc.) can take
            # 30-45s on the 8B model with 384-token cap. Use 90s to avoid timeouts.
            resp = requests.post(endpoint, json=payload, timeout=90)
            elapsed = time.time() - t0

            if resp.status_code == 200:
                data = resp.json()
                extracted_items = data.get("items", [])
                method = data.get("method", "unknown")
            else:
                extracted_items = []
                method = f"http_{resp.status_code}"
                print(f"  WARN {case['id']}: HTTP {resp.status_code}")
        except Exception as e:
            extracted_items = []
            method = f"error_{type(e).__name__}"
            elapsed = 0
            print(f"  ERROR {case['id']}: {e}")

        result = score_case(case, extracted_items)
        result["case_id"] = case["id"]
        result["narratorId"] = case["narratorId"]
        result["phase"] = case["phase"]
        result["subTopic"] = case["subTopic"]
        result["expectedBehavior"] = case["expectedBehavior"]
        result["currentExtractorExpected"] = case.get("currentExtractorExpected", True)
        result["caseType"] = case.get("caseType", "contract")
        result["oralHistoryStyle"] = case.get("oralHistoryStyle", "life_history")
        result["style_bucket"] = case.get("style_bucket", "life_history")
        result["chunk_size"] = case.get("chunk_size", "small")
        result["noise_profile"] = case.get("noise_profile", "clean")
        result["case_mode"] = case.get("case_mode", "contract")
        result["sequence_group"] = case.get("sequence_group")
        result["mode"] = "live"
        result["method"] = method
        result["elapsed_ms"] = round(elapsed * 1000)
        result["extracted_count"] = len(extracted_items)
        # WO-QB-EVAL-EXPAND-01 — persist synthesized stage context and
        # confidence summary so the life-map / diagnostic report axes can
        # read them directly rather than re-deriving per case.
        result["current_era"]  = _case_era
        result["current_pass"] = _case_pass
        result["current_mode"] = _case_mode
        result["confidence_stats"] = _confidence_stats(extracted_items)
        result["stubborn_partition"] = _stubborn_partition_for(case["id"])
        # Compact raw items for report — only fieldPath, value (capped), confidence
        compact_items = []
        for item in extracted_items:
            val = item.get("value", "")
            if isinstance(val, str):
                val = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', val)
                if len(val) > 100:
                    val = val[:100] + "…"
            compact_items.append({
                "fieldPath": item.get("fieldPath", ""),
                "value": val,
                "confidence": item.get("confidence"),
            })
        result["raw_items"] = compact_items
        # WO-EX-DENSE-DIAG-01 — pipe diagnostic metadata through for dense_metrics
        if "_diagFamily" in case:
            result["_diagFamily"] = case["_diagFamily"]
            result["_diagSubclass"] = case.get("_diagSubclass", "")
        if "_cardinality_assertion" in case:
            result["_cardinality_assertion"] = case["_cardinality_assertion"]
        if "_length_assertion" in case:
            result["_length_assertion"] = case["_length_assertion"]
        results.append(result)

    return results


def _phase_to_spine_phase(phase_key: str) -> Optional[str]:
    """Map question_bank phase key to a spine phase hint."""
    mapping = {
        "developmental_foundations": "pre_school",
        "transitional_adolescence": "high_school",
        "early_adulthood": "post_school",
        "midlife": "post_school",
        "legacy_reflection": "post_school",
    }
    return mapping.get(phase_key)


def _phase_to_era(phase_key: str) -> Optional[str]:
    """Map question_bank phase key to a life-map currentEra label.

    WO-EX-SECTION-EFFECT-01 Phase 2 (#93). Synthesized stage context so
    the eval round-trips era/pass/mode into the extraction payload and
    logs — the causal matrix in Phase 3 consumes these lines.

    Life-map era taxonomy (ui/js/life-map.js): early_childhood /
    school_years / adolescence / early_adulthood / midlife / later_life.
    """
    mapping = {
        "childhood_origins":        "early_childhood",
        "developmental_foundations": "school_years",
        "transitional_adolescence": "adolescence",
        "early_adulthood":          "early_adulthood",
        "middle_adulthood":         "midlife",
        "midlife":                  "midlife",
        "later_adulthood":          "later_life",
        "legacy_reflection":        "later_life",
    }
    return mapping.get(phase_key)


# ── Dense-truth diagnostic metrics (WO-EX-DENSE-DIAG-01) ────────────────────

# Narrator-identity fields protected by the extractor; any emission here
# against a non-narrator subject is a narrator-identity corruption.
PROTECTED_IDENTITY_FIELDS = {
    "personal.fullName",
    "personal.preferredName",
    "personal.dateOfBirth",
    "personal.placeOfBirth",
    "personal.birthOrder",
}

# Field-path prefix → generation bucket, for per_generation_hits.
_GEN_PREFIX_MAP = [
    ("personal.", "narrator"),
    ("spouse.", "spouse"),
    ("children.", "child"),
    ("siblings.", "sibling"),
    ("parents.", "parent"),
    ("grandparents.", "grandparent"),
    ("greatGrandparents.", "greatGrandparent"),
    ("education.", "education"),
    ("pets.", "pet"),
    ("marriage.", "marriage"),
    ("familyTraditions.", "family_traditions"),
    ("earlyMemories.", "early_memories"),
    ("laterYears.", "later_years"),
    ("hobbies.", "hobbies"),
    ("health.", "health"),
    ("technology.", "technology"),
    ("additionalNotes.", "notes"),
]


def _generation_bucket(field_path: str) -> str:
    for prefix, bucket in _GEN_PREFIX_MAP:
        if field_path.startswith(prefix):
            return bucket
    return "other"


def _classify_method(method: str) -> str:
    """Classify an extractor method tag into parse_success / parse_failure / rules_fallback / other."""
    if not method:
        return "other"
    m = method.lower()
    if m.startswith("llm_") or m in ("llm", "json", "llm_json", "llm_json_repair", "llm_direct"):
        return "parse_success"
    if m.startswith("rules") or m == "rules_fallback" or m == "fallback":
        return "rules_fallback"
    if m.startswith("error_") or m.startswith("http_") or "parse_fail" in m or "parse_error" in m or m in ("empty", "timeout"):
        return "parse_failure"
    # Conservative default: unknown methods are other (not counted as success or failure)
    return "other"


def _check_cardinality_conflict(result: dict) -> bool:
    """Return True if this result violates its case's _cardinality_assertion.

    A cardinality conflict = at least one forbidden_duplicate_keys pattern matches
    the raw_items emitted for this case.
    """
    ca = result.get("_cardinality_assertion")
    if not ca:
        return False
    forbidden = ca.get("forbidden_duplicate_keys", [])
    if not forbidden:
        return False
    raw = result.get("raw_items", [])
    # forbidden patterns look like "parents[firstName=Pete]" — match against
    # any item where item.fieldPath starts with the array name and item.value
    # normalize-matches the =value side.
    for pattern in forbidden:
        try:
            # Parse "array[key=value]" pattern
            if "[" not in pattern or "]" not in pattern:
                continue
            arr_name = pattern.split("[", 1)[0]
            inner = pattern.split("[", 1)[1].rstrip("]")
            if "=" not in inner:
                continue
            key_name, forbidden_val = inner.split("=", 1)
            # Match items with fieldPath "{arr_name}.{key_name}" and value == forbidden_val
            target_fp = f"{arr_name}.{key_name}"
            for item in raw:
                fp = item.get("fieldPath", "")
                val = item.get("value", "")
                if fp == target_fp and normalize_value(val) == normalize_value(forbidden_val):
                    return True
        except Exception:
            continue
    return False


def _check_narrator_identity_leak(result: dict) -> bool:
    """Return True if this result emitted to a PROTECTED_IDENTITY_FIELD.

    For dense_truth diagnostic cases, none target the narrator's identity
    fields as must_extract. Any emission to those fields is a narrator-
    identity leak (potential grandparent/parent/sibling subject bleeding
    into the narrator's own identity slot).
    """
    # If the case DOES have a must_extract on any protected field, skip —
    # that's a legitimate target. (None of DIAG-01's 12 cases do this, but
    # future diag packs might.)
    tz_details = result.get("truth_zone_details", {})
    for fp, td in tz_details.items():
        base_fp = fp.split("[", 1)[0]  # strip multi-index suffix
        if base_fp in PROTECTED_IDENTITY_FIELDS and td.get("zone") == "must_extract":
            return False
    raw = result.get("raw_items", [])
    for item in raw:
        if item.get("fieldPath", "") in PROTECTED_IDENTITY_FIELDS:
            return True
    return False


def _compute_dense_metrics(results: List[dict]) -> dict:
    """Compute dense-truth diagnostic metrics for WO-EX-DENSE-DIAG-01.

    Only considers results that have the _diagFamily tag. Returns a dict
    with the 8 dense-specific metrics plus a per-family breakdown.
    """
    diag_results = [r for r in results if "_diagFamily" in r]
    if not diag_results:
        return {}

    # ── Parse / fallback counts ────────────────────────────────────────────
    parse_success = 0
    parse_failure = 0
    rules_fallback = 0
    method_other = 0
    method_tally: Dict[str, int] = {}
    for r in diag_results:
        m = r.get("method", "")
        method_tally[m] = method_tally.get(m, 0) + 1
        cls = _classify_method(m)
        if cls == "parse_success":
            parse_success += 1
        elif cls == "parse_failure":
            parse_failure += 1
        elif cls == "rules_fallback":
            rules_fallback += 1
        else:
            method_other += 1

    # ── invalid_fieldpath_rejection_count (approximation) ─────────────────
    # Count cases where failure_categories includes 'field_path_mismatch' or
    # 'schema_gap' — these correspond to the extractor emitting paths that
    # were either rejected or mismatched against the schema.
    invalid_fieldpath = 0
    for r in diag_results:
        fcs = r.get("failure_categories", [])
        if "field_path_mismatch" in fcs or "schema_gap" in fcs:
            invalid_fieldpath += 1

    # ── single_cardinality_conflict_count (Family B) ──────────────────────
    cardinality_conflicts = sum(1 for r in diag_results if _check_cardinality_conflict(r))

    # ── duplicate_narrator_identity_count ─────────────────────────────────
    narrator_identity_leaks = sum(1 for r in diag_results if _check_narrator_identity_leak(r))

    # ── per_generation_hits ───────────────────────────────────────────────
    # Walk every truth_zone_details entry across all diag results. For each
    # must_extract target, bucket by generation and record hit/miss.
    per_gen: Dict[str, Dict[str, int]] = {}
    for r in diag_results:
        for fp, td in r.get("truth_zone_details", {}).items():
            if td.get("zone") != "must_extract":
                continue
            # Strip array-index suffix like [0], [1] from the key
            base_fp = fp.split("[", 1)[0]
            bucket = _generation_bucket(base_fp)
            if bucket not in per_gen:
                per_gen[bucket] = {"total": 0, "hit": 0, "miss": 0}
            per_gen[bucket]["total"] += 1
            if td.get("extracted"):
                per_gen[bucket]["hit"] += 1
            else:
                per_gen[bucket]["miss"] += 1
    # Add recall per bucket
    for bucket, stats in per_gen.items():
        t = stats["total"]
        stats["recall"] = round(stats["hit"] / t, 3) if t else 0.0

    # ── v2_vs_v3_divergence_count ─────────────────────────────────────────
    v2_v3_divergence = sum(1 for r in diag_results if r.get("v2_pass") != r.get("pass"))
    v2_pass_v3_fail = sum(1 for r in diag_results if r.get("v2_pass") and not r.get("pass"))
    v3_pass_v2_fail = sum(1 for r in diag_results if r.get("pass") and not r.get("v2_pass"))

    # ── Per-family breakdown ──────────────────────────────────────────────
    by_family: Dict[str, Dict[str, Any]] = {}
    for r in diag_results:
        fam = r["_diagFamily"]
        if fam not in by_family:
            by_family[fam] = {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "avg_score": 0.0,
                "subclasses": {},
            }
        by_family[fam]["total"] += 1
        if r.get("pass"):
            by_family[fam]["passed"] += 1
        else:
            by_family[fam]["failed"] += 1
        by_family[fam]["avg_score"] += r.get("overall_score", 0.0)
        sub = r.get("_diagSubclass", "unlabeled")
        sub_entry = by_family[fam]["subclasses"].setdefault(
            sub, {"total": 0, "passed": 0, "avg_score": 0.0, "case_ids": []}
        )
        sub_entry["total"] += 1
        if r.get("pass"):
            sub_entry["passed"] += 1
        sub_entry["avg_score"] += r.get("overall_score", 0.0)
        sub_entry["case_ids"].append(r["case_id"])
    for fam, stats in by_family.items():
        t = stats["total"]
        stats["avg_score"] = round(stats["avg_score"] / t, 3) if t else 0
        stats["pass_rate"] = round(stats["passed"] / t, 3) if t else 0
        for sub, sub_entry in stats["subclasses"].items():
            st = sub_entry["total"]
            sub_entry["avg_score"] = round(sub_entry["avg_score"] / st, 3) if st else 0

    # ── Failure-class dominance (which of the 4 families is worst) ────────
    failure_class_dominance = sorted(
        [(fam, stats["passed"], stats["total"], stats["pass_rate"])
         for fam, stats in by_family.items()],
        key=lambda x: x[3],
    )

    total = len(diag_results)
    return {
        "_wo_gate": "WO-EX-DENSE-DIAG-01 Phase 2 metrics",
        "total_diag_cases": total,
        "parse_success_count": parse_success,
        "parse_failure_count": parse_failure,
        "rules_fallback_count": rules_fallback,
        "method_other_count": method_other,
        "method_tally": method_tally,
        "invalid_fieldpath_rejection_count": invalid_fieldpath,
        "single_cardinality_conflict_count": cardinality_conflicts,
        "duplicate_narrator_identity_count": narrator_identity_leaks,
        "per_generation_hits": per_gen,
        "v2_vs_v3_divergence_count": v2_v3_divergence,
        "v2_pass_v3_fail": v2_pass_v3_fail,
        "v3_pass_v2_fail": v3_pass_v2_fail,
        "by_diag_family": by_family,
        "failure_class_dominance": [
            {
                "family": fam,
                "passed": p,
                "total": t,
                "pass_rate": pr,
            }
            for fam, p, t, pr in failure_class_dominance
        ],
    }


# ── Report generation ───────────────────────────────────────────────────────

def generate_report(results: List[dict], mode: str) -> dict:
    """Build a structured report from scored results."""
    total = len(results)
    passed = sum(1 for r in results if r["pass"])
    failed = total - passed

    # Breakdown by expectedBehavior
    by_behavior = {}
    for r in results:
        b = r["expectedBehavior"]
        if b not in by_behavior:
            by_behavior[b] = {"total": 0, "passed": 0, "failed": 0}
        by_behavior[b]["total"] += 1
        if r["pass"]:
            by_behavior[b]["passed"] += 1
        else:
            by_behavior[b]["failed"] += 1

    # Breakdown by narrator
    by_narrator = {}
    for r in results:
        n = r["narratorId"]
        if n not in by_narrator:
            by_narrator[n] = {"total": 0, "passed": 0, "avg_score": 0.0}
        by_narrator[n]["total"] += 1
        if r["pass"]:
            by_narrator[n]["passed"] += 1
        by_narrator[n]["avg_score"] += r["overall_score"]
    for n in by_narrator:
        by_narrator[n]["avg_score"] = round(
            by_narrator[n]["avg_score"] / by_narrator[n]["total"], 3
        )

    # Expected vs unexpected failures
    expected_pass = [r for r in results if r["currentExtractorExpected"]]
    expected_fail = [r for r in results if not r["currentExtractorExpected"]]

    # Failure category distribution
    all_failures = {}
    for r in results:
        for fc in r.get("failure_categories", []):
            all_failures[fc] = all_failures.get(fc, 0) + 1

    # ── Helper: build a grouped breakdown ────────────────────────────────
    def _breakdown(key: str, default: str = "unknown") -> dict:
        groups: Dict[str, dict] = {}
        for r in results:
            val = r.get(key, default)
            if val not in groups:
                groups[val] = {"total": 0, "passed": 0, "failed": 0, "avg_score": 0.0}
            groups[val]["total"] += 1
            if r["pass"]:
                groups[val]["passed"] += 1
            else:
                groups[val]["failed"] += 1
            groups[val]["avg_score"] += r["overall_score"]
        for v in groups:
            t = groups[v]["total"]
            groups[v]["avg_score"] = round(groups[v]["avg_score"] / t, 3) if t else 0
        return groups

    by_case_type = _breakdown("caseType", "contract")
    by_style = _breakdown("style_bucket", "life_history")
    by_chunk = _breakdown("chunk_size", "small")
    by_noise = _breakdown("noise_profile", "clean")
    by_case_mode = _breakdown("case_mode", "contract")

    # ── WO-QB-EVAL-EXPAND-01: life-map axes ───────────────────────────────
    # New since SECTION-EFFECT Phase 2 (#93): case-level current_era /
    # current_pass / current_mode are persisted on every result. These
    # axes surface whether a given era or pass dominates the failure
    # frontier — useful input for SPANTAG Pass 2 sizing decisions.
    by_era  = _breakdown("current_era",  "unknown")
    by_pass = _breakdown("current_pass", "unknown")
    by_mode = _breakdown("current_mode", "unknown")

    # Cross-tab: era × pass. Keys are "era::pass" so JSON stays flat.
    by_era_x_pass: Dict[str, dict] = {}
    for r in results:
        era = r.get("current_era") or "unknown"
        ps  = r.get("current_pass") or "unknown"
        k = f"{era}::{ps}"
        if k not in by_era_x_pass:
            by_era_x_pass[k] = {"total": 0, "passed": 0, "failed": 0, "avg_score": 0.0}
        by_era_x_pass[k]["total"] += 1
        if r["pass"]:
            by_era_x_pass[k]["passed"] += 1
        else:
            by_era_x_pass[k]["failed"] += 1
        by_era_x_pass[k]["avg_score"] += r["overall_score"]
    for k, d in by_era_x_pass.items():
        t = d["total"]
        d["avg_score"] = round(d["avg_score"] / t, 3) if t else 0

    # ── WO-QB-EVAL-EXPAND-01: extractor method distribution ───────────────
    # method_distribution = full tally of observed method strings (superset
    # of the dense-diag 4-way classifier below). rules_fallback_rate is the
    # proportion of cases whose method classified as rules_fallback.
    # truncation_rate looks for truncation markers in the method tag —
    # today the extractor does not emit a "truncated" method tag, so this
    # is expected to read 0.0 until a future WO surfaces it. Kept in the
    # report shape so the eval harness is ready for that WO.
    method_distribution: Dict[str, int] = {}
    rules_fallback_count = 0
    parse_failure_count  = 0
    parse_success_count  = 0
    truncation_count     = 0
    for r in results:
        m = r.get("method") or "unknown"
        method_distribution[m] = method_distribution.get(m, 0) + 1
        cls = _classify_method(m)
        if cls == "rules_fallback":
            rules_fallback_count += 1
        elif cls == "parse_failure":
            parse_failure_count += 1
        elif cls == "parse_success":
            parse_success_count += 1
        if "truncat" in m.lower():
            truncation_count += 1
    rules_fallback_rate = round(rules_fallback_count / total, 3) if total else 0.0
    parse_failure_rate  = round(parse_failure_count  / total, 3) if total else 0.0
    truncation_rate     = round(truncation_count     / total, 3) if total else 0.0

    # ── WO-QB-EVAL-EXPAND-01: stubborn-pack partition summary ─────────────
    # Buckets case-results into the 4 SPANTAG partitions (primary /
    # secondary / truncation_starved / out_of_scope) so the master report
    # surfaces SPANTAG-relevant movement directly. Non-stubborn cases are
    # excluded — they're covered by the contract/style/case_type axes.
    stubborn_pack_summary: Dict[str, Dict[str, Any]] = {}
    for partition_name in STUBBORN_PACK_PARTITION:
        stubborn_pack_summary[partition_name] = {
            "total": 0, "passed": 0, "failed": 0, "avg_score": 0.0, "case_ids": []
        }
    for r in results:
        part = r.get("stubborn_partition")
        if not part:
            continue
        bucket = stubborn_pack_summary[part]
        bucket["total"] += 1
        if r["pass"]:
            bucket["passed"] += 1
        else:
            bucket["failed"] += 1
        bucket["avg_score"] += r["overall_score"]
        bucket["case_ids"].append(r["case_id"])
    for part, bucket in stubborn_pack_summary.items():
        t = bucket["total"]
        bucket["avg_score"] = round(bucket["avg_score"] / t, 3) if t else 0.0
        bucket["pass_rate"] = round(bucket["passed"] / t, 3) if t else 0.0
        bucket["case_ids"].sort()

    # ── WO-QB-EVAL-EXPAND-01: defensible_alt_credit rate + pairs ──────────
    # SECTION-EFFECT #94 scorer policy adds the "defensible_alt_credit"
    # failure tag when a must_extract path missed primary but an adjudicated
    # alt path caught the value. Track both the rate and the specific
    # (primary → winning_alt) pairs so the report can show WHICH alt paths
    # are doing the work. This is also the core of field_path_confusion_pairs:
    # any primary→alt pair that credits a defensible lane.
    #
    # WO-QB-ALT-VALUES-01 (#97) extends this to a value-axis credit track.
    defensible_alt_credit_count = 0
    defensible_value_alt_credit_count = 0
    alt_credit_pairs: Dict[str, int] = {}     # path-axis: "primary_fp -> alt_fp" -> count
    value_alt_credit_cases: List[Dict[str, Any]] = []  # value-axis: per-case matched alts
    field_path_mismatch_count = 0
    for r in results:
        fcs = r.get("failure_categories", [])
        if "defensible_alt_credit" in fcs:
            defensible_alt_credit_count += 1
        if "defensible_value_alt_credit" in fcs:
            defensible_value_alt_credit_count += 1
        if "field_path_mismatch" in fcs:
            field_path_mismatch_count += 1
        for fp, td in r.get("truth_zone_details", {}).items():
            via = td.get("winning_via")
            if via == "alt_defensible_path":
                primary = fp.split("[", 1)[0]
                alt = td.get("winning_path") or "?"
                key = f"{primary} -> {alt}"
                alt_credit_pairs[key] = alt_credit_pairs.get(key, 0) + 1
            elif via == "alt_defensible_value":
                value_alt_credit_cases.append({
                    "case_id": r["case_id"],
                    "fieldPath": fp.split("[", 1)[0],
                    "matched_alt_value": td.get("matched_alt_value"),
                    "score": td.get("winning_score"),
                })
    defensible_alt_credit_rate = (
        round(defensible_alt_credit_count / total, 3) if total else 0.0
    )
    defensible_value_alt_credit_rate = (
        round(defensible_value_alt_credit_count / total, 3) if total else 0.0
    )
    # Top-N pair list (sorted by frequency, descending)
    alt_credit_pair_list = [
        {"pair": k, "count": v}
        for k, v in sorted(alt_credit_pairs.items(), key=lambda x: -x[1])
    ]

    # ── WO-QB-EVAL-EXPAND-01: invalid-fieldpath hallucination signal ──────
    # "invalid" here = the extractor emitted to a path that either isn't in
    # the schema or doesn't match any expected/truth-zone path for that
    # case. Approximated via failure_categories 'schema_gap' ∪ 'field_path_mismatch'.
    # Per-case count surfaces which cases are the worst offenders.
    invalid_field_path_hallucinations: List[Dict[str, Any]] = []
    for r in results:
        fcs = r.get("failure_categories", [])
        if "schema_gap" in fcs or "field_path_mismatch" in fcs:
            # Count extracted items whose fieldPath isn't on any expected/tz path
            expected_paths = set((r.get("field_scores") or {}).keys())
            tz_paths = set(
                fp.split("[", 1)[0]
                for fp in (r.get("truth_zone_details") or {}).keys()
            )
            allowed = expected_paths | tz_paths
            raw = r.get("raw_items", [])
            offenders = [it["fieldPath"] for it in raw
                         if it.get("fieldPath") and it["fieldPath"] not in allowed]
            if offenders or not raw:  # include cases with schema_gap even if no raw_items (offline)
                invalid_field_path_hallucinations.append({
                    "case_id": r["case_id"],
                    "offender_count": len(offenders),
                    "offenders": offenders[:5],  # cap list for report size
                    "failure_categories": fcs,
                })
    invalid_field_path_hallucinations.sort(key=lambda x: -x["offender_count"])

    # ── WO-QB-EVAL-EXPAND-01: confidence distribution ─────────────────────
    # Aggregate across every extracted item in every case. Offline cases
    # contribute mockLlmOutput confidences; live cases contribute API
    # response confidences. When no confidences are present (mocks without
    # the field, or error paths) the distribution is zeros — not missing.
    all_confs: List[float] = []
    for r in results:
        cs = r.get("confidence_stats") or {}
        # Re-extract the raw confidences by scanning raw_items (live) or
        # reusing the per-case stats min/max/avg (offline without raw_items).
        raw = r.get("raw_items")
        if raw:
            for it in raw:
                c = it.get("confidence")
                if isinstance(c, (int, float)):
                    all_confs.append(float(c))
    confidence_distribution = {
        "item_count": len(all_confs),
        "min": round(min(all_confs), 3) if all_confs else None,
        "max": round(max(all_confs), 3) if all_confs else None,
        "avg": round(sum(all_confs) / len(all_confs), 3) if all_confs else None,
        "buckets": {
            "lt_0_5":     sum(1 for c in all_confs if c <  0.5),
            "0_5_to_0_7": sum(1 for c in all_confs if 0.5 <= c < 0.7),
            "0_7_to_0_9": sum(1 for c in all_confs if 0.7 <= c < 0.9),
            "ge_0_9":     sum(1 for c in all_confs if c >= 0.9),
        },
    }

    # ── Aggregate truth zone metrics ───────────────────────────────────────
    agg_tz = {
        "must_extract": {"total": 0, "hit": 0, "miss": 0},
        "may_extract": {"total": 0, "hit": 0, "miss": 0},
        "should_ignore": {"total": 0, "hit": 0, "leaked": 0},
        "must_not_write": {"total": 0, "hit": 0, "violated": 0},
    }
    for r in results:
        tz = r.get("truth_zone_scores", {})
        for zone in agg_tz:
            if zone in tz:
                for k in agg_tz[zone]:
                    agg_tz[zone][k] += tz[zone].get(k, 0)

    truth_zone_summary = {}
    me = agg_tz["must_extract"]
    truth_zone_summary["must_extract_recall"] = round(me["hit"] / me["total"], 3) if me["total"] else 0
    ma = agg_tz["may_extract"]
    truth_zone_summary["may_extract_bonus_rate"] = round(ma["hit"] / ma["total"], 3) if ma["total"] else 0
    si = agg_tz["should_ignore"]
    truth_zone_summary["should_ignore_leak_rate"] = round(si["leaked"] / si["total"], 3) if si["total"] else 0
    mnw = agg_tz["must_not_write"]
    truth_zone_summary["must_not_write_violation_rate"] = round(mnw["violated"] / mnw["total"], 3) if mnw["total"] else 0
    truth_zone_summary["raw_counts"] = agg_tz

    # ── must_not_write violations list ─────────────────────────────────────
    mnw_violations = []
    for r in results:
        for fp, td in r.get("truth_zone_details", {}).items():
            if td.get("violated"):
                mnw_violations.append({
                    "case_id": r["case_id"],
                    "fieldPath": fp,
                    "narratorId": r["narratorId"],
                })

    # ── Contract subset delta (first 62 cases = original regression set) ──
    contract_subset = [r for r in results if r.get("caseType") == "contract"]
    contract_passed = sum(1 for r in contract_subset if r["pass"])
    contract_total = len(contract_subset)

    # ── v2-compatible baseline (for comparison with old 32/62) ────────────
    v2_passed_all = sum(1 for r in results if r.get("v2_pass", False))
    v2_passed_contract = sum(1 for r in contract_subset if r.get("v2_pass", False))
    v2_avg_contract = round(
        sum(r.get("v2_score", 0) for r in contract_subset) / contract_total, 3
    ) if contract_total else 0

    report = {
        "_wo": "WO-QB-MASTER-EVAL-01",
        "_generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mode": mode,
        "summary": {
            "total_cases": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": round(passed / total, 3) if total else 0,
            "avg_overall_score": round(
                sum(r["overall_score"] for r in results) / total, 3
            ) if total else 0,
        },
        "contract_subset": {
            "total": contract_total,
            "passed_v3": contract_passed,
            "passed_v2": v2_passed_contract,
            "v2_avg_score": v2_avg_contract,
            "pass_rate_v3": round(contract_passed / contract_total, 3) if contract_total else 0,
            "pass_rate_v2": round(v2_passed_contract / contract_total, 3) if contract_total else 0,
            "note": "v2 = old scorer (field avg >= 0.7). v3 = truth zone recall. Prior baseline: 32/62 v2.",
        },
        "v2_baseline": {
            "total_v2_passed": v2_passed_all,
            "total_v2_rate": round(v2_passed_all / total, 3) if total else 0,
            "note": "v2-compat scoring for all 104 cases. Compare contract subset v2 against old 32/62.",
        },
        "by_behavior": by_behavior,
        "by_narrator": by_narrator,
        "by_case_type": by_case_type,
        "by_style_bucket": by_style,
        "by_chunk_size": by_chunk,
        "by_noise_profile": by_noise,
        "by_case_mode": by_case_mode,
        # WO-QB-EVAL-EXPAND-01 life-map axes (#93 plumbing surfaced here)
        "by_era":         by_era,
        "by_pass":        by_pass,
        "by_mode":        by_mode,
        "by_era_x_pass":  by_era_x_pass,
        # WO-QB-EVAL-EXPAND-01 diagnostic axes
        "method_distribution": method_distribution,
        "method_rates": {
            "parse_success_rate": round(parse_success_count / total, 3) if total else 0.0,
            "parse_failure_rate": parse_failure_rate,
            "rules_fallback_rate": rules_fallback_rate,
            "truncation_rate": truncation_rate,
        },
        "stubborn_pack_summary": stubborn_pack_summary,
        "defensible_alt_credit": {
            "rate": defensible_alt_credit_rate,
            "count": defensible_alt_credit_count,
            "field_path_mismatch_count": field_path_mismatch_count,
            "pairs_top": alt_credit_pair_list[:20],
        },
        # WO-QB-ALT-VALUES-01 (#97). Scoped to case_075 / case_088 first cut;
        # no global value-match loosening. rate applies across all results so
        # a stray value_alt credit anywhere in the suite surfaces honestly.
        "defensible_value_alt_credit": {
            "rate": defensible_value_alt_credit_rate,
            "count": defensible_value_alt_credit_count,
            "cases": value_alt_credit_cases[:20],
        },
        "invalid_field_path_hallucinations": invalid_field_path_hallucinations[:20],
        "confidence_distribution": confidence_distribution,
        "truth_zone_summary": truth_zone_summary,
        "must_not_write_violations": mnw_violations,
        "expected_extractor_results": {
            "should_pass": {
                "total": len(expected_pass),
                "actually_passed": sum(1 for r in expected_pass if r["pass"]),
            },
            "known_gaps": {
                "total": len(expected_fail),
                "actually_passed": sum(1 for r in expected_fail if r["pass"]),
            },
        },
        "failure_categories": all_failures,
        "case_results": results,
    }

    # WO-EX-DENSE-DIAG-01 Phase 2 — auto-emit dense_metrics block when
    # any diagnostic-tagged cases are in the batch. Zero-touch for master.
    dense_metrics = _compute_dense_metrics(results)
    if dense_metrics:
        report["dense_metrics"] = dense_metrics

    return report


def _print_breakdown(title: str, data: dict, width: int = 25):
    """Print a grouped breakdown section."""
    print(f"  {title}:")
    for key, d in data.items():
        print(f"    {key:{width}s}  {d['passed']}/{d['total']} passed  (avg {d['avg_score']:.3f})")
    print()


def print_summary(report: dict):
    """Print a human-readable summary table."""
    s = report["summary"]
    print()
    print("=" * 78)
    print(f"  WO-QB-MASTER-EVAL-01 — {report['mode'].upper()} MODE")
    print("=" * 78)
    print(f"  Total cases:     {s['total_cases']}")
    print(f"  Passed:          {s['passed']}")
    print(f"  Failed:          {s['failed']}")
    print(f"  Pass rate:       {s['pass_rate']:.1%}")
    print(f"  Avg score:       {s['avg_overall_score']:.3f}")
    print()

    # ── Contract subset delta ──────────────────────────────────────────────
    cs = report.get("contract_subset", {})
    if cs:
        print(f"  CONTRACT SUBSET (regression guard):")
        v3p = cs.get('passed_v3', cs.get('passed', 0))
        v2p = cs.get('passed_v2', '?')
        t = cs['total']
        print(f"    v3 (truth zones): {v3p}/{t} passed  ({v3p/t:.1%})" if t else "")
        print(f"    v2 (field avg):   {v2p}/{t} passed  ({v2p/t:.1%})" if isinstance(v2p, int) and t else "")
        print(f"    Prior baseline:   32/62 (v2)")
        print()

    # ── v2 baseline ───────────────────────────────────────────────────────
    v2b = report.get("v2_baseline", {})
    if v2b:
        print(f"  V2-COMPAT (all cases): {v2b['total_v2_passed']}/{s['total_cases']} passed ({v2b['total_v2_rate']:.1%})")
        print()

    # ── Layer 1: Contract score ────────────────────────────────────────────
    print("  ─── LAYER 1: CONTRACT / REGRESSION ───")
    print()

    # Truth zones
    tz = report.get("truth_zone_summary", {})
    if tz:
        print("  Truth zone metrics:")
        print(f"    must_extract recall:        {tz['must_extract_recall']:.1%}")
        print(f"    may_extract bonus rate:     {tz['may_extract_bonus_rate']:.1%}")
        print(f"    should_ignore leak rate:    {tz['should_ignore_leak_rate']:.1%}")
        print(f"    must_not_write violations:  {tz['must_not_write_violation_rate']:.1%}")
        print()

    # must_not_write violations list
    mnw_v = report.get("must_not_write_violations", [])
    if mnw_v:
        print("  must_not_write violations:")
        for v in mnw_v:
            print(f"    {v['case_id']:12s}  {v['fieldPath']:35s}  ({v['narratorId']})")
        print()

    # By behavior
    print("  By behavior:")
    for b, d in report["by_behavior"].items():
        print(f"    {b:30s}  {d['passed']}/{d['total']} passed")
    print()

    # By narrator
    _print_breakdown("By narrator", report["by_narrator"], width=30)

    # Expected vs unexpected
    exp = report["expected_extractor_results"]
    print("  Expected extractor results:")
    print(f"    Should pass (currentExtractorExpected=true):  "
          f"{exp['should_pass']['actually_passed']}/{exp['should_pass']['total']}")
    print(f"    Known gaps (currentExtractorExpected=false):  "
          f"{exp['known_gaps']['actually_passed']}/{exp['known_gaps']['total']}")
    print()

    # Failure categories
    if report["failure_categories"]:
        print("  Failure categories:")
        for cat, count in sorted(report["failure_categories"].items(), key=lambda x: -x[1]):
            print(f"    {cat:30s}  {count}")
        print()

    # ── Layer 2: Oral-history style ────────────────────────────────────────
    print("  ─── LAYER 2: ORAL-HISTORY STYLE ───")
    print()

    _print_breakdown("By case type", report.get("by_case_type", {}))
    _print_breakdown("By style bucket", report.get("by_style_bucket", {}))
    _print_breakdown("By chunk size", report.get("by_chunk_size", {}))
    _print_breakdown("By noise profile", report.get("by_noise_profile", {}))

    # ── Layer 3a: Life-map axes (WO-QB-EVAL-EXPAND-01) ─────────────────────
    if any(k in report for k in ("by_era", "by_pass", "by_mode")):
        print("  ─── LAYER 3a: LIFE-MAP AXES (era / pass / mode) ───")
        print()
        if report.get("by_era"):
            _print_breakdown("By era", report["by_era"], width=22)
        if report.get("by_pass"):
            _print_breakdown("By pass", report["by_pass"], width=22)
        if report.get("by_mode"):
            _print_breakdown("By mode", report["by_mode"], width=22)
        exp = report.get("by_era_x_pass", {})
        if exp:
            print("  By era × pass:")
            for key, d in sorted(exp.items()):
                print(f"    {key:40s}  {d['passed']}/{d['total']} passed  "
                      f"(avg {d['avg_score']:.3f})")
            print()

    # ── Layer 3b: Stubborn-pack partition (WO-EX-SPANTAG-01 §Partition) ────
    sps = report.get("stubborn_pack_summary", {})
    if sps and any(b["total"] > 0 for b in sps.values()):
        print("  ─── LAYER 3b: STUBBORN-PACK PARTITION ───")
        print()
        for part_name in ("primary", "secondary", "truncation_starved", "out_of_scope"):
            b = sps.get(part_name, {})
            if b.get("total", 0) == 0:
                continue
            print(f"    {part_name:22s}  {b['passed']}/{b['total']} passed  "
                  f"({b.get('pass_rate', 0):.1%}, avg {b['avg_score']:.3f})")
            if b.get("case_ids"):
                print(f"      cases: {', '.join(b['case_ids'])}")
        print()

    # ── Layer 3c: Diagnostic rates (WO-QB-EVAL-EXPAND-01) ──────────────────
    mr = report.get("method_rates", {})
    md = report.get("method_distribution", {})
    dac = report.get("defensible_alt_credit", {})
    cd = report.get("confidence_distribution", {})
    ifp = report.get("invalid_field_path_hallucinations", [])
    if mr or md or dac or cd or ifp:
        print("  ─── LAYER 3c: EXTRACTOR DIAGNOSTICS ───")
        print()
        if mr:
            print("  Method rates:")
            print(f"    parse_success_rate:     {mr.get('parse_success_rate', 0):.1%}")
            print(f"    parse_failure_rate:     {mr.get('parse_failure_rate', 0):.1%}")
            print(f"    rules_fallback_rate:    {mr.get('rules_fallback_rate', 0):.1%}")
            print(f"    truncation_rate:        {mr.get('truncation_rate', 0):.1%}")
            print()
        if md:
            print("  Method distribution:")
            for m, c in sorted(md.items(), key=lambda x: -x[1]):
                print(f"    {m:40s}  {c}")
            print()
        if dac:
            print("  Defensible-alt-credit scorer (SECTION-EFFECT #94):")
            print(f"    credited cases:               {dac.get('count', 0)}  "
                  f"({dac.get('rate', 0):.1%})")
            print(f"    still-mismatched cases:       {dac.get('field_path_mismatch_count', 0)}")
            pairs = dac.get("pairs_top") or []
            if pairs:
                print("    top primary → alt pairs:")
                for p in pairs[:10]:
                    print(f"      {p['pair']:60s}  {p['count']}")
            print()
        # WO-QB-ALT-VALUES-01 (#97) — scoped to case_075 / case_088 first cut.
        dvac = report.get("defensible_value_alt_credit", {})
        if dvac:
            print("  Defensible-value-alt-credit scorer (#97, 075/088-scoped):")
            print(f"    credited cases:               {dvac.get('count', 0)}  "
                  f"({dvac.get('rate', 0):.1%})")
            cases = dvac.get("cases") or []
            if cases:
                print("    per-case value-alt matches:")
                for e in cases[:10]:
                    mv = (e.get('matched_alt_value') or '')
                    if len(mv) > 50:
                        mv = mv[:50] + "…"
                    print(f"      {e['case_id']:12s}  {e['fieldPath']:30s}  "
                          f"score={e.get('score', 0):.3f}  alt=\"{mv}\"")
            print()
        if cd:
            print("  Confidence distribution:")
            print(f"    item_count:      {cd.get('item_count', 0)}")
            if cd.get("item_count"):
                print(f"    min/avg/max:     {cd.get('min'):.3f} / "
                      f"{cd.get('avg'):.3f} / {cd.get('max'):.3f}")
                buckets = cd.get("buckets", {})
                print(f"    <0.5:            {buckets.get('lt_0_5', 0)}")
                print(f"    0.5-0.7:         {buckets.get('0_5_to_0_7', 0)}")
                print(f"    0.7-0.9:         {buckets.get('0_7_to_0_9', 0)}")
                print(f"    >=0.9:           {buckets.get('ge_0_9', 0)}")
            print()
        if ifp:
            print("  Invalid-fieldpath hallucinations (top 10):")
            for e in ifp[:10]:
                print(f"    {e['case_id']:12s}  offenders={e['offender_count']:2d}  "
                      f"categories={e['failure_categories']}")
                if e.get("offenders"):
                    print(f"      emitted: {', '.join(e['offenders'])}")
            print()

    # ── Layer 3: Dense-truth diagnostic metrics (WO-EX-DENSE-DIAG-01) ──────
    dm = report.get("dense_metrics")
    if dm:
        print("  ─── LAYER 3: DENSE-TRUTH DIAGNOSTIC METRICS ───")
        print()
        print(f"  Diagnostic cases evaluated: {dm['total_diag_cases']}")
        print()
        print("  Extractor method distribution:")
        print(f"    parse_success:                 {dm['parse_success_count']}")
        print(f"    parse_failure:                 {dm['parse_failure_count']}")
        print(f"    rules_fallback:                {dm['rules_fallback_count']}")
        print(f"    other/unknown:                 {dm['method_other_count']}")
        print()
        print("  Diagnostic signal counts:")
        print(f"    invalid_fieldpath_rejection:   {dm['invalid_fieldpath_rejection_count']}")
        print(f"    single_cardinality_conflict:   {dm['single_cardinality_conflict_count']}")
        print(f"    duplicate_narrator_identity:   {dm['duplicate_narrator_identity_count']}")
        print(f"    v2_vs_v3_divergence:           {dm['v2_vs_v3_divergence_count']}  "
              f"(v2✓/v3✗: {dm['v2_pass_v3_fail']}, v3✓/v2✗: {dm['v3_pass_v2_fail']})")
        print()
        pg = dm.get("per_generation_hits", {})
        if pg:
            print("  Per-generation must_extract recall:")
            for bucket, stats in sorted(pg.items(), key=lambda x: -x[1]["total"]):
                print(f"    {bucket:22s}  {stats['hit']:2d}/{stats['total']:2d}  "
                      f"(recall {stats['recall']:.1%})")
            print()
        bf = dm.get("by_diag_family", {})
        if bf:
            print("  By diagnostic family:")
            for fam in sorted(bf.keys()):
                st = bf[fam]
                print(f"    Family {fam}: {st['passed']}/{st['total']} passed  "
                      f"({st['pass_rate']:.1%}, avg {st['avg_score']:.3f})")
                for sub, ss in st["subclasses"].items():
                    print(f"      {sub:50s}  {ss['passed']}/{ss['total']}  "
                          f"avg {ss['avg_score']:.3f}")
            print()
        fcd = dm.get("failure_class_dominance", [])
        if fcd:
            print("  Failure-class dominance (worst first):")
            for entry in fcd:
                print(f"    Family {entry['family']}: "
                      f"{entry['passed']}/{entry['total']}  "
                      f"({entry['pass_rate']:.1%})")
            print()

    # ── Failed cases ───────────────────────────────────────────────────────
    failed = [r for r in report["case_results"] if not r["pass"]]
    if failed:
        print("  ─── FAILED CASES ───")
        print()
        for r in failed:
            marker = " [GAP]" if not r["currentExtractorExpected"] else ""
            ct = r.get("caseType", "")
            cs = r.get("chunk_size", "")
            np = r.get("noise_profile", "")
            print(f"    {r['case_id']:10s}  {ct:15s}  {cs:6s}  {np:12s}  "
                  f"score={r['overall_score']:.2f}  {r['narratorId']}{marker}")
            if r["forbidden_violations"]:
                print(f"      Forbidden: {r['forbidden_violations']}")
            if r["failure_categories"]:
                print(f"      Failures:  {r['failure_categories']}")
        print()

    print("=" * 78)


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="WO-QB-EXTRACT-EVAL-01 extraction evaluation runner"
    )
    parser.add_argument(
        "--mode", choices=["offline", "live"], default="offline",
        help="offline = use mockLlmOutput, live = POST to API"
    )
    parser.add_argument(
        "--api", default="http://localhost:8000",
        help="API base URL for live mode (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--output", default=None,
        help="Output report path (default: docs/reports/question_bank_extraction_eval_report.json)"
    )
    parser.add_argument(
        "--cases", default=None,
        help="Path to cases JSON (default: data/qa/question_bank_extraction_cases.json)"
    )
    parser.add_argument(
        "--case-ids", default=None,
        help="Comma-separated case IDs to run (e.g. case_014,case_096)"
    )
    parser.add_argument(
        "--narrator", default=None,
        help="Run only cases for this narrator (e.g. kent-james-horne)"
    )
    parser.add_argument(
        "--case-type", default=None,
        help="Run only cases of this type (contract, mixed_narrative, dense_truth, follow_up, null_clarify)"
    )
    parser.add_argument(
        "--failed-only", default=None, metavar="REPORT_PATH",
        help="Re-run only cases that failed in a prior report JSON"
    )
    parser.add_argument(
        "--max-cases", type=int, default=None,
        help="Cap the number of cases to run (for quick debug loops)"
    )
    # WO-EX-DISCIPLINE-01 (#142): optional cold-stack fail-fast when invoked
    # from a combined restart+eval block. Default off — normal eval runs
    # proceed regardless of warmup classification.
    parser.add_argument(
        "--fail-on-cold", action="store_true",
        help=("Exit 2 if the discipline warmup probe classifies the stack "
              "as 'cold' or 'unreachable'. Use only from a combined "
              "restart+eval block; default is to proceed and record."),
    )
    args = parser.parse_args()

    # Load cases
    cases_path = Path(args.cases) if args.cases else CASES_PATH
    if not cases_path.exists():
        print(f"ERROR: Cases file not found: {cases_path}")
        sys.exit(1)

    with open(cases_path) as f:
        data = json.load(f)
    cases = data.get("cases", [])

    # ── Apply filters ─────────────────────────────────────────────────────
    if args.case_ids:
        ids = set(args.case_ids.split(","))
        cases = [c for c in cases if c["id"] in ids]

    if args.narrator:
        cases = [c for c in cases if c["narratorId"] == args.narrator]

    if args.case_type:
        cases = [c for c in cases if c.get("caseType") == args.case_type]

    if args.failed_only:
        prior_path = Path(args.failed_only)
        if not prior_path.exists():
            print(f"ERROR: Prior report not found: {prior_path}")
            sys.exit(1)
        with open(prior_path) as f:
            prior = json.load(f)
        failed_ids = set(
            r["case_id"] for r in prior.get("case_results", []) if not r["pass"]
        )
        cases = [c for c in cases if c["id"] in failed_ids]
        print(f"Filtered to {len(failed_ids)} failed cases from prior report")

    if args.max_cases and len(cases) > args.max_cases:
        cases = cases[:args.max_cases]

    print(f"Running {len(cases)} evaluation cases from {cases_path.name}")

    # WO-EX-DISCIPLINE-01 (#142): build the discipline header BEFORE the eval
    # loop runs so the warmup probe and api.log freshness reflect the pre-run
    # stack state. Output-path is resolved here (not later) so eval_tag is
    # captured in the header. The rendered text is printed to stdout now and
    # also prepended to the .console.txt later via the tee buffer.
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = Path(args.output) if args.output else (
        REPORT_DIR / "question_bank_extraction_eval_report.json"
    )
    try:
        _discipline_header, _discipline_text = _capture_discipline_header(
            api_base=args.api,
            mode=args.mode,
            cases_path=cases_path,
            output_path=output_path,
        )
        print(_discipline_text, end="")
        print()
    except Exception as _dh_err:
        # Header capture should never break the eval. Record the failure
        # and proceed with a stub so downstream code can still reference
        # run_metadata.
        print(f"WARNING: discipline header capture failed: {_dh_err}",
              file=sys.stderr)
        _discipline_header = {
            "eval_tag": None,
            "capture_error": f"{type(_dh_err).__name__}: {_dh_err}",
        }
        _discipline_text = (
            f"[discipline] capture_error: {type(_dh_err).__name__}\n"
        )

    # --fail-on-cold gate: applies only to the combined restart+eval case.
    _wp = _discipline_header.get("warmup_probe") or {}
    _wp_class = _wp.get("classification")
    if args.fail_on_cold and _wp_class in ("cold", "unreachable"):
        print(
            f"ERROR: --fail-on-cold set and warmup_probe classification="
            f"{_wp_class!r}; aborting before eval loop.",
            file=sys.stderr,
        )
        sys.exit(2)

    # Run
    if args.mode == "offline":
        results = run_offline(cases)
    else:
        results = run_live(cases, args.api)

    # Generate report
    report = generate_report(results, args.mode)
    # Attach the discipline header as a top-level run_metadata key. Additive;
    # scoring code never reads this.
    report["run_metadata"] = _discipline_header

    # Print summary FIRST — stdout survives even if file write crashes.
    # Also tee into an in-memory buffer so we can write a .console.txt
    # companion file that doesn't depend on shell `2>&1 | tee` (which has
    # silently failed under WSL pipe-buffering conditions — r4h's 0-byte
    # console was the trigger for adding this).
    _console_buffer = io.StringIO()
    # WO-EX-DISCIPLINE-01 (#142): discipline header leads the .console.txt.
    # Written directly into the buffer (not through _Tee) because it was
    # already emitted to stdout before the eval loop ran.
    _console_buffer.write(_discipline_text)
    _console_buffer.write("\n")
    class _Tee(io.TextIOBase):
        def __init__(self, *streams): self._streams = streams
        def write(self, s):
            for st in self._streams:
                try: st.write(s)
                except Exception: pass
            return len(s)
        def flush(self):
            for st in self._streams:
                try: st.flush()
                except Exception: pass
    _tee = _Tee(sys.stdout, _console_buffer)
    with contextlib.redirect_stdout(_tee):
        print_summary(report)

    # Write report — atomic temp-file-then-rename to prevent truncation.
    # output_path and REPORT_DIR were resolved earlier (pre-eval) for
    # discipline-header eval_tag derivation; reuse that resolved path here.
    try:
        report_json = json.dumps(report, indent=2, ensure_ascii=False, default=str)
        fd, tmp_path = tempfile.mkstemp(
            suffix=".json.tmp", dir=str(output_path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(report_json)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, str(output_path))
            print(f"Report written to {output_path} ({len(report_json):,} bytes)")
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as e:
        print(f"WARNING: Failed to write report to {output_path}: {e}",
              file=sys.stderr)
        print("  (Console summary above is still valid.)", file=sys.stderr)

    # Write console companion (<output>.console.txt). This guarantees the
    # human-readable summary survives even if `| tee` is dropped or stdout
    # pipe-buffers silently. Always-on, no flag needed.
    try:
        console_path = output_path.with_suffix("")  # strip .json
        console_path = console_path.with_suffix(".console.txt")
        # If --output didn't end with .json, just append .console.txt
        if console_path == output_path:
            console_path = Path(str(output_path) + ".console.txt")
        console_path.write_text(
            _console_buffer.getvalue(), encoding="utf-8"
        )
        print(f"Console summary written to {console_path}", file=sys.stderr)
    except Exception as e:
        print(f"WARNING: Failed to write console summary: {e}",
              file=sys.stderr)

    # WO-EX-FAILURE-PACK-01 (#141): failure-cluster sidecar. Grouped by
    # failure_category × narrator × phase × score-bucket, plus hallucination
    # prefix rollup and must_not_write breakout. Derived from the same report
    # dict — zero impact on the master JSON. Failures here must not abort the
    # run; the master eval remains the source of truth.
    try:
        # Derive eval_tag from --output filename when it matches the
        # standard pattern master_loop01_<tag>.json — cheap heuristic.
        eval_tag = None
        stem = output_path.stem
        if stem.startswith("master_loop01_"):
            eval_tag = stem[len("master_loop01_"):]

        pack = build_failure_pack(report, eval_tag=eval_tag)
        pack_json = json.dumps(pack, indent=2, ensure_ascii=False, default=str)
        # Sidecars live next to the master JSON with compound suffixes.
        # Compound suffixes don't round-trip through Path.with_suffix (it only
        # replaces the final `.x`), so build from stem.
        base_stem = output_path.stem if output_path.suffix == ".json" else output_path.name
        pack_json_path = output_path.parent / f"{base_stem}.failure_pack.json"
        pack_json_path.write_text(pack_json, encoding="utf-8")

        pack_console = render_failure_pack_console(pack)
        pack_console_path = output_path.parent / f"{base_stem}.failure_pack.console.txt"
        pack_console_path.write_text(pack_console, encoding="utf-8")
        print(f"Failure pack written to {pack_json_path}", file=sys.stderr)
        print(f"Failure pack console written to {pack_console_path}",
              file=sys.stderr)
    except Exception as e:
        print(f"WARNING: Failed to write failure pack: {e}",
              file=sys.stderr)

    # Exit code: 0 if all expected-to-pass cases pass, 1 otherwise
    exp = report["expected_extractor_results"]["should_pass"]
    if exp["actually_passed"] < exp["total"]:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
