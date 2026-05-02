"""WO-EX-UTTERANCE-FRAME-01 Phase 0-2 — unit tests for the frame builder.

═══════════════════════════════════════════════════════════════════════
  These tests are the safety gate. Every fixture in
  tests/fixtures/utterance_frame_cases.json is exercised here as a
  partial-shape assertion (NOT byte-equality). The frame is allowed to
  fill more slots than the test asserts; it MUST NOT contradict an
  assertion.

  Why partial shape, not byte-equality:
    - The frame is a deterministic interpretation, but anchor-extraction
      heuristics can legitimately surface extra slots (object words,
      bare-noun place fallbacks) without breaking downstream consumers.
    - Byte-locked tests would freeze v1's exact regex set and slow down
      the natural growth of the canon (kinship aliases, event verbs,
      place prepositions) without catching real regressions.
    - The shape contract is what consumers depend on: subject_class,
      event_class, candidate_fieldPaths emission, negation/uncertainty
      flags. Lock that surface; let the rest evolve.

  What this file tests:
    1. Public API exists and returns the right shape.
    2. Every fixture case parses without raising.
    3. Per-fixture assertions hold (clause count, subject/event class,
       place, candidate_fieldPaths inclusion, negation, uncertainty,
       confidence).
    4. Edge cases the fixtures can't cover cleanly (empty input,
       whitespace, idempotency, no-invented-facts).
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

# Add server/code/ to the path so `import api.services.utterance_frame`
# works regardless of how the test is invoked.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api.services.utterance_frame import (  # noqa: E402
    build_frame,
    Clause,
    NarratorUtteranceFrame,
    SUBJECT_SELF,
    SUBJECT_PARENT,
    SUBJECT_SIBLING,
    SUBJECT_SPOUSE,
    SUBJECT_CHILD,
    SUBJECT_GRANDPARENT,
    SUBJECT_GREAT_GRANDPARENT,
    SUBJECT_PET,
    SUBJECT_UNKNOWN,
    EVENT_BIRTH,
    EVENT_DEATH,
    EVENT_MOVE,
    EVENT_WORK,
    EVENT_MARRIAGE,
    EVENT_MILITARY,
    EVENT_EDUCATION,
    EVENT_ILLNESS,
    EVENT_UNKNOWN,
    CONFIDENCE_HIGH,
    CONFIDENCE_PARTIAL,
    CONFIDENCE_LOW,
)


_FIXTURES_PATH = _REPO_ROOT / "tests" / "fixtures" / "utterance_frame_cases.json"


def _load_fixtures():
    if not _FIXTURES_PATH.is_file():
        raise FileNotFoundError(
            f"fixture file missing: {_FIXTURES_PATH}\n"
            "Phase 0-2 requires both the fixture file and the test file."
        )
    with _FIXTURES_PATH.open(encoding="utf-8") as fp:
        data = json.load(fp)
    return data["cases"]


# ─── Public API shape ────────────────────────────────────────────────

class PublicApiShapeTest(unittest.TestCase):
    """The public API surface — the contract downstream consumers
    depend on. If anything here breaks, every consumer must adapt."""

    def test_build_frame_returns_frame_object(self):
        f = build_frame("Hello.")
        self.assertIsInstance(f, NarratorUtteranceFrame)

    def test_frame_to_dict_returns_stable_keys(self):
        f = build_frame("Hello.")
        d = f.to_dict()
        # Locked keys — adding new keys is fine; renaming or removing
        # any of these is a breaking change for consumers.
        self.assertIn("raw_text", d)
        self.assertIn("clauses", d)
        self.assertIn("unbound_remainder", d)
        self.assertIn("parse_confidence", d)

    def test_clause_to_dict_has_locked_keys(self):
        f = build_frame("My dad was born in Stanley.")
        self.assertGreaterEqual(len(f.clauses), 1)
        c0 = f.to_dict()["clauses"][0]
        for k in (
            "raw", "who", "who_canonical", "who_subject_class",
            "event", "event_class", "place", "time", "object",
            "feeling", "negation", "uncertainty",
            "candidate_fieldPaths",
        ):
            self.assertIn(k, c0, f"clause dict missing key: {k}")

    def test_empty_input_returns_low_confidence_empty_frame(self):
        for txt in ("", "   ", "\n\t  "):
            f = build_frame(txt)
            self.assertEqual(f.parse_confidence, CONFIDENCE_LOW)
            self.assertEqual(len(f.clauses), 0)

    def test_none_input_does_not_raise(self):
        # Defensive — chat_ws.py may pass None on degenerate paths.
        f = build_frame(None)  # type: ignore[arg-type]
        self.assertEqual(f.parse_confidence, CONFIDENCE_LOW)
        self.assertEqual(len(f.clauses), 0)


# ─── Determinism + idempotency ──────────────────────────────────────

class DeterminismTest(unittest.TestCase):
    """Same input always yields the same output. Same input parsed
    twice through to_dict() yields identical dicts. The frame is a
    pure function."""

    SAMPLES = [
        "My dad was born in Stanley, and I was born in Stanley too.",
        "I served in the Navy during the war.",
        "I don't remember where we lived then.",
        "Thank you.",
        "",
    ]

    def test_two_calls_same_input_yield_equal_dicts(self):
        for s in self.SAMPLES:
            d1 = build_frame(s).to_dict()
            d2 = build_frame(s).to_dict()
            self.assertEqual(d1, d2, f"non-deterministic on input: {s!r}")


# ─── Per-fixture assertions ─────────────────────────────────────────

class FixtureCasesTest(unittest.TestCase):
    """Every fixture in utterance_frame_cases.json is exercised as a
    partial-shape assertion. The shape of each fixture is described
    inside the fixture itself; this test reads the fixture and applies
    the assertions."""

    @classmethod
    def setUpClass(cls):
        cls.cases = _load_fixtures()

    def _assert_clause(self, fixture_id, expected, actual_dict):
        """Apply one fixture clause assertion against an actual clause
        dict. Each key in `expected` is a partial-shape requirement."""
        ctx = f"[{fixture_id}]"
        if "who_subject_class" in expected:
            self.assertEqual(
                actual_dict["who_subject_class"],
                expected["who_subject_class"],
                f"{ctx} who_subject_class mismatch on clause "
                f"{actual_dict['raw']!r}",
            )
        if "who_subject_class_in" in expected:
            self.assertIn(
                actual_dict["who_subject_class"],
                expected["who_subject_class_in"],
                f"{ctx} who_subject_class not in allowed set",
            )
        if "who_canonical" in expected:
            self.assertEqual(
                actual_dict["who_canonical"],
                expected["who_canonical"],
                f"{ctx} who_canonical mismatch",
            )
        if "event_class" in expected:
            self.assertEqual(
                actual_dict["event_class"],
                expected["event_class"],
                f"{ctx} event_class mismatch on clause "
                f"{actual_dict['raw']!r}",
            )
        if "place" in expected:
            self.assertEqual(
                actual_dict["place"],
                expected["place"],
                f"{ctx} place mismatch",
            )
        if "object" in expected:
            self.assertEqual(
                actual_dict["object"],
                expected["object"],
                f"{ctx} object mismatch",
            )
        if "feeling" in expected:
            self.assertEqual(
                actual_dict["feeling"],
                expected["feeling"],
                f"{ctx} feeling mismatch",
            )
        if "negation" in expected:
            self.assertEqual(
                actual_dict["negation"],
                expected["negation"],
                f"{ctx} negation mismatch",
            )
        if "uncertainty" in expected:
            self.assertEqual(
                actual_dict["uncertainty"],
                expected["uncertainty"],
                f"{ctx} uncertainty mismatch",
            )
        if "feeling_present" in expected:
            if expected["feeling_present"]:
                self.assertIsNotNone(
                    actual_dict["feeling"],
                    f"{ctx} expected feeling slot to be filled",
                )
            else:
                self.assertIsNone(
                    actual_dict["feeling"],
                    f"{ctx} expected feeling slot to be empty",
                )
        if "must_include_field_path" in expected:
            self.assertIn(
                expected["must_include_field_path"],
                actual_dict["candidate_fieldPaths"],
                f"{ctx} expected candidate_fieldPaths to include "
                f"{expected['must_include_field_path']!r}; got "
                f"{actual_dict['candidate_fieldPaths']!r}",
            )
        if expected.get("candidate_fieldPaths_must_be_empty"):
            self.assertEqual(
                actual_dict["candidate_fieldPaths"],
                [],
                f"{ctx} candidate_fieldPaths expected empty; got "
                f"{actual_dict['candidate_fieldPaths']!r}",
            )

    def _find_matching_clause(self, fixture_id, expected, clauses):
        """Find a clause in `clauses` that satisfies `expected`. Used
        for `expected_clauses_must_include` — order-independent shape
        match. Returns the matching clause dict or fails the test."""
        for cl in clauses:
            try:
                self._assert_clause(fixture_id, expected, cl)
                return cl
            except AssertionError:
                continue
        self.fail(
            f"[{fixture_id}] no clause in actual frame matches expected "
            f"shape {expected!r}; actual clauses: "
            f"{[c.get('raw') for c in clauses]}"
        )

    def test_all_fixtures(self):
        """Single test that loops every fixture so a regression names
        the fixture id directly. Exits at first failure to keep the
        signal clear."""
        for case in self.cases:
            cid = case["id"]
            text = case["narrator_text"]

            # Parse must not raise.
            try:
                frame = build_frame(text)
            except Exception as e:
                self.fail(f"[{cid}] build_frame raised: {e!r}")

            d = frame.to_dict()

            # Confidence assertions.
            if "expected_confidence" in case:
                self.assertEqual(
                    d["parse_confidence"],
                    case["expected_confidence"],
                    f"[{cid}] expected_confidence "
                    f"{case['expected_confidence']!r}, got "
                    f"{d['parse_confidence']!r}",
                )
            if "expected_confidence_in" in case:
                self.assertIn(
                    d["parse_confidence"],
                    case["expected_confidence_in"],
                    f"[{cid}] expected_confidence_in "
                    f"{case['expected_confidence_in']!r}, got "
                    f"{d['parse_confidence']!r}",
                )

            # Clause-count assertions.
            if "expected_clause_count" in case:
                self.assertEqual(
                    len(d["clauses"]),
                    case["expected_clause_count"],
                    f"[{cid}] expected_clause_count "
                    f"{case['expected_clause_count']}, got "
                    f"{len(d['clauses'])}",
                )
            if "expected_clause_count_min" in case:
                self.assertGreaterEqual(
                    len(d["clauses"]),
                    case["expected_clause_count_min"],
                    f"[{cid}] expected_clause_count_min "
                    f"{case['expected_clause_count_min']}, got "
                    f"{len(d['clauses'])}",
                )

            # Per-clause ordered assertions.
            if "expected_clauses" in case:
                for i, expected_cl in enumerate(case["expected_clauses"]):
                    self.assertLess(
                        i, len(d["clauses"]),
                        f"[{cid}] expected clause #{i} but only "
                        f"{len(d['clauses'])} actual clauses",
                    )
                    self._assert_clause(cid, expected_cl, d["clauses"][i])

            # Per-clause unordered "must include" assertions.
            if "expected_clauses_must_include" in case:
                for expected_cl in case["expected_clauses_must_include"]:
                    self._find_matching_clause(cid, expected_cl, d["clauses"])

            # "must have negation clause" — at least one clause flagged.
            if case.get("must_have_negation_clause"):
                negs = [c for c in d["clauses"] if c["negation"]]
                self.assertGreater(
                    len(negs), 0,
                    f"[{cid}] expected at least one negation clause; "
                    f"got none in {[c['raw'] for c in d['clauses']]}",
                )


# ─── No-invented-facts guard ────────────────────────────────────────

class NoInventedFactsTest(unittest.TestCase):
    """The frame must NOT invent facts. Every place/time/feeling slot
    must be substring-traceable to the narrator text (modulo
    whitespace + case)."""

    SAMPLES = [
        "My dad was born in Stanley, and I was born in Stanley too.",
        "I served in the Navy during the war.",
        "My great-grandfather was born in Hanover.",
        "We got married in 1967.",
    ]

    def test_no_slot_carries_text_not_in_input(self):
        for s in self.SAMPLES:
            f = build_frame(s)
            lower = s.lower()
            for cl in f.clauses:
                for slot_name in ("place", "time", "object", "feeling"):
                    val = getattr(cl, slot_name)
                    if val:
                        self.assertIn(
                            val.lower(),
                            lower,
                            f"slot {slot_name}={val!r} not present in "
                            f"input {s!r} — frame invented content",
                        )


# ─── Subject-class coverage smoke ───────────────────────────────────

class SubjectCoverageSmokeTest(unittest.TestCase):
    """Quick smoke that every public subject class is reachable from
    at least one input — guards against silent regression of one
    subject pattern when a regex is edited."""

    def test_self_subject_reachable(self):
        f = build_frame("I was born in Stanley.")
        self.assertEqual(f.clauses[0].who_subject_class, SUBJECT_SELF)

    def test_parent_subject_reachable(self):
        f = build_frame("My dad worked nights.")
        self.assertEqual(f.clauses[0].who_subject_class, SUBJECT_PARENT)

    def test_sibling_subject_reachable(self):
        f = build_frame("My sister was born in Bismarck.")
        self.assertEqual(f.clauses[0].who_subject_class, SUBJECT_SIBLING)

    def test_spouse_subject_reachable(self):
        f = build_frame("My wife was born in Spokane.")
        self.assertEqual(f.clauses[0].who_subject_class, SUBJECT_SPOUSE)

    def test_child_subject_reachable(self):
        f = build_frame("My daughter was born in Mandan.")
        self.assertEqual(f.clauses[0].who_subject_class, SUBJECT_CHILD)

    def test_grandparent_subject_reachable(self):
        f = build_frame("My grandmother was born in Oslo.")
        self.assertEqual(
            f.clauses[0].who_subject_class, SUBJECT_GRANDPARENT,
        )

    def test_great_grandparent_subject_reachable(self):
        f = build_frame("My great-grandfather was born in Hanover.")
        self.assertEqual(
            f.clauses[0].who_subject_class, SUBJECT_GREAT_GRANDPARENT,
        )

    def test_pet_subject_reachable(self):
        f = build_frame("My dog Skip was a good boy.")
        self.assertEqual(f.clauses[0].who_subject_class, SUBJECT_PET)


if __name__ == "__main__":
    unittest.main(verbosity=2)
