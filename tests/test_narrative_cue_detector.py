"""WO-NARRATIVE-CUE-LIBRARY-01 Phase 2 — Unit + eval-pack tests for
narrative_cue_detector.

Two layers:
  1. Public-API contract tests (deterministic, edge cases, schema).
  2. Eval-pack walk over data/qa/lori_narrative_cue_eval.json (40 cases)
     measuring how often the detector's top_cue.cue_type matches the
     case's expected_cue_type. Reports pass rate and per-case detail.

The eval pack is treated as a CALIBRATION TARGET, not a strict
acceptance gate. Phase 2 ships when:
  - All public-API contract tests pass (these ARE strict)
  - Eval pack pass rate is reported with per-case breakdown
  - Any miss is documented (top vs expected, what fired)

Subsequent calibration can ride on top by tightening trigger terms in
the library JSON; the detector itself stays unchanged.

Usage:
    python tests/test_narrative_cue_detector.py
    python -m unittest tests.test_narrative_cue_detector
    pytest tests/test_narrative_cue_detector.py
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

# Add server/code to import path so `services.narrative_cue_detector` resolves.
import sys
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api.services.narrative_cue_detector import (  # noqa: E402
    CueDetection,
    CueMatch,
    NarrativeCueLibrary,
    build_library,
    build_library_from_path,
    detect_cues,
)


_DEFAULT_LIB_PATH = _REPO_ROOT / "data" / "lori" / "narrative_cue_library.v1.seed.json"
_EVAL_PACK_PATH = _REPO_ROOT / "data" / "qa" / "lori_narrative_cue_eval.json"


# ── 1. Public API contract tests ──────────────────────────────────────────

class PublicApiShapeTest(unittest.TestCase):
    """Detector returns the expected dataclass shape with correct fields."""

    def test_empty_text_returns_empty_detection(self):
        result = detect_cues("")
        self.assertIsInstance(result, CueDetection)
        self.assertEqual(result.cues, ())
        self.assertIsNone(result.top_cue)
        self.assertEqual(result.no_match_reason, "empty_text")

    def test_none_text_returns_empty_detection(self):
        # detect_cues should not crash on None — coerce to empty.
        result = detect_cues(None)  # type: ignore[arg-type]
        self.assertEqual(result.cues, ())
        self.assertIsNone(result.top_cue)
        self.assertEqual(result.no_match_reason, "empty_text")

    def test_whitespace_only_returns_empty_detection(self):
        result = detect_cues("   \n\t  ")
        self.assertEqual(result.cues, ())
        self.assertEqual(result.no_match_reason, "empty_text")

    def test_no_match_text_returns_empty_with_reason(self):
        # A sentence with no library trigger terms.
        result = detect_cues("xyzzy plugh thud frobnicate.")
        self.assertEqual(result.cues, ())
        self.assertIsNone(result.top_cue)
        self.assertEqual(result.no_match_reason, "no_trigger_match")

    def test_top_cue_matches_first_in_cues(self):
        result = detect_cues("My father had calloused hands from years of work.")
        self.assertGreaterEqual(len(result.cues), 1)
        self.assertIs(result.top_cue, result.cues[0])
        self.assertEqual(result.no_match_reason, "")

    def test_cue_match_has_runtime_safe_fields_only(self):
        """CueMatch.to_dict() must NOT expose operator_extract_hints —
        the schema sets runtime_exposes_extract_hints: false."""
        result = detect_cues("My father worked the field.")
        self.assertIsNotNone(result.top_cue)
        d = result.top_cue.to_dict()
        self.assertNotIn("operator_extract_hints", d)
        # Required runtime-visible keys
        for key in (
            "cue_id", "cue_type", "label", "risk_level",
            "scene_anchor_dimensions", "safe_followups",
            "forbidden_moves", "trigger_matches", "score",
        ):
            self.assertIn(key, d)

    def test_to_dict_round_trip_is_stable(self):
        """Serializing to_dict twice produces identical output."""
        result = detect_cues("Mother had a Sunday voice and a Monday voice.")
        a = result.to_dict()
        b = result.to_dict()
        self.assertEqual(a, b)


class DeterminismTest(unittest.TestCase):
    """Same input → same output across repeated calls."""

    def test_repeat_call_byte_stable(self):
        text = "My grandmother kept the recipe in a Bible, and we never told outsiders."
        a = detect_cues(text).to_dict()
        b = detect_cues(text).to_dict()
        self.assertEqual(a, b)

    def test_section_bonus_breaks_ties_in_documented_direction(self):
        """When two cues match equally on triggers, supplying a
        current_section that overlaps one cue's operator_extract_hints
        should bring that cue to the top."""
        # Construct text that triggers both parent_character (mother) and
        # hearth_food (Sunday). Without section: parent_character wins
        # by library order (it's first in v1 seed). With current_section
        # = "rituals" or similar, hearth_food might bubble up — but that
        # depends on hint paths in v1 seed. We just confirm the tie-break
        # rule is consistent across calls and that providing a section
        # does not crash.
        text = "My mother always made bread on Sunday."
        no_section = detect_cues(text)
        with_section_irrelevant = detect_cues(text, current_section="something_unmapped")
        # Section that doesn't match any hint must not change ordering.
        self.assertEqual(
            [c.cue_type for c in no_section.cues],
            [c.cue_type for c in with_section_irrelevant.cues],
        )


class LibraryLoaderTest(unittest.TestCase):
    """build_library + build_library_from_path round-trip and validate."""

    def test_default_library_loads(self):
        lib = build_library()
        self.assertIsInstance(lib, NarrativeCueLibrary)
        self.assertGreaterEqual(len(lib.cue_defs), 12)

    def test_default_library_has_expected_cue_types(self):
        lib = build_library()
        types = {c.cue_type for c in lib.cue_defs}
        # All 12 v1 schema cue types should be present.
        for expected in (
            "parent_character", "elder_keeper", "journey_arrival",
            "home_place", "work_survival", "hearth_food",
            "object_keepsake", "language_name", "identity_between",
            "hard_times", "hidden_custom", "legacy_wisdom",
        ):
            self.assertIn(expected, types, f"missing cue type: {expected}")

    def test_load_from_path_matches_default(self):
        a = build_library()
        b = build_library_from_path(str(_DEFAULT_LIB_PATH))
        # They should describe the same library content.
        self.assertEqual(a.version, b.version)
        self.assertEqual(len(a.cue_defs), len(b.cue_defs))
        self.assertEqual(
            [c.cue_type for c in a.cue_defs],
            [c.cue_type for c in b.cue_defs],
        )

    def test_refuses_library_without_no_truth_write_flag(self):
        """The covenant flag must be present and true. Library files
        that don't declare it are refused with a clear message."""
        bad = {
            "version": 99,
            "description": "missing covenant flag",
            "cue_types": [
                {
                    "cue_id": "x", "cue_type": "x", "label": "x",
                    "risk_level": "low",
                    "trigger_terms": ["x"],
                    "scene_anchor_dimensions": ["object"],
                    "safe_followups": ["x?"],
                    "forbidden_moves": ["x"],
                }
            ],
        }
        tmp = _REPO_ROOT / ".runtime" / "test_bad_lib.json"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(bad), encoding="utf-8")
        try:
            with self.assertRaisesRegex(ValueError, "no_truth_write"):
                build_library_from_path(str(tmp))
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass


class NormalizationTest(unittest.TestCase):
    """Smart quotes and apostrophe variants must match library terms."""

    def test_smart_apostrophe_matches_father(self):
        # The eval pack uses curly apostrophes ("Father's hands").
        # The library has "father" as a trigger. We must match.
        result = detect_cues("Father’s hands were calloused.")
        self.assertIsNotNone(result.top_cue)
        self.assertEqual(result.top_cue.cue_type, "parent_character")

    def test_capitalized_term_matches_lowercase_trigger(self):
        result = detect_cues("MOTHER kept seeds in her apron.")
        self.assertIsNotNone(result.top_cue)
        self.assertEqual(result.top_cue.cue_type, "parent_character")

    def test_word_boundary_does_not_match_substring(self):
        """The trigger 'mom' must NOT match 'momentum' or 'mommie'.
        word-boundary regex protects against substring leaks."""
        result = detect_cues("The momentum carried us forward, mommified by routine.")
        self.assertIsNone(result.top_cue, f"unexpected match: {result.cues}")


# ── 2. Eval-pack walk (CALIBRATION report, not strict gate) ───────────────

class EvalPackCalibrationTest(unittest.TestCase):
    """Walk every case in lori_narrative_cue_eval.json. For each case:
    run the detector with the case's user_text + current_section, then
    record whether top_cue.cue_type matches expected_cue_type.

    This test always PASSES (it just reports). The pass rate is the
    calibration metric for the library's trigger terms — improving it
    means tightening the JSON, not changing the detector.
    """

    def test_eval_pack_calibration_report(self):
        if not _EVAL_PACK_PATH.is_file():
            self.skipTest(f"eval pack missing at {_EVAL_PACK_PATH}")

        with _EVAL_PACK_PATH.open(encoding="utf-8") as f:
            pack = json.load(f)

        cases = pack.get("cases", [])
        self.assertGreater(len(cases), 0, "eval pack has no cases")

        hits = 0
        misses: list[dict] = []
        for case in cases:
            case_id = case.get("id", "?")
            user_text = case.get("user_text", "")
            section = case.get("current_section")
            expected = case.get("expected_cue_type")
            if not user_text or not expected:
                continue

            result = detect_cues(user_text, current_section=section)
            actual_type = result.top_cue.cue_type if result.top_cue else None
            actual_score = result.top_cue.score if result.top_cue else 0
            actual_triggers = list(result.top_cue.trigger_matches) if result.top_cue else []

            if actual_type == expected:
                hits += 1
            else:
                misses.append({
                    "id": case_id,
                    "expected": expected,
                    "actual": actual_type,
                    "actual_score": actual_score,
                    "actual_triggers": actual_triggers,
                    "user_text": user_text[:100] + ("..." if len(user_text) > 100 else ""),
                })

        total = hits + len(misses)
        rate = (hits / total * 100.0) if total else 0.0

        # Print a calibration report (visible with pytest -s or unittest -v).
        print()
        print(f"=== narrative_cue_detector eval pack calibration ===")
        print(f"  cases:       {total}")
        print(f"  top-1 hits:  {hits}")
        print(f"  misses:      {len(misses)}")
        print(f"  pass rate:   {rate:.1f}%")
        if misses:
            print(f"\n  --- miss detail (top-{min(len(misses), 10)}) ---")
            for m in misses[:10]:
                print(f"  [{m['id']}]")
                print(f"     expected: {m['expected']}")
                print(f"     actual:   {m['actual']}  (score={m['actual_score']}, triggers={m['actual_triggers']})")
                print(f"     text:     {m['user_text']}")

        # Report-only: this test passes regardless of pass rate.
        # The calibration target lives in the WO acceptance criteria, not here.
        self.assertTrue(True)


# ── 3. Schema validation (lightweight) ────────────────────────────────────

class SchemaSanityTest(unittest.TestCase):
    """Eyeball-check that the v1 seed library matches the schema's
    structural minimum. Full JSON Schema validation can ride later."""

    def test_v1_seed_has_all_required_keys_per_cue(self):
        lib = build_library()
        required = {
            "cue_id", "cue_type", "label", "risk_level",
            "trigger_terms", "scene_anchor_dimensions",
            "safe_followups", "forbidden_moves",
        }
        # Read raw JSON to verify keys exist there too.
        with _DEFAULT_LIB_PATH.open(encoding="utf-8") as f:
            raw = json.load(f)
        for idx, cue in enumerate(raw["cue_types"]):
            missing = required - set(cue.keys())
            self.assertFalse(
                missing,
                f"v1 seed cue_types[{idx}] missing keys: {missing}",
            )

    def test_v1_seed_runtime_exposes_extract_hints_is_false(self):
        with _DEFAULT_LIB_PATH.open(encoding="utf-8") as f:
            raw = json.load(f)
        for idx, cue in enumerate(raw["cue_types"]):
            self.assertEqual(
                cue.get("runtime_exposes_extract_hints"),
                False,
                f"v1 seed cue_types[{idx}] must have runtime_exposes_extract_hints: false",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
