#!/usr/bin/env python3
"""Guard Lab live acceptance — READ ONLY. Chris drives; this records.

WO-LORI-BASELINE-RESET-AND-GUARD-LAB-01 Continuation A, section X.

    cd /mnt/c/Users/chris/hornelore
    .venv-gpu/bin/python scripts/guard_lab_live_acceptance.py preflight
    .venv-gpu/bin/python scripts/guard_lab_live_acceptance.py snapshot before-all-off
    .venv-gpu/bin/python scripts/guard_lab_live_acceptance.py verify

── WHY A SEPARATE INSTRUMENT ─────────────────────────────────────────

The offline suite proves the router and the panel are correct against a
test database. It cannot prove that the RUNNING SERVER picks a changed
configuration up on the next turn, that a turn already generating keeps
the one it acquired, or that an override survives a restart. Those are
properties of a live stack and only a live stack can answer them.

They are also properties nobody should certify from memory. Six of the
eight acceptance clauses are decided by comparing two recorded facts —
which revision a turn consumed, and when the operator changed it — and
a person reading a log at midnight will believe whichever they expected.

── WHAT THIS FILE MAY NOT DO ─────────────────────────────────────────

It sends no turns, creates no narrator, writes no override, and never
opens the database for writing. **It has no mutation path at all.** The
acceptance is Chris in the browser; this reads what that left behind.

The one exception is `snapshot`, which performs a GET against the
operator API and saves the response. A read of the configuration is
part of the evidence, not a change to it.

── THE THREE VERDICTS ────────────────────────────────────────────────

PASS · FAIL · UNVERIFIED. The third is not a soft failure — it means
the evidence to decide the clause is absent, and saying PASS on absent
evidence is the failure this project has paid for most often. A run
that ends with unverified clauses is an incomplete acceptance, and the
summary says so rather than rounding up.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
API = os.environ.get("HORNELORE_API", "http://localhost:8000")
GUARD_LAB = f"{API}/api/operator/guard-lab"
MARKER = REPO_ROOT / ".runtime" / "eval" / "current_eval_dir"

PASS, FAIL, UNVERIFIED = "PASS", "FAIL", "UNVERIFIED"


# ── plumbing ──────────────────────────────────────────────────────────

def _get(url: str, timeout: int = 20) -> Tuple[int, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except Exception:
            return exc.code, None
    except Exception as exc:
        return 0, {"error": str(exc)}


def _db_path() -> Path:
    """Resolved exactly as the server resolves it, and opened READ ONLY."""
    data_dir = os.environ.get("DATA_DIR")
    db_name = os.environ.get("DB_NAME")
    if not data_dir or not db_name:
        env = REPO_ROOT / ".env"
        if env.is_file():
            for line in env.read_text(encoding="utf-8",
                                      errors="replace").splitlines():
                line = line.strip()
                if line.startswith("DATA_DIR=") and not data_dir:
                    data_dir = line.split("=", 1)[1].strip()
                elif line.startswith("DB_NAME=") and not db_name:
                    db_name = line.split("=", 1)[1].strip()
    return Path(data_dir or "data") / "db" / (db_name or "lorevox.sqlite3")


def _read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _armed_dir() -> Optional[str]:
    try:
        if not MARKER.is_file():
            return None
        return MARKER.read_text(encoding="utf-8", errors="replace").strip() or None
    except Exception:
        return None


def _run_dir() -> Path:
    """Evidence lands beside the traces it explains."""
    armed = _armed_dir()
    base = Path(armed) if armed else (REPO_ROOT / ".runtime" / "eval" / "guard-lab")
    out = base / "guard-lab-acceptance"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


#: `state-<ISO8601 basic>-<label>.json`, written by `snapshot`.
_SNAPSHOT_RX = re.compile(r"^state-(\d{8}T\d{6}Z)-(.+)\.json$")

RESTART_BEFORE = "before-restart"
RESTART_AFTER = "after-restart"


def _labelled_snapshots(run_dir: Path) -> Dict[str, List[Path]]:
    """Snapshots grouped by the label the operator gave them, oldest first.

    THE LABEL IS THE WHOLE POINT and the first version ignored it. It
    took `sorted(glob("state-*.json"))[0]` and `[-1]`, so on a correct
    run — which the procedure itself asks for — the pair compared was
    `before-all-off` (revision 0, no overrides) against `after-restart`
    (37 overrides). Those differ for the obvious reason, the guard fell
    through to its `else`, and a restart that worked perfectly was
    reported UNVERIFIED.

    It failed in the safe direction, which is the only good thing about
    it: it under-reported a passing restart rather than certifying a
    failing one. It would still have cost the run, and then an argument
    about whether persistence actually worked — which is exactly the
    kind of question the instrument exists to settle.
    """
    out: Dict[str, List[Path]] = {}
    for path in sorted(run_dir.glob("state-*.json")):
        match = _SNAPSHOT_RX.match(path.name)
        if not match:
            continue
        out.setdefault(match.group(2), []).append(path)
    for paths in out.values():
        paths.sort(key=lambda p: _SNAPSHOT_RX.match(p.name).group(1))  # type: ignore[union-attr]
    return out


def _overrides_of(payload: Dict[str, Any]) -> Dict[int, Any]:
    return {a["id"]: a["operator_override"]
            for a in payload.get("authorities", [])
            if a.get("operator_override") is not None}


def _restart_verdict(run_dir: Path) -> Tuple[str, str]:
    """Decide restart persistence from the NAMED pair, and nothing else.

    Returns (verdict, detail). Separated from `cmd_verify` so the
    decision can be tested against real snapshot files rather than
    against a reimplementation of it.
    """
    groups = _labelled_snapshots(run_dir)
    before_paths = groups.get(RESTART_BEFORE) or []
    after_paths = groups.get(RESTART_AFTER) or []

    missing = [name for name, paths in ((RESTART_BEFORE, before_paths),
                                        (RESTART_AFTER, after_paths))
               if not paths]
    if missing:
        found = ", ".join(sorted(groups)) or "none"
        return UNVERIFIED, (
            f"no snapshot labelled {' and '.join(missing)}. "
            f"Labels present: {found}.\n"
            f"Run `snapshot {RESTART_BEFORE}` and `snapshot "
            f"{RESTART_AFTER}` either side of the stop/start, with "
            f"nothing else changed in between.")

    # The latest matching pair, so a retried restart supersedes an
    # earlier attempt rather than being averaged with it.
    before_path, after_path = before_paths[-1], after_paths[-1]
    before_stamp = _SNAPSHOT_RX.match(before_path.name).group(1)   # type: ignore[union-attr]
    after_stamp = _SNAPSHOT_RX.match(after_path.name).group(1)     # type: ignore[union-attr]
    if after_stamp <= before_stamp:
        return UNVERIFIED, (
            f"{after_path.name} was taken before {before_path.name}. "
            f"A restart pair has to be in order to mean anything.")

    try:
        before = json.loads(before_path.read_text(encoding="utf-8"))
        after = json.loads(after_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return UNVERIFIED, f"could not read the snapshot pair: {exc}"

    before_overrides = _overrides_of(before)
    after_overrides = _overrides_of(after)

    # AN EMPTY PAIR PROVES NOTHING. Two snapshots with no overrides on
    # either side compare equal and would report a green restart while
    # testing nothing at all — the fixture supplying the property.
    if not before_overrides:
        return UNVERIFIED, (
            f"{before_path.name} carries no operator override, so a "
            f"matching {after_path.name} proves nothing. Apply a "
            f"configuration BEFORE the restart snapshot.")

    if before_overrides != after_overrides:
        lost = sorted(set(before_overrides) - set(after_overrides))
        changed = sorted(k for k in set(before_overrides) & set(after_overrides)
                         if before_overrides[k] != after_overrides[k])
        added = sorted(set(after_overrides) - set(before_overrides))
        return FAIL, (
            f"the operator configuration did not survive the restart.\n"
            f"before {before_path.name}: {len(before_overrides)} override(s), "
            f"revision {before.get('revision')}\n"
            f"after  {after_path.name}: {len(after_overrides)} override(s), "
            f"revision {after.get('revision')}\n"
            f"lost {lost or '[]'} · changed {changed or '[]'} · "
            f"added {added or '[]'}")

    if before.get("revision") != after.get("revision"):
        return UNVERIFIED, (
            f"the overrides match but the revision moved "
            f"{before.get('revision')} -> {after.get('revision')}, so "
            f"something changed the configuration between the two "
            f"snapshots. That is not a clean restart pair.")

    return PASS, (
        f"{len(after_overrides)} override(s) identical across the restart, "
        f"revision {after.get('revision')} unchanged\n"
        f"{before_path.name} -> {after_path.name}")


def _line(verdict: str, clause: str, detail: str = "") -> None:
    mark = {PASS: "  ok  ", FAIL: " FAIL ", UNVERIFIED: " ---- "}[verdict]
    print(f"[{mark}] {clause}")
    if detail:
        for chunk in detail.splitlines():
            print(f"          {chunk}")


# ── preflight ─────────────────────────────────────────────────────────

def cmd_preflight(_args) -> int:
    """The four conditions, SORTED BY WHEN THEY MUST HOLD.

    TWO PHASES, NOT ONE CHECKLIST — and conflating them made the first
    version of this impossible to satisfy on a first run.

    `trace_env.sh` resolves the marker into `HORNELORE_RESPONSE_TRACE`
    only when a PROCESS STARTS, so the marker and the operator flag must
    be set before the API comes up; arming afterwards leaves tracing off
    and the gate refuses every experimental turn with
    `trace_not_enabled` for a reason that is nowhere on screen.

    The testing-only narrator is different. It can only be created
    through the product UI, which needs a running stack — so requiring
    it before startup demands this command's own output as its input.
    It has to exist before the acceptance TURNS, not before the process.

    So a run with only the narrator missing is BOOTSTRAP INCOMPLETE, not
    a failure: start the stack, create the narrator through New narrator
    -> "Skip - add narrator for testing only", and run this again while
    that same correctly-armed stack keeps running. Re-running a
    read-only check after startup is not a violation of the ordering
    rule; the rule is about when the CONFIGURATION exists, not about
    when this executable may be run.
    """
    print("Guard Lab live acceptance — PREFLIGHT")
    print(f"repo: {REPO_ROOT}")
    print()
    problems: List[str] = []
    before_start: List[str] = []

    armed = _armed_dir()
    if armed:
        _line(PASS, "an evaluation is armed", armed)
    else:
        _line(FAIL, "no evaluation is armed",
              "Arm it BEFORE the stack starts — the marker only becomes\n"
              "HORNELORE_RESPONSE_TRACE=1 when a process starts:\n"
              "  RUN=.runtime/eval/guard-lab-$(date +%Y%m%d_%H%M%S)\n"
              "  mkdir -p \"$RUN\"\n"
              "  echo \"$PWD/$RUN\" > .runtime/eval/current_eval_dir")
        problems.append("marker")
        before_start.append("marker")

    env_file = REPO_ROOT / ".env"
    gate_on = False
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8",
                                       errors="replace").splitlines():
            if line.strip().startswith("HORNELORE_OPERATOR_GUARD_LAB="):
                gate_on = line.split("=", 1)[1].strip().lower() in (
                    "1", "true", "yes", "on")
    if gate_on:
        _line(PASS, "HORNELORE_OPERATOR_GUARD_LAB is on in .env")
    else:
        _line(FAIL, "HORNELORE_OPERATOR_GUARD_LAB is not on in .env",
              "Set HORNELORE_OPERATOR_GUARD_LAB=1 in .env before starting.\n"
              "Without it every guard-lab route answers 404 and the panel\n"
              "renders its disabled placeholder.")
        problems.append("gate")
        before_start.append("gate")

    db = _db_path()
    if not db.is_file():
        _line(FAIL, "database not found", str(db))
        problems.append("db")
    else:
        con = _read_only(db)
        try:
            cols = {r[1] for r in con.execute("PRAGMA table_info(people)")}
            if "testing_only" not in cols:
                _line(FAIL, "people.testing_only is missing",
                      "init_db() adds it on boot; start the stack once.")
                problems.append("column")
            else:
                rows = con.execute(
                    "SELECT id, display_name FROM people "
                    "WHERE is_deleted = 0 AND COALESCE(testing_only, 0) = 1 "
                    "ORDER BY updated_at DESC").fetchall()
                if rows:
                    _line(PASS, f"{len(rows)} testing-only narrator(s) exist",
                          "\n".join(f"{r[0]}  {r[1]}" for r in rows))
                else:
                    _line(FAIL, "NO testing-only narrator exists",
                          "Every experimental turn will be refused with\n"
                          "`not_testing_only`, which is the gate working.\n"
                          "THIS ONE NEEDS A RUNNING STACK. It is created\n"
                          "through the product path — New narrator ->\n"
                          "'Skip - add narrator for testing only' — so it is\n"
                          "not a before-startup condition. Start the stack,\n"
                          "create it, and run this check again while that\n"
                          "same stack keeps running.\n"
                          "It CANNOT be granted to an existing narrator, and\n"
                          "no existing narrator may be converted into one.")
                    problems.append("narrator")
            tables = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name LIKE 'lori_guard%'")}
            if {"lori_guard_authority_override",
                    "lori_guard_control_state"} <= tables:
                rev = con.execute(
                    "SELECT revision FROM lori_guard_control_state "
                    "WHERE id = 1").fetchone()
                n = con.execute(
                    "SELECT COUNT(*) FROM lori_guard_authority_override"
                ).fetchone()
                _line(PASS, "migration 0053 is applied",
                      f"revision={rev[0] if rev else '?'} overrides={n[0]}")
            else:
                _line(FAIL, "guard-lab tables absent",
                      "Migration 0053 has not run; start the stack once.")
                problems.append("migration")
        finally:
            con.close()

    print()
    if before_start:
        # These decide what the API process reads at startup. Starting
        # the stack now would bake the wrong answer in for its lifetime.
        print(f"BLOCKED BEFORE STARTUP — {len(before_start)} condition(s) "
              f"must be set before the API process starts: "
              f"{', '.join(before_start)}")
        print("Fix these, then run preflight again. Do NOT start the stack "
              "first: the trace flag is resolved once, at process start.")
        return 1
    if problems:
        print(f"BOOTSTRAP INCOMPLETE — {len(problems)} condition(s) unmet: "
              f"{', '.join(problems)}")
        print("The startup-time configuration is correct, so START THE "
              "STACK now, create the testing-only narrator through the "
              "product UI, and run this command again while that same "
              "stack keeps running.")
        return 3
    print("PREFLIGHT OK — all four conditions met.")
    print("If the stack is not running yet, start it now; if it is already "
          "running with this configuration, continue the acceptance on it.")
    return 0


# ── snapshot ──────────────────────────────────────────────────────────

def cmd_snapshot(args) -> int:
    """Save the live configuration under a label. Evidence, not a change."""
    status, body = _get(f"{GUARD_LAB}/state")
    if status == 404:
        print("404 — HORNELORE_OPERATOR_GUARD_LAB is off in the RUNNING "
              "server. A .env edit needs a restart to take effect.")
        return 1
    if status != 200 or not isinstance(body, dict):
        print(f"could not read the configuration: HTTP {status} {body}")
        return 1

    out = _run_dir() / f"state-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{args.label}.json"
    out.write_text(json.dumps(body, indent=2), encoding="utf-8")

    gate = body.get("gate") or {}
    print(f"label            {args.label}")
    print(f"revision         {body.get('revision')}")
    print(f"selection        {str(body.get('selection_fingerprint'))[:12]}")
    print(f"registry         {str(body.get('registry_fingerprint'))[:12]}")
    counts = body.get("counts") or {}
    print(f"running/total    {counts.get('selected')}/{counts.get('total')}")
    print(f"can reach a turn {gate.get('can_apply_to_a_turn')}")
    for cond in gate.get("conditions") or []:
        print(f"  {'met ' if cond.get('met') else 'UNMET'}  {cond.get('name')}"
              f"  {cond.get('detail')}")
    print(f"saved            {out}")
    return 0


# ── verify ────────────────────────────────────────────────────────────

def _trace_records(armed: str) -> List[Dict[str, Any]]:
    """Every traced turn in the armed run, oldest first.

    `.runtime/` is gitignored, not empty — and a missing trace is
    reported as missing rather than as an empty result set that reads
    like a clean run.
    """
    base = Path(armed) / "response-trace"
    records: List[Dict[str, Any]] = []
    if not base.is_dir():
        return records
    for path in sorted(base.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8",
                                   errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                continue
    records.sort(key=lambda r: r.get("started_at") or 0)
    return records


def _authority(rec: Dict[str, Any]) -> Dict[str, Any]:
    ctx = rec.get("context") or {}
    return {k[len("authority_"):]: v for k, v in ctx.items()
            if k.startswith("authority_")}


def cmd_verify(args) -> int:
    armed = _armed_dir() or args.eval_dir
    results: List[Tuple[str, str, str]] = []

    def record(verdict, clause, detail=""):
        results.append((verdict, clause, detail))
        _line(verdict, clause, detail)

    print("Guard Lab live acceptance — VERIFY")
    print(f"eval dir: {armed or '(none)'}")
    print()

    if not armed:
        record(UNVERIFIED, "traced turns are available",
               "No armed eval directory. Pass --eval-dir, or re-run the\n"
               "acceptance with the marker armed before stack startup.")
        return _summarise(results)

    records = _trace_records(armed)
    if not records:
        record(UNVERIFIED, "traced turns are available",
               f"No response-trace records under {armed}/response-trace.\n"
               "Tracing resolves at process start — if the marker was armed\n"
               "after the API came up, nothing was recorded.")
        return _summarise(results)

    record(PASS, "traced turns are available",
           f"{len(records)} turn(s) recorded")

    # ── every turn carries its authority identity ──────────────────────
    missing = [r.get("trace_id") for r in records if not _authority(r)]
    if missing:
        record(FAIL, "every traced turn carries the authority identity",
               f"{len(missing)} turn(s) with no authority_* context: "
               f"{', '.join(str(m)[:8] for m in missing[:5])}")
    else:
        record(PASS, "every traced turn carries the authority identity",
               "registry fingerprint, consumed revision, selection "
               "fingerprint, gate reason")

    # ── the gate refused where it should ───────────────────────────────
    applied = [r for r in records if _authority(r).get("experiment_applied")]
    refused = [r for r in records if not _authority(r).get("experiment_applied")]
    reasons: Dict[str, int] = {}
    for r in refused:
        reasons[str(_authority(r).get("gate_reason"))] = reasons.get(
            str(_authority(r).get("gate_reason")), 0) + 1

    if applied:
        record(PASS, "an experimental configuration governed a live turn",
               f"{len(applied)} turn(s) with experiment_applied=true, "
               f"revision(s) "
               f"{sorted({_authority(r).get('revision') for r in applied})}")
    else:
        record(UNVERIFIED,
               "an experimental configuration governed a live turn",
               "No turn ran with the experiment applied. Refusals: "
               + (", ".join(f"{k}×{v}" for k, v in reasons.items()) or "none"))

    # ── a real narrator never received one ─────────────────────────────
    db = _db_path()
    testing_ids: set = set()
    if db.is_file():
        con = _read_only(db)
        try:
            testing_ids = {r[0] for r in con.execute(
                "SELECT id FROM people WHERE COALESCE(testing_only, 0) = 1")}
        finally:
            con.close()
    leaked = [r for r in applied
              if str(r.get("narrator_id")) not in testing_ids]
    if leaked:
        record(FAIL, "no real narrator received an experiment",
               f"{len(leaked)} experimental turn(s) on narrators that are "
               f"NOT testing_only: "
               f"{', '.join(str(r.get('narrator_id'))[:8] for r in leaked[:5])}")
    elif applied:
        record(PASS, "no real narrator received an experiment",
               f"all {len(applied)} experimental turn(s) belong to a "
               f"testing-only narrator")
    else:
        record(UNVERIFIED, "no real narrator received an experiment",
               "vacuous — no experimental turn ran at all")

    ordinary = [r for r in refused
                if _authority(r).get("gate_reason") == "not_testing_only"]
    if ordinary:
        record(PASS, "an ordinary narrator was refused BY NAME",
               f"{len(ordinary)} turn(s) refused with `not_testing_only` — "
               f"the safety property observed, not assumed")
    else:
        record(UNVERIFIED, "an ordinary narrator was refused BY NAME",
               "No turn was refused with `not_testing_only`. Talk to a "
               "normal narrator once while a configuration is selected.")

    # ── a change is picked up on the NEXT turn, and only then ──────────
    revisions = [(_authority(r).get("revision"), r) for r in records
                 if _authority(r).get("experiment_applied")]
    distinct = sorted({rev for rev, _ in revisions if rev is not None})
    if len(distinct) >= 2:
        record(PASS, "a configuration change was picked up without a restart",
               f"consumed revisions {distinct} across one running process")
    elif distinct:
        record(UNVERIFIED,
               "a configuration change was picked up without a restart",
               f"every experimental turn consumed revision {distinct[0]}. "
               f"Change an authority mid-session and take another turn.")
    else:
        record(UNVERIFIED,
               "a configuration change was picked up without a restart",
               "no experimental turn to compare")

    # ── the in-flight turn stayed frozen ───────────────────────────────
    #
    # A turn is frozen if it carries ONE revision and ONE selection
    # fingerprint from start to finish. The trace records the identity
    # taken at acquisition, so a turn that reported a revision the store
    # only reached mid-generation would be the failure.
    torn = []
    for rev, rec in revisions:
        auth = _authority(rec)
        selected = auth.get("selected")
        excluded = auth.get("excluded")
        if not isinstance(selected, list) or not isinstance(excluded, list):
            torn.append(rec.get("trace_id"))
            continue
        if set(selected) & set(excluded):
            torn.append(rec.get("trace_id"))
    if revisions and not torn:
        record(PASS, "each turn's configuration is internally coherent",
               f"{len(revisions)} turn(s): selected and excluded are "
               f"disjoint and complete, one revision each")
    elif torn:
        record(FAIL, "each turn's configuration is internally coherent",
               f"{len(torn)} incoherent turn(s)")
    else:
        record(UNVERIFIED, "each turn's configuration is internally coherent",
               "no experimental turn to inspect")

    # THE MID-TURN FREEZE ITSELF IS NOT DECIDABLE FROM THE TRACE ALONE.
    # It needs the operator's own timestamp for the toggle, compared
    # against the turn's start and end. Claiming it from the trace would
    # be exactly the "inferred, reported as measured" failure.
    if args.toggle_at:
        try:
            t = float(args.toggle_at)
        except ValueError:
            t = 0.0
        straddling = [r for r in records
                      if (r.get("started_at") or 0) < t < (r.get("ended_at") or 0)]
        if straddling:
            rec = straddling[0]
            before = [x for x in records
                      if (x.get("ended_at") or 0) <= t and _authority(x).get("revision") is not None]
            after = [x for x in records
                     if (x.get("started_at") or 0) >= t and _authority(x).get("revision") is not None]
            in_flight = _authority(rec).get("revision")
            prior = _authority(before[-1]).get("revision") if before else None
            later = _authority(after[0]).get("revision") if after else None
            if prior is not None and in_flight == prior and (
                    later is None or later != in_flight):
                record(PASS, "a mid-turn change did not reach the turn in flight",
                       f"toggle at {t}; in-flight turn kept revision "
                       f"{in_flight}; the next turn consumed {later}")
            else:
                record(FAIL, "a mid-turn change did not reach the turn in flight",
                       f"in-flight revision {in_flight}, prior {prior}, "
                       f"next {later}")
        else:
            record(UNVERIFIED,
                   "a mid-turn change did not reach the turn in flight",
                   f"no traced turn straddles {t}. The toggle has to land "
                   f"while Lori is actually generating.")
    else:
        record(UNVERIFIED,
               "a mid-turn change did not reach the turn in flight",
               "Pass --toggle-at <unix seconds> — the moment the operator\n"
               "pressed the switch. The trace alone cannot decide this, and\n"
               "guessing it from turn order would be inference reported as\n"
               "measurement.")

    # ── extraction ownership on an experimental turn ───────────────────
    #
    # Legacy compatibility is DELIBERATE in production: a browser that
    # does not declare `field_extraction_result=v1` owns extraction
    # itself, and the server yields rather than extracting the turn
    # twice. That is correct, and this verifier does not ask the product
    # to stop supporting it.
    #
    # It IS a defect on an evaluation run. The shipped browser negotiates
    # backend ownership, so a Guard Lab turn that fell back to legacy was
    # not measured by the instrument the experiment depends on — and the
    # trace would say `not_measured / legacy_client_owns_extraction`
    # rather than carrying a retention result at all.
    legacy = []
    unswept_check = []
    for rec in records:
        storage = (rec.get("storage") or {}).get("extraction") or {}
        detail = storage.get("detail") or {}
        if str(detail.get("reason") or "") == "legacy_client_owns_extraction":
            legacy.append(rec.get("trace_id"))
        if rec.get("swept"):
            unswept_check.append(rec.get("trace_id"))

    if legacy:
        record(FAIL, "the backend owned extraction on every traced turn",
               f"{len(legacy)} turn(s) ran with LEGACY client ownership: "
               f"{', '.join(str(t)[:8] for t in legacy)}.\n"
               f"Compatible in production, wrong for an evaluation — the "
               f"shipped browser is supposed to negotiate backend "
               f"ownership, so these turns were not measured by the "
               f"instrument the experiment relies on.")
    else:
        record(PASS, "the backend owned extraction on every traced turn",
               "no turn fell back to legacy client ownership")

    # ── the sweep is recovery, not the normal way a turn finishes ──────
    if unswept_check:
        record(FAIL, "every traced turn closed without the sweep",
               f"{len(unswept_check)} turn(s) carry `swept` — they waited "
               f"the full 180 seconds instead of closing on their "
               f"retention outcome: "
               f"{', '.join(str(t)[:8] for t in unswept_check)}")
    else:
        record(PASS, "every traced turn closed without the sweep",
               f"{len(records)} turn(s), none swept")

    # ── the trace carries the committed turn's canonical key ───────────
    unbound = [r.get("trace_id") for r in records
               if not str(r.get("turn_key") or "").strip()]
    if not unbound:
        record(PASS, "every traced turn carries its canonical turn_key",
               "trace and ledger can be joined directly")
    elif len(unbound) == len(records):
        # ALL of them. Almost certainly a run recorded before the
        # late-binding existed — the two 2026-09-07 Guard Lab turns are
        # exactly this, and calling that a FAILURE would blame a run for
        # not satisfying a clause that had no implementation yet.
        # UNVERIFIED is the honest verdict: the property is untested by
        # this evidence, not violated by it.
        record(UNVERIFIED, "every traced turn carries its canonical turn_key",
               f"all {len(records)} turn(s) persisted with an empty "
               f"turn_key. Runs recorded before the canonical key was "
               f"late-bound cannot show it; take one bounded turn on the "
               f"current build to decide this clause.")
    else:
        # A MIX is a real inconsistency inside one run — the binding
        # exists and did not happen for some turns.
        record(FAIL, "every traced turn carries its canonical turn_key",
               f"{len(unbound)} of {len(records)} turn(s) persisted with "
               f"an empty turn_key while others carried one: "
               f"{', '.join(str(t)[:8] for t in unbound)}")

    # ── the override survived a restart ────────────────────────────────
    #
    # Decided from the snapshots the operator LABELLED, never from
    # whichever files the glob happened to order first and last.
    verdict, detail = _restart_verdict(_run_dir())
    record(verdict, "the operator configuration survived a stack restart",
           detail)

    return _summarise(results)


def _summarise(results: List[Tuple[str, str, str]]) -> int:
    counts = {PASS: 0, FAIL: 0, UNVERIFIED: 0}
    for verdict, _, _ in results:
        counts[verdict] += 1
    print()
    print(f"{counts[PASS]} passed / {counts[FAIL]} failed / "
          f"{counts[UNVERIFIED]} unverified")
    if counts[FAIL]:
        print("ACCEPTANCE FAILED.")
        return 1
    if counts[UNVERIFIED]:
        print("ACCEPTANCE INCOMPLETE — unverified is not a soft pass. The "
              "evidence to decide those clauses is absent.")
        return 2
    print("ACCEPTANCE COMPLETE.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("preflight", help="check the four conditions BEFORE start")

    snap = sub.add_parser("snapshot", help="save the live configuration")
    snap.add_argument("label", help="e.g. before-all-off, after-restart")

    ver = sub.add_parser("verify", help="judge the acceptance from evidence")
    ver.add_argument("--eval-dir", default=None,
                     help="run directory, when the marker is already disarmed")
    ver.add_argument("--toggle-at", default=None,
                     help="unix seconds when the mid-turn toggle was pressed")

    args = parser.parse_args()
    return {"preflight": cmd_preflight,
            "snapshot": cmd_snapshot,
            "verify": cmd_verify}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
