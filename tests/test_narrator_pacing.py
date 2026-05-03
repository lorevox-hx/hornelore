"""WO-LORI-SESSION-AWARENESS-01 Phase 4 — narrator_pacing unit tests.

Pure-stdlib tests for the rolling-window math + decision logic.

Run:
    python tests/test_narrator_pacing.py
    python -m unittest tests.test_narrator_pacing
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api.services.narrator_pacing import (  # noqa: E402
    add_response_gap,
    reset_narrator,
    reset_all,
    compute_silence_ladder,
    get_silence_decision,
    get_window_snapshot,
    is_live_enabled,
    HARD_FLOOR_MS,
    COLD_START_THRESHOLD,
    WINDOW_SIZE,
    WO_10C_TIER1_MS,
    WO_10C_TIER2_MS,
    WO_10C_TIER3_MS,
    PROMPT_WEIGHTS,
    ENV_LIVE_FLAG,
)


# ─────────────────────────────────────────────────────────────────
# add_response_gap + storage
# ─────────────────────────────────────────────────────────────────

class AddResponseGapTest(unittest.TestCase):
    def setUp(self):
        reset_all()

    def test_single_add_appears_in_snapshot(self):
        add_response_gap("n1", "med", 12_000)
        snap = get_window_snapshot("n1", "med")
        self.assertEqual(snap["n_gaps"], 1)
        self.assertEqual(snap["recent_gaps"], [12_000])

    def test_window_caps_at_30(self):
        for i in range(40):
            add_response_gap("n1", "med", 1_000 + i)
        snap = get_window_snapshot("n1", "med")
        self.assertEqual(snap["n_gaps"], WINDOW_SIZE)
        # FIFO drop — first 10 should be gone, last 30 should remain
        self.assertEqual(snap["recent_gaps"][0], 1_010)
        self.assertEqual(snap["recent_gaps"][-1], 1_039)

    def test_negative_gap_clamped_to_zero(self):
        add_response_gap("n1", "med", -500)
        snap = get_window_snapshot("n1", "med")
        self.assertEqual(snap["recent_gaps"], [0])

    def test_unknown_prompt_weight_coerces_to_med(self):
        add_response_gap("n1", "extreme", 9_000)
        # Should land in the "med" bucket, not raise
        snap = get_window_snapshot("n1", "med")
        self.assertEqual(snap["n_gaps"], 1)

    def test_empty_narrator_id_is_no_op(self):
        add_response_gap("", "med", 10_000)
        snap = get_window_snapshot("", "med")
        self.assertEqual(snap["n_gaps"], 0)

    def test_per_prompt_weight_isolation(self):
        add_response_gap("n1", "low", 5_000)
        add_response_gap("n1", "med", 10_000)
        add_response_gap("n1", "high", 15_000)
        self.assertEqual(get_window_snapshot("n1", "low")["n_gaps"], 1)
        self.assertEqual(get_window_snapshot("n1", "med")["n_gaps"], 1)
        self.assertEqual(get_window_snapshot("n1", "high")["n_gaps"], 1)
        self.assertEqual(get_window_snapshot("n1", "low")["recent_gaps"], [5_000])
        self.assertEqual(get_window_snapshot("n1", "med")["recent_gaps"], [10_000])

    def test_per_narrator_isolation(self):
        add_response_gap("n1", "med", 5_000)
        add_response_gap("n2", "med", 50_000)
        self.assertEqual(get_window_snapshot("n1", "med")["recent_gaps"], [5_000])
        self.assertEqual(get_window_snapshot("n2", "med")["recent_gaps"], [50_000])


# ─────────────────────────────────────────────────────────────────
# reset_narrator + reset_all
# ─────────────────────────────────────────────────────────────────

class ResetTest(unittest.TestCase):
    def setUp(self):
        reset_all()

    def test_reset_narrator_removes_all_buckets_for_that_narrator(self):
        add_response_gap("n1", "low", 1_000)
        add_response_gap("n1", "med", 2_000)
        add_response_gap("n1", "high", 3_000)
        add_response_gap("n2", "med", 4_000)
        reset_narrator("n1")
        self.assertEqual(get_window_snapshot("n1", "low")["n_gaps"], 0)
        self.assertEqual(get_window_snapshot("n1", "med")["n_gaps"], 0)
        self.assertEqual(get_window_snapshot("n1", "high")["n_gaps"], 0)
        # n2 is untouched
        self.assertEqual(get_window_snapshot("n2", "med")["recent_gaps"], [4_000])

    def test_reset_all_drops_everything(self):
        for i in range(5):
            add_response_gap(f"n{i}", "med", 10_000 + i)
        reset_all()
        for i in range(5):
            self.assertEqual(get_window_snapshot(f"n{i}", "med")["n_gaps"], 0)


# ─────────────────────────────────────────────────────────────────
# compute_silence_ladder — cold start vs fitted
# ─────────────────────────────────────────────────────────────────

class ComputeSilenceLadderTest(unittest.TestCase):
    def setUp(self):
        reset_all()

    def test_no_data_returns_wo10c_fallback(self):
        ladder = compute_silence_ladder("n1", "med")
        self.assertEqual(ladder["source"], "cold_start_fallback")
        self.assertEqual(ladder["tier1_ms"], WO_10C_TIER1_MS)
        self.assertEqual(ladder["tier2_ms"], WO_10C_TIER2_MS)
        self.assertEqual(ladder["tier3_ms"], WO_10C_TIER3_MS)
        self.assertEqual(ladder["n_gaps"], 0)

    def test_under_threshold_returns_fallback(self):
        # COLD_START_THRESHOLD = 10
        for i in range(COLD_START_THRESHOLD - 1):  # one short
            add_response_gap("n1", "med", 8_000 + i * 100)
        ladder = compute_silence_ladder("n1", "med")
        self.assertEqual(ladder["source"], "cold_start_fallback")
        self.assertEqual(ladder["n_gaps"], COLD_START_THRESHOLD - 1)

    def test_at_threshold_returns_fitted(self):
        # Exactly 10 gaps — should fit
        gaps = [5_000, 6_000, 7_000, 8_000, 9_000,
                10_000, 11_000, 12_000, 13_000, 14_000]
        for g in gaps:
            add_response_gap("n1", "med", g)
        ladder = compute_silence_ladder("n1", "med")
        self.assertEqual(ladder["source"], "fitted")
        self.assertEqual(ladder["n_gaps"], 10)
        # tier1 must be at least HARD_FLOOR_MS
        self.assertGreaterEqual(ladder["tier1_ms"], HARD_FLOOR_MS)

    def test_fitted_tiers_respect_doubling_rule(self):
        # When p75 is small, tier1 floors at HARD_FLOOR_MS, tier2 at
        # tier1*2 (50s), tier3 at tier2*2 (100s) — even though the
        # raw p90/p95 + margin would be smaller.
        for i in range(15):
            add_response_gap("n1", "med", 1_000)  # all 1s — uniform
        ladder = compute_silence_ladder("n1", "med")
        self.assertEqual(ladder["tier1_ms"], HARD_FLOOR_MS)  # 25_000
        self.assertEqual(ladder["tier2_ms"], HARD_FLOOR_MS * 2)
        self.assertEqual(ladder["tier3_ms"], HARD_FLOOR_MS * 4)

    def test_fitted_tiers_use_percentile_when_high(self):
        # When recent gaps are large, percentiles drive tier values.
        # p75 of [30k, 35k, ..., 100k] should be high — well above
        # HARD_FLOOR_MS.
        gaps = list(range(30_000, 101_000, 5_000))  # 15 gaps
        for g in gaps:
            add_response_gap("n1", "med", g)
        ladder = compute_silence_ladder("n1", "med")
        self.assertEqual(ladder["source"], "fitted")
        # tier1 should reflect p75 + 5s margin, well above HARD_FLOOR
        self.assertGreater(ladder["tier1_ms"], HARD_FLOOR_MS + 30_000)
        # tier2 > tier1, tier3 > tier2 always
        self.assertGreater(ladder["tier2_ms"], ladder["tier1_ms"])
        self.assertGreater(ladder["tier3_ms"], ladder["tier2_ms"])


# ─────────────────────────────────────────────────────────────────
# get_silence_decision — vocabulary contract
# ─────────────────────────────────────────────────────────────────

class GetSilenceDecisionTest(unittest.TestCase):
    def setUp(self):
        reset_all()

    def test_under_hard_floor_returns_narrator_space(self):
        d = get_silence_decision(20_000, "n1", "med")
        self.assertEqual(d["silence_tier"], -1)
        self.assertEqual(d["reason"], "hard_floor")
        self.assertFalse(d["visual_presence_allowed"])
        self.assertFalse(d["cue_allowed"])
        self.assertEqual(d["intent"], "visual_only")

    def test_above_hard_floor_below_tier1_within_normal(self):
        d = get_silence_decision(30_000, "n1", "med")
        # Cold-start tier1 is 120s, so 30s is below tier1
        self.assertEqual(d["silence_tier"], -1)
        self.assertEqual(d["reason"], "within_normal_rhythm")
        self.assertTrue(d["visual_presence_allowed"])
        self.assertFalse(d["cue_allowed"])

    def test_at_tier1_boundary_returns_tier1(self):
        d = get_silence_decision(WO_10C_TIER1_MS, "n1", "med")
        self.assertEqual(d["silence_tier"], 1)
        self.assertEqual(d["reason"], "above_tier1")
        self.assertTrue(d["visual_presence_allowed"])

    def test_at_tier2_boundary_returns_tier2(self):
        d = get_silence_decision(WO_10C_TIER2_MS, "n1", "med")
        self.assertEqual(d["silence_tier"], 2)

    def test_at_tier3_boundary_returns_tier3(self):
        d = get_silence_decision(WO_10C_TIER3_MS, "n1", "med")
        self.assertEqual(d["silence_tier"], 3)

    def test_cue_allowed_always_false_phase4_skeleton(self):
        # Phase 5 is the only future gate that may flip cue_allowed
        # to True. Phase 4 skeleton MUST keep it False.
        for gap in [10_000, 30_000, 130_000, 310_000, 700_000]:
            d = get_silence_decision(gap, "n1", "med")
            self.assertFalse(d["cue_allowed"],
                f"cue_allowed must be False at gap_ms={gap}")

    def test_intent_always_visual_only(self):
        # Same Phase 3 lock: never produce a spoken intent in skeleton.
        for gap in [0, 25_000, 60_000, 120_000, 600_000]:
            d = get_silence_decision(gap, "n1", "med")
            self.assertEqual(d["intent"], "visual_only",
                f"intent must be visual_only at gap_ms={gap}")


# ─────────────────────────────────────────────────────────────────
# Live-flag gate
# ─────────────────────────────────────────────────────────────────

class LiveFlagGateTest(unittest.TestCase):
    def test_default_off(self):
        # Skeleton ships with the flag undefined — should be False.
        # This test is environment-sensitive; tolerate prior set.
        import os
        prev = os.environ.pop(ENV_LIVE_FLAG, None)
        try:
            self.assertFalse(is_live_enabled())
        finally:
            if prev is not None:
                os.environ[ENV_LIVE_FLAG] = prev

    def test_explicit_on(self):
        import os
        prev = os.environ.get(ENV_LIVE_FLAG)
        os.environ[ENV_LIVE_FLAG] = "1"
        try:
            self.assertTrue(is_live_enabled())
        finally:
            if prev is None:
                del os.environ[ENV_LIVE_FLAG]
            else:
                os.environ[ENV_LIVE_FLAG] = prev


# ─────────────────────────────────────────────────────────────────
# Constants are sane
# ─────────────────────────────────────────────────────────────────

class ConstantsTest(unittest.TestCase):
    def test_hard_floor_matches_dispatcher(self):
        # attention-cue-dispatcher.js uses HARD_FLOOR_MS = 25 * 1000.
        # If these drift apart, Phase 3 visual cue + Phase 4 ladder
        # will disagree about when "narrator's space" ends.
        self.assertEqual(HARD_FLOOR_MS, 25_000)

    def test_cold_start_threshold_is_ten(self):
        self.assertEqual(COLD_START_THRESHOLD, 10)

    def test_window_size_is_thirty(self):
        self.assertEqual(WINDOW_SIZE, 30)

    def test_wo10c_fallback_matches_spec(self):
        self.assertEqual(WO_10C_TIER1_MS, 120_000)
        self.assertEqual(WO_10C_TIER2_MS, 300_000)
        self.assertEqual(WO_10C_TIER3_MS, 600_000)

    def test_prompt_weights_locked(self):
        self.assertEqual(PROMPT_WEIGHTS, ("low", "med", "high"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
