"""WO-LORI-SESSION-AWARENESS-01 Phase 4 — Adaptive Narrator Silence Ladder.

╔════════════════════════════════════════════════════════════════════╗
║                                                                    ║
║  PHASE 4 SKELETON — DO NOT WIRE LIVE                               ║
║                                                                    ║
║  Per Chris's locked rule (2026-05-03): "wait for one real          ║
║  Janice/Kent observation of Phase 3 before scoping Phase 4."       ║
║                                                                    ║
║  This module is a pure-Python helper with no live consumers. It    ║
║  is committed AHEAD OF the live-observation gate so the rolling-   ║
║  window math is reviewable + testable, but no caller in the live   ║
║  request path imports it. The HORNELORE_NARRATOR_PACING_LIVE       ║
║  env flag stays default-OFF until Janice/Kent post-Phase-3         ║
║  observation lands and Phase 4 is explicitly green-lit.            ║
║                                                                    ║
║  When Phase 4 actually opens:                                      ║
║    1. Confirm Janice/Kent feel-test of Phase 3 visual cue is OK    ║
║    2. Flip HORNELORE_NARRATOR_PACING_LIVE=1 in .env                ║
║    3. Wire callers in chat_ws.py + attention-cue-ticker.js         ║
║    4. Persist windows to DB (in-memory storage in this skeleton    ║
║       loses data on restart — fine for skeleton, NOT fine for      ║
║       production)                                                  ║
║                                                                    ║
╚════════════════════════════════════════════════════════════════════╝

Design (per WO-LORI-SESSION-AWARENESS-01 §Phase 4):

  Per-narrator × prompt_weight rolling window:
    narrator_pacing[narrator_id][prompt_weight] = {
      recent_gaps: [<= 30 most recent response_gap_ms],
      last_updated: ts,
    }

  Ladder calculation (per narrator × prompt_weight, recomputed lazily):
    if len(window) < 10:
      # cold-start — fall back to WO-10C defaults (120s/300s/600s)
      tier1, tier2, tier3 = 120s, 300s, 600s
    else:
      p75 = percentile(window, 75)
      p90 = percentile(window, 90)
      p95 = percentile(window, 95)
      tier1 = max(FLOOR_MS, p75 + 5s)
      tier2 = max(tier1 * 2, p90 + 10s)
      tier3 = max(tier2 * 2, p95 + 30s)

  HARD_FLOOR_MS = 25s — no cue fires before this regardless of any
                       signal or computed tier.

Hard rules (cannot violate):
  - Pure pacing FIT, not measurement. No clinical scoring.
  - Window persists locally only. No long-term aggregate retained.
  - No surface exposes the window data. No "narrator pacing report"
    UI exists or will be built.
  - Per-narrator data lives in this module's in-memory dict only
    (skeleton); production wiring will move to short-lived per-
    session DB rows that age out.

LAW: pure stdlib. No db, no LLM, no IO. Suitable for use inside
any eval harness without touching the runtime stack.
"""
from __future__ import annotations

import math
import os
import time
from typing import Dict, List, Optional, Tuple

# ── Constants ──────────────────────────────────────────────────────

# Hard floor — no cue fires before this gap_ms, ever. Matches the
# attention-cue-dispatcher.js HARD_FLOOR_MS exactly.
HARD_FLOOR_MS: int = 25_000

# Cold-start threshold — fewer than this many gaps in the window
# means we don't have enough data to fit; fall back to WO-10C.
COLD_START_THRESHOLD: int = 10

# Window size — keep at most this many recent response gaps per
# (narrator_id, prompt_weight). Older gaps are dropped FIFO.
WINDOW_SIZE: int = 30

# WO-10C fallback ladder (ms) — what we use when cold-start.
WO_10C_TIER1_MS: int = 120_000
WO_10C_TIER2_MS: int = 300_000
WO_10C_TIER3_MS: int = 600_000

# Margins added to percentiles when fitting (per WO §Phase 4 spec).
TIER1_PERCENTILE_MARGIN_MS: int =  5_000
TIER2_PERCENTILE_MARGIN_MS: int = 10_000
TIER3_PERCENTILE_MARGIN_MS: int = 30_000

# Allowed prompt-weight values — small fixed vocabulary so a typo
# can't proliferate across the dict.
PROMPT_WEIGHTS = ("low", "med", "high")

# Default env-flag name for live wiring (NOT consulted in skeleton).
ENV_LIVE_FLAG = "HORNELORE_NARRATOR_PACING_LIVE"


# ── In-memory storage ──────────────────────────────────────────────

# Skeleton-only. Production wiring will move this to a short-lived
# per-session DB table that ages out after ~24h.
#
# Shape: { (narrator_id, prompt_weight): {recent_gaps: list[int],
#                                          last_updated: float} }
_pacing_windows: Dict[Tuple[str, str], Dict] = {}


# ── Helpers ────────────────────────────────────────────────────────

def _percentile(sorted_values: List[int], pct: float) -> float:
    """Compute a single percentile from a SORTED list (ascending).

    pct is in [0, 100]. Uses linear interpolation between the two
    nearest values — same convention as numpy.percentile default.
    Returns 0.0 on an empty list.
    """
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    if pct <= 0:
        return float(sorted_values[0])
    if pct >= 100:
        return float(sorted_values[-1])
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return float(sorted_values[lo])
    weight = rank - lo
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * weight


def _key(narrator_id: str, prompt_weight: str) -> Tuple[str, str]:
    """Compose the dict key + validate prompt_weight."""
    if prompt_weight not in PROMPT_WEIGHTS:
        # Coerce unknown to "med" rather than raising — defensive.
        prompt_weight = "med"
    return (narrator_id, prompt_weight)


# ── Public API — write side ────────────────────────────────────────

def add_response_gap(narrator_id: str, prompt_weight: str, gap_ms: int) -> None:
    """Record a single response_gap_ms observation for this narrator
    × prompt_weight bucket. Drops the oldest entry once the window
    is full (FIFO).

    No validation on gap_ms beyond clamping negatives to 0 — caller
    is expected to filter degenerate values (mic-still-active, no-
    response, etc.) BEFORE calling.
    """
    if not narrator_id:
        return
    gap = max(0, int(gap_ms or 0))
    k = _key(narrator_id, prompt_weight)
    bucket = _pacing_windows.setdefault(k, {"recent_gaps": [], "last_updated": 0.0})
    bucket["recent_gaps"].append(gap)
    if len(bucket["recent_gaps"]) > WINDOW_SIZE:
        # Drop oldest (FIFO trim)
        bucket["recent_gaps"] = bucket["recent_gaps"][-WINDOW_SIZE:]
    bucket["last_updated"] = time.time()


def reset_narrator(narrator_id: str) -> None:
    """Clear all windows for a narrator (e.g. on Reset Identity).
    Removes every (narrator_id, *) bucket."""
    if not narrator_id:
        return
    for key in list(_pacing_windows.keys()):
        if key[0] == narrator_id:
            del _pacing_windows[key]


def reset_all() -> None:
    """Drop every window — for tests + dev clear. Production must
    NOT call this at runtime."""
    _pacing_windows.clear()


# ── Public API — read side ─────────────────────────────────────────

def compute_silence_ladder(
    narrator_id: str,
    prompt_weight: str,
) -> Dict[str, int]:
    """Return the per-narrator × prompt_weight ladder thresholds (ms).

    Returned dict shape:
        {
          "tier1_ms": int,
          "tier2_ms": int,
          "tier3_ms": int,
          "source":   "fitted" | "cold_start_fallback",
          "n_gaps":   int,   # how many gaps were used in the fit
        }

    When source == "cold_start_fallback", tiers are the WO-10C
    defaults (120s / 300s / 600s). When "fitted", the tiers are
    computed from p75 / p90 / p95 of the recent_gaps window with
    the margins from WO §Phase 4 applied.

    HARD_FLOOR_MS (25s) is enforced on tier1; the remaining tiers
    are at least double the previous tier (per WO §Phase 4 spec).
    """
    k = _key(narrator_id, prompt_weight)
    bucket = _pacing_windows.get(k)
    if not bucket or len(bucket["recent_gaps"]) < COLD_START_THRESHOLD:
        return {
            "tier1_ms": WO_10C_TIER1_MS,
            "tier2_ms": WO_10C_TIER2_MS,
            "tier3_ms": WO_10C_TIER3_MS,
            "source":   "cold_start_fallback",
            "n_gaps":   len(bucket["recent_gaps"]) if bucket else 0,
        }

    sorted_gaps = sorted(bucket["recent_gaps"])
    p75 = _percentile(sorted_gaps, 75)
    p90 = _percentile(sorted_gaps, 90)
    p95 = _percentile(sorted_gaps, 95)

    tier1 = max(HARD_FLOOR_MS, int(p75) + TIER1_PERCENTILE_MARGIN_MS)
    tier2 = max(tier1 * 2,     int(p90) + TIER2_PERCENTILE_MARGIN_MS)
    tier3 = max(tier2 * 2,     int(p95) + TIER3_PERCENTILE_MARGIN_MS)

    return {
        "tier1_ms": tier1,
        "tier2_ms": tier2,
        "tier3_ms": tier3,
        "source":   "fitted",
        "n_gaps":   len(sorted_gaps),
    }


def get_silence_decision(
    gap_ms: int,
    narrator_id: str,
    prompt_weight: str,
) -> Dict:
    """Given a current response_gap_ms, return a decision object
    in the same vocabulary as the Phase 3 dispatcher.

    Returned dict shape:
        {
          "silence_tier":          int (-1, 1, 2, 3),
          "intent":                "visual_only" | "spoken_cue",
          "reason":                str,
          "cue_allowed":           bool,   # always False in Phase 4 skeleton
          "visual_presence_allowed": bool,
          "ladder":                <result from compute_silence_ladder>,
        }

    Per WO §Phase 4 + Chris's "no spoken cue until Phase 5" lock:
      - cue_allowed is always False (spoken cues are Phase 5 work)
      - intent is always "visual_only" (matches Phase 3 lock)
      - visual_presence_allowed is True iff gap_ms >= HARD_FLOOR_MS
        AND tier >= 1

    Phase 4 here only computes the LADDER and the SILENCE_TIER. It
    does NOT decide whether to fire a cue — that decision lives in
    attention-cue-dispatcher.js + presence-cue.js.
    """
    gap = max(0, int(gap_ms or 0))
    ladder = compute_silence_ladder(narrator_id, prompt_weight)

    # Hard floor: under 25s, narrator's space.
    if gap < HARD_FLOOR_MS:
        return {
            "silence_tier":          -1,
            "intent":                "visual_only",
            "reason":                "hard_floor",
            "cue_allowed":           False,
            "visual_presence_allowed": False,
            "ladder":                ladder,
        }

    if gap >= ladder["tier3_ms"]:
        tier = 3
    elif gap >= ladder["tier2_ms"]:
        tier = 2
    elif gap >= ladder["tier1_ms"]:
        tier = 1
    else:
        # Above hard floor but below fitted tier1 — narrator is
        # within their normal pacing rhythm.
        return {
            "silence_tier":          -1,
            "intent":                "visual_only",
            "reason":                "within_normal_rhythm",
            "cue_allowed":           False,
            "visual_presence_allowed": True,  # Phase 3 visual cue still shows
            "ladder":                ladder,
        }

    return {
        "silence_tier":          tier,
        "intent":                "visual_only",
        "reason":                "above_tier" + str(tier),
        # Phase 3 + Phase 4 lock: spoken cues are Phase 5 work only.
        "cue_allowed":           False,
        "visual_presence_allowed": True,
        "ladder":                ladder,
    }


# ── Diagnostics (operator-side, never narrator-facing) ─────────────

def get_window_snapshot(narrator_id: str, prompt_weight: str) -> Dict:
    """Return a copy of the current window for inspection. Operator
    use only. Used by test harness + future operator dashboard."""
    k = _key(narrator_id, prompt_weight)
    bucket = _pacing_windows.get(k)
    if not bucket:
        return {"recent_gaps": [], "last_updated": 0.0, "n_gaps": 0}
    return {
        "recent_gaps":  list(bucket["recent_gaps"]),
        "last_updated": bucket["last_updated"],
        "n_gaps":       len(bucket["recent_gaps"]),
    }


def is_live_enabled() -> bool:
    """Returns True iff HORNELORE_NARRATOR_PACING_LIVE is set to 1.
    No caller in the request path consults this yet — it's the gate
    that Phase 4 wiring will respect when it lands."""
    return os.getenv(ENV_LIVE_FLAG, "0").strip() == "1"


__all__ = [
    "add_response_gap",
    "reset_narrator",
    "reset_all",
    "compute_silence_ladder",
    "get_silence_decision",
    "get_window_snapshot",
    "is_live_enabled",
    # Constants exposed for tests + downstream consumers
    "HARD_FLOOR_MS",
    "COLD_START_THRESHOLD",
    "WINDOW_SIZE",
    "WO_10C_TIER1_MS",
    "WO_10C_TIER2_MS",
    "WO_10C_TIER3_MS",
    "PROMPT_WEIGHTS",
    "ENV_LIVE_FLAG",
]
