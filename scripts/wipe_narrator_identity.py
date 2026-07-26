#!/usr/bin/env python3
"""Bounded hard reset of a single narrator identity, by explicit id.

WO-TRAVEL-DOC-IMPORT-PROVENANCE-FOUNDATION-01, Phase 1.1.

═══════════════════════════════════════════════════════════════════════
  WHY THIS EXISTS
═══════════════════════════════════════════════════════════════════════

The identity pre-flight (scripts/audit_identity_preflight.py, run
2026-07-26) found two `people` rows that both read as Christopher:

    a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2  "Christopher Todd Horne"
    e7fdb578-5563-479f-8951-aab764faa6d8  "Christopher"

Same date of birth, same birthplace, one human. The operator decision
was NOT to merge and NOT to add a canonical pointer, but to delete the
newer, thinner row and keep the original -- so the import-provenance
epic starts from one identity instead of reconciling a split.

This script is that delete, and nothing else. It is deliberately NOT a
person-merge tool, NOT a duplicate-cleanup sweep, and NOT a general
narrator admin CLI. Those are all explicitly out of scope.

═══════════════════════════════════════════════════════════════════════
  WHY NOT scripts/cleanup_test_narrators.py
═══════════════════════════════════════════════════════════════════════

That script exists and does adjacent work, but it is the wrong tool
here for two reasons:

  1. It classifies by DISPLAY NAME. The whole problem is that the two
     rows share a name. Name-based selection is precisely the failure
     mode that created this mess, and requirement 4 of the operator
     order is "delete by explicit id, never by display name".
  2. Its KEEP list pins "Christopher Todd Horne" (correctly -- that is
     the row we are keeping) and its SAFE_DELETE patterns do not match
     the bare "Christopher", so the target would land in NEEDS_REVIEW
     and never be actioned.

So this script selects by id only. The display name is read and
compared, but ONLY as an abort condition -- it can stop a delete, it
can never cause one.

═══════════════════════════════════════════════════════════════════════
  WHY NOT A HAND-WRITTEN PILE OF DELETE STATEMENTS
═══════════════════════════════════════════════════════════════════════

`api.db.hard_delete_person()` already does this correctly and is
covered by tests/test_person_delete_coverage.py. It handles the case
that makes narrator deletion dangerous in this schema: fourteen
person-scoped tables have NO foreign key to people(id), so the SQLite
cascade cannot reach them and they must be deleted explicitly, in an
order that respects the NO-ACTION media-archive children. It also
writes the narrator_delete_audit row.

Reimplementing that here would mean two divergent definitions of "what
belongs to a person", which is exactly the class of bug this whole work
order is about. This script is a safety harness around the existing
function, not a replacement for it.

═══════════════════════════════════════════════════════════════════════
  USAGE
═══════════════════════════════════════════════════════════════════════

  Report only (default -- read-only, no mutations):

      python3 scripts/wipe_narrator_identity.py \\
          --person-id e7fdb578-5563-479f-8951-aab764faa6d8

  Actually delete (all four flags required):

      ./scripts/backup_before_migration.sh --tag pre_christopher_wipe
      python3 scripts/wipe_narrator_identity.py \\
          --person-id e7fdb578-5563-479f-8951-aab764faa6d8 \\
          --backup /mnt/c/hornelore_data/db/backup_pre_christopher_wipe_<stamp>.sqlite3 \\
          --commit --i-acknowledge

  Verify after the fact (read-only orphan sweep):

      python3 scripts/wipe_narrator_identity.py \\
          --person-id e7fdb578-5563-479f-8951-aab764faa6d8 --verify-only

  Run with the stack DOWN. The delete is transactional, but a
  concurrent writer holding the WAL makes the backup a moving target.

═══════════════════════════════════════════════════════════════════════
  SAFETY MODEL
═══════════════════════════════════════════════════════════════════════

  * ALLOWED_TARGETS is a frozen allowlist. Any other id is refused
    outright, so the script cannot be pointed at Kent, Janice, Melanie
    or the surviving Christopher even by typo or by copy-paste of the
    wrong uuid.
  * PROTECTED_IDS are checked to still exist, with their dependent row
    counts unchanged, AFTER the delete. A delete that damaged a
    protected narrator reports failure even though it committed.
  * --commit requires --i-acknowledge AND --backup pointing at a real
    file that passes PRAGMA integrity_check and that still contains the
    target row (which proves it was taken from this DB, before this
    delete). No backup, no delete.
  * The expected display name is asserted before deleting. A mismatch
    aborts -- if the row under that id is not the one the operator
    surveyed, something has changed and a human should look.
  * Post-delete, a full orphan sweep runs across every person-scoped
    and photo-scoped table, plus PRAGMA foreign_key_check.

Exit codes:  0 = clean   1 = refused / verification failed   2 = DB unreachable
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

# --------------------------------------------------------------------
# Frozen allowlist. Widening this is a code change, reviewed as one.
# --------------------------------------------------------------------
ALLOWED_TARGETS = {
    "e7fdb578-5563-479f-8951-aab764faa6d8": "Christopher",
}

# Narrators that must survive this operation completely untouched.
PROTECTED_IDS = {
    "a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2": "Christopher Todd Horne",
    "4aa0cc2b-1f27-433a-9152-203bb1f69a55": "Kent",
    "93479171-0b97-4072-bcf0-d44c7f9078ba": "Janice",
    "d56900b5-3dda-4f44-b419-4891e1683007": "Melanie Zollner",
}

# Every table that carries a person id, whether or not it has an FK.
# Used for the before/after inventory and the orphan sweep. Kept in
# sync with api.db._EXTENDED_PERSON_SCOPED_TABLES plus the FK-cascaded
# tables that function relies on the cascade to reach.
PERSON_SCOPED = [
    ("bio_builder_questionnaires", "person_id"),
    ("bio_facts", "narrator_id"),
    ("consent_attestations", "narrator_id"),
    ("facts", "person_id"),
    ("family_truth_notes", "person_id"),
    ("family_truth_promoted", "person_id"),
    ("family_truth_rows", "person_id"),
    ("follow_up_bank", "person_id"),
    ("graph_persons", "narrator_id"),
    ("graph_relationships", "narrator_id"),
    ("identity_change_log", "person_id"),
    ("interview_answers", "person_id"),
    ("interview_projections", "person_id"),
    ("interview_sessions", "person_id"),
    ("life_phases", "person_id"),
    ("media_archive_items", "person_id"),
    ("media_archive_people", "person_id"),
    ("memory_archive_sessions", "person_id"),
    ("memory_archive_turns", "person_id"),
    ("photo_people", "person_id"),
    ("photo_sessions", "narrator_id"),
    ("photos", "narrator_id"),
    ("profiles", "person_id"),
    ("safety_events", "person_id"),
    ("section_summaries", "person_id"),
    ("story_candidates", "narrator_id"),
    ("timeline_events", "person_id"),
    ("trip_bio_suggestions", "person_id"),
    ("trips", "person_id"),
]

# narrator_delete_audit is person-scoped but must SURVIVE the delete it
# records, so it is never counted as residue.
AUDIT_TABLE = "narrator_delete_audit"


# --------------------------------------------------------------------
# DB path resolution -- mirrors api/db.py exactly.
# --------------------------------------------------------------------
def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_dotenv_value(key: str):
    env_path = _repo_root() / ".env"
    if not env_path.exists():
        return None
    try:
        with open(env_path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == key:
                    return v.strip().strip('"').strip("'")
    except OSError:
        return None
    return None


def resolve_db_path(override: str | None) -> Path:
    if override:
        return Path(override).expanduser()
    data_dir = os.getenv("DATA_DIR") or _load_dotenv_value("DATA_DIR") or "data"
    db_name = os.getenv("DB_NAME") or _load_dotenv_value("DB_NAME") or "lorevox.sqlite3"
    return Path(data_dir).expanduser() / "db" / db_name


def _connect_ro(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _table_has_column(con, table: str, column: str) -> bool:
    row = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (table,)
    ).fetchone()
    if not row:
        return False
    return column in [r[1] for r in con.execute(f"PRAGMA table_info({table});")]


def inventory(con, person_id: str) -> dict:
    """Row counts per person-scoped table, plus photo-reachable children."""
    counts: dict[str, int] = {}
    for table, col in PERSON_SCOPED:
        if not _table_has_column(con, table, col):
            continue
        n = con.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {col}=?;", (person_id,)  # noqa: S608
        ).fetchone()[0]
        if n:
            counts[f"{table}.{col}"] = n

    # Children reachable only through this person's photos. photos has no
    # FK to people, and trip_photo_links has no FK to photos, so these do
    # not all cascade -- they are counted so the report is honest.
    photo_children = [
        ("photo_events", "photo_id"),
        ("photo_memories", "photo_id"),
        ("photo_people", "photo_id"),
        ("photo_session_shows", "photo_id"),
        ("trip_photo_links", "photo_id"),
    ]
    for table, col in photo_children:
        if not _table_has_column(con, table, col):
            continue
        n = con.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {col} IN "  # noqa: S608
            f"(SELECT id FROM photos WHERE narrator_id=?);",
            (person_id,),
        ).fetchone()[0]
        if n:
            counts[f"{table} (via photos)"] = n
    return counts


def orphan_sweep(con) -> list[str]:
    """Return a list of orphan findings. Empty list means clean."""
    findings: list[str] = []

    for table, col in PERSON_SCOPED:
        if not _table_has_column(con, table, col):
            continue
        n = con.execute(
            f"SELECT COUNT(*) FROM {table} t WHERE t.{col} IS NOT NULL "  # noqa: S608
            f"AND NOT EXISTS (SELECT 1 FROM people p WHERE p.id = t.{col});"
        ).fetchone()[0]
        if n:
            findings.append(f"{table}.{col}: {n} row(s) point at a missing person")

    if _table_has_column(con, "trip_photo_links", "photo_id"):
        n = con.execute(
            "SELECT COUNT(*) FROM trip_photo_links l WHERE NOT EXISTS "
            "(SELECT 1 FROM photos p WHERE p.id = l.photo_id);"
        ).fetchone()[0]
        if n:
            findings.append(f"trip_photo_links.photo_id: {n} link(s) point at a missing photo")

        n = con.execute(
            "SELECT COUNT(*) FROM trip_photo_links l "
            "JOIN trips t ON t.id = l.trip_id "
            "JOIN photos p ON p.id = l.photo_id "
            "WHERE p.narrator_id <> t.person_id;"
        ).fetchone()[0]
        if n:
            findings.append(f"trip_photo_links: {n} link(s) cross owner (photo owner <> trip owner)")

    for row in con.execute("PRAGMA foreign_key_check;"):
        findings.append(f"foreign_key_check: {tuple(row)}")

    return findings


def christopher_split_check(con) -> list[str]:
    """Any remaining people rows whose name normalizes to christopher."""
    rows = con.execute(
        "SELECT id, display_name, is_deleted FROM people "
        "WHERE lower(display_name) LIKE '%christopher%';"
    ).fetchall()
    return [f"{r['id']}  is_deleted={r['is_deleted']}  {r['display_name']!r}" for r in rows]


def validate_backup(backup: Path, target_id: str) -> str | None:
    """Return an error string, or None if the backup is acceptable."""
    if not backup.exists():
        return f"backup file does not exist: {backup}"
    if backup.stat().st_size < 1024:
        return f"backup file is implausibly small ({backup.stat().st_size} bytes): {backup}"
    try:
        bcon = _connect_ro(backup)
    except sqlite3.Error as exc:
        return f"backup is not a readable sqlite database: {exc}"
    try:
        res = bcon.execute("PRAGMA integrity_check;").fetchone()[0]
        if res != "ok":
            return f"backup failed integrity_check: {res}"
        row = bcon.execute("SELECT id FROM people WHERE id=?;", (target_id,)).fetchone()
        if not row:
            return (
                "backup does not contain the target person row -- it is either "
                "from a different database or was taken AFTER the delete"
            )
    finally:
        bcon.close()
    return None


def _fmt(counts: dict) -> str:
    if not counts:
        return "      (none)\n"
    width = max(len(k) for k in counts)
    return "".join("      %-*s  %d\n" % (width, k, v) for k, v in sorted(counts.items()))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--person-id", required=True, help="Full uuid. Must be on the allowlist.")
    ap.add_argument("--db", default=None, help="Override the resolved DB path.")
    ap.add_argument("--backup", default=None, help="Path to the pre-delete backup. Required with --commit.")
    ap.add_argument("--commit", action="store_true", help="Actually delete. Requires --i-acknowledge and --backup.")
    ap.add_argument("--i-acknowledge", action="store_true", help="Second confirmation flag.")
    ap.add_argument("--verify-only", action="store_true", help="Read-only post-delete verification sweep.")
    args = ap.parse_args()

    target = args.person_id
    db_path = resolve_db_path(args.db)

    print("=" * 70)
    print("  WIPE NARRATOR IDENTITY -- WO-IMPORT-PROVENANCE-FOUNDATION-01 Phase 1.1")
    print("=" * 70)
    print(f"  database : {db_path}")
    print(f"  target   : {target}")
    print(f"  mode     : {'VERIFY-ONLY' if args.verify_only else ('COMMIT' if args.commit else 'REPORT (dry run)')}")
    print()

    if target not in ALLOWED_TARGETS and not args.verify_only:
        print("REFUSED: id is not on the frozen allowlist.")
        print("         Allowed: " + ", ".join(sorted(ALLOWED_TARGETS)))
        print("         This script deletes one specific identity and nothing else.")
        return 1

    if not db_path.exists():
        print(f"DB UNREACHABLE: {db_path} does not exist.")
        return 2

    # ---------------- read-only survey ----------------
    try:
        con = _connect_ro(db_path)
    except sqlite3.Error as exc:
        print(f"DB UNREACHABLE: {exc}")
        return 2

    person = con.execute(
        "SELECT id, display_name, is_deleted, created_at FROM people WHERE id=?;", (target,)
    ).fetchone()

    if args.verify_only:
        print("--- 1. target row ---")
        print("      GONE (no people row under this id)" if not person
              else f"      STILL PRESENT: {dict(person)}")
        print()
        print("--- 2. residue under the target id ---")
        print(_fmt(inventory(con, target)))
        print("--- 3. orphan sweep ---")
        findings = orphan_sweep(con)
        print("      CLEAN -- no orphans, no crossing links, foreign_key_check empty\n"
              if not findings else "".join(f"      {f}\n" for f in findings))
        print("--- 4. remaining christopher rows ---")
        for line in christopher_split_check(con) or ["      (none)"]:
            print(f"      {line}")
        print()
        print("--- 5. protected narrators ---")
        for pid, name in sorted(PROTECTED_IDS.items(), key=lambda kv: kv[1]):
            r = con.execute("SELECT display_name FROM people WHERE id=?;", (pid,)).fetchone()
            print(f"      {'OK     ' if r else 'MISSING'} {pid}  {name}")
        con.close()
        ok = not findings and person is None
        print()
        print("=" * 70)
        print("  VERIFY: CLEAN" if ok else "  VERIFY: NOT CLEAN -- see findings above")
        print("=" * 70)
        return 0 if ok else 1

    if not person:
        print("NOTHING TO DO: no people row under that id (already deleted?).")
        con.close()
        return 0

    expected = ALLOWED_TARGETS[target]
    actual = person["display_name"]
    if actual != expected:
        print(f"REFUSED: display name mismatch. Expected {expected!r}, found {actual!r}.")
        print("         The row under this id is not the one that was surveyed.")
        print("         A human should look before anything is deleted.")
        con.close()
        return 1

    counts_before = inventory(con, target)
    total = sum(counts_before.values())

    print("--- target row ---")
    print(f"      display_name : {actual!r}")
    print(f"      created_at   : {person['created_at']}")
    print(f"      is_deleted   : {person['is_deleted']}")
    print()
    print(f"--- dependent rows that will be destroyed ({total} total) ---")
    print(_fmt(counts_before))

    print("--- protected narrators (must be untouched) ---")
    protected_before = {}
    for pid, name in sorted(PROTECTED_IDS.items(), key=lambda kv: kv[1]):
        r = con.execute("SELECT display_name FROM people WHERE id=?;", (pid,)).fetchone()
        protected_before[pid] = sum(inventory(con, pid).values())
        print(f"      {'OK     ' if r else 'MISSING'} {pid}  {name}  ({protected_before[pid]} dependent rows)")
    print()

    pre_findings = orphan_sweep(con)
    print("--- pre-delete orphan sweep ---")
    print("      CLEAN\n" if not pre_findings else "".join(f"      {f}\n" for f in pre_findings))
    con.close()

    if not args.commit:
        print("=" * 70)
        print("  DRY RUN -- nothing was written.")
        print("  To execute: take a backup, then re-run with")
        print("    --backup <path> --commit --i-acknowledge")
        print("=" * 70)
        return 0

    # ---------------- guards before any write ----------------
    if not args.i_acknowledge:
        print("REFUSED: --commit requires --i-acknowledge as a second confirmation.")
        return 1
    if not args.backup:
        print("REFUSED: --commit requires --backup pointing at a pre-delete backup.")
        print("         Take one with: ./scripts/backup_before_migration.sh --tag pre_christopher_wipe")
        return 1

    err = validate_backup(Path(args.backup).expanduser(), target)
    if err:
        print(f"REFUSED: {err}")
        return 1
    print(f"--- backup validated ---\n      {args.backup}\n      integrity_check ok, contains the target row\n")

    # ---------------- the delete, via the app's own code path ----------------
    sys.path.insert(0, str(_repo_root() / "server" / "code"))
    os.environ.setdefault("DATA_DIR", str(db_path.parent.parent))
    os.environ.setdefault("DB_NAME", db_path.name)
    try:
        from api.db import hard_delete_person  # noqa: E402
    except Exception as exc:  # pragma: no cover
        print(f"REFUSED: could not import api.db.hard_delete_person: {exc}")
        return 1

    print("--- deleting via api.db.hard_delete_person() ---")
    result = hard_delete_person(target, requested_by="wipe_narrator_identity.py/phase-1.1")
    if result is None:
        print("      hard_delete_person returned None (person vanished mid-run)")
        return 1
    if result.get("error"):
        print(f"      ROLLED BACK: {result.get('detail')}")
        return 1
    print(f"      status: {result.get('status')}  name: {result.get('display_name')!r}")
    print()

    # ---------------- post-delete verification ----------------
    con = _connect_ro(db_path)
    still = con.execute("SELECT id FROM people WHERE id=?;", (target,)).fetchone()
    residue = inventory(con, target)
    findings = orphan_sweep(con)

    print("--- post-delete verification ---")
    print(f"      people row gone            : {'YES' if not still else 'NO  <-- FAILURE'}")
    print(f"      residue under target id    : {sum(residue.values())}")
    if residue:
        print(_fmt(residue))
    print(f"      orphan sweep               : {'CLEAN' if not findings else 'FINDINGS'}")
    for f in findings:
        print(f"        {f}")

    damaged = []
    for pid, name in sorted(PROTECTED_IDS.items(), key=lambda kv: kv[1]):
        r = con.execute("SELECT display_name FROM people WHERE id=?;", (pid,)).fetchone()
        after = sum(inventory(con, pid).values())
        state = "OK"
        if not r:
            state = "MISSING <-- FAILURE"
            damaged.append(name)
        elif after != protected_before[pid]:
            state = f"CHANGED {protected_before[pid]} -> {after} <-- FAILURE"
            damaged.append(name)
        print(f"      protected {name:<24} {state}")

    print()
    print("--- remaining christopher rows ---")
    for line in christopher_split_check(con) or ["      (none)"]:
        print(f"      {line}")
    con.close()

    ok = (not still) and (not residue) and (not findings) and (not damaged)
    print()
    print("=" * 70)
    print("  PHASE 1.1: CLEAN" if ok else "  PHASE 1.1: NOT CLEAN -- restore from the backup and stop")
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
