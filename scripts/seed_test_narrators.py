#!/usr/bin/env python3
"""WO-QA-01 — Seed synthetic test narrators for the Quality Harness.

Loads rich fictional biographies from data/narrator_templates/test_*.json and
UPSERTs them into the people + profiles tables with narrator_type='test'.

The existing reference-narrator write guards treat any non-'live' narrator
as read-only to the family-truth pipeline, so 'test' narrators are
permanently quarantined from real archive data.

Re-running this script is idempotent — it overwrites the rows with the
current template content, which is what you want for reproducible runs.
Edits to the template files change the baseline; regression runs should
pin to a specific template commit.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = REPO_ROOT / "data" / "narrator_templates"
TEST_TEMPLATES = ["test_structured.json", "test_storyteller.json"]


def _resolve_db_path() -> str:
    """Mirror db.py's DB_PATH composition so this script finds the same file.

    db.py: DATA_DIR / "db" / DB_NAME   (defaults: ./data/db/lorevox.sqlite3)
    Hornelore .env overrides both:
        DATA_DIR=/mnt/c/hornelore_data
        DB_NAME=hornelore.sqlite3
    Net: /mnt/c/hornelore_data/db/hornelore.sqlite3
    """
    override = os.getenv("HORNELORE_DB_PATH")
    if override:
        return override
    data_dir = os.getenv("DATA_DIR", "data")
    db_name = os.getenv("DB_NAME", "lorevox.sqlite3").strip() or "lorevox.sqlite3"
    return str(Path(data_dir).expanduser() / "db" / db_name)


DEFAULT_DB = _resolve_db_path()


def load_template(name: str) -> Dict[str, Any]:
    path = TEMPLATE_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Template not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_db(path: str) -> Path:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"Database not found: {p}\n"
            f"(set HORNELORE_DB_PATH to override, default is {DEFAULT_DB})"
        )
    return p


def upsert_narrator(conn: sqlite3.Connection, narrator: Dict[str, Any]) -> None:
    """UPSERT into people + profiles using the live schema.

    The schema is managed by server/code/api/db.py::init_db — this script
    intentionally does NOT call CREATE TABLE. If the tables are missing,
    the API hasn't run yet; start it first.
    """
    pid = narrator["id"]
    display_name = narrator["display_name"]
    role = narrator.get("role", "narrator")
    dob = narrator.get("date_of_birth", "")
    pob = narrator.get("place_of_birth", "")
    narrator_type = narrator.get("narrator_type", "test")

    conn.execute(
        """
        INSERT INTO people (id, display_name, role, date_of_birth, place_of_birth, narrator_type)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            display_name = excluded.display_name,
            role = excluded.role,
            date_of_birth = excluded.date_of_birth,
            place_of_birth = excluded.place_of_birth,
            narrator_type = excluded.narrator_type,
            updated_at = datetime('now'),
            is_deleted = 0
        """,
        (pid, display_name, role, dob, pob, narrator_type),
    )

    profile_json = narrator.get("profile_json", {})
    conn.execute(
        """
        INSERT INTO profiles (person_id, profile_json, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(person_id) DO UPDATE SET
            profile_json = excluded.profile_json,
            updated_at = excluded.updated_at
        """,
        (pid, json.dumps(profile_json, ensure_ascii=False)),
    )


def main(argv: List[str]) -> int:
    db_path = ensure_db(DEFAULT_DB)
    conn = sqlite3.connect(str(db_path))
    try:
        seeded = 0
        for tname in TEST_TEMPLATES:
            narrator = load_template(tname)
            # Safety: enforce narrator_type='test' even if the template was edited
            narrator["narrator_type"] = "test"
            upsert_narrator(conn, narrator)
            print(
                f"  ✓ {narrator['id']:<30} {narrator['display_name']:<20} "
                f"style={(narrator.get('profile_json', {}).get('basics') or {}).get('style', '?')}"
            )
            seeded += 1
        conn.commit()
        print(f"[WO-QA-01] Seeded {seeded} synthetic test narrators into {db_path}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
