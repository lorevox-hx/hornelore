"""WO-LORI-BIO-BUILDER-UNIVERSAL-01 (2026-06-14) — Phase D Tier 3 service.

═══════════════════════════════════════════════════════════════════════
  WHAT THIS IS
═══════════════════════════════════════════════════════════════════════

The Tier 3 anchored asker. The only piece of the bio architecture
where Lori's mouth is used as an operator instrument. Every other tier
(chapter extraction, document derivation, operator direct-entry) fills
bio without interrupting the narrator. This tier interrupts.

Because of that, this service is structurally engineered to RESIST its
own use. Eligibility is gated by multiple independent checks, every
ask is logged for telemetry that surfaces creep, the per-session cap
is hard-coded modulo the override-file friction, and three creep
defenses (continuation telemetry, chapter health floor, hard friction
on raising caps) layer on top.

PER WO §Anchored Asking Creep Defense:
  "The friction is the defense; the friction is what makes 'we're an
  oral-history system' a maintained promise rather than an aspirational
  one."

LAW 3 INFRASTRUCTURE BOUNDARY:
This module imports stdlib + ..db + .bio_schema + .bio_anchored_overrides
only. It does NOT import from extract.py, chat_ws.py, prompt_composer.
The integration point is one call from chat_ws.py's composition pipeline
(wired in D.5), behind the HORNELORE_BIO_ANCHORED_ASKER env flag
default-off.

═══════════════════════════════════════════════════════════════════════
  ELIGIBILITY CHAIN (per WO §Tier 3)
═══════════════════════════════════════════════════════════════════════

For a turn to be eligible for an anchored ask, ALL of the following
must be true:

  E1. HORNELORE_BIO_ANCHORED_ASKER=1 (env flag — feature on)
  E2. Momentum score < momentum_ceiling (default 0.4)
  E3. Asks-this-session < max_per_session (default 3)
  E4. Turns since last anchored ask >= turn_spacing (default 4)
  E5. Last-5-turn avg word count >= chapter_health_floor * first-5-turn
      avg word count (default 0.8) — Defense 2
  E6. At least one bio_fields high-value field is currently a gap for
      this narrator
  E7. Chapter context (last narrator turn) matches at least one
      asking_anchors pattern for a gap field

When all E1-E7 hold, the asker picks the FIRST anchor-matched gap (by
bio_schema seed order — deterministic), composes the surface text, and
writes a placeholder bio_facts row at status='anchored_asked_pending'.
The next narrator turn extraction either fills the value
(extracted_needs_verify) or doesn't (placeholder remains for operator
review).

═══════════════════════════════════════════════════════════════════════
  CHAPTER CONTINUATION METRIC (Defense 1)
═══════════════════════════════════════════════════════════════════════

Per anchored-ask, the placeholder row carries a JSON-encoded metric:

  {
    "narrator_turn_length_before_ask": int,    # avg of last 3 turns
    "narrator_turn_length_after_ask": int,     # the turn after the ask
    "narrator_turn_length_baseline": int,      # session avg
    "continuation_delta": float,               # (after - baseline) / baseline
    "ask_caused_chapter_end": bool,            # true if next 2 turns < 20w each
  }

The `after`/`continuation_delta`/`ask_caused_chapter_end` fields can
only be filled AFTER the narrator's subsequent turn(s) arrive. The
asker computes the `before` + `baseline` + scaffold at the moment of
the ask; bio_anchored_asker.update_metric_after_response is called
from the next-turn pipeline to backfill `after` + derived fields.

═══════════════════════════════════════════════════════════════════════
  PUBLIC API
═══════════════════════════════════════════════════════════════════════

  asker_enabled() → bool
      Reads HORNELORE_BIO_ANCHORED_ASKER. Default OFF.

  evaluate_eligibility(narrator_id, momentum_score,
                       session_narrator_turns, turns_since_last_ask,
                       asks_this_session) → EligibilityResult

  pick_anchored_gap(narrator_id, narrator_text) → Optional[GapMatch]
      Returns the (FieldDefinition, matched_anchor) tuple or None.

  compose_surface_text(field_def, narrator_text) → str
      Deterministic template — chapter-natural framing.

  fire_anchored_ask(narrator_id, gap_match, *, session_id, turn_id,
                    session_narrator_turns) → str
      Writes the placeholder bio_facts row. Returns the row id.
      Computes the chapter_continuation_metric scaffold.

  update_metric_after_response(fact_id, response_turn_text,
                               subsequent_turn_texts) → bool
      Backfill the after/delta/ask_caused_chapter_end fields once
      the narrator's next turn(s) arrive.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from .. import db
from . import bio_schema
from .bio_anchored_overrides import (
    AnchoredOverrides,
    DEFAULT_CHAPTER_HEALTH_FLOOR,
    DEFAULT_MAX_PER_SESSION,
    DEFAULT_MOMENTUM_CEILING,
    DEFAULT_TURN_SPACING,
    load_overrides,
)


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────

# Per WO §Defense 1 — "next 2 turns < 20 words each" definition of
# chapter-end caused by the ask.
_ASK_CAUSED_CHAPTER_END_WORD_THRESHOLD = 20

# Per WO §Defense 2 — minimum number of turns required to assess
# session health. Below this, we don't have enough data to compute
# the floor reliably, so we pass the check.
_HEALTH_FLOOR_MIN_TURNS = 5

# Status enum we write at ask time
_STATUS_PENDING = "anchored_asked_pending"
_STATUS_ASKED = "anchored_asked"


# ─────────────────────────────────────────────────────────────────────
# Env flag
# ─────────────────────────────────────────────────────────────────────


def asker_enabled() -> bool:
    """Tier 3 anchored asker is shipped default-OFF behind
    HORNELORE_BIO_ANCHORED_ASKER. Set to 1 to enable."""
    return os.environ.get(
        "HORNELORE_BIO_ANCHORED_ASKER", "0",
    ).strip().lower() in ("1", "true", "yes", "on")


# ─────────────────────────────────────────────────────────────────────
# Eligibility
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EligibilityResult:
    """Frozen eligibility decision. .eligible is the structural answer;
    .reason carries the FIRST failed check for telemetry / log lines.
    Multiple failures might exist; we report the first because
    operators care about the dispositive condition, not the full set.
    """
    eligible: bool
    reason: str = ""
    overrides_active: bool = False


def _compute_first_5_avg(turns: List[int]) -> float:
    """Average word count of the first 5 turns. Returns 0.0 when
    fewer than 5 turns exist."""
    if len(turns) < 5:
        return 0.0
    head = turns[:5]
    return sum(head) / len(head)


def _compute_last_5_avg(turns: List[int]) -> float:
    """Average word count of the last 5 turns. Returns 0.0 when
    fewer than 5 turns exist."""
    if len(turns) < 5:
        return 0.0
    tail = turns[-5:]
    return sum(tail) / len(tail)


def evaluate_eligibility(
    narrator_id: str,
    momentum_score: float,
    session_turn_word_counts: List[int],
    turns_since_last_ask: int,
    asks_this_session: int,
    *,
    overrides: Optional[AnchoredOverrides] = None,
) -> EligibilityResult:
    """Run the full eligibility chain E1-E5. E6 (gap exists) + E7
    (anchor matches) are decided by pick_anchored_gap() because they
    require DB queries against bio_facts; this function handles only
    the rate-limit + chapter-health checks.

    `session_turn_word_counts` is a list (oldest-first) of word counts
    for the narrator's prior turns in this session, EXCLUDING the
    current turn being composed for.

    `turns_since_last_ask` is the count of narrator turns since the
    last anchored ask fired in this session (or a large number if no
    prior ask exists).

    `asks_this_session` is the number of anchored asks already fired
    in this session.
    """
    o = overrides if overrides is not None else load_overrides()
    overrides_active = o.active

    # E1 — env flag (caller's responsibility; we still surface in
    # the result for tests that mock the flag separately).
    if not asker_enabled():
        return EligibilityResult(
            eligible=False, reason="asker_disabled",
            overrides_active=overrides_active,
        )

    if not narrator_id:
        return EligibilityResult(
            eligible=False, reason="no_narrator_id",
            overrides_active=overrides_active,
        )

    # E2 — momentum ceiling
    if momentum_score >= o.momentum_ceiling:
        return EligibilityResult(
            eligible=False,
            reason=(
                f"momentum_too_high "
                f"score={momentum_score:.2f} ceiling={o.momentum_ceiling}"
            ),
            overrides_active=overrides_active,
        )

    # E3 — session frequency cap
    if asks_this_session >= o.max_per_session:
        return EligibilityResult(
            eligible=False,
            reason=(
                f"session_cap_reached "
                f"asks={asks_this_session} cap={o.max_per_session}"
            ),
            overrides_active=overrides_active,
        )

    # E4 — turn spacing rate limit
    if turns_since_last_ask < o.turn_spacing:
        return EligibilityResult(
            eligible=False,
            reason=(
                f"turn_spacing_violation "
                f"turns_since={turns_since_last_ask} "
                f"required={o.turn_spacing}"
            ),
            overrides_active=overrides_active,
        )

    # E5 — chapter health floor (Defense 2)
    if len(session_turn_word_counts) >= _HEALTH_FLOOR_MIN_TURNS:
        first_5 = _compute_first_5_avg(session_turn_word_counts)
        last_5 = _compute_last_5_avg(session_turn_word_counts)
        if first_5 > 0:
            ratio = last_5 / first_5
            if ratio < o.chapter_health_floor:
                return EligibilityResult(
                    eligible=False,
                    reason=(
                        f"chapter_health_floor_violated "
                        f"last_5_avg={last_5:.1f} "
                        f"first_5_avg={first_5:.1f} "
                        f"ratio={ratio:.2f} "
                        f"floor={o.chapter_health_floor}"
                    ),
                    overrides_active=overrides_active,
                )

    return EligibilityResult(
        eligible=True, reason="",
        overrides_active=overrides_active,
    )


# ─────────────────────────────────────────────────────────────────────
# Gap selection
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GapMatch:
    """One matched (field, anchor) pair. field is a FieldDefinition
    from the seeded schema; anchor is the lowercased substring that
    triggered the match."""
    field_key: str
    field_label: str
    matched_anchor: str


def _current_gap_field_keys(narrator_id: str) -> Set[str]:
    """Compute the set of high-value field_keys that are currently
    gaps for this narrator. A field is a "gap" when:
      - no bio_facts row exists for (narrator, field), OR
      - the only rows for (narrator, field) are status='empty'

    Rows in any non-empty status (extracted_needs_verify, approved,
    document_sourced, operator_entered, conflicted, anchored_asked,
    anchored_asked_pending, superseded) DO NOT count as gaps. Once a
    narrator has answered or the operator has filled a field, the
    anchored asker stops asking — even if the answer is conflicted.
    """
    high_value = bio_schema.get_high_value_fields()
    high_value_keys = {fd.field_key for fd in high_value}
    try:
        existing_rows = db.bio_fact_list_by_narrator(narrator_id)
    except Exception:
        # If the DB query crashes, treat all high-value fields as
        # gaps (best-effort permissive behavior; the asker has many
        # other gates that would still block a real ask).
        return high_value_keys
    filled_keys: Set[str] = set()
    for r in existing_rows:
        if str(r.get("status") or "") != "empty":
            filled_keys.add(str(r.get("field_key") or ""))
    return high_value_keys - filled_keys


def pick_anchored_gap(
    narrator_id: str,
    narrator_text: str,
) -> Optional[GapMatch]:
    """Find a high-value gap whose asking_anchors patterns match the
    narrator's current turn. Returns the first match (by bio_schema
    seed order — deterministic). None when no gap matches.

    Anchor matching is case-insensitive lowercase substring against
    the narrator's text. This is intentionally coarse; the seeded
    anchors are short, specific phrases and the chapter context is
    long enough that false positives are rare.
    """
    if not narrator_id or not narrator_text:
        return None
    gap_keys = _current_gap_field_keys(narrator_id)
    if not gap_keys:
        return None
    text_lower = narrator_text.lower()
    for fd in bio_schema.iter_seed():
        if fd.field_key not in gap_keys:
            continue
        # narrative_value=high + non-empty asking_anchors is the
        # Tier 3 eligibility floor (this is the deactivation signal
        # for fields that are high-value-but-only-extracted-not-asked).
        if fd.narrative_value != "high" or not fd.asking_anchors:
            continue
        for anchor in fd.asking_anchors:
            if anchor in text_lower:
                return GapMatch(
                    field_key=fd.field_key,
                    field_label=fd.field_label,
                    matched_anchor=anchor,
                )
    return None


# ─────────────────────────────────────────────────────────────────────
# Composition
# ─────────────────────────────────────────────────────────────────────


def compose_surface_text(
    field_def_or_match: Any,
    narrator_text: str,
) -> str:
    """Deterministic template that names the gap and the chapter
    context. The actual question phrasing is composed by the LLM via
    the LORI_ANCHORED_ASK_DIRECTIVE_TEMPLATE prompt block; this
    function returns the OPERATOR-VISIBLE surface text that the
    composer hands the LLM as context.

    Accepts either a FieldDefinition or a GapMatch (both have
    field_key + field_label attributes).
    """
    field_label = getattr(field_def_or_match, "field_label", "")
    matched_anchor = getattr(
        field_def_or_match, "matched_anchor", "",
    )
    # Operator-visible composer instruction. Lori sees this through
    # the LORI_ANCHORED_ASK_DIRECTIVE block and chooses chapter-natural
    # phrasing. Keep concise — the LLM has the chapter context too.
    parts = [
        f"You have not yet captured the narrator's {field_label.lower()}.",
        f"Their current chapter touches on: {matched_anchor!r}.",
        (
            "If a natural opening exists in this chapter, ask one brief, "
            "specific question that anchors to what they just said. "
            "Phrase it as a chapter-natural continuation, NOT a generic "
            "questionnaire item. Do NOT ask if no natural opening exists."
        ),
    ]
    return " ".join(parts)


# ─────────────────────────────────────────────────────────────────────
# Chapter continuation metric (Defense 1)
# ─────────────────────────────────────────────────────────────────────


def _compute_metric_scaffold(
    session_turn_word_counts: List[int],
) -> Dict[str, Any]:
    """Build the chapter_continuation_metric scaffold at the moment of
    the ask. The `_after` + `_delta` + `_caused_chapter_end` fields
    are filled later by update_metric_after_response when subsequent
    narrator turns arrive."""
    # Avg of last 3 turns (the ones BEFORE the ask)
    if len(session_turn_word_counts) >= 3:
        before_avg = int(
            sum(session_turn_word_counts[-3:]) / 3
        )
    elif session_turn_word_counts:
        before_avg = int(
            sum(session_turn_word_counts) / len(session_turn_word_counts)
        )
    else:
        before_avg = 0
    # Session avg as the baseline
    if session_turn_word_counts:
        baseline_avg = int(
            sum(session_turn_word_counts) / len(session_turn_word_counts)
        )
    else:
        baseline_avg = 0
    return {
        "narrator_turn_length_before_ask": before_avg,
        "narrator_turn_length_after_ask": None,
        "narrator_turn_length_baseline": baseline_avg,
        "continuation_delta": None,
        "ask_caused_chapter_end": None,
    }


# ─────────────────────────────────────────────────────────────────────
# Fire-ask + post-response update
# ─────────────────────────────────────────────────────────────────────


def fire_anchored_ask(
    narrator_id: str,
    gap_match: GapMatch,
    *,
    session_id: Optional[str] = None,
    turn_id: Optional[str] = None,
    session_turn_word_counts: Optional[List[int]] = None,
    tenant_id: str = "default",
) -> str:
    """Write the placeholder bio_facts row recording that the asker
    fired. Returns the row id. Computes the metric scaffold per
    Defense 1.

    The row carries status='anchored_asked_pending' until the next
    narrator turn arrives; then either:
      - Extraction succeeds → status promotes to 'anchored_asked'
        AND a sibling extracted_needs_verify row is written by Tier 1
      - Extraction fails → row stays anchored_asked_pending, visible
        to the operator as "asked, no answer"
    """
    metric_scaffold = _compute_metric_scaffold(
        session_turn_word_counts or [],
    )
    source_payload = {
        "tier": 3,
        "session_id": session_id,
        "turn_id": turn_id,
        "matched_anchor": gap_match.matched_anchor,
    }
    new_id = db.bio_fact_create(
        narrator_id=narrator_id,
        field_key=gap_match.field_key,
        # Empty JSON string for placeholder; will be replaced when
        # the narrator's next turn produces an extraction.
        value_json='""',
        status=_STATUS_PENDING,
        source_json=json.dumps(source_payload),
        confidence=0.0,
        chapter_continuation_metric_json=json.dumps(metric_scaffold),
        tenant_id=tenant_id,
    )
    return new_id


def update_metric_after_response(
    fact_id: str,
    response_turn_word_count: int,
    subsequent_turn_word_counts: Optional[List[int]] = None,
) -> bool:
    """Backfill the after-the-ask metric fields. Called from the
    next-turn pipeline once the narrator's response arrives.

    `response_turn_word_count` is the word count of the turn
    IMMEDIATELY after Lori's anchored question.
    `subsequent_turn_word_counts` is the next-2-turns word counts
    used by the ask_caused_chapter_end check.

    Returns True when the update lands.
    """
    row = db.bio_fact_get(fact_id)
    if not row:
        return False
    metric_json = row.get("chapter_continuation_metric")
    if not metric_json:
        return False
    try:
        metric = json.loads(metric_json)
    except (ValueError, TypeError):
        return False
    baseline = int(metric.get("narrator_turn_length_baseline") or 0)
    metric["narrator_turn_length_after_ask"] = int(
        response_turn_word_count or 0,
    )
    if baseline > 0:
        metric["continuation_delta"] = round(
            (response_turn_word_count - baseline) / float(baseline),
            3,
        )
    else:
        metric["continuation_delta"] = 0.0
    # ask_caused_chapter_end — true if the next two turns (the
    # response itself + the one after) are both shorter than
    # _ASK_CAUSED_CHAPTER_END_WORD_THRESHOLD (default 20)
    next_two = [response_turn_word_count] + list(
        subsequent_turn_word_counts or [],
    )
    next_two = next_two[:2]
    if len(next_two) == 2:
        metric["ask_caused_chapter_end"] = all(
            w < _ASK_CAUSED_CHAPTER_END_WORD_THRESHOLD for w in next_two
        )
    else:
        # Only one post-ask turn observed yet — leave field null;
        # caller may re-invoke later when a second turn lands.
        metric["ask_caused_chapter_end"] = None

    # Write back. Status transition is the caller's concern; we
    # only update the metric column. Use a small direct UPDATE to
    # avoid extending the db.py API with a metric-only setter.
    init_db = getattr(db, "init_db", None)
    if init_db:
        try:
            init_db()
        except Exception:
            pass
    con = db._connect()
    try:
        con.execute(
            "UPDATE bio_facts "
            "SET chapter_continuation_metric=?, last_updated=? "
            "WHERE id=?;",
            (json.dumps(metric), _now_iso(), fact_id),
        )
        con.commit()
        return True
    except Exception:
        try:
            con.rollback()
        except Exception:
            pass
        return False
    finally:
        con.close()


def _now_iso() -> str:
    """Local timestamp helper — mirrors db._now_iso behavior without
    importing the underscore-prefixed function directly."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────────
# Telemetry rollup (Defense 1 — surfaces creep)
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CreepTelemetry:
    """Per-narrator rolling rollup of anchored-ask creep telemetry.

    rolling_continuation_delta_avg: average of continuation_delta
        across the last N anchored asks for this narrator. Negative
        values mean asks systematically shorten subsequent turns.
    ask_caused_chapter_end_rate: fraction of asks where
        ask_caused_chapter_end=True. >0.4 escalates to red warning.
    sample_size: number of anchored asks in the rollup window.
    """
    rolling_continuation_delta_avg: float
    ask_caused_chapter_end_rate: float
    sample_size: int


def compute_creep_telemetry(
    narrator_id: str,
    window: int = 5,
) -> CreepTelemetry:
    """Compute the rolling creep telemetry for a narrator. Window=5
    matches the WO spec's "rolling 5-ask window".

    Returns a CreepTelemetry with all-zero fields when fewer than
    window asks exist (insufficient data for a meaningful rollup).
    """
    try:
        # Fetch all bio_facts rows with a chapter_continuation_metric
        # (tier-3 originated only). Newest first.
        rows = db.bio_fact_list_by_narrator(narrator_id)
    except Exception:
        return CreepTelemetry(0.0, 0.0, 0)
    metric_rows: List[Dict[str, Any]] = []
    for r in rows:
        if r.get("chapter_continuation_metric"):
            try:
                metric = json.loads(r["chapter_continuation_metric"])
                metric_rows.append(metric)
            except (ValueError, TypeError):
                continue
    if len(metric_rows) < window:
        return CreepTelemetry(0.0, 0.0, len(metric_rows))
    # Most recent `window` rows
    metric_rows = metric_rows[:window]
    deltas = [
        m.get("continuation_delta") for m in metric_rows
        if m.get("continuation_delta") is not None
    ]
    ends = [
        bool(m.get("ask_caused_chapter_end")) for m in metric_rows
        if m.get("ask_caused_chapter_end") is not None
    ]
    delta_avg = sum(deltas) / len(deltas) if deltas else 0.0
    end_rate = sum(ends) / len(ends) if ends else 0.0
    return CreepTelemetry(
        rolling_continuation_delta_avg=round(delta_avg, 3),
        ask_caused_chapter_end_rate=round(end_rate, 3),
        sample_size=len(metric_rows),
    )


# Warning thresholds per WO §Defense 1 — amber at delta < -0.25,
# red at chapter-end rate > 40%.
DELTA_AMBER_THRESHOLD = -0.25
CHAPTER_END_RED_THRESHOLD = 0.40


def classify_telemetry_warning(
    telemetry: CreepTelemetry,
) -> str:
    """Classify telemetry into 'red' / 'amber' / 'green'. Operator
    dashboard banner color flows from this."""
    if telemetry.sample_size < 1:
        return "green"
    if telemetry.ask_caused_chapter_end_rate >= CHAPTER_END_RED_THRESHOLD:
        return "red"
    if telemetry.rolling_continuation_delta_avg < DELTA_AMBER_THRESHOLD:
        return "amber"
    return "green"


__all__ = [
    "EligibilityResult",
    "GapMatch",
    "CreepTelemetry",
    "DELTA_AMBER_THRESHOLD",
    "CHAPTER_END_RED_THRESHOLD",
    "asker_enabled",
    "evaluate_eligibility",
    "pick_anchored_gap",
    "compose_surface_text",
    "fire_anchored_ask",
    "update_metric_after_response",
    "compute_creep_telemetry",
    "classify_telemetry_warning",
]
