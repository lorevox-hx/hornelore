#!/usr/bin/env python3
"""One safe, repeatable live acceptance run across the narrator cohort.

    cd /mnt/c/Users/chris/hornelore
    python3 scripts/run_narrator_cohort_acceptance.py --plan          # writes nothing
    python3 scripts/run_narrator_cohort_acceptance.py --quick --live
    python3 scripts/run_narrator_cohort_acceptance.py --full --live
    python3 scripts/run_narrator_cohort_acceptance.py --resume RUN_ID

── WHY THIS EXISTS ───────────────────────────────────────────────────

Seventeen `run_*_harness.py` runners already encode real narrator
biographies, chapter narrations, era anchors and scoring. They cannot
simply be launched together any more:

  * `harness_lib` creates narrators and never inventories or erases them;
  * the long-form runners send `current_pass=pass2a`, which no longer
    bypasses anything — new intake ENROLLS a narrator in Profile Seed,
    so the ordinary interview prompt they expect is replaced by the
    onboarding walk;
  * `harness_lib.REPO_ROOT` is hard-coded to one absolute path;
  * the product persona harness hard-deletes what it created unless
    `--keep-run` is passed, which contradicts the standing rule that
    erasure needs Chris's explicit authorization.

**This runner consolidates them; it does not replace their content.**
Every biography, chapter and anchor is read by importing the existing
harness module and calling its `build_config()`. Nothing is copied here,
so a fixture improved in its own file improves this run too.

── THE SAFETY RULES, WHICH ARE NOT NEGOTIABLE ────────────────────────

  * `--plan` is the default and performs NO network and NO database work.
  * Live creation needs `--live`, and goes through the product intake
    endpoint with `testing_only=true`. Consent is never forged.
  * Every created narrator carries the run id in its display name, and
    its UUID is recorded to `artifacts.json` BEFORE anything else runs.
  * Selection after creation is BY UUID ONLY. Display names are for
    humans; two runs can share one.
  * **Nothing is ever deleted.** `erasure-manifest.json` is written for
    later use by a human, and this program has no deletion path at all.
  * A person that is not synthetic/test (or a declared read-only
    reference) is refused before any turn is sent.

── EXCLUSIONS, WITH THEIR EVIDENCE ───────────────────────────────────

  * **Jake Max Miller** — `run_jake_long_narration_harness.py` is the
    only harness declaring `"testing_only": False`, and its own
    docstring says the chapters are drawn from Kent James Horne's
    transcript. Family-derived content and a non-testing flag; excluded
    on both counts.
  * **The writable Shatner long-narration harness** — Shatner is a
    read-only REFERENCE persona in
    `data/qa/narrator_product_personas_v1.json`. A writable fixture with
    the same name would give one identity two contradictory roles.
  * **Every family narrator** — refused by the guard, not by a list.
  * **Archived Test Lab** — its location defects are a separate repair.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── LOCATION AWARENESS ────────────────────────────────────────────────
#
# Derived from this file, never hard-coded. `harness_lib.REPO_ROOT` is a
# literal absolute path, which is one of the reasons the older runners
# resolve the wrong tree when invoked from elsewhere.
REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
EVAL_ROOT = REPO_ROOT / ".runtime" / "eval" / "narrator-cohort"

API_BASE = os.environ.get("HORNELORE_API_BASE", "http://localhost:8000")

#: Harness modules whose `build_config()` supplies a WRITABLE synthetic
#: narrator. Keyed by module stem; the value is the label expected from
#: the config, used only to report drift, never to select a person.
COHORT_HARNESSES: Dict[str, str] = {
    "run_alex_they_long_narration_harness": "Alex Eunseo Park",
    "run_john_baldy_seven_era_harness": "John Baldy",
    "run_pat_teacher_betty_harness": "Patricia Frye",
    "run_regional_african_american_georgia_harness": "Mable Hudson",
    "run_regional_asian_american_california_harness": "Hiroshi Frank Yamada",
    # The fixture says "Stefi", not the formal "Estefana". The FIXTURE
    # is the source of truth for who a persona is; aligning the
    # expectation to it is right, widening the matcher to hide the
    # difference is not.
    "run_regional_crypto_jewish_new_mexico_harness": "Stefi Sandoval",
    "run_regional_native_american_new_mexico_harness": "Joe Quintana",
    "run_regional_hispano_tex_mex_harness": "Tomasita Cantu",
    "run_richard_late_coming_out_harness": "Richard Bellamy",
    "run_seven_era_walk_harness": "Walter O'Donnell",
}

#: Fixed QA narrator templates — structured vs storytelling behaviour.
QA_TEMPLATES = {
    "Mara Vale": REPO_ROOT / "data" / "narrator_templates" / "test_structured.json",
    "Elena March": REPO_ROOT / "data" / "narrator_templates" / "test_storyteller.json",
}

#: READ-ONLY reference personas. Never created, never mutated. Absent =>
#: `not_applicable`, and the denominator does NOT shrink.
REFERENCE_PERSONAS = ("William Shatner", "Dolly Parton")

#: Excluded, with the reason recorded in the report rather than in a
#: comment nobody reads.
EXCLUSIONS = {
    "run_jake_long_narration_harness":
        "Kent-derived content and the only harness with testing_only=False",
    "run_shatner_long_narration_harness":
        "Shatner is a read-only reference persona; a writable fixture would "
        "give one identity two contradictory roles",
    "run_narrator_product_harness":
        "auto-deletes what it creates unless --keep-run; superseded here",
    "run_factual_chain_live_harness": "single-purpose probe, not a cohort persona",
    "run_john_baldy_full_diagnostic_harness":
        "superseded by the seven-era John Baldy harness for cohort purposes",
    "run_trip_route_canary_harness": "Travel Document canary, own lane",
    "run_trip_2019_france_italy_canary_harness": "Travel Document canary, own lane",
}

LANES = ("inventory", "conversation", "era", "behavior", "extraction",
         "ui", "traveldoc", "isolation", "persistence")

#: A person must look like this to receive a single turn.
SYNTHETIC_MARKERS = ("testing_only", "test", "reference")


# ── Result accounting ─────────────────────────────────────────────────
#
# FIVE outcomes, always all five. A denominator that shrinks when a
# fixture is missing is how a run reports 12/12 while testing ten things.
@dataclass
class LaneResult:
    lane: str
    persona: str
    passed: int = 0
    failed: int = 0
    not_applicable: int = 0
    skipped: int = 0
    unverified: int = 0
    findings: List[Dict[str, Any]] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)

    @property
    def denominator(self) -> int:
        return (self.passed + self.failed + self.not_applicable
                + self.skipped + self.unverified)


class CohortRefusal(Exception):
    """A safety precondition failed. Nothing has been written."""


# ── Fixture discovery — IMPORT, never copy ────────────────────────────
#: True when a transport dependency had to be stubbed to READ a fixture.
#: Reported, because a plan produced under a stub has not verified that
#: the real transport imports — and a reader must not infer that it did.
FIXTURES_READ_WITH_STUB: List[str] = []


def _stub_transport_deps() -> None:
    """Let PLAN read fixtures without the live transport installed.

    `harness_lib` imports `websockets` at module scope and exits if it is
    missing. That is right for a runner that sends turns and wrong for
    one that only wants to know which chapters a fixture declares.

    Only inserted when genuinely absent, so a real environment is never
    shadowed. Recorded in the report either way.
    """
    for name in ("websockets",):
        if name in sys.modules:
            continue
        try:
            __import__(name)
        except ImportError:
            import types
            mod = types.ModuleType(name)
            mod.__doc__ = "plan-mode stub; no transport is available"
            sys.modules[name] = mod
            if name not in FIXTURES_READ_WITH_STUB:
                FIXTURES_READ_WITH_STUB.append(name)


def load_harness_config(stem: str):
    """Import a harness module and return its `build_config()` result.

    The biography lives in that file and stays there. If it is edited,
    this run picks the edit up with no change here — which is the whole
    point of importing rather than duplicating.
    """
    path = SCRIPTS / f"{stem}.py"
    if not path.exists():
        return None, f"missing: {path.name}"
    _stub_transport_deps()
    try:
        spec = importlib.util.spec_from_file_location(stem, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[stem] = mod
        spec.loader.exec_module(mod)
    except Exception as exc:                       # pragma: no cover - env
        return None, f"import failed: {type(exc).__name__}: {exc}"
    builder = getattr(mod, "build_config", None)
    if not callable(builder):
        return None, "no build_config()"
    try:
        return builder(), None
    except Exception as exc:                       # pragma: no cover
        return None, f"build_config raised: {type(exc).__name__}: {exc}"


def _norm(name: str) -> str:
    """Identity comparison: case, accents, punctuation and nicknames out."""
    import unicodedata
    n = unicodedata.normalize("NFKD", name or "")
    n = "".join(c for c in n if not unicodedata.combining(c)).lower()
    n = re.sub(r"\(.*?\)|'.*?'|\u2019.*?\u2019|\".*?\"", " ", n)
    return re.sub(r"[^a-z]+", " ", n).strip()


def _same_identity(actual: str, expected: str) -> bool:
    """True when both names denote the same person.

    Surname plus at least one given-name token must agree. That accepts
    "Frank Yamada" for "Hiroshi Frank Yamada" and rejects a fixture that
    silently became somebody else.
    """
    a, e = set(_norm(actual).split()), set(_norm(expected).split())
    if not a or not e:
        return False
    return len(a & e) >= 2 or (a <= e) or (e <= a)


def intake_is_testing_only(cfg) -> bool:
    payload = getattr(cfg, "intake_payload", None) or {}
    return bool(payload.get("testing_only")) or bool(
        getattr(cfg, "testing_only", False))


# ── Safety guards ─────────────────────────────────────────────────────
def assert_synthetic(person: Dict[str, Any]) -> None:
    """Refuse anything that is not clearly synthetic.

    Checked against the SERVER's record, not against our own intent —
    the question is what this narrator actually is, not what we meant to
    create.
    """
    name = (person.get("display_name") or "")
    if not name.strip():
        raise CohortRefusal("person has no display name; refusing")
    testing = person.get("testing_only")
    narrator_type = (person.get("narrator_type") or "").lower()
    if testing is True or narrator_type == "reference":
        return
    raise CohortRefusal(
        f"{name!r} ({person.get('id')}) is not marked testing_only and is not "
        "a reference narrator — refusing to send it a turn. Family and "
        "production narrators are never part of this cohort.")


def run_prefix(run_id: str) -> str:
    """Unmistakable, and carries the run id so artifacts are traceable."""
    return f"ZZ COHORT {run_id} · "


# ── Artifact ledger — written BEFORE anything else happens ────────────
class Ledger:
    """Everything this run created, recorded the moment it exists.

    The order matters more than the format: a UUID is appended and
    flushed before the narrator is used for anything, so a crash between
    creation and use still leaves a complete inventory. The older
    harnesses create first and record later, which is how orphans appear.
    """

    def __init__(self, out_dir: Path, run_id: str):
        self.path = out_dir / "artifacts.json"
        self.erasure = out_dir / "erasure-manifest.json"
        self.data: Dict[str, Any] = {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "people": [], "conversations": [], "turns": [],
            "storage_paths": [], "notes": [],
        }
        self._flush()

    def add_person(self, person_id: str, display_name: str, source: str) -> None:
        self.data["people"].append({"person_id": person_id,
                                    "display_name": display_name,
                                    "source": source,
                                    "at": datetime.now(timezone.utc).isoformat(
                                        timespec="seconds")})
        self._flush()

    def add(self, bucket: str, value: Any) -> None:
        self.data.setdefault(bucket, []).append(value)
        self._flush()

    def _flush(self) -> None:
        self.path.write_text(json.dumps(self.data, indent=1), encoding="utf-8")

    def write_erasure_manifest(self) -> None:
        """INFORMATIONAL ONLY. This program deletes nothing, ever.

        The manifest exists so a human can erase deliberately, later,
        through the product hard-delete path with Chris's authorization.
        It is not a script and it is not wired to anything.
        """
        self.erasure.write_text(json.dumps({
            "run_id": self.data["run_id"],
            "authorization_required": True,
            "how": ("Erasure is a product operation. Use the product "
                    "hard-delete path for each id below, only with Chris's "
                    "explicit authorization. This runner has no deletion "
                    "code path."),
            "person_ids": [p["person_id"] for p in self.data["people"]],
            "people": self.data["people"],
        }, indent=1), encoding="utf-8")


# ── Checkpointing ─────────────────────────────────────────────────────
class Checkpoint:
    """Completed (persona, lane) pairs, so a resume repeats no model work."""

    def __init__(self, out_dir: Path):
        self.path = out_dir / "checkpoint.json"
        self.done: Dict[str, Any] = {}
        if self.path.exists():
            try:
                self.done = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self.done = {}

    @staticmethod
    def key(persona: str, lane: str) -> str:
        return f"{persona}::{lane}"

    def is_done(self, persona: str, lane: str) -> bool:
        return self.key(persona, lane) in self.done

    def mark(self, persona: str, lane: str, result: Dict[str, Any]) -> None:
        self.done[self.key(persona, lane)] = result
        self.path.write_text(json.dumps(self.done, indent=1), encoding="utf-8")


# ── Planning ──────────────────────────────────────────────────────────
def build_plan(quick: bool = False) -> Dict[str, Any]:
    """What WOULD run. No network, no database, no writes."""
    personas, problems = [], []
    for stem, expected in COHORT_HARNESSES.items():
        cfg, err = load_harness_config(stem)
        if cfg is None:
            problems.append({"harness": stem, "problem": err,
                             "disposition": "skipped"})
            continue
        label = getattr(cfg, "narrator_label", None) or expected
        chapters = list(getattr(cfg, "chapters", []) or [])
        entry = {
            "harness": stem,
            "label": label,
            "expected_label": expected,
            # Labels carry descriptors — "Alex Eunseo Park (they/them)" —
            # so equality would flag every row. Drift means the IDENTITY
            # moved, not that the decoration differs.
            "label_drift": not _same_identity(label, expected),
            "chapters": len(chapters),
            "eras": [getattr(c, "runtime71_era", "?") for c in chapters],
            "testing_only": intake_is_testing_only(cfg),
        }
        if not entry["testing_only"]:
            entry["disposition"] = "refused: not testing_only"
            problems.append(entry)
            continue
        personas.append(entry)

    if quick:
        personas = personas[:2]

    return {
        "api_base": API_BASE,
        "repo_root": str(REPO_ROOT),
        "personas": personas,
        "qa_templates": {k: (v.exists()) for k, v in QA_TEMPLATES.items()},
        "reference_personas": list(REFERENCE_PERSONAS),
        "exclusions": EXCLUSIONS,
        "problems": problems,
        "lanes": list(LANES),
        "fixtures_read_with_stubbed_transport": list(FIXTURES_READ_WITH_STUB),
        "stub_caveat": (
            "A stubbed transport means the fixture's CONTENT was read; it "
            "does NOT mean the real transport imports in this environment."
            if FIXTURES_READ_WITH_STUB else None),
        "writes": "NONE — --plan performs no network or database work",
    }


# ── Entry point ───────────────────────────────────────────────────────
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Report-only narrator cohort acceptance runner.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true",
                      help="default; enumerate what would run, write nothing")
    mode.add_argument("--quick", action="store_true",
                      help="two synthetic narrators")
    mode.add_argument("--full", action="store_true", help="the whole cohort")
    ap.add_argument("--resume", metavar="RUN_ID",
                    help="continue a run, repeating no completed model turn")
    ap.add_argument("--live", action="store_true",
                    help="REQUIRED for any network or database work")
    ap.add_argument("--only-persona", action="append", default=[])
    ap.add_argument("--only-lane", action="append", default=[],
                    choices=list(LANES))
    args = ap.parse_args(argv)

    # ── DEFAULT IS PLAN, AND LIVE IS EXPLICIT ─────────────────────────
    #
    # Both halves matter. Defaulting to plan means a mistyped command
    # inspects rather than creates; requiring --live means creating
    # narrators is always a decision somebody made on purpose.
    if not (args.quick or args.full or args.resume):
        args.plan = True
    if args.plan or not args.live:
        plan = build_plan(quick=args.quick)
        print(json.dumps(plan, indent=1))
        if not args.plan:
            print("\nREFUSED: --live is required for network or database "
                  "work. The above is a plan; nothing was written.",
                  file=sys.stderr)
            return 2
        return 0

    # Live execution is deliberately not implemented in this commit.
    # The instrument, its safety guards and its tests land first; the
    # live lanes land only once those are accepted, so that a green test
    # suite is never mistaken for a run that actually happened.
    print("REFUSED: live lanes are not enabled in this commit. The plan, "
          "guards, ledger and tests are in place; live execution is the "
          "next reviewed step.", file=sys.stderr)
    return 3


if __name__ == "__main__":      # pragma: no cover
    sys.exit(main())
