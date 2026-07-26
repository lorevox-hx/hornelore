#!/usr/bin/env python3
"""Identity pre-flight audit — WO-TRAVEL-DOC-IMPORT-PROVENANCE-FOUNDATION-01
Phase 1 (2026-07-26).

READ-ONLY. Opens the live DB with SQLite's ``mode=ro`` URI flag, runs
SELECTs only, and writes nothing anywhere. Safe to run against a live
database with the stack up or down.

WHY THIS EXISTS
---------------
Two identity columns name the same human and nothing in the schema says
they must agree:

  * ``photos.narrator_id``  -- migration 0001, NOT NULL, no FOREIGN KEY
  * ``trips.person_id``     -- migration 0034, NOT NULL, FK -> people(id)
                               ON DELETE CASCADE

The application equates them by convention. ``routers/trips.py`` line 702
reads::

    narrator_id = req.narrator_id or trip.get("person_id")

and hands that straight to ``_photos_for_narrator()``, which filters
``photos WHERE narrator_id = ?``. The same ``narrator_id=person_id``
substitution appears in chat_ws.py, people.py and trips.py. So the
whole application rests on an unstated invariant:

    one row in ``people`` == one narrator == one photo owner

There is no schema constraint behind it and no person-merge tooling in
the repo. If a narrator ends up with two ``people`` rows, photo
clustering does not error -- it returns an empty list and reports a
successful run with zero matches.

WO-TRAVEL-DOC-IMPORT-PROVENANCE-FOUNDATION-01 proposes an
``import_candidate`` table carrying BOTH ``person_id`` and ``photo_id``.
That table would inherit this fault line and start writing provenance
across it. This script measures the fault line before anything is built
on top of it.

USAGE
-----
Run from the repo root so the .env-derived paths resolve the same way
the API resolves them::

    cd /mnt/c/Users/chris/hornelore
    python3 scripts/audit_identity_preflight.py

Override the database explicitly if needed::

    python3 scripts/audit_identity_preflight.py --db /mnt/c/hornelore_data/db/hornelore.sqlite3

Exit codes:
    0  no identity split detected
    1  identity split detected (details printed)
    2  could not open the database
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

# Tables keyed by narrator_id that a person-merge would have to touch.
_NARRATOR_KEYED = (
    "photos",
    "photo_sessions",
    "bio_facts",
    "story_candidates",
)

# Tables keyed by person_id.
_PERSON_KEYED = (
    "trips",
    "profiles",
)

# Tables whose rows mean "this id has real narrator activity". profiles is
# deliberately excluded: db.py creates one profile row per person, so every
# person carries exactly one and it proves nothing about a split.
_SUBSTANTIVE = ("photos", "photo_sessions", "bio_facts",
                "story_candidates", "trips")


def _load_dotenv(repo_root: Path) -> dict:
    """Parse .env the way the API's environment would have it. Does not
    mutate os.environ."""
    values = {}
    env_path = repo_root / ".env"
    if not env_path.is_file():
        return values
    try:
        raw = env_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return values
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip().strip('"').strip("'")
    return values


def _resolve_db_path(repo_root: Path) -> Path:
    """Mirror api/db.py: DATA_DIR/db/DB_NAME, env first then .env."""
    dotenv = _load_dotenv(repo_root)
    data_dir = os.getenv("DATA_DIR") or dotenv.get("DATA_DIR") or "data"
    db_name = (os.getenv("DB_NAME") or dotenv.get("DB_NAME")
               or "lorevox.sqlite3").strip() or "lorevox.sqlite3"
    base = Path(data_dir).expanduser()
    if not base.is_absolute():
        base = (repo_root / base).resolve()
    return base / "db" / db_name


def _connect_ro(db_path: Path) -> sqlite3.Connection:
    """Open strictly read-only. mode=ro fails rather than creating a file
    and never upgrades to a writer."""
    uri = "file:%s?mode=ro" % db_path.as_posix()
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?;",
        (name,),
    ).fetchone()
    return row is not None


def _has_column(con: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        cols = con.execute("PRAGMA table_info(%s);" % table).fetchall()
    except sqlite3.Error:
        return False
    return any(str(c[1]) == column for c in cols)


def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z]+", " ", (name or "").lower()).strip()


def _looks_like_same_person(a: str, b: str) -> bool:
    """Conservative: one normalized name's token set is a subset of the
    other's, and they share a first token. Catches
    'Christopher' vs 'Christopher Todd Horne' without pairing
    'Chris Horne' with 'Pat Horne'."""
    ta, tb = _norm_name(a).split(), _norm_name(b).split()
    if not ta or not tb:
        return False
    if ta[0] != tb[0]:
        return False
    sa, sb = set(ta), set(tb)
    return sa <= sb or sb <= sa


def _rule(title: str) -> None:
    print("")
    print("-" * 68)
    print(title)
    print("-" * 68)


def main(argv=None) -> int:
    repo_root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=None, help="explicit path to the sqlite file")
    args = ap.parse_args(argv)

    db_path = Path(args.db).expanduser() if args.db else _resolve_db_path(repo_root)

    print("=" * 68)
    print("IDENTITY PRE-FLIGHT AUDIT (read-only)")
    print("=" * 68)
    print("repo root : %s" % repo_root)
    print("database  : %s" % db_path)

    if not db_path.is_file():
        print("")
        print("FAIL: no such database file.")
        print("      Set DATA_DIR / DB_NAME in .env, or pass --db explicitly.")
        return 2

    try:
        con = _connect_ro(db_path)
    except sqlite3.Error as exc:
        print("")
        print("FAIL: could not open read-only: %s" % exc)
        return 2

    findings = []

    try:
        # ---------------------------------------------------------- people
        _rule("1. people")
        if not _table_exists(con, "people"):
            print("  people table missing -- nothing to audit.")
            return 2
        people = con.execute(
            "SELECT id, display_name, role, date_of_birth, created_at "
            "FROM people ORDER BY created_at;"
        ).fetchall()
        print("  %d row(s)" % len(people))
        for r in people:
            print("    %-38s  %-28s  role=%-10s dob=%-12s %s" % (
                r["id"], (r["display_name"] or "")[:28],
                (r["role"] or "")[:10], (r["date_of_birth"] or "")[:12],
                r["created_at"]))

        # ---------------------------------------- ownership counts per id
        # Built before the duplicate report so each cluster member can be
        # shown with the rows it actually owns. A split only matters when
        # more than one member of a cluster holds data.
        known_ids = {r["id"] for r in people}
        owned = defaultdict(dict)   # person_id -> {table: count}
        keyed = ([(t, "narrator_id") for t in _NARRATOR_KEYED]
                 + [(t, "person_id") for t in _PERSON_KEYED])
        for table, col in keyed:
            if not _table_exists(con, table) or not _has_column(con, table, col):
                continue
            where = " WHERE deleted_at IS NULL" if _has_column(
                con, table, "deleted_at") else ""
            for r in con.execute(
                "SELECT %s AS owner, COUNT(*) AS n FROM %s%s GROUP BY %s;"
                % (col, table, where, col)
            ).fetchall():
                owned[r["owner"]][table] = r["n"]

        def _load(pid):
            d = owned.get(pid, {})
            if not d:
                return "no rows"
            return ", ".join("%s=%d" % (k, v) for k, v in sorted(d.items()))

        def _is_active(pid):
            """True when this id owns rows in a table that implies real
            narrator activity (profiles alone does not count)."""
            d = owned.get(pid, {})
            return any(d.get(t) for t in _SUBSTANTIVE)

        # ----------------------------------------- duplicate name clusters
        _rule("2. possible duplicate people (name clusters)")
        clusters, seen = [], set()
        for i, a in enumerate(people):
            if a["id"] in seen:
                continue
            group = [a]
            seen.add(a["id"])
            for b in people[i + 1:]:
                if b["id"] in seen:
                    continue
                if _looks_like_same_person(a["display_name"], b["display_name"]):
                    group.append(b)
                    seen.add(b["id"])
            if len(group) > 1:
                clusters.append(group)

        if not clusters:
            print("  none detected")
        else:
            # A cluster is only load-bearing when >1 member has real
            # narrator activity. profiles-only members do not count.
            loaded = [g for g in clusters
                      if sum(1 for m in g if _is_active(m["id"])) > 1]
            print("  %d name cluster(s) with more than one id; %d of them carry "
                  "narrator activity on more than one id"
                  % (len(clusters), len(loaded)))
            for g in clusters:
                active = sum(1 for m in g if _is_active(m["id"]))
                mark = "  <-- SPLIT CARRIES DATA" if active > 1 else ""
                print("")
                print("    cluster %r  (%d ids, %d active)%s"
                      % (g[0]["display_name"], len(g), active, mark))
                for m in g:
                    flag = " *" if _is_active(m["id"]) else "  "
                    print("      %s %-38s %s" % (flag, m["id"], _load(m["id"])))
            if loaded:
                findings.append(
                    "%d duplicate-name cluster(s) carry narrator activity on "
                    "more than one id" % len(loaded))
            else:
                print("")
                print("    No cluster carries narrator activity on more than")
                print("    one id, so no live split is implied -- these are")
                print("    most likely placeholder or test names.")
                print("    (profiles rows are excluded: db.py creates one per")
                print("     person, so they prove nothing about a split.)")

        # --------------------------------------------- ownership by table
        _rule("3. row ownership per table")
        for table, col in keyed:
            if not _table_exists(con, table) or not _has_column(con, table, col):
                print("  %-18s (absent)" % table)
                continue
            where = ""
            if _has_column(con, table, "deleted_at"):
                where = " WHERE deleted_at IS NULL"
            rows = con.execute(
                "SELECT %s AS owner, COUNT(*) AS n FROM %s%s GROUP BY %s "
                "ORDER BY n DESC;" % (col, table, where, col)
            ).fetchall()
            if not rows:
                print("  %-18s (empty)" % table)
                continue
            print("  %-18s keyed by %s" % (table, col))
            for r in rows:
                owner = r["owner"]
                orphan = "" if owner in known_ids else "   <-- NO people ROW"
                print("      %-38s %6d%s" % (owner, r["n"], orphan))
                if orphan:
                    findings.append("%s has %d row(s) owned by unknown id %s"
                                    % (table, r["n"], owner))

        # ------------------------------------- the cross-owner link check
        _rule("4. trip_photo_links pointing across owners  (THE ONE THAT MATTERS)")
        if not (_table_exists(con, "trip_photo_links")
                and _table_exists(con, "photos")
                and _table_exists(con, "trips")):
            print("  required tables absent -- skipped")
        else:
            missing = con.execute(
                "SELECT COUNT(*) AS n FROM trip_photo_links l "
                "LEFT JOIN photos p ON p.id = l.photo_id "
                "WHERE p.id IS NULL;"
            ).fetchone()["n"]
            print("  links whose photo_id has no photos row : %d" % missing)
            if missing:
                findings.append("%d trip_photo_link(s) point at a missing photo"
                                % missing)

            crossed = con.execute(
                "SELECT l.id AS link_id, l.trip_id, t.person_id, "
                "       l.photo_id, p.narrator_id "
                "FROM trip_photo_links l "
                "JOIN trips  t ON t.id = l.trip_id "
                "JOIN photos p ON p.id = l.photo_id "
                "WHERE p.narrator_id <> t.person_id;"
            ).fetchall()
            print("  links where photo.narrator_id <> trip.person_id : %d"
                  % len(crossed))
            for r in crossed[:20]:
                print("      link=%s trip=%s" % (r["link_id"], r["trip_id"]))
                print("          trip.person_id     = %s" % r["person_id"])
                print("          photo.narrator_id  = %s" % r["narrator_id"])
            if len(crossed) > 20:
                print("      ... and %d more" % (len(crossed) - 20))
            if crossed:
                findings.append("%d trip_photo_link(s) cross the person/narrator "
                                "boundary" % len(crossed))

        # ------------------------------- what clustering would see per trip
        _rule("5. what photo clustering would see, per trip")
        if not (_table_exists(con, "trips") and _table_exists(con, "photos")):
            print("  required tables absent -- skipped")
        else:
            trips = con.execute(
                "SELECT id, person_id, title, start_date, end_date "
                "FROM trips ORDER BY created_at;"
            ).fetchall()
            print("  %d trip(s)" % len(trips))
            blind = 0
            for t in trips:
                n = con.execute(
                    "SELECT COUNT(*) AS n FROM photos "
                    "WHERE narrator_id = ? AND deleted_at IS NULL;",
                    (t["person_id"],),
                ).fetchone()["n"]
                if n == 0:
                    blind += 1
                    print("      ZERO PHOTOS VISIBLE  trip=%s  person_id=%s  %s"
                          % (t["id"], t["person_id"], (t["title"] or "")[:34]))
            print("  trips whose owner has zero visible photos: %d of %d"
                  % (blind, len(trips)))
            if blind and len(people) > 1:
                findings.append("%d trip(s) would cluster against an empty photo "
                                "set" % blind)

        # ------------------------------------------------------- verdict
        _rule("VERDICT")
        if not findings:
            print("  CLEAN -- no identity split detected.")
            print("  The person_id == narrator_id invariant holds in this DB.")
            return 0
        print("  IDENTITY SPLIT DETECTED")
        for f in findings:
            print("    * %s" % f)
        print("")
        print("  Nothing was modified. This audit is read-only.")
        return 1
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
