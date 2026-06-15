"""WO-LORI-BIO-BUILDER-UNIVERSAL-01 (2026-06-14) — Phase F gap map service.

═══════════════════════════════════════════════════════════════════════
  WHAT THIS IS
═══════════════════════════════════════════════════════════════════════

The operator's situational-awareness surface for what the memoir is
missing. Per WO §Bio gap map, for each narrator the gap map shows:

  - Bio completeness percentage by category
  - Recently-asked section (last anchored asks + outcomes)
  - Suggested-asks section (high-value empty fields without current
    chapter anchor — operator can manually ask via direct entry or
    note for next session)
  - Conflicts pending section
  - Creep telemetry rolled up across the narrator's anchored-ask
    history (Defense 1 surface — amber/red banners)

This service is the pure-aggregation layer consumed by both the
Phase F gap map dashboard (operator_bio_gap_map router) AND the
Phase E bio editor's "what's missing" sidebar (operator_bio_editor
router).

LAW 3 INFRASTRUCTURE BOUNDARY:
This module imports stdlib + ..db + .bio_schema +
.bio_anchored_asker only. It does NOT import from extract.py,
chat_ws.py, prompt_composer. No DB writes — read-only aggregation.

═══════════════════════════════════════════════════════════════════════
  PUBLIC API
═══════════════════════════════════════════════════════════════════════

  compute_completeness(narrator_id) → CompletenessRollup
      Per-category fill rate + overall percentage.

  recently_asked(narrator_id, limit=10) → List[RecentAsk]
      The last N anchored asks for this narrator, newest first.
      Each carries the field_label + matched_anchor + outcome
      classification (resolved / pending / declined-by-silence).

  suggested_asks(narrator_id) → List[SuggestedAsk]
      High-value empty fields without a current chapter anchor.
      Operator can manually ask offline OR note for the next
      session OR mark as known-unanswerable. Sorted by category
      then field_key for deterministic display.

  list_conflicts(narrator_id) → List[ConflictPair]
      Pairs of conflicted bio_facts rows with their source info.
      Operator picks which to promote via the editor.

  creep_telemetry_rollup(narrator_id, window=5) → Dict[str, Any]
      Wraps bio_anchored_asker.compute_creep_telemetry + warning
      classification into a shape the dashboard can render
      directly. Includes the literal threshold values so the UI
      can show "delta avg X (amber at -0.25)".
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .. import db
from . import bio_schema
from . import bio_anchored_asker


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Status taxonomy — "filled" for completeness purposes
# ─────────────────────────────────────────────────────────────────────


# Statuses that count as "filled" in the completeness rollup. The
# anchored_asked_pending placeholder DOES NOT count as filled (it's a
# scaffolding row, not an answer). conflicted also DOES NOT count —
# operator review is pending, treat as gap.
_FILLED_STATUSES = frozenset({
    "extracted_needs_verify",
    "document_sourced",
    "anchored_asked",
    "operator_entered",
    "approved",
})


# Statuses that surface in the "conflicts pending" section.
_CONFLICT_STATUSES = frozenset({"conflicted"})


# ─────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CategoryCompleteness:
    category: str
    total_fields: int
    filled_fields: int

    @property
    def percentage(self) -> float:
        if self.total_fields == 0:
            return 0.0
        return round(100.0 * self.filled_fields / self.total_fields, 1)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "total_fields": self.total_fields,
            "filled_fields": self.filled_fields,
            "percentage": self.percentage,
        }


@dataclass(frozen=True)
class CompletenessRollup:
    narrator_id: str
    overall_percentage: float
    total_fields: int
    filled_fields: int
    by_category: Tuple[CategoryCompleteness, ...] = field(
        default_factory=tuple,
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "narrator_id": self.narrator_id,
            "overall_percentage": self.overall_percentage,
            "total_fields": self.total_fields,
            "filled_fields": self.filled_fields,
            "by_category": [c.to_dict() for c in self.by_category],
        }


@dataclass(frozen=True)
class RecentAsk:
    fact_id: str
    field_key: str
    field_label: str
    matched_anchor: str
    status: str
    outcome: str   # "resolved" | "pending" | "no_answer"
    asked_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "field_key": self.field_key,
            "field_label": self.field_label,
            "matched_anchor": self.matched_anchor,
            "status": self.status,
            "outcome": self.outcome,
            "asked_at": self.asked_at,
        }


@dataclass(frozen=True)
class SuggestedAsk:
    field_key: str
    field_label: str
    field_category: str
    asking_anchors: Tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_key": self.field_key,
            "field_label": self.field_label,
            "field_category": self.field_category,
            "asking_anchors": list(self.asking_anchors),
        }


@dataclass(frozen=True)
class ConflictPair:
    field_key: str
    field_label: str
    rows: Tuple[Dict[str, Any], ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        # Strip the raw DB rows to a render-friendly shape.
        return {
            "field_key": self.field_key,
            "field_label": self.field_label,
            "rows": [
                {
                    "fact_id": r.get("id"),
                    "value": r.get("value"),
                    "status": r.get("status"),
                    "source": r.get("source"),
                    "confidence": r.get("confidence"),
                    "last_updated": r.get("last_updated"),
                }
                for r in self.rows
            ],
        }


# ─────────────────────────────────────────────────────────────────────
# Completeness rollup
# ─────────────────────────────────────────────────────────────────────


def compute_completeness(narrator_id: str) -> CompletenessRollup:
    """Per-category fill rate + overall percentage for a narrator.

    A field counts as "filled" when at least one bio_facts row exists
    with a status in _FILLED_STATUSES. Multiple rows for the same
    (narrator, field) count once.
    """
    if not narrator_id:
        return CompletenessRollup(
            narrator_id="", overall_percentage=0.0,
            total_fields=0, filled_fields=0,
        )
    try:
        existing_rows = db.bio_fact_list_by_narrator(narrator_id)
    except Exception:
        existing_rows = []
    # Map field_key → set of statuses seen
    seen: Dict[str, set] = {}
    for r in existing_rows:
        fk = str(r.get("field_key") or "")
        seen.setdefault(fk, set()).add(str(r.get("status") or ""))

    # Aggregate per-category
    category_totals: Dict[str, Tuple[int, int]] = {}
    overall_total = 0
    overall_filled = 0
    for cat in bio_schema.FIELD_CATEGORIES:
        cat_fields = bio_schema.get_fields_by_category(cat)
        total = len(cat_fields)
        filled = 0
        for fd in cat_fields:
            statuses = seen.get(fd.field_key, set())
            if statuses & _FILLED_STATUSES:
                filled += 1
        category_totals[cat] = (total, filled)
        overall_total += total
        overall_filled += filled

    by_category = tuple(
        CategoryCompleteness(
            category=cat,
            total_fields=category_totals[cat][0],
            filled_fields=category_totals[cat][1],
        )
        for cat in bio_schema.FIELD_CATEGORIES
    )
    overall_pct = (
        round(100.0 * overall_filled / overall_total, 1)
        if overall_total else 0.0
    )
    return CompletenessRollup(
        narrator_id=narrator_id,
        overall_percentage=overall_pct,
        total_fields=overall_total,
        filled_fields=overall_filled,
        by_category=by_category,
    )


# ─────────────────────────────────────────────────────────────────────
# Recently asked
# ─────────────────────────────────────────────────────────────────────


def _classify_outcome(row: Dict[str, Any]) -> str:
    """Classify the post-ask outcome from the bio_facts row's status
    + chapter_continuation_metric.

      resolved  — narrator answered + extraction succeeded
                  (status='anchored_asked')
      pending   — ask still awaiting response
                  (status='anchored_asked_pending')
      no_answer — ask fired + narrator didn't engage (placeholder
                  row stayed pending; deferred classification)
    """
    s = str(row.get("status") or "")
    if s == "anchored_asked":
        return "resolved"
    if s == "anchored_asked_pending":
        return "pending"
    return "no_answer"


def recently_asked(
    narrator_id: str, limit: int = 10,
) -> List[RecentAsk]:
    """The last N anchored asks for this narrator, newest first.

    Only rows whose source.tier == 3 are anchored-asker writes;
    legacy-source rows are excluded so this surface stays focused on
    Tier 3 activity.
    """
    if not narrator_id:
        return []
    try:
        rows = db.bio_fact_list_by_narrator(narrator_id)
    except Exception:
        return []
    tier_3_rows: List[Dict[str, Any]] = []
    for r in rows:
        try:
            src = json.loads(r.get("source") or "{}")
        except (ValueError, TypeError):
            continue
        if int(src.get("tier") or 0) != 3:
            continue
        tier_3_rows.append((src, r))
    # Sort newest first by last_updated DESC (db CRUD already
    # orders by field_key + last_updated; do a tighter sort here).
    tier_3_rows.sort(
        key=lambda pair: pair[1].get("last_updated") or "",
        reverse=True,
    )
    out: List[RecentAsk] = []
    for src, r in tier_3_rows[: max(1, int(limit or 10))]:
        field_key = str(r.get("field_key") or "")
        fd = bio_schema.get_field_by_key(field_key)
        field_label = fd.field_label if fd else field_key
        matched_anchor = str(src.get("matched_anchor") or "")
        out.append(RecentAsk(
            fact_id=str(r.get("id") or ""),
            field_key=field_key,
            field_label=field_label,
            matched_anchor=matched_anchor,
            status=str(r.get("status") or ""),
            outcome=_classify_outcome(r),
            asked_at=str(r.get("created_at") or ""),
        ))
    return out


# ─────────────────────────────────────────────────────────────────────
# Suggested asks
# ─────────────────────────────────────────────────────────────────────


def suggested_asks(narrator_id: str) -> List[SuggestedAsk]:
    """High-value empty fields without a current chapter anchor.

    Per WO §Bio gap map "Suggested asks" — these are the fields the
    operator could manually ask about offline OR note for the next
    session OR mark as known-unanswerable. Filter is narrative_value=
    high + non-empty asking_anchors (Tier 3 candidates) that are
    currently gaps for this narrator.

    Sorted by category (in BIO_SCHEMA_SEED category order) then by
    field_key alphabetically — deterministic for the operator UI.
    """
    if not narrator_id:
        return []
    high_value = bio_schema.get_high_value_fields()
    try:
        existing = db.bio_fact_list_by_narrator(narrator_id)
    except Exception:
        existing = []
    filled_keys: set = set()
    for r in existing:
        s = str(r.get("status") or "")
        if s in _FILLED_STATUSES or s == "anchored_asked_pending":
            # anchored_asked_pending counts as "already attempted"
            # for the suggested-asks surface — operator already
            # surfaced this gap; don't suggest it again.
            filled_keys.add(str(r.get("field_key") or ""))
    suggested: List[SuggestedAsk] = []
    for fd in high_value:
        if fd.field_key in filled_keys:
            continue
        suggested.append(SuggestedAsk(
            field_key=fd.field_key,
            field_label=fd.field_label,
            field_category=fd.field_category,
            asking_anchors=fd.asking_anchors,
        ))
    # Stable sort by category (FIELD_CATEGORIES order) then field_key
    cat_order = {cat: i for i, cat in enumerate(bio_schema.FIELD_CATEGORIES)}
    suggested.sort(
        key=lambda s: (cat_order.get(s.field_category, 999), s.field_key),
    )
    return suggested


# ─────────────────────────────────────────────────────────────────────
# Conflicts pending
# ─────────────────────────────────────────────────────────────────────


def list_conflicts(narrator_id: str) -> List[ConflictPair]:
    """Group conflicted bio_facts rows by field_key so the operator
    review surface can present each pair together.

    Multiple rows may share a conflict cluster (3-way conflicts are
    possible). All rows for a single field_key with status='conflicted'
    travel together.
    """
    if not narrator_id:
        return []
    try:
        rows = db.bio_fact_list_by_narrator(
            narrator_id, status="conflicted",
        )
    except Exception:
        rows = []
    by_field: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        fk = str(r.get("field_key") or "")
        by_field.setdefault(fk, []).append(r)
    out: List[ConflictPair] = []
    # Stable sort by field_key for deterministic operator-UI order.
    for fk in sorted(by_field.keys()):
        fd = bio_schema.get_field_by_key(fk)
        field_label = fd.field_label if fd else fk
        out.append(ConflictPair(
            field_key=fk,
            field_label=field_label,
            rows=tuple(by_field[fk]),
        ))
    return out


# ─────────────────────────────────────────────────────────────────────
# Creep telemetry rollup (Defense 1 dashboard surface)
# ─────────────────────────────────────────────────────────────────────


def creep_telemetry_rollup(
    narrator_id: str, window: int = 5,
) -> Dict[str, Any]:
    """Wrap bio_anchored_asker.compute_creep_telemetry +
    classify_telemetry_warning into a render-friendly shape. Surface
    the literal threshold values so the UI can show "delta avg X
    (amber at -0.25)" without hard-coding the threshold on the FE.
    """
    if not narrator_id:
        return {
            "narrator_id": "",
            "warning": "green",
            "rolling_continuation_delta_avg": 0.0,
            "ask_caused_chapter_end_rate": 0.0,
            "sample_size": 0,
            "delta_amber_threshold": bio_anchored_asker.DELTA_AMBER_THRESHOLD,
            "chapter_end_red_threshold": bio_anchored_asker.CHAPTER_END_RED_THRESHOLD,
        }
    t = bio_anchored_asker.compute_creep_telemetry(narrator_id, window=window)
    return {
        "narrator_id": narrator_id,
        "warning": bio_anchored_asker.classify_telemetry_warning(t),
        "rolling_continuation_delta_avg": t.rolling_continuation_delta_avg,
        "ask_caused_chapter_end_rate": t.ask_caused_chapter_end_rate,
        "sample_size": t.sample_size,
        "delta_amber_threshold": bio_anchored_asker.DELTA_AMBER_THRESHOLD,
        "chapter_end_red_threshold": bio_anchored_asker.CHAPTER_END_RED_THRESHOLD,
    }


# ─────────────────────────────────────────────────────────────────────
# All-in-one summary (consumed by /api/operator/bio-gap-map/summary)
# ─────────────────────────────────────────────────────────────────────


def full_summary(narrator_id: str) -> Dict[str, Any]:
    """One-shot rollup the operator dashboard pulls per refresh.

    Bundles completeness + recently_asked + suggested_asks (top 10) +
    conflicts + creep telemetry so the FE makes one round trip
    instead of five.
    """
    completeness = compute_completeness(narrator_id)
    recents = recently_asked(narrator_id, limit=10)
    suggested = suggested_asks(narrator_id)
    conflicts = list_conflicts(narrator_id)
    telemetry = creep_telemetry_rollup(narrator_id)
    return {
        "narrator_id": narrator_id,
        "completeness": completeness.to_dict(),
        "recently_asked": [r.to_dict() for r in recents],
        # Cap suggested at 20 — full list is queryable separately
        # via /api/operator/bio-gap-map/suggested-asks
        "suggested_asks": [s.to_dict() for s in suggested[:20]],
        "suggested_asks_total": len(suggested),
        "conflicts": [c.to_dict() for c in conflicts],
        "creep_telemetry": telemetry,
    }


__all__ = [
    "CategoryCompleteness",
    "CompletenessRollup",
    "RecentAsk",
    "SuggestedAsk",
    "ConflictPair",
    "compute_completeness",
    "recently_asked",
    "suggested_asks",
    "list_conflicts",
    "creep_telemetry_rollup",
    "full_summary",
]
