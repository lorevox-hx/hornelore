#!/usr/bin/env python3
"""WO-TRUTH-PIPELINE-01 Phase 2 (Gate 7) — the live acceptance driver.

WHY THIS SCRIPT EXISTS. Phase 2 connected the completed chat_ws
interview turn to field extraction through one shared, idempotent,
observable, failure-isolated service. The automated suite proves the
wiring in isolation. The work order requires more than that:

    "This must work in the running application, not only in unit
    tests. Do not declare completion until this is run against the
    actual local stack."

So this script drives the real stack over HTTP, reads the real database
and the real archive files, and writes a machine-readable evidence
record. It is the instrument the completion report quotes from.

═══════════════════════════════════════════════════════════════════════
  USAGE — three phases, because the environment must differ
═══════════════════════════════════════════════════════════════════════

The five required live tests cannot share one server process. Test A
needs the operator harness ENABLED; Test C needs a forced extraction
failure, which has to come from the server's own environment; Test E
needs the harness GONE. And the harness runs each turn over an internal
WebSocket to /api/chat/ws, so the turn body executes in a different
asyncio context from the HTTP handler — a per-request toggle set in the
handler could never reach it. Hence three runs, each after a restart:

  PHASE 1 — harness on, observability on, no forced failure.
            Runs Test A (normal turn), Test B (idempotent replay),
            Test D (correction control).

      export HORNELORE_OPERATOR_HARNESS=1
      export HORNELORE_TRUTH_PIPELINE_LOG=1
      unset  HORNELORE_EXTRACTION_FORCE_FAILURE
      # restart the stack, then:
      python scripts/gate7_phase2_acceptance.py --phase 1

  PHASE 2 — same, plus the failure seam. Runs Test C.

      export HORNELORE_EXTRACTION_FORCE_FAILURE=raise
      # restart the stack, then:
      python scripts/gate7_phase2_acceptance.py --phase 2

  PHASE 3 — every temporary flag unset. Runs Test E and the cleanup.

      unset HORNELORE_OPERATOR_HARNESS
      unset HORNELORE_TRUTH_PIPELINE_LOG
      unset HORNELORE_EXTRACTION_FORCE_FAILURE
      # restart the stack, then:
      python scripts/gate7_phase2_acceptance.py --phase 3

Phase 1 writes the disposable narrator id to a state file; phases 2 and
3 read it, so the same narrator carries the whole run and phase 3 can
clean exactly what phases 1 and 2 created.

═══════════════════════════════════════════════════════════════════════
  WHAT IT REFUSES TO DO
═══════════════════════════════════════════════════════════════════════

  * It never edits configuration. The work order is explicit: "Do not
    corrupt production configuration to create this failure." The Test C
    seam is a purpose-built environment variable read at extraction
    time, default off, and the script only OBSERVES whether it is on.
  * It never touches a narrator whose id does not start with
    "harness-test-". Cleanup is delegated to the archived isolation
    probe's cleanup_synthetic(), which enforces that prefix itself.
  * It never deletes Kent's control turn. Kent's narrator id does not
    carry the synthetic prefix, so the guard above already excludes it,
    and nothing here names him.
  * It logs no narrative text beyond the short fixed prompts it sends
    itself, and never the narrator's projection values.

═══════════════════════════════════════════════════════════════════════
  WHY IT READS THE DATABASE DIRECTLY
═══════════════════════════════════════════════════════════════════════

The harness response reports the probe's own tally. That is the
instrument under test, so trusting it alone would be circular. Every
required number is therefore taken twice: once from the probe stage
counts, and once from an independent read of the sqlite rows, the
extraction ledger, and the append-only transcript.jsonl on disk.

Note that `archive_event_created` is a FILE write, not a table. The
archived probe listed a table named `archive_events` for years; it has
never existed. The archive lives at
DATA_DIR/memory/archive/people/<person_id>/sessions/<session_id>/transcript.jsonl
and the independent check counts lines there.

DB PATH RESOLUTION. api/db.py resolves DATA_DIR and DB_NAME from the
process environment with no dotenv load of its own, so a script that
does not inherit the server's shell can silently open a DIFFERENT,
freshly-created database and report a confident set of zeroes. This
script therefore reads DATA_DIR and DB_NAME out of .env when they are
absent from the environment, and records the resolved absolute path and
byte size in the evidence so a wrong-database run is visible on its
face rather than mistaken for a clean pass.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parent.parent


# ── Environment resolution — must happen BEFORE api.* is imported ─────────

_ENV_KEYS_READ = ("DATA_DIR", "DB_NAME")


def load_env_defaults() -> Dict[str, str]:
    """Fill DATA_DIR / DB_NAME from .env when the shell did not set them.

    Only those two keys are read. .env carries roughly a hundred and
    forty others, several of them credentials, and none of them are this
    script's business.
    """
    resolved: Dict[str, str] = {}
    env_path = _REPO_ROOT / ".env"
    from_file: Dict[str, str] = {}
    if env_path.exists():
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            if k in _ENV_KEYS_READ:
                from_file[k] = v.strip().strip('"').strip("'")
    for key in _ENV_KEYS_READ:
        if os.environ.get(key):
            resolved[key] = f"{os.environ[key]} (from shell)"
        elif key in from_file:
            os.environ[key] = from_file[key]
            resolved[key] = f"{from_file[key]} (from .env)"
        else:
            resolved[key] = "(unset — api/db.py default applies)"
    return resolved


_ENV_PROVENANCE = load_env_defaults()

_DATA_DIR = Path(os.environ.get("DATA_DIR", "data")).expanduser()
_DB_NAME = (os.environ.get("DB_NAME") or "lorevox.sqlite3").strip()
_DB_PATH = _DATA_DIR / "db" / _DB_NAME
_XFER_DIR = _DATA_DIR / "_xfer"
_STATE_PATH = _XFER_DIR / "gate7_phase2_state.json"

_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

try:
    import requests  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    print("FATAL: the `requests` package is required. "
          "Run this inside the server virtualenv.", file=sys.stderr)
    raise


# ── Small helpers ─────────────────────────────────────────────────────────

def _api_base() -> str:
    return (os.environ.get("HORNELORE_API_URL")
            or "http://localhost:8000").rstrip("/")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), timeout=15.0)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _count(conn: sqlite3.Connection, sql: str, args: Tuple) -> Optional[int]:
    """Scalar count, or None when the table is absent.

    None and 0 are kept distinct on purpose. The archived probe collapsed
    them, a missing table diffed as "unchanged", and "unchanged" read as
    "isolation held" — seven guaranteed passes measuring nothing. A None
    in this evidence means THE MEASUREMENT FAILED, never "no writes".
    """
    try:
        cur = conn.execute(sql, args)
        row = cur.fetchone()
        return int(row[0]) if row is not None else None
    except sqlite3.Error:
        return None


def snapshot(narrator_id: str) -> Dict[str, Any]:
    """Every row count that could change for this narrator, plus the
    projection's version stamp so a rewrite with the same row count is
    still visible."""
    if not narrator_id:
        return {"error": "empty narrator_id"}
    out: Dict[str, Any] = {}
    conn = _connect()
    try:
        by_narrator = ("story_candidates", "photos", "turn_extraction_ledger")
        by_person = ("media_archive_items", "profiles", "interview_projections",
                     "family_truth_rows", "family_truth_notes")
        for t in by_narrator:
            out[t] = (_count(conn, f"SELECT COUNT(*) FROM {t} WHERE narrator_id = ?",
                             (narrator_id,)) if _table_exists(conn, t) else None)
        for t in by_person:
            out[t] = (_count(conn, f"SELECT COUNT(*) FROM {t} WHERE person_id = ?",
                             (narrator_id,)) if _table_exists(conn, t) else None)
        out["turns"] = (_count(
            conn, "SELECT COUNT(*) FROM turns WHERE conv_id LIKE ?",
            (f"%{narrator_id}%",)) if _table_exists(conn, "turns") else None)
        # ADDED 2026-07-30. The disposable narrator now gets a real `people`
        # row (see ensure_disposable_person below), so Test E's
        # "no rows left for the disposable narrator" has to count it or the
        # cleanup check would pass while leaving the row behind.
        out["people"] = (_count(
            conn, "SELECT COUNT(*) FROM people WHERE id = ?",
            (narrator_id,)) if _table_exists(conn, "people") else None)
        # Projection version — a correction can overwrite fields in place.
        out["projection_version"] = None
        out["projection_updated_at"] = ""
        if _table_exists(conn, "interview_projections"):
            row = conn.execute(
                "SELECT version, updated_at FROM interview_projections "
                "WHERE person_id = ?", (narrator_id,),
            ).fetchone()
            if row is not None:
                out["projection_version"] = row["version"]
                out["projection_updated_at"] = row["updated_at"] or ""
    finally:
        conn.close()
    return out


def ensure_disposable_person(narrator_id: str) -> Dict[str, Any]:
    """Give the disposable narrator a real `people` row before any turn.

    ADDED 2026-07-30, by the first live acceptance run. Test D failed there
    with `projection_update_path_reachable: probe projection_updated=0`, and
    api.log carried the actual cause:

        [projection-writer] upsert_projection failed
        person=harness-test-gate7p2-03d26274-...: FOREIGN KEY constraint failed

    `interview_projections` declares
    FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE, and the
    harness narrator existed only as a string in conv ids. The correction path
    was reached and the parse was correct; the write could not land because
    the narrator was not a person. That is a FIXTURE defect in this script,
    not a defect in the correction path, and the fix belongs here.

    Written with sqlite directly rather than through POST /api/people because
    PersonCreate mints its own id --- the API cannot be asked to create a row
    at a chosen id, and the id is the whole point.

    Refuses any id outside the harness prefix, mirroring the same guard in
    cleanup_synthetic. narrator_type is 'live': a 'reference' narrator is
    protected by _block_if_reference and would measure a different path.
    """
    if not narrator_id.startswith("harness-test-"):
        return {"ok": False, "error": "refusing to create a non-synthetic person"}
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        existing = conn.execute(
            "SELECT id FROM people WHERE id = ?", (narrator_id,)).fetchone()
        if existing is not None:
            return {"ok": True, "created": False, "id": narrator_id}
        conn.execute(
            "INSERT INTO people (id, display_name, role, created_at, "
            "updated_at, narrator_type) VALUES (?, ?, ?, ?, ?, ?)",
            (narrator_id, "Gate 7 disposable harness narrator",
             "narrator", now, now, "live"),
        )
        conn.commit()
        return {"ok": True, "created": True, "id": narrator_id}
    except sqlite3.Error as exc:
        return {"ok": False, "error": f"{exc.__class__.__name__}: {exc}"}
    finally:
        conn.close()


_LEDGER_TERMINAL = ("succeeded", "noop", "failed")


def wait_for_ledger_settled(
    narrator_id: str,
    known_ids: Any = (),
    *,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """Block until this narrator's new ledger rows leave outcome='started'.

    ADDED 2026-07-30. Extraction used to be awaited inside the turn body, so
    by the time the harness answered, the ledger row was already final and a
    flat `time.sleep(1.0)` was enough. It is not enough any more: the claim is
    written inline at outcome='started' and the extractor now runs on a
    background task that finishes after the response. A fixed sleep would race
    a real model call, and Test C asserts on the FINAL row --- outcome
    'failed', error_class 'ForcedExtractionFailure' --- so reading a row still
    at 'started' would report a false failure.

    Polls instead of sleeping, and returns what it saw rather than raising, so
    a genuine hang is reported as a timeout in the evidence file instead of
    being hidden by a longer sleep.
    """
    seen = set(known_ids or ())
    deadline = time.monotonic() + timeout
    report: Dict[str, Any] = {"timeout_s": timeout, "settled": False,
                              "waited_s": 0.0, "unsettled": []}
    start = time.monotonic()
    while True:
        rows = [r for r in ledger_rows(narrator_id) if r["id"] not in seen]
        unsettled = [r for r in rows
                     if str(r.get("outcome") or "") not in _LEDGER_TERMINAL]
        if rows and not unsettled:
            report["settled"] = True
            report["waited_s"] = round(time.monotonic() - start, 3)
            report["rows"] = len(rows)
            return report
        if time.monotonic() >= deadline:
            report["waited_s"] = round(time.monotonic() - start, 3)
            report["rows"] = len(rows)
            report["unsettled"] = [
                {"id": r["id"], "outcome": r.get("outcome")} for r in unsettled]
            return report
        time.sleep(0.25)


def _delta(pre: Dict[str, Any], post: Dict[str, Any]) -> Dict[str, Any]:
    keys = sorted(set(pre) | set(post))
    out: Dict[str, Any] = {}
    for k in keys:
        a, b = pre.get(k), post.get(k)
        if isinstance(a, int) and isinstance(b, int):
            out[k] = b - a
        elif a != b:
            out[k] = f"{a!r} -> {b!r}"
    return out


def _delta_is_zero(delta: Dict[str, Any], key: str) -> bool:
    """True only when `key` moved by exactly nothing.

    CORRECTED 2026-07-30 by the second live acceptance run. Test C's
    `projection_unchanged` check used to read:

        counts.get("projection_updated", 0) == 0
        and rec["db_delta"].get("projection_version") is None

    That predicate was written when no disposable narrator had ever owned
    an `interview_projections` row, so "unchanged" and "absent" were the
    same state and `_delta` above omitted the key entirely. Once Phase 1
    Test D started writing a real projection for the same narrator, an
    UNCHANGED version began arriving as the integer 0 --- and `0 is None`
    is False, so the check reported a failure whose own detail line read
    `probe projection_updated=0; version delta 0`. Both of those numbers
    are the PASSING values. The assertion contradicted its own evidence.

    The distinction this helper has to preserve is that `_delta` encodes
    three different situations in one slot:

        key absent   the value was equal on both sides and was not an int
                     --- for projection_version that means no row existed
                     before and none exists now. Unchanged.
        int          both sides numeric; the value is post minus pre.
                     Unchanged only when it is exactly 0.
        str          something like "None -> 1": the row came into
                     existence, or a non-numeric value moved. CHANGED,
                     and it must never be read as zero.

    Truthiness is wrong here in both directions: 0 is the value we
    require, and a non-empty string like "None -> 1" is the value we
    reject, so `if delta.get(key)` would invert this check exactly.
    """
    if key not in delta:
        return True
    value = delta[key]
    if isinstance(value, bool):
        return False
    return isinstance(value, int) and value == 0


def projection_is_unchanged(counts: Dict[str, Any],
                            db_delta: Dict[str, Any]) -> bool:
    """No correction projection was created, rewritten, or bumped.

    A named function rather than an inline expression so the regression
    test can exercise THE predicate instead of a copy of it. The bug this
    replaces survived because the expression lived in one place and was
    only ever evaluated by a live run.

    Three independent measurements, each compared explicitly to zero:

        probe projection_updated   the pipeline stage counter --- did the
                                   turn ASK to update a projection
        interview_projections      row count for this narrator --- did a
                                   projection come into existence
        projection_version         the version stamp --- did an existing
                                   projection get rewritten in place at
                                   the same row count

    All three must be zero. None of them may be evaluated for truthiness,
    because zero is the required value.
    """
    return (counts.get("projection_updated", 0) == 0
            and _delta_is_zero(db_delta, "interview_projections")
            and _delta_is_zero(db_delta, "projection_version"))


def ledger_rows(narrator_id: str) -> List[Dict[str, Any]]:
    """The extraction ledger for this narrator. No narrative text lives
    here by design — identifiers, outcome, counts, error CLASS only."""
    conn = _connect()
    try:
        if not _table_exists(conn, "turn_extraction_ledger"):
            return []
        rows = conn.execute(
            "SELECT id, turn_key, turn_id, session_id, turn_mode, source, "
            "outcome, item_count, method, error_class, duration_ms, "
            "created_at, updated_at FROM turn_extraction_ledger "
            "WHERE narrator_id = ? ORDER BY id",
            (narrator_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def last_assistant_turn_row(conv_id: str) -> Optional[int]:
    """The AUTOINCREMENT id of the newest assistant row in this
    conversation. This — not the request's turn_id, and never the text —
    is what the idempotency key is built from, because `turns` has no
    turn_id column and a text key would collide across two legitimately
    identical answers."""
    conn = _connect()
    try:
        if not _table_exists(conn, "turns"):
            return None
        row = conn.execute(
            "SELECT id FROM turns WHERE conv_id = ? AND role = 'assistant' "
            "ORDER BY id DESC LIMIT 1", (conv_id,),
        ).fetchone()
        return int(row["id"]) if row else None
    finally:
        conn.close()


def archive_jsonl_lines(person_id: str, session_id: str) -> Optional[int]:
    """Line count of the append-only transcript for this session.

    The independent half of `archive_event_created`. This is a FILE, not
    a table — the reason the archived probe's `archive_events` entry
    never matched anything.
    """
    path = (_DATA_DIR / "memory" / "archive" / "people" / person_id
            / "sessions" / session_id / "transcript.jsonl")
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
    except OSError:
        return None


def probe_counts(resp: Dict[str, Any]) -> Dict[str, Any]:
    """The five stage tallies as the harness reports them.

    Returns {} when the observability flag is off, which is a setup
    error for this script rather than a pass.
    """
    tp = resp.get("truth_pipeline")
    if not isinstance(tp, dict):
        return {}
    counts = tp.get("counts")
    return dict(counts) if isinstance(counts, dict) else {}


# ── HTTP ──────────────────────────────────────────────────────────────────

def harness_health() -> Dict[str, Any]:
    """GET the harness health route. A 404 means the gate is closed —
    which is the CORRECT closed state: the route answers 404 rather than
    403 so an external probe cannot tell it exists."""
    try:
        r = requests.get(_api_base() + "/api/operator/harness/health", timeout=10)
        try:
            body = r.json()
        except Exception:
            body = (r.text or "")[:200]
        return {"status": r.status_code, "body": body}
    except Exception as exc:
        return {"status": -1, "body": {"error": exc.__class__.__name__}}


def harness_turn(
    *,
    person_id: str,
    text: str,
    session_id: str,
    turn_mode: str = "interview",
    turn_id: str = "",
    timeout_seconds: int = 120,
) -> Dict[str, Any]:
    """POST one turn through /api/operator/harness/interview-turn."""
    payload = {
        "person_id": person_id,
        "text": text,
        "session_style": "clear_direct",
        "turn_mode": turn_mode,
        "session_id": session_id,
        "timeout_seconds": timeout_seconds,
    }
    if turn_id:
        payload["turn_id"] = turn_id
    try:
        r = requests.post(
            _api_base() + "/api/operator/harness/interview-turn",
            json=payload, timeout=timeout_seconds + 20,
        )
    except Exception as exc:
        return {"ok": False, "http_status": -1,
                "errors": [f"transport: {exc.__class__.__name__}"]}
    try:
        data = dict(r.json())
    except Exception:
        data = {"ok": False, "errors": [(r.text or "")[:400]]}
    data["http_status"] = r.status_code
    return data


def _browser_outcome(resp: Dict[str, Any]) -> Dict[str, Any]:
    """What the browser would have seen. The work order requires the
    user-facing turn to remain successful in every test, including the
    one where extraction is forced to fail."""
    types = resp.get("raw_event_types") or []
    final = resp.get("final_text_from_done") or ""
    return {
        "http_status": resp.get("http_status"),
        "ok": bool(resp.get("ok")),
        "done_event_received": "done" in types,
        "final_text_nonempty": bool(final.strip()),
        "final_text_chars": len(final),
        "raw_event_types": list(types),
        "db_locked": bool(resp.get("db_locked")),
        "elapsed_ms": resp.get("elapsed_ms"),
        "errors": list(resp.get("errors") or []),
    }


def _browser_ok(outcome: Dict[str, Any]) -> bool:
    return (outcome["ok"] and outcome["done_event_received"]
            and outcome["final_text_nonempty"] and not outcome["db_locked"])


# ── The five required stage numbers, in one place ──────────────────────────

_REQUIRED_STAGES = ("raw_turn_saved", "archive_event_created",
                    "extract_fields_called", "family_truth_written",
                    "projection_updated")


def _stage_block(counts: Dict[str, Any]) -> Dict[str, Any]:
    return {k: counts.get(k, 0) for k in _REQUIRED_STAGES}


def _check(record: Dict[str, Any], label: str, ok: bool, detail: str) -> None:
    record.setdefault("checks", []).append(
        {"check": label, "passed": bool(ok), "detail": detail})
    if not ok:
        record.setdefault("failures", []).append(f"{label}: {detail}")


# ── Test A — a normal interview turn ──────────────────────────────────────

_TEST_A_TEXT = (
    "We kept a rowboat at the cabin on Pelican Lake and my father "
    "painted it green every spring."
)


def test_a(narrator_id: str) -> Dict[str, Any]:
    session_id = f"gate7p2-a-{narrator_id}"
    turn_id = f"gate7p2-a-{uuid.uuid4()}"
    rec: Dict[str, Any] = {
        "test": "A", "name": "normal interview turn",
        "narrator_id": narrator_id, "session_id": session_id,
        "turn_id": turn_id, "turn_mode": "interview",
    }
    pre = snapshot(narrator_id)
    pre_ledger = ledger_rows(narrator_id)
    pre_archive = archive_jsonl_lines(narrator_id, session_id)
    resp = harness_turn(person_id=narrator_id, text=_TEST_A_TEXT,
                        session_id=session_id, turn_id=turn_id)
    # The probe files its record in a finally, and the extractor now runs on
    # a background task, so neither is guaranteed done when the response is.
    rec["ledger_settle"] = wait_for_ledger_settled(
        narrator_id, {r["id"] for r in pre_ledger})
    post = snapshot(narrator_id)
    post_archive = archive_jsonl_lines(narrator_id, session_id)

    counts = probe_counts(resp)
    rec["probe_stages"] = _stage_block(counts)
    rec["probe_present"] = bool(counts)
    rec["db_pre"] = pre
    rec["db_post"] = post
    rec["db_delta"] = _delta(pre, post)
    rec["archive_jsonl_lines"] = {"pre": pre_archive, "post": post_archive}
    rec["browser"] = _browser_outcome(resp)
    rec["ledger"] = ledger_rows(narrator_id)

    _check(rec, "observability_flag_on", bool(counts),
           "HORNELORE_TRUTH_PIPELINE_LOG must be exported into the SERVER "
           "process, not just this shell. truth_pipeline was "
           f"{resp.get('truth_pipeline')!r}.")
    _check(rec, "extraction_reached_a_final_outcome",
           bool(rec["ledger_settle"].get("settled")),
           "the extraction ledger row never left outcome='started' inside "
           f"{rec['ledger_settle'].get('timeout_s')}s: "
           f"{json.dumps(rec['ledger_settle'])}. Every ledger assertion "
           "below reads a row that is still in flight, so none of them "
           "means anything.")
    _check(rec, "raw_turn_saved==1", counts.get("raw_turn_saved") == 1,
           f"probe reported {counts.get('raw_turn_saved')!r}")
    _check(rec, "archive_event_created>=1",
           isinstance(counts.get("archive_event_created"), int)
           and counts["archive_event_created"] >= 1,
           f"probe reported {counts.get('archive_event_created')!r}")
    _check(rec, "extract_fields_called==1",
           counts.get("extract_fields_called") == 1,
           f"probe reported {counts.get('extract_fields_called')!r} — this is "
           "the number the Phase 1 reading showed as 0, which was the defect")
    _check(rec, "family_truth_written==0",
           counts.get("family_truth_written", 0) == 0,
           f"probe reported {counts.get('family_truth_written')!r}; an "
           "interview turn must not write family truth")
    _check(rec, "projection_updated==0",
           counts.get("projection_updated", 0) == 0,
           f"probe reported {counts.get('projection_updated')!r}; projections "
           "are correction-only")
    # Independent confirmations — the probe is the instrument under test.
    _check(rec, "turns_rows_added", (rec["db_delta"].get("turns") or 0) >= 2,
           f"turns delta was {rec['db_delta'].get('turns')!r}; a completed "
           "turn writes a user row and an assistant row")
    _check(rec, "archive_jsonl_grew",
           isinstance(post_archive, int) and post_archive >= 1,
           f"transcript.jsonl line count went {pre_archive!r} -> "
           f"{post_archive!r}")
    _check(rec, "family_truth_rows_unchanged_in_db",
           (rec["db_delta"].get("family_truth_rows") or 0) == 0
           and (rec["db_delta"].get("family_truth_notes") or 0) == 0,
           f"family truth deltas: rows="
           f"{rec['db_delta'].get('family_truth_rows')!r} notes="
           f"{rec['db_delta'].get('family_truth_notes')!r}")
    # Exactly one ledger row, and it must not be the forced-failure seam.
    led = rec["ledger"]
    _check(rec, "exactly_one_ledger_row", len(led) == 1,
           f"ledger holds {len(led)} rows for this narrator: "
           f"{[r['turn_key'] for r in led]}")
    if len(led) == 1:
        row = led[0]
        _check(rec, "ledger_source_is_chat_ws", row["source"] == "chat_ws",
               f"source={row['source']!r}")
        _check(rec, "ledger_key_is_a_committed_row",
               str(row["turn_key"]).startswith("turnrow:"),
               f"turn_key={row['turn_key']!r}")
        _check(rec, "ledger_outcome_is_not_a_forced_failure",
               row["error_class"] != "ForcedExtractionFailure",
               "HORNELORE_EXTRACTION_FORCE_FAILURE is still set in the "
               "server environment. Phase 1 must run without it — unset it, "
               "restart, and re-run.")
        rec["ledger_outcome"] = row["outcome"]
        rec["ledger_error_class"] = row["error_class"]
        rec["ledger_item_count"] = row["item_count"]
        rec["ledger_duration_ms"] = row["duration_ms"]
    _check(rec, "browser_turn_succeeded", _browser_ok(rec["browser"]),
           json.dumps(rec["browser"]))
    rec["passed"] = not rec.get("failures")
    return rec


# ── Test B — idempotent replay ────────────────────────────────────────────

def test_b(narrator_id: str, session_id: str) -> Dict[str, Any]:
    """Re-invoke extraction for the SAME persisted turn.

    "Reinvoke extraction for the same persisted turn using the safest
    available mechanism." The safest available mechanism is to call the
    shared service directly, in this process, with the turn_key of the
    row the live turn just committed. It touches no running server, sends
    no second turn, and exercises the exact code path a WebSocket
    reconnect would take. If the guard held, the service returns before
    the extractor is ever reached, so this costs no model call.
    """
    import asyncio
    rec: Dict[str, Any] = {
        "test": "B", "name": "idempotent replay",
        "narrator_id": narrator_id, "session_id": session_id,
        "mechanism": ("in-process call to "
                      "api.services.turn_extraction.extract_completed_turn "
                      "with the committed turn_key"),
    }
    row_id = last_assistant_turn_row(session_id)
    rec["assistant_turn_row_id"] = row_id
    if row_id is None:
        rec["failures"] = ["no committed assistant row found for the Test A "
                           "conversation — Test A must run first"]
        rec["passed"] = False
        return rec

    from api import db as _db                      # noqa: E402
    from api.services import turn_extraction as tx  # noqa: E402

    turn_key = _db.turn_extraction_key_for_row(row_id)
    rec["turn_key"] = turn_key
    pre = snapshot(narrator_id)
    pre_ledger = ledger_rows(narrator_id)
    rec["ledger_before"] = pre_ledger

    outcome = asyncio.run(tx.extract_completed_turn(
        narrator_id=narrator_id,
        turn_id=f"gate7p2-b-replay-{uuid.uuid4()}",
        user_text=_TEST_A_TEXT,
        assistant_text="(replay — the assistant text is not re-sent)",
        session_id=session_id,
        turn_key=turn_key,
        turn_mode="interview",
        source="harness_replay",
    ))
    time.sleep(0.3)
    post = snapshot(narrator_id)
    post_ledger = ledger_rows(narrator_id)
    rec["ledger_after"] = post_ledger
    rec["db_delta"] = _delta(pre, post)
    rec["outcome"] = {
        "status": outcome.status, "method": outcome.method,
        "item_count": outcome.item_count, "error_class": outcome.error_class,
        "ok": outcome.ok, "log_fields": outcome.as_log_fields(),
    }

    _check(rec, "replay_reported_duplicate", outcome.status == "duplicate",
           f"status={outcome.status!r} method={outcome.method!r}")
    _check(rec, "replay_reason_is_already_processed",
           outcome.method == "already_processed",
           f"method={outcome.method!r}")
    _check(rec, "replay_is_still_a_success_for_the_caller", outcome.ok,
           "a duplicate must not read as a failure to the turn path")
    _check(rec, "no_second_ledger_row",
           len(post_ledger) == len(pre_ledger),
           f"ledger went {len(pre_ledger)} -> {len(post_ledger)} rows")
    _check(rec, "no_duplicate_proposal_or_output_rows",
           (rec["db_delta"].get("story_candidates") or 0) == 0,
           f"story_candidates delta {rec['db_delta'].get('story_candidates')!r}")
    _check(rec, "no_duplicate_family_truth",
           (rec["db_delta"].get("family_truth_rows") or 0) == 0
           and (rec["db_delta"].get("family_truth_notes") or 0) == 0,
           json.dumps({k: v for k, v in rec["db_delta"].items()
                       if "family_truth" in k}))
    # The first attempt's real result must survive the replay: a
    # 'duplicate' describes a SECOND attempt and is deliberately not
    # storable, so writing it would erase the outcome that actually ran.
    if pre_ledger and post_ledger:
        _check(rec, "first_attempt_outcome_preserved",
               pre_ledger[0]["outcome"] == post_ledger[0]["outcome"]
               and pre_ledger[0]["updated_at"] == post_ledger[0]["updated_at"],
               f"{pre_ledger[0]['outcome']!r}/{pre_ledger[0]['updated_at']!r} "
               f"-> {post_ledger[0]['outcome']!r}/"
               f"{post_ledger[0]['updated_at']!r}")
    rec["passed"] = not rec.get("failures")
    return rec


# ── Test D — the correction control ───────────────────────────────────────

_TEST_D_TEXT = "Actually, we only had two children, not three."


def test_d(narrator_id: str) -> Dict[str, Any]:
    """A correction-mode turn must still reach the projection writer, and
    must NOT be extracted.

    Both halves matter. The first proves the interview-only extraction
    change did not break correction behaviour. The second proves the new
    hook honours EXTRACTION_ELIGIBLE_TURN_MODES rather than firing on
    every completed turn.
    """
    session_id = f"gate7p2-d-{narrator_id}"
    turn_id = f"gate7p2-d-{uuid.uuid4()}"
    rec: Dict[str, Any] = {
        "test": "D", "name": "correction control",
        "narrator_id": narrator_id, "session_id": session_id,
        "turn_id": turn_id, "turn_mode": "correction",
    }
    pre = snapshot(narrator_id)
    pre_ledger = ledger_rows(narrator_id)
    resp = harness_turn(person_id=narrator_id, text=_TEST_D_TEXT,
                        session_id=session_id, turn_id=turn_id,
                        turn_mode="correction")
    time.sleep(1.0)
    post = snapshot(narrator_id)
    post_ledger = ledger_rows(narrator_id)

    counts = probe_counts(resp)
    rec["probe_stages"] = _stage_block(counts)
    rec["db_delta"] = _delta(pre, post)
    rec["browser"] = _browser_outcome(resp)

    # Independent read: did the projection actually change? Field NAMES
    # and provenance only — the narrator's values are not copied into the
    # evidence file.
    applied_sources: List[str] = []
    field_names: List[str] = []
    conn = _connect()
    try:
        if _table_exists(conn, "interview_projections"):
            row = conn.execute(
                "SELECT projection_json FROM interview_projections "
                "WHERE person_id = ?", (narrator_id,)).fetchone()
            if row:
                try:
                    blob = json.loads(row["projection_json"] or "{}")
                    fields = (blob.get("fields")
                              if isinstance(blob.get("fields"), dict) else {})
                    for name, meta in fields.items():
                        field_names.append(name)
                        if isinstance(meta, dict) and meta.get("source"):
                            applied_sources.append(str(meta["source"]))
                except Exception as exc:
                    rec["projection_read_error"] = exc.__class__.__name__
    finally:
        conn.close()
    rec["projection_field_names"] = sorted(field_names)
    rec["projection_field_sources"] = sorted(set(applied_sources))

    _check(rec, "correction_payload_emitted",
           "correction_payload" in (resp.get("raw_event_types") or []),
           f"raw_event_types={resp.get('raw_event_types')!r}")
    _check(rec, "projection_update_path_reachable",
           counts.get("projection_updated", 0) >= 1
           or "correction" in rec["projection_field_sources"],
           f"probe projection_updated={counts.get('projection_updated')!r}; "
           f"field sources={rec['projection_field_sources']!r}")
    _check(rec, "correction_turn_was_not_extracted",
           counts.get("extract_fields_called", 0) == 0,
           f"extract_fields_called={counts.get('extract_fields_called')!r}; "
           "a correction turn is not extraction-eligible")
    _check(rec, "no_ledger_row_for_the_correction_turn",
           len(post_ledger) == len(pre_ledger),
           f"ledger went {len(pre_ledger)} -> {len(post_ledger)} rows")
    _check(rec, "family_truth_still_untouched",
           counts.get("family_truth_written", 0) == 0
           and (rec["db_delta"].get("family_truth_rows") or 0) == 0,
           "a correction turn must not write family truth either")
    _check(rec, "browser_turn_succeeded", _browser_ok(rec["browser"]),
           json.dumps(rec["browser"]))
    rec["passed"] = not rec.get("failures")
    return rec


# ── Test C — forced extraction failure ────────────────────────────────────

_TEST_C_TEXT = (
    "My grandmother ran a boarding house on Third Street during the war."
)


def test_c(narrator_id: str) -> Dict[str, Any]:
    """Extraction fails; everything else must survive.

    The failure comes from HORNELORE_EXTRACTION_FORCE_FAILURE, a seam
    that exists only for this test, is read at extraction time, is off by
    default, and short-circuits before the extractor is built so no model
    call is spent. Nothing in the production configuration is touched:
    "Do not corrupt production configuration to create this failure."
    """
    session_id = f"gate7p2-c-{narrator_id}"
    turn_id = f"gate7p2-c-{uuid.uuid4()}"
    rec: Dict[str, Any] = {
        "test": "C", "name": "forced extraction failure",
        "narrator_id": narrator_id, "session_id": session_id,
        "turn_id": turn_id, "turn_mode": "interview",
        "seam": "HORNELORE_EXTRACTION_FORCE_FAILURE=raise (harness-only)",
    }
    pre = snapshot(narrator_id)
    pre_ledger = ledger_rows(narrator_id)
    pre_archive = archive_jsonl_lines(narrator_id, session_id)
    resp = harness_turn(person_id=narrator_id, text=_TEST_C_TEXT,
                        session_id=session_id, turn_id=turn_id)
    rec["ledger_settle"] = wait_for_ledger_settled(
        narrator_id, {r["id"] for r in pre_ledger})
    post = snapshot(narrator_id)
    post_ledger = ledger_rows(narrator_id)
    post_archive = archive_jsonl_lines(narrator_id, session_id)

    counts = probe_counts(resp)
    rec["probe_stages"] = _stage_block(counts)
    rec["db_delta"] = _delta(pre, post)
    rec["archive_jsonl_lines"] = {"pre": pre_archive, "post": post_archive}
    rec["browser"] = _browser_outcome(resp)
    rec["ledger_before_count"] = len(pre_ledger)
    rec["ledger_after"] = post_ledger

    new_rows = [r for r in post_ledger
                if r["id"] not in {x["id"] for x in pre_ledger}]
    rec["new_ledger_rows"] = new_rows

    _check(rec, "observability_flag_on", bool(counts),
           "HORNELORE_TRUTH_PIPELINE_LOG must be exported into the server "
           "process")
    _check(rec, "raw_turn_saved==1", counts.get("raw_turn_saved") == 1,
           f"probe reported {counts.get('raw_turn_saved')!r}")
    _check(rec, "turn_rows_still_committed",
           (rec["db_delta"].get("turns") or 0) >= 2,
           f"turns delta {rec['db_delta'].get('turns')!r}")
    _check(rec, "archive_event_still_committed",
           isinstance(counts.get("archive_event_created"), int)
           and counts["archive_event_created"] >= 1
           and isinstance(post_archive, int) and post_archive >= 1,
           f"probe={counts.get('archive_event_created')!r} "
           f"jsonl_lines={post_archive!r}")
    _check(rec, "browser_turn_still_completed", _browser_ok(rec["browser"]),
           json.dumps(rec["browser"]))
    # THE STAGE MEANS "ASKED", NOT "SUCCEEDED". If this reads 0 the
    # observability is worthless, because 0 is also what the original
    # defect produced.
    _check(rec, "extract_fields_called==1_even_though_it_failed",
           counts.get("extract_fields_called") == 1,
           f"probe reported {counts.get('extract_fields_called')!r}; a failed "
           "attempt must not be indistinguishable from never asking")
    _check(rec, "extraction_reached_a_final_outcome",
           bool(rec["ledger_settle"].get("settled")),
           "the extraction ledger row never left outcome='started' inside "
           f"{rec['ledger_settle'].get('timeout_s')}s: "
           f"{json.dumps(rec['ledger_settle'])}. Every ledger assertion "
           "below reads a row that is still in flight, so none of them "
           "means anything.")
    _check(rec, "exactly_one_new_ledger_row", len(new_rows) == 1,
           f"{len(new_rows)} new ledger rows")
    if len(new_rows) == 1:
        row = new_rows[0]
        rec["ledger_outcome"] = row["outcome"]
        rec["ledger_error_class"] = row["error_class"]
        _check(rec, "failure_recorded_as_failed", row["outcome"] == "failed",
               f"outcome={row['outcome']!r}")
        _check(rec, "failure_carries_the_seam_class",
               row["error_class"] == "ForcedExtractionFailure",
               f"error_class={row['error_class']!r} — if this is empty the "
               "seam was not exported into the SERVER process; export "
               "HORNELORE_EXTRACTION_FORCE_FAILURE=raise, restart, re-run")
        _check(rec, "no_error_message_stored",
               "=" not in (row["error_class"] or "")
               and " " not in (row["error_class"] or ""),
               "error_class must be a bare class name, never a message that "
               f"could quote narrator text: {row['error_class']!r}")
    _check(rec, "family_truth_unchanged",
           counts.get("family_truth_written", 0) == 0
           and (rec["db_delta"].get("family_truth_rows") or 0) == 0
           and (rec["db_delta"].get("family_truth_notes") or 0) == 0,
           json.dumps({k: v for k, v in rec["db_delta"].items()
                       if "family_truth" in k}))
    # CORRECTED 2026-07-30 — see _delta_is_zero. Three independent
    # measurements, each compared explicitly against zero: the probe stage,
    # the projection ROW COUNT, and the projection VERSION stamp. The row
    # count catches a projection appearing; the version stamp catches one
    # being rewritten in place at the same row count.
    _check(rec, "projection_unchanged",
           projection_is_unchanged(counts, rec["db_delta"]),
           f"probe projection_updated={counts.get('projection_updated')!r}; "
           f"row delta {rec['db_delta'].get('interview_projections')!r}; "
           f"version delta {rec['db_delta'].get('projection_version')!r}")
    rec["passed"] = not rec.get("failures")
    return rec


# ── Test E — harness disabled, then cleanup ───────────────────────────────

_HARNESS_ROUTES = (
    ("GET", "/api/operator/harness/health"),
    ("POST", "/api/operator/harness/interview-turn"),
)


def test_e(narrator_id: str) -> Dict[str, Any]:
    """Every temporary flag gone; the harness must be invisible again.

    404, not 403 — the gate answers "no such route" so an external probe
    cannot learn the surface exists. A 403 here would be a regression in
    its own right.
    """
    rec: Dict[str, Any] = {"test": "E", "name": "harness disabled + cleanup",
                           "narrator_id": narrator_id, "routes": []}
    for method, path in _HARNESS_ROUTES:
        url = _api_base() + path
        try:
            if method == "GET":
                r = requests.get(url, timeout=10)
            else:
                r = requests.post(url, json={"person_id": "x", "text": "x"},
                                  timeout=15)
            status = r.status_code
        except Exception as exc:
            status = -1
        entry = {"method": method, "path": path, "status": status}
        rec["routes"].append(entry)
        _check(rec, f"{method} {path} -> 404", status == 404,
               f"got {status}; 404 is required so the route's existence is "
               "not discoverable, and 403 would leak it")

    # ── Cleanup, delegated to the archived probe's guarded routine ──────
    # It refuses any narrator id without the "harness-test-" prefix, so
    # Kent's control turn is out of reach by construction. Reusing it also
    # exercises the table list repaired in Step 7 — including the new
    # extraction ledger, which is why the ledger was added to that list.
    rec["cleanup"] = {"mechanism":
                      "scripts/archive/golfball_narrator_isolation.py"
                      "::cleanup_synthetic"}
    pre = snapshot(narrator_id)
    rec["cleanup"]["db_before"] = pre
    try:
        import importlib.util
        probe_path = (_REPO_ROOT / "scripts" / "archive"
                      / "golfball_narrator_isolation.py")
        spec = importlib.util.spec_from_file_location(
            "_gate7_cleanup_probe", probe_path)
        mod = importlib.util.module_from_spec(spec)
        # Registered before execution: the probe defines a module-scope
        # dataclass, and dataclasses resolves annotations through
        # sys.modules[cls.__module__].
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        result = mod.cleanup_synthetic(str(_DB_PATH), narrator_id)
        rec["cleanup"]["result"] = result
    except Exception as exc:
        rec["cleanup"]["error"] = f"{exc.__class__.__name__}: {exc}"
        result = {"ok": False}
    post = snapshot(narrator_id)
    rec["cleanup"]["db_after"] = post

    _check(rec, "cleanup_ran", bool(result.get("ok")),
           json.dumps(rec["cleanup"].get("result")
                      or rec["cleanup"].get("error")))
    residual = {k: v for k, v in post.items()
                if isinstance(v, int) and v > 0}
    _check(rec, "no_rows_left_for_the_disposable_narrator", not residual,
           f"rows still present: {residual}")
    rec["passed"] = not rec.get("failures")
    return rec


# ── State carried between phases ──────────────────────────────────────────

def _read_state() -> Dict[str, Any]:
    if _STATE_PATH.exists():
        try:
            return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _write_state(state: Dict[str, Any]) -> None:
    _XFER_DIR.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _env_block() -> Dict[str, Any]:
    """What THIS process sees. The server's own environment is what
    actually matters, which is why every flag-dependent check above reads
    an observed behaviour rather than this block."""
    return {
        "resolved_db_path": str(_DB_PATH),
        "db_exists": _DB_PATH.exists(),
        "db_bytes": _DB_PATH.stat().st_size if _DB_PATH.exists() else None,
        "data_dir": str(_DATA_DIR),
        "env_provenance": _ENV_PROVENANCE,
        "api_base": _api_base(),
        "harness_flag_in_this_shell":
            os.environ.get("HORNELORE_OPERATOR_HARNESS", "(unset)"),
        "truth_log_flag_in_this_shell":
            os.environ.get("HORNELORE_TRUTH_PIPELINE_LOG", "(unset)"),
        "forced_failure_in_this_shell":
            os.environ.get("HORNELORE_EXTRACTION_FORCE_FAILURE", "(unset)"),
    }


# ── Reporting ─────────────────────────────────────────────────────────────

def _print_record(rec: Dict[str, Any]) -> None:
    flag = "PASS" if rec.get("passed") else "FAIL"
    print(f"\n── Test {rec['test']} — {rec['name']}: {flag}")
    stages = rec.get("probe_stages")
    if stages:
        print("   " + "  ".join(f"{k}={stages[k]}" for k in _REQUIRED_STAGES))
    if rec.get("browser"):
        b = rec["browser"]
        print(f"   browser: ok={b['ok']} done={b['done_event_received']} "
              f"final_text_chars={b['final_text_chars']} "
              f"db_locked={b['db_locked']} elapsed_ms={b['elapsed_ms']}")
    if rec.get("outcome"):
        print(f"   service outcome: {rec['outcome']['status']} "
              f"({rec['outcome']['method']})")
    for f in rec.get("failures") or []:
        print(f"   ! {f}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="WO-TRUTH-PIPELINE-01 Phase 2 live acceptance run.")
    ap.add_argument("--phase", type=int, required=True, choices=(1, 2, 3),
                    help="1: Tests A,B,D  |  2: Test C  |  3: Test E + cleanup")
    ap.add_argument("--narrator-id", default="",
                    help="reuse an existing disposable narrator instead of "
                         "the one recorded by phase 1")
    args = ap.parse_args()

    env = _env_block()
    print("WO-TRUTH-PIPELINE-01 Phase 2 — live acceptance, "
          f"phase {args.phase}")
    print(f"  api            : {env['api_base']}")
    print(f"  database       : {env['resolved_db_path']} "
          f"({env['db_bytes']} bytes)")
    print(f"  DATA_DIR       : {env['env_provenance'].get('DATA_DIR')}")
    print(f"  DB_NAME        : {env['env_provenance'].get('DB_NAME')}")

    if not _DB_PATH.exists():
        print("\nFATAL: the resolved database does not exist. This process is "
              "not looking at the same DATA_DIR as the server, and every "
              "count below would be a meaningless zero.", file=sys.stderr)
        return 2

    state = _read_state()
    records: List[Dict[str, Any]] = []

    if args.phase == 1:
        narrator_id = (args.narrator_id
                       or f"harness-test-gate7p2-{uuid.uuid4()}")
        health = harness_health()
        print(f"  harness health : {health['status']}")
        if health["status"] != 200:
            print("\nFATAL: the operator harness is not enabled. Export "
                  "HORNELORE_OPERATOR_HARNESS=1 and "
                  "HORNELORE_TRUTH_PIPELINE_LOG=1, restart the stack, and "
                  "re-run. (A 404 here is the correct CLOSED state — it is "
                  "only wrong for phases 1 and 2.)", file=sys.stderr)
            return 2
        armed = bool((health.get("body") or {}).get("forced_failure_armed")) \
            if isinstance(health.get("body"), dict) else False
        print(f"  failure seam   : {'ARMED' if armed else 'disarmed'} "
              "(server process)")
        if armed:
            print("\nFATAL: HORNELORE_EXTRACTION_FORCE_FAILURE is armed in the "
                  "SERVER process. Tests A, B and D measure the normal path "
                  "and would all be measuring the Test C seam instead. Unset "
                  "it, restart the stack, and re-run phase 1.", file=sys.stderr)
            return 2
        print(f"  narrator       : {narrator_id}")
        fixture = ensure_disposable_person(narrator_id)
        print(f"  people row     : {fixture}")
        if not fixture.get("ok"):
            print("\nFATAL: could not create the disposable people row. "
                  "interview_projections has a FOREIGN KEY to people(id), so "
                  "Test D would fail on the fixture rather than on the "
                  "correction path.", file=sys.stderr)
            return 2
        a = test_a(narrator_id)
        records.append(a)
        _print_record(a)
        b = test_b(narrator_id, a["session_id"])
        records.append(b)
        _print_record(b)
        d = test_d(narrator_id)
        records.append(d)
        _print_record(d)
        state.update({
            "narrator_id": narrator_id,
            "test_a_session_id": a["session_id"],
            "phase_1_passed": all(r.get("passed") for r in records),
        })
        _write_state(state)

    elif args.phase == 2:
        narrator_id = args.narrator_id or state.get("narrator_id", "")
        if not narrator_id:
            print("\nFATAL: no narrator id. Run --phase 1 first, or pass "
                  "--narrator-id.", file=sys.stderr)
            return 2
        health = harness_health()
        print(f"  harness health : {health['status']}")
        if health["status"] != 200:
            print("\nFATAL: the harness must still be enabled for Test C.",
                  file=sys.stderr)
            return 2
        # ADDED 2026-07-30. The first live Test C was run against a server
        # that had never been restarted with the seam exported. It recorded
        # error_class='CancelledError' from a real extractor at ~830 ms
        # instead of ForcedExtractionFailure, so the test measured nothing
        # and had to be discarded. The server now reports its own arming
        # state, and this refuses to spend a turn without it.
        armed = bool((health.get("body") or {}).get("forced_failure_armed")) \
            if isinstance(health.get("body"), dict) else False
        print(f"  failure seam   : {'ARMED' if armed else 'DISARMED'} "
              "(server process)")
        if not armed:
            print("\nFATAL: the forced-failure seam is not live in the SERVER "
                  "process. Exporting HORNELORE_EXTRACTION_FORCE_FAILURE in "
                  "this shell is not enough — the stack must be restarted "
                  "with it exported. Stop the API, export the variable in the "
                  "terminal that starts it, start it again, and re-run "
                  "phase 2.", file=sys.stderr)
            if env["forced_failure_in_this_shell"] == "(unset)":
                print("       (it is not set in this shell either.)",
                      file=sys.stderr)
            return 2
        print(f"  narrator       : {narrator_id}")
        c = test_c(narrator_id)
        records.append(c)
        _print_record(c)
        state["phase_2_passed"] = c.get("passed")
        _write_state(state)

    else:
        narrator_id = args.narrator_id or state.get("narrator_id", "")
        if not narrator_id:
            print("\nFATAL: no narrator id to clean. Run --phase 1 first, or "
                  "pass --narrator-id.", file=sys.stderr)
            return 2
        print(f"  narrator       : {narrator_id}")
        e = test_e(narrator_id)
        records.append(e)
        _print_record(e)
        state["phase_3_passed"] = e.get("passed")
        _write_state(state)

    evidence = {
        "work_order": "WO-TRUTH-PIPELINE-01 Phase 2 (Gate 7)",
        "phase": args.phase,
        "environment": env,
        "tests": records,
        "all_passed": all(r.get("passed") for r in records),
    }
    _XFER_DIR.mkdir(parents=True, exist_ok=True)
    out = _XFER_DIR / f"gate7_phase2_evidence_phase{args.phase}.json"
    out.write_text(json.dumps(evidence, indent=2, default=str),
                   encoding="utf-8")
    print(f"\nEvidence written to {out}")
    print("PHASE RESULT: " + ("PASS" if evidence["all_passed"] else "FAIL"))
    return 0 if evidence["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
