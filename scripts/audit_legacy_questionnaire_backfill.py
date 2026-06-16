#!/usr/bin/env python3
"""WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01 Phase 7.5 — read-only
audit for the legacy backfill readiness report.

Inventories per-narrator:
  - bio_facts row counts by status
  - whether `bio_builder_questionnaires` blob exists + has content
  - whether `profiles.profile_json` is populated
  - overlap: which legacy blob field_keys also have bio_facts rows

Output: prints a Markdown table the human-judgment sections of the
report (recommendations, risk classification) can be hand-edited
against.

USAGE:
    cd /mnt/c/Users/chris/hornelore
    python3 scripts/audit_legacy_questionnaire_backfill.py \\
        --db /path/to/lorevox.sqlite3 \\
        --output docs/reports/WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01_BACKFILL_READINESS_data.md

The full readiness report
(`docs/reports/WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01_BACKFILL_READINESS.md`)
combines this script's output with manual decisions on the status
matrix, normalization adapter, and recommended backfill approach.

LAW 3 read-only: this script opens the sqlite file in read-only URI
mode (`?mode=ro`) and runs only SELECT statements. It does not import
extract.py / chat_ws.py / prompt_composer.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


def _ro_connect(db_path: str) -> sqlite3.Connection:
    """Open a read-only connection. Refuses to open in r/w mode."""
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _list_narrators(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, display_name, role, narrator_type, created_at "
        "FROM people ORDER BY created_at ASC",
    ).fetchall()
    return [dict(r) for r in rows]


def _bio_facts_summary(
    conn: sqlite3.Connection, narrator_id: str,
) -> Dict[str, Any]:
    try:
        rows = conn.execute(
            "SELECT field_key, status FROM bio_facts WHERE narrator_id = ?",
            (narrator_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        # bio_facts table not present yet (very old DB)
        return {"total": 0, "by_status": {}, "field_keys": set()}
    by_status: Counter = Counter()
    field_keys: set = set()
    for r in rows:
        by_status[str(r["status"])] += 1
        field_keys.add(str(r["field_key"]))
    return {
        "total": len(rows),
        "by_status": dict(by_status),
        "field_keys": field_keys,
    }


def _legacy_blob(
    conn: sqlite3.Connection, narrator_id: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        row = conn.execute(
            "SELECT questionnaire_json, updated_at "
            "FROM bio_builder_questionnaires WHERE person_id = ?",
            (narrator_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None, None
    if not row:
        return None, None
    try:
        blob = json.loads(row["questionnaire_json"] or "{}")
    except (ValueError, TypeError):
        return None, str(row["updated_at"] or "")
    return blob, str(row["updated_at"] or "")


def _profile_json(
    conn: sqlite3.Connection, narrator_id: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        row = conn.execute(
            "SELECT profile_json, updated_at FROM profiles "
            "WHERE person_id = ?",
            (narrator_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None, None
    if not row:
        return None, None
    try:
        return json.loads(row["profile_json"] or "{}"), str(row["updated_at"] or "")
    except (ValueError, TypeError):
        return None, str(row["updated_at"] or "")


# Coarse field-key mapping: legacy blob slot → bio_schema field_key.
# Only covers the scalar slots that have a clean 1:1 mapping. Array
# sections (parents/siblings/etc.) are flagged for the normalization
# adapter section of the report.
_LEGACY_TO_FIELD_KEY: Dict[str, str] = {
    "personal.fullName":      "full_legal_name",
    "personal.preferredName": "preferred_name",
    "personal.dateOfBirth":   "birth_date",
    "personal.placeOfBirth":  "birth_place",
    "personal.birthOrder":    "birth_order",
}


def _flatten_blob(blob: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if not isinstance(blob, dict):
        return out
    for k, v in blob.items():
        full = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten_blob(v, full))
        elif isinstance(v, list):
            # Just count populated entries; report flags array shape diff
            out[full] = f"[array len={len(v)}]"
        else:
            out[full] = v
    return out


def _classify_risk(
    legacy_blob: Optional[Dict[str, Any]],
    profile_json: Optional[Dict[str, Any]],
    bio_facts: Dict[str, Any],
) -> str:
    """Coarse per-narrator classification:
      clean    — no legacy blob OR blob is a strict subset of bio_facts
      conflict — legacy blob has a scalar value that disagrees with bio_facts
      orphaned — legacy blob has data with no bio_schema field
      skip     — narrator has no content anywhere (never used)
    """
    has_blob = bool(legacy_blob)
    has_profile = bool(profile_json)
    has_bio_facts = bio_facts.get("total", 0) > 0
    if not has_blob and not has_profile and not has_bio_facts:
        return "skip"
    if not has_blob:
        return "clean"
    # When legacy blob exists, look for conflicts via the coarse map.
    flat = _flatten_blob(legacy_blob)
    for legacy_key, _field_key in _LEGACY_TO_FIELD_KEY.items():
        v = flat.get(legacy_key)
        if v and str(v).strip() and not str(v).startswith("[array"):
            # If bio_facts has the same field_key but a different value,
            # we'd need the actual value to check — without it here, flag
            # as "potential conflict" when both exist.
            if _field_key in bio_facts.get("field_keys", set()):
                return "conflict"
    # If the blob has content that doesn't map to any field_key, it's
    # orphaned. Look for unrecognized blob keys.
    legacy_keys = set(flat.keys())
    mapped_keys = set(_LEGACY_TO_FIELD_KEY.keys())
    # Anything not in mapped_keys and not in the array sections is
    # potentially orphaned. Skip array placeholders.
    plain_scalars = {
        k for k, v in flat.items()
        if not str(v).startswith("[array")
    }
    orphaned_scalars = plain_scalars - mapped_keys
    # Sections we treat as known but currently un-mapped: parents/
    # siblings/spouses/children. Drop those prefixes.
    orphaned_scalars = {
        k for k in orphaned_scalars
        if not any(k.startswith(pfx + ".") for pfx in (
            "parents", "siblings", "spouses", "spouse",
            "children", "education", "military", "faith", "today",
            "grandparents", "personal",
        ))
    }
    if orphaned_scalars:
        return "orphaned"
    return "clean"


def _per_narrator_row(
    conn: sqlite3.Connection, narrator: Dict[str, Any],
) -> Dict[str, Any]:
    pid = str(narrator.get("id"))
    bf = _bio_facts_summary(conn, pid)
    blob, blob_ts = _legacy_blob(conn, pid)
    prof, prof_ts = _profile_json(conn, pid)
    risk = _classify_risk(blob, prof, bf)
    return {
        "narrator_id":      pid,
        "display_name":     narrator.get("display_name") or "",
        "narrator_type":    narrator.get("narrator_type") or "",
        "created_at":       narrator.get("created_at") or "",
        "bio_facts_total":  bf.get("total", 0),
        "bio_facts_status": bf.get("by_status", {}),
        "legacy_blob":      bool(blob),
        "legacy_ts":        blob_ts or "",
        "profile_json":     bool(prof and prof != {}),
        "profile_ts":       prof_ts or "",
        "risk":             risk,
    }


def _render_markdown(rows: List[Dict[str, Any]]) -> str:
    counts: Counter = Counter()
    out: List[str] = []
    out.append(
        "# Phase 7.5 — Legacy backfill readiness data\n\n"
        f"Run at: {datetime.utcnow().isoformat()}Z  \n"
        f"Total narrators: {len(rows)}\n\n"
    )
    # Per-narrator table
    out.append(
        "## Per-narrator inventory\n\n"
        "| narrator_id | display_name | bio_facts | "
        "legacy_blob | profile_json | risk |\n"
        "|---|---|---|---|---|---|\n"
    )
    for r in rows:
        counts[r["risk"]] += 1
        out.append(
            "| `{nid}` | {name} | {bf} (statuses: {st}) | {blob} | {prof} | {risk} |\n".format(
                nid=str(r["narrator_id"])[:8],
                name=(r["display_name"] or "").replace("|", "\\|")[:30],
                bf=r["bio_facts_total"],
                st=json.dumps(r["bio_facts_status"]),
                blob="yes" if r["legacy_blob"] else "no",
                prof="yes" if r["profile_json"] else "no",
                risk=r["risk"],
            )
        )
    out.append("\n## Risk distribution\n\n")
    for k, v in sorted(counts.items()):
        out.append(f"- **{k}**: {v}\n")
    return "".join(out)


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True, help="Path to lorevox.sqlite3")
    ap.add_argument(
        "--output", default=None,
        help="Optional output path (markdown). Defaults to stdout.",
    )
    args = ap.parse_args(argv)
    if not os.path.exists(args.db):
        print(f"ERROR: db file not found: {args.db}", file=sys.stderr)
        return 2
    conn = _ro_connect(args.db)
    try:
        narrators = _list_narrators(conn)
        rows = [_per_narrator_row(conn, n) for n in narrators]
    finally:
        conn.close()
    md = _render_markdown(rows)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
