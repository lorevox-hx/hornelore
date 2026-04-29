"""DB inspector — operator/dev tool for sqlite table introspection.

Default-OFF behind `HORNELORE_DB_INSPECTOR=1` env flag. When disabled
(default), every endpoint returns 404 so external probes can't enumerate
the schema. Per 2026-04-29 review: this is needed because the inspector
exposes everything (profiles, turns, family_truth, segment_flags,
safety_events, identity_change_log, etc.) and a generic table dump
defeats the privacy boundary that safety_events.py carefully builds.

Additional protections enabled by default even when the flag is on:
  - `limit` capped at 200 (was unbounded)
  - rows returned as dicts (was raw tuples)
  - sensitive columns redacted unless `LV_DEV_MODE=1` is also set
  - `db_path` only exposed under `LV_DEV_MODE=1`

For local debugging only. Do NOT promote to Lorevox without proper
operator-tab auth.
"""
from fastapi import APIRouter, HTTPException, Query
import sqlite3
import os
from pathlib import Path
from typing import Any, Dict

router = APIRouter(tags=["db"])

# Columns that may contain narrator-sensitive content. Redacted to
# "[redacted N chars]" unless LV_DEV_MODE is on. Operator can still
# inspect via sqlite CLI; the web endpoint should not casually dump
# these.
_REDACT_COLUMNS = {
    "content",
    "body",
    "profile_json",
    "questionnaire_json",
    "projection_json",
    "source_says",
    "approved_value",
    "value",
    "turn_excerpt",
    "matched_phrase",
    "user_message",
    "assistant_message",
    "narrative",
    "answer",
    "raw_answer",
    "transcript",
}


def _db_path() -> str:
    # Match your existing pattern: DATA_DIR + /db/lorevox.sqlite3 (or DB_NAME)
    data_dir = Path(os.getenv("DATA_DIR", "data")).expanduser()
    db_name = os.getenv("DB_NAME", "lorevox.sqlite3")
    return str(data_dir / "db" / db_name)


def _db_inspector_enabled() -> bool:
    """Backend gate: every endpoint is 404 unless this env flag is on.
    Default-OFF so the route doesn't advertise itself; operator opts
    in by setting `HORNELORE_DB_INSPECTOR=1` in .env when actively
    debugging."""
    return os.getenv("HORNELORE_DB_INSPECTOR", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _require_db_inspector_enabled() -> None:
    """Raise 404 (not 403) when the backend gate is off so an external
    probe can't distinguish 'endpoint exists but you can't have it'
    from 'endpoint doesn't exist'."""
    if not _db_inspector_enabled():
        raise HTTPException(status_code=404, detail="Not found")


def _dev_mode_enabled() -> bool:
    return os.getenv("LV_DEV_MODE", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _safe_table_name(table_name: str) -> str:
    name = str(table_name or "").strip()
    if not name.replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid table name")
    return name


def _connect(dbp: str) -> sqlite3.Connection:
    conn = sqlite3.connect(dbp)
    conn.row_factory = sqlite3.Row
    return conn


def _maybe_redact(row: Dict[str, Any]) -> Dict[str, Any]:
    """Redact sensitive columns unless LV_DEV_MODE is on. Replaces the
    value with a placeholder showing length so the operator can see
    that a value exists without leaking the content itself."""
    if _dev_mode_enabled():
        return dict(row)
    out = dict(row)
    for k in list(out.keys()):
        if k in _REDACT_COLUMNS:
            val = out.get(k)
            if val:
                out[k] = f"[redacted {len(str(val))} chars]"
    return out


@router.get("/db/tables")
def list_tables():
    _require_db_inspector_enabled()
    dbp = _db_path()
    if not Path(dbp).exists():
        raise HTTPException(status_code=404, detail="DB not found")

    conn = _connect(dbp)
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
        payload: Dict[str, Any] = {"tables": [r[0] for r in cur.fetchall()]}
        if _dev_mode_enabled():
            payload["db_path"] = dbp
        return payload
    finally:
        conn.close()


@router.get("/db/table/{table_name}")
def preview_table(
    table_name: str,
    limit: int = Query(50, ge=1, le=200, description="Max rows (1-200, default 50)"),
):
    _require_db_inspector_enabled()
    dbp = _db_path()
    if not Path(dbp).exists():
        raise HTTPException(status_code=404, detail="DB not found")

    table = _safe_table_name(table_name)
    limit = max(1, min(int(limit or 50), 200))

    conn = _connect(dbp)
    try:
        # Confirm table exists before querying so we return 404 instead
        # of 500 on a missing table.
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1;",
            (table,),
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Table not found")

        rows = conn.execute(f'SELECT * FROM "{table}" LIMIT ?;', (limit,)).fetchall()
        items = [_maybe_redact(dict(r)) for r in rows]

        payload: Dict[str, Any] = {
            "table": table,
            "limit": limit,
            "count": len(items),
            "rows": items,
        }
        if _dev_mode_enabled():
            payload["db_path"] = dbp
        return payload
    except sqlite3.OperationalError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()
