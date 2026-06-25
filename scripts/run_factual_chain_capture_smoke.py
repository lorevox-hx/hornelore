#!/usr/bin/env python3
"""Smoke harness for WO-LORI-FACTUAL-CHAIN-CAPTURE-01.

Runs the deterministic classifier (factual_chain_capture.detect_factual_
chain) against the canonical canary set from the WO spec. No live API
required — this is a pure-stdlib classifier smoke.

Usage:
    cd /mnt/c/Users/chris/hornelore
    python3 scripts/run_factual_chain_capture_smoke.py

Exit code 0 = GREEN, 1 = RED.

Adding a case: append a dict to CASES with:
    id              str — short identifier
    narrator        str — the narrator turn text
    must_match      bool — should classifier mark as factual chain
    required_cues   list[str] — at least one of these must be in cue_labels
                                 (empty list = no cue assertion)
    required_anchors list[str] — substrings (case-insensitive) that must
                                 appear in the anchors list (empty list = no
                                 anchor assertion)
    forbid_cues     list[str] — these cues must NOT appear (empty = no check)
    note            str — human-readable description
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_CODE = REPO_ROOT / "server" / "code"
sys.path.insert(0, str(SERVER_CODE))

from api.services.factual_chain_capture import (  # noqa: E402
    build_factual_chain_followup_context,
    detect_factual_chain,
    detect_meta_feedback_against_probe,
)


# ──────────────────────────────────────────────────────────────────────────
# Canonical canary set (from WO-LORI-FACTUAL-CHAIN-CAPTURE-01 §Phase 5)
# ──────────────────────────────────────────────────────────────────────────

CASES: List[Dict[str, Any]] = [
    {
        "id": "kent_army_induction_chain",
        "narrator": (
            "They took us from Stanley to Fargo for the exam. "
            "I got the top score, and then they gave us meal tickets "
            "and sent us west."
        ),
        "must_match": True,
        "required_cues": ["multi_place_sequence", "travel_leg_sequence"],
        "required_anchors": ["stanley", "fargo"],
        "forbid_cues": [],
        "note": "Kent canonical: BUG-LORI-FACTUAL-OVER-SENSORY-PROBE-01 evidence",
    },
    {
        "id": "chris_trip_route_chain",
        "narrator": (
            "We started in Prague, then went to Salzburg, then Ljubljana, "
            "then Pula, and finally into northern Italy."
        ),
        "must_match": True,
        "required_cues": ["multi_place_sequence", "travel_leg_sequence"],
        "required_anchors": ["prague", "salzburg", "ljubljana", "pula"],
        "forbid_cues": [],
        "note": "Chris Spring 2026 trip route",
    },
    {
        "id": "venice_dulles_disruption_chain",
        "narrator": (
            "The flight out of Venice was delayed, then we had to get "
            "through Dulles, then Denver, then Santa Fe."
        ),
        "must_match": True,
        "required_cues": ["disruption_sequence"],
        "required_anchors": ["venice", "dulles", "denver", "santa fe"],
        "forbid_cues": [],
        "note": "Travel disruption chain — return-journey class",
    },
    {
        "id": "school_work_military_sequence_chain",
        "narrator": (
            "I graduated from Bismarck High in 1965, then went to "
            "college at North Dakota State. After that I enlisted in "
            "the Army and was sent to basic training at Fort Leonard Wood."
        ),
        "must_match": True,
        "required_cues": ["job_school_military_sequence"],
        "required_anchors": ["bismarck high", "north dakota state"],
        "forbid_cues": [],
        "note": "School / work / military life-step sequence",
    },
    {
        "id": "family_migration_chain",
        "narrator": (
            "My grandfather emigrated from Norway in 1902. He came over "
            "through Ellis Island, then settled in Stanley, North Dakota "
            "with his brother."
        ),
        "must_match": True,
        "required_cues": ["family_migration_sequence"],
        "required_anchors": ["norway", "ellis island", "stanley"],
        "forbid_cues": [],
        "note": "Family migration chain",
    },
    {
        "id": "medical_sequence_chain",
        "narrator": (
            "I was admitted to Mayo Clinic in March, then they did the "
            "biopsy and I was diagnosed two weeks later. The surgery "
            "happened in April."
        ),
        "must_match": True,
        "required_cues": ["medical_sequence"],
        "required_anchors": ["mayo clinic"],
        "forbid_cues": [],
        "note": "Medical procedure / diagnosis / surgery chain",
    },
    {
        "id": "sensory_rich_no_chain_negative_control",
        "narrator": (
            "It was so beautiful. The smell of the bay, the sound of "
            "the seagulls, the warmth of the sun on my face. I remember "
            "feeling completely at peace."
        ),
        "must_match": False,
        "required_cues": [],
        "required_anchors": [],
        "forbid_cues": [],
        "note": "Negative control: sensory-rich emotional memory, "
                "no factual chain — Lori should be free to ask sensory follow-ups",
    },
    {
        "id": "single_anchor_negative_control",
        "narrator": "I went to Boston.",
        "must_match": False,
        "required_cues": [],
        "required_anchors": [],
        "forbid_cues": [],
        "note": "Negative control: one place, no chain",
    },
]


# ──────────────────────────────────────────────────────────────────────────
# Meta-feedback canary
# ──────────────────────────────────────────────────────────────────────────

META_FEEDBACK_CASES = [
    {
        "id": "kent_meta_feedback_against_sensory",
        "narrator": (
            "You are being vague and not asking about basic training "
            "rather the sensory parts of it. I want to tell my "
            "experience and you want to know how I felt."
        ),
        "last_assistant_text": (
            "What do you remember about the sense of camaraderie and "
            "teamwork among your fellow recruits?"
        ),
        "must_match": True,
        "expected_rejected_type": "sensory",
        "note": "Kent verbatim meta-feedback turn",
    },
    {
        "id": "not_scenery_meta_feedback",
        "narrator": "No, not the scenery — I want the facts.",
        "last_assistant_text": "What did the scenery look like?",
        "must_match": True,
        "expected_rejected_type": "sensory",
        "note": "Short narrator pushback against scenery probe",
    },
    {
        "id": "normal_narrator_not_meta_feedback",
        "narrator": (
            "We started in Prague, then went to Salzburg, then Ljubljana."
        ),
        "last_assistant_text": "Where did you go first?",
        "must_match": False,
        "expected_rejected_type": "",
        "note": "Negative control: normal travel narration is not meta-feedback",
    },
]


# ──────────────────────────────────────────────────────────────────────────
# Runner
# ──────────────────────────────────────────────────────────────────────────


def _assert_case(case: Dict[str, Any]) -> Dict[str, Any]:
    """Run one chain-detection case. Returns a dict with pass/fail + reason."""
    result = detect_factual_chain(case["narrator"])
    failures: List[str] = []

    is_match = result["is_factual_chain"]
    if is_match != case["must_match"]:
        failures.append(
            f"is_factual_chain={is_match} expected={case['must_match']}"
        )

    if case["must_match"]:
        # At least one required cue must be present
        if case["required_cues"]:
            present = [c for c in case["required_cues"] if c in result["cue_labels"]]
            if not present:
                failures.append(
                    f"none of required_cues={case['required_cues']!r} "
                    f"in cue_labels={result['cue_labels']!r}"
                )
        # All required anchor substrings must be present (case-insensitive)
        if case["required_anchors"]:
            anchors_blob = " ".join(result["anchors"]).lower()
            missing = [
                a for a in case["required_anchors"]
                if a.lower() not in anchors_blob
            ]
            if missing:
                failures.append(
                    f"missing required_anchors={missing!r} "
                    f"in anchors={result['anchors']!r}"
                )

    if case["forbid_cues"]:
        forbidden = [c for c in case["forbid_cues"] if c in result["cue_labels"]]
        if forbidden:
            failures.append(f"forbidden cues fired: {forbidden!r}")

    return {
        "id": case["id"],
        "passed": not failures,
        "failures": failures,
        "result": result,
        "note": case["note"],
    }


def _assert_meta_case(case: Dict[str, Any]) -> Dict[str, Any]:
    """Run one meta-feedback case."""
    result = detect_meta_feedback_against_probe(
        case["narrator"], case["last_assistant_text"]
    )
    failures: List[str] = []

    if result["is_meta_feedback"] != case["must_match"]:
        failures.append(
            f"is_meta_feedback={result['is_meta_feedback']} "
            f"expected={case['must_match']}"
        )
    if case["must_match"] and case["expected_rejected_type"]:
        if result["last_rejected_probe_type"] != case["expected_rejected_type"]:
            failures.append(
                f"last_rejected_probe_type={result['last_rejected_probe_type']!r} "
                f"expected={case['expected_rejected_type']!r}"
            )

    return {
        "id": case["id"],
        "passed": not failures,
        "failures": failures,
        "result": result,
        "note": case["note"],
    }


def main() -> int:
    print("=" * 78)
    print("WO-LORI-FACTUAL-CHAIN-CAPTURE-01 — classifier smoke")
    print("=" * 78)

    chain_results = [_assert_case(c) for c in CASES]
    meta_results = [_assert_meta_case(c) for c in META_FEEDBACK_CASES]

    all_pass = True

    print("\n── Chain detection cases ──────────────────────────────────")
    for r in chain_results:
        tag = "PASS" if r["passed"] else "FAIL"
        if not r["passed"]:
            all_pass = False
        print(f"  [{tag}] {r['id']}")
        if not r["passed"]:
            for f in r["failures"]:
                print(f"        - {f}")
            print(f"        result: {json.dumps(r['result'], indent=2)}")

    print("\n── Meta-feedback cases ────────────────────────────────────")
    for r in meta_results:
        tag = "PASS" if r["passed"] else "FAIL"
        if not r["passed"]:
            all_pass = False
        print(f"  [{tag}] {r['id']}")
        if not r["passed"]:
            for f in r["failures"]:
                print(f"        - {f}")
            print(f"        result: {json.dumps(r['result'], indent=2)}")

    print("\n" + "=" * 78)
    if all_pass:
        print(f"GREEN factual_chain_capture_smoke  "
              f"({len(chain_results)}/{len(chain_results)} chain, "
              f"{len(meta_results)}/{len(meta_results)} meta)")
        return 0
    else:
        chain_pass = sum(1 for r in chain_results if r["passed"])
        meta_pass = sum(1 for r in meta_results if r["passed"])
        print(f"RED factual_chain_capture_smoke  "
              f"({chain_pass}/{len(chain_results)} chain, "
              f"{meta_pass}/{len(meta_results)} meta)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
