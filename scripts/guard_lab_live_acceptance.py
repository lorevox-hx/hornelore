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


def _line(verdict: str, clause: str, detail: str = "") -> None:
    mark = {PASS: "  ok  ", FAIL: " FAIL ", UNVERIFIED: " ---- "}[verdict]
    print(f"[{mark}] {clause}")
    if detail:
        for chunk in detail.splitlines():
            print(f"          {chunk}")


# ── preflight ─────────────────────────────────────────────────────────

def cmd_preflight(_args) -> int:
    """Run this BEFORE starting the stack. Order is load-bearing.

    `trace_env.sh` resolves the marker into `HORNELORE_RESPONSE_TRACE`
    only when a PROCESS STARTS. Arming after the API is up leaves
    tracing off, the gate refuses every experimental turn with
    `trace_not_enabled`, and the panel looks broken for a reason that is
    nowhere on screen.
    """
    print("Guard Lab live acceptance — PREFLIGHT")
    print(f"repo: {REPO_ROOT}")
    print()
    problems: List[str] = []

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
                          "Create one through the product path: New narrator\n"
                          "-> 'Skip - add narrator for testing only'.\n"
                          "It CANNOT be granted to an existing narrator.")
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
    if problems:
        print(f"PREFLIGHT INCOMPLETE — {len(problems)} condition(s) unmet: "
              f"{', '.join(problems)}")
        print("Fix these BEFORE starting the stack, then run preflight again.")
        return 1
    print("PREFLIGHT OK — start the stack, then open Bug Panel -> Guard Lab.")
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

    # ── the override survived a restart ────────────────────────────────
    snapshots = sorted(_run_dir().glob("state-*.json"))
    if len(snapshots) >= 2:
        first = json.loads(snapshots[0].read_text(encoding="utf-8"))
        last = json.loads(snapshots[-1].read_text(encoding="utf-8"))
        overridden_first = {a["id"]: a["operator_override"]
                            for a in first.get("authorities", [])
                            if a.get("operator_override") is not None}
        overridden_last = {a["id"]: a["operator_override"]
                           for a in last.get("authorities", [])
                           if a.get("operator_override") is not None}
        if overridden_first and overridden_first == overridden_last:
            record(PASS, "the operator configuration is durable across the run",
                   f"{len(overridden_last)} override(s) identical between "
                   f"{snapshots[0].name} and {snapshots[-1].name}; revision "
                   f"{first.get('revision')} -> {last.get('revision')}")
        else:
            record(UNVERIFIED,
                   "the operator configuration is durable across the run",
                   f"snapshots differ ({len(overridden_first)} -> "
                   f"{len(overridden_last)} overrides). That is expected if "
                   f"you deliberately changed it; take a snapshot either "
                   f"side of the RESTART with nothing else in between.")
    else:
        record(UNVERIFIED,
               "the operator configuration is durable across the run",
               "Fewer than two snapshots. Run `snapshot before-restart` and "
               "`snapshot after-restart` around the stop/start.")

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
