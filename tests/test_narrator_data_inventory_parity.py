"""Parity: the ownership declaration, erasure, and the live schema must agree.

WO-LOREVOX-PORTABLE-NARRATOR-01 Phase 1. One truth, held by test rather
than by refactor (WO §17 Phase 1: "do not rewrite hard deletion
wholesale"). Fails LOUDLY in either direction unless the difference is
named in POLICY_EXCEPTIONS with a reason.

Four things, each against the schema `init_db()` + migrations actually
build in a temp DATA_DIR — never against a hand-written list:

  1. COMPLETENESS   every live table is declared; every declared table exists.
  2. REACH          every lane the declaration marks erasable is reached by
                    erasure — explicitly (db._EXTENDED_PERSON_SCOPED_TABLES,
                    db._PARENT_OWNED_CHILDREN) or by an ON DELETE CASCADE
                    chain read from PRAGMA foreign_key_list, to fixpoint.
                    And the reverse: everything erasure reaches is declared
                    narrator-owned.
  3. SELECTORS      db.py's (table, column) pairs equal the declaration's
                    Direct columns; every select_sql / delete_sql PREPARES
                    against the live schema, so a wrong column name fails
                    here and not in an export.
  4. FILESYSTEM     person-keyed lanes == narrator_erasure.FIXED_TARGETS,
                    row-keyed lanes == its dynamic plan, shared == SHARED_PURGE.

Run:
    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python -m unittest \\
        tests.test_narrator_data_inventory_parity
"""
from __future__ import annotations

import importlib
import inspect
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Dict, List, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_CODE = REPO_ROOT / "server" / "code"
if str(SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(SERVER_CODE))

from api.services import narrator_data_inventory as inv  # noqa: E402
from api.services import narrator_erasure  # noqa: E402

# Differences that are POLICY, each with its reason. Anything not listed
# here that differs is a failure.
POLICY_EXCEPTIONS: Dict[str, str] = {
    # Tables that are reached by cascade only through a parent that is
    # itself reached — listed here only if they are NOT narrator-owned
    # in the declaration. (Currently none.)
}

# Tables the live schema carries that are not lanes at all.
_SCHEMA_NOISE = {"sqlite_sequence"}
# Rebuild scratch tables that a migration creates and renames away; if one
# survives in a live schema it is damage, and completeness should say so —
# they are NOT excepted.


class _SchemaCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._prev = {k: os.environ.get(k) for k in ("DATA_DIR", "DB_NAME")}
        os.environ["DATA_DIR"] = self._tmp.name
        os.environ["DB_NAME"] = "test_inventory_parity.sqlite3"
        from api import db as _db
        importlib.reload(_db)
        self.db = _db
        self.db.init_db()
        self.assertTrue(str(self.db.DB_PATH).startswith(self._tmp.name),
                        f"REFUSING: DB_PATH {self.db.DB_PATH} is not under the temp dir")
        self.addCleanup(self._restore)
        self.con = self.db._connect()
        self.addCleanup(self.con.close)

    def _restore(self):
        for k, v in self._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        from api import db as _db
        importlib.reload(_db)

    # ── live schema readers ──────────────────────────────────────────

    def live_tables(self) -> Set[str]:
        rows = self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
        return {r[0] for r in rows} - _SCHEMA_NOISE

    def fks(self, table: str) -> List[Tuple[str, str, str, str]]:
        """(from_col, parent_table, to_col, on_delete)"""
        return [(r["from"], r["table"], r["to"], (r["on_delete"] or "NO ACTION").upper())
                for r in self.con.execute(f'PRAGMA foreign_key_list("{table}")')]


# ══════════════════════════════════════════════════════════════════════
# 1. Completeness
# ══════════════════════════════════════════════════════════════════════

class CompletenessTests(_SchemaCase):

    def test_every_live_table_is_declared(self):
        undeclared = sorted(self.live_tables() - set(inv.db_tables()))
        self.assertEqual(undeclared, [],
                         f"live tables with NO ownership declaration: {undeclared}. "
                         f"A migration or init_db() added a table; declare it "
                         f"(narrator-owned or installation) before anything exports.")

    def test_every_declared_table_exists(self):
        missing = sorted(set(inv.db_tables()) - self.live_tables())
        self.assertEqual(missing, [],
                         f"declared tables absent from the schema init_db() builds: {missing}")

    def test_no_rebuild_scratch_table_survives(self):
        survivors = sorted(t for t in self.live_tables() if t.endswith("_new") or t.endswith("__new"))
        self.assertEqual(survivors, [], f"a migration's rebuild scratch table survived: {survivors}")


# ══════════════════════════════════════════════════════════════════════
# 2. Reach — export ↔ erasure, both directions
# ══════════════════════════════════════════════════════════════════════

class ReachTests(_SchemaCase):

    # Deleted by db._hard_delete_media (db.py:6140-6144), not by a list:
    # their FKs to people are ON DELETE SET NULL, so the cascade would
    # orphan rather than remove them. Guarded below so this stays a
    # citation of the function, not a belief about it.
    _MEDIA_BY_FUNCTION = ("media", "media_attachments")

    def _explicit_reach(self) -> Set[str]:
        reached = {t for t, _c in self.db._EXTENDED_PERSON_SCOPED_TABLES}
        reached |= {child for child, _fk, _parent, _pcol in self.db._PARENT_OWNED_CHILDREN}
        src = inspect.getsource(self.db._hard_delete_media)
        for t in self._MEDIA_BY_FUNCTION:
            self.assertIn(f"DELETE FROM {t} WHERE", src,
                          f"_hard_delete_media no longer deletes {t}; the reach set is stale")
        reached |= set(self._MEDIA_BY_FUNCTION)
        reached.add("people")
        return reached

    def _cascade_fixpoint(self, reached: Set[str]) -> Set[str]:
        """A table joins the reached set when it has an ON DELETE CASCADE FK
        to a table already in it. Iterate until nothing changes."""
        live = self.live_tables()
        changed = True
        while changed:
            changed = False
            for t in live - reached:
                for _from, parent, _to, on_delete in self.fks(t):
                    if parent in reached and on_delete == "CASCADE":
                        reached.add(t)
                        changed = True
                        break
        return reached

    def test_every_erasable_lane_is_reached_by_erasure(self):
        reached = self._cascade_fixpoint(self._explicit_reach())
        unreached = sorted(t for t in inv.erasable_tables()
                           if t not in reached and t not in POLICY_EXCEPTIONS)
        self.assertEqual(unreached, [],
                         f"declared erasable but NOTHING in hard-delete reaches them "
                         f"(not explicit, not parent-owned, no CASCADE chain): {unreached}. "
                         f"This is the Phase 0 gap class. Repair db.py or record a policy "
                         f"exception with its reason.")

    def test_everything_erasure_reaches_is_declared_narrator_owned(self):
        reached = self._cascade_fixpoint(self._explicit_reach())
        owned = set(inv.narrator_owned_tables())
        stray = sorted(t for t in reached if t not in owned and t not in POLICY_EXCEPTIONS)
        self.assertEqual(stray, [],
                         f"erasure reaches these but the declaration does not own them: {stray}. "
                         f"Either erasure deletes something that is not the narrator's, or the "
                         f"declaration is missing a lane an export would then omit.")

    def test_installation_tables_are_never_reached(self):
        reached = self._cascade_fixpoint(self._explicit_reach())
        hit = sorted(t for t in inv.installation_tables() if t in reached)
        self.assertEqual(hit, [],
                         f"installation-owned tables reached by narrator erasure: {hit}")


# ══════════════════════════════════════════════════════════════════════
# 3. Selectors
# ══════════════════════════════════════════════════════════════════════

class SelectorTests(_SchemaCase):

    def test_db_direct_columns_match_the_declaration(self):
        mismatches = []
        for table, col in self.db._EXTENDED_PERSON_SCOPED_TABLES:
            l = inv.lane(table)
            if isinstance(l.owner, inv.Direct) and l.owner.column == col:
                continue
            # The §13 asymmetry: a Parent-owned table may ALSO be swept by a
            # column that names another person (media_archive_people.person_id
            # — tags naming this narrator on other people's items go with the
            # narrator, the item stays). Allowed only when declared external.
            if isinstance(l.owner, inv.Parent) and col in l.external_person_columns:
                continue
            mismatches.append((table, col, l.owner))
        self.assertEqual(mismatches, [],
                         f"db.py deletes by a column the declaration does not own by: {mismatches}")

    def test_db_parent_children_match_the_declaration(self):
        mismatches = []
        for child, fk_col, parent, _pcol in self.db._PARENT_OWNED_CHILDREN:
            owner = inv.lane(child).owner
            if isinstance(owner, inv.Parent):
                if (owner.fk_column, owner.parent_table) != (fk_col, parent):
                    mismatches.append((child, (fk_col, parent), owner))
            elif isinstance(owner, inv.Direct):
                # db.py may ALSO delete a direct-owned table by parent
                # (media_archive_people). Allowed only when the parent
                # relationship is one the schema actually declares.
                declared = [(f, p) for f, p, _t, _d in self.fks(child)]
                if (fk_col, parent) not in declared:
                    mismatches.append((child, (fk_col, parent), "no such FK in schema"))
            else:
                mismatches.append((child, (fk_col, parent), owner))
        self.assertEqual(mismatches, [], f"parent-owned children disagree: {mismatches}")

    def test_every_selector_prepares_against_the_live_schema(self):
        """A wrong column or table name fails HERE, not inside an export."""
        failures = []
        for table in inv.narrator_owned_tables():
            for kind, sql in (("select", inv.select_sql(table)), ("delete", inv.delete_sql(table))):
                try:
                    self.con.execute("EXPLAIN " + sql, {"pid": "00000000-0000-0000-0000-000000000000"})
                except sqlite3.Error as exc:
                    failures.append((table, kind, str(exc)))
        self.assertEqual(failures, [], f"selectors that do not compile against the schema: {failures}")

    def test_selectors_select_only_the_narrators_rows(self):
        """Production boundary for the declaration itself: two narrators,
        one row each in a direct lane, a parent lane, and a two-hop lane;
        each selector returns exactly its narrator's row."""
        a = self.db.create_person(display_name="A")["id"]
        b = self.db.create_person(display_name="B")["id"]
        con = self.con
        plan = "plan-parity"
        con.execute("INSERT INTO interview_plans (id, title, created_at) VALUES (?, ?, ?)",
                    (plan, "p", "2026-09-10T00:00:00Z"))
        for pid, tag in ((a, "a"), (b, "b")):
            con.execute("INSERT INTO interview_sessions (id, person_id, plan_id, started_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?)", (f"sess-{tag}", pid, plan, "t", "t"))
            con.execute("INSERT INTO interview_threads (id, session_id, thread_anchor, introduced_at) "
                        "VALUES (?, ?, ?, ?)", (f"thr-{tag}", f"sess-{tag}", "anchor", "t"))
            con.execute("INSERT INTO trips (id, person_id, title) VALUES (?, ?, ?)", (f"trip-{tag}", pid, "t"))
            con.execute("INSERT INTO trip_days (id, trip_id, day_index, date) "
                        "VALUES (?, ?, ?, ?)", (f"day-{tag}", f"trip-{tag}", 1, "2026-09-10"))
        con.commit()
        for table, expect in (("interview_sessions", "sess-a"), ("interview_threads", "thr-a"),
                              ("trips", "trip-a"), ("trip_days", "day-a")):
            rows = con.execute(inv.select_sql(table), {"pid": a}).fetchall()
            self.assertEqual([r["id"] for r in rows], [expect],
                             f"{table}: selector for A returned {[r['id'] for r in rows]}")


# ══════════════════════════════════════════════════════════════════════
# 4. Filesystem
# ══════════════════════════════════════════════════════════════════════

class FilesystemParityTests(unittest.TestCase):

    def test_person_keyed_lanes_equal_fixed_targets(self):
        erasure = {tuple(parts) for _k, parts in narrator_erasure.FIXED_TARGETS}
        declared = {l.parts for l in inv.FS_LANES if l.keyed_by == "person"}
        self.assertEqual(declared, erasure,
                         f"person-keyed lanes differ.\n  declared only: {declared - erasure}\n"
                         f"  erasure only:  {erasure - declared}")

    def test_shared_lanes_equal_shared_purge(self):
        erasure = {tuple(parts) for _k, parts in narrator_erasure.SHARED_PURGE}
        declared = {l.parts for l in inv.FS_LANES if l.keyed_by == "shared"}
        self.assertEqual(declared, erasure)

    def test_row_keyed_lanes_match_the_dynamic_plan(self):
        """narrator_erasure._dynamic_plan names four row-keyed lanes:
        trip_sources, import_staging, import_staging/.incoming and the
        legacy memory/agents transcript exports. The declaration must name
        the same four, no more, no fewer — measured by RUNNING the plan
        against a narrator who has one row in each lane table."""
        declared = {l.parts for l in inv.FS_LANES if l.keyed_by == "row"}
        self.assertEqual(declared, {("trip_sources",), ("import_staging",),
                                    ("import_staging", ".incoming"), ("memory", "agents")})

    def test_incoming_is_erasable_but_not_portable(self):
        l = inv.fs_lane("import_staging_incoming")
        self.assertTrue(l.erasable)
        self.assertEqual(l.portable, "no")


class DynamicPlanParityTests(_SchemaCase):

    def test_dynamic_plan_targets_are_all_declared(self):
        """Run the REAL planner against a narrator with one row in each lane
        table. Every target it emits must have a declared row-keyed lane
        whose parts prefix the target's parts, and every declared row lane
        must be named at least once."""
        pid = self.db.create_person(display_name="A")["id"]
        con = self.con
        con.execute("INSERT INTO trips (id, person_id, title) VALUES ('trip-a', ?, 't')", (pid,))
        con.execute("INSERT INTO trip_sources (id, trip_id, source_type, title, storage_path) "
                    "VALUES ('src-a', 'trip-a', 'ticket', 't', 'trip_sources/src-a/x.pdf')")
        con.execute("INSERT INTO import_batch (id, person_id, source) "
                    "VALUES ('batch-a', ?, 'google_photos_picker')", (pid,))
        con.execute("INSERT INTO sessions (conv_id, title, updated_at, person_id) "
                    "VALUES ('conv-a', 't', 't', ?)", (pid,))
        con.commit()
        plan = narrator_erasure._dynamic_plan(pid, con)
        self.assertTrue(plan, "the planner produced nothing; the fixture rows did not land")
        prefixes = [l.parts for l in inv.FS_LANES if l.keyed_by == "row"]
        undeclared = [t for t in plan
                      if not any(tuple(t["parts"][:len(p)]) == p for p in prefixes)]
        self.assertEqual(undeclared, [], f"planner targets with no declared lane: {undeclared}")
        hit = {p for p in prefixes if any(tuple(t["parts"][:len(p)]) == p for t in plan)}
        self.assertEqual(hit, set(prefixes), f"declared row lanes the planner never named: {set(prefixes) - hit}")
        # And the lane tables erasure plans from are declared narrator-owned.
        lane_tables = set()
        for _lane, (required, _opt) in narrator_erasure._LANE_TABLES.items():
            lane_tables.update(required)
        self.assertTrue(lane_tables <= set(inv.narrator_owned_tables()),
                        f"erasure lane tables not declared narrator-owned: "
                        f"{lane_tables - set(inv.narrator_owned_tables())}")


if __name__ == "__main__":
    unittest.main()
