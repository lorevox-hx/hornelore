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
    endpoint requesting `testing_only=true`. Consent is never forged.
  * Every created narrator carries the run id in its display name, and
    its UUID is recorded to `artifacts.json` BEFORE anything else runs.
  * Selection after creation is BY UUID ONLY. Display names are for
    humans; two runs can share one.
  * **Nothing is ever deleted.** `erasure-manifest.json` is written for
    later use by a human, and this program has no deletion path at all.

── WHAT AUTHORIZES TOUCHING A NARRATOR (corrected 2026-08-30) ────────

**The artifact journal, and nothing else.** A UUID this run wrote to
`artifacts.json` is one this run created; every other narrator is
refused, whatever it is called.

`testing_only=true` does NOT establish synthetic status and must never
be described as doing so. It is an intake/consent behaviour: the route
uses it to skip consent attestations and echoes it in that one response.
It is **not a `people` column**, `create_person` accepts no such
argument, and the durable row intake writes is `narrator_type="live"` —
identical to a family narrator's. Intake also writes profile and
bio-fact data regardless. The manifest records
`testing_only_requested` as a fact about the REQUEST, not as a
classification the database holds.

The `ZZ COHORT <run_id> ·` display-name prefix is an **operator
affordance** — how a human recognises test data in the picker. It is
checked for consistency and recorded; it authorizes nothing. Nothing in
this runner ever looks a narrator up by display name, so a real narrator
someone happened to name "ZZ COHORT ..." is still refused.

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

#: The lanes this instrument ACTUALLY EXECUTES.
#:
#: ── "behavior" AND "extraction" REMOVED, 2026-08-30 ────────────────────
#:
#: They were advertised in the plan, printed in every report and offered
#: as `--only-lane` choices, and nothing in `LiveRun.execute` ran either
#: one. The live run walked create → pause → turns → era-reuse → browser
#: → inventory and stopped. A plan that lists work nobody does is worse
#: than a short plan: it is read as coverage.
#:
#: They are not stubbed here. Naming what is missing belongs in the work
#: list, not in a tuple that makes the runner look wider than it is.
LANES = ("inventory", "conversation", "era",
         "ui", "traveldoc", "isolation", "persistence")

#: Named so their absence is stated rather than inferred from a gap.
NOT_EXECUTED_LANES = {
    "behavior": "no behavioural scoring in this runner; the parent-session "
                "rehearsal harness is what scores Lori's replies",
    "extraction": "no extraction lane; /api/extract-fields is never called",
}

#: Which orchestration steps each executed lane owns. Used to make
#: `--only-lane` actually control execution instead of being recorded and
#: ignored.
LANE_STEPS = {
    "conversation": ("model_turns",),
    "era": ("era_evidence",),
    "ui": ("browser_traversal",),
    "traveldoc": ("browser_traversal",),
    "isolation": ("browser_traversal",),
    "persistence": ("browser_traversal",),
    "inventory": ("delete_inventory_read",),
}

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
# ── `assert_synthetic` was REMOVED, 2026-08-30 ────────────────────────
#
# It refused any person whose row was not `testing_only: True` or
# `narrator_type: "reference"`, and it was called on the row read back
# straight after creation.
#
# It could never have passed. `testing_only` is not a `people` column,
# `create_person` accepts no such parameter, and intake writes
# `narrator_type="live"` — so the guard would have refused the narrator
# this runner had just created, on the first persona of the first run.
# A mocked transport that returned `testing_only: True` is what hid it.
#
# Deleted rather than rewired, because its premise is the false one: no
# field on the product row distinguishes a cohort narrator from a family
# narrator. `Ledger.require_journaled` is the authority — a UUID this run
# recorded — and `verify_identity` additionally requires the run's
# display-name marker as an operator affordance.


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
            "storage_paths": [], "notes": [], "identity_checks": [],
        }
        # ── AN EXISTING JOURNAL IS LOADED, NEVER OVERWRITTEN ──────────
        #
        # This used to write the empty structure unconditionally, so
        # constructing a RESUMED run truncated `artifacts.json` — the
        # record of every narrator the interrupted attempt had already
        # created. Those narrators would then be refused by
        # `require_journaled` (the run no longer knew it made them) AND
        # dropped from `erasure-manifest.json`, leaving orphans with no
        # inventory. The journal exists to prevent exactly that, so
        # destroying it on resume defeated its whole purpose.
        if self.path.is_file():
            try:
                existing = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                existing = None
            if isinstance(existing, dict) and existing.get("people") is not None:
                for key, value in existing.items():
                    self.data[key] = value
                self.data["resumed_at"] = datetime.now(
                    timezone.utc).isoformat(timespec="seconds")
        self._flush()

    def add_person(self, person_id: str, display_name: str, source: str,
                   *, testing_only_requested: bool = True) -> None:
        self.data["people"].append({
            "person_id": person_id,
            "display_name": display_name,
            "source": source,
            # A FACT ABOUT THE INTAKE REQUEST, not a database
            # classification. `testing_only` is not a `people` column and
            # `create_person` takes no such argument; intake uses it only
            # to skip consent attestations, and the durable row is
            # `narrator_type="live"` either way. Recorded here so the
            # manifest says what was asked for without implying the
            # database remembers it.
            "testing_only_requested": bool(testing_only_requested),
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        self._flush()

    def person_for_source(self, source: str) -> Optional[Dict[str, Any]]:
        """The narrator this run already created for a persona, if any.

        ── WHY A RESUME MUST NOT CREATE AGAIN, 2026-08-30 ──────────────

        *(It did. `create_narrator` ran unconditionally, so resuming an
        interrupted run POSTed intake a second time and the journal went
        from two narrators to four. Worse, the turn checkpoint is keyed
        by persona rather than by UUID, so the freshly created duplicates
        were told their turns were already done and received NONE — two
        orphaned, empty narrators, while the report described turns
        belonging to the first pair.*

        *Matched on `source`, the harness stem, because that is stable
        across runs. The display name is not used: it carries the run id
        and is an operator affordance, never a lookup key.)*
        """
        for row in self.data.get("people", []):
            if row.get("source") == source:
                return row
        return None

    def is_journaled(self, person_id: str) -> bool:
        return any(p["person_id"] == str(person_id)
                   for p in self.data.get("people", []))

    def require_journaled(self, person_id: str) -> Dict[str, Any]:
        """THE durable authority for "this run may touch this narrator".

        ── WHY NOT `testing_only`, 2026-08-30 ──────────────────────────

        *(This guard used to be `assert_synthetic` on the row read back
        after creation, and that was doubly wrong. `testing_only` is not
        persisted — it is not a column in any migration, `create_person`
        accepts no such parameter, and intake uses it only to bypass
        consent attestations. The durable row is `narrator_type="live"`,
        exactly like a family narrator's.*

        *So the check could not have passed: the run would have created
        its first narrator and then REFUSED it. A mocked transport that
        returned `testing_only: True` from the GET is what hid this,
        which is its own lesson about fakes that are kinder than the
        product.*

        *The journal is the authority instead. A UUID this run wrote to
        `artifacts.json` is one this run created; anything else is
        somebody else's narrator, whatever it is called.)*
        """
        for row in self.data.get("people", []):
            if row["person_id"] == str(person_id):
                return row
        raise CohortRefusal(
            f"{person_id} is not journaled by this run. Only narrators this "
            "run created may be touched, and the artifact journal — not a "
            "display name and not any field on the product row — is what "
            "establishes that.")

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


#: The full cohort is exactly this: ten long-form harness personas plus
#: the two QA templates. Written down as an arithmetic expectation so a
#: silent drop is a refusal rather than a smaller run nobody noticed.
FULL_COHORT_SIZE = len(COHORT_HARNESSES) + len(QA_TEMPLATES)


def assert_full_selection(personas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Refuse unless `--full` selected the whole configured cohort.

    `load_personas` SKIPS SILENTLY — a harness that fails to import, or
    that loses `intake: testing_only`, simply does not appear, and the
    run proceeds with eleven. That is the failure this exists to catch:
    a cohort run is a claim about coverage, and eleven-of-twelve
    reported as a full run is a false claim.

    Returns the counted shape so the caller can print it.
    """
    got_harness = {p["harness"] for p in personas if p["source"] == "harness"}
    got_template = {p["label"] for p in personas
                    if p["source"] == "qa_template"}
    problems: List[str] = []

    missing_h = set(COHORT_HARNESSES) - got_harness
    if missing_h:
        problems.append(
            "harness personas missing (not importable, or no longer "
            f"intake: testing_only): {sorted(missing_h)}")
    extra_h = got_harness - set(COHORT_HARNESSES)
    if extra_h:
        problems.append(f"unconfigured harness personas: {sorted(extra_h)}")

    missing_t = set(QA_TEMPLATES) - got_template
    if missing_t:
        problems.append(f"QA template fixtures missing: {sorted(missing_t)}")
    extra_t = got_template - set(QA_TEMPLATES)
    if extra_t:
        problems.append(f"unconfigured templates: {sorted(extra_t)}")

    if len(personas) != FULL_COHORT_SIZE:
        problems.append(f"expected exactly {FULL_COHORT_SIZE} narrators, "
                        f"selected {len(personas)}")

    if problems:
        raise CohortRefusal(
            "--full must run the whole configured cohort or refuse. "
            + "; ".join(problems)
            + ". Fix the selection rather than accepting a smaller run: a "
              "partial cohort reported as full is a false coverage claim.")
    return {"narrators": len(personas),
            "harness_personas": len(got_harness),
            "qa_templates": len(got_template)}


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
        # The plan is where a reader forms an expectation of coverage, so
        # the gaps belong here rather than only in the report afterwards.
        "lanes_not_implemented": dict(NOT_EXECUTED_LANES),
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
        # ── EVERYTHING THE TRANSPORT SAW, 2026-08-30 ──────────────────
        #
        # This returned `{"text":…, "events": len(events), "era":…}` and
        # `run_turns` then kept only `len(text)`. Lori's words were
        # fetched and thrown away, so the report could not answer the one
        # question the cohort exists to ask — did she say something
        # appropriate to this era? A character count is not evidence.
        #
        # The `done` event is kept whole (minus token deltas, which are
        # just `final_text` again in pieces) because it is where the
        # server puts turn ids and any per-turn metadata it chooses to
        # surface. Capturing the envelope rather than named fields means
        # a future server addition arrives in the report for free.
        done = next((e for e in reversed(events)
                     if isinstance(e, dict) and e.get("type") == "done"), {})
        errors = [e for e in events
                  if isinstance(e, dict) and e.get("type") == "error"]
        return {
            "text": final_text,
            "chars": len(final_text or ""),
            "event_count": len(events),
            "era_sent": era,          # what crossed the WS boundary
            "era": era,               # kept: existing readers use this key
            "done_event": {k: v for k, v in done.items() if k != "delta"},
            "ws_errors": errors,
        }

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
        # Recorded so the report can be checked against the product row
        # without rerunning anything: this is the string the browser
        # waited for, and passing the wrong one is what made every UI
        # lane time out on r20260830-011413-fa48c7.
        evidence: Dict[str, Any] = {"exit_code": proc.returncode,
                                    "expected_name_used": expected_name}
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
                 run_id: Optional[str] = None,
                 replay_of: Optional[str] = None,
                 source_ledger: Optional["Ledger"] = None):
        self.personas = personas
        self.lanes = lanes
        self.mode = mode
        self.out_dir = out_dir
        self.transport = transport
        self.ui_url = ui_url
        self.db_path = db_path
        self.run_id = run_id or new_run_id()
        #: The run whose narrators this one re-measures, if any.
        self.replay_of = replay_of
        #: The ORIGINAL run's journal, opened READ-ONLY for its UUIDs.
        #: A replay writes its own journal in its own directory; the
        #: source is never reopened for writing and never truncated.
        self.source_ledger = source_ledger
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.ledger = Ledger(self.out_dir, self.run_id)
        self.checkpoint = Checkpoint(self.out_dir)
        #: Ordered record of what actually happened, asserted by tests.
        self.trace: List[str] = []
        self.results: List[Dict[str, Any]] = []
        self.era_evidence: Dict[str, Any] = {}
        #: The MARKED display name the product row actually carries, per
        #: person_id, as read back in `verify_identity`. The browser waits
        #: on this string; the fixture label is not what the picker shows.
        self.display_names: Dict[str, str] = {}

    # ── step helpers ─────────────────────────────────────────────────
    def _step(self, name: str) -> None:
        if name not in ORCHESTRATION:
            raise CohortRefusal(f"undeclared orchestration step: {name!r}")
        self.trace.append(name)

    def conversation_id_for(self, person_id: str) -> str:
        """The conversation this run speaks into.

        ── A REPLAY GETS ITS OWN CONVERSATION, 2026-08-30 ─────────────

        An ordinary run keys the conversation on the RUN id, so resuming
        continues the same thread. A REPLAY must not: the journaled
        Alex thread `cohort-r20260830-011413-fa48c7-c6f78b9b` carries the
        phantom-presentation defect evidence — the turn where
        `presented(childhood_home, epoch 2)` was committed against prose
        that asked nothing — and that thread is preserved deliberately.
        Appending new turns to it would bury the evidence inside a later,
        healthy conversation.

        So a replay reuses the PERSON and takes a new CONVERSATION. No
        narrator is created, no journal is rewritten, and the original
        thread is left exactly as it was.
        """
        if self.replay_of:
            return f"replay-{self.run_id}-{person_id[:8]}"
        return f"cohort-{self.run_id}-{person_id[:8]}"

    # ── lane selection ───────────────────────────────────────────────
    def _lane_on(self, lane: str) -> bool:
        return lane in self.lanes

    def _browser_lanes_on(self) -> bool:
        """One subprocess serves four lanes, so any of them opens it."""
        return any(self._lane_on(lane)
                   for lane in ("ui", "traveldoc", "isolation", "persistence"))

    @staticmethod
    def _lane_off(lane: str) -> Dict[str, Any]:
        """A lane that did not run says so, in the shape of a result.

        `None` would be indistinguishable from a lane that ran and found
        nothing, which is the whole class of defect this repair is about.
        """
        return {"executed": False, "lane": lane,
                "reason": "not selected by --only-lane"}

    def run_person_ids(self) -> List[str]:
        """The narrators THIS run touches — the containment exclusion set.

        ── THE TWO HASHES MUST COVER THE SAME POPULATION, 2026-08-31 ──

        The baseline passed `[]`, which is right for an ordinary run: no
        narrator exists yet, so nothing can be excluded. On a REPLAY the
        narrators already exist, so they sat INSIDE the baseline's
        "non-run" population and were excluded from the after-snapshot —
        10 rows compared against 8, guaranteeing a mismatch.

        `containment_unchanged: false` on the invalid replay was that,
        not a containment breach. A comparison between different
        populations is not a comparison.

        On a replay the ids are known up front, from the source journal.
        On an ordinary run they are not, and `[]` remains correct.
        """
        if self.source_ledger is not None:
            return [str(r.get("person_id")) for r in
                    (self.source_ledger.data.get("people") or [])
                    if r.get("person_id")]
        return []

    def _baseline(self) -> Dict[str, Any]:
        """Captured once. A resume reads the stored one, never re-takes it."""
        path = self.out_dir / "containment-before.json"
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        snap = containment_snapshot(
            self.run_person_ids(), db_path=self.db_path,
            people_rows=self.transport.list_people())
        path.write_text(json.dumps(snap, indent=1), encoding="utf-8")
        return snap

    def create_narrator(self, persona: Dict[str, Any]) -> str:
        """Intake, then journal BEFORE anything else touches the network."""
        self._step("create_intake")
        # A RESUME REUSES, IT DOES NOT RE-CREATE. If this run already
        # journaled a narrator for this persona, that narrator IS the
        # persona for the rest of the run; creating a second one would
        # orphan the first and strand the completed turns against it.
        # A REPLAY LOOKS IN THE SOURCE RUN'S JOURNAL FIRST. Its own
        # journal starts empty, so without this it would fall through to
        # intake and create a duplicate Alex — the exact thing a replay
        # exists to avoid.
        existing = None
        if self.source_ledger is not None:
            existing = self.source_ledger.person_for_source(persona["harness"])
            if existing is not None:
                # Recorded in THIS run's journal too, as a reuse, so the
                # replay's own inventory is complete without the source
                # being written to.
                if self.ledger.person_for_source(persona["harness"]) is None:
                    self.ledger.add_person(
                        existing["person_id"], existing.get("display_name", ""),
                        persona["harness"],
                        testing_only_requested=bool(
                            existing.get("testing_only_requested", True)))
                    self.ledger.add("notes", {
                        "replay_of": self.replay_of,
                        "reused_person_id": existing["person_id"],
                        "why": "replay re-measures an existing narrator; "
                               "no intake, no new person"})
        if existing is None:
            existing = self.ledger.person_for_source(persona["harness"])
        if existing is not None:
            self.ledger.add("notes", {
                "reused_existing_narrator": existing["person_id"],
                "persona": persona["label"],
                "why": "resumed run; intake is not repeated"})
            self._step("journal_uuid")      # already journaled; order kept
            self._step("verify_identity")
            return self.verify_identity(existing["person_id"])

        # `testing_only` is REQUESTED here, and that is all it is: an
        # intake/consent behaviour, recorded in the manifest as a fact
        # about the request. It is not persisted, so it proves nothing
        # about this narrator after creation. The safety boundary is the
        # journal, checked in `verify_identity`.
        if self.replay_of:
            # Unreachable when the source journal owns this persona, which
            # is the only supported replay. Refusing rather than creating
            # is the difference between a re-measurement and a duplicate.
            raise CohortRefusal(
                f"replay of {self.replay_of} has no journaled narrator for "
                f"{persona['label']!r}; refusing to create one")
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
        return self.verify_identity(person_id, payload)

    def verify_identity(self, person_id: str,
                        payload: Optional[Dict[str, Any]] = None) -> str:
        """Journal first, then read the row back and check consistency.

        The ORDER of the two checks is the point. Authorization comes
        from `require_journaled` — a UUID this run created. The product
        row is then read to confirm the narrator is really there and
        really carries the marker, but nothing about that row is what
        makes it touchable: the durable row is `narrator_type="live"`
        and carries no `testing_only` field at all.

        The marked display name is an OPERATOR AFFORDANCE — it is how a
        human recognises test data in the picker. It is recorded and
        checked for consistency, and it authorizes nothing. There is no
        lookup by display name anywhere in this runner, so a real
        narrator someone christened "ZZ COHORT ..." is still refused by
        the journal.
        """
        journal_row = self.ledger.require_journaled(person_id)
        vstatus, vbody = self.transport.get(f"/api/people/{person_id}")
        person = (vbody or {}).get("person") if isinstance(vbody, dict) else None
        if vstatus != 200 or not isinstance(person, dict):
            raise CohortRefusal(
                f"created {person_id} but could not read it back: HTTP {vstatus}")

        actual_id = str(person.get("id") or person.get("person_id") or "")
        if actual_id and actual_id != person_id:
            raise CohortRefusal(
                f"identity mismatch: asked for {person_id}, row says {actual_id}")

        display = str(person.get("display_name") or "")
        # ── A REPLAY CHECKS THE SOURCE RUN'S MARKER, 2026-08-30 ───────
        #
        # The narrator was stamped by the run that CREATED it. Comparing
        # against this run's prefix would refuse every replayed narrator
        # — correctly by its own logic, and uselessly, since a
        # re-measurement must by definition meet somebody else's
        # narrator.
        #
        # The guard does not weaken: the marker must still be present,
        # so a real narrator is still refused, and authority still comes
        # from `require_journaled` above rather than from any name.
        expected_marker = run_prefix(self.replay_of or self.run_id)
        self.ledger.add("identity_checks", {
            "person_id": person_id,
            "display_name": display,
            "marker_present": display.startswith(expected_marker),
            "narrator_type": person.get("narrator_type"),
            "row_has_testing_only_field": "testing_only" in person,
            "testing_only_requested": journal_row.get(
                "testing_only_requested"),
            "authority": "artifact journal (UUID), not display name",
        })
        if not display.startswith(expected_marker):
            raise CohortRefusal(
                f"{person_id} was created without this run's marker "
                f"({expected_marker!r}); refusing to continue with a narrator "
                "an operator cannot recognise as test data.")
        # ── THE NAME THE UI ACTUALLY SHOWS, 2026-08-30 ────────────────
        #
        # Kept because the browser lane has to wait for it. `traverse`
        # passed `persona["label"]` — the FIXTURE name, "Alex Eunseo Park
        # (they/them)" — while `mark_intake_payload` had stamped the row
        # as "ZZ COHORT <run> · Alex". The helper waits up to 60s for the
        # active-narrator label to contain the string it was given, so
        # every browser lane was destined to time out on a narrator that
        # had opened perfectly well. The row is the authority on its own
        # display name, and this is where the row was read.
        self.display_names[person_id] = display
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

    def assert_chapters_populated(self) -> Dict[str, int]:
        """Every selected chapter must carry narrator words. Pre-network.

        Returns the per-persona word counts, which the caller prints so a
        human sees positive numbers before anything is sent.
        """
        counts: Dict[str, int] = {}
        empty: List[str] = []
        scripted = 0
        for persona in self.personas:
            chapters = persona.get("chapters") or []
            if not chapters:
                # The two QA templates are fixtures, not scripted
                # conversations — `load_personas` gives them `chapters:
                # []` on purpose, and they exercise intake, Profile Seed
                # and the UI surfaces instead. Refusing them here would
                # have made `--full` refuse on its first run, every run.
                # A HARNESS persona with no chapters is still a defect.
                if persona.get("source") == "qa_template":
                    counts[persona["label"]] = 0
                    continue
                empty.append(f"{persona['label']}: no chapters at all")
                continue
            scripted += 1
            words = 0
            for index, chapter in enumerate(chapters):
                text = getattr(chapter, "text", None)
                if not isinstance(text, str) or not text.strip():
                    empty.append(
                        f"{persona['label']} chapter {index} "
                        f"({getattr(chapter, 'runtime71_era', '?')}) has no text")
                    continue
                words += len(text.split())
            if not words:
                empty.append(f"{persona['label']}: zero narrator words")
            counts[persona["label"]] = words
        if empty:
            raise CohortRefusal(
                "REFUSING to send empty narrator turns. "
                + "; ".join(empty)
                + ". An empty turn measures nothing and makes Lori answer "
                  "silence, which is what invalidated the 2026-08-30 run.")

        chapter_total = sum(len(p.get("chapters") or []) for p in self.personas)
        word_total = sum(counts.values())
        print(f"  [cohort] {len(self.personas)} narrators, "
              f"{scripted} scripted, "
              f"{len(self.personas) - scripted} fixture-only, "
              f"{chapter_total} chapters, {word_total} narrator words")
        for label, words in counts.items():
            n = len(next(p["chapters"] for p in self.personas
                         if p["label"] == label))
            suffix = "  (fixture: intake + surfaces, no model turn)" if not n else ""
            print(f"  [chapters] {label}: {n} chapters, "
                  f"{words} narrator words{suffix}")
        return counts

    def _seed_state(self, person_id: str) -> Dict[str, Any]:
        """Profile Seed state as the server reports it, for one turn."""
        status, body = self.transport.get(
            "/api/interview/profile-seed?person_id="
            + urllib.parse.quote(person_id))
        if status != 200 or not isinstance(body, dict):
            return {"http": status, "unavailable": True}
        return {
            "status": body.get("status"),
            "active_topic_id": body.get("active_topic_id"),
            "version": body.get("version"),
            "presentation_epoch": body.get("presentation_epoch"),
            "remaining": body.get("remaining_topics"),
        }

    #: How long to wait for background extraction to settle after a turn.
    #: `[extract-turn] extract_fields_scheduled` runs as a background task
    #: AFTER the WebSocket `done`, so reading facts immediately measures
    #: the state before extraction ran and reports every turn as
    #: extracting nothing. Observed settle time in the live log is ~2.3s.
    EXTRACTION_POLL_SECONDS = 12.0
    EXTRACTION_POLL_INTERVAL = 0.75

    def _facts(self, person_id: str) -> Dict[str, Any]:
        """Extracted facts WITH VALUES, not just a count.

        A count cannot answer "was this fact placed in the right era" or
        "which turn produced it", which are the questions the cohort
        exists to ask. The rows are kept whole, minus nothing, because
        the operator reviewing them needs the value and its provenance.
        """
        status, body = self.transport.get(
            "/api/facts/list?person_id=" + urllib.parse.quote(person_id))
        if status != 200 or not isinstance(body, dict):
            return {"http": status, "unavailable": True, "rows": {}}
        facts = body.get("facts") or body.get("items") or []
        if not isinstance(facts, list):
            return {"http": status, "unavailable": True, "rows": {}}
        rows: Dict[str, Any] = {}
        for f in facts:
            if not isinstance(f, dict):
                continue
            key = str(f.get("field_key") or "")
            if not key:
                continue
            rows[key] = {
                "value": f.get("value"),
                "status": f.get("status"),
                "era": f.get("era") or f.get("era_id"),
                "source_turn": (f.get("source_turn_id") or f.get("turn_id")
                                or f.get("provenance_turn_id")),
                "source": f.get("source"),
                "last_updated": f.get("last_updated"),
            }
        return {"count": len(rows), "keys": sorted(rows), "rows": rows}

    def _facts_settled(self, person_id: str,
                       before: Dict[str, Any]) -> Dict[str, Any]:
        """Poll until extraction changes something, or time out. BOUNDED.

        Returns the after-snapshot with `settled` / `timed_out` recorded.
        A timeout is NOT a failure of the product — extraction may
        legitimately find nothing — so it is reported as what it is: this
        instrument stopped waiting. Reporting a timeout as "extracted
        nothing" would be the same class of lie as counting characters.
        """
        deadline = time.time() + self.EXTRACTION_POLL_SECONDS
        baseline_keys = set((before or {}).get("keys") or [])
        last = self._facts(person_id)
        while time.time() < deadline:
            if set(last.get("keys") or []) != baseline_keys:
                last["extraction"] = {
                    "settled": True, "timed_out": False,
                    "waited_s": round(self.EXTRACTION_POLL_SECONDS
                                      - (deadline - time.time()), 2)}
                return last
            time.sleep(self.EXTRACTION_POLL_INTERVAL)
            last = self._facts(person_id)
        last["extraction"] = {
            "settled": False, "timed_out": True,
            "waited_s": self.EXTRACTION_POLL_SECONDS,
            "note": ("no fact change within the window; extraction may have "
                     "found nothing, or may not have finished. This "
                     "instrument stopped waiting — it did not observe a "
                     "negative result.")}
        return last

    def _life_map(self, person_id: str) -> Dict[str, Any]:
        """Where the chronology/Life Map places what is known.

        Captured because "are facts placed in the correct era" cannot be
        answered from `bio_facts` alone.
        """
        status, body = self.transport.get(
            "/api/chronology-accordion?person_id="
            + urllib.parse.quote(person_id))
        if status != 200 or not isinstance(body, dict):
            return {"http": status, "unavailable": True}
        decades = body.get("decades") or body.get("items") or []
        return {"http": status,
                "decade_count": len(decades) if isinstance(decades, list) else None,
                "payload": body}

    def run_turns(self, persona: Dict[str, Any], person_id: str) -> Dict[str, Any]:
        """Sequential. One turn at a time, checkpointed as it goes.

        ── THE RECORD IS THE EVIDENCE, 2026-08-30 ────────────────────
        Each turn used to store `{"index", "era", "chars"}`. Reviewing
        Lori from that is impossible: a length cannot show whether she
        recognised the era, repeated herself, or answered at all. Every
        field below exists so a human can read the exchange and judge it.

        WHAT IS NOT CAPTURED, and is marked so rather than faked:
        `current_pass` and `effective_pass` are HARDCODED to "pass2a" in
        `harness_lib._send_turn_and_capture`, so they are constants of
        this instrument and not readings of a browser. This path can
        therefore never observe pass reconciliation. The browser half
        does that; this half must not pretend to.
        """
        self._step("model_turns")
        conv_id = self.conversation_id_for(person_id)
        turns: List[Dict[str, Any]] = []
        for index, chapter in enumerate(persona.get("chapters", [])):
            lane_key = f"turn{index}"
            if self.checkpoint.is_done(persona["label"], lane_key):
                prior = self.checkpoint.done.get(
                    self.checkpoint.key(persona["label"], lane_key), {})
                # Carry the PRIOR record forward rather than a stub, or a
                # resumed run reports a turn it cannot show anybody.
                turns.append({**prior, "index": index,
                              "reused_from_checkpoint": True})
                continue

            # ── `chapter.text`, AND NO getattr DEFAULT, 2026-08-31 ──
            #
            # This read `getattr(chapter, "narrator_text", "")`.
            # `ChapterConfig` declares `text: str  # the narrator
            # monologue` and has no `narrator_text` field, so the default
            # fired on EVERY chapter and every narrator turn the cohort
            # has ever sent was EMPTY — including the 2026-08-30 live run.
            #
            # Lori was answering silence. She filled both sides of the
            # conversation, inventing the narrator's memories and then
            # reflecting on her own invention, which is why Walt's
            # transcript repeats Aunt Mabel's kitchen four turns running.
            # Both that run and replay-r20260831-032111-cf4b5a are void
            # as evidence about Lori.
            #
            # A direct attribute access raises on a renamed field. The
            # default is what turned a rename into ten silent turns.
            narrator_text = chapter.text
            era_requested = getattr(chapter, "runtime71_era", "unknown")
            seed_before = self._seed_state(person_id)
            facts_before = self._facts(person_id)

            result = self.transport.model_turn(
                person_id=person_id, text=narrator_text, era=era_requested,
                speaker_name=persona["label"], conv_id=conv_id)

            seed_after = self._seed_state(person_id)
            # BOUNDED WAIT. Extraction is a background task that starts
            # after `done`; reading immediately measured the world before
            # it ran.
            facts_after = self._facts_settled(person_id, facts_before)
            life_map_after = self._life_map(person_id)

            record = {
                "index": index,
                "person_id": person_id,
                "conversation_id": conv_id,
                "era_requested": era_requested,
                "era_sent": result.get("era_sent"),
                # Constants of the transport, named as such.
                "runtime_pass_sent": "pass2a (hardcoded by harness_lib)",
                "narrator_text": narrator_text,
                "lori_text": result.get("text") or "",
                "chars": result.get("chars"),
                "done_event": result.get("done_event"),
                "ws_errors": result.get("ws_errors") or [],
                "profile_seed_before": seed_before,
                "profile_seed_after": seed_after,
                "facts_before": facts_before,
                "facts_after": facts_after,
                "extraction": facts_after.get("extraction"),
                "facts_added": {
                    k: v for k, v in (facts_after.get("rows") or {}).items()
                    if k not in set((facts_before or {}).get("keys") or [])},
                "life_map_after": life_map_after,
            }
            turns.append(record)
            # The LEDGER stays a thin inventory — ids and shape, no prose.
            # Narrator and Lori text belong in the report, which is the
            # thing a human reads; duplicating it into the journal would
            # put narrator speech in an artifact whose job is accounting.
            self.ledger.add("turns", {
                "person_id": person_id, "index": index,
                "conversation_id": conv_id,
                "era_sent": record["era_sent"], "chars": record["chars"]})
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
        expected = self.display_names.get(person_id)
        if not expected:
            # verify_identity always runs first and always records it, so
            # this is unreachable in the wired order. Refuse rather than
            # fall back to the fixture label: falling back is what the
            # defect was, and a quiet fallback would restore it.
            raise CohortRefusal(
                f"no verified display name recorded for {person_id}; "
                "refusing to guess what the picker shows")
        return self.transport.browser(
            person_id=person_id, expected_name=expected,
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
        # ── NOTHING IS SENT UNTIL EVERY CHAPTER HAS WORDS, 2026-08-31 ──
        #
        # BEFORE the baseline, before intake, before any socket opens.
        # An empty narrator turn is never a legitimate measurement, and
        # the failure it produces — Lori talking to herself for ten turns
        # — looks like a working run in every summary that counts turns.
        # Refusing costs one message; not refusing cost two whole runs.
        self.assert_chapters_populated()

        self._step("freeze_selection")
        self.checkpoint.set_selection(
            personas=[p["label"] for p in self.personas],
            lanes=self.lanes, mode=self.mode)

        self._step("containment_baseline")
        before = self._baseline()

        for persona in self.personas:
            # The spine is not lane-gated: a narrator has to exist, be
            # verified and have its walk paused before any lane can mean
            # anything. `--only-lane` selects work, it does not remove the
            # ground the work stands on.
            person_id = self.create_narrator(persona)
            seed = self.pause_profile_seed(person_id)

            # ── `--only-lane` NOW CONTROLS EXECUTION, 2026-08-30 ───────
            #
            # It was parsed, validated against LANES, stored in the
            # checkpoint's frozen selection and then never consulted:
            # `execute` called every step unconditionally. So
            # `--only-lane inventory` ran the full model conversation and
            # the whole browser traversal, and the checkpoint recorded a
            # selection that did not describe the run it belonged to.
            conversation = (self.run_turns(persona, person_id)
                            if self._lane_on("conversation")
                            else self._lane_off("conversation"))
            # The era lane READS the conversation lane's turns, so it
            # cannot run without it. Selecting era alone would otherwise
            # report "eras_covered: []" as though the walk covered none.
            era = (self.reuse_era_evidence(persona, conversation)
                   if (self._lane_on("era") and self._lane_on("conversation"))
                   else self._lane_off("era"))
            browser = (self.traverse(persona, person_id)
                       if self._browser_lanes_on()
                       else self._lane_off("ui"))
            inventory = (self.read_delete_inventory(person_id)
                         if self._lane_on("inventory")
                         else self._lane_off("inventory"))
            self.results.append({
                "persona": persona["label"], "person_id": person_id,
                "display_name": self.display_names.get(person_id),
                "profile_seed": seed, "conversation": conversation,
                "era": era, "browser": browser,
                "delete_inventory": inventory,
            })

        self._step("containment_after")
        # The SAME exclusion set the baseline used, plus anything this run
        # created (nothing, on a replay). Union rather than the results
        # alone, so the two hashes cannot describe different populations.
        _excluded = sorted(set(self.run_person_ids())
                           | {r["person_id"] for r in self.results})
        after = containment_snapshot(
            _excluded, db_path=self.db_path,
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
            "replay_of": self.replay_of,
            "personas": self.results,
            # ── WHAT RAN, AND WHAT DID NOT, 2026-08-30 ────────────────
            #
            # Stated positively so nobody has to infer coverage from the
            # absence of a complaint.
            "lanes": {
                "selected": list(self.lanes),
                "executed": sorted({
                    lane for lane in self.lanes if lane in LANE_STEPS}),
                "not_implemented": dict(NOT_EXECUTED_LANES),
            },
            "reference_personas": {
                "names": list(REFERENCE_PERSONAS),
                # NOT a result. No reference narrator was opened, read,
                # traversed or extracted from in this run — the runner has
                # no reference lane at all. This block previously reported
                # `extraction: not_applicable` beside real per-persona
                # results, which reads as a lane that ran and returned a
                # disposition. It is a standing policy statement about
                # what would happen IF such a lane existed.
                "executed": False,
                "policy_only": True,
                "extraction_policy": REFERENCE_EXTRACTION_DISPOSITION,
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
    """A readable report. THE EXCHANGES ARE THE REPORT.

    ── WHY THIS IS NOT A TABLE OF COUNTS, 2026-08-30 ─────────────────

    The previous version showed persona, id, paused, turn COUNT and a
    browser boolean. Everything a reviewer actually needs — what the
    narrator said, what Lori said back, and whether her answer belonged
    to the era on screen — was absent, and the underlying record only
    held a character count anyway.

    Era appropriateness is deliberately NOT scored here. No keyword
    matching, no length heuristic. The exchange is printed with the era
    it was sent under and the Profile Seed state either side of it, and
    a human decides. A number that looked like a judgement would be
    worse than no number at all.
    """
    def esc(value: Any) -> str:
        return (str(value if value is not None else "")
                .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    def seed_line(seed: Any) -> str:
        if not isinstance(seed, dict) or seed.get("unavailable"):
            return "<span class='muted'>profile seed unavailable</span>"
        return (f"{esc(seed.get('status'))} · "
                f"topic {esc(seed.get('active_topic_id'))} · "
                f"v{esc(seed.get('version'))} · "
                f"epoch {esc(seed.get('presentation_epoch'))}")

    blocks = []
    for p in report.get("personas", []):
        turns = (p.get("conversation") or {}).get("turns") or []
        by_era: Dict[str, List[Dict[str, Any]]] = {}
        for t in turns:
            by_era.setdefault(str(t.get("era_sent") or t.get("era_requested")
                                  or "unknown"), []).append(t)
        era_html = []
        for era, rows in by_era.items():
            exchanges = []
            for t in rows:
                if t.get("reused_from_checkpoint") and not t.get("lori_text"):
                    exchanges.append(
                        "<p class='muted'>turn %s reused from a checkpoint; "
                        "no text was captured by the run that made it</p>"
                        % esc(t.get("index")))
                    continue
                facts_b = (t.get("facts_before") or {}).get("count")
                facts_a = (t.get("facts_after") or {}).get("count")
                exchanges.append(
                    "<div class='turn'>"
                    f"<div class='meta'>turn {esc(t.get('index'))} · "
                    f"era sent <code>{esc(t.get('era_sent'))}</code> · "
                    f"pass {esc(t.get('runtime_pass_sent'))}</div>"
                    f"<div class='who'>Narrator</div>"
                    f"<blockquote class='narrator'>{esc(t.get('narrator_text'))}</blockquote>"
                    f"<div class='who'>Lori</div>"
                    f"<blockquote class='lori'>{esc(t.get('lori_text'))}</blockquote>"
                    f"<div class='meta'>before: {seed_line(t.get('profile_seed_before'))}"
                    f"<br>after:&nbsp; {seed_line(t.get('profile_seed_after'))}"
                    f"<br>facts {esc(facts_b)} &rarr; {esc(facts_a)}"
                    + ("<br><span class='bad'>ws errors: %s</span>"
                       % esc(len(t.get("ws_errors") or []))
                       if t.get("ws_errors") else "")
                    + "</div></div>")
            era_html.append(
                f"<h4>{esc(era)} <span class='muted'>· {len(rows)} turn(s)</span></h4>"
                + "".join(exchanges))
        blocks.append(
            f"<section class='persona'><h3>{esc(p.get('persona'))}</h3>"
            f"<p class='meta'><code>{esc(p.get('person_id'))}</code><br>"
            f"conversation <code>{esc((p.get('conversation') or {}).get('conversation_id'))}</code></p>"
            + ("".join(era_html) or "<p class='muted'>no turns recorded</p>")
            + "</section>")

    c = report.get("containment", {})
    lanes = report.get("lanes", {})
    missing = "".join(f"<li><code>{esc(k)}</code> — {esc(v)}</li>"
                      for k, v in (lanes.get("not_implemented") or {}).items())
    d = report.get("denominators") or {}
    replay = report.get("replay_of")
    return f"""<!doctype html><meta charset="utf-8">
<title>Narrator cohort — {esc(report.get('run_id'))}</title>
<style>
body{{font:16px/1.6 system-ui,sans-serif;margin:2rem auto;max-width:52rem;color:#1e293b}}
code{{font-size:.85em;background:#f1f5f9;padding:1px 4px;border-radius:3px}}
.persona{{border-top:2px solid #cbd5e1;margin-top:2rem;padding-top:.5rem}}
.turn{{border-left:3px solid #e2e8f0;padding:.4rem 0 .4rem .9rem;margin:1rem 0}}
blockquote{{margin:.25rem 0 .6rem;padding:.5rem .8rem;border-radius:6px}}
.narrator{{background:#f8fafc;border-left:3px solid #94a3b8}}
.lori{{background:#eef2ff;border-left:3px solid #6366f1}}
.who{{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:#64748b}}
.meta{{font-size:13px;color:#64748b}}
.muted{{color:#94a3b8}} .bad{{color:#b91c1c}}
.warn{{background:#fff4e5;padding:.6rem;border-left:3px solid #e59700}}
</style>
<h1>Narrator cohort</h1>
<p>Run <code>{esc(report.get('run_id'))}</code> · mode
<strong>{esc(report.get('mode'))}</strong> · {esc(report.get('generated_at'))}
{"<br>Re-measurement of <code>" + esc(replay) + "</code> — existing narrators, new conversations, nothing created." if replay else ""}</p>

<p class="warn">Era appropriateness is <strong>not scored</strong>. The
exchanges below are printed for a human to judge. Response length is not
evidence of response quality.</p>

<h2>Exchanges</h2>
{''.join(blocks) or "<p class='muted'>no personas recorded</p>"}

<h2>Denominators</h2>
<pre>{esc(json.dumps(d, indent=1))}</pre>

<h2>Lanes</h2>
<p>Executed: <code>{esc(", ".join(lanes.get("executed") or []))}</code></p>
<p class="warn">Not implemented by this runner, and therefore not covered:</p>
<ul>{missing}</ul>
<p>No reference persona was opened, read or extracted from. The reference
block in the JSON is a policy statement, not a result.</p>
<p class="muted">Browser <code>currentPass</code> is not observable on this
path: <code>harness_lib._send_turn_and_capture</code> hardcodes
<code>pass2a</code>, so it is a constant of the instrument rather than a
reading. Pass reconciliation is the browser half's to prove.</p>

<h2>Containment</h2>
<p>Non-run membership unchanged: <strong>{esc(c.get('non_run_membership_unchanged'))}</strong><br>
Non-run onboarding rows unchanged: <strong>{esc(c.get('non_run_onboarding_unchanged'))}</strong></p>
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
    ap.add_argument("--replay", metavar="RUN_ID",
                    help="RE-MEASURE an earlier run's narrators. Reuses its "
                         "journaled UUIDs, performs no intake, creates no "
                         "people, writes a NEW run directory and journal, "
                         "and leaves the original untouched. Use this when "
                         "--resume would return reused_from_checkpoint and "
                         "hand back the same evidence-free rows.")
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
    if not (args.quick or args.full or args.resume or args.replay):
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
    # `--full` WAS closed, and refused here unconditionally: twelve
    # narrators were never to be created on the strength of a test suite
    # alone. It opened on 2026-08-31, on the authority of an inspected
    # two-narrator run — `replay-r20260831-034021-fed7f2`, the first
    # cohort evidence ever taken against real narrator input, after the
    # empty-turn defect was found and fixed.
    #
    # What replaces the refusal is NOT nothing. The gate below is
    # arithmetic on the selection, before any socket is opened:
    # exactly the twelve configured writable synthetic narrators, and
    # positive narrator words in every chapter that exists. A silent
    # drop to eleven — one harness losing `intake: testing_only`, one
    # template file renamed — is exactly what an unchecked `--full`
    # would have run straight past.

    if args.replay and args.resume:
        print("REFUSED: --replay and --resume are different operations. "
              "Resume continues a run; replay re-measures its narrators "
              "in a new run.", file=sys.stderr)
        return 5
    mode = ("replay" if args.replay
            else "quick" if args.quick else "resume")
    # `--full` is the ONLY thing that widens the selection. Replay and
    # resume keep loading the quick two exactly as before: a replay
    # reuses journaled UUIDs from its source run, so widening it would
    # ask for narrators that run never created.
    try:
        personas = load_personas(quick=not args.full)
        if args.full:
            assert_full_selection(personas)
    except CohortRefusal as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 4

    if args.only_persona:
        wanted = {_norm(p) for p in args.only_persona}
        personas = [p for p in personas if _norm(p["label"]) in wanted]
    lanes = list(args.only_lane or LANES)

    source_ledger = None
    if args.replay:
        source_dir = EVAL_ROOT / args.replay
        if not source_dir.is_dir():
            print(f"REFUSED: no run to replay at {source_dir}", file=sys.stderr)
            return 4
        # READ-ONLY. `Ledger.__init__` loads an existing journal rather
        # than truncating it (see its own note), and this replay never
        # calls a mutator on it.
        source_ledger = Ledger(source_dir, args.replay)
        if not source_ledger.data.get("people"):
            print(f"REFUSED: {args.replay} journals no narrators to replay",
                  file=sys.stderr)
            return 4
        run_id = f"replay-{new_run_id()}"
    else:
        run_id = args.resume or new_run_id()
    out_dir = EVAL_ROOT / run_id
    if args.resume and not out_dir.is_dir():
        print(f"REFUSED: no run to resume at {out_dir}", file=sys.stderr)
        return 4

    run = LiveRun(personas=personas, lanes=lanes, mode=mode,
                  out_dir=out_dir, transport=Transport(),
                  ui_url=os.environ.get(
                      "HORNELORE_UI_URL",
                      "http://localhost:8082/ui/hornelore1.0.html"),
                  run_id=run_id, replay_of=args.replay,
                  source_ledger=source_ledger)
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
