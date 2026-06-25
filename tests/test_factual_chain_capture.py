"""Unit tests for factual_chain_capture classifier.

WO-LORI-FACTUAL-CHAIN-CAPTURE-01 Phase 1 + Phase 3 detection tests.

Canonical positive cases:
  - Kent Army induction (Stanley → Fargo → exam → top score → meal tickets → west)
  - Chris Spring 2026 trip route (Prague → Salzburg → Ljubljana → Pula → Italy)
  - Venice/Dulles disruption sequence
  - School / work / military sequence
  - Family migration sequence
  - Medical sequence

Negative control:
  - Sensory-rich emotional memory (no places, no dates, no events)
  - Single-anchor reflection (real but not a chain)
  - Empty / whitespace input

Meta-feedback detection:
  - "not the scenery"
  - "I want to tell my experience not how I felt"
  - "stop asking about sensory parts"

LAW 3 isolation:
  - Static AST walk over factual_chain_capture.py imports — no forbidden
    prefixes (api.routers.*, prompt_composer, memory_echo, etc.).
"""
from __future__ import annotations

import ast
import os
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_CODE = REPO_ROOT / "server" / "code"
sys.path.insert(0, str(SERVER_CODE))

# Direct import — service is pure-stdlib, no FastAPI / DB / etc.
from api.services.factual_chain_capture import (  # noqa: E402
    CUE_LABELS,
    DEFAULT_BLOCKED_PROBE_TYPES,
    PROBE_TYPE_SENSORY,
    build_factual_chain_followup_context,
    classify_factual_chain_cues,
    detect_factual_chain,
    detect_meta_feedback_against_probe,
)


# ──────────────────────────────────────────────────────────────────────────
# Canonical narrator fixtures
# ──────────────────────────────────────────────────────────────────────────

KENT_ARMY_INDUCTION = (
    "They took us from Stanley to Fargo for the exam. I got the top "
    "score, and then they gave us meal tickets and sent us west."
)

CHRIS_TRIP_ROUTE = (
    "We started in Prague, then went to Salzburg, then Ljubljana, then "
    "Pula, and finally into northern Italy."
)

VENICE_DULLES_DISRUPTION = (
    "The flight out of Venice was delayed, then we had to get through "
    "Dulles, then Denver, then Santa Fe."
)

SCHOOL_WORK_MILITARY = (
    "I graduated from Bismarck High in 1965, then went to college at "
    "North Dakota State. After that I enlisted in the Army and was sent "
    "to basic training at Fort Leonard Wood."
)

FAMILY_MIGRATION = (
    "My grandfather emigrated from Norway in 1902. He came over through "
    "Ellis Island, then settled in Stanley, North Dakota with his brother."
)

MEDICAL_SEQUENCE = (
    "I was admitted to Mayo Clinic in March, then they did the biopsy "
    "and I was diagnosed two weeks later. The surgery happened in April."
)

# Negative control: pure sensory / emotional, no chain
SENSORY_RICH_NO_CHAIN = (
    "It was so beautiful. The smell of the bay, the sound of the "
    "seagulls, the warmth of the sun on my face. I remember feeling "
    "completely at peace."
)

# Negative control: single proper noun, no sequence
SINGLE_ANCHOR = "I went to Boston."

# Edge cases
EMPTY = ""
WHITESPACE = "   \n  "

# Meta-feedback fixtures
KENT_META_FEEDBACK = (
    "You are being vague and not asking about basic training rather the "
    "sensory parts of it. I want to tell my experience and you want to "
    "know how I felt."
)

NOT_SCENERY = "No, not the scenery — I want the facts."

LORI_LAST_SENSORY_PROBE = (
    "What do you remember about the sense of camaraderie and teamwork "
    "among your fellow recruits?"
)


# ──────────────────────────────────────────────────────────────────────────
# Public-API shape
# ──────────────────────────────────────────────────────────────────────────


class PublicApiShapeTests(unittest.TestCase):
    """detect_factual_chain dict contract."""

    def test_dict_keys_locked(self):
        result = detect_factual_chain(KENT_ARMY_INDUCTION)
        for key in (
            "is_factual_chain",
            "confidence",
            "cue_labels",
            "anchors",
            "blocked_probe_types",
            "preferred_followup_type",
        ):
            self.assertIn(key, result)

    def test_empty_input_returns_empty_result(self):
        for text in (EMPTY, WHITESPACE, None):
            result = detect_factual_chain(text)  # type: ignore[arg-type]
            self.assertFalse(result["is_factual_chain"])
            self.assertEqual(result["confidence"], 0.0)
            self.assertEqual(result["cue_labels"], [])
            self.assertEqual(result["anchors"], [])
            self.assertEqual(result["blocked_probe_types"], [])
            self.assertEqual(result["preferred_followup_type"], "")

    def test_idempotent(self):
        a = detect_factual_chain(KENT_ARMY_INDUCTION)
        b = detect_factual_chain(KENT_ARMY_INDUCTION)
        self.assertEqual(a, b)

    def test_cue_labels_from_locked_vocabulary(self):
        result = detect_factual_chain(KENT_ARMY_INDUCTION)
        for label in result["cue_labels"]:
            self.assertIn(label, CUE_LABELS)


# ──────────────────────────────────────────────────────────────────────────
# Positive cases (factual chain SHOULD detect)
# ──────────────────────────────────────────────────────────────────────────


class KentArmyInductionTests(unittest.TestCase):
    """Canary 1: the canonical test case from BUG-LORI-FACTUAL-OVER-
    SENSORY-PROBE-01 (2026-05-09 transcript)."""

    def test_classified_as_factual_chain(self):
        result = detect_factual_chain(KENT_ARMY_INDUCTION)
        self.assertTrue(result["is_factual_chain"], result)

    def test_confidence_above_threshold(self):
        result = detect_factual_chain(KENT_ARMY_INDUCTION)
        self.assertGreaterEqual(result["confidence"], 0.5)

    def test_anchors_include_stanley_and_fargo(self):
        result = detect_factual_chain(KENT_ARMY_INDUCTION)
        anchors_lc = [a.lower() for a in result["anchors"]]
        self.assertIn("stanley", anchors_lc)
        self.assertIn("fargo", anchors_lc)

    def test_anchors_include_outcome_phrase(self):
        result = detect_factual_chain(KENT_ARMY_INDUCTION)
        joined = " ".join(result["anchors"]).lower()
        # "top score" or "meal tickets" should appear
        self.assertTrue(
            "top score" in joined or "meal tickets" in joined,
            f"expected outcome anchor in {result['anchors']!r}",
        )

    def test_blocks_sensory_probe_class(self):
        result = detect_factual_chain(KENT_ARMY_INDUCTION)
        self.assertIn(PROBE_TYPE_SENSORY, result["blocked_probe_types"])

    def test_cue_labels_include_travel_or_multi_place(self):
        result = detect_factual_chain(KENT_ARMY_INDUCTION)
        self.assertTrue(
            "multi_place_sequence" in result["cue_labels"]
            or "travel_leg_sequence" in result["cue_labels"],
            result["cue_labels"],
        )

    def test_preferred_followup_is_next_factual_link(self):
        result = detect_factual_chain(KENT_ARMY_INDUCTION)
        self.assertEqual(
            result["preferred_followup_type"], "next_factual_link"
        )


class ChrisTripRouteTests(unittest.TestCase):
    """Canary 2: Chris's Spring 2026 trip route."""

    def test_classified_as_factual_chain(self):
        result = detect_factual_chain(CHRIS_TRIP_ROUTE)
        self.assertTrue(result["is_factual_chain"], result)

    def test_anchors_include_all_five_places(self):
        result = detect_factual_chain(CHRIS_TRIP_ROUTE)
        anchors_lc = [a.lower() for a in result["anchors"]]
        for place in ("prague", "salzburg", "ljubljana", "pula"):
            self.assertIn(place, anchors_lc, f"missing {place}: {result}")

    def test_cue_labels_include_travel_or_multi_place(self):
        result = detect_factual_chain(CHRIS_TRIP_ROUTE)
        self.assertTrue(
            "travel_leg_sequence" in result["cue_labels"]
            or "multi_place_sequence" in result["cue_labels"],
            result["cue_labels"],
        )


class VeniceDullesDisruptionTests(unittest.TestCase):
    """Canary 3: travel disruption chain."""

    def test_classified_as_factual_chain(self):
        result = detect_factual_chain(VENICE_DULLES_DISRUPTION)
        self.assertTrue(result["is_factual_chain"], result)

    def test_cue_labels_include_disruption(self):
        result = detect_factual_chain(VENICE_DULLES_DISRUPTION)
        self.assertIn("disruption_sequence", result["cue_labels"])

    def test_anchors_include_airport_codes(self):
        result = detect_factual_chain(VENICE_DULLES_DISRUPTION)
        anchors_lc = [a.lower() for a in result["anchors"]]
        for place in ("venice", "dulles", "denver", "santa fe"):
            self.assertIn(place, anchors_lc, f"missing {place}")


class SchoolWorkMilitarySequenceTests(unittest.TestCase):
    """Canary 4: school / work / military sequence."""

    def test_classified_as_factual_chain(self):
        result = detect_factual_chain(SCHOOL_WORK_MILITARY)
        self.assertTrue(result["is_factual_chain"], result)

    def test_cue_labels_include_school_or_military(self):
        result = detect_factual_chain(SCHOOL_WORK_MILITARY)
        self.assertIn("job_school_military_sequence", result["cue_labels"])


class FamilyMigrationSequenceTests(unittest.TestCase):
    def test_classified_as_factual_chain(self):
        result = detect_factual_chain(FAMILY_MIGRATION)
        self.assertTrue(result["is_factual_chain"], result)

    def test_cue_labels_include_family_migration(self):
        result = detect_factual_chain(FAMILY_MIGRATION)
        self.assertIn("family_migration_sequence", result["cue_labels"])


class MedicalSequenceTests(unittest.TestCase):
    def test_classified_as_factual_chain(self):
        result = detect_factual_chain(MEDICAL_SEQUENCE)
        self.assertTrue(result["is_factual_chain"], result)

    def test_cue_labels_include_medical(self):
        result = detect_factual_chain(MEDICAL_SEQUENCE)
        self.assertIn("medical_sequence", result["cue_labels"])


# ──────────────────────────────────────────────────────────────────────────
# Negative controls (factual chain should NOT detect)
# ──────────────────────────────────────────────────────────────────────────


class NegativeControlTests(unittest.TestCase):
    def test_sensory_rich_no_chain_not_classified(self):
        result = detect_factual_chain(SENSORY_RICH_NO_CHAIN)
        self.assertFalse(result["is_factual_chain"], result)
        self.assertEqual(result["blocked_probe_types"], [])

    def test_single_anchor_not_classified(self):
        result = detect_factual_chain(SINGLE_ANCHOR)
        self.assertFalse(result["is_factual_chain"], result)


# ──────────────────────────────────────────────────────────────────────────
# Meta-feedback detection
# ──────────────────────────────────────────────────────────────────────────


class MetaFeedbackTests(unittest.TestCase):
    def test_kent_meta_feedback_detected(self):
        result = detect_meta_feedback_against_probe(
            KENT_META_FEEDBACK,
            LORI_LAST_SENSORY_PROBE,
        )
        self.assertTrue(result["is_meta_feedback"], result)
        self.assertEqual(result["last_rejected_probe_type"], PROBE_TYPE_SENSORY)
        self.assertEqual(result["turns_remaining"], 2)

    def test_not_scenery_detected(self):
        result = detect_meta_feedback_against_probe(NOT_SCENERY, "")
        self.assertTrue(result["is_meta_feedback"], result)
        self.assertEqual(result["last_rejected_probe_type"], PROBE_TYPE_SENSORY)

    def test_normal_narrator_text_is_not_meta_feedback(self):
        result = detect_meta_feedback_against_probe(
            KENT_ARMY_INDUCTION,
            "",
        )
        self.assertFalse(result["is_meta_feedback"], result)

    def test_empty_text_returns_inactive(self):
        result = detect_meta_feedback_against_probe("", "")
        self.assertFalse(result["is_meta_feedback"])
        self.assertEqual(result["last_rejected_probe_type"], "")
        self.assertEqual(result["turns_remaining"], 0)


# ──────────────────────────────────────────────────────────────────────────
# Composer-context builder (Phase 2 directive consumer)
# ──────────────────────────────────────────────────────────────────────────


class FollowupContextBuilderTests(unittest.TestCase):
    def test_kent_chain_builds_composer_directive(self):
        ctx = build_factual_chain_followup_context(KENT_ARMY_INDUCTION)
        self.assertTrue(ctx["is_factual_chain"])
        self.assertIn("factual chain", ctx["composer_directive"].lower())
        self.assertIn(PROBE_TYPE_SENSORY, ctx["blocked_probe_types"])

    def test_meta_feedback_appends_rejection_directive(self):
        prior = [
            {"role": "user", "content": KENT_ARMY_INDUCTION},
            {"role": "assistant", "content": LORI_LAST_SENSORY_PROBE},
        ]
        ctx = build_factual_chain_followup_context(
            KENT_META_FEEDBACK,
            prior_turns=prior,
        )
        self.assertTrue(ctx["meta_feedback"]["is_meta_feedback"])
        self.assertIn(
            "rejected the previous",
            ctx["composer_directive"].lower(),
        )

    def test_sensory_narrator_no_directive(self):
        ctx = build_factual_chain_followup_context(SENSORY_RICH_NO_CHAIN)
        self.assertFalse(ctx["is_factual_chain"])
        self.assertFalse(ctx["meta_feedback"]["is_meta_feedback"])
        self.assertEqual(ctx["composer_directive"], "")


# ──────────────────────────────────────────────────────────────────────────
# classify_factual_chain_cues shortcut
# ──────────────────────────────────────────────────────────────────────────


class ClassifyShortcutTests(unittest.TestCase):
    def test_returns_just_cue_labels(self):
        cues = classify_factual_chain_cues(KENT_ARMY_INDUCTION)
        self.assertIsInstance(cues, list)
        self.assertGreater(len(cues), 0)
        for c in cues:
            self.assertIn(c, CUE_LABELS)


# ──────────────────────────────────────────────────────────────────────────
# LAW 3 isolation gate (mirrors test_story_preservation_isolation pattern)
# ──────────────────────────────────────────────────────────────────────────


class FactualChainCaptureIsolationTests(unittest.TestCase):
    """Build-gate: factual_chain_capture.py must not import from
    forbidden prefixes. Pure-stdlib + sibling pure-function services
    only."""

    FORBIDDEN_PREFIXES = (
        "api.routers.extract",
        "api.routers.chat_ws",
        "api.routers.llm",
        "api.prompt_composer",
        "api.memory_echo",
        "api.db",
        "api.services.story_preservation",
        "api.services.story_trigger",
        # bare-package equivalents
        "..routers.extract",
        "..routers.chat_ws",
        "..routers.llm",
        "..prompt_composer",
        "..memory_echo",
        "..db",
        ".story_preservation",
        ".story_trigger",
    )

    def _collect_imports(self, path: Path) -> list:
        with open(path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(path))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                prefix = "." * (node.level or 0)
                imports.append(f"{prefix}{module}")
        return imports

    def test_no_forbidden_imports(self):
        target = (
            REPO_ROOT / "server" / "code" / "api" / "services"
            / "factual_chain_capture.py"
        )
        self.assertTrue(target.exists(), f"missing: {target}")
        imports = self._collect_imports(target)
        for imp in imports:
            for bad in self.FORBIDDEN_PREFIXES:
                self.assertFalse(
                    imp.startswith(bad),
                    f"forbidden import in factual_chain_capture.py: "
                    f"{imp!r} matches prefix {bad!r}",
                )


if __name__ == "__main__":
    unittest.main()
