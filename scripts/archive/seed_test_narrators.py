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


def _load_env() -> None:
    """Load repo .env so DATA_DIR / DB_NAME resolve the same way the API does.

    Without this, running the seed script from a bare shell would fall back
    to ./data/db/ (relative to cwd) instead of /mnt/c/hornelore_data/db/.
    Mirrors the dotenv-or-manual-parse pattern in server/code/api/main.py.
    """
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(str(env_file), override=False)  # shell env takes precedence
    except ImportError:
        with env_file.open() as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())


_load_env()


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


def ensure_narrator_type_column(conn: sqlite3.Connection) -> None:
    """Defensively add narrator_type if the local DB predates WO-13 Phase 3.

    Normal Hornelore init_db() adds this column, but if the user's DB was
    seeded from an older snapshot or ran a partial migration, this script
    would fail at INSERT with 'has no column named narrator_type'. Safe,
    idempotent ALTER covers both cases.
    """
    cols = [r[1] for r in conn.execute("PRAGMA table_info(people)")]
    if "narrator_type" in cols:
        return
    conn.execute("ALTER TABLE people ADD COLUMN narrator_type TEXT DEFAULT 'live'")
    conn.commit()
    print("  [migrate] added missing people.narrator_type column")


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

    # Provide created_at / updated_at / is_deleted explicitly — the live schema
    # marks created_at NOT NULL without a SQL-level default, so the UPSERT
    # must supply them on the INSERT side. On conflict, updated_at is bumped
    # but created_at is preserved (first-insert wins).
    conn.execute(
        """
        INSERT INTO people (
            id, display_name, role, date_of_birth, place_of_birth,
            narrator_type, created_at, updated_at, is_deleted
        )
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), 0)
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
    print(f"[WO-QA-01] DB path: {db_path}")
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_narrator_type_column(conn)
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
