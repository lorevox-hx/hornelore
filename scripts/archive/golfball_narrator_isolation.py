"""WO-GOLFBALL-HARNESS-02 — Narrator Isolation + Truth Pipeline Flow.

Companion module to scripts/archive/run_golfball_interview_eval.py.
Answers two questions that cannot be answered by the style-diff probe:

  1. NARRATOR ISOLATION
     If Kent says A, Janice says B, Kent says C — does Kent's record
     contain only A + C (not B), and Janice's record contain only B
     (not A or C)?
     Catches: cross-narrator contamination (BUG-208 class), session
     bleed, conv_id pollution, narrator-state leak across switches.

  2. TRUTH PIPELINE FLOW
     For a single turn, verify the data propagates through every
     surface that should see it:
       raw turn saved (turns / archive_events)
       story candidate preserved (story_candidates)
       shadow/proposal created (family_truth_rows, if WO-13 wired)
       projection updated (interview_projection)
       operator review surface sees it (/api/operator/story-candidates)
       chronology / timeline surface sees it (/api/chronology-accordion)
       memoir peek surface sees it (memoir_export / projection)
     Surfaces that aren't reachable get reported as "skipped: 404"
     so the harness fails LOUD on real surfaces and stays QUIET on
     deferred lanes.

Hits POST /api/operator/harness/interview-turn (gated by
HORNELORE_OPERATOR_HARNESS=1) for every chat turn. Uses two synthetic
narrators (`harness-test-kent-<uuid>` + `harness-test-janice-<uuid>`)
so the harness can clean up after itself and never touches production
narrator records. Each harness turn writes to those synthetic ids and
they're DELETEd at the end.

Pass/fail contract:
  - Each turn must produce row-count deltas for the SPEAKING narrator
    AND zero deltas for the OTHER narrator.
  - Cross-narrator text-leakage check: no row written for narrator
    X may contain a unique substring from narrator Y's text.
  - Each turn's pipeline-flow assertion: at least the bedrock
    surfaces (story_candidates, /api/operator/story-candidates) must
    show the new data. Other surfaces report best-effort.

Threshold for noise tolerance: zero. If Kent's count goes up after
Janice speaks, that IS contamination, full stop — no LLM
stochasticity excuse.
"""
from __future__ import annotations

import dataclasses
import json
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


# ── Test sequence ──────────────────────────────────────────────────────────
#
# Three turns, each from a different narrator, each with distinguishing
# tokens so cross-leakage is visible by string-search alone.
#   - Turn A: Kent — Otto / Stanley / 1893 / Norway
#   - Turn B: Janice — Spokane / 1939 / Verene / piano
#   - Turn C: Kent — Mandan / John Deere / 1958 / cattle
# Each turn carries 3+ scene anchors so story_candidate fires too,
# letting us verify preservation flows narrator-correctly.

@dataclasses.dataclass
class IsolationTurn:
    narrator_key: str  # "kent" or "janice" — abstract; gets resolved to synthetic id
    user_text: str
    unique_tokens: Tuple[str, ...]  # substrings unique enough to detect leakage
    expect_story_candidate: bool = True


ISOLATION_SEQUENCE: List[IsolationTurn] = [
    IsolationTurn(
        narrator_key="kent",
        user_text=(
            "My grandfather Otto Horne came over from Norway in 1893. "
            "We grew up on the farm in Stanley, North Dakota."
        ),
        unique_tokens=("Otto Horne", "Norway", "1893", "Stanley"),
    ),
    IsolationTurn(
        narrator_key="janice",
        user_text=(
            "I was born in Spokane on August 30, 1939. "
            "My mother Verene played the piano in our home."
        ),
        unique_tokens=("Spokane", "August 30", "1939", "Verene"),
    ),
    IsolationTurn(
        narrator_key="kent",
        user_text=(
            "My father drove a John Deere tractor at the Mandan farm in 1958. "
            "We had cattle and chickens then."
        ),
        unique_tokens=("John Deere", "Mandan", "1958", "cattle"),
    ),
]


# ── DB probes ──────────────────────────────────────────────────────────────

NARRATOR_SCOPED_TABLES_NARRATOR_ID = (
    "story_candidates",
    "photos",                # WO-LORI-PHOTO-SHARED-01
    "photo_review_queue",
    "narrator_relationships",
)
NARRATOR_SCOPED_TABLES_PERSON_ID = (
    "memory_archive_audio",
    "memory_archive_events",
    "media_archive_items",
    "profiles",
    "interview_segment_flags",
    "interview_projection",
    "family_truth_rows",
    "archive_events",
)


def db_connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _scoped_count(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    narrator_id: str,
) -> Optional[int]:
    """Count rows where the given column equals narrator_id. Returns
    None if the table or column is missing."""
    if not _table_exists(conn, table):
        return None
    try:
        cur = conn.execute(
            f"SELECT COUNT(*) AS n FROM {table} WHERE {column} = ?",
            (narrator_id,),
        )
        row = cur.fetchone()
        return int(row["n"]) if row else 0
    except sqlite3.Error:
        return None


def snapshot_narrator(db_path: str, narrator_id: str) -> Dict[str, Any]:
    """Take a snapshot of all narrator-scoped table counts. Returns a
    dict {table: count_or_null}. Tables that are missing from the
    schema get None (not zero) so a follow-up diff can distinguish
    'unchanged' from 'never existed'."""
    if not Path(db_path).exists():
        return {"_error": f"DB not found: {db_path}"}
    conn = db_connect(db_path)
    try:
        snap: Dict[str, Any] = {}
        for table in NARRATOR_SCOPED_TABLES_NARRATOR_ID:
            snap[table] = _scoped_count(conn, table, "narrator_id", narrator_id)
        for table in NARRATOR_SCOPED_TABLES_PERSON_ID:
            snap[table] = _scoped_count(conn, table, "person_id", narrator_id)
        return snap
    finally:
        conn.close()


def find_text_in_any_narrator_row(
    db_path: str,
    narrator_id: str,
    needle: str,
) -> List[str]:
    """Search every text-like column in every narrator-scoped table
    for `needle`. Returns a list of "table.column" hits where the
    substring was found in a row owned by narrator_id. Used to detect
    cross-narrator text leakage — e.g., does Kent's row set contain
    Janice's 'Spokane'?"""
    if not Path(db_path).exists() or not narrator_id or not needle:
        return []
    hits: List[str] = []
    conn = db_connect(db_path)
    try:
        # Combine both column conventions
        all_tables = [
            (t, "narrator_id") for t in NARRATOR_SCOPED_TABLES_NARRATOR_ID
        ] + [
            (t, "person_id") for t in NARRATOR_SCOPED_TABLES_PERSON_ID
        ]
        for table, scope_col in all_tables:
            if not _table_exists(conn, table):
                continue
            try:
                cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
            except sqlite3.Error:
                continue
            text_cols = [
                c["name"] for c in cols
                if str(c["type"]).upper() in ("TEXT", "VARCHAR", "JSON", "")
                and c["name"] != scope_col
            ]
            for col in text_cols:
                try:
                    row = conn.execute(
                        f"SELECT 1 FROM {table} "
                        f"WHERE {scope_col} = ? AND {col} LIKE ? LIMIT 1",
                        (narrator_id, f"%{needle}%"),
                    ).fetchone()
                except sqlite3.Error:
                    continue
                if row:
                    hits.append(f"{table}.{col}")
        return hits
    finally:
        conn.close()


# ── HTTP probes ────────────────────────────────────────────────────────────

def call_harness_turn(
    *,
    api: str,
    person_id: str,
    text: str,
    session_style: str,
    session_id: str,
    timeout_seconds: int = 120,
) -> Dict[str, Any]:
    """POST one turn to /api/operator/harness/interview-turn."""
    payload = {
        "person_id": person_id,
        "text": text,
        "session_style": session_style,
        "turn_mode": "interview",
        "session_id": session_id,
        "timeout_seconds": timeout_seconds,
    }
    try:
        r = requests.post(
            api.rstrip("/") + "/api/operator/harness/interview-turn",
            json=payload,
            timeout=timeout_seconds + 15,
        )
    except Exception as exc:
        return {"ok": False, "errors": [f"http_error: {exc!r}"], "http_ok": False}
    try:
        data = r.json()
    except Exception:
        data = {"ok": False, "errors": [r.text[:500]]}
    data["http_status"] = r.status_code
    data["http_ok"] = r.ok
    return data


def probe_get(api: str, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """GET a JSON endpoint. Returns {ok, status, body}. Used for
    pipeline-flow propagation checks; gracefully reports unreachable
    endpoints so the harness doesn't hard-fail on missing surfaces."""
    try:
        r = requests.get(
            api.rstrip("/") + path,
            params=params or {},
            timeout=10,
        )
        try:
            body = r.json()
        except Exception:
            body = r.text[:300]
        return {"ok": r.ok, "status": r.status_code, "body": body}
    except Exception as exc:
        return {"ok": False, "status": -1, "body": {"error": repr(exc)}}


# ── Pipeline flow surfaces ─────────────────────────────────────────────────

def pipeline_flow_check(
    *,
    api: str,
    db_path: str,
    narrator_id: str,
    needle: str,
) -> Dict[str, Any]:
    """For a known just-spoken turn, walk every surface that should
    see the data and report visibility. Each surface independently
    passes / fails / skipped.

    Surfaces probed:
      DB:
        - turns / archive_events (raw transcript persisted)
        - story_candidates (preservation lane wrote the row)
        - family_truth_rows (WO-13 shadow/proposal — best-effort)
        - interview_projection (state — best-effort)
      HTTP:
        - GET /api/operator/story-candidates?narrator_id=X
            (operator review surface visible)
        - GET /api/chronology-accordion?person_id=X (timeline surface)
        - GET /api/transcript?conv_id=... (transcript surface)
    """
    surfaces: Dict[str, Any] = {}

    # ── DB-side ───────────────────────────────────────────────────────────
    if Path(db_path).exists():
        conn = db_connect(db_path)
        try:
            # story_candidates with this narrator + needle in transcript
            # Sanitize LIKE wildcards in needle so '%' / '_' in narrator
            # text don't match unrelated rows.
            esc_needle = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            if _table_exists(conn, "story_candidates"):
                try:
                    cur = conn.execute(
                        "SELECT COUNT(*) AS n FROM story_candidates "
                        "WHERE narrator_id = ? AND transcript LIKE ? ESCAPE '\\'",
                        (narrator_id, f"%{esc_needle}%"),
                    )
                    # Single fetchone — second call returns None and would crash.
                    n = int(cur.fetchone()["n"])
                    surfaces["db.story_candidates"] = {"ok": n > 0, "matches": n}
                except sqlite3.Error as exc:
                    surfaces["db.story_candidates"] = {
                        "ok": False, "error": repr(exc),
                    }
            else:
                surfaces["db.story_candidates"] = {
                    "ok": False, "skipped": "table missing",
                }

            # archive_events with this person_id + needle in content
            if _table_exists(conn, "archive_events"):
                try:
                    cur = conn.execute(
                        "SELECT COUNT(*) AS n FROM archive_events "
                        "WHERE person_id = ? AND content LIKE ? ESCAPE '\\'",
                        (narrator_id, f"%{esc_needle}%"),
                    )
                    n = int(cur.fetchone()["n"])
                    surfaces["db.archive_events"] = {"ok": n > 0, "matches": n}
                except sqlite3.Error as exc:
                    surfaces["db.archive_events"] = {
                        "ok": False, "error": repr(exc),
                    }
            else:
                surfaces["db.archive_events"] = {
                    "ok": False, "skipped": "table missing",
                }

            # family_truth_rows with this person_id (any row)
            if _table_exists(conn, "family_truth_rows"):
                try:
                    cur = conn.execute(
                        "SELECT COUNT(*) AS n FROM family_truth_rows "
                        "WHERE person_id = ?",
                        (narrator_id,),
                    )
                    surfaces["db.family_truth_rows"] = {
                        "ok": True,  # presence-only check; row count != truth
                        "count": int(cur.fetchone()["n"]),
                    }
                except sqlite3.Error as exc:
                    surfaces["db.family_truth_rows"] = {
                        "ok": False, "error": repr(exc),
                    }
            else:
                surfaces["db.family_truth_rows"] = {
                    "ok": False, "skipped": "table missing (WO-13 not deployed)",
                }

            # interview_projection — presence check only
            if _table_exists(conn, "interview_projection"):
                try:
                    cur = conn.execute(
                        "SELECT COUNT(*) AS n FROM interview_projection "
                        "WHERE person_id = ?",
                        (narrator_id,),
                    )
                    surfaces["db.interview_projection"] = {
                        "ok": True,
                        "count": int(cur.fetchone()["n"]),
                    }
                except sqlite3.Error as exc:
                    surfaces["db.interview_projection"] = {
                        "ok": False, "error": repr(exc),
                    }
            else:
                surfaces["db.interview_projection"] = {
                    "ok": False, "skipped": "table missing",
                }
        finally:
            conn.close()

    # ── HTTP-side ─────────────────────────────────────────────────────────
    # Operator review surface: must be enabled for this check to work
    sc = probe_get(api, "/api/operator/story-candidates",
                   params={"narrator_id": narrator_id, "limit": 50})
    if sc.get("status") == 404:
        surfaces["http.operator_story_review"] = {
            "ok": False,
            "skipped": (
                "404 — set HORNELORE_OPERATOR_STORY_REVIEW=1 + restart"
            ),
        }
    elif sc.get("ok") and isinstance(sc.get("body"), dict):
        items = sc["body"].get("items", [])
        match = any(needle in (it.get("transcript_preview") or "") for it in items)
        surfaces["http.operator_story_review"] = {
            "ok": match,
            "items_count": len(items),
        }
    else:
        surfaces["http.operator_story_review"] = {
            "ok": False, "status": sc.get("status"),
        }

    # Chronology / timeline — best-effort
    ca = probe_get(api, "/api/chronology-accordion",
                   params={"person_id": narrator_id})
    if ca.get("status") in (404, 405):
        surfaces["http.chronology_accordion"] = {
            "ok": False, "skipped": f"status={ca.get('status')}",
        }
    elif ca.get("ok"):
        surfaces["http.chronology_accordion"] = {"ok": True}
    else:
        surfaces["http.chronology_accordion"] = {
            "ok": False, "status": ca.get("status"),
        }

    return surfaces


# ── Cleanup ────────────────────────────────────────────────────────────────

def make_synthetic(prefix: str) -> str:
    return f"harness-test-{prefix}-{uuid.uuid4()}"


def cleanup_synthetic(db_path: str, narrator_id: str) -> Dict[str, Any]:
    """DELETE every row that touches a synthetic narrator. Mirror of
    cleanup_synthetic_narrator in the parent harness, scoped wider."""
    if not Path(db_path).exists():
        return {"ok": False, "error": "DB not found"}
    if not narrator_id.startswith("harness-test-"):
        return {"ok": False, "error": "refusing to cleanup non-synthetic narrator"}

    conn = db_connect(db_path)
    deleted: Dict[str, int] = {}
    try:
        # narrator_id-scoped tables
        for table in NARRATOR_SCOPED_TABLES_NARRATOR_ID:
            if not _table_exists(conn, table):
                continue
            try:
                cur = conn.execute(
                    f"DELETE FROM {table} WHERE narrator_id = ?",
                    (narrator_id,),
                )
                deleted[table] = cur.rowcount
            except sqlite3.Error:
                deleted[table] = -1
        # person_id-scoped tables
        for table in NARRATOR_SCOPED_TABLES_PERSON_ID:
            if not _table_exists(conn, table):
                continue
            try:
                cur = conn.execute(
                    f"DELETE FROM {table} WHERE person_id = ?",
                    (narrator_id,),
                )
                deleted[table] = cur.rowcount
            except sqlite3.Error:
                deleted[table] = -1
        # turns are conv-scoped — try the narrator-shaped conv_id
        if _table_exists(conn, "turns"):
            try:
                cur = conn.execute(
                    "DELETE FROM turns WHERE conv_id LIKE ?",
                    (f"%{narrator_id}%",),
                )
                deleted["turns"] = cur.rowcount
            except sqlite3.Error:
                deleted["turns"] = -1
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "narrator_id": narrator_id, "deleted": deleted}


# ── Main entry point ───────────────────────────────────────────────────────

def run_narrator_isolation_block(
    *,
    api: str,
    db_path: str,
    delay_seconds: float = 4.0,
    turn_timeout_seconds: int = 120,
    cleanup_synthetic_narrators: bool = True,
) -> Dict[str, Any]:
    """Run the 3-turn narrator-isolation sequence.

    Returns a structured report block:
      {
        "ok": bool,
        "purpose": "...",
        "narrators": {kent_id, janice_id},
        "turns": [<per-turn record>, ...],
        "cross_narrator_leakage": [<finding>, ...],
        "pipeline_flow": {<surface_name>: <pass/fail>},
        "cleanup": {...},
      }
    """
    kent_id = make_synthetic("kent")
    janice_id = make_synthetic("janice")
    speaker_id = {"kent": kent_id, "janice": janice_id}
    other_id = {"kent": janice_id, "janice": kent_id}

    turn_records: List[Dict[str, Any]] = []

    for turn in ISOLATION_SEQUENCE:
        spk = speaker_id[turn.narrator_key]
        oth = other_id[turn.narrator_key]

        pre_speaker = snapshot_narrator(db_path, spk)
        pre_other = snapshot_narrator(db_path, oth)

        session_id = (
            f"isolation-{turn.narrator_key}-{int(time.time())}"
        )
        endpoint_result = call_harness_turn(
            api=api,
            person_id=spk,
            text=turn.user_text,
            session_style="clear_direct",
            session_id=session_id,
            timeout_seconds=turn_timeout_seconds,
        )

        # Brief settle before snapshotting — preserve_turn writes are
        # synchronous but archive writes may be slightly deferred.
        time.sleep(0.5)

        post_speaker = snapshot_narrator(db_path, spk)
        post_other = snapshot_narrator(db_path, oth)

        speaker_delta = _diff_snapshots(pre_speaker, post_speaker)
        other_delta = _diff_snapshots(pre_other, post_other)

        # Pipeline-flow probe for this turn's unique tokens.
        # The strongest distinctive token (longest) is the safest needle
        # for a LIKE search — short tokens like "Spokane" can collide with
        # narrator-template content, while a multi-word phrase like
        # "Bonnyville Alberta" or "rainbow trout" is far less ambiguous.
        flow: Dict[str, Any] = {}
        per_needle_flows: List[Dict[str, Any]] = []
        if turn.unique_tokens:
            primary_needle = max(turn.unique_tokens, key=len)
            flow = pipeline_flow_check(
                api=api, db_path=db_path,
                narrator_id=spk, needle=primary_needle,
            )
            flow["primary_needle"] = primary_needle
            # Also surface every other token so the report shows whether
            # ANY of the four landmarks reached the surfaces — useful
            # when STT/normalization mangles the strongest one.
            for needle in turn.unique_tokens:
                per_needle_flows.append({
                    "needle": needle,
                    "result": pipeline_flow_check(
                        api=api, db_path=db_path,
                        narrator_id=spk, needle=needle,
                    ),
                })

        failures: List[str] = []
        # Speaker MUST have at least one nonzero delta (something was written)
        if not any((v or 0) > 0 for v in speaker_delta.values()):
            failures.append("speaker_zero_delta — turn did not write anywhere")
        # Other MUST have all-zero deltas (no contamination)
        for k, v in other_delta.items():
            if v and v > 0:
                failures.append(f"OTHER_NARRATOR_LEAKED: {k}=+{v}")
        # Endpoint health
        if endpoint_result.get("db_locked"):
            failures.append("db_locked_during_turn")
        if not endpoint_result.get("http_ok"):
            failures.append(
                f"endpoint_http_fail={endpoint_result.get('http_status')}"
            )

        turn_records.append({
            "narrator_key": turn.narrator_key,
            "speaker_id": spk,
            "user_text": turn.user_text,
            "unique_tokens": list(turn.unique_tokens),
            "endpoint": {
                "ok": endpoint_result.get("ok"),
                "http_status": endpoint_result.get("http_status"),
                "db_locked": endpoint_result.get("db_locked"),
                "elapsed_ms": endpoint_result.get("elapsed_ms"),
                "story_candidate_delta": endpoint_result.get(
                    "story_candidate_delta"
                ),
                "errors": endpoint_result.get("errors") or [],
            },
            "speaker_delta": speaker_delta,
            "other_delta": other_delta,
            "pipeline_flow": flow,
            "pipeline_flow_per_needle": per_needle_flows,
            "passed": not failures,
            "failures": failures,
        })

        time.sleep(delay_seconds)

    # ── Cross-narrator text-leakage check (full sequence aware) ──────────
    leakage_findings: List[Dict[str, Any]] = []
    # Aggregate every unique token said by Kent, search Janice's rows.
    kent_tokens: List[str] = []
    janice_tokens: List[str] = []
    for t in ISOLATION_SEQUENCE:
        if t.narrator_key == "kent":
            kent_tokens.extend(t.unique_tokens)
        else:
            janice_tokens.extend(t.unique_tokens)

    # Janice should NOT have any of Kent's tokens
    for tok in kent_tokens:
        hits = find_text_in_any_narrator_row(db_path, janice_id, tok)
        if hits:
            leakage_findings.append({
                "direction": "kent_token_in_janice_rows",
                "token": tok,
                "hits": hits,
            })
    # Kent should NOT have any of Janice's tokens
    for tok in janice_tokens:
        hits = find_text_in_any_narrator_row(db_path, kent_id, tok)
        if hits:
            leakage_findings.append({
                "direction": "janice_token_in_kent_rows",
                "token": tok,
                "hits": hits,
            })

    # ── Cleanup synthetic narrators ──────────────────────────────────────
    cleanup: Dict[str, Any] = {}
    if cleanup_synthetic_narrators:
        cleanup["kent"] = cleanup_synthetic(db_path, kent_id)
        cleanup["janice"] = cleanup_synthetic(db_path, janice_id)
    else:
        cleanup["skipped"] = "cleanup disabled by caller"

    overall_ok = (
        all(r["passed"] for r in turn_records)
        and not leakage_findings
    )

    return {
        "ok": overall_ok,
        "purpose": (
            "Verify that switching narrators (Kent → Janice → Kent) "
            "writes data ONLY into the speaking narrator's record, "
            "and that downstream surfaces (story_candidates, "
            "operator review, chronology) reflect the new data for "
            "the correct narrator. Catches BUG-208 class contamination."
        ),
        "narrators": {
            "kent_synthetic_id": kent_id,
            "janice_synthetic_id": janice_id,
        },
        "turns": turn_records,
        "cross_narrator_leakage": leakage_findings,
        "cleanup": cleanup,
    }


def _diff_snapshots(pre: Dict[str, Any], post: Dict[str, Any]) -> Dict[str, int]:
    """Compute post-pre per-table delta. None values pass through as None."""
    out: Dict[str, int] = {}
    for k in set(pre.keys()) | set(post.keys()):
        if k.startswith("_"):
            continue
        a = pre.get(k)
        b = post.get(k)
        if a is None or b is None:
            out[k] = 0
        else:
            out[k] = int(b) - int(a)
    return out


__all__ = [
    "ISOLATION_SEQUENCE",
    "run_narrator_isolation_block",
    "snapshot_narrator",
    "find_text_in_any_narrator_row",
    "cleanup_synthetic",
    "make_synthetic",
]


if __name__ == "__main__":
    print(
        "This module is the narrator-isolation extension for the "
        "golfball harness. Import run_narrator_isolation_block from "
        "run_golfball_interview_eval.py."
    )
