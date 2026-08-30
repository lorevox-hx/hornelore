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
import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import sys
import time
import urllib.parse
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
#:
#: These are WRITABLE COHORT MEMBERS, not a listing. The cohort is twelve
#: synthetic narrators: the ten long-form harness personas above plus
#: these two. Listing them without creating them would have reported a
#: twelve-narrator cohort that ran ten.
#:
#: Both files are marked "Do NOT edit" and carry `narrator_type: "test"`.
#: They are READ and mapped into an intake payload by
#: `template_intake_payload`; the templates themselves are never written.
QA_TEMPLATES = {
    "Mara Vale": REPO_ROOT / "data" / "narrator_templates" / "test_structured.json",
    "Elena March": REPO_ROOT / "data" / "narrator_templates" / "test_storyteller.json",
}

#: `--quick` is Alex and Walt BY NAME, not "the first two".
#:
#: It was `personas[:2]`, which is Alex and *John Baldy* — dictionary
#: order, silently. Walt is the one whose harness walks all seven eras,
#: so a quick run that omits him cannot exercise the era lane at all,
#: and the two personas the quick run is specified to cover would not
#: have been the two it ran.
QUICK_HARNESSES = ("run_alex_they_long_narration_harness",
                   "run_seven_era_walk_harness")

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

#: The browser half. The UI lane is INCOMPLETE without this file, so its
#: presence is asserted rather than assumed — a missing helper must be a
#: reported problem, not a silently skipped lane.
BROWSER_HELPER = SCRIPTS / "ui" / "run_narrator_cohort_surfaces.js"

#: The product database, read ONLY through `mode=ro`. See
#: `containment_snapshot` for why the read-only URI is load-bearing.
DEFAULT_DB_PATH = Path(os.environ.get(
    "HORNELORE_DB_PATH", str(REPO_ROOT / ".runtime" / "hornelore.db")))

#: Reference personas are never extracted from.
#:
#: `/api/extract-fields` CAN PERSIST bio facts when routing is enabled, so
#: running it against a read-only reference narrator would write to a
#: person this instrument promises never to modify. The disposition is
#: `not_applicable` rather than `skipped`: the denominator keeps the case,
#: and the report states why it was never eligible.
REFERENCE_EXTRACTION_DISPOSITION = "not_applicable"
REFERENCE_EXTRACTION_REASON = (
    "reference narrators are read-only; /api/extract-fields may persist bio "
    "facts when routing is enabled, so extraction is never run against them")

#: Travel Document surface states. `unknown` is deliberately NOT a pass —
#: a classifier that cannot tell populated from empty has not measured
#: anything, and saying so is more useful than guessing.
TRAVEL_CLASSIFICATIONS = ("populated", "empty", "unavailable", "unknown")

#: Every terminal status a task may hold. `summarize_tasks` raises on
#: anything outside this set, so a typo cannot invent a category that
#: quietly vanishes from the denominator.
TASK_STATUSES = ("passed", "failed", "not_applicable", "skipped",
                 "unverified", "pending", "running")


def summarize_tasks(tasks) -> Dict[str, int]:
    """Explicit denominators, including the ones nobody wants to look at.

    `not_applicable`, `skipped` and `unverified` are counted and REPORTED,
    never dropped. A run that cannot score twelve cultural-humility cases
    must say "12 unverified", because "0 failures" over a vanished
    denominator is the most flattering way to describe having tested
    nothing.
    """
    counts = {key: 0 for key in TASK_STATUSES}
    alias = {"pass": "passed", "fail": "failed"}
    for task in tasks:
        raw = task.get("status") if isinstance(task, dict) else getattr(
            task, "status", None)
        status = alias.get(str(raw), str(raw))
        if status not in counts:
            raise CohortRefusal(f"unknown task status in denominator: {raw!r}")
        counts[status] += 1
    counts["total"] = sum(counts.values())
    return counts


def containment_snapshot(person_ids_in_run, db_path: Path = DEFAULT_DB_PATH,
                         people_rows=None) -> Dict[str, Any]:
    """Hash the narrators this run must NOT touch, before and after.

    Opened with `file:...?mode=ro` deliberately. The obvious way to read
    onboarding state is the Profile Seed GET endpoint, and that endpoint
    IS A WRITING READ for an enrolled narrator — resolving a turn can
    recompute derived topic state and bump the row's version. Using it to
    prove "I did not touch these people" would therefore touch them. A
    read-only SQLite handle cannot, whatever the query says.

    What this proves and what it does not: the hashes establish that the
    membership of the people table and the onboarding rows of non-run
    narrators are unchanged. They do NOT prove no read occurred, and they
    do not cover every column. Stated in the report rather than implied.
    """
    ids = sorted(str(p) for p in (people_rows or []))
    in_run = {str(p) for p in person_ids_in_run}
    non_run = sorted(p for p in ids if p not in in_run)

    onboarding_rows: List[str] = []
    probe_errors = 0
    if db_path.exists():
        try:
            con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            try:
                raw = con.execute(
                    "SELECT person_id,status,active_topic_id,version "
                    "FROM profile_seed_onboarding ORDER BY person_id;"
                ).fetchall()
            finally:
                con.close()
            non_run_set = set(non_run)
            onboarding_rows = [
                "\t".join("" if v is None else str(v) for v in row)
                for row in raw if str(row[0]) in non_run_set
            ]
        except (OSError, sqlite3.Error):
            probe_errors = 1
    else:
        probe_errors = 1

    def _sha(values) -> str:
        return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()

    return {
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "db_opened_read_only": True,
        "count": len(ids),
        "id_set_sha256": _sha(ids),
        "non_run_count": len(non_run),
        "non_run_id_set_sha256": _sha(non_run),
        "non_run_onboarding_row_count": len(onboarding_rows),
        "non_run_onboarding_state_sha256": _sha(onboarding_rows),
        "onboarding_probe_errors": probe_errors,
        "proves": ("stable membership and unchanged onboarding rows for "
                   "non-run narrators"),
        "does_not_prove": ("absence of reads, or that every column of every "
                           "row is unchanged"),
    }


def delete_inventory_path(person_id: str) -> str:
    """The product's own dependency inventory — a READ, never a delete.

    This runner has no deletion call site. Knowing what WOULD be removed
    is what lets a human erase deliberately later; performing the removal
    is not this instrument's job and never becomes it.
    """
    return f"/api/people/{urllib.parse.quote(str(person_id))}/delete-inventory"


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
    """Unmistakable, and carries the run id so artifacts are traceable.

    This is a NARRATOR DISPLAY-NAME prefix, not a run id and not a path
    component — it contains spaces and a middot on purpose, so a cohort
    narrator is impossible to mistake for a real one in the picker. Use
    `new_run_id()` for anything that becomes a directory.
    """
    return f"ZZ COHORT {run_id} · "


def new_run_id() -> str:
    """A filesystem-safe run id.

    `run_prefix` was briefly used for this, which produced the directory
    `.runtime/eval/narrator-cohort/ZZ COHORT 1d66d482 · ` — spaces, a
    non-ASCII middot, and a trailing separator, in a path that later has
    to survive a shell, a resume argument and a Windows checkout.
    """
    return f"r{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"


def mark_intake_payload(payload: Dict[str, Any], run_id: str) -> Dict[str, Any]:
    """Stamp the cohort marker onto the narrator's visible names.

    WITHOUT THIS, the cohort creates narrators called "Alex" and "Walter
    O'Donnell" — indistinguishable in the picker from anybody real. The
    fixtures carry ordinary human names because they are written to read
    like people; making them identifiable as test data is this runner's
    job, not the fixture's.

    Both name fields are stamped: `preferred_name` becomes the people
    row's `display_name`, which is what the picker shows, and
    `full_legal_name` is what the intake fan-out writes into bio facts.
    """
    marked = dict(payload)
    prefix = run_prefix(run_id)
    for field in ("preferred_name", "full_legal_name"):
        value = str(marked.get(field) or "").strip()
        if value and not value.startswith("ZZ COHORT"):
            marked[field] = f"{prefix}{value}"
    marked["testing_only"] = True
    return marked


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
        self.selection: Optional[Dict[str, Any]] = None
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                raw = {}
            # Older checkpoints are a bare {key: result} map; newer ones
            # carry the frozen selection alongside. Read both.
            if isinstance(raw, dict) and "tasks" in raw:
                self.done = raw.get("tasks") or {}
                self.selection = raw.get("selection")
            else:
                self.done = raw if isinstance(raw, dict) else {}

    @staticmethod
    def key(persona: str, lane: str) -> str:
        return f"{persona}::{lane}"

    def is_done(self, persona: str, lane: str) -> bool:
        return self.key(persona, lane) in self.done

    def set_selection(self, *, personas, lanes, mode: str) -> None:
        """Freeze the run boundary before the first network request.

        A bare `--resume` must mean "finish the same run", never "widen a
        two-narrator quick run into the full twelve". Without this, the
        cheapest possible typo — resuming a quick run with the default
        mode — silently creates ten narrators nobody asked for, and the
        checkpoint makes it look intentional afterwards.

        The stored selection is compared, not merged. Any difference is
        refused rather than reconciled, because the safe reconciliation
        of "quick" and "full" is not obvious and guessing it is how a
        containment promise breaks.
        """
        requested = {"personas": sorted(str(p) for p in personas),
                     "lanes": sorted(str(lane) for lane in lanes),
                     "mode": str(mode)}
        if self.selection is not None and self.selection != requested:
            raise CohortRefusal(
                "run selection is immutable — a resume cannot change or "
                f"broaden it.\n  stored:    {self.selection!r}\n"
                f"  requested: {requested!r}")
        self.selection = requested
        self._flush()

    def mark(self, persona: str, lane: str, result: Dict[str, Any]) -> None:
        self.done[self.key(persona, lane)] = result
        self._flush()

    def _flush(self) -> None:
        self.path.write_text(json.dumps(
            {"selection": self.selection, "tasks": self.done}, indent=1),
            encoding="utf-8")


# ── Persona loading ───────────────────────────────────────────────────
def load_personas(quick: bool = False) -> List[Dict[str, Any]]:
    """The cohort as LIVE-USABLE objects: chapters and intake payloads.

    Twelve writable synthetic narrators — ten long-form harness personas
    plus the two QA templates. `build_plan` renders its JSON view from
    this same list, so the plan can never describe a cohort different
    from the one that would run.
    """
    personas: List[Dict[str, Any]] = []
    for stem, expected in COHORT_HARNESSES.items():
        cfg, _err = load_harness_config(stem)
        if cfg is None or not intake_is_testing_only(cfg):
            continue
        personas.append({
            "harness": stem,
            "label": getattr(cfg, "narrator_label", None) or expected,
            "expected_label": expected,
            "chapters": list(getattr(cfg, "chapters", []) or []),
            "intake_payload": dict(getattr(cfg, "intake_payload", {}) or {}),
            "source": "harness",
        })
    for name, path in QA_TEMPLATES.items():
        if not path.is_file():
            continue
        personas.append({
            "harness": f"template:{path.name}",
            "label": name,
            "expected_label": name,
            # The templates are fixtures, not scripted conversations;
            # they exercise intake, Profile Seed and the UI surfaces.
            "chapters": [],
            "intake_payload": template_intake_payload(name, path),
            "source": "qa_template",
            "harness_supplied_fields": list(TEMPLATE_SUPPLIED_FIELDS),
        })

    if quick:
        wanted = [p for p in personas if p["harness"] in QUICK_HARNESSES]
        if len(wanted) != len(QUICK_HARNESSES):
            missing = set(QUICK_HARNESSES) - {p["harness"] for p in wanted}
            raise CohortRefusal(
                f"--quick requires Alex and Walt; missing: {sorted(missing)}")
        return wanted
    return personas


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

    # The two QA templates are COHORT MEMBERS, so they appear here beside
    # the harness personas rather than only as a `qa_templates` listing.
    for name, tpath in QA_TEMPLATES.items():
        if not tpath.is_file():
            problems.append({"harness": f"template:{tpath.name}",
                             "label": name,
                             "problem": "template file is missing",
                             "disposition": "skipped"})
            continue
        personas.append({
            "harness": f"template:{tpath.name}",
            "label": name,
            "expected_label": name,
            "label_drift": False,
            "chapters": 0,
            "eras": [],
            "testing_only": True,
            "source": "qa_template",
            "harness_supplied_fields": list(TEMPLATE_SUPPLIED_FIELDS),
        })

    if quick:
        keep = {p["label"] for p in load_personas(quick=True)}
        personas = [p for p in personas if p["label"] in keep]

    # The UI lane cannot run without its browser half. A missing helper is
    # recorded as a PROBLEM, so the lane is visibly unavailable rather than
    # quietly absent from the report.
    helper_present = BROWSER_HELPER.is_file()
    if not helper_present:
        problems.append({
            "component": "browser helper",
            "path": str(BROWSER_HELPER.relative_to(REPO_ROOT)),
            "problem": "missing — the ui, traveldoc, isolation and "
                       "persistence lanes have no browser half",
            "disposition": "ui lanes unavailable",
        })

    return {
        "api_base": API_BASE,
        "repo_root": str(REPO_ROOT),
        "personas": personas,
        "browser_helper": {
            "path": str(BROWSER_HELPER.relative_to(REPO_ROOT)),
            "present": helper_present,
            "interaction": ("exact-UUID semantic Open only; never "
                            "coordinates, never list position, never Delete"),
            "travel_classifications": list(TRAVEL_CLASSIFICATIONS),
        },
        "reference_extraction": {
            "disposition": REFERENCE_EXTRACTION_DISPOSITION,
            "reason": REFERENCE_EXTRACTION_REASON,
        },
        "containment": {
            "db_read_mode": "sqlite mode=ro",
            "why": ("Profile Seed GET is a writing read for an enrolled "
                    "narrator, so containment evidence is taken from a "
                    "read-only database handle instead"),
        },
        "deletion": {
            "call_sites": 0,
            "inventory_endpoint": delete_inventory_path("<person_id>"),
            "note": ("the product deletion inventory is READ to record "
                     "dependencies; this runner never deletes"),
        },
        "task_statuses": list(TASK_STATUSES),
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


# ── Live orchestration ────────────────────────────────────────────────
#
# THE ORDER IS THE CONTRACT.
#
# Every step below exists because doing it later would either touch data
# this instrument promises not to touch, or produce evidence that cannot
# be trusted afterwards. Two are load-bearing and easy to get wrong:
#
#   * `journal_uuid` comes IMMEDIATELY after `create_intake` and before
#     any other request. A narrator that exists but is not on disk is an
#     orphan, and a crash between creating and recording is exactly when
#     orphans are made. Verification is a subsequent request, so it
#     happens after the journal, not before.
#
#   * `containment_baseline` is captured ONCE per run and never replaced.
#     A resumed run has already created some of its cohort; re-taking the
#     baseline then would fold those narrators into it and make the delta
#     show nothing, turning resumability into false evidence.
#
# `ORCHESTRATION` is asserted by the mocked end-to-end test, so reordering
# these steps breaks a test rather than silently changing what is proven.
ORCHESTRATION = (
    "freeze_selection",
    "containment_baseline",
    "create_intake",
    "journal_uuid",
    "verify_identity",
    "profile_seed_resolve",
    "profile_seed_pause",
    "model_turns",
    "era_evidence",
    "browser_traversal",
    "delete_inventory_read",
    "containment_after",
    "emit_reports",
)

#: Walt's harness already walks all seven eras. The era lane REUSES that
#: completed evidence rather than re-asking the same material, which is
#: both minutes of model time and a second set of turns whose only
#: function would be to agree with the first.
ERA_EVIDENCE_SOURCE = "run_seven_era_walk_harness"


class Transport:
    """Every side effect the live run can have, in one injectable object.

    Collected here so the mocked end-to-end test can prove the
    orchestration order without a stack, a model or a browser — and so
    that the set of things this instrument is even CAPABLE of doing is a
    short list somebody can read. There is no deletion method, which is
    the strongest form of "it never deletes".
    """

    def __init__(self, api_base: str = API_BASE, timeout: int = 300):
        self.api_base = api_base.rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, path: str,
                 payload: Optional[Dict[str, Any]] = None):
        import urllib.error
        import urllib.request
        url = f"{self.api_base}{path}"
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers,
                                     method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
                return resp.status, (json.loads(body) if body else {})
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            try:
                return exc.code, json.loads(raw)
            except ValueError:
                return exc.code, {"detail": raw[:400]}

    def get(self, path: str):
        return self._request("GET", path)

    def post(self, path: str, payload: Dict[str, Any]):
        return self._request("POST", path, payload)

    def patch(self, path: str, payload: Dict[str, Any]):
        return self._request("PATCH", path, payload)

    def list_people(self) -> List[str]:
        status, body = self.get("/api/people?limit=500")
        if status != 200 or not isinstance(body, dict):
            raise CohortRefusal(f"people listing failed: HTTP {status}")
        return [str(r.get("id") or r.get("person_id") or "")
                for r in body.get("people", []) if isinstance(r, dict)]

    def model_turn(self, *, person_id: str, text: str, era: str,
                   speaker_name: str, conv_id: str) -> Dict[str, Any]:
        """One narrator turn over the production WebSocket.

        Delegated to `harness_lib._send_turn_and_capture` so the cohort
        speaks to the model through exactly the same transport the
        individual harnesses use. A private copy here would drift.
        """
        import asyncio
        sys.path.insert(0, str(SCRIPTS))
        import harness_lib  # noqa: E402
        import websockets   # noqa: E402

        async def _run():
            async with websockets.connect(
                harness_lib.WS_URL if hasattr(harness_lib, "WS_URL")
                else self.api_base.replace("http", "ws") + "/api/chat/ws",
                max_size=None, open_timeout=60,
            ) as ws:
                return await harness_lib._send_turn_and_capture(
                    ws, text=text, conv_id=conv_id, person_id=person_id,
                    speaker_name=speaker_name, runtime71_era=era,
                    chapter_label=era, timeout_s=self.timeout)

        final_text, events = asyncio.run(_run())
        return {"text": final_text, "events": len(events), "era": era}

    def browser(self, *, person_id: str, expected_name: str,
                ui_url: str, output: Path, screenshots: Path) -> Dict[str, Any]:
        """Run the exact-UUID browser helper as a subprocess."""
        import subprocess
        if not BROWSER_HELPER.is_file():
            return {"ok": False, "error": "browser helper is missing",
                    "lane_status": "unverified"}
        output.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            ["node", str(BROWSER_HELPER),
             "--ui", ui_url, "--person-id", person_id,
             "--expected-name", expected_name,
             "--output", str(output), "--screenshots", str(screenshots)],
            capture_output=True, text=True, timeout=900)
        evidence: Dict[str, Any] = {"exit_code": proc.returncode}
        if output.is_file():
            try:
                evidence.update(json.loads(output.read_text(encoding="utf-8")))
            except ValueError:
                evidence["parse_error"] = True
        if proc.returncode != 0 and "ok" not in evidence:
            evidence["stderr"] = proc.stderr[-800:]
        return evidence


def template_intake_payload(name: str, path: Path) -> Dict[str, Any]:
    """Build an intake payload from a quarantined QA template.

    The templates are marked "Do NOT edit", so they are READ and mapped
    here rather than modified to fit the intake form.

    TWO FIELDS ARE HARNESS-SUPPLIED, and they are labelled as such in the
    report rather than presented as fixture truth: the templates carry no
    pronouns and no current residence, while intake requires both. An
    invented value that is silently indistinguishable from fixture data
    is how a fixture acquires biography nobody wrote.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    display = str(data.get("display_name") or name)
    return {
        "full_legal_name": display,
        "preferred_name": display.split()[0] if display.split() else display,
        "date_of_birth": str(data.get("date_of_birth") or ""),
        "place_of_birth": str(data.get("place_of_birth") or ""),
        # ── HARNESS-SUPPLIED, not fixture truth ──────────────────────
        "pronouns": "she_her",
        "current_residence": "unspecified — synthetic QA fixture",
        # ─────────────────────────────────────────────────────────────
        "testing_only": True,
        "consent_recording_agreement": True,
        "consent_disclosure_reviewed": True,
    }


#: Fields `template_intake_payload` invents because intake demands them.
TEMPLATE_SUPPLIED_FIELDS = ("pronouns", "current_residence")


class LiveRun:
    """The wired quick/full run. Report-only; it creates and reads."""

    def __init__(self, *, personas: List[Dict[str, Any]], lanes: List[str],
                 mode: str, out_dir: Path, transport: Transport,
                 ui_url: str, db_path: Path = DEFAULT_DB_PATH,
                 run_id: Optional[str] = None):
        self.personas = personas
        self.lanes = lanes
        self.mode = mode
        self.out_dir = out_dir
        self.transport = transport
        self.ui_url = ui_url
        self.db_path = db_path
        self.run_id = run_id or new_run_id()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.ledger = Ledger(self.out_dir, self.run_id)
        self.checkpoint = Checkpoint(self.out_dir)
        #: Ordered record of what actually happened, asserted by tests.
        self.trace: List[str] = []
        self.results: List[Dict[str, Any]] = []
        self.era_evidence: Dict[str, Any] = {}

    # ── step helpers ─────────────────────────────────────────────────
    def _step(self, name: str) -> None:
        if name not in ORCHESTRATION:
            raise CohortRefusal(f"undeclared orchestration step: {name!r}")
        self.trace.append(name)

    def _baseline(self) -> Dict[str, Any]:
        """Captured once. A resume reads the stored one, never re-takes it."""
        path = self.out_dir / "containment-before.json"
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        snap = containment_snapshot(
            [], db_path=self.db_path,
            people_rows=self.transport.list_people())
        path.write_text(json.dumps(snap, indent=1), encoding="utf-8")
        return snap

    def create_narrator(self, persona: Dict[str, Any]) -> str:
        """Intake, then journal BEFORE anything else touches the network."""
        self._step("create_intake")
        # Marked AND testing-only. The marker is what makes a cohort
        # narrator identifiable in the picker; testing_only is what keeps
        # it out of family truth. Neither substitutes for the other.
        payload = mark_intake_payload(persona["intake_payload"], self.run_id)
        status, body = self.transport.post("/api/people/intake", payload)
        if status != 200 or not isinstance(body, dict):
            raise CohortRefusal(
                f"intake failed for {persona['label']}: HTTP {status} {body}")
        person_id = str(body.get("person_id")
                        or (body.get("person") or {}).get("id") or "")
        if not person_id:
            raise CohortRefusal(
                f"intake returned no person_id for {persona['label']}")

        # THE JOURNAL IS THE NEXT THING THAT HAPPENS. Not verification,
        # not a follow-up GET — a crash after this line still leaves a
        # complete inventory of what exists.
        self._step("journal_uuid")
        self.ledger.add_person(person_id, persona["label"], persona["harness"])

        self._step("verify_identity")
        vstatus, vbody = self.transport.get(f"/api/people/{person_id}")
        person = (vbody or {}).get("person") if isinstance(vbody, dict) else None
        if vstatus != 200 or not isinstance(person, dict):
            raise CohortRefusal(
                f"created {person_id} but could not read it back: HTTP {vstatus}")
        assert_synthetic(person)          # refuses anything not testing-only
        return person_id

    def pause_profile_seed(self, person_id: str) -> Dict[str, Any]:
        """Resolve, then pause through the VERSIONED product endpoint.

        Never by writing the onboarding row, and never by forging client
        runtime: a paused state this instrument manufactured would not be
        a state any narrator can actually reach.
        """
        self._step("profile_seed_resolve")
        status, state = self.transport.get(
            f"/api/interview/profile-seed?person_id={urllib.parse.quote(person_id)}")
        if status != 200 or not isinstance(state, dict):
            return {"paused": False, "reason": f"resolve HTTP {status}"}
        if not state.get("enrolled", True):
            return {"paused": False, "reason": "not enrolled; nothing to pause"}

        self._step("profile_seed_pause")
        version = state.get("version")
        if not isinstance(version, int):
            return {"paused": False,
                    "reason": f"version is not an integer: {version!r}"}
        pstatus, pbody = self.transport.patch(
            "/api/interview/profile-seed",
            {"person_id": person_id, "expected_version": version,
             "action": "pause"})
        return {"paused": pstatus == 200, "http": pstatus,
                "version_sent": version,
                "status_after": (pbody or {}).get("status")
                if isinstance(pbody, dict) else None}

    def run_turns(self, persona: Dict[str, Any], person_id: str) -> Dict[str, Any]:
        """Sequential. One turn at a time, checkpointed as it goes."""
        self._step("model_turns")
        conv_id = f"cohort-{self.run_id}-{person_id[:8]}"
        turns: List[Dict[str, Any]] = []
        for index, chapter in enumerate(persona.get("chapters", [])):
            lane_key = f"turn{index}"
            if self.checkpoint.is_done(persona["label"], lane_key):
                turns.append({"index": index, "reused_from_checkpoint": True})
                continue
            result = self.transport.model_turn(
                person_id=person_id,
                text=getattr(chapter, "narrator_text", "") or "",
                era=getattr(chapter, "runtime71_era", "unknown"),
                speaker_name=persona["label"], conv_id=conv_id)
            record = {"index": index, "era": result.get("era"),
                      "chars": len(result.get("text") or "")}
            turns.append(record)
            self.ledger.add("turns", {"person_id": person_id, **record})
            self.checkpoint.mark(persona["label"], lane_key, record)
        return {"conversation_id": conv_id, "turns": turns}

    def reuse_era_evidence(self, persona: Dict[str, Any],
                           conversation: Dict[str, Any]) -> Dict[str, Any]:
        """The era lane reads the conversation that already happened."""
        self._step("era_evidence")
        eras = sorted({t.get("era") for t in conversation.get("turns", [])
                       if t.get("era")})
        return {
            "source": ERA_EVIDENCE_SOURCE
            if persona["harness"] == ERA_EVIDENCE_SOURCE else persona["harness"],
            "reused_from_conversation_lane": True,
            "eras_covered": eras,
            "note": ("derived from the conversation lane's completed turns; "
                     "the same seven-era material is never asked twice"),
        }

    def traverse(self, persona: Dict[str, Any], person_id: str) -> Dict[str, Any]:
        self._step("browser_traversal")
        return self.transport.browser(
            person_id=person_id, expected_name=persona["label"],
            ui_url=self.ui_url,
            output=self.out_dir / "browser" / f"{person_id}.json",
            screenshots=self.out_dir / "screenshots" / person_id)

    def read_delete_inventory(self, person_id: str) -> Dict[str, Any]:
        """Exact dependency evidence. A READ. Nothing is removed."""
        self._step("delete_inventory_read")
        status, body = self.transport.get(delete_inventory_path(person_id))
        return {"http": status,
                "inventory": body if isinstance(body, dict) else None,
                "deleted": False}

    # ── the run ──────────────────────────────────────────────────────
    def execute(self) -> Dict[str, Any]:
        self._step("freeze_selection")
        self.checkpoint.set_selection(
            personas=[p["label"] for p in self.personas],
            lanes=self.lanes, mode=self.mode)

        self._step("containment_baseline")
        before = self._baseline()

        for persona in self.personas:
            person_id = self.create_narrator(persona)
            seed = self.pause_profile_seed(person_id)
            conversation = self.run_turns(persona, person_id)
            era = self.reuse_era_evidence(persona, conversation)
            browser = self.traverse(persona, person_id)
            inventory = self.read_delete_inventory(person_id)
            self.results.append({
                "persona": persona["label"], "person_id": person_id,
                "profile_seed": seed, "conversation": conversation,
                "era": era, "browser": browser,
                "delete_inventory": inventory,
            })

        self._step("containment_after")
        after = containment_snapshot(
            [r["person_id"] for r in self.results], db_path=self.db_path,
            people_rows=self.transport.list_people())

        self._step("emit_reports")
        return self.emit(before, after)

    def emit(self, before: Dict[str, Any],
             after: Dict[str, Any]) -> Dict[str, Any]:
        tasks = []
        for row in self.results:
            tasks.append({"status": "passed" if row["browser"].get("ok")
                          else "unverified"})
        report = {
            "run_id": self.run_id,
            "mode": self.mode,
            "generated_at": datetime.now(timezone.utc).isoformat(
                timespec="seconds"),
            "orchestration": list(self.trace),
            "personas": self.results,
            "reference_personas": {
                "names": list(REFERENCE_PERSONAS),
                "extraction": REFERENCE_EXTRACTION_DISPOSITION,
                "reason": REFERENCE_EXTRACTION_REASON,
            },
            "containment": {
                "before": before, "after": after,
                "non_run_membership_unchanged":
                    before.get("non_run_id_set_sha256")
                    == after.get("non_run_id_set_sha256"),
                "non_run_onboarding_unchanged":
                    before.get("non_run_onboarding_state_sha256")
                    == after.get("non_run_onboarding_state_sha256"),
            },
            "denominators": summarize_tasks(tasks),
            "template_supplied_fields": list(TEMPLATE_SUPPLIED_FIELDS),
            "deletion": {"performed": False, "call_sites": 0},
        }
        (self.out_dir / "report.json").write_text(
            json.dumps(report, indent=1), encoding="utf-8")
        (self.out_dir / "report.html").write_text(
            _render_html(report), encoding="utf-8")
        self.ledger.write_erasure_manifest()
        return report


def _render_html(report: Dict[str, Any]) -> str:
    """A readable report. Deliberately plain and self-contained."""
    def esc(value: Any) -> str:
        return (str(value).replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;"))
    rows = "".join(
        f"<tr><td>{esc(p['persona'])}</td><td><code>{esc(p['person_id'])}</code></td>"
        f"<td>{esc(p['profile_seed'].get('paused'))}</td>"
        f"<td>{esc(len(p['conversation'].get('turns', [])))}</td>"
        f"<td>{esc(p['browser'].get('ok'))}</td></tr>"
        for p in report.get("personas", []))
    c = report.get("containment", {})
    return f"""<!doctype html><meta charset="utf-8">
<title>Narrator cohort — {esc(report.get('run_id'))}</title>
<style>body{{font:15px/1.5 system-ui,sans-serif;margin:2rem;max-width:60rem}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;
padding:.4rem .6rem;text-align:left}}code{{font-size:.85em}}
.warn{{background:#fff4e5;padding:.6rem;border-left:3px solid #e59700}}</style>
<h1>Narrator cohort acceptance</h1>
<p>Run <code>{esc(report.get('run_id'))}</code> · mode
<strong>{esc(report.get('mode'))}</strong> ·
{esc(report.get('generated_at'))}</p>
<h2>Personas</h2>
<table><tr><th>Persona</th><th>person_id</th><th>Seed paused</th>
<th>Turns</th><th>Browser ok</th></tr>{rows}</table>
<h2>Denominators</h2><pre>{esc(json.dumps(report.get('denominators'), indent=1))}</pre>
<h2>Containment</h2>
<p>Non-run membership unchanged:
<strong>{esc(c.get('non_run_membership_unchanged'))}</strong><br>
Non-run onboarding rows unchanged:
<strong>{esc(c.get('non_run_onboarding_unchanged'))}</strong></p>
<p class="warn">These hashes prove stable membership and unchanged onboarding
rows for narrators outside this run. They do <em>not</em> prove that no read
occurred, nor that every column of every row is unchanged.</p>
<h2>Deletion</h2>
<p>Nothing was deleted. <code>erasure-manifest.json</code> is an inventory for
a human to act on later, with explicit authorization, through the product
hard-delete path.</p>
"""


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

    # ── LIVE ──────────────────────────────────────────────────────────
    #
    # `--full` stays closed. The quick run is wired and offline-tested;
    # the full cohort opens only after a quick run has been inspected,
    # so twelve narrators are never created on the strength of a test
    # suite alone.
    if args.full:
        print("REFUSED: --full is not open yet. Run --quick --live, inspect "
              "its report and artifact inventory, then the full cohort can "
              "be authorized.", file=sys.stderr)
        return 3

    mode = "quick" if args.quick else "resume"
    try:
        personas = load_personas(quick=True)
    except CohortRefusal as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 4

    if args.only_persona:
        wanted = {_norm(p) for p in args.only_persona}
        personas = [p for p in personas if _norm(p["label"]) in wanted]
    lanes = list(args.only_lane or LANES)

    run_id = args.resume or new_run_id()
    out_dir = EVAL_ROOT / run_id
    if args.resume and not out_dir.is_dir():
        print(f"REFUSED: no run to resume at {out_dir}", file=sys.stderr)
        return 4

    run = LiveRun(personas=personas, lanes=lanes, mode="quick",
                  out_dir=out_dir, transport=Transport(),
                  ui_url=os.environ.get(
                      "HORNELORE_UI_URL",
                      "http://localhost:8082/ui/hornelore1.0.html"),
                  run_id=run_id)
    try:
        report = run.execute()
    except CohortRefusal as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 4
    print(json.dumps({
        "run_id": report["run_id"],
        "out_dir": str(out_dir),
        "personas": [p["persona"] for p in report["personas"]],
        "denominators": report["denominators"],
        "containment_unchanged": (
            report["containment"]["non_run_membership_unchanged"]
            and report["containment"]["non_run_onboarding_unchanged"]),
        "deleted": report["deletion"]["performed"],
    }, indent=1))
    return 0


if __name__ == "__main__":      # pragma: no cover
    sys.exit(main())
