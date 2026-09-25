#!/usr/bin/env python3
"""Mutation gate for Batch C-4D — the migration runner's atomicity / foreign-key
protocol and migration 0065's table rebuild.

Each mutation breaks one promise IN PLACE (tests/mutation_runner.py: restore
after every mutation, verified byte-identical at exit) and runs

    tests.test_migrations_runner  tests.test_migration_0065_activity_event

A mutation that leaves both green names an inert check. A missing anchor is
NOT APPLIED, never counted as caught.

0065 is edited in place here only because no persistent database may have
applied it yet (the stack stays down during C-4D). Once it is committed and
applied anywhere it is immutable, and its mutations must move to a copy.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python tests/mutate_migrations_c4d.py [label-substring ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tests.mutation_runner import MutationRunner  # noqa: E402

SOURCES = {
    "runner": REPO / "server" / "code" / "db" / "migrations_runner.py",
    "m0065": REPO / "server" / "code" / "db" / "migrations" / "0065_life_record_activity_event.sql",
    "hygiene": REPO / "tests" / "test_db_connection_hygiene.py",
}
# The hygiene-isolation repair (found while proving C-4D's trips preservation)
# is judged by its own regression AND the trips suite on the far side of it.
HYGIENE_SUITES = ["tests.test_db_hygiene_isolation", "tests.test_c1_trips_person_id_fk_migration",
                  "tests.test_db_connection_hygiene"]
SUITES = ["tests.test_migrations_runner", "tests.test_migration_0065_activity_event"]

MUTATIONS = [
    # ── the runner ──
    ("R1 runner opens no transaction for a runner-managed file", "runner",
     'con.executescript("BEGIN IMMEDIATE;\\n" + sql)', "con.executescript(sql)"),
    ("R2 body committed before its tracking row", "runner",
     '        con.execute("INSERT INTO schema_migrations(filename) VALUES (?);", (path.name,))\n'
     '        con.commit()                                      # body + tracking row: one commit',
     '        con.commit()\n'
     '        con.execute("INSERT INTO schema_migrations(filename) VALUES (?);", (path.name,))\n'
     '        con.commit()'),
    ("R3 a failed file's transaction is never rolled back", "runner",
     "    if con.in_transaction:\n        con.rollback()", "    pass"),
    ("R4 foreign keys not restored after a file", "runner",
     "            con.execute(f\"PRAGMA foreign_keys={'ON' if fk_before else 'OFF'};\")",
     "            pass"),
    ("R5 the foreign_keys=off directive is ignored", "runner",
     '    if fk_off:\n        con.execute("PRAGMA foreign_keys=OFF;")', "    if False:\n        pass"),
    ("R6 new foreign-key violations are not refused", "runner",
     "            if created:", "            if False:"),
    ("R7 an OLD violation elsewhere blocks the migration", "runner",
     "            created = _fk_violations(con) - before", "            created = _fk_violations(con)"),
    ("R8 own-transaction files are no longer recognised", "runner",
     "    return bool(_SELF_MANAGED_RX.search(sql))", "    return False"),
    # ── migration 0065 ──
    ("M1 activity missing from the rebuilt CHECK", "m0065",
     "'education', 'work', 'service', 'activity', 'arrival',", "'education', 'work', 'service', 'arrival',"),
    ("M2 a column's data is not copied", "m0065",
     "    SELECT id, narrator_id, type, place_id, attributes_json, created_at, updated_at FROM lr_events;",
     "    SELECT id, narrator_id, type, place_id, NULL, created_at, updated_at FROM lr_events;"),
    ("M3 the narrator index is not recreated", "m0065",
     "CREATE INDEX IF NOT EXISTS idx_lr_events_narrator ON lr_events(narrator_id);", ""),
    ("M4 the place foreign key is dropped", "m0065",
     "    place_id            TEXT REFERENCES lr_places(id),", "    place_id            TEXT,"),
    ("M5 the narrator cascade is dropped", "m0065",
     "    narrator_id         TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,",
     "    narrator_id         TEXT NOT NULL REFERENCES people(id),"),
    ("M6 the foreign_keys=off directive is removed", "m0065",
     "-- migration: foreign_keys=off\n", "-- (no directive)\n"),
    ("M7 the copy silently drops a type's rows", "m0065",
     "created_at, updated_at FROM lr_events;", "created_at, updated_at FROM lr_events WHERE type <> 'service';"),
    ("M8 a bogus type is admitted too", "m0065",
     "'loss', 'milestone', 'other')),", "'loss', 'milestone', 'other', 'hobby')),"),
    # ── test isolation: the hygiene suite must not replace the shared api.db ──
    ("H1 the original api.db modules are not put back", "hygiene",
     "    sys.modules.update(_saved_modules)\n", "    pass\n"),
    ("H2 the api package's db attribute is not restored", "hygiene",
     '            setattr(_pkg, "db", _attr)', "            pass"),
    ("H3 DATA_DIR is left pointing at the temp directory", "hygiene",
     '        os.environ["DATA_DIR"] = _saved_data_dir', "        pass"),
]


def main(labels):
    chosen = [m for m in MUTATIONS if not labels or any(l in m[0] for l in labels)]
    with MutationRunner(SOURCES) as mr:
        for label, key, old, new in chosen:
            v = mr.check(label, key, old, new, HYGIENE_SUITES if key == "hygiene" else SUITES, timeout=400)
            print(f"  {v:<14} {label}", flush=True)
        ok = mr.report()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
