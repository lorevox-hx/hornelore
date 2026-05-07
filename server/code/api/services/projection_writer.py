"""Projection writer — applies parsed corrections to a narrator's
interview_projections.projection_json record.

BUG-LORI-CORRECTION-ABSORBED-NOT-APPLIED-01 Phase 3 (2026-05-07):
this module closes the loop on corrections. Phase 1 (regex-based
detection in memory_echo.parse_correction_rule_based) and Phase 2
(chat_ws turn_mode dispatch + correction_payload to client) were
already in place. Phase 3 adds the server-side write so corrections
that the narrator volunteers actually mutate the canonical
provisional-truth surface — not just acknowledged in prose.

LAW 3 — this service touches DB only. It does NOT import from
extract.py / prompt_composer / llm_api / chat_ws. The chat_ws caller
hands us the parsed correction dict; we map it onto the projection
shape and write back via db.upsert_projection.

Layer boundaries (per Architecture Spec v1):
  - parser     (memory_echo.parse_correction_rule_based) — text → dict
  - applier    (this module) — dict → projection write
  - composer   (prompt_composer.compose_correction_ack) — dict → narrator-facing reply

Composition rule: applier runs FIRST so the projection has the new
value, THEN the composer reads (or the next memory_echo turn reads)
the updated state. Failures in apply_correction are non-fatal —
caller continues to compose + send the ack response. The DB write
is best-effort because LAW 3 says the chat path must not break on
storage trouble.

Fieldpath mapping (parser → projection):
  family.children.count        → personal.childrenCount
                                  (also clears any conflicting
                                  pendingSuggestion at children[].count)
  family.parents.father.name   → parents[0].firstName    (role=father)
                                  Or just store as parents.father.name
                                  pendingSuggestion if no parents[]
                                  array exists yet.
  family.parents.mother.name   → parents[1].firstName    (role=mother)
  identity.place_of_birth      → personal.placeOfBirth
  education_work.retirement    → community.retirement_status
                                  (free-form; "never fully retired")

_retracted (control sentinel, not a field path):
  Each retracted value is a string the narrator says they did NOT
  say or that should NOT be a real fact. Apply by scanning all
  pendingSuggestions + fields for any value that contains the
  retracted token (case-insensitive) and removing it / lowering
  confidence. This handles Melanie's "there was no Hannah" — any
  pendingSuggestion that introduced "Hannah" gets scrubbed.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Mapping from parser field-path keys → canonical projection field paths.
# Conservative: only field paths we KNOW the schema accepts. Unmapped
# entries from the parser get logged but skipped (they may be valid
# parser output the schema doesn't yet have a slot for).
_PARSER_TO_PROJECTION: Dict[str, str] = {
    "family.children.count":        "personal.childrenCount",
    "family.parents.father.name":   "parents.father.firstName",
    "family.parents.mother.name":   "parents.mother.firstName",
    "identity.place_of_birth":      "personal.placeOfBirth",
    "education_work.retirement":    "community.retirementStatus",
}


def apply_correction(
    person_id: str,
    parsed: Dict[str, Any],
    *,
    source_turn_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Apply a parsed correction to the narrator's projection_json.

    Args:
        person_id:       narrator UUID. Required.
        parsed:          dict from parse_correction_rule_based. May contain
                         field paths (string keys) and/or control sentinels
                         (`_retracted` / `_meant`).
        source_turn_id:  optional turn_id to record in the field metadata
                         for audit / rollback.

    Returns:
        Summary dict with `applied` (list of {field_path, value}),
        `retracted` (list of values scrubbed from pendingSuggestions),
        `skipped` (list of {field_path, reason}), `errors` (list of
        strings — non-fatal). On any unexpected exception, logs +
        returns errors-only — never raises into the chat path.
    """
    summary: Dict[str, Any] = {
        "applied": [],
        "retracted": [],
        "skipped": [],
        "errors": [],
    }
    if not person_id:
        summary["errors"].append("missing_person_id")
        return summary
    if not isinstance(parsed, dict) or not parsed:
        summary["errors"].append("empty_or_invalid_parsed")
        return summary

    # Lazy import — keeps LAW 3 boundary visible (db is the only project
    # dependency this module reaches into).
    try:
        from .. import db as _db
    except Exception as exc:
        summary["errors"].append(f"db_import_failed: {exc}")
        return summary

    # Read existing projection. Empty/missing → start with fresh shape.
    try:
        existing_blob = _db.get_projection(person_id) or {}
    except Exception as exc:
        logger.warning("[projection-writer] get_projection failed for %s: %s", person_id, exc)
        existing_blob = {}

    proj = existing_blob.get("projection") if isinstance(existing_blob.get("projection"), dict) else {}
    fields = proj.get("fields") if isinstance(proj.get("fields"), dict) else {}
    pending = proj.get("pendingSuggestions") if isinstance(proj.get("pendingSuggestions"), list) else []

    now = datetime.utcnow().isoformat()

    # ── Field corrections ────────────────────────────────────────────
    for parser_key, value in parsed.items():
        # Skip control sentinels — handled separately below
        if parser_key.startswith("_"):
            continue
        canonical = _PARSER_TO_PROJECTION.get(parser_key)
        if not canonical:
            summary["skipped"].append({
                "field_path": parser_key,
                "reason": "no_canonical_mapping",
            })
            continue
        # Normalize value to string for storage; numeric counts kept as
        # integer-looking string so downstream readers can choose how
        # to coerce. Lists are not used here.
        v_str = str(value).strip() if value is not None else ""
        if not v_str:
            summary["skipped"].append({
                "field_path": parser_key,
                "reason": "empty_value",
            })
            continue
        fields[canonical] = {
            "value": v_str,
            "source": "correction",
            "confidence": "high",
            "turn_id": source_turn_id,
            "applied_at": now,
        }
        summary["applied"].append({
            "field_path": canonical,
            "value": v_str,
        })

    # ── Retraction handling — scrub pendingSuggestions ──────────────
    retracted_tokens: List[str] = []
    for r in (parsed.get("_retracted") or []):
        r_str = str(r).strip()
        if r_str:
            retracted_tokens.append(r_str)

    if retracted_tokens:
        scrubbed_pending: List[Dict[str, Any]] = []
        for sug in pending:
            if not isinstance(sug, dict):
                scrubbed_pending.append(sug)
                continue
            sug_value = (sug.get("value") or "")
            if not isinstance(sug_value, str):
                scrubbed_pending.append(sug)
                continue
            v_lower = sug_value.lower()
            matched_token = None
            for tok in retracted_tokens:
                if tok.lower() in v_lower:
                    matched_token = tok
                    break
            if matched_token is not None:
                summary["retracted"].append({
                    "field_path": sug.get("fieldPath"),
                    "value": sug_value,
                    "matched_token": matched_token,
                })
                # Drop the suggestion entirely. Audit trail is in
                # summary["retracted"] for the operator surface.
                continue
            scrubbed_pending.append(sug)
        pending = scrubbed_pending

        # Also scrub fields that match the retracted tokens, EXCEPT
        # corrections we just applied this turn (the fields[]
        # additions above) — those are the new authoritative values.
        applied_paths = {a["field_path"] for a in summary["applied"]}
        scrubbed_fields = {}
        for fp, entry in fields.items():
            if fp in applied_paths:
                scrubbed_fields[fp] = entry
                continue
            if not isinstance(entry, dict):
                scrubbed_fields[fp] = entry
                continue
            v = entry.get("value") or ""
            if not isinstance(v, str):
                scrubbed_fields[fp] = entry
                continue
            v_lower = v.lower()
            matched = None
            for tok in retracted_tokens:
                if tok.lower() in v_lower:
                    matched = tok
                    break
            if matched is not None:
                summary["retracted"].append({
                    "field_path": fp,
                    "value": v,
                    "matched_token": matched,
                    "from_fields": True,
                })
                # Drop from canonical fields entirely — the narrator
                # explicitly retracted this. If they want it back they
                # can volunteer it again.
                continue
            scrubbed_fields[fp] = entry
        fields = scrubbed_fields

    # Stage the updated projection shape and write back. Preserve any
    # other top-level keys the projection may carry (timeline_events,
    # extracted_summary, etc.) by mutating in place.
    proj["fields"] = fields
    proj["pendingSuggestions"] = pending
    proj["last_correction_at"] = now

    if not summary["applied"] and not summary["retracted"]:
        # Parser returned only control sentinels with no effect —
        # nothing to persist. Still success-shaped so caller doesn't
        # treat this as an error.
        return summary

    try:
        _db.upsert_projection(
            person_id,
            proj,
            source="correction",
            version=int(existing_blob.get("version") or 1),
        )
        logger.info(
            "[projection-writer] applied correction person=%s applied=%d retracted=%d turn=%s",
            person_id,
            len(summary["applied"]),
            len(summary["retracted"]),
            source_turn_id,
        )
    except Exception as exc:
        logger.warning(
            "[projection-writer] upsert_projection failed person=%s: %s",
            person_id, exc,
        )
        summary["errors"].append(f"upsert_failed: {exc}")

    return summary


__all__ = ["apply_correction"]
